# Khi nào nên dùng JPA, JDBC hoặc phối hợp nhiều cách truy cập

Trong một ứng dụng Java làm việc với cơ sở dữ liệu quan hệ, **JPA** và **JDBC** giải quyết những phần khác nhau của bài toán truy cập dữ liệu. Lựa chọn phù hợp phụ thuộc vào việc ứng dụng đang cần quản lý vòng đời đối tượng nghiệp vụ, thực thi SQL chuyên biệt, xử lý khối lượng lớn hay kết hợp các nhu cầu đó.

Bài học thuộc chủ đề **Nền tảng ORM** này giúp bạn hiểu các đánh đổi, chọn công cụ theo từng luồng xử lý và phối hợp JPA với JDBC mà vẫn kiểm soát được transaction, trạng thái dữ liệu và hiệu năng.

## 1. Hiểu đúng vai trò của JPA và JDBC

### JDBC: giao tiếp trực tiếp bằng SQL

JDBC (Java Database Connectivity) là API tiêu chuẩn để Java kết nối và gửi câu lệnh tới cơ sở dữ liệu. Lập trình viên chủ động viết SQL, truyền tham số, đọc `ResultSet`, chuyển từng dòng thành đối tượng Java và quản lý tài nguyên.

Một ví dụ chỉ dùng JDBC:

```java
record CustomerRow(long id, String email) {}

Optional<CustomerRow> findCustomer(DataSource dataSource, long id)
        throws SQLException {
    String sql = "SELECT id, email FROM customers WHERE id = ?";

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql)) {

        statement.setLong(1, id);

        try (ResultSet rs = statement.executeQuery()) {
            if (!rs.next()) {
                return Optional.empty();
            }
            return Optional.of(
                    new CustomerRow(rs.getLong("id"), rs.getString("email"))
            );
        }
    }
}
```

`PreparedStatement` tách tham số khỏi nội dung SQL và giúp tránh SQL injection đối với **giá trị** được ràng buộc. `try-with-resources` đóng `ResultSet`, `PreparedStatement` và `Connection` đúng cách. Đoạn ví dụ trên hoạt động độc lập với Spring; trong ứng dụng có transaction do Spring quản lý, nên dùng công cụ tham gia transaction của Spring thay vì tự mở kết nối trong luồng nghiệp vụ.

Thư viện **Spring JDBC** (`JdbcTemplate`, `NamedParameterJdbcTemplate`) vẫn dùng JDBC bên dưới nhưng giảm mã lặp cho việc đóng tài nguyên, bind tham số và xử lý ngoại lệ. Trong thực tế, khi nói “chọn JDBC” ở ứng dụng Spring, thường có thể chọn `JdbcTemplate` trước khi tự viết JDBC thuần.

### JPA: làm việc với entity và trạng thái của chúng

JPA (Jakarta Persistence) là **đặc tả** ánh xạ đối tượng–quan hệ (ORM). Hibernate là một nhà cung cấp triển khai JPA phổ biến; Spring Data JPA xây thêm lớp repository, phân trang và cơ chế khai báo truy vấn trên nền JPA. Ba tên gọi này liên quan nhưng không đồng nghĩa.

Với JPA, ta mô hình hóa bản ghi thành `@Entity`, xác định quan hệ giữa các entity và để `EntityManager` / provider theo dõi thay đổi trong *persistence context*:

```java
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private Status status;

    @Column(name = "total_amount", nullable = false)
    private BigDecimal totalAmount;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Version
    private long version;

    protected PurchaseOrder() { } // JPA cần constructor không tham số.

    public void markPaid() {
        if (status != Status.PENDING) {
            throw new IllegalStateException("Order is not pending");
        }
        status = Status.PAID;
    }
}

enum Status {
    PENDING, PAID, CANCELLED, EXPIRED
}
```

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {
}
```

Trong một phương thức `@Transactional`, khi repository trả về một entity đang được quản lý, lời gọi `order.markPaid()` thay đổi trạng thái Java. Provider có thể nhận ra thay đổi (*dirty checking*) và phát lệnh `UPDATE` khi `flush`. `@Version` hỗ trợ kiểm soát cập nhật đồng thời theo cơ chế *optimistic locking* khi cập nhật thông qua JPA.

Điều này tiết kiệm phần lớn mã lặp cho CRUD nhưng cũng tạo thêm những khái niệm phải hiểu: entity managed/detached, lazy loading, flush, quan hệ, truy vấn phát sinh và bộ nhớ dùng cho persistence context.

## 2. So sánh các đánh đổi

| Tiêu chí | JPA / ORM | JDBC / Spring JDBC |
|---|---|---|
| Cách làm việc chính | Entity, quan hệ, thay đổi trạng thái | SQL và dữ liệu trả về theo hàng/cột |
| CRUD và luồng nghiệp vụ | Thuận tiện khi nhiều entity có quan hệ, quy tắc chuyển trạng thái | Cần viết SQL và ánh xạ dữ liệu rõ ràng |
| Truy vấn báo cáo, tổng hợp phức tạp | Có JPQL, Criteria, projection và native query, nhưng một số truy vấn khó diễn đạt | Thể hiện trực tiếp SQL, CTE, window function, truy vấn đặc thù DB |
| Kiểm soát SQL | Có thể cấu hình và tối ưu, nhưng SQL sinh ra cần được quan sát | Chủ động hoàn toàn với câu SQL viết ra |
| Quản lý trạng thái đối tượng | Persistence context, dirty checking, cascade, optimistic locking | Không tự theo dõi entity hay tự cập nhật thay đổi |
| Chi phí ánh xạ | Giảm mã thủ công nhưng có chi phí ORM và rủi ro tải thừa dữ liệu | Thường ánh xạ DTO thủ công, dễ chọn đúng cột cần đọc |
| Khả năng bảo trì | Hợp lý khi mô hình domain ổn định và logic hướng đối tượng | Hợp lý khi hợp đồng dữ liệu được định nghĩa chủ yếu bằng SQL |
| Tối ưu hiệu năng | Có batching, projection, fetch strategy; cần cấu hình, đo đạc | Dễ chọn SQL tối ưu theo trường hợp; vẫn phụ thuộc DB, index, network |
| Tính linh hoạt giữa DB | API truy cập tương đối thống nhất, vẫn có khác biệt dialect | SQL đặc thù DB có thể tạo ràng buộc với nhà cung cấp |

**Không có quy tắc “JDBC luôn nhanh hơn JPA”**: JPA có thể hiệu quả với truy vấn được thiết kế tốt; JDBC vẫn có thể chậm nếu SQL, index hoặc cách gọi DB kém. So sánh trên cùng dữ liệu, tải và yêu cầu nghiệp vụ mới có ý nghĩa.

## 3. Khi nào nên ưu tiên JPA?

### 3.1. Nghiệp vụ làm việc với entity có vòng đời

Ví dụ: đơn hàng chuyển từ `PENDING` sang `PAID` rồi `SHIPPED`; đơn có các dòng hàng, khách hàng và lịch sử trạng thái. JPA phù hợp khi logic thường xuyên đọc entity, kiểm tra điều kiện, thay đổi trạng thái và lưu lại.

Lợi ích chính:

- Model Java gần với ngôn ngữ nghiệp vụ: `Order`, `OrderItem`, `Customer`.
- Repository và ánh xạ giảm mã SQL CRUD lặp lại.
- Persistence context theo dõi thay đổi của entity được quản lý trong một transaction.
- Có thể sử dụng `@Version`, lifecycle callback, cascade khi thực sự phù hợp.
- Kết hợp tốt với transaction service để thực thi nhiều thao tác nhất quán.

Ví dụ service điều khiển trạng thái:

```java
@Service
public class PaymentService {
    private final PurchaseOrderRepository orders;

