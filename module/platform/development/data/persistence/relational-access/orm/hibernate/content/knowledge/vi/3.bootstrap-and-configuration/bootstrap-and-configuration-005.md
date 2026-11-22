# Đăng ký thực thể, package và các nguồn siêu dữ liệu trong JPA/Hibernate

Khi khởi động ứng dụng dùng JPA/Hibernate, việc có các lớp Java gắn `@Entity` mới chỉ là một phần của cấu hình. Bộ quản lý persistence cần **biết những lớp nào tham gia mô hình dữ liệu**, đọc **siêu dữ liệu ánh xạ** từ annotation hoặc XML, xác định quan hệ giữa các lớp rồi xây dựng bộ máy làm việc với cơ sở dữ liệu.

Bài học này tập trung vào ba câu hỏi: **đăng ký thực thể bằng cách nào**, **package có vai trò gì trong việc tìm và tổ chức thực thể**, và **Hibernate/JPA lấy siêu dữ liệu ánh xạ từ những nguồn nào**. Ví dụ dùng Jakarta Persistence cùng Hibernate ORM, phù hợp các dự án Java hiện đại sử dụng namespace `jakarta.persistence`; những dự án cũ có thể vẫn dùng `javax.persistence`.

## 1. Đăng ký thực thể nghĩa là gì?

Một **thực thể (entity)** là lớp có định danh và được persistence provider quản lý theo ánh xạ quan hệ. Chẳng hạn:

~~~java
package com.example.shop.domain;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    protected Customer() {
        // Constructor không tham số cho JPA.
    }

    public Customer(String name) {
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

Các annotation mô tả rằng `Customer` là một entity, bảng tương ứng là `customers`, trường `id` làm khóa chính và dùng cơ chế sinh khóa identity. Tuy nhiên, **có annotation không đồng nghĩa lớp đã được đưa vào persistence unit**. Hibernate chỉ quản lý entity khi nó được tìm thấy qua cách đăng ký hoặc cơ chế khám phá lớp phù hợp với môi trường khởi động.

Có thể tách hai thao tác:

1. **Khai báo ánh xạ:** xác định `Customer` là entity, tên bảng, khóa chính, cột, quan hệ… thông qua annotation, XML hoặc API metadata.
2. **Đưa ánh xạ vào cấu hình chạy:** khai báo rõ lớp hoặc cho phép framework/provider khám phá, để nó tham gia mô hình persistence được xây dựng khi khởi động.

Nếu thiếu bước hai, thao tác như `entityManager.persist(customer)` có thể thất bại với lỗi entity không được quản lý, dù trên lớp vẫn có `@Entity`.

## 2. Từ mã nguồn đến mô hình metadata lúc khởi động

Hibernate không phân tích lại mọi annotation mỗi lần chạy SQL. Khi tạo `EntityManagerFactory` hoặc `SessionFactory`, nó thu thập cấu hình và metadata, giải quyết các ánh xạ liên quan, kiểm tra các điều kiện cần thiết rồi dựng mô hình dùng chung.

~~~mermaid
flowchart TD
    A["Các lớp Java và annotation"] --> D["Thu thập nguồn metadata"]
    B["XML: orm.xml hoặc mapping của Hibernate"] --> D
    C["Khai báo lớp, package và cấu hình bootstrap"] --> D
    D --> E["Xây dựng mô hình entity và quan hệ"]
    E --> F["EntityManagerFactory / SessionFactory"]
    F --> G["EntityManager / Session xử lý dữ liệu"]
~~~

Cần phân biệt:

| Thuật ngữ | Vai trò |
| --- | --- |
| `@Entity`, `@Id`, `@Column`, `@ManyToOne` | Mô tả ánh xạ trong mã Java |
| `persistence.xml` | Định nghĩa persistence unit JPA, có thể liệt kê lớp, file mapping và cấu hình provider |
| `orm.xml` | Nguồn ánh xạ XML chuẩn Jakarta Persistence |
| `hibernate.cfg.xml` | Cấu hình bootstrap Hibernate native; có thể khai báo các nguồn mapping |
| `*.hbm.xml` | Định dạng XML mapping riêng của Hibernate, thường gặp trong dự án cũ |
| `MetadataSources` | API Hibernate gom các nguồn metadata khi bootstrap native |
| `Metadata` | Mô hình ánh xạ đã tổng hợp trong cơ chế bootstrap Hibernate |
| `EntityManagerFactory` / `SessionFactory` | Factory được tạo từ cấu hình và metadata, phục vụ nhiều phiên làm việc |

**Metadata không phải dữ liệu nghiệp vụ.** Nó là phần mô tả cách lớp Java liên hệ với bảng/cột/khóa/quan hệ SQL. Ví dụ, “`Customer` dùng bảng `customers`” là metadata; “khách hàng có `id=12`, `name='An'`” là dữ liệu.

## 3. Ví dụ xuyên suốt và cấu trúc package

Giả sử dự án lưu khách hàng và đơn đặt hàng:

~~~text
src/
  main/
    java/
      com/
        example/
          shop/
            ShopApplication.java
            domain/
              Customer.java
              PurchaseOrder.java
            legacy/
              LegacyProduct.java
    resources/
      META-INF/
        persistence.xml
        legacy-orm.xml
~~~

Lớp đơn hàng tham chiếu `Customer`:

~~~java
package com.example.shop.domain;

import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(Customer customer) {
        this.customer = customer;
    }
}
~~~

