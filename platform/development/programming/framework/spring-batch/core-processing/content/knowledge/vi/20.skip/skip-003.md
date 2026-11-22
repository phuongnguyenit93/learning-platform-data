# SkipPolicy trong Spring Batch

Trong Spring Batch, một item có thể gặp lỗi khi đọc, xử lý hoặc ghi. Không phải lỗi nào cũng buộc toàn bộ step thất bại. Với những lỗi gắn với một bản ghi cụ thể và có thể loại bỏ an toàn, ứng dụng có thể cho phép step bỏ qua item đó rồi tiếp tục xử lý phần còn lại.

SkipPolicy là thành phần quyết định một exception có được phép skip hay không. Nó giúp phân biệt lỗi dữ liệu có thể chấp nhận với lỗi hạ tầng hoặc lỗi nghiêm trọng cần dừng job. Có thể khai báo chính sách bằng các phương thức skip(), noSkip(), skipLimit() hoặc triển khai SkipPolicy tùy chỉnh khi quy tắc nghiệp vụ phức tạp hơn.

## 1. SkipPolicy là gì?

SkipPolicy là một hợp đồng của Spring Batch dùng để đánh giá exception phát sinh trong chunk processing. Policy nhận exception và số lượng item đã bị skip, sau đó quyết định có cho phép bỏ qua exception hiện tại hay không.

Hợp đồng cơ bản:

```java
public interface SkipPolicy {

    boolean shouldSkip(Throwable t, long skipCount)
        throws SkipLimitExceededException;
}
```

Hai tham số có ý nghĩa:

- t: exception đang được xem xét.
- skipCount: số item đã bị skip trong step trước lần đánh giá hiện tại.

Nếu policy trả về true, exception được xem là skippable và framework có thể bỏ qua item tương ứng, tùy giai đoạn xảy ra lỗi. Nếu policy trả về false, exception không được skip và thường làm step thất bại sau khi các cơ chế retry phù hợp đã được áp dụng. Policy cũng có thể ném SkipLimitExceededException để báo giới hạn skip đã bị vượt.

SkipPolicy chỉ quyết định có được skip hay không. Nó không lưu bản ghi lỗi, không ghi log thay ứng dụng và không quyết định retry. Các trách nhiệm đó thuộc listener, writer hoặc retry policy tương ứng.

## 2. Skip xảy ra ở những giai đoạn nào?

Trong chunk-oriented step, exception có thể xuất hiện ở ba giai đoạn:

| Giai đoạn | Ví dụ | Callback skip tương ứng |
| --- | --- | --- |
| Read | File có dòng sai định dạng; reader không thể parse một bản ghi. | SkipListener.onSkipInRead(Throwable) |
| Process | Processor phát hiện một bản ghi không hợp lệ và ném exception. | SkipListener.onSkipInProcess(item, Throwable) |
| Write | Writer không thể ghi một output item do constraint hoặc dữ liệu không hợp lệ. | SkipListener.onSkipInWrite(item, Throwable) |

Policy đánh giá exception theo cấu hình step, bất kể nó phát sinh ở phase nào. Nếu exception được phép skip, Spring Batch ghi nhận bộ đếm tương ứng như readSkipCount, processSkipCount hoặc writeSkipCount.

Không nhầm skip với hai trường hợp khác:

- ItemReader.read() trả về null có nghĩa đã hết input, không phải exception và không phải skip.
- ItemProcessor.process() trả về null có nghĩa item được filter theo quy tắc nghiệp vụ, không phải skip.

Ví dụ, một order đã hủy có thể được processor filter bằng cách trả về null. Một dòng CSV sai cấu trúc có thể khiến reader ném FlatFileParseException; nếu policy cho phép, dòng đó được skip. Hai trường hợp này cần được thống kê riêng.

## 3. Khi nào nên skip và khi nào nên fail?

Skip phù hợp khi exception đại diện cho một item riêng lẻ, việc bỏ item đó không làm mất khả năng xử lý các item tiếp theo và nghiệp vụ chấp nhận kết quả thiếu item đó.

Ví dụ có thể cân nhắc skip:

- Một dòng CSV không đúng định dạng nhưng các dòng khác độc lập.
- Một bản ghi thiếu trường tùy chọn hoặc vi phạm quy tắc có thể loại bỏ.
- Một output item vi phạm unique constraint do dữ liệu trùng mà nghiệp vụ quy định bỏ qua.

