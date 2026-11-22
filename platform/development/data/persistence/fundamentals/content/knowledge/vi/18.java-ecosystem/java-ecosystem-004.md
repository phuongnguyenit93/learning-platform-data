# Phân biệt SQL trực tiếp, SQL mapper và ORM

Cùng một chức năng Java — lấy danh sách đơn hàng rồi cập nhật trạng thái — có thể được triển khai bằng JDBC, SQL mapper hoặc ORM. Cả ba cách đều có thể truy cập **cùng một cơ sở dữ liệu quan hệ**, sử dụng connection pool và tuân thủ các ràng buộc dữ liệu, transaction, isolation và cơ chế khóa như nhau. Điều khác nhau chủ yếu là **ai mô tả SQL, ai chuyển hàng dữ liệu thành đối tượng Java và ai theo dõi trạng thái đối tượng để phát sinh thao tác ghi**.

Trong chương **Hệ sinh thái Java** thuộc **DATA_PERSISTENCE_FUNDAMENTALS**, việc hiểu ba cách tiếp cận này giúp chọn ranh giới persistence phù hợp, xử lý lỗi kết nối, tối ưu truy vấn, quản lý schema và không nhầm một framework ánh xạ với cơ chế bảo đảm dữ liệu của database.

## 1. Bản đồ khái niệm

**SQL trực tiếp** (*hand-written SQL*) là cách ứng dụng tự viết và gửi câu SQL qua **JDBC**, có thể dùng `Connection`, `PreparedStatement`, `ResultSet`. Spring `JdbcTemplate` giúp bớt code quản lý tài nguyên và ánh xạ hàng nhưng lập trình viên vẫn chủ động viết SQL.

**SQL mapper** là lớp hỗ trợ ánh xạ SQL và kết quả về kiểu Java. **MyBatis** gắn SQL (annotation/XML) vào mapper method; **jOOQ** cung cấp DSL SQL kiểu mạnh, có thể sinh mã bảng/cột từ schema và chuyển kết quả thành record/DTO. Hai công cụ có cách tiếp cận khác nhau nhưng đều đặt truy vấn do lập trình viên xác định ở trung tâm.

**ORM** (*Object–Relational Mapping*) ánh xạ entity và quan hệ sang bảng/hàng, đồng thời có thể theo dõi **managed entity** trong *persistence context* và sinh SQL khi **flush**. Trong Java, **Jakarta Persistence (JPA)** là đặc tả/API, **Hibernate ORM** là một implementation, còn **Spring Data JPA** là lớp repository hỗ trợ trên nền JPA. Chúng không phải cùng một thứ.

```text
                 Application / business logic
                             |
                    Persistence boundary
                       /      |       \
                      v       v        v
                 JDBC SQL  SQL mapper   ORM
                          MyBatis/jOOQ  JPA/Hibernate
                      \       |        /
                       \      |       /
                        JDBC / DB driver
                               |
                         Database server
```

| Câu hỏi | SQL trực tiếp | SQL mapper | ORM |
| --- | --- | --- | --- |
| Ai mô tả truy vấn? | Lập trình viên viết SQL | Lập trình viên viết SQL hoặc DSL | ORM sinh SQL từ thao tác entity/JPQL; vẫn có native SQL |
| Ai ánh xạ dữ liệu? | Code Java hoặc `RowMapper` | Mapper mapping / DSL projection | ORM ánh xạ entity và hỗ trợ projection |
| Ai theo dõi việc sửa object đã tải? | Không tự động | Thường không có dirty checking kiểu ORM | Persistence context theo dõi managed entity |
| Quan hệ giữa các bảng | JOIN và mapping tường minh | JOIN, result mapping, DSL | Entity association, fetch plan, cascade |
| Khả năng kiểm soát SQL | Rất trực tiếp | Rất cao | Có thể điều khiển, nhưng cần quan sát SQL được sinh |
| Transaction | JDBC hoặc transaction manager | Vẫn cần quản lý transaction | Vẫn cần transaction manager và DB commit |
| Đánh đổi thường gặp | Lặp code bind/map/tài nguyên | Học mapper DSL, cấu hình/codegen | Học entity lifecycle, flush, lazy loading, N+1 |

