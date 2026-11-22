# Giữ mô hình đọc phức tạp bằng SQL hoặc thư viện chuyên dụng

Khi chuyển một ứng dụng sang **Spring Data JDBC**, không nhất thiết phải viết lại mọi truy vấn đọc bằng repository method hoặc cố biến mọi kết quả thành aggregate. Spring Data JDBC phù hợp với persistence theo aggregate root; các màn hình tìm kiếm, báo cáo và truy vấn đọc nhiều bảng có thể tiếp tục dùng SQL tường minh hoặc một thư viện chuyên dụng như **JdbcTemplate, MyBatis hoặc jOOQ**.

Cách tiếp cận này giúp chuyển đổi từng phần: Spring Data JDBC quản lý những aggregate đã được chuyển sang mô hình mới, trong khi read model phức tạp vẫn được phục vụ bởi query hiện có. Điều quan trọng là xác định ranh giới đọc/ghi, giữ transaction và mapping nhất quán, đồng thời kiểm thử các đường dữ liệu đi qua cả hai công nghệ.

Bài này giải thích vì sao nên giữ các truy vấn đọc phức tạp, chọn công cụ phù hợp, tổ chức read model riêng, phối hợp với transaction Spring và lập kế hoạch chuyển đổi mà không tạo ra hai nguồn quy tắc persistence khó kiểm soát.

## 1. Không phải truy vấn đọc nào cũng cần dựng aggregate

Spring Data JDBC tổ chức dữ liệu theo aggregate root. Repository thường trả về aggregate được ánh xạ từ một root cùng các entity thuộc aggregate đó. Cách này phù hợp với use case cần đọc và thay đổi trạng thái domain theo invariant.

Một màn hình quản trị có thể cần dữ liệu từ nhiều aggregate hoặc bảng:

- Mã đơn hàng và trạng thái.
- Tên khách hàng.
- Trạng thái thanh toán.
- Tên nhân viên xử lý.
- Tổng số dòng hàng.
- Tổng tiền và thông tin vận chuyển.

Kết quả đó là một **read model** phục vụ màn hình, không nhất thiết là một aggregate cần được lưu. Dựng toàn bộ PurchaseOrder, Customer, Payment và các collection con chỉ để hiển thị một bảng có thể tải nhiều dữ liệu hơn cần thiết và làm query khó tối ưu.

Một câu SQL join có thể lấy đúng projection:

~~~sql
SELECT
    o.id AS order_id,
    o.order_number,
    o.status,
    c.display_name AS customer_name,
    p.payment_status,
    o.total,
    COUNT(l.line_no) AS line_count
FROM purchase_orders o
JOIN customers c ON c.id = o.customer_id
LEFT JOIN payments p ON p.order_id = o.id
LEFT JOIN order_lines l ON l.order_id = o.id
WHERE o.created_at >= :from_time
  AND o.created_at < :to_time
GROUP BY
    o.id,
    o.order_number,
    o.status,
    c.display_name,
    p.payment_status,
    o.total
ORDER BY o.created_at DESC, o.id ASC;
~~~

Query này tạo ra một tập kết quả phẳng dành cho báo cáo. Nó không cần trở thành object graph domain.

## 2. Phân biệt write model và read model

Một cách tổ chức hữu ích khi chuyển đổi là phân chia hai trách nhiệm:

- **Write model**: dùng aggregate root, domain rule, optimistic locking và Spring Data JDBC repository để thay đổi dữ liệu.
- **Read model**: dùng projection/DTO được thiết kế theo màn hình, báo cáo hoặc nhu cầu tìm kiếm; có thể được truy vấn bằng SQL hoặc thư viện chuyên dụng.

~~~mermaid
flowchart TD
    A[Controller / API / Job] --> B[Application Service]
    B --> C[Write path]
    B --> D[Read path]
    C --> E[Spring Data JDBC Repository]
    E --> F[Aggregate Root]
    D --> G[JdbcTemplate / MyBatis / jOOQ]
    G --> H[DTO / Read Projection]
    F --> I[(Shared Database)]
    H --> I
~~~

Đây là sự phân chia trách nhiệm ở cấp ứng dụng. Nó không bắt buộc phải dùng hai database và cũng không tự động đồng nghĩa với event sourcing. Cả hai đường có thể đọc/ghi cùng một database, cùng schema và cùng transaction manager.

Ví dụ:

| Use case | Công cụ phù hợp để bắt đầu |
|---|---|
| Tạo đơn hàng và các dòng hàng | Spring Data JDBC |
| Đổi trạng thái theo domain rule | Spring Data JDBC |
| Đọc đơn hàng theo ID để thực hiện nghiệp vụ | Spring Data JDBC |
| Bảng tìm kiếm kết hợp khách hàng và thanh toán | SQL projection hoặc MyBatis |
| Báo cáo doanh thu theo tháng | SQL, jOOQ hoặc MyBatis |
| Dashboard tổng hợp nhiều bảng | Read model chuyên biệt |
| Bulk update đặc thù | SQL/JDBC có kiểm soát, nếu đã bảo vệ invariant và version |

