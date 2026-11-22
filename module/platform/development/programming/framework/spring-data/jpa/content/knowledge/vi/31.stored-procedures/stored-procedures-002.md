# Khai báo phương thức Repository bằng @Procedure

## 1. Mục tiêu

Stored procedure là chương trình SQL được lưu và thực thi trong database. Spring Data JPA cho phép gọi stored procedure từ phương thức Repository bằng annotation `@Procedure`, dựa trên Stored Procedure API của JPA.

Sau bài học, bạn có thể:
- Phân biệt tên procedure trong database với tên JPA dùng để đăng ký `@NamedStoredProcedureQuery`.
- Khai báo metadata tham số `IN`, `OUT`, `INOUT` và `REF_CURSOR`.
- Gọi procedure bằng `@Procedure` và nhận một tham số OUT làm giá trị trả về.
- Ánh xạ nhiều tham số OUT thành `Map<String, Object>`.
- Chọn giữa `value`, `procedureName` và `name` trong `@Procedure`.
- Gọi procedure qua `EntityManager` khi cần kiểm soát tham số hoặc kết quả chi tiết hơn.
- Quản lý transaction và persistence context khi procedure thay đổi dữ liệu.
- Kiểm thử việc gọi procedure trên database có hỗ trợ stored procedure.

## 2. Stored procedure và Spring Data JPA

Stored procedure là routine được định nghĩa trong database. Nó có thể nhận tham số đầu vào, thay đổi dữ liệu, trả tham số đầu ra hoặc trả một hay nhiều result set.

Spring Data JPA cung cấp `@Procedure` để khai báo cách một method Repository gọi procedure. JPA cung cấp metadata và API thực thi qua `StoredProcedureQuery`.

Ví dụ, database có procedure `plus1inout` nhận một số nguyên và trả số đó cộng 1:

```sql
CREATE PROCEDURE plus1inout (IN arg INT, OUT res INT)
BEGIN ATOMIC
    SET res = arg + 1;
END
```

Ứng dụng gọi procedure với `arg = 41` và nhận `res = 42`.

Stored procedure phù hợp khi logic cần chạy trong database, được chia sẻ bởi nhiều ứng dụng, tận dụng khả năng xử lý dữ liệu của database hoặc tuân theo một hợp đồng database đã có. Với truy vấn CRUD đơn giản, derived query hoặc JPQL thường dễ bảo trì và ít phụ thuộc database hơn.

## 3. Cấu hình dependency

Ví dụ sử dụng Java 17+, Spring Boot 3.x, Spring Data JPA và Hibernate do Spring Boot quản lý phiên bản. Cần một JDBC driver tương ứng với database đang chạy.

Ví dụ dependency cho ứng dụng:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-jpa</artifactId>
</dependency>
```

Ví dụ dependency HSQLDB chỉ dành cho integration test:

```xml
<dependency>
    <groupId>org.hsqldb</groupId>
    <artifactId>hsqldb</artifactId>
    <scope>test</scope>
</dependency>
```

Spring Boot 3 dùng Jakarta Persistence (`jakarta.persistence.*`). Không trộn annotation Jakarta với dependency cũ chỉ cung cấp `javax.persistence.*`. Hãy để Spring Boot dependency management quản lý phiên bản Hibernate, Spring Data JPA và driver tương thích.

## 4. Hai loại tên trong @NamedStoredProcedureQuery

JPA cho phép đăng ký metadata stored procedure trên một Entity bằng `@NamedStoredProcedureQuery`. Annotation có hai tên khác nhau:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `name` | Tên logic JPA dùng trong EntityManager và được tham chiếu bởi `@Procedure(name = ...)`. |
| `procedureName` | Tên routine thực tế trong database. |

Ví dụ:

```java
@NamedStoredProcedureQuery(
    name = "Calculator.plus1",
    procedureName = "plus1inout",
    parameters = {
        @StoredProcedureParameter(
            mode = ParameterMode.IN, name = "arg", type = Integer.class),
        @StoredProcedureParameter(
            mode = ParameterMode.OUT, name = "res", type = Integer.class)
    }
)
```

Ở đây `Calculator.plus1` là tên JPA, còn `plus1inout` là tên procedure trong database. Hai tên không bắt buộc giống nhau. Tên logic JPA cần duy nhất trong persistence unit để tránh xung đột.

## 5. Khai báo Entity có metadata procedure

Ví dụ đặt `@NamedStoredProcedureQuery` trên Entity `Calculator`:

`src/main/java/com/example/calculator/Calculator.java`:

```java
package com.example.calculator;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.NamedStoredProcedureQuery;
import jakarta.persistence.ParameterMode;
import jakarta.persistence.StoredProcedureParameter;
import jakarta.persistence.Table;

