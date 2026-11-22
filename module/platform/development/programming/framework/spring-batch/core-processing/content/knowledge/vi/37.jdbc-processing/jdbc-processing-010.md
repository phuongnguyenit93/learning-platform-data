# Restart sau khi commit database

Trong một chunk-oriented step của Spring Batch, writer có thể ghi nhiều item vào database rồi transaction commit. Nếu job dừng ngay sau lần commit đó, lần chạy tiếp theo phải xác định chính xác phần dữ liệu nào đã được ghi bền vững và phần nào còn phải xử lý. Cơ chế restart của Spring Batch dựa trên checkpoint được lưu trong JobRepository, thường kết hợp với state do reader và writer ghi vào ExecutionContext.

Điểm cốt lõi là dữ liệu nghiệp vụ và checkpoint phải tiến lên nhất quán. Nếu database đã commit một chunk nhưng checkpoint vẫn ở vị trí cũ, restart có thể đọc và ghi lại item đã xử lý. Nếu checkpoint tiến lên nhưng dữ liệu nghiệp vụ chưa commit, restart có thể bỏ qua item chưa thực sự được lưu. Khi writer và JobRepository cùng tham gia một transaction database, Spring Batch có thể commit dữ liệu chunk và checkpoint trong cùng ranh giới transaction. Khi chúng dùng transaction manager hoặc resource khác nhau, cần thiết kế idempotency và đối soát vì không còn tính atomic tự nhiên giữa hai nơi.

## 1. Commit chunk và restart là hai phần của cùng một quy trình

Spring Batch thường xử lý dữ liệu theo chunk. Reader đọc một nhóm item, processor chuyển đổi từng item, writer ghi cả nhóm; sau đó transaction của chunk được commit.

Ví dụ chunk size 100:

~~~text
Chunk 1: items 1-100    -> write -> commit
Chunk 2: items 101-200 -> write -> commit
Chunk 3: items 201-300 -> write -> commit
...
~~~

Nếu job thất bại sau khi chunk 2 đã commit, restart cần tiếp tục từ checkpoint sau item 200. Hai chunk đầu đã được lưu bền vững; chunk tiếp theo chưa commit phải được thực hiện lại theo state đã lưu.

Một checkpoint không chỉ là số item đã đọc. Nó có thể gồm:

- Vị trí hiện tại của reader trong file hoặc resource.
- Page/sort key cuối cùng đã đọc.
- Số item đã đọc/ghi và trạng thái của step.
- State riêng do reader hoặc writer lưu trong ExecutionContext.
- Các thông tin cần thiết để mở lại resource và tiếp tục đúng vị trí.

Checkpoint chỉ có ích nếu nguồn dữ liệu và cấu hình reader vẫn tương ứng với state đó. Nếu file đầu vào bị thay đổi, thứ tự query thay đổi hoặc resource bị thay thế giữa hai lần chạy, cùng một checkpoint có thể trỏ đến dữ liệu khác.

## 2. Các thành phần tham gia restart

| Thành phần | Vai trò |
|---|---|
| JobInstance | Đại diện một lần chạy logic theo job name và identifying JobParameters |
| JobExecution | Một lần thực thi cụ thể của JobInstance; restart tạo JobExecution mới |
| StepExecution | Theo dõi một lần thực thi step, gồm status và execution metrics |
| JobRepository | Lưu metadata, trạng thái thực thi và ExecutionContext |
| ExecutionContext | Lưu state cần khôi phục khi restart |
| ItemStream | Lifecycle để component mở resource, lưu state và đóng resource |
| PlatformTransactionManager | Quản lý transaction của chunk và resource được enlist |
| ItemReader | Đọc item và lưu vị trí/checkpoint nếu hỗ trợ restart |
| ItemWriter | Ghi chunk và tham gia transaction phù hợp |

Spring Batch không tự suy ra mọi vị trí đọc từ database nghiệp vụ. Reader hoặc component có state phải triển khai ItemStream và ghi thông tin cần thiết qua update(ExecutionContext) nếu cần restart từ vị trí trước đó.

## 3. Trình tự xử lý một chunk

Ở mức khái niệm, một chunk có các bước:

1. Reader cung cấp các item tiếp theo.
2. Processor xử lý từng item nếu được cấu hình.
3. Writer ghi chunk.
4. Các ItemStream được yêu cầu cập nhật state vào ExecutionContext.
5. StepExecution/ExecutionContext được cập nhật trong JobRepository.
6. Transaction commit.

Sơ đồ rút gọn:

~~~mermaid
sequenceDiagram
    participant R as ItemReader
    participant P as ItemProcessor
    participant W as JDBC ItemWriter
    participant C as Step/Chunk
    participant J as JobRepository
    participant DB as Database

    C->>R: read items
    R-->>C: chunk items
    C->>P: process items
    P-->>C: processed items
    C->>W: write chunk
    W->>DB: INSERT/UPDATE
    C->>R: ItemStream.update(context)
    C->>J: persist ExecutionContext and StepExecution
    C->>DB: commit transaction
~~~

Sơ đồ mô tả trường hợp JobRepository và writer cùng tham gia một transaction phù hợp. Chi tiết nội bộ có thể khác theo phiên bản và cấu hình, nhưng nguyên tắc cần bảo đảm là thay đổi nghiệp vụ và checkpoint của chunk không được commit độc lập theo cách tạo ra trạng thái lệch nhau.

## 4. Vì sao database commit và checkpoint phải nhất quán?

Giả sử reader đã đọc đến item 100 và writer ghi các item đó.

**Trường hợp A: dữ liệu commit nhưng checkpoint không tiến lên**

- Database chứa kết quả của item 1-100.
- JobRepository vẫn lưu checkpoint trước item 1.
- Restart đọc lại item 1-100.
- Nếu writer không idempotent, có thể tạo duplicate hoặc lỗi unique key.

**Trường hợp B: checkpoint tiến lên nhưng dữ liệu chưa commit**

- JobRepository lưu checkpoint sau item 100.
- Database nghiệp vụ rollback hoặc chưa ghi bền vững.
- Restart bắt đầu từ item 101.
- Item 1-100 bị bỏ qua dù chưa có kết quả trong database.

Hai trường hợp đều là sai lệch giữa progress metadata và business data. Khi checkpoint và writer cùng nằm trong một transaction database, transaction commit hoặc rollback cả hai nhóm thay đổi, giảm thiểu cửa sổ sai lệch này.

