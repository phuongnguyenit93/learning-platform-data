# Alias cột, tên tham số và kiểu dữ liệu trên projection

Trong **Spring Data Relational JDBC**, projection cho phép một truy vấn trả về hình dạng dữ liệu phù hợp với use case thay vì luôn dựng toàn bộ aggregate root. Một màn hình danh sách có thể chỉ cần mã đơn, tên khách hàng và tổng tiền; một báo cáo có thể cần số lượng đơn theo trạng thái. Projection giúp biểu diễn những kết quả này bằng interface, DTO hoặc record.

Để projection hoạt động chính xác, hợp đồng giữa SQL và Java phải rõ ràng. **Tên cột trong result set, tên thuộc tính hoặc constructor parameter, tên tham số đầu vào và kiểu dữ liệu phải khớp với nhau theo quy tắc mapping của Spring Data JDBC và JDBC driver.** Một truy vấn chạy được ở database vẫn có thể lỗi khi framework ánh xạ kết quả nếu alias không đúng, constructor không phù hợp hoặc kiểu Java không nhận được giá trị SQL.

Bài học tập trung vào ba phần liên quan trực tiếp đến projection:

- **Alias cột:** đặt tên cột kết quả để ánh xạ rõ ràng sang thuộc tính projection.
- **Tên tham số:** liên kết placeholder trong SQL với tham số của repository method.
- **Kiểu dữ liệu:** bảo đảm kiểu SQL, kiểu JDBC và kiểu Java tương thích, kể cả trường hợp null, phép tính và giá trị aggregate.

## 1. Projection là gì?

Một entity thường mô tả trạng thái của aggregate được lưu. Projection mô tả **một góc nhìn dữ liệu** cần cho một truy vấn cụ thể.

Ví dụ entity đơn hàng:

~~~java
@Table("purchase_order")
public record PurchaseOrder(
        @Id Long id,
        String orderNumber,
        String status,
        Long customerId,
        BigDecimal totalAmount,
        LocalDateTime createdAt
) {
}
~~~

Một màn hình danh sách chỉ cần:

~~~java
public record OrderListItem(
        Long orderId,
        String orderNumber,
        String customerName,
        BigDecimal totalAmount
) {
}
~~~

Truy vấn có thể join bảng đơn hàng với bảng khách hàng và trả về OrderListItem. Kết quả này không phải aggregate PurchaseOrder đầy đủ; nó là một cấu trúc đọc kết hợp dữ liệu từ nhiều bảng.

### 1.1. Vì sao không luôn trả về entity?

Nếu màn hình chỉ cần bốn trường, tải toàn bộ aggregate có thể gây lãng phí:

- Có thể đọc thêm những cột không được hiển thị.
- Aggregate có thể chứa collection child cần truy vấn và materialize.
- Query join cho báo cáo có thể trả kết quả không tương ứng với một entity duy nhất.
- Entity persistence có thể để lộ chi tiết mô hình ghi sang API đọc.

Projection giúp chọn đúng dữ liệu cho use case. Nó đặc biệt hữu ích cho danh sách, báo cáo, dashboard, tìm kiếm và truy vấn tổng hợp.

### 1.2. Projection không phải aggregate để cập nhật

Projection thường chỉ chứa một phần dữ liệu và có thể kết hợp nhiều bảng. Không nên lấy một projection mỏng rồi dùng nó như thể là aggregate đầy đủ để gọi hành vi miền hoặc lưu lại qua repository root.

Khi cần thay đổi nghiệp vụ:

1. Đọc aggregate root bằng repository.
2. Gọi hành vi miền trên root.
3. Lưu aggregate qua repository.

Khi chỉ cần đọc:

1. Viết query lấy đúng cột.
2. Ánh xạ vào projection/DTO.
3. Trả kết quả cho caller.

## 2. Ba dạng projection thường gặp

Spring Data hỗ trợ projection theo nhiều hình thức. Chi tiết cụ thể có thể phụ thuộc module và phiên bản Spring Data JDBC đang dùng; luôn xác minh contract của release trong dự án.

### 2.1. Interface-based projection

Interface mô tả những accessor mà caller cần:

~~~java
public interface CustomerSummary {
    Long getId();
    String getName();
    String getCity();
}
~~~

Repository có thể khai báo method trả projection:

~~~java
List<CustomerSummary> findByActiveTrue();
~~~

Spring Data tạo implementation/proxy phù hợp để cung cấp các giá trị từ kết quả truy vấn. Với closed projection, interface chỉ khai báo các property có thể xác định trước. Điều này giúp framework biết những thuộc tính mà caller cần trong những kiểu query được module hỗ trợ tối ưu.

Accessor JavaBean thường dùng dạng getName(). Nếu dùng record hoặc DTO class, accessor có thể là name(); đó là hai kiểu API khác nhau.

### 2.2. Class-based projection (DTO)

DTO class biểu diễn dữ liệu trả về bằng constructor:

~~~java
public class CustomerSummary {
    private final Long id;
    private final String name;
    private final String city;

