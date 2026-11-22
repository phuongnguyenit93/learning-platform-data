# Chạy thử thao tác thêm, đọc, sửa và xóa dữ liệu với Spring Data JPA

Spring Data JPA giúp ứng dụng Java thao tác với cơ sở dữ liệu quan hệ thông qua repository. Thay vì tự viết các câu SQL cơ bản cho từng thao tác, ta khai báo entity đại diện cho bảng và một interface repository. Spring Data tạo phần triển khai repository khi ứng dụng khởi động; Hibernate thường đảm nhiệm vai trò JPA provider để chuyển các thao tác trên entity thành SQL.

Bài thực hành này tạo một ứng dụng Spring Boot nhỏ dùng Java 17+, Spring Data JPA và H2. Chương trình sẽ thêm một sản phẩm, đọc lại sản phẩm, thay đổi giá rồi xóa bản ghi. Cơ sở dữ liệu H2 chạy trong bộ nhớ nên phù hợp để thử nghiệm mà không cần cài máy chủ cơ sở dữ liệu.

## 1. CRUD hoạt động như thế nào?

CRUD là bốn thao tác cơ bản trên dữ liệu:

| Thao tác | Ý nghĩa | Phương thức thường dùng |
|---|---|---|
| Create | Thêm bản ghi mới | \`save(entity)\`, \`saveAll(entities)\` |
| Read | Đọc một hoặc nhiều bản ghi | \`findById(id)\`, \`findAll()\`, \`count()\` |
| Update | Thay đổi bản ghi đã tồn tại | Tải entity, sửa thuộc tính rồi \`save(entity)\`; hoặc dùng dirty checking trong transaction |
| Delete | Xóa bản ghi | \`deleteById(id)\`, \`delete(entity)\`, \`deleteAll()\` |

Luồng xử lý cơ bản:

1. Ứng dụng gọi một phương thức của repository.
2. Spring Data JPA chuyển lời gọi thành thao tác JPA trên \`EntityManager\`.
3. Hibernate quản lý entity và tạo câu SQL tương ứng.
4. Cơ sở dữ liệu thực thi SQL và trả kết quả.
5. Kết quả được ánh xạ trở lại thành entity hoặc giá trị Java.

Repository giúp giảm mã lặp, nhưng không loại bỏ kiến thức về SQL, khóa chính, transaction hay thiết kế bảng. Khi dữ liệu tăng lên, cần chú ý cách truy vấn, phân trang, chỉ mục và số lượng câu SQL được thực thi.

## 2. Tạo project Maven

Tạo project với cấu trúc sau. Các package và đường dẫn trong ví dụ thống nhất là \`com.example.jpacrud\`.

~~~text
spring-data-jpa-crud/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/jpacrud/
    │   │   ├── JpaCrudApplication.java
    │   │   ├── Product.java
    │   │   ├── ProductRepository.java
    │   │   └── ProductService.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/com/example/jpacrud/
            └── ProductRepositoryTest.java
~~~

Nội dung \`pom.xml\`:

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
    <artifactId>spring-data-jpa-crud</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>spring-data-jpa-crud</name>

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

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

Spring Boot quản lý phiên bản tương thích của Spring Data JPA, Hibernate và H2 thông qua dependency management. Trong project thực tế, có thể chọn bản vá Spring Boot 3.5.x mới nhất phù hợp với môi trường triển khai; không cần tự đặt phiên bản riêng cho từng dependency đã được parent quản lý.

## 3. Cấu hình cơ sở dữ liệu

Tạo \`src/main/resources/application.properties\`:

~~~properties
spring.datasource.url=jdbc:h2:mem:shopdb;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.show-sql=true
spring.jpa.properties.hibernate.format_sql=true
spring.jpa.open-in-view=false

spring.h2.console.enabled=true
~~~

Giải thích:

- \`jdbc:h2:mem:shopdb\` tạo cơ sở dữ liệu H2 trong bộ nhớ có tên \`shopdb\`. Dữ liệu sẽ mất khi JVM kết thúc.
- \`DB_CLOSE_DELAY=-1\` giữ cơ sở dữ liệu tồn tại trong suốt vòng đời JVM, kể cả khi tạm thời không còn kết nối.
- \`ddl-auto=create-drop\` yêu cầu Hibernate tạo schema khi ứng dụng khởi động và xóa schema khi ứng dụng dừng. Đây là lựa chọn thuận tiện cho bài thực hành.
- \`show-sql\` và \`format_sql\` giúp quan sát SQL do Hibernate phát sinh.
- \`open-in-view=false\` tránh giữ persistence context mở xuyên suốt vòng đời HTTP request. Với ứng dụng web, hãy tải dữ liệu cần thiết trong transaction của service.

Không dùng \`create-drop\` cho dữ liệu thật. Ở môi trường triển khai, thường dùng Flyway hoặc Liquibase để quản lý migration và chọn \`validate\` hoặc cấu hình schema phù hợp. H2 console cũng chỉ nên bật trong môi trường phát triển được kiểm soát.

## 4. Khai báo entity Product

Entity là lớp Java được JPA ánh xạ với bảng trong cơ sở dữ liệu. Tạo file \`Product.java\`:

~~~java
package com.example.jpacrud;

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

    // JPA cần constructor không tham số có mức truy cập protected hoặc public.
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

Các annotation quan trọng:

- \`@Entity\` đánh dấu lớp được JPA quản lý.
- \`@Table(name = "products")\` chỉ định tên bảng.
- \`@Id\` xác định khóa chính.
- \`@GeneratedValue(strategy = GenerationType.IDENTITY)\` giao việc sinh ID cho cơ sở dữ liệu theo cơ chế identity.
- \`@Column\` khai báo một số ràng buộc và kiểu cột. \`precision = 12, scale = 2\` phù hợp với ví dụ lưu giá có hai chữ số thập phân.
- Constructor không tham số cho phép JPA tạo entity khi đọc dữ liệu.

Dùng \`BigDecimal\` cho giá tiền thay vì \`double\` hoặc \`float\`, vì kiểu dấu phẩy động nhị phân có thể tạo sai số khi biểu diễn số thập phân. Trong hệ thống thực tế, nên bổ sung validation cho dữ liệu đầu vào và ràng buộc tương ứng ở database.

## 5. Tạo repository

Tạo file \`ProductRepository.java\`:

~~~java
package com.example.jpacrud;

import java.math.BigDecimal;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository extends JpaRepository<Product, Long> {

    List<Product> findByNameContainingIgnoreCase(String keyword);

    List<Product> findByPriceGreaterThanEqual(BigDecimal minPrice);
}
~~~

Hai tham số kiểu của \`JpaRepository<Product, Long>\` lần lượt là kiểu entity và kiểu khóa chính. Spring Data tự tạo implementation cho interface này khi ứng dụng khởi động.

Ngoài các phương thức CRUD chuẩn, Spring Data có thể tạo truy vấn từ tên phương thức:

- \`findByNameContainingIgnoreCase\` tìm tên có chứa từ khóa, không phân biệt chữ hoa và chữ thường.
- \`findByPriceGreaterThanEqual\` tìm sản phẩm có giá lớn hơn hoặc bằng giá truyền vào.

Không cần viết SQL cho các truy vấn đơn giản này. Với truy vấn phức tạp, có thể dùng \`@Query\` với JPQL hoặc native SQL; hãy chọn cách phù hợp với độ phức tạp và yêu cầu hiệu năng.

## 6. Chạy thử đủ bốn thao tác

Tạo file \`JpaCrudApplication.java\`:

~~~java
package com.example.jpacrud;

import java.math.BigDecimal;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class JpaCrudApplication {

    public static void main(String[] args) {
        SpringApplication.run(JpaCrudApplication.class, args);
    }

    @Bean
    CommandLineRunner crudDemo(ProductRepository products) {
        return args -> {
            // CREATE: thêm một sản phẩm mới.
            Product created = products.save(
                    new Product("Mechanical Keyboard", new BigDecimal("89.90"))
            );
            System.out.println("CREATE: " + created);

            // READ: đọc lại sản phẩm theo khóa chính.
            Product read = products.findById(created.getId())
                    .orElseThrow(() -> new IllegalStateException("Product not found"));
            System.out.println("READ:   " + read);

            // UPDATE: thay đổi giá rồi lưu entity.
            read.setPrice(new BigDecimal("79.90"));
            Product updated = products.save(read);
            System.out.println("UPDATE: " + updated);

            // DELETE: xóa sản phẩm và kiểm tra lại sự tồn tại.
            products.deleteById(created.getId());
            System.out.println("DELETE: exists="
                    + products.existsById(created.getId()));
        };
    }
}
~~~

Chạy ứng dụng bằng Maven:

~~~bash
mvn spring-boot:run
~~~

Khi database mới được tạo và chương trình chạy lần đầu, bốn dòng do chương trình in ra sẽ có dạng:

~~~text
CREATE: Product{id=1, name='Mechanical Keyboard', price=89.90}
READ:   Product{id=1, name='Mechanical Keyboard', price=89.90}
UPDATE: Product{id=1, name='Mechanical Keyboard', price=79.90}
DELETE: exists=false
~~~

Các dòng log khởi động và câu SQL của Hibernate có thể xuất hiện xen kẽ. Phần kết quả trên là bốn dòng từ các lệnh \`System.out.println\` trong runner. ID bắt đầu từ 1 vì đây là database H2 mới, không có bản ghi trước đó.

### 6.1. CREATE — thêm dữ liệu

~~~java
Product created = products.save(
        new Product("Mechanical Keyboard", new BigDecimal("89.90"))
);
~~~

Ta tạo một entity mới rồi truyền vào \`save\`. Vì entity chưa có ID được sinh, Spring Data JPA nhận diện đây là entity mới và yêu cầu JPA persist entity. Hibernate phát sinh câu lệnh \`INSERT\`; sau khi lưu thành công, ID được gán vào entity.

Có thể thêm nhiều entity bằng \`saveAll(entities)\`. Không nên gọi \`save\` trong vòng lặp cho một lượng dữ liệu rất lớn mà chưa xem xét batching và transaction, vì cách gọi đơn giản có thể tạo nhiều lần tương tác với database.

### 6.2. READ — đọc dữ liệu

~~~java
Product product = products.findById(id)
        .orElseThrow(() -> new IllegalArgumentException("Product not found"));
~~~

\`findById\` trả về \`Optional<Product>\`, vì ID được yêu cầu có thể không tồn tại. Hãy xử lý trường hợp rỗng bằng \`orElseThrow\`, \`orElse\` hoặc kiểm tra \`isPresent()\`; không gọi \`get()\` một cách tùy tiện.

Các lựa chọn đọc thường gặp:

- \`findAll()\`: đọc toàn bộ bản ghi; chỉ phù hợp khi bảng nhỏ hoặc dữ liệu đã được giới hạn.
- \`findAllById(ids)\`: đọc các bản ghi theo danh sách ID.
- \`existsById(id)\`: kiểm tra một ID có tồn tại.
- \`count()\`: đếm số bản ghi.
- Phương thức truy vấn dẫn xuất như \`findByNameContainingIgnoreCase(keyword)\`: tìm theo điều kiện cụ thể.

Với bảng lớn, tránh dùng \`findAll()\` để tải toàn bộ dữ liệu vào bộ nhớ. Hãy dùng phân trang hoặc truy vấn có giới hạn.

### 6.3. UPDATE — sửa dữ liệu

Trong runner, ta tải entity, đổi giá rồi gọi \`save\`:

~~~java
Product product = products.findById(id).orElseThrow();
product.setPrice(new BigDecimal("79.90"));
Product updated = products.save(product);
~~~

Với entity đã tồn tại, \`save\` thường dùng thao tác merge để đồng bộ trạng thái entity với persistence context. Hãy dùng đối tượng được trả về từ \`save\`, vì với entity detached, đối tượng được merge có thể là một instance khác.

Trong một transaction, nếu entity đang được quản lý (managed), Hibernate có thể phát hiện thay đổi thuộc tính bằng dirty checking và phát sinh \`UPDATE\` khi flush hoặc commit. Khi đó không bắt buộc phải gọi \`save\` lần nữa. Ví dụ ở phần service bên dưới minh họa cách này.

Không nên xem \`save\` là một câu lệnh SQL upsert có quy tắc giống nhau ở mọi database. Việc xác định entity mới hay đã tồn tại dựa trên cơ chế nhận diện trạng thái mới của Spring Data JPA và cấu hình entity.

### 6.4. DELETE — xóa dữ liệu

~~~java
products.deleteById(id);
boolean stillExists = products.existsById(id);
~~~

\`deleteById\` xóa entity có khóa chính tương ứng. Có thể dùng \`delete(entity)\` khi đã có entity hoặc \`deleteAll()\` khi thật sự cần xóa toàn bộ dữ liệu. Các thao tác xóa hàng loạt cần được cân nhắc kỹ vì có thể ảnh hưởng đến cascade, persistence context và các ràng buộc khóa ngoại.

Trong ứng dụng thật, nên xác định rõ hành vi khi ID không tồn tại, quyền của người dùng, ràng buộc nghiệp vụ và việc ghi audit trước khi xóa.

## 7. Đặt transaction trong service

Repository đã cung cấp transaction cho nhiều phương thức CRUD riêng lẻ. Tuy nhiên, một nghiệp vụ thường gồm nhiều bước đọc và ghi; nên đặt ranh giới transaction ở service để các bước cùng thành công hoặc cùng rollback.

Tạo file \`ProductService.java\`:

~~~java
package com.example.jpacrud;

import java.math.BigDecimal;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductService {

    private final ProductRepository products;

    public ProductService(ProductRepository products) {
        this.products = products;
    }

    @Transactional(readOnly = true)
    public Product getProduct(Long id) {
        return products.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("Product not found"));
    }

    @Transactional
    public Product updatePrice(Long id, BigDecimal newPrice) {
        Product product = products.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("Product not found"));

        product.setPrice(newPrice);

        // Entity vẫn đang managed; dirty checking sẽ ghi thay đổi khi commit.
        return product;
    }

    @Transactional
    public void deleteProduct(Long id) {
        Product product = products.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("Product not found"));
        products.delete(product);
    }
}
~~~

Điểm cần hiểu:

- \`@Transactional\` tạo ranh giới transaction cho phương thức service.
- \`readOnly = true\` thể hiện phương thức chỉ đọc và cho phép framework/provider áp dụng một số tối ưu phù hợp; không nên xem đây là cơ chế bảo mật chống ghi tuyệt đối.
- Khi \`updatePrice\` thay đổi một entity managed, dirty checking phát hiện thay đổi và Hibernate ghi xuống database khi transaction commit.
- Nếu một lỗi làm transaction rollback, các thay đổi trong transaction đó được hoàn tác theo cơ chế của database.
- Trong một ứng dụng web, controller nên gọi service; service chịu trách nhiệm nghiệp vụ và transaction, còn repository tập trung vào truy cập dữ liệu.

Runner ở phần trước gọi repository trực tiếp để minh họa từng thao tác. Trong ứng dụng có nghiệp vụ thực tế, hãy chuyển luồng đó vào service thay vì để controller hoặc nhiều thành phần tự quản lý transaction.

## 8. Kiểm thử CRUD bằng JUnit

Có thể kiểm thử repository bằng \`@DataJpaTest\`. Tạo file \`ProductRepositoryTest.java\`:

~~~java
package com.example.jpacrud;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
class ProductRepositoryTest {

    @Autowired
    private ProductRepository products;

    @Test
    void shouldCreateReadUpdateAndDeleteProduct() {
        Product saved = products.save(
                new Product("Wireless Mouse", new BigDecimal("25.00"))
        );

        assertThat(saved.getId()).isNotNull();

        Product found = products.findById(saved.getId()).orElseThrow();
        assertThat(found.getName()).isEqualTo("Wireless Mouse");

        found.setPrice(new BigDecimal("20.00"));
        Product updated = products.save(found);
        assertThat(updated.getPrice()).isEqualByComparingTo("20.00");

        products.deleteById(saved.getId());
        assertThat(products.existsById(saved.getId())).isFalse();
    }
}
~~~

Chạy kiểm thử:

~~~bash
mvn test
~~~

\`@DataJpaTest\` tạo test slice tập trung vào thành phần JPA và thường chạy mỗi test trong transaction được rollback sau khi test kết thúc. Điều này giúp test không để lại dữ liệu thử trong database. Test ở trên xác nhận ID được tạo, dữ liệu đọc đúng, giá được cập nhật và bản ghi không còn tồn tại sau khi xóa.

## 9. Truy vấn và phân trang khi dữ liệu tăng

Repository có thể khai báo thêm phương thức truy vấn theo quy tắc đặt tên:

~~~java
List<Product> findByNameContainingIgnoreCase(String keyword);
List<Product> findByPriceGreaterThanEqual(BigDecimal minPrice);
~~~

Ví dụ gọi:

~~~java
List<Product> matches =
        products.findByNameContainingIgnoreCase("keyboard");

List<Product> affordable =
        products.findByPriceGreaterThanEqual(new BigDecimal("50.00"));
~~~

Nếu cần sắp xếp và phân trang, dùng \`Pageable\`:

~~~java
Page<Product> page = products.findAll(
        PageRequest.of(0, 10, Sort.by("name").ascending())
);

List<Product> firstTenProducts = page.getContent();
long totalProducts = page.getTotalElements();
int totalPages = page.getTotalPages();
~~~

Các import cần thiết cho ví dụ phân trang:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
~~~

Số trang bắt đầu từ 0; ví dụ trên lấy trang đầu tiên, tối đa 10 sản phẩm, sắp xếp theo thuộc tính entity \`name\` tăng dần. Tên thuộc tính trong \`Sort\` là tên thuộc tính Java của entity, không nhất thiết trùng tên cột vật lý trong database.

\`Page\` thường cần thêm truy vấn đếm để tính tổng số phần tử. Nếu giao diện chỉ cần biết còn trang tiếp theo hay không, \`Slice\` có thể phù hợp hơn vì không nhất thiết phải lấy tổng số bản ghi.

## 10. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Không tạo được bean repository | Package scan không bao phủ repository hoặc cấu hình Spring sai | Đặt lớp main ở package cha của entity, repository và service |
| Entity không được ánh xạ | Thiếu \`@Entity\`, \`@Id\` hoặc constructor không tham số | Kiểm tra annotation và constructor của entity |
| Không kết nối được H2 | Thiếu dependency H2 hoặc URL/driver sai | Kiểm tra dependency, JDBC URL và log khởi động |
| Không tìm thấy bản ghi | ID không tồn tại hoặc dữ liệu chưa được commit | Kiểm tra ID, transaction và dữ liệu thực tế |
| Giá tiền có sai số | Dùng \`double\` hoặc \`float\` | Dùng \`BigDecimal\` và khai báo precision/scale |
| Truy vấn chậm hoặc tốn bộ nhớ | Dùng \`findAll()\` với bảng lớn hoặc tải quan hệ không cần thiết | Dùng điều kiện lọc, phân trang và xem SQL phát sinh |
| Lỗi ràng buộc khóa ngoại | Xóa bản ghi cha khi vẫn còn bản ghi con | Xác định quan hệ và quy tắc cascade rõ ràng |

Một số lưu ý khi đưa vào ứng dụng thực tế:

1. **Validation:** kiểm tra dữ liệu đầu vào ở tầng ứng dụng; đồng thời giữ các ràng buộc quan trọng ở database như \`NOT NULL\`, \`UNIQUE\` và khóa ngoại.
2. **Transaction:** gom nhiều thao tác thuộc cùng một nghiệp vụ vào một transaction ở service.
3. **N+1 query:** khi đọc quan hệ entity, kiểm tra số lượng SQL. Dùng fetch join, entity graph hoặc projection khi phù hợp; không đặt eager loading cho mọi quan hệ một cách máy móc.
4. **Optimistic locking:** nếu nhiều người có thể sửa cùng một bản ghi, cân nhắc thêm trường \`@Version\` để phát hiện cập nhật xung đột thay vì âm thầm ghi đè dữ liệu của nhau.
5. **Migration:** dùng Flyway hoặc Liquibase để quản lý thay đổi schema có kiểm soát. Tránh để Hibernate tự tạo hoặc xóa bảng dữ liệu thật.
6. **Bảo mật:** không bật H2 console công khai và không trả entity trực tiếp ra API nếu điều đó làm lộ trường nội bộ hoặc gây tải quan hệ ngoài ý muốn.

## 11. Tự kiểm tra sau bài thực hành

Sau khi chạy \`mvn spring-boot:run\` và \`mvn test\`, hãy xác nhận:

- [ ] Ứng dụng khởi động và kết nối được với H2.
- [ ] Thao tác CREATE tạo được sản phẩm và nhận được ID.
- [ ] Thao tác READ lấy lại đúng tên và giá.
- [ ] Thao tác UPDATE lưu được giá mới.
- [ ] Thao tác DELETE làm cho \`existsById\` trả về \`false\`.
- [ ] Kiểm thử repository hoàn thành thành công.
- [ ] Có thể giải thích vai trò của entity, repository, transaction và dirty checking.

Khi đã hiểu luồng CRUD với H2, có thể thay datasource bằng PostgreSQL, MySQL hoặc một hệ quản trị quan hệ khác. Phần entity và repository thường giữ nguyên ở mức cơ bản; cần cập nhật driver, JDBC URL, thông tin kết nối, kiểu dữ liệu phù hợp và cách quản lý schema cho database mới.