Để một `PurchaseOrder` hoạt động đúng, mô hình metadata cũng cần biết `Customer` là kiểu entity được tham chiếu. Nếu chỉ đăng ký một phía mà bỏ lớp entity phía còn lại, quá trình xây dựng metadata có thể báo lỗi ánh xạ quan hệ.

Trong Java, **package** như `com.example.shop.domain` có nhiệm vụ tổ chức tên lớp, tránh đụng tên và định vị class trên classpath. Package tự nó **không phải bảng**, không phải entity và không nhất thiết là “đơn vị quét” của mọi cấu hình ORM. Cách ứng dụng xử lý package phụ thuộc cơ chế bootstrap.

## 4. Đăng ký tường minh qua `persistence.xml` của JPA

Với cấu hình Jakarta Persistence truyền thống, file `META-INF/persistence.xml` chứa một hoặc nhiều **persistence unit**. Mỗi unit là một cấu hình độc lập gồm provider, các lớp được quản lý, nguồn mapping và thuộc tính kết nối hoặc hành vi.

Đường dẫn trong dự án Maven/Gradle thông thường:

~~~text
src/main/resources/META-INF/persistence.xml
~~~

Ví dụ:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence
    xmlns="https://jakarta.ee/xml/ns/persistence"
    version="3.1">

    <persistence-unit
        name="shopPU"
        transaction-type="RESOURCE_LOCAL">

        <provider>
            org.hibernate.jpa.HibernatePersistenceProvider
        </provider>

        <class>com.example.shop.domain.Customer</class>
        <class>com.example.shop.domain.PurchaseOrder</class>

        <exclude-unlisted-classes>true</exclude-unlisted-classes>

        <properties>
            <property
                name="jakarta.persistence.jdbc.driver"
                value="org.postgresql.Driver"/>
            <property
                name="jakarta.persistence.jdbc.url"
                value="jdbc:postgresql://localhost:5432/shop"/>
            <property
                name="jakarta.persistence.jdbc.user"
                value="shop_user"/>
            <property
                name="hibernate.hbm2ddl.auto"
                value="validate"/>
        </properties>
    </persistence-unit>
</persistence>
~~~

Ví dụ cố ý không đặt mật khẩu trong XML: khi triển khai thực tế, giá trị nhạy cảm nên lấy từ môi trường hoặc hệ thống quản lý bí mật và truyền qua cấu hình runtime. `validate` yêu cầu bảng đã tồn tại với cấu trúc phù hợp; nếu chưa có schema, cần tạo bằng migration hoặc công cụ quản lý lược đồ trước khi chạy ví dụ.

Ý nghĩa các thành phần:

| Thành phần | Ý nghĩa |
| --- | --- |
| `name="shopPU"` | Tên để ứng dụng chọn persistence unit lúc bootstrap |
| `transaction-type="RESOURCE_LOCAL"` | Transaction do ứng dụng quản lý bằng `EntityTransaction` trong ví dụ Java SE |
| `<provider>` | Chọn Hibernate làm triển khai Jakarta Persistence |
| `<class>...Customer</class>` | Đăng ký tường minh lớp `Customer` |
| `<class>...PurchaseOrder</class>` | Đăng ký tường minh lớp `PurchaseOrder` |
| `<exclude-unlisted-classes>true</exclude-unlisted-classes>` | Không đưa các lớp chưa liệt kê vào unit chỉ vì chúng được tìm thấy qua cơ chế scan của unit |
| `<properties>` | Thuộc tính JDBC và cấu hình riêng của provider |

Để mở unit này:

~~~java
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.Persistence;

public class Main {
    public static void main(String[] args) {
        EntityManagerFactory emf =
            Persistence.createEntityManagerFactory("shopPU");

        try {
            // Tạo EntityManager và thao tác với entity ở đây.
        } finally {
            emf.close();
        }
    }
}
~~~

Lời gọi `createEntityManagerFactory("shopPU")` tìm unit theo **tên**, đọc cấu hình và dùng provider phù hợp để dựng factory. Tên không khớp, file không nằm trên classpath hoặc thiếu provider đều có thể khiến bootstrap thất bại.

### Khi nào nên liệt kê `<class>`?

Liệt kê tường minh giúp:

- Kiểm soát chính xác lớp tham gia một persistence unit.
- Tránh phụ thuộc vào việc ứng dụng có hỗ trợ quét classpath hay không.
- Phù hợp chương trình Java SE nhỏ, công cụ dòng lệnh và các unit cần tách rõ phạm vi.
- Dễ nhận ra lớp nào bị thiếu khi đổi module hoặc package.

