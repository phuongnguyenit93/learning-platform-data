# Kiểm thử tích hợp trên hệ quản trị thực để xác minh kế hoạch và hành vi JDBC

## Vì sao cần kiểm thử trên hệ quản trị cơ sở dữ liệu thực?

Ứng dụng Java thường được phát triển với JDBC, connection pool, ORM hoặc thư viện truy cập dữ liệu. Unit test có thể kiểm tra logic chuyển đổi dữ liệu và cách ứng dụng gọi repository, nhưng một database giả lập hoặc database thay thế không nhất thiết tái hiện đúng hành vi của hệ quản trị sẽ chạy trong production.

Các hệ quản trị khác nhau về kiểu dữ liệu, quy tắc NULL, collation, xử lý transaction, isolation, khóa, generated key, cú pháp SQL, optimizer và cách driver JDBC triển khai protocol. Ngay cả hai phiên bản của cùng một hệ quản trị cũng có thể khác nhau về kế hoạch thực thi, thống kê, kiểu dữ liệu hoặc tính năng được hỗ trợ. Vì vậy, một truy vấn chạy qua H2 trong test không chứng minh truy vấn đó sẽ có cùng kết quả hoặc hiệu năng trên PostgreSQL, MySQL hay SQL Server.

Kiểm thử tích hợp trên hệ quản trị thực (real database integration testing) khởi tạo một instance database tương thích với môi trường mục tiêu, áp dụng schema/migration thật, nạp dữ liệu đại diện và chạy ứng dụng qua driver JDBC thật. Cách này giúp phát hiện lỗi ở ranh giới giữa ứng dụng, driver, transaction manager và database engine.

Trong tối ưu hiệu năng cơ sở dữ liệu, kiểm thử tích hợp còn giúp xác minh các giả thuyết dựa trên execution plan và thống kê: chỉ mục có được dùng không, điều kiện lọc có pruning/seek đúng không, số hàng thực tế có gần ước lượng không, transaction có giữ khóa quá lâu không và JDBC có gửi đúng kiểu tham số hay không. Bài học này tập trung vào cách xây dựng test đáng tin cậy, xác minh hành vi JDBC và kiểm tra kế hoạch thực thi mà không biến test thành một benchmark thiếu kiểm soát.

## Kiểm thử tích hợp khác gì unit test và kiểm thử hiệu năng?

| Loại kiểm thử | Phạm vi chính | Ví dụ | Điều không thể kết luận riêng từ loại test này |
|---|---|---|---|
| Unit test | Logic nhỏ, phụ thuộc được thay thế hoặc cô lập | Mapping DTO, kiểm tra điều kiện nghiệp vụ | SQL có chạy đúng trên engine thật hay không |
| Repository test với database thực | SQL, mapping, transaction và ràng buộc trên engine mục tiêu | INSERT/UPDATE, JOIN, generated keys | Hệ thống chịu được tải production hay không |
| Integration test nhiều thành phần | Kết nối ứng dụng, pool, migration, database và các thành phần liên quan | Khởi động service và gọi API truy vấn | Throughput tối đa trong mọi môi trường |
| Performance/load test | Độ trễ, throughput và tài nguyên dưới tải có kiểm soát | Tải đồng thời nhiều session và đo p95/p99 | Tính đúng đắn mọi trường hợp nghiệp vụ nếu không có assertion phù hợp |

Một integration test có thể đo thời gian và đọc execution plan, nhưng không nên dùng một lần chạy đơn lẻ để tuyên bố truy vấn đạt SLO. Hiệu năng phụ thuộc CPU, RAM, storage, dữ liệu, thống kê, concurrency, cache và cấu hình. Integration test chủ yếu xác minh tính đúng đắn của hành vi trên engine thật và phát hiện hồi quy rõ ràng.

## Chọn hệ quản trị và môi trường kiểm thử

### Dùng đúng engine và phiên bản mục tiêu

Nếu production chạy PostgreSQL, integration test quan trọng nên chạy PostgreSQL. Nếu production chạy MySQL/InnoDB hoặc SQL Server, hãy dùng đúng engine tương ứng. Cần khớp các yếu tố có thể ảnh hưởng đến kết quả:

- Major/minor version hoặc phiên bản tương thích đã được xác định.
- Storage engine, extension và tính năng được ứng dụng sử dụng.
- Collation, character set và timezone.
- Isolation mặc định và các thiết lập transaction quan trọng.
- Kiểu dữ liệu, precision/scale và quy tắc chuyển đổi.
- Cấu hình liên quan đến optimizer hoặc compatibility level khi cần.
- Driver JDBC và phiên bản driver đang được ứng dụng sử dụng.