Không cần ép mọi truy vấn vào một abstraction. Chọn công cụ dựa trên hình dạng kết quả và trách nhiệm của use case.

## 3. Vì sao nên giữ SQL đọc phức tạp trong giai đoạn chuyển đổi?

Một ứng dụng cũ có thể đã có những truy vấn đọc được tối ưu qua nhiều năm. Chúng có thể sử dụng:

- Nhiều JOIN và subquery.
- Common Table Expression (CTE).
- Window function.
- GROUP BY, HAVING và aggregate function.
- Full-text search hoặc JSON operator.
- Stored procedure hoặc database view.
- Bộ lọc động và sort nhiều trường.
- Pagination hoặc keyset pagination.
- Hint và cú pháp đặc thù DBMS.
- Projection chỉ lấy một phần nhỏ cột.

Viết lại những query này cùng lúc với việc chuyển đổi persistence làm tăng phạm vi thay đổi và khó xác định nguyên nhân nếu hiệu năng hoặc kết quả khác trước.

Giữ read query đã được kiểm chứng mang lại một số lợi ích:

1. Giảm số use case phải chuyển đổi trong cùng một đợt.
2. Bảo toàn execution plan và semantics đã biết.
3. Cho phép tập trung chuyển write path sang aggregate model.
4. Tạo cơ hội so sánh kết quả cũ/mới bằng contract test.
5. Tránh biến read model thành aggregate chỉ để phù hợp với repository CRUD.

Giữ SQL cũ không có nghĩa là giữ mãi mọi chi tiết cũ. Hãy đưa query vào một adapter có contract rõ ràng, đo hiệu năng và chuyển đổi sau khi có lý do cụ thể.

## 4. Thiết kế DTO riêng cho read model

Không nên tái sử dụng aggregate root làm kiểu trả về cho mọi màn hình. Một DTO thể hiện đúng dữ liệu mà query trả về sẽ giảm phụ thuộc giữa UI và domain model.

Ví dụ:

~~~java
import java.math.BigDecimal;

public record OrderSearchRow(
        Long orderId,
        String orderNumber,
        String orderStatus,
        String customerName,
        String paymentStatus,
        BigDecimal total,
        Long lineCount
) {}
~~~

Read service:

~~~java
public interface OrderSearch {
    List<OrderSearchRow> search(OrderSearchCriteria criteria);
}
~~~

Criteria:

~~~java
import java.time.Instant;

public record OrderSearchCriteria(
        String status,
        Instant fromTime,
        Instant toTime,
        String customerName,
        int page,
        int size
) {}
~~~

DTO chỉ chứa dữ liệu cần cho truy vấn. Nếu màn hình cần thêm một cột, có thể thay đổi projection và mapper mà không làm thay đổi aggregate PurchaseOrder.

Một read model có thể chứa dữ liệu tổng hợp hoặc giá trị hiển thị đã tính toán. Không nên dùng DTO đó để gọi repository.save như thể nó là aggregate đầy đủ.

## 5. Chọn công cụ theo mức độ phức tạp của SQL

Không có một công cụ duy nhất phù hợp cho mọi query.

| Công cụ | Phù hợp khi | Chi phí cần cân nhắc |
|---|---|---|
| Derived query của Spring Data JDBC | Điều kiện đơn giản dựa trên property | Khả năng diễn đạt query có giới hạn |
| @Query của Spring Data JDBC | SQL tùy chỉnh vừa phải, kết quả mapping đơn giản | SQL viết tay vẫn phụ thuộc DBMS |
| JdbcTemplate | Cần kiểm soát SQL và RowMapper trực tiếp | Tự quản lý mapping và query structure |
| NamedParameterJdbcTemplate | Query SQL tường minh có nhiều tham số | Cần quản lý dynamic fragments và mapping |
| MyBatis | Nhiều mapper, dynamic SQL, resultMap hoặc SQL legacy | Phải duy trì mapper, TypeHandler và cache |
| jOOQ | Cần SQL DSL có kiểu và truy vấn phức tạp | Cần quản lý code generation, cấu hình và edition phù hợp |
| Database view | Query đọc ổn định được dùng ở nhiều nơi | Schema/view migration và portability |
| Stored procedure | Logic SQL cần chạy gần database hoặc đã là contract legacy | Khó kiểm thử/di chuyển hơn nếu phụ thuộc DBMS |

Bắt đầu với công cụ đơn giản nhất đáp ứng yêu cầu. Nếu một query có thể biểu diễn rõ bằng JdbcTemplate và RowMapper, không nhất thiết thêm MyBatis hoặc jOOQ chỉ để viết một câu SELECT.

## 6. Giữ query bằng JdbcTemplate

JdbcTemplate phù hợp khi cần SQL tường minh nhưng số lượng mapper không lớn.

RowMapper:

~~~java
import java.sql.ResultSet;
import java.sql.SQLException;
import org.springframework.jdbc.core.RowMapper;

public class OrderSearchRowMapper
        implements RowMapper<OrderSearchRow> {

    @Override
    public OrderSearchRow mapRow(ResultSet rs, int rowNum)
            throws SQLException {
        return new OrderSearchRow(
                rs.getLong("order_id"),
                rs.getString("order_number"),
                rs.getString("order_status"),
                rs.getString("customer_name"),
                rs.getString("payment_status"),
                rs.getBigDecimal("total"),
                rs.getLong("line_count")
        );
    }
}
~~~

