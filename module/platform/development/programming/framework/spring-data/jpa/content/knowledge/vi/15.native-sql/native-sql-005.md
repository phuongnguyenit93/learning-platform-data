# Ánh xạ phức tạp bằng @SqlResultSetMapping và @ConstructorResult

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vai trò của `@SqlResultSetMapping` khi ánh xạ kết quả native SQL trong JPA.
- Phân biệt ba loại kết quả: entity qua `@EntityResult`, DTO qua `@ConstructorResult` và giá trị đơn qua `@ColumnResult`.
- Ánh xạ tên cột/alias SQL vào constructor DTO theo đúng thứ tự và kiểu dữ liệu.
- Dùng `EntityManager.createNativeQuery()` để chạy SQL và nhận kết quả có cấu trúc.
- Xử lý kết quả gồm nhiều loại, giá trị null, kiểu số và alias cột.
- Chọn giữa native result mapping, JPQL constructor expression và projection của Spring Data.
- Kiểm thử mapping trên database thực tế và tránh các lỗi thường gặp.

## 1. Khi nào cần @SqlResultSetMapping?

JPQL làm việc với entity và thuộc tính Java. Với các truy vấn thông thường, Spring Data JPA có thể sinh SQL từ JPQL hoặc derived query. Tuy nhiên, đôi khi ứng dụng cần viết SQL trực tiếp, ví dụ:

- Dùng CTE, window function, hàm riêng của database hoặc cú pháp SQL đặc thù.
- Tối ưu báo cáo có nhiều phép join, group by và aggregate.
- Truy vấn dữ liệu từ view hoặc cấu trúc bảng legacy.
- Kết hợp dữ liệu từ nhiều bảng thành một DTO mà không cần tải toàn bộ entity.
- Dùng native query để khai thác tính năng mà JPQL không biểu diễn thuận tiện.

Khi chạy native SQL, kết quả thường là các dòng và cột JDBC. JPA cần biết cách chuyển các cột đó thành entity, DTO hoặc giá trị scalar. `@SqlResultSetMapping` khai báo quy tắc chuyển đổi này.

Ví dụ, SQL trả về:

| customer_id | customer_name | paid_order_count |
|---:|---|---:|
| 10 | An | 3 |
| 11 | Bình | 0 |

Ứng dụng có thể muốn nhận mỗi dòng thành một đối tượng `CustomerOrderSummary` thay vì nhận `Object[]` rồi tự đọc từng vị trí.

## 2. Ba thành phần chính của SQL result mapping

JPA cung cấp ba loại mapping thường dùng trong `@SqlResultSetMapping`:

| Thành phần | Dùng khi | Kết quả |
|---|---|---|
| `@EntityResult` | Một dòng SQL biểu diễn entity đã được mapping | Entity |
| `@ConstructorResult` | Một dòng SQL cần tạo DTO qua constructor | Đối tượng DTO mới |
| `@ColumnResult` | Một cột SQL là giá trị scalar | Giá trị như String, Long, BigDecimal, Date... |

Một `@SqlResultSetMapping` có thể khai báo một hoặc nhiều nhóm kết quả. Điều quan trọng là SQL phải trả về đúng các column label mà mapping yêu cầu.

### @EntityResult

Dùng khi muốn ánh xạ kết quả native SQL thành entity:

- `entityClass` chỉ định entity class.
- `@FieldResult(name = "...", column = "...")` nối thuộc tính persistent của entity với column label trong result set.
- `name` là tên thuộc tính Java của entity.
- `column` là tên cột/alias SQL.

Khi ánh xạ entity, SQL phải trả về đủ các cột cần thiết để provider dựng entity đúng theo mapping, bao gồm identifier và các cột cần cho trạng thái entity, quan hệ hoặc inheritance. Không nên chỉ select một vài cột rồi yêu cầu JPA coi kết quả đó là một entity đầy đủ.

### @ConstructorResult

Dùng khi muốn tạo DTO bằng constructor:

- `targetClass` là lớp DTO cần khởi tạo.
- `columns` là danh sách `@ColumnResult`.
- Thứ tự khai báo `columns` phải khớp thứ tự tham số trong constructor.
- Tên cột là alias/label SQL, không phải tên field Java.
- `type` có thể khai báo kiểu Java mong muốn cho cột.

Đây là lựa chọn phù hợp cho báo cáo hoặc projection native SQL.

### @ColumnResult

Dùng để ánh xạ một giá trị scalar. Ví dụ, SQL trả về một cột `total_amount` thì mapping có thể khai báo `@ColumnResult(name = "total_amount", type = BigDecimal.class)`.

Nếu mapping chỉ có một column result, mỗi dòng thường được trả về như một scalar. Nếu có nhiều scalar columns mà không gom vào constructor DTO, kết quả mỗi dòng thường là một mảng giá trị theo thứ tự mapping.

## 3. Ví dụ hoàn chỉnh: Native SQL ánh xạ vào DTO

Giả sử có hai bảng:

**customers**

| id | full_name | enabled |
|---:|---|---|
| 10 | An | true |
| 11 | Bình | true |
| 12 | Chi | false |

**orders**

| id | customer_id | status |
|---:|---:|---|
| 100 | 10 | PAID |
| 101 | 10 | PAID |
| 102 | 10 | PENDING |
| 103 | 11 | PENDING |

Bài toán: lấy danh sách khách hàng đang hoạt động cùng số đơn hàng đã thanh toán. Khách hàng không có đơn PAID vẫn phải xuất hiện với số lượng bằng 0.

### DTO đích

Tạo lớp DTO có constructor nhận ba tham số:

~~~java
package com.example.reporting;

public class CustomerOrderSummary {

    private final Long customerId;
    private final String customerName;
    private final Long paidOrderCount;

    public CustomerOrderSummary(
            Long customerId,
            String customerName,
            Long paidOrderCount) {
        this.customerId = customerId;
        this.customerName = customerName;
        this.paidOrderCount = paidOrderCount;
    }

    public Long getCustomerId() {
        return customerId;
    }

    public String getCustomerName() {
        return customerName;
    }

    public Long getPaidOrderCount() {
        return paidOrderCount;
    }
}
~~~

Constructor có thứ tự:

1. `Long customerId`
2. `String customerName`
3. `Long paidOrderCount`

Thứ tự này phải khớp với danh sách `@ColumnResult` được khai báo sau đó.

### Khai báo mapping trên entity

Có thể khai báo `@SqlResultSetMapping` trên một managed type, thường là entity class:

~~~java
package com.example.customer;

import com.example.reporting.CustomerOrderSummary;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.SqlResultSetMapping;
import jakarta.persistence.ConstructorResult;
import jakarta.persistence.ColumnResult;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
@SqlResultSetMapping(
    name = "CustomerOrderSummaryMapping",
    classes = @ConstructorResult(
        targetClass = CustomerOrderSummary.class,
        columns = {
            @ColumnResult(name = "customer_id", type = Long.class),
            @ColumnResult(name = "customer_name", type = String.class),
            @ColumnResult(name = "paid_order_count", type = Long.class)
        }
    )
)
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "full_name", nullable = false)
    private String fullName;

    @Column(nullable = false)
    private boolean enabled;

    protected Customer() {
    }

    public Long getId() {
        return id;
    }
}
~~~

Tên mapping `CustomerOrderSummaryMapping` phải duy nhất trong persistence unit. Khi chạy native query, ứng dụng truyền đúng tên mapping này cho EntityManager.

### Native SQL

SQL sử dụng alias khớp với tên trong `@ColumnResult`:

~~~sql
SELECT
    c.id AS customer_id,
    c.full_name AS customer_name,
    COUNT(o.id) AS paid_order_count
FROM customers c
LEFT JOIN orders o
    ON o.customer_id = c.id
   AND o.status = 'PAID'
WHERE c.enabled = true
GROUP BY c.id, c.full_name
ORDER BY c.id
~~~

