# Chuyển từ JdbcTemplate sang repository theo từng ca sử dụng

Trong **Spring Data Relational JDBC**, ứng dụng có thể chuyển từng ca sử dụng từ `JdbcTemplate` sang repository mà không cần viết lại toàn bộ tầng truy cập dữ liệu. Repository phù hợp với thao tác đọc/lưu aggregate có ranh giới rõ; `JdbcTemplate` vẫn hữu ích cho báo cáo, bulk update, truy vấn tổng hợp, stored procedure hoặc SQL đặc thù.

Hai cách truy cập dữ liệu có thể cùng tồn tại trong một ứng dụng. Nếu dùng chung `DataSource` và transaction manager, các thao tác Spring Data JDBC repository và `JdbcTemplate` có thể tham gia cùng một transaction. Đây là cơ sở để chuyển đổi từng use case một cách có kiểm soát.

Mục tiêu của chuyển đổi là giữ đúng contract nghiệp vụ, mapping khớp schema hiện tại, transaction nhất quán và có test chứng minh hành vi trước/sau. Không nên đổi một lớp DAO chỉ để thay API gọi SQL; trước hết cần xác định ca sử dụng nào thực sự hưởng lợi từ aggregate repository.

## 1. Hiểu đúng hai cách truy cập dữ liệu

### 1.1. JdbcTemplate

`JdbcTemplate` là abstraction cấp thấp hơn JDBC repository. Ứng dụng vẫn quyết định SQL, cách bind parameter, `RowMapper`, batch và nhiều chi tiết của truy vấn.

Ví dụ DAO hiện hữu:

~~~java
@Repository
public class JdbcPurchaseOrderDao {

    private final JdbcTemplate jdbcTemplate;

    public JdbcPurchaseOrderDao(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public Optional<PurchaseOrderRow> findByOrderNumber(
            String orderNumber) {

        List<PurchaseOrderRow> rows = jdbcTemplate.query(
                """
                SELECT id, order_number, customer_id, status, created_at
                FROM purchase_order
                WHERE order_number = ?
                """,
                (rs, rowNum) -> new PurchaseOrderRow(
                        rs.getLong("id"),
                        rs.getString("order_number"),
                        rs.getLong("customer_id"),
                        rs.getString("status"),
                        rs.getTimestamp("created_at").toInstant()
                ),
                orderNumber
        );

        if (rows.isEmpty()) {
            return Optional.empty();
        }
        if (rows.size() > 1) {
            throw new IllegalStateException(
                    "Order number is not unique: " + orderNumber);
        }
        return Optional.of(rows.get(0));
    }
}
~~~

DAO kiểm soát hoàn toàn SQL và mapping. Điều này linh hoạt, nhưng nếu nhiều use case lặp lại cách tìm, insert, update và mapping cùng một aggregate, phần code JDBC có thể trở nên dài và phân tán.

### 1.2. Spring Data JDBC repository

Repository biểu diễn thao tác lưu/tìm aggregate thông qua interface:

~~~java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    Optional<PurchaseOrder> findByOrderNumber(String orderNumber);
}
~~~

Spring Data JDBC tạo implementation cho các thao tác repository chuẩn và derived query. Mapping metadata được khai báo trên aggregate/entity, còn ứng dụng tập trung hành vi nghiệp vụ trong service/domain model.

Repository phù hợp khi:

- Dữ liệu có thể mô hình hóa thành aggregate root với ranh giới rõ.
- Use case thường đọc/lưu aggregate theo ID hoặc thuộc tính nghiệp vụ.
- Các thao tác insert/update/delete tuân theo lifecycle của aggregate.
- Muốn giảm SQL CRUD và mapping lặp lại.
- Cần optimistic locking, auditing hoặc repository abstraction phù hợp.

`JdbcTemplate` vẫn phù hợp khi:

- Query báo cáo trả projection phức tạp hoặc dữ liệu tổng hợp.
- Bulk update/delete tác động nhiều hàng.
- Stored procedure, CTE hoặc SQL đặc thù khó biểu diễn bằng repository.
- Cần kiểm soát chính xác SQL, lock hoặc hint theo database.
- Đọc dữ liệu lớn theo streaming/batch với contract riêng.
- Một thao tác chỉ là lệnh SQL nhỏ, không cần load và lưu aggregate.

Không có yêu cầu phải chọn một trong hai cho toàn ứng dụng. Chọn abstraction theo từng ca sử dụng.

## 2. Lập danh sách use case trước khi sửa code

Trước khi chuyển, lập inventory từ service/controller/job đang gọi DAO. Với mỗi ca sử dụng, ghi lại:

| Thông tin | Câu hỏi cần trả lời |
| --- | --- |
| Mục đích nghiệp vụ | Người dùng hoặc hệ thống đang thực hiện hành động gì? |
| Đường đọc/ghi | Query nào chạy, bảng nào thay đổi? |
| Cardinality | Kết quả là 0/1/nhiều hàng? |
| Aggregate boundary | Những hàng nào thuộc cùng aggregate root? |
| SQL đặc thù | Có join, CTE, window function, bulk update hoặc stored procedure không? |
| Transaction | Các bước nào phải commit/rollback cùng nhau? |
| Tải | Tần suất, số hàng, latency và mức độ đồng thời? |
| Contract | Service đang trả về gì, xử lý lỗi và null ra sao? |

