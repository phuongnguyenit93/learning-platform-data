# Phân biệt entity, mapped superclass và embeddable trong siêu dữ liệu

> **Chủ đề:** Data Persistence Relational Access ORM JPA  
> **Chương:** Siêu dữ liệu và lược đồ

Khi thiết kế domain model bằng Jakarta Persistence (JPA), không phải lớp Java nào có các thuộc tính cần lưu xuống cơ sở dữ liệu cũng nên được đánh dấu `@Entity`. Một số lớp đại diện cho **đối tượng có định danh và vòng đời riêng**, một số chỉ cung cấp **ánh xạ kế thừa cho nhiều entity**, trong khi một số khác là **giá trị cấu thành một đối tượng lớn hơn**.

Ba loại thường gặp là:

- `@Entity`: một kiểu thực thể có **persistent identity**. JPA có thể quản lý, tìm, cập nhật và xóa các đối tượng của kiểu này thông qua `EntityManager`.
- `@MappedSuperclass`: lớp cha khai báo thuộc tính và mapping để các entity con kế thừa. Bản thân lớp cha **không phải entity** và không phải một JPQL query root độc lập.
- `@Embeddable`: kiểu thành phần giá trị được nhúng vào entity hoặc một embeddable khác, hoặc xuất hiện như phần tử của `@ElementCollection`. Nó **không có identity/vòng đời entity độc lập**.

Sự khác biệt này ảnh hưởng trực tiếp đến **siêu dữ liệu JPA metamodel**, **cách provider lập ánh xạ cột/bảng**, **JPQL/Criteria API**, **trạng thái managed/detached**, **quy tắc @Id/@Version**, **kế thừa**, **schema generation** và **thiết kế aggregate**.

Một hiểu lầm cần loại bỏ ngay: “Có lớp Java” không đồng nghĩa “có bảng SQL riêng”. Entity có thể dùng cùng một bảng với entity khác trong một chiến lược kế thừa; mapped superclass không có bảng riêng chỉ vì được annotate; embeddable có thể được lưu trong bảng chủ sở hữu **hoặc** bảng collection khi được dùng với `@ElementCollection`.

Bài này sử dụng `jakarta.persistence.*` của các phiên bản JPA hiện đại. Với dự án legacy dùng `javax.persistence.*`, đổi package theo đúng stack. Các SQL/DDL là **minh họa cấu trúc logic**: tên bảng/cột, cú pháp sinh khóa và cách xử lý types phụ thuộc mapping, naming strategy và dialect.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích đúng vai trò của `@Entity`, `@MappedSuperclass` và `@Embeddable`.
2. Phân biệt **định danh entity** với **equality theo giá trị**.
3. Biết vì sao entity cần identity và thường có `@Id` hoặc `@EmbeddedId`.
4. Hiểu mapped superclass có thể chứa `@Id`, `@Version`, basic attributes, associations và callbacks để con kế thừa.
5. Hiểu embeddable không có EntityManager lifecycle độc lập, không được dùng như JPQL entity root.
6. Đọc một hierarchy Java và dự đoán entity nào có persistent metadata/table mapping.
7. Phân biệt `@MappedSuperclass` với một **abstract entity có @Inheritance**.
8. Biết khi nào chọn inheritance của entity thay vì mapping inheritance.
9. Thiết kế `Address` kiểu `@Embeddable` cho billing/shipping addresses mà không tạo bảng Address riêng.
10. Dùng `@Embedded`, `@AttributeOverride` và `@AttributeOverrides` để tránh trùng tên cột.
11. Dùng `@AssociationOverride` để tùy chỉnh join column của association được kế thừa hoặc nhúng.
12. Giải thích embeddable trong `@ElementCollection` và sự xuất hiện của collection table.
13. Giải thích `@EmbeddedId`: một embeddable có thể chứa composite primary key nhưng vẫn không phải entity.
14. Biết khi nào cần `@MapsId` với composite identifier.
15. Phân biệt field access và property access theo vị trí `@Id`/`@Access`.
16. Kiểm tra JPA metamodel qua `EntityManagerFactory.getMetamodel()`.
17. Phân biệt `EntityType`, `MappedSuperclassType` và `EmbeddableType` trong metadata API.
18. Tìm hiểu mapping inheritance, AttributeOverrides, default column naming và schema generation.
19. Truy vấn các thuộc tính nhúng qua JPQL path expressions hoặc Criteria API.
20. Nhận biết những lỗi thường gặp về duplicate columns, sai query root, missing ID và immutable value objects.
21. Kiểm tra persistence bằng `persist`/`flush`/`clear`/`find` và SQL logs.
22. Xây test phản ánh đúng lifecycle của entity và các giá trị nhúng.
23. Phân biệt **JPA managed type** với **SQL table** và **lớp Java thuần**.
24. Chọn cấu trúc ánh xạ dựa vào ranh giới trách nhiệm của domain, thay vì số lượng bảng muốn tạo.

---

## 2. Sơ đồ phân biệt ba loại

```text
                     JAVA DOMAIN MODEL
                            |
          +-----------------+-----------------+
          |                 |                 |
          v                 v                 v
      @Entity      @MappedSuperclass     @Embeddable
          |                 |                 |
          |                 |                 |
  Có identity riêng    Cung cấp mapping     Là thành phần giá trị
  Có lifecycle JPA     cho entity con       thuộc owner
  Query root hợp lệ    Không query root     Không query root
  EntityManager CRUD   Không EM CRUD        Không EM CRUD
          |                 |                 |
          |                 +--------+        |
          |                          |        |
          v                          v        v
  @Table / inheritance        Các cột/associations
  strategy / @SecondaryTable  được map vào entity/
                              bảng của entity con
                              hoặc collection table
```

Một ví dụ dễ hình dung:

```text
AuditedRecord                  <-- @MappedSuperclass
   id
   createdAt
   version
       |
       +-- Customer           <-- @Entity
              name
              billingAddress  <-- @Embedded Address
              shippingAddress <-- @Embedded Address
                       |
                       +-- street
                       +-- city
                       +-- postalCode
                       +-- countryCode

Bảng customers:
  id
  version
  created_at
  name
  billing_street
  billing_city
  billing_postal_code
  billing_country_code
  shipping_street
  shipping_city
  shipping_postal_code
  shipping_country_code
```

**Không có bảng `audited_record` và không bắt buộc có bảng `address` chỉ vì hai lớp ấy tồn tại trong Java.**

---

## 3. So sánh nhanh theo hợp đồng JPA

| Tiêu chí | `@Entity` | `@MappedSuperclass` | `@Embeddable` |
|---|---|---|---|
| Thuộc nhóm managed types trong metamodel | Có | Có | Có |
| Persistent identity độc lập | **Có** | **Không** | **Không** |
| Có primary key của chính kiểu đó | Có, trong entity hierarchy | Có thể khai báo ID **được con kế thừa**, nhưng bản thân không có entity identity | Không theo nghĩa entity độc lập; có thể biểu diễn composite ID khi được dùng với `@EmbeddedId` |
| `EntityManager.persist(instance)` trực tiếp | Có, khi hợp lệ | Không | Không |
| `EntityManager.find(Type.class,id)` | Có | Không | Không |
| JPQL `FROM Type t` | Có, dùng entity name | Không | Không |
| Có bảng SQL riêng mặc định | Thường có mapping entity vào bảng, nhưng inheritance có thể dùng chung | Không tạo bảng riêng | Không tạo bảng riêng khi @Embedded; có thể được lưu ở collection table |
| Có `@Table` dành riêng cho chính loại này | Có | Không dùng như entity table | Không dùng như entity table |
| Có thể có basic fields | Có | Có | Có |
| Có thể có association mappings | Có | Có, được kế thừa | Có trong trường hợp mapping phù hợp |
| Có thể dùng `@Version` | Có | Có, để entity con kế thừa | Không dùng để tạo entity version độc lập |
| Được subclass Java kế thừa | Có | Có | Có ở mức Java, nhưng mapping phải được kiểm soát |
| Có thể là abstract class | Có | Có, thường gặp | Có thể theo Java nhưng instantiation/mapping phụ thuộc provider; tránh giả định portable |
| Vai trò phổ biến | Customer, Invoice, Product | BaseEntity, AuditedRecord | Address, Money, Period, Coordinate |
| Dữ liệu cập nhật theo | Entity lifecycle | Lifecycle của entity con | Entity owner/collection lifecycle |

Một cách nhận biết:

- **Thứ cần tìm riêng theo ID, khóa, quản lý và tham chiếu** thường là entity.
- **Phần Java dùng lại các mapping giữa nhiều entities nhưng không có tồn tại nghiệp vụ độc lập** thường là mapped superclass.
- **Giá trị có ý nghĩa khi thuộc một owner và phù hợp với value semantics** thường là embeddable.

---

## 4. Entity: kiểu có identity và vòng đời

`@Entity` đánh dấu một lớp Java là JPA entity.

```java
package demo.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "sku", nullable = false, unique = true)
    private String sku;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    protected Product() {
        // Dành cho JPA provider.
    }

    public Product(String sku, String displayName) {
        this.sku = sku;
        this.displayName = displayName;
    }

    public Long getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }
}
```

### 4.1. `@Id` là điểm khác biệt quan trọng

Entity có identity JPA, thường được khai báo bằng `@Id` hoặc `@EmbeddedId`. Primary key có thể khai báo trong chính entity hoặc **kế thừa từ mapped superclass/entity parent**.

Không nhất thiết mọi entity phải viết lại `@Id` trong cùng source file: điều quan trọng là entity hierarchy có identity mapping hợp lệ.

### 4.2. Entity có trạng thái managed

```java
EntityManager em = emf.createEntityManager();

EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    Product p = new Product("JAVA-01", "Java Handbook");
    em.persist(p);

    em.flush();
    Long generatedId = p.getId();

    Product same = em.find(Product.class, generatedId);
    System.out.println(p == same); // cùng managed identity

    tx.commit();
} catch (RuntimeException error) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw error;
} finally {
    em.close();
}
```

EntityManager theo dõi Product khi managed, quản lý identity, dirty checking, persist/remove/merge/refresh/lock tùy trạng thái.

### 4.3. Entity không luôn ứng với đúng một bảng

Entity có thể dùng:

- `@Table` chính.
- `@SecondaryTable` cho một phần các cột.
- `@Inheritance(SINGLE_TABLE)`: nhiều entity types chia sẻ một bảng.
- `@Inheritance(JOINED)`: các bảng trong hierarchy được JOIN.
- `@Inheritance(TABLE_PER_CLASS)`: mỗi concrete entity có bảng riêng theo strategy.
- Join tables/collection tables cho các associations.

Vì vậy câu “entity = một bảng, luôn luôn” là một quy tắc giản lược dễ dẫn tới kết luận sai về metadata.

---

## 5. Mapped superclass: tái sử dụng mapping, không tạo entity riêng

`@MappedSuperclass` đánh dấu lớp có persistent mappings để **các entity con kế thừa**.

Ví dụ nhiều entities đều cần:

```text
id
version
createdAt
```

Thay vì lặp các annotations `@Id`, `@Version` và `@Column`, ta khai báo một lần:

```java
package demo.domain;

import jakarta.persistence.Access;
import jakarta.persistence.AccessType;
import jakarta.persistence.Column;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.MappedSuperclass;
import jakarta.persistence.Version;

import java.time.Instant;
import java.util.Objects;

@MappedSuperclass
@Access(AccessType.FIELD)
public abstract class AuditedRecord {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    @Column(name = "version", nullable = false)
    private long version;

    @Column(name = "created_at",
            nullable = false,
            updatable = false)
    private Instant createdAt;

    protected AuditedRecord() {
        // Entity subclasses kế thừa constructor mặc định.
    }

    protected void markCreated(Instant at) {
        if (createdAt != null) {
            throw new IllegalStateException(
                "Already initialized");
        }
        createdAt = Objects.requireNonNull(at);
    }

    public Long getId() {
        return id;
    }

    public long getVersion() {
        return version;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
```

### 5.1. Metadata được kế thừa

`Customer` extends `AuditedRecord` sẽ kế thừa ánh xạ ID, version và createdAt. DDL của bảng Customer sẽ có các cột tương ứng. Nhưng bảng `audited_record` **không** xuất hiện chỉ vì lớp cha được đánh dấu mapped superclass.

### 5.2. Không thể query mapped superclass như entity

Sai:

```jpql
SELECT a
FROM AuditedRecord a
```

Vì `AuditedRecord` không có entity name/query root theo JPA. Khi muốn query Customer, phải dùng:

```jpql
SELECT c
FROM Customer c
```

hoặc một **entity root** thích hợp nếu hierarchy thật sự dùng entity inheritance.

### 5.3. Không `persist` bản thân mapped superclass

Sai về API semantics:

```java
AuditedRecord base = ...;
em.persist(base);
```

Đối tượng thực tế cần là một entity concrete hợp lệ, chẳng hạn `Customer`. Mapped superclass không có bảng/lifecycle riêng để persist như một hàng độc lập.

