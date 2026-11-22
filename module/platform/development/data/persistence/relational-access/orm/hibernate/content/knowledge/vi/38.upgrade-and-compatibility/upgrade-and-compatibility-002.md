# Thay đổi không gian tên javax.persistence sang jakarta.persistence trong mã cũ

Khi nâng cấp một ứng dụng Hibernate/JPA cũ lên nền tảng Jakarta, thay đổi dễ thấy nhất là package của Persistence API chuyển từ `javax.persistence` sang `jakarta.persistence`. Ví dụ, annotation `@Entity` trước đây được import từ `javax.persistence.Entity`; với Jakarta Persistence, nó đến từ `jakarta.persistence.Entity`.

Đây không chỉ là đổi tên cho đẹp. Hai package tạo ra **hai tập kiểu Java khác nhau**. Một entity được biên dịch với `javax.persistence.Entity` không trở thành Jakarta entity chỉ vì runtime có Hibernate mới. Provider Jakarta tìm annotation `jakarta.persistence.Entity`, trong khi bytecode cũ vẫn tham chiếu `javax.persistence.Entity`.

Vì vậy, migration cần đồng bộ source imports, dependency graph, XML descriptors, property names và các thư viện tích hợp. Cũng cần phân biệt các package Java vẫn thuộc Java SE, chẳng hạn `javax.sql` hoặc `javax.naming`, để không thay thế hàng loạt một cách máy móc.

Bài thuộc chương **Nâng cấp và tương thích** của module *Data Persistence Relational Access ORM Hibernate*. Trọng tâm là di chuyển mã cũ từ Java EE/JPA namespace sang Jakarta Persistence khi nâng cấp Hibernate và framework liên quan.

## 1. Vì sao namespace thay đổi?

Trong các phiên bản Java EE trước đây, nhiều specification APIs dùng package bắt đầu bằng `javax.*`. Sau quá trình chuyển Java EE sang Eclipse Foundation, nền tảng được đổi tên thành Jakarta EE.

Từ **Jakarta EE 9**, các API thuộc Jakarta EE được chuyển sang namespace `jakarta.*`. Jakarta Persistence là một trong các specification thực hiện thay đổi này:

~~~text
Java EE / JPA 2.x:
  javax.persistence.Entity
  javax.persistence.EntityManager
  javax.persistence.Persistence

Jakarta EE / Jakarta Persistence 3.x:
  jakarta.persistence.Entity
  jakarta.persistence.EntityManager
  jakarta.persistence.Persistence
~~~

Tên class/interface thường được giữ nguyên, nhưng package thay đổi. Trong Java, package là một phần của binary name. Vì thế:

~~~text
javax.persistence.Entity
jakarta.persistence.Entity
~~~

là hai kiểu khác nhau, không phải alias của nhau.

### Tác động đến ứng dụng

- Source code cũ cần cập nhật imports.
- Bytecode cũ cần được biên dịch lại với Jakarta API.
- Dependencies phải cung cấp đúng Jakarta API version.
- Hibernate/JPA provider phải hỗ trợ namespace mới.
- XML descriptors phải dùng schema/namespace phù hợp.
- Các integration libraries và annotation processors phải tương thích.
- Một số JPA property names có prefix mới.

**Chỉ đổi imports mà giữ nguyên Hibernate 5/JPA 2 dependencies sẽ không tạo ra migration hoàn chỉnh.**

## 2. Mốc phiên bản cần hiểu

| Stack cũ | Stack Jakarta |
| --- | --- |
| Java EE 8 | Jakarta EE 8 vẫn giữ namespace javax |
| JPA 2.2 | Jakarta Persistence 3.0 trở lên |
| `javax.persistence.*` | `jakarta.persistence.*` |
| Hibernate ORM 5.x | Hibernate ORM 6.x/7.x |
| Spring Framework 5 / Spring Boot 2 | Spring Framework 6 / Spring Boot 3 trở lên |
| Java EE-era integrations | Jakarta-compatible integrations |

Điểm dễ nhầm: **Jakarta EE 8 vẫn dùng namespace javax**. Việc chuyển package bắt đầu với Jakarta EE 9. Vì vậy, tên “Jakarta EE” không tự động có nghĩa ứng dụng đã dùng `jakarta.*`.

Hibernate ORM 6 là bước chuyển quan trọng sang Jakarta Persistence. Hibernate 5.6 vẫn thuộc thế hệ JPA 2.2/`javax.persistence`. Các minor versions của Hibernate 6/7 có thể hỗ trợ những phiên bản Jakarta Persistence khác nhau; hãy đối chiếu compatibility matrix và BOM của target stack.

### Không nâng cấp chỉ một thư viện

Một ứng dụng thường có cả:

- JDK.
- Spring Boot/Spring Framework hoặc Jakarta EE application server.
- Hibernate ORM.
- Jakarta Persistence API.
- JTA/transaction manager.
- Bean Validation/Hibernate Validator.
- Servlet/JAX-RS/CDI nếu có.
- JDBC driver.
- JPA metamodel generator.
- QueryDSL, Envers, Search, auditing và các integration libraries.

Những thành phần này cần cùng một hệ namespace. Nâng Hibernate nhưng để validation hoặc transaction integration cũ có thể tạo compile errors hoặc runtime linkage errors.

## 3. Namespace migration là binary-incompatible

Xét entity cũ:

~~~java
import javax.persistence.Entity;
import javax.persistence.Id;

@Entity
public class Customer {

    @Id
    private Long id;
}
~~~

Sau khi biên dịch, bytecode có annotation descriptor tham chiếu đến:

~~~text
Ljavax/persistence/Entity;
Ljavax/persistence/Id;
~~~

Hibernate Jakarta tìm:

~~~text
Ljakarta/persistence/Entity;
Ljakarta/persistence/Id;
~~~

Tên class giống nhau nhưng descriptor khác nhau. Provider không tự xem annotation cũ là annotation mới.

Điều đó có nghĩa:

1. Không thể chỉ thay dependency ở runtime rồi mong bytecode cũ hoạt động.
2. Cần biên dịch lại source với Jakarta imports.
3. Các module nội bộ chứa entity cũng phải được build lại.
4. JAR bên thứ ba được biên dịch chỉ với javax API cần bản Jakarta-compatible hoặc phải được thay thế/migrate.
5. Cần tránh đưa cả hai API vào một classloader với kỳ vọng chúng tương thích.

## 4. Bảng thay đổi imports JPA phổ biến

