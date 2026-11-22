# Not a managed type và lỗi quét Entity

Lỗi `Not a managed type: class ...` thường xuất hiện khi Spring Data JPA khởi tạo repository hoặc khi JPA truy cập metamodel. Ý nghĩa của lỗi là persistence unit hiện tại không nhận diện class được khai báo làm domain type của repository như một JPA entity.

Ví dụ, repository khai báo `JpaRepository<Product, Long>`, nhưng `Product` chưa được đăng ký trong persistence unit. Nguyên nhân thường nằm ở annotation `@Entity`, package scanning, namespace `javax.persistence`/`jakarta.persistence`, cấu hình nhiều `EntityManagerFactory`, hoặc generic type của repository.

Cần phân biệt ba cơ chế độc lập: component scanning tìm Spring bean, repository scanning tìm interface repository, còn entity scanning đăng ký các kiểu dữ liệu JPA. Một cơ chế hoạt động đúng không bảo đảm hai cơ chế còn lại cũng đúng.

## 1. Hiểu đúng thông báo Not a managed type

Ví dụ repository:

```java
public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
```

Spring Data cần biết `Product` là entity được quản lý bởi JPA để tạo metadata cho repository. Khi không tìm thấy entity tương ứng trong metamodel, ứng dụng có thể báo:

```text
IllegalArgumentException: Not a managed type: class com.example.store.Product
```

Thông báo thường xảy ra lúc Spring tạo repository bean, nên ứng dụng có thể dừng ngay khi khởi động. Trong một số cấu hình, lỗi chỉ xuất hiện khi repository hoặc `EntityManager` được sử dụng.

JPA Metamodel là tập metadata mà persistence provider xây dựng từ các entity và kiểu mapping được đăng ký. Một entity managed có thể được tìm thấy trong `EntityManagerFactory.getMetamodel().getEntities()`.

Lỗi này không có nghĩa database thiếu bảng. Nó cho biết class Java chưa được nhận diện là entity trong persistence unit đang dùng. Bảng có tồn tại, đúng tên và đúng schema cũng không làm class tự trở thành entity.

## 2. Kiểm tra class có được khai báo là Entity không

Một class dùng làm domain type cho `JpaRepository` cần được đánh dấu `@Entity` và có định danh bằng `@Id` hoặc `@EmbeddedId`.

Ví dụ với Spring Boot 3 và Jakarta Persistence:

```java
package com.example.store.product.domain;

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

    private String name;

    protected Product() {
    }

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
```

Repository:

```java
package com.example.store.product.repository;

import com.example.store.product.domain.Product;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
```

Các lỗi khai báo thường gặp:

- Chỉ có `@Table` mà thiếu `@Entity`. `@Table` chỉ tùy chỉnh mapping bảng cho một entity; nó không đăng ký class thành entity.
- Quên khai báo `@Id` hoặc `@EmbeddedId`.
- Đánh dấu class bằng `@Embeddable` hoặc `@MappedSuperclass` rồi dùng trực tiếp làm domain type của repository. Đây không phải entity độc lập.
- Repository dùng DTO, projection hoặc class request làm kiểu entity đầu tiên của `JpaRepository`.
- Class không đáp ứng yêu cầu cơ bản của entity, chẳng hạn thiếu constructor không tham số `public` hoặc `protected`, hoặc dùng class không phù hợp với quy tắc entity của JPA.

Một `@MappedSuperclass` có thể chứa các field mapping dùng chung cho lớp con; lớp con cụ thể cần được đánh dấu `@Entity`. Một `@Embeddable` là kiểu giá trị được nhúng vào entity, không phải root entity để khai báo `JpaRepository`.

## 3. Kiểm tra namespace javax và jakarta

Đây là nguyên nhân phổ biến khi nâng cấp Spring Boot hoặc trộn dependency không tương thích.

| Nền tảng | Namespace Persistence |
|---|---|
| Spring Boot 2.x / JPA 2.x | `javax.persistence.*` |
| Spring Boot 3.x / Jakarta Persistence 3.x | `jakarta.persistence.*` |

