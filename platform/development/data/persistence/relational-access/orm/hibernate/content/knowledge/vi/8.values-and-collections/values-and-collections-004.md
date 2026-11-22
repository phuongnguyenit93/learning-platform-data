# `@ElementCollection` cho tập hợp giá trị không có danh tính thực thể riêng

Trong mô hình dữ liệu Hibernate/Jakarta Persistence, không phải mọi phần tử được lưu vào bảng riêng đều cần trở thành một `@Entity`. Một sản phẩm có nhiều thẻ tìm kiếm, khách hàng có nhiều địa chỉ giao hàng, tài liệu có danh sách từ khóa, hoặc một đối tượng có tập thông số `key → value`: những phần tử này thường **được nhận diện bằng giá trị và ngữ cảnh của đối tượng sở hữu**, không cần định danh entity riêng.

**`@ElementCollection`** là cơ chế chuẩn của Jakarta Persistence dành cho **tập hợp kiểu cơ bản (*basic type*) hoặc kiểu nhúng (*embeddable*)**. Hibernate, với vai trò persistence provider, ánh xạ tập hợp đó sang một **collection table**, liên kết các hàng bằng khóa ngoại tới entity sở hữu.

Bài học tập trung vào điều kiện dùng `@ElementCollection`, cấu trúc bảng, cách mapping `Set`, `List`, `Map`, `@Embeddable`, thứ tự và khóa map, vòng đời thao tác, lazy loading, hiệu năng và những dấu hiệu cho thấy nên dùng `@OneToMany` thay thế.

## 1. Ý nghĩa của “giá trị không có danh tính thực thể riêng”

Hãy so sánh hai khái niệm:

- **Entity:** có danh tính ổn định, thường là `@Id`; hai entity có thuộc tính giống nhau vẫn có thể là hai đối tượng nghiệp vụ khác nhau. Entity có thể được tìm, tham chiếu, cập nhật hay xóa độc lập.
- **Value:** được quan tâm chủ yếu qua các thuộc tính cấu thành. Hai giá trị có nội dung giống nhau thường được xem là tương đương; vòng đời của chúng gắn với entity chứa chúng.

Ví dụ:

```text
Product (entity)
  id = 42
  sku = "MOUSE-001"
  tags = {"wireless", "office", "ergonomic"}

"wireless" là một giá trị trong tập thẻ của Product 42.
Không cần một Tag entity với ID riêng chỉ để ghi nhận chuỗi này.
```

Một bảng quan hệ vẫn có thể cần thiết để lưu nhiều phần tử:

```text
products                           product_tags
+----+-----------+                 +------------+-----------+
| id | sku       |                 | product_id | tag       |
+----+-----------+                 +------------+-----------+
| 42 | MOUSE-001 |---------------> | 42         | wireless  |
|    |           |---------------> | 42         | office    |
|    |           |---------------> | 42         | ergonomic |
+----+-----------+                 +------------+-----------+
                                   FK tới products.id
```

**Có bảng riêng không đồng nghĩa có entity riêng.** `product_tags` là bảng lưu giá trị thuộc `Product`, còn chỉ có `Product` được định danh bằng `@Id` và có persistence context entry của entity. Những dòng thẻ không tự có `EntityManager.find(Tag.class, ...)`, vì chúng không phải entity `Tag`.

### 1.1. Tình huống phù hợp và không phù hợp

| Dữ liệu | `@ElementCollection` thường phù hợp? | Lý do |
| --- | --- | --- |
| `Set<String>` thẻ/từ khóa | Có | Chuỗi đơn giản, thuộc một entity |
| `List<String>` bước hướng dẫn ngắn | Có, nếu cần ánh xạ thứ tự | Phần tử là giá trị, thứ tự thuộc owner |
| `Set<Address>` địa chỉ kiểu `@Embeddable` | Có, nếu địa chỉ không có danh tính riêng | Lưu nhiều nhóm cột cho cùng owner |
| `Map<String, String>` thông số tùy chọn nhỏ | Có | Mỗi key/value thuộc owner |
| `List<OrderLine>` dòng hàng có ID, trạng thái, audit, quan hệ độc lập | Thường không | Cân nhắc `@OneToMany` với `OrderLine @Entity` |
| Danh mục `Tag` dùng chung giữa hàng triệu sản phẩm và có metadata riêng | Thường không | Cân nhắc `Tag @Entity` và bảng liên kết |
| Hàng triệu log sự kiện phải tìm/phân trang độc lập | Không nên | Nên mô hình hóa entity/bảng chuyên biệt |

Tiêu chí then chốt là **danh tính và vòng đời của phần tử**, không phải kích thước Java class hay việc SQL cần `JOIN`.

## 2. Cấu trúc annotation cơ bản

```java
@ElementCollection
@CollectionTable(
    name = "product_tags",
    joinColumns = @JoinColumn(name = "product_id")
)
@Column(name = "tag")
private Set<String> tags = new HashSet<>();
```

Bốn thành phần có nhiệm vụ khác nhau:

| Annotation | Vai trò |
| --- | --- |
| `@ElementCollection` | Đánh dấu collection của giá trị basic hoặc embeddable |
| `@CollectionTable` | Chỉ định bảng lưu giá trị của collection |
| `@JoinColumn` trong `@CollectionTable` | Chỉ định FK từ collection table về bảng entity sở hữu |
| `@Column` | Chỉ định cột chứa **giá trị basic** trong collection table |

Nếu phần tử là `@Embeddable`, các cột nội tại đến từ các field của embeddable; có thể dùng `@AttributeOverride` để thay tên hoặc đặc điểm cột.

`@ElementCollection` thuộc package `jakarta.persistence.*` của các phiên bản Jakarta Persistence hiện đại. Các ví dụ Java sau dùng **field access**: annotation mapping đặt trực tiếp trên field; nếu entity chọn property access thì đặt annotation tương ứng trên getter theo quy tắc truy cập JPA.

## 3. Ví dụ hoàn chỉnh: `Set<String>` thẻ sản phẩm

```java
import jakarta.persistence.CollectionTable;
import jakarta.persistence.Column;
import jakarta.persistence.ElementCollection;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.Table;

import java.util.Collections;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "sku", length = 80, nullable = false, unique = true)
    private String sku;

    @ElementCollection(fetch = FetchType.LAZY)
    @CollectionTable(
        name = "product_tags",
        joinColumns = @JoinColumn(name = "product_id")
    )
    @Column(name = "tag", nullable = false, length = 60)
    private Set<String> tags = new HashSet<>();

    protected Product() {
        // Constructor không tham số cho JPA.
    }

    public Product(String sku) {
        this.sku = Objects.requireNonNull(sku);
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public Set<String> getTags() {
        return Collections.unmodifiableSet(tags);
    }

    public void addTag(String tag) {
        String normalized = Objects.requireNonNull(tag).trim();
        if (normalized.isEmpty() || normalized.length() > 60) {
            throw new IllegalArgumentException("Invalid tag");
        }
        tags.add(normalized);
    }

    public void removeTag(String tag) {
        tags.remove(tag);
    }
}
```

