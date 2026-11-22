# Đưa JdbcClient hoặc thư viện SQL khác vào đúng ranh giới trách nhiệm

Spring Data JDBC cung cấp repository để đọc và ghi aggregate theo ranh giới domain. Trong thực tế, vẫn có những truy vấn báo cáo, phép JOIN, thao tác hàng loạt hoặc câu SQL đặc thù mà repository chuẩn không diễn đạt thuận tiện. Khi đó có thể bổ sung JdbcClient hoặc một thư viện SQL chuyên biệt.

Điều quan trọng là đặt công cụ SQL ở đúng tầng. JdbcClient, jOOQ, MyBatis hay Jdbi nên thực hiện công việc truy cập dữ liệu trong infrastructure adapter. Chúng không nên trở thành API của domain model, và không nên tạo một đường ghi thứ hai có thể bỏ qua invariant mà aggregate root đang bảo vệ.

Bài học này trình bày cách phối hợp Spring Data JDBC với công cụ SQL chuyên biệt, cách chọn ranh giới cho query và command, cách chia sẻ transaction, cùng những điều cần kiểm soát khi SQL trực tiếp thay đổi dữ liệu.

## 1. Vì sao cần một công cụ SQL bên cạnh Spring Data JDBC?

Spring Data JDBC tập trung vào aggregate. Repository thường cung cấp các thao tác CRUD phù hợp khi ứng dụng cần tải aggregate root, thay đổi domain object và lưu trạng thái aggregate.

Tuy nhiên, một số use case có hình dạng khác:

- Màn hình cần tổng doanh thu theo ngày, nhóm theo trạng thái và JOIN nhiều bảng.
- Báo cáo cần GROUP BY, window function, CTE hoặc database-specific function.
- Tìm kiếm cần điều kiện SQL phức tạp và projection thành DTO.
- Tác vụ batch cần cập nhật hoặc xóa hàng nghìn bản ghi.
- Một câu lệnh cần RETURNING, UPSERT, lock hoặc cú pháp đặc thù database.
- Query cần tối ưu rất cụ thể theo index và execution plan.

Có thể giải quyết các nhu cầu đó bằng JdbcClient hoặc một thư viện SQL chuyên dụng mà vẫn giữ Spring Data JDBC làm công cụ persistence cho aggregate.

Ví dụ, một màn hình danh sách đơn chỉ cần mã đơn, trạng thái và tổng tiền. Tải từng SalesOrder cùng toàn bộ OrderLine chỉ để cộng tiền có thể gây ra nhiều truy vấn và materialize dữ liệu không cần thiết. Một câu SQL tổng hợp trả về DTO thường phù hợp hơn.

## 2. Xác định ranh giới trách nhiệm trước khi chọn công cụ

Hãy bắt đầu bằng câu hỏi: use case cần làm gì với dữ liệu?

| Nhu cầu | Thành phần nên chịu trách nhiệm |
|---|---|
| Thực hiện quy tắc nghiệp vụ và bảo vệ invariant | Aggregate root / domain service |
| Điều phối một use case | Application service |
| Lưu và tải aggregate theo mapping | Spring Data JDBC repository |
| Truy vấn báo cáo, projection, JOIN đặc thù | Query adapter dùng JdbcClient hoặc thư viện SQL |
| Thao tác SQL hàng loạt có kiểm soát | Command adapter trong infrastructure |
| Quản lý transaction cho nhiều thao tác cùng datasource | Application service với @Transactional |
| Tích hợp database-specific SQL | Infrastructure adapter |

Một cấu trúc phụ thuộc hợp lý:

~~~text
Web / API
    |
    v
Application service
    |
    +---- Domain model
    |        |
    |        +---- Repository port
    |
    +---- Query / command port
              |
              v
       Infrastructure adapters
              |
              +---- Spring Data JDBC repository
              |
              +---- JdbcClient adapter
              |
              +---- jOOQ / MyBatis / Jdbi adapter
                         |
                         v
                      Database
~~~

Domain model không cần biết ứng dụng dùng JdbcClient, jOOQ hay MyBatis. Domain chỉ cần biết các khái niệm nghiệp vụ và các interface mà application layer định nghĩa.

Không truyền ResultSet, JdbcClient, DSLContext, SqlSession hoặc kiểu riêng của thư viện SQL vào entity hay domain service. Những kiểu đó thuộc tầng truy cập dữ liệu.

## 3. JdbcClient là gì?

JdbcClient được Spring Framework giới thiệu từ phiên bản 6.1. Đây là API fluent cho JDBC, cung cấp cách viết truy vấn gọn hơn bằng cách kết hợp các khả năng của JdbcTemplate và NamedParameterJdbcTemplate.

Có thể tạo client từ một trong hai template:

~~~java
@Bean
JdbcClient jdbcClient(NamedParameterJdbcTemplate template) {
    return JdbcClient.create(template);
}
~~~

Hoặc tạo từ JdbcTemplate:

~~~java
@Bean
JdbcClient jdbcClient(JdbcTemplate template) {
    return JdbcClient.create(template);
}
~~~

