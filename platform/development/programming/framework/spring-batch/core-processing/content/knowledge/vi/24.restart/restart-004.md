# Restart từ chunk checkpoint

Trong Spring Batch, một chunk-oriented Step thường xử lý dữ liệu theo từng nhóm item trong transaction riêng. Sau khi một chunk được ghi thành công và transaction commit, Spring Batch lưu trạng thái thực thi để biết reader đã đi đến đâu. Trạng thái đã lưu tại ranh giới commit này được gọi là **checkpoint**.

Nếu Job bị lỗi hoặc process dừng giữa chừng, lần restart có thể dùng checkpoint gần nhất để tiếp tục từ phần dữ liệu chưa hoàn tất. Nhờ vậy, Step không phải xử lý lại toàn bộ input từ đầu. Cơ chế này chỉ hoạt động đúng khi reader hỗ trợ lưu và khôi phục trạng thái, Job được restart trong cùng JobInstance và dữ liệu nguồn vẫn phù hợp với checkpoint đã lưu.

## 1. Chunk và checkpoint liên hệ với nhau như thế nào?

Chunk-oriented processing đọc item từ ItemReader, xử lý bằng ItemProcessor và ghi một nhóm item bằng ItemWriter. Một chunk thường nằm trong một transaction:

~~~text
Chunk 1
  |
  +-- Reader đọc item
  +-- Processor xử lý
  +-- Writer ghi dữ liệu
  +-- Lưu trạng thái reader / ExecutionContext
  |
  +-- COMMIT
  |
  v
Chunk 2
  |
  +-- Reader đọc item tiếp theo
  +-- Processor xử lý
  +-- Writer ghi dữ liệu
  +-- Lưu trạng thái reader / ExecutionContext
  |
  +-- COMMIT
~~~

Checkpoint là trạng thái khôi phục được lưu tại ranh giới commit. Với reader có hỗ trợ restart, trạng thái thường mô tả vị trí tiếp theo cần đọc, chẳng hạn:

- Số dòng đã đọc trong file.
- Vị trí byte hoặc record tiếp theo.
- Trang tiếp theo trong paging reader.
- Khóa cuối cùng đã đọc trong truy vấn có thứ tự.
- Một token hoặc offset mà nguồn dữ liệu cho phép khôi phục.

Checkpoint không phải bản sao toàn bộ item trong chunk. Nó là thông tin đủ để reader mở lại nguồn và tiếp tục từ vị trí phù hợp.

## 2. Ví dụ restart sau khi một chunk thất bại

Giả sử Job đọc file có 1.000 dòng và chunk size bằng 100:

~~~text
Chunk 1: dòng 1-100       -> COMMIT
Chunk 2: dòng 101-200     -> COMMIT
Chunk 3: dòng 201-300     -> COMMIT
Chunk 4: dòng 301-400     -> lỗi -> ROLLBACK
Chunk 5: dòng 401-500     -> chưa chạy

Checkpoint bền vững gần nhất: sau dòng 300
~~~

Khi chunk 4 thất bại, các thay đổi thuộc transaction của chunk đó được rollback theo transaction policy. Checkpoint đã commit sau chunk 3 vẫn còn. Khi restart cùng JobInstance, reader có thể khôi phục vị trí sau dòng 300 và đọc lại các dòng 301 trở đi.

Các chunk 1, 2 và 3 đã commit không cần được xử lý lại trong trường hợp Step, reader và transaction được cấu hình đúng. Chunk thất bại được thực hiện lại vì checkpoint chưa tiến qua chunk đó.

Đây là nguyên tắc quan trọng: **restart tiếp tục từ checkpoint đã commit gần nhất, không phải từ item cuối cùng mà reader từng trả về trước khi process dừng**.

## 3. JobInstance và điều kiện restart

Spring Batch phân biệt JobInstance và JobExecution:

| Khái niệm | Ý nghĩa |
| --- | --- |
| JobInstance | Một lần xử lý logic, được xác định bởi Job name và identifying JobParameters |
| JobExecution | Một lần chạy cụ thể của JobInstance |
| StepExecution | Một lần thực thi cụ thể của Step trong JobExecution |