## 5. Cùng transaction manager và cùng database resource

Để dữ liệu JDBC và metadata restart được commit nguyên tử, thông thường cần:

- JDBC writer dùng DataSource của database cần ghi.
- JobRepository dùng cùng database resource.
- Chunk step dùng transaction manager quản lý resource đó.
- Các thao tác ghi metadata và dữ liệu nghiệp vụ thực sự tham gia cùng transaction.

Ví dụ cấu hình khái quát:

~~~java
@Bean
public JdbcBatchItemWriter<Order> orderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("""
                    insert into processed_order(order_id, amount)
                    values (:orderId, :amount)
                    """)
            .beanMapped()
            .build();
}

@Bean
public Step processOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, Order> processor,
        JdbcBatchItemWriter<Order> writer) {

    return new StepBuilder("processOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
~~~

Đoạn mã minh họa giả định writer và JobRepository được cấu hình trên cùng transaction resource. Chỉ việc truyền cùng một đối tượng DataSource vào hai bean chưa đủ nếu transaction manager hoặc propagation khác nhau khiến các thao tác không tham gia cùng transaction. Cần kiểm tra cấu hình thực tế của JobRepository và transaction manager.

## 6. Khi JobRepository dùng database khác

Một số hệ thống lưu business data trong một database nhưng lưu Spring Batch metadata trong database riêng. Khi đó, một local transaction manager không thể tự commit nguyên tử cả hai database.

Ví dụ:

~~~text
Transaction A: business database
  - INSERT processed_order
  - COMMIT

Transaction B: batch metadata database
  - UPDATE StepExecution
  - UPDATE ExecutionContext
  - COMMIT
~~~

Nếu process dừng sau commit A nhưng trước commit B, database nghiệp vụ đã có kết quả trong khi checkpoint vẫn cũ. Khi restart, chunk có thể được thực hiện lại.

Nếu commit B xảy ra trước commit A, restart có thể bỏ qua item mà business data chưa được lưu. Thứ tự chính xác phụ thuộc transaction orchestration, nhưng khi hai resource không atomic, không nên giả định một thứ tự gọi method có thể loại bỏ mọi crash window.

Các hướng xử lý thường dùng:

- Đưa JobRepository và business writer vào cùng transaction resource nếu kiến trúc cho phép.
- Thiết kế writer idempotent theo business key.
- Dùng unique constraint để chống ghi trùng.
- Ghi trạng thái xử lý theo source key trong database nghiệp vụ.
- Thực hiện reconciliation sau crash.
- Nếu cần transaction xuyên nhiều resource, đánh giá XA/JTA và chi phí vận hành trước khi chọn.

## 7. Same JobInstance khi restart

Restart là tiếp tục một JobInstance đã thất bại hoặc bị dừng, không phải khởi tạo một instance mới.

JobInstance được xác định bởi job name và các identifying JobParameters. Khi restart:

- Giữ nguyên identifying parameters.
- Spring Batch tạo JobExecution mới cho cùng JobInstance.
- JobRepository cung cấp execution context đã lưu của lần chạy trước.
- Các step có thể tiếp tục theo state đã commit, tùy restartability và flow configuration.

Nếu thêm một identifying parameter mới như run timestamp hoặc tăng run.id, bạn thường tạo JobInstance mới. Khi đó reader có thể bắt đầu từ đầu và output identity cũng có thể thay đổi.

Một JobInstance đã COMPLETED thường không thể launch lại với cùng identifying parameters như một lần chạy mới. Muốn reprocess có chủ đích, hãy tạo một instance mới bằng output version hoặc identifying parameter phù hợp.

## 8. JobExecution mới không có nghĩa đọc lại từ đầu

Mỗi lần restart tạo JobExecution mới nhưng vẫn thuộc cùng JobInstance. Điều này cho phép phân biệt lần thực thi đầu và lần restart trong metadata, đồng thời giữ nguyên logical identity của job.

Ví dụ:

| Thuộc tính | Lần đầu | Lần restart |
|---|---|---|
| JobInstance | orders:businessDate=2026-11-15 | Cùng instance |
| JobExecution | ID 501 | ID 502 |
| StepExecution | ID 701 | ID mới |
| Checkpoint | Sau item 200 | Khôi phục checkpoint sau item 200 |
| Output identity | Cùng output key | Cùng output resource/state |

ID trong bảng chỉ minh họa. Điều quan trọng là JobExecution ID thay đổi, còn identifying parameters giữ nguyên để JobInstance không đổi.

Không dùng JobExecution ID làm duy nhất output filename nếu restart cần tiếp tục đúng file của lần chạy trước. Có thể ghi execution ID vào log hoặc manifest để audit.

## 9. Reader cần lưu state để restart

Reader có state phải hỗ trợ ItemStream. Trong lifecycle:

- open(context) mở resource và khôi phục vị trí.
- read() trả item kế tiếp.
- update(context) lưu vị trí/checkpoint hiện tại.
- close() giải phóng resource.

Ví dụ custom reader lưu offset:

~~~java
public class OffsetOrderReader
        implements ItemStreamReader<Order> {

    private static final String OFFSET_KEY = "orderReader.offset";
    private int offset;

    @Override
    public void open(ExecutionContext context) {
        offset = context.containsKey(OFFSET_KEY)
                ? context.getInt(OFFSET_KEY)
                : 0;
    }

    @Override
    public Order read() {
        Order order = readAt(offset);
        if (order != null) {
            offset++;
        }
        return order;
    }

    @Override
    public void update(ExecutionContext context) {
        context.putInt(OFFSET_KEY, offset);
    }

    @Override
    public void close() {
        // Đóng resource nếu reader có mở resource.
    }
}
~~~

Đây là ví dụ khái niệm. Offset chỉ an toàn nếu nguồn có thứ tự ổn định và vị trí offset luôn trỏ tới cùng item qua restart. Với database query, nên ưu tiên sort key ổn định và duy nhất thay vì dựa vào thứ tự không xác định.

## 10. saveState và tên reader

Các reader có sẵn thường cung cấp cấu hình saveState. Khi bật, reader lưu state vào ExecutionContext để tiếp tục sau checkpoint:

~~~java
new JdbcPagingItemReaderBuilder<Order>()
        .name("orderPagingReader")
        .dataSource(dataSource)
        .selectClause("select order_id, amount")
        .fromClause("from source_order")
        .sortKeys(Map.of("order_id", Order.ASCENDING))
        .pageSize(100)
        .rowMapper(orderRowMapper)
        .saveState(true)
        .build();
~~~

Tên reader phải ổn định giữa các lần chạy cùng JobInstance vì nó thường được dùng để tạo key trong ExecutionContext. Nếu đổi name, reader có thể không tìm thấy state cũ và bắt đầu từ vị trí mặc định.

Nếu có nhiều instance của cùng loại reader trong một step, mỗi reader cần tên riêng để state không ghi đè nhau. Khi dùng delegate hoặc composite, bảo đảm stream được đăng ký và mở/đóng đúng lifecycle.

## 11. JdbcPagingItemReader và sort key ổn định

Với database lớn, JdbcPagingItemReader thường đọc theo page và lưu thông tin vị trí để restart. Cần có sort key xác định, ổn định và tốt nhất là duy nhất.

Ví dụ:

~~~sql
select order_id, customer_id, amount
from source_order
where status = 'READY'
order by order_id
~~~

Nếu order_id duy nhất và không thay đổi, reader có thể tiếp tục sau key đã đọc. Nếu sort key không duy nhất, nhiều row có cùng key có thể khiến ranh giới page không rõ và tạo nguy cơ thiếu hoặc đọc lặp tùy query provider.

Không dùng ORDER BY theo một cột có nhiều giá trị trùng nếu không có tie-breaker. Có thể dùng composite sort key, ví dụ created_at và order_id, nếu API reader/query provider hỗ trợ đúng.

## 12. Nguồn dữ liệu phải ổn định qua restart

Checkpoint biểu diễn vị trí trong một nguồn dữ liệu cụ thể. Nếu nguồn thay đổi giữa lần chạy đầu và restart, cùng vị trí có thể đại diện cho record khác.

Ví dụ:

- Lần đầu query trả ID 1-1000.
- Job commit đến ID 500.
- Nguồn thêm record có ID nhỏ hơn 500 hoặc thay đổi status filter.
- Restart tiếp tục từ checkpoint nhưng tập dữ liệu không còn giống lúc đầu.

Kết quả có thể thiếu record mới, đọc lặp record cũ hoặc thay đổi thứ tự. Cần xác định input snapshot:

- Dùng batch date/cutoff cố định.
- Chọn tập record bằng snapshot ID hoặc high-water mark.
- Giữ immutable input file.
- Dùng staging table cho danh sách key cần xử lý.
- Lưu source version/checksum và xác minh khi restart.

Nếu business query dùng trạng thái mutable như READY/PROCESSED, cần đặc biệt chú ý việc writer cập nhật chính bảng nguồn vì điều đó có thể làm thay đổi kết quả query đang được reader sử dụng.

## 13. Đọc và cập nhật cùng một bảng

Một pattern thường gặp là đọc các row có status READY rồi writer cập nhật chúng thành PROCESSED:

~~~sql
select order_id, amount
from source_order
where status = 'READY'
order by order_id
~~~

~~~sql
update source_order
set status = 'PROCESSED'
where order_id = :orderId
~~~

Khi commit một chunk, các row đã xử lý biến mất khỏi điều kiện READY. Nếu reader dùng paging theo offset hoặc page query không ổn định, tập kết quả có thể dịch chuyển và bỏ qua record.

Một chiến lược ổn định hơn là:

- Dùng keyset paging theo ID bất biến.
- Lưu high-water mark ở đầu job.
- Query theo điều kiện ID lớn hơn key cuối và không vượt high-water mark.
- Hoặc claim một tập record bằng trạng thái/claim token có transaction rõ.

Ví dụ keyset:

~~~sql
select order_id, amount
from source_order
where order_id > :lastOrderId
  and order_id <= :highWaterMark
order by order_id
fetch first 100 rows only
~~~

Syntax giới hạn số dòng phụ thuộc database. Ý tưởng là thứ tự và biên nguồn được cố định, tránh offset bị thay đổi khi các row đã xử lý rời khỏi filter.

## 14. JdbcBatchItemWriter và transaction chunk

JdbcBatchItemWriter dùng NamedParameterJdbcTemplate để ghi nhiều item theo batch. Khi writer dùng DataSource được quản lý bởi transaction manager của step, các update tham gia transaction chunk:

~~~java
@Bean
public JdbcBatchItemWriter<ProcessedOrder> processedOrderWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<ProcessedOrder>()
            .dataSource(dataSource)
            .sql("""
                    insert into processed_order(order_id, amount)
                    values (:orderId, :amount)
                    """)
            .beanMapped()
            .assertUpdates(true)
            .build();
}
~~~

Nếu writer ném exception trước khi commit, transaction chunk có thể rollback các thay đổi database trong chunk. Khi restart, checkpoint không nên tiến qua chunk chưa commit.

Để behavior này hoạt động, writer phải dùng đúng transaction resource. Nếu writer tự mở connection riêng không tham gia transaction, database có thể commit độc lập với JobRepository và reader checkpoint.

## 15. Cùng database chưa chắc đã cùng transaction

Hai bean có thể trỏ tới cùng database server nhưng vẫn không tham gia cùng transaction:

- Dùng hai DataSource pool riêng.
- Dùng hai transaction manager độc lập.
- Một thao tác mở connection mới không được enlist vào transaction hiện tại.
- Dùng propagation REQUIRES_NEW cho một thao tác ghi.
- Writer gọi stored procedure hoặc service thực hiện commit nội bộ.

Do đó, cần kiểm tra transaction manager được truyền vào StepBuilder, DataSource của writer và cấu hình JobRepository. Đặc biệt chú ý propagation của service được gọi từ processor/writer.

Nếu một service dùng REQUIRES_NEW để commit business data trước khi chunk transaction kết thúc, exception sau đó có thể rollback chunk metadata nhưng không rollback business transaction đã commit riêng. Điều này tạo duplicate khi restart trừ khi thao tác idempotent.

## 16. Thứ tự commit và crash window

Một crash có thể xảy ra ở nhiều thời điểm:

| Thời điểm crash | Kết quả mong đợi nếu cùng transaction |
|---|---|
| Trước khi writer ghi | Không có business write/checkpoint của chunk |
| Trong khi writer ghi, trước commit | Transaction rollback khi connection được recovery |
| Sau khi writer ghi nhưng trước transaction commit | Cả business write và checkpoint chưa commit |
| Sau transaction commit | Business write và checkpoint của chunk đã bền vững |
| Sau commit, trước khi job chuyển trạng thái COMPLETED | Chunk vẫn đã commit; job execution có thể cần restart/recovery |

Điểm cần phân biệt: commit chunk không đồng nghĩa toàn job đã COMPLETED. Job có thể dừng sau một chunk đã commit và trước các chunk tiếp theo hoặc trước các step sau. Restart tiếp tục từ checkpoint của step.

Nếu JobRepository và business writer ở hai transaction resource khác nhau, crash window có thể xuất hiện giữa hai lần commit. Khi đó cần idempotency và reconciliation thay vì giả định transaction chunk bao trùm cả hai.

## 17. Idempotent writer là lớp bảo vệ quan trọng

Ngay cả khi transaction được cấu hình đúng, idempotency vẫn hữu ích cho các tình huống như:

- Job được chạy lại có chủ đích.
- Input bị gửi trùng.
- Có side effect ngoài database transaction.
- Writer tích hợp API hoặc storage không transactional.
- Metadata và business database không cùng transaction.
- Operator phải phục hồi một execution có trạng thái không xác định.

Idempotent operation có nghĩa thực hiện lại cùng một business operation không tạo thêm kết quả sai. Cách phổ biến là dùng business key ổn định và unique constraint:

~~~sql
create table processed_order (
    order_id bigint primary key,
    amount decimal(18, 2) not null,
    processed_at timestamp not null
);
~~~

Unique key ngăn một order được insert hai lần. Tuy nhiên, duplicate key có thể làm writer thất bại; ứng dụng cần quyết định đó là lỗi thật hay dấu hiệu item đã được xử lý.

## 18. Upsert và xử lý duplicate có chủ đích

Một số database hỗ trợ upsert hoặc câu lệnh tương đương. Ví dụ SQL theo một dialect cụ thể có thể dùng ON CONFLICT:

~~~sql
insert into processed_order(order_id, amount)
values (:orderId, :amount)
on conflict (order_id)
do update set amount = excluded.amount
~~~

Upsert giúp thao tác lặp lại không tạo thêm row. Nhưng không phải mọi duplicate đều nên ghi đè:

- Nếu payload giống nhau, có thể coi là replay hợp lệ.
- Nếu payload khác nhau, ghi đè có thể che giấu xung đột dữ liệu.
- Nếu record đã được downstream sử dụng, update lại có thể làm thay đổi lịch sử.

Một pattern khác là insert-if-absent hoặc conflict-do-nothing, sau đó xác minh record hiện có có cùng payload/checksum. Hãy chọn semantics phù hợp với business contract và database cụ thể.

## 19. Bảng xử lý theo source key

Đối với import từ file hoặc API, có thể lưu source identity và record key:

~~~sql
create table batch_processed_record (
    source_id varchar(200) not null,
    record_key varchar(200) not null,
    payload_hash varchar(64) not null,
    processed_at timestamp not null,
    primary key (source_id, record_key)
);
~~~

Khi ghi một record:

1. Tính source_id ổn định cho file/snapshot/API batch.
2. Dùng business key của record.
3. Lưu payload hash hoặc version để phát hiện cùng key nhưng nội dung khác.
4. Insert trong cùng transaction với kết quả nghiệp vụ.
5. Nếu key đã tồn tại, xác minh payload hash và xử lý theo duplicate policy.

Bảng này có thể đóng vai trò deduplication ledger. Không dùng JobExecution ID làm source_id nếu restart tạo execution mới nhưng phải nhận diện cùng input.

## 20. Reader checkpoint và writer idempotency bổ trợ nhau

Checkpoint giúp không đọc lại phần đã commit khi reader có state đúng. Idempotency bảo vệ hệ thống khi một item được giao lại hoặc checkpoint không thể đồng bộ hoàn toàn với business side effect.

Hai cơ chế không thay thế nhau:

- Checkpoint không ngăn duplicate từ nguồn có thể redeliver hoặc từ lần reprocess mới.
- Idempotency không giúp reader tìm đúng vị trí tiếp tục và có thể làm job xử lý lại rất nhiều dữ liệu không cần thiết.
- Cùng transaction giúp commit business write và checkpoint nguyên tử.
- Idempotency là lớp bảo vệ khi có retry, replay hoặc ranh giới transaction không đồng nhất.

Một thiết kế bền vững thường kết hợp cả ba: nguồn ổn định, checkpoint transaction-aware và writer idempotent.

## 21. Chunk size ảnh hưởng restart như thế nào?

Chunk size quyết định số item được xử lý trong một transaction:

~~~java
.chunk(100, transactionManager)
~~~

Chunk nhỏ:

- Transaction ngắn hơn.
- Ít item phải rollback khi lỗi.
- Nhiều lần commit và cập nhật metadata hơn.
- Có thể giảm throughput do overhead transaction.

Chunk lớn:

- Ít commit hơn.
- Có thể tăng throughput với workload phù hợp.
- Transaction giữ lock lâu hơn.
- Tốn bộ nhớ hơn.
- Khi rollback, nhiều item phải được xử lý lại.

Chunk size không thay đổi nguyên tắc checkpoint: state chỉ được coi là đã tiến qua chunk khi transaction commit thành công theo cấu hình. Chọn chunk size dựa trên latency, lock, memory, batch throughput và recovery cost.

## 22. Writer không được commit riêng từng item ngoài chunk

Một custom writer có thể bị cám dỗ mở connection và commit mỗi item:

~~~java
for (Order order : chunk) {
    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);
        save(order, connection);
        connection.commit();
    }
}
~~~

