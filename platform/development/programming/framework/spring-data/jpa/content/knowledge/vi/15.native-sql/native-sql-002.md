# Khai báo @Query với nativeQuery và khả năng dùng @NativeQuery theo phiên bản

## Mục tiêu

Sau bài này, bạn có thể viết truy vấn SQL thuần trong Spring Data JPA bằng `@Query(nativeQuery = true)`; nhận biết `@NativeQuery` từ Spring Data JPA 3.4; chọn cách ánh xạ kết quả về entity, interface projection hoặc DTO; xử lý tham số, phân trang, count query và câu lệnh cập nhật/xóa; đồng thời biết giới hạn về tính portable, sort động và tương thích phiên bản.

Các ví dụ dùng Java 17+, Spring Boot 3+ và Jakarta Persistence. Tên bảng/cột trong SQL phải khớp schema thật. Những đoạn repository giả định ứng dụng đã có `spring-boot-starter-data-jpa`, entity tương ứng và `DataSource` hoạt động.

## 1. Native SQL khác JPQL như thế nào?

Spring Data JPA cho phép viết truy vấn theo hai cách chính:

- **JPQL** truy vấn entity và thuộc tính Java. Provider chuyển JPQL thành SQL phù hợp với database.
- **Native SQL** là câu SQL của hệ quản trị database. Bạn viết trực tiếp tên bảng, tên cột, hàm, phép nối và cú pháp mà database hỗ trợ.

Ví dụ cùng một mục tiêu tìm khách hàng theo trạng thái:

JPQL:

```java
@Query("select c from Customer c where c.status = :status")
List<Customer> findByStatus(@Param("status") String status);
```

Native SQL:

```java
@Query(
    value = "select c.* from customers c where c.status = :status",
    nativeQuery = true
)
List<Customer> findByStatusNative(@Param("status") String status);
```

JPQL dùng `Customer` và `status` là tên entity/property. Native SQL dùng `customers` và `status` là tên bảng/cột trong database. Nếu entity ánh xạ `status` sang cột `customer_status`, câu SQL thuần phải dùng `customer_status`.

Native query hữu ích khi cần:

- Dùng CTE (`WITH`), window function, JSON operator, full-text search hoặc tính năng riêng của database.
- Tối ưu một truy vấn phức tạp đã được phân tích bằng execution plan.
- Dùng câu SQL có cấu trúc khó diễn đạt hoặc khó bảo đảm hiệu năng bằng JPQL.
- Gọi câu lệnh SQL đặc thù, view hoặc stored procedure theo cách mà repository hỗ trợ.

Native SQL làm ứng dụng phụ thuộc nhiều hơn vào schema và dialect. Nếu JPQL hoặc derived query đáp ứng tốt yêu cầu, chúng thường dễ bảo trì và chuyển database hơn.

## 2. Dùng @Query(nativeQuery = true)

`@Query` là annotation của Spring Data JPA. Thuộc tính `nativeQuery = true` báo cho Spring Data rằng chuỗi truy vấn là SQL thuần, không phải JPQL.

Ví dụ repository:

```java
package com.example.learning.customer;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface CustomerRepository extends JpaRepository<Customer, Long> {

    @Query(
        value = """
            SELECT c.*
            FROM customers c
            WHERE c.status = :status
            ORDER BY c.created_at DESC, c.id DESC
            """,
        nativeQuery = true
    )
    List<Customer> findNativeByStatus(@Param("status") String status);
}
```

Trong ví dụ:

- `value` chứa SQL thực tế gửi tới database.
- `nativeQuery = true` bật chế độ native query.
- `:status` là named parameter; `@Param("status")` liên kết tham số Java với tên đó.
- `customers`, `status`, `created_at` và `id` phải đúng với schema vật lý.
- `ORDER BY` được viết rõ trong SQL để kết quả có thứ tự ổn định.

Vì phương thức trả về `Customer`, câu SQL cần chọn đủ các cột cần thiết để provider dựng entity. `SELECT c.*` phù hợp với ví dụ bảng đơn giản này. Không nên chọn vài cột tùy ý rồi yêu cầu JPA dựng một entity đầy đủ; hãy dùng projection hoặc DTO khi chỉ cần một phần dữ liệu.

