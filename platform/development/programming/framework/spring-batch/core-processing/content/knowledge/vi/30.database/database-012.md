# Restart reader database trong Spring Batch

Database reader trong Spring Batch thường đọc hàng nghìn hoặc hàng triệu bản ghi. Nếu process dừng giữa chừng, job cần tiếp tục từ điểm đã commit gần nhất thay vì đọc lại toàn bộ dữ liệu hoặc bỏ sót bản ghi. Cơ chế này được gọi là restart reader.

Spring Batch hỗ trợ restart thông qua ItemStream, ExecutionContext và JobRepository. Reader lưu checkpoint trong execution context; khi một execution được restart, reader mở lại tài nguyên và khôi phục vị trí đọc từ checkpoint đã lưu. Để cơ chế này đúng, reader phải hỗ trợ lưu state, có định danh ổn định và đọc dữ liệu theo thứ tự có thể tái lập.

Với database reader, cần phân biệt cách restart của cursor reader và paging reader. Cursor reader thường khôi phục vị trí trong kết quả truy vấn; paging reader thường khôi phục dựa trên sort key của bản ghi cuối cùng đã đọc/commit. Cả hai đều phụ thuộc vào query và dữ liệu nguồn ổn định.

## 1. Restart khác retry như thế nào?

Retry xử lý một thao tác hoặc item tạm thời thất bại trong quá trình thực thi. Restart tiếp tục một job/step execution đã dừng hoặc thất bại, thường trong một JobExecution mới thuộc cùng JobInstance.

| Khái niệm | Mục tiêu | Ví dụ |
| --- | --- | --- |
| Retry | Thử lại thao tác lỗi theo retry policy | Gọi lại processor khi dịch vụ tạm thời timeout |
| Rollback | Hoàn tác thay đổi trong transaction chưa commit | Hủy các lệnh ghi của chunk lỗi |
| Restart | Tiếp tục từ checkpoint đã commit của execution trước | Đọc tiếp order sau chunk cuối đã commit |

Giả sử chunk size là 3 và reader lấy các order có ID 1 đến 9:

~~~text
Chunk 1: 1, 2, 3 -> ghi thành công -> COMMIT
Chunk 2: 4, 5, 6 -> writer lỗi -> ROLLBACK
Job: FAILED

Restart:
Chunk tiếp theo bắt đầu lại từ checkpoint sau ID 3
Reader đọc lại: 4, 5, 6
Sau đó tiếp tục: 7, 8, 9
~~~

Các item của chunk chưa commit có thể được đọc và xử lý lại. Restart không có nghĩa Spring Batch nhớ chính xác mọi thao tác Java đã chạy trước khi process dừng; framework khôi phục state bền vững đã commit.

## 2. JobInstance và JobExecution quyết định lần chạy nào được restart

Spring Batch phân biệt JobInstance và JobExecution:

- JobInstance đại diện cho một lần chạy logic của job, được xác định bởi job name và identifying JobParameters.
- JobExecution là một lần thực thi cụ thể của JobInstance.
- Một JobInstance có thể có nhiều JobExecution nếu lần chạy trước thất bại hoặc bị dừng và được restart.

Ví dụ:

~~~text
Job: importOrders
Identifying parameter: businessDate=2026-11-15

JobInstance A
  |
  +-- JobExecution 1 -> FAILED
  |
  +-- JobExecution 2 -> COMPLETED (restart)
~~~

Khi restart, truyền lại cùng identifying parameters để Spring Batch nhận diện cùng JobInstance. Nếu thay identifying parameter, ví dụ business date hoặc batch ID, bạn đang yêu cầu một JobInstance khác và reader sẽ bắt đầu theo state của execution mới.

Không tạo một run.id identifying mới khi mục tiêu là restart execution thất bại. RunIdIncrementer thường tạo định danh mới cho một lần chạy logic mới; nó không tiếp tục checkpoint của JobInstance trước.

Một JobInstance đã hoàn tất thường không thể được chạy lại với cùng identifying parameters. Muốn xử lý một batch mới, dùng tham số nhận diện mới phù hợp với nghiệp vụ.

## 3. ExecutionContext là nơi lưu checkpoint

ExecutionContext là map key/value được Spring Batch quản lý và lưu qua JobRepository. Mỗi StepExecution có step execution context; JobExecution có job execution context.

Database reader thường lưu thông tin cần thiết để khôi phục vị trí đọc. Khi step chạy, lifecycle của ItemStream gồm:

- open(ExecutionContext): đọc checkpoint đã lưu và mở reader ở trạng thái phù hợp.
- update(ExecutionContext): ghi state hiện tại vào execution context.
- close(): giải phóng cursor, connection hoặc resource reader đang sở hữu.