Cách này tách mỗi item khỏi transaction của chunk. Nếu item thứ 80 thất bại, 79 item trước có thể đã commit, trong khi chunk metadata chưa được cập nhật. Restart có thể gửi lại cả chunk và tạo duplicate.

Trong chunk-oriented step, ưu tiên dùng JDBC operations tham gia transaction hiện tại. Không tự mở/commit connection riêng trừ khi có thiết kế rõ cho partial commit, idempotency và reconciliation.

## 23. Transaction propagation trong service được gọi từ writer

Nếu writer gọi một service có transaction riêng, cần hiểu propagation:

- REQUIRED thường tham gia transaction hiện tại nếu có.
- REQUIRES_NEW tạo transaction độc lập và suspend transaction hiện tại.
- NOT_SUPPORTED có thể chạy ngoài transaction hiện tại.
- SUPPORTS tham gia nếu có transaction, nếu không thì chạy không transaction.

Một service lưu business row bằng REQUIRES_NEW có thể commit trước khi chunk transaction commit. Nếu writer sau đó thất bại, transaction ngoài rollback nhưng business row vẫn tồn tại.

Hãy giữ thao tác ghi của chunk trong cùng transaction nếu muốn checkpoint và business write cùng commit. Nếu cần commit độc lập, hãy coi đó là side effect có thể lặp và thiết kế idempotency rõ ràng.

