# Lựa chọn annotation hoặc tệp orm.xml trong JPA

**Jakarta Persistence (JPA)** cần **siêu dữ liệu ánh xạ** (*mapping metadata*) để biết một lớp Java tương ứng với bảng nào, thuộc tính nào là khóa chính, các cột được đọc/ghi ra sao, quan hệ giữa entities được biểu diễn bằng khóa ngoại nào và cơ chế sinh ID hoặc versioning hoạt động như thế nào.

Có hai cách tiêu chuẩn để khai báo phần lớn metadata đó:

- **Annotation** ngay trên lớp/field/getter Java, chẳng hạn `@Entity`, `@Table`, `@Id`, `@Column`, `@ManyToOne`, `@JoinColumn` và `@Version`.
- **XML mapping**, thường nằm trong tệp **`META-INF/orm.xml`**, với các phần tử như `<entity>`, `<table>`, `<id>`, `<basic>`, `<many-to-one>` và `<version>`.

Đây không phải hai hệ ORM khác nhau. Cả hai cung cấp metadata cho **cùng JPA provider** và cùng cơ chế `EntityManager`, persistence context, JPQL, Criteria API và transaction. Ứng dụng cũng có thể **kết hợp annotation với XML** khi có lý do rõ ràng.

> **Nguyên tắc lựa chọn:** Đối với phần lớn ứng dụng tự sở hữu source code của entities và mapping tương đối ổn định, **annotation là điểm khởi đầu dễ đọc, dễ refactor và dễ kiểm tra**. Chọn **`orm.xml`** khi cần ánh xạ các lớp không tiện sửa, tách mapping khỏi source, quản lý metadata tập trung hoặc ghi đè một số khai báo của annotations. Dùng **hybrid** có chủ đích khi phần lớn mapping nằm trong Java nhưng một phần phải được override ở XML.

Đồng thời phải phân biệt ba loại cấu hình:

1. **`persistence.xml`**: định nghĩa persistence unit và cách JPA bootstrap, có thể liệt kê mapping files.
2. **`orm.xml`**: mô tả metadata ánh xạ của entity/mapped superclass/embeddable và một số defaults/listeners.
3. **SQL schema/migration**: định nghĩa bảng, cột, khóa ngoại, indexes và constraints thực sự trong database. Mapping JPA **không mặc nhiên là một migration an toàn**.

Bài học nằm trong chương **Siêu dữ liệu và lược đồ** thuộc module **Data Persistence Relational Access ORM JPA**. Nội dung đi từ so sánh annotation/XML, ví dụ ánh xạ tương đương, XML-only entities, quy tắc ghi đè và `metadata-complete`, quyền sở hữu quan hệ, đặt tên/lược đồ, inheritance, lifecycle listeners, sự khác biệt giữa metadata và DDL, migration, kiểm thử, các lỗi thường gặp và bài tập.

---

## 1. JPA metadata được sử dụng để làm gì?

Giả sử có lớp Java:

```java
public class Product {
    private Long id;
    private String sku;
    private String name;
    private BigDecimal price;
    private Category category;
    private Long version;
}
```

Chỉ nhìn Java class, provider chưa biết chắc:

- `Product` có là một entity hay chỉ là POJO bình thường?
- Bảng sẽ là `products`, `PRODUCT` hay một tên khác?
- `id` là primary key hay chỉ là một field?
- `sku` có phải unique/not-null không?
- `price` dùng precision và scale bao nhiêu?
- `category` là relationship `@ManyToOne` hay một đối tượng value?
- Cột khóa ngoại gọi là `category_id` hay tên khác?
- `version` có phải trường khóa lạc quan?
- Provider đọc/ghi trực tiếp fields hay qua getters?
- Entity được scan từ đâu và thuộc persistence unit nào?

Metadata trả lời các câu hỏi ánh xạ trên để JPA provider tạo mapping nội bộ.

### 1.1. Từ Java đến database

```text
                    Java domain classes
                    Product, Category
                           |
                  Mapping metadata
             +-------------+-------------+
             |                           |
         Annotations                   orm.xml
             |                           |
             +-------------+-------------+
                           |
                           v
                     JPA provider
                 (Hibernate/EclipseLink/...)
                           |
                 Runtime entity mapping
                           |
              EntityManager / JPQL / SQL
                           |
                           v
                    Database schema
                 (products, categories)
```

**Cách khai báo metadata không làm thay đổi trách nhiệm của application:** vẫn phải quản lý transaction, entity lifecycle, concurrency, validation, migrations và database constraints.

### 1.2. Annotation không phải SQL schema

Ví dụ:

```java
@Column(name = "sku", nullable = false, length = 50)
private String sku;
```

Đây là metadata JPA. Nó có thể được sử dụng khi sinh schema, nhưng **không có nghĩa database production đã có cột và ràng buộc tương ứng**.

Nếu database được quản lý bằng migration, một thay đổi annotation vẫn cần migration SQL thích hợp.

### 1.3. orm.xml không phải persistence.xml

Hai tệp có trách nhiệm khác nhau:

```text
src/main/resources/
└── META-INF/
    ├── persistence.xml   # Bootstrap persistence unit
    └── orm.xml           # Entity mapping metadata
```

`persistence.xml` có thể dùng phần tử `<mapping-file>` trỏ tới `META-INF/orm.xml`. Ngược lại, `orm.xml` không thay thế việc thiết lập connection, datasource hoặc transaction strategy.

## 2. Những annotation ánh xạ thường gặp

| Nhóm | Annotations | Vai trò |
| --- | --- | --- |
| Entity | `@Entity`, `@Table` | Xác định entity và bảng |
| Identity | `@Id`, `@EmbeddedId`, `@IdClass` | Xác định primary key |
| ID generation | `@GeneratedValue`, `@SequenceGenerator`, `@TableGenerator` | Sinh ID theo strategy |
| Scalar | `@Basic`, `@Column`, `@Enumerated`, `@Lob` | Ánh xạ thuộc tính đơn |
| Versioning | `@Version` | Kiểm soát optimistic version |
| Relationship | `@ManyToOne`, `@OneToMany`, `@OneToOne`, `@ManyToMany` | Ánh xạ quan hệ |
| Join | `@JoinColumn`, `@JoinTable` | FK và join table |
| Embedded | `@Embeddable`, `@Embedded`, `@AttributeOverride` | Value objects |
| Inheritance | `@Inheritance`, `@DiscriminatorColumn` | Entity hierarchy |
| Mapping base | `@MappedSuperclass` | Chia sẻ metadata cho subclasses |
| Callbacks | `@EntityListeners`, `@PrePersist`, `@PreUpdate` | Sự kiện vòng đời |
| Index/constraint hints | `@Index`, `@UniqueConstraint` | Thông tin dùng cho schema generation |
| Cache | `@Cacheable` | Khả năng dùng shared cache |

Annotations thường được đặt **gần Java member mà chúng mô tả**, giúp người đọc nhìn field và cột tương ứng trong cùng một file.

### 2.1. Không phải mọi annotation là JPA mapping

Một lớp entity có thể còn chứa:

```java
@NotBlank
@Size(max = 50)
private String sku;
```

Các annotation trên thuộc **Jakarta Bean Validation**, không cùng chức năng với `@Column`. Metadata hoàn chỉnh qua XML của JPA không đồng nghĩa mọi Bean Validation rule tự mất hiệu lực.

Tương tự, Jackson JSON annotations, Lombok, OpenAPI annotations hoặc Spring annotations là các lớp metadata khác. Không gộp tất cả vào “annotation mapping JPA”.

## 3. Bảng so sánh annotation và orm.xml

| Tiêu chí | Annotation | `orm.xml` |
| --- | --- | --- |
| Vị trí | Ngay trong source entity | Tệp XML riêng |
| Dễ thấy mapping khi đọc Java | Rất rõ | Phải mở metadata bên ngoài |
| Refactor field/class | IDE thường hỗ trợ tốt | Cần đồng bộ tên khai báo XML |
| XML verbosity | Không có | Nhiều cấu hình, cú pháp dài hơn |
| Tách persistence khỏi domain POJO | Ít hơn | Tốt hơn nếu chọn XML-only |
| Không sửa source class | Khó/không thể thêm annotation | Có thể ánh xạ lớp phù hợp bằng XML |
| Tập trung defaults toàn persistence unit | Một phần qua base classes/config | Có thể khai báo một số defaults qua XML |
| Ghi đè mapping cụ thể | Sửa source/rebuild | Có thể dùng XML override đúng phạm vi |
| Lỗi tên member viết sai | Compiler/IDE có thể hỗ trợ một phần | Hay lộ khi bootstrap |
| Portability | Annotation chuẩn JPA khá portable | XML chuẩn JPA cũng portable nếu schema/feature hỗ trợ |
| Provider-specific tính năng | Annotation riêng | XML/provider config riêng nếu hỗ trợ |
| Multi-environment | Thường cùng mapping, thay properties | Có thể đóng gói mapping variants nếu kiểm soát |
| Khả năng review diff | Java diff sát field | XML diff rõ ở một nơi, nhưng tách khỏi code |
| Tác động lên schema | Metadata không tự là migration | Tương tự, không tự là migration |

**Không có câu trả lời “XML luôn tốt hơn annotation” hoặc ngược lại.** Cần xem ai sở hữu source code, mức thay đổi mapping, đội ngũ bảo trì và yêu cầu triển khai.

## 4. Cây quyết định nhanh

```text
Có quyền sửa source code của entities?
     |
     +-- Có
     |    |
     |    +-- Mapping đơn giản/ổn định?
     |    |       |
     |    |       +-- Có  -> Ưu tiên annotations
     |    |       |
     |    |       +-- Không -> Xem XML/hybrid để quản lý
     |    |                  override và metadata phức tạp
     |    |
     |    +-- Chỉ cần đổi một số mapping?
     |            |
     |            +-- Có  -> Annotations + XML override cụ thể
     |
     +-- Không
          |
          +-- Lớp Java đáp ứng yêu cầu entity JPA?
                 |
                 +-- Có  -> Cân nhắc XML-only mapping
                 |
                 +-- Không -> Cần adapter/model riêng hoặc
                              thay đổi class, không thể
                              "cứ thêm XML là xong"
```

Một số câu hỏi nên đặt trước khi lựa chọn:

1. Domain classes do team hiện tại sở hữu hay đến từ thư viện khác?
2. Mapping có giống nhau ở tất cả deployments không?
3. Team quen đọc Java annotations hay XML metadata?
4. Có cần thay đổi mapping mà không sửa Java source không?
5. Có nhiều entity inheritance/overrides/danh sách converters phức tạp không?
6. Có bao nhiêu persistence units và mapping variants?
7. Có provider-specific features không thể diễn đạt bằng chuẩn JPA?
8. Ai chịu trách nhiệm đồng bộ DDL migrations?
9. Đã có integration tests cho metadata bootstrap và mapping không?
10. Khi sự cố SQL xảy ra, developers có dễ truy ra mapping đang có hiệu lực không?

## 5. Mô hình ví dụ để đối chiếu hai cách

Ta xây catalog đơn giản:

```text
Category
  id
  code
  name
       ^
       |
       | Product.category
       | ManyToOne
       |
Product
  id
  sku
  name
  price
  category
  version
```

Giả định:

- `Category` có primary key do ứng dụng gán.
- `Product` có primary key do ứng dụng gán.
- `Category.code` và `Product.sku` là duy nhất.
- `Product.price` là `BigDecimal`, precision 14, scale 2.
- Product bắt buộc có Category.
- Product có version cho optimistic locking.
- Chưa cần reverse collection `Category.products` ở ví dụ cơ bản.

DDL minh họa gần PostgreSQL:

```sql
CREATE TABLE categories (
    id BIGINT PRIMARY KEY,
    code VARCHAR(40) NOT NULL UNIQUE,
    name VARCHAR(160) NOT NULL
);

CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(160) NOT NULL,
    price NUMERIC(14, 2) NOT NULL,
    category_id BIGINT NOT NULL,
    version BIGINT NOT NULL,

    CONSTRAINT fk_products_category
        FOREIGN KEY (category_id)
        REFERENCES categories(id)
);

CREATE INDEX idx_products_category
    ON products(category_id);
```

