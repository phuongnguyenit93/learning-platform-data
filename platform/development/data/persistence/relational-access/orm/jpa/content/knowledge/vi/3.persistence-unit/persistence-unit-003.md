# Khai báo lớp entity, tệp ánh xạ và nguồn dữ liệu

## 1. Persistence Unit là gì?

Trong Jakarta Persistence (JPA), **Persistence Unit (PU)** là một đơn vị cấu hình logic xác định **những lớp nào được quản lý như thực thể, siêu dữ liệu ánh xạ của chúng nằm ở đâu, và JPA kết nối với nguồn dữ liệu nào**. Khi ứng dụng yêu cầu một `EntityManagerFactory` cho một PU, JPA provider (ví dụ Hibernate) đọc cấu hình và xây dựng mô hình ánh xạ tương ứng.

Ba thành phần cần nắm vững khi khai báo một PU:

1. **Lớp entity**: những lớp Java cần được quản lý bằng JPA, định danh bằng annotation `@Entity` hoặc cấu hình XML.
2. **Tệp ánh xạ**: những chỉ dẫn về bảng, cột, khóa, quan hệ, cách truy cập thuộc tính; có thể dùng annotation và/hoặc `orm.xml`.
3. **Nguồn dữ liệu**: nơi cung cấp kết nối tới cơ sở dữ liệu, thông qua `DataSource` hoặc cấu hình JDBC, gắn với cách quản lý giao dịch.

Sơ đồ liên hệ:

```text
Ứng dụng Java
    |
    |  Persistence.createEntityManagerFactory("shopPU")
    |  hoặc @PersistenceContext(unitName = "shopPU")
    v
+------------------------------------------------------+
| Persistence Unit: shopPU                             |
|                                                      |
|  Entity classes ── Product, Customer, ...            |
|  Mapping        ── @Entity/@Table/... + orm.xml      |
|  Provider       ── Hibernate hoặc triển khai JPA khác|
|  Transaction    ── RESOURCE_LOCAL hoặc JTA           |
|  Connection     ── JDBC properties / DataSource      |
+------------------------------------------------------+
    |
    v
 EntityManagerFactory -> EntityManager -> SQL -> Database
```

**Phân biệt phạm vi:** PU là cấu hình và tập thực thể được quản lý; `EntityManagerFactory` được tạo dựa trên PU và thường tồn tại lâu; `EntityManager` là đối tượng thao tác với persistence context trong một đơn vị công việc. Một cơ sở dữ liệu có thể phục vụ nhiều PU, và một ứng dụng có thể khai báo nhiều PU với mục đích khác nhau.

## 2. Tệp trung tâm: `META-INF/persistence.xml`

### 2.1. Vị trí và cấu trúc thư mục

Với dự án Java dùng cấu trúc Maven/Gradle tiêu chuẩn, một cách bố trí điển hình là:

```text
src/
└── main/
    ├── java/
    │   └── com/example/shop/
    │       ├── App.java
    │       └── domain/
    │           ├── Product.java
    │           └── Customer.java
    └── resources/
        └── META-INF/
            ├── persistence.xml
            └── orm.xml
```

Khi đóng gói, các tài nguyên được đưa vào classpath, ví dụ `META-INF/persistence.xml`. JPA tìm các tệp cấu hình PU ở vị trí này trong các artifact thích hợp. **`persistence.xml` không phải tệp cấu hình Spring tùy ý**: tên, vị trí, namespace và cấu trúc XML phải tuân theo đặc tả Jakarta Persistence tương ứng.

### 2.2. Ví dụ PU chạy trong Java SE với JDBC

Giả sử ứng dụng cửa hàng có `Product` được ánh xạ bằng annotation và `Customer` được ánh xạ bằng XML. Trong ví dụ học tập dưới đây, cơ sở dữ liệu H2 chạy trong bộ nhớ; JPA provider là Hibernate.

