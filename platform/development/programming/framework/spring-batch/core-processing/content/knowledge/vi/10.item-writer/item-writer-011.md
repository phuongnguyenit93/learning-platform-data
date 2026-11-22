# Writer restart state

Trong Spring Batch, writer có thể cần lưu trạng thái để tiếp tục ghi đúng vị trí sau khi một Step thất bại và được restart. Trạng thái này thường được lưu trong Step ExecutionContext thông qua hợp đồng ItemStream. Khi Job chạy lại cùng JobInstance, Spring Batch mở lại writer với ExecutionContext đã lưu để writer khôi phục trạng thái tương ứng với checkpoint gần nhất.

Cơ chế này đặc biệt quan trọng với writer ghi file, cursor hoặc một đích dữ liệu có vị trí ghi cần tiếp tục. Với writer ghi database theo transaction, dữ liệu đã commit thường là nguồn sự thật và có thể không cần một con trỏ riêng. Dù dùng loại writer nào, trạng thái được lưu phải khớp với dữ liệu đã ghi bền vững.

## 1. Vì sao writer cần restart state?

Một chunk-oriented Step thường đọc và ghi dữ liệu theo từng nhóm. Giả sử Step xử lý 1.000 đơn hàng với commit interval bằng 100:

~~~text
Chunk 1: write orders 1-100    -> commit
Chunk 2: write orders 101-200  -> commit
Chunk 3: write orders 201-300  -> commit
Chunk 4: write orders 301-400  -> lỗi
~~~

Nếu chunk 1, 2 và 3 đã commit, nhưng chunk 4 thất bại, khi restart Job cần tiếp tục từ điểm phù hợp với trạng thái đã commit. Với reader, checkpoint cho biết vị trí đọc tiếp theo. Với writer, restart state có thể cho biết vị trí hoặc trạng thái đầu ra đã được xác nhận.

Ví dụ:

- Writer ghi file cần biết vị trí tiếp tục ghi và tránh ghi lại dữ liệu đã commit.
- Writer gọi hệ thống đích có thể cần biết mã bản ghi hoặc khóa cuối cùng đã được xác nhận.
- Writer ghi database có thể dựa vào transaction và unique key để bảo đảm dữ liệu đã commit không bị tạo trùng.

Reader checkpoint và writer restart state có liên quan nhưng không phải một. Reader lưu trạng thái nguồn đầu vào; writer lưu trạng thái đích đầu ra nếu implementation cần. Hai trạng thái phải mô tả cùng một ranh giới xử lý đã commit.

## 2. ItemStream và vòng đời của writer

ItemWriter<T> chỉ định nghĩa thao tác ghi chunk. Nếu writer cần mở resource hoặc lưu trạng thái để restart, nó có thể triển khai ItemStreamWriter<T>, kết hợp ItemWriter<T> và ItemStream.

Hợp đồng ItemStream gồm ba callback:

~~~java
public interface ItemStream {
    void open(ExecutionContext executionContext);
    void update(ExecutionContext executionContext);
    void close();
}
~~~

Trong API thực tế, các phương thức có thể khai báo ItemStreamException. Ý nghĩa của từng callback:

- **open(ExecutionContext):** được gọi khi Step bắt đầu. Writer mở resource và đọc state đã lưu nếu đây là lần restart.
- **update(ExecutionContext):** được gọi khi framework chuẩn bị lưu trạng thái tại ranh giới chunk. Writer ghi thông tin cần thiết vào ExecutionContext.
- **close():** được gọi khi Step kết thúc để đóng file, cursor hoặc giải phóng resource.

Vòng đời khái quát:

~~~text
Step bắt đầu
    |
    v
writer.open(saved ExecutionContext)
    |
    v
Đọc và xử lý chunk
    |
    v
writer.write(chunk)
    |
    v
writer.update(ExecutionContext)
    |
    v
JobRepository lưu checkpoint
    |
    v
Commit chunk transaction
    |
    v
