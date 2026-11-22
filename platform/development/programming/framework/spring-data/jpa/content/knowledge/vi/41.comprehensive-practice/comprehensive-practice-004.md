# Làm báo cáo có projection, tổng hợp và phân trang chính xác

Một báo cáo Spring Data JPA thường cần lấy một phần dữ liệu, tính tổng hợp theo nhóm và chia kết quả thành các trang. Để báo cáo vừa nhanh vừa chính xác, cần thiết kế đồng thời ba phần:

- **Projection** xác định những cột hoặc giá trị báo cáo thực sự cần.
- **Aggregation** dùng COUNT, SUM, AVG, MIN, MAX cùng GROUP BY, HAVING để tính kết quả ngay tại database.
- **Pagination** chia các hàng báo cáo và tính đúng tổng số hàng sau khi nhóm/lọc.

Điểm dễ sai nhất là câu truy vấn nội dung và câu truy vấn đếm tổng số trang không cùng một định nghĩa về kết quả. Với báo cáo có GROUP BY, một hàng kết quả thường đại diện cho một nhóm, không phải một bản ghi entity. Vì vậy, countQuery phải đếm số nhóm được trả về sau các điều kiện lọc.

## 1. Xác định đơn vị của một hàng báo cáo

Trước khi viết query, hãy trả lời câu hỏi: **một hàng trong báo cáo đại diện cho điều gì?**

Ví dụ báo cáo doanh thu theo khách hàng:

| customerId | customerName | orderCount | revenue |
|---:|---|---:|---:|
| 101 | An | 3 | 12,500,000 |
| 102 | Bình | 1 | 2,000,000 |
| 103 | Chi | 0 | 0 |

Mỗi hàng là một khách hàng, không phải một đơn hàng. Do đó:

- GROUP BY theo customer.
- COUNT đếm số đơn hàng của từng khách hàng.
- SUM cộng tổng tiền của các đơn hàng.
- Pagination chia các khách hàng sau khi đã tổng hợp.
- Total elements phải là số khách hàng thỏa điều kiện báo cáo, không phải số đơn hàng.

Nếu báo cáo đổi thành một hàng cho mỗi tháng và khách hàng, đơn vị nhóm trở thành cặp (customer, month). Khi đó countQuery phải đếm số cặp nhóm thỏa điều kiện, không thể chỉ đếm customer.

Hãy viết rõ đơn vị nhóm trước khi chọn projection hoặc pagination. Đây là cơ sở để kiểm tra countQuery.

## 2. Projection: chỉ lấy dữ liệu báo cáo cần dùng

Projection giúp truy vấn chỉ trả về các thuộc tính cần cho màn hình hoặc file báo cáo. Điều này giảm dữ liệu truyền từ database, tránh tải toàn bộ entity graph và làm rõ hợp đồng đầu ra.

Spring Data JPA thường dùng ba kiểu projection:

| Kiểu | Cách hoạt động | Phù hợp khi |
|---|---|---|
| Interface projection | Spring tạo proxy đọc các thuộc tính từ kết quả query | Báo cáo đơn giản, alias rõ ràng |
| Class/record DTO projection | JPA tạo đối tượng qua constructor | Cần kiểu trả về tường minh, bất biến |
| Dynamic projection | Caller chọn projection type khi gọi repository | Cùng query có nhiều hình thức hiển thị |

### 2.1. Interface projection

Khai báo interface:

~~~java
import java.math.BigDecimal;

public interface CustomerSalesView {

    Long getCustomerId();

    String getCustomerName();

    Long getOrderCount();

    BigDecimal getRevenue();
}
~~~

Các alias trong SELECT phải khớp với tên property mà projection cần đọc:

~~~java
@Query("""
    select
        c.id as customerId,
        c.name as customerName,
        count(o.id) as orderCount,
        coalesce(sum(o.totalAmount), :zero) as revenue
    from Customer c
    left join c.orders o
        on o.createdAt >= :from
       and o.createdAt < :to
    where c.active = true
    group by c.id, c.name
    order by revenue desc, c.id asc
    """)
