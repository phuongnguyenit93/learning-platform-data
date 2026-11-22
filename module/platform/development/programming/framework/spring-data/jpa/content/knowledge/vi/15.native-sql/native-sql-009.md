# Ràng buộc tham số an toàn và tránh ghép SQL từ đầu vào

## Mục tiêu

Spring Data JPA cho phép truyền giá trị vào JPQL và native SQL thông qua bind parameter. Cách này giúp database phân biệt cấu trúc câu truy vấn với dữ liệu người dùng, tránh lỗi cú pháp do ký tự đặc biệt và ngăn SQL injection qua giá trị được bind.

Nguy cơ xuất hiện khi ứng dụng ghép trực tiếp input vào chuỗi JPQL/SQL hoặc ghép input vào các phần cấu trúc như tên cột, hướng sắp xếp và biểu thức query. Những phần cấu trúc đó không thể được bảo vệ chỉ bằng bind parameter; ứng dụng phải chọn chúng từ danh sách cho phép hoặc dùng API xây dựng query có kiểu.

Sau bài này, bạn có thể:

- Hiểu SQL injection phát sinh từ việc nối chuỗi.
- Bind tham số an toàn trong `@Query`, JPQL, native SQL và EntityManager.
- Xử lý LIKE, IN, null và collection input đúng cách.
- Xây dựng filter và sort động bằng allowlist.
- Nhận biết những thành phần query không thể bind như giá trị.
- Viết test xác nhận input được xem là dữ liệu.
- Tránh rò rỉ dữ liệu nhạy cảm qua log và thông báo lỗi.

Ví dụ sử dụng Java 17+, Spring Boot 3.x, Jakarta Persistence và Spring Data JPA.

## 1. Vì sao không được ghép input vào câu truy vấn?

Giả sử ứng dụng tìm nhân viên theo email do người dùng nhập. Cách ghép chuỗi sau không an toàn:

```java
String email = request.email();

String jpql =
        "select e from Employee e where e.email = '" + email + "'";

List<Employee> result = entityManager
        .createQuery(jpql, Employee.class)
        .getResultList();
```

Ứng dụng đã trộn cấu trúc JPQL với dữ liệu bên ngoài. Nếu input chứa dấu nháy hoặc nội dung có ý nghĩa cú pháp, nó có thể làm thay đổi câu truy vấn được thực thi. Hậu quả có thể là truy cập dữ liệu ngoài phạm vi dự kiến, bỏ qua điều kiện lọc hoặc làm hỏng câu query.

Một lỗi tương tự xảy ra với native SQL:

```java
String sql =
        "select * from employees where email = '" + email + "'";

List<?> rows = entityManager
        .createNativeQuery(sql)
        .getResultList();
```

Không nên tự escape dấu nháy bằng cách thay thế ký tự rồi tiếp tục nối chuỗi. Escape thủ công rất dễ sai khi có encoding, kiểu dữ liệu, database hoặc nhiều lớp cú pháp khác nhau. Hãy dùng bind parameter.

### 1.1. Bind parameter tách dữ liệu khỏi cấu trúc query

Query an toàn giữ nguyên cấu trúc và đặt một placeholder tại vị trí giá trị:

```java
TypedQuery<Employee> query = entityManager.createQuery(
        "select e from Employee e where e.email = :email",
        Employee.class
);

query.setParameter("email", email);

List<Employee> result = query.getResultList();
```

Database/provider nhận câu query và giá trị tham số riêng biệt. Nội dung input được xử lý như một giá trị email, không được phân tích lại thành cú pháp JPQL/SQL.

Nguyên tắc áp dụng cho cả JPQL và native SQL: không nối input vào query string; bind giá trị theo đúng kiểu dữ liệu.

## 2. Named parameter trong @Query

Với Spring Data JPA, cách dễ đọc nhất thường là named parameter, dùng dấu hai chấm trước tên tham số và liên kết bằng `@Param`.

```java
public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {

    @Query("""
           select e
           from Employee e
           where e.email = :email
           """)
    Optional<Employee> findByEmail(
            @Param("email") String email
    );
}
```

Spring Data bind giá trị của tham số Java vào placeholder `:email`. Nếu input là chuỗi có dấu nháy, dấu chấm phẩy hoặc ký tự trông giống cú pháp SQL, nó vẫn được truyền như dữ liệu của một giá trị email.

