# Kiểm thử tính đúng đắn và khả năng chuyển cơ sở dữ liệu của SQL thuần trong Spring Data JPA

SQL thuần (native SQL) cho phép tận dụng cú pháp và tính năng của hệ quản trị cơ sở dữ liệu, nhưng nó cũng làm ứng dụng phụ thuộc trực tiếp hơn vào database. Một truy vấn chạy đúng trên H2 chưa chắc chạy đúng trên PostgreSQL, MySQL hoặc MariaDB. Ngay cả khi cùng trả về dữ liệu, các database vẫn có thể khác nhau về kiểu dữ liệu, collation, cách xử lý NULL, phân trang, hàm ngày giờ và ràng buộc.

Muốn kiểm thử tốt, cần xác nhận hai khía cạnh riêng:

- **Tính đúng đắn:** câu SQL trả đúng hàng, đúng thứ tự, đúng kiểu dữ liệu, đúng tổng số kết quả và xử lý đúng các trường hợp biên.
- **Khả năng chuyển database:** câu truy vấn, mapping, migration và hành vi transaction hoạt động trên từng hệ quản trị mà ứng dụng cam kết hỗ trợ.

Bài này xây dựng một repository native query có phân trang, chạy cùng một bộ kiểm thử hợp đồng trên PostgreSQL và MariaDB bằng Testcontainers, sau đó trình bày cách mở rộng cho schema migration và các khác biệt SQL thường gặp.

## 1. Phân biệt các mức độ portability

“Portable” có thể mang nhiều ý nghĩa. Cần xác định ứng dụng muốn chuyển đổi ở lớp nào:

| Phạm vi | Câu hỏi cần trả lời | Cách kiểm thử |
|---|---|---|
| Database portability | Cùng SQL có chạy trên các database mục tiêu không? | Chạy integration test trên từng database |
| Schema portability | Entity, kiểu cột, index, constraint và migration có tạo được schema hợp lệ không? | Chạy migration trên database thật, sau đó validate schema |
| Result mapping portability | Kết quả native query có ánh xạ đúng sang entity/DTO không? | Kiểm tra kiểu, null, alias và dữ liệu trả về |
| Provider portability | Query hoạt động với Hibernate và EclipseLink hay không? | Chạy cùng contract test với từng JPA provider nếu dự án hỗ trợ cả hai |
| Version portability | SQL có chạy trên các phiên bản database được hỗ trợ không? | Test với đúng phiên bản thấp nhất và phiên bản triển khai |

Native SQL không có mức độc lập database như JPQL. Câu lệnh dùng hàm riêng, kiểu dữ liệu riêng hoặc cú pháp phân trang riêng có thể chỉ chạy trên một hệ quản trị. Vì vậy, trước khi viết test, hãy ghi rõ danh sách database và phiên bản mà ứng dụng thực sự hỗ trợ.

Một bài test chạy với Hibernate và PostgreSQL chỉ chứng minh hành vi trên tổ hợp đó. Nó không chứng minh truy vấn chạy với EclipseLink hoặc MariaDB.

## 2. Kiểm thử điều gì trong một native query?

Không chỉ kiểm tra rằng phương thức repository không ném exception. Một test có giá trị cần xác nhận nội dung và ngữ nghĩa của kết quả.

Với truy vấn danh sách sản phẩm, nên kiểm tra:

1. **Điều kiện lọc:** chỉ lấy hàng thỏa tất cả predicate.
2. **Biên:** giá trị đúng bằng ngưỡng có được bao gồm hay không, ví dụ `>=` so với `>`.
3. **Dữ liệu rỗng:** query trả danh sách rỗng hoặc Page rỗng đúng hợp đồng.
4. **NULL:** xử lý đúng khi cột nullable có giá trị NULL.
5. **Trùng giá trị:** các hàng cùng giá hoặc cùng ngày vẫn được sắp xếp ổn định.
6. **Thứ tự:** có tie-breaker duy nhất để kết quả không thay đổi ngẫu nhiên giữa các lần chạy.
7. **Phân trang:** nội dung trang, trang kế tiếp, tổng phần tử và tổng số trang nhất quán.
8. **Mapping:** kiểu số, boolean, ngày giờ và tên cột được ánh xạ đúng.
9. **Tham số:** dữ liệu người dùng được bind bằng parameter, không nối chuỗi vào SQL.
10. **Transaction:** query nhìn thấy dữ liệu theo đúng ranh giới transaction và isolation level của ứng dụng.