| Namespace cũ | Namespace mới |
| --- | --- |
| `javax.persistence.Entity` | `jakarta.persistence.Entity` |
| `javax.persistence.Table` | `jakarta.persistence.Table` |
| `javax.persistence.Id` | `jakarta.persistence.Id` |
| `javax.persistence.GeneratedValue` | `jakarta.persistence.GeneratedValue` |
| `javax.persistence.GenerationType` | `jakarta.persistence.GenerationType` |
| `javax.persistence.Column` | `jakarta.persistence.Column` |
| `javax.persistence.ManyToOne` | `jakarta.persistence.ManyToOne` |
| `javax.persistence.OneToMany` | `jakarta.persistence.OneToMany` |
| `javax.persistence.ManyToMany` | `jakarta.persistence.ManyToMany` |
| `javax.persistence.OneToOne` | `jakarta.persistence.OneToOne` |
| `javax.persistence.JoinColumn` | `jakarta.persistence.JoinColumn` |
| `javax.persistence.JoinTable` | `jakarta.persistence.JoinTable` |
| `javax.persistence.Embedded` | `jakarta.persistence.Embedded` |
| `javax.persistence.Embeddable` | `jakarta.persistence.Embeddable` |
| `javax.persistence.EmbeddedId` | `jakarta.persistence.EmbeddedId` |
| `javax.persistence.Version` | `jakarta.persistence.Version` |
| `javax.persistence.Transient` | `jakarta.persistence.Transient` |
| `javax.persistence.Enumerated` | `jakarta.persistence.Enumerated` |
| `javax.persistence.EnumType` | `jakarta.persistence.EnumType` |
| `javax.persistence.Temporal` | `jakarta.persistence.Temporal` |
| `javax.persistence.TemporalType` | `jakarta.persistence.TemporalType` |
| `javax.persistence.AttributeConverter` | `jakarta.persistence.AttributeConverter` |
| `javax.persistence.Converter` | `jakarta.persistence.Converter` |
| `javax.persistence.PrePersist` | `jakarta.persistence.PrePersist` |
| `javax.persistence.PostLoad` | `jakarta.persistence.PostLoad` |
| `javax.persistence.EntityManager` | `jakarta.persistence.EntityManager` |
| `javax.persistence.EntityManagerFactory` | `jakarta.persistence.EntityManagerFactory` |
| `javax.persistence.Persistence` | `jakarta.persistence.Persistence` |
| `javax.persistence.TypedQuery` | `jakarta.persistence.TypedQuery` |
| `javax.persistence.Query` | `jakarta.persistence.Query` |
| `javax.persistence.criteria.CriteriaBuilder` | `jakarta.persistence.criteria.CriteriaBuilder` |
| `javax.persistence.metamodel.SingularAttribute` | `jakarta.persistence.metamodel.SingularAttribute` |
| `javax.persistence.PersistenceException` | `jakarta.persistence.PersistenceException` |
| `javax.persistence.LockModeType` | `jakarta.persistence.LockModeType` |
| `javax.persistence.PersistenceContext` | `jakarta.persistence.PersistenceContext` |
| `javax.persistence.PersistenceUnit` | `jakarta.persistence.PersistenceUnit` |

Phần lớn type names và method names giữ nguyên. Thay đổi chủ yếu là package; nhưng behavior khác giữa JPA 2.2 và Jakarta Persistence 3.x vẫn cần được kiểm tra theo specification/version.

## 5. Ví dụ entity trước và sau migration

### Trước: JPA 2.2

~~~java
package com.example.store.domain;

import javax.persistence.Column;
import javax.persistence.Entity;
import javax.persistence.GeneratedValue;
import javax.persistence.GenerationType;
import javax.persistence.Id;
import javax.persistence.Table;
import javax.persistence.Version;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String sku;

    @Column(nullable = false)
    private String name;

    @Version
    private long version;

    protected Product() {
    }
}
~~~

### Sau: Jakarta Persistence

~~~java
package com.example.store.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String sku;

    @Column(nullable = false)
    private String name;

    @Version
    private long version;

    protected Product() {
    }
}
~~~

Tên entity, bảng, cột, identifier strategy và field không cần đổi chỉ vì namespace. Database schema không tự thay đổi do import đổi package.

### Entity inheritance và embedded types

Phải chuyển imports ở tất cả entity types, không chỉ root entity:

~~~java
import jakarta.persistence.Embeddable;
import jakarta.persistence.Embedded;
import jakarta.persistence.EmbeddedId;
import jakarta.persistence.MappedSuperclass;
import jakarta.persistence.Inheritance;
import jakarta.persistence.InheritanceType;
~~~

Một embedded object hoặc mapped superclass vẫn có thể bị provider bỏ qua nếu annotation của nó đến từ namespace cũ.

## 6. Đổi dependencies Maven

Với JPA 2.2 và Hibernate 5.x, dự án cũ thường có dependencies dạng:

~~~xml
<dependency>
    <groupId>javax.persistence</groupId>
    <artifactId>javax.persistence-api</artifactId>
    <version>2.2</version>
</dependency>

<dependency>
    <groupId>org.hibernate</groupId>
    <artifactId>hibernate-core</artifactId>
    <version>5.6.x</version>
</dependency>
~~~

Khi chuyển sang Hibernate ORM 6.x, coordinates thường là:

~~~xml
<dependency>
    <groupId>org.hibernate.orm</groupId>
    <artifactId>hibernate-core</artifactId>
    <version>6.6.x.Final</version>
</dependency>

<dependency>
    <groupId>jakarta.persistence</groupId>
    <artifactId>jakarta.persistence-api</artifactId>
    <version>3.1.x</version>
</dependency>
~~~

Các version ở đây minh họa thế hệ artifact, không phải khuyến nghị pin một patch cụ thể. Với Spring Boot nên để BOM quản lý version thay vì tự đặt một bộ version không tương thích.

### Nếu dùng Spring Boot

Thông thường giữ starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-jpa</artifactId>
</dependency>
~~~

Thay parent/BOM sang Spring Boot 3 phù hợp để framework quản lý Hibernate/Jakarta dependencies.

**Không thêm một phiên bản Jakarta Persistence tùy ý để ghi đè BOM** trừ khi đã kiểm tra compatibility matrix.

### Loại bỏ API cũ

Sau migration, không nên còn dependency compile/runtime vào:

~~~xml
<dependency>
    <groupId>javax.persistence</groupId>
    <artifactId>javax.persistence-api</artifactId>
</dependency>
~~~

Nếu một thư viện khác kéo API này transitively, hãy tìm dependency gây ra và nâng cấp/thay thế nó. Không chỉ exclude mù quáng nếu thư viện vẫn được compile với javax types.

## 7. Dependency coordinates không phải tất cả đều đổi cùng quy tắc

| Mục đích | Cũ | Mới |
| --- | --- | --- |
| JPA API | `javax.persistence:javax.persistence-api` | `jakarta.persistence:jakarta.persistence-api` |
| Hibernate ORM core | `org.hibernate:hibernate-core` ở Hibernate 5.x | `org.hibernate.orm:hibernate-core` ở Hibernate 6+ |
| Bean Validation API | `javax.validation:validation-api` | `jakarta.validation:jakarta.validation-api` |
| Hibernate Validator | Thế hệ 6.x dùng javax | Thế hệ 7+ dùng Jakarta |
| JTA API | `javax.transaction:javax.transaction-api` | `jakarta.transaction:jakarta.transaction-api` |
| Servlet API | `javax.servlet:javax.servlet-api` | `jakarta.servlet:jakarta.servlet-api` |

