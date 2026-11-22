# Phân biệt kiểm thử đơn vị dịch vụ và kiểm thử tích hợp Repository trong Spring Data JPA

## Mục tiêu bài học

Sau bài này, bạn có thể:

1. Phân biệt **unit test cho Service** và **integration test cho Repository** theo **đối tượng thật được kiểm tra**, **phụ thuộc được thay thế**, **cách thiết lập** và **loại lỗi phát hiện được**.
2. Viết kiểm thử Service bằng **JUnit Jupiter (JUnit 5) + Mockito**, không khởi động Spring hay kết nối database.
3. Viết kiểm thử Repository bằng **`@DataJpaTest` + database H2**, dùng Spring Data JPA/Hibernate thật để kiểm tra mapping, truy vấn suy diễn, điều kiện biên và persistence.
4. Hiểu `@Transactional`, `flush()`, `clear()`, rollback mặc định và giới hạn của mỗi kiểu kiểm thử.
5. Chọn cấp kiểm thử phù hợp và phối hợp hai loại nhằm kiểm tra cả **quy tắc nghiệp vụ** lẫn **hành vi truy cập dữ liệu**.

Phạm vi: ứng dụng Java 17+, **Spring Boot 3.5**, **Spring Data JPA**, một service sử dụng `JpaRepository`. Trong bài, “kiểm thử đơn vị dịch vụ” nghĩa là **khởi tạo Service thật với Repository mock**; “kiểm thử tích hợp Repository” nghĩa là **chạy Repository thật thông qua JPA provider cùng một database**.

## 1. Cùng một luồng ứng dụng, hai ranh giới kiểm thử khác nhau

Giả sử ứng dụng quản lý sản phẩm có luồng:

```text
Client
  │
  ▼
Controller
  │
  ▼
ProductService                   ← UNIT TEST: ProductService thật
  │                                 + ProductRepository là Mockito mock
  ▼
ProductRepository               ← INTEGRATION TEST: Repository thật
  │                                 + JPA/Hibernate thật
  ▼
JPA / Hibernate                 ← mapping, SQL, flush, database constraint
  │
  ▼
Database
```

**Unit test Service** hỏi: “Với kết quả mà Repository trả về, Service có xử lý nghiệp vụ đúng không?” Ví dụ: kiểm tra giá không hợp lệ trước khi lưu; chuẩn hóa SKU; từ chối mã trùng; thông báo khi không tìm thấy sản phẩm còn hoạt động.

**Integration test Repository** hỏi: “Khi chạy Repository thực sự qua Spring Data JPA và database, kết quả lưu/truy vấn có đúng không?” Ví dụ: `findByActiveTrueAndPriceGreaterThanEqualOrderByPriceAsc` có trả đúng sản phẩm theo điều kiện, kể cả biên bằng; entity có được persist và tải lại đúng không?

Hai câu hỏi **bổ sung cho nhau**. Service test dùng mock không chứng minh câu SQL đúng; Repository test chạy database không tự chứng minh mọi nhánh nghiệp vụ ở Service đều đúng.

### Bảng so sánh nhanh

| Tiêu chí | Unit test Service | Integration test Repository |
| --- | --- | --- |
| SUT – đối tượng thực sự cần kiểm tra | Class Service và logic trong class | Interface Repository do Spring Data triển khai, entity mapping, JPA provider và database |
| Repository trong test | Mockito mock; không thực thi query | Bean Repository thật do Spring tạo |
| Database | Không cần | Có (H2, PostgreSQL Testcontainers hoặc database test khác) |
| Spring `ApplicationContext` | Thường **không** khởi động | Khởi động **test slice** với `@DataJpaTest` |
| Thư viện nổi bật | JUnit Jupiter, Mockito, AssertJ | JUnit Jupiter, Spring Boot Test, Hibernate/JPA, database |
| Chi phí thời gian | Thường thấp, không kết nối I/O | Thường cao hơn vì dựng context, schema, SQL |
| Lỗi phát hiện tốt | Nhánh if, validate, tính toán, chuyển đổi, phối hợp dependency, ngoại lệ | Tên derived query, JPQL, entity mapping, ràng buộc SQL, flush và dữ liệu thực |
| Lỗi **không** chứng minh được | Query/DDL thật, rollback do proxy Spring, SQL lỗi | Mọi nhánh Service bị bỏ ngoài slice, các giả định từ mock, luồng request đầy đủ |
| Dữ liệu kiểm thử | Stub: `when(...).thenReturn(...)` | Seed: `persist(...)` / `save(...)`, sau đó đọc lại qua JPA |
| Isolation | Mỗi test tạo mock mới; không có dữ liệu DB | `@DataJpaTest` mặc định transactional và rollback sau mỗi test |
| Kết quả mong đợi | Giá trị trả về, exception, lời gọi collaborator | Bản ghi thực, kết quả query, mapping, constraint và trạng thái sau flush/clear |