Với query có `Page<T>`, kiểm tra cả truy vấn lấy nội dung và `countQuery`. Một trang hiển thị đúng dữ liệu nhưng tổng số phần tử sai vẫn là lỗi chức năng.

## 3. Ví dụ native query có phân trang

Ta xây dựng truy vấn lấy sản phẩm đang hoạt động có giá từ một ngưỡng trở lên. Kết quả được sắp xếp theo giá tăng dần, sau đó theo ID để thứ tự luôn xác định.

### 3.1. Entity Product

Tạo file `Product.java`:

~~~java
package com.example.nativequery;

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

    @Column(nullable = false)
    private boolean active;

    protected Product() {
    }

    public Product(String name, BigDecimal price, boolean active) {
        this.name = name;
        this.price = price;
        this.active = active;
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
}
~~~

Entity chỉ có các cột cơ bản để ví dụ tập trung vào native query. Trong dự án thực tế, entity có thể có thêm quan hệ hoặc audit field; nếu query trả về entity, phải bảo đảm SELECT cung cấp đủ các cột được mapping.

### 3.2. Repository với @Query(nativeQuery = true)

Tạo file `ProductRepository.java`:

~~~java
package com.example.nativequery;

import java.math.BigDecimal;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Query(
        value = """
                SELECT p.id, p.name, p.price, p.active
                FROM products p
                WHERE p.active = TRUE
                  AND p.price >= ?1
                ORDER BY p.price ASC, p.id ASC
                """,
        countQuery = """
                     SELECT COUNT(*)
                     FROM products p
                     WHERE p.active = TRUE
                       AND p.price >= ?1
                     """,
        nativeQuery = true
    )
    Page<Product> findActiveAtOrAbove(
            BigDecimal minimumPrice,
            Pageable pageable);
}
~~~

Truy vấn dùng các thành phần SQL phổ biến: `SELECT`, `FROM`, `WHERE`, `AND`, phép so sánh, `ORDER BY` và `COUNT(*)`.

Các quyết định trong query:

- `p.active = TRUE` chỉ lấy sản phẩm đang hoạt động.
- `p.price >= ?1` bao gồm sản phẩm có giá bằng ngưỡng.
- `?1` là tham số vị trí theo cú pháp khai báo query của Spring Data JPA; giá trị được bind, không ghép trực tiếp vào chuỗi SQL.
- `ORDER BY p.price ASC, p.id ASC` tạo thứ tự ổn định ngay cả khi nhiều sản phẩm cùng giá.
- `countQuery` dùng cùng điều kiện lọc với query nội dung để tổng số phần tử chính xác.
- `Pageable` cho phép Spring Data và Hibernate áp dụng phân trang theo dialect của database.

Vì kết quả là entity `Product`, SELECT liệt kê đầy đủ các cột được mapping: `id`, `name`, `price`, `active`. Nếu entity có thêm cột bắt buộc hoặc quan hệ cần mapping, cần bổ sung cột tương ứng. Không nên SELECT một vài cột rồi yêu cầu provider ánh xạ kết quả thành entity đầy đủ.

### 3.3. Gọi repository

~~~java
Page<Product> page = productRepository.findActiveAtOrAbove(
        new BigDecimal("50.00"),
        PageRequest.of(0, 20)
);

List<Product> products = page.getContent();
long total = page.getTotalElements();
int totalPages = page.getTotalPages();
~~~

