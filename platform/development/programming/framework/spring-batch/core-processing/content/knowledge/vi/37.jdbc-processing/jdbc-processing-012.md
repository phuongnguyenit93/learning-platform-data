# Kiểm thử database reader writer

Trong Spring Batch, database reader và writer thường là nơi kết nối trực tiếp với dữ liệu nghiệp vụ, nên cần được kiểm thử ở cả cấp component và cấp Job/Step. Test reader xác nhận câu SQL, mapping, thứ tự và checkpoint; test writer xác nhận parameter binding, batch update, transaction và constraint; integration test xác nhận các thành phần phối hợp đúng dưới transaction manager và JobRepository thực tế.

Một test chỉ mock ItemReader hoặc ItemWriter không chứng minh JDBC query và câu lệnh ghi chạy đúng. Ngược lại, chỉ chạy một Job end-to-end cũng có thể khiến lỗi mapping hoặc boundary case khó định vị. Chiến lược phù hợp kết hợp unit test cho logic mapping, database integration test cho reader/writer, và Spring Batch test cho chunk, restart, skip và transaction behavior.

## 1. Mục tiêu khi kiểm thử database reader và writer

Một database reader có thể đọc đúng số dòng nhưng vẫn sai dữ liệu do mapping cột, điều kiện lọc hoặc thứ tự không ổn định. Một writer có thể trả về thành công nhưng ghi sai cột, thiếu parameter, không rollback cùng chunk hoặc không xử lý constraint theo chính sách.

Các mục tiêu thường cần xác nhận:

- Reader thực thi đúng SQL và bind đúng tham số.
- RowMapper chuyển ResultSet thành object chính xác.
- Kết quả được trả theo thứ tự xác định.
- Reader xử lý tập rỗng, null và dữ liệu biên.
- Reader lưu và khôi phục checkpoint khi restart.
- Writer bind đúng property vào câu lệnh SQL.
- Batch insert/update tác động đúng số dòng.
- Unique, foreign key và check constraint được xử lý đúng.
- Writer tham gia transaction của Step.
- Rollback không để lại dữ liệu của chunk thất bại.
- Job restart không bỏ sót hoặc ghi trùng record.
- Skip/retry listener và ExecutionContext phản ánh đúng kết quả.

Nên xác định rõ contract dữ liệu trước khi viết test: khóa nào unique, record nào được phép thiếu, thứ tự nào quan trọng và một lần restart phải tiếp tục từ đâu.

## 2. Các tầng kiểm thử

Không phải mọi test đều cần khởi chạy toàn bộ Job. Có thể chia thành ba tầng:

| Tầng | Thành phần | Mục tiêu |
|---|---|---|
| Unit test | RowMapper, parameter mapper, processor, route rule | Kiểm tra logic Java nhỏ và deterministic |
| Database integration test | JdbcCursorItemReader, JdbcPagingItemReader, JdbcBatchItemWriter | Xác nhận SQL, mapping và JDBC driver |
| Spring Batch integration test | Job, Step, JobRepository, transaction manager | Xác nhận chunk, checkpoint, restart, skip và lifecycle |

Unit test phù hợp khi logic không cần database. Ví dụ một mapper chuyển ResultSet thành Order có thể test bằng ResultSet mock, nhưng test với database thật vẫn hữu ích để phát hiện sai tên cột hoặc kiểu dữ liệu.

Database integration test chạy SQL trên database test và xác nhận dữ liệu thực tế. Spring Batch integration test đưa reader/writer vào Step để kiểm tra cách framework quản lý transaction và ExecutionContext.

## 3. Dependency kiểm thử Spring Batch

Với Spring Batch 5, dependency test thường là:

~~~xml
<dependency>
    <groupId>org.springframework.batch</groupId>
    <artifactId>spring-batch-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Dự án Spring Boot thường quản lý version thông qua dependency management/BOM tương ứng. Nếu không dùng Boot, cần căn chỉnh version spring-batch-test với spring-batch-core.

Spring Batch Test cung cấp các tiện ích như:
- @SpringBatchTest để đăng ký các thành phần hỗ trợ test Batch.
- JobLauncherTestUtils để launch Job hoặc Step.
- JobRepositoryTestUtils để dọn JobExecution metadata trong test.
- StepScopeTestExecutionListener và JobScopeTestExecutionListener cho scoped bean trong test.
- MetaDataInstanceFactory để tạo metadata test khi cần.

API cụ thể có thể khác theo phiên bản Spring Batch. Kiểm tra dependency thực tế thay vì trộn snippet của Spring Batch 4 với Spring Batch 5.

## 4. Chọn database test

Có thể dùng embedded database như H2 hoặc dùng database container gần production.

