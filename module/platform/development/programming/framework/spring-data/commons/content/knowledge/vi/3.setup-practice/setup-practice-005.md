# Quan sát phần hành vi chung và phần truy vấn do store tạo ra

## 1. Mục tiêu: đi từ lời gọi Java đến thao tác trên kho dữ liệu

Khi gọi một repository Spring Data, bạn thường chỉ nhìn thấy một phương thức Java:

```java
products.findByActiveTrueAndCategoryOrderByPriceAscSkuAsc("PHU_KIEN");
```

Lời gọi này chứa nhiều tầng trách nhiệm:

- Repository interface biểu đạt yêu cầu của ứng dụng.
- Spring Data Commons cung cấp hợp đồng và hạ tầng dùng chung.
- Store module diễn giải yêu cầu theo công nghệ truy cập dữ liệu.
- Provider hoặc driver, nếu có, thực hiện phần việc tích hợp tiếp theo.
- Kho dữ liệu thực thi thao tác và trả kết quả.

Trong module **SPRING_DATA_COMMONS**, mục tiêu là hiểu các abstraction như repository, CRUD, derived queries, phân trang, sắp xếp, projection và auditing. Bài thực hành này giúp bạn quan sát ranh giới giữa các abstraction đó và phần thực thi cụ thể.

Sau bài học, bạn có thể:

1. Đọc tên phương thức repository thành ý định truy vấn.
2. Đối chiếu ý định đó với dữ liệu và truy vấn thực tế.
3. Phân biệt log SQL với log giá trị tham số.
4. Quan sát sự khác nhau giữa danh sách, `Page`, `Slice` và projection.
5. Giải thích vì sao một lời gọi repository không luôn tương ứng đúng một truy vấn mới.

## 2. Chọn một store để quan sát rõ từng tầng

Bài thực hành chọn Spring Data JPA, Hibernate và H2. Lý do là có thể xem câu SQL cùng tham số, đồng thời đối chiếu chúng với hợp đồng repository.

| Tầng | Trách nhiệm trong ví dụ |
| --- | --- |
| Ứng dụng | Khai báo domain, repository và yêu cầu tìm sản phẩm |
| Spring Data Commons | Hợp đồng repository, metadata, phân tích cấu trúc derived query, kiểu phân trang và projection |
| Spring Data JPA | Tích hợp repository với JPA, xây dựng và thực thi truy vấn qua API JPA |
| Hibernate | Provider JPA, xử lý mapping và sinh SQL theo dialect |
| JDBC driver và H2 | Truyền và thực thi SQL trong cơ sở dữ liệu |

Không nên gộp tất cả thành “Commons sinh SQL”. Với JPA, phần truy vấn được tạo qua cơ chế của Spring Data JPA và được provider dịch thành SQL cụ thể.

Nếu thay JPA bằng MongoDB, hợp đồng chung vẫn có thể quen thuộc nhưng phần truy vấn được quan sát sẽ là filter, sort hoặc command MongoDB. Khi đó không còn đường thực thi qua `EntityManager` và Hibernate.

## 3. Chuẩn bị môi trường thực hành

### 3.1. Dependency và phạm vi ví dụ

Các đoạn test dưới đây dùng cấu trúc Spring Boot 3.x, API `jakarta.persistence`, Hibernate 6 và JUnit 5. Đây là một nền ví dụ cụ thể; khi dùng dòng khác, cần đối chiếu package và cấu hình log tương ứng.

Trong dự án đã có Boot parent hoặc dependency management phù hợp:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>

    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Đặt entity và repository dưới phạm vi mà ứng dụng hoặc test JPA phát hiện. Mẫu test giả định dự án có lớp cấu hình Boot gốc thông thường.

Dùng cơ sở dữ liệu nhúng dành riêng cho test. Các bài kiểm tra nạp fixture trong transaction và mặc định rollback sau mỗi test, nhờ đó các lần quan sát không phụ thuộc thay đổi từ lần trước.

Commons thường được đưa vào thông qua dependency của Spring Data JPA. Chỉ thêm Commons không cung cấp entity manager, JPA provider hoặc kết nối cơ sở dữ liệu.