List<CustomerSalesView> findSalesRows(
    @Param("from") Instant from,
    @Param("to") Instant to,
    @Param("zero") BigDecimal zero
);
~~~

Ví dụ trên chưa phân trang; nó minh họa cách tạo projection từ các biểu thức tổng hợp. Dùng LEFT JOIN để giữ khách hàng chưa có đơn trong khoảng thời gian. Điều kiện thời gian đặt trong ON để không biến LEFT JOIN thành INNER JOIN.

Nếu đặt điều kiện o.createdAt trong WHERE, các hàng có o null sẽ bị loại, khiến khách hàng không có đơn biến mất khỏi báo cáo.

### 2.2. Class hoặc record DTO projection

Nếu muốn kết quả là kiểu dữ liệu bất biến, có thể dùng Java record:

~~~java
package com.example.reporting;

import java.math.BigDecimal;

public record CustomerSalesReport(
    Long customerId,
    String customerName,
    Long orderCount,
    BigDecimal revenue
) {
}
~~~

JPQL dùng constructor expression với tên đầy đủ của DTO:

~~~java
@Query("""
    select new com.example.reporting.CustomerSalesReport(
        c.id,
        c.name,
        count(o.id),
        coalesce(sum(o.totalAmount), :zero)
    )
    from Customer c
    left join c.orders o
        on o.createdAt >= :from
       and o.createdAt < :to
    where c.active = true
    group by c.id, c.name
    order by coalesce(sum(o.totalAmount), :zero) desc, c.id asc
    """)
List<CustomerSalesReport> findSalesReports(
    @Param("from") Instant from,
    @Param("to") Instant to,
    @Param("zero") BigDecimal zero
);
~~~

Các kiểu constructor phải khớp với kiểu biểu thức JPQL:

- COUNT trả về Long.
- SUM trên thuộc tính BigDecimal trả về BigDecimal.
- COALESCE cần các đối số tương thích kiểu.
- ID và name phải có kiểu tương ứng với entity.

Không dùng SELECT c trong báo cáo nếu chỉ cần bốn trường trên. Lấy entity đầy đủ có thể kéo theo trạng thái persistence context, dirty checking hoặc lazy association không cần thiết.

### 2.3. Khi nào dùng projection lồng nhau?

Nested projection có thể hữu ích khi đọc cấu trúc quan hệ, nhưng không phải lựa chọn mặc định cho báo cáo tổng hợp. Với COUNT/SUM/GROUP BY, hãy ưu tiên các giá trị scalar và alias phẳng để tránh vô tình tải association hoặc tạo query phức tạp.

Không dùng projection như một cách thay thế cho GROUP BY. Projection chỉ định hình kết quả; aggregation vẫn phải được diễn đạt đúng trong query.

## 3. Aggregation với COUNT, SUM và COALESCE

Các hàm tổng hợp phổ biến trong JPQL:

| Hàm | Ý nghĩa | Kiểu kết quả thường gặp |
|---|---|---|
| COUNT(x) | Đếm giá trị không null | Long |
| SUM(x) | Tổng các giá trị | Kiểu số tương ứng theo JPA |
| AVG(x) | Trung bình | Double |
| MIN(x) | Giá trị nhỏ nhất | Kiểu của biểu thức |
| MAX(x) | Giá trị lớn nhất | Kiểu của biểu thức |

### 3.1. COUNT(o.id) và COUNT(*)

Với LEFT JOIN, khách hàng chưa có đơn vẫn tạo ra một hàng join có phần order null. Nếu dùng COUNT(*) trong SQL, hàng này vẫn được tính là một hàng. Dùng **COUNT(o.id)** để chỉ đếm đơn hàng có ID thực sự.

Ví dụ:

~~~sql
SELECT
    c.id,
    COUNT(o.id) AS order_count
FROM customer c
LEFT JOIN purchase_order o
    ON o.customer_id = c.id
GROUP BY c.id;
~~~

Khách hàng chưa có đơn sẽ có order_count bằng 0.

### 3.2. SUM có thể trả về null

Khi một nhóm không có giá trị để cộng, SUM có thể trả về null. Dùng **COALESCE** để đưa kết quả về 0 theo quy ước báo cáo:

~~~sql
COALESCE(SUM(o.total_amount), 0)
~~~

Với tiền tệ, dùng BigDecimal ở Java và kiểu DECIMAL/NUMERIC ở database. Tránh chuyển số tiền sang double vì sai số dấu phẩy động có thể làm kết quả báo cáo lệch.

### 3.3. WHERE và HAVING khác nhau

- **WHERE** lọc các hàng đầu vào trước khi nhóm.
- **HAVING** lọc các nhóm sau khi GROUP BY và tính aggregation.

Ví dụ chỉ lấy đơn hàng trong khoảng thời gian rồi giữ khách hàng có doanh thu ít nhất một ngưỡng:

~~~sql
SELECT
    customer_id,
    COUNT(id) AS order_count,
    SUM(total_amount) AS revenue
FROM purchase_order
WHERE created_at >= ?
  AND created_at < ?
GROUP BY customer_id
HAVING SUM(total_amount) >= ?;
~~~

Điều kiện ngày nằm trong WHERE vì nó lọc từng đơn hàng đầu vào. Điều kiện doanh thu nằm trong HAVING vì nó áp dụng trên tổng của nhóm.

Nếu cần giữ khách hàng không có đơn, hãy cẩn thận với vị trí điều kiện trên bảng con khi dùng LEFT JOIN. Đặt điều kiện vào WHERE có thể loại các nhóm không có đơn.

## 4. GROUP BY phải khớp với projection

Mọi biểu thức được SELECT mà không nằm trong hàm tổng hợp thường phải xuất hiện trong GROUP BY theo quy tắc JPQL/database.

Ví dụ:

~~~sql
SELECT
    c.id,
    c.name,
    COUNT(o.id),
    SUM(o.total_amount)
FROM customer c
LEFT JOIN purchase_order o
    ON o.customer_id = c.id
GROUP BY c.id, c.name;
~~~

Nếu thêm c.email vào SELECT, cần cập nhật GROUP BY phù hợp. Không dựa vào việc database dễ tính ra cột đó từ primary key nếu muốn query chạy nhất quán giữa các hệ quản trị.

Khi nhóm theo nhiều cấp, chẳng hạn customer và month, cả hai khóa nhóm phải có trong GROUP BY:

~~~sql
SELECT
    customer_id,
    EXTRACT(YEAR FROM created_at) AS report_year,
    EXTRACT(MONTH FROM created_at) AS report_month,
    SUM(total_amount)
FROM purchase_order
GROUP BY
    customer_id,
    EXTRACT(YEAR FROM created_at),
    EXTRACT(MONTH FROM created_at);
~~~

Cú pháp trích năm/tháng có thể khác theo database và JPQL provider. Nếu query phụ thuộc dialect, hãy kiểm thử bằng database production tương ứng hoặc dùng native query có chủ đích.

## 5. Phân trang với Page và countQuery

Spring Data JPA hỗ trợ trả về **Page<T>** để có nội dung trang và thông tin tổng số phần tử/trang.

Ví dụ repository báo cáo theo khách hàng:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface CustomerRepository extends JpaRepository<Customer, Long> {

    @Query(
        value = """
            select new com.example.reporting.CustomerSalesReport(
                c.id,
                c.name,
                count(o.id),
                coalesce(sum(o.totalAmount), :zero)
            )
            from Customer c
            left join c.orders o
                on o.createdAt >= :from
               and o.createdAt < :to
            where c.active = true
            group by c.id, c.name
            order by coalesce(sum(o.totalAmount), :zero) desc, c.id asc
            """,
        countQuery = """
            select count(c.id)
            from Customer c
            where c.active = true
            """
    )
    Page<CustomerSalesReport> findSalesReport(
        @Param("from") Instant from,
        @Param("to") Instant to,
        @Param("zero") BigDecimal zero,
        Pageable pageable
    );
}
~~~

Count query trên chính xác vì:

- Content query tạo đúng một nhóm cho mỗi khách hàng active.
- LEFT JOIN giữ cả khách hàng không có đơn trong khoảng thời gian.
- Không có HAVING loại bỏ một số nhóm.
- Do đó tổng số nhóm chính là số khách hàng active.

