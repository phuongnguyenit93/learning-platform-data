# ItemWriter ghi một chunk item

Trong Spring Batch, ItemWriter là thành phần nhận dữ liệu đã được đọc và xử lý để ghi ra đích. Với chunk-oriented Step, framework gom nhiều item thành một chunk rồi gọi writer để ghi cả nhóm. Vì vậy, một lần gọi write() thường đại diện cho một đơn vị ghi theo chunk, không phải một lần ghi riêng lẻ cho từng item.

Cách tổ chức này giúp Spring Batch phối hợp đọc, xử lý, ghi và commit transaction theo từng phần dữ liệu. Writer có thể ghi vào database, file, message broker hoặc hệ thống khác, miễn là triển khai đúng hợp đồng và xử lý phù hợp với transaction, lỗi và khả năng chạy lại.

## 1. Hợp đồng của ItemWriter

Trong Spring Batch 5, interface ItemWriter<T> có phương thức:

~~~java
public interface ItemWriter<T> {
    void write(Chunk<? extends T> chunk) throws Exception;
}
~~~

Tham số Chunk chứa các item mà framework chuyển cho writer trong lần ghi hiện tại. Writer có thể duyệt các item trong chunk và thực hiện thao tác ghi phù hợp với đích dữ liệu.

Một số điểm cần nhớ:

- Writer nhận một chunk gồm nhiều item, có thể ít hơn commit interval.
- Writer thường được gọi sau khi reader đã đọc và processor đã xử lý các item của chunk.
- Writer không tự quyết định khi nào chunk kết thúc.
- Writer không tự commit transaction của chunk.
- Nếu ghi thất bại, writer có thể ném exception để framework xử lý rollback, retry hoặc skip theo cấu hình Step.

Với Spring Batch 4.x, chữ ký ItemWriter cũ nhận List<? extends T>. Khi chuyển sang Spring Batch 5, API đổi sang Chunk<? extends T>. Hãy dùng đúng chữ ký theo phiên bản đang chạy, không trộn ví dụ của hai thế hệ API.

## 2. Chunk được tạo trước khi gọi writer

Giả sử Step có commit interval bằng 3. Reader đọc từng item, processor có thể biến đổi hoặc lọc item, sau đó writer nhận các kết quả còn lại.

~~~text
ItemReader
  read A
  read B
  read C
      |
      v
ItemProcessor
  A -> A'
  B -> null (filter)
  C -> C'
      |
      v
Chunk đầu ra
  [A', C']
      |
      v
ItemWriter.write(chunk)
      |
      v
Commit transaction
~~~

Trong ví dụ này, reader đã cung cấp ba item nhưng processor lọc item B bằng cách trả về null. Writer chỉ nhận hai item còn lại là A' và C'.

Do đó, số item writer nhận không nhất thiết bằng commit interval hoặc số item reader đã đọc. Chunk cuối của nguồn dữ liệu cũng có thể nhỏ hơn commit interval vì reader trả null khi hết dữ liệu.

Ví dụ với tám item và commit interval bằng ba:

~~~text
Chunk 1: [A, B, C] -> write -> commit
Chunk 2: [D, E, F] -> write -> commit
Chunk 3: [G, H]    -> write -> commit
~~~

Writer không cần tự đếm số item đã đọc từ đầu Job. Framework quản lý vòng lặp đọc và gom chunk dựa trên cấu hình Step.

## 3. Khai báo một chunk-oriented Step

Ví dụ sau dùng API Java của Spring Batch 5:

~~~java
@Bean
Step exportCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Customer> customerReader,
        ItemProcessor<Customer, Customer> customerProcessor,
        ItemWriter<Customer> customerWriter) {

    return new StepBuilder("exportCustomersStep", jobRepository)
            .<Customer, Customer>chunk(100, transactionManager)
            .reader(customerReader)
            .processor(customerProcessor)
            .writer(customerWriter)
            .build();
}
~~~

Cấu hình chunk(100, transactionManager) cho biết framework gom tối đa 100 item đầu vào cho một chunk theo luồng xử lý thông thường. Khi chunk được xử lý, writer nhận các item đầu ra của processor.