DDL và metadata được thiết kế tương ứng để học cách mapping; thực tế cần migrations và kiểm tra dialect. Giá trị version khởi tạo và cập nhật theo strategy của JPA provider.

## 6. Cách A: ánh xạ hoàn toàn bằng annotation

### 6.1. Category

```java
package com.example.catalog;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "categories")
public class Category {

    @Id
    @Column(name = "id")
    private Long id;

    @Column(
        name = "code",
        nullable = false,
        unique = true,
        length = 40
    )
    private String code;

    @Column(
        name = "name",
        nullable = false,
        length = 160
    )
    private String name;

    protected Category() {
        // JPA constructor.
    }

    public Category(Long id, String code, String name) {
        this.id = id;
        this.code = code;
        this.name = name;
    }

    public Long getId() { return id; }
    public String getCode() { return code; }
    public String getName() { return name; }
}
```

### 6.2. Product

```java
package com.example.catalog;

import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @Column(name = "id")
    private Long id;

    @Column(
        name = "sku",
        nullable = false,
        unique = true,
        length = 50
    )
    private String sku;

    @Column(
        name = "name",
        nullable = false,
        length = 160
    )
    private String name;

    @Column(
        name = "price",
        nullable = false,
        precision = 14,
        scale = 2
    )
    private BigDecimal price;

    @ManyToOne(
        fetch = FetchType.LAZY,
        optional = false
    )
    @JoinColumn(
        name = "category_id",
        nullable = false
    )
    private Category category;

    @Version
    @Column(name = "version", nullable = false)
    private Long version;

    protected Product() {
    }

    public Product(
            Long id,
            String sku,
            String name,
            BigDecimal price,
            Category category) {

        this.id = id;
        this.sku = sku;
        this.name = name;
        this.price = price;
        this.category = category;
    }

    public Long getId() { return id; }
    public String getSku() { return sku; }
    public String getName() { return name; }
    public BigDecimal getPrice() { return price; }
    public Category getCategory() { return category; }
    public Long getVersion() { return version; }

    public void changePrice(BigDecimal newPrice) {
        if (newPrice == null || newPrice.signum() < 0) {
            throw new IllegalArgumentException(
                "Invalid product price"
            );
        }
        price = newPrice;
    }
}
```

### 6.3. Những annotation quan trọng

- `@Entity`: đăng ký class là entity nếu được persistence unit quản lý.
- `@Table(name="products")`: bảng tương ứng.
- `@Id`: primary key.
- `@Column`: tên và metadata của basic column.
- `@ManyToOne`: quan hệ Product tới Category.
- `@JoinColumn`: khóa ngoại nằm trong bảng Products.
- `@Version`: kiểm tra optimistic version khi cập nhật managed entity.
- `FetchType.LAZY`: yêu cầu lazy loading; hành vi truy cập proxy/enhancement phụ thuộc provider.

### 6.4. Access strategy trong ví dụ

`@Id` được đặt **trên field**, nên theo access-default rules của JPA, các mapped attributes của entity đang dùng **field access** nếu không có override phù hợp.

```java
@Id
private Long id;
```

Provider truy cập mapped fields theo semantics của field access, không cần setters công khai chỉ để persist. Ngược lại, nếu `@Id` ở getter, entity thường có **property access**.

Không đặt annotations bừa giữa field và getter nếu không sử dụng `@Access` rõ ràng; sẽ dễ tạo mapping bất ngờ.

## 7. Dùng annotations trong persistence unit

Một phần cấu hình Java SE có thể là:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence
    xmlns="https://jakarta.ee/xml/ns/persistence"
    version="3.1">

    <persistence-unit
        name="catalogPU"
        transaction-type="RESOURCE_LOCAL">

        <class>com.example.catalog.Category</class>
        <class>com.example.catalog.Product</class>

        <!-- Provider, JDBC/datasource properties và
             quản lý schema cấu hình riêng theo runtime. -->

    </persistence-unit>
</persistence>
```

Tệp trên là ví dụ tối giản để chỉ ra **hai entity classes được quản lý**. Nó chưa có datasource/properties nên không nhất thiết bootstrap độc lập thành công khi chạy ứng dụng.

### 7.1. Có bắt buộc liệt kê class bằng persistence.xml?

Không phải trong mọi môi trường. Framework, classpath scanning, container và cấu hình persistence unit có thể phát hiện entities theo cơ chế thích hợp.

Tuy nhiên, khi muốn ví dụ dễ kiểm soát hoặc dùng Java SE bootstrap đơn giản, liệt kê classes rõ ràng giúp tránh phụ thuộc vào giả định về scan.

### 7.2. Mã sử dụng không phụ thuộc cách khai báo metadata

```java
EntityManager em = emf.createEntityManager();

try {
    EntityTransaction tx = em.getTransaction();
    tx.begin();

    Category category =
        em.find(Category.class, 10L);

    Product product = new Product(
        101L,
        "KB-101",
        "Mechanical Keyboard",
        new BigDecimal("120.00"),
        category
    );

    em.persist(product);
    tx.commit();
} finally {
    em.close();
}
```

Ví dụ giả định `Category#10` đã có trong database và persistence unit dùng resource-local transactions. Trong code production, thêm rollback khi lỗi.

**Cùng Java code sử dụng `EntityManager` có thể hoạt động với XML-only mapping**, miễn provider nhận được metadata tương đương.

## 8. Cách B: lớp Java thuần, mapping bằng orm.xml

Nếu muốn tách các annotations JPA khỏi domain model, lớp Java có thể là POJO:

```java
package com.example.catalog;

public class Category {

    private Long id;
    private String code;
    private String name;

    protected Category() {
    }

    public Category(Long id, String code, String name) {
        this.id = id;
        this.code = code;
        this.name = name;
    }

    public Long getId() { return id; }
    public String getCode() { return code; }
    public String getName() { return name; }
}
```

```java
package com.example.catalog;

import java.math.BigDecimal;

public class Product {

    private Long id;
    private String sku;
    private String name;
    private BigDecimal price;
    private Category category;
    private Long version;

    protected Product() {
    }

    public Product(
            Long id,
            String sku,
            String name,
            BigDecimal price,
            Category category) {

        this.id = id;
        this.sku = sku;
        this.name = name;
        this.price = price;
        this.category = category;
    }

    public Long getId() { return id; }
    public String getSku() { return sku; }
    public String getName() { return name; }
    public BigDecimal getPrice() { return price; }
    public Category getCategory() { return category; }
    public Long getVersion() { return version; }

    public void changePrice(BigDecimal newPrice) {
        if (newPrice == null || newPrice.signum() < 0) {
            throw new IllegalArgumentException(
                "Invalid product price"
            );
        }
        price = newPrice;
    }
}
```

Hai lớp **không có `@Entity`, `@Id` hay `@Column`**. JPA provider chỉ quản lý chúng như entities khi nhận được metadata XML tương ứng.

### 8.1. Không phải mọi POJO đều ánh xạ tùy ý được

XML giúp tránh sửa source class để thêm JPA annotations, nhưng lớp vẫn phải đáp ứng những yêu cầu entity của JPA và giới hạn bytecode/provider liên quan:

- Có constructor không tham số theo quy tắc JPA.
- Hình thức class không vi phạm những ràng buộc entity của JPA, chẳng hạn về tính final và các method persistent theo đặc tả.
- Fields/properties ánh xạ phải có khả năng truy cập phù hợp.
- Identity và lifecycle semantics phải được khai báo đúng.
- Những lớp thư viện không được thiết kế cho persistence có thể cần adapter.

**Không được kết luận “bất cứ final class trong dependency nào cũng có thể biến thành entity chỉ bằng XML”.**

## 9. Tệp META-INF/orm.xml: mapping tương đương

Một bản XML mapping minh họa bằng Jakarta Persistence 3.1:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<entity-mappings
    xmlns="https://jakarta.ee/xml/ns/persistence/orm"
    version="3.1">

    <entity
        class="com.example.catalog.Category"
        access="FIELD"
        metadata-complete="true">

        <table name="categories"/>

        <attributes>
            <id name="id">
                <column name="id"/>
            </id>

            <basic name="code" optional="false">
                <column
                    name="code"
                    nullable="false"
                    unique="true"
                    length="40"/>
            </basic>

            <basic name="name" optional="false">
                <column
                    name="name"
                    nullable="false"
                    length="160"/>
            </basic>
        </attributes>
    </entity>

    <entity
        class="com.example.catalog.Product"
        access="FIELD"
        metadata-complete="true">

        <table name="products"/>

        <attributes>
            <id name="id">
                <column name="id"/>
            </id>

            <basic name="sku" optional="false">
                <column
                    name="sku"
                    nullable="false"
                    unique="true"
                    length="50"/>
            </basic>

            <basic name="name" optional="false">
                <column
                    name="name"
                    nullable="false"
                    length="160"/>
            </basic>

            <basic name="price" optional="false">
                <column
                    name="price"
                    nullable="false"
                    precision="14"
                    scale="2"/>
            </basic>

            <many-to-one
                name="category"
                fetch="LAZY"
                optional="false">

                <join-column
                    name="category_id"
                    nullable="false"/>
            </many-to-one>

            <version name="version">
                <column
                    name="version"
                    nullable="false"/>
            </version>
        </attributes>
    </entity>
</entity-mappings>
```

Trong ví dụ:

- `<entity class="...">` chỉ định Java class được ánh xạ.
- `access="FIELD"` chọn field access.
- `metadata-complete="true"` yêu cầu mapping metadata cho entity đó được lấy từ XML thay vì pha trộn với JPA annotations trên class.
- `<table>` ánh xạ bảng.
- `<id>` ánh xạ primary key.
- `<basic>` ánh xạ cột cơ bản.
- `<many-to-one>` và `<join-column>` ánh xạ relationship.
- `<version>` ánh xạ trường optimistic version.

**Lưu ý về ví dụ:** Đây là hướng XML-only dành cho các POJO không có JPA mapping annotations. Tên các members trong XML phải khớp chính xác với Java fields. Cần dùng schema/namespace/version XML tương thích với phiên bản Jakarta Persistence mà ứng dụng chạy.

### 9.1. Mapping metadata là tương đương về ý định

Với cùng Java model, schema và các cài đặt provider thích hợp, hai cách có thể diễn đạt cùng mapping:

| Ý định | Annotation | XML |
| --- | --- | --- |
| Entity class | `@Entity` | `<entity class="...">` |
| Table | `@Table(name="products")` | `<table name="products"/>` |
| Primary key | `@Id` | `<id name="id">` |
| Basic field | `@Column(...)` | `<basic ...><column .../></basic>` |
| Many-to-one | `@ManyToOne` | `<many-to-one name="...">` |
| Foreign key | `@JoinColumn` | `<join-column .../>` |
| Version | `@Version` | `<version name="version">` |
| Field access | `@Access(FIELD)` hoặc placement | `access="FIELD"` |

**Không cần dùng cả hai phiên bản đồng thời** chỉ để làm ví dụ. Trong project thật, chọn một nguồn mapping chủ đạo hoặc định nghĩa override có chủ đích.

## 10. Nạp tệp orm.xml bằng persistence.xml

Để chỉ định mapping file, thêm `<mapping-file>` trong persistence unit:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence
    xmlns="https://jakarta.ee/xml/ns/persistence"
    version="3.1">

    <persistence-unit
        name="catalogPU"
        transaction-type="RESOURCE_LOCAL">

        <mapping-file>META-INF/orm.xml</mapping-file>

        <!-- Datasource/provider/JDBC properties
             được cung cấp theo môi trường. -->

    </persistence-unit>
</persistence>
```

Vì `orm.xml` có khai báo các `<entity class="...">` tương ứng, JPA provider có metadata để quản lý `Category` và `Product` khi bootstrap persistence unit.

### 10.1. Vì sao cần đúng classpath resource path?

`<mapping-file>` không phải một filesystem path tùy ý relative với current working directory của Java process. Nó tham chiếu **resource có thể tìm được trong deployment/classpath** của persistence unit.

Cấu trúc thường gặp:

