# Sắp xếp theo biểu thức và rủi ro của JpaSort.unsafe

## Mục tiêu

Spring Data JPA cho phép sắp xếp kết quả bằng `Sort` và `Pageable`. Với thuộc tính entity thông thường, có thể dùng `Sort.by("fullName")`. Tuy nhiên, một số yêu cầu cần sắp xếp theo biểu thức như chuyển chữ về chữ thường, tính độ dài chuỗi hoặc một biểu thức JPQL khác. Spring Data JPA cung cấp `JpaSort.unsafe` để truyền các biểu thức sắp xếp như vậy.

`JpaSort.unsafe` bỏ qua bước kiểm tra thông thường đối với tên thuộc tính. Vì biểu thức được đưa vào phần ORDER BY của query, không được lấy biểu thức tùy ý từ request hoặc nối trực tiếp input người dùng vào nó. Cách an toàn là giữ biểu thức trong source code và chọn qua allowlist.

Sau bài này, bạn có thể:

- Phân biệt sắp xếp theo property với sắp xếp theo expression.
- Hiểu cách Spring Data JPA áp dụng Sort vào JPQL query.
- Dùng `JpaSort.unsafe` cho biểu thức cố định do ứng dụng kiểm soát.
- Nhận diện nguy cơ injection khi tạo sort động.
- Xây dựng allowlist cho field và direction.
- Kết hợp expression sort với Pageable và phân trang ổn định.
- Hiểu giới hạn với native query, database và index.
- Kiểm thử query, thứ tự kết quả và các trường hợp đầu vào không hợp lệ.

Ví dụ sử dụng Java 17+, Spring Boot 3.x, Jakarta Persistence và Spring Data JPA.

## 1. Sort thông thường hoạt động như thế nào?

Spring Data JPA cho phép truyền `Sort` vào repository method:

```java
Sort sort = Sort.by(Sort.Direction.ASC, "fullName");
List<Employee> employees = employeeRepository.findAll(sort);
```

Tên property trong `Sort` là thuộc tính Java của entity, không phải tên cột SQL. Nếu entity có:

```java
@Column(name = "full_name")
private String fullName;
```

thì dùng `fullName`, không dùng `full_name`.

Với query khai báo bằng `@Query`, Spring Data JPA bổ sung điều kiện sắp xếp vào query. Ví dụ:

```java
@Query("""
       select e
       from Employee e
       where e.active = true
       """)
List<Employee> findActiveEmployees(Sort sort);
```

Gọi:

```java
List<Employee> employees = repository.findActiveEmployees(
        Sort.by(Sort.Direction.ASC, "fullName")
);
```

Spring Data kiểm tra đường dẫn sắp xếp có hợp lệ theo property của domain model hoặc alias được query khai báo hay không. Nếu property không tồn tại, query có thể bị từ chối thay vì chèn một biểu thức tùy ý vào ORDER BY.

### 1.1. Sắp xếp theo nhiều thuộc tính

Có thể kết hợp nhiều tiêu chí:

```java
Sort sort = Sort.by(
        Sort.Order.asc("department.name"),
        Sort.Order.asc("fullName"),
        Sort.Order.desc("id")
);
```

Thứ tự ưu tiên từ trái sang phải: department.name trước, fullName tiếp theo, rồi id. Đường dẫn lồng nhau như `department.name` phải tương ứng với association và property hợp lệ trong entity.

Khi phân trang, nên có tiêu chí cuối cùng đủ phân biệt các hàng, thường là primary key. Điều này giúp thứ tự ổn định hơn khi nhiều bản ghi có cùng tên hoặc cùng thời điểm.

### 1.2. Sắp xếp theo alias của query

Với JPQL projection, một alias được chọn có thể được dùng trong Sort nếu Spring Data nhận diện alias đó:

```java
@Query("""
       select e.id as employeeId,
              lower(e.fullName) as normalizedName
       from Employee e
       where e.active = true
       """)
List<Object[]> findActiveNames(Sort sort);
```

Ví dụ query có alias `normalizedName`. Việc dùng alias phụ thuộc kiểu query, parser và cách khai báo kết quả. Với DTO constructor expression, không phải mọi alias đều có thể dùng như property của entity. Hãy kiểm tra query được sinh và kiểu kết quả thực tế.

## 2. Vì sao cần sắp xếp theo biểu thức?

