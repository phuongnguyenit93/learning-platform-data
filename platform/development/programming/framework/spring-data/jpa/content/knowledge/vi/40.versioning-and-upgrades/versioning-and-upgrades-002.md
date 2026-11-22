# Chuyển từ javax.persistence sang jakarta.persistence

Khi nâng cấp từ hệ sinh thái Java EE/JPA cũ sang Jakarta EE, package `javax.persistence.*` được đổi thành `jakarta.persistence.*`. Đây là thay đổi ở cấp namespace và kiểu Java, không chỉ là đổi tên trong tài liệu. Một entity được đánh dấu bằng `javax.persistence.Entity` không phải là entity được provider Jakarta nhận diện bằng `jakarta.persistence.Entity`.

Với Spring Data JPA, việc chuyển đổi thường đi cùng nâng cấp Spring Boot 2.x lên 3.x, Spring Framework 5 lên 6 và Hibernate ORM 5 lên 6. Cần nâng cấp đồng bộ JDK, framework, provider, dependency và cấu hình mapping. Không nên chỉ thay import rồi giữ nguyên các thư viện cũ.

## 1. Vì sao javax.persistence đổi thành jakarta.persistence?

Trước đây, Java Persistence API (JPA) thuộc hệ sinh thái Java EE và dùng namespace `javax.persistence`. Sau khi Java EE được chuyển giao cho Eclipse Foundation, nền tảng được phát triển dưới tên Jakarta EE.

Kể từ Jakarta EE 9, các API Java EE chuyển sang namespace mới `jakarta.*`. Jakarta Persistence tiếp tục phát triển với package `jakarta.persistence`.

Ví dụ:

| Trước đây | Sau khi chuyển |
|---|---|
| `javax.persistence.Entity` | `jakarta.persistence.Entity` |
| `javax.persistence.Id` | `jakarta.persistence.Id` |
| `javax.persistence.EntityManager` | `jakarta.persistence.EntityManager` |
| `javax.persistence.ManyToOne` | `jakarta.persistence.ManyToOne` |
| `javax.persistence.PersistenceContext` | `jakarta.persistence.PersistenceContext` |
| `javax.persistence.criteria.CriteriaBuilder` | `jakarta.persistence.criteria.CriteriaBuilder` |

Tên class và phần lớn API mapping quen thuộc được giữ lại, nhưng package đã thay đổi. Vì Java xem hai class cùng tên ở hai package khác nhau là hai kiểu độc lập, provider Jakarta không tự nhận diện annotation từ namespace cũ.

Đây là lý do một class vẫn có `@Entity` trong mã nguồn nhưng ứng dụng có thể báo `Not a managed type`: annotation đang import có thể là `javax.persistence.Entity` trong khi Hibernate 6 đang tìm `jakarta.persistence.Entity`.

## 2. Quan hệ giữa Spring Boot, Spring Data JPA và Hibernate

Việc chuyển namespace thường là một phần của nâng cấp nền tảng:

| Thế hệ | Persistence API | Hibernate ORM | Java tối thiểu |
|---|---|---|---|
| Spring Boot 2.x | JPA 2.x, `javax.persistence` | Hibernate 5.x | Phụ thuộc phiên bản Boot |
| Spring Boot 3.x | Jakarta Persistence, `jakarta.persistence` | Hibernate 6.x | Java 17 |
| Spring Boot 4.x | Jakarta Persistence thế hệ mới | Phiên bản Hibernate do Boot quản lý | Java 17 trở lên theo dòng Boot |

Bảng này mô tả thế hệ tương thích, không phải ma trận đầy đủ cho từng bản minor/patch. Hãy dùng dependency management của đúng phiên bản Spring Boot để biết chính xác Spring Data JPA, Hibernate và Jakarta Persistence API nào được quản lý.

Spring Boot 3 chuyển sang Spring Framework 6 và Jakarta EE 10. Jakarta Persistence 3.1 là thế hệ API được dùng trong dòng Boot 3.0. Các bản Boot 3.x sau có thể quản lý phiên bản Hibernate khác nhau; không tự suy ra phiên bản provider chỉ từ số major của Boot.

Spring Data JPA 3.x sử dụng Jakarta Persistence. Hibernate ORM 6 là provider theo Jakarta namespace. Vì vậy, khi ứng dụng chuyển sang Boot 3+, hãy nâng cả nhóm dependency tương ứng thay vì chỉ thêm một JAR `jakarta.persistence-api` vào project Boot 2.

## 3. Thay import trong entity và các lớp liên quan

