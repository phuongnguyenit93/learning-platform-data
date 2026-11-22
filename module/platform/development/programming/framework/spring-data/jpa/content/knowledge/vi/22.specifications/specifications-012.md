# Kiểm thử bộ Specification tái sử dụng

## Mục tiêu

Spring Data JPA Specification cho phép tách các điều kiện truy vấn thành những predicate nhỏ, có thể kết hợp và dùng lại giữa nhiều repository method hoặc use case. Nhưng một Specification chỉ thực sự đáng tin khi được kiểm thử với mapping JPA và database: điều kiện có thể đúng về cú pháp Java nhưng tạo SQL sai, JOIN làm nhân bản hàng, hoặc count query cho kết quả khác với query nội dung.

Bài này tập trung vào cách thiết kế Specification có thể tái sử dụng và cách kiểm thử chúng bằng repository integration test. Ta sẽ kiểm tra từng điều kiện, cách kết hợp AND/OR, filter tùy chọn, phân trang/count, association JOIN và các tình huống biên.

Sau bài này, bạn có thể:

- Hiểu cấu trúc và vòng đời của `Specification<T>`.
- Viết các Specification nhỏ, độc lập và không giữ trạng thái.
- Kết hợp điều kiện bằng `and`, `or` và `not`.
- Kiểm thử predicate qua `JpaSpecificationExecutor`.
- Kiểm tra filter tùy chọn, null, chuỗi rỗng và ngày tháng.
- Phát hiện lỗi JOIN, DISTINCT, phân trang và count query.
- Chọn giữa unit test và integration test với JPA provider thật.
- Tổ chức bộ test để Specification được dùng lại an toàn khi nghiệp vụ phát triển.

Ví dụ sử dụng Java 17+, Spring Boot 3.x, Jakarta Persistence và Spring Data JPA.

## 1. Specification là gì?

`Specification<T>` là abstraction của Spring Data JPA để biểu diễn một predicate dựa trên Criteria API. Interface này có phương thức:

```java
Predicate toPredicate(
        Root<T> root,
        CriteriaQuery<?> query,
        CriteriaBuilder criteriaBuilder
);
```

Ba tham số có vai trò:

- `Root<T>`: đại diện entity đang được truy vấn; dùng để truy cập thuộc tính và association.
- `CriteriaQuery<?>`: đại diện cấu trúc query; có thể dùng cho DISTINCT, subquery hoặc các phần query khác khi thật sự cần.
- `CriteriaBuilder`: cung cấp API tạo điều kiện như equal, like, greaterThan, and, or, isNull.

Specification trả về một Predicate mô tả điều kiện WHERE. Spring Data nhận predicate đó và kết hợp vào query mà repository thực thi.

Ví dụ:

```java
public static Specification<Employee> isActive(boolean active) {
    return (root, query, cb) ->
            cb.equal(root.get("active"), active);
}
```

Đây là một Specification độc lập. Nó có thể được dùng trong danh sách, phân trang, đếm số hàng hoặc kết hợp với các Specification khác.

## 2. Bật khả năng chạy Specification trên repository

Repository cần kế thừa `JpaSpecificationExecutor<T>`:

```java
public interface EmployeeRepository
        extends JpaRepository<Employee, Long>,
                JpaSpecificationExecutor<Employee> {
}
```

Các method thường dùng:

```java
repository.findAll(specification);
repository.findAll(specification, sort);
repository.findAll(specification, pageable);
repository.findOne(specification);
repository.count(specification);
repository.exists(specification);
```

`JpaSpecificationExecutor` thực thi Specification trên entity domain type. Repository không cần tự viết một method cho từng tổ hợp filter.

Nếu cần trả DTO projection, custom query hoặc fetch plan phức tạp, có thể kết hợp Specification với custom repository hoặc API khác. Không nên ép mọi kiểu truy vấn vào một Specification chung.

## 3. Entity mẫu dùng trong bài kiểm thử

Ta dùng Employee với ba thuộc tính có thể lọc: fullName, active và createdAt.

```java
package com.example.demo.employee;

import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(name = "employees")
public class Employee {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String fullName;

    @Column(nullable = false)
    private boolean active;

    @Column(nullable = false)
    private Instant createdAt;

    protected Employee() {
    }

    public Employee(String fullName, boolean active, Instant createdAt) {
        this.fullName = fullName;
        this.active = active;
        this.createdAt = createdAt;
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public boolean isActive() {
        return active;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
```