## 24. Database trigger và stored procedure

JDBC writer có thể kích hoạt trigger hoặc gọi stored procedure. Cần xác định các thay đổi mà database thực hiện:

- Trigger có ghi sang bảng khác trong cùng database transaction không?
- Procedure có gọi hệ thống ngoài hoặc commit độc lập không?
- Có autonomous transaction hoặc cơ chế tương đương không?
- Procedure có phát message hoặc cập nhật trạng thái không thể rollback?
- Retry có tạo tác dụng phụ trùng không?

Các thay đổi trong cùng database transaction thông thường rollback cùng transaction gọi chúng. Nhưng nếu procedure thực hiện side effect ngoài transaction hoặc dùng autonomous commit, checkpoint không bảo vệ được các side effect đó.

Test restart nên bao gồm behavior thực tế của trigger/procedure, không chỉ test câu SQL writer.

## 25. Xử lý lỗi sau commit nhưng trước khi job hoàn tất

Một job có thể commit nhiều chunk rồi gặp lỗi ở chunk sau:

~~~text
Chunk 1 -> COMMIT
Chunk 2 -> COMMIT
Chunk 3 -> WRITE ERROR -> ROLLBACK
JobExecution -> FAILED
~~~

Khi restart cùng JobInstance:

- Hai chunk đầu được giữ lại.
- Chunk lỗi được xử lý lại theo checkpoint.
- Reader phải tiếp tục tại vị trí tương ứng với chunk đã commit cuối cùng.
- Writer không được tạo duplicate cho dữ liệu đã commit.

