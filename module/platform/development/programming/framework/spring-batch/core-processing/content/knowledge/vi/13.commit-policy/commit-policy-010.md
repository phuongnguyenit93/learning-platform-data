# Commit policy và restart checkpoint

Trong Spring Batch, commit policy quyết định khi nào một nhóm item được xem là hoàn tất và transaction của nhóm đó được commit. Restart checkpoint là trạng thái đã lưu tại một ranh giới commit, giúp Job tiếp tục từ phần công việc chưa hoàn thành sau khi bị dừng hoặc thất bại.

Hai khái niệm gắn chặt với nhau. Commit policy xác định tần suất tạo checkpoint; checkpoint ghi lại tiến độ mà reader, writer hoặc Tasklet cần để khôi phục. Nếu thiết kế không đúng, Job có thể phải đọc lại nhiều dữ liệu, xử lý trùng side effect hoặc bỏ sót item khi restart.

## 1. Commit policy trong chunk-oriented processing

Chunk-oriented Step đọc item từ ItemReader, xử lý qua ItemProcessor rồi ghi một nhóm item bằng ItemWriter. Spring Batch gom các item thành chunk và thực hiện mỗi chunk trong một transaction.

~~~text
ItemReader
    |
    v
ItemProcessor
    |
    v
Gom item thành chunk
    |
    v
ItemWriter
    |
    v
Cập nhật trạng thái / checkpoint
    |
    v
Commit transaction
    |
    v
Chunk tiếp theo
~~~

**Commit policy** là quy tắc xác định khi nào chunk hiện tại kết thúc. Cách dùng phổ biến nhất là commit theo số lượng item, thường gọi là chunk size hoặc commit interval.

Ví dụ chunk size bằng 100:

- Step đọc và xử lý tối đa khoảng 100 item cho một chunk.
- Writer nhận các item đã qua processor trong chunk đó.
- Sau khi ghi thành công và cập nhật trạng thái cần thiết, transaction được commit.
- Step bắt đầu chunk tiếp theo.

Chunk cuối có thể chứa ít hơn 100 item nếu reader đã hết dữ liệu. Nếu processor filter item bằng cách trả về null, số item writer nhận có thể nhỏ hơn số item đã đọc trong chunk.

### Khai báo commit interval bằng Java

Với Spring Batch 5 trở lên:

~~~java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
~~~

Giá trị 100 là commit interval. Trong các cấu hình XML cũ, thuộc tính commit-interval được dùng để biểu diễn cùng ý tưởng. API cụ thể phụ thuộc phiên bản Spring Batch, nhưng mục đích vẫn là xác định ranh giới chunk và transaction.

## 2. Commit policy không chỉ là một con số

Commit theo số lượng là lựa chọn thường gặp vì dễ hiểu và có thể dự đoán lượng item trong một transaction. Tuy nhiên, Spring Batch cũng hỗ trợ CompletionPolicy để xác định thời điểm hoàn tất chunk theo một quy tắc.

Với SimpleCompletionPolicy, chunk kết thúc sau số lần xử lý được cấu hình:

~~~java
SimpleCompletionPolicy completionPolicy =
        new SimpleCompletionPolicy(100);