Trong ứng dụng Spring Boot, có thể đăng ký một bean JdbcClient và inject vào các adapter cần truy vấn SQL. Hãy dùng cùng DataSource và transaction manager mà ứng dụng Spring Data JDBC đang sử dụng nếu các thao tác cần tham gia cùng transaction.

Các bước thường gặp:

1. Khai báo SQL bằng sql(...).
2. Bind tham số bằng param(...).
3. Chọn cách đọc kết quả qua query(...), hoặc thực hiện ghi qua update().
4. Chọn kết quả danh sách, một dòng hoặc tùy chọn bằng list(), single() hay optional().

Ví dụ đọc một danh sách DTO:

~~~java
List<OrderSummary> summaries = jdbcClient
        .sql("""
            SELECT id, order_code, status
            FROM sales_orders
            WHERE status = :status
            ORDER BY id DESC
            """)
        .param("status", "OPEN")
        .query((rs, rowNum) -> new OrderSummary(
                rs.getLong("id"),
                rs.getString("order_code"),
                rs.getString("status")
        ))
        .list();
~~~

Ví dụ đọc một giá trị:

~~~java
long count = jdbcClient
        .sql("""
            SELECT COUNT(*)
            FROM sales_orders
            WHERE status = :status
            """)
        .param("status", "OPEN")
        .query(Long.class)
        .single();
~~~

Ví dụ cập nhật:

~~~java
int changed = jdbcClient
        .sql("""
            UPDATE sales_orders
            SET status = :status
            WHERE id = :id
            """)
        .param("status", "CANCELLED")
        .param("id", orderId)
        .update();
~~~

update() trả về số hàng bị ảnh hưởng. Ứng dụng nên kiểm tra giá trị này khi use case yêu cầu một bản ghi duy nhất phải được thay đổi.

## 4. Dùng JdbcClient cho read model và báo cáo

Một query phục vụ màn hình thường không cần trả về aggregate. Có thể tạo DTO chuyên biệt:

~~~java
public record OrderSummary(
        Long id,
        String orderCode,
        String status,
        BigDecimal totalAmount
) {
}
~~~

Query adapter:

~~~java
@Repository
public class JdbcOrderSummaryQuery implements OrderSummaryQuery {

    private final JdbcClient jdbcClient;

    public JdbcOrderSummaryQuery(JdbcClient jdbcClient) {
        this.jdbcClient = jdbcClient;
    }

    public List<OrderSummary> findByStatus(String status) {
        return jdbcClient
                .sql("""
                    SELECT
                        o.id,
                        o.order_code,
                        o.status,
                        COALESCE(
                            SUM(l.quantity * l.unit_price),
                            0
                        ) AS total_amount
                    FROM sales_orders o
                    LEFT JOIN order_lines l
                        ON l.order_id = o.id
                    WHERE o.status = :status
                    GROUP BY o.id, o.order_code, o.status
                    ORDER BY o.id DESC
                    """)
                .param("status", status)
                .query((rs, rowNum) -> new OrderSummary(
                        rs.getLong("id"),
                        rs.getString("order_code"),
                        rs.getString("status"),
                        rs.getBigDecimal("total_amount")
                ))
                .list();
    }
}
~~~

Query này thực hiện JOIN và tính tổng trong database, rồi chỉ chuyển các cột cần thiết thành OrderSummary. Ứng dụng không phải tải mỗi đơn cùng tất cả các dòng hàng để tính tổng trong Java.

Có thể đặt một interface ở application layer để giữ dependency inversion:

~~~java
public interface OrderSummaryQuery {
    List<OrderSummary> findByStatus(String status);
}
~~~

JdbcOrderSummaryQuery triển khai interface đó trong infrastructure. Application service phụ thuộc vào OrderSummaryQuery, không phụ thuộc trực tiếp vào JdbcClient.

### 4.1. Không trả DTO đọc thành aggregate để ghi

OrderSummary không phải SalesOrder. Nó thiếu các dữ liệu và invariant cần thiết để thực hiện hành vi domain.

Ví dụ, không nên nhận OrderSummary từ màn hình, sửa status rồi cố lưu nó như aggregate. Khi cần thay đổi đơn, hãy tải SalesOrder qua repository, gọi domain method và lưu root.

Read model được tối ưu cho việc đọc; aggregate được thiết kế để bảo vệ nghiệp vụ khi ghi. Hai mô hình có thể biểu diễn cùng một dữ liệu ở những hình dạng khác nhau.

## 5. Đặt JdbcClient trong custom repository fragment

Nếu truy vấn bổ sung gắn chặt với một repository, có thể dùng custom repository fragment của Spring Data.

Interface fragment:

~~~java
public interface OrderSummaryQueries {

    List<OrderSummary> findSummaries(String status);
}
~~~

Implementation:

~~~java
class OrderSummaryQueriesImpl implements OrderSummaryQueries {

    private final JdbcClient jdbcClient;

    OrderSummaryQueriesImpl(JdbcClient jdbcClient) {
        this.jdbcClient = jdbcClient;
    }

