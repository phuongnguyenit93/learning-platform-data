# Chọn projection, SQL JOIN hoặc Single Query Loading theo số đo

Trong **Spring Data Relational JDBC**, không có một chiến lược đọc dữ liệu tối ưu cho mọi use case. Một màn hình danh sách có thể chỉ cần vài cột, trong khi một use case nghiệp vụ cần toàn bộ aggregate root và các entity được sở hữu. Một báo cáo có thể cần tổng hợp dữ liệu từ nhiều bảng. Dùng cùng một cách tải cho cả ba trường hợp thường làm tăng số SQL, số hàng truyền qua mạng hoặc lượng object được tạo trong JVM.

Ba hướng tiếp cận chính:

- **Projection/read model:** chỉ truy vấn các cột cần dùng và ánh xạ thành DTO; phù hợp cho danh sách, báo cáo và API read-only.
- **SQL JOIN:** kết hợp dữ liệu từ nhiều bảng trong một câu query; hiệu quả với quan hệ to-one hoặc một collection có cardinality được kiểm soát, nhưng có thể tạo hàng lặp hoặc tích Descartes khi JOIN nhiều collection.
- **Single Query Loading:** tính năng của Spring Data JDBC từ phiên bản 3.2, cho phép tải aggregate qua một SQL query trong những điều kiện được hỗ trợ. Tài liệu hiện hành vẫn mô tả tính năng này là experimental và có giới hạn về mapping, dialect và repository method.

Không nên chọn chỉ vì một phương án tạo ít câu SQL hơn. Hãy đo thời gian phản hồi, số hàng truyền về, kích thước kết quả, CPU database, bộ nhớ JVM và khả năng mở rộng dưới tải thực tế.

## 1. Bắt đầu từ dữ liệu use case thực sự cần

Giả sử ứng dụng có aggregate:

~~~java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private Long customerId;

    private String status;

    private LocalDateTime createdAt;

    @MappedCollection(idColumn = "order_id", keyColumn = "line_no")
    private List<OrderLine> lines = new ArrayList<>();

    // constructor, getters, domain methods...
}
~~~

Mỗi OrderLine có product, quantity và unitPrice. Một trang quản trị có thể cần mã đơn, tên khách hàng, trạng thái, ngày tạo, số dòng hàng và tổng tiền. Màn hình này không cần toàn bộ từng OrderLine, không cần domain behavior của PurchaseOrder và cũng không cần mọi cột trong aggregate.

Ngược lại, use case xác nhận đơn hàng có thể cần toàn bộ dòng hàng để kiểm tra invariant, tính lại tổng, cập nhật trạng thái và lưu aggregate. DTO chỉ chứa vài trường sẽ không đủ để thực hiện nghiệp vụ đó.

| Nhu cầu | Dữ liệu cần | Cách đọc thường phù hợp |
|---|---|---|
| Chỉnh sửa aggregate hoặc chạy domain behavior | Aggregate root và các thành phần cần thiết cho invariant | Repository load aggregate |
| Trang danh sách/API summary | Một tập con cột, có thể kèm count/sum | Projection DTO |
| Báo cáo nhiều bảng | Các cột tổng hợp/nhóm theo điều kiện | SQL JOIN + aggregation + DTO |
| Đọc toàn bộ aggregate có collection | Root và owned entities | Default loading hoặc Single Query Loading nếu đủ điều kiện |
| Tìm kiếm tùy biến phức tạp | Read model theo query riêng | Repository fragment/NamedParameterJdbcTemplate |

Không dùng projection chỉ vì DTO nhỏ hơn entity nếu sau đó code vẫn phải tải lại aggregate đầy đủ cho từng kết quả. Hãy tính toàn bộ chi phí của use case.

## 2. Projection trong Spring Data JDBC

Projection là kiểu kết quả chỉ biểu diễn phần dữ liệu mà caller cần. Với Spring Data JDBC, cách kiểm soát rõ ràng cho một read model chuyên biệt là khai báo SQL tường minh và ánh xạ ResultSet thành DTO bằng RowMapper hoặc ResultSetExtractor.

Spring Data JDBC có hỗ trợ custom query và custom mapping. Tuy nhiên, không nên áp dụng mọi giả định projection của Spring Data JPA cho JDBC. Với query string trong Spring Data JDBC, hãy kiểm tra chính xác các cột mà row mapper cần; query custom trả về aggregate root còn có thể tải collection bằng những câu query riêng.

### DTO cho màn hình danh sách

~~~java
public record OrderSummary(
        Long orderId,
        String customerName,
        String status,
        LocalDateTime createdAt,
        Long lineCount,
        BigDecimal totalAmount
) {}
~~~