### 3.2. Bật log truy vấn và tham số

Trong cấu hình test:

```yaml
spring:
  jpa:
    show-sql: false
    properties:
      hibernate:
        format_sql: true
        cache:
          use_second_level_cache: false
          use_query_cache: false

logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
```

Với Hibernate 6:

- `org.hibernate.SQL` giúp quan sát câu SQL.
- `org.hibernate.orm.jdbc.bind` giúp quan sát các giá trị được bind.
- `format_sql` giúp đọc SQL thuận tiện hơn.

Logger bind phụ thuộc phiên bản Hibernate. Không thấy giá trị tham số chưa đủ để kết luận truy vấn không nhận tham số; có thể bạn đang bật sai nhóm logger hoặc mức log chưa phù hợp.

Việc tắt cache cấp hai và query cache giúp giảm yếu tố gây nhiễu. Persistence context của JPA vẫn tồn tại và sẽ được quan sát riêng ở phần sau.

Trong mẫu test dùng `@DataJpaTest(showSql = false)` để không đồng thời có thêm SQL in trực tiếp qua cơ chế `show-sql`. Nhờ vậy, dễ đọc log theo một nguồn hơn.

Log tham số chỉ nên bật khi cần quan sát trên dữ liệu thử phù hợp. Giá trị bind có thể chứa email hoặc thông tin nghiệp vụ, nên không cần duy trì mức TRACE cho mọi môi trường.

## 4. Domain đủ nhỏ để đối chiếu bằng mắt

### 4.1. Entity Product

Mỗi public type trong ví dụ nằm trong tệp Java riêng, cùng package thực hành hoặc có import phù hợp.

```java
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

    @Column(name = "product_name", nullable = false)
    private String name;

    @Column(name = "category_code", nullable = false)
    private String category;

    @Column(nullable = false, precision = 14, scale = 2)
    private BigDecimal price;

    @Column(nullable = false)
    private boolean active;

    protected Product() {
    }

    public Product(
            String sku,
            String name,
            String category,
            BigDecimal price,
            boolean active
    ) {
        this.sku = sku;
        this.name = name;
        this.category = category;
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

    public String getCategory() {
        return category;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public boolean isActive() {
        return active;
    }
}
```

Chú ý hai cặp tên:

- Thuộc tính Java `name` được lưu vào cột `product_name`.
- Thuộc tính Java `category` được lưu vào cột `category_code`.

Derived query và `Sort` được khai báo theo tên thuộc tính domain. Mapping JPA quyết định tên cột trong SQL.

ID được cơ sở dữ liệu sinh trong ví dụ. Không dựa vào giả định ID luôn bắt đầu từ 1 hoặc được cấp lại giống nhau sau mỗi lần rollback.

### 4.2. Projection cho màn hình danh sách

```java
import java.math.BigDecimal;

public interface ProductCard {

    String getSku();

    String getName();

    BigDecimal getPrice();
}
```

Projection chỉ mô tả hình dạng kết quả đọc trong tình huống này. Nó không phải entity mới cần bảng riêng.

### 4.3. Repository dùng cho các phép quan sát

```java
import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository
        extends JpaRepository<Product, Long> {

    List<Product>
    findByActiveTrueAndCategoryOrderByPriceAscSkuAsc(
            String category
    );

    Page<Product> findPageByActiveTrueAndCategory(
            String category,
            Pageable pageable
    );

    Slice<Product> findSliceByActiveTrueAndCategory(
            String category,
            Pageable pageable
    );

    List<ProductCard>
    findByCategoryAndActiveTrueOrderByPriceAscSkuAsc(
            String category
    );
}
```

Ở hai tên `findPageBy...` và `findSliceBy...`, phần mô tả nằm giữa `find` và `By` giúp phân biệt phương thức. Hợp đồng trả về `Page` hay `Slice` được xác định bởi kiểu trả về, không phải vì tên phương thức chứa chữ Page hoặc Slice.

`JpaRepository` là API của store JPA. Nó tái sử dụng và mở rộng các hợp đồng dùng chung của Spring Data. Các kiểu `Page`, `Slice`, `Pageable` thuộc phần dùng chung; `flush` là khả năng gắn với nhánh JPA trong ví dụ.

