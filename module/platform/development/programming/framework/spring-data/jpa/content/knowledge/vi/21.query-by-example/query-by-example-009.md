# Lựa chọn Query by Example cho biểu mẫu tìm kiếm đơn giản

## Mục tiêu

Query by Example (QBE) là cách xây dựng truy vấn từ một object mẫu (probe). Ứng dụng điền các thuộc tính cần tìm vào probe, sau đó dùng `Example` và `ExampleMatcher` để xác định cách so khớp. Spring Data JPA chuyển các giá trị trong probe thành điều kiện truy vấn mà không cần viết JPQL cho từng tổ hợp filter.

QBE đặc biệt phù hợp với biểu mẫu tìm kiếm đơn giản, trong đó người dùng có thể điền một hoặc nhiều trường tùy chọn như tên, email, trạng thái hoặc phòng ban. Các giá trị không được điền thường được bỏ qua.

Sau bài này, bạn có thể:

- Hiểu probe, Example và ExampleMatcher.
- Tạo truy vấn tìm kiếm từ các trường tùy chọn của form.
- Chọn matchingAll hoặc matchingAny.
- Cấu hình so khớp chuỗi, phân biệt hoa thường và bỏ qua thuộc tính.
- Kết hợp QBE với Sort và Pageable.
- Nhận biết giới hạn của QBE và khi nào nên chuyển sang Specification, Querydsl hoặc @Query.
- Tránh lỗi do primitive default value, null, association và dữ liệu form không đáng tin cậy.

Ví dụ sử dụng Java 17+, Spring Boot 3.x, Jakarta Persistence và Spring Data JPA.

## 1. Query by Example là gì?

QBE xây dựng điều kiện tìm kiếm từ một object mẫu. Các thuộc tính có giá trị trong probe trở thành tiêu chí so khớp; các thuộc tính null thường được bỏ qua theo mặc định.

Ví dụ, người dùng điền form:

- Tên: `An`
- Email: để trống
- Trạng thái hoạt động: `true`

Ứng dụng tạo probe Employee có fullName là `An`, email là null và active là true. QBE tạo truy vấn tương đương về ý nghĩa:

```sql
WHERE full_name = 'An'
  AND active = true
```

Nếu cấu hình matcher cho tên theo kiểu chứa chuỗi, điều kiện có thể tương đương:

```sql
WHERE full_name LIKE '%An%'
  AND active = true
```

SQL thực tế được JPA provider sinh ra và sử dụng bind parameter; không cần tự ghép chuỗi SQL.

Ba thành phần chính:

| Thành phần | Vai trò |
|---|---|
| Probe | Object mẫu chứa các giá trị cần tìm |
| ExampleMatcher | Quy định cách so khớp, bỏ qua field và xử lý chuỗi |
| Example | Kết hợp probe với matcher thành tiêu chí truy vấn |

QBE nằm trong Spring Data Commons và được Spring Data JPA hỗ trợ thông qua `QueryByExampleExecutor`.

## 2. Probe, Example và repository

Giả sử entity Employee:

```java
package com.example.demo.employee;

import jakarta.persistence.*;

@Entity
@Table(name = "employees")
public class Employee {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String fullName;

    @Column(nullable = false, unique = true, length = 320)
    private String email;

    @Column(nullable = false)
    private Boolean active;

    protected Employee() {
    }

    public Employee(String fullName, String email, Boolean active) {
        this.fullName = fullName;
        this.email = email;
        this.active = active;
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public String getEmail() {
        return email;
    }

    public Boolean getActive() {
        return active;
    }

    public void setFullName(String fullName) {
        this.fullName = fullName;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public void setActive(Boolean active) {
        this.active = active;
    }
}
```

Repository:

```java
package com.example.demo.employee;

import org.springframework.data.jpa.repository.JpaRepository;

public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {
}
```

`JpaRepository` kế thừa khả năng Query by Example, nên repository có thể dùng các phương thức như `findAll(Example<S>)`, `findOne(Example<S>)`, `count(Example<S>)`, `exists(Example<S>)` và các overload nhận Sort hoặc Pageable.

Tạo probe và Example:

```java
Employee probe = new Employee();
probe.setFullName("An");
probe.setActive(true);

Example<Employee> example = Example.of(probe);
```

