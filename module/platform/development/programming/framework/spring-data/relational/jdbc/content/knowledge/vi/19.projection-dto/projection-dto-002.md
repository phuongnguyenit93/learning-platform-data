# Projection interface đóng và các thuộc tính được chọn

Trong **Spring Data Relational JDBC**, repository thường trả về aggregate root để ứng dụng thực hiện hành vi nghiệp vụ. Nhưng nhiều màn hình chỉ cần một vài thuộc tính của aggregate, chẳng hạn mã đơn, trạng thái và ngày tạo. Tải toàn bộ object chỉ để đọc ba trường có thể tạo thêm chi phí không cần thiết.

**Projection interface đóng (closed interface projection)** cho phép khai báo một interface chỉ chứa các accessor tương ứng với những thuộc tính cần đọc. Spring Data có thể xác định trước tập thuộc tính mà projection yêu cầu và, trong các trường hợp truy vấn được hỗ trợ, tối ưu câu SELECT để chỉ lấy những cột cần thiết.

Bài học trình bày cách khai báo closed projection, cách tên getter liên kết với thuộc tính Java của aggregate, cách repository trả projection, ý nghĩa của các thuộc tính được chọn, và giới hạn khi cần dữ liệu từ aggregate khác hoặc collection con. Ta cũng sẽ so sánh projection với aggregate root, DTO và SQL tùy chỉnh.

## 1. Projection là gì?

Projection là một **góc nhìn dữ liệu giới hạn** trên một đối tượng. Thay vì trả toàn bộ `PurchaseOrder`, ứng dụng có thể yêu cầu một kiểu chỉ mô tả `id`, `orderNumber` và `status`.

Giả sử aggregate có nhiều thuộc tính:

~~~java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("order_number")
    private String orderNumber;

    private Long customerId;
    private String status;

    @Column("created_at")
    private LocalDateTime createdAt;

    @Column("total_amount")
    private BigDecimal totalAmount;

    // Các thuộc tính và hành vi domain khác.
}
~~~

Một màn hình danh sách có thể chỉ cần:

~~~text
id | orderNumber | status
~~~

Nếu trả `PurchaseOrder`, code gọi nhận cả các thuộc tính khác và có thể cả các thành phần được mapping trong aggregate. Nếu trả projection, code gọi chỉ nhìn thấy những accessor được khai báo trong interface.

Projection không phải một bảng database, không phải một aggregate root mới và không tự tạo một câu SQL VIEW. Nó là kiểu kết quả mà Spring Data dùng để trình bày dữ liệu được truy vấn.

## 2. Closed interface projection là gì?

Một interface projection được xem là **closed** khi các accessor của nó tương ứng trực tiếp với các thuộc tính đã biết của kiểu domain đích. Spring Data có thể xác định chính xác projection cần những thuộc tính nào.

Ví dụ:

~~~java
package com.example.orders.read;

import java.time.LocalDateTime;

public interface OrderListProjection {

    Long getId();

    String getOrderNumber();

    String getStatus();

    LocalDateTime getCreatedAt();
}
~~~

Các getter tương ứng với thuộc tính `id`, `orderNumber`, `status` và `createdAt` của `PurchaseOrder`.

Projection không khai báo:

- `customerId`, nếu màn hình không cần mã khách hàng.
- `totalAmount`, nếu màn hình không hiển thị tổng tiền.
- `lines`, nếu màn hình không cần danh sách dòng hàng.
- Những thuộc tính khác của aggregate không phục vụ use case đọc.

Spring Data biết trước tập thuộc tính cần thiết từ interface. Với truy vấn dẫn xuất và các trường hợp projection được hỗ trợ, framework có thể giới hạn các cột cần đọc. Đây là lợi ích quan trọng của closed projection.

### 2.1. Vì sao gọi là “đóng”?

Interface đóng phạm vi dữ liệu cần truy cập: các thuộc tính được khai báo có thể được xác định từ metadata của aggregate. Spring Data không cần thực thi một biểu thức tùy ý để tìm ra những trường nào sẽ được đọc.

Ví dụ:

~~~java
public interface OrderIdentityProjection {
    Long getId();
    String getOrderNumber();
}
~~~

Projection này chỉ yêu cầu hai thuộc tính. Nếu code gọi chỉ dùng mã đơn và ID, không có lý do nghiệp vụ nào buộc nó phải nhận thêm `status`, `customerId`, `createdAt` hoặc collection `lines`.