```text
project/
├── src/main/java/com/example/catalog/
│   ├── Category.java
│   └── Product.java
└── src/main/resources/META-INF/
    ├── persistence.xml
    └── orm.xml
```

Sau build, hai XML files thường nằm trong `classes/META-INF` hoặc vị trí tài nguyên tương ứng trong JAR/WAR.

### 10.2. META-INF/orm.xml có thể được nhận diện mặc định

Theo cơ chế bootstrap của JPA, `META-INF/orm.xml` là tên mapping file mặc định được nhận diện trong những điều kiện thích hợp. Tuy vậy, khi muốn **rõ tính sở hữu và tránh nhầm classpath packaging**, khai báo `<mapping-file>META-INF/orm.xml</mapping-file>` là một lựa chọn dễ hiểu.

Tránh vô tình **đăng ký cùng một XML mapping file nhiều lần** qua cơ chế mặc định và các khai báo khác mà không biết provider xử lý ra sao. Khi ứng dụng có nhiều modules/persistence units, hãy kiểm tra danh sách mapping resources thực sự được bootstrap.

### 10.3. XML chỉ đổi khi EntityManagerFactory được bootstrap lại

Sửa nội dung `orm.xml` trên disk **không có nghĩa EntityManagerFactory đã hoạt động sẽ tự rebuild mapping metadata**.

Thông thường, thay đổi metadata cần:

1. Build/package file XML đúng.
2. Deploy/restart hoặc tạo EntityManagerFactory mới.
3. Chạy migrations DB tương ứng nếu schema thay đổi.
4. Xác nhận application đã load metadata mới.

Không dùng `orm.xml` như “một file cấu hình hot reload” mặc định.

## 11. Sử dụng EntityManager với XML-only entities

Khi XML mapping tương đương đã được load, persistence operations vẫn là:

```java
EntityManagerFactory emf =
    Persistence.createEntityManagerFactory("catalogPU");

EntityManager em = emf.createEntityManager();

try {
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        Category category =
            em.find(Category.class, 10L);

        Product product = new Product(
            101L,
            "KB-101",
            "Mechanical Keyboard",
            new BigDecimal("120.00"),
            category
        );

        em.persist(product);
        em.flush();
        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw ex;
    }
} finally {
    em.close();
    emf.close();
}
```

Đoạn code này dùng `jakarta.persistence.*` và `java.math.BigDecimal`, giả định Category#10 có sẵn, database connection/provider đã được cấu hình và resource-local transaction được dùng.

**Không tồn tại `EntityManager.persistWithXml(...)` riêng.** Mapping được chọn trong quá trình bootstrap, còn API sử dụng giống nhau.

### 11.1. JPQL cũng không đổi

```jpql
SELECT p
FROM Product p
JOIN p.category c
WHERE c.code = :categoryCode
```

JPQL làm việc với **entity name và Java persistent attributes**, không quan tâm chúng được định nghĩa bằng Java annotations hay XML metadata.

`Product` ở `FROM Product` phải tương ứng với tên entity được provider biết; `p.category` là tên persistent attribute, không phải tên cột `category_id`.

## 12. Lựa chọn annotation phù hợp trong những tình huống nào?

Annotation thường là lựa chọn có lợi khi:

- Team sở hữu Java source của entity classes.
- Mapping và model thay đổi cùng nhau.
- Dự án nhỏ hoặc vừa, ít customization.
- Developers thường refactor tên fields/classes bằng IDE.
- Muốn code review thấy relationship, column, fetch, cascade ngay gần fields.
- Không cần chuyển mapping metadata giữa các deployments.
- Muốn tránh XML dài và lỗi tên class/attribute dạng chuỗi.
- Entity classes được xem là một phần của persistence model.

### 12.1. Khi source và mapping ở gần nhau

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "category_id", nullable = false)
private Category category;
```

Người đọc thấy relationship ngay khi mở `Product.java`.

Nếu đổi `category` thành `productCategory`, IDE thường có thể giúp cập nhật các truy cập Java. Ngược lại, XML:

```xml
<many-to-one name="category">
```

phải được cập nhật thủ công hoặc bởi tooling chuyên biệt nếu không muốn bootstrap failure.

### 12.2. Chi phí annotation

Entity có thể trở nên dài nếu chứa:

- Nhiều secondary tables.
- Composite keys.
- Associations phức tạp.
- Attribute overrides.
- Named queries.
- Listener/cache metadata.
- Index/constraint declarations.

Với mapping dày đặc, source Java khó đọc cũng là một tín hiệu đáng cân nhắc tách một phần metadata ra XML.

### 12.3. “Domain thuần” không phải yêu cầu tuyệt đối

Một số team áp dụng Domain-Driven Design và muốn domain classes không phụ thuộc `jakarta.persistence`. XML-only có thể hữu ích. Nhưng nếu các class vẫn cần tuân thủ constructor, identity và lifecycle của JPA, chúng chưa hoàn toàn “không bị ảnh hưởng bởi persistence”.

Một lựa chọn khác là tách **domain model** và **persistence entities/adapters**, chấp nhận mapping giữa hai kiểu đối tượng. Không phải dự án nào cũng cần mức tách biệt đó.

## 13. Lựa chọn orm.xml phù hợp trong những tình huống nào?

XML có thể phù hợp nếu:

- Class là từ module/library không tiện chỉnh sửa để thêm JPA annotation.
- Muốn giữ POJO không phụ thuộc trực tiếp JPA annotations.
- Cần ghi đè mapping của một số entities mà không thay source.
- Có nhiều persistence units cần metadata khác nhau.
- Legacy database có naming/mapping đặc thù cần quản lý tập trung.
- Các đặc tả metadata được tạo tự động bởi tooling.
- Muốn kiểm soát một tập default entity listeners hoặc metadata ở cấp persistence unit.
- Team đã có quy trình quản lý XML mapping và kiểm thử tốt.

### 13.1. Ví dụ với lớp từ module dùng chung

Module `domain-core` định nghĩa:

```java
public class Product {
    private Long id;
    private String sku;
    // getters, constructor...
}
```

Module `persistence-jpa` sở hữu `orm.xml`, khai báo `Product` thành entity. Khi đó `domain-core` không cần import `jakarta.persistence`.

### 13.2. Phạm vi có thể thay đổi theo persistence unit

Nếu hai applications dùng cùng Java class nhưng bảng database khác nhau, mỗi persistence unit có thể được bootstrap với mapping phù hợp.

Tuy nhiên, **đổi mapping giữa các deployments không đơn giản chỉ là chỉnh XML trong cùng process**. Cần kiểm soát packaging, schema và transaction boundaries; đồng thời tránh một class vô tình được quản lý bằng hai mapping mâu thuẫn trong một persistence unit.

### 13.3. XML làm tăng trách nhiệm về naming

Nếu Java field là `productCategory` mà XML vẫn ghi:

```xml
<many-to-one name="category">
```

metadata có thể thất bại khi bootstrap hoặc ánh xạ không như mong đợi. Compiler Java thường không biết `name="category"` là tên member cần đồng bộ.

Do đó XML-heavy projects nên có **bootstrap/integration tests bắt buộc trong CI**.

## 14. Kết hợp annotation và XML (hybrid)

JPA hỗ trợ mô hình:

```text
Java annotations
  @Entity
  @Id
  @Column
  @ManyToOne
         |
         +-- orm.xml overrides for selected mapping metadata
                        |
                        v
                  Effective mapping
                        |
                        v
                 EntityManagerFactory
```

Ví dụ team giữ `@Entity`, `@Id`, `@ManyToOne` trong source, nhưng cần đổi table name ở một deployment.

### 14.1. Java source

```java
@Entity
@Table(name = "products")
public class Product {

    @Id
    private Long id;

    @Column(name = "sku", length = 50)
    private String sku;

    // Các attributes khác...
}
```

### 14.2. XML override phần table name

```xml
<?xml version="1.0" encoding="UTF-8"?>
<entity-mappings
    xmlns="https://jakarta.ee/xml/ns/persistence/orm"
    version="3.1">

    <entity class="com.example.catalog.Product">
        <table name="catalog_products"/>
    </entity>

</entity-mappings>
```

Với cách phối hợp XML/annotation được đặc tả hỗ trợ, mapping trong XML có thể **ghi đè metadata tương ứng** từ annotations; trong ví dụ là tên bảng.

Không đặt `metadata-complete="true"` khi chỉ muốn override một phần mà vẫn sử dụng các annotations khác.

### 14.3. Không phải lúc nào cũng nên dùng hybrid

Hybrid tạo ra hai nơi có thể chứa một phần sự thật:

```text
Product.java says: @Table(name="products")
orm.xml says:      <table name="catalog_products"/>
```

Nếu developers không biết XML override đang hoạt động, họ có thể debug sai bảng. Cần tài liệu xác định **effective mapping**, test bootstrap và quy tắc review rõ.

### 14.4. Chọn một nguồn sự thật chủ đạo

Một mô hình quản trị dễ bảo trì:

- Java annotations là nguồn chính.
- XML chỉ chứa những overrides thực sự cần.
- Mỗi XML override có lý do được ghi nhận.
- Không lặp lại toàn bộ `@Column` metadata trong XML nếu chỉ cần đổi tên bảng.
- Test xác nhận effective table/column names của runtime.

Đừng copy toàn bộ annotation metadata sang XML “cho chắc” rồi để hai bản lệch nhau.

## 15. Quy tắc ghi đè: không chỉ là “annotation thắng” hay “XML thắng”

Đối với JPA metadata trong cùng persistence unit, XML mapping được thiết kế để **ghi đè những metadata tương ứng được khai báo bằng annotations**, theo quy tắc hợp nhất của đặc tả.

Nhưng cần phân biệt:

1. XML **có một khai báo cụ thể** ghi đè phần tương ứng.
2. XML **không khai báo** một phần metadata: annotations và defaults khác có thể tiếp tục áp dụng.
3. XML bật **metadata-complete**: những JPA mapping annotations trong phạm vi bị coi là không dùng để quyết định metadata.
4. Cùng một class/attribute được khai báo mâu thuẫn ở nhiều XML resources: cần xác định hợp đồng và kiểm tra bootstrap, không tự suy thứ tự ưu tiên theo thứ tự file ngẫu nhiên.

### 15.1. Ví dụ dễ hiểu

Java:

```java
@Column(name = "sku", nullable = false, length = 50)
private String sku;
```

XML muốn đổi tên cột:

```xml
<basic name="sku" optional="false">
    <column
        name="product_sku"
        nullable="false"
        length="50"/>
</basic>
```

Cần xác nhận **tập thuộc tính cuối cùng** của field trong cấu hình kết hợp theo đặc tả/provider đang dùng; không tự suy rằng mỗi XML attribute bỏ trống đều có nghĩa kế thừa nguyên giá trị annotation tương ứng.

Ví dụ, nếu đổi `name` mà XML không ghi `length`, phải hiểu default và override rules của XML mapping element đó, thay vì mặc định giữ giá trị `50` chỉ vì Java annotation có nó.

### 15.2. XML override không nên là một quy trình thử-sai

Một thay đổi mapping có thể ảnh hưởng:

- Tên bảng/cột.
- Nullability.
- Kích thước/precision/scale.
- Fetch/optional.
- Ownership của relationship.
- Cascade.
- Generation strategy.
- Version field.
- DDL schema generation.

Vì thế hybrid mapping cần test **effective metadata và round-trip persistence**, không chỉ biên dịch Java.

## 16. metadata-complete trên một entity

Để yêu cầu JPA sử dụng metadata XML thay cho các JPA annotations của một entity:

```xml
<entity
    class="com.example.catalog.Product"
    access="FIELD"
    metadata-complete="true">

    <table name="products"/>

    <attributes>
        <id name="id">
            <column name="id"/>
        </id>

        <basic name="sku" optional="false">
            <column
                name="sku"
                nullable="false"
                length="50"/>
        </basic>

        <!-- Các persistent attributes cần thiết khác
             phải được ánh xạ nhất quán. -->
    </attributes>
