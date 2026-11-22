# Parameter trong query

Trong Spring Batch, reader hoặc processor thường truy vấn database theo một tập điều kiện: ngày nghiệp vụ, trạng thái, khoảng ID, tenant, partition range hoặc watermark. Các giá trị này cần được truyền vào SQL theo cách an toàn và nhất quán.

**Parameter trong query** là giá trị được bind vào câu SQL tại thời điểm thực thi. Thay vì ghép dữ liệu vào chuỗi SQL, ứng dụng dùng placeholder của PreparedStatement hoặc named parameter. Spring Batch có thể lấy giá trị từ JobParameters, StepExecutionContext hoặc cấu hình runtime rồi chuyển chúng cho JDBC reader.

Thiết kế parameter đúng giúp:

- Ngăn SQL injection khi giá trị đến từ bên ngoài.
- Đảm bảo kiểu dữ liệu JDBC phù hợp với cột.
- Dùng lại câu SQL với nhiều bộ giá trị.
- Phân vùng dữ liệu cho các worker.
- Giữ nguyên phạm vi truy vấn khi Job restart.
- Làm rõ điều kiện lọc và dễ kiểm thử.

## 1. Vì sao không ghép parameter trực tiếp vào SQL?

Cách không an toàn:

~~~java
String sql = "SELECT id, amount FROM orders WHERE status = '"
        + status + "'";

return jdbcTemplate.query(sql, rowMapper);
~~~

Nếu status đến từ JobParameters hoặc nguồn bên ngoài, giá trị có thể chứa dấu nháy hoặc đoạn SQL ngoài ý muốn. Việc ghép chuỗi còn khiến database phải parse một câu SQL khác nhau theo từng giá trị.

Dùng placeholder:

~~~java
String sql =
        "SELECT id, amount FROM orders WHERE status = ?";

return jdbcTemplate.query(sql, rowMapper, status);
~~~

JDBC gửi câu SQL và giá trị parameter riêng biệt. Driver bind giá trị theo kiểu dữ liệu tương ứng, không diễn giải nội dung parameter như cú pháp SQL.

PreparedStatement không chỉ giúp bảo mật. Nó còn làm câu SQL dễ đọc, dễ tái sử dụng và tránh lỗi escaping thủ công.

## 2. Positional parameter với dấu hỏi

JDBC PreparedStatement sử dụng dấu hỏi làm placeholder:

~~~sql
SELECT id, customer_id, amount
FROM orders
WHERE status = ?
  AND created_at >= ?
  AND created_at < ?
ORDER BY id
~~~

Parameter được bind theo vị trí bắt đầu từ 1:

~~~java
PreparedStatement statement = connection.prepareStatement(sql);

statement.setString(1, status);
statement.setTimestamp(2, startTimestamp);
statement.setTimestamp(3, endTimestamp);
~~~

Thứ tự bind phải khớp chính xác thứ tự placeholder trong SQL. Nếu đảo vị trí hai parameter cùng có kiểu tương thích, câu query có thể chạy nhưng trả dữ liệu sai mà không phát sinh lỗi rõ ràng.

Với nhiều điều kiện, nên giữ SQL và phần bind gần nhau, hoặc dùng NamedParameterJdbcTemplate để giảm nhầm lẫn thứ tự.

## 3. Dùng JdbcTemplate trong processor hoặc service

JdbcTemplate phù hợp khi processor hoặc service cần truy vấn dữ liệu phụ trợ cho từng item.

Ví dụ kiểm tra trạng thái khách hàng:

~~~java
public class CustomerLookupService {

    private final JdbcTemplate jdbcTemplate;

    public CustomerLookupService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public CustomerStatus findStatus(Long customerId) {
        String sql = """
                SELECT status
                FROM customer
                WHERE id = ?
                """;

        return jdbcTemplate.queryForObject(
                sql,
                (rs, rowNum) ->
                        CustomerStatus.valueOf(rs.getString("status")),
                customerId);
    }
}
~~~

Parameter customerId được bind vào placeholder. Không cần tự chuyển ID thành chuỗi hoặc đặt dấu nháy trong SQL.

Nếu processor gọi service này cho từng item, cần xem xét N+1 query. Với chunk lớn, có thể batch lookup theo tập customer ID hoặc join dữ liệu ngay trong reader để giảm số round-trip tới database.

## 4. NamedParameterJdbcTemplate