### 2.2. Getter phải tương ứng với property của Java

Tên getter được chuyển thành tên thuộc tính Java theo quy tắc JavaBean:

| Getter trong projection | Thuộc tính Java cần có |
|---|---|
| `getId()` | `id` |
| `getOrderNumber()` | `orderNumber` |
| `getStatus()` | `status` |
| `getCreatedAt()` | `createdAt` |
| `isArchived()` | `archived` |

Tên trong interface dựa trên **tên property Java**, không phải tên cột SQL. Ví dụ:

~~~java
@Column("order_number")
private String orderNumber;
~~~

Projection vẫn khai báo:

~~~java
String getOrderNumber();
~~~

Không khai báo `getOrder_number()` chỉ vì tên cột database dùng snake_case. Annotation `@Column` và naming strategy chịu trách nhiệm ánh xạ property Java sang cột SQL.

## 3. Dùng projection trong repository

Repository có thể trả về projection interface thay vì aggregate:

~~~java
package com.example.orders.repository;

import java.util.List;

import com.example.orders.domain.PurchaseOrder;
import com.example.orders.read.OrderListProjection;
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    List<OrderListProjection> findByStatus(String status);
}
~~~

Gọi repository:

~~~java
List<OrderListProjection> rows =
    repository.findByStatus("SUBMITTED");

for (OrderListProjection row : rows) {
    System.out.println(
        row.getId() + " - " + row.getOrderNumber()
            + " - " + row.getStatus()
    );
}
~~~

Method `findByStatus` vẫn truy vấn theo thuộc tính của aggregate `PurchaseOrder`, nhưng kiểu trả về là `OrderListProjection`. Spring Data tạo các projection object từ kết quả truy vấn.

Có thể dùng các kiểu trả về khác phù hợp với cardinality:

~~~java
List<OrderListProjection> findByStatus(String status);

Optional<OrderListProjection> findByOrderNumber(String orderNumber);

OrderListProjection findFirstByCustomerIdOrderByCreatedAtDesc(
    Long customerId
);
~~~

Ví dụ cuối chỉ phù hợp khi nghiệp vụ và dữ liệu bảo đảm có kết quả; nếu có thể không tìm thấy, `Optional` thường diễn đạt hợp đồng rõ hơn.

Không khai báo một method kế thừa `findById(Long)` với kiểu trả về projection không tương thích với method đã có trong `CrudRepository`. Hãy dùng tên query method khác, ví dụ `findProjectionByOrderNumber(...)`, hoặc thiết kế repository/query interface riêng.

## 4. Projection giúp chọn thuộc tính nào?

Hãy xem hai projection:

~~~java
public interface OrderIdentityProjection {
    Long getId();
    String getOrderNumber();
}

public interface OrderListProjection {
    Long getId();
    String getOrderNumber();
    String getStatus();
    LocalDateTime getCreatedAt();
    BigDecimal getTotalAmount();
}
~~~

Projection thứ nhất cần hai property. Projection thứ hai cần năm property. Khi query được tối ưu theo projection, tập cột có thể được giới hạn tương ứng.

### 4.1. SQL minh họa cho tập cột được chọn

Với `OrderIdentityProjection`, câu SELECT về mặt ý nghĩa chỉ cần:

~~~sql
SELECT id, order_number
FROM purchase_orders
WHERE status = ?;
~~~

Với `OrderListProjection`, câu SELECT cần thêm các cột:

~~~sql
SELECT
    id,
    order_number,
    status,
    created_at,
    total_amount
FROM purchase_orders
WHERE status = ?;
~~~

Đây là minh họa cho **tập thuộc tính được chọn**, không phải cam kết rằng mọi phiên bản Spring Data JDBC đều phát ra chính xác chuỗi SQL trên trong mọi trường hợp. Câu lệnh thực tế còn phụ thuộc loại query, mapping, dialect và khả năng tối ưu của framework.

Hãy bật SQL logging hoặc dùng công cụ quan sát JDBC để xác nhận các cột được đọc trong ứng dụng đang chạy.

### 4.2. Projection càng nhỏ, mục tiêu đọc càng rõ

Không nên tạo một interface chứa mọi getter “để dùng chung cho tiện” nếu mỗi màn hình chỉ cần một nhóm trường nhỏ. Làm như vậy sẽ mở rộng tập property cần đọc và làm mất lợi ích của projection.

Nên đặt tên theo use case:

~~~java
public interface OrderListProjection {
    Long getId();
    String getOrderNumber();
    String getStatus();
}

public interface OrderExportProjection {
    Long getId();
    String getOrderNumber();
    String getStatus();
    LocalDateTime getCreatedAt();
    BigDecimal getTotalAmount();
}
~~~

Hai projection có thể cùng dựa trên `PurchaseOrder`, nhưng biểu đạt hai nhu cầu đọc khác nhau. Tên interface giúp người đọc biết dữ liệu nào được yêu cầu và dùng ở đâu.

## 5. Closed projection và computed property

Một projection có thể cung cấp default method được tính từ các accessor đã khai báo:

~~~java
public interface OrderListProjection {

    String getOrderNumber();

    String getStatus();

    default String getDisplayLabel() {
        return getOrderNumber() + " [" + getStatus() + "]";
    }
}
~~~

`getDisplayLabel()` không tương ứng với cột database. Đây là giá trị tính trong Java từ hai property đã có trong projection. Vì default method chỉ dùng các accessor đóng, Spring Data vẫn có thể xác định tập thuộc tính nguồn.

Cách này phù hợp với phép ghép đơn giản cho mục đích trình bày. Nếu phép tính phức tạp, cần dữ liệu từ nhiều bảng hoặc phải áp dụng quy tắc nghiệp vụ, hãy đặt logic ở query service, DTO mapper hoặc domain model thích hợp.

### 5.1. Phân biệt với open projection

Một open projection có thể dùng biểu thức SpEL để truy cập target:

~~~java
import org.springframework.beans.factory.annotation.Value;

public interface OrderOpenProjection {

    String getOrderNumber();

    @Value("#{target.orderNumber + ' - ' + target.status}")
    String getLabel();
}
~~~

Vì biểu thức SpEL có thể tham chiếu các thuộc tính khác của target, Spring Data không thể xác định chắc chắn chỉ từ interface rằng cần những property nào. Do đó, open projection không có cùng lợi thế giới hạn selected properties như closed projection.

Khi mục tiêu chính là giảm tập cột được đọc, hãy ưu tiên accessor đóng và default method chỉ dựa trên những accessor đó. Không thêm `@Value` chỉ để ghép hai chuỗi đơn giản.

## 6. Kiểu dữ liệu của accessor

Kiểu trả về trong projection nên tương thích với kiểu property của aggregate:

| Property của aggregate | Accessor projection |
|---|---|
| `Long id` | `Long getId()` |
| `String orderNumber` | `String getOrderNumber()` |
| `BigDecimal totalAmount` | `BigDecimal getTotalAmount()` |
| `LocalDateTime createdAt` | `LocalDateTime getCreatedAt()` |
| `OrderStatus status` | `OrderStatus getStatus()` |
| `boolean archived` | `boolean isArchived()` hoặc getter phù hợp |

Nếu property có thể null, dùng kiểu tham chiếu tương ứng thay vì primitive:

~~~java
public interface CustomerReferenceProjection {
    Long getCustomerId();
    String getOptionalNote();
}
~~~

Nếu ứng dụng dùng nullable wrapper hoặc `Optional` trong projection, hãy bảo đảm cách ánh xạ và kiểu property tương thích với phiên bản Spring Data đang dùng. Không khai báo `long getCustomerId()` nếu database có thể trả NULL, vì primitive không thể biểu diễn null.

Với enum, accessor có thể dùng kiểu enum của domain nếu property aggregate có kiểu đó:

~~~java
public interface OrderStatusProjection {
    OrderStatus getStatus();
}
~~~

Spring Data dùng cơ chế conversion đã cấu hình cho property. Nếu enum có mã lưu trữ tùy chỉnh, converter đọc dữ liệu cần được đăng ký nhất quán; projection không thay thế converter.

## 7. Projection không phải aggregate có thể lưu lại

Projection là góc nhìn đọc. Nó không thay thế `PurchaseOrder` trong quy trình thay đổi nghiệp vụ.

Ví dụ:

~~~java
OrderListProjection row =
    repository.findByOrderNumber("SO-2026-001")
        .orElseThrow();
~~~

Bạn có thể đọc:

~~~java
String number = row.getOrderNumber();
String status = row.getStatus();
~~~

Nhưng không nên thiết kế luồng:

~~~java
// Không phải cách cập nhật aggregate:
row.setStatus("SUBMITTED");
repository.save(row);
~~~