Điều kiện `o.status = 'PAID'` nằm trong ON. Vì dùng LEFT JOIN, khách hàng đang hoạt động vẫn xuất hiện ngay cả khi không có đơn PAID; `COUNT(o.id)` khi đó trả về 0.

Nếu chuyển điều kiện `o.status = 'PAID'` xuống WHERE, các dòng có phía orders null sẽ bị loại, làm mất khách hàng không có đơn đã thanh toán.

### Thực thi bằng EntityManager

~~~java
package com.example.reporting;

import java.util.List;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;

import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class CustomerReportRepository {

    @PersistenceContext
    private EntityManager entityManager;

    private static final String SQL = """
        SELECT
            c.id AS customer_id,
            c.full_name AS customer_name,
            COUNT(o.id) AS paid_order_count
        FROM customers c
        LEFT JOIN orders o
            ON o.customer_id = c.id
           AND o.status = 'PAID'
        WHERE c.enabled = true
        GROUP BY c.id, c.full_name
        ORDER BY c.id
        """;

    @Transactional(readOnly = true)
    @SuppressWarnings("unchecked")
    public List<CustomerOrderSummary> findPaidOrderSummaries() {
        return entityManager
            .createNativeQuery(SQL, "CustomerOrderSummaryMapping")
            .getResultList();
    }
}
~~~

`createNativeQuery(sql, mappingName)` yêu cầu JPA áp dụng mapping đã khai báo. Kết quả là danh sách DTO được tạo qua constructor, không phải danh sách entity Customer.

Với dữ liệu minh họa, kết quả mong đợi:

~~~text
customerId=10, customerName=An, paidOrderCount=2
customerId=11, customerName=Bình, paidOrderCount=0
~~~

Khách hàng Chi bị loại vì `enabled = false`.

Đây là ví dụ tích hợp gồm DTO, entity mapping và repository; để chạy cần có dependency JPA, Spring context, hai bảng và dữ liệu test tương ứng.

## 4. Vì sao thứ tự ConstructorResult quan trọng?

`@ConstructorResult` không tự tìm constructor dựa trên tên field DTO. Provider sử dụng danh sách column result theo thứ tự để gọi constructor.

Ví dụ đúng:

~~~java
public CustomerOrderSummary(
        Long customerId,
        String customerName,
        Long paidOrderCount) {
    // ...
}
~~~

Mapping tương ứng:

~~~java
@ConstructorResult(
    targetClass = CustomerOrderSummary.class,
    columns = {
        @ColumnResult(name = "customer_id", type = Long.class),
        @ColumnResult(name = "customer_name", type = String.class),
        @ColumnResult(name = "paid_order_count", type = Long.class)
    }
)
~~~

Nếu đổi thứ tự cột:

~~~java
columns = {
    @ColumnResult(name = "customer_name", type = String.class),
    @ColumnResult(name = "customer_id", type = Long.class),
    @ColumnResult(name = "paid_order_count", type = Long.class)
}
~~~

thì constructor cũng phải đổi thành `(String, Long, Long)`. Nếu không, provider có thể báo không tìm thấy constructor phù hợp khi khởi tạo mapping hoặc thực thi query.

Hãy kiểm tra đồng thời ba nơi:

1. Alias trong SELECT.
2. Tên trong `@ColumnResult`.
3. Thứ tự và kiểu tham số constructor.

## 5. Kiểu dữ liệu và giá trị NULL

Native SQL trả kiểu dữ liệu theo database và JDBC driver. Kiểu của `COUNT`, `SUM`, `AVG`, timestamp hoặc numeric có thể khác nhau giữa các database.

Dùng `type` trong `@ColumnResult` để khai báo kiểu Java mong muốn:

~~~java
@ColumnResult(name = "total_amount", type = BigDecimal.class)
~~~

Một số lưu ý:

- `COUNT` thường được biểu diễn thành kiểu số nguyên lớn; DTO dùng `Long` là lựa chọn phổ biến.
- `SUM` trên kiểu decimal thường nên ánh xạ sang `BigDecimal`.
- Cột nullable cần dùng kiểu wrapper như `Long`, `Integer`, `Boolean`, không dùng primitive nếu có thể nhận null.
- Không giả định mọi driver tự chuyển kiểu số theo cùng một cách.
- Kiểm thử mapping trên database/driver thật sự được triển khai.

Ví dụ, nếu truy vấn có thể trả `discount_rate` null, DTO nên dùng `BigDecimal` có thể null. Nếu dùng `double`, việc nhận null có thể gây lỗi hoặc không biểu diễn được ý nghĩa “không có giá trị”.

### Alias cột

`@ColumnResult(name = "customer_id")` tham chiếu column label mà JDBC result set cung cấp. Hãy đặt alias rõ ràng và ổn định trong SQL:

~~~sql
SELECT c.id AS customer_id
~~~

Tên alias có thể chịu ảnh hưởng quy tắc chữ hoa/chữ thường của database nếu dùng identifier có dấu nháy. Cách an toàn là dùng alias chữ thường, snake_case, không trùng tên và kiểm thử trên database đích.

Không nhầm:

- `@ColumnResult(name = "...")`: tên cột/alias trong kết quả SQL.
- `@FieldResult(name = "...", column = "...")`: `name` là thuộc tính entity, `column` là cột SQL.
- `@ConstructorResult(targetClass = ...)`: lớp DTO nhận kết quả qua constructor.

## 6. Mapping kết quả thành Entity bằng @EntityResult

Nếu native SQL trả về một entity đầy đủ, có thể dùng `@EntityResult`.

Ví dụ khái niệm:

~~~java
@SqlResultSetMapping(
    name = "CustomerEntityMapping",
    entities = @EntityResult(
        entityClass = Customer.class,
        fields = {
            @FieldResult(name = "id", column = "customer_id"),
            @FieldResult(name = "fullName", column = "customer_name"),
            @FieldResult(name = "enabled", column = "is_enabled")
        }
    )
)
~~~

Trong đó:

- `entityClass` là entity cần tạo.
- `name` trong FieldResult là tên persistent attribute Java.
- `column` là alias trong result set.
- SQL phải cung cấp các cột cần thiết để provider khởi tạo entity theo mapping.

Entity được ánh xạ theo identity và persistence context. Nếu entity cùng identity đã được quản lý trong context, JPA sẽ tuân theo identity semantics của persistence context thay vì tạo một bản ghi Java độc lập có identity trùng lặp.

Không dùng EntityResult chỉ để lấy vài cột báo cáo. Nếu không cần entity lifecycle, dirty checking hoặc association, DTO qua ConstructorResult thường nhẹ và rõ mục đích hơn.

## 7. Mapping giá trị scalar bằng @ColumnResult

Nếu query chỉ trả một giá trị tổng hợp, có thể dùng mapping scalar:

~~~java
@SqlResultSetMapping(
    name = "CustomerRevenueMapping",
    columns = {
        @ColumnResult(name = "total_revenue", type = BigDecimal.class)
    }
)
~~~

Native SQL:

~~~sql
SELECT SUM(o.total_amount) AS total_revenue
FROM orders o
WHERE o.status = 'PAID'
~~~

Thực thi:

~~~java
BigDecimal revenue = (BigDecimal) entityManager
    .createNativeQuery(SQL, "CustomerRevenueMapping")
    .getSingleResult();
~~~

Nếu không có dòng phù hợp, aggregate SUM thường trả về một dòng với giá trị null; cần xử lý null theo nghiệp vụ. Ngược lại, `COUNT(*)` thường trả 0 khi không có dòng phù hợp.

Nếu mapping có nhiều scalar columns, hãy xác định cấu trúc kết quả và thứ tự rõ ràng; dùng DTO constructor mapping khi cần một kiểu kết quả có tên field thay vì phải đọc `Object[]` theo index.