Read adapter:

~~~java
@Repository
public class JdbcOrderSearch implements OrderSearch {

    private final NamedParameterJdbcTemplate jdbc;

    public JdbcOrderSearch(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public List<OrderSearchRow> search(OrderSearchCriteria criteria) {
        String sql = """
            SELECT
                o.id AS order_id,
                o.order_number,
                o.status AS order_status,
                c.display_name AS customer_name,
                p.payment_status,
                o.total,
                COUNT(l.line_no) AS line_count
            FROM purchase_orders o
            JOIN customers c ON c.id = o.customer_id
            LEFT JOIN payments p ON p.order_id = o.id
            LEFT JOIN order_lines l ON l.order_id = o.id
            WHERE (:status IS NULL OR o.status = :status)
              AND o.created_at >= :from_time
              AND o.created_at < :to_time
            GROUP BY
                o.id, o.order_number, o.status,
                c.display_name, p.payment_status, o.total
            ORDER BY o.id DESC
            """;

        var parameters = new MapSqlParameterSource()
                .addValue("status", criteria.status())
                .addValue("from_time", criteria.fromTime())
                .addValue("to_time", criteria.toTime());

        return jdbc.query(sql, parameters, new OrderSearchRowMapper());
    }
}
~~~

Đây là ví dụ cấu trúc. Query thực tế cần xử lý paging, sort, null semantics và khác biệt SQL của DBMS. Nếu criteria có nhiều bộ lọc tùy chọn, có thể build các fragment cố định và bind value thay vì viết một biểu thức OR cho mọi trường hợp.

Tách query vào adapter giúp application service không phụ thuộc trực tiếp JdbcTemplate và cho phép thay implementation sau này.

## 7. Giữ query bằng MyBatis

MyBatis phù hợp khi có nhiều SQL statement, dynamic SQL hoặc result mapping phức tạp. Mapper interface biểu diễn contract:

~~~java
@Mapper
public interface OrderSearchMapper {
    List<OrderSearchRow> search(OrderSearchCriteria criteria);
}
~~~

XML mapper có thể chứa SQL:

~~~xml
<mapper namespace="com.example.orders.read.OrderSearchMapper">