Đáng chú ý:

1. `Product` là entity có `@Id`; từng `String` trong `tags` **không có** `@Id`.
2. `Set<String>` biểu diễn tập giá trị không trùng theo `String.equals()`.
3. `@CollectionTable` mô tả bảng liên kết owner–value.
4. `@Column(name = "tag")` định nghĩa cột chứa chuỗi; `@Column` ở đây **không** áp vào bảng `products`.
5. Getter chỉ cung cấp view không sửa được; thao tác thay đổi thông qua phương thức nghiệp vụ giúp chuẩn hóa dữ liệu. Hibernate vẫn thao tác trên field `tags` vì dùng field access.
6. Khởi tạo collection giúp object mới có tập rỗng thay vì `null`. Khi entity được quản lý, Hibernate có thể thay implementation collection bằng wrapper của provider.

Ví dụ DDL tương ứng trên PostgreSQL:

```sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(80) NOT NULL UNIQUE
);

CREATE TABLE product_tags (
    product_id BIGINT NOT NULL,
    tag VARCHAR(60) NOT NULL,

    CONSTRAINT pk_product_tags PRIMARY KEY (product_id, tag),
    CONSTRAINT fk_product_tags_product FOREIGN KEY (product_id)
        REFERENCES products(id)
);
```

Đây là **schema chủ động thiết kế**, không khẳng định Hibernate sẽ tự tạo đúng tên constraint và PK như trên ở mọi dialect. Khóa ghép `(product_id, tag)` bảo đảm một sản phẩm không có hai hàng lưu cùng một tag; nó phù hợp với ý nghĩa của `Set`. Trong hệ thống có phân biệt chữ hoa/chữ thường hoặc chuẩn hóa dấu/Unicode, cần kiểm tra quy tắc collation của database để bảo đảm nhất quán với Java.

### 3.1. Persist sản phẩm và các tag

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityTransaction;

EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    Product product = new Product("MOUSE-001");
    product.addTag("wireless");
    product.addTag("office");

    em.persist(product);

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
```

`emf` là `EntityManagerFactory` đã được cấu hình. Ví dụ sử dụng transaction **resource-local** trong Java SE; với Spring `@Transactional` hoặc môi trường JTA, transaction thường do hạ tầng quản lý.

SQL minh họa:

```sql
INSERT INTO products (sku) VALUES ('MOUSE-001');
-- DB sinh product ID = 42

INSERT INTO product_tags (product_id, tag)
VALUES (42, 'wireless');

INSERT INTO product_tags (product_id, tag)
VALUES (42, 'office');
```

Thứ tự statement thực tế, batching và thời điểm gán ID phụ thuộc strategy sinh khóa, flush mode và Hibernate version. Điều cần ghi nhớ là các giá trị được lưu **theo vòng đời entity sở hữu**, không cần `em.persist("wireless")`.

## 4. Quy ước ánh xạ mặc định và vì sao nên đặt tên rõ ràng

Jakarta Persistence có quy tắc suy ra tên collection table, join column và value column nếu bỏ các annotation cấu hình chi tiết. Tuy nhiên tên DDL tạo ra có thể còn chịu ảnh hưởng **physical naming strategy** của Hibernate/framework.

Ví dụ rút gọn:

```java
@ElementCollection
private Set<String> tags = new HashSet<>();
```

Provider có thể suy tên bảng theo entity và tên thuộc tính, suy cột nối từ primary key của owner và cột chứa giá trị từ `tags`. Nhưng khi cơ sở dữ liệu phải được migration bằng Flyway/Liquibase hoặc dùng chung với ứng dụng khác, **đừng đoán tên cột**. Hãy khai báo tường minh:

```java
@ElementCollection
@CollectionTable(
    name = "product_tags",
    joinColumns = @JoinColumn(name = "product_id")
)
@Column(name = "tag", length = 60)
private Set<String> tags = new HashSet<>();
```

Với composite primary key của entity sở hữu, `@CollectionTable` có thể cần **nhiều `@JoinColumn`**; các cột FK trong collection table phải tham chiếu đúng các thành phần khóa owner. Đừng dùng một `JoinColumn` giả định owner luôn có duy nhất một ID kiểu `Long`.

## 5. Tập hợp `@Embeddable`: mỗi phần tử gồm nhiều giá trị

Một địa chỉ giao hàng có thể bao gồm `street`, `city`, `postalCode` nhưng không nhất thiết có một `address_id` hay lifecycle riêng. Đó là trường hợp của **`@Embeddable` trong `@ElementCollection`**.

### 5.1. Value type `PostalAddress`

```java
import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

import java.util.Objects;

@Embeddable
public class PostalAddress {

    @Column(name = "street", length = 160, nullable = false)
    private String street;

    @Column(name = "city", length = 80, nullable = false)
    private String city;

    @Column(name = "postal_code", length = 20, nullable = false)
    private String postalCode;

    protected PostalAddress() {
    }

    public PostalAddress(String street, String city, String postalCode) {
        this.street = Objects.requireNonNull(street);
        this.city = Objects.requireNonNull(city);
        this.postalCode = Objects.requireNonNull(postalCode);
    }

    public String getStreet() {
        return street;
    }

    public String getCity() {
        return city;
    }

    public String getPostalCode() {
        return postalCode;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof PostalAddress that)) return false;
        return street.equals(that.street)
            && city.equals(that.city)
            && postalCode.equals(that.postalCode);
    }

    @Override
    public int hashCode() {
        return Objects.hash(street, city, postalCode);
    }
}
```

Đây là object giá trị, vì vậy `equals()`/`hashCode()` so sánh theo các thành phần cấu thành. Không có `@Entity` hoặc `@Id` bên trong. Các giá trị được đặt lúc khởi tạo và không công khai setter nhằm giảm nguy cơ sửa object đã nằm trong `Set`.

### 5.2. Owner lưu nhiều địa chỉ

```java
import jakarta.persistence.CollectionTable;
import jakarta.persistence.ElementCollection;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.Table;

import java.util.Collections;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ElementCollection(fetch = FetchType.LAZY)
    @CollectionTable(
        name = "customer_addresses",
        joinColumns = @JoinColumn(name = "customer_id")
    )
    private Set<PostalAddress> addresses = new HashSet<>();

    protected Customer() {
    }

    public Set<PostalAddress> getAddresses() {
        return Collections.unmodifiableSet(addresses);
    }

    public void addAddress(PostalAddress address) {
        addresses.add(Objects.requireNonNull(address));
    }

    public void removeAddress(PostalAddress address) {
        addresses.remove(address);
    }
}
```

`PostalAddress` được lưu dưới dạng **các cột** trong bảng collection:

```sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY
);

