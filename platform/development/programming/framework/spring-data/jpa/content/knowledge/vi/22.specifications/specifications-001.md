# Vì sao cần Specification cho bộ lọc kết hợp động

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích Query by Example (QBE) phù hợp với loại tìm kiếm nào và giới hạn ở đâu.
- Nhận biết khi nào bộ lọc động cần biểu thức AND/OR, khoảng giá trị, IS NULL, IN, join hoặc subquery.
- Dùng Spring Data JPA Specification để xây dựng các predicate độc lập và kết hợp chúng.
- Thiết kế filter object phân biệt không lọc, lọc null và lọc theo giá trị.
- Kết hợp Specification với JpaSpecificationExecutor, phân trang và sắp xếp.
- Tránh duplicate row, count sai, fetch join không phù hợp và điều kiện lọc do client tự kiểm soát.
- Kiểm thử các tổ hợp filter và chọn đúng công cụ giữa QBE, Specification và @Query.

## 1. Bài toán bộ lọc kết hợp động

Một màn hình tìm kiếm khách hàng có thể cho phép người dùng nhập nhiều điều kiện:

- Tên chứa một đoạn văn bản.
- Email bằng một giá trị hoặc email đang null.
- Trạng thái thuộc một enum.
- Ngày tạo nằm trong một khoảng.
- Chỉ lấy khách hàng đang bật hoặc tắt.
- Có ít nhất một đơn hàng đã thanh toán.

Mỗi điều kiện có thể được cung cấp hoặc bỏ qua độc lập. Người dùng có thể chỉ lọc theo tên, hoặc kết hợp tên với trạng thái, ngày tạo và sự tồn tại của đơn hàng.

Nếu có sáu filter độc lập, số tổ hợp đầu vào đã rất lớn. Viết một repository method cho mỗi tổ hợp sẽ tạo ra nhiều method gần giống nhau:

~~~java
findByNameContaining(...);
findByStatus(...);
findByNameContainingAndStatus(...);
findByStatusAndCreatedAtBetween(...);
findByNameContainingAndStatusAndEnabled(...);
// Còn nhiều tổ hợp khác...
~~~

Một cách khác là viết một câu JPQL dài với nhiều điều kiện kiểu:

~~~jpql
where (:name is null or lower(c.name) like ...)
  and (:status is null or c.status = :status)
  and (:enabled is null or c.enabled = :enabled)
~~~

Cách này phù hợp với bộ lọc đơn giản, nhưng nhanh chóng khó đọc khi có nhóm OR, điều kiện null tường minh, khoảng ngày tùy chọn, join, subquery hoặc logic chỉ áp dụng khi một nhóm filter được bật.

Spring Data JPA Specification giải quyết bài toán bằng cách biểu diễn từng điều kiện thành một predicate có thể tái sử dụng, sau đó kết hợp các predicate theo nhu cầu của request.

## 2. Query by Example phù hợp với điều gì?

Query by Example (QBE) dùng một object làm probe. Các thuộc tính có giá trị trong probe được so khớp theo một ExampleMatcher.

Ví dụ, giả sử entity Customer có các thuộc tính name, email và status. Có thể tạo probe:

~~~java
Customer probe = new Customer(
    "an",
    null,
    CustomerStatus.ACTIVE,
    null,
    null
);

ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withIgnoreNullValues()
    .withMatcher("name", rule -> rule.contains().ignoreCase());

Example<Customer> example = Example.of(probe, matcher);

List<Customer> customers = repository.findAll(example);
~~~

Đoạn code giả định Customer có constructor nhận lần lượt name, email, status, createdAt và enabled như entity minh họa ở phần sau.

QBE phù hợp khi:

- Điều kiện chủ yếu là so khớp giá trị của các thuộc tính.
- Null trong probe có nghĩa là bỏ qua thuộc tính đó.
- Logic là AND giữa các thuộc tính, hoặc OR đơn giản bằng matchingAny().
- Tìm chuỗi theo exact, starts with, ends with hoặc contains.
- Không cần biểu thức nghiệp vụ phức tạp hay subquery.

### QBE có hỗ trợ OR không?

Có. matchingAny() yêu cầu khớp bất kỳ thuộc tính probe nào. Tuy nhiên, đây là OR đơn giản giữa các thuộc tính được khai báo trong probe; nó không biểu diễn tự do các nhóm lồng nhau như:

~~~text
(status = ACTIVE AND enabled = true)
OR
(status = VIP AND createdAt >= from)
~~~

Đây là khác biệt quan trọng: QBE có thể xử lý một số điều kiện OR cơ bản, nhưng không phải một bộ dựng biểu thức logic tổng quát.

## 3. Khi nào QBE không còn đủ?

QBE có những giới hạn khiến nó không phù hợp với nhiều màn hình tìm kiếm nghiệp vụ:

- Không biểu diễn trực tiếp các phép so sánh lớn hơn, nhỏ hơn hoặc khoảng BETWEEN theo cách tổng quát.
- Không biểu diễn nhóm AND/OR tùy ý với ngoặc logic.
- Không cung cấp cách tổng quát để tạo join và subquery theo ý muốn.
- Không phù hợp với các điều kiện cần hàm database, phép tính hoặc biểu thức Criteria phức tạp.
- Không hỗ trợ matching collection và map theo kiểu probe thông thường.
- Khó thể hiện rõ sự khác nhau giữa filter không được gửi và filter được gửi với giá trị null nếu chỉ dùng một thuộc tính nullable.

Ví dụ, yêu cầu sau cần nhiều loại predicate:

~~~text
name contains "an"
AND status IN (ACTIVE, VIP)
AND createdAt >= 2026-01-01
AND (enabled = true OR status = VIP)
AND EXISTS (một đơn hàng PAID)
~~~

Đây không còn là so khớp các field đơn giản trong một probe. Specification phù hợp hơn vì nó cho phép dùng Criteria API để tạo like, in, greaterThanOrEqualTo, or, exists và các phép nối.

## 4. Specification là gì?

Specification<T> là một abstraction của Spring Data JPA dùng để mô tả điều kiện truy vấn cho entity T. Nó dựa trên JPA Criteria API và thường trả về một Predicate.

Một Specification có ba thành phần đầu vào:

- Root<T>: entity gốc đang được truy vấn.
- CriteriaQuery<?>: đối tượng truy vấn, có thể dùng cho subquery hoặc điều chỉnh distinct.
- CriteriaBuilder: công cụ tạo predicate và biểu thức như equal, like, between, isNull, and, or.

Ví dụ nhỏ:

~~~java
Specification<Customer> activeCustomers =
    (root, query, cb) -> cb.isTrue(root.get("enabled"));
~~~

Specification này mô tả điều kiện enabled = true. Nó chưa chạy query. Repository sẽ kết hợp Specification với các điều kiện khác rồi tạo SQL khi thực thi.

### Specification có thể kết hợp

Spring Data cung cấp các phép kết hợp:

- and(other): cả hai điều kiện phải đúng.
- or(other): ít nhất một điều kiện đúng.
- not(spec): phủ định một Specification.

Ví dụ:

~~~java
Specification<Customer> spec =
    activeCustomers.and(hasStatus(CustomerStatus.ACTIVE));
~~~

Các predicate nhỏ có thể được đặt trong những method riêng, đặt tên theo nghiệp vụ và tái sử dụng ở nhiều use case.

## 5. Khai báo entity và filter object

Ví dụ dưới đây dùng Java 17+, Spring Data JPA và Jakarta Persistence. Entity Customer có các field phục vụ tìm kiếm.

~~~java
package com.example.customer;

import java.time.LocalDateTime;

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

    @Column(nullable = false, length = 120)
    private String name;

    @Column(length = 254)
    private String email;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private CustomerStatus status;

    @Column(nullable = false)
    private LocalDateTime createdAt;

    @Column(nullable = false)
    private Boolean enabled;

    protected Customer() {
    }

    public Customer(
            String name,
            String email,
            CustomerStatus status,
            LocalDateTime createdAt,
            Boolean enabled) {
        this.name = name;
        this.email = email;
        this.status = status;
        this.createdAt = createdAt;
        this.enabled = enabled;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }

    public CustomerStatus getStatus() {
        return status;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public Boolean getEnabled() {
        return enabled;
    }
}
~~~

Enum:

~~~java
package com.example.customer;

public enum CustomerStatus {
    ACTIVE,
    INACTIVE,
    VIP
}
~~~

Filter object:

~~~java
package com.example.customer;

import java.time.LocalDateTime;

