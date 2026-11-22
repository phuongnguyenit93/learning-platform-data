# Skippable exception

Trong Spring Batch, một exception xảy ra khi đọc, xử lý hoặc ghi item thường làm chunk thất bại và có thể khiến Step dừng. Tuy nhiên, có những lỗi chỉ liên quan đến một bản ghi riêng lẻ, chẳng hạn dòng CSV sai định dạng hoặc dữ liệu không đáp ứng quy tắc nghiệp vụ. Nếu yêu cầu nghiệp vụ cho phép bỏ qua bản ghi đó và tiếp tục xử lý các bản ghi còn lại, có thể cấu hình **skippable exception**.

Skippable exception là loại exception mà chính sách skip của Step cho phép bỏ qua sau khi lỗi được phát hiện. Spring Batch ghi nhận số lượng item hoặc lỗi bị skip, tiếp tục xử lý theo chính sách đã cấu hình và gọi SkipListener khi một lỗi thực sự được chấp nhận để skip.

Không nên xem skip là cách che giấu mọi lỗi. Chỉ skip những lỗi có thể bỏ qua mà không làm dữ liệu đích mất tính nhất quán. Lỗi hạ tầng, lỗi cấu hình hoặc lỗi lập trình thường cần làm Step thất bại hoặc được retry theo chính sách riêng.

## 1. Skippable exception là gì?

Trong chunk-oriented Step, dữ liệu đi qua ba giai đoạn chính:

~~~text
ItemReader
    |
    v
ItemProcessor
    |
    v
ItemWriter
    |
    v
Commit chunk
~~~

Exception có thể phát sinh ở bất kỳ giai đoạn nào:

- **Read:** dữ liệu nguồn không thể parse hoặc không thể chuyển thành item.
- **Process:** item vi phạm quy tắc nghiệp vụ hoặc không thể biến đổi.
- **Write:** dữ liệu không thể ghi vào đích, ví dụ vi phạm constraint hoặc lỗi theo từng bản ghi.

Nếu exception thuộc nhóm skippable và Step còn trong giới hạn skip, Spring Batch có thể bỏ qua lỗi tương ứng và tiếp tục xử lý. Exception không được phép skip, hoặc lỗi vượt giới hạn, sẽ làm Step thất bại nếu không có cơ chế xử lý khác.

Ví dụ Job nhập file đơn hàng có 100.000 dòng. Một vài dòng có số lượng âm hoặc ngày sai định dạng. Nếu nghiệp vụ cho phép đưa những dòng đó vào danh sách rejected và tiếp tục nhập các dòng hợp lệ, có thể skip các exception dữ liệu đã xác định.

~~~text
Dòng 1: hợp lệ       -> xử lý
Dòng 2: hợp lệ       -> xử lý
Dòng 3: sai định dạng -> SKIP
Dòng 4: hợp lệ       -> xử lý
Dòng 5: thiếu mã đơn  -> SKIP
Dòng 6: hợp lệ       -> xử lý
~~~

Skip không có nghĩa exception chưa từng xảy ra. Spring Batch vẫn theo dõi skip count và có thể gọi listener để ứng dụng ghi lại lý do từ chối.

## 2. Cấu hình exception được phép skip

Với Spring Batch 5, có thể cấu hình skip exception trên một fault-tolerant chunk Step bằng các phương thức skip và skipLimit:

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
            .faultTolerant()
            .skip(FlatFileParseException.class)
            .skip(InvalidOrderException.class)
            .skipLimit(50)
            .build();
}
~~~

Trong ví dụ:

- Step chạy theo chunk 100 item.
- FlatFileParseException được phép skip khi reader không parse được dòng file.
- InvalidOrderException được phép skip khi processor phát hiện bản ghi không hợp lệ.
- Tổng số lỗi skip trong Step bị giới hạn ở 50.

Phải gọi faultTolerant() trước các cấu hình retry/skip. Nếu không cấu hình skip policy, mặc định Step không tự ý bỏ qua các exception nghiệp vụ. Khi một exception không được phân loại là skippable, Step sẽ thất bại theo cơ chế xử lý lỗi của framework.