Checkpoint được cập nhật trong quá trình xử lý chunk và được lưu cùng transaction metadata theo cấu hình repository/transaction manager. Khi chunk rollback, checkpoint của chunk chưa commit không được coi là mốc phục hồi mới; restart tiếp tục từ checkpoint đã commit gần nhất.

Không nên tự lưu object ResultSet, Connection hoặc cursor vào ExecutionContext. Chỉ lưu giá trị có thể serialize và khôi phục, ví dụ số thứ tự item, sort key, file offset hoặc business identifier.

## 4. Reader phải hỗ trợ ItemStream và saveState

Các reader database có sẵn của Spring Batch hỗ trợ ItemStream. Để restart, cần cho phép reader lưu state và đặt tên ổn định:

~~~java
new JdbcCursorItemReaderBuilder<OrderRow>()
    .name("ordersCursorReader")
    .dataSource(dataSource)
    .sql("select id, customer_id, total from orders order by id")
    .rowMapper(orderRowMapper)
    .saveState(true)
    .build();
~~~

Với JdbcPagingItemReader cũng cần đặt tên và bật state:

~~~java
new JdbcPagingItemReaderBuilder<OrderRow>()
    .name("ordersPagingReader")
    .dataSource(dataSource)
    .queryProvider(queryProvider)
    .pageSize(500)
    .rowMapper(orderRowMapper)
    .saveState(true)
    .build();
~~~

saveState(true) cho phép reader ghi thông tin phục hồi vào execution context. Nếu tắt saveState, reader không lưu checkpoint và không thể dựa vào cơ chế restart stateful mặc định của reader.

Tên reader phải ổn định giữa các lần chạy và duy nhất trong phạm vi step. Spring Batch dùng tên reader để tạo key trong execution context. Đổi tên reader giữa các phiên bản triển khai có thể làm execution cũ không tìm thấy key checkpoint mà code mới mong đợi.

## 5. Restart với JdbcCursorItemReader

JdbcCursorItemReader đọc dữ liệu thông qua một JDBC cursor. Reader thực hiện query, sau đó mỗi lần read() lấy hàng tiếp theo từ ResultSet và chuyển thành item bằng RowMapper.

Ví dụ:

~~~java
@Bean
@StepScope
JdbcCursorItemReader<OrderRow> ordersCursorReader(
        DataSource dataSource,
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    return new JdbcCursorItemReaderBuilder<OrderRow>()
        .name("ordersCursorReader")
        .dataSource(dataSource)
        .sql("""
            select id, customer_id, total, business_date
            from orders
            where business_date = ?
            order by id
            """)
        .preparedStatementSetter(ps ->
            ps.setDate(1, Date.valueOf(businessDate)))
        .rowMapper(new OrderRowMapper())
        .fetchSize(500)
        .saveState(true)
        .build();
}
~~~

Khi reader restart, nó thực thi lại query và định vị cursor tới vị trí tương ứng với số item đã được checkpoint. Tùy driver và cấu hình, reader có thể dùng khả năng nhảy đến vị trí tuyệt đối của ResultSet hoặc tiến tuần tự qua các hàng để tới vị trí cần tiếp tục.

Do đó, cursor restart phụ thuộc vào việc query trả lại cùng tập kết quả theo cùng thứ tự. Nếu có insert/delete trước vị trí đã lưu, vị trí hàng có thể dịch chuyển và reader có nguy cơ bỏ sót hoặc đọc trùng bản ghi.

### Điều kiện để cursor restart ổn định

- Có ORDER BY rõ ràng và thứ tự xác định.
- Thứ tự nên dựa trên khóa duy nhất, thường là primary key.
- Điều kiện WHERE và job parameters phải giữ nguyên khi restart.
- Tập dữ liệu nên ổn định trong thời gian job chạy và restart.
- RowMapper không được tự gọi ResultSet.next() hoặc thay đổi vị trí cursor.

Ví dụ, ORDER BY created_at có thể không đủ nếu nhiều order có cùng timestamp. Dùng thêm ID làm tie-breaker:

~~~sql
select id, customer_id, created_at
from orders
where business_date = ?
order by created_at, id
~~~

Nếu dữ liệu nguồn có thể thay đổi giữa hai lần chạy, cần xác định chiến lược snapshot hoặc cutoff. Chỉ có ORDER BY không bảo đảm tập kết quả không thay đổi.

## 6. driverSupportsAbsolute của cursor reader