Đây là tình huống restart thông thường. Không cần xóa dữ liệu của chunk 1 và 2 nếu transaction/checkpoint đã được lưu đúng và job được thiết kế để tiếp tục.

Nếu nghiệp vụ yêu cầu all-or-nothing cho toàn bộ job, chunk transaction không đủ vì các chunk trước đã commit. Cần ghi vào staging/version riêng rồi publish toàn bộ kết quả sau khi tất cả step hoàn tất.

## 26. Restart sau khi process bị kill

Khi JVM hoặc máy chủ bị kill đột ngột, finally block và close callback có thể không chạy. Database sẽ recovery transaction đang mở theo cơ chế của nó, còn metadata có thể phản ánh execution chưa hoàn tất.

Khi vận hành restart:

1. Xác định JobInstance và JobExecution gần nhất.
2. Kiểm tra transaction đang mở đã được database recovery hay chưa.
3. Kiểm tra trạng thái execution trong JobRepository.
4. Xác định execution có còn được coi là đang chạy hay bị đánh dấu thất bại/dừng.
5. Dùng cơ chế vận hành phù hợp để kết thúc hoặc phục hồi execution stale trước khi restart.
6. Restart cùng identifying parameters khi trạng thái cho phép.
7. Xác minh business data và checkpoint sau khi chạy lại.

Nếu metadata còn STARTED vì process chết trước khi cập nhật status, launch cùng parameters có thể bị từ chối do execution được xem là đang chạy. Không tự sửa bảng metadata bằng SQL tùy tiện. Hãy dùng JobOperator/operations procedure đã được tổ chức phê duyệt hoặc quy trình recovery phù hợp với version và repository schema.

## 27. JobRepository metadata không phải business ledger

JobRepository lưu trạng thái vận hành: job/step execution, execution context, read/write/commit/rollback counts và thông tin restart. Nó không thay thế bảng nghiệp vụ để xác nhận một order đã được xử lý theo business contract.

Ví dụ:

- StepExecution writeCount = 1000 cho biết writer đã ghi số item theo metrics của step.
- Nó không tự chứng minh downstream record còn tồn tại, không bị sửa hoặc đã được external system nhận.
- JobExecution COMPLETED không chứng minh side effect ngoài transaction đã được xác nhận.

Nếu cần audit nghiệp vụ, lưu business key, source identity, payload version và kết quả trong bảng/manifest riêng. Dùng JobRepository để điều khiển lifecycle và restart, dùng business ledger để đối soát nghiệp vụ.

## 28. ExecutionContext chỉ nên lưu restart state cần thiết

ExecutionContext nên chứa dữ liệu nhỏ, có thể serialize và có ý nghĩa khi khôi phục:

- Last processed ID hoặc sort key.
- File byte offset/line number.
- Page number/token.
- Resource index hiện tại.
- Checksum/version của input.
- State nhỏ của custom reader/writer.

Không nên lưu:

- Toàn bộ danh sách item đã đọc.
- Connection, stream hoặc object không serialize được.
- Exception object hoặc payload nhạy cảm.
- Một cache lớn thay cho database.
- State ngẫu nhiên không thể tái tạo.

Nếu state cần nhiều dữ liệu, hãy lưu vào bảng staging/ledger và chỉ giữ key/version trong ExecutionContext.

## 29. saveState(false) và hậu quả

Một số reader/writer có thể tắt lưu state:

~~~java
.saveState(false)
~~~

Điều đó có thể phù hợp nếu step không cần restart hoặc component được thiết kế để bắt đầu lại từ đầu một cách an toàn. Nhưng nếu step phải tiếp tục sau commit, tắt state có thể khiến reader bắt đầu lại từ đầu hoặc không khôi phục được vị trí mong muốn.

Nếu reader đọc lại từ đầu, writer phải có semantics idempotent. Nếu writer không idempotent, restart có thể tạo duplicate. Nếu output là file, cần hiểu writer có truncate, append hay khôi phục resource như thế nào.

Không bật saveState một cách máy móc cho component không hỗ trợ restart; cũng không tắt nó khi quy trình phụ thuộc vào checkpoint. Hãy kiểm tra contract của từng reader/writer.

## 30. JdbcCursorItemReader và restart

JdbcCursorItemReader giữ một cursor JDBC trong quá trình đọc. Khi restart, reader cần khôi phục vị trí theo state được lưu và query phải trả về cùng thứ tự dữ liệu.