</entity>
```

### 16.1. Ý nghĩa của metadata-complete

Khi cấu hình metadata-complete cho entity, JPA mapping annotations trong phạm vi entity tương ứng **không còn được dùng như nguồn bổ sung** theo cơ chế metadata XML-complete.

Điều này hữu ích nếu:

- Entity class có annotations cũ cần bỏ qua.
- XML-only mapping là nguồn authoritative.
- Một persistence unit cần thay đổi mapping đầy đủ so với annotations.

### 16.2. Rủi ro phổ biến

Nếu bật metadata-complete mà **không cung cấp metadata phù hợp**, class có thể:

- Thiếu primary key mapping.
- Mất quan hệ dự định.
- Không còn version mapping như ban đầu.
- Ánh xạ nhầm kiểu field/column theo defaults.
- Không được khai báo association/cascade đúng.

Vì vậy, **đừng bật metadata-complete chỉ để override một tên cột**. Khi muốn partial override, dùng XML mapping không-complete với phạm vi cụ thể.

### 16.3. Metadata-complete không tắt mọi Java annotation trong vũ trụ

Nó liên quan tới metadata mapping JPA theo phạm vi đặc tả, không phải công tắc xóa hiệu lực tất cả các annotations khác như Jakarta Validation, Jackson hay annotations của frameworks.

Một entity vẫn có thể chịu Bean Validation hoặc domain rules riêng nếu runtime sử dụng các cơ chế đó.

## 17. xml-mapping-metadata-complete ở cấp persistence unit

XML còn có cơ chế chỉ định metadata completeness rộng hơn.

Ví dụ:

```xml
<entity-mappings
    xmlns="https://jakarta.ee/xml/ns/persistence/orm"
    version="3.1">

    <persistence-unit-metadata>
        <xml-mapping-metadata-complete/>
    </persistence-unit-metadata>

    <entity class="com.example.catalog.Product">
        <!-- Mapping XML đầy đủ theo chính sách project -->
    </entity>

    <entity class="com.example.catalog.Category">
        <!-- Mapping XML đầy đủ theo chính sách project -->
    </entity>
</entity-mappings>
```

### 17.1. Khác với metadata-complete trên từng entity

| Cơ chế | Ý định |
| --- | --- |
| `<entity ... metadata-complete="true">` | XML-complete cho entity cụ thể |
| `<xml-mapping-metadata-complete/>` | Quy tắc metadata XML-complete rộng cấp persistence unit |

Khi áp chế độ toàn cục, phải bảo đảm **mọi managed type trong phạm vi đó** được khai báo đúng metadata cần thiết trong XML hoặc theo những quy tắc áp dụng, thay vì tiếp tục trông chờ các annotations bị loại bỏ.

### 17.2. Tác động đến dự án nhiều entity

Với 100 entities đang dùng `@Entity` và `@Id`, chuyển sang XML-complete toàn cục mà chỉ khai báo 2 entities là thay đổi lớn. Nó có thể khiến những entities còn lại không được ánh xạ như trước.

Đây là một **migration kiến trúc**, không phải một cờ tối ưu hiệu năng.

### 17.3. Không dùng khi muốn partial override

Nếu mục tiêu là đổi tên bảng của một entity, dùng cơ chế override hẹp sẽ rõ ràng và ít rủi ro hơn.

## 18. Field access và property access

Một nguồn lỗi thường gặp khi chuyển annotation → XML là **mismatch access strategy**.

### 18.1. Field access với annotations

```java
@Entity
public class Product {

    @Id
    private Long id;

    @Column(name = "sku")
    private String sku;

    public Long getId() { return id; }
    public String getSku() { return sku; }
}
```

Vì `@Id` nằm ở field, metadata mặc định ở ví dụ theo field access.

### 18.2. Property access với annotations

```java
@Entity
public class Product {

    private Long id;
    private String sku;

    @Id
    public Long getId() {
        return id;
    }

    @Column(name = "sku")
    public String getSku() {
        return sku;
    }

    public void setId(Long id) { this.id = id; }
    public void setSku(String sku) { this.sku = sku; }
}
```

JPA dùng properties theo getter/setter contract tương ứng.

### 18.3. Trong XML

Field access:

```xml
<entity
    class="com.example.catalog.Product"
    access="FIELD">
    <!-- ... -->
</entity>
```

Property access:

```xml
<entity
    class="com.example.catalog.Product"
    access="PROPERTY">
    <!-- ... -->
</entity>
```

### 18.4. Những lỗi cần tránh

- Metadata XML nói `PROPERTY` nhưng class không có setter thích hợp.
- Annotation `@Id` ở getter, còn XML mặc định chọn field access mà không có chủ đích.
- Vừa annotate field vừa getter của cùng attribute không dùng `@Access` rõ.
- Một business getter tính toán bị JPA nhận như persistent property ngoài ý muốn.
- XML khai báo tên field không tồn tại.
- Đổi field Java nhưng quên đổi XML.

**Khi chuyển mapping từ annotations sang XML, access strategy phải được đưa vào kế hoạch migration.**

## 19. Các trường không persistent: @Transient và XML transient

Một class có trường chỉ dùng trong memory:

```java
private String displayLabel;
```

Annotation mapping:

```java
@Transient
private String displayLabel;
```

XML mapping:

```xml
<transient name="displayLabel"/>
```

### 19.1. Vì sao cần chú ý khi XML-complete?

Khi JPA mapping annotations bị bỏ qua và default access rules áp dụng, một field/property mà trước đây dựa vào `@Transient` có thể cần được khai báo là transient trong XML để tránh bị coi là persistent.

### 19.2. Java transient khác JPA @Transient

Một Java field có modifier `transient` liên quan Java serialization, còn `@Transient` là metadata mapping JPA. Chúng có liên hệ theo những quy tắc persistence defaults nhưng không nên dùng lẫn lộn như những từ đồng nghĩa trong mọi thiết kế.

### 19.3. Không phải mọi field đều cần XML <basic>

JPA có default mapping rules cho persistent attributes. Khi chọn XML-complete, cần hiểu những member nào được nhận theo default access và member nào phải khai báo rõ. Với schema legacy cần chính xác, explicit mapping giúp giảm đoán ngầm.

## 20. Basic type, enum và temporal mapping

### 20.1. BigDecimal

Annotation:

```java
@Column(precision = 14, scale = 2, nullable = false)
private BigDecimal price;
```

XML:

```xml
<basic name="price" optional="false">
    <column
        name="price"
        precision="14"
        scale="2"
        nullable="false"/>
</basic>
```

### 20.2. Enum

Annotation:

```java
@Enumerated(EnumType.STRING)
private ProductStatus status;
```

XML:

```xml
<basic name="status">
    <enumerated>STRING</enumerated>
    <column name="status" length="30"/>
</basic>
```

Với enum values thay đổi theo thời gian, dùng string storage thường dễ đọc hơn ordinal. Nhưng đổi tên enum constant vẫn có migration/data-compatibility implications.

### 20.3. LocalDateTime và Instant

Các kiểu `java.time` được JPA hỗ trợ theo đặc tả phiên bản tương ứng. Không tự đặt `@Temporal` lên `LocalDateTime` như với `java.util.Date`/`Calendar` cũ.

XML cũng cần khai báo phù hợp loại thuộc tính thực tế; không viết `<temporal>` cho mọi Java time type một cách máy móc.

### 20.4. AttributeConverter

Một `AttributeConverter` có thể chuyển giữa domain value và JDBC column representation. JPA hỗ trợ metadata converter qua các cơ chế tiêu chuẩn, nhưng syntax và scope XML cần được cấu hình đúng theo phiên bản.

Nếu chuyển từ annotations sang XML-only, cần xem cả:

- `@Converter(autoApply = true)`.
- `@Convert` trên attribute.
- XML converter declarations/convert overrides.
- Inheritance và embeddable attributes.

Không chỉ copy `@Column` rồi bỏ sót converter, vì giá trị lưu có thể thay đổi định dạng.

## 21. ID generation và metadata XML

Hai ví dụ cơ bản bên trên dùng ID do ứng dụng gán để tập trung vào mapping. Với hệ thống thực tế, nhiều entity dùng database-generated ID.

### 21.1. Annotation IDENTITY

```java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
```

Một XML mapping tương ứng:

```xml
<id name="id">
    <column name="id"/>
    <generated-value strategy="IDENTITY"/>
</id>
```

Khi chuyển metadata, phải giữ strategy và kiểm tra schema thật.

### 21.2. SEQUENCE

Annotation có thể gồm:

```java
@Id
@GeneratedValue(
    strategy = GenerationType.SEQUENCE,
    generator = "product_sequence"
)
@SequenceGenerator(
    name = "product_sequence",
    sequenceName = "product_seq",
    allocationSize = 20
)
private Long id;
```

XML cũng có metadata sequence generator theo schema JPA; phải đặt generator declaration đúng vị trí cho version đang dùng.

Không chỉ chuyển `SEQUENCE` thành `IDENTITY` trong XML rồi cho rằng behavior tương đương. Nó có thể ảnh hưởng:

- JDBC batching.
- Thời điểm được cấp ID.
- Hiệu năng insert.
- Sequence allocation.
- Schema object names.
- Cách xử lý migration.

### 21.3. Generator names và namespace

Trong codebase nhiều modules, generator names có thể va chạm nếu dùng naming không nhất quán. Khi đưa generator metadata vào XML chung, càng cần quy ước tên rõ và kiểm tra bootstrap.

## 22. Relationship metadata: annotation và XML

Một `@ManyToOne` annotation:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(
    name = "category_id",
    nullable = false
)
private Category category;
```

XML:

```xml
<many-to-one
    name="category"
    fetch="LAZY"
    optional="false">

    <join-column
        name="category_id"
        nullable="false"/>
</many-to-one>
```

### 22.1. Điều bắt buộc giữ khi chuyển

- Relationship type.
- Owning side.
- Join-column/join-table names.
- Optionality/nullability.
- Fetch strategy.
- Cascade lifecycle.
- Orphan removal (nếu là quan hệ hỗ trợ).
- Map key/order column.
- Access strategy.
- Target entity khi không thể suy tự động.

### 22.2. Vì sao chỉ copy tên field chưa đủ?

Nếu XML quên `fetch="LAZY"`, default của relationship có thể khác với annotation ban đầu. Kết quả là SQL behavior thay đổi mặc dù schema không đổi.

Nếu XML quên `optional="false"` hoặc `nullable="false"`, domain intent/schema-generation behavior cũng có thể lệch.

### 22.3. Owning side của quan hệ hai chiều

Ví dụ:

```java
@OneToMany(mappedBy = "category")
private List<Product> products;
```

`mappedBy = "category"` chỉ tới Java attribute của phía sở hữu trong `Product`, **không phải database column `category_id`**.

XML:

```xml
<one-to-many
    name="products"
    mapped-by="category"
    fetch="LAZY"/>
```

Phía Product:

```xml
<many-to-one name="category" fetch="LAZY">
    <join-column name="category_id"/>
</many-to-one>
```

Dù dùng annotations hay XML, application vẫn cần giữ object graph nhất quán. Metadata không tự sửa cả hai phía cho mọi mutation.

## 23. Cascade và orphanRemoval cần được chuyển cẩn thận

Annotation:

```java
@OneToMany(
    mappedBy = "order",
    cascade = {
        CascadeType.PERSIST,
        CascadeType.MERGE
    },
    orphanRemoval = true
)
private List<OrderLine> lines;
```

XML mapping gần tương ứng:

```xml
<one-to-many
    name="lines"
    mapped-by="order"
    orphan-removal="true">

    <cascade>
        <cascade-persist/>
        <cascade-merge/>
    </cascade>
</one-to-many>
```

### 23.1. Cascade không phải Fetch

`cascade-persist` và `cascade-merge` liên quan lifecycle operations. `fetch="LAZY"` liên quan loading strategy. Chuyển XML mà quên một trong hai có thể gây vấn đề khác nhau.

### 23.2. Không thêm cascade-all vì muốn đơn giản

`CascadeType.ALL` có thể bao gồm REMOVE. Nếu OrderLine tham chiếu Product dùng chung, cascade REMOVE từ line sang Product có thể gây xóa/tác động nhầm shared entity.

Quy tắc **ownership của lifecycle** quan trọng hơn việc metadata được viết bằng Java hay XML.