Ở đây email không được đặt nên là null và mặc định bị bỏ qua. Query sẽ tìm Employee có fullName khớp `An` và active khớp `true` theo matcher mặc định.

Lưu ý: probe chỉ là object dùng để mô tả điều kiện tìm kiếm. Không gọi `save(probe)` và không cần persist probe vào database.

## 3. ExampleMatcher và cách so khớp

`ExampleMatcher` quy định cách xử lý các thuộc tính trong probe. Có thể tạo matcher bằng:

```java
ExampleMatcher matcher = ExampleMatcher.matchingAll();
```

Hoặc:

```java
ExampleMatcher matcher = ExampleMatcher.matchingAny();
```

### 3.1. matchingAll: tất cả điều kiện phải khớp

`matchingAll()` là AND giữa các thuộc tính được đưa vào probe.

Ví dụ probe có fullName và active:

```java
ExampleMatcher matcher = ExampleMatcher.matchingAll();

Example<Employee> example = Example.of(probe, matcher);
```

Ý nghĩa:

```sql
WHERE full_name = ?
  AND active = ?
```

Đây là lựa chọn thường phù hợp cho biểu mẫu tìm kiếm có nhiều filter: mỗi trường người dùng điền đều thu hẹp tập kết quả.

### 3.2. matchingAny: chỉ cần một điều kiện khớp

`matchingAny()` tạo logic OR giữa các thuộc tính được đưa vào probe:

```java
ExampleMatcher matcher = ExampleMatcher.matchingAny();

Example<Employee> example = Example.of(probe, matcher);
```

Ý nghĩa:

```sql
WHERE full_name = ?
   OR email = ?
   OR active = ?
```

Chỉ các thuộc tính được xem là có giá trị theo cấu hình matcher mới tham gia. Hãy dùng matchingAny khi nghiệp vụ thật sự muốn tìm thấy bản ghi nếu một trong các tiêu chí khớp.

Không nhầm matchingAny với khả năng xây dựng các nhóm điều kiện phức tạp. QBE không biểu diễn tự do biểu thức kiểu:

```sql
WHERE active = true
  AND (full_name LIKE ? OR email LIKE ?)
```

`matchingAny()` sẽ OR toàn bộ các tiêu chí được đưa vào probe; nó không cho phép tự nhóm một vài điều kiện OR bên trong một nhóm AND khác. Với logic như trên, dùng Specification, Querydsl hoặc JPQL.

### 3.3. Hành vi mặc định

Nếu dùng `Example.of(probe)` mà không truyền matcher:

- Null value được bỏ qua theo mặc định.
- String được so khớp chính xác (exact).
- String phân biệt chữ hoa/chữ thường theo mặc định.
- Các thuộc tính không null khác được so sánh theo kiểu tương ứng.

Để code thể hiện rõ ý định, có thể khai báo `matchingAll().withIgnoreNullValues()` thay vì phụ thuộc vào mặc định.

## 4. Tạo matcher cho trường chuỗi

Các biểu mẫu tìm kiếm thường cần tìm tên theo một phần chuỗi thay vì chính xác toàn bộ. `ExampleMatcher` hỗ trợ nhiều kiểu so khớp chuỗi:

| Kiểu | Ý nghĩa | Ví dụ probe |
|---|---|---|
| `EXACT` | Bằng chính xác | `An` |
| `STARTING` | Bắt đầu bằng | `An` |
| `ENDING` | Kết thúc bằng | `An` |
| `CONTAINING` | Có chứa chuỗi | `An` |

Ví dụ:

```java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnoreNullValues()
        .withStringMatcher(ExampleMatcher.StringMatcher.CONTAINING)
        .withIgnoreCase();
```

Cấu hình này áp dụng chứa chuỗi và không phân biệt hoa thường cho các thuộc tính String được đưa vào probe. Nếu chỉ muốn một số field chứa chuỗi, nên cấu hình riêng từng thuộc tính để tránh thay đổi semantics của email hoặc mã định danh.

### 4.1. Matcher riêng cho từng thuộc tính

```java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnoreNullValues()
        .withMatcher(
                "fullName",
                match -> match.contains().ignoreCase()
        )
        .withMatcher(
                "email",
                match -> match.exact().ignoreCase()
        );
```

Trong ví dụ:

- `fullName` tìm chuỗi con và không phân biệt hoa thường.
- `email` so khớp chính xác và không phân biệt hoa thường.
- Các thuộc tính khác giữ quy tắc mặc định.
- Null value được bỏ qua.

Tên trong `withMatcher` là property path của entity, không phải tên cột SQL. Ví dụ entity có `fullName` được map sang cột `full_name`, matcher vẫn dùng `fullName`.

### 4.2. Phân biệt hoa thường

Có thể đặt case-insensitive cho mọi String:

```java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnoreCase();
```

Hoặc chỉ một vài property:

```java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnoreCase("fullName", "email");
```

Provider/database có thể chuyển điều kiện thành biểu thức chuẩn hóa chữ hoa hoặc chữ thường. Cách so sánh Unicode và collation phụ thuộc database. Nếu ứng dụng có yêu cầu đặc biệt về dấu tiếng Việt, collation hoặc locale, hãy kiểm thử trên database đích.

### 4.3. Không dùng một kiểu chuỗi cho mọi field một cách máy móc

Nếu dùng `CONTAINING` toàn cục, email, mã nhân viên và các chuỗi khác cũng có thể được tìm theo kiểu chứa. Điều này có thể không đúng nghiệp vụ và làm query khó tận dụng index thông thường.

Nên đặt matcher theo từng property:

- Tên: CONTAINING hoặc STARTING.
- Email: EXACT, có thể ignoreCase.
- Mã nhân viên: EXACT.
- Từ khóa mô tả: CONTAINING nếu nghiệp vụ cho phép.

Chọn semantics trước, sau đó mới chọn matcher.

## 5. Xây dựng QBE từ form tìm kiếm

Không nên nhận trực tiếp toàn bộ entity từ request làm probe. Tạo DTO riêng cho các trường mà biểu mẫu được phép tìm kiếm:

```java
package com.example.demo.employee;

public record EmployeeSearchForm(
        String name,
        String email,
        Boolean active
) {
}
```

Dùng wrapper `Boolean` để phân biệt ba trạng thái:

- `true`: chỉ tìm nhân viên đang hoạt động.
- `false`: chỉ tìm nhân viên không hoạt động.
- `null`: không áp dụng điều kiện trạng thái.

Nếu dùng primitive `boolean`, giá trị mặc định là false; QBE có thể hiểu false là tiêu chí cần so khớp ngay cả khi người dùng không chọn trạng thái. Đây là lỗi thường gặp với probe có primitive field.

Tạo probe:

```java
private Employee toProbe(EmployeeSearchForm form) {
    Employee probe = new Employee();

    probe.setFullName(blankToNull(form.name()));
    probe.setEmail(blankToNull(form.email()));
    probe.setActive(form.active());

    return probe;
}

private String blankToNull(String value) {
    if (value == null || value.isBlank()) {
        return null;
    }

    return value.trim();
}
```

Chuyển chuỗi trống thành null giúp field đó được bỏ qua theo null handling mặc định. Nếu để chuỗi rỗng, QBE có thể tạo điều kiện tìm chuỗi rỗng thay vì bỏ qua filter.

Tạo Example:

```java
private Example<Employee> toExample(EmployeeSearchForm form) {
    Employee probe = toProbe(form);

    ExampleMatcher matcher = ExampleMatcher.matchingAll()
            .withIgnoreNullValues()
            .withMatcher(
                    "fullName",
                    match -> match.contains().ignoreCase()
            )
            .withMatcher(
                    "email",
                    match -> match.exact().ignoreCase()
            );

    return Example.of(probe, matcher);
}
```

## 6. Repository method với QBE

Service có thể dùng Example để tìm danh sách:

```java
@Service
public class EmployeeSearchService {

    private final EmployeeRepository repository;

    public EmployeeSearchService(EmployeeRepository repository) {
        this.repository = repository;
    }

    public List<Employee> search(EmployeeSearchForm form) {
        Example<Employee> example = toExample(form);
        return repository.findAll(example);
    }

    private Example<Employee> toExample(EmployeeSearchForm form) {
        Employee probe = new Employee();
        probe.setFullName(blankToNull(form.name()));
        probe.setEmail(blankToNull(form.email()));
        probe.setActive(form.active());

        ExampleMatcher matcher = ExampleMatcher.matchingAll()
                .withIgnoreNullValues()
                .withMatcher(
                        "fullName",
                        match -> match.contains().ignoreCase()
                )
                .withMatcher(
                        "email",
                        match -> match.exact().ignoreCase()
                );

        return Example.of(probe, matcher);
    }

    private String blankToNull(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        return value.trim();
    }
}
```