Không cần sao chép toàn bộ cấu hình production vào mọi test. Nhưng nếu một hành vi phụ thuộc cấu hình, chẳng hạn isolation, collation, timezone hoặc optimizer feature, môi trường test phải mô phỏng cấu hình liên quan.

### Container giúp tạo môi trường lặp lại

Testcontainers có thể khởi chạy database trong container khi test chạy và dừng container sau đó. Mỗi lần chạy có thể dùng image đã cố định phiên bản, áp dụng migration và nạp dữ liệu fixture.

Ví dụ dưới đây dùng PostgreSQL và JUnit 5. Cấu trúc tương tự có thể áp dụng cho module Testcontainers của MySQL hoặc SQL Server, với image, port và cấu hình phù hợp.

~~~java
@Testcontainers
class OrderRepositoryIT {

    @Container
    static final PostgreSQLContainer<?> database =
        new PostgreSQLContainer<>("postgres:16.4")
            .withDatabaseName("app_test")
            .withUsername("app")
            .withPassword("test");

    private HikariDataSource dataSource;

    @BeforeEach
    void setUp() {
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl(database.getJdbcUrl());
        config.setUsername(database.getUsername());
        config.setPassword(database.getPassword());
        dataSource = new HikariDataSource(config);

        // Chạy migration thật của ứng dụng trước khi test.
        runMigrations(dataSource);
    }

    @AfterEach
    void tearDown() {
        if (dataSource != null) {
            dataSource.close();
        }
    }
}
~~~

Ví dụ minh họa cách khởi tạo, không phải lớp hoàn chỉnh có thể sao chép nguyên trạng vào mọi dự án. Cần thêm dependency tương ứng, cấu hình package, migration runner và cách quản lý schema theo framework đang dùng.

Có thể dùng container dùng chung cho một test class hoặc một suite để giảm thời gian khởi động. Tuy nhiên, cần cô lập dữ liệu và schema giữa các test. Nếu test chạy song song, không để nhiều test ghi vào cùng một bảng với cùng khóa hoặc cùng trạng thái dùng chung.

### Cố định image và tránh dùng latest

Không dùng tag latest cho database trong pipeline. Tag đó có thể trỏ sang phiên bản mới và làm kết quả thay đổi mà không có thay đổi source code. Cố định version hoặc digest đã được kiểm duyệt, đồng thời cập nhật có chủ đích khi nâng cấp engine.

Khi production nâng major version, hãy chạy integration test trên cả phiên bản cũ và mới trong giai đoạn chuyển đổi nếu ứng dụng cần hỗ trợ rolling upgrade hoặc rollback. Đây cũng là lúc kiểm tra thay đổi execution plan và hành vi optimizer.

### Migration phải giống production

Tạo schema bằng cùng công cụ migration và cùng thứ tự migration mà ứng dụng sử dụng. Không tự tạo một schema rút gọn trong test rồi cho rằng nó tương đương production. Migration thật có thể tạo index, constraint, generated column, trigger, sequence hoặc partition mà truy vấn phụ thuộc.

Nếu test bỏ qua migration và tự tạo bảng tối giản, nó có thể bỏ lỡ lỗi:
- Thiếu index hoặc index có thứ tự cột khác.
- Kiểu dữ liệu hoặc precision/scale không khớp.
- Unique constraint hoặc foreign key thiếu.
- Default value, identity/sequence hoặc generated column khác.
- Collation và timezone khác.
- Partition hoặc extension chưa được tạo.

Test nên thất bại sớm nếu migration không chạy được trên engine và phiên bản mục tiêu.

## Thiết kế dữ liệu kiểm thử có ý nghĩa

### Dữ liệu nhỏ nhưng phải đại diện cho quy tắc

Integration test không cần sao chép toàn bộ production data. Nhưng dữ liệu fixture phải đủ để kích hoạt các nhánh nghiệp vụ và hành vi SQL cần kiểm chứng.

Ví dụ cho bảng orders:
- Một khách hàng có nhiều đơn.
- Hai đơn có cùng created_at để kiểm tra thứ tự ổn định.
- Một đơn không có bản ghi con để kiểm tra LEFT JOIN.
- Một đơn có nhiều dòng hàng để kiểm tra cardinality.
- Các trạng thái khác nhau để kiểm tra filter.
- Giá trị NULL ở các cột cho phép NULL.
- Giá trị biên về ngày giờ, số lượng và precision.
- Hai tenant có cùng business identifier nếu khóa chỉ duy nhất trong tenant.

