# Tạo repository ngoài ApplicationContext bằng factory phù hợp

## 1. Repository không bắt buộc phải được lấy từ ApplicationContext

Trong ứng dụng Spring thông thường, repository được phát hiện, đăng ký thành bean rồi inject vào service. Nhưng đó không phải con đường duy nhất để sử dụng repository abstraction.

Một chương trình Java độc lập có thể tự:

1. Chuẩn bị hạ tầng truy cập dữ liệu.
2. Tạo factory dành cho store.
3. Yêu cầu factory tạo repository proxy từ interface cụ thể.
4. Gọi repository trong vòng đời tài nguyên và transaction do chương trình quản lý.

Cách này hữu ích cho một công cụ nhập dữ liệu nhỏ, một chương trình thử nghiệm tập trung hoặc một tình huống tích hợp không khởi tạo Spring ApplicationContext.

Trong module **SPRING_DATA_COMMONS**, cần phân biệt hạ tầng tạo repository dùng chung với các factory tích hợp theo store. Các hợp đồng CRUD, derived query, phân trang và projection vẫn có thể được sử dụng khi điều kiện tương ứng được chuẩn bị đầy đủ.

Không tạo ApplicationContext không có nghĩa là không dùng thư viện Spring. Factory và repository vẫn là thành phần Spring Data cùng các dependency cần thiết.

## 2. Từ interface đến repository proxy

### 2.1. Factory dùng chung và factory theo store

Commons cung cấp lớp nền:

```java
org.springframework.data.repository.core.support.RepositoryFactorySupport
```

Đây là abstraction cho việc tạo repository. Bạn sử dụng một factory cụ thể có khả năng làm việc với store đã chọn.

| Store hoặc mô hình | Factory tiêu biểu | Hạ tầng đầu vào |
| --- | --- | --- |
| JPA | `JpaRepositoryFactory` | `EntityManager` |
| MongoDB đồng bộ | `MongoRepositoryFactory` | `MongoOperations`, thường qua MongoTemplate |
| MongoDB reactive | `ReactiveMongoRepositoryFactory` | Hạ tầng MongoDB reactive tương ứng |

Các factory thuộc module của store. Việc thêm spring-data-commons không tự cung cấp toàn bộ chúng hoặc tạo kết nối đến cơ sở dữ liệu.

Constructor, tùy chọn và mức hỗ trợ phải được đối chiếu với phiên bản đang dùng. Các ví dụ chính trong bài dùng nhánh JPA với `jakarta.persistence`.

### 2.2. Ba dòng cốt lõi với JPA

```java
JpaRepositoryFactory factory =
        new JpaRepositoryFactory(entityManager);

ProductRepository products =
        factory.getRepository(ProductRepository.class);
```

Ở đây:

- EntityManager đã tồn tại và có mapping domain phù hợp.
- ProductRepository là interface cụ thể, đã đóng kiểu domain và ID.
- Factory tạo một proxy thực hiện interface đó.
- Proxy phối hợp implementation cơ sở, hạ tầng truy vấn và các phần mở rộng được cấu hình.

Bạn không gọi `new ProductRepository()`. Interface không phải class có thể khởi tạo trực tiếp.

### 2.3. Điều factory không tự tạo từ ba dòng trên

Đoạn code chưa:

- Tạo EntityManagerFactory hoặc kết nối.
- Khai báo entity mapping.
- Bắt đầu một transaction.
- Tìm mọi repository trong package.
- Tự inject các bean của ứng dụng.
- Tự đóng tài nguyên sau khi dùng.
- Tái hiện toàn bộ cấu hình mà một repository bean trong ứng dụng Spring có thể nhận.

Có repository proxy là một bước quan trọng, nhưng chưa phải toàn bộ môi trường thực thi.

## 3. Phân biệt RepositoryFactory và FactoryBean

Trong cấu hình dựa vào Spring container, bạn có thể gặp một FactoryBean của store, chẳng hạn JpaRepositoryFactoryBean.