    public PaymentService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public void markPaid(long orderId) {
        PurchaseOrder order = orders.findById(orderId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Order not found: " + orderId));

        order.markPaid();
        // Không cần gọi UPDATE thủ công:
        // provider flush thay đổi của managed entity.
    }
}
```

Đoạn mã minh họa Spring Data JPA, Spring transaction và các lớp entity/repository ở phần trước; các import Spring được lược bớt để tập trung vào cơ chế.

### 3.2. Ứng dụng có nhiều chức năng CRUD và mô hình quan hệ rõ

Các màn hình quản lý danh mục, khách hàng, đơn hàng, chi tiết đơn hoặc cấu hình thường có cấu trúc dữ liệu tương đối ổn định. JPA với repository, phân trang và projection giảm công sức phát triển.

Tuy nhiên, **dùng entity để cập nhật** không có nghĩa mọi truy vấn đọc đều phải tải toàn bộ entity. Với danh sách lớn, chỉ lấy cột cần thiết bằng DTO projection; sử dụng phân trang; chủ động thiết kế cách tải quan hệ bằng `JOIN FETCH` / `@EntityGraph` khi phù hợp.

### 3.3. Những tình huống phải thận trọng với JPA

- **N+1 query:** lấy một danh sách rồi vô tình kích hoạt thêm một truy vấn cho mỗi phần tử khi truy cập quan hệ lazy.
- **Tải đồ thị quá lớn:** nhiều quan hệ eager hoặc fetch join thiếu kiểm soát có thể nhân số hàng, tăng bộ nhớ.
- **Persistence context phình to:** xử lý hàng trăm nghìn entity trong một transaction có thể giữ nhiều đối tượng managed.
- **SQL sinh ra không như mong đợi:** cần bật log SQL trong môi trường phát triển, theo dõi số câu truy vấn và xem execution plan khi tối ưu.
- **Bulk update/delete:** JPQL bulk operation hay SQL trực tiếp thường bỏ qua cơ chế theo dõi entity và lifecycle thông thường.

JPA không thay thế kiến thức SQL; hiểu SQL được thực thi, index và transaction vẫn là yêu cầu cốt lõi.

## 4. Khi nào nên ưu tiên JDBC?

### 4.1. SQL là phần quan trọng nhất của yêu cầu

Báo cáo doanh thu, thống kê nhiều tầng, CTE đệ quy, window function, chức năng đặc thù PostgreSQL/Oracle/SQL Server hoặc câu query đã được DBA tối ưu thường dễ biểu đạt trực tiếp bằng SQL.

Ví dụ một truy vấn báo cáo theo ngày trên **PostgreSQL**:

```sql
SELECT CAST(created_at AS date) AS sales_day,
       COUNT(*)                 AS order_count,
       SUM(total_amount)        AS revenue
FROM purchase_orders
WHERE status = 'PAID'
  AND created_at >= ?
  AND created_at < ?
GROUP BY CAST(created_at AS date)
ORDER BY sales_day;
```

Ta có thể map kết quả vào DTO thay vì biến mỗi hàng tổng hợp thành một entity:

```java
public record DailySales(
        LocalDate date,
        long orderCount,
        BigDecimal revenue
) {}

@Repository
public class SalesReportQuery {
    private final JdbcTemplate jdbc;