Lặp lại với chunk tiếp theo
    |
    v
writer.close()
~~~

Framework quản lý thời điểm gọi các callback. Writer không nên tự gọi update() hoặc tự ghi ExecutionContext vào JobRepository.

## 3. ExecutionContext lưu restart state ở đâu?

Spring Batch có hai phạm vi ExecutionContext:

- **Step ExecutionContext** thuộc về một StepExecution. Đây là nơi thông thường để reader hoặc writer lưu state riêng của Step.
- **Job ExecutionContext** thuộc về JobExecution. Nó phù hợp để chia sẻ metadata nhỏ giữa các Step trong cùng lần chạy Job.

Restart state của writer thường thuộc Step ExecutionContext vì vị trí ghi là trạng thái riêng của writer trong Step đó.

Với JDBC JobRepository, dữ liệu này được lưu trong metadata repository, thường ở bảng BATCH_STEP_EXECUTION_CONTEXT. Khi Step được restart, Spring Batch nạp lại ExecutionContext đã lưu và truyền cho writer qua open().

ExecutionContext nên chứa thông tin nhỏ, cần thiết để phục hồi, chẳng hạn:

- Byte offset hoặc vị trí ghi đã commit.
- Số thứ tự bản ghi cuối cùng đã xác nhận.
- Khóa phân trang hoặc ID cuối đã xử lý.
- Tên file hoặc mã phiên bản của đầu ra.
- Một dấu mốc cần thiết để tiếp tục thao tác ghi.

Không lưu toàn bộ chunk, danh sách nghiệp vụ lớn, password, API token hoặc private key trong ExecutionContext. Metadata repository không phải kho dữ liệu nghiệp vụ hoặc secret manager.

## 4. Tên writer và saveState

Nhiều writer dựng sẵn của Spring Batch có tùy chọn lưu state. Ví dụ, FlatFileItemWriter có thể lưu thông tin cần thiết để tiếp tục ghi file sau restart.

~~~java
@Bean
@StepScope
FlatFileItemWriter<Order> orderFileWriter(
        @Value("#{jobParameters['outputFile']}") String outputFile) {

    return new FlatFileItemWriterBuilder<Order>()
            .name("orderFileWriter")
            .resource(new FileSystemResource(outputFile))
            .lineAggregator(order ->
                    order.getId() + "," + order.getAmount())
            .saveState(true)
            .build();
}
~~~

Các chi tiết quan trọng:

- **name("orderFileWriter")** đặt tên ổn định cho writer. Tên này được dùng để tạo các key state trong ExecutionContext.
- **saveState(true)** yêu cầu writer lưu trạng thái phục vụ restart.
- **resource(...)** xác định file đích. Khi restart, writer phải mở đúng file hoặc đúng đầu ra tương ứng với execution.
- **lineAggregator(...)** chuyển mỗi item thành một dòng văn bản.

Nếu writer lưu state, hãy giữ tên writer ổn định qua các lần triển khai. Đổi tên tùy tiện có thể khiến writer không tìm thấy key state đã lưu và không phục hồi đúng vị trí.

Nếu tắt saveState hoặc dùng writer không hỗ trợ ItemStream, Spring Batch không thể khôi phục state nội bộ của writer đó. Khi ấy, ứng dụng phải chấp nhận ghi lại từ đầu hoặc tự cung cấp cơ chế phục hồi an toàn.

## 5. FlatFileItemWriter khôi phục vị trí ghi

FlatFileItemWriter là ví dụ điển hình của writer có restart state. Nó quản lý resource file và lưu thông tin cần thiết để tiếp tục ghi theo checkpoint.

Giả sử file đầu ra có ba chunk đã commit:

~~~text
orders-export.csv
  order 1
  order 2
  ...
  order 300
~~~

Chunk tiếp theo gặp lỗi trước khi commit. Khi restart, writer cần phục hồi vị trí ghi phù hợp với trạng thái đã lưu, tránh nối dữ liệu từ một vị trí sai hoặc tạo lại những dòng đã commit.

