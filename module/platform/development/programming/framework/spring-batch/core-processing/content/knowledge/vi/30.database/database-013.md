# Đọc và ghi cùng database

Trong Spring Batch, một Job thường đọc dữ liệu từ database, xử lý từng item rồi ghi kết quả trở lại database. Có thể đọc bảng nguồn và ghi bảng đích, hoặc đọc các hàng rồi cập nhật chính những hàng đó. Cả hai cách đều phổ biến, nhưng cần thiết kế đúng transaction, reader, writer, thứ tự đọc và checkpoint để tránh đọc trùng, bỏ sót dữ liệu hoặc giữ khóa quá lâu.

Khi reader và writer cùng dùng một database, điều quan trọng là xác định rõ:

- Reader và writer có dùng cùng DataSource không?
- Step dùng transaction manager nào?
- Reader có tham gia transaction của chunk hay mở connection riêng?
- Writer ghi vào bảng khác hay cập nhật bảng mà reader đang đọc?
- Dữ liệu được phân trang theo khóa ổn định nào?
- Khi rollback hoặc restart, reader có thể tiếp tục chính xác không?

Không nên mặc định rằng cùng database đồng nghĩa mọi thao tác đọc và ghi đều dùng cùng một connection hoặc cùng một snapshot. Điều đó phụ thuộc reader implementation, transaction manager, isolation level và database driver.

## 1. Hai mô hình đọc và ghi cùng database

Có hai mô hình thường gặp:

**Đọc bảng nguồn, ghi bảng kết quả**

~~~text
orders_source
      |
      v
ItemReader
      |
      v
ItemProcessor
      |
      v
ItemWriter
      |
      v
orders_result
~~~

Ví dụ đọc giao dịch đã hoàn tất từ bảng orders, tính phí và ghi kết quả sang bảng order_summary. Hai bảng ở cùng database nhưng dữ liệu nguồn và đích tách biệt. Đây thường là mô hình dễ kiểm soát hơn.

**Đọc và cập nhật cùng bảng**

~~~text
orders
  |
  v
Reader lấy các hàng có status = READY
  |
  v
Processor kiểm tra và tính toán
  |
  v
Writer cập nhật status = PROCESSED
  |
  v
orders
~~~

Mô hình thứ hai cần chú ý hơn. Nếu writer thay đổi cột dùng trong điều kiện đọc hoặc khóa phân trang, tập dữ liệu mà reader đang duyệt có thể thay đổi ngay trong lúc Step chạy. Nếu nhiều Job cùng xử lý bảng, còn phải tránh hai Job cùng nhận một hàng.

## 2. Cấu hình DataSource và transaction manager

Một chunk Step thường nhận JobRepository và PlatformTransactionManager. Với JDBC, transaction manager phổ biến là DataSourceTransactionManager hoặc JdbcTransactionManager quản lý một DataSource.

Ví dụ cấu hình Step đọc và ghi cùng database:

~~~java
@Bean
public Step summarizeOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ItemProcessor<Order, OrderSummary> processor,
        ItemWriter<OrderSummary> summaryWriter) {

    return new StepBuilder("summarizeOrdersStep", jobRepository)
            .<Order, OrderSummary>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(processor)
            .writer(summaryWriter)
            .build();
}
~~~

Nếu reader và writer sử dụng cùng DataSource được quản lý bởi transaction manager của Step, các thao tác JDBC tham gia transaction theo cơ chế hỗ trợ của từng thành phần. Khi writer thất bại trước commit, các thay đổi database trong transaction chunk có thể rollback.

Không chỉ dựa vào việc hai bean cùng nhận một URL JDBC để kết luận chúng dùng chung transaction. Hãy kiểm tra chúng thực sự dùng cùng bean DataSource và transaction manager tương ứng. Hai DataSource bean riêng, dù trỏ đến cùng một database/schema, vẫn có thể tạo hai connection pool và hai transaction độc lập.

### JobRepository có nhất thiết cùng database nghiệp vụ không?

JobRepository lưu metadata như JobExecution, StepExecution và ExecutionContext. Database nghiệp vụ lưu dữ liệu mà Job đọc/ghi. Hai phần có thể dùng cùng database hoặc tách riêng.

Nếu metadata và dữ liệu nghiệp vụ cùng tham gia một transaction manager phù hợp, việc cập nhật checkpoint và dữ liệu chunk có thể được phối hợp trong transaction. Nếu chúng nằm ở hai database hoặc dùng hai transaction manager độc lập, cần đánh giá rủi ro commit lệch nhau.