    public CustomerSummary(Long id, String name, String city) {
        this.id = id;
        this.name = name;
        this.city = city;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getCity() {
        return city;
    }
}
~~~

Class-based projection không cần proxy interface. Spring Data phải biết cách tạo DTO và ánh xạ các giá trị truy vấn vào constructor/property tương ứng.

Nếu DTO có nhiều constructor, cần làm rõ constructor persistence được chọn theo quy tắc của Spring Data, có thể dùng @PersistenceCreator khi phù hợp. Tên tham số constructor và metadata biên dịch cũng có thể ảnh hưởng việc ánh xạ.

### 2.3. Record projection

Java record rất phù hợp cho DTO đọc vì component và constructor được khai báo ngắn gọn:

~~~java
public record CustomerSummary(
        Long id,
        String name,
        String city
) {
}
~~~

Record cung cấp canonical constructor và accessor theo tên component:

~~~java
CustomerSummary summary = ...;
summary.name();
summary.city();
~~~

Record phù hợp khi dữ liệu projection được xem là giá trị bất biến. Tuy nhiên, record không tự giải quyết vấn đề alias hoặc chuyển đổi kiểu; các cột kết quả vẫn phải ánh xạ được vào component.

## 3. Alias cột: nối tên SQL với tên property Java

Khi truy vấn có biểu thức, join hoặc tên cột khác với property Java, hãy dùng alias để đặt tên rõ ràng cho từng cột kết quả.

Ví dụ:

~~~sql
SELECT
    po.id AS order_id,
    po.order_number AS order_number,
    c.name AS customer_name,
    po.total_amount AS total_amount
FROM purchase_order po
JOIN customer c ON c.id = po.customer_id
WHERE po.status = :status;
~~~

Projection:

~~~java
public record OrderListItem(
        Long orderId,
        String orderNumber,
        String customerName,
        BigDecimal totalAmount
) {
}
~~~

Với naming strategy mặc định phổ biến của Spring Data Relational, tên property Java dạng camelCase thường tương ứng với tên cột dạng snake_case. Vì vậy alias order_id, order_number, customer_name và total_amount thể hiện tên cột kết quả phù hợp với các property trên. Nếu ứng dụng dùng naming strategy khác hoặc mapping tùy chỉnh, alias phải theo tên cột mà mapping metadata mong đợi.

### 3.1. Vì sao alias quan trọng?

Một query join có thể có nhiều cột cùng tên:

~~~sql
SELECT
    po.id,
    c.id,
    po.status,
    c.name
FROM purchase_order po
JOIN customer c ON c.id = po.customer_id;
~~~

Result set có hai cột cùng nhãn id. Điều đó gây mơ hồ khi ánh xạ vào DTO có cả orderId và customerId. Hãy alias:

~~~sql
SELECT
    po.id AS order_id,
    c.id AS customer_id,
    po.status AS order_status,
    c.name AS customer_name
FROM purchase_order po
JOIN customer c ON c.id = po.customer_id;
~~~

DTO:

~~~java
public record OrderCustomerView(
        Long orderId,
        Long customerId,
        String orderStatus,
        String customerName
) {
}
~~~

Alias làm rõ nguồn và ý nghĩa của từng giá trị, đồng thời giảm nguy cơ driver trả về label trùng nhau hoặc bị ghi đè trong quá trình mapping.

### 3.2. Alias cho biểu thức tính toán

Một cột tính toán không có tên property tự nhiên:

~~~sql
SELECT
    id AS product_id,
    price_minor_units * stock_quantity AS inventory_value_minor_units
FROM product;
~~~

Projection:

~~~java
public record InventoryValue(
        Long productId,
        Long inventoryValueMinorUnits
) {
}
~~~

Biểu thức phải có alias phù hợp với mapping property. Không dựa vào tên biểu thức do database tự sinh, vì nhãn đó khó ánh xạ và có thể khác giữa driver.

### 3.3. Alias cho aggregate function

~~~sql
SELECT
    status AS order_status,
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_revenue
FROM purchase_order
GROUP BY status;
~~~

Projection:

~~~java
public record OrderStatistics(
        String orderStatus,
        Long orderCount,
        BigDecimal totalRevenue
) {
}
~~~

Các alias order_status, order_count và total_revenue mô tả tên cột kết quả. Kiểu Java cần phù hợp với kiểu mà database/driver trả về cho COUNT và SUM; không giả định mọi database đều trả cùng kiểu cho một biểu thức aggregate.

### 3.4. Quy tắc đặt alias dễ bảo trì

- Dùng alias ổn định, có ý nghĩa nghiệp vụ.
- Tránh hai cột kết quả cùng alias.
- Dùng chữ thường và snake_case nhất quán nếu đó là naming strategy của dự án.
- Alias mọi biểu thức, function và cột có thể trùng tên trong join.
- Không dùng tên alias là từ khóa SQL hoặc tên khó xử lý do khoảng trắng/ký tự đặc biệt.
- Chọn cột kết quả đúng với projection; tránh SELECT *.
- Khi schema đổi, kiểm tra lại alias và mapping DTO.

## 4. Alias có phải luôn giống tên component Java?

Không nhất thiết. Cần phân biệt:

- **Tên property/component Java:** ví dụ customerName.
- **Tên cột trong schema:** ví dụ customer_name.
- **Tên label trong result set:** tên được SQL trả về sau alias.

Spring Data Relational sử dụng mapping metadata và naming strategy để liên hệ property với cột. Với naming strategy snake_case mặc định, property customerName thường được ánh xạ tới cột customer_name. Vì vậy alias theo tên cột được ánh xạ thường là lựa chọn rõ ràng:

~~~sql
SELECT c.name AS customer_name
~~~

Nếu property được đánh dấu bằng mapping tùy chỉnh hoặc ứng dụng dùng naming strategy riêng, phải theo đúng tên cột đã cấu hình. Không nên suy luận chỉ từ tên getter.

### 4.1. Dùng @Column khi tên cột khác quy ước

Với entity, @Column cho phép chỉ định tên cột rõ ràng:

~~~java
@Column("display_label")
private String displayLabel;
~~~

Nếu một projection DTO có mapping metadata tương ứng được Spring Data hỗ trợ, alias phải khớp tên cột được khai báo. Với projection class/record đơn giản, cách an toàn là giữ tên alias theo quy ước mapping và xác nhận bằng integration test của đúng phiên bản.

Không thêm @Column vào DTO một cách máy móc rồi giả định mọi loại projection đều xử lý annotation giống entity. Khả năng đọc annotation và cách chọn constructor phụ thuộc kiểu projection và mapping path cụ thể.

### 4.2. Chú ý chữ hoa/chữ thường và dấu nháy

Một số database tự chuyển identifier không đặt trong dấu nháy thành chữ thường hoặc chữ hoa. Driver có thể trả column label theo cách viết đã chuẩn hóa. Để giảm khác biệt:

- Ưu tiên alias đơn giản như customer_name.
- Tránh alias có khoảng trắng.
- Tránh phụ thuộc vào chữ hoa/chữ thường nếu không thật sự cần.
- Nếu phải quote alias, kiểm tra đúng quy tắc quote của database mục tiêu.

Ví dụ:

~~~sql
SELECT c.name AS customer_name
~~~

thường dễ portable hơn alias có khoảng trắng như AS "Customer Name".

## 5. Projection với @Query

Khi dùng SQL tường minh, người viết kiểm soát chính xác danh sách cột và alias:

~~~java
import java.util.List;
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface OrderReadRepository {

    @Query("""
           SELECT
               po.id AS order_id,
               po.order_number AS order_number,
               c.name AS customer_name,
               po.total_amount AS total_amount
           FROM purchase_order po
           JOIN customer c ON c.id = po.customer_id
           WHERE po.status = :status
           ORDER BY po.id DESC
           """)
    List<OrderListItem> findOrderItems(
            @Param("status") String status
    );
}
~~~

OrderListItem là record projection ở mục trước. Trong ứng dụng thật, interface repository có thể kế thừa repository root hoặc được tổ chức thành fragment tùy kiến trúc. Ví dụ tập trung vào hợp đồng SQL/result mapping.

Với @Query:

- SQL phải dùng tên bảng và cột của database.
- Alias phải tương thích với property/component của projection.
- Các kiểu cột phải chuyển đổi được sang kiểu Java.
- Result set phải có đủ dữ liệu để dựng projection.
- Cardinality phải khớp kiểu trả về: List cho nhiều dòng, Optional cho tối đa một dòng.

### 5.1. SQL quyết định những cột được chọn

Với query viết tường minh, không nên giả định Spring Data tự sửa danh sách cột để phù hợp với projection. Hãy chọn đúng cột trong SELECT. Nếu projection có bốn component nhưng SQL chỉ trả ba cột, constructor mapping có thể thất bại hoặc thiếu dữ liệu tùy đường mapping.

### 5.2. Projection không tự tạo join

Khai báo DTO có component customerName không tự khiến Spring Data JDBC join bảng customer. SQL phải có join và chọn cột tương ứng. Projection mô tả hình dạng kết quả; SQL mô tả cách lấy dữ liệu.

## 6. Tên tham số method và named parameter trong SQL

Tên tham số đầu vào là một hợp đồng khác với alias cột. Placeholder SQL nhận giá trị từ tham số Java qua cơ chế bind.

Ví dụ:

~~~java
@Query("""
       SELECT id, sku, name, price_minor_units
       FROM product
       WHERE status = :status
         AND price_minor_units >= :minimumPrice
       """)
List<ProductSummary> search(
        @Param("status") String productStatus,
        @Param("minimumPrice") long minPrice
);
~~~

Liên kết:

| Placeholder SQL | Tham số Java | Vai trò |
| --- | --- | --- |
| :status | @Param("status") String productStatus | Giá trị lọc trạng thái |
| :minimumPrice | @Param("minimumPrice") long minPrice | Ngưỡng giá tối thiểu |

Tên biến Java productStatus không cần giống status vì @Param("status") chỉ định tên liên kết. Điều quan trọng là chuỗi trong @Param phải khớp chính xác placeholder trong SQL.

### 6.1. Vì sao nên khai báo @Param tường minh?

Không có @Param, framework có thể phải dựa vào metadata tên tham số được lưu khi biên dịch. Điều này phụ thuộc cấu hình compiler, ví dụ cờ -parameters.

Với Gradle:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += "-parameters"
}
~~~