public record CustomerFilter(
        String name,
        CustomerStatus status,
        LocalDateTime createdFrom,
        LocalDateTime createdTo,
        Boolean enabled,
        String email,
        boolean emailIsNull) {

    public CustomerFilter {
        if (emailIsNull && email != null) {
            throw new IllegalArgumentException(
                "email and emailIsNull cannot both be set"
            );
        }

        if (email != null && email.isBlank()) {
            throw new IllegalArgumentException(
                "email must not be blank"
            );
        }

        if (createdFrom != null
                && createdTo != null
                && createdFrom.isAfter(createdTo)) {
            throw new IllegalArgumentException(
                "createdFrom must not be after createdTo"
            );
        }
    }
}
~~~

Trong filter này:

- null ở name, status, createdFrom, createdTo hoặc enabled nghĩa là bỏ qua điều kiện tương ứng.
- enabled = false vẫn là một filter hợp lệ; vì dùng Boolean, null và false được phân biệt.
- email = null cùng emailIsNull = false nghĩa là bỏ qua email.
- email = null cùng emailIsNull = true nghĩa là tìm email IS NULL.
- email có giá trị nghĩa là tìm bằng giá trị đó.

Một filter object tốt làm rõ semantics đầu vào trước khi xây dựng query. Không để Specification phải tự đoán null có nghĩa là bỏ qua hay tìm cột null.

## 6. Viết các Specification nhỏ

Tạo lớp chứa các predicate có thể tái sử dụng:

~~~java
package com.example.customer;

import java.time.LocalDateTime;
import java.util.Locale;

import org.springframework.data.jpa.domain.Specification;

public final class CustomerSpecifications {

    private CustomerSpecifications() {
    }

    public static Specification<Customer> unrestricted() {
        return (root, query, cb) -> cb.conjunction();
    }

    public static Specification<Customer> nameContains(String name) {
        if (name == null || name.isBlank()) {
            return unrestricted();
        }

        String pattern = "%"
            + name.trim().toLowerCase(Locale.ROOT)
            + "%";

        return (root, query, cb) ->
            cb.like(cb.lower(root.<String>get("name")), pattern);
    }

    public static Specification<Customer> hasStatus(
            CustomerStatus status) {
        if (status == null) {
            return unrestricted();
        }

        return (root, query, cb) ->
            cb.equal(root.get("status"), status);
    }

    public static Specification<Customer> enabled(Boolean enabled) {
        if (enabled == null) {
            return unrestricted();
        }

        return (root, query, cb) ->
            cb.equal(root.<Boolean>get("enabled"), enabled);
    }

    public static Specification<Customer> createdFrom(
            LocalDateTime from) {
        if (from == null) {
            return unrestricted();
        }

        return (root, query, cb) ->
            cb.greaterThanOrEqualTo(
                root.<LocalDateTime>get("createdAt"),
                from
            );
    }

    public static Specification<Customer> createdTo(
            LocalDateTime to) {
        if (to == null) {
            return unrestricted();
        }

        return (root, query, cb) ->
            cb.lessThanOrEqualTo(
                root.<LocalDateTime>get("createdAt"),
                to
            );
    }

    public static Specification<Customer> emailMatches(
            String email,
            boolean emailIsNull) {
        if (emailIsNull) {
            return (root, query, cb) ->
                cb.isNull(root.get("email"));
        }

        if (email == null) {
            return unrestricted();
        }

        String normalized = email.trim().toLowerCase(Locale.ROOT);

        return (root, query, cb) ->
            cb.equal(
                cb.lower(root.<String>get("email")),
                normalized
            );
    }
}
~~~

Các điểm cần hiểu:

- unrestricted() trả về predicate luôn đúng bằng cb.conjunction(). Khi kết hợp bằng AND, điều kiện này không giới hạn kết quả.
- Mỗi method xử lý trường hợp filter không được cung cấp.
- enabled(Boolean) không dùng if (!enabled), vì cách đó sẽ bỏ qua cả giá trị false.
- Khoảng thời gian được tách thành hai predicate để hỗ trợ chỉ có cận dưới, chỉ có cận trên hoặc cả hai.
- emailMatches() phân biệt rõ bỏ qua filter, tìm null và tìm giá trị.

Trong ví dụ name contains, ký tự % và _ do người dùng nhập sẽ được hiểu như wildcard LIKE. Nếu nghiệp vụ yêu cầu tìm chúng như ký tự thường, hãy escape pattern bằng escape character của Criteria API hoặc chuẩn hóa input theo quy tắc đã công bố.