Sau đó phân nhóm:

| Nhóm use case | Hướng chuyển đổi |
| --- | --- |
| Tìm một aggregate theo ID hoặc khóa duy nhất | Repository finder |
| Tạo/cập nhật một aggregate | Repository `save` trong service transaction |
| Xóa aggregate theo version/ID | Repository delete theo contract |
| Lọc danh sách đơn giản | Derived query hoặc `@Query` |
| Báo cáo join nhiều bảng, group/aggregate | Có thể giữ `JdbcTemplate` |
| Bulk update nhiều hàng | Thường giữ `JdbcTemplate` hoặc SQL chuyên biệt |
| Import/export và batch | Đánh giá riêng theo kích thước và resource lifetime |
| Stored procedure hoặc database-specific SQL | Giữ abstraction SQL phù hợp |

Một use case có thể dùng cả hai: repository lưu aggregate chính, `JdbcTemplate` đọc một projection phụ hoặc cập nhật một bảng kỹ thuật trong cùng transaction.

## 3. Chuyển theo ca sử dụng, không chuyển theo bảng một cách máy móc

Ranh giới repository của Spring Data JDBC xoay quanh **aggregate root**, không chỉ là một bảng. Một aggregate root quản lý các entity/value object thuộc nó và là điểm truy cập để lưu thay đổi của aggregate.

Ví dụ mô hình đơn hàng:

~~~text
PurchaseOrder (aggregate root)
  ├── id
  ├── orderNumber
  ├── customerId
  ├── status
  └── lines
        ├── OrderLine
        └── OrderLine
~~~

Nếu `OrderLine` chỉ tồn tại trong vòng đời của đơn hàng, ứng dụng thường lưu và thay đổi nó qua `PurchaseOrderRepository`. Nếu một đối tượng có vòng đời độc lập, được tham chiếu và thay đổi riêng, nó có thể là aggregate root khác.

Không nên tạo repository cho mọi bảng chỉ vì DAO cũ có một class cho mỗi bảng. Điều đó có thể phá vỡ ranh giới aggregate và khiến ứng dụng thao tác entity con độc lập ngoài invariant của root.

### 3.1. Không mang mô hình JPA sang Spring Data JDBC

Spring Data JDBC không phải JPA:

- Không có persistence context/identity map kiểu JPA.
- Không có dirty checking tự động khi sửa object đã load mà không gọi `save`.
- Không có lazy loading proxy cho quan hệ như JPA.
- Aggregate được lưu theo lifecycle và mapping của Spring Data JDBC.
- Quan hệ được nạp theo mapping/aggregate design, không nên thiết kế như một object graph tùy ý.

Vì vậy, khi chuyển từ `JdbcTemplate`, hãy thiết kế aggregate theo cách Spring Data JDBC quản lý được; đừng tạo entity graph lớn chỉ để giống ORM.

## 4. Ví dụ schema hiện hữu và model Spring Data JDBC

Giả sử hệ thống cũ có schema:

~~~sql
CREATE TABLE purchase_order (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE order_line (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    purchase_order_id BIGINT NOT NULL,
    sku VARCHAR(50) NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT fk_order_line_order
        FOREIGN KEY (purchase_order_id)
        REFERENCES purchase_order(id)
);
~~~

Model:

~~~java
import java.time.Instant;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order")
public record PurchaseOrder(
        @Id Long id,
        @Column("order_number") String orderNumber,
        @Column("customer_id") Long customerId,
        String status,
        @Column("created_at") Instant createdAt,
        @MappedCollection(idColumn = "purchase_order_id")
        List<OrderLine> lines
) {
    public PurchaseOrder confirm() {
        if (!"PENDING".equals(status)) {
            throw new IllegalStateException(
                    "Only pending orders can be confirmed");
        }
        return new PurchaseOrder(
                id, orderNumber, customerId, "CONFIRMED",
                createdAt, lines);
    }
}

public record OrderLine(
        @Id Long id,
        String sku,
        Integer quantity
) {}
~~~

Tên bảng/cột được khai báo tường minh để mapping khớp schema hiện hữu. Khi schema có naming convention khác, dùng `@Table`, `@Column`, `@MappedCollection` hoặc mapping metadata tương ứng thay vì đổi database chỉ để khớp tên mặc định.

Ví dụ này dùng record để thể hiện immutable data. Với entity mutable, constructor, getter/setter và access strategy cần tuân theo mapping convention của Spring Data JDBC. Dùng kiểu dữ liệu/annotation được hỗ trợ bởi phiên bản Spring Data đang chạy.

### 4.1. Mapping collection con

`@MappedCollection(idColumn = "purchase_order_id")` cho Spring Data JDBC biết cột ở bảng con dùng để tham chiếu aggregate root. Tên cột phải khớp schema hiện tại.

Nếu child có thứ tự cần bảo toàn, xem xét khai báo cột key qua `keyColumn` và schema tương ứng. Không giả định thứ tự hàng trong database được bảo đảm nếu query không có `ORDER BY` hoặc mapping không lưu vị trí.

### 4.2. Khóa chính do database sinh

Khi ID được sinh bởi database, `@Id` trên kiểu tương thích cho phép Spring Data JDBC nhận ID được tạo khi insert. Dùng instance trả về từ `save` để lấy ID:

~~~java
PurchaseOrder saved = repository.save(newOrder);
Long generatedId = saved.id();
~~~

Đừng giả định object đầu vào immutable sẽ được thay đổi tại chỗ. Nếu ứng dụng cũ dùng sequence, UUID tự tạo hoặc key composite, hãy xác định chiến lược ID trước khi chuyển.

## 5. Chuyển finder từ RowMapper sang repository method

### 5.1. Code cũ

DAO cũ thường tự viết query:

~~~java
public Optional<PurchaseOrderRow> findByOrderNumber(String number) {
    List<PurchaseOrderRow> rows = jdbcTemplate.query(
            """
            SELECT id, order_number, customer_id, status, created_at
            FROM purchase_order
            WHERE order_number = ?
            """,
            purchaseOrderRowMapper,
            number
    );
    return rows.stream().findFirst();
}
~~~

Điểm cần kiểm tra trong code cũ: `findFirst()` âm thầm bỏ qua hàng thứ hai nếu dữ liệu trùng. Nếu `order_number` phải duy nhất, hành vi này che giấu dữ liệu sai.

### 5.2. Repository mới

~~~java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    Optional<PurchaseOrder> findByOrderNumber(String orderNumber);
}
~~~

