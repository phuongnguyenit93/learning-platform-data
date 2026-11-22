# Tra cứu thuộc tính cơ bản, thuộc tính đơn và tập hợp trong JPA Metamodel

Trong Java Persistence API (JPA), một entity không chỉ là lớp Java được gắn `@Entity`. Đối với persistence provider, entity còn có một **mô hình metadata**: thuộc tính nào được persistence quản lý, kiểu Java là gì, thuộc tính đó là giá trị cơ bản, embedded object, quan hệ một-một, quan hệ nhiều-một hay collection, và những thông tin cấu trúc có thể dùng để xây Criteria Query.

Jakarta Persistence cung cấp **Metamodel API** trong package `jakarta.persistence.metamodel` để ứng dụng tra cứu mô hình này một cách chuẩn hóa. Ví dụ, từ `PurchaseOrder.class`, ta có thể xác định:

- `id` là thuộc tính đơn, đồng thời là khóa chính và có persistent kind `BASIC`.
- `version` là thuộc tính đơn, versioned field.
- `customer` là thuộc tính đơn, nhưng là quan hệ `MANY_TO_ONE`, **không phải** thuộc tính basic.
- `shippingAddress` là thuộc tính đơn, mapping `EMBEDDED`.
- `lines` là `List<OrderLine>` và được mô tả bởi `ListAttribute`.
- `labels` là `Set<String>` của `@ElementCollection`, được mô tả bởi `SetAttribute`.
- `notes` là `Map<String,String>` của `@ElementCollection`, được mô tả bởi `MapAttribute`.

Sự phân biệt này quan trọng khi viết trình tạo truy vấn động, generic repository, công cụ kiểm tra mappings, bộ dựng biểu mẫu, API tìm kiếm hoặc công cụ thống kê các entities mà không phải tự quét annotations bằng reflection.

Bài học tập trung vào **tra cứu thuộc tính cơ bản, thuộc tính đơn và tập hợp** trong ngữ cảnh chương *Siêu dữ liệu và lược đồ*. Nội dung bao gồm cấu trúc runtime metamodel, các interface `Attribute`, `SingularAttribute`, `PluralAttribute`, các lớp con `CollectionAttribute`, `SetAttribute`, `ListAttribute`, `MapAttribute`, các cách gọi `getAttribute`/`getSingularAttribute`/`getPluralAttribute`/`getList`/`getSet`/`getMap`, ví dụ Criteria API, static metamodel và giới hạn khi dùng metadata để suy ra database schema.

---

## 1. Metamodel là gì, và tại sao cần đến nó?

Giả sử có class:

```java
@Entity
public class Customer {

    @Id
    private Long id;

    private String displayName;

    @OneToMany(mappedBy = "customer")
    private Set<PurchaseOrder> orders;
}
```

Ta có thể dùng Java reflection để nhìn thấy ba fields. Nhưng reflection thuần không tự cho biết `orders` được provider ánh xạ như một `ONE_TO_MANY`, `displayName` là basic persistent field, hoặc Java member nào thực sự được chọn theo JPA field/property access strategy.

JPA Metamodel mô tả **mô hình persistent đã được provider nhận diện** sau khi xử lý annotations, XML mappings và những quy tắc ánh xạ liên quan.

```java
Metamodel metamodel = em.getMetamodel();

EntityType<Customer> customerType =
    metamodel.entity(Customer.class);
```

Từ `customerType`, ứng dụng có thể liệt kê hoặc tra cứu các thuộc tính đã được provider quản lý.

### 1.1. Runtime metamodel khác Java reflection

- **Reflection** nhìn vào lớp Java: fields, methods, generic declarations và annotations.
- **JPA Metamodel** nhìn vào các thuộc tính persistent thực tế theo model của JPA provider.
- **JDBC DatabaseMetaData** nhìn vào database đang kết nối: tables, columns, keys, indexes và cấu trúc vật lý.

Ba nguồn này trả lời những câu hỏi khác nhau và không thay thế nhau.

### 1.2. Metamodel không đồng nghĩa database schema

`Attribute.getName()` cung cấp tên **persistent attribute** trong Java model, không phải tên cột SQL sau khi áp dụng `@Column`, naming strategy, XML override hoặc inheritance mapping.

Ví dụ:

```java
@Column(name = "display_name")
private String displayName;
```

Metamodel attribute name là `"displayName"`, còn physical column có thể là `display_name`. Không được giả định `getName()` chính là tên cột SQL.

### 1.3. Metamodel không tự tạo hay sửa schema

Metamodel phục vụ introspection và type-safe query construction. Nó không phải công cụ migration thay cho Flyway, Liquibase, database DDL hay các schema management features của provider.

---

## 2. Các interface quan trọng trong Metamodel API

Sơ đồ khái quát:

```text
jakarta.persistence.metamodel.Metamodel
    |
    +-- EntityType<X>
    +-- EmbeddableType<X>
    +-- MappedSuperclassType<X>
    |
    +-- Các ManagedType<X> được tra cứu
            |
            +-- Attribute<X,Y>
                 |
                 +-- SingularAttribute<X,T>
                 |
                 +-- PluralAttribute<X,C,E>
                       |
                       +-- CollectionAttribute<X,E>
                       +-- SetAttribute<X,E>
                       +-- ListAttribute<X,E>
                       +-- MapAttribute<X,K,V>
```

Sơ đồ thể hiện quan hệ khái niệm; trong API, `EntityType`, `EmbeddableType` và `MappedSuperclassType` kế thừa nhánh `ManagedType`, còn các attribute interfaces có generic parameters riêng.

### 2.1. Metamodel

Điểm vào:

```java
Metamodel mm = em.getMetamodel();
```

Hoặc:

```java
Metamodel mm = emf.getMetamodel();
```

Các phương thức hay dùng:

```java
mm.getEntities();
mm.getEmbeddables();
mm.getManagedTypes();

mm.entity(PurchaseOrder.class);
mm.embeddable(Address.class);
mm.managedType(PurchaseOrder.class);
```

`entity()` dùng khi lớp đó được ánh xạ là entity. `embeddable()` dùng cho `@Embeddable`. `managedType()` bao quát các JPA managed types được hỗ trợ.

### 2.2. Type<X>

`Type<X>` biểu diễn thông tin kiểu theo JPA:

```java
Class<?> javaType = type.getJavaType();

Type.PersistenceType kind =
    type.getPersistenceType();
```

`PersistenceType` có các nhóm như `BASIC`, `ENTITY`, `EMBEDDABLE`, `MAPPED_SUPERCLASS`.

Đây là **kind của một JPA type**, khác với `Attribute.PersistentAttributeType`, vốn mô tả cách **thuộc tính** được ánh xạ.

### 2.3. ManagedType<X>

`ManagedType` cung cấp các phương thức liệt kê và lấy persistent attributes, bao gồm thuộc tính kế thừa hoặc chỉ thuộc tính khai báo trực tiếp.

### 2.4. Attribute<X,Y>

`Attribute` mô tả một persistent attribute của managed type `X`, với Java value type `Y`.

### 2.5. SingularAttribute và PluralAttribute

- `SingularAttribute<X,T>`: thuộc tính **đơn trị**, có value type `T`.
- `PluralAttribute<X,C,E>`: thuộc tính **tập hợp**, với Java container type `C` và element type `E`.

Không có nguyên tắc “singular = basic”. Một quan hệ `@ManyToOne` vẫn là `SingularAttribute`, còn `@ElementCollection` có thể chứa **basic elements** nhưng là `PluralAttribute`.

---

## 3. Mô hình entity mẫu để thực hành

Để minh họa các kiểu metadata, dùng một mô hình đơn hàng đơn giản với khách hàng, dòng đơn hàng, địa chỉ giao hàng và collection values.

### 3.1. Mapped superclass: Auditable

```java
package com.example.shop.domain;

import jakarta.persistence.*;
import java.time.Instant;

@MappedSuperclass
public abstract class Auditable {

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "updated_at")
    private Instant updatedAt;

    public Instant getCreatedAt() {
        return createdAt;
    }
}
```

`createdAt` và `updatedAt` là các persistent attributes kế thừa bởi entity con. Điều này giúp phân biệt `getAttributes()` với `getDeclaredAttributes()` ở phần sau.

### 3.2. Embeddable: Address

```java
package com.example.shop.domain;

import jakarta.persistence.*;

@Embeddable
public class Address {

    @Column(name = "street")
    private String street;

    @Column(name = "city")
    private String city;

    @Column(name = "postal_code")
    private String postalCode;

    protected Address() {}

    public String getCity() { return city; }
}
```

Khi một entity dùng `@Embedded Address`, thuộc tính Address là **singular**, nhưng persistent attribute type là `EMBEDDED`, không phải `BASIC`.

### 3.3. Customer

```java
package com.example.shop.domain;

import jakarta.persistence.*;
import java.util.HashSet;
import java.util.Set;

@Entity
@Table(name = "customer")
public class Customer {

    @Id
    private Long id;

    @Column(nullable = false)
    private String displayName;

    @OneToMany(mappedBy = "customer")
    private Set<PurchaseOrder> orders = new HashSet<>();

    protected Customer() {}

    public Long getId() { return id; }
}
```

`displayName` là basic singular. `orders` là plural one-to-many association.

### 3.4. PurchaseOrder

```java
package com.example.shop.domain;

import jakarta.persistence.*;
import java.util.*;

@Entity
@Table(name = "purchase_order")
public class PurchaseOrder extends Auditable {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private long version;

    @Column(name = "order_number", nullable = false)
    private String orderNumber;

    @Embedded
    private Address shippingAddress;

    @ManyToOne(
        fetch = FetchType.LAZY,
        optional = false
    )
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines = new ArrayList<>();

    @ElementCollection
    @CollectionTable(
        name = "order_label",
        joinColumns = @JoinColumn(name = "order_id")
    )
    @Column(name = "label")
    private Set<String> labels = new HashSet<>();

    @ElementCollection
    @CollectionTable(
        name = "order_note",
        joinColumns = @JoinColumn(name = "order_id")
    )
    @MapKeyColumn(name = "note_key")
    @Column(name = "note_value")
    private Map<String, String> notes = new HashMap<>();

    @Transient
    private String viewOnlySummary;

    protected PurchaseOrder() {}

    public Long getId() { return id; }
}
```

### 3.5. OrderLine

```java
package com.example.shop.domain;

import jakarta.persistence.*;

@Entity
@Table(name = "order_line")
public class OrderLine {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "order_id")
    private PurchaseOrder order;

    @Column(nullable = false)
    private int quantity;

    protected OrderLine() {}
}
```

Mô hình này cung cấp đủ các ví dụ về basic attribute, embedded, to-one, to-many, Set, List, Map và inherited attributes.

---

## 4. Bảng kỳ vọng metadata cho PurchaseOrder