### 2.1. Named parameter và positional parameter

Named parameter thường dễ đọc và ít nhầm thứ tự:

```java
@Query(
    value = "SELECT c.* FROM customers c WHERE c.status = :status AND c.active = :active",
    nativeQuery = true
)
List<Customer> search(
    @Param("status") String status,
    @Param("active") boolean active
);
```

Có thể dùng positional parameter theo thứ tự tham số:

```java
@Query(
    value = "SELECT c.* FROM customers c WHERE c.status = ?1 AND c.active = ?2",
    nativeQuery = true
)
List<Customer> search(String status, boolean active);
```

Trong Spring Data JPA, positional parameter trong chuỗi `@Query` dùng chỉ số `?1`, `?2`, ... tương ứng với thứ tự tham số. Khi dùng named parameter, nên khai báo `@Param` tường minh để tên liên kết rõ ràng và không phụ thuộc cấu hình biên dịch giữ tên tham số.

### 2.2. Bind giá trị, không nối chuỗi SQL

Không tạo câu SQL bằng cách ghép trực tiếp dữ liệu request:

```java
// Không an toàn: không nối input người dùng vào SQL.
String sql = "SELECT * FROM customers WHERE email = '" + email + "'";
```

Hãy dùng bind parameter:

```java
@Query(value = "SELECT c.* FROM customers c WHERE c.email = :email", nativeQuery = true)
Optional<Customer> findByEmailNative(@Param("email") String email);
```

Bind parameter giúp tách dữ liệu khỏi cấu trúc câu lệnh, giảm nguy cơ SQL injection và xử lý kiểu dữ liệu đúng. Parameter chỉ đại diện cho **giá trị**; nó không thay thế được tên bảng, tên cột, từ khóa `ASC`/`DESC` hoặc một đoạn SQL tùy ý.

Nếu cần chọn cột sort từ request, hãy ánh xạ đầu vào qua danh sách cho phép trong code rồi chọn một query/nhánh SQL tương ứng. Không nối trực tiếp tên cột hoặc hướng sort do người dùng gửi vào câu SQL.

## 3. @NativeQuery là gì và có từ phiên bản nào?

`@NativeQuery` là annotation riêng của Spring Data JPA, được giới thiệu từ **Spring Data JPA 3.4.0**. Nó là một annotation chuyên cho native SQL, được xây dựng trên `@Query(nativeQuery = true)` và cung cấp thêm thuộc tính như `sqlResultSetMapping` để chỉ định cách ánh xạ result set theo Jakarta Persistence.

Import:

```java
import org.springframework.data.jpa.repository.NativeQuery;
```

Ví dụ:

```java
package com.example.learning.customer;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.NativeQuery;
import org.springframework.data.repository.query.Param;

public interface CustomerRepository extends JpaRepository<Customer, Long> {

    @NativeQuery("""
        SELECT c.*
        FROM customers c
        WHERE c.status = :status
        ORDER BY c.created_at DESC, c.id DESC
        """)
    List<Customer> findByStatusUsingNativeQuery(
        @Param("status") String status
    );
}
```

Với nhu cầu native SQL cơ bản, `@NativeQuery` và `@Query(nativeQuery = true)` có mục đích tương đương. Bạn không cần đổi toàn bộ repository cũ sang annotation mới; có thể tiếp tục dùng `@Query` nếu muốn tương thích với các phiên bản Spring Data JPA trước 3.4.

### 3.1. Khả năng theo phiên bản

| Phiên bản Spring Data JPA | Cách khai báo native SQL |
| --- | --- |
| Trước 3.4.0 | Dùng `@Query(value = "...", nativeQuery = true)` |
| 3.4.0 trở lên | Dùng `@Query(nativeQuery = true)` hoặc `@NativeQuery` |

Spring Boot 3.4 trở lên thường quản lý một phiên bản Spring Data JPA có `@NativeQuery` thông qua dependency management. Tuy nhiên, phiên bản thực tế có thể khác nếu dự án override dependency hoặc BOM. Hãy kiểm tra artifact đã resolve thay vì chỉ nhìn số phiên bản Spring Boot.