Khi SQL có nhiều parameter, named parameter giúp câu query dễ đọc hơn.

~~~java
String sql = """
        SELECT id, customer_id, amount
        FROM orders
        WHERE status = :status
          AND created_at >= :startTime
          AND created_at < :endTime
        ORDER BY id
        """;

MapSqlParameterSource parameters = new MapSqlParameterSource()
        .addValue("status", status)
        .addValue("startTime", startTime)
        .addValue("endTime", endTime);

List<Order> orders = namedParameterJdbcTemplate.query(
        sql,
        parameters,
        orderRowMapper);
~~~

Tên trong SQL phải khớp với key trong parameter source. NamedParameterJdbcTemplate chuyển named parameter thành placeholder JDBC phù hợp trước khi thực thi.

Named parameter giúp tránh nhầm vị trí khi thêm hoặc đổi điều kiện. Tuy nhiên, nó vẫn bind **giá trị**, không cho phép truyền tên bảng, tên cột hoặc từ khóa SQL như một parameter.

## 5. Lấy parameter từ JobParameters

Một Job thường nhận các giá trị như business date, tenant ID, input mode hoặc giới hạn ID khi được launch.

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addLong("minOrderId", 1000L, true)
        .addString("status", "READY", false)
        .toJobParameters();
~~~

Các tham số này có thể được inject vào bean StepScope bằng SpEL:

~~~java
@Bean
@StepScope
public ItemReader<Order> orderReader(
        @Value("#{jobParameters['businessDate']}") String dateText,
        @Value("#{jobParameters['minOrderId']}") Long minOrderId,
        @Value("#{jobParameters['status']}") String status) {
    // Tạo reader với các giá trị đã resolve.
}
~~~

StepScope trì hoãn việc tạo target bean tới khi StepExecution hoạt động. Khi đó JobParameters của lần chạy hiện tại đã sẵn sàng.

Nếu parameter bắt buộc, hãy xác thực trước khi Step chạy bằng JobParametersValidator. Không để một giá trị null đi sâu vào query rồi mới thất bại do conversion hoặc SQL semantics.

## 6. Parameter từ StepExecutionContext

Với partitioning, mỗi worker thường truy vấn một khoảng dữ liệu riêng. Partitioner có thể đưa fromId và toId vào StepExecutionContext của từng partition.

Reader nhận các giá trị đó bằng StepScope:

~~~java
@Bean
@StepScope
public JdbcCursorItemReader<Order> partitionOrderReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['fromId']}") Long fromId,
        @Value("#{stepExecutionContext['toId']}") Long toId) {

    // Cấu hình query cho khoảng ID của partition.
}
~~~

Ví dụ mỗi worker nhận một khoảng:

| Partition | fromId | toId |
|---|---:|---:|
| worker-0 | 1 | 10000 |
| worker-1 | 10001 | 20000 |
| worker-2 | 20001 | 30000 |

Query có thể dùng:

~~~sql
SELECT id, amount
FROM orders
WHERE id >= ?
  AND id <= ?
ORDER BY id
~~~

Mỗi StepExecution có context riêng, vì vậy reader của partition cần được tạo theo StepScope. Không dùng một reader singleton có mutable parameter fields chung cho nhiều worker.

## 7. Dùng PreparedStatementSetter với JdbcCursorItemReader

JdbcCursorItemReader dùng JDBC cursor để đọc kết quả tuần tự. Khi SQL có positional parameter, có thể truyền PreparedStatementSetter để bind giá trị.

Ví dụ:

~~~java
@Bean
@StepScope
public JdbcCursorItemReader<Order> orderCursorReader(
        DataSource dataSource,
        @Value("#{jobParameters['status']}") String status,
        @Value("#{jobParameters['minOrderId']}") Long minOrderId) {

    String sql = """
            SELECT id, customer_id, amount, status
            FROM orders
            WHERE status = ?
              AND id > ?
            ORDER BY id
            """;

    return new JdbcCursorItemReaderBuilder<Order>()
            .name("orderCursorReader")
            .dataSource(dataSource)
            .sql(sql)
            .preparedStatementSetter(statement -> {
                statement.setString(1, status);
                statement.setLong(2, minOrderId);
            })
            .rowMapper(orderRowMapper())
            .fetchSize(500)
            .saveState(true)
            .build();
}
~~~