Việc dùng root.get("name") dựa trên tên property dạng String. Với dự án lớn, có thể dùng JPA static metamodel (ví dụ Customer_.name) để phát hiện lỗi đổi tên property ngay khi compile.

## 7. Kết hợp filter trong service

Repository cần mở rộng JpaSpecificationExecutor:

~~~java
package com.example.customer;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                JpaSpecificationExecutor<Customer> {
}
~~~

Service ghép các Specification:

~~~java
package com.example.customer;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerSearchService {

    private final CustomerRepository repository;

    public CustomerSearchService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public Page<Customer> search(
            CustomerFilter filter,
            Pageable pageable) {

        Specification<Customer> spec =
            CustomerSpecifications.unrestricted()
                .and(CustomerSpecifications.nameContains(filter.name()))
                .and(CustomerSpecifications.hasStatus(filter.status()))
                .and(CustomerSpecifications.createdFrom(filter.createdFrom()))
                .and(CustomerSpecifications.createdTo(filter.createdTo()))
                .and(CustomerSpecifications.enabled(filter.enabled()))
                .and(CustomerSpecifications.emailMatches(
                    filter.email(),
                    filter.emailIsNull()
                ));

        return repository.findAll(spec, pageable);
    }
}
~~~

Repository sẽ tạo query từ Specification cuối cùng. Service không cần viết một method riêng cho từng tổ hợp filter.

Ví dụ gọi:

~~~java
CustomerFilter filter = new CustomerFilter(
    "an",
    CustomerStatus.ACTIVE,
    LocalDateTime.of(2026, 1, 1, 0, 0),
    null,
    true,
    null,
    false
);

Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.asc("name"),
        Sort.Order.asc("id")
    )
);

Page<Customer> result = searchService.search(filter, pageable);
~~~

Ví dụ này tìm khách hàng có tên chứa “an”, status ACTIVE, được bật và tạo từ ngày 1/1/2026; không giới hạn cận trên hoặc email. Sort theo name rồi id để thứ tự phân trang ổn định.

Page<T> thường cần count query để tính tổng số phần tử. Nếu giao diện chỉ cần biết còn kết quả tiếp theo mà không cần tổng số, cân nhắc một thiết kế Slice hoặc query theo cửa sổ phù hợp với API/version đang dùng.

## 8. Biểu diễn nhóm OR có ngoặc logic

Một lợi thế lớn của Specification là có thể tạo nhóm predicate rồi kết hợp nhóm đó với điều kiện khác.

Giả sử yêu cầu:

~~~text
(name contains "an")
AND
(status = ACTIVE OR status = VIP)
AND
(enabled = true)
~~~

Tạo nhóm OR:

~~~java
public static Specification<Customer> activeOrVip() {
    return (root, query, cb) ->
        cb.or(
            cb.equal(root.get("status"), CustomerStatus.ACTIVE),
            cb.equal(root.get("status"), CustomerStatus.VIP)
        );
}
~~~

Kết hợp:

~~~java
Specification<Customer> spec =
    CustomerSpecifications.nameContains("an")
        .and(CustomerSpecifications.activeOrVip())
        .and(CustomerSpecifications.enabled(true));
~~~

Kết quả tương đương:

~~~sql
WHERE lower(name) LIKE '%an%'
  AND (status = 'ACTIVE' OR status = 'VIP')
  AND enabled = true
~~~

Nhóm OR nằm trong một predicate riêng, nên khi ghép bằng AND, dấu ngoặc logic được giữ đúng. Đây là điểm QBE không thể diễn đạt linh hoạt bằng một probe đơn giản.

## 9. IN, NOT IN và danh sách filter

Specification có thể biểu diễn điều kiện thuộc một tập giá trị:

~~~java
public static Specification<Customer> statusIn(
        Collection<CustomerStatus> statuses) {
    if (statuses == null) {
        return unrestricted();
    }

    if (statuses.isEmpty()) {
        return (root, query, cb) -> cb.disjunction();
    }

    return (root, query, cb) ->
        root.get("status").in(statuses);
}
~~~

Ví dụ này quy định:

- null collection: không áp dụng filter.
- Collection rỗng: không có bản ghi nào phù hợp.
- Collection có giá trị: chỉ lấy status nằm trong tập.

