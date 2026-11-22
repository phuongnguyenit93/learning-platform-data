# Giao dịch, lỗi thủ tục và quy tắc riêng của cơ sở dữ liệu

## Mục tiêu

Stored procedure là chương trình được lưu và thực thi bên trong hệ quản trị cơ sở dữ liệu (DBMS). Spring Data JPA có thể gọi procedure qua annotation `@Procedure`; Jakarta Persistence cung cấp API `StoredProcedureQuery` để đăng ký tham số, thực thi và lấy kết quả.

Gọi được procedure mới chỉ là một phần của thiết kế. Procedure có thể thay đổi dữ liệu, lấy hoặc giữ lock, phát sinh lỗi SQL, trả mã trạng thái, OUT parameter hoặc ResultSet. Các hành vi này phải được đặt trong ranh giới transaction rõ ràng và kiểm thử với đúng database mà ứng dụng triển khai.

Sau bài này, bạn có thể:

- Phân biệt procedure metadata của JPA với procedure thật trong database.
- Gọi procedure bằng `@Procedure` và `StoredProcedureQuery`.
- Đăng ký tham số IN, OUT, INOUT và REF_CURSOR.
- Quản lý transaction khi procedure đọc hoặc ghi dữ liệu.
- Hiểu rollback, persistence context và dữ liệu entity bị stale sau bulk DML.
- Xử lý lỗi database qua Spring `DataAccessException`.
- Phân biệt lỗi SQL với mã lỗi nghiệp vụ do procedure trả về.
- Nhận biết khác biệt giữa PostgreSQL, MySQL, SQL Server, Oracle và các provider.
- Kiểm thử procedure bằng database tương thích production.

Ví dụ dùng Java 17+, Spring Boot 3.x, Jakarta Persistence và Spring Data JPA. Cú pháp tạo procedure trong phần SQL được ghi rõ theo PostgreSQL; không coi DDL đó là SQL portable.

## 1. Procedure được lưu ở đâu và ai quản lý?

Stored procedure nằm trong database schema. Nó có thể được tạo bằng migration SQL, công cụ quản trị database hoặc quy trình triển khai riêng.

JPA không tự tạo procedure chỉ vì entity có `@NamedStoredProcedureQuery`. Annotation đó chỉ khai báo metadata để persistence provider biết cách gọi một procedure đã tồn tại.

Phân biệt hai tên trong metadata:

- `name`: tên logic mà JPA dùng trong persistence unit.
- `procedureName`: tên procedure thật trong database, có thể kèm schema.

Ví dụ:

```java
@Entity
@NamedStoredProcedureQuery(
    name = "Employee.raiseSalary",
    procedureName = "raise_salary",
    parameters = {
        @StoredProcedureParameter(
            mode = ParameterMode.IN,
            name = "p_employee_id",
            type = Long.class
        ),
        @StoredProcedureParameter(
            mode = ParameterMode.IN,
            name = "p_increment",
            type = BigDecimal.class
        ),
        @StoredProcedureParameter(
            mode = ParameterMode.OUT,
            name = "p_new_salary",
            type = BigDecimal.class
        )
    }
)
public class Employee {
    // entity mapping
}
```

JPA gọi metadata bằng tên `Employee.raiseSalary`; database thực thi procedure `raise_salary`. Migration phải bảo đảm procedure này được tạo trước khi ứng dụng gọi nó.

### 1.1. Quản lý DDL bằng migration

Trong ứng dụng thực tế, nên quản lý procedure bằng Flyway, Liquibase hoặc quy trình migration đã chuẩn hóa:

- Tạo procedure trong migration có version.
- Thay đổi procedure bằng migration mới thay vì sửa lịch sử migration đã chạy.
- Triển khai procedure tương thích với phiên bản ứng dụng đang chạy trong giai đoạn rollout.
- Cấp quyền EXECUTE cho database user của ứng dụng.
- Có cách rollback hoặc forward-fix nếu migration thất bại.
- Kiểm thử migration trên đúng loại database và phiên bản dự kiến.

Không đặt DDL tạo procedure trong code Java rồi thực thi tùy tiện mỗi lần ứng dụng khởi động. Việc triển khai schema cần có thứ tự, quyền và khả năng audit rõ ràng.

## 2. Ví dụ procedure thay đổi dữ liệu

Giả sử bảng employees có các cột id và salary. Procedure tăng lương theo employee ID và trả về mức lương mới.

Ví dụ dưới đây dùng PostgreSQL PL/pgSQL:

```sql
CREATE OR REPLACE PROCEDURE raise_salary(
    IN p_employee_id BIGINT,
    IN p_increment NUMERIC,
    OUT p_new_salary NUMERIC
)
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE employees
    SET salary = salary + p_increment
    WHERE id = p_employee_id
    RETURNING salary INTO p_new_salary;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Employee % does not exist', p_employee_id
            USING ERRCODE = 'P0002';
    END IF;
END;
$$;
```