Khai báo @Param giúp method thể hiện rõ hợp đồng và giảm phụ thuộc vào metadata. Đặc biệt hữu ích khi:

- Tên biến Java khác tên placeholder.
- Query có nhiều tham số.
- Method được refactor tên biến.
- Project có nhiều module hoặc cấu hình biên dịch khác nhau.

### 6.2. Phân biệt ba loại tên

~~~text
SQL column alias         Java projection property
-----------------        -----------------------
customer_name     -----> customerName
total_revenue     -----> totalRevenue

SQL named parameter      Java method parameter
-------------------      ---------------------
:status            <---- @Param("status") String productStatus
:minimumPrice      <---- @Param("minimumPrice") long minPrice
~~~

Alias mô tả **dữ liệu trả về**; named parameter mô tả **giá trị đầu vào**. Đừng dùng alias cột thay cho @Param hoặc nghĩ tên tham số Java quyết định tên cột trong result set.

### 6.3. Không bind tên bảng, cột hoặc ORDER BY

Bind parameter chỉ thay thế giá trị:

~~~sql
WHERE status = :status
~~~

Không thể dùng:

~~~sql
ORDER BY :sortColumn
~~~

với kỳ vọng sortColumn trở thành tên cột. Database sẽ hiểu placeholder là một giá trị, không phải identifier SQL.

