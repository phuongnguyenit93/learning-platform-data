# Ghi đè ánh xạ bằng XML và quản lý nguồn cấu hình trong JPA

Trong Java Persistence API (JPA), developer thường ánh xạ entity bằng annotations như `@Entity`, `@Table`, `@Column`, `@ManyToOne` và `@JoinColumn`. Cách này trực quan vì metadata nằm cạnh Java class. Tuy nhiên, JPA còn hỗ trợ **XML mapping metadata**: cấu hình ánh xạ trong file XML bên ngoài entity source code.

Một dự án có thể dùng XML để:

- Ghi đè tên bảng hoặc cột khi tích hợp với một database legacy.
- Điều chỉnh fetch mapping hoặc ánh xạ quan hệ mà không đặt toàn bộ thông tin vào annotations.
- Dùng entity class không phụ thuộc trực tiếp vào một số JPA annotations trong những trường hợp phù hợp.
- Khai báo named queries, converter và những mapping metadata khác.
- Chuẩn hóa một số defaults cho toàn persistence unit.
- Quản lý tách biệt **nguồn mapping**, **nguồn cấu hình kết nối**, **nguồn schema migration** và **cấu hình môi trường**.

Ví dụ một Java entity:

```java
package com.example.catalog.domain;

import jakarta.persistence.*;

@Entity
@Table(name = "product")
public class Product {

    @Id
    private Long id;

    @Column(name = "product_name", length = 100)
    private String name;

    protected Product() {
    }

    public Product(Long id, String name) {
        this.id = id;
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
```

Một file XML mapping có thể ghi đè tên bảng và tên cột:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<entity-mappings
    xmlns="https://jakarta.ee/xml/ns/persistence/orm"
    version="3.0">

    <entity class="com.example.catalog.domain.Product">
        <table name="catalog_item"/>

        <attributes>
            <basic name="name">
                <column name="display_name" length="200"/>
            </basic>
        </attributes>
    </entity>
</entity-mappings>
```

Trong một persistence unit có file này được nạp đúng và không có cấu hình loại trừ/ghi đè khác, metadata XML cho các thành phần đã khai báo có thể thay thế annotation metadata tương ứng: `product` thành `catalog_item`, `product_name` thành `display_name`.

**Quan trọng:** XML không phải file SQL migration. XML thay đổi **cách JPA hiểu mapping**; nó không tự bảo đảm schema vật lý của database đã được đổi theo.

Bài học thuộc chương **Siêu dữ liệu và lược đồ**, module *Data Persistence Relational Access ORM JPA*. Trọng tâm là **cách sử dụng XML để ghi đè ánh xạ JPA và cách quản lý nguồn cấu hình nhất quán, kiểm chứng được, tránh drift giữa code – mapping – database**.

> **Nguyên tắc cốt lõi:** Xác định một nguồn có thẩm quyền cho từng loại thông tin: **entity mapping**, **persistence-unit setup**, **môi trường chạy**, và **schema evolution**. Chỉ dùng XML overrides khi có lý do cụ thể, kiểm soát rõ phạm vi override và xác minh provider đã nạp đúng file.

---

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt `persistence.xml`, `orm.xml` và các file XML mapping tùy tên.
2. Giải thích vai trò của annotations so với XML mapping metadata.
3. Hiểu ý nghĩa **XML override** và trường hợp **metadata-complete**.
4. Cấu hình để JPA nạp một hoặc nhiều mapping XML files.
5. Ghi đè table, column, ID, generated value, version và mapping association bằng XML.
6. Nhận biết sự khác nhau giữa **field access** và **property access** khi viết XML.
7. Sử dụng defaults, listeners, named queries và attribute overrides một cách có chủ đích.
8. Tránh hiểu nhầm về **thứ tự ưu tiên** khi annotation, XML và runtime settings cùng tham gia.
9. Quản lý cấu hình phát triển, kiểm thử và production mà không nhúng secrets vào repository.
10. Phân biệt thay đổi mapping XML với thay đổi vật lý database schema.
11. Kiểm chứng metadata thực tế bằng JPA Metamodel, SQL logging và integration tests.
12. Xử lý lỗi thường gặp: file không được nạp, sai namespace, sai Java member name, thiếu ID, trùng metadata và schema drift.
13. Thiết lập conventions để mọi developer biết cấu hình nào là nguồn sự thật.

## 2. Hai lớp XML khác nhau trong JPA

JPA có hai loại XML quan trọng nhưng thường bị gọi chung là “JPA XML”:

| Tệp | Mục đích chính | Nội dung điển hình |
|---|---|---|
| `META-INF/persistence.xml` | **Định nghĩa persistence unit** | Provider, transaction type, data source, entity classes, mapping files, properties, caching, validation |
| `META-INF/orm.xml` hoặc file mapping khác | **Định nghĩa hoặc ghi đè mapping metadata** | Entity, table, column, ID, relationship, embedded mapping, named query, listeners |

Sơ đồ:

```text
Application startup
       |
       v
persistence.xml / container or framework configuration
       |
       +-- Persistence unit name
       +-- Provider
       +-- Data source / transaction mode
       +-- Entity discovery
       +-- References to XML mapping files
       |
       v
Mapping metadata resolution
       |
       +-- Java annotations
       +-- orm.xml / other JPA XML mapping files
       +-- Mapping defaults / metadata-complete rules
       |
       v
EntityManagerFactory
       |
       +-- Effective entity model
       +-- Mappings, converters, queries, relationships
       |
       v
SQL generated and executed against real database schema
```

### 2.1. persistence.xml không thay orm.xml

`persistence.xml` không phải nơi bạn viết phần lớn `<entity>` và `<attributes>` mapping metadata. Nó chỉ dẫn cách khởi tạo persistence unit và có thể tham chiếu các mapping files.

### 2.2. orm.xml không thay database migration

`orm.xml` mô tả cách class/property tương ứng với tables/columns. Nếu đặt `<table name="catalog_item"/>`, database vẫn phải có bảng `catalog_item` hoặc một cơ chế schema creation phù hợp; file XML không tự rename bảng đang được sử dụng trong production.

### 2.3. Annotations và XML có thể cùng tồn tại

Một class có `@Entity`, `@Id`, `@Column` vẫn có thể được ánh xạ lại một phần qua XML. Không bắt buộc xóa toàn bộ annotations mỗi khi thêm XML mapping.

### 2.4. Nhưng phải biết ai có quyền quyết định cuối cùng

Nếu table name được khai báo ở annotation và XML, cần biết **XML có được nạp không**, **entity có metadata-complete không**, **provider có extension riêng không** và **có XML mapping file khác khai báo xung đột không**. Đừng dựa vào việc “tên file nghe có vẻ đúng”.

---

## 3. Cấu trúc một persistence unit

Một ví dụ Jakarta Persistence với resource-local transaction:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence
    xmlns="https://jakarta.ee/xml/ns/persistence"
    version="3.0">

    <persistence-unit
        name="catalogPU"
        transaction-type="RESOURCE_LOCAL">

        <provider>
            org.hibernate.jpa.HibernatePersistenceProvider
        </provider>

        <mapping-file>META-INF/catalog-mapping.xml</mapping-file>

        <class>com.example.catalog.domain.Product</class>
        <class>com.example.catalog.domain.Category</class>

        <properties>
            <property
                name="jakarta.persistence.schema-generation.database.action"
                value="none"/>
        </properties>
    </persistence-unit>
</persistence>
```

Các thuộc tính:

- `name="catalogPU"`: tên persistence unit được dùng khi tạo `EntityManagerFactory`.
- `transaction-type="RESOURCE_LOCAL"`: quản lý transaction bằng JPA `EntityTransaction` trong ví dụ thuần Java SE.
- `provider`: implementation JPA được chọn.
- `mapping-file`: đường dẫn resource mapping XML được nạp.
- `class`: khai báo classes trong unit (cách rõ ràng khi muốn explicit registration).
- `properties`: cấu hình JPA/provider theo nhu cầu.

Đây là cấu hình **minh họa**, chưa bao gồm datasource và JDBC driver. Dự án JTA hoặc Spring container-managed transaction có cách quản lý khác; không dùng `em.getTransaction()` trên một JTA-managed `EntityManager`.

### 3.1. persistence.xml đặt ở đâu?

Thông dụng:

```text
src/main/resources/
└── META-INF/
    ├── persistence.xml
    └── catalog-mapping.xml
```

Khi build:

```text
target/classes/ hoặc build/resources/main/
└── META-INF/
    ├── persistence.xml
    └── catalog-mapping.xml
```

Trong một JAR, chúng thường là resources theo cấu trúc classpath.

### 3.2. Đường dẫn mapping-file là đường dẫn resource

```xml
<mapping-file>META-INF/catalog-mapping.xml</mapping-file>
```

không có nghĩa JPA sẽ đọc đường dẫn tuyệt đối kiểu:

```text
C:\projects\catalog\src\main\resources\META-INF\catalog-mapping.xml
```

Trong deployment, provider tìm resource theo quy tắc persistence unit/classpath. Nếu file tồn tại trong source tree nhưng không được đóng gói vào classpath, startup có thể báo mapping file not found.

### 3.3. Tên persistence unit là định danh cấu hình

Ví dụ Java SE:

```java
EntityManagerFactory emf =
    Persistence.createEntityManagerFactory("catalogPU");

try {
    EntityManager em = emf.createEntityManager();
    try {
        // ...
    } finally {
        em.close();
    }
} finally {
    emf.close();
}
```

Tên `catalogPU` phải khớp cấu hình được khởi tạo. Nếu ứng dụng có nhiều persistence units, cần xác định entity thuộc unit nào và mapping file được nạp bởi unit nào.

---

## 4. File orm.xml chuẩn và file mapping tùy tên

Tên mặc định phổ biến là:

```text
META-INF/orm.xml
```

JPA có quy tắc phát hiện mapping resource mặc định này trong persistence unit theo cấu trúc đóng gói thích hợp. Tuy nhiên để dễ vận hành và tránh phụ thuộc ngầm trong dự án phức tạp, có thể **khai báo mapping-file tường minh**, nhất là với file không mang tên mặc định.

### 4.1. Khai báo file tùy tên

```xml
<mapping-file>META-INF/catalog-mapping.xml</mapping-file>
<mapping-file>META-INF/order-mapping.xml</mapping-file>
```

Tách file theo bounded context hoặc domain module có thể giúp review mapping dễ hơn.

### 4.2. Không khai báo cùng một mapping file hai lần theo hai đường

Nếu `META-INF/orm.xml` được provider tự nạp và bạn còn khai báo nó tường minh, cần kiểm tra cách provider xử lý để tránh duplicate resource/metadata. Không nên trông đợi việc nạp lặp đem lại override theo thứ tự có ích.

### 4.3. Không nhầm mapping filename với entity name

File `catalog-mapping.xml` chỉ là resource; entity name mặc định vẫn liên quan Java class hoặc mapping `name` được cấu hình, không tự lấy từ filename.

### 4.4. Nhiều persistence units

```text
catalogPU -> catalog-mapping.xml
billingPU -> billing-mapping.xml
```

Một mapping file được nạp trong `catalogPU` không tự ảnh hưởng `billingPU`. Đồng thời, nếu cùng class được quản lý trong nhiều persistence units với mappings khác nhau, đừng tùy ý trộn EntityManager của hai units khi xử lý cùng transaction/business operation.

---

## 5. XML ghi đè annotations như thế nào?

Một mapping annotation:

```java
@Entity
@Table(name = "products_v1")
public class Product {

    @Id
    private Long id;

    @Column(name = "display_name", length = 120)
    private String name;
}
```

XML:

```xml
<entity-mappings
    xmlns="https://jakarta.ee/xml/ns/persistence/orm"
    version="3.0">

    <entity class="com.example.catalog.domain.Product">
        <table name="catalog_product"/>

        <attributes>
            <basic name="name">
                <column name="product_label" length="200"/>
            </basic>
        </attributes>
    </entity>
</entity-mappings>
```

Nếu XML được áp dụng đúng, metadata explicit trong XML được ưu tiên cho những mapping elements tương ứng. Java property vẫn là `name`, nhưng mapped column là `product_label`.

### 5.1. Ghi đè một phần không có nghĩa bỏ toàn bộ annotations

Nếu XML chỉ khai báo:

```xml
<entity class="com.example.catalog.domain.Product">
    <table name="catalog_product"/>
</entity>
```

thì mục tiêu là override table mapping, trong khi những metadata khác không bị thay bằng khai báo XML tương ứng vẫn có thể đến từ annotations theo quy tắc kết hợp.

### 5.2. Cần phân biệt mức ghi đè

“XML overrides annotations” không có nghĩa một câu chung chung “mọi khai báo trong mọi file XML luôn có ưu tiên tuyệt đối, theo thứ tự file”. Trong thực tế cần xét:

- Phần metadata cụ thể được khai báo bằng XML.
- Sự hiện diện của `metadata-complete`.
- Metadata mặc định theo persistence unit.
- Sự khác nhau giữa entity-level và attribute-level metadata.
- XML mapping declarations trùng nhau.
- JPA specification version và vendor-specific extensions.

### 5.3. Khi cần override, khai báo đúng Java member name

```xml
<basic name="name">
    <column name="product_label"/>
</basic>
```

`name="name"` là **tên persistent Java attribute**, không phải `display_name` hay tên SQL column hiện tại. Nếu viết `<basic name="product_label">` mà class không có attribute như vậy, metadata có thể không hợp lệ.

### 5.4. XML không trực tiếp sửa Java API

Dù database column đổi, method `product.getName()` vẫn là `getName()`; JPQL thường truy cập `p.name` chứ không truy cập `p.product_label`.

---

## 6. Khi nào dùng metadata-complete?