Đổi lại, mỗi khi thêm entity mới, người phát triển phải cập nhật danh sách. Nếu có nhiều module hoặc hàng trăm entity, framework có thể hỗ trợ cơ chế khám phá thuận tiện hơn.

## 5. Khám phá entity bằng package: đừng nhầm các cơ chế

Có ba cách thường bị gọi chung là “quét package”, nhưng chúng khác nhau.

### 5.1. Quét lớp do môi trường JPA hoặc provider hỗ trợ

Một persistence provider có thể tìm các lớp được đánh dấu `@Entity`, `@Embeddable`, `@MappedSuperclass` và những thành phần mapping liên quan trong phạm vi deployment/persistence unit được quy định. Mức độ khám phá tự động phụ thuộc môi trường, cấu trúc archive và cấu hình.

Trong Java SE, **đăng ký tường minh các lớp bằng `<class>` là lựa chọn dễ dự đoán và có tính di động tốt**. Không nên mặc định rằng bất cứ entity nào nằm trên toàn bộ classpath cũng sẽ được Hibernate tự động tìm thấy.

Một vài thành phần của `persistence.xml` ảnh hưởng phạm vi này:

| Cấu hình | Tác dụng |
| --- | --- |
| `<class>com.example.shop.domain.Customer</class>` | Chỉ định một managed persistence class |
| `<mapping-file>META-INF/legacy-orm.xml</mapping-file>` | Thêm file ánh xạ XML chuẩn JPA |
| `<jar-file>...jar</jar-file>` | Tham chiếu archive chứa các lớp persistent theo quy tắc đường dẫn của persistence unit |
| `<exclude-unlisted-classes>true</exclude-unlisted-classes>` | Ngăn đưa các lớp chưa liệt kê vào unit chỉ do khám phá tự động trong phạm vi tương ứng |

Khi chia ứng dụng thành nhiều JAR, cần kiểm tra vị trí persistence unit và cách các JAR được đóng gói; không thể chỉ nhìn package name rồi kết luận provider đã tìm thấy lớp.

### 5.2. Quét entity trong Spring Boot

Spring Boot thường tự cấu hình JPA và tìm entity trong package của ứng dụng cùng các package con. Ví dụ nếu lớp chính nằm tại `com.example.shop`, các entity trong `com.example.shop.domain` thường được phát hiện theo quy ước.

~~~java
package com.example.shop;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.SpringApplication;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

Nếu entity nằm ngoài phạm vi mặc định, khai báo `@EntityScan`:

~~~java
package com.example.shop;

import com.example.shop.domain.Customer;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.domain.EntityScan;
import org.springframework.boot.SpringApplication;

@SpringBootApplication
@EntityScan(basePackageClasses = Customer.class)
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

`basePackageClasses = Customer.class` cho phép xác định package theo kiểu Java thay vì chuỗi đường dẫn dễ sai khi refactor. Nếu entity nằm ở nhiều package độc lập, có thể cung cấp nhiều marker classes hoặc khai báo `basePackages` phù hợp.

Lưu ý phạm vi của các công cụ Spring:

- `@EntityScan` kiểm soát vùng tìm **entity** cho cấu hình tự động của Spring Boot.
- `@ComponentScan` hoặc `scanBasePackages` của `@SpringBootApplication` kiểm soát vùng tìm **Spring bean**.
- `@EnableJpaRepositories`, khi cần dùng, kiểm soát vùng tìm **Spring Data repository**.

Ba loại tìm kiếm này có mục tiêu riêng. Đặt một bean trong component scan không làm lớp đó tự động trở thành JPA entity.

### 5.3. `MetadataSources.addPackage(...)` trong Hibernate native

Hibernate có API:

~~~java
sources.addPackage("com.example.shop.domain");
~~~

Tên phương thức dễ khiến người mới hiểu rằng Hibernate sẽ tìm và đăng ký toàn bộ entity trong package. **Đó không phải mục đích chính của `addPackage`.** Phương thức này bổ sung metadata khai báo ở **mức package**, chẳng hạn annotation trong `package-info.java` được Hibernate hỗ trợ. Nó **không thay thế việc đăng ký class bằng `addAnnotatedClass`** và không hàm ý quét đệ quy mọi class con.

Vì vậy, với bootstrap native, một cách chỉ định rõ ràng là:

~~~java
sources.addAnnotatedClass(Customer.class);
sources.addAnnotatedClass(PurchaseOrder.class);

// Chỉ bổ sung khi thực sự dùng metadata ở mức package:
sources.addPackage("com.example.shop.domain");
~~~

Phần sau sẽ minh họa cách tạo `sources` và factory đầy đủ.

## 6. Bootstrap Hibernate native bằng `MetadataSources`

Ngoài `persistence.xml` và API JPA, Hibernate cung cấp API khởi tạo riêng. Đây là lựa chọn khi ứng dụng dùng `SessionFactory` trực tiếp hoặc cần kiểm soát danh sách nguồn mapping.