  <select id="search" resultType="com.example.orders.read.OrderSearchRow">
    SELECT
      o.id AS orderId,
      o.order_number AS orderNumber,
      o.status AS orderStatus,
      c.display_name AS customerName,
      p.payment_status AS paymentStatus,
      o.total AS total
    FROM purchase_orders o
    JOIN customers c ON c.id = o.customer_id
    LEFT JOIN payments p ON p.order_id = o.id
    <where>
      <if test="status != null and status != ''">
        AND o.status = #{status}
      </if>
      <if test="fromTime != null">
        AND o.created_at >= #{fromTime}
      </if>
      <if test="toTime != null">
        AND o.created_at < #{toTime}
      </if>
    </where>
    ORDER BY o.id DESC
  </select>

</mapper>
~~~

MyBatis cho phép dùng resultMap nếu DTO có constructor mapping, nested object hoặc collection. Khi query trả projection phẳng, resultType cùng alias rõ ràng thường đủ.

Các value dùng parameter binding. Không chèn dữ liệu request trực tiếp vào SQL structure. Identifier động, sort column và direction phải đến từ whitelist.

Nếu ứng dụng đã có MyBatis mapper hoạt động ổn định, có thể giữ chúng trong giai đoạn chuyển đổi và chỉ thay write path cần thiết.

## 8. Giữ query bằng jOOQ

jOOQ cung cấp SQL DSL để tạo truy vấn có cấu trúc bằng Java. Khi schema được code generation, table và field có thể được tham chiếu bằng kiểu Java thay vì viết tên cột dưới dạng chuỗi.

Ví dụ khái quát:

~~~java
public List<OrderSearchRow> search(OrderSearchCriteria criteria) {
    return dsl
            .select(
                    PURCHASE_ORDERS.ID,
                    PURCHASE_ORDERS.ORDER_NUMBER,
                    CUSTOMERS.DISPLAY_NAME,
                    PURCHASE_ORDERS.TOTAL
            )
            .from(PURCHASE_ORDERS)
            .join(CUSTOMERS)
                .on(CUSTOMERS.ID.eq(PURCHASE_ORDERS.CUSTOMER_ID))
            .where(PURCHASE_ORDERS.STATUS.eq(criteria.status()))
            .fetch(record -> new OrderSearchRow(
                    record.get(PURCHASE_ORDERS.ID),
                    record.get(PURCHASE_ORDERS.ORDER_NUMBER),
                    null,
                    record.get(CUSTOMERS.DISPLAY_NAME),
                    null,
                    record.get(PURCHASE_ORDERS.TOTAL),
                    null
            ));
}
~~~

Tên generated table/field phụ thuộc package và cấu hình code generation của dự án. Ví dụ minh họa phong cách DSL; query thực tế cần chọn join, filter và mapping đầy đủ.

jOOQ có thể giảm lỗi tên cột trong code và hỗ trợ dialect rendering, nhưng không tự loại bỏ mọi khác biệt schema hoặc semantics. Cần cấu hình DSLContext dùng DataSource/transaction integration phù hợp với Spring nếu muốn cùng tham gia transaction với Spring Data JDBC.

## 9. Phân chia package để read path không lẫn với aggregate persistence

Một cấu trúc có thể dùng:

~~~text
com.example.orders
  domain/
    PurchaseOrder.java
    OrderLine.java
  application/
    OrderCommandService.java
    OrderSearchService.java
  persistence/
    aggregate/
      PurchaseOrderRepository.java
    read/
      OrderSearch.java
      OrderSearchRow.java
      JdbcOrderSearch.java
      OrderSearchMapper.java
      OrderSearchMapper.xml
~~~

Không bắt buộc phải dùng đúng tên package trên. Mục tiêu là để người đọc nhận biết:

- Repository aggregate sở hữu các thao tác ghi domain.
- Read adapter sở hữu query/projection.
- Application service điều phối use case.
- DTO không bị nhầm là aggregate root.
- SQL được gom ở nơi có thể review và kiểm thử.

Nếu một read adapter chỉ dùng cho báo cáo, tên như OrderReportQuery hoặc OrderSearchReadRepository giúp biểu đạt rõ vai trò hơn một repository tổng quát.

## 10. Không dùng read projection để cập nhật aggregate

Một query join có thể trả về OrderSearchRow gồm thông tin từ nhiều bảng. DTO đó không phải trạng thái đầy đủ của PurchaseOrder.

Không làm như sau:

~~~java
OrderSearchRow row = orderSearch.search(criteria).getFirst();

// Không chuyển DTO tổng hợp thành aggregate để save trực tiếp.
purchaseOrderRepository.save(convertToPurchaseOrder(row));
~~~

DTO có thể thiếu version, child collection, invariant hoặc property cần thiết cho domain. Việc dựng aggregate từ projection có thể ghi đè dữ liệu bằng null hoặc trạng thái mặc định.

Nếu use case cần thay đổi đơn hàng:

1. Đọc aggregate root qua repository.
2. Gọi hành vi domain để thay đổi trạng thái.
3. Lưu aggregate qua repository.
4. Đọc lại read projection nếu response cần dữ liệu join.

Giữ read model và write model tách biệt giúp tránh cập nhật domain từ một góc nhìn dữ liệu không đầy đủ.

## 11. Transaction chung giữa Spring Data JDBC và query adapter

Nếu một use case cần ghi aggregate rồi thực hiện thêm SQL trong cùng transaction, các công cụ có thể phối hợp qua transaction Spring khi cấu hình đúng.

Điều kiện quan trọng:

- Cùng sử dụng DataSource được quản lý bởi Spring.
- Transaction manager quản lý DataSource đó.
- JdbcTemplate/NamedParameterJdbcTemplate lấy connection theo cơ chế Spring JDBC.
- MyBatis sử dụng tích hợp MyBatis-Spring như SqlSessionTemplate/mapper proxy.
- jOOQ được cấu hình với transaction-aware connection/provider phù hợp.
- Method nghiệp vụ chạy qua Spring transaction proxy.

Ví dụ application service:

~~~java
@Service
public class OrderCommandService {

    private final PurchaseOrderRepository orders;
    private final OrderAuditWriter auditWriter;

    public OrderCommandService(
            PurchaseOrderRepository orders,
            OrderAuditWriter auditWriter
    ) {
        this.orders = orders;
        this.auditWriter = auditWriter;
    }