CREATE TABLE customer_addresses (
    customer_id BIGINT NOT NULL,
    street VARCHAR(160) NOT NULL,
    city VARCHAR(80) NOT NULL,
    postal_code VARCHAR(20) NOT NULL,
    CONSTRAINT fk_customer_addresses_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
);
```

Một địa chỉ không tồn tại như một JPA entity độc lập. Khi khách hàng bị xóa theo cơ chế entity lifecycle thông thường, Hibernate sẽ đồng bộ việc loại bỏ các giá trị thuộc collection; tùy cấu hình database, FK cũng có thể khai báo `ON DELETE CASCADE`.

### 5.3. `@AttributeOverride` khi cần tên cột khác

Nếu cùng `PostalAddress` được sử dụng ở nhiều nơi, tên cột có thể khác:

```java
@ElementCollection
@CollectionTable(
    name = "customer_delivery_points",
    joinColumns = @JoinColumn(name = "customer_id")
)
@AttributeOverrides({
    @AttributeOverride(
        name = "street",
        column = @Column(name = "delivery_street", length = 160, nullable = false)
    ),
    @AttributeOverride(
        name = "city",
        column = @Column(name = "delivery_city", length = 80, nullable = false)
    ),
    @AttributeOverride(
        name = "postalCode",
        column = @Column(name = "delivery_postal_code", length = 20, nullable = false)
    )
})
private Set<PostalAddress> deliveryPoints = new HashSet<>();
```

`@AttributeOverride(name = "postalCode")` dùng **tên thuộc tính Java của embeddable**, không phải `postal_code` từ schema. Cột được ghi trong `@Column(name=...)` là tên SQL. Như vậy cùng một value type có thể được tái sử dụng với bảng/cột khác nhau mà không biến nó thành entity.

## 6. `Set`, `List`, `Collection`, `Map` khác nhau ra sao?

`@ElementCollection` có thể dùng với các interface collection được hỗ trợ trong JPA: `Collection`, `Set`, `List`, `Map`. **Chọn interface theo ngữ nghĩa nghiệp vụ**, vì nó ảnh hưởng tới duplicate, thứ tự, khóa và cách Hibernate lưu cập nhật.

| Java type | Ngữ nghĩa ứng dụng | Lưu ý khi persist |
| --- | --- | --- |
| `Set<E>` | Không cho phần tử trùng theo `equals()`/`hashCode()` | Equality ổn định; xem xét UNIQUE ở DB |
| `List<E>` | Có thứ tự trong Java, có thể có giá trị lặp | Muốn thứ tự được lưu bền vững, dùng `@OrderColumn` hoặc quy tắc sắp xếp phù hợp |
| `Collection<E>` | Không cam kết duy nhất hoặc vị trí | Hibernate có thể dùng bag semantics tùy mapping |
| `Map<K,V>` | Mỗi key tương ứng một value | Cấu hình cột key bằng `@MapKeyColumn` hoặc mapping key phù hợp |

JPA thường cho phép dùng `HashSet`, `ArrayList`, `HashMap` để **khởi tạo trước khi entity được quản lý**, nhưng field persistent nên khai báo qua interface (`Set`, `List`, `Map`). Hibernate thường thay collection bằng implementation riêng để phát hiện thay đổi và thực hiện lazy loading.

### 6.1. Không phải `Set` tự tạo UNIQUE ở database

Trong bộ nhớ Java:

```java
Set<String> tags = new HashSet<>();
tags.add("office");
tags.add("office");