Nếu cần sort động, dùng whitelist:

~~~java
String orderBy = switch (sort) {
    case NEWEST -> "created_at DESC, id DESC";
    case NAME -> "name ASC, id ASC";
    case PRICE -> "price_minor_units DESC, id DESC";
};
~~~

Chỉ nối chuỗi lấy từ tập hằng số do ứng dụng kiểm soát; không nối trực tiếp tên cột do request gửi lên.

### 6.4. Tham số collection và IN

Một truy vấn có thể lọc theo tập ID:

~~~java
@Query("""
       SELECT id, name, status
       FROM customer
       WHERE id IN (:ids)
       """)
List<CustomerSummary> findByIds(@Param("ids") Collection<Long> ids);
~~~

Khi bind collection, cơ chế named parameter của Spring JDBC có thể mở rộng danh sách placeholder theo số phần tử. Cần kiểm tra hành vi của phiên bản/framework đang dùng và quy định rõ trường hợp collection rỗng:

- Trả list rỗng ngay ở service nếu không có ID cần tìm.
- Hoặc chọn query khác phù hợp.
- Không để một danh sách rỗng tạo SQL không hợp lệ hoặc vô tình bỏ điều kiện lọc.

Kiểm tra phần tử null và giới hạn kích thước collection nếu input đến từ API.

## 7. Kiểu dữ liệu: SQL, JDBC và Java phải tương thích

Projection chỉ hoạt động ổn định khi kiểu dữ liệu cột/biểu thức có thể chuyển sang kiểu Java tương ứng. Có ba lớp cần xem xét:

1. **Kiểu SQL:** kiểu khai báo trong schema hoặc kiểu do biểu thức SQL tạo ra.
2. **Kiểu JDBC:** kiểu driver trả về từ ResultSet hoặc metadata.
3. **Kiểu Java:** kiểu component, constructor parameter hoặc accessor trong projection.

Không phải mọi database đều trả cùng kiểu cho một biểu thức. Ví dụ SUM(INTEGER) có thể trả kiểu rộng hơn kiểu cột gốc; phép chia có thể trả decimal; COUNT(*) thường trả số nguyên lớn.

### 7.1. Bảng đối chiếu kiểu phổ biến

| Kiểu SQL thường gặp | Kiểu Java thường phù hợp | Lưu ý |
| --- | --- | --- |
| BIGINT | Long / long | Dùng Long nếu cột có thể null; long không biểu diễn null |
| INTEGER | Integer / int | Cẩn thận overflow khi phép tính trả kết quả lớn hơn |
| SMALLINT | Short / Integer | Có thể dùng kiểu rộng hơn sau khi kiểm tra range |
| DECIMAL, NUMERIC | BigDecimal | Phù hợp tiền và số thập phân cần độ chính xác |
| REAL, FLOAT, DOUBLE | Float, Double | Không dùng floating point cho tiền cần chính xác thập phân |
| VARCHAR, CHAR, TEXT | String | Chú ý độ dài, collation và encoding |
| BOOLEAN | Boolean / boolean | Boolean cho phép null; mapping phụ thuộc driver/database |
| DATE | LocalDate | Chỉ biểu diễn ngày, không có thời điểm |
| TIME | LocalTime | Không chứa ngày hoặc timezone |
| TIMESTAMP không timezone | LocalDateTime | Là ngày giờ địa phương, không tự đại diện một instant toàn cầu |
| Timestamp có timezone/offset | OffsetDateTime, Instant hoặc kiểu được converter hỗ trợ | Kiểm tra quy tắc driver và database |
| UUID | UUID | Hỗ trợ và representation có thể khác giữa database |
| Binary/BLOB | byte[] hoặc kiểu stream phù hợp | Cân nhắc kích thước và cách tải dữ liệu |

Bảng trên là hướng dẫn phổ biến, không phải cam kết chuyển đổi giống nhau trên mọi JDBC driver. Hãy kiểm tra kiểu dữ liệu thực tế trong database và driver production.

### 7.2. Dùng wrapper khi cột có thể NULL

Nếu query có thể trả SQL NULL, kiểu primitive không phù hợp:

~~~java
public record CustomerSummary(
        Long id,
        String name,
        Integer loyaltyPoints,
        Boolean marketingOptIn
) {
}
~~~

long, int và boolean không biểu diễn null. Nếu database có thể trả null cho cột tương ứng, dùng wrapper (Long, Integer, Boolean) hoặc dùng COALESCE để quy định giá trị mặc định.

Ví dụ:

~~~sql
SELECT
    id AS id,
    name AS name,
    COALESCE(loyalty_points, 0) AS loyalty_points,
    COALESCE(marketing_opt_in, FALSE) AS marketing_opt_in
FROM customer;
~~~

Chỉ dùng giá trị mặc định nếu nó có đúng ý nghĩa nghiệp vụ. Null có thể có nghĩa “chưa biết”, khác với 0 hoặc false.

### 7.3. COUNT và SUM có kiểu trả về khác nhau

Ví dụ:

~~~sql
SELECT
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_revenue
FROM purchase_order
WHERE status = :status;
~~~

Projection:

~~~java
public record RevenueSummary(
        Long orderCount,
        BigDecimal totalRevenue
) {
}
~~~

COUNT(*) thường trả kiểu số nguyên lớn, phù hợp Long. SUM(total_amount) có kiểu kết quả phụ thuộc kiểu cột và database; nếu total_amount là DECIMAL/NUMERIC, BigDecimal thường phù hợp.