**Tên annotation không tự quyết định tên cấp kiểm thử.** Dùng `@SpringBootTest` rồi `@MockitoBean` Repository vẫn là test có Spring context; nó kiểm tra wiring/configuration ở mức nào đó nhưng không phải unit test thuần chỉ vì dependency bị mock. Ngược lại, `@DataJpaTest` chạy H2 trong bộ nhớ vẫn là **integration test** vì JPA và database thực sự tham gia.

## 2. Nguyên tắc thiết kế một ca kiểm thử tốt

Dùng mô hình **Arrange – Act – Assert** (tương đương Given – When – Then):

1. **Arrange**: tạo đối tượng đầu vào, đặt hành vi mock (unit) hoặc insert dữ liệu vào DB (integration).
2. **Act**: gọi đúng **một hành vi cần kiểm tra**.
3. **Assert**: khẳng định kết quả nghiệp vụ hoặc trạng thái persistence; chỉ `verify` lời gọi khi tương tác đó thực sự thuộc hợp đồng hành vi.

Một test tốt nên:
- Có tên rõ hành vi, ví dụ `rejectsDuplicateSku` và `findsActiveProductsAtInclusivePriceBoundary`.
- Có dữ liệu **đúng biên**: số bằng ngưỡng, ngay dưới ngưỡng, entity active/inactive, bản ghi không tồn tại.
- Không phụ thuộc vào thứ tự chạy các test khác, không “tái sử dụng” dữ liệu từ test trước.
- Không assert chi tiết triển khai không cần thiết, như số lần gọi getter hay thứ tự các method nội bộ, trừ khi chính thứ tự đó là nghiệp vụ.
- Phản ánh ranh giới test: unit test không cần mạng/database; integration test phải thật sự chạm persistence.

## 3. Ví dụ hoàn chỉnh: cùng một Product, hai lớp kiểm thử

Yêu cầu nghiệp vụ của ví dụ:

- Khi đăng ký sản phẩm: SKU không được rỗng, phải được `trim()`; giá phải lớn hơn 0; không chấp nhận SKU đã có.
- Sản phẩm mới mặc định `active=true`.
- Truy xuất giá bằng SKU chỉ được trả về khi sản phẩm còn active.
- Repository phải tìm đúng sản phẩm active có `price >= minPrice` và sắp xếp theo giá tăng dần.
- Dữ liệu phải được lưu/tải lại đúng qua JPA.

Cấu trúc Maven (mọi class cùng package để Spring Boot quét entity/repository):

```text
service-repository-testing/
├── pom.xml
└── src/
    ├── main/java/com/example/testing/
    │   ├── TestingApplication.java
    │   ├── Product.java
    │   ├── ProductRepository.java
    │   └── ProductService.java
    └── test/java/com/example/testing/
        ├── ProductServiceTest.java
        └── ProductRepositoryTest.java
```

Ví dụ chọn **Spring Boot 3.5.16** với Java 17. Maven cần khả năng tải các dependency từ repository chuẩn trong lần chạy đầu; không cần máy chủ database riêng vì H2 chạy in-memory.

### 3.1. Khai báo dependency — `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>service-repository-testing</artifactId>
    <version>1.0.0</version>

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
```

`spring-boot-starter-data-jpa` cung cấp Spring Data JPA và Hibernate; `h2` là database nhúng khi chạy test; `spring-boot-starter-test` có JUnit Jupiter, Mockito, AssertJ và hạ tầng Spring Test. Nhờ Spring Boot dependency management, các dependency này không cần tự gắn version riêng.

### 3.2. Spring Boot entry point — `TestingApplication.java`

```java
package com.example.testing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TestingApplication {
    public static void main(String[] args) {
        SpringApplication.run(TestingApplication.class, args);
    }
}
```

Class này giúp Spring Boot tìm configuration khi chạy `@DataJpaTest`. **Unit test Service không khởi động class này.**

### 3.3. JPA Entity — `Product.java`

```java
package com.example.testing;

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

    @Column(nullable = false, unique = true, length = 64)
    private String sku;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    @Column(nullable = false)
    private boolean active;

    protected Product() {
        // JPA cần constructor không đối số.
    }

    public Product(String sku, BigDecimal price, boolean active) {
        this.sku = sku;
        this.price = price;
        this.active = active;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public boolean isActive() {
        return active;
    }
}
```

Đây là entity **tối giản phục vụ kiểm thử**. Trong ứng dụng thật, thêm invariant/validation và các phương thức thay đổi trạng thái phù hợp. `unique = true` tạo ràng buộc trong schema do Hibernate tạo cho demo, nhưng độ tin cậy của ràng buộc production phải được kiểm tra với **migration/schema production thực tế**.

### 3.4. Repository thật — `ProductRepository.java`

```java
package com.example.testing;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository extends JpaRepository<Product, Long> {

    boolean existsBySku(String sku);

    Optional<Product> findBySku(String sku);

    Optional<Product> findBySkuAndActiveTrue(String sku);

    List<Product> findByActiveTrueAndPriceGreaterThanEqualOrderByPriceAsc(
            BigDecimal minPrice);
}
```

Spring Data JPA sẽ phân tích tên method và tạo truy vấn. **Bài kiểm thử Repository cần chứng minh hành vi đó trên database**, không được dùng `Mockito.mock(ProductRepository.class)` để “kiểm tra” truy vấn này.

### 3.5. Service chứa nghiệp vụ — `ProductService.java`

```java
package com.example.testing;