Restart tạo JobExecution mới nhưng thuộc cùng JobInstance. Vì vậy, phải giữ nguyên Job name và các identifying JobParameters của lần chạy cần tiếp tục.

Ví dụ lần chạy đầu:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFileId", "orders-2026-11-15", true)
        .addString("businessDate", "2026-11-15", true)
        .toJobParameters();
~~~

Lần restart phải dùng cùng các identifying values:

~~~java
JobExecution restartedExecution =
        jobLauncher.run(importOrdersJob, parameters);
~~~

Nếu thêm một identifying timestamp hoặc UUID mới, Spring Batch có thể tạo JobInstance mới. Instance mới không dùng checkpoint của instance cũ và có thể bắt đầu xử lý input từ đầu.

Restart thường chỉ khả dụng khi JobExecution trước đã kết thúc ở trạng thái có thể restart, chẳng hạn FAILED hoặc STOPPED, và Job không bị cấu hình **preventRestart()**. JobInstance đã COMPLETED thường không thể chạy lại bằng cùng identifying parameters.

## 4. ExecutionContext lưu checkpoint ở đâu?

Spring Batch dùng ExecutionContext để lưu trạng thái key-value cần thiết cho việc tiếp tục Job hoặc Step. Có hai phạm vi phổ biến:

- **JobExecutionContext:** trạng thái gắn với toàn JobExecution.
- **StepExecutionContext:** trạng thái gắn với một StepExecution cụ thể.

Checkpoint của reader trong chunk Step thường nằm trong StepExecutionContext. JobRepository lưu metadata của JobExecution, StepExecution và ExecutionContext để có thể khôi phục khi restart.

Ví dụ một reader có thể lưu:

~~~java
executionContext.putLong("lastProcessedOrderId", 125000L);
executionContext.putInt("nextPage", 26);
~~~

Các key cần ổn định và có ý nghĩa rõ ràng. Chỉ lưu dữ liệu nhỏ, có thể serialize và cần thiết để khôi phục. Không lưu connection, stream object, service object, toàn bộ item list hoặc payload lớn vào ExecutionContext.

Không nên tự suy ra checkpoint chỉ từ readCount, writeCount hoặc commitCount. Những counter này giúp quan sát tiến độ, nhưng không phải lúc nào cũng đủ để reader tái tạo vị trí chính xác, nhất là khi có filter, skip, retry hoặc reader có logic phức tạp.

## 5. ItemStream cung cấp cơ chế lưu và khôi phục

Các reader và writer cần lưu trạng thái thường triển khai ItemStream. Vòng đời gồm ba phương thức:

- open(ExecutionContext): đọc trạng thái đã lưu để khôi phục resource.
- update(ExecutionContext): ghi trạng thái hiện tại vào ExecutionContext.
- close(): giải phóng resource khi Step kết thúc.

Trong chunk processing, Spring Batch gọi cơ chế cập nhật trạng thái của các stream tại ranh giới chunk trước khi commit. Khi transaction commit thành công, checkpoint tương ứng được lưu bền vững theo cấu hình JobRepository và transaction manager.

~~~text
ItemStream.open(context)
       |
       v
Đọc / xử lý một chunk
       |
       v
ItemStream.update(context)
       |
       v
JobRepository lưu StepExecutionContext
       |
       v
COMMIT transaction
       |
       v
Checkpoint mới có hiệu lực
~~~

Nếu transaction rollback, checkpoint của chunk chưa hoàn tất không được xem là checkpoint đã commit. Reader sẽ được khôi phục từ trạng thái gần nhất đã lưu thành công.

### Reader cần được đăng ký như một stream

Các reader có sẵn được cấu hình qua StepBuilder thường được framework nhận diện và quản lý vòng đời ItemStream. Nếu reader được bọc trong decorator, composite hoặc được tạo gián tiếp, hãy bảo đảm stream delegate được đăng ký đúng. Nếu open, update và close không được gọi, checkpoint có thể không được lưu dù class có triển khai ItemStream.

## 6. Restart với FlatFileItemReader