Bắt đầu bằng cách chuyển toàn bộ import JPA trong source code:

Trước:

```java
import javax.persistence.Entity;
import javax.persistence.Id;
import javax.persistence.GeneratedValue;
import javax.persistence.GenerationType;
import javax.persistence.ManyToOne;
import javax.persistence.FetchType;
```

Sau:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.FetchType;
```

Ví dụ entity sau khi chuyển:

```java
package com.example.store.product.domain;

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

    @Column(nullable = false, length = 120)
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

Không chỉ entity chính cần đổi. Hãy rà soát tất cả class có liên quan đến persistence:

- `@Embeddable`, `@Embedded`, `@EmbeddedId`.
- `@MappedSuperclass` và các entity kế thừa.
- `AttributeConverter` và `@Converter`.
- Entity listener và lifecycle callback.
- `EntityManager`, `EntityManagerFactory`, `PersistenceContext`.
- Criteria API, metamodel, query parameter và các kiểu exception.
- Test fixture, integration test, custom repository implementation và thư viện nội bộ.

Nếu một module shared-domain vẫn biên dịch với `javax.persistence` nhưng ứng dụng chính dùng Hibernate 6, module đó cần được nâng cấp hoặc thay thế bằng phiên bản Jakarta-compatible.

## 4. Chuyển dependency Maven hoặc Gradle

Với Spring Boot 3+, cách đơn giản nhất là dùng Spring Boot dependency management và starter JPA:

Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-jpa</artifactId>
</dependency>
```

Gradle:

```gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-jpa")
    runtimeOnly("org.postgresql:postgresql")
}
```

Starter quản lý các phiên bản tương thích của Spring Data JPA, Hibernate và API Jakarta Persistence. Không cần khai báo thêm `javax.persistence:javax.persistence-api`.

Nếu project trước đây khai báo trực tiếp:

Maven cũ:

```xml
<dependency>
    <groupId>javax.persistence</groupId>
    <artifactId>javax.persistence-api</artifactId>
    <version>2.2</version>
</dependency>
```

Hãy gỡ dependency cũ khi chuyển sang Jakarta. Thông thường starter mới đã cung cấp API cần thiết. Chỉ khai báo trực tiếp `jakarta.persistence-api` nếu kiến trúc build thực sự cần và phải dùng đúng phiên bản tương thích với provider/framework.

Tránh các tình huống:

- Giữ đồng thời cả `javax.persistence-api` và `jakarta.persistence-api`.
- Nâng riêng Hibernate lên 6 nhưng vẫn giữ Spring Data JPA đời cũ dùng `javax.persistence`.
- Ép phiên bản Hibernate ngoài dependency management mà chưa kiểm tra tương thích.
- Dùng một thư viện custom repository hoặc auditing cũ chỉ hỗ trợ JPA 2.x.

Kiểm tra dependency tree để phát hiện API hoặc provider cũ được kéo vào gián tiếp.

Maven:

```bash
mvn dependency:tree
```

Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Nếu có nhiều phiên bản cùng xuất hiện, hãy xem dependency nào kéo chúng vào và cập nhật dependency gốc hoặc loại bỏ artifact không tương thích. Không loại trừ JAR chỉ dựa vào tên package; hãy xác minh thư viện đó thực sự thuộc API cũ hay một API Java SE vẫn hợp lệ.

## 5. Không thay mọi package javax thành jakarta

Đây là lỗi chuyển đổi phổ biến. Chỉ những API thuộc Java EE/Jakarta EE được chuyển namespace mới cần đổi. Không phải mọi package bắt đầu bằng `javax.` đều đã trở thành `jakarta.`.

Ví dụ các package Java SE vẫn giữ nguyên:

| Package vẫn dùng | Vai trò |
|---|---|
| `javax.sql.DataSource` | JDBC datasource |
| `javax.crypto` | Cryptography |
| `javax.naming` | Naming và directory service |
| `javax.net` | Networking |
| `javax.management` | JMX management |
| `javax.xml.parsers` | XML parsing |
| `javax.annotation.processing` | Annotation processing của Java compiler |

Một số API Java EE khác có namespace mới, ví dụ:

| API cũ | Namespace Jakarta |
|---|---|
| `javax.persistence` | `jakarta.persistence` |
| `javax.transaction` (JTA) | `jakarta.transaction` |
| `javax.validation` | `jakarta.validation` |
| `javax.servlet` | `jakarta.servlet` |
| `javax.ws.rs` | `jakarta.ws.rs` |
| `javax.inject` | `jakarta.inject` |
| `javax.annotation` (Common Annotations API) | `jakarta.annotation` |

Cần phân biệt `javax.transaction.Transactional` của JTA với `org.springframework.transaction.annotation.Transactional` của Spring. Annotation Spring giữ nguyên package và vẫn dùng được trong ứng dụng Spring Boot 3. Không đổi annotation Spring thành một package Jakarta.

Tương tự, `javax.sql.DataSource` vẫn là API JDBC của Java SE. Không sửa import này thành `jakarta.sql.DataSource`, vì package đó không tồn tại.

Không chạy replace toàn project cho chuỗi `javax.` một cách mù quáng. Xác định API nào đã chuyển namespace, kiểm tra artifact cung cấp API và thay đổi đúng những import cần thiết.

## 6. Chuyển cấu hình persistence.xml và orm.xml

Spring Boot thường cấu hình persistence unit qua auto-configuration nên nhiều ứng dụng không có `persistence.xml`. Tuy nhiên, ứng dụng dùng JPA bootstrap thủ công hoặc mapping XML cần cập nhật namespace và version của descriptor.

Ví dụ `persistence.xml` theo Jakarta Persistence 3.1:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence
    xmlns="https://jakarta.ee/xml/ns/persistence"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        https://jakarta.ee/xml/ns/persistence
        https://jakarta.ee/xml/ns/persistence/persistence_3_1.xsd"
    version="3.1">

    <persistence-unit name="store">
        <provider>org.hibernate.jpa.HibernatePersistenceProvider</provider>
        <class>com.example.store.product.domain.Product</class>
    </persistence-unit>
</persistence>
```