Những lỗi thường không nên skip:

- Mất kết nối database khiến reader không biết vị trí đọc tiếp theo.
- Sai credential hoặc không có quyền truy cập nguồn dữ liệu.
- File đầu vào bắt buộc không tồn tại.
- Lỗi lập trình như NullPointerException do bug trong processor.
- Lỗi khiến toàn bộ dữ liệu sau vị trí hiện tại không thể diễn giải đúng.

Với lỗi tạm thời như timeout hoặc deadlock, retry có thể phù hợp hơn skip. Bỏ qua một lỗi kết nối có thể khiến cả phần dữ liệu còn lại không được đọc mà job vẫn báo hoàn tất. Quyết định phải dựa trên bản chất exception và khả năng tiếp tục an toàn của reader/writer.

## 4. Cấu hình skip bằng skip(), noSkip() và skipLimit()

Với các quy tắc đơn giản, không cần tự viết SkipPolicy. Có thể khai báo trực tiếp trên fault-tolerant step:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, OrderEntity> processor,
        ItemWriter<OrderEntity> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, OrderEntity>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(FlatFileParseException.class)
        .skip(InvalidOrderException.class)
        .noSkip(IllegalStateException.class)
        .skipLimit(20)
        .build();
}
```

Ý nghĩa:

- faultTolerant() bật cấu hình fault tolerance cho chunk step.
- skip(FlatFileParseException.class) cho phép bỏ qua lỗi parse file.
- skip(InvalidOrderException.class) cho phép bỏ qua lỗi nghiệp vụ được phân loại cụ thể.
- noSkip(IllegalStateException.class) đánh dấu loại exception phải được xem là không thể skip, kể cả khi một rule rộng hơn có thể khớp.
- skipLimit(20) đặt giới hạn tổng số item được skip trong step.

skip() và noSkip() làm việc với kiểu exception, bao gồm quan hệ kế thừa của exception. Vì vậy, hãy chú ý khi khai báo lớp cha rộng. Nếu cho phép skip một lớp quá tổng quát, nhiều exception con không mong muốn cũng có thể được xem là skippable.

Ví dụ, nếu cấu hình skip(Exception.class), cần xem xét cẩn thận những lỗi hệ thống như lỗi xác thực hoặc lỗi trạng thái. Tốt hơn là liệt kê các exception dữ liệu cụ thể và để những lỗi chưa được phân loại làm step thất bại.

## 5. Skip limit được tính như thế nào?

skipLimit giới hạn tổng số skip của step. Nó được tính chung cho lỗi đọc, xử lý và ghi, không phải một giới hạn độc lập cho từng phase.

Ví dụ với:

```java
.faultTolerant()
.skip(InvalidOrderException.class)
.skipLimit(3)
```

Step có thể chấp nhận ba item bị skip. Khi một item tiếp theo cần skip khiến tổng số vượt quá giới hạn, step thất bại với SkipLimitExceededException.

| Số skip đã xảy ra | Kết quả khi có thêm một lỗi cần skip |
| ---: | --- |
| 0 | Có thể skip lỗi đầu tiên. |
| 1 | Có thể skip lỗi tiếp theo. |
| 2 | Có thể skip lỗi thứ ba. |
| 3 | Lỗi tiếp theo vượt giới hạn; step thất bại. |

Nếu skipLimit không được cấu hình, mặc định là 0; không có item nào được phép skip theo giới hạn mặc định. Giá trị limit cần dựa trên quy tắc nghiệp vụ, quy mô dữ liệu và mức độ chấp nhận lỗi của hệ thống.

Không nên đặt limit quá cao chỉ để job luôn hoàn tất. Ví dụ, một file có 100.000 dòng nhưng 30.000 dòng bị skip có thể cho thấy file sai định dạng trên diện rộng. Một giới hạn hợp lý giúp step dừng sớm để tránh tạo kết quả thiếu dữ liệu mà không ai phát hiện.

## 6. Skip count được tính chung giữa các phase

Giả sử skipLimit(5) và step đã có:

- 2 read skip do dòng CSV sai định dạng.
- 2 process skip do order không hợp lệ.
- 1 write skip do dữ liệu vi phạm constraint.

Tổng skip count đã bằng 5. Một item tiếp theo cần skip sẽ vượt giới hạn, dù nó phát sinh ở read, process hay write.

Điều này quan trọng khi đặt ngưỡng. Nếu muốn giám sát riêng tỷ lệ lỗi đọc và lỗi xử lý, có thể dùng các bộ đếm riêng của StepExecution hoặc metric trong listener; nhưng skip limit tiêu chuẩn vẫn là giới hạn tổng của step.

Các bộ đếm thường dùng:

| Bộ đếm | Ý nghĩa |
| --- | --- |
| readSkipCount | Số item bị skip ở reader. |
| processSkipCount | Số item bị skip ở processor. |
| writeSkipCount | Số item bị skip ở writer. |
| readCount | Số item reader cung cấp thành công. |
| filterCount | Số item processor filter bằng cách trả về null. |

Không cộng filterCount vào skip count. Filtering không phải lỗi và không sử dụng SkipPolicy.

## 7. Exception classification và thứ tự quy tắc

Chọn đúng loại exception là phần quan trọng nhất của skip policy. Một lớp exception cha có thể đại diện cho nhiều lỗi con với ý nghĩa khác nhau. Ví dụ, DataAccessException có thể bao gồm lỗi tạm thời, lỗi constraint hoặc lỗi cấu hình truy cập dữ liệu.

Hãy ưu tiên phân loại cụ thể:

```java
.faultTolerant()
.skip(FlatFileParseException.class)
.skip(InvalidOrderException.class)
.noSkip(AccessDeniedException.class)
.noSkip(IllegalStateException.class)
.skipLimit(25)
```

Ví dụ này cho phép skip các lỗi dữ liệu được biết trước và loại trừ một số lỗi không thể phục hồi. Khi dùng lớp cha rộng cùng lớp con cụ thể, hãy đọc quy tắc phân loại của phiên bản Spring Batch đang sử dụng và viết test cho các exception có quan hệ kế thừa.

Một cách phân loại tốt nên trả lời được:

- Exception có chỉ ra một item cụ thể không?
- Reader có thể tiếp tục đọc item tiếp theo không?
- Item có thể được loại bỏ mà không làm sai kết quả nghiệp vụ không?
- Lỗi có thể hết sau một lần retry không?
- Lỗi có phải do cấu hình hoặc bug cần dừng ngay không?

Không nên dựa vào nội dung message của exception để phân loại nếu có thể dùng kiểu exception riêng. Message có thể thay đổi theo driver, ngôn ngữ hoặc phiên bản thư viện.

## 8. Tự triển khai SkipPolicy

Khi quy tắc phụ thuộc vào nhiều điều kiện, có thể triển khai interface SkipPolicy. Ví dụ policy chỉ cho phép skip InvalidOrderException và FlatFileParseException, với giới hạn tổng là 10:

```java
public class ImportSkipPolicy implements SkipPolicy {

