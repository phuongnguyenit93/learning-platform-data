# Chọn template hay JDBC trực tiếp cho thao tác ngoài mô hình aggregate

## 1. Bài toán: khi repository và aggregate không còn là cách truy cập phù hợp

Spring Data JDBC tổ chức việc ghi dữ liệu quanh aggregate root. Repository của một aggregate là nơi tự nhiên để tạo, đọc, cập nhật và xóa aggregate cùng các đối tượng con thuộc quyền sở hữu của nó. Mô hình này giúp bảo vệ invariant và làm rõ ranh giới nhất quán.

Tuy nhiên, không phải mọi thao tác dữ liệu trong ứng dụng đều là thao tác trên aggregate:

- Một báo cáo cần tổng hợp dữ liệu từ nhiều bảng và nhiều aggregate.
- Một màn hình chỉ cần vài cột để hiển thị danh sách.
- Một tác vụ quản trị cần cập nhật hàng loạt theo điều kiện SQL.
- Một job cần ghi staging table hoặc đọc dữ liệu phục vụ đối soát.
- Một truy vấn phân tích cần JOIN, GROUP BY, CTE hoặc hàm cửa sổ.

Trong những trường hợp đó, cố ép mọi thao tác qua repository của một aggregate có thể làm mô hình khó hiểu và truy vấn kém phù hợp. Spring cung cấp nhiều mức truy cập dữ liệu. Với Spring Data JDBC, hai lựa chọn cần phân biệt là:

- **JdbcAggregateTemplate:** làm việc ở mức aggregate, sử dụng mapping và persistence semantics của Spring Data JDBC.
- **JdbcTemplate hoặc NamedParameterJdbcTemplate:** làm việc trực tiếp với SQL và hàng/cột của database.

Tên gọi đều có chữ “template”, nhưng hai công cụ giải quyết hai loại bài toán khác nhau. JdbcAggregateTemplate là API thao tác aggregate không cần thông qua repository interface. JdbcTemplate là API JDBC tổng quát, phù hợp với truy vấn và cập nhật không được biểu diễn tự nhiên như thao tác aggregate.

Bài này giúp xác định nên dùng công cụ nào, cách phối hợp chúng trong transaction và những rủi ro khi SQL trực tiếp thay đổi dữ liệu thuộc một aggregate.

## 2. Hai mức trừu tượng khác nhau

### 2.1. JdbcAggregateTemplate làm việc với aggregate

JdbcAggregateTemplate là API mức thấp hơn repository nhưng vẫn giữ mô hình aggregate của Spring Data JDBC. Nó sử dụng metadata mapping để lưu và tải aggregate root, xử lý quan hệ với các đối tượng con theo mapping đã khai báo.

Ví dụ, một đơn hàng gồm root và các dòng hàng:

~~~text
PurchaseOrder
  id
  orderNumber
  status
  lines
    - PurchaseOrderLine
    - PurchaseOrderLine
~~~

Khi lưu đơn hàng bằng JdbcAggregateTemplate, ứng dụng đưa vào một aggregate object. Spring Data JDBC xử lý bảng root và các bảng con theo mapping. Caller không phải tự viết SQL cho từng bảng con hoặc tự gán khóa ngoại và index collection.

Ví dụ:

~~~java
import org.springframework.data.jdbc.core.JdbcAggregateTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PurchaseOrderWriter {

    private final JdbcAggregateTemplate aggregateTemplate;

    public PurchaseOrderWriter(JdbcAggregateTemplate aggregateTemplate) {
        this.aggregateTemplate = aggregateTemplate;
    }

    @Transactional
    public PurchaseOrder create(PurchaseOrder order) {
        return aggregateTemplate.insert(order);
    }

    @Transactional
    public PurchaseOrder change(PurchaseOrder order) {
        return aggregateTemplate.update(order);
    }

    @Transactional
    public void remove(PurchaseOrder order) {
        aggregateTemplate.delete(order);
    }
}
~~~

Các phương thức minh họa thao tác ở mức aggregate. Tên và chữ ký API cụ thể cần đối chiếu phiên bản Spring Data Relational của dự án, nhưng nguyên tắc không đổi: template nhận aggregate object và thực hiện persistence theo mapping của aggregate đó.

Nếu ứng dụng đã có repository interface rõ ràng, hãy tiếp tục dùng repository cho các thao tác CRUD thông thường. JdbcAggregateTemplate hữu ích khi cần gọi trực tiếp API aggregate, chẳng hạn trong một adapter hoặc một thành phần infrastructure không cần thêm repository interface.