FlatFileItemReader hỗ trợ lưu trạng thái đọc. Khi dùng builder, đặt tên ổn định và bật saveState:

~~~java
@Bean
@StepScope
public FlatFileItemReader<OrderInput> orderFileReader(
        @Value("#{jobParameters['inputFile']}") Resource inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderFileReader")
            .resource(inputFile)
            .delimited()
            .names("orderId", "customerCode", "quantity", "unitPrice")
            .targetType(OrderInput.class)
            .saveState(true)
            .build();
}
~~~

name("orderFileReader") tạo namespace ổn định cho các key trạng thái của reader trong ExecutionContext. saveState(true) cho phép reader lưu tiến độ để restart.

Khi Step chạy lần đầu, reader mở file và cập nhật vị trí đọc theo từng chunk. Khi restart, reader đọc lại trạng thái đã lưu và tiếp tục từ vị trí tương ứng.

### Input file phải ổn định

Checkpoint theo dòng hoặc vị trí file chỉ có ý nghĩa khi input không bị thay đổi giữa lần chạy đầu và restart. Nếu file bị thay thế, chèn dòng hoặc xóa dòng trước vị trí checkpoint, reader có thể bỏ sót hoặc đọc trùng dữ liệu.

Nên dùng file bất biến theo batch, tên file hoặc input ID có version, checksum hoặc metadata nhận diện. Nếu file đầu vào đã thay đổi, cần xác định đó là một lần xử lý nghiệp vụ mới với JobParameters phù hợp, thay vì áp checkpoint cũ vào nội dung khác.

## 7. Restart với JdbcPagingItemReader

Với database paging reader, checkpoint thường gắn với trạng thái trang và sort key. Truy vấn cần có thứ tự ổn định để reader tiếp tục đúng vị trí.

Ví dụ:

~~~java
@Bean
@StepScope
public JdbcPagingItemReader<Order> orderPagingReader(
        DataSource dataSource,
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    return new JdbcPagingItemReaderBuilder<Order>()
            .name("orderPagingReader")
            .dataSource(dataSource)
            .selectClause(
                    "select order_id, customer_code, total_amount")
            .fromClause("from orders")
            .whereClause("where business_date = :businessDate")
            .parameterValues(Map.of("businessDate", businessDate))
            .sortKeys(Map.of("order_id", Order.ASCENDING))
            .rowMapper(new OrderRowMapper())
            .pageSize(100)
            .saveState(true)
            .build();
}
~~~

Trong ví dụ, order_id là sort key ổn định và cần xác định thứ tự duy nhất cho tập dữ liệu được đọc. Nếu sort key không duy nhất, các bản ghi có cùng giá trị có thể được phân trang không nhất quán. Hãy dùng khóa ghép hoặc một unique key làm tie-breaker.

### Dữ liệu nguồn thay đổi trong lúc Job chạy

Ngay cả khi sort key ổn định, việc thêm hoặc xóa bản ghi trong phạm vi truy vấn có thể ảnh hưởng đến paging. Ví dụ, nếu một bản ghi mới được chèn trước vị trí đã lưu, offset/page checkpoint có thể không còn đại diện cho cùng tập dữ liệu.

Các cách giảm rủi ro:

- Đọc từ một snapshot hoặc tập dữ liệu được đóng băng cho batch.
- Dùng watermark hoặc cutoff cố định, chẳng hạn created_at <= :batchCutoff.
- Dùng keyset pagination với khóa duy nhất và điều kiện key > lastKey.
- Lưu version hoặc ID của input dataset trong JobParameters.
- Đảm bảo các điều kiện lọc không đổi giữa lần chạy đầu và restart.

## 8. Custom ItemStreamReader tự lưu checkpoint

Nếu reader tự xây dựng, cần triển khai ItemStream và lưu đủ trạng thái để khôi phục vị trí. Ví dụ dưới đây dùng chỉ số item để minh họa:

~~~java
public class IndexedOrderReader
        implements ItemStreamReader<OrderInput> {

    private static final String NEXT_INDEX =
            "indexedOrderReader.nextIndex";

    private final List<OrderInput> items;
    private int nextIndex;

    public IndexedOrderReader(List<OrderInput> items) {
        this.items = items;
    }

    @Override
    public void open(ExecutionContext context) {
        nextIndex = context.containsKey(NEXT_INDEX)
                ? context.getInt(NEXT_INDEX)
                : 0;
    }

    @Override
    public OrderInput read() {
        if (nextIndex >= items.size()) {
            return null;
        }

        return items.get(nextIndex++);
    }

    @Override
    public void update(ExecutionContext context) {
        context.putInt(NEXT_INDEX, nextIndex);
    }

    @Override
    public void close() {
        // Đóng resource nếu reader đang giữ file hoặc connection.
    }
}
~~~

Ví dụ này cho thấy:

1. open khôi phục nextIndex từ checkpoint.
2. read trả item kế tiếp và tăng vị trí nội bộ.
3. update lưu vị trí tiếp theo vào ExecutionContext.
4. close giải phóng resource.

Trong ứng dụng thật, không nên nạp toàn bộ dữ liệu lớn vào List như ví dụ. Reader nên lưu offset, page, khóa hoặc token mà nguồn dữ liệu hỗ trợ. Key ExecutionContext phải duy nhất cho reader trong Step.

Reader custom cũng cần được đăng ký trong Step như một ItemStream. Nếu reader được bọc bởi một decorator không chuyển tiếp ItemStream lifecycle, cần đăng ký delegate stream rõ ràng để checkpoint hoạt động.

## 9. saveState và reader không hỗ trợ restart

Nhiều reader/writer có tùy chọn saveState. Khi bật, thành phần lưu trạng thái vào ExecutionContext. Khi tắt bằng saveState(false), thành phần không lưu checkpoint riêng.

Ví dụ:

~~~java
new FlatFileItemReaderBuilder<OrderInput>()
        .name("orderFileReader")
        .resource(inputFile)
        .delimited()
        .names("orderId", "quantity")
        .targetType(OrderInput.class)
        .saveState(false)
        .build();
~~~

Khi saveState(false), không thể mong reader tự tiếp tục từ vị trí cũ sau restart. Reader có thể bắt đầu lại từ đầu hoặc cần một cơ chế phục hồi khác do ứng dụng cung cấp.

Chỉ tắt saveState khi:

- Reader không cần restart vì Step được thiết kế chạy lại toàn bộ một cách an toàn.
- Nguồn dữ liệu có cơ chế checkpoint độc lập.
- Ứng dụng tự quản lý vị trí đọc bằng một kho trạng thái bền vững khác.

Nếu reader có trạng thái nhưng không lưu, Step có thể restart sai vị trí và tạo dữ liệu trùng hoặc bỏ sót.

## 10. Chunk size ảnh hưởng đến checkpoint

Checkpoint thường được lưu ở ranh giới chunk, nên chunk size ảnh hưởng đến tần suất lưu tiến độ và lượng công việc có thể phải đọc lại.

| Chunk size | Tần suất commit/checkpoint | Hệ quả khi lỗi |
| --- | --- | --- |
| Nhỏ | Thường xuyên hơn | Ít item chưa commit hơn có thể phải xử lý lại |
| Lớn | Ít thường xuyên hơn | Nhiều item hơn có thể thuộc chunk chưa commit |

Ví dụ với 10.000 item:

- Chunk size 100 tạo khoảng 100 chunk.
- Chunk size 500 tạo khoảng 20 chunk.
- Chunk size 1.000 tạo khoảng 10 chunk.

Đây là số chunk lý thuyết nếu không có filter, skip hoặc yếu tố làm thay đổi số item. Chunk nhỏ tăng số lần commit và ghi metadata. Chunk lớn có thể tăng throughput nhưng làm transaction dài, giữ nhiều item trong memory và tăng lượng việc phải làm lại khi chunk thất bại.

Không nên chọn chunk size chỉ dựa trên số lần commit. Hãy cân bằng throughput, transaction duration, memory, tần suất checkpoint và chi phí restart.

## 11. Checkpoint và transaction phải nhất quán