Không nên nghĩ rằng chỉ bật chế độ append là đã có restart an toàn. Append chỉ nói cách mở file; restart còn cần state phù hợp, tên writer ổn định và chính sách xử lý file hiện có đúng với vòng đời Job.

Khi cấu hình file writer, hãy quyết định rõ:

- File được tạo mới cho mỗi JobInstance hay dùng lại một file đã có.
- Khi restart, writer tiếp tục file cũ hay tạo lại toàn bộ đầu ra.
- File có thể bị một JobInstance khác ghi đè không.
- File được công bố cho hệ thống khác ở thời điểm nào.
- Cách xử lý file còn dang dở sau khi Job thất bại.

Nếu nhiều JobInstance cùng ghi vào một đường dẫn cố định, chúng có thể ghi đè hoặc trộn dữ liệu. Hãy tạo đường dẫn gắn với business key hoặc JobInstance, rồi chỉ công bố file khi Step hoàn thành theo quy trình.

## 6. Checkpoint writer phải khớp với dữ liệu đã commit

Điều quan trọng nhất của restart state là tính nhất quán giữa trạng thái metadata và dữ liệu đầu ra.

Ví dụ, giả sử writer lưu lastWrittenId = 300 trong ExecutionContext. Giá trị này chỉ có ý nghĩa nếu dữ liệu đến ID 300 thực sự đã được ghi bền vững theo cùng ranh giới commit.

Nếu metadata nói đã ghi đến ID 300 nhưng dữ liệu đích chỉ có đến ID 250, restart có thể bỏ sót 251-300. Ngược lại, nếu dữ liệu đích đã ghi đến 350 nhưng checkpoint chỉ là 300, restart có thể ghi lặp 301-350.

Với writer ghi database, cách đơn giản và đáng tin cậy thường là để dữ liệu ghi và metadata checkpoint tham gia cùng transaction khi có thể. Nếu chúng dùng hai database hoặc hai transaction manager riêng, không mặc định rằng hai nơi sẽ commit hoặc rollback nguyên tử.

Với file hoặc API bên ngoài, transaction database không tự động hoàn tác dữ liệu đã ghi. Cần sử dụng cơ chế riêng như transactional buffering, idempotency key, staging, outbox hoặc bù trừ.

## 7. Writer ghi database có luôn cần restart state riêng không?

Không phải writer nào cũng cần một con trỏ restart riêng.

Ví dụ JdbcBatchItemWriter ghi các item của chunk vào cùng database và tham gia transaction của Step. Nếu transaction rollback, các câu lệnh ghi trong chunk được rollback. Nếu transaction commit, dữ liệu nghiệp vụ đã tồn tại bền vững.

~~~java
@Bean
JdbcBatchItemWriter<Order> orderDatabaseWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("""
                insert into orders (id, amount)
                values (:id, :amount)
                """)
            .beanMapped()
            .build();
}
~~~

Trong mô hình này, writer thường không cần tự lưu một biến lastWrittenId để quyết định vị trí ghi tiếp. Reader checkpoint và transaction database quản lý phần lớn trạng thái xử lý.

Tuy nhiên, writer database vẫn cần tính đến:

- JobRepository và business data có dùng chung transaction resource hay không.
- Retry hoặc restart có thể thực hiện lại cùng item hay không.
- Khóa chính hoặc unique constraint có ngăn bản ghi trùng không.
- Có cần upsert hoặc kiểm tra trạng thái nghiệp vụ trước khi ghi không.
- Các side effect bên ngoài database có được phát sinh trong cùng thao tác không.

Nếu metadata repository và database nghiệp vụ tách rời, có thể xuất hiện trạng thái không đồng bộ. Thiết kế writer idempotent giúp xử lý an toàn hơn trong những trường hợp này.

## 8. Tự viết writer có restart state