Repository:

```java
package com.example.demo.employee;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

public interface EmployeeRepository
        extends JpaRepository<Employee, Long>,
                JpaSpecificationExecutor<Employee> {
}
```

Entity và repository ở trên là nền tảng cho các ví dụ tiếp theo. Trong dự án thực tế, dùng đúng package, constructor và thuộc tính của domain model hiện có.

## 4. Tách Specification thành các điều kiện nhỏ

Một Specification tái sử dụng nên tập trung vào một điều kiện nghiệp vụ. Tránh tạo một Specification lớn chứa tất cả filter, sort, fetch và logic đặc thù của một màn hình.

Ví dụ:

```java
package com.example.demo.employee;

import java.time.Instant;
import java.util.Locale;

import jakarta.persistence.criteria.Path;
import org.springframework.data.jpa.domain.Specification;

public final class EmployeeSpecifications {

    private EmployeeSpecifications() {
    }

    public static Specification<Employee> isActive(Boolean active) {
        return (root, query, cb) -> {
            if (active == null) {
                return cb.conjunction();
            }
            return cb.equal(root.get("active"), active);
        };
    }

    public static Specification<Employee> fullNameContains(String keyword) {
        return (root, query, cb) -> {
            if (keyword == null || keyword.isBlank()) {
                return cb.conjunction();
            }

            String normalized = keyword.trim().toLowerCase(Locale.ROOT);
            Path<String> fullName = root.get("fullName");

            return cb.like(
                    cb.lower(fullName),
                    "%" + normalized + "%"
            );
        };
    }

    public static Specification<Employee> createdAtOnOrAfter(Instant from) {
        return (root, query, cb) -> {
            if (from == null) {
                return cb.conjunction();
            }

            Path<Instant> createdAt = root.get("createdAt");
            return cb.greaterThanOrEqualTo(createdAt, from);
        };
    }

    public static Specification<Employee> createdBefore(Instant to) {
        return (root, query, cb) -> {
            if (to == null) {
                return cb.conjunction();
            }

            Path<Instant> createdAt = root.get("createdAt");
            return cb.lessThan(createdAt, to);
        };
    }
}
```

Mỗi method trả về một Specification không giữ trạng thái. Tham số được truyền vào khi tạo Specification, còn Root/CriteriaBuilder chỉ được sử dụng khi provider thực thi predicate.

### 4.1. Vì sao nên viết các điều kiện nhỏ?

Có thể dùng lại `isActive` cho màn hình danh sách, báo cáo và API tìm kiếm. `fullNameContains` có thể kết hợp với filter khác mà không cần sao chép điều kiện.

Lợi ích:

- Mỗi điều kiện có một mục đích rõ ràng.
- Có thể kiểm thử điều kiện riêng.
- Có thể kết hợp theo nhiều use case.
- Khi quy tắc nghiệp vụ thay đổi, chỉ cần sửa một nơi.
- Tên method thể hiện ý nghĩa thay vì để lộ chi tiết Criteria API ở service.

Không nên tạo một thư viện Specification quá vụn. Tách theo điều kiện có ý nghĩa nghiệp vụ và thực sự được dùng lại.

### 4.2. Vì sao filter tùy chọn trả về conjunction?

`cb.conjunction()` tạo predicate luôn đúng, tương đương điều kiện không làm thu hẹp tập kết quả. Khi kết hợp bằng AND, predicate này không thay đổi kết quả:

```java
isActive(null).and(fullNameContains("an"))
```

Kết quả tương đương chỉ áp dụng điều kiện tìm tên. Có thể dùng `null` predicate theo quy ước của Spring Data Specification ở các version hỗ trợ, nhưng `cb.conjunction()` thể hiện rõ ý nghĩa “không lọc” và dễ hiểu khi đọc code.

Cần phân biệt “không áp dụng filter” với “tìm thuộc tính có giá trị null”. Hai trường hợp này có semantics khác nhau. Nếu nghiệp vụ cần tìm các hàng có cột null, hãy tạo Specification riêng dùng `cb.isNull(...)`.