import java.math.BigDecimal;
import java.util.NoSuchElementException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Product register(String sku, BigDecimal price) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU must not be blank");
        }
        if (price == null || price.signum() <= 0) {
            throw new IllegalArgumentException("Price must be positive");
        }

        String normalizedSku = sku.trim();
        if (repository.existsBySku(normalizedSku)) {
            throw new IllegalStateException("SKU already exists");
        }

        return repository.save(new Product(normalizedSku, price, true));
    }

    @Transactional(readOnly = true)
    public BigDecimal activePrice(String sku) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU must not be blank");
        }

        String normalizedSku = sku.trim();
        return repository.findBySkuAndActiveTrue(normalizedSku)
                .map(Product::getPrice)
                .orElseThrow(() ->
                        new NoSuchElementException("Active product not found"));
    }
}
```

Phần logic của `register` là:
1. Validate tham số.
2. Chuẩn hóa SKU.
3. Hỏi repository SKU có tồn tại không.
4. Nếu chưa có, tạo `Product` active và gọi `save`.

Phần `activePrice` yêu cầu repository tìm **SKU đang active**; `Optional.empty()` dẫn tới `NoSuchElementException`.

**Giới hạn:** việc gọi `existsBySku` trước `save` không loại bỏ race condition khi hai request cùng đăng ký một SKU. Constraint `UNIQUE` của database vẫn cần thiết để đảm bảo tính duy nhất. Điều này là ví dụ rõ ràng về lý do unit test và integration test cùng cần tồn tại.

## 4. Kiểm thử đơn vị Service: JUnit + Mockito, không Spring

**`src/test/java/com/example/testing/ProductServiceTest.java`**

```java
package com.example.testing;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import java.math.BigDecimal;
import java.util.NoSuchElementException;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class ProductServiceTest {

    @Mock
    private ProductRepository repository;

    @InjectMocks
    private ProductService service;

    @Test
    void registersValidProductWithNormalizedSku() {
        when(repository.existsBySku("BK-01")).thenReturn(false);
        when(repository.save(any(Product.class)))
                .thenAnswer(invocation -> invocation.getArgument(0));

        Product result =
                service.register("  BK-01  ", new BigDecimal("100.00"));

        assertThat(result.getSku()).isEqualTo("BK-01");
        assertThat(result.getPrice()).isEqualByComparingTo("100.00");
        assertThat(result.isActive()).isTrue();

        verify(repository).existsBySku("BK-01");
        ArgumentCaptor<Product> productCaptor =
                ArgumentCaptor.forClass(Product.class);
        verify(repository).save(productCaptor.capture());

        assertThat(productCaptor.getValue().getSku()).isEqualTo("BK-01");
        assertThat(productCaptor.getValue().isActive()).isTrue();
    }

    @Test
    void rejectsNonPositivePriceBeforeRepositoryCall() {
        assertThatThrownBy(() ->
                service.register("BK-02", BigDecimal.ZERO))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("Price must be positive");

        verifyNoInteractions(repository);
    }

    @Test
    void rejectsDuplicateSkuWithoutSaving() {
        when(repository.existsBySku("BK-01")).thenReturn(true);

        assertThatThrownBy(() ->
                service.register("BK-01", new BigDecimal("50.00")))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("SKU already exists");

        verify(repository).existsBySku("BK-01");
        verify(repository, never()).save(any(Product.class));
    }

    @Test
    void readsPriceOnlyForActiveProduct() {
        when(repository.findBySkuAndActiveTrue("BK-03"))
                .thenReturn(Optional.of(
                        new Product("BK-03", new BigDecimal("75.00"), true)));

        BigDecimal price = service.activePrice("  BK-03  ");

        assertThat(price).isEqualByComparingTo("75.00");
        verify(repository).findBySkuAndActiveTrue("BK-03");
    }

    @Test
    void reportsMissingOrInactiveProduct() {
        when(repository.findBySkuAndActiveTrue("BK-04"))
                .thenReturn(Optional.empty());

        assertThatThrownBy(() -> service.activePrice("BK-04"))
                .isInstanceOf(NoSuchElementException.class)
                .hasMessage("Active product not found");

        verify(repository).findBySkuAndActiveTrue("BK-04");
    }
}
```

### Vì sao đây là unit test?

- `@ExtendWith(MockitoExtension.class)` quản lý mock của Mockito cho JUnit Jupiter.
- `@Mock` tạo **ProductRepository giả**; mọi method mock trả về giá trị do test cấu hình (hoặc giá trị mặc định).
- `@InjectMocks` tạo **ProductService thật** và đưa repository mock vào constructor. Không có Spring ApplicationContext, Hibernate hoặc database.
- `when(...).thenReturn(...)` giả lập **kết quả dependency**; `thenAnswer(...)` trong ví dụ trả lại đối tượng được truyền vào `save`, thay cho DB thực.
- `assertThat(...)` khẳng định kết quả; `verify(...)` khẳng định tương tác cần thiết, ví dụ **không lưu** khi input không hợp lệ.
- Test có thể chạy nhanh và độc lập: lỗi của Hibernate/SQL không ảnh hưởng đến phép thử logic service.

**Điểm đặc biệt:** `result.getId()` ở test đầu vẫn thường là `null` vì Mockito không thực hiện `INSERT` hay sinh ID. Không được assert rằng DB đã lưu thành công chỉ vì một mock `save` được gọi.

**Thử nghiệm quan trọng:** nếu đổi sai tên derived method trong Repository, một unit test Service với mock vẫn có thể xanh vì interface mock không chạy truy vấn. Lỗi đó cần kiểm thử integration để phát hiện.

### Nên mock điều gì?

Mock dependency nằm **ngoài ranh giới logic cần kiểm tra**, ví dụ Repository, publisher/email client hoặc clock cố định. Không nên mock chính `ProductService` khi mục đích là kiểm tra quy tắc nghiệp vụ của nó. Không cần mock `Product` nếu đó chỉ là entity đơn giản dùng làm dữ liệu đầu vào/đầu ra.

Mockito không phù hợp để chứng minh SQL, transaction commit/rollback, @Entity mapping hoặc hiệu năng query. Nếu unit test phải cấu hình hàng chục stub để đi qua logic, hãy xem lại cách tách trách nhiệm của service và test data.

## 5. Kiểm thử tích hợp Repository: @DataJpaTest + H2 thật

**`src/test/java/com/example/testing/ProductRepositoryTest.java`**

```java
package com.example.testing;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