System.out.println(tags.size()); // 1
```

Nhưng bảng SQL chỉ ngăn duplicate theo **ràng buộc thực sự có trên database**. Nếu dữ liệu có thể được ghi qua script hoặc ứng dụng khác, cần PK/UNIQUE phù hợp, ví dụ `(product_id, tag)`. Collation, khoảng trắng, chữ hoa/thường có thể khiến định nghĩa trùng của database khác Java; chuẩn hóa và thiết kế constraint theo một quy tắc thống nhất.

## 7. `List` và thứ tự: `@OrderColumn` so với `@OrderBy`

Một lỗi phổ biến là thấy `List<String>` rồi mặc định cho rằng **vị trí phần tử luôn được giữ sau khi reload**. Với Hibernate, một `List` không có cột index có thể được quản lý theo kiểu bag; database relation bản chất **không có thứ tự tự nhiên**. Khi nghiệp vụ cần vị trí rõ ràng, hãy khai báo.

### 7.1. `@OrderColumn`: lưu vị trí của từng phần tử

```java
@ElementCollection
@CollectionTable(
    name = "recipe_steps",
    joinColumns = @JoinColumn(name = "recipe_id")
)
@OrderColumn(name = "step_position")
@Column(name = "instruction", length = 300, nullable = false)
private List<String> steps = new ArrayList<>();
```

Bảng tương ứng:

```sql
CREATE TABLE recipe_steps (
    recipe_id BIGINT NOT NULL,
    step_position INTEGER NOT NULL,
    instruction VARCHAR(300) NOT NULL,
    PRIMARY KEY (recipe_id, step_position),
    FOREIGN KEY (recipe_id) REFERENCES recipes(id)
);
```

Dữ liệu minh họa:

| `recipe_id` | `step_position` | `instruction` |
| ---: | ---: | --- |
| 9 | 0 | Rửa nguyên liệu |
| 9 | 1 | Cắt thành miếng |
| 9 | 2 | Nấu trong 10 phút |

`@OrderColumn` là một **cột quản lý bởi persistence provider**; mặc định vị trí bắt đầu từ `0`, theo thứ tự liên tục. Nó không phải field của object `String`. Khi thêm/xóa ở giữa `List`, Hibernate có thể phải cập nhật vị trí nhiều hàng. Đây là chi phí đổi lấy **thứ tự bền vững theo index**.

```java
steps.add(1, "Đun nóng chảo");
```

Sau thao tác này, Hibernate cần đồng bộ lại vị trí của các bước đứng sau. Không nên dùng danh sách cực dài và reorder liên tục nếu từng thay đổi gây nhiều SQL.

### 7.2. `@OrderBy`: sắp xếp theo một thuộc tính đã lưu

Với `@Embeddable`, có thể muốn sắp xếp địa chỉ theo thành phố:

```java
@ElementCollection
@CollectionTable(
    name = "customer_addresses",
    joinColumns = @JoinColumn(name = "customer_id")
)
@OrderBy("city ASC, street ASC")
private List<PostalAddress> addresses = new ArrayList<>();
```

`@OrderBy` yêu cầu **sắp xếp theo giá trị thuộc tính** khi truy xuất. Nó không duy trì một cột vị trí theo thao tác kéo-thả hoặc `list.add(index, ...)`. Nếu thành phố thay đổi, thứ tự khi đọc lại có thể khác.

| Tiêu chí | `@OrderColumn` | `@OrderBy` |
| --- | --- | --- |
| Dùng cho | Thứ tự vị trí nghiệp vụ xác định bằng index | Thứ tự suy ra từ giá trị đã có |
| Cột bổ sung | Có, ví dụ `step_position` | Không bắt buộc |
| Tự cập nhật khi chuyển phần tử | Có, provider giữ thứ tự | Không giữ “thứ tự kéo thả”; sort lại theo giá trị |
| Ví dụ | Các bước của công thức, ưu tiên danh sách | Địa chỉ theo thành phố, nhãn theo alphabet |

Theo đặc tả, **không nên kết hợp `@OrderBy` với `@OrderColumn` trên cùng collection**. Cũng cần phân biệt `@OrderBy` của JPA với các annotation ordering riêng của Hibernate.

### 7.3. Bag và giá trị lặp

`List<String>` có thể chứa:

```text
["repeat", "repeat", "finish"]
```

Nếu không có index hoặc khóa hàng riêng, hai chuỗi `"repeat"` tương đương nhau tại DB và provider có thể không xác định được chính xác một hàng cần xóa. Với bag semantics, Hibernate có thể xử lý thay đổi bằng cách xóa nhiều hoặc toàn bộ hàng của collection rồi chèn lại. Nếu có `@OrderColumn`, mỗi phần tử được phân biệt qua vị trí; nhưng thêm/xóa ở giữa lại phát sinh công việc cập nhật các index liên quan.

Chọn `Set` nếu phần tử thực sự không trùng; chọn `List` có `@OrderColumn` nếu cần thứ tự; còn nếu mỗi dòng cần được cập nhật độc lập với ID ổn định, cân nhắc `@Entity`.

## 8. `Map<String, String>` và `@MapKeyColumn`

Một bộ thông số của sản phẩm có thể là:

```text
{
  "color": "black",
  "connection": "bluetooth",
  "warranty": "12 months"
}
```

Đây là các cặp giá trị thuộc sản phẩm, không nhất thiết là entity độc lập.

```java
@ElementCollection
@CollectionTable(
    name = "product_properties",
    joinColumns = @JoinColumn(name = "product_id")
)
@MapKeyColumn(name = "property_key", length = 80)
@Column(name = "property_value", length = 200)
private Map<String, String> properties = new HashMap<>();
```

Bảng mẫu:

```sql
CREATE TABLE product_properties (
    product_id BIGINT NOT NULL,
    property_key VARCHAR(80) NOT NULL,
    property_value VARCHAR(200),
    PRIMARY KEY (product_id, property_key),
    FOREIGN KEY (product_id) REFERENCES products(id)
);
```

Ở đây:

- `product_id` là FK tới entity sở hữu.
- `property_key` chứa **key** của `Map`.
- `property_value` chứa **value** của `Map`.
- `(product_id, property_key)` là khóa ghép thiết kế theo tính duy nhất của key trong một map thuộc một product.

Thao tác:

```java
product.getProperties().put("color", "black");
product.getProperties().put("color", "white"); // Thay value của cùng key.
product.getProperties().remove("warranty");
```

Trong entity production, nên cung cấp method `setProperty()`/`removeProperty()` thay vì trả trực tiếp map có thể sửa tùy ý; ví dụ trên chỉ minh họa ngữ nghĩa Java `Map`.

### 8.1. Map key không phải entity ID

`@MapKeyColumn` xác định cột key của map kiểu basic; nó không tạo entity `Property` độc lập. Một phần tử có thể được nhận diện trong bảng bằng `(owner_id, property_key)`, nhưng đó là **khóa hàng ở database**, không đồng nghĩa với có `@Id`, `EntityManager.find(Property.class, ...)` hoặc lifecycle entity riêng.

### 8.2. Map có value là `@Embeddable`

```java
@ElementCollection
@CollectionTable(
    name = "shop_contact_by_locale",
    joinColumns = @JoinColumn(name = "shop_id")
)
@MapKeyColumn(name = "locale_tag", length = 15)
@AttributeOverrides({
    @AttributeOverride(
        name = "phone",
        column = @Column(name = "phone_number", length = 30)
    ),
    @AttributeOverride(
        name = "email",
        column = @Column(name = "email_address", length = 150)
    )
})
private Map<String, ContactInfo> contactByLocale = new HashMap<>();
```

`ContactInfo` ở đây được giả định là `@Embeddable` có hai thuộc tính `phone`, `email`. Khi value là embeddable, các cột value được lấy từ mapping của lớp đó, còn key `"vi-VN"`, `"en-US"` nằm ở `locale_tag`.

Jakarta Persistence xác định việc dùng **`@ElementCollection` hay `@OneToMany`/`@ManyToMany` cho Map chủ yếu theo kiểu value của map**: value là basic/embeddable thì có thể dùng `@ElementCollection`; value là entity thì dùng mapping quan hệ entity tương ứng.

## 9. Enum và các kiểu basic khác

Tập hợp enum thường thích hợp làm element collection:

```java
public enum SupportedChannel {
    EMAIL, SMS, PUSH
}
```

```java
@ElementCollection
@CollectionTable(
    name = "notification_channels",
    joinColumns = @JoinColumn(name = "preference_id")
)
@Enumerated(EnumType.STRING)
@Column(name = "channel", nullable = false, length = 20)
private Set<SupportedChannel> channels =
    EnumSet.noneOf(SupportedChannel.class);
```

Trong entity mới, `EnumSet` có thể là cấu trúc Java phù hợp; sau khi Hibernate quản lý entity, provider có thể dùng collection wrapper của nó. Nếu muốn tránh giả định về implementation, khởi tạo `new HashSet<>()` cũng được.

`EnumType.STRING` lưu tên hằng enum như `"EMAIL"`. Tránh `EnumType.ORDINAL` trong dữ liệu bền vững nếu việc chèn/sắp xếp lại hằng enum có thể khiến dữ liệu cũ bị hiểu thành giá trị khác. Khi cần tương thích ngược nghiêm ngặt, dùng mã ổn định và converter/schema theo chính sách của hệ thống.

Các basic type khác có thể được lưu qua mapping tương ứng, ví dụ `Integer`, `BigDecimal`, `LocalDate`, `UUID` hoặc kiểu được hỗ trợ thông qua converter. Phải chọn JDBC/SQL type và precision/scale phù hợp với dữ liệu; đặc biệt **không mặc định `double` cho số tiền**.

### 9.1. `AttributeConverter` trong element collection

Nếu một kiểu giá trị được biểu diễn trong database bằng dạng scalar, có thể dùng `AttributeConverter<X, Y>` hoặc `@Convert` tùy mapping. Điều này **không biến mỗi phần tử thành entity**; chỉ thay cách chuyển đổi giữa kiểu Java và cột SQL. Tránh viết converter mà toàn bộ collection bị serialize thành một chuỗi rồi mong Hibernate vẫn truy vấn được từng phần tử như collection table: đó là một mô hình lưu trữ khác.

## 10. Vòng đời dữ liệu: owner quản lý các phần tử

`@ElementCollection` không có thuộc tính `cascade` hay `orphanRemoval` như một quan hệ entity. Nó là tập giá trị **thuộc owner**; việc thêm/xóa giá trị được đồng bộ cùng lifecycle của entity khi owner đang managed.

Ví dụ cập nhật sản phẩm:

```java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    Product product = em.find(Product.class, 42L);
    if (product == null) {
        throw new IllegalArgumentException("Product not found");
    }

    product.addTag("sale");
    product.removeTag("office");

    tx.commit(); // Hibernate theo dõi thay đổi collection và flush.
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
```

Kết quả logic:

```text
Trước: {"wireless", "office"}
Sau:   {"wireless", "sale"}
```

Hibernate có thể phát các SQL như:

```sql
DELETE FROM product_tags
WHERE product_id = 42 AND tag = 'office';