DTO không có identity persistence, không có collection và không cần repository CRUD riêng. Nó là read model được tạo cho truy vấn cụ thể.

### Dùng custom repository fragment

Khi SQL có JOIN, GROUP BY, pagination hoặc filter động, một repository fragment giúp giữ query và mapping ở một nơi:

~~~java
public interface OrderReadOperations {

    List<OrderSummary> findSummaries(
            String status,
            int limit,
            long offset
    );
}
~~~

Implementation:

~~~java
public class OrderReadOperationsImpl implements OrderReadOperations {

    private final NamedParameterJdbcTemplate jdbc;

    public OrderReadOperationsImpl(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public List<OrderSummary> findSummaries(
            String status,
            int limit,
            long offset) {

        String sql = """
                SELECT
                    po.id AS order_id,
                    c.name AS customer_name,
                    po.status,
                    po.created_at,
                    COUNT(ol.id) AS line_count,
                    COALESCE(
                        SUM(ol.quantity * ol.unit_price),
                        0
                    ) AS total_amount
                FROM purchase_order po
                JOIN customer c ON c.id = po.customer_id
                LEFT JOIN order_line ol ON ol.order_id = po.id
                WHERE po.status = :status
                GROUP BY
                    po.id,
                    c.name,
                    po.status,
                    po.created_at
                ORDER BY po.created_at DESC, po.id DESC
                LIMIT :limit OFFSET :offset
                """;

        MapSqlParameterSource parameters = new MapSqlParameterSource()
                .addValue("status", status)
                .addValue("limit", limit)
                .addValue("offset", offset);

        return jdbc.query(sql, parameters, (rs, rowNum) ->
                new OrderSummary(
                        rs.getLong("order_id"),
                        rs.getString("customer_name"),
                        rs.getString("status"),
                        rs.getTimestamp("created_at").toLocalDateTime(),
                        rs.getLong("line_count"),
                        rs.getBigDecimal("total_amount")
                )
        );
    }
}
~~~

Repository chính kết hợp fragment:

~~~java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long>,
                OrderReadOperations {
}
~~~

Tên implementation theo convention là OrderReadOperationsImpl. Spring Data ghép fragment vào repository proxy khi interface và implementation được phát hiện trong vùng scan phù hợp.

Ví dụ SQL dùng LIMIT/OFFSET của PostgreSQL và MySQL. Nếu database khác, thay cú pháp paging tương ứng. Thứ tự sắp xếp có thêm ID làm tie-breaker để các trang ổn định khi nhiều đơn có cùng created_at.

**Lợi ích của projection:**

- Chỉ truyền các cột mà DTO cần.
- Không tạo object cho mọi child entity khi màn hình chỉ cần count/sum.
- Có thể JOIN và aggregate dữ liệu từ các bảng khác aggregate.
- Read model có thể thay đổi theo nhu cầu màn hình mà không làm phình domain aggregate.

**Chi phí cần theo dõi:**

- SQL và DTO mapping phải được bảo trì cùng schema.
- Query nhiều JOIN/GROUP BY có thể tốn CPU hoặc cần index phù hợp.
- DTO không có domain behavior; không dùng nó làm đối tượng để lưu aggregate.
- Nếu cần nhiều read model khác nhau, giữ mỗi query có tên và mục đích rõ ràng thay vì tạo một DTO khổng lồ cho mọi màn hình.

## 3. Dùng @Query với RowMapper cho projection

Nếu muốn giữ query trong repository interface, Spring Data JDBC hỗ trợ @Query với rowMapperRef, rowMapperClass, resultSetExtractorRef hoặc resultSetExtractorClass.

Ví dụ:

~~~java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    @Query(
        value = """
            SELECT
                po.id AS order_id,
                c.name AS customer_name,
                po.status,
                po.created_at,
                COUNT(ol.id) AS line_count,
                COALESCE(SUM(ol.quantity * ol.unit_price), 0) AS total_amount
            FROM purchase_order po
            JOIN customer c ON c.id = po.customer_id
            LEFT JOIN order_line ol ON ol.order_id = po.id
            WHERE po.status = :status
            GROUP BY po.id, c.name, po.status, po.created_at
            ORDER BY po.created_at DESC, po.id DESC
            """,
        rowMapperRef = "orderSummaryRowMapper"
    )
    List<OrderSummary> findSummaries(@Param("status") String status);
}
~~~

Đăng ký mapper bean:

~~~java
@Configuration
public class QueryMappingConfiguration {

    @Bean
    RowMapper<OrderSummary> orderSummaryRowMapper() {
        return (rs, rowNum) -> new OrderSummary(
                rs.getLong("order_id"),
                rs.getString("customer_name"),
                rs.getString("status"),
                rs.getTimestamp("created_at").toLocalDateTime(),
                rs.getLong("line_count"),
                rs.getBigDecimal("total_amount")
        );
    }
}
~~~