JdbcCursorItemReader có tùy chọn driverSupportsAbsolute. Nếu JDBC driver hỗ trợ di chuyển cursor đến vị trí tuyệt đối, reader có thể dùng khả năng đó để khôi phục vị trí nhanh hơn. Nếu driver không hỗ trợ, reader phải tiến qua các hàng để tới checkpoint.

Ví dụ cấu hình khi driver thực sự hỗ trợ:

~~~java
new JdbcCursorItemReaderBuilder<OrderRow>()
    .name("ordersCursorReader")
    .dataSource(dataSource)
    .sql("select id, total from orders order by id")
    .rowMapper(orderRowMapper)
    .driverSupportsAbsolute(true)
    .saveState(true)
    .build();
~~~

Chỉ bật tùy chọn này sau khi xác nhận driver và ResultSet mode đang dùng hỗ trợ absolute positioning. Không bật chỉ để tăng tốc theo phỏng đoán; nếu driver không hỗ trợ, restart có thể lỗi hoặc không hoạt động đúng.

Với dữ liệu rất lớn, việc phải đọc bỏ qua nhiều hàng để tới checkpoint có thể tốn thời gian. Nếu restart thường xuyên ở vị trí sâu trong tập dữ liệu, paging reader dựa trên sort key có thể phù hợp hơn cursor reader.

## 7. Restart với JdbcPagingItemReader

JdbcPagingItemReader lấy dữ liệu theo từng trang. Reader dùng PagingQueryProvider để tạo query phù hợp với database và sort key đã cấu hình. Khi restart, reader lưu giá trị sort key của vị trí đã xử lý và tiếp tục truy vấn các hàng nằm sau key đó.

Ví dụ cấu hình tổng quát:

~~~java
@Bean
@StepScope
JdbcPagingItemReader<OrderRow> ordersPagingReader(
        DataSource dataSource,
        PagingQueryProvider queryProvider,
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    return new JdbcPagingItemReaderBuilder<OrderRow>()
        .name("ordersPagingReader")
        .dataSource(dataSource)
        .queryProvider(queryProvider)
        .parameterValues(Map.of(
            "businessDate", Date.valueOf(businessDate)
        ))
        .pageSize(500)
        .rowMapper(new OrderRowMapper())
        .saveState(true)
        .build();
}
~~~

Query provider cần có sort key. Ví dụ SQL minh họa:

~~~sql
select id, customer_id, total
from orders
where business_date = :businessDate
order by id
~~~

Khi checkpoint được lưu sau một chunk, paging reader có thể bắt đầu lại sau giá trị sort key đã commit. Cách này tránh phải đọc và bỏ qua tất cả các hàng trước checkpoint như cách khôi phục theo vị trí cursor.

### Sort key phải duy nhất và ổn định

Nếu sort key không duy nhất, nhiều hàng có thể có cùng giá trị tại ranh giới trang. Khi restart, điều kiện “sau sort key cuối” có thể bỏ qua hàng cùng key hoặc làm kết quả không xác định tùy query provider.

Nếu created_at không duy nhất, có thể dùng composite sort key:

~~~text
sort key = (created_at, id)
~~~

Sort key cần:

- Xác định thứ tự tổng thể của các hàng.
- Không thay đổi trong khi job đang chạy.
- Có giá trị so sánh nhất quán trong database.
- Được hỗ trợ bởi PagingQueryProvider.
- Phù hợp với query và index để tránh full scan khi restart.

Không dùng một trường mutable như status làm sort key nếu writer hoặc tiến trình khác có thể cập nhật trường đó trong lúc job chạy.

## 8. Phân biệt pageSize và chunk size

pageSize của paging reader và commit interval của step là hai thông số riêng:

| Thông số | Ý nghĩa | Tác động |
| --- | --- | --- |
| pageSize | Số hàng reader lấy trong một page query | Ảnh hưởng số lần query, lượng dữ liệu reader giữ và paging |
| chunk(size) | Số item được xử lý trong một transaction chunk | Ảnh hưởng commit frequency, rollback scope và checkpoint frequency |

Ví dụ:

~~~java
.chunk(100, transactionManager)
// reader:
.pageSize(500)
~~~

Reader có thể lấy một page 500 hàng trong khi step commit theo chunk 100 item. Khi restart, checkpoint phản ánh ranh giới đã được commit theo step, không phải chỉ vì một page đã được tải.

Page size bằng chunk size có thể dễ hình dung nhưng không phải yêu cầu bắt buộc. Chọn dựa trên database, network round trips, memory và tần suất commit.

## 9. Tập dữ liệu thay đổi giữa lần chạy và restart