Tên provider trong ví dụ là Hibernate. Nếu ứng dụng dùng provider khác, hãy khai báo provider tương ứng hoặc để cơ chế bootstrap chọn theo cấu hình.

Nếu có `orm.xml`, cần chuyển namespace và schema sang Jakarta Persistence tương ứng. Không giữ namespace XML JPA cũ chỉ vì source code đã đổi import.

Ngoài descriptor, rà soát các cấu hình property chuẩn có tiền tố cũ. Ví dụ các property JDBC và schema generation chuẩn có thể cần chuyển từ `javax.persistence.*` sang `jakarta.persistence.*` theo đặc tả mới. Các property bắt đầu bằng `hibernate.*` là property của Hibernate; không đổi tiền tố chúng theo quy tắc thay namespace JPA.

Với cấu hình Spring Boot dùng `spring.datasource.url`, `spring.datasource.username` và `spring.datasource.password`, các property này vẫn giữ nguyên. Chúng thuộc Spring Boot, không phải `javax.persistence`.

## 7. Cập nhật transaction và validation API đúng chỗ

Một số ứng dụng dùng thêm JTA hoặc Bean Validation bên cạnh JPA. Khi chuyển Jakarta EE, những import thuộc API này cũng có thể cần thay:

JTA:

```java
import jakarta.transaction.Transactional;
```

Bean Validation:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
```

Tuy nhiên, nếu ứng dụng dùng annotation transaction của Spring thì import vẫn là:

```java
import org.springframework.transaction.annotation.Transactional;
```

Spring Data JPA, Spring transaction và Spring validation có package riêng của Spring; không đổi chúng chỉ vì chuyển từ Java EE sang Jakarta EE.

Kiểm tra các constraint trên entity, DTO, request body và custom validator. Nếu dependency validation vẫn dùng API cũ, ứng dụng có thể gặp lỗi compile, không nhận annotation hoặc không chạy validation như mong đợi.

Ví dụ DTO dùng Jakarta Validation:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateProductRequest(
        @NotBlank
        @Size(max = 120)
        String name) {
}
```

Nếu dùng Spring MVC, hãy xác nhận starter validation và provider tương thích Jakarta được khai báo. Đừng chỉ đổi import mà bỏ quên dependency cung cấp implementation.

## 8. Kiểm tra Hibernate 5 lên Hibernate 6

Chuyển sang Jakarta thường đi kèm nâng Hibernate 5 lên 6. Đây là một bước nâng cấp riêng có thể tạo thay đổi ngoài namespace.

Một số khu vực cần đọc migration guide đúng phiên bản:

- Query HQL/JPQL và cách Hibernate 6 phân tích query.
- Custom type, `UserType`, `BasicType`, `TypeContributor` và JDBC type mapping.
- Dialect và cấu hình database-specific.
- ID generator, sequence và schema generation.
- SQL function, native query và result mapping.
- Fetching, collection semantics và cách loại trùng entity khi fetch join.
- Second-level cache và tích hợp cache provider.
- Logging, statistics và SPI nội bộ của Hibernate.