Nếu không có hàng phù hợp:

- COUNT(*) thường trả 0 trong một row kết quả.
- SUM(...) có thể trả SQL NULL.

Nếu muốn tổng mặc định bằng 0:

~~~sql
COALESCE(SUM(total_amount), 0) AS total_revenue
~~~

Kiểu literal 0 có thể được database suy ra thành kiểu số khác. Nếu cần độ chính xác/scale cụ thể, dùng cast phù hợp với database hoặc kiểm tra kiểu thực tế của biểu thức.

### 7.4. Tránh ép kiểu thu hẹp không an toàn

Giả sử database trả BIGINT nhưng projection khai báo Integer. Giá trị lớn hơn giới hạn Integer có thể gây lỗi chuyển đổi hoặc mất dữ liệu nếu có ép kiểu không phù hợp.

Tương tự, không map DECIMAL sang double chỉ vì tiện. Với tiền:

~~~java
public record PaymentSummary(
        Long paymentCount,
        BigDecimal totalAmount
) {
}
~~~

BigDecimal giữ độ chính xác thập phân. Nếu cần làm tròn, quy tắc scale và rounding mode phải được quy định trong nghiệp vụ.

## 8. Kiểu dữ liệu cho biểu thức và phép tính

Kiểu của cột gốc không nhất thiết là kiểu của biểu thức kết quả.

### 8.1. Phép nhân

~~~sql
SELECT
    quantity * unit_price AS line_total
FROM order_line;
~~~

Nếu quantity là INTEGER và unit_price là DECIMAL, kiểu kết quả phụ thuộc quy tắc promotion của database. Projection nên dùng kiểu đủ rộng và chính xác, thường là BigDecimal cho giá trị tiền.

### 8.2. Phép chia

~~~sql
SELECT
    CAST(total_amount AS DECIMAL(19, 4))
        / NULLIF(item_count, 0) AS average_item_amount
FROM order_summary;
~~~

Phép chia số nguyên ở một số database có thể cắt phần thập phân. Nếu cần kết quả decimal, hãy cast operand hoặc biểu thức theo cú pháp database. NULLIF tránh chia cho 0 bằng cách trả NULL khi mẫu số bằng 0. Kiểu DECIMAL và cú pháp cast cần điều chỉnh theo database mục tiêu.

### 8.3. CASE expression

~~~sql
SELECT
    id AS id,
    CASE
        WHEN active = TRUE THEN 'ACTIVE'
        ELSE 'INACTIVE'
    END AS display_status
FROM customer;
~~~

Projection:

~~~java
public record CustomerStatusView(
        Long id,
        String displayStatus
) {
}
~~~

Kiểu Java của component cần tương thích với kiểu kết quả của các nhánh CASE. Các nhánh nên có kiểu tương thích; nếu một nhánh trả NULL, cân nhắc wrapper/nullable type.

## 9. Tên constructor parameter và record component

Class-based projection thường được tạo thông qua constructor. Spring Data cần biết giá trị nào tương ứng với tham số nào.

Record:

~~~java
public record CustomerContact(
        Long customerId,
        String customerName,
        String emailAddress
) {
}
~~~

Canonical constructor có component names rõ ràng. Query:

~~~sql
SELECT
    c.id AS customer_id,
    c.name AS customer_name,
    c.email AS email_address
FROM customer c
WHERE c.active = TRUE;
~~~

Với naming strategy snake_case, các alias tương ứng với component names camelCase. Hãy bảo đảm mapping metadata của ứng dụng dùng cùng quy ước.

### 9.1. DTO class có một constructor

~~~java
public final class CustomerContact {
    private final Long customerId;
    private final String customerName;
    private final String emailAddress;

    public CustomerContact(
            Long customerId,
            String customerName,
            String emailAddress
    ) {
        this.customerId = customerId;
        this.customerName = customerName;
        this.emailAddress = emailAddress;
    }
}
~~~

Tên constructor parameter là một phần quan trọng của mapping khi framework dùng constructor binding. Với class thông thường, bật metadata tên tham số bằng -parameters khi cần và kiểm tra quy tắc của phiên bản Spring Data. Một constructor duy nhất giúp lựa chọn constructor rõ ràng hơn.

### 9.2. DTO có nhiều constructor

Nếu class có nhiều constructor, Spring Data cần xác định constructor dùng để tạo projection. Có thể dùng annotation @PersistenceCreator trong các trường hợp mà mapping API hỗ trợ:

~~~java
@PersistenceCreator
public CustomerContact(
        Long customerId,
        String customerName,
        String emailAddress
) {
    // ...
}
~~~

Đừng giả định constructor được chọn chỉ vì nó có nhiều tham số nhất. Kiểm tra quy tắc constructor discovery của release đang dùng.

### 9.3. Thứ tự cột không nên là hợp đồng duy nhất

Không thiết kế projection dựa trên giả định “cột đầu tiên luôn vào tham số đầu tiên, cột thứ hai vào tham số thứ hai” nếu mapping framework dùng tên property/column. Hãy đặt alias rõ ràng và bảo đảm constructor parameter có tên tương ứng.

Điều này giúp thay đổi thứ tự SELECT ít gây lỗi và làm SQL tự mô tả hơn. Nếu sử dụng custom RowMapper, lúc đó code mapper quyết định rõ cột nào đi vào constructor nào.

## 10. Interface projection và accessor

Một interface projection có thể khai báo:

~~~java
public interface ProductCard {
    Long getId();
    String getSku();
    String getName();
    BigDecimal getPrice();
}
~~~