    public SalesReportQuery(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<DailySales> byDay(Instant from, Instant to) {
        String sql = """
                SELECT CAST(created_at AS date) AS sales_day,
                       COUNT(*) AS order_count,
                       SUM(total_amount) AS revenue
                FROM purchase_orders
                WHERE status = ?
                  AND created_at >= ?
                  AND created_at < ?
                GROUP BY CAST(created_at AS date)
                ORDER BY sales_day
                """;

        return jdbc.query(sql,
                (rs, index) -> new DailySales(
                        rs.getObject("sales_day", LocalDate.class),
                        rs.getLong("order_count"),
                        rs.getBigDecimal("revenue")),
                "PAID", Timestamp.from(from), Timestamp.from(to));
    }
}
```

Các mẫu dùng `record` và text block giả định Java 17+; ứng dụng Spring Boot 3 dùng các package `jakarta.persistence.*`. Với cột timestamp có múi giờ, cần thống nhất cách xác định “ngày báo cáo” và múi giờ của DB để tránh lệch nhóm ngày.

### 4.2. Đọc dữ liệu dạng bảng hoặc DTO, không cần vòng đời entity

Ví dụ: xuất dữ liệu CSV, tìm kiếm đọc nhiều bảng, dashboard, đối soát, kiểm tra trạng thái đơn giản. Nếu chỉ cần vài cột trong nhiều bảng, JDBC cho phép mô tả rõ dữ liệu và số cột được tải. Một câu truy vấn trả về DTO cũng có thể thực hiện bằng JPA projection; hãy chọn theo mức độ dễ đọc và kiểm soát SQL.

### 4.3. Thao tác tập hợp hoặc batch có lợi từ SQL chuyên biệt

Cập nhật hàng loạt có điều kiện, `INSERT ... ON CONFLICT`, batch insert, thao tác trên staging table hoặc gọi stored procedure có thể phù hợp với JDBC khi SQL đặc thù DB đem lại lợi ích cụ thể.

Ví dụ cập nhật trực tiếp các đơn quá hạn:

```sql
UPDATE purchase_orders
SET status = 'EXPIRED'
WHERE status = 'PENDING'
  AND created_at < ?;
```

Một câu `UPDATE` tập hợp thường tránh việc tải từng entity rồi sửa trong Java. Đổi lại, nó **bỏ qua** dirty checking, callback, cascade và logic kiểm tra trong phương thức entity; nếu có cột `version`, cần tự thiết kế chiến lược cập nhật/kiểm tra đồng thời tương ứng.

### 4.4. Những tình huống phải thận trọng với JDBC

JDBC không tự bảo vệ các quy tắc nghiệp vụ nằm trong entity. Lập trình viên phải chủ động tổ chức SQL, mapping, lỗi, kiểm tra thay đổi đồng thời và transaction. Khi truy vấn ngày càng nhiều, nên gom SQL theo repository/query object có mục đích rõ ràng, dùng tham số ràng buộc và viết integration test cho câu SQL quan trọng.

Đừng nối dữ liệu người dùng trực tiếp vào SQL:

```java
// Sai: giá trị email bị ghép vào cấu trúc SQL.
String unsafe = "SELECT * FROM customers WHERE email = '" + email + "'";

// Đúng: ràng buộc tham số.
List<CustomerRow> rows = jdbc.query(
        "SELECT id, email FROM customers WHERE email = ?",
        (rs, i) -> new CustomerRow(rs.getLong("id"), rs.getString("email")),
        email
);
```

Placeholder chỉ áp dụng cho **giá trị**; tên bảng, tên cột và chiều sắp xếp động cần được xác thực bằng danh sách cho phép, không lấy thẳng từ input.

## 5. Khi nào nên phối hợp JPA và JDBC?

Nhiều ứng dụng có hai kiểu tác vụ cùng lúc:

1. **Ghi giao dịch nghiệp vụ:** tạo, sửa đơn hàng, kiểm soát trạng thái → JPA phù hợp.
2. **Đọc hoặc cập nhật có SQL chuyên biệt:** báo cáo, thống kê, bulk update → JDBC hoặc native SQL phù hợp.

Không cần áp đặt một công cụ cho toàn bộ ứng dụng. Có thể tổ chức phần **write model** với JPA và phần **read model** với JDBC trong cùng một cơ sở dữ liệu; đó là cách tách trách nhiệm đọc/ghi ở mức thiết kế, chưa nhất thiết phải xây hệ thống CQRS phức tạp hay tách database.

Ví dụ bố trí thư mục:

```text
order/
  domain/
    PurchaseOrder.java
  persistence/
    PurchaseOrderRepository.java   # JPA: entity và vòng đời
    SalesReportQuery.java          # JDBC: SQL thống kê
  application/
    OrderService.java              # Transaction và quy tắc nghiệp vụ
```

### 5.1. Kết hợp trong cùng một transaction

Ví dụ: đổi trạng thái đơn bằng JPA rồi chạy một câu SQL JDBC đọc tổng số đơn đã thanh toán:

```java
@Service
public class OrderService {
    private final PurchaseOrderRepository orders;
    private final JdbcTemplate jdbc;
    private final EntityManager entityManager;

    public OrderService(
            PurchaseOrderRepository orders,
            JdbcTemplate jdbc,
            EntityManager entityManager) {
        this.orders = orders;
        this.jdbc = jdbc;
        this.entityManager = entityManager;
    }