    private static final long SKIP_LIMIT = 10;

    @Override
    public boolean shouldSkip(Throwable throwable, long skipCount)
            throws SkipLimitExceededException {

        if (!isSkippable(throwable)) {
            return false;
        }

        if (skipCount >= SKIP_LIMIT) {
            throw new SkipLimitExceededException(
                "Skip limit of " + SKIP_LIMIT + " exceeded",
                skipCount
            );
        }

        return true;
    }

    private boolean isSkippable(Throwable throwable) {
        return throwable instanceof InvalidOrderException
            || throwable instanceof FlatFileParseException;
    }
}
```

Policy này:

1. Phân loại exception trước.
2. Trả về false với loại lỗi không được phép skip.
3. Kiểm tra số skip đã xảy ra.
4. Ném SkipLimitExceededException khi giới hạn đã đạt.
5. Chỉ trả về true cho lỗi phù hợp và còn trong giới hạn.

Khi tự triển khai policy, chính policy phải xử lý giới hạn. Không nên giả định skipLimit() sẽ tự động áp dụng giống hệt khi custom policy đã thay thế policy được tạo từ các khai báo skip().

Đăng ký custom policy:

```java
@Bean
SkipPolicy importSkipPolicy() {
    return new ImportSkipPolicy();
}

@Bean
Step importOrdersStep(JobRepository jobRepository,
                      PlatformTransactionManager transactionManager,
                      ItemReader<Order> reader,
                      ItemProcessor<Order, OrderEntity> processor,
                      ItemWriter<OrderEntity> writer,
                      SkipPolicy importSkipPolicy) {
    return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, OrderEntity>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skipPolicy(importSkipPolicy)
        .build();
}
```

Khi dùng skipPolicy(), hãy đặt toàn bộ logic phân loại và giới hạn trong policy đó. Tránh trộn nhiều cách cấu hình skip khiến người đọc khó xác định quy tắc nào đang có hiệu lực.

## 9. SkipPolicy phụ thuộc vào dữ liệu nghiệp vụ

Một số hệ thống cần quyết định skip dựa trên loại lỗi và ngữ cảnh. Ví dụ, chỉ cho phép skip lỗi validation nếu file thuộc loại dữ liệu không bắt buộc đầy đủ; còn file đối soát tài chính phải dừng khi có bất kỳ lỗi validation nào.

Không phải mọi SkipPolicy đều có sẵn StepExecution hoặc item đầu vào. Hợp đồng chuẩn chỉ nhận Throwable và skipCount. Nếu quyết định cần dữ liệu nghiệp vụ, có thể:

- Mã hóa loại lỗi vào exception riêng, ví dụ OptionalRecordValidationException.
- Dùng exception subclass khác nhau cho các nhóm dữ liệu.
- Tạo policy bean với cấu hình cố định theo step.
- Đưa quy tắc quyết định vào service/processor và chỉ ném exception phân loại rõ.
- Dùng StepExecutionListener hoặc context để thiết lập trạng thái trước, nếu policy được thiết kế để nhận thông tin đó qua cơ chế an toàn.

Không nên dùng biến static hoặc ThreadLocal tùy tiện để truyền item vào policy. Những cách đó dễ sai khi step chạy đa luồng hoặc partitioned.

Ví dụ, processor có thể ném hai loại exception:

```java
if (order.isOptionalRecord() && !order.isValid()) {
    throw new OptionalRecordValidationException(order.getId());
}