### 23.3. OrphanRemoval và merge detached graph

Nếu application nhận payload partial rồi merge một graph thiếu children, semantics orphan removal có thể gây kết quả bất ngờ. Annotation/XML không làm vấn đề tự biến mất. Cần thiết kế DTO và domain methods rõ.

## 24. @Embedded và attribute overrides

Một Product có thể chứa value object:

```java
@Embeddable
public class Dimensions {

    private BigDecimal width;
    private BigDecimal height;
    private BigDecimal depth;
}
```

Trong entity:

```java
@Embedded
@AttributeOverrides({
    @AttributeOverride(
        name = "width",
        column = @Column(name = "box_width")
    ),
    @AttributeOverride(
        name = "height",
        column = @Column(name = "box_height")
    ),
    @AttributeOverride(
        name = "depth",
        column = @Column(name = "box_depth")
    )
})
private Dimensions box;
```

XML có các phần tử:

```xml
<embedded name="box">
    <attribute-override name="width">
        <column name="box_width"/>
    </attribute-override>
    <attribute-override name="height">
        <column name="box_height"/>
    </attribute-override>
    <attribute-override name="depth">
        <column name="box_depth"/>
    </attribute-override>
</embedded>
```

Với XML-only mapping, `Dimensions` còn cần được khai báo là `<embeddable class="...">` hoặc có metadata tương ứng.

### 24.1. Khi nào XML hữu ích với embedded graph?

Nếu nhiều embedded instances phải override các cột trong một legacy schema, việc tách mapping vào XML có thể giúp nhìn toàn bộ column assignments tập trung.

### 24.2. Khi nào annotation dễ hơn?

Nếu chỉ có một `@Embedded` đơn giản, annotation gần field giúp người bảo trì hiểu cấu trúc nhanh hơn.

## 25. Inheritance và mapped superclass

JPA inheritance có các chiến lược như:

- `InheritanceType.SINGLE_TABLE`.
- `InheritanceType.JOINED`.
- `InheritanceType.TABLE_PER_CLASS`.

Annotation:

```java
@Entity
@Inheritance(strategy = InheritanceType.JOINED)
public abstract class Payment {
    @Id
    private Long id;
}
```

XML mapping có thể khai báo:

```xml
<entity class="com.example.payments.Payment">
    <inheritance strategy="JOINED"/>
    <attributes>
        <id name="id"/>
    </attributes>
</entity>
```

### 25.1. Không chỉ so sánh tên strategy

Khi chuyển annotation → XML, còn phải kiểm tra:

- Root entity và subclasses được đăng ký.
- Primary key join columns.
- Discriminator behavior/names.
- Nullable columns và DDL.
- Polymorphic JPQL.
- Các converters/listeners được kế thừa.
- Cache/locking behavior của hierarchy.

### 25.2. Mapped superclass khác entity

Annotation:

```java
@MappedSuperclass
public abstract class AuditedEntity {
    private Instant createdAt;
}
```

XML có mapping element `<mapped-superclass class="...">`. Mapped superclass chia sẻ mapping cho subclasses nhưng **không tự là một entity có thể query bằng `EntityManager.find()`**.

### 25.3. Đừng biến mapped superclass thành entity do đổi XML

Nếu metadata XML khai báo nhầm một base type là `<entity>` thay vì `<mapped-superclass>`, cấu trúc inheritance/query/table mapping có thể thay đổi đáng kể. Khi migration, cần giữ đúng loại managed type.

## 26. Lifecycle listeners qua annotation và XML

Annotation:

```java
@Entity
@EntityListeners(AuditListener.class)
public class Product {
    // ...
}
```

Listener:

```java
public class AuditListener {

    @PrePersist
    public void beforeInsert(Object entity) {
        // Logic ngắn, không external side effects.
    }
}
```

XML mapping có thể đăng ký entity listeners:

```xml
<entity class="com.example.catalog.Product">
    <entity-listeners>
        <entity-listener
            class="com.example.audit.AuditListener">

            <pre-persist method-name="beforeInsert"/>
        </entity-listener>
    </entity-listeners>
</entity>
```

### 26.1. Default listeners

Ở cấp persistence unit, `orm.xml` có thể cung cấp default entity listeners:

```xml
<persistence-unit-metadata>
    <persistence-unit-defaults>
        <entity-listeners>
            <entity-listener
                class="com.example.audit.GlobalListener">
                <pre-persist method-name="beforeInsert"/>
            </entity-listener>
        </entity-listeners>
    </persistence-unit-defaults>
</persistence-unit-metadata>
```

Đây là đoạn con của `entity-mappings` có cấu trúc hợp lệ theo schema/version tương ứng; không phải toàn bộ tệp.

### 26.2. Khi nào XML có lợi?

Một listener áp cho phần lớn managed entities có thể được đăng ký tập trung mà không thêm `@EntityListeners` vào từng class. Nhưng phạm vi quá rộng có thể tạo side effects/chi phí không mong muốn; dùng exclusion và policy rõ.

### 26.3. Callback không phải after-commit event

Dù đăng ký qua annotation hay XML:

- `@PostPersist` không bảo đảm transaction đã commit.
- `@PostUpdate` không phải sự kiện “đã ghi thành công vĩnh viễn”.
- Không gửi email, thanh toán hoặc notification không thể rollback trực tiếp chỉ dựa trên callback.
- Dùng after-commit handling hoặc transactional outbox khi cần.

Cách khai báo metadata **không thay đổi transaction semantics của callbacks**.

## 27. XML defaults cấp persistence unit

`orm.xml` có thể khai báo metadata defaults qua `<persistence-unit-metadata>` / `<persistence-unit-defaults>`.

Ví dụ về schema dùng mặc định:

```xml
<persistence-unit-metadata>
    <persistence-unit-defaults>
        <schema>shop_core</schema>
    </persistence-unit-defaults>
</persistence-unit-metadata>
```

### 27.1. Ưu điểm

Nếu nhiều entities dùng cùng một schema, defaults có thể giảm lặp tên schema trên từng `@Table`.

### 27.2. Giới hạn

Một schema default trong mapping không đồng nghĩa:

- Schema đó đã tồn tại trong database.
- User kết nối có quyền `CREATE/SELECT/INSERT` ở schema đó.
- Migration đã tạo tables đúng schema.
- Mọi SQL native và stored procedure tự dùng schema đó.
- Database search path đã được thiết lập theo ý định.

### 27.3. Nhiều môi trường

Nếu dev/staging/prod dùng các schemas khác nhau, có thể cân nhắc mapping variants hoặc configuration phù hợp provider/deployment. Nhưng dùng **một bản DDL/migration thống nhất** hoặc có quy tắc tên rõ ràng thường ít rủi ro hơn việc thay đổi object names tùy tiện giữa môi trường.

### 27.4. Không biến XML defaults thành business rules

Defaults về schema, catalog hoặc listener metadata không phải thay thế cho tenant authorization hay business validation.

## 28. Annotation/XML và physical naming strategy

Một vấn đề thường gặp trong Hibernate hoặc provider khác:

Java field:

```java
private Instant createdAt;
```

SQL column lại là:

```sql
created_at
```

Sự khác biệt có thể đến từ:

- `@Column(name="created_at")`.
- XML `<column name="created_at"/>`.
- Implicit/physical naming strategy do provider/configuration xác định.

### 28.1. Naming strategy có thể là provider-specific

Một số naming strategy implementations không thuộc những phần portable của JPA specification. Nếu dự án phụ thuộc chúng, hãy ghi rõ provider/version và kiểm thử SQL thực tế.

### 28.2. XML không tự giải quyết naming inconsistencies

Chuyển từ annotations sang XML nhưng tiếp tục dựa vào naming defaults khác giữa các environments vẫn có thể tạo schema mismatch.

Với legacy database, các tên table/column/join thường nên được khai báo **rõ** để tránh provider default bị thay đổi.

### 28.3. Case sensitivity và quoted identifiers

Database có quy tắc khác nhau cho chữ hoa/thường và identifier quoting. Các tên như `Order`, `User`, `Group` có thể đụng reserved keywords.

Chọn tên schema có chủ đích; đừng kỳ vọng mọi DBMS quoting rules giống nhau chỉ vì metadata JPA giống nhau.

## 29. Metadata và schema generation là hai chuyện khác

JPA provider có thể hỗ trợ tính năng tạo DDL theo metadata. Ví dụ cấu hình chuẩn dạng property:

```properties
jakarta.persistence.schema-generation.database.action=none
```

Các lựa chọn schema generation theo chuẩn có thể gồm `none`, `create`, `drop-and-create`, `drop` theo phiên bản/khả năng áp dụng.

Cấu hình database action thay đổi nguy hiểm nếu chỉ để thử mapping.

### 29.1. Trong development/test

Có thể dùng database tạm và schema generation để thử nhanh mapping. Tuy nhiên cần biết:

- Provider có thể sinh tên constraint/index khác migration production.
- Một số DDL feature không portable.
- Changes không được track như migration lịch sử.
- Chạy `drop-and-create` trên dữ liệu thật có thể xóa dữ liệu.

### 29.2. Trong production

Nhiều dự án sử dụng:

- Flyway.
- Liquibase.
- SQL migrations thủ công có kiểm soát.

Metadata annotations/XML và migrations được thay đổi **đồng bộ**, nhưng deployment schema phải nằm trong quy trình kiểm soát riêng.

### 29.3. Thay mapping không tự rename column

Nếu sửa:

```java
@Column(name="price")
private BigDecimal price;
```

thành XML:

```xml
<column name="unit_price"/>
```

nhưng database vẫn có cột `price`, runtime có thể nhận lỗi SQL vì `unit_price` không tồn tại.

Cần migration:

```sql
ALTER TABLE products
RENAME COLUMN price TO unit_price;
```

Cú pháp thay đổi tùy DBMS, và production rollout có thể cần kỹ thuật expand/contract nếu phải tương thích nhiều app versions.

### 29.4. Mapping là hợp đồng runtime, migration là lịch sử thay đổi DB

Không dùng một file XML để mô tả “từ khi nào thêm cột” hay “đã chuyển dữ liệu chưa”. Những thông tin triển khai và lịch sử đó thuộc migration pipeline.

## 30. Quy trình migration từ annotations sang orm.xml

Một dự án legacy muốn giữ domain classes không còn import `jakarta.persistence`.

### 30.1. Bước 1 — Ghi nhận mapping hiện tại

Với từng entity:

- Entity name.
- Table/schema/catalog.
- ID và generation strategy.
- Basic fields, nullable/length/precision/scale.
- Enumerated/converters.
- Version.
- Relationships và join columns/tables.
- Cascade/fetch/orphanRemoval.
- Embedded types và overrides.
- Inheritance strategy.
- Callbacks/listeners.
- Named queries.
- Cache metadata.
- Provider-specific extensions.

### 30.2. Bước 2 — Chọn thử một entity ít rủi ro

Không chuyển ngay toàn bộ 100 entities. Chọn một class đơn giản như `Category`, khai báo XML tương đương và đảm bảo bootstrap.

### 30.3. Bước 3 — Giữ schema không đổi

Mục tiêu lượt đầu chỉ là **đổi nơi khai báo metadata**, không đồng thời rename tables/columns.

Nếu cả mapping và schema cùng thay đổi, rất khó xác định lỗi đến từ đâu.

### 30.4. Bước 4 — Chuyển từng relationship

Đặc biệt cẩn trọng với:

- Owning side.
- `mappedBy`.
- Join columns.
- Collection type.
- Lazy/EAGER.
- Cascades.
- OrphanRemoval.
- Embedded IDs và maps.

### 30.5. Bước 5 — Xử lý annotations cũ

Có thể:

- Gỡ annotations sau khi XML-only mapping đã được xác nhận.
- Hoặc dùng `metadata-complete` đúng phạm vi để tắt ảnh hưởng metadata JPA annotations còn sót.

Không để annotation và XML **mâu thuẫn ngầm** mà không có chủ ý.

### 30.6. Bước 6 — Bootstrap và round-trip tests

Kiểm tra tạo EntityManagerFactory, persist, find, update, remove, lazy loading và JPQL. Xác nhận SQL/tables/columns thực tế.