Nếu thêm điều kiện HAVING như tổng doanh thu phải lớn hơn một ngưỡng, count query trên sẽ sai vì nó vẫn đếm cả khách hàng không đạt ngưỡng. Count query luôn phải phản ánh đúng điều kiện tạo ra các hàng của content query.

### 5.1. Page yêu cầu đếm tổng số hàng

Page chứa dữ liệu trang hiện tại và metadata như totalElements, totalPages. Để tính các giá trị đó, Spring Data thường thực hiện count query khi cần. Tùy trường hợp, framework có thể suy ra tổng từ nội dung trang cuối mà không cần gọi count; nhưng không nên dựa vào tối ưu này để thay thế countQuery đúng.

Với query tổng hợp, hãy khai báo countQuery tường minh nếu query phức tạp hoặc Spring không thể suy ra phép đếm đúng.

### 5.2. Count query cho GROUP BY và HAVING

Giả sử báo cáo có một hàng cho mỗi khách hàng, chỉ giữ nhóm có ít nhất ba đơn hàng. Content query có HAVING:

~~~sql
SELECT
    c.id,
    c.name,
    COUNT(o.id) AS order_count
FROM customer c
LEFT JOIN purchase_order o
    ON o.customer_id = c.id
WHERE c.active = true
GROUP BY c.id, c.name
HAVING COUNT(o.id) >= 3;
~~~

Không thể dùng countQuery đơn giản là:

~~~sql
SELECT COUNT(DISTINCT c.id)
FROM customer c
LEFT JOIN purchase_order o
    ON o.customer_id = c.id
WHERE c.active = true;
~~~

Query đó đếm cả khách hàng có ít hơn ba đơn hàng. Nó không áp dụng HAVING nên totalElements sẽ lớn hơn số nhóm thực tế.

Với native SQL, có thể đếm các nhóm qua subquery:

~~~sql
SELECT COUNT(*)
FROM (
    SELECT c.id
    FROM customer c
    LEFT JOIN purchase_order o
        ON o.customer_id = c.id
    WHERE c.active = true
    GROUP BY c.id
    HAVING COUNT(o.id) >= 3
) grouped_customers;
~~~

Khi dùng native query với Page, khai báo countQuery riêng trong @Query. Subquery trong FROM và cách đặt alias phụ thuộc SQL dialect, vì vậy hãy chạy trên database thực tế. Nếu JPQL không biểu diễn được count nhóm cần thiết, native count query hoặc một bước truy vấn riêng có thể rõ ràng hơn.

### 5.3. COUNT DISTINCT khi nào đủ?

Nếu mỗi nhóm tương ứng đúng một customer và không có HAVING, **COUNT(DISTINCT c.id)** có thể đếm số nhóm. Nhưng nếu một nhóm là (customer, month), phải đếm số cặp đó. COUNT(DISTINCT c.id) sẽ đếm khách hàng và bỏ qua số tháng.

Nếu có HAVING, điều kiện lọc nhóm phải được phản ánh trong count query. Đừng chỉ nhìn thấy JOIN rồi thêm DISTINCT để chữa duplicate; hãy xác định chính xác grain của báo cáo.

## 6. Khi không cần tổng số phần tử: Slice

Nếu giao diện chỉ cần nút Trang tiếp theo và không hiển thị tổng số trang, dùng **Slice<T>** có thể tiết kiệm chi phí.

- Page thường cần total count để cung cấp totalElements/totalPages.
- Slice chỉ cần biết còn dữ liệu tiếp theo hay không; Spring Data thường lấy thêm một hàng để xác định hasNext.
- Với báo cáo tổng hợp lớn, bỏ count query có thể giảm đáng kể chi phí.

Ví dụ:

~~~java
Slice<CustomerSalesView> findByActiveTrue(Pageable pageable);
~~~

Đây là ví dụ derived query minh họa kiểu trả về; báo cáo aggregate thực tế vẫn cần query projection tương ứng. Nếu nghiệp vụ không cần total count, cân nhắc Slice thay vì Page.

Không trả về List khi caller cần phân trang ở database. Lấy toàn bộ kết quả rồi chia bằng Java sẽ tiêu tốn bộ nhớ và thời gian theo tổng dữ liệu.