Transaction manager được truyền vào StepBuilder để quản lý transaction của chunk. Nếu writer ghi vào database sử dụng cùng transaction resource, thao tác ghi có thể tham gia transaction đó.

Không nên tạo transaction mới và commit riêng trong writer cho từng item nếu mục tiêu là giữ ranh giới transaction theo chunk. Làm vậy có thể khiến một phần item đã ghi không rollback được khi item khác trong cùng chunk thất bại.

## 4. Viết một ItemWriter tùy chỉnh

Khi không có writer dựng sẵn phù hợp, có thể triển khai ItemWriter<T>.

Ví dụ ghi thông tin audit cho các Customer trong chunk:

~~~java
public class CustomerAuditWriter implements ItemWriter<Customer> {

    private final CustomerAuditService auditService;

    public CustomerAuditWriter(CustomerAuditService auditService) {
        this.auditService = auditService;
    }

    @Override
    public void write(Chunk<? extends Customer> chunk) {
        for (Customer customer : chunk) {
            auditService.record(customer);
        }
    }
}
~~~

Mỗi lần write(), writer duyệt các item trong chunk và chuyển từng item cho service ghi audit. Framework chịu trách nhiệm gọi write() với chunk phù hợp.

Đây là ví dụ đơn giản. Nếu auditService ghi vào cùng database và cùng transaction resource, các thay đổi có thể rollback cùng chunk. Nếu service gọi API hoặc ghi sang một hệ thống khác, transaction database của Step không tự động hoàn tác các tác động đó.

Writer nên tập trung vào việc ghi các item được giao. Tránh để writer tự đọc thêm dữ liệu từ nguồn, tự khởi chạy Step khác hoặc tự điều khiển vòng đời Job. Các trách nhiệm đó thuộc những thành phần khác của ứng dụng hoặc Job flow.

## 5. Ghi chunk vào database với JdbcBatchItemWriter

Spring Batch cung cấp JdbcBatchItemWriter để thực hiện batch update/insert vào database. Writer nhận chunk và thực hiện các câu SQL cho các item trong nhóm.

Ví dụ:

~~~java
@Bean
JdbcBatchItemWriter<Customer> customerDatabaseWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<Customer>()
            .dataSource(dataSource)
            .sql("""
                insert into customer (id, name, email)
                values (:id, :name, :email)
                """)
            .beanMapped()
            .build();
}
~~~

Với bean mapping, các placeholder như id, name và email được ánh xạ từ thuộc tính tương ứng của Customer. JdbcBatchItemWriter thực hiện các thao tác JDBC cho các item trong chunk.

Trong ứng dụng thực tế, cần xác định rõ:

- Bảng đích có khóa chính hoặc unique constraint phù hợp không.
- Trường hợp bản ghi đã tồn tại sẽ insert, update hay upsert.
- Batch update có phù hợp với driver và database đang dùng không.
- Transaction manager của Step có quản lý cùng DataSource mà writer sử dụng không.
- Số lượng item mỗi chunk có phù hợp với giới hạn tham số, bộ nhớ và hiệu năng database không.

Nếu writer và JobRepository dùng hai database hoặc transaction manager khác nhau, không mặc định rằng metadata và dữ liệu nghiệp vụ được commit nguyên tử cùng nhau. Cần thiết kế restart và idempotency cho trường hợp hai nơi có trạng thái không đồng bộ.

### Insert hay update?

Writer cần phản ánh đúng quy tắc nghiệp vụ. Một số lựa chọn thường gặp:

| Cách ghi | Hành vi |
|---|---|
| INSERT | Tạo bản ghi mới; có thể lỗi nếu khóa đã tồn tại |
| UPDATE | Cập nhật bản ghi đã có; có thể không cập nhật hàng nào |
| UPSERT | Insert hoặc update tùy khóa và cú pháp database |
| MERGE | Kết hợp insert/update theo điều kiện, tùy database |
| Stored procedure | Chuyển logic ghi vào thủ tục phía database |