Với truy vấn này, @Query trả về DTO; nó không yêu cầu Spring Data JDBC tải và dựng toàn bộ PurchaseOrder aggregate.

Lưu ý:

- String-based query của Spring Data JDBC không tự viết lại SQL để áp dụng Pageable, Sort hoặc Limit như một số query derivation khác. Nếu cần paging, hãy đưa LIMIT/OFFSET và tham số tương ứng vào SQL, hoặc dùng fragment với JDBC template.
- Named parameters của Spring Data JDBC dùng dạng :status.
- Tên cột/alias trong ResultSet phải khớp với mapper.
- Khi dùng custom RowMapper/ResultSetExtractor, entity callbacks và lifecycle events không tự chạy cho kết quả mapping đó; mapper tự chịu trách nhiệm tạo DTO.
- Nếu @Query trả về aggregate root với default RowMapper, các collection entity vẫn được tải bằng query riêng theo mapping. Chỉ viết JOIN vào SQL không có nghĩa collection tự được gom vào aggregate trong một statement.

Với SQL động hoặc logic paging phức tạp, fragment + NamedParameterJdbcTemplate thường dễ kiểm soát hơn một annotation dài.

## 4. SQL JOIN: khi nào hiệu quả?

JOIN cho phép lấy dữ liệu từ nhiều bảng trong một statement. Cardinality của quan hệ quyết định kết quả có gọn hay phình to.

### JOIN quan hệ to-one

Ví dụ đơn hàng có một Customer:

~~~sql
SELECT
    po.id,
    po.status,
    c.name AS customer_name
FROM purchase_order po
JOIN customer c ON c.id = po.customer_id
WHERE po.id = :id;
~~~

Mỗi đơn hàng khớp tối đa một customer, vì vậy JOIN thường không nhân số hàng của root. Đây là trường hợp dễ hưởng lợi từ JOIN nếu caller cần cả hai thông tin.

### JOIN một collection to-many

Nếu đơn hàng có nhiều dòng hàng:

~~~sql
SELECT
    po.id,
    po.status,
    ol.id AS line_id,
    ol.product_id,
    ol.quantity
FROM purchase_order po
LEFT JOIN order_line ol ON ol.order_id = po.id
WHERE po.id = :id;
~~~

Một đơn hàng có 5 dòng sẽ tạo 5 result rows, lặp các cột của purchase_order. Để dựng lại một aggregate hoặc DTO chứa danh sách child, ứng dụng phải gom các hàng theo root ID.

Không nên dùng RowMapper đơn giản tạo một PurchaseOrder cho mỗi row; cách đó có thể tạo nhiều root trùng. Dùng ResultSetExtractor hoặc custom mapper có cấu trúc map theo ID nếu mục tiêu thực sự là materialize một object graph.

### JOIN nhiều collection có thể tạo tích Descartes

Giả sử mỗi order có 5 OrderLine, 3 Payment và 4 Shipment. JOIN cả ba collection có thể tạo đến 5 × 3 × 4 = 60 rows cho một order. Các thông tin line, payment và shipment bị lặp chéo trong kết quả.

~~~mermaid
flowchart TD
    A["PurchaseOrder"] --> B["5 OrderLine"]
    A --> C["3 Payment"]
    A --> D["4 Shipment"]
    B --> E["JOIN tất cả collection"]
    C --> E
    D --> E
    E --> F["Tối đa 60 result rows cho một order"]
~~~

Tác động:

- Nhiều dữ liệu trùng được truyền qua network.
- Database phải join và materialize nhiều hàng.
- JVM phải đọc và loại trùng dữ liệu.
- Aggregation dễ bị sai nếu COUNT/SUM tính trên kết quả đã nhân chéo.
- Paging theo root có thể sai nếu LIMIT áp dụng trên joined rows thay vì root rows.

Vì vậy, không JOIN nhiều collection chỉ để giảm query count. Hãy so sánh tổng số rows/bytes và CPU với phương án nhiều query hoặc Single Query Loading.

## 5. JOIN và aggregation cho read model

Với màn hình tổng quan, thường không cần tạo collection trong Java. Hãy để database tính count/sum/grouping và trả một DTO.

~~~sql
SELECT
    po.id,
    po.status,
    COUNT(ol.id) AS line_count,
    COALESCE(SUM(ol.quantity * ol.unit_price), 0) AS total_amount
FROM purchase_order po
LEFT JOIN order_line ol ON ol.order_id = po.id
WHERE po.status = :status
GROUP BY po.id, po.status
ORDER BY po.id DESC;
~~~

