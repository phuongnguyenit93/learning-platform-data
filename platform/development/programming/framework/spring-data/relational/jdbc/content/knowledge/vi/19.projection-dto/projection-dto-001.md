# Tách mô hình đọc khỏi aggregate dùng cho cập nhật

Trong **Spring Data Relational JDBC**, aggregate root là đơn vị mà ứng dụng dùng để thực hiện thay đổi nghiệp vụ và lưu trạng thái nhất quán. Nhưng một màn hình danh sách, báo cáo hoặc API tìm kiếm thường chỉ cần một vài trường từ nhiều bảng. Nếu mọi truy vấn đều tải đầy đủ aggregate rồi chuyển thành JSON, ứng dụng có thể đọc nhiều dữ liệu không cần thiết và buộc mô hình ghi phải phục vụ cả những nhu cầu hiển thị rất khác nhau.

Một cách tổ chức rõ ràng là tách:

- **Write model (mô hình ghi):** aggregate root và các hành vi domain dùng để kiểm tra invariant, thay đổi trạng thái và lưu qua repository.
- **Read model (mô hình đọc):** projection hoặc DTO chứa đúng dữ liệu mà một truy vấn/màn hình cần.

Đây là cách áp dụng CQRS ở mức vừa phải: tách đường đọc và đường ghi về mặt mô hình và API, nhưng có thể vẫn dùng chung một database quan hệ. Không cần xây dựng event sourcing hoặc hai hệ thống lưu trữ riêng chỉ để dùng projection.

## 1. Vì sao không dùng aggregate cho mọi truy vấn?

Giả sử hệ thống bán hàng có aggregate:

```text
PurchaseOrder (aggregate root)
  ├── id
  ├── orderNumber
  ├── status
  ├── customer reference
  ├── shippingAddress
  └── lines
        ├── OrderLine
        ├── OrderLine
        └── ...
```

Mô hình này phù hợp cho thao tác nghiệp vụ như xác nhận đơn hàng, thay đổi địa chỉ giao hàng hoặc thêm dòng hàng. Nhưng trang danh sách đơn hàng có thể chỉ cần:

```text
OrderListItem
  ├── orderId
  ├── orderNumber
  ├── customerName
  ├── status
  ├── createdAt
  └── totalAmount
```

Nếu tải từng aggregate đầy đủ để hiển thị danh sách, ứng dụng có thể phải tải các dòng hàng và những property không được hiển thị. Khi số đơn hàng tăng, cách làm này tạo thêm dữ liệu truyền qua JDBC, object được tạo trong JVM và công việc mapping.

Read model cho phép truy vấn đúng cột cần thiết, kết hợp dữ liệu theo nhu cầu màn hình và trả về một cấu trúc đơn giản. Write model vẫn giữ ranh giới aggregate để các thay đổi nghiệp vụ được kiểm soát.

## 2. Write model: aggregate chịu trách nhiệm thay đổi nghiệp vụ

Ví dụ aggregate đơn hàng:

```java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderNumber;
    private String status;

    @MappedCollection(idColumn = "purchase_order_id")
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String orderNumber) {
        this.orderNumber = orderNumber;
        this.status = "DRAFT";
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public String getStatus() {
        return status;
    }

    public List<OrderLine> getLines() {
        return List.copyOf(lines);
    }

    public void addLine(OrderLine line) {
        if (!"DRAFT".equals(status)) {
            throw new IllegalStateException(
                    "Only a draft order can be changed");
        }
        lines.add(line);
    }

    public void confirm() {
        if (lines.isEmpty()) {
            throw new IllegalStateException(
                    "An order must contain at least one line");
        }
        status = "CONFIRMED";
    }
}

public record OrderLine(
        String sku,
        int quantity
) {}
```

Repository ghi:

```java
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
```