    @Transactional
    public PurchaseOrder approve(Long id) {
        PurchaseOrder current = orders.findById(id).orElseThrow();

        PurchaseOrder approved = current.approve();

        PurchaseOrder saved = orders.save(approved);

        auditWriter.recordApproval(saved.id(), saved.version());

        return saved;
    }
}
~~~

Nếu auditWriter dùng JdbcTemplate/MyBatis/jOOQ được cấu hình trên cùng DataSource và transaction manager, thao tác audit có thể commit hoặc rollback cùng aggregate save.

Nếu query adapter dùng DataSource khác, read replica hoặc transaction manager khác, không được mặc định rằng cùng annotation @Transactional tạo một transaction nguyên tử giữa các nguồn dữ liệu.

## 12. Đọc ngay sau khi ghi và consistency

Khi ghi aggregate rồi đọc read model ngay sau đó, kết quả phụ thuộc nơi query chạy:

- Cùng database primary và cùng transaction: query có thể nhìn thấy thay đổi chưa commit của chính transaction theo isolation/database semantics.
- Cùng primary nhưng transaction khác: chỉ thấy dữ liệu đã commit theo isolation.
- Read replica: có thể chưa nhận replication event và trả dữ liệu cũ.
- Cache: có thể trả snapshot cũ nếu chưa invalidated.
- Materialized view: có thể cần refresh theo lịch hoặc cơ chế riêng.

Ví dụ use case tạo đơn hàng rồi trả về màn hình chi tiết. Nếu read adapter đọc từ replica có độ trễ, response có thể chưa thấy đơn vừa tạo. Có thể trả aggregate vừa lưu, đọc từ primary hoặc thiết kế consistency contract phù hợp.

Không coi một read query chạy qua thư viện khác là tự động nhất quán chỉ vì nó dùng chung database server.

## 13. Cache khi nhiều công cụ cùng đọc và ghi

Nếu Spring Data JDBC ghi bảng mà MyBatis hoặc read adapter khác cache kết quả, cache không tự biết dữ liệu đã đổi.

Các loại cache có thể xuất hiện:

- MyBatis local cache theo SqlSession.
- MyBatis second-level cache theo mapper namespace nếu bật.
- Cache trong application service.
- Distributed cache.
- Cache của API gateway hoặc client.
- Materialized view hoặc bảng read model cập nhật bất đồng bộ.

Nếu dữ liệu được ghi qua nhiều đường, cần quy định invalidation chung. Đừng giả định một mapper update sẽ xóa cache của mapper khác hoặc repository save sẽ làm mới distributed cache.

Cách tiếp cận:

1. Chỉ bật cache khi đã đo được lợi ích.
2. Xác định mọi writer của dữ liệu.
3. Định nghĩa sự kiện hoặc cơ chế invalidation.
4. Kiểm thử đọc sau ghi qua từng adapter.
5. Cân nhắc outbox nếu invalidation phải được phát hành tin cậy sau commit.

Nếu không có nhu cầu cache rõ ràng, không bật cache cho read model thay đổi thường xuyên qua nhiều persistence path.

## 14. SQL đặc thù database và portability

Read query hiện tại có thể dùng cú pháp riêng như:

- JSON operator.
- CTE hoặc recursive query.
- Window function.
- Full-text search.
- Pagination syntax.
- Optimizer hint.
- Stored procedure.
- Function hoặc type riêng của DBMS.

Giữ query hiện có trong giai đoạn chuyển đổi có thể bảo toàn hành vi, nhưng cũng giữ lại phụ thuộc vào database. Nếu ứng dụng cần hỗ trợ nhiều DBMS, hãy ghi rõ query nào là portable và query nào vendor-specific.

Các lựa chọn:

- Dùng cú pháp SQL chuẩn cho phần truy vấn chung.
- Dùng database view để đóng gói một projection ổn định.
- Tách query theo DBMS khi khác biệt thực sự cần thiết.
- Dùng dialect rendering của jOOQ nếu phù hợp.
- Dùng custom repository adapter để cô lập SQL đặc thù.
- Chạy integration test trên từng DBMS được hỗ trợ.

Không nên chỉ test query trên H2 nếu production dùng PostgreSQL, MySQL, SQL Server hoặc Oracle. Hành vi kiểu dữ liệu, JSON, timezone, collation và execution plan có thể khác.

## 15. Dynamic filters và bảo mật

Query đọc phức tạp thường có filter và sort động. Giá trị phải được bind bằng parameter; identifier phải được whitelist.

Ví dụ NamedParameterJdbcTemplate:

~~~java
StringBuilder sql = new StringBuilder("""
    SELECT id, order_number, status
    FROM purchase_orders
    WHERE 1 = 1
    """);

MapSqlParameterSource parameters = new MapSqlParameterSource();

if (criteria.status() != null) {
    sql.append(" AND status = :status");
    parameters.addValue("status", criteria.status());
}

if (criteria.fromTime() != null) {
    sql.append(" AND created_at >= :fromTime");
    parameters.addValue("fromTime", criteria.fromTime());
}
~~~

Nếu sort động, ánh xạ lựa chọn client sang tên cột cố định:

~~~java
String sortColumn = switch (requestedSort) {
    case "created" -> "created_at";
    case "number" -> "order_number";
    case "total" -> "total";
    default -> throw new IllegalArgumentException("Unsupported sort");
};
~~~

Không nối trực tiếp tên cột do client gửi vào SQL. Parameter binding không thể thay tên bảng/cột hoặc keyword.

Đối với dữ liệu nhiều tenant, điều kiện tenant phải lấy từ security context đã xác thực, không tin một tenant ID tùy ý do client gửi.

## 16. Giữ nguyên contract của query cũ

Trong quá trình chuyển đổi, query không chỉ có SQL. Nó còn có contract về:

- Tên field và kiểu dữ liệu trong kết quả.
- Nullability.
- Thứ tự sắp xếp.
- Pagination boundary.
- Cách xử lý filter rỗng.
- Timezone và khoảng ngày.
- Quyền truy cập và tenant filter.
- Quy tắc tổng hợp và làm tròn.
- Xử lý duplicate row từ JOIN.
- Hành vi khi không có kết quả.

Ví dụ, hai query cùng trả danh sách đơn hàng nhưng một query sắp xếp theo created_at rồi id, query còn lại chỉ sort theo created_at. Khi có timestamp trùng nhau, thứ tự trang có thể khác.

Hãy viết contract test cho kết quả, không chỉ kiểm tra SQL chạy thành công. Nếu thay mapper cũ bằng adapter mới, so sánh cùng input và dữ liệu fixture để xác nhận output giữ đúng semantics.

## 17. Migration từng phần: giữ read query, chuyển write path

Không cần chuyển toàn bộ ứng dụng trong một lần. Một lộ trình có thể là:

~~~mermaid
flowchart TD
    A[Hệ thống hiện tại] --> B[Đóng gói read SQL thành adapter]
    B --> C[Thêm contract và integration tests]
    C --> D[Chuyển một aggregate write sang Spring Data JDBC]
    D --> E[Kiểm tra read-after-write và transaction]
    E --> F[Chuyển các write use case tiếp theo]
    F --> G[Đánh giá query cũ và tối ưu riêng khi có số liệu]
~~~

Các bước cụ thể:

1. **Liệt kê query hiện tại**: phân loại CRUD aggregate, tìm kiếm, báo cáo, bulk và SQL đặc thù.
2. **Xác định owner**: mỗi aggregate có một đường ghi chuẩn; read adapter chỉ đọc nếu không có lý do đặc biệt.
3. **Đóng gói SQL cũ**: đưa query vào mapper/DAO/service adapter thay vì để controller gọi trực tiếp.
4. **Tạo DTO/read contract**: định nghĩa rõ cột, kiểu, nullability và sort.
5. **Viết test trước khi thay đổi**: kiểm tra kết quả query cũ trên database mục tiêu.
6. **Chuyển write path từng aggregate**: dùng Spring Data JDBC repository và domain behavior.
7. **Kiểm tra transaction**: xác nhận repository và SQL adapter cùng rollback khi cần.
8. **Kiểm tra read-after-write**: xác định primary, replica và cache.
9. **Theo dõi hiệu năng**: đo latency, rows read, execution plan và connection usage.
10. **Gỡ code cũ có chủ đích**: chỉ xóa query cũ khi adapter mới đã đáp ứng contract và được kiểm chứng.

Không chuyển đồng thời tất cả query, schema và transaction configuration nếu không cần thiết. Chuyển đổi nhỏ giúp xác định thay đổi nào gây ra lỗi.

## 18. Tổ chức interface để có thể thay công nghệ

Application service nên phụ thuộc vào interface của use case, không phụ thuộc trực tiếp thư viện SQL:

~~~java
public interface OrderSearch {
    Page<OrderSearchRow> search(
            OrderSearchCriteria criteria,
            Pageable pageable
    );
}
~~~

Implementation ban đầu có thể dùng MyBatis:

~~~java
@Repository
public class MyBatisOrderSearch implements OrderSearch {
    private final OrderSearchMapper mapper;

