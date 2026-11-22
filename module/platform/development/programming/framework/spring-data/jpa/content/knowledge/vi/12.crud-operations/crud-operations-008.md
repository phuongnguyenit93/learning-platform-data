# existsById, count và chi phí truy vấn

## Mục tiêu

Spring Data JPA cung cấp các thao tác kiểm tra sự tồn tại và đếm bản ghi như `existsById`, `existsBy...`, `count` và `countBy...`. Chúng đều trả về kết quả nhỏ gọn (`boolean` hoặc `long`), nhưng có mục đích và chi phí khác nhau.

- `existsById(id)` trả lời một entity có tồn tại theo khóa chính hay không.
- `existsBy...` là query method do ứng dụng khai báo, dùng điều kiện trên thuộc tính entity để kiểm tra có bản ghi phù hợp hay không.
- `count()` đếm số entity trong repository domain.
- `countBy...` đếm số bản ghi thỏa điều kiện.

Chọn đúng thao tác giúp tránh tải entity không cần thiết, tránh đếm dữ liệu chỉ để kiểm tra có hay không, và hạn chế số truy vấn lặp trong vòng lặp hoặc phân trang.

## 1. existsById(): kiểm tra theo khóa chính

`JpaRepository` kế thừa `CrudRepository`, trong đó có:

```java
boolean existsById(ID id);
```

Ví dụ:

```java
boolean exists = productRepository.existsById(42L);
if (!exists) {
    throw new EntityNotFoundException("Product not found");
}
```

Phương thức trả về `true` nếu có entity mang khóa chính đó và `false` nếu không có. Nó không trả entity.

### SQL thường được thực thi

Trong các phiên bản Spring Data JPA hiện đại, `SimpleJpaRepository.existsById` thường tạo một count query theo ID thay vì hydrate toàn bộ entity:

```sql
select count(p)
from Product p
where p.id = ?
```

Đây là dạng JPQL khái niệm. Hibernate chuyển thành SQL theo dialect, có thể dùng alias và tên cột khác. Với khóa chính có index, database thường có thể kiểm tra nhanh bằng index mà không cần đọc toàn bộ entity.

Đây là chi tiết triển khai phổ biến, không phải cam kết rằng mọi phiên bản/provider đều phát đúng một câu SQL giống hệt. Với composite ID, một số đường xử lý có thể fallback sang `findById` do khác biệt bind tham số. Khi cần tối ưu cụ thể, hãy bật SQL logging và đo trên phiên bản thực tế.

### Khi nào nên dùng existsById?

- Khi chỉ cần câu trả lời có/không theo primary key.
- Khi không cần các thuộc tính khác của entity.
- Khi muốn tránh hydrate entity và các quan hệ liên quan.

Nếu cần cập nhật entity ngay sau đó, thường nên dùng `findById` hoặc `EntityManager.find` để tải managed entity trong transaction rồi thực hiện thao tác. Gọi `existsById` rồi lại `findById` thường tạo hai lần round-trip.

## 2. existsBy...: query method kiểm tra theo thuộc tính

Spring Data JPA có thể tạo query kiểm tra sự tồn tại từ tên phương thức:

```java
boolean existsBySku(String sku);
boolean existsByCategoryAndActiveTrue(String category);
```

Spring Data phân tích phần `existsBy` và các predicate sau đó dựa trên thuộc tính Java của entity. Query có thể chỉ lấy thông tin đủ để xác định có kết quả, thay vì trả toàn bộ entity. Cách SQL chính xác phụ thuộc phiên bản Spring Data JPA và JPA provider; query derivation thường dùng giới hạn kết quả để không cần lấy mọi hàng phù hợp.

Ví dụ sử dụng:

```java
if (productRepository.existsBySku(sku)) {
    throw new DuplicateSkuException(sku);
}
```

Phương thức này kiểm tra theo `sku`, không yêu cầu `sku` là primary key. Tên thuộc tính phải khớp property trong entity; nếu Java field là `sku` nhưng cột database là `product_code`, tên method vẫn là `existsBySku`.

### existsBy và countBy khác nhau

- `existsBySku(sku)` trả lời có ít nhất một hàng thỏa điều kiện hay không.
- `countBySku(sku)` đếm chính xác số hàng thỏa điều kiện.

Nếu nghiệp vụ chỉ cần boolean, không nên dùng `countBySku(sku) > 0` vì mục tiêu đếm chính xác có thể buộc database làm nhiều công việc hơn mức cần thiết. Dùng `existsBySku` diễn đạt đúng ý định và cho phép framework/provider chọn chiến lược kiểm tra phù hợp.