## 7. Sắp xếp ổn định để tránh lặp hoặc bỏ sót hàng

Báo cáo cần thứ tự xác định. Nếu chỉ sắp xếp theo doanh thu, nhiều khách hàng có thể có cùng revenue. Hãy thêm khóa duy nhất làm tie-breaker:

~~~sql
ORDER BY revenue DESC, customer_id ASC
~~~

Thứ tự ổn định giúp các trang có kết quả nhất quán hơn khi giá trị tổng hợp bằng nhau.

Với Sort truyền từ Pageable:

- Chỉ cho phép sort theo các thuộc tính/biểu thức đã được whitelist.
- Alias của projection không phải lúc nào cũng là thuộc tính entity.
- Native query và dynamic sort có khác biệt theo Spring Data JPA version/provider.
- Không nối trực tiếp chuỗi sort từ request vào SQL.

Nếu query đã có ORDER BY cố định, truyền Pageable không yêu cầu thêm sort hoặc dùng Sort.unsorted() để tránh tạo thứ tự chồng lặp không mong muốn.

## 8. Pagination và dữ liệu thay đổi đồng thời

Page thường gồm ít nhất hai câu SQL logic: content query và count query. Nếu dữ liệu thay đổi giữa hai lần thực thi, nội dung trang và totalElements có thể phản ánh hai thời điểm khác nhau.

Ví dụ:

1. Content query trả về 20 khách hàng.
2. Một transaction khác thêm khách hàng mới hoặc thay đổi đơn hàng.
3. Count query chạy sau đó và đếm được số nhóm mới.

Kết quả có thể không phải một snapshot hoàn toàn đồng nhất, tùy isolation level và database. Với báo cáo vận hành thông thường, điều này có thể chấp nhận được. Với báo cáo tài chính hoặc đối soát cần tính tái lập:

- Chạy content và count trong transaction có isolation/snapshot phù hợp với database.
- Dùng cùng khoảng thời gian báo cáo cố định.
- Lưu thời điểm chốt dữ liệu hoặc phiên bản snapshot.
- Với báo cáo rất lớn, cân nhắc bảng tổng hợp/materialized view được cập nhật theo quy trình riêng.

Không giả định rằng chỉ cần đặt @Transactional là hai câu query luôn nhìn thấy cùng snapshot trên mọi database. Isolation semantics phụ thuộc engine và cấu hình.

## 9. Tránh N+1 và phân trang sai khi join collection

Với báo cáo, projection scalar/DTO thường tốt hơn việc tải entity rồi truy cập lazy association trong vòng lặp.

Một số lỗi cần tránh:

- Tải Page<Customer> rồi gọi customer.getOrders() cho từng customer gây N+1.
- Dùng JOIN FETCH cho collection trong query phân trang; kết quả join có thể nhân số hàng, làm phân trang sai hoặc khiến provider phải phân trang trong bộ nhớ.
- Đếm số hàng JOIN thay vì số nhóm báo cáo.
- Chọn toàn bộ entity dù chỉ cần vài cột.
- Dùng DISTINCT để che lỗi join mà không hiểu grain của báo cáo.

Hãy để database tính aggregation và trả về một hàng DTO cho mỗi nhóm. Nếu cần chi tiết từng đơn hàng, đó có thể là một endpoint/query khác với phân trang theo đơn hàng.

## 10. Kiểm thử báo cáo có projection và pagination

Một integration test cần xác nhận cả nội dung projection lẫn metadata phân trang.

Dùng fixture cố định, ví dụ:

| Customer | Đơn hàng trong kỳ | Tổng tiền | Có active? |
|---|---:|---:|---|
| A | 2 | 1,000 | Có |
| B | 1 | 500 | Có |
| C | 0 | 0 | Có |
| D | 4 | 4,000 | Không |

Với báo cáo tất cả khách hàng active, kết quả phải có ba hàng: A, B và C. Tổng số đơn là 2, 1 và 0; doanh thu là 1,000, 500 và 0.

Test nên xác nhận:

1. Projection chỉ có đúng các trường báo cáo cần dùng.
2. COUNT(o.id) không đếm hàng null của LEFT JOIN.
3. SUM/COALESCE trả 0 cho khách hàng không có đơn.
4. GROUP BY tạo đúng một hàng cho mỗi khách hàng.
5. Count query trả totalElements = 3.
6. Page size 2 tạo trang đầu có hai hàng và trang sau có một hàng.
7. Thứ tự doanh thu giảm dần, tie-breaker ổn định.
8. Khách hàng inactive không xuất hiện.
9. Khoảng thời gian from/to lọc đúng; dùng quy ước from inclusive, to exclusive.
10. Nếu có HAVING, countQuery đếm đúng số nhóm sau HAVING.

### 10.1. Ví dụ test với Page

~~~java
@DataJpaTest
class CustomerSalesReportRepositoryTest {

    @Autowired
    private CustomerRepository customers;

    @Test
    void returnsCorrectGroupsAndTotalPages() {
        Pageable pageable = PageRequest.of(0, 2, Sort.unsorted());

        Page<CustomerSalesReport> page = customers.findSalesReport(
            Instant.parse("2026-01-01T00:00:00Z"),
            Instant.parse("2026-02-01T00:00:00Z"),
            BigDecimal.ZERO,
            pageable
        );

        assertEquals(2, page.getContent().size());
        assertEquals(3, page.getTotalElements());
        assertEquals(2, page.getTotalPages());

        CustomerSalesReport first = page.getContent().get(0);
        assertEquals(2L, first.orderCount());
        assertEquals(new BigDecimal("1000.00"), first.revenue());
    }
}
~~~

Ví dụ giả định fixture được tạo trước test, CustomerSalesReport là record đã khai báo, repository có phương thức findSalesReport như phần trước và các giá trị tiền được lưu theo scale 2. Cần import JUnit assertions, Page, Pageable, PageRequest, Sort, Instant và BigDecimal.

Với @DataJpaTest, test method mặc định chạy trong transaction và thường rollback sau test. Fixture có thể được tạo bằng repository/EntityManager trong cùng transaction hoặc bằng @Sql theo transaction mode đã chọn.

### 10.2. Test countQuery riêng cho HAVING

Tạo fixture có nhóm đạt và không đạt ngưỡng, sau đó kiểm tra:

- Content query chỉ trả nhóm đạt HAVING.
- totalElements chỉ đếm nhóm đạt HAVING.
- Khi chuyển trang, không có nhóm bị lặp do join.
- Page cuối có số hàng đúng.
- Count query native chạy được trên database production.

Đây là test quan trọng vì một báo cáo có thể hiển thị đúng trang đầu nhưng totalPages sai do countQuery không phản ánh GROUP BY/HAVING.

### 10.3. Chọn database phù hợp

H2 hữu ích cho test nhanh nhưng có thể khác PostgreSQL/MySQL/SQL Server về hàm ngày giờ, kiểu số, alias native query, group-by validation và SQL dialect. Nếu báo cáo dùng native SQL hoặc biểu thức đặc thù, hãy chạy integration test bằng Testcontainers với database gần production.

Không chỉ test kết quả của một bộ fixture nhỏ. Cần kiểm tra query plan và index khi dữ liệu lớn để bảo đảm việc group, sort và count không trở thành nút thắt.

## 11. Tối ưu hiệu năng báo cáo

Các điểm thường đem lại hiệu quả:

- Chỉ SELECT các cột cần cho projection.
- Lọc theo khoảng thời gian và điều kiện nghiệp vụ trước khi group.
- Tạo index phù hợp với join key và filter, ví dụ customer_id, created_at hoặc tổ hợp theo query thực tế.
- Tránh gọi count query quá đắt nếu giao diện chỉ cần Slice.
- Xem EXPLAIN/EXPLAIN ANALYZE trên database triển khai.
- Đo riêng content query và count query.
- Nếu tổng hợp theo kỳ lặp lại nhiều lần, cân nhắc summary table hoặc materialized view.
- Dùng keyset pagination khi phù hợp với thứ tự và nhu cầu điều hướng; keyset không cung cấp total count tự động.