Service cập nhật aggregate:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PurchaseOrderCommandService {

    private final PurchaseOrderRepository repository;

    public PurchaseOrderCommandService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public PurchaseOrder confirm(Long orderId) {
        PurchaseOrder order = repository.findById(orderId)
                .orElseThrow();

        order.confirm();

        return repository.save(order);
    }
}
```

Ở đây, service tải aggregate đầy đủ, gọi hành vi domain và lưu root. Việc xác nhận đơn hàng cần biết các dòng hàng để kiểm tra invariant. Đây là công việc của write model.

Spring Data JDBC không dùng persistence context và dirty checking kiểu JPA. Khi gọi `save`, ứng dụng gửi trạng thái aggregate qua repository; vì thế không nên tạo một object chỉ có ID và vài field rồi coi nó là bản cập nhật đầy đủ. Cách đọc aggregate hiện tại, thay đổi qua method domain rồi lưu lại giúp giữ đúng trạng thái và quan hệ con.

## 3. Read model: chỉ trả dữ liệu mà truy vấn cần

Read model thường là một DTO hoặc projection. Nó không cần có toàn bộ hành vi domain, không cần các method thay đổi trạng thái và không nhất thiết tương ứng một bảng.

Ví dụ DTO cho màn hình danh sách:

```java
import java.math.BigDecimal;
import java.time.Instant;

public record OrderListItem(
        Long orderId,
        String orderNumber,
        String customerName,
        String status,
        Instant createdAt,
        BigDecimal totalAmount
) {}
```

DTO có thể kết hợp dữ liệu từ nhiều bảng, tính tổng, đổi tên trường cho API hoặc bỏ các cột không được phép hiển thị. Không cần biến DTO thành aggregate root chỉ vì nó chứa dữ liệu của một đơn hàng.

Một DTO đọc không nên được truyền vào `PurchaseOrderRepository.save`. Nó không phải trạng thái đầy đủ của aggregate và không có trách nhiệm bảo vệ invariant.

## 4. Interface-based projection

Spring Data hỗ trợ projection dựa trên interface cho các query method phù hợp. Interface khai báo các accessor mà ứng dụng muốn đọc:

```java
public interface CustomerSummary {
    Long getId();
    String getFullName();
    String getEmail();
}
```

Repository:

```java
import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    List<CustomerSummary> findByStatus(String status);
}
```

Khi gọi:

```java
List<CustomerSummary> active =
        customerRepository.findByStatus("ACTIVE");

for (CustomerSummary customer : active) {
    System.out.println(customer.getFullName());
}
```

Spring Data tạo projection cho kết quả truy vấn theo các property được khai báo. Interface này là góc nhìn đọc dữ liệu; nó không thay thế entity `Customer` và không phải đối tượng để lưu bằng repository.

### 4.1. Closed projection

Một projection là **closed projection** khi các accessor tương ứng trực tiếp với property của domain type:

```java
public interface CustomerListView {
    Long getId();
    String getFullName();
    String getStatus();
}
```

Framework biết chính xác property nào được yêu cầu. Với query type và module hỗ trợ tối ưu projection, Spring Data có thể giới hạn dữ liệu được chọn vào những property cần thiết. Khả năng tối ưu cụ thể phụ thuộc Spring Data JDBC, loại query và phiên bản; hãy quan sát SQL thực tế thay vì mặc định mọi interface projection luôn làm giảm số cột.

### 4.2. Projection có accessor tính toán

Projection có thể cung cấp method mặc định dựa trên các property đã có:

```java
public interface CustomerNameView {
    String getFirstName();
    String getLastName();

    default String getDisplayName() {
        return getFirstName() + " " + getLastName();
    }
}
```

`getDisplayName()` được tính trong Java từ hai accessor, không phải một cột database. Nếu logic hiển thị đơn giản và chỉ dùng trong read model, default method có thể tiện lợi.

Với biểu thức phụ thuộc SpEL hoặc property không thể xác định tĩnh, projection không còn là closed projection theo nghĩa tối ưu property. Không nên dùng biểu thức động phức tạp để thay thế một truy vấn đọc được thiết kế rõ ràng.

### 4.3. Projection không phải một hợp đồng ghi

Không thêm setter hoặc method thay đổi trạng thái vào projection với kỳ vọng Spring Data JDBC sẽ lưu thay đổi. Projection phục vụ đọc; thao tác ghi phải đi qua aggregate root và repository tương ứng.

## 5. Class-based projection và DTO

Nếu muốn có một kiểu dữ liệu cụ thể thay vì interface proxy, có thể dùng DTO class hoặc Java record:

```java
public record CustomerCard(
        Long id,
        String fullName,
        String email
) {}
```

Một query method tùy chỉnh có thể trả về DTO:

```java
import java.util.List;
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.Repository;
import org.springframework.data.repository.query.Param;