Một query có nhiều tham số:

```java
@Query("""
       select e
       from Employee e
       where e.active = :active
         and e.department.id = :departmentId
       """)
List<Employee> findByDepartmentAndStatus(
        @Param("departmentId") Long departmentId,
        @Param("active") boolean active
);
```

Tên trong `@Param` phải khớp chính xác với placeholder trong query. Dùng named parameter giúp giảm nhầm lẫn khi method có nhiều tham số hoặc thứ tự tham số thay đổi.

## 3. Positional parameter

JPQL và Spring Data JPA cũng hỗ trợ tham số theo vị trí:

```java
@Query("""
       select e
       from Employee e
       where e.email = ?1
         and e.active = ?2
       """)
List<Employee> findByEmailAndActive(
        String email,
        boolean active
);
```

Số thứ tự bắt đầu từ 1. Tham số đầu tiên là `?1`, tham số thứ hai là `?2`.

Positional parameter vẫn an toàn nếu được bind đúng cách. Tuy nhiên, với query có nhiều tham số, named parameter thường dễ đọc và bảo trì hơn.

Không trộn named parameter và positional parameter trong cùng một query. Chọn một kiểu và giữ nhất quán.

## 4. Bind tham số trong native SQL

Khi cần SQL cụ thể của database, có thể dùng `nativeQuery = true`. Giá trị vẫn phải được bind:

```java
@Query(
    value = """
            select *
            from employees
            where email = :email
            """,
    nativeQuery = true
)
Optional<Employee> findByEmailNative(
        @Param("email") String email
);
```

Query dùng tên bảng/cột của database, nhưng `:email` vẫn là bind parameter. Không thay nó bằng cách nối chuỗi.

Với EntityManager:

```java
Query query = entityManager.createNativeQuery(
        "select * from employees where email = :email",
        Employee.class
);

query.setParameter("email", email);

List<Employee> employees = query.getResultList();
```

Tên placeholder và cú pháp native query cần được kiểm thử với JPA provider/database mà ứng dụng sử dụng. Bind parameter bảo vệ giá trị; nó không làm cho native SQL tự động độc lập với database.

## 5. Những thành phần không thể bind như một giá trị

Bind parameter dùng cho giá trị dữ liệu, chẳng hạn email, ID, ngày tháng, số tiền hoặc trạng thái. Nó không thay thế được tên bảng, tên cột, từ khóa SQL, toán tử hay hướng sắp xếp.

Ví dụ sau không hoạt động như mong muốn:

```java
String column = request.sortBy();

@Query("select e from Employee e order by :column")
List<Employee> findSorted(@Param("column") String column);
```

Placeholder `:column` được hiểu là một giá trị, không phải tên thuộc tính để database sắp xếp. Query có thể sắp xếp theo cùng một giá trị hằng và không thực hiện việc chọn cột như ứng dụng mong muốn.

Tương tự, không thể bind tên bảng:

```sql
select * from :tableName
```

Nếu cần thay đổi cấu trúc query theo input, hãy dùng allowlist hoặc Criteria API/Specification/Querydsl để xây dựng biểu thức có kiểm soát.

### 5.1. Sort động bằng allowlist

Giả sử giao diện cho phép sắp xếp theo tên, email hoặc ngày tạo. Không dùng trực tiếp chuỗi client gửi làm property hay SQL expression.

```java
public enum EmployeeSortField {
    NAME,
    EMAIL,
    CREATED_AT
}
```

Chuyển lựa chọn đã xác thực sang property cố định trong code:

```java
private Sort toSort(EmployeeSortField field, Sort.Direction direction) {
    String property = switch (field) {
        case NAME -> "fullName";
        case EMAIL -> "email";
        case CREATED_AT -> "createdAt";
    };

    return Sort.by(direction, property);
}
```

Controller/service phải parse input thành enum hợp lệ; nếu giá trị không hợp lệ, trả lỗi validation hoặc dùng mặc định đã định nghĩa. Direction cũng nên giới hạn ở `ASC` hoặc `DESC` qua enum `Sort.Direction`.