@DataJpaTest
class ProductRepositoryTest {

    @Autowired
    private ProductRepository repository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void findsOnlyActiveProductsAtInclusivePriceBoundary() {
        entityManager.persist(
                new Product("BK-90", new BigDecimal("90.00"), true));
        entityManager.persist(
                new Product("BK-100", new BigDecimal("100.00"), true));
        entityManager.persist(
                new Product("BK-150", new BigDecimal("150.00"), true));
        entityManager.persist(
                new Product("BK-200", new BigDecimal("200.00"), false));

        entityManager.flush();
        entityManager.clear();

        List<Product> actual =
                repository.findByActiveTrueAndPriceGreaterThanEqualOrderByPriceAsc(
                        new BigDecimal("100.00"));

        assertThat(actual)
                .extracting(Product::getSku)
                .containsExactly("BK-100", "BK-150");
    }

    @Test
    void persistsAndReloadsEntityMapping() {
        Product inserted = entityManager.persistAndFlush(
                new Product("BK-09", new BigDecimal("19.90"), true));
        Long generatedId = inserted.getId();

        entityManager.clear();

        Product reloaded = repository.findBySku("BK-09").orElseThrow();

        assertThat(generatedId).isNotNull();
        assertThat(reloaded.getId()).isEqualTo(generatedId);
        assertThat(reloaded.getSku()).isEqualTo("BK-09");
        assertThat(reloaded.getPrice()).isEqualByComparingTo("19.90");
        assertThat(reloaded.isActive()).isTrue();
    }

    @Test
    void excludesInactiveProductFromActiveSkuQuery() {
        entityManager.persistAndFlush(
                new Product("OFF-01", new BigDecimal("40.00"), false));
        entityManager.clear();

        assertThat(repository.findBySkuAndActiveTrue("OFF-01"))
                .isEmpty();
    }