Repository finder diễn đạt contract “không có hoặc có tối đa một đơn hàng”. Nếu có nhiều hàng, Spring Data báo `IncorrectResultSizeDataAccessException` thay vì chọn ngẫu nhiên.

Để bảo đảm contract, database cần unique constraint:

~~~sql
ALTER TABLE purchase_order
ADD CONSTRAINT uk_purchase_order_number UNIQUE (order_number);
~~~

Trước khi thêm constraint, kiểm tra và xử lý dữ liệu trùng bằng migration có kế hoạch. Không xóa dữ liệu trùng tự động khi chưa xác định quy tắc nghiệp vụ.

### 5.3. Dùng collection cho query nhiều kết quả

Nếu nhiều đơn hàng là kết quả hợp lệ:

~~~java
List<PurchaseOrder> findByCustomerId(Long customerId);
~~~

Không chuyển query nhiều kết quả thành `Optional<T>` chỉ để giảm số dòng code. Kiểu trả về phải phản ánh cardinality nghiệp vụ.

## 6. Chuyển create/update từ SQL thủ công sang save

### 6.1. Code cũ

Một DAO có thể insert root rồi lấy generated key để insert child:

~~~java
public long insertOrder(CreateOrderCommand command) {
    KeyHolder keyHolder = new GeneratedKeyHolder();

    jdbcTemplate.update(connection -> {
        PreparedStatement ps = connection.prepareStatement(
                """
                INSERT INTO purchase_order
                    (order_number, customer_id, status, created_at)
                VALUES (?, ?, ?, ?)
                """,
                Statement.RETURN_GENERATED_KEYS
        );
        ps.setString(1, command.orderNumber());
        ps.setLong(2, command.customerId());
        ps.setString(3, "PENDING");
        ps.setTimestamp(4, Timestamp.from(command.createdAt()));
        return ps;
    }, keyHolder);

    long orderId = keyHolder.getKey().longValue();
    // Insert order_line rows with orderId.
    return orderId;
}
~~~

Đoạn code này cần transaction để insert root và child cùng thành công hoặc rollback. Nếu DAO tự quản lý nhiều connection hoặc không có transaction boundary, có thể tạo aggregate dở dang.

### 6.2. Repository mới

~~~java
@Service
public class PlaceOrderService {

    private final PurchaseOrderRepository repository;

    public PlaceOrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public PurchaseOrder place(CreateOrderCommand command) {
        PurchaseOrder order = new PurchaseOrder(
                null,
                command.orderNumber(),
                command.customerId(),
                "PENDING",
                command.createdAt(),
                command.lines().stream()
                        .map(line -> new OrderLine(
                                null, line.sku(), line.quantity()))
                        .toList()
        );

        return repository.save(order);
    }
}
~~~

Spring Data JDBC lưu aggregate root và collection con theo mapping. Service vẫn chịu trách nhiệm tạo trạng thái domain hợp lệ và xác định transaction boundary.

Không giả định mọi schema child đều tương thích với collection mapping ngay lập tức. Cần kiểm tra foreign key, ID generation, thứ tự child, nullability, default values và trigger hiện hữu. Nếu schema cũ phức tạp hoặc child được quản lý độc lập, có thể giữ một phần thao tác bằng `JdbcTemplate` trong giai đoạn chuyển tiếp.

### 6.3. Update aggregate

Repository `save` được dùng cho cả insert và update theo trạng thái entity mà Spring Data JDBC xác định. Khi update, tải aggregate, gọi domain method, rồi lưu aggregate mới:

~~~java
@Transactional
public PurchaseOrder confirm(Long id) {
    PurchaseOrder current = repository.findById(id)
            .orElseThrow(() -> new OrderNotFoundException(id));

    return repository.save(current.confirm());
}
~~~

Không chỉ sửa object rồi quên gọi `save`. Spring Data JDBC không dùng dirty checking kiểu JPA để tự ghi mọi thay đổi khi transaction kết thúc.

## 7. Giữ JdbcTemplate trong cùng service transaction

Một chuyển đổi theo từng ca sử dụng thường có giai đoạn mà service dùng cả repository và `JdbcTemplate`.

Ví dụ: repository lưu aggregate đơn hàng, `JdbcTemplate` cập nhật một bảng projection kỹ thuật:

~~~java
@Service
public class OrderApplicationService {

    private final PurchaseOrderRepository orderRepository;
    private final JdbcTemplate jdbcTemplate;

    public OrderApplicationService(
            PurchaseOrderRepository orderRepository,
            JdbcTemplate jdbcTemplate) {
        this.orderRepository = orderRepository;
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional
    public PurchaseOrder confirm(Long id) {
        PurchaseOrder order = orderRepository.findById(id)
                .orElseThrow(() -> new OrderNotFoundException(id));

        PurchaseOrder confirmed = order.confirm();
        PurchaseOrder saved = orderRepository.save(confirmed);

        jdbcTemplate.update(
                """
                UPDATE order_search_projection
                SET status = ?
                WHERE order_id = ?
                """,
                saved.status(),
                saved.id()
        );

        return saved;
    }
}
~~~

Nếu `JdbcTemplate` và repository dùng cùng `DataSource` cùng transaction manager, thao tác JDBC có thể tham gia transaction hiện tại. Nếu câu lệnh projection thất bại và exception đi qua transaction boundary, thay đổi repository cũng rollback.

Điều kiện này phải được xác nhận trong cấu hình. Nếu có nhiều `DataSource`, nhiều transaction manager hoặc tự lấy connection bằng `DataSource.getConnection()`, không mặc định chúng cùng tham gia một transaction. Với JDBC trực tiếp trong transaction Spring, dùng `JdbcTemplate`, `DataSourceUtils` hoặc cơ chế transaction-aware phù hợp.

## 8. Chuyển query tùy biến bằng @Query

Không phải query nào cũng cần viết lại thành derived method. Spring Data JDBC hỗ trợ `@Query` để khai báo SQL cụ thể cho repository method:

~~~java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    @Query("""
        SELECT id, order_number, customer_id, status, created_at
        FROM purchase_order
        WHERE customer_id = :customerId
          AND status = :status
        ORDER BY created_at DESC, id DESC
        """)
    List<PurchaseOrder> findRecentByCustomerAndStatus(
            @Param("customerId") Long customerId,
            @Param("status") String status
    );
}
~~~

`@Query` giữ quyền kiểm soát SQL nhưng đưa query vào contract repository. Điều này hữu ích khi query là một phần ổn định của thao tác aggregate.

Lưu ý:

- Tên cột phải khớp schema và mapping.
- Result set phải có các cột cần thiết cho kiểu trả về.
- Dùng bind parameter thay vì nối chuỗi input vào SQL.
- `ORDER BY` phải ổn định nếu caller phụ thuộc thứ tự.
- Query trả aggregate root không tự động biến một join one-to-many thành object graph hoàn chỉnh.
- SQL trong `@Query` vẫn phụ thuộc database dialect; không tự nhiên portable giữa mọi database.

Nếu query trả DTO/report projection phức tạp, `JdbcTemplate` với `RowMapper` có thể rõ ràng và phù hợp hơn.

## 9. Custom repository fragment khi cần kết hợp abstraction

Một số use case cần repository contract nhưng SQL implementation tùy chỉnh. Có thể dùng repository fragment:

~~~java
public interface PurchaseOrderSearch {
    List<OrderSummary> search(OrderSearchCriteria criteria);
}

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long>,
                PurchaseOrderSearch {
}
~~~

Implementation fragment có thể dùng `JdbcTemplate`:

~~~java
public class PurchaseOrderSearchImpl implements PurchaseOrderSearch {

    private final JdbcTemplate jdbcTemplate;

