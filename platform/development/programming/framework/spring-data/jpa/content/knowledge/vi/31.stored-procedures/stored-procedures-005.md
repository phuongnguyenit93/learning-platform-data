# Ánh xạ giá trị trả về, nhiều OUT và tập kết quả từ stored procedure trong Spring Data JPA

Stored procedure là thủ tục được định nghĩa và thực thi trong hệ quản trị cơ sở dữ liệu. Spring Data JPA cung cấp `@Procedure` để gọi thủ tục từ repository; JPA cung cấp `@NamedStoredProcedureQuery`, `StoredProcedureQuery` và `@SqlResultSetMapping` để khai báo tham số và ánh xạ kết quả.

Cần phân biệt ba dạng dữ liệu trả về:

- **Một tham số OUT:** thường ánh xạ trực tiếp vào kiểu trả về của repository method.
- **Nhiều tham số OUT:** có thể nhận dưới dạng `Map<String, Object>` khi dùng `@Procedure` với named stored procedure.
- **Một hoặc nhiều result set:** có thể ánh xạ thành entity hoặc DTO. Khi cần duyệt nhiều result set, update count và OUT parameter trong cùng một lần gọi, `StoredProcedureQuery` cho phép kiểm soát thứ tự xử lý rõ ràng hơn.

Khả năng cụ thể còn phụ thuộc database, JDBC driver và JPA provider. Ví dụ dưới đây dùng Java 17+, Spring Boot 3.x, Spring Data JPA và Hibernate 6; phần DDL minh họa dùng cú pháp MySQL 8.

## 1. Các loại tham số và kết quả

JPA định nghĩa các mode tham số stored procedure:

| Mode | Ý nghĩa |
|---|---|
| `IN` | Ứng dụng truyền giá trị vào thủ tục |
| `OUT` | Thủ tục trả một giá trị cho ứng dụng |
| `INOUT` | Ứng dụng truyền giá trị vào và thủ tục có thể thay đổi giá trị đó |
| `REF_CURSOR` | Tham chiếu tới cursor/result set; hỗ trợ phụ thuộc database và provider |

Một stored procedure có thể trả về OUT parameter, result set hoặc cả hai. Result set là các hàng dữ liệu được trả từ câu `SELECT` trong thủ tục. OUT parameter là giá trị riêng được khai báo trong chữ ký thủ tục. Chúng là hai kênh kết quả khác nhau.

Ví dụ chữ ký khái niệm:

```sql
PROCEDURE update_customer_credit(
    IN  p_customer_id,
    IN  p_delta,
    OUT p_new_credit,
    OUT p_status
)
```

Thủ tục nhận mã khách hàng và số tiền thay đổi, sau đó trả số dư mới và trạng thái xử lý.

## 2. Khai báo named stored procedure

JPA cho phép khai báo stored procedure bằng `@NamedStoredProcedureQuery` trên một entity. Tên trong thuộc tính `name` là tên logic được ứng dụng tham chiếu; `procedureName` là tên thực tế của thủ tục trong database.

Ví dụ MySQL 8:

```sql
DELIMITER //

CREATE PROCEDURE update_customer_credit(
    IN p_customer_id BIGINT,
    IN p_delta DECIMAL(12, 2),
    OUT p_new_credit DECIMAL(12, 2),
    OUT p_status VARCHAR(20)
)
BEGIN
    DECLARE v_exists INT DEFAULT 0;

    SELECT COUNT(*)
      INTO v_exists
      FROM customers
     WHERE id = p_customer_id;

    IF v_exists = 0 THEN
        SET p_new_credit = NULL;
        SET p_status = 'NOT_FOUND';
    ELSE
        UPDATE customers
           SET credit_limit = credit_limit + p_delta
         WHERE id = p_customer_id;

        SELECT credit_limit
          INTO p_new_credit
          FROM customers
         WHERE id = p_customer_id;

        SET p_status = 'UPDATED';
    END IF;
END//

DELIMITER ;
```

