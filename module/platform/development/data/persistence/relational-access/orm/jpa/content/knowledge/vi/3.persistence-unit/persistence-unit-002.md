# Cấu trúc và vai trò của `persistence.xml` trong JPA

`persistence.xml` là tệp cấu hình chuẩn của **Jakarta Persistence (JPA)**, dùng để khai báo một hoặc nhiều **persistence unit**: tập entity, mapping và cấu hình cần thiết để JPA tạo `EntityManagerFactory` và làm việc với cơ sở dữ liệu quan hệ. Trong một unit, ứng dụng có thể xác định provider JPA, nguồn kết nối, kiểu transaction, phạm vi managed classes cùng các tùy chọn cache, validation và tạo schema.

Tài liệu giải thích cấu trúc và cách sử dụng `persistence.xml` trong ngữ cảnh nền tảng ORM/JPA. Các ví dụ sử dụng **Jakarta Persistence 3.1** (`jakarta.persistence.*`), có ghi rõ sự khác biệt với JPA `javax.persistence.*` đời cũ và với cơ chế tự cấu hình của Spring Boot.

> **Phân biệt:** `persistence.xml` là bản khai báo cấu hình persistence unit. Nó không chứa logic nghiệp vụ, không trực tiếp thực thi SQL và không thay thế database transaction. `EntityManagerFactory` được bootstrap theo unit; `EntityManager` mới là API làm việc với entity trong một persistence context.

## 1. Vai trò của `persistence.xml` trong luồng ORM

Giả sử chương trình có các entity `Customer`, `Product` và `Order`. JPA cần trả lời:

1. **Những lớp nào thuộc mô hình dữ liệu này?** Chúng được liệt kê tường minh, ánh xạ bằng XML hay tự phát hiện trong persistence-unit root?
2. **Ai triển khai đặc tả JPA?** Hibernate, EclipseLink hoặc provider khác sẽ chịu trách nhiệm mapping, dirty checking và tạo SQL.
3. **Kết nối với database bằng gì?** JDBC trực tiếp hay một `DataSource` do môi trường quản lý?
4. **Ai quản lý giao dịch?** Ứng dụng điều khiển local transaction hay transaction manager theo JTA?
5. **Các chính sách bổ sung là gì?** Validation, shared cache, schema generation, logging, batching và property của provider.

`persistence.xml` tổ chức những quyết định này thành các **persistence unit có tên**, để ứng dụng chọn bằng API hoặc injection.

~~~mermaid
flowchart TD
    XML["META-INF/persistence.xml"] --> PU["persistence-unit: catalogPU"]
    PU --> Provider["JPA Provider"]
    PU --> Classes["Entity + mapping XML"]
    PU --> Source["DataSource / JDBC"]
    PU --> Tx["JTA hoặc RESOURCE_LOCAL"]
    PU --> Props["Properties + policies"]
    Provider --> EMF["EntityManagerFactory"]
    Classes --> EMF
    Source --> EMF
    Tx --> EMF
    Props --> EMF
    EMF --> EM["EntityManager"]
    EM --> DB[("Relational Database")]
~~~

JPA là **đặc tả API và ngữ nghĩa persistence**, còn Hibernate/EclipseLink là triển khai. Dù XML nêu tên provider, thư viện tương ứng vẫn phải có trên runtime classpath hoặc được container cung cấp.

## 2. Tệp nằm ở đâu trong dự án?

Vị trí tiêu chuẩn là **`META-INF/persistence.xml` trong persistence archive**. Với cấu trúc Maven/Gradle thông thường:

~~~text
catalog-app/
├── src/
│   ├── main/
│   │   ├── java/
│   │   │   └── com/example/catalog/
│   │   │       ├── Product.java
│   │   │       └── Main.java
│   │   └── resources/
│   │       └── META-INF/
│   │           └── persistence.xml
│   └── test/
│       └── resources/
│           └── META-INF/
│               └── persistence.xml  # nếu muốn cấu hình test riêng
└── build.gradle / pom.xml
~~~

Khi build, các tệp trong `src/main/resources` thường trở thành:

~~~text
target/classes/META-INF/persistence.xml       # Maven
build/resources/main/META-INF/persistence.xml  # Gradle
~~~

Trong JAR, tệp thường được đóng gói ở `META-INF/persistence.xml`. Trong WAR, có thể đặt ở `WEB-INF/classes/META-INF/persistence.xml` hoặc trong một JAR thích hợp thuộc `WEB-INF/lib`. Với EAR/Jakarta EE, khái niệm **persistence-unit root** và phạm vi các lớp được xem xét còn phụ thuộc loại archive cùng quy tắc deployment.

Nếu đặt XML tại `src/main/java/persistence.xml`, `config/persistence.xml` hoặc thư mục gốc dự án mà không có bước đóng gói thành `META-INF/persistence.xml`, bootstrap chuẩn thường **không tìm thấy** persistence unit.

Một `persistence.xml` có thể khai báo nhiều unit. Một ứng dụng cũng có thể mang nhiều persistence archive; khi đó nên đặt tên unit rõ ràng và tránh trùng tên gây nhập nhằng khi bootstrap.

## 3. Cấu trúc tổng thể và ví dụ XML

