# QueryCreationException, lỗi JPQL và tham số không khớp trong Spring Data JPA

Khi một repository method không thể tạo hoặc thực thi truy vấn, Spring Data JPA có thể báo lỗi ngay lúc khởi động ứng dụng hoặc chỉ khi method được gọi. Một nhóm lỗi thường gặp là QueryCreationException, lỗi cú pháp/định danh trong JPQL và lỗi bind parameter không khớp giữa chữ ký method với câu query.

Cách xử lý hiệu quả là tìm nguyên nhân gốc thay vì chỉ nhìn exception ngoài cùng. Cần xác định lỗi nằm ở bước phân tích tên method, xác thực JPQL, bind parameter, chuyển đổi kiểu, thực thi SQL hay ánh xạ kết quả. Mỗi bước có dấu hiệu và cách sửa khác nhau.

Bài học này dùng một mô hình PurchaseOrder nhất quán để minh họa derived query, @Query, named/positional parameter, Page/countQuery, DTO projection và modifying query. Các phần sau trình bày cách đọc stack trace, xác minh tên entity/property, xử lý tham số, kiểm thử repository và xây dựng quy trình chẩn đoán có thể áp dụng trong dự án.

## 1. QueryCreationException là gì?

QueryCreationException thuộc Spring Data Commons và thường xuất hiện khi Spring Data không thể tạo query cho một repository method. Nó có thể bao bọc một nguyên nhân cụ thể hơn, ví dụ:

- Không tìm thấy property mà derived query tham chiếu.
- Tên method không thể được phân tích thành một query hợp lệ.
- JPQL khai báo trong @Query không hợp lệ hoặc tham chiếu entity/property không tồn tại.
- Parameter trong query không khớp với tham số method.
- Kiểu trả về hoặc chữ ký method không phù hợp với cách query được tạo.

Tên exception không nói chính xác lỗi nằm ở đâu. Luôn xem phần Caused by sâu nhất và message của provider.

Ví dụ stack trace có thể có dạng:

~~~text
org.springframework.data.repository.query.QueryCreationException:
Could not create query for method ...
    at ...
Caused by: org.springframework.data.mapping.PropertyReferenceException:
No property 'customerMail' found for type 'PurchaseOrder'
~~~

Nguyên nhân gốc ở đây là tên property sai: entity có customerEmail nhưng method dùng customerMail.

Một trường hợp khác:

~~~text
org.springframework.data.repository.query.QueryCreationException:
Could not create query for method ...
Caused by: java.lang.IllegalArgumentException:
Validation failed for query for method ...
Caused by: org.hibernate.query.SemanticException:
Could not resolve attribute 'orderStatus' of 'PurchaseOrder'
~~~

Lỗi này nằm trong JPQL: entity có property status, không có orderStatus.

Không nên kết luận mọi lỗi truy vấn đều là QueryCreationException. Một số lỗi chỉ xuất hiện khi thực thi và có thể được bọc thành DataAccessException, InvalidDataAccessApiUsageException hoặc exception từ JPA provider. Loại exception cụ thể phụ thuộc Spring Data, Hibernate và thời điểm query được tạo/kiểm tra.

## 2. Truy vấn được tạo ở thời điểm nào?

Spring Data JPA có thể tạo query từ nhiều nguồn:

1. Derived query: phân tích tên method như findByStatusAndCreatedAtAfter.
2. Declared query: câu JPQL hoặc native SQL khai báo bằng @Query.
3. Named query: query được khai báo bằng annotation hoặc XML.
4. Custom repository: code tự tạo query bằng EntityManager hoặc Criteria API.

Mặc định, Spring Data thường ưu tiên query khai báo nếu có và có thể suy luận query từ tên method khi không có declared query. Query lookup strategy có thể được cấu hình thành CREATE, USE_DECLARED_QUERY hoặc CREATE_IF_NOT_FOUND.

Repository thường được khởi tạo khi application context khởi động, nên lỗi có thể xuất hiện trước khi endpoint được gọi. Tuy nhiên, bootstrap mode, lazy/deferred repository initialization và cách provider xác thực query có thể làm thời điểm phát hiện thay đổi.

Một số lỗi cú pháp JPQL được phát hiện khi repository tạo query. Một số lỗi bind/type hoặc SQL dialect chỉ xuất hiện khi query thực sự chạy. Vì vậy:

- Lỗi ngay lúc khởi động thường hướng tới repository method parsing, query validation, mapping hoặc bean configuration.
- Lỗi ở lần gọi method đầu tiên có thể liên quan lazy repository initialization, parameter binding, database SQL hoặc dữ liệu.
- Lỗi chỉ xuất hiện với một bộ tham số thường hướng tới null, collection rỗng, kiểu dữ liệu, sort hoặc nhánh điều kiện cụ thể.

Không dựa riêng vào thời điểm lỗi để kết luận; cần kết hợp stack trace, query và method signature.

## 3. Mô hình entity dùng xuyên suốt bài học

Các ví dụ dùng entity PurchaseOrder trong package com.example.orders. Tên entity và property được khai báo rõ để tránh nhầm JPQL với tên bảng/cột.

Enum:

~~~java
package com.example.orders;

public enum OrderStatus {
    NEW,
    PAID,
    SHIPPED,
    CANCELLED
}
~~~

Entity:

~~~java
package com.example.orders;