Nếu IDE báo không tìm thấy `NativeQuery`, nguyên nhân thường là Spring Data JPA đang ở phiên bản thấp hơn 3.4 hoặc dependency classpath chưa được cập nhật. Có thể dùng `@Query(nativeQuery = true)` ngay, hoặc nâng Spring Data theo bộ dependency tương thích của Spring Boot. Tránh nâng riêng `spring-data-jpa` mà không kiểm tra tương thích với các module Spring Data khác.

### 3.2. Kiểm tra phiên bản thực tế

Với Maven:

```bash
./mvnw dependency:tree -Dincludes=org.springframework.data:spring-data-jpa
```

Với Gradle:

```bash
./gradlew dependencyInsight --dependency spring-data-jpa --configuration runtimeClasspath
```

Trên Windows PowerShell có thể chạy `./mvnw.cmd` hoặc `./gradlew.bat`. Hãy xem phiên bản `spring-data-jpa` được resolve trong dependency tree/insight. Nếu dự án dùng Spring Boot BOM, ưu tiên nâng Boot lên phiên bản phù hợp để nhận một bộ Spring Data đồng bộ.

## 4. Ánh xạ kết quả native query

Native SQL có thể trả về entity, projection, DTO hoặc dữ liệu scalar. Kiểu trả về của repository phải phù hợp với cột được chọn và cách mapping.

### 4.1. Trả về entity

```java
@NativeQuery("SELECT c.* FROM customers c WHERE c.id = :id")
Optional<Customer> findEntityByIdNative(@Param("id") Long id);
```

Dùng khi kết quả đại diện cho một entity được quản lý bởi persistence context. Câu SQL cần trả đủ các cột mà entity mapping yêu cầu, gồm khóa chính và các cột persistent liên quan. Nếu entity có quan hệ hoặc inheritance mapping, hãy kiểm tra yêu cầu của mapping cụ thể.

### 4.2. Interface projection

Nếu chỉ cần một vài cột, dùng projection để tránh tải toàn bộ entity:

```java
package com.example.learning.customer;

public interface CustomerEmailView {
    Long getId();
    String getEmail();
}
```

Repository:

```java
@NativeQuery("""
    SELECT c.id AS id, c.email AS email
    FROM customers c
    WHERE c.status = :status
    """)
List<CustomerEmailView> findEmailViewsByStatus(
    @Param("status") String status
);
```

Alias trong SQL nên khớp tên property mà projection yêu cầu, ở đây là `id` và `email`. Quy tắc viết hoa/viết thường và cách database trả column label có thể khác nhau; nếu alias có camelCase hoặc tên đặc biệt, hãy kiểm tra cách database xử lý identifier và dùng dấu quote theo dialect khi cần.

Projection phù hợp cho danh sách đọc, màn hình tổng hợp và API chỉ cần một phần dữ liệu. Nó không phải entity managed; không dùng projection như một object để cập nhật persistence state.

### 4.3. DTO với @SqlResultSetMapping

Với DTO class cần constructor mapping rõ ràng, Jakarta Persistence cung cấp `@SqlResultSetMapping` và `@ConstructorResult`. Ví dụ DTO:

```java
package com.example.learning.customer;

public class CustomerSummaryDto {
    private final Long id;
    private final String email;

    public CustomerSummaryDto(Long id, String email) {
        this.id = id;
        this.email = email;
    }

    public Long getId() { return id; }
    public String getEmail() { return email; }
}
```

Khai báo mapping trên một entity trong persistence unit:

```java
package com.example.learning.customer;

import jakarta.persistence.ColumnResult;
import jakarta.persistence.ConstructorResult;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.SqlResultSetMapping;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
@SqlResultSetMapping(
    name = "CustomerSummaryMapping",
    classes = @ConstructorResult(
        targetClass = CustomerSummaryDto.class,
        columns = {
            @ColumnResult(name = "customer_id", type = Long.class),
            @ColumnResult(name = "email", type = String.class)
        }
    )
)
public class Customer {
    @Id
    private Long id;

    private String email;

    protected Customer() {
    }
}
```

Repository dùng `sqlResultSetMapping` của `@NativeQuery`:

```java
@NativeQuery(
    value = """
        SELECT c.id AS customer_id, c.email AS email
        FROM customers c
        WHERE c.status = :status
        """,
    sqlResultSetMapping = "CustomerSummaryMapping"
)
List<CustomerSummaryDto> findSummaries(
    @Param("status") String status
);
```

Tên `customer_id` và `email` trong `@ColumnResult` phải khớp column label mà SQL trả về. Thứ tự và kiểu các `ColumnResult` phải tương thích với constructor DTO. `sqlResultSetMapping` là điểm tiện lợi bổ sung của `@NativeQuery` từ Spring Data JPA 3.4; nếu dùng phiên bản cũ, có thể thực hiện mapping bằng `EntityManager.createNativeQuery(sql, mappingName)` trong custom repository.

Đây là các tệp minh họa trong cùng package; trong ứng dụng thật, chỉ khai báo một entity `Customer` và bổ sung mapping vào entity hiện có, không tạo thêm class trùng tên.

## 5. Phân trang native query với countQuery

Khi repository trả `Page<T>`, Spring Data cần biết tổng số hàng phù hợp để tạo thông tin trang. Với native SQL, hãy khai báo `countQuery` tường minh cho truy vấn phức tạp hoặc khi không muốn phụ thuộc khả năng phân tích SQL tự động.

Ví dụ:

```java
@Query(
    value = """
        SELECT c.*
        FROM customers c
        WHERE c.status = :status
        ORDER BY c.created_at DESC, c.id DESC
        """,
    countQuery = """
        SELECT COUNT(*)
        FROM customers c
        WHERE c.status = :status
        """,
    nativeQuery = true
)
Page<Customer> findPageByStatus(
    @Param("status") String status,
    Pageable pageable
);
```

Với Spring Data JPA 3.4+, có thể viết tương đương bằng `@NativeQuery`:

```java
@NativeQuery(
    value = """
        SELECT c.*
        FROM customers c
        WHERE c.status = :status
        ORDER BY c.created_at DESC, c.id DESC
        """,
    countQuery = """
        SELECT COUNT(*)
        FROM customers c
        WHERE c.status = :status
        """
)
Page<Customer> findPageByStatusNative(
    @Param("status") String status,
    Pageable pageable
);
```

`countQuery` phải áp dụng cùng điều kiện lọc với query chính. Nếu query chính join bảng một-nhiều và có thể tạo nhiều hàng cho một customer, `COUNT(*)` có thể đếm trùng; khi đó cần đếm đúng đơn vị kết quả, ví dụ `COUNT(DISTINCT c.id)`, và kiểm thử với dữ liệu có nhiều quan hệ.

Native SQL đơn giản đôi khi được Spring Data phân tích để tạo count query, nhưng query có CTE, subquery, union, group by hoặc cú pháp riêng của database có thể vượt khả năng rewrite. Khai báo `countQuery` rõ ràng thường dễ kiểm soát hơn. Spring Data JPA cũng có thể dùng JSqlParser nếu thư viện đó có trên classpath, nhưng parser không loại bỏ nhu cầu kiểm tra SQL và kết quả count.

### 5.1. Page, Slice và List

- `Page<T>` cung cấp tổng số phần tử và tổng số trang; thường cần thêm count query.
- `Slice<T>` cho biết còn trang tiếp theo hay không; có thể tránh truy vấn đếm tổng số bản ghi.
- `List<T>` không mang metadata phân trang; phù hợp khi số kết quả đã được giới hạn hoặc use case không cần phân trang.

Chọn `Page` khi giao diện thật sự cần tổng số trang. Với bảng lớn, count query có thể tốn kém; `Slice` có thể phù hợp hơn.

### 5.2. Sort động với native query

Không nên mặc định rằng `Pageable` hoặc `Sort` có thể chèn một `ORDER BY` bất kỳ vào mọi native SQL. Việc rewrite câu SQL phụ thuộc dialect và độ phức tạp query; các CTE, union, subquery hoặc alias có thể khiến việc thêm sort không an toàn hoặc không được hỗ trợ.

Với native query, cách dễ kiểm soát là viết `ORDER BY` cố định trong SQL. Nếu cần sort động, dùng một tập lựa chọn cột/hướng sort được whitelist trong code hoặc xây dựng custom repository với logic riêng. Không nối trực tiếp chuỗi sort từ request.