    @Override
    public List<OrderSummary> findSummaries(String status) {
        return jdbcClient
                .sql("""
                    SELECT
                        o.id,
                        o.order_code,
                        o.status,
                        COALESCE(SUM(l.quantity * l.unit_price), 0)
                            AS total_amount
                    FROM sales_orders o
                    LEFT JOIN order_lines l
                        ON l.order_id = o.id
                    WHERE o.status = :status
                    GROUP BY o.id, o.order_code, o.status
                    ORDER BY o.id DESC
                    """)
                .param("status", status)
                .query((rs, rowNum) -> new OrderSummary(
                        rs.getLong("id"),
                        rs.getString("order_code"),
                        rs.getString("status"),
                        rs.getBigDecimal("total_amount")
                ))
                .list();
    }
}
~~~

Repository kết hợp CRUD và fragment:

~~~java
public interface SalesOrderRepository
        extends CrudRepository<SalesOrder, Long>, OrderSummaryQueries {
}
~~~

Spring Data ghép implementation fragment vào repository theo quy ước tên implementation, ở đây là OrderSummaryQueriesImpl. Có thể cấu hình postfix khác nếu dự án có quy ước riêng.

Cách này phù hợp khi custom query vẫn là một phần của khả năng truy vấn thuộc repository. Nếu query phục vụ một màn hình hoặc báo cáo độc lập, một query adapter riêng thường dễ hiểu hơn và tránh làm repository aggregate trở thành nơi chứa mọi loại SQL trong ứng dụng.

## 6. Khi nào nên dùng repository fragment, khi nào dùng query adapter riêng?

| Tiêu chí | Repository fragment | Query adapter riêng |
|---|---|---|
| Query gắn chặt với repository aggregate | Phù hợp | Cũng có thể dùng |
| Query phục vụ báo cáo hoặc dashboard | Có thể làm repository phình to | Phù hợp hơn |
| Nhiều bảng và read model riêng | Dễ trộn với CRUD | Ranh giới rõ |
| Nhiều use case dùng chung query | Có thể tái sử dụng | Dễ tái sử dụng qua port |
| Cần thay đổi công cụ SQL | Có thể thay implementation fragment | Dễ thay adapter sau interface |

Ví dụ, findByExternalReference có thể là khả năng truy vấn gắn với SalesOrderRepository. Nhưng findMonthlyRevenueByRegion là query báo cáo tổng hợp; nên đặt trong một RevenueReportQuery riêng.

Tên lớp và interface nên phản ánh mục đích nghiệp vụ, không chỉ tên thư viện. RevenueReportQuery cho biết use case cần gì; JdbcRevenueReportAdapter cho biết cách triển khai hiện tại.

## 7. Giữ transaction khi kết hợp repository và JdbcClient

Một lợi ích lớn của Spring JDBC là JdbcTemplate, NamedParameterJdbcTemplate và JdbcClient có thể tham gia transaction Spring khi chúng dùng cùng DataSource và transaction manager.

Ví dụ application service phối hợp repository và query adapter:

~~~java
@Service
public class OrderApplicationService {

    private final SalesOrderRepository orderRepository;
    private final OrderAuditWriter auditWriter;

    public OrderApplicationService(
            SalesOrderRepository orderRepository,
            OrderAuditWriter auditWriter
    ) {
        this.orderRepository = orderRepository;
        this.auditWriter = auditWriter;
    }

    @Transactional
    public void cancel(Long orderId) {
        SalesOrder order = orderRepository.findById(orderId)
                .orElseThrow(() ->
                        new IllegalArgumentException("Order not found"));

        order.cancel();

        orderRepository.save(order);
        auditWriter.recordCancellation(orderId);
    }
}
~~~

Nếu OrderAuditWriter dùng JdbcClient cùng datasource và transaction manager, câu INSERT audit có thể tham gia cùng transaction với repository.save(order).

Nếu bất kỳ thao tác nào ném exception làm rollback, thay đổi root và audit record sẽ cùng rollback theo chính sách transaction.

Cần bảo đảm:

- Repository và JdbcClient dùng cùng datasource.
- Transaction manager quản lý datasource đó.
- Các phương thức được gọi trong cùng transaction boundary.
- Không tự mở connection bằng DriverManager bên trong adapter.
- Không tạo một DataSource mới cho mỗi công cụ SQL.

Nếu hai công cụ kết nối đến hai database khác nhau, @Transactional thông thường không biến chúng thành một distributed transaction. Cần thiết kế saga, outbox hoặc transaction coordinator phù hợp với yêu cầu hệ thống.

### 7.1. Transaction read-only

Query adapter chỉ đọc có thể được gọi trong service:

~~~java
@Transactional(readOnly = true)
public List<OrderSummary> listOpenOrders() {
    return orderSummaryQuery.findByStatus("OPEN");
}
~~~

readOnly = true thể hiện ý định của use case và có thể giúp transaction manager/driver tối ưu phù hợp. Không xem nó là hàng rào bảo mật tuyệt đối ngăn mọi câu ghi; quyền database và thiết kế adapter vẫn cần được kiểm soát.

