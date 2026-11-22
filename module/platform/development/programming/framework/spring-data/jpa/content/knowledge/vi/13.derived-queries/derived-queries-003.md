# Duyệt thuộc tính lồng nhau và phân giải tên bằng dấu gạch dưới

## 1. Mục tiêu

Spring Data JPA có thể tạo truy vấn từ tên phương thức repository. Khi điều kiện nằm trên một thuộc tính lồng bên trong Entity khác hoặc một `@Embedded` object, Spring Data phân tích tên phương thức thành đường dẫn thuộc tính (property path).

Ví dụ:
- `findByAddressZipCode(...)` có thể được phân tích thành `addressZip.code`.
- `findByAddress_ZipCode(...)` dùng dấu gạch dưới để chỉ rõ đường dẫn `address.zipCode`.

Bài học này giải thích cách parser phân giải tên, khi nào phát sinh nhập nhằng, cách dùng `_` để chỉ ranh giới traversal, và cách kiểm tra truy vấn bằng Spring Data JPA.

Sau bài học, bạn có thể:
- Viết derived query đi qua thuộc tính của `@Embedded` và quan hệ Entity.
- Hiểu cách Spring Data ưu tiên property match và tách camel case.
- Xử lý tên thuộc tính có nhiều cách diễn giải bằng dấu gạch dưới.
- Kết hợp nested property với toán tử như `IgnoreCase`, `Containing`, `And`, `Or`, `OrderBy`.
- Nhận biết lỗi do tên property, kiểu dữ liệu, quan hệ hoặc đường dẫn không hợp lệ.

## 2. Derived query và property path

Spring Data repository hỗ trợ khai báo truy vấn ngay trong tên phương thức. Framework phân tích tên, xác định phần subject và predicate, rồi chuyển các biểu thức property thành điều kiện truy vấn.

Ví dụ:

```java
List<Customer> findByAddress_ZipCode(String zipCode);
```

Tên này có thể được hiểu như:

- `findBy`: phần mở đầu chỉ ra truy vấn tìm kiếm.
- `Address_ZipCode`: đường dẫn thuộc tính `address.zipCode`.
- `String zipCode`: giá trị dùng để so sánh với thuộc tính cuối cùng.

Với Entity `Customer` có thuộc tính `address`, trong đó `Address` có `zipCode`, Spring Data tạo điều kiện tương đương JPQL:

```jpql
select c from Customer c where c.address.zipCode = ?1
```

JPQL sử dụng tên thuộc tính Java, không sử dụng tên cột SQL. Nếu `zipCode` được ánh xạ vào cột `postal_code`, property path vẫn là `address.zipCode`.

## 3. Cách Spring Data phân giải tên thuộc tính

Spring Data cố gắng khớp tên property theo các bước khái quát:

1. Trước tiên, thử xem toàn bộ phần tên có khớp với một thuộc tính trực tiếp của kiểu hiện tại hay không.
2. Nếu không khớp, parser tách phần tên tại các ranh giới camel case, bắt đầu từ phía phải, rồi thử tìm property ở phần đầu và tiếp tục phân tích phần còn lại trên kiểu của property đó.
3. Khi một cách phân giải khớp với các property hợp lệ, đường dẫn được sử dụng để tạo truy vấn.

Ví dụ, nếu `Customer` có `address` kiểu `Address`, `Address` có `zipCode` kiểu String, đường dẫn `address.zipCode` có thể được diễn đạt bằng `AddressZipCode` trong tên phương thức khi không có property cạnh tranh.

Nhưng nếu `Customer` đồng thời có một thuộc tính `addressZip` kiểu `AddressZip`, và `AddressZip` cũng có thuộc tính `code`, thì `AddressZipCode` có thể được phân tích thành `addressZip.code`. Parser có thể chọn property trực tiếp dài hơn ở bước đầu, dù người viết đang muốn `address.zipCode`.

Đây là nguyên nhân cần dấu gạch dưới để chỉ rõ traversal point.

## 4. Dấu gạch dưới `_` để chỉ ranh giới traversal

Dấu gạch dưới trong tên derived query được Spring Data dành làm ký hiệu phân tách đường dẫn thuộc tính. Nó giúp cố định điểm bắt đầu của một nested property.

Ví dụ:

| Tên phương thức | Đường dẫn thuộc tính |
| --- | --- |
| `findByAddressZipCode(...)` | Có thể bị phân giải thành `addressZip.code` nếu property đó tồn tại. |
| `findByAddress_ZipCode(...)` | Chỉ rõ `address.zipCode`. |
| `findByCustomer_Address_ZipCode(...)` | Chỉ rõ `customer.address.zipCode`. |

Trong ví dụ nhập nhằng, dùng:

```java
List<Customer> findByAddress_ZipCode(String zipCode);
```

Đường dẫn được cố định thành `address` rồi tới `zipCode`. Spring Data không cần đoán xem `addressZip` có phải property đầu tiên hay không.

**Quy ước:** hãy dùng `_` ở những điểm traversal có nguy cơ nhập nhằng hoặc khi tên nested property dài khiến người đọc khó nhận ra ranh giới. Không cần chèn dấu gạch dưới vào mọi phương thức nếu đường dẫn đã rõ ràng.

Dấu `_` là ký hiệu cú pháp trong property expression. Vì vậy, nên tránh đặt tên persistent property Java có dấu gạch dưới. Hãy dùng camelCase cho tên field/property; tên cột database có thể dùng snake_case qua `@Column(name = "...")` mà không ảnh hưởng tới cách parser đọc tên property.

## 5. Ví dụ hoàn chỉnh: hai cách phân giải khác nhau

Ta tạo `Customer` có hai embedded object:

- `address.zipCode`: mã bưu chính của địa chỉ hiện tại.
- `addressZip.code`: một mã khác được lưu từ hệ thống cũ.

Cả hai đường dẫn đều có thể khớp một phần tên `AddressZipCode`. Đây là tình huống minh họa tại sao cần viết rõ ranh giới.

### 5.1. Lớp Address

`src/main/java/com/example/customer/Address.java`:

```java
package com.example.customer;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

@Embeddable
public class Address {
    @Column(name = "street", nullable = false, length = 160)
    private String street;

    @Column(name = "zip_code", nullable = false, length = 12)
    private String zipCode;

    protected Address() {
        // JPA cần constructor không tham số.
    }

    public Address(String street, String zipCode) {
        if (street == null || street.isBlank() || street.length() > 160) {
            throw new IllegalArgumentException("Street is required");
        }
        if (zipCode == null || zipCode.isBlank() || zipCode.length() > 12) {
            throw new IllegalArgumentException("Zip code is required");
        }
        this.street = street.trim();
        this.zipCode = zipCode.trim();
    }

    public String getStreet() {
        return street;
    }

    public String getZipCode() {
        return zipCode;
    }
}
```

### 5.2. Lớp AddressZip

`src/main/java/com/example/customer/AddressZip.java`:

```java
package com.example.customer;

import jakarta.persistence.Embeddable;

@Embeddable
public class AddressZip {
    private String code;

    protected AddressZip() {
        // JPA cần constructor không tham số.
    }

    public AddressZip(String code) {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("Address zip code is required");
        }
        this.code = code.trim();
    }

    public String getCode() {
        return code;
    }
}
```

### 5.3. Entity Customer

`src/main/java/com/example/customer/Customer.java`:

```java
package com.example.customer;

import jakarta.persistence.AttributeOverride;
import jakarta.persistence.Column;
import jakarta.persistence.Embedded;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    @Embedded
    private Address address;

    @Embedded
    @AttributeOverride(
            name = "code",
            column = @Column(name = "legacy_address_code", nullable = false, length = 30))
    private AddressZip addressZip;

    protected Customer() {
        // JPA cần constructor không tham số.
    }

    public Customer(String name, Address address, AddressZip addressZip) {
        if (name == null || name.isBlank() || name.length() > 120) {
            throw new IllegalArgumentException("Customer name is required");
        }
        this.name = name.trim();
        this.address = address;
        this.addressZip = addressZip;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public Address getAddress() {
        return address;
    }

    public AddressZip getAddressZip() {
        return addressZip;
    }
}
```

`@AttributeOverride` đổi tên cột của `AddressZip.code` để tránh trùng với cột `Address.zipCode`. Property Java vẫn là `addressZip.code`; chỉ tên cột vật lý là `legacy_address_code`.

### 5.4. Repository

`src/main/java/com/example/customer/CustomerRepository.java`:

```java
package com.example.customer;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository extends JpaRepository<Customer, Long> {
    List<Customer> findByAddress_ZipCode(String zipCode);

    List<Customer> findByAddressZipCode(String code);

    List<Customer> findByAddress_ZipCodeAndAddress_StreetContainingIgnoreCase(
            String zipCode, String streetPart);
}
```

Ý nghĩa:
- `findByAddress_ZipCode`: truy vấn `customer.address.zipCode` vì dấu gạch dưới cố định điểm tách.
- `findByAddressZipCode`: trong mô hình này, parser có thể khớp `customer.addressZip.code`, do `addressZip` là property trực tiếp và `AddressZip` có `code`.
- `findByAddress_ZipCodeAndAddress_StreetContainingIgnoreCase`: kết hợp hai điều kiện, mỗi đường dẫn được phân tách rõ; điều kiện thứ hai dùng `Containing` và `IgnoreCase`.