| Lựa chọn | Ưu điểm | Giới hạn |
|---|---|---|
| H2 | Khởi động nhanh, dễ reset, phù hợp test SQL đơn giản | Khác biệt cú pháp, type, isolation và driver so với production |
| HSQLDB/Derby | Nhẹ, embedded | Vẫn có khác biệt với database production |
| Testcontainers | Chạy engine và driver gần production | Tốn thời gian khởi động và cần Docker/runtime phù hợp |
| Database test dùng chung | Có thể phản ánh môi trường nội bộ | Cần cô lập schema/data và tránh test chạy song song đụng nhau |

Nếu ứng dụng production dùng PostgreSQL, MySQL, Oracle hoặc SQL Server, các test quan trọng về paging, cursor, batch update, exception translation và locking nên chạy trên đúng engine/driver hoặc môi trường tương đương.

H2 hữu ích cho test nhanh nhưng không chứng minh một câu SQL đặc thù PostgreSQL hay Oracle sẽ hoạt động giống nhau. Không dùng H2 làm bằng chứng cho holdability, vendor error code hoặc isolation semantics của database khác.

## 5. Tạo schema và dữ liệu test có thể lặp lại

Test phải kiểm soát schema và dữ liệu đầu vào. Mỗi test cần biết rõ database bắt đầu ở trạng thái nào và kết quả mong đợi là gì.

Có thể tạo schema bằng schema.sql:

~~~sql
DROP TABLE IF EXISTS orders;

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    amount DECIMAL(12, 2) NOT NULL
);
~~~

Dữ liệu test:

~~~sql
INSERT INTO orders (id, customer_id, status, amount)
VALUES
    (101, 501, 'NEW', 125.50),
    (102, 502, 'NEW', 89.00),
    (103, 503, 'DONE', 210.00);
~~~

Có thể dùng @Sql để chạy script trước test:

~~~java
@SpringBootTest
@Sql(
    scripts = "/sql/orders-test-data.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD)
class OrderReaderIntegrationTest {
}
~~~

Nếu script tạo lại schema, cần dọn dữ liệu hoặc dùng schema riêng để các test không phụ thuộc thứ tự chạy. Với database dùng chung, nên dùng tên schema/database riêng theo test suite hoặc transaction isolation được kiểm soát.

Không để test phụ thuộc dữ liệu còn sót từ lần chạy trước. Một test chạy riêng và chạy trong toàn suite phải cho cùng kết quả.

## 6. Dùng JdbcTemplate để chuẩn bị và kiểm tra dữ liệu

JdbcTemplate hữu ích để insert fixture và xác nhận kết quả sau khi reader/writer chạy:

~~~java
@Autowired
JdbcTemplate jdbcTemplate;

@BeforeEach
void setUp() {
    jdbcTemplate.update("delete from orders");
    jdbcTemplate.update("""
            insert into orders(id, customer_id, status, amount)
            values (?, ?, ?, ?)
            """,
            101L, 501L, "NEW", new BigDecimal("125.50"));
}
~~~

Assert dữ liệu:

~~~java
Integer count = jdbcTemplate.queryForObject(
        "select count(*) from orders where status = ?",
        Integer.class,
        "NEW");

assertEquals(1, count);
~~~

JdbcTemplate giúp test tập trung vào dữ liệu thực tế thay vì mock mọi JDBC call. Khi test transaction, cần biết JdbcTemplate dùng cùng DataSource với transaction manager của Step hay không.

Tránh dùng cùng một transaction của test để vô tình che giấu commit/rollback của Job. Nếu Job chạy trong transaction riêng hoặc thread riêng, dữ liệu fixture chưa commit có thể không nhìn thấy được. Cách đơn giản là setup fixture rồi commit trước khi launch Job.

## 7. Test JdbcCursorItemReader trực tiếp

JdbcCursorItemReader mở cursor và đọc tuần tự ResultSet. Có thể test reader độc lập bằng cách gọi open, read nhiều lần, kiểm tra item rồi close.

Ví dụ:

~~~java
@Test
void readsOrdersInStableOrder() throws Exception {
    JdbcCursorItemReader<Order> reader =
            new JdbcCursorItemReaderBuilder<Order>()
                    .name("ordersReader")
                    .dataSource(dataSource)
                    .sql("""
                            select id, customer_id, status, amount
                            from orders
                            where status = ?
                            order by id
                            """)
                    .preparedStatementSetter(ps ->
                            ps.setString(1, "NEW"))
                    .rowMapper((rs, rowNum) -> new Order(
                            rs.getLong("id"),
                            rs.getLong("customer_id"),
                            rs.getString("status"),
                            rs.getBigDecimal("amount")))
                    .saveState(true)
                    .build();

    ExecutionContext context = new ExecutionContext();
    reader.open(context);

    try {
        Order first = reader.read();
        Order second = reader.read();
        Order end = reader.read();

        assertEquals(101L, first.getId());
        assertEquals(102L, second.getId());
        assertNull(end);
    } finally {
        reader.close();
    }
}
~~~

Đây là test component trực tiếp, không kiểm tra transaction/chunk orchestration của Step. Nó phù hợp để phát hiện lỗi SQL, parameter binding, RowMapper và end-of-input.

Nếu reader là bean @StepScope, cần khởi tạo trong Step scope test hoặc dùng StepScopeTestUtils. Không gọi target scoped bean khi scope chưa được kích hoạt.

## 8. Kiểm tra RowMapper

RowMapper quyết định cách mỗi hàng ResultSet trở thành object. Test cần kiểm tra tất cả field quan trọng, đặc biệt kiểu dữ liệu có thể gây lỗi chuyển đổi.

Ví dụ:
- BIGINT sang long/Long.
- DECIMAL sang BigDecimal.
- TIMESTAMP sang LocalDateTime hoặc Instant.
- Nullable column sang wrapper type.
- Enum hoặc status code sang domain enum.

Có thể xác nhận trực tiếp bằng dữ liệu test:

~~~java
Order order = reader.read();

assertAll(
        () -> assertEquals(101L, order.getId()),
        () -> assertEquals(501L, order.getCustomerId()),
        () -> assertEquals("NEW", order.getStatus()),
        () -> assertEquals(
                new BigDecimal("125.50"),
                order.getAmount()));
~~~

Với nullable column, test cả trường hợp SQL NULL. Tránh dùng primitive nếu database cho phép null và null có ý nghĩa nghiệp vụ; ResultSet.getLong() trả 0 cho SQL NULL, vì vậy cần gọi wasNull() hoặc dùng cách mapping phù hợp.

Test cũng nên xác nhận alias cột nếu SQL dùng AS. Đổi alias mà không cập nhật RowMapper có thể làm lỗi runtime dù query vẫn chạy.

## 9. Test JdbcPagingItemReader

JdbcPagingItemReader đọc theo page và cần sort key ổn định để phân trang không bỏ sót hoặc lặp record.

Một test nên có:
- Nhiều record hơn page size.
- Record ở biên giữa hai page.
- Sort key có giá trị trùng nếu thiết kế cho phép.
- Bộ lọc query và parameter.
- Page cuối không đủ số item.
- Tập kết quả rỗng.

Ví dụ cấu hình khái quát:

~~~java
JdbcPagingItemReader<Order> reader =
        new JdbcPagingItemReaderBuilder<Order>()
                .name("ordersPagingReader")
                .dataSource(dataSource)
                .queryProvider(queryProvider)
                .parameterValues(Map.of("status", "NEW"))
                .pageSize(2)
                .rowMapper(orderRowMapper)
                .saveState(true)
                .build();
~~~

Query provider cần có sort key. Nếu chỉ sắp xếp theo created_at mà nhiều record có cùng timestamp, thứ tự có thể không ổn định. Dùng thêm unique key làm tie-breaker, ví dụ (created_at, id).

Test với nhiều page để phát hiện lỗi paging, query provider và sort mapping. Đừng chỉ test một page nhỏ vì nhiều lỗi paging chỉ xuất hiện ở ranh giới page.

## 10. Kiểm tra sort order và tập dữ liệu ổn định

SQL không đảm bảo thứ tự nếu không có ORDER BY. Test reader phải chỉ rõ thứ tự cần thiết và dùng assert tương ứng.

Ví dụ:
~~~sql
SELECT id, customer_id, status, amount
FROM orders
WHERE status = :status
ORDER BY id ASC
~~~

Nếu sort key không unique, thêm khóa phụ để tạo thứ tự toàn phần. Với paging reader, điều này đặc biệt quan trọng vì mỗi page được truy vấn riêng.

Nếu dữ liệu nguồn thay đổi trong lúc Job chạy, paging có thể gặp record mới, record bị xóa hoặc record đổi sort key. Khi yêu cầu xử lý một tập input cố định, cân nhắc batch ID, watermark, snapshot hoặc staging table.

Test nên mô phỏng ít nhất một số thay đổi nguồn nếu ứng dụng cho phép writer cập nhật cùng bảng mà reader đang đọc. Hành vi thực tế phụ thuộc database, isolation level và cách reader truy vấn.

## 11. Test checkpoint của reader

Reader triển khai ItemStream có thể lưu vị trí vào ExecutionContext. Test checkpoint trực tiếp giúp xác nhận reader khôi phục từ state đã lưu.

Mô hình test:

~~~text
Reader lần 1:
  open(context rỗng)
  read item 1
  read item 2
  update(context)
  close()

Reader lần 2:
  open(cùng context đã lưu)
  read item 3
  read item 4
  close()
~~~

Ví dụ khái quát:

~~~java
ExecutionContext context = new ExecutionContext();

reader.open(context);
assertEquals(101L, reader.read().getId());
assertEquals(102L, reader.read().getId());
reader.update(context);
reader.close();

reader.open(context);
assertEquals(103L, reader.read().getId());
reader.close();
~~~

Tùy reader và phiên bản, state có thể là row count, key hoặc thông tin nội bộ khác. Test không nên phụ thuộc key nội bộ nếu framework không công khai contract đó. Hãy kiểm tra hành vi đọc tiếp đúng item sau khi reopen.

Với cursor reader, restart có thể mở lại query rồi bỏ qua hoặc định vị tới checkpoint. Với paging reader, checkpoint thường liên quan page/current item. Kiểm tra bằng dữ liệu thật và sort order ổn định.

## 12. Test JdbcBatchItemWriter

JdbcBatchItemWriter thực hiện batch insert/update dựa trên SQL và item mapping. Test writer trực tiếp có thể mở writer với ExecutionContext, ghi chunk, đóng writer rồi query database để xác nhận.

Ví dụ cấu hình:

~~~java
@Bean
JdbcBatchItemWriter<Order> orderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("""
                    insert into orders(id, customer_id, status, amount)
                    values (:id, :customerId, :status, :amount)
                    """)
            .beanMapped()
            .assertUpdates(true)
            .build();
}
~~~

