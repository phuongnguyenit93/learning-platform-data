# Metamodel tĩnh và giảm lỗi tên thuộc tính khi tái cấu trúc trong Spring Data JPA

JPA cung cấp **static metamodel** (canonical metamodel) để tham chiếu entity và thuộc tính bằng các trường Java có kiểu thay vì chuỗi tên thuộc tính. Các lớp metamodel thường được sinh tự động lúc biên dịch, có tên theo quy ước như `Product_`, `Category_`. Khi dùng với Criteria API hoặc Spring Data JPA `Specification`, ta có thể viết `root.get(Product_.name)` thay cho `root.get("name")`.

Lợi ích lớn nhất xuất hiện khi tái cấu trúc code: nếu đổi tên thuộc tính Java và annotation processor sinh lại metamodel, các tham chiếu `Product_.name` cũ sẽ không còn tồn tại và compiler báo lỗi. Nhờ vậy, nhiều lỗi gõ sai tên property hoặc quên cập nhật sau refactor được phát hiện sớm hơn.

Static metamodel không tự làm mọi truy vấn trong Spring Data JPA an toàn kiểu. Nó chủ yếu hỗ trợ Criteria API và các đoạn code dùng metamodel; chuỗi trong `@Query`, native SQL, `Sort.by("...")` và nhiều API cấu hình khác vẫn có thể phụ thuộc tên dạng String.

Tài liệu dùng Jakarta Persistence (`jakarta.persistence`) trong Spring Boot 3 trở lên. Dự án Spring Boot 2/Hibernate 5 cũ thường dùng namespace `javax.persistence` và artifact annotation processor khác group.

## 1. Metamodel là gì?

Metamodel mô tả cấu trúc persistence model của ứng dụng: entity, embeddable, thuộc tính đơn, quan hệ và collection. JPA có hai cách tiếp cận liên quan:

- **Runtime metamodel:** provider cung cấp qua `EntityManagerFactory.getMetamodel()` hoặc `EntityManager.getMetamodel()`. Có thể tra cứu entity và attribute khi ứng dụng chạy.
- **Static/canonical metamodel:** các lớp Java được sinh ở compile time, ví dụ `Product_`, cho phép tham chiếu attribute bằng kiểu Java và được compiler kiểm tra.

Ví dụ runtime metamodel:

```java
EntityType<Product> productType =
    entityManager.getMetamodel().entity(Product.class);

Attribute<? super Product, ?> nameAttribute =
    productType.getAttribute("name");
```

Cách này vẫn dùng tên String và chỉ kiểm tra lúc chạy. Static metamodel cho phép viết:

```java
SingularAttribute<Product, String> nameAttribute = Product_.name;
```

Tên `Product_` là quy ước phổ biến cho canonical metamodel class của entity Product. Lớp này thường nằm cùng package với entity và được sinh bởi annotation processor; lập trình viên không nên tự sửa file generated.

## 2. Entity và lớp metamodel được sinh

Entity ví dụ:

```java
package com.example.catalog;

import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "product")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    @Column(precision = 19, scale = 2)
    private BigDecimal price;

    private boolean active;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "category_id")
    private Category category;

    protected Product() {
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

    public boolean isActive() {
        return active;
    }

    public Category getCategory() {
        return category;
    }
}
```

Sau khi annotation processor chạy, lớp metamodel được sinh theo cấu trúc tương tự:

```java
package com.example.catalog;

import jakarta.persistence.metamodel.SingularAttribute;
import jakarta.persistence.metamodel.StaticMetamodel;

@StaticMetamodel(Product.class)
public abstract class Product_ {

    public static volatile SingularAttribute<Product, Long> id;
    public static volatile SingularAttribute<Product, String> name;
    public static volatile SingularAttribute<Product, BigDecimal> price;
    public static volatile SingularAttribute<Product, Boolean> active;
    public static volatile SingularAttribute<Product, Category> category;
}
```

Đây là hình dạng minh họa để hiểu API. File thực tế do processor tạo; nội dung, annotation `@Generated`, import và modifier có thể khác theo phiên bản processor.

Một số điểm cần chú ý:

- Thuộc tính entity đơn được biểu diễn bằng `SingularAttribute`.
- Field primitive như `boolean` thường được biểu diễn bằng wrapper type tương ứng trong metamodel, ở đây là `Boolean`.
- Quan hệ to-one như category cũng là singular attribute.
- Metamodel field thường là `public static volatile`; provider khởi tạo metadata khi persistence unit được bootstrap.
- Không tạo hoặc sửa `Product_` thủ công; thay đổi entity rồi để processor sinh lại.

## 3. Các loại attribute trong static metamodel

JPA có các kiểu metamodel tương ứng với dạng thuộc tính:

| Loại thuộc tính trong entity | Kiểu metamodel |
|---|---|
| Thuộc tính đơn, basic hoặc to-one | `SingularAttribute<X, Y>` |
| `Collection<T>` | `CollectionAttribute<X, T>` |
| `Set<T>` | `SetAttribute<X, T>` |
| `List<T>` | `ListAttribute<X, T>` |
| `Map<K, V>` | `MapAttribute<X, K, V>` |

Ví dụ entity có collection:

```java
@Entity
public class Product {

    @Id
    private Long id;

    @ElementCollection
    private Set<String> labels;

    @ManyToMany
    private Set<Tag> tags;
}
```

Metamodel tương ứng có thể chứa:

```java
public static volatile SingularAttribute<Product, Long> id;
public static volatile SetAttribute<Product, String> labels;
public static volatile SetAttribute<Product, Tag> tags;
```

Với `@Embedded`, processor cũng sinh metamodel cho embeddable:

```java
@Embeddable
public class Address {
    private String city;
    private String postalCode;
}

@Entity
public class Customer {
    @Id
    private Long id;

    @Embedded
    private Address address;
}
```

Các thuộc tính có thể được truy cập theo đường dẫn kiểu:

```java
root.get(Customer_.address).get(Address_.city)
```

Với entity kế thừa, metamodel class của entity con có thể kế thừa metamodel class của superclass tương ứng. Điều này giúp thuộc tính được khai báo ở mapped superclass hoặc entity cha tiếp tục có thể truy cập trong Criteria API.

## 4. Cấu hình annotation processor

Static metamodel không được tạo tự động chỉ vì project có dependency Spring Data JPA. Cần bật annotation processor trong build để sinh các lớp `*_ ` theo mô hình entity.

Hibernate cung cấp JPA metamodel generator. Chọn artifact cùng dòng/version với Hibernate ORM đang được Spring Boot quản lý.

### 4.1. Maven

Ví dụ với Hibernate ORM 6/7, artifact processor có group `org.hibernate.orm`:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <annotationProcessorPaths>
                    <path>
                        <groupId>org.hibernate.orm</groupId>
                        <artifactId>hibernate-jpamodelgen</artifactId>
                        <version>${hibernate.version}</version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
```

`hibernate.version` trong ví dụ phải trỏ tới phiên bản Hibernate ORM tương thích với provider của ứng dụng. Nếu Spring Boot BOM đang quản lý version, hãy dùng đúng version được BOM quản lý hoặc khai báo property dự án một cách nhất quán; không chọn ngẫu nhiên version mới hơn cho processor.

Với Hibernate 5, artifact thường dùng group cũ `org.hibernate`:

```xml
<path>
    <groupId>org.hibernate</groupId>
    <artifactId>hibernate-jpamodelgen</artifactId>
    <version>${hibernate.version}</version>
</path>
```

Không dùng nhầm group của Hibernate 5 trong project Hibernate 6/7. Nếu dùng EclipseLink hoặc provider khác, hãy dùng annotation processor tương ứng với provider đó.

### 4.2. Gradle

Với Gradle, khai báo processor trong configuration `annotationProcessor`:

```groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-jpa")

    annotationProcessor(
        "org.hibernate.orm:hibernate-jpamodelgen:${hibernateVersion}"
    )
}
```

`hibernateVersion` phải khớp dòng Hibernate ORM được ứng dụng sử dụng. Trong project dùng version catalog hoặc Spring Boot dependency management, lấy version theo cấu hình tập trung của dự án thay vì hard-code nhiều nơi.

Khi processor được cấu hình đúng, Gradle tạo source generated trong thư mục build, thường nằm dưới `build/generated/sources/annotationProcessor/java/main`. Maven thường tạo dưới `target/generated-sources/annotations`.

### 4.3. Kiểm tra generated source

Chạy clean compile:

```bash
# Maven
./mvnw clean compile