### 5.4. Mapped superclass có bắt buộc là abstract không?

Không bắt buộc ở Java; annotation có thể gắn lên một lớp không abstract. Tuy nhiên viết `abstract` thường diễn đạt ý định tốt hơn: không có domain instance độc lập của base class.

### 5.5. Mapping không chỉ là scalar columns

Mapped superclass có thể khai báo basic properties, ID, version, associations và lifecycle callback methods theo các quy tắc mapping/inheritance tương ứng. Nó không chỉ là nơi chứa các getter/setter Java.

---

## 6. Entity con kế thừa mapped superclass

Dùng `Customer` để lưu thông tin khách hàng.

```java
package demo.domain;

import jakarta.persistence.AttributeOverride;
import jakarta.persistence.AttributeOverrides;
import jakarta.persistence.Column;
import jakarta.persistence.Embedded;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

import java.time.Instant;
import java.util.Objects;

@Entity
@Table(name = "customers")
public class Customer extends AuditedRecord {

    @Column(name = "display_name",
            nullable = false,
            length = 150)
    private String displayName;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(
            name = "street",
            column = @Column(name = "billing_street",
                             length = 180)),
        @AttributeOverride(
            name = "city",
            column = @Column(name = "billing_city",
                             length = 100)),
        @AttributeOverride(
            name = "postalCode",
            column = @Column(name = "billing_postal_code",
                             length = 30)),
        @AttributeOverride(
            name = "countryCode",
            column = @Column(name = "billing_country_code",
                             length = 2))
    })
    private Address billingAddress;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(
            name = "street",
            column = @Column(name = "shipping_street",
                             length = 180)),
        @AttributeOverride(
            name = "city",
            column = @Column(name = "shipping_city",
                             length = 100)),
        @AttributeOverride(
            name = "postalCode",
            column = @Column(name = "shipping_postal_code",
                             length = 30)),
        @AttributeOverride(
            name = "countryCode",
            column = @Column(name = "shipping_country_code",
                             length = 2))
    })
    private Address shippingAddress;

    protected Customer() {}

    public Customer(
            String displayName,
            Address billingAddress,
            Address shippingAddress,
            Instant createdAt) {
        this.displayName = Objects.requireNonNull(displayName);
        this.billingAddress =
            Objects.requireNonNull(billingAddress);
        this.shippingAddress =
            Objects.requireNonNull(shippingAddress);
        markCreated(createdAt);
    }

    public String getDisplayName() {
        return displayName;
    }

    public Address getBillingAddress() {
        return billingAddress;
    }

    public Address getShippingAddress() {
        return shippingAddress;
    }

    public void changeShippingAddress(Address address) {
        shippingAddress = Objects.requireNonNull(address);
    }
}
```

Ở code này:

- `Customer` là entity thật.
- `AuditedRecord` là mapped superclass.
- `Address` là embeddable được nhúng hai lần.
- Cột `id`, `version` và `created_at` đến từ mapped superclass.
- Các cột `billing_*`/`shipping_*` đến từ hai embedded fields, được override để không trùng tên.

### 6.1. DDL hình thành như thế nào?

Ví dụ logical DDL:

```sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    version BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    display_name VARCHAR(150) NOT NULL,
    billing_street VARCHAR(180),
    billing_city VARCHAR(100),
    billing_postal_code VARCHAR(30),
    billing_country_code VARCHAR(2),
    shipping_street VARCHAR(180),
    shipping_city VARCHAR(100),
    shipping_postal_code VARCHAR(30),
    shipping_country_code VARCHAR(2)
);
```

Cú pháp sinh ID và kiểu timestamp thay đổi theo DBMS; schema thực tế còn phụ thuộc cách JPA provider map `Instant`, defaults và naming strategy. Ý chính là **không có bảng riêng cho AuditedRecord hoặc hai Address objects**.

---

## 7. Embeddable: kiểu giá trị được nhúng

Một address trong nhiều domain là **value object**:

```java
package demo.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

import java.util.Objects;

@Embeddable
public class Address {

    @Column(name = "street", length = 180)
    private String street;

    @Column(name = "city", length = 100)
    private String city;

    @Column(name = "postal_code", length = 30)
    private String postalCode;

    @Column(name = "country_code", length = 2)
    private String countryCode;

    protected Address() {
        // JPA constructor.
    }

    public Address(
            String street,
            String city,
            String postalCode,
            String countryCode) {
        this.street = requireText(street);
        this.city = requireText(city);
        this.postalCode = requireText(postalCode);
        this.countryCode = requireText(countryCode);
    }

    private static String requireText(String value) {
        Objects.requireNonNull(value);
        String normalized = value.trim();

        if (normalized.isEmpty()) {
            throw new IllegalArgumentException(
                "Address field must not be blank");
        }
        return normalized;
    }

    public String getStreet() { return street; }
    public String getCity() { return city; }
    public String getPostalCode() { return postalCode; }
    public String getCountryCode() { return countryCode; }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof Address that)) return false;

        return street.equals(that.street)
            && city.equals(that.city)
            && postalCode.equals(that.postalCode)
            && countryCode.equals(that.countryCode);
    }

    @Override
    public int hashCode() {
        return Objects.hash(
            street, city, postalCode, countryCode);
    }
}
```

### 7.1. Embeddable không có `@Id` riêng

Hai Address có bốn fields giống nhau về giá trị thường được coi là cùng **giá trị** theo domain equality. Chúng không có primary key hoặc entity identity riêng để gọi `em.find(Address.class, 42L)`.

### 7.2. Không `persist` một embeddable trực tiếp

Sai:

```java
Address address = new Address(
    "1 Main St", "Hanoi", "100000", "VN");

em.persist(address); // không phải JPA entity
```

Đúng: đặt Address vào một entity, rồi persist owner.

```java
Customer customer = new Customer(
    "Lan",
    address,
    address,
    Instant.parse("2026-11-15T09:00:00Z")
);

em.persist(customer);
```

### 7.3. Embeddable là value object theo thiết kế domain

Java vẫn cho phép một embeddable có setters và mutable fields. Nhưng khi nó đại diện một giá trị như địa chỉ hoặc tiền, thiết kế hạn chế mutation thường giúp tránh hiệu ứng phụ giữa nhiều owners.

Ví dụ hai fields `billingAddress` và `shippingAddress` có thể tham chiếu cùng Address object trong Java tại lúc tạo. Nếu Address mutable, sửa object qua một tham chiếu có thể vô tình đổi cả hai trong memory. Dùng value objects bất biến về public API hoặc tạo bản sao theo ownership policy giúp rõ ràng hơn.

### 7.4. Có dùng Java record cho embeddable được không?

Khả năng ánh xạ record, constructor binding và immutable embeddables phụ thuộc **phiên bản Jakarta Persistence/JPA provider**. Một số providers có extensions hỗ trợ record-like value objects, nhưng không nên giả định mọi JPA stack portable đều có thể thay một `@Embeddable class` bằng Java record mà không cấu hình bổ sung.

Để minh họa JPA truyền thống, class có constructor không tham số phù hợp vẫn là lựa chọn an toàn.

---

## 8. Vì sao nhúng hai Address dễ tạo duplicate columns?

Nếu viết:

```java
@Entity
public class Customer {

    @Id
    private Long id;

    @Embedded
    private Address billingAddress;

    @Embedded
    private Address shippingAddress;
}
```

và cả hai Address có properties `street`, `city`, `postalCode`, `countryCode`, theo mapping mặc định provider có thể cố map hai occurrences vào **cùng tên cột** hoặc áp naming strategy khác nhau.

Một số providers hỗ trợ implicit component-path naming, nhưng không nên phụ thuộc vào convention chưa được xác nhận khi schema cần portable.

### 8.1. Giải pháp portable: @AttributeOverrides

Khai báo rõ từng cột cho mỗi occurrence:

```java
@Embedded
@AttributeOverrides({
    @AttributeOverride(
        name = "street",
        column = @Column(name = "billing_street")),
    @AttributeOverride(
        name = "city",
        column = @Column(name = "billing_city")),
    @AttributeOverride(
        name = "postalCode",
        column = @Column(name = "billing_postal_code")),
    @AttributeOverride(
        name = "countryCode",
        column = @Column(name = "billing_country_code"))
})
private Address billingAddress;
```

và tương tự `shipping_*`. Các overrides xác định rõ schema bất kể tên cột mặc định của Address.

### 8.2. @AttributeOverride thay cột, không tạo entity mới

`@AttributeOverride` không biến Address thành entity, không tạo bảng Address và không tạo independent identity. Nó chỉ thay mapping của một attribute **tại vị trí sở hữu**.

### 8.3. Ghi chú về nullability/length

Khi override bằng `@Column` mới, cần khai báo các column constraints cần thiết tại chỗ thay vì giả định mọi attribute của annotation cũ được giữ lại theo cách cộng dồn. Nếu billingAddress bắt buộc, quyết định cột nào `nullable=false` theo domain và DB schema.

---

## 9. Mapped superclass cũng cho phép override cột kế thừa

Giả sử một entity cần tên cột khác cho `createdAt`:

```java
@Entity
@Table(name = "archived_documents")
@AttributeOverride(
    name = "createdAt",
    column = @Column(
        name = "registered_at",
        nullable = false,
        updatable = false))
public class ArchivedDocument extends AuditedRecord {

    @Column(nullable = false)
    private String filename;

    protected ArchivedDocument() {}
}
```

Kết quả: mapped superclass vẫn khai báo persistent attribute `createdAt`, nhưng entity con dùng cột `registered_at` ở bảng của nó.

### 9.1. Không làm đổi mọi entity khác

Nếu `Customer` dùng `created_at`, còn `ArchivedDocument` dùng `registered_at`, hai entities có mapping riêng theo overrides. Không có “bảng cha” cần ALTER chỉ vì một con đổi tên cột.

### 9.2. Attribute name là tên thuộc tính Java được map

`name = "createdAt"` là **persistent attribute name**, không phải `"created_at"`. Việc nhầm property path Java với SQL column name là nguyên nhân lỗi mapping rất thường gặp.

### 9.3. Kế thừa không nhất thiết là kế thừa bảng

Mapped superclass mang mapping declarations xuống entity con, **không dùng JPA entity inheritance strategy** để tạo các bảng cha–con.

---

## 10. @MappedSuperclass khác một lớp Java cha thông thường

Ba trường hợp:

```java
public abstract class AbstractJavaBase {
    private String note;
}

@MappedSuperclass
public abstract class JpaMappedBase {
    @Column(name = "note")
    private String note;
}

@Entity
public class ConcreteEntity extends JpaMappedBase {
    @Id
    private Long id;
}
```

Nếu `note` nằm trong mapped superclass, nó thuộc metadata của ConcreteEntity theo mapping rules.

Còn field `note` trong **Java superclass không thuộc managed hierarchy và không được đánh dấu mapped superclass/entity** thì không nên mặc định rằng provider sẽ persist nó như một persistent field chỉ vì Java inheritance. JPA mapping hierarchy có các quy tắc riêng.

### 10.1. Java inheritance và persistence inheritance không đồng nhất

Java chỉ nói lớp con kế thừa members/methods. JPA còn cần biết superclass thuộc nhóm managed nào để suy ra persistent attributes, table mapping và query semantics.

### 10.2. Khi nào không cần mapped superclass?

Nếu chỉ cần tái sử dụng **logic thuần Java** mà không cần inherited persistence mapping, một plain abstract class hoặc composition có thể đủ. Đừng đánh dấu `@MappedSuperclass` lên mọi base class theo thói quen.

---

## 11. Abstract entity và mapped superclass khác nhau

Một entity cũng có thể là abstract:

```java
@Entity
@Inheritance(strategy = InheritanceType.JOINED)
public abstract class Payment {

    @Id
    @GeneratedValue
    private Long id;

    @Column(nullable = false)
    private BigDecimal amount;
}

@Entity
public class CardPayment extends Payment {
    private String cardNetwork;
}

@Entity
public class BankTransfer extends Payment {
    private String bankReference;
}
```

### 11.1. Abstract entity vẫn là entity type

`Payment` là một entity trong metamodel, dù Java không cho `new Payment()` trực tiếp.

Có thể dùng entity polymorphism:

```jpql
SELECT p
FROM Payment p
ORDER BY p.id
```

Truy vấn có thể trả instances của `CardPayment`, `BankTransfer` thuộc hierarchy theo semantics JPA.

### 11.2. Mapped superclass không là polymorphic query root

Nếu thay `@Entity` trên Payment bằng `@MappedSuperclass`:

```jpql
SELECT p FROM Payment p
```

không còn là JPQL entity root hợp lệ theo chuẩn. Mỗi entity con vẫn có thể được query riêng, nhưng không có một polymorphic entity type Payment chung trong JPA metamodel.

### 11.3. Tiêu chí quyết định

Dùng **abstract entity** khi cần:

- Polymorphic query trên kiểu cha.
- Association target đến kiểu cha như một entity.
- Một entity inheritance hierarchy rõ.
- Identity/lifecycle metadata của kiểu cha.

Dùng **mapped superclass** khi chỉ cần:

- Tái sử dụng ID/version/audit fields.
- Tái sử dụng mapping annotation/behavior.
- Không muốn entity name/table/hierarchy polymorphism cho lớp cha.

### 11.4. Mapped superclass không “rẻ hơn” mọi entity inheritance

Nó đơn giản về persistence polymorphism, nhưng nếu sau này cần repository/query liên kiểu con hoặc association đến lớp cha, lựa chọn mapped superclass có thể trở thành giới hạn. Quyết định theo domain use cases, không chỉ theo DDL ban đầu.

---

## 12. Entity inheritance strategies không áp dụng cho mapped superclass như entity root

Trong entity hierarchy, JPA hỗ trợ chiến lược:

| Strategy | Cấu trúc logic | Ghi chú |
|---|---|---|
| `SINGLE_TABLE` | Nhiều entity subclasses cùng một bảng | Có discriminator, cột subclasses có thể nullable |
| `JOINED` | Bảng của entity root và các bảng subclass, JOIN theo ID | Phù hợp kế thừa có common base entity |
| `TABLE_PER_CLASS` | Concrete entities có bảng riêng theo strategy | Polymorphic queries thường phức tạp/cost hơn |

Ví dụ:

```java
@Entity
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(name = "payment_kind")
public abstract class Payment {
    @Id
    private Long id;
}
```

`@MappedSuperclass` **không phải** một entity root để áp cùng ý nghĩa polymorphic persistence hierarchy và discriminator.

### 12.1. So sánh DDL

```text
Mapped superclass:
  AuditedRecord
      |
      +-- Customer -> customers(id,version,created_at,...)
      +-- Supplier -> suppliers(id,version,created_at,...)

Abstract entity + JOINED:
  Payment -> payments(id,amount,...)
      |
      +-- CardPayment -> card_payments(id,card_network)
      +-- BankTransfer -> bank_transfers(id,bank_reference)
```

### 12.2. Một entity có thể vừa kế thừa mapped superclass vừa là entity root

Ví dụ:

```text
AuditedRecord                 @MappedSuperclass
      |
      v
Payment                       @Entity @Inheritance(...)
      |
      +-- CardPayment         @Entity
      +-- BankTransfer        @Entity
```

Khi đó audit fields nằm trên mapping entity Payment theo inheritance strategy; mapped superclass vẫn không trở thành entity root độc lập.

---

## 13. Embeddable không phải entity association

Hai cách biểu diễn địa chỉ:

### Cách A: Address là giá trị của Customer

```java
@Embeddable
public class Address {
    private String street;
    private String city;
}

@Entity
public class Customer {
    @Embedded
    private Address shippingAddress;
}
```

Địa chỉ không có identity riêng. Khi Customer thay shippingAddress, owner state được cập nhật theo mapping.

### Cách B: Address là entity được quản lý độc lập

```java
@Entity
public class AddressRecord {
    @Id
    private Long id;

    private String street;
    private String city;
}

@Entity
public class Customer {
    @ManyToOne
    private AddressRecord shippingAddress;
}
```

Một AddressRecord có thể được nhiều Customers tham chiếu, query/update/delete riêng theo identity.

### 13.1. Chọn theo identity và lifecycle

Nếu địa chỉ là snapshot value gắn với một Customer/Order và không có lifecycle riêng, embeddable thường phù hợp.

Nếu địa chỉ có ID riêng, workflow phê duyệt, nhiều đối tượng cùng tham chiếu và business muốn update một address chung, entity có thể hợp lý hơn.

### 13.2. Vấn đề shared mutable state

Nếu một `@Embeddable Address` bị chia sẻ cùng Java instance giữa nhiều Customers và bị mutate, các owners có thể thay đổi không mong muốn. Thiết kế value semantics giúp tránh lỗi này.

Nếu dùng một Address entity chung, việc cập nhật một row có thể cố ý làm thay đổi dữ liệu tham chiếu ở nhiều owners. Đây là semantics rất khác.

---

## 14. Embeddable có thể chứa association

Không nên nói “embeddable chỉ được chứa kiểu primitive/string”. Tùy quy tắc JPA mapping và use case, embeddable có thể chứa association như `@ManyToOne`.

Ví dụ một contact point có vùng phân phối:

```java
@Embeddable
public class ContactPoint {

    @Column(name = "phone_number")
    private String phoneNumber;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "region_id")
    private Region region;
}
```

Giả sử `Region` là entity có ID riêng.

Khi ContactPoint được nhúng trong Customer, `phoneNumber` và **foreign key của association region** được ánh xạ vào location phù hợp của owner (hoặc collection table nếu dùng theo mapping hợp lệ).

### 14.1. Association không biến embeddable thành entity

`ContactPoint` vẫn không có identity/entity lifecycle riêng. `Region` là entity được nó tham chiếu, và có identity riêng.

### 14.2. Không phải mapping association nào cũng hợp lệ trong mọi ngữ cảnh

Cần xem embeddable được nhúng trực tiếp hay dùng trong `@ElementCollection`, owner là gì và provider/dialect hỗ trợ mapping tương ứng. Tránh giả định mọi loại relationship/cascade có cùng semantics ở tất cả embeddable contexts.

---

## 15. @AssociationOverride khác @AttributeOverride

`@AttributeOverride` dành cho **basic/embedded attribute column mappings**. Khi cần đổi **join column** của association đã được khai báo trong embeddable hoặc mapped superclass, dùng `@AssociationOverride`.

Ví dụ:

```java
@Entity
public class Customer {

    @Id
    private Long id;

    @Embedded
    @AssociationOverride(
        name = "region",
        joinColumns = @JoinColumn(
            name = "shipping_region_id"))
    private ContactPoint shippingContact;
}
```

Ở ví dụ này `ContactPoint.region` là association `@ManyToOne`.

### 15.1. Phân biệt bằng loại mapping

| Điều cần override | Annotation |
|---|---|
| Cột `Address.city` | `@AttributeOverride` |
| Cột `AuditedRecord.createdAt` được kế thừa | `@AttributeOverride` |
| Join column của `ContactPoint.region` | `@AssociationOverride` |
| Join table của một association có mapping phù hợp | `@AssociationOverride` với mapping tương ứng |

### 15.2. Một association inherited từ mapped superclass

Nếu mapped superclass khai báo `@ManyToOne Department department`, entity con có thể override join column bằng `@AssociationOverride` trên class để phù hợp schema của chính nó.

Không dùng `@AttributeOverride` để đổi FK của một association và mong provider tự suy.

---

## 16. Embeddable lồng nhau

Có thể tạo một value object bên trong value object khác.

```java
@Embeddable
public class Coordinates {

    @Column(name = "latitude")
    private BigDecimal latitude;

    @Column(name = "longitude")
    private BigDecimal longitude;

    protected Coordinates() {}

    public Coordinates(
            BigDecimal latitude,
            BigDecimal longitude) {
        this.latitude = latitude;
        this.longitude = longitude;
    }
}

@Embeddable
public class LocationDetails {

    @Embedded
    private Address address;

    @Embedded
    private Coordinates coordinates;

    protected LocationDetails() {}
}
```

Entity dùng:

```java
@Entity
public class Warehouse {

    @Id
    private Long id;

    @Embedded
    private LocationDetails locationDetails;
}
```

### 16.1. Cột có thể được flatten vào bảng entity

Trong mapping embedded thông thường, các basic attributes như `locationDetails.address.city` và `locationDetails.coordinates.latitude` được ánh xạ vào bảng của Warehouse, trừ khi có mapping/collection context khác.

### 16.2. Override đường dẫn lồng nhau

Tại vị trí owner có thể override nested attribute bằng dotted path theo attribute names:

```java
@Embedded
@AttributeOverride(
    name = "address.city",
    column = @Column(name = "warehouse_city"))
private LocationDetails locationDetails;
```

Các names trong path là persistent attribute names, không phải SQL column names.

### 16.3. Không nhầm @Embedded với một JOIN

Lồng nhau trong Java không mặc nhiên tạo JOIN giữa các SQL tables. Embeddable thường mô tả các cột của location lưu trữ được ánh xạ, không phải foreign-key relationship đến một entity Address.

---

## 17. @ElementCollection: embeddable có thể nằm trong bảng riêng

Một trường hợp khác:

```java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    private Long id;

    @ElementCollection
    @CollectionTable(
        name = "customer_saved_addresses",
        joinColumns = @JoinColumn(name = "customer_id"))
    @AttributeOverrides({
        @AttributeOverride(
            name = "street",
            column = @Column(name = "street")),
        @AttributeOverride(
            name = "city",
            column = @Column(name = "city")),
        @AttributeOverride(
            name = "postalCode",
            column = @Column(name = "postal_code")),
        @AttributeOverride(
            name = "countryCode",
            column = @Column(name = "country_code"))
    })
    private List<Address> savedAddresses =
        new ArrayList<>();
}
```

Đây là một **ví dụ Customer giản lược độc lập** để minh họa element collection, không phải khai báo Customer thứ hai trong cùng package với ví dụ phần 6.

DDL có thể gồm:

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY
);

CREATE TABLE customer_saved_addresses (
    customer_id BIGINT NOT NULL,
    street VARCHAR(180),
    city VARCHAR(100),
    postal_code VARCHAR(30),
    country_code VARCHAR(2),
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);
```

### 17.1. Có bảng collection không làm Address thành entity

`@ElementCollection` sử dụng collection table, nhưng mỗi Address value **không có entity identity riêng**. Không gọi:

```java
em.find(Address.class, 123L);
```

để lấy từng Address element theo PK entity.

### 17.2. Lifecycle vẫn thuộc owner

Thêm/bớt Address khỏi collection của Customer làm provider đồng bộ collection state theo mapping. Điều này không tương đương `persist(address)`/`remove(address)` riêng như với entity association.

### 17.3. Duplicates, equality và List order

Nếu lưu `List<Address>` và thứ tự có ý nghĩa, có thể cần `@OrderColumn` theo mapping; nếu dùng `Set<Address>`, equality/hashCode của value object cần ổn định. Một collection table có thể cần khóa hoặc order column cụ thể tùy thiết kế. Đừng giả định mỗi element tự có một ID độc lập chỉ vì nằm ở một SQL row.

### 17.4. @ElementCollection thường được tải LAZY theo mapping default, nhưng cần kiểm tra

JPA định nghĩa fetch mode với `@ElementCollection`; provider có thể tải theo chiến lược riêng. Không serialize trực tiếp collections trên detached entities mà không có fetch plan/DTO phù hợp.

---

## 18. @EmbeddedId: embeddable chứa composite key

Có một trường hợp embeddable **giữ giá trị định danh** nhưng vẫn không phải entity:

```java
package demo.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

import java.io.Serializable;
import java.util.Objects;

@Embeddable
public class ExchangeRateId implements Serializable {

    @Column(name = "base_currency",
            nullable = false, length = 3)
    private String baseCurrency;

    @Column(name = "quote_currency",
            nullable = false, length = 3)
    private String quoteCurrency;

    protected ExchangeRateId() {}

    public ExchangeRateId(
            String baseCurrency,
            String quoteCurrency) {
        this.baseCurrency =
            Objects.requireNonNull(baseCurrency);
        this.quoteCurrency =
            Objects.requireNonNull(quoteCurrency);
    }

    public String getBaseCurrency() {
        return baseCurrency;
    }

    public String getQuoteCurrency() {
        return quoteCurrency;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof ExchangeRateId that)) {
            return false;
        }

        return baseCurrency.equals(that.baseCurrency)
            && quoteCurrency.equals(that.quoteCurrency);
    }

    @Override
    public int hashCode() {
        return Objects.hash(baseCurrency, quoteCurrency);
    }
}
```

Entity:

```java
package demo.domain;

import jakarta.persistence.Column;
import jakarta.persistence.EmbeddedId;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

import java.math.BigDecimal;

@Entity
@Table(name = "exchange_rates")
public class ExchangeRate {

    @EmbeddedId
    private ExchangeRateId id;

    @Column(name = "rate", nullable = false,
            precision = 19, scale = 8)
    private BigDecimal rate;

    protected ExchangeRate() {}

    public ExchangeRate(
            ExchangeRateId id,
            BigDecimal rate) {
        this.id = id;
        this.rate = rate;
    }

    public ExchangeRateId getId() {
        return id;
    }
}
```

### 18.1. Ai là entity?

`ExchangeRate` là entity có identity là `ExchangeRateId` composite value. `ExchangeRateId` là embeddable, không phải entity.

### 18.2. @EmbeddedId không tạo một bảng ID riêng

DDL:

```sql
CREATE TABLE exchange_rates (
    base_currency VARCHAR(3) NOT NULL,
    quote_currency VARCHAR(3) NOT NULL,
    rate DECIMAL(19,8) NOT NULL,
    PRIMARY KEY (base_currency, quote_currency)
);
```

### 18.3. Find theo embedded ID

```java
ExchangeRateId id =
    new ExchangeRateId("USD", "VND");

ExchangeRate rate =
    em.find(ExchangeRate.class, id);
