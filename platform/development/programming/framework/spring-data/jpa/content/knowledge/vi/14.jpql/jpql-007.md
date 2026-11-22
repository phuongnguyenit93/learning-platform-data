# GROUP BY, HAVING và các hàm tổng hợp

JPQL không chỉ dùng để tìm từng entity. Bạn còn có thể nhóm dữ liệu, tính tổng doanh thu, đếm số đơn hàng, tính giá trị trung bình và lọc các nhóm theo điều kiện tổng hợp. Ba thành phần thường đi cùng nhau là **GROUP BY**, **HAVING** và các hàm tổng hợp như **COUNT**, **SUM**, **AVG**, **MIN**, **MAX**.

- **GROUP BY** gom các hàng kết quả thành nhóm theo một hoặc nhiều thuộc tính entity.
- **HAVING** lọc các nhóm sau khi đã tổng hợp.
- **WHERE** lọc từng hàng trước khi nhóm.
- Các hàm tổng hợp tính một giá trị cho mỗi nhóm hoặc cho toàn bộ tập kết quả.

JPQL truy vấn trên entity và thuộc tính Java, không truy vấn trực tiếp tên bảng/cột như SQL. Nắm được khác biệt này giúp bạn viết báo cáo dữ liệu đúng với mô hình JPA và trả kết quả qua DTO rõ ràng.

**Điều kiện của ví dụ:** các đoạn mã dùng Spring Boot 3.x, Java 17 trở lên, Jakarta Persistence và Spring Data JPA. Ứng dụng cần **spring-boot-starter-data-jpa**, JDBC driver, DataSource và schema phù hợp. Đây là các tệp trong ứng dụng Spring Boot, không phải chương trình độc lập có thể chạy chỉ bằng **javac**.

## 1. Mô hình dữ liệu dùng trong ví dụ

Ta dùng entity **PurchaseOrder** để biểu diễn đơn hàng. Mỗi đơn hàng có trạng thái, tổng tiền, thời điểm tạo và khách hàng sở hữu đơn hàng.

~~~java
package com.example.sales.domain;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.LocalDateTime;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status;

    @Column(nullable = false, precision = 14, scale = 2)
    private BigDecimal totalAmount;

    @Column(nullable = false)
    private LocalDateTime createdAt;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    protected PurchaseOrder() {
    }

    public Long getId() {
        return id;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public Customer getCustomer() {
        return customer;
    }
}
~~~

Enum:

~~~java
public enum OrderStatus {
    NEW,
    PAID,
    SHIPPED,
    CANCELLED
}
~~~

Entity Customer có các thuộc tính **id** và **name**:

~~~java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    protected Customer() {
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

Giả sử dữ liệu có các đơn hàng như sau:

| Đơn hàng | Khách hàng | Trạng thái | Tổng tiền |
|---|---|---|---:|
| 1 | An | PAID | 500 |
| 2 | An | PAID | 300 |
| 3 | Bình | NEW | 200 |
| 4 | An | SHIPPED | 700 |
| 5 | Bình | PAID | 400 |

Một báo cáo theo trạng thái cần trả về số đơn và tổng tiền của từng trạng thái. Đây là trường hợp điển hình để dùng GROUP BY.

## 2. GROUP BY: gom các bản ghi thành nhóm

Cú pháp cơ bản:

~~~sql
SELECT expression, aggregate_function(...)
FROM Entity e
WHERE condition
GROUP BY e.attribute
~~~

Trong JPQL, tên entity và thuộc tính Java được sử dụng:

~~~java
@Query("""
    select o.status, count(o), sum(o.totalAmount)
    from PurchaseOrder o
    group by o.status
    """)
List<Object[]> summarizeByStatus();
~~~

Kết quả gồm một dòng cho mỗi trạng thái:

| status | count(o) | sum(totalAmount) |
|---|---:|---:|
| NEW | 1 | 200 |
| PAID | 3 | 1200 |
| SHIPPED | 1 | 700 |

Mỗi phần tử trong **Object[]** lần lượt là trạng thái, số đơn và tổng tiền. Cách trả về này dùng được nhưng phải ép kiểu theo đúng thứ tự cột, dễ gây nhầm lẫn khi truy vấn thay đổi. Ở phần sau, ta sẽ chuyển sang DTO projection.

### Nhóm theo nhiều thuộc tính

Có thể nhóm theo nhiều thuộc tính cùng lúc:

~~~java
@Query("""
    select o.customer.id, o.status, count(o)
    from PurchaseOrder o
    group by o.customer.id, o.status
    """)
List<Object[]> countByCustomerAndStatus();
~~~

Mỗi nhóm là một tổ hợp **customer.id + status**. Ví dụ, một khách hàng có đơn PAID và SHIPPED sẽ xuất hiện thành hai nhóm riêng.

Quy tắc cần nhớ: một biểu thức được chọn trực tiếp trong SELECT mà không nằm trong hàm tổng hợp thường phải xuất hiện trong GROUP BY. Ví dụ, nếu SELECT có **o.customer.name** và **o.status**, cần nhóm theo cả hai thuộc tính đó.

~~~java
@Query("""
    select o.customer.name, o.status, sum(o.totalAmount)
    from PurchaseOrder o
    group by o.customer.name, o.status
    """)
List<Object[]> revenueByCustomerAndStatus();
~~~

Không nên chọn một thuộc tính chi tiết không được nhóm hoặc tổng hợp. SQL có thể từ chối truy vấn đó; JPQL cũng yêu cầu biểu thức SELECT phù hợp với grouping semantics.

## 3. Các hàm tổng hợp trong JPQL

JPQL chuẩn hỗ trợ năm hàm tổng hợp phổ biến:

| Hàm | Công dụng | Ví dụ |
|---|---|---|
| **COUNT** | Đếm entity hoặc giá trị khác null | **count(o)** |
| **SUM** | Tính tổng giá trị số | **sum(o.totalAmount)** |
| **AVG** | Tính trung bình | **avg(o.totalAmount)** |
| **MIN** | Tìm giá trị nhỏ nhất | **min(o.totalAmount)** |
| **MAX** | Tìm giá trị lớn nhất | **max(o.totalAmount)** |

Ví dụ tính các chỉ số chung:

~~~java
@Query("""
    select count(o), sum(o.totalAmount),
           avg(o.totalAmount), min(o.totalAmount),
           max(o.totalAmount)
    from PurchaseOrder o
    where o.status = :status
    """)
Object[] calculateStatistics(@Param("status") OrderStatus status);
~~~

Truy vấn không có GROUP BY nên trả về một dòng tổng hợp cho toàn bộ tập đơn hàng thỏa WHERE. Giá trị trả về là một mảng object theo thứ tự SELECT.

### Kiểu dữ liệu trả về

Không phải hàm tổng hợp nào cũng trả về cùng kiểu:

| Hàm | Kiểu kết quả theo JPQL |
|---|---|
| **COUNT** | **Long** |
| **AVG** | **Double** |
| **MIN**, **MAX** | Cùng kiểu với biểu thức được tổng hợp |
| **SUM** trên kiểu số nguyên thông thường | **Long** |
| **SUM** trên **Float/Double** | **Double** |
| **SUM** trên **BigInteger** | **BigInteger** |
| **SUM** trên **BigDecimal** | **BigDecimal** |

Ví dụ **sum(o.totalAmount)** có kết quả kiểu **BigDecimal** vì totalAmount là BigDecimal. Trong khi đó, **avg(o.totalAmount)** có kết quả kiểu **Double** theo quy tắc kiểu trả về của JPQL, kể cả khi trường đầu vào là BigDecimal.

Hãy khai báo kiểu DTO và ép kiểu đúng. Đừng mặc định AVG của BigDecimal sẽ trả về BigDecimal.

### COUNT và DISTINCT

**COUNT(o)** đếm số entity trong nhóm. Có thể dùng DISTINCT để đếm các giá trị duy nhất:

~~~java
@Query("""
    select count(distinct o.customer.id)
    from PurchaseOrder o
    where o.status = :status
    """)
Long countDistinctCustomers(@Param("status") OrderStatus status);
~~~

Truy vấn trên đếm số khách hàng khác nhau có đơn ở trạng thái đã chọn. Nếu một khách hàng có nhiều đơn PAID, khách hàng đó chỉ được đếm một lần.

**COUNT(path)** bỏ qua giá trị null của biểu thức. **COUNT(o)** đếm entity được chọn; **COUNT(DISTINCT o.customer.id)** đếm ID khách hàng khác nhau.

JPQL dùng **COUNT(expression)**; không viết **COUNT(*)** như SQL trong JPQL chuẩn.

## 4. WHERE và HAVING khác nhau thế nào?

Đây là điểm quan trọng nhất khi viết báo cáo.

- **WHERE** lọc từng bản ghi trước khi nhóm.
- **HAVING** lọc các nhóm sau khi GROUP BY và tổng hợp.

Ví dụ: chỉ lấy đơn đã thanh toán, sau đó giữ các trạng thái có ít nhất 10 đơn:

~~~java
@Query("""
    select o.status, count(o), sum(o.totalAmount)
    from PurchaseOrder o
    where o.createdAt >= :from
      and o.createdAt < :to
      and o.status <> :cancelled
    group by o.status
    having count(o) >= :minimumOrders
    order by count(o) desc
    """)
List<Object[]> summarizeStatus(
    @Param("from") LocalDateTime from,
    @Param("to") LocalDateTime to,
    @Param("cancelled") OrderStatus cancelled,
    @Param("minimumOrders") long minimumOrders
);
~~~

Trình tự logic:

1. FROM xác định nguồn entity.
2. WHERE loại các đơn không thỏa điều kiện.
3. GROUP BY gom các đơn còn lại theo trạng thái.
4. HAVING loại các nhóm không đạt số lượng tối thiểu.
5. SELECT tạo các giá trị tổng hợp cho từng nhóm.
6. ORDER BY sắp xếp kết quả nhóm.

Ví dụ, nếu một trạng thái có 8 đơn sau khi lọc WHERE và **minimumOrders = 10**, toàn bộ nhóm đó bị loại bởi HAVING.

Không đặt điều kiện tổng hợp như **count(o) >= 10** trong WHERE. WHERE hoạt động trên từng hàng trước grouping; điều kiện tổng hợp thuộc về HAVING.

### HAVING không bắt buộc phải có GROUP BY tường minh

Có thể dùng hàm tổng hợp trên toàn bộ tập kết quả và lọc bằng HAVING mà không nhóm theo thuộc tính:

~~~java
@Query("""
    select count(o)
    from PurchaseOrder o
    having count(o) >= :minimumOrders
    """)
List<Long> countIfThresholdReached(
    @Param("minimumOrders") long minimumOrders
);
~~~

Truy vấn này tạo một nhóm tổng hợp duy nhất cho tập dữ liệu. Nếu tổng số đơn không đạt ngưỡng, kết quả không có dòng. Nếu cần luôn nhận một giá trị đếm, dùng truy vấn chỉ có COUNT và xử lý giá trị trả về.

## 5. Dùng DTO projection thay cho Object[]

Với truy vấn báo cáo, DTO giúp đặt tên rõ ràng cho từng trường kết quả và tránh ép kiểu thủ công.

Record DTO:

~~~java
package com.example.sales.dto;

import com.example.sales.domain.OrderStatus;
import java.math.BigDecimal;

public record StatusSummary(
    OrderStatus status,
    Long orderCount,
    BigDecimal revenue
) {
}
~~~

Repository dùng JPQL constructor expression:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query("""
        select new com.example.sales.dto.StatusSummary(
            o.status,
            count(o),
            sum(o.totalAmount)
        )
        from PurchaseOrder o
        where o.createdAt >= :from
          and o.createdAt < :to
        group by o.status
        having count(o) >= :minimumOrders
        order by count(o) desc
        """)
    List<StatusSummary> summarizeByStatus(
        @Param("from") LocalDateTime from,
        @Param("to") LocalDateTime to,
        @Param("minimumOrders") long minimumOrders
    );
}
~~~