| Tên thuộc tính | Java type | Singular hay Plural? | Persistent attribute type |
|---|---|---|---|
| `id` | `Long` | Singular | `BASIC` |
| `version` | `long` | Singular | `BASIC` |
| `orderNumber` | `String` | Singular | `BASIC` |
| `shippingAddress` | `Address` | Singular | `EMBEDDED` |
| `customer` | `Customer` | Singular | `MANY_TO_ONE` |
| `lines` | `List<OrderLine>` | Plural/List | `ONE_TO_MANY` |
| `labels` | `Set<String>` | Plural/Set | `ELEMENT_COLLECTION` |
| `notes` | `Map<String,String>` | Plural/Map | `ELEMENT_COLLECTION` |
| `createdAt` | `Instant` | Singular, inherited | `BASIC` |
| `updatedAt` | `Instant` | Singular, inherited | `BASIC` |
| `viewOnlySummary` | `String` | Không thuộc persistent metamodel | `@Transient` |

Một điểm cần nhấn mạnh: `@Transient` không phải `BASIC` hay `SingularAttribute` persistent chỉ vì nó là một String field. Metamodel liệt kê **persistent attributes**, không phải mọi Java fields.

---

## 5. Lấy Metamodel từ EntityManager và EntityManagerFactory

Trong một service:

```java
@PersistenceContext
private EntityManager em;

public void inspect() {
    Metamodel metamodel = em.getMetamodel();

    EntityType<PurchaseOrder> orderType =
        metamodel.entity(PurchaseOrder.class);
}
```

Nếu ứng dụng có `EntityManagerFactory`:

```java
EntityManagerFactory emf = ...;

Metamodel metamodel = emf.getMetamodel();
```

### 5.1. Khác nhau về vòng đời

`EntityManager` gắn với persistence context và không thread-safe. `EntityManagerFactory` dùng để tạo EntityManager và cung cấp mô hình metadata cho persistence unit; việc introspection có thể tổ chức tại startup thay vì mở transaction chỉ để xem tên attributes.

### 5.2. Không cần query một row trong DB để tìm metadata

Tra cứu metamodel không có nghĩa phải thực hiện `SELECT` trên bảng PurchaseOrder. Provider đã nhận biết mappings trong quá trình bootstrap.

### 5.3. Provider có thể xây metadata theo cách riêng

Một số provider tạo metadata khi EntityManagerFactory khởi tạo; có lazy initialization hoặc generated-model integration riêng. Nhưng code dùng JPA metamodel API không nên phụ thuộc vendor-specific internal descriptor classes.

### 5.4. Metamodel theo persistence unit

Nếu ứng dụng có nhiều persistence units, mỗi `EntityManagerFactory` có model của riêng nó. Không mặc định entity cùng Java class trong hai persistence units có mappings/cache/attributes hoàn toàn giống nhau.

---

## 6. Liệt kê tất cả managed types

```java
Metamodel mm = emf.getMetamodel();

for (ManagedType<?> type : mm.getManagedTypes()) {
    System.out.println(
        type.getJavaType().getName()
    );
}
```

Bạn có thể giới hạn theo nhóm:

```java
for (EntityType<?> entity : mm.getEntities()) {
    System.out.println(
        entity.getName() + " -> " +
        entity.getJavaType().getName()
    );
}
```

Với embeddable:

```java
for (EmbeddableType<?> type : mm.getEmbeddables()) {
    System.out.println(
        type.getJavaType().getSimpleName()
    );
}
```

### 6.1. Entity name khác class name

`EntityType.getName()` trả tên entity trong JPA model, có thể là tên khai báo qua `@Entity(name = "...")`, không nhất thiết bằng Java simple class name hoặc SQL table name.

### 6.2. Mapped superclass cũng là managed type

`Auditable` không có bảng độc lập như một entity trong mô hình minh họa, nhưng `@MappedSuperclass` có persistent attributes kế thừa. Nó có thể được truy xuất qua `managedType()` và nhận `MappedSuperclassType` trong JPA metamodel.

### 6.3. Đừng duyệt thứ tự metadata như thứ tự nghiệp vụ

`getEntities()` và `getAttributes()` cung cấp các tập hợp, không nên mặc định iteration order phản ánh thứ tự cột DB hoặc thứ tự fields trong source code.

---

## 7. Tra cứu Attribute tổng quát bằng tên

```java
EntityType<PurchaseOrder> orderType =
    emf.getMetamodel().entity(PurchaseOrder.class);

Attribute<? super PurchaseOrder, ?> attribute =
    orderType.getAttribute("orderNumber");
```

Interface `Attribute<X,Y>` cung cấp các thông tin quan trọng:

```java
String name = attribute.getName();

Class<?> javaType = attribute.getJavaType();

Attribute.PersistentAttributeType kind =
    attribute.getPersistentAttributeType();

boolean association = attribute.isAssociation();

boolean collection = attribute.isCollection();

ManagedType<?> declaringType =
    attribute.getDeclaringType();

java.lang.reflect.Member member =
    attribute.getJavaMember();
```

### 7.1. Attribute.getName()

Đây là **tên thuộc tính persistent** theo JPA model, ví dụ `"orderNumber"`, không phải SQL column `"order_number"`.

### 7.2. getJavaType()

Là Java type của value/attribute. Với `String orderNumber`, kết quả là `String.class`. Với `List<OrderLine> lines`, kết quả là raw Java container class/interface như `List.class`, không phải `OrderLine.class`.

### 7.3. getPersistentAttributeType()

Cho biết mapping kind: `BASIC`, `EMBEDDED`, `MANY_TO_ONE`, `ONE_TO_ONE`, `ONE_TO_MANY`, `MANY_TO_MANY`, `ELEMENT_COLLECTION`.

### 7.4. isAssociation()

Giúp phân biệt association với entity khác. Một `@ManyToOne` hoặc `@OneToMany` là association. `@ElementCollection` thường không phải association tới entity dù nó là collection mapping.

### 7.5. isCollection()

Giúp nhận biết plural-valued persistent attribute; nó không đơn giản tương đương “Java type có chữ Collection trong tên” nếu mapping thực tế dùng các basic/vendor-specific types.

### 7.6. getJavaMember()

Trả `Member` đại diện cho field hoặc property accessor được dùng theo JPA access strategy. Đây là điểm kết nối giữa metadata và reflection; không phải API để lấy trực tiếp tên cột cuối cùng trong DB.

---

## 8. PersistentAttributeType: Thuộc tính được ánh xạ theo kiểu gì?

Enum:

```java
Attribute.PersistentAttributeType
```

có các giá trị:

| Giá trị | Ý nghĩa thường gặp | Ví dụ |
|---|---|---|
| `BASIC` | Persistent basic value | `String`, `Long`, `BigDecimal`, enum |
| `EMBEDDED` | Embedded value object | `@Embedded Address` |
| `ONE_TO_ONE` | Quan hệ một-một | `@OneToOne Profile` |
| `MANY_TO_ONE` | Quan hệ nhiều-một | `@ManyToOne Customer` |
| `ONE_TO_MANY` | Quan hệ một-nhiều | `@OneToMany List<OrderLine>` |
| `MANY_TO_MANY` | Quan hệ nhiều-nhiều | `@ManyToMany Set<Tag>` |
| `ELEMENT_COLLECTION` | Collection của basic/embeddable values | `@ElementCollection Set<String>` |

### 8.1. Không nhầm với Type.PersistenceType

Hai phương thức khác nhau:

```java
attribute.getPersistentAttributeType();

singularAttribute.getType().getPersistenceType();
```

Phương thức đầu diễn đạt **mapping kind của attribute**. Phương thức sau diễn đạt **JPA kind của type được tham chiếu**.

Ví dụ:

```text
PurchaseOrder.customer:
  PersistentAttributeType = MANY_TO_ONE
  Attribute value type    = Customer
  Type.PersistenceType    = ENTITY

PurchaseOrder.shippingAddress:
  PersistentAttributeType = EMBEDDED
  Attribute value type    = Address
  Type.PersistenceType    = EMBEDDABLE

PurchaseOrder.orderNumber:
  PersistentAttributeType = BASIC
  Attribute value type    = String
  Type.PersistenceType    = BASIC
```

### 8.2. Singular có thể là basic, embedded hoặc association

`@ManyToOne Customer` chỉ chứa một reference nên là `SingularAttribute`, nhưng không phải basic scalar.

### 8.3. Plural có thể chứa basic elements

`Set<String> labels` ánh xạ bằng `@ElementCollection`. `labels` là plural, trong khi từng phần tử `String` có JPA type BASIC.

---

## 9. Tra cứu SingularAttribute theo tên

```java
EntityType<PurchaseOrder> orderType =
    emf.getMetamodel().entity(PurchaseOrder.class);

SingularAttribute<? super PurchaseOrder, String>
    orderNumber = orderType.getSingularAttribute(
        "orderNumber",
        String.class
    );
```

Có thể bỏ tham số Java type khi chỉ cần introspection:

```java
SingularAttribute<? super PurchaseOrder, ?>
    attr = orderType.getSingularAttribute(
        "orderNumber"
    );
```

Typed overload có lợi khi muốn xác nhận metadata thật sự có type đã dự kiến.

### 9.1. SingularAttribute<X,T>

`X` là entity/managed owner type. `T` là Java value type.

Các method hữu ích:

```java
Class<?> valueClass = attr.getJavaType();

Type<?> jpaType = attr.getType();

boolean id = attr.isId();

boolean version = attr.isVersion();

boolean optional = attr.isOptional();
```

### 9.2. isId()

Cho biết thuộc tính có tham gia vai trò identifier theo JPA mapping. Đừng suy luận field tên `id` chắc chắn là identifier nếu mapping sử dụng tên khác hoặc composite key.

### 9.3. isVersion()

Cho biết thuộc tính là version attribute được dùng bởi optimistic locking. Không tìm kiếm chỉ bằng field name `"version"`; dùng metadata.

### 9.4. isOptional()

Cho biết tính optionality của singular attribute theo metadata. Không coi đây là một bản sao đầy đủ của DB `NOT NULL` constraint: schema có thể có additional constraints, XML overrides hoặc validation rules khác.

### 9.5. getType()

Trả `Type<T>` tương ứng giá trị singular. Với `Customer` là ENTITY, với `Address` là EMBEDDABLE, với `String` là BASIC.

---

## 10. Thế nào là thuộc tính cơ bản (basic attribute)?

“Basic” là **loại ánh xạ persistent attribute**. Các kiểu phổ biến:

- Primitive và wrapper types: `int`, `long`, `boolean`, `Integer`, `Long`.
- `String`, `BigDecimal`, `BigInteger`.
- Enum khi ánh xạ theo `@Enumerated`.
- Các loại ngày/giờ được JPA hỗ trợ.
- `byte[]`, dữ liệu nhị phân, `@Lob` theo mapping.
- Một số custom value types được ánh xạ qua converter hoặc provider extension.

Ví dụ:

```java
@Column(name = "order_number")
private String orderNumber;

@Version
private long version;

@Enumerated(EnumType.STRING)
private OrderStatus status;

@Lob
private byte[] documentBytes;
```