### 7.2. Tránh tự quản lý connection

Không tự gọi DataSource.getConnection() rồi tự commit/close trong một phương thức đang chạy dưới @Transactional, trừ khi bạn chủ động tích hợp đúng cơ chế transaction-aware của Spring.

Làm như vậy có thể tạo connection ngoài transaction hiện tại. Dùng JdbcClient hoặc Spring JDBC template giúp Spring quản lý connection và transaction participation.

## 8. Dùng JdbcClient để ghi trực tiếp: phải bảo vệ invariant

JdbcClient không biết aggregate root hay domain rule. Một câu UPDATE/DELETE có thể sửa bảng con mà không tải root, không gọi domain method và không tự áp dụng optimistic locking của Spring Data JDBC.

Ví dụ, nghiệp vụ chỉ cho phép xóa dòng hàng khi đơn còn ở trạng thái DRAFT. Không nên chỉ viết:

~~~java
jdbcClient.sql("""
    DELETE FROM order_lines
    WHERE order_id = :orderId
      AND line_no = :lineNo
    """)
    .param("orderId", orderId)
    .param("lineNo", lineNo)
    .update();
~~~

Câu lệnh trên chưa kiểm tra trạng thái đơn, tenant, version hoặc những bản ghi phụ thuộc.

Nếu đây là một direct command có chủ đích, có thể dùng một câu UPDATE có điều kiện để kiểm tra và tăng version root trước khi xóa child:

~~~java
@Service
public class DirectOrderLineCommands {

    private final JdbcClient jdbcClient;

    public DirectOrderLineCommands(JdbcClient jdbcClient) {
        this.jdbcClient = jdbcClient;
    }

    @Transactional
    public void deleteDraftLine(
            Long orderId,
            Integer lineNo,
            Long expectedVersion
    ) {
        int claimed = jdbcClient
                .sql("""
                    UPDATE sales_orders
                    SET version = version + 1
                    WHERE id = :orderId
                      AND version = :expectedVersion
                      AND status = 'DRAFT'
                    """)
                .param("orderId", orderId)
                .param("expectedVersion", expectedVersion)
                .update();

        if (claimed != 1) {
            throw new OptimisticLockingFailureException(
                    "Order changed or cannot be edited"
            );
        }

        int deleted = jdbcClient
                .sql("""
                    DELETE FROM order_lines
                    WHERE order_id = :orderId
                      AND line_no = :lineNo
                    """)
                .param("orderId", orderId)
                .param("lineNo", lineNo)
                .update();

        if (deleted != 1) {
            throw new IllegalArgumentException("Order line not found");
        }
    }
}
~~~

Hai câu lệnh phải tham gia cùng transaction. Nếu dòng hàng không tồn tại, exception làm rollback cả thao tác tăng version.

Cách làm này cần một quy ước thống nhất: mọi đường ghi thay đổi aggregate đều phải tôn trọng version. Nếu một SQL khác thay đổi status hoặc child mà không tăng version, optimistic locking không còn phát hiện đầy đủ các thay đổi đó.

Sau direct SQL mutation, object aggregate đã tải trước đó có thể trở nên cũ. Không tiếp tục sửa object cũ rồi lưu bằng repository. Hãy tải lại aggregate ở use case tiếp theo và invalidation cache phù hợp.

Với thao tác nghiệp vụ thông thường, ưu tiên domain method trên aggregate root. Direct SQL nên dành cho trường hợp có lý do rõ ràng như batch, hiệu năng hoặc một thao tác kỹ thuật đã được thiết kế để bảo vệ đầy đủ invariant.

## 9. Phân biệt command adapter và query adapter

Có thể tách hai loại SQL adapter theo ý định:

**Query adapter** đọc dữ liệu và trả DTO/read model. Nó thường không thay đổi trạng thái aggregate.

**Command adapter** thay đổi dữ liệu. Nó phải tuân thủ invariant, authorization, transaction, concurrency và side effect của use case.

~~~text
Application service
      |
      +---- Query port
      |        |
      |        v
      |    JdbcClient query adapter
      |        |
      |        v
      |    DTO / read model
      |
      +---- Command flow
               |
               v
          Domain invariant
               |
               +---- Repository save
               |
               +---- Direct SQL adapter (chỉ khi cần)
                        |
                        v
                   Version / FK / audit
~~~

Đừng để một class vừa xử lý báo cáo, vừa sửa bảng con, vừa gửi message, vừa chứa quy tắc domain. Phân chia theo use case giúp transaction và trách nhiệm rõ ràng hơn.

## 10. Chọn thư viện SQL khác như thế nào?

JdbcClient không phải lựa chọn duy nhất. Có thể dùng thư viện SQL khác nếu dự án cần khả năng mà Spring JDBC API không cung cấp thuận tiện.