Ví dụ, dữ liệu nghiệp vụ commit nhưng checkpoint không được lưu có thể khiến restart đọc lại item và ghi trùng. Ngược lại, checkpoint được lưu nhưng dữ liệu nghiệp vụ rollback có thể làm reader bỏ qua item chưa được ghi. Với hai resource độc lập, cần thiết kế idempotency, unique key hoặc cơ chế đối soát.

## 3. Đọc và ghi bằng JDBC reader/writer

Spring Batch cung cấp các thành phần JDBC phổ biến:

| Thành phần | Vai trò |
| --- | --- |
| JdbcCursorItemReader | Đọc kết quả truy vấn qua JDBC cursor |
| JdbcPagingItemReader | Đọc theo từng trang bằng truy vấn phân trang |
| JdbcBatchItemWriter | Ghi nhiều item bằng JDBC batch update |
| JdbcTemplate | Thực hiện các thao tác JDBC trong service hoặc component tùy chỉnh |

Chọn reader dựa trên kích thước dữ liệu, khả năng cursor của database, cách phân trang, restart và tác động đến transaction. Writer thường dùng JdbcBatchItemWriter nếu cần insert/update theo batch.

## 4. Ví dụ đọc một bảng và ghi sang bảng khác

Giả sử có hai bảng:

~~~sql
create table orders (
    order_id bigint primary key,
    customer_code varchar(40),
    total_amount decimal(18, 2),
    status varchar(20)
);

create table order_summary (
    order_id bigint primary key,
    customer_code varchar(40),
    total_amount decimal(18, 2),
    tax_amount decimal(18, 2),
    processed_at timestamp
);
~~~

Reader lấy các đơn hàng đã hoàn tất:

~~~java
@Bean
@StepScope
public JdbcPagingItemReader<Order> orderReader(
        DataSource dataSource,
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    return new JdbcPagingItemReaderBuilder<Order>()
            .name("orderReader")
            .dataSource(dataSource)
            .selectClause(
                    "select order_id, customer_code, total_amount, status")
            .fromClause("from orders")
            .whereClause(
                    "where status = :status and business_date = :businessDate")
            .parameterValues(Map.of(
                    "status", "COMPLETED",
                    "businessDate", businessDate))
            .sortKeys(Map.of("order_id", Order.ASCENDING))
            .rowMapper(new OrderRowMapper())
            .pageSize(500)
            .saveState(true)
            .build();
}
~~~

Processor tính thuế:

~~~java
public class OrderSummaryProcessor
        implements ItemProcessor<Order, OrderSummary> {

    @Override
    public OrderSummary process(Order order) {
        BigDecimal tax = order.getTotalAmount()
                .multiply(new BigDecimal("0.10"));

        return new OrderSummary(
                order.getOrderId(),
                order.getCustomerCode(),
                order.getTotalAmount(),
                tax,
                Instant.now());
    }
}
~~~

Writer ghi bảng kết quả:

~~~java
@Bean
public JdbcBatchItemWriter<OrderSummary> summaryWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<OrderSummary>()
            .dataSource(dataSource)
            .sql("""
                    insert into order_summary
                    (order_id, customer_code, total_amount,
                     tax_amount, processed_at)
                    values
                    (:orderId, :customerCode, :totalAmount,
                     :taxAmount, :processedAt)
                    """)
            .beanMapped()
            .assertUpdates(true)
            .build();
}
~~~

Trong ví dụ, reader truy vấn bảng orders còn writer insert sang order_summary. Nếu hai thành phần dùng cùng DataSource và transaction manager của Step, insert được thực hiện trong transaction chunk. Khi chunk rollback, các insert chưa commit được rollback theo transaction database.

Ví dụ giả định order_id là duy nhất trong tập dữ liệu xử lý và order_summary chưa có các hàng tương ứng. Nếu Job có thể restart hoặc chạy lại cùng business input, cần xác định hành vi khi khóa đã tồn tại: fail, update, upsert theo database, hoặc bỏ qua có kiểm soát. Không dùng một chiến lược ghi đè tùy tiện để che giấu việc xử lý trùng.

## 5. JdbcBatchItemWriter và batch update

JdbcBatchItemWriter phù hợp khi mỗi item tạo ra một câu lệnh insert hoặc update. Writer thực thi các câu lệnh theo batch để giảm số lần round trip đến database.

Ví dụ update trạng thái đơn hàng:

~~~java
@Bean
public JdbcBatchItemWriter<Order> orderStatusWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("""
                    update orders
                    set status = :status,
                        processed_at = :processedAt
                    where order_id = :orderId
                    """)
            .beanMapped()
            .assertUpdates(true)
            .build();
}
~~~

Nếu update không ảnh hưởng đúng số hàng dự kiến, assertUpdates(true) giúp phát hiện một số trường hợp writer không cập nhật hàng nào. Tuy nhiên, semantics của batch update count có thể khác theo JDBC driver và câu lệnh; cần kiểm thử trên database thực tế.

Với câu lệnh update có điều kiện, nên đưa điều kiện bảo vệ vào SQL:

~~~sql
update orders
set status = 'PROCESSED'
where order_id = :orderId
  and status = 'READY'
~~~

Điều kiện status = READY giúp phát hiện hoặc ngăn việc cập nhật một hàng đã được worker khác xử lý. Nếu không có hàng nào được cập nhật, ứng dụng cần quyết định đó là duplicate, conflict hay lỗi dữ liệu.

## 6. Đọc và cập nhật chính bảng đang đọc

Trường hợp đọc rồi cập nhật cùng bảng thường dùng khi xử lý hàng đợi công việc trong database:

~~~text
orders.status = READY
        |
        v
Reader chọn hàng READY
        |
        v
Processor xử lý
        |
        v
Writer đổi status thành PROCESSED
~~~

Vấn đề xuất hiện khi status là điều kiện lọc. Sau khi writer cập nhật một hàng từ READY sang PROCESSED, hàng đó không còn thuộc tập truy vấn READY. Nếu reader phân trang theo offset hoặc cách truy vấn bị ảnh hưởng bởi tập kết quả đang thay đổi, các hàng tiếp theo có thể bị bỏ qua hoặc lặp lại.

Ví dụ giả sử truy vấn trả 10 hàng READY, page size bằng 5:

~~~text
Trang đầu: 1, 2, 3, 4, 5
Writer đổi trạng thái các hàng này thành PROCESSED

Tập READY còn: 6, 7, 8, 9, 10
Nếu truy vấn trang tiếp theo dùng offset 5:
  bỏ qua 5 hàng đầu của tập còn lại
  có thể không còn hàng nào được trả về
~~~

Đây là rủi ro của phân trang theo vị trí trên một tập kết quả thay đổi. Các reader paging của Spring Batch có thể dùng sort key và truy vấn theo khóa tùy database dialect, vì vậy không phải mọi cấu hình đều dùng offset theo ví dụ. Dù vậy, nguyên tắc vẫn là giữ điều kiện đọc và khóa phân trang ổn định trong suốt lần chạy.

### Tránh thay đổi điều kiện chọn hàng trong lúc duyệt

Nếu reader chọn status = READY, đừng cập nhật status của các hàng đó trong khi vẫn dựa vào một phân trang không ổn định trên cùng tập dữ liệu. Có thể:

- Đọc một tập ID đã được xác định trước.
- Dùng một cột khóa bất biến làm sort key.
- Chọn một batch ID hoặc cutoff cố định.
- Dùng staging/claim table để giữ tập công việc ổn định.
- Chia bước chọn dữ liệu và bước cập nhật trạng thái khi phù hợp.

## 7. Dùng staging table để tách tập input

Một mẫu dễ kiểm soát là tạo bảng staging hoặc bảng batch membership để cố định các hàng thuộc lần chạy:

~~~sql
create table batch_order_item (
    batch_id varchar(80) not null,
    order_id bigint not null,
    processing_status varchar(20) not null,
    primary key (batch_id, order_id)
);
~~~

Một bước chuẩn bị chọn các order cần xử lý và ghi ID vào batch_order_item. Step xử lý sau đó chỉ đọc các hàng thuộc batch_id hiện tại:

~~~sql
select o.order_id, o.customer_code, o.total_amount
from orders o
join batch_order_item b on b.order_id = o.order_id
where b.batch_id = :batchId
  and b.processing_status = 'READY'
order by o.order_id
~~~

Khi writer cập nhật trạng thái, có thể cập nhật processing_status trong staging table hoặc ghi kết quả sang bảng khác. Tập thành viên của batch không thay đổi chỉ vì status nghiệp vụ của orders thay đổi.

Staging giúp:

- Xác định rõ hàng nào thuộc JobInstance.
- Giữ tập input ổn định qua restart.
- Đối soát số hàng được chọn, xử lý và lỗi.
- Chia phạm vi cho partition.
- Tránh phụ thuộc vào điều kiện động trên bảng nghiệp vụ.