Sắp xếp theo property phù hợp khi tiêu chí tương ứng trực tiếp với một thuộc tính entity. Nhưng đôi khi nghiệp vụ yêu cầu sắp xếp theo một phép biến đổi:

- Không phân biệt chữ hoa/chữ thường: `LOWER(e.fullName)`.
- Theo độ dài tên: `LENGTH(e.fullName)`.
- Theo một biểu thức CASE để ưu tiên trạng thái.
- Theo một phép tính trên nhiều thuộc tính.
- Theo hàm database hoặc JPQL mà query sử dụng.

Ví dụ, nếu dùng:

```java
Sort.by(Sort.Direction.ASC, "LOWER(fullName)")
```

Spring Data thường coi toàn bộ chuỗi là một property path và từ chối vì `LOWER(fullName)` không phải thuộc tính entity. Cơ chế kiểm tra này bảo vệ query khỏi việc chèn biểu thức tùy ý.

Khi biểu thức đã được lập trình viên viết cố định và kiểm tra, có thể dùng `JpaSort.unsafe` để báo cho Spring Data rằng đây là expression được chủ động cho phép.

## 3. JpaSort.unsafe là gì?

`JpaSort.unsafe` là API của Spring Data JPA để tạo một Sort chứa biểu thức ORDER BY không được kiểm tra như property path thông thường.

Ví dụ:

```java
JpaSort sort = JpaSort.unsafe(
        Sort.Direction.ASC,
        "LOWER(e.fullName)"
);
```

Dùng trong repository có JPQL alias `e`:

```java
public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {

    @Query("""
           select e
           from Employee e
           where e.active = true
           """)
    List<Employee> findActiveEmployees(Sort sort);
}
```

Gọi:

```java
List<Employee> employees = repository.findActiveEmployees(
        JpaSort.unsafe(
                Sort.Direction.ASC,
                "LOWER(e.fullName)"
        )
);
```

Spring Data thêm biểu thức vào ORDER BY của JPQL. Provider chuyển query thành SQL phù hợp với database.

### 3.1. Các overload thường dùng

Có thể tạo unsafe sort theo một hoặc nhiều expression:

```java
JpaSort.unsafe("LENGTH(e.fullName)");

JpaSort.unsafe(
        Sort.Direction.DESC,
        "LENGTH(e.fullName)"
);

JpaSort.unsafe(
        Sort.Direction.ASC,
        "LOWER(e.fullName)",
        "e.id"
);
```

Tên và overload cụ thể cần đối chiếu với version Spring Data JPA của dự án. `JpaSort.unsafe` trả về một đối tượng Sort có thể truyền vào repository method nhận `Sort` hoặc kết hợp với Pageable.

Không đưa một chuỗi đã chứa nguyên câu `ORDER BY` vào tham số expression. Truyền expression hợp lệ theo cú pháp query và để Spring Data xây dựng phần sắp xếp.

### 3.2. Unsafe không có nghĩa là bỏ qua mọi quy tắc query

`JpaSort.unsafe` bỏ qua kiểm tra property path an toàn của Spring Data đối với expression. Nó không biến một expression bất kỳ thành cú pháp hợp lệ trong mọi trường hợp.

Expression vẫn phải phù hợp với query được thực thi:

- JPQL expression phải hợp lệ theo JPQL/provider.
- Alias phải tồn tại trong query.
- Property phải tồn tại trên entity hoặc subtype được tham chiếu.
- Hàm phải được JPA provider/database hỗ trợ.
- Native query cần cú pháp SQL phù hợp với database.

Ví dụ `LOWER(e.fullName)` phù hợp với JPQL khi alias `e` và property `fullName` tồn tại. Một hàm riêng của PostgreSQL không nhất thiết chạy được trên MySQL hoặc trên JPQL provider khác.

## 4. Rủi ro khi dùng JpaSort.unsafe với input bên ngoài

Điểm nguy hiểm không nằm ở việc dùng một expression cố định. Rủi ro xuất hiện khi lấy expression từ người dùng hoặc ghép chuỗi request vào query.

Ví dụ không an toàn:

```java
String requestedSort = request.getSortExpression();

Sort sort = JpaSort.unsafe(
        Sort.Direction.ASC,
        requestedSort
);

return repository.findActiveEmployees(sort);
```