JPA hỗ trợ cách chỉ định một entity hoặc phạm vi mapping dùng **XML làm nguồn ánh xạ đầy đủ**, thay vì kết hợp XML và mapping annotations.

Ví dụ:

```xml
<entity-mappings
    xmlns="https://jakarta.ee/xml/ns/persistence/orm"
    version="3.0">

    <entity
        class="com.example.catalog.domain.Product"
        access="FIELD"
        metadata-complete="true">

        <table name="catalog_product"/>

        <attributes>
            <id name="id"/>

            <basic name="name">
                <column name="product_label" length="200"/>
            </basic>
        </attributes>
    </entity>
</entity-mappings>
```

Ý định: mapping của entity này được định nghĩa bởi XML và không dựa vào JPA mapping annotations tương ứng để lấp những phần bạn quên khai báo.

### 6.1. Vì sao nguy hiểm nếu bật vội?

Khi `metadata-complete="true"`, những mapping elements chỉ tồn tại trong annotations có thể không còn được dùng. Ví dụ:

```java
@Version
private Long version;
```

Nếu XML complete mapping quên khai báo `<version name="version"/>`, optimistic version mapping có thể không được cấu hình như bạn tưởng.

### 6.2. Không chuyển sang metadata-complete chỉ để đổi tên một cột

Nếu nhu cầu chỉ là rename `products_v1` thành `catalog_product`, partial override thường ít rủi ro và ít lặp metadata hơn.

### 6.3. Các tình huống thích hợp

- Legacy entity class không muốn/không thể gắn JPA annotations.
- Một codebase có chủ trương mapping metadata hoàn toàn ở XML.
- Một bounded context cần mapping được quản lý bởi đội database integration.
- Một tập mappings được generate/kiểm soát bằng quy trình riêng có test rõ.

### 6.4. Vẫn phải có nhận diện entity và ID đúng

JPA cần biết Java type nào là entity, primary key là attribute nào, relationship ownership ra sao. Với complete mapping, file XML phải mô tả đầy đủ những yếu tố cần thiết.

---

## 7. xml-mapping-metadata-complete ở mức persistence unit

Ngoài entity-level metadata-complete, XML cho phép tuyên bố mapping metadata hoàn toàn ở XML cho phạm vi persistence unit theo quy tắc đặc tả.

Ví dụ cấu trúc ý tưởng:

```xml
<entity-mappings
    xmlns="https://jakarta.ee/xml/ns/persistence/orm"
    version="3.0">

    <persistence-unit-metadata>
        <xml-mapping-metadata-complete/>
    </persistence-unit-metadata>

    <entity class="com.example.catalog.domain.Product"
            access="FIELD">

        <table name="catalog_product"/>

        <attributes>
            <id name="id"/>
            <basic name="name">
                <column name="product_label"/>
            </basic>
        </attributes>
    </entity>
</entity-mappings>
```

### 7.1. Phạm vi rộng hơn entity-level complete

Đây là lựa chọn kiến trúc lớn: **mapping annotations có thể bị bỏ qua trong phạm vi persistence unit**. Một class không được khai báo đầy đủ trong XML có thể không được quản lý hoặc thiếu thông tin mapping cần thiết.

### 7.2. Không dùng để “giảm warning”

Một warning về column name hay access type không nên được xử lý bằng cách bật complete metadata toàn unit. Nó có thể thay đổi metadata của hàng chục entities khác.

### 7.3. Cần test startup và mọi entities

Nếu chọn global XML-complete strategy, cần đảm bảo:

- Tất cả entities cần thiết có XML metadata.
- ID/embedded IDs, associations, inheritance được mô tả.
- Version/converters/listeners không bị mất.
- Named queries, filters và vendor extensions được xử lý theo nguồn phù hợp.
- Không có class được kỳ vọng quản lý chỉ nhờ annotation nhưng thực tế bị bỏ.

### 7.4. Không xem complete mapping là một cách “đổi database runtime”

XML-complete là **cách hợp nhất metadata khi EntityManagerFactory được xây**, không phải công tắc runtime để cùng một EMF map một class sang schema khác tùy request.

---

## 8. Field access và property access trong XML

JPA có hai mô hình truy cập persistent state:

- **FIELD**: mapping tới Java fields.
- **PROPERTY**: mapping tới JavaBean properties (getter/setter theo contract).

### 8.1. Field access

Java:

```java
public class Product {

    private Long id;

    private String name;

    protected Product() {
    }
}
```

XML:

```xml
<entity class="com.example.catalog.domain.Product"
        access="FIELD"
        metadata-complete="true">

    <attributes>
        <id name="id"/>
        <basic name="name"/>
    </attributes>
</entity>
```

`name="name"` liên quan field `name`.

### 8.2. Property access

Java:

```java
public class Product {

    private Long id;
    private String name;

    protected Product() {
    }

    public Long getId() {
        return id;
    }

    protected void setId(Long id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    protected void setName(String name) {
        this.name = name;
    }
}
```

XML:

```xml
<entity class="com.example.catalog.domain.Product"
        access="PROPERTY"
        metadata-complete="true">

    <attributes>
        <id name="id"/>
        <basic name="name"/>
    </attributes>
</entity>
```

### 8.3. Tránh trộn access type không chủ đích

Nếu annotations đặt `@Id` trên field nhưng XML khai `access="PROPERTY"`, có thể phát sinh mapping bất ngờ nếu không hiểu precedence/metadata-complete. Nên chọn access convention rõ, test bằng metamodel và SQL.

### 8.4. Java attribute name không phải getter method name

Với property access, XML dùng `name="name"`, không dùng `name="getName"`.

### 8.5. @Transient và transient field

Khi dùng XML-complete mapping, nếu một Java field không phải persistent, cần bảo đảm phạm vi default field/property discovery và khai báo transient phù hợp. Không bỏ qua xác định persistent attributes chỉ vì field không có `@Column`.

---

## 9. Ghi đè table, schema và catalog

Các mapping elements có thể diễn đạt:

```xml
<entity class="com.example.catalog.domain.Product"
        access="FIELD">

    <table name="catalog_product"
           schema="catalog"
           catalog="shop_data"/>

    <attributes>
        <id name="id"/>
    </attributes>
</entity>
```

Tùy database, `schema` và `catalog` có thể có ý nghĩa khác nhau:

- PostgreSQL thường tổ chức tên bảng theo schema.
- MySQL sử dụng database name theo cách gần với catalog/schema tùy driver.
- SQL Server/Oracle có conventions riêng.

### 9.1. Không hard-code schema môi trường nếu không cần

Nếu cùng artifact chạy dev/staging/prod nhưng schema names khác nhau, hard-code `schema="dev_catalog"` trong XML có thể khiến deploy production truy cập sai nơi.

### 9.2. Cân nhắc persistence-unit defaults

Có thể đặt schema/catalog defaults cho một nhóm entities theo quy tắc XML metadata; tuy nhiên default chỉ nên dùng khi thực sự nhất quán, không làm thay đổi data source/tenant routing semantics.

### 9.3. Schema name không phải connection target

`<table schema="catalog">` không quyết định JDBC URL hay database server. Data source kết nối DB nào là cấu hình khác, không được giải quyết bằng cách chỉ đổi schema trong entity mapping.

### 9.4. Đổi tên mapping phải đi cùng migration

`catalog_product` phải tồn tại ở DB; `@Table`/XML chỉ điều khiển SQL được phát, không biến bảng legacy thành bảng mới một cách an toàn.

---

## 10. Ghi đè columns và thuộc tính cơ bản

Một entity có các fields:

```java
private String sku;
private String title;
private BigDecimal price;
private boolean active;
```

XML:

```xml
<entity class="com.example.catalog.domain.Product"
        access="FIELD"
        metadata-complete="true">

    <table name="catalog_product"/>

    <attributes>
        <id name="id">
            <column name="product_id"/>
        </id>

        <basic name="sku" optional="false">
            <column name="product_code"
                    nullable="false"
                    length="64"/>
        </basic>

        <basic name="title" optional="false">
            <column name="display_title"
                    nullable="false"
                    length="200"/>
        </basic>

        <basic name="price" optional="false">
            <column name="unit_price"
                    nullable="false"
                    precision="14"
                    scale="2"/>
        </basic>

        <basic name="active">
            <column name="is_active" nullable="false"/>
        </basic>
    </attributes>
</entity>
```

Các yếu tố:

- `<basic name="title">`: persistent Java attribute.
- `<column name="display_title">`: database column name.
- `nullable="false"`: mapping/schema metadata, không phải một Bean Validation `@NotNull` runtime validator.
- `length`: thường dùng cho chuỗi.
- `precision`/`scale`: thường dùng cho decimal.
- `optional`: JPA mapping metadata về nullability của basic attribute.

### 10.1. Tên Java và SQL khác nhau là bình thường

JPQL dùng:

```jpql
select p from Product p where p.title = :title
```

không phải:

```jpql
select p from Product p where p.display_title = :title
```

### 10.2. Đổi nullable không tự thêm DB constraint

Nếu sửa XML `nullable="false"` nhưng migration chưa có `NOT NULL`, behavior tùy schema/tooling. Production nên có migration và kiểm chứng database constraint thực.

### 10.3. XML column precision phải khớp domain numeric rules

Một `BigDecimal` có precision/scale mapping không tự kiểm tra mọi business currency rule hoặc rounding strategy. Có thể cần Bean Validation, domain methods và DB CHECK phù hợp.

### 10.4. Quên attribute trong XML-complete mapping

Khi dùng `metadata-complete="true"`, cần kiểm tra toàn bộ attributes dự kiến được persist. Nếu thiếu mapping hoặc access convention không đúng, có thể sinh columns không mong muốn hoặc bỏ metadata annotation cần thiết. Đừng suy luận từ source Java đơn thuần.

---

## 11. Ghi đè @Id và @GeneratedValue bằng XML

Java entity có:

```java
private Long id;
private String name;
```

XML complete:

```xml
<entity class="com.example.catalog.domain.Product"
        access="FIELD"
        metadata-complete="true">

    <table name="catalog_product"/>

    <attributes>
        <id name="id">
            <column name="product_id"/>

            <generated-value
                strategy="SEQUENCE"
                generator="catalog_product_seq"/>
        </id>

        <basic name="name"/>
    </attributes>
</entity>
```

Cần khai báo sequence generator được tham chiếu ở nơi phù hợp với XML mapping, ví dụ:

```xml
<sequence-generator
    name="catalog_product_seq"
    sequence-name="catalog_product_id_seq"
    allocation-size="50"/>
```

Vị trí của `<sequence-generator>` trong XML phải tuân theo XSD version: nó có thể được khai báo ở phạm vi entity hoặc thích hợp trong metadata mapping. Không đặt XML elements tùy ý ngoài thứ tự/parent mà schema cho phép.

### 11.1. SEQUENCE không phải lúc nào cũng khả dụng trên mọi database

Database có thể không hỗ trợ sequence theo cùng cách. JPA provider/dialect quyết định SQL và strategy tương ứng. Nếu target DB chỉ hỗ trợ IDENTITY phù hợp hơn, chọn mapping/generator đúng.

### 11.2. allocation-size phải khớp generator design

Sai allocation size hoặc database sequence increment có thể gây behavior ID generation bất thường theo provider. Khi đổi từ IDENTITY sang SEQUENCE, đây không chỉ là đổi XML; cần migration và kiểm thử.

### 11.3. Không dùng XML để tùy tiện đổi PK column trên DB đã có data

Đổi mapping `id` từ `product_id` sang `legacy_key` có thể khiến JPA query nhầm, fail FK joins hoặc đọc nhầm identity. Cần kiểm tra PK uniqueness, FK references và migration.

### 11.4. @IdClass và @EmbeddedId

Composite keys đòi metadata chính xác. Với XML-complete, cần khai báo `id-class` hoặc `embedded-id` theo model. Không được chỉ ghi `<id name="id"/>` nếu class thực sự dùng embedded/composite identity.

---

## 12. Ghi đè @Version và optimistic locking metadata

Java:

```java
private Long version;
```

XML:

```xml
<attributes>
    <id name="id"/>

    <version name="version">
        <column name="row_version"
                nullable="false"/>
    </version>
</attributes>
```

### 12.1. Vì sao version quan trọng?

`@Version`/`<version>` giúp JPA phát hiện stale entity updates theo optimistic locking semantics.

```text
A: load Product#42 version=7
B: load Product#42 version=7
A: update -> version=8, COMMIT
B: update dựa trên version=7 -> conflict
```

### 12.2. metadata-complete có thể làm mất version mapping

Nếu source Java có `@Version` nhưng XML complete không khai báo `<version>`, optimistic locking có thể không hoạt động theo thiết kế. Đây là một trong những rủi ro lớn khi chuyển annotation mappings sang XML.

### 12.3. Không tự gán version

Application code không nên gán `version` tùy ý để “khớp” với XML. Version được JPA provider quản lý cho entity-level writes.

### 12.4. Bulk JPQL/native SQL cần xử lý version riêng

Dù entity có version mapping từ XML, bulk JPQL/native UPDATE không tự thực hiện toàn bộ entity-level optimistic version handling. Cần manual version predicates/increments và đồng bộ persistence context/cache khi dùng DML trực tiếp.

---

## 13. Ghi đè @ManyToOne và join column

Giả sử:

```java
public class Order {

    private Long id;
    private Customer customer;
}
```

XML:

```xml
<entity class="com.example.order.domain.Order"
        access="FIELD"
        metadata-complete="true">

    <table name="sales_order"/>

    <attributes>
        <id name="id">
            <column name="order_id"/>
        </id>

        <many-to-one
            name="customer"
            target-entity="com.example.customer.domain.Customer"
            fetch="LAZY"
            optional="false">

            <join-column
                name="customer_id"
                referenced-column-name="customer_id"
                nullable="false"/>
        </many-to-one>
    </attributes>
</entity>
```

