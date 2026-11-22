# Kiểu trả về đơn, Optional và nhiều kết quả

## Mục tiêu

Kiểu trả về của một repository method trong Spring Data JPA thể hiện số lượng kết quả mà ứng dụng mong đợi. Một query có thể không tìm thấy bản ghi, tìm thấy đúng một bản ghi hoặc tìm thấy nhiều bản ghi. Chọn đúng kiểu trả về giúp code biểu đạt rõ trường hợp rỗng, tránh lỗi cardinality và không tải dữ liệu nhiều hơn nhu cầu.

Các lựa chọn thường gặp:

- `T`: một entity hoặc projection; nếu không có kết quả, phương thức có thể trả `null`; nếu có nhiều hơn một kết quả, Spring Data báo lỗi kích thước kết quả.
- `Optional<T>`: không có kết quả thì `Optional.empty()`, có một kết quả thì `Optional.of(value)`; nhiều kết quả vẫn là lỗi.
- `List<T>` hoặc collection: nhận không, một hoặc nhiều kết quả; không có kết quả thì collection rỗng.
- `Page<T>` và `Slice<T>`: nhận một phần kết quả theo trang, với metadata khác nhau.
- `Stream<T>`: duyệt kết quả theo luồng; cần quản lý transaction và đóng stream đúng cách.

Kiểu trả về không tự bảo đảm dữ liệu duy nhất. Nếu nghiệp vụ yêu cầu một email hoặc mã định danh không trùng, database vẫn cần unique constraint.

## 1. Cardinality: query có thể trả về bao nhiêu hàng?

Trước khi khai báo method, xác định cardinality của điều kiện tìm kiếm:

| Cardinality | Ví dụ | Kiểu trả về phù hợp |
| --- | --- | --- |
| Không hoặc tối đa một | Tìm customer theo email duy nhất | `Optional<Customer>` hoặc `Customer` nullable |
| Chính xác một theo quy tắc nghiệp vụ | Tải cấu hình bắt buộc | `Customer` với kiểm tra null hoặc xử lý lỗi rõ ràng |
| Không, một hoặc nhiều | Tìm customer theo thành phố | `List<Customer>` hoặc collection khác |
| Một kết quả đầu tiên theo thứ tự | Bản ghi mới nhất trong một nhóm | `Optional<T>` kết hợp `First` và sort xác định |
| Một trang trong tập lớn | Danh sách tìm kiếm có điều hướng trang | `Page<T>` hoặc `Slice<T>` |

Không nên chọn kiểu trả về chỉ vì code gọi hiện tại muốn một object. Điều kiện query phải thực sự giới hạn được số kết quả tối đa một, hoặc method phải chủ động giới hạn kết quả.

## 2. Trả về một entity: T

Repository method có thể trả trực tiếp entity:

```java
Customer getByEmailAddress(String emailAddress);
```

Với query method đơn kết quả, Spring Data JPA xử lý như sau:

- Không có hàng phù hợp: kết quả trả về là `null` nếu repository/package không bật chế độ nullability nghiêm ngặt.
- Có đúng một hàng: trả về entity đó.
- Có nhiều hơn một hàng: ném `IncorrectResultSizeDataAccessException` (được chuyển đổi từ lỗi nhiều kết quả của JPA provider).

Kiểu `T` phù hợp khi query được bảo đảm trả tối đa một hàng, ví dụ tra cứu bằng primary key hoặc một business key có unique constraint.

### Nullability của repository method

Trong Spring Data, có thể bật kiểm tra nullability ở cấp package bằng `@NonNullApi` trong `package-info.java`. Khi đó các tham số và giá trị trả về được coi là non-null theo mặc định; nếu query đơn không tìm thấy kết quả, Spring Data có thể ném `EmptyResultDataAccessException` thay vì âm thầm trả null.

Ví dụ:

```java
@org.springframework.lang.NonNullApi
package com.example.repositories;
```

Nếu một method trong package đó được phép không có kết quả và muốn biểu diễn bằng `null`, đánh dấu rõ bằng `@Nullable`. Với trường hợp không có kết quả là bình thường, `Optional<T>` thường dễ đọc và ít mơ hồ hơn.

Không nên giả định mọi repository đều có cùng nullability policy. Kiểm tra package annotations và signature thực tế của dự án.

## 3. Optional<T>: biểu diễn kết quả có thể vắng mặt

`Optional<T>` phù hợp khi query trả về tối đa một kết quả nhưng không tìm thấy là tình huống bình thường.