# Gradle
./gradlew clean compileJava
```

Sau đó kiểm tra lớp `Product_` đã được sinh và IDE nhận generated source. Nếu compiler báo không tìm thấy `Product_`:

1. Kiểm tra annotation processor dependency và đúng group/version.
2. Kiểm tra Maven Compiler Plugin hoặc Gradle annotationProcessor configuration.
3. Chạy clean compile để tránh dùng generated source cũ.
4. Reimport project trong IDE và bật annotation processing nếu IDE yêu cầu.
5. Kiểm tra entity có được nhận diện là managed type và dùng đúng Jakarta/Javax namespace.

Không tạo một `Product_` giả để làm hết lỗi compile; việc đó che giấu processor chưa chạy và có thể làm metadata không đồng bộ entity.

## 5. Dùng metamodel trong Criteria API

Criteria API xây dựng truy vấn bằng object và expression thay vì ghép chuỗi JPQL. Khi dùng static metamodel, các path được kiểm tra kiểu lúc compile.

Ví dụ query theo tên:

```java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();

CriteriaQuery<Product> cq = cb.createQuery(Product.class);
Root<Product> product = cq.from(Product.class);

cq.select(product)
  .where(cb.equal(product.get(Product_.name), "Tea"));

List<Product> results =
    entityManager.createQuery(cq).getResultList();
```

So sánh hai cách:

```java
product.get("name")       // String path, dễ gõ sai
product.get(Product_.name) // Typed path, compiler kiểm tra
```

Nếu viết `product.get("naem")`, compiler vẫn chấp nhận vì đó là String; lỗi chỉ có thể xuất hiện khi query được xử lý. Nếu viết `product.get(Product_.naem)`, compiler báo không tìm thấy field `naem` trong Product_.

Đây là lợi ích cốt lõi của static metamodel.

## 6. Dùng metamodel với nhiều predicate

Ví dụ xây query tìm sản phẩm theo các filter tùy chọn:

```java
public List<Product> search(
        EntityManager entityManager,
        String name,
        BigDecimal minimumPrice,
        Boolean active) {

    CriteriaBuilder cb = entityManager.getCriteriaBuilder();
    CriteriaQuery<Product> cq = cb.createQuery(Product.class);
    Root<Product> product = cq.from(Product.class);

    List<Predicate> predicates = new ArrayList<>();

    if (name != null && !name.isBlank()) {
        predicates.add(
            cb.like(
                cb.lower(product.get(Product_.name)),
                "%" + name.toLowerCase(Locale.ROOT) + "%"
            )
        );
    }

    if (minimumPrice != null) {
        predicates.add(
            cb.greaterThanOrEqualTo(
                product.get(Product_.price),
                minimumPrice
            )
        );
    }

    if (active != null) {
        predicates.add(
            cb.equal(product.get(Product_.active), active)
        );
    }

    cq.select(product)
      .where(cb.and(predicates.toArray(Predicate[]::new)))
      .orderBy(
          cb.asc(product.get(Product_.name)),
          cb.desc(product.get(Product_.id))
      );

    return entityManager.createQuery(cq).getResultList();
}
```

Đây là method minh họa cần import `jakarta.persistence.criteria.*`, `java.util.*`, `java.math.BigDecimal`, `java.util.Locale` và entity đã mapping. Các property path đều dùng static metamodel. Nếu không có predicate nào, `cb.and(emptyArray)` có semantics conjunction đúng (true), nên truy vấn trả tất cả hàng phù hợp với phần còn lại.

Với dữ liệu lớn, kiểm tra index và execution plan cho các điều kiện LIKE/price/order. Static metamodel giúp kiểm tra tên và kiểu property; nó không tự tối ưu SQL.

## 7. Dùng metamodel với association và JOIN

Giả sử Product có quan hệ many-to-one tới Category. Có thể join bằng metamodel:

```java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();
CriteriaQuery<Product> cq = cb.createQuery(Product.class);
Root<Product> product = cq.from(Product.class);

Join<Product, Category> category =
    product.join(Product_.category, JoinType.INNER);

cq.select(product)
  .where(cb.equal(category.get(Category_.name), "Books"));