| Công cụ | Điểm mạnh | Khi phù hợp | Ranh giới nên giữ |
|---|---|---|---|
| JdbcClient | API fluent gọn, tích hợp Spring JDBC và transaction | Query/command SQL trực tiếp, DTO | Infrastructure adapter |
| NamedParameterJdbcTemplate | Bind named parameter, mapping và batch update | Ứng dụng đang dùng Spring JDBC template | DAO/adapter |
| jOOQ | DSL có kiểu, sinh code từ schema, hỗ trợ SQL phức tạp | Query phức tạp, database-specific SQL, type safety | Adapter trả DTO hoặc triển khai port |
| MyBatis | SQL tường minh qua mapper/XML/annotation | SQL nhiều, cần kiểm soát câu lệnh và mapping | Mapper/DAO ở infrastructure |
| Jdbi | API SQL object và mapper gọn trên JDBC | Muốn giữ SQL rõ ràng với ít boilerplate | DAO/adapter |
| Querydsl SQL | DSL truy vấn có kiểu | Query động và điều kiện phức tạp | Adapter truy vấn |
| Hibernate/JPA native query | Có thể dùng trong hệ thống đã có JPA | Dự án vốn dùng JPA cho một phần persistence | Không trộn lifecycle entity với Spring Data JDBC tùy tiện |

Không chọn công cụ chỉ vì nó có nhiều tính năng. Hãy xét kỹ năng đội ngũ, độ phức tạp SQL, khả năng kiểm thử, migration schema, chi phí vận hành và cách nó tham gia transaction.

### 10.1. jOOQ cho SQL phức tạp

jOOQ phù hợp khi query sử dụng nhiều CTE, window function, lateral join hoặc cú pháp đặc thù database. DSL có kiểu và có thể sinh code từ schema, giúp phát hiện một số lỗi tên bảng/cột khi biên dịch.

Adapter nên chuyển kết quả sang DTO hoặc read model:

~~~java
public interface RevenueReportQuery {
    List<RevenueByMonth> findRevenue(int year);
}
~~~

~~~java
@Repository
public class JooqRevenueReportAdapter implements RevenueReportQuery {

    private final DSLContext dsl;

    public JooqRevenueReportAdapter(DSLContext dsl) {
        this.dsl = dsl;
    }

    @Override
    public List<RevenueByMonth> findRevenue(int year) {
        // Dùng jOOQ DSL để tạo query và map kết quả
        // sang RevenueByMonth.
        return List.of();
    }
}
~~~

Phần thân được lược bỏ vì cách viết DSL phụ thuộc code generation và schema của dự án. Điều quan trọng là DSLContext không xuất hiện trong domain model hoặc controller.

### 10.2. MyBatis cho SQL được quản lý tường minh

MyBatis phù hợp khi SQL dài, cần lưu trong XML mapper hoặc cần mapping kết quả phức tạp.

Ví dụ interface mapper:

~~~java
@Mapper
public interface OrderReportMapper {

    List<OrderSummary> findByStatus(
            @Param("status") String status
    );
}
~~~

SQL có thể nằm trong mapper XML. Application service chỉ phụ thuộc vào port hoặc query service; không cần biết câu lệnh nằm ở annotation hay XML.

MyBatis có thể tham gia Spring transaction nếu được cấu hình với cùng datasource và transaction manager.

### 10.3. Jdbi và Querydsl SQL

Jdbi cung cấp cách tổ chức SQL object, named binding và row mapper. Querydsl SQL cung cấp DSL cho query có điều kiện động.

Cả hai nên được đặt trong infrastructure. Không để kiểu query-specific như Query, Handle, SQLQuery hoặc ResultQuery rò rỉ ra application/domain API nếu không có lý do kiến trúc rõ ràng.

## 11. Không tạo hai nguồn sự thật cho cùng một aggregate

Một rủi ro khi thêm công cụ SQL là hai đường ghi cùng thao tác trên một bảng:

- SalesOrderRepository.save(order).
- JdbcClient trực tiếp UPDATE sales_orders và order_lines.

Nếu mỗi đường có quy tắc riêng, hệ thống có thể gặp các lỗi:

- Một đường tăng version, đường kia quên tăng.
- Một đường kiểm tra trạng thái, đường kia không kiểm tra.
- Một đường ghi audit, đường kia bỏ qua.
- Một đường phát event, đường kia không phát.
- Cache hoặc read model chỉ được cập nhật từ một đường.
- Hai cách mapping hiểu khác nhau về null, enum, key hoặc thứ tự collection.

Hãy xác định một quy ước cho từng loại thay đổi. Ví dụ:

| Loại thay đổi | Đường ghi được chọn |
|---|---|
| Thay đổi trạng thái đơn theo nghiệp vụ | Aggregate root và repository |
| Thêm/xóa dòng hàng thông thường | Domain method trên root, sau đó save |
| Xóa hàng loạt các dòng tạm đã hết hạn | Command adapter có transaction và kiểm soát version |
| Cập nhật counter kỹ thuật không thuộc domain invariant | SQL adapter có điều kiện rõ |
| Ghi audit/outbox | Cùng transaction với command khi yêu cầu nguyên tử |