## 5. Fixture và thứ tự kết quả mong đợi

| SKU | Tên | Nhóm | Giá VND | Active |
| --- | --- | --- | ---: | --- |
| KEY-001 | Bàn phím cơ | PHU_KIEN | 1.200.000 | true |
| MOU-001 | Chuột không dây | PHU_KIEN | 450.000 | true |
| MAT-001 | Tấm lót chuột | PHU_KIEN | 150.000 | true |
| HUB-001 | Bộ chia USB | PHU_KIEN | 450.000 | true |
| MON-001 | Màn hình 24 inch | MAN_HINH | 3.500.000 | true |
| MOU-OLD | Chuột đời cũ | PHU_KIEN | 300.000 | false |

Điều kiện `active = true` và `category = PHU_KIEN` chọn đúng bốn sản phẩm. Sắp xếp theo giá tăng dần rồi SKU tăng dần cho:

```text
MAT-001 → HUB-001 → MOU-001 → KEY-001
```

HUB-001 và MOU-001 cùng giá. SKU duy nhất cung cấp tiêu chí phân định để thứ tự rõ ràng trên tập dữ liệu này.

SKU trong ví dụ dùng ký tự ASCII đơn giản. Khi áp dụng vào dữ liệu thật, quy tắc đối chiếu chuỗi của cơ sở dữ liệu vẫn ảnh hưởng cách sắp xếp và so sánh.

## 6. Khung test: tách bước nạp dữ liệu khỏi bước quan sát

Tạo lớp test trong package thuộc phạm vi cấu hình của ứng dụng:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.util.List;

import jakarta.persistence.EntityManager;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.Sort;

@DataJpaTest(showSql = false)
class ProductRepositoryObservationTest {

    private static final Logger log =
            LoggerFactory.getLogger(
                    ProductRepositoryObservationTest.class
            );

    @Autowired
    private ProductRepository products;

    @Autowired
    private EntityManager entityManager;

    private Long mouseId;

    @BeforeEach
    void prepareFixture() {
        List<Product> saved = products.saveAll(List.of(
                new Product(
                        "KEY-001", "Bàn phím cơ", "PHU_KIEN",
                        new BigDecimal("1200000"), true
                ),
                new Product(
                        "MOU-001", "Chuột không dây", "PHU_KIEN",
                        new BigDecimal("450000"), true
                ),
                new Product(
                        "MAT-001", "Tấm lót chuột", "PHU_KIEN",
                        new BigDecimal("150000"), true
                ),
                new Product(
                        "HUB-001", "Bộ chia USB", "PHU_KIEN",
                        new BigDecimal("450000"), true
                ),
                new Product(
                        "MON-001", "Màn hình 24 inch", "MAN_HINH",
                        new BigDecimal("3500000"), true
                ),
                new Product(
                        "MOU-OLD", "Chuột đời cũ", "PHU_KIEN",
                        new BigDecimal("300000"), false
                )
        ));

        products.flush();

        mouseId = saved.stream()
                .filter(p -> p.getSku().equals("MOU-001"))
                .findFirst()
                .orElseThrow()
                .getId();

        entityManager.clear();
        log.info("FIXTURE_READY");
    }

    private Sort productOrder() {
        return Sort.by(
                Sort.Order.asc("price"),
                Sort.Order.asc("sku")
        );
    }