Ví dụ, custom type hoặc code trực tiếp dùng `org.hibernate.type.*` có thể cần thay đổi khi nâng Hibernate 6. Những API này vốn đã phụ thuộc provider, nên không thể chỉ thay package `javax` là đủ.

Không tự động thay tất cả class Hibernate cũ bằng class cùng tên gần giống. Đọc Javadoc và migration guide của đúng phiên bản đích, rồi kiểm thử từng tính năng custom đang sử dụng.

## 9. Chuyển repository Spring Data JPA

Repository thông thường giữ nguyên cấu trúc. Domain type vẫn là entity, nhưng entity phải dùng Jakarta annotation:

```java
import com.example.store.product.domain.Product;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
```

Derived query và các annotation Spring Data cũng giữ package của Spring Data:

```java
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Query("""
        select p
        from Product p
        where p.name like concat('%', :keyword, '%')
        """)
    List<Product> searchByName(
            @Param("keyword") String keyword);
}
```

Không đổi `org.springframework.data.jpa.repository.Query` thành `jakarta.persistence.Query`. Một bên là annotation khai báo query trên repository method; bên kia là interface query runtime của Jakarta Persistence.

Nếu custom repository implementation inject `EntityManager`, hãy đổi import sang `jakarta.persistence.EntityManager`. Các API `createQuery`, `createNativeQuery`, `flush`, `clear` và `find` vẫn là API chuẩn, nhưng dependency phải cung cấp đúng Jakarta type.

## 10. Quy trình chuyển đổi theo từng bước

Nên chuyển đổi trên branch riêng và thực hiện theo trình tự có thể kiểm tra:

1. **Ghi nhận baseline:** build hiện tại, Java version, Spring Boot, Spring Data JPA, Hibernate, database driver và thư viện custom.
2. **Chọn phiên bản đích:** dùng ma trận tương thích và dependency management của Spring Boot đích; xác nhận JDK tối thiểu.
3. **Nâng JDK và build tool:** với Spring Boot 3, chuyển runtime/build sang Java 17 trở lên và cập nhật Maven/Gradle plugin nếu cần.
4. **Nâng framework/provider đồng bộ:** cập nhật Spring Boot parent/plugin và starter; không giữ Spring Data JPA hoặc Hibernate cũ không tương thích.
5. **Chuyển source imports:** đổi các API Java EE đã chuyển namespace, đặc biệt `javax.persistence` sang `jakarta.persistence`.
6. **Cập nhật XML và property:** kiểm tra `persistence.xml`, `orm.xml`, persistence property và descriptor khác nếu ứng dụng có sử dụng.
7. **Rà soát thư viện nội bộ:** xác nhận module entity, repository custom, auditing, validation và integration library đã có bản Jakarta-compatible.
8. **Compile và sửa lỗi theo root cause:** xử lý import, method signature, SPI hoặc behavior thay đổi; tránh thêm cả hai API để làm build qua tạm thời.
9. **Chạy integration test:** xác minh entity scanning, repository bootstrap, persist/read/update/delete, transaction và migration.
10. **Kiểm tra SQL và triển khai thử:** xác nhận dialect, sequence, locking, query và connection pool trên database mục tiêu.

Với hệ thống lớn, có thể nâng theo module hoặc service. Tuy nhiên, ranh giới module phải thống nhất namespace: module chứa entity được ứng dụng Jakarta dùng phải cung cấp class đã biên dịch với Jakarta annotation, không phải artifact cũ dùng `javax.persistence`.

## 11. Tìm các tham chiếu javax còn sót

Dùng tìm kiếm source để phát hiện import cũ:

```bash
rg -n "javax\.persistence|javax\.transaction|javax\.validation|javax\.servlet" .
```

Sau đó phân loại từng kết quả:

- Import JPA cũ cần đổi sang Jakarta.
- Import JTA/Validation/Servlet cũ cần chuyển nếu ứng dụng đã nâng API tương ứng.
- Package Java SE như `javax.sql` hoặc `javax.crypto` cần giữ nguyên.
- Package từ thư viện khác cần đọc tài liệu của chính thư viện đó.

Kiểm tra cả XML và cấu hình:

```bash
rg -n "javax\.persistence|persistence_2|orm_2" src
```

Tìm kiếm không thay thế việc đọc dependency tree. Một thư viện bên thứ ba có thể đóng gói bytecode hoặc metadata tham chiếu API cũ mà source của ứng dụng không thể hiện. Hãy kiểm tra runtime dependency và nâng thư viện đó lên phiên bản hỗ trợ Jakarta.

