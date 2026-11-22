# JpaSpecificationExecutor và hợp đồng Specification<T>

## Mục tiêu

Sau bài này, bạn có thể mô tả đúng hợp đồng `Specification<T>.toPredicate(...)`; kết hợp nhiều điều kiện bằng `and`, `or`, `not`; xây dựng bộ lọc tùy chọn từ request; thực thi specification qua `JpaSpecificationExecutor<T>`; và xử lý các vấn đề về join, kết quả trùng, phân trang, count query và kiểm thử.

Các ví dụ dùng Java 17+, Spring Boot 3+, Spring Data JPA và Jakarta Persistence (`jakarta.persistence.*`). Mã minh họa thuộc package `com.example.learning.customer`; nếu dự án đã có entity/repository cùng chức năng, hãy bổ sung các method cần thiết vào cấu trúc hiện tại.

## 1. Specification giải quyết vấn đề gì?

Derived query phù hợp khi điều kiện tìm kiếm đơn giản và cố định, ví dụ `findByActiveTrueAndStatus(...)`. Nhưng màn hình tìm kiếm thường cho phép người dùng nhập nhiều bộ lọc tùy chọn: tên, email, trạng thái, ngày tạo hoặc các điều kiện liên quan. Số tổ hợp có thể tăng nhanh nếu tạo một repository method cho từng trường hợp.

`Specification<T>` cho phép mô tả một điều kiện truy vấn dưới dạng một đối tượng có thể tái sử dụng và kết hợp. Mỗi specification tạo ra một predicate của Criteria API. Repository nhận predicate đó và thực thi truy vấn.

Ví dụ, thay vì tạo riêng nhiều method:

```java
findByActiveTrueAndStatus(...);
findByFirstNameContainingIgnoreCaseAndActiveTrue(...);
findByEmailContainingIgnoreCaseAndStatus(...);
```

Ta có thể tạo các điều kiện độc lập như `firstNameContains(...)`, `activeEquals(...)`, `hasStatus(...)`, rồi ghép chúng theo bộ lọc hiện tại.

## 2. Hợp đồng Specification<T>.toPredicate

`Specification<T>` là functional interface của Spring Data JPA. Phương thức cốt lõi có dạng:

```java
Predicate toPredicate(
    Root<T> root,
    CriteriaQuery<?> query,
    CriteriaBuilder criteriaBuilder
);
```

Ba tham số có vai trò khác nhau:

| Tham số | Vai trò |
| --- | --- |
| `Root<T> root` | Đại diện cho entity gốc đang được truy vấn; dùng để truy cập thuộc tính và tạo join |
| `CriteriaQuery<?> query` | Đại diện cấu trúc truy vấn; có thể dùng cho distinct hoặc tạo subquery khi cần |
| `CriteriaBuilder criteriaBuilder` | Nhà máy tạo predicate và biểu thức như `equal`, `like`, `and`, `or`, `greaterThan`, `isNull` |

Phương thức trả về một `Predicate` mô tả điều kiện lọc. Ví dụ:

```java
public static Specification<Customer> isActive() {
    return (root, query, cb) -> cb.isTrue(root.get("active"));
}
```

Specification không tự chạy SQL và không tự mở transaction. Nó chỉ mô tả predicate; `JpaSpecificationExecutor` mới thực thi truy vấn đó.

Nếu specification không cần thêm điều kiện, có thể trả về `cb.conjunction()` — predicate luôn đúng. Spring Data cũng hỗ trợ predicate `null` như một điều kiện không đóng góp vào phép kết hợp, nhưng dùng `cb.conjunction()` thường làm ý định rõ ràng hơn trong code.

## 3. Bật JpaSpecificationExecutor trong repository

Repository cần kế thừa `JpaSpecificationExecutor<T>` bên cạnh `JpaRepository<T, ID>`:

```java
package com.example.learning.customer;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                JpaSpecificationExecutor<Customer> {
}
```

`JpaSpecificationExecutor<Customer>` cung cấp các thao tác chính:

| Method | Kết quả |
| --- | --- |
| `findAll(spec)` | Danh sách entity khớp điều kiện |
| `findAll(spec, sort)` | Danh sách entity có sắp xếp |
| `findAll(spec, pageable)` | `Page<T>` gồm nội dung và metadata phân trang |
| `findOne(spec)` | `Optional<T>`; báo lỗi nếu có nhiều hơn một kết quả |
| `count(spec)` | Tổng số entity khớp điều kiện |
| `exists(spec)` | Có ít nhất một entity khớp điều kiện hay không |