    public PurchaseOrderSearchImpl(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public List<OrderSummary> search(OrderSearchCriteria criteria) {
        return jdbcTemplate.query(
                """
                SELECT id, order_number, status, created_at
                FROM purchase_order
                WHERE customer_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (rs, rowNum) -> new OrderSummary(
                        rs.getLong("id"),
                        rs.getString("order_number"),
                        rs.getString("status"),
                        rs.getTimestamp("created_at").toInstant()
                ),
                criteria.customerId()
        );
    }
}
~~~

Tên class implementation phải tuân theo quy ước discovery của Spring Data repository fragment trong phiên bản dự án. Repository fragment hữu ích khi muốn API tìm kiếm thuộc repository nhưng cần SQL tùy chỉnh. Không nên biến mọi DAO cũ thành fragment chỉ để đổi tên class.

## 10. Giữ các truy vấn báo cáo và bulk operation ở JdbcTemplate

### 10.1. Báo cáo/aggregate

Ví dụ dashboard cần group và sum:

~~~sql
SELECT status, COUNT(*) AS order_count
FROM purchase_order
WHERE created_at >= ?
GROUP BY status
ORDER BY order_count DESC;
~~~

Đây là projection báo cáo, không phải aggregate root. `JdbcTemplate` với DTO/RowMapper thường là lựa chọn tự nhiên:

~~~java
public record OrderCountByStatus(String status, long count) {}

public List<OrderCountByStatus> countByStatus(Instant from) {
    return jdbcTemplate.query(
            """
            SELECT status, COUNT(*) AS order_count
            FROM purchase_order
            WHERE created_at >= ?
            GROUP BY status
            ORDER BY order_count DESC
            """,
            (rs, rowNum) -> new OrderCountByStatus(
                    rs.getString("status"),
                    rs.getLong("order_count")
            ),
            Timestamp.from(from)
    );
}
~~~

Không cần dựng một `PurchaseOrder` cho mỗi hàng báo cáo.

### 10.2. Bulk update

Ví dụ đóng hàng nghìn đơn hết hạn:

~~~sql
UPDATE purchase_order
SET status = 'EXPIRED'
WHERE status = 'PENDING'
  AND expires_at < ?;
~~~

Đây là thao tác bulk trên nhiều hàng. Dùng `JdbcTemplate.update` có thể hiệu quả và rõ ràng hơn việc load từng aggregate rồi gọi `save` trong vòng lặp:

~~~java
int expirePendingOrders(Instant cutoff) {
    return jdbcTemplate.update(
            """
            UPDATE purchase_order
            SET status = 'EXPIRED'
            WHERE status = 'PENDING'
              AND expires_at < ?
            """,
            Timestamp.from(cutoff)
    );
}
~~~

Tuy nhiên, bulk SQL bỏ qua lifecycle callbacks và logic domain của từng aggregate. Nếu có `@Version`, auditing hoặc invariant nghiệp vụ, phải cập nhật các cột liên quan và cân nhắc tác động tới optimistic locking. Không dùng bulk update để lách domain rule.

## 11. Transaction boundary trong quá trình chuyển đổi

Đặt transaction ở service/use case để nhiều thao tác dữ liệu phải thành công hoặc thất bại cùng nhau:

~~~java
@Transactional
public void completeOrder(Long orderId) {
    PurchaseOrder order = orderRepository.findById(orderId)
            .orElseThrow();

    orderRepository.save(order.complete());
    jdbcTemplate.update(
            "UPDATE customer_stats SET completed_orders = completed_orders + 1 " +
            "WHERE customer_id = ?",
            order.customerId()
    );
}
~~~

Nếu cả hai dùng cùng local transaction manager/DataSource, các lệnh có thể commit/rollback cùng nhau.

Những điều cần kiểm tra:

- Repository và `JdbcTemplate` được inject từ cùng cấu hình `DataSource` hay không.
- `PlatformTransactionManager` quản lý đúng DataSource đó hay không.
- Service được gọi qua Spring proxy hay bị self-invocation.
- Exception có đi qua transaction boundary không.
- Checked exception có cần `rollbackFor` hay không.
- Có `REQUIRES_NEW` hoặc async task tạo transaction riêng không.

Không giả định một `@Transactional` có thể rollback hai database resource độc lập. Nếu hai DAO dùng hai DataSource/transaction manager khác nhau, cần kiến trúc phân tán phù hợp hoặc eventual consistency.

## 12. Giữ nguyên contract của service khi thay implementation

Controller và consumer nên phụ thuộc vào application service/use case, không phụ thuộc trực tiếp vào `JdbcTemplate` hoặc repository cụ thể.

Ví dụ contract:

~~~java
public interface OrderQueries {
    Optional<OrderDetails> findDetails(String orderNumber);
}

public interface OrderCommands {
    PurchaseOrder confirm(Long id);
}
~~~

Trong giai đoạn chuyển đổi, service có thể gọi DAO cũ. Sau khi repository mới sẵn sàng, thay implementation bên trong service mà không cần thay API bên ngoài:

~~~text
Controller / Message Handler
            │
            ▼
       Application Service
            │
       ┌────┴─────┐
       ▼          ▼
   Old DAO    New Repository
 JdbcTemplate  Spring Data JDBC
~~~

Đây là cách giảm phạm vi thay đổi: caller vẫn gọi cùng use case, chỉ persistence adapter thay đổi. Không để controller có lúc gọi repository, lúc gọi DAO trực tiếp theo từng endpoint.

## 13. Chiến lược chuyển đổi từng bước

Một trình tự an toàn:

### Bước 1: Chọn một use case nhỏ

Chọn một đường đọc/ghi có phạm vi rõ, ít side effect và có thể kiểm thử độc lập. Ví dụ tìm đơn hàng theo order number hoặc cập nhật trạng thái đơn hàng.

Tránh bắt đầu bằng use case phức tạp có nhiều database, batch lớn, trigger và side effect bên ngoài.

### Bước 2: Ghi lại behavior hiện tại

Thu thập SQL hiện tại và bind parameter, kiểu trả về và hành vi khi không có/nhiều hàng, null handling và exception mapping, transaction boundary, generated key/default value/trigger, thứ tự kết quả nếu caller phụ thuộc, latency và tần suất truy vấn.

Viết test characterization để ghi nhận contract hiện tại trước khi thay đổi.

### Bước 3: Xác định aggregate và mapping

Xác định root, entity con, ID, cột và quan hệ. Khai báo mapping Spring Data JDBC khớp schema hiện hữu. Không thay schema cùng lúc nếu không cần.

### Bước 4: Tạo repository mới

Bắt đầu với finder/CRUD đơn giản. Dùng `Optional` cho 0/1 kết quả, collection cho nhiều kết quả và unique constraint cho invariant duy nhất.

### Bước 5: Chuyển một service method

Thay DAO call bằng repository call bên trong application service. Giữ nguyên method signature và transaction semantics nếu đó là contract mong muốn.

### Bước 6: Đối chiếu kết quả

Chạy test trên cùng dữ liệu, so sánh giá trị trả về, số hàng đọc/ghi, mapping null/time/enum/numeric, generated ID, side effect, transaction rollback và query count/latency khi cần.

### Bước 7: Chuyển traffic

Khi test ổn định, route use case qua repository mới. Với hệ thống cần rollout dần, dùng feature flag ở tầng application service để chọn adapter. Không dual-write vào hai implementation nếu chưa có cơ chế idempotency và đối soát rõ ràng.

### Bước 8: Quan sát production

Theo dõi lỗi mapping, duplicate result, transaction rollback, query latency, connection pool và database load. So sánh với baseline đã ghi nhận.

### Bước 9: Loại bỏ code cũ sau khi xác nhận

Chỉ xóa DAO/RowMapper cũ khi không còn caller và đã qua thời gian xác nhận phù hợp. Giữ những truy vấn vẫn có lý do rõ ràng để dùng `JdbcTemplate`.

## 14. Không dual-write một cách tùy tiện

Trong migration, đôi khi nhóm muốn ghi cả qua DAO cũ và repository mới để so sánh. Điều này có thể gây insert trùng hoặc duplicate side effect, version tăng hai lần, trigger chạy hai lần, audit event bị nhân đôi, race condition hoặc kết quả khác nhau nếu một đường ghi thất bại giữa chừng.

Với read path, có thể chạy shadow read trong môi trường kiểm soát: một implementation trả kết quả cho caller, implementation còn lại chỉ đọc để so sánh. Cần cân nhắc tải database và bảo đảm query phụ không có side effect.

Với write path, ưu tiên một đường ghi có thẩm quyền. Nếu cần đối chiếu, dùng fixture/test hoặc replay trên database thử nghiệm. Chỉ dual-write khi có thiết kế idempotency, reconciliation và failure handling rõ ràng.

## 15. Mapping khác biệt cần chú ý

Khi thay `RowMapper` bằng Spring Data JDBC mapping, kiểm tra các kiểu dữ liệu:

| Dữ liệu cũ | Điều cần xác nhận khi chuyển |
| --- | --- |
| Timestamp/Date | Time zone, precision, `Instant`/`LocalDateTime` và JDBC driver |
| Enum | Mapping string hay ordinal; schema hiện tại lưu gì |
| Boolean | Kiểu cột và conversion theo database |
| Decimal | Precision/scale và `BigDecimal` |
| JSON/JSONB | JDBC type, converter và driver-specific value |
| UUID | Cách driver/database biểu diễn và conversion |
| Null | Nullable column, constructor parameter và wrapper type |
| Generated ID | Identity/sequence/UUID và giá trị trả về từ `save` |
| Naming | Tên bảng/cột hiện hữu và naming strategy |
| Child collection | Foreign key, key/order column và aggregate ownership |

Nếu kiểu dữ liệu cần conversion riêng, Spring Data JDBC hỗ trợ custom conversions. Đăng ký converter theo cấu hình mapping của phiên bản đang dùng và viết test round-trip từ domain value sang JDBC value rồi đọc lại.

Không thay đổi cách lưu enum, timestamp hoặc JSON chỉ vì mapping mặc định tiện hơn. Dữ liệu đã tồn tại phải tiếp tục đọc đúng.

## 16. Generated columns, defaults và trigger

DAO cũ có thể bỏ qua một số cột vì database tự đặt default hoặc trigger điền giá trị. Khi chuyển sang repository, kiểm tra cách Spring Data JDBC sinh INSERT và cách database trả generated value.

Ví dụ:

~~~sql
created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
~~~

Nếu entity truyền `createdAt = null`, database default chỉ được áp dụng khi câu INSERT bỏ cột hoặc dùng từ khóa DEFAULT theo cú pháp phù hợp; nếu Spring Data gửi cột với giá trị NULL, default có thể không chạy. Cần kiểm tra SQL thực tế và mapping.

Tương tự, trigger có thể cập nhật `updated_at`, nhưng object trả về từ `save` không nhất thiết tự phản ánh mọi thay đổi trigger nếu database/driver không trả lại giá trị đó. Nếu caller cần giá trị sau trigger, hãy xác định cơ chế reload hoặc generated value phù hợp.

## 17. Paging, streaming và dữ liệu lớn

Không phải repository collection nào cũng phù hợp với hàng triệu dòng. Trước khi chuyển query lớn từ `JdbcTemplate`, xác định kích thước kết quả tối đa, có cần toàn bộ dữ liệu trong bộ nhớ không, có yêu cầu sort/page không, có cần cursor/stream và transaction giữ lâu không, và có thể xử lý theo keyset/batch không.

Nếu use case là export lớn, `JdbcTemplate` với `RowCallbackHandler`, `ResultSetExtractor` hoặc cơ chế streaming có thể phù hợp hơn. Nếu chuyển sang repository, chọn return type và transaction/resource lifecycle theo contract của Spring Data JDBC phiên bản đang dùng.

Đối với pagination, kiểm tra query count, count query và sort. Với offset sâu, cân nhắc keyset pagination nếu API cho phép.

## 18. Kiểm thử chuyển đổi

Nên có nhiều lớp test:

| Test | Xác nhận điều gì? |
| --- | --- |
| Mapping/repository test | Entity đọc/ghi đúng schema |
| Query test | Finder trả đúng 0/1/nhiều kết quả và thứ tự |
| Service test | Use case giữ nguyên contract nghiệp vụ |
| Transaction integration test | Repository và JdbcTemplate rollback/commit cùng nhau |
| Database integration test | Dialect, driver, generated key, constraint và type mapping đúng |
| Performance comparison | Latency, query count và resource usage không suy giảm ngoài dự kiến |

Ví dụ test repository:

~~~java
@DataJdbcTest
class PurchaseOrderRepositoryTest {

    @Autowired
    PurchaseOrderRepository repository;

    @Test
    void findsOrderByUniqueOrderNumber() {
        PurchaseOrder saved = repository.save(
                new PurchaseOrder(
                        null, "PO-100", 42L, "PENDING",
                        Instant.parse("2026-01-01T10:00:00Z"),
                        List.of()
                )
        );

        Optional<PurchaseOrder> found =
                repository.findByOrderNumber("PO-100");

        assertThat(found).isPresent();
        assertThat(found.orElseThrow().id()).isEqualTo(saved.id());
    }
}
~~~

Ví dụ integration test xác nhận repository và `JdbcTemplate` dùng chung transaction:

~~~java
@SpringBootTest
class MixedPersistenceRollbackTest {

    @Autowired
    OrderApplicationService service;

    @Autowired
    PurchaseOrderRepository repository;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void rollsBackRepositoryAndJdbcTemplateWritesTogether() {
        assertThatThrownBy(() -> service.createAndFail())
                .isInstanceOf(IllegalStateException.class);

        assertThat(repository.count()).isZero();

        Integer projectionCount = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM order_search_projection",
                Integer.class
        );
        assertThat(projectionCount).isZero();
    }
}
~~~

Test transaction integration nên gọi service qua Spring bean/proxy. Nếu test method tự mang `@Transactional`, transaction của test có thể che giấu việc service có transaction boundary độc lập hay không. Dùng database engine gần production khi phụ thuộc dialect/constraint/driver.

## 19. Đo hiệu năng trước và sau

Repository abstraction không tự động làm query nhanh hơn. SQL sinh ra có thể khác DAO cũ về số cột, số query hoặc cách tải aggregate.

So sánh trước/sau:

- Số SQL statement cho một use case.
- Query latency p50/p95/p99.
- Số hàng đọc và số hàng trả về.
- N+1 hoặc truy vấn lặp ngoài ý muốn.
- Connection acquisition/usage time.
- Database CPU, I/O và lock wait.
- Throughput của thao tác ghi.
- Kích thước dữ liệu/aggregate được load vào bộ nhớ.

Một finder đơn giản có thể chuyển tốt, nhưng nếu repository load toàn bộ aggregate có nhiều child trong khi DAO cũ chỉ select một projection nhỏ, hiệu năng có thể giảm. Khi đó, giữ query projection bằng `JdbcTemplate` hoặc thiết kế query chuyên biệt.

Không benchmark bằng dữ liệu quá nhỏ nếu production có hàng triệu dòng. Dữ liệu test phải gần phân bố và cardinality thực tế.

## 20. Các lỗi thường gặp khi chuyển đổi

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Repository không tìm thấy bảng/cột | Mapping mặc định không khớp schema cũ | Khai báo `@Table`, `@Column`, `@MappedCollection` |
| Insert root được nhưng child không lưu | Aggregate mapping/foreign key sai hoặc child không nằm trong root | Kiểm tra aggregate boundary và `idColumn` |
| Giá trị default database thành NULL | INSERT gửi NULL thay vì bỏ cột/default | Kiểm tra SQL và generated/default column mapping |
| ID trả về khác hành vi DAO cũ | Khác chiến lược generated key/sequence | Xác định ID strategy và dùng instance trả về từ `save` |
| Query trả duplicate result | Return type đơn nhưng dữ liệu/query khớp nhiều hàng | Unique constraint, sửa predicate hoặc đổi collection |
| Repository và JdbcTemplate không rollback cùng nhau | Khác DataSource/transaction manager hoặc transaction boundary | Dùng cùng transaction resource và kiểm thử integration |
| Update không ghi thay đổi object | Quên gọi `save` hoặc entity state sai | Tải aggregate, gọi domain method rồi save |
| Update ghi lại nhiều child ngoài dự kiến | Mapping aggregate collection khác DAO cũ | Kiểm tra ownership và semantics lưu aggregate |
| Query mới chậm hơn | Load aggregate lớn hoặc SQL khác | Đo query plan, projection và số câu SQL |
| Batch operation chậm | Chuyển bulk SQL thành vòng lặp save từng aggregate | Giữ bulk path ở JdbcTemplate nếu phù hợp |
| Trigger/auditing tạo giá trị khác | Lifecycle callback và trigger cùng ghi field | Xác định một contract rõ và test giá trị cuối |
| Test pass nhưng production fail | Chỉ test bằng embedded DB hoặc test-managed transaction | Chạy integration test với database mục tiêu |

## 21. Checklist cho từng ca sử dụng

Trước khi chuyển một use case, xác nhận:

1. Use case và contract hiện tại đã được mô tả/test chưa?
2. Query trả 0/1/nhiều hàng và kiểu trả về mới có diễn đạt đúng không?
3. Dữ liệu có thuộc một aggregate root rõ ràng không?
4. Mapping có khớp tên bảng/cột, ID, nullability, default và child key không?
5. SQL tùy biến có thể dùng derived query/`@Query` hay nên giữ `JdbcTemplate`?
6. Transaction boundary có bao quanh toàn bộ nghiệp vụ không?
7. Repository và JdbcTemplate có dùng chung DataSource/transaction manager khi cần không?
8. Rollback, generated ID, trigger và audit metadata đã được kiểm tra chưa?
9. Test có chạy trên database/driver mục tiêu không?
10. Query count, latency và write overhead có được so sánh không?
11. Có cách chuyển traffic/rollback implementation rõ ràng không?
12. DAO cũ chỉ được xóa sau khi không còn caller và đã xác nhận behavior mới?

## 22. Bài tập thực hành

**Bài 1 — Inventory use case.** Chọn ba method trong một DAO JdbcTemplate hiện hữu. Ghi SQL, bảng, cardinality, transaction và mục đích nghiệp vụ của từng method. Phân loại method nào nên chuyển sang repository và method nào nên giữ SQL.

**Bài 2 — Chuyển finder.** Chuyển một RowMapper tìm theo khóa nghiệp vụ thành repository method trả Optional<T>. Thêm unique constraint tương ứng và test trường hợp không tìm thấy.

**Bài 3 — Chuyển aggregate write.** Chuyển thao tác insert root/child thành aggregate Spring Data JDBC. Xác nhận generated ID và child foreign key đúng với schema cũ.

**Bài 4 — Giữ JdbcTemplate trong transaction.** Viết service @Transactional gọi repository save và JdbcTemplate.update. Cố ý làm bước cuối thất bại, xác nhận cả hai thay đổi rollback.

**Bài 5 — Custom query.** Chuyển một query đơn giản sang @Query. So sánh SQL, bind parameter và result mapping với DAO cũ.

**Bài 6 — Báo cáo.** Giữ một query GROUP BY dùng JdbcTemplate và ánh xạ DTO. Giải thích vì sao dữ liệu báo cáo không cần trở thành aggregate root.

**Bài 7 — Bulk update.** Giữ một bulk update ở JdbcTemplate. Xác định cột version/audit nào cần cập nhật và kiểm thử tác động tới repository optimistic locking nếu có.

**Bài 8 — Custom repository fragment.** Tạo repository fragment có implementation dùng JdbcTemplate cho truy vấn tìm kiếm phức tạp. Kiểm tra naming/discovery convention của phiên bản Spring Data đang dùng.

**Bài 9 — Mapping cũ.** Chuyển một cột timestamp, enum hoặc JSON từ RowMapper sang Spring Data JDBC mapping. Viết test round-trip trên database mục tiêu.

**Bài 10 — Đo trước/sau.** Đo số query và latency của một use case trước và sau chuyển đổi. Giải thích thay đổi do aggregate loading, projection, index hoặc transaction.

**Bài 11 — Feature flag.** Giữ hai adapter sau cùng một service contract và chuyển một read use case bằng feature flag trong môi trường staging. So sánh kết quả mà không dual-write.

**Bài 12 — Rollback migration.** Chọn một use case đã chuyển, mô phỏng lỗi production và chuyển traffic lại implementation cũ. Ghi rõ điều kiện cần để rollback an toàn nếu schema không thay đổi.

### Tài liệu tham khảo

- [Spring Data Relational — JDBC Reference](https://docs.spring.io/spring-data/relational/reference/jdbc.html): repository, mapping, aggregate persistence và query trong Spring Data JDBC.
- [Spring Data Relational — Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): mapping entity, table/column và collection.
- [Spring Data Relational — Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html): derived query và query annotation.
- [Spring Framework — JdbcTemplate](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): SQL execution, RowMapper và JDBC abstraction.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): transaction boundary và rollback rules.
- [Spring Framework — JDBC Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html): DataSource connection management và transaction integration.