```

EntityManager tìm **ExchangeRate** bằng key object, không tìm ExchangeRateId như một entity.

### 18.4. Composite ID phải có equality đúng

Key classes cần equality/hashCode nhất quán với database identity. Fields của key nên ổn định sau khi entity được persist; không mutate ID object làm thay đổi identity trong persistence context.

### 18.5. @IdClass khác @EmbeddedId

`@IdClass` khai báo key class song song với nhiều `@Id` fields/properties trên entity. `@EmbeddedId` khai báo **một embedded ID attribute**. Hai kiểu có khác biệt về JPQL path và code organization; không đồng nghĩa key class của `@IdClass` tự trở thành embeddable attribute của entity.

---

## 19. @MapsId với embedded composite identifier

Trong một số mô hình, composite ID chứa foreign key đến entity owner.

Ví dụ OrderLine có composite key `(orderId,lineNumber)`:

```java
@Embeddable
public class OrderLineId implements Serializable {

    private Long orderId;
    private Integer lineNumber;

    protected OrderLineId() {}

    // Constructor, equals và hashCode theo hai giá trị.
}

@Entity
public class OrderLine {

    @EmbeddedId
    private OrderLineId id;

    @MapsId("orderId")
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(nullable = false)
    private String sku;
}
```

Giả sử `PurchaseOrder` là entity có primary key Long.

### 19.1. Vai trò @MapsId

`@MapsId("orderId")` liên kết association `order` với phần `orderId` của embedded ID. Nó cho phép mapping composite key và relationship nhất quán.

### 19.2. Embeddable key không trở thành entity

`OrderLineId` vẫn là value object cho identity của `OrderLine`; association target `PurchaseOrder` là entity riêng.

### 19.3. Lưu ý generator và identifier values

Composite assigned IDs có lifecycle/validation riêng. Không áp `@GeneratedValue` đơn giản theo kiểu IDENTITY Long cho mọi phần của composite ID và mong cùng một mapping portable. Hãy chọn key strategy rõ và kiểm tra provider.

---

## 20. Field access và property access quyết định metadata

JPA có hai chiến lược truy cập phổ biến:

- **Field access:** annotations mapping trên fields.
- **Property access:** annotations trên getters JavaBeans.

Ví dụ field access:

```java
@Entity
public class Product {

    @Id
    private Long id;

    @Column(name = "product_name")
    private String name;

    public Long getId() { return id; }
    public String getName() { return name; }
}
```

Ví dụ property access:

```java
@Entity
public class Product {

    private Long id;
    private String name;

    @Id
    public Long getId() {
        return id;
    }

    @Column(name = "product_name")
    public String getName() {
        return name;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public void setName(String name) {
        this.name = name;
    }
}
```

### 20.1. Vị trí @Id thường xác định access strategy mặc định

Đặt `@Id` trên field dẫn đến field access theo hierarchy mapping rules. Đặt trên getter dẫn đến property access. Dùng `@Access(AccessType.FIELD)` hoặc `PROPERTY` khi cần minh bạch và đúng quy tắc override/access.

### 20.2. Mapped superclass cần thống nhất access

Nếu mapped superclass có `@Id` trên getter còn entity con đặt annotations trên fields mà không khai báo access policy hợp lệ, metadata có thể không như dự đoán. Cấu trúc JPA hierarchy cần tuân theo rules của mixed access.

### 20.3. Embeddable thừa hưởng context access theo mapping rules

Trong trường hợp thông dụng, embeddable sử dụng access type phù hợp với owner/mapping context, trừ khi `@Access` được khai báo. Nếu annotation nằm trên wrong access path, một attribute có thể bị bỏ qua hoặc được map khác dự kiến.

### 20.4. Dùng @Transient khi cần loại một attribute

`@Transient` dùng để đánh dấu Java field/property không thuộc persistent state theo JPA mapping, khác với keyword Java `transient` theo serialization semantics.

Một giá trị tính từ Address có thể không cần cột:

```java
@Transient
public String getFormattedAddress() {
    return street + ", " + city;
}
```

Nếu entity đang dùng field access, việc thêm `@Transient` trên getter theo mixed access không được tùy tiện coi là tương đương đánh dấu field. Đặt annotation phù hợp với access strategy hoặc thiết kế getter không thuộc persistent property access.

---

## 21. JPA metamodel là gì?

**Metamodel** là API siêu dữ liệu do `EntityManagerFactory` cung cấp, mô tả các managed types và persistent attributes mà JPA provider đã nhận diện.

```java
EntityManagerFactory emf = ...;

Metamodel metamodel = emf.getMetamodel();
```

Các giao diện quan trọng trong package `jakarta.persistence.metamodel`:

- `Metamodel`: điểm truy cập danh sách các managed types.
- `ManagedType<X>`: kiểu được JPA quản lý ở tầng metadata.
- `EntityType<X>`: metadata dành cho `@Entity`.
- `MappedSuperclassType<X>`: metadata dành cho `@MappedSuperclass`.
- `EmbeddableType<X>`: metadata dành cho `@Embeddable`.
- `IdentifiableType<X>`: metadata cho kiểu có thể có identity mapping/hierarchy identity.
- `Attribute<X,Y>`: một persistent attribute.
- `SingularAttribute<X,Y>` và `PluralAttribute<X,C,E>`: phân biệt singular/plural persistent attributes.
- `Type.PersistenceType`: phân loại metadata như ENTITY, MAPPED_SUPERCLASS, EMBEDDABLE, BASIC.

### 21.1. “Managed type” không đồng nghĩa “entity”

Cả ba loại đều có thể nằm trong `getManagedTypes()`, nhưng chỉ `EntityType` là entity type để truy vấn/persist trực tiếp.

### 21.2. MappedSuperclassType vẫn có metadata

Vì fields được ánh xạ cho entity con, mapped superclass có managed metadata riêng, dù không có table/entity name/query root độc lập.

### 21.3. EmbeddableType vẫn có metadata

Provider cần biết các thuộc tính của Address/ExchangeRateId để flatten columns hoặc map composite ID, nên chúng xuất hiện trong metamodel dù không có `@Id` riêng theo kiểu entity.

---

## 22. Đọc toàn bộ managed types bằng Metamodel API

Ví dụ:

```java
package demo.inspect;

import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.metamodel.Attribute;
import jakarta.persistence.metamodel.ManagedType;
import jakarta.persistence.metamodel.Metamodel;

public final class JpaMetadataInspector {