Thông thường chúng đều là singular basic attributes.

### 10.1. Basic không phải một interface attribute độc lập

Bạn không dùng `BasicAttribute<X,T>` như một interface tương đương `SingularAttribute`. Thay vào đó, tra cứu `SingularAttribute` rồi xét:

```java
Attribute.PersistentAttributeType kind =
    attr.getPersistentAttributeType();

boolean basic =
    kind == Attribute.PersistentAttributeType.BASIC;
```

Ngoài ra `attr.getType()` có thể là `BasicType<T>` khi type được mô tả là basic theo API/provider.

### 10.2. @Basic không bắt buộc phải được viết tường minh

Một số fields mặc định được ánh xạ basic khi entity dùng field access/property access và không có annotation association/embedded khác. Metamodel dựa vào **mapping cuối cùng**, không chỉ việc source có hay không có `@Basic`.

### 10.3. @Enumerated và @Convert

```java
@Enumerated(EnumType.STRING)
private OrderStatus status;

@Convert(converter = MoneyConverter.class)
private Money amount;
```

Một basic-mapped value vẫn có thể là `SingularAttribute` với Java type `OrderStatus` hoặc `Money`; JPA metamodel không mặc nhiên chuyển `getJavaType()` thành JDBC column type như `VARCHAR` hay `DECIMAL`.

### 10.4. Basic array không tự là PluralAttribute

Một `byte[]` được ánh xạ basic/LOB không phải JPA plural association chỉ vì cú pháp Java có `[]`. Phải phân biệt **Java container shape** với **persistence mapping classification**.

---

## 11. Lọc mọi basic attributes từ một ManagedType

Có thể dùng `getAttributes()` rồi lọc bằng mapping kind.

```java
public static List<String> basicAttributeNames(
        ManagedType<?> type) {

    List<String> names = new ArrayList<>();

    for (Attribute<?, ?> attr : type.getAttributes()) {
        if (attr.getPersistentAttributeType()
                == Attribute.PersistentAttributeType.BASIC) {
            names.add(attr.getName());
        }
    }

    names.sort(String::compareTo);
    return names;
}
```

Với `PurchaseOrder`, kết quả có thể chứa `id`, `version`, `orderNumber`, `createdAt`, `updatedAt`; nhưng không chứa `customer`, `shippingAddress`, `lines`, `labels`, `notes`.

### 11.1. Không dùng isCollection() == false để suy ra BASIC

`customer` và `shippingAddress` đều không phải collections, nhưng một cái là `MANY_TO_ONE`, một cái là `EMBEDDED`.

Sai:

```java
if (!attr.isCollection()) {
    // Kết luận BASIC là sai!
}
```

Đúng khi cần phân loại basic:

```java
if (attr.getPersistentAttributeType()
        == Attribute.PersistentAttributeType.BASIC) {
    // Basic mapping.
}
```

### 11.2. Identifier cũng có thể là BASIC

Một `Long id` có `@Id` là basic attribute đồng thời đóng vai trò identifier. **Vai trò khóa chính** và **kiểu mapping attribute** là hai chiều metadata khác nhau.

---

## 12. SingularAttribute không phải lúc nào cũng basic

Xét ba thuộc tính:

```java
private String orderNumber;

@Embedded
private Address shippingAddress;

@ManyToOne
private Customer customer;
```

Cả ba đều là **singular**. Nhưng:

| Thuộc tính | Persistent kind | Type kind |
|---|---|---|
| `orderNumber` | `BASIC` | BASIC |
| `shippingAddress` | `EMBEDDED` | EMBEDDABLE |
| `customer` | `MANY_TO_ONE` | ENTITY |

Tra cứu:

```java
EntityType<PurchaseOrder> order =
    mm.entity(PurchaseOrder.class);

SingularAttribute<? super PurchaseOrder, String>
    number = order.getSingularAttribute(
        "orderNumber", String.class
    );

SingularAttribute<? super PurchaseOrder, Address>
    address = order.getSingularAttribute(
        "shippingAddress", Address.class
    );

SingularAttribute<? super PurchaseOrder, Customer>
    customer = order.getSingularAttribute(
        "customer", Customer.class
    );
```

### 12.1. Tại sao phân biệt này quan trọng cho query builder?

Một generic filter builder có thể cho phép `equal` trên basic fields, nhưng cần join với Customer hoặc navigate nested Address đối với hai kiểu kia. Nếu coi tất cả singular fields là basic, có thể sinh query sai hoặc truy cập dữ liệu không hợp lệ.

### 12.2. SingularAttribute là thông tin về cardinality

Nó diễn đạt attribute có **một giá trị** theo Java model, kể cả khi giá trị đó là reference đến entity khác hoặc embedded object.

---

## 13. Tra cứu embedded attributes

`PurchaseOrder.shippingAddress` được tra cứu như singular attribute:

```java
SingularAttribute<? super PurchaseOrder, Address>
    shipping = orderType.getSingularAttribute(
        "shippingAddress",
        Address.class
    );
```

Đồng thời có thể lấy metadata riêng của embeddable:

```java
EmbeddableType<Address> addressType =
    mm.embeddable(Address.class);

SingularAttribute<? super Address, String>
    city = addressType.getSingularAttribute(
        "city", String.class
    );
```

### 13.1. Embedded không tương đương một bảng riêng

`@Embedded` thường đóng góp columns vào bảng của entity owner hoặc cấu trúc mapping tương ứng, nhưng metadata JPA trả `EMBEDDED` và `EmbeddableType`, không cho ta một “bảng Address” riêng tự động.

### 13.2. AttributeOverride

Nếu PurchaseOrder có `@AttributeOverride(name="city", column=@Column(name="shipping_city"))`, JPA metamodel vẫn mô tả persistent attribute name là `city`. Tên cột vật lý là một concern khác.

### 13.3. Criteria path qua embeddable

```java
Path<String> cityPath = root
    .get(PurchaseOrder_.shippingAddress)
    .get(Address_.city);
```

Các static metamodel classes như `PurchaseOrder_` và `Address_` cần được sinh bởi annotation processor hoặc tooling phù hợp.

---

## 14. Tra cứu quan hệ đơn: @ManyToOne và @OneToOne

Một quan hệ to-one là `SingularAttribute`.

```java
SingularAttribute<? super PurchaseOrder, Customer>
    customer = orderType.getSingularAttribute(
        "customer", Customer.class
    );
```

Metadata:

```java
boolean association = customer.isAssociation();

Attribute.PersistentAttributeType kind =
    customer.getPersistentAttributeType();

Type<Customer> valueType = customer.getType();
```

Kỳ vọng cho mô hình mẫu:

```text
isAssociation()                 = true
getPersistentAttributeType()   = MANY_TO_ONE
getType().getPersistenceType() = ENTITY
```

### 14.1. @OneToOne cũng là singular

Ví dụ `Customer.profile` với `@OneToOne` cũng sẽ là `SingularAttribute<Customer, Profile>`, nhưng `PersistentAttributeType.ONE_TO_ONE`.

### 14.2. Không đánh đồng isOptional với FK constraint duy nhất

`isOptional()` cho biết optionality theo model; việc FK có `NOT NULL`, `UNIQUE`, cascade hay database constraint còn phụ thuộc mapping/DDL. Metamodel không cung cấp toàn bộ constraint graph.

### 14.3. To-one association không nhất thiết eager

`@ManyToOne(fetch = FetchType.LAZY)` vẫn là singular association. Metadata cơ bản không thay việc đánh giá fetch plan và provider lazy-loading support.

---

## 15. PluralAttribute<X,C,E> là gì?

`PluralAttribute` biểu diễn một persistent attribute chứa nhiều phần tử hoặc một keyed collection.

```text
PluralAttribute<X, C, E>

X = entity/managed owner type
C = Java container type
E = element/value type
```

Ví dụ:

```java
List<OrderLine> lines;

Set<String> labels;

Map<String, String> notes;
```

Các subtype:

```text
PluralAttribute
    |
    +-- CollectionAttribute
    +-- SetAttribute
    +-- ListAttribute
    +-- MapAttribute
```

Thông tin chung:

```java
PluralAttribute<?, ?, ?> attr = ...;

PluralAttribute.CollectionType collectionKind =
    attr.getCollectionType();

Type<?> elementType =
    attr.getElementType();

Class<?> containerJavaType =
    attr.getJavaType();
```

### 15.1. CollectionType

`PluralAttribute.CollectionType` có các giá trị:

- `COLLECTION`
- `SET`
- `LIST`
- `MAP`

Đây là kind của **collection container**, khác với `PersistentAttributeType.ONE_TO_MANY` hoặc `ELEMENT_COLLECTION`.

### 15.2. Hai chiều metadata độc lập

Ví dụ `labels`:

```text
PersistentAttributeType = ELEMENT_COLLECTION
CollectionType          = SET
ElementType             = BASIC (String)
```

Ví dụ `lines`:

```text
PersistentAttributeType = ONE_TO_MANY
CollectionType          = LIST
ElementType             = ENTITY (OrderLine)
```

---

## 16. getPluralAttribute: Tra cứu chung một thuộc tính tập hợp

```java
EntityType<PurchaseOrder> orderType =
    mm.entity(PurchaseOrder.class);

PluralAttribute<? super PurchaseOrder, ?, ?>
    attr = orderType.getPluralAttribute("lines");
```

Kiểm tra:

```java
System.out.println(attr.getName());

System.out.println(
    attr.getCollectionType()
);

System.out.println(
    attr.getElementType().getJavaType()
);
```

Khi không biết collection là List, Set hay Map, `getPluralAttribute(name)` là điểm bắt đầu phù hợp.

### 16.1. Không dùng getSingularAttribute cho một List

```java
orderType.getSingularAttribute("lines");
```

không phải tra cứu đúng kind. Provider sẽ báo metadata lookup error khi attribute không singular.

### 16.2. Không dùng getPluralAttribute cho Customer

```java
orderType.getPluralAttribute("customer");
```

`customer` là to-one singular attribute; lookup plural không hợp lệ.

### 16.3. Khi cần type-specific behavior

Sau khi tra cứu plural, có thể dùng `getCollectionType()` hoặc `instanceof` để phân nhánh List, Set và Map. Nếu code đã biết kind, nên gọi typed lookup như `getList`, `getSet` hoặc `getMap`.

---

## 17. CollectionAttribute: java.util.Collection

Ví dụ entity có:

```java
@ElementCollection
private Collection<String> keywords =
    new ArrayList<>();
```

Tra cứu:

```java
CollectionAttribute<? super PurchaseOrder, String>
    keywords = orderType.getCollection(
        "keywords", String.class
    );
```

Ví dụ này giả định `keywords` đã được khai báo trong PurchaseOrder của use case tương ứng; mô hình mẫu ban đầu chưa có field này.

### 17.1. Collection không đồng nghĩa List