Nếu Job có thể restart hoặc được gửi launch nhiều lần, hãy dùng khóa nghiệp vụ ổn định và quy tắc ghi an toàn khi chạy lại. Chỉ dựa vào việc chunk trước đã commit là chưa đủ để bảo đảm không có duplicate trong mọi tình huống, nhất là khi nguồn và đích không cùng transaction.

## 6. Ghi chunk ra file với FlatFileItemWriter

FlatFileItemWriter là writer dựng sẵn để ghi item thành các dòng văn bản. Có thể cấu hình một LineAggregator để chuyển từng object thành dòng.

Ví dụ đơn giản:

~~~java
@Bean
@StepScope
FlatFileItemWriter<Customer> customerFileWriter(
        @Value("#{jobParameters['outputFile']}") String outputFile) {

    return new FlatFileItemWriterBuilder<Customer>()
            .name("customerFileWriter")
            .resource(new FileSystemResource(outputFile))
            .lineAggregator(customer ->
                    customer.getId() + "," + customer.getName())
            .saveState(true)
            .build();
}
~~~

Khi Step chạy, FlatFileItemWriter nhận chunk, ánh xạ từng Customer thành một dòng và ghi ra file. saveState(true) cho phép writer lưu trạng thái cần thiết để restart, chẳng hạn vị trí ghi trong file.

Ví dụ lineAggregator trên chỉ minh họa cách ghép trường. Nếu dữ liệu có dấu phẩy, dấu nháy kép hoặc xuống dòng, hãy dùng formatter/CSV library phù hợp để escape đúng định dạng. Không tự ghép CSV đơn giản cho dữ liệu thực tế có thể chứa ký tự đặc biệt.

### Ghi file trung gian an toàn

Nếu file là đầu ra nghiệp vụ quan trọng, cần quyết định cách xử lý file khi Step thất bại hoặc restart:

- Dùng tên file gắn với JobInstance hoặc business key.
- Không để hai JobInstance ghi đè cùng một file đầu ra ngoài ý muốn.
- Giữ file trung gian đủ lâu để restart có thể tiếp tục.
- Chỉ công bố file hoàn chỉnh sau khi Step ghi thành công.
- Có thể ghi vào file tạm rồi đổi tên khi hoàn tất nếu filesystem và môi trường triển khai hỗ trợ thao tác rename phù hợp.

Ghi file không mặc nhiên tham gia transaction database. Cần phân biệt cơ chế transactional buffering mà một writer cụ thể hỗ trợ với tính nguyên tử của cả filesystem và database.

## 7. Writer và ranh giới transaction của chunk

Trong chunk-oriented Step, writer được gọi trong quá trình xử lý chunk. Sau khi writer hoàn tất và các trạng thái stream cần thiết được cập nhật, framework commit transaction của chunk.

Luồng khái quát:

~~~text
Begin chunk transaction
       |
       v
Read items
       |
       v
Process items
       |
       v
ItemWriter.write(chunk)
       |
       v
Update checkpoint / stream state
       |
       v
Commit transaction
~~~

Nếu writer ném exception và lỗi đó làm transaction rollback, các thay đổi trên tài nguyên tham gia transaction hiện tại được hoàn tác. Các chunk đã commit trước đó vẫn được giữ.

Ví dụ, chunk size bằng 100 và writer ghi database:

~~~text
Chunk 1: insert 100 customers -> commit
Chunk 2: insert 100 customers -> commit
Chunk 3: insert customer gặp lỗi -> rollback chunk 3
~~~

Sau rollback, dữ liệu đã commit ở chunk 1 và 2 vẫn tồn tại. Khi restart, Step có thể tiếp tục từ checkpoint gần nhất nếu reader và writer hỗ trợ restart.

Transaction chỉ bảo vệ các tài nguyên tham gia cùng transaction. Nếu writer ghi database rồi gửi HTTP request đến dịch vụ khác, database rollback không thể tự rút lại HTTP request đã thành công.

Với tác động ngoài transaction, cân nhắc:

- Idempotency key ở hệ thống nhận.
- Transactional outbox để lưu ý định phát message cùng transaction database.
- Bảng trạng thái nghiệp vụ để phát hiện thao tác đã hoàn tất.
- Cơ chế bù trừ khi không thể rollback hành động bên ngoài.