Không truyền một biểu thức SQL tùy ý vào `JpaSort.unsafe` từ request. `JpaSort.unsafe` cho phép đưa expression vào ORDER BY và chỉ phù hợp với expression cố định, đáng tin cậy do lập trình viên kiểm soát.

### 5.2. Dynamic filter bằng Criteria API

Khi điều kiện lọc thay đổi theo input, không nên nối thêm đoạn JPQL bằng chuỗi. Có thể dùng Spring Data `Specification`:

```java
public interface EmployeeRepository
        extends JpaRepository<Employee, Long>,
                JpaSpecificationExecutor<Employee> {
}
```

```java
public final class EmployeeSpecifications {

    private EmployeeSpecifications() {
    }

    public static Specification<Employee> hasEmail(String email) {
        return (root, query, builder) ->
                email == null
                        ? builder.conjunction()
                        : builder.equal(root.get("email"), email);
    }

    public static Specification<Employee> isActive(Boolean active) {
        return (root, query, builder) ->
                active == null
                        ? builder.conjunction()
                        : builder.equal(root.get("active"), active);
    }
}
```

Kết hợp điều kiện:

```java
Specification<Employee> specification =
        Specification.where(EmployeeSpecifications.hasEmail(email))
                .and(EmployeeSpecifications.isActive(active));

List<Employee> employees =
        employeeRepository.findAll(specification);
```

Criteria API tạo predicate từ metadata entity và bind giá trị theo cơ chế provider. Property path trong code vẫn phải là property hợp lệ của entity; input bên ngoài không được dùng để tạo tên path tùy ý. Với nhiều lựa chọn field, hãy ánh xạ enum/allowlist sang các property cố định.

## 6. LIKE: phân biệt wildcard với SQL injection

Dùng bind parameter không có nghĩa ký tự `%` và `_` mất ý nghĩa của chúng trong toán tử LIKE. Đây là wildcard của LIKE, không phải cú pháp SQL injection:

- `%`: khớp với không hoặc nhiều ký tự.
- `_`: khớp với đúng một ký tự.

Ví dụ tìm tên có chứa keyword:

```java
@Query("""
       select e
       from Employee e
       where lower(e.fullName) like lower(concat('%', :keyword, '%'))
       """)
List<Employee> searchByName(
        @Param("keyword") String keyword
);
```

Query này an toàn trước việc input biến thành cú pháp SQL vì giá trị được bind. Tuy nhiên, nếu người dùng nhập `%`, kết quả có thể khớp gần như mọi tên. Đây là khác biệt về semantics tìm kiếm, không phải SQL injection.

### 6.1. Tìm chuỗi literal và escape wildcard

Nếu yêu cầu là tìm đúng ký tự phần trăm hoặc gạch dưới như văn bản, hãy escape wildcard. Ví dụ chọn ký tự `!` làm escape character:

```java
private String escapeLike(String value) {
    return value
            .replace("!", "!!")
            .replace("%", "!%")
            .replace("_", "!_");
}
```

Escape ký tự escape trước, sau đó escape hai wildcard. Query JPQL:

```java
@Query("""
       select e
       from Employee e
       where lower(e.fullName) like lower(:pattern) escape '!'
       """)
List<Employee> searchNameLiteral(
        @Param("pattern") String pattern
);
```

Gọi repository:

```java
String pattern = "%" + escapeLike(keyword) + "%";
List<Employee> result = repository.searchNameLiteral(pattern);
```

Bind parameter bảo vệ cấu trúc query; escape LIKE bảo đảm ký tự wildcard được xem là văn bản theo yêu cầu tìm kiếm. Hai việc này giải quyết hai vấn đề khác nhau.

Cú pháp escape và collation có thể khác theo database/provider. Hãy có integration test với database đích, đặc biệt khi ứng dụng hỗ trợ Unicode hoặc tìm kiếm không phân biệt dấu/hoa thường.

## 7. Truyền collection vào IN

Có thể bind một collection vào điều kiện IN:

```java
@Query("""
       select e
       from Employee e
       where e.id in :ids
       """)
List<Employee> findAllByIds(@Param("ids") Collection<Long> ids);
```

Spring Data/JPA provider mở rộng collection thành các giá trị bind tương ứng. Không tự nối danh sách ID thành chuỗi SQL:

```java
// Không an toàn và dễ lỗi:
String sql = "select * from employees where id in (" +
        ids.stream().map(String::valueOf)
                .collect(Collectors.joining(",")) + ")";
```

Hãy xử lý collection rỗng ở tầng service:

```java
public List<Employee> findEmployees(Collection<Long> ids) {
    if (ids == null || ids.isEmpty()) {
        return List.of();
    }

    return repository.findAllByIds(ids);
}
```

Cách xử lý rỗng phải theo nghiệp vụ. Với truy vấn “lấy các ID được chọn”, trả danh sách rỗng thường hợp lý. Với nghiệp vụ khác, có thể trả validation error. Không giả định mọi provider/database xử lý `IN ()` giống nhau.

Với danh sách rất lớn, cần xem giới hạn số bind parameter của database và driver. Có thể chia batch, dùng temporary table, table-valued parameter hoặc cơ chế database phù hợp.

## 8. Null và tham số tùy chọn

Trong SQL/JPQL, so sánh bằng null không hoạt động như so sánh giá trị thông thường. Biểu thức:

```sql
e.departmentId = :departmentId
```

khi `:departmentId` là null sẽ không tự chuyển thành `IS NULL`. Kết quả điều kiện thường là UNKNOWN và không khớp hàng nào.

Nếu null có nghĩa “bỏ qua bộ lọc”, có thể viết rõ:

```java
@Query("""
       select e
       from Employee e
       where (:active is null or e.active = :active)
       """)
List<Employee> findByOptionalActive(
        @Param("active") Boolean active
);
```

Nếu null có nghĩa “tìm những hàng có cột null”, dùng điều kiện rõ ràng:

```java
@Query("""
       select e
       from Employee e
       where (:departmentId is null and e.department is null)
          or e.department.id = :departmentId
       """)
List<Employee> findByDepartmentOrWithoutDepartment(
        @Param("departmentId") Long departmentId
);
```

Hãy xác định semantics của null trước khi viết query:

- Null nghĩa là không áp dụng filter?
- Null nghĩa là tìm cột đang null?
- Null không hợp lệ và phải bị từ chối?

Với nhiều filter tùy chọn, Specification/Criteria API thường dễ đọc hơn một query dài chứa nhiều điều kiện `(:x is null or ...)`.

## 9. UPDATE/DELETE cũng phải bind parameter

`@Modifying` không làm mất yêu cầu bind parameter. Ví dụ update trạng thái theo ID:

```java
@Modifying
@Query("""
       update Employee e
       set e.active = :active
       where e.id = :id
       """)
int updateActive(
        @Param("id") Long id,
        @Param("active") boolean active
);
```

Service gọi trong transaction:

```java
@Transactional
public void deactivate(Long id) {
    int updated = repository.updateActive(id, false);

    if (updated == 0) {
        throw new IllegalArgumentException("Employee not found");
    }
}
```

Không ghép ID hoặc giá trị trạng thái vào chuỗi JPQL. Ngoài bảo vệ injection, bind parameter còn giúp provider xử lý đúng kiểu dữ liệu và giảm lỗi định dạng ngày, số hoặc ký tự.

Bulk UPDATE/DELETE có thể làm entity đã managed trong persistence context giữ dữ liệu cũ. Nếu cần, dùng `flushAutomatically` và `clearAutomatically` có chủ đích; đây là vấn đề đồng bộ persistence context, tách biệt với việc bind parameter.

## 10. SpEL trong @Query: dùng có giới hạn

Spring Data JPA hỗ trợ một số biểu thức SpEL trong query. Ví dụ `#{#entityName}` giúp tái sử dụng entity name:

```java
@NoRepositoryBean
public interface BaseRepository<T, ID>
        extends Repository<T, ID> {

    @Query("""
           select e
           from #{#entityName} e
           where e.id = :id
           """)
    Optional<T> findOneById(@Param("id") ID id);
}
```

`#entityName` lấy metadata entity do Spring Data quản lý; nó không phải chuỗi input tùy ý từ request.

Một số query expression có thể tham chiếu tham số method. Dù vậy, không biến input người dùng thành một đoạn query expression, tên property, ORDER BY hoặc SQL fragment. Hãy giữ query template trong source code và truyền giá trị qua bind parameter.