Với query method, kết quả cần cung cấp các property mà interface yêu cầu. Với SQL tùy chỉnh, alias cột phải tương thích với mapping của projection:

~~~sql
SELECT
    p.id AS id,
    p.sku AS sku,
    p.name AS name,
    p.price_amount AS price
FROM product p
WHERE p.active = TRUE;
~~~

Nếu mapping dựa trên tên property Java và naming strategy, alias có thể cần theo tên cột tương ứng. Hãy dùng integration test để xác nhận chính xác hành vi của interface projection với phiên bản Spring Data JDBC trong dự án.

### 10.1. Getter phải phù hợp property

Accessor getCustomerName() diễn đạt property customerName. Nếu SQL trả alias không liên quan, chẳng hạn client_label, mapping có thể không tìm được giá trị trừ khi metadata/custom mapping cung cấp cách liên kết.

### 10.2. Projection đóng và dữ liệu tính toán

Closed projection chỉ khai báo các property cụ thể cần đọc. Một số kiểu query có thể tối ưu tập cột theo các property này. Với @Query viết SQL tường minh, chính danh sách SELECT là nơi quyết định cột nào được database trả về.

Nếu projection có property dẫn xuất từ nhiều field hoặc biểu thức SQL, hãy cân nhắc:

- Tính trong SQL và đặt alias rõ ràng.
- Dùng default method nếu chỉ cần kết hợp các property đã có.
- Dùng DTO projection khi muốn constructor và kiểu dữ liệu rõ ràng.

Không mặc định rằng một getter bổ sung sẽ khiến Spring Data tự tạo JOIN hoặc tự chạy truy vấn khác.

## 11. Null, Optional và giá trị mặc định trong projection

SQL NULL có thể xuất hiện trong result set dù bảng gốc cho phép hoặc không cho phép null, ví dụ do LEFT JOIN hoặc aggregate function.

Ví dụ:

~~~sql
SELECT
    po.id AS order_id,
    c.name AS customer_name
FROM purchase_order po
LEFT JOIN customer c ON c.id = po.customer_id;
~~~

Nếu không có customer tương ứng, customer_name là SQL NULL. Projection nên dùng kiểu có thể nhận null:

~~~java
public record OrderCustomerSummary(
        Long orderId,
        String customerName
) {
}
~~~

Không dùng primitive cho component có thể null:

~~~java
// Rủi ro nếu LEFT JOIN không có customer:
public record OrderCustomerSummary(
        long orderId,
        String customerName
) {
}
~~~

### 11.1. COALESCE hay wrapper?

Hai lựa chọn có ý nghĩa khác nhau:

- Dùng wrapper (Long, Integer, Boolean) để giữ nguyên thông tin SQL NULL.
- Dùng COALESCE để thay NULL bằng giá trị mặc định theo quy tắc nghiệp vụ.

Ví dụ:

~~~sql
SELECT
    id AS id,
    COALESCE(nickname, name) AS display_name
FROM customer;
~~~

Ở đây display name được định nghĩa là nickname nếu có, nếu không dùng name. Đây là một quy tắc hiển thị rõ ràng.

Không thay mọi NULL bằng chuỗi rỗng hoặc số 0 một cách máy móc. NULL có thể biểu diễn “chưa biết”, “không áp dụng” hoặc “không có quan hệ”, khác với giá trị rỗng/0.

### 11.2. Không có row khác với một row chứa NULL

Truy vấn projection trả:

- Zero rows: collection rỗng hoặc Optional.empty tùy kiểu method.
- Một row với customer_name = NULL: projection tồn tại, thuộc tính customerName null nếu mapping cho phép.
- Một row với customer_name = chuỗi rỗng: projection tồn tại và tên là chuỗi rỗng.

Đừng dùng Optional của toàn bộ projection để biểu diễn null của một component.

## 12. Alias và kiểu dữ liệu trong JOIN

JOIN là nơi alias và type mapping thường gây lỗi nhất:

~~~sql
SELECT
    po.id AS order_id,
    po.created_at AS order_created_at,
    c.id AS customer_id,
    c.name AS customer_name,
    c.active AS customer_active
FROM purchase_order po
JOIN customer c ON c.id = po.customer_id
WHERE po.id = :orderId;
~~~

Projection:

~~~java
public record OrderCustomerDetail(
        Long orderId,
        LocalDateTime orderCreatedAt,
        Long customerId,
        String customerName,
        Boolean customerActive
) {
}
~~~

Những alias có prefix giúp phân biệt hai aggregate cùng có property id, name hoặc createdAt. Nếu alias chỉ là id, một projection có cả order ID và customer ID sẽ không thể ánh xạ rõ ràng.

### 12.1. LEFT JOIN và kiểu nullable

Nếu đổi sang LEFT JOIN, các component lấy từ customer có thể null. Dùng wrapper/reference nullable phù hợp và xác định cách DTO biểu diễn customer vắng mặt.

### 12.2. Kiểu ID giữa hai bảng

Nếu purchase_order.customer_id là BIGINT nhưng customer.id là UUID hoặc kiểu khác, join có thể yêu cầu cast hoặc schema cần được sửa. Projection phải dùng kiểu tương ứng với cột result, không chỉ dựa trên kiểu ID của một entity khác.

## 13. Mapping ngày giờ và timezone

Ngày giờ cần đặc biệt chú ý vì tên kiểu Java không tự xác định ý nghĩa timezone.

| SQL column | Java type thường gặp | Ý nghĩa |
| --- | --- | --- |
| DATE | LocalDate | Ngày lịch |
| TIME | LocalTime | Giờ trong ngày |
| TIMESTAMP không timezone | LocalDateTime | Ngày giờ địa phương, không có offset |
| Timestamp có timezone/offset | OffsetDateTime hoặc Instant theo driver/converter | Thời điểm có thông tin offset hoặc instant |