Một bảng có thể được đọc từ nhiều adapter, nhưng các command thay đổi nó cần có quy tắc nhất quán và được tài liệu hóa.

## 12. Bind tham số và bảo vệ SQL injection

Luôn bind giá trị thay vì nối chuỗi input vào SQL:

~~~java
jdbcClient
        .sql("""
            SELECT id, order_code
            FROM sales_orders
            WHERE status = :status
              AND customer_id = :customerId
            """)
        .param("status", status)
        .param("customerId", customerId)
        .query((rs, rowNum) ->
                new OrderHeader(
                        rs.getLong("id"),
                        rs.getString("order_code")
                ))
        .list();
~~~

Không viết:

~~~java
String sql = "SELECT * FROM sales_orders WHERE status = '"
        + status + "'";
~~~

Bind parameter bảo vệ giá trị đầu vào và cho phép driver xử lý kiểu dữ liệu phù hợp.

Tên bảng, tên cột, hướng sắp xếp và từ khóa SQL thường không thể bind như một giá trị. Nếu cần lựa chọn động, dùng whitelist:

~~~java
String orderColumn = switch (sortField) {
    case "createdAt" -> "created_at";
    case "orderCode" -> "order_code";
    default -> throw new IllegalArgumentException(
            "Unsupported sort field"
    );
};
~~~

Sau đó chỉ ghép identifier đã được chọn từ whitelist vào câu SQL. Không ghép trực tiếp chuỗi do client gửi.

## 13. Mapping kết quả và xử lý kiểu dữ liệu

Khi tự map ResultSet, adapter chịu trách nhiệm chuyển đổi JDBC type sang kiểu ứng dụng.

Ví dụ:

~~~java
OrderSummary mapRow(ResultSet rs, int rowNum) throws SQLException {
    return new OrderSummary(
            rs.getLong("id"),
            rs.getString("order_code"),
            rs.getString("status"),
            rs.getBigDecimal("total_amount")
    );
}
~~~

Cần chú ý:

- getLong() trả 0 khi SQL NULL; dùng wasNull() nếu cột nullable, hoặc dùng kiểu wrapper qua mapper phù hợp.
- BigDecimal phù hợp cho tiền; tránh dùng double để lưu số tiền chính xác.
- Enum cần quy ước mapping ổn định, chẳng hạn lưu code nghiệp vụ thay vì phụ thuộc thứ tự enum.
- TIMESTAMP, DATE, timezone và Instant cần quy tắc rõ giữa database và ứng dụng.
- Alias cột phải khớp tên mà mapper mong đợi.
- Nếu JOIN tạo nhiều hàng cho một root, cần nhóm kết quả bằng mapper/extractor phù hợp để tránh duplicate root hoặc child.

Đừng để mapping JDBC nằm trong domain entity. Entity nên nhận kiểu Java đã được adapter chuyển đổi.

## 14. Pagination, batch và giới hạn tài nguyên

Query adapter thường phục vụ danh sách lớn. Hãy giới hạn kết quả và dữ liệu trả về.

Với SQL hỗ trợ LIMIT/OFFSET:

~~~java
List<OrderHeader> page = jdbcClient
        .sql("""
            SELECT id, order_code, status
            FROM sales_orders
            WHERE status = :status
            ORDER BY id DESC
            LIMIT :pageSize OFFSET :offset
            """)
        .param("status", status)
        .param("pageSize", pageSize)
        .param("offset", offset)
        .query((rs, rowNum) -> new OrderHeader(
                rs.getLong("id"),
                rs.getString("order_code"),
                rs.getString("status")
        ))
        .list();
~~~

Kiểm tra pageSize và offset theo giới hạn ứng dụng. Với bảng lớn và phân trang sâu, keyset pagination có thể ổn định và hiệu quả hơn offset pagination.

Với batch write, chia dữ liệu thành các nhóm hợp lý để tránh:

- Một transaction giữ lock quá lâu.
- SQL statement có quá nhiều bind parameters.
- Bộ nhớ tăng cao do giữ toàn bộ input.
- Rollback một lượng dữ liệu quá lớn.
- Connection pool bị chiếm trong thời gian dài.

Batch không có nghĩa bỏ qua validation. Hãy xác định rõ batch được phép xử lý từng phần hay phải nguyên tử toàn bộ.

## 15. Kiểm thử adapter và ranh giới transaction

Query adapter có SQL cụ thể, vì vậy cần kiểm tra với database có dialect gần môi trường triển khai. H2 không phải lúc nào cũng thay thế được PostgreSQL, MySQL hoặc SQL Server cho cú pháp, constraint và execution plan.

Các lớp kiểm thử hữu ích:

### 15.1. Unit test cho application service

Mock các port để kiểm tra điều phối:

- Use case gọi đúng query/command port.
- Lỗi nghiệp vụ được truyền đúng.
- Không gọi command khi validation thất bại.
- Event/outbox được yêu cầu theo đúng quy tắc.

Unit test không chứng minh SQL đúng.

### 15.2. Integration test cho adapter

Dùng database test phù hợp để xác nhận:

- SQL chạy được trên dialect mục tiêu.
- Bind parameter đúng kiểu.
- DTO được map đúng.
- JOIN/GROUP BY trả đúng dữ liệu.
- Constraint và affected row count đúng.
- Batch và pagination hoạt động theo dự kiến.

### 15.3. Kiểm thử transaction kết hợp

Một test nên xác nhận khi bước SQL thứ hai thất bại, bước repository hoặc bước audit đầu tiên cũng rollback nếu chúng cùng transaction manager.

~~~text
@Transactional use case
    |
    +-- Spring Data JDBC save root
    |
    +-- JdbcClient insert audit
    |
    +-- Lỗi tại bước cuối
             |
             v
         ROLLBACK
    |
    +-- Root không đổi
    +-- Audit không tồn tại
~~~

### 15.4. Kiểm thử concurrency cho direct command

Dùng hai transaction thực sự cạnh tranh cùng một root. Xác nhận version predicate hoặc lock ngăn transaction cũ ghi đè thay đổi mới.

Không chỉ kiểm tra một lần gọi tuần tự rồi kết luận optimistic locking hoạt động.

## 16. Tổ chức package để thư viện SQL không rò rỉ

Ví dụ cấu trúc:

~~~text
order/
  domain/
    SalesOrder.java
    OrderLine.java
    OrderRepository.java

  application/
    CancelOrderService.java
    OrderSummaryQuery.java
    OrderSummary.java

  infrastructure/
    jdbc/
      JdbcOrderSummaryAdapter.java
      JdbcOrderLineCommandAdapter.java
    springdata/
      SpringDataSalesOrderRepository.java
    jooq/
      JooqRevenueReportAdapter.java

  web/
    OrderController.java
~~~

Một dự án không nhất thiết phải có tất cả các package trên. Hãy chọn cấu trúc phù hợp quy mô hiện tại, nhưng giữ nguyên nguyên tắc: domain không phụ thuộc vào thư viện SQL cụ thể.

Nếu dùng Spring Data repository trực tiếp ở application layer, có thể đặt interface đó ở package phù hợp theo convention dự án. Khi cần kiến trúc port-adapter nghiêm ngặt hơn, định nghĩa repository port trong domain/application và để infrastructure triển khai.

## 17. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Inject JdbcClient vào domain entity | Domain phụ thuộc hạ tầng và khó kiểm thử | Đặt trong infrastructure adapter |
| Dùng SQL trực tiếp cho mọi CRUD | Trùng lặp mapping và bỏ qua aggregate persistence | Giữ Spring Data JDBC cho aggregate |
| Trả DTO báo cáo rồi dùng để ghi | DTO thiếu invariant và trạng thái đầy đủ | Tải aggregate root cho command |
| Dùng hai đường ghi không thống nhất | Version, audit và event bị lệch | Quy định command path cho từng thay đổi |
| Tạo connection thủ công bên trong transaction | SQL có thể chạy ngoài transaction Spring | Dùng JdbcClient/template cùng datasource |
| Nghĩ @Transactional bao trùm mọi database | Nhiều datasource không tự thành một transaction | Cấu hình transaction phù hợp hoặc dùng outbox/saga |
| Nối chuỗi input vào SQL | SQL injection | Bind parameter và whitelist identifier |
| Map JOIN trực tiếp thành aggregate tùy tiện | Trùng root/child hoặc sai collection | Dùng DTO và mapper/extractor có kiểm soát |
| Chỉ test bằng H2 | Bỏ sót khác biệt dialect | Integration test trên database mục tiêu |
| Chọn thư viện theo số tính năng | Tăng độ phức tạp và chi phí vận hành | Chọn theo yêu cầu SQL và năng lực đội ngũ |

## 18. Quy trình đưa một công cụ SQL vào dự án

Khi một use case cần JdbcClient hoặc thư viện khác, hãy thực hiện theo thứ tự:

**Bước 1 — Xác định mục đích.** Đây là query/read model hay command thay đổi dữ liệu?

**Bước 2 — Kiểm tra aggregate boundary.** Thao tác có cần domain invariant và hành vi của root không?

**Bước 3 — Chọn công cụ tối thiểu phù hợp.** Dùng JdbcClient cho SQL trực tiếp; chọn jOOQ/MyBatis/Jdbi khi lợi ích cụ thể đủ lớn.

**Bước 4 — Định nghĩa interface ở tầng phù hợp.** Application layer phụ thuộc query/command port, không phụ thuộc API của thư viện SQL.

**Bước 5 — Viết adapter.** Đặt SQL, mapping, bind parameter và database-specific behavior trong infrastructure.

**Bước 6 — Xác định transaction.** Dùng cùng datasource/transaction manager nếu cần phối hợp với Spring Data JDBC.

**Bước 7 — Bảo vệ command.** Kiểm tra authorization, invariant, version/lock, FK, affected row count và audit.

**Bước 8 — Kiểm thử SQL thật.** Kiểm tra dialect, mapping, rollback và concurrency.

**Bước 9 — Đo hiệu năng.** Quan sát execution plan, số hàng, round-trip, bộ nhớ và thời gian.