```java
Optional<Customer> findByEmailAddress(String emailAddress);
```

Cách sử dụng:

```java
Optional<Customer> result = repository.findByEmailAddress(email);

if (result.isPresent()) {
    Customer customer = result.get();
    System.out.println(customer.getName());
} else {
    System.out.println("Customer not found");
}
```

Hoặc xử lý gọn hơn:

```java
Customer customer = repository.findByEmailAddress(email)
        .orElseThrow(() -> new CustomerNotFoundException(email));
```

Những phương thức hữu ích của Optional:

| Method | Ý nghĩa |
| --- | --- |
| `isPresent()` / `isEmpty()` | Kiểm tra có giá trị hay không. |
| `orElse(value)` | Trả giá trị mặc định nếu rỗng; biểu thức `value` được tính trước khi gọi. |
| `orElseGet(supplier)` | Tính giá trị mặc định khi Optional thực sự rỗng. |
| `orElseThrow()` | Ném `NoSuchElementException` nếu rỗng. |
| `map(fn)` | Biến đổi giá trị bên trong nếu có. |
| `ifPresent(action)` | Thực hiện hành động nếu có giá trị. |

Nếu tạo giá trị mặc định tốn chi phí, `orElseGet` tránh thực thi không cần thiết:

```java
Customer customer = repository.findByEmailAddress(email)
        .orElseGet(() -> createGuestCustomer(email));
```

`Optional<T>` không có nghĩa query tự chọn một hàng bất kỳ. Nếu điều kiện khớp nhiều hàng, Spring Data vẫn báo `IncorrectResultSizeDataAccessException`. Optional chỉ biểu diễn trường hợp zero-or-one.

### Optional và unique constraint

Giả sử email là định danh duy nhất:

```java
@Column(nullable = false, unique = true)
private String emailAddress;
```

Repository:

```java
Optional<Customer> findByEmailAddress(String emailAddress);
```

Unique constraint ở database là lớp bảo vệ cuối cùng trước ghi đồng thời. Chỉ khai báo `Optional` hoặc kiểm tra `existsByEmailAddress` không ngăn được hai transaction cùng insert email giống nhau.

### Không dùng Optional cho mọi loại trả về

- Không dùng `Optional<List<Customer>>` cho query nhiều kết quả. Dùng `List<Customer>` và nhận list rỗng khi không có hàng.
- Không dùng `Optional` làm kiểu thuộc tính persistent trong entity JPA. Dùng kiểu thuộc tính thông thường; Optional có thể dùng ở tầng repository/service.
- Không trả `null` thay cho một `Optional`; repository nên trả `Optional.empty()`.
- Không gọi `get()` mà chưa kiểm tra hoặc chưa có lý do chắc chắn Optional chứa giá trị.

## 4. Nhiều kết quả: List và các collection

Khi query có thể khớp nhiều entity, dùng collection:

```java
List<Customer> findAllByCityOrderByNameAscIdAsc(String city);
```

Đặc điểm:

- Không có kết quả: trả collection rỗng, không trả `null`.
- Có một kết quả: collection có một phần tử.
- Có nhiều kết quả: collection chứa các phần tử tìm được.
- Thứ tự chỉ được bảo đảm khi query khai báo `OrderBy` hoặc caller truyền `Sort`/`Pageable` có sort.

Các kiểu collection được Spring Data hỗ trợ bao gồm `List`, `Collection`, `Iterable`, `Set` và `Streamable` trong những trường hợp phù hợp. `List` thường là lựa chọn dễ hiểu nhất khi cần thứ tự và truy cập theo index.

### Vì sao không trả một entity khi query có thể khớp nhiều hàng?

Ví dụ:

```java
Customer findByCity(String city);
```

Nếu thành phố có nhiều customer, method trên không tự trả phần tử đầu tiên. Nó ném `IncorrectResultSizeDataAccessException` vì signature yêu cầu một kết quả nhưng query trả nhiều hơn một.

Nếu cần toàn bộ kết quả, đổi thành `List<Customer>`. Nếu chỉ cần một kết quả theo quy tắc nghiệp vụ, dùng `First`/`Top` kèm thứ tự xác định:

```java
Optional<Customer> findFirstByCityOrderByCreatedAtDescIdDesc(String city);
```

Ở đây `createdAt DESC` chọn bản ghi mới nhất; `id DESC` là tie-breaker khi timestamp bằng nhau. Nếu bỏ sort, “first” không có ý nghĩa ổn định vì database không bảo đảm thứ tự hàng.