INSERT INTO product_tags(product_id, tag)
VALUES (42, 'sale');
```

**SQL trên chỉ là mô hình dễ hiểu**, không bảo đảm Hibernate luôn phát đúng hai statement. Tùy loại collection, khả năng xác định hàng, database constraint và phiên bản, Hibernate có thể xóa/chèn lại nhiều hàng để đồng bộ thay đổi.

### 10.1. Xóa một phần tử

```java
product.removeTag("wireless");
```

Không cần `EntityManager.remove(tag)`; `"wireless"` là `String`, không phải entity.

### 10.2. Xóa owner

```java
em.remove(product);
```

Trong vòng đời remove entity thông thường, Hibernate xử lý dữ liệu collection thuộc owner để không còn các hàng con mồ côi trước/sau lệnh xóa owner tùy kế hoạch SQL, constraint và cấu hình. Có thể dùng foreign key `ON DELETE CASCADE` ở database theo yêu cầu, nhưng **đừng giả định Hibernate DDL mặc định luôn tạo `ON DELETE CASCADE`**.

**Bulk JPQL delete hoặc native SQL delete** là trường hợp khác với `em.remove(entity)`: các cơ chế này có thể bỏ qua lifecycle đồng bộ collection của persistence context, dẫn đến vi phạm FK nếu schema không có cơ chế phù hợp. Cần kiểm tra hành vi cụ thể khi dùng bulk operations.

### 10.3. Thay toàn bộ collection

Với entity managed, thay field bằng `new HashSet<>()` tùy ý có thể làm Hibernate bỏ wrapper đang theo dõi hoặc gây nhiều SQL. Thường nên cung cấp method thay nội dung trong collection hiện có:

```java
public void replaceTags(Set<String> newTags) {
    Objects.requireNonNull(newTags);
    tags.clear();
    for (String tag : newTags) {
        addTag(tag);
    }
}
```

Cách này thể hiện mục tiêu nghiệp vụ và giữ collection field đang được provider theo dõi. **Không có nghĩa `clear() + addAll()` luôn tối ưu SQL**; nếu collection lớn, phải đo chi phí và cân nhắc mô hình dữ liệu khác.

## 11. Mutable embeddable, `Set` và equality

Một `Set<PostalAddress>` cần equality ổn định. Nếu chỉnh sửa field tham gia `equals/hashCode` **sau khi phần tử đã nằm trong `HashSet`**, có thể làm `remove()` hoặc `contains()` hoạt động bất ngờ.

Ví dụ nguy hiểm:

```text
Address ban đầu: city="Da Nang", street="A"
Được thêm vào HashSet, hashCode dựa trên city+street

Sau đó sửa trực tiếp city="Hue"
→ hashCode thay đổi trong khi object vẫn nằm ở bucket cũ
→ HashSet có thể không tìm lại được bằng contains/remove
```

Đối với collection value:

- Ưu tiên **bất biến từ phía API nghiệp vụ**: constructor đặt giá trị, không public setter tùy ý.
- Nếu cần đổi nội dung một phần tử trong `Set`, cân nhắc **xóa giá trị cũ rồi thêm giá trị mới**.
- Viết `equals()`/`hashCode()` theo tất cả thuộc tính tạo nên giá trị; cẩn thận `BigDecimal` vì `equals()` còn xét scale.
- Chọn cách chuẩn hóa chuỗi nhất quán (trim, case, Unicode) nếu domain coi hai chuỗi khác biểu diễn là cùng một giá trị.

Việc dùng `@Embeddable` không tự làm class bất biến. Provider vẫn cần khả năng khởi tạo/đọc ghi theo mô hình access; thiết kế giá trị bất biến ở API ứng dụng cần tương thích với yêu cầu ORM.

## 12. Fetch: `@ElementCollection` mặc định LAZY

`@ElementCollection` có `fetch` mặc định là **`FetchType.LAZY`**. Theo Jakarta Persistence, LAZY là **hint** với provider, còn EAGER yêu cầu collection được lấy sớm; vì vậy vẫn cần quan sát hành vi thực của Hibernate.

```java
@ElementCollection(fetch = FetchType.LAZY)
private Set<String> tags;
```

Một truy vấn:

```java
Product product = em.find(Product.class, 42L);
```

không nhất thiết tải `tags` ngay. Khi code truy cập:

```java
product.getTags().size();
```

Hibernate có thể cần phát SQL đọc bảng `product_tags`, nếu collection chưa được khởi tạo và không có tối ưu phù hợp.

### 12.1. LazyInitializationException

```java
Product product;

EntityManager em = emf.createEntityManager();
try {
    product = em.find(Product.class, 42L);
} finally {
    em.close();
}

// Collection chưa được khởi tạo trong persistence context.
System.out.println(product.getTags().size());
```

Khi `tags` thực sự còn lazy và session đã đóng, Hibernate có thể ném `LazyInitializationException`. Cách xử lý là **xác định trước dữ liệu cần trả và tải nó trong phạm vi persistence context/transaction thích hợp**; không mở session dài qua tầng web chỉ để tránh lỗi.

### 12.2. JPQL `JOIN FETCH` có chủ đích

```java
Product product = em.createQuery(
        "select distinct p from Product p " +
        "left join fetch p.tags where p.id = :id",
        Product.class
    )
    .setParameter("id", 42L)
    .getSingleResult();
```

Query này yêu cầu tải `tags` cùng owner. `distinct` mô tả mong muốn kết quả entity không trùng; mức độ Hibernate loại trùng hay đẩy `DISTINCT` xuống SQL tùy phiên bản/provider.

Nếu cần **nhiều collection** cùng lúc, join fetch có thể gây nhân số hàng (*cartesian product*), tăng dữ liệu truyền và đôi khi vướng `MultipleBagFetchException` với nhiều bag trong Hibernate. Tránh join-fetch mọi collection theo thói quen; chọn fetch plan theo từng use case.

### 12.3. Query theo phần tử

Tìm sản phẩm có tag `"wireless"`:

```java
List<Product> products = em.createQuery(
        "select distinct p from Product p join p.tags t " +
        "where t = :tag",
        Product.class
    )
    .setParameter("tag", "wireless")
    .getResultList();
```

Hoặc dùng toán tử `MEMBER OF` của JPQL:

```java
List<Product> products = em.createQuery(
        "select p from Product p where :tag member of p.tags",
        Product.class
    )
    .setParameter("tag", "wireless")
    .getResultList();