Một số lưu ý:

- Dùng LEFT JOIN nếu vẫn cần hiển thị đơn chưa có dòng hàng.
- COUNT(ol.id) trả 0 cho root không có child; COUNT(*) có thể trả 1 do hàng root vẫn tồn tại.
- SUM có thể trả NULL khi không có child; dùng COALESCE nếu DTO cần 0.
- Nếu JOIN thêm một collection khác, COUNT/SUM có thể bị nhân đôi do tích Descartes.
- Nếu cần aggregate nhiều collection độc lập, có thể tổng hợp từng bảng trong subquery/CTE rồi JOIN kết quả đã gom về một hàng mỗi root.

Ví dụ tránh nhân chéo bằng subquery:

~~~sql
SELECT
    po.id,
    po.status,
    line_stats.line_count,
    line_stats.total_amount,
    payment_stats.payment_count
FROM purchase_order po
LEFT JOIN (
    SELECT
        order_id,
        COUNT(*) AS line_count,
        SUM(quantity * unit_price) AS total_amount
    FROM order_line
    GROUP BY order_id
) line_stats ON line_stats.order_id = po.id
LEFT JOIN (
    SELECT
        order_id,
        COUNT(*) AS payment_count
    FROM payment
    GROUP BY order_id
) payment_stats ON payment_stats.order_id = po.id
WHERE po.status = :status;
~~~

Mỗi subquery trả tối đa một row cho một order_id; kết quả không bị nhân chéo giữa từng line và từng payment. Database optimizer có thể chọn execution plan khác nhau tùy index, cardinality và statistics; cần đo trên dữ liệu thật.

## 6. Single Query Loading là gì?

Spring Data JDBC bổ sung **Single Query Loading** từ phiên bản 3.2. Khi được bật và aggregate đáp ứng các điều kiện hỗ trợ, Spring Data JDBC có thể tải nhiều aggregate cùng các collection của chúng bằng một SQL SELECT.

Cách truyền thống thường tải root trước, sau đó chạy các statement riêng để lấy entity được sở hữu. Với nhiều aggregate, việc tải collection có thể tạo nhiều round-trip và dạng N+1 query.

Single Query Loading sử dụng các tính năng SQL như analytic/window functions để tổ chức kết quả sao cho các collection có thể được ghép lại mà không cần JOIN thô tất cả collection thành tích Descartes. Spring Data JDBC sau đó materialize aggregate từ result set.

Single Query Loading là chiến lược tải **aggregate**, không phải projection DTO tùy ý. Nó dành cho các find methods được hỗ trợ của CrudRepository và phải đáp ứng giới hạn mapping/dialect.

### Bật Single Query Loading

Cần bật trên JdbcMappingContext:

~~~java
@Configuration
@EnableJdbcRepositories
public class JdbcConfiguration extends AbstractJdbcConfiguration {

    @Override
    @Bean
    public JdbcMappingContext jdbcMappingContext(
            Optional<NamingStrategy> namingStrategy,
            JdbcCustomConversions customConversions,
            RelationalManagedTypes jdbcManagedTypes) {

        JdbcMappingContext context =
                super.jdbcMappingContext(
                        namingStrategy,
                        customConversions,
                        jdbcManagedTypes
                );

        context.setSingleQueryLoadingEnabled(true);
        return context;
    }
}
~~~

Ví dụ dùng Java configuration kế thừa AbstractJdbcConfiguration để minh họa nơi cấu hình mapping context. Trong ứng dụng Spring Boot, hãy tích hợp thiết lập này vào cấu hình Spring Data JDBC hiện có; tránh đăng ký thêm một JdbcMappingContext thứ hai hoặc ghi đè các bean infrastructure đang được auto-configuration sử dụng.

Thuộc tính này có từ Spring Data Relational 3.2. Nếu dialect hỗ trợ và aggregate đủ điều kiện, Spring Data JDBC sẽ cố dùng Single Query Loading. Nếu một điều kiện không được đáp ứng, framework quay về cách tải mặc định.

### Các giới hạn trong tài liệu hiện hành

Theo tài liệu Spring Data Relational 4.1:

1. Aggregate không được có **nested collections**. Giới hạn này bao gồm Map.
2. Aggregate không được dùng **AggregateReference** hoặc embedded entities.
3. Dialect phải hỗ trợ các tính năng SQL cần thiết, gồm analytic/window functions. Trong các dialect tích hợp, H2 và HSQL không hỗ trợ vì thiếu windowing functions; các dialect tích hợp còn lại hỗ trợ.
4. Chỉ các find methods của **CrudRepository** được hỗ trợ. Derived query methods và annotated query methods không dùng Single Query Loading.
5. Phải bật flag trên JdbcMappingContext.