PreparedStatementSetter được gọi khi reader chuẩn bị câu query. Các giá trị được bind theo thứ tự placeholder.

Nếu parameter có thể null, cần quyết định kiểu JDBC và ý nghĩa SQL trước khi bind. Không gọi setLong với Long null vì Java sẽ unbox null và gây NullPointerException. Dùng setNull với java.sql.Types tương ứng hoặc thiết kế predicate phù hợp.

## 8. Bind ngày và thời gian đúng kiểu JDBC

Ngày nghiệp vụ và timestamp cần được bind với kiểu phù hợp. Tránh nối chuỗi ngày vào SQL vì format và locale có thể khác giữa môi trường.

Ví dụ lọc theo một ngày:

~~~java
LocalDate businessDate = LocalDate.parse(dateText);

statement.setDate(
        1,
        java.sql.Date.valueOf(businessDate));
~~~

Với khoảng thời gian:

~~~java
LocalDateTime start = businessDate.atStartOfDay();
LocalDateTime end = businessDate.plusDays(1).atStartOfDay();

statement.setTimestamp(
        1,
        Timestamp.valueOf(start));

statement.setTimestamp(
        2,
        Timestamp.valueOf(end));
~~~

Query dùng khoảng đóng ở đầu và mở ở cuối:

~~~sql
WHERE created_at >= ?
  AND created_at < ?
~~~

Cách này tránh phải tạo mốc 23:59:59.999... và phù hợp hơn khi precision timestamp khác nhau.

Nếu cột lưu UTC instant hoặc có timezone semantics riêng, hãy chuyển đổi theo ZoneId nghiệp vụ đã xác định. Không dựa vào timezone mặc định của JVM để tạo timestamp.

## 9. Parameter trong JdbcPagingItemReader

JdbcPagingItemReader đọc dữ liệu theo trang. Query provider tạo SQL phù hợp với database và sort key. Các giá trị named parameter được truyền qua parameterValues.

Ví dụ dùng PostgresPagingQueryProvider:

~~~java
@Bean
@StepScope
public JdbcPagingItemReader<Order> orderPagingReader(
        DataSource dataSource,
        @Value("#{jobParameters['businessDate']}") String dateText,
        @Value("#{jobParameters['minOrderId']}") Long minOrderId) {

    LocalDate businessDate = LocalDate.parse(dateText);

    PostgresPagingQueryProvider queryProvider =
            new PostgresPagingQueryProvider();

    queryProvider.setSelectClause(
            "SELECT id, customer_id, amount, status");
    queryProvider.setFromClause("FROM orders");
    queryProvider.setWhereClause(
            "WHERE business_date = :businessDate AND id > :minOrderId");
    queryProvider.setSortKeys(
            Map.of("id", Order.ASCENDING));

    return new JdbcPagingItemReaderBuilder<Order>()
            .name("orderPagingReader")
            .dataSource(dataSource)
            .queryProvider(queryProvider)
            .parameterValues(Map.of(
                    "businessDate",
                    java.sql.Date.valueOf(businessDate),
                    "minOrderId",
                    minOrderId))
            .pageSize(500)
            .fetchSize(500)
            .rowMapper(orderRowMapper())
            .saveState(true)
            .build();
}
~~~

Các key trong parameterValues phải khớp tên placeholder trong whereClause. Ví dụ :businessDate cần key businessDate, không phải :business_date hoặc business_date.

Query provider chịu trách nhiệm tạo truy vấn trang tiếp theo dựa trên sort key. Cấu hình query provider và kiểu parameter phải phù hợp database thực tế.

## 10. Sort key phải ổn định và duy nhất

Paging reader cần thứ tự xác định để chuyển từ trang này sang trang tiếp theo. Nếu sort key không duy nhất, nhiều record có cùng giá trị có thể nằm ở ranh giới trang và gây trùng hoặc thiếu khi paging/restart.

Không nên chỉ sort theo status nếu nhiều order có cùng status:

~~~sql
ORDER BY status
~~~

Nên dùng khóa duy nhất làm tie-breaker:

~~~sql
ORDER BY status, id
~~~

Với JdbcPagingItemReader, cấu hình sortKeys phải phản ánh thứ tự ổn định này. Nếu dùng nhiều cột, tất cả cột cần tạo ra thứ tự xác định và điều kiện query provider có thể tiếp tục chính xác.