**`src/main/resources/META-INF/persistence.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence
    xmlns="https://jakarta.ee/xml/ns/persistence"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        https://jakarta.ee/xml/ns/persistence
        https://jakarta.ee/xml/ns/persistence/persistence_3_1.xsd"
    version="3.1">

    <persistence-unit name="shopPU" transaction-type="RESOURCE_LOCAL">
        <provider>org.hibernate.jpa.HibernatePersistenceProvider</provider>

        <mapping-file>META-INF/orm.xml</mapping-file>
        <class>com.example.shop.domain.Product</class>
        <exclude-unlisted-classes>true</exclude-unlisted-classes>

        <properties>
            <property name="jakarta.persistence.jdbc.driver"
                      value="org.h2.Driver"/>
            <property name="jakarta.persistence.jdbc.url"
                      value="jdbc:h2:mem:shop;DB_CLOSE_DELAY=-1"/>
            <property name="jakarta.persistence.jdbc.user"
                      value="sa"/>
            <property name="jakarta.persistence.jdbc.password"
                      value=""/>

            <!-- Dành riêng cho ví dụ cơ sở dữ liệu tạm -->
            <property name="jakarta.persistence.schema-generation.database.action"
                      value="create"/>
        </properties>
    </persistence-unit>
</persistence>
```

Đây là ví dụ dùng **Jakarta Persistence 3.1**. Nếu dự án dùng phiên bản đặc tả khác, phải dùng phiên bản/schema phù hợp và thư viện tương thích; đừng trộn namespace `jakarta.persistence` với các gói `javax.persistence` của những thế hệ JPA cũ.

Giải nghĩa các thành phần:

| Thành phần | Ý nghĩa |
|---|---|
| `<persistence>` | Phần tử gốc chứa một hoặc nhiều PU. |
| `version="3.1"` và `xsi:schemaLocation` | Xác định phiên bản định dạng XML và schema để kiểm tra cấu trúc. |
| `<persistence-unit name="shopPU">` | Đặt tên duy nhất để ứng dụng chọn PU cần khởi tạo. |
| `transaction-type="RESOURCE_LOCAL"` | EntityManager dùng `EntityTransaction` để tự quản lý giao dịch, thích hợp cho ví dụ Java SE. |
| `<provider>` | Tên lớp JPA provider; có thể bỏ qua nếu môi trường có cơ chế chọn provider phù hợp. |
| `<mapping-file>` | Đăng ký tệp metadata ánh xạ XML trong classpath. |
| `<class>` | Đăng ký tường minh một lớp được quản lý. |
| `<exclude-unlisted-classes>` | Với `true`, hạn chế tự đưa các lớp chưa được liệt kê/phát hiện qua metadata phù hợp vào PU. |
| `<properties>` | Các tham số JDBC và các tùy chọn chuẩn hoặc riêng provider. |

Các thuộc tính `jakarta.persistence.jdbc.*` thiết lập kết nối JDBC trực tiếp. Ứng dụng còn cần có **driver JDBC của H2** và **JPA provider** tương ứng trên classpath/runtime. Khai báo tên driver trong XML **không tự tải thư viện driver**.

> **Lưu ý về schema:** `jakarta.persistence.schema-generation.database.action=create` chỉ phù hợp cho môi trường thử nghiệm có thể tạo lại dữ liệu. Trong môi trường thật, nên kiểm soát thay đổi lược đồ bằng migration và tránh cấu hình có thể xóa/tạo lại bảng ngoài ý muốn.

## 3. Khai báo lớp entity

### 3.1. Entity bằng annotation

Tạo lớp `Product` trong package đúng với giá trị `<class>` ở trên:

**`src/main/java/com/example/shop/domain/Product.java`**

```java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.math.BigDecimal;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "product_name", nullable = false, length = 150)
    private String name;

    @Column(name = "price", nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    protected Product() {
        // Constructor không tham số để JPA khởi tạo entity.
    }

    public Product(String name, BigDecimal price) {
        this.name = name;
        this.price = price;
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

    public void changePrice(BigDecimal newPrice) {
        this.price = newPrice;
    }
}
```

Ở đây:

- `@Entity` đánh dấu lớp là entity được JPA quản lý.
- `@Table(name = "products")` khai báo bảng; nếu bỏ qua, tên bảng được suy ra theo quy tắc mặc định và có thể chịu ảnh hưởng chiến lược đặt tên của provider.
- `@Id` xác định khóa chính của entity. Một entity thường có một khóa chính đơn hoặc khóa chính ghép (`@EmbeddedId`, `@IdClass`).
- `@GeneratedValue` chỉ cách sinh khóa; `IDENTITY` dựa trên cơ chế nhận dạng của cột và khả năng của hệ cơ sở dữ liệu.
- `@Column` tùy chỉnh tên, khả năng chấp nhận null và độ chính xác biểu diễn cột.
- Constructor không tham số `public` hoặc `protected` hỗ trợ JPA tạo đối tượng.
- Annotation đặt ở **field** cùng vị trí với `@Id`, vì vậy ví dụ sử dụng **field access**: JPA đọc/ghi các trường trực tiếp thay vì gọi getter/setter để truy cập trạng thái lưu trữ.