### 13.1. name là Java property

`name="customer"` tương ứng field/property `customer` trong class Order.

### 13.2. join-column là FK của owning side

`name="customer_id"` nói cột FK trong bảng owning entity Order. `referenced-column-name="customer_id"` phải phù hợp target column thực tế của Customer mapping.

### 13.3. LAZY là một fetch intention, không phải SQL guarantee tuyệt đối

Với to-one relationships, khả năng lazy proxy/enhancement và timing truy vấn có thể phụ thuộc provider. Đổi từ EAGER sang LAZY cần test behavior/API serialization, không chỉ sửa XML và giả định N+1 tự biến mất.

### 13.4. Không nhầm JPA cascade với foreign-key ON DELETE

XML cascade metadata điều khiển JPA persistence operations, không đồng nghĩa database FK cascade action. Nếu schema FK có `ON DELETE CASCADE` thì đó là database-level behavior riêng.

---

## 14. Ghi đè @OneToMany và mapped-by

Giả sử Order có các OrderLines; OrderLine là owning side vì chứa `order_id` FK.

Java:

```java
public class Order {

    private Long id;

    private List<OrderLine> lines = new ArrayList<>();
}

public class OrderLine {

    private Long id;
    private Order order;
}
```

XML cho Order:

```xml
<entity class="com.example.order.domain.Order"
        access="FIELD"
        metadata-complete="true">

    <table name="sales_order"/>

    <attributes>
        <id name="id"/>

        <one-to-many
            name="lines"
            target-entity="com.example.order.domain.OrderLine"
            mapped-by="order"
            fetch="LAZY">

            <cascade>
                <cascade-persist/>
                <cascade-merge/>
            </cascade>
        </one-to-many>
    </attributes>
</entity>
```

XML cho OrderLine:

```xml
<entity class="com.example.order.domain.OrderLine"
        access="FIELD"
        metadata-complete="true">

    <table name="order_line"/>

    <attributes>
        <id name="id"/>

        <many-to-one
            name="order"
            target-entity="com.example.order.domain.Order"
            optional="false">

            <join-column name="order_id" nullable="false"/>
        </many-to-one>
    </attributes>
</entity>
```

### 14.1. mapped-by tham chiếu Java member name

`mapped-by="order"` nghĩa là thuộc tính `OrderLine.order`, **không phải tên SQL FK column `order_id`**.

### 14.2. Owner quyết định FK

Nếu trong memory chỉ thêm OrderLine vào `order.getLines()` mà không set `line.order`, owning side có thể chưa được đồng bộ. XML không tự sửa việc hai phía object relationship không nhất quán.

### 14.3. Cascade phải được thiết kế theo aggregate boundary

`cascade-persist` hoặc `cascade-remove` có ảnh hưởng lớn. Đừng bật cascade ALL chỉ vì cần save một collection, đặc biệt đối với reference entities được nhiều aggregates dùng chung.

### 14.4. orphanRemoval và delete

Orphan removal giúp quản lý entity không còn được tham chiếu theo parent collection trong những mappings thích hợp. Nếu XML override một annotation đã có `orphanRemoval=true`, hãy kiểm tra effective metadata; thay đổi tùy tiện có thể làm child rows không được xóa hoặc bị xóa ngoài ý muốn.

---

## 15. Embedded value objects và attribute overrides

Một `@Embeddable` value object:

```java
public class Address {

    private String street;
    private String city;
    private String postalCode;
}
```

Customer chứa:

```java
private Address billingAddress;
private Address shippingAddress;
```

Để hai embedded copies không map vào cùng columns, dùng XML attribute overrides:

```xml
<entity class="com.example.customer.domain.Customer"
        access="FIELD"
        metadata-complete="true">

    <table name="customer"/>

    <attributes>
        <id name="id"/>

        <embedded name="billingAddress">
            <attribute-override name="street">
                <column name="billing_street"/>
            </attribute-override>

            <attribute-override name="city">
                <column name="billing_city"/>
            </attribute-override>

            <attribute-override name="postalCode">
                <column name="billing_postal_code"/>
            </attribute-override>
        </embedded>

        <embedded name="shippingAddress">
            <attribute-override name="street">
                <column name="shipping_street"/>
            </attribute-override>

            <attribute-override name="city">
                <column name="shipping_city"/>
            </attribute-override>

            <attribute-override name="postalCode">
                <column name="shipping_postal_code"/>
            </attribute-override>
        </embedded>
    </attributes>
</entity>
```

### 15.1. Embedded class cũng phải có mapping metadata

Trong XML-complete strategy, `Address` cần được xác định là embeddable bằng XML metadata thích hợp, không dựa vào `@Embeddable` nếu mapping annotations đã bị vô hiệu.

```xml
<embeddable class="com.example.customer.domain.Address"
            access="FIELD">

    <attributes>
        <basic name="street"/>
        <basic name="city"/>
        <basic name="postalCode"/>
    </attributes>
</embeddable>
```

### 15.2. Attribute override name là thuộc tính của embedded object

`street` là tên field/property Java trong Address. Column names là `billing_street`/`shipping_street`.

### 15.3. Không dùng attribute-override để đổi relationship ownership

`<attribute-override>` dành cho những basic/embedded attribute mappings phù hợp. Nếu nested member là association, cần cơ chế association override hoặc mapping riêng theo spec.

### 15.4. Schema vẫn phải có các columns

XML không tạo các columns `billing_street` tự động trên production database trừ khi schema generation tooling đã được cấu hình và cho phép thay đổi DB — điều không nên dùng như migration chính.

---

## 16. XML named queries

Named JPQL query có thể đặt trong annotations:

```java
@NamedQuery(
    name = "Product.findActive",
    query = "select p from Product p where p.active = true"
)
```

hoặc XML mapping:

```xml
<named-query name="Product.findActive">
    <query>
        select p
        from Product p
        where p.active = true
        order by p.id
    </query>
</named-query>
```

### 16.1. JPQL vẫn dùng entity names và attribute names

Dù mapped table `catalog_product` và column `is_active`, JPQL dùng `Product` và `active` theo JPA model.

### 16.2. Named query được nạp cùng metadata

Nhiều providers phân tích/kiểm tra named queries lúc tạo EntityManagerFactory. Một JPQL sai có thể khiến startup thất bại, hữu ích cho fail fast; exact validation timing phụ thuộc provider.

### 16.3. Không dùng XML named query để “đổi SQL table name”

Chuyển `select p from Product p` sang SQL `select * from catalog_product` không phải một named JPQL query hợp lệ theo cùng semantics. Native named queries cần mapping/result handling riêng.

### 16.4. Query name collision

Nếu cả annotations và XML khai cùng named query name, cần hiểu XML override rules và không tạo duplicate inconsistent declarations trong nhiều files. Tốt nhất mỗi named query có một nguồn authoritative.

---

## 17. Entity listeners và lifecycle callbacks từ XML

JPA entity lifecycle events gồm `PrePersist`, `PreUpdate`, `PostLoad`, v.v. XML có thể cấu hình listeners thay vì chỉ dùng annotations.

Java listener:

```java
package com.example.catalog.persistence;

import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import java.time.Instant;

public class ProductAuditListener {

    @PrePersist
    public void beforeInsert(Object entity) {
        // Ví dụ minh họa:
        // Trong dự án thật nên type-check rõ và dùng
        // một audited interface hoặc listener riêng.
    }

    @PreUpdate
    public void beforeUpdate(Object entity) {
        // Không nên gọi HTTP/database external ở đây.
    }
}
```

XML có thể tham chiếu listener class ở phạm vi thích hợp:

```xml
<entity-listeners>
    <entity-listener
        class="com.example.catalog.persistence.ProductAuditListener"/>
</entity-listeners>
```

### 17.1. Listener từ XML và annotation có thể tương tác

Khi XML override/complete metadata, callbacks/listeners được áp theo rules của persistence spec. Đừng assume annotation `@EntityListeners` và XML đều chạy đúng thứ tự mong muốn nếu cấu hình chưa được thử.

### 17.2. Listener không phải service transaction orchestration

Không gọi external API hoặc chạy business workflow phức tạp trong pre-persist/pre-update. Callback diễn ra trong persistence lifecycle; có thể được gọi gần flush và chịu transaction failure/rollback.

### 17.3. Tách audit khỏi schema generation

Listener gán timestamp hay createdBy không tự tạo columns `created_at`/`created_by`. Mapping và DB migration phải đồng bộ.

### 17.4. Không dùng listener để tự sửa mapping metadata runtime

EntityManagerFactory đã được xây với mapping model xác định. Callback trên entity instance không phải cơ chế thay tên column/table động.

---

## 18. AttributeConverter và XML

JPA hỗ trợ `AttributeConverter<X,Y>` để chuyển Java value sang JDBC/DB representation.

Ví dụ:

```java
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter(autoApply = false)
public class OrderStatusConverter
        implements AttributeConverter<OrderStatus, String> {

    @Override
    public String convertToDatabaseColumn(OrderStatus value) {
        return value == null ? null : value.name();
    }

    @Override
    public OrderStatus convertToEntityAttribute(String value) {
        return value == null
            ? null
            : OrderStatus.valueOf(value);
    }
}
```

XML có thể đăng ký converter và áp dụng cho persistent attribute theo mapping metadata tương ứng.

### 18.1. Chọn converter khi cần gì?

- Kiểu value object được biểu diễn trong một column.
- Legacy code mapping cũ sang enum/domain type.
- Mã hóa một format được thiết kế rõ.

### 18.2. Không nhầm converter với serialization chung

Converter có phạm vi types/attributes nhất định và những giới hạn với IDs, versions, relationships hoặc mapping đặc biệt theo spec/provider. Đừng áp một converter toàn cục khi type quá phổ biến mà không kiểm tra.

### 18.3. Nếu annotations và XML cùng khai converter

Phải xác định effective mapping rõ. Nếu XML complete bỏ annotation `@Convert`, behavior có thể đổi. Provider metadata tests/SQL values cần kiểm tra.

### 18.4. Data migration vẫn cần

Đổi converter từ lưu `ACTIVE` thành `A` không làm những rows `ACTIVE` trong DB tự chuyển thành `A`. Cần migration/backward-compatibility strategy.

---

## 19. Defaults trong persistence-unit-metadata

XML có thể khai một số defaults chung cho persistence unit, ví dụ:

```xml
<entity-mappings
    xmlns="https://jakarta.ee/xml/ns/persistence/orm"
    version="3.0">

    <persistence-unit-metadata>
        <persistence-unit-defaults>
            <schema>catalog</schema>
            <access>FIELD</access>
        </persistence-unit-defaults>
    </persistence-unit-metadata>

    <!-- entities ... -->
</entity-mappings>
```

### 19.1. Defaults giảm lặp

Nếu nhiều entities ở cùng schema và cùng access convention, defaults giúp XML gọn và nhất quán.

### 19.2. Defaults không phải một replace-all policy

Entity/attribute metadata explicit có thể ghi đè defaults theo rules. Nên thiết kế để người đọc biết giá trị nào là default, giá trị nào là override đặc biệt.

### 19.3. Schema defaults vẫn ảnh hưởng portability

Một persistence unit chạy nhiều database vendors có thể có schema naming khác nhau. Không đưa một default cứng sang production khi database conventions không khớp.

### 19.4. Không đặt defaults tùy ý trong nhiều XML files

Các file cùng persistence unit có thể đưa ra defaults hoặc declarations ảnh hưởng phạm vi rộng. Tránh nhiều tác giả định nghĩa defaults xung đột; không dựa vào thứ tự đọc file ngầm để chọn giá trị thắng.

---

## 20. XML schema version và namespace

Một `orm.xml` theo Jakarta Persistence 3.0 sử dụng:

```xml
<entity-mappings
    xmlns="https://jakarta.ee/xml/ns/persistence/orm"
    version="3.0">
    <!-- mapping elements -->
</entity-mappings>
```

Trong hệ sinh thái trước Jakarta, JPA XML có thể dùng namespaces kiểu:

```text
http://xmlns.jcp.org/xml/ns/persistence/orm
http://java.sun.com/xml/ns/persistence/orm
```

tùy JPA version lịch sử.

### 20.1. Namespace và API phải đồng bộ

Nếu code dùng `jakarta.persistence.*` nhưng XML copy từ một dự án `javax.persistence.*` quá cũ, provider có thể không parse hoặc semantics khác mong đợi.

### 20.2. Version phải khớp provider được triển khai

Không đổi `version="3.0"` thành 3.1/3.2 chỉ vì thư viện mới hơn mà không xác nhận provider hỗ trợ XML schema tương ứng. Cũng không dùng XML element mới hơn trong một XSD cũ và mong parser bỏ qua an toàn.

### 20.3. Có nên khai xsi:schemaLocation?

Có thể khai schemaLocation tham chiếu XSD đúng version để IDE/build validation nhận biết cấu trúc. Ví dụ cấu hình khung:

```xml
<entity-mappings
    xmlns="https://jakarta.ee/xml/ns/persistence/orm"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    version="3.0">
    <!-- Có thể thêm xsi:schemaLocation chính xác
         theo tài liệu/XSD của JPA version được dùng. -->
</entity-mappings>
```

Nếu dùng schemaLocation, phải dùng namespace và đường dẫn XSD **đúng theo bản đặc tả đang triển khai**; không tự sáng tạo đường dẫn. Một build pipeline có thể kiểm tra XML bằng XSD đã pin/versioned để tránh phụ thuộc network runtime.

### 20.4. XML well-formed chưa chắc mapping hợp lệ