    // Chèn các phương thức @Test ở những phần tiếp theo vào đây.
}
```

Khung test có hai thao tác chủ ý:

- `flush()` đẩy các thay đổi đang chờ của persistence context xuống cơ sở dữ liệu.
- `clear()` tách các entity đã nạp khỏi persistence context để phép đọc đầu tiên không chỉ trả lại entity còn được quản lý từ bước nạp fixture.

Flush không đồng nghĩa commit. Trong test transaction mặc định, thay đổi vẫn có thể rollback khi test kết thúc.

Dữ liệu nạp sẵn của ứng dụng hoặc script test khác có thể làm fixture không còn đúng sáu bản ghi. Môi trường thực hành cần sử dụng bộ dữ liệu riêng và không tự động nạp thêm dữ liệu ngoài fixture đang xét.

Hãy bắt đầu đọc log của từng phép quan sát tại mốc `OBSERVE_...`, không tính các câu insert trước `FIXTURE_READY` là truy vấn do phương thức tìm kiếm tạo ra.

## 7. Quan sát A: derived query và mapping

Thêm phương thức này vào lớp test:

```java
@Test
void observeDerivedQuery() {
    log.info("OBSERVE_DERIVED_BEGIN");

    List<Product> result =
            products
                .findByActiveTrueAndCategoryOrderByPriceAscSkuAsc(
                        "PHU_KIEN"
                );

    log.info(
            "OBSERVE_DERIVED_END skus={}",
            result.stream().map(Product::getSku).toList()
    );

    assertThat(result)
            .extracting(Product::getSku)
            .containsExactly(
                    "MAT-001", "HUB-001", "MOU-001", "KEY-001"
            );
}
```

### 7.1. Đọc ý định trước khi đọc SQL

| Phần tên phương thức | Ý định |
| --- | --- |
| `ActiveTrue` | Chỉ lấy sản phẩm đang hoạt động |
| `AndCategory` | Kết hợp điều kiện nhóm sản phẩm |
| `OrderByPriceAscSkuAsc` | Giá tăng dần, sau đó SKU tăng dần |

Hạ tầng phân tích dùng chung nhận diện cấu trúc và thuộc tính domain. Spring Data JPA kết hợp với mapping và API truy vấn JPA để thực hiện yêu cầu; Hibernate sinh SQL cho H2.

### 7.2. Đối chiếu hình dạng SQL

SQL có thể có hình dạng tương tự:

```sql
select
    p.id,
    p.active,
    p.category_code,
    p.product_name,
    p.price,
    p.sku
from products p
where p.active = true
  and p.category_code = ?
order by p.price, p.sku
```

Đây là hình minh họa, không phải chuỗi SQL bắt buộc. Alias, thứ tự cột, cách biểu diễn boolean, dấu nháy và cấu trúc SQL có thể khác theo phiên bản, provider hoặc dialect.

Các điều cần xác nhận:

1. Có điều kiện tương ứng với `active = true`.
2. Giá trị `PHU_KIEN` được đưa vào điều kiện nhóm.
3. Thuộc tính `category` đã được ánh xạ thành cột `category_code`.
4. Thứ tự cuối cùng tương ứng giá rồi SKU.
5. Kết quả có đúng bốn sản phẩm theo fixture.

Điều kiện boolean có thể được đưa trực tiếp vào SQL hoặc thể hiện bằng tham số. Không đếm vị trí bind dựa trên một ví dụ minh họa rồi mặc định mọi provider đều giống nhau.

### 7.3. Hai loại log phải đọc cùng nhau

Log SQL có thể chỉ cho thấy:

```text
... category_code = ?
```

Log bind cho biết một tham số nhận giá trị `PHU_KIEN`. Chỉ khi ghép hai loại thông tin mới biết đầy đủ ý nghĩa lời gọi.

Không kết luận “SQL thiếu giá trị” chỉ vì thấy dấu `?`. Prepared statement tách cấu trúc lệnh khỏi giá trị tham số là cách thực hiện bình thường.

## 8. Quan sát B: Page và nhu cầu tổng số phần tử

```java
@Test
void observePage() {
    PageRequest request = PageRequest.of(
            0, 2, productOrder()
    );

    log.info("OBSERVE_PAGE_BEGIN");

    Page<Product> page =
            products.findPageByActiveTrueAndCategory(
                    "PHU_KIEN", request
            );

    log.info(
            "OBSERVE_PAGE_END rows={} total={} pages={}",
            page.getNumberOfElements(),
            page.getTotalElements(),
            page.getTotalPages()
    );

    assertThat(page.getContent())
            .extracting(Product::getSku)
            .containsExactly("MAT-001", "HUB-001");

    assertThat(page.getTotalElements()).isEqualTo(4);
    assertThat(page.getTotalPages()).isEqualTo(2);
    assertThat(page.hasNext()).isTrue();
}
```

### 8.1. Phần chung có thể nhìn thấy từ Java

`PageRequest` biểu đạt:

- Trang đầu tiên, chỉ số 0.
- Kích thước 2.
- Thứ tự theo `price` và `sku`.

`Page` biểu đạt nội dung trang và metadata như tổng số phần tử, tổng số trang. Những kiểu này thuộc phần dùng chung.

### 8.2. Phần do store và provider thực hiện

Trong cấu hình JPA thông thường, với fixture bốn kết quả và trang đầu có hai phần tử, bạn thường quan sát:

- Truy vấn lấy nội dung, có điều kiện lọc và giới hạn kết quả.
- Truy vấn đếm để xác định tổng số phần tử.

Một hình dạng truy vấn đếm là:

```sql
select count(p.id)
from products p
where p.active = true
  and p.category_code = ?