### 2.2. JdbcTemplate làm việc với câu SQL và hàng dữ liệu

JdbcTemplate không hiểu khái niệm aggregate root, ownership hoặc invariant trong domain model. Nó thực thi SQL, bind tham số, đọc ResultSet và ánh xạ kết quả thành kiểu Java mà ứng dụng chỉ định.

Ví dụ truy vấn tổng số lượng hàng tồn theo SKU:

~~~java
public record StockSummary(String sku, long totalAvailable) {
}

@Repository
public class StockReportDao {

    private final JdbcTemplate jdbcTemplate;

    public StockReportDao(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public List<StockSummary> summarize() {
        String sql = """
                SELECT sku, SUM(available) AS total_available
                FROM inventory
                GROUP BY sku
                ORDER BY sku
                """;

        return jdbcTemplate.query(
                sql,
                (rs, rowNum) -> new StockSummary(
                        rs.getString("sku"),
                        rs.getLong("total_available")
                )
        );
    }
}
~~~

Kết quả là một projection dành cho báo cáo. Không cần dựng từng aggregate Inventory chỉ để tính tổng số lượng. DAO sở hữu câu SQL và cách ánh xạ hàng kết quả; nó không trở thành repository của một aggregate.

## 3. So sánh nhanh

| Tiêu chí | JdbcAggregateTemplate | JdbcTemplate / NamedParameterJdbcTemplate |
| --- | --- | --- |
| Mức làm việc | Aggregate root | SQL, bảng, hàng và cột |
| Mapping | Dùng mapping metadata của Spring Data JDBC | Caller cung cấp RowMapper, ResultSetExtractor hoặc kiểu ánh xạ khác |
| Quan hệ đối tượng con | Xử lý theo aggregate mapping | Caller tự viết JOIN/INSERT/UPDATE/DELETE |
| Invariant domain | Có thể đi qua hành vi aggregate trước khi gọi template; template không tự thay thế validation domain | Không biết invariant; caller phải bảo đảm |
| SQL | Framework tạo SQL theo mapping | Caller viết SQL |
| Báo cáo nhiều bảng | Không phải mục đích chính | Phù hợp |
| Bulk DML | Thao tác theo aggregate | Phù hợp khi cần SQL cập nhật hàng loạt |
| CRUD aggregate thông thường | Có thể dùng | Thường không nên tự viết lại |
| Tối ưu projection | Không phải lựa chọn tự nhiên nếu không cần aggregate đầy đủ | Có thể chỉ chọn các cột cần thiết |
| Phụ thuộc Spring Data mapping | Có | Không bắt buộc |

Hãy dùng JdbcAggregateTemplate khi đối tượng được thao tác là một aggregate. Dùng JDBC trực tiếp khi use case thực sự làm việc với dữ liệu ở mức hàng, báo cáo, staging hoặc câu SQL đặc thù.

## 4. Khi nào repository là lựa chọn tốt nhất?

Trước khi chọn template, hãy xem repository interface đã đáp ứng chưa. Repository thể hiện rõ aggregate mà use case làm việc và cung cấp một contract ổn định cho application service.

Ví dụ:

~~~java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    List<PurchaseOrder> findByStatus(OrderStatus status);
}
~~~

Service dùng repository:

~~~java
@Service
public class OrderApplicationService {

    private final PurchaseOrderRepository orders;

    public OrderApplicationService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public void approve(Long id) {
        PurchaseOrder order = orders.findById(id).orElseThrow();
        order.approve();
        orders.save(order);
    }
}
~~~

Đây là luồng phù hợp khi nghiệp vụ cần tải aggregate, gọi hành vi domain và lưu lại trạng thái. Không cần chuyển sang JdbcAggregateTemplate chỉ vì muốn tránh khai báo repository; repository thường là abstraction dễ hiểu hơn cho application code.

## 5. Khi nào dùng JdbcAggregateTemplate thay repository?

JdbcAggregateTemplate có thể phù hợp khi:

- Một adapter infrastructure cần thao tác trực tiếp trên aggregate nhưng không cần một repository interface riêng.
- Một thành phần cần chọn kiểu aggregate lúc chạy và muốn gọi API aggregate tổng quát.
- Cần sử dụng các thao tác insert/update/delete/find ở mức aggregate trong một thành phần kỹ thuật.
- Muốn viết một abstraction dùng chung cho một số aggregate nhưng vẫn giữ persistence semantics của Spring Data JDBC.