    @Test
    void checksSkuExistenceAgainstPersistedData() {
        entityManager.persistAndFlush(
                new Product("EX-01", new BigDecimal("30.00"), true));
        entityManager.clear();

        assertThat(repository.existsBySku("EX-01")).isTrue();
        assertThat(repository.existsBySku("ABSENT-01")).isFalse();
    }
}
```

### Vì sao đây là integration test?

`@DataJpaTest` dựng một **phần Spring ApplicationContext chỉ tập trung JPA**: tìm `@Entity`, tạo DataSource, EntityManagerFactory, TransactionManager và các Repository Spring Data. Với H2 trên test classpath, nó sử dụng embedded database theo cấu hình mặc định. Các thao tác `persist`, `flush` và truy vấn Repository gửi tới **Hibernate và database thật**.

Không có `@Mock` ở đây: `ProductRepository` là bean do Spring Data JPA tạo. Vì vậy test có thể phát hiện:
- Tên method sai thuộc tính (ví dụ `findByPricee...`) khiến Spring Data không tạo được query.
- Lỗi mapping cột hoặc sai kiểu dữ liệu.
- Điều kiện `>=` bị viết nhầm `>`, lọc `active` sai, thứ tự kết quả sai.
- Dữ liệu không được lưu hoặc không tải lại đúng sau khi xóa persistence context.
- Một số lỗi constraint và JPQL/SQL chỉ xuất hiện khi truy vấn hoặc `flush` thực thi.

**Vì sao test dùng `entityManager.flush()` rồi `entityManager.clear()`?** `flush()` gửi các câu ghi đang chờ vào database trong transaction hiện tại; `clear()` xóa các entity đang được quản lý khỏi L1 cache. Truy vấn sau đó phải tái nạp trạng thái thông qua persistence layer, tránh một phép thử “xanh” chỉ vì object cũ còn trong persistence context. Dù vậy `flush()` **chưa phải commit**, và sau test dữ liệu mặc định bị rollback.

### SQL thật và giới hạn H2

Test này có SQL thực thi trên H2, nên là integration test. Tuy nhiên **H2 không tương đương mọi hệ quản trị production**: JSONB, array, collations, timezone, locking, index hints, native PostgreSQL query, transaction isolation và dialect có thể khác. Nếu production là PostgreSQL và query dùng tính năng riêng PostgreSQL, cần integration test chạy **PostgreSQL thật** (thường là Testcontainers) với migration schema production. Không nên dùng mock để thay thế cho phần kiểm chứng database đặc thù đó.

## 6. Chạy ví dụ và đọc kết quả

Trong thư mục chứa `pom.xml`, cần **JDK 17+ và Maven**. Chạy toàn bộ:

```bash
mvn test
```

Chạy riêng từng lớp nếu muốn so sánh phạm vi:

```bash
mvn -Dtest=ProductServiceTest test
mvn -Dtest=ProductRepositoryTest test
```

Với cấu hình và mã nguồn như trên, kỳ vọng:
- `ProductServiceTest` có **5 ca**: đăng ký thành công, giá không hợp lệ, SKU trùng, lấy giá active, không tìm thấy/không active.
- `ProductRepositoryTest` có **4 ca**: lọc active với biên bao gồm, round-trip mapping, loại inactive, xác minh tồn tại SKU.
- Tổng cộng **9 test**, tất cả **PASS** nếu môi trường/dependency hoạt động đúng; chi tiết log, thời gian chạy và dòng tổng kết Maven khác nhau theo phiên bản/plugin nên không ràng buộc stdout cố định.

Trường hợp lỗi, đọc stack trace theo **lớp**: thất bại trong `ProductServiceTest` gợi ý logic/stub/assertion; thất bại khi khởi tạo `ProductRepositoryTest` có thể do entity/query mapping, H2/DDL hoặc cấu hình JPA; thất bại khi `flush` có thể do constraint, kiểu cột hoặc dữ liệu.

## 7. Cần phân biệt @Mock, @MockitoBean, @DataJpaTest và @SpringBootTest

| Cách viết | Tác dụng | Khi nào dùng |
| --- | --- | --- |
| `@Mock` của Mockito | Tạo đối tượng giả do Mockito quản lý | Unit test Service không khởi động Spring |
| `@InjectMocks` | Dựng class thật và tiêm các mock vào dependency | Unit test của class có constructor rõ ràng |
| `@MockitoBean` của Spring Test | Thay thế một bean trong **Spring ApplicationContext** bằng Mockito mock | Test có Spring context, ví dụ test Controller/service wiring; không cần trong unit test thuần |
| `@DataJpaTest` | Khởi động slice JPA, Repository thật và database test | Integration test Repository/entity/query |
| `@SpringBootTest` | Khởi động context ứng dụng rộng hơn, có thể có nhiều tầng | Kiểm tra tích hợp Service–Repository–DB, transaction proxy, wiring hoặc luồng ứng dụng |

Từ Spring Framework 6.2 và Spring Boot 3.4+, `@MockitoBean` là annotation chuẩn dùng để override Spring bean trong test có context; annotation cũ `@MockBean` của Spring Boot đã bị deprecated trong nhánh 3.4. **Đừng đặt `@MockitoBean` vào unit test thuần rồi kỳ vọng nó tự tạo Spring context**: Mockito `@Mock` đúng và nhẹ hơn cho bài kiểm tra Service không dùng Spring.

`@DataJpaTest` thông thường **không đưa Service thông thường được đánh dấu `@Service` vào context**. Nếu muốn kiểm thử chính Service dùng Repository thật và kiểm chứng `@Transactional`, dùng một integration test có cấu hình context phù hợp, thường `@SpringBootTest` kết hợp database thử nghiệm. Không nhầm test slice Repository với full-stack end-to-end test.

## 8. @Transactional và rollback: rất dễ tạo test “xanh giả”

### 8.1. @Transactional ở Service unit test

Trong `ProductServiceTest`, `@InjectMocks` gọi constructor trực tiếp; service **không đi qua Spring AOP transaction proxy**. Do đó:
- `@Transactional` trong `ProductService` **không thực sự mở transaction** ở unit test.
- Unit test có thể kiểm tra việc ném exception, nhưng **không chứng minh database rollback** khi exception đó xảy ra.
- Test unit nhanh là chủ đích; không nên coi nó là bằng chứng về transaction semantics.

### 8.2. @DataJpaTest rollback mặc định

`@DataJpaTest` mặc định chạy mỗi test trong một transaction và **rollback khi kết thúc**. Điều này giúp các test độc lập và không để lại bản ghi. Vì test transaction còn mở, `flush()` cho phép quan sát constraint/truy vấn nhưng **không kiểm tra đầy đủ những hành vi chỉ xảy ra lúc commit hoặc sau commit**, chẳng hạn event after-commit.

Nếu một tính năng yêu cầu commit thật, cân nhắc integration test tách biệt có ranh giới transaction rõ, ví dụ `TestTransaction.flagForCommit()` + `TestTransaction.end()` ở test Spring transactional có hỗ trợ; nhớ quản lý dọn dữ liệu sau commit. Với test qua HTTP `@SpringBootTest(webEnvironment = RANDOM_PORT)`, server thường chạy transaction ở thread riêng, nên rollback transaction ở test client **không rollback** giao dịch server.

### 8.3. Flush trước khi kiểm tra constraint

Hibernate có thể trì hoãn SQL INSERT/UPDATE đến flush/commit. Nếu kiểm thử UNIQUE, NOT NULL hoặc foreign key mà chỉ gọi `repository.save(entity)` rồi assert không exception, bạn có thể bỏ qua lỗi xuất hiện muộn. Hãy dùng `entityManager.flush()` hoặc `repository.saveAndFlush(...)` trong test integration để đưa SQL ra database. Lưu ý một số constraint deferred trên database production chỉ bị kiểm tra ở **commit**, cần test phù hợp.

### 8.4. Dirty checking và L1 cache

Khi cùng EntityManager giữ object managed, `findById` có thể trả đúng object đó mà chưa cần SELECT mới. Muốn kiểm tra database round-trip, `flush` rồi `clear`. Nhưng `clear()` detach toàn bộ entity trong persistence context; nếu có dữ liệu chưa flush, thay đổi có thể mất. Đây là thao tác có chủ đích trong fixture test, không phải pattern tùy tiện trong nghiệp vụ.

## 9. Những trường hợp mà một loại test không thể thay loại kia

### Trường hợp 1: Derived query bị đổi sai

Developer đổi repository từ:

```java
List<Product> findByActiveTrueAndPriceGreaterThanEqualOrderByPriceAsc(
        BigDecimal minPrice);