Nếu cần chọn cấu trúc query động, dùng allowlist hoặc Criteria/Specification/Querydsl. Không đánh giá hoặc thực thi biểu thức query do client gửi.

## 11. Giới hạn của bind parameter và allowlist

Bind parameter chỉ thay thế một giá trị tại vị trí hợp lệ của query. Không thể dùng nó để thay thế:

- Tên bảng hoặc tên schema.
- Tên cột hoặc tên thuộc tính.
- Từ khóa SELECT, WHERE, GROUP BY, ORDER BY.
- Toán tử hoặc biểu thức SQL.
- Hướng sắp xếp ASC/DESC.
- Một đoạn JOIN hoặc điều kiện tùy ý.

Nếu nghiệp vụ cần lựa chọn bảng hoặc cột, hãy ánh xạ lựa chọn thành một trong các giá trị cố định do ứng dụng định nghĩa. Không cho phép client gửi tên SQL tự do.

Ví dụ allowlist cho báo cáo:

```java
public enum ReportColumn {
    EMAIL,
    FULL_NAME,
    CREATED_AT
}

private String columnFor(ReportColumn column) {
    return switch (column) {
        case EMAIL -> "email";
        case FULL_NAME -> "full_name";
        case CREATED_AT -> "created_at";
    };
}
```

Nếu buộc phải tạo native SQL động, chỉ ghép các identifier đã được ánh xạ từ enum/allowlist cố định; tất cả dữ liệu vẫn truyền bằng bind parameter. Cần kiểm tra kỹ quyền truy cập để người dùng không chọn được cột nhạy cảm ngoài phạm vi.

## 12. Logging và xử lý lỗi

Bind parameter bảo vệ câu query ở thời điểm thực thi, nhưng log có thể làm lộ dữ liệu nhạy cảm nếu ghi toàn bộ tham số.

Thực hành tốt:

- Không log mật khẩu, token, số thẻ đầy đủ hoặc dữ liệu cá nhân không cần thiết.
- Nếu cần trace, log query name, request ID và metadata đã được làm sạch.
- Không trả nguyên câu SQL, stack trace hoặc thông tin schema nội bộ cho client.
- Không đưa input chưa làm sạch vào log theo cách có thể tạo log injection hoặc phá cấu trúc log.
- Giới hạn quyền truy cập log và thời gian lưu theo chính sách hệ thống.

Khi query thất bại, ghi nhận loại lỗi và ngữ cảnh cần thiết ở server. Client nhận thông báo nghiệp vụ phù hợp, ví dụ “bộ lọc không hợp lệ”, thay vì nội dung exception/database.

## 13. Kiểm thử an toàn tham số

Test nên xác nhận input đặc biệt được xem là dữ liệu và không làm thay đổi cấu trúc query.

Ví dụ với repository tìm email:

```java
@DataJpaTest
class EmployeeRepositorySecurityTest {

    @Autowired
    private EmployeeRepository repository;

    @Test
    void treatsSpecialCharactersAsParameterValue() {
        repository.save(new Employee(
                "An",
                "an@example.com",
                true
        ));

        String input = "' OR '1'='1";

        Optional<Employee> result = repository.findByEmail(input);

        assertThat(result).isEmpty();
    }
}
```

Test này giả định repository dùng `@Query` named parameter như phần trước. Input được truyền như một giá trị email; nó không thể biến thành điều kiện OR của JPQL.

Nên bổ sung các test:

- Dấu nháy đơn, dấu nháy kép, dấu gạch chéo và ký tự Unicode.
- Chuỗi chứa `%` và `_` với tìm kiếm LIKE literal.
- Collection rỗng và collection lớn cho IN.
- Tham số null theo đúng semantics nghiệp vụ.
- Sort field không nằm trong allowlist phải bị từ chối.
- Native query chạy trên database thực tế.
- Update/delete có bind parameter và transaction đúng.

Embedded database có thể khác PostgreSQL/MySQL về cú pháp native SQL, collation, giới hạn bind parameter và kiểu dữ liệu. Với query quan trọng, hãy chạy integration test trên cùng loại database với môi trường triển khai, ví dụ bằng Testcontainers.

## 14. Ví dụ service hoàn chỉnh với filter và sort an toàn