Một XML parser có thể chấp nhận file có tags đúng cú pháp nhưng:

- Class không tồn tại.
- Attribute `name` không tồn tại.
- ID mapping thiếu.
- Join column sai.
- Duplicate entity/named query metadata.
- Unsupported extension element.

Startup metadata validation của JPA provider mới phát hiện những lỗi ở tầng mapping; một số sai lầm chỉ lộ khi SQL chạy.

---

## 21. Quy tắc quản lý nguồn cấu hình: phân loại trước khi chọn file

Một hệ thống thường có nhiều nguồn:

```text
Java annotations
orm.xml files
persistence.xml
Framework configuration
Provider properties
Environment variables / Secrets Manager
Database schema migrations
Database runtime settings
```

Cách tránh xung đột là **phân quyền theo loại thông tin**.

| Loại thông tin | Nguồn có thẩm quyền đề xuất |
|---|---|
| Java entity attributes và domain model | Java source |
| Mapping table/column/association | Annotations mặc định, XML override có chủ đích |
| Persistence unit identity và mapping resource list | persistence.xml hoặc framework EMF configuration rõ |
| JDBC URL/username/password | Environment/secret store, không hard-code vào mapping XML |
| Pool size/timeout | Framework/data source configuration của môi trường |
| Hibernate-specific behavior | Provider configuration với version được pin |
| Tạo/đổi tables, columns, indexes | Flyway/Liquibase/migration scripts |
| Business constraints | Domain logic + DB constraints |
| Transaction boundaries | JTA/Spring/application service |
| Cache and fetch policy | JPA/provider config + use-case-driven tuning |
| Schema validation startup | Provider-supported validation/checks, không phải migration |
| Production rollout/rollback | Deployment/migration plan |

**Đề xuất trên là một convention quản trị**, không phải luật bắt buộc của JPA. Nhưng nó giúp giảm việc một thay đổi có thể bị khai ở ba nơi khác nhau mà không ai biết nguồn thắng.

### 21.1. “Một nguồn sự thật” không có nghĩa mọi thứ chỉ nằm trong một file

Nhiều lớp có trách nhiệm khác nhau: mapping XML và DB schema đều mô tả column nhưng phục vụ mục đích khác. Điều cần tránh là **hai nguồn cùng chịu trách nhiệm quyết định một thuộc tính mà không có quy tắc rõ**.

### 21.2. Dùng XML override như một ngoại lệ có lý do

Nếu 95% mappings được quản lý bằng annotations, có thể giữ XML chỉ cho các legacy overrides thay vì chuyển toàn bộ entity metadata sang XML.

### 21.3. Đừng để cùng một cột được khai khác tên trong ba lớp

Ví dụ:

```text
Java annotation: product_name
orm.xml:        display_label
DB migration:   title
```

Nếu không có test, JPA generated SQL sẽ trỏ sai cột. Mỗi thay đổi cần update mapping source authoritative và schema migration đồng bộ.

---

## 22. Quy tắc ưu tiên: không có một bảng “mọi thứ” áp dụng cho tất cả

Một lỗi thường gặp là nói:

> “Environment variables thắng XML, XML thắng annotations, còn YAML thắng persistence.xml.”

Câu này quá chung và dễ sai vì **mỗi lớp metadata/property có quy tắc ưu tiên riêng**.

### 22.1. Mapping metadata

Trong trường hợp annotation + JPA XML mapping, XML declarations có precedence theo JPA mapping rules khi cùng mô tả một metadata element, trừ những giới hạn và metadata-complete semantics. Đây là **mapping resolution**.

### 22.2. Persistence properties

Properties trong `persistence.xml` có thể được bổ sung hoặc override bằng properties truyền khi tạo EntityManagerFactory theo bootstrap API, tùy property và môi trường triển khai. Đây là **runtime bootstrap settings**, không phải XML mapping metadata override.

### 22.3. Framework configuration

Spring Boot có các nguồn `application.yml`/`application.properties`, environment variables, command-line arguments, config server, secrets và property source precedence của Spring. **Đó là quy tắc framework**, không tự thay JPA metadata precedence.

### 22.4. Provider-specific settings

`hibernate.*`, EclipseLink-specific settings và framework-level properties có semantics và overrides riêng, không được coi thuộc cùng một hierarchy với `@Column` vs `<column>`.

### 22.5. Migration schema

Ngay cả khi XML mapping được ưu tiên so với annotation, nó không ưu tiên hơn **database reality**. DB table/column có thể tồn tại hoặc không; schema migration là bước thay đổi database thật.

---

## 23. Runtime property overrides khi tạo EntityManagerFactory

Với Java SE `Persistence` bootstrap:

```java
Map<String, Object> overrides = new HashMap<>();

overrides.put(
    "jakarta.persistence.jdbc.url",
    jdbcUrlFromEnvironment
);
overrides.put(
    "jakarta.persistence.jdbc.user",
    jdbcUserFromSecrets
);
overrides.put(
    "jakarta.persistence.jdbc.password",
    jdbcPasswordFromSecrets
);

EntityManagerFactory emf =
    Persistence.createEntityManagerFactory(
        "catalogPU",
        overrides
    );
```

Các properties được truyền lúc bootstrap có thể được dùng để override/cung cấp cấu hình cho persistence unit theo JPA bootstrap contract.

### 23.1. Không nhúng secrets vào source control

Không lưu:

```xml
<property
    name="jakarta.persistence.jdbc.password"
    value="production-password"/>
```

trong repository. Dùng environment/secret manager theo infrastructure, có quản lý quyền và rotation.

### 23.2. Runtime properties không phải SQL mapping override cho từng entity

Truyền một key tùy ý như `"product.table"="catalog_prod"` vào `createEntityManagerFactory` không khiến JPA chuẩn tự đổi `@Table`/XML mapping. Chỉ những properties provider/framework nhận biết mới có hiệu lực.

### 23.3. Datasource injection và RESOURCE_LOCAL khác JTA

Trong môi trường JTA/container, data source và transaction coordination có cấu hình riêng. Không sao chép một ví dụ RESOURCE_LOCAL JDBC credentials rồi kỳ vọng có JTA enlistment.

### 23.4. Bootstrap-time, không phải per-request

Mapping/EMF configuration thường được resolve **khi khởi tạo EntityManagerFactory**. Không sửa environment variable giữa request rồi kỳ vọng các EntityManager hiện tại đổi table mapping.

---

## 24. XML và môi trường dev, test, staging, production

Một codebase có thể chạy nhiều môi trường nhưng không nên có nhiều bản mapping XML khác nhau nếu schema contract phải thống nhất.

### 24.1. Những thứ thường khác nhau theo môi trường

- Database URL/hostname.
- Username/password/secret.
- Connection pool size.
- Timeout/retry policy.
- Logging verbosity.
- Schema name hoặc tenant routing khi kiến trúc yêu cầu.
- Cache backend/region sizes.
- Feature flags cho application behavior.

### 24.2. Những thứ thường nên giống nhau

- Entity/table/column mapping contract (trừ khi hỗ trợ multi-schema legacy rõ ràng).
- Constraint semantics.
- Named queries.
- Primary key mapping.
- Relationship ownership.
- Versioning.
- Migration history tương thích.

### 24.3. Tránh tạo dev-orm.xml/prod-orm.xml không được kiểm soát

Nếu dev dùng column `product_name` còn prod dùng `legacy_name`, code có thể pass ở local nhưng fail ở production. Nếu thật sự có hai schema variants, hãy:

1. Định nghĩa hỗ trợ rõ ràng trong kiến trúc.
2. Có hai sets migration/integration tests.
3. Không dùng “đổi file ngầm” như hack deployment.
4. Kiểm tra resource artifact đóng gói đúng profile.
5. Có kế hoạch hội tụ schema nếu có thể.

### 24.4. Không dùng Hibernate auto-update schema làm migration chính ở production

Một setting như `hibernate.hbm2ddl.auto=update` có thể tạo thay đổi schema không được review đầy đủ. Ưu tiên migration có version, code review, rollback/forward plan. Schema validation khi startup có thể giúp phát hiện drift, nhưng không thay migration.

---

## 25. Spring Boot và nguồn cấu hình JPA

Trong Spring Boot, nhiều ứng dụng để framework tự cấu hình EntityManagerFactory từ `DataSource` và `spring.jpa.*` settings mà **không trực tiếp dùng persistence.xml theo cách Java SE**.

Ví dụ cấu hình:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://db-host:5432/catalog
    username: app_user
    # Password đọc từ secret environment, không commit giá trị thật.
  jpa:
    properties:
      hibernate:
        format_sql: true
```

### 25.1. Không nhầm framework configuration với JPA XML mapping

`application.yml` thường chứa runtime/environment settings. Nó không phải thay thế một cách portable cho file `orm.xml` với `<entity>`/`<attributes>` metadata.

### 25.2. Khi cần nạp XML mapping trong Boot

Có thể dùng cơ chế mapping resources/framework-supported EntityManagerFactory configuration hoặc cấu hình persistence unit tường minh. Cách chính xác phụ thuộc Spring Boot/Spring ORM version và cách EMF được xây.

Không nên thêm `META-INF/orm.xml` vào resource folder rồi **chỉ suy đoán** nó được nạp đúng trong mọi auto-configuration. Hãy kiểm tra startup logs, effective metamodel và SQL.

### 25.3. Không cấu hình hai EntityManagerFactories vô tình

Nếu bạn tự tạo `LocalContainerEntityManagerFactoryBean` nhưng Boot vẫn auto-config thêm một EMF, có thể dẫn đến repository binding sai hoặc mapping file áp ở factory không được sử dụng. Đặt tên beans, persistence units và transaction managers rõ.

### 25.4. @Transactional không quyết định metadata override

`@Transactional` điều phối transaction. Nó không ghi đè `@Table`, `orm.xml` hoặc database schema.

---

## 26. ORM XML trong một ứng dụng nhiều module

Giả sử repository:

```text
catalog-service/
├── catalog-domain/
│   └── src/main/java/.../Product.java
├── catalog-persistence/
│   ├── src/main/resources/META-INF/
│   │   └── catalog-mapping.xml
│   └── ...
└── catalog-app/
    ├── src/main/resources/META-INF/
    │   └── persistence.xml
    └── ...
```

### 26.1. Module chứa entity có thể khác module chứa mapping XML

Miễn là classes/resources được đóng gói vào persistence unit/classpath đúng và được chỉ định, XML có thể nằm ngoài entity source module. Nhưng build phải đưa chúng vào artifact deploy.

### 26.2. Mục tiêu tách module

- Domain library ít phụ thuộc mapping specifics.
- Persistence adapter sở hữu mapping.
- Application bootstrap sở hữu datasource/transaction setup.

### 26.3. Đổi package Java phải cập nhật XML

Nếu class di chuyển từ:

```text
com.example.catalog.domain.Product
```

sang:

```text
com.example.core.catalog.Product
```

thì `class="..."` trong XML phải đổi tương ứng, trừ khi dùng package defaults và tên ngắn phù hợp theo spec. Compiler thường không refactor string XML tự động nếu IDE không hỗ trợ.

### 26.4. Không package hai bản cùng resource path ngoài ý muốn

Nếu hai dependency JARs cùng cung cấp `META-INF/orm.xml`, resource discovery/classloader behavior có thể khó đoán hoặc provider xử lý nhiều files. Dùng tên resource có namespace rõ và khai báo mapping-file khi hệ thống lớn.

### 26.5. Classloader startup là thời điểm phát hiện sớm

Một mapping file bị thiếu hoặc class mapping không tồn tại thường dẫn tới EntityManagerFactory bootstrapping failure. Đây là lỗi tốt để phát hiện tại integration test/startup, không nên để tới lúc xử lý đơn hàng.

---

## 27. XML vs annotations: tiêu chí chọn nguồn mapping

| Tiêu chí | Annotations | XML mapping |
|---|---|---|
| Dễ đọc khi mở entity class | Rất trực tiếp | Phải mở thêm XML |
| Dễ refactor tên field/class | IDE thường hỗ trợ tốt | XML strings có thể dễ bị bỏ sót |
| Phù hợp domain/persistence code cùng module | Tốt | Có thêm cấu hình |
| Mapping class không muốn gắn annotations | Khó hơn | Phù hợp |
| Override một số legacy table/column | Có thể sửa source trực tiếp | Phù hợp khi muốn tách mapping |
| Quản lý metadata tập trung | Metadata phân tán theo classes | Có thể nhóm theo XML files |
| Risk của duplicate metadata | Ít hơn nếu chỉ annotation | Cao nếu dùng cả hai không có policy |
| Support từ JPA portable spec | Có | Có |
| Nhạy với XSD/packaging | Ít hơn | Có, cần đúng namespace/resource |
| Khả năng generate từ tooling | Có thể | Có thể |
| Thay đổi không biên dịch Java class | Có thể yêu cầu rebuild | XML có thể thay resource nhưng vẫn cần redeploy/rebootstrap |
| Production schema migration | Không thay migration | Không thay migration |

### 27.1. Khi annotations thường phù hợp hơn

- Hầu hết các dự án mới.
- Entity ownership rõ ở Java team.
- Mapping không cần thay giữa môi trường.
- Muốn refactor bằng compiler/IDE.

### 27.2. Khi XML có lợi thế

- Legacy schema với mapping phức tạp.
- Class models được chia sẻ và không nên nhiễm persistence annotations.
- Cần kiểm soát metadata từ persistence module độc lập.
- Migration từ một JPA mapping source sang source khác có giai đoạn song song được kiểm thử.

### 27.3. Khi dùng cả hai

Hãy đặt convention:

> Annotations là mapping mặc định. XML chỉ ghi đè danh sách metadata đã được phê duyệt và được ghi rõ lý do. Không bật metadata-complete trừ trường hợp full XML mapping.

### 27.4. Không đánh giá theo số dòng XML/annotation

Ít dòng hơn không luôn tốt hơn. Mapping đúng, dễ hiểu, không drift và được kiểm chứng quan trọng hơn.

---

## 28. Quản lý thay đổi mapping và schema migration cùng nhau

Một yêu cầu: đổi tên cột Product.name từ `product_name` thành `display_name`.

### 28.1. Nếu chỉ sửa XML

JPA có thể sinh SQL:

```sql
SELECT product_id, display_name
FROM catalog_product
WHERE product_id = ?;
```

nhưng DB vẫn có `product_name`, dẫn đến lỗi “column not found”.

### 28.2. Nếu chỉ sửa database

DB đổi thành `display_name`, nhưng JPA vẫn tìm `product_name` theo annotation/XML cũ, cũng lỗi.

### 28.3. Quy trình thay đổi có version

1. Viết migration DB.
2. Sửa mapping authoritative (annotation hoặc XML).
3. Cập nhật các native queries nếu dùng column cũ.
4. Cập nhật views/triggers/ETL/reporting liên quan.
5. Viết integration test với schema sau migration.
6. Review backward compatibility nếu deploy rolling.
7. Chạy migration/deploy theo thứ tự an toàn.
8. Có phương án rollback/forward-fix.

### 28.4. Expand-and-contract khi rolling deployments

Nếu app version cũ và mới cùng chạy, một column rename trực tiếp có thể phá version cũ. Một chiến lược:

```text
Phase 1: Expand
  Thêm display_name, giữ product_name.
  Backfill/synchronize theo kế hoạch.