Không mặc định collection rỗng nghĩa là bỏ qua filter. Hai semantics đó khác nhau và cần được API contract xác định rõ.

Có thể tạo notIn tương tự. Nếu collection chứa null, SQL ba giá trị có thể làm NOT IN cho kết quả khó hiểu; nên validate và loại null khỏi danh sách trước khi tạo predicate.

## 10. Join và subquery

Specification dựa trên Criteria API nên có thể nối association hoặc tạo subquery.

Giả sử entity PurchaseOrder có thuộc tính customer là ManyToOne và status là OrderStatus. Để tìm Customer có ít nhất một đơn PAID, có thể dùng EXISTS:

~~~java
public static Specification<Customer> hasPaidOrder() {
    return (root, query, cb) -> {
        Subquery<Long> subquery = query.subquery(Long.class);
        Root<PurchaseOrder> order =
            subquery.from(PurchaseOrder.class);

        subquery.select(order.<Long>get("id"));
        subquery.where(
            cb.equal(order.get("customer"), root),
            cb.equal(order.get("status"), OrderStatus.PAID)
        );

        return cb.exists(subquery);
    };
}
~~~

Đây là fragment phụ thuộc vào entity PurchaseOrder và enum OrderStatus của ứng dụng. Subquery EXISTS diễn đạt đúng ý “có ít nhất một đơn PAID” mà không nhân số dòng Customer theo số đơn hàng.

Nếu dùng join collection:

~~~java
Join<Customer, PurchaseOrder> orders =
    root.join("orders", JoinType.INNER);

query.distinct(true);

return cb.equal(orders.get("status"), OrderStatus.PAID);
~~~

Join collection có thể tạo nhiều dòng SQL cho cùng Customer. Khi kết quả cần mỗi Customer một lần, phải xử lý duplicate bằng distinct hoặc cân nhắc EXISTS.

Đối với truy vấn phân trang, join collection có thể làm count query phức tạp. Hãy kiểm tra SQL và tổng số kết quả, không chỉ kiểm tra danh sách content.

## 11. Specification và phân trang, sắp xếp

JpaSpecificationExecutor cung cấp các phương thức phổ biến:

- findAll(spec): lấy tất cả entity thỏa điều kiện.
- findAll(spec, sort): lấy kết quả có sắp xếp.
- findAll(spec, pageable): lấy một Page.
- count(spec): đếm entity thỏa điều kiện.
- exists(spec): kiểm tra có entity phù hợp.
- findOne(spec): lấy tối đa một entity; nếu nhiều kết quả, thao tác có thể báo lỗi cardinality.

Ví dụ:

~~~java
Page<Customer> page =
    repository.findAll(
        spec,
        PageRequest.of(
            0,
            20,
            Sort.by(
                Sort.Order.asc("createdAt"),
                Sort.Order.asc("id")
            )
        )
    );
~~~

Thêm khóa duy nhất như id vào cuối sort giúp thứ tự ổn định khi nhiều bản ghi có cùng createdAt. Với dữ liệu thay đổi liên tục, offset pagination vẫn có thể dịch chuyển giữa các request; nếu cần duyệt sâu tuần tự, cân nhắc keyset scrolling ở phiên bản Spring Data hỗ trợ.

## 12. Không trộn fetch join tùy tiện vào Specification

Specification thường được tái sử dụng cho cả query lấy dữ liệu và count query của Page. Vì vậy, việc gọi root.fetch(...) bên trong một Specification dùng chung có thể gây vấn đề khi Spring Data tạo count query, vì count query không cần fetch association.

Một số lưu ý:

- Không thêm fetch join collection vào mọi Specification chỉ để tránh lazy loading.
- Tách predicate lọc khỏi chiến lược fetch dữ liệu khi có thể.
- Dùng @EntityGraph trên repository method hoặc một query chuyên biệt khi cần tải association.
- Nếu dùng join collection để lọc, xem xét EXISTS để tránh nhân dòng.
- Kiểm tra count query khi kết hợp distinct, group hoặc join.

Specification nên mô tả điều kiện lọc có thể tái sử dụng. Fetch plan là quyết định riêng của use case đọc.

## 13. QBE, Specification và @Query: chọn công cụ nào?