Client có thể gửi một expression không nằm trong dự kiến. Vì unsafe sort bỏ qua kiểm tra property path thông thường, expression đó có thể làm query lỗi, truy cập dữ liệu theo cách ngoài dự kiến hoặc chèn cú pháp không mong muốn vào ORDER BY tùy query/provider.

Một ví dụ nguy hiểm khác là tự ghép direction:

```java
String direction = request.getDirection();
String expression = request.getSortExpression();

String jpql = "select e from Employee e order by "
        + expression + " " + direction;
```

Cả expression và direction đều là phần cấu trúc query. Không thể bảo vệ chúng bằng cách bind parameter như một giá trị thông thường.

### 4.1. Bind parameter không thể thay tên cột hoặc expression

Bind parameter dùng cho giá trị:

```java
@Query("""
       select e
       from Employee e
       where e.email = :email
       """)
List<Employee> findByEmail(@Param("email") String email);
```

Không thể viết:

```java
order by :sortExpression
```

rồi kỳ vọng giá trị của `:sortExpression` được diễn giải thành tên cột hoặc hàm. Database xem nó là giá trị, không phải cấu trúc ORDER BY.

Do đó, dynamic sorting phải được kiểm soát bằng allowlist, enum hoặc mapping cố định trong code.

### 4.2. Sort.by cũng không phải nơi nhận chuỗi SQL tùy ý

Với property path thông thường, `Sort.by` được Spring Data kiểm tra theo domain property/query alias. Dùng `Sort.by` không phải cách để thực thi expression như `LOWER(e.fullName)`; thường nó sẽ bị coi là tên property và có thể bị từ chối.

Không chuyển sang `JpaSort.unsafe` chỉ để làm cho một chuỗi client gửi vào “chạy được”. Nếu biểu thức cần thiết, lập trình viên phải định nghĩa trước những expression được phép.

## 5. Allowlist cho sắp xếp động

Cách an toàn là để client chọn một lựa chọn nghiệp vụ có tên rõ ràng, sau đó server ánh xạ lựa chọn đó thành property hoặc expression cố định.

### 5.1. Khai báo enum cho field được phép

```java
public enum EmployeeSortField {
    NAME,
    EMAIL,
    CREATED_AT
}
```

Controller/service parse input thành enum. Nếu giá trị không hợp lệ, trả lỗi validation hoặc dùng giá trị mặc định đã công bố. Không giữ chuỗi tự do từ request làm expression.

### 5.2. Ánh xạ enum sang Sort

Giả sử repository query sử dụng alias `e`:

```java
public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {

    @Query("""
           select e
           from Employee e
           where e.active = true
           """)
    Page<Employee> findActiveEmployees(Pageable pageable);
}
```

Service xây dựng sort:

```java
@Service
public class EmployeeSearchService {

    private final EmployeeRepository repository;

    public EmployeeSearchService(EmployeeRepository repository) {
        this.repository = repository;
    }

    public Page<Employee> search(
            EmployeeSortField field,
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

        Sort sort = switch (field) {
            case NAME -> JpaSort.unsafe(
                    direction,
                    "LOWER(e.fullName)"
            );
            case EMAIL -> JpaSort.unsafe(
                    direction,
                    "LOWER(e.email)"
            );
            case CREATED_AT -> Sort.by(
                    direction,
                    "createdAt"
            );
        };

        // Thêm ID làm tiêu chí cuối để ổn định thứ tự khi phân trang.
        sort = sort.and(Sort.by(direction, "id"));

        Pageable pageable = PageRequest.of(page, size, sort);
        return repository.findActiveEmployees(pageable);
    }
}
```

Trong ví dụ:

- `NAME` ánh xạ tới expression cố định `LOWER(e.fullName)`.
- `EMAIL` ánh xạ tới expression cố định `LOWER(e.email)`.
- `CREATED_AT` dùng property path bình thường `createdAt`.
- `direction` là enum `Sort.Direction`, chỉ có ASC hoặc DESC.
- `id` là tie-breaker để các hàng có cùng giá trị sort chính vẫn có thứ tự xác định.

Client không thể gửi một expression JPQL mới. Nó chỉ chọn một trong những giá trị enum mà server cho phép.

Trong code thực tế, cần xử lý cả trường hợp `field` hoặc `direction` null. Có thể dùng default rõ ràng hoặc trả lỗi validation trước khi gọi repository.