```java
@Service
public class EmployeeSearchService {

    private final EmployeeRepository repository;

    public EmployeeSearchService(EmployeeRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public Page<Employee> search(
            String email,
            Boolean active,
            EmployeeSortField sortField,
            Sort.Direction direction,
            int page,
            int size
    ) {
        if (page < 0) {
            throw new IllegalArgumentException("Page must be >= 0");
        }

        if (size < 1 || size > 100) {
            throw new IllegalArgumentException("Page size must be 1..100");
        }

        String property = switch (sortField) {
            case NAME -> "fullName";
            case EMAIL -> "email";
            case CREATED_AT -> "createdAt";
        };

        Sort sort = Sort.by(direction, property);
        Pageable pageable = PageRequest.of(page, size, sort);

        Specification<Employee> spec =
                Specification.where(EmployeeSpecifications.hasEmail(email))
                        .and(EmployeeSpecifications.isActive(active));

        return repository.findAll(spec, pageable);
    }
}
```

Ví dụ cho thấy ba ranh giới:

- Giá trị lọc email/active được tạo thành predicate và bind bởi Criteria API.
- Field sắp xếp được ánh xạ từ enum sang property cố định.
- Page và size được kiểm tra giới hạn trước khi tạo Pageable.

Trong ứng dụng thực tế, cần xử lý null của `sortField` và `direction` theo validation hoặc giá trị mặc định. Không nhận tên property tự do rồi truyền thẳng vào Sort.

## 15. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Query bị thay đổi khi input có dấu nháy | Nối input trực tiếp vào JPQL/SQL | Dùng named/positional bind parameter |
| ORDER BY không sắp xếp theo cột client chọn | Dùng placeholder cho tên cột | Ánh xạ field qua allowlist |
| LIKE trả về quá nhiều kết quả | Input chứa % hoặc _ là wildcard | Escape wildcard nếu cần tìm literal |
| IN lỗi với danh sách rỗng | Provider/database xử lý IN rỗng khác nhau | Xử lý collection rỗng ở service |
| = null không trả kết quả | SQL/JPQL dùng logic ba giá trị | Dùng IS NULL hoặc điều kiện optional rõ ràng |
| Native query không bind được tham số | Placeholder hoặc provider syntax không phù hợp | Kiểm tra named/positional syntax theo provider |
| Dynamic SQL có thể bị injection | Ghép identifier hoặc fragment từ input | Allowlist identifier, bind mọi giá trị |
| Dữ liệu nhạy cảm xuất hiện trong log | Log toàn bộ bind parameter | Mask/redact và giới hạn log |
| Sort/filter gây query quá nặng | Không giới hạn field, page size hoặc filter | Allowlist, validate và giới hạn tài nguyên |

## 16. Checklist trước khi đưa query vào production

- [ ] Không nối input người dùng vào JPQL, SQL hoặc query fragment.
- [ ] Dùng named parameter với @Param hoặc positional parameter.
- [ ] Bind đúng kiểu dữ liệu cho ID, ngày, số và trạng thái.
- [ ] Xử lý wildcard LIKE riêng nếu cần tìm chuỗi literal.
- [ ] Xử lý collection rỗng trước IN.
- [ ] Xác định semantics của tham số null.
- [ ] Không dùng bind parameter để thay tên bảng/cột hoặc ORDER BY.
- [ ] Ánh xạ sort/filter động qua enum hoặc allowlist.
- [ ] Giới hạn page size và số lượng giá trị IN.
- [ ] Không log secret hoặc toàn bộ dữ liệu nhạy cảm.
- [ ] Kiểm thử input đặc biệt và native query trên database đích.

## Kết luận

Bind parameter là cách chuẩn để truyền giá trị vào JPQL và native SQL. Nó giữ input ở vai trò dữ liệu, giúp ngăn SQL injection do nối chuỗi và xử lý đúng kiểu giá trị. Tuy nhiên, bind parameter không thay thế được tên bảng, cột, từ khóa hoặc biểu thức động.

Giữ query template cố định, bind mọi giá trị, dùng allowlist cho cấu trúc query động và kiểm thử các trường hợp đặc biệt. Kết hợp các nguyên tắc này với validation, giới hạn tài nguyên và logging an toàn giúp repository chống injection và dễ bảo trì.