return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(completionPolicy, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .build();
~~~

Đây là cách khai báo tương đương về ý nghĩa với chunk size 100. Dùng CompletionPolicy hữu ích khi muốn tách quy tắc hoàn tất chunk khỏi phần cấu hình reader, processor và writer.

Một CompletionPolicy tùy chỉnh có thể dựa trên điều kiện của ứng dụng, chẳng hạn số item, thời gian đã trôi qua hoặc một ngưỡng dữ liệu. Tuy nhiên, policy được kiểm tra trong vòng lặp xử lý; nó không phải bộ hẹn giờ có thể ngắt ngay một item đang xử lý hoặc hủy một truy vấn đang chạy.

Không nên nhầm CompletionPolicy với transaction timeout:

| Cơ chế | Vai trò |
| --- | --- |
| Chunk size / CompletionPolicy | Quyết định khi nào chunk kết thúc và transaction chunk được hoàn tất |
| TransactionAttribute timeout | Giới hạn thời gian transaction được phép tồn tại |
| Query timeout | Giới hạn thời gian thực thi một câu SQL |
| Job deadline | Giới hạn tổng thời gian của một quy trình Job nếu ứng dụng triển khai cơ chế đó |

Commit policy quyết định kích thước hoặc điều kiện kết thúc chunk. Transaction timeout bảo vệ transaction khỏi việc tồn tại quá lâu. Hai cấu hình bổ sung cho nhau.

## 3. Vì sao commit tạo ra checkpoint?

Spring Batch cần biết phần công việc nào đã được commit thành công để có thể tiếp tục sau lỗi. Trong chunk-oriented Step, checkpoint thường được lưu cùng metadata của StepExecution trong JobRepository.

ExecutionContext là vùng lưu trạng thái key-value cho JobExecution hoặc StepExecution. Các thành phần hỗ trợ ItemStream có thể dùng ExecutionContext để lưu tiến độ như:

- Vị trí hiện tại trong file.
- Số dòng hoặc số item đã đọc.
- Trang tiếp theo cần truy vấn.
- Khóa cuối cùng đã xử lý.
- Trạng thái cần thiết để mở lại một resource.

Vòng đời ItemStream gồm ba phương thức quan trọng:

- open(ExecutionContext): khôi phục trạng thái khi resource được mở.
- update(ExecutionContext): ghi trạng thái hiện tại vào ExecutionContext.
- close(): giải phóng resource khi Step kết thúc.

Trong chunk processing, Spring Batch gọi cơ chế cập nhật trạng thái của các stream tại ranh giới chunk để checkpoint được lưu trong metadata. Với cấu hình dùng chung transaction manager và cùng database cho dữ liệu nghiệp vụ và metadata, dữ liệu ghi và checkpoint có thể được commit trong cùng transaction.

~~~text
Chunk hiện tại
    |
    +-- Reader đọc item
    +-- Processor xử lý
    +-- Writer ghi dữ liệu
    +-- ItemStream.update(context)
    +-- JobRepository lưu ExecutionContext
    |
    v
Commit transaction
    |
    v
Checkpoint mới đã bền vững
~~~

Checkpoint đại diện cho tiến độ đã được lưu tại một ranh giới commit. Nếu transaction của chunk rollback, checkpoint của chunk đó không được xem là đã hoàn tất.

## 4. Restart khôi phục từ checkpoint gần nhất

Giả sử Job đọc file gồm 1.000 dòng với chunk size 100. Sau khi ba chunk đầu commit, ứng dụng gặp lỗi khi xử lý chunk thứ tư.

~~~text
File: 1 ---------------------------------------- 1000

Chunk 1: dòng 1-100       -> COMMIT
Chunk 2: dòng 101-200     -> COMMIT
Chunk 3: dòng 201-300     -> COMMIT
Chunk 4: dòng 301-400     -> ERROR / ROLLBACK
Chunk 5: dòng 401-500     -> chưa chạy

Checkpoint đã lưu: sau dòng 300
~~~

Khi restart cùng JobInstance, reader có khả năng khôi phục trạng thái sẽ tiếp tục từ checkpoint sau dòng 300. Chunk thứ tư được đọc và xử lý lại. Các chunk 1, 2 và 3 đã commit không cần được xử lý lại trong trường hợp reader và Step được cấu hình restart đúng.

Điều này không có nghĩa Spring Batch lưu một bản sao toàn bộ item của chunk. Reader hoặc thành phần xử lý phải lưu đủ thông tin để tái tạo vị trí hoặc trạng thái cần thiết. Ví dụ reader file lưu vị trí đọc, paging reader lưu khóa hoặc trang, còn custom reader cần tự triển khai cơ chế tương ứng.

### JobInstance và JobExecution khi restart

Restart sử dụng cùng Job name và cùng identifying JobParameters để xác định JobInstance đã có. Spring Batch tạo JobExecution mới cho lần thử tiếp theo và khôi phục trạng thái từ metadata của execution trước đó.

~~~text
Job: importOrders
    |
    +-- JobInstance A
            |
            +-- JobExecution #1: FAILED
            |       Checkpoint: chunk 3 đã commit
            |
            +-- JobExecution #2: STARTED -> COMPLETED
                    Tiếp tục từ checkpoint đã lưu
~~~

Nếu thay đổi identifying parameters, Spring Batch có thể tạo JobInstance mới. Instance mới không dùng checkpoint của instance cũ. Vì vậy, không thêm timestamp hoặc UUID identifying mới khi mục tiêu là restart.

## 5. ItemStream và cách lưu trạng thái

Các reader và writer có trạng thái cần khôi phục thường triển khai ItemStream. Nhiều thành phần có sẵn của Spring Batch đã hỗ trợ cơ chế này.

Ví dụ, FlatFileItemReader có thể lưu vị trí đọc để tiếp tục sau restart. Khi cấu hình reader bằng builder, cần đặt tên ổn định:

~~~java
@Bean
public FlatFileItemReader<OrderInput> orderReader(
        Resource inputResource) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(inputResource)
            .delimited()
            .names("orderId", "customerCode", "quantity", "unitPrice")
            .targetType(OrderInput.class)
            .saveState(true)
            .build();
}
~~~