public interface CustomerReadRepository
        extends Repository<Customer, Long> {

    @Query("""
        SELECT id, full_name, email
        FROM customer
        WHERE status = :status
        ORDER BY full_name, id
        """)
    List<CustomerCard> findCardsByStatus(
            @Param("status") String status);
}
```

Với class-based projection, constructor/record component và tên cột trả về cần phù hợp với cơ chế mapping của phiên bản Spring Data Relational đang dùng. Nếu dùng alias, chọn alias tương thích với tên property/constructor parameter; nếu query trả thiếu cột bắt buộc hoặc kiểu dữ liệu không tương thích, mapping có thể thất bại.

Ví dụ SQL trên dùng tên cột PostgreSQL `full_name`, trong khi record có component `fullName`. Hãy xác nhận naming strategy/column mapping của dự án xử lý tên này như mong đợi. Khi cần chắc chắn về phép biến đổi hoặc query rất phức tạp, dùng `JdbcTemplate` với `RowMapper` tường minh là lựa chọn rõ ràng.

### 5.1. DTO projection và truy vấn tùy chỉnh

Một query đọc thường chỉ chọn những cột cần thiết:

```sql
SELECT id, full_name, email
FROM customer
WHERE status = ?
ORDER BY full_name, id;
```

Không cần chọn các cột như password hash, thông tin nội bộ hoặc trường không dùng trên màn hình. Đây vừa là tối ưu dữ liệu truyền, vừa giảm nguy cơ vô tình đưa trường nhạy cảm vào response.

Query tùy chỉnh nên:

- Chỉ chọn các cột DTO cần.
- Đặt alias rõ ràng khi tên cột kết quả cần khác tên trong schema.
- Dùng bind parameter cho giá trị lọc.
- Dùng whitelist nếu cần sort động; không ghép identifier do người dùng gửi vào SQL.
- Kiểm tra kiểu dữ liệu SQL và Java, đặc biệt với số thập phân, ngày giờ và nullable column.

## 6. Khi cần tự kiểm soát ánh xạ: JdbcTemplate và RowMapper

Với báo cáo hoặc truy vấn JOIN nhiều bảng, có thể dùng Spring JDBC trực tiếp để tạo DTO. Cách này đặc biệt hữu ích khi kết quả không tương ứng một aggregate duy nhất.

Ví dụ DTO:

```java
import java.math.BigDecimal;

public record OrderListItem(
        Long orderId,
        String orderNumber,
        String customerName,
        String status,
        BigDecimal totalAmount
) {}
```

Repository đọc:

```java
import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderReadDao {

    private final JdbcTemplate jdbcTemplate;

    public OrderReadDao(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public List<OrderListItem> findOrderCards(String status) {
        String sql = """
            SELECT
                o.id AS order_id,
                o.order_number,
                c.full_name AS customer_name,
                o.status,
                COALESCE(SUM(l.quantity * l.unit_price), 0) AS total_amount
            FROM purchase_order o
            JOIN customer c ON c.id = o.customer_id
            LEFT JOIN order_line l ON l.purchase_order_id = o.id
            WHERE o.status = ?
            GROUP BY o.id, o.order_number, c.full_name, o.status
            ORDER BY o.id DESC
            """;

        return jdbcTemplate.query(sql, (rs, rowNum) ->
                new OrderListItem(
                        rs.getLong("order_id"),
                        rs.getString("order_number"),
                        rs.getString("customer_name"),
                        rs.getString("status"),
                        rs.getBigDecimal("total_amount")
                ),
                status
        );
    }
}
```

SQL trên là ví dụ PostgreSQL; schema cần có `customer_id` trên bảng đơn hàng và `unit_price`, `quantity` trên bảng dòng hàng. `JdbcTemplate` bind `status` qua tham số `?`, còn `RowMapper` chuyển từng hàng result set thành `OrderListItem`.

Ở đây một dòng kết quả là một card đọc, không phải một `PurchaseOrder` aggregate cần được lưu lại. DTO được dựng trực tiếp từ dữ liệu JOIN và phép tổng hợp.

### 6.1. Cẩn thận với JOIN một-nhiều

Nếu một đơn hàng có nhiều dòng hàng, JOIN tạo nhiều hàng kết quả cho cùng một root. Khi DTO chỉ cần tổng tiền, dùng `GROUP BY` và phép tổng hợp như `SUM`. Nếu DTO cần danh sách các dòng hàng lồng nhau, một `RowMapper` đơn giản theo từng hàng sẽ tạo nhiều DTO trùng root; cần nhóm theo ID trong một `ResultSetExtractor` hoặc dùng nhiều truy vấn có chủ đích rồi ghép kết quả.

Không nên tự ánh xạ một result set phẳng thành aggregate update model nếu query không cung cấp đủ dữ liệu và quy tắc domain để tái tạo aggregate.

## 7. Dynamic projection

Spring Data Commons hỗ trợ dynamic projection cho một số query method: caller truyền kiểu projection cần nhận. Ví dụ tổng quát:

```java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    <T> List<T> findByStatus(String status, Class<T> projectionType);
}
```

Có thể gọi:

```java
List<Customer> entities =
        repository.findByStatus("ACTIVE", Customer.class);