Trong mô hình JPA thông thường, entity phải là lớp có thể được quản lý theo các ràng buộc của đặc tả; không nên khai báo lớp entity là `final` hoặc coi nó như một record Java bất biến. Tùy provider, một số tối ưu như proxy và lazy loading còn phụ thuộc khả năng mở rộng lớp/phương thức.

### 3.2. Entity phải được đưa vào PU bằng cách nào?

Đánh dấu `@Entity` và khai báo `<class>` là hai việc khác nhau:

- **`@Entity`** mô tả vai trò và ánh xạ của lớp.
- **`<class>com.example.shop.domain.Product</class>`** đưa lớp đó vào danh sách được quản lý trong PU tương ứng.
- Một số môi trường có thể tự quét các lớp được đánh dấu `@Entity`. Phạm vi quét phụ thuộc cách đóng gói và cách bootstrap; **liệt kê tường minh giúp ví dụ Java SE dễ tái hiện và tránh phụ thuộc vào hành vi quét riêng**.
- `<exclude-unlisted-classes>true</exclude-unlisted-classes>` làm rõ ý định quản lý các lớp đã đăng ký tường minh hoặc thông qua tệp ánh xạ. Nó không có nghĩa các lớp trong `orm.xml` sẽ bị loại bỏ.

Nếu entity có quan hệ với những entity khác, cần bảo đảm tất cả các kiểu entity tham gia được quản lý phù hợp bởi PU. Một Java class bình thường thiếu ánh xạ entity hợp lệ không đương nhiên trở thành bảng chỉ vì được một entity khác tham chiếu.

### 3.3. Những loại lớp liên quan nhưng không giống entity

| Loại | Annotation thường dùng | Vai trò |
|---|---|---|
| Entity | `@Entity` | Có định danh riêng; được quản lý và có vòng đời persistence. |
| Value object nhúng | `@Embeddable`; được dùng qua `@Embedded` | Các thuộc tính được nhúng vào entity chứa, thường không có định danh độc lập. |
| Lớp cha dùng chung mapping | `@MappedSuperclass` | Chia sẻ mapping cho các entity kế thừa; không phải một thực thể có thể truy vấn độc lập như entity. |
| DTO/projection | Không cần annotation JPA | Dùng để truyền dữ liệu hoặc nhận kết quả truy vấn; không được theo dõi dirty checking. |

PU quản lý nhiều loại metadata, nhưng chỉ những lớp có ánh xạ **entity** mới có vòng đời entity với `persist`, `find` và `remove` như một thực thể độc lập.

## 4. Khai báo tệp ánh xạ XML

### 4.1. Tại sao dùng `orm.xml`?

Dù annotation tiện lợi vì nằm ngay trong mã, ánh xạ XML vẫn hữu ích khi:

- Không muốn hoặc không thể sửa mã nguồn lớp Java.
- Cần để metadata ánh xạ ngoài mã ứng dụng.
- Muốn quy định tường minh tên bảng/cột hoặc cấu hình ánh xạ cho một PU.
- Phải tích hợp hệ thống cũ, một số entity được định nghĩa bằng Java class thuần.

JPA có thể sử dụng **annotation, XML hoặc kết hợp cả hai**. Cần hiểu rõ cách metadata được hợp nhất hoặc ghi đè; nếu cùng một thuộc tính được khai báo khác nhau ở nhiều nơi mà không có chủ đích, cấu hình sẽ khó kiểm soát.

### 4.2. Khai báo entity hoàn toàn bằng XML

Giả sử `Customer` là một Java class bình thường, **không gắn `@Entity`**:

**`src/main/java/com/example/shop/domain/Customer.java`**

```java
package com.example.shop.domain;

public class Customer {
    private Long id;
    private String fullName;

    public Customer() {
    }

    public Customer(String fullName) {
        this.fullName = fullName;
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public void rename(String newName) {
        this.fullName = newName;
    }
}
```

Tạo tệp mapping tại đúng nơi đã khai báo trong `persistence.xml`:

**`src/main/resources/META-INF/orm.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<entity-mappings
    xmlns="https://jakarta.ee/xml/ns/persistence/orm"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        https://jakarta.ee/xml/ns/persistence/orm
        https://jakarta.ee/xml/ns/persistence/orm/orm_3_1.xsd"
    version="3.1">

    <entity class="com.example.shop.domain.Customer"
            access="FIELD">
        <table name="customers"/>
        <attributes>
            <id name="id">
                <generated-value strategy="IDENTITY"/>
            </id>
            <basic name="fullName">
                <column name="full_name" nullable="false"
                        length="150"/>
            </basic>
        </attributes>
    </entity>
</entity-mappings>
```

Ý nghĩa:

- `<entity class="...Customer">` cho JPA biết Java class này có metadata của một entity, dù lớp không có annotation `@Entity`.
- `access="FIELD"` yêu cầu ánh xạ theo trường.
- `<table>` và `<column>` nối tên class/field với bảng và cột.
- `<id>` khai báo thuộc tính nhận dạng và `<generated-value>` khai báo chiến lược sinh ID.
- `<mapping-file>META-INF/orm.xml</mapping-file>` trong `persistence.xml` làm cho mapping này trở thành một phần của PU.

Vì `orm.xml` có thể tự đăng ký một class là entity, ta không nhất thiết phải lặp lại `Customer` trong `<class>`. Quan trọng là mapping file được nạp đúng và chứa tên lớp đầy đủ chính xác.

### 4.3. Kết hợp annotation với XML

Một lớp có `@Entity` vẫn có thể được tùy chỉnh qua XML. Theo quy tắc metadata của JPA, khai báo XML có thể ghi đè một phần annotation tương ứng; tùy cấu hình, metadata XML có thể được dùng như nguồn đầy đủ thay cho annotation ở phạm vi thực thể hoặc persistence unit.

Các tùy chọn như `metadata-complete` nên chỉ dùng khi thật sự muốn **ngừng áp dụng annotation ánh xạ** cho phạm vi đó. Đây là khác biệt quan trọng so với trường hợp XML chỉ bổ sung hoặc điều chỉnh vài thuộc tính.

Cách tổ chức dễ bảo trì là thống nhất một quy ước, ví dụ:

1. Phần lớn lớp dùng annotation làm nguồn ánh xạ chính.
2. Những lớp không sửa được mã dùng XML trọn vẹn.
3. Các ngoại lệ ghi đè bằng XML phải được ghi rõ lý do và phạm vi.

Khi phát sinh vấn đề, kiểm tra cả annotation và `orm.xml` trước khi kết luận provider đang dùng tên bảng/cột mặc định.

### 4.4. Lưu ý về đường dẫn tệp

Trong `persistence.xml`, giá trị:

```xml
<mapping-file>META-INF/orm.xml</mapping-file>
```

là đường dẫn tài nguyên trong classpath/Persistence Unit phù hợp; đây không phải đường dẫn tuyệt đối đến `src/main/resources` trên máy lập trình. Sau khi build, hãy hình dung nó như tài nguyên có thể được JPA tìm thấy trong artifact đã đóng gói.

Nếu đặt XML ở vị trí khác, chẳng hạn `META-INF/mappings/customer-orm.xml`, phải cập nhật đường dẫn trong `<mapping-file>` theo tài nguyên thực tế. Không nên gõ đường dẫn Windows hoặc đường dẫn tương đối phụ thuộc thư mục chạy chương trình.

## 5. Khai báo nguồn dữ liệu cho Persistence Unit

### 5.1. Phân biệt kết nối và giao dịch

**Kết nối** trả lời câu hỏi “JPA lấy `Connection` từ đâu?”. **Giao dịch** trả lời “ai bắt đầu, commit, rollback và điều phối công việc?”. Chúng liên quan nhưng không phải cùng một cấu hình.

Có ba dạng thường gặp:

| Mô hình | Nguồn kết nối | Ai quản lý giao dịch? | Ngữ cảnh phù hợp |
|---|---|---|---|
| `RESOURCE_LOCAL` + thuộc tính JDBC | Driver, URL, user/password do PU cấu hình | Ứng dụng gọi `EntityTransaction` | Java SE, demo, công cụ nhỏ |
| `RESOURCE_LOCAL` + `non-jta-data-source` | `DataSource` đã được cung cấp/đăng ký | Ứng dụng điều khiển giao dịch cục bộ | Môi trường có sẵn connection pool, không cần JTA |
| `JTA` + `jta-data-source` | `DataSource` tích hợp JTA do môi trường cung cấp | Bộ quản lý giao dịch JTA/container | Jakarta EE hoặc runtime được thiết kế cho JTA |