`java.util.Collection` không bảo đảm ordering và indexed access như List.

### 17.2. getCollection yêu cầu mapping kind phù hợp

Không dùng `getCollection("lines", OrderLine.class)` nếu field thực sự là `List<OrderLine>` và metamodel biểu diễn nó bằng `ListAttribute`; dùng `getList` đúng subtype.

### 17.3. Không dùng CollectionAttribute để suy ra database table

Element collection thường có collection table, nhưng tên bảng/cột, foreign keys và constraints phải tra từ mapping/DDL tương ứng, không lấy từ `CollectionAttribute.getName()`.

---

## 18. SetAttribute: Tập hợp không trùng theo Java Set semantics

Trong PurchaseOrder:

```java
@ElementCollection
private Set<String> labels =
    new HashSet<>();
```

Tra cứu:

```java
SetAttribute<? super PurchaseOrder, String>
    labels = orderType.getSet(
        "labels",
        String.class
    );
```

Metadata thường cho:

```text
labels.getCollectionType() = SET
labels.getElementType().getJavaType() = String.class
labels.getPersistentAttributeType() = ELEMENT_COLLECTION
```

### 18.1. SetAttribute không nói hết DB uniqueness

Java `Set` ngăn duplicate theo equality semantics ở Java. Database constraints đối với collection table còn phụ thuộc DDL/mapping. Không mặc định một Set field đồng nghĩa đã có một UNIQUE index tương ứng.

### 18.2. Nếu Set chứa entities

```java
@ManyToMany
private Set<Tag> tags = new HashSet<>();
```

Nó vẫn được mô tả bởi `SetAttribute`, nhưng persistent kind là `MANY_TO_MANY`, element JPA type là ENTITY.

### 18.3. Không suy ra fetch mode từ SetAttribute

Một SetAttribute không tự nói liệu collection đã initialized hay chưa. Fetch strategy là một chiều khác của mapping/runtime.

---

## 19. ListAttribute: Tập hợp có thứ tự theo Java List

Trong mô hình mẫu:

```java
@OneToMany(mappedBy = "order")
private List<OrderLine> lines =
    new ArrayList<>();
```

Tra cứu:

```java
ListAttribute<? super PurchaseOrder, OrderLine>
    lines = orderType.getList(
        "lines",
        OrderLine.class
    );
```

Thông tin:

```java
PluralAttribute.CollectionType container =
    lines.getCollectionType();

Type<OrderLine> elementType =
    lines.getElementType();
```

Trong mô hình này:

```text
CollectionType          = LIST
PersistentAttributeType = ONE_TO_MANY
Element JPA type        = ENTITY
```

### 19.1. ListAttribute không đảm bảo thứ tự lưu vật lý

Java field là List không tự đảm bảo database rows có thứ tự ổn định khi truy vấn. Muốn semantics thứ tự được ánh xạ rõ, cần `@OrderBy` hoặc `@OrderColumn` theo yêu cầu và mapping.

### 19.2. @OrderColumn không phải là metadata index trong ListAttribute

JPA runtime metamodel có thể cho biết List container kind, nhưng không cung cấp API portable đầy đủ để lấy physical index column name, unique constraints hoặc ordering SQL.

### 19.3. Criteria join List

```java
ListJoin<PurchaseOrder, OrderLine> joinedLines =
    root.join(PurchaseOrder_.lines);
```

Lúc này `joinedLines` là path tới OrderLine entities trong một Criteria query, khác với việc gọi `getList()` để chỉ đọc metadata.

---

## 20. MapAttribute: Tập hợp có key và value

Trong PurchaseOrder:

```java
@ElementCollection
@CollectionTable(
    name = "order_note",
    joinColumns = @JoinColumn(name = "order_id")
)
@MapKeyColumn(name = "note_key")
@Column(name = "note_value")
private Map<String, String> notes =
    new HashMap<>();
```

Tra cứu:

```java
MapAttribute<? super PurchaseOrder, String, String>
    notes = orderType.getMap(
        "notes",
        String.class,
        String.class
    );
```

Các method đặc thù:

```java
Class<String> keyClass =
    notes.getKeyJavaType();

Type<String> keyType =
    notes.getKeyType();

Type<String> valueType =
    notes.getElementType();
```

### 20.1. PluralAttribute element type đối với Map

Với `Map<K,V>`, `getElementType()` mô tả **value type V**, không phải một `Map.Entry<K,V>` hay container Map.

### 20.2. getKeyJavaType() và getKeyType()

- `getKeyJavaType()` trả Java class của key.
- `getKeyType()` trả JPA type metadata của key.
- `getElementType()` trả type metadata của value.

Ví dụ Map<String,String> có BASIC key và BASIC value. Với association Map có entity/embeddable keys theo mapping được hỗ trợ, cần inspect cả hai loại.

### 20.3. PersistentAttributeType của Map

`MapAttribute` có thể là `ELEMENT_COLLECTION`, `ONE_TO_MANY` hoặc `MANY_TO_MANY` tùy mapping. Không mặc định mọi Map được lưu ở một “key-value table” tương tự nhau.

### 20.4. getJavaType() của Map

`notes.getJavaType()` mô tả Java container type (`Map`), không phải `String`. Để lấy value dùng `getElementType().getJavaType()`.

---

## 21. ElementCollection với basic hoặc embeddable values

`@ElementCollection` có thể dùng cho các basic values hoặc embeddable objects.

Basic:

```java
@ElementCollection
private Set<String> labels;
```

Embeddable:

```java
@ElementCollection
private List<Address> shippingStops;
```

Trong trường hợp thứ hai, `getElementType().getPersistenceType()` thường cho `EMBEDDABLE`.

### 21.1. ElementCollection là plural nhưng không phải entity association

Một collection của Strings không trỏ tới nhiều entity instances. `PersistentAttributeType.ELEMENT_COLLECTION` khác `ONE_TO_MANY`/`MANY_TO_MANY`.

### 21.2. Embedded element metadata

```java
EmbeddableType<Address> addressType =
    mm.embeddable(Address.class);
```

Có thể tiếp tục tra các scalar attributes của Address, chẳng hạn `city` và `postalCode`, thay vì coi toàn bộ Address như một chuỗi SQL.

### 21.3. Map element collection

`Map<String,String>` trong ví dụ mẫu là element collection; key/value mappings được tổ chức theo collection table và annotations như `@MapKeyColumn`.

### 21.4. Đừng suy ra collection table name từ member name

Tên Java property `labels` không đủ để khẳng định SQL table tên `labels`. Physical schema phụ thuộc `@CollectionTable`, naming strategies và provider configuration.

---

## 22. To-many entity association cũng là PluralAttribute

Ví dụ:

```java
@OneToMany(mappedBy = "customer")
private Set<PurchaseOrder> orders;
```

hoặc:

```java
@ManyToMany
private Set<Tag> tags;
```

Cả hai có Java container `Set`, nhưng persistent mapping kind khác nhau:

```text
Customer.orders:
  CollectionType = SET
  PersistentAttributeType = ONE_TO_MANY
  ElementType = ENTITY (PurchaseOrder)

Product.tags:
  CollectionType = SET
  PersistentAttributeType = MANY_TO_MANY
  ElementType = ENTITY (Tag)
```

### 22.1. isAssociation() hỗ trợ phân biệt

`ONE_TO_MANY` và `MANY_TO_MANY` là các association mappings. Một plural `ELEMENT_COLLECTION` không nên bị gộp cùng entity associations chỉ vì nó được lưu ở bảng riêng.

### 22.2. Element type cho to-many

```java
Type<OrderLine> lineType =
    lines.getElementType();
```

`lineType.getPersistenceType()` là ENTITY đối với OrderLine mapping.

### 22.3. Không dùng metamodel để suy luận owning side đầy đủ

Metamodel có `PersistentAttributeType`, `isAssociation()` và `getJavaMember()`, nhưng việc association là owning/inverse side, join table name hoặc FK column đòi mapping metadata khác. Reflection annotations có thể giúp nhưng không bao phủ mọi XML override hoặc naming strategy.

---

## 23. Tóm tắt ba chiều phân loại một attribute

Mỗi thuộc tính nên được nhìn theo ba câu hỏi:

1. **Cardinality/container:** Singular hay Plural? Nếu plural, Collection/Set/List/Map?
2. **Persistent mapping kind:** BASIC, EMBEDDED, MANY_TO_ONE, ONE_TO_MANY, ELEMENT_COLLECTION...?
3. **JPA value/element type:** BASIC, ENTITY, EMBEDDABLE...?

Ví dụ:

| Attribute | Cardinality | Persistent kind | Value/element kind |
|---|---|---|---|
| `orderNumber` | Singular | BASIC | BASIC/String |
| `customer` | Singular | MANY_TO_ONE | ENTITY/Customer |
| `shippingAddress` | Singular | EMBEDDED | EMBEDDABLE/Address |
| `lines` | Plural/List | ONE_TO_MANY | ENTITY/OrderLine |
| `labels` | Plural/Set | ELEMENT_COLLECTION | BASIC/String |
| `notes` | Plural/Map | ELEMENT_COLLECTION | BASIC/String, key BASIC/String |

Nếu một metadata-driven application trộn ba chiều này, nó có thể xây sai Criteria joins, suy sai schema hoặc hiển thị collection thành một input text field.

---

## 24. getAttributes() và getDeclaredAttributes()

`ManagedType` có:

```java
Set<? extends Attribute<?, ?>> all =
    orderType.getAttributes();

Set<? extends Attribute<?, ?>> declared =
    orderType.getDeclaredAttributes();
```

Ví dụ type `PurchaseOrder extends Auditable`.

- `getAttributes()` bao gồm các persistent attributes kế thừa từ `@MappedSuperclass` và những attributes của PurchaseOrder.
- `getDeclaredAttributes()` chỉ chứa những attributes được **khai báo trực tiếp** ở PurchaseOrder theo JPA metamodel.

### 24.1. createdAt là inherited attribute

Với mô hình ví dụ, `createdAt` khai báo trong Auditable nên:

```java
orderType.getAttribute("createdAt");
```

có thể tra cứu thành công, còn:

```java
orderType.getDeclaredAttribute("createdAt");
```

không phải lời gọi thích hợp nếu attribute không được khai báo trực tiếp trong PurchaseOrder.

### 24.2. getDeclared* không có nghĩa database column riêng

Một inherited basic field trong `@MappedSuperclass` vẫn có thể được ánh xạ vào bảng PurchaseOrder. “Declared” chỉ nói về chỗ attribute được khai báo trong JPA type hierarchy, không phải physical table ownership.

### 24.3. Mọi typed lookup đều có declared variant

Đối với những method tương ứng, ManagedType có `getDeclaredSingularAttribute`, `getDeclaredPluralAttribute`, `getDeclaredCollection`, `getDeclaredSet`, `getDeclaredList`, `getDeclaredMap`.

Dùng declared variant khi thực sự muốn phân biệt attributes tại mỗi mức của class hierarchy.