import java.math.BigDecimal;
import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 200)
    private String customerEmail;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private OrderStatus status;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal totalAmount;

    @Column(nullable = false)
    private Instant createdAt;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(
            String customerEmail,
            OrderStatus status,
            BigDecimal totalAmount,
            Instant createdAt) {
        this.customerEmail = customerEmail;
        this.status = status;
        this.totalAmount = totalAmount;
        this.createdAt = createdAt;
    }

    public Long getId() {
        return id;
    }

    public String getCustomerEmail() {
        return customerEmail;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
~~~

Mapping có các thuộc tính Java:

- id
- customerEmail
- status
- totalAmount
- createdAt

Tên bảng database là purchase_orders. JPQL phải dùng tên entity PurchaseOrder và các thuộc tính Java, không dùng purchase_orders hoặc tên cột vật lý.

## 4. Lỗi derived query: tên property không tồn tại

Spring Data phân tích tên method thành subject và predicate. Phần sau By mô tả điều kiện theo tên property và keyword.

Ví dụ đúng:

~~~java
List<PurchaseOrder> findByStatus(OrderStatus status);

List<PurchaseOrder> findByCustomerEmail(String customerEmail);

List<PurchaseOrder> findByStatusAndCreatedAtAfter(
        OrderStatus status,
        Instant createdAt);
~~~

Các method này tham chiếu property thực sự tồn tại trên PurchaseOrder.

Ví dụ sai:

~~~java
List<PurchaseOrder> findByOrderStatus(OrderStatus status);
~~~

Entity không có property orderStatus. Spring Data có thể báo PropertyReferenceException với thông báo gần giống No property 'orderStatus' found for type 'PurchaseOrder', sau đó được bọc trong lỗi tạo repository query.

Cách sửa là dùng đúng property:

~~~java
List<PurchaseOrder> findByStatus(OrderStatus status);
~~~

Checklist khi gặp PropertyReferenceException:

1. Mở entity và kiểm tra tên field/property thực tế.
2. Kiểm tra chính tả và chữ hoa/chữ thường.
3. Kiểm tra getter/property access nếu entity dùng property-based access.
4. Kiểm tra đường dẫn association lồng nhau.
5. Không nhầm tên cột @Column(name = ...) với tên property Java.

Ví dụ:

~~~java
@Column(name = "customer_email")
private String customerEmail;
~~~

Derived query vẫn dùng findByCustomerEmail, không dùng findByCustomer_Email chỉ vì tên cột có dấu gạch dưới.

## 5. Lỗi phân tích nested property path

Spring Data có thể phân tích đường dẫn qua association. Ví dụ nếu PurchaseOrder có association customer và Customer có property email, method có thể dùng findByCustomer_Email.

Dấu gạch dưới giúp phân định ranh giới property path rõ ràng:

~~~java
List<PurchaseOrder> findByCustomer_Email(String email);
~~~

Trong mô hình bài học hiện tại, PurchaseOrder có customerEmail là một String, không có association customer. Do đó findByCustomer_Email không hợp lệ với entity hiện tại.

Khi entity có nhiều property tên gần nhau, parser có thể phân tách path theo cách khác với ý định. Dùng dấu gạch dưới để chỉ rõ điểm đi qua association và kiểm tra tên từng bước.

Ví dụ minh họa entity khác:

~~~java
@Entity
public class Customer {
    @Id
    private Long id;

    private String email;
}

@Entity
public class SalesOrder {
    @ManyToOne
    private Customer customer;
}
~~~

Với mô hình này, SalesOrder có thể dùng:

~~~java
List<SalesOrder> findByCustomer_Email(String email);
~~~

Không sao chép method đó vào PurchaseOrder nếu entity không có association tương ứng.

## 6. Các keyword derived query thường dùng

Một số keyword phổ biến:

| Keyword | Ý nghĩa | Ví dụ |
|---|---|---|
| Is, Equals | Bằng | findByStatus |
| And | Kết hợp AND | findByStatusAndCustomerEmail |
| Or | Kết hợp OR | findByStatusOrCustomerEmail |
| After | Lớn hơn với kiểu ngày/giờ | findByCreatedAtAfter |
| Before | Nhỏ hơn với kiểu ngày/giờ | findByCreatedAtBefore |
| Between | Nằm trong khoảng | findByCreatedAtBetween |
| GreaterThan | Lớn hơn | findByTotalAmountGreaterThan |
| LessThan | Nhỏ hơn | findByTotalAmountLessThan |
| In | Thuộc tập giá trị | findByStatusIn |
| IsNull | Giá trị null | findByCustomerEmailIsNull |
| IsNotNull | Khác null | findByCustomerEmailIsNotNull |
| Containing | Chuỗi con | findByCustomerEmailContaining |
| StartingWith | Bắt đầu bằng | findByCustomerEmailStartingWith |
| EndingWith | Kết thúc bằng | findByCustomerEmailEndingWith |
| IgnoreCase | Không phân biệt hoa thường cho chuỗi | findByCustomerEmailIgnoreCase |
| OrderBy | Sắp xếp | findByStatusOrderByCreatedAtDesc |
| First, Top | Giới hạn kết quả | findFirstByStatusOrderByCreatedAtDesc |

Keyword phải tương thích với kiểu property. Ví dụ IgnoreCase phù hợp với String; không áp dụng tùy tiện cho enum hoặc Instant.

Nếu method name quá dài hoặc điều kiện có nhóm ngoặc phức tạp, dùng @Query, Specification hoặc Querydsl thay vì cố biểu diễn toàn bộ logic bằng tên method.

## 7. Tên method có thể hợp lệ nhưng mang ý nghĩa khác dự định

Một method có thể được parser chấp nhận nhưng query sinh ra không đúng ý nghiệp vụ. Ví dụ:

~~~java
List<PurchaseOrder> findByStatusOrCustomerEmailAndCreatedAtAfter(
        OrderStatus status,
        String email,
        Instant createdAt);
~~~

Thứ tự toán tử trong derived query có quy tắc phân tích riêng; không nên giả định biểu thức được nhóm giống cách đọc tự nhiên. Nếu cần logic rõ ràng như:

~~~text
(status = PAID OR customerEmail = ...)
AND createdAt > ...
~~~

hãy viết @Query với ngoặc tường minh hoặc dùng Specification/Criteria API.

Đừng chỉ kiểm tra method có khởi tạo được hay không. Hãy kiểm tra SQL và kết quả với dữ liệu đại diện để xác nhận logic AND/OR.

## 8. Reserved method name trong repository

Một số tên method kế thừa từ CrudRepository/JpaRepository có ngữ nghĩa đặc biệt. Ví dụ findById được định nghĩa để tìm theo identifier của entity.

Nếu entity có một property nghiệp vụ tên id khác với khóa chính hoặc bạn muốn tìm theo property không phải khóa chính, tránh giả định rằng method trùng tên sẽ được phân tích như derived query thông thường.

Dùng tên method rõ nghĩa khác hoặc @Query tường minh khi có xung đột với method kế thừa. Khi gặp kết quả truy vấn bất ngờ, kiểm tra xem method có đang override/khớp method nền tảng của repository hay không.

## 9. JPQL dùng entity name và property name

JPQL truy vấn entity model, không truy vấn trực tiếp bảng SQL.

Ví dụ đúng:

~~~java
@Query("""
       select o
       from PurchaseOrder o
       where o.status = :status
       """)
List<PurchaseOrder> findByStatusJpql(
        @Param("status") OrderStatus status);
~~~

Các thành phần:

- PurchaseOrder là entity name mặc định theo tên class, trừ khi @Entity(name = "...") đặt tên khác.
- o là alias.
- o.status là persistent property Java.
- :status là named parameter.

Ví dụ sai:

~~~java
@Query("""
       select *
       from purchase_orders
       where order_status = :status
       """)
List<PurchaseOrder> findByStatusJpql(
        @Param("status") OrderStatus status);
~~~

Đây là cú pháp SQL, không phải JPQL. SELECT * và tên bảng/cột vật lý không phù hợp trong JPQL.

Nếu muốn viết SQL trực tiếp, khai báo nativeQuery = true và dùng đúng dialect/schema:

~~~java
@Query(
    value = """
            select *
            from purchase_orders
            where status = :status
            """,
    nativeQuery = true
)
List<PurchaseOrder> findNativeByStatus(
        @Param("status") String status);
~~~

Native query phải dùng tên cột vật lý và kiểu parameter phù hợp với schema/database. Nếu enum được lưu bằng STRING, giá trị truyền cho native query thường cần được chuyển thành tên enum; mapping native enum không giống JPQL entity parameter trong mọi provider.

## 10. Các lỗi JPQL phổ biến

| Lỗi | Ví dụ sai | Cách kiểm tra/sửa |
|---|---|---|
| Sai entity name | from Orders o | Dùng PurchaseOrder hoặc entity name đã khai báo |
| Sai property | o.orderStatus | Dùng o.status |
| Dùng tên cột | o.customer_email | Dùng o.customerEmail |
| Sai alias | where p.status nhưng alias là o | Dùng đúng alias đã khai báo |
| Thiếu alias | select PurchaseOrder from PurchaseOrder | Khai báo alias, ví dụ select o from PurchaseOrder o |
| Dùng cú pháp SQL | select * from purchase_orders | Chuyển sang nativeQuery hoặc viết JPQL |
| Sai kiểu literal | o.status = 1 trong khi status là enum | Bind OrderStatus |
| Sai constructor DTO | new com.example.Dto(...) với tham số không khớp | Kiểm tra FQCN, thứ tự và kiểu constructor |
| Fetch join không hợp lệ | fetch trong count query | Tách count query, không fetch association |
| Aggregate thiếu GROUP BY | chọn field thường cùng count | Thêm GROUP BY phù hợp |
| Sai toán tử | dùng cú pháp không được JPQL hỗ trợ | Kiểm tra JPQL/provider version |

JPQL được provider phân tích theo entity mapping. Khi gặp lỗi, kiểm tra chính xác class entity, field, association, kiểu dữ liệu và alias trước khi sửa SQL/database.

## 11. Named parameter: tên phải khớp chính xác

Với named parameter, placeholder trong JPQL phải khớp tên trong @Param.

Đúng:

~~~java
@Query("""
       select o
       from PurchaseOrder o
       where o.status = :status
         and o.customerEmail = :email
       """)
List<PurchaseOrder> search(
        @Param("status") OrderStatus status,
        @Param("email") String customerEmail);
~~~

Sai:

~~~java
@Query("""
       select o
       from PurchaseOrder o
       where o.status = :orderStatus
       """)
List<PurchaseOrder> findByStatus(
        @Param("status") OrderStatus status);
~~~

Query dùng :orderStatus nhưng method bind tên status. Provider có thể báo không tìm thấy parameter hoặc Spring Data báo không thể bind parameter tương ứng.

Cách sửa: đồng nhất tên placeholder và @Param:

~~~java
@Query("""
       select o
       from PurchaseOrder o
       where o.status = :status
       """)
List<PurchaseOrder> findByStatus(
        @Param("status") OrderStatus status);
~~~

Tên parameter phân biệt chính xác theo cách provider xử lý. Hãy giữ quy ước nhất quán, không đổi tên một phía rồi quên phía còn lại.

## 12. Số lượng parameter phải khớp

Nếu JPQL có hai placeholder nhưng method chỉ cung cấp một bindable parameter, query không thể được bind đầy đủ.

Sai:

~~~java
@Query("""
       select o
       from PurchaseOrder o
       where o.status = :status
         and o.customerEmail = :email
       """)
List<PurchaseOrder> search(
        @Param("status") OrderStatus status);
~~~

Query yêu cầu cả status và email nhưng method chỉ có status.

Đúng:

~~~java
@Query("""
       select o
       from PurchaseOrder o
       where o.status = :status
         and o.customerEmail = :email
       """)
List<PurchaseOrder> search(
        @Param("status") OrderStatus status,
        @Param("email") String email);
~~~

Cũng cần kiểm tra parameter method không còn được sử dụng trong query sau khi sửa. Parameter thừa có thể khiến Spring Data không biết bind vào đâu hoặc làm query signature khó hiểu.

Khi thêm/xóa placeholder, cập nhật đồng thời method signature, @Param và test gọi repository.

## 13. Named parameter và positional parameter

Có hai cách bind phổ biến.

Named parameter:

~~~java
@Query("""
       select o
       from PurchaseOrder o
       where o.status = :status
         and o.createdAt >= :from
       """)
List<PurchaseOrder> findByStatusFrom(
        @Param("status") OrderStatus status,
        @Param("from") Instant from);
~~~

Positional parameter:

~~~java
@Query("""
       select o
       from PurchaseOrder o
       where o.status = ?1
         and o.createdAt >= ?2
       """)
List<PurchaseOrder> findByStatusFrom(
        OrderStatus status,
        Instant from);
~~~

Với positional parameter, ?1 là tham số thứ nhất, ?2 là tham số thứ hai. Thứ tự method signature phải khớp.

Không trộn named và positional parameter trong cùng một query. Chọn một phong cách cho từng query. Named parameter thường dễ đọc và ít lỗi hơn khi method có nhiều tham số.

Nếu dùng named parameter, khai báo @Param tường minh giúp code rõ ràng và tránh phụ thuộc cấu hình lưu tên parameter của compiler.

## 14. @Param và tùy chọn giữ tên parameter bằng compiler

Một số phiên bản Spring Data có thể suy ra tên method parameter nếu ứng dụng biên dịch với tùy chọn giữ tên parameter trong bytecode, ví dụ javac -parameters. Tuy nhiên, hành vi và yêu cầu cụ thể phụ thuộc phiên bản Spring Data và cách build.

Cách tường minh, dễ đọc:

~~~java
List<PurchaseOrder> findByStatusAndCreatedAtAfter(
        OrderStatus status,
        Instant createdAt);
~~~

Với derived query, tên parameter thường được suy ra theo thứ tự method predicate; @Param không cần thiết để định nghĩa điều kiện derived query.

Với @Query có named parameter, nên dùng @Param cho từng giá trị để tránh lỗi khi đổi tên tham số, cấu hình compiler hoặc di chuyển phiên bản.

## 15. Parameter không thể thay tên entity, property hoặc keyword

Bind parameter chỉ thay giá trị, không thay identifier hoặc cấu trúc JPQL.

Không làm như sau:

~~~java
@Query("select o from PurchaseOrder o order by :field")
List<PurchaseOrder> sortBy(
        @Param("field") String field);
~~~

:field là một giá trị parameter, không phải tên property dùng để sắp xếp.

Nếu cần sort động, nhận Sort/Pageable hoặc xây dựng query có whitelist property. Với repository method có @Query, Spring Data có thể áp dụng Sort động trong các trường hợp được hỗ trợ; property vẫn cần hợp lệ và không được lấy raw expression tùy ý từ client.

Không nối trực tiếp input vào ORDER BY:

~~~java
String jpql = "select o from PurchaseOrder o order by " + requestSort;
~~~

Thay vào đó, ánh xạ tên được phép:

~~~java
Map<String, String> allowedSorts = Map.of(
        "createdAt", "o.createdAt",
        "totalAmount", "o.totalAmount",
        "status", "o.status",
        "id", "o.id"
);
~~~

Chỉ ghép expression đã được tra trong whitelist; direction phải lấy từ enum hoặc giá trị ASC/DESC đã validate.

## 16. Parameter type phải tương thích với property

Tên parameter đúng vẫn có thể lỗi nếu kiểu dữ liệu không phù hợp.

Ví dụ entity:

~~~java
@Enumerated(EnumType.STRING)
private OrderStatus status;

private Instant createdAt;

private BigDecimal totalAmount;
~~~

Các method đúng kiểu:

~~~java
List<PurchaseOrder> findByStatus(OrderStatus status);

List<PurchaseOrder> findByCreatedAtAfter(Instant instant);

List<PurchaseOrder> findByTotalAmountGreaterThan(BigDecimal amount);
~~~

Các lỗi thường gặp:

- Truyền String tùy ý vào query JPQL đang so sánh với enum.
- Truyền LocalDate khi property là Instant mà không chuyển timezone/mốc thời gian rõ ràng.
- Truyền Integer cho property BigDecimal.
- Truyền một entity object khi query cần ID scalar hoặc ngược lại.
- Truyền collection có phần tử sai kiểu cho predicate IN.

Hãy dùng đúng kiểu domain trong method signature. Nếu API nhận String, chuyển đổi/validate sang enum, Instant hoặc BigDecimal ở service boundary trước khi gọi repository.

## 17. IN parameter và collection rỗng

JPQL có thể dùng collection parameter:

~~~java
@Query("""
       select o
       from PurchaseOrder o
       where o.status in :statuses
       """)
List<PurchaseOrder> findByStatuses(
        @Param("statuses") Collection<OrderStatus> statuses);
~~~

Collection phải chứa giá trị đúng kiểu. Trường hợp collection rỗng cần được xử lý rõ ràng ở service vì SQL/JPQL provider có thể xử lý danh sách bind rỗng khác nhau; một số hệ quản trị không chấp nhận IN ().

Ví dụ:

~~~java
public List<PurchaseOrder> findByStatusesSafe(
        Collection<OrderStatus> statuses) {
    if (statuses == null || statuses.isEmpty()) {
        return List.of();
    }
    return repository.findByStatuses(statuses);
}
~~~

Đoạn này là method service minh họa, giả sử repository có findByStatuses. Nếu nghiệp vụ quy định danh sách rỗng nghĩa là "không lọc", trả tất cả kết quả là hành vi khác; hãy quyết định rõ và kiểm thử.

Không âm thầm đổi collection null/rỗng thành query không có filter nếu điều đó có thể trả nhiều dữ liệu ngoài dự định.

## 18. Null parameter và điều kiện tùy chọn

Biểu thức:

~~~jpql
where o.status = :status
~~~

không có nghĩa "bỏ qua filter nếu status null". So sánh với null theo SQL/JPQL không trả true như phép bằng thông thường.

Nếu muốn filter tùy chọn:

~~~java
@Query("""
       select o
       from PurchaseOrder o
       where (:status is null or o.status = :status)
       """)
List<PurchaseOrder> searchByOptionalStatus(
        @Param("status") OrderStatus status);
~~~

Nếu status null, nhánh đầu đúng và predicate không giới hạn status. Nếu status có giá trị, query lọc theo status.

Tuy nhiên, biểu thức OR có thể ảnh hưởng khả năng dùng index và execution plan tùy database. Với nhiều filter tùy chọn, Specification/Criteria hoặc JPQL động có thể tạo query chỉ gồm predicate cần thiết.

Nếu nghiệp vụ cần tìm property IS NULL, hãy viết rõ:

~~~java
@Query("""
       select o
       from PurchaseOrder o
       where o.customerEmail is null
       """)
List<PurchaseOrder> findWithoutCustomerEmail();
~~~

Phân biệt rõ null nghĩa là không có tiêu chí với null nghĩa là tìm cột có giá trị null.

## 19. LIKE parameter và wildcard

JPQL LIKE nhận pattern. Dùng named parameter:

~~~java
@Query("""
       select o
       from PurchaseOrder o
       where lower(o.customerEmail) like lower(:pattern)
       """)
List<PurchaseOrder> findByEmailPattern(
        @Param("pattern") String pattern);
~~~

Gọi với %example.com% để tìm chuỗi con. Nếu dùng derived query Containing, Spring Data sẽ xử lý việc thêm wildcard theo semantics của keyword.

Hai ký tự có ý nghĩa đặc biệt:

- %: khớp không hoặc nhiều ký tự.
- _: khớp đúng một ký tự.

Nếu người dùng muốn tìm chính ký tự % hoặc _, phải escape theo ký tự escape được khai báo trong JPQL/provider. Bind parameter chống injection nhưng không tự biến wildcard thành literal.

Khi query dùng IgnoreCase hoặc lower(), kiểm tra collation/locale và index. Không giả định ignore case cũng loại bỏ dấu tiếng Việt.

## 20. Pageable và Sort là tham số đặc biệt

Pageable và Sort không phải bind parameter thông thường trong JPQL. Spring Data xử lý chúng để áp dụng pagination/sorting.

Ví dụ:

~~~java
@Query("""
       select o
       from PurchaseOrder o
       where o.status = :status
       """)
Page<PurchaseOrder> findPageByStatus(
        @Param("status") OrderStatus status,
        Pageable pageable);
~~~

Chỉ status được bind vào :status. Pageable là tham số đặc biệt, không cần @Param("pageable").

Nếu method khai báo:

~~~java
Page<PurchaseOrder> findPageByStatus(
        @Param("status") OrderStatus status,
        @Param("pageable") Pageable pageable);
~~~

thì không nên coi pageable là một JPQL placeholder. Không khai báo :pageable trong query để mong JPA tự áp dụng offset/limit.

Sort property phải hợp lệ theo entity model và nên được giới hạn ở các trường được phép. Khi phân trang, thêm khóa duy nhất làm tie-breaker để có thứ tự ổn định.

## 21. Page và countQuery không khớp

Page<T> cần content và tổng số phần tử. Với query phức tạp, có thể khai báo countQuery riêng:

~~~java
@Query(
    value = """
            select o
            from PurchaseOrder o
            where o.status = :status
              and o.createdAt >= :from
            order by o.createdAt desc, o.id desc
            """,
    countQuery = """
            select count(o)
            from PurchaseOrder o
            where o.status = :status
              and o.createdAt >= :from
            """
)
Page<PurchaseOrder> findPage(
        @Param("status") OrderStatus status,
        @Param("from") Instant from,
        Pageable pageable);
~~~

Count query phải giữ cùng predicate lọc, nhưng không cần ORDER BY hoặc fetch association.

Nếu content query có status và from nhưng count query chỉ có status, totalElements sẽ sai. Nếu query join collection, count(o) có thể đếm dòng join; dùng EXISTS hoặc count(distinct o.id) tùy cấu trúc.

Một countQuery sai có thể không tạo QueryCreationException. Nó có thể chạy thành công nhưng trả tổng số sai. Vì vậy, cần test cả content và totalElements.

## 22. DTO constructor expression không khớp

JPQL có thể trả DTO bằng constructor expression:

~~~java
package com.example.orders;

import java.math.BigDecimal;

public record OrderSummary(
        Long id,
        String customerEmail,
        BigDecimal totalAmount
) {
}
~~~

Repository query:

~~~java
@Query("""
       select new com.example.orders.OrderSummary(
           o.id,
           o.customerEmail,
           o.totalAmount
       )
       from PurchaseOrder o
       where o.id = :id
       """)
Optional<OrderSummary> findSummaryById(
        @Param("id") Long id);
~~~

JPQL phải dùng fully qualified class name trong constructor expression. Thứ tự và kiểu các biểu thức phải khớp constructor DTO.

Lỗi thường gặp:

- Gõ sai package/class DTO.
- DTO không có constructor tương ứng.
- Đảo thứ tự trường.
- Dùng kiểu không tương thích, ví dụ constructor nhận Integer nhưng query trả Long.
- Dùng alias hoặc cú pháp constructor expression không đúng.

Nếu dùng record, canonical constructor có đúng thứ tự các component. Khi thay đổi DTO, cập nhật query và test cùng lúc.

## 23. Lỗi kiểu trả về và cardinality

Query có thể được tạo thành công nhưng lỗi khi thực thi vì kết quả không phù hợp kiểu trả về.

Ví dụ:

~~~java
Optional<PurchaseOrder> findByCustomerEmail(String email);
~~~

Nếu nhiều đơn hàng có cùng email, query có thể trả nhiều dòng và provider/Spring Data báo lỗi kết quả không duy nhất. Đây không nhất thiết là QueryCreationException.

Chọn kiểu trả về theo cardinality:

| Kiểu trả về | Kỳ vọng |
|---|---|
| PurchaseOrder | Một kết quả; tùy API có thể trả null khi không có |
| Optional<PurchaseOrder> | Không có hoặc một kết quả |
| List<PurchaseOrder> | Không hoặc nhiều kết quả |
| Page<PurchaseOrder> | Nhiều kết quả phân trang và tổng số |
| Slice<PurchaseOrder> | Một phần kết quả và thông tin còn trang |
| long | Số lượng |
| boolean | Kiểm tra tồn tại khi method/query được thiết kế cho exists |

Nếu cần một kết quả gần nhất, dùng findFirstBy...OrderBy... hoặc Pageable giới hạn 1 thay vì Optional trên điều kiện không duy nhất.

## 24. @Modifying cho UPDATE và DELETE query

@Query mặc định dùng cho truy vấn đọc. Nếu khai báo bulk UPDATE/DELETE, cần @Modifying:

~~~java
@Modifying(clearAutomatically = true, flushAutomatically = true)
@Transactional
@Query("""
       update PurchaseOrder o
       set o.status = :status
       where o.id = :id
       """)
int updateStatus(
        @Param("id") Long id,
        @Param("status") OrderStatus status);
~~~

Nếu thiếu @Modifying, Spring Data có thể cố xử lý query update như truy vấn select và báo lỗi khi thực thi.

Các điểm cần nhớ:

- Bulk update/delete không đi qua dirty checking từng entity.
- Persistence context có thể còn entity cũ sau bulk update.
- clearAutomatically có thể clear persistence context sau khi query chạy.
- flushAutomatically yêu cầu flush thay đổi đang chờ trước bulk operation.
- Transaction phải được quản lý phù hợp; ví dụ đặt @Transactional trên method.
- Kiểu trả về thường là số dòng bị ảnh hưởng hoặc void, không phải List<PurchaseOrder>.

Không dùng @Modifying trên SELECT query. Nếu cần thay đổi nhiều entity và cần lifecycle callback/cascade, cân nhắc load entity rồi cập nhật từng object hoặc thiết kế nghiệp vụ phù hợp.

## 25. JPQL và native SQL: xác định đúng ngôn ngữ

Một lỗi phổ biến là viết SQL nhưng quên nativeQuery = true.

JPQL:

~~~java
@Query("""
       select o
       from PurchaseOrder o
       where o.status = :status
       """)
List<PurchaseOrder> findByStatusJpql(
        @Param("status") OrderStatus status);
~~~

Native SQL:

~~~java
@Query(
    value = """
            select *
            from purchase_orders
            where status = :status
            """,
    nativeQuery = true
)
List<PurchaseOrder> findByStatusNative(
        @Param("status") String status);
~~~

Trong JPQL:
- Dùng entity name và property name.
- Enum parameter có thể truyền bằng enum type.
- Association và constructor expression theo entity model.

Trong native SQL:
- Dùng bảng/cột vật lý.
- SQL phải tương thích database.
- Enum, timestamp, pagination và result mapping có thể phụ thuộc provider/database.
- Một số tính năng sort động hoặc count derivation có giới hạn hơn JPQL.

Khi thấy lỗi kiểu "unexpected token", "table not mapped" hoặc "could not resolve attribute", xác nhận query đang được hiểu là JPQL hay native SQL trước khi sửa.

## 26. Named query và thứ tự phân giải query

JPA cho phép khai báo @NamedQuery trên entity hoặc XML. Spring Data có thể tìm named query theo quy ước tên gồm entity simple name và repository method name.

Ví dụ minh họa:

~~~java
@NamedQuery(
    name = "PurchaseOrder.findByStatus",
    query = "select o from PurchaseOrder o where o.status = :status"
)
@Entity
public class PurchaseOrder {
    // Entity mapping
}
~~~

Nếu repository method tương ứng có declared @Query, query khai báo trên method thường được dùng theo quy tắc query lookup của Spring Data. Nếu không, Spring Data có thể tìm named query hoặc tạo derived query tùy lookup strategy.

Khi sửa @Query mà kết quả không đổi như dự kiến, kiểm tra xem method đang dùng declared query, named query hay derived query. Không giả định tên method luôn là nguồn query duy nhất.

## 27. Đọc stack trace để tìm nguyên nhân gốc

Một quy trình đọc stack trace:

1. Tìm exception đầu tiên ở tầng Spring Data, thường là QueryCreationException hoặc InvalidDataAccessApiUsageException.
2. Đi xuống các khối Caused by.
3. Tìm message cụ thể nhất: property không tồn tại, parameter không bind được, syntax error, type mismatch hoặc SQL error.
4. Xác định lỗi xuất hiện khi repository được tạo hay khi method thực thi.
5. Đối chiếu message với method signature, @Query và entity mapping.
6. Sửa một nguyên nhân gốc rồi chạy lại test hẹp nhất.

Một số message thường gặp:

| Message/dấu hiệu | Hướng điều tra |
|---|---|
| No property ... found for type ... | Derived method dùng sai property path |
| Could not resolve attribute ... | JPQL/Criteria tham chiếu property không có trong entity |
| Could not resolve entity ... | Entity name hoặc persistence unit mapping sai |
| Named parameter not bound | Query có placeholder chưa được bind |
| Could not locate named parameter | @Param/placeholder không khớp |
| Parameter value did not match expected type | Kiểu tham số không phù hợp property |
| Validation failed for query | Kiểm tra query string và nested cause |
| Unexpected token / syntax error | JPQL hay native SQL sai cú pháp/dialect |
| NonUniqueResultException | Kiểu trả về đơn nhưng query có nhiều dòng |
| NoResultException | JPA Query.getSingleResult() không có dòng; Spring Data method trả Optional thường cho Optional.empty() |
| SQLGrammarException | SQL sinh ra không hợp lệ với dialect/schema |
| Query did not return a unique result | Điều kiện hoặc kiểu trả về không đảm bảo duy nhất |

Message cụ thể thay đổi theo Hibernate và Spring Data version. Hãy đọc nested cause, không chỉ tìm đúng chuỗi message trong một bài viết cũ.

## 28. Bật log để kiểm tra query

Trong môi trường phát triển/test, có thể bật SQL log:

~~~properties
spring.jpa.show-sql=true
spring.jpa.properties.hibernate.format_sql=true
logging.level.org.hibernate.SQL=DEBUG
~~~

Để xem parameter bind trên Hibernate 6:

~~~properties
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Với một số phiên bản Hibernate cũ, category log bind parameter có tên khác. Kiểm tra tài liệu phiên bản đang chạy.

Log giúp xác nhận:

- Query có được tạo và gửi tới database không.
- SQL có đúng bảng/cột không.
- Parameter có đúng giá trị và kiểu không.
- Pagination có áp dụng LIMIT/OFFSET phù hợp không.
- Count query có chạy không.
- Query có join ngoài dự kiến không.

Bind log có thể chứa email, dữ liệu khách hàng hoặc thông tin nhạy cảm. Chỉ bật ở môi trường kiểm soát và tắt sau khi chẩn đoán; tránh ghi parameter nhạy cảm vào production log.

## 29. Tạo repository hoàn chỉnh cho mô hình ví dụ

Interface sau tổng hợp các ví dụ chính. Đặt file PurchaseOrderRepository.java trong package com.example.orders:

~~~java
package com.example.orders;

import java.time.Instant;
import java.util.Collection;
import java.util.List;
import java.util.Optional;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.transaction.annotation.Transactional;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    List<PurchaseOrder> findByStatus(OrderStatus status);

    List<PurchaseOrder> findByStatusAndCreatedAtAfter(
            OrderStatus status,
            Instant createdAt);

    List<PurchaseOrder> findByCustomerEmailContainingIgnoreCase(
            String fragment);

    List<PurchaseOrder> findByStatusIn(
            Collection<OrderStatus> statuses);

    Optional<PurchaseOrder> findFirstByCustomerEmailOrderByCreatedAtDesc(
            String email);

    @Query("""
           select o
           from PurchaseOrder o
           where o.status = :status
             and o.createdAt >= :from
           """)
    Page<PurchaseOrder> findPage(
            @Param("status") OrderStatus status,
            @Param("from") Instant from,
            Pageable pageable);

    @Query("""
           select new com.example.orders.OrderSummary(
               o.id,
               o.customerEmail,
               o.totalAmount
           )
           from PurchaseOrder o
           where o.id = :id
           """)
    Optional<OrderSummary> findSummaryById(
            @Param("id") Long id);

    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Transactional
    @Query("""
           update PurchaseOrder o
           set o.status = :status
           where o.id = :id
           """)
    int updateStatus(
            @Param("id") Long id,
            @Param("status") OrderStatus status);
}
~~~