Đổi lại, cần quản lý vòng đời staging record, batch ID, cleanup và tính nhất quán giữa staging với dữ liệu nghiệp vụ.

## 8. Claim hoặc reserve hàng để nhiều Job không xử lý trùng

Nếu nhiều Job hoặc nhiều worker cùng đọc một bảng READY, chỉ dùng SELECT rồi xử lý có thể khiến hai worker nhận cùng một hàng. Cần cơ chế claim/reserve.

Một cách là cập nhật trạng thái sang CLAIMED với owner hoặc batch ID trước khi xử lý:

~~~sql
update orders
set status = 'CLAIMED',
    claimed_by = :workerId,
    claimed_at = current_timestamp
where order_id = :orderId
  and status = 'READY'
~~~

Chỉ worker cập nhật được đúng một hàng mới được xem là đã claim thành công. Nếu update count bằng 0, hàng có thể đã được worker khác claim hoặc trạng thái đã thay đổi.

Tuy nhiên, claim từng hàng sau khi reader đã đọc không tự bảo đảm toàn bộ quy trình atomic. Cần xác định transaction boundary, timeout của claim và cách thu hồi claim bị bỏ dở khi worker chết.

Một số database hỗ trợ SELECT ... FOR UPDATE SKIP LOCKED để nhiều worker chọn các hàng khác nhau:

~~~sql
select order_id, customer_code, total_amount
from orders
where status = 'READY'
order by order_id
for update skip locked
~~~

Đây là cú pháp phụ thuộc database, không phải SQL portable. Hành vi khóa, giữ khóa qua transaction và tương thích với cursor/paging reader phải được kiểm thử trên database đang dùng. Không giả định mọi JDBC driver hoặc database đều hỗ trợ SKIP LOCKED.

Với xử lý lâu, giữ row lock trong suốt thời gian processor/writer có thể làm tăng contention. Một mô hình claim ngắn rồi xử lý ngoài transaction có thể giảm thời gian giữ khóa, nhưng cần lease/timeout và khả năng phục hồi claim.

## 9. Transaction isolation và khả năng nhìn thấy dữ liệu

Isolation level quyết định transaction có thể nhìn thấy thay đổi của transaction khác như thế nào. Các mức phổ biến:

| Isolation | Ý nghĩa khái quát |
| --- | --- |
| READ_UNCOMMITTED | Có thể đọc dữ liệu chưa commit nếu database hỗ trợ |
| READ_COMMITTED | Chỉ đọc dữ liệu đã commit; truy vấn sau có thể thấy commit mới |
| REPEATABLE_READ | Hạn chế việc đọc lại cùng hàng cho kết quả khác nhau; chi tiết phụ thuộc database |
| SERIALIZABLE | Cung cấp mức cô lập cao hơn, thường có chi phí khóa hoặc kiểm tra xung đột lớn hơn |

Không nên chọn isolation level cao nhất cho mọi Job. Isolation cao có thể tăng khóa, deadlock và thời gian transaction. Isolation thấp có thể cho phép tập dữ liệu thay đổi giữa các trang hoặc chunk.

Với Job cần xử lý một snapshot logic, có thể dùng cutoff cố định, snapshot isolation nếu database hỗ trợ, staging table hoặc batch membership thay vì giữ một transaction rất dài.

### Một Job không có một snapshot duy nhất mặc định

Chunk-oriented Step thường commit sau mỗi chunk. Vì vậy, mỗi chunk có transaction riêng. Nếu nguồn thay đổi giữa các chunk, Step có thể nhìn thấy dữ liệu khác nhau tùy isolation và reader.

Ví dụ:

~~~text
Chunk 1 transaction -> đọc dữ liệu lúc T1 -> commit
Chunk 2 transaction -> đọc dữ liệu lúc T2 -> commit
Chunk 3 transaction -> đọc dữ liệu lúc T3 -> commit
~~~

Nếu yêu cầu nghiệp vụ cần một tập input cố định, hãy cố định tập dữ liệu bằng batch ID, watermark, snapshot hoặc bảng staging. Không giả định toàn Job tự động chạy trong một transaction duy nhất.

## 10. JdbcCursorItemReader khi cùng database với writer

JdbcCursorItemReader mở JDBC cursor để đọc result set. Một điểm cần chú ý là reader thường mở connection riêng cho cursor để cursor có thể tiếp tục tồn tại qua các lần commit của chunk. Vì vậy, việc writer dùng cùng DataSource không có nghĩa cursor mặc định dùng cùng connection transaction với writer.