## 6. Native query cập nhật hoặc xóa dữ liệu

Native query không chỉ dùng để đọc. Có thể dùng `@Modifying` cùng `@Query(nativeQuery = true)` hoặc `@NativeQuery` cho `UPDATE`/`DELETE`.

Ví dụ repository:

```java
@Modifying(flushAutomatically = true, clearAutomatically = true)
@Query(
    value = """
        UPDATE customers
        SET active = :active
        WHERE last_login_at < :cutoff
        """,
    nativeQuery = true
)
int updateActiveBefore(
    @Param("active") boolean active,
    @Param("cutoff") Instant cutoff
);
```

Service gọi trong transaction:

```java
package com.example.learning.customer;

import java.time.Instant;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerMaintenanceService {
    private final CustomerRepository customers;

    public CustomerMaintenanceService(CustomerRepository customers) {
        this.customers = customers;
    }

    @Transactional
    public int deactivateBefore(Instant cutoff) {
        return customers.updateActiveBefore(false, cutoff);
    }
}
```

`@Modifying` báo cho Spring Data rằng query method thực hiện thao tác ghi. Phương thức phải chạy trong transaction; có thể đặt `@Transactional` ở service như ví dụ hoặc ở repository method theo thiết kế ứng dụng. Giá trị trả về kiểu `int` là số hàng được database cập nhật.

Bulk update/delete chạy trực tiếp trên database và không đi qua dirty checking của từng entity. Entity đang nằm trong persistence context có thể giữ dữ liệu cũ. `flushAutomatically = true` yêu cầu flush thay đổi đang chờ trước khi chạy query; `clearAutomatically = true` xóa persistence context sau query để tránh tiếp tục dùng entity stale.

`clearAutomatically` ảnh hưởng tới tất cả entity đang được quản lý trong persistence context hiện tại, không chỉ các customer được cập nhật. Nếu không muốn clear toàn bộ, hãy cân nhắc refresh entity liên quan hoặc quản lý ranh giới persistence context rõ ràng.

Với `@NativeQuery` trên Spring Data JPA 3.4+, có thể kết hợp `@Modifying` theo cùng nguyên tắc vì đây là annotation chuyên native query của Spring Data. Dù dùng annotation nào, vẫn cần transaction và phải kiểm tra trạng thái persistence context sau bulk operation.

## 7. Native query với IN, NULL và kiểu dữ liệu

Native SQL tuân theo quy tắc của database. Ví dụ:

```sql
SELECT c.*
FROM customers c
WHERE c.status IN ('NEW', 'ACTIVE');
```

Đối với tham số collection, cách bind danh sách trong native query có thể phụ thuộc JPA provider, database và cách provider mở rộng bind parameter. Nếu cần truyền nhiều giá trị, hãy kiểm thử trên đúng database production. Với truy vấn đơn giản, derived query hoặc JPQL `IN :statuses` thường portable hơn.

SQL vẫn có logic ba giá trị: `column = NULL` không tìm được hàng null; phải dùng `IS NULL`. `NOT IN` với tập có phần tử `NULL` có thể làm điều kiện thành `UNKNOWN` và loại nhiều hàng ngoài dự kiến. Hãy lọc phần tử null ở service hoặc viết điều kiện `IS NULL` riêng nếu nghiệp vụ cần.

Kiểu Java truyền vào phải tương thích kiểu SQL. Ví dụ `Instant` có thể được map sang timestamp theo provider/database; enum cần thống nhất cách lưu chuỗi hay ordinal; UUID, JSON, array và kiểu đặc thù có thể cần mapping riêng. Khi dùng native SQL, không giả định tên hàm hoặc cách cast của một database sẽ chạy trên database khác.

## 8. Stored procedure, CTE và tính năng riêng của database

Native SQL phù hợp khi cần dùng cú pháp database mà JPQL không biểu diễn được. Ví dụ PostgreSQL có thể dùng CTE và window function:

```sql
WITH ranked_customers AS (
    SELECT
        c.id,
        c.email,
        c.status,
        ROW_NUMBER() OVER (
            PARTITION BY c.status
            ORDER BY c.created_at DESC, c.id DESC
        ) AS row_number
    FROM customers c
)
SELECT id, email, status
FROM ranked_customers
WHERE row_number = 1;
```