Đây là executor cho entity type `T` của repository. Nếu cần projection, query shape đặc biệt hoặc tối ưu count riêng, hãy kiểm tra API của phiên bản Spring Data JPA đang dùng hoặc bổ sung custom repository phù hợp.

## 4. Tạo entity và bộ lọc mẫu

Entity đơn giản để minh họa:

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

    @Column(name = "first_name", nullable = false)
    private String firstName;

    @Column(nullable = false)
    private String email;

    @Column(nullable = false)
    private Boolean active;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private CustomerStatus status;

    protected Customer() {
    }

    public Customer(String firstName, String email, Boolean active, CustomerStatus status) {
        this.firstName = firstName;
        this.email = email;
        this.active = active;
        this.status = status;
    }

    public Long getId() { return id; }
    public String getFirstName() { return firstName; }
    public String getEmail() { return email; }
    public Boolean getActive() { return active; }
    public CustomerStatus getStatus() { return status; }
}
```

Enum:

```java
package com.example.learning.customer;

public enum CustomerStatus {
    NEW,
    ACTIVE,
    SUSPENDED
}
```

Request filter:

```java
package com.example.learning.customer;

public record CustomerFilter(
    String firstName,
    String email,
    Boolean active,
    CustomerStatus status
) {
}
```

`Boolean active` cho phép phân biệt bộ lọc không được gửi (`null`) với yêu cầu tìm `active = true` hoặc `active = false`. Nếu nghiệp vụ có nhu cầu tìm cột active đang lưu `NULL`, nên bổ sung một lựa chọn lọc riêng; không dùng cùng một `null` vừa để biểu thị “bỏ qua bộ lọc” vừa để biểu thị “tìm giá trị NULL”.

## 5. Viết specification nhỏ, mỗi điều kiện một nhiệm vụ

Tạo class chứa các factory method trả về `Specification<Customer>`:

```java
package com.example.learning.customer;

import java.util.Locale;
import org.springframework.data.jpa.domain.Specification;

public final class CustomerSpecifications {
    private CustomerSpecifications() {
    }

    public static Specification<Customer> firstNameContains(String value) {
        return (root, query, cb) -> {
            if (value == null || value.isBlank()) {
                return cb.conjunction();
            }
            String pattern = "%" + value.trim().toLowerCase(Locale.ROOT) + "%";
            return cb.like(cb.lower(root.get("firstName")), pattern);
        };
    }

    public static Specification<Customer> emailEqualsIgnoreCase(String value) {
        return (root, query, cb) -> {
            if (value == null || value.isBlank()) {
                return cb.conjunction();
            }
            return cb.equal(
                cb.lower(root.get("email")),
                value.trim().toLowerCase(Locale.ROOT)
            );
        };
    }

    public static Specification<Customer> activeEquals(Boolean value) {
        return (root, query, cb) -> {
            if (value == null) {
                return cb.conjunction();
            }
            return cb.equal(root.get("active"), value);
        };
    }

    public static Specification<Customer> hasStatus(CustomerStatus value) {
        return (root, query, cb) -> {
            if (value == null) {
                return cb.conjunction();
            }
            return cb.equal(root.get("status"), value);
        };
    }