```

Có thể **lọc theo giá trị collection** mà không cần biến các tag thành entity. Tuy nhiên với những truy vấn analytics lớn, index/cost vẫn do database quyết định.

### 12.4. EntityGraph và batch fetching

Các cơ chế như `EntityGraph` hoặc fetch profile của provider có thể giúp chọn collection cần load theo use case. Hibernate còn có các tối ưu đặc thù như `@BatchSize` hoặc `@Fetch(FetchMode.SUBSELECT)` trong những tình huống phù hợp. Đây là **tối ưu của provider**, không phải thuộc tính bắt buộc của `@ElementCollection`; cần đo số SQL, tổng row và thời gian thực thi trước khi sử dụng.

## 13. Hiệu năng UPDATE/DELETE: tập hợp giá trị có cái giá riêng

Các phần tử `@ElementCollection` **không có entity ID riêng**. Hibernate phải định vị hàng cần sửa dựa vào owner và giá trị, cột index hoặc map key có sẵn. Điều này quyết định chiến lược SQL khi cập nhật.

### 13.1. Set với giá trị có thể định vị duy nhất

Ví dụ `Set<String>` và database có PK `(product_id, tag)`:

```text
Trước: {A, B, C}
Sau:   {A, C, D}
```

Có thể đồng bộ bằng:

```sql
DELETE FROM product_tags WHERE product_id = ? AND tag = 'B';
INSERT INTO product_tags(product_id, tag) VALUES (?, 'D');
```

Chiến lược thực tế có thể khác, nhưng khóa ghép giúp database định vị hàng chính xác. Nếu giá trị `@Embeddable` có nhiều cột, SQL để định vị một phần tử có thể phức tạp hơn.

### 13.2. Bag không có khóa hàng ổn định

Ví dụ `List<String>` không `@OrderColumn` chứa giá trị trùng. Khi xóa một phần tử, provider có thể không biết **hàng vật lý nào** là phần tử bị xóa; Hibernate thường có chiến lược **xóa toàn bộ các hàng thuộc collection rồi insert lại các phần tử còn lại** trong nhiều trường hợp bag/element collection.

Điều này dễ gây vấn đề nếu:

- Collection có hàng nghìn/hàng triệu phần tử.
- Người dùng sửa một phần tử rất thường xuyên.
- Database có trigger/audit theo hàng.
- Bảng bị khóa hoặc phát nhiều WAL/binlog vì các đợt delete/insert lại.

Cải thiện có thể đến từ thay đổi mô hình collection, thêm index theo vị trí, hoặc biến phần tử thành `@Entity` nếu thực sự cần lifecycle và PK riêng. Không thể khẳng định một annotation sẽ làm mọi câu SQL cập nhật trở thành một dòng; **xem SQL Hibernate tạo ra với workload thực tế**.

### 13.3. `@OrderColumn` vẫn cần cập nhật khi reorder

Với danh sách 100 bước đánh số `0..99`, chèn một bước vào vị trí `2` có thể cần dịch nhiều index. Thêm vào cuối danh sách thường nhẹ hơn so với chèn/xóa ở đầu hoặc giữa. Nếu nghiệp vụ liên tục kéo thả danh sách dài, cân nhắc entity con có `sortOrder` riêng và một chiến lược đánh số phù hợp.

### 13.4. Index dữ liệu

Cấu trúc:

```sql
CREATE INDEX idx_product_tags_tag
ON product_tags(tag);
```

có thể hữu ích cho câu truy vấn “tìm mọi sản phẩm có tag X”. Trong khi PK `(product_id, tag)` thường thuận tiện cho câu “tải tag của một product”. Lựa chọn index theo access pattern, volume và execution plan; tránh thêm index chỉ vì nhìn thấy một trường trong `@ElementCollection`.

## 14. Transaction, dirty checking và detached entity

Khi owner đang **managed**, Hibernate có thể theo dõi collection qua persistent wrapper và đồng bộ thay đổi khi `flush()`/`commit()`:

```java
Product product = em.find(Product.class, 42L);
product.addTag("new");
em.flush(); // Đồng bộ các thay đổi đang chờ, chưa nhất thiết commit.
```

Trong transaction resource-local, `flush()` không đồng nghĩa `commit()`: nếu sau đó rollback, thao tác ghi có thể bị hoàn tác.

### 14.1. Detached state

Sau `em.close()` hoặc `em.detach(product)`, owner không còn managed. Thay đổi `product`/collection trong trạng thái detached **không tự động phát SQL**. `merge()` có thể đưa trạng thái vào một managed instance mới:

```java
Product managed = em.merge(detachedProduct);
```

`merge()` trả về **managed instance**; đối tượng được truyền vào vẫn detached. Với collection, merge có thể phải đọc/so sánh trạng thái và phát nhiều SQL. Cần cân nhắc dữ liệu hiện thời: một DTO gửi thiếu collection không nên vô tình bị hiểu là “xóa hết giá trị”.

Cách cập nhật đáng tin cậy với request chỉ sửa tag thường là tải owner trong transaction rồi áp dụng **delta có chủ đích** (`addTag`/`removeTag`) trên managed instance. Điều này cũng tránh việc người dùng cũ ghi đè toàn bộ collection mới của người dùng khác.

### 14.2. Optimistic locking

Nếu owner có:

```java
@Version
private long version;
```

Hibernate có thể đưa các thay đổi collection do owner quản lý vào cơ chế tăng version để phát hiện xung đột. Nhưng hành vi chi tiết phụ thuộc mapping, khả năng ownership và những thao tác đi qua persistence context. **Native SQL và bulk JPQL updates** có thể bỏ qua cơ chế version thông thường. Khi cần ngăn hai request ghi đè collection, thiết kế optimistic locking và kiểm thử đúng đường cập nhật, không chỉ dựa vào việc có `@Version`.

## 15. Ràng buộc trong `@Embeddable` dùng trong element collection

Jakarta Persistence hỗ trợ những kiểu nhúng có giá trị basic và embedded lồng nhau, nhưng đặt **hạn chế cấu trúc** đối với embeddable nằm trong element collection.

Theo Jakarta Persistence 3.2:

- Một `@Embeddable` nằm trong element collection **không được chứa `@ElementCollection` khác**.
- Nó **không được chứa quan hệ `@OneToMany` hoặc `@ManyToMany`**.
- Một số quan hệ `@ManyToOne` hoặc `@OneToOne` từ embeddable tới entity có thể được hỗ trợ nếu embeddable là **phía sở hữu** và quan hệ được ánh xạ bằng foreign key theo đặc tả.

Vì vậy, ví dụ:

```java
@Embeddable
class CatalogBundle {
    @ElementCollection
    private Set<String> options; // Không hợp lệ trong embeddable
                                 // đang là phần tử của element collection.
}
```

không phải mô hình JPA portable cho một collection lồng trong collection. Nếu cần nhiều cấp children với lifecycle và truy vấn riêng, nên thiết kế entity trung gian và quan hệ entity rõ ràng.

`@Embeddable` có thể dùng lại ở thuộc tính đơn:

```java
@Embedded
private PostalAddress billingAddress;
```

hoặc trong tập:

```java
@ElementCollection
private Set<PostalAddress> deliveryAddresses;
```

Sự khác biệt là **một giá trị thuộc owner** so với **nhiều giá trị thuộc owner**, không phải cấp độ “entity hơn” của embeddable.

## 16. Khi nào thay bằng `@OneToMany`?

Đừng dùng `@ElementCollection` nếu phần tử đã có **định danh nghiệp vụ ổn định và cần thao tác độc lập**.

Ví dụ, một `OrderLine` chứa:

```text
lineId
orderId
sku
quantity
unitPrice
deliveryStatus
createdAt
updatedAt
```

Nếu mỗi line cần được cập nhật trạng thái giao hàng, audit riêng, nhận event riêng, được nhiều bảng tham chiếu hoặc phân trang độc lập, nên cân nhắc:

```java
@Entity
public class OrderLine {
    @Id
    @GeneratedValue
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    private PurchaseOrder order;