## 5. Page, Slice và List kết hợp Pageable

Với tập dữ liệu lớn, không nên tải toàn bộ kết quả vào bộ nhớ chỉ để hiển thị một trang.

### Page<T>

`Page<T>` chứa nội dung trang cùng thông tin tổng số phần tử và tổng số trang:

```java
Page<Customer> findByCity(String city, Pageable pageable);
```

Ví dụ:

```java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by("name").ascending().and(Sort.by("id").ascending())
);
Page<Customer> page = repository.findByCity("Ha Noi", pageable);

List<Customer> content = page.getContent();
long total = page.getTotalElements();
int pages = page.getTotalPages();
```

Trang đầu tiên có index `0`. `Page` thường cần count query để tính tổng số hàng; Spring Data có thể tối ưu và bỏ count query trong một số trường hợp có thể suy ra tổng từ nội dung trang, nhưng không nên giả định count luôn miễn phí.

### Slice<T>

`Slice<T>` cung cấp nội dung trang và thông tin có trang kế tiếp hay không, không yêu cầu tổng số chính xác:

```java
Slice<Customer> findByActiveTrue(Pageable pageable);
```

```java
Slice<Customer> slice = repository.findByActiveTrue(
        PageRequest.of(0, 20, Sort.by("id").ascending())
);
boolean hasNext = slice.hasNext();
```

Spring Data thường lấy thêm một hàng ngoài page size để xác định `hasNext()`. Vì không cần tổng số, Slice có thể tránh count query tốn kém.

### List<T> với Pageable

Method có thể trả `List<T>` và nhận `Pageable` để áp dụng limit/offset và sort nhưng không trả metadata Page/Slice:

```java
List<Customer> findByActiveTrue(Pageable pageable);
```

Chọn `Page` khi giao diện cần tổng số trang, `Slice` khi chỉ cần biết có trang tiếp theo, và `List` khi chỉ cần nội dung của một đoạn dữ liệu.

## 6. Stream<T> và vòng đời tài nguyên

Repository method có thể trả `Stream<T>` để duyệt kết quả theo luồng:

```java
Stream<Customer> streamByCity(String city);
```

Stream có thể giữ tài nguyên JDBC và persistence context trong lúc duyệt. Vì vậy, cần thực thi trong transaction thích hợp và đóng stream:

```java
try (Stream<Customer> customers = repository.streamByCity("Ha Noi")) {
    customers.forEach(this::processCustomer);
}
```

Không giữ stream sau khi transaction kết thúc. Nếu chỉ cần một danh sách vừa phải, `List<T>` đơn giản hơn. Với xử lý batch lớn, cân nhắc streaming, fetch size và phân trang theo keyset dựa trên khả năng của provider/database.

## 7. Projection và kiểu trả về không phải entity

Repository không bắt buộc phải trả entity đầy đủ. Nếu chỉ cần một số trường, dùng interface projection hoặc DTO để giảm dữ liệu đọc và hydrate:

```java
public interface CustomerNameView {
    Long getId();
    String getName();
}

List<CustomerNameView> findByCity(String city);
```

Hoặc DTO constructor expression trong JPQL:

```java
@Query("select new com.example.CustomerSummary(c.id, c.name) "
     + "from Customer c where c.city = :city")
List<CustomerSummary> findSummariesByCity(@Param("city") String city);
```

Cardinality vẫn áp dụng: projection trả một giá trị đơn có thể không có kết quả hoặc bị lỗi nếu query trả nhiều hàng; projection dạng collection có thể trả nhiều hàng và collection rỗng.

## 8. @Query không thay đổi quy tắc kiểu trả về

Kiểu trả về vẫn phải phù hợp với số hàng mà JPQL có thể trả:

```java
@Query("select c from Customer c where c.emailAddress = :email")
Optional<Customer> lookupByEmail(@Param("email") String email);

@Query("select c from Customer c where c.city = :city order by c.name")
List<Customer> lookupByCity(@Param("city") String city);
```

Việc dùng `@Query` không khiến một query nhiều hàng trở thành query đơn. Nếu khai báo `Optional<Customer>` mà có hai hàng phù hợp, vẫn phát sinh lỗi kích thước kết quả.

Đối với query đơn có thể không có hàng, `Optional<T>` thể hiện hợp đồng rõ hơn. Đối với query nhiều hàng, dùng collection hoặc Page/Slice.