Procedure thực hiện hai việc:

1. Cập nhật salary trong database.
2. Trả giá trị salary sau cập nhật qua OUT parameter `p_new_salary`.

Nếu không có employee tương ứng, procedure phát sinh lỗi database. Đây là lựa chọn phù hợp khi caller cần transaction thất bại và rollback. Một thiết kế khác có thể trả mã trạng thái; khi đó service phải kiểm tra mã đó và quyết định có ném exception để rollback hay không.

Cú pháp `CREATE OR REPLACE PROCEDURE`, khối `plpgsql`, `RETURNING INTO` và SQLSTATE ở trên thuộc PostgreSQL. MySQL, SQL Server và Oracle có cú pháp tạo procedure, khai báo tham số, xử lý exception và trả kết quả khác nhau.

## 3. Gọi procedure bằng @Procedure

Spring Data JPA cung cấp `@Procedure` để khai báo procedure trên repository method. Với metadata ở entity, repository tham chiếu tên JPA bằng thuộc tính `name`:

```java
public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {

    @Procedure(name = "Employee.raiseSalary")
    BigDecimal raiseSalary(
            @Param("p_employee_id") Long employeeId,
            @Param("p_increment") BigDecimal increment
    );
}
```

Method có hai tham số IN và trả về một giá trị OUT duy nhất là BigDecimal. Tên tham số trong `@Param` phải khớp tên được khai báo trong `@StoredProcedureParameter` và được provider/database hỗ trợ.

Service đặt lời gọi trong transaction:

```java
@Service
public class EmployeeSalaryService {

    private final EmployeeRepository repository;
    private final EntityManager entityManager;

    public EmployeeSalaryService(
            EmployeeRepository repository,
            EntityManager entityManager
    ) {
        this.repository = repository;
        this.entityManager = entityManager;
    }

    @Transactional
    public BigDecimal increaseSalary(
            Long employeeId,
            BigDecimal increment
    ) {
        if (increment == null || increment.signum() <= 0) {
            throw new IllegalArgumentException(
                    "increment must be positive"
            );
        }

        entityManager.flush();

        BigDecimal newSalary =
                repository.raiseSalary(employeeId, increment);

        entityManager.clear();

        return newSalary;
    }
}
```

Service xác thực input, flush các thay đổi JPA đang chờ, gọi procedure và clear persistence context sau khi procedure đã cập nhật dữ liệu. Lý do của flush/clear được giải thích ở phần persistence context bên dưới.

### 3.1. Gọi trực tiếp tên procedure trong database

Nếu không cần khai báo `@NamedStoredProcedureQuery`, Spring Data cho phép chỉ định tên procedure thật:

```java
@Procedure(procedureName = "raise_salary")
BigDecimal callRaiseSalary(
        Long employeeId,
        BigDecimal increment
);
```

`value` là alias của `procedureName`. Khi dùng cách khai báo trực tiếp này, Spring Data gọi procedure trong database và không sử dụng metadata `@NamedStoredProcedureQuery` đã khai báo cho một tên JPA.

Cách trực tiếp phù hợp với procedure đơn giản, đặc biệt khi chỉ có một OUT parameter. Khi cần nhiều OUT parameter, REF_CURSOR hoặc metadata tham số chi tiết, named stored procedure thường rõ ràng hơn.

### 3.2. Không nhầm name với procedureName

| Thuộc tính | Ví dụ | Ý nghĩa |
|---|---|---|
| `@Procedure(name = ...)` | `Employee.raiseSalary` | Tên metadata JPA |
| `@Procedure(procedureName = ...)` | `raise_salary` | Tên procedure trong database |
| `@Procedure("...")` | `@Procedure("raise_salary")` | Cách viết ngắn của procedureName |

Nếu truyền nhầm tên logic JPA vào `procedureName`, database có thể báo không tìm thấy procedure. Ngược lại, truyền tên database vào `name` sẽ khiến JPA tìm metadata theo tên đó trong persistence unit.

## 4. Parameter mode: IN, OUT, INOUT và REF_CURSOR

Jakarta Persistence định nghĩa các mode chính:

| Mode | Vai trò | Cách dùng |
|---|---|---|
| `IN` | Giá trị đầu vào | Java truyền giá trị cho procedure |
| `OUT` | Giá trị đầu ra | Procedure gán kết quả để Java đọc |
| `INOUT` | Vừa nhận đầu vào vừa trả kết quả | Java truyền giá trị ban đầu, procedure có thể thay đổi |
| `REF_CURSOR` | Cursor/result set được trả về | Provider lấy các hàng từ cursor theo hỗ trợ của database |

Các tham số phải được đăng ký đúng kiểu Java và mode. Kiểu `BigDecimal` thường phù hợp với NUMERIC/DECIMAL; kiểu ngày giờ cần chọn tương thích với SQL type và JDBC driver.