Không nên trộn cách gọi `em.getTransaction()` của RESOURCE_LOCAL vào một entity manager đang tham gia giao dịch JTA.

### 5.2. Nguồn JDBC trực tiếp: `RESOURCE_LOCAL`

Ví dụ `shopPU` ở mục 2 dùng:

```xml
<persistence-unit name="shopPU" transaction-type="RESOURCE_LOCAL">
    <class>com.example.shop.domain.Product</class>
    <properties>
        <property name="jakarta.persistence.jdbc.driver"
                  value="org.h2.Driver"/>
        <property name="jakarta.persistence.jdbc.url"
                  value="jdbc:h2:mem:shop;DB_CLOSE_DELAY=-1"/>
        <property name="jakarta.persistence.jdbc.user"
                  value="sa"/>
        <property name="jakarta.persistence.jdbc.password"
                  value=""/>
    </properties>
</persistence-unit>
```

Đây là **đoạn minh họa tập trung vào nguồn dữ liệu**, không thay thế toàn bộ tệp `persistence.xml` của ví dụ đang dùng `Customer` từ XML.

Ưu điểm là cấu hình tự chứa, dễ hiểu trong Java SE. Hạn chế là ghi URL/tài khoản trong XML kém linh hoạt; việc pooling, bảo mật bí mật kết nối và quản lý nhiều môi trường thường cần cơ chế cấu hình riêng của ứng dụng/provider hoặc `DataSource`.

**Không đưa mật khẩu thật vào repository.** Môi trường triển khai nên cấp thông tin xác thực thông qua secret manager, biến môi trường hoặc cơ chế cấu hình bảo mật do runtime hỗ trợ. Thuộc tính JDBC trong tệp trên dùng H2 không mật khẩu chỉ để minh họa.

### 5.3. Nguồn dữ liệu `DataSource` không tham gia JTA

Khi runtime đã có `DataSource` không tham gia JTA được đăng ký, PU có thể dùng `<non-jta-data-source>`:

```xml
<persistence-unit name="shopLocalPU" transaction-type="RESOURCE_LOCAL">
    <class>com.example.shop.domain.Product</class>
    <non-jta-data-source>java:comp/env/jdbc/ShopLocalDS</non-jta-data-source>
</persistence-unit>
```

`java:comp/env/jdbc/ShopLocalDS` chỉ là **ví dụ tên JNDI**. Nó phải được khai báo/bind bằng cơ chế của môi trường chạy. Việc viết tên vào `persistence.xml` **không tự tạo connection pool, schema hay tài khoản database**.

Dùng `DataSource` giúp tách quản lý kết nối khỏi ánh xạ entity. Nếu runtime không cung cấp JNDI cho cấu hình trên, phải chọn cách bootstrap/cấu hình `DataSource` được runtime hoặc provider hỗ trợ.

### 5.4. `JTA` với `jta-data-source`

Trong môi trường Jakarta EE có JTA, một PU có thể khai báo:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence
    xmlns="https://jakarta.ee/xml/ns/persistence"
    version="3.1">

    <persistence-unit name="shopServerPU" transaction-type="JTA">
        <jta-data-source>java:app/jdbc/ShopDS</jta-data-source>

        <mapping-file>META-INF/orm.xml</mapping-file>
        <class>com.example.shop.domain.Product</class>
        <exclude-unlisted-classes>true</exclude-unlisted-classes>
    </persistence-unit>
</persistence>
```

`java:app/jdbc/ShopDS` cũng là tên minh họa; ứng dụng hoặc server phải đăng ký một `DataSource` đúng tên, đúng driver, URL, thông tin xác thực và thuộc tính pooling. Trong hệ Jakarta EE, runtime thường quản lý vòng đời EntityManager và giao dịch; mã nghiệp vụ có thể sử dụng:

```java
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import jakarta.transaction.Transactional;

@ApplicationScoped
public class ProductService {

    @PersistenceContext(unitName = "shopServerPU")
    private EntityManager em;