Không dựa vào cách parser tự đoán khi có hai đường dẫn hợp lệ. Hãy dùng `_` để thể hiện chính xác property path mà bạn muốn.

## 6. Kiểm thử truy vấn và phân giải property path

Ví dụ dùng Java 17+, Maven, Spring Boot 3.5.0, Spring Data JPA và H2. Dependency cần có `spring-boot-starter-data-jpa`, H2 runtime và `spring-boot-starter-test` ở test scope.

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:customerdb;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.show-sql=true
```

`src/test/java/com/example/customer/CustomerRepositoryTest.java`:

```java
package com.example.customer;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
class CustomerRepositoryTest {
    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void underscoreForcesTraversalThroughAddress() {
        customerRepository.saveAll(List.of(
                new Customer(
                        "Lan",
                        new Address("12 Nguyen Trai", "700000"),
                        new AddressZip("LEGACY-700000")),
                new Customer(
                        "Minh",
                        new Address("25 Le Loi", "100000"),
                        new AddressZip("LEGACY-100000"))));
        customerRepository.flush();

        List<Customer> customers = customerRepository.findByAddress_ZipCode("700000");

        assertThat(customers)
                .extracting(Customer::getName)
                .containsExactly("Lan");
    }

    @Test
    void unseparatedNameResolvesAddressZipCodePath() {
        customerRepository.save(new Customer(
                "Lan",
                new Address("12 Nguyen Trai", "700000"),
                new AddressZip("LEGACY-700000")));
        customerRepository.flush();

        List<Customer> customers = customerRepository.findByAddressZipCode("LEGACY-700000");

        assertThat(customers)
                .extracting(Customer::getName)
                .containsExactly("Lan");
    }

    @Test
    void combinesNestedPredicates() {
        customerRepository.save(new Customer(
                "Lan",
                new Address("12 Nguyen Trai", "700000"),
                new AddressZip("LEGACY-700000")));
        customerRepository.save(new Customer(
                "An",
                new Address("12 Tran Hung Dao", "700000"),
                new AddressZip("LEGACY-700000")));
        customerRepository.flush();

        List<Customer> customers = customerRepository
                .findByAddress_ZipCodeAndAddress_StreetContainingIgnoreCase(
                        "700000", "nguyen");

        assertThat(customers)
                .extracting(Customer::getName)
                .containsExactly("Lan");
    }
}
```

Chạy kiểm thử tại thư mục chứa `pom.xml`:

```bash
mvn test
```

Kết quả mong đợi là `BUILD SUCCESS` và cả ba test đều thành công. Test đầu xác nhận dấu `_` buộc parser đi theo `address.zipCode`; test thứ hai xác nhận tên không phân tách có thể khớp `addressZip.code`; test thứ ba xác nhận nhiều nested predicate kết hợp bằng `And`. Đây là kết quả kỳ vọng theo ví dụ, chưa phải log build thực tế.

## 7. Duyệt qua quan hệ Entity thay vì @Embedded

Property path không chỉ dùng cho `@Embedded`. Spring Data có thể đi qua quan hệ Entity như `@ManyToOne` hoặc `@OneToOne`.

Giả sử `PurchaseOrder` có thuộc tính `customer`, `Customer` có `address`, và `Address` có `zipCode`. Có thể khai báo:

```java
List<PurchaseOrder> findByCustomer_Address_ZipCode(String zipCode);
```

Đường dẫn tương ứng là `purchaseOrder.customer.address.zipCode`. Mỗi dấu gạch dưới xác định một ranh giới traversal rõ ràng.

JPQL tương đương:

```java
@Query("select o from PurchaseOrder o where o.customer.address.zipCode = :zipCode")
List<PurchaseOrder> findOrdersByCustomerZipCode(@Param("zipCode") String zipCode);
```

Trong JPQL, dùng dấu chấm để đi qua thuộc tính; dấu gạch dưới chỉ là cú pháp phân tách trong tên derived query.

## 8. Các từ khóa truy vấn có thể kết hợp với nested property

Nested property có thể kết hợp với nhiều keyword của Spring Data:

| Keyword | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `IgnoreCase` | So sánh chuỗi không phân biệt hoa/thường. | `findByAddress_ZipCodeIgnoreCase(...)` |
| `Containing` | Chuỗi chứa giá trị tìm kiếm. | `findByAddress_StreetContaining(...)` |
| `StartingWith` | Bắt đầu bằng chuỗi. | `findByAddress_StreetStartingWith(...)` |
| `Between` | Nằm trong khoảng. | `findByMetrics_ScoreBetween(...)` |
| `IsNull` | Giá trị null. | `findByAddress_IsNull()` |
| `And`, `Or` | Kết hợp điều kiện. | `findByAddress_ZipCodeAndName(...)` |
| `OrderBy` | Sắp xếp kết quả. | `findByAddress_ZipCodeOrderByNameAsc(...)` |

Keyword được áp dụng lên property cuối cùng của đường dẫn. Hãy kiểm tra kiểu dữ liệu: `Containing` thường dùng cho chuỗi hoặc collection phù hợp; `Between` yêu cầu kiểu có thể so sánh theo ngữ nghĩa của provider.

## 9. Khi nào nên dùng @Query?

Derived query phù hợp khi tên phương thức vẫn ngắn và dễ hiểu. Nếu đường dẫn quá sâu hoặc kết hợp nhiều điều kiện, `@Query` có thể giúp ý định rõ hơn.

```java
@Query("""
       select c
       from Customer c
       where c.address.zipCode = :zipCode
         and lower(c.address.street) like lower(concat('%', :streetPart, '%'))
       """)