**Bước 10 — Tài liệu hóa đường ghi.** Chỉ rõ adapter nào được phép thay đổi bảng và cách nó giữ đồng bộ version/event/cache.

~~~text
Use case mới
    |
    v
Read hay write?
    |
    +---- Read ----------------------------+
    |                                      |
    v                                      v
DTO / projection cần gì?             Cần aggregate đầy đủ?
    |                                      |
    v                                      v
JdbcClient / SQL library              Spring Data repository
query adapter                         và domain behavior
    |                                      |
    +------------------+-------------------+
                       |
                       v
             Cùng transaction nếu cần
                       |
                       v
             Kiểm thử SQL và mapping
                       |
                       v
             Đo hiệu năng thực tế
~~~

## 19. Bài tập tự suy luận

**Tình huống A — Dashboard doanh thu**

Dashboard cần tổng tiền theo tháng và trạng thái đơn. Có nên tải tất cả SalesOrder cùng OrderLine rồi cộng trong Java không?

**Gợi ý:** Thường không. Một query tổng hợp bằng JdbcClient trả DTO có thể giảm dữ liệu truyền và số object cần dựng.

**Tình huống B — Xóa một dòng hàng**

Một dòng hàng chỉ được xóa khi đơn còn ở trạng thái DRAFT. Có thể dùng JdbcClient để DELETE trực tiếp không?

**Gợi ý:** Có thể nếu đây là command được thiết kế rõ, nhưng phải kiểm tra status, root ID, version/lock, FK, transaction và affected row count. Với thao tác nghiệp vụ thông thường, domain method trên root thường phù hợp hơn.

**Tình huống C — Query dùng jOOQ**

Application service cần báo cáo nhưng không muốn phụ thuộc DSLContext. Nên đặt DSLContext ở đâu?

**Gợi ý:** Trong adapter infrastructure. Application service gọi interface query port và nhận DTO.

**Tình huống D — Hai datasource**

Repository dùng database A, JdbcClient dùng database B. Một @Transactional thông thường có bảo đảm cả hai database commit cùng nhau không?

**Gợi ý:** Không. Cần transaction coordinator/distributed transaction hoặc thiết kế outbox/saga phù hợp.

**Tình huống E — Dynamic sort**

Client gửi sortField = "created_at desc; drop table...". Có thể bind chuỗi này như một parameter cho ORDER BY không?

**Gợi ý:** Không thể bind identifier/order expression như giá trị. Dùng whitelist các tên cột và hướng sort được phép.

**Tình huống F — DTO bị dùng để cập nhật**

Một OrderSummary có id, status và totalAmount. Có thể dùng nó thay SalesOrder để gọi repository save không?

**Gợi ý:** Không. DTO đọc không đại diện đầy đủ aggregate và không bảo vệ invariant. Tải root để thực hiện command.

## 20. Ghi nhớ

| Thành phần | Trách nhiệm |
|---|---|
| Aggregate root | Bảo vệ invariant và vòng đời entity con |
| Spring Data JDBC repository | Lưu/tải aggregate theo mapping |
| JdbcClient | Thực thi SQL JDBC qua API fluent |
| Query adapter | Trả DTO/read model cho màn hình và báo cáo |
| Command adapter | Thực hiện SQL ghi có kiểm soát |
| Repository fragment | Bổ sung khả năng SQL cho repository hiện có |
| jOOQ / MyBatis / Jdbi | Công cụ SQL chuyên biệt đặt ở infrastructure |
| @Transactional | Phối hợp thao tác cùng transaction manager |
| Version predicate / lock | Bảo vệ direct SQL trước cập nhật đồng thời |
| Bind parameter | Bảo vệ giá trị đầu vào và kiểu dữ liệu |
| Integration test | Xác nhận SQL, dialect, transaction và mapping |

**Hãy chọn công cụ theo công việc và giữ nó trong tầng truy cập dữ liệu.** Spring Data JDBC tiếp tục quản lý aggregate và domain invariant; JdbcClient hoặc thư viện SQL khác xử lý những truy vấn, báo cáo hay command đặc thù qua adapter. Khi nhiều công cụ cùng tham gia một use case, dùng chung transaction manager nếu cần tính nguyên tử, và bảo đảm mọi đường ghi đều tôn trọng version, khóa ngoại, audit và sự kiện của aggregate.

## Tài liệu tham khảo

- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): JdbcClient, JdbcTemplate, named parameters, row mapping và truy cập JDBC.
- [Spring Data Relational — Custom Repository Implementations](https://docs.spring.io/spring-data/relational/reference/repositories/custom-implementations.html): repository fragments và custom implementation.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): @Transactional, transaction boundary, propagation và rollback.
- [jOOQ Manual](https://www.jooq.org/doc/latest/manual/): SQL DSL, code generation và mapping.
- [MyBatis Documentation](https://mybatis.org/mybatis-3/): mapper, SQL mapping và integration.
- [Jdbi Documentation](https://jdbi.org/): SQL object, parameter binding và row mapping.