### 5.3. Nếu chỉ cần property thông thường

Không cần dùng unsafe cho mọi field. Với property path đã được mapping, ưu tiên:

```java
Sort sort = Sort.by(direction, "createdAt")
        .and(Sort.by(direction, "id"));
```

Chỉ dùng `JpaSort.unsafe` cho expression thực sự cần thiết như hàm hoặc phép tính. Giữ phần lớn lựa chọn sort ở dạng property thông thường làm code dễ kiểm tra hơn.

## 6. Expression thường gặp

### 6.1. Không phân biệt chữ hoa/chữ thường

```java
JpaSort.unsafe(
        Sort.Direction.ASC,
        "LOWER(e.fullName)"
);
```

Query sắp xếp theo kết quả của `LOWER`. Giá trị gốc trong entity không bị thay đổi; đây chỉ là biểu thức ORDER BY.

Nếu database có collation không phân biệt hoa thường, có thể cân nhắc dùng collation hoặc cấu hình cột phù hợp thay vì áp dụng hàm cho mọi hàng. Việc gọi hàm trên cột có thể làm database khó sử dụng index B-tree thông thường, trừ khi có functional index hoặc index phù hợp.

### 6.2. Sắp xếp theo độ dài chuỗi

```java
JpaSort.unsafe(
        Sort.Direction.DESC,
        "LENGTH(e.fullName)"
);
```

Expression `LENGTH` là hàm JPQL chuẩn. Cần kiểm tra provider và database xử lý ký tự Unicode/độ dài chuỗi theo đúng semantics mong muốn. Với một số database, độ dài ký tự và độ dài byte là hai khái niệm khác nhau.

### 6.3. Sắp xếp theo điều kiện CASE

Có thể ưu tiên một nhóm trạng thái:

```java
JpaSort.unsafe(
        Sort.Direction.ASC,
        "CASE WHEN e.active = true THEN 0 ELSE 1 END"
);
```

CASE expression phải hợp lệ theo JPQL/provider và cần giữ cố định trong code. Nếu nghiệp vụ chỉ cần một thứ tự trạng thái đơn giản, hãy cân nhắc lưu thứ tự bằng một thuộc tính domain hoặc dùng sort theo property để giảm phụ thuộc expression.

### 6.4. Kết hợp expression và property

```java
Sort sort = JpaSort.unsafe(
        Sort.Direction.ASC,
        "LOWER(e.fullName)"
).and(
        Sort.by(Sort.Direction.ASC, "id")
);
```

Kết quả sắp xếp theo tên đã chuẩn hóa trước, rồi theo ID. Điều này giúp phân trang có thứ tự xác định khi nhiều người trùng tên.

## 7. Pageable và phân trang ổn định

Có thể truyền unsafe Sort thông qua Pageable:

```java
Sort sort = JpaSort.unsafe(
        Sort.Direction.ASC,
        "LOWER(e.fullName)"
).and(Sort.by("id"));

Pageable pageable = PageRequest.of(0, 20, sort);

Page<Employee> result =
        employeeRepository.findActiveEmployees(pageable);
```

`Pageable` mang cả số trang, kích thước trang và Sort. Spring Data áp dụng chúng khi thực thi repository method.

### 7.1. Vì sao cần tie-breaker?

Giả sử 100 nhân viên có cùng fullName sau khi chuyển về chữ thường. Nếu chỉ sort theo `LOWER(e.fullName)`, database không có nghĩa vụ trả các hàng bằng nhau theo một thứ tự cố định.

Khi đọc page 0 rồi page 1, các hàng có cùng giá trị sort có thể đổi vị trí giữa các lần thực thi, nhất là khi dữ liệu được thêm hoặc cập nhật đồng thời. Có thể xuất hiện bản ghi lặp hoặc bị bỏ qua giữa các trang.

Thêm primary key làm tiêu chí cuối:

```java
Sort sort = JpaSort.unsafe(
        Sort.Direction.ASC,
        "LOWER(e.fullName)"
).and(Sort.by(Sort.Direction.ASC, "id"));
```

Tie-breaker giúp thứ tự xác định với cùng một snapshot dữ liệu. Nó không loại bỏ mọi thay đổi do transaction khác ghi đồng thời. Với tập dữ liệu thay đổi liên tục hoặc phân trang sâu, hãy cân nhắc keyset/scrolling theo version Spring Data đang dùng.