## 8. Writer có thể nhận chunk được retry hoặc xử lý skip

Trong Step có cấu hình fault tolerance, một lỗi ghi có thể làm chunk rollback và được retry hoặc xử lý theo skip policy.

Điều này có nghĩa writer có thể được gọi lại với dữ liệu giống hoặc gần giống lần gọi trước. Writer cần được thiết kế để chịu được tình huống đó.

Ví dụ, nếu writer gửi email cho từng item rồi một email sau đó thất bại, việc retry có thể gửi lại những email đã gửi thành công. Transaction database không thu hồi được email đã phát đi.

Để tránh tác động trùng:

- Ưu tiên writer ghi database với unique key hoặc upsert khi phù hợp.
- Dùng idempotency key cho API hoặc message.
- Lưu trạng thái gửi theo business key nếu cần.
- Phân biệt lỗi tạm thời có thể retry với lỗi nghiệp vụ cần xử lý.
- Ghi nhận item bị skip để có thể đối soát sau Job.

Skip trong write có thể cần framework rollback rồi xác định item lỗi theo cơ chế fault-tolerant của Step. Không tự bắt mọi exception trong writer rồi bỏ qua im lặng, vì framework sẽ không biết lỗi xảy ra và counters/skip policy không phản ánh đúng.

## 9. ItemWriter và ItemStreamWriter

Một writer chỉ cần nhận chunk có thể triển khai ItemWriter<T>. Nếu writer cần quản lý resource hoặc lưu trạng thái phục vụ restart, nó có thể triển khai ItemStreamWriter<T>.

ItemStreamWriter kết hợp hợp đồng ghi của ItemWriter và vòng đời của ItemStream:

~~~java
public interface ItemStream {
    void open(ExecutionContext executionContext);
    void update(ExecutionContext executionContext);
    void close();
}
~~~

Các callback có ý nghĩa:

- **open:** mở resource và khôi phục trạng thái khi Step bắt đầu hoặc restart.
- **update:** ghi trạng thái hiện tại vào ExecutionContext trước khi checkpoint được lưu.
- **close:** đóng resource và giải phóng tài nguyên khi Step kết thúc.

FlatFileItemWriter là một ví dụ writer có quản lý state/resource. Khi tự viết writer giữ file handle, cursor hoặc trạng thái ghi, cần triển khai lifecycle phù hợp và bảo đảm delegate ItemStream được đăng ký đúng nếu writer được bọc trong một composite.

Không lưu object nghiệp vụ lớn hoặc credential vào ExecutionContext của writer. Chỉ lưu thông tin cần thiết để khôi phục vị trí hoặc trạng thái ghi.

## 10. Writer có trạng thái và restart

Một writer restartable phải xác định được vị trí hoặc trạng thái ghi đã commit gần nhất. Ví dụ, FlatFileItemWriter có thể lưu vị trí ghi để khi restart tiếp tục ghi đúng chỗ theo cơ chế của nó.

Với writer tùy chỉnh, cần tự thiết kế state:

~~~java
public class CountingWriter<T> implements ItemStreamWriter<T> {

    private static final String WRITTEN_COUNT = "countingWriter.writtenCount";

    private long writtenCount;

    @Override
    public void open(ExecutionContext context) {
        writtenCount = context.containsKey(WRITTEN_COUNT)
                ? context.getLong(WRITTEN_COUNT)
                : 0L;
    }

    @Override
    public void write(Chunk<? extends T> chunk) {
        for (T item : chunk) {
            // Thực hiện thao tác ghi thực tế ở đây.
            writtenCount++;
        }
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong(WRITTEN_COUNT, writtenCount);
    }

    @Override
    public void close() {
        // Đóng resource nếu writer có mở resource.
    }
}
~~~

Đây chỉ là ví dụ minh họa lifecycle. Bộ đếm trong memory không tự khôi phục tác động ghi của hệ thống đích. Trong writer thực tế, state phải khớp với dữ liệu đã commit; nếu writer ghi vào database, thường nên để transaction và khóa nghiệp vụ bảo đảm tính nhất quán thay vì dựa vào một bộ đếm tự tạo.