Nếu sort key có thể thay đổi trong lúc Job chạy, paging vẫn có nguy cơ bỏ sót hoặc đọc lặp. Hãy dùng dữ liệu snapshot, watermark hoặc phạm vi bất biến.

## 11. Parameter values và null

Named parameter có thể nhận giá trị null, nhưng câu SQL phải có semantics đúng.

Ví dụ:

~~~sql
WHERE customer_id = :customerId
~~~

Nếu customerId là null, phép so sánh bằng NULL không trả về true trong SQL. Nó cho kết quả UNKNOWN. Không thể dùng cùng predicate này để tìm các row có customer_id IS NULL.

Nếu muốn parameter tùy chọn, có thể viết:

~~~sql
WHERE (:customerId IS NULL OR customer_id = :customerId)
~~~

Cách này có thể tiện nhưng đôi khi làm query planner khó sử dụng index tối ưu. Với query quan trọng về hiệu năng, cân nhắc tạo hai câu query có predicate rõ ràng dựa trên việc parameter có mặt hay không.

Không dùng Map.of khi có thể có null vì Map.of từ chối null key/value. Hãy validate trước hoặc dùng MapSqlParameterSource/HashMap có xử lý null có chủ đích.

## 12. Parameter tùy chọn và dynamic filters

Một query có thể có nhiều filter tùy chọn: status, customer ID, ngày bắt đầu, ngày kết thúc. Không nên nối giá trị vào SQL.

Có thể xây dựng danh sách predicate từ các điều kiện đã được xác thực, nhưng chỉ nối các đoạn SQL cố định do ứng dụng kiểm soát:

~~~java
List<String> predicates = new ArrayList<>();
MapSqlParameterSource params = new MapSqlParameterSource();

if (status != null) {
    predicates.add("status = :status");
    params.addValue("status", status);
}

if (customerId != null) {
    predicates.add("customer_id = :customerId");
    params.addValue("customerId", customerId);
}

String where = predicates.isEmpty()
        ? ""
        : " WHERE " + String.join(" AND ", predicates);

String sql = """
        SELECT id, customer_id, amount
        FROM orders
        """ + where + " ORDER BY id";
~~~

Giá trị vẫn được bind qua params. Chỉ các đoạn predicate cố định được ứng dụng lựa chọn mới được nối vào SQL.

Với JdbcPagingItemReader, query provider thường được cấu hình trước khi reader chạy. Nếu filter thay đổi theo JobParameters, hãy tạo query provider trong bean StepScope với cấu trúc predicate tương ứng và parameterValues phù hợp.

## 13. Không thể bind tên bảng hoặc tên cột bằng placeholder

Placeholder đại diện cho **giá trị**, không phải SQL identifier.

Câu này không hoạt động như mong đợi:

~~~sql
SELECT * FROM ? WHERE status = ?
~~~

Parameter đầu tiên không thể thay thế tên bảng. JDBC sẽ xem nó là một giá trị expression, không phải identifier.

Nếu người dùng cần chọn bảng hoặc cột, dùng whitelist:

~~~java
Map<String, String> allowedTables = Map.of(
        "orders", "orders",
        "returns", "returns");

String table = allowedTables.get(requestedTable);

if (table == null) {
    throw new IllegalArgumentException("Unsupported table");
}

String sql = "SELECT id, status FROM " + table
        + " WHERE status = ?";
~~~

requestedTable được đối chiếu với danh sách cho phép. Chỉ tên bảng đã được ứng dụng kiểm soát mới được đưa vào SQL. Giá trị status vẫn dùng placeholder.

Áp dụng cùng nguyên tắc cho ORDER BY, tên cột, schema, operator và các đoạn SQL động khác. Không ghép trực tiếp dữ liệu bên ngoài vào identifier hoặc keyword.

## 14. Parameter cho IN clause

Khi cần lọc theo một danh sách ID, NamedParameterJdbcTemplate hỗ trợ mở rộng collection parameter trong IN clause:

~~~sql
SELECT id, amount
FROM orders
WHERE id IN (:orderIds)
~~~

Ví dụ:

~~~java
MapSqlParameterSource parameters = new MapSqlParameterSource()
        .addValue("orderIds", orderIds);

List<Order> orders = namedParameterJdbcTemplate.query(
        sql,
        parameters,
        orderRowMapper);
~~~

NamedParameterJdbcTemplate mở rộng collection thành số placeholder phù hợp và bind từng phần tử.