Các method trên dùng cùng entity và property đã khai báo. Page method có Pageable là tham số đặc biệt, không bind thành placeholder JPQL. DTO query dùng OrderSummary đã định nghĩa ở phần trước. Bulk update có @Modifying và @Transactional.

Trong dự án thật, có thể tách query đọc và query ghi theo service/use case. Interface tổng hợp này nhằm minh họa các dạng chữ ký trong cùng một repository, không bắt buộc mọi dự án phải gom tất cả method vào một file.

## 30. Kiểm thử repository với @DataJpaTest

Một test nhỏ có thể xác minh derived query, JPQL named parameter, Page/count và DTO constructor mapping.

~~~java
package com.example.orders;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;

@DataJpaTest
class PurchaseOrderRepositoryTest {

    @Autowired
    private PurchaseOrderRepository repository;

    @BeforeEach
    void setUp() {
        repository.saveAll(List.of(
                new PurchaseOrder(
                        "an@example.com",
                        OrderStatus.PAID,
                        new BigDecimal("100.00"),
                        Instant.parse("2026-01-03T10:00:00Z")),
                new PurchaseOrder(
                        "anna@example.com",
                        OrderStatus.PAID,
                        new BigDecimal("200.00"),
                        Instant.parse("2026-01-02T10:00:00Z")),
                new PurchaseOrder(
                        "binh@example.com",
                        OrderStatus.NEW,
                        new BigDecimal("50.00"),
                        Instant.parse("2026-01-01T10:00:00Z"))
        ));
    }