**Phân biệt quan trọng:** tự chuyển một hàng thành object không khiến thư viện đó trở thành ORM. Điều tạo nên khác biệt lớn của ORM đầy đủ là **trạng thái được quản lý**, ánh xạ quan hệ và cơ chế đồng bộ thay đổi trong một đơn vị công việc; không chỉ là “ít code SQL hơn”.

## 2. Cùng một bài toán để so sánh công bằng

Giả sử ứng dụng Java quản lý đơn hàng trong PostgreSQL:

```sql
CREATE TABLE shop_orders (
    order_id      BIGINT PRIMARY KEY,
    customer_id   BIGINT NOT NULL,
    status        VARCHAR(20) NOT NULL
                  CHECK (status IN ('PENDING', 'PAID', 'CANCELLED')),
    total_amount  NUMERIC(18, 2) NOT NULL CHECK (total_amount >= 0),
    version       BIGINT NOT NULL DEFAULT 0,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_shop_orders_customer_recent
ON shop_orders (customer_id, updated_at DESC, order_id DESC);
```

Hai chức năng cần triển khai:

1. **Query:** lấy tối đa 50 đơn gần nhất của khách hàng, chỉ trả `order_id`, `status`, `total_amount` và `version` để phục vụ giao diện.
2. **Command:** chuyển đơn từ `PENDING` sang `PAID`, nhưng chỉ khi đúng khách hàng và `version` chưa đổi từ lúc yêu cầu bắt đầu.

Câu đọc SQL gốc:

```sql
SELECT order_id, status, total_amount, version
FROM shop_orders
WHERE customer_id = ?
ORDER BY updated_at DESC, order_id DESC
LIMIT ?;
```

Câu ghi có điều kiện:

```sql
UPDATE shop_orders
SET status = 'PAID',
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE order_id = ?
  AND customer_id = ?
  AND status = 'PENDING'
  AND version = ?;
```

Nếu câu ghi ảnh hưởng **1 hàng**, cập nhật đã thỏa điều kiện. Nếu ảnh hưởng **0 hàng**, có thể đơn không tồn tại, không thuộc khách hàng, không còn `PENDING` hoặc version đã đổi. Khi trả lỗi API, đừng để việc phân biệt các trường hợp làm lộ đơn của người khác. `version` là công cụ **optimistic concurrency control** — không thay thế ràng buộc khóa, giao dịch và kiểm soát quyền.

## 3. SQL trực tiếp: JDBC và JdbcTemplate

JDBC đưa ra quyền điều khiển tường minh nhưng lập trình viên cần quản lý nhiều bước: mượn connection, bind tham số, đọc result set, commit/rollback khi cần và đóng tài nguyên. Ví dụ Java 17+ tự ánh xạ một kết quả đọc thành immutable record:

```java
import javax.sql.DataSource;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;

public final class JdbcOrderReader {
    public record OrderSummary(
            long orderId, String status, BigDecimal totalAmount, long version) {}

    private final DataSource dataSource;

    public JdbcOrderReader(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public List<OrderSummary> recentOrders(long customerId, int limit)
            throws SQLException {
        if (limit < 1 || limit > 50) {
            throw new IllegalArgumentException("limit phải nằm trong 1..50");
        }

        String sql = """
            SELECT order_id, status, total_amount, version
            FROM shop_orders WHERE customer_id = ?
            ORDER BY updated_at DESC, order_id DESC LIMIT ?
            """;
        List<OrderSummary> result = new ArrayList<>();

        try (Connection c = dataSource.getConnection();
             PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setLong(1, customerId);
            ps.setInt(2, limit);
            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    result.add(new OrderSummary(
                        rs.getLong("order_id"),
                        rs.getString("status"),
                        rs.getBigDecimal("total_amount"),
                        rs.getLong("version")));
                }
            }
        }
        return result;
    }
}
```