Không tự viết `LIMIT` hoặc `OFFSET` trong query ví dụ. Khi dùng `Pageable`, Spring Data/Hibernate có thể tạo cú pháp phân trang phù hợp với dialect đang chạy. Cần kiểm tra SQL thực tế nếu thay provider hoặc dùng một query phức tạp.

## 4. Chạy cùng contract test trên nhiều database

Cách đáng tin cậy để kiểm tra database portability là chạy cùng một bộ assertion trên từng database mục tiêu. Testcontainers khởi chạy database thật trong container, vì vậy test dùng SQL engine thực tế thay vì một database giả lập.

Ví dụ dưới đây dùng PostgreSQL và MariaDB. Cần Docker hoặc môi trường CI có khả năng chạy container.

### 4.1. Dependencies Maven

Với Spring Boot 3.x và Java 17+, thêm các dependency sau vào `pom.xml`. Spring Boot parent quản lý các dependency Spring; Testcontainers có thể được quản lý qua BOM hoặc khai báo một phiên bản thống nhất cho tất cả module.

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>junit-jupiter</artifactId>
        <version>1.21.1</version>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>postgresql</artifactId>
        <version>1.21.1</version>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>mariadb</artifactId>
        <version>1.21.1</version>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.mariadb.jdbc</groupId>
        <artifactId>mariadb-java-client</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Các image trong test nên được pin theo phiên bản gần với production. Nếu production chạy PostgreSQL 16.4 và MariaDB 11.4.4, hãy dùng đúng các phiên bản đó trong CI thay vì dùng tag `latest`.

### 4.2. Viết một bộ kiểm thử hợp đồng dùng chung

Tạo file `ProductNativeQueryContract.java`. Đây là lớp test cơ sở, chứa dữ liệu mẫu và các assertion mà mọi database phải đáp ứng:

~~~java
package com.example.nativequery;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.util.List;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;

abstract class ProductNativeQueryContract {

    @Autowired
    protected ProductRepository products;

    @Autowired
    protected TestEntityManager entityManager;

    protected void verifiesNativeQueryContract() {
        products.saveAll(List.of(
                new Product("Keyboard", new BigDecimal("80.00"), true),
                new Product("Mouse", new BigDecimal("50.00"), true),
                new Product("Monitor", new BigDecimal("200.00"), true),
                new Product("Cable", new BigDecimal("10.00"), true),
                new Product("Inactive", new BigDecimal("60.00"), false),
                new Product("USB Hub", new BigDecimal("80.00"), true)
        ));

        entityManager.flush();
        entityManager.clear();

        Page<Product> first = products.findActiveAtOrAbove(
                new BigDecimal("50.00"),
                PageRequest.of(0, 2)
        );

        assertThat(first.getContent())
                .extracting(Product::getName)
                .containsExactly("Mouse", "Keyboard");

        assertThat(first.getTotalElements()).isEqualTo(4);
        assertThat(first.getTotalPages()).isEqualTo(2);

        Page<Product> second = products.findActiveAtOrAbove(
                new BigDecimal("50.00"),
                PageRequest.of(1, 2)
        );

        assertThat(second.getContent())
                .extracting(Product::getName)
                .containsExactly("USB Hub", "Monitor");

        assertThat(second.getTotalElements()).isEqualTo(4);
    }
}
~~~

Bộ dữ liệu cố ý có các trường hợp:

- `Mouse` có giá đúng bằng ngưỡng 50.00 để kiểm tra toán tử `>=`.
- `Cable` có giá thấp hơn ngưỡng để kiểm tra lọc giá.
- `Inactive` có giá đạt ngưỡng nhưng trạng thái inactive để kiểm tra điều kiện boolean.
- `Keyboard` và `USB Hub` cùng giá 80.00 để kiểm tra tie-breaker `id`.
- Có bốn sản phẩm hợp lệ để kiểm tra nội dung hai trang và tổng số kết quả.