Với Spring Boot 3, entity phải dùng annotation Jakarta:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
```

Nếu entity vẫn import:

```java
import javax.persistence.Entity;
import javax.persistence.Id;
```

thì Hibernate/JPA provider theo Jakarta không xem các annotation `javax.persistence` đó là annotation mapping mà nó cần xử lý. Class có thể trông như đã được đánh dấu `@Entity` trong mã nguồn nhưng vẫn không được quản lý.

Khi nâng cấp:

- Kiểm tra toàn bộ import trong entity, mapped superclass, embeddable và converter.
- Đồng bộ phiên bản Spring Boot, Spring Data JPA, Hibernate và Jakarta Persistence.
- Không thêm đồng thời API `javax.persistence` và `jakarta.persistence` để chữa lỗi một cách tạm thời.
- Kiểm tra dependency tree để tìm thư viện cũ kéo theo JPA API không tương thích.
- Clean build và chạy lại ứng dụng sau khi sửa import/dependency.

Với Spring Boot 2, dùng `javax.persistence` theo phiên bản mà ứng dụng đang sử dụng. Không thay namespace chỉ vì một ví dụ trên mạng dùng Jakarta.

## 4. Kiểm tra package mặc định của Spring Boot

Spring Boot thường xác định package gốc từ class chứa `@SpringBootApplication`. Cấu hình mặc định dùng package đó làm điểm bắt đầu cho component scanning và auto-configuration package; entity scanning mặc định của JPA cũng dựa trên package gốc này.

Một cấu trúc thuận tiện:

```text
com.example.store
├── StoreApplication.java
├── product
│   ├── domain
│   │   └── Product.java
│   └── repository
│       └── ProductRepository.java
└── customer
    ├── domain
    │   └── Customer.java
    └── repository
        └── CustomerRepository.java
```

Class ứng dụng:

```java
package com.example.store;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StoreApplication {

    public static void main(String[] args) {
        SpringApplication.run(StoreApplication.class, args);
    }
}
```

Vì class ứng dụng nằm ở `com.example.store`, các package con như `com.example.store.product.domain` nằm trong phạm vi mặc định.

Nếu đặt class ứng dụng ở package quá sâu:

```text
com.example.store
├── StoreApplication.java
└── product
    └── domain
        └── Product.java
```

và `StoreApplication` lại nằm trong `com.example.store.config`, package `com.example.store.product.domain` không phải package con của `com.example.store.config`. Entity có thể bị bỏ sót trong lần quét mặc định.

Thực hành tốt là đặt class ứng dụng tại package cha chung của các module. Tránh đặt class main trong default package vì phạm vi scan có thể quá rộng và gây khó kiểm soát.

## 5. Dùng @EntityScan khi Entity nằm ngoài package gốc

Nếu entity nằm ở package khác hoặc một module dùng chung, có thể khai báo rõ package entity bằng `@EntityScan`:

```java
package com.example.application;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.domain.EntityScan;

@SpringBootApplication
@EntityScan(basePackages = {
    "com.example.application.domain",
    "com.example.shared.persistence.entity"
})
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

Có thể dùng `basePackageClasses` để tránh hard-code tên package:

```java
@EntityScan(basePackageClasses = {
    Product.class,
    SharedEntityMarker.class
})
```

Khi dùng `basePackageClasses`, Spring lấy package của các class được chỉ định làm package cần quét. Marker class có thể là một class rỗng được đặt trong package entity dùng chung.

Lưu ý: `@EntityScan` điều khiển entity packages cho auto-configuration của Spring Boot. Nếu ứng dụng tự khai báo nhiều `LocalContainerEntityManagerFactoryBean`, hãy cấu hình `setPackagesToScan()` trên từng factory tương ứng; đừng cho rằng `@EntityScan` tự cấu hình mọi persistence unit thủ công.

## 6. Phân biệt Entity scanning và Repository scanning

Ba annotation thường bị nhầm lẫn:

| Annotation | Mục đích |
|---|---|
| `@ComponentScan` | Tìm Spring bean như `@Service`, `@Component`, `@Controller`, `@Repository`. |
| `@EnableJpaRepositories` | Tìm interface Spring Data JPA repository. |
| `@EntityScan` | Khai báo package chứa entity cho JPA auto-configuration của Spring Boot. |