~~~java
import com.example.shop.domain.Customer;
import com.example.shop.domain.PurchaseOrder;
import org.hibernate.SessionFactory;
import org.hibernate.boot.Metadata;
import org.hibernate.boot.MetadataSources;
import org.hibernate.boot.registry.StandardServiceRegistry;
import org.hibernate.boot.registry.StandardServiceRegistryBuilder;

public class HibernateBootstrap {
    public static SessionFactory buildFactory() {
        StandardServiceRegistry registry =
            new StandardServiceRegistryBuilder()
                .configure("hibernate.cfg.xml")
                .build();

        try {
            MetadataSources sources = new MetadataSources(registry)
                .addAnnotatedClass(Customer.class)
                .addAnnotatedClass(PurchaseOrder.class);

            Metadata metadata = sources.buildMetadata();
            return metadata.buildSessionFactory();
        } catch (RuntimeException e) {
            StandardServiceRegistryBuilder.destroy(registry);
            throw e;
        }
    }
}
~~~

Đoạn mã giả định `hibernate.cfg.xml` là resource cấu hình hợp lệ có các thuộc tính cần thiết để kết nối database. Phía gọi chịu trách nhiệm **đóng `SessionFactory`** khi ứng dụng kết thúc. Nếu bootstrap lỗi, ví dụ đã hủy registry; khi đóng factory thành công, Hibernate quản lý vòng đời tài nguyên nó sở hữu.

Diễn tiến bootstrap:

1. `StandardServiceRegistryBuilder` thiết lập dịch vụ cấu hình của Hibernate: kết nối, dialect, transaction và các dịch vụ khác.
2. `MetadataSources` thu thập các lớp có annotation và các nguồn ánh xạ khác.
3. `buildMetadata()` tổng hợp chúng thành mô hình entity, thuộc tính và quan hệ.
4. `buildSessionFactory()` tạo factory dùng chung, từ đó có thể mở `Session` để thao tác dữ liệu.

Các phương thức đăng ký tiêu biểu:

| Phương thức | Đăng ký gì? | Ghi chú |
| --- | --- | --- |
| `addAnnotatedClass(Customer.class)` | Một lớp Java có annotation mapping | Cách rõ nhất để thêm từng entity |
| `addAnnotatedClassName("com.example.shop.domain.Customer")` | Lớp thông qua tên đầy đủ | Cần tên class chính xác trên classpath |
| `addPackage("com.example.shop.domain")` | Metadata annotation ở mức package | Không tự quét tất cả entity trong package |
| `addResource("mappings/legacy.hbm.xml")` | Một resource XML mapping trên classpath | Định dạng cần được Hibernate hỗ trợ |
| `addFile(...)` | Mapping XML từ tệp trên hệ thống | Khác resource tải bằng classloader |

Trong bootstrap native, có thể thêm nhiều nguồn trước khi gọi `buildMetadata()`:

~~~java
MetadataSources sources = new MetadataSources(registry);

sources.addAnnotatedClass(Customer.class);
sources.addAnnotatedClass(PurchaseOrder.class);

// Nếu dự án có mapping XML Hibernate phù hợp:
// sources.addResource("mappings/legacy.hbm.xml");

// Nếu có annotation hợp lệ trong package-info.java:
// sources.addPackage("com.example.shop.domain");

Metadata metadata = sources.buildMetadata();
~~~

Các API Hibernate native và các thuộc tính cấu hình riêng của Hibernate có thể thay đổi giữa các phiên bản lớn. Chúng là phần mở rộng của Hibernate; mã ứng dụng cần di động giữa các JPA provider nên ưu tiên API và cấu hình Jakarta Persistence.

## 7. Những nguồn siêu dữ liệu ánh xạ chủ yếu

### 7.1. Annotation trên entity và thành phần liên quan

Nguồn phổ biến nhất là annotation ngay trong mã Java:

~~~java
@Entity
@Table(name = "customers")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "full_name", nullable = false, length = 120)
    private String name;

    protected Customer() {}
}
~~~

Các annotation thường gặp:

| Nhóm | Annotation tiêu biểu | Ý nghĩa |
| --- | --- | --- |
| Loại đối tượng | `@Entity`, `@MappedSuperclass`, `@Embeddable` | Vai trò của kiểu Java trong mô hình persistence |
| Định danh | `@Id`, `@EmbeddedId`, `@GeneratedValue` | Khóa chính và cơ chế sinh khóa |
| Bảng, cột | `@Table`, `@Column`, `@AttributeOverride` | Tên và đặc điểm ánh xạ |
| Quan hệ | `@ManyToOne`, `@OneToMany`, `@OneToOne`, `@ManyToMany`, `@JoinColumn` | Liên kết thực thể |
| Chuyển đổi | `@Convert`, `@Converter`, `@Enumerated` | Chuyển đổi giá trị Java với cột SQL |
| Truy vấn có tên | `@NamedQuery` | Định nghĩa truy vấn reusable |
| Đặc thù Hibernate | Các annotation trong `org.hibernate.annotations` | Bổ sung khả năng ngoài chuẩn JPA |