## 9. Bảng quyết định chọn kiểu trả về

| Nhu cầu | Khuyến nghị | Không nên |
| --- | --- | --- |
| Tìm theo primary key | `Optional<T>` qua `findById` | Tự query collection rồi lấy phần tử đầu |
| Tìm theo email duy nhất | `Optional<T>` và unique constraint | Giả định Optional tự bảo đảm duy nhất |
| Query có thể không có và caller chấp nhận null | `T` nullable, ghi rõ nullability | Để caller đoán null có hợp lệ không |
| Tìm mọi entity theo thuộc tính | `List<T>` | `Optional<List<T>>` |
| Chọn một bản ghi mới nhất | `Optional<T>` + `First` + sort ổn định | `findFirst` không có thứ tự |
| Danh sách có tổng số trang | `Page<T>` | Tự gọi count thêm lần nữa nếu Page đã cung cấp total |
| Chỉ cần biết còn dữ liệu không | `Slice<T>` | Count toàn bộ khi không cần total |
| Duyệt kết quả lớn theo luồng | `Stream<T>` đóng đúng cách trong transaction | Để stream sống sau transaction |

## 10. Ví dụ chạy được với Java 17+, Spring Boot và H2

Ví dụ tạo bốn customer. Email là duy nhất; nhiều customer có thể cùng thành phố. Repository minh họa kết quả đơn, Optional, List, First, Page và Slice.

### Cấu trúc dự án

```text
repository-return-types/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/returntypes/
        │   ├── ReturnTypesApplication.java
        │   ├── Customer.java
        │   └── CustomerRepository.java
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
    <artifactId>repository-return-types</artifactId>
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
spring.datasource.url=jdbc:h2:mem:returntypes;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
logging.level.org.hibernate.SQL=DEBUG
```

### `Customer.java`

```java
package com.example.returntypes;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    @Column(nullable = false, unique = true, length = 180)
    private String emailAddress;

    @Column(nullable = false, length = 80)
    private String city;

    @Column(nullable = false)
    private Instant createdAt;

    @Column(nullable = false)
    private boolean active;

    protected Customer() {
    }

    public Customer(String name, String emailAddress, String city,
                    Instant createdAt, boolean active) {
        this.name = name;
        this.emailAddress = emailAddress;
        this.city = city;
        this.createdAt = createdAt;
        this.active = active;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getEmailAddress() {
        return emailAddress;
    }

    public String getCity() {
        return city;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
```

### `CustomerRepository.java`

```java
package com.example.returntypes;

import java.util.List;
import java.util.Optional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository extends JpaRepository<Customer, Long> {
    Customer getByEmailAddress(String emailAddress);

    Optional<Customer> findByEmailAddress(String emailAddress);

    List<Customer> findAllByCityOrderByNameAscIdAsc(String city);

    Optional<Customer> findFirstByCityOrderByCreatedAtDescIdDesc(String city);

    Page<Customer> findByCity(String city, Pageable pageable);

    Slice<Customer> findByActiveTrue(Pageable pageable);
}
```

`getByEmailAddress` minh họa kiểu trả về entity trực tiếp; nếu không tìm thấy và package không bật strict nullability, kết quả là null. `findByEmailAddress` biểu diễn cùng cardinality bằng Optional. Không khai báo hai method này để phân biệt query logic; chúng chỉ minh họa hai hợp đồng trả về khác nhau.

### `ReturnTypesApplication.java`