Test:

~~~java
@Test
void writesAllItems() throws Exception {
    JdbcBatchItemWriter<Order> writer = orderWriter(dataSource);
    ExecutionContext context = new ExecutionContext();

    writer.open(context);
    try {
        writer.write(new Chunk<>(List.of(
                new Order(201L, 601L, "NEW",
                        new BigDecimal("10.00")),
                new Order(202L, 602L, "NEW",
                        new BigDecimal("20.00")))));
    } finally {
        writer.close();
    }

    Integer count = jdbcTemplate.queryForObject(
            "select count(*) from orders where id in (201, 202)",
            Integer.class);

    assertEquals(2, count);
}
~~~

Đoạn test trực tiếp này xác nhận câu SQL và binding. Transaction commit/rollback cần được test trong Step với transaction manager, vì mở/đóng writer không tự tạo transaction chunk.

Ở Spring Batch 5, write nhận Chunk; API ở phiên bản trước có thể nhận List. Điều chỉnh test theo version thực tế.

## 13. Kiểm tra parameter binding

Một lỗi phổ biến là tên parameter trong SQL không khớp property của item hoặc field map.

Ví dụ SQL:
~~~sql
INSERT INTO orders(id, customer_id, amount)
VALUES (:id, :customerId, :amount)
~~~

Item cần cung cấp các property id, customerId và amount nếu dùng bean mapping. Nếu dùng ItemSqlParameterSourceProvider tùy chỉnh, test cần xác nhận provider tạo đúng tên và kiểu parameter.

Nên có test với:
- BigDecimal có scale.
- Timestamp/timezone.
- SQL NULL.
- String có Unicode.
- Giá trị ở biên độ dài cột.
- Boolean/enum nếu database có kiểu riêng.

Đừng chỉ xác nhận số row được insert. Hãy query lại từng cột để chắc chắn mapping không đảo hoặc làm tròn sai.

## 14. Kiểm tra update và assertUpdates

JdbcBatchItemWriter có thể thực hiện UPDATE thay vì INSERT. Ví dụ:

~~~sql
UPDATE orders
SET status = :status,
    amount = :amount
WHERE id = :id
~~~

Test nên xác nhận:
- ID tồn tại thì đúng một row được cập nhật.
- ID không tồn tại thì hành vi phù hợp với assertUpdates.
- Không có điều kiện WHERE quá rộng làm cập nhật nhiều row.
- Các field không được cập nhật vẫn giữ nguyên.
- Một chunk có nhiều item cập nhật đúng record.

assertUpdates(true) yêu cầu writer kiểm tra số dòng update theo contract của nó. Với một item update không tác động row, writer có thể ném exception. Điều này khác với duplicate key và cần được test như một trường hợp riêng.

## 15. Kiểm tra unique constraint và DuplicateKeyException

Để test duplicate, tạo một row đã tồn tại rồi ghi item có cùng key. Xác nhận exception thực tế từ writer/driver.

~~~java
@Test
void duplicatePrimaryKeyIsReported() {
    jdbcTemplate.update("""
            insert into orders(id, customer_id, status, amount)
            values (?, ?, ?, ?)
            """,
            301L, 701L, "NEW", new BigDecimal("15.00"));

    assertThrows(DataIntegrityViolationException.class, () ->
            writer.write(new Chunk<>(List.of(
                    new Order(301L, 702L, "NEW",
                            new BigDecimal("25.00"))))));
}
~~~

Exception class cụ thể phụ thuộc writer và database. Nếu Step skip DuplicateKeyException, test trên database production-like cần xác nhận đúng class đó được ném ra. Không viết test chỉ assert một superclass rồi kết luận skip classification sẽ hoạt động.

Ngoài primary key, test các unique constraint khác. Một external reference duplicate có thể có ý nghĩa khác với ID duplicate.