`flush()` gửi dữ liệu setup xuống database. `clear()` xóa persistence context để kết quả query không bị nhầm với entity instance còn đang được quản lý. Assertion kiểm tra cả nội dung, thứ tự và count query.

### 4.3. Chạy contract test với PostgreSQL

Tạo file `ProductNativeQueryPostgresTest.java`:

~~~java
package com.example.nativequery;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@DataJpaTest(properties = "spring.jpa.hibernate.ddl-auto=create-drop")
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
@Testcontainers
class ProductNativeQueryPostgresTest
        extends ProductNativeQueryContract {

    @Container
    static final PostgreSQLContainer<?> DATABASE =
            new PostgreSQLContainer<>("postgres:16.4-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", DATABASE::getJdbcUrl);
        registry.add("spring.datasource.username", DATABASE::getUsername);
        registry.add("spring.datasource.password", DATABASE::getPassword);
    }

    @Test
    void nativeQueryWorksOnPostgreSql() {
        verifiesNativeQueryContract();
    }
}
~~~

`@AutoConfigureTestDatabase(replace = NONE)` yêu cầu Spring giữ datasource từ Testcontainers thay vì thay bằng database embedded. `@DynamicPropertySource` đưa JDBC URL và credentials của container vào Spring context.

### 4.4. Chạy cùng contract test với MariaDB

Tạo file `ProductNativeQueryMariaDbTest.java`:

~~~java
package com.example.nativequery;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.MariaDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@DataJpaTest(properties = "spring.jpa.hibernate.ddl-auto=create-drop")
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
@Testcontainers
class ProductNativeQueryMariaDbTest
        extends ProductNativeQueryContract {

    @Container
    static final MariaDBContainer<?> DATABASE =
            new MariaDBContainer<>("mariadb:11.4.4");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", DATABASE::getJdbcUrl);
        registry.add("spring.datasource.username", DATABASE::getUsername);
        registry.add("spring.datasource.password", DATABASE::getPassword);
    }

    @Test
    void nativeQueryWorksOnMariaDb() {
        verifiesNativeQueryContract();
    }
}
~~~

Hai test class dùng cùng `ProductNativeQueryContract`. Nếu query chạy đúng trên PostgreSQL nhưng sai trên MariaDB, test MariaDB sẽ chỉ ra khác biệt. Khi thêm database mới, tạo một test class cấu hình container tương ứng và gọi cùng contract method.

Chạy:

~~~bash
mvn -Dtest=ProductNativeQueryPostgresTest,ProductNativeQueryMariaDbTest test
~~~

Testcontainers tải image ở lần đầu và cần Docker đang hoạt động. Khi CI chạy, có thể cache image để giảm thời gian. Hãy pin image theo phiên bản production và cập nhật có chủ đích.

Ví dụ trên dùng Hibernate tạo schema bằng `create-drop` để tập trung kiểm tra query. Nó chưa kiểm tra migration của ứng dụng; phần tiếp theo trình bày cách kiểm tra migration thật.

## 5. Kiểm thử schema và migration trên từng database

Một native query có thể đúng về cú pháp nhưng vẫn lỗi khi chạy trên schema thực tế. Nguyên nhân thường là:

- Tên bảng/cột khác với tên query giả định.
- Kiểu cột khác nhau giữa migration và entity.
- Cột nullable hoặc default value không giống nhau.
- Index hoặc foreign key chưa được tạo.
- Migration dùng cú pháp riêng của một database.
- Tên định danh bị trùng từ khóa hoặc khác nhau về chữ hoa/chữ thường.

`ddl-auto=create-drop` chỉ kiểm tra schema do Hibernate sinh từ entity. Nó không chứng minh migration trong repository có thể tạo đúng schema.

Trong integration test của dự án thật:

1. Khởi chạy database container sạch.
2. Chạy Flyway hoặc Liquibase migrations như production.
3. Đặt `spring.jpa.hibernate.ddl-auto=validate` để Hibernate kiểm tra mapping với schema đã tạo.
4. Chạy contract test của native query trên schema đó.
5. Xác nhận index, constraint và dữ liệu seed cần thiết đã tồn tại.

Ví dụ cấu hình khi migration được bật trong test:

~~~properties
spring.jpa.hibernate.ddl-auto=validate
spring.flyway.enabled=true
~~~

Các property trên giả định dự án đã thêm và cấu hình Flyway. Nếu dùng Liquibase, dùng cơ chế migration tương ứng. Không bật `create-drop` cùng lúc rồi kết luận migration đã được kiểm tra; Hibernate có thể tự tạo schema và che giấu lỗi migration.

Nếu một migration chỉ dùng cú pháp riêng của PostgreSQL, hãy tổ chức migration theo vendor hoặc cung cấp script tương ứng cho từng database bằng cơ chế mà công cụ migration hỗ trợ. Sau đó chạy cùng contract test trên từng schema. Khả năng chuyển database cần bao gồm cả DDL, không chỉ câu SELECT.

## 6. Các khác biệt SQL dễ làm hỏng portability

Native query càng dùng nhiều tính năng riêng, chi phí kiểm thử đa database càng cao.

| Khu vực | Khác biệt có thể gặp | Cách xử lý |
|---|---|---|
| Phân trang | `LIMIT/OFFSET`, `FETCH FIRST`, cú pháp TOP | Dùng `Pageable` khi phù hợp; kiểm tra SQL dialect |
| Boolean | Boolean native, `BIT`, `TINYINT`, literal khác nhau | Dùng kiểu entity phù hợp và test literal trên từng DB |
| Chuỗi | Hàm nối chuỗi, substring, trim, regex | Ưu tiên hàm SQL phổ biến hoặc tách query theo vendor |
| Chữ hoa/thường | Collation và so sánh không phân biệt hoa thường | Test dữ liệu khác casing và cấu hình collation thực tế |
| NULL | `NULLS FIRST/LAST`, thứ tự NULL mặc định | Viết thứ tự NULL tường minh nếu database hỗ trợ; test từng vendor |
| Ngày giờ | Hàm ngày, interval, timezone và độ chính xác timestamp | Bind kiểu thời gian Java phù hợp; kiểm tra timezone và precision |
| Số thập phân | Precision, scale và rounding | Dùng `BigDecimal`, khai báo precision/scale, test giá trị biên |
| Identifier | Từ khóa, quoting và quy tắc chữ hoa/thường | Tránh tên cột/bảng là từ khóa; đặt tên đơn giản |
| JSON/Array | Kiểu và hàm thao tác riêng của từng DB | Cô lập query theo vendor hoặc dùng abstraction phù hợp |
| Upsert | `ON CONFLICT`, `ON DUPLICATE KEY`, `MERGE` | Viết implementation theo database và test cùng contract |
| CTE/Window | Hỗ trợ cú pháp và giới hạn theo phiên bản | Xác định phiên bản tối thiểu và test trên phiên bản đó |
| Generated key | Identity, sequence và cách trả ID | Dùng mapping JPA phù hợp; kiểm thử insert/readback |
| Locking | Lock mode, timeout và isolation | Test trên database triển khai, không chỉ H2 |

### 6.1. Phân trang và thứ tự ổn định

Một query không có `ORDER BY` không bảo đảm thứ tự hàng. Ngay cả khi có `ORDER BY price`, các hàng cùng giá vẫn có thể đổi thứ tự giữa các lần chạy.

Nên thêm một khóa duy nhất làm tie-breaker:

~~~sql
ORDER BY price ASC, id ASC
~~~

Nếu tự viết `LIMIT` trong native SQL, query có thể chỉ chạy trên một số database. Với repository method nhận `Pageable`, Spring Data/Hibernate có thể chuyển phân trang theo dialect. Dù vậy, vẫn phải test query trên từng database và kiểm tra `countQuery`.