```java
package com.example.returntypes;

import java.time.Instant;
import java.util.List;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.Sort;

@SpringBootApplication
public class ReturnTypesApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReturnTypesApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(CustomerRepository repository) {
        return args -> {
            repository.saveAll(List.of(
                    new Customer("An", "an@example.com", "Ha Noi",
                            Instant.parse("2025-01-01T00:00:00Z"), true),
                    new Customer("Binh", "binh@example.com", "Ha Noi",
                            Instant.parse("2025-02-01T00:00:00Z"), true),
                    new Customer("Cuong", "cuong@example.com", "Ho Chi Minh City",
                            Instant.parse("2025-02-15T00:00:00Z"), true),
                    new Customer("Dung", "dung@example.com", "Ha Noi",
                            Instant.parse("2025-03-01T00:00:00Z"), false)
            ));
            repository.flush();

            Customer single = repository.getByEmailAddress("an@example.com");
            System.out.println("Single entity: " + single.getName());

            System.out.println("Optional missing: "
                    + repository.findByEmailAddress("missing@example.com").isEmpty());

            List<Customer> cityCustomers =
                    repository.findAllByCityOrderByNameAscIdAsc("Ha Noi");
            System.out.println("List by city: " + names(cityCustomers));

            Customer latest = repository
                    .findFirstByCityOrderByCreatedAtDescIdDesc("Ha Noi")
                    .orElseThrow();
            System.out.println("Latest in Ha Noi: " + latest.getName());

            Page<Customer> page = repository.findByCity(
                    "Ha Noi",
                    PageRequest.of(0, 2, Sort.by("name").ascending().and(Sort.by("id").ascending()))
            );
            System.out.println("Page 0: " + names(page.getContent())
                    + " | total=" + page.getTotalElements());

            Slice<Customer> slice = repository.findByActiveTrue(
                    PageRequest.of(0, 2, Sort.by("id").ascending())
            );
            System.out.println("Active slice: " + names(slice.getContent())
                    + " | hasNext=" + slice.hasNext());
        };
    }

    private static String names(List<Customer> customers) {
        return customers.stream()
                .map(Customer::getName)
                .reduce((left, right) -> left + ", " + right)
                .orElse("");
    }
}
```

### Chạy chương trình

```bash
mvn spring-boot:run
```

Phần output do ứng dụng in ra:

```text
Single entity: An
Optional missing: true
List by city: An, Binh, Dung
Latest in Ha Noi: Dung
Page 0: An, Binh | total=3
Active slice: An, Binh | hasNext=true
```

Output dựa trên database H2 mới của ví dụ. ID được sinh theo thứ tự insert; thứ tự danh sách và trang được xác định bởi `OrderBy` hoặc `Sort`, không dựa vào thứ tự vật lý của bảng.

## 11. Lỗi thường gặp

1. **Dùng entity đơn cho điều kiện có thể khớp nhiều hàng:** Spring Data ném `IncorrectResultSizeDataAccessException`. Đổi sang collection hoặc giới hạn rõ ràng bằng `First`/`Top`.
2. **Nghĩ Optional tự chọn một hàng:** Optional chỉ biểu diễn zero-or-one; nhiều hàng vẫn là lỗi.
3. **Dùng Optional<List<T>>:** collection query không có kết quả đã trả list rỗng.
4. **Giả định entity return luôn non-null:** nếu không có kết quả, method có thể trả null trừ khi nullability policy quy định khác.
5. **Dùng First mà không có sort:** kết quả được chọn không ổn định. Thêm `OrderBy` với tie-breaker duy nhất.
6. **Dùng Optional thay unique constraint:** hai transaction vẫn có thể ghi cùng business key. Bảo vệ bằng constraint ở database.
7. **Chọn Page khi không cần tổng số:** count query có thể tốn kém; cân nhắc Slice hoặc List với Pageable.
8. **Không đóng Stream:** stream có thể giữ connection và persistence context. Dùng try-with-resources trong transaction.
9. **Trả entity đầy đủ khi chỉ cần vài trường:** cân nhắc projection hoặc DTO để giảm dữ liệu tải.
10. **Trả null cho Optional:** dùng `Optional.empty()` và giữ hợp đồng nhất quán.

## 12. Nguyên tắc thực hành

- Xác định số kết quả tối đa trước khi chọn kiểu trả về.
- Dùng `Optional<T>` cho query zero-or-one khi không có kết quả là bình thường.
- Chỉ dùng `T` khi query có thể bảo đảm tối đa một kết quả; làm rõ nullability.
- Dùng `List<T>` hoặc collection cho query nhiều kết quả; collection rỗng biểu diễn không tìm thấy.
- Dùng `First`/`Top` với sort ổn định nếu nghiệp vụ cần một phần tử trong tập nhiều hàng.
- Dùng unique constraint để bảo đảm business key duy nhất dưới concurrency.
- Chọn `Page`, `Slice` hoặc `List` với `Pageable` theo nhu cầu metadata.
- Đóng `Stream<T>` và giữ nó trong transaction thích hợp.
- Dùng projection khi không cần toàn bộ entity.

Điểm cốt lõi: **`T` biểu diễn một kết quả và có thể null khi không tìm thấy; `Optional<T>` biểu diễn zero-or-one rõ ràng; collection biểu diễn zero-to-many và rỗng khi không có hàng. Nếu query có thể trả nhiều hàng, đừng khai báo kiểu đơn trừ khi đã giới hạn kết quả hoặc bảo đảm tính duy nhất ở database.**