Các exception cần skip nên được chọn cụ thể. Tránh cấu hình skip cho Exception.class hoặc RuntimeException.class một cách rộng rãi vì có thể bỏ qua cả lỗi kết nối, lỗi lập trình hoặc lỗi hệ thống.

## 3. Ý nghĩa của skipLimit

skipLimit xác định số lỗi tối đa được phép bỏ qua trong một Step. Giới hạn này áp dụng tổng hợp cho lỗi đọc, xử lý và ghi, không phải một hạn mức riêng cho từng loại exception.

Ví dụ:

~~~java
.faultTolerant()
.skip(FlatFileParseException.class)
.skip(InvalidOrderException.class)
.skipLimit(10)
~~~

Step có thể tiếp tục sau tối đa 10 lần skip thuộc các loại exception đã khai báo. Khi phát sinh lỗi cần skip tiếp theo làm tổng số vượt giới hạn, Step thất bại.

| Số lỗi skip đã ghi nhận | Kết quả |
| ---: | --- |
| 0 đến 9 | Còn trong giới hạn |
| 10 | Đã dùng hết giới hạn |
| Lỗi cần skip tiếp theo | Vượt giới hạn, Step thất bại |

Vì vậy, skipLimit(10) không có nghĩa Step luôn bỏ qua vô hạn lỗi sau khi đã skip 10 lỗi. Lỗi thứ 11 cần skip sẽ làm Step thất bại.

### Chọn giới hạn theo yêu cầu dữ liệu

Không nên chọn skip limit chỉ để Job luôn chạy đến cuối file. Hãy xem xét:

- Tỷ lệ lỗi dữ liệu có thể chấp nhận.
- Tổng số bản ghi dự kiến.
- Mức độ nghiêm trọng của từng loại lỗi.
- Khả năng đối soát và sửa dữ liệu rejected.
- Yêu cầu chất lượng dữ liệu đầu ra.

Với file 1.000.000 dòng, giới hạn 50 lỗi có ý nghĩa khác với file 100 dòng. Có thể cần kết hợp giới hạn tuyệt đối với kiểm tra tỷ lệ lỗi ở một bước tổng hợp sau khi nhập.

## 4. Phân biệt skip và noSkip

skip khai báo một exception hoặc nhóm exception được phép bỏ qua. noSkip khai báo exception không được bỏ qua, kể cả khi nó nằm trong một nhóm exception rộng hơn đã được cấu hình skip.

Ví dụ:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(Exception.class)
        .noSkip(IllegalStateException.class)
        .skipLimit(100)
        .build();
~~~

Ví dụ này minh họa ý nghĩa của việc loại trừ một exception khỏi nhóm được phép skip. Trong ứng dụng thật, không nên dùng skip(Exception.class) trừ khi có lý do rất đặc biệt và đã phân loại rõ các ngoại lệ nguy hiểm. Cấu hình rộng khiến chính sách khó dự đoán và dễ che giấu lỗi.

Một cách thiết kế dễ hiểu hơn là chỉ khai báo các loại dữ liệu lỗi cụ thể:

~~~java
.faultTolerant()
.skip(FlatFileParseException.class)
.skip(InvalidOrderException.class)
.noSkip(DatabaseUnavailableException.class)
.skipLimit(50)
~~~

Khi cần kết hợp skip và noSkip, hãy xem xét quan hệ kế thừa giữa các exception. Một exception con có thể được phân loại khác với superclass của nó. Kiểm thử các lớp exception thực tế mà reader, processor và writer phát ra để chắc chắn chính sách có kết quả như mong muốn.

## 5. Exception được phân loại ở đâu?

Skip policy được áp dụng cho exception phát sinh trong các giai đoạn của chunk processing. Mỗi giai đoạn có thể cung cấp ngữ cảnh khác nhau:

| Giai đoạn | Ví dụ exception | Có item để ghi nhận? |
| --- | --- | --- |
| Read | FlatFileParseException | Có thể không có item đã parse thành công; exception có thể chứa dòng nguồn |
| Process | InvalidOrderException | Có OrderInput đã đọc được |
| Write | DataIntegrityViolationException | Có item đầu ra hoặc nhóm item đang được ghi |