Đây là DDL riêng của MySQL; delimiter và kiểu dữ liệu có thể khác ở PostgreSQL, SQL Server, Oracle hoặc database khác.

Đặt metadata cho thủ tục trên entity `Customer`:

**Customer.java** — phần khai báo liên quan:

```java
package com.example.customer;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.NamedStoredProcedureQuery;
import jakarta.persistence.ParameterMode;
import jakarta.persistence.StoredProcedureParameter;
import jakarta.persistence.Table;
import java.math.BigDecimal;

@Entity
@Table(name = "customers")
@NamedStoredProcedureQuery(
    name = "Customer.updateCredit",
    procedureName = "update_customer_credit",
    parameters = {
        @StoredProcedureParameter(
            mode = ParameterMode.IN,
            name = "p_customer_id",
            type = Long.class
        ),
        @StoredProcedureParameter(
            mode = ParameterMode.IN,
            name = "p_delta",
            type = BigDecimal.class
        ),
        @StoredProcedureParameter(
            mode = ParameterMode.OUT,
            name = "p_new_credit",
            type = BigDecimal.class
        ),
        @StoredProcedureParameter(
            mode = ParameterMode.OUT,
            name = "p_status",
            type = String.class
        )
    }
)
public class Customer {

    @Id
    private Long id;

    protected Customer() {
    }
}
```

Đoạn mã thể hiện phần entity cần cho ánh xạ thủ tục; trong ứng dụng thật, entity còn có các thuộc tính và mapping cột tương ứng với bảng `customers`.

Mỗi tham số cần khai báo đúng mode, tên và kiểu Java tương ứng với chữ ký database. Thứ tự khai báo cũng cần khớp với thứ tự tham số của thủ tục để tương thích với provider và driver có cách bind theo vị trí. Tên tham số giúp mã dễ đọc, nhưng không phải database/driver nào cũng hỗ trợ bind theo tên giống nhau.

## 3. Ánh xạ một OUT parameter bằng `@Procedure`

Nếu thủ tục chỉ trả một OUT parameter mà repository method cần sử dụng, có thể ánh xạ giá trị đó trực tiếp vào kiểu trả về.

Ví dụ thủ tục có tên database là `get_customer_credit`, nhận mã khách hàng và trả `p_credit`:

```java
package com.example.customer;

import java.math.BigDecimal;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.query.Procedure;
import org.springframework.data.repository.query.Param;
import org.springframework.transaction.annotation.Transactional;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @Transactional
    @Procedure(
        procedureName = "get_customer_credit",
        outputParameterName = "p_credit"
    )
    BigDecimal getCredit(
        @Param("p_customer_id") Long customerId
    );
}
```

Ở đây:

- `procedureName` trỏ tới tên thủ tục trong database.
- `outputParameterName` chỉ rõ OUT parameter cần dùng làm kết quả method.
- `@Param` gắn đối số Java với tham số IN.
- Kiểu trả về `BigDecimal` cần tương thích với kiểu OUT parameter.

Nếu đã khai báo `@NamedStoredProcedureQuery`, có thể tham chiếu tên logic bằng `@Procedure(name = "Customer.updateCredit")`. Thuộc tính `name` trong trường hợp này là tên named query JPA, khác với `procedureName` là tên thủ tục database.

## 4. Ánh xạ nhiều OUT parameter thành Map

Một thủ tục có nhiều OUT parameter không thể biểu diễn đầy đủ bằng một scalar return value. Spring Data JPA cho phép repository method trả về `Map<String, Object>` khi tham chiếu named stored procedure.

**CustomerRepository.java** — bổ sung phương thức:

```java
@Transactional
@Procedure(name = "Customer.updateCredit")
Map<String, Object> updateCredit(
    @Param("p_customer_id") Long customerId,
    @Param("p_delta") BigDecimal delta
);
```

Cách gọi:

```java
Map<String, Object> output =
    customerRepository.updateCredit(42L, new BigDecimal("25.00"));

BigDecimal newCredit =
    (BigDecimal) output.get("p_new_credit");

String status =
    (String) output.get("p_status");
```

Map chứa các giá trị OUT được provider trả về, được truy cập theo tên tham số đã khai báo. Cần kiểm tra key thực tế bằng integration test trên database/driver đang sử dụng; quy tắc chữ hoa, chữ thường và cách expose tên có thể khác giữa provider.

Không nhầm Map OUT với một result set: Map là tập giá trị tham số đầu ra, còn result set là danh sách hàng từ câu SELECT. Nếu thủ tục trả nhiều OUT và nhiều result set cùng lúc, hãy cân nhắc JPA `StoredProcedureQuery` hoặc JDBC để điều khiển toàn bộ luồng kết quả.

## 5. Ánh xạ result set thành DTO

Một thủ tục có thể trả các hàng dữ liệu. Nếu cột kết quả không khớp trực tiếp entity, có thể dùng `@SqlResultSetMapping` cùng `@ConstructorResult` để ánh xạ sang DTO.

Hai DTO Java:

**CustomerSummary.java**

```java
package com.example.customer;

public record CustomerSummary(
    Long customerId,
    String customerName
) {
}
```

**RegionSummary.java**

```java
package com.example.customer;

public record RegionSummary(
    String region,
    Long orderCount
) {
}
```

Khai báo hai mapping trên một entity được quản lý, ví dụ `Customer`:

```java
@SqlResultSetMappings({
    @SqlResultSetMapping(
        name = "CustomerSummaryMapping",
        classes = @ConstructorResult(
            targetClass = CustomerSummary.class,
            columns = {
                @ColumnResult(name = "customer_id", type = Long.class),
                @ColumnResult(name = "customer_name", type = String.class)
            }
        )
    ),
    @SqlResultSetMapping(
        name = "RegionSummaryMapping",
        classes = @ConstructorResult(
            targetClass = RegionSummary.class,
            columns = {
                @ColumnResult(name = "region", type = String.class),
                @ColumnResult(name = "order_count", type = Long.class)
            }
        )
    )
})
@Entity
@Table(name = "customers")
public class Customer {
    // Entity fields and mappings.
}
```

Các tên trong `@ColumnResult` phải khớp alias cột được procedure trả về. Thứ tự cột trong `@ConstructorResult` phải khớp thứ tự tham số constructor của DTO.

Ví dụ procedure MySQL trả hai result set:

```sql
DELIMITER //

CREATE PROCEDURE customer_report(
    IN p_year INT,
    OUT p_total BIGINT
)
BEGIN
    SELECT id AS customer_id,
           name AS customer_name
      FROM customers
     WHERE YEAR(created_at) = p_year
     ORDER BY id;

    SELECT region,
           COUNT(*) AS order_count
      FROM orders
     WHERE YEAR(created_at) = p_year
     GROUP BY region
     ORDER BY region;

    SELECT COUNT(*)
      INTO p_total
      FROM orders
     WHERE YEAR(created_at) = p_year;
END//

DELIMITER ;
```

Result set thứ nhất có các cột `customer_id` và `customer_name`; result set thứ hai có `region` và `order_count`. OUT parameter `p_total` trả tổng số đơn hàng của năm được truyền vào.

## 6. Duyệt nhiều result set bằng `StoredProcedureQuery`

Repository method `@Procedure` phù hợp với các chữ ký đơn giản. Khi cần xử lý nhiều result set theo thứ tự, xen kẽ update count và đọc OUT parameter, JPA API cho phép điều khiển rõ ràng hơn.

Tạo kết quả tổng hợp:

**CustomerReport.java**

```java
package com.example.customer;

import java.util.List;

public record CustomerReport(
    List<CustomerSummary> customers,
    List<RegionSummary> regions,
    Long totalOrders
) {
}
```