    @Transactional
    public long markPaidAndCountPaid(long orderId) {
        PurchaseOrder order = orders.findById(orderId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Order not found: " + orderId));

        order.markPaid();

        // Đẩy các thay đổi JPA đang chờ xuống DB trước khi JDBC đọc.
        entityManager.flush();

        Long count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM purchase_orders WHERE status = ?",
                Long.class,
                "PAID");

        return count;
    }
}
```

Đoạn mã giả định JPA và `JdbcTemplate` được cấu hình cùng `DataSource` và tham gia cùng transaction do Spring quản lý (thường qua `JpaTransactionManager` trong ứng dụng dùng JPA). Khi cấu hình đúng, cả hai đường truy cập có thể dùng chung transaction database. `@Transactional` gắn vào service để transaction bao phủ toàn bộ thao tác; mã JDBC không tự gọi `commit()` hoặc `rollback()`.

**Vì sao cần `flush()`?** JPA có thể giữ thay đổi ở persistence context và chưa phát SQL `UPDATE` ngay. Một truy vấn JDBC sau đó chỉ thấy dữ liệu đã được gửi tới database theo ngữ cảnh transaction của nó. Gọi `flush()` trước truy vấn JDBC đảm bảo các thay đổi JPA đang chờ được đồng bộ xuống database; `flush` **không đồng nghĩa** với `commit`. Khi transaction rollback, các SQL đã flush vẫn được rollback theo transaction.

Không giả định hai cách truy cập tự động chung transaction nếu chúng dùng khác `DataSource`, khác transaction manager, hoặc mở `Connection` riêng không tham gia transaction Spring. Cần kiểm tra cấu hình thực tế.

### 5.2. JDBC cập nhật bảng mà JPA đang quản lý

Tình huống ngược lại dễ gây dữ liệu cũ trong bộ nhớ: đã tải `PurchaseOrder` bằng JPA, sau đó JDBC chạy `UPDATE` trực tiếp trên cùng hàng. Persistence context vẫn có thể giữ phiên bản entity trước cập nhật, vì JPA không tự biết SQL JDBC đã thay đổi DB.

Một cách thực hiện bulk update có chủ đích:

```java
@Transactional
public int expirePendingOrders(Instant cutoff) {
    // Không để các thay đổi JPA chưa ghi bị xử lý sai thứ tự.
    entityManager.flush();

    int updated = jdbc.update(
            """
            UPDATE purchase_orders
            SET status = ?
            WHERE status = ? AND created_at < ?
            """,
            "EXPIRED",
            "PENDING",
            Timestamp.from(cutoff));

    // Các entity đang managed có thể đã cũ sau SQL trực tiếp.
    entityManager.clear();
    return updated;
}
```

`clear()` làm **toàn bộ** entity managed trong persistence context trở thành detached; nó không chỉ tác động đến đơn vừa cập nhật. Vì vậy cần cân nhắc phạm vi method/transaction, không gọi bừa sau khi code khác còn kỳ vọng entity managed. Nếu chỉ có một entity, có thể dùng `refresh(entity)` cho entity đó; với luồng bulk lớn, cách đơn giản hơn là tách riêng transaction và không giữ entity liên quan đang managed.

Lưu ý: SQL trực tiếp trong ví dụ **không tăng `@Version`** và không chạy callback của JPA. Nếu nghiệp vụ phụ thuộc vào optimistic locking, lịch sử thay đổi hoặc điều kiện bất biến, phải đưa logic tương ứng vào SQL, dùng JPA bulk phù hợp, hoặc chọn đường cập nhật entity. Không trộn các cách cập nhật cùng bản ghi mà thiếu quy tắc sở hữu rõ ràng.

### 5.3. Khi nào chưa cần JDBC riêng?

Trước khi thêm repository JDBC, kiểm tra xem yêu cầu có thể giải quyết đơn giản bằng:

- JPA projection (DTO/interface projection) cho truy vấn đọc ít cột.
- JPQL cho join/filter/grouping thông thường.
- JPA native query cho SQL đặc thù nhưng vẫn muốn giữ truy vấn trong repository JPA.
- JPA batching hoặc `@Modifying` cho bulk update có kiểm soát.

Chỉ bổ sung lớp JDBC khi lợi ích về SQL, mapping, hiệu năng hoặc vận hành đủ rõ để bù cho việc phải duy trì hai cơ chế.

## 6. Những điểm phải thống nhất khi phối hợp

| Vấn đề | Rủi ro | Cách xử lý |
|---|---|---|
| Ranh giới transaction | JPA ghi và JDBC đọc/ghi ở hai transaction khác nhau | Đặt transaction ở service, cấu hình chung nguồn kết nối và transaction manager phù hợp |
| Thứ tự đồng bộ | JDBC không thấy thay đổi JPA đang chờ flush | `entityManager.flush()` trước SQL JDBC phụ thuộc vào thay đổi đó |
| Entity cũ sau JDBC | JPA vẫn giữ trạng thái trước lệnh SQL trực tiếp | `refresh()` entity liên quan hoặc `clear()` khi thực sự phù hợp |
| Khóa và tranh chấp ghi | Lost update, thay đổi cùng hàng không theo quy tắc chung | Dùng transaction, khóa, điều kiện `WHERE`, `@Version` / cột version theo thiết kế nhất quán |
| Logic nghiệp vụ bị bỏ qua | Bulk SQL vượt qua validation, callback, auditing của ORM | Định nghĩa bất biến ở service/DB, kiểm tra rõ những gì bulk SQL phải đảm bảo |
| SQL/ORM cùng truy cập bảng | Khó biết đường nào có quyền sửa trạng thái nào | Đặt quy ước rõ về chủ sở hữu cập nhật và repository theo từng tác vụ |
| Hiệu năng | N+1 ở JPA; full scan ở JDBC; transaction giữ khóa lâu | Quan sát SQL thực tế, tạo index đúng, xem `EXPLAIN`, đo dưới tải tương ứng |
| Bảo mật | SQL injection hoặc lộ dữ liệu quá mức | Bind tham số; chọn cột tối thiểu; xác thực cột/order động |
| Nhiều database | Một `@Transactional` thông thường không tự tạo tính nguyên tử giữa các DB độc lập | Xem xét transaction phân tán khi thật cần, hoặc saga/outbox và nhất quán cuối cùng |

**Quy tắc then chốt:** transaction đảm bảo ranh giới nhất quán ở database; persistence context đảm bảo trạng thái entity bên trong JPA. Hai khái niệm liên quan nhưng không thay thế cho nhau.

## 7. Quy trình chọn công cụ cho một yêu cầu

Thay vì chọn JPA hoặc JDBC theo sở thích cá nhân, đi qua các câu hỏi sau:

1. **Có cần quản lý entity và các quy tắc chuyển trạng thái không?** Nếu có, ưu tiên JPA cho đoạn nghiệp vụ đó.
2. **Kết quả chủ yếu là DTO, bảng tổng hợp, hoặc SQL chuyên biệt?** Cân nhắc JDBC, JPA projection hay native query.
3. **Có yêu cầu về hàng loạt, số lượng dữ liệu lớn, hoặc query đã được tối ưu riêng?** So sánh batch của JPA với SQL/JDBC bằng đo đạc.
4. **Hai đường truy cập có cùng bảng/transaction không?** Nếu có, thiết kế thứ tự flush, làm mới entity và quyền cập nhật.
5. **Những gì cần giữ nhất quán ở database?** Dùng constraint, khóa, điều kiện cập nhật, transaction và kiểm soát đồng thời tương ứng.
6. **Chi phí bảo trì ra sao?** Ưu tiên phương án ít cơ chế hơn khi hai cách có hiệu quả tương đương và mã vẫn dễ hiểu.

Bảng tình huống gợi ý:

| Tình huống | Điểm xuất phát hợp lý | Vì sao |
|---|---|---|
| API tạo/sửa đơn hàng, nhiều trạng thái và quan hệ | JPA | Làm việc theo entity, thay đổi trạng thái trong transaction |
| Form CRUD danh mục với phân trang | JPA + projection | Giảm mã CRUD, giới hạn dữ liệu khi đọc |
| Dashboard tổng hợp doanh thu theo ngày, nhiều join/CTE | JDBC hoặc JPA native query | SQL và DTO là trọng tâm |
| Xuất hàng triệu dòng có giới hạn bộ nhớ | JDBC streaming/fetch size hoặc JPA stream được cấu hình đúng | Cần điều khiển cách đọc và giải phóng tài nguyên |
| Cập nhật hàng loạt với điều kiện SQL rõ | JDBC hoặc JPA bulk query | Một câu lệnh tập hợp, tránh nạp từng entity |
| Cập nhật entity rồi đọc thống kê tức thời cùng transaction | JPA + JDBC | Mỗi phần dùng công cụ phù hợp, chủ động `flush` |
| Một ứng dụng có CRUD đơn giản, không có truy vấn đặc biệt | JPA **hoặc** JDBC theo nền tảng sẵn có | Tránh thêm hai stack chỉ vì một khả năng chưa cần |

## 8. Đo hiệu năng trước khi quyết định đổi stack

Nếu một endpoint chậm, đừng lập tức viết lại từ JPA sang JDBC. Xác định nút thắt thực tế:

- Endpoint chạy **bao nhiêu** SQL? Có N+1 hay nhiều lần gọi DB không?
- SQL có dùng đúng index và lọc dữ liệu sớm không? `EXPLAIN` cho biết kế hoạch thực thi.
- Có tải quá nhiều cột/hàng hoặc fetch quan hệ không cần thiết không?
- Chi phí nằm ở truy vấn, ánh xạ Java, serialization, network hay lock contention?
- Transaction có giữ mở lâu; batch size, fetch size và connection pool có hợp lý không?
- Khi so sánh hai phương án, p95 latency, throughput, CPU, bộ nhớ và độ ổn định thay đổi thế nào ở cùng dữ liệu/tải?

JPA có thể giải quyết nhiều vấn đề bằng fetch strategy, projection, query tuning, cache có chủ đích hoặc batch. JDBC phù hợp hơn khi chính lớp trừu tượng entity gây bất tiện và SQL chuyên biệt mang lại lợi ích đo được.

## 9. Các hiểu lầm thường gặp

**“Dùng JPA thì không cần học SQL.”** Sai. ORM phát SQL thay bạn, nhưng DB vẫn thực thi SQL đó. Hiểu index, join, transaction và execution plan là điều cần thiết.

**“Dùng JDBC thì tự động nhanh.”** Sai. SQL không có index, truy vấn lặp hoặc tải quá nhiều bản ghi vẫn chậm.

**“Gọi `save()` là mọi SQL đã được commit.”** Không luôn đúng. JPA có thể trì hoãn SQL đến flush; commit là bước kết thúc transaction. Cả `saveAndFlush()` và `flush()` không thay thế commit.

**“Sau JDBC update, entity JPA luôn tự cập nhật.”** Sai. Persistence context có thể giữ state cũ; cần chiến lược refresh/clear hoặc ranh giới transaction rõ.

**“`@Transactional` đủ để hai database cùng rollback.”** Sai. Một transaction manager thông thường chỉ quản lý tài nguyên mà nó được cấu hình. Nhiều nguồn dữ liệu độc lập cần thiết kế riêng.

**“Phải chọn JPA hoặc JDBC cho toàn bộ dự án.”** Không cần. Chọn theo luồng nghiệp vụ, nhưng quy định rõ trách nhiệm và tính nhất quán của từng đường truy cập.

## 10. Bài tập áp dụng

Xét hệ thống bán hàng có các yêu cầu:

- **A.** Tạo đơn, xác minh trạng thái thanh toán và cập nhật từng đơn theo quy tắc nghiệp vụ.
- **B.** Báo cáo doanh thu theo tháng, phân nhóm kênh bán và xếp hạng top sản phẩm.
- **C.** Hàng đêm chuyển hàng trăm nghìn đơn `PENDING` quá hạn sang `EXPIRED`.
- **D.** Sau khi đổi trạng thái một đơn, service phải đọc ngay số đơn `PAID` trong cùng transaction.

Hướng giải phù hợp:

- **A → JPA:** entity và transaction giúp biểu diễn quy tắc chuyển trạng thái rõ ràng; có thể dùng `@Version` để kiểm soát cập nhật đồng thời.
- **B → JDBC hoặc native query:** SQL tổng hợp và DTO trực tiếp dễ kiểm soát hơn tải một đồ thị entity rồi tính ở Java.
- **C → SQL tập hợp qua JDBC/JPQL bulk:** tránh lặp cập nhật từng entity; kiểm tra các tác động bị bỏ qua như callback/version/audit.
- **D → JPA phối hợp JDBC:** flush thay đổi JPA trước khi JDBC đọc, bảo đảm cùng cấu hình transaction và nguồn dữ liệu.

Điểm cần nhớ là **JPA tối ưu cho thao tác trên mô hình đối tượng có trạng thái; JDBC tối ưu cho quyền chủ động với SQL**. Khi một ứng dụng có cả hai nhu cầu, phối hợp là hợp lý nếu các đường truy cập được thiết kế chung về transaction, cập nhật đồng thời và tính nhất quán dữ liệu.