Một writer tùy chỉnh cần triển khai ItemStreamWriter khi có state cần khôi phục. Về nguyên tắc, writer thực hiện ba việc:

1. open() đọc checkpoint cũ và khôi phục resource hoặc vị trí.
2. write() ghi chunk vào đích.
3. update() đưa trạng thái tương ứng với đầu ra đã ghi vào ExecutionContext.

Mẫu cấu trúc:

~~~java
public class RestartableOrderWriter
        implements ItemStreamWriter<Order> {

    private static final String LAST_ID_KEY =
            "restartableOrderWriter.lastId";

    private final OrderSink sink;
    private long lastCommittedId;

    public RestartableOrderWriter(OrderSink sink) {
        this.sink = sink;
    }

    @Override
    public void open(ExecutionContext context) {
        lastCommittedId = context.containsKey(LAST_ID_KEY)
                ? context.getLong(LAST_ID_KEY)
                : 0L;

        sink.openAfter(lastCommittedId);
    }

    @Override
    public void write(Chunk<? extends Order> chunk) throws Exception {
        sink.write(chunk);
    }

    @Override
    public void update(ExecutionContext context) {
        long position = sink.positionForCheckpoint();
        context.putLong(LAST_ID_KEY, position);
    }

    @Override
    public void close() {
        sink.close();
    }
}
~~~

OrderSink ở đây là abstraction minh họa cho một đích ghi có khả năng khôi phục vị trí. Implementation thực tế phải định nghĩa rõ positionForCheckpoint() đại diện cho vị trí nào và làm sao bảo đảm vị trí đó khớp với dữ liệu đã commit.

Đây không phải một writer có thể dùng trực tiếp nếu chưa triển khai OrderSink và transaction semantics. Với đích database cùng transaction, positionForCheckpoint() phải phản ánh trạng thái ghi được commit cùng metadata. Với file hoặc dịch vụ bên ngoài, cần thêm cơ chế buffering, truncate/restore, idempotency hoặc đối soát để xử lý phần ghi dở dang.

Không nên chỉ tăng một biến trong bộ nhớ rồi ghi biến đó vào ExecutionContext và coi đó là checkpoint an toàn. Nếu chunk rollback, trạng thái trong memory có thể đã tiến lên dù dữ liệu đích chưa được commit. Writer tùy chỉnh phải xử lý được cả rollback trong cùng execution, không chỉ restart sau khi process khởi động lại.

## 9. Writer state và rollback trong cùng một execution

Restart sau khi JobExecution thất bại là một trường hợp. Rollback và retry ngay trong cùng execution là trường hợp khác.

Ví dụ:

~~~text
write(chunk 1) -> thành công
update state   -> chuẩn bị checkpoint
commit         -> thành công

write(chunk 2) -> ghi được một phần
exception      -> rollback transaction
retry chunk 2  -> framework có thể gọi write lại
~~~

Nếu writer đã thay đổi state nội bộ trong lần write thất bại, lần retry có thể sử dụng state sai. Vì vậy, state trong bộ nhớ phải được phục hồi hoặc tính toán lại phù hợp với transaction.

Một số nguyên tắc:

- Chỉ checkpoint trạng thái tương ứng với đầu ra đã được xác nhận.
- Không coi trạng thái mutable trong writer là nguồn sự thật duy nhất.
- Với database, ưu tiên để transaction quản lý cả business writes và metadata khi có thể.
- Với file, dùng writer có transactional buffering và restart support đã được Spring Batch cung cấp nếu phù hợp.
- Với hệ thống bên ngoài, thiết kế thao tác idempotent hoặc có thể đối soát khi retry.
- Kiểm thử rollback trong cùng execution, không chỉ kiểm thử restart sau process failure.

ItemStream.update() được gọi trong quy trình quản lý chunk; nó không có nghĩa rằng dữ liệu đã được commit thành công ngay tại thời điểm callback được gọi. Transaction của chunk vẫn có thể rollback. Do đó, việc cập nhật state trong ExecutionContext phải tham gia cơ chế transaction của repository và được thiết kế cùng đích dữ liệu.