Dữ liệu cần phản ánh quan hệ và ràng buộc thực tế. Nếu mọi fixture đều có một hàng mỗi khóa, test sẽ không phát hiện lỗi fan-out khi dữ liệu thực có quan hệ một-nhiều.

### Dữ liệu hiệu năng cần có phân bố

Để kiểm tra execution plan hoặc hành vi chỉ mục, vài hàng fixture thường không đủ. Optimizer có thể chọn sequential scan cho bảng nhỏ dù production dùng index seek. Đó không nhất thiết là lỗi; với vài hàng, scan có thể rẻ hơn.

Muốn kiểm tra giả thuyết hiệu năng, hãy tạo dataset thử nghiệm đủ lớn và có phân bố tương tự:
- Số lượng hàng theo tenant hoặc trạng thái.
- Giá trị phổ biến và hiếm (skew).
- Khoảng thời gian dữ liệu nóng và lạnh.
- Tỷ lệ NULL.
- Độ rộng hàng và kích thước payload.
- Tỷ lệ khớp giữa các bảng khi JOIN.
- Mức độ trùng lặp của cột lọc và cột nối.

Có thể dùng fixture nhỏ cho test logic và dataset lớn hơn cho nhóm test plan/performance. Hai nhóm có mục đích khác nhau và không nên làm toàn bộ test suite chậm chỉ để duy trì một dataset lớn.

### Dữ liệu kiểm thử phải xác định và lặp lại được

Dùng khóa cố định hoặc sinh dữ liệu theo seed xác định. Tránh phụ thuộc vào thứ tự tự nhiên của bảng. Nếu test kiểm tra kết quả theo thứ tự, câu SQL phải có ORDER BY đầy đủ.

Đối với thời gian, đặt timezone rõ ràng và dùng mốc cố định thay vì NOW() hoặc CURRENT_TIMESTAMP không kiểm soát. Nếu phải kiểm tra hành vi theo thời gian hiện tại, dùng Clock hoặc truyền thời điểm làm tham số để test có thể lặp lại.

## Kiểm tra hành vi JDBC trên engine thật

### Parameter binding và kiểu dữ liệu

JDBC driver chuyển kiểu Java sang kiểu SQL theo quy tắc của driver và database. Dùng PreparedStatement và bind đúng kiểu, tránh nối chuỗi SQL.

~~~java
String sql = """
    SELECT order_id, total_amount
    FROM orders
    WHERE tenant_id = ?
      AND created_at >= ?
      AND created_at < ?
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setLong(1, tenantId);
    statement.setTimestamp(2, Timestamp.from(fromInstant));
    statement.setTimestamp(3, Timestamp.from(toInstant));

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            long orderId = resultSet.getLong("order_id");
            BigDecimal total = resultSet.getBigDecimal("total_amount");
        }
    }
}
~~~

Test cần xác minh:
- Java type và SQL type được bind đúng.
- NULL được bind bằng setNull với SQL type phù hợp khi cần.
- BigDecimal giữ đúng precision và scale.
- Timestamp được diễn giải theo timezone đã thống nhất.
- UUID, binary, enum hoặc JSON được driver chuyển đúng theo engine.
- Tham số không gây implicit conversion không mong muốn trên cột được đánh index.

Không giả định setObject có cùng hành vi cho mọi driver và mọi kiểu dữ liệu. Nếu ứng dụng phụ thuộc kiểu cụ thể, hãy test với driver thật và schema thật.

### NULL và phân biệt NULL với giá trị mặc định

JDBC có quy tắc đặc biệt khi đọc NULL từ ResultSet. Ví dụ getLong trả 0 nếu cột SQL là NULL; phải gọi wasNull() để phân biệt.

~~~java
long customerId = resultSet.getLong("customer_id");
if (resultSet.wasNull()) {
    // Cột customer_id thực sự là SQL NULL
}
~~~

Với kiểu nullable, có thể dùng getObject với lớp Java phù hợp nếu driver hỗ trợ và mapping rõ ràng. Integration test cần có hàng NULL để phát hiện code vô tình biến NULL thành 0, false hoặc chuỗi rỗng.

### Generated keys, identity và sequence

Cách lấy khóa được sinh có thể khác theo engine và driver. JDBC hỗ trợ yêu cầu generated keys:

~~~java
String sql = """
    INSERT INTO orders (tenant_id, status, total_amount)
    VALUES (?, ?, ?)
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
         sql, Statement.RETURN_GENERATED_KEYS)) {

    statement.setLong(1, tenantId);
    statement.setString(2, "NEW");
    statement.setBigDecimal(3, new BigDecimal("125.50"));

    int affected = statement.executeUpdate();
    if (affected != 1) {
        throw new SQLException("Unexpected affected row count: " + affected);
    }

    try (ResultSet keys = statement.getGeneratedKeys()) {
        if (!keys.next()) {
            throw new SQLException("Database did not return a generated key");
        }
        long orderId = keys.getLong(1);
    }
}
~~~