## 16. Test Job bằng SpringBatchTest và JobLauncherTestUtils

Để kiểm thử Job end-to-end, dùng @SpringBatchTest cùng JobLauncherTestUtils.

Ví dụ:

~~~java
@SpringBatchTest
@SpringBootTest
@Sql(
    scripts = "/sql/orders-test-data.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD)
class ImportOrdersJobTest {

    @Autowired
    JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void importsOrdersSuccessfully() throws Exception {
        JobParameters parameters =
                new JobParametersBuilder()
                        .addString("inputBatch", "test-001")
                        .toJobParameters();

        JobExecution execution =
                jobLauncherTestUtils.launchJob(parameters);

        assertEquals(
                BatchStatus.COMPLETED,
                execution.getStatus());

        Integer count = jdbcTemplate.queryForObject(
                "select count(*) from orders",
                Integer.class);

        assertEquals(3, count);
    }
}
~~~

Cấu hình test phải xác định Job nào được launch nếu ApplicationContext có nhiều Job. Có thể cấu hình JobLauncherTestUtils với Job bean cụ thể hoặc test configuration riêng tùy phiên bản.

JobParameters identifying cần khác nhau giữa các lần chạy test nếu muốn tạo JobInstance mới. Nếu dùng cùng identifying parameters cho một JobInstance đã COMPLETED, Spring Batch có thể từ chối launch lại như một instance đã hoàn thành.

## 17. Test Step riêng lẻ

Nếu lỗi nằm ở một Step, không nhất thiết phải launch toàn Job. JobLauncherTestUtils có thể launch Step cụ thể bằng tiện ích tương ứng.

Ví dụ khái quát:

~~~java
JobExecution execution =
        jobLauncherTestUtils.launchStep(
                "importOrdersStep",
                new JobParametersBuilder()
                        .addString("inputBatch", "step-test-01")
                        .toJobParameters());
~~~

Test Step giúp cô lập reader/writer và giảm thời gian chạy. Tuy nhiên, nếu Step phụ thuộc Job ExecutionContext được tạo bởi Step trước, cần chuẩn bị context phù hợp hoặc test toàn Job.

Nên assert:
- BatchStatus.
- ExitStatus.
- Read/write/filter/skip counts.
- StepExecutionContext nếu là public contract.
- Dữ liệu database sau commit.
- Các side effect được yêu cầu.

Không chỉ assert COMPLETED; Step có thể hoàn thành nhưng ghi thiếu record do processor filter hoặc skip ngoài dự kiến.

## 18. Kiểm tra transaction rollback của chunk

Một test quan trọng là xác nhận khi writer lỗi, mọi database update trong cùng chunk transaction được rollback.

Có thể dùng writer test cố ý ghi rồi ném exception:

~~~java
public class FailingDatabaseWriter
        implements ItemWriter<Order> {

    private final JdbcTemplate jdbcTemplate;

    public FailingDatabaseWriter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) {
        for (Order order : chunk) {
            jdbcTemplate.update("""
                    insert into orders(id, customer_id, status, amount)
                    values (?, ?, ?, ?)
                    """,
                    order.getId(),
                    order.getCustomerId(),
                    order.getStatus(),
                    order.getAmount());
        }

        throw new IllegalStateException("Simulated writer failure");
    }
}
~~~

Khi writer dùng cùng DataSource được transaction manager của Step quản lý, exception sẽ làm transaction chunk rollback. Sau Job thất bại, query database để xác nhận các row của chunk đó không tồn tại.

Test cần bảo đảm:
- Transaction manager và JdbcTemplate dùng cùng DataSource.
- Writer không tự mở transaction độc lập với propagation REQUIRES_NEW.
- Test không bị bao bởi transaction ngoài làm sai kết quả quan sát.
- Job đã kết thúc trước khi query kết quả.

Nếu writer ghi file hoặc gọi HTTP, side effect đó không tự rollback cùng JDBC. Test database rollback không chứng minh external resource cũng được rollback.

## 19. Không để transaction của test che giấu kết quả Job

Một lỗi thường gặp là đặt @Transactional trên test method rồi launch Job. Transaction của test có thể không phải transaction mà Job sử dụng, đặc biệt khi Job chạy ở thread khác hoặc qua transaction manager riêng.

Điều này có thể làm:
- Job không nhìn thấy fixture chưa commit của test.
- Test không nhìn thấy dữ liệu Job đã commit.
- Cleanup rollback không xóa được dữ liệu được commit bởi transaction khác.
- Kết quả khác nhau giữa synchronous và asynchronous launcher.

Cách tiếp cận an toàn:
1. Tạo fixture bằng transaction riêng và commit.
2. Launch Job.
3. Đợi Job hoàn tất.
4. Query kết quả bằng connection mới hoặc JdbcTemplate.
5. Dọn dữ liệu sau test bằng script hoặc transaction riêng.