## 10. JobRepository và transaction manager có ảnh hưởng thế nào?

JobRepository lưu ExecutionContext và các metadata khác. Transaction manager của Step điều phối transaction chunk. Cấu hình hai thành phần này ảnh hưởng đến mức độ nhất quán giữa checkpoint và dữ liệu nghiệp vụ.

Trường hợp thuận lợi là business data và metadata repository dùng cùng transaction resource phù hợp. Khi đó, dữ liệu nghiệp vụ và checkpoint có thể commit hoặc rollback cùng nhau.

Nếu chúng dùng hai database khác nhau:

~~~text
Step transaction
    |
    +--> Business database
    |
    +--> JobRepository database
~~~

Hai nơi không tự động trở thành một transaction nguyên tử chỉ vì cùng được sử dụng trong một Step. Có thể xảy ra một bên commit trong khi bên kia chưa commit hoặc gặp lỗi.

Khi dùng nhiều transaction manager hoặc resource, hãy đánh giá:

- Có cần transaction coordinator phân tán hay không.
- Có thể chấp nhận eventual consistency hay không.
- Writer có idempotent không.
- Có thể đối soát business data với checkpoint không.
- Có thể khôi phục đầu ra từ staging hoặc nguồn bất biến không.

Không cập nhật trực tiếp bảng BATCH_STEP_EXECUTION_CONTEXT để sửa vị trí writer. Hãy để Spring Batch và JobRepository quản lý trạng thái qua lifecycle và API tương ứng.

## 11. Restart cùng JobInstance

Spring Batch restart một JobInstance bằng cách tạo JobExecution mới khi execution trước thất bại hoặc bị dừng và trạng thái cho phép restart. Step đã hoàn thành thường được bỏ qua; Step cần chạy lại sẽ khôi phục reader và writer state nếu các component hỗ trợ ItemStream.

Ví dụ:

~~~text
JobInstance: exportOrders, businessDate=2026-11-15

JobExecution 101:
  exportOrdersStep
    chunk 1 -> commit
    chunk 2 -> commit
    chunk 3 -> writer error
  status = FAILED

JobExecution 108 (restart):
  exportOrdersStep
    reader.open(saved reader state)
    writer.open(saved writer state)
    tiếp tục từ checkpoint đã commit
~~~

Để restart đúng:

- Giữ nguyên identifying JobParameters của JobInstance cần tiếp tục.
- Giữ nguyên tên Step và tên reader/writer có state.
- Bảo đảm file hoặc đích dữ liệu cần tiếp tục vẫn tồn tại.
- Không thay đổi nguồn hoặc đích theo cách làm checkpoint cũ mất ý nghĩa.
- Bảo đảm writer không tạo duplicate khi chunk được retry hoặc Step được restart.

Nếu thay đổi identifying JobParameters, Spring Batch tạo JobInstance mới. Job mới không tự sử dụng writer state của instance cũ.

## 12. Đầu ra file và chính sách quản lý file khi restart

Với writer ghi file, vị trí file là một phần quan trọng của restart state. Cần quyết định đầu ra là file riêng cho từng JobInstance hay file dùng chung.

Một mô hình dễ quản lý:

~~~text
/data/batch/output/
    export-2026-11-15-job-101.csv
    export-2026-11-16-job-105.csv
~~~

Mỗi JobInstance ghi một file riêng. Sau khi Step hoàn thành, một bước publish riêng có thể đổi tên hoặc chuyển file vào thư mục mà hệ thống tiêu thụ theo dõi.

Cần cân nhắc:

- Không xóa file đầu ra dở dang nếu Job vẫn cần restart từ nó.
- Không để một JobInstance khác ghi đè file đang được restart.
- Xác định thời điểm file được xem là hoàn chỉnh.
- Nếu tạo lại file từ đầu, bảo đảm Step và toàn bộ quy trình có thể chạy lại an toàn.
- Dọn file cũ sau khi Job không còn cần restart và đã qua thời hạn lưu trữ.

