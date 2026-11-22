# Không đưa pipeline item vào tasklet quá lớn

Trong Spring Batch, `Tasklet` phù hợp với một tác vụ có phạm vi rõ ràng, chẳng hạn gọi stored procedure, tạo file điều khiển, dọn dữ liệu tạm hoặc thực hiện một thao tác điều phối. Không nên biến một Tasklet thành nơi tự đọc, xử lý và ghi hàng trăm nghìn hoặc hàng triệu item trong một vòng lặp lớn.

Khi một công việc chủ yếu là pipeline item — đọc từng bản ghi, kiểm tra hoặc chuyển đổi, rồi ghi kết quả — mô hình chunk-oriented processing thường phù hợp hơn. Mô hình này cung cấp sẵn `ItemReader`, `ItemProcessor`, `ItemWriter`, transaction theo chunk, bộ đếm và các cơ chế retry, skip, checkpoint. Nếu tự xây dựng toàn bộ pipeline bên trong một lần gọi `Tasklet.execute()`, ứng dụng phải tự chịu trách nhiệm cho nhiều vấn đề mà Spring Batch đã có cơ chế hỗ trợ.

## 1. Vì sao Tasklet không nên ôm một pipeline item quá lớn?

Một Tasklet có thể thực hiện nhiều thao tác trong `execute()`. Về mặt kỹ thuật, không có giới hạn nào ngăn việc viết vòng lặp đọc file, gọi service, chuyển đổi dữ liệu và ghi database trong cùng một phương thức. Nhưng nếu công việc có khối lượng lớn, cách làm này dễ tạo ra một đơn vị xử lý quá lớn và khó vận hành.

Ví dụ không nên dùng:

```java
@Component
public class ImportAllCustomersTasklet implements Tasklet {

    private final CustomerService customerService;
    private final CustomerRepository customerRepository;

    public ImportAllCustomersTasklet(
            CustomerService customerService,
            CustomerRepository customerRepository) {
        this.customerService = customerService;
        this.customerRepository = customerRepository;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        List<CustomerInput> allCustomers = customerService.loadAllCustomers();
        List<Customer> converted = new ArrayList<>();

        for (CustomerInput input : allCustomers) {
            converted.add(convert(input));
        }

        customerRepository.saveAll(converted);
        return RepeatStatus.FINISHED;
    }
}
```

Tasklet này nạp toàn bộ dữ liệu vào bộ nhớ, chuyển đổi tất cả rồi ghi một lần. Với vài trăm bản ghi, cách làm có thể chấp nhận được nếu giới hạn dữ liệu rõ ràng. Với hàng triệu bản ghi, nó có thể gây áp lực heap, garbage collection, transaction dài và khó tiếp tục sau lỗi.

Một vấn đề khác là vòng lặp tự viết không tự động được Spring Batch quản lý như pipeline chunk. Nếu một item lỗi giữa chừng, Tasklet cần tự quyết định item nào đã xử lý, item nào được retry, item nào được bỏ qua và cách khôi phục sau restart.

## 2. Các rủi ro khi xử lý quá nhiều item trong một Tasklet

### Dùng bộ nhớ tăng theo toàn bộ tập dữ liệu

Nếu Tasklet gọi `loadAll()` hoặc đọc toàn bộ file vào `List`, bộ nhớ cần thiết tăng theo số lượng và kích thước item. Một triệu object có thể tiêu tốn nhiều heap hơn kích thước dữ liệu thô vì JVM còn phải lưu header, reference, collection và các object trung gian.

Khi heap bị sử dụng quá mức, garbage collector phải làm việc nhiều hơn; ứng dụng có thể chậm, phát sinh `OutOfMemoryError` hoặc bị hệ điều hành/container kết thúc. Tình trạng này cũng ảnh hưởng các Job khác và API trực tuyến nếu cùng chạy trong một JVM.

Chunk-oriented processing thường chỉ giữ một nhóm item đang xử lý cùng lúc. Với chunk size 500, ứng dụng không cần giữ toàn bộ một triệu item trong một danh sách chỉ để ghi dữ liệu.

### Một transaction có thể kéo dài quá lâu

Trong `TaskletStep`, mỗi lần gọi `Tasklet.execute()` được quản lý trong transaction của Step. Nếu một lần gọi thực hiện vòng lặp hàng chục phút rồi mới trả về, transaction có thể giữ connection và khóa database trong thời gian dài.

Hệ quả có thể gồm:

- Transaction timeout trước khi Tasklet hoàn tất.
- Khóa database được giữ lâu, làm các transaction khác phải chờ.
- Transaction log hoặc undo data tăng nhanh.
- Connection pool bị chiếm dụng lâu.
- Khi rollback, toàn bộ thay đổi thuộc transaction lớn có thể bị hoàn tác, dù phần lớn công việc đã thực hiện.

Với chunk processing, mỗi chunk có transaction riêng theo cấu hình Step. Các chunk đã commit vẫn được giữ lại nếu một chunk sau đó thất bại. Điều này giới hạn phạm vi rollback và cho phép Job tiếp tục từ checkpoint đã lưu khi reader hỗ trợ restart.

### Khó xác định tiến độ và vị trí lỗi

Nếu một Tasklet chỉ có một lời gọi `execute()`, metadata Step chủ yếu phản ánh trạng thái của lần thực thi đó. Nếu Tasklet tự xử lý 500.000 item rồi thất bại ở item thứ 450.000, Spring Batch không tự biết vị trí đó trừ khi code Tasklet tự lưu tiến độ.

Người vận hành có thể chỉ thấy Step `FAILED` mà không có bộ đếm đọc/ghi theo item, không biết bao nhiêu item đã hoàn tất và không biết có thể tiếp tục từ đâu. Muốn có thông tin này, Tasklet phải tự ghi log, cập nhật bộ đếm và lưu checkpoint.

Chunk processing cung cấp các bộ đếm như `readCount`, `writeCount`, `filterCount`, skip count và thông tin execution context của reader. Những thông tin đó giúp theo dõi tiến độ chi tiết hơn.

### Retry và skip phải tự triển khai

Trong một pipeline tự viết bằng vòng lặp, nếu item thứ 300 gặp lỗi, Tasklet phải tự định nghĩa:

- Có retry item đó không và tối đa bao nhiêu lần?
- Có bỏ qua item không hợp lệ hay phải dừng toàn bộ Step?
- Nếu retry thành công, tiếp tục từ item nào?
- Nếu lỗi xảy ra sau khi hệ thống ngoài đã nhận request, làm sao tránh gửi lại tác dụng phụ?

Chunk-oriented Step có cấu hình fault tolerance để retry hoặc skip những exception được chọn, kèm giới hạn và listener phù hợp. Điều này không loại bỏ nhu cầu thiết kế idempotency, nhưng tạo ra cơ chế chuẩn để quản lý lỗi theo item/chunk.

### Khó restart sau khi ứng dụng dừng

Giả sử Tasklet đọc một file 1 GB, xử lý đến 90% rồi máy chủ khởi động lại. Nếu Tasklet không lưu checkpoint, lần restart có thể phải đọc và xử lý lại từ đầu. Nếu nó đã ghi một phần dữ liệu ra hệ thống đích, việc chạy lại có thể tạo dữ liệu trùng.

Chunk-oriented processing kết hợp `ItemStream` và `ExecutionContext` có thể lưu vị trí đọc tại ranh giới commit. Khi restart, reader có hỗ trợ lưu trạng thái có thể tiếp tục từ checkpoint. Các chunk đã commit được giữ lại; phần chưa commit được xử lý lại theo cấu hình và trạng thái reader.

## 3. So sánh Tasklet lớn với chunk-oriented processing

| Khía cạnh | Tasklet tự xử lý toàn bộ pipeline | Chunk-oriented processing |
|---|---|---|
| Đơn vị xử lý | Toàn bộ vòng lặp hoặc logic tự viết trong `execute()` | Một nhóm item theo chunk size |
| Bộ nhớ | Dễ tăng theo toàn bộ tập dữ liệu nếu nạp tất cả | Thường giới hạn ở nhóm item đang xử lý và buffer của reader |
| Transaction | Có thể kéo dài suốt lần gọi Tasklet | Transaction thường được commit theo từng chunk |
| Retry/skip theo item | Phải tự viết logic | Có cơ chế fault tolerance của Step |
| Theo dõi tiến độ | Phải tự cập nhật log, counter và trạng thái | Có bộ đếm StepExecution và metadata chunk |
| Restart | Phải tự lưu và khôi phục tiến độ | Reader/ItemStream có thể dùng ExecutionContext làm checkpoint |
| Phù hợp | Tác vụ đơn, có giới hạn rõ hoặc thao tác set-based | Pipeline đọc, xử lý và ghi số lượng lớn item |