```

Không gắn hợp đồng `Page` với quy tắc “luôn đúng hai SQL”. Một số tình huống cho phép hạ tầng suy ra tổng số mà không thực hiện truy vấn đếm; fetch plan hoặc mapping khác cũng có thể phát sinh thêm thao tác.

Mục tiêu là chứng minh được tổng số 4 đến từ đâu trong lần quan sát, thay vì ghi nhớ một số lượng câu lệnh cố định.

### 8.3. Thử thay đổi một biến

Đổi kích thước trang từ 2 thành 10 rồi quan sát lại. Nội dung chỉ có bốn phần tử; hạ tầng có thể suy ra tổng từ kết quả của trang đầu chưa đầy.

Giữ nguyên điều kiện và dữ liệu giúp bạn hiểu tác động của kích thước trang. Nếu đồng thời đổi dữ liệu, sort và truy vấn, sẽ khó nhận diện nguyên nhân khác biệt.

## 9. Quan sát C: Slice và câu hỏi còn dữ liệu hay không

```java
@Test
void observeSlice() {
    PageRequest request = PageRequest.of(
            0, 2, productOrder()
    );

    log.info("OBSERVE_SLICE_BEGIN");

    Slice<Product> slice =
            products.findSliceByActiveTrueAndCategory(
                    "PHU_KIEN", request
            );

    log.info(
            "OBSERVE_SLICE_END rows={} hasNext={}",
            slice.getNumberOfElements(),
            slice.hasNext()
    );

    assertThat(slice.getContent())
            .extracting(Product::getSku)
            .containsExactly("MAT-001", "HUB-001");

    assertThat(slice.hasNext()).isTrue();
}
```

Kết quả Java vẫn có hai sản phẩm, nhưng hợp đồng không cung cấp tổng số phần tử.

Trong cách thực hiện Slice thông thường của Spring Data JPA, hạ tầng lấy tối đa nhiều hơn kích thước yêu cầu một phần tử để nhận biết còn dữ liệu. Với size bằng 2, giới hạn lấy dữ liệu có thể tương ứng 3, còn nội dung Slice trả về vẫn có 2 phần tử.

Trong log, hãy tìm:

- Điều kiện và thứ tự tương đương phép quan sát Page.
- Giới hạn đọc tương ứng chiến lược phát hiện phần tiếp theo.
- Việc có hay không có truy vấn đếm trong đúng đoạn quan sát.

Đừng nhầm giới hạn đọc 3 với lỗi trả thừa dữ liệu. Đó có thể là phần việc phục vụ `hasNext()`.

So sánh Page và Slice theo yêu cầu giao diện: nếu chỉ có nút “xem thêm”, tổng số trang có thể không cần thiết. Quyết định dùng kiểu nào phải dựa trên chức năng và chi phí đã quan sát.

## 10. Quan sát D: projection và danh sách cột được đọc

```java
@Test
void observeProjection() {
    log.info("OBSERVE_PROJECTION_BEGIN");

    List<ProductCard> cards =
            products
                .findByCategoryAndActiveTrueOrderByPriceAscSkuAsc(
                        "PHU_KIEN"
                );

    log.info(
            "OBSERVE_PROJECTION_END skus={}",
            cards.stream().map(ProductCard::getSku).toList()
    );

    assertThat(cards)
            .extracting(ProductCard::getSku)
            .containsExactly(
                    "MAT-001", "HUB-001", "MOU-001", "KEY-001"
            );
}
```

Trong phép quan sát A, kết quả là entity `Product`. Trong phép quan sát D, kết quả là hình dạng `ProductCard`.

Với closed projection đơn giản của JPA như ví dụ, bạn có thể thấy danh sách chọn tập trung vào `sku`, `product_name` và `price`. Hãy xem SQL thực tế để xác nhận, thay vì suy ra chỉ từ số getter.

So sánh:

| Điểm quan sát | Trả entity | Trả ProductCard |
| --- | --- | --- |
| Kiểu Java người gọi nhận | `Product` | `ProductCard` |
| Thuộc tính người gọi cần | Toàn bộ entity theo mapping | SKU, tên, giá |
| Danh sách cột SQL | Quan sát trong lần truy vấn | Quan sát trong lần truy vấn |
| Khả năng tối ưu | Theo mapping và cách tải | Theo dạng projection và hỗ trợ của store |

Interface projection là một phần cách biểu đạt dùng chung trong Spring Data. Cách xây dựng truy vấn và khả năng chỉ đọc một số trường vẫn thuộc đường thực thi của store.

Một kết quả tốt trong ví dụ phẳng không chứng minh projection lồng nhau hoặc projection có biểu thức sẽ tạo SQL giống hệt. Hãy mở rộng từng yếu tố khi muốn quan sát tiếp.

## 11. Quan sát E: ba lần gọi findById có thể chỉ có hai lần đọc

```java
@Test
void observePersistenceContext() {
    log.info("OBSERVE_ID_FIRST_BEGIN");

    Product first = products.findById(mouseId)
            .orElseThrow();

    log.info("OBSERVE_ID_SECOND_BEGIN");

    Product second = products.findById(mouseId)
            .orElseThrow();

    assertThat(second).isSameAs(first);

    log.info("OBSERVE_CLEAR_CONTEXT");
    entityManager.clear();

    log.info("OBSERVE_ID_THIRD_BEGIN");

    Product third = products.findById(mouseId)
            .orElseThrow();

    assertThat(third).isNotSameAs(first);
    assertThat(third.getSku()).isEqualTo("MOU-001");

    log.info("OBSERVE_ID_END");
}
```

### 11.1. Kết quả cần quan sát

Trong cùng persistence context, với cấu hình thông thường của ví dụ:

1. Lần đầu tìm ID đọc dữ liệu và đưa entity vào context.
2. Lần thứ hai có thể lấy lại chính entity đang được quản lý, không cần SQL select mới.
3. Sau `clear()`, lần thứ ba phải tìm lại; với các cache đã tắt, thường thấy một select mới.

Điều quan trọng là phương thức Java vẫn được gọi ba lần. Việc không có SQL ở lần thứ hai không có nghĩa lời gọi repository bị bỏ qua.

### 11.2. Trách nhiệm nằm ở đâu?

- `findById` thuộc hợp đồng truy cập theo định danh.
- Spring Data JPA tích hợp thao tác đó với `EntityManager`.
- Persistence context và quy tắc quản lý entity thuộc JPA/provider.
- Commons không hứa rằng mọi `findById` ở mọi store đều có cache định danh giống JPA.

Cũng không suy rằng mọi derived query sẽ bị bỏ qua khi entity đã có trong context. Một truy vấn theo điều kiện khác vẫn có thể cần SQL để xác định tập kết quả.

### 11.3. Vì sao cần flush trước clear trong phần chuẩn bị?

`clear()` tách các entity khỏi context. Nếu còn thay đổi chưa đồng bộ, việc clear có thể khiến những thay đổi đó không được tự động ghi như bạn mong đợi.

Trong khung test, fixture được flush trước rồi mới clear. Ở phép quan sát E không sửa entity giữa các lần đọc, nên clear chỉ phục vụ việc tách trạng thái quản lý để quan sát.

Không sử dụng clear như một thao tác mặc định trong code nghiệp vụ chỉ để “buộc có SQL”. Đây là công cụ thí nghiệm cho một câu hỏi cụ thể.

## 12. Quan sát bổ sung: QBE dùng chung ý định nhưng khác đường thực thi

Vì `JpaRepository` hỗ trợ Query by Example, có thể thử cùng điều kiện bằng probe:

```java
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;