Một lệnh ghi độc lập (minh họa như một method thuộc service/repository có `DataSource`):

```java
public int markPaid(DataSource dataSource, long orderId,
                    long customerId, long expectedVersion) throws SQLException {
    String sql = """
        UPDATE shop_orders
        SET status = 'PAID', version = version + 1,
            updated_at = CURRENT_TIMESTAMP
        WHERE order_id = ? AND customer_id = ?
          AND status = 'PENDING' AND version = ?
        """;
    try (Connection c = dataSource.getConnection();
         PreparedStatement ps = c.prepareStatement(sql)) {
        ps.setLong(1, orderId);
        ps.setLong(2, customerId);
        ps.setLong(3, expectedVersion);
        return ps.executeUpdate();
    }
}
```

Ví dụ ghi này giả định kết nối ở `autoCommit=true` cho **một câu cập nhật độc lập**. Nếu nghiệp vụ còn phải cập nhật tồn kho, sổ cái hoặc outbox, không gọi từng method tự lấy một connection rồi mong chúng cùng rollback. Service phải **sở hữu một transaction chung**, gọi các thao tác trên cùng connection hoặc trong transaction manager được chia sẻ, rồi commit chỉ khi tất cả bước bắt buộc thành công.

**Lợi ích:** SQL hiển thị rõ, thuận tiện cho `EXPLAIN` và tuning; không có flush/dirty checking ngầm. **Chi phí:** nhiều code bind/map/đóng resource; dễ quên xử lý `NULL`, kiểu ngày giờ, exception hoặc đóng `ResultSet`. `try-with-resources` đặc biệt quan trọng khi dùng pool vì connection được trả về pool khi `close()`.

### JdbcTemplate vẫn là đường SQL trực tiếp

Spring `JdbcTemplate` giảm việc xử lý `Connection`, statement và `SQLException`; câu SQL và phép ánh xạ hàng vẫn do lập trình viên quy định:

```java
// jdbcTemplate, customerId và limit đã được khai báo bởi ứng dụng.
var summaries = jdbcTemplate.query(
    """
    SELECT order_id, status, total_amount, version
    FROM shop_orders WHERE customer_id = ?
    ORDER BY updated_at DESC, order_id DESC LIMIT ?
    """,
    (rs, rowNum) -> new JdbcOrderReader.OrderSummary(
        rs.getLong("order_id"),
        rs.getString("status"),
        rs.getBigDecimal("total_amount"),
        rs.getLong("version")),
    customerId, limit
);
```

Đoạn trên là ví dụ sử dụng API, không phải một lớp có thể chạy độc lập. Việc JdbcTemplate quản lý thao tác JDBC thường ngày **không tự tạo transaction đa bước**: vẫn cần cấu hình và dùng transaction manager thích hợp.

## 4. SQL mapper: MyBatis và jOOQ

### 4.1. MyBatis gắn SQL vào mapper method

MyBatis cho phép khai báo SQL qua annotation/XML, bind tham số và chuyển kết quả sang JavaBean hoặc kiểu đã cấu hình. Phương thức Java tạo ra SQL rõ ràng; nhưng **sửa object được MyBatis trả về không tự sinh UPDATE**.