Phase 2: Deploy new app
  App mới đọc/ghi format mới;
  compatibility window được kiểm soát.

Phase 3: Contract
  Khi tất cả instances cũ đã hết,
  xóa column cũ và cleanup mapping.
```

Không có một công thức áp dụng nguyên xi mọi schema; thực hiện theo phụ thuộc FK, triggers, locks và khả năng rollback thực tế.

---

## 29. Không dùng mapping XML làm công cụ chọn database theo request

Một ý tưởng sai:

```text
Tenant A -> Product maps to schema_a.product
Tenant B -> Product maps to schema_b.product
```

rồi đổi file XML tùy HTTP request.

Thông thường, EntityManagerFactory được boot với **một effective mapping model**. XML mapping không phải nơi thay table/schema names động theo mỗi request.

### 29.1. Hướng phù hợp với multi-tenancy

- Database-per-tenant.
- Schema-per-tenant.
- Discriminator/tenant-column model.
- Provider multi-tenancy support hoặc datasource routing.
- Mapping abstraction rõ theo JPA provider và transaction boundaries.

### 29.2. Khi dùng schema-per-tenant

Một provider có thể hỗ trợ chuyển schema/connection theo tenant context, nhưng cách đó không đồng nghĩa thay `orm.xml` runtime. Kiểm tra provider/version, cache keying và connection pool state.

### 29.3. Không coi tenant column mapping là authorization

Dù XML map `tenant_id` đúng, ứng dụng vẫn phải filter/match authorized tenant và bảo vệ cross-tenant writes.

### 29.4. Cache và metamodel

Một EMF có metadata/caches liên quan tới mapping nó quản lý. Không chia sẻ cache entries hoặc EntityManager bừa bãi giữa tenants khi identity/domain keys không được namespace đúng.

---

## 30. Schema generation: chức năng riêng, không phải migration

JPA có cấu hình schema generation. Ví dụ:

```xml
<property
    name="jakarta.persistence.schema-generation.database.action"
    value="none"/>
```

### 30.1. none trong production

Đặt `none` là một cách nói rõ: khởi tạo persistence unit không có ý định tự create/drop schema bằng tính năng chuẩn đó.

### 30.2. create/drop-and-create

Có thể hữu ích trong môi trường test database disposable, nhưng rất nguy hiểm nếu chạy nhầm trên dữ liệu quan trọng. Không bật từ một profile mơ hồ có thể được dùng ở production.

### 30.3. validate thường là provider-specific

Một option như:

```text
hibernate.hbm2ddl.auto=validate
```

là cấu hình Hibernate ORM, không phải một giá trị chuẩn của `jakarta.persistence.schema-generation.database.action`. Nếu dùng, phải kiểm tra version/dialect và giới hạn của schema validation implementation.

### 30.4. Mapping valid chưa chắc schema tương thích

Provider có thể start thành công nhưng chỉ khi query thực thi mới lộ sai column type, precision, missing FK/index hoặc naming strategy. Cần integration tests thực thi SQL, không chỉ parse XML.

---

## 31. Metamodel: cách xem entity mapping đã được nhận diện chưa

JPA cung cấp metadata API:

```java
Metamodel metamodel = em.getMetamodel();

EntityType<Product> type =
    metamodel.entity(Product.class);

System.out.println(type.getName());

for (Attribute<? super Product, ?> attribute
        : type.getAttributes()) {
    System.out.println(
        attribute.getName()
        + " : "
        + attribute.getJavaType().getSimpleName()
    );
}
```

### 31.1. Metamodel có ích để xác minh những gì?

- Product có được quản lý là entity không?
- Các Java attributes expected có xuất hiện không?
- ID/version attributes được JPA nhận diện không?
- Quan hệ singular/plural có mapping category nào?
- Entity name dùng trong JPQL là gì?

### 31.2. Hạn chế: standard metamodel không nhất thiết lộ SQL table/column

`EntityType<Product>` theo JPA chuẩn tập trung vào entity model/attributes. Nó không có API portable đơn giản tương đương `getTableName()`/`getColumnName()` cho mọi provider.

Để xác minh physical SQL mappings, dùng:

- Provider-specific metadata API nếu thật sự cần.
- SQL logging có bind parameters theo policy bảo mật.
- Integration test query/INSERT/UPDATE.
- JDBC `DatabaseMetaData` và schema introspection.
- Schema validation/migration assertions.

### 31.3. Không dùng generated static metamodel như bằng chứng table name

`Product_` với `name` giúp Criteria API type safety cho Java attributes. Nó không tự chứng minh XML mapped column là `display_name`.

---

## 32. Test đơn giản: mapping table/column override có thực sự hoạt động?

Một integration test nên chạy với database target hoặc container database cùng dialect.

Fixture:

```sql
CREATE TABLE catalog_product (
    product_id BIGINT PRIMARY KEY,
    display_name VARCHAR(200) NOT NULL
);
```

XML:

```xml
<entity class="com.example.catalog.domain.Product"
        access="FIELD"
        metadata-complete="true">
    <table name="catalog_product"/>
    <attributes>
        <id name="id">
            <column name="product_id"/>
        </id>
        <basic name="name">
            <column name="display_name"/>
        </basic>
    </attributes>
</entity>
```

Test:

```java
EntityManager em = emf.createEntityManager();

try {
    EntityTransaction tx = em.getTransaction();
    tx.begin();

    Product product =
        new Product(42L, "JPA XML Mapping");

    em.persist(product);
    tx.commit();

    em.clear();

    Product loaded =
        em.find(Product.class, 42L);

    assertEquals(
        "JPA XML Mapping",
        loaded.getName()
    );
} finally {
    em.close();
}
```

### 32.1. Vì sao clear trước find?

Tránh `find` chỉ trả lại managed instance vừa persist trong L1, làm test “pass” mà không thực sự thử đọc từ DB.

### 32.2. Kiểm tra SQL/generated schema

Đảm bảo SQL thực sự tác động `catalog_product.display_name`, không phải `product.product_name`. Điều này cần quan sát SQL/DB thực, vì standard metamodel không expose physical columns đầy đủ.

### 32.3. Không dựa vào H2 duy nhất cho mọi quyết định

H2 hoặc DB in-memory có thể khác PostgreSQL/Oracle/SQL Server về schema identifiers, sequences, DDL và quoting. Với use case quan trọng, test trên provider/dialect/database mục tiêu.

### 32.4. Đọc lại qua context mới

Nếu test muốn chứng minh dữ liệu đã commit, đọc bằng EntityManager mới hoặc context đã clear sau commit. Nếu có L2 enabled và muốn chắc read physical DB, cần cache policy phù hợp.

---

## 33. Test metadata-complete không bỏ sót @Version

Giả sử Product có Java `@Version` nhưng XML dùng `metadata-complete="true"`.

Test cần khẳng định effective entity metadata vẫn có version:

```java
EntityType<Product> type =
    em.getMetamodel().entity(Product.class);

SingularAttribute<? super Product, ?> version =
    type.getVersion(Long.class);

assertEquals("version", version.getName());
```

Nếu JPA provider không có version metadata như mong đợi, XML complete mapping đã thiếu hoặc cấu hình sai.

### 33.1. Test optimistic conflict

Hai EntityManagers load Product cùng version, một bên update+commit trước, bên kia update và kỳ vọng optimistic conflict theo JPA semantics. Đây là integration test concurrency, khác với chỉ hỏi metamodel.

### 33.2. Khi ID mapping bị lỗi

EntityManagerFactory có thể fail vì thiếu ID. Đừng “đoán thêm @Id trên Java class” khi XML complete đang bỏ qua annotations; bổ sung đúng XML mapping.

### 33.3. Không dùng compile-success làm mapping-success

Java compiler không parse mọi XML JPA metadata. Một project compile tốt vẫn có thể fail khi EMF bootstrap hoặc SQL query thực thi.

---

## 34. Test relationship mapping và FK

Nếu XML ghi:

```xml
<many-to-one name="customer">
    <join-column name="customer_id"/>
</many-to-one>
```

hãy test cả hai chiều:

1. Persist Customer.
2. Persist Order với `order.customer=customer`.
3. Flush/commit.
4. Kiểm tra `sales_order.customer_id` đúng.
5. Load Order trong context mới và đọc `order.getCustomer()`.
6. Nếu có `mapped-by` collection, kiểm tra relationship được đồng bộ.

### 34.1. FK và join-column phải khớp

Một XML mapping có thể parse được nhưng SQL join sai column names dẫn đến query fail hoặc kết quả bất ngờ.

### 34.2. Relationship ownership không đổi do Java collection

Nếu XML đặt mapped-by sai, chỉ thêm child vào parent collection có thể không ghi FK đúng. Cần domain helper methods giữ cả hai phía đồng bộ.

### 34.3. Lưu ý lazy loading

Test khi access association trong transaction và sau khi EntityManager đóng để hiểu fetch plan và tránh LazyInitializationException provider-specific ở API serialization.

### 34.4. Tránh dùng dữ liệu quá đơn giản

Nếu chỉ có một Customer và một Order, một join sai có thể vẫn trông đúng tình cờ. Test nhiều customers/orders có IDs khác nhau và FK thực.

---

## 35. Xác minh resource đóng gói thay vì chỉ nhìn source tree

Một lỗi thực tế:

```text
src/main/resources/META-INF/catalog-mapping.xml
  -> tồn tại

jar deployed:
  -> thiếu META-INF/catalog-mapping.xml
```

Nguyên nhân có thể là build resource filters, excludes, multi-module packaging hoặc shadow/fat jar config.

### 35.1. Các câu hỏi khi lỗi không load XML

- File có nằm trong artifact chạy thật không?
- Đường dẫn `mapping-file` có khớp resource path không?
- Persistence unit name có đúng không?
- EMF đang được tạo từ persistence.xml hay Spring auto config khác?
- Có nhiều EMF và service đang dùng sai unit không?
- XML namespace/version có tương thích provider không?
- JPA provider logs có báo mapping file not found/ignored không?

### 35.2. Không thử sửa đường dẫn bằng file system absolute path trong code

Hard-code `C:\...\src\main\resources\...` có thể chạy ở máy developer nhưng fail trong container/JAR. Dùng classpath/resource conventions.

### 35.3. Fail fast ở startup

Một mapping file bắt buộc nên được kiểm tra khi EMF bootstrap, có integration startup test và log tương ứng. Đừng để production chỉ phát hiện sai khi người dùng mở một endpoint ít dùng.

---

## 36. Trùng XML definitions và vấn đề thứ tự

Dự án có:

```text
catalog-mapping.xml
product-legacy-overrides.xml
product-test-overrides.xml
```

Cả ba cùng khai `Product` và `table` khác nhau.

### 36.1. Đừng coi mapping-file order là override chain tự do

Không thiết kế:

```text
file A khai Product
file B khai Product và “chắc chắn thắng”
file C khai Product và “chắc chắn thắng hơn”
```

như một quy tắc portable chung. JPA XML mapping có các semantics merge/override/duplicate riêng; khai báo xung đột có thể làm provider fail hoặc hành vi không như mong muốn.

### 36.2. Chiến lược tốt hơn

- Mỗi entity có một primary mapping XML file.
- Chỉ một nơi authoritative cho table/column/ID mappings.
- Cấu hình test có persistence unit riêng nếu cần.
- Không dùng production mapping file chồng lên nhau qua nhiều lớp ngầm.
- Một change review cần chỉ rõ XML mappings nào bị ảnh hưởng.

### 36.3. Nếu cần nhiều variants

Dùng explicit packaging/profiles được test riêng, hoặc provider multi-tenancy/custom mapping strategy phù hợp, không giả định XML override chain qua các files có thứ tự bất biến.

### 36.4. Kiểm tra toàn bộ sources trong PR

Khi ai đó sửa `@Column` nhưng XML đang override, thay đổi annotation có thể **không có hiệu lực**. Code review phải đọc effective configuration, không chỉ diff Java.

---

## 37. Mapping metadata vs application properties vs database schema

Ví dụ một thay đổi:

```text
JPA entity:
  Product.price