| Nhu cầu | Công cụ phù hợp | Lý do |
|---|---|---|
| So khớp nhiều field không null theo AND | QBE | Ít code, probe và matcher dễ hiểu |
| OR đơn giản giữa các field probe | QBE matchingAny | Hỗ trợ any-match cơ bản |
| Filter tùy chọn có khoảng ngày, lớn hơn/nhỏ hơn, IN | Specification | Criteria API có toán tử phù hợp |
| Nhóm AND/OR lồng nhau | Specification | Có thể ghép predicate theo ngoặc logic |
| Join, EXISTS, subquery theo điều kiện | Specification | Có thể truy cập association và Criteria subquery |
| Một truy vấn cố định, phức tạp nhưng ổn định | @Query | JPQL/SQL được viết tường minh |
| SQL đặc thù database hoặc CTE/window function | Native @Query/custom repository | Kiểm soát cú pháp SQL trực tiếp |
| Truy vấn động rất phức tạp và cần type-safe DSL | Querydsl hoặc custom Criteria | DSL phù hợp cho biểu thức lớn |

Không phải mọi truy vấn động đều cần Specification. Nếu QBE đã biểu diễn đúng nghiệp vụ và dễ đọc, hãy giữ QBE. Nếu query cố định và có tên rõ ràng, @Query có thể đơn giản hơn. Specification có giá trị khi cần ghép nhiều predicate tùy chọn theo logic nghiệp vụ.

## 14. Kiểm thử Specification

Nên kiểm thử cả từng predicate quan trọng và các tổ hợp thực tế qua repository với database test.

Ví dụ integration test:

~~~java
package com.example.customer;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.LocalDateTime;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.domain.Specification;

@DataJpaTest
class CustomerSpecificationTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void combinesNameStatusAndEnabledFilters() {
        repository.saveAll(List.of(
            new Customer(
                "An Nguyen",
                "an@example.com",
                CustomerStatus.ACTIVE,
                LocalDateTime.of(2026, 2, 1, 10, 0),
                true
            ),
            new Customer(
                "An Tran",
                "an2@example.com",
                CustomerStatus.INACTIVE,
                LocalDateTime.of(2026, 2, 2, 10, 0),
                true
            ),
            new Customer(
                "Binh Le",
                null,
                CustomerStatus.ACTIVE,
                LocalDateTime.of(2026, 2, 3, 10, 0),
                false
            )
        ));
        repository.flush();

        Specification<Customer> spec =
            CustomerSpecifications.nameContains("an")
                .and(CustomerSpecifications.hasStatus(
                    CustomerStatus.ACTIVE
                ))
                .and(CustomerSpecifications.enabled(true));

        List<Customer> result = repository.findAll(
            spec,
            Sort.by(Sort.Order.asc("id"))
        );

        assertEquals(1, result.size());
        assertEquals("An Nguyen", result.get(0).getName());
    }
}
~~~

Test giả định các lớp Customer, CustomerStatus, CustomerSpecifications và CustomerRepository đã được khai báo như các phần trước, cùng với test database tương thích. DataJpaTest thường chạy trong transaction test và rollback sau mỗi test.

Nên bổ sung test cho:

- Không có filter nào: trả về tất cả bản ghi phù hợp với quyền truy cập.
- Boolean false: vẫn tạo predicate và chỉ trả về bản ghi false.
- Cận dưới/cận trên riêng lẻ và cả hai cận.
- Email IS NULL và email bằng giá trị.
- Collection IN rỗng và collection có giá trị.
- Nhóm OR có ngoặc logic.
- EXISTS với không có đơn, đơn PENDING và đơn PAID.
- Phân trang, count query và sort có giá trị trùng.

## 15. Bảo mật và kiểm soát filter

Không nhận tên property hoặc fragment Criteria/SQL tùy ý từ client rồi truyền thẳng vào query.

Ví dụ, nếu API nhận sortBy=name, hãy ánh xạ qua whitelist:

~~~java
Sort sort = switch (sortBy) {
    case "name" -> Sort.by("name").ascending();
    case "createdAt" -> Sort.by("createdAt").descending();
    default -> Sort.by("id").ascending();
};
~~~

Tương tự, chỉ cho phép những filter mà use case công bố. Không để client tự chọn field nội bộ như role, tenantId, approvalState hoặc audit fields nếu họ không có quyền thay đổi phạm vi truy vấn.