List<Product> results =
    entityManager.createQuery(cq).getResultList();
```

Các điểm quan trọng:

- `Product_.category` xác định association từ Product sang Category.
- `Category_.name` xác định thuộc tính name của Category.
- Đổi tên property `category` hoặc `name` sẽ khiến tham chiếu metamodel cũ không compile sau khi processor chạy lại.
- Join type vẫn là quyết định nghiệp vụ: INNER loại Product không có Category phù hợp; LEFT có thể giữ Product không có Category.

Truy cập thuộc tính to-one mà không khai báo join tường minh cũng có thể dùng typed path:

```java
Path<String> categoryName =
    product.get(Product_.category).get(Category_.name);
```

Với collection-valued association, dùng join phù hợp với loại attribute, ví dụ `root.join(Product_.tags)`. Cẩn thận cardinality khi join collection vì một entity cha có thể xuất hiện nhiều hàng trong kết quả SQL; có thể cần DISTINCT hoặc EXISTS theo ý nghĩa truy vấn.

## 8. Static metamodel trong Spring Data JPA Specification

`Specification<T>` của Spring Data JPA dùng Criteria API để tạo predicate có thể kết hợp. Static metamodel giúp Specification tránh tên property dạng String.

Repository:

```java
public interface ProductRepository
        extends JpaRepository<Product, Long>,
                JpaSpecificationExecutor<Product> {
}
```

Specification theo tên:

```java
public final class ProductSpecifications {

    private ProductSpecifications() {
    }

    public static Specification<Product> nameContains(String name) {
        return (root, query, cb) -> {
            if (name == null || name.isBlank()) {
                return cb.conjunction();
            }

            String pattern =
                "%" + name.toLowerCase(Locale.ROOT) + "%";

            return cb.like(
                cb.lower(root.get(Product_.name)),
                pattern
            );
        };
    }

    public static Specification<Product> minimumPrice(
            BigDecimal minimumPrice) {
        return (root, query, cb) -> {
            if (minimumPrice == null) {
                return cb.conjunction();
            }

            return cb.greaterThanOrEqualTo(
                root.get(Product_.price),
                minimumPrice
            );
        };
    }
}
```

Kết hợp:

```java
Specification<Product> specification =
    ProductSpecifications.nameContains("tea")
        .and(ProductSpecifications.minimumPrice(
            new BigDecimal("10.00")
        ));

Page<Product> page = productRepository.findAll(
    specification,
    PageRequest.of(0, 20)
);
```

Mỗi Specification tạo một predicate độc lập. Có thể ghép bằng `and()`, `or()` và `not()` theo logic nghiệp vụ. Vì các path dùng `Product_.name` và `Product_.price`, đổi tên property sẽ được compiler phát hiện sau khi metamodel sinh lại.

Không thêm fetch join collection vào Specification dùng chung cho cả query dữ liệu và count query một cách tùy tiện. Spring Data có thể thực thi Specification trong count query; fetch join collection ở đó có thể gây lỗi hoặc count sai. Nếu cần tải association, cân nhắc EntityGraph, projection hoặc thiết kế query riêng.

## 9. Metamodel cho mapped superclass và kế thừa

Nếu nhiều entity chia sẻ thuộc tính từ mapped superclass:

```java
@MappedSuperclass
public abstract class AuditedEntity {

    @Id
    private Long id;