Ví dụ Jakarta Persistence 3.1 với một unit sử dụng Hibernate, H2 và resource-local transaction:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence
    xmlns="https://jakarta.ee/xml/ns/persistence"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        https://jakarta.ee/xml/ns/persistence
        https://jakarta.ee/xml/ns/persistence/persistence_3_1.xsd"
    version="3.1">

    <persistence-unit name="catalogPU" transaction-type="RESOURCE_LOCAL">
        <description>Catalog domain persistence unit</description>
        <provider>org.hibernate.jpa.HibernatePersistenceProvider</provider>

        <class>com.example.catalog.Product</class>
        <class>com.example.catalog.Category</class>
        <exclude-unlisted-classes>true</exclude-unlisted-classes>

        <properties>
            <property name="jakarta.persistence.jdbc.driver"
                      value="org.h2.Driver"/>
            <property name="jakarta.persistence.jdbc.url"
                      value="jdbc:h2:mem:catalog;DB_CLOSE_DELAY=-1"/>
            <property name="jakarta.persistence.jdbc.user" value="sa"/>
            <property name="jakarta.persistence.jdbc.password" value=""/>
            <property name="jakarta.persistence.schema-generation.database.action"
                      value="drop-and-create"/>
            <property name="hibernate.show_sql" value="true"/>
        </properties>
    </persistence-unit>
</persistence>
~~~

Đây là **cấu hình học tập**, yêu cầu dependency Hibernate và H2 cùng các class đã khai báo. `drop-and-create` có thể hủy dữ liệu/schema hiện có và chỉ phù hợp môi trường demo hoặc test chủ động tạo lại.

### Ba lớp cấu trúc

| Thành phần | Mục đích |
|---|---|
| `<persistence>` | Phần tử gốc, chứa namespace, schema, version và các persistence unit. |
| `<persistence-unit name="...">` | Một đơn vị cấu hình JPA có định danh riêng. |
| Các thẻ con trong unit | Nêu provider, DataSource, mapping, classes, cache, validation và các property. |

### Namespace, schema và version

- `xmlns="https://jakarta.ee/xml/ns/persistence"`: namespace của tài liệu Jakarta Persistence.
- `xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"`: cho phép khai báo schema location.
- `xsi:schemaLocation`: gắn namespace với địa chỉ XSD tương ứng để XML parser/IDE có thể kiểm tra cấu trúc.
- `version="3.1"`: phiên bản schema XML được dùng; cần đồng bộ với runtime và namespace.

Version trong XML là phiên bản đặc tả/schema JPA, **không phải** phiên bản của database hay Hibernate. Đừng ghép namespace Jakarta 3.x với XSD kiểu `persistence_2_2.xsd` thuộc dòng javax.

Do XSD có quy định trình tự phần tử, các thẻ nên xuất hiện theo thứ tự chuẩn khi có mặt:

~~~text
persistence-unit
  ├── description
  ├── provider
  ├── jta-data-source
  ├── non-jta-data-source
  ├── mapping-file       (lặp lại được)
  ├── jar-file           (lặp lại được)
  ├── class              (lặp lại được)
  ├── exclude-unlisted-classes
  ├── shared-cache-mode
  ├── validation-mode
  └── properties
        └── property name="..." value="..." (lặp lại được)
~~~

Không cần khai báo mọi phần tử; nhưng **thứ tự** các phần tử đã khai báo phải tương thích XSD. Sai thứ tự có thể gây lỗi parse hoặc validation ngay lúc tạo factory.

## 4. Ý nghĩa các phần tử của `persistence-unit`

| Element / attribute | Ý nghĩa | Ghi chú |
|---|---|---|
| `name` | Tên định danh persistence unit, bắt buộc | Dùng trong `Persistence.createEntityManagerFactory` hoặc `unitName` khi injection. |
| `transaction-type` | Chọn mô hình transaction | `JTA` hoặc `RESOURCE_LOCAL`; mặc định phụ thuộc môi trường. |
| `<description>` | Mô tả cho người đọc | Không ảnh hưởng entity mapping hay SQL. |
| `<provider>` | Provider triển khai JPA | Có thể được chọn bằng cơ chế bootstrap nếu bỏ trống. |
| `<jta-data-source>` | Nguồn dữ liệu được quản lý cho JTA | Thường là JNDI name được cung cấp bởi container. |
| `<non-jta-data-source>` | DataSource sử dụng ngoài JTA | Dùng cho local hoặc các hoạt động không theo JTA tùy runtime. |
| `<mapping-file>` | Tham chiếu metadata mapping XML | Ví dụ `META-INF/orm.xml`. |
| `<jar-file>` | Bổ sung archive liên quan managed classes/mapping | Cách phân giải đường dẫn phụ thuộc môi trường đóng gói. |
| `<class>` | Khai báo managed class tường minh | Giá trị là fully-qualified class name. |
| `<exclude-unlisted-classes>` | Điều khiển tự khám phá lớp chưa liệt kê trong unit root | `true` giới hạn scanning unlisted classes. |
| `<shared-cache-mode>` | Chính sách shared/second-level cache theo chuẩn | Ví dụ `NONE`, `ALL`, `ENABLE_SELECTIVE`. |
| `<validation-mode>` | Tích hợp Bean Validation ở lifecycle callbacks | `AUTO`, `CALLBACK` hoặc `NONE`. |
| `<properties>` | Cấu hình key/value | Chứa property JPA chuẩn và mở rộng của provider. |