    @Test
    void derivedQueryFindsOrdersByStatus() {
        List<PurchaseOrder> result =
                repository.findByStatus(OrderStatus.PAID);

        assertThat(result).hasSize(2);
    }

    @Test
    void jpqlNamedParametersAndCountMatch() {
        Page<PurchaseOrder> page = repository.findPage(
                OrderStatus.PAID,
                Instant.parse("2026-01-01T00:00:00Z"),
                PageRequest.of(0, 1));

        assertThat(page.getContent()).hasSize(1);
        assertThat(page.getTotalElements()).isEqualTo(2);
        assertThat(page.getTotalPages()).isEqualTo(2);
    }

    @Test
    void dtoConstructorExpressionMapsExpectedFields() {
        PurchaseOrder order = repository.findByStatus(OrderStatus.NEW)
                .get(0);

        OrderSummary summary = repository.findSummaryById(order.getId())
                .orElseThrow();

        assertThat(summary.customerEmail()).isEqualTo("binh@example.com");
        assertThat(summary.totalAmount())
                .isEqualByComparingTo("50.00");
    }
}
~~~

Imports đầy đủ cho test nằm ở đầu file. Test giả định Spring Boot test slice có cấu hình JPA và database test phù hợp. @DataJpaTest thường chạy trong transaction và rollback sau mỗi test.