Interface projection thường chỉ công bố getter và không có hành vi domain. Quan trọng hơn, projection không đại diện cho đầy đủ trạng thái aggregate, nên dùng nó để ghi có thể bỏ qua invariant hoặc các property cần thiết.

Luồng command nên tải aggregate:

~~~java
@Transactional
public void submitOrder(Long id) {
    PurchaseOrder order = orders.findById(id)
        .orElseThrow();

    order.submit();
    orders.save(order);
}
~~~

Luồng query có thể dùng projection:

~~~java
@Transactional(readOnly = true)
public List<OrderListProjection> listSubmittedOrders() {
    return orders.findByStatus("SUBMITTED");
}
~~~

Hai luồng phục vụ mục tiêu khác nhau và có thể cùng tồn tại trong một repository hoặc các thành phần query riêng.

## 8. Projection có tự JOIN aggregate khác không?

Không nên giả định rằng thêm getter vào projection sẽ tự tạo JOIN tới bất kỳ bảng nào.

Giả sử `PurchaseOrder` chỉ lưu:

~~~java
private Long customerId;
~~~

và `Customer` là aggregate root độc lập. Thêm:

~~~java
String getCustomerName();
~~~

không tự làm Spring Data JDBC suy ra rằng cần JOIN `customers` rồi lấy `display_name`. `customerName` không phải property của `PurchaseOrder` trong ví dụ.

Nếu màn hình cần tên khách cùng đơn hàng, có thể viết SQL đọc chuyên biệt:

~~~sql
SELECT
    o.id AS order_id,
    o.order_number,
    o.status,
    c.display_name AS customer_name
FROM purchase_orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.status = :status;
~~~

Sau đó ánh xạ kết quả thành DTO bằng `NamedParameterJdbcTemplate`, hoặc dùng một query/projection tùy chỉnh có mapping được hỗ trợ rõ ràng trong phiên bản Spring Data JDBC của dự án.

Đây là điểm phân biệt:

- Closed projection giới hạn các property của kiểu domain được chiếu.
- JOIN kết hợp dữ liệu từ nhiều bảng theo SQL.
- DTO/read model có thể chứa các giá trị kết hợp hoặc tính toán không thuộc một aggregate đơn lẻ.

Không nên gán tên property giả vào projection chỉ để mong framework tự tìm bảng liên quan.

## 9. Projection với collection con

Giả sử aggregate có:

~~~java
@MappedCollection(idColumn = "order_id")
private Set<OrderLine> lines;
~~~

Một màn hình danh sách chỉ cần `orderNumber` và `status`. Closed projection có thể chỉ yêu cầu hai property này:

~~~java
public interface OrderListProjection {
    String getOrderNumber();
    String getStatus();
}
~~~

Không cần khai báo `getLines()` nếu màn hình không dùng dòng hàng. Điều này giúp tránh yêu cầu đọc thêm dữ liệu không cần thiết khi kiểu projection và query path cho phép giới hạn property.

Nếu màn hình cần `lineCount`, `totalAmount` được tính từ `order_lines`, đó không đơn giản là một property scalar của root trừ khi aggregate đã lưu sẵn các giá trị đó. Không thể mặc định getter `getLineCount()` sẽ khiến Spring Data tự chạy `COUNT(*)` trên bảng con.

Hãy dùng SQL đọc chuyên biệt:

~~~sql
SELECT
    o.id,
    o.order_number,
    COUNT(l.id) AS line_count,
    COALESCE(SUM(l.quantity * l.unit_price), 0) AS total_amount
FROM purchase_orders o
LEFT JOIN order_lines l ON l.order_id = o.id
GROUP BY o.id, o.order_number;
~~~

Kết quả có thể được ánh xạ vào:

~~~java
public record OrderSummaryDto(
        Long id,
        String orderNumber,
        long lineCount,
        BigDecimal totalAmount
) {
}
~~~

DTO phù hợp hơn ở đây vì `lineCount` và `totalAmount` được tính từ truy vấn, không nhất thiết là property được lưu trực tiếp trên aggregate.

## 10. Closed projection với `@Query`

Repository cũng có thể khai báo SQL tùy chỉnh:

~~~java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    @Query("""
        SELECT id, order_number, status, created_at
        FROM purchase_orders
        WHERE status = :status
        ORDER BY created_at DESC, id DESC
        """)
    List<OrderListProjection> findListByStatus(
        @Param("status") String status
    );
}
~~~