---

## 25. getAttribute và getDeclaredAttribute

```java
Attribute<? super PurchaseOrder, ?> number =
    orderType.getAttribute("orderNumber");
```

Khi chỉ cần attribute được khai báo trực tiếp:

```java
Attribute<PurchaseOrder, ?> declaredNumber =
    orderType.getDeclaredAttribute("orderNumber");
```

### 25.1. Không dùng declared lookup cho mapped-superclass field

`createdAt` trong Auditable là inherited. Nếu generic metadata tool muốn toàn bộ persistent fields có hiệu lực trên PurchaseOrder, dùng `getAttributes()`/`getAttribute()`.

### 25.2. Khi nào cần declared lookup?

- In metadata migration report, biết field được định nghĩa tại class nào.
- Hiển thị riêng fields của mỗi entity subtype.
- Kiểm tra local declarations trong class hierarchy.
- Xây schema documentation theo mô hình entity inheritance.

### 25.3. getDeclaringType()

```java
ManagedType<?> declaring =
    attribute.getDeclaringType();
```

Có thể dùng để nhận biết property được khai báo trên mapped superclass hay entity class hiện tại.

---

## 26. Tra cứu singular attributes được khai báo trực tiếp

```java
SingularAttribute<PurchaseOrder, String> number =
    orderType.getDeclaredSingularAttribute(
        "orderNumber",
        String.class
    );
```

Đối chiếu:

```java
SingularAttribute<? super PurchaseOrder, Instant>
    createdAt = orderType.getSingularAttribute(
        "createdAt",
        Instant.class
    );
```

Nếu trường `createdAt` thuộc Auditable, nó không nên được lookup bằng `getDeclaredSingularAttribute` trên PurchaseOrder.

### 26.1. Generic owner type

Trong nhiều signatures `getSingularAttribute()` có owner type `? super X` để cho phép attribute đến từ superclass. Declared lookup có owner X vì attribute được khai báo trực tiếp ở chính X.

### 26.2. Không ép generic casting tùy tiện

Một metadata scanner làm việc với `ManagedType<?>` nên dùng wildcards và kiểm tra `instanceof`, thay vì cast mọi attribute sang `SingularAttribute<PurchaseOrder,String>`.

---

## 27. Tra cứu primary key và version bằng metadata

`EntityType<X>` kế thừa khả năng nhận diện identifier/version attributes từ `IdentifiableType<X>`.

Ví dụ:

```java
EntityType<PurchaseOrder> orderType =
    mm.entity(PurchaseOrder.class);

boolean singleId = orderType.hasSingleIdAttribute();

Type<?> idType = orderType.getIdType();

SingularAttribute<? super PurchaseOrder, Long>
    id = orderType.getId(Long.class);
```

Với version field khai báo là primitive `long`:

```java
SingularAttribute<? super PurchaseOrder, Long>
    version = orderType.getVersion(long.class);
```

Phần generic wrapper của primitive class literal được Java type system đại diện theo reflection API; metadata Java type thực tế của member có thể là `long.class`.

### 27.1. Không tìm ID chỉ bằng tên

Một entity có thể dùng tên `orderKey`, composite key hoặc `@EmbeddedId`. Metadata `isId()`/IdentifiableType API đáng tin hơn giả định mọi entity có field `"id"`.

### 27.2. Embedded ID

Khi dùng `@EmbeddedId`, identifier thường là một singular embeddable attribute. `hasSingleIdAttribute()` có thể true nhưng ID type không phải basic `Long`; cần tra theo embeddable class.

### 27.3. IdClass

Với `@IdClass` có nhiều identifier attributes, `getIdClassAttributes()` hỗ trợ tra tập attributes liên quan. Không gọi `getId(Long.class)` với giả định lúc nào cũng có một single ID field.

### 27.4. Version không phải mặc định bắt buộc

Một entity không có `@Version` thì `hasVersionAttribute()` trả false và việc gọi `getVersion(...)` không phù hợp. Generic scanner nên kiểm tra trước.

### 27.5. Entity inheritance

`IdentifiableType.getSupertype()` cho phép tra identifiable superclass nếu có, hỗ trợ hiểu hierarchy của ID/version mapping; không nên nhầm với `ManagedType.getDeclaredAttributes()`.

---

## 28. Java member, field access và property access

Với entity:

```java
@Id
private Long id;

private String code;
```

Provider thường dùng field access theo vị trí của `@Id`.

Với property access:

```java
private Long id;
private String code;

@Id
public Long getId() {
    return id;
}

@Basic
public String getCode() {
    return code;
}
```

Provider có thể nhận persistent property thông qua getter.

### 28.1. getJavaMember()

```java
java.lang.reflect.Member member =
    attr.getJavaMember();

System.out.println(member.getName());
System.out.println(
    member.getDeclaringClass().getName()
);
```

`Member` có thể là `Field` hoặc `Method`.

### 28.2. Không mặc định member là Field

Sai:

```java
Field f = (Field) attr.getJavaMember();
```

nếu entity dùng property access.

Đúng là kiểm tra loại:

```java
Member member = attr.getJavaMember();

if (member instanceof Field field) {
    // field access metadata.
} else if (member instanceof Method method) {
    // property access metadata.
}
```

### 28.3. Reflection annotation không phải resolved schema

Từ member có thể kiểm tra annotations, nhưng physical column name có thể bị XML overrides, naming strategy, provider conventions hoặc attribute overrides thay đổi. Không coi Reflection là nguồn duy nhất xác định DDL.

### 28.4. @Transient không nằm trong persistent attributes

Trường chỉ dùng cho UI hoặc tính toán tạm, đánh dấu `@Transient`, không được xem là persistent attribute của ManagedType dù reflection vẫn thấy field.

---

## 29. Runtime metamodel và static metamodel

Có hai cách tiếp cận phổ biến:

**Runtime metamodel:**

```java
EntityType<PurchaseOrder> orderType =
    em.getMetamodel().entity(PurchaseOrder.class);

Attribute<?, ?> attr =
    orderType.getAttribute("orderNumber");
```

**Static metamodel:**

```java
root.get(PurchaseOrder_.orderNumber);
```

Static metamodel được annotation processor/tooling sinh ra dựa trên mappings, giúp Java compiler hỗ trợ tên/kiểu thuộc tính thay vì string literals.

### 29.1. Dạng class static metamodel minh họa

Một generated class có thể có cấu trúc tương tự:

```java
@StaticMetamodel(PurchaseOrder.class)
public abstract class PurchaseOrder_ {

    public static volatile
        SingularAttribute<PurchaseOrder, Long> id;

    public static volatile
        SingularAttribute<PurchaseOrder, String> orderNumber;

    public static volatile
        SingularAttribute<PurchaseOrder, Customer> customer;

    public static volatile
        SingularAttribute<PurchaseOrder, Address> shippingAddress;

    public static volatile
        ListAttribute<PurchaseOrder, OrderLine> lines;

    public static volatile
        SetAttribute<PurchaseOrder, String> labels;

    public static volatile
        MapAttribute<PurchaseOrder, String, String> notes;
}
```

Đây là **minh họa hình dạng code sinh ra**, không phải file cần tự viết và bảo trì. Generated metamodel có thể chứa thêm constants/imports và các attributes kế thừa tùy generator/version.

### 29.2. Annotation processor

Các công cụ như Hibernate JPA Metamodel Generator/Hibernate Processor hoặc annotation processor tương ứng của stack có thể tạo static metamodel classes. Artifact names và setup cụ thể phụ thuộc version, nên phải dựa trên dependency management của project hiện tại.

### 29.3. Runtime introspection vẫn cần thiết

Static metamodel phù hợp khi viết Criteria queries ở compile time. Runtime metamodel hữu ích khi duyệt **mọi** attributes để làm dynamic forms, generic filters hoặc diagnostics.

### 29.4. Static metamodel không thay database constraints

Một field typed là String trong `PurchaseOrder_` không cho biết mọi unique/check constraints ở database.

---

## 30. Criteria API dùng singular attribute

Ví dụ tìm Order theo order number.

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);

Root<PurchaseOrder> root =
    cq.from(PurchaseOrder.class);

cq.select(root)
  .where(
      cb.equal(
          root.get(PurchaseOrder_.orderNumber),
          "ORD-2026-001"
      )
  );

List<PurchaseOrder> result =
    em.createQuery(cq).getResultList();
```

### 30.1. Vì sao tốt hơn string path?

```java
root.get("orderNumber");
```

có thể hoạt động nhưng lỗi typo chỉ lộ tại runtime. Static metamodel giúp compiler/generator tham gia kiểm soát member name và type.

### 30.2. Singular relationship join

```java
Join<PurchaseOrder, Customer> customerJoin =
    root.join(PurchaseOrder_.customer);

cq.select(root)
  .where(
      cb.equal(
          customerJoin.get(Customer_.id),
          customerId
      )
  );
```

`Customer_.id` cũng cần được generator sinh cho Customer.

### 30.3. Embedded path

```java
Path<String> city = root
    .get(PurchaseOrder_.shippingAddress)
    .get(Address_.city);

cq.where(cb.equal(city, "Hà Nội"));
```

Path navigation cho embeddable khác với việc join entity association; không tự biến Address thành một entity/table độc lập.

---

## 31. Criteria API với plural ListAttribute

Giả sử tìm Orders có OrderLine quantity lớn hơn một ngưỡng:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);

Root<PurchaseOrder> root =
    cq.from(PurchaseOrder.class);

ListJoin<PurchaseOrder, OrderLine> line =
    root.join(PurchaseOrder_.lines);

cq.select(root)
  .distinct(true)
  .where(
      cb.greaterThan(
          line.get(OrderLine_.quantity),
          10
      )
  );

List<PurchaseOrder> orders =
    em.createQuery(cq).getResultList();
```

### 31.1. Vì sao distinct(true)?

Một Order có nhiều Lines khớp filter có thể tạo nhiều SQL joined rows. `distinct(true)` diễn đạt mục đích loại kết quả trùng theo Criteria semantics, nhưng hiệu năng/SQL translation cần đánh giá theo DB/provider.

### 31.2. Join type phải phù hợp

Inner join không trả Orders không có Lines. Khi cần những Orders thiếu Lines hoặc optional associations, phải chọn left join/exists phù hợp; metamodel chỉ xác định property types, không quyết định business query semantics.

### 31.3. Metadata và query là hai giai đoạn

`orderType.getList("lines", OrderLine.class)` tra metadata. `root.join(PurchaseOrder_.lines)` xây một join trong Criteria query. Hai API liên quan nhưng không phải một operation.

---

## 32. Criteria API với SetAttribute

Tìm Orders có label bằng `"priority"`:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);

Root<PurchaseOrder> root =
    cq.from(PurchaseOrder.class);

SetJoin<PurchaseOrder, String> label =
    root.join(PurchaseOrder_.labels);

cq.select(root)
  .distinct(true)
  .where(
      cb.equal(label, "priority")
  );