List<CustomerSummary> summaries =
        repository.findByStatus("ACTIVE", CustomerSummary.class);
```

Điều này cho phép cùng một điều kiện lọc trả về kiểu nhìn khác nhau. Tuy nhiên, dynamic projection phụ thuộc query derivation, projection type và hỗ trợ của phiên bản Spring Data JDBC. Không phải mọi custom query hoặc mapping phức tạp đều có thể đổi target type tùy ý. Nếu dự án không hỗ trợ signature này cho query cụ thể, khai báo các method đọc riêng có return type tường minh.

Khi có nhiều kiểu đọc khác nhau, đừng biến dynamic projection thành một API tùy ý không kiểm soát. Chỉ cung cấp projection mà tầng ứng dụng có lý do sử dụng.

## 8. Tổ chức repository và service theo hướng đọc/ghi

Có thể tách repository ghi aggregate và thành phần truy vấn đọc:

```java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
```

```java
public interface OrderReadRepository {
    List<OrderListItem> findOrderCards(String status);
}
```

Service ghi:

```java
@Service
public class OrderCommandService {

    private final PurchaseOrderRepository repository;

    public OrderCommandService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public PurchaseOrder confirm(Long id) {
        PurchaseOrder order = repository.findById(id).orElseThrow();
        order.confirm();
        return repository.save(order);
    }
}
```

Service đọc:

```java
@Service
public class OrderQueryService {

    private final OrderReadRepository readRepository;

    public OrderQueryService(OrderReadRepository readRepository) {
        this.readRepository = readRepository;
    }

    public List<OrderListItem> list(String status) {
        return readRepository.findOrderCards(status);
    }
}
```

`OrderReadRepository` ở ví dụ là interface do ứng dụng định nghĩa; có thể được implement bằng `JdbcTemplate`, Spring Data repository projection hoặc một công nghệ đọc phù hợp. Mục tiêu là để controller gọi đúng use case:

- Command service nhận lệnh và thay đổi aggregate.
- Query service trả projection/DTO phục vụ đọc.

Với dự án nhỏ, không nhất thiết tạo nhiều module hoặc nhiều tầng class chỉ vì có DTO. Có thể đặt query method projection ngay trên repository hiện tại. Tách riêng khi truy vấn đọc có nhu cầu, SQL hoặc vòng đời khác rõ rệt.

## 9. Phân trang cho read model

Màn hình danh sách thường cần pagination. Có thể kết hợp projection với `Pageable` nếu repository method và phiên bản hỗ trợ:

```java
Page<CustomerSummary> findByStatus(
        String status,
        Pageable pageable
);
```

Caller:

```java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Order.desc("createdAt"), Sort.Order.asc("id"))
);

Page<CustomerSummary> page =
        repository.findByStatus("ACTIVE", pageable);