Restart chỉ đáng tin cậy khi reader có thể diễn giải checkpoint trên tập dữ liệu tương thích. Nếu query trả một tập khác sau khi process dừng, checkpoint cũ có thể không còn chỉ đến đúng phần dữ liệu chưa xử lý.

Ví dụ cursor reader lưu vị trí hàng 100:

~~~text
Lần đầu: 1, 2, 3, ... 100 [checkpoint], 101, 102, ...
Sau khi dừng: một hàng trước vị trí 100 bị xóa
Query mới: vị trí 100 giờ tương ứng với hàng cũ 101
Restart theo row position có thể bỏ qua hàng cần xử lý
~~~

Paging reader dùng sort key tránh một số vấn đề dịch chuyển offset, nhưng vẫn có rủi ro nếu:

- Hàng đã xử lý bị cập nhật sort key và chuyển sang sau checkpoint.
- Hàng mới được insert với sort key nhỏ hơn checkpoint.
- Điều kiện lọc thay đổi giữa hai lần chạy.
- Một hàng bị xóa hoặc thay đổi trạng thái khiến nó rời khỏi tập kết quả.
- Sort key không duy nhất hoặc không bất biến.

Các cách giảm rủi ro:

1. Dùng batch ID hoặc business date để cố định tập dữ liệu đầu vào.
2. Chỉ đọc các hàng đã được đánh dấu sẵn sàng và không thay đổi membership trong suốt execution.
3. Dùng cutoff timestamp hoặc high-water mark được chụp ở đầu job.
4. Dùng snapshot/isolation phù hợp nếu database và thời lượng job cho phép.
5. Thiết kế nguồn staging bất biến cho batch lớn hoặc cần restart dài hạn.

Không giả định saveState(true) tự tạo database snapshot. Nó lưu checkpoint reader; tính nhất quán của dữ liệu nguồn vẫn phụ thuộc transaction isolation, query và quy trình nghiệp vụ.

## 10. Dùng high-water mark để cố định phạm vi đọc

Một cách phổ biến là xác định giới hạn trên của dữ liệu tại thời điểm bắt đầu job. Ví dụ lấy ID lớn nhất hiện có làm high-water mark:

~~~text
Job bắt đầu:
  minId = checkpoint ban đầu
  maxId = 900000  <- chụp một lần và giữ trong JobParameters/context

Reader:
  where id > lastCommittedId
    and id <= maxId
  order by id
~~~

Các hàng được thêm sau khi job bắt đầu có ID lớn hơn maxId nên không làm thay đổi phạm vi của lần chạy hiện tại. Giá trị maxId phải được lưu bền vững cùng job execution để restart dùng lại đúng giới hạn.

Nếu ID không tăng đơn điệu hoặc dữ liệu có thể được cập nhật/xóa, high-water mark đơn lẻ chưa đủ. Cần kết hợp batch membership, version hoặc snapshot phù hợp.

Không tính lại maxId mới mỗi khi restart nếu mục tiêu là tiếp tục cùng một JobInstance. Làm vậy có thể mở rộng tập dữ liệu giữa chừng và khiến kết quả khác với lần chạy ban đầu.

## 11. Reader state và chunk transaction

Trong chunk-oriented step, reader đọc item, processor xử lý và writer ghi theo transaction. Reader cập nhật execution context tại ranh giới chunk thông qua ItemStream.update(). Spring Batch lưu context theo lifecycle của step và JobRepository.

Ví dụ:

~~~text
BEGIN CHUNK 1
  Read 1, 2, 3
  Process 1, 2, 3
  Write 1, 2, 3
  Update reader checkpoint
COMMIT CHUNK 1

BEGIN CHUNK 2
  Read 4, 5, 6
  Process 4, 5, 6
  Write -> exception
  ROLLBACK CHUNK 2
~~~

Checkpoint được commit gần nhất vẫn là sau item 3. Khi restart, reader tiếp tục từ đó. Item 4, 5, 6 có thể được đọc lại vì chúng thuộc chunk chưa commit.

Điều này giả định JobRepository và business data được quản lý với transaction semantics phù hợp. Trong cấu hình nhiều datasource hoặc transaction manager khác nhau, metadata checkpoint và dữ liệu nghiệp vụ có thể không cùng một transaction. Cần thiết kế và kiểm thử failure window giữa commit business data và commit metadata để tránh trùng hoặc mất dữ liệu.

## 12. Đăng ký delegate ItemStream khi reader được bọc

Nếu reader database nằm bên trong một wrapper chỉ triển khai ItemReader, Spring Batch có thể không nhận ra delegate cần lifecycle open, update, close.

Ví dụ wrapper:

~~~java
public class LoggingOrderReader implements ItemReader<OrderRow> {