## 3. count(): đếm tất cả entity

`JpaRepository` cung cấp:

```java
long count();
```

Ví dụ:

```java
long totalProducts = productRepository.count();
```

`count()` trả số entity theo repository domain. Với entity đơn giản, SQL thường có dạng:

```sql
select count(*)
from products
```

Spring Data JPA thường tạo count query JPQL rồi để provider chuyển thành SQL. Query có thể phức tạp hơn khi entity dùng inheritance, filter, mapping đặc biệt hoặc query được tùy biến.

Kiểu trả về là `long` vì số bản ghi có thể vượt giới hạn của `int`. Không ép về `int` nếu không có kiểm tra phạm vi.

## 4. countBy...: đếm theo điều kiện

Query derivation hỗ trợ đếm theo thuộc tính:

```java
long countByActiveTrue();
long countByCategory(String category);
long countByCategoryAndActiveTrue(String category);
```

Ví dụ:

```java
long activeBooks = productRepository.countByCategoryAndActiveTrue("BOOK");
```

SQL khái niệm:

```sql
select count(*)
from products
where category = ?
  and active = true
```

Điều kiện được phân tích từ tên method và property của entity. Có thể kết hợp các predicate như `And`, `Or`, `IsNull`, `In`, `Between` hoặc điều kiện trên quan hệ, miễn là cú pháp query derivation hỗ trợ.

Đếm theo quan hệ có thể phát sinh join. Ví dụ `countByCategoryName("Books")` có thể cần join giữa product và category. Khi đó cần xem SQL và execution plan để hiểu chi phí thực tế.

## 5. COUNT và EXISTS có chi phí khác nhau

`COUNT` phải trả về số lượng chính xác. `EXISTS` chỉ cần xác định có ít nhất một hàng phù hợp. Khác biệt này quan trọng khi tập kết quả lớn.

| Nhu cầu | Cách phù hợp | Lý do |
| --- | --- | --- |
| Kiểm tra một ID có tồn tại | `existsById(id)` | Chỉ cần boolean theo primary key. |
| Kiểm tra có bản ghi theo SKU/email | `existsBySku(value)` | Query method thể hiện đúng mục đích tồn tại. |
| Đếm tổng số bản ghi | `count()` | Cần số lượng chính xác. |
| Đếm bản ghi theo trạng thái | `countByStatus(status)` | Cần số lượng chính xác trong nhóm. |
| Lấy dữ liệu để hiển thị hoặc cập nhật | `findById` / query trả entity | Cần nội dung entity, không chỉ boolean. |

### COUNT(*) có luôn quét toàn bộ bảng không?

Không thể kết luận chỉ từ câu SQL. Database có thể dùng index, index-only scan, thống kê, partition pruning hoặc chiến lược khác. Tuy vậy, để trả về count chính xác, database phải xử lý đủ thông tin cần thiết về tập hàng thỏa điều kiện. Trên bảng lớn, `count()` có thể tốn đáng kể I/O và CPU, ngay cả khi query không trả nhiều dữ liệu về ứng dụng.

`EXISTS` thường có lợi thế vì database có thể dừng khi tìm được hàng phù hợp. Tuy nhiên, optimizer, index, predicate, join và database engine quyết định kế hoạch thực thi thực tế. Không có quy tắc rằng mọi exists query luôn nhanh hơn mọi count query.

### Index ảnh hưởng thế nào?

Ví dụ `existsBySku` hoặc `countByCategory` thường hưởng lợi từ index phù hợp:

```sql
create unique index ux_products_sku on products(sku);
create index ix_products_category on products(category);
```

- Index unique trên `sku` vừa tăng tốc tra cứu vừa bảo đảm không có hai sản phẩm cùng SKU.
- Index trên `category` có thể giúp lọc hoặc đếm theo category, tùy selectivity và execution plan.
- Với truy vấn có nhiều điều kiện, composite index có thể phù hợp hơn, nhưng thứ tự cột cần dựa trên workload.

Index làm tăng chi phí INSERT/UPDATE/DELETE và tiêu tốn dung lượng. Không tạo index cho mọi field; xem execution plan và số liệu thực tế trước.

## 6. existsById rồi save có tránh được trùng dữ liệu không?

Không. Mẫu sau có race condition:

```java
if (!repository.existsById(id)) {
    repository.save(entity);
}
```

Hai transaction đồng thời có thể cùng kiểm tra `false`, sau đó cùng cố insert. Kiểm tra tồn tại trước không khóa được khoảng thời gian giữa SELECT và INSERT.