```

thành:

```java
List<Product> findByActiveTrueAndPriceGreaterThanOrderByPriceAsc(
        BigDecimal minPrice);
```

Mã vẫn hợp lệ nhưng mất dấu bằng tại biên. Unit test của Service vẫn có thể PASS vì mocked Repository trả dữ liệu đã chuẩn bị sẵn. Test Repository seed sản phẩm giá **đúng bằng 100.00** sẽ FAIL vì bản ghi bị loại. Đó là nguyên nhân cần test hành vi query thực.

### Trường hợp 2: Service kiểm tra giá sai

Developer đổi `price.signum() <= 0` thành `price.signum() < 0`, vô tình cho phép giá **0**. Repository integration tests chỉ dùng dữ liệu hợp lệ có thể vẫn PASS. Unit test `rejectsNonPositivePriceBeforeRepositoryCall` sẽ FAIL. Đó là nguyên nhân nên kiểm thử logic Service trực tiếp.

### Trường hợp 3: SKU trùng do hai giao dịch đồng thời

Hai request cùng gọi `existsBySku("BK-01")` và cùng thấy `false`; sau đó đều lưu. Unit test xác nhận nhánh kiểm tra trùng hoạt động, nhưng không thể đảm bảo xử lý race. Constraint UNIQUE trên database mới giữ dữ liệu hợp lệ dưới concurrency. Integration test kết hợp transaction đồng thời/DB production mới chứng minh đầy đủ race handling; Service nên chuyển lỗi ràng buộc thành lỗi nghiệp vụ thích hợp theo thiết kế API.

### Trường hợp 4: Giao dịch phải rollback cả chuỗi thao tác

Service lưu Product rồi gọi một thao tác thứ hai gây lỗi; yêu cầu là **toàn bộ thay đổi phải rollback**. Unit test mock có thể xác nhận nhánh ném lỗi hoặc lời gọi, nhưng không thể chứng minh rollback thật. Repository slice cũng chưa đủ vì không bao gồm transaction boundary của Service. Cần integration test với **Service bean thật + Repository bean thật + database**, gọi service qua Spring proxy và kiểm tra DB sau khi transaction kết thúc.

## 10. DataJpaTest, schema, migration và database trong test

Có ba cấp mức độ sát production:

| Cách dựng database | Ưu điểm | Giới hạn / nên dùng khi |
| --- | --- | --- |
| H2 embedded theo `@DataJpaTest` | Nhẹ, nhanh, chạy offline sau khi đã tải dependencies | Tốt cho JPQL và mapping phổ thông; không chứng minh dialect/SQL của PostgreSQL, MySQL... |
| Database test cục bộ/cấu hình riêng | Có thể kiểm tra engine thật | Cần cô lập môi trường, schema, data và thao tác dọn |
| Testcontainers với DB cùng loại/version production | Cô lập và gần thực tế hơn; bắt lỗi SQL/dialect/schema đặc thù | Khởi tạo chậm hơn, cần runtime container; muốn đúng phải chạy migration gần production |

### Không thay thế DataSource khi cần database thật

`@DataJpaTest` mặc định có thể tự thay application DataSource bằng embedded database khi H2 nằm trên classpath. Nếu muốn **giữ** DataSource test đã cấu hình, sử dụng (theo Spring Boot 3.5):

```java
@DataJpaTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE
)
class ProductRepositoryDatabaseTest {
    // Các test dùng DataSource cấu hình bởi môi trường test.
}
```

Cần import `org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase` và `org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest`. Đoạn này **minh họa cấu hình**, không phải test độc lập để copy thêm vào project ở mục 3. Chỉ dùng `Replace.NONE` khi test thực sự cung cấp URL, credential và database riêng (thường qua Testcontainers/`@DynamicPropertySource` hoặc service connection); nếu không, bạn có thể vô tình chạm database ngoài ý định.

### Test schema thật thay vì chỉ dựa vào ddl-auto

Hibernate `ddl-auto=create-drop` tạo schema từ entity; đây là tiện ích cho demo, nhưng có thể che lỗi migration. Nếu production dùng Flyway/Liquibase, integration test quan trọng nên chạy migration thực tế trên database thử nghiệm rồi xác minh entity mapping/query. Đừng sửa SQL migration chỉ để khớp một hành vi khác biệt của H2 khi production là PostgreSQL.

## 11. Thiết kế bộ test hiệu quả trong dự án Spring Data JPA

Một chiến lược thực tế:

1. **Unit test Service** cho mỗi nhánh nghiệp vụ có ý nghĩa: validate, chuyển đổi dữ liệu, quyết định gọi repository, xử lý `Optional.empty()`, exception và event được yêu cầu.
2. **Repository integration test** cho query custom/derived có logic, đặc biệt `AND`/`OR`, khoảng ngày giờ, `JOIN FETCH`, `@EntityGraph`, projection, pagination, unique/foreign key và SQL đặc thù.
3. **Service integration test** khi cần chứng minh transaction AOP, rollback, optimistic locking, chain nhiều repository, event sau commit hoặc việc phối hợp bean thật.
4. **API/end-to-end test** cho serialization, security, HTTP contract, routing và các tầng triển khai; chỉ chọn kịch bản đại diện thay vì lặp lại mọi unit case.
5. **Đo hiệu năng/reliability riêng** cho N+1, query count, lock contention, race condition: đa số test đúng giá trị không tự chứng minh hiệu năng hoặc concurrency.

Tên test nên nói rõ điều kiện và kết quả, ví dụ `findsActiveProductsAtInclusivePriceBoundary`, không chỉ `testFindAll`. Ở Repository, insert dữ liệu bằng `TestEntityManager` hoặc SQL fixture rồi query bằng **Repository thật**; tránh dùng đúng phương thức đang kiểm tra vừa để seed vừa để xác nhận vì dễ tự hợp thức hóa lỗi.

Để tránh test flakiness:
- Không phụ thuộc thứ tự record nếu query **không có `OrderBy`**; dùng `containsExactlyInAnyOrder` khi nghiệp vụ không yêu cầu sắp xếp.
- Với thời gian, dùng `Clock` hoặc `Instant` cố định thay vì `Instant.now()` trong assertion biên.
- Tránh số thập phân `double` cho tiền; dùng `BigDecimal` và so sánh số học.
- Khi kiểm tra persistence, `flush` + `clear` để phân biệt dữ liệu ở L1 và DB.
- Với xử lý bất đồng bộ, đợi trên điều kiện có giới hạn và ổn định; tránh `Thread.sleep` tùy tiện.
- Không chia sẻ mutable test data hoặc database state giữa các test nếu không có cơ chế isolation rõ.

## 12. Checklist chọn loại kiểm thử theo câu hỏi

| Bạn cần kiểm chứng điều gì? | Kiểu kiểm thử phù hợp |
| --- | --- |
| SKU rỗng hoặc giá ≤ 0 bị chặn trước khi lưu? | Unit test Service |
| Service gọi `existsBySku` với SKU đã trim? | Unit test Service |
| Service ném exception khi repository trả `Optional.empty()`? | Unit test Service |
| Method `findBy...GreaterThanEqual` lấy đúng giá trị bằng biên? | Repository integration |
| Entity map cột `price` đúng precision/scale? | Repository integration, với DB tương ứng |
| JPQL/native query thực thi đúng dialect production? | Repository integration trên database cùng loại production |
| UNIQUE/foreign key/NULL constraint thật có hiệu lực? | Repository integration (flush/commit theo loại constraint) |
| `@Transactional` ở Service có rollback nhiều lần ghi khi lỗi? | Service integration với Spring proxy và database thật |
| Controller trả status/JSON đúng? | MVC/API test, phạm vi lớn hơn bài này |
| Hai request đồng thời có tránh lost update? | Integration/concurrency test với DB, transaction và locking thật |

## 13. Lỗi thường gặp và cách khắc phục

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Mock Repository trong test tên “RepositoryIntegrationTest” | Không chạy query, không kiểm tra mapping/SQL | Dùng `@DataJpaTest` và Repository bean thật |
| Bật `@SpringBootTest` cho mọi Service unit test | Chậm, dễ phụ thuộc cấu hình ngoài ý muốn | Dùng `@ExtendWith(MockitoExtension.class)` khi chỉ test logic |
| Dùng `@Mock` nhưng mong Spring tự inject vào context | Spring không override bean ứng dụng | Với test có context, dùng `@MockitoBean`; unit không cần context |
| Gọi `save` mock rồi assert DB có record | Mock không lưu database và không sinh ID thật | Kiểm tra tương tác ở unit; lưu/tải DB ở integration |
| Chỉ test “happy path” | Không bắt điều kiện biên, null, thiếu dữ liệu | Thêm ca đúng biên, sai input, duplicate, inactive |
| Không `flush` khi test constraint | Exception có thể chưa xảy ra | Flush hoặc commit trong test phù hợp |
| Không `clear` khi xác minh round-trip | L1 có thể che lỗi đọc lại | Flush rồi clear trước khi load lại |
| Tưởng `@DataJpaTest` kiểm thử `@Transactional` Service | Service thường không có trong slice | Service integration test với Spring proxy |
| Tin H2 phản ánh mọi SQL production | Có thể bỏ sót khác biệt dialect/locking | Testcontainers hoặc DB đúng loại/version |
| Assert thứ tự nhưng không ORDER BY | Test flaky theo execution plan | Thêm order rõ hoặc assert không phụ thuộc thứ tự |
| Lạm dụng `verify(..., times(1))` cho mọi lời gọi | Test gắn chặt implementation, dễ vỡ khi refactor | Chỉ verify tương tác thể hiện hành vi bắt buộc |
| Dùng `@DirtiesContext` quá rộng để dọn test data | Chậm đáng kể vì dựng lại context | Ưu tiên rollback/fixture isolation có kiểm soát |

## 14. Bài tập tự luyện

**Bài A — Unit test:** Thêm vào `ProductService.register` quy tắc: SKU phải dài tối thiểu 4 ký tự sau `trim()`. Viết test xác nhận SKU ngắn bị từ chối **trước mọi repository call**. Không dùng Spring context.

**Bài B — Repository integration:** Thêm `List<Product> findByActiveTrueAndPriceLessThanOrderByPriceAsc(BigDecimal ceiling)`. Seed ba giá `99.99`, `100.00`, `100.01`, đều active, sau đó query với trần `100.00`. Kết quả phải chứa **chỉ 99.99**, vì `LessThan` là `<`.

**Bài C — Kiểm tra mapping:** Tạo một Product, `persistAndFlush`, `clear`, sau đó tải theo SKU. So sánh trường `id`, `price` và `active`. Nếu không clear, bạn đang kiểm tra thêm điều gì từ L1 mà chưa chứng minh được về round-trip?

**Bài D — Thiết kế mức test:** Service cập nhật hai entity trong một transaction rồi ném exception. Loại test nào chứng minh **cả hai lần cập nhật đều rollback**? Cần dựng dependency thật và transaction boundary ra sao?

**Đáp án gợi ý:**
- A: Unit test `@Mock` repository và `verifyNoInteractions(repository)`.
- B: `@DataJpaTest` với seed thật, `flush/clear` và assert chỉ một SKU.
- C: Chưa loại trừ khả năng object đang managed ở L1 được trả lại mà không cần lấy từ DB.
- D: Service integration test có **Spring-managed Service thật**, Repository thật và DB thử nghiệm; kiểm tra DB sau transaction kết thúc, không chỉ verify mock.

## 15. Ghi nhớ

**Unit test Service = Service thật + Repository mock → kiểm tra logic/nghiệp vụ.**  
**Integration test Repository = Repository thật + JPA thật + DB → kiểm tra mapping/truy vấn/persistence.**

Hai lớp test có mục tiêu và chi phí khác nhau; chúng không thay thế nhau. `@Transactional` của Service chỉ được kiểm tra đúng khi Service chạy **qua Spring proxy** trong integration test phù hợp. Đừng nhầm `flush` với `commit`, cũng đừng nhầm dữ liệu L1 với dữ liệu đã được tải lại từ DB.

### Tài liệu chính thức

- Spring Boot 3.5 – Testing: https://docs.spring.io/spring-boot/3.5/reference/testing/index.html
- Spring Boot 3.5 – Auto-configured Data JPA Tests và TestEntityManager: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html#testing.spring-boot-applications.autoconfigured-tests
- Spring Framework 6.2 – `@MockitoBean` và `@MockitoSpyBean`: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html
- Spring Data JPA – Query Methods: https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html
- Spring Framework – Test-managed transactions: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html