    private Instant createdAt;
}
```

Entity con:

```java
@Entity
public class Product extends AuditedEntity {
    private String name;
}
```

Processor có thể sinh `AuditedEntity_` và `Product_`, trong đó metamodel entity con kế thừa metamodel superclass. Có thể dùng thuộc tính được kế thừa trong Criteria:

```java
root.get(Product_.createdAt)
```

Tên field static có thể được kế thừa từ superclass metamodel theo cấu trúc Java. Hãy dùng lớp generated thực tế do processor tạo và không khai báo lại thuộc tính kế thừa trong metamodel thủ công.

Với inheritance entity như `SINGLE_TABLE` hoặc `JOINED`, processor cũng tạo metamodel tương ứng cho các entity trong hierarchy. Việc truy cập thuộc tính subtype có thể cần `CriteriaBuilder.treat(...)` khi root đang có kiểu cha; không ép cast Java thông thường để thay thế type narrowing của Criteria API.

## 10. Refactor an toàn khi đổi tên thuộc tính

Giả sử entity ban đầu có:

```java
private String name;
```

Criteria query dùng:

```java
root.get(Product_.name)
```

Sau khi đổi tên thuộc tính thành `displayName` bằng IDE refactor:

1. Entity chuyển sang `displayName`.
2. Annotation processor sinh lại `Product_.displayName`.
3. `Product_.name` không còn tồn tại.
4. Compiler báo lỗi tại các Criteria query còn tham chiếu field cũ.
5. Developer sửa query sang `Product_.displayName` rồi build lại.

Nếu dùng chuỗi:

```java
root.get("name")
```

Compiler không biết đó là property của Product. Build có thể vẫn thành công dù entity đã đổi tên; lỗi chỉ xuất hiện lúc query được tạo hoặc chạy.

Đây là lý do static metamodel đặc biệt hữu ích trong codebase có nhiều Specification/Criteria query và thường xuyên refactor domain model.

Tuy nhiên, hãy chạy clean build sau refactor. Nếu generated source cũ còn sót lại, compiler/IDE có thể tạm thời nhìn thấy một metamodel không còn phản ánh entity mới.

## 11. Những nơi static metamodel không tự bảo vệ

Static metamodel không thay thế toàn bộ type safety của Spring Data JPA. Một số API vẫn nhận String:

| API/cách viết | Ví dụ | Mức bảo vệ |
|---|---|---|
| Criteria API với static metamodel | `root.get(Product_.name)` | Compile-time typed path |
| Criteria API với String | `root.get("name")` | Chỉ kiểm tra lúc chạy |
| JPQL trong `@Query` | `where p.name = :name` | Query string, thường xác thực lúc khởi tạo/chạy |
| Native SQL | `select name from product` | Phụ thuộc schema/database |
| Spring Data Sort | `Sort.by("name")` | Property string, được kiểm tra lúc chạy |
| EntityGraph attributePaths | `attributePaths = {"category"}` | String path |
| `@OrderBy` và nhiều annotation mapping | `@OrderBy("name ASC")` | String expression |

Vì vậy, static metamodel nên được dùng ở nơi nó mang lại giá trị rõ ràng, đặc biệt Criteria API và Specification. Với query string, hãy dùng named parameter, test integration và giữ property path đồng bộ khi refactor.

Spring Data có `TypedSort` ở một số phiên bản để tạo sort từ method reference, nhưng đây là cơ chế riêng, không phải static JPA metamodel. Kiểm tra API/version của Spring Data đang dùng nếu muốn type-safe sort.

## 12. Runtime injection và thời điểm sử dụng

Các field trong generated metamodel được provider khởi tạo trong quá trình bootstrap persistence unit. Vì vậy:

- Dùng `Product_.name` trong Criteria query sau khi EntityManagerFactory đã được tạo.
- Không đọc giá trị metadata static quá sớm trong static initializer của một class tùy ý trước khi JPA bootstrap.
- Không tự gán `Product_.name` bằng một object attribute giả.
- Không coi `Product_` là DTO hoặc entity; đây là metadata class.

Trong Spring Boot, repository/service được gọi sau khi application context và EntityManagerFactory khởi tạo nên thường có thể dùng metamodel bình thường. Nếu tự tạo static utility hoặc chạy test trước khi persistence provider bootstrap, chú ý thứ tự khởi tạo.

## 13. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không tìm thấy class `Product_` | Annotation processor chưa chạy hoặc IDE chưa nhận generated source | Kiểm tra processor dependency, build config, clean compile và IDE |
| Metamodel thiếu property | Entity không được processor nhận diện, access type hoặc namespace sai | Kiểm tra `@Entity`, `@MappedSuperclass`, `@Embeddable`, Jakarta/Javax và processor version |
| Compile báo `Product_.name` không tồn tại sau refactor | Generated metamodel đã đổi theo entity mới | Cập nhật Criteria/Specification sang property mới |
| Build command line thành công nhưng IDE báo lỗi | IDE chưa import annotation processor output | Reimport Maven/Gradle và bật annotation processing nếu cần |
| Dùng sai loại attribute cho join | Nhầm SingularAttribute với Set/List/Map attribute | Xem generated class và dùng overload Criteria phù hợp |
| Runtime báo metamodel field null | Provider chưa bootstrap hoặc generated metadata không được provider nhận diện | Kiểm tra persistence unit scan, annotation và provider |
| Criteria query vẫn sai nghiệp vụ | Typed path chỉ bảo vệ tên/kiểu, không xác nhận logic predicate | Viết integration test cho kết quả |
| Query JPQL không được bảo vệ khi đổi tên | Chuỗi `@Query` vẫn dùng tên property cũ | Tìm toàn bộ query string và cập nhật/test sau refactor |
| Build giữ generated source cũ | Không clean hoặc generated source được commit không đồng bộ | Clean build; tuân theo chính sách generated code của dự án |

## 14. Kiểm thử Criteria/Specification

Nên kiểm thử trên JPA provider và database phù hợp với production. Một test repository có thể xác nhận Specification lọc đúng:

```java
@DataJpaTest
class ProductSpecificationTest {