    public static Specification<Customer> from(CustomerFilter filter) {
        return ((Specification<Customer>) (root, query, cb) -> cb.conjunction())
            .and(firstNameContains(filter.firstName()))
            .and(emailEqualsIgnoreCase(filter.email()))
            .and(activeEquals(filter.active()))
            .and(hasStatus(filter.status()));
    }
}
```

Mỗi method có một trách nhiệm:

- `firstNameContains` tìm tên có chứa chuỗi đã nhập, không phân biệt hoa thường.
- `emailEqualsIgnoreCase` so sánh email sau khi chuẩn hóa chữ thường và khoảng trắng đầu/cuối.
- `activeEquals` chỉ thêm predicate khi caller gửi true hoặc false.
- `hasStatus` chỉ lọc status khi có giá trị.
- `from` kết hợp tất cả điều kiện bằng `and`.

Trong ví dụ, `cb.conjunction()` là điều kiện trung tính: khi filter vắng mặt, nó không loại bản ghi nào. Các giá trị đầu vào vẫn được bind thông qua Criteria API; không ghép chuỗi người dùng thành SQL.

### 5.1. Quy tắc null của filter

Điều kiện “không lọc theo email” khác điều kiện “email trong database phải là NULL”. Nếu `null` ở request có nghĩa bỏ qua filter, dùng `cb.conjunction()` như trên. Nếu API cần tìm email null, hãy khai báo một cờ riêng hoặc một filter mode rõ ràng và tạo predicate `cb.isNull(root.get("email"))`.

Tương tự, `active = null` trong filter mẫu có nghĩa không áp dụng điều kiện active. Nó không có nghĩa `active IS NULL`.

### 5.2. Escape ký tự LIKE khi cần tìm literal

Trong `LIKE`, `%` và `_` là wildcard. Nếu người dùng nhập chúng và mong muốn tìm đúng ký tự đó, cần escape theo ký tự escape đã chọn:

```java
private static String escapeLike(String value) {
    return value
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_");
}
```

Predicate có thể dùng overload `cb.like(expression, pattern, '\\')` để chỉ định ký tự escape. Cần kiểm thử cách escape với database mục tiêu; nếu nghiệp vụ muốn `%` và `_` được xem là wildcard thì không escape chúng.

## 6. Kết hợp Specification bằng and, or và not

Mỗi specification có thể dùng độc lập hoặc ghép với specification khác:

```java
Specification<Customer> activeAndNamed =
    CustomerSpecifications.activeEquals(true)
        .and(CustomerSpecifications.firstNameContains("an"));

Specification<Customer> suspendedOrInactive =
    CustomerSpecifications.hasStatus(CustomerStatus.SUSPENDED)
        .or(CustomerSpecifications.activeEquals(false));

Specification<Customer> notSuspended =
    Specification.not(
        CustomerSpecifications.hasStatus(CustomerStatus.SUSPENDED)
    );