Không suy đoán mapping chỉ từ tên cột. Hãy xác nhận kiểu dữ liệu, độ chính xác số, timezone và nullability giữa procedure, JDBC driver và Java.

### 4.1. Một OUT parameter

Ví dụ procedure `raise_salary` có một OUT parameter. Spring Data có thể trả OUT value đó trực tiếp làm giá trị trả về của repository method:

```java
@Procedure(name = "Employee.raiseSalary")
BigDecimal raiseSalary(
        @Param("p_employee_id") Long employeeId,
        @Param("p_increment") BigDecimal increment
);
```

Đây là cách đơn giản nhất khi procedure trả đúng một scalar output và không cần trả ResultSet.

### 4.2. Nhiều OUT parameter

Nếu procedure có nhiều OUT parameter, khai báo metadata bằng `@NamedStoredProcedureQuery` và trả về `Map<String, Object>`:

```java
@Entity
@NamedStoredProcedureQuery(
    name = "Employee.salarySummary",
    procedureName = "salary_summary",
    parameters = {
        @StoredProcedureParameter(
            mode = ParameterMode.IN,
            name = "p_department_id",
            type = Long.class
        ),
        @StoredProcedureParameter(
            mode = ParameterMode.OUT,
            name = "p_employee_count",
            type = Long.class
        ),
        @StoredProcedureParameter(
            mode = ParameterMode.OUT,
            name = "p_total_salary",
            type = BigDecimal.class
        )
    }
)
public class Employee {
    // entity mapping
}
```

Repository:

```java
@Procedure(name = "Employee.salarySummary")
Map<String, Object> salarySummary(
        @Param("p_department_id") Long departmentId
);
```

Đọc kết quả:

```java
Map<String, Object> result =
        repository.salarySummary(departmentId);

Long employeeCount =
        ((Number) result.get("p_employee_count")).longValue();

BigDecimal totalSalary =
        (BigDecimal) result.get("p_total_salary");
```

Tên key trong Map là tên parameter được khai báo trong metadata. Kiểu giá trị thực tế có thể phụ thuộc JDBC driver/provider; với kiểu số, kiểm tra kiểu trả về thay vì ép kiểu một cách mù quáng.

### 4.3. INOUT parameter

Với INOUT, Java truyền giá trị ban đầu và đọc lại giá trị sau khi procedure thực thi:

```java
@StoredProcedureParameter(
    mode = ParameterMode.INOUT,
    name = "p_counter",
    type = Integer.class
)
```

Trong API EntityManager, đăng ký tham số với `ParameterMode.INOUT`, đặt giá trị ban đầu bằng `setParameter` rồi lấy giá trị bằng `getOutputParameterValue`. Với repository annotation, cần đối chiếu cách provider và Spring Data version ánh xạ INOUT sang chữ ký method; không giả định mọi tổ hợp INOUT đều được biểu diễn giống một IN cộng một OUT độc lập.

### 4.4. REF_CURSOR và ResultSet

Một số database hỗ trợ trả cursor tham chiếu. Metadata JPA có thể khai báo:

```java
@StoredProcedureParameter(
    mode = ParameterMode.REF_CURSOR,
    name = "p_result",
    type = void.class
)
```

REF_CURSOR phụ thuộc mạnh vào database, JDBC driver và JPA provider. PostgreSQL, Oracle và các database khác có quy tắc cursor riêng; không giả định một cấu hình chạy được trên mọi hệ quản trị.

Spring Data JPA lưu ý rằng nếu procedure trả ResultSet thì các OUT parameter có thể bị bỏ qua khi method chỉ có một kiểu kết quả trả về. Nếu cần lấy nhiều OUT parameter, metadata named procedure là bắt buộc và method có thể cần trả Map theo khả năng hỗ trợ. Khi cần nhiều result set hoặc mapping DTO phức tạp, dùng StoredProcedureQuery hoặc custom repository để kiểm soát việc đọc kết quả.

## 5. Gọi procedure bằng StoredProcedureQuery

Khi cần điều khiển đăng ký tham số, result set hoặc thứ tự xử lý, dùng trực tiếp EntityManager:

```java
@Repository
public class EmployeeProcedureDao {

    @PersistenceContext
    private EntityManager entityManager;

    public BigDecimal raiseSalary(
            Long employeeId,
            BigDecimal increment
    ) {
        StoredProcedureQuery query =
                entityManager.createStoredProcedureQuery("raise_salary");

        query.registerStoredProcedureParameter(
                "p_employee_id",
                Long.class,
                ParameterMode.IN
        );
        query.registerStoredProcedureParameter(
                "p_increment",
                BigDecimal.class,
                ParameterMode.IN
        );
        query.registerStoredProcedureParameter(
                "p_new_salary",
                BigDecimal.class,
                ParameterMode.OUT
        );

        query.setParameter("p_employee_id", employeeId);
        query.setParameter("p_increment", increment);

        query.execute();

        return (BigDecimal) query.getOutputParameterValue(
                "p_new_salary"
        );
    }
}
```