Cần xử lý danh sách rỗng trước khi chạy query. Một IN clause không có phần tử có thể tạo SQL không hợp lệ hoặc behavior khác theo framework/database. Hãy quyết định rõ: danh sách rỗng có nghĩa không trả record nào, không áp dụng filter hay là input không hợp lệ.

Với danh sách rất lớn, tránh tạo hàng chục nghìn placeholder. Có thể dùng temporary table, table-valued parameter, staging table hoặc join với nguồn dữ liệu đã được nạp trước tùy database.

## 15. LIKE parameter và wildcard

Có thể bind pattern cho LIKE:

~~~sql
WHERE customer_name LIKE ?
~~~

Ví dụ tìm tên bắt đầu bằng chuỗi prefix:

~~~java
statement.setString(1, prefix + "%");
~~~

Dấu % và _ là wildcard trong LIKE. Nếu người dùng nhập chúng như ký tự literal, cần escape theo quy tắc database và khai báo ESCAPE character:

~~~sql
WHERE customer_name LIKE :pattern ESCAPE '\'
~~~

Cần escape ký tự escape trước, sau đó escape % và _. Không giả định parameterization tự biến wildcard thành ký tự thường; parameterization ngăn SQL injection nhưng không thay đổi semantics của LIKE.

## 16. Kiểu parameter phải khớp kiểu cột

Bind sai kiểu có thể khiến database cast ngầm, bỏ qua index hoặc từ chối query.

Ví dụ:

- BIGINT: setLong hoặc Long.
- INTEGER: setInt hoặc Integer.
- DECIMAL/NUMERIC: setBigDecimal hoặc BigDecimal.
- DATE: setDate hoặc java.sql.Date.
- TIMESTAMP: setTimestamp hoặc kiểu JDBC phù hợp.
- VARCHAR: setString.
- BOOLEAN: setBoolean.

Không chuyển tất cả parameter thành String chỉ để tiện cấu hình. Database có thể phải cast chuỗi sang kiểu cột, dẫn tới lỗi format hoặc query plan kém.

Với enum, quyết định lưu tên, code hay ordinal. Nếu lưu tên, bind String theo code đã định nghĩa. Không dùng enum.ordinal() làm business value vì thay đổi thứ tự enum có thể làm sai dữ liệu.

## 17. Parameter và query plan

Database thường có thể tái sử dụng prepared statement hoặc query plan cho câu SQL có cấu trúc ổn định. Điều này có thể giảm chi phí parse và plan.

Tuy nhiên, parameterization không đảm bảo mọi query luôn có plan tối ưu. Một số database có parameter sniffing hoặc kế hoạch phụ thuộc phân bố dữ liệu.

Khi query chậm:

- Kiểm tra execution plan.
- Kiểm tra index trên các cột lọc và sort.
- Kiểm tra kiểu parameter có khớp kiểu cột.
- Kiểm tra selectivity của filter.
- Tránh predicate tùy chọn dạng OR nếu làm planner bỏ qua index.
- Đo với các giá trị đại diện, không chỉ một bộ parameter.

Không thêm hint hoặc ép cast chỉ dựa trên phỏng đoán. Hãy dùng execution plan và dữ liệu thực tế.

## 18. Parameter trong JdbcCursorItemReader và JdbcPagingItemReader

Hai reader hỗ trợ cách đọc khác nhau:

| Tiêu chí | JdbcCursorItemReader | JdbcPagingItemReader |
|---|---|---|
| Cách đọc | Cursor tuần tự | Truy vấn từng trang |
| Parameter phổ biến | PreparedStatementSetter | Map named parameterValues |
| Sort key | ORDER BY để có thứ tự ổn định | Bắt buộc để paging ổn định |
| Kết nối | Có thể giữ cursor/connection trong thời gian Step | Mở query theo từng trang |
| Restart | Khôi phục vị trí theo reader state | Tiếp tục dựa trên paging state/sort keys |
| Phù hợp | Đọc tuần tự trên cursor | Dataset lớn cần phân trang hoặc không tiện giữ cursor |

Cả hai cần reader name ổn định và saveState khi muốn hỗ trợ restart. Chọn theo database driver, transaction, concurrency, kích thước dữ liệu và khả năng truy vấn tiếp tục.