Các method QBE có thể dùng:

```java
repository.findAll(example);
repository.findAll(example, Sort.by("fullName"));
repository.findAll(example, pageable);
repository.findOne(example);
repository.count(example);
repository.exists(example);
```

`findOne` phù hợp khi mong đợi tối đa một kết quả. Nếu nhiều hàng khớp, Spring Data có thể ném `IncorrectResultSizeDataAccessException`; đừng dùng nó như một cách tùy tiện để lấy một hàng đầu tiên.

## 7. Kết hợp QBE với phân trang và sắp xếp

Với biểu mẫu tìm kiếm có thể trả về nhiều kết quả, nên giới hạn dữ liệu bằng `Pageable`:

```java
public Page<Employee> search(
        EmployeeSearchForm form,
        Pageable pageable
) {
    Example<Employee> example = toExample(form);
    return repository.findAll(example, pageable);
}
```

Gọi service:

```java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(
                Sort.Order.asc("fullName"),
                Sort.Order.asc("id")
        )
);

Page<Employee> page = searchService.search(form, pageable);
```

Sort dùng property Java của entity. Thêm ID làm tiêu chí cuối giúp thứ tự xác định hơn khi nhiều nhân viên có cùng tên.

Có thể dùng `Slice` hoặc query theo window/scrolling trong các thiết kế phù hợp, nhưng hãy kiểm tra API/version cụ thể. Với QBE thông thường, các overload nhận Pageable và Sort là lựa chọn trực tiếp, dễ dùng.

### 7.1. Page và count query

`Page<T>` cung cấp tổng số phần tử và tổng số trang. Vì vậy, Spring Data có thể phải thực hiện thêm count query.

Nếu giao diện chỉ cần biết còn dữ liệu tiếp theo hay không, cân nhắc Slice hoặc một cơ chế cuộn phù hợp để tránh chi phí đếm tổng. Chọn theo yêu cầu UX, không phải lúc nào Page cũng cần thiết.

## 8. Bỏ qua các thuộc tính không tham gia tìm kiếm

Probe thường được tạo từ entity nên có thể chứa nhiều field hơn form. Hãy bỏ qua các thuộc tính không phải tiêu chí tìm kiếm:

```java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnoreNullValues()
        .withIgnorePaths(
                "id",
                "createdAt",
                "updatedAt",
                "version"
        );
```

Null field thường đã được bỏ qua, nhưng `withIgnorePaths` thể hiện rõ những property không được dùng làm điều kiện. Điều này hữu ích khi probe có giá trị mặc định hoặc khi entity có các field kỹ thuật.

### 8.1. Primitive field có giá trị mặc định

Các primitive như `boolean`, `int` và `long` không thể null. Một probe mới tạo sẽ có các giá trị mặc định như false hoặc 0. QBE có thể coi những giá trị đó là điều kiện tìm kiếm.

Ví dụ entity:

```java
private boolean active;
private int level;
```

Một probe mới sẽ có active là false và level là 0. Nếu form không có hai filter này, query vẫn có thể vô tình thêm các điều kiện tương ứng.

Cách xử lý:

- Dùng wrapper `Boolean`, `Integer`, `Long` cho thuộc tính có thể không được đưa vào probe.
- Hoặc thêm field primitive vào `withIgnorePaths` khi filter không được chọn.
- Có thể xây matcher động theo trạng thái form, nhưng phải kiểm thử cả trường hợp false/0 là giá trị người dùng thực sự muốn tìm.

Không chuyển false thành null nếu false là một tiêu chí tìm kiếm hợp lệ.

## 9. Nested property và association

QBE có thể làm việc với một số nested property path thông qua object graph trong probe. Ví dụ Employee có quan hệ to-one tới Department:

```java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "department_id")
private Department department;
```

Nếu form có departmentName, có thể tạo Department probe:

```java
Department departmentProbe = new Department();
departmentProbe.setName(blankToNull(form.departmentName()));

Employee employeeProbe = new Employee();
employeeProbe.setDepartment(departmentProbe);
```

Matcher có thể tham chiếu path:

```java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnoreNullValues()
        .withMatcher(
                "department.name",
                match -> match.contains().ignoreCase()
        );
```

Đường dẫn association có thể khiến JPA provider tạo JOIN. Hãy kiểm tra SQL và số lượng query thực tế; không giả định nested property luôn rẻ hoặc không tạo JOIN.

QBE không hỗ trợ so khớp collection/map như một tiêu chí probe thông thường. Nếu cần tìm Employee có ít nhất một Order thỏa điều kiện, hoặc cần điều kiện trên collection association, dùng JPQL, Specification hoặc Querydsl.

## 10. Null handling và ý nghĩa của form

Mặc định, null values được bỏ qua. Nếu muốn thay đổi semantics, cần xác định rõ nghiệp vụ:

| Giá trị trong form | Cách xử lý thường dùng |
|---|---|
| Null | Bỏ qua filter |
| Chuỗi rỗng | Chuẩn hóa thành null nếu form coi là chưa nhập |
| Chuỗi có khoảng trắng | Trim trước khi tạo probe |
| Boolean false | Giữ false nếu người dùng chọn “không hoạt động” |
| Số 0 | Giữ 0 nếu đó là tiêu chí hợp lệ |
| Ngày null | Bỏ qua filter ngày; QBE không tự tạo khoảng ngày |

QBE thường bỏ qua null trong probe. Nếu cần tìm các hàng có cột null, QBE có thể cấu hình include null values qua matcher, nhưng việc đưa null vào probe sẽ áp dụng cho các thuộc tính được chọn theo quy tắc matcher và có thể không phù hợp với một form nhiều filter. Hãy dùng cách này có chủ đích và kiểm thử.

Nếu form cần phân biệt “không nhập” với “tìm trường có giá trị null”, phải biểu diễn trạng thái đó riêng trong DTO; một giá trị null duy nhất không thể diễn tả cả hai ý nghĩa.

## 11. Giới hạn của Query by Example

QBE có giao diện đơn giản, nhưng không phải bộ xây dựng query tổng quát.

Các giới hạn quan trọng:

- Không hỗ trợ các nhóm điều kiện tùy ý như `(A AND B) OR (C AND D)`.
- `matchingAny()` chỉ OR các thuộc tính được chọn; không xây được các nhóm logic lồng nhau.
- Không phù hợp với điều kiện so sánh như lớn hơn, nhỏ hơn, BETWEEN hoặc phép tính khoảng ngày.
- Không hỗ trợ so khớp collection/map theo cách probe thông thường.
- Không thay thế được các truy vấn JOIN phức tạp, subquery hoặc aggregate.
- Các kiểu StringMatcher và hành vi của store có giới hạn riêng; không giả định mọi kiểu như regex đều được JPA hỗ trợ portable.
- Không phải cách tốt nhất khi truy vấn cần điều kiện bảo mật/tenant phức tạp phải kết hợp với filter do server kiểm soát.

Ví dụ yêu cầu tìm nhân viên có ngày tạo trong khoảng:

```sql
WHERE created_at >= :from
  AND created_at < :to
```

QBE không có matcher chuẩn để biểu diễn range này. Dùng Specification hoặc JPQL:

```java
@Query("""
       select e
       from Employee e
       where e.createdAt >= :from
         and e.createdAt < :to
       """)
List<Employee> findCreatedBetween(
        @Param("from") Instant from,
        @Param("to") Instant to
);
```

## 12. Khi nào chọn QBE, Specification, Querydsl hoặc @Query?

| Công cụ | Phù hợp khi | Hạn chế/cân nhắc |
|---|---|---|
| Query by Example | Form tìm kiếm đơn giản, nhiều field tùy chọn, điều kiện chủ yếu exact/LIKE | Không biểu diễn được nhóm logic và range phức tạp |
| Specification | Filter động, AND/OR, range, join và predicate có điều kiện | Cần viết predicate bằng Criteria API |
| Querydsl | Query động có kiểu, nhiều điều kiện và biểu thức | Cần cấu hình annotation processing/dependency |
| @Query | Truy vấn rõ ràng, cố định, có JPQL/native SQL cụ thể | Query phải được bảo trì cùng method |
| Derived query | Điều kiện đơn giản, có thể biểu diễn rõ bằng tên method | Method name dài khi nhiều điều kiện |