Ví dụ, `@EnableJpaRepositories` có thể tìm thấy `ProductRepository` nhưng `Product` vẫn chưa được đăng ký vào JPA metamodel. Khi đó Spring tìm được repository interface nhưng không thể tạo repository vì domain type không phải managed type.

Cấu hình:

```java
@Configuration
@EnableJpaRepositories(
    basePackages = "com.example.store.product.repository"
)
@EntityScan(
    basePackages = "com.example.store.product.domain"
)
public class JpaPackageConfig {
}
```

Trong ứng dụng Spring Boot đơn giản, không cần thêm hai annotation này nếu auto-configuration đã quét đúng package. Chỉ khai báo khi cần mở rộng hoặc giới hạn phạm vi scan.

Đừng dùng `@ComponentScan` để chữa lỗi entity scanning. Component scan có thể tìm được bean repository hoặc service, nhưng nó không thay thế việc đăng ký entity vào persistence unit.

## 7. Kiểm tra generic type của repository

Kiểu đầu tiên trong `JpaRepository<T, ID>` phải là entity managed. Projection/DTO là kiểu trả về của query, không phải domain type của repository.

Sai:

```java
public interface ProductRepository
        extends JpaRepository<ProductSummary, Long> {
}
```

Nếu `ProductSummary` là record hoặc DTO, JPA không quản lý nó như entity nên có thể báo `Not a managed type`.

Đúng:

```java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Query("""
        select new com.example.store.product.api.ProductSummary(
            p.id, p.name
        )
        from Product p
        where p.name like concat('%', :keyword, '%')
        """)
    List<ProductSummary> searchSummaries(
            @Param("keyword") String keyword);
}
```

Trong ví dụ này:

- `Product` là entity managed và được dùng làm domain type.
- `ProductSummary` là DTO projection, chỉ dùng làm kiểu kết quả của query.
- Constructor của `ProductSummary` phải khớp thứ tự và kiểu các biểu thức được chọn.

Cũng cần kiểm tra repository import đúng class. Hai class cùng tên ở package khác nhau có thể khiến repository trỏ đến DTO hoặc entity cũ thay vì entity dự kiến.

## 8. Kiểm tra class có nằm trên runtime classpath không

Trong project nhiều module, entity có thể tồn tại trong mã nguồn nhưng module chạy ứng dụng không phụ thuộc module chứa entity.

Ví dụ:

```text
store-app
├── build.gradle
└── src/main/java/...

shared-domain
├── build.gradle
└── src/main/java/com/example/shared/domain/Customer.java
```

Nếu `store-app` không khai báo dependency đến `shared-domain`, entity `Customer` không có trên runtime classpath. Thêm package vào `@EntityScan` không thể quét một class chưa được tải vào ứng dụng.

Kiểm tra:

- Module chứa entity có được build thành công không.
- Module ứng dụng có khai báo dependency đúng không.
- Dependency có ở runtime classpath hay chỉ ở test/compile configuration không.
- Artifact được deploy có chứa class mới nhất không.
- Có hai phiên bản thư viện cùng chứa class entity hoặc package trùng tên không.

Với Gradle:

```gradle
dependencies {
    implementation project(":shared-domain")
}
```

Với Maven, khai báo dependency đến artifact chứa entity trong `pom.xml` của ứng dụng. Sau khi sửa, build lại và kiểm tra dependency tree hoặc nội dung artifact.

## 9. Ứng dụng có nhiều EntityManagerFactory

Một ứng dụng có thể dùng nhiều database hoặc nhiều persistence unit. Mỗi `EntityManagerFactory` có metamodel và danh sách entity được quản lý riêng.

Một entity đã được scan trong `catalogEntityManagerFactory` không có nghĩa nó cũng được quản lý bởi `billingEntityManagerFactory`.

Với cấu hình thủ công, cần gắn repository vào đúng factory và transaction manager:

```java
@Configuration
@EnableJpaRepositories(
    basePackages = "com.example.catalog.repository",
    entityManagerFactoryRef = "catalogEntityManagerFactory",
    transactionManagerRef = "catalogTransactionManager"
)
public class CatalogJpaConfig {

    @Bean
    LocalContainerEntityManagerFactoryBean catalogEntityManagerFactory(
            @Qualifier("catalogDataSource") DataSource dataSource,
            JpaVendorAdapter vendorAdapter) {

        var factory = new LocalContainerEntityManagerFactoryBean();
        factory.setDataSource(dataSource);
        factory.setPackagesToScan("com.example.catalog.domain");
        factory.setJpaVendorAdapter(vendorAdapter);
        return factory;
    }

    @Bean
    PlatformTransactionManager catalogTransactionManager(
            @Qualifier("catalogEntityManagerFactory")
            EntityManagerFactory entityManagerFactory) {
        return new JpaTransactionManager(entityManagerFactory);
    }
}
```

Ví dụ này chỉ minh họa phần liên kết chính; cấu hình thực tế còn cần bean datasource, vendor adapter, properties và các bean cần thiết khác. Điểm quan trọng là:

- `setPackagesToScan()` đăng ký entity cho đúng factory.
- `entityManagerFactoryRef` gắn repository package với factory tương ứng.
- `transactionManagerRef` chọn transaction manager của persistence unit đó.
- Repository không nên bị gắn nhầm sang factory không quản lý entity của nó.

Nếu dùng nhiều database, nên tách package repository và entity rõ ràng theo từng persistence unit để tránh nhầm lẫn.

## 10. Kiểm tra JPA Metamodel trực tiếp

Khi ứng dụng đã khởi tạo được `EntityManagerFactory`, có thể kiểm tra entity có được quản lý hay không:

```java
import jakarta.persistence.EntityManagerFactory;
import org.springframework.stereotype.Component;

@Component
public class JpaMetadataInspector {

    private final EntityManagerFactory entityManagerFactory;

    public JpaMetadataInspector(EntityManagerFactory entityManagerFactory) {
        this.entityManagerFactory = entityManagerFactory;
    }

    public boolean isManagedEntity(Class<?> type) {
        return entityManagerFactory.getMetamodel()
                .getEntities()
                .stream()
                .anyMatch(entityType ->
                        entityType.getJavaType().equals(type));
    }
}
```

Nếu `isManagedEntity(Product.class)` trả về `false`, class chưa được đăng ký là entity trong factory đang inject.

Có thể in danh sách entity đã nhận diện:

```java
entityManagerFactory.getMetamodel()
        .getEntities()
        .forEach(entityType ->
                System.out.println(
                        entityType.getName() + " -> "
                        + entityType.getJavaType().getName()));
```

Lưu ý khi có nhiều `EntityManagerFactory`: bean `EntityManagerFactory` được inject phải là factory mà repository đang sử dụng. Nếu inject nhầm factory, danh sách metamodel không phản ánh persistence unit cần kiểm tra.

Một cách kiểm tra trực tiếp khác là:

```java
entityManagerFactory.getMetamodel().entity(Product.class);
```

Lệnh này trả về metadata của entity nếu class được quản lý; nếu không, nó ném `IllegalArgumentException`. Đây là phép kiểm tra tốt trong integration test.

## 11. Viết integration test để bắt lỗi scan sớm

Có thể dùng `@DataJpaTest` để xác nhận entity và repository được cấu hình đúng:

```java
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;

import jakarta.persistence.EntityManagerFactory;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
class ProductRepositoryTest {

    @Autowired
    EntityManagerFactory entityManagerFactory;

    @Autowired
    ProductRepository productRepository;

    @Test
    void productIsManagedByJpa() {
        assertDoesNotThrow(() ->
                entityManagerFactory.getMetamodel()
                        .entity(Product.class));
    }

    @Test
    void repositoryCanPersistProduct() {
        Product saved = productRepository.save(
                new Product("Keyboard"));

        assertDoesNotThrow(() ->
                productRepository.findById(saved.getId()));
    }
}
```

`@DataJpaTest` tạo slice test tập trung vào JPA và thường dùng database nhúng nếu có trên classpath. Nếu ứng dụng có cấu hình nhiều datasource hoặc persistence unit riêng, test cần nạp đúng cấu hình tương ứng. Nếu thiếu database nhúng, có thể dùng Testcontainers hoặc cấu hình datasource test.

Không chỉ kiểm tra context khởi động. Hãy lưu và đọc lại một entity để xác nhận repository thực sự dùng đúng mapping và database test.

## 12. Quy trình chẩn đoán theo thứ tự