    // quantity, unitPrice, status...
}
```

và trên `PurchaseOrder` (nếu cần quan hệ hai chiều):

```java
@OneToMany(mappedBy = "order")
private List<OrderLine> lines = new ArrayList<>();
```

So sánh:

| Tiêu chí | `@ElementCollection` | `@OneToMany` với entity con |
| --- | --- | --- |
| Phần tử có `@Id` riêng | Không | Có |
| Có thể `EntityManager.find()` từng phần tử | Không | Có |
| Vòng đời độc lập | Phụ thuộc owner | Có thể độc lập theo thiết kế |
| Các hàng lưu ở đâu | Collection table | Bảng entity con |
| Cập nhật một phần tử theo ID | Không có entity ID để định vị | Thuận tiện qua PK |
| Trạng thái/version riêng của từng phần tử | Không | Có thể có |
| Chi phí mapping | Thường đơn giản | Nhiều mapping và lifecycle hơn |
| Phù hợp | Tags, labels, address value, thông số nhỏ | Order lines, comments, trạng thái/workflow riêng |

Không phải cứ có yêu cầu audit một cột là bắt buộc tạo entity, nhưng nếu **tính độc lập của phần tử** ngày càng lớn, `@ElementCollection` có thể khiến SQL cập nhật và domain khó quản lý.

## 17. `@ElementCollection` so với JSON column và chuỗi phân cách

Với dữ liệu nhỏ, đôi khi có ba cách lưu:

1. **Collection table:** nhiều hàng liên kết owner bằng FK, mapping `@ElementCollection`.
2. **JSON column:** một cột JSON chứa array/object, cần mapping JSON phù hợp với provider/database.
3. **Chuỗi phân cách:** một cột VARCHAR chứa `"a,b,c"`.

### 17.1. Collection table

Ưu điểm: dùng cấu trúc quan hệ rõ ràng, có thể index từng giá trị, join/filter bằng SQL, quản lý constraint. Nhược điểm: cần thêm bảng và có thể nhiều statement khi cập nhật.

### 17.2. JSON column

Ưu điểm: lưu một cấu trúc document trong cùng hàng owner, thuận tiện với dữ liệu cấu hình lồng nhau. Nhược điểm: khả năng query/index/constraint và hành vi update phụ thuộc mạnh vào DBMS/provider, có thể phải ghi lại toàn bộ JSON. Đây **không phải** mapping `@ElementCollection` chuẩn nếu dữ liệu được đặt trong **một cột JSON**.

### 17.3. Chuỗi phân cách

Dễ bắt đầu nhưng khó truy vấn chính xác khi giá trị chứa dấu phân cách, khó kiểm tra uniqueness, null, escaping và migration. Không nên chọn làm thiết kế mặc định cho dữ liệu cần truy vấn và cập nhật từng phần tử.

Lựa chọn dựa trên **kiểu truy vấn, vòng đời, schema và chi phí cập nhật**; dữ liệu là “value type” không có nghĩa chỉ được phép dùng một kỹ thuật lưu.

## 18. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách tiếp cận |
| --- | --- | --- |
| `@ElementCollection` trên `List<MyEntity>` | Phần tử là entity chứ không phải basic/embeddable | Dùng `@OneToMany`/`@ManyToMany` đúng quan hệ |
| Gọi `em.persist(tagString)` | Tưởng từng phần tử value là entity | Thêm vào collection của owner đang managed |
| `LazyInitializationException` khi đọc tags ở controller | Session/transaction đã đóng trước khi initialize collection | Load theo fetch plan/use case trong transaction |
| `List` bị đổi thứ tự sau khi reload | Không có `@OrderColumn`/sort bảo đảm | Chọn thứ tự index hay theo giá trị và map đúng |
| Xóa một value mà Hibernate xóa/chèn lại nhiều hàng | Bag/element collection thiếu row identity ổn định | Kiểm tra SQL, chọn Set/index/entity khi phù hợp |
| Hai `PostalAddress` giống nhau cùng xuất hiện | Dùng `List`, hoặc `equals/hashCode` của `Set` sai | Định nghĩa uniqueness và equality theo domain |
| `Set.remove(address)` không tìm thấy | Embeddable mutable đã đổi field tham gia hash | Value bất biến hoặc remove/add thay vì mutation |
| Column ở sai bảng hoặc sai tên | Nhầm `@Column` với `@CollectionTable`, naming strategy | Chỉ rõ collection table, join column, value column |
| `@MapKeyColumn` bị nhầm với value column | Chưa tách key và value của `Map` | Dùng `@MapKeyColumn` cho key, `@Column` cho basic value |
| Thay mới toàn bộ collection làm cập nhật bất ngờ | Mất/đổi wrapper persistent hoặc merge detached state | Sửa collection managed theo delta có chủ đích |
| Xóa owner qua bulk SQL bị FK error | Bulk delete không đi qua lifecycle ORM thông thường | Quản lý constraint/bulk deletes ở DB và giao dịch |
| Thao tác cực chậm khi reorder list dài | `@OrderColumn` phải cập nhật nhiều index | Đo SQL; thiết kế lại thứ tự hoặc entity child |
| Dữ liệu khác giữa app và DB | DB thiếu UNIQUE/FK, collation khác Java | Xác định invariant và enforce ở DB |
| Các collection bị query N+1 | Lazy access sau khi lấy nhiều owners | Chọn batch fetch, graph/query phù hợp và đo |
| Trùng hàng khi fetch nhiều collection | Join nhiều collection làm nhân bản hàng | Giảm số join fetch, tách truy vấn hoặc batch |

## 19. Một quy trình lựa chọn và triển khai

### Bước 1: Xác định đây là value hay entity

Hỏi: phần tử có cần URL, ID, workflow, version, quyền truy cập hoặc cập nhật độc lập không? Nếu có nhiều yêu cầu như vậy, nghiêng về entity con.

### Bước 2: Chọn cấu trúc collection

- Không trùng, không quan tâm thứ tự: `Set<E>`.
- Có thứ tự do người dùng quyết định: `List<E>` với `@OrderColumn`.
- Chỉ cần sắp xếp theo dữ liệu: cân nhắc `@OrderBy`.
- Các cặp key/value: `Map<K,V>` với mapping key phù hợp.

### Bước 3: Thiết kế collection table và constraint

Định nghĩa FK về owner, các cột value, khóa/unique phù hợp với ngữ nghĩa Java, chỉ mục theo truy vấn dự kiến và chính sách xóa. Không mặc định JPA schema generation sẽ tạo đầy đủ constraint nghiệp vụ.

### Bước 4: Viết mapping tường minh

Với basic element, dùng `@Column`; với embeddable, dùng `@AttributeOverride` khi cần. Đặt tên `@CollectionTable` và `@JoinColumn` rõ ràng nếu quản lý schema bằng migration.

### Bước 5: Định nghĩa API thay đổi giá trị

Xây method như `addTag`, `removeTag`, `replaceAddresses`, `setProperty` trên aggregate root. Chuẩn hóa và validation đầu vào tại ranh giới nghiệp vụ; tránh để tầng web thao tác collection ORM tùy ý.

### Bước 6: Thiết kế fetch theo use case

Với màn hình chỉ hiển thị tên sản phẩm, không fetch tags. Với màn hình chi tiết cần tags, dùng fetch plan phù hợp trong transaction. Theo dõi SQL count và rows để tránh N+1 hoặc cartesian multiplication.

### Bước 7: Kiểm soát migration và concurrency

Khi thêm collection table vào hệ thống hiện có, viết migration, backfill dữ liệu nếu có và định nghĩa behavior rollback. Nếu nhiều request cùng chỉnh collection, kiểm tra version/concurrency; tránh áp nguyên bộ giá trị cũ lên dữ liệu mới.

## 20. Tình huống thực hành

### Bài tập A — Tags sản phẩm

Một sản phẩm có tags `{"sale", "office"}`. Người dùng bỏ `"office"` và thêm `"new"`. Có cần `TagRepository.delete()` không?

**Giải thích:** Không. Nếu tags là `Set<String>` với `@ElementCollection`, hãy lấy `Product` đang managed, gọi `removeTag("office")` và `addTag("new")`, rồi commit transaction. Hibernate đồng bộ bảng value theo handling strategy thực tế.

### Bài tập B — Danh sách bước có thứ tự

Mỗi công thức có các bước được người dùng kéo-thả. Nên chọn `@OrderBy("instruction")` hay `@OrderColumn`?

**Giải thích:** Dùng `@OrderColumn` nếu cần lưu **vị trí kéo-thả**. `@OrderBy` sắp xếp theo giá trị `instruction`, không lưu thứ tự do người dùng định nghĩa.

### Bài tập C — Địa chỉ trùng nhau

Khách hàng có hai địa chỉ cùng street/city/postalCode nhưng khác nhãn `"home"` và `"office"`. Nếu dùng `Set<PostalAddress>` mà equality chỉ gồm street/city/postalCode thì sao?

**Giải thích:** `Set` coi hai địa chỉ là một giá trị và không giữ đủ hai mục. Phải làm rõ domain: nhãn có tạo nên danh tính của **giá trị** hay không? Có thể thêm nhãn vào embeddable/equality, chuyển sang `List` cho phép lặp hoặc dùng `AddressEntry` entity nếu mỗi mục có lifecycle riêng.

### Bài tập D — Map thuộc tính

Dữ liệu yêu cầu một sản phẩm có `{"size":"M","color":"red"}`. Cột nào là map key, cột nào là value?

**Giải thích:** Dùng `Map<String,String>`, `@MapKeyColumn(name="property_key")` cho `"size"` và `"color"`, `@Column(name="property_value")` cho `"M"` và `"red"`; `@CollectionTable` chỉ định bảng và FK owner.

### Bài tập E — Comment có phản hồi và phân quyền

Một bình luận có tác giả, ID, ngày chỉnh sửa, phản hồi theo thread và trạng thái kiểm duyệt. Có nên dùng `@ElementCollection List<String>`?

**Giải thích:** Thường không. Comment có danh tính và lifecycle riêng; nên mô hình hóa `Comment @Entity`, liên kết tới bài viết và quan hệ với tác giả/parent comment.

### Bài tập F — Hibernate xóa/chèn lại nhiều hàng

Một `List<String>` không có `@OrderColumn` chứa hàng nghìn mã. Xóa một mã mà log SQL có rất nhiều `DELETE`/`INSERT`. Nên nghĩ đến điều gì?

**Giải thích:** Collection có thể được quản lý theo bag, không có row identity đáng tin cậy để định vị từng phần tử. Kiểm tra SQL và workload, xem xét `Set`, index ổn định hoặc entity con nếu cập nhật từng hàng thường xuyên.

### Bài tập G — Lazy loading sau transaction

Service lấy `Product`, đóng `EntityManager`, sau đó controller duyệt `getTags()`. Hibernate báo lazy initialization. Có nên bật `EAGER` trên mọi collection?

**Giải thích:** Không nên dùng EAGER hàng loạt. Service nên trả DTO đã lấy các tag cần thiết trong transaction hoặc dùng query/fetch plan cụ thể, vừa giải quyết lỗi vừa kiểm soát query count.

### Bài tập H — Bulk delete

Ứng dụng xóa Product bằng JPQL `delete from Product p where p.id = :id`, nhưng DB báo FK từ `product_tags`. Tại sao?

**Giải thích:** Bulk delete có thể bỏ qua lifecycle xóa collection của ORM; khác `em.remove()` trên managed entity. Cần chiến lược xóa nhất quán: dùng entity lifecycle khi thích hợp, xóa các hàng collection trước trong transaction hoặc FK `ON DELETE CASCADE` do migration kiểm soát.

## 21. Nguồn tài liệu chính thức

- [Jakarta Persistence 3.2 — `@ElementCollection`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/elementcollection): tập hợp basic/embeddable và mặc định fetch.
- [Jakarta Persistence 3.2 — `@CollectionTable`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/collectiontable): bảng lưu collection, join column và quy tắc mapping.
- [Jakarta Persistence 3.2 — `@OrderColumn`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/ordercolumn): provider duy trì thứ tự `List`, đánh số vị trí.
- [Jakarta Persistence 3.2 — `@MapKeyColumn`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/mapkeycolumn): cột key của `Map` có basic key.
- [Jakarta Persistence 3.2 — Specification](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html): phần collection-valued attributes, embeddable, map, lifecycle và mapping.
- [Hibernate ORM User Guide](https://docs.hibernate.org/stable/orm/userguide/html_single/): element collections, persistent collections, fetching, batch/subselect và SQL lifecycle. Chọn user guide đúng dòng Hibernate khi dự án có yêu cầu behavior cụ thể.

## Kết luận

`@ElementCollection` là lựa chọn phù hợp khi các phần tử chỉ là **giá trị thuộc entity sở hữu**, không có danh tính và vòng đời độc lập. Một `Set<String>`, `List<String>`, `Map<String,String>` hoặc `Set<@Embeddable>` có thể được ánh xạ tới collection table với FK về owner; Hibernate quản lý việc đọc, thêm và xóa các giá trị đó trong persistence context. Chọn `Set`, `List` và `Map` theo ngữ nghĩa thực tế; dùng `@OrderColumn` nếu phải lưu vị trí; xác định equality và constraint nhất quán; thiết kế fetch cùng chi phí SQL cập nhật. Khi phần tử cần ID ổn định, trạng thái riêng, truy vấn hoặc cập nhật độc lập, hãy chuyển sang một quan hệ entity như `@OneToMany` thay vì cố mở rộng value collection vượt quá vai trò của nó.