### 4.3. Xử lý chuỗi rỗng và wildcard

Ví dụ `fullNameContains` coi null hoặc chuỗi chỉ có khoảng trắng là không áp dụng filter. Nó dùng `LIKE '%keyword%'`; ký tự `%` và `_` do người dùng nhập vẫn có ý nghĩa wildcard của LIKE.

Nếu yêu cầu là tìm chuỗi literal, cần escape wildcard và khai báo escape character:

```java
private static String escapeLike(String value) {
    return value
            .replace("!", "!!")
            .replace("%", "!%")
            .replace("_", "!_");
}
```

Sau đó truyền pattern đã escape vào overload `cb.like(expression, pattern, '!')`. Bind parameter vẫn được provider xử lý; escape wildcard là vấn đề semantics tìm kiếm, không phải thay thế cho bind parameter.

## 5. Kết hợp Specification bằng AND và OR

Các Specification có thể kết hợp bằng method của interface:

```java
Specification<Employee> specification =
        EmployeeSpecifications.isActive(true)
                .and(EmployeeSpecifications.fullNameContains("an"))
                .and(EmployeeSpecifications.createdAtOnOrAfter(
                        Instant.parse("2026-01-01T00:00:00Z")
                ));
```

Logic tương đương:

```sql
WHERE active = true
  AND lower(full_name) LIKE '%an%'
  AND created_at >= '2026-01-01T00:00:00Z'
```

Kết hợp OR:

```java
Specification<Employee> nameMatches =
        EmployeeSpecifications.fullNameContains("an")
                .or(EmployeeSpecifications.fullNameContains("binh"));
```

Có thể nhóm điều kiện rõ ràng:

```java
Specification<Employee> specification =
        EmployeeSpecifications.isActive(true)
                .and(
                    EmployeeSpecifications.fullNameContains("an")
                            .or(EmployeeSpecifications.fullNameContains("binh"))
                );
```

Logic tương đương:

```sql
WHERE active = true
  AND (
      lower(full_name) LIKE '%an%'
      OR lower(full_name) LIKE '%binh%'
  )
```

Dấu ngoặc trong cách kết hợp Java rất quan trọng. Nếu bỏ nhóm OR, có thể tạo ra logic khác với yêu cầu nghiệp vụ.

### 5.1. Phủ định bằng not

Có thể đảo một Specification:

```java
Specification<Employee> inactive =
        Specification.not(EmployeeSpecifications.isActive(true));
```

Kết quả là điều kiện phủ định predicate active. Khi xử lý null hoặc SQL three-valued logic, cần kiểm tra semantics của predicate; NOT trên điều kiện có thể nhận UNKNOWN không giống cách hiểu boolean đơn giản trong Java.

## 6. Tổ chức service xây dựng truy vấn động

Service nhận DTO tìm kiếm và chỉ kết hợp những điều kiện được hỗ trợ:

```java
public record EmployeeSearchForm(
        String name,
        Boolean active,
        Instant createdFrom,
        Instant createdTo
) {
}
```

Service:

```java
@Service
@Transactional(readOnly = true)
public class EmployeeSearchService {

    private final EmployeeRepository repository;

    public EmployeeSearchService(EmployeeRepository repository) {
        this.repository = repository;
    }

    public Page<Employee> search(
            EmployeeSearchForm form,
            Pageable pageable
    ) {
        if (form.createdFrom() != null
                && form.createdTo() != null
                && !form.createdFrom().isBefore(form.createdTo())) {
            throw new IllegalArgumentException(
                    "createdFrom must be earlier than createdTo"
            );
        }

        Specification<Employee> specification =
                EmployeeSpecifications.isActive(form.active())
                        .and(EmployeeSpecifications.fullNameContains(form.name()))
                        .and(EmployeeSpecifications.createdAtOnOrAfter(
                                form.createdFrom()
                        ))
                        .and(EmployeeSpecifications.createdBefore(
                                form.createdTo()
                        ));

        return repository.findAll(specification, pageable);
    }
}
```

Service chịu trách nhiệm xác thực quan hệ giữa các tham số, ví dụ ngày bắt đầu phải trước ngày kết thúc. Specification tập trung vào biểu diễn điều kiện database.