Các bước thực hiện:

1. Tạo StoredProcedureQuery với tên procedure trong database.
2. Đăng ký từng parameter: tên hoặc vị trí, Java type và ParameterMode.
3. Gán giá trị cho các tham số IN/INOUT.
4. Gọi `execute()`.
5. Lấy OUT value sau khi procedure thực thi và xử lý result set nếu có.

Có thể đăng ký tham số theo vị trí:

```java
query.registerStoredProcedureParameter(
        1, Long.class, ParameterMode.IN
);
```

Tên và vị trí tham số phải khớp metadata của procedure và khả năng hỗ trợ của provider/driver. Khi database hoặc driver chỉ xử lý tham số theo vị trí, thứ tự khai báo phải trùng chính xác chữ ký procedure.

### 5.1. Procedure trả ResultSet

Nếu procedure trả result set, API có thể đọc kết quả sau khi execute:

```java
boolean hasResultSet = query.execute();

if (hasResultSet) {
    List<?> rows = query.getResultList();
}
```

Với procedure trả nhiều kết quả, có thể cần dùng `hasMoreResults()`, `getUpdateCount()` và các thao tác lấy result tiếp theo theo hợp đồng của Jakarta Persistence/provider. Thứ tự giữa ResultSet, update count và OUT parameter cần được kiểm thử với driver thực tế.

Nếu muốn map result set thành entity hoặc DTO, khai báo result class/result set mapping phù hợp với `createStoredProcedureQuery` hoặc metadata named procedure. Số cột, alias và kiểu SQL phải khớp mapping đã khai báo.

## 6. Transaction boundary khi gọi procedure

Procedure có thể đọc và ghi dữ liệu. Với nghiệp vụ ghi, hãy gọi nó trong transaction do Spring quản lý:

```java
@Service
public class PayrollService {

    private final EmployeeProcedureDao procedureDao;

    public PayrollService(EmployeeProcedureDao procedureDao) {
        this.procedureDao = procedureDao;
    }

    @Transactional
    public BigDecimal increaseSalary(
            Long employeeId,
            BigDecimal increment
    ) {
        return procedureDao.raiseSalary(employeeId, increment);
    }
}
```

Transaction boundary đặt ở service giúp procedure tham gia cùng đơn vị công việc với các thao tác JPA khác trong method, nếu chúng dùng cùng transaction manager và cùng resource transaction.

Ví dụ một nghiệp vụ có thể:

1. Kiểm tra quyền và dữ liệu đầu vào.
2. Đọc thông tin cần thiết bằng repository.
3. Gọi procedure cập nhật nhiều bảng.
4. Ghi audit hoặc dữ liệu liên quan bằng JPA.
5. Commit khi toàn bộ công việc thành công.

Nếu procedure thất bại và exception thoát khỏi transactional method, Spring có thể rollback transaction theo quy tắc rollback. Mặc định Spring rollback với RuntimeException và Error; checked exception không tự động rollback trừ khi khai báo `rollbackFor` hoặc cấu hình tương ứng.

### 6.1. Repository query method không tự tạo transaction cho mọi trường hợp

Các phương thức CRUD kế thừa từ repository có transaction configuration mặc định. Với query method khai báo riêng, không nên dựa vào giả định rằng mọi method đều tự mở transaction.

Đặt `@Transactional` ở service boundary thường dễ quản lý hơn vì nó bao trùm toàn bộ nghiệp vụ, bao gồm cả lời gọi procedure và các thao tác JPA liên quan.

Không mở một transaction mới chỉ để gọi procedure nếu nghiệp vụ cần procedure và các thao tác JPA cùng commit/rollback. `Propagation.REQUIRES_NEW` tạo transaction riêng và có thể làm procedure commit độc lập với transaction bên ngoài.

### 6.2. Procedure có tự COMMIT hoặc ROLLBACK không?

Quy tắc transaction bên trong procedure phụ thuộc DBMS. Một số database cho phép transaction control trong stored procedure ở những điều kiện nhất định; một số hạn chế hoặc cấm commit trong transaction do caller quản lý.

Nếu procedure tự commit giữa chừng, rollback từ Spring có thể không hoàn tác được phần đã commit. Khi đó nghiệp vụ không còn atomic theo cách ứng dụng mong muốn.

Quy tắc an toàn cho đa số ứng dụng Spring:

- Để Spring quản lý transaction boundary.
- Tránh COMMIT/ROLLBACK bên trong procedure khi procedure được gọi trong transaction ứng dụng.
- Không giả định procedure chạy trong transaction độc lập.
- Kiểm tra quy tắc transaction control của database cụ thể.
- Nếu cần autonomous transaction hoặc commit riêng, thiết kế như một hành vi vendor-specific và kiểm thử failure/recovery riêng.

## 7. Persistence context có thể stale sau procedure