### 6.2. NULL và phép so sánh

Trong SQL, `column = NULL` không kiểm tra được giá trị null. Dùng:

~~~sql
WHERE deleted_at IS NULL
~~~

hoặc:

~~~sql
WHERE deleted_at IS NOT NULL
~~~

Thứ tự NULL trong `ORDER BY` có thể khác giữa database. Nếu nghiệp vụ yêu cầu NULL luôn ở cuối, cần viết cách biểu đạt phù hợp với tập database hỗ trợ và kiểm thử thứ tự thực tế. Đừng giả định mọi database có cùng mặc định.

### 6.3. Collation và so sánh chuỗi

Một database có thể so sánh `ABC` và `abc` như bằng nhau do collation không phân biệt hoa thường; database khác có thể phân biệt. Điều này ảnh hưởng tìm kiếm, unique constraint và sắp xếp.

Nếu nghiệp vụ yêu cầu tìm kiếm không phân biệt hoa thường, hãy xác định rõ quy tắc chuẩn hóa. `LOWER(column) = LOWER(?)` có thể dùng trên nhiều database, nhưng có thể ảnh hưởng khả năng dùng index. Cần test cả kết quả lẫn hiệu năng.

### 6.4. Ngày giờ và timezone

Các database khác nhau về kiểu timestamp, timezone, độ chính xác phần lẻ giây và cách chuyển đổi theo session timezone.

Khi native query lọc khoảng thời gian:

~~~sql
WHERE created_at >= ?
  AND created_at < ?
~~~

nên dùng khoảng nửa mở `[start, end)` để tránh trùng dữ liệu ở ranh giới giữa hai khoảng liền kề. Test giá trị ngay trước, đúng tại và ngay sau ranh giới; kiểm tra timezone mà ứng dụng và database đang dùng.

### 6.5. Tham số và SQL injection

Không nối trực tiếp dữ liệu request vào SQL:

~~~java
// Không an toàn: chuỗi đầu vào trở thành một phần câu SQL.
String sql = "SELECT * FROM products WHERE name = '" + name + "'";
~~~

Dùng parameter binding:

~~~java
@Query(
    value = "SELECT p.id, p.name, p.price, p.active "
          + "FROM products p WHERE p.name = ?1",
    nativeQuery = true
)
List<Product> findByExactName(String name);
~~~

Parameter chỉ thay thế giá trị, không thay thế tên bảng, tên cột hoặc từ khóa SQL. Nếu cần sort theo cột do người dùng chọn, ánh xạ lựa chọn đó qua whitelist các tên cột đã được định nghĩa trong code; không nối trực tiếp chuỗi tùy ý vào `ORDER BY`.

### 6.6. Tên cột và quoting

Tên như `order`, `user`, `group` có thể là từ khóa hoặc có ý nghĩa đặc biệt ở một database. Dùng tên bảng/cột rõ ràng, tránh từ khóa phổ biến. Nếu bắt buộc phải quote identifier, cú pháp quote có thể khác giữa database; kiểm thử trên từng vendor.

## 7. Native query trả entity hay DTO?

Kết quả mapping là một phần của tính đúng đắn.

### 7.1. Trả entity

Khi repository trả `Product`, query cần chọn đủ cột được entity mapping yêu cầu:

~~~sql
SELECT p.id, p.name, p.price, p.active
FROM products p
~~~

Nếu entity có thêm cột `created_at` hoặc quan hệ cần mapping, hãy kiểm tra yêu cầu của provider đối với result set. Thiếu cột có thể gây lỗi khi hydrate entity.

Entity trả về là entity managed trong persistence context theo quy tắc query JPA. Nếu chỉ đọc vài trường để hiển thị, tải cả entity có thể không cần thiết.

### 7.2. Trả DTO từ native query

Cú pháp JPQL `SELECT NEW ...` không phải cú pháp SQL thuần. Với native query, có thể dùng:

- Interface projection với alias cột khớp getter.
- `@SqlResultSetMapping` kết hợp `@ConstructorResult`.
- Mapping riêng của provider nếu chấp nhận phụ thuộc Hibernate/EclipseLink.

Ví dụ interface projection:

~~~java
public interface ProductRow {
    Long getProductId();
    String getProductName();
    BigDecimal getUnitPrice();
}
~~~

~~~java
@Query(value = """
       SELECT p.id AS productId,
              p.name AS productName,
              p.price AS unitPrice
       FROM products p
       WHERE p.active = TRUE
       ORDER BY p.id
       """, nativeQuery = true)
List<ProductRow> findActiveRows();
~~~

Alias phải được kiểm tra với provider và database mục tiêu. Một số database/provider có thể thay đổi cách trả nhãn cột hoặc chữ hoa/thường; test projection trên từng database giúp phát hiện sớm vấn đề.

Nếu dùng `@SqlResultSetMapping`, kiểm tra cả tên cột, kiểu JDBC và constructor DTO. Không giả định mapping chạy giống nhau chỉ vì SQL đã chạy.

## 8. Kiểm tra countQuery và phân trang

Với `Page<T>`, query nội dung và query đếm phải mô tả cùng một tập kết quả.

Ví dụ query nội dung:

~~~sql
SELECT p.id, p.name, p.price, p.active
FROM products p
WHERE p.active = TRUE
  AND p.price >= ?
ORDER BY p.price ASC, p.id ASC
~~~

Query đếm tương ứng:

~~~sql
SELECT COUNT(*)
FROM products p
WHERE p.active = TRUE
  AND p.price >= ?
~~~

Nếu query nội dung có join làm một sản phẩm xuất hiện nhiều hàng, `COUNT(*)` có thể đếm hàng join thay vì số sản phẩm. Khi đó cần xem xét `COUNT(DISTINCT p.id)` và cách query nội dung loại trùng.

Với `GROUP BY`, count query thường phải đếm số nhóm chứ không phải số hàng nguồn. Có thể cần một query đếm riêng hoặc subquery phù hợp với database mục tiêu.

Test tối thiểu:

- Trang đầu có đúng số hàng và đúng thứ tự.
- Trang kế tiếp không lặp hoặc bỏ sót hàng.
- `totalElements` bằng số kết quả logic.
- `totalPages` phù hợp với page size.
- Khi không có kết quả, page rỗng và tổng bằng 0.
- Hai hàng cùng giá trị sort vẫn có thứ tự ổn định.

Nếu caller không cần tổng số kết quả, `Slice<T>` có thể phù hợp hơn `Page<T>` vì không cần cung cấp tổng số phần tử. Tuy nhiên, native query dùng `Slice` vẫn cần kiểm thử hành vi phân trang và truy vấn thực tế.

## 9. Dùng H2 đúng vai trò

H2 hữu ích cho test nhanh, nhưng không thể đại diện hoàn toàn cho PostgreSQL, MySQL hoặc MariaDB.

H2 có compatibility mode cho một số database, nhưng mode đó không biến H2 thành cùng SQL engine. Những khác biệt về hàm, kiểu dữ liệu, collation, locking, query planner, DDL và constraint vẫn có thể xuất hiện.

Chiến lược hợp lý:

- Dùng H2 cho test nhanh những truy vấn đơn giản, không phụ thuộc tính năng riêng.
- Dùng Testcontainers với database thật cho native query quan trọng.
- Chạy test trên phiên bản database giống production.
- Giữ contract test dùng chung để so sánh hành vi giữa các vendor.

Không kết luận truy vấn portable chỉ vì nó chạy trên H2 với `MODE=PostgreSQL` hoặc `MODE=MySQL`.

## 10. Kiểm tra hiệu năng sau khi xác nhận tính đúng

Một native query trả đúng dữ liệu vẫn có thể chậm trên database lớn. Correctness test và performance test trả lời hai câu hỏi khác nhau.