Không nhận tên property tùy ý từ client để đưa vào Criteria path hoặc Sort. Với sort động, dùng enum/allowlist và giới hạn page size ở tầng service/controller.

## 7. Kiểm thử Specification qua repository

Một Specification dùng Criteria API và phụ thuộc mapping JPA. Cách kiểm thử có giá trị nhất thường là chạy nó qua repository với JPA provider và database test thực tế.

`@DataJpaTest` phù hợp để kiểm tra slice persistence:

- Entity mapping và repository được cấu hình.
- Specification tạo predicate hợp lệ.
- Query trả đúng tập dữ liệu.
- JOIN, DISTINCT và count query hoạt động như mong muốn.
- Pageable và Sort được áp dụng.

Ví dụ test đầy đủ:

```java
package com.example.demo.employee;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.domain.Specification;

@DataJpaTest
class EmployeeSpecificationsTest {

    @Autowired
    private EmployeeRepository repository;

    @BeforeEach
    void setUp() {
        repository.saveAllAndFlush(List.of(
                new Employee(
                        "An Nguyen",
                        true,
                        Instant.parse("2026-01-10T08:00:00Z")
                ),
                new Employee(
                        "Binh Tran",
                        true,
                        Instant.parse("2026-02-10T08:00:00Z")
                ),
                new Employee(
                        "An inactive",
                        false,
                        Instant.parse("2026-03-10T08:00:00Z")
                ),
                new Employee(
                        "Chi Le",
                        true,
                        Instant.parse("2025-12-10T08:00:00Z")
                )
        ));

        // Buộc các lần đọc sau lấy dữ liệu qua query.
        repository.flush();
    }

    @Test
    void combinesActiveNameAndDateFilters() {
        Specification<Employee> specification =
                EmployeeSpecifications.isActive(true)
                        .and(EmployeeSpecifications.fullNameContains("an"))
                        .and(EmployeeSpecifications.createdAtOnOrAfter(
                                Instant.parse("2026-01-01T00:00:00Z")
                        ))
                        .and(EmployeeSpecifications.createdBefore(
                                Instant.parse("2026-03-01T00:00:00Z")
                        ));

        List<Employee> result = repository.findAll(
                specification,
                Sort.by(Sort.Direction.ASC, "id")
        );

        assertThat(result)
                .extracting(Employee::getFullName)
                .containsExactly("An Nguyen");
    }

    @Test
    void ignoresOptionalFiltersWhenValuesAreNull() {
        Specification<Employee> specification =
                EmployeeSpecifications.isActive(null)
                        .and(EmployeeSpecifications.fullNameContains(null))
                        .and(EmployeeSpecifications.createdAtOnOrAfter(null))
                        .and(EmployeeSpecifications.createdBefore(null));

        assertThat(repository.count(specification)).isEqualTo(4);
    }

    @Test
    void groupsOrConditionsInsideActiveFilter() {
        Specification<Employee> specification =
                EmployeeSpecifications.isActive(true)
                        .and(
                            EmployeeSpecifications.fullNameContains("an")
                                    .or(EmployeeSpecifications.fullNameContains("binh"))
                        );

        List<Employee> result = repository.findAll(
                specification,
                Sort.by("id")
        );

        assertThat(result)
                .extracting(Employee::getFullName)
                .containsExactly("An Nguyen", "Binh Tran");
    }

    @Test
    void appliesSpecificationToPageContentAndCount() {
        Specification<Employee> specification =
                EmployeeSpecifications.isActive(true);

        Page<Employee> page = repository.findAll(
                specification,
                PageRequest.of(
                        0,
                        2,
                        Sort.by(Sort.Direction.ASC, "id")
                )
        );

        assertThat(page.getContent()).hasSize(2);
        assertThat(page.getTotalElements()).isEqualTo(3);
        assertThat(page.getTotalPages()).isEqualTo(2);
    }
}
```

Ví dụ giả định entity/repository như các phần trước và có dependency Spring Boot JPA test, JUnit 5, AssertJ cùng database test được cấu hình. `@DataJpaTest` thường chạy trong transaction và rollback sau mỗi test method.

Test setup có thể dùng `saveAllAndFlush` để buộc INSERT xuống database trước khi kiểm tra. Nếu muốn bảo đảm query không vô tình lấy entity còn trong persistence context, có thể inject `TestEntityManager` rồi gọi `clear()` sau khi lưu dữ liệu.