### 7.2. Sort động và count query

Khi repository trả `Page<T>`, Spring Data có thể chạy query lấy nội dung và count query. Sort áp dụng cho query nội dung; count query chỉ cần đếm và không cần ORDER BY thông thường.

Nếu query có JOIN phức tạp hoặc projection, khai báo `countQuery` phù hợp. Không cố đưa expression sắp xếp vào count query nếu nó không phục vụ việc đếm.

## 8. Alias và phạm vi của expression

Expression unsafe thường được chèn vào query do repository khai báo. Vì vậy alias trong expression phải khớp alias của query.

Ví dụ:

```java
@Query("""
       select e
       from Employee e
       where e.active = true
       """)
Page<Employee> findActive(Pageable pageable);
```

Sort expression dùng alias `e`:

```java
JpaSort.unsafe("LOWER(e.fullName)")
```

Nếu query đổi alias từ `e` thành `employee`, expression cũng phải đổi. Một expression dùng alias sai có thể khiến query lỗi khi thực thi.

Không dùng một expression gắn với alias cụ thể cho nhiều repository query có alias khác nhau. Hãy giữ mapping sort gần repository method mà nó phục vụ hoặc đóng gói thành hàm có tên rõ ràng.

## 9. Native query và giới hạn tương thích

Với native SQL, ORDER BY sử dụng tên cột, alias SQL và hàm của database, không phải JPQL entity property.

Ví dụ native query:

```java
@Query(
    value = """
            select *
            from employees
            where active = true
            """,
    countQuery = """
            select count(*)
            from employees
            where active = true
            """,
    nativeQuery = true
)
Page<Employee> findActiveNative(Pageable pageable);
```

Khả năng Spring Data phân tích và thêm Sort vào native query phụ thuộc version, parser và độ phức tạp của SQL. Một số query native phức tạp không thể tự động chỉnh sửa an toàn để thêm sort.

Không giả định expression JPQL như `LOWER(e.fullName)` có thể dùng nguyên văn trong native SQL. Native query có thể cần `LOWER(full_name)` hoặc cú pháp khác theo database.

Nếu cần native sorting:

- Chỉ cho phép một tập cột/biểu thức đã định nghĩa trước.
- Dùng đúng tên cột/alias SQL.
- Kiểm tra khả năng dynamic sorting của Spring Data version đang triển khai.
- Với query phức tạp, viết các query/ORDER BY cố định hoặc custom repository có mapping allowlist.
- Chạy integration test trên đúng database và driver.

## 10. Hiệu năng của expression sort

Sắp xếp theo expression có thể khiến database phải tính biểu thức cho nhiều hàng trước khi xác định thứ tự. Ví dụ `ORDER BY LOWER(full_name)` có thể không tận dụng index thông thường trên `full_name`.

Các hướng tối ưu:

- Đo query bằng execution plan và dữ liệu gần production.
- Tạo functional index nếu database hỗ trợ và biểu thức được dùng thường xuyên.
- Cân nhắc cột chuẩn hóa được cập nhật theo quy tắc domain.
- Giới hạn kết quả và phân trang.
- Lọc trước bằng điều kiện có index phù hợp.
- Tránh nhiều expression phức tạp trong cùng ORDER BY nếu không cần.

Không thêm index chỉ vì có expression. Index có chi phí ghi, dung lượng và bảo trì. Hãy căn cứ vào query plan, tần suất truy vấn và phân bố dữ liệu.

## 11. Kiểm thử sắp xếp an toàn

Nên kiểm tra thứ tự thực tế, không chỉ xác nhận repository không ném exception.

Ví dụ repository:

```java
public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {

    @Query("""
           select e
           from Employee e
           where e.active = true
           """)
    List<Employee> findActiveEmployees(Sort sort);
}
```

Test:

```java
@DataJpaTest
class EmployeeSortTest {

    @Autowired
    private EmployeeRepository repository;

    @Test
    void sortsNamesWithoutCaseSensitivity() {
        repository.save(new Employee("bravo", "b@example.com", true));
        repository.save(new Employee("Alpha", "a@example.com", true));
        repository.save(new Employee("charlie", "c@example.com", true));

        Sort sort = JpaSort.unsafe(
                Sort.Direction.ASC,
                "LOWER(e.fullName)"
        ).and(Sort.by(Sort.Direction.ASC, "id"));

        List<Employee> result = repository.findActiveEmployees(sort);

        assertThat(result)
                .extracting(Employee::getFullName)
                .containsExactly("Alpha", "bravo", "charlie");
    }
}
```