Coordinates và phiên bản cụ thể phụ thuộc target platform. Application server có thể cung cấp APIs ở runtime; scope/dependency declarations cần theo hướng dẫn của server.

Không suy luận rằng mọi artifact có chữ `javax` trong tên đều phải đổi, hoặc mọi artifact `jakarta` đều tương thích với mọi Hibernate version.

## 8. Gradle dependencies

Dự án Gradle cũ có thể khai báo:

~~~groovy
dependencies {
    implementation "javax.persistence:javax.persistence-api:2.2"
    implementation "org.hibernate:hibernate-core:5.6.15.Final"
}
~~~

Ví dụ Jakarta với Hibernate 6.x, nếu tự quản version:

~~~groovy
dependencies {
    implementation "jakarta.persistence:jakarta.persistence-api:3.1.0"
    implementation "org.hibernate.orm:hibernate-core:6.6.0.Final"
}
~~~

Đây là minh họa coordinates; hãy dùng release versions đã được xác nhận tương thích. Với Spring Boot Gradle plugin/BOM, ưu tiên:

~~~groovy
dependencies {
    implementation "org.springframework.boot:spring-boot-starter-data-jpa"
}
~~~

### Kiểm tra dependency graph

Maven:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dincludes=javax.persistence:javax.persistence-api
mvn dependency:tree -Dincludes=jakarta.persistence:jakarta.persistence-api
~~~

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency javax.persistence-api --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jakarta.persistence-api --configuration runtimeClasspath
~~~

Mục tiêu là hiểu **ai đang kéo API cũ**, chứ không chỉ nhìn file build trực tiếp. Một dependency cũ có thể kéo JPA 2.2 transitive vào classpath dù source code đã đổi imports.

## 9. Không thay thế hàng loạt mọi javax

Đây là một trong những lỗi migration phổ biến nhất.

Jakarta EE chuyển các specification packages của mình sang `jakarta.*`, nhưng nhiều package `javax.*` vẫn là Java SE APIs hoặc APIs không thuộc phần namespace migration đó.

| Package | Hướng xử lý |
| --- | --- |
| `javax.persistence` | Đổi sang `jakarta.persistence` |
| `javax.transaction` (JTA) | Đổi sang `jakarta.transaction` khi chuyển JTA API |
| `javax.validation` | Đổi sang `jakarta.validation` |
| `javax.servlet` | Đổi sang `jakarta.servlet` khi chuyển Servlet API |
| `javax.inject` | Dùng `jakarta.inject` nếu chuyển sang Jakarta Inject |
| `javax.enterprise` | Dùng `jakarta.enterprise` nếu chuyển CDI |
| `javax.ws.rs` | Dùng `jakarta.ws.rs` nếu chuyển Jakarta REST |
| `javax.xml.bind` | Dùng `jakarta.xml.bind` khi chuyển JAXB |
| `javax.annotation` (Common Annotations) | Kiểm tra API tương ứng; thường chuyển sang `jakarta.annotation` |
| `javax.sql` | Giữ nguyên; Java SE |
| `javax.naming` | Giữ nguyên; Java SE |
| `javax.crypto` | Giữ nguyên; Java SE |
| `javax.net.ssl` | Giữ nguyên; Java SE |
| `javax.xml.parsers` | Giữ nguyên; Java SE |
| `javax.annotation.processing` | Giữ nguyên; Java compiler API |
| `javax.transaction.xa` | Giữ nguyên; Java SE XA API |

Danh sách là những trường hợp phổ biến, không thay thế việc kiểm tra từng type. Ví dụ, `javax.transaction` (JTA) và `javax.transaction.xa` không cùng được migrate theo một cách: XA package thuộc Java SE và vẫn dùng namespace `javax`.

### Ví dụ quan trọng: DataSource

Code này vẫn đúng sau migration:

~~~java
import javax.sql.DataSource;
~~~

Không đổi thành `jakarta.sql.DataSource` vì package đó không phải Jakarta Persistence API.

Tương tự:

~~~java
import javax.naming.InitialContext;
import javax.crypto.Cipher;
import javax.net.ssl.SSLContext;
~~~

vẫn là Java SE packages.

### Quy tắc an toàn

Không dùng search-and-replace toàn repository cho chuỗi `javax.`. Thay theo danh sách package/specification đã xác định, sau đó compile và review imports.

## 10. JTA transaction API

Nếu code cũ dùng JTA:

~~~java
import javax.transaction.Transactional;
import javax.transaction.UserTransaction;
import javax.transaction.TransactionManager;
~~~

Trong Jakarta stack, API tương ứng thường là:

~~~java
import jakarta.transaction.Transactional;
import jakarta.transaction.UserTransaction;
import jakarta.transaction.TransactionManager;
~~~

Nhưng nếu dùng Spring transaction annotation:

~~~java
import org.springframework.transaction.annotation.Transactional;
~~~

thì **giữ nguyên** import này. Đây là annotation của Spring, không phải JTA annotation.

| Annotation | Thuộc về |
| --- | --- |
| `jakarta.transaction.Transactional` | Jakarta Transactions |
| `org.springframework.transaction.annotation.Transactional` | Spring transaction abstraction |

Một method có thể chạy dưới Spring transaction manager hoặc JTA transaction manager tùy cấu hình. Chọn đúng annotation và transaction integration; đổi namespace không tự cấu hình transaction manager.

## 11. Bean Validation API liên quan tới entity

Ứng dụng JPA thường đặt validation annotations trên entity:

~~~java
import javax.validation.constraints.NotBlank;
import javax.validation.constraints.Size;
~~~

Khi chuyển sang Jakarta Validation:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
~~~

Ví dụ:

~~~java
@Entity
public class Customer {

    @Id
    private Long id;

    @NotBlank
    @Size(max = 120)
    private String name;
}
~~~

Phải nâng cấp Bean Validation provider tương thích Jakarta, chẳng hạn Hibernate Validator thuộc thế hệ Jakarta phù hợp. Nếu giữ Validator cũ dùng `javax.validation`, provider mới có thể không nhận ra constraints.

Cũng cần kiểm tra validation dependency có được quản lý bởi Spring Boot BOM hay application server hay không.

## 12. Common Annotations và lifecycle hooks

Code cũ có thể dùng:

~~~java
import javax.annotation.PostConstruct;
import javax.annotation.PreDestroy;
~~~

Trong Jakarta Common Annotations, package tương ứng là:

~~~java
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
~~~

Đây không phải JPA lifecycle callbacks. JPA callbacks vẫn nằm trong:

~~~java
import jakarta.persistence.PrePersist;
import jakarta.persistence.PostLoad;
import jakarta.persistence.PreUpdate;
~~~

