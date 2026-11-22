# Xử lý null, boolean, In và NotIn trong Spring Data JPA

## Mục tiêu

Sau bài này, bạn có thể viết derived query để tìm giá trị `NULL`, lọc thuộc tính boolean và tìm theo một tập giá trị bằng `In`/`NotIn`; giải thích được vì sao SQL xử lý `NULL` khác giá trị thông thường; nhận diện các bẫy khi collection chứa `null` hoặc rỗng; và kiểm thử repository để xác nhận kết quả.

Các ví dụ dùng Java 17+, Spring Boot 3+, Spring Data JPA và Jakarta Persistence (`jakarta.persistence.*`). Entity/repository là mã trong ứng dụng Spring Boot có `spring-boot-starter-data-jpa`, `DataSource` và JDBC driver. Integration test cần `spring-boot-starter-test` cùng database kiểm thử như H2.

## 1. SQL NULL và logic ba giá trị

Trong Java, `null` biểu thị không có giá trị tham chiếu. Trong SQL, `NULL` biểu thị giá trị chưa biết hoặc không hiện diện. Vì vậy, không thể so sánh `NULL` bằng `=` hoặc `<>` như một giá trị bình thường.

```sql
SELECT * FROM customers WHERE email = NULL;
```

Điều kiện `email = NULL` cho kết quả `UNKNOWN`, không phải `TRUE`. Trong `WHERE`, chỉ hàng có điều kiện `TRUE` được giữ lại; `FALSE` và `UNKNOWN` đều bị loại. SQL vì vậy có logic ba giá trị:

| Biểu thức | Kết quả |
| --- | --- |
| `NULL = NULL` | `UNKNOWN` |
| `NULL <> 'a@example.test'` | `UNKNOWN` |
| `NULL IS NULL` | `TRUE` |
| `'a@example.test' IS NULL` | `FALSE` |
| `NULL IS NOT NULL` | `FALSE` |

Để tìm giá trị thiếu, dùng `IS NULL`; để tìm giá trị đã có, dùng `IS NOT NULL`:

```sql
SELECT * FROM customers WHERE email IS NULL;
SELECT * FROM customers WHERE email IS NOT NULL;
```

Quy tắc này cũng ảnh hưởng tới boolean, `IN`, `NOT IN` và các điều kiện kết hợp. Hiểu `UNKNOWN` giúp tránh các truy vấn trả ít hàng hơn dự kiến.

## 2. Derived query với IsNull và IsNotNull

Spring Data JPA phân tích tên method repository và tạo truy vấn theo thuộc tính entity. Các keyword kiểm tra null gồm:

- `IsNull` hoặc `Null`: điều kiện `IS NULL`.
- `IsNotNull` hoặc `NotNull`: điều kiện `IS NOT NULL`.

Ví dụ `CustomerRepository.java`:

```java
package com.example.learning.customer;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository extends JpaRepository<Customer, Long> {
    List<Customer> findByEmailIsNull();

    List<Customer> findByEmailIsNotNull();
}
```

Hai method tương ứng với điều kiện SQL `email IS NULL` và `email IS NOT NULL`. Không cần truyền tham số `null`; tên method đã nói rõ ý định truy vấn.

### 2.1. Null không phải chuỗi rỗng

`NULL`, chuỗi rỗng `''` và chuỗi chỉ có khoảng trắng `'   '` là các giá trị khác nhau:

- `email IS NULL`: cột không có giá trị.
- `email = ''`: cột chứa chuỗi rỗng.
- `TRIM(email) = ''`: sau khi bỏ khoảng trắng, chuỗi không còn ký tự.

JPA không tự động coi chuỗi rỗng hoặc khoảng trắng là `NULL`. Nếu nghiệp vụ xem chúng như cùng một trạng thái, hãy chuẩn hóa dữ liệu đầu vào hoặc viết truy vấn thể hiện rõ chính sách.

```java
@Query("select c from Customer c where c.email = ''")
List<Customer> findWithEmptyEmail();
```

Đây là JPQL tìm chuỗi rỗng. Nếu cần xử lý khoảng trắng, có thể cân nhắc `trim(c.email) = ''`; hãy kiểm thử trên database và provider đang dùng.

### 2.2. Kết hợp điều kiện null

Có thể kết hợp keyword bằng `And` và `Or`:

```java
List<Customer> findByEmailIsNotNullAndActiveTrue();
List<Customer> findByEmailIsNullOrActiveFalse();
```

Method đầu tìm khách hàng có email và đang active. Method thứ hai tìm khách hàng thiếu email hoặc có `active = false`. Khi logic có nhiều nhánh, dùng `@Query` hoặc `Specification` nếu tên method trở nên khó đọc hoặc khó diễn đạt ngoặc logic.

## 3. Boolean: True, False và giá trị chưa biết

Spring Data JPA hỗ trợ keyword `True`/`IsTrue` và `False`/`IsFalse`:

```java
List<Customer> findByActiveTrue();
List<Customer> findByActiveFalse();
```

Ý nghĩa tương ứng là `active = TRUE` và `active = FALSE`. SQL `NULL` không được xem là `false`; nếu thuộc tính boolean có thể thiếu giá trị, phải truy vấn trạng thái đó riêng.

### 3.1. boolean hay Boolean?

| Kiểu Java | Giá trị có thể có | Khi phù hợp |
| --- | --- | --- |
| `boolean` | `true`, `false` | Trạng thái luôn được xác định |
| `Boolean` | `true`, `false`, `null` | Nghiệp vụ có trạng thái chưa biết/chưa thiết lập |

Ví dụ entity có trạng thái ba giá trị:

```java
package com.example.learning.customer;

import jakarta.persistence.Column;
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

    @Column
    private String email;

    @Column
    private Boolean active;

    protected Customer() {
    }

    public Customer(String email, Boolean active) {
        this.email = email;
        this.active = active;
    }

    public Long getId() { return id; }
    public String getEmail() { return email; }
    public Boolean getActive() { return active; }
}
```

Repository:

```java
package com.example.learning.customer;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository extends JpaRepository<Customer, Long> {
    List<Customer> findByActiveTrue();
    List<Customer> findByActiveFalse();
    List<Customer> findByActiveIsNull();
    List<Customer> findByActiveIsNotNull();
}
```

Với `Boolean active`, các method trên lần lượt tìm `true`, `false`, `NULL` và giá trị đã được thiết lập. `findByActiveFalse()` không bao gồm hàng có `active IS NULL`.

Nếu trạng thái luôn bắt buộc, dùng `boolean` và khai báo cột `NOT NULL` trong schema, ví dụ `@Column(nullable = false)`. Nếu cần phân biệt “chưa xác định” với “đã tắt”, dùng `Boolean` và định nghĩa rõ ý nghĩa của cả ba trạng thái. Không dùng `null` thay cho `false` chỉ để né quyết định nghiệp vụ.

### 3.2. Tên property phải khớp entity

Spring Data phân tích tên thuộc tính persistent. Với field `active`, getter có thể là `getActive()` cho `Boolean` hoặc `isActive()` cho `boolean`; property JavaBeans vẫn tên `active`, vì vậy repository dùng `findByActiveTrue()`.

Nếu entity đặt tên field là `isActive`, hãy kiểm tra property name thực tế thay vì suy ra từ tên getter. Cách dễ hiểu nhất là đặt thuộc tính là `active` và tuân theo quy ước JavaBeans.

## 4. IN: tìm giá trị thuộc một tập

`In` tạo điều kiện kiểm tra một thuộc tính có thuộc tập giá trị được truyền vào hay không. Tham số có thể là `Collection`, `List`, array hoặc varargs; ví dụ dùng `Collection`:

```java
package com.example.learning.customer;

import java.util.Collection;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository extends JpaRepository<Customer, Long> {
    List<Customer> findByStatusIn(Collection<CustomerStatus> statuses);
}
```

Enum được ánh xạ dưới dạng chuỗi:

```java
package com.example.learning.customer;

public enum CustomerStatus {
    NEW, ACTIVE, SUSPENDED, CLOSED
}
```

Trong entity, khai báo:

```java
@Enumerated(EnumType.STRING)
@Column(name = "status")
private CustomerStatus status;
```

Gọi repository:

```java
List<Customer> result = repository.findByStatusIn(
    List.of(CustomerStatus.NEW, CustomerStatus.ACTIVE)
);
```

Ý nghĩa SQL tương đương:

```sql
SELECT * FROM customers WHERE status IN ('NEW', 'ACTIVE');
```