    @Transactional
    public void add(Product product) {
        em.persist(product);
    }
}
```

Trong ví dụ, `Product` cần được import từ package thực tế của dự án. `@PersistenceContext` yêu cầu môi trường có hỗ trợ tiêm persistence context, còn `@Transactional` yêu cầu tích hợp JTA phù hợp. Không thể lấy đoạn này chạy như Java SE thuần nếu không có container/framework cung cấp các dịch vụ tương ứng.

Với JTA, ứng dụng thường không trực tiếp gọi `EntityTransaction.begin()/commit()`; giao dịch được điều phối bởi transaction manager.

### 5.5. Nên chọn nguồn nào?

- **Bài tập Java SE độc lập:** `RESOURCE_LOCAL` với URL JDBC dễ khởi động và quan sát.
- **Ứng dụng server có connection pool:** sử dụng `DataSource` do runtime quản lý để tránh lặp cấu hình kết nối.
- **Jakarta EE với giao dịch quản lý bởi container:** chọn `JTA` và nguồn dữ liệu tham gia JTA.
- **Ứng dụng Spring Boot:** thường cấu hình `spring.datasource.*` và để Spring/JPA tạo hoặc quản lý `EntityManagerFactory`; không nhất thiết tự viết `persistence.xml`. Cách cấu hình ở đây minh họa **JPA chuẩn**, giúp hiểu những gì framework làm phía sau.

Cần phân biệt khả năng quản lý giao dịch cục bộ của một nguồn dữ liệu với khả năng thực sự tham gia vào giao dịch JTA; chỉ đổi tên thẻ XML không biến một JDBC source thành JTA-capable source.

## 6. Khởi tạo Persistence Unit và sử dụng EntityManager

### 6.1. Java SE: `Persistence.createEntityManagerFactory`

Đối với `shopPU` khai báo `RESOURCE_LOCAL`, ứng dụng có thể dùng:

```java
package com.example.shop;

import com.example.shop.domain.Product;
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;
import jakarta.persistence.Persistence;

import java.math.BigDecimal;

public class App {