### Lỗi ở ItemReader

Reader có thể ném FlatFileParseException khi một dòng CSV sai định dạng. Spring Batch có thể skip exception nếu được cấu hình và reader có khả năng tiếp tục đọc sau dòng lỗi.

Ví dụ:

~~~java
.faultTolerant()
.skip(FlatFileParseException.class)
.skipLimit(20)
~~~

Với file reader, cần kiểm tra exception có chứa input line và số dòng hay không. Thông tin đó hữu ích để lưu bản ghi rejected dù chưa tạo được object OrderInput.

### Lỗi ở ItemProcessor

Processor thường phát hiện lỗi nghiệp vụ trên một item đã đọc:

~~~java
public class OrderProcessor
        implements ItemProcessor<OrderInput, Order> {

    @Override
    public Order process(OrderInput input) {
        if (input.getQuantity() == null || input.getQuantity() <= 0) {
            throw new InvalidOrderException(
                    "Quantity must be greater than zero");
        }

        return transform(input);
    }
}
~~~

Nếu InvalidOrderException được khai báo là skippable, item đó có thể được bỏ qua và các item khác tiếp tục xử lý theo chính sách Step.

### Lỗi ở ItemWriter

Writer có thể ném exception khi ghi dữ liệu, ví dụ vi phạm constraint. Tuy nhiên, skip ở write phức tạp hơn vì writer thường nhận cả một chunk, không chỉ một item.

Spring Batch có thể phải rollback chunk và xác định item gây lỗi theo cơ chế fault-tolerant. Việc này phụ thuộc writer có thể được gọi lại an toàn hay không, transaction behavior và cách exception phát sinh. Không nên giả định một exception writer luôn chỉ ảnh hưởng đúng một item.

Nếu writer ghi nhiều item trong một batch statement, database có thể báo lỗi cho cả batch. Hãy kiểm thử khả năng xác định item lỗi, rollback và retry/skip với đúng writer và database đang dùng.

## 6. SkipListener ghi nhận bản ghi bị bỏ qua

Khi một exception thực sự được skip, SkipListener cho phép ứng dụng ghi nhận item hoặc exception cùng lý do:

~~~java
public interface SkipListener<I, O> {

    void onSkipInRead(Throwable t);

    void onSkipInProcess(I item, Throwable t);

    void onSkipInWrite(O item, Throwable t);
}
~~~

Ba callback tương ứng với lỗi ở read, process và write.

Ví dụ listener ghi nhận lỗi xử lý đơn hàng:

~~~java
public class OrderSkipListener
        implements SkipListener<OrderInput, Order> {

    private final RejectedOrderRepository rejectedRepository;

    public OrderSkipListener(
            RejectedOrderRepository rejectedRepository) {
        this.rejectedRepository = rejectedRepository;
    }

    @Override
    public void onSkipInRead(Throwable t) {
        rejectedRepository.save(
                RejectedOrder.fromReadFailure(t));
    }

    @Override
    public void onSkipInProcess(OrderInput item, Throwable t) {
        rejectedRepository.save(
                RejectedOrder.fromInput(item, t.getMessage()));
    }

    @Override
    public void onSkipInWrite(Order item, Throwable t) {
        rejectedRepository.save(
                RejectedOrder.fromOrder(item, t.getMessage()));
    }
}
~~~

Đăng ký listener trong Step:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(FlatFileParseException.class)
        .skip(InvalidOrderException.class)
        .skipLimit(50)
        .listener(orderSkipListener)
        .build();
~~~

SkipListener khác với ItemReadListener hoặc ItemProcessListener. Listener ở read/process có thể quan sát một lần lỗi xảy ra; SkipListener được gọi khi framework xác định lỗi đó đã được skip. Vì vậy, dùng SkipListener phù hợp hơn để ghi nhận danh sách bản ghi bị loại khỏi kết quả cuối cùng.

### Thông tin cần lưu

Một bản ghi rejected thường cần:

- JobInstance hoặc JobExecution ID để truy vết lần chạy.
- Step name và giai đoạn lỗi.
- Business key nếu đã đọc được.
- Số dòng hoặc vị trí nguồn nếu có.
- Loại exception hoặc error code ổn định.
- Thông báo lỗi đã được làm sạch.
- Thời điểm và phiên bản input.

Không nên chỉ lưu message tự do làm khóa phân loại vì nội dung message có thể thay đổi giữa các phiên bản. Hãy dùng error code ổn định nếu cần thống kê và đối soát.

Nếu rejected record được ghi vào cùng database và cùng transaction manager với Step, thao tác lưu có thể tham gia transaction tương ứng. Nếu ghi sang database khác hoặc hệ thống ngoài, không được giả định nó commit cùng chunk. Hãy thiết kế transaction và idempotency rõ ràng.

## 7. Skip khác với filter

Skip và filter đều có thể làm một item không đến writer, nhưng ý nghĩa khác nhau:

| Cơ chế | Cách hoạt động | Ý nghĩa |
| --- | --- | --- |
| Skip | Exception được chính sách cho phép bỏ qua | Item hoặc thao tác gặp lỗi có thể được loại khỏi xử lý |
| Filter | Processor trả về null | Item bị loại theo điều kiện xử lý bình thường |

Ví dụ:

- Đơn hàng có trạng thái CANCELLED và quy tắc báo cáo không nhận đơn đã hủy: processor có thể trả null để filter.
- Dòng CSV thiếu dấu phân cách khiến không thể parse: reader ném FlatFileParseException và Step có thể skip nếu chính sách cho phép.
- Đơn hàng có quantity âm: processor ném InvalidOrderException để skip và ghi nhận rejected.

Filter count và skip count là các counter khác nhau trong StepExecution. Không nên dùng filter để che giấu lỗi dữ liệu cần được kiểm toán.

## 8. Skip khác với retry

Retry và skip phục vụ hai tình huống khác nhau:

- **Retry:** thử lại thao tác thất bại vì lỗi có khả năng tạm thời hoặc có thể phục hồi.
- **Skip:** bỏ qua lỗi đã được xác định là có thể chấp nhận bỏ qua theo nghiệp vụ.

Ví dụ:

| Tình huống | Hướng xử lý thường phù hợp |
| --- | --- |
| Dòng file sai định dạng | Skip nếu có thể lưu thông tin rejected và tiếp tục |
| Số lượng đơn hàng âm | Skip hoặc fail theo quy tắc chất lượng dữ liệu |
| Database tạm mất kết nối | Retry có giới hạn hoặc fail |
| Thiếu index làm query luôn chậm | Điều tra và tối ưu; retry không giải quyết nguyên nhân |
| NullPointerException do bug | Fail và sửa code |

Spring Batch hỗ trợ cấu hình retry và skip cùng một Step. Khi một exception được cả hai policy quan tâm, thứ tự và kết quả xử lý phụ thuộc cấu hình fault-tolerant và retry limit. Một chiến lược thường dùng là retry lỗi tạm thời trước, sau khi hết lần thử mới cân nhắc skip nếu nghiệp vụ cho phép. Hãy kiểm thử chính xác exception classification và hành vi của phiên bản Spring Batch đang sử dụng.

Ví dụ:

~~~java
.faultTolerant()
.retry(TransientDataAccessException.class)
.retryLimit(3)
.skip(InvalidOrderException.class)
.skipLimit(50)
~~~

Trong cấu hình này, lỗi truy cập dữ liệu tạm thời có thể được thử lại tối đa theo retry policy; lỗi dữ liệu InvalidOrderException được xử lý theo skip policy. Không đưa cùng một exception vào cả hai policy nếu chưa xác định rõ ý định và hành vi mong muốn.

## 9. Skip và transaction rollback

Chunk processing thường thực hiện trong transaction. Khi exception phát sinh, transaction có thể rollback tùy loại exception và rollback policy. Với fault-tolerant Step, framework phối hợp retry/skip để quyết định có thể tiếp tục hay phải thất bại.

Một số điểm cần hiểu:

- Exception trong processor có thể làm chunk rollback trước khi framework xử lý skip.
- Exception trong writer có thể khiến toàn chunk rollback.
- Framework có thể gọi lại reader, processor hoặc writer trong quá trình xác định item gây lỗi.
- Writer và processor cần an toàn khi bị gọi lại nếu retry/skip có thể xảy ra.
- Các side effect ngoài transaction database có thể không được rollback.

Ví dụ, nếu writer gửi HTTP request cho từng item rồi ném exception ở item cuối, transaction database rollback không thể thu hồi các request đã gửi trước đó. Khi framework thử lại hoặc skip, các request có thể được gửi lần nữa.

Vì vậy, không nên đặt side effect không idempotent trong processor/writer nếu cơ chế retry/skip có thể gọi lại chúng. Dùng idempotency key, outbox hoặc tách side effect sang bước xử lý riêng.

## 10. Skip trong read có thể tiếp tục đọc như thế nào?

Không phải reader nào cũng có thể tiếp tục sau một exception. Với file reader, lỗi parse thường gắn với một dòng cụ thể và reader có thể chuyển sang dòng tiếp theo tùy implementation.

Với custom reader, nếu exception xảy ra trước khi trạng thái đọc được cập nhật, lần gọi tiếp theo có thể đọc lại cùng item và lặp lỗi. Reader cần có quy tắc rõ ràng về việc tiến vị trí sau một lỗi có thể skip.

Nếu reader truy vấn API hoặc stream từ xa, cần xác định:

- Exception xảy ra trước hay sau khi nguồn đã tiêu thụ item?
- Có thể đọc lại cùng item bằng offset hoặc cursor không?
- Có thể bỏ qua một message lỗi và tiếp tục nhận message kế tiếp không?
- Checkpoint có được cập nhật nhất quán khi lỗi bị skip không?

Không nên khai báo exception là skippable cho một reader không thể tiếp tục an toàn. Nếu nguồn không hỗ trợ phục hồi sau lỗi, Step có thể cần thất bại để tránh bỏ sót dữ liệu.

## 11. Skip trong write và khả năng xác định item lỗi

Writer thường nhận một chunk thay vì từng item riêng lẻ. Khi một lệnh batch insert thất bại, database có thể chỉ trả thông tin lỗi chung cho toàn batch hoặc thông tin constraint không đủ để xác định item cụ thể.

Spring Batch có cơ chế fault-tolerant để xử lý write exception và có thể thử ghi lại từng item trong một số tình huống nhằm xác định item gây lỗi. Tuy nhiên, hành vi này làm tăng số lần gọi writer và yêu cầu writer có thể được gọi lại an toàn.

Ví dụ, writer tự viết:

~~~java
public class OrderWriter implements ItemWriter<Order> {

    private final OrderRepository repository;

    public OrderWriter(OrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) {
        repository.saveAll(chunk.getItems());
    }
}
~~~

Nếu saveAll thất bại vì một bản ghi vi phạm unique constraint, framework có thể cần phân loại lại các item để xác định lỗi. Cách writer và repository thực hiện batch insert ảnh hưởng đến việc xác định item gây lỗi.

Nếu writer không thể được gọi lại an toàn, hoặc có side effect bên ngoài database, cần thiết kế lại trước khi bật skip ở write. Có thể dùng staging table, kiểm tra dữ liệu trước khi ghi, hoặc chia thao tác ghi theo cách có thể xác định lỗi.

## 12. Skip policy tùy chỉnh

Khi phân loại exception không thể diễn đạt gọn bằng skip/noSkip, có thể dùng SkipPolicy tùy chỉnh. Policy nhận exception và số lượng skip hiện tại, sau đó quyết định có cho phép skip hay không.

~~~java
public interface SkipPolicy {
    boolean shouldSkip(Throwable t, long skipCount)
            throws SkipLimitExceededException;
}
~~~

Ví dụ policy đơn giản:

~~~java
public class OrderSkipPolicy implements SkipPolicy {

    private final long skipLimit;

    public OrderSkipPolicy(long skipLimit) {
        this.skipLimit = skipLimit;
    }