Các lưu ý:

- Query phải có ORDER BY xác định.
- Nên có sort key duy nhất.
- Không thay đổi query parameters giữa restart.
- Không để writer làm thay đổi tập kết quả theo cách làm dịch chuyển cursor/checkpoint.
- Kiểm tra driver/database behavior với cursor và transaction.
- Dùng reader name ổn định và saveState nếu cần.

Với dataset rất lớn hoặc nguồn thay đổi, paging theo key có thể dễ kiểm soát hơn cursor/offset, tùy workload và database.

## 31. JdbcPagingItemReader và high-water mark

Paging reader có thể lưu sort key của page để tiếp tục. Tuy nhiên, nếu nguồn liên tục nhận record mới, job có thể không có một điểm kết thúc ổn định hoặc có thể nhìn thấy dữ liệu mới ngoài phạm vi ban đầu.

Một pattern là xác định high-water mark ở đầu job:

~~~sql
select max(order_id) from source_order
~~~

Sau đó mọi page dùng:

~~~sql
where order_id > :lastOrderId
  and order_id <= :highWaterMark
order by order_id
~~~

Syntax giới hạn số dòng phụ thuộc database. Ý tưởng là thứ tự và biên nguồn được cố định, tránh offset bị thay đổi khi các row đã xử lý rời khỏi filter.

High-water mark phải được lưu như identifying job parameter hoặc execution state phù hợp để restart dùng lại cùng giá trị. Nếu tính lại max ID khi restart, phạm vi input có thể thay đổi.

Nếu record cũ có thể được cập nhật hoặc xóa, high-water mark theo ID không tạo snapshot đầy đủ. Cần snapshot isolation, staging key table hoặc versioned source tùy yêu cầu.

## 32. StepExecution metrics sau restart

Sau restart, mỗi StepExecution là một execution mới; các metrics của execution hiện tại cần được hiểu trong ngữ cảnh JobInstance và các execution trước đó.

Không nên chỉ cộng hoặc so sánh một trường count mà không xét restart semantics. Để xác minh kết quả nghiệp vụ:

- Kiểm tra status của từng execution.
- Xác định checkpoint cuối đã commit.
- Đọc business keys trong output table.
- Đếm duplicate theo business key.
- Đối chiếu số item input trong snapshot.
- Kiểm tra skip/filter counts và error ledger.

Metrics giúp vận hành và quan sát, nhưng business reconciliation mới xác nhận tập dữ liệu cuối đúng.

## 33. Restartability của step và flow

Không phải mọi step đều có thể restart theo cùng cách. Step có side effect không idempotent hoặc không có state có thể cần được thiết kế lại.

Các câu hỏi cần trả lời:

- Step có được phép chạy lại sau failure không?
- Step đã COMPLETED có được bỏ qua khi restart job không?
- Có allowStartIfComplete cho step cần chạy lại có chủ đích không?
- Flow có transition theo ExitStatus làm bỏ qua step cần thiết không?
- Step downstream có phụ thuộc output staging của step upstream không?
- Khi một partition thất bại, partition thành công có được giữ và tái sử dụng không?

Không bật allowStartIfComplete chỉ để giải quyết lỗi restart. Nó có thể khiến step đã hoàn tất chạy lại và tạo side effect trùng nếu không idempotent.

## 34. Reprocessing khác restart

Restart tiếp tục một JobInstance thất bại/dừng với cùng identifying parameters và checkpoint đã lưu.

Reprocessing là chạy lại dữ liệu theo một yêu cầu nghiệp vụ mới. Thường cần:

- JobInstance mới hoặc output version mới.
- Xác định input snapshot/version.
- Chính sách xử lý record đã tồn tại.
- Upsert/versioning hoặc bảng kết quả theo lần chạy.
- Quy trình publish kết quả mới.

Không tăng run.id chỉ để restart một job đã lỗi; làm vậy có thể tạo instance mới và đọc từ đầu. Ngược lại, không cố restart một instance đã COMPLETED để thực hiện một lần reprocess mới.

## 35. Transaction isolation và dữ liệu nguồn thay đổi

Isolation level ảnh hưởng những gì reader nhìn thấy trong transaction. Với job chạy lâu, nhiều chunk commit theo thời gian; mỗi chunk có thể thấy snapshot khác nhau tùy database và isolation.

Các vấn đề:

- Record mới được insert giữa hai chunk.
- Record READY bị một process khác cập nhật thành PROCESSED.
- Sort key hoặc filter column bị thay đổi.
- Row bị xóa trước khi reader tới.
- Restart chạy trong snapshot khác với lần đầu.

Nếu cần xử lý đúng một tập dữ liệu cố định, xác định input snapshot hoặc claim set trước. Không giả định một transaction cho từng chunk sẽ giữ cùng một snapshot xuyên suốt toàn job.

## 36. Claiming records và nhiều job đồng thời

Khi nhiều job có thể đọc cùng bảng nguồn, hai job có thể cùng chọn một record READY. Cần một chiến lược claim:

- Cập nhật trạng thái/claim token trong transaction trước khi xử lý.
- Dùng locking phù hợp với database, chẳng hạn skip locked nếu database hỗ trợ và semantics phù hợp.
- Partition theo key không chồng lấn.
- Tạo staging table với unique key cho job/source identity.
- Dùng lease/claim expiry để phục hồi record bị worker chết.

Claim operation phải có tính atomic để hai job không cùng nhận một record. Khi job restart, cần biết claim cũ còn hiệu lực hay đã hết hạn và có thể reclaim an toàn.

Không chỉ dựa vào suffix output hoặc JobExecution ID để tránh hai job xử lý trùng nguồn. Quyền sở hữu input phải được kiểm soát ở database hoặc orchestration layer.

## 37. Transactional outbox khi có side effect bên ngoài

Nếu sau khi ghi database cần gửi event, không nên gọi message broker trực tiếp trong writer rồi giả định transaction database sẽ rollback message khi chunk thất bại.

Transactional outbox pattern:

1. Trong cùng transaction chunk, ghi business row.
2. Trong cùng transaction đó, ghi outbox event với event ID ổn định.
3. Commit database.
4. Một publisher riêng đọc outbox và gửi message.
5. Publisher đánh dấu event đã gửi hoặc consumer deduplicate theo event ID.