Nếu điều kiện không phù hợp, framework fallback về loading truyền thống. Tài liệu hiện hành vẫn mô tả Single Query Loading là experimental; hãy kiểm tra phiên bản Spring Data JDBC thực tế trước khi dựa vào nó trong production.

Không nhầm tên viết tắt Single Query Loading với Structured Query Language. Tài liệu Spring Data khuyến nghị viết đầy đủ tên tính năng để tránh nhập nhằng.

## 7. Khi nào chọn Single Query Loading?

Phù hợp khi:

- Caller cần toàn bộ aggregate, không chỉ một DTO.
- Aggregate có collection trực tiếp nhưng không có nested collection.
- Không dùng AggregateReference hoặc embedded entities trong aggregate cần tải.
- Query đi qua các find methods CrudRepository được hỗ trợ.
- Database dialect có window functions và feature hoạt động với phiên bản đang dùng.
- Đo đạc cho thấy nhiều statement/round-trip là nút thắt.

Không phù hợp hoặc không có tác dụng khi:

- Màn hình chỉ cần vài cột của root và count/sum.
- Query là derived query hoặc annotated query.
- Aggregate có nested collection/Map, AggregateReference hoặc embedded entities.
- Database dùng H2/HSQL dialect tích hợp.
- Use case cần một report JOIN nhiều bảng ngoài aggregate.
- Chi phí thực tế nằm ở query scan lớn, thiếu index, network payload hoặc object mapping thay vì số round-trip.

Single Query Loading không tự biến một query báo cáo thành DTO projection, không thay thế index và không đảm bảo nhanh hơn trong mọi workload. Nó thay đổi cách tải aggregate; hãy đo tổng chi phí.

## 8. So sánh ba lựa chọn

| Tiêu chí | Projection DTO | SQL JOIN | Single Query Loading |
|---|---|---|---|
| Mục tiêu | Chỉ lấy dữ liệu caller cần | Kết hợp dữ liệu nhiều bảng | Tải aggregate đầy đủ |
| Kết quả | DTO/read model | DTO hoặc object graph tự gom | Aggregate root và owned entities |
| Số query | Thường một query cho read model | Có thể một query | Một query cho aggregate load đủ điều kiện |
| Dữ liệu truyền | Có thể ít nếu SELECT đúng cột | Có thể nhiều do lặp root/child | Giảm round-trip; result shape do framework quản lý |
| Mapping | RowMapper/ResultSetExtractor | Custom grouping nếu có to-many | Spring Data JDBC materialization |
| Nhiều collection | Có thể aggregate/subquery riêng | Có nguy cơ tích Descartes | Không hỗ trợ nested collections theo giới hạn hiện hành |
| Query tùy biến | Rất phù hợp | Rất phù hợp | Không dùng cho derived/annotated queries |
| Domain behavior | DTO không phải aggregate | Tùy mapping, cần tránh giả mạo aggregate | Trả aggregate phù hợp cho domain behavior |
| Dialect | Phụ thuộc SQL tự viết | Phụ thuộc SQL tự viết | Cần dialect hỗ trợ window functions |
| Mức kiểm soát SQL | Cao | Cao | Framework tạo SQL |

## 9. Chọn theo loại use case

### Trang danh sách hoặc API summary

Chọn projection DTO khi response chỉ cần vài cột, tên khách hàng và tổng hợp từ child. Một query với JOIN/grouping hoặc subquery thường hợp lý. Tránh tải toàn bộ aggregate cho hàng trăm kết quả nếu không cần domain behavior.

### Màn hình chi tiết cần một aggregate đầy đủ

Dùng repository findById/findAll phù hợp. Nếu aggregate có collection và đáp ứng giới hạn, thử Single Query Loading. Nếu không đáp ứng, dùng default loading hoặc một read query tùy chỉnh cho view riêng.

### Nghiệp vụ thay đổi aggregate

Load aggregate bằng repository để giữ domain model, invariant và optimistic locking. Projection DTO không đủ để thay thế object dùng cho command. Single Query Loading có thể giảm round-trip khi load aggregate nếu đủ điều kiện.

### Báo cáo nhiều aggregate

Dùng SQL JOIN, CTE, subquery và aggregate function trả DTO. Không cần materialize aggregate root cho báo cáo. Cân nhắc read replica/materialized view nếu workload đọc nặng và freshness cho phép.

### Search có filter/sort động

Dùng repository fragment với NamedParameterJdbcTemplate hoặc query builder phù hợp. Whitelist tên cột sort; bind giá trị filter qua named parameters. Không nối input người dùng vào SQL identifier.