Đừng dựa vào tên file cố định như orders.csv nếu nhiều lần chạy có thể đồng thời hoặc cần lưu lịch sử đầu ra. Định danh file theo business key hoặc JobInstance giúp giảm xung đột.

## 13. Writer ghi API hoặc message broker

Khi writer gọi API hoặc gửi message, đích thường không tham gia transaction database của Spring Batch. Nếu API đã nhận request nhưng ứng dụng mất kết nối trước khi nhận response, writer không biết chắc thao tác đã thành công hay chưa.

Nếu retry chunk, cùng một request có thể được gửi lại. Restart state đơn thuần không giải quyết được sự mơ hồ này.

Các cơ chế thường dùng:

- **Idempotency key:** gửi khóa ổn định theo business item hoặc chunk để hệ thống nhận biết request lặp.
- **Transactional outbox:** ghi message cần phát vào database cùng transaction nghiệp vụ, sau đó tiến trình riêng gửi message.
- **Inbox/deduplication:** phía nhận lưu ID message đã xử lý để bỏ qua lần giao lại.
- **Reconciliation:** đối soát trạng thái đầu ra sau khi timeout hoặc lỗi không xác định.
- **Compensation:** thực hiện hành động bù trừ nếu không thể rollback tác động đã xảy ra.

Nếu writer gửi một message cho mỗi item, idempotency key nên gắn với định danh nghiệp vụ của item. Nếu gửi một message cho cả chunk, khóa nên xác định được chunk hoặc batch một cách ổn định.

## 14. Nhiều writer hoặc composite writer

CompositeItemWriter có thể điều phối nhiều delegate writer nhận cùng một chunk. Nếu delegate có restart state, cần bảo đảm lifecycle ItemStream của delegate được đăng ký đúng để open(), update() và close() được gọi.

Ví dụ:

~~~java
@Bean
CompositeItemWriter<Order> orderCompositeWriter(
        JdbcBatchItemWriter<Order> databaseWriter,
        FlatFileItemWriter<Order> fileWriter) {

    return new CompositeItemWriterBuilder<Order>()
            .delegates(databaseWriter, fileWriter)
            .build();
}
~~~

Trong cấu hình thực tế, kiểm tra phiên bản Spring Batch và cơ chế stream registration của composite/delegate. Không giả định rằng mọi delegate đều tự động được quản lý lifecycle trong mọi kiểu lồng nhau.

Nếu database writer và file writer không cùng tham gia một transaction nguyên tử, có thể một đích đã ghi thành công còn đích kia thất bại. Khi restart, hai delegate có thể ở hai trạng thái khác nhau. Cần thiết kế idempotency, staging hoặc một Step riêng để tạo đầu ra phụ từ dữ liệu đã commit.

## 15. Kiểm thử writer restart state

Kiểm thử writer cần bao gồm cả state lifecycle, rollback và restart. Chỉ xác nhận write() ghi đúng dữ liệu cho một chunk là chưa đủ với writer có state.

Các kịch bản cần kiểm tra:

| Kịch bản | Điều cần xác nhận |
|---|---|
| Lần chạy đầu | open() nhận context rỗng và writer bắt đầu đúng vị trí |
| Sau một chunk thành công | update() lưu state tương ứng với đầu ra đã commit |
| Restart | open() khôi phục state đã lưu |
| Writer thất bại giữa chunk | transaction rollback theo cấu hình |
| Retry cùng execution | writer không dùng state trong memory đã tiến sai |
| Restart sau process failure | Không ghi trùng hoặc bỏ sót dữ liệu |
| File nguồn/đích bị thay đổi | Job phát hiện hoặc xử lý theo chính sách |
| Delegate writer | Lifecycle của từng stream được gọi đúng |
| Secret/log | Không ghi credential vào ExecutionContext hoặc log |