## 12. Kiểm thử sau khi chuyển đổi

Tối thiểu cần có các nhóm kiểm tra:

**Khởi động context**

- Spring Boot context khởi động thành công.
- Hibernate provider khởi tạo được EntityManagerFactory.
- Repository được tạo và domain entity nằm trong JPA metamodel.
- Không còn lỗi `Not a managed type`, `NoClassDefFoundError` hoặc `ClassNotFoundException` do API cũ.

**Mapping và repository**

- Persist và đọc lại entity.
- Kiểm tra quan hệ `@OneToMany`, `@ManyToOne`, embedded ID, converter và inheritance.
- Kiểm tra derived query, JPQL, native query và projection.
- Kiểm tra lazy loading, fetch plan và pagination.

**Transaction và database**

- Xác nhận commit/rollback và propagation.
- Kiểm tra optimistic locking và sequence/identity.
- Chạy migration schema trên database mục tiêu.
- Kiểm tra native SQL và dialect-specific behavior.

**Tích hợp**

- Chạy integration test trên database thật hoặc Testcontainers khi behavior phụ thuộc dialect, locking, sequence hay JDBC type.
- Kiểm tra Flyway/Liquibase và dữ liệu migration.
- Kiểm tra cache, auditing, validation và serialization nếu ứng dụng sử dụng.

Không chỉ dựa vào unit test hoặc H2 nếu production dùng PostgreSQL/MySQL/Oracle. Database khác nhau có thể có behavior về sequence, JSON, timestamp, locking và SQL syntax khác nhau.

## 13. Lỗi thường gặp khi migration

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| `Not a managed type` | Entity vẫn dùng `javax.persistence.Entity` hoặc chưa được scan trong factory Jakarta. | Đổi annotation/import và xác minh metamodel. |
| `ClassNotFoundException: javax.persistence...` | Dependency hoặc thư viện cũ còn tham chiếu JPA API cũ. | Nâng thư viện, kiểm tra dependency tree và runtime classpath. |
| `NoClassDefFoundError: jakarta/persistence/...` | Thiếu Jakarta API tương thích hoặc dependency bị loại khỏi runtime. | Dùng starter/BOM phù hợp và kiểm tra runtime dependency. |
| Annotation validation không hoạt động | DTO/entity còn dùng `javax.validation` hoặc thiếu provider Jakarta Validation. | Chuyển import và cập nhật validation dependency. |
| Repository không khởi tạo | Spring Data JPA cũ không tương thích với Jakarta hoặc entity generic type không đúng. | Nâng Spring Data JPA đồng bộ với Spring Boot. |
| Hibernate query lỗi sau nâng cấp | HQL, custom type hoặc SPI thay đổi giữa Hibernate major versions. | Đọc migration guide và sửa query/API cụ thể. |
| XML mapping không được đọc | Descriptor còn namespace/schema cũ. | Cập nhật namespace và version Jakarta Persistence. |
| Lỗi compile sau replace toàn cục | Đã đổi nhầm API Java SE như `javax.sql`. | Phục hồi package Java SE và chỉ đổi API đã chuyển namespace. |

## 14. Checklist hoàn tất migration

- Spring Boot, Spring Framework, Spring Data JPA và Hibernate nằm trong nhóm version tương thích.
- JDK đạt yêu cầu của phiên bản Spring Boot đích.
- Entity, embeddable, converter, listener và EntityManager dùng `jakarta.persistence`.
- Không còn dependency JPA `javax.persistence-api` trong runtime.
- Không thay nhầm package Java SE như `javax.sql`, `javax.crypto`, `javax.naming`.
- Các API JTA, Validation, Servlet và Annotation được chuyển đúng phạm vi.
- `persistence.xml`, `orm.xml` và property chuẩn được cập nhật nếu có.
- Custom Hibernate extension đã được đối chiếu migration guide.
- Repository bootstrap và JPA metamodel được xác minh.
- Integration test chạy trên database phù hợp với production.
- Schema migration, transaction, query, locking và fetching đã được kiểm tra.

Chuyển từ `javax.persistence` sang `jakarta.persistence` là một thay đổi namespace có ảnh hưởng đến type identity và dependency compatibility. Thực hiện cùng nâng cấp framework/provider, chỉ chuyển đúng API đã đổi namespace và kiểm thử trên database mục tiêu sẽ giúp tránh lỗi khởi động cũng như sai khác runtime sau khi triển khai.