| Annotation | Ý nghĩa |
| --- | --- |
| `jakarta.annotation.PostConstruct` | Container/framework lifecycle callback |
| `jakarta.persistence.PostLoad` | Entity lifecycle callback sau load |
| `jakarta.persistence.PrePersist` | Entity callback trước persist |
| `jakarta.persistence.PreUpdate` | Entity callback trước update |

Ngoài ra, `javax.annotation.processing` thuộc Java compiler API và vẫn giữ nguyên namespace. Không đổi tất cả imports bắt đầu bằng `javax.annotation` mà không xác định type cụ thể.

## 13. Cập nhật persistence.xml

Ứng dụng cũ có thể có `META-INF/persistence.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence
    xmlns="http://xmlns.jcp.org/xml/ns/persistence"
    version="2.2">
    <persistence-unit name="storePU">
        <provider>org.hibernate.jpa.HibernatePersistenceProvider</provider>
    </persistence-unit>
</persistence>
~~~

Với Jakarta Persistence 3.0, namespace/schema được chuyển sang Jakarta XML namespace:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence
    xmlns="https://jakarta.ee/xml/ns/persistence"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        https://jakarta.ee/xml/ns/persistence
        https://jakarta.ee/xml/ns/persistence/persistence_3_0.xsd"
    version="3.0">

    <persistence-unit name="storePU">
        <provider>org.hibernate.jpa.HibernatePersistenceProvider</provider>
    </persistence-unit>
</persistence>
~~~

Nếu target Jakarta Persistence 3.1/3.2, dùng version/schema tương ứng được specification và provider hỗ trợ. Không copy version 3.0 vào mọi target stack.

### Những gì thường giữ nguyên?

- Tên persistence unit, ví dụ `storePU`.
- Provider class name của Hibernate, nếu version vẫn dùng class đó.
- Entity class names.
- Table/column mappings.
- JDBC URL/user/password values.
- Hibernate-specific properties, trừ khi có breaking changes riêng.

Nhưng phải kiểm tra toàn bộ descriptor và schema version; XML namespace cũ có thể khiến validation/bootstrap không đúng.

## 14. Cập nhật orm.xml

Nếu dùng XML mapping thay annotations, descriptor cũng cần namespace/schema Jakarta phù hợp.

Ví dụ khung Jakarta ORM XML:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<entity-mappings
    xmlns="https://jakarta.ee/xml/ns/persistence/orm"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        https://jakarta.ee/xml/ns/persistence/orm
        https://jakarta.ee/xml/ns/persistence/orm/orm_3_0.xsd"
    version="3.0">

    <entity class="com.example.store.Product">
        <table name="products"/>
    </entity>
</entity-mappings>
~~~

Đây là ví dụ cho ORM XML 3.0; hãy dùng schema version tương ứng với Jakarta Persistence target.

Nếu dự án dùng `hibernate.cfg.xml` hoặc Hibernate-specific `hbm.xml`, đó là Hibernate configuration/mapping formats, không phải tất cả đều dùng persistence XML namespace. Không thay schema/DOCTYPE của các file Hibernate-specific theo quy tắc JPA XML.

## 15. JPA property names và prefix

Một số standard JPA property names cũ bắt đầu bằng `javax.persistence.*`. Trong Jakarta Persistence, prefix tương ứng chuyển sang `jakarta.persistence.*`.

| Cũ | Jakarta |
| --- | --- |
| `javax.persistence.jdbc.driver` | `jakarta.persistence.jdbc.driver` |
| `javax.persistence.jdbc.url` | `jakarta.persistence.jdbc.url` |
| `javax.persistence.jdbc.user` | `jakarta.persistence.jdbc.user` |
| `javax.persistence.jdbc.password` | `jakarta.persistence.jdbc.password` |
| `javax.persistence.schema-generation.database.action` | `jakarta.persistence.schema-generation.database.action` |
| `javax.persistence.validation.mode` | `jakarta.persistence.validation.mode` |

Ví dụ property map:

~~~java
Map<String, Object> properties = new HashMap<>();

properties.put(
    "jakarta.persistence.jdbc.url",
    jdbcUrl
);

properties.put(
    "jakarta.persistence.jdbc.user",
    username
);
~~~

Các property của Hibernate như `hibernate.show_sql`, `hibernate.format_sql` hoặc `hibernate.jdbc.batch_size` vẫn mang prefix `hibernate.*`. Không thay mọi string bắt đầu bằng `javax.` một cách máy móc.

Nếu Spring Boot cấu hình datasource qua `spring.datasource.*`, các keys đó thuộc Spring Boot và không đổi thành `jakarta.persistence.*`.

## 16. JPQL, HQL và database schema có phải đổi không?

Chỉ namespace migration **không bắt buộc** đổi JPQL entity names hoặc table/column names.

~~~java
List<Product> products = entityManager.createQuery(
    "select p from Product p where p.active = true",
    Product.class
).getResultList();
~~~

Câu JPQL không chứa package `javax.persistence` nên không cần đổi chỉ vì namespace.

Tương tự:

- `@Table(name = "products")` giữ nguyên.
- `@Column(name = "created_at")` giữ nguyên.
- Tên persistence unit giữ nguyên.
- SQL table/column names không tự đổi.
- Database data không tự chuyển đổi.

Tuy nhiên, nếu đồng thời nâng Hibernate 5 lên 6/7, có thể có thay đổi HQL parser, type system, SQL generation, dialect, identifier handling và schema tooling. Phải tách namespace migration khỏi provider upgrade để tìm đúng nguyên nhân khi test thất bại.

## 17. JPA Criteria API và Metamodel

Các Criteria imports cũng đổi package:

~~~java
import javax.persistence.criteria.CriteriaBuilder;
import javax.persistence.criteria.CriteriaQuery;
import javax.persistence.criteria.Root;
~~~

thành:

~~~java
import jakarta.persistence.criteria.CriteriaBuilder;
import jakarta.persistence.criteria.CriteriaQuery;
import jakarta.persistence.criteria.Root;
~~~

Static metamodel types cũng chuyển:

~~~java
import jakarta.persistence.metamodel.SingularAttribute;
~~~

Nếu dùng generated metamodel:

~~~java
criteria.where(
    builder.equal(root.get(Product_.sku), sku)
);
~~~

thì annotation processor phải tương thích Jakarta Persistence. Nếu processor cũ tạo source dựa trên `javax.persistence.metamodel`, build có thể lỗi hoặc generated sources không phù hợp.

Kiểm tra:

- Hibernate metamodel generator version.
- QueryDSL JPA artifacts/classifier tương thích Jakarta.
- Annotation processor path.
- Generated source directories.
- Incremental build cache.
- IDE annotation processing settings.

Sau khi thay processor, dùng clean build chuẩn của dự án để tránh source cũ còn sót. Không chỉnh tay generated classes.

## 18. QueryDSL và thư viện tích hợp

Không chỉ entity source mới cần chuyển. Các thư viện có APIs nhận/return JPA types cũng cần bản Jakarta-compatible.

Ví dụ cần rà soát:

- QueryDSL JPA.
- Hibernate Envers.
- Hibernate Search.
- Spring Data JPA.
- Auditing libraries.
- Repository extensions.
- JPA metamodel generators.
- Migration/test libraries có dùng EntityManager.
- Custom framework modules chứa annotations hoặc metamodel types.

Một thư viện có thể compile được vì có cả hai APIs trên classpath nhưng vẫn không tương tác với provider Jakarta nếu nó dùng `javax.persistence.EntityManager`.

Kiểm tra release notes và artifact variant của từng integration. Đừng chỉ dựa vào tên package của library.

## 19. Spring Boot 2 sang Spring Boot 3

Nếu ứng dụng dùng Spring Boot 2, việc chuyển JPA namespace thường đi cùng một đợt nâng cấp lớn:

| Spring Boot 2.x | Spring Boot 3.x |
| --- | --- |
| Java 8/11 tùy release | Java 17 baseline |
| Spring Framework 5 | Spring Framework 6 |
| Hibernate 5.x thường được quản lý | Hibernate 6.x theo BOM |
| JPA 2.2 / javax | Jakarta Persistence |
| Servlet javax trong stack cũ | Jakarta Servlet |
| Bean Validation javax | Jakarta Validation |

Bảng là hướng tổng quát; kiểm tra yêu cầu Java và dependency versions của đúng Spring Boot release.

Trong Spring Boot, thường giữ starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-jpa</artifactId>
</dependency>
~~~

Thay parent/BOM sang Spring Boot 3 phù hợp để framework quản lý Hibernate/Jakarta dependencies. Không giữ Spring Framework 5 với Hibernate/Jakarta stack mới mà không có compatibility plan. Spring Data JPA và transaction integration phải thuộc release train phù hợp.

## 20. Java version là một phần của migration plan

Namespace Jakarta và JDK baseline là hai thay đổi liên quan nhưng không đồng nhất.

Ví dụ Spring Boot 3 yêu cầu Java 17. Một dự án có thể cần nâng:

- Compiler source/target hoặc `--release`.
- Maven/Gradle toolchain.
- CI JDK image.
- Runtime container image.
- Test JDK.
- Application server/Jakarta runtime.
- Build plugins và annotation processors.

Maven compiler:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Gradle toolchain:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Các ví dụ chỉ phù hợp nếu target stack yêu cầu Java 17; Hibernate/Spring release khác có thể có baseline khác. Dùng release documentation của framework làm nguồn quyết định.

## 21. Application server và provided APIs

Nếu triển khai lên Jakarta EE application server, server có thể cung cấp Persistence API, transaction manager, validation provider và các services khác.

Trong trường hợp đó:

- Dùng namespace/version mà server hỗ trợ.
- Tránh bundle thêm API jar xung đột với server.
- Đánh dấu dependencies theo hướng dẫn deployment (ví dụ provided scope khi phù hợp).
- Không mang Hibernate version không tương thích nếu server quản lý Hibernate.
- Kiểm tra classloader isolation và server module policy.

Một ứng dụng chạy trên server Java EE 8/Jakarta EE 8 vẫn có thể cần `javax.persistence`. Không đổi package chỉ vì server mang tên Jakarta EE 8.

## 22. Tại sao không để cả javax và jakarta API cùng tồn tại?

Trong quá trình chuyển tiếp, classpath có thể vô tình chứa:

~~~text
javax.persistence-api-2.2.jar
jakarta.persistence-api-3.x.jar
hibernate-core-5.x.jar
hibernate-core-6.x.jar
~~~

Đây là dấu hiệu dependency graph chưa được thống nhất.

Các hậu quả:

- Source imports compile nhầm API.
- Library cũ trả về `javax.persistence.EntityManager` trong khi code mới cần `jakarta.persistence.EntityManager`.
- Provider không nhận annotation của namespace kia.
- ClassCastException hoặc NoClassDefFoundError ở runtime.
- Container classloader chọn class khác với class mong đợi.
- Có nhiều providers cạnh tranh khi bootstrap.

Hai APIs có thể cùng tồn tại trong một số bridge scenarios được thiết kế có chủ đích, nhưng **không tự tương thích**. Không giữ cả hai chỉ để dập compile errors.

## 23. Tìm imports cũ trong source

Tìm toàn repository các package cần migration:

~~~bash
rg -n "javax\\.persistence" src
rg -n "javax\\.transaction" src
rg -n "javax\\.validation" src
rg -n "javax\\.annotation" src
~~~

Trong multi-module project, tìm cả module con, test sources, generated sources và shared libraries. Điều chỉnh path theo cấu trúc repo.

Không thay thế mọi kết quả `javax.annotation`: phân biệt Common Annotations với Java compiler APIs như `javax.annotation.processing`.

Search toàn project có chọn lọc:

~~~bash
rg -n "javax\\.(persistence|transaction|validation|servlet|inject|enterprise|ws\\.rs|xml\\.bind)" .
~~~

Kết quả là danh sách ứng viên cần review. Không chạy replace tự động trước khi phân loại từng package.

## 24. Thứ tự migration đề xuất

~~~text
1. Chụp baseline và xác nhận tests hiện có
          |
          v
2. Inventory JDK, framework, provider và integrations
          |
          v
3. Chọn target Jakarta/Hibernate/Spring versions
          |
          v
4. Cập nhật BOM và dependency graph
          |
          v
5. Chuyển imports và APIs liên quan
          |
          v
6. Cập nhật XML descriptors / property keys
          |
          v
7. Nâng annotation processors và integrations
          |
          v
8. Clean compile và unit tests
          |
          v
9. Integration tests với DB thật/test container
          |
          v
10. Smoke test deployment, transactions và runtime
~~~

Giữ mỗi nhóm thay đổi trong một commit hoặc patch logic để khi có lỗi có thể xác định tầng gây ra.

## 25. Bước 1: lập inventory trước khi sửa

Tạo bảng:

| Thành phần | Phiên bản hiện tại | Phiên bản đích | Nguồn quản lý |
| --- | --- | --- | --- |
| JDK | | | Toolchain/CI |
| Spring Boot | | | Parent/BOM |
| Hibernate ORM | | | BOM/dependency |
| Persistence API | | | Provider/platform |
| JTA | | | Framework/server |
| Bean Validation | | | BOM |
| Servlet | | | Server/framework |
| Metamodel generator | | | Annotation processor |
| QueryDSL/Envers | | | BOM/integration |
| JDBC driver | | | App/platform |

Xác định ai quản lý version: Spring Boot BOM, Hibernate BOM, Jakarta EE platform BOM hoặc app tự pin. Tránh để nhiều BOM ghi đè nhau mà không biết thứ tự precedence.

## 26. Bước 2: nâng dependency graph

Sau khi chọn target stack:

- Thay Hibernate 5 coordinates bằng Hibernate 6/7 coordinates nếu tự quản provider.
- Dùng Jakarta Persistence API phù hợp.
- Bỏ `javax.persistence-api`.
- Cập nhật JTA/Validation/Servlet dependencies nếu framework yêu cầu.
- Cập nhật integration libraries.
- Kiểm tra test scope và annotation processor path.
- Kiểm tra runtime container có cung cấp API nào.
- Xem dependency tree để tìm javax transitive dependencies.

Nếu dùng Spring Boot, ưu tiên starter/BOM để giữ bộ dependencies tương thích.

## 27. Bước 3: thay imports theo package

Ví dụ:

~~~diff
-import javax.persistence.Entity;
-import javax.persistence.Id;
-import javax.persistence.Table;
+import jakarta.persistence.Entity;
+import jakarta.persistence.Id;
+import jakarta.persistence.Table;
~~~

Làm tương tự cho:

- Main sources.
- Test sources.
- Shared domain modules.
- Custom converters.
- Entity listeners.
- Repositories/DAO interfaces.
- Criteria/metamodel code.
- Test fixtures.
- Integration modules.

Không sửa package Java SE giữ nguyên namespace.

### Annotation không cần đổi tên

`@Entity` vẫn là `@Entity`, `@Id` vẫn là `@Id`, `@ManyToOne` vẫn là `@ManyToOne`. Điều đổi là package chứa annotation.

## 28. Bước 4: cập nhật JPA XML và property keys

Rà soát:

- `META-INF/persistence.xml`.
- `META-INF/orm.xml`.
- XML mapping files.
- JPA schema-generation property names.
- JPA JDBC property names.
- Configuration Map được tạo bằng strings.
- Environment variables/properties mapping sang JPA keys.

Hibernate-specific `hibernate.*` settings thường vẫn giữ tên; đọc migration guide cho các settings/provider behavior đã thay đổi độc lập.

## 29. Bước 5: annotation processors và generated code

Nếu dùng static metamodel, đảm bảo processor tương thích Jakarta. Sau khi thay version:

1. Kiểm tra annotation processor dependency.
2. Kiểm tra Gradle/Maven processor path.
3. Clean generated source output.
4. Rebuild toàn bộ modules.
5. Xác nhận generated types import `jakarta.persistence.metamodel`.
6. Chạy tests dùng Criteria API/metamodel.

Không sửa file generated source bằng tay; thay generator hoặc cấu hình để source được tạo đúng.

## 30. Bước 6: kiểm tra transaction/validation phụ trợ

Một ứng dụng JPA có thể compile entity tốt nhưng lỗi ở transaction/validation vì một integration vẫn dùng javax.

Rà soát:

- `javax.transaction.*` (JTA) so với `jakarta.transaction.*`.
- `javax.validation.*` so với `jakarta.validation.*`.
- `javax.annotation.PostConstruct` so với `jakarta.annotation.PostConstruct`.
- `javax.inject.*` so với `jakarta.inject.*`.
- Servlet APIs nếu web layer cũng được nâng.
- Container-provided transaction/validation services.

Nếu dùng Spring annotation, giữ `org.springframework.transaction.annotation.Transactional` và các Spring APIs tương ứng.

## 31. Bước 7: clean build và test theo tầng

Maven:

~~~bash
mvn clean test
mvn verify
~~~

Gradle:

~~~bash
./gradlew clean test
./gradlew check
~~~

Dùng task phù hợp dự án; chạy sau khi dependency/config đã cập nhật.

Phân tầng lỗi:

1. Compile imports: còn type javax hay thiếu Jakarta artifact?
2. Annotation processing: metamodel/generated sources có đúng namespace?
3. Unit tests: business code/DTO logic có đổi không?
4. JPA bootstrap: persistence unit/provider/descriptor có nhận đúng không?
5. Mapping: entities/associations/converters/listeners có được nhận diện không?
6. Transactions: JTA/Spring transaction integration có hoạt động không?
7. Database integration: SQL/schema behavior có thay đổi do Hibernate upgrade không?
8. Deployment: runtime server/classloader có conflict không?

## 32. Kiểm tra entity có được Hibernate nhận diện

Một lỗi phổ biến sau migration là entity không còn được phát hiện. Dấu hiệu có thể là:

- `Not a managed type`.
- Unknown entity.
- Missing entity mapping.
- Persistence unit bootstrap failure.

Kiểm tra:

- Entity imports là `jakarta.persistence.*`.
- Đúng EntityManagerFactory/SessionFactory đang được dùng.
- Entity package nằm trong scan configuration.
- XML mapping references đúng class.
- Không còn module entity compile với javax.
- Runtime provider đúng version.
- Có một API/provider stack nhất quán trong classloader.

Một entity có annotation `javax.persistence.Entity` không được coi như có `jakarta.persistence.Entity`.

## 33. Lỗi compile thường gặp

| Lỗi | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `package javax.persistence does not exist` | Đã bỏ API cũ nhưng source chưa đổi | Đổi imports sang Jakarta |
| `package jakarta.persistence does not exist` | Thiếu Jakarta API hoặc BOM cũ | Cập nhật dependencies |
| `cannot access javax.persistence.EntityManager` | Library cũ được compile với JPA 2.2 | Nâng/thay library Jakarta-compatible |
| `incompatible types: jakarta... cannot be converted to javax...` | Hai namespace cùng tồn tại ở API boundary | Chuẩn hóa method signatures/dependencies |
| Metamodel generated source compile fail | Processor cũ | Nâng Jakarta-compatible processor |
| `NoClassDefFoundError: javax/persistence/...` | Runtime library vẫn tham chiếu javax | Tìm dependency cũ và nâng cấp |
| `ClassNotFoundException: jakarta.persistence...` | Runtime thiếu Jakarta API | Sửa runtime packaging/server |
| Annotation không được nhận | Entity bytecode còn javax annotation | Recompile toàn bộ entity modules |

Không giải quyết lỗi bằng cách thêm cả hai APIs nếu mục tiêu là một Jakarta runtime thống nhất.

## 34. Lỗi runtime/bootstrap thường gặp

| Triệu chứng | Kiểm tra |
| --- | --- |
| No Persistence provider for persistence unit | Provider dependency, persistence.xml, classloader |
| Not a managed type | Entity scan, namespace imports, EMF |
| Unknown entity | Mapping/registration và module JAR |
| Persistence unit schema invalid | XML namespace/schema version |
| JTA transaction integration error | javax/jakarta JTA mismatch và transaction manager |
| Validation annotations không chạy | Jakarta Validation provider/dependencies |
| LinkageError/NoSuchMethodError | Version conflict hoặc binary incompatible library |
| Multiple persistence providers | Dependency graph/service loader |
| App server deployment error | API version và server-provided modules |

Đọc nguyên nhân gốc trong stack trace. Dòng lỗi đầu tiên thường chỉ là symptom; `Caused by` sâu hơn có thể chỉ rõ API class thiếu hoặc method không tương thích.

## 35. Database schema có cần migrate không?

**Namespace đổi từ javax sang jakarta tự nó không đổi database schema.**

Nếu chỉ thay imports và API artifacts mà giữ mapping/provider behavior tương đương:

- Table names giữ nguyên.
- Column names giữ nguyên.
- Foreign keys giữ nguyên.
- Data giữ nguyên.
- Sequence names giữ nguyên trừ khi cấu hình thay đổi.
- SQL migrations không cần chỉ vì namespace.

Tuy nhiên, nếu cùng lúc nâng Hibernate 5 lên 6/7, schema generation, type mappings, dialects, identifier handling hoặc SQL generation có thể thay đổi. Đây là migration của provider, không phải hệ quả trực tiếp của package rename.

Nên:

1. Dùng schema migrations có version control.
2. So sánh generated DDL trước/sau trên cùng mappings.
3. Kiểm tra numeric/temporal/enum/UUID types.
4. Kiểm tra sequences/identity columns.
5. Không chạy auto schema update trực tiếp trên production chỉ để thử upgrade.
6. Test migrations trên bản sao database hoặc staging.

## 36. JPQL/HQL và native SQL

Namespace migration không bắt buộc sửa JPQL:

~~~java
entityManager.createQuery(
    "select p from Product p where p.sku = :sku",
    Product.class
);
~~~

Nhưng Hibernate 5 -> 6/7 có thể thay đổi HQL parsing, query type inference, SQL rendering và APIs. Nếu query fail sau upgrade, tách:

- Lỗi compile do namespace.
- Lỗi JPA specification behavior.
- Lỗi Hibernate-specific HQL/SQL behavior.
- Lỗi dialect/database.

Native SQL thường không chứa JPA package names, nhưng code tạo query và result mappings có thể phụ thuộc API types.

## 37. Entity listeners, converters và callbacks

Ví dụ converter cũ:

~~~java
import javax.persistence.AttributeConverter;
import javax.persistence.Converter;

@Converter
public class CurrencyConverter
        implements AttributeConverter<Money, BigDecimal> {
    // ...
}
~~~

Sau migration:

~~~java
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter
public class CurrencyConverter
        implements AttributeConverter<Money, BigDecimal> {
    // ...
}
~~~

Cũng kiểm tra `@EntityListeners`, `@PrePersist`, `@PostPersist`, `@PreUpdate`, `@PostUpdate`, `@PostLoad`, `@Embeddable`, `@Embedded`, `@Converter` và custom repository interfaces nhận `EntityManager`.

Các class listener/converter trong shared module cũng phải biên dịch với cùng API namespace.

## 38. Envers và Hibernate extensions

Hibernate Envers là extension của Hibernate, không phải annotation thuộc Jakarta Persistence. Tuy vậy, version Envers phải tương thích với Hibernate ORM core cùng release line.

- Đổi Hibernate core nhưng giữ Envers version cũ có thể tạo linkage errors.
- Custom Envers listeners có thể dùng JPA types và cần đổi imports.
- Audit entities cũng phải dùng Jakarta annotations.
- Schema audit tables cần được kiểm tra nếu đồng thời thay Hibernate version.

Cùng nguyên tắc áp dụng với Hibernate Search, Spatial và các extension khác: chọn version compatible với Hibernate ORM và Jakarta stack.

## 39. Test strategy trước khi deploy

Một bộ test migration nên có các lớp:

### Compile and dependency checks

- Không còn imports javax thuộc Jakarta APIs đã migrate.
- Không có JPA 2.2 API transitive ngoài dự kiến.
- Không có Hibernate core major versions cùng classpath.
- Annotation processor tạo Jakarta metamodel.
- Các modules domain/shared được build lại.

### Persistence integration

- Persistence unit/EntityManagerFactory khởi động.
- Persist và load một entity.
- Entity relationships và cascade hoạt động.
- Attribute converters hoạt động.
- Entity listeners/callbacks hoạt động.
- JPQL, Criteria và native query hoạt động.
- Optimistic/pessimistic locks hoạt động theo expectation.
- Transaction commit/rollback hoạt động.

### Schema/deployment

- DDL diff được review.
- Flyway/Liquibase migrations chạy trên database test.
- Connection pool hoạt động.
- App server/container load đúng provider/API.
- Không có duplicate provider/service-loader issue.

## 40. Ví dụ integration test đơn giản

Với Spring Boot test:

~~~java
@DataJpaTest
class ProductRepositoryTest {

    @Autowired
    ProductRepository repository;

    @Test
    void persistsAndLoadsProduct() {
        Product saved = repository.save(
            new Product("SKU-100", "Keyboard")
        );

        Product loaded = repository.findById(saved.getId())
            .orElseThrow();

        assertEquals("SKU-100", loaded.getSku());
    }
}
~~~

Các imports JPA trong entity/repository và test configuration phải dùng namespace phù hợp. `@DataJpaTest` là Spring Boot annotation nên không chuyển sang Jakarta package.

Test này chỉ là smoke test. Cần thêm tests cho mappings, converters, transactions, native SQL, schema migrations và query behavior của ứng dụng thật.

## 41. Kiểm tra package còn sót bằng build tools

Maven:

~~~bash
mvn dependency:tree -Dverbose
mvn dependency:tree -Dincludes=javax.persistence:javax.persistence-api
mvn dependency:tree -Dincludes=org.hibernate:hibernate-core
~~~

Gradle:

~~~bash
./gradlew dependencyInsight --dependency javax.persistence-api --configuration runtimeClasspath
./gradlew dependencyInsight --dependency hibernate-core --configuration runtimeClasspath
~~~

Source scan:

~~~bash
rg -n "javax\\.persistence" .
rg -n "javax\\.transaction" .
rg -n "javax\\.validation" .
~~~

Sau migration, kết quả search cần được review theo package cụ thể. Có thể còn reference trong tài liệu, compatibility modules hoặc code không chạy; không kết luận lỗi chỉ từ một match trong README.

## 42. Không tự động rewrite dependency của thư viện bên thứ ba

Nếu thư viện vendor chỉ phát hành bản javax:

- Tìm release Jakarta-compatible.
- Kiểm tra vendor support matrix.
- Thay bằng thư viện tương đương nếu cần.
- Cô lập integration cũ trong service/module riêng nếu kiến trúc cho phép.
- Chỉ dùng bytecode transformation tool khi nền tảng và vendor khuyến nghị, có test và có kế hoạch vận hành rõ.

Một transformer có thể đổi class references trong bytecode nhưng không bảo đảm semantics, reflection strings, XML resources, service descriptors và external APIs đều đúng.

Không dùng transformer như cách mặc định để trộn một ecosystem javax và một ecosystem Jakarta trong cùng persistence unit.

## 43. Có nên migrate từng module không?

Trong monolith multi-module, có thể chia migration theo dependency boundaries, nhưng một persistence unit không nên nhận entities từ hai namespace và kỳ vọng provider tự hiểu cả hai.

~~~text
legacy-domain.jar
  javax.persistence annotations

new-api.jar
  jakarta.persistence annotations

Hibernate 6 SessionFactory
  -> không coi javax entities là Jakarta entities
~~~

Có thể giữ một nhánh release cũ và một nhánh release Jakarta trong giai đoạn chuyển đổi, hoặc tách deployments/services có boundary rõ. Nhưng không nên trộn entity classes javax và jakarta trong cùng một Hibernate 6 persistence unit.

Shared DTOs không chứa persistence annotations có thể dễ di chuyển hơn; domain/entity modules cần được migrate đồng bộ.

## 44. Rollback và triển khai theo giai đoạn

Trước production:

- Giữ artifact/build cũ có thể redeploy.
- Lưu dependency lock/BOM versions.
- Chạy migration scripts trên staging copy.
- Kiểm tra schema compatibility và backward/forward deployment requirements.
- Xác định có thể rollback app mà không rollback database không.
- Nếu schema DDL thay đổi, chuẩn bị migration tương thích cả hai app versions khi cần.
- Theo dõi bootstrap errors, transaction failures, query latency và connection pool metrics sau deploy.

Namespace migration thuần túy thường không cần data migration, nhưng Hibernate major upgrade có thể kéo theo schema/query behavior changes. Đừng gộp hai quyết định mà không có rollback plan.

## 45. Các lỗi do search-and-replace quá rộng

| Thay thế sai | Vì sao sai | Cách đúng |
| --- | --- | --- |
| `javax.sql.DataSource` → `jakarta.sql.DataSource` | Java SE package, không có Jakarta replacement | Giữ `javax.sql.DataSource` |
| `javax.naming.InitialContext` → `jakarta.naming.InitialContext` | Java SE JNDI | Giữ `javax.naming` |
| `javax.crypto.Cipher` → `jakarta.crypto.Cipher` | Java SE cryptography | Giữ `javax.crypto` |
| `javax.annotation.processing.Processor` → jakarta | Java compiler API | Giữ `javax.annotation.processing` |
| `javax.transaction.xa.XAResource` → jakarta | Java SE XA package | Giữ `javax.transaction.xa` |
| `org.springframework.transaction.annotation.Transactional` → jakarta | Spring package, không phải JTA | Giữ Spring import |
| Tất cả string bắt đầu `javax.` → `jakarta.` | Có nhiều Java SE packages | Chuyển theo specification/package cụ thể |

## 46. Checklist migration thực tế

**Platform và dependencies**

- Xác định Jakarta EE/Jakarta Persistence version mục tiêu.
- Chọn Hibernate ORM release tương thích.
- Chọn Spring Boot/Spring Framework release tương thích nếu dùng Spring.
- Xác nhận JDK baseline và CI/runtime toolchain.
- Dùng BOM nhất quán.
- Loại bỏ JPA 2.2 API khỏi Jakarta runtime.
- Cập nhật Validator, JTA, Servlet và integration libraries nếu cần.
- Không bundle API mà application server đã cung cấp theo hướng dẫn.

**Source code**

- Đổi `javax.persistence` sang `jakarta.persistence`.
- Đổi package Jakarta liên quan sau khi phân loại.
- Giữ Java SE `javax.*` packages.
- Cập nhật entity, converter, listener, repositories, Criteria và tests.
- Cập nhật generated metamodel/annotation processors.
- Biên dịch lại toàn bộ modules chứa entities.

**Configuration**

- Cập nhật `persistence.xml` namespace/schema/version.
- Cập nhật `orm.xml` namespace/schema/version.
- Cập nhật JPA property prefixes.
- Giữ Hibernate `hibernate.*` properties trừ breaking changes riêng.
- Kiểm tra provider/persistence unit registration.
- Kiểm tra server classloader và service provider discovery.

**Validation**

- Dependency tree không có API/provider cũ ngoài dự kiến.
- Clean compile và test thành công.
- EntityManagerFactory bootstrap.
- Persist/load/relationship/converter/callback tests.
- JPQL/Criteria/native query tests.
- Transaction/locking tests.
- Schema migration diff được review.
- Deployment smoke test và rollback plan.

## 47. Tổng kết

Chuyển từ `javax.persistence` sang `jakarta.persistence` là một **migration namespace có tính binary-incompatible**, không phải một alias đơn giản.

Các nguyên tắc quan trọng:

1. Jakarta EE 9 bắt đầu chuyển namespace các APIs từ `javax.*` sang `jakarta.*`; Jakarta EE 8 vẫn dùng javax.
2. Hibernate ORM 6 chuyển sang Jakarta Persistence; Hibernate 5.6 thuộc thế hệ JPA 2.2/namespace cũ.
3. `javax.persistence.Entity` và `jakarta.persistence.Entity` là hai kiểu khác nhau; phải recompile entity modules.
4. Đổi imports, dependencies, BOM, XML descriptors và JPA property keys cùng nhau.
5. Cập nhật JTA, Bean Validation, Common Annotations và các integration libraries khi chúng thuộc Jakarta APIs.
6. Không thay mọi `javax.`: `javax.sql`, `javax.naming`, `javax.crypto`, `javax.annotation.processing` và `javax.transaction.xa` vẫn là các package cần giữ.
7. Dùng Spring Boot BOM hoặc Jakarta platform BOM để tránh version drift.
8. Annotation processors, metamodel generators và thư viện bên thứ ba cũng phải hỗ trợ Jakarta.
9. Namespace migration tự nó không đổi table/column/data; Hibernate major upgrade có thể có thay đổi schema/query riêng.
10. Test bootstrap, mappings, transactions, queries, schema và deployment classloader trước production.

Một migration tốt giữ cho toàn bộ persistence stack sử dụng **một hệ API thống nhất**, giúp Hibernate nhận đúng annotations, application gọi đúng contracts và runtime không trộn các kiểu javax/jakarta không tương thích.

## Tài liệu tham khảo

- [Jakarta EE 9 — Release and namespace changes](https://jakarta.ee/specifications/platform/9/)
- [Jakarta Persistence 3.0 Specification](https://jakarta.ee/specifications/persistence/3.0/)
- [Jakarta Persistence 3.1 Specification](https://jakarta.ee/specifications/persistence/3.1/)
- [Jakarta Persistence 3.2 Specification](https://jakarta.ee/specifications/persistence/3.2/)
- [Hibernate ORM 6.6 User Guide](https://docs.hibernate.org/orm/6.6/userguide/html_single/)
- [Hibernate ORM 7.2 User Guide](https://docs.hibernate.org/orm/7.2/userguide/html_single/)
- [Hibernate ORM migration guides](https://docs.hibernate.org/orm/6.6/migration-guide/)
- [Spring Boot 3.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide)
- [Spring Boot Reference — Data Access](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Jakarta Transactions Specification](https://jakarta.ee/specifications/transactions/)
- [Jakarta Validation Specification](https://jakarta.ee/specifications/bean-validation/)
- [Jakarta Common Annotations Specification](https://jakarta.ee/specifications/annotations/)