Tham số được bind riêng; không nối chuỗi đầu vào vào SQL. Điều này giúp database xử lý kiểu dữ liệu đúng và tránh injection do tự ghép câu lệnh.

### 4.1. Kết hợp In với điều kiện khác

```java
List<Customer> findByStatusInAndActiveTrue(
    Collection<CustomerStatus> statuses
);

List<Customer> findByStatusInAndEmailIsNotNull(
    Collection<CustomerStatus> statuses
);
```

Method đầu tìm khách hàng thuộc một trong các trạng thái và đang active. Method thứ hai chỉ lấy khách hàng có email.

### 4.2. In với cột null

Nếu `status` là `NULL`, biểu thức `status IN ('NEW', 'ACTIVE')` cho kết quả `UNKNOWN`, nên hàng đó không được trả về. Nếu muốn bao gồm cả hàng có status null, thể hiện điều kiện riêng:

```java
List<Customer> findByStatusInOrStatusIsNull(
    Collection<CustomerStatus> statuses
);
```

Ý nghĩa là `status IN (...) OR status IS NULL`. Trước khi gọi vẫn cần quyết định rõ cách xử lý collection rỗng và phần tử null.

## 5. NOT IN: loại trừ một tập giá trị

`NotIn` trả về các hàng có thuộc tính không thuộc tập được truyền vào:

```java
List<Customer> findByStatusNotIn(
    Collection<CustomerStatus> excludedStatuses
);
```

SQL có dạng:

```sql
SELECT * FROM customers WHERE status NOT IN ('CLOSED', 'SUSPENDED');
```

Điểm cần nhớ: `NOT IN` chỉ giữ hàng mà biểu thức là `TRUE`. Hàng có `status IS NULL` cho kết quả `UNKNOWN` và bị loại. Vì vậy, `findByStatusNotIn(...)` mặc định không bao gồm entity có status null.

Nếu muốn loại trừ một tập nhưng vẫn bao gồm status null, khai báo method riêng:

```java
List<Customer> findByStatusNotInOrStatusIsNull(
    Collection<CustomerStatus> excludedStatuses
);
```

Đây là điều kiện `status NOT IN (...) OR status IS NULL`. Chỉ dùng khi null phải là một nhóm kết quả hợp lệ theo nghiệp vụ.

## 6. Bẫy: phần tử null trong collection NOT IN

Giả sử tham số là `('CLOSED', NULL)`:

```sql
status NOT IN ('CLOSED', NULL)
```

Với một hàng có `status = 'ACTIVE'`, phép so sánh tương đương:

```sql
status <> 'CLOSED' AND status <> NULL
```

Vế đầu là `TRUE`, vế sau là `UNKNOWN`; `TRUE AND UNKNOWN` cho kết quả `UNKNOWN`. Hàng đó bị loại. Một phần tử null trong danh sách có thể làm `NOT IN` trả về ít hàng hơn nhiều so với mong đợi, thậm chí không có hàng nào.

Với `IN`, một phần tử null cũng không làm giá trị null trong cột tự động khớp. Ví dụ `status IN ('NEW', NULL)` chỉ chắc chắn khớp hàng `NEW`; các hàng không khớp giá trị nào sẽ có kết quả `UNKNOWN`.

Quy tắc thực hành:

- Không truyền phần tử `null` trong collection dùng cho `In`/`NotIn`, trừ khi đã định nghĩa rõ cách xử lý.
- Nếu cần tìm cột null, dùng `IsNull` hoặc thêm nhánh `Or...IsNull`.
- Với `NotIn`, kiểm tra và từ chối hoặc loại phần tử null trước khi gọi repository.
- Với `NOT IN (subquery)`, bảo đảm subquery không trả về null; nếu không kiểm soát được, cân nhắc `NOT EXISTS`.

## 7. Collection rỗng và collection null

Collection null và collection rỗng là hai tình huống khác nhau. Null thường có nghĩa caller không cung cấp tập; collection rỗng có nghĩa tập không có phần tử.

Theo logic tập hợp, `x IN empty` không khớp hàng nào, còn `x NOT IN empty` không loại trừ giá trị nào. Tuy nhiên, SQL không có cách biểu diễn `IN ()` thống nhất giữa mọi database; hành vi cụ thể còn phụ thuộc provider. Hãy xử lý collection rỗng ở tầng service trước khi gọi repository.