### 30.7. Bước 7 — Chuyển tiếp những entity phức tạp

Sau khi mẫu migration đơn giản thành công mới chuyển:

- Composite keys.
- Inheritance hierarchies.
- Bidirectional associations.
- Collections.
- Listeners.
- Converters.
- Optimistic versioning.

### 30.8. Bước 8 — CI phải bắt lỗi XML sớm

XML metadata errors nên làm build/integration tests fail, không đợi production traffic mới bootstrap lần đầu.

## 31. Quy trình migration từ orm.xml sang annotations

Trường hợp ngược: đội ngũ muốn tập trung metadata trở lại source Java.

1. Xác định effective mappings trong XML, kể cả defaults.
2. Thêm annotations tương ứng trên entity classes.
3. Chọn field/property access nhất quán.
4. Giữ chính xác table, column, join và generator names.
5. Xử lý listeners và converters.
6. Loại bỏ hoặc giảm XML override dần.
7. Tránh để tệp XML cũ tiếp tục ghi đè annotations mới mà team không biết.
8. Test schema compatibility, CRUD, cascades, inheritance và queries.
9. Deploy với migrations nếu có thay đổi DB thật.

### 31.1. Bẫy thường gặp

Team thêm:

```java
@Table(name="products_v2")
```

nhưng `orm.xml` vẫn có:

```xml
<table name="products"/>
```

Nếu mapping XML override vẫn có hiệu lực, runtime có thể tiếp tục dùng bảng cũ.

Không được coi source annotation là **effective metadata** khi mapping XML chưa được xem xét.

## 32. Nhiều persistence units và mapping files

Một ứng dụng có thể có:

```text
catalogPU -> catalog-orm.xml
billingPU -> billing-orm.xml
```

Có thể cấu hình:

```xml
<persistence-unit name="catalogPU">
    <mapping-file>META-INF/catalog-orm.xml</mapping-file>
</persistence-unit>

<persistence-unit name="billingPU">
    <mapping-file>META-INF/billing-orm.xml</mapping-file>
</persistence-unit>
```

Đây là các fragments minh họa bên trong `persistence.xml`.

### 32.1. Cùng một class có thể có mapping khác nhau?

Một class Java có thể được xem xét trong nhiều persistence units với metadata khác nhau khi bootstrap riêng phù hợp. Nhưng phải kiểm soát:

- Những entities nào thuộc mỗi unit.
- Database/datasource mà mỗi factory trỏ tới.
- Transactions chạy qua một hay nhiều units.
- Classpath resources được load.
- Không vô tình dùng `EntityManager` của unit này với entity chỉ thuộc unit khác.

### 32.2. Không trộn nhiều XML overrides không có quy tắc

Nếu một Product được khai báo trong hai XML mappings với tên bảng khác nhau, không nên dựa vào thứ tự load file do tình cờ trên classpath. Thiết kế cấu hình để mỗi persistence unit có một mapping nhất quán, và để bootstrap/test phát hiện mâu thuẫn sớm.

### 32.3. Đừng đánh đồng multi-tenancy với nhiều mapping files

Multi-tenancy có nhiều chiến lược: chung schema có tenant discriminator, schema per tenant, database per tenant. Chọn annotation/XML không tự giải quyết tenant isolation; cần transaction/data access và security policy riêng.

## 33. Annotation, orm.xml và provider-specific mapping

Chuẩn JPA bảo đảm **một tập metadata portable**. Tuy nhiên, Hibernate, EclipseLink và các provider khác có extensions riêng.

Ví dụ một project có thể dùng:

- Hibernate-specific annotation cho formula, filters, soft-delete hoặc SQL customization.
- EclipseLink-specific annotations hoặc descriptors.
- Provider-specific XML mapping ngoài schema `orm.xml` chuẩn.
- Config riêng cho second-level cache/query cache.
- SQL dialect-specific types.

### 33.1. orm.xml chuẩn không thay mọi extension

Không thể khẳng định mọi vendor-specific annotation đều có một phần tử tương đương trong chuẩn `orm.xml`.

Nếu dự án đang dùng `@Formula` hay một extension khác, cần tìm hiểu extension XML tương ứng (nếu có) hoặc giữ provider-specific annotation/adapter; không tự bịa cú pháp XML trong namespace JPA.

### 33.2. Tính portable của một mapping

| Mapping | Mức portable tương đối |
| --- | --- |
| `@Entity`, `@Id`, `@ManyToOne` chuẩn | Cao trong phạm vi JPA |
| `<entity>`, `<id>`, `<many-to-one>` chuẩn | Cao nếu dùng đúng XML schema/version |
| Hibernate-specific annotations | Phụ thuộc Hibernate |
| Hibernate-specific XML | Phụ thuộc Hibernate |
| Custom SQL columnDefinition hoặc dialect | Có thể phụ thuộc DBMS |
| Database-generated expressions/triggers | Phụ thuộc DBMS |

### 33.3. Đổi annotation thành XML không tự làm ứng dụng portable hơn

Tính portable phụ thuộc **các mapping semantics được sử dụng**, không chỉ hình thức khai báo. Một XML chứa provider extension hoặc column definitions chuyên biệt vẫn có vendor lock-in.

## 34. Những điều không nên đặt trong mapping metadata

JPA mapping mô tả **lưu trữ và quan hệ**. Nó không nên trở thành nơi chứa toàn bộ business logic.

Ví dụ những nhu cầu khác nhau:

| Nhu cầu | Lớp giải quyết phù hợp |
| --- | --- |
| Product.price không âm | Bean Validation/domain + DB CHECK |
| Customer có quyền mua Product không | Domain/application service |
| Product thuộc tenant đúng không | Authorization/transactional access |
| Giá thay đổi trong lúc checkout | Transaction/version/locking policy |
| Gửi email sau khi đơn commit | Outbox/after-commit workflow |
| Bảng Products gọi tên gì | JPA annotation/XML mapping |
| Cột SKU bắt buộc | Mapping + DB NOT NULL |
| Tạo mới cột SKU trong production | Migration |
| Lịch sử migration | Flyway/Liquibase/SQL scripts |

### 34.1. XML không phải công cụ giải quyết lỗi transaction

Nếu transaction gặp `OptimisticLockException` hoặc deadlock, đổi annotation sang XML không xử lý được. Phải thiết kế rollback/retry/locking đúng.

### 34.2. Nullability trong mapping không đủ

`@Column(nullable=false)` hoặc `<column nullable="false"/>` không có nghĩa giá trị Java được validate ở mọi đường code trước khi gọi persistence. Dùng Bean Validation/domain checks nếu cần phản hồi lỗi sớm; DB constraint là bảo vệ cuối.

### 34.3. Mapping không tự giải quyết identity equality

Dù dùng XML hay annotation, `equals/hashCode` trên entities với generated IDs vẫn cần thiết kế phù hợp. Nó không tự thay đổi chỉ vì nơi khai báo `@Id` khác đi.

## 35. Mức độ dễ debug khi gặp SQL lỗi

Một lỗi database:

```text
column "category_id" does not exist
```

có thể xuất phát từ:

- Annotation `@JoinColumn` sai.
- XML override đang dùng tên cũ.
- Physical naming strategy của provider.
- Migration chưa chạy.
- Query native viết cột sai.
- Application đang connect nhầm schema.

### 35.1. Debug annotation-only

Mở `Product.java`, tìm `@JoinColumn` và `@Table`; đối chiếu SQL generated và schema.

### 35.2. Debug XML-only

Mở `META-INF/orm.xml` và mapping resources được load; tìm `<many-to-one>` và `<join-column>`.

### 35.3. Debug hybrid

Phải xem **cả annotations và XML**. Không kết luận từ một file riêng rằng đó là effective mapping.

### 35.4. Những thông tin cần log ở development/test

- JPA provider/version.
- Persistence unit name.
- Mapping files/classes được bootstrap.
- Generated SQL và bind parameter diagnostics ở môi trường cho phép.
- Schema/database URL đã chọn (không ghi credentials).
- Migrations/schema version.
- Runtime metamodel nếu cần.

**Không bật SQL parameter logging chứa dữ liệu nhạy cảm trong production một cách thiếu kiểm soát.**

## 36. Dùng JPA Metamodel để kiểm tra effective mapping

Provider tạo runtime metamodel từ **metadata cuối cùng đã hợp nhất**.

```java
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.metamodel.EntityType;
import jakarta.persistence.metamodel.Metamodel;

Metamodel model = emf.getMetamodel();

EntityType<Product> productType =
    model.entity(Product.class);

System.out.println(productType.getName());

System.out.println(
    productType.getAttribute("category")
        .getPersistentAttributeType()
);
```

Metamodel giúp kiểm tra:

- Product có được đăng ký làm entity không.
- Persistent attributes có được provider nhận diện không.
- Relationship type có phù hợp không.

### 36.1. Metamodel không phải toàn bộ SQL schema inspector

JPA Metamodel chuẩn không cung cấp toàn bộ chi tiết vật lý như tên database column, index/constraint hay effective SQL table names theo mọi provider.

Để xác nhận những chi tiết vật lý đó, cần kết hợp:

- DDL/schema inspection.
- SQL generated by provider.
- Mapping metadata provider-specific khi cần.
- Integration tests.

### 36.2. Kiểm tra missing attribute

Nếu XML vẫn dùng tên cũ:

```xml
<basic name="legacyPrice"/>
```

nhưng Java chỉ còn `price`, việc tạo EntityManagerFactory có thể thất bại hoặc metamodel không có attribute mong muốn. CI bootstrap sẽ phát hiện sớm hơn production traffic.

### 36.3. Static metamodel và XML

Criteria API vẫn có thể dùng type-safe metamodel generation phù hợp nếu toolchain biết effective JPA managed model. Với XML-only entities, annotation processors chỉ nhìn Java annotations có thể không đủ. Cần xem khả năng của generator/build plugin hoặc dùng Criteria path names có test thích hợp.

Không tự giả định code generation tool nhận XML mapping chỉ vì JPA runtime nhận.

## 37. Kiểm thử so sánh hai cấu hình mapping

Một chiến lược migration an toàn là chạy **cùng bộ kiểm thử nghiệp vụ** với hai mapping configurations khi có thể.

### 37.1. Bộ kiểm thử tối thiểu

1. Bootstrap EntityManagerFactory thành công.
2. Product, Category xuất hiện trong metamodel.
3. Persist Category.
4. Persist Product tham chiếu Category.
5. Commit và mở EntityManager mới.
6. Load Product bằng `find()`.
7. Kiểm tra `product.getCategory().getId()` đúng.
8. Kiểm tra `price` round-trip đúng precision/scale.
9. Update price và kiểm tra versioning.
10. Query Product bằng JPQL join.
11. Thử lưu Product thiếu Category để xem constraints/validation.
12. Remove Product đúng transaction.
13. Đối chiếu database tables/columns/FKs/unique constraints.

### 37.2. Ví dụ JPA round-trip

```java
EntityManager em = emf.createEntityManager();

try {
    EntityTransaction tx = em.getTransaction();
    tx.begin();

    Category category = new Category(
        10L, "KEYBOARDS", "Keyboards"
    );

    Product product = new Product(
        101L,
        "KB-101",
        "Keyboard",
        new BigDecimal("120.00"),
        category
    );

    em.persist(category);
    em.persist(product);

    tx.commit();
} finally {
    em.close();
}

EntityManager verifyEm =
    emf.createEntityManager();

try {
    Product loaded =
        verifyEm.find(Product.class, 101L);

    if (loaded == null) {
        throw new AssertionError("Product not found");
    }

    if (!Long.valueOf(10L).equals(
            loaded.getCategory().getId())) {
        throw new AssertionError("Wrong category");
    }
} finally {
    verifyEm.close();
}
```

Đây là test illustration, cần database fixture trống hoặc ID hợp lệ không trùng, rollback/cleanup khi lỗi và datasource đã được cấu hình.

### 37.3. Test phải dùng EntityManager mới

Nếu persist và find ngay trong cùng persistence context, `find()` có thể trả managed instance từ first-level cache, không chứng minh mapping đọc lại database đúng.

### 37.4. Test schema thật