Để restart an toàn, checkpoint phải phản ánh dữ liệu nghiệp vụ đã commit. Trong cấu hình phổ biến, dữ liệu nghiệp vụ và metadata của JobRepository cùng tham gia một transaction hoặc được phối hợp theo cách bảo đảm tính nhất quán.

~~~text
Một chunk transaction
    |
    +-- Writer ghi dữ liệu nghiệp vụ
    |
    +-- ItemStream.update(context)
    |
    +-- JobRepository lưu checkpoint
    |
    +-- COMMIT
~~~

Nếu dữ liệu nghiệp vụ commit nhưng checkpoint không commit, restart có thể đọc lại item và ghi trùng. Nếu checkpoint commit nhưng dữ liệu nghiệp vụ rollback, reader có thể bỏ qua item chưa được ghi.

Rủi ro này cần được xem xét khi:

- JobRepository và dữ liệu nghiệp vụ nằm ở hai database.
- Dùng hai transaction manager độc lập.
- Reader/writer ghi sang hệ thống ngoài transaction của Step.
- Metadata được cập nhật qua một transaction khác.

Không thể giả định hai thao tác atomic chỉ vì chúng được gọi trong cùng một phương thức Java. Nếu không có transaction chung, hãy thiết kế writer idempotent, unique business key, inbox/outbox, staging hoặc cơ chế đối soát.

## 12. Retry, skip và checkpoint

Retry và skip ảnh hưởng đến cách chunk được hoàn tất:

- **Retry:** thử lại thao tác thất bại theo retry policy. Chunk có thể rollback trước khi framework thử lại.
- **Skip:** bỏ qua exception được chính sách cho phép; chunk có thể tiếp tục và commit nếu vẫn hợp lệ.
- **Rollback:** loại bỏ thay đổi chưa commit của transaction hiện tại.

Ví dụ:

~~~text
Chunk 1: item 1-100 -> COMMIT
Chunk 2: item 101-200 -> lỗi tại item 145
       |
       +-- Retry: thử lại theo retry policy
       |
       +-- Skip: bỏ item lỗi nếu policy cho phép
       |
       +-- Fail: rollback chunk và Step thất bại
~~~

Nếu chunk 2 rollback và Step thất bại, checkpoint gần nhất vẫn là sau item 100. Khi restart, reader có thể đọc lại từ item 101. Nếu item 145 được skip và chunk 2 hoàn tất, checkpoint của chunk được commit cùng trạng thái skip.

Không nên suy ra vị trí restart chỉ từ readCount. Với filter, skip, retry hoặc writer lỗi, số item đã đọc có thể khác vị trí checkpoint và số item đã ghi. Reader phải khôi phục từ trạng thái mà chính nó lưu.

## 13. Step đã COMPLETED và Step bị FAILED

Restart Job không có nghĩa tất cả Step đều chạy lại từ đầu:

- Step đã COMPLETED thường được bỏ qua.
- Step FAILED hoặc STOPPED có thể được thực hiện lại nếu Job cho phép restart.
- Chunk Step bị lỗi có thể khôi phục từ checkpoint đã lưu gần nhất.
- allowStartIfComplete(true) cho phép một Step đã hoàn tất được chạy lại trong lần restart.

Ví dụ:

~~~text
Lần chạy đầu:
  prepareInputStep  -> COMPLETED
  importOrdersStep  -> FAILED (checkpoint sau chunk 3)
  publishReportStep -> chưa chạy

Restart:
  prepareInputStep  -> bỏ qua
  importOrdersStep  -> tiếp tục sau checkpoint chunk 3
  publishReportStep -> chạy sau khi import hoàn tất
~~~

Nếu cần restart cùng JobInstance, giữ nguyên Job name và identifying JobParameters. Nếu thay đổi identifying parameters, Spring Batch có thể tạo instance mới và không sử dụng checkpoint cũ.

## 14. Checkpoint của partitioned Step

Với partitioning, mỗi worker StepExecution có ExecutionContext riêng. Mỗi partition có checkpoint riêng để có thể tiếp tục phạm vi dữ liệu của nó.