```

Khi dùng projection, vẫn phải sắp xếp theo property persistent hợp lệ. Nếu projection chỉ có `id`, `fullName` và `status` nhưng sort theo `createdAt`, cần xác nhận query/mapping cho phép sort property đó dù nó không nằm trong projection output. Với custom SQL, hãy tự khai báo `ORDER BY` và cú pháp phân trang phù hợp dialect.

Nếu client chỉ cần "còn trang tiếp theo không", cân nhắc `Slice<T>` thay cho `Page<T>` khi query type hỗ trợ; `Page` thường cần tổng số phần tử và có thể phát sinh count query.

## 10. DTO không tự động bảo đảm query chỉ đọc ít cột

Một nhầm lẫn phổ biến là cho rằng chỉ cần đổi return type từ entity sang DTO thì database chắc chắn chỉ gửi các cột DTO cần.

Cần phân biệt:

1. **Kiểu kết quả:** projection/DTO quyết định cấu trúc object trả về.
2. **SQL projection:** mệnh đề `SELECT` quyết định database trả về cột nào.
3. **Mapping optimization:** Spring Data có thể tối ưu lựa chọn cột cho các loại projection được hỗ trợ.

Với query tùy chỉnh, bạn kiểm soát danh sách cột trong `SELECT`. Với derived query, framework có thể tối ưu closed projection tùy module/phiên bản. Luôn quan sát SQL thực tế nếu mục tiêu là giảm dữ liệu truyền.

Đặc biệt, nếu custom query dùng `SELECT *` rồi map vào DTO, database vẫn trả tất cả cột được chọn bởi dấu sao, dù DTO chỉ giữ ba trường. Hãy liệt kê cột cần thiết:

```sql
-- Tránh nếu chỉ cần ba trường:
SELECT *
FROM customer
WHERE status = ?;

-- Chọn đúng cột cần:
SELECT id, full_name, email
FROM customer
WHERE status = ?;
```

## 11. Nhất quán dữ liệu giữa đường đọc và đường ghi

Tách read model và write model không có nghĩa dữ liệu tự động đồng bộ qua event. Nếu cả hai dùng cùng database quan hệ, query đọc thường thấy dữ liệu đã commit theo isolation level của transaction.

Một luồng đơn giản:

```text
Command API
    │
    ▼
Command Service
    │ load aggregate
    ▼
Aggregate Root ── domain behavior
    │
    ▼
Repository.save(root)
    │
    ▼
Transaction commit
    │
    ▼
Relational database
    ▲
    │ query projection / DTO
    │
Query Service
    ▲
    │
Read API
```

Khi read query chạy sau khi transaction ghi đã commit, nó đọc trạng thái đã commit theo transaction/isolation phù hợp. Nếu query đọc trong một transaction khác đang chạy đồng thời, kết quả phụ thuộc isolation level và thời điểm truy vấn.

Nếu sau này tách read model sang database/search index riêng, việc cập nhật thường dựa trên event/message hoặc pipeline đồng bộ. Khi đó có thể xuất hiện **eventual consistency**: command đã thành công nhưng read model chưa cập nhật ngay. Đây là một quyết định kiến trúc lớn hơn việc dùng projection; cần có cơ chế retry, idempotency, theo dõi lag và xử lý lỗi đồng bộ.

## 12. Bảo mật và ranh giới dữ liệu API

Projection/DTO là cơ hội tốt để giới hạn dữ liệu được phép trả về. Entity có thể chứa thông tin nội bộ như:

- Password hash hoặc credential metadata.
- Ghi chú nội bộ, cờ kiểm soát rủi ro.
- Dữ liệu cá nhân không cần cho màn hình.
- Trường kỹ thuật phục vụ persistence.

Không trả entity trực tiếp chỉ vì nó đã có sẵn. Tạo read DTO chỉ chứa các trường API được phép công khai:

```java
public record CustomerPublicView(
        Long id,
        String displayName
) {}
```

Projection không thay thế authorization. Query vẫn phải giới hạn dữ liệu theo tenant, người dùng, vai trò và quyền truy cập. Ví dụ:

```sql
SELECT id, full_name
FROM customer
WHERE tenant_id = ?
  AND status = ?;