Nếu code có `@Column(unique = true)` hoặc XML `unique="true"`, database production/test được tạo bằng migration vẫn phải có unique constraint. Không chỉ kiểm tra entity metadata hoặc schema-generation settings.

### 37.5. Đừng dùng một in-memory database làm bằng chứng tuyệt đối

H2 hoặc DB khác có thể có naming, generated keys và SQL dialect khác PostgreSQL/Oracle/MySQL production. Với mapping quan trọng, integration test nên dùng DBMS gần production (ví dụ Testcontainers) và migrations thực tế.

## 38. Những sai lầm thường gặp

### Sai lầm 1 — Nhầm orm.xml và persistence.xml

`persistence.xml` bootstrap persistence unit; `orm.xml` cung cấp mapping metadata. Chúng không thay nhau hoàn toàn.

### Sai lầm 2 — Nghĩ phải chọn đúng một trong hai và không thể kết hợp

JPA hỗ trợ annotation-only, XML-only và hybrid. Điều cần quản lý là effective metadata và override rules.

### Sai lầm 3 — Tạo orm.xml nhưng file không được load

Đường dẫn classpath, packaging hoặc persistence unit sai làm mapping không có hiệu lực. Cần bootstrap test.

### Sai lầm 4 — Tin Java annotations luôn thắng XML

Khi XML override được dùng, effective mapping có thể khác source annotations. Phải xem cả hai.

### Sai lầm 5 — Bật metadata-complete khi chỉ muốn đổi một tên cột

Metadata JPA annotations khác trong phạm vi đó có thể không còn được sử dụng, làm thiếu mapping mong muốn.

### Sai lầm 6 — Để hai nguồn khai báo mapping mâu thuẫn

`@Table("products")` và XML `<table name="catalog_products"/>` không nên tồn tại ngầm nếu team không nhận biết override.

### Sai lầm 7 — Đổi tên Java field mà quên XML

Compiler có thể không phát hiện string `name="legacyField"`; runtime bootstrap mới báo.

### Sai lầm 8 — Chuyển field access sang property access vô tình

Provider có thể map khác hoặc không tìm thấy getters/setters phù hợp.

### Sai lầm 9 — Quên relationship owning side

`mappedBy` trỏ tới persistent attribute ở owning entity, không phải column name.

### Sai lầm 10 — Quên fetch, cascade hoặc orphanRemoval khi chuyển mapping

Behavior khi load/persist/remove children có thể thay đổi mà schema trông vẫn giống.

### Sai lầm 11 — Cho rằng XML mapping có thể biến mọi class thành entity

Class vẫn phải đáp ứng JPA entity requirements; final classes/constructors/accessors có thể không phù hợp.

### Sai lầm 12 — Nghĩ annotation @Column tự chạy migration

Mapping metadata không tự thay đổi database production khi migration pipeline đang được dùng.

### Sai lầm 13 — Dùng drop-and-create ở production để thử XML

Có thể xóa dữ liệu. Dùng migration có kiểm soát và test database riêng.

### Sai lầm 14 — Quên @Version hoặc XML <version> khi chuyển

Optimistic locking behavior có thể mất đi, tạo nguy cơ lost updates.

### Sai lầm 15 — Quên converter/enum storage

Dữ liệu persisted có thể không đọc được hoặc mất tương thích.

### Sai lầm 16 — Đăng ký cùng listeners lặp ở nhiều tầng

Có thể tạo callback duplicate/hành vi khó suy luận. Cần rõ default/entity/superclass listeners.

### Sai lầm 17 — Dùng metadata XML làm transaction after-commit hooks

Lifecycle callbacks không phải sự kiện sau commit, dù được đăng ký trong XML.

### Sai lầm 18 — Tưởng XML mapping thay thế database constraints

FK/UNIQUE/CHECK ở database vẫn cần thiết khi invariant yêu cầu.

### Sai lầm 19 — Coi provider-specific XML là portable JPA orm.xml

Không phải mọi XML format đều thuộc chuẩn Jakarta Persistence.

### Sai lầm 20 — Cho rằng đổi sang XML tự xóa vendor lock-in

Nếu vẫn dùng proprietary SQL/types/features, tính portable không tự tăng.

### Sai lầm 21 — Coi XML là hot reload configuration

EntityManagerFactory thường không tự rebuild metadata khi file XML trên disk đổi.

### Sai lầm 22 — Chỉ unit test POJO, không bootstrap EntityManagerFactory

Lỗi mapping XML thường chỉ lộ ở bootstrap hoặc truy vấn/flush thực tế.

### Sai lầm 23 — Dùng cùng một EntityManager để kiểm tra round-trip DB

First-level cache có thể che lỗi SQL mapping trong lượt đọc.

### Sai lầm 24 — Cho rằng Hibernate ddl-auto thay thế lịch sử migration

Tự đồng bộ schema ở runtime không tạo một quy trình versioned migration an toàn.

### Sai lầm 25 — Không tài liệu hóa tên persistence unit và mapping files

Trong multi-module app, developer có thể sửa file XML không hề được unit đang chạy sử dụng.

## 39. Bài tập thực hành

### Bài 1 — Chọn cách ánh xạ

Dự án có 8 entities, team sở hữu toàn bộ Java classes, mapping ổn định.

**Gợi ý:** Ưu tiên annotations để dễ đọc và refactor, vẫn giữ schema migrations riêng.

### Bài 2 — Lớp không tiện sửa

Một shared library chứa POJO `Product` đáp ứng yêu cầu JPA entity nhưng không muốn phụ thuộc `jakarta.persistence`.

**Gợi ý:** Cân nhắc XML-only mapping trong persistence module. Phải kiểm tra constructor/class/access requirements.

### Bài 3 — Đổi một tên bảng

`@Entity` và các field annotations đã đúng, chỉ cần map Product sang bảng `catalog_products`.

**Gợi ý:** XML override hẹp; không bật metadata-complete nếu còn dùng những annotations khác.

### Bài 4 — Vì sao lỗi sau metadata-complete?

XML chỉ khai báo `id` và `sku`, class Java còn nhiều `@ManyToOne`/`@Version` annotations nhưng `metadata-complete="true"`.

**Đáp án:** Các JPA annotations bị loại khỏi nguồn mapping theo phạm vi; XML cần cung cấp metadata phù hợp hoặc không dùng metadata-complete cho partial override.

### Bài 5 — Đường dẫn orm.xml

File đặt `src/main/resources/META-INF/orm.xml`.

**Câu hỏi:** `<mapping-file>` dùng tên gì?

**Đáp án minh họa:** `META-INF/orm.xml`, nếu resource được đóng gói ở classpath tương ứng.

### Bài 6 — Tên thuộc tính

Java đổi `category` thành `productCategory`, nhưng XML còn:

```xml
<many-to-one name="category"/>
```

**Đáp án:** XML phải được cập nhật theo tên persistent member, rồi bootstrap/test.

### Bài 7 — mappedBy

Phía Product có attribute `category`, Category.products dùng one-to-many.

**Câu hỏi:** `mapped-by` là `category` hay `category_id`?

**Đáp án:** `category` — tên Java persistent attribute ở phía sở hữu.

### Bài 8 — Quên LAZY

Annotation dùng `@ManyToOne(fetch=LAZY)`, XML chuyển sang `<many-to-one name="category"/>`.

**Đáp án:** Có thể thay đổi fetch default, gây SQL/lazy behavior khác. Cần diễn đạt `fetch="LAZY"` nếu đó là ý định.

### Bài 9 — Nullability và unique

XML map SKU, muốn non-null, unique và max 50 chars.

**Đáp án:** `<basic name="sku" optional="false"><column name="sku" nullable="false" unique="true" length="50"/></basic>`.

### Bài 10 — ID generation

Entity trước dùng `GenerationType.SEQUENCE` với allocationSize 20, sau XML migration lại dùng IDENTITY.

**Đáp án:** Đây không chỉ là đổi cú pháp; generation behavior, schema, batching và performance có thể thay đổi. Phải giữ metadata tương ứng hoặc chủ động migration.

### Bài 11 — Schema generation

Đổi XML `<column name="price"/>` thành `<column name="unit_price"/>`, production DB vẫn có `price`.

**Đáp án:** Cần migration schema và rollout phù hợp; XML không tự rename cột.

### Bài 12 — Default listener

Muốn một listener áp dụng cho phần lớn entities mà không gắn trên từng class.

**Gợi ý:** XML `persistence-unit-defaults/entity-listeners`; xác định exceptions và callback timing.

### Bài 13 — Multi persistence units

`catalogPU` và `billingPU` cần mapping files khác nhau.

**Gợi ý:** Khai báo mapping-file riêng cho từng unit, tránh dùng nhầm EntityManagerFactory.

### Bài 14 — XML-only static metamodel

JPA runtime load XML-only entity thành công, nhưng annotation processor không tạo `Product_`.

**Đáp án:** Runtime metadata và code generation toolchain không giống nhau; cần generator hỗ trợ XML hoặc chiến lược Criteria khác.

### Bài 15 — Migration hoàn tất?

Unit test instantiate Product và gọi getter thành công.

**Đáp án:** Chưa. Cần bootstrap persistence unit, persist/find/update/JPQL/constraint tests với DB thật.

### Bài 16 — Hibernate extension

Product dùng provider-specific `@Formula`. Team muốn XML-only chuẩn JPA.

**Đáp án:** Không được giả định có XML equivalent portable cho mọi extension. Cần giữ extension hoặc dùng mô hình/provider API tương ứng và ghi nhận vendor dependency.

### Bài 17 — Access strategy

JPA annotations ở getters nhưng XML chọn `access="FIELD"`.

**Đáp án:** Có thể thay đổi mapping semantics; cần chọn field/property access có chủ đích và kiểm tra toàn bộ attributes.

### Bài 18 — Named queries và entity names

JPQL `SELECT p FROM Product p` từng hoạt động; XML mới khai báo entity name khác.

**Đáp án:** Queries có thể cần cập nhật. JPQL sử dụng JPA entity names, không phải SQL table names.

### Bài 19 — Dự án nhiều environments

Team muốn một XML cho development và một XML cho production để dùng tên bảng khác.

**Gợi ý:** Chỉ làm nếu thực sự cần và có packaging/configuration test riêng. Thường giữ schema naming thống nhất và thay datasource/connection là dễ bảo trì hơn.

### Bài 20 — Chọn hybrid hay XML-only

Một dự án có 60 entities annotations ổn định, chỉ 2 entities cần override bảng/cột vì legacy integration.

**Gợi ý:** Hybrid override có giới hạn dễ kiểm soát hơn chuyển toàn bộ 60 entities sang XML-only.

## 40. Câu hỏi tự kiểm tra

**1. JPA mapping metadata có thể được khai báo bằng những hình thức tiêu chuẩn nào?**

Java annotations và XML mapping metadata `orm.xml`; có thể phối hợp khi đúng quy tắc.

**2. `persistence.xml` có giống `orm.xml` không?**

Không. Một bên bootstrap persistence unit, bên kia định nghĩa entity mapping metadata.

**3. Annotation tương ứng với `<entity>` là gì?**

`@Entity`.

**4. Annotation tương ứng với `<id>` là gì?**

`@Id`.

**5. `<many-to-one>` tương ứng annotation nào?**

`@ManyToOne`.

**6. `<join-column>` dùng để khai báo gì?**

Thông tin join/foreign key column của relationship.

**7. Một class không có `@Entity` có thể được map bằng XML không?**

Có nếu class đáp ứng yêu cầu JPA và được khai báo trong metadata XML/persistence unit phù hợp.

**8. Annotation hay XML có thay đổi EntityManager API không?**

Không. Cùng provider/API hoạt động trên effective mapping.

**9. Khi nào annotation thường phù hợp hơn?**

Khi sở hữu source classes, mapping ổn định, muốn code và metadata gần nhau.

**10. Khi nào XML có lợi?**

Khi cần tách metadata khỏi source, map classes không tiện sửa hoặc override mapping có chủ đích.

**11. Hybrid mapping là gì?**

Kết hợp annotations làm nguồn chính với XML bổ sung/ghi đè một số metadata.