    private final ItemStreamReader<OrderRow> delegate;

    public LoggingOrderReader(ItemStreamReader<OrderRow> delegate) {
        this.delegate = delegate;
    }

    @Override
    public OrderRow read() throws Exception {
        return delegate.read();
    }
}
~~~

Nếu wrapper không chuyển tiếp ItemStream, đăng ký delegate với step:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
    .<OrderRow, OrderEntity>chunk(100, transactionManager)
    .reader(loggingReader)
    .stream(databaseReader)
    .processor(processor)
    .writer(writer)
    .build();
~~~

Hoặc để wrapper triển khai ItemStreamReader và forward cả ba callback. Nếu delegate không nhận open() và update(), nó không thể khôi phục checkpoint dù saveState(true) đã được cấu hình.

## 13. @StepScope và database reader restart

Database reader thường được khai báo @StepScope khi cần late binding JobParameters hoặc step execution context:

~~~java
@Bean
@StepScope
JdbcPagingItemReader<OrderRow> reader(
        DataSource dataSource,
        @Value("#{jobParameters['businessDate']}") String businessDate) {
    // Tạo reader theo input của JobExecution.
}
~~~

Mỗi StepExecution có target reader phù hợp với execution đó. Khi restart, Spring Batch tạo target mới và truyền execution context đã lưu vào open(). State runtime trong field của reader cũ không được giữ qua process restart; checkpoint bền vững mới là nguồn để khôi phục.

Không dùng static field để lưu vị trí reader. Hai job chạy đồng thời có thể ghi đè vị trí của nhau. Cũng không dùng một singleton reader mutable cho nhiều step execution nếu reader giữ cursor hoặc state riêng.

@StepScope quản lý vòng đời object, còn ExecutionContext lưu checkpoint. Hai cơ chế bổ trợ nhau nhưng không thay thế nhau.

## 14. Reader name phải ổn định giữa các lần triển khai

Tên reader được dùng làm một phần key state trong execution context. Ví dụ:

~~~java
.name("ordersPagingReader")
~~~

Nếu đổi tên thành ordersReaderV2 khi restart một JobInstance cũ, reader mới có thể không đọc được key state mà phiên bản trước đã lưu. Khi đó reader có thể khởi động từ đầu hoặc không khôi phục đúng state theo cấu hình.

Khi nâng cấp ứng dụng trong lúc job có thể restart:

- Giữ reader name nếu cấu trúc checkpoint vẫn tương thích.
- Nếu thay đổi cách lưu state, có kế hoạch migration hoặc xử lý execution cũ.
- Không tái sử dụng cùng reader name cho hai reader stateful độc lập trong một step.
- Kiểm tra restart của execution được tạo bởi phiên bản ứng dụng trước.

Đổi tên step hoặc reader, thay query, đổi sort key hay đổi kiểu dữ liệu trong context đều có thể ảnh hưởng restart compatibility. Đây là một phần của thiết kế deployment cho batch job dài hạn.

## 15. saveState(false) khi nào phù hợp?

Một số reader có thể được cấu hình saveState(false). Khi đó reader không lưu checkpoint để restart. Nếu step thất bại và được chạy lại, reader có thể bắt đầu từ đầu hoặc theo behavior được cấu hình, dẫn đến xử lý lại dữ liệu.

Chỉ dùng khi:

- Reader stateless và việc chạy lại toàn bộ dữ liệu là chấp nhận được.
- Job được thiết kế idempotent và không cần resume từ checkpoint.
- Step luôn chạy một lần trong môi trường không yêu cầu restart.
- Một cơ chế khác quản lý checkpoint và được kiểm chứng rõ.

Không tắt saveState chỉ để tránh lỗi serialization hoặc để reader đơn giản hơn nếu job cần restart. Với dữ liệu lớn, đọc lại từ đầu có thể rất tốn thời gian và gây side effect trùng nếu writer không idempotent.

## 16. Restart với query có tham số

Các query parameter ảnh hưởng tập dữ liệu cần giữ nguyên giữa lần chạy đầu và restart. Ví dụ businessDate, tenantId, status hoặc sourceBatchId.

Nếu tham số là input xác định JobInstance, truyền bằng identifying JobParameters. Nếu giá trị được tính trong quá trình job chạy, lưu trong JobExecutionContext hoặc StepExecutionContext phù hợp.

Ví dụ:

~~~java
@Bean
@StepScope
JdbcPagingItemReader<OrderRow> reader(
        DataSource dataSource,
        PagingQueryProvider queryProvider,
        @Value("#{jobParameters['businessDate']}") String businessDate,
        @Value("#{jobParameters['tenantId']}") String tenantId) {

    return new JdbcPagingItemReaderBuilder<OrderRow>()
        .name("tenantOrdersReader")
        .dataSource(dataSource)
        .queryProvider(queryProvider)
        .parameterValues(Map.of(
            "businessDate", Date.valueOf(businessDate),
            "tenantId", tenantId
        ))
        .pageSize(300)
        .rowMapper(orderRowMapper)
        .saveState(true)
        .build();
}
~~~

Khi restart, không đổi tenant hoặc business date của cùng JobInstance. Nếu cần chạy tenant khác, tạo một JobInstance khác với parameters tương ứng.

## 17. Kiểm thử restart với JdbcPagingItemReader

Integration test nên dùng database và JobRepository có state bền vững trong suốt hai lần launch. Một kịch bản đơn giản:

1. Tạo 10 order có ID 1 đến 10.
2. Cấu hình paging reader với sort key duy nhất id, page size 4 và chunk size 2.
3. Writer ghi chunk đầu thành công.
4. Writer cố ý ném exception ở chunk sau, làm step FAILED.
5. Xác nhận dữ liệu của chunk đã commit tồn tại và checkpoint đã được lưu.
6. Restart cùng JobInstance với đúng identifying parameters.
7. Xác nhận reader tiếp tục sau checkpoint, không bỏ sót hoặc ghi trùng các order hợp lệ.

Ví dụ cấu hình writer test có thể thất bại đúng một lần:

~~~java
public class FailOnceWriter implements ItemWriter<OrderRow> {

    private final OrderRepository repository;
    private final AtomicBoolean fail = new AtomicBoolean(true);

    @Override
    public void write(Chunk<? extends OrderRow> chunk) {
        if (fail.compareAndSet(true, false)) {
            throw new IllegalStateException("Simulated failure");
        }

        repository.saveAll(chunk.getItems().stream()
            .map(OrderEntity::from)
            .toList());
    }
}
~~~

Đây là minh họa về failure injection; vị trí ném lỗi cần được điều chỉnh để một chunk trước đó đã commit. Khi restart, writer tiếp tục hoạt động và reader sử dụng checkpoint đã lưu.

Các assertion quan trọng:

- Execution đầu có BatchStatus.FAILED.
- Execution restart thuộc cùng JobInstance.
- Execution mới kết thúc COMPLETED.
- Số bản ghi đích cuối cùng đúng bằng số bản ghi nguồn hợp lệ.
- Mỗi business ID chỉ xuất hiện một lần ở output nếu nghiệp vụ yêu cầu uniqueness.
- Các item của chunk rollback được xử lý lại.

## 18. Kiểm thử restart với JdbcCursorItemReader

Với cursor reader, dùng dữ liệu có thứ tự rõ ràng và cố định trong test. Cố ý làm writer lỗi sau ít nhất một chunk đã commit, rồi restart cùng JobInstance.

Nên kiểm tra:

- Query được thực thi lại khi restart.
- Reader định vị lại sau số item đã checkpoint.
- Không có insert/delete làm thay đổi vị trí hàng giữa hai lần chạy.
- RowMapper trả cùng business ID cho cùng record.
- Cursor được đóng ở execution thất bại và cursor mới được mở ở execution restart.
- Kết quả cuối không thiếu hoặc trùng item.

Nếu test bật driverSupportsAbsolute(true), phải dùng driver/database hỗ trợ cursor absolute và kiểm tra behavior thực tế. Có thể test cả chế độ mặc định để bảo đảm reader hoạt động với driver mục tiêu.

## 19. Không bọc toàn bộ test launch trong một transaction ngoài

Khi kiểm thử restart, cần để các chunk và metadata commit theo transaction thực tế của Spring Batch. Nếu test method được đánh dấu @Transactional và toàn bộ dữ liệu bị rollback khi test kết thúc, có thể làm sai cách quan sát commit của từng chunk hoặc che giấu lỗi transaction.

Một cách tổ chức rõ ràng:

1. Tạo dữ liệu fixture và commit trước khi launch job.
2. Launch job bằng JobLauncherTestUtils hoặc JobLauncher.
3. Để step quản lý transaction theo chunk.
4. Đọc JobExecution, StepExecution và bảng đích sau khi job kết thúc.
5. Restart với cùng identifying parameters.
6. Dọn fixture trong bước teardown riêng.

JobRepository phải lưu metadata đủ lâu để lần launch thứ hai đọc được execution context trước đó. Dùng repository in-memory cho test không thể chứng minh restart qua process restart thật; nó chỉ phù hợp để kiểm tra restart trong cùng test process nếu implementation lưu state tương ứng.