Ví dụ một importer tạo aggregate từ dữ liệu đã được kiểm tra:

~~~java
@Service
public class CatalogImporter {

    private final JdbcAggregateTemplate aggregates;

    public CatalogImporter(JdbcAggregateTemplate aggregates) {
        this.aggregates = aggregates;
    }

    @Transactional
    public Product importProduct(Product product) {
        // Product đã được chuẩn hóa và kiểm tra ở application/domain layer.
        return aggregates.insert(product);
    }
}
~~~

Template không tự biến dữ liệu nhập thành dữ liệu hợp lệ. Importer vẫn phải kiểm tra đầu vào, tạo aggregate qua factory phù hợp và gọi hành vi domain để bảo đảm invariant. JdbcAggregateTemplate chịu trách nhiệm persistence theo mapping.

### Template không phải SQL builder

Không dùng JdbcAggregateTemplate để mong viết một câu SQL tùy ý như:

~~~sql
SELECT category, COUNT(*)
FROM products
GROUP BY category;
~~~

Đó là truy vấn theo bảng và projection; JdbcTemplate hoặc một query abstraction phù hợp là công cụ tự nhiên hơn.

## 6. Khi nào dùng JdbcTemplate hoặc NamedParameterJdbcTemplate?

### 6.1. Báo cáo và projection

Một báo cáo có thể kết hợp nhiều bảng mà không cần trả về aggregate:

~~~java
public record MonthlySales(
        int year,
        int month,
        BigDecimal revenue
) {
}

@Repository
public class SalesReportDao {

    private final JdbcTemplate jdbc;

    public SalesReportDao(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<MonthlySales> byMonth(int year) {
        String sql = """
                SELECT EXTRACT(YEAR FROM paid_at) AS sales_year,
                       EXTRACT(MONTH FROM paid_at) AS sales_month,
                       SUM(total_amount) AS revenue
                FROM payments
                WHERE EXTRACT(YEAR FROM paid_at) = ?
                  AND status = ?
                GROUP BY EXTRACT(YEAR FROM paid_at),
                         EXTRACT(MONTH FROM paid_at)
                ORDER BY sales_month
                """;

        return jdbc.query(
                sql,
                (rs, rowNum) -> new MonthlySales(
                        rs.getInt("sales_year"),
                        rs.getInt("sales_month"),
                        rs.getBigDecimal("revenue")
                ),
                year,
                "PAID"
        );
    }
}
~~~

SQL dùng hàm EXTRACT minh họa một dialect có hỗ trợ cú pháp này. Khi triển khai, kiểm tra hàm ngày giờ và kiểu kết quả trên database đích. Điểm chính là DAO chỉ lấy dữ liệu cần cho báo cáo thay vì tải toàn bộ Payment aggregate.

### 6.2. Cập nhật hàng loạt

Khi cần đánh dấu nhiều hàng theo điều kiện, JDBC trực tiếp có thể đơn giản hơn việc tải từng aggregate rồi save:

~~~java
@Repository
public class CustomerMaintenanceDao {

    private final JdbcTemplate jdbc;

    public CustomerMaintenanceDao(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int deactivateInactiveCustomers(LocalDate cutoff) {
        return jdbc.update("""
                UPDATE customers
                SET active = false
                WHERE last_seen < ?
                  AND active = true
                """, cutoff);
    }
}
~~~

Đây là thao tác row-oriented. Nó không gọi hành vi của từng Customer aggregate và không tự phát hiện optimistic-locking version. Chỉ dùng khi quy tắc nghiệp vụ cho phép cập nhật trực tiếp và các invariant cần thiết được bảo vệ bằng điều kiện SQL, constraint hoặc quy trình ứng dụng.

### 6.3. NamedParameterJdbcTemplate cho câu SQL nhiều tham số

Khi có nhiều điều kiện, named parameter giúp câu SQL dễ đọc:

~~~java
@Repository
public class InventorySearchDao {

    private final NamedParameterJdbcTemplate jdbc;