Parameter values cần giống nhau qua restart. Nếu ngày nghiệp vụ hoặc partition range thay đổi giữa lần chạy và lần restart, reader có thể tiếp tục trên tập dữ liệu khác.

## 19. Parameter và restart identity

JobParameters có hai vai trò riêng:

- Truyền giá trị runtime cho query.
- Xác định JobInstance nếu parameter được đánh dấu identifying.

Nếu businessDate xác định tập dữ liệu, thường nên coi nó là identifying parameter. Nếu thay đổi businessDate mà vẫn dùng cùng JobInstance, restart có thể truy vấn một tập record khác với checkpoint đã lưu.

Ví dụ:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addLong("minOrderId", 1000L, true)
        .addString("traceLabel", "night-run", false)
        .toJobParameters();
~~~

traceLabel chỉ phục vụ quan sát nên có thể non-identifying. businessDate và minOrderId ảnh hưởng phạm vi query nên cần được xem xét trong identity.

Nếu parameter đến từ StepExecutionContext của partition, context đó được lưu theo StepExecution. Khi restart partition, cần khôi phục đúng range đã cấp, không tính range mới theo dữ liệu thay đổi nếu muốn tiếp tục cùng công việc.

## 20. Snapshot và dữ liệu thay đổi trong lúc paging

Ngay cả khi parameter không đổi, dữ liệu nguồn có thể thay đổi trong lúc Job chạy.

Ví dụ reader dùng:

~~~sql
WHERE id > :lastId
ORDER BY id
~~~

Nếu record mới được insert với ID lớn hơn lastId trong lúc Step đang chạy, reader có thể đọc thêm record đó. Nếu update hoặc delete record ảnh hưởng predicate, kết quả qua các trang có thể thay đổi.

Các chiến lược:

- Chốt upper bound khi bắt đầu: id <= :maxId.
- Dùng business date hoặc batch ID bất biến.
- Dùng snapshot isolation nếu database và workload hỗ trợ.
- Đọc từ staging table đã được cố định.
- Lưu watermark và query range vào JobParameters hoặc ExecutionContext.

Ví dụ:

~~~sql
WHERE id > :lastId
  AND id <= :upperBound
ORDER BY id
~~~

upperBound phải được giữ nguyên qua restart. Nếu tính lại max(id) ở mỗi lần restart, tập dữ liệu có thể mở rộng và Job xử lý nhiều record hơn dự kiến.

## 21. Query parameter cho tenant isolation

Nếu dữ liệu phân tách theo tenant, tenantId cần được đưa vào mọi query liên quan:

~~~sql
SELECT id, amount
FROM orders
WHERE tenant_id = :tenantId
  AND business_date = :businessDate
ORDER BY id
~~~

Không lấy tenantId từ dữ liệu item rồi bỏ qua phạm vi tenant đã xác thực. Hãy xác thực tenant ở bước launch hoặc theo security context đáng tin cậy.

Với partitioning, mỗi partition vẫn cần giữ tenantId đúng và range riêng. Đừng cho phép JobParameters hoặc file input tự do chọn tenant nếu caller không được cấp quyền.

Tenant parameter ảnh hưởng trực tiếp đến phạm vi dữ liệu, vì vậy cần được coi là một phần của contract và restart identity phù hợp.

## 22. Parameter cho processor query và tránh N+1

Processor có thể dùng query parameter để lookup dữ liệu cho từng item:

~~~java
public OrderEnrichment process(OrderInput input) {
    Customer customer = namedParameterJdbcTemplate.queryForObject(
            """
            SELECT id, tier
            FROM customer
            WHERE id = :customerId
            """,
            Map.of("customerId", input.customerId()),
            customerRowMapper);

    return enrich(input, customer);
}
~~~

Cách này an toàn nhưng có thể tạo một query cho mỗi item. Với 1 triệu item, processor có thể thực hiện 1 triệu query lookup.

Có thể cải thiện:

- Join customer trong query của reader nếu phù hợp.
- Cache lookup bất biến có giới hạn.
- Gom ID theo chunk và lookup một lần.
- Dùng bulk query với IN clause hoặc staging table.
- Dùng processor có dữ liệu reference được nạp trước nếu tập nhỏ.

Nếu cache dữ liệu thay đổi theo tenant hoặc business date, key cache cần bao gồm các parameter đó. Không dùng cache global chỉ theo customer ID nếu cùng ID có thể tồn tại trong nhiều tenant.