JPA persistence context theo dõi các entity đã được load. Nếu procedure trực tiếp UPDATE hoặc DELETE các hàng, JPA không tự đồng bộ trạng thái của các entity đang managed với thay đổi do procedure thực hiện.

Ví dụ:

```java
Employee employee = employeeRepository.findById(id).orElseThrow();

employeeProcedureDao.raiseSalary(id, new BigDecimal("100.00"));

// employee.getSalary() có thể vẫn là giá trị cũ trong bộ nhớ.
```

Database đã cập nhật salary, nhưng object Employee đang nằm trong persistence context có thể vẫn chứa giá trị trước procedure.

### 7.1. Flush trước khi gọi procedure

Nếu trước khi gọi procedure có thay đổi entity chưa được ghi xuống database, gọi:

```java
entityManager.flush();
```

để buộc các thay đổi đang chờ được đồng bộ trước khi procedure chạy. Điều này làm thứ tự thực thi rõ ràng hơn, đặc biệt khi procedure đọc những hàng vừa được thay đổi trong cùng transaction.

### 7.2. Refresh hoặc clear sau procedure

Nếu cần tiếp tục dùng một entity cụ thể, có thể refresh:

```java
entityManager.refresh(employee);
```

Nếu procedure cập nhật nhiều entity hoặc nhiều hàng mà ứng dụng không biết đầy đủ đối tượng nào bị ảnh hưởng, có thể clear persistence context:

```java
entityManager.clear();
```

`clear()` detach tất cả entity đang managed. Sau đó, lần đọc tiếp theo sẽ lấy dữ liệu mới từ database. Tuy nhiên, clear trước khi flush có thể làm mất các thay đổi chưa đồng bộ; do đó thường cần flush trước procedure và chỉ clear sau khi procedure thành công.

Không dùng clear một cách máy móc nếu service còn cần tiếp tục cập nhật các entity đã load. Khi đó refresh đúng entity hoặc thiết kế lại ranh giới persistence context.

## 8. Rollback và xử lý lỗi procedure

Procedure có thể thất bại do:

- Vi phạm unique, foreign key, check constraint hoặc NOT NULL.
- Không tìm thấy dữ liệu.
- Deadlock hoặc lock timeout.
- Sai kiểu hoặc số lượng tham số.
- Procedure không tồn tại hoặc không có quyền EXECUTE.
- Lỗi cú pháp hoặc lỗi trong logic SQL.
- Timeout, mất kết nối hoặc lỗi transaction.

Khi lỗi database thoát khỏi JPA provider, Spring có thể dịch lỗi sang hệ thống exception của Spring DAO, thường thuộc cây `DataAccessException`. Ví dụ có thể gặp:

| Nhóm lỗi | Exception Spring có thể gặp |
|---|---|
| Vi phạm constraint | `DataIntegrityViolationException` |
| Cú pháp hoặc đối tượng SQL không hợp lệ | `BadSqlGrammarException` hoặc exception truy cập dữ liệu tương ứng |
| Không lấy được lock | `CannotAcquireLockException` hoặc exception liên quan |
| Timeout | `QueryTimeoutException` hoặc exception truy cập dữ liệu tương ứng |
| Lỗi persistence/provider khác | `JpaSystemException` hoặc `DataAccessException` cụ thể khác |

Mapping cụ thể phụ thuộc SQLState, vendor error code, provider và exception translator. Không viết code phụ thuộc tuyệt đối vào một subclass cho mọi database.

### 8.1. Không nuốt exception trong transaction

Ví dụ nguy hiểm:

```java
@Transactional
public void updateSalary(Long id, BigDecimal increment) {
    try {
        repository.raiseSalary(id, increment);
    } catch (DataAccessException ex) {
        log.error("Procedure failed", ex);
        // Nuốt lỗi rồi trả về bình thường.
    }
}
```

Nếu exception bị bắt và không được ném lại, Spring có thể xem transactional method đã kết thúc bình thường. Database hoặc transaction manager có thể đã đánh dấu rollback-only, nhưng service không nên dựa vào hành vi đó một cách ngẫu nhiên.

Nếu lỗi không thể phục hồi, hãy ném lại exception hoặc chuyển thành domain runtime exception:

```java
@Transactional
public void updateSalary(Long id, BigDecimal increment) {
    try {
        repository.raiseSalary(id, increment);
    } catch (DataAccessException ex) {
        throw new SalaryUpdateException(
                "Unable to update employee salary",
                ex
        );
    }
}
```

`SalaryUpdateException` cần kế thừa RuntimeException nếu muốn rollback theo mặc định. Nếu dùng checked exception, khai báo `@Transactional(rollbackFor = ...)` phù hợp.

### 8.2. Mã lỗi nghiệp vụ do procedure trả về

Không phải procedure nào cũng phát sinh SQL exception khi nghiệp vụ thất bại. Một procedure có thể trả:

- `status_code`: mã kết quả.
- `status_message`: thông báo.
- `affected_count`: số hàng bị ảnh hưởng.