| Thành phần | Vai trò |
| --- | --- |
| Repository factory | Tạo repository proxy bằng hạ tầng store đã được cung cấp |
| Repository FactoryBean | Tích hợp việc tạo repository vào vòng đời và cấu hình bean của Spring |
| Repository scanning | Phát hiện các interface cần đăng ký |
| ApplicationContext | Quản lý bean và phối hợp các thành phần ứng dụng |

Khi tạo repository độc lập, thường bắt đầu trực tiếp từ factory của store. Không cần khởi tạo một FactoryBean rồi giả định mọi callback, BeanFactory hoặc post-processor đã tự xuất hiện.

Các annotation kích hoạt như `@EnableJpaRepositories` chỉ có tác dụng khi được cơ chế cấu hình Spring xử lý. Đặt annotation lên một class rồi chạy main không tự tạo context hoặc quét repository.

## 4. Chuẩn bị ví dụ JPA độc lập

### 4.1. Dependency cần có

Một cấu hình Maven minh họa gồm:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.data</groupId>
        <artifactId>spring-data-jpa</artifactId>
    </dependency>

    <dependency>
        <groupId>jakarta.persistence</groupId>
        <artifactId>jakarta.persistence-api</artifactId>
    </dependency>

    <dependency>
        <groupId>org.hibernate.orm</groupId>
        <artifactId>hibernate-core</artifactId>
    </dependency>

    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Đoạn dependency giả định dự án đã có dependency management tương thích hoặc bổ sung version phù hợp cho từng artifact. Chọn đồng bộ Spring Data JPA, Commons, Spring Framework, JPA API, Hibernate và JDK.

Spring Data BOM quản lý các module Spring Data trong phạm vi của nó; không mặc định BOM đó quản lý luôn mọi provider, driver và thư viện khác trong ví dụ.

Không cần Spring Boot để gọi factory. Nếu dùng dependency management của Boot để quản lý phiên bản, việc đó cũng không bắt buộc chương trình phải chạy SpringApplication hoặc tạo ApplicationContext.

### 4.2. Cấu trúc ví dụ

```text
src/main/java/example/standalone/
    Product.java
    ProductRepository.java
    StandaloneRepositoryDemo.java

src/main/resources/META-INF/
    persistence.xml
```

Mỗi public type nằm trong tệp riêng. Các đoạn dưới dùng package example.standalone.

Phần cấu hình chỉ dùng cơ sở dữ liệu H2 trong bộ nhớ, dành cho chương trình thử nghiệm. Không dùng cấu hình tạo/xóa schema này cho một cơ sở dữ liệu đang lưu dữ liệu nghiệp vụ.

## 5. Entity và repository cụ thể

### 5.1. Product

```java
package example.standalone;

import java.math.BigDecimal;

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

    @Column(nullable = false, unique = true)
    private String sku;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false, precision = 14, scale = 2)
    private BigDecimal price;

    @Column(nullable = false)
    private boolean active;

    protected Product() {
    }

    public Product(
            String sku,
            String name,
            BigDecimal price,
            boolean active
    ) {
        this.sku = sku;
        this.name = name;
        this.price = price;
        this.active = active;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
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
}
```

Field access được chọn thông qua vị trí annotation mapping trên các field. Không cần setter cho các phép đọc của ví dụ này.

### 5.2. ProductRepository

```java
package example.standalone;

import java.util.List;
import java.util.Optional;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository
        extends JpaRepository<Product, Long> {

    Optional<Product> findBySku(String sku);

    List<Product> findByActiveTrueOrderByPriceAscSkuAsc();

    Page<Product> findByActiveTrue(Pageable pageable);
}
```

Không cần đặt `@Repository` lên interface để gọi `getRepository` trực tiếp. Bạn đã truyền chính interface cần tạo cho factory.

Repository phải gắn với domain cụ thể. Một base generic có `@NoRepositoryBean` là hợp đồng trung gian; nó không phải lựa chọn thay thế cho ProductRepository trong lời gọi getRepository.

`@NoRepositoryBean` chủ yếu tham gia quy trình phát hiện repository. Trong cách tạo trực tiếp, trách nhiệm chọn đúng interface thuộc về code gọi factory.

## 6. Khai báo persistence unit