Một quy tắc chọn nhanh:

- Form có name, email, active tùy chọn và các điều kiện đều so khớp đơn giản: QBE.
- Form có date range, giá trị lớn hơn/nhỏ hơn hoặc nhóm OR riêng: Specification/Querydsl.
- Báo cáo có JOIN, GROUP BY, aggregate rõ ràng: @Query hoặc custom repository.
- Query cố định, dễ diễn đạt bằng method name: derived query.

Không cần dùng QBE chỉ vì repository hỗ trợ nó. Chọn công cụ biểu đạt đúng logic nghiệp vụ và dễ kiểm thử nhất.

## 13. Bảo mật và quyền truy cập khi tạo probe

Không bind toàn bộ request trực tiếp vào entity probe. Entity có thể chứa các field như tenantId, role, salary, internalStatus hoặc dữ liệu audit mà người dùng không được quyền dùng để điều khiển truy vấn.

Nên:

1. Tạo DTO search chỉ có các filter được công khai.
2. Map thủ công các field được phép từ DTO sang probe.
3. Thêm điều kiện tenant/authorization từ thông tin xác thực ở server.
4. Không để client quyết định tenant hoặc phạm vi dữ liệu được truy cập.
5. Giới hạn page size và sort field.

Ví dụ, nếu mọi truy vấn phải giới hạn theo tenant hiện tại, đừng lấy tenantId trực tiếp từ form. Lấy tenantId từ security context và bảo đảm điều kiện này luôn được áp dụng. QBE đơn thuần có thể không đủ để kết hợp một điều kiện bắt buộc phức tạp với các filter tùy chọn; khi đó dùng Specification hoặc query service có predicate bảo mật riêng.

QBE sử dụng bind parameter qua cơ chế query của Spring Data/JPA, nhưng điều đó không thay thế authorization và validation.

## 14. Hiệu năng và SQL được sinh ra

QBE giúp giảm code tạo query, nhưng hiệu năng vẫn phụ thuộc SQL cuối cùng.

Các điểm cần kiểm tra:

- `CONTAINING` thường tạo điều kiện LIKE có wildcard ở đầu; index B-tree thông thường có thể không hỗ trợ hiệu quả.
- Ignore case có thể khiến database áp dụng LOWER/UPPER hoặc cơ chế collation; functional index hoặc collation phù hợp có thể cần thiết.
- Nested association có thể tạo JOIN.
- matchingAny có thể tạo nhiều nhánh OR, làm query khó dùng index hơn.
- Page có thể phát sinh count query.
- Probe có nhiều field không cần thiết có thể tạo điều kiện lọc ngoài ý muốn.

Hãy bật SQL logging trong môi trường phát triển hoặc dùng datasource metrics để xem câu SQL và bind parameter. Dùng EXPLAIN/EXPLAIN ANALYZE trên database đích để xác nhận index và execution plan. Không kết luận QBE nhanh hơn Specification hay @Query chỉ từ số dòng code.

## 15. Kiểm thử Query by Example

Ví dụ test với repository:

```java
@DataJpaTest
class EmployeeQueryByExampleTest {

    @Autowired
    private EmployeeRepository repository;

    @Test
    void findsEmployeesByPartialNameAndStatus() {
        repository.save(new Employee(
                "An Nguyen",
                "an@example.com",
                true
        ));

        repository.save(new Employee(
                "Binh Tran",
                "binh@example.com",
                true
        ));

        repository.save(new Employee(
                "An inactive",
                "inactive@example.com",
                false
        ));

        Employee probe = new Employee();
        probe.setFullName("an");
        probe.setActive(true);

        ExampleMatcher matcher = ExampleMatcher.matchingAll()
                .withIgnoreNullValues()
                .withMatcher(
                        "fullName",
                        match -> match.contains().ignoreCase()
                );

        Example<Employee> example = Example.of(probe, matcher);

        List<Employee> result = repository.findAll(example);

        assertThat(result)
                .extracting(Employee::getEmail)
                .containsExactlyInAnyOrder(
                        "an@example.com"
                );
    }
}
```

Test giả định Employee có constructor/getter/setter như ví dụ và các dependency JUnit 5, AssertJ, Spring Boot JPA test support đã được cấu hình. `@DataJpaTest` thường chạy trong transaction và rollback sau test.

Nên kiểm thử thêm:

- Probe có tất cả field null.
- Chuỗi rỗng và chuỗi chỉ có khoảng trắng.
- exact, startsWith và contains.
- ignoreCase với dữ liệu có chữ hoa/thường.
- Boolean false được giữ làm điều kiện.
- Primitive field không vô tình tham gia query.
- matchingAll và matchingAny.
- Nested association nếu ứng dụng sử dụng.
- Page/Sort và thứ tự khi có giá trị trùng.
- Các filter tenant/authorization do server bổ sung.

Nếu probe rỗng, Example có thể không tạo tiêu chí lọc hữu ích và có thể trả về toàn bộ tập dữ liệu. Với biểu mẫu tìm kiếm, hãy quyết định rõ có cho phép tìm kiếm không điều kiện hay yêu cầu ít nhất một filter trước khi gọi repository.

## 16. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Form bỏ trống nhưng query tìm chuỗi rỗng | Không chuẩn hóa blank thành null | Trim và chuyển chuỗi rỗng thành null |
| Chỉ muốn tìm active=true nhưng không có kết quả | Probe có primitive false mặc định | Dùng Boolean wrapper hoặc ignorePaths |
| Tìm tên không phân biệt hoa thường nhưng kết quả thiếu | Chưa cấu hình ignoreCase hoặc collation khác | Cấu hình matcher và test trên database đích |
| matchingAny trả quá nhiều hàng | Các field được OR toàn bộ | Dùng matchingAll hoặc Specification để nhóm điều kiện |
| Không tạo được date range | QBE không hỗ trợ toán tử range | Dùng Specification hoặc @Query |
| Association collection không được so khớp | QBE không hỗ trợ collection/map probe matching | Dùng JOIN với Specification/Querydsl/JPQL |
| findOne ném exception | Nhiều hàng khớp Example | Dùng List/Page hoặc bảo đảm điều kiện duy nhất |
| Query chậm với contains | LIKE có wildcard đầu | Xem execution plan và chọn chiến lược tìm kiếm phù hợp |
| Người dùng lọc được field nội bộ | Bind entity trực tiếp từ request | Dùng search DTO và map allowlist |
| Probe rỗng trả toàn bộ dữ liệu | Không kiểm tra số filter trước khi query | Quy định rõ hành vi form rỗng |

## 17. Checklist chọn Query by Example

- [ ] Form có các filter tùy chọn với semantics đơn giản.
- [ ] Dùng DTO tìm kiếm riêng, không bind entity trực tiếp từ request.
- [ ] Probe chỉ chứa các field được phép tìm.
- [ ] Chọn matchingAll hay matchingAny theo đúng logic.
- [ ] Cấu hình matcher riêng cho từng chuỗi khi cần.
- [ ] Trim và chuẩn hóa chuỗi rỗng.
- [ ] Dùng wrapper cho filter tùy chọn thay vì primitive default.
- [ ] Bỏ qua ID, audit và field kỹ thuật không tham gia tìm kiếm.
- [ ] Kiểm tra nested association và tránh collection matching.
- [ ] Dùng Pageable/Sort và giới hạn page size.
- [ ] Không dùng QBE cho range, nhóm logic hoặc query phức tạp.
- [ ] Bổ sung tenant/authorization filter từ server.
- [ ] Kiểm thử probe rỗng, null, false, chuỗi đặc biệt và database đích.
- [ ] Xem SQL và execution plan khi query có yêu cầu hiệu năng.

## Kết luận

Query by Example phù hợp với biểu mẫu tìm kiếm đơn giản có nhiều trường tùy chọn. Ứng dụng tạo probe từ DTO, chọn `ExampleMatcher` để quy định exact/contains/case-insensitive và tạo `Example` để repository thực thi. Null thường được bỏ qua; matchingAll tạo AND và matchingAny tạo OR trên các tiêu chí được chọn.

QBE giúp giảm code query cho các filter cơ bản, nhưng không thay thế công cụ truy vấn tổng quát. Với range, nhóm điều kiện phức tạp, collection association hoặc filter bảo mật bắt buộc, hãy dùng Specification, Querydsl hoặc JPQL. Map probe từ các field được phép, xử lý primitive default cẩn thận và kiểm tra SQL thực tế để biểu mẫu tìm kiếm cho kết quả đúng và dễ bảo trì.