@Entity
@Table(name = "calculators")
@NamedStoredProcedureQuery(
    name = "Calculator.plus1",
    procedureName = "plus1inout",
    parameters = {
        @StoredProcedureParameter(
            mode = ParameterMode.IN,
            name = "arg",
            type = Integer.class
        ),
        @StoredProcedureParameter(
            mode = ParameterMode.OUT,
            name = "res",
            type = Integer.class
        )
    }
)
public class Calculator {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 80)
    private String label;

    protected Calculator() {
        // JPA cần constructor không tham số.
    }

    public Calculator(String label) {
        if (label == null || label.isBlank()) {
            throw new IllegalArgumentException("Label is required");
        }
        this.label = label.trim();
    }

    public Long getId() {
        return id;
    }

    public String getLabel() {
        return label;
    }
}
```

Entity này đóng vai trò nơi đăng ký metadata cho procedure. Bản thân lời gọi `plus1inout` không cần tạo hoặc tải một `Calculator` row. Bảng `calculators` vẫn được tạo/quản lý theo mapping Entity như các Entity JPA khác.

## 6. Repository gọi procedure bằng @Procedure

`@Procedure` nằm trong package `org.springframework.data.jpa.repository.query`.

`src/main/java/com/example/calculator/CalculatorRepository.java`:

```java
package com.example.calculator;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.query.Procedure;
import org.springframework.data.repository.query.Param;