Khi gặp `Not a managed type`, thực hiện lần lượt:

1. **Đọc đúng class trong exception.** Xác nhận repository đang dùng class nào, package nào và generic type đầu tiên là gì.
2. **Kiểm tra annotation entity.** Xác nhận class có `@Entity`, có `@Id` hoặc `@EmbeddedId`, và không chỉ là DTO, `@Embeddable` hoặc `@MappedSuperclass`.
3. **Kiểm tra import namespace.** Boot 2 dùng `javax.persistence`; Boot 3 dùng `jakarta.persistence`. Đồng bộ dependency với Spring/Hibernate.
4. **Kiểm tra package gốc.** Đặt class ứng dụng ở package cha chung hoặc khai báo `@EntityScan`.
5. **Phân biệt hai loại scan.** Xác nhận repository scan và entity scan đều bao phủ package đúng.
6. **Kiểm tra runtime dependency.** Nếu entity nằm ở module khác, bảo đảm module đó có mặt trên runtime classpath.
7. **Kiểm tra nhiều persistence unit.** Xác nhận repository trỏ đến đúng `EntityManagerFactory` và factory quét package entity.
8. **Kiểm tra metamodel.** Liệt kê entity đã được quản lý và thử `getMetamodel().entity(Product.class)`.
9. **Clean build và chạy integration test.** Tránh dùng artifact cũ sau khi đã sửa package, import hoặc dependency.

Không nên chữa lỗi bằng cách thêm hàng loạt package vào component scan hoặc chuyển mọi quan hệ thành EAGER. Hãy sửa đúng cơ chế scan hoặc mapping đang thiếu.

## 13. Các lỗi liên quan dễ nhầm

| Thông báo | Ý nghĩa thường gặp | Hướng kiểm tra |
|---|---|---|
| `Not a managed type: class ...` | Repository domain type không có trong metamodel của factory đang dùng. | `@Entity`, namespace, entity scan, generic type, đúng factory. |
| `No identifier specified for entity` | Entity không có khóa chính được mapping. | `@Id`, `@EmbeddedId`, mapping kế thừa. |
| `Not an entity` hoặc lỗi entity metadata tương tự | Class không được provider nhận diện là entity hoặc mapping không hợp lệ. | Annotation và persistence unit. |
| `UnknownEntityTypeException` | Provider không tìm thấy entity type trong ngữ cảnh đang truy vấn hoặc thao tác. | Entity scan, factory và class thực tế. |
| `No property ... found for type ...` | Tên property trong derived query không khớp domain class. | Tên field/getter và generic type repository. |
| `UnknownEntityException` trong JPQL | Tên entity trong JPQL không khớp entity name đã khai báo. | `@Entity(name = "...")` và tên dùng trong JPQL. |

Các thông báo trên có thể xuất hiện ở những giai đoạn khác nhau. Hãy đọc cả root cause và class cụ thể trong stack trace thay vì chỉ dựa vào dòng lỗi đầu tiên.

## 14. Checklist phòng tránh

- Đặt entity trong package rõ ràng, nằm dưới package gốc của ứng dụng hoặc khai báo `@EntityScan`.
- Dùng đúng namespace Persistence tương ứng với phiên bản Spring Boot.
- Đảm bảo entity có `@Entity` và khóa chính hợp lệ.
- Chỉ dùng entity làm generic domain type của `JpaRepository`; dùng DTO/projection làm kiểu kết quả query.
- Phân biệt `@ComponentScan`, `@EnableJpaRepositories` và `@EntityScan`.
- Kiểm tra dependency runtime của module chứa entity.
- Với nhiều database, gắn repository với đúng entity manager factory và transaction manager.
- Thêm integration test kiểm tra entity có trong metamodel và repository có thể persist/read.
- Kiểm tra artifact và dependency tree sau khi nâng cấp Spring Boot hoặc Hibernate.

`Not a managed type` là lỗi về metadata của persistence unit. Hãy xác định class repository đang dùng, kiểm tra annotation và namespace, rồi xác minh package scan hoặc factory liên quan. Khi phân biệt rõ entity scanning với repository scanning, lỗi thường được khoanh vùng nhanh mà không cần thay đổi mapping hay cấu hình một cách tùy tiện.