## 23. Parameter cho Stored Procedure

Stored procedure cũng nhận parameter theo vị trí hoặc tên tùy database/driver. Với Spring JDBC, có thể dùng SimpleJdbcCall hoặc CallableStatementCreator.

Ví dụ CallableStatement:

~~~java
CallableStatement statement =
        connection.prepareCall("{call refresh_order_status(?, ?)}");

statement.setDate(1, java.sql.Date.valueOf(businessDate));
statement.setString(2, tenantId);

statement.execute();
~~~

Cần xác định parameter IN, OUT và INOUT, kiểu JDBC, transaction participation và behavior khi retry. Stored procedure có thể thực hiện commit nội bộ hoặc side effect khác; hãy kiểm tra implementation trước khi giả định chunk rollback sẽ hoàn tác tất cả.

Không ghép parameter vào chuỗi gọi procedure. Dùng bind API tương ứng.

## 24. Query timeout, fetch size và parameter

Parameter query là một phần của hiệu năng, nhưng reader còn có các cấu hình vận hành:

- fetchSize: gợi ý số row driver lấy mỗi lần.
- queryTimeout: giới hạn thời gian query theo giây nếu driver hỗ trợ.
- maxRows: giới hạn số row được trả về.
- pageSize: số item mỗi trang của paging reader.
- chunk size: số item mỗi transaction chunk.

Ví dụ:

~~~java
return new JdbcCursorItemReaderBuilder<Order>()
        .name("orderCursorReader")
        .dataSource(dataSource)
        .sql(sql)
        .preparedStatementSetter(setter)
        .rowMapper(orderRowMapper())
        .fetchSize(500)
        .queryTimeout(60)
        .saveState(true)
        .build();
~~~

fetchSize không phải chunk size. Driver có thể diễn giải fetchSize khác nhau; một số driver cần cấu hình cursor hoặc transaction phù hợp để streaming thực sự.

Query timeout không phải retry policy. Khi timeout, cần xác định exception và quyết định có retry được không.

## 25. SQL parameter và injection

Parameterization bảo vệ giá trị nhưng không tự bảo vệ mọi phần SQL được tạo động.

An toàn:

~~~java
String sql = "SELECT id FROM orders WHERE status = ?";
jdbcTemplate.query(sql, rowMapper, status);
~~~

Không an toàn:

~~~java
String sql = "SELECT id FROM orders ORDER BY " + sortColumn;
~~~

Nếu sortColumn đến từ bên ngoài, attacker có thể chèn biểu thức SQL. Hãy dùng whitelist:

~~~java
Map<String, String> sortColumns = Map.of(
        "created", "created_at",
        "amount", "amount",
        "id", "id");

String column = sortColumns.get(requestedSort);

if (column == null) {
    throw new IllegalArgumentException("Unsupported sort field");
}

String sql = "SELECT id FROM orders ORDER BY " + column;
~~~

Giá trị filter vẫn nên bind bằng placeholder. Identifier chỉ được chọn từ danh sách cố định do ứng dụng quản lý.

## 26. Kiểm thử parameter binding

Unit test hoặc integration test nên xác nhận giá trị được bind đúng và kết quả query chính xác.

Ví dụ với JdbcTemplate có database test:

~~~java
@Test
void filtersOrdersByStatusAndDate() {
    insertOrder(1L, "READY", LocalDate.of(2026, 11, 15));
    insertOrder(2L, "DONE", LocalDate.of(2026, 11, 15));
    insertOrder(3L, "READY", LocalDate.of(2026, 11, 14));

    List<Order> result = repository.findReadyOrders(
            "READY",
            LocalDate.of(2026, 11, 15));

    assertEquals(List.of(1L), result.stream()
            .map(Order::id)
            .toList());
}
~~~

Test cần bao phủ:

- Giá trị bình thường.
- Null hoặc parameter tùy chọn.
- Chuỗi có dấu nháy và ký tự SQL đặc biệt.
- Ngày ở ranh giới đầu/cuối.
- Kiểu số lớn và overflow.
- Danh sách rỗng cho IN.
- Parameter sai tên trong named query.
- Parameter sai thứ tự trong PreparedStatementSetter.
- Partition range không giao nhau và không bỏ sót.

Dùng database test phù hợp nếu SQL phụ thuộc cú pháp riêng của database. H2 có thể không mô phỏng đầy đủ PostgreSQL, Oracle hoặc SQL Server.