## 8. Kiểm thử từng Specification độc lập

Ngoài test tổ hợp, nên có test cho từng predicate quan trọng. Điều này giúp xác định chính xác điều kiện nào bị lỗi khi bộ lọc phát triển.

Ví dụ kiểm tra tên không phân biệt hoa thường:

```java
@Test
void fullNameContainsIgnoresCase() {
    Specification<Employee> specification =
            EmployeeSpecifications.fullNameContains("NGUYEN");

    List<Employee> result = repository.findAll(specification);

    assertThat(result)
            .extracting(Employee::getFullName)
            .contains("An Nguyen");
}
```

Kiểm tra trạng thái false:

```java
@Test
void filtersInactiveEmployees() {
    Specification<Employee> specification =
            EmployeeSpecifications.isActive(false);

    List<Employee> result = repository.findAll(specification);

    assertThat(result)
            .extracting(Employee::getFullName)
            .containsExactly("An inactive");
}
```

Kiểm tra khoảng thời gian theo biên nửa mở:

```java
@Test
void filtersCreatedAtUsingInclusiveStartAndExclusiveEnd() {
    Specification<Employee> specification =
            EmployeeSpecifications.createdAtOnOrAfter(
                    Instant.parse("2026-01-10T08:00:00Z")
            ).and(
                    EmployeeSpecifications.createdBefore(
                            Instant.parse("2026-02-10T08:00:00Z")
                    )
            );

    List<Employee> result = repository.findAll(specification);

    assertThat(result)
            .extracting(Employee::getFullName)
            .containsExactly("An Nguyen");
}
```

Dùng khoảng `[from, to)`: bao gồm thời điểm bắt đầu và loại trừ thời điểm kết thúc. Cách này thường thuận tiện khi chia dữ liệu theo ngày/tháng vì hai khoảng liền nhau không bị trùng ở ranh giới. Hãy thống nhất timezone và độ chính xác timestamp giữa Java và database.

## 9. Kiểm thử association JOIN

Specification có thể truy cập association bằng JOIN. Ví dụ Employee thuộc Department:

```java
public static Specification<Employee> belongsToDepartment(Long departmentId) {
    return (root, query, cb) -> {
        if (departmentId == null) {
            return cb.conjunction();
        }

        return cb.equal(
                root.join("department").get("id"),
                departmentId
        );
    };
}
```

Test cần tạo Department và Employee liên kết đúng, sau đó xác nhận chỉ Employee thuộc phòng ban đó được trả về. Không chỉ kiểm tra query không ném exception; cần xác nhận cả tập kết quả.

Nếu Specification JOIN collection, một entity cha có thể xuất hiện nhiều lần do một hàng cho mỗi phần tử collection. Có thể cần:

```java
query.distinct(true);
```

Tuy nhiên, DISTINCT ảnh hưởng cả cách database đếm và cách provider tạo count query. Hãy test `findAll(spec, pageable)` và `count(spec)` riêng để chắc chắn tổng số phần tử là số entity logic, không phải số hàng JOIN.

## 10. Không trộn fetch join vào Specification dùng chung một cách tùy tiện

Specification có thể truy cập `CriteriaQuery<?>` và thêm fetch:

```java
root.fetch("department", JoinType.LEFT);
```

Nhưng một Specification có fetch join có thể được dùng cho cả query lấy nội dung và count query của Page. Count query không nhất thiết chấp nhận fetch join, đặc biệt khi fetch collection hoặc query được chuyển thành phép đếm.

Vì vậy:

- Giữ Specification tái sử dụng tập trung vào predicate WHERE.
- Dùng `@EntityGraph` hoặc query riêng để điều khiển fetch plan khi cần.
- Nếu phải dùng fetch trong Specification, phân biệt content query với count query một cách có chủ đích và viết integration test cho cả hai.
- Tránh để một Specification tìm kiếm đơn giản thay đổi selection, order hoặc fetch behavior ngoài mục tiêu của nó.

Đây là lý do một predicate nhỏ thường dễ dùng lại hơn một Specification chứa nhiều side effect trên query.

## 11. Kiểm thử Specification với null và dữ liệu biên