Nếu process chết sau khi database commit nhưng trước khi gửi message, outbox vẫn còn event để publisher tiếp tục. Nếu publisher gửi thành công nhưng chết trước khi đánh dấu, có thể gửi lại; consumer cần idempotent.

Đây là cách xử lý crash window giữa database commit và side effect ngoài transaction mà checkpoint Spring Batch không thể tự giải quyết.

## 38. Restart với database writer và file writer cùng step

Nếu một chunk ghi cả database và file, cần kiểm tra hai resource có cùng tham gia transaction hay không. Database transaction không tự rollback một file write thông thường.

Ví dụ:

- Writer ghi database thành công.
- Writer ghi file một phần.
- Chunk gặp lỗi.
- Database rollback nhưng file có thể đã nhận byte.

Hoặc ngược lại, database commit thành công nhưng file flush chưa hoàn tất. Khi restart, có thể tạo file không đồng bộ với bảng dữ liệu.

Các hướng xử lý:

- Ghi file staging theo chunk hoặc theo step, rồi publish sau khi database/job hoàn tất.
- Dùng database làm source of truth và tạo file ở step riêng có thể chạy lại.
- Ghi file theo business key/idempotent artifact strategy.
- Dùng manifest/checksum để xác nhận output hoàn chỉnh.

Không coi việc đặt database và file writer trong cùng CompositeItemWriter là một distributed transaction.

## 39. Restart với stored procedure cập nhật nhiều bảng

Stored procedure có thể ghi nhiều bảng trong một lần gọi. Nếu tất cả thao tác thuộc transaction JDBC hiện tại, rollback có thể hoàn tác các thay đổi đó. Nhưng cần xác minh:

- Procedure có tự commit không?
- Có gọi external service không?
- Có ghi audit bằng autonomous transaction không?
- Có cập nhật sequence/counter ngoài rollback semantics không?
- Procedure có idempotent khi gọi lại cùng business key không?

Test restart cần kiểm tra trạng thái cuối của tất cả bảng liên quan, không chỉ bảng chính. Một stored procedure có thể tạo side effect ẩn mà unit test writer không nhìn thấy.

## 40. Xử lý duplicate key sau restart

Nếu restart gửi lại item đã commit do transaction/resource không đồng bộ, unique constraint có thể phát hiện duplicate. Đây là một tín hiệu hữu ích nhưng cần policy:

- Nếu row đã tồn tại với cùng payload, xác minh và coi như đã xử lý nếu contract cho phép.
- Nếu row đã tồn tại với payload khác, báo conflict.
- Nếu duplicate do source chứa record lặp, ghi nhận vào error ledger.
- Nếu duplicate do retry sau timeout, dùng idempotency key để phân biệt.

Không catch DuplicateKeyException rồi bỏ qua tất cả. Làm vậy có thể che giấu xung đột business data hoặc constraint sai.

## 41. Ví dụ test restart sau khi chunk đã commit

Một integration test nên mô phỏng:

1. Reader cung cấp một tập item có business key ổn định.
2. Writer ghi chunk đầu vào database.
3. Chunk đầu commit.
4. Một test double làm chunk sau thất bại có chủ đích.
5. JobExecution đầu có trạng thái FAILED.
6. Restart cùng identifying parameters.
7. Reader tiếp tục từ checkpoint đã commit.
8. Writer ghi phần còn lại.
9. Query database và xác nhận mỗi business key có đúng một kết quả.

Có thể dùng writer test double hoặc processor ném exception theo một key để tạo failure có kiểm soát. Không dùng sleep hoặc timing race để hy vọng process dừng đúng sau commit.

## 42. Ví dụ kiểm tra business rows sau restart

Sau khi restart hoàn tất, test nên kiểm tra dữ liệu thực tế:

~~~java
List<Long> orderIds = jdbcTemplate.queryForList(
        "select order_id from processed_order order by order_id",
        Long.class);

assertEquals(List.of(1001L, 1002L, 1003L, 1004L), orderIds);

Integer duplicates = jdbcTemplate.queryForObject("""
        select count(*)
        from (
            select order_id
            from processed_order
            group by order_id
            having count(*) > 1
        ) duplicate_orders
        """, Integer.class);

assertEquals(0, duplicates);
~~~

Ví dụ giả định order_id là business key duy nhất và database cho phép query dạng này. Với schema thực tế, hãy kiểm tra cả payload/version, không chỉ số lượng row.

## 43. Kiểm tra JobRepository state

Integration test cũng có thể kiểm tra metadata:

- JobInstance của hai execution giống nhau.
- JobExecution đầu FAILED hoặc trạng thái phù hợp với cách test tạo failure.
- JobExecution restart có ID mới.
- StepExecution restart sử dụng checkpoint đã lưu.
- ExecutionContext chứa reader/writer state mong đợi.
- Step cuối COMPLETED.

Không phụ thuộc quá sâu vào tên key nội bộ do reader framework tạo nếu không phải public contract. Với custom reader, có thể kiểm tra key do ứng dụng định nghĩa. Với reader có sẵn, ưu tiên xác nhận hành vi qua item tiếp theo và output cuối.

## 44. Test commit boundary bằng failure injection

Để xác minh transaction, có thể tạo failure injection tại các điểm:

- Trước writer.
- Sau khi writer gọi JDBC nhưng trước khi chunk commit.
- Sau khi một chunk commit và trước chunk kế tiếp.
- Trong ItemStream.update.
- Trong bước sau cùng khi JobExecution chuyển trạng thái.

Mục tiêu là xác nhận business data và checkpoint cùng rollback/commit theo transaction design. Failure injection cần deterministic, ví dụ test double có bộ đếm hoặc hook được bật bằng test configuration.

Không thêm production code chỉ để test một timing window nếu có thể dùng test double hoặc transaction synchronization phù hợp. Test phải kiểm tra dữ liệu database và checkpoint sau failure, không chỉ kiểm tra exception được ném.

## 45. Xử lý execution stale sau crash

Khi process chết, metadata có thể vẫn ghi STARTED. Trước khi restart, operator cần xác định:

- Process cũ thực sự đã dừng chưa?
- Có worker/partition nào vẫn còn chạy không?
- Database đã recovery transaction đang mở chưa?
- Output staging còn resource dở dang nào?
- Execution context cuối cùng có được commit không?
- Có side effect ngoài transaction đang ở trạng thái không xác định không?

Không đánh dấu execution FAILED bằng SQL trực tiếp trong production trừ khi đó là quy trình recovery được thiết kế và kiểm soát. Thay đổi metadata sai có thể làm JobRepository mất khả năng điều phối restart.