Đặt nội dung sau trong META-INF/persistence.xml của chương trình ví dụ:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence
        xmlns="https://jakarta.ee/xml/ns/persistence"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xsi:schemaLocation="
            https://jakarta.ee/xml/ns/persistence
            https://jakarta.ee/xml/ns/persistence/persistence_3_0.xsd"
        version="3.0">

    <persistence-unit
            name="standalone-repository"
            transaction-type="RESOURCE_LOCAL">

        <provider>
            org.hibernate.jpa.HibernatePersistenceProvider
        </provider>

        <class>example.standalone.Product</class>

        <exclude-unlisted-classes>true</exclude-unlisted-classes>

        <properties>
            <property
                    name="jakarta.persistence.jdbc.driver"
                    value="org.h2.Driver"/>
            <property
                    name="jakarta.persistence.jdbc.url"
                    value="jdbc:h2:mem:repository_factory_demo"/>
            <property
                    name="jakarta.persistence.jdbc.user"
                    value="sa"/>
            <property
                    name="jakarta.persistence.jdbc.password"
                    value=""/>

            <property
                    name="hibernate.hbm2ddl.auto"
                    value="create-drop"/>
            <property
                    name="hibernate.show_sql"
                    value="true"/>
            <property
                    name="hibernate.format_sql"
                    value="true"/>
        </properties>
    </persistence-unit>
</persistence>
```

Tên persistence unit phải khớp chuỗi truyền cho Persistence.createEntityManagerFactory.

Entity được liệt kê rõ, không dựa vào component scanning. Provider, JDBC driver và resource cấu hình phải nằm trên classpath của chương trình.

Các thuộc tính `spring.datasource.*` hoặc `spring.jpa.*` trong một file cấu hình Boot không tự được JPA bootstrap chuẩn này xử lý. Ở đây dùng thuộc tính Jakarta Persistence và Hibernate mà bootstrap tương ứng hiểu.

## 7. Chương trình main tạo và sử dụng repository

Các đoạn Java của ví dụ dùng Java 17 trở lên và tập thư viện tương thích với nhánh Jakarta Persistence đã chọn.

```java
package example.standalone;

import java.math.BigDecimal;
import java.util.List;

import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;
import jakarta.persistence.Persistence;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.repository.support.JpaRepositoryFactory;

public class StandaloneRepositoryDemo {

    public static void main(String[] args) {
        EntityManagerFactory emf =
                Persistence.createEntityManagerFactory(
                        "standalone-repository"
                );

        try {
            EntityManager em = emf.createEntityManager();

            try {
                runExample(em);
            } finally {
                em.close();
            }
        } finally {
            emf.close();
        }
    }