    @Override
    public boolean shouldSkip(Throwable throwable, long skipCount) {
        if (throwable instanceof InvalidOrderException) {
            if (skipCount < skipLimit) {
                return true;
            }
            throw new SkipLimitExceededException(
                    "Order skip limit exceeded",
                    throwable);
        }

        return false;
    }
}
~~~

Đăng ký policy tùy chỉnh:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skipPolicy(new OrderSkipPolicy(50))
        .build();
~~~

Ví dụ trên minh họa cách quyết định skip dựa trên loại exception và số lượng đã skip. Trong thực tế, policy cần xử lý exception cause hoặc wrapper phù hợp với exception thực tế từ reader/writer, đồng thời tránh ném SkipLimitExceededException cho lỗi không thuộc nhóm được skip.

Chỉ dùng SkipPolicy tùy chỉnh khi chính sách có điều kiện phức tạp, chẳng hạn giới hạn theo tenant, loại file hoặc tỷ lệ lỗi. Với các quy tắc đơn giản, cấu hình skip và noSkip thường dễ đọc và dễ bảo trì hơn.

## 13. Theo dõi skip count và kết quả Step

StepExecution lưu các counter giúp theo dõi lỗi:

- readSkipCount: số lỗi bị skip trong lúc đọc.
- processSkipCount: số lỗi bị skip trong lúc xử lý.
- writeSkipCount: số lỗi bị skip trong lúc ghi.
- skipCount: tổng số skip của Step.
- readCount, process count, filterCount và writeCount: các counter ở những giai đoạn khác.

Có thể quan sát qua StepExecution:

~~~java
@Component
public class SkipSummaryListener implements StepExecutionListener {

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        log.info(
                "Step {} skips: read={}, process={}, write={}, total={}",
                stepExecution.getStepName(),
                stepExecution.getReadSkipCount(),
                stepExecution.getProcessSkipCount(),
                stepExecution.getWriteSkipCount(),
                stepExecution.getSkipCount());

        return null;
    }
}
~~~

Trả về null giữ nguyên ExitStatus hiện tại. Listener chỉ quan sát và ghi nhận số liệu; không nên tự thay đổi trạng thái Step thành COMPLETED khi skip count cao nếu nghiệp vụ chưa xác nhận kết quả có thể chấp nhận.

Một Step có thể kết thúc COMPLETED dù có skip, nếu các lỗi đều nằm trong chính sách và giới hạn. Điều đó không tự động có nghĩa dữ liệu đầu ra đạt chất lượng. Ứng dụng có thể cần một bước tổng hợp để kiểm tra tỷ lệ rejected và quyết định Job có được publish kết quả hay không.

## 14. Kiểm thử skippable exception

Nên kiểm thử cả trường hợp exception được skip và trường hợp không được skip:

1. Một lỗi parse thuộc nhóm skip xuất hiện trong reader.
2. Một InvalidOrderException xuất hiện trong processor.
3. Một exception không được khai báo skip làm Step thất bại.
4. Số lỗi skip đúng bằng giới hạn.
5. Lỗi cần skip tiếp theo làm Step thất bại vì vượt giới hạn.
6. SkipListener được gọi đúng callback.
7. Rejected record được ghi nhận với thông tin đủ để đối soát.
8. Restart không tạo dữ liệu trùng hoặc bỏ sót checkpoint.

Ví dụ kiểm thử Step với lỗi dữ liệu:

~~~java
@Test
void skipsInvalidOrderAndWritesValidOrders() throws Exception {
    // Reader trả về item hợp lệ, item gây InvalidOrderException,
    // rồi một item hợp lệ khác.
    // Step được cấu hình skip InvalidOrderException.

    JobExecution execution = jobLauncherTestUtils.launchStep(
            "importOrdersStep",
            new JobParametersBuilder()
                    .addString("inputId", "test-file-01", true)
                    .toJobParameters());

    StepExecution stepExecution =
            execution.getStepExecutions().iterator().next();

    assertEquals(BatchStatus.COMPLETED, stepExecution.getStatus());
    assertEquals(1, stepExecution.getProcessSkipCount());
    assertEquals(2, stepExecution.getWriteCount());
}
~~~