List<PurchaseOrder> orders =
    em.createQuery(cq).getResultList();
```

`labels` là `@ElementCollection Set<String>`, nên Criteria join có element type String chứ không phải `Tag` entity.

### 32.1. Khác với @ManyToMany

Nếu labels được mô hình hóa là entity `Tag`, Criteria join sẽ có element type Tag và có thể tiếp tục navigate Tag attributes.

### 32.2. Không thay đổi collection chỉ để query

Criteria API tạo query representation; nó không đòi mutate collection trong một managed PurchaseOrder.

---

## 33. Criteria API với MapAttribute

Map có key/value semantics. Ví dụ tìm Order có note `"channel" = "web"`:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);

Root<PurchaseOrder> root =
    cq.from(PurchaseOrder.class);

MapJoin<PurchaseOrder, String, String> note =
    root.join(PurchaseOrder_.notes);

cq.select(root)
  .distinct(true)
  .where(
      cb.and(
          cb.equal(note.key(), "channel"),
          cb.equal(note.value(), "web")
      )
  );

List<PurchaseOrder> orders =
    em.createQuery(cq).getResultList();
```

### 33.1. Map key và value là hai paths khác nhau

- `note.key()` biểu diễn key path.
- `note.value()` biểu diễn value path.
- Metadata `MapAttribute.getKeyType()` và `getElementType()` cho phép biết Java/JPA types của hai phía.

### 33.2. Key có thể là loại khác String

Ví dụ Map<Locale,String> hoặc Map<Product,BigDecimal> khi mapping cho phép. Generic query builder phải đọc metadata thực tế và validate key/value types trước khi tạo predicates.

### 33.3. Không biến Map into SQL JSON mặc định

Một Map có `@ElementCollection` thường được mapping qua collection table. Một Map được provider map vào JSON column là câu chuyện provider/custom type riêng; không dùng Java `Map` làm bằng chứng rằng SQL schema luôn là JSON hay join table.

---

## 34. Generic metadata inspector chạy theo runtime metamodel

Một utility có thể in attributes mà không biết trước entity cụ thể:

```java
import jakarta.persistence.metamodel.*;
import java.lang.reflect.Member;

public final class MetamodelInspector {

    private MetamodelInspector() {}

    public static void describe(ManagedType<?> type) {

        System.out.println(
            "Managed type: " +
            type.getJavaType().getName()
        );

        for (Attribute<?, ?> attr : type.getAttributes()) {

            System.out.println(
                "name=" + attr.getName()
                + ", javaType=" + attr.getJavaType().getName()
                + ", kind=" + attr.getPersistentAttributeType()
                + ", association=" + attr.isAssociation()
                + ", collection=" + attr.isCollection()
            );

            Member member = attr.getJavaMember();

            if (member != null) {
                System.out.println(
                    "  member=" +
                    member.getDeclaringClass().getName() +
                    "." + member.getName()
                );
            }

            if (attr instanceof SingularAttribute<?, ?> s) {
                System.out.println(
                    "  singular, id=" + s.isId()
                    + ", version=" + s.isVersion()
                    + ", optional=" + s.isOptional()
                    + ", jpaType=" +
                    s.getType().getPersistenceType()
                );
            } else if (attr instanceof MapAttribute<?, ?, ?> m) {
                System.out.println(
                    "  map, key=" +
                    m.getKeyJavaType().getName()
                    + ", value=" +
                    m.getElementType().getJavaType().getName()
                );
            } else if (attr instanceof PluralAttribute<?, ?, ?> p) {
                System.out.println(
                    "  plural, collectionType=" +
                    p.getCollectionType()
                    + ", elementType=" +
                    p.getElementType().getJavaType().getName()
                );
            }
        }
    }
}
```

Sử dụng:

```java
MetamodelInspector.describe(
    emf.getMetamodel().entity(PurchaseOrder.class)
);
```

### 34.1. Vì sao xử lý Map trước Plural?

`MapAttribute` cũng là một `PluralAttribute`. Nếu nhánh generic Plural đứng trước thì phần phân loại riêng cho key type của Map có thể không được thực hiện.

### 34.2. Java reflection import

`java.lang.reflect.Member` chỉ giúp xác định field/getter đã mapped. Đừng giả định nó có API riêng để trả SQL foreign key, collection table hoặc constraints.

### 34.3. Không cần EntityManager mỗi lần in metadata

Utility có thể chạy ở startup với `EntityManagerFactory.getMetamodel()` rồi lưu mô tả immutable nếu ứng dụng cần dùng nhiều lần.

---

## 35. Dynamic classification theo attribute kind

Một generic inspector có thể phân thành ba nhóm:

```java
public static void categorize(ManagedType<?> type) {

    for (Attribute<?, ?> a : type.getAttributes()) {

        if (a.getPersistentAttributeType()
                == Attribute.PersistentAttributeType.BASIC) {

            System.out.println(
                "BASIC: " + a.getName()
            );

        } else if (a instanceof SingularAttribute<?, ?>) {

            System.out.println(
                "OTHER SINGULAR: " + a.getName()
            );

        } else if (a instanceof PluralAttribute<?, ?, ?> p) {

            System.out.println(
                "PLURAL " + p.getCollectionType()
                + ": " + a.getName()
            );
        }
    }
}
```

### 35.1. Đây là cách nhóm phục vụ use case

Nhóm BASIC đứng đầu; còn `OTHER SINGULAR` có thể là EMBEDDED, MANY_TO_ONE hoặc ONE_TO_ONE. Nhóm PLURAL bao gồm cả entity associations và element collections.

### 35.2. Không coi `OTHER SINGULAR` là lỗi

Một entity hợp lệ có thể có nhiều to-one associations hoặc embedded objects. Generic form/filter builder cần có quy tắc riêng cho các kiểu này.

### 35.3. Không thay `getPersistentAttributeType()` bằng `instanceof SingularAttribute`

Nếu mục tiêu của ứng dụng là “chỉ lấy scalar database values”, điều kiện instanceof Singular quá rộng. Dùng BASIC kind để phân loại chính xác hơn.

---

## 36. getCollection, getSet, getList, getMap: Chọn API nào?

| Mô tả thuộc tính | API runtime metamodel | Kết quả |
|---|---|---|
| Không biết kind | `getAttribute(name)` | `Attribute` |
| Biết là singular | `getSingularAttribute(name)` | `SingularAttribute` |
| Biết là plural, chưa biết container | `getPluralAttribute(name)` | `PluralAttribute` |
| `Collection<E>` | `getCollection(name, E.class)` | `CollectionAttribute` |
| `Set<E>` | `getSet(name, E.class)` | `SetAttribute` |
| `List<E>` | `getList(name, E.class)` | `ListAttribute` |
| `Map<K,V>` | `getMap(name, K.class, V.class)` | `MapAttribute` |

### 36.1. Dùng typed overload để phát hiện mismatch sớm

Ví dụ:

```java
orderType.getList("lines", OrderLine.class);
```

rõ ý định hơn việc lấy raw Attribute rồi cast mà không kiểm tra.

### 36.2. Java type đúng nhưng collection kind sai vẫn không hợp lệ

`List<OrderLine>` không tương đương `Set<OrderLine>` chỉ vì element type đều là OrderLine.

### 36.3. Đúng collection kind nhưng element type sai cũng không hợp lệ

`getList("lines", Customer.class)` không phù hợp khi actual element type là OrderLine.

### 36.4. Khi không chắc, tra tổng quát trước

Một ứng dụng nhận tên thuộc tính từ cấu hình có thể dùng `getAttribute(name)`, kiểm tra `isCollection()` và `instanceof` rồi mới thao tác như subtype tương ứng.

---

## 37. Truy cập metadata theo tên dễ gặp lỗi gì?

Các lookup có tên hoặc type không khớp thường ném `IllegalArgumentException` theo JPA API contract.

Ví dụ:

```java
orderType.getAttribute("notExisting");

orderType.getSingularAttribute("lines");

orderType.getList("customer", Customer.class);

orderType.getSet("lines", OrderLine.class);
```

Các calls trên không nên được coi là trả `null` khi metadata không tồn tại.

### 37.1. Xử lý trong dynamic API

Nếu user được chọn field filter, backend có thể kiểm tra trước:

```java
Set<String> allowedBasicFields =
    basicAttributeNames(orderType).stream()
        .collect(Collectors.toSet());

if (!allowedBasicFields.contains(requestedField)) {
    throw new IllegalArgumentException(
        "Unsupported filter field"
    );
}
```

Đây mới là kiểm tra về **loại field**, chưa phải kiểm tra authorization. Phần security vẫn phải được áp dụng riêng.

### 37.2. Không dùng exception để dò rất nhiều tên

Khi cần xây UI hoặc tự động lập tài liệu, duyệt `getAttributes()` một lần rồi lập index theo name/type có thể rõ ràng hơn thử hàng trăm getAttribute calls và catch exceptions.

### 37.3. Class literal phải đúng với Java type

Nếu attribute Java type là primitive `int`, đừng mặc định typed lookup bằng `Integer.class` có semantics giống `int.class`. Dùng type metadata và kiểu Java thực tế tương ứng.

---

## 38. Metamodel và inheritance

Mô hình:

```text
@MappedSuperclass Auditable
    |
    +-- createdAt : Instant
    +-- updatedAt : Instant
    |
@Entity PurchaseOrder
    +-- id : Long
    +-- version : long
    +-- orderNumber : String
```

Tại `PurchaseOrder`:

```java
orderType.getAttributes();
```

bao gồm cả các attributes kế thừa.

```java
orderType.getDeclaredAttributes();
```

chỉ liệt kê các attributes được khai báo trực tiếp ở PurchaseOrder.

### 38.1. getDeclaringType hữu ích hơn getJavaMember trong một số trường hợp

Một attribute có thể được mapping lại/override trên subclass. `getDeclaringType()` trả JPA managed type nơi attribute được khai báo theo model, còn Java member cung cấp reflection information.

### 38.2. Entity inheritance chiến lược JOINED/SINGLE_TABLE/TABLE_PER_CLASS

Metamodel vẫn mô tả entity types và attributes, không tự phản ánh đầy đủ physical SQL storage strategy. Một thuộc tính inherited có thể được lưu ở bảng khác tùy inheritance mapping.

### 38.3. Đừng coi mỗi EntityType là một bảng riêng

Với SINGLE_TABLE inheritance, nhiều entity types có thể chia sẻ cùng SQL table. Metamodel type hierarchy không phải một map một-một với database tables.

---

## 39. Tra cứu các attributes của EmbeddableType

```java
EmbeddableType<Address> address =
    mm.embeddable(Address.class);

for (Attribute<?, ?> a : address.getAttributes()) {
    System.out.println(
        a.getName() + " : " +
        a.getJavaType().getSimpleName()
    );
}
```

Kết quả sẽ mô tả `street`, `city`, `postalCode` như những persistent basic attributes của Address.