    private static void runExample(EntityManager em) {
        JpaRepositoryFactory factory =
                new JpaRepositoryFactory(em);

        ProductRepository products =
                factory.getRepository(ProductRepository.class);

        EntityTransaction tx = em.getTransaction();

        try {
            tx.begin();

            List<Product> saved = products.saveAll(List.of(
                    new Product(
                            "KEY-001",
                            "Bàn phím cơ",
                            new BigDecimal("1200000"),
                            true
                    ),
                    new Product(
                            "MOU-001",
                            "Chuột không dây",
                            new BigDecimal("450000"),
                            true
                    ),
                    new Product(
                            "MON-001",
                            "Màn hình 24 inch",
                            new BigDecimal("3500000"),
                            false
                    )
            ));

            tx.commit();

            System.out.println(
                    "Đã lưu: " + saved.size() + " sản phẩm"
            );

            em.clear();

            tx.begin();

            List<Product> active =
                    products
                        .findByActiveTrueOrderByPriceAscSkuAsc();

            PageRequest request = PageRequest.of(
                    0,
                    1,
                    Sort.by("price").ascending()
                        .and(Sort.by("sku").ascending())
            );

            Page<Product> firstPage =
                    products.findByActiveTrue(request);

            System.out.println(
                    "SKU đang hoạt động: "
                            + active.stream()
                                .map(Product::getSku)
                                .toList()
            );

            System.out.println(
                    "Trang đầu: "
                            + firstPage.getContent().stream()
                                .map(Product::getSku)
                                .toList()
            );

            System.out.println(
                    "Tổng đang hoạt động: "
                            + firstPage.getTotalElements()
            );

            tx.commit();
        } catch (RuntimeException failure) {
            if (tx.isActive()) {
                try {
                    tx.rollback();
                } catch (RuntimeException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
            }

            throw failure;
        }
    }
}
```

### 7.1. Luồng tài nguyên

```text
Tạo EntityManagerFactory
    |
    +-- Tạo EntityManager
    |      |
    |      +-- Tạo JpaRepositoryFactory
    |      |
    |      +-- Lấy ProductRepository proxy
    |      |
    |      +-- Transaction 1: lưu fixture, commit
    |      |
    |      +-- Clear persistence context
    |      |
    |      +-- Transaction 2: truy vấn, commit
    |      |
    |      +-- Đóng EntityManager
    |
    +-- Đóng EntityManagerFactory
```

Repository được sử dụng trong khoảng EntityManager còn mở. Factory không sở hữu việc đóng EntityManager mà bạn đã truyền vào.

Ví dụ cố ý có hai transaction: dữ liệu được commit ở giai đoạn nạp, sau đó được đọc trong transaction kế tiếp. Nếu giai đoạn đọc gặp lỗi, việc rollback transaction đọc không hủy transaction nạp đã commit.

### 7.2. Kết quả mong đợi

Ngoài log khởi tạo và SQL, phần kết quả của chương trình có ý nghĩa:

```text
Đã lưu: 3 sản phẩm
SKU đang hoạt động: [MOU-001, KEY-001]
Trang đầu: [MOU-001]
Tổng đang hoạt động: 2
```

Không cố định ID được sinh hoặc chuỗi SQL nguyên văn. Các chi tiết đó có thể phụ thuộc provider, dialect và phiên bản.

Factory vẫn tạo được derived query và phân trang dù không có ApplicationContext. Điều kiện là metadata domain, implementation store và tài nguyên cần thiết đã tồn tại.

## 8. Transaction không tự xuất hiện nhờ annotation trên interface

### 8.1. Repository factory trực tiếp và đường bean không giống hệt nhau

Trong ứng dụng Spring, hạ tầng đăng ký repository có thể bổ sung các interceptor và post-processor liên quan đến transaction.

Khi chỉ dùng:

```java
new JpaRepositoryFactory(em)
        .getRepository(ProductRepository.class);
```

không được mặc định rằng toàn bộ chuỗi tích hợp transaction của repository bean đã được thiết lập.

Annotation `@Transactional` cần cơ chế xử lý tương ứng. Sự xuất hiện của annotation trên implementation hoặc interface không tự bắt đầu transaction trong một chương trình Java độc lập.

Ví dụ dùng `EntityTransaction` tường minh để ranh giới ghi và đọc không phụ thuộc giả định đó.

### 8.2. Vì sao save có thể báo cần transaction?

Một repository proxy có thể tồn tại và phương thức Java có thể gọi được, nhưng persist, merge hoặc flush vẫn cần transaction thích hợp.

Nếu gọi ghi ngoài transaction trong cấu hình resource-local này, bạn có thể gặp lỗi yêu cầu transaction. Cách sửa là chuẩn bị ranh giới transaction đúng, không phải thêm `@Repository` hoặc `@Transactional` rồi để chúng không được xử lý.

### 8.3. Có thể dùng hạ tầng transaction của Spring mà không có context không?

Có thể lập trình với các thành phần transaction được khởi tạo và cấu hình tường minh, chẳng hạn một transaction manager phù hợp và TransactionTemplate.

Tuy nhiên, tất cả thành phần phải phối hợp với cùng tài nguyên. Không mở transaction trên một EntityManager được quản lý qua cơ chế này rồi gọi repository đang giữ một EntityManager độc lập khác và mặc định chúng là một.

Bài thực hành dùng transaction JPA trực tiếp để tránh trộn hai cơ chế quản lý tài nguyên. Nếu chọn một cơ chế khác, thiết kế rõ cách repository lấy tài nguyên tham gia transaction đó.

## 9. Hợp đồng chung vẫn hoạt động đến đâu?

Với cấu hình đơn giản của ví dụ:

| Khả năng | Vì sao có thể dùng |
| --- | --- |
| CRUD chuẩn | Factory tích hợp implementation cơ sở của JPA |
| Derived query | Interface và domain metadata đủ để phân tích và tạo truy vấn |
| Page, Pageable, Sort | Hợp đồng chung được Spring Data JPA chuyển sang truy vấn phù hợp |
| Default method đơn giản | Có thân Java để proxy điều phối |
| Projection được store hỗ trợ | Có thể dùng nếu truy vấn và dạng projection phù hợp |
| Metadata repository | Domain type và ID type được suy ra từ interface cụ thể |

Nhưng không nên coi bảng này là bảo đảm mọi dạng truy vấn hoặc projection đều chạy mà không cần cấu hình thêm.

Những tính năng tham chiếu bean, evaluation context mở rộng hoặc các thành phần ứng dụng khác cần được xem riêng.

Factory không đọc ý định từ tên class cấu hình của bạn. Nó chỉ sử dụng những gì được cung cấp và những mặc định thực sự thuộc đường factory đó.

## 10. Đăng ký fragment tường minh ngoài container

### 10.1. Nhu cầu tùy chỉnh

Giả sử cần lấy giá cao nhất trong các sản phẩm đang hoạt động:

```java
package example.standalone;

import java.math.BigDecimal;

public interface ProductPriceLookup {