## 20. Kiểm tra metadata và checkpoint

Có thể dùng JobExplorer để đọc execution trước và sau restart:

~~~java
JobExecution previous = jobExplorer.getJobExecution(previousExecutionId);

assertThat(previous).isNotNull();
assertThat(previous.getStatus()).isEqualTo(BatchStatus.FAILED);

StepExecution failedStep = previous.getStepExecutions()
    .stream()
    .filter(step -> step.getStepName().equals("importOrdersStep"))
    .findFirst()
    .orElseThrow();

assertThat(failedStep.getExecutionContext())
    .containsKey("ordersPagingReader.start.after");
~~~

Key cụ thể trong execution context là chi tiết triển khai của reader và có thể thay đổi theo phiên bản. Không nên viết ứng dụng production phụ thuộc vào key nội bộ này. Trong test minh họa, ưu tiên kiểm tra reader đã khôi phục qua hành vi dữ liệu; chỉ kiểm tra key nội bộ khi test đang xác nhận một implementation/version cụ thể.

Sau restart, JobExplorer có thể truy vấn JobExecution mới và các StepExecution tương ứng. Kiểm tra chúng cùng JobInstance để xác nhận đó là restart chứ không phải một job instance mới.

## 21. Nhiều datasource và transaction manager

Một job có thể đọc từ database nguồn, ghi sang database đích và lưu metadata ở một datasource khác. Khi đó cần xác định rõ transaction manager nào quản lý từng resource.

Nếu business data đã commit nhưng metadata checkpoint chưa commit, restart có thể đọc lại item đã ghi. Nếu metadata checkpoint đã commit nhưng business write chưa commit, restart có thể bỏ qua item chưa được ghi. Với nhiều resource không có transaction phối hợp, không thể mặc định hai commit là nguyên tử.

Các chiến lược cần cân nhắc:

- Dùng cùng transaction manager/database cho business write và batch metadata nếu phù hợp kiến trúc.
- Dùng XA/JTA chỉ khi thực sự cần distributed transaction và chấp nhận độ phức tạp vận hành.
- Thiết kế writer idempotent bằng unique key/upsert để an toàn khi item được xử lý lại.
- Dùng outbox/inbox hoặc bảng staging để đối soát các trạng thái giữa nguồn, đích và batch metadata.
- Ghi nhận operation ID và trạng thái bền vững để có thể phục hồi sau failure window.

Restart reader không tự giải quyết tính nhất quán giữa hai database. Nó chỉ khôi phục vị trí đọc theo checkpoint đã lưu.

## 22. Writer cần idempotent khi item có thể được đọc lại

Ngay cả khi reader checkpoint đúng, một số failure window vẫn có thể khiến item được xử lý lại, đặc biệt khi business write và metadata không cùng transaction. Vì vậy, writer nên có chiến lược chống ghi trùng phù hợp.

Ví dụ bảng đích có unique constraint theo source order ID:

~~~sql
create unique index uk_imported_order_source
    on imported_order(source_order_id);
~~~

Writer có thể dùng upsert hoặc insert-if-absent theo database. Nếu update được phép, cần định nghĩa rõ một lần import mới có ghi đè phiên bản trước hay không.

Idempotency key nên đại diện cho một operation nghiệp vụ, chẳng hạn sourceBatchId + orderId. Không chỉ dùng order ID nếu cùng một order có thể được import hợp lệ trong nhiều batch khác nhau.

## 23. Những thay đổi có thể phá restart compatibility

Một job có thể restart sau khi ứng dụng đã được deploy phiên bản mới. Những thay đổi sau có thể ảnh hưởng checkpoint:

- Đổi reader name làm key execution context khác.
- Đổi sort key hoặc thứ tự ORDER BY.
- Đổi điều kiện WHERE hoặc ý nghĩa job parameter.
- Đổi kiểu dữ liệu của checkpoint.
- Đổi query làm tập kết quả hoặc thứ tự thay đổi.
- Thay RowMapper/domain mapping khiến item cũ không còn đọc được.
- Thay page size hoặc paging provider theo cách làm thay đổi semantics.
- Xóa hoặc sửa dữ liệu nguồn mà checkpoint dựa vào.

Không phải mọi thay đổi page size đều làm checkpoint mất hiệu lực, nhưng phải kiểm tra theo implementation và query provider đang dùng. Với execution đang dở dang, cần giữ tương thích hoặc có kế hoạch migration/abandon/reprocess rõ ràng.

Trước khi deploy phiên bản mới, xác định job nào đang FAILED/STOPPED và có thể được restart. Test restart execution được tạo từ phiên bản trước với code mới nếu hệ thống yêu cầu hỗ trợ nâng cấp giữa chừng.