Nếu method query lỗi ngay lúc khởi tạo repository, test slice thường phát hiện sớm. Nếu lỗi chỉ xuất hiện với parameter cụ thể, thêm test cho null, collection rỗng, enum, thời gian biên và từng nhánh query.

Để kiểm tra lỗi JPQL, đừng chỉ mock repository. Cần để JPA provider thực sự khởi tạo và xác thực query trong test.

## 31. Quy trình chẩn đoán từng bước

Khi gặp QueryCreationException hoặc query error, làm theo thứ tự:

1. **Xác định nguồn query.** Derived method, @Query, named query, native query hay custom EntityManager?
2. **Đọc root cause.** Tìm PropertyReferenceException, parser error, parameter error, type mismatch hay SQL exception.
3. **Đối chiếu entity mapping.** Entity name, property name, association path và kiểu Java.
4. **Đối chiếu method signature.** Số tham số, tên @Param, kiểu parameter, Pageable/Sort đặc biệt và kiểu trả về.
5. **Kiểm tra ngôn ngữ query.** JPQL dùng entity/property; native SQL dùng bảng/cột.
6. **Kiểm tra cardinality.** Optional/entity có thể chỉ nhận tối đa một dòng; Page cần count đúng.
7. **Chạy repository test.** Tái hiện lỗi với dữ liệu nhỏ, xác định.
8. **Bật SQL/bind log khi cần.** Kiểm tra câu SQL thực tế và giá trị bind.
9. **Chạy lại test liên quan sau khi sửa.** Không thay nhiều phần cùng lúc nếu chưa biết nguyên nhân.
10. **Tắt log bind nhạy cảm.** Không để trace parameter ở production ngoài nhu cầu có kiểm soát.