```

Không chỉ lọc ở Java sau khi tải toàn bộ dữ liệu. Đưa điều kiện quyền truy cập vào query phù hợp và kiểm tra quyền ở service/controller theo thiết kế bảo mật của ứng dụng.

## 13. Khi nào chọn projection, DTO hay aggregate?

| Nhu cầu | Lựa chọn phù hợp |
| --- | --- |
| Thay đổi trạng thái đơn hàng và kiểm tra invariant | Load aggregate root, gọi domain behavior, save root |
| Danh sách chỉ cần vài property của một entity | Interface projection hoặc DTO projection |
| Báo cáo kết hợp nhiều bảng, aggregate function | DTO với custom query/`JdbcTemplate` |
| Màn hình chi tiết cần toàn bộ hành vi và quan hệ aggregate | Aggregate root có thể phù hợp |
| Dữ liệu API cần loại bỏ trường nội bộ | Response DTO/projection giới hạn trường |
| Nhiều kiểu hiển thị từ cùng điều kiện lọc | Dynamic projection nếu query/module hỗ trợ |
| Truy vấn rất phức tạp hoặc cần SQL tối ưu riêng | Query DAO đọc chuyên biệt và DTO |

Đừng tạo một aggregate mới chỉ để chứa kết quả báo cáo. Đừng dùng DTO đọc để ghi. Và đừng tách read/write thành hai database nếu nhu cầu hiện tại chỉ là tránh tải dư thừa.

## 14. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Projection getter trả null | Tên accessor không khớp property hoặc alias kết quả | Đối chiếu property Java, column alias và mapping |
| DTO constructor không được gọi đúng | Tên/thứ tự tham số hoặc kiểu dữ liệu không khớp | Kiểm tra constructor/record component và cột trả về |
| DTO vẫn tải nhiều cột | Query dùng `SELECT *` hoặc projection không được tối ưu | Chọn cột tường minh và quan sát SQL |
| JOIN tạo nhiều DTO trùng root | Quan hệ một-nhiều làm result set lặp root | GROUP BY/aggregate hoặc nhóm rows bằng extractor |
| Gọi `save` với DTO không hoạt động | DTO không phải aggregate entity | Đọc root và cập nhật qua domain behavior |
| Read API thấy dữ liệu cũ | Transaction chưa commit, isolation hoặc read store riêng chưa đồng bộ | Xác định transaction boundary và mô hình đồng bộ |
| Projection sort không chạy | Sort dùng tên cột thay property hoặc property không hợp lệ | Dùng property persistent hoặc khai báo ORDER BY trong custom SQL |
| Projection làm lộ trường không mong muốn | Return entity/DTO chứa quá nhiều field | Tạo DTO giới hạn dữ liệu và kiểm tra authorization |

## 15. Bài tập thực hành

**Bài 1 — Tách command và query.** Dùng `PurchaseOrderRepository` để tải và xác nhận đơn hàng. Tạo một query service riêng trả danh sách đơn hàng theo trạng thái.

**Bài 2 — Interface projection.** Tạo `CustomerSummary` chỉ có ID, tên và email. Khai báo derived query trả `List<CustomerSummary>` và gọi từ service.

**Bài 3 — DTO projection.** Tạo record `CustomerCard` và query tùy chỉnh chỉ chọn ID, tên, email. Kiểm tra mapping column/constructor trong phiên bản Spring Data JDBC của dự án.

**Bài 4 — JOIN read model.** Dùng `JdbcTemplate` để tạo `OrderListItem` gồm tên khách hàng và tổng tiền. Xác nhận một đơn hàng có nhiều dòng hàng chỉ tạo một card nhờ `GROUP BY`.

**Bài 5 — Pagination.** Trả projection có `Pageable`; so sánh `Page` và `Slice` về metadata và số câu SQL được thực hiện.

**Bài 6 — Bảo mật response.** Thêm một trường nội bộ vào entity nhưng không đưa vào DTO public. Kiểm tra JSON response không chứa trường đó và query có điều kiện tenant phù hợp.

### Tài liệu tham khảo

- [Spring Data Commons — Projections](https://docs.spring.io/spring-data/commons/reference/repositories/projections.html): interface-based, class-based và dynamic projections.
- [Spring Data Relational — JDBC Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html): query methods và projection trong Spring Data JDBC.
- [Spring Data Relational — JDBC Repositories](https://docs.spring.io/spring-data/relational/reference/jdbc/repositories.html): repository abstraction và truy cập aggregate trong Spring Data JDBC.