JPQL **new com.example...StatusSummary(...)** yêu cầu constructor có tham số tương ứng với biểu thức SELECT và đúng thứ tự kiểu dữ liệu. Record Java có canonical constructor nên dùng thuận tiện cho DTO bất biến.

Kết quả:

~~~java
List<StatusSummary> summaries =
    repository.summarizeByStatus(
        startOfMonth,
        startOfNextMonth,
        5L
    );

for (StatusSummary summary : summaries) {
    System.out.println(summary.status());
    System.out.println(summary.orderCount());
    System.out.println(summary.revenue());
}
~~~

DTO tổng hợp không phải entity managed. Nó chỉ chứa dữ liệu báo cáo được truy vấn trả về.

## 6. Tổng hợp theo khách hàng

Một báo cáo phổ biến là tổng doanh thu theo khách hàng. Ta nhóm theo ID và tên khách hàng:

~~~java
public record CustomerRevenue(
    Long customerId,
    String customerName,
    Long orderCount,
    BigDecimal revenue
) {
}
~~~

Repository:

~~~java
@Query("""
    select new com.example.sales.dto.CustomerRevenue(
        o.customer.id,
        o.customer.name,
        count(o),
        sum(o.totalAmount)
    )
    from PurchaseOrder o
    where o.createdAt >= :from
      and o.createdAt < :to
    group by o.customer.id, o.customer.name
    having sum(o.totalAmount) >= :minimumRevenue
    order by sum(o.totalAmount) desc
    """)