Sửa đúng nguyên nhân gốc sẽ tốt hơn việc đổi tên method hoặc thêm annotation một cách thử-sai.

## 32. Những lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Repository không khởi động | Derived property sai | Kiểm tra entity property/path |
| QueryCreationException với validation failed | JPQL sai entity/property/alias | Kiểm tra JPQL theo entity model |
| Named parameter không được bind | :name và @Param khác nhau | Đồng nhất tên |
| Query thiếu parameter | Placeholder nhiều hơn bindable args | Bổ sung method parameter |
| Method có parameter thừa | Không có placeholder tương ứng | Xóa parameter hoặc dùng đúng query |
| Positional query trả nhầm filter | ?1/?2 lệch thứ tự method | Đối chiếu index |
| Type mismatch | String/enum/date/number không tương thích | Dùng đúng kiểu domain và chuyển đổi ở service |
| IN rỗng gây SQL lỗi | Provider/database không xử lý IN () | Guard collection trước khi gọi repository |
| JPQL báo không tìm thấy bảng | Dùng SQL table name trong JPQL | Dùng entity name hoặc nativeQuery |
| JPQL báo không tìm thấy attribute | Dùng tên cột thay property | Dùng Java property |
| Optional query báo nhiều kết quả | Điều kiện không duy nhất | Dùng List hoặc giới hạn một kết quả |
| Page totalElements sai | countQuery thiếu predicate hoặc đếm join row | Đồng bộ filter, EXISTS/count distinct |
| DTO query lỗi constructor | FQCN/thứ tự/kiểu constructor sai | Đồng bộ record/constructor với SELECT |
| UPDATE query báo lỗi select | Thiếu @Modifying | Thêm @Modifying và transaction |
| Sort động gây lỗi | Property không hợp lệ hoặc raw expression | Whitelist sort field |
| Lỗi chỉ xuất hiện ở một input | Null, blank, wildcard hoặc collection rỗng | Test các giá trị biên |
| Query chỉ lỗi trên production DB | Dialect/native SQL/collation khác | Test trên database cùng loại |
| SQL bind log không thấy | Chưa bật đúng category/version | Kiểm tra logger của Hibernate version |