```

`and` và `or` có thể kết hợp theo biểu thức nhiều tầng. Hãy đặt biến trung gian hoặc dùng ngoặc rõ ràng để người đọc hiểu chính xác thứ tự logic. Ví dụ `A.and(B).or(C)` tương đương `(A AND B) OR C`, không phải `A AND (B OR C)`.

Specification nên là mô tả điều kiện có thể tái sử dụng. Tránh lưu trạng thái mutable vào object specification hoặc thay đổi biến dùng chung giữa các request; factory method tạo predicate từ tham số đầu vào sẽ an toàn và dễ kiểm thử hơn.

## 7. Thực thi specification với phân trang và sắp xếp

Service có thể chuyển filter từ request thành specification rồi gọi repository:

```java
package com.example.learning.customer;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerSearchService {
    private final CustomerRepository customers;

    public CustomerSearchService(CustomerRepository customers) {
        this.customers = customers;
    }

    @Transactional(readOnly = true)
    public Page<Customer> search(CustomerFilter filter, Pageable pageable) {
        return customers.findAll(CustomerSpecifications.from(filter), pageable);
    }
}
```

Ví dụ caller tạo trang:

```java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(Sort.Order.asc("lastName"), Sort.Order.asc("id"))
);
```

Trong entity minh họa ở trên chưa có `lastName`; vì vậy khi dùng đúng entity đó, hãy sort theo thuộc tính tồn tại, chẳng hạn `Sort.by("firstName").and(Sort.by("id"))`. Các thuộc tính sort phải là property Java hợp lệ của entity, không phải tên cột SQL.

`Page<T>` cung cấp nội dung trang, `totalElements` và `totalPages`. Để tính tổng số phần tử, Spring Data thường chạy count query bổ sung. Với bảng lớn hoặc specification có join phức tạp, count có thể tốn đáng kể.

## 8. Join quan hệ và nguy cơ kết quả trùng

Specification có thể join sang entity liên quan. Ví dụ, giả sử `Customer` có collection `orders` và mỗi order có `status`:

```java
public static Specification<Customer> hasOrderWithStatus(OrderStatus status) {
    return (root, query, cb) -> {
        var orders = root.join("orders", JoinType.INNER);
        query.distinct(true);
        return cb.equal(orders.get("status"), status);
    };
}
```

Đây là fragment minh họa, giả định entity có association `orders` và enum `OrderStatus`. Khi một customer có nhiều order cùng thỏa điều kiện, join có thể tạo nhiều hàng SQL cho cùng một customer. `query.distinct(true)` yêu cầu kết quả entity không bị lặp.

Việc đặt `distinct` có thể ảnh hưởng cách database/provider tạo count query và cách phân trang được tính. Hãy kiểm thử `content`, `totalElements` và số trang với dữ liệu có nhiều bản ghi quan hệ. Với một số trường hợp, truy vấn bằng `exists` subquery phù hợp hơn join trực tiếp vì nó kiểm tra sự tồn tại mà không nhân hàng kết quả.

Không thêm join chỉ vì có quan hệ trong entity. Mỗi join có thể làm tăng chi phí, thay đổi cardinality hoặc khiến count query phức tạp hơn.

## 9. Dùng subquery khi cần kiểm tra sự tồn tại

Với quan hệ một-nhiều, `exists` có thể biểu diễn điều kiện “customer có ít nhất một order thỏa mãn” mà không cần trả các hàng order trong kết quả chính:

```java
public static Specification<Customer> hasPaidOrder() {
    return (root, query, cb) -> {
        var subquery = query.subquery(Long.class);
        var order = subquery.from(PurchaseOrder.class);

        subquery.select(order.get("id"));
        subquery.where(
            cb.equal(order.get("customer"), root),
            cb.equal(order.get("status"), OrderStatus.PAID)
        );

        return cb.exists(subquery);
    };
}
```

Đoạn này giả định `PurchaseOrder.customer` là quan hệ tới `Customer` và `PurchaseOrder.status` có kiểu `OrderStatus`. Predicate `exists` trả về true khi subquery tìm thấy ít nhất một order đã thanh toán cho customer hiện tại.

Subquery có thể giúp tránh duplicate root rows do join, nhưng không mặc định nhanh hơn trong mọi database. So sánh execution plan và index của khóa ngoại/trạng thái trên dữ liệu thực tế.

## 10. Specification nên tập trung vào predicate

Tham số `CriteriaQuery<?> query` cho phép specification tác động tới cấu trúc truy vấn. Tuy nhiên, `JpaSpecificationExecutor` có thể dùng specification cho cả truy vấn lấy dữ liệu và count query khi phân trang.

Vì vậy, một specification có `fetch join`, `orderBy`, `groupBy` hoặc thay đổi select list có thể gây vấn đề khi Spring Data tái sử dụng nó cho count query. Ví dụ fetch join collection có thể không hợp lệ trong count query hoặc làm kết quả phân trang sai.

Quy tắc thiết kế thực tế:

- Ưu tiên trả về predicate và giữ specification tập trung vào điều kiện lọc.
- Dùng `Pageable`/`Sort` để điều khiển phân trang và thứ tự thay vì tự đặt `orderBy` trong specification.
- Tránh đặt fetch join collection trong specification được dùng cho `Page<T>`.
- Nếu cần tải quan hệ, cân nhắc `@EntityGraph`, projection, query riêng hoặc custom repository.
- Nếu buộc phải dùng distinct/join/subquery, kiểm thử cả query nội dung lẫn count query.

Trong Spring Data JPA, các overload `findAll(spec, pageable)` có thể phát sinh truy vấn count. Đừng chỉ kiểm tra danh sách content rồi kết luận pagination đúng; cần kiểm tra cả tổng số và các trang cuối.

## 11. Kiểm thử Specification

Test dưới đây kiểm tra composition và phân trang thông qua repository. Nó giả định project có entity, enum, filter, specifications và repository như các ví dụ trên, cùng `spring-boot-starter-test`, `spring-boot-starter-data-jpa` và database test như H2.

```java
package com.example.learning.customer;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class CustomerSpecificationTest {
    @Autowired
    private CustomerRepository customers;

    @Test
    void combinesOptionalFiltersAndPaginatesResults() {
        customers.saveAll(List.of(
            new Customer("An", "an@example.test", true, CustomerStatus.ACTIVE),
            new Customer("Lan", "lan@example.test", false, CustomerStatus.NEW),
            new Customer("Binh", "binh@example.test", true, CustomerStatus.SUSPENDED)
        ));
        customers.flush();

        CustomerFilter filter = new CustomerFilter("an", null, true, null);
        Page<Customer> page = customers.findAll(
            CustomerSpecifications.from(filter),
            PageRequest.of(0, 10, Sort.by("id").ascending())
        );

        assertThat(page.getContent())
            .extracting(Customer::getFirstName)
            .containsExactly("An");
        assertThat(page.getTotalElements()).isEqualTo(1);
        assertThat(page.getTotalPages()).isEqualTo(1);
    }
}
```

Test lưu ba customer: `An` và `Binh` active, `Lan` inactive. Filter yêu cầu tên chứa `an` và `active = true`; chỉ `An` thỏa cả hai điều kiện. `flush()` buộc dữ liệu được gửi xuống database trước khi repository thực thi truy vấn.

Test này kiểm tra predicate, composition và metadata phân trang cơ bản. Với specification có join, subquery hoặc distinct, bổ sung fixture có nhiều order cho cùng customer và xác nhận không bị duplicate cũng như `totalElements` chính xác.

## 12. Static metamodel và an toàn khi refactor

Trong các ví dụ trên, `root.get("firstName")` dùng tên property dạng chuỗi. Cách này dễ đọc nhưng compiler không phát hiện lỗi nếu property bị đổi tên.

JPA static metamodel cho phép tham chiếu thuộc tính có kiểu, ví dụ:

```java
root.get(Customer_.firstName)
```

`Customer_` là lớp metamodel được sinh bởi annotation processor tương thích với JPA provider. Khi dự án cấu hình metamodel generator, IDE/compiler có thể phát hiện lỗi tên thuộc tính sớm hơn. Nếu chưa cấu hình generator, dùng string path có kiểm soát và bảo đảm test bao phủ các specification.

Static metamodel hữu ích trong codebase có nhiều specification hoặc entity thường xuyên refactor. Không cần thêm nó chỉ cho một vài predicate đơn giản nếu chi phí cấu hình lớn hơn lợi ích.

## 13. Các lỗi thường gặp

- **Nhầm Specification là truy vấn đã thực thi.** Specification chỉ tạo predicate; executor mới gửi truy vấn tới database.
- **Quên repository kế thừa `JpaSpecificationExecutor<T>`.** Khi thiếu interface này, không có `findAll(spec, pageable)`.
- **Dùng `null` request vừa để bỏ qua filter vừa để tìm cột NULL.** Hai ý nghĩa cần biểu diễn riêng.
- **Ghép điều kiện bằng chuỗi SQL.** Dùng CriteriaBuilder để tạo predicate và bind giá trị an toàn.
- **Hiểu sai thứ tự `and`/`or`.** `A.and(B).or(C)` là `(A AND B) OR C`; dùng biến trung gian hoặc ngoặc rõ ràng.
- **Join collection mà không xử lý duplicate.** Kiểm tra `distinct`, cardinality và count query.
- **Đặt fetch join trong specification phân trang.** Count query có thể lỗi hoặc trả kết quả không đúng; cân nhắc EntityGraph hoặc query riêng.
- **Đặt sort trong specification.** Dùng `Sort`/`Pageable` để giữ predicate độc lập với thứ tự hiển thị.
- **Chỉ test content, không test totalElements.** Join và distinct có thể làm count sai.
- **Dùng property path sai tên.** JPQL/Criteria dùng tên property Java; static metamodel giúp refactor an toàn hơn.
- **Tạo một specification khổng lồ chứa mọi điều kiện.** Chia thành factory method nhỏ để tái sử dụng và kiểm thử.

## 14. Quy trình xây dựng bộ lọc động

1. Xác định trường nào là tùy chọn và ý nghĩa chính xác của giá trị null/rỗng.
2. Tạo một factory method `Specification<T>` cho mỗi điều kiện độc lập.
3. Dùng `CriteriaBuilder` để tạo predicate, không ghép SQL từ input.
4. Kết hợp điều kiện bằng `and`, `or`, `not` theo logic nghiệp vụ.
5. Cho repository kế thừa `JpaSpecificationExecutor<T>` và gọi overload phù hợp.
6. Dùng `Pageable`/`Sort` cho phân trang và thứ tự.
7. Nếu có join, subquery hoặc distinct, kiểm tra cả content và count query.
8. Kiểm thử trường hợp không có filter, một filter, nhiều filter, null, kết quả rỗng và quan hệ có nhiều bản ghi.
9. Xem SQL/execution plan và thêm index khi có bằng chứng về nút thắt.

## Kết luận

`Specification<T>` là hợp đồng mô tả một predicate thông qua `Root`, `CriteriaQuery` và `CriteriaBuilder`; nó không tự thực thi truy vấn. `JpaSpecificationExecutor<T>` cung cấp các phương thức `findAll`, `findOne`, `count`, `exists` và phân trang để chạy specification. Hãy viết điều kiện nhỏ, kết hợp rõ ràng, định nghĩa riêng ý nghĩa của filter null, giữ specification tập trung vào predicate và kiểm thử cả dữ liệu lẫn count query khi có join. Cách tổ chức này giúp bộ lọc động dễ tái sử dụng, mở rộng và kiểm soát.