Ví dụ trên lấy customer mới nhất trong từng status theo thứ tự xác định. Đây là SQL minh họa theo cú pháp hỗ trợ bởi các database hiện đại; cần xác nhận khả năng CTE/window function và tên cột ở hệ quản trị đang dùng.

Nếu cần gọi stored procedure, JPA có `@Procedure` và `StoredProcedureQuery`; native SQL không phải lúc nào cũng là cách tốt nhất. Chọn API phù hợp với cách procedure nhận tham số, trả result set và được quản lý trong transaction.

## 9. Tổ chức repository và custom repository

Không nên để một repository chứa hàng loạt native SQL rất dài nếu chúng phục vụ các truy vấn phức tạp khác nhau. Có thể tách custom repository khi cần:

- Ghép điều kiện động có whitelist.
- Dùng nhiều câu SQL theo dialect.
- Ánh xạ nhiều result set hoặc DTO đặc biệt.
- Tối ưu truy vấn cần hint hoặc cấu hình provider.
- Kiểm soát pagination, sorting và count query theo một cách riêng.

Ví dụ cấu trúc:

```text
customer/
├── Customer.java
├── CustomerRepository.java
├── CustomerRepositoryCustom.java
├── CustomerRepositoryImpl.java
├── CustomerSummaryView.java
└── CustomerService.java
```

`CustomerRepository` vẫn giữ CRUD và các derived query đơn giản. `CustomerRepositoryCustom` khai báo API tùy biến; `CustomerRepositoryImpl` dùng `EntityManager` hoặc `JdbcTemplate` khi cần kiểm soát SQL và mapping chi tiết hơn.

Đặt native query ở repository method khi câu lệnh tĩnh, ngắn và dễ hiểu. Chuyển sang custom repository khi cần logic xây dựng SQL hoặc xử lý kết quả phức tạp.

## 10. Kiểm thử native query

Native SQL cần được kiểm thử trên database gần với môi trường chạy thật, đặc biệt khi dùng cú pháp riêng, JSON, CTE, window function, hint, kiểu dữ liệu đặc thù hoặc count query.

Với query portable và schema đơn giản, có thể dùng `@DataJpaTest` cùng H2:

```java
package com.example.learning.customer;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class CustomerNativeQueryTest {
    @Autowired
    private CustomerRepository customers;

    @Test
    void findsCustomersUsingNativeSql() {
        customers.saveAll(List.of(
            new Customer("a@example.test", "ACTIVE"),
            new Customer("b@example.test", "SUSPENDED")
        ));
        customers.flush();

        List<Customer> result = customers.findNativeByStatus("ACTIVE");

        assertThat(result)
            .extracting(Customer::getEmail)
            .containsExactly("a@example.test");
    }
}
```

Đoạn test giả định entity `Customer` có constructor `Customer(String email, String status)`, getter `getEmail()` và repository method `findNativeByStatus` như ví dụ trước; project có `spring-boot-starter-test` và H2 trong test runtime.

H2 không mô phỏng đầy đủ mọi cú pháp PostgreSQL, MySQL, SQL Server hay Oracle. Nếu native SQL dùng tính năng riêng, hãy chạy integration test với cùng hệ quản trị, thường thông qua Testcontainers hoặc database test chuyên dụng.

Với truy vấn phân trang, kiểm tra cả nội dung trang và tổng số hàng. Với update/delete, kiểm tra số hàng bị tác động và đọc lại dữ liệu sau khi persistence context đã được refresh/clear. Với projection/DTO, kiểm tra alias, kiểu dữ liệu và thứ tự constructor mapping.

## 11. Những lỗi thường gặp