Tasklet không phải lúc nào cũng kém hiệu quả. Một lệnh SQL set-based có thể cập nhật hàng triệu hàng nhanh hơn việc đọc từng item qua Java. Vấn đề là dùng Tasklet để tự triển khai một pipeline item lớn mà không có lý do phù hợp.

## 4. Chuyển pipeline lớn sang chunk-oriented processing

Giả sử cần import 500.000 khách hàng từ file CSV. Mỗi dòng cần được kiểm tra, chuẩn hóa và ghi vào database.

Thay vì nạp toàn bộ file vào một `List` trong Tasklet, hãy tách pipeline thành ba thành phần:

```text
CSV file
   |
   v
ItemReader<CustomerInput>
   |
   v
ItemProcessor<CustomerInput, Customer>
   |
   v
ItemWriter<Customer>
   |
   v
Database

Mỗi chunk được ghi và commit theo cấu hình.
```

### Reader đọc từng dòng

```java
@Bean
@StepScope
FlatFileItemReader<CustomerInput> customerReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<CustomerInput>()
            .name("customerReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("customerId", "fullName", "email")
            .targetType(CustomerInput.class)
            .build();
}
```

Reader lấy từng dòng và trả về một `CustomerInput`. Khi hết file, reader trả `null` để báo EOF. Reader có hỗ trợ `ItemStream` có thể lưu vị trí đọc để phục vụ restart.

### Processor xử lý một item

```java
@Bean
ItemProcessor<CustomerInput, Customer> customerProcessor() {
    return input -> {
        if (input.customerId() == null || input.customerId().isBlank()) {
            throw new InvalidCustomerException("customerId is required");
        }

        return new Customer(
                input.customerId().trim(),
                input.fullName().trim(),
                input.email().trim().toLowerCase());
    };
}
```

Processor chỉ xử lý item hiện tại, không giữ toàn bộ danh sách và không cần biết chunk có bao nhiêu item.

### Writer ghi một chunk

```java
@Bean
JdbcBatchItemWriter<Customer> customerWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Customer>()
            .dataSource(dataSource)
            .sql("""
                    INSERT INTO customers(customer_id, full_name, email)
                    VALUES (:customerId, :fullName, :email)
                    """)
            .beanMapped()
            .build();
}
```

Writer nhận danh sách item đã xử lý trong chunk và có thể dùng batch operation để ghi hiệu quả vào database.

### Cấu hình Step với commit interval

```java
@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<CustomerInput> customerReader,
        ItemProcessor<CustomerInput, Customer> customerProcessor,
        ItemWriter<Customer> customerWriter) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<CustomerInput, Customer>chunk(500, transactionManager)
            .reader(customerReader)
            .processor(customerProcessor)
            .writer(customerWriter)
            .build();
}
```

Với chunk size 500, Spring Batch đọc và xử lý tối đa 500 item, gọi writer cho nhóm đó rồi commit transaction. Nếu file có 500.000 dòng và không có item bị lọc hoặc lỗi làm thay đổi luồng, có khoảng 1.000 chunk cần xử lý. Chunk cuối cùng có thể nhỏ hơn nếu số item không chia hết.

## 5. Thêm retry và skip cho pipeline item

Chunk-oriented Step có thể cấu hình xử lý lỗi theo loại exception. Ví dụ, lỗi dữ liệu khách hàng được phép skip với giới hạn, còn lỗi database tạm thời có thể retry:

```java
@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<CustomerInput> customerReader,
        ItemProcessor<CustomerInput, Customer> customerProcessor,
        ItemWriter<Customer> customerWriter) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<CustomerInput, Customer>chunk(500, transactionManager)
            .reader(customerReader)
            .processor(customerProcessor)
            .writer(customerWriter)
            .faultTolerant()
            .skip(InvalidCustomerException.class)
            .skipLimit(100)
            .retry(TransientDataAccessException.class)
            .retryLimit(3)
            .build();
}
```

Đây là ví dụ minh họa chính sách lỗi. Chỉ skip khi nghiệp vụ cho phép loại bản ghi đó ra khỏi kết quả; chỉ retry lỗi có khả năng tự hết. Cần lưu lại item bị skip và nguyên nhân để có thể sửa dữ liệu hoặc xử lý bù. Với writer có tác dụng phụ ngoài database, cần thêm idempotency để retry không tạo hành động lặp.

## 6. Khi Tasklet vẫn là lựa chọn phù hợp

Không phải cứ số lượng bản ghi lớn là bắt buộc phải dùng chunk. Nếu database có thể thực hiện công việc bằng một lệnh set-based hiệu quả, Tasklet gọi service hoặc stored procedure có thể là lựa chọn tốt.