    BigDecimal highestActivePrice();
}
```

Implementation JPA:

```java
package example.standalone;

import java.math.BigDecimal;

import jakarta.persistence.EntityManager;

public class ProductPriceLookupImpl
        implements ProductPriceLookup {

    private final EntityManager entityManager;

    public ProductPriceLookupImpl(
            EntityManager entityManager
    ) {
        this.entityManager = entityManager;
    }

    @Override
    public BigDecimal highestActivePrice() {
        BigDecimal result = entityManager.createQuery(
                "select max(p.price) from Product p "
                        + "where p.active = true",
                BigDecimal.class
        ).getSingleResult();

        return result == null ? BigDecimal.ZERO : result;
    }
}
```

Repository cụ thể mở rộng thêm ProductPriceLookup bên cạnh JpaRepository. Giữ các phương thức truy vấn đã có:

```java
public interface ProductRepository
        extends JpaRepository<Product, Long>,
                ProductPriceLookup {

    // Giữ các phương thức đã khai báo ở phần trước.
}
```

Đoạn khai báo này là phiên bản mở rộng thay thế interface trước, không tạo thêm một ProductRepository trùng tên.

### 10.2. Truyền implementation cho factory

```java
import org.springframework.data.repository.core.support.RepositoryComposition.RepositoryFragments;

ProductPriceLookup custom =
        new ProductPriceLookupImpl(em);

RepositoryFragments fragments =
        RepositoryFragments.just(custom);

ProductRepository products = factory.getRepository(
        ProductRepository.class,
        fragments
);
```

Đặt phần tạo repository này thay cho lời gọi getRepository ban đầu khi thực hành fragment, rồi gọi `highestActivePrice()` trong transaction đọc thích hợp.

Với fixture, giá cao nhất của sản phẩm đang hoạt động là 1.200.000 VND. Sản phẩm MON-001 giá 3.500.000 bị loại vì active bằng false.

### 10.3. Điểm khác với phát hiện fragment qua cấu hình ứng dụng

Trong đường tạo trực tiếp này, chương trình khởi tạo implementation và đưa nó cho factory.

Không dựa vào giả định rằng tên ProductPriceLookupImpl tự khiến một factory độc lập đi quét package, tạo instance và inject EntityManager.

Implementation fragment cũng sử dụng tài nguyên do bạn quản lý. Annotation transaction hoặc injection trên một object được tạo bằng new không tự có hiệu lực nếu không có cơ chế bổ sung tương ứng.

## 11. Đối chiếu với MongoRepositoryFactory

### 11.1. Domain và repository MongoDB

Trong một ví dụ MongoDB riêng, giả sử dùng domain:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("factory_customers")
public class CustomerDocument {

    @Id
    private String id;

    private String email;

    private boolean active;

    public CustomerDocument() {
    }

    public CustomerDocument(
            String id,
            String email,
            boolean active
    ) {
        this.id = id;
        this.email = email;
        this.active = active;
    }

    public String getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public boolean isActive() {
        return active;
    }
}
```

```java
import java.util.Optional;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface CustomerDocumentRepository
        extends MongoRepository<CustomerDocument, String> {

    Optional<CustomerDocument> findByEmail(String email);
}
```

Mỗi public type vẫn nằm trong tệp riêng. Đây là domain MongoDB, không tái sử dụng annotation entity JPA của ví dụ trước.

### 11.2. Tạo hạ tầng và factory tương ứng

Với MongoDB driver đồng bộ và Spring Data MongoDB tương thích, đoạn sau nằm trong một phương thức của chương trình:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.repository.support.MongoRepositoryFactory;

try (MongoClient client = MongoClients.create(
        "mongodb://localhost:27017"
)) {
    MongoTemplate template = new MongoTemplate(
            client,
            "repository_factory_demo"
    );

    MongoRepositoryFactory factory =
            new MongoRepositoryFactory(template);

    CustomerDocumentRepository customers =
            factory.getRepository(
                    CustomerDocumentRepository.class
            );

    CustomerDocument saved = customers.save(
            new CustomerDocument(
                    "demo-C001",
                    "mai@example.com",
                    true
            )
    );

    System.out.println("Đã lưu: " + saved.getId());

    CustomerDocument found = customers
            .findByEmail("mai@example.com")
            .orElseThrow();

    System.out.println(found.getEmail());
}
```

Ví dụ yêu cầu MongoDB server đang có tại địa chỉ cấu hình. Factory không tự khởi động server. Dùng database và collection dành riêng cho thực hành.

Email là điều kiện tìm kiếm trong ví dụ, không tự có ràng buộc duy nhất chỉ vì phương thức trả Optional. Cần bảo đảm dữ liệu thử chỉ có một kết quả phù hợp hoặc thiết kế index/ràng buộc theo nghiệp vụ.

### 11.3. Điểm giống và khác

| Nội dung | JPA | MongoDB |
| --- | --- | --- |
| API tạo proxy | `getRepository(interface)` | `getRepository(interface)` |
| Hạ tầng chính truyền cho factory | EntityManager | MongoOperations |
| Mapping domain | JPA entity | MongoDB document |
| Tài nguyên tự tạo cần quản lý | EntityManager, EntityManagerFactory | MongoClient và tài nguyên liên quan |
| Transaction của ví dụ | EntityTransaction resource-local | Không tự có transaction nhiều thao tác chỉ từ factory |
| Provider/driver | JPA provider và JDBC driver | MongoDB driver |

Đoạn MongoDB không hứa chuỗi save rồi find nằm trong một transaction nhiều thao tác. Nếu nghiệp vụ cần transaction MongoDB, phải chuẩn bị hạ tầng, session và điều kiện triển khai phù hợp.

Không dùng JpaRepositoryFactory cho một MongoRepository rồi trông chờ Commons tự đổi EntityManager thành MongoTemplate. Hợp đồng chung không thay thế factory và đường truy cập của store.

## 12. Những tích hợp cần chuẩn bị thêm khi không có container

### 12.1. Auditing

Annotation như `@CreatedDate` hay `@CreatedBy` biểu đạt vai trò metadata. Chỉ có annotation và repository proxy chưa đủ chứng minh auditing đã được kích hoạt đúng.

Cần chuẩn bị cơ chế auditing theo store, nguồn thời gian hoặc auditor khi cần, và callback/listener tương ứng.

Phân biệt điều đó với callback JPA định nghĩa trực tiếp trên entity: provider vẫn có thể thực hiện callback vòng đời theo mapping mà không cần ApplicationContext. Nhưng một listener phụ thuộc bean hoặc hạ tầng Spring khác cần được tích hợp riêng.

Không suy rằng “không có context thì mọi callback đều biến mất”, cũng không suy rằng mọi annotation auditing tự hoạt động.

### 12.2. Dependency injection và bean tham chiếu trong biểu thức

Một fragment được tạo bằng new phải nhận dependency qua code bạn viết. Các field có Autowired không tự được inject.

Một truy vấn hoặc biểu thức tham chiếu một bean trong container cũng cần môi trường phân giải bean tương ứng. Trong chương trình không có BeanFactory, không thể mặc định tên bean sẽ tự được tìm ra.

Các ví dụ của bài tránh phụ thuộc đó bằng constructor và đối tượng được truyền tường minh.

### 12.3. Exception translation

Đường đăng ký repository trong Spring có thể được bổ sung hạ tầng chuyển exception theo cấu hình của ứng dụng.

Factory trực tiếp không bảo đảm tự tái hiện toàn bộ cấu hình post-processor đó. Một số tầng vẫn có thể chuyển đổi exception theo cơ chế riêng, nhưng không nên mặc định mọi lỗi JPA/provider đều xuất hiện đúng như trong một repository bean đã cấu hình đầy đủ.

Khi xử lý lỗi, quan sát loại exception và nguyên nhân thực tế trong chương trình độc lập.

### 12.4. Event publication và các post-processor khác

Nếu ứng dụng dựa vào publication sự kiện domain, interceptor tùy chỉnh hoặc các phần mở rộng được đăng ký qua container, cần xác định chúng được gắn vào đường factory trực tiếp như thế nào.

Việc interface giống nhau không chứng minh chuỗi proxy và post-processor ở hai môi trường giống nhau.

Chọn tạo trực tiếp khi phạm vi tích hợp đủ rõ để quản lý. Khi phải dựng lại nhiều cơ chế của ứng dụng Spring, một context nhỏ có thể dễ tổ chức hơn.

## 13. Quản lý vòng đời và chia sẻ giữa các luồng

### 13.1. Factory không kéo dài tuổi thọ tài nguyên

Repository giữ liên hệ với hạ tầng được cung cấp. Sau khi EntityManager đã đóng, không tiếp tục dùng repository gắn với nó để gọi truy vấn.

Tương tự, đóng MongoClient do chương trình sở hữu làm các thao tác cần client đó không còn khả năng hoạt động bình thường.

Giữ một tham chiếu repository trong biến static không làm tài nguyên bên dưới sống lại.

### 13.2. EntityManager không phải tài nguyên chia sẻ tùy ý

EntityManager thông thường không được dùng đồng thời tùy ý giữa nhiều luồng. Repository được tạo với chính EntityManager đó chịu giới hạn tương ứng.

Một mô hình dễ theo dõi cho chương trình độc lập là tạo EntityManager theo đơn vị công việc, tạo repository gắn với nó, hoàn thành transaction rồi đóng tài nguyên.

EntityManagerFactory thường có vòng đời dài hơn và có thể phục vụ việc tạo EntityManager. Không cần tạo lại toàn bộ factory persistence cho từng bản ghi.

Không kết luận mọi repository của mọi store đều có cùng quy tắc chia sẻ luồng. Với MongoDB, MongoClient và MongoTemplate có mô hình vòng đời khác; cần dựa vào hợp đồng của các thành phần thực tế.

### 13.3. Dữ liệu lazy sau khi đóng tài nguyên

Trong JPA, một entity hoặc association lazy có thể cần persistence context còn phù hợp để tải dữ liệu. Trả một object ra ngoài rồi đóng EntityManager có thể khiến bước truy cập sau đó thất bại.

Product của ví dụ chỉ có các thuộc tính đơn giản, nên không dùng nó làm bằng chứng rằng mọi domain có quan hệ đều an toàn sau khi đóng context.

Nếu kết quả cần đi qua ranh giới tài nguyên, xác định dữ liệu cần đọc và chuyển thành DTO trong phạm vi thích hợp.

## 14. Chẩn đoán lỗi theo tầng

| Hiện tượng | Tầng nên kiểm tra |
| --- | --- |
| Không tìm thấy JpaRepositoryFactory | Dependency Spring Data JPA và phiên bản |
| Không tìm thấy persistence unit | Đường dẫn resource, tên unit, cấu hình đóng gói |
| Không tìm thấy provider hoặc driver | Dependency runtime và classpath |
| Domain không phải managed type | Entity mapping và danh sách class trong persistence unit |
| Không giải quyết được generic domain | Interface truyền vào getRepository chưa cụ thể hoặc khai báo sai |
| Ghi dữ liệu báo cần transaction | Ranh giới transaction thực tế, không chỉ annotation |
| Fragment chưa có implementation | Đối tượng implementation đã được truyền vào factory chưa |
| Derived query báo sai thuộc tính | Tên thuộc tính Java của domain và chữ ký method |
| Repository lỗi sau khi đóng EntityManager | Vòng đời repository đang vượt vòng đời tài nguyên |
| Annotation không kích hoạt hành vi mong đợi | Thiếu cơ chế xử lý, callback hoặc post-processor tương ứng |

Không giải quyết mọi dòng bằng cách thêm ApplicationContext một cách máy móc. Trước hết xác định phần đang thiếu.

Ngược lại, đừng cố dùng factory trực tiếp nếu yêu cầu thực tế phụ thuộc nhiều hạ tầng container mà chương trình chưa cung cấp.

## 15. Bài thực hành kiểm tra mức hiểu

### Bài 1: chạy luồng JPA độc lập

Trên môi trường đã chuẩn bị dependency phù hợp, thực hiện chương trình và đối chiếu:

- Lưu được ba sản phẩm.
- Truy vấn active trả MOU-001 rồi KEY-001.
- Trang đầu kích thước 1 có MOU-001.
- Tổng số sản phẩm active là 2.
- EntityManager và EntityManagerFactory được đóng khi kết thúc.

Kết quả này xác nhận đường cấu hình cụ thể của bài, không phải mọi tùy chọn Spring Data đều tự được kích hoạt.

### Bài 2: quan sát transaction

Trong một biến thể test riêng, thử gọi thao tác ghi mà không bắt đầu transaction.

Giải thích lỗi dựa vào tài nguyên JPA, rồi khôi phục ranh giới transaction tường minh. Không dùng việc thêm annotation chưa được xử lý làm bằng chứng đã sửa lỗi.

### Bài 3: thêm fragment

Mở rộng repository với ProductPriceLookup, truyền ProductPriceLookupImpl bằng RepositoryFragments và xác nhận giá cao nhất của sản phẩm active là 1.200.000 VND.

Giải thích vì sao chỉ đặt tên class kết thúc bằng Impl chưa đủ để thay thế bước truyền đối tượng trong luồng trực tiếp này.

### Bài 4: kiểm tra ownership tài nguyên

Vẽ lại thứ tự tạo và đóng tài nguyên. Chỉ ra ai chịu trách nhiệm rollback khi có lỗi và ai sở hữu EntityManager.

Nếu repository được trả từ một phương thức nhưng EntityManager bị đóng trước khi người gọi sử dụng, hãy xác định vì sao thiết kế vòng đời đó không phù hợp.

### Bài 5: đổi store

Giữ yêu cầu đọc một domain theo thuộc tính nhưng chuyển sang ví dụ MongoDB. Liệt kê phần được giữ ở mức hợp đồng và phần phải thay ở mức mapping, factory, kết nối và transaction.

Không chỉ thay import của factory mà giữ nguyên toàn bộ hạ tầng JPA.

## 16. Nguyên tắc cần giữ

Tạo repository ngoài ApplicationContext là việc sử dụng hạ tầng Spring Data theo chương trình: cung cấp tài nguyên store, chọn factory phù hợp, tạo proxy cho interface cụ thể và quản lý phần tích hợp còn lại một cách tường minh.

Commons cung cấp nền tạo repository và các hợp đồng chung. Factory của store biến chúng thành một repository có thể truy cập dữ liệu. Transaction, auditing, fragment, exception translation và vòng đời tài nguyên phải được chuẩn bị theo đường thực thi mà bạn thực sự chọn.