Tên reader giúp tạo key trạng thái ổn định trong ExecutionContext. saveState(true) bật việc lưu trạng thái của reader. Với thành phần có hỗ trợ restart, không nên thay đổi tên một cách tùy tiện giữa các lần chạy nếu muốn khôi phục cùng checkpoint.

Một số thành phần có thể được cấu hình saveState(false). Khi tắt, thành phần không lưu checkpoint của chính nó; restart có thể không tiếp tục đúng vị trí mà phải đọc lại từ đầu hoặc dựa vào cơ chế khác của ứng dụng. Chỉ tắt lưu trạng thái khi đã có cách phục hồi phù hợp và hiểu rõ hệ quả.

### Ví dụ custom ItemStreamReader

Một custom reader cần lưu vị trí tiếp theo cần đọc. Ví dụ dưới đây minh họa một reader đơn giản dùng danh sách đã được cung cấp:

~~~java
public class IndexedOrderReader
        implements ItemReader<OrderInput>, ItemStream {

    private static final String INDEX_KEY =
            "indexedOrderReader.nextIndex";

    private final List<OrderInput> items;
    private int nextIndex;

    public IndexedOrderReader(List<OrderInput> items) {
        this.items = items;
    }

    @Override
    public void open(ExecutionContext executionContext) {
        nextIndex = executionContext.containsKey(INDEX_KEY)
                ? executionContext.getInt(INDEX_KEY)
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
    public void update(ExecutionContext executionContext) {
        executionContext.putInt(INDEX_KEY, nextIndex);
    }

    @Override
    public void close() {
        // Giải phóng resource nếu reader có mở resource.
    }
}
~~~

Ví dụ cho thấy ba việc cần làm:

1. Khi mở reader, khôi phục nextIndex từ ExecutionContext.
2. Khi đọc item, tăng nextIndex để trỏ đến item kế tiếp.
3. Khi cập nhật stream, lưu nextIndex vào ExecutionContext.

Trong ứng dụng thực tế, không nên nạp toàn bộ dữ liệu vào List như ví dụ nếu nguồn có thể lớn. Reader nên truy cập file, database hoặc API theo cách có giới hạn tài nguyên. Key trong ExecutionContext cần duy nhất cho từng stream và dữ liệu lưu phải có kiểu được hỗ trợ bởi cơ chế serialization của JobRepository.

## 6. Checkpoint phải nhất quán với dữ liệu đã commit

Checkpoint chỉ hữu ích khi nó phản ánh chính xác tiến độ dữ liệu đã được commit. Hãy xét hai thao tác:

- Ghi dữ liệu nghiệp vụ.
- Lưu vị trí tiếp theo trong ExecutionContext.

Nếu hai thao tác tham gia cùng transaction, chúng có thể cùng commit hoặc cùng rollback. Đây là cách thuận lợi nhất để tránh checkpoint tiến xa hơn dữ liệu.

~~~text
Một transaction chunk
    |
    +-- ghi dữ liệu nghiệp vụ
    |
    +-- lưu checkpoint
    |
    +-- COMMIT cùng nhau
~~~

Nếu dữ liệu nghiệp vụ và metadata nằm trên hai database với hai transaction manager độc lập, không thể mặc định hai thao tác là atomic. Có thể xảy ra:

- Dữ liệu nghiệp vụ commit nhưng checkpoint không commit: restart có thể xử lý lại item.
- Checkpoint commit nhưng dữ liệu nghiệp vụ rollback: restart có thể bỏ qua item chưa được ghi.

Trong trường hợp tách database, cần chiến lược phục hồi như idempotent writer, khóa nghiệp vụ, outbox, staging hoặc transaction phân tán nếu yêu cầu atomicity thực sự bắt buộc. Chỉ đặt hai thao tác trong cùng một phương thức Java không làm chúng trở thành một transaction.

## 7. Commit policy ảnh hưởng đến tần suất checkpoint

Chunk size quyết định số item thường được xử lý giữa hai lần commit. Vì checkpoint được lưu tại ranh giới chunk, chunk size cũng ảnh hưởng đến tần suất lưu tiến độ.

| Chunk size | Tần suất commit/checkpoint | Hệ quả khi lỗi |
| --- | --- | --- |
| Nhỏ | Thường xuyên hơn | Ít item hơn có thể phải đọc và xử lý lại |
| Lớn | Ít thường xuyên hơn | Nhiều item hơn có thể thuộc chunk chưa commit |

Ví dụ, cùng một nguồn 10.000 item:

- Chunk size 100 tạo khoảng 100 chunk.
- Chunk size 500 tạo khoảng 20 chunk.
- Chunk size 1.000 tạo khoảng 10 chunk.

Đây là số chunk lý thuyết nếu không có skip hoặc các yếu tố làm thay đổi số item. Chunk nhỏ tạo nhiều lần ghi metadata và commit hơn. Chunk lớn giảm tần suất commit nhưng có thể làm transaction dài, tăng memory và tăng lượng công việc phải thực hiện lại khi chunk thất bại.

Không nên chọn chunk size chỉ dựa trên tốc độ. Hãy cân bằng throughput, memory, transaction duration, tần suất checkpoint và chi phí restart.

## 8. Retry, skip và checkpoint

Retry và skip ảnh hưởng đến cách một chunk được hoàn tất:

- **Retry** thử lại một thao tác thất bại theo retry policy. Nếu transaction rollback, item hoặc chunk có thể được xử lý lại tùy vị trí phát sinh lỗi.
- **Skip** cho phép bỏ qua một item hoặc lỗi thuộc nhóm được cấu hình. Skip count được ghi nhận và chunk vẫn có thể commit nếu chính sách cho phép.
- **Rollback** làm mất các thay đổi chưa commit của transaction hiện tại.

Ví dụ:

~~~text
Chunk size = 4

Chunk 1: [1, 2, 3, 4] -> ghi thành công -> COMMIT
Chunk 2: [5, 6, 7, 8] -> item 6 lỗi
    |
    +-- retry nếu lỗi tạm thời
    |
    +-- skip nếu lỗi thuộc nhóm được phép
    |
    +-- fail nếu không thể xử lý
~~~

Nếu item 6 được skip và chunk hoàn tất, checkpoint của chunk được commit cùng trạng thái skip. Khi restart, reader không cần xử lý lại item đã được xác nhận skip theo checkpoint đó. Nếu chunk rollback, trạng thái checkpoint mới chưa được xác nhận; item có thể được đọc lại.

Không nên giả định mọi exception đều làm rollback hoặc mọi skip đều làm rollback. Hành vi phụ thuộc exception type, rollback classifier, retry/skip configuration và thời điểm lỗi. Cần kiểm thử chính sách với loại reader/writer thực tế.

## 9. Restart và trạng thái của Step

Khi restart Job, Spring Batch xem xét trạng thái của các Step:

- Step đã hoàn tất thường được bỏ qua trong lần restart.
- Step thất bại hoặc dừng có thể được thực hiện lại nếu Job cho phép restart.
- Step có allowStartIfComplete(true) có thể được chạy lại ngay cả khi đã hoàn tất, tùy flow và cấu hình.
- startLimit giới hạn số lần một Step được phép bắt đầu.

Việc restart không đồng nghĩa toàn bộ Job chạy lại từ đầu. Spring Batch dùng metadata để xác định Step nào đã hoàn thành và Step nào cần tiếp tục.

Ví dụ:

~~~text
Job: dailyImport

Step 1: prepareInput       COMPLETED
Step 2: importRecords      FAILED
Step 3: publishResult     chưa chạy

Restart:
Step 1: thường được bỏ qua
Step 2: thực hiện lại từ checkpoint đã lưu
Step 3: chạy sau khi Step 2 hoàn tất
~~~

Nếu Step 1 phải chạy lại ở mọi lần restart, có thể cân nhắc allowStartIfComplete(true). Nhưng chỉ dùng khi thao tác chuẩn bị an toàn khi thực hiện lại. Ví dụ tạo thư mục hoặc kiểm tra file có thể idempotent; xóa dữ liệu đã xử lý hoặc gửi thông báo có thể tạo side effect ngoài ý muốn.

## 10. Checkpoint của Tasklet

Tasklet tùy chỉnh không tự động có checkpoint chi tiết như một reader triển khai ItemStream. Nếu Tasklet chia công việc thành nhiều lượt và trả CONTINUABLE, ứng dụng có thể lưu tiến độ trong ExecutionContext:

~~~java
@Bean
public Step processPagesStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        PageService pageService) {

    Tasklet tasklet = (contribution, chunkContext) -> {
        ExecutionContext context =
                contribution.getStepExecution().getExecutionContext();

        int nextPage = context.getInt("nextPage", 0);
        boolean hasMore = pageService.processPage(nextPage);

        if (hasMore) {
            context.putInt("nextPage", nextPage + 1);
            return RepeatStatus.CONTINUABLE;
        }

        return RepeatStatus.FINISHED;
    };

    return new StepBuilder("processPagesStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .build();
}
~~~

Ví dụ minh họa cách lưu vị trí. Trong ứng dụng thực tế, cần bảo đảm dữ liệu của page và checkpoint được commit nhất quán. Nếu service ghi dữ liệu vào resource khác transaction manager của Step, checkpoint có thể không đồng bộ với kết quả nghiệp vụ.

Với Tasklet chỉ thực hiện một thao tác, có thể không cần checkpoint riêng nếu thao tác nằm trọn trong một transaction và có thể rollback hoàn toàn. Nếu Tasklet gọi API, ghi file hoặc xử lý nhiều phần đã commit, cần idempotency hoặc trạng thái bền vững để restart an toàn.

## 11. Khi nào checkpoint không hoạt động như mong đợi?

### Reader không lưu trạng thái

Một custom reader chỉ triển khai ItemReader mà không triển khai ItemStream sẽ không tự động lưu vị trí đọc vào ExecutionContext. Khi restart, reader có thể bắt đầu lại từ đầu hoặc cần cơ chế khôi phục riêng.

### Tắt saveState

Một số reader/writer có tùy chọn saveState. Nếu tắt, thành phần đó không lưu checkpoint. Hãy xác nhận lý do trước khi dùng cấu hình này.

### Tên stream không ổn định hoặc trùng nhau

Tên reader/writer có thể được dùng để tạo key trong ExecutionContext. Tên trùng có thể gây xung đột key; đổi tên giữa các lần triển khai có thể khiến thành phần không tìm thấy trạng thái cũ. Hãy đặt tên rõ và ổn định.

### Lưu object không phù hợp trong ExecutionContext

ExecutionContext được lưu vào metadata repository và có thể phải serialize. Chỉ lưu dữ liệu nhỏ, bền vững và có kiểu được hỗ trợ. Tránh lưu connection, stream, service object hoặc object graph lớn.

### Dữ liệu nguồn thay đổi giữa các lần chạy

Checkpoint theo số dòng hoặc offset có thể không còn đúng nếu file bị thay thế hoặc dữ liệu database bị chèn/xóa trước vị trí đã đọc. Hãy dùng input bất biến, snapshot, version hoặc keyset checkpoint phù hợp.

### Side effect nằm ngoài transaction

Nếu API hoặc file đã được cập nhật nhưng transaction database rollback, restart có thể lặp side effect. Dùng idempotency key, outbox hoặc cơ chế đối soát.

### Dùng nhiều database không có transaction chung

Dữ liệu nghiệp vụ và checkpoint có thể commit lệch nhau. Cần thiết kế phục hồi cho trạng thái không đồng bộ, không dựa vào giả định atomicity.

## 12. Checkpoint theo offset và theo khóa

Không phải mọi nguồn dữ liệu đều có thể lưu một số đếm item để khôi phục.

### Offset hoặc item count

Với file bất biến, reader có thể lưu số dòng hoặc vị trí byte tiếp theo. Khi restart, reader mở lại file và chuyển đến vị trí đã lưu. Cách này dễ hiểu nhưng phụ thuộc file không thay đổi.

### Keyset checkpoint

Với database, có thể lưu khóa cuối cùng đã xử lý:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE order_id > :lastProcessedOrderId
ORDER BY order_id ASC
FETCH FIRST 100 ROWS ONLY;
~~~

Sau khi chunk commit, checkpoint lưu lastProcessedOrderId. Lần tiếp theo truy vấn các bản ghi có ID lớn hơn khóa đã lưu.

Keyset checkpoint phù hợp khi khóa ổn định và thứ tự truy vấn được xác định. Nếu thứ tự nghiệp vụ là created_at, có thể cần lưu cả created_at và order_id làm khóa ghép. Điều kiện truy vấn phải so sánh theo cùng thứ tự:

~~~sql
WHERE created_at > :lastCreatedAt
   OR (created_at = :lastCreatedAt AND order_id > :lastOrderId)
ORDER BY created_at, order_id
~~~

Nếu dữ liệu nguồn có thể được cập nhật trong lúc Job chạy, cần xác định snapshot hoặc watermark để tránh bản ghi mới chen vào phạm vi đã xử lý.

## 13. Quan sát checkpoint và lịch sử commit

JobRepository lưu metadata của JobExecution, StepExecution và ExecutionContext. Có thể dùng JobExplorer để xem trạng thái thay vì đọc trực tiếp các bảng nội bộ.

Ví dụ:

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

Các count giúp quan sát tiến độ nhưng không thay thế checkpoint của reader. Ví dụ readCount không nhất thiết là vị trí chính xác để khôi phục nếu có skip, retry, filter hoặc reader có logic phức tạp.

ExecutionContext là nơi thành phần lưu trạng thái khôi phục. Không nên tự suy ra vị trí restart chỉ từ writeCount hoặc commitCount nếu reader cần một key hoặc offset khác.

Không cập nhật trực tiếp metadata để sửa checkpoint. Các bảng có quan hệ chặt chẽ và dữ liệu ExecutionContext có thể được serialize theo cơ chế riêng. Sửa thủ công có thể khiến reader khôi phục sai hoặc làm hỏng lịch sử Job.

## 14. Thiết kế commit policy và checkpoint an toàn

Khi thiết kế một Step, nên xác định rõ:

1. Một chunk nên gồm bao nhiêu item để cân bằng throughput, memory và transaction duration?
2. Commit policy dựa trên số item hay CompletionPolicy tùy chỉnh?
3. Reader hoặc writer có trạng thái cần lưu qua ItemStream không?
4. ExecutionContext cần lưu offset, page, key hay version nào?
5. Dữ liệu nghiệp vụ và checkpoint có cùng transaction manager không?
6. Khi chunk rollback, reader có thể đọc lại cùng item một cách an toàn không?
7. Retry và skip có làm thay đổi checkpoint hoặc số lượng item cần xử lý không?
8. Input có bất biến giữa lần chạy đầu và restart không?
9. Side effect bên ngoài transaction có idempotent không?
10. Step đã COMPLETED có cần chạy lại khi restart hay không?

Checkpoint tốt phải đại diện cho dữ liệu đã commit, có thể tái tạo sau khi tiến trình khởi động lại và không phụ thuộc vào trạng thái chỉ tồn tại trong bộ nhớ.

## 15. Những lỗi thường gặp

### Chọn chunk size quá lớn

Commit ít hơn nhưng transaction dài, memory tăng và nhiều item có thể phải xử lý lại khi chunk lỗi. Hãy đo hiệu năng và chi phí restart.

### Nghĩ checkpoint được lưu sau mọi item

Thông thường checkpoint của chunk được lưu tại ranh giới commit. Nếu tiến trình dừng giữa chunk, phần chưa commit có thể phải đọc và xử lý lại.

### Custom reader không triển khai ItemStream

Không có open/update để khôi phục trạng thái, reader không thể tự lưu vị trí đọc. Hãy triển khai ItemStream hoặc dùng reader có sẵn hỗ trợ restart.

### Tắt saveState mà vẫn mong restart tiếp tục

Khi saveState bị tắt, thành phần không lưu checkpoint tương ứng. Cần một cơ chế phục hồi khác trước khi tắt.

### Thay input nhưng giữ checkpoint cũ

Offset hoặc last key có thể trỏ sai vị trí nếu file/database đã thay đổi. Dùng input version, file ID hoặc snapshot ổn định.

### Lưu checkpoint và dữ liệu nghiệp vụ ở hai transaction độc lập

Hai phía có thể commit lệch nhau. Thiết kế idempotency, outbox hoặc transaction phân tán nếu yêu cầu phù hợp.

### Dùng ExecutionContext như một kho dữ liệu nghiệp vụ

ExecutionContext dành cho trạng thái thực thi cần khôi phục. Không lưu toàn bộ item, payload lớn hoặc dữ liệu nghiệp vụ dài hạn vào đó.

### Thay identifying parameters khi restart

Tham số định danh mới có thể tạo JobInstance mới và không dùng checkpoint cũ. Giữ nguyên Job name và identifying parameters khi restart cùng instance.

### Cho rằng Step COMPLETED sẽ luôn chạy lại

Step đã hoàn tất thường được bỏ qua khi restart. Chỉ bật allowStartIfComplete khi có yêu cầu rõ và thao tác an toàn khi chạy lại.

## Kết luận

Commit policy xác định ranh giới hoàn tất chunk và transaction; restart checkpoint lưu trạng thái tại ranh giới commit để Spring Batch tiếp tục từ phần việc chưa hoàn tất. Chunk size hoặc CompletionPolicy quyết định tần suất commit, còn ItemStream và ExecutionContext cung cấp cơ chế lưu/khôi phục vị trí đọc hoặc trạng thái xử lý. Để restart an toàn, checkpoint phải nhất quán với dữ liệu đã commit, input cần ổn định, identifying parameters phải được giữ nguyên và side effect cần có tính idempotent. Khi metadata và dữ liệu nghiệp vụ nằm ở các transaction độc lập, phải thiết kế cơ chế phục hồi cho trường hợp commit lệch nhau.