public interface CalculatorRepository extends JpaRepository<Calculator, Long> {
    @Procedure(name = "Calculator.plus1")
    Integer plusOne(@Param("arg") Integer argument);
}
```

Khi gọi:

```java
Integer result = calculatorRepository.plusOne(41);
System.out.println(result);
```

Output mong đợi:

```text
42
```

Method `plusOne` tham chiếu tên JPA `Calculator.plus1`. `@Param("arg")` ánh xạ đối số Java vào tham số IN có tên `arg` trong metadata. Procedure trả một tham số OUT tên `res`; Spring Data JPA đưa giá trị OUT đó về làm giá trị trả về `Integer` của method.

Với một OUT parameter, kiểu trả về của Repository phải tương thích với kiểu Java đã khai báo cho OUT parameter. Ví dụ `Integer.class` tương ứng với `Integer`.

## 7. Chọn value, procedureName hoặc name

Annotation `@Procedure` có ba cách tham chiếu phổ biến:

### 7.1. Dùng name cho JPA named procedure

```java
@Procedure(name = "Calculator.plus1")
Integer plusOne(@Param("arg") Integer argument);
```

`name` tham chiếu thuộc tính `name` của `@NamedStoredProcedureQuery`. Đây là cách phù hợp khi Entity đã khai báo đầy đủ metadata tham số bằng JPA.

### 7.2. Dùng procedureName cho tên database

```java
@Procedure(
    procedureName = "plus1inout",
    outputParameterName = "res"
)
Integer callPlusOne(@Param("arg") Integer argument);
```

`procedureName` trỏ trực tiếp tới procedure trong database. Cách này không sử dụng cấu hình của `@NamedStoredProcedureQuery`; cần bảo đảm metadata tham số và output phù hợp với cách Spring Data/provider đăng ký lời gọi.

### 7.3. Dùng value làm dạng viết tắt

```java
@Procedure("plus1inout")
Integer callPlusOne(@Param("arg") Integer argument);
```

`value` là dạng viết tắt của `procedureName`. Nó cũng trỏ trực tiếp tới tên procedure trong database.

### 7.4. Không khai báo thuộc tính

Nếu không đặt `value`, `procedureName` hoặc `name`, Spring Data dùng tên method Repository làm tên JPA named procedure. Ví dụ method `plus1inout(...)` sẽ tìm named procedure có tên tương ứng trong EntityManager.

Đừng nhầm tên method Java với tên procedure trong database. Khi tên hai bên khác nhau, khai báo rõ `name` hoặc `procedureName` để code dễ đọc.

## 8. Tham số IN, OUT, INOUT và REF_CURSOR

`@StoredProcedureParameter` mô tả từng tham số của stored procedure:

| ParameterMode | Ý nghĩa |
| --- | --- |
| `IN` | Ứng dụng truyền giá trị vào procedure. |
| `OUT` | Procedure ghi giá trị để ứng dụng đọc sau khi gọi. |
| `INOUT` | Ứng dụng truyền giá trị ban đầu và procedure có thể trả lại giá trị mới. |
| `REF_CURSOR` | Procedure trả cursor/result set; hỗ trợ phụ thuộc database và provider. |

Ví dụ metadata cho một tham số IN và một tham số OUT:

```java
@StoredProcedureParameter(
    mode = ParameterMode.IN, name = "customerId", type = Long.class
),
@StoredProcedureParameter(
    mode = ParameterMode.OUT, name = "orderCount", type = Long.class
)
```

Tên tham số trong metadata phải khớp với tên procedure mà database/provider nhận diện. Với database phân biệt chữ hoa/thường hoặc có quy tắc schema riêng, cần kiểm tra quy tắc đặt tên của engine.

Đối với `INOUT`, đăng ký mode `ParameterMode.INOUT` và kiểu Java tương ứng. Giá trị đầu vào được bind trước khi thực thi; giá trị đầu ra được đọc sau khi procedure chạy. Cách bind tên hoặc vị trí tham số phụ thuộc khả năng hỗ trợ của JPA provider và driver.

`REF_CURSOR` không được hỗ trợ đồng nhất ở mọi database. Chỉ dùng khi database, JDBC driver và Hibernate/JPA provider của dự án hỗ trợ cách trả cursor đó; hãy kiểm thử trên đúng engine triển khai.

## 9. Procedure có nhiều tham số OUT

Nếu procedure khai báo nhiều tham số OUT, Spring Data JPA có thể trả chúng dưới dạng `Map<String, Object>` khi metadata được đăng ký bằng `@NamedStoredProcedureQuery`.

Ví dụ metadata:

```java
@NamedStoredProcedureQuery(
    name = "Calculator.summary",
    procedureName = "order_summary",
    parameters = {
        @StoredProcedureParameter(
            mode = ParameterMode.IN, name = "customerId", type = Long.class),
        @StoredProcedureParameter(
            mode = ParameterMode.OUT, name = "orderCount", type = Long.class),
        @StoredProcedureParameter(
            mode = ParameterMode.OUT, name = "totalAmount", type = BigDecimal.class)
    }
)
```

Repository:

```java
@Procedure(name = "Calculator.summary")
Map<String, Object> summarizeCustomer(
        @Param("customerId") Long customerId);
```

Gọi và đọc kết quả:

```java
Map<String, Object> summary = repository.summarizeCustomer(101L);