Ví dụ:

~~~java
@Bean
@StepScope
public JdbcCursorItemReader<Order> orderCursorReader(
        DataSource dataSource) {

    return new JdbcCursorItemReaderBuilder<Order>()
            .name("orderCursorReader")
            .dataSource(dataSource)
            .sql("""
                    select order_id, customer_code, total_amount
                    from orders
                    where status = 'READY'
                    order by order_id
                    """)
            .rowMapper(new OrderRowMapper())
            .fetchSize(500)
            .saveState(true)
            .build();
}
~~~

Cursor reader có thể phù hợp với tập dữ liệu lớn và database/driver hỗ trợ cursor hiệu quả. Cần chú ý:

- Cursor connection có thể khác connection của transaction chunk.
- Writer có thể cập nhật cùng các hàng mà cursor đang duyệt.
- Isolation và cursor holdability phụ thuộc database/driver.
- Cursor thường giữ connection trong thời gian dài, ảnh hưởng connection pool.
- Restart cần reader lưu state và có khả năng mở lại truy vấn ở vị trí phù hợp.

JdbcCursorItemReader có tùy chọn chia sẻ extended connection trong những trường hợp cần dùng chung connection đã được bọc phù hợp. Cấu hình này cần ExtendedConnectionDataSourceProxy và driver hỗ trợ cursor holdability qua commit. Không bật chỉ vì reader và writer cùng database; hãy xác nhận yêu cầu và kiểm thử với database/driver thật.

## 11. JdbcPagingItemReader khi đọc và ghi cùng bảng

JdbcPagingItemReader lấy dữ liệu theo từng trang. Nó phù hợp khi không muốn giữ cursor mở lâu hoặc cần phân trang và restart theo sort key.

Ví dụ:

~~~java
@Bean
@StepScope
public JdbcPagingItemReader<Order> readyOrderReader(
        DataSource dataSource) {

    return new JdbcPagingItemReaderBuilder<Order>()
            .name("readyOrderReader")
            .dataSource(dataSource)
            .selectClause(
                    "select order_id, customer_code, total_amount")
            .fromClause("from orders")
            .whereClause("where status = :status")
            .parameterValues(Map.of("status", "READY"))
            .sortKeys(Map.of("order_id", Order.ASCENDING))
            .rowMapper(new OrderRowMapper())
            .pageSize(200)
            .saveState(true)
            .build();
}
~~~

Sort key phải xác định thứ tự ổn định và tốt nhất là duy nhất. Nếu dùng nhiều cột, cần đảm bảo tổ hợp sort key tạo thứ tự toàn phần.

Nếu writer cập nhật status từ READY sang PROCESSED, điều kiện truy vấn thay đổi trong lúc Step đang đọc. Cần kiểm tra cách paging provider tạo truy vấn và đảm bảo các trang tiếp theo không bỏ sót hàng. Một cách an toàn hơn là dùng batch ID/staging hoặc phân vùng theo khóa bất biến.

Page size và chunk size là hai tham số khác nhau:

- Page size quyết định số hàng reader lấy trong một lần truy vấn trang.
- Chunk size quyết định số item xử lý trong một transaction chunk.

Ví dụ page size 500 và chunk size 100 có nghĩa reader có thể nạp một trang 500 hàng nhưng Step commit sau mỗi 100 item. Cần cân bằng bộ nhớ, round trip, transaction duration và tác động khi restart.

## 12. Đọc bằng cursor hay paging?

| Tiêu chí | JdbcCursorItemReader | JdbcPagingItemReader |
| --- | --- | --- |
| Cách đọc | Giữ result set/cursor mở | Truy vấn theo từng trang |
| Connection | Thường dùng connection riêng cho cursor | Thực hiện query theo từng trang; có thể tham gia transaction theo cấu hình DataSource |
| Tài nguyên | Có thể giữ connection lâu | Không cần giữ một cursor xuyên suốt toàn bộ Step |
| Restart | Cần lưu và khôi phục vị trí cursor | Lưu trạng thái phân trang/sort key |
| Thay đổi dữ liệu nguồn | Phụ thuộc cursor, isolation và database | Tập kết quả có thể thay đổi giữa các trang |
| Phù hợp | Đọc tuần tự dài trên DB hỗ trợ cursor tốt | Tập dữ liệu lớn cần phân trang và restart |