Specification cũng không thay thế authorization. Điều kiện tenant, ownership hoặc quyền truy cập cần được áp dụng bắt buộc ở service/security layer để mọi request đều bị giới hạn đúng phạm vi.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Một filter false bị bỏ qua | Dùng kiểm tra boolean thay vì kiểm tra null | Dùng Boolean và chỉ bỏ qua khi null |
| Không phân biệt bỏ qua filter và IS NULL | Dùng một nullable parameter cho hai ý nghĩa | Dùng cờ presence hoặc tri-state filter |
| QBE không biểu diễn được khoảng ngày | QBE tập trung vào matching probe, không phải toán tử quan hệ tổng quát | Dùng Specification |
| QBE OR trả kết quả quá rộng | matchingAny áp dụng OR đơn giản trên các probe property | Dùng nhóm predicate Specification |
| Query trả Customer trùng | Join collection tạo nhiều dòng | Dùng EXISTS hoặc distinct có chủ đích |
| Page total không đúng | Count query đếm dòng join thay vì entity gốc | Kiểm tra count semantics, dùng EXISTS/count distinct |
| Count query lỗi sau khi thêm fetch | Specification dùng fetch join cả trong count query | Tách fetch plan khỏi predicate |
| LIKE coi % là wildcard | Không escape ký tự pattern do người dùng nhập | Escape pattern nếu cần tìm literal |
| Specification khó bảo trì | Một method chứa toàn bộ logic lọc | Tách predicate theo thuộc tính/nghiệp vụ |
| Client tự lọc field nội bộ | Nhận property name hoặc sort trực tiếp không whitelist | Ánh xạ input qua danh sách cho phép |
| Test chỉ kiểm tra một tổ hợp | Chưa bao phủ trạng thái null, false, rỗng và OR | Viết test theo từng trạng thái và tổ hợp quan trọng |

## Quy trình lựa chọn

1. Xác định filter có phải chỉ là so khớp field đơn giản hay có toán tử và nhóm logic phức tạp.
2. Dùng QBE khi probe và matcher đã diễn đạt chính xác yêu cầu.
3. Dùng Specification khi cần predicate tùy chọn, range, IN, null, nhóm AND/OR, join hoặc subquery.
4. Dùng @Query cho truy vấn cố định mà JPQL/SQL viết tường minh dễ hiểu hơn.
5. Định nghĩa semantics của null, false, chuỗi rỗng và collection rỗng ở filter object.
6. Ghép predicate nhỏ theo service/use case thay vì tạo một Specification khổng lồ.
7. Kiểm tra duplicate row, count query, fetch plan và index.
8. Whitelist sort/filter và bảo đảm authorization được áp dụng.
9. Integration test các tổ hợp filter đại diện và các trường hợp biên.

## Checklist trước khi merge

- [ ] QBE đã được cân nhắc và chỉ dùng khi matching semantics đáp ứng đủ yêu cầu.
- [ ] Specification chỉ thêm predicate khi filter tương ứng được cung cấp.
- [ ] Boolean false không bị nhầm với filter vắng mặt.
- [ ] Null filter có semantics rõ ràng: bỏ qua hay IS NULL.
- [ ] Predicate AND/OR có grouping đúng.
- [ ] Range, IN, join và EXISTS được dùng đúng mục đích.
- [ ] Join collection không làm nhân bản entity hoặc sai count.
- [ ] Fetch plan không bị trộn tùy tiện vào Specification dùng cho Page.
- [ ] Sort/filter đầu vào được whitelist.
- [ ] Authorization/tenant scope luôn được áp dụng.
- [ ] Integration test bao phủ filter rỗng, false, null, range, OR và phân trang.

## Kết luận

Query by Example phù hợp với tìm kiếm dựa trên probe và các matcher đơn giản. Khi bộ lọc cần khoảng giá trị, IN, null tường minh, nhóm AND/OR lồng nhau, join hoặc subquery, Specification cung cấp Criteria API để xây dựng predicate độc lập rồi kết hợp theo use case. Filter object phải định nghĩa rõ ý nghĩa của null, false và collection rỗng. Hãy giữ predicate nhỏ, tách fetch plan khỏi điều kiện lọc, kiểm tra count query và giới hạn field client được phép truy vấn. Điều đó giúp màn hình tìm kiếm động dễ mở rộng mà vẫn giữ được logic rõ ràng và có thể kiểm thử.