Nếu cố ý test transaction propagation, hãy viết test riêng và mô tả rõ transaction boundary thay vì dựa vào mặc định của test framework.

## 20. Test restart của reader và writer

Restart test cần chứng minh Job tiếp tục cùng JobInstance và checkpoint được khôi phục. Một kịch bản phổ biến:
1. Launch Job với identifying parameters cố định.
2. Cho một số chunk commit.
3. Cố ý làm một chunk sau đó thất bại.
4. Xác nhận JobExecution FAILED và dữ liệu của chunk đã commit còn tồn tại.
5. Khởi chạy lại cùng JobInstance với cùng identifying parameters.
6. Xác nhận JobExecution mới thuộc JobInstance cũ.
7. Xác nhận reader tiếp tục sau checkpoint và writer không ghi trùng.

Ví dụ kiểm tra ID:

~~~java
assertEquals(
        firstExecution.getJobInstance().getInstanceId(),
        restartExecution.getJobInstance().getInstanceId());

assertNotEquals(
        firstExecution.getId(),
        restartExecution.getId());
~~~

Restart không phải launch với identifying parameters mới. Nếu thay identifying parameter, Spring Batch tạo JobInstance mới và không dùng checkpoint của instance cũ.

Cần test cả dữ liệu trong database và metadata của JobRepository. Một Job có thể báo COMPLETED nhưng kết quả vẫn sai nếu query đầu vào không có thứ tự ổn định hoặc writer tạo side effect ngoài transaction.

## 21. Test skip và retry của database writer

Nếu Step cấu hình skip duplicate key, test cần chuẩn bị:
- Một item mới.
- Một item có key đã tồn tại.
- Một item mới khác nằm sau item duplicate.

Sau khi launch, xác nhận:
- Hai item mới được ghi.
- Item duplicate không làm Step dừng nếu nằm trong skip policy.
- Write skip count tăng đúng.
- SkipListener nhận đúng item.
- Item sau duplicate vẫn được xử lý.
- Một loại integrity violation khác không bị skip nhầm.

Với retry, mô phỏng lỗi transient có thể phục hồi. Đừng dùng DuplicateKeyException làm lỗi retry vì duplicate deterministic thường không biến mất khi thử lại cùng INSERT.

Nếu writer dùng JDBC batch, driver có thể báo batch failure ở mức cả batch. Cần test thực tế cách Spring Batch xác định item gây lỗi và áp dụng skip.

## 22. Test scoped reader/writer và JobParameters

Reader/writer dùng @StepScope hoặc @JobScope thường nhận parameter qua SpEL. Test cần chạy trong scope tương ứng.

Ví dụ:

~~~java
@Bean
@StepScope
JdbcCursorItemReader<Order> orderReader(
        DataSource dataSource,
        @Value("#{jobParameters['businessDate']}")
        String businessDate) {
    // Cấu hình reader theo businessDate.
}
~~~

Có thể test qua JobLauncherTestUtils bằng cách truyền JobParameters. Đây thường là cách gần thực tế nhất vì framework kích hoạt scope trong Step.

Đối với unit test component scoped, dùng StepScopeTestExecutionListener hoặc StepScopeTestUtils để tạo StepExecution test. Đừng lấy bean target trước khi scope hoạt động.

Test các trường hợp:
- Parameter có giá trị.
- Parameter thiếu.
- Parameter format sai.
- Parameter xác định tập dữ liệu rỗng.
- Restart dùng cùng identifying parameters.
- Non-identifying parameter thay đổi nhưng không làm đổi JobInstance.

## 23. Test reader/writer dùng nhiều DataSource

Một Job có thể đọc từ database nguồn và ghi sang database đích. Test cần cấu hình đúng DataSource, transaction manager và schema cho từng bên.

Cần xác nhận:
- Reader dùng đúng DataSource nguồn.
- Writer dùng đúng DataSource đích.
- Transaction manager điều khiển đúng resource cần rollback.
- JobRepository có thể dùng DataSource riêng.
- Không nhầm transaction của nguồn với transaction của đích.
- Failure giữa đọc và ghi không để lại trạng thái không nhất quán ngoài dự kiến.

Một transaction manager JDBC đơn giản không tạo atomic transaction trên nhiều DataSource. Nếu nguồn và đích khác nhau, test phải phản ánh semantics thực tế: commit đích, checkpoint metadata và việc đọc nguồn có thể thuộc các transaction riêng.

Nếu cần distributed transaction, cấu hình và test transaction manager tương ứng. Nếu không, thiết kế retry, idempotency và reconciliation cho các trường hợp process dừng giữa hai resource.

## 24. Test database-specific behavior bằng Testcontainers

Khi production dùng database cụ thể, Testcontainers có thể chạy một instance database thật trong integration test.

Ví dụ PostgreSQL container với Spring Boot:

~~~java
@Testcontainers
@SpringBootTest
class PostgreSqlOrderWriterTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16");

    @DynamicPropertySource
    static void databaseProperties(
            DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username",
                postgres::getUsername);
        registry.add("spring.datasource.password",
                postgres::getPassword);
    }
}
~~~

Version image nên được pin theo môi trường dự án, không dùng latest trong CI nếu cần kết quả có thể lặp lại.

Testcontainers hữu ích để kiểm tra:
- SQL dialect.
- SQLState và exception translation.
- Batch insert/update.
- Decimal/date/time mapping.
- Paging query provider.
- Isolation và locking.
- Constraint behavior.
- Cursor/fetch behavior của driver.

Container test vẫn không thay thế production validation. Database version, extension, collation, timezone và cấu hình connection có thể khác môi trường thật.

## 25. Kiểm thử hiệu năng reader và writer

Performance test nên đo theo dữ liệu gần production:
- Số item.
- Kích thước row.
- Số cột và join.
- Index.
- Chunk size.
- Fetch size/page size.
- Batch update size.
- Connection pool.
- Network latency.
- Execution plan.

Không đo thời gian một test nhỏ trên H2 rồi suy ra throughput production. Cũng không tăng chunk size tùy tiện vì transaction dài hơn có thể tăng lock duration, rollback cost và bộ nhớ.

Có thể đo:
- Items read/write mỗi giây.
- Thời gian query và fetch.
- Thời gian write batch.
- Số round trip.
- Heap usage.
- Connection wait time.
- Lock wait/deadlock.
- Thời gian commit.

Test hiệu năng nên tách khỏi unit/integration test chức năng để CI không trở nên không ổn định do tải máy.

## 26. Test resource lifecycle và connection leak

Reader cursor có thể giữ connection trong suốt Step. Test nên xác nhận resource được đóng khi Step hoàn tất hoặc thất bại.

Có thể quan sát connection pool metrics trước/sau Job, hoặc dùng datasource proxy/test double để đếm acquire/release. Với JDBC reader, kiểm tra cursor/statement được đóng qua lifecycle.

Các trường hợp:
- Job hoàn thành bình thường.
- Reader ném exception giữa lúc đọc.
- Writer thất bại.
- Step bị stop.
- Restart sau failure.
- Open resource thứ hai thất bại sau khi resource thứ nhất đã mở.

Không chỉ test happy path. Connection leak thường xuất hiện sau nhiều lần chạy hoặc ở nhánh lỗi.

## 27. Assertions nên kiểm tra dữ liệu, không chỉ trạng thái Job

Một integration test tốt kiểm tra cả metadata lẫn business data.

Ví dụ các assertion:
- BatchStatus.COMPLETED.
- ExitStatus phù hợp.
- readCount, writeCount, filterCount, skipCount.
- Số row trong bảng đích.
- Giá trị từng cột quan trọng.
- Không có duplicate business key ngoài dự kiến.
- Không có record thiếu.
- Checkpoint/JobInstance identity khi restart.
- Audit record cho skip/reject.

Nếu processor filter item, write count nhỏ hơn read count là bình thường. Test cần biết expected count theo business rule thay vì luôn khẳng định readCount bằng writeCount.

Với dữ liệu lớn, có thể xác nhận count, min/max key, checksum hoặc tập business key thay vì load toàn bộ bảng vào bộ nhớ test.

## 28. Cô lập test và chạy song song

Các test cùng dùng một database/schema có thể xung đột nếu chạy song song:
- Một test xóa bảng trong khi test khác đang đọc.
- Hai Job dùng cùng identifying parameters.
- Sequence/identity bị reset.
- JobRepository metadata còn lại từ test trước.
- File output trùng tên.

Các biện pháp:
- Schema riêng theo test suite hoặc worker.
- JobParameters unique cho mỗi lần launch mới.
- Dọn JobExecution metadata bằng JobRepositoryTestUtils khi phù hợp.
- Dùng transaction/cleanup rõ ràng.
- Tránh dùng cùng output directory cho các test song song.
- Không reset sequence khi test khác đang chạy.

Nếu test cần xác nhận restart cùng JobInstance, giữ nguyên identifying parameters trong chính test đó. Unique parameter chỉ nên được tạo giữa các test case độc lập.

## 29. Test configuration của JobRepository và transaction manager

Một Job test có thể chạy reader/writer đúng nhưng JobRepository dùng database hoặc transaction manager khác với cấu hình production. Điều này làm test không phản ánh checkpoint/commit thực tế.

Cần xác nhận:
- JobRepository được cấu hình với DataSource dự kiến.
- Step dùng transaction manager phù hợp.
- Writer JDBC dùng DataSource tham gia transaction của Step.
- Reader cursor có connection semantics được hiểu rõ.
- Schema Batch metadata đã được tạo.
- Isolation level và transaction propagation phù hợp.