```java
import java.util.List;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Result;
import org.apache.ibatis.annotations.Results;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

public interface OrderMapper {
    @Select("""
        SELECT order_id, status, total_amount, version
        FROM shop_orders
        WHERE customer_id = #{customerId}
        ORDER BY updated_at DESC, order_id DESC
        LIMIT #{limit}
        """)
    @Results({
        @Result(property = "orderId", column = "order_id"),
        @Result(property = "status", column = "status"),
        @Result(property = "totalAmount", column = "total_amount"),
        @Result(property = "version", column = "version")
    })
    List<OrderRow> recentOrders(@Param("customerId") long customerId,
                                @Param("limit") int limit);

    @Update("""
        UPDATE shop_orders
        SET status = 'PAID', version = version + 1,
            updated_at = CURRENT_TIMESTAMP
        WHERE order_id = #{orderId}
          AND customer_id = #{customerId}
          AND status = 'PENDING'
          AND version = #{expectedVersion}
        """)
    int markPaid(@Param("orderId") long orderId,
                 @Param("customerId") long customerId,
                 @Param("expectedVersion") long expectedVersion);
}
```

Để ví dụ mapping rõ nghĩa, `OrderRow` là một JavaBean có constructor không tham số và các setter:

```java
import java.math.BigDecimal;

public class OrderRow {
    private long orderId;
    private String status;
    private BigDecimal totalAmount;
    private long version;

    public OrderRow() {}
    public long getOrderId() { return orderId; }
    public void setOrderId(long value) { orderId = value; }
    public String getStatus() { return status; }
    public void setStatus(String value) { status = value; }
    public BigDecimal getTotalAmount() { return totalAmount; }
    public void setTotalAmount(BigDecimal value) { totalAmount = value; }
    public long getVersion() { return version; }
    public void setVersion(long value) { version = value; }
}
```

Ký pháp `#{customerId}` và `#{limit}` của MyBatis biểu thị bind **giá trị tham số**, không phải tự nối chuỗi SQL từ dữ liệu người dùng. MyBatis cũng có chế độ chèn nội dung SQL dạng văn bản; nếu đưa input không tin cậy trực tiếp vào tên cột, `ORDER BY` hoặc một đoạn SQL động, vẫn có thể bị SQL injection. Với tên cột/chiều sort, dùng **allowlist** từ code.

Mapper được tạo qua `SqlSession` hoặc được inject qua tích hợp với Spring. Cần quản lý session/transaction phù hợp; MyBatis **không tự biến** hai lời gọi mapper trên hai transaction khác nhau thành một đơn vị ghi nguyên tử. `int markPaid(...)` ở ví dụ là số hàng cập nhật — ứng dụng vẫn phải kiểm tra để phát hiện xung đột.

### 4.2. jOOQ sử dụng SQL DSL và schema code generation

jOOQ hỗ trợ diễn đạt SQL qua API có kiểu. Khi sinh code từ schema, tên bảng và cột được biểu diễn bằng các trường Java, giúp phát hiện nhiều lỗi tên/kiểu ở lúc biên dịch.

```java
// Minh họa: SHOP_ORDERS là table object do jOOQ codegen sinh.
var rows = dsl.select(
        SHOP_ORDERS.ORDER_ID,
        SHOP_ORDERS.STATUS,
        SHOP_ORDERS.TOTAL_AMOUNT)
    .from(SHOP_ORDERS)
    .where(SHOP_ORDERS.CUSTOMER_ID.eq(customerId))
    .orderBy(SHOP_ORDERS.UPDATED_AT.desc(),
             SHOP_ORDERS.ORDER_ID.desc())
    .limit(limit)
    .fetch();
```

Đây là đoạn sử dụng API, giả định `DSLContext dsl`, bảng `SHOP_ORDERS` đã được sinh và các biến đầu vào tồn tại. Nó không phải một lớp chạy độc lập. Khi schema thay đổi, cần quản lý migration và sinh lại mã cho phù hợp; cấu hình dialect ảnh hưởng cú pháp SQL được phát ra.

**MyBatis và jOOQ không đồng nhất:** MyBatis thường tổ chức quanh câu SQL trong mapper, còn jOOQ thường tổ chức quanh DSL mô tả SQL và các kiểu được sinh. Nhưng cả hai đều thuận tiện khi cần chủ động tối ưu JOIN, CTE, window function, phân trang hoặc query báo cáo đặc thù — không cần tạo một mạng quan hệ entity chỉ để lấy DTO.

