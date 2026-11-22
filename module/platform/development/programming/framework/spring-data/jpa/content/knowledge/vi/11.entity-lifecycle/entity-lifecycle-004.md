# Dirty checking và thời điểm phát hiện thay đổi trong Spring Data JPA

Dirty checking là cơ chế JPA provider theo dõi các entity đang được quản lý (managed) và tự đồng bộ những thay đổi của chúng xuống database. Khi ứng dụng sửa một thuộc tính của entity managed trong transaction, thông thường không cần gọi lại `repository.save()` để ghi thay đổi. Provider phát hiện trạng thái khác với trạng thái đã quản lý và tạo câu lệnh SQL UPDATE khi flush.

Hiểu dirty checking cần phân biệt ba thời điểm: lúc Java object bị thay đổi, lúc JPA phát hiện/đồng bộ thay đổi và lúc transaction commit. Chúng không nhất thiết xảy ra cùng một thời điểm. Bài này giải thích vòng đời entity, snapshot, flush, transaction, detached entity, bulk update và cách kiểm thử để biết thay đổi đã thực sự được ghi hay chưa.

## 1. Dirty checking là gì?

Giả sử có entity sản phẩm:

~~~java
Product product = entityManager.find(Product.class, 10L);
product.setPrice(new BigDecimal("120.00"));
~~~

Nếu `product` đang ở trạng thái managed trong persistence context, JPA provider theo dõi nó. Khi flush, provider so sánh trạng thái hiện tại với trạng thái đã quản lý trước đó (hoặc dùng cơ chế theo dõi thay đổi bằng bytecode enhancement). Nếu phát hiện thuộc tính đã thay đổi, provider tạo SQL UPDATE tương ứng.

Ta có thể hình dung:

1. Entity được tải hoặc persist và trở thành managed.
2. Provider lưu thông tin trạng thái cần thiết để theo dõi entity.
3. Ứng dụng thay đổi thuộc tính của object.
4. Đến thời điểm flush, provider phát hiện sự khác biệt.
5. Provider phát SQL INSERT/UPDATE/DELETE để đồng bộ persistence context với database.
6. Transaction commit xác nhận các thay đổi theo cơ chế transaction của database.

Dirty checking là cơ chế của persistence context/JPA provider. Spring Data JPA cung cấp repository để truy cập entity, còn `@Transactional` thường xác định ranh giới transaction trong ứng dụng Spring.

## 2. Vòng đời Entity và điều kiện để dirty checking hoạt động

JPA có các trạng thái entity quan trọng:

| Trạng thái | Ý nghĩa | Dirty checking? |
|---|---|---|
| New / Transient | Object Java mới, chưa được persistence context quản lý | Chưa theo dõi như entity managed |
| Managed / Persistent | Entity đang thuộc persistence context | Có |
| Detached | Entity từng được quản lý nhưng đã tách khỏi persistence context | Không còn được theo dõi |
| Removed | Entity được đánh dấu xóa trong persistence context | Provider đồng bộ thao tác xóa khi flush |

Ví dụ:

~~~java
Product product = new Product("Keyboard", new BigDecimal("80.00"));
// product đang là transient.

entityManager.persist(product);
// product trở thành managed.

product.setPrice(new BigDecimal("75.00"));
// dirty checking có thể phát hiện thay đổi.

entityManager.flush();
// đồng bộ INSERT/UPDATE đang chờ xuống database.

entityManager.detach(product);
// product trở thành detached.

product.setPrice(new BigDecimal("70.00"));
// thay đổi trên object detached không được tự động theo dõi.
~~~

Điều kiện quan trọng: entity phải còn managed tại thời điểm thay đổi và khi provider đồng bộ trạng thái. Chỉ giữ một object Java có ID không có nghĩa object đó đang được JPA quản lý.

### 2.1. Persistence context

Persistence context là tập entity instance được EntityManager quản lý. Trong một persistence context, JPA duy trì identity: với cùng entity type và primary key, việc tìm lại entity thường trả về cùng managed instance.

Ví dụ:

~~~java
Product first = entityManager.find(Product.class, 10L);
Product second = entityManager.find(Product.class, 10L);

assert first == second;
~~~

Trong cùng persistence context, hai biến thường tham chiếu cùng một instance managed. Thay đổi qua biến nào cũng là thay đổi trên cùng object mà provider đang theo dõi.