Nếu writer ghi file hoặc một hệ thống bên ngoài, cần xác định rõ cách rollback hoặc tiếp tục sau lỗi. Không thể chỉ lưu một số đếm rồi giả định mọi item trước đó chắc chắn đã được ghi bền vững.

## 11. Composite writer và ghi ra nhiều đích

Một số quy trình cần ghi cùng một chunk vào nhiều nơi, ví dụ database và file audit. Có thể dùng CompositeItemWriter để điều phối nhiều delegate writer.

Ví dụ:

~~~java
@Bean
CompositeItemWriter<Customer> customerCompositeWriter(
        JdbcBatchItemWriter<Customer> customerDatabaseWriter,
        FlatFileItemWriter<Customer> customerFileWriter) {

    return new CompositeItemWriterBuilder<Customer>()
            .delegates(customerDatabaseWriter, customerFileWriter)
            .build();
}
~~~

Khi Step gọi composite writer, các delegate nhận chunk theo thứ tự cấu hình. Cần bảo đảm delegate nào cần lifecycle ItemStream đều được đăng ký và callback được gọi đúng. Với composite/delegate lồng nhau, hãy kiểm tra cơ chế stream registration của phiên bản Spring Batch đang dùng.

Ghi nhiều đích không đồng nghĩa với transaction phân tán tự động. Nếu database commit nhưng file không thể hoàn tất, hoặc ngược lại, hai đích có thể lệch trạng thái. Cần cân nhắc:

- Dùng cùng transaction manager nếu các delegate cùng tham gia một transaction resource phù hợp.
- Ghi dữ liệu chính vào database, sau đó tạo file từ dữ liệu đã commit ở Step riêng.
- Dùng outbox hoặc staging để phát sinh dữ liệu phụ sau commit.
- Có cơ chế phát hiện và sửa trạng thái lệch khi restart.

Nếu các đích không thể commit nguyên tử cùng nhau, thiết kế phục hồi cần được nêu rõ trong quy trình.

## 12. Kích thước chunk và hiệu năng ghi

Commit interval ảnh hưởng đến số item mỗi lần writer nhận. Chunk quá nhỏ có thể làm tăng số lần gọi writer và số lần commit; chunk quá lớn có thể tăng bộ nhớ, thời gian giữ lock và chi phí xử lý lại sau rollback.

| Chunk nhỏ | Chunk lớn |
|---|---|
| Nhiều lần gọi write() hơn | Ít lần gọi write() hơn |
| Transaction thường ngắn hơn | Transaction có thể kéo dài hơn |
| Ít item phải xử lý lại khi rollback | Có thể xử lý lại nhiều item hơn |
| Chi phí commit cao hơn | Chi phí commit trên mỗi item có thể thấp hơn |
| Thường dùng ít bộ nhớ hơn | Có thể cần nhiều bộ nhớ hơn |

Không chọn chunk size chỉ dựa trên tốc độ ghi. Cần đo với kích thước dữ liệu thực tế, database driver, index, network, thời gian processor và giới hạn transaction của hệ thống.

Nếu writer gọi một API bên ngoài, kích thước chunk lớn cũng có thể làm tăng số request hoặc payload mỗi lần xử lý. Hãy cân nhắc giới hạn batch của API đích và chia nhỏ trong phạm vi hợp đồng mà writer hỗ trợ, nhưng không tự ý phá vỡ transaction semantics của Step.

## 13. Những lỗi thường gặp khi triển khai ItemWriter

**Giả định writer nhận từng item.** Trong chunk-oriented Step, write() nhận cả Chunk. Hãy duyệt các item trong chunk hoặc dùng writer dựng sẵn.

**Tự commit trong writer.** Việc commit thủ công có thể phá vỡ rollback của chunk. Hãy để transaction manager của Step quản lý transaction.

**Bắt exception rồi bỏ qua.** Framework không thể áp dụng retry/skip policy đúng nếu writer che giấu lỗi. Hãy ném exception phù hợp hoặc cấu hình skip rõ ràng.