Đây là khung minh họa; cần cấu hình test reader, processor, writer và Job phù hợp với ứng dụng. Nên kiểm tra cả nội dung dữ liệu đích và rejected store, không chỉ kiểm tra BatchStatus.

## 15. Những lỗi thường gặp

### Skip mọi exception

Skip Exception.class hoặc RuntimeException.class có thể che giấu lỗi database, cấu hình và bug. Chỉ khai báo loại exception có thể bỏ qua theo nghiệp vụ.

### Không đặt skipLimit

Nếu không giới hạn số lỗi, dữ liệu đầu vào có thể sai hàng loạt nhưng Job vẫn tiếp tục. Dùng giới hạn phù hợp và kiểm tra tỷ lệ lỗi.

### Nhầm skip với filter

Filter là kết quả bình thường của processor trả null. Skip là xử lý một exception được policy cho phép bỏ qua. Dùng đúng semantics để có thống kê chính xác.

### Cho rằng onReadError đồng nghĩa đã skip

Callback lỗi đọc chỉ quan sát exception. Dùng SkipListener để ghi nhận exception thực sự được skip.

### Bỏ qua lỗi writer mà không kiểm tra tính an toàn

Writer có thể ghi một phần hoặc có side effect bên ngoài transaction. Kiểm thử rollback và khả năng gọi lại trước khi bật skip ở write.

### Skip lỗi hạ tầng

Database unavailable hoặc network timeout thường không phải dữ liệu xấu của một item. Retry có giới hạn hoặc fail thường phù hợp hơn.

### Không lưu rejected record

Job có thể COMPLETED nhưng bản ghi lỗi bị mất dấu. Dùng SkipListener hoặc cơ chế quarantine để lưu lý do và nguồn.

### Chọn skip limit quá cao

Giới hạn lớn có thể cho phép Job hoàn tất với dữ liệu đầu ra thiếu quá nhiều. Hãy xác định ngưỡng dựa trên yêu cầu chất lượng dữ liệu.

### Không xem xét retry và skip cùng lúc

Một exception có thể chịu tác động của cả hai policy. Xác định rõ lỗi nào retry trước, lỗi nào skip sau khi retry hết và kiểm thử hành vi thực tế.

## 16. Quy trình thiết kế skip policy

Khi cấu hình skip cho một Step, hãy thực hiện:

1. Liệt kê exception có thể phát sinh ở read, process và write.
2. Phân loại lỗi dữ liệu có thể bỏ qua và lỗi hệ thống phải dừng hoặc retry.
3. Chọn exception class cụ thể cho skip.
4. Dùng noSkip để loại trừ các lỗi nghiêm trọng nếu cần.
5. Chọn skipLimit dựa trên số lượng và tỷ lệ lỗi nghiệp vụ cho phép.
6. Đăng ký SkipListener để lưu thông tin rejected và giai đoạn phát sinh.
7. Kiểm tra writer có thể rollback và được gọi lại an toàn không.
8. Xác định cách xử lý khi vượt skip limit.
9. Theo dõi read/process/write skip count và tỷ lệ rejected.
10. Kiểm thử retry, skip, rollback và restart với dữ liệu đại diện.

Một skip policy tốt phải giải thích được vì sao loại lỗi đó có thể bỏ qua, bản ghi bị bỏ qua được lưu ở đâu và hệ thống sẽ làm gì khi số lỗi vượt ngưỡng.

## Kết luận

Skippable exception là exception được fault-tolerant Step cho phép bỏ qua theo chính sách đã cấu hình. Dùng skip và skipLimit để kiểm soát lỗi dữ liệu ở read, process hoặc write; dùng noSkip để loại trừ lỗi cần làm Step thất bại; và dùng SkipListener để lưu lại bản ghi cùng lý do bị bỏ qua. Hãy phân biệt skip với filter và retry, giới hạn số lỗi chấp nhận được, đồng thời bảo đảm writer, transaction và side effect an toàn khi framework phải rollback hoặc gọi lại thao tác.