Khi dùng SQL tùy chỉnh, câu SELECT phải trả các cột cần thiết với tên/alias tương thích với mapping kết quả. Tùy database, naming strategy và cơ chế mapping của phiên bản Spring Data JDBC, cách đặt alias có thể cần điều chỉnh. Hãy kiểm tra integration test với database mục tiêu thay vì giả định alias camelCase hay snake_case được xử lý giống nhau ở mọi dialect.

Đặc biệt:

- Không SELECT thiếu property mà projection yêu cầu.
- Không trả nhiều cột trùng tên sau JOIN mà không đặt alias rõ.
- Không dùng projection root để giả định collection con tự được tải qua một custom SELECT.
- Nếu query trả kết quả tổng hợp hoặc nhiều bảng, DTO/read DAO thường dễ kiểm soát hơn.

Với derived query đơn giản, Spring Data có thể xác định property từ interface projection. Với custom SQL, người viết chịu trách nhiệm nhiều hơn về danh sách cột và alias.

## 11. Projection, DTO và aggregate: chọn kiểu nào?

| Tiêu chí | Closed interface projection | DTO/record | Aggregate root |
|---|---|---|---|
| Mục tiêu | Đọc một tập property đã xác định | Đọc dữ liệu trình bày hoặc kết quả kết hợp | Thực hiện hành vi domain |
| Khai báo | Interface getter | Class/record có constructor | Entity/domain class |
| Nguồn dữ liệu | Thường là property của aggregate | Có thể từ nhiều bảng hoặc biểu thức SQL | Mapping aggregate |
| Tập cột | Có thể được tối ưu từ accessor đóng | Do query/mapping xác định | Theo aggregate mapping |
| Computed value | Default method đơn giản | Constructor/mapper hoặc SQL | Domain method |
| Ghi dữ liệu | Không phải mục đích | Không phải mục đích | Qua repository root |
| JOIN/báo cáo phức tạp | Không tự suy ra JOIN | Phù hợp với SQL tùy chỉnh | Không phải mục tiêu chính |

### Khi nên chọn closed projection?

- Query dẫn xuất theo aggregate.
- Chỉ cần một số property đã tồn tại trên kiểu domain.
- Muốn interface nhỏ, rõ ràng cho một màn hình hoặc use case đọc.
- Không cần sửa dữ liệu qua kết quả trả về.

### Khi nên chọn DTO?

- Kết quả JOIN nhiều bảng.
- Có cột tính toán như tổng tiền, số lượng hoặc rank.
- Tên trường trả về khác property domain.
- Muốn một cấu trúc dữ liệu độc lập với entity.
- Cần kiểm soát rõ kiểu kết quả của một báo cáo hoặc API.

### Khi cần aggregate root?

- Use case thay đổi trạng thái hoặc dữ liệu.
- Cần bảo vệ invariant.
- Cần làm việc với các entity con thuộc aggregate.
- Kết quả sẽ được lưu qua repository.

## 12. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Getter projection không được ánh xạ | Tên getter không khớp property Java | Đặt getter theo JavaBean property |
| Projection yêu cầu thuộc tính không tồn tại | Nhầm tên cột SQL với tên property hoặc tự thêm property không có trên entity | Kiểm tra entity và mapping `@Column` |
| SQL vẫn đọc nhiều cột hơn dự kiến | Query path/version không tối ưu projection hoặc projection mở | Kiểm tra SQL thực tế, dùng closed accessor và query phù hợp |
| Thêm `@Value` rồi mong chọn ít cột | Open projection cho phép truy cập target tùy ý | Dùng getter đóng/default method đơn giản |
| Getter `getCustomerName()` không hoạt động | `customerName` không phải property của aggregate | Dùng JOIN/DTO hoặc mapping quan hệ rõ ràng |
| Getter `getLineCount()` không tự chạy COUNT | Projection không tự tạo phép tổng hợp | Viết query aggregate function và ánh xạ DTO |
| Projection bị dùng để cập nhật | Nhầm read view với domain entity | Tải aggregate root, gọi method nghiệp vụ, `save()` |
| Custom query không map được cột | Alias hoặc tên cột không khớp mapping | Đặt alias rõ và kiểm tra bằng integration test |
| Dùng primitive cho property nullable | Primitive không biểu diễn được NULL | Dùng kiểu wrapper phù hợp |
| Một projection dùng cho mọi màn hình | Interface chứa quá nhiều property | Tạo projection nhỏ theo use case |

## 13. Kiểm tra SQL thực tế của projection