## 8. Kết hợp EntityResult, ConstructorResult và ColumnResult

Một result set mapping có thể mô tả nhiều phần của một dòng kết quả, ví dụ:

- Một entity Order.
- Một DTO chứa thông tin tổng hợp.
- Một scalar như tổng tiền hoặc cờ tính toán.

Điều này hữu ích với báo cáo cần entity cùng dữ liệu tổng hợp. Tuy nhiên, kết quả nhiều phần thường khó đọc và phụ thuộc cấu trúc mapping; hãy cân nhắc DTO tổng hợp đơn giản nếu ứng dụng chỉ cần một view model.

Khi khai báo nhiều loại result trong cùng mapping, đọc kỹ semantics của Jakarta Persistence và xác nhận kiểu object thực tế mà provider trả về. Không suy luận rằng một mapping hỗn hợp sẽ trả về một DTO duy nhất nếu nó được khai báo thành nhiều result component.

## 9. Dùng mapping với NamedNativeQuery

Có thể gắn tên cho native query bằng `@NamedNativeQuery` và liên kết tới mapping:

~~~java
@NamedNativeQuery(
    name = "Customer.paidOrderSummary",
    query = """
        SELECT
            c.id AS customer_id,
            c.full_name AS customer_name,
            COUNT(o.id) AS paid_order_count
        FROM customers c
        LEFT JOIN orders o
            ON o.customer_id = c.id
           AND o.status = 'PAID'
        WHERE c.enabled = true
        GROUP BY c.id, c.full_name
        ORDER BY c.id
        """,
    resultSetMapping = "CustomerOrderSummaryMapping"
)
~~~

Gọi bằng EntityManager:

~~~java
List<CustomerOrderSummary> rows = entityManager
    .createNamedQuery(
        "Customer.paidOrderSummary",
        CustomerOrderSummary.class
    )
    .getResultList();
~~~

Typed named query với DTO constructor mapping được hỗ trợ bởi các phiên bản Jakarta Persistence phù hợp. Nếu API/provider của dự án cũ không cung cấp typed overload cần thiết, dùng `createNativeQuery(sql, mappingName)` và kiểm tra/cast kết quả theo mapping.

Named query phù hợp khi SQL ổn định, được đặt tên và tái sử dụng. Nếu SQL phụ thuộc nhiều điều kiện runtime, custom repository với EntityManager thường linh hoạt hơn.

## 10. So sánh với JPQL constructor expression

Nếu truy vấn có thể viết bằng JPQL, không cần native SQL chỉ để tạo DTO.

JPQL constructor expression:

~~~java
@Query("""
    select new com.example.reporting.CustomerOrderSummary(
        c.id,
        c.fullName,
        count(o)
    )
    from Customer c
    left join c.orders o on o.status = :status
    where c.enabled = true
    group by c.id, c.fullName
    order by c.id
    """)
List<CustomerOrderSummary> findSummaryByStatus(
    @Param("status") OrderStatus status
);
~~~

Khác biệt:

| Tiêu chí | JPQL constructor expression | Native SQL + SqlResultSetMapping |
|---|---|---|
| Ngôn ngữ | Entity name và property Java | Tên bảng/cột và SQL của database |
| Tính di động | Thường cao hơn giữa các database | Có thể phụ thuộc database/dialect |
| DTO | Dùng `select new package.Dto(...)` | Dùng `@ConstructorResult` |
| Tính năng SQL đặc thù | Bị giới hạn bởi JPQL | Dùng được tính năng SQL riêng |
| Mapping | Constructor expression nằm trong query | Mapping khai báo riêng, tái sử dụng được |
| Bảo trì | Đổi entity property có thể cần sửa JPQL | Đổi schema/alias cần sửa SQL và mapping |

Ưu tiên JPQL nếu query có thể diễn đạt rõ ràng bằng entity model. Chọn native SQL khi cần khả năng của database hoặc cần kiểm soát SQL cụ thể.

## 11. Dùng cùng Spring Data JPA