Ví dụ:

~~~text
Master Step
  |
  +-- partition0: COMPLETED
  |       checkpoint riêng
  |
  +-- partition1: FAILED
  |       checkpoint sau chunk 4
  |
  +-- partition2: COMPLETED
          checkpoint riêng
~~~

Khi restart, Spring Batch có thể bỏ qua partition đã hoàn tất và thực hiện lại partition thất bại từ checkpoint của worker nếu cấu hình và metadata ổn định.

Để cơ chế này hoạt động:

- Tên partition cần ổn định.
- Partitioner phải tái tạo phạm vi tương ứng với lần chạy đầu.
- Worker reader phải lưu checkpoint riêng.
- Không thay đổi mapping partition khi JobInstance cũ còn cần restart.
- Side effect của partition phải idempotent vì chunk cuối cùng có thể được thực hiện lại.

Nếu Partitioner dựa trên dữ liệu nguồn đang thay đổi, restart có thể tạo phạm vi khác. Nên dùng input snapshot, watermark hoặc tham số định danh dữ liệu để bảo đảm partition mapping nhất quán.

## 15. Side effect và xử lý lại item

Rollback transaction database không tự hoàn tác side effect bên ngoài như:

- Gọi REST API.
- Gửi email hoặc thông báo.
- Publish message sang broker khác.
- Ghi hoặc di chuyển file.
- Gọi dịch vụ thanh toán.

Ví dụ, processor hoặc writer đã gửi request đến hệ thống ngoài rồi transaction database rollback. Khi restart từ checkpoint, item có thể được xử lý lại và request được gửi lần thứ hai.

Các cách giảm rủi ro:

- Dùng idempotency key ổn định theo business key hoặc item ID.
- Dùng unique constraint để ngăn ghi dữ liệu trùng.
- Dùng outbox để ghi yêu cầu phát message cùng transaction database.
- Ghi trạng thái operation vào kho bền vững.
- Tách side effect ra Step riêng sau khi dữ liệu chính đã commit.
- Dùng compensation nếu nghiệp vụ cho phép và không thể rollback trực tiếp.

Không nên giả định checkpoint tự bảo đảm exactly-once cho mọi hệ thống ngoài. Checkpoint chỉ mô tả tiến độ của Step; side effect phải có cơ chế nhất quán riêng.

## 16. Quan sát checkpoint và lịch sử restart

JobExplorer cho phép tra cứu JobExecution và StepExecution để xem trạng thái thực thi:

~~~java
JobExecution execution =
        jobExplorer.getJobExecution(jobExecutionId);

if (execution != null) {
    for (StepExecution stepExecution : execution.getStepExecutions()) {
        log.info(
                "step={}, status={}, read={}, write={}, commits={}, rollbacks={}",
                stepExecution.getStepName(),
                stepExecution.getStatus(),
                stepExecution.getReadCount(),
                stepExecution.getWriteCount(),
                stepExecution.getCommitCount(),
                stepExecution.getRollbackCount());
    }
}
~~~

Khi điều tra một lần restart, cần xem:

- JobInstance ID và identifying JobParameters.
- JobExecution trước đó có FAILED hoặc STOPPED không.
- StepExecution nào thất bại.
- Commit count và rollback count.
- Reader có lưu ExecutionContext không.
- Checkpoint key và giá trị đã lưu.
- Input file, snapshot hoặc query filter có còn giống lần chạy đầu không.
- Có side effect nào đã xảy ra ngoài transaction không.

Read count, write count và commit count giúp hiểu tiến độ, nhưng không thay thế nội dung checkpoint. Nếu cần xem ExecutionContext, dùng API hoặc công cụ quản trị phù hợp; không tự sửa trực tiếp metadata đã serialize trong JobRepository.

## 17. Những lỗi thường gặp

### Reader không triển khai ItemStream

Custom reader không lưu trạng thái thì Spring Batch không có vị trí để khôi phục. Hãy triển khai ItemStream hoặc dùng reader có sẵn hỗ trợ restart.

### Tắt saveState nhưng mong restart tiếp tục