**Không idempotent.** Khi retry hoặc restart, writer có thể ghi trùng. Dùng unique constraint, upsert hoặc idempotency key.

**Giữ chunk sau khi write kết thúc.** Không nên lưu tham chiếu đến Chunk hoặc item mutable để xử lý bất đồng bộ sau khi phương thức kết thúc, trừ khi đã sao chép dữ liệu và quản lý transaction/ownership rõ ràng.

**Ghi nhiều đích nhưng không có kế hoạch phục hồi.** Các hệ thống ngoài transaction có thể không đồng bộ sau lỗi. Cần outbox, staging hoặc cơ chế bù trừ.

**Không quản lý resource.** File hoặc connection cần được đóng đúng lifecycle. Dùng ItemStreamWriter khi writer có trạng thái hoặc resource cần quản lý.

## 14. Kiểm thử ItemWriter

Có thể kiểm thử writer độc lập bằng cách tạo một Chunk với các item mẫu và xác nhận writer thực hiện thao tác ghi như mong đợi.

Ví dụ với một writer tùy chỉnh:

~~~java
@Test
void writesEveryItemInChunk() throws Exception {
    Customer first = new Customer(1L, "An", "an@example.test");
    Customer second = new Customer(2L, "Binh", "binh@example.test");

    Chunk<Customer> chunk = new Chunk<>(List.of(first, second));

    CustomerAuditService auditService = mock(CustomerAuditService.class);
    CustomerAuditWriter writer = new CustomerAuditWriter(auditService);

    writer.write(chunk);

    verify(auditService).record(first);
    verify(auditService).record(second);
}
~~~

Ngoài unit test, integration test của Step nên kiểm tra:

- Writer nhận đúng item đầu ra của processor.
- Chunk cuối nhỏ hơn commit interval vẫn được ghi.
- Khi writer thất bại, transaction hiện tại rollback theo cấu hình.
- Retry hoặc skip hoạt động đúng với loại exception đã chọn.
- Restart không tạo dữ liệu trùng ngoài ý muốn.
- Writer đóng resource và khôi phục state đúng khi restart.
- Composite writer xử lý lỗi ở một delegate theo chính sách phục hồi đã thiết kế.

Đối với JDBC writer, nên kiểm tra kết quả trong database bằng transaction và dữ liệu thử nghiệm thực tế. Đối với file writer, kiểm tra nội dung file, encoding, delimiter, escaping và hành vi khi restart.

## 15. Chọn writer phù hợp với đích dữ liệu

Trước khi triển khai writer, hãy xác định:

1. Đích ghi là database, file, message broker, API hay nhiều hệ thống?
2. Mỗi lần ghi có thể nhận bao nhiêu item?
3. Các thao tác ghi có tham gia transaction của Step không?
4. Nếu một item trong chunk lỗi, cần rollback, retry hay skip?
5. Writer có cần lưu trạng thái để restart không?
6. Có thể ghi trùng khi retry hoặc restart không?
7. Nếu ghi nhiều đích, làm thế nào phục hồi khi chỉ một đích thành công?
8. Có cần giới hạn payload, batch size hoặc tốc độ gọi hệ thống đích không?

Với database, ưu tiên writer JDBC/JPA phù hợp và transaction manager đúng. Với file, dùng FlatFileItemWriter hoặc writer chuyên dụng có lifecycle rõ ràng. Với API hoặc message broker, thiết kế idempotency và cơ chế phát lại an toàn. Với nhiều đích, đánh giá tính nguyên tử và kế hoạch phục hồi trước khi đưa vào vận hành.

Nguyên tắc cốt lõi là ItemWriter nhận một chunk do framework tạo ra và ghi các item trong chunk đó. Spring Batch quản lý vòng đời chunk, transaction, checkpoint và trạng thái Step. Khi writer giữ đúng trách nhiệm ghi, ném lỗi minh bạch và được thiết kế cho retry/restart, quy trình batch có thể ghi dữ liệu hiệu quả mà vẫn kiểm soát được tính nhất quán.