Nếu procedure trả `status_code = 0` cho thành công và `status_code = 10` cho không tìm thấy dữ liệu, Spring không tự hiểu mã 10 là lỗi transaction. Service phải diễn giải kết quả:

```java
ProcedureResult result = repository.runBusinessProcedure(...);

if (result.statusCode() != 0) {
    throw new BusinessProcedureException(result.statusMessage());
}
```

Khi exception runtime thoát khỏi transactional method, Spring có thể rollback. Nếu service chỉ trả kết quả thất bại cho controller mà không ném lỗi hoặc đánh dấu rollback-only, transaction có thể commit các thay đổi mà procedure đã thực hiện trước khi trả status. Hãy định nghĩa rõ contract của procedure: status failure có bảo đảm không ghi dữ liệu hay cần rollback từ caller?

### 8.3. Không parse thông báo lỗi database làm hợp đồng nghiệp vụ

Thông báo lỗi và vendor error code có thể thay đổi theo version, locale hoặc provider. Tránh viết logic nghiệp vụ dựa vào chuỗi message như `duplicate key value violates unique constraint`.

Ưu tiên:

- Unique/check/foreign key constraint trong database.
- OUT status code có contract rõ nếu procedure được thiết kế theo cách đó.
- SQLState/vendor code khi cần phân loại lỗi kỹ thuật và có kiểm thử theo DBMS.
- Chuyển exception thành domain exception tại service boundary.
- Giữ nguyên cause để log và chẩn đoán.

## 9. Deadlock, lock timeout và retry

Procedure có thể cập nhật nhiều bảng và lấy lock theo thứ tự riêng. Nếu hai transaction gọi các procedure theo thứ tự khác nhau, deadlock có thể xảy ra.

Ví dụ:

- Transaction A khóa Account 1 rồi cần Account 2.
- Transaction B khóa Account 2 rồi cần Account 1.
- Database phát hiện vòng chờ và hủy một transaction.

Để giảm nguy cơ:

- Thống nhất thứ tự cập nhật/khóa các bảng và hàng.
- Giữ transaction ngắn.
- Tạo index cho điều kiện tìm hàng cần cập nhật.
- Tránh gọi dịch vụ mạng hoặc thao tác chậm trong khi giữ lock.
- Cấu hình timeout theo transaction manager/database phù hợp.
- Ghi nhận deadlock và lock timeout để theo dõi.

### 9.1. Retry phải có chủ đích

Chỉ retry những lỗi tạm thời đã xác định, ví dụ deadlock victim hoặc serialization failure tùy DBMS. Không retry mọi `DataAccessException` vì lỗi permission, sai tham số hoặc procedure không tồn tại sẽ không tự hết.

Khi retry một transaction, phải chạy lại toàn bộ transaction trong một boundary mới. Không tiếp tục dùng transaction đã bị rollback-only.

Procedure ghi dữ liệu cần idempotency nếu có khả năng client gửi lại request sau timeout mà không biết database đã commit hay chưa. Có thể dùng request ID duy nhất, bảng idempotency hoặc unique constraint để ngăn thực thi trùng. Không chỉ dựa vào timeout phía client để kết luận procedure chưa chạy.

## 10. Quy tắc riêng theo database

Cùng một ý tưởng procedure có thể được triển khai khác nhau giữa các DBMS.

| Khía cạnh | Điều cần xác minh |
|---|---|
| Tạo procedure | CREATE PROCEDURE, body delimiter, block syntax và replace/alter khác nhau |
| Tên/schema | Quy tắc schema, catalog, quoted identifier và chữ hoa/thường |
| Tham số | Named/positional parameter, thứ tự, INOUT/OUT và default value |
| ResultSet/cursor | REF_CURSOR, nhiều result set và thứ tự lấy kết quả |
| Transaction | Có cho COMMIT/ROLLBACK trong procedure hay không; autonomous transaction |
| Exception | Cú pháp raise/throw, SQLState, vendor code và rollback behavior |
| Kiểu dữ liệu | NUMERIC, boolean, date/time, UUID, JSON và kiểu proprietary |
| Quyền thực thi | EXECUTE grant, owner/definer, invoker rights và schema search path |
| Timeout/lock | Cách đặt statement timeout, lock timeout và xử lý cancellation |
| Migration | Cú pháp versioning, thay procedure và rollback DDL |

Một số ví dụ khác biệt cần nhớ:

- PostgreSQL dùng PL/pgSQL và có phân biệt procedure với function; procedure được gọi bằng CALL, function thường được dùng trong biểu thức SELECT.
- MySQL có quy tắc delimiter khi tạo routine trong script client, cùng cú pháp IN/OUT/INOUT riêng.
- SQL Server dùng T-SQL, tham số OUTPUT và cơ chế TRY/CATCH, THROW.
- Oracle dùng PL/SQL, procedure/package, OUT parameter và REF CURSOR theo quy tắc Oracle/JDBC.