    @Autowired
    private ProductRepository repository;

    @Test
    void filtersByMinimumPrice() {
        repository.save(new Product("Tea", new BigDecimal("5.00")));
        repository.save(new Product("Coffee", new BigDecimal("15.00")));
        repository.flush();

        Specification<Product> specification =
            ProductSpecifications.minimumPrice(
                new BigDecimal("10.00")
            );

        List<Product> results =
            repository.findAll(specification);

        assertThat(results)
            .extracting(Product::getName)
            .containsExactly("Coffee");
    }
}
```

Đây là ví dụ test minh họa; entity constructor, getters, imports và fixture phải khớp project thực tế. `@DataJpaTest` cần Spring Boot test dependency và cấu hình database test. Test này xác minh ngữ nghĩa truy vấn; việc static metamodel compile thành công được xác minh qua build compile.

Các kiểm tra nên có:

- Clean compile sinh đủ metamodel cho entity, mapped superclass và embeddable.
- Criteria query dùng typed path cho thuộc tính đơn và association.
- Specification kết hợp AND/OR trả đúng kết quả.
- Đổi tên một property khiến tham chiếu static cũ lỗi compile.
- Collection join không tạo kết quả trùng ngoài ý muốn.
- Count query của Page vẫn đúng nếu Specification được dùng cho phân trang.
- JPQL/native query string vẫn được kiểm tra riêng vì static metamodel không bảo vệ chúng.

## 15. Checklist áp dụng static metamodel

- [ ] Project đã khai báo annotation processor tương thích Hibernate/provider?
- [ ] Version processor khớp dòng ORM runtime?
- [ ] Maven/Gradle build sinh được các lớp `*_ `?
- [ ] IDE đã nhận generated source?
- [ ] Không sửa file metamodel generated thủ công?
- [ ] Criteria API dùng `Product_.attribute` thay cho String khi có thể?
- [ ] Join dùng đúng SingularAttribute/PluralAttribute?
- [ ] Mapped superclass/embeddable có metamodel được sinh?
- [ ] Clean build được chạy sau khi đổi tên property?
- [ ] Các chuỗi `@Query`, native SQL, Sort và EntityGraph được kiểm tra riêng?
- [ ] Integration test xác minh logic truy vấn, không chỉ compile?
- [ ] Generated source được quản lý theo chính sách build/version control của dự án?

## 16. Kết luận

Static metamodel tạo ra lớp metadata Java như `Product_` với các attribute có kiểu. Khi dùng `root.get(Product_.name)`, compiler có thể phát hiện property không tồn tại hoặc sai tên sau khi entity được refactor và metamodel được sinh lại. Đây là lợi ích lớn so với `root.get("name")` trong Criteria API.

Để sử dụng, cần cấu hình annotation processor đúng provider/version, chạy clean build và để processor quản lý generated source. Kết hợp static metamodel với Criteria API và Spring Data JPA Specification để tạo predicate, join và path có kiểu. Hãy nhớ rằng `@Query`, native SQL, Sort dạng String và các API attribute path dạng chuỗi vẫn cần được kiểm tra riêng. Static metamodel giảm lỗi tên thuộc tính trong phần code được typed; nó không thay thế integration test hay kiểm tra hiệu năng truy vấn.