Không có lựa chọn tốt nhất cho mọi database. Đo query, fetch size, page size, thời gian mở cursor, connection usage và hành vi restart trên môi trường tương tự production.

## 13. Tránh đọc lại dữ liệu đã xử lý

Một thiết kế phổ biến là dùng trạng thái READY và PROCESSED. Nếu reader chọn READY và writer đổi thành PROCESSED, cần đảm bảo reader không bị ảnh hưởng bởi thay đổi tập kết quả theo cách làm sai vị trí phân trang.

Một phương án là chọn một watermark cố định cho lần chạy:

~~~sql
select order_id, customer_code, total_amount
from orders
where status = 'READY'
  and order_id <= :maxOrderId
order by order_id
~~~

Trong bước chuẩn bị, lấy maxOrderId hoặc cutoff rồi lưu vào JobParameters/JobExecutionContext. Điều này giới hạn tập input của Job. Tuy nhiên, nếu hàng READY mới được thêm với ID nhỏ hơn watermark hoặc trạng thái thay đổi, cần quy định rõ có thuộc batch hiện tại hay không.

Phương án khác là lưu danh sách ID vào staging table. Đây thường là lựa chọn rõ ràng hơn khi tập dữ liệu cần được cố định qua restart.

Không dùng thời điểm hiện tại được tính lại ở mỗi chunk làm cutoff. Hãy xác định cutoff một lần ở đầu Job và giữ nguyên trong suốt JobInstance.

## 14. Idempotency và khóa nghiệp vụ

Restart, retry hoặc chạy lại Job có thể khiến cùng một item được xử lý nhiều lần. Nếu writer insert kết quả, cần có khóa duy nhất hoặc cơ chế idempotent.

Ví dụ:

~~~sql
create table order_result (
    order_id bigint primary key,
    result_amount decimal(18, 2),
    processed_at timestamp
);
~~~

Khóa order_id ngăn hai lần xử lý tạo hai hàng kết quả giống nhau. Khi insert gặp duplicate key, ứng dụng cần quyết định đó là lỗi cần fail, một lần chạy lại hợp lệ hay cần update theo version.

Với update, nên dùng điều kiện trạng thái cũ hoặc version:

~~~sql
update orders
set status = 'PROCESSED',
    version = version + 1
where order_id = :orderId
  and status = 'READY'
  and version = :expectedVersion
~~~

Nếu số hàng cập nhật bằng 0, có thể dữ liệu đã bị worker khác thay đổi. Xử lý như conflict hoặc duplicate theo quy tắc nghiệp vụ.

Không chỉ dựa vào việc writer chạy trong transaction để kết luận không thể trùng. Transaction rollback không hoàn tác side effect đã gửi sang API, message broker hoặc hệ thống khác. Với các side effect đó, dùng idempotency key, inbox/outbox hoặc cơ chế đối soát.

## 15. Locking và deadlock

Khi nhiều Job hoặc worker đọc và cập nhật cùng bảng, database có thể phải giữ row lock hoặc page lock tùy câu lệnh và engine. Transaction chunk quá lớn có thể giữ nhiều khóa lâu hơn.

Các nguyên nhân thường gặp:

- Hai Job chọn cùng tập hàng READY.
- Reader giữ cursor trong khi writer cập nhật cùng bảng.
- Các worker cập nhật nhiều hàng theo thứ tự khác nhau.
- Index không phù hợp khiến database khóa phạm vi rộng hơn dự kiến.
- Chunk size lớn làm transaction giữ khóa lâu.
- Writer batch update tạo lock contention.

Giảm rủi ro bằng cách:

- Chia phạm vi công việc không chồng lấn.
- Cập nhật hàng theo thứ tự khóa ổn định.
- Giữ transaction ngắn.
- Tạo index phù hợp với điều kiện lọc và sort key.
- Dùng claim/reservation hoặc SKIP LOCKED nếu database hỗ trợ.
- Giới hạn concurrency theo khả năng database.
- Thiết lập retry có giới hạn cho deadlock/serialization failure.

Không retry vô hạn một deadlock. Nếu cùng một thứ tự truy cập tài nguyên luôn gây deadlock, cần sửa thiết kế truy vấn hoặc thứ tự cập nhật.

## 16. Transaction timeout và chunk size

Chunk size ảnh hưởng trực tiếp đến số hàng writer cập nhật trong một transaction. Chunk lớn giảm số lần commit nhưng có thể:

- Giữ row lock lâu hơn.
- Tăng rollback cost.
- Tăng bộ nhớ.
- Làm deadlock khó phục hồi hơn.
- Tăng thời gian chờ connection hoặc transaction timeout.

Chunk nhỏ thường giảm thời gian transaction nhưng làm tăng số lần commit và metadata update.

Hãy đo thời gian đọc, xử lý, ghi và commit. Nếu processor gọi dịch vụ từ xa, không nên giữ transaction database mở trong thời gian chờ mạng dài. Có thể tách xử lý ngoài database khỏi phần ghi ngắn trong transaction, nhưng phải giữ tính nhất quán bằng idempotency và trạng thái công việc.

## 17. Restart và checkpoint khi đọc/ghi cùng database

Reader và writer cần lưu state phù hợp để restart. Với reader có hỗ trợ ItemStream, checkpoint thường được lưu trong StepExecutionContext tại ranh giới chunk. JdbcPagingItemReader và JdbcCursorItemReader có thể lưu trạng thái đọc khi saveState được bật.

Ví dụ:

~~~java
return new StepBuilder("processOrdersStep", jobRepository)
        .<Order, OrderResult>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderResultWriter)
        .build();
~~~

Khi chunk commit, dữ liệu writer và checkpoint cần nhất quán. Khi chunk rollback, trạng thái chưa commit không được xem là checkpoint bền vững.

Để restart an toàn:

- Giữ Job name và identifying JobParameters của JobInstance.
- Giữ reader name ổn định.
- Giữ sort key và query filter ổn định.
- Không thay input dataset hoặc cutoff giữa lần chạy và restart.
- Đảm bảo writer idempotent nếu item có thể được xử lý lại.
- Không xóa hoặc thay đổi dữ liệu staging mà checkpoint đang phụ thuộc.

Nếu reader query các hàng READY nhưng writer đổi trạng thái sang PROCESSED, restart phải tái tạo được cùng tập dữ liệu chưa hoàn tất. Staging table hoặc batch membership thường giúp việc này rõ ràng hơn.

## 18. Đọc và ghi cùng database trong một Step hay nhiều Step?

Có thể tách quy trình thành nhiều Step khi cần ranh giới rõ:

~~~text
prepareBatchStep
    |
    v
processBatchStep
    |
    v
finalizeBatchStep
~~~

Ví dụ:

- prepareBatchStep chọn các hàng và ghi ID vào staging table.
- processBatchStep đọc staging và ghi kết quả.
- finalizeBatchStep cập nhật trạng thái batch, tổng hợp lỗi và đánh dấu hoàn tất.

Tách Step giúp theo dõi tiến độ, restart và đối soát rõ hơn. Tuy nhiên, các Step có transaction riêng; dữ liệu trung gian cần được quản lý bền vững và có thể restart.

Nếu quy trình nhỏ và không cần staging, một chunk Step có thể đủ. Không nên tách nhiều Step chỉ để tránh hiểu transaction; hãy dựa trên yêu cầu nghiệp vụ, khả năng phục hồi và quan sát.

## 19. Kiểm thử đọc và ghi cùng database

Nên kiểm thử với database có semantics gần production. H2 hoặc database in-memory có thể khác về cursor, locking, isolation, paging SQL và batch update count.

Các tình huống cần kiểm tra:

1. Đọc từ bảng nguồn và insert sang bảng đích trong cùng transaction.
2. Writer lỗi giữa batch và xác nhận dữ liệu chunk rollback.
3. Restart sau một số chunk commit và kiểm tra không mất/ghi trùng hàng.
4. Đọc và cập nhật cùng bảng với page size lớn hơn chunk size.
5. Hai Job cùng chọn tập READY để kiểm tra claim/locking.
6. Một hàng bị worker khác thay đổi trước khi writer update.
7. Deadlock hoặc lock timeout và retry có giới hạn.
8. Nguồn thay đổi trong lúc Job chạy.
9. Job restart khi staging/batch membership vẫn tồn tại.
10. Job chạy đồng thời với cùng hoặc khác JobParameters.

Ví dụ kiểm tra rollback:

~~~java
@Test
void rollsBackDatabaseWritesWhenChunkFails() {
    // Khởi chạy Step với reader và writer dùng cùng DataSource.
    // Cấu hình writer/test hook gây lỗi trước commit.
    // Sau khi Step thất bại, truy vấn bảng đích để xác nhận
    // các hàng của chunk chưa commit không tồn tại.
}
~~~