List<CustomerRevenue> findCustomerRevenue(
    @Param("from") LocalDateTime from,
    @Param("to") LocalDateTime to,
    @Param("minimumRevenue") BigDecimal minimumRevenue
);
~~~

Ở đây:

- **customer.id** và **customer.name** là các thuộc tính được nhóm.
- **count(o)** đếm số đơn của từng khách hàng.
- **sum(o.totalAmount)** tính doanh thu của từng khách hàng.
- **having sum(...) >= ...** giữ khách hàng đạt ngưỡng doanh thu.
- **order by sum(...) desc** đưa khách hàng có doanh thu cao lên đầu.

JPQL dùng đường dẫn thuộc tính **o.customer.name**, không cần tự viết JOIN nếu chỉ điều hướng qua association đơn hợp lệ. Nếu truy vấn cần kiểm soát kiểu join, điều kiện join hoặc association tùy chọn, hãy khai báo JOIN rõ ràng.

## 7. Tổng hợp với JOIN và DISTINCT

Khi nhóm dữ liệu qua association, JOIN có thể làm tăng số dòng đầu vào. Ví dụ một đơn hàng có nhiều dòng chi tiết. Nếu join PurchaseOrder với OrderLine, mỗi đơn có thể xuất hiện nhiều lần.

~~~java
select o.status, count(o)
from PurchaseOrder o
join o.lines line
group by o.status
~~~

Nếu một đơn có ba dòng hàng, đơn đó có thể được tính ba lần. Khi mục tiêu là đếm số đơn duy nhất, dùng:

~~~java
select o.status, count(distinct o.id)
from PurchaseOrder o
join o.lines line
group by o.status
~~~

Nếu mục tiêu là tổng tiền đơn hàng, việc join collection cũng có thể khiến **sum(o.totalAmount)** bị nhân lặp theo số dòng. Cần hiểu cardinality của join trước khi tổng hợp.

Có thể cần truy vấn con, tách thành hai truy vấn hoặc tổng hợp trên entity phù hợp để tránh cộng trùng. Không sửa lỗi bằng cách thêm DISTINCT một cách máy móc vào mọi hàm tổng hợp; **SUM(DISTINCT value)** có ý nghĩa khác với việc loại trùng entity theo ID.

## 8. NULL và tập kết quả rỗng trong hàm tổng hợp

Các hàm tổng hợp có quy tắc xử lý null:

- **COUNT(expression)** bỏ qua các giá trị null của expression.
- **COUNT(entity)** đếm entity được chọn.
- **SUM**, **AVG**, **MIN**, **MAX** bỏ qua giá trị null.
- Khi GROUP BY, các hàng có cùng giá trị null của khóa nhóm có thể nằm trong cùng một nhóm.
- Với truy vấn tổng hợp không có GROUP BY và tập đầu vào rỗng, COUNT trả về 0; SUM, AVG, MIN và MAX trả về null.

Ví dụ:

~~~java
@Query("""
    select count(o), sum(o.totalAmount), avg(o.totalAmount)
    from PurchaseOrder o
    where o.status = :status
    """)
Object[] summarize(@Param("status") OrderStatus status);
~~~

Nếu không có đơn nào phù hợp, kết quả COUNT là 0 nhưng SUM và AVG có thể là null. Khi map sang DTO hoặc tính toán tiếp, cần xử lý null phù hợp.

Có thể dùng **COALESCE** trong JPQL để thay null bằng giá trị mặc định:

~~~java
@Query("""
    select coalesce(sum(o.totalAmount), 0)
    from PurchaseOrder o
    where o.status = :status
    """)
BigDecimal totalForStatus(@Param("status") OrderStatus status);
~~~

Kiểu literal số trong JPQL cần tương thích với kiểu tổng hợp. Với BigDecimal, nếu provider/database gặp vấn đề suy luận kiểu literal, hãy kiểm thử và cân nhắc truyền tham số BigDecimal hoặc xử lý null ở Java.

## 9. ORDER BY với kết quả tổng hợp

Có thể sắp xếp nhóm theo biểu thức tổng hợp:

~~~java
@Query("""
    select o.status, count(o)
    from PurchaseOrder o
    group by o.status
    order by count(o) desc
    """)
List<Object[]> findStatusesByOrderCount();
~~~

Trong một số truy vấn, có thể đặt alias cho biểu thức SELECT và dùng alias trong ORDER BY:

~~~java
@Query("""
    select o.status as status, count(o) as orderCount
    from PurchaseOrder o
    group by o.status
    order by orderCount desc
    """)
List<Object[]> findStatusCounts();
~~~

Nếu dùng constructor DTO, cách đơn giản là sắp xếp trực tiếp bằng biểu thức tổng hợp trong ORDER BY. Khả năng dùng alias và cú pháp chi tiết có thể phụ thuộc provider/version, nên kiểm tra truy vấn trong ứng dụng thực tế.

## 10. Phân trang kết quả GROUP BY

Spring Data JPA có thể phân trang query thông qua **Pageable**, nhưng query có GROUP BY cần chú ý câu count dùng để tính tổng số trang.

Ví dụ:

~~~java
@Query(
    value = """
        select new com.example.sales.dto.StatusSummary(
            o.status, count(o), sum(o.totalAmount)
        )
        from PurchaseOrder o
        group by o.status
        """,
    countQuery = """
        select count(distinct o.status)
        from PurchaseOrder o
        """
)
Page<StatusSummary> pageStatusSummary(Pageable pageable);
~~~