Sau khi test đúng kết quả:

1. Kiểm tra index hỗ trợ các cột lọc và sắp xếp.
2. Dùng `EXPLAIN` hoặc công cụ tương ứng của database để xem execution plan.
3. Test với lượng dữ liệu gần production, không chỉ vài hàng fixture.
4. Kiểm tra truy vấn count riêng của `Page`.
5. Đo latency và số hàng đọc/trả về.
6. Kiểm tra N+1 nếu kết quả query được kết hợp với entity relation.

Không so sánh nguyên văn execution plan giữa PostgreSQL và MariaDB; optimizer của mỗi database khác nhau. Hãy xác định tiêu chí hiệu năng có ý nghĩa như thời gian, số hàng đọc, index được sử dụng và giới hạn tài nguyên.

## 11. Khi nào nên chấp nhận SQL riêng theo database?

Có trường hợp ứng dụng cần tính năng đặc thù như JSON operator, full-text search, upsert, array hoặc CTE riêng. Cố ép một câu SQL duy nhất cho mọi database có thể làm query khó đọc và kém hiệu quả.

Khi đó:

1. Xác định rõ database nào được hỗ trợ.
2. Đặt phần SQL riêng trong repository fragment hoặc lớp adapter theo database.
3. Giữ cùng một hợp đồng ở tầng service.
4. Viết cùng một bộ contract test cho từng implementation.
5. Chạy migration và test trên từng database.
6. Ghi rõ database/version tối thiểu mà implementation yêu cầu.

Mục tiêu portability có thể là “cùng hành vi nghiệp vụ trên các implementation riêng”, không nhất thiết là “một chuỗi SQL duy nhất”. Điều quan trọng là sự khác biệt được cô lập và kiểm thử.

## 12. Checklist kiểm thử native SQL

- [ ] Đã xác định database và phiên bản cần hỗ trợ.
- [ ] Query dùng parameter binding, không nối dữ liệu đầu vào vào SQL.
- [ ] Kết quả mapping có đủ cột và đúng kiểu.
- [ ] Có test điều kiện lọc, giá trị biên, NULL và tập kết quả rỗng.
- [ ] Có thứ tự ổn định với tie-breaker duy nhất.
- [ ] Test nội dung trang, trang kế tiếp và count query.
- [ ] Chạy cùng contract test trên từng database mục tiêu.
- [ ] Test dùng đúng phiên bản database gần production.
- [ ] Migration được chạy trên database sạch trước khi validate entity mapping.
- [ ] Không dựa vào H2 để kết luận native SQL portable.
- [ ] Kiểm tra collation, timezone, decimal precision và boolean mapping.
- [ ] DTO/interface projection được kiểm tra alias và kiểu trả về.
- [ ] SQL đặc thù database được cô lập thành implementation riêng.
- [ ] Hiệu năng được đo riêng bằng dữ liệu và execution plan phù hợp.

## 13. Tài liệu tham khảo

- [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html) — khai báo `@Query`, native query, count query và projection.
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html) — tích hợp container với kiểm thử Spring Boot.
- [Testcontainers — PostgreSQL Module](https://java.testcontainers.org/modules/databases/postgres/) — khởi chạy PostgreSQL trong integration test.
- [Testcontainers — MariaDB Module](https://java.testcontainers.org/modules/databases/mariadb/) — khởi chạy MariaDB trong integration test.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/) — native SQL query, parameter binding và result mapping.

Một native query chỉ có thể được coi là đúng khi test xác nhận cả dữ liệu, thứ tự, mapping, count và các trường hợp biên. Khả năng chuyển database cần được chứng minh bằng cách chạy cùng contract test và migration trên từng hệ quản trị mà ứng dụng hỗ trợ. Testcontainers giúp đưa việc kiểm chứng đó vào CI, để thay đổi SQL hoặc nâng cấp database không làm lỗi chỉ xuất hiện sau khi triển khai.