## 33. Checklist trước khi hoàn tất một repository query

- [ ] Xác định method dùng derived query, JPQL, native SQL hay custom EntityManager.
- [ ] Kiểm tra entity name và tên property Java.
- [ ] Kiểm tra association path và dùng underscore khi cần phân định nested path.
- [ ] Kiểm tra keyword derived query tương thích với property type.
- [ ] Đồng nhất placeholder named parameter và @Param.
- [ ] Đếm đủ parameter và kiểm tra thứ tự positional parameter.
- [ ] Không trộn named và positional parameter.
- [ ] Dùng đúng kiểu enum, date/time, number và collection.
- [ ] Xử lý null, blank và collection rỗng theo hợp đồng nghiệp vụ.
- [ ] Không bind parameter để thay identifier hoặc ORDER BY field.
- [ ] Whitelist sort property và hướng sắp xếp.
- [ ] Kiểm tra Page/countQuery cùng predicate.
- [ ] Kiểm tra DTO constructor expression và kiểu trả về.
- [ ] Dùng @Modifying cho bulk UPDATE/DELETE.
- [ ] Kiểm tra transaction và persistence context sau bulk query.
- [ ] Viết @DataJpaTest để provider thực sự tạo/thực thi query.
- [ ] Đọc root cause và SQL/bind log khi lỗi khó xác định.
- [ ] Tắt log bind parameter nhạy cảm sau khi chẩn đoán.

## 34. Kết luận

QueryCreationException là dấu hiệu Spring Data không thể tạo query cho một repository method, nhưng nguyên nhân thật có thể là property path sai, JPQL không hợp lệ, parameter không khớp hoặc kiểu dữ liệu không tương thích. Một số lỗi khác chỉ xuất hiện khi query chạy, ví dụ cardinality không đúng, SQL dialect sai hoặc count query đếm nhầm.

Hãy bắt đầu từ root cause trong stack trace, đối chiếu entity mapping với query và method signature, rồi xác nhận bằng repository test. Trong JPQL, dùng entity/property Java; với named parameter, giữ tên placeholder và @Param đồng nhất; với positional parameter, giữ đúng thứ tự. Xử lý riêng Pageable, collection rỗng, null, DTO constructor và modifying query. Khi cần, bật SQL/bind log trong môi trường kiểm soát để xác minh truy vấn thực tế.