Đây là định hướng để biết phần nào cần kiểm tra, không phải hướng dẫn DDL đầy đủ cho từng DBMS. Cú pháp cụ thể phải lấy từ tài liệu phiên bản database đang triển khai.

### 10.1. Procedure và function không giống nhau

Procedure thường được gọi như một thao tác bằng `CALL` hoặc StoredProcedureQuery. Function thường trả một giá trị dùng trong biểu thức SQL, ví dụ `SELECT calculate_tax(?)`.

Cách gọi function qua JPA phụ thuộc DBMS và có thể cần native query hoặc API riêng. Không thay `@Procedure` bằng một `@Query` tùy tiện nếu chưa xác minh cú pháp và kiểu kết quả.

### 10.2. Named parameter không bảo đảm portable

Jakarta Persistence cho phép đăng ký tham số theo tên hoặc vị trí, nhưng provider phải chuyển cách khai báo đó xuống JDBC/database. Một số driver/provider có thể yêu cầu tham số theo vị trí hoặc xử lý OUT parameter theo thứ tự signature.

Vì vậy:

- Đối chiếu thứ tự tham số với định nghĩa procedure.
- Kiểm thử cả IN và OUT với driver production.
- Không giả định tên trong `@Param` luôn là named argument syntax của database.
- Kiểm tra schema qualification và quyền EXECUTE của user ứng dụng.

## 11. Kiểm thử procedure với database tương thích production

Stored procedure phụ thuộc DBMS nên H2 hoặc database embedded không phải lúc nào cũng mô phỏng đúng behavior production. Nếu ứng dụng triển khai PostgreSQL, MySQL, SQL Server hoặc Oracle, nên dùng Testcontainers hoặc môi trường integration test của cùng loại database.

Ví dụ repository test:

```java
@DataJpaTest
class EmployeeProcedureRepositoryTest {

    @Autowired
    private EmployeeRepository repository;

    @Autowired
    private EntityManager entityManager;

    @Test
    void procedureUpdatesSalaryAndReturnsNewValue() {
        Employee employee = repository.saveAndFlush(
                new Employee(
                        "An Nguyen",
                        new BigDecimal("1000.00")
                )
        );

        BigDecimal result = repository.raiseSalary(
                employee.getId(),
                new BigDecimal("100.00")
        );

        entityManager.clear();

        Employee reloaded = repository.findById(employee.getId())
                .orElseThrow();

        assertThat(result).isEqualByComparingTo("1100.00");
        assertThat(reloaded.getSalary())
                .isEqualByComparingTo("1100.00");
    }
}
```

Test giả định Employee có constructor và getter phù hợp, repository có method `raiseSalary`, procedure đã được tạo bởi migration trong test database và database test hỗ trợ cú pháp procedure tương ứng. `@DataJpaTest` thường chạy trong transaction và rollback sau test; việc `clear()` giúp lần đọc lại lấy dữ liệu từ database thay vì entity còn trong persistence context.

Nên kiểm thử thêm:

- Procedure thành công với giá trị biên và null được phép.
- ID không tồn tại và contract lỗi tương ứng.
- OUT/INOUT trả đúng kiểu và giá trị.
- Nhiều OUT parameter được map đúng key.
- ResultSet/REF_CURSOR nếu use case dùng cursor.
- Constraint violation và exception translation.
- Rollback khi procedure ném lỗi giữa chừng.
- Status code nghiệp vụ thất bại có rollback đúng không.
- Persistence context sau procedure không trả dữ liệu stale.
- Deadlock/timeout và retry nếu đây là yêu cầu thực tế.
- Quyền EXECUTE và schema của database user triển khai.

Không dùng test trên H2 làm bằng chứng procedure PostgreSQL/Oracle/MySQL chạy giống production. Test cần chạy migration thật và dùng JDBC driver thật.

## 12. Logging và quan sát lỗi

Khi procedure thất bại, log nên đủ thông tin để tìm nguyên nhân nhưng không làm lộ dữ liệu nhạy cảm.

Nên ghi:

- Tên nghiệp vụ hoặc tên procedure đã chuẩn hóa.
- Correlation/request ID.
- Entity/business key cần chẩn đoán nếu được phép.
- Thời gian thực thi và transaction outcome.
- Exception type, SQLState hoặc vendor code khi có.
- Database/schema/version và application version trong telemetry.

Tránh ghi toàn bộ tham số IN nếu chứa lương, thông tin cá nhân, token hoặc dữ liệu tài chính. Mask hoặc loại bỏ dữ liệu nhạy cảm theo chính sách logging.

Có thể theo dõi thời gian procedure, số lần gọi, số lỗi theo nhóm, timeout, deadlock và retry. Không chỉ đếm exception tổng; phân loại lỗi kỹ thuật và lỗi nghiệp vụ giúp đội vận hành biết cần xử lý database, dữ liệu hay request.