DAO/repository tùy biến:

**CustomerReportDao.java**

```java
package com.example.customer;

import jakarta.persistence.EntityManager;
import jakarta.persistence.ParameterMode;
import jakarta.persistence.PersistenceContext;
import jakarta.persistence.StoredProcedureQuery;
import java.util.ArrayList;
import java.util.List;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class CustomerReportDao {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public CustomerReport loadReport(int year) {
        StoredProcedureQuery query =
            entityManager.createStoredProcedureQuery(
                "customer_report",
                "CustomerSummaryMapping",
                "RegionSummaryMapping"
            );

        query.registerStoredProcedureParameter(
            "p_year", Integer.class, ParameterMode.IN
        );
        query.registerStoredProcedureParameter(
            "p_total", Long.class, ParameterMode.OUT
        );
        query.setParameter("p_year", year);

        List<List<?>> resultSets = new ArrayList<>();

        boolean hasResultSet = query.execute();

        while (true) {
            if (hasResultSet) {
                resultSets.add(query.getResultList());
            } else if (query.getUpdateCount() == -1) {
                break;
            }

            hasResultSet = query.hasMoreResults();
        }

        if (resultSets.size() != 2) {
            throw new IllegalStateException(
                "Expected two result sets, got " + resultSets.size()
            );
        }

        @SuppressWarnings("unchecked")
        List<CustomerSummary> customers =
            (List<CustomerSummary>) (List<?>) resultSets.get(0);

        @SuppressWarnings("unchecked")
        List<RegionSummary> regions =
            (List<RegionSummary>) (List<?>) resultSets.get(1);

        Number totalValue =
            (Number) query.getOutputParameterValue("p_total");

        Long totalOrders =
            totalValue == null ? null : totalValue.longValue();

        return new CustomerReport(customers, regions, totalOrders);
    }
}
```

Cách hoạt động:

1. `createStoredProcedureQuery` nhận tên procedure và các result set mapping theo thứ tự procedure trả về.
2. Đăng ký tham số IN và OUT, sau đó gán giá trị IN.
3. `execute()` chạy thủ tục và cho biết kết quả hiện tại có phải result set hay không.
4. Nếu là result set, gọi `getResultList()`; nếu là update count, đọc `getUpdateCount()`.
5. Gọi `hasMoreResults()` để chuyển sang kết quả tiếp theo cho tới khi không còn result set hoặc update count.
6. Sau khi xử lý các kết quả, đọc OUT parameter bằng `getOutputParameterValue()`.

Việc xử lý cả update count là cần thiết vì stored procedure có thể chạy câu DML trước khi trả SELECT. Nếu chỉ gọi `getResultList()` một lần, ứng dụng có thể bỏ qua result set tiếp theo.

Tên result set mapping trong ví dụ phải được khai báo trên một entity mapping được JPA quản lý. Database, driver và provider cần hỗ trợ cách trả nhiều result set tương ứng; hãy xác minh thứ tự và kiểu dữ liệu thực tế trong integration test.

## 7. Khi nào dùng `REF_CURSOR` hoặc JDBC?

Một số database, đặc biệt các hệ quản trị có hỗ trợ cursor parameter, trả result set thông qua `REF_CURSOR`. JPA có `ParameterMode.REF_CURSOR`, nhưng khả năng đăng ký và đọc cursor phụ thuộc database, JDBC driver và provider. Không giả định mọi database hỗ trợ giống nhau.

Nếu provider không xử lý đúng nhiều result set, update count hoặc cursor của database đang dùng, có thể gọi procedure qua Spring JDBC (`JdbcTemplate`, `SimpleJdbcCall`) và `CallableStatement`. JDBC cho phép dùng `getMoreResults()`, `getUpdateCount()` và đọc OUT parameter theo khả năng driver. Khi dùng JDBC trong cùng ứng dụng, hãy bảo đảm nó dùng cùng `DataSource` và transaction manager phù hợp để thao tác tham gia đúng transaction.