## 10. Đo trước khi chọn chiến lược

Một benchmark có ý nghĩa phải so sánh cùng một kết quả nghiệp vụ và cùng điều kiện dữ liệu.

| Chỉ số | Vì sao cần |
|---|---|
| Số SQL statements | Nhận diện N+1 hoặc quá nhiều round-trip |
| Tổng thời gian query | Biết database dành bao lâu để xử lý |
| End-to-end latency p50/p95/p99 | Thể hiện trải nghiệm thực tế, đặc biệt dưới tải |
| Số result rows | Phát hiện JOIN làm nhân bản dữ liệu |
| Bytes trả về | Ước lượng chi phí network và decode |
| Database CPU/buffer reads | Phát hiện scan, join hoặc sort tốn kém |
| JVM CPU/heap allocation/GC | Phát hiện materialization quá nhiều object |
| Connection pool usage | Phát hiện transaction/query giữ connection lâu |
| Throughput dưới concurrency | Xác nhận phương án có mở rộng được không |

### Quy trình benchmark

1. Chuẩn bị dữ liệu đại diện: số root, số child trung bình và phân bố cực đại.
2. Chạy default aggregate loading, projection DTO, JOIN và Single Query Loading khi đủ điều kiện.
3. Dùng cùng filter, sort, page size và semantics.
4. Warm up JVM/connection pool và database cache theo kịch bản được định nghĩa.
5. Chạy nhiều lần, ghi latency percentile và throughput thay vì chỉ lấy một lần đo.
6. Quan sát SQL thực tế, query plan và số hàng trả về.
7. Thử tải đồng thời gần với production.
8. So sánh CPU, memory, bytes và database resource cùng latency.
9. Lặp lại sau khi thêm index hoặc thay đổi query để biết cải thiện đến từ đâu.

Không chỉ đo số lần gọi database. Một câu JOIN duy nhất có thể trả về hàng trăm nghìn rows do tích Descartes và chậm hơn nhiều câu query nhỏ có index tốt.

### Công cụ đo

- SQL logging hoặc datasource instrumentation để đếm statements.
- Micrometer/Actuator và tracing để đo latency theo repository/use case.
- Database EXPLAIN/EXPLAIN ANALYZE để xem execution plan.
- PostgreSQL EXPLAIN (ANALYZE, BUFFERS) để kiểm tra thời gian, rows và buffer reads.
- Testcontainers để chạy integration test trên cùng engine với production.
- JFR hoặc profiler để quan sát allocation và GC phía JVM.

Bật SQL logging chi tiết trong môi trường benchmark/test; tránh log payload nhạy cảm hoặc bật debug quá mức trong production lâu dài.

## 11. Ví dụ đo query count cho N+1

Giả sử trang lấy 100 order và mỗi order có lines. Với cách tải truyền thống, có thể thấy:

~~~text
1 query: SELECT purchase_order ...
N queries: SELECT order_line WHERE order_id = ?
~~~

Nếu 100 order đều có collection, tổng số statement có thể tăng theo số aggregate. Nếu aggregate có nhiều collection, số query có thể tăng thêm theo từng quan hệ được tải.

Sau khi bật Single Query Loading và aggregate đủ điều kiện, find method được hỗ trợ có thể tải các aggregate bằng một SQL query. Nhưng nếu query thực tế là derived query hoặc @Query, Single Query Loading không áp dụng; cần đo lại đúng method đang được gọi.

Projection summary có thể dùng một query GROUP BY để trả 100 DTO mà không tải toàn bộ OrderLine. Đây có thể là phương án tốt nhất nếu caller chỉ cần số dòng và tổng tiền.

Bảng minh họa, không phải số đo đảm bảo:

| Chiến lược | Số statement kỳ vọng | Result rows | Object materialization |
|---|---:|---|---|
| Default aggregate loading | Root query + các query collection | Root và child theo nhiều result sets | Aggregate đầy đủ |
| Projection + aggregate SQL | Thường 1 query | Một row/DTO mỗi root | DTO nhỏ |
| JOIN root + one collection | Thường 1 query | Có thể nhiều row mỗi root | Cần gom nếu dựng collection |
| JOIN nhiều collection | Có thể 1 query | Có thể nhân chéo mạnh | Mapping/khử trùng lặp tốn kém |
| Single Query Loading | 1 query khi đủ điều kiện | Result set do framework tạo để dựng aggregate | Aggregate đầy đủ |

Đừng biến bảng minh họa thành cam kết hiệu năng. Query count, rows và thời gian thực tế phụ thuộc method, mapping, database, dialect và dữ liệu.

## 12. Pagination và JOIN collection