## 5. ORM JPA/Hibernate: quản lý vòng đời entity

ORM biểu diễn hàng dữ liệu bằng entity và có cơ chế quản lý trạng thái. Một vòng đời rút gọn:

```text
Entity mới (transient)
         | persist()
         v
Managed entity <-- find()/query() -- Database
         |
         +-- gọi method sửa trạng thái
         |   ORM ghi nhận dirty checking
         |
         +-- flush() -> phát SQL để đồng bộ với DB
         +-- commit transaction
         |
         v
Detached (khi context kết thúc)
```

**Flush không phải commit.** Flush có thể gửi SQL trong transaction đang mở nhưng vẫn có thể bị rollback. Chỉnh sửa một DTO hoặc detached entity không tự tạo SQL; chỉ thay đổi **managed entity** trong context phù hợp mới được ORM theo dõi tự động.

Entity ánh xạ bảng `shop_orders`:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.math.BigDecimal;
import java.time.OffsetDateTime;

@Entity
@Table(name = "shop_orders")
public class OrderEntity {
    @Id
    @Column(name = "order_id")
    private Long id;

    @Column(name = "customer_id", nullable = false)
    private long customerId;

    @Column(nullable = false)
    private String status;

    @Column(name = "total_amount", nullable = false)
    private BigDecimal totalAmount;

    @Version
    @Column(nullable = false)
    private long version;

    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt;

    protected OrderEntity() {} // constructor phục vụ JPA

    public Long getId() { return id; }
    public long getCustomerId() { return customerId; }
    public String getStatus() { return status; }
    public long getVersion() { return version; }

    @PreUpdate
    protected void touchUpdatedAt() {
        updatedAt = OffsetDateTime.now();
    }

    public boolean markPaid() {
        if (!"PENDING".equals(status)) {
            return false;
        }
        status = "PAID";
        return true;
    }
}
```

Application service dùng Spring transaction và `EntityManager`:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class JpaOrderService {
    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public boolean markPaid(long orderId, long customerId,
                            long expectedVersion) {
        OrderEntity order = entityManager.find(OrderEntity.class, orderId);
        if (order == null || order.getCustomerId() != customerId
                || order.getVersion() != expectedVersion) {
            return false;
        }
        return order.markPaid();
    }
}
```

Khi flush/commit, Hibernate phát hiện entity đã đổi và sinh SQL cập nhật. Trường `@Version` hỗ trợ **optimistic locking**: nếu một giao dịch khác đã đổi hàng và version, ORM có thể ném `OptimisticLockException` (hoặc exception được Spring chuyển đổi). Transaction thất bại cần được rollback, sau đó tầng gọi quyết định báo conflict hoặc retry **toàn đơn vị nghiệp vụ** nếu an toàn.

**Khác biệt tinh tế:** câu JDBC/MyBatis ở phần trên kiểm tra `status='PENDING'` và `version` **trong cùng SQL UPDATE**. Đoạn ORM kiểm tra `status` trong Java dựa trên giá trị được tải, rồi sử dụng `@Version` để phát hiện ghi cạnh tranh. Không mặc định SQL được Hibernate sinh giống hệt câu UPDATE trong ví dụ trước. Nếu có yêu cầu kiểm tra điều kiện tại DB trong một lệnh nguyên tử, vẫn có thể dùng query cập nhật có điều kiện hoặc khóa/ràng buộc DB phù hợp.

JPA còn hỗ trợ truy vấn JPQL theo tên **entity/field**:

```java
var orders = entityManager.createQuery(
        """
        SELECT o FROM OrderEntity o
        WHERE o.customerId = :customerId
        ORDER BY o.updatedAt DESC, o.id DESC
        """,
        OrderEntity.class)
    .setParameter("customerId", customerId)
    .setMaxResults(50)
    .getResultList();
```