Ví dụ, xóa các bản ghi staging đã hết hạn bằng một câu SQL:

```java
@Component
public class DeleteExpiredStagingTasklet implements Tasklet {

    private final JdbcTemplate jdbcTemplate;

    public DeleteExpiredStagingTasklet(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        int deleted = jdbcTemplate.update("""
                DELETE FROM staging_records
                WHERE expires_at < CURRENT_TIMESTAMP
                """);

        contribution.incrementWriteCount(deleted);
        return RepeatStatus.FINISHED;
    }
}
```

Tasklet này không đọc từng bản ghi vào Java. Database thực hiện thao tác theo tập dữ liệu và trả về số hàng đã xóa. Cách làm có thể hiệu quả hơn một pipeline Java nếu thao tác đơn giản, có thể thực hiện nguyên tử và transaction có thời gian phù hợp.

Tuy nhiên, một câu lệnh xóa hàng triệu dòng vẫn có thể tạo transaction lớn, giữ khóa và sinh transaction log đáng kể. Nếu database không xử lý tốt thao tác một lần, có thể chia thành các lần xóa có giới hạn, ví dụ mỗi lần xóa một nhóm ID, rồi trả `CONTINUABLE` để TaskletStep lặp tiếp. Cách này cần điều kiện dừng, tính idempotent và cơ chế ghi nhận tiến độ phù hợp.

Tasklet cũng phù hợp với:

- Gọi một stored procedure có ranh giới và thời gian thực thi được kiểm soát.
- Tạo một file manifest hoặc file điều khiển.
- Kiểm tra điều kiện trước khi bắt đầu pipeline.
- Đổi trạng thái một lô dữ liệu bằng một thao tác set-based.
- Gọi một service điều phối để khởi tạo công việc khác.

## 7. Nếu cần chia Tasklet thành nhiều lượt

Tasklet có thể trả `RepeatStatus.CONTINUABLE` để yêu cầu Spring Batch gọi `execute()` thêm lần nữa. Cách này hữu ích cho một tác vụ có thể chia thành các lượt nhỏ, ví dụ xóa dữ liệu theo từng nhóm ID. Mỗi lần gọi có thể xử lý một nhóm giới hạn rồi kết thúc transaction của lượt đó.

Ví dụ khái quát:

```java
@Component
public class PurgeOldRecordsTasklet implements Tasklet {

    private final PurgeService purgeService;

    public PurgeOldRecordsTasklet(PurgeService purgeService) {
        this.purgeService = purgeService;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        int deleted = purgeService.deleteNextPage(500);
        contribution.incrementWriteCount(deleted);

        return deleted == 0
                ? RepeatStatus.FINISHED
                : RepeatStatus.CONTINUABLE;
    }
}
```

Đây là một tác vụ lặp có giới hạn mỗi lượt, không phải sự thay thế tổng quát cho chunk processing. Nếu công việc thực chất cần reader, processor, writer theo từng item, cần skip/retry theo item và checkpoint reader, hãy dùng chunk-oriented Step để framework quản lý các phần đó.

Khi Tasklet lặp nhiều lượt, cần bảo đảm:

- Mỗi lần gọi có tiến triển hữu hình.
- Có điều kiện dừng chắc chắn để tránh lặp vô hạn.
- Các thao tác đã commit có thể được nhận diện khi restart.
- Không tạo tác dụng phụ trùng khi một lượt bị retry hoặc thực hiện lại.
- Có log và metadata đủ để người vận hành biết đã xử lý đến đâu.

## 8. Những yếu tố cần cân nhắc khi tách pipeline

Khi chuyển một Tasklet lớn sang chunk-oriented processing, nên xác định rõ ranh giới trách nhiệm của từng thành phần:

| Thành phần | Trách nhiệm |
|---|---|
| `ItemReader` | Đọc một item tiếp theo và trả `null` khi hết input; hỗ trợ checkpoint nếu cần restart |
| `ItemProcessor` | Kiểm tra, biến đổi hoặc lọc một item; tránh giữ trạng thái mutable dùng chung |
| `ItemWriter` | Ghi nhóm item của chunk; bảo đảm cách ghi an toàn khi retry |
| `Step` | Cấu hình chunk size, transaction manager, retry, skip và listener |
| `JobRepository` | Lưu metadata Job/Step và trạng thái thực thi |

Một số câu hỏi thiết kế:

1. Nguồn dữ liệu có thể đọc tuần tự hoặc theo trang không?
2. Có thể xác định thứ tự ổn định và phạm vi dữ liệu cho mỗi JobInstance không?
3. Một item có thể xử lý độc lập hay phải dựa vào item trước đó?
4. Writer có thể ghi theo lô không, và transaction bao phủ resource nào?
5. Nếu chunk lỗi, item nào có thể được đọc hoặc ghi lại?
6. Có cần skip bản ghi lỗi, lưu danh sách lỗi và xử lý bù không?
7. Reader có thể lưu checkpoint và khôi phục vị trí sau restart không?
8. Có tác dụng phụ ở hệ thống ngoài cần idempotency không?

Không phải pipeline nào cũng có thể chuyển thẳng sang chunk processing. Nếu nghiệp vụ yêu cầu xử lý theo thứ tự và trạng thái tích lũy, có thể cần phân nhóm dữ liệu theo khóa nghiệp vụ hoặc dùng nhiều Step. Nếu một thao tác phụ thuộc toàn bộ tập dữ liệu, có thể tách thành Step tổng hợp sau khi các Step xử lý item hoàn tất.

## 9. Tác động đến hiệu năng và khả năng vận hành

Chunk size là tham số cần đo và điều chỉnh. Chunk quá nhỏ có thể làm tăng số lần commit và round trip; chunk quá lớn có thể tăng bộ nhớ và thời gian transaction. Không nên chọn một giá trị chỉ dựa trên cảm tính.

Khi so sánh Tasklet lớn với chunk processing, hãy đo:

- Tổng thời gian Job và throughput (item/giây).
- Heap usage, garbage collection và CPU.
- Thời gian transaction, lock wait và connection pool.
- Số lượng item đọc, ghi, lọc và skip.
- Số lần commit, rollback và retry.
- Thời gian khôi phục sau khi mô phỏng lỗi giữa chừng.
- Tải phát sinh lên database và service phụ thuộc.

Một Tasklet set-based có thể nhanh hơn chunk vì database xử lý dữ liệu gần nơi lưu trữ. Một chunk Step có thể đáng tin cậy hơn cho pipeline cần xử lý từng item. Lựa chọn đúng dựa trên bản chất công việc và giới hạn vận hành, không dựa riêng vào số dòng dữ liệu.

## 10. Các lỗi thường gặp

**Nạp toàn bộ dữ liệu vào một List:** bộ nhớ tăng theo khối lượng dữ liệu và có thể làm JVM hết heap. Dùng reader tuần tự hoặc paging nếu cần xử lý nhiều item.

**Đọc, xử lý và ghi hàng triệu item trong một `execute()`:** transaction có thể kéo dài, tiến độ khó quan sát và lỗi giữa chừng buộc code tự khôi phục. Tách thành chunk nếu đây là pipeline item.

**Tự viết retry/skip sơ sài:** có thể bỏ qua lỗi quan trọng hoặc lặp tác dụng phụ. Dùng fault-tolerant Step khi phù hợp và xác định chính sách lỗi theo nghiệp vụ.

**Không có checkpoint:** restart có thể phải làm lại toàn bộ công việc. Dùng reader hỗ trợ `ItemStream` hoặc lưu tiến độ có kiểm soát.

**Chọn chunk size quá lớn:** giảm số lần commit nhưng có thể làm tăng bộ nhớ, thời gian giữ transaction và phạm vi rollback.

**Dùng chunk cho một lệnh SQL set-based đơn giản:** việc đọc từng item qua Java có thể tốn tài nguyên hơn để database tự thực hiện một thao tác tập hợp.

**Giả định rollback database hoàn tác service ngoài:** REST API, email hoặc file system thường không tham gia transaction của database. Cần idempotency và đối soát.

## Kết luận

Không nên dùng một Tasklet để tự nạp, xử lý và ghi một pipeline có khối lượng item lớn trong một lần `execute()`. Cách làm này dễ tiêu tốn bộ nhớ, giữ transaction lâu, thiếu bộ đếm theo item và buộc ứng dụng tự xây dựng retry, skip, checkpoint cùng cơ chế restart. Với pipeline đọc–xử lý–ghi nhiều item, chunk-oriented processing cung cấp ranh giới transaction, reader/processor/writer, fault tolerance và metadata tiến độ phù hợp hơn. Tasklet vẫn là lựa chọn tốt cho tác vụ đơn, thao tác set-based hoặc công việc điều phối có phạm vi rõ ràng; điều quan trọng là chọn mô hình theo bản chất công việc và thiết kế khả năng phục hồi ngay từ đầu.