Không trộn lẫn nhiều cách gọi trong một transaction mà không hiểu rõ connection và transaction boundary. Một procedure có thể tự commit hoặc rollback nếu database cho phép; hành vi đó có thể ảnh hưởng đến transaction do Spring quản lý.

## 8. Transaction, lỗi mapping và kiểm thử

Stored procedure có thể đọc hoặc thay đổi dữ liệu. Với thủ tục có DML, đặt transaction boundary rõ ràng bằng `@Transactional` trên service hoặc DAO. Tránh chỉ dựa vào việc method nằm trong repository mà không kiểm tra transaction semantics của query method.

Một số lỗi thường gặp:

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Không tìm thấy procedure | Sai schema, tên hoặc quyền execute | Kiểm tra DDL, schema hiện tại và quyền database user |
| Procedure chạy nhưng OUT là null/sai kiểu | Sai mode, thứ tự, tên hoặc kiểu Java/JDBC | Đối chiếu chữ ký procedure và `@StoredProcedureParameter`; kiểm tra provider/driver |
| Map không có key mong đợi | Khác biệt cách expose tên OUT parameter | In/log key trong môi trường test; xác nhận tên theo provider và database |
| DTO mapping lỗi cột | Alias SELECT không khớp `@ColumnResult` | So sánh tên cột, kiểu dữ liệu và thứ tự constructor |
| Chỉ đọc được result set đầu | Chưa duyệt `hasMoreResults()` hoặc driver không hỗ trợ | Xử lý cả update count và kiểm tra hỗ trợ multi-result của driver |
| Test pass trên H2 nhưng fail production | Khác biệt cú pháp procedure, cursor, OUT parameter hoặc kiểu dữ liệu | Chạy integration test với cùng họ database hoặc Testcontainers |

Với stored procedure, H2 không phải lúc nào cũng mô phỏng được cú pháp và hành vi của database production. Hãy ưu tiên integration test với đúng database family, driver và phiên bản gần production. Test nên xác nhận:

- Giá trị trả về của scalar OUT parameter.
- Từng key/value của Map khi có nhiều OUT parameter.
- Số lượng, thứ tự, alias và kiểu dữ liệu của mỗi result set.
- OUT parameter sau khi đã tiêu thụ result set, nếu thủ tục trả cả hai loại.
- Transaction commit/rollback và side effect của thủ tục.
- Hành vi khi tham số không hợp lệ hoặc không tìm thấy dữ liệu.

Không dùng mock repository để kết luận stored procedure mapping đúng. Mock chỉ kiểm tra lời gọi Java, không xác minh procedure có tồn tại, tham số có bind đúng hay result set có ánh xạ đúng.

## 9. Chọn cách ánh xạ phù hợp

| Nhu cầu | Cách tiếp cận |
|---|---|
| Một OUT parameter, chữ ký đơn giản | `@Procedure` trả về scalar |
| Nhiều OUT parameter, không cần duyệt nhiều result set | `@NamedStoredProcedureQuery` + `@Procedure` trả `Map<String, Object>` |
| Một result set ánh xạ entity/DTO | `@Procedure` hoặc `StoredProcedureQuery` với result mapping phù hợp |
| Nhiều result set hoặc kết hợp update count và OUT | `EntityManager.createStoredProcedureQuery()` và duyệt `hasMoreResults()` |
| Cần điều khiển chi tiết theo khả năng driver | Spring JDBC với `CallableStatement` |

Khi ánh xạ stored procedure, hãy xem chữ ký database là hợp đồng: mode, tên, thứ tự và kiểu tham số phải khớp; alias và cấu trúc result set phải khớp mapping. Dùng `@Procedure` cho chữ ký đơn giản, `Map` cho nhiều OUT parameter, và API JPA/JDBC mức thấp hơn khi cần xử lý nhiều tập kết quả.