    public InventorySearchDao(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<InventoryRow> findBelowThreshold(
            String warehouse,
            int threshold
    ) {
        String sql = """
                SELECT id, sku, available
                FROM inventory
                WHERE warehouse_code = :warehouse
                  AND available < :threshold
                ORDER BY id
                """;

        MapSqlParameterSource parameters = new MapSqlParameterSource()
                .addValue("warehouse", warehouse)
                .addValue("threshold", threshold);

        return jdbc.query(
                sql,
                parameters,
                (rs, rowNum) -> new InventoryRow(
                        rs.getLong("id"),
                        rs.getString("sku"),
                        rs.getInt("available")
                )
        );
    }
}
~~~

Named parameter làm rõ mỗi giá trị được dùng ở đâu. Cả JdbcTemplate lẫn NamedParameterJdbcTemplate đều bind giá trị qua JDBC; không nối input vào SQL bằng phép ghép chuỗi.

## 7. Ranh giới aggregate không biến mất khi dùng JDBC trực tiếp

Một aggregate root bảo vệ invariant của nhóm dữ liệu được sở hữu. Nếu một bảng con là một phần của aggregate, thao tác trực tiếp lên bảng con có thể phá vỡ trạng thái mà domain model kỳ vọng.

Ví dụ:

~~~text
PurchaseOrder
  status = DRAFT
  lines
    - sku = BOOK-01, quantity = 2
    - sku = PEN-02, quantity = 5
~~~

Giả sử aggregate có quy tắc:

- Chỉ đơn nháp mới được thay đổi dòng hàng.
- Tổng số lượng phải lớn hơn 0.
- Mỗi SKU chỉ xuất hiện một lần trong đơn.
- Khi đơn được gửi, phải ghi nhận thời điểm gửi và không được sửa dòng hàng nữa.

Một câu SQL trực tiếp cập nhật purchase_order_lines.quantity không gọi các quy tắc đó. Dữ liệu có thể thay đổi dù đơn hàng đã gửi hoặc tạo ra một trạng thái domain không hợp lệ.

Với thao tác thuộc aggregate, ưu tiên:

1. Tải aggregate root.
2. Gọi hành vi domain.
3. Lưu aggregate bằng repository hoặc JdbcAggregateTemplate.

Chỉ dùng SQL trực tiếp để thay đổi các hàng thuộc aggregate khi có lý do rõ ràng, ví dụ maintenance/bulk operation đã được thiết kế riêng, có điều kiện bảo vệ invariant, xử lý version và kiểm thử trên database thật.

## 8. Transaction khi phối hợp template và JDBC trực tiếp

JdbcAggregateTemplate, JdbcTemplate và NamedParameterJdbcTemplate có thể tham gia cùng transaction nếu chúng dùng cùng DataSource và transaction manager tương ứng.

Ví dụ một use case ghi aggregate và một bản ghi audit:

~~~java
@Service
public class OrderRegistrationService {

    private final JdbcAggregateTemplate aggregates;
    private final JdbcTemplate jdbc;

    public OrderRegistrationService(
            JdbcAggregateTemplate aggregates,
            JdbcTemplate jdbc
    ) {
        this.aggregates = aggregates;
        this.jdbc = jdbc;
    }