Một lỗi phổ biến là áp dụng LIMIT/OFFSET trực tiếp trên kết quả JOIN one-to-many:

~~~sql
SELECT po.id, ol.id AS line_id
FROM purchase_order po
LEFT JOIN order_line ol ON ol.order_id = po.id
ORDER BY po.created_at DESC
LIMIT 20 OFFSET 0;
~~~

LIMIT 20 ở đây giới hạn joined rows, không phải 20 purchase orders. Nếu một order có 10 lines, một trang có thể chỉ chứa vài root.

Nếu cần page theo root:

1. Chọn page ID/root trước.
2. Sau đó JOIN/fetch dữ liệu cho tập ID đó.
3. Hoặc dùng query tổng hợp trả đúng một row mỗi root.
4. Đảm bảo count query đếm root, không đếm child rows.

Ví dụ dùng CTE:

~~~sql
WITH page_orders AS (
    SELECT id, customer_id, status, created_at
    FROM purchase_order
    WHERE status = :status
    ORDER BY created_at DESC, id DESC
    LIMIT :limit OFFSET :offset
)
SELECT
    po.id,
    po.status,
    po.created_at,
    c.name AS customer_name
FROM page_orders po
JOIN customer c ON c.id = po.customer_id
ORDER BY po.created_at DESC, po.id DESC;
~~~

Nếu cần collection details, query riêng cho các IDs trong page hoặc dùng ResultSetExtractor để gom. Với trang lớn, cân nhắc keyset pagination theo (created_at, id) thay vì offset sâu.

## 13. Kiểm thử kết quả và số query

Kiểm thử chức năng cần xác nhận dữ liệu trả về đúng; kiểm thử hiệu năng cần đo SQL và resource.

Các trường hợp cần có:

- Aggregate có 0, 1 và nhiều child.
- Aggregate có collection trực tiếp và nested collection.
- Projection trả đúng count/sum khi root không có child.
- JOIN một-to-many không tạo root trùng.
- JOIN nhiều collection không nhân đôi tổng tiền.
- Pagination trả đúng số root, kể cả root có nhiều child.
- Single Query Loading được bật và chỉ chạy trên database/dialect đủ điều kiện.
- Khi điều kiện Single Query Loading không thỏa, framework fallback và kết quả vẫn đúng.
- SQL custom chạy trên database/driver production-compatible.
- Query plan sử dụng index phù hợp với filter/sort.

### Integration test với Testcontainers

Dùng database cùng engine với production để kiểm tra dialect, window functions, SQL JOIN, paging và mapping. H2 có thể hữu ích cho test nhanh nhưng không đại diện cho dialect Single Query Loading vì dialect H2/HSQL tích hợp không hỗ trợ tính năng windowing cần thiết.

Trong test Single Query Loading, bật SQL instrumentation hoặc datasource proxy để xác nhận số statement thực tế. Đừng chỉ assert flag isSingleQueryLoadingEnabled() là true; flag chỉ cho biết cấu hình, không chứng minh một method cụ thể đã dùng chiến lược đó.

## 14. Những lỗi thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
|---|---|---|
| Vẫn có nhiều query sau khi bật Single Query Loading | Method là derived/@Query, dialect không hỗ trợ hoặc aggregate không đủ điều kiện | Kiểm tra find method, mapping, dialect và SQL log |
| H2 test không dùng Single Query Loading | Dialect H2 không hỗ trợ window functions cần thiết | Test trên database production-compatible |
| Projection vẫn tải nhiều dữ liệu | Query chọn quá nhiều cột hoặc return aggregate thay vì DTO | SELECT đúng cột và map DTO rõ ràng |
| @Query JOIN nhưng collection vẫn query riêng | Default RowMapper xử lý collection bằng statement riêng | Dùng DTO/RowMapper hoặc custom ResultSetExtractor nếu cần một read model |
| Một order xuất hiện nhiều lần | JOIN one-to-many tạo nhiều result rows | Group rows theo root ID hoặc aggregate trong SQL |
| Tổng tiền bị nhân đôi | JOIN nhiều collection tạo tích Descartes | Aggregate từng collection trong subquery/CTE trước khi JOIN |
| Page có ít root hơn mong đợi | LIMIT áp dụng trên joined rows | Page root IDs trước, rồi fetch phần còn lại |
| Single Query Loading không hoạt động | Có nested collection, Map, AggregateReference hoặc embedded entity | Dùng default loading hoặc query read model riêng |
| SQL JOIN chậm dù chỉ một statement | Plan scan lớn, thiếu index, result rows quá nhiều | EXPLAIN, kiểm tra cardinality/index và payload |
| DTO mapping lỗi kiểu dữ liệu | Alias, JDBC type hoặc RowMapper không khớp | Kiểm tra ResultSet metadata và mapping |
| Query summary sai khi không có child | INNER JOIN hoặc COUNT(*)/SUM xử lý NULL không đúng | LEFT JOIN, COUNT(child.id), COALESCE |
| Dữ liệu domain bị thiếu khi dùng DTO cho command | DTO không chứa invariant/owned entities cần thiết | Load aggregate cho command use case |