Test giả định Employee có constructor và getter như trong ví dụ, repository sử dụng JPQL alias `e`, và có các dependency JUnit 5, AssertJ, Spring Boot JPA test support. `@DataJpaTest` thường chạy trong transaction và rollback sau test.

Cần bổ sung test cho:

- Mỗi enum sort field được phép.
- ASC và DESC.
- Hai hoặc nhiều hàng có cùng giá trị sort chính.
- Page boundary khi sort có tie-breaker.
- Field không nằm trong allowlist bị từ chối trước khi gọi repository.
- Alias thay đổi hoặc expression không hợp lệ gây lỗi trong test.
- Native query sorting trên database đích nếu ứng dụng sử dụng native query.

Không nên kiểm thử injection bằng cách cho phép request truyền expression độc hại rồi chạy trực tiếp vào database. Hãy test rằng input không nằm trong enum/allowlist bị từ chối và repository chỉ nhận expression cố định.

## 12. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Property sort không hợp lệ | Dùng tên cột SQL thay cho property Java | Dùng property entity, ví dụ fullName |
| LOWER(...) bị từ chối với Sort.by | Spring Data coi expression là property path | Chỉ dùng JpaSort.unsafe cho expression cố định |
| Query lỗi không nhận alias | Expression tham chiếu alias không tồn tại | Khớp alias với @Query |
| Request có thể thay đổi ORDER BY | Truyền trực tiếp input vào JpaSort.unsafe | Dùng enum/allowlist ánh xạ expression |
| Direction không hợp lệ | Nhận chuỗi ASC/DESC tự do | Parse thành Sort.Direction và validate |
| Trang có bản ghi lặp hoặc thiếu | Sort không có tie-breaker hoặc dữ liệu đổi giữa các lần đọc | Thêm ID vào cuối sort; cân nhắc keyset pagination |
| Native query không thêm được sort | SQL phức tạp hoặc parser không hỗ trợ | Dùng ORDER BY cố định/custom repository và test trên DB đích |
| Query chậm sau khi thêm LOWER | Database khó dùng index thường | Xem execution plan, functional index hoặc cột chuẩn hóa |
| Expression chạy trên DB này nhưng lỗi DB khác | Hàm/cú pháp phụ thuộc provider/database | Ưu tiên JPQL chuẩn hoặc test từng database |
| Sort gây lỗi ở count query | Query phân trang hoặc count query cấu hình không phù hợp | Kiểm tra query content và countQuery riêng |

## 13. Checklist dùng JpaSort.unsafe

- [ ] Chỉ dùng khi cần expression, không dùng thay cho Sort.by thông thường.
- [ ] Expression được viết cố định trong source code.
- [ ] Không truyền raw sort expression từ request, header hoặc query parameter.
- [ ] Dùng enum/allowlist để ánh xạ lựa chọn client thành expression đã duyệt.
- [ ] Direction được parse thành Sort.Direction.
- [ ] Alias trong expression khớp JPQL query.
- [ ] Hàm và cú pháp được provider/database hỗ trợ.
- [ ] Thêm unique tie-breaker khi dùng phân trang.
- [ ] Kiểm tra native query riêng, không dùng giả định JPQL.
- [ ] Đo execution plan trước khi kết luận expression sort nhanh hay chậm.
- [ ] Test field không hợp lệ bị từ chối trước khi gọi repository.

## Kết luận

`Sort.by` phù hợp với property path hợp lệ của entity hoặc query alias. Khi cần sắp xếp theo biểu thức như `LOWER(e.fullName)`, Spring Data JPA cung cấp `JpaSort.unsafe` để bỏ qua kiểm tra property path thông thường và đưa expression vào ORDER BY.

Vì expression unsafe là một phần cấu trúc query, không được lấy nó từ input tùy ý. Hãy giữ expression trong code, cho client chọn qua enum/allowlist và dùng `Sort.Direction` đã validate. Khi kết hợp với Pageable, thêm tie-breaker duy nhất để thứ tự ổn định; với native query hoặc hàm riêng database, kiểm thử trên đúng provider và database triển khai.