Đây là khung mô tả kiểm thử; cần triển khai fixture và fault injection theo ứng dụng. Đừng chỉ assert BatchStatus. Hãy truy vấn database để xác nhận dữ liệu, trạng thái hàng, checkpoint và số lượng bản ghi.

## 20. Những lỗi thường gặp

### Nghĩ cùng database đồng nghĩa cùng transaction

Hai bean có thể dùng DataSource hoặc transaction manager khác nhau dù trỏ đến cùng database. Xác nhận resource được quản lý thực sự.

### Đọc và cập nhật cùng bảng với query không ổn định

Writer thay đổi điều kiện lọc hoặc sort key trong khi reader đang phân trang. Dùng khóa bất biến, batch ID hoặc staging table.

### Dùng cursor và giả định writer dùng cùng connection

JdbcCursorItemReader thường mở connection riêng cho cursor. Kiểm tra shared extended connection và yêu cầu driver nếu cần.

### Phân trang không có thứ tự duy nhất

Thứ tự không ổn định có thể gây đọc trùng hoặc bỏ sót. Dùng sort key duy nhất hoặc khóa ghép.

### Nhiều Job cùng đọc hàng READY

Hai Job có thể nhận cùng item. Dùng claim, lock, batch membership hoặc cơ chế điều phối.

### Transaction quá dài

Chunk lớn hoặc processor chờ dịch vụ ngoài có thể giữ khóa lâu. Tối ưu transaction duration và chunk size.

### Writer không idempotent

Restart hoặc retry có thể tạo kết quả trùng. Dùng unique key, upsert có kiểm soát hoặc version check.

### Dùng skip để bỏ qua mọi lỗi database

Lỗi kết nối hoặc deadlock thường cần retry/fail policy riêng, không nên xem là dữ liệu lỗi có thể bỏ qua.

### Chỉ kiểm tra Step status

Step COMPLETED không chứng minh dữ liệu đích chính xác. Kiểm tra record count, business key, trạng thái nguồn và kết quả đối soát.

### Dùng database test khác production

Paging, cursor và locking semantics có thể khác. Chạy integration test trên cùng loại database khi hành vi phụ thuộc engine.

## 21. Quy trình thiết kế Step đọc và ghi cùng database

Trước khi triển khai, hãy xác định:

1. Reader và writer dùng cùng DataSource bean hay chỉ cùng database server?
2. Transaction manager của Step quản lý resource nào?
3. JobRepository có cùng transaction boundary với dữ liệu nghiệp vụ không?
4. Dữ liệu được đọc và ghi ở hai bảng hay cùng một bảng?
5. Nếu cùng bảng, writer có thay đổi điều kiện lọc hoặc sort key của reader không?
6. Cursor hay paging phù hợp hơn với database và tập dữ liệu?
7. Sort key có duy nhất và ổn định không?
8. Nguồn có thay đổi trong lúc Job chạy không?
9. Có cần batch ID, staging hoặc claim để cố định tập input không?
10. Nhiều Job/worker có thể nhận cùng hàng không?
11. Chunk size, page size, fetch size và connection pool có phù hợp không?
12. Retry, rollback và restart có thể tạo xử lý trùng không?
13. Writer có unique key hoặc idempotency phù hợp không?
14. Có cần đo lock wait, deadlock, query time và batch update count không?

Một thiết kế tốt giữ tập input ổn định, transaction ngắn, thứ tự đọc xác định và writer có thể phục hồi an toàn. Khi dữ liệu cần được chọn một lần rồi xử lý qua nhiều lần restart, staging hoặc batch membership thường là cách rõ ràng để bảo toàn phạm vi.

## Kết luận

Đọc và ghi cùng database là mô hình phổ biến trong Spring Batch, nhưng phải phân biệt đọc bảng nguồn rồi ghi bảng đích với đọc và cập nhật chính bảng đang duyệt. Dùng cùng DataSource và transaction manager phù hợp giúp writer tham gia transaction của chunk; tuy nhiên, reader như JdbcCursorItemReader có thể dùng connection riêng, còn paging phụ thuộc sort key và tập kết quả ổn định. Khi cập nhật cùng bảng, tránh làm thay đổi điều kiện lọc hoặc thứ tự phân trang trong lúc đọc; cân nhắc batch ID, staging, claim hoặc locking để tránh xử lý trùng. Thiết kế checkpoint, unique key và idempotency để retry/restart không làm mất hoặc ghi lặp dữ liệu, đồng thời kiểm thử trên database thực tế vì cursor, isolation và locking phụ thuộc engine.