Long orderCount = (Long) summary.get("orderCount");
BigDecimal totalAmount = (BigDecimal) summary.get("totalAmount");
```

Key của Map là tên tham số OUT đã khai báo trong `@NamedStoredProcedureQuery`. Kiểu giá trị cần khớp với kiểu Java/provider trả về; với kiểu số, driver có thể trả về kiểu wrapper khác tùy database nên hãy kiểm tra mapping cụ thể.

Metadata `@NamedStoredProcedureQuery` là cần thiết cho trường hợp nhiều OUT parameters vì nó cung cấp danh sách và mode tham số để ánh xạ kết quả.

## 10. Gọi procedure bằng EntityManager

Khi cần đăng ký tham số động, xử lý nhiều tham số, hoặc cần kiểm soát trực tiếp kết quả, có thể dùng JPA `StoredProcedureQuery` qua `EntityManager` thay vì `@Procedure` trên Repository.

Ví dụ gọi procedure `plus1inout`:

```java
package com.example.calculator;

import jakarta.persistence.EntityManager;
import jakarta.persistence.ParameterMode;
import jakarta.persistence.StoredProcedureQuery;
import org.springframework.stereotype.Repository;

@Repository
public class CalculatorProcedureGateway {
    private final EntityManager entityManager;

    public CalculatorProcedureGateway(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    public Integer plusOne(Integer argument) {
        StoredProcedureQuery query =
                entityManager.createStoredProcedureQuery("plus1inout");

        query.registerStoredProcedureParameter(
                "arg", Integer.class, ParameterMode.IN);
        query.registerStoredProcedureParameter(
                "res", Integer.class, ParameterMode.OUT);
        query.setParameter("arg", argument);

        query.execute();
        return (Integer) query.getOutputParameterValue("res");
    }
}
```

JPA cũng cho phép đăng ký tham số theo vị trí bắt đầu từ 1. Ví dụ `registerStoredProcedureParameter(1, Integer.class, ParameterMode.IN)`. Dùng tên hay vị trí phải nhất quán với metadata và khả năng hỗ trợ của provider/database.

`EntityManager.createStoredProcedureQuery` nhận tên procedure trong database. Nếu cần ánh xạ result set về Entity hoặc mapping đã định nghĩa, có thể dùng các overload nhận result class hoặc result set mapping theo JPA API.

## 11. Procedure trả result set

Procedure có thể trả một hoặc nhiều result set thay vì chỉ trả OUT scalar. Ví dụ procedure tìm các đơn hàng gần đây theo khách hàng.

Khả năng đọc result set phụ thuộc cách database khai báo procedure, JDBC driver và JPA provider. Với JPA, metadata có thể dùng `resultClasses` hoặc `resultSetMappings`; một số database sử dụng `REF_CURSOR` để trả cursor.

Không giả định một method `@Procedure` có thể đồng thời trả mọi loại dữ liệu tùy ý. Nếu procedure trả ResultSet cùng OUT parameters, Spring Data JPA có giới hạn: kết quả ResultSet và OUT parameters không thể cùng được biểu diễn như các giá trị trả về độc lập trong một kiểu return đơn giản. Với nhiều OUT parameters, dùng `Map`; nếu có cursor/result set, kiểm tra hành vi provider và thiết kế method/EntityManager call phù hợp.

Với procedure trả dữ liệu phức tạp, hãy thử nghiệm bằng integration test trên đúng database và driver. Nếu việc ánh xạ trở nên khó đọc, một custom repository hoặc JDBC `CallableStatement` có thể phù hợp hơn.

## 12. Transaction khi gọi procedure

Nếu procedure thay đổi dữ liệu, hãy gọi nó trong transaction do Service quản lý:

```java
package com.example.calculator;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CalculatorService {
    private final CalculatorRepository repository;

    public CalculatorService(CalculatorRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Integer calculate(Integer argument) {
        if (argument == null) {
            throw new IllegalArgumentException("Argument is required");
        }
        return repository.plusOne(argument);
    }
}
```

`@Transactional` đặt transaction boundary ở Service, bao gồm thao tác gọi procedure và các bước nghiệp vụ khác. Quy tắc commit/rollback cụ thể phụ thuộc database và cách procedure được định nghĩa. Không tự thêm lệnh COMMIT/ROLLBACK bên trong routine nếu ứng dụng đang quản lý transaction từ Spring; một số engine có giới hạn riêng về transaction control trong procedure.

Nếu procedure chỉ đọc dữ liệu, có thể dùng `@Transactional(readOnly = true)` khi phù hợp với database/provider. Không đánh dấu read-only cho procedure có ghi dữ liệu.

## 13. Persistence context khi procedure thay đổi dữ liệu

Procedure chạy SQL trong database và có thể cập nhật những dòng đang được JPA quản lý trong persistence context. Các Entity đã load trước đó không tự động được đồng bộ lại chỉ vì procedure đã thay đổi bảng.

Ví dụ:

1. Service tải `Product` với giá 100 vào persistence context.
2. Procedure cập nhật giá trong database thành 120.
3. Object `Product` đang managed có thể vẫn hiển thị giá 100.

Để tránh đọc dữ liệu cũ:

- Gọi `EntityManager.flush()` trước procedure nếu các thay đổi JPA đang chờ phải được ghi trước khi routine chạy.
- Gọi `EntityManager.refresh(entity)` cho Entity cụ thể cần đồng bộ lại.
- Gọi `EntityManager.clear()` sau procedure nếu cần loại toàn bộ Entity managed khỏi persistence context rồi tải lại.

Clear làm mọi Entity đang managed trở thành detached, không chỉ Entity bị procedure thay đổi. Cần chọn thời điểm phù hợp và tránh tiếp tục dùng object cũ như thể chúng còn managed.

`@Modifying(clearAutomatically = true)` là thuộc tính của `@Modifying` dành cho modifying query, không phải thuộc tính của `@Procedure`. Với stored procedure, hãy kiểm soát flush/refresh/clear qua `EntityManager` hoặc một quy trình Service rõ ràng.

## 14. Không dùng @Modifying cho @Procedure

`@Modifying` đánh dấu một `@Query` JPQL/native SQL là câu lệnh UPDATE hoặc DELETE cần thực thi thay vì đọc dữ liệu.

`@Procedure` đã chọn execution path dành cho stored procedure. Không thêm `@Modifying` vào cùng method để cố bật chế độ ghi. Transaction của thao tác procedure được quản lý bằng `@Transactional` ở Service hoặc Repository khi cần.

Ví dụ:

```java
@Procedure(name = "Calculator.plus1")
Integer plusOne(@Param("arg") Integer argument);
```

Đây là method gọi procedure; không cần `@Modifying`.

## 15. Khai báo procedure trong database

Stored procedure là đối tượng database, không được tạo ra chỉ nhờ annotation Java. Cần triển khai DDL procedure bằng migration hoặc script quản lý schema.

Ví dụ HSQLDB dùng trong bài:

```sql
DROP PROCEDURE IF EXISTS plus1inout;

CREATE PROCEDURE plus1inout (IN arg INT, OUT res INT)
BEGIN ATOMIC
    SET res = arg + 1;
END
```

Procedure có cú pháp khác nhau giữa PostgreSQL, MySQL, SQL Server, Oracle và HSQLDB. Cần viết migration theo engine thực tế. Nếu nhiều môi trường dùng database khác nhau, hãy quản lý script theo từng database/dialect thay vì giả định một DDL chạy trên mọi engine.

Đặt procedure trong Flyway hoặc Liquibase giúp version hóa thay đổi routine, triển khai cùng ứng dụng và có thể review lịch sử thay đổi.

## 16. Kiểm thử @Procedure với HSQLDB

Ví dụ kiểm thử dùng HSQLDB để chạy một procedure có một IN và một OUT parameter. HSQLDB có cú pháp `CREATE PROCEDURE ... BEGIN ATOMIC ... END` phù hợp với ví dụ.

Dependency test:

```xml
<dependency>
    <groupId>org.hsqldb</groupId>
    <artifactId>hsqldb</artifactId>
    <scope>test</scope>
</dependency>
```

`src/test/resources/application.properties`:

```properties
spring.datasource.url=jdbc:hsqldb:mem:storedprocdb
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.show-sql=true
```

Repository dùng trong test:

```java
package com.example.calculator;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.query.Procedure;
import org.springframework.data.repository.query.Param;

public interface CalculatorRepository extends JpaRepository<Calculator, Long> {
    @Procedure(name = "Calculator.plus1")
    Integer plusOne(@Param("arg") Integer argument);
}
```

Integration test:

```java
package com.example.calculator;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.jdbc.core.JdbcTemplate;

@DataJpaTest
class CalculatorProcedureTest {
    @Autowired
    private CalculatorRepository repository;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @BeforeEach
    void createStoredProcedure() {
        jdbcTemplate.execute("DROP PROCEDURE IF EXISTS plus1inout");
        jdbcTemplate.execute("""
                CREATE PROCEDURE plus1inout (IN arg INT, OUT res INT)
                BEGIN ATOMIC
                    SET res = arg + 1;
                END
                """);
    }

    @Test
    void mapsSingleOutParameterToRepositoryReturnValue() {
        Integer result = repository.plusOne(41);

        assertThat(result).isEqualTo(42);
    }

    @Test
    void mapsNegativeInputWithoutChangingProcedureContract() {
        Integer result = repository.plusOne(-2);

        assertThat(result).isEqualTo(-1);
    }
}
```

Test xác nhận Spring Data JPA gọi đúng procedure, bind tham số IN `arg` và ánh xạ OUT `res` vào giá trị trả về. Procedure được tạo bằng `JdbcTemplate` trước mỗi test để test độc lập với trạng thái routine còn lại trong database test.

Chạy:

```bash
mvn test
```

Kết quả mong đợi là Maven kết thúc với `BUILD SUCCESS`; hai test xác nhận `41` trả `42` và `-2` trả `-1`. Đây là kết quả mong đợi từ ví dụ, không phải log build đã chạy trong môi trường này.

Test HSQLDB xác nhận mapping JPA/Spring Data cơ bản. Nếu production dùng PostgreSQL, MySQL, SQL Server hoặc Oracle, cần thêm integration test trên đúng engine đó để kiểm tra cú pháp routine, kiểu tham số, transaction, cursor và driver behavior.

## 17. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy procedure | `procedureName` sai, procedure chưa được migration hoặc schema không đúng. | Kiểm tra DDL đã triển khai, schema/search path và tên database procedure. |
| Không tìm thấy named procedure | `@Procedure(name = ...)` không khớp `@NamedStoredProcedureQuery.name`. | Dùng đúng tên JPA, phân biệt với `procedureName` trong database. |
| Không bind được tham số IN | Tên `@Param` không khớp `@StoredProcedureParameter.name` hoặc vị trí không đúng. | Đồng bộ tên và kiểu tham số giữa Java metadata và DDL. |
| Giá trị OUT null hoặc sai kiểu | OUT parameter chưa khai báo đúng mode/type hoặc database trả kiểu khác. | Kiểm tra `ParameterMode.OUT`, Java type, JDBC type và mapping của provider. |
| Có nhiều OUT nhưng method trả về một scalar | Một giá trị return không thể chứa nhiều output độc lập. | Đăng ký named procedure metadata và dùng `Map<String, Object>`. |
| Procedure chạy nhưng Entity đã load vẫn có dữ liệu cũ | Database thay đổi ngoài dirty checking của persistence context. | Flush trước nếu cần và refresh/clear sau procedure. |
| Procedure ghi dữ liệu nhưng không rollback như dự kiến | Transaction boundary không bao trọn lời gọi hoặc routine dùng transaction control riêng. | Đặt `@Transactional` ở Service và kiểm tra hành vi transaction của database. |
| HSQLDB test qua nhưng production lỗi | Cú pháp routine, kiểu tham số hoặc cursor khác giữa database. | Chạy integration test trên engine và driver production. |
| Procedure trả result set không ánh xạ được | Database/provider dùng cursor hoặc result mapping đặc thù. | Kiểm tra `REF_CURSOR`, `resultClasses`/`resultSetMappings` hoặc dùng EntityManager/JDBC. |
| Thêm @Modifying khiến method lỗi | `@Modifying` dành cho `@Query` DML, không phải `@Procedure`. | Bỏ `@Modifying`; dùng transaction cho procedure ghi dữ liệu. |

## 18. Nguyên tắc thiết kế

1. Dùng `@Procedure` khi cần gọi routine đã được triển khai trong database; CRUD đơn giản thường phù hợp hơn với derived query hoặc JPQL.
2. Phân biệt `@NamedStoredProcedureQuery.name` (tên logic JPA) và `procedureName` (tên database).
3. Dùng `@Procedure(name = ...)` khi muốn tái sử dụng metadata JPA đã khai báo trên Entity.
4. Dùng `value` hoặc `procedureName` khi muốn tham chiếu trực tiếp routine database; nhớ rằng cách này bỏ qua named-query metadata.
5. Khai báo chính xác mode, tên và Java type của từng tham số IN/OUT/INOUT.
6. Dùng kiểu return scalar cho một OUT parameter và `Map<String, Object>` cho nhiều OUT parameters có named metadata.
7. Chỉ dùng REF_CURSOR/result set khi database, driver và provider hỗ trợ; kiểm thử trên engine mục tiêu.
8. Đặt transaction boundary ở Service khi procedure thay đổi dữ liệu hoặc cần phối hợp với thao tác JPA khác.
9. Đồng bộ persistence context sau khi procedure thay đổi bảng có Entity đang managed.
10. Không dùng `@Modifying` trên method `@Procedure`.
11. Version hóa DDL procedure bằng Flyway/Liquibase và quản lý script theo database dialect.
12. Kiểm thử tên procedure, bind parameter, output mapping, transaction và result set trên database thật.

## 19. Checklist hoàn thành

- [ ] Giải thích được stored procedure và vai trò của `@Procedure`.
- [ ] Phân biệt tên JPA `name` với tên procedure database `procedureName`.
- [ ] Đăng ký procedure bằng `@NamedStoredProcedureQuery`.
- [ ] Khai báo tham số `IN` và `OUT` bằng `@StoredProcedureParameter`.
- [ ] Gọi procedure bằng `@Procedure(name = ...)`.
- [ ] Dùng `value` hoặc `procedureName` để tham chiếu trực tiếp procedure database.
- [ ] Ánh xạ một OUT parameter thành giá trị trả về của Repository method.
- [ ] Ánh xạ nhiều OUT parameters thành `Map<String, Object>`.
- [ ] Biết khi nào cần `EntityManager.createStoredProcedureQuery`.
- [ ] Quản lý transaction khi procedure thay đổi dữ liệu.
- [ ] Flush/refresh/clear persistence context khi cần.
- [ ] Kiểm thử routine trên đúng database engine triển khai.

## 20. Tài liệu tham khảo

- [Spring Data JPA — Stored Procedures](https://docs.spring.io/spring-data/jpa/reference/jpa/stored-procedures.html)
- [Spring Data JPA — Procedure annotation API](https://docs.spring.io/spring-data/jpa/docs/current/api/org/springframework/data/jpa/repository/query/Procedure.html)
- [Jakarta Persistence — StoredProcedureQuery API](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/storedprocedurequery)
- [HyperSQL User Guide — SQL-Invoked Routines](https://hsqldb.org/doc/2.0/guide/sqlroutines-chapt.html)

Khi hoàn thành, bạn có thể khai báo phương thức Repository để gọi stored procedure, bind đúng tham số, nhận output và quản lý transaction cùng persistence context trong Spring Data JPA.