    public MyBatisOrderSearch(OrderSearchMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public Page<OrderSearchRow> search(
            OrderSearchCriteria criteria,
            Pageable pageable
    ) {
        // Gọi mapper lấy content và count theo query contract.
        throw new UnsupportedOperationException("Illustrative example");
    }
}
~~~

Sau này có thể thay bằng JdbcTemplate hoặc jOOQ mà không phải sửa controller và application service, miễn contract không đổi.

Ví dụ implementation trên cố ý để phần content/count ở dạng minh họa vì SQL phân trang và count query phụ thuộc query cụ thể. Trong code thật, không để UnsupportedOperationException; triển khai cả truy vấn dữ liệu và truy vấn đếm, hoặc dùng cursor/keyset nếu đó là contract.

Không cần tạo interface cho mọi câu SELECT nhỏ. Abstraction hữu ích khi nó cô lập công nghệ hoặc có nhiều implementation/test seam thực sự cần thiết.

## 19. Count query và pagination

Một read model phân trang thường cần hai query:

- Query lấy content của trang.
- Query đếm tổng số hàng phù hợp nếu API cần total.

Với JOIN một-nhiều, count có thể đếm duplicate rows nếu không đếm theo root ID hoặc dùng subquery DISTINCT. Ví dụ:

~~~sql
SELECT COUNT(DISTINCT o.id)
FROM purchase_orders o
JOIN customers c ON c.id = o.customer_id
LEFT JOIN order_lines l ON l.order_id = o.id
WHERE o.status = :status;
~~~

Query content có thể GROUP BY hoặc dùng window function; count query cần giữ cùng filter semantics. Đừng copy nguyên query content rồi chỉ bỏ LIMIT nếu nó có GROUP BY/HAVING phức tạp.

Với dữ liệu lớn, có thể cân nhắc Slice/cursor hoặc keyset pagination thay vì luôn tính total. Contract API cần nói rõ có total hay không.

## 20. Read query có thể dùng view hoặc read table

Khi một projection được dùng bởi nhiều màn hình và thay đổi ít, database view có thể đóng gói logic join:

~~~sql
CREATE VIEW order_search_view AS
SELECT
    o.id AS order_id,
    o.order_number,
    o.status,
    c.display_name AS customer_name,
    o.total
FROM purchase_orders o
JOIN customers c ON c.id = o.customer_id;
~~~

Adapter có thể truy vấn view như một nguồn dữ liệu đọc. View thường phản ánh dữ liệu hiện tại khi được query, nhưng materialized view có thể cần refresh và có độ trễ.

Nếu query tổng hợp rất nặng, có thể duy trì một read table/projection được cập nhật bởi application event hoặc job. Khi đó phải định nghĩa consistency model, retry, rebuild và xử lý sự kiện bị lặp.

Không tạo read model riêng chỉ vì có thể. Chỉ dùng khi query hiện tại có chi phí hoặc độ phức tạp đủ lớn để biện minh cho một bản sao dữ liệu.

## 21. Transaction và nhiều DataSource

Một ứng dụng có thể đọc từ primary và replica hoặc từ nhiều database. Cần phân biệt:

- Cùng DataSource và transaction manager: các thao tác JDBC có thể tham gia cùng transaction Spring.
- Hai DataSource riêng: một local JDBC transaction thông thường không tự làm chúng atomic.
- Read replica: có thể trả dữ liệu cũ sau write do replication lag.
- External search engine: cần consistency strategy riêng, thường cập nhật bất đồng bộ.

Nếu use case ghi aggregate rồi ghi thêm một database khác, đừng giả định @Transactional đơn giản sẽ bảo đảm atomicity xuyên hai nguồn. Cần transaction coordinator phù hợp hoặc thiết kế outbox/saga theo nghiệp vụ.

Nếu query read phức tạp chỉ cần dữ liệu đã commit, đọc replica có thể hợp lý. Nếu response phải thấy ngay write vừa thực hiện, đọc primary hoặc dùng chiến lược read-your-writes.

## 22. Đo hiệu năng và quan sát read model

Giữ SQL cũ có thể bảo toàn hiệu năng, nhưng cần tiếp tục đo sau khi thay write path hoặc schema.

Theo dõi:

- p50, p95 và p99 latency.
- Số hàng đọc và số cột trả về.
- Số lần query cho một request.
- Execution plan và index usage.
- Database CPU, I/O và lock wait.
- Connection pool active/pending.
- Cache hit/miss nếu có cache.
- Replica lag nếu đọc từ replica.
- Tỷ lệ timeout và query cancellation.

Một query join có thể nhanh ở dataset nhỏ nhưng chậm khi cardinality tăng. Hãy chạy EXPLAIN/EXPLAIN ANALYZE theo database, kiểm tra index và đo trên dữ liệu đại diện.

Không bật log parameter nhạy cảm trong production chỉ để quan sát query. Dùng metrics/tracing và logging có mask phù hợp.

## 23. Kiểm thử khi giữ read query và chuyển write path

Một bộ integration test nên bảo vệ contract qua cả hai đường:

| Test | Điều cần xác nhận |
|---|---|
| Read query baseline | Query cũ trả đúng DTO, filter và sort |
| Aggregate save | Spring Data JDBC lưu root/child theo mapping |
| Read-after-write | Read adapter thấy dữ liệu mới theo consistency contract |
| Transaction rollback | Write aggregate và SQL phụ rollback cùng nhau khi dùng chung transaction |
| Version | Update qua repository giữ optimistic locking |
| Pagination | Content/count nhất quán và sort ổn định |
| Null/filter | Filter null, rỗng và boundary date có semantics rõ |
| Authorization | Tenant/user chỉ đọc dữ liệu được phép |
| DB portability | Query chạy trên mọi DBMS được công bố hỗ trợ |
| Cache | Read adapter không trả snapshot cũ sau writer khác cập nhật |
| Migration | Schema mới vẫn tương thích query cũ |

Có thể dùng Testcontainers để chạy database engine gần production và đúng JDBC driver. H2 phù hợp cho test nhanh nhưng không thay thế kiểm thử các tính năng riêng của DBMS.

## 24. Các lỗi thường gặp trong quá trình chuyển đổi

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Cố dựng aggregate lớn cho màn hình báo cáo | Nhầm read model với write aggregate | Dùng DTO/projection và SQL join |
| Query mới trả thiếu hoặc thừa hàng | Mapping JOIN, GROUP BY hoặc DISTINCT khác query cũ | So sánh contract trên fixture đại diện |
| Read sau write trả dữ liệu cũ | Đọc replica hoặc cache chưa invalidated | Đọc primary/read-your-writes hoặc cập nhật cache |
| Repository và mapper không rollback cùng nhau | Khác DataSource hoặc transaction manager | Cấu hình cùng Spring transaction infrastructure |
| SQL chạy ở DB cũ nhưng lỗi DB mới | Query có cú pháp vendor-specific | Tách query theo dialect và test DBMS |
| Count pagination lớn hơn content | JOIN một-nhiều làm nhân bản hàng | COUNT DISTINCT root ID hoặc subquery |
| DTO bị null field | Alias/result mapping không khớp | Dùng alias/resultMap rõ ràng |
| Update qua SQL bỏ qua version | Mapper không kiểm tra optimistic lock | Giữ mapper read-only hoặc tự triển khai version contract |
| Cache trả dữ liệu cũ sau repository save | Writer và cache owner khác nhau | Thiết kế invalidation chung |
| Chuyển đổi gây regression hiệu năng | Query plan, index hoặc cardinality khác | Đo execution plan và p95/p99 |
| Query động có SQL injection | Ghép identifier/value từ request | Bind value và whitelist SQL structure |
| Hai mô hình ghi cùng một aggregate | Không có ownership rõ | Chọn một đường ghi chuẩn |

## 25. Ma trận quyết định: giữ hay viết lại query?

| Điều kiện | Khuyến nghị |
|---|---|
| SQL phức tạp, đã tối ưu và có test tốt | Giữ nguyên trong adapter trong giai đoạn chuyển đổi |
| Query join nhiều bảng chỉ phục vụ DTO | Giữ dưới dạng read projection |
| Query đơn giản, tương ứng property aggregate | Cân nhắc derived query hoặc @Query |
| SQL cũ phụ thuộc DBMS nhưng ứng dụng chỉ hỗ trợ DBMS đó | Có thể giữ, tài liệu hóa dependency |
| Ứng dụng cần nhiều DBMS | Dùng cú pháp portable hoặc query variant theo DB |
| Query khó bảo trì và không có test | Đưa vào phạm vi refactor riêng, thêm contract test trước |
| Query nặng nhưng ít thay đổi | Cân nhắc view/materialized view hoặc read model |
| Query cần type-safe DSL và nhiều dialect | Cân nhắc jOOQ |
| Nhiều dynamic mapper và resultMap | Cân nhắc MyBatis |
| SQL ngắn, số lượng ít | JdbcTemplate/NamedParameterJdbcTemplate có thể đủ |

Quyết định nên dựa trên độ phức tạp, hiệu năng, khả năng kiểm thử và kỹ năng của nhóm. Không chuyển công nghệ chỉ để đồng nhất tên thư viện.

## 26. Bài thực hành: chuyển write path, giữ read path

Giả sử ứng dụng cũ có query tìm kiếm đơn hàng kết hợp khách hàng và thanh toán.

Thực hiện:

1. Viết contract test cho query hiện tại: filter, sort, pagination, null và DTO.
2. Đóng gói query trong OrderSearch interface/adapter.
3. Giữ nguyên SQL/MyBatis/jOOQ implementation.
4. Tạo PurchaseOrder aggregate và repository Spring Data JDBC.
5. Chuyển một use case tạo đơn hàng sang repository.save.
6. Sau khi lưu, gọi read adapter để lấy projection theo ID.
7. Xác nhận read-after-write trên primary và cùng transaction khi cần.
8. Cố ý gây lỗi ở bước audit/side effect database để kiểm tra rollback nếu dùng chung transaction.
9. Chạy query với dataset gần production và so sánh p95/p99.
10. Chỉ viết lại read query nếu có lý do đo được hoặc query contract thay đổi.

Ghi lại những phần đã chuyển, phần còn dùng SQL cũ, DataSource/transaction manager của từng adapter và các DBMS được hỗ trợ. Đây là tài liệu hữu ích cho các đợt chuyển đổi tiếp theo.

## 27. Nguyên tắc ghi nhớ

- Spring Data JDBC phù hợp với write model theo aggregate; read query phức tạp có thể tiếp tục dùng SQL hoặc thư viện chuyên dụng.
- Không dựng aggregate đầy đủ chỉ để phục vụ màn hình cần một projection nhiều bảng.
- Tách DTO/read model khỏi aggregate root và không dùng projection để save domain.
- JdbcTemplate phù hợp với SQL tường minh; MyBatis phù hợp với mapper/dynamic SQL; jOOQ phù hợp với SQL DSL có kiểu.
- Giữ query cũ trong adapter giúp chuyển đổi write path từng phần và giảm phạm vi regression.
- Dùng cùng DataSource và transaction manager nếu repository và query adapter cần commit/rollback cùng nhau.
- Đọc từ replica hoặc cache có thể không thấy write mới ngay; xác định read-your-writes contract.
- Mỗi aggregate nên có một đường ghi chuẩn; custom SQL ghi aggregate phải bảo vệ version và invariant.
- SQL tùy chỉnh phải bind value, whitelist identifier và kiểm thử theo DBMS.
- Giữ contract của query: field, type, nullability, filter, sort, pagination và authorization.
- Kiểm thử read-after-write, rollback, cache, count query và migration trên database mục tiêu.
- Chỉ viết lại query khi có lợi ích rõ ràng; không chuyển công nghệ chỉ để đồng nhất stack.

Khi chuyển sang Spring Data JDBC, hãy để aggregate repository sở hữu những thay đổi domain và giữ các truy vấn đọc phức tạp ở nơi chúng được biểu diễn rõ nhất. Một read adapter có DTO và contract ổn định cho phép nhóm chuyển write path từng bước mà không phải viết lại báo cáo, tìm kiếm và SQL đã được tối ưu. Điều cần bảo vệ xuyên suốt là transaction, consistency, mapping, quyền truy cập và khả năng kiểm thử trên database thực tế.

## Tài liệu tham khảo

- [Spring Data Relational — JDBC Reference](https://docs.spring.io/spring-data/relational/reference/jdbc.html)
- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html)
- [MyBatis 3 Reference](https://mybatis.org/mybatis-3/)
- [MyBatis-Spring Reference](https://mybatis.org/spring/)
- [jOOQ Manual](https://www.jooq.org/doc/latest/manual/)