Với FlatFileItemWriter, có thể dùng integration test chạy Job lần đầu, mô phỏng lỗi ở chunk sau, sau đó restart cùng JobInstance và xác nhận file cuối cùng có đúng các dòng, không trùng hoặc thiếu.

Với writer database, kiểm tra dữ liệu và metadata checkpoint sau commit/rollback. Nếu JobRepository và business database khác nhau, kiểm thử cả tình huống một bên commit và bên kia gặp lỗi để xác định khả năng phục hồi.

## 16. Lỗi thường gặp khi thiết kế restart state

**Không đặt tên writer ổn định.** Writer có thể không tìm đúng key state trong ExecutionContext sau restart. Đặt tên ổn định và duy nhất trong phạm vi Step.

**Tắt saveState khi cần restart.** Writer dựng sẵn không lưu state thì không thể tự khôi phục vị trí ghi. Bật saveState hoặc triển khai cơ chế riêng.

**Nghĩ append đồng nghĩa restart an toàn.** Append chỉ quyết định cách mở file; cần state và chính sách xử lý phần ghi dở dang.

**Lưu state trước khi dữ liệu đích bền vững.** Metadata có thể đi trước dữ liệu và khiến restart bỏ sót item. Đồng bộ checkpoint với transaction hoặc dùng idempotency/đối soát.

**Chỉ kiểm tra restart sau khi process chết.** Rollback và retry trong cùng execution cũng có thể làm state trong memory lệch với checkpoint đã commit.

**Dùng bộ đếm trong memory làm nguồn sự thật.** Bộ đếm có thể tiến lên dù chunk rollback. State phải được suy ra từ đầu ra đã xác nhận hoặc được phục hồi khi rollback.

**Giả định mọi đích ghi đều transactional.** File, API và broker không tự rollback cùng database. Cần thiết kế phục hồi riêng.

**Thay đổi file hoặc nguồn giữa hai lần chạy.** Checkpoint cũ có thể trỏ đến vị trí khác. Dùng phiên bản nguồn/đích ổn định hoặc phát hiện thay đổi trước khi restart.

## 17. Quy trình thiết kế writer có restart state

Khi triển khai writer, hãy trả lời các câu hỏi sau:

1. Đích ghi có lưu trạng thái bền vững và hỗ trợ transaction không?
2. Writer có cần lưu vị trí hoặc trạng thái riêng không?
3. State nào đủ để tiếp tục mà không lưu dữ liệu nghiệp vụ lớn?
4. State có được lưu trong Step ExecutionContext không?
5. Writer có triển khai ItemStreamWriter và quản lý open/update/close đúng không?
6. Tên writer có ổn định giữa các lần triển khai không?
7. Chunk rollback hoặc retry trong cùng execution có thể làm state trong memory sai không?
8. JobRepository và business sink có cùng transaction resource không?
9. Nếu ghi file/API/message, cơ chế idempotency hoặc phục hồi là gì?
10. Kiểm thử đã bao gồm restart, rollback, retry và dữ liệu đầu ra chưa?

Với writer dựng sẵn như FlatFileItemWriter, hãy dùng cơ chế saveState và lifecycle mà framework cung cấp. Với writer database, ưu tiên transaction và ràng buộc dữ liệu để bảo đảm thao tác ghi an toàn khi chạy lại. Với writer tùy chỉnh hoặc đích ngoài transaction, cần thiết kế state theo checkpoint đã commit và có cơ chế xử lý tác động đã xảy ra nhưng chưa được xác nhận.

Restart state của writer chỉ đáng tin cậy khi nó mô tả đúng trạng thái đầu ra đã bền vững. ItemStream cung cấp lifecycle để lưu và phục hồi state; JobRepository lưu checkpoint; transaction và idempotency bảo vệ dữ liệu khi rollback, retry hoặc restart. Kết hợp đúng các cơ chế này giúp writer tiếp tục công việc mà không ghi trùng hoặc bỏ sót item.