## 13. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Procedure không tồn tại | Nhầm tên JPA với tên DB hoặc sai schema | Kiểm tra name/procedureName, schema và migration |
| Sai số lượng tham số | Metadata khác signature procedure | Đối chiếu IN/OUT/INOUT và thứ tự tham số |
| OUT parameter luôn null | Mode, tên, kiểu hoặc driver mapping sai | Kiểm tra đăng ký OUT và lấy kết quả sau execute |
| Method trả sai kiểu số | JDBC driver trả kiểu Number khác dự kiến | Kiểm tra runtime type và chuyển đổi an toàn |
| Không lấy được ResultSet | Procedure/cursor không được provider hỗ trợ như cấu hình | Kiểm tra REF_CURSOR, result mapping và DBMS |
| Exception nhưng dữ liệu vẫn thay đổi | Procedure tự commit hoặc lỗi được chuyển thành status rồi bị bỏ qua | Kiểm tra transaction control và contract lỗi |
| Spring không rollback | Exception bị bắt/nuốt hoặc là checked exception không có rollbackFor | Ném lại runtime exception hoặc cấu hình rollback |
| Entity trả dữ liệu cũ | Procedure DML không đồng bộ persistence context | Flush trước; refresh hoặc clear sau |
| H2 test pass nhưng production fail | Khác DDL, driver, cursor, type hoặc transaction semantics | Test bằng đúng DBMS qua Testcontainers |
| Permission denied | User ứng dụng thiếu quyền EXECUTE hoặc schema access | Cấp quyền tối thiểu theo deployment |
| Deadlock/timeout | Lock order, transaction dài hoặc index không phù hợp | Chuẩn hóa thứ tự lock, giảm transaction và kiểm tra plan |
| Procedure chạy hai lần | Retry/request lặp mà không có idempotency | Dùng request key hoặc unique constraint |
| Lỗi không được phân loại đúng | Dựa vào message string hoặc giả định exception subclass | Dùng DataAccessException, SQLState/vendor code có kiểm thử |

## 14. Checklist trước khi đưa procedure vào production

- [ ] Procedure được quản lý bằng migration và có version.
- [ ] Metadata JPA phân biệt đúng tên logic và tên trong database.
- [ ] Parameter mode, thứ tự, kiểu dữ liệu và nullability khớp signature.
- [ ] OUT, INOUT và REF_CURSOR được kiểm thử với JDBC driver thực tế.
- [ ] Transaction boundary được đặt ở service.
- [ ] Procedure không tự commit/rollback trái với atomicity mong muốn.
- [ ] Đã xác định rollback behavior với SQL exception và business status code.
- [ ] Persistence context được flush/refresh/clear phù hợp sau procedure DML.
- [ ] Deadlock, lock timeout, statement timeout và retry có chính sách rõ.
- [ ] Request có thể retry được bảo vệ bằng idempotency khi cần.
- [ ] Database user có quyền EXECUTE tối thiểu và đúng schema.
- [ ] Exception được chuyển thành domain error mà vẫn giữ cause.
- [ ] Log không lộ tham số nhạy cảm.
- [ ] Integration test chạy trên cùng DBMS/version dự kiến production.
- [ ] Migration và procedure tương thích với phiên bản ứng dụng trong rollout.

## 15. Tài liệu tham khảo

- [Spring Data JPA — Stored Procedures](https://docs.spring.io/spring-data/jpa/reference/jpa/stored-procedures.html)
- [Jakarta Persistence — StoredProcedureQuery API](https://jakarta.ee/specifications/persistence/4.0/apidocs/jakarta.persistence/jakarta/persistence/storedprocedurequery)
- [Jakarta Persistence — NamedStoredProcedureQuery](https://jakarta.ee/specifications/platform/9/apidocs/jakarta/persistence/namedstoredprocedurequery)

## Kết luận

Spring Data JPA gọi procedure qua `@Procedure`; Jakarta Persistence cho phép kiểm soát chi tiết hơn bằng `StoredProcedureQuery`. Metadata `@NamedStoredProcedureQuery` mô tả cách gọi một procedure đã tồn tại trong database, còn migration chịu trách nhiệm triển khai DDL thực tế.

Với procedure ghi dữ liệu, đặt lời gọi trong transaction do Spring quản lý và hiểu rõ procedure có tự commit hay không. Exception database thường được chuyển thành `DataAccessException`; để rollback theo mặc định, không nuốt runtime exception. Nếu procedure trả status code thay vì ném lỗi, service phải diễn giải status và quyết định rollback. Sau bulk DML, flush trước và refresh/clear persistence context phù hợp để tránh entity stale.

Cú pháp DDL, tham số, cursor, transaction control và exception code phụ thuộc DBMS, JDBC driver và JPA provider. Hãy quản lý procedure bằng migration, kiểm thử trên đúng database production và ghi rõ các quy tắc vendor-specific trong hợp đồng tích hợp.