Nếu test dùng @SpringBootTest, kiểm tra profile test và property override. Không vô tình dùng embedded database trong khi nghĩ rằng test đang dùng Testcontainers.

## 30. Bộ test mẫu cho database reader/writer

Một bộ test thực tế có thể được chia thành:

| Nhóm | Test tối thiểu |
|---|---|
| Reader SQL | Filter, parameter binding, mapping, empty result |
| Reader order | ORDER BY ổn định, page boundary |
| Reader state | Open/update/close, checkpoint/reopen |
| Writer SQL | Insert, update, parameter mapping |
| Writer constraint | Duplicate, foreign key, not-null |
| Transaction | Commit và rollback của chunk |
| Batch behavior | Nhiều item, partial batch failure |
| Job integration | Launch Job/Step và assert dữ liệu |
| Restart | Cùng JobInstance, ExecutionContext được khôi phục |
| Fault tolerance | Skip, retry, listener và limit |
| Resource | Connection/cursor được đóng khi success/failure |
| Database dialect | Test trên engine/driver gần production |

Bộ test này tạo lớp bảo vệ từ SQL nhỏ tới hành vi end-to-end mà không cần mock mọi thành phần.

## 31. Lỗi thường gặp khi kiểm thử database reader/writer

**Chỉ mock JdbcTemplate hoặc ItemWriter.** Test không xác nhận SQL thực tế, constraint và driver behavior.

**Chỉ dùng H2 cho mọi thứ.** Có thể bỏ sót khác biệt dialect, isolation, paging và exception translation.

**Không có ORDER BY trong query.** Test có thể pass ngẫu nhiên rồi fail khi dữ liệu hoặc execution plan thay đổi.

**Test paging với một page duy nhất.** Không phát hiện lỗi ở ranh giới page.

**Không kiểm tra field mapping.** Số row đúng nhưng dữ liệu từng cột có thể sai.

**Dùng transaction test bao quanh Job.** Fixture chưa commit hoặc kết quả đã commit có thể bị quan sát sai.

**Dùng identifying JobParameters giống nhau giữa test.** JobInstance đã COMPLETED có thể không launch lại được.

**Chỉ assert BatchStatus.** Job COMPLETED không đảm bảo business data đúng.

**Không test rollback.** Writer có thể để lại một phần dữ liệu của chunk lỗi.

**Không test restart.** Checkpoint và thứ tự input có thể làm thiếu/trùng record.

**Bỏ qua exception class thực tế của driver.** Skip DuplicateKeyException có thể không hoạt động nếu writer ném SQLException khác.

**Không dọn JobRepository metadata.** Test sau có thể bị ảnh hưởng bởi JobExecution cũ.

**Không test resource cleanup.** Cursor/connection có thể rò rỉ ở nhánh lỗi.

**Chạy test song song trên cùng schema/file.** Dữ liệu hoặc output có thể ghi đè lẫn nhau.

## 32. Quy trình kiểm thử database reader và writer

Khi kiểm thử một Step dùng database reader/writer, hãy thực hiện theo trình tự:

1. Chọn database test phù hợp; dùng engine/driver gần production cho hành vi đặc thù.
2. Tạo schema và fixture có thể lặp lại, cô lập giữa các test.
3. Test reader trực tiếp về SQL, parameter, RowMapper, sort order và tập rỗng.
4. Test paging/cursor qua nhiều page/chunk và ranh giới dữ liệu.
5. Test reader checkpoint bằng ExecutionContext và reopen.
6. Test writer trực tiếp về SQL, parameter binding, insert/update và constraint.
7. Test transaction của Step để xác nhận commit/rollback.
8. Dùng SpringBatchTest và JobLauncherTestUtils để launch Job/Step.
9. Assert BatchStatus, ExitStatus, counts và dữ liệu database thực tế.
10. Test skip/retry, DuplicateKeyException, listener và skip limit.
11. Test restart cùng JobInstance với identifying parameters ổn định.
12. Test nhiều DataSource, connection lifecycle và resource cleanup nếu ứng dụng có dùng.
13. Dùng Testcontainers cho SQL dialect, driver và concurrency behavior quan trọng.
14. Cô lập JobRepository metadata, schema, output path và fixture để test chạy độc lập.
15. Tách performance test khỏi test chức năng và đo trên dữ liệu gần production.

Kiểm thử database reader/writer cần chứng minh cả câu SQL lẫn cách chúng hoạt động trong transaction và lifecycle của Spring Batch. Unit test giúp xác nhận logic nhỏ; database integration test xác nhận JDBC và schema; Spring Batch integration test xác nhận chunk, checkpoint, skip và restart. Khi test chạy trên database phù hợp, fixture được cô lập và assertion kiểm tra dữ liệu thực tế, ứng dụng có thể phát hiện lỗi trước khi batch xử lý dữ liệu production.