Product probe = new Product(
        null, null, "PHU_KIEN", null, true
);

ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnoreNullValues()
        .withIgnorePaths("id");

Example<Product> example = Example.of(probe, matcher);

List<Product> result =
        products.findAll(example, productOrder());
```

Đoạn code đặt bên trong một phương thức test của cùng khung và bổ sung các import tương ứng. Probe chỉ dùng để mô tả điều kiện, không được lưu như một sản phẩm hợp lệ.

Trong probe:

- `category` là `PHU_KIEN`.
- `active` là true.
- `sku`, `name`, `price` là null nên được bỏ qua theo matcher.
- `id` được bỏ qua rõ ràng.

Kết quả mong đợi vẫn là MAT-001, HUB-001, MOU-001, KEY-001. SQL có thể có alias, thứ tự điều kiện hoặc cách tổ chức khác với derived query.

Hai lời gọi cho cùng tập kết quả chưa đủ để kết luận chúng dùng đúng một implementation nội bộ. Chúng chỉ đang biểu đạt cùng điều kiện trên fixture này.

Lớp `Product` dùng `boolean active`, nên false là giá trị thật trên probe chứ không có trạng thái null. Nếu tạo probe bằng constructor mặc định rồi quên đặt active, điều kiện có thể khác mong muốn. Với bộ lọc tùy chọn, cần thiết kế cách biểu đạt “không lọc” một cách rõ ràng.

Ở store khác, trước khi lặp lại thí nghiệm phải kiểm tra mức hỗ trợ Query by Example, matcher và kiểu thuộc tính của store đó.

## 13. Ghi nhận bằng chứng, tránh suy đoán từ một dòng log

Một bản ghi quan sát hữu ích có thể gồm:

| Mục | Ví dụ nội dung |
| --- | --- |
| Đầu vào | `PHU_KIEN`, page 0, size 2, sort giá rồi SKU |
| Hợp đồng Java | `Page<Product>` |
| Mốc log | Từ `OBSERVE_PAGE_BEGIN` đến `OBSERVE_PAGE_END` |
| Truy vấn nội dung | Có lọc active, category và giới hạn kết quả |
| Tham số | Giá trị nhóm và tham số phân trang thực tế |
| Truy vấn bổ sung | Có hoặc không có count trong lần quan sát |
| Kết quả | MAT-001, HUB-001; total 4 |
| Diễn giải | Hợp đồng Page được thực hiện bởi đường JPA đang cấu hình |

Ghi rõ version của Commons, Spring Data JPA, Hibernate và H2 trong môi trường thực hành của bạn. Một thay đổi dialect có thể làm hình dạng SQL khác mà vẫn giữ nguyên hợp đồng Java.

Các câu hỏi đối chiếu nên đi theo thứ tự:

1. Dữ liệu trả về có đúng không?
2. Truy vấn có thể hiện đúng điều kiện và thứ tự không?
3. Giá trị bind có đúng đầu vào không?
4. Có thao tác bổ sung nào cần giải thích không?
5. Kết luận thuộc Commons, store module, provider hay cơ sở dữ liệu?

Không coi khoảng trắng, tên alias hoặc thứ tự cột do provider chọn là hợp đồng nghiệp vụ. Những chi tiết đó thường không phải điều cần cố định trong một bài quan sát.

## 14. Những yếu tố có thể làm log gây hiểu nhầm

### 14.1. SQL nạp fixture bị tính vào truy vấn cần khảo sát

Các insert trong `@BeforeEach` là dữ liệu chuẩn bị. Dùng mốc log và đọc đúng khoảng để tránh kết luận rằng một truy vấn tìm kiếm tạo ra cả loạt insert.

DDL tạo bảng, sequence hoặc thao tác khởi tạo kết nối cũng không phải phần trực tiếp của derived query đang xét.

### 14.2. Auto-flush xảy ra trước một truy vấn đọc

Nếu sửa entity nhưng chưa flush, một truy vấn tiếp theo có thể khiến provider đồng bộ thay đổi trước khi đọc. Log khi đó có thể có update xuất hiện gần một lời gọi tìm kiếm.

Không suy rằng tên phương thức bắt đầu bằng `find` đã tự chứa nghiệp vụ cập nhật. Hãy kiểm tra thay đổi đang chờ trong persistence context và chế độ flush.

### 14.3. SQL bị in hai lần

Khi vừa bật `show-sql` vừa bật SQL logger, cùng một câu lệnh có thể xuất hiện qua hai đường in. Số dòng log lúc đó không đồng nghĩa số lần cơ sở dữ liệu thực thi.

Mẫu test đã tắt `show-sql` và giữ logger để giảm nhầm lẫn này.

### 14.4. Log không cho biết đầy đủ hiệu năng

Một SQL nhìn ngắn không chứng minh truy vấn nhanh. Hiệu năng còn phụ thuộc lượng dữ liệu, index, kế hoạch thực thi, số dòng đọc, tải mạng và cách lấy kết quả.

Fixture sáu sản phẩm phục vụ kiểm tra ý nghĩa. Nó chưa mô phỏng tải production hoặc chứng minh một chiến lược phân trang phù hợp ở quy mô lớn.

### 14.5. Mapping khác làm phát sinh truy vấn khác

Entity Product ở đây không có quan hệ tới entity khác, nên ít yếu tố gây nhiễu. Nếu bổ sung association, fetch plan, callback hoặc listener, một lời gọi có thể làm xuất hiện thêm truy vấn.

Tương tự, khi bổ sung auditing, cần quan sát cả giá trị trường sau thao tác ghi và đường callback/listener của store. Không xác minh auditing chỉ bằng việc đếm số SQL.

## 15. Nếu làm lại với một store khác

Giữ yêu cầu nghiệp vụ và fixture logic:

- Bốn sản phẩm đang hoạt động thuộc PHU_KIEN.
- Sắp xếp theo giá rồi SKU.
- Trang đầu có hai sản phẩm.
- Projection cần SKU, tên, giá.

Thay các phần theo store:

| Giữ để so sánh | Điều chỉnh theo công nghệ |
| --- | --- |
| Ý nghĩa điều kiện lọc | Mapping entity, document hoặc cấu trúc lưu trữ |
| Yêu cầu thứ tự và giới hạn | Repository interface đặc thù và API được hỗ trợ |
| Hình dạng kết quả mong muốn | Cách thực hiện projection |
| Câu hỏi về tổng số hoặc còn dữ liệu | Chiến lược count, limit hoặc cơ chế tương ứng |
| Bộ dữ liệu kiểm soát được | Driver, môi trường test và logger phù hợp |

Với MongoDB, quan sát command/filter/sort thay cho SQL và JDBC bind. Mức log hoặc công cụ theo dõi phải theo driver và phiên bản thực tế.

Không mang kết luận về persistence context của JPA sang một store khác. Cũng không đòi các truy vấn có cùng hình dạng vật lý chỉ vì chúng có cùng tên phương thức Java.

## 16. Kết quả cần đạt sau bài thực hành

Bạn hoàn thành bài khi có thể giải thích những điều sau bằng log và kết quả đã quan sát:

- Derived query dùng tên thuộc tính Java nhưng truy vấn vật lý dùng mapping của store.
- `Pageable` biểu đạt yêu cầu chung, còn limit, offset và count được hiện thực theo đường truy cập cụ thể.
- `Page` và `Slice` trả lời hai nhu cầu metadata khác nhau.
- Projection mô tả hình dạng kết quả; cần xem truy vấn để xác nhận cách đọc dữ liệu.
- Một phương thức repository có thể dẫn đến không có, một hoặc nhiều thao tác truy vấn mới tùy trạng thái và cơ chế liên quan.
- Commons cung cấp hợp đồng và hạ tầng chung; store module, provider và kho dữ liệu quyết định phần thực thi cụ thể.

Mang theo cách quan sát này khi học tiếp CRUD, phân trang, projection, QBE, metadata và auditing: bắt đầu từ hợp đồng Java, kiểm tra dữ liệu trả về, rồi lần theo bằng chứng của đúng store đang dùng.