Đoạn JPQL minh họa API; phép sắp xếp theo `updatedAt DESC, id DESC` tương ứng ý định của query SQL ở phần JDBC. Trong ví dụ này, `@PreUpdate` lấy thời gian từ đồng hồ ứng dụng, còn SQL trực tiếp dùng `CURRENT_TIMESTAMP` của DB. Khi nhiều đường ghi cùng cập nhật `updated_at`, cần thống nhất nguồn thời gian và quy tắc cập nhật (chẳng hạn dùng trigger DB hoặc cơ chế ORM đã cấu hình) để tránh khác biệt thứ tự ngoài ý muốn.

## 6. ORM vẫn đòi hỏi kiến thức SQL và transaction

**Dirty checking và persistence context.** ORM giữ một danh tính entity được quản lý trong context. Điều này tiện cho use case cập nhật nhiều trường theo quy tắc domain, nhưng một batch dài với hàng nghìn managed entity có thể tiêu tốn bộ nhớ. Cân nhắc batch, `flush()/clear()`, hoặc SQL bulk phù hợp.

**Lazy loading và N+1.** Đọc 100 đơn rồi lặp qua `order.getItems()` có thể phát sinh một câu SELECT cho danh sách và thêm một SELECT cho mỗi đơn. Cần kiểm tra SQL thực tế, sử dụng fetch join, entity graph, batch fetching hoặc DTO projection. Không đổi tất cả sang `EAGER` vô điều kiện vì còn nguy cơ truy vấn lớn và JOIN không cần thiết.

**Thời điểm flush.** Gọi setter không nhất thiết chạy SQL ngay; ORM có thể flush trước query, lúc yêu cầu hoặc ở commit. Vì vậy lỗi khóa ngoại hoặc optimistic locking đôi khi chỉ xuất hiện khi flush/commit, không ở dòng đổi trường.

**Bulk update, native query và dữ liệu cũ.** Các câu UPDATE hàng loạt qua JPQL/native SQL có thể bỏ qua dirty checking của từng entity và không tự đồng bộ mọi instance trong persistence context. Cần có quy tắc `clear()/refresh()` khi cần, đồng thời bảo vệ `version` nhất quán.

**Cascade và vòng đời association.** Một thay đổi entity có thể kéo theo nhiều câu INSERT/UPDATE/DELETE, tạo khóa hoặc thời lượng transaction không như mong đợi. SQL log và metric thực tế quan trọng hơn cảm giác “chỉ gọi một method Java”.

**JPA không tự giải quyết giao dịch ngoài DB.** Email, HTTP, thanh toán và broker không bị hoàn tác cùng transaction JDBC/JPA; cần transactional outbox, idempotency hoặc quy trình bù trừ khi có side effect.

## 7. So sánh xử lý xung đột đồng thời

Giả sử hai request cùng đọc đơn ở `version=5` rồi muốn chuyển sang `PAID`:

| Công cụ | Cơ chế ứng dụng thường dùng | Tín hiệu cần xử lý |
| --- | --- | --- |
| JDBC | `UPDATE ... WHERE status='PENDING' AND version=5` | Kiểm tra `executeUpdate()` trả 1 hay 0 |
| MyBatis | SQL `@Update` cùng điều kiện | Mapper trả số hàng cập nhật |
| jOOQ | DSL diễn đạt UPDATE với điều kiện trạng thái/version | Số hàng cập nhật, SQL và transaction thật |
| JPA/Hibernate | Managed entity + `@Version`, kiểm tra điều kiện trong domain/service | Optimistic locking exception ở flush/commit khi có cạnh tranh |

Đây là cách **ngăn lost update trong use case cụ thể**, không có nghĩa đã giải quyết mọi bất biến nhiều hàng. Nếu nghiệp vụ chuyển tiền cần sửa hai tài khoản và ghi sổ cái, các thao tác bắt buộc phải cùng transaction và có chiến lược khóa/cô lập phù hợp dù dùng công cụ nào.