## 46. Restart và file/database output version

Nếu job tạo cả dữ liệu database lẫn artifact file, hãy gắn chúng với cùng output identity:

~~~text
jobKey = orders:2026-11-15:tenant-42:v1
database batch_key = orders:2026-11-15:tenant-42:v1
staging file = orders-2026-11-15-tenant-42-v1.tmp
published file = orders-2026-11-15-tenant-42-v1.csv
~~~

Restart cùng JobInstance tiếp tục staging artifact và database batch key đó. Reprocess có chủ đích tạo version mới. Downstream chỉ đọc output đã publish sau khi kiểm tra database/file/manifest đồng bộ.

## 47. Các lỗi thường gặp

| Tình huống | Nguyên nhân | Cách xử lý |
|---|---|---|
| Restart ghi duplicate rows | Business write commit riêng checkpoint hoặc reader đọc lại từ đầu | Cùng transaction resource, save state và idempotent writer |
| Restart bỏ sót item | Checkpoint commit trước business data hoặc input thay đổi | Đồng bộ transaction và cố định input snapshot |
| Job tạo JobInstance mới khi restart | Thêm identifying parameter/run ID mới | Dùng lại identifying parameters cũ |
| Reader đọc lại toàn bộ file | Tắt saveState hoặc reader không lưu state | Bật state và triển khai ItemStream đúng |
| Reader bỏ qua record khi paging | Sort key không duy nhất hoặc query thay đổi | Dùng stable unique key/high-water mark |
| Dữ liệu đã commit nhưng job còn FAILED | Job lỗi ở chunk/step sau commit trước đó | Restart từ checkpoint, không xóa chunk đã commit |
| Database rollback nhưng API vẫn bị gọi | API side effect ngoài transaction | Idempotency key, outbox hoặc reconciliation |
| Cùng database nhưng checkpoint lệch | Writer mở connection/transaction riêng | Kiểm tra DataSource, transaction manager và propagation |
| Restart không mở được execution | Metadata vẫn STARTED sau process crash | Dùng quy trình recovery/JobOperator phù hợp |
| Chunk lớn phải làm lại quá nhiều item | Chunk size quá lớn cho recovery cost | Điều chỉnh chunk size theo throughput và rollback |
| Reprocess ghi đè kết quả cũ | Dùng chung business key/output path | Version hóa output và quy định upsert |
| Duplicate key bị bỏ qua âm thầm | Catch DuplicateKeyException quá rộng | So sánh payload/version và phân loại duplicate |
| File không khớp database | File writer không transactional với database | Staging, publish riêng và manifest |
| Step đã hoàn tất chạy lại ngoài ý muốn | Cấu hình allowStartIfComplete hoặc flow không phù hợp | Xác định restart/reprocess semantics của step |

## 48. Quy trình thiết kế restart sau database commit

1. **Xác định transaction boundary:** writer và JobRepository có dùng cùng transaction manager/resource không?
2. **Kiểm tra writer:** JDBC connection có tham gia transaction chunk hay tự commit riêng?
3. **Bật checkpoint:** reader/writer có hỗ trợ ItemStream và saveState phù hợp không?
4. **Đặt tên component ổn định:** reader/writer name không thay đổi giữa restart.
5. **Giữ JobInstance:** restart dùng cùng identifying JobParameters.
6. **Ổn định input:** giữ file, query, high-water mark và sort order tương ứng checkpoint.
7. **Thiết kế business key:** unique constraint hoặc dedup ledger bảo vệ việc ghi lặp.
8. **Xử lý external side effect:** dùng outbox/idempotency/staging thay vì giả định rollback phân tán.
9. **Kiểm soát chunk size:** cân bằng commit overhead, lock và recovery cost.
10. **Lập quy trình crash recovery:** xác định cách xử lý execution stale và output dở dang.
11. **Test failure sau commit:** restart cùng instance và xác minh không mất/trùng dữ liệu.
12. **Đối soát kết quả:** kiểm tra business rows, checkpoint, error ledger và output manifest.

## 49. Những nguyên tắc cần nhớ

- Restart tiếp tục một JobInstance bằng JobExecution mới; dùng lại identifying JobParameters.
- Chunk commit bao gồm business data và checkpoint khi chúng tham gia cùng transaction.
- JobRepository lưu metadata và ExecutionContext; nó không thay thế business ledger.
- Reader/writer cần lưu state qua ItemStream nếu phải tiếp tục đúng vị trí.
- Giữ reader name, writer name, input resource, query, sort key và cấu hình rollover ổn định qua restart.
- Cùng một database server chưa chắc có cùng transaction; kiểm tra DataSource, transaction manager và propagation.
- Nếu JobRepository và business writer ở hai resource độc lập, phải xử lý crash window bằng idempotency và reconciliation.
- JdbcPagingItemReader cần sort key ổn định, tốt nhất là duy nhất; input query phải có phạm vi cố định.
- Tránh đọc và cập nhật cùng bảng theo cách làm dịch chuyển tập kết quả; cân nhắc keyset paging, high-water mark hoặc claim set.
- Unique constraint, business key và payload hash giúp phát hiện hoặc xử lý duplicate có chủ đích.
- Upsert không nên ghi đè xung đột payload mà không có business rule.
- Chunk size quyết định transaction và recovery cost; không phải số item của toàn job.
- Không tự commit từng item ngoài chunk nếu muốn checkpoint và business write atomic.
- Side effect ngoài transaction cần outbox, idempotency key, staging hoặc reconciliation.
- Restart khác reprocessing; reprocess cần output identity/version mới và policy cho dữ liệu đã tồn tại.
- Sau crash, execution metadata có thể stale; dùng quy trình recovery được kiểm soát.
- Test phải gây failure có chủ đích, restart cùng JobInstance và kiểm tra dữ liệu thực tế không mất/trùng.

Restart sau khi commit database an toàn khi trạng thái dữ liệu nghiệp vụ và checkpoint được quản lý nhất quán. Dùng cùng transaction resource cho JDBC writer và JobRepository khi có thể, giữ nguồn đọc ổn định, lưu reader state đúng và bảo vệ business key bằng idempotency. Với side effect nằm ngoài transaction, cần thêm outbox, staging hoặc reconciliation để job có thể phục hồi mà không tạo duplicate hay bỏ sót dữ liệu.