## 15. Quy trình ra quyết định

1. **Xác định mục đích:** caller cần aggregate để thay đổi nghiệp vụ hay chỉ cần dữ liệu đọc?
2. **Nếu chỉ cần một phần dữ liệu:** thiết kế projection DTO và SELECT đúng các cột cần thiết.
3. **Nếu cần dữ liệu từ bảng liên quan:** dùng JOIN cho to-one hoặc query aggregate/subquery cho to-many.
4. **Kiểm tra cardinality:** tính số rows sau JOIN; tránh nhân chéo nhiều collection.
5. **Nếu cần aggregate đầy đủ:** dùng repository find method phù hợp.
6. **Kiểm tra Single Query Loading:** phiên bản từ 3.2, mapping không có giới hạn, method CrudRepository được hỗ trợ và dialect có window functions.
7. **Đo query thực tế:** count statements, rows, bytes, latency, CPU và allocation.
8. **Kiểm tra pagination:** page theo root, dùng sort ổn định và cân nhắc keyset cho offset sâu.
9. **Kiểm thử trên database mục tiêu:** xác nhận SQL, dialect, mapping, count và concurrency.
10. **Chọn phương án theo tổng chi phí:** round-trip, dữ liệu truyền, CPU database, JVM và độ phức tạp bảo trì.

### Bảng quyết định nhanh

| Tình huống | Ưu tiên thử |
|---|---|
| Danh sách chỉ cần vài field và số liệu tổng hợp | Projection DTO + SQL aggregate |
| Cần tên một quan hệ to-one cùng root | SQL JOIN |
| Cần một collection cho read-only detail | JOIN + ResultSetExtractor hoặc query riêng; đo cardinality |
| Cần nhiều collection trực tiếp trong aggregate và method CrudRepository được hỗ trợ | Thử Single Query Loading nếu dialect/mapping đủ điều kiện |
| Có nested collections, Map, AggregateReference hoặc embedded entities | Default loading hoặc custom read model |
| Derived query hoặc @Query cần load aggregate | Default loading; tối ưu query/index hoặc đổi sang fragment phù hợp |
| JOIN nhiều collection làm tăng rows mạnh | Subquery/CTE aggregate từng collection hoặc Single Query Loading nếu phù hợp |
| Command cần invariant/domain behavior | Load aggregate đầy đủ bằng repository |
| Báo cáo nhiều bảng, không cần aggregate behavior | Custom SQL/fragment trả DTO |

**Điểm cốt lõi:** projection DTO phù hợp khi caller chỉ cần một phần dữ liệu; SQL JOIN phù hợp khi quan hệ và cardinality được kiểm soát; Single Query Loading phù hợp khi cần aggregate đầy đủ và mọi điều kiện của Spring Data JDBC được đáp ứng. Chọn bằng số đo tổng thể — query count, rows/bytes, latency, database CPU và JVM allocation — thay vì chỉ đếm số câu SQL.

## Tài liệu tham khảo chính thức

- [Spring Data Relational — Persisting Entities and Loading Aggregates](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html): cách tải aggregate truyền thống, Single Query Loading, giới hạn và cấu hình JdbcMappingContext.
- [Spring Data Relational — Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html): @Query, RowMapper, ResultSetExtractor, mapping collection và pagination limitations.
- [Spring Data Relational — JdbcMappingContext API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/core/mapping/JdbcMappingContext.html): setSingleQueryLoadingEnabled(boolean).
- [Spring Data Relational — AbstractJdbcConfiguration API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/repository/config/AbstractJdbcConfiguration.html): cấu hình mapping context và infrastructure.
- [Spring Blog — Introducing Single Query Loading](https://spring.io/blog/2023/08/31/this-is-the-beginning-of-the-end-of-the-n-1-problem-introducing-single-query/): bối cảnh, cách tiếp cận và giới hạn ban đầu của Single Query Loading.
- [PostgreSQL — EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): phân tích execution plan và chi phí truy vấn.
- [PostgreSQL — Window Functions](https://www.postgresql.org/docs/current/tutorial-window.html): analytic/window functions được dùng trong các chiến lược SQL nâng cao.
- [Testcontainers — Database Modules](https://java.testcontainers.org/modules/databases/): kiểm thử tích hợp với database engine thực tế.