Khi **kết hợp JDBC/MyBatis với JPA** trong một ứng dụng, chú ý entity do ORM giữ có thể trở nên lỗi thời nếu đường SQL trực tiếp cập nhật cùng hàng. SQL trực tiếp còn có thể bỏ qua quy tắc `@Version` nếu không chủ động cập nhật và kiểm tra cột version. Phải tổ chức rõ ranh giới transaction, thứ tự ghi và cơ chế refresh/clear context khi cần.

## 8. Hiệu năng và vận hành: đo SQL thật, không đo danh tiếng framework

Không thể kết luận “JDBC luôn nhanh hơn Hibernate” hay “ORM luôn gây N+1”. Chi phí thường nằm ở số câu SQL, round-trip, số hàng tải, kế hoạch truy vấn, fetch strategy, lock wait và thời gian mượn connection.

| Workload | Điều nên đánh giá |
| --- | --- |
| Trang danh sách nhiều đơn | Chỉ chọn cột cần thiết, DTO, phân trang, index; tránh tải toàn bộ entity graph |
| Thao tác trên aggregate có nhiều quy tắc | ORM có thể giúp tổ chức vòng đời entity; quan sát fetch/cascade/SQL |
| Báo cáo CTE, window function, nhiều JOIN | SQL trực tiếp, MyBatis, jOOQ hoặc native SQL của ORM; đo `EXPLAIN` |
| Ghi batch lớn | Driver batching, flush/clear, kích thước transaction, WAL và số round-trip |
| Giao dịch bị timeout | SQL duration, lock wait, transaction duration, pool acquire/usage time |
| Đổi schema | Migration, mapper SQL, mã sinh jOOQ và entity mapping phải theo kịp |

Các thông số hữu ích: số SQL mỗi request, p95/p99 latency, bytes/rows trả về, lock wait, lỗi transaction, thời gian giữ connection, cache hit và truy vấn N+1. Không bật log tham số chứa dữ liệu nhạy cảm bừa bãi ở production.

**Migration schema là một bài toán riêng.** Hibernate có tính năng tạo/kiểm tra schema theo cấu hình nhưng không nên coi việc tự sửa schema ngầm khi khởi động là chiến lược production. Sử dụng Flyway, Liquibase hoặc cơ chế quản lý migration có kiểm soát và cập nhật đồng bộ SQL, mã sinh schema, DTO và entity. Quản lý tương thích ngược khi có nhiều phiên bản ứng dụng cùng hoạt động.

## 9. Quy tắc lựa chọn có căn cứ

| Nhu cầu | Lựa chọn thường hợp lý | Vì sao |
| --- | --- | --- |
| Dịch vụ nhỏ, ít truy vấn, muốn SQL minh bạch | JDBC / `JdbcTemplate` | Ít lớp trừu tượng, trực tiếp và dễ quan sát |
| Nhiều SQL viết tay, báo cáo đa dạng | MyBatis | Ánh xạ SQL có cấu trúc, giảm code bind/map |
| SQL giàu tính năng, cần DSL kiểu mạnh/dialect | jOOQ | Truy vấn là trung tâm, sinh field từ schema |
| Aggregate có vòng đời và quan hệ phức tạp | JPA/Hibernate | Entity mapping, persistence context, dirty checking |
| Cả giao dịch domain và báo cáo nặng | Kết hợp có chủ đích | ORM cho domain, SQL mapper/JDBC cho query tối ưu |

Một ứng dụng có thể dừng ở JDBC/JdbcTemplate mà vẫn có kiến trúc sạch; một ứng dụng ORM vẫn có thể cần SQL thủ công ở vài chỗ. Không nên xây nhiều tầng repository trừu tượng chỉ để che rằng bên dưới vẫn là các câu SELECT/UPDATE, cũng không nên lạm dụng SQL trực tiếp làm mỗi nghiệp vụ tự ghép quy tắc đồng thời ở controller.