Với điều kiện duy nhất như email hoặc SKU, hãy đặt unique constraint/index ở database. Ứng dụng có thể kiểm tra trước để đưa ra thông báo thân thiện, nhưng vẫn phải xử lý lỗi unique constraint khi ghi.

```sql
alter table products
add constraint uk_products_sku unique (sku);
```

Với cập nhật theo ID, có thể dùng optimistic locking (`@Version`) để phát hiện ghi đè đồng thời. Chọn transaction isolation hoặc locking khi nghiệp vụ cần bảo đảm mạnh hơn; không dùng exists check như một cơ chế khóa.

## 7. Tránh N+1 truy vấn kiểm tra tồn tại

Một lỗi hiệu năng phổ biến là lặp qua danh sách ID và gọi `existsById` từng phần tử:

```java
for (Long id : ids) {
    if (repository.existsById(id)) {
        // xử lý
    }
}
```

Nếu có N ID, cách này có thể tạo N query. Với số lượng lớn, cân nhắc một query theo tập ID hoặc truy vấn lấy đúng dữ liệu cần thiết:

```java
List<Product> products = repository.findAllById(ids);
Set<Long> foundIds = products.stream()
        .map(Product::getId)
        .collect(Collectors.toSet());
```

Đối chiếu `foundIds` với danh sách đầu vào để tìm ID thiếu. Nếu chỉ cần kiểm tra tập ID và không cần entity, có thể viết repository query trả danh sách ID hoặc dùng query native/JPQL phù hợp. Chia batch nếu danh sách vượt giới hạn bind parameter của database.

`findAllById` không bảo đảm kết quả giữ nguyên thứ tự đầu vào và không tạo placeholder cho ID không tồn tại. Nếu thứ tự quan trọng, tự dựng kết quả theo thứ tự danh sách ID ban đầu.

## 8. count và phân trang

`Page<T>` thường cần tổng số phần tử để cung cấp `getTotalElements()` và `getTotalPages()`. Vì vậy, truy vấn phân trang có thể phát sinh:

1. Query lấy trang dữ liệu với limit/offset hoặc cú pháp tương ứng.
2. Count query để xác định tổng số hàng thỏa điều kiện.

Với bảng lớn hoặc predicate phức tạp, count query có thể là phần tốn kém nhất của phân trang.

Nếu giao diện chỉ cần biết còn trang tiếp theo hay không, dùng `Slice<T>` hoặc `Window<T>` theo kiểu phân trang phù hợp có thể tránh yêu cầu tổng số chính xác. Keyset/scroll pagination có thể phù hợp hơn offset pagination khi dữ liệu lớn và có khóa sắp xếp ổn định.

Không tự gọi `count()` rồi lại dùng `Page` nếu Page đã thực hiện count query; điều đó có thể đếm hai lần.

## 9. Ví dụ chạy được với Java 17+, Spring Boot và H2

Ví dụ tạo repository có `existsById`, `existsBySku`, `count` và các query method `countBy...`. Dự án dùng Spring Boot 3.4.5, Java 17 và H2 in-memory database.

### Cấu trúc dự án

```text
crud-query-cost/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/querycost/
        │   ├── QueryCostApplication.java
        │   ├── Product.java
        │   └── ProductRepository.java
        └── resources/
            └── application.properties
```

### `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>crud-query-cost</artifactId>
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
```

### `src/main/resources/application.properties`

```properties
spring.datasource.url=jdbc:h2:mem:querycost;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
logging.level.org.hibernate.SQL=DEBUG
```

### `Product.java`

```java
package com.example.querycost;

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

    @Column(nullable = false, unique = true, length = 40)
    private String sku;

    @Column(nullable = false, length = 40)
    private String category;

    @Column(nullable = false)
    private boolean active;

    protected Product() {
    }

    public Product(String sku, String category, boolean active) {
        this.sku = sku;
        this.category = category;
        this.active = active;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }
}
```

### `ProductRepository.java`

```java
package com.example.querycost;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository extends JpaRepository<Product, Long> {
    boolean existsBySku(String sku);

    boolean existsByCategoryAndActiveTrue(String category);

    long countByActiveTrue();

    long countByCategory(String category);
}
```

### `QueryCostApplication.java`

```java
package com.example.querycost;