XML:
  <column name="unit_price" precision="14" scale="2"/>

Application config:
  JDBC URL = jdbc:postgresql://.../catalog

DB migration:
  ALTER TABLE catalog_product
  ADD COLUMN unit_price NUMERIC(14,2)
```

### 37.1. Java entity: ngữ nghĩa application state

`price` là BigDecimal, domain rules có thể yêu cầu không âm.

### 37.2. XML: cách lưu state

`unit_price` là tên SQL column và precision/scale mapping.

### 37.3. Application config: nơi kết nối và vận hành

JDBC URL chọn database instance; timeout/pool size quyết định behavior hoạt động. Đây không phải mapping Java attribute.

### 37.4. Migration: trạng thái vật lý của database

Một migration thêm cột thật. Nó không diễn giải `<column name="..."/>` theo ý nghĩa Java domain.

### 37.5. Constraint: bảo vệ khi nhiều writers

`CHECK (unit_price >= 0)` bảo vệ DB kể cả khi native SQL bypass Bean Validation/JPA lifecycle.

---

## 38. Quản lý mật khẩu và thông tin nhạy cảm

Không lưu vào XML repository:

```text
Production database password
JDBC URL có embedded password
Private certificates hoặc access tokens
Service credentials
```

### 38.1. Dùng secret manager hoặc môi trường an toàn

Đưa secrets vào runtime qua những cơ chế như environment injection, container secrets hoặc cloud secret store, với access policies rõ.

### 38.2. Không log properties Map nguyên vẹn

`Persistence.createEntityManagerFactory` nhận Map có password. Khi debug, không `System.out.println(overrides)` hoặc ghi toàn bộ config vào log.

### 38.3. Không commit nhiều file persistence-prod.xml có credentials

Tách configuration per environment có thể hữu ích về topology, nhưng secrets vẫn phải nằm ngoài source control.

### 38.4. Encryption không tự giải quyết quản lý key

Mã hóa password rồi lưu ciphertext và key cùng repository không cải thiện đáng kể. Dùng secret storage có rotation/auditing phù hợp.

---

## 39. Version control và review đối với XML mapping

XML không có compiler kiểm tra tên Java field ngay ở thời điểm biên dịch thông thường. Vì vậy workflow review nên chặt chẽ:

- Mapping XML được version control cùng code dùng nó.
- Không sửa XML thủ công trực tiếp trên production server rồi quên commit.
- Mỗi mapping change đi cùng migration (nếu physical schema đổi).
- Có integration tests khởi động EMF và chạy SQL.
- Xác định chủ sở hữu từng mapping file.
- Document lý do override cho legacy cases.
- Dùng formatter/schema validation để giảm lỗi XML.
- Diff schema migration và mapping source cùng trong PR.

### 39.1. Comment cho override khác thường

```xml
<!-- Legacy DB dùng cột "P_NM".
     Không đổi thành "product_name" trước migration V24. -->
<basic name="name">
    <column name="P_NM"/>
</basic>
```

Comment cần giải thích **lý do và constraint thực**, không chỉ nói “override”.

### 39.2. Tránh các giá trị environment-dependent trong XML

Một file mapping “prod-only” không có test có thể trở thành nguồn lỗi deployment. Ưu tiên code artifact có mapping contract nhất quán.

### 39.3. Pin provider/version

JPA standard XML có thể tương đối portable, nhưng provider extensions, naming strategies và SQL dialect behavior vẫn có thể thay đổi giữa releases. Pin versions và kiểm tra upgrade qua integration tests.

### 39.4. Review generated SQL

Một XML change có thể làm đổi join cardinality, fetch behavior hoặc column types. Bên cạnh unit tests, quan sát SQL và execution plan cho critical queries.

---

## 40. Hiệu năng: XML không mặc định nhanh hoặc chậm hơn annotations

Annotations và XML đều trở thành metadata model ở EntityManagerFactory startup. Khi runtime SQL được tạo từ effective metadata, **ngôn ngữ khai báo ban đầu thường không phải yếu tố hiệu năng chính**.

### 40.1. Những thay đổi XML có thể làm hiệu năng khác

- Đổi EAGER/LAZY fetch.
- Đổi join columns/relationship cardinality.
- Đổi index/schema dependencies.
- Thêm association mapping.
- Bật cascade ngoài dự kiến.
- Đổi enum converter, type mapping.
- Đổi named queries hoặc inheritance strategy.

### 40.2. Đừng đánh giá theo file size

Một `orm.xml` 20 KB không nhất thiết khiến ứng dụng chậm; một to-many EAGER mapping trong đó có thể là nguyên nhân thật.

### 40.3. Metadata bootstrap cost

Rất nhiều mapping files/entities có thể ảnh hưởng thời gian EMF startup. Nhưng production hot-path performance thường phụ thuộc SQL, database indexes, fetch plan và caching hơn.

### 40.4. SQL logging cần đúng mức

Bật SQL logging/bind parameter debug trong dev/test hữu ích; trong production phải kiểm soát mức độ log, dữ liệu nhạy cảm và overhead.

---

## 41. Troubleshooting: XML bị bỏ qua, SQL vẫn dùng tên cũ

Triệu chứng:

```text
XML: <table name="catalog_product"/>
SQL log: SELECT ... FROM product ...
```

Các khả năng:

1. Mapping file chưa được đóng gói.
2. Persistence unit thực tế không tham chiếu file đó.
3. File có namespace không khớp hoặc provider không nạp.
4. Entity class name trong XML sai.
5. Có nhiều EMF và repository dùng factory khác.
6. XML override được khai sai element scope.
7. Một mapping XML khác có declaration xung đột.
8. App đang chạy artifact cũ/chưa redeploy.
9. SQL log là của entity/query khác bạn tưởng.

### 41.1. Điều tra từ runtime trước

Xác nhận service đang chạy artifact version nào, EMF nào được tạo, mapping file có trong classpath và SQL log query nào tương ứng.

### 41.2. Không sửa annotations liên tục khi XML override đang hiệu lực

Thay `@Table(name="...")` mà không sửa XML có thể không đổi SQL; xác định effective mapping source trước.

### 41.3. Dùng test nhỏ

Persist/fetch một entity và xem SQL physical table/column. Tách vấn đề metadata khỏi business logic lớn.

### 41.4. Không bật schema auto-create để che lỗi

Nếu SQL báo table not found, tạo bảng tự động trong dev có thể làm test “xanh” nhưng production migration vẫn thiếu. Sửa migration/mapping source đúng.

---

## 42. Troubleshooting: EntityManagerFactory fail khi startup

Các lỗi thường gặp:

| Lỗi | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Mapping file not found | Đường dẫn/resource packaging sai | Kiểm tra artifact và mapping-file |
| XML schema parsing error | Namespace/version/element order sai | Kiểm tra XSD đúng version |
| Unknown managed class | XML class attribute sai package | Cập nhật FQCN và classpath |
| Unknown persistent attribute | `<basic name>`/`mapped-by` không khớp Java member | Kiểm tra access type và attribute name |
| No identifier specified | XML-complete thiếu ID | Khai báo `<id>`/`<embedded-id>` đúng |
| Duplicate entity mapping | Cùng class khai trùng nhiều files | Chọn một authoritative declaration |
| Missing converter class | XML converter class không có trong runtime | Kiểm tra dependency/registration |
| Relationship mismatch | owning side/join column/mapped-by sai | Xác định ownership và FK |
| Unsupported XML element | Copy schema mới cho provider cũ | Đồng bộ spec/provider versions |
| Wrong persistence unit | App khởi tạo unit khác | Cố định EMF/repository bindings |

### 42.1. XML parse pass chưa đủ

Một file đúng cú pháp vẫn có thể map thiếu target entity hoặc SQL join sai; test persistence operations thật.

### 42.2. Entity class đã đổi nhưng XML chưa đổi

Refactor package trong Java không sửa string FQCN trong XML ở mọi IDE. Đặt integration startup test để phát hiện.

### 42.3. Đừng catch EMF startup error rồi tiếp tục chạy

Nếu mappings của core entities không hợp lệ, ứng dụng không thể đảm bảo truy cập dữ liệu đúng. Startup nên fail rõ thay vì chạy nửa vời.

---

## 43. Troubleshooting: dữ liệu sai cột hoặc null

Triệu chứng:

- Product.name thành null sau load.
- Một cột không được INSERT.
- UPDATE ghi sai column.
- Legacy data đọc không đúng.
- Unique constraint lỗi ở cột không mong đợi.

### 43.1. Kiểm tra tên Java attribute

`<basic name="name">` phải trỏ đúng property/field Java theo access type.

### 43.2. Kiểm tra access type

Có thể XML mapping đang dùng PROPERTY nhưng getters/setters khác với field state thực.

### 43.3. Kiểm tra optional/insertable/updatable

Nếu XML column được đánh dấu không insertable hoặc updatable, JPA có thể bỏ cột khỏi SQL ghi. Đừng coi đó là lỗi dirty checking khi đã cấu hình mapping như vậy.

### 43.4. Kiểm tra converter

Converter có thể đổi value/null representation. Nếu XML metadata complete làm mất `@Convert` trước đây, dữ liệu có thể được đọc/ghi khác.

### 43.5. Kiểm tra schema vật lý và triggers

Database trigger/default có thể thay đổi row sau INSERT; XML mapping không tự phản ánh generated value vào entity state nếu provider/mapping không hỗ trợ sync.

---

## 44. XML và naming strategies của provider

JPA mapping XML cho phép explicit table/column names. Nhưng provider cũng có implicit/physical naming strategies.

### 44.1. Explicit vs implicit

Nếu XML chỉ ghi:

```xml
<basic name="createdAt"/>
```

provider sẽ chọn tên column theo defaults/naming strategy. Nếu ghi:

```xml
<column name="created_at"/>
```

bạn đã đặt tên explicit ở mapping layer.

### 44.2. Physical naming strategy có thể vẫn biến đổi identifiers

Trong một số providers, physical naming strategy có thể áp dụng cả các explicit logical names theo quy tắc riêng. Vì vậy không khẳng định tên XML là exact SQL identifier trên mọi provider/configuration mà chưa xem generated SQL.

### 44.3. Identifier quoting

Database reserved words, chữ hoa/thường và quoting có thể làm `Product`/`product`/`"Product"` khác nhau. XML mapping cần phù hợp dialect/quoting policy; tránh dùng reserved words làm columns khi có thể.

### 44.4. Không xử lý lỗi case-sensitive bằng cách đoán

Hãy kiểm tra SQL được sinh và catalog/schema thật trong DB. Các dialect có identifier folding khác nhau.

---

## 45. XML và inheritance strategy

JPA hỗ trợ inheritance mappings như SINGLE_TABLE, JOINED và TABLE_PER_CLASS. XML có thể định nghĩa inheritance metadata phù hợp.

### 45.1. Vì sao đây là thay đổi lớn?

Đổi inheritance strategy có thể đổi số lượng tables, joins, discriminator columns và câu SQL của cả class hierarchy.

### 45.2. Không đổi strategy chỉ để sửa lỗi column name

Một legacy column override không cần thiết phải chuyển inheritance model sang XML-complete hoặc đổi strategy.

### 45.3. Hierarchy mapping cần đồng bộ

Base class, subclasses, discriminator, ID mapping và association relationships phải phù hợp. Khi XML complete được bật ở hierarchy, metadata chỉ nằm trong annotations của một superclass có thể không còn hiệu lực như kỳ vọng.

### 45.4. Cần migration và integration tests

Nếu chuyển SINGLE_TABLE sang JOINED, phải migrate data/keys và kiểm thử polymorphic JPQL, CRUD, cascade, fetching và optimistic locking.

---

## 46. XML và @MappedSuperclass

Một base class:

```java
public abstract class AuditedEntity {

    protected Instant createdAt;