### 39.1. @Embeddable cũng có Metamodel

Dù không phải entity độc lập và không có primary key riêng trong mô hình thông thường, Address vẫn là managed type theo JPA và có attributes để introspection.

### 39.2. Embeddable nested

Nếu Address chứa một embeddable khác, metadata có thể tiếp tục diễn giải qua `getSingularAttribute()` và `getType()`. Dynamic schema explorer nên tránh vòng lặp vô hạn bằng cách theo dõi visited types/depth limit nếu đi qua association graphs.

### 39.3. Embeddable trong collection

Một `List<Address>` với `@ElementCollection` có PluralAttribute element JPA type là EMBEDDABLE. Việc nó nằm ở collection table không biến Address thành entity có `@Id`.

---

## 40. Liên hệ với database schema và DDL

Metamodel có thể trả:

```text
name="orderNumber"
javaType=java.lang.String
persistentKind=BASIC
```

nhưng để suy ra schema:

```sql
order_number VARCHAR(40) NOT NULL
```

cần xem thêm:

- `@Column(name, length, nullable, unique, precision, scale)`.
- XML mapping overrides.
- Physical/implicit naming strategy của provider.
- `@AttributeOverride`, `@AssociationOverride`.
- `@JoinColumn`, `@JoinTable`, `@CollectionTable`.
- Dialect và database type mapping.
- Migrated actual database schema.
- Composite constraints/indexes không nằm ở một Attribute.
- Custom converters và provider-specific mappings.

### 40.1. Metamodel không cho toàn bộ column metadata portable

Không có một method chuẩn duy nhất như:

```java
attribute.getPhysicalColumnName();
```

trong JPA Attribute API.

### 40.2. Khi cần actual database schema

Dùng một migration source of truth, database catalog/JDBC `DatabaseMetaData`, hoặc provider-specific mapping introspection khi thực sự cần physical schema details.

### 40.3. Không dùng Java class name làm bảng SQL

`@Table(name="purchase_order")` đã cho thấy tên SQL khác class `PurchaseOrder`. Ngoài ra, entity inheritance, secondary tables và join tables làm quan hệ giữa Java types và SQL tables phức tạp hơn.

---

## 41. Độ portable giữa Hibernate, EclipseLink và các providers

JPA Metamodel API chuẩn hóa các interface và enum được đề cập. Hibernate/EclipseLink có implementation tương ứng.

Nhưng cần lưu ý:

- Bootstrap metadata có thể phụ thuộc annotations/XML/config.
- Provider extensions có thể thêm mapping types không nằm gọn trong JPA portable model.
- Static metamodel generators là tooling riêng và có version dependencies.
- Tên physical columns/tables chịu naming strategies/dialect.
- Runtime metadata của provider có thể giàu thông tin hơn chuẩn JPA.
- Dynamic introspection phải kiểm chứng nếu có custom converters, JSON types, composite values hoặc đặc thù provider.

### 41.1. Không dựa vào internal provider classes nếu chỉ cần chuẩn JPA

Nếu bài toán chỉ là xác định basic/singular/plural, ưu tiên:

```java
jakarta.persistence.metamodel.Metamodel
jakarta.persistence.metamodel.ManagedType
jakarta.persistence.metamodel.Attribute
jakarta.persistence.metamodel.SingularAttribute
jakarta.persistence.metamodel.PluralAttribute
```

trước khi unwrapping Hibernate-specific EntityPersister hay EclipseLink Descriptor.

### 41.2. Khi cần physical mapping thì vendor extension là lựa chọn có điều kiện

Nếu phải biết SQL column names, FK mappings hay table groups mà JPA Metamodel không phơi ra, dùng internal metadata của provider có thể hợp lý nhưng cần khóa version, tests và tài liệu hóa dependency.

### 41.3. Provider migration

Một tool chỉ dùng các interface JPA Metamodel thường dễ chuyển provider hơn tool phụ thuộc vendor descriptors. Tuy nhiên, hãy chạy integration tests để xác nhận mọi mapping được bootstrap và phân loại chính xác trên stack mới.

---

## 42. Các ứng dụng thực tế của attribute introspection

### 42.1. Dynamic filter builder

API nhận các tên field hợp lệ như `orderNumber`, `createdAt`, `version`. Backend dùng metamodel xác nhận field là BASIC và thuộc allowlist, rồi tạo Criteria predicates.

### 42.2. Form generation

Một admin UI có thể hiển thị String/number/date fields từ singular BASIC metadata. Embedded fields được mở rộng theo cấu trúc; to-one associations dùng lookup component; to-many được hiển thị bằng một editor riêng.

### 42.3. Entity documentation

Một tool có thể tạo bảng các persistent attributes, loại mapping, Java type và declaring type để hỗ trợ review domain model.

### 42.4. Generic audit field list

Một auditing tool có thể liệt kê scalar persistent fields. Nhưng audit policy phải loại bỏ secrets/PII và không giả định mọi field đều được phép xuất ra log.

### 42.5. Repository query validation

Khi cấu hình một tên sort/filter field, metamodel giúp fail fast nếu thuộc tính không tồn tại hoặc là collection không được hỗ trợ.

### 42.6. Cross-provider migration checks

Một acceptance test có thể so sánh danh sách persistent names/kinds giữa hai providers, nhưng không dùng những khác biệt về physical schema như bằng chứng trực tiếp nếu chưa xét naming strategy.

### 42.7. Query planning assistance

Metadata giúp xác định khi nào phải join to-one/to-many, nhưng không tự cung cấp query cost, index selectivity hoặc DB optimizer plan.

---

## 43. Cẩn trọng khi xây metadata-driven API

Một ứng dụng cho người dùng chọn field sort/filter có thể có nguy cơ:

- Expose field nhạy cảm như `passwordHash`, `internalNote`.
- Cho filter/sort trên collection lớn gây truy vấn nặng.
- Tạo joins vượt quyền tenant.
- Sinh Cartesian products.
- Cho truy cập các relationships không được cấp quyền.
- Gây DoS từ nested paths quá sâu.

### 43.1. Metamodel không thay authorization

Dù attribute tồn tại trong JPA model, caller chưa chắc được xem/lọc/sort theo nó.

### 43.2. Allowlist riêng cho từng use case

```java
Set<String> sortableFields = Set.of(
    "orderNumber",
    "createdAt"
);
```

Dùng metamodel để xác nhận tên/type, còn authorization và resource limits do API policy quyết định.

### 43.3. Chặn nested join depth

Nếu client có thể yêu cầu `order.customer.orders.customer...`, một dynamic query builder phải giới hạn depth và entity graph traversal, không để metadata tự mở vô hạn.

### 43.4. Phân biệt plural filter semantics

Một filter trên `lines.quantity > 10` thường liên quan EXISTS/ANY/join logic và có thể nhân rows. Không đơn giản xem List<OrderLine> như một scalar SQL column.

---

## 44. Performance và lifecycle của Metamodel API

Metamodel thường được provider xây dựng từ lúc bootstrap. Metadata introspection không cần chạy trong mỗi business transaction nếu chỉ cần cấu trúc entity.

### 44.1. Có thể cache mô tả đã chuẩn hóa

Một application có thể xây immutable map:

```text
PurchaseOrder:
    id -> BASIC/Singular/Long
    customer -> MANY_TO_ONE/Singular/Customer
    lines -> ONE_TO_MANY/List/OrderLine
    labels -> ELEMENT_COLLECTION/Set/String
```

Cache này là **application metadata cache**, không phải JPA L2 entity cache. Nó không lưu database row values.

### 44.2. Giữ cấu trúc metadata theo EntityManagerFactory

Không trộn metadata của hai persistence units có mappings khác nhau; mỗi EMF có metamodel riêng.

### 44.3. Không dùng introspection thay index tuning

Biết `orderNumber` là BASIC/String không cho biết cột SQL có index, selectivity hay query plan tốt. Cần EXPLAIN/DB statistics cho performance.

### 44.4. Không phát SQL per attribute trong UI metadata endpoint

Nếu mục tiêu chỉ hiển thị thuộc tính, dùng metamodel thay vì chạy `SELECT` một entity rồi gọi getters/lazy associations để “dò” cấu trúc.

---

## 45. Các lỗi thường gặp

| Biểu hiện | Nguyên nhân phổ biến | Hướng xử lý |
|---|---|---|
| Tra `lines` bằng getSingularAttribute thất bại | `lines` là plural List | Dùng getList/getPluralAttribute |
| Tra `customer` bằng getPluralAttribute thất bại | To-one singular | Dùng getSingularAttribute |
| Tưởng mọi singular đều BASIC | Embedded/to-one cũng singular | Xem PersistentAttributeType |
| Tưởng Set<String> là association | `@ElementCollection` basic values | Xem ELEMENT_COLLECTION và element type |
| Tưởng `byte[]` là plural | Basic/LOB mapping | Dựa mapping kind |
| Dùng getJavaType() để lấy List element type | Kết quả là container type | Dùng getElementType() |
| Dùng Map.getElementType() làm key type | Element của Map là value | Dùng getKeyType() |
| getDeclaredAttribute không thấy createdAt | Thuộc tính inherited | Dùng getAttribute/getAttributes |
| getAttributes có nhiều field hơn source class | Có mapped superclass | Xem getDeclaringType |
| getAttribute("order_number") không thấy | Name là Java property | Dùng "orderNumber" |
| @Transient field không được liệt kê | Không persistent | Đúng thiết kế |
| Cast JavaMember thành Field lỗi | Entity dùng property access | Kiểm tra Field/Method |
| Tưởng getName() là SQL column | JPA attribute name khác DDL | Xem actual schema/naming |
| Tưởng List mặc định có SQL ordering | List mapping chưa chắc có order index | Cấu hình @OrderBy/@OrderColumn |
| Tưởng getId(Long.class) luôn có | Composite/embedded IDs | Kiểm tra IdentifiableType |
| getVersion không thấy | Entity không có @Version | Kiểm tra hasVersionAttribute |
| Query generic join nhân rows | To-many relationships | DISTINCT/EXISTS phù hợp |
| Dynamic API expose secret field | Không có allowlist/security | Explicit authorization policy |
| Static metamodel class không được sinh | Chưa cấu hình annotation processor | Kiểm tra build tooling |
| Internal Hibernate API hỏng sau upgrade | Phụ thuộc vendor descriptor | Ưu tiên JPA API hoặc khóa version |
| Metadata type không khớp custom mapping | Provider extensions/converters | Test thực tế và phân biệt Java/JDBC type |

---

## 46. Bài tập thực hành

### Bài 1. Basic hay singular?

Một entity có `String code` persistent.

**Đáp án:** Thường là BASIC và đồng thời là SingularAttribute.

### Bài 2. Customer quan hệ nhiều-một

`@ManyToOne Customer customer` là singular hay plural?

**Đáp án:** SingularAttribute; PersistentAttributeType là MANY_TO_ONE, không phải BASIC.