import java.util.List;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class QueryCostApplication {
    public static void main(String[] args) {
        SpringApplication.run(QueryCostApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(ProductRepository repository) {
        return args -> {
            List<Product> saved = repository.saveAll(List.of(
                    new Product("SKU-100", "BOOK", true),
                    new Product("SKU-200", "BOOK", true),
                    new Product("SKU-300", "TOOL", false)
            ));
            repository.flush();

            System.out.println("existsById: "
                    + repository.existsById(saved.get(0).getId()));
            System.out.println("missing id: " + repository.existsById(-1L));
            System.out.println("existsBySku: " + repository.existsBySku("SKU-200"));
            System.out.println("existsByCategoryAndActiveTrue: "
                    + repository.existsByCategoryAndActiveTrue("BOOK"));
            System.out.println("count: " + repository.count());
            System.out.println("active count: " + repository.countByActiveTrue());
            System.out.println("BOOK count: " + repository.countByCategory("BOOK"));
        };
    }
}
```

### Chạy chương trình

```bash
mvn spring-boot:run
```

Phần output do ứng dụng in ra:

```text
existsById: true
missing id: false
existsBySku: true
existsByCategoryAndActiveTrue: true
count: 3
active count: 2
BOOK count: 2
```

SQL log có thể hiển thị các truy vấn count/existence và các câu SELECT khác nhau tùy phiên bản Spring Data JPA, Hibernate và H2. Dùng log này để xác nhận chiến lược thực thi trong dự án thực tế.

## 10. Cách đo chi phí truy vấn

Để đánh giá một thao tác tồn tại hoặc đếm, không chỉ nhìn thời gian ở một lần chạy. Hãy:

1. Dùng dữ liệu có kích thước gần với production.
2. Bật SQL logging trong môi trường thử nghiệm để xem số lượng và dạng query.
3. Dùng `EXPLAIN` hoặc execution plan của database để xem index, scan, join và estimated rows.
4. Đo latency và database load khi chạy đồng thời, sau khi warm-up.
5. Kiểm tra cả trường hợp có kết quả, không có kết quả và predicate có độ chọn lọc thấp.
6. So sánh query có index và không có index trên bản sao dữ liệu phù hợp.

Tránh kết luận từ H2 in-memory cho database production. Kế hoạch truy vấn và chi phí phụ thuộc hệ quản trị database, thống kê, index, dữ liệu, concurrency và cấu hình.

## 11. Lỗi thường gặp

1. **Dùng count để kiểm tra tồn tại:** `countBy... > 0` yêu cầu số lượng chính xác. Dùng `existsBy...` nếu chỉ cần boolean.
2. **Tải entity chỉ để kiểm tra có hay không:** `findById` có thể hydrate entity và quan hệ; `existsById` phù hợp hơn nếu chỉ cần boolean.
3. **Gọi existsById rồi findById:** thường tạo hai query. Nếu cần entity, tải trực tiếp bằng `findById`.
4. **Gọi exists trong vòng lặp:** tạo N query cho N ID. Cân nhắc query theo tập ID hoặc batch.
5. **Dùng exists check để chống trùng tuyệt đối:** có race condition. Dùng unique constraint/index và xử lý lỗi khi ghi.
6. **Đếm dữ liệu lớn mà không cần tổng chính xác:** xem xét Slice hoặc keyset pagination thay cho Page nếu tổng count không cần thiết.
7. **Bỏ qua index:** predicate trên cột không có index có thể quét nhiều hàng; tạo index theo workload và xác minh bằng execution plan.
8. **Tin rằng COUNT(*) luôn quét toàn bảng hoặc EXISTS luôn nhanh hơn:** optimizer có thể chọn chiến lược khác; đo trên database thật.

## 12. Nguyên tắc thực hành

- Dùng `existsById` cho kiểm tra boolean theo khóa chính.
- Dùng `existsBy...` cho điều kiện theo thuộc tính khi chỉ cần biết có bản ghi phù hợp.
- Dùng `count()` hoặc `countBy...` khi cần số lượng chính xác.
- Dùng `findById` hoặc query trả entity khi cần dữ liệu để đọc/cập nhật.
- Với unique business key, dùng unique constraint ở database; kiểm tra tồn tại chỉ để cải thiện thông báo.
- Kiểm tra query count do `Page` tạo ra; dùng `Slice` nếu không cần tổng số.
- Đo execution plan, index và latency trên hệ quản trị database thực tế.

Điểm cốt lõi: **exists trả lời có hay không; count trả về số lượng chính xác. Chọn API theo nhu cầu thực, tránh query lặp, tận dụng index phù hợp và dùng constraint database để bảo đảm tính duy nhất trong môi trường đồng thời.**