Spring Data JPA hỗ trợ nhiều cách khai báo native query, nhưng không phải mọi phiên bản đều có cùng API cho result set mapping.

Cách ổn định, trực tiếp là dùng custom repository implementation với EntityManager như ví dụ ở phần 3. Điều này giúp truyền tên mapping rõ ràng và kiểm soát transaction, pagination, parameter binding.

Một số phiên bản Spring Data JPA mới có annotation `@NativeQuery` hỗ trợ thuộc tính `sqlResultSetMapping`. API này phụ thuộc phiên bản Spring Data JPA; hãy kiểm tra tài liệu đúng phiên bản BOM của dự án trước khi dùng. Không giả định thuộc tính đó tồn tại trong mọi phiên bản chỉ vì một ví dụ trên mạng sử dụng nó.

Nếu dùng `@Query(nativeQuery = true)` thông thường, hãy xác nhận cách Spring Data chuyển kết quả. Native query trả interface projection hoặc DTO có quy tắc riêng; đừng cho rằng nó tự áp dụng tên `@SqlResultSetMapping` nếu không cấu hình rõ.

## 12. Phân trang native query

Với native SQL có phân trang, cần xác định cả query dữ liệu và count query. Count query phải đếm đúng tập kết quả logic, đặc biệt khi query có join hoặc group by.

Ví dụ trong custom repository:

~~~java
Query dataQuery = entityManager.createNativeQuery(
    DATA_SQL,
    "CustomerOrderSummaryMapping"
);

dataQuery.setFirstResult(page * size);
dataQuery.setMaxResults(size);

@SuppressWarnings("unchecked")
List<CustomerOrderSummary> content = dataQuery.getResultList();

Query countQuery = entityManager.createNativeQuery(COUNT_SQL);
long total = ((Number) countQuery.getSingleResult()).longValue();
~~~

Nếu query có GROUP BY, count query có thể cần đếm số nhóm bằng subquery thay vì đếm trực tiếp bảng gốc. Không dùng `COUNT(*)` trên join result nếu mục tiêu là đếm customer duy nhất.

Cần validate `page` và `size` để tránh giá trị âm hoặc kích thước quá lớn. Thứ tự sắp xếp phải ổn định; thêm khóa duy nhất làm tie-breaker nếu nhiều dòng có cùng giá trị sắp xếp.

## 13. Bảo mật và tham số hóa SQL

Không nối trực tiếp dữ liệu người dùng vào chuỗi SQL:

~~~java
String sql = "SELECT * FROM customers WHERE email = '" + email + "'";
~~~

Cách này có nguy cơ SQL injection.

Dùng parameter binding:

~~~java
Query query = entityManager.createNativeQuery(
    "SELECT * FROM customers WHERE email = :email",
    "CustomerEntityMapping"
);

query.setParameter("email", email);
~~~

Parameter binding áp dụng cho giá trị dữ liệu, không áp dụng để thay tên bảng, tên cột hoặc từ khóa SQL. Nếu cần sort động hoặc chọn cột, hãy dùng whitelist các lựa chọn hợp lệ và ghép identifier đã được kiểm soát.

Không đưa tên mapping, tên bảng hoặc fragment SQL từ request bên ngoài vào query mà không xác thực.

## 14. Kiểm thử mapping

Integration test nên xác nhận:

- SQL trả đúng column label.
- Mapping name đúng và tồn tại trong persistence unit.
- Constructor DTO đúng thứ tự và kiểu.
- Cột nullable được ánh xạ sang wrapper phù hợp.
- Kết quả LEFT JOIN có null ở phía không có association.
- Aggregate như COUNT/SUM có kiểu dữ liệu mong đợi.
- Truy vấn chạy được trên database/driver đích.
- Pagination và count query đếm đúng.

Ví dụ kiểm thử repository:

~~~java
@DataJpaTest
@Import(CustomerReportRepository.class)
class CustomerReportRepositoryTest {

    @Autowired
    CustomerReportRepository reportRepository;