## 27. Kiểm thử restart với query parameter

Một integration test restart cần chứng minh reader tiếp tục trên cùng tập dữ liệu:

1. Launch Job với businessDate và minOrderId.
2. Cho một chunk commit.
3. Làm chunk sau thất bại.
4. Restart cùng JobInstance và cùng identifying parameters.
5. Xác nhận reader tiếp tục từ checkpoint.
6. Xác nhận query vẫn dùng cùng businessDate, minOrderId và partition range.
7. Xác nhận item đã commit không bị ghi trùng.
8. Xác nhận item chưa commit được xử lý lại.

Không chỉ kiểm tra Step status. Hãy so sánh business key trong bảng đích với tập dữ liệu nguồn dự kiến.

Nếu parameter được lấy từ StepExecutionContext, kiểm tra context được lưu và phục hồi đúng cho partition restart.

## 28. Những lỗi thường gặp

### Ghép giá trị vào SQL bằng String concatenation

Có nguy cơ SQL injection và lỗi escaping. Dùng PreparedStatement hoặc NamedParameterJdbcTemplate.

### Dùng placeholder cho tên bảng hoặc cột

Placeholder chỉ bind giá trị. Dùng whitelist cho identifier động.

### Sai thứ tự positional parameter

Query chạy nhưng lọc sai. Giữ SQL và PreparedStatementSetter gần nhau, test thứ tự bind.

### Named parameter không khớp key

SQL dùng :businessDate nhưng map lại có business_date. Tên phải khớp chính xác.

### Bind ngày giờ dưới dạng String

Database phải cast theo locale/format. Dùng JDBC Date/Timestamp phù hợp.

### Dùng phép so sánh bằng với NULL

column = NULL không tìm được row null. Dùng IS NULL hoặc predicate riêng.

### Dùng Map.of với giá trị có thể null

Map.of từ chối null. Validate hoặc dùng MapSqlParameterSource có chủ đích.

### Parameter tùy chọn làm query mất index

Predicate dạng OR có thể làm plan kém. Đo execution plan và cân nhắc query shape riêng.

### Paging sort key không duy nhất

Có thể trùng hoặc thiếu record ở ranh giới trang. Dùng sort key duy nhất hoặc composite key ổn định.

### Thay đổi parameter giữa restart

Checkpoint cũ có thể áp dụng lên tập dữ liệu mới. Giữ identifying parameters và query context nhất quán.

### Processor tạo N+1 query

Hiệu năng giảm theo số item. Dùng join, bulk lookup hoặc cache có giới hạn.

### Query đọc dữ liệu đang thay đổi

Paging có thể thấy tập record khác giữa các trang hoặc lần restart. Dùng upper bound, snapshot hoặc staging.

## 29. Quy trình thiết kế parameter trong query

Trước khi triển khai query trong Spring Batch, hãy xác định:

1. Parameter đến từ JobParameters, StepExecutionContext hay nguồn cấu hình nào?
2. Parameter bắt buộc hay tùy chọn?
3. Giá trị được bind bằng PreparedStatementSetter hay named parameter?
4. Kiểu Java/JDBC có khớp kiểu cột không?
5. Có parameter null và SQL semantics tương ứng không?
6. Query có dynamic filter hoặc identifier cần whitelist không?
7. Paging có sort key ổn định và duy nhất không?
8. Parameter có xác định phạm vi dữ liệu hoặc tenant không?
9. Parameter có cần identifying để restart cùng JobInstance không?
10. Nguồn dữ liệu có thể thay đổi trong khi Step chạy không?
11. Query plan, index, fetch size và timeout đã được đo chưa?
12. Test có kiểm tra bind values, injection strings, boundary, partition và restart không?

Parameter trong query là cầu nối giữa cấu hình thực thi của Job và dữ liệu database. Hãy lấy giá trị từ JobParameters hoặc ExecutionContext theo đúng scope, bind bằng PreparedStatement hoặc named parameter, giữ identifier động trong whitelist và chọn kiểu JDBC phù hợp. Với paging hoặc partitioning, sort key và query range phải ổn định; với restart, các parameter xác định tập dữ liệu cần giữ nguyên. Thiết kế như vậy giúp query an toàn, dễ kiểm thử và cho kết quả nhất quán qua nhiều lần thực thi.