Ví dụ:

~~~sql
SELECT
    id AS id,
    created_at AS created_at
FROM purchase_order
WHERE created_at >= :fromTime;
~~~

Projection:

~~~java
public record OrderCreatedView(
        Long id,
        LocalDateTime createdAt
) {
}
~~~

Nếu database lưu timestamp không timezone, LocalDateTime thường phản ánh đúng dữ liệu. Nếu nghiệp vụ cần một thời điểm toàn cầu, hãy xác định timezone ở tầng domain/database và dùng kiểu/converter tương ứng. Không tự diễn giải LocalDateTime thành UTC nếu schema không cam kết điều đó.

## 14. Projection cho phép tính tiền và số lượng

Tiền nên được lưu và đọc bằng kiểu số thập phân chính xác hoặc mô hình đơn vị nhỏ nhất theo chính sách của hệ thống.

Ví dụ cột DECIMAL:

~~~sql
SELECT
    order_id AS order_id,
    SUM(quantity * unit_price) AS line_total
FROM order_line
GROUP BY order_id;
~~~

Projection:

~~~java
public record OrderLineTotal(
        Long orderId,
        BigDecimal lineTotal
) {
}
~~~

Nếu schema lưu tiền bằng số nguyên đơn vị nhỏ nhất, phép tính có thể trả BIGINT:

~~~sql
SELECT
    order_id AS order_id,
    SUM(quantity * unit_price_minor_units) AS line_total_minor_units
FROM order_line
GROUP BY order_id;
~~~

Projection:

~~~java
public record OrderLineTotalMinorUnits(
        Long orderId,
        Long lineTotalMinorUnits
) {
}
~~~

Không đổi giữa hai mô hình mà không xác định scale, rounding và currency. Một số tiền không chỉ là một con số; nếu kết quả có thể gồm nhiều currency, projection cần mang thêm mã tiền hoặc nhóm theo currency.

## 15. Custom RowMapper khi projection mapping chuẩn không đủ

Với SQL có result shape phức tạp, có thể dùng custom repository fragment cùng JdbcClient hoặc NamedParameterJdbcTemplate để ánh xạ từng cột tường minh.

Ví dụ:

~~~java
public record CustomerSpend(
        Long customerId,
        String customerName,
        Long orderCount,
        BigDecimal totalSpend
) {
}
~~~

Custom query:

~~~java
public List<CustomerSpend> findCustomerSpend(String status) {
    return jdbcClient.sql("""
            SELECT
                c.id AS customer_id,
                c.name AS customer_name,
                COUNT(po.id) AS order_count,
                COALESCE(SUM(po.total_amount), 0) AS total_spend
            FROM customer c
            LEFT JOIN purchase_order po
                ON po.customer_id = c.id
               AND po.status = :status
            GROUP BY c.id, c.name
            ORDER BY total_spend DESC, c.id
            """)
        .param("status", status)
        .query((rs, rowNum) -> new CustomerSpend(
                rs.getLong("customer_id"),
                rs.getString("customer_name"),
                rs.getLong("order_count"),
                rs.getBigDecimal("total_spend")
        ))
        .list();
}
~~~

RowMapper tường minh có một số lợi ích:

- Người viết quyết định chính xác cột nào đi vào component nào.
- Có thể gọi getter JDBC phù hợp với từng kiểu.
- Có thể xử lý null bằng wasNull() hoặc getter object.
- Có thể biến đổi/chuẩn hóa dữ liệu trong lúc ánh xạ.
- Không phụ thuộc cơ chế projection tự động cho một result shape phức tạp.

Ví dụ trên giả định JdbcClient của Spring Framework 6.1 trở lên và schema có các cột tương ứng. Với phiên bản cũ hơn, dùng NamedParameterJdbcTemplate hoặc JdbcTemplate.

### 15.1. Kiểm tra NULL trong RowMapper

Với primitive getter như getLong, JDBC trả 0 khi SQL value là NULL; phải gọi wasNull() ngay sau getter nếu cần phân biệt:

~~~java
long raw = rs.getLong("customer_id");
Long customerId = rs.wasNull() ? null : raw;
~~~

Hoặc dùng getter trả object nếu driver hỗ trợ kiểu tương ứng:

~~~java
Long customerId = rs.getObject("customer_id", Long.class);
~~~

Không để NULL bị biến thành 0 ngoài ý muốn.

### 15.2. Khi nào không cần RowMapper riêng?

Nếu projection chỉ có vài cột đơn giản và mapping chuẩn của Spring Data JDBC hoạt động rõ ràng, dùng DTO/record projection sẽ ít code hơn. Custom mapper chỉ nên xuất hiện khi nó giải quyết một nhu cầu cụ thể như kiểu dữ liệu đặc biệt, biểu thức phức tạp, JSON, nhiều nhánh nullable hoặc mapping nhiều bảng.