Không tạo index theo cảm tính. Index cần dựa trên điều kiện WHERE, JOIN, GROUP BY và ORDER BY thực tế; index quá nhiều cũng làm chậm INSERT/UPDATE.

## 12. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| totalElements lớn hơn số hàng báo cáo | Count query đếm hàng JOIN thay vì nhóm | Đếm đúng grain, dùng count distinct hoặc subquery nhóm |
| totalPages sai khi có HAVING | Count query không áp dụng HAVING | Đếm subquery chứa cùng GROUP BY/HAVING |
| Khách hàng không có đơn biến mất | Điều kiện bảng con đặt trong WHERE sau LEFT JOIN | Đặt điều kiện phù hợp trong ON |
| orderCount của khách hàng không đơn bằng 1 | Dùng COUNT(*) với LEFT JOIN | Dùng COUNT(o.id) |
| revenue trả null | SUM trên nhóm không có giá trị | Dùng COALESCE với kiểu số phù hợp |
| DTO constructor không khớp | Sai thứ tự hoặc kiểu tham số constructor | Kiểm tra COUNT, SUM và constructor expression |
| Interface projection trả null | Alias không khớp getter | Đặt alias đúng tên property |
| Dữ liệu lặp giữa các trang | Join nhân hàng hoặc sort không ổn định | Group đúng grain, sắp xếp thêm khóa duy nhất |
| Page query rất chậm | Count query hoặc GROUP BY tốn kém | Đo riêng count/content, thêm index hoặc dùng Slice |
| H2 pass nhưng production fail | Native SQL hoặc hàm phụ thuộc dialect | Kiểm thử bằng database production tương ứng |
| Số tổng thay đổi giữa content và count | Dữ liệu bị cập nhật giữa hai query | Chọn isolation/snapshot phù hợp với yêu cầu báo cáo |

## 13. Checklist triển khai

- [ ] Đã xác định một hàng báo cáo đại diện cho entity hay nhóm nào.
- [ ] Projection chỉ lấy trường cần cho báo cáo.
- [ ] Interface projection có alias khớp getter hoặc DTO có constructor đúng kiểu.
- [ ] COUNT(o.id) được dùng đúng khi LEFT JOIN.
- [ ] SUM được xử lý null bằng COALESCE khi nghiệp vụ cần.
- [ ] WHERE lọc hàng đầu vào và HAVING lọc nhóm.
- [ ] GROUP BY chứa các biểu thức không tổng hợp được SELECT.
- [ ] Content query và countQuery có cùng điều kiện nghiệp vụ.
- [ ] CountQuery đếm nhóm sau HAVING, không đếm hàng JOIN.
- [ ] Dùng Slice nếu không cần totalElements/totalPages.
- [ ] ORDER BY có tie-breaker duy nhất để phân trang ổn định.
- [ ] Sort động được whitelist; không nối raw input vào SQL.
- [ ] Đã đánh giá thay đổi đồng thời giữa content và count query.
- [ ] Integration test kiểm tra projection, tổng hợp, page size, totalElements và totalPages.
- [ ] Native query được kiểm thử trên database phù hợp production.
- [ ] Đã đo content query, count query và query plan trên dữ liệu đủ lớn.

## 14. Ghi nhớ

Projection quyết định dữ liệu nào được trả về; aggregation quyết định cách database tạo các nhóm; pagination chia các nhóm đó thành trang. Muốn Page chính xác, countQuery phải đếm đúng đơn vị của một hàng báo cáo và áp dụng cùng điều kiện lọc, đặc biệt là GROUP BY và HAVING.

Với báo cáo tổng hợp, hãy ưu tiên DTO/interface projection phẳng, dùng COUNT(o.id) cho LEFT JOIN, COALESCE cho giá trị tổng rỗng, ORDER BY ổn định và integration test xác nhận cả nội dung lẫn totalElements. Nếu không cần tổng số trang, Slice có thể tránh một count query tốn kém.

## Tài liệu tham khảo

- [Spring Data JPA — Projections](https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html)
- [Spring Data JPA — Query methods and countQuery](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Spring Data Commons — Paging and sorting](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html)
- [Jakarta Persistence — JPQL and aggregate functions](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html)