    public static void printManagedTypes(
            EntityManagerFactory emf) {

        Metamodel mm = emf.getMetamodel();

        for (ManagedType<?> type : mm.getManagedTypes()) {
            System.out.println(
                type.getJavaType().getName()
                + " => " + type.getPersistenceType()
            );

            for (Attribute<?, ?> attr :
                    type.getDeclaredAttributes()) {

                System.out.printf(
                    "  %s : %s [%s]%n",
                    attr.getName(),
                    attr.getJavaType().getSimpleName(),
                    attr.getPersistentAttributeType()
                );
            }
        }
    }
}
```

### 22.1. Kết quả minh họa

```text
demo.domain.AuditedRecord => MAPPED_SUPERCLASS
  id : Long [BASIC]
  version : long [BASIC]
  createdAt : Instant [BASIC]

demo.domain.Address => EMBEDDABLE
  street : String [BASIC]
  city : String [BASIC]
  postalCode : String [BASIC]
  countryCode : String [BASIC]

demo.domain.Customer => ENTITY
  displayName : String [BASIC]
  billingAddress : Address [EMBEDDED]
  shippingAddress : Address [EMBEDDED]
```

Thứ tự trả về của set trong `getManagedTypes()` và `getDeclaredAttributes()` không nên được coi là thứ tự trình bày ổn định; nếu test snapshot metadata, hãy sort theo tên.

### 22.2. getDeclaredAttributes khác getAttributes

`getDeclaredAttributes()` chỉ chứa persistent attributes **được khai báo trên chính managed type** theo metadata.

`getAttributes()` bao gồm attributes đã được kế thừa từ managed supertype (theo hierarchy), khi đó Customer có thể thấy cả `id`, `version`, `createdAt`.

### 22.3. Attribute type không phải SQL type

`attr.getJavaType() == String.class` không có nghĩa DB column luôn là VARCHAR(255); còn `@Column(length)`, converter, enum/LOB mapping và dialect.

Metamodel API mô tả JPA persistent model, không phải toàn bộ DDL/physical storage metadata.

---

## 23. Phân biệt EntityType, MappedSuperclassType, EmbeddableType

Đọc bằng API:

```java
import jakarta.persistence.metamodel.EmbeddableType;
import jakarta.persistence.metamodel.EntityType;
import jakarta.persistence.metamodel.ManagedType;
import jakarta.persistence.metamodel.MappedSuperclassType;
import jakarta.persistence.metamodel.Metamodel;
import jakarta.persistence.metamodel.Type;

Metamodel mm = emf.getMetamodel();

EntityType<Customer> customerType =
    mm.entity(Customer.class);

EmbeddableType<Address> addressType =
    mm.embeddable(Address.class);

ManagedType<AuditedRecord> baseType =
    mm.managedType(AuditedRecord.class);

if (baseType instanceof MappedSuperclassType<?>) {
    System.out.println(
        "AuditedRecord is a mapped superclass");
}

System.out.println(
    customerType.getPersistenceType()
        == Type.PersistenceType.ENTITY);

System.out.println(
    addressType.getPersistenceType()
        == Type.PersistenceType.EMBEDDABLE);
```

### 23.1. Dùng đúng lookup method

`mm.entity(Customer.class)` hợp lệ khi Customer thuộc entity metadata.

`mm.embeddable(Address.class)` hợp lệ khi Address được nhận diện là embeddable.

`mm.managedType(AuditedRecord.class)` truy xuất metadata cho mapped superclass.

Không gọi `mm.entity(AuditedRecord.class)` rồi mong nó hoạt động như entity: class đó không phải entity type.

### 23.2. Những loại được biết tới tùy persistence unit

Nếu Address không được dùng trong mappings, không được đăng ký/scan hoặc provider không nhận diện, việc gọi `embeddable(Address.class)` có thể không tìm thấy metadata như mong đợi. Metadata đến từ **persistence unit đang được boot**, không phải mọi lớp có annotation trên classpath.

### 23.3. Kiểm tra danh sách EntityType

```java
for (EntityType<?> entityType :
        emf.getMetamodel().getEntities()) {
    System.out.println(
        entityType.getName()
        + " -> "
        + entityType.getJavaType().getName()
    );
}
```

Danh sách này chỉ chứa entity types đã được JPA đăng ký, **không** chứa Address/AuditedRecord như entity.

### 23.4. Kiểm tra danh sách EmbeddableType

```java
for (EmbeddableType<?> embeddable :
        emf.getMetamodel().getEmbeddables()) {
    System.out.println(
        embeddable.getJavaType().getSimpleName()
    );
}
```

`@MappedSuperclass` có thể được nhận diện qua `getManagedTypes()` và `getPersistenceType()`, không cần giả định có một phương thức `getMappedSuperclasses()` trên `Metamodel`.

---

## 24. @Entity(name=...) khác @Table(name=...)

Một lỗi rất phổ biến là nhầm **JPQL entity name** với tên SQL table.

```java
@Entity(name = "Client")
@Table(name = "customers")
public class Customer {
    @Id
    private Long id;
}
```

Khi đó:

```jpql
SELECT c
FROM Client c
```

là JPQL dùng entity name đã cấu hình. Còn SQL do provider phát thường truy cập bảng `customers`.

### 24.1. @Entity(name) không đổi Java class name

Java class vẫn là `Customer`; metamodel `entityType.getJavaType()` trả Customer.class, trong khi `entityType.getName()` là "Client".

### 24.2. @MappedSuperclass và @Embeddable không có JPQL entity name

Không thể làm:

```jpql
SELECT a FROM Address a
```

chỉ vì một property Address được nhúng vào Customer.

### 24.3. Alias trong JPQL không phải table alias khai báo trực tiếp

`FROM Client c` dùng entity identification variable `c`; provider chịu trách nhiệm dịch sang SQL FROM/JOIN/aliases đúng mapping.

---

## 25. JPQL truy vấn các trường của embeddable

Dù Address không là JPQL root, có thể truy vấn **through an entity owner**.

```jpql
SELECT c
FROM Customer c
WHERE c.billingAddress.city = :city
ORDER BY c.id
```

Trong đó:

- `Customer` là entity name.
- `billingAddress` là embedded attribute.
- `city` là basic attribute của embeddable.

### 25.1. Truy vấn DTO projection

```jpql
SELECT NEW demo.dto.CustomerCard(
    c.id,
    c.displayName,
    c.billingAddress.city
)
FROM Customer c
WHERE c.shippingAddress.countryCode = :country
ORDER BY c.displayName, c.id
```

DTO constructor phải phù hợp types và parameter ordering.

### 25.2. Không JOIN một basic embedded field như entity association

Không giả định:

```jpql
JOIN c.billingAddress a
```

là một relational entity JOIN giống `JOIN c.orders`. Embedded value attributes thường được ánh xạ vào same storage row và truy cập bằng path expression; cú pháp/khả năng JOIN path đối với embedded attributes khác entity relationships, cần tuân thủ JPQL spec/provider. Thường chỉ cần `c.billingAddress.city`.

### 25.3. Embedded path ảnh hưởng SQL column

Với override, `c.billingAddress.city` được dịch sang cột `billing_city` trong bảng Customer, không phải cột `city` ở bảng Address riêng.

---

## 26. Criteria API đi qua embedded attributes

```java
import jakarta.persistence.criteria.CriteriaBuilder;
import jakarta.persistence.criteria.CriteriaQuery;
import jakarta.persistence.criteria.Root;

CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<Customer> cq =
    cb.createQuery(Customer.class);

Root<Customer> customer =
    cq.from(Customer.class);

cq.select(customer)
  .where(
      cb.equal(
          customer.get("billingAddress").get("city"),
          "Hanoi"
      )
  )
  .orderBy(cb.asc(customer.get("id")));

List<Customer> result =
    em.createQuery(cq).getResultList();
```

### 26.1. Root phải là entity

`cq.from(Customer.class)` hợp lệ vì Customer là entity.

Không dùng:

```java
cq.from(Address.class);
```

để tạo root độc lập nếu Address chỉ là `@Embeddable`.

### 26.2. Nested path vẫn được typed

Với JPA static metamodel được generate, có thể dùng những attributes typed, ví dụ `Customer_.billingAddress`/`Address_.city` tùy toolchain. Điều này giảm lỗi typo khi refactor so với chuỗi `"billingAddress"`.

### 26.3. Association bên trong embeddable thì khác

Nếu ContactPoint có `@ManyToOne Region`, việc điều hướng `contactPoint.region.name` cần dịch sang join theo relationship mapping. Đừng áp nguyên nhận định “mọi property của embeddable nằm cùng bảng” cho cả entity association.

---

## 27. Một entity có thể có nhiều embedded values cùng loại

Ví dụ hệ thống logistics:

```text
Shipment (@Entity)
  pickupAddress  (@Embedded Address)
  dropoffAddress (@Embedded Address)
  returnAddress  (@Embedded Address)
```

Đây là cùng **Java type** được dùng ba lần với ba vị trí ánh xạ khác nhau.

### 27.1. Đừng để column naming dựa vào tình cờ

Nên đặt:

```text
pickup_street / pickup_city / ...
dropoff_street / dropoff_city / ...
return_street / return_city / ...
```

bằng explicit overrides hoặc naming strategy được dự án cam kết.

### 27.2. Value object nên biểu diễn giá trị của từng thời điểm

Địa chỉ giao hàng thường cần snapshot ngay lúc đặt đơn. Nếu nhúng Address vào Order, khi Customer đổi địa chỉ mặc định, các Orders cũ không tự bị sửa — thường là điều mong muốn.

Ngược lại, nếu Orders tham chiếu một Address entity chung được update, lịch sử giao hàng có thể thay đổi theo record tham chiếu. Đó là quyết định domain rất quan trọng.

---

## 28. Nullability của embeddable và kiểm tra persisted state

Một embedded object có thể là null, tùy mapping/constraints. Ví dụ:

```java
private Address shippingAddress;
```

Khi null, các mapped columns tương ứng có thể là NULL. Khi đọc lại, việc provider tạo `Address` object trống hay trả null trong một số trường hợp “toàn bộ columns null” có các chi tiết implementation/mapping cần kiểm tra.

### 28.1. Dùng DB constraints rõ ràng khi value bắt buộc

Nếu shipping address bắt buộc, có thể đặt `nullable=false` cho các columns quan trọng hoặc enforce domain validation/constraints phù hợp. Không nhầm `@Embedded` tự biến toàn bộ value object thành non-null database constraint.

### 28.2. Partial null values

Một Address có street nhưng thiếu city có thể là trạng thái không hợp lệ theo nghiệp vụ, dù DB cho phép một số columns NULL. Kiểm tra ở domain constructor và database schema nếu yêu cầu bảo vệ dữ liệu mọi write path.

### 28.3. Đọc lại sau flush/clear

Unit test Address constructor chỉ kiểm tra Java invariants; integration test cần `persist(customer)`, `flush()`, `clear()` rồi `find` để xác minh cột billing/shipping không bị hoán đổi hoặc collision.

---

## 29. Value equality khác entity identity

Hai Address:

```java
Address first = new Address(
    "12 Lake Road", "Hanoi", "100000", "VN");

Address second = new Address(
    "12 Lake Road", "Hanoi", "100000", "VN");
```

Với `equals/hashCode` theo fields:

```java
System.out.println(first.equals(second)); // true
```

Hai Product entities có cùng displayName nhưng khác IDs **không** là cùng entity identity. Entity equality/hashCode cần cân nhắc primary key lifecycle/proxies/generated ID.

### 29.1. Embeddable equality theo value semantics

Với value object, equality theo các fields thường tự nhiên. Nếu Address immutable từ góc nhìn domain, equality ổn định.

### 29.2. EmbeddedId equality còn quan trọng hơn

Composite ID class phải có `equals/hashCode` đúng với identity fields. Nếu ID object mutable trong một Map/Set hoặc sau khi được gắn với entity, khả năng lookup/identity có thể gặp lỗi.

### 29.3. Embeddable không tự tham gia identity map như entity

Persistence context quản lý Customer, chứ không tạo một independent identity entry cho mỗi Address embedded field theo kiểu `Address#ID`.

---

## 30. Change tracking cho embeddable dựa vào owner

Nếu Customer đang managed:

```java
Customer customer = em.find(Customer.class, id);

customer.changeShippingAddress(
    new Address(
        "99 River Street",
        "Danang",
        "550000",
        "VN"
    )
);

em.flush();
```

Provider phát SQL UPDATE trên bảng Customer theo mapping, nếu nhận diện thay đổi và transaction cho phép.

### 30.1. Không cần em.persist(newAddress)

`Address` không là entity; đặt value mới lên managed Customer và flush là workflow phù hợp cho basic embedded mapping.

### 30.2. Không có cascading persist đến Address như một entity

`CascadeType.PERSIST` liên quan entity associations, không phải yêu cầu để lưu các cột của một `@Embedded Address`. Không cần đặt `cascade=ALL` lên embedded value chỉ để insert billing_city.

### 30.3. Dirty checking sâu của mutable embeddable

Provider có thể nhận diện thay đổi fields bên trong embeddable, nhưng bytecode enhancement, property access, immutability và equals/dirty-checking implementation có thể ảnh hưởng. Với value object, thay cả embedded value qua domain method thường dễ reasoning/test hơn sửa trực tiếp một field nested mutable.

### 30.4. Version của owner

Nếu Customer có `@Version` từ mapped superclass, khi UPDATE owner theo ORM, version thường được quản lý. Address không có version độc lập. Concurrency checks bảo vệ entity owner theo mapping, không bảo vệ một “Address entity” riêng.

---

## 31. Mapped superclass và lifecycle callbacks

Mapped superclass không có lifecycle entity độc lập, nhưng **callback methods được kế thừa** có thể áp dụng cho entity con theo lifecycle rules.

Ví dụ:

```java
@MappedSuperclass
public abstract class TimestampedBase {

    @Column(name = "updated_at")
    private Instant updatedAt;

    @PreUpdate
    protected void beforeUpdate() {
        updatedAt = Instant.now();
    }
}

@Entity
public class InventoryItem extends TimestampedBase {

    @Id
    private Long id;

    private String label;
}
```

Khi InventoryItem có UPDATE thực tế qua entity lifecycle, callback kế thừa có thể gán updatedAt.

### 31.1. Không có callback “mapped superclass persisted”

`@PreUpdate` thuộc lifecycle của **InventoryItem entity instance**, không phải một entity TimestampedBase riêng.

### 31.2. Callback không chạy trên bulk JPQL update

`UPDATE InventoryItem i SET ...` là bulk DML và không kích hoạt callback cho từng managed entity như dirty checking.

### 31.3. Callback có thể ảnh hưởng testability

`Instant.now()` gắn cứng làm test thời gian kém xác định. Nếu cần audit metadata nghiêm ngặt, cân nhắc service stamping với injected `Clock` hoặc auditing framework có DateTimeProvider. Bản chất mapped superclass không tự cung cấp dependency injection.

---

## 32. @Version và @Id trong mapped superclass

Một pattern:

```java
@MappedSuperclass
public abstract class BaseEntity {

    @Id
    @GeneratedValue
    private Long id;

    @Version
    private long version;

    // getters...
}
```

Sau đó:

```java
@Entity
public class Customer extends BaseEntity {
    private String name;
}

@Entity
public class Supplier extends BaseEntity {
    private String companyName;
}
```

### 32.1. ID có thể trùng giữa các entity types khác nhau

Customer ID 42 và Supplier ID 42 không phải cùng entity. Identity ở JPA bao gồm entity type/hierarchy context và primary key, không phải chỉ một số `42` trên toàn database.

### 32.2. Generation strategy cần phù hợp nhiều tables

Nếu mọi entity con dùng IDENTITY trên bảng riêng, mỗi bảng có thể tự sinh IDs. Nếu dùng sequence generation, cấu hình sequence/generator cần rõ để tránh bất ngờ giữa database dialects/hierarchies.

### 32.3. @Version của entity con

Version field khai báo trong mapped superclass được entity con kế thừa và quản lý. Không cần đặt @Version mới trùng lặp trong mỗi entity con; một entity hierarchy thường có một version attribute theo rules của JPA.

### 32.4. Không dùng @Version trong Address để mong khóa Address riêng

Address embedded không có independent entity update/lifecycle. Concurrency quản lý ở Customer hoặc entity owner, không phải một version entry riêng cho Address.

---

## 33. Chọn superclass hay composition?

Mapped superclass thường tiện khi nhiều entities có fields giống nhau. Nhưng inheritance không phải luôn là cách thiết kế domain tốt nhất.

### 33.1. Khi mapped superclass phù hợp

```text
BaseRecord
  id
  version
  createdAt
  createdBy

Customer extends BaseRecord
Product extends BaseRecord
Invoice extends BaseRecord
```

Các field này có mapping/semantics giống nhau trên nhiều entity types.

### 33.2. Khi embeddable composition phù hợp

```text
Customer
  @Embedded ContactInfo contact

Supplier
  @Embedded ContactInfo contact
```

ContactInfo là một khái niệm giá trị hoàn chỉnh (phone, email, preferred channel), không phải “is-a” relationship.

### 33.3. Một thiết kế có thể kết hợp cả hai

```text
@MappedSuperclass AuditedRecord
   |
   +-- @Entity Customer
          |
          +-- @Embedded Address
          +-- @Embedded ContactInfo
```

**Inheritance** dùng để tái sử dụng common mapping; **composition** dùng để biểu diễn domain value concepts. Chúng không loại trừ nhau.

### 33.4. Dùng embeddable thay base class cho audit fields được không?

Có thể mô hình `@Embedded AuditInfo` chứa createdAt/updatedAt/actor fields, nếu domain muốn nhóm metadata thành value object. Nhưng cần xử lý lifecycle callback/time stamping, column overrides và attribute access thích hợp. Không có công thức bắt buộc rằng audit fields luôn phải nằm trong mapped superclass.

---

## 34. Đặt tên cột qua @Embedded AuditInfo

Ví dụ value grouping:

```java
@Embeddable
public class AuditInfo {
    private Instant createdAt;
    private Instant updatedAt;

    protected AuditInfo() {}
}

@Entity
public class PurchaseOrder {

    @Id
    private Long id;

    @Embedded
    private AuditInfo audit;
}
```

Cách này nhóm fields theo **composition** thay vì inheritance.

### 34.1. Lợi ích

Entity code thể hiện `order.getAudit().getUpdatedAt()`, nhóm các metadata liên quan. Một vài entities không có audit cũng không cần extends BaseEntity.

### 34.2. Hạn chế

- Query paths dài hơn: `o.audit.updatedAt`.
- Metadata của `AuditInfo` là EMBEDDABLE, không phải superclass.
- Audit lifecycle stamping không tự động chỉ vì @Embedded.
- Nếu cần một `@Id` chung, vẫn phải khai báo ở entity hoặc mapped superclass.

### 34.3. Khi đã có BaseEntity và embedded AuditInfo

Có thể dùng `BaseEntity` cho ID/version, `AuditInfo` cho timestamps/actors. Cách chia này có thể mang lại ranh giới trách nhiệm rõ nhưng cần tránh quá nhiều abstraction nhỏ vô nghĩa.

---

## 35. Liên hệ schema generation và database migration

JPA mapping metadata và physical database schema không tự đồng nhất mọi lúc.

### 35.1. Mapping model

Provider đọc:

```text
Customer @Entity
  inherits AuditedRecord fields
  embeds Address twice with overrides
```

và lập metadata cột:

```text
customers.id
customers.version
customers.created_at
customers.billing_city
customers.shipping_city
...
```

### 35.2. Schema generation

Nếu bật schema generation, provider có thể tạo DDL tương ứng. Nhưng:

- Tên cột mặc định phụ thuộc naming strategy.
- Kiểu dữ liệu phụ thuộc dialect.
- `@Column(length/nullable/unique)` ảnh hưởng metadata schema.
- Constraints/indexes có thể cần khai báo riêng hoặc migration.
- Inheritance strategy thay đổi cấu trúc tables.
- Foreign keys và join tables phụ thuộc association mappings.

### 35.3. Production nên quản lý migration có kiểm soát

Với hệ thống production, thường dùng migration tool như Flyway/Liquibase và giữ DDL nhất quán với JPA mappings. Không cho rằng đổi `@AttributeOverride` rồi deploy sẽ tự chuyển dữ liệu từ cột cũ sang cột mới an toàn.

### 35.4. Schema validation

JPA provider có thể cung cấp validate/update/generation options, nhưng chúng không thay thế test migration data correctness. Metadata inspector giúp biết kiểu/attribute names; SQL schema checks xác minh physical table/column tồn tại.

### 35.5. @MappedSuperclass không tạo “bảng base record”

Nếu cần một bảng chung chứa tất cả records với foreign keys về từng subtype, mapped superclass đơn thuần không thực hiện điều đó. Cần entity inheritance/association hoặc schema riêng.

---

## 36. Ánh xạ association qua mapped superclass

Một mapped superclass có thể khai báo:

```java
@MappedSuperclass
public abstract class DepartmentOwned {

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "department_id")
    private Department department;

    protected DepartmentOwned() {}

    public Department getDepartment() {
        return department;
    }
}
```

Giả sử Department là entity.

Entity con:

```java
@Entity
@Table(name = "employees")
@AssociationOverride(
    name = "department",
    joinColumns = @JoinColumn(
        name = "home_department_id"))
public class Employee extends DepartmentOwned {

    @Id
    private Long id;

    private String fullName;
}
```

### 36.1. Association vẫn thuộc entity con

DepartmentOwned không có independent foreign-key row. Khi Employee được lưu, `home_department_id` nằm trên bảng Employee theo mapping.

### 36.2. Dùng override khi schema mỗi entity khác nhau

Một subclass khác có thể dùng `department_id` mặc định; Employee override thành `home_department_id`.

### 36.3. Không áp inheritance cascading như entity relationship

Java extends mapped superclass không là một `@ManyToOne`/`@OneToMany` association và không dùng `CascadeType` để “persist superclass”. Những fields inherited được persist như một phần entity child.

---

## 37. Khi nào cần @Entity chứ không phải @Embeddable?

Một checklist domain:

| Câu hỏi | Gợi ý |
|---|---|
| Object có business identity ổn định không? | Có thể là entity |
| Có cần tìm riêng qua ID không? | Entity |
| Có lifecycle cập nhật/phê duyệt riêng không? | Entity |
| Nhiều owners có cùng tham chiếu đến **một đối tượng chung** không? | Entity |
| Thay đổi object chung phải tác động mọi owners không? | Entity có thể hợp lý |
| Object chủ yếu là một tập giá trị không cần ID không? | Embeddable |
| Muốn giữ snapshot tại thời điểm đặt hàng không? | Embeddable thường phù hợp |
| Muốn query root `FROM Address` không? | Nếu có, cần entity |
| Chỉ muốn tái sử dụng mapping giữa entities? | Mapped superclass |
| Muốn polymorphic query root trên lớp cha? | Abstract entity |

### 37.1. Bẫy “mọi thứ có tên là Entity”

Domain code có thể đặt tên `MoneyEntity` nhưng nếu chỉ gồm amount và currency và không có identity, embeddable có thể đúng hơn. Ngược lại, một “Address” có thể là entity nếu nó có identity và independent lifecycle thật.

### 37.2. Bẫy “ít bảng hơn là tốt”

Đưa mọi khái niệm vào embedded columns có thể tạo bảng rất rộng và khó query độc lập. Tạo entity cho mọi trường nhỏ có thể dẫn đến quá nhiều JOIN, cascading và lifecycle complexity. Chọn theo nghiệp vụ, cardinality và access patterns.

---

## 38. Mối liên hệ với repository/DAO

Spring Data JPA repositories thường làm việc với **entity root**:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
```

Lớp `Customer` phải là entity được JPA managed; `Long` là ID type.

Không nên khai báo `JpaRepository<Address,Long>` khi Address chỉ là embeddable, vì Address không có independent primary key/entity metadata.

### 38.1. Query theo embedded field trong repository

Có thể định nghĩa repository query:

```java
@Query("""
    SELECT c
    FROM Customer c
    WHERE c.billingAddress.city = :city
    ORDER BY c.id
    """)
List<Customer> findByBillingCity(String city);
```

Đó là query trên Customer entity root, không cần repository riêng cho Address.

### 38.2. Repository cho abstract entity

Với `@Entity abstract Payment` trong một inheritance hierarchy, một repository/query trên Payment có thể xử lý các subtype theo semantics JPA. Nếu Payment chỉ là `@MappedSuperclass`, không có polymorphic JPA entity root theo kiểu đó.

### 38.3. CRUD của embedded value thông qua owner

Đổi địa chỉ:

```text
load managed Customer
change shippingAddress
flush / commit
```

không phải “save Address riêng rồi cập nhật foreign key” trừ khi Address được thiết kế là entity.

---

## 39. Static metamodel và compile-time type safety

JPA còn có khái niệm **static metamodel classes**, thường được tạo bằng annotation processor khi build.

Ví dụ conceptual:

```java
@StaticMetamodel(Customer.class)
public abstract class Customer_ {