if (!order.isValid()) {
    throw new MandatoryRecordValidationException(order.getId());
}
```

Policy có thể cho phép skip loại optional và từ chối loại mandatory. Quy tắc được thể hiện qua type rõ ràng, dễ test và không phụ thuộc vào chuỗi message.

## 10. Kết hợp RetryPolicy và SkipPolicy

Retry và skip giải quyết hai tình huống khác nhau:

- Retry thử lại một thao tác có khả năng thành công nếu lỗi tạm thời biến mất.
- Skip chấp nhận loại bỏ item lỗi khi nghiệp vụ cho phép tiếp tục mà không có item đó.

Có thể cấu hình cả hai trong một fault-tolerant step:

```java
.faultTolerant()
.retry(TransientDataAccessException.class)
.retryLimit(3)
.skip(InvalidOrderException.class)
.skipLimit(20)
```

Trong ví dụ:

- TransientDataAccessException có thể được thử lại tối đa theo retry limit.
- InvalidOrderException được phép skip trong giới hạn skip.
- Lỗi không thuộc retry hoặc skip policy sẽ làm step thất bại.

Không nên cho cùng một loại exception vừa retry vừa skip mà không có chủ đích. Nếu một lỗi kết nối tạm thời được retry nhưng vẫn thất bại, skip nó có thể khiến reader mất khả năng tiếp tục. Chỉ kết hợp hai policy cho cùng exception khi đã hiểu cách reader/writer phục hồi và nghiệp vụ chấp nhận bỏ item đó.

Khi retry thành công, item không bị skip và SkipListener không được gọi cho lỗi tạm thời đã phục hồi. Nếu retry không thành công, framework tiếp tục xử lý theo policy còn lại phù hợp với cấu hình và loại exception.

## 11. SkipPolicy và rollback

Skip không có nghĩa là transaction luôn được commit ngay tại thời điểm exception xảy ra. Chunk processing vẫn phải bảo vệ transaction boundary. Tùy phase và loại exception, Spring Batch có thể rollback transaction để cô lập item lỗi rồi tiếp tục xử lý chunk.

Ví dụ, writer nhận một chunk nhiều item và thất bại khi ghi một item. Framework có thể rollback chunk và thực hiện lại thao tác ghi theo cơ chế giúp xác định item gây lỗi. Nếu item đó được phép skip, các item còn lại có thể được ghi thành công trong chunk được xử lý lại.

Những điểm cần nhớ:

- Các chunk đã commit trước đó vẫn được giữ lại.
- Chunk hiện tại có thể rollback trước khi skip được hoàn tất.
- Writer có thể được gọi lại trong quá trình xử lý write skip.
- Side effect ngoài transaction không tự rollback.
- Reader tùy chỉnh cần có khả năng tiếp tục hoặc khôi phục vị trí sau rollback.

noRollback() là một cấu hình riêng để chỉ định exception không làm rollback transaction theo chính sách step. Nó không thay thế SkipPolicy và không tự động cho phép skip. Chỉ dùng noRollback khi đã hiểu tác động của exception lên dữ liệu transactional và muốn giữ transaction hiện tại tiếp tục.

## 12. SkipPolicy và SkipListener phối hợp như thế nào?

Hai thành phần có trách nhiệm bổ sung cho nhau:

| Thành phần | Câu hỏi được trả lời |
| --- | --- |
| SkipPolicy | Exception này có được phép bỏ qua không? |
| SkipListener | Item nào đã bị bỏ qua, ở phase nào và vì exception gì? |

Ví dụ listener:

```java
public class OrderSkipListener
        implements SkipListener<Order, OrderEntity> {

    private final RejectedOrderRepository repository;

    public OrderSkipListener(RejectedOrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public void onSkipInRead(Throwable t) {
        repository.save(RejectedOrder.fromReadException(t));
    }

    @Override
    public void onSkipInProcess(Order item, Throwable t) {
        repository.save(RejectedOrder.fromOrder(item, "PROCESS", t));
    }

    @Override
    public void onSkipInWrite(OrderEntity item, Throwable t) {
        repository.save(RejectedOrder.fromEntity(item, "WRITE", t));
    }
}
```

Đăng ký cả policy và listener:

```java
.faultTolerant()
.skipPolicy(importSkipPolicy)
.listener(orderSkipListener)
```

Policy quyết định item có thể được skip; listener ghi nhận kết quả skip. Nếu việc lưu quarantine bắt buộc để đối soát, hãy bảo đảm listener ghi vào resource có transaction phù hợp hoặc có idempotency khi ghi ra ngoài transaction.

## 13. SkipPolicy trong multi-threaded step và partitioning

Khi step chạy đa luồng hoặc partitioned, policy có thể được gọi đồng thời từ nhiều worker tùy kiến trúc. Một SkipPolicy được đăng ký dưới dạng singleton nên nên stateless hoặc thread-safe.

Tránh lưu skipCount vào field nội bộ của policy:

```java
// Không nên: state này có thể bị chia sẻ giữa các worker.
private long skipped;
```

Hãy dùng tham số skipCount được framework truyền vào mỗi lần gọi shouldSkip(). Nếu cần thống kê theo partition hoặc theo phase, dùng StepExecution counters, listener hoặc metrics với tag phù hợp.

Trong partitioning, mỗi worker step có execution và skip count riêng. Giới hạn skip thường được áp dụng theo từng step execution của worker, không tự động là một hạn mức toàn cục cho toàn bộ manager job. Nếu nghiệp vụ cần tổng giới hạn cho cả job, phải có cơ chế tổng hợp và điều phối riêng, đồng thời xử lý concurrency an toàn.

Với remote partitioning, policy cần được cấu hình nhất quán ở các worker. Không nên giả định manager policy tự được truyền sang worker qua message; worker step phải có cấu hình skip phù hợp trong ứng dụng worker.

## 14. Kiểm thử SkipPolicy độc lập

Custom policy có thể được unit test mà không cần khởi chạy Spring Batch. Kiểm tra cả exception được phép, exception bị từ chối và giới hạn:

```java
class ImportSkipPolicyTest {

    private final ImportSkipPolicy policy = new ImportSkipPolicy();

    @Test
    void allowsKnownDataExceptionsBelowLimit() throws Exception {
        assertThat(policy.shouldSkip(
            new InvalidOrderException("Invalid order"), 0
        )).isTrue();
    }

    @Test
    void rejectsUnexpectedException() throws Exception {
        assertThat(policy.shouldSkip(
            new IllegalStateException("Programming error"), 0
        )).isFalse();
    }

    @Test
    void throwsWhenLimitHasAlreadyBeenReached() {
        assertThatThrownBy(() -> policy.shouldSkip(
            new InvalidOrderException("Invalid order"), 10
        )).isInstanceOf(SkipLimitExceededException.class);
    }
}
```

Test này xác nhận logic của policy. Cần bổ sung integration test để kiểm tra policy được gắn đúng vào step và Spring Batch cập nhật skip count/trạng thái như mong đợi.

## 15. Kiểm thử skip trong một chunk step

Một integration test có thể dùng reader cung cấp ba order, processor ném exception cho một order và writer ghi các order còn lại. Cấu hình step dùng policy hoặc skip() tương ứng.

Các assertion hữu ích:

- Job/step hoàn tất nếu số skip nằm trong giới hạn và không có lỗi khác.
- readCount phản ánh số item reader cung cấp.
- processSkipCount tăng đúng số item processor lỗi được skip.
- writeCount phản ánh số output item ghi thành công.
- SkipListener.onSkipInProcess() nhận đúng item và exception.
- Repository quarantine có bản ghi lỗi nếu listener ghi nhận.

Nên kiểm tra cả trường hợp vượt giới hạn. Ví dụ skipLimit(2) nhưng có ba item gây lỗi được policy cho phép; step phải thất bại khi skip tiếp theo vượt limit. Xác nhận JobExecution/StepExecution có trạng thái FAILED và failure exception phù hợp.

Đối với read skip, dùng reader giả lập ném exception ở một vị trí có thể tiếp tục. Đối với write skip, dùng writer test có thể xác định output item lỗi. Không nên chỉ kiểm thử processor rồi giả định read và write skip có cùng hành vi.

## 16. Lỗi thường gặp khi cấu hình SkipPolicy

**Skip mọi Exception:** policy quá rộng có thể bỏ qua lỗi kết nối, lỗi xác thực hoặc bug. Chỉ cho phép exception dữ liệu đã phân loại.

**Không đặt skip limit:** khi dùng DSL, limit mặc định là 0; khai báo exception mà không đặt limit có thể không cho phép item nào bị bỏ qua.

**Hiểu limit là giới hạn theo từng phase:** skip limit tiêu chuẩn là tổng của read, process và write trong step.

**Dùng retry thay cho skip:** lỗi tạm thời nên retry nếu thao tác có thể thực hiện lại an toàn; skip là quyết định bỏ item.

**Dùng skip cho lỗi reader không thể tiếp tục:** mất kết nối hoặc mất cursor có thể làm reader không biết item kế tiếp. Fail thường an toàn hơn.

**Nhầm filter với skip:** processor trả về null không gọi policy và không tăng skip count.

**Custom policy không kiểm tra giới hạn:** khi tự triển khai, policy phải quyết định rõ thời điểm ném SkipLimitExceededException.

**Giữ state mutable trong singleton policy:** step đa luồng/partition có thể gọi policy đồng thời. Dùng skipCount được truyền vào thay vì bộ đếm nội bộ.

**Cho rằng listener quyết định skip:** SkipListener chỉ nhận thông báo; policy mới quyết định exception có thể bị bỏ qua.

**Không kiểm tra transaction khi lưu quarantine:** bản ghi lỗi có thể rollback cùng chunk hoặc bị ghi trùng khi retry. Chọn transaction và idempotency phù hợp.

## 17. Cách thiết kế SkipPolicy cho production

Trước tiên, lập danh sách exception có thể xuất hiện ở reader, processor và writer. Với mỗi loại, xác định đó là lỗi dữ liệu của một item, lỗi tạm thời có thể retry, hay lỗi hạ tầng/bug cần dừng. Ưu tiên exception class cụ thể và không dùng message text làm quy tắc chính.

Với quy tắc đơn giản, dùng skip(), noSkip() và skipLimit() để cấu hình ngay trên step. Khi quyết định cần nhiều điều kiện hoặc cần tái sử dụng logic phân loại, triển khai SkipPolicy riêng và để policy quản lý giới hạn rõ ràng. Trong môi trường partitioning, bảo đảm policy stateless/thread-safe và hiểu skip limit đang áp dụng theo từng worker execution.

Kết hợp policy với SkipListener để lưu dấu vết item bị bỏ qua, nhưng không đặt side effect khó rollback trong callback. Theo dõi read/process/write skip count, filter count và tỷ lệ lỗi; đặt ngưỡng để job dừng khi chất lượng dữ liệu vượt mức chấp nhận.

SkipPolicy giúp Spring Batch tiếp tục xử lý khi một số item lỗi có thể được loại bỏ an toàn. Một policy tốt phân loại exception rõ ràng, giới hạn số skip và phối hợp với retry, listener cùng transaction boundary để job không che giấu lỗi hệ thống hoặc âm thầm tạo ra kết quả thiếu dữ liệu.