Không phải mọi lớp có annotation persistence đều tạo một bảng độc lập. `@Embeddable` mô tả giá trị nhúng; `@MappedSuperclass` chia sẻ ánh xạ cho lớp con; `@Converter` hỗ trợ chuyển đổi thuộc tính. Các loại này có thể được khám phá hoặc đăng ký theo ngữ cảnh, nhưng **không nên nhầm chúng với entity độc lập có `@Id` và vòng đời riêng**.

### 7.2. XML chuẩn Jakarta Persistence: `orm.xml`

Có thể mô tả ánh xạ bằng XML, hữu ích khi cần cấu hình ngoài mã nguồn Java hoặc giữ một mô hình domain ít phụ thuộc annotation JPA.

Ví dụ lớp Java chưa gắn `@Entity`:

~~~java
package com.example.shop.legacy;

public class LegacyProduct {
    private Long id;
    private String title;

    protected LegacyProduct() {}

    public Long getId() { return id; }
    public String getTitle() { return title; }
}
~~~

File `src/main/resources/META-INF/legacy-orm.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<entity-mappings
    xmlns="https://jakarta.ee/xml/ns/persistence/orm"
    version="3.1">

    <entity
        class="com.example.shop.legacy.LegacyProduct"
        access="FIELD">

        <table name="legacy_products"/>

        <attributes>
            <id name="id">
                <generated-value strategy="IDENTITY"/>
            </id>

            <basic name="title">
                <column name="product_title"
                        nullable="false"
                        length="200"/>
            </basic>
        </attributes>
    </entity>
</entity-mappings>
~~~

Đăng ký file từ `persistence.xml` bên trong `<persistence-unit>`:

~~~xml
<mapping-file>META-INF/legacy-orm.xml</mapping-file>
~~~

Khi ánh xạ XML đúng và file được load, provider có thể xem `LegacyProduct` là entity dù lớp không khai báo `@Entity`. Đây là ví dụ về **đăng ký ánh xạ thông qua nguồn metadata XML**.

Nếu sử dụng đồng thời annotation và `orm.xml`, quy tắc hợp nhất và ghi đè metadata do chuẩn Jakarta Persistence xác định. XML có thể được dùng để thay thế hoặc ghi đè một phần thông tin annotation; chế độ `metadata-complete` cho phép bỏ qua annotation trong phạm vi áp dụng theo quy tắc của descriptor. Việc thay đổi một ánh xạ phải xét **kết quả metadata cuối cùng**, không chỉ đọc riêng Java hay XML.

### 7.3. Hibernate XML mapping: `*.hbm.xml`

Hibernate có định dạng mapping XML lịch sử, thường gặp trong ứng dụng dùng Hibernate trước khi JPA annotation phổ biến. Nó biểu diễn entity, thuộc tính và quan hệ theo cú pháp **riêng của Hibernate**. Một resource mapping dạng này có thể được đăng ký qua `MetadataSources.addResource(...)` hoặc khai báo trong cấu hình native tương ứng.

Ví dụ khái niệm:

~~~java
MetadataSources sources = new MetadataSources(registry);
sources.addResource("mappings/legacy.hbm.xml");
~~~

File cần tồn tại trên classpath và có nội dung mapping hợp lệ với phiên bản Hibernate đang dùng. **`hbm.xml` và `orm.xml` không phải cùng định dạng**: không thể đổi tên file rồi giả định parser và quy tắc ánh xạ sẽ giống nhau. Khi nâng cấp Hibernate lớn, mapping legacy có thể cần điều chỉnh hoặc chuyển dần sang annotation/`orm.xml`.

### 7.4. Metadata khai báo ở mức package

Java cho phép tạo file `package-info.java` để chứa annotation có đích áp dụng là `PACKAGE`, ví dụ:

~~~java
@SomePackageLevelAnnotation
package com.example.shop.domain;
~~~

Đoạn trên chỉ minh họa cú pháp: `SomePackageLevelAnnotation` đại diện một annotation thực sự được định nghĩa và hỗ trợ ở cấp package, **không phải một annotation có sẵn của JPA/Hibernate**.

Trong Hibernate, một số annotation đặc thù có thể được phép khai báo ở cấp package. Nếu dùng chúng với bootstrap native, `sources.addPackage("com.example.shop.domain")` bổ sung nguồn metadata package. Đây là lý do tên `addPackage` có mặt trong API.

Ba thao tác dễ nhầm:

- `@Entity` trên `Customer`: tuyên bố lớp là entity ở mức Java.
- `addAnnotatedClass(Customer.class)`: đưa ánh xạ lớp đó vào quá trình bootstrap Hibernate native.
- `addPackage("com.example.shop.domain")`: đưa **annotation ở cấp package** vào nguồn metadata; không phải lệnh tìm tất cả entity bên trong.

Không phải annotation nào cũng dùng được trong `package-info.java`: Java kiểm tra `@Target` của annotation khi biên dịch.

## 8. `persistence.xml` và `hibernate.cfg.xml` khác nhau thế nào?

Cả hai có thể xuất hiện trong dự án Hibernate, nhưng thuộc **hai lối bootstrap**:

| Khía cạnh | JPA với `persistence.xml` | Hibernate native với `hibernate.cfg.xml` |
| --- | --- | --- |
| API khởi tạo | `Persistence.createEntityManagerFactory("shopPU")` | `StandardServiceRegistryBuilder` + `MetadataSources` + `buildSessionFactory()` |
| Đơn vị cấu hình | `<persistence-unit>` | Cấu hình các dịch vụ Hibernate và mapping |
| Đăng ký entity | `<class>`, `<mapping-file>`, khám phá theo môi trường | `addAnnotatedClass`, `addResource`, `<mapping ...>` trong cấu hình native |
| Factory thường dùng | `EntityManagerFactory` | `SessionFactory` |
| Mức phụ thuộc provider | API chuẩn JPA, có thể dùng thuộc tính riêng Hibernate | API trực tiếp của Hibernate |

Một dự án Spring Boot dùng auto-configuration thường không cần tự tạo `persistence.xml` hoặc tự gọi `StandardServiceRegistryBuilder`. Cấu hình datasource, JPA và entity scan được Spring Boot xây dựng cho `EntityManagerFactory` theo quy ước/khai báo ứng dụng.

Nên chọn **một đường bootstrap chủ đạo** cho một tập entity và datasource. Nếu vừa để framework tạo factory vừa tự tạo thêm một `SessionFactory` khác, ứng dụng có thể phát sinh hai ngữ cảnh metadata, hai pool hoặc cách quản lý transaction khác nhau nếu cấu hình thiếu nhất quán.

## 9. Phạm vi của persistence unit, module và package

Một persistence unit có tên, tập lớp được quản lý, mapping files và thuộc tính cấu hình riêng. Trong một ứng dụng, có thể có nhiều persistence unit để làm việc với các datasource hoặc mô hình độc lập. Cùng một class có thể xuất hiện trong nhiều unit với bối cảnh quản lý khác nhau, nhưng mỗi factory hoạt động theo metadata của unit mà nó được tạo từ đó.

Ví dụ:

~~~text
com.example.shop.customer.Customer
com.example.shop.order.PurchaseOrder
com.example.shared.audit.AuditRecord
~~~

Nếu chỉ quét `com.example.shop`, `AuditRecord` nằm ở nhánh `com.example.shared` có thể không được tìm thấy. Các cách xử lý tùy môi trường:

- Với JPA XML, liệt kê `com.example.shared.audit.AuditRecord` trong `<class>` hoặc cấu hình archive/mapping phù hợp.
- Với Spring Boot, cấu hình `@EntityScan` bao gồm package tương ứng.
- Với Hibernate native, gọi `addAnnotatedClass(AuditRecord.class)`.

Ngược lại, đừng mở rộng phạm vi quét tới toàn bộ ứng dụng chỉ vì có một entity nằm ngoài vị trí ban đầu. Phạm vi entity rõ ràng giúp tránh đăng ký nhầm các lớp chỉ dành cho một module, tạo tên entity trùng hoặc kéo thêm bảng không mong muốn vào persistence unit.

### Tên entity và tên bảng là hai khái niệm riêng

~~~java
@Entity(name = "CustomerRecord")
@Table(name = "customers")
public class Customer {
    // ...
}
~~~

- `CustomerRecord` là **tên entity** dùng trong JPQL, ví dụ `SELECT c FROM CustomerRecord c`.
- `customers` là **tên bảng SQL**.
- `com.example.shop.domain.Customer` là **tên class đầy đủ** để đăng ký bằng `<class>` hoặc `addAnnotatedClass`.

Nếu có hai entity trùng tên entity trong một persistence unit, có thể xảy ra xung đột mapping. Chúng cũng có thể trùng tên class đơn giản nhưng khác package; khi ấy tên đầy đủ ở đăng ký class vẫn khác nhau, còn tên entity mặc định có thể vẫn va chạm.

## 10. Từ đăng ký đến truy vấn: khi nào phát hiện sai cấu hình?

Quá trình khởi động có thể gặp lỗi ở những điểm khác nhau:

~~~text
1. Nạp file cấu hình và classpath
       ↓
2. Thu thập entity classes và mapping files
       ↓
3. Đọc annotation/XML, tạo metadata
       ↓
4. Kiểm tra liên kết và thông tin khóa/quan hệ
       ↓
5. Tạo EntityManagerFactory / SessionFactory
       ↓
6. Mở phiên làm việc, thực thi query/SQL
~~~

Ví dụ `PurchaseOrder` tham chiếu `Customer` qua `@ManyToOne`. Nếu `PurchaseOrder` được đưa vào metadata nhưng `Customer` không phải entity đã đăng ký, Hibernate có thể phát hiện vấn đề ngay ở bước xây dựng metadata. Nếu entity đăng ký đầy đủ nhưng tên bảng thực tế sai, vấn đề có thể bộc lộ ở bước xác thực schema (nếu bật) hoặc khi truy vấn/ghi dữ liệu.

Để xem danh sách entity đã thực sự nằm trong factory JPA, dùng **JPA Metamodel**:

~~~java
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.Persistence;
import jakarta.persistence.metamodel.EntityType;

public class InspectEntities {
    public static void main(String[] args) {
        EntityManagerFactory emf =
            Persistence.createEntityManagerFactory("shopPU");

        try {
            for (EntityType<?> type : emf.getMetamodel().getEntities()) {
                System.out.println(
                    type.getName() + " => " +
                    type.getJavaType().getName()
                );
            }
        } finally {
            emf.close();
        }
    }
}
~~~

Đầu ra kỳ vọng nếu unit đã đăng ký hai entity trong ví dụ:

~~~text
Customer => com.example.shop.domain.Customer
PurchaseOrder => com.example.shop.domain.PurchaseOrder
~~~

Thứ tự in ra không được đảm bảo. Nếu `LegacyProduct` được đưa vào cùng unit thông qua `legacy-orm.xml`, nó cũng có thể xuất hiện trong tập này.

`getMetamodel().getEntities()` phản ánh **các entity thực sự được quản lý bởi factory hiện tại**. Nó hữu ích để phân biệt “file Java có annotation” với “entity có mặt trong runtime”.

## 11. Lỗi phổ biến và cách định vị nguyên nhân

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `Not a managed type` ở Spring Data JPA | Entity chưa được tìm qua entity scan, thiếu `@Entity` hoặc dùng nhầm namespace | Kiểm tra `@EntityScan`, package của class chính, import `jakarta.persistence` |
| `Unknown entity` / không tìm thấy entity mapping | Class chưa được đăng ký trong unit hoặc `MetadataSources` | Kiểm tra `<class>`, `addAnnotatedClass`, file mapping XML |
| `No Persistence provider for EntityManager named ...` | Sai tên unit, thiếu `META-INF/persistence.xml` trên classpath hoặc thiếu provider | Kiểm tra tên `shopPU`, đường dẫn resource, dependency runtime |
| Có `@Entity` nhưng truy vấn JPQL báo tên entity không tồn tại | Dùng tên bảng thay vì tên entity, hoặc entity chưa đăng ký | Kiểm tra `@Entity(name = ...)` và metamodel |
| Báo mapping resource không tìm thấy | Sai đường dẫn classpath hoặc resource không được đóng gói | Kiểm tra vị trí trong `src/main/resources` và tên `<mapping-file>`/`addResource` |
| Lỗi quan hệ tham chiếu entity chưa xác định | Lớp đầu kia của `@ManyToOne`/`@OneToMany` chưa có trong mô hình | Đưa đủ những lớp entity liên quan vào unit |
| Lỗi XML namespace/phiên bản | Trộn `javax.persistence` cũ với `jakarta.persistence` mới hoặc dùng descriptor sai schema | Đồng bộ API, phiên bản provider và namespace XML |
| Trùng entity name hoặc duplicate mapping | Một tên entity bị dùng lại, hoặc một class được định nghĩa mâu thuẫn qua nhiều nguồn | Kiểm tra tên entity và toàn bộ annotation/XML đang được load |
| Startup thành công nhưng báo không tồn tại bảng | Metadata trỏ tới tên bảng/schema khác database đang có | Kiểm tra `@Table`, naming strategy, schema và migration |

### Mối liên hệ giữa package và classpath

Một package đúng tên chỉ giúp giải quyết địa chỉ logic của class. Để bootstrap load được class hay XML, **class/resource thực sự phải có trong classpath runtime**. Ví dụ file `src/main/resources/META-INF/persistence.xml` thường được build tool chép vào đầu ra resources; đặt nhầm nó dưới một thư mục không được đóng gói sẽ khiến tên unit không thể tìm thấy.

Nếu mô hình entity ở module JAR khác, ứng dụng cần dependency tới JAR đó. Sau khi thêm dependency, vẫn phải đảm bảo cơ chế đăng ký hoặc quét entity bao phủ các lớp cần thiết.

### Đừng phụ thuộc vào tự sinh bảng để xác nhận cấu hình

`hibernate.hbm2ddl.auto` có các chế độ như `validate`, `update`, `create`. Việc Hibernate cố tạo bảng có thể giúp quan sát mapping trong môi trường thực hành, nhưng **không phải là bằng chứng rằng cấu hình đúng với nghiệp vụ**. Ở môi trường có dữ liệu thật, nên quản lý lược đồ bằng migration rõ ràng. Tránh dùng `create`/`create-drop` trên database cần giữ dữ liệu.

## 12. Chọn phương thức đăng ký phù hợp

| Tình huống | Cách thường phù hợp | Lý do |
| --- | --- | --- |
| Java SE nhỏ, cần portable JPA | `persistence.xml` với `<class>` | Rõ tập entity và ranh giới persistence unit |
| Spring Boot thông dụng | Entity scan theo quy ước hoặc `@EntityScan` | Tích hợp với cấu hình factory của Spring |
| Hibernate standalone/native | `MetadataSources.addAnnotatedClass` | Chủ động thu thập metadata trước khi tạo `SessionFactory` |
| Mapping ngoài annotation | `orm.xml` + `<mapping-file>` | Mô tả hoặc điều chỉnh mapping chuẩn JPA bằng XML |
| Dự án Hibernate legacy | `hbm.xml` + nguồn mapping tương ứng | Duy trì mapping sẵn có khi công nghệ hỗ trợ |
| Có annotation package-level của Hibernate | `package-info.java` + cơ chế đọc metadata package tương ứng | Cung cấp metadata cấp package, khác đăng ký entity |

Không có một công thức “quét package” áp dụng giống hệt cho mọi dự án. Hãy xác định trước dự án dùng **JPA thuần, Spring Boot hay Hibernate native**, rồi mới chọn cách đưa class, XML và package metadata vào bootstrap.

## 13. Bài tập áp dụng

Cho cấu trúc:

~~~text
com.acme.sales.domain.Invoice
com.acme.sales.domain.InvoiceLine
com.acme.identity.domain.Account
com.acme.sales.SalesApplication
~~~

Giả sử cả ba lớp đều là `@Entity` và `Invoice` có quan hệ `@ManyToOne` tới `Account`.

**Yêu cầu 1 — JPA thuần:** Tạo persistence unit `salesPU` có ba entity và không phụ thuộc scan tự động.

Gợi ý phần khai báo:

~~~xml
<persistence-unit name="salesPU" transaction-type="RESOURCE_LOCAL">
    <class>com.acme.sales.domain.Invoice</class>
    <class>com.acme.sales.domain.InvoiceLine</class>
    <class>com.acme.identity.domain.Account</class>
    <exclude-unlisted-classes>true</exclude-unlisted-classes>
    <!-- Thêm cấu hình provider và datasource phù hợp. -->
</persistence-unit>
~~~

**Yêu cầu 2 — Spring Boot:** Vì `Account` nằm ngoài package `com.acme.sales`, hãy mở rộng entity scan:

~~~java
@SpringBootApplication
@EntityScan(basePackageClasses = {
    Invoice.class,
    Account.class
})
public class SalesApplication {
}
~~~

Ví dụ trên giả định các import và ứng dụng Spring Boot đã được cấu hình; `InvoiceLine` nằm cùng package với `Invoice` nên thuộc phạm vi quét đó.

**Yêu cầu 3 — Hibernate native:** Nếu code chỉ có:

~~~java
sources.addPackage("com.acme.sales.domain");
~~~

thì có thể kết luận `Invoice` và `InvoiceLine` đều đã được đăng ký chưa?

**Đáp án:** Chưa. `addPackage` không có nghĩa quét toàn bộ entity của package. Hãy đăng ký lớp tương ứng, ví dụ:

~~~java
sources.addAnnotatedClass(Invoice.class);
sources.addAnnotatedClass(InvoiceLine.class);
sources.addAnnotatedClass(Account.class);
~~~

**Yêu cầu 4 — Quan sát runtime:** Sau khi factory khởi tạo, liệt kê `emf.getMetamodel().getEntities()`. Từ kết quả, xác định lớp nào thực sự được quản lý. Nếu thiếu `Account`, quay lại kiểm tra phạm vi đăng ký trước khi tìm lỗi ở lệnh SQL.

## 14. Ghi nhớ các ranh giới quan trọng

- **Annotation định nghĩa mapping**; **đăng ký/khám phá đưa mapping vào factory**. Hai việc liên quan nhưng không giống nhau.
- **Package name tổ chức lớp**; cơ chế scan package phụ thuộc môi trường; **`MetadataSources.addPackage` là đường thu thập metadata cấp package**, không tự động tương đương với entity scanning.
- **Nguồn metadata** có thể là annotation Java, XML Jakarta Persistence, XML riêng Hibernate hoặc đăng ký programmatic. `persistence.xml` và `hibernate.cfg.xml` chủ yếu điều phối quá trình bootstrap và tham chiếu các nguồn đó.
- **`EntityManagerFactory`/`SessionFactory` là kết quả bootstrap** chứa mô hình metadata dùng khi làm việc với các entity. Mọi truy vấn và quan hệ chỉ hoạt động theo những entity và mapping mà factory đó biết.
- Khi gặp “unknown entity”, “not a managed type” hoặc lỗi ánh xạ, hãy đi theo chuỗi: **classpath → cấu hình bootstrap → danh sách class/scan/XML → metadata của factory → tên bảng và schema**.

Hiểu đúng chuỗi này giúp tổ chức package hợp lý, thêm entity mới có chủ đích, phối hợp annotation với XML an toàn và chẩn đoán lỗi cấu hình Hibernate ngay từ lúc ứng dụng khởi động.