    public static volatile SingularAttribute<Customer, Long> id;

    public static volatile SingularAttribute<Customer, Address>
        billingAddress;

    public static volatile SingularAttribute<Customer, String>
        displayName;
}
```

Generated code/thành phần thực tế phụ thuộc processor/provider và cách JPA superclass attributes được kế thừa trong static metamodel.

### 39.1. Đường đi typed trong Criteria

Thay:

```java
root.get("billingAddress").get("city")
```

bằng dạng tương ứng dùng generated static metamodel nếu có:

```java
root.get(Customer_.billingAddress)
    .get(Address_.city)
```

Tên và types phải khớp generated metamodel; không thể dùng code này nếu build không sinh `Customer_`/`Address_`.

### 39.2. Mapped superclass cũng có metamodel type

Một annotation processor có thể sinh metamodel đại diện cho AuditedRecord và inherited attributes, giúp Criteria truy xuất các fields inherited mà không cần literal strings. Điều này thể hiện mapped superclass được JPA biết tới trong metadata dù không phải entity root.

### 39.3. Không nhầm metamodel class với entity class

`Customer_` là metadata helper được sinh, không phải một entity để `persist` và không có table riêng.

---

## 40. Triển khai thí nghiệm JPA đầy đủ

Giả sử persistence unit đã đăng ký các classes tương ứng.

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;

import java.time.Instant;

public final class MappingExperiment {

    public static Long createCustomer(
            EntityManagerFactory emf) {

        EntityManager em = emf.createEntityManager();
        EntityTransaction tx = em.getTransaction();

        try {
            tx.begin();

            Address billing = new Address(
                "12 Main Street", "Hanoi", "100000", "VN");

            Address shipping = new Address(
                "7 River Road", "Danang", "550000", "VN");

            Customer customer = new Customer(
                "Nguyen Lan",
                billing,
                shipping,
                Instant.parse("2026-11-15T09:00:00Z")
            );

            em.persist(customer);
            em.flush();

            Long id = customer.getId();

            tx.commit();
            return id;
        } catch (RuntimeException failure) {
            if (tx.isActive()) tx.rollback();
            throw failure;
        } finally {
            em.close();
        }
    }

    public static void verifyCustomer(
            EntityManagerFactory emf,
            Long id) {

        EntityManager em = emf.createEntityManager();

        try {
            Customer loaded =
                em.find(Customer.class, id);

            if (loaded == null) {
                throw new IllegalStateException(
                    "Customer was not persisted");
            }

            System.out.println(
                loaded.getId()
                + " / "
                + loaded.getCreatedAt()
            );

            System.out.println(
                loaded.getBillingAddress().getCity()
                + " -> "
                + loaded.getShippingAddress().getCity()
            );
        } finally {
            em.close();
        }
    }
}
```

### 40.1. Vì sao đọc bằng EntityManager mới?

Sau `persist`, Customer đã managed trong context hiện tại. Đọc trong context mới giúp quan sát state được persist, không chỉ object identity trong L1.

### 40.2. L2 cache có thể ảnh hưởng số SQL SELECT

Nếu provider bật shared cache, `find` ở EntityManager mới có thể được phục vụ từ L2. Khi test cần xác minh **physical storage mapping**, có thể dùng SQL/native inspection, tắt/bypass shared cache hoặc thiết kế test phù hợp.

### 40.3. Transaction model

Code dùng `RESOURCE_LOCAL` và `em.getTransaction()`. Trong Spring/JTA-managed transaction, cần dùng transaction manager/`@Transactional` thay vì copy nguyên flow transaction control trên container-managed EntityManager.

---

## 41. Kiểm chứng database schema trên target DBMS

Sau khi persist một Customer:

```sql
SELECT
    id,
    version,
    created_at,
    display_name,
    billing_street,
    billing_city,
    billing_postal_code,
    billing_country_code,
    shipping_street,
    shipping_city,
    shipping_postal_code,
    shipping_country_code
FROM customers
WHERE id = ?;
```

Tùy SQL client, dùng bind parameter/placeholder tương ứng.

### 41.1. Điều cần quan sát

- `id/version/created_at` nằm trong Customers table dù khai báo ở mapped superclass.
- `billing_city` và `shipping_city` khác nhau.
- Không cần bảng Address cho hai trường `@Embedded`.
- Dữ liệu đọc lại qua JPA khớp SQL columns.
- `@Version` thuộc owner entity.
- Schema constraints phản ánh optionality cần thiết.

### 41.2. Không suy từ entity class name ra tên table chính xác

`@Table(name)` có thể được khai báo hoặc naming strategy có thể đổi tên. Không thể chỉ nhìn class `Customer` mà đoán chắc SQL có bảng `Customer` viết hoa.

### 41.3. Kiểm tra metadata cùng DDL

`getMetamodel()` cho biết JPA mapping types; SQL schema inspection cho biết physical tables. Hai nguồn bổ trợ nhau, không thay thế nhau.

---

## 42. Kiểm thử thay đổi embedded value và optimistic version

Một test:

```java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    Customer customer = em.find(Customer.class, customerId);
    long oldVersion = customer.getVersion();

    customer.changeShippingAddress(
        new Address(
            "99 New Road", "Hue", "530000", "VN")
    );

    em.flush();

    long newVersion = customer.getVersion();

    // Kiểm tra theo provider/ID/version semantics.
    // Bảo đảm UPDATE owner và persistent version thay đổi
    // nếu đây là một dirty update được ORM quản lý.

    tx.commit();
} catch (RuntimeException failure) {
    if (tx.isActive()) tx.rollback();
    throw failure;
} finally {
    em.close();
}
```

Đọc lại trong context mới để xác nhận:

```text
shipping_city = "Hue"
billing_city vẫn = "Hanoi"
created_at không thay
owner version tăng theo successful update
```

### 42.1. Embeddable không có transaction riêng

Thay Address value và commit là một phần transaction của Customer. Không có `tx.commitAddress()` độc lập trong JPA.

### 42.2. Value equality giúp nhận diện no-op

Nếu new Address bằng current Address, domain có thể quyết định không gọi setter hoặc trả `false`. Tuy nhiên số UPDATE thực tế vẫn phụ thuộc mapping/dirty-checking provider và những fields khác được sửa trong transaction.

### 42.3. Không dùng timestamp làm thay thế version

Một timestamp có thể trùng giữa concurrent changes; optimistic versioning là cơ chế concurrency riêng.

---

## 43. Hành vi với null embeddable trong queries

Ví dụ:

```jpql
SELECT c
FROM Customer c
WHERE c.shippingAddress.city = :city
```

Nếu shippingAddress null, các columns có thể là NULL; query sẽ tuân theo SQL NULL semantics.

### 43.1. Không mong so sánh equals null hoạt động như Java

`c.shippingAddress.city = NULL` không phải điều kiện SQL/JPA đúng để tìm null. Dùng `IS NULL` cho attribute phù hợp:

```jpql
SELECT c
FROM Customer c
WHERE c.shippingAddress.city IS NULL
```

### 43.2. Toàn bộ embedded object null không nhất thiết tương đương city null

Nếu Address object có city null nhưng street non-null, city IS NULL vẫn true. Nếu nghiệp vụ cần phân biệt toàn bộ embedded value absent với một phần values null, schema/mapping/domain cần một indicator hoặc quy tắc rõ.

### 43.3. Nullability constraints

Các cột có `nullable=false` sẽ từ chối null ở DB, bất kể object graph Java được cấu tạo thế nào. Unit test JPA mapping nên có scenario intentionally invalid để xác minh constraint thực tế.

---

## 44. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
|---|---|---|
| `em.persist(Address)` thất bại | Address là embeddable, không entity | Persist owner |
| `FROM Address a` lỗi JPQL | Address không có entity name | Query Customer rồi đi qua path |
| `FROM BaseRecord b` lỗi | BaseRecord là mapped superclass | Query entity con hoặc thiết kế abstract entity |
| Duplicate column mapping | Embedded same type nhiều lần | AttributeOverrides/prefix naming |
| SQL không có bảng AuditedRecord | Mapped superclass không tạo bảng | Đúng thiết kế, xem entity table |
| SQL không có bảng Address | `@Embedded` flatten fields | Đúng, không tạo table riêng |
| Có bảng cho Address values | `@ElementCollection` dùng collection table | Đúng, không là entity |
| `@Id` ở base nhưng subclass startup lỗi | Access strategy/hierarchy mapping | Kiểm tra @MappedSuperclass và vị trí annotation |
| Column created_at bị map sai | AttributeOverride sai tên Java field | Dùng persistent attribute name |
| Association FK giữ tên cũ | Dùng AttributeOverride thay AssociationOverride | Override join column đúng loại |
| EmbeddedId find không được | equals/hashCode/key values sai | Key class đúng semantics |
| @EmbeddedId class không Serializable | Composite key contract chưa đủ | Implement Serializable và constructors |
| Đổi embedded Address không thấy DB update | Entity detached hoặc dirty checking khác dự kiến | Load managed owner, flush/transaction |
| Hai embedded fields đổi cùng nhau | Reuse mutable object instance | Immutable/copy semantics |
| @Version không có trong subclass | Mapping hierarchy sai | Khai báo base mapped superclass đúng |
| Query root abstract class không được | Abstract class là mapped superclass, không entity | @Entity inheritance nếu cần polymorphism |
| Repository cho embeddable lỗi | Không có independent entity ID | Repository cho owner |
| Metamodel không thấy Address | Chưa được dùng/scan/registered | Kiểm tra persistence unit |
| DDL tên khác annotation | Naming strategy/dialect | Xem actual SQL/schema |
| Override nullable/length không đúng | Quên khai báo constraints trên override | Kiểm soát @Column đầy đủ |
| EntityManager mới vẫn không SELECT | L2 cache đang hit | Bypass/disable khi test physical DB |
| JPQL path đến embedded lỗi | Sai persistent attribute name/access | Kiểm tra metamodel.getAttributes() |
| MappedSuperclass không xuất hiện trong getEntities | Đúng vì không là EntityType | Xem getManagedTypes |
| @Table đặt lên mapped superclass không như mong đợi | Mapped superclass không có table riêng | Đặt @Table ở entity con |
| Record embeddable chạy ở provider này lỗi provider khác | Extension/phiên bản khác | Kiểm tra JPA portability |
| @OneToMany child change không update parent | Child association không làm dirty basic parent | Touch aggregate root theo business |
| Column trùng khi nested @Embedded | Override path chưa đủ | Dotted attribute override/metadata review |

---

## 45. Bài thực hành A — Nhận diện ba loại

Cho các classes:

```text
Product
Order
Customer
AuditedBase
Address
Money
OrderLineId
Payment
CardPayment
```

1. Phân loại theo business identity/lifecycle/value/mapping reuse.
2. Đánh dấu `@Entity` cho Product, Order, Customer theo giả định phù hợp.
3. Đánh dấu `@MappedSuperclass` cho AuditedBase.
4. Đánh dấu `@Embeddable` cho Address và Money.
5. Dùng `@EmbeddedId` cho OrderLineId nếu model composite key phù hợp.
6. Thiết kế Payment như abstract entity nếu cần polymorphic query.
7. Giải thích vì sao không thể quyết định chỉ dựa trên tên class.

## 46. Bài thực hành B — Mapped superclass chứa ID/version

1. Tạo `AuditedRecord` có `@Id`, `@GeneratedValue`, `@Version`, `createdAt`.
2. Tạo `Customer` và `Supplier` extends AuditedRecord.
3. Đánh dấu cả hai là entities, có `@Table` riêng.
4. Persist một Customer và một Supplier.
5. Kiểm tra SQL tables chỉ có `customers` và `suppliers` cho hai entities.
6. Xác nhận các cột id/version/createdAt nằm ở mỗi table.
7. Thử `FROM AuditedRecord r` và ghi nhận vì sao không phải query root.
8. Thử `FROM Customer c` và `FROM Supplier s`.
9. Đọc JPA metamodel và phân biệt persistence types.

## 47. Bài thực hành C — Hai Address embedded

1. Tạo Address embeddable có street/city/postalCode/countryCode.
2. Thêm billingAddress và shippingAddress vào Customer.
3. Đặt `@Embedded` lên cả hai.
4. Kiểm tra DDL khi không có overrides.
5. Thêm đầy đủ `@AttributeOverrides` với billing_* và shipping_*.
6. Persist Customer có hai addresses khác nhau.
7. Flush/clear, nạp lại Customer.
8. Assert billingAddress và shippingAddress đúng.
9. Kiểm tra trực tiếp các SQL columns.
10. Thay shippingAddress và xác nhận billingAddress không đổi.

## 48. Bài thực hành D — Entity Address thay embeddable

1. Định nghĩa AddressRecord `@Entity` có `@Id`.
2. Customer liên kết AddressRecord bằng `@ManyToOne`.
3. Persist hai Customers tham chiếu cùng AddressRecord.
4. Update AddressRecord và commit.
5. Quan sát dữ liệu chung của Customers khi đọc lại.
6. So sánh với hai snapshot embedded Addresses.
7. Thảo luận lifecycle/ownership/consistency.
8. Chọn thiết kế phù hợp với địa chỉ giao hàng của đơn hàng đã chốt.

## 49. Bài thực hành E — Abstract entity vs mapped superclass

1. Tạo Payment abstract `@Entity`.
2. Thêm `@Inheritance(strategy=JOINED)`.
3. Tạo CardPayment/BankTransfer.
4. Persist hai subclasses.
5. Truy vấn `FROM Payment p`.
6. Ghi SQL JOINs/schema.
7. Thử đổi Payment thành mapped superclass trong một mô hình riêng.
8. Quan sát JPQL polymorphic root không còn tương đương.
9. Giải thích sự khác biệt giữa Java inheritance và JPA entity inheritance.

## 50. Bài thực hành F — @ElementCollection

1. Tạo Customer với `List<Address> savedAddresses`.
2. Gắn `@ElementCollection` và `@CollectionTable`.
3. Persist Customer có ba Address values.
4. Kiểm tra bảng customer_saved_addresses.
5. Đọc lại collection sau flush/clear.
6. Thử thêm một Address, rồi xóa một Address.
7. Quan sát SQL collection synchronization.
8. Thử `em.persist(address)` trực tiếp và giải thích không hợp lệ.
9. Thử `@OrderColumn` nếu thứ tự có ý nghĩa nghiệp vụ.
10. So sánh collection table với entity relationship table.

## 51. Bài thực hành G — @EmbeddedId

1. Tạo ExchangeRateId chứa baseCurrency và quoteCurrency.
2. Implement Serializable/equals/hashCode.
3. Tạo ExchangeRate entity dùng `@EmbeddedId`.
4. Persist rate USD/VND.
5. Find bằng ExchangeRateId mới có cùng values.
6. Query `r.id.baseCurrency = :code`.
7. Kiểm tra composite PK hai columns.
8. Thử một key class thiếu equals/hashCode và giải thích rủi ro.
9. So sánh với @IdClass.
10. Thử mapping @MapsId trong OrderLine nếu phù hợp.

## 52. Bài thực hành H — Metamodel inspection

1. Boot EntityManagerFactory đã đăng ký các managed types.
2. Gọi `getMetamodel().getEntities()`.
3. Gọi `getMetamodel().getEmbeddables()`.
4. Gọi `getMetamodel().getManagedTypes()`.
5. In `getJavaType()` và `getPersistenceType()` cho từng type.
6. So sánh EntityType/EmbeddableType/MappedSuperclassType.
7. Gọi `getDeclaredAttributes()` và `getAttributes()` trên Customer.
8. Xác nhận inherited `id`, `version`, `createdAt`.
9. Kiểm tra `billingAddress` có persistent type EMBEDDED.
10. Cố gọi `metamodel.entity(Address.class)` và giải thích sai loại type.
11. Sort output theo tên để kết quả test deterministic.

## 53. Bài thực hành I — JPQL và Criteria

1. Tạo 10 Customers với các billing cities khác nhau.
2. Viết JPQL `WHERE c.billingAddress.city = :city`.
3. Viết Criteria `root.get("billingAddress").get("city")`.
4. So sánh IDs kết quả.
5. Đổi `@AttributeOverride` cho billing_city.
6. Kiểm tra JPQL/Criteria vẫn dùng Java attribute names.
7. Bật SQL logging và quan sát physical column name.
8. Thử dùng Address làm query root và giải thích lỗi.
9. Nếu có static metamodel, dùng Customer_/Address_ để thay string paths.

## 54. Bài thực hành J — Override association

1. Tạo Region entity có ID.
2. Tạo ContactPoint embeddable tham chiếu Region bằng @ManyToOne.
3. Nhúng ContactPoint vào Customer.
4. Dùng @AssociationOverride để đổi FK thành shipping_region_id.
5. Persist Customer và Region.
6. Xác minh FK column trong SQL.
7. Thử @AttributeOverride trên region và giải thích vì sao không đúng loại.
8. Kiểm tra JPA metamodel association attribute.

## 55. Bài thực hành K — Access type và inheritance

1. Tạo mapped superclass đặt @Id trên field.
2. Tạo entity con đặt @Column trên fields.
3. Ghi metadata mapping bằng getAttributes.
4. Viết một model thử khác dùng getter annotations.
5. Dùng @Access khi cần mixed access có kiểm soát.
6. Kiểm tra duplicated/missing attributes.
7. Thử @Transient cho một calculated property.
8. Giải thích vì sao placement annotations ảnh hưởng metadata.
9. Chạy test provider bootstrap/schema validation.

## 56. Bài thực hành L — Đổi embedded value và version

1. Persist Customer với billing/shipping Addresses.
2. Ghi owner version.
3. Thay shippingAddress bằng Address mới.
4. Flush/commit.
5. Nạp lại Customer ở context mới.
6. Xác minh shipping fields thay đổi, billing fields không đổi.
7. Xác minh version tăng theo ORM successful update.
8. Thử concurrent update bằng hai EntityManagers.
9. Kiểm tra conflict và persisted state sau rollback.
10. Giải thích vì sao Address không có @Version độc lập.

---

## 57. Checklist thiết kế trước khi triển khai

| Câu hỏi | Điều cần chốt |
|---|---|
| Lớp có business identity độc lập không? | Chọn entity khi cần |
| Có cần `EntityManager.find` theo ID không? | Entity |
| Có cần query root trên lớp này không? | Entity/abstract entity |
| Chỉ cần kế thừa mapping? | Mapped superclass |
| Có cần polymorphic query root của superclass? | Abstract entity, không phải mapped superclass |
| Có thể dùng composition value object không? | Embeddable |
| Value có nghĩa độc lập khỏi owner không? | Nếu có, cân nhắc entity |
| Entity hierarchy có ID hợp lệ không? | @Id/@EmbeddedId |
| Mapped superclass có ID/version chung không? | Inherited mapping đúng |
| Có dùng inheritance strategy không? | Chỉ khi entity hierarchy cần |
| Có nhúng một embeddable nhiều lần không? | AttributeOverrides rõ |
| Embeddable có association không? | AssociationOverride cho FK |
| Có nested embeddables không? | Dotted attribute paths |
| Có collection các value objects không? | ElementCollection và CollectionTable |
| Collection cần ổn định thứ tự không? | @OrderColumn hoặc design phù hợp |
| Có composite key không? | EmbeddedId/IdClass + equality |
| Có relationship là một phần ID không? | @MapsId khi thích hợp |
| Access strategy có thống nhất không? | @Id placement/@Access |
| Metamodel có nhận đúng types không? | getEntities/getEmbeddables/getManagedTypes |
| Query dùng entity name hay table name? | JPQL dùng entity name |
| Query embedded fields thế nào? | Path qua owner |
| Mapping có tạo đúng cột không? | SQL logs/schema inspect |
| Các columns nullable/length đúng không? | @Column/overrides/schema constraints |
| Entity con có kế thừa callbacks không? | Theo lifecycle rules |
| Có cần optimistic version không? | @Version ở entity/mapped superclass |
| Có quản lý embedded value như entity không? | Không persist/merge trực tiếp |
| Có proxy/lazy load liên quan association không? | Fetch plan riêng |
| Có test flush/clear không? | Verify persisted state |
| Có second-level cache khi test không? | Tránh nhầm SQL absence |
| Có migration DDL production chưa? | Schema quản lý bằng migrations |
| Có phụ thuộc provider-specific record mapping không? | Xác định portability |
| Có yêu cầu history/snapshot values không? | Domain value semantics |
| Có test concurrent updates không? | Owner version/locking |

---

## 58. Những hiểu lầm cần tránh

### 58.1. “@MappedSuperclass là abstract entity”

Sai. Mapped superclass không là entity type/query root. Abstract class mang `@Entity` vẫn là entity type có thể dùng trong polymorphic query.

### 58.2. “Mọi entity luôn có một bảng SQL riêng”

Sai. Entity inheritance có thể dùng chung bảng hoặc nhiều bảng; `@SecondaryTable` cũng làm một entity trải qua nhiều tables.

### 58.3. “@MappedSuperclass sẽ tạo bảng base”

Sai. Mapping declarations được entity con kế thừa, không tạo entity table riêng cho lớp cha.

### 58.4. “@Embeddable tạo bảng cùng tên Address”

Sai khi `@Embedded` thông thường. Nhưng element collection của embeddable có thể dùng một collection table — điều đó vẫn không tạo entity identity cho mỗi element.

### 58.5. “Có @Column thì class phải là entity”

Không. @Column có thể nằm trong mapped superclass hoặc embeddable và được áp vào storage mapping của owner/entity con.

### 58.6. “Mọi object có ID trong Java đều là JPA entity”

Không. JPA entity identity cần mapping hợp lệ. Embedded ID object chứa các key values nhưng không là entity.

### 58.7. “@EmbeddedId làm ID class thành entity”

Không. ID class là embeddable; entity dùng nó để định danh.

### 58.8. “Một embeddable không bao giờ được chứa association”

Quá mạnh. Embeddable có thể chứa association theo mapping rules; association target vẫn là entity riêng.

### 58.9. “@AttributeOverride dùng đổi mọi column kể cả FK”

Không. Đổi join column của association cần @AssociationOverride phù hợp.

### 58.10. “Đổi @Embedded Address không cần transaction”

Nếu owner managed cần đồng bộ thay đổi xuống DB, transaction và flush/commit rules vẫn áp dụng. Embeddable không có transaction riêng.

### 58.11. “Persist Address trước, sau đó persist Customer”

Address embeddable không được persist riêng. Gán value vào Customer rồi persist owner.

### 58.12. “Dùng CascadeType.ALL để lưu basic embedded columns”

Không cần. Cascade semantics áp dụng entity relationships; embedded basic values được map như state của owner.

### 58.13. “Customer và Supplier cùng extends BaseEntity thì phải chia sẻ ID domain”

Không. Chúng là các entity types khác nhau, identity không chỉ một Long value trên toàn application.

### 58.14. “Java extends đồng nghĩa JPA polymorphic query”

Không. Chỉ có entity hierarchy phù hợp mới cho entity polymorphism/query root; mapped superclass không tạo query root.

### 58.15. “@Entity(name) là tên bảng SQL”

Không. @Entity(name) đặt JPQL entity name; @Table(name) đặt primary table name.

### 58.16. “Query Address bằng FROM Address vì nó có metadata”

Không. Managed type không đồng nghĩa entity root. EmbeddableType có metadata nhưng không là EntityType.

### 58.17. “EntityManagerFactory.getMetamodel().getEntities() trả tất cả managed classes”

Không. Chỉ entity types; getManagedTypes bao gồm mapped superclasses và embeddables được nhận diện.

### 58.18. “@Column trên field luôn được đọc dù JPA chọn property access”

Không bảo đảm. Mapping annotations phải tuân thủ access type/mixed access rules.

### 58.19. “Hai Embedded cùng loại tự đặt cột khác tên portable”

Không nên dựa vào provider implicit naming. Dùng explicit overrides khi cần schema ổn định.

### 58.20. “Một embeddable Java object là immutable theo JPA”

Không. JPA không tự cấm field setters/mutation. Value immutability là quyết định thiết kế; provider support cho immutable classes/records có giới hạn phiên bản.

### 58.21. “Embedded basic attributes luôn có một table không thể khác”

Không. Trong `@ElementCollection` có collection table; bên cạnh đó embeddables có thể chứa associations.

### 58.22. “MappedSuperclass có EntityManager lifecycle riêng”

Không. Callback/mapping của nó được sử dụng theo entity con, không persist superclass instance như một entity.

### 58.23. “Thấy cột updated_at nghĩa @PreUpdate của mapped superclass chạy trên bulk UPDATE”

Không. Bulk JPQL/native updates không kích hoạt per-entity lifecycle callbacks như dirty checking.

### 58.24. “Chỉ nhìn class annotation là đủ để xác minh schema”

Không. Phải xem inherited mappings, overrides, provider naming strategy, SQL dialect và physical schema.

---

## 59. Câu hỏi ôn tập

1. Ba annotations `@Entity`, `@MappedSuperclass` và `@Embeddable` khác nhau ở điểm nào quan trọng nhất?
2. Vì sao một managed type không nhất thiết là entity?
3. JPA persistent identity là gì?
4. Mapped superclass có tạo bảng riêng không?
5. Embeddable dùng `@Embedded` thông thường có tạo bảng riêng không?
6. Khi nào embeddable xuất hiện trong collection table?
7. Lớp abstract có `@Entity` khác `@MappedSuperclass` thế nào?
8. Có thể query polymorphic `FROM Payment` khi Payment là mapped superclass không?
9. `@Inheritance(JOINED)` và mapped superclass giải quyết hai nhu cầu khác nhau nào?
10. Tại sao một entity có thể dùng nhiều SQL tables?
11. ID của Customer có thể khai báo trong mapped superclass không?
12. `@Version` ở mapped superclass có áp dụng cho entity con không?
13. Vì sao không persist mapped superclass instance trực tiếp?
14. Vì sao không `em.find(Address.class,id)` với embeddable?
15. Dấu hiệu nào cho biết Address nên là entity thay vì embeddable?
16. Tại sao Address value có thể cần equals/hashCode?
17. Hai Java instances Address bằng giá trị có nghĩa cùng entity không?
18. Vì sao mutable embeddable shared instance có rủi ro?
19. Cách dùng `@AttributeOverrides` cho billing/shipping là gì?
20. Tham số `name` của `@AttributeOverride` là tên Java field hay SQL column?
21. Khi nào dùng `@AssociationOverride`?
22. @ManyToOne trong embeddable có biến embeddable thành entity không?
23. Embeddable lồng nhau có override attribute path thế nào?
24. `@ElementCollection` khác `@OneToMany` với entity như thế nào?
25. Collection table có bảo đảm mỗi Address có entity ID riêng không?
26. `@EmbeddedId` đại diện cho gì?
27. Tại sao EmbeddedId class cần Serializable/equals/hashCode?
28. EntityManager.find trên ExchangeRate nhận key object kiểu nào?
29. `@IdClass` và `@EmbeddedId` khác nhau về mapping shape thế nào?
30. `@MapsId` giúp giải quyết mapping nào?
31. JPA field access/property access được xác định ra sao?
32. Vì sao vị trí `@Id` ảnh hưởng thuộc tính persistent?
33. Lúc nào nên dùng `@Access`?
34. `@Transient` dùng vào mục đích gì?
35. Tại sao metadata không đồng nghĩa physical SQL schema?
36. `EntityType`/`MappedSuperclassType`/`EmbeddableType` khác nhau ở đâu?
37. `getEntities()` và `getManagedTypes()` trả những nhóm nào?
38. `getDeclaredAttributes()` và `getAttributes()` khác nhau ra sao?
39. Có thể dùng `mm.entity(AuditedRecord.class)` không?
40. Có thể dùng `mm.embeddable(Address.class)` khi Address được nhận diện không?
41. `EntityType.getName()` tương ứng với annotation nào?
42. Khi dùng `@Entity(name="Client")` và `@Table(name="customers")`, JPQL FROM dùng tên nào?
43. Làm sao viết JPQL filter theo `billingAddress.city`?
44. Criteria Root có thể là Address khi Address chỉ @Embeddable không?
45. Typed static metamodel giúp tránh lỗi gì?
46. Tại sao cần test persist/flush/clear/find?
47. Khi dùng L2 cache, EntityManager mới có chắc phát SQL SELECT không?
48. Vì sao @Embedded không cần CascadeType.PERSIST?
49. Concurrency của embedded Address được quản lý qua entity nào?
50. Đổi Address trên detached Customer có tự lưu xuống DB không?
51. Khi nào mapped superclass callbacks có thể chạy?
52. Vì sao bulk JPQL UPDATE không tương đương per-entity dirty checking callbacks?
53. Tại sao schema migration cần được kiểm tra khi đổi AttributeOverrides?
54. Trường hợp nào nên chọn composition thay inheritance?
55. Vì sao lưu Address snapshot trong Order thường khác tham chiếu Address entity của Customer?
56. Những lỗi nào dễ xuất hiện khi mapping same embeddable hai lần?
57. SQL physical columns phụ thuộc yếu tố gì ngoài annotations?
58. Khi nào parent abstract entity sẽ làm thay đổi mô hình queries?
59. Metadata inspector giúp phát hiện loại sai sót nào?
60. Tóm tắt một quy tắc chọn Entity/MappedSuperclass/Embeddable cho dự án của bạn.

---

## 60. Bảng ghi nhớ cuối bài

| Cần làm | Cách JPA biểu diễn | Lưu ý |
|---|---|---|
| Object có ID và lifecycle riêng | `@Entity` | `@Id`/`@EmbeddedId` hợp lệ |
| Tái sử dụng common mapping | `@MappedSuperclass` | Không có JPQL root/bảng riêng |
| Đại diện một nhóm giá trị | `@Embeddable` | Không có EntityManager lifecycle độc lập |
| Nhúng Address vào Customer | `@Embedded` | Cột thường ở bảng owner |
| Nhúng Address hai lần | `@AttributeOverrides` | Tránh duplicate columns |
| Đổi FK của embedded association | `@AssociationOverride` | Khác override basic columns |
| Nhúng embeddable lồng nhau | `@Embedded` trong embeddable | Dotted property paths khi override |
| Danh sách value objects | `@ElementCollection` | Collection table có thể xuất hiện |
| Composite key là value object | `@EmbeddedId` | Key class equals/hashCode |
| FK trong composite ID | `@MapsId` | Identity và relationship linked |
| Polymorphic query theo base type | Abstract `@Entity` | Entity inheritance strategy |
| Query entity con | JPQL `FROM Customer c` | Không `FROM AuditedRecord` |
| Filter theo embedded city | `c.billingAddress.city` | Path qua owner |
| Tiếp cận metadata | `emf.getMetamodel()` | ManagedType != EntityType |
| Danh sách entities | `getEntities()` | Không gồm mapped superclass/embeddable |
| Danh sách managed classes | `getManagedTypes()` | Có cả ba nhóm |
| Chọn field/property mapping | @Id placement / `@Access` | Tuân thủ hierarchy rules |
| Kiểm tra physical schema | SQL logs + DB inspection | Khác metamodel |
| Test persist mapping | Persist / flush / clear / find | Chú ý L2 cache |
| Quản lý cập nhật embedded state | Mutate owner rồi flush/commit | Không persist Address riêng |
| Concurrency trên embedded values | Owner `@Version` | Value object không có version độc lập |
| Dùng record/immutable embeddable | Kiểm tra provider/version | Không mặc nhiên portable |

### Sơ đồ kết luận

```text
                    JAVA CLASS CẦN PERSIST
                              |
                              v
                  Có identity/lifecycle riêng?
                         /          \
                       CÓ          KHÔNG
                        |             |
                        v             v
                    @Entity       Chỉ là mapped fields
                        |         dùng chung cho các entity?
                        |             /          \
                        |           CÓ           KHÔNG
                        |           |              |
                        |           v              v
                        |    @MappedSuperclass   Là value component?
                        |                          /        \
                        |                        CÓ        KHÔNG
                        |                        |          |
                        |                        v          v
                        |                   @Embeddable  Java helper/
                        |                                nonpersistent
                        v
                @Id / @EmbeddedId
                        |
                        v
             Identity map + JPA lifecycle
                        |
                        v
                Entity table mapping

@MappedSuperclass:
  attributes inherited by entity metadata and tables

@Embeddable:
  fields embedded into owner mapping or collection table

Metamodel:
  ENTITY / MAPPED_SUPERCLASS / EMBEDDABLE
```

**Nguyên tắc cuối bài:** `@Entity`, `@MappedSuperclass` và `@Embeddable` có thể cùng đóng góp persistent attributes vào mô hình Java, nhưng **chúng không có cùng identity, query semantics hoặc database mapping responsibility**. Entity là đối tượng JPA quản lý riêng; mapped superclass chia sẻ mapping cho entity subclasses mà không tạo entity root; embeddable biểu diễn value component được lưu qua owner. Khi thiết kế, hãy xác định **domain identity và lifecycle** trước, sau đó mới chọn annotations, overrides và inheritance strategy. Cuối cùng, xác minh bằng **JPA metamodel**, JPQL/Criteria, SQL schema và test persist/flush/reload — không chỉ dựa vào tên lớp hay cảm giác “một class tương ứng một bảng”.