## 24. Các lỗi thường gặp khi restart database reader

**Không bật saveState:** reader không lưu checkpoint và không thể tiếp tục theo state mặc định. Bật save state nếu job cần restart.

**Không đặt reader name ổn định:** key execution context có thể thay đổi hoặc xung đột. Đặt tên duy nhất và giữ ổn định.

**Restart với identifying parameters mới:** Spring Batch tạo JobInstance mới và reader không dùng checkpoint của instance cũ. Dùng lại đúng parameters khi restart.

**Cursor query không có ORDER BY:** thứ tự hàng không được bảo đảm, vị trí checkpoint có thể trỏ tới record khác. Dùng thứ tự xác định với tie-breaker duy nhất.

**Dữ liệu nguồn thay đổi trước checkpoint:** cursor position có thể dịch chuyển; paging sort key có thể bị thay đổi hoặc hàng mới nằm trước checkpoint. Cố định input hoặc dùng snapshot/cutoff.

**Paging sort key không duy nhất:** nhiều hàng cùng key có thể bị bỏ sót hoặc xử lý lặp. Dùng unique/composite sort key bất biến.

**Nhầm page size với chunk size:** page boundary không phải commit boundary. Hiểu checkpoint được lưu theo chunk transaction.

**Wrapper không đăng ký delegate ItemStream:** delegate không nhận open/update/close và không khôi phục state. Forward lifecycle hoặc đăng ký stream(delegate).

**Đổi reader/query giữa các lần chạy mà không kiểm tra:** execution context cũ có thể không tương thích. Giữ tương thích hoặc xử lý execution cũ có chủ đích.

**Giả định reader restart làm writer exactly-once:** transaction nhiều resource và failure window vẫn có thể tạo ghi trùng. Thiết kế idempotent writer.

## 25. Checklist thiết kế restart reader database

Trước khi đưa job vào production, xác nhận:

- Reader triển khai ItemStream hoặc reader framework có hỗ trợ lifecycle.
- saveState(true) được bật khi cần restart.
- Reader có tên ổn định và duy nhất trong step.
- Query có điều kiện lọc và thứ tự xác định.
- Cursor reader dùng sort order duy nhất; paging reader có sort key duy nhất/bất biến.
- Job restart dùng đúng identifying JobParameters.
- Tham số query và phạm vi dữ liệu được giữ nguyên giữa lần chạy và restart.
- ExecutionContext được lưu trong JobRepository bền vững.
- Delegate stream được đăng ký với step.
- Writer có thể xử lý lại item an toàn hoặc có idempotency.
- Integration test chứng minh resume sau chunk đã commit.
- Có chiến lược khi source data thay đổi hoặc ứng dụng được deploy phiên bản mới.

## 26. Quy trình thiết kế và kiểm thử trong production

Trước tiên, xác định tập dữ liệu mà job sẽ đọc và bảo đảm tập đó có thể tái lập khi restart. Chọn cursor reader nếu cần đọc liên tục một cursor và dữ liệu có thứ tự ổn định; chọn paging reader khi muốn phân trang và khôi phục theo sort key. Dùng ORDER BY xác định, unique/composite sort key và cutoff/batch membership nếu nguồn có thể thay đổi.

Tiếp theo, cấu hình reader có tên ổn định và saveState(true). Để reader tham gia lifecycle ItemStream, lưu checkpoint trong ExecutionContext và dùng JobRepository bền vững. Khi restart, chạy lại cùng JobInstance với identifying parameters giống lần trước; không tạo run.id mới nếu mục tiêu là tiếp tục execution cũ.

Cuối cùng, kiểm thử bằng database thật: commit một chunk, làm chunk tiếp theo thất bại, rồi restart và xác nhận reader tiếp tục từ checkpoint. Kiểm tra không thiếu/trùng business key, resource cũ được đóng, query/sort key không thay đổi và writer idempotent trong failure window. Nếu có nhiều datasource, thiết kế riêng cách đồng bộ business commit với metadata checkpoint.

Restart reader database dựa trên checkpoint đã commit và một truy vấn có thể tái lập. JdbcCursorItemReader khôi phục vị trí trong kết quả; JdbcPagingItemReader khôi phục dựa trên sort key. Khi reader name, query, parameters và dữ liệu nguồn ổn định, Spring Batch có thể tiếp tục xử lý sau lỗi mà không phải bắt đầu lại toàn bộ batch. Writer idempotent và integration test restart hoàn chỉnh giúp bảo vệ dữ liệu trong các tình huống process dừng hoặc transaction thất bại.