Lợi ích chọn thuộc tính cần được xác nhận bằng câu SQL được thực thi. Bật log SQL của ứng dụng trong môi trường phát triển:

~~~yaml
logging:
  level:
    org.springframework.jdbc.core: DEBUG
    org.springframework.data.jdbc: DEBUG
~~~

Mức log cụ thể có thể khác giữa phiên bản Spring Boot/Spring Data. Nếu log không hiển thị đầy đủ câu SQL hoặc bind parameter, dùng datasource proxy, công cụ quan sát JDBC hoặc log của database.

Khi kiểm tra, hãy so sánh:

1. Repository method trả `PurchaseOrder`.
2. Repository method trả `OrderIdentityProjection`.
3. Repository method trả `OrderListProjection`.

Quan sát:

- Danh sách cột SELECT có thay đổi theo projection không?
- Có đọc thêm bảng hoặc collection không cần thiết không?
- Query có cùng điều kiện WHERE và ORDER BY không?
- Kết quả projection có đúng giá trị và kiểu dữ liệu không?
- Chi phí thực tế có giảm trên tập dữ liệu đại diện không?

Không kết luận hiệu năng chỉ từ số getter trong interface. Kết quả còn phụ thuộc database, index, kích thước hàng, driver, mapping và số lượng bản ghi.

## 14. Bài tập thực hành

### Bài 1 — Tạo closed projection đầu tiên

1. Tạo `PurchaseOrder` có `id`, `orderNumber`, `status`, `customerId`, `createdAt` và `totalAmount`.
2. Tạo `OrderIdentityProjection` chỉ có `getId()` và `getOrderNumber()`.
3. Khai báo `List<OrderIdentityProjection> findByStatus(String status)`.
4. Gọi repository và in hai thuộc tính.
5. Bật SQL log để quan sát tập cột được truy vấn.

### Bài 2 — Tạo projection cho màn hình danh sách

1. Tạo `OrderListProjection` với `id`, `orderNumber`, `status` và `createdAt`.
2. Tạo query method trả projection.
3. Thêm `default String getDisplayLabel()` dựa trên `getOrderNumber()` và `getStatus()`.
4. So sánh với một open projection dùng `@Value`.
5. Giải thích vì sao closed projection dễ được tối ưu selected properties hơn.

### Bài 3 — Xử lý property không thuộc aggregate

1. Thêm bảng `customers` và property `customerId` trong `PurchaseOrder`.
2. Thử khai báo getter `getCustomerName()` trong projection.
3. Xác định vì sao getter không tự tạo JOIN đến bảng khách.
4. Viết SQL JOIN và ánh xạ kết quả thành `OrderSummaryDto`.

### Bài 4 — Tổng hợp dữ liệu từ collection con

1. Thêm bảng `order_lines`.
2. Tạo query đếm số dòng và tính tổng tiền theo đơn.
3. Ánh xạ kết quả thành DTO có `lineCount` và `totalAmount`.
4. So sánh DTO báo cáo với closed projection chỉ đọc property của root.

### Bài 5 — So sánh chi phí

1. Tạo dữ liệu thử với nhiều đơn và dòng hàng.
2. Đọc danh sách bằng aggregate root.
3. Đọc lại bằng closed projection.
4. Đọc báo cáo bằng DTO JOIN.
5. Ghi nhận SQL, số hàng, thời gian và lượng dữ liệu trả về.

## 15. Kết luận

**Closed interface projection** khai báo một tập getter tương ứng với các property đã biết của aggregate. Spring Data có thể xác định trước các thuộc tính được yêu cầu và tối ưu tập cột được chọn trong những truy vấn được hỗ trợ. Tên getter dựa trên **property Java**, còn `@Column` và naming strategy ánh xạ property đó sang tên cột database.

Giữ projection nhỏ theo use case để code đọc rõ ràng và tránh yêu cầu dữ liệu không cần thiết. Default method có thể tính giá trị đơn giản từ các accessor đóng; biểu thức SpEL tạo open projection và không có cùng lợi thế tối ưu selected properties.

Projection là góc nhìn đọc, không phải aggregate để cập nhật. Khi cần JOIN sang aggregate khác, tính tổng từ collection con hoặc tạo báo cáo, hãy dùng SQL tùy chỉnh và DTO/read model phù hợp. Khi cần thay đổi nghiệp vụ, tải aggregate root, kiểm tra invariant và lưu qua repository.