    public static void main(String[] args) {
        EntityManagerFactory emf =
            Persistence.createEntityManagerFactory("shopPU");

        try {
            EntityManager em = emf.createEntityManager();
            try {
                EntityTransaction tx = em.getTransaction();

                try {
                    tx.begin();
                    em.persist(new Product(
                        "Mechanical keyboard",
                        new BigDecimal("890000.00")
                    ));
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
        } finally {
            emf.close();
        }
    }
}
```

Các điểm quan trọng:

1. Chuỗi `"shopPU"` phải khớp **chính xác** thuộc tính `name` của `persistence-unit`.
2. `EntityManagerFactory` gắn với metadata/config của PU, thường tạo một lần trong vòng đời ứng dụng thay vì mỗi truy vấn.
3. `EntityManager` không được dùng chia sẻ tùy tiện giữa nhiều thread; thường tạo/đóng theo một đơn vị công việc với Java SE, hoặc để container quản lý.
4. `RESOURCE_LOCAL` dùng `EntityTransaction` để bao quanh thao tác ghi. `commit()` kết thúc giao dịch; nếu có lỗi cần rollback khi giao dịch vẫn hoạt động.
5. `em.persist(...)` cần đối tượng của một entity được PU quản lý. Nếu JPA không nhận biết class đó, lỗi có thể xuất hiện lúc gọi `persist` hoặc khởi tạo metadata, tùy tình huống.

Ví dụ tạo EMF trong `main` để minh họa; ứng dụng thực tế nên quản lý vòng đời EMF ở lớp khởi động/tắt ứng dụng. Một PU và một cơ sở dữ liệu không ngăn việc tạo nhiều `EntityManager` khác nhau.

### 6.2. Một PU không phải một persistence context duy nhất

Hai EntityManager cùng sinh ra từ `shopPU` dùng **cùng tập ánh xạ và nguồn dữ liệu cấu hình**, nhưng mỗi EntityManager thường có **persistence context riêng**. Entity được quản lý trong context này không tự trở thành managed trong context khác.

Điều đó giải thích tại sao mã đọc một entity bằng EntityManager A, đóng A rồi thao tác tiếp ở B phải hiểu trạng thái `detached` và cách dùng `merge` hoặc tải lại đúng cách. Không nên suy luận rằng “cùng PU” đồng nghĩa với “mọi đối tượng Java đang được JPA theo dõi như nhau”.

### 6.3. Nhiều Persistence Unit trong một ứng dụng

Một `persistence.xml` có thể chứa nhiều `<persistence-unit>`:

```xml
<persistence-unit name="shopPU" transaction-type="RESOURCE_LOCAL">
    <!-- Ánh xạ và nguồn dữ liệu của nghiệp vụ bán hàng -->
</persistence-unit>

<persistence-unit name="auditPU" transaction-type="RESOURCE_LOCAL">
    <!-- Ánh xạ và nguồn dữ liệu của nhật ký -->
</persistence-unit>
```

Hai đoạn trên minh họa cấu trúc thành phần; để chạy phải hoàn thiện các thiết lập cần thiết trong tệp `persistence.xml` hợp lệ.

Khi gọi `Persistence.createEntityManagerFactory("auditPU")`, JPA chọn cấu hình `auditPU`. Hai PU có thể truy cập cùng database hoặc database khác nhau, nhưng **không tự chia sẻ persistence context, metadata của entity, hay một transaction phân tán**. Cần thiết kế rõ ranh giới nếu nghiệp vụ ghi đồng thời vào nhiều nguồn.

## 7. Nguyên tắc tổ chức cấu hình trong dự án thực tế

### 7.1. Làm rõ nguồn sự thật của metadata

Một entity có thể bị khai báo ở nhiều chỗ: annotation trong class, `<class>` trong `persistence.xml`, hoặc `<entity>` trong `orm.xml`. Đó là các tầng thông tin khác nhau. Để hạn chế khó hiểu:

- Đăng ký tường minh các lớp cần quản lý khi việc quét classpath không chắc chắn.
- Đặt tên bảng, cột và quan hệ có chủ đích; kiểm tra SQL và schema thực tế.
- Khi dùng XML bổ sung cho annotation, ghi rõ thuộc tính bị override và tác động.
- Không đưa entity vào nhiều PU chỉ vì chúng dùng chung tên package; cân nhắc vòng đời và giao dịch của từng PU.

### 7.2. Tách các môi trường dev, test và production

Một ví dụ cấu hình thường thay đổi theo môi trường:

| Phần | Development/test | Production |
|---|---|---|
| Database | H2 tạm, container thử nghiệm hoặc database cô lập | Database đã vận hành, có backup |
| Schema | Có thể tạo lại từ đầu trong bài tập | Migration được kiểm soát; tránh tạo/xóa bảng tự động |
| Credentials | Dữ liệu thử nghiệm | Secret store hoặc cấu hình bảo mật của runtime |
| Connection pooling | Đơn giản hoặc do framework tạo | Cấu hình giới hạn phù hợp tải thực tế |
| SQL logging | Có thể bật để học và gỡ lỗi | Có kiểm soát dữ liệu nhạy cảm, độ ồn và chi phí |
| Transaction | Có thể thử RESOURCE_LOCAL | Theo kiến trúc runtime: RESOURCE_LOCAL hoặc JTA phù hợp |

`persistence.xml` định nghĩa metadata và cách cấu hình PU; không nên biến nó thành nơi lưu mật khẩu production hay cơ chế triển khai schema tùy tiện.

### 7.3. Chọn version tương thích

JPA đã chuyển các API từ `javax.persistence.*` sang `jakarta.persistence.*` ở các thế hệ Jakarta Persistence mới. Vì vậy cần đồng bộ:

- Import trong mã Java (`jakarta.persistence.Entity`, `jakarta.persistence.Persistence`, ...).
- Namespace/schema của `persistence.xml` và `orm.xml`.
- Phiên bản Jakarta Persistence API và ORM provider.
- Runtime/Jakarta EE hoặc framework tích hợp nếu dùng container.

Khi nâng cấp một dự án cũ, đổi một vài import mà bỏ qua phiên bản provider hoặc XML có thể làm bootstrap thất bại. Cấu hình thư viện và driver là trách nhiệm của hệ build/runtime; `persistence.xml` không thay thế dependency management.

## 8. Lỗi thường gặp và cách nhận biết

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| `No Persistence provider for EntityManager named shopPU` | Không tìm thấy `persistence.xml`, tên PU sai, provider không có trên classpath hoặc cấu hình không hợp lệ | Kiểm tra đường dẫn đóng gói `META-INF/persistence.xml`, tên và thư viện runtime |
| `Not a managed type` / `Unknown entity` | Lớp chưa được đưa vào PU hoặc thiếu metadata entity hợp lệ | Kiểm tra `@Entity`, `<class>`, mapping XML và hành vi quét |
| Không tìm thấy `META-INF/orm.xml` | `<mapping-file>` trỏ sai đường dẫn hoặc tệp không vào artifact | Kiểm tra cấu trúc `src/main/resources` và nội dung sau build |
| Lỗi xác thực/kết nối SQL | Sai driver, URL, tài khoản, JNDI name; nguồn dữ liệu chưa được đăng ký | Kiểm tra cấu hình DataSource/JDBC và khả năng kết nối DB |
| `TransactionRequiredException` khi ghi | Chưa có giao dịch phù hợp | Thiết lập transaction cục bộ hoặc JTA đúng mô hình |
| Lỗi ánh xạ bảng/cột | Annotation, XML và schema không khớp; chiến lược đặt tên ngoài dự kiến | Đối chiếu mapping, SQL sinh ra và schema thật |
| Ứng dụng không chạy sau nâng cấp JPA | Trộn `javax.*` và `jakarta.*` hoặc version provider/XML không tương thích | Căn chỉnh bộ thư viện và namespace/schema |
| Bảng bị tạo lại mất dữ liệu | Bật schema generation không phù hợp | Tắt tác vụ tạo/xóa tự động trong môi trường có dữ liệu cần giữ |

Khi gặp lỗi, cần biết nó xuất hiện **lúc tạo EntityManagerFactory, lúc tạo kết nối, lúc bắt đầu giao dịch, hay lúc xử lý entity**. Vị trí lỗi thường cho biết nên kiểm tra phần metadata, nguồn dữ liệu hoặc transaction trước.

## 9. Bài thực hành: cấu hình hai kiểu entity trong một PU

Mục tiêu là hiểu quan hệ giữa các phần chứ không chỉ sao chép cấu hình:

1. Tạo `Product` có `@Entity` và `@Id`; đăng ký bằng `<class>` trong `shopPU`.
2. Tạo `Customer` không có `@Entity` nhưng được khai báo bằng `<entity>` trong `META-INF/orm.xml`; đăng ký tệp bằng `<mapping-file>`.
3. Thiết lập nguồn H2 JDBC và `transaction-type="RESOURCE_LOCAL"`, cài đúng provider/driver cần thiết.
4. Gọi `Persistence.createEntityManagerFactory("shopPU")`, tạo EntityManager, mở transaction và lưu một `Product`.
5. Lưu một `Customer` bằng EntityManager từ cùng PU. Sau đó đọc lại từng entity bằng `find` với ID nhận được sau khi lưu.
6. Thử đổi tên `shopPU` ở nơi bootstrap mà không đổi trong XML để quan sát lỗi nhận diện PU. Khôi phục và thử bỏ `<mapping-file>` để thấy khác biệt khi class `Customer` không còn metadata.

Trong quá trình thực hành, thử giải thích ba câu hỏi:

- Vì sao `Product` cần metadata entity và việc đăng ký trong PU, còn `Customer` vẫn có thể được quản lý dù không có `@Entity`?
- Vì sao `<jta-data-source>` không thể thay bằng một tên JNDI tùy ý nếu runtime không đăng ký nguồn dữ liệu tương ứng?
- Vì sao hai EntityManager tạo từ cùng `shopPU` không tự chia sẻ một persistence context?

## 10. Tổng kết

Một Persistence Unit là **hợp đồng cấu hình giữa ứng dụng, JPA provider, bộ metadata ánh xạ và nguồn dữ liệu**. Khi khai báo, hãy xác định rõ:

- **Entity nào** được quản lý: bằng annotation `@Entity`, khai báo `<class>` hoặc metadata XML.
- **Ánh xạ nào** được áp dụng: annotation và/hoặc `orm.xml`, được tìm thấy thông qua đường dẫn tài nguyên hợp lệ.
- **Kết nối và giao dịch nào** được sử dụng: JDBC trực tiếp, `non-jta-data-source` hay `jta-data-source`; `RESOURCE_LOCAL` hay `JTA`.
- **Ai quản lý vòng đời**: EntityManagerFactory, EntityManager và transaction trong Java SE hoặc thông qua môi trường container.

Hiểu đúng các ranh giới này giúp tránh ba nhóm lỗi phổ biến: **entity không được nhận diện, metadata không được nạp và không thể truy cập database/giao dịch**.