Persistence context thường gắn với một transaction trong ứng dụng Spring khi dùng transaction-scoped EntityManager. Tuy nhiên, persistence context và transaction là hai khái niệm khác nhau; một persistence context có thể có vòng đời riêng tùy cách cấu hình.

### 2.2. Snapshot và cơ chế phát hiện thay đổi

Cách triển khai truyền thống của Hibernate là giữ snapshot trạng thái entity khi entity được tải hoặc trở thành managed. Khi flush, provider so sánh trạng thái hiện tại với snapshot để xác định thuộc tính nào thay đổi.

Bytecode enhancement có thể cho phép provider theo dõi thay đổi thuộc tính trực tiếp (self-dirty tracking), giảm một số chi phí so sánh snapshot. Đây là chi tiết triển khai của provider, không phải ứng dụng phải tự gọi một phương thức “mark dirty”.

Dù provider dùng snapshot hay enhancement, quy tắc ở cấp ứng dụng vẫn là: sửa entity managed trong persistence context, rồi để provider flush khi phù hợp.

## 3. Ví dụ Spring Boot: cập nhật entity không cần gọi save lần nữa

Ví dụ dưới đây dùng Java 17+, Spring Boot 3.x, Spring Data JPA và H2. Cấu trúc tối thiểu:

~~~text
dirty-checking-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/dirtychecking/
    │   ├── DirtyCheckingApplication.java
    │   ├── Product.java
    │   ├── ProductRepository.java
    │   └── ProductService.java
    └── resources/application.properties
~~~

### 3.1. Maven dependencies