    protected Instant updatedAt;
}
```

Trong full XML metadata strategy, cần nhận diện mapped superclass và persistent fields theo JPA XML metadata phù hợp, không chỉ khai mỗi concrete entity.

### 46.1. Vì sao quan trọng?

Nếu superclass mapping bị thiếu, inherited attributes có thể không được persist hoặc mappings không đúng.

### 46.2. Attribute override ở subclass

Một subclass có thể override inherited column names theo mapping rules. Nhưng phải dùng đúng Java attribute name và không phá inheritance mapping.

### 46.3. @Transient khác mapped superclass

Một abstract Java superclass có fields không tự động tương đương JPA mapped superclass khi metadata-complete khiến annotation bị bỏ. Phải xác định mapping classification rõ.

---

## 47. XML, validation và lifecycle: cái gì được điều khiển bởi nguồn nào?

Một Product có:

```java
@NotBlank
private String name;
```

đây là Jakarta Validation constraint, không phải JPA mapping metadata tương đương `@Column`.

### 47.1. XML mapping-complete chủ yếu liên quan JPA metadata

Đừng suy luận rằng bật JPA `metadata-complete` sẽ tự tắt mọi annotation của mọi framework như Bean Validation, Jackson, Spring Security. Các thư viện đó có introspection riêng.

### 47.2. JPA lifecycle validation có cấu hình khác

`persistence.xml` có `validation-mode` và validation groups properties, nhưng đó là **cấu hình JPA–Bean Validation integration**, khác `orm.xml` mapping column/table.

### 47.3. @PrePersist/@PreUpdate từ annotations có thể bị ảnh hưởng bởi XML metadata override

Entity lifecycle callbacks là một phần JPA metadata; nếu chuyển sang XML-complete, phải xác định listeners/callbacks có còn được đăng ký không. Không để audit timestamps biến mất.

### 47.4. Database constraints vẫn độc lập

`NOT NULL`, `UNIQUE`, `CHECK` và foreign keys do database thực thi. XML không thay thế constraint enforcement cho JDBC/native/bulk writers.

---

## 48. Migration từ annotations sang XML theo từng bước

Không nên chuyển một hệ thống lớn sang XML-complete trong một commit nếu không có kiểm chứng.

### 48.1. Phase 1 — Inventory metadata

Liệt kê các entity annotations hiện có:

- Entity name/table/schema.
- IDs, generators, versions.
- Basic columns/converters/enums.
- Embedded objects.
- Associations, cascade, orphan removal.
- Inheritance, listeners.
- Named queries.
- Vendor-specific mapping extensions.

### 48.2. Phase 2 — Chọn một entity pilot

Ví dụ Product có ít associations, tests rõ.

### 48.3. Phase 3 — Partial override trước

Đổi một column trong `orm.xml`, giữ annotations khác. Xác nhận SQL và DB outcome.

### 48.4. Phase 4 — Full XML nếu thật sự cần

Bật `metadata-complete="true"` cho pilot entity, chuyển toàn bộ mapping cần thiết sang XML. Test version/IDs/associations/callbacks.

### 48.5. Phase 5 — Chia module/ownership

Nếu XML là primary source, đặt file ở persistence adapter module và định nghĩa contribution rules.

### 48.6. Phase 6 — Bảo vệ bằng integration tests

EMF bootstrap, CRUD, associations, optimistic locking, generated IDs, schema migration compatibility.

### 48.7. Phase 7 — Triển khai theo release có kế hoạch

Đảm bảo rollback/backward compatibility với database schema hiện tại.

### 48.8. Không bỏ annotations nếu chưa hoàn chỉnh XML

Việc xóa một loạt annotations và dựa vào defaults XML có thể làm nhiều mapping đổi ngầm mà không xuất hiện lỗi compile.

---

## 49. Migration từ XML sang annotations

Chiều ngược lại cũng phổ biến khi hiện đại hóa hệ thống.

### 49.1. Đọc effective XML mappings

Không copy tùy ý vì XML có thể chứa overrides cho ID, columns, inheritance, query names và listeners.

### 49.2. Chuyển dần sang annotations

Chọn một entity, ánh xạ annotations đầy đủ, loại XML declaration tương ứng có kiểm soát.

### 49.3. Tránh giai đoạn duplicate authoritative metadata kéo dài

Nếu giữ cả XML và annotation với giá trị khác nhau, reviewer có thể tưởng annotation mới đã có hiệu lực dù XML vẫn override.

### 49.4. Test generated SQL tương đương

Mục tiêu là cùng table/column/relationship semantics; thay đổi nguồn metadata không có nghĩa muốn thay schema.

### 49.5. Làm sạch resources

Sau khi XML không còn được dùng, loại `mapping-file` và resource tương ứng có chủ đích, không để “zombie configuration” khiến người sau hiểu sai.

---

## 50. Quản trị cấu hình bằng một bảng ownership

Một team có thể duy trì bảng:

| Cấu hình | Owner | File/nguồn | Quy tắc thay đổi |
|---|---|---|---|
| Product table/column | Persistence team | `catalog-mapping.xml` | PR + SQL integration test |
| Product business constraints | Domain team | Java domain/validation | Unit tests + DB constraints |
| Persistence unit list | Platform/persistence | `persistence.xml` hoặc EMF config | Startup test |
| JDBC credentials | Infrastructure | Secret store | Không commit vào repo |
| Hibernate version/dialect | Platform team | Build + runtime config | Upgrade compatibility test |
| Schema migration | DB/app team | Versioned migrations | Review + deploy plan |
| Production DB schema state | Database operations | Actual DB + migration history | Audited changes |
| Connection pool | Platform | Environment settings | Load test |
| Mapping regression | CI | Integration tests | Blocking checks |

### 50.1. Không nhất thiết có một file bảng như vậy

Đây là mẫu quy trình, có thể nằm trong engineering handbook/ADR. Điều quan trọng là mọi developer biết nơi cần sửa.

### 50.2. Đặt lý do override gần khai báo

Khi XML là exception, comment/mapping test có thể giải thích tại sao không sửa annotation trực tiếp.

### 50.3. Xóa cấu hình chết

Nếu XML mapping không còn được nạp nhưng vẫn nằm trong repository, người sau dễ chỉnh sai nơi. Dùng integration tests và review để loại dead configuration.

### 50.4. Chạy kiểm tra trên artifact deploy

Không chỉ chạy tests trên source/classes khác với fat JAR thực tế; resource packaging là phần của correctness.

---

## 51. Các tình huống thực tế và hướng xử lý

### 51.1. Database legacy dùng tên cột lạ

**Bài toán:** Entity Java dùng `customerName` nhưng DB column là `C_NM`.

**Hướng:** Partial XML override `<basic name="customerName"><column name="C_NM"/></basic>`; thêm test persist/load; migration không cần nếu schema legacy giữ nguyên.

### 51.2. Đổi schema dev/prod

**Bài toán:** Dev schema `catalog_dev`, prod schema `catalog`.

**Hướng:** Xác định schema routing/defaults ở datasource/provider level nếu phù hợp; tránh maintain hai mapping XML khác nhau mà không test. Không cho request tự thay orm.xml.

### 51.3. Refactor Java field

**Bài toán:** Đổi `name` thành `displayName` trong entity.

**Hướng:** Cập nhật XML `name` attribute, JPQL Criteria usage, tests. Nếu physical column không đổi, không nhất thiết migration.

### 51.4. Full XML bỏ mất @Version

**Bài toán:** Sau chuyển `metadata-complete=true`, optimistic locking không hoạt động.

**Hướng:** Khai `<version name="version">` đúng XML, kiểm tra DB row_version, concurrency integration test.

### 51.5. Quan hệ nhiều-một đổi FK

**Bài toán:** DB chuyển `customer_id` sang `buyer_id`.

**Hướng:** Migration FK/data/indexes + XML `<join-column name="buyer_id"/>` + tests nhiều entities. Không chỉ đổi annotation.

### 51.6. Spring Boot không nạp orm.xml

**Bài toán:** File đúng nhưng SQL vẫn dùng annotation.

**Hướng:** Kiểm tra factory thực tế, mapping resources, classpath, startup logs và SQL. Không giả định persistence.xml được Boot tự đọc trong mọi cấu hình.

### 51.7. Lỗi XML chỉ xảy ra trên production

**Bài toán:** Local chạy nhưng production báo file not found.

**Hướng:** So sánh deploy artifact/classpath/build profiles, không so sánh riêng source trees.

### 51.8. Đổi @Column nhưng runtime không đổi

**Bài toán:** Developer sửa annotation nhưng SQL không đổi.

**Hướng:** Kiểm tra XML override effective và có metadata-complete hay không.

### 51.9. Query chạy nhưng sai dữ liệu

**Bài toán:** Một column join mapping nhầm tới ID khác.

**Hướng:** Kiểm tra owner, referenced column, schema FK, SQL và test với nhiều data records.

### 51.10. EntityFactory startup thành công nhưng index thiếu

**Bài toán:** Query chậm dù mappings chính xác.

**Hướng:** XML không tự tối ưu DB indexes; migration/index/execution plan và workload tests cần xử lý riêng.

---

## 52. Anti-pattern phổ biến

### 52.1. Sửa XML mà nghĩ database tự đổi tên bảng

Mapping file không phải schema migration.

### 52.2. Sửa @Column trong khi XML override vẫn đang tồn tại

Annotation change có thể không có hiệu lực.

### 52.3. Dùng metadata-complete chỉ để đổi một column

Có thể làm mất IDs/versions/associations/listeners từ annotations.

### 52.4. Dùng XML name là tên SQL column thay vì Java property

`<basic name="display_name">` sai nếu Java field tên `name`.

### 52.5. Khai mapped-by là tên FK

`mapped-by="customer_id"` sai nếu Java owning property tên `customer`.

### 52.6. Bật global xml-mapping-metadata-complete không có inventory

Có thể khiến nhiều entities thiếu mapping.

### 52.7. Tin nhiều XML files được áp override theo thứ tự tự chọn

Trùng declarations có thể gây failure/behavior không portable.

### 52.8. Đặt mapping file ngoài classpath

Local file tồn tại nhưng artifact không có.

### 52.9. Hard-code absolute Windows/Linux path trong mapping-file

Không portable khi deploy JAR/container.

### 52.10. Dùng namespace javax cũ với Jakarta stack mới

Có thể fail parser/provider hoặc sai XML version.

### 52.11. Đổi version XML mà không kiểm tra provider

Unsupported tags/schema có thể làm EMF fail.

### 52.12. Tạo nhiều EMF rồi không biết repository dùng factory nào

Mapping changes áp vào factory không sử dụng.

### 52.13. Đưa password production vào persistence.xml

Rủi ro lộ secrets.

### 52.14. Cố thay mapping bằng environment variable không được provider hiểu

Không có property JPA chuẩn tùy ý `product.table` để đổi table.

### 52.15. Dùng Hibernate auto-update làm migration production

Schema drift và deployment khó kiểm soát.

### 52.16. Không test khi XML đổi join column

Một query đơn giản có thể không lộ FK sai.

### 52.17. Nghĩ @Cacheable hoặc cache sẽ tự invalidate khi mapping đổi

Cache/EMF được tạo từ metadata boot time; thay file có thể cần restart/redeploy/invalidation.

### 52.18. Dùng cùng persistence context sau đổi config và mong metadata mới

Mapping không tự đổi với EntityManager đang mở.

### 52.19. Bỏ @Version vô tình khi chuyển full XML

Có thể gây lost updates.

### 52.20. Quên ID generator khi chuyển XML

Entity mới có thể fail INSERT/ID mapping.

### 52.21. Trộn field và property access không theo quy tắc

Entity state có thể được ánh xạ khác dự kiến.

### 52.22. Xem JPA cascade như database ON DELETE CASCADE

Hai cơ chế độc lập.

### 52.23. Bật cascade remove trên shared reference entity

Có thể xóa nhiều rows ngoài dự kiến.

### 52.24. Nghĩ JOIN FETCH là khóa quan hệ

Fetch plan không phải row-lock strategy.

### 52.25. Mapping @Embedded hai lần nhưng không override columns

Có thể gây duplicate column mappings.

### 52.26. Không cập nhật named queries sau refactor field

JPQL dùng Java attribute names.

### 52.27. Bật XML complete và nghĩ Bean Validation annotations cũng luôn tắt

JPA metadata-complete không phải công tắc toàn bộ annotation frameworks.

### 52.28. Chỉ test em.find cùng EntityManager sau persist

L1 identity cache có thể che lỗi reload từ SQL.

### 52.29. Chỉ dùng H2 để khẳng định production SQL dialect đúng

Different DBs have different identifiers, sequences and joins.

### 52.30. Không đọc SQL log/provider startup errors

Mapping problems có thể chỉ lộ lúc runtime SQL.

### 52.31. Hard-code schema tên dev vào mapping dùng ở production

Có thể truy cập sai namespace.

### 52.32. Thay converter mà không migrate existing rows

New converter có thể không đọc được dữ liệu cũ.

### 52.33. Đổi nullable mapping mà không thêm DB NOT NULL

External SQL vẫn có thể INSERT null.

### 52.34. Dùng XML overrides để lách authorization/tenant filters

Mapping không tự xác thực user hay chặn cross-tenant access.

### 52.35. Sửa mapping trực tiếp trên server mà không commit git

Khó tái lập và rollback.

### 52.36. Không có ownership giữa annotation, XML và migration

Một thay đổi có thể được sửa ở nơi không có hiệu lực.

### 52.37. Quên provider-specific extensions khi migrate XML

XML JPA portable có thể không mô tả mọi tính năng vendor-specific.

### 52.38. Để dead orm.xml nằm trong repo

Developer tiếp tục chỉnh file không được nạp.

---

## 53. Bài tập thực hành có gợi ý

### Bài 1 — Phân biệt hai XML files

`persistence.xml` và `orm.xml` khác nhau ở đâu?

**Gợi ý:** Persistence unit/bootstrap vs mapping metadata.

### Bài 2 — Tạo persistence unit

Viết `persistence.xml` khai `catalogPU` và `mapping-file=META-INF/catalog-mapping.xml`.

**Gợi ý:** Dùng namespace Jakarta phù hợp, `persistence-unit name` và `mapping-file` trước `class` theo cấu trúc XML.

### Bài 3 — Mapping file ở đâu?

Vì sao `src/main/resources/META-INF/catalog-mapping.xml` tồn tại nhưng startup báo not found?

**Gợi ý:** Kiểm tra artifact/classpath resource packaging.

### Bài 4 — Override table

Java `@Table(name="product")` nhưng DB legacy dùng `catalog_item`.

**Gợi ý:**

```xml
<entity class="com.example.catalog.domain.Product">
    <table name="catalog_item"/>
</entity>
```

### Bài 5 — Override column

Java attribute `name`, DB column `display_name`.

**Gợi ý:**

```xml
<basic name="name">
    <column name="display_name"/>