Một class trong `<class>` có thể là entity, embeddable, mapped superclass hoặc converter phù hợp với mô hình persistence. Tuy nhiên khai báo class không tự biến một POJO bình thường thành entity: lớp vẫn cần mapping hợp lệ bằng annotation/XML.

## 5. Persistence unit và vòng đời JPA runtime

**Persistence unit** định nghĩa phạm vi metadata và cấu hình được một `EntityManagerFactory` sử dụng. Sau khi bootstrap, factory có thể tạo nhiều `EntityManager`; mỗi `EntityManager` làm việc với persistence context theo vòng đời ứng dụng hoặc container quy định.

~~~mermaid
flowchart LR
    PU["persistence-unit catalogPU"] --> EMF["EntityManagerFactory"]
    EMF --> E1["EntityManager 1"]
    EMF --> E2["EntityManager 2"]
    E1 --> DB[("Database")]
    E2 --> DB
~~~

`EntityManagerFactory` thường khởi tạo tốn chi phí và nên được dùng lại trong suốt vòng đời ứng dụng, sau đó đóng khi ngừng sử dụng. `EntityManager` thường tồn tại theo một đơn vị công việc, **không được xem là đối tượng thread-safe** để chia sẻ tùy ý giữa các thread. Trong Jakarta EE/Spring, việc inject proxy hoặc context do runtime quản lý có quy tắc vòng đời riêng.

Trong Java SE, tên unit được truyền trực tiếp:

~~~java
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.Persistence;

EntityManagerFactory emf =
    Persistence.createEntityManagerFactory("catalogPU");
~~~

Trong môi trường hỗ trợ injection, có thể chọn bằng annotation:

~~~java
@PersistenceContext(unitName = "catalogPU")
private EntityManager entityManager;

@PersistenceUnit(unitName = "catalogPU")
private EntityManagerFactory entityManagerFactory;
~~~

`@PersistenceContext` yêu cầu `EntityManager` do môi trường quản lý; `@PersistenceUnit` yêu cầu factory. Cả hai dùng **tên persistence unit**, không phải tên class Java hay tên bảng SQL.

### Nhiều persistence unit trong một ứng dụng

~~~xml
<persistence
    xmlns="https://jakarta.ee/xml/ns/persistence"
    version="3.1">
    <persistence-unit name="catalogPU" transaction-type="RESOURCE_LOCAL">
        <class>com.example.catalog.Product</class>
        <exclude-unlisted-classes>true</exclude-unlisted-classes>
        <properties>
            <property name="jakarta.persistence.jdbc.driver" value="org.h2.Driver"/>
            <property name="jakarta.persistence.jdbc.url"
                      value="jdbc:h2:mem:catalog"/>
        </properties>
    </persistence-unit>

    <persistence-unit name="reportPU" transaction-type="RESOURCE_LOCAL">
        <class>com.example.report.ReportSnapshot</class>
        <exclude-unlisted-classes>true</exclude-unlisted-classes>
        <properties>
            <property name="jakarta.persistence.jdbc.driver" value="org.h2.Driver"/>
            <property name="jakarta.persistence.jdbc.url"
                      value="jdbc:h2:mem:reports"/>
        </properties>
    </persistence-unit>
</persistence>
~~~

Đoạn trên thể hiện hai unit có tên, class và JDBC URL khác nhau; các dependency, class và phần cấu hình còn thiếu phải được bổ sung khi triển khai thật. Một unit không tự động quản lý entity chỉ khai báo ở unit khác. Có thể có nhiều unit cùng truy cập một database, hoặc mỗi unit truy cập database khác nhau. **Khai báo nhiều unit không tự tạo distributed transaction** giữa các database.

## 6. Ví dụ hoàn chỉnh: Java SE, Hibernate và H2

Ví dụ này cho thấy XML được load khi bootstrap và cách một entity được persist trong resource-local transaction. Để chạy cần các thư viện tương thích: Jakarta Persistence API, Hibernate ORM 6.x, JDBC driver H2 và logging phù hợp; dùng dependency management/BOM của dự án để chọn phiên bản tương thích.

### 6.1. Entity `Product`