Khi chọn công cụ, hỏi: workload chủ yếu là query tổng hợp hay thao tác trên aggregate? Đội ngũ có kỹ năng debug SQL và transaction không? Có cần dialect đặc thù không? Cần version/schema evolution và tích hợp hệ thống ngoài thế nào? Khả năng kiểm thử mapping, contention và recovery ra sao?

## 10. Bài tập thực hành

### Bài tập 1 — Nhận diện cơ chế

A dùng `PreparedStatement` đọc `ResultSet` để tạo DTO. B khai báo `@Select` với `#{customerId}` và mapper trả JavaBean. C tải entity qua `EntityManager.find()` và ORM phát `UPDATE` khi flush.

**Đáp án:** A là JDBC/SQL trực tiếp, B là MyBatis/SQL mapper, C là JPA/Hibernate/ORM.

### Bài tập 2 — Setter có ghi database không?

Code lấy một `OrderRow` từ MyBatis, gọi `row.setStatus("PAID")` rồi trả về mà không gọi mapper method ghi. Database có thay đổi không?

**Đáp án:** không chỉ vì setter; MyBatis thông thường không theo dõi dirty state như JPA. Cần gọi UPDATE tường minh. Với JPA, setter trên **managed entity** có thể được ghi khi flush trong transaction thích hợp.

### Bài tập 3 — Hai request ghi đồng thời

Hai request cùng dùng `expectedVersion=7`. Với JDBC/MyBatis, nên thêm điều kiện gì vào SQL? Với JPA/Hibernate, cơ chế nào thường phát hiện xung đột?

**Đáp án:** SQL cần `WHERE ... AND status='PENDING' AND version=7`, đồng thời `SET version=version+1` và kiểm tra số hàng cập nhật. JPA dùng `@Version` để phát hiện concurrent update ở lần flush/commit, rồi phải xử lý lỗi ở ranh giới transaction.

### Bài tập 4 — Có phải dùng một công cụ cho mọi truy vấn?

Một hệ thống có báo cáo doanh thu nhiều CTE/window function, và một nghiệp vụ xử lý aggregate đơn hàng với nhiều chuyển trạng thái. Có buộc dùng cùng một công cụ không?

**Đáp án:** không. Có thể dùng MyBatis/jOOQ hoặc JDBC cho báo cáo, ORM cho aggregate, miễn bảo đảm transaction, quyền truy cập và quy tắc cập nhật nhất quán; cần xử lý stale persistence context nếu các đường cùng đụng một entity.

### Checklist trước khi chọn hoặc tích hợp công cụ

- Có phân biệt **ai viết SQL**, **ai ánh xạ kết quả**, **ai theo dõi entity** và **ai sở hữu transaction** không?
- Đường đọc có DTO/projection phù hợp, phân trang, chỉ mục và kiểm tra quyền truy cập không?
- Đường ghi có kiểm tra status/version hoặc ràng buộc DB, khóa/cô lập và số hàng ảnh hưởng không?
- Có biết SQL thật sự được phát sinh, N+1, flush, cascade và thời gian giữ connection không?
- Khi lỗi SQL/commit, ứng dụng có rollback, phân loại lỗi, retry đúng phạm vi và xử lý kết quả không rõ không?
- Nếu kết hợp ORM với SQL mapper/JDBC, có kiểm soát stale managed entity và version bypass không?
- Schema migration, SQL mapper, jOOQ generated code và mapping entity có được cập nhật tương thích không?

**Kết luận:** **SQL trực tiếp** giúp kiểm soát truy vấn tường minh, **SQL mapper** giữ SQL ở trung tâm và giảm phần công việc mapping, còn **ORM** bổ sung ánh xạ entity được quản lý và dirty checking. Cả ba vẫn phải hiểu transaction, index, khóa, kết nối và độ bền của cơ sở dữ liệu. Chọn theo bài toán và khả năng vận hành, không chọn chỉ vì mong tránh phải học SQL.