    @Transactional
    public PurchaseOrder register(PurchaseOrder order) {
        PurchaseOrder saved = aggregates.insert(order);

        jdbc.update("""
                INSERT INTO order_audit(order_id, action)
                VALUES (?, ?)
                """,
                saved.id(),
                "CREATED"
        );

        return saved;
    }
}
~~~

Nếu cả hai template dùng cùng transaction-bound DataSource, thao tác insert aggregate và insert audit nằm trong cùng transaction. Nếu insert audit thất bại và exception làm transaction rollback, thao tác insert aggregate cũng được rollback.

Không mặc định điều này đúng nếu các template được cấu hình với hai DataSource khác nhau. Khi ứng dụng có nhiều database, cần transaction manager phù hợp cho từng resource hoặc thiết kế cơ chế phối hợp riêng. Một @Transactional thông thường không tạo distributed transaction tự động.

## 9. Đừng trộn direct update với một aggregate cũ trong bộ nhớ

Một rủi ro khi dùng cả hai mức truy cập là object aggregate trong bộ nhớ có thể trở nên cũ sau câu SQL trực tiếp.

Ví dụ:

1. Service tải PurchaseOrder với status DRAFT.
2. Một DAO dùng JdbcTemplate đổi status trong database thành CANCELLED.
3. Service tiếp tục sửa object PurchaseOrder cũ và gọi repository.save(order).

Object trong bộ nhớ vẫn mang status DRAFT. Khi lưu, nó có thể ghi lại trạng thái cũ hoặc tạo ra kết quả không mong muốn tùy mapping và version strategy.

Nếu một câu SQL trực tiếp thay đổi dữ liệu của aggregate:

- Tránh tiếp tục lưu một instance aggregate cũ mà không đồng bộ lại.
- Tải lại aggregate sau thao tác trực tiếp nếu cần tiếp tục xử lý nó.
- Cân nhắc optimistic locking/version để phát hiện ghi cạnh tranh.
- Tốt nhất, tránh hai đường ghi độc lập cho cùng một aggregate nếu không có quy tắc phối hợp rõ ràng.

Spring Data JDBC không có persistence context/identity map kiểu JPA, nhưng điều đó không làm object Java đã tải tự cập nhật khi một JdbcTemplate khác thay đổi database.

## 10. Optimistic locking và SQL trực tiếp

Nếu aggregate dùng @Version, đường lưu aggregate có thể kiểm tra version và tăng version theo cơ chế Spring Data JDBC. Một câu UPDATE viết bằng JdbcTemplate không tự động áp dụng logic đó.

Nếu direct update cần tuân thủ optimistic locking, đưa version mong đợi vào điều kiện và tăng version trong cùng câu lệnh:

~~~sql
UPDATE purchase_orders
SET status = :newStatus,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion;
~~~

Sau khi chạy, kiểm tra row count:

- 1 hàng: cập nhật thành công theo version đã đọc.
- 0 hàng: aggregate không tồn tại hoặc version không còn khớp.

Đây là SQL minh họa. Kiểu version, tên cột và cách tăng version phải phù hợp schema. Nếu có nhiều đường ghi, tất cả phải tuân theo cùng một quy ước version; nếu không, optimistic locking sẽ không còn đáng tin cậy.

## 11. Lifecycle callback và domain event

Các thao tác aggregate của Spring Data JDBC có thể tham gia các callback/event lifecycle do Spring Data cung cấp. Khi chuyển sang JdbcTemplate, ứng dụng chỉ thực thi SQL và ánh xạ kết quả; nó không tự gọi quy trình aggregate persistence.

Nếu ứng dụng dựa vào callback để:

- Chuẩn hóa dữ liệu trước khi lưu.
- Tạo metadata hoặc audit.
- Phát hiện thời điểm aggregate được lưu.
- Tạo outbox event.

thì direct SQL có thể bỏ qua những bước đó. Không nên giả định một câu jdbc.update(...) sẽ phát ra cùng lifecycle event như JdbcAggregateTemplate.insert(...) hoặc repository save.

Với nghiệp vụ cần phát sự kiện sau khi commit, cân nhắc ghi outbox row trong cùng transaction. Đừng gửi message hoặc gọi API bên ngoài trước khi transaction database hoàn tất nếu hệ thống cần nhất quán giữa dữ liệu và thông điệp.

## 12. Batch operation và SimpleJdbcInsert

JDBC trực tiếp cũng phù hợp với staging, import hoặc batch maintenance khi thao tác không đại diện cho một aggregate đầy đủ.

Ví dụ batch update:

~~~java
public int[] markProcessed(List<Long> ids) {
    String sql = """
            UPDATE import_staging
            SET processed = true
            WHERE id = ?
            """;

    return jdbcTemplate.batchUpdate(
            sql,
            ids,
            500,
            (ps, id) -> ps.setLong(1, id)
    );
}
~~~

Batch size và số lệnh được gửi phụ thuộc driver. Với batch lớn, cân nhắc chia transaction thành từng lô nếu nghiệp vụ cho phép commit từng phần, đồng thời lưu checkpoint và thiết kế retry idempotent.

Khi cần insert đơn giản và muốn hỗ trợ generated key, Spring JDBC còn có tiện ích như SimpleJdbcInsert. Đây vẫn là thao tác ở mức bảng/hàng; nó không thay thế aggregate mapping hoặc bảo vệ invariant domain.

## 13. An toàn SQL và quản lý identifier

Với JdbcTemplate, giá trị đầu vào phải được truyền dưới dạng bind parameter:

~~~java
jdbcTemplate.update(
        "UPDATE customers SET active = ? WHERE id = ?",
        false,
        customerId
);
~~~

Không ghép dữ liệu từ request vào SQL:

~~~java
// Không an toàn: input trở thành một phần của câu SQL.
String sql = "SELECT * FROM customers WHERE name = '" + name + "'";
~~~

Bind parameter bảo vệ giá trị, nhưng không thể thay tên bảng, tên cột hoặc từ khóa SQL. Nếu cần chọn một cột sắp xếp, hãy ánh xạ input sang danh sách cố định:

~~~java
String orderColumn = switch (sortField) {
    case "name" -> "name";
    case "created" -> "created_at";
    default -> throw new IllegalArgumentException("Unsupported sort field");
};

String sql = "SELECT id, name FROM customers ORDER BY " + orderColumn;
~~~

Identifier được chọn từ whitelist do code kiểm soát, còn giá trị lọc vẫn được bind riêng.

## 14. Đặt JDBC trực tiếp ở đâu trong kiến trúc?

Không nên để controller gọi JdbcTemplate trực tiếp. Tạo một adapter/DAO có trách nhiệm rõ ràng:

~~~text
Controller
    |
    v
Application service
    |                 \
    v                  v
Aggregate repository  Report DAO
    |                  |
    v                  v
JdbcAggregateTemplate JdbcTemplate
    |                  |
    +--------+---------+
             |
             v
          Database
~~~

Ví dụ:

- PurchaseOrderRepository: thao tác aggregate PurchaseOrder.
- PurchaseOrderReportDao: SQL JOIN và projection cho báo cáo.
- InventoryMaintenanceDao: bulk update được thiết kế riêng.
- OrderApplicationService: điều phối transaction và quy tắc use case.

Tên DAO nên mô tả mục đích dữ liệu, tránh tạo một lớp DatabaseHelper chứa mọi câu SQL của toàn hệ thống.

## 15. Bảng quyết định

| Câu hỏi | Lựa chọn nên xem xét |
| --- | --- |
| Tôi đang tạo/sửa/xóa một aggregate root? | Repository trước; JdbcAggregateTemplate khi cần API aggregate trực tiếp |
| Tôi cần lưu cả aggregate và các object con theo mapping? | Repository hoặc JdbcAggregateTemplate |
| Tôi chỉ cần vài cột để báo cáo? | JdbcTemplate/NamedParameterJdbcTemplate |
| Tôi cần JOIN/GROUP BY/CTE hoặc SQL đặc thù? | JdbcTemplate hoặc công cụ SQL phù hợp |
| Tôi cần cập nhật hàng loạt theo điều kiện? | JDBC trực tiếp, kèm transaction, row count và bảo vệ invariant |
| Tôi cần thao tác staging/import không phải aggregate? | JDBC trực tiếp |
| Tôi cần bảo vệ hành vi domain và version? | Tải aggregate, gọi hành vi và lưu qua repository/template |
| Tôi cần một transaction gồm aggregate write và audit row? | Application service với @Transactional và cùng transaction manager |

## 16. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| SQL trực tiếp làm aggregate mất invariant | Bỏ qua hành vi domain và điều kiện nghiệp vụ | Dùng aggregate operation hoặc đưa điều kiện/constraint cần thiết vào SQL |
| Dữ liệu con không đồng bộ với root | Ghi trực tiếp child table mà không cập nhật quan hệ/position liên quan | Để aggregate mapping quản lý child hoặc thiết kế thao tác bulk có quy tắc rõ |
| Audit và aggregate chỉ commit một phần | Hai thao tác không dùng chung transaction manager/resource | Đặt @Transactional ở service và xác nhận cùng DataSource |
| Lưu aggregate cũ ghi đè direct update | Object trong bộ nhớ không được tự đồng bộ sau SQL trực tiếp | Tải lại aggregate hoặc tránh trộn hai đường ghi |
| Optimistic locking không phát hiện xung đột | SQL trực tiếp không kiểm tra/tăng version | Đưa expected version vào WHERE và tăng version nguyên tử |
| Callback không chạy | Dùng JdbcTemplate thay cho aggregate persistence | Gọi logic cần thiết tường minh hoặc dùng aggregate API |
| Báo cáo tải quá nhiều object | Dùng aggregate repository cho projection chỉ cần vài cột | Dùng SQL projection/RowMapper |
| SQL injection qua sort field | Ghép identifier do client gửi | Dùng whitelist identifier và bind giá trị |
| Batch giữ transaction quá lâu | Dồn quá nhiều hàng vào một transaction | Chia chunk nếu nghiệp vụ cho phép, checkpoint và retry |

## 17. Quy trình chọn công cụ

Trước khi viết một thao tác dữ liệu mới, hãy trả lời:

1. Dữ liệu đang thao tác có thuộc một aggregate root cụ thể không?
2. Use case có cần bảo vệ invariant của aggregate không?
3. Có cần mapping các đối tượng con và quan hệ sở hữu không?
4. Kết quả cần là aggregate đầy đủ hay chỉ một projection?
5. Có cần JOIN, GROUP BY, bulk DML hoặc SQL đặc thù không?
6. Nếu dùng SQL trực tiếp, invariant/version/callback nào sẽ không còn tự chạy?
7. Các thao tác có cần cùng transaction không và chúng dùng chung DataSource/transaction manager nào?
8. Có cần kiểm tra row count, checkpoint hoặc idempotency không?

Nếu đối tượng thao tác là aggregate và cần hành vi domain, dùng repository hoặc JdbcAggregateTemplate. Nếu use case làm việc với dữ liệu quan hệ ở mức hàng, báo cáo hoặc staging, dùng JdbcTemplate/NamedParameterJdbcTemplate trong DAO chuyên trách.

## 18. Bài tập tự thực hành

**Bài tập 1 — Cùng một aggregate, hai API.** Tạo một PurchaseOrder và lưu bằng repository. Sau đó thử insert một aggregate mới bằng JdbcAggregateTemplate. So sánh cách gọi và xác định phần mapping nào framework đảm nhiệm.

**Bài tập 2 — Báo cáo projection.** Viết DAO dùng JdbcTemplate để tính tổng doanh thu theo tháng. Chỉ trả về các cột cần thiết trong một record báo cáo, không tải Payment aggregate.

**Bài tập 3 — Bulk update.** Viết câu lệnh cập nhật nhiều inventory row có điều kiện. Kiểm tra row count và giải thích invariant nào cần được bảo vệ ở SQL hoặc database constraint.

**Bài tập 4 — Transaction phối hợp.** Trong một service có @Transactional, ghi một aggregate qua JdbcAggregateTemplate và ghi một audit row qua JdbcTemplate. Cố tình làm audit insert thất bại rồi xác nhận aggregate cũng rollback.

**Bài tập 5 — Stale object.** Tải aggregate, thay đổi cùng hàng bằng JdbcTemplate rồi tiếp tục save object cũ. Quan sát kết quả và đề xuất cách tránh ghi đè.

**Bài tập 6 — Version.** Thêm @Version cho aggregate. Viết direct update có expected version và tăng version. Chạy hai transaction cạnh tranh và quan sát một transaction không cập nhật được.

**Bài tập 7 — Quyết định kiến trúc.** Với các use case báo cáo, import, bulk maintenance và đổi trạng thái đơn hàng, chọn repository, JdbcAggregateTemplate hay JdbcTemplate. Giải thích lựa chọn theo aggregate boundary và transaction.

## 19. Ghi nhớ

JdbcAggregateTemplate và JdbcTemplate không phải hai cách viết SQL thay thế nhau. JdbcAggregateTemplate làm việc ở mức aggregate và dùng mapping của Spring Data JDBC; JdbcTemplate/NamedParameterJdbcTemplate làm việc trực tiếp với SQL, hàng và cột.

Hãy dùng repository cho CRUD và use case aggregate thông thường. Dùng JdbcAggregateTemplate khi cần API aggregate trực tiếp mà không muốn tạo repository interface. Dùng JDBC trực tiếp cho báo cáo, projection, staging, bulk DML hoặc truy vấn đặc thù nằm ngoài mô hình aggregate.

Khi SQL trực tiếp thay đổi dữ liệu thuộc aggregate, ứng dụng phải chủ động bảo vệ invariant, version, audit và lifecycle behavior mà đường aggregate persistence thường đảm nhiệm. Đặt transaction ở application service khi nhiều thao tác phải cùng commit/rollback, xác nhận chúng dùng chung transaction manager và kiểm thử kết quả trên database mục tiêu.

### Tài liệu tham khảo

- [Spring Data Relational – JDBC Aggregate Operations](https://docs.spring.io/spring-data/relational/reference/jdbc/aggregate-operations.html)
- [Spring Data Relational – JDBC Repositories](https://docs.spring.io/spring-data/relational/reference/jdbc/repositories.html)
- [Spring Framework – JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html)
- [Spring Framework – Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