Count query ở đây phù hợp vì grouping chỉ theo một thuộc tính trạng thái. Nếu grouping theo nhiều thuộc tính, **count(distinct ...)** trên một field không còn đếm đúng số tổ hợp nhóm. Khi đó cần thiết kế count query tương ứng, dùng projection khác, hoặc trả **Slice**/**List** nếu không cần tổng số trang.

Đừng mặc định Spring Data luôn suy ra được count query chính xác cho mọi JPQL có GROUP BY/HAVING. Với truy vấn tổng hợp phức tạp, khai báo **countQuery** tường minh và kiểm thử tổng số phần tử.

## 11. JPQL khác SQL ở điểm nào khi dùng GROUP BY?

JPQL làm việc trên entity model:

| JPQL | SQL tương ứng về ý tưởng |
|---|---|
| **PurchaseOrder** | Bảng **purchase_orders** |
| **o.totalAmount** | Cột **total_amount** |
| **o.customer.name** | Truy cập thuộc tính qua association/join |
| **count(o)** | Đếm entity/hàng tương ứng |
| **group by o.status** | Nhóm theo cột trạng thái |

Trong JPQL:

- Dùng tên entity, mặc định là tên lớp entity hoặc tên tùy chỉnh trong **@Entity(name = "...")**.
- Dùng tên thuộc tính Java, không dùng tên cột database nếu chúng khác nhau.
- Dùng association path hoặc JOIN để đi qua quan hệ.
- Không phụ thuộc trực tiếp vào tên bảng/cột vật lý hoặc cú pháp riêng của một database.

Nếu cần dùng hàm database đặc thù hoặc cú pháp SQL không có trong JPQL chuẩn, có thể cân nhắc native query. Tuy nhiên, native query làm giảm tính portable và cần tự quản lý mapping kết quả/count query cẩn thận.

## 12. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Database báo lỗi GROUP BY | SELECT có field không được group hoặc aggregate | Đưa field vào GROUP BY hoặc dùng hàm tổng hợp |
| Đặt điều kiện count trong WHERE | WHERE chạy trước grouping | Dùng HAVING |
| Đếm đơn bị nhân lên | JOIN collection tạo nhiều dòng cho một entity | Dùng count(distinct entity.id) khi mục tiêu là đếm entity duy nhất |
| Tổng tiền bị nhân lên | Join làm lặp giá trị tổng tiền của entity cha | Đổi cấu trúc truy vấn hoặc tổng hợp ở đúng mức dữ liệu |
| DTO constructor không khớp | Sai thứ tự hoặc kiểu tham số | Kiểm tra kiểu trả về aggregate và constructor |
| AVG BigDecimal bị ép sai kiểu | JPQL AVG trả Double | Khai báo DTO/biến đúng kiểu hoặc chuyển đổi có kiểm soát |
| SUM/AVG trả null | Không có giá trị đầu vào hoặc tập dữ liệu rỗng | Xử lý null hoặc dùng COALESCE |
| Page có tổng số trang sai | Count query không đếm số nhóm thực tế | Viết countQuery tương ứng với grouping |
| JPQL không tìm thấy thuộc tính | Dùng tên cột SQL thay vì field Java | Dùng entity name và thuộc tính entity |
| COUNT(*) không chạy | Cú pháp JPQL chuẩn yêu cầu biểu thức trong COUNT | Dùng count(o) hoặc count(o.id) |

## 13. Checklist viết truy vấn tổng hợp

- [ ] Xác định mỗi nhóm được tạo theo một hay nhiều thuộc tính.
- [ ] Dùng tên entity và thuộc tính Java trong JPQL.
- [ ] Đưa mọi biểu thức SELECT không tổng hợp vào GROUP BY.
- [ ] Dùng WHERE để lọc bản ghi trước khi nhóm.
- [ ] Dùng HAVING để lọc nhóm dựa trên kết quả tổng hợp.
- [ ] Chọn COUNT, SUM, AVG, MIN hoặc MAX đúng mục đích.
- [ ] Kiểm tra kiểu trả về của từng hàm tổng hợp.
- [ ] Dùng DTO projection thay cho Object[] khi truy vấn được dùng lâu dài.
- [ ] Kiểm tra JOIN có làm nhân số dòng trước khi đếm hoặc tính tổng không.
- [ ] Xử lý null và tập kết quả rỗng.
- [ ] Khai báo countQuery rõ ràng khi phân trang nhóm phức tạp.
- [ ] Kiểm thử SQL và kết quả với dữ liệu có nhiều nhóm, nhóm rỗng và association lặp.

## 14. Kết luận

**GROUP BY** gom entity thành các nhóm theo thuộc tính; **COUNT**, **SUM**, **AVG**, **MIN** và **MAX** tính chỉ số cho từng nhóm; **HAVING** lọc nhóm sau tổng hợp, còn **WHERE** lọc bản ghi trước khi nhóm.

Khi viết truy vấn báo cáo, hãy chú ý field trong SELECT phải phù hợp với GROUP BY, kiểu trả về của aggregate, tác động của JOIN tới số dòng và cách xử lý dữ liệu null. DTO projection giúp kết quả rõ ràng; count query tường minh giúp phân trang chính xác.