**12. XML override có thể làm effective table khác `@Table` không?**

Có, theo quy tắc XML/annotation metadata tương ứng.

**13. Có nên bật metadata-complete để chỉ đổi tên một cột không?**

Không nên; partial override thường phù hợp hơn.

**14. `metadata-complete` ở entity dùng để làm gì?**

Quy định metadata XML-complete cho entity đó trong phạm vi JPA.

**15. `xml-mapping-metadata-complete` có phạm vi thế nào?**

Rộng hơn, cấp persistence unit theo XML mapping metadata.

**16. JPA annotations ngoài mapping có tự bị xóa bởi metadata-complete không?**

Không. Nó không phải công tắc vô hiệu mọi annotation/framework.

**17. `access="FIELD"` trong XML có nghĩa gì?**

Persistent state được ánh xạ theo field access.

**18. Vì sao chuyển giữa FIELD và PROPERTY có thể gây lỗi?**

Provider đọc/ghi members khác và có thể cần getters/setters khác.

**19. `mappedBy` và `mapped-by` trỏ tới cột DB hay Java attribute?**

Java persistent attribute ở phía sở hữu quan hệ.

**20. Chuyển annotations sang XML có cần giữ cascade và fetch không?**

Có, nếu muốn semantics không đổi.

**21. `@Version` có XML equivalent không?**

Có, `<version name="...">`.

**22. Cần làm gì khi dùng XML-only với IDENTITY?**

Khai báo `<generated-value strategy="IDENTITY"/>` phù hợp ở ID mapping và kiểm tra schema/database.

**23. `@Column(nullable=false)` có tự chạy migration production không?**

Không.

**24. Chỉnh `orm.xml` có tự cập nhật EntityManagerFactory đang hoạt động không?**

Không nên giả định; thường cần rebuild/restart/rebootstrap.

**25. Có nên dùng `drop-and-create` trên production DB để thử mapping không?**

Không, vì có thể làm mất dữ liệu.

**26. Tính portable phụ thuộc hình thức annotation/XML hay feature semantics?**

Phụ thuộc cả việc dùng các tính năng chuẩn hay provider-specific, không chỉ hình thức.

**27. Có phải mọi Hibernate annotation đều có tag tương đương trong JPA orm.xml chuẩn không?**

Không.

**28. Khi nào kiểm thử mapping mới đúng nghĩa?**

Bootstrap EntityManagerFactory, CRUD round-trip và schema/relationship/transaction tests với DB phù hợp.

**29. JPA metamodel giúp kiểm tra điều gì?**

Những managed entities và attributes/type mappings mà provider nhận diện sau bootstrap.

**30. Khi dùng XML, rủi ro refactor lớn là gì?**

Tên class/field trong XML là chuỗi, có thể lệch khi Java code đổi tên.

**31. Query JPQL dùng tên bảng hay entity?**

Tên JPA entity và persistent attribute, không phải trực tiếp table/column SQL.

**32. XML có thay thế database constraints không?**

Không.

**33. XML default schema có tự tạo schema đó không?**

Không; cần schema/migration và quyền database phù hợp.

**34. Vì sao cần xem cả annotations lẫn orm.xml khi debug hybrid?**

Vì XML override có thể làm effective mapping khác source annotation.

**35. Lựa chọn thực tiễn cho đa số dự án mới tự sở hữu entities là gì?**

Bắt đầu bằng annotations; chỉ thêm XML khi có lợi ích cụ thể và đủ test.

## 41. Một kịch bản thực tế: chuyển metadata của legacy catalog

Một công ty có catalog database lâu năm:

```text
Database:
  LEGACY_PRODUCT_ITEM
    PROD_ID
    PROD_CODE
    UNIT_PRICE
    CAT_REF
    ROW_VERSION

Java:
  Product
    id
    sku
    price
    category
    version
```

Team muốn áp JPA nhưng không muốn code domain import Jakarta Persistence. Đồng thời có hai applications dùng cùng Java module:

- `catalog-read-service`: chỉ đọc.
- `catalog-admin-service`: đọc và cập nhật.

### 41.1. Đề xuất mapping module

```text
catalog-domain/
  Product.java
  Category.java

catalog-persistence/
  src/main/resources/META-INF/
    persistence.xml
    orm.xml
  repository + integration tests

catalog-app/
  application service + HTTP API
```

XML ánh xạ bảng/column names hiện có, ví dụ:

```xml
<entity class="com.example.catalog.Product" access="FIELD">
    <table name="LEGACY_PRODUCT_ITEM"/>

    <attributes>
        <id name="id">
            <column name="PROD_ID"/>
        </id>

        <basic name="sku">
            <column name="PROD_CODE" length="50"/>
        </basic>

        <basic name="price">
            <column name="UNIT_PRICE"
                    precision="14" scale="2"/>
        </basic>

        <many-to-one name="category" fetch="LAZY">
            <join-column name="CAT_REF"/>
        </many-to-one>

        <version name="version">
            <column name="ROW_VERSION"/>
        </version>
    </attributes>
</entity>
```

### 41.2. Vì sao XML có lợi trong trường hợp này?

- Java domain classes ít phụ thuộc persistence-specific naming.
- DDL legacy có tên cột khó đọc nhưng được cô lập trong mapping.
- Một thay đổi tên cột database không bắt team thêm annotation vào domain.
- Admin/read service có thể chia sẻ mô hình và mapping contract nếu schema giống nhau.

### 41.3. Điều cần bảo vệ

- Schema legacy còn nhiều constraints/triggers.
- Một số relationships có thể không có FK thực.
- ID generation có thể do legacy system kiểm soát.
- Native SQL writers vẫn có thể sửa dữ liệu ngoài JPA.
- Optimistic versioning chỉ hiệu quả nếu mọi đường cập nhật tương thích.
- Read service và admin service phải thống nhất entity name/field semantics.
- Mapping XML được package đúng với từng persistence unit.
- Migrations phải có quy trình riêng.

### 41.4. Khi nào hybrid tốt hơn XML-only trong chính kịch bản đó?

Nếu domain module đã có `@Entity`/`@Id` và các relationships ổn định, chỉ khác table/column naming ở legacy database, việc giữ annotations và override một số metadata trong XML có thể giảm chi phí chuyển đổi.

### 41.5. Khi nào nên tách domain và persistence entities hoàn toàn?

Nếu model domain cần dùng records/immutable types hoặc có lifecycle không phù hợp với JPA entity requirements, việc cố dùng `orm.xml` để “map trực tiếp” có thể gây phức tạp. Một persistence adapter class được map bằng JPA, rồi chuyển sang domain objects, có thể rõ ràng hơn.

## 42. Bảng khuyến nghị theo tình huống

| Tình huống | Lựa chọn thường phù hợp | Cần lưu ý |
| --- | --- | --- |
| Ứng dụng CRUD mới, 10–50 entities | **Annotations** | Refactor dễ, SQL migrations riêng |
| Team sở hữu mọi entity classes | **Annotations** | Tránh metadata XML trùng |
| Một vài cột/bảng cần override | **Hybrid** | Test effective mapping, không bật metadata-complete không cần |
| Domain POJOs không được thêm JPA annotations | **XML-only** | Kiểm tra JPA entity requirements |
| Database legacy tên bảng/cột khó, mapping nhiều | **XML hoặc hybrid** | Explicit names, schema tests |
| Nhiều deploy environments cùng schema | **Annotations hoặc XML cố định** | Thường chỉ thay datasource/properties |
| Nhiều persistence units với mappings khác | **XML/hybrid có tổ chức** | Mapping files per unit, không nhầm EMF |
| Entity inheritance/relations phức tạp | **Tùy team** | Mapping tests đặc biệt quan trọng |
| Provider-specific features | **Cách provider hỗ trợ** | Không tự coi là portable JPA |
| Chuyển annotation sang XML dần dần | **Hybrid tạm thời** | Theo dõi ownership và metadata-complete |
| Muốn đổi schema production | **Migration** | Annotation/XML không thay DDL deployment |
| Muốn thay runtime metadata không restart | **Không phải lựa chọn mặc định** | EMF cần bootstrap lại |

## 43. Những nguyên tắc tổ chức dự án

### 43.1. Một entity, một nguồn mapping chủ đạo

Khi dùng annotation-first, đặt phần lớn metadata trong Java và chỉ dùng XML cho override cụ thể. Khi XML-first, xác định rõ phạm vi XML-complete và hạn chế annotations JPA không cần thiết.

### 43.2. Mapping files được sở hữu rõ

Mỗi XML mapping file nên có maintainer, module và persistence unit xác định. Tránh một file shared chứa cả catalog, billing và HR entities nếu không có lý do.

### 43.3. Đổi metadata luôn phải có integration test

Unit tests của POJO không thể xác nhận SQL mapping. Build CI cần bootstrap runtime mapping và thao tác trên schema phù hợp.

### 43.4. Migrations được review cùng metadata

Một PR đổi `@Column` hoặc `<column>` nên trả lời:

- DB schema có đổi không?
- Migration nào tạo/đổi cột?
- Deployment có nhiều app versions cùng chạy không?
- Dữ liệu cũ có cần chuyển không?
- Có index/FK/constraint cần cập nhật không?

### 43.5. Không che giấu provider defaults

Khi một hành vi quan trọng cho correctness, khai báo rõ thay vì dựa vào default khó nhớ. Ví dụ: fetch strategy, `mappedBy`, optimistic version, generated ID sequence, nullable constraints và join columns.

### 43.6. Giữ XML có thể đọc được

Chia file theo module/aggregate khi phù hợp, đặt class names nhất quán, không lạm dụng copy-paste metadata dài và không nhét business workflow vào mapping file.

## 44. Kết luận

**Annotation và `orm.xml` là hai hình thức chuẩn để đưa JPA mapping metadata vào runtime.** Chúng sử dụng cùng entity lifecycle, `EntityManager`, JPQL, Criteria API và transaction semantics. Sự khác biệt cốt lõi là **vị trí đặt thông tin, cách tổ chức và khả năng ghi đè metadata**, chứ không phải khả năng “JPA làm việc với database theo hai cơ chế khác nhau”.

Những điểm cần ghi nhớ:

1. **Annotation-first** là lựa chọn mặc định hợp lý cho ứng dụng tự sở hữu Java entity classes, cần đọc mapping gần code và refactor thường xuyên.
2. **XML-only** phù hợp khi muốn tách JPA metadata khỏi classes hoặc phải map những POJOs không tiện chỉnh sửa, miễn chúng vẫn đáp ứng JPA entity requirements.
3. **Hybrid** hữu ích cho một số overrides, nhưng cần hiểu rõ precedence và tránh “hai nguồn sự thật” mâu thuẫn.
4. **`metadata-complete` không phải chỉ là một cờ vô hại.** Nó có thể loại ảnh hưởng của JPA annotations trong phạm vi áp dụng; chỉ dùng khi muốn XML thực sự là nguồn metadata đầy đủ.
5. **`persistence.xml` và `orm.xml` có vai trò riêng.** Đặt file trong classpath đúng và kiểm tra persistence unit đã load resource.
6. **Field/property access, ID, relationships, fetch, cascade, version và converters** phải được giữ nguyên về semantics nếu chỉ chuyển cách khai báo.
7. **Metadata không phải migration.** Tên bảng/cột/FK thực tế phải được quản lý bằng schema/DDL pipeline phù hợp.
8. **Provider-specific features không tự trở thành portable** chỉ vì chuyển sang XML.
9. **Runtime metamodel và integration tests** là cách thiết thực để xác nhận effective mapping, nhất là khi annotation và XML cùng được dùng.
10. **Chọn giải pháp dễ bảo trì nhất trong bối cảnh thật**: ít duplication, có ownership rõ, test được và không che giấu những quy tắc ảnh hưởng dữ liệu.

Một dự án JPA trưởng thành không cần chọn annotation hay XML theo sở thích tuyệt đối. Điều quan trọng là xây dựng **một hợp đồng mapping nhất quán với Java model, database schema và transaction requirements**, rồi sử dụng annotations, `orm.xml` hoặc sự kết hợp có kiểm soát để duy trì hợp đồng đó qua các lần phát triển và triển khai.