Test phải chạy trên engine thật vì identity, sequence, trigger và generated key behavior có thể khác nhau. Kiểm tra cả trường hợp insert một hàng, batch insert và lỗi constraint. Với batch, driver có thể trả update counts hoặc generated keys theo cách riêng; đừng giả định mọi driver đều trả cùng cấu trúc.

### Batch update

JDBC batch có thể giảm round-trip và overhead khi ghi nhiều hàng:

~~~java
String sql = """
    INSERT INTO order_items (order_id, product_id, quantity)
    VALUES (?, ?, ?)
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    connection.setAutoCommit(false);

    for (OrderItem item : items) {
        statement.setLong(1, item.orderId());
        statement.setLong(2, item.productId());
        statement.setInt(3, item.quantity());
        statement.addBatch();
    }

    try {
        int[] counts = statement.executeBatch();
        connection.commit();
    } catch (SQLException exception) {
        connection.rollback();
        throw exception;
    }
}
~~~

Test cần xác minh:
- Batch được thực thi với số hàng dự kiến.
- Update counts được hiểu đúng, kể cả SUCCESS_NO_INFO hoặc EXECUTE_FAILED nếu driver trả các mã đó.
- Một lỗi giữa batch có thể ảnh hưởng transaction ra sao.
- Rollback có hoàn tác toàn bộ thay đổi theo ranh giới transaction không.
- Kích thước batch không vượt giới hạn packet, parameter hoặc bộ nhớ.
- Driver có rewrite batch thành multi-row insert hay gửi từng statement riêng không nếu hiệu năng phụ thuộc hành vi đó.

Không kiểm tra batch chỉ bằng cách xác nhận không có exception. Hãy truy vấn lại dữ liệu để xác nhận số hàng và giá trị được lưu đúng.

## Kiểm tra transaction và isolation

### Auto-commit và commit/rollback

JDBC Connection thường mặc định auto-commit bật, nghĩa là mỗi statement được commit riêng khi hoàn tất. Ứng dụng cần transaction nhiều statement phải tắt auto-commit và commit hoặc rollback rõ ràng.

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        debit(connection, fromAccount, amount);
        credit(connection, toAccount, amount);
        connection.commit();
    } catch (Exception exception) {
        connection.rollback();
        throw exception;
    }
}
~~~

Integration test nên xác minh:
- Hai thao tác cùng transaction được commit cùng nhau.
- Nếu thao tác thứ hai thất bại, rollback không để lại thay đổi đầu tiên.
- Connection được trả về pool với transaction đã kết thúc.
- Trạng thái auto-commit và isolation không rò rỉ sang borrower tiếp theo.
- Exception path không bỏ qua rollback hoặc close.

Pool thường reset một số trạng thái connection khi trả về, nhưng không nên phụ thuộc mù quáng vào hành vi đó. Test với pool thật của ứng dụng nếu trạng thái session hoặc transaction có thể bị rò rỉ giữa các request.

### Isolation level và hành vi đọc/ghi

JDBC cung cấp các mức isolation tiêu chuẩn qua setTransactionIsolation, nhưng database engine có thể triển khai và hỗ trợ khác nhau. Ví dụ, READ COMMITTED, REPEATABLE READ và SERIALIZABLE không nhất thiết có cùng semantics giữa PostgreSQL, MySQL/InnoDB và SQL Server.

Các hiện tượng cần kiểm thử:
- Dirty read nếu engine/isolation cho phép.
- Non-repeatable read.
- Phantom row.
- Lost update.
- Write skew.
- Deadlock và lock timeout.
- Snapshot visibility và transaction timestamp.

Không viết test chỉ kiểm tra giá trị trả về của getTransactionIsolation rồi kết luận engine thực thi đúng isolation. Cần tạo hai transaction đồng thời và kiểm tra kết quả theo hành vi được tài liệu của engine cam kết.

### Kiểm tra khóa bằng hai connection thật

Ví dụ khái niệm cho kiểm tra blocking:
1. Connection A bắt đầu transaction và cập nhật một hàng.
2. Connection A chưa commit.
3. Connection B cố cập nhật cùng hàng.
4. Test xác nhận B phải chờ hoặc nhận lỗi timeout theo cấu hình.
5. Connection A commit hoặc rollback.
6. Test xác nhận B tiếp tục hoặc thất bại đúng như mong đợi.

Dùng CountDownLatch, barrier hoặc cơ chế đồng bộ xác định trong Java để điều phối thời điểm hai transaction. Không dùng Thread.sleep để giả định transaction A đã giữ khóa; sleep dễ tạo test chập chờn theo tốc độ máy.

Mỗi test concurrency phải có timeout và cleanup trong finally. Nếu một assertion thất bại, phải rollback và đóng cả hai connection để không để khóa còn tồn tại làm hỏng các test sau.

### Deadlock và retry

Deadlock phụ thuộc thứ tự khóa, concurrency và lịch thực thi. Có thể tạo một test có kiểm soát với hai transaction cập nhật hai hàng theo thứ tự ngược nhau, nhưng test cần đồng bộ chính xác và chỉ nên chạy trên engine mục tiêu.

Nếu ứng dụng có retry cho deadlock hoặc serialization failure, hãy kiểm tra:
- Chỉ retry lỗi được phân loại là transient.
- Transaction được rollback trước khi retry.
- Toàn bộ thao tác được thực hiện lại trong transaction mới.
- Retry có giới hạn, backoff và jitter.
- Logic có idempotent hoặc có cơ chế chống xử lý trùng.
- Không retry lỗi constraint hoặc lỗi dữ liệu vĩnh viễn.

Mã lỗi và SQLState có thể khác nhau theo engine/driver. Dùng SQLState hoặc mã vendor theo tài liệu driver, không so sánh chuỗi message lỗi.

## Xác minh execution plan trên database thật

### Vì sao test plan trên database thay thế có thể sai?

Optimizer dựa vào schema, index, thống kê, dữ liệu, phiên bản engine, cấu hình và tham số để chọn kế hoạch. H2 hoặc database giả lập không tái hiện đầy đủ optimizer và access path của engine production. Vì vậy, test có thể pass về kết quả nhưng không phát hiện:
- Chỉ mục không được sử dụng.
- Implicit conversion làm giảm khả năng seek.
- Cardinality estimate sai do dữ liệu skew.
- Join order hoặc join algorithm khác.
- Sort/hash spill hoặc memory grant không phù hợp.
- Partition pruning không xảy ra.
- Query plan thay đổi sau nâng phiên bản.

Integration test với engine thật là điều kiện cần để xác minh, nhưng dữ liệu quá nhỏ vẫn có thể khiến optimizer chọn plan khác production.

### Dùng EXPLAIN và actual execution plan

Cách kiểm tra phụ thuộc hệ quản trị:

- PostgreSQL: EXPLAIN cho kế hoạch ước lượng; EXPLAIN ANALYZE thực thi câu lệnh và báo số liệu thực tế. BUFFERS giúp xem hoạt động buffer.
- MySQL: EXPLAIN và EXPLAIN ANALYZE ở các phiên bản hỗ trợ cung cấp thông tin về kế hoạch và thời gian thực tế.
- SQL Server: Actual Execution Plan, Query Store, STATISTICS IO/TIME và các công cụ theo dõi phù hợp có thể cung cấp estimated/actual rows, reads và elapsed/CPU.

Cần đặc biệt cẩn thận với EXPLAIN ANALYZE trên INSERT, UPDATE hoặc DELETE vì lệnh được thực thi thật. Một transaction rollback sau đó có thể hoàn tác thay đổi transactional, nhưng không phải mọi tác động phụ đều nhất thiết được đảo ngược, chẳng hạn sequence advancement, external side effect của extension hoặc gọi hệ thống bên ngoài. Chỉ chạy trên dữ liệu test cô lập và hiểu rõ side effect.

Ví dụ PostgreSQL cho SELECT:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = 42
  AND status = 'READY'
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
~~~

Khi đọc plan, tập trung vào:
- Access path: Seq Scan, Index Scan, Index Only Scan, Bitmap Scan hoặc toán tử tương đương.
- Estimated Rows và Actual Rows.
- Rows Removed by Filter.
- Số loop và số hàng mỗi loop.
- Sort method, memory và disk spill.
- Shared/local/temp buffers hoặc logical reads tùy engine.
- Join algorithm và cardinality ở mỗi bước.
- Partition pruning và partition được truy cập.
- Wait events hoặc thời gian I/O nếu công cụ cung cấp.

Không kết luận truy vấn tốt chỉ vì plan có Index Scan. Một index scan có thể đọc rất nhiều hàng hoặc thực hiện lookup lặp lại. Sequential scan cũng có thể tối ưu nếu truy vấn cần phần lớn bảng.

### Test plan nên kiểm tra điều gì?

Tránh assertion cứng vào toàn bộ chuỗi plan hoặc tên toán tử cụ thể nếu engine có thể thay đổi plan theo phiên bản và thống kê. Một test bền vững hơn có thể xác minh:
- Query trả đúng tập kết quả.
- Index bắt buộc tồn tại sau migration.
- Partition pruning xảy ra trong trường hợp yêu cầu.
- Rows read hoặc logical reads nằm trong giới hạn tương đối trên dataset cố định.
- Không có sort spill hoặc full scan ngoài dự kiến trong test chuyên biệt.
- Estimated/actual rows không lệch vượt ngưỡng đã xác định cho fixture.
- Plan sử dụng access path được chấp nhận trong một môi trường đã cố định.

Nếu cần assertion vào plan text hoặc JSON, hãy viết parser cho định dạng plan của đúng engine/version và chỉ kiểm tra thuộc tính ổn định cần thiết. Đừng so sánh nguyên văn toàn bộ plan; một thay đổi nhỏ về cost hoặc tên node có thể làm test fail dù hiệu năng không suy giảm.

### Thống kê phải đủ để optimizer chọn plan có ý nghĩa

Sau khi nạp fixture lớn, cần cập nhật thống kê theo cơ chế của engine nếu cần. Ví dụ PostgreSQL dùng ANALYZE; MySQL và SQL Server có cơ chế thống kê riêng. Test plan chạy trên bảng chỉ có vài hàng có thể không phản ánh index usage trong production.

Đối với dữ liệu skew, tạo phân bố có giá trị phổ biến và hiếm. Kiểm tra nhiều nhóm tham số vì một kế hoạch duy nhất có thể tốt cho tenant nhỏ nhưng kém cho tenant lớn. Nếu production có parameter sniffing hoặc parameter sensitivity, integration/performance test nên bao phủ các nhóm cardinality khác nhau.

## Kiểm tra connection pool và driver

### Dùng đúng driver và pool

Nếu production dùng HikariCP và PostgreSQL JDBC driver, test tích hợp quan trọng nên dùng cùng các thành phần hoặc phiên bản tương thích. Một test dùng DriverManager trực tiếp không thể phát hiện lỗi cấu hình pool, connection leak hoặc reset session state.

Các hành vi cần xác minh:
- Connection được trả lại pool sau success và exception.
- Transaction được rollback khi lỗi.
- Auto-commit và isolation không rò rỉ sang borrower khác.
- Statement/ResultSet được đóng.
- Connection bị mất giữa chừng được xử lý phù hợp.
- Validation và lifetime không tạo connection storm.
- Pool max, acquisition timeout và database session limit tương thích.

Không cố tình làm hỏng production connection để kiểm tra. Dùng container hoặc môi trường thử nghiệm riêng và mô phỏng network/database restart theo cách có kiểm soát nếu cần.

### Prepared statement và statement cache

Driver có thể hỗ trợ server-side prepared statements, client-side emulation hoặc statement cache. Hành vi này ảnh hưởng parse/plan reuse và đôi khi tương tác với parameter-sensitive plan.

Test nên kiểm tra query với nhiều giá trị tham số có độ chọn lọc khác nhau. Không giả định prepared statement luôn tạo cùng một plan tốt cho mọi tham số. Khi có dấu hiệu plan regression, đối chiếu driver settings, server prepare threshold, query stats và plan cache của engine.

### Fetch size và streaming

Với kết quả lớn, JDBC fetch size có thể ảnh hưởng số round-trip, bộ nhớ client và thời gian giữ connection. Cách triển khai khác nhau theo driver và engine. Một số driver cần transaction hoặc cursor mode cụ thể để streaming thực sự hoạt động.

Integration test có thể:
- Truy vấn số hàng đủ lớn để vượt một batch fetch.
- Đo số hàng và byte được đọc.
- Xác minh ứng dụng không tải toàn bộ dữ liệu vào bộ nhớ nếu yêu cầu streaming.
- Kiểm tra connection được giữ trong lúc ResultSet còn mở.
- Xác minh ResultSet và Statement đóng sau khi tiêu thụ hoặc hủy sớm.

Đừng chỉ gọi setFetchSize rồi cho rằng driver chắc chắn stream. Đọc tài liệu driver và quan sát hành vi thực tế.

## Cô lập dữ liệu và thứ tự test

### Mỗi test phải tự chuẩn bị dữ liệu

Test không được phụ thuộc vào test khác đã chạy trước. Các lựa chọn phổ biến:
- Tạo schema riêng cho từng test hoặc từng test class.
- Dùng tenant/test key duy nhất.
- Xóa dữ liệu fixture theo thứ tự phụ thuộc khóa ngoại.
- Tạo database/container mới cho suite khi chi phí cho phép.
- Dùng transaction rollback cho test đơn giản nếu tất cả thay đổi nằm trong cùng transaction và không cần quan sát từ connection khác.

Transaction rollback không phù hợp cho mọi test. Test concurrency cần nhiều connection độc lập; mỗi connection có transaction riêng. DDL, sequence và một số thao tác database có thể không rollback như DML thông thường. Hãy hiểu semantics của engine.

### Chạy song song có kiểm soát

Test suite chạy song song có thể làm kết quả không ổn định nếu:
- Nhiều test dùng chung bảng hoặc khóa.
- Một test thay đổi thống kê trong khi test khác đọc plan.
- Test cạnh tranh CPU/I/O trong cùng container.
- Test thay đổi global setting hoặc timezone của database.
- Container hoặc schema dùng chung bị xóa khi test khác còn chạy.

Nếu test plan hoặc latency nhạy với tài nguyên, chạy trong nhóm riêng, giới hạn concurrency và dùng môi trường ổn định. Integration test logic có thể chạy song song nếu dữ liệu được cô lập đúng.

### Cleanup và tính lặp lại

Dùng try-with-resources, transaction rollback, schema cleanup hoặc container lifecycle. Cleanup phải chạy cả khi assertion thất bại. Không để connection đang mở hoặc transaction chưa kết thúc vì nó có thể giữ lock và làm các test tiếp theo treo.

## Quy trình xây dựng integration test cho hiệu năng database

1. **Xác định hành vi cần kiểm chứng:** JDBC type binding, transaction, constraint, locking, access path, partition pruning hay plan regression.
2. **Chọn engine/version/driver:** khớp môi trường mục tiêu ở các yếu tố liên quan.
3. **Khởi chạy database cô lập:** dùng container hoặc instance test riêng, cố định image/version.
4. **Áp dụng migration thật:** tạo đúng schema, index, constraint, extension và partition.
5. **Nạp fixture đại diện:** gồm giá trị biên, NULL, duplicate hợp lệ, skew và cardinality cần thiết.
6. **Chạy qua đường truy cập thật của ứng dụng:** repository, JDBC template, ORM, driver và pool nếu chúng thuộc phạm vi cần test.
7. **Assertion tính đúng đắn:** kết quả, update count, generated key, rollback, isolation và lỗi constraint.
8. **Đo telemetry:** query fingerprint, execution plan, reads, CPU, wait, rows, fetch và pool metrics.
9. **Kiểm tra plan trên dữ liệu đủ lớn:** cập nhật thống kê và thử nhiều nhóm tham số.
10. **Chạy concurrency test có đồng bộ:** xác minh blocking, deadlock, timeout và retry.
11. **Dọn dữ liệu và tài nguyên:** đóng ResultSet/Statement/Connection, kết thúc transaction và dừng container.
12. **Chạy lại sau thay đổi:** so sánh cùng engine, dữ liệu, driver, cấu hình và workload.

Tách test thành nhóm:
- Repository correctness tests chạy thường xuyên.
- Transaction/concurrency tests chạy theo pipeline phù hợp vì có thể tốn thời gian.
- Plan/performance regression tests chạy trên dataset và môi trường được kiểm soát.
- Load tests riêng để đánh giá throughput, latency và tài nguyên dưới tải lớn.

## Ví dụ tổng hợp: kiểm chứng truy vấn danh sách đơn hàng

Giả sử API lấy 50 đơn mới nhất của một tenant theo trạng thái. Truy vấn:

~~~sql
SELECT order_id, status, created_at, total_amount
FROM orders
WHERE tenant_id = ?
  AND status = ?
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
~~~

Bài test cần xác minh:
1. Kết quả chỉ thuộc tenant được yêu cầu.
2. Status được lọc đúng.
3. Thứ tự ổn định khi nhiều đơn có cùng created_at.
4. Không trả hàng trùng hoặc thiếu do JOIN không cần thiết.
5. JDBC bind tenant_id và status đúng kiểu.
6. Migration tạo index ghép dự kiến.
7. Với dataset đủ lớn và thống kê phù hợp, plan không đọc lượng hàng vượt ngưỡng thiết kế.
8. Query vẫn trả đúng kết quả với các tenant có kích thước dữ liệu khác nhau.

Một index ứng viên có thể là (tenant_id, status, created_at DESC, order_id DESC), nhưng không nên assertion rằng optimizer luôn phải chọn index scan ở mọi dataset. Nếu bảng chỉ có vài hàng, sequential scan có thể hợp lý. Test plan phải dùng fixture đủ lớn và môi trường cố định để kiểm tra giả thuyết có ý nghĩa.

Có thể tách:
- Test logic với fixture nhỏ để xác minh kết quả và thứ tự.
- Test plan với fixture lớn, thống kê được cập nhật và tham số đại diện.
- Test concurrency để xác minh nhiều request lấy trang không gây lỗi transaction hoặc pool.
- Benchmark riêng để đo p95/p99 và throughput.

Ví dụ chỉ mục và số liệu cần được xác minh trên database thật; không lấy một con số minh họa làm ngưỡng production.

## Những sai lầm thường gặp

- **Dùng H2 thay cho engine production trong mọi integration test:** khác biệt dialect, type, isolation, locking và optimizer có thể che giấu lỗi.
- **Dùng image latest:** kết quả thay đổi theo phiên bản mà không có thay đổi chủ đích.
- **Tự tạo schema rút gọn:** bỏ sót index, constraint, trigger, partition hoặc migration lỗi.
- **Dataset quá nhỏ để kiểm tra plan:** optimizer chọn scan vì bảng nhỏ và test không đại diện.
- **Assert nguyên văn execution plan:** test dễ vỡ khi cost hoặc node thay đổi nhưng hành vi vẫn tốt.
- **Chỉ kiểm tra không có exception:** bỏ qua update count, generated key, NULL, rollback và dữ liệu thực tế.
- **Giả định JDBC type binding giống nhau:** driver có thể chuyển kiểu khác nhau và tạo implicit conversion.
- **Dùng Thread.sleep cho concurrency test:** thứ tự chạy không xác định và test dễ chập chờn.
- **Không rollback hoặc cleanup khi test thất bại:** để lại lock, transaction và dữ liệu gây ảnh hưởng test sau.
- **Dùng một transaction chung cho test nhiều connection:** không kiểm tra được hành vi đồng thời thật.
- **Dùng EXPLAIN ANALYZE trên DML mà không xét side effect:** câu lệnh được thực thi thật.
- **Dùng integration test thay benchmark:** một lần chạy không đại diện p95/p99 và throughput dưới tải.
- **So sánh plan trên môi trường khác nhau:** CPU, thống kê, cấu hình và phiên bản làm kết quả không tương đương.

## Checklist kiểm thử tích hợp database cho ứng dụng Java

- [ ] Engine, phiên bản, driver và cấu hình liên quan khớp mục tiêu.
- [ ] Container/image được cố định version hoặc digest.
- [ ] Migration thật chạy thành công.
- [ ] Schema có đúng type, index, constraint, trigger và partition.
- [ ] Fixture bao phủ NULL, giá trị biên, quan hệ một-nhiều và dữ liệu skew.
- [ ] JDBC bind đúng kiểu và xử lý NULL/BigDecimal/timestamp/UUID chính xác.
- [ ] Generated keys và batch update được xác minh trên driver thật.
- [ ] Commit, rollback, auto-commit và connection cleanup được kiểm tra.
- [ ] Isolation, blocking, deadlock và retry được kiểm tra với connection độc lập.
- [ ] Execution plan được kiểm tra trên dataset đủ lớn và thống kê phù hợp.
- [ ] Test plan kiểm tra thuộc tính ổn định, không phụ thuộc toàn bộ plan text.
- [ ] EXPLAIN ANALYZE chỉ chạy trên dữ liệu test cô lập và đã xét side effect.
- [ ] Pool, fetch size, timeout và prepared statement được kiểm tra nếu thuộc phạm vi.
- [ ] Test độc lập, có timeout và cleanup kể cả khi thất bại.
- [ ] Performance/load test được tách khỏi test logic và có môi trường đo kiểm soát.

## Kết luận

Kiểm thử tích hợp trên hệ quản trị thực giúp xác minh ứng dụng Java, JDBC driver và database engine phối hợp đúng với schema, kiểu dữ liệu, transaction, isolation, constraint và optimizer của môi trường mục tiêu. Database thay thế có thể hữu ích cho test nhanh, nhưng không chứng minh hành vi hoặc kế hoạch thực thi giống engine production.

Hãy cố định engine/version/driver, chạy migration thật, tạo dữ liệu đại diện và kiểm tra qua đúng đường truy cập ứng dụng sử dụng. Khi xác minh execution plan, dùng dataset đủ lớn, thống kê phù hợp và assertion vào thuộc tính quan trọng thay vì toàn bộ plan text. Kết hợp correctness test, concurrency test và performance test riêng biệt sẽ giúp phát hiện lỗi JDBC, sai khác engine và hồi quy access path trước khi triển khai, đồng thời giữ kết quả đo có thể lặp lại và diễn giải được.