Ví dụ service áp dụng chính sách rõ ràng:

```java
package com.example.learning.customer;

import java.util.Collection;
import java.util.List;
import java.util.Objects;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class CustomerSearchService {
    private final CustomerRepository customers;

    public CustomerSearchService(CustomerRepository customers) {
        this.customers = customers;
    }

    public List<Customer> findWithStatuses(
            Collection<CustomerStatus> statuses) {
        requireCollection(statuses, "statuses");
        if (statuses.isEmpty()) return List.of();
        rejectNullElements(statuses, "statuses");
        return customers.findByStatusIn(statuses);
    }

    public List<Customer> findOutsideStatuses(
            Collection<CustomerStatus> excludedStatuses) {
        requireCollection(excludedStatuses, "excludedStatuses");
        if (excludedStatuses.isEmpty()) return customers.findAll();
        rejectNullElements(excludedStatuses, "excludedStatuses");
        return customers.findByStatusNotIn(excludedStatuses);
    }

    private static void requireCollection(
            Collection<?> values, String name) {
        if (values == null) {
            throw new IllegalArgumentException(name + " must not be null");
        }
    }

    private static void rejectNullElements(
            Collection<?> values, String name) {
        if (values.stream().anyMatch(Objects::isNull)) {
            throw new IllegalArgumentException(
                name + " must not contain null elements"
            );
        }
    }
}
```

Trong ví dụ, service chọn hai quy tắc cụ thể: tập tìm kiếm rỗng trả về danh sách rỗng; tập loại trừ rỗng có nghĩa không loại trạng thái nào nên trả về tất cả khách hàng. `findOutsideStatuses` dùng `findByStatusNotIn`, vì vậy entity có `status IS NULL` vẫn bị loại. Nếu nghiệp vụ muốn bao gồm nhóm null, dùng `findByStatusNotInOrStatusIsNull`.

Không áp dụng chính sách này máy móc cho mọi API. Với endpoint này, collection rỗng có thể mang nghĩa “không lọc”; với endpoint khác, nó có thể mang nghĩa “không có kết quả”. Hãy định nghĩa rõ hợp đồng đầu vào.

## 8. Entity và repository đầy đủ cho ví dụ

`Customer.java`:

```java
package com.example.learning.customer;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
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

    @Column
    private String email;

    @Column
    private Boolean active;

    @Enumerated(EnumType.STRING)
    @Column
    private CustomerStatus status;

    protected Customer() {
    }

    public Customer(String email, Boolean active, CustomerStatus status) {
        this.email = email;
        this.active = active;
        this.status = status;
    }

    public Long getId() { return id; }
    public String getEmail() { return email; }
    public Boolean getActive() { return active; }
    public CustomerStatus getStatus() { return status; }
}
```

`CustomerStatus.java`:

```java
package com.example.learning.customer;

public enum CustomerStatus {
    NEW, ACTIVE, SUSPENDED, CLOSED
}
```

`CustomerRepository.java`:

```java
package com.example.learning.customer;

import java.util.Collection;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository extends JpaRepository<Customer, Long> {
    List<Customer> findByEmailIsNull();
    List<Customer> findByEmailIsNotNull();
    List<Customer> findByActiveTrue();
    List<Customer> findByActiveFalse();
    List<Customer> findByActiveIsNull();
    List<Customer> findByActiveIsNotNull();
    List<Customer> findByStatusIn(Collection<CustomerStatus> statuses);
    List<Customer> findByStatusNotIn(Collection<CustomerStatus> statuses);
    List<Customer> findByStatusNotInOrStatusIsNull(
        Collection<CustomerStatus> statuses
    );
}
```

Đây là các tệp cùng package. Nếu dự án đã có entity hoặc enum tương ứng, hãy thêm method phù hợp vào repository hiện tại và dùng đúng tên property trong entity; không tạo class trùng tên.

## 9. Integration test cho null, boolean, In và NotIn

Test dưới đây lưu bốn khách hàng đại diện cho các trạng thái khác nhau rồi truy vấn qua repository. `@DataJpaTest` cấu hình lát cắt persistence, chạy test trong transaction và thường rollback dữ liệu sau mỗi test.

`CustomerRepositoryQueryTest.java`:

```java
package com.example.learning.customer;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class CustomerRepositoryQueryTest {
    @Autowired
    private CustomerRepository customers;

    @Test
    void handlesNullBooleanInAndNotIn() {
        customers.saveAll(List.of(
            new Customer(null, true, CustomerStatus.NEW),
            new Customer("paid@example.test", false, CustomerStatus.ACTIVE),
            new Customer("suspended@example.test", null, CustomerStatus.SUSPENDED),
            new Customer("unknown@example.test", true, null)
        ));
        customers.flush();

        assertThat(customers.findByEmailIsNull()).hasSize(1);
        assertThat(customers.findByEmailIsNotNull()).hasSize(3);
        assertThat(customers.findByActiveTrue()).hasSize(2);
        assertThat(customers.findByActiveFalse()).hasSize(1);
        assertThat(customers.findByActiveIsNull()).hasSize(1);

        assertThat(customers.findByStatusIn(
            List.of(CustomerStatus.NEW, CustomerStatus.SUSPENDED)
        )).hasSize(2);

        assertThat(customers.findByStatusNotIn(
            List.of(CustomerStatus.NEW, CustomerStatus.SUSPENDED)
        )).hasSize(1);

        assertThat(customers.findByStatusNotInOrStatusIsNull(
            List.of(CustomerStatus.NEW, CustomerStatus.SUSPENDED)
        )).hasSize(2);
    }
}
```

Test giả định project có `spring-boot-starter-data-jpa`, `spring-boot-starter-test` và H2 trong test runtime, cùng cấu hình database kiểm thử. Fixture gồm một email null, một Boolean null và một status null.

Kết quả mong đợi:

| Truy vấn | Số hàng | Giải thích |
| --- | ---: | --- |
| `findByEmailIsNull()` | 1 | Khách hàng không có email |
| `findByEmailIsNotNull()` | 3 | Ba khách hàng có email |
| `findByActiveTrue()` | 2 | Hai khách hàng có active true |
| `findByActiveFalse()` | 1 | Một khách hàng có active false |
| `findByActiveIsNull()` | 1 | Một khách hàng chưa có trạng thái active |
| `findByStatusIn(NEW, SUSPENDED)` | 2 | Hai trạng thái thuộc tập tìm kiếm |
| `findByStatusNotIn(NEW, SUSPENDED)` | 1 | Chỉ ACTIVE; status null bị loại |
| `findByStatusNotInOrStatusIsNull(NEW, SUSPENDED)` | 2 | ACTIVE và status null |

Chạy test bằng Maven Wrapper:

```bash
./mvnw -Dtest=CustomerRepositoryQueryTest test
```

Trên Windows PowerShell:

```powershell
.\mvnw.cmd -Dtest=CustomerRepositoryQueryTest test
```

Test cần chạy trong project có dependency và cấu hình phù hợp. Không sao chép riêng class test vào project Java thuần vì `@DataJpaTest`, Spring context và repository proxy cần môi trường Spring Boot.

## 10. Khi nào nên dùng @Query?

Derived query phù hợp với điều kiện đơn giản. Khi logic có nhiều nhánh, tham số tùy chọn hoặc cần `NOT EXISTS`, `@Query` có thể diễn đạt rõ hơn.

Ví dụ JPQL bao gồm status null khi loại trừ một tập:

```java
@Query("""
    select c
    from Customer c
    where c.status not in :excluded
       or c.status is null
    """)
List<Customer> findOutsideStatusesIncludingNull(
    @Param("excluded") Collection<CustomerStatus> excluded
);
```

Đoạn này dùng Java text block và JPQL. Với collection rỗng, vẫn nên xử lý ở service trước khi gọi. Nếu nhiều bộ lọc có thể bật/tắt theo request, cân nhắc `Specification` để thêm predicate theo từng điều kiện thay vì một câu `(:param is null OR ...)` dài.

Trong native SQL, `:param is null` có thể gặp vấn đề suy luận kiểu tham số ở một số database/driver. Hãy kiểm thử trên database thật và tránh dùng null parameter mơ hồ để biểu thị “bỏ qua bộ lọc”.

## 11. Hiệu năng và giới hạn của IN/NOT IN

Với danh sách nhỏ, `IN` thường là cách tự nhiên để lọc theo tập. Khi danh sách rất lớn, mỗi phần tử có thể trở thành bind parameter và gây ra các vấn đề:

- Database có giới hạn số bind parameter hoặc kích thước câu lệnh.
- SQL dài làm tăng chi phí parse và truyền dữ liệu.
- Optimizer có thể chọn execution plan kém khi tập giá trị lớn hoặc độ chọn lọc thay đổi mạnh.
- `NOT IN` có thể khó tối ưu nếu tập loại trừ lớn hoặc đến từ subquery.

Với danh sách lớn, cân nhắc chia batch có kiểm soát, bảng tạm, staging table, table-valued parameter (nếu database hỗ trợ), join với bảng chứa tập giá trị hoặc một chiến lược tìm kiếm khác. Nếu ghép kết quả nhiều batch, phải xử lý phân trang, trùng lặp và thứ tự.

Index trên cột lọc có thể giúp `IN`, `NOT IN`, `IS NULL` hoặc `IS NOT NULL`, nhưng hiệu quả phụ thuộc database, tỷ lệ null, độ chọn lọc và điều kiện khác. Cột boolean thường có ít giá trị phân biệt nên index riêng có thể không hữu ích; index kết hợp với cột chọn lọc hơn có thể phù hợp. Kiểm tra execution plan trước khi thêm index.

## 12. Những lỗi thường gặp

- **Dùng `= NULL` hoặc `<> NULL`.** Dùng `IS NULL`/`IS NOT NULL` vì so sánh với NULL cho kết quả UNKNOWN.
- **Coi null là false.** `Boolean` có ba trạng thái; `findByActiveFalse()` không trả hàng có active null.
- **Dùng primitive boolean khi nghiệp vụ cần trạng thái chưa xác định.** Primitive chỉ có true/false; dùng `Boolean` nếu null là trạng thái hợp lệ.
- **Dùng `NotIn` với collection chứa null.** Một phần tử null có thể làm điều kiện NOT IN thành UNKNOWN và loại các hàng mong muốn.
- **Cho rằng `NotIn` bao gồm cột null.** `NULL NOT IN (...)` là UNKNOWN; thêm `OrStatusIsNull` nếu cần.
- **Gửi collection rỗng trực tiếp xuống repository.** Xử lý ở service theo hợp đồng nghiệp vụ để tránh phụ thuộc SQL/provider.
- **Dùng null collection như empty collection.** Hai đầu vào có thể mang ý nghĩa khác nhau; kiểm tra và quyết định rõ.
- **Dùng `In` để tìm giá trị null trong cột.** Dùng `IsNull` hoặc thêm nhánh `Or...IsNull`.
- **Nối chuỗi giá trị vào SQL.** Dùng derived query hoặc bind parameter.
- **Dùng một danh sách IN rất lớn mà không đo.** Xem giới hạn parameter, execution plan và cân nhắc bảng tạm hoặc join.

## 13. Checklist trước khi đưa query vào ứng dụng

- [ ] Thuộc tính có thể null hay luôn bắt buộc? Mapping Java và constraint database có thống nhất không?
- [ ] Cần tìm null, chuỗi rỗng hay chuỗi chỉ có khoảng trắng?
- [ ] Với Boolean, null có ý nghĩa nghiệp vụ riêng không?
- [ ] `In`/`NotIn` nhận collection không null và không chứa phần tử null?
- [ ] Collection rỗng có hợp đồng rõ ràng ở tầng service?
- [ ] `NotIn` có cần bao gồm các hàng có thuộc tính null không?
- [ ] Test đã bao phủ true, false, null, tập có giá trị và collection rỗng?
- [ ] Truy vấn có danh sách lớn đã được đo trên database thực tế?
- [ ] SQL dùng bind parameter và index đã được kiểm tra bằng execution plan?

## Kết luận

Trong Spring Data JPA, dùng `IsNull`/`IsNotNull` để diễn đạt rõ việc tìm giá trị thiếu; dùng `True`/`False` cho thuộc tính boolean; dùng `In`/`NotIn` cho tập giá trị. SQL có logic ba giá trị nên `NULL` không tự khớp với `IN` và thường bị loại khỏi `NOT IN`. Hãy kiểm tra collection null/rỗng/phần tử null ở tầng service, viết method thể hiện rõ chính sách với null và kiểm thử trên database để bảo đảm kết quả đúng với nghiệp vụ.