## 16. Các lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Projection property không nhận được giá trị | Alias không khớp column mapping/property | Đặt alias theo naming strategy và kiểm tra result-set labels |
| Hai bảng đều có cột id | JOIN tạo nhãn cột trùng | Alias riêng như order_id, customer_id |
| DTO constructor không được gọi đúng | Constructor không rõ hoặc tên tham số không có metadata phù hợp | Dùng record/constructor rõ ràng, -parameters, @PersistenceCreator khi cần |
| Component record không được ánh xạ | Alias hoặc kiểu dữ liệu không khớp component | Kiểm tra từng component và column label |
| Primitive nhận SQL NULL | Primitive không biểu diễn null | Dùng wrapper hoặc COALESCE có chủ đích |
| COUNT/SUM không khớp kiểu Java | Kiểu kết quả aggregate khác kiểu cột gốc | Kiểm tra kiểu DB/driver, dùng Long/BigDecimal phù hợp |
| Tiền bị sai phần thập phân | Dùng double hoặc phép chia số nguyên | Dùng BigDecimal, cast và quy tắc rounding rõ |
| Thời điểm lệch timezone | Nhầm TIMESTAMP với instant có timezone | Xác định semantics schema và kiểu Java |
| @Param không khớp placeholder | Sai tên hoặc phụ thuộc metadata tham số | Dùng @Param tường minh |
| Dùng placeholder cho tên cột | Bind parameter chỉ dành cho giá trị | Whitelist identifier và dựng SQL an toàn |
| LEFT JOIN gây lỗi constructor | Cột phía phải có thể null nhưng DTO dùng primitive | Dùng wrapper hoặc quy tắc mặc định |
| SELECT * làm mapping bất ổn | Result set chứa cột trùng/thừa hoặc thay đổi theo schema | Liệt kê cột và alias rõ ràng |
| Projection bị dùng để cập nhật aggregate | DTO không chứa đầy đủ invariant/state | Đọc root đầy đủ cho command path |
| RowMapper biến NULL thành 0 | Dùng getLong/getInt mà không gọi wasNull() | Dùng getObject hoặc kiểm tra wasNull() |

## 17. Quy trình thiết kế projection

Khi tạo projection mới, hãy làm theo trình tự:

1. **Xác định use case đọc.** Caller cần hiển thị, báo cáo, tìm kiếm hay xử lý nghiệp vụ?
2. **Chọn hình dạng kết quả.** Interface projection, DTO class, record hoặc RowMapper.
3. **Liệt kê component.** Mỗi component có tên và kiểu Java rõ ràng.
4. **Viết SELECT có chủ đích.** Chỉ lấy cột cần thiết; không dùng SELECT * cho projection join.
5. **Đặt alias duy nhất.** Alias theo tên cột mà mapping metadata mong đợi; dùng prefix để phân biệt cột từ nhiều bảng.
6. **Liên kết tham số.** Dùng named placeholder và @Param tường minh.
7. **Kiểm tra kiểu.** So sánh SQL type, JDBC type và Java type; xem xét null, overflow, scale và timezone.
8. **Xác định cardinality.** Optional cho tối đa một row; List/Iterable cho nhiều row; scalar cho một giá trị.
9. **Kiểm tra version/module.** Xác minh loại projection và mapping được hỗ trợ bởi Spring Data JDBC trong dự án.
10. **Integration test.** Kiểm tra dữ liệu có/không có, alias, null, biểu thức aggregate, join và database dialect thật.

## 18. Ví dụ kiểm thử projection end-to-end

Giả sử repository có query:

~~~java
@Query("""
       SELECT
           po.id AS order_id,
           po.order_number AS order_number,
           c.name AS customer_name,
           po.total_amount AS total_amount
       FROM purchase_order po
       JOIN customer c ON c.id = po.customer_id
       WHERE po.status = :status
       ORDER BY po.id
       """)
List<OrderListItem> findOrderItems(@Param("status") String status);
~~~

Test nên xác nhận:

~~~java
@Test
void mapsAliasesAndTypesToProjection() {
    List<OrderListItem> result =
            repository.findOrderItems("CONFIRMED");

    assertThat(result).hasSize(1);
    OrderListItem item = result.get(0);
    assertThat(item.orderId()).isEqualTo(1001L);
    assertThat(item.orderNumber()).isEqualTo("ORD-1001");
    assertThat(item.customerName()).isEqualTo("Lan");
    assertThat(item.totalAmount())
            .isEqualByComparingTo("125000.00");
}
~~~

Đây là khung minh họa; test thực tế cần chuẩn bị schema và fixture, imports, repository bean và database phù hợp. Ngoài trường hợp thành công, nên kiểm tra:

- Không có đơn phù hợp thì trả list rỗng.
- LEFT JOIN không có customer thì component nullable hoạt động đúng.
- Aggregate function trả kiểu phù hợp.
- Tên alias không bị driver chuẩn hóa ngoài dự kiến.
- Tham số có giá trị đặc biệt vẫn được bind an toàn.

Với SQL phụ thuộc PostgreSQL, MySQL hoặc SQL Server, chạy integration test trên đúng database hoặc Testcontainers tương ứng. H2 không phải bằng chứng đầy đủ cho mọi dialect.

## Ghi nhớ

Projection là hợp đồng giữa SQL và Java. **Alias cột** xác định nhãn dữ liệu trả về; **tên tham số** liên kết placeholder SQL với method parameter; **kiểu dữ liệu** quyết định giá trị từ JDBC có thể được ánh xạ chính xác vào component hay không.

Hãy alias rõ các cột, đặc biệt khi JOIN hoặc dùng biểu thức; dùng @Param để khai báo tên placeholder tường minh; chọn wrapper cho dữ liệu có thể NULL, BigDecimal cho số thập phân cần chính xác và kiểu ngày giờ đúng semantics của schema. Khi mapping chuẩn không đủ, custom RowMapper cho phép kiểm soát từng cột. Cuối cùng, kiểm thử projection trên database mục tiêu để xác nhận alias, constructor, kiểu dữ liệu và trường hợp null thực sự hoạt động như thiết kế.