List<Customer> searchByAddress(
        @Param("zipCode") String zipCode,
        @Param("streetPart") String streetPart);
```

JPQL dùng tên Entity và thuộc tính Java, không dùng tên bảng hoặc tên cột vật lý. Khi truy vấn cần join phức tạp, projection hoặc fetch plan, hãy chọn cách khai báo dễ bảo trì nhất thay vì cố kéo dài method name.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Query đi nhầm nested path | Parser chọn property trực tiếp dài hơn trước khi tách camel case. | Chèn `_` tại điểm traversal, ví dụ `Address_ZipCode`. |
| Spring báo không tìm thấy property | Tên property sai hoặc đường dẫn đi vào kiểu không có thuộc tính tiếp theo. | Đối chiếu chính xác tên field/getter persistent và kiểu của từng bước. |
| Tên cột snake_case không hoạt động trong method name | Derived query dùng tên property Java, không dùng tên cột. | Dùng camelCase property, ví dụ `zipCode`, dù cột là `zip_code`. |
| Tên property có `_` gây parser khó hiểu | Dấu `_` được dành làm dấu phân tách đường dẫn. | Tránh underscore trong tên persistent property Java. |
| Query nested trả kết quả chậm | Traversal qua association có thể tạo join hoặc truy vấn bổ sung. | Kiểm tra SQL, index và dùng projection/fetch plan phù hợp. |
| `IgnoreCase` không cho kết quả như mong đợi | Database collation hoặc kiểu dữ liệu có quy tắc so sánh khác. | Kiểm tra SQL sinh ra và collation; chuẩn hóa dữ liệu nếu cần. |
| Method name quá dài, khó đọc | Derived query chứa nhiều nhánh và property lồng nhau. | Chuyển sang `@Query`, Specification hoặc custom repository. |

## 11. Nguyên tắc thiết kế

1. Đặt tên persistent property bằng camelCase và dùng `_` chỉ để phân tách nested path trong tên derived query.
2. Khi có nhiều đường dẫn có thể khớp, luôn chỉ rõ traversal point thay vì phụ thuộc vào cách parser tự đoán.
3. Dùng tên thuộc tính Java trong derived query và JPQL; dùng tên cột chỉ trong SQL native hoặc mapping annotation.
4. Giữ method name ngắn, có ý nghĩa; chuyển truy vấn quá phức tạp sang `@Query` hoặc custom repository.
5. Kiểm tra SQL được sinh ra khi query có nhiều association hoặc điều kiện nested.
6. Dùng index trên các cột thường xuyên lọc/join và đánh giá execution plan với dữ liệu gần thực tế.
7. Không nhầm dấu `_` trong method name với dấu gạch dưới của tên cột database.

## 12. Checklist hoàn thành

- [ ] Giải thích được cách Spring Data phân giải property path.
- [ ] Mô tả được quy tắc thử direct property trước rồi mới tách camel case.
- [ ] Nhận biết được trường hợp `addressZip.code` cạnh tranh với `address.zipCode`.
- [ ] Dùng `findByAddress_ZipCode` để cố định đường dẫn mong muốn.
- [ ] Dùng nested property qua cả `@Embedded` và quan hệ Entity.
- [ ] Kết hợp được nested path với `IgnoreCase`, `Containing`, `And`, `Or` và `OrderBy`.
- [ ] Chọn được giữa derived query và `@Query` dựa trên độ phức tạp.
- [ ] Kiểm tra được truy vấn bằng integration test.

Khi hoàn thành, bạn có thể viết derived query dễ đọc, kiểm soát chính xác cách Spring Data đi qua các thuộc tính lồng nhau và tránh lỗi do tên property có nhiều cách phân giải.