Với saveState(false), reader không lưu checkpoint của chính nó. Cần một cơ chế phục hồi khác trước khi tắt.

### Đổi tên reader giữa các lần chạy

Tên reader có thể được dùng để tạo key trong ExecutionContext. Đổi tên có thể làm reader không tìm thấy checkpoint cũ. Giữ tên ổn định trong vòng đời JobInstance cần restart.

### Thay input file nhưng giữ checkpoint cũ

Checkpoint theo dòng hoặc offset có thể trỏ sai vị trí nếu file thay đổi. Dùng input ID/version hoặc tạo JobInstance mới cho tập dữ liệu mới.

### Query paging không có sort key duy nhất

Thứ tự không ổn định có thể khiến phân trang đọc trùng hoặc bỏ sót item. Dùng ORDER BY với unique key hoặc khóa ghép.

### Nhầm readCount với checkpoint

Filter, skip và retry làm số lượng item đã đọc khác với vị trí tiếp tục. Dùng ExecutionContext của reader thay vì tự tính vị trí từ counter.

### Checkpoint và dữ liệu nghiệp vụ commit độc lập

Hai phía có thể lệch nhau khi restart, dẫn đến bỏ sót hoặc ghi trùng. Dùng transaction chung nếu phù hợp hoặc thiết kế idempotency và đối soát.

### Cho rằng mọi item của chunk lỗi đều đã mất

Chunk chưa commit được xử lý lại từ checkpoint gần nhất. Dữ liệu của chunk đó có thể phải đọc và xử lý lại, trong khi các chunk đã commit vẫn tồn tại.

### Không bảo vệ side effect ngoài transaction

API, message hoặc file có thể đã được tạo trước rollback. Dùng idempotency key, outbox hoặc compensation.

### Thay identifying JobParameters khi restart

Tham số mới có thể tạo JobInstance khác và không sử dụng checkpoint cũ. Giữ nguyên Job name và identifying parameters khi tiếp tục instance trước.

## 18. Quy trình thiết kế restart từ chunk checkpoint

Khi xây dựng Step cần restart, hãy xác định:

1. Reader đang dùng có hỗ trợ ItemStream và lưu trạng thái không?
2. saveState có được bật và reader có tên ổn định không?
3. Checkpoint mô tả offset, page, sort key hay token nào?
4. Input có bất biến hoặc có version/watermark trong suốt lần chạy không?
5. Chunk size có phù hợp với transaction duration và chi phí restart không?
6. JobRepository và dữ liệu nghiệp vụ có transaction boundary nhất quán không?
7. Retry, skip và rollback ảnh hưởng đến reader position như thế nào?
8. Writer có idempotent khi chunk được thực hiện lại không?
9. Job restart có giữ nguyên JobInstance và identifying parameters không?
10. Có cần khôi phục riêng từng partition hoặc từng resource không?
11. Log và metadata có đủ để xác định checkpoint gần nhất không?

Nên thử nghiệm bằng cách cho Job dừng có chủ đích sau một số chunk đã commit, tạo lỗi trong chunk tiếp theo, sau đó restart cùng JobParameters. Xác nhận các chunk đã commit không bị ghi trùng, chunk chưa commit được thực hiện lại và reader tiếp tục từ checkpoint đúng. Kiểm thử thêm trường hợp input thay đổi và writer tạo side effect ngoài transaction.

## Kết luận

Restart từ chunk checkpoint cho phép Spring Batch tiếp tục một chunk-oriented Step từ trạng thái đã lưu tại ranh giới commit gần nhất. ItemStream và ExecutionContext cung cấp cơ chế lưu/khôi phục vị trí reader; JobRepository lưu metadata để lần JobExecution mới của cùng JobInstance có thể tiếp tục. Để restart chính xác, reader phải hỗ trợ lưu state, tên và input phải ổn định, truy vấn cần thứ tự xác định, checkpoint phải nhất quán với dữ liệu đã commit và side effect cần idempotent. Chunk chưa commit có thể được xử lý lại, còn các chunk đã commit được giữ nguyên theo transaction đã hoàn tất.