</basic>
```

### Bài 6 — Tên Java hay tên DB?

`<basic name="display_name">` có đúng nếu class chỉ có field `name`?

**Đáp án:** Không. `name` là Java persistent member name.

### Bài 7 — Partial override

Chỉ muốn đổi table name, có bắt buộc XML complete không?

**Đáp án:** Không. Có thể override phần liên quan.

### Bài 8 — metadata-complete

Điều gì xảy ra nếu XML complete quên khai `<id>`?

**Gợi ý:** Entity mapping có thể không hợp lệ/EMF startup fail.

### Bài 9 — @Version bị mất

Java có `@Version`, XML complete không khai version.

**Gợi ý:** Khai `<version name="version">`, test optimistic concurrency.

### Bài 10 — Global complete

Có nên bật `<xml-mapping-metadata-complete/>` cho cả persistence unit để sửa một relation?

**Gợi ý:** Không; phạm vi rộng và nhiều rủi ro.

### Bài 11 — Field vs property

Nếu XML `access="PROPERTY"`, `<basic name="name">` tham chiếu gì?

**Đáp án:** JavaBean property `name`, thường qua `getName`/`setName`.

### Bài 12 — @Id generated

Mapping `SEQUENCE` cần gì ngoài `<generated-value>`?

**Gợi ý:** Sequence generator declaration phù hợp và database sequence/schema migration.

### Bài 13 — Change generator

Chuyển IDENTITY sang SEQUENCE chỉ sửa XML có đủ không?

**Gợi ý:** Không. Kiểm tra DB support, sequence, allocation, migration và provider.

### Bài 14 — ManyToOne FK

Order.customer mapped tới `customer_id`.

**Gợi ý:** Dùng `<many-to-one name="customer">` và `<join-column name="customer_id"/>`.

### Bài 15 — mapped-by

Order.lines inverse side của OrderLine.order.

**Gợi ý:** `mapped-by="order"`, không phải `mapped-by="order_id"`.

### Bài 16 — Bidirectional ownership

Chỉ thêm Line vào Order.lines nhưng quên set Line.order.

**Gợi ý:** XML mapping không tự đồng bộ owning side; dùng helper domain methods.

### Bài 17 — Embedded Address

Customer có billingAddress/shippingAddress cùng type.

**Gợi ý:** Override street/city columns để tránh collision.

### Bài 18 — Named JPQL

Nếu Java property là `active`, table column là `is_active`, JPQL dùng gì?

**Đáp án:** `p.active`.

### Bài 19 — XML namespace

XML copy từ JPA `javax` cũ vào Jakarta provider mới báo schema parsing error.

**Gợi ý:** Dùng namespace/version phù hợp API/provider.

### Bài 20 — L2 and metadata

Sửa XML tại runtime có làm EntityManager đang mở thay table mapping không?

**Đáp án:** Không; mapping được resolve khi xây EMF.

### Bài 21 — Source of truth

Annotations và XML cùng khai table khác nhau.

**Gợi ý:** Kiểm tra XML được nạp và override semantics, chọn nguồn authoritative.

### Bài 22 — Hai mapping files trùng class

File A và B đều khai Product table name.

**Gợi ý:** Không dựa vào mapping-file order như override chain; loại declarations xung đột.

### Bài 23 — Schema drift

XML đã đổi column thành display_name nhưng DB chỉ có product_name.

**Gợi ý:** Cần migration DB, integration test.

### Bài 24 — Rolling deployment

App cũ dùng product_name, app mới dùng display_name.

**Gợi ý:** Cân nhắc expand-and-contract migration để có compatibility window.

### Bài 25 — Runtime secrets

Có nên commit password vào `persistence.xml`?

**Đáp án:** Không; dùng secret store/runtime injection.

### Bài 26 — Runtime properties

`Persistence.createEntityManagerFactory("catalogPU", properties)` có thể dùng làm gì?

**Gợi ý:** Bootstrap property overrides, không tùy ý đổi every table mapping.

### Bài 27 — Spring Boot

File `persistence.xml` tồn tại nhưng service thực tế dùng EMF auto-config khác.

**Gợi ý:** Xác định EMF/repository binding, mapping resources được nạp.

### Bài 28 — Metamodel

Làm sao kiểm tra Product đã được nhận là entity?

**Gợi ý:** `em.getMetamodel().entity(Product.class)`.

### Bài 29 — Physical columns

JPA Metamodel có portable API `getColumnName()` cho mọi attribute không?

**Đáp án:** Không; dùng SQL/provider metadata/DB introspection để xác minh.

### Bài 30 — L1 che lỗi test

Test persist rồi `find` trong cùng EM, assert field đúng.

**Gợi ý:** Có thể chỉ lấy L1; clear/context mới và kiểm tra SQL/DB.

### Bài 31 — Relationship integration

Làm sao xác minh XML mapped FK đúng?

**Gợi ý:** Persist parent/child, commit, query FK tại DB, load relationship trong EM mới.

### Bài 32 — Unique constraints

Mapping XML ghi tên cột chính xác có ngăn duplicate SKU không?

**Gợi ý:** Cần DB UNIQUE constraint và xử lý concurrency.

### Bài 33 — Nullable

Sửa XML `nullable="false"` có làm cột production NOT NULL ngay không?

**Đáp án:** Không nếu không có migration/schema change tương ứng.

### Bài 34 — Converter

Đổi cách converter ghi enum từ tên dài sang mã ngắn.

**Gợi ý:** Migration existing values và compatibility.

### Bài 35 — Cache trong multi-node

Hai nodes dùng cùng EMF metadata version nhưng one node chạy artifact cũ.

**Gợi ý:** Versioned deployment, consistency tests, rollback plan, không assume mọi JVM đồng bộ khi file thay đổi.

### Bài 36 — Tenant schema

Có nên thay orm.xml cho mỗi request tenant?

**Gợi ý:** Không; dùng multi-tenancy routing strategy/provider mechanisms.

### Bài 37 — Hibernate validate

`hibernate.hbm2ddl.auto=validate` là chuẩn `jakarta.persistence.schema-generation.database.action`?

**Đáp án:** Không. Đây là provider-specific setting.

### Bài 38 — Metadata-complete và callbacks

Chuyển sang full XML, audit listener annotation không còn hoạt động như dự kiến.

**Gợi ý:** Xem JPA lifecycle metadata override, khai listener/callback trong XML đúng và test.

### Bài 39 — SQL performance

XML đổi một quan hệ sang EAGER, endpoint danh sách chậm.

**Gợi ý:** Kiểm tra fetch plan/N+1/row multiplication, không kết luận “XML chậm”.

### Bài 40 — Quản lý ownership

Team Java sửa annotations, team DB sửa orm.xml, migration không cập nhật.

**Gợi ý:** Có một nguồn mapping có thẩm quyền, PR checklist mapping+schema và integration tests.

---

## 54. Checklist thay đổi XML mapping

Trước khi merge một thay đổi `orm.xml`:

- [ ] Đã xác định `menuLevel2`/use case cụ thể cần override thay vì sửa annotations.
- [ ] Đã phân biệt `persistence.xml` với mapping XML.
- [ ] Mapping resource nằm trong artifact classpath thực tế.
- [ ] `mapping-file` path đúng và không khai duplicate ngoài ý muốn.
- [ ] Persistence unit và EMF mà service dùng đã được xác định.
- [ ] XML namespace/version khớp JPA provider.
- [ ] Schema/XSD elements được khai đúng cấu trúc.
- [ ] Java fully qualified class name còn chính xác.
- [ ] `name` trong `<basic>`/`<id>`/`mapped-by` là Java member name phù hợp.
- [ ] Field vs PROPERTY access được chọn rõ.
- [ ] Partial XML override chỉ ghi đè đúng phần cần.
- [ ] Nếu metadata-complete, mọi ID/version/associations/converters/callbacks cần thiết đã được mô tả.
- [ ] Nếu global complete, đã kiểm tra toàn persistence unit.
- [ ] Không có mapping declarations xung đột giữa files.
- [ ] Table/column/schema/cataloɡ naming khớp database.
- [ ] Generated-value strategy khớp DB và migration.
- [ ] FK/association ownership/cascade được hiểu rõ.
- [ ] Embedded attribute overrides không collision.
- [ ] Named JPQL query vẫn dùng Java property names.
- [ ] Provider extensions được ghi rõ và pin version.
- [ ] Không dùng XML cho secrets/authorization logic.
- [ ] Thay đổi mapping DB vật lý đi cùng migration versioned.
- [ ] Rolling deployment compatibility được xem xét.
- [ ] Không dùng schema auto-update làm production migration.
- [ ] Integration test bootstraps EMF thành công.
- [ ] Test INSERT/UPDATE/SELECT trên schema thật, đọc lại context mới.
- [ ] Test quan hệ, ID generation, version conflict nếu bị ảnh hưởng.
- [ ] Đã xem generated SQL và các indices/queries hot.
- [ ] Không quên multi-tenant schema/connection routing và cache scope.
- [ ] Có owner/reviewers cho XML và migration.
- [ ] Có cách rollback/forward fix khi deploy.

## 55. Bảng tra cứu nhanh

| Nhu cầu | Cơ chế hoặc file |
|---|---|
| Định nghĩa persistence unit | `META-INF/persistence.xml` |
| Định nghĩa entity mappings bằng XML | `META-INF/orm.xml` hoặc resource mapping tùy tên |
| Tham chiếu mapping file | `<mapping-file>resource-path</mapping-file>` |
| Chọn JPA provider | `<provider>...` hoặc bootstrap/framework config |
| Chọn entity class | `<class>...` hoặc entity discovery/XML mapping |
| Đặt entity table bằng XML | `<entity><table name="..."/></entity>` |
| Đặt basic column bằng XML | `<basic name="x"><column name="..."/></basic>` |
| Đặt ID bằng XML | `<id name="id"/>` |
| Generated ID | `<generated-value>` và generator metadata phù hợp |
| Version field | `<version name="version">` |
| Many-to-one FK | `<many-to-one>` + `<join-column>` |
| One-to-many inverse side | `<one-to-many mapped-by="...">` |
| Embedded mapping | `<embedded>` + `<attribute-override>` |
| XML named query | `<named-query>` |
| Entity callbacks/listeners | XML `<entity-listeners>` hoặc Java annotations |
| Ghi đè một phần annotations | XML declarations cho metadata cụ thể |
| Mapping đầy đủ entity | `metadata-complete="true"` |
| Mapping đầy đủ persistence unit | `<xml-mapping-metadata-complete/>` |
| Shared defaults | `<persistence-unit-defaults>` |
| Field mapping | `access="FIELD"` |
| Property mapping | `access="PROPERTY"` |
| Runtime override properties | `Persistence.createEntityManagerFactory(name, map)` |
| Kết nối DB | DataSource/JDBC properties/runtime secrets |
| Thay table/column vật lý | Versioned DB migration |
| Đổi XML khi app đang chạy | Thường cần rebuild/redeploy/rebootstrap EMF |
| Xác minh Java attributes | `em.getMetamodel()` |
| Xác minh SQL table/columns | SQL logging/provider metadata/DB queries |
| Schema validation Hibernate | Provider-specific `hibernate.hbm2ddl.auto=validate` |
| JPA schema generation action | `jakarta.persistence.schema-generation.database.action` |
| Chặn duplicate SKU | Database UNIQUE constraint |
| Ngăn lost update | `@Version`/XML `<version>` + concurrency strategy |
| Multi-tenancy | Provider/architecture strategy, không thay XML per request |

## 56. Tổng kết

Những nguyên tắc quan trọng nhất:

1. **`persistence.xml` và `orm.xml` có trách nhiệm khác nhau**: file đầu định nghĩa persistence unit, file sau định nghĩa hoặc ghi đè mapping metadata.
2. **XML có thể ghi đè mapping annotations** với những metadata được khai đúng, nhưng phải xét metadata-complete và rules của persistence unit.
3. **Partial override thường an toàn hơn full XML mapping** khi chỉ đổi table/column của một legacy entity.
4. **`metadata-complete="true"` làm thay đổi nguồn metadata**; nếu thiếu ID, version, listeners hoặc relationships trong XML, mapping có thể không còn như source annotations.
5. **`<xml-mapping-metadata-complete/>` có phạm vi rộng**, không nên bật chỉ để xử lý một field.
6. **XML attribute names là Java persistent member names**, còn `<column name="...">`/`<table name="...">` là database identifiers.
7. **Association mapping cần đúng owning side, join columns và mapped-by**, XML không tự giữ hai phía object relationship đồng bộ.
8. **XML mapping resource phải được đóng gói/nạp vào đúng EntityManagerFactory**, không chỉ tồn tại trong source tree.
9. **Không có một quy tắc ưu tiên chung cho mọi nguồn cấu hình**. Annotation/XML mapping, persistence properties, framework config và DB schema thuộc những lớp khác nhau.
10. **Connection URL, secrets, pool configuration nên nằm ở runtime environment/secret management**, không nhúng vào XML mapping source.
11. **Thay XML không tự migrate schema production**. Database migrations phải có version, review, compatibility plan và rollback strategy.
12. **Không đổi XML mapping per request**; EntityManagerFactory quản lý effective metadata được thiết lập khi bootstrap.
13. **Kiểm tra effective mapping bằng startup tests, Metamodel và SQL/database integration tests**; Java compile thành công không chứng minh XML đúng.
14. **Một nguồn có thẩm quyền cho mỗi loại metadata** giúp tránh drift giữa annotations, XML, runtime settings và migration.
15. **Provider/dialect/version-specific behavior phải được kiểm chứng**, đặc biệt với schema, ID generators, fetch plans, cache và query naming.

**Kết luận:** Ghi đè ánh xạ bằng XML trong JPA là công cụ hữu ích khi cần tách mapping khỏi Java source hoặc tương thích với schema legacy. Thành công không nằm ở việc có thêm một `orm.xml`, mà ở việc **quản lý được nguồn cấu hình có hiệu lực**: biết file nào được nạp, metadata nào bị ghi đè, transaction/data source nào đang dùng, và database schema thực sự có cấu trúc ra sao. Khi áp dụng XML overrides có phạm vi rõ, quản lý secrets đúng nơi, sử dụng migrations có version và kiểm chứng bằng integration tests, ứng dụng giữ được tính nhất quán giữa domain model, JPA metadata và relational database mà không tạo ra những cấu hình chồng chéo khó bảo trì.