### Bài 3. Embedded Address

`@Embedded Address address` có persistent kind nào?

**Đáp án:** EMBEDDED; vẫn là singular. Type.PersistenceType thường EMBEDDABLE.

### Bài 4. Set<String> với @ElementCollection

**Đáp án:** SetAttribute, CollectionType.SET, PersistentAttributeType.ELEMENT_COLLECTION, element JPA type BASIC.

### Bài 5. List<OrderLine>

`@OneToMany List<OrderLine> lines`.

**Đáp án:** ListAttribute, CollectionType.LIST, PersistentAttributeType.ONE_TO_MANY, element JPA type ENTITY.

### Bài 6. Map<String,String>

**Câu hỏi:** Metadata của key và value lấy ở đâu?

**Đáp án:** `MapAttribute.getKeyType()`/`getKeyJavaType()` cho key; `getElementType()` cho value.

### Bài 7. getJavaType() của List

**Câu hỏi:** `lines.getJavaType()` trả `OrderLine.class` không?

**Đáp án:** Không; nó diễn đạt container Java type (List). Dùng `getElementType().getJavaType()` cho OrderLine.

### Bài 8. getSingularAttribute trên Set

**Đáp án:** Không phù hợp; dùng getSet/getPluralAttribute.

### Bài 9. Basic attribute interface

Có interface JPA `BasicAttribute` tương tự SingularAttribute không?

**Đáp án:** Không theo cách phân loại đang dùng; basic là PersistentAttributeType.BASIC, thường được biểu diễn bởi SingularAttribute.

### Bài 10. @Transient

Field String có `@Transient` có xuất hiện trong getAttributes không?

**Đáp án:** Không, vì nó không persistent.

### Bài 11. Mapped superclass

`createdAt` khai báo trong `Auditable`, Order extends Auditable.

**Đáp án:** getAttributes/getAttribute của Order bao gồm inherited field; getDeclaredAttributes/getDeclaredAttribute của Order không xem đó là local declaration.

### Bài 12. Attribute.getName

Java field `orderNumber` ánh xạ SQL column `order_number`.

**Đáp án:** getName trả `orderNumber`, không phải `order_number`.

### Bài 13. getJavaMember

Entity dùng property access.

**Đáp án:** Member có thể là getter Method; không ép cast thành Field.

### Bài 14. @Version

Làm sao nhận diện versioned attribute mà không dựa vào field name?

**Đáp án:** SingularAttribute.isVersion() hoặc IdentifiableType metadata.

### Bài 15. Composite ID

Entity dùng @IdClass với hai khóa.

**Đáp án:** Không gọi getId(Long.class) như single ID; xem hasSingleIdAttribute và getIdClassAttributes.

### Bài 16. EmbeddedId

**Đáp án:** Single identifier attribute có Java type embeddable; không mặc định basic Long.

### Bài 17. Query Criteria basic field

**Đáp án:** `root.get(PurchaseOrder_.orderNumber)` rồi tạo predicate tương ứng.

### Bài 18. Query Criteria to-many

**Đáp án:** `root.join(PurchaseOrder_.lines)`, dùng ListJoin và cân nhắc duplicate rows/EXISTS.

### Bài 19. Dynamic filter field

Người dùng yêu cầu filter theo `internalCost`.

**Đáp án:** Metamodel có thể xác minh field tồn tại, nhưng phải có authorization/allowlist riêng.

### Bài 20. DDL columns

Có thể gọi `attribute.getPhysicalColumnName()` trong JPA standard metamodel không?

**Đáp án:** Không. Metamodel không là API portable đầy đủ cho physical schema.

### Bài 21. Static metamodel generation

Dự án không tìm được `PurchaseOrder_`.

**Đáp án:** Kiểm tra annotation processor/module/build configuration, generated sources và version compatibility.

### Bài 22. @ManyToMany Set<Tag>

**Đáp án:** SetAttribute, PersistentAttributeType.MANY_TO_MANY, element type ENTITY.

### Bài 23. Collection<Address>

`@ElementCollection List<Address>` có element JPA kind nào?

**Đáp án:** EMBEDDABLE, dù attribute là plural element collection.

### Bài 24. getAttribute không tồn tại

**Đáp án:** JPA lookup thường ném IllegalArgumentException, không giả định trả null.

### Bài 25. Provider migration

**Câu hỏi:** Khi nào nên dùng provider internal descriptors?

**Đáp án:** Chỉ khi thông tin cần thiết như physical schema details không có trong JPA API, đã chấp nhận vendor dependency và có version-specific tests.

---

## 47. Checklist khi tra cứu persistent attributes

1. Metadata đến từ đúng EntityManagerFactory/persistence unit?
2. Đã phân biệt Java reflection, JPA metamodel và JDBC schema metadata?
3. Có tra EntityType/EmbeddableType/ManagedType đúng kind?
4. Có hiểu getAttributes gồm inherited attributes?
5. Có hiểu getDeclaredAttributes chỉ gồm local declarations?
6. Có dùng getDeclaringType khi cần phân biệt class hierarchy?
7. Có dùng persistent name thay vì SQL column name?
8. Có xác nhận attribute tồn tại trước khi cast?
9. Có phân biệt BASIC và SingularAttribute?
10. Có biết EMBEDDED là singular nhưng không BASIC?
11. Có biết MANY_TO_ONE/ONE_TO_ONE là singular associations?
12. Có biết ONE_TO_MANY/MANY_TO_MANY là plural associations?
13. Có biết ELEMENT_COLLECTION là plural nhưng element có thể BASIC/EMBEDDABLE?
14. Có dùng getJavaType cho attribute và getElementType cho collection elements?
15. Có xử lý key/value riêng cho MapAttribute?
16. Có phân biệt CollectionType và PersistentAttributeType?
17. Có dùng typed getList/getSet/getMap đúng Java types?
18. Có hiểu @Transient không xuất hiện trong persistent model?
19. Có kiểm tra Field/Method khi dùng getJavaMember?
20. Có nhận diện ID/version qua metadata thay vì field names?
21. Có xử lý EmbeddedId/IdClass thay vì giả định mọi ID là Long?
22. Có dùng static metamodel generator nếu muốn Criteria compile-time safety?
23. Có hạn chế to-many joins để tránh duplicate rows hoặc heavy SQL?
24. Có nhớ JPA metamodel không cung cấp toàn bộ physical table/column/constraint details?
25. Có allowlist/authorization cho metadata-driven API?
26. Có giới hạn nested paths/joins/filters từ đầu vào người dùng?
27. Có kiểm thử custom converter/provider extension trên runtime cụ thể?
28. Có tránh phụ thuộc vendor internals khi chỉ cần JPA standard metadata?
29. Có kết hợp migration/JDBC metadata khi phân tích actual schema?
30. Có lưu metadata dưới dạng immutable snapshot thay vì quét lại cho mỗi request nếu cần tối ưu?

---

## 48. Sơ đồ quyết định tra cứu một thuộc tính

```text
          Cần tra metadata của entity/embeddable
                           |
                           v
                    Lấy Metamodel
                           |
                           v
               entity()/managedType()
                           |
                           v
                  Biết tên attribute?
                      /          \
                    Không        Có
                     |            |
                     v            v
              getAttributes()  getAttribute(name)
                     |            |
                     +------+-----+
                            |
                            v
                     Mapping kind là?
                     /      |       \
                  BASIC   EMBEDDED  RELATIONSHIP/
                     |      |       ELEMENT_COLLECTION
                     v      v          |
                 Singular Singular     v
                                   isCollection()?
                                    /         \
                                  Không       Có
                                   |           |
                                   v           v
                               Singular     Plural
                               to-one       CollectionType
                                             |
                                        +----+----+----+
                                        |    |    |    |
                                   Collection Set List Map
                                        |    |    |    |
                                        +----+----+----+
                                             |
                                             v
                                  getElementType()
                                   + Map.getKeyType()
                                             |
                                             v
                                Tạo Criteria/query/report
                                 với security allowlist
```

Điểm cần nhớ: “BASIC”, “SINGULAR” và “PLURAL” không phải ba loại loại trừ nhau. BASIC là **kind ánh xạ**, còn singular/plural nói về **cấu trúc giá trị attribute**.

---

## 49. Tổng kết

Những nguyên tắc quan trọng nhất:

1. **JPA Metamodel mô tả persistent model đã được provider nhận diện**, không đơn thuần là Java reflection.
2. **Basic attribute là mapping kind**, thường là singular nhưng không phải mọi singular attribute đều basic.
3. **SingularAttribute** bao gồm basic fields, embedded objects và to-one associations.
4. **PluralAttribute** bao gồm Collection, Set, List và Map, cho cả element collections và to-many entity associations.
5. **Attribute.getPersistentAttributeType()** cho biết BASIC, EMBEDDED, MANY_TO_ONE, ONE_TO_MANY, ELEMENT_COLLECTION...
6. **Type.getPersistenceType()** cho biết JPA kind của value/element type như BASIC, ENTITY hoặc EMBEDDABLE; không đồng nhất hai enums.
7. **getJavaType()** mô tả Java type của attribute/container; **getElementType()** mô tả element/value của plural attribute.
8. **MapAttribute.getKeyType()/getKeyJavaType()** cần dùng riêng cho map keys.
9. **getAttributes()** bao gồm inherited persistent attributes; **getDeclaredAttributes()** chỉ gồm những declarations của managed type đó.
10. **getAttribute/getSingularAttribute/getPluralAttribute/getList/getSet/getMap** cần được chọn đúng loại; tên/type không khớp có thể gây IllegalArgumentException.
11. **@Id/@Version** nên được tra qua `isId`/`isVersion` và `IdentifiableType`, không suy từ tên field.
12. **@Transient fields không thuộc persistent metamodel**, dù reflection vẫn nhìn thấy Java fields đó.
13. **Static metamodel** cải thiện type safety cho Criteria API; runtime metamodel phù hợp introspection và dynamic tools.
14. **Entity relationship joins khác scalar filters**; to-many joins có thể nhân rows và cần query design cẩn thận.
15. **JPA metamodel không phải physical schema API**, không cung cấp đầy đủ table names, column names, indexes, FK hoặc DDL constraints portable.
16. **Metadata-driven API vẫn phải có allowlist, tenant scoping và authorization**, không xuất toàn bộ entity model cho caller.
17. **Hãy ưu tiên JPA standard metadata trước provider internals**, trừ khi có nhu cầu cụ thể và chấp nhận dependency/version testing.

Khi tra cứu metadata trong JPA, hãy đặt đúng câu hỏi: **thuộc tính persistent đó đơn trị hay tập hợp, ánh xạ theo kiểu gì, và kiểu Java/JPA của value hoặc element là gì?** Ba chiều phân loại này giúp xây Criteria Query an toàn hơn, tránh nhầm lẫn giữa basic field và entity association, đồng thời xác định chính xác giới hạn của JPA Metamodel khi phân tích mô hình quan hệ.