~~~java
// src/main/java/com/example/catalog/Product.java
package com.example.catalog;

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

    @Column(nullable = false)
    private String name;

    protected Product() {} // Constructor không tham số theo yêu cầu JPA

    public Product(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

### 6.2. Cấu hình `META-INF/persistence.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence
    xmlns="https://jakarta.ee/xml/ns/persistence"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        https://jakarta.ee/xml/ns/persistence
        https://jakarta.ee/xml/ns/persistence/persistence_3_1.xsd"
    version="3.1">

    <persistence-unit name="catalogPU" transaction-type="RESOURCE_LOCAL">
        <provider>org.hibernate.jpa.HibernatePersistenceProvider</provider>
        <class>com.example.catalog.Product</class>
        <exclude-unlisted-classes>true</exclude-unlisted-classes>
        <properties>
            <property name="jakarta.persistence.jdbc.driver" value="org.h2.Driver"/>
            <property name="jakarta.persistence.jdbc.url"
                      value="jdbc:h2:mem:catalog;DB_CLOSE_DELAY=-1"/>
            <property name="jakarta.persistence.jdbc.user" value="sa"/>
            <property name="jakarta.persistence.jdbc.password" value=""/>
            <property name="jakarta.persistence.schema-generation.database.action"
                      value="drop-and-create"/>
            <property name="hibernate.show_sql" value="true"/>
            <property name="hibernate.format_sql" value="true"/>
        </properties>
    </persistence-unit>
</persistence>
~~~

Vì `<exclude-unlisted-classes>true</exclude-unlisted-classes>`, chỉ class đã chỉ rõ và các class/mapping được khai báo hợp lệ khác nằm trong unit được xét theo quy tắc tương ứng. `jdbc:h2:mem:catalog` tạo database trong bộ nhớ. `DB_CLOSE_DELAY=-1` giúp giữ database còn tồn tại trong vòng đời JVM demo sau khi các connection đóng; dữ liệu không phải persistence disk lâu dài. `drop-and-create` phù hợp bài demo, có thể phá hủy dữ liệu trong môi trường khác.

### 6.3. Bootstrap và thực hiện transaction

~~~java
// src/main/java/com/example/catalog/Main.java
package com.example.catalog;

import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;
import jakarta.persistence.Persistence;

public class Main {
    public static void main(String[] args) {
        EntityManagerFactory emf =
            Persistence.createEntityManagerFactory("catalogPU");

        try {
            EntityManager em = emf.createEntityManager();
            try {
                EntityTransaction tx = em.getTransaction();
                try {
                    tx.begin();
                    em.persist(new Product("Notebook"));
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

            EntityManager reader = emf.createEntityManager();
            try {
                long count = reader.createQuery(
                    "select count(p) from Product p", Long.class
                ).getSingleResult();
                System.out.println("Product count = " + count);
            } finally {
                reader.close();
            }
        } finally {
            emf.close();
        }
    }
}
~~~

Diễn biến theo thứ tự:

1. `Persistence.createEntityManagerFactory("catalogPU")` yêu cầu provider tìm unit tên `catalogPU`, đọc cấu hình và chuẩn bị metadata/kết nối.
2. `emf.createEntityManager()` tạo một `EntityManager` quản lý persistence context.
3. `tx.begin()` bắt đầu resource-local transaction.
4. `em.persist(...)` chuyển entity mới vào trạng thái managed; provider đưa `INSERT` vào luồng đồng bộ.
5. `tx.commit()` yêu cầu flush nếu cần và commit transaction. Với khóa `IDENTITY`, `INSERT` có thể diễn ra sớm hơn để lấy ID.
6. `reader` là `EntityManager` khác dùng query để kiểm tra bản ghi sau commit, dự kiến in `Product count = 1`.
7. `em.close()` và `emf.close()` giải phóng tài nguyên tương ứng.

`persistence.xml` chủ yếu liên quan đến **lúc tạo persistence unit/factory**. Những thay đổi field trong entity và dirty checking diễn ra sau đó qua `EntityManager`; tệp XML không được đọc lại cho từng lệnh `persist`.

## 7. RESOURCE_LOCAL và JTA: chọn đúng transaction type

Hai giá trị chuẩn của thuộc tính `transaction-type`:

| Khía cạnh | `RESOURCE_LOCAL` | `JTA` |
|---|---|---|
| Ai quản lý transaction? | Ứng dụng hoặc framework điều phối local transaction | JTA transaction manager/container |
| API điển hình | `em.getTransaction().begin()/commit()/rollback()` | Transaction do container, `UserTransaction` hoặc cơ chế framework tương ứng điều phối |
| DataSource thường gặp | JDBC trực tiếp hoặc non-JTA DataSource | JTA DataSource trong container |
| Môi trường thường gặp | Java SE, app tự quản lý giao dịch | Jakarta EE/container có tích hợp JTA |
| Điều cần tránh | Quên `begin` hoặc `commit` | Dùng `EntityTransaction` trực tiếp trên JTA EntityManager |

### Ví dụ persistence unit trong Jakarta EE

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence
    xmlns="https://jakarta.ee/xml/ns/persistence"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        https://jakarta.ee/xml/ns/persistence
        https://jakarta.ee/xml/ns/persistence/persistence_3_1.xsd"
    version="3.1">

    <persistence-unit name="ordersPU" transaction-type="JTA">
        <jta-data-source>java:app/jdbc/OrdersDS</jta-data-source>
        <class>com.example.orders.Order</class>
        <exclude-unlisted-classes>true</exclude-unlisted-classes>
        <properties>
            <property name="jakarta.persistence.schema-generation.database.action"
                      value="none"/>
        </properties>
    </persistence-unit>
</persistence>
~~~

`java:app/jdbc/OrdersDS` là một **tên DataSource minh họa**; server/ứng dụng phải thật sự khai báo nguồn dữ liệu này. `<jta-data-source>` chứa tên nguồn dữ liệu, không chứa trực tiếp JDBC URL, user hay password.

Code Jakarta Enterprise Beans minh họa container quản lý entity manager và transaction:

~~~java
import jakarta.ejb.Stateless;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;

@Stateless
public class OrderService {
    @PersistenceContext(unitName = "ordersPU")
    private EntityManager entityManager;

    public void createOrder(Order order) {
        entityManager.persist(order);
        // Container điều phối transaction cho lời gọi nghiệp vụ.
    }
}
~~~

`Order` giả định là entity đã khai báo hợp lệ trong unit. `@Stateless` chỉ là một ví dụ Jakarta EE; cơ chế Jakarta Transactions hoặc CDI trong môi trường khác có cách cấu hình tương ứng.

JTA unit đôi khi cũng có `<non-jta-data-source>` cho hoạt động ngoài giao dịch JTA, nên không nên diễn giải đơn giản rằng hai thẻ DataSource luôn loại trừ lẫn nhau. Quan trọng nhất là nguồn dữ liệu và transaction manager phải tương thích với môi trường triển khai.

Nếu `transaction-type` bị bỏ qua, mặc định thường là **JTA trong Jakarta EE** và **RESOURCE_LOCAL trong Java SE**. Khai báo tường minh khi cần tính dễ đọc và tránh hành vi khác nhau giữa các môi trường.

## 8. Liệt kê entity, scanning và tệp mapping

### Khai báo class tường minh

~~~xml
<class>com.example.catalog.Product</class>
<class>com.example.catalog.Category</class>
<class>com.example.catalog.MoneyConverter</class>
<exclude-unlisted-classes>true</exclude-unlisted-classes>
~~~

`<class>` nhận **fully qualified class name**, không phải đường dẫn file. Có thể khai báo entity, mapped superclass, embeddable hoặc converter được mapping hợp lệ. Đây là cách dễ kiểm soát khi chạy Java SE, khi deployment nhiều module hoặc khi muốn hạn chế lớp được auto-discover.

### Scanning các class chưa được liệt kê

~~~xml
<persistence-unit name="autoPU">
    <exclude-unlisted-classes>false</exclude-unlisted-classes>
</persistence-unit>
~~~

Khi được phép tìm lớp chưa liệt kê, provider/container xét các class đủ điều kiện trong **persistence-unit root** theo quy tắc triển khai. Điều này **không** có nghĩa JPA tự quét mọi JAR trên classpath, và cũng không có nghĩa nó dùng quy tắc `@EntityScan` của Spring. Với Java SE, việc liệt kê rõ class hoặc cấu hình discovery được hỗ trợ thường làm chương trình ổn định hơn khi đóng gói/chuyển provider.

`exclude-unlisted-classes=true` ảnh hưởng nhóm class được tìm tự động. Nó không xóa các class mà unit khai báo tường minh qua `<class>` và cũng không vô hiệu hóa mapping XML đã cấu hình hợp lệ.

### `<mapping-file>` và `orm.xml`

~~~xml
<persistence-unit name="catalogPU">
    <mapping-file>META-INF/orm.xml</mapping-file>
    <class>com.example.catalog.Product</class>
    <exclude-unlisted-classes>true</exclude-unlisted-classes>
</persistence-unit>
~~~

`persistence.xml` chỉ ra **unit nào sử dụng tệp metadata**; còn `orm.xml` mô tả ánh xạ entity/bảng/cột/quan hệ, named query và các chi tiết mapping tương ứng. Annotation và XML mapping có thể phối hợp; mức độ XML bổ sung hoặc ghi đè annotation phụ thuộc quy tắc mapping và các thiết lập như `metadata-complete`.

Trích đoạn ví dụ về vai trò của `orm.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<entity-mappings
    xmlns="https://jakarta.ee/xml/ns/persistence/orm"
    version="3.1">
    <entity class="com.example.catalog.Product">
        <table name="products"/>
    </entity>
</entity-mappings>
~~~

Đây chỉ là ví dụ về tên thẻ; để dùng thực tế, class, schema, ID mapping và namespace/version của tệp `orm.xml` phải tương thích nhau. **Không chép `<entity>` trực tiếp vào `persistence.xml`**: chúng là hai tài liệu có nhiệm vụ khác nhau.

### `<jar-file>` bổ sung những gì?

`<jar-file>` dùng để tham chiếu archive bổ sung cần xét khi xây dựng managed classes/mapping. Cách diễn giải đường dẫn có thể phụ thuộc cấu trúc JAR/WAR/EAR, vị trí persistence-unit root và hỗ trợ runtime. Với dự án nhiều module, nên xác nhận cách packaging thực tế và cơ chế provider/container xử lý các JAR, thay vì đoán một đường dẫn tương đối tùy ý.

## 9. `<properties>` và ranh giới giữa chuẩn JPA với provider

Mỗi phần tử `<property>` là một cặp `name`/`value`:

~~~xml
<properties>
    <property name="jakarta.persistence.jdbc.url"
              value="jdbc:postgresql://localhost:5432/catalog"/>
    <property name="hibernate.show_sql" value="true"/>
</properties>
~~~

| Nhóm | Property | Chức năng |
|---|---|---|
| JDBC theo JPA | `jakarta.persistence.jdbc.driver` | Tên driver JDBC. |
| JDBC theo JPA | `jakarta.persistence.jdbc.url` | URL database. |
| JDBC theo JPA | `jakarta.persistence.jdbc.user` và `jakarta.persistence.jdbc.password` | Thông tin xác thực khi dùng JDBC connection. |
| Schema JPA | `jakarta.persistence.schema-generation.database.action` | Hành động schema: `none`, `create`, `drop-and-create`, `drop`. |
| DDL script JPA | `jakarta.persistence.schema-generation.scripts.action` | Điều khiển sinh các script schema, không đồng nghĩa áp dụng schema vào DB. |
| Validation JPA | `jakarta.persistence.validation.mode` | Thiết lập chế độ Bean Validation. |
| Shared cache JPA | `jakarta.persistence.sharedCache.mode` | Chính sách dùng shared cache. |
| Hibernate | `hibernate.show_sql`, `hibernate.format_sql` | Hiển thị và định dạng SQL khi phát triển. |
| Hibernate | `hibernate.hbm2ddl.auto` | Chiến lược schema riêng Hibernate, ví dụ `validate` hoặc `update`. |
| Hibernate | `hibernate.jdbc.batch_size` | Batch JDBC khi mapping/driver cho phép. |

Tiền tố `jakarta.persistence.*` thường chỉ nhóm property chuẩn của Jakarta Persistence. Tiền tố `hibernate.*` chỉ cấu hình **riêng Hibernate**; chuyển provider sang EclipseLink không bảo đảm các property này còn hiệu lực. Một số thuộc tính chuẩn chỉ có ý nghĩa với một cách bootstrap nhất định: chẳng hạn JDBC connection properties không nhất thiết là nguồn kết nối chính của một persistence unit sử dụng JTA DataSource do container cấp.

### Cấp cấu hình nhạy cảm qua runtime

Không nên commit mật khẩu production vào XML. Java SE có overload bootstrap nhận `Map`:

~~~java
Map<String, Object> overrides = new HashMap<>();
overrides.put("jakarta.persistence.jdbc.url", jdbcUrl);
overrides.put("jakarta.persistence.jdbc.user", jdbcUser);
overrides.put("jakarta.persistence.jdbc.password", jdbcPassword);

EntityManagerFactory emf =
    Persistence.createEntityManagerFactory("catalogPU", overrides);
~~~

Trong đó `jdbcUrl`, `jdbcUser` và `jdbcPassword` được lấy từ cấu hình runtime hoặc secret store. Khi dùng container hoặc Spring, một `DataSource` được quản lý tập trung thường thích hợp hơn là để từng unit tự chứa mật khẩu. Quy tắc ưu tiên khi property tồn tại ở nhiều nguồn cần được xác định theo bootstrap/provider đang sử dụng.

### Thận trọng với schema generation

~~~xml
<property name="jakarta.persistence.schema-generation.database.action"
          value="drop-and-create"/>
~~~

Giá trị này yêu cầu thao tác phá/tạo schema, phù hợp bài test tái tạo dữ liệu nhưng có thể **xóa dữ liệu** nếu dùng sai database. Với production, thường dùng migration có lịch sử rõ ràng (Flyway, Liquibase hoặc quy trình tương đương) và hạn chế việc JPA tự thay đổi cấu trúc schema. `persistence.xml` không phải công cụ quản lý version migration.

## 10. Shared cache và Bean Validation

Hai phần tử tùy chọn có thể đặt trước `<properties>`:

~~~xml
<persistence-unit name="catalogPU">
    <class>com.example.catalog.Product</class>
    <exclude-unlisted-classes>true</exclude-unlisted-classes>
    <shared-cache-mode>ENABLE_SELECTIVE</shared-cache-mode>
    <validation-mode>AUTO</validation-mode>
</persistence-unit>
~~~

### `shared-cache-mode`

| Giá trị | Ý nghĩa khái quát |
|---|---|
| `ALL` | Cố gắng cache các entity theo chính sách toàn bộ. |
| `NONE` | Không sử dụng shared cache cho entity. |
| `ENABLE_SELECTIVE` | Chỉ cache entity được chọn, ví dụ qua `@Cacheable(true)`. |
| `DISABLE_SELECTIVE` | Cache theo mặc định, ngoại trừ entity tắt cache. |
| `UNSPECIFIED` | Để provider xác định theo chính sách mặc định. |

**First-level cache** là phần của persistence context nhằm quản lý entity theo danh tính; nó khác **second-level/shared cache** dùng giữa các context/factory theo cấu hình và provider. Chỉ khai báo `<shared-cache-mode>` không tự tạo cache backend phân tán hoặc làm cho mọi query được cache.

### `validation-mode`

`AUTO` áp dụng Bean Validation tích hợp khi có provider validation thích hợp; `CALLBACK` chỉ rõ việc thực thi validation callback theo điều kiện của môi trường; `NONE` tắt cơ chế validation tự động này. Ví dụ một field:

~~~java
@jakarta.validation.constraints.NotBlank
private String name;
~~~

Annotation cần dependency Bean Validation API và implementation. Validation trước ghi dữ liệu **không thay thế** constraint vật lý trong database như unique constraint, foreign key hoặc not-null. Có thể cấu hình các nhóm validation theo lifecycle bằng các property chuẩn `jakarta.persistence.validation.group.*`.

## 11. `persistence.xml` trong Spring và Spring Boot

Trong Java SE hoặc Jakarta EE, XML thường là đầu vào cấu hình trực tiếp. Ngược lại, **Spring Boot + Spring Data JPA** thường không cần `persistence.xml` vì Boot tự cấu hình `DataSource`, `EntityManagerFactory`, package scanning và các thuộc tính JPA từ `application.yml`/`application.properties`.

Ví dụ Spring Boot:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/catalog
    username: catalog_user
    password: ${DB_PASSWORD}
  jpa:
    hibernate:
      ddl-auto: validate
    properties:
      hibernate:
        format_sql: true
~~~

`${DB_PASSWORD}` là cú pháp placeholder của Spring; giá trị mật khẩu thực tế nên đến từ biến môi trường hoặc secret manager. Các khóa `spring.*` là cấu hình Spring Boot, **không phải phần tử `persistence.xml`**.

| Kiểu ứng dụng | Cấu hình JPA phổ biến | Ai bootstrap factory? |
|---|---|---|
| Java SE theo chuẩn JPA | `META-INF/persistence.xml` | Code gọi `Persistence.createEntityManagerFactory`. |
| Jakarta EE | `persistence.xml` + DataSource/container config | Container/JPA integration. |
| Spring Boot auto-config | `application.yml` + classpath/entity scan | Spring Boot/Spring ORM. |
| Spring ORM tự cấu hình | `LocalContainerEntityManagerFactoryBean`, có thể sử dụng persistence unit XML | Spring context. |

Vì vậy, thêm `persistence.xml` vào dự án Spring Boot **không tự bảo đảm** một unit XML sẽ thay toàn bộ cấu hình Boot. Khi có nhiều factory, cần kiểm tra bean wiring, persistence unit name và package scanning để biết cấu hình thực sự có hiệu lực.

## 12. Chuyển đổi từ `javax.persistence` sang `jakarta.persistence`

Một dự án JPA 2.2 cũ có thể có dạng:

~~~xml
<persistence xmlns="http://xmlns.jcp.org/xml/ns/persistence"
             version="2.2">
    <persistence-unit name="legacyPU">
        <properties>
            <property name="javax.persistence.jdbc.url"
                      value="jdbc:postgresql://localhost:5432/legacy"/>
        </properties>
    </persistence-unit>
</persistence>
~~~

Khi chuyển sang Jakarta Persistence 3.x, cần đồng bộ:

- Java imports/annotations từ `javax.persistence.*` sang `jakarta.persistence.*`.
- XML namespace/XSD/version từ dòng cũ sang `https://jakarta.ee/xml/ns/persistence` và schema phù hợp.
- Property chuẩn từ `javax.persistence.*` sang `jakarta.persistence.*`.
- Tệp `orm.xml`, Bean Validation và thư viện provider/runtime tương thích với Jakarta.
- Các extension Hibernate/Spring/Jakarta EE cần được xem xét theo phiên bản thực tế.

Thay tên package trong XML **không đủ** để migrate một ứng dụng nếu bytecode entity, provider và framework vẫn phụ thuộc thư viện `javax`. Không nên ghép provider đời cũ với entity `jakarta` rồi kỳ vọng việc phát hiện mapping tự động thành công.

## 13. Các lỗi thường gặp khi cấu hình

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `No Persistence provider for EntityManager named catalogPU` | Không có unit đúng tên; `META-INF` sai vị trí; thiếu provider | Kiểm tra artifact classpath, tên unit, dependency runtime. |
| XML parser báo schema/element lỗi | Namespace/version không khớp hoặc thứ tự element sai | Kiểm tra XML well-formed, XSD và vị trí từng thẻ. |
| `Not a managed type` / `Unknown entity` | Entity không thuộc unit hoặc metadata không được tìm thấy | Kiểm tra `@Entity`, `<class>`, mapping file, scanning và archive. |
| Driver không được tìm thấy | Thiếu JDBC driver tại runtime | Kiểm tra dependency của H2/PostgreSQL/MySQL tương ứng. |
| Không lấy được connection | Sai JDBC URL/credential/JNDI DataSource hoặc database không chạy | Kiểm tra loại DataSource và môi trường deployment. |
| `TransactionRequiredException` hoặc không commit | Sai mô hình JTA/local hoặc thao tác ngoài transaction | Kiểm tra `transaction-type` và transaction boundary. |
| `Table not found` | Schema thiếu, nhầm database/schema, mapping tên bảng sai | Kiểm tra migration, schema action và datasource thực tế. |
| Chọn sai bảng hoặc sai entity | Bootstrap nhầm unit hoặc nhiều archive/cấu hình chồng nhau | Xác nhận persistence unit name, packages và factory đang dùng. |
| Cache không hoạt động như mong đợi | Chỉ bật mode nhưng chưa cấu hình provider/cache backend | Kiểm tra second-level cache integration và mapping. |
| Spring Boot dường như bỏ qua XML | Factory do Spring tự dựng từ cấu hình khác | Kiểm tra cấu hình Spring ORM, packagesToScan và unit name. |
| Dữ liệu mất khi chạy test/khởi động | Vô tình để `drop-and-create`/`create` | Tách config test/prod, dùng migrations an toàn. |

Một chuỗi chẩn đoán hữu ích khi `EntityManagerFactory` không khởi tạo được:

~~~mermaid
flowchart TD
    A["Có META-INF/persistence.xml trên runtime classpath?"] -->|Không| B["Kiểm tra resources và packaging"]
    A -->|Có| C["XML/XSD và thứ tự phần tử hợp lệ?"]
    C -->|Không| D["Sửa namespace, version và cấu trúc"]
    C -->|Có| E["Tên persistence unit khớp?"]
    E -->|Không| F["Sửa name / unitName"]
    E -->|Có| G["Provider và JDBC driver có sẵn?"]
    G -->|Không| H["Kiểm tra dependencies/runtime"]
    G -->|Có| I["Managed classes và mappings đúng?"]
    I -->|Không| J["Kiểm tra class, mapping-file, scanning"]
    I -->|Có| K["DataSource, transaction và schema đúng?"]
    K -->|Không| L["Kiểm tra connection/JTA/local/schema"]
    K -->|Có| M["Bootstrap persistence unit thành công"]
~~~

Ngay cả khi bootstrap thành công, một transaction vẫn có thể fail do constraint, deadlock, quyền database hoặc lỗi nghiệp vụ. `persistence.xml` quyết định **cách cấu hình ORM**, không bảo đảm mọi SQL đều commit thành công.

## 14. Cách tổ chức cấu hình trong dự án thực tế

### Khi nào nên dùng `persistence.xml`?

Tệp này hữu ích khi muốn bootstrap theo chuẩn JPA trong Java SE, khi Jakarta EE container nhận diện persistence unit, khi cần khai báo chính xác các mapping/class, hoặc khi ứng dụng có nhiều unit cần chọn tường minh. Với Spring Boot auto-configuration, `application.yml` có thể đã đủ và tránh duy trì hai nguồn cấu hình cạnh tranh.

### Những nguyên tắc quan trọng

1. **Đặt đúng file** tại `META-INF/persistence.xml` trong archive thực sự chạy.
2. **Đặt tên unit rõ nghĩa**, dùng cùng tên khi tạo factory hoặc injection.
3. **Giữ XML và dependency đồng thế hệ**: namespace, XSD, provider và `javax`/`jakarta`.
4. **Chọn transaction type có chủ đích** cùng DataSource/JDBC phù hợp.
5. **Kiểm soát tập managed classes** qua `<class>` và hiểu đúng discovery.
6. **Phân biệt property chuẩn với vendor-specific** khi chuyển provider hoặc nâng cấp.
7. **Bảo vệ secrets** và tránh schema action phá hủy dữ liệu ngoài môi trường demo/test.
8. **Kiểm tra cơ chế bootstrap của framework** trước khi thêm một unit XML vào Spring.

### `persistence.xml` khác những tệp nào?

| Tệp | Vai trò |
|---|---|
| `persistence.xml` | Định nghĩa persistence unit, provider, transaction, DataSource, classes và properties JPA. |
| `orm.xml` | Ánh xạ entity, bảng, cột và quan hệ dưới dạng XML metadata. |
| `application.yml`/`application.properties` | Cấu hình ứng dụng Spring, thường bao gồm DataSource và JPA auto-config. |
| Flyway/Liquibase/SQL migrations | Theo dõi và áp dụng các thay đổi schema qua các phiên bản ứng dụng. |

## 15. Tổng hợp luồng từ tệp XML đến SQL

~~~text
META-INF/persistence.xml
        │
        ├── persistence-unit name
        ├── provider
        ├── managed classes + mapping
        ├── DataSource / JDBC
        ├── transaction type
        └── options/properties
                   │
                   ▼
           EntityManagerFactory
                   │
                   ▼
               EntityManager
                   │
         find / persist / merge / remove
                   │
                   ▼
          JPA Provider + JDBC SQL
                   │
                   ▼
          Database + transaction
            commit / rollback
~~~

Khi xem một dự án có `persistence.xml`, năm câu hỏi quan trọng nhất là:

- **“JPA quản lý entity nào?”** Xem `<class>`, mapping XML, `<jar-file>` và scanning.
- **“JPA dùng database nào?”** Xem DataSource/JDBC properties và đối chiếu cấu hình của container/Spring.
- **“Ai commit/rollback?”** Xem `transaction-type` và cách runtime điều phối transaction.
- **“Ai tạo SQL?”** Xem provider được chọn và dependency thực tế.
- **“Vì sao không khởi tạo được?”** Kiểm tra đường dẫn, XML schema, tên unit, provider, mapping và connection.

`persistence.xml` là **bản mô tả phạm vi và cách khởi tạo persistence unit**. Hiểu rõ cấu trúc của nó giúp lần theo luồng từ metadata entity đến `EntityManagerFactory`, `EntityManager`, câu SQL và ranh giới transaction, đồng thời tránh nhầm lẫn giữa cấu hình JPA chuẩn và cấu hình của framework hoặc provider.