- **Quên `nativeQuery = true` khi dùng SQL trong `@Query`.** Spring sẽ phân tích chuỗi như JPQL và có thể báo lỗi entity/property không tồn tại.
- **Dùng tên entity/property trong native SQL.** SQL cần tên bảng/cột vật lý theo schema.
- **Chọn thiếu cột khi trả về entity.** Provider không có đủ dữ liệu để hydrate entity; dùng projection/DTO nếu chỉ cần một phần.
- **Quên `@Param` hoặc đặt tên parameter không khớp.** Tên trong SQL phải khớp với `@Param`.
- **Ghép input vào SQL.** Dùng bind parameter cho giá trị và whitelist identifier/sort.
- **Dùng `Page` mà count query sai.** Count query phải giữ cùng điều kiện lọc và tránh đếm trùng khi join.
- **Giả định native query luôn hỗ trợ Sort động.** Viết `ORDER BY` rõ hoặc tự quản lý sort an toàn.
- **Dùng native UPDATE nhưng quên `@Modifying`.** Spring Data cần biết đây là thao tác ghi.
- **Chạy bulk update rồi tiếp tục dùng entity cũ trong persistence context.** Refresh/clear hoặc thiết kế ranh giới transaction phù hợp.
- **Dùng `@NativeQuery` trên Spring Data JPA trước 3.4.** Dùng `@Query(nativeQuery = true)` hoặc nâng dependency theo bộ tương thích.
- **Test native SQL đặc thù chỉ bằng H2.** Kiểm thử trên đúng database để phát hiện khác biệt dialect.
- **Giả định tên hàm, kiểu dữ liệu và cú pháp SQL portable.** Native query gắn với hệ quản trị cụ thể; ghi rõ database/version nếu cần.

## 12. Quy trình chọn annotation và triển khai

1. Kiểm tra truy vấn có thật sự cần SQL thuần hay derived query/JPQL đã đáp ứng được.
2. Xác định phiên bản Spring Data JPA được resolve trong build.
3. Nếu phiên bản dưới 3.4, dùng `@Query(value = "...", nativeQuery = true)`; nếu từ 3.4 trở lên, có thể dùng `@NativeQuery`.
4. Chọn kiểu kết quả: entity, interface projection hay DTO với `@SqlResultSetMapping`.
5. Dùng bind parameter cho giá trị; không nối dữ liệu người dùng vào SQL.
6. Với `Page`, viết và kiểm tra `countQuery`; với `Slice`, cân nhắc khi không cần tổng số bản ghi.
7. Với UPDATE/DELETE, thêm `@Modifying` và bảo đảm transaction.
8. Kiểm tra tác động tới persistence context sau bulk operation.
9. Chạy integration test trên database tương thích và xem SQL/execution plan khi hiệu năng quan trọng.
10. Ghi nhận dialect/version nếu truy vấn phụ thuộc tính năng riêng của database.

## 13. Bảng lựa chọn nhanh

| Nhu cầu | Cách phù hợp |
| --- | --- |
| CRUD hoặc điều kiện đơn giản theo entity | Derived query |
| Truy vấn trên entity/property, cần join và predicate JPA | JPQL với `@Query` |
| SQL thuần, Spring Data JPA dưới 3.4 | `@Query(nativeQuery = true)` |
| SQL thuần, Spring Data JPA 3.4+ | `@NativeQuery` hoặc `@Query(nativeQuery = true)` |
| Chỉ cần vài cột | Interface projection |
| DTO constructor mapping theo result set | `@NativeQuery(sqlResultSetMapping = ...)` từ 3.4+ hoặc custom repository với `EntityManager` |
| Native query phân trang | `Page<T>` kèm `countQuery` rõ ràng |
| Native UPDATE/DELETE | `@Modifying` + transaction |
| SQL động phức tạp hoặc sort whitelist | Custom repository |

## Kết luận

`@Query(nativeQuery = true)` là cách khai báo native SQL đã có từ lâu trong Spring Data JPA. `@NativeQuery` được bổ sung từ Spring Data JPA 3.4.0, cung cấp cách viết chuyên biệt hơn và hỗ trợ `sqlResultSetMapping`. Hãy kiểm tra phiên bản dependency thực tế, dùng tên bảng/cột vật lý, bind tham số, chọn kiểu ánh xạ kết quả phù hợp, khai báo count query cho phân trang và quản lý persistence context sau bulk update/delete. Native SQL rất hữu ích khi cần kiểm soát câu lệnh hoặc dùng tính năng database riêng, nhưng cần kiểm thử trên đúng hệ quản trị và chấp nhận mức phụ thuộc schema/dialect cao hơn.