Tạo `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>dirty-checking-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Spring Boot parent quản lý phiên bản tương thích của Spring Data JPA, Hibernate và H2. Trong dự án thực tế, chọn bản vá Spring Boot phù hợp với chính sách nâng cấp của dự án thay vì tự đặt phiên bản rời rạc cho từng thư viện.

### 3.2. Entity Product

Tạo `Product.java`:

~~~java
package com.example.dirtychecking;

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

    @Column(nullable = false, length = 120)
    private String name;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    protected Product() {
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

    public void setName(String name) {
        this.name = name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public void setPrice(BigDecimal price) {
        this.price = price;
    }

    @Override
    public String toString() {
        return "Product{id=" + id
                + ", name='" + name + '\''
                + ", price=" + price.toPlainString()
                + "}";
    }
}
~~~

### 3.3. Repository

Tạo `ProductRepository.java`:

~~~java
package com.example.dirtychecking;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

### 3.4. Service cập nhật bằng dirty checking

Tạo `ProductService.java`:

~~~java
package com.example.dirtychecking;

import java.math.BigDecimal;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductService {

    private final ProductRepository products;

    public ProductService(ProductRepository products) {
        this.products = products;
    }

    @Transactional
    public Product changePrice(Long id, BigDecimal newPrice) {
        Product product = products.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException("Product not found: " + id));

        product.setPrice(newPrice);

        // product đang managed.
        // Không cần gọi products.save(product) lần nữa.
        return product;
    }

    @Transactional(readOnly = true)
    public Product getProduct(Long id) {
        return products.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException("Product not found: " + id));
    }
}
~~~

Trong `changePrice`:

- `findById` tải entity vào persistence context của transaction.
- `product` là managed.
- `setPrice` thay đổi trạng thái Java object.
- Khi transaction flush/commit, provider phát hiện thay đổi và tạo UPDATE.
- Không cần gọi `save` lần nữa cho entity managed.

Nếu gọi `save` cho entity managed, thao tác đó thường không cần thiết. `save` của Spring Data JPA dùng `persist` khi entity được nhận diện là mới và `merge` khi entity không mới; merge có thể sao chép trạng thái vào một managed instance và trả về instance được quản lý. Với entity đã được tải và đang managed trong transaction hiện tại, chỉ cần thay đổi thuộc tính.

### 3.5. Cấu hình H2

Tạo `application.properties`:

~~~properties
spring.datasource.url=jdbc:h2:mem:dirtydb;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.show-sql=true
spring.jpa.properties.hibernate.format_sql=true
spring.jpa.open-in-view=false
~~~

`create-drop` phù hợp với demo vì schema được tạo khi ứng dụng khởi động và xóa khi JVM kết thúc. Không dùng cấu hình này cho database có dữ liệu cần giữ. Ở môi trường thật, quản lý schema bằng Flyway/Liquibase hoặc quy trình migration tương đương.

### 3.6. Chạy thử và kết quả

Tạo `DirtyCheckingApplication.java`:

~~~java
package com.example.dirtychecking;

import java.math.BigDecimal;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DirtyCheckingApplication {

    public static void main(String[] args) {
        SpringApplication.run(DirtyCheckingApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(
            ProductRepository products,
            ProductService service) {
        return args -> {
            Product saved = products.save(
                    new Product("Keyboard", new BigDecimal("80.00"))
            );

            Long id = saved.getId();
            System.out.println("BEFORE: " + service.getProduct(id));

            service.changePrice(id, new BigDecimal("75.00"));

            System.out.println("AFTER:  " + service.getProduct(id));
        };
    }
}
~~~

Chạy:

~~~bash
mvn spring-boot:run
~~~

Các dòng do chương trình in ra trong một database H2 mới:

~~~text
BEFORE: Product{id=1, name='Keyboard', price=80.00}
AFTER:  Product{id=1, name='Keyboard', price=75.00}
~~~

Log SQL của Hibernate sẽ có câu INSERT khi tạo sản phẩm và câu UPDATE khi transaction trong `changePrice` kết thúc. Log khởi động, câu DDL và các log framework khác có thể xen kẽ; phần stdout ở trên chỉ là hai dòng do runner in ra.

## 4. Thời điểm dirty checking phát hiện và ghi thay đổi

Một thay đổi trên entity managed không nhất thiết phát SQL ngay khi setter chạy. Provider thường ghi nhận thay đổi trong bộ nhớ rồi đồng bộ tại thời điểm flush.

### 4.1. Flush trước commit

Trong transaction có flush mode mặc định `AUTO`, provider phải đồng bộ những thay đổi liên quan trước khi transaction commit. Vì vậy, ví dụ service ở trên có thể kết thúc mà không gọi `flush()` tường minh; Spring transaction manager sẽ hoàn tất transaction và JPA flush trước commit theo quy tắc provider/JPA.

Sơ đồ:

~~~text
@Transactional bắt đầu
        |
        v
findById() -> entity managed
        |
        v
setPrice() -> thay đổi trong bộ nhớ
        |
        v
phương thức service kết thúc
        |
        v
flush -> phát SQL UPDATE
        |
        v
commit transaction
~~~

Nếu exception làm transaction rollback, database không giữ thay đổi của transaction đó, dù SQL UPDATE có thể đã được gửi xuống database trong lúc flush.

### 4.2. Gọi EntityManager.flush() tường minh

Có thể yêu cầu đồng bộ ngay:

~~~java
@Transactional
public void updatePriceAndFlush(Long id) {
    Product product = products.findById(id).orElseThrow();
    product.setPrice(new BigDecimal("70.00"));

    entityManager.flush();
}
~~~

Flush hữu ích khi muốn phát hiện sớm lỗi constraint hoặc cần bảo đảm các thay đổi trước đó đã được gửi xuống database trước một thao tác tiếp theo. Nó không kết thúc transaction và không bảo đảm dữ liệu đã commit.

Nếu flush thành công nhưng sau đó transaction rollback, thay đổi vẫn không được commit.

### 4.3. AUTO và COMMIT flush mode

JPA có các flush mode chính:

- `FlushModeType.AUTO`: provider phải bảo đảm các thay đổi có thể ảnh hưởng đến kết quả query được phản ánh khi query chạy; provider có thể flush trước query.
- `FlushModeType.COMMIT`: provider có thể trì hoãn flush cho đến commit; kết quả query trong transaction trước commit không nhất thiết phản ánh mọi thay đổi chưa flush.

Trong Spring Data JPA/Hibernate, query có thể kích hoạt auto-flush nếu cần để kết quả chính xác. Không nên suy luận rằng mỗi lần gọi repository query đều chắc chắn phát SQL flush, hoặc rằng không có flush nào trước commit. Điều này còn phụ thuộc flush mode, query space và provider.

Có thể đặt flush mode ở cấp query hoặc persistence context trong trường hợp đặc biệt, nhưng không nên thay đổi tùy tiện vì có thể làm kết quả query khó hiểu.

### 4.4. persist và IDENTITY có thể phát INSERT sớm

Dirty checking chủ yếu nói về thay đổi của entity đã được quản lý. Với entity mới dùng `GenerationType.IDENTITY`, Hibernate thường cần thực thi INSERT sớm để lấy khóa chính do database sinh. Do đó, không nên khẳng định mọi SQL chỉ xuất hiện tại commit.

Thời điểm INSERT còn phụ thuộc chiến lược sinh ID, provider, transaction và khả năng trì hoãn của database. Phân biệt thao tác persist entity mới với UPDATE do dirty checking giúp đọc SQL log chính xác hơn.

## 5. Dirty checking trong các trạng thái khác nhau

### 5.1. Managed entity

~~~java
@Transactional
public void rename(Long id) {
    Product product = products.findById(id).orElseThrow();
    product.setName("New keyboard");
}
~~~

Entity được tải trong transaction và vẫn managed. Khi flush, provider phát hiện thay đổi và ghi UPDATE. Không cần gọi `save`.

### 5.2. Detached entity

Entity có thể trở thành detached khi:

- Gọi `entityManager.detach(entity)`.
- Gọi `entityManager.clear()`, tách toàn bộ entity đang được quản lý.
- Persistence context đóng.
- Transaction kết thúc trong mô hình persistence context theo transaction.

Thay đổi một object detached không được dirty checking tự động theo dõi:

~~~java
Product product = repository.findById(id).orElseThrow();
entityManager.detach(product);

product.setPrice(new BigDecimal("60.00"));
// Thay đổi này không tự ghi xuống database.
~~~

Muốn đồng bộ trạng thái detached, có thể dùng `merge`:

~~~java
Product managed = entityManager.merge(product);
~~~

`merge` sao chép trạng thái từ object nguồn vào một managed instance và trả về instance managed đó. Object nguồn vẫn detached. Vì vậy hãy dùng kết quả trả về của `merge`, không giả định object đầu vào đã trở thành managed.

Cẩn thận khi merge một object được tạo từ request chỉ chứa một số trường. Những thuộc tính không được khởi tạo có thể mang giá trị null hoặc mặc định và ghi đè dữ liệu đang có. Cách an toàn thường là tải entity managed, cập nhật những trường được phép rồi để dirty checking xử lý.

### 5.3. Removed entity

Khi gọi `entityManager.remove(entity)` hoặc repository delete trên entity phù hợp, entity managed được đánh dấu removed. SQL DELETE thường được phát khi flush. Nếu transaction rollback, thao tác xóa không được commit.

### 5.4. New entity

Entity transient chưa được quản lý không được dirty checking theo dõi như một entity đã có trong database. Khi gọi `persist` hoặc `repository.save` trên entity mới, provider đăng ký entity để INSERT. Những thay đổi tiếp theo trên entity managed có thể được ghi cùng INSERT hoặc UPDATE tùy thời điểm flush và chiến lược ID.

## 6. Những thao tác không đi qua dirty checking thông thường

### 6.1. JPQL bulk update/delete

Ví dụ:

~~~java
@Modifying
@Query("""
       update Product p
       set p.active = false
       where p.discontinued = true
       """)
int deactivateDiscontinuedProducts();
~~~

Bulk JPQL DML tác động trực tiếp lên database, không tải từng entity rồi thay đổi thuộc tính. Vì vậy:

- Không chạy dirty checking cho từng entity bị tác động.
- Persistence context đang mở có thể giữ entity cũ, không phản ánh giá trị vừa update.
- Entity lifecycle callback và cascade theo từng entity không được thực hiện như thao tác thay đổi từng entity.
- Cần cân nhắc version field và optimistic locking; bulk DML không tự động thực hiện đầy đủ cơ chế version như cập nhật entity thông thường.

Có thể cấu hình:

~~~java
@Modifying(flushAutomatically = true, clearAutomatically = true)
@Query("""
       update Product p
       set p.active = false
       where p.discontinued = true
       """)
int deactivateDiscontinuedProducts();
~~~

`flushAutomatically` yêu cầu flush persistence context trước khi chạy bulk query; `clearAutomatically` xóa persistence context sau khi query để tránh tiếp tục dùng các entity cũ. Việc clear có thể làm detached các entity khác đang được quản lý, vì vậy chỉ bật khi caller hiểu hệ quả.

### 6.2. Native SQL và cập nhật ngoài ứng dụng

Nếu một script SQL, stored procedure hoặc ứng dụng khác sửa bảng, persistence context hiện tại không tự biết thay đổi đó. Entity managed có thể trở nên stale.

Có thể:

- Flush các thay đổi đang chờ trước khi chạy SQL ngoài.
- Clear hoặc refresh entity sau khi dữ liệu bên ngoài thay đổi.
- Kết thúc transaction/persistence context trước khi đọc lại.
- Dùng chiến lược cache phù hợp nếu có second-level cache.

Không gọi `refresh` tùy tiện trên entity đang có thay đổi chưa flush, vì refresh tải lại trạng thái từ database và có thể ghi đè thay đổi trong bộ nhớ.

## 7. Kiểm soát cột UPDATE và tối ưu dirty checking

### 7.1. UPDATE có thể chứa nhiều cột hơn cột thay đổi

Mặc định, Hibernate thường sinh UPDATE với tập cột updateable đã ánh xạ, ngay cả khi chỉ một thuộc tính thay đổi. Provider vẫn biết entity dirty nhưng SQL có thể không chỉ chứa đúng cột đã đổi.

Với Hibernate, annotation `@DynamicUpdate` yêu cầu sinh SQL UPDATE dựa trên các cột thực sự thay đổi:

~~~java
import org.hibernate.annotations.DynamicUpdate;

@Entity
@DynamicUpdate
public class Product {
    // entity fields
}
~~~

Đây là tính năng riêng của Hibernate. Nó có thể giảm dữ liệu ghi khi entity có nhiều cột, nhưng làm tăng số hình dạng SQL khác nhau và có thể ảnh hưởng hiệu quả statement cache. Chỉ bật sau khi đo workload thực tế.

### 7.2. @Column(updatable = false)

Thuộc tính được đánh dấu:

~~~java
@Column(updatable = false)
private String externalCode;
~~~

sẽ không được đưa vào SQL UPDATE do JPA provider tạo cho thuộc tính đó sau khi insert. Đây là mapping metadata, không phải cơ chế dirty checking đặc biệt. Dùng cho giá trị không được phép cập nhật sau khi tạo, chẳng hạn mã tham chiếu bất biến. Nếu cần thay đổi, phải thiết kế mapping và quy trình ghi phù hợp.

### 7.3. readOnly transaction

Spring cho phép:

~~~java
@Transactional(readOnly = true)
public ProductSummary getSummary(Long id) {
    // đọc dữ liệu
}
~~~

`readOnly = true` là gợi ý/optimization cho transaction manager và provider. Với Hibernate, Spring có thể đặt flush mode phù hợp để giảm chi phí dirty checking trong một số cấu hình. Tuy nhiên, không nên coi nó là cơ chế bảo mật tuyệt đối ngăn mọi câu lệnh ghi.

Không sửa entity trong phương thức được khai báo read-only rồi kỳ vọng dirty checking sẽ ghi thay đổi như transaction ghi thông thường. Hãy dùng `@Transactional` ghi cho nghiệp vụ thay đổi dữ liệu.

## 8. Transaction boundary và Spring proxy

`@Transactional` thường được thực thi qua Spring AOP proxy. Lời gọi từ một bean khác đi qua proxy có thể mở transaction theo cấu hình. Nhưng self-invocation (một method trong cùng object gọi trực tiếp method khác có `@Transactional`) không đi qua proxy trong chế độ proxy mặc định.

Ví dụ:

~~~java
@Service
public class ProductService {

    public void process(Long id) {
        changePrice(id); // self-invocation
    }

    @Transactional
    public void changePrice(Long id) {
        // Không nên giả định lời gọi nội bộ này tự mở transaction.
    }
}
~~~

Nên đặt ranh giới transaction ở phương thức service được gọi qua bean proxy, hoặc tách nghiệp vụ sang một bean khác. Nếu không có transaction phù hợp, repository method có thể tự tạo transaction riêng cho thao tác của nó, nhưng nhiều bước nghiệp vụ sẽ không còn chung một transaction như dự kiến.

Dirty checking chỉ phát huy đúng trong persistence context và transaction được quản lý đúng. Nếu service đọc entity ở một transaction rồi thay đổi object sau khi transaction đóng, thay đổi không tự ghi.

## 9. Kiểm thử dirty checking bằng flush và clear

Một test tốt cần buộc provider flush rồi clear persistence context trước khi đọc lại. Nếu chỉ đọc lại cùng entity managed, test có thể nhìn thấy giá trị trong bộ nhớ mà chưa chứng minh database đã được cập nhật.

~~~java
package com.example.dirtychecking;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

@DataJpaTest
class DirtyCheckingTest {

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void managedEntityChangesAreWrittenAtFlush() {
        Product product = new Product(
                "Keyboard",
                new BigDecimal("80.00")
        );

        entityManager.persist(product);
        entityManager.flush();

        Long id = product.getId();

        Product managed = entityManager.find(Product.class, id);
        managed.setPrice(new BigDecimal("75.00"));

        // Ép provider đồng bộ thay đổi xuống database.
        entityManager.flush();

        // Xóa persistence context để lần đọc tiếp theo không dùng instance cũ.
        entityManager.clear();

        Product reloaded = entityManager.find(Product.class, id);

        assertThat(reloaded.getPrice())
                .isEqualByComparingTo("75.00");
    }
}
~~~

`flush` bảo đảm SQL UPDATE được gửi xuống database. `clear` tách các entity hiện tại khỏi persistence context. Lần `find` sau phải lấy lại trạng thái từ database (hoặc cache/provider theo cấu hình); test xác nhận giá trị đã được lưu trong database transaction hiện tại.

`@DataJpaTest` thường chạy trong transaction và rollback sau test. Điều này giúp test độc lập, không để dữ liệu thử tồn tại lâu dài.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Sửa entity nhưng database không đổi | Entity detached hoặc transaction đã đóng | Tải entity trong transaction ghi và sửa khi managed |
| Gọi save nhưng vẫn mất dữ liệu | Transaction rollback hoặc lỗi xảy ra lúc flush/commit | Kiểm tra exception, transaction propagation và log |
| Không thấy UPDATE ngay sau setter | SQL chỉ phát khi flush | Quan sát tại flush/commit hoặc gọi flush trong test |
| Query đọc lại dữ liệu cũ trong transaction | Flush mode COMMIT hoặc query không kích hoạt flush | Hiểu flush mode, flush tường minh khi cần |
| Thay đổi bị ghi đè khi merge | Merge object detached thiếu trường | Tải managed entity rồi cập nhật trường cho phép |
| Bulk update xong entity vẫn mang giá trị cũ | Persistence context không tự đồng bộ | Clear/refresh phù hợp sau bulk DML |
| N+1 query | Đọc quan hệ lazy trong vòng lặp | EntityGraph, fetch join, projection hoặc batch fetching |
| SQL UPDATE nhiều cột | Provider sinh câu lệnh theo mapping mặc định | Đo và cân nhắc Hibernate @DynamicUpdate |
| Read-only không ghi như mong đợi | Transaction được đánh dấu read-only | Dùng transaction ghi cho nghiệp vụ cập nhật |
| Self-invocation không tạo transaction | Lời gọi nội bộ bỏ qua Spring proxy | Đặt transaction ở method qua proxy hoặc tách bean |

## 11. Checklist thực hành

- [ ] Entity được sửa đang managed trong persistence context.
- [ ] Transaction bao trọn nghiệp vụ đọc và cập nhật.
- [ ] Không gọi save dư thừa sau khi thay đổi entity managed.
- [ ] Hiểu flush và commit là hai thời điểm khác nhau.
- [ ] Đã xem xét AUTO/COMMIT flush mode nếu query phụ thuộc thay đổi chưa flush.
- [ ] Không dùng readOnly transaction cho thao tác ghi.
- [ ] Không merge một DTO/partial entity có thể ghi đè trường không được gửi.
- [ ] Sau bulk DML, đã xử lý persistence context stale.
- [ ] Có test flush, clear và đọc lại để xác nhận dữ liệu.
- [ ] Đã quan sát SQL và kiểm tra N+1 khi quan hệ được tải.

Dirty checking giúp giảm mã cập nhật thủ công và giữ trạng thái entity nhất quán trong một transaction. Quy tắc thực hành quan trọng nhất là tải entity trong transaction, thay đổi khi entity còn managed, để provider flush vào thời điểm phù hợp và kiểm thử bằng cách đọc lại sau khi clear persistence context.