    @Test
    void mapsNativeRowsIntoCustomerSummaryDto() {
        List<CustomerOrderSummary> rows =
                reportRepository.findPaidOrderSummaries();

        assertEquals(2, rows.size());

        assertEquals(10L, rows.get(0).getCustomerId());
        assertEquals("An", rows.get(0).getCustomerName());
        assertEquals(2L, rows.get(0).getPaidOrderCount());

        assertEquals(11L, rows.get(1).getCustomerId());
        assertEquals("Bình", rows.get(1).getCustomerName());
        assertEquals(0L, rows.get(1).getPaidOrderCount());
    }
}
~~~

Test giả định test database đã có đúng dữ liệu customers/orders như phần 3. Có thể seed dữ liệu bằng `@Sql`, data.sql hoặc repository setup trong test. Nếu dùng Testcontainers, chạy cùng loại database như production để kiểm tra alias, kiểu dữ liệu và SQL dialect thực tế.

## 15. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Mapping không được tìm thấy | Tên mapping sai hoặc chưa được đăng ký trong persistence unit | Kiểm tra chính tả và managed type chứa annotation |
| Không tìm thấy constructor DTO | Thứ tự hoặc kiểu ColumnResult không khớp constructor | So sánh alias, thứ tự cột và constructor signature |
| Giá trị DTO bị đảo | Khai báo columns khác thứ tự constructor | Sắp xếp lại ColumnResult theo thứ tự tham số |
| Cột trả về null ngoài dự kiến | Alias sai, LEFT JOIN không có match hoặc dữ liệu thật null | Kiểm tra SQL result set và column label |
| ClassCastException với COUNT/SUM | Kiểu JDBC khác kiểu DTO giả định | Dùng ColumnResult type rõ ràng và kiểm tra driver |
| SQL chạy nhưng mapping lỗi | Alias trong SELECT không khớp ColumnResult/FieldResult | Dùng alias ổn định và thống nhất tên |
| EntityResult thiếu dữ liệu | SQL không trả đủ cột cần cho entity | Select đủ cột hoặc dùng DTO nếu chỉ cần một phần |
| Native query không portable | Dùng hàm/cú pháp riêng database | Kiểm thử theo database đích và cô lập SQL đặc thù |
| Page total sai | Count query đếm dòng join thay vì nhóm/entity | Viết count query đúng semantics |
| SQL injection | Ghép chuỗi input trực tiếp vào SQL | Dùng named/positional parameter binding |

## Checklist trước khi merge

- [ ] Đã xác định kết quả cần là entity, DTO hay scalar.
- [ ] Mapping name duy nhất và được đăng ký trong persistence unit.
- [ ] Alias SELECT khớp chính xác ColumnResult/FieldResult.
- [ ] ConstructorResult columns đúng thứ tự và kiểu constructor.
- [ ] DTO dùng wrapper cho các cột có thể null.
- [ ] Aggregate được kiểm tra kiểu trên database/driver đích.
- [ ] EntityResult trả đủ cột cần thiết cho entity.
- [ ] Native SQL dùng parameter binding, không nối input người dùng.
- [ ] Count query và pagination có semantics chính xác.
- [ ] Integration test xác nhận dữ liệu, null, kiểu số và mapping trên database phù hợp.

## Kết luận

`@SqlResultSetMapping` mô tả cách JPA chuyển kết quả native SQL thành entity, DTO hoặc scalar. `@EntityResult` ánh xạ entity, `@ConstructorResult` tạo DTO qua constructor và `@ColumnResult` ánh xạ từng cột. Với constructor mapping, alias SQL phải khớp tên column result, còn thứ tự và kiểu cột phải khớp constructor. Dùng EntityManager với tên mapping khi cần kiểm soát rõ native query; ưu tiên JPQL constructor expression nếu truy vấn có thể diễn đạt bằng entity model. Luôn kiểm thử mapping trên database/driver thực tế, đặc biệt với alias, aggregate, null và phân trang.