Filter tùy chọn là nơi thường phát sinh lỗi. Hãy kiểm tra rõ:

| Trường hợp | Kỳ vọng |
|---|---|
| Filter null | Không thêm điều kiện tương ứng |
| Chuỗi rỗng | Được chuẩn hóa hoặc bỏ qua theo quy tắc form |
| Chuỗi chỉ có khoảng trắng | Không tạo LIKE với pattern rỗng ngoài ý muốn |
| Boolean false | Vẫn là một điều kiện hợp lệ |
| Giá trị ngày bắt đầu | Có/không bao gồm đúng theo hợp đồng |
| Giá trị ngày kết thúc | Có/không bao gồm đúng theo hợp đồng |
| Khoảng ngày đảo ngược | Bị từ chối ở tầng validation |
| Ký tự % và _ | Có semantics wildcard hoặc literal đã xác định |
| Không có hàng khớp | Trả danh sách/trang rỗng, count bằng 0 |
| Probe/filter rỗng hoàn toàn | Có hành vi được quyết định rõ, tránh vô tình quét toàn bảng |

Không nên dùng primitive để biểu diễn filter tùy chọn nếu cần phân biệt “không gửi” với false hoặc 0. Dùng wrapper như `Boolean` hoặc `Integer` để giữ được trạng thái chưa chọn.

## 12. Unit test hay integration test?

Có thể kiểm thử Specification ở nhiều mức, nhưng mỗi mức chứng minh điều khác nhau.

### 12.1. Unit test thuần Java

Unit test phù hợp với logic chuẩn hóa input, validation khoảng ngày, mapping DTO hoặc lựa chọn filter. Ví dụ kiểm tra chuỗi trống thành null:

```java
assertThat(blankToNull("   ")).isNull();
assertThat(blankToNull(" An ")).isEqualTo("An");
```

Không nên mock toàn bộ Root, CriteriaBuilder, Path và Predicate chỉ để xác nhận một Specification gọi đúng vài method. Mock Criteria API thường mong manh và không chứng minh query chạy được với provider.

### 12.2. Repository integration test

Dùng `@DataJpaTest` để kiểm tra Specification thực sự được chuyển thành query và trả dữ liệu đúng. Đây là mức test chính cho:

- Predicate và kiểu dữ liệu.
- Property path và association mapping.
- AND/OR.
- DISTINCT và JOIN.
- Page content/count.
- Null và biên thời gian.

### 12.3. Kiểm thử với database production

H2 hoặc embedded database hữu ích cho test nhanh nhưng không bảo đảm tương đương PostgreSQL, MySQL, Oracle hoặc SQL Server về collation, kiểu dữ liệu, hàm, index và query plan.

Nếu Specification sử dụng hàm database, kiểu dữ liệu đặc thù, collation hoặc logic phụ thuộc dialect, dùng Testcontainers hoặc database test tương ứng với production.

## 13. Kiểm tra hiệu năng của Specification

Specification chỉ là cách xây dựng query. Nó không tự làm query nhanh hơn derived query hoặc JPQL.

Khi query chậm, kiểm tra:

- SQL provider sinh ra.
- Số lượng JOIN và khả năng nhân bản hàng.
- Điều kiện LIKE có wildcard ở đầu.
- Index trên các cột filter và join key.
- Count query của Page.
- Sort và kích thước trang.
- N+1 query do truy cập lazy association sau khi đọc kết quả.

Có thể bật SQL logging trong môi trường phát triển hoặc dùng datasource metrics. Dùng EXPLAIN/EXPLAIN ANALYZE trên database đích để xem index scan, row estimate, sort và buffer usage.

Không viết assertion về toàn bộ chuỗi SQL trong test thông thường vì SQL có thể thay đổi theo provider/version. Hãy kiểm tra hành vi nghiệp vụ bằng dữ liệu; dành kiểm thử SQL/plan riêng cho những query quan trọng về hiệu năng.

## 14. Tổ chức thư mục và quy ước đặt tên

Một cấu trúc dễ bảo trì:

```text
employee/
  Employee.java
  EmployeeRepository.java
  EmployeeSearchForm.java
  EmployeeSearchService.java
  EmployeeSpecifications.java
  EmployeeSpecificationsTest.java
```

Quy ước:

- Tên method diễn tả điều kiện nghiệp vụ: `isActive`, `fullNameContains`, `createdBefore`.
- Mỗi method tạo một predicate, không giữ mutable state.
- Chuẩn hóa input ở service hoặc một lớp riêng; không lặp quy tắc trim/null trong nhiều nơi.
- Specification dùng chung không tự thêm authorization filter theo một request cụ thể nếu thông tin tenant/user chưa được truyền rõ ràng.
- Filter bảo mật bắt buộc phải được kết hợp ở server trong mọi đường truy cập, không phụ thuộc client.
- Tránh tạo một Specification “generic” nhận tên property tùy ý từ request.

Với domain lớn, có thể chia theo nhóm như EmployeeSpecifications, OrderSpecifications, InvoiceSpecifications thay vì một lớp chứa hàng trăm điều kiện không liên quan.

## 15. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Filter null vẫn thu hẹp kết quả | Xử lý null không nhất quán hoặc primitive default | Dùng wrapper và predicate no-op rõ ràng |
| OR trả nhiều hàng ngoài dự kiến | Nhóm AND/OR sai | Đặt ngoặc bằng cách nhóm Specification trước khi kết hợp |
| Test chạy nhưng Page total sai | JOIN collection tạo hàng trùng hoặc count khác content | Kiểm tra DISTINCT và count query |
| Count query lỗi | Specification thêm fetch join hoặc sửa selection | Giữ predicate độc lập, tách fetch plan |
| Kết quả trùng entity | JOIN collection nhân bản hàng | Dùng distinct có kiểm thử |
| Test H2 pass nhưng production lỗi | Dialect/collation/type khác nhau | Test với database production qua Testcontainers |
| Specification không dùng lại được | Chứa filter hoặc state riêng của một màn hình | Tách thành predicate nhỏ, truyền tham số rõ |
| LIKE không tìm literal %/_ | Wildcard chưa được escape | Xác định semantics và dùng escape character |
| Query chậm khi thêm nhiều filter | Thiếu index hoặc predicate làm mất khả năng dùng index | Xem SQL và execution plan |
| Mock Criteria API quá phức tạp | Test ở sai tầng | Kiểm thử predicate qua repository integration test |

## 16. Checklist cho bộ Specification tái sử dụng

- [ ] Repository kế thừa `JpaSpecificationExecutor<T>`.
- [ ] Mỗi Specification biểu diễn một predicate có tên rõ ràng.
- [ ] Specification không giữ trạng thái mutable giữa các lần gọi.
- [ ] Filter tùy chọn có semantics null/blank được định nghĩa.
- [ ] Boolean false và số 0 không bị nhầm với “không nhập”.
- [ ] AND/OR được nhóm đúng logic nghiệp vụ.
- [ ] Có test cho từng predicate quan trọng.
- [ ] Có test cho tổ hợp filter thực tế.
- [ ] Có test cho null, chuỗi rỗng, biên ngày và không có kết quả.
- [ ] Có test JOIN/DISTINCT nếu Specification dùng association.
- [ ] Có test Page content và total count.
- [ ] Specification dùng chung không tự ý thêm fetch join hoặc thay đổi selection.
- [ ] Authorization/tenant condition luôn được áp dụng từ server.
- [ ] Query quan trọng được kiểm tra SQL và execution plan.
- [ ] Dùng database test phù hợp khi có hành vi phụ thuộc dialect.

## Kết luận

Specification tái sử dụng nên là những predicate nhỏ, độc lập và không giữ trạng thái. Spring Data cho phép kết hợp chúng bằng AND, OR và NOT rồi thực thi qua `JpaSpecificationExecutor`. Cách tổ chức này giúp service xây dựng filter động mà không phải sao chép JPQL cho từng tổ hợp.

Bộ kiểm thử tốt cần chạy Specification qua repository và JPA provider thật. Hãy xác nhận từng điều kiện, cách nhóm logic, null/blank, JOIN, DISTINCT, phân trang và count query. Giữ fetch plan tách khỏi predicate dùng chung, kiểm tra authorization ở server và dùng database tương ứng production khi query phụ thuộc dialect. Như vậy, Specification mới thực sự có thể dùng lại mà vẫn giữ kết quả đúng khi ứng dụng phát triển.
