# Skip trong read, process và write

Trong Spring Batch, **skip** cho phép một Step bỏ qua item không thể xử lý theo chính sách đã cấu hình và tiếp tục với các item còn lại. Skip có thể xảy ra ở ba giai đoạn của chunk pipeline:

- **Read skip**: reader ném exception khi lấy hoặc parse dữ liệu nguồn.
- **Process skip**: processor ném exception khi chuyển đổi hoặc kiểm tra một item.
- **Write skip**: writer ném exception khi ghi một hoặc nhiều item của chunk.

Cả ba trường hợp đều làm tăng skip count của Step, nhưng thông tin có sẵn và cách framework xác định item lỗi khác nhau. Read skip có thể không tạo được object đầu vào; process skip có item đầu vào; write skip có item đầu ra mà writer không ghi được.

Skip là quyết định nghiệp vụ có kiểm soát. Nó không có nghĩa mọi exception đều được bỏ qua. Cần chọn đúng loại exception, giới hạn tổng số item bị skip, ghi nhận dữ liệu lỗi và bảo đảm việc bỏ qua không làm sai kết quả nghiệp vụ.

## 1. Skip nằm ở đâu trong chunk pipeline?

Một chunk-oriented Step thực hiện ba giai đoạn chính:

~~~text
Nguồn dữ liệu
     |
     v
  ItemReader
     |
     |  Read skip nếu reader ném lỗi
     v
 ItemProcessor
     |
     |  Process skip nếu processor ném lỗi
     v
  ItemWriter
     |
     |  Write skip nếu writer không ghi được item
     v
 Commit chunk
~~~

Ví dụ nhập 100 đơn hàng:

- Reader gặp một dòng CSV sai định dạng.
- Processor phát hiện hai đơn hàng thiếu mã bắt buộc.
- Writer không thể ghi một đơn hàng vi phạm constraint.

Nếu các exception đó được cấu hình skippable và skip limit chưa bị vượt, Step có thể bỏ qua các item tương ứng rồi tiếp tục xử lý.

Mỗi loại skip có callback riêng trong SkipListener:

| Giai đoạn | Callback | Dữ liệu callback nhận |
|---|---|---|
| Read | onSkipInRead | Exception, thường không có item đã tạo |
| Process | onSkipInProcess | Item đầu vào và exception |
| Write | onSkipInWrite | Item đầu ra và exception |

Đừng nhầm skip với filter. Processor trả về null là filter item theo logic nghiệp vụ; processor ném exception được phân loại skippable mới là process skip.

## 2. Cấu hình skip cơ bản cho Step

Spring Batch cấu hình skip thông qua fault-tolerant chunk Step:

~~~java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer,
        OrderSkipListener skipListener) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .skip(FlatFileParseException.class)
            .skip(InvalidOrderException.class)
            .skipLimit(50)
            .listener(skipListener)
            .build();
}
~~~

Trong ví dụ:

- Step xử lý tối đa 100 item mỗi chunk.
- Lỗi parse file và lỗi nghiệp vụ InvalidOrderException được phép skip.
- Tổng số item bị skip trong Step không được vượt quá 50.
- OrderSkipListener ghi nhận các item bị loại.

Nên khai báo exception cụ thể theo nguồn lỗi. Tránh skip Exception.class hoặc RuntimeException.class một cách rộng rãi vì có thể bỏ qua cả lỗi lập trình, lỗi cấu hình và lỗi hạ tầng nghiêm trọng.

Nếu không cấu hình skip, mặc định một exception không được xử lý sẽ làm Step thất bại theo rollback policy. Cấu hình skip phải thể hiện rõ loại lỗi nào nghiệp vụ chấp nhận loại bỏ.

## 3. Read skip: lỗi xảy ra trong ItemReader

Read skip xảy ra khi ItemReader ném exception trong lúc lấy item. Ví dụ:

- Một dòng CSV không đủ cột.
- Một trường số không chuyển được sang kiểu đích.
- Một bản ghi nguồn có định dạng không hợp lệ.
- Một lỗi đọc riêng lẻ được xác định là có thể bỏ qua.

Ví dụ FlatFileItemReader parse một dòng CSV:

~~~text
id,orderNumber,amount
1,ORD-001,100.00
2,ORD-002,not-a-number
3,ORD-003,250.00
~~~

Nếu reader chuyển amount sang kiểu số và dòng thứ hai gây FlatFileParseException, Step có thể skip dòng đó rồi tiếp tục đọc dòng thứ ba nếu exception được cấu hình skippable.

Cấu hình:

~~~java
.faultTolerant()
.skip(FlatFileParseException.class)
.skipLimit(20)
~~~

Read skip đặc biệt ở chỗ reader có thể không tạo được object đầu vào. Do đó SkipListener.onSkipInRead chỉ nhận exception, không nhận item.

### Không dùng null để biểu thị dòng lỗi

Trong Spring Batch, reader trả về null có nghĩa là **đã hết dữ liệu**. Nếu reader tự trả null khi gặp một dòng sai định dạng, Step có thể kết thúc đọc sớm và bỏ mất tất cả các dòng phía sau.

Hãy ném exception phù hợp khi một record không thể đọc và để skip policy quyết định có bỏ qua hay không. Chỉ trả null khi thực sự đạt EOF.

## 4. Lấy thông tin dòng lỗi trong read skip

Với FlatFileItemReader, FlatFileParseException thường chứa thông tin hữu ích:

- Line number: số thứ tự dòng.
- Input: nội dung dòng gây lỗi.
- Cause: exception gốc khi parse hoặc chuyển đổi.

Ví dụ listener:

~~~java
@Component
public class OrderSkipListener
        implements SkipListener<OrderInput, Order> {

    private final RejectedRecordRepository rejectedRepository;

    public OrderSkipListener(
            RejectedRecordRepository rejectedRepository) {
        this.rejectedRepository = rejectedRepository;
    }

    @Override
    public void onSkipInRead(Throwable exception) {
        if (exception instanceof FlatFileParseException parseException) {
            rejectedRepository.save(
                    RejectedRecord.from(
                            parseException.getLineNumber(),
                            parseException.getInput(),
                            parseException.getMessage()));
        }
    }

    @Override
    public void onSkipInProcess(
            OrderInput item,
            Throwable exception) {
        // Xử lý ở phần process skip.
    }

    @Override
    public void onSkipInWrite(
            Order item,
            Throwable exception) {
        // Xử lý ở phần write skip.
    }
}
~~~

Đoạn code minh họa việc lưu số dòng và nội dung gốc. Trong ứng dụng thực tế, cần cân nhắc bảo mật dữ liệu nhạy cảm trong input, giới hạn độ dài nội dung lưu và tránh lưu nguyên payload nếu không cần thiết.

Nếu reader tùy chỉnh ném exception riêng, hãy đính kèm source location hoặc record key để có thể truy vết item bị lỗi. Không nên chỉ lưu message chung chung như "read failed".

## 5. Process skip: lỗi xảy ra trong ItemProcessor

Process skip xảy ra khi processor nhận được item đầu vào nhưng ném exception trong lúc kiểm tra hoặc chuyển đổi.

Ví dụ processor kiểm tra đơn hàng:

~~~java
public class OrderProcessor
        implements ItemProcessor<OrderInput, Order> {

    @Override
    public Order process(OrderInput input) {
        if (input.orderNumber() == null
                || input.orderNumber().isBlank()) {
            throw new InvalidOrderException(
                    "Order number is required");
        }

        if (input.amount() == null || input.amount().signum() <= 0) {
            throw new InvalidOrderException(
                    "Amount must be positive");
        }

        return new Order(
                input.id(),
                input.orderNumber(),
                input.amount());
    }
}
~~~

Nếu InvalidOrderException được cấu hình skippable, item đó không được chuyển sang writer. Các item hợp lệ khác vẫn có thể được ghi.

Callback tương ứng:

~~~java
@Override
public void onSkipInProcess(
        OrderInput item,
        Throwable exception) {

    rejectedOrderRepository.save(
            RejectedOrder.from(
                    item.id(),
                    item.orderNumber(),
                    exception.getMessage()));
}
~~~

Process skip thường dễ ghi nhận hơn read skip vì đã có object đầu vào. Có thể lưu business key, dữ liệu quan trọng và lý do từ chối để sửa hoặc xử lý lại sau.

### Phân biệt process skip với filter

Processor có hai cách kết thúc không tạo output:

~~~java
@Override
public Order process(OrderInput input) {
    if (input.isCancelled()) {
        return null; // Filter: loại theo quy tắc nghiệp vụ.
    }

    if (input.orderNumber() == null) {
        throw new InvalidOrderException("Missing order number");
    }

    return convert(input);
}
~~~

Hai trường hợp có ý nghĩa khác nhau:

| Hành vi | Ý nghĩa | Counter |
|---|---|---|
| Trả về null | Filter item có chủ đích | filterCount tăng |
| Ném exception skippable | Bỏ qua item lỗi | processSkipCount tăng |
| Ném exception không skippable | Step không thể tiếp tục theo policy | Step thất bại |

Không nên ném exception chỉ để filter item. Ngược lại, không nên trả null để che giấu dữ liệu không hợp lệ nếu cần thống kê và lưu lý do từ chối.

## 6. Write skip: lỗi xảy ra trong ItemWriter

Write skip xảy ra khi writer không ghi được một hoặc nhiều item. Đây là trường hợp phức tạp nhất vì writer thường nhận cả chunk thay vì từng item riêng lẻ.

Ví dụ writer ghi đơn hàng vào database và một item vi phạm unique constraint:

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

Nếu một item làm batch ghi thất bại và exception thuộc nhóm skippable, Spring Batch có thể rollback lần ghi chunk và thực hiện quy trình xác định item gây lỗi. Tùy cấu hình và loại writer, framework có thể gọi writer lại với các tập con hoặc từng item để cô lập lỗi.

Ví dụ minh họa:

~~~text
Writer nhận [A, B, C, D]
          |
          v
Ghi cả chunk thất bại
          |
          v
Framework xác định item lỗi
          |
          +--> A ghi được
          +--> B lỗi -> skip
          +--> C ghi được
          +--> D ghi được
~~~

Đây là mô hình khái niệm. Không phải mọi writer hoặc mọi lỗi batch đều có thể được phân tách an toàn thành item riêng. Nếu writer chỉ nhận một lỗi chung từ hệ thống ngoài mà không xác định item gây lỗi, skip ở cấp item có thể không phù hợp.

### Writer có thể được gọi nhiều lần

Trong quá trình write skip, writer có thể được gọi lại với các tập item khác nhau. Vì vậy:

- Không giả định write() chỉ chạy một lần cho mỗi chunk.
- Writer nên tham gia transaction hoặc có tính idempotent.
- Tránh gửi email, tạo vận đơn hoặc gọi API không có idempotency trực tiếp trong writer.
- Nếu không thể xác định item lỗi, hãy fail hoặc dùng quy trình đối soát riêng.

## 7. SkipListener cho cả ba giai đoạn

SkipListener cung cấp ba callback:

~~~java
public interface SkipListener<I, O> {

    void onSkipInRead(Throwable t);

    void onSkipInProcess(I item, Throwable t);

    void onSkipInWrite(O item, Throwable t);
}
~~~

Ví dụ listener đầy đủ:

~~~java
@Component
public class OrderSkipListener
        implements SkipListener<OrderInput, Order> {

    private final RejectedOrderRepository repository;

    public OrderSkipListener(RejectedOrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public void onSkipInRead(Throwable exception) {
        repository.save(
                RejectedOrder.readFailure(
                        exception.getMessage()));
    }

    @Override
    public void onSkipInProcess(
            OrderInput item,
            Throwable exception) {
        repository.save(
                RejectedOrder.processFailure(
                        item.id(),
                        exception.getMessage()));
    }

    @Override
    public void onSkipInWrite(
            Order item,
            Throwable exception) {
        repository.save(
                RejectedOrder.writeFailure(
                        item.id(),
                        exception.getMessage()));
    }
}
~~~

Listener có thể ghi nhận:

- Giai đoạn xảy ra lỗi: READ, PROCESS hoặc WRITE.
- Business key của item nếu có.
- Exception type và message.
- Source file, line number hoặc partition.
- Thời điểm và JobExecution/StepExecution liên quan.

Không nên lưu toàn bộ stack trace hoặc payload lớn vào bảng rejected nếu không cần. Có thể lưu exception class, message đã chuẩn hóa và mã tham chiếu tới log chi tiết.

### Thời điểm gọi SkipListener

Spring Batch gọi SkipListener ở giai đoạn gần trước khi transaction commit để listener có thể sử dụng tài nguyên transactional. Điều này hữu ích khi listener ghi rejected record vào cùng database và muốn bản ghi lỗi được commit cùng chunk.

Nếu chunk rollback trước khi commit, việc ghi rejected record tham gia transaction đó cũng có thể rollback. Không nên gửi side effect tới hệ thống ngoài từ SkipListener rồi cho rằng database rollback sẽ thu hồi được side effect.

## 8. skipLimit áp dụng cho tổng số skip

skipLimit là giới hạn tổng số item được phép skip trong Step, cộng từ read, process và write. Nó không phải ba giới hạn độc lập.

Ví dụ:

~~~java
.faultTolerant()
.skip(FlatFileParseException.class)
.skip(InvalidOrderException.class)
.skip(DuplicateOrderException.class)
.skipLimit(10)
~~~

Giả sử Step có:

| Giai đoạn | Số item skip |
|---|---:|
| Read | 2 |
| Process | 5 |
| Write | 3 |
| Tổng | 10 |

Với skipLimit bằng 10, Step có thể chấp nhận tổng cộng 10 item bị skip. Item skip tiếp theo làm vượt giới hạn và khiến Step thất bại.

Điều này có nghĩa cần theo dõi tổng skip chứ không chỉ nhìn một loại lỗi. Một file có 4 lỗi parse, 4 lỗi validation và 3 lỗi ghi sẽ vượt giới hạn 10 dù từng nhóm riêng lẻ không vượt 10.

Nếu cần giới hạn khác nhau cho từng loại lỗi, có thể xây dựng SkipPolicy tùy chỉnh. Tuy nhiên, vẫn cần có giới hạn tổng hoặc chính sách dừng rõ ràng để bảo vệ Job khỏi dữ liệu lỗi hàng loạt.

## 9. Chọn exception nào được skip?

Chính sách skip nên phân biệt lỗi dữ liệu theo item với lỗi hệ thống.

| Loại lỗi | Hướng xử lý thường gặp |
|---|---|
| CSV thiếu cột hoặc sai kiểu | Read skip nếu dòng riêng lẻ có thể loại |
| Thiếu business key | Process skip hoặc fail theo nghiệp vụ |
| Giá trị nghiệp vụ ngoài miền cho phép | Process skip nếu có quy trình rejected |
| Duplicate key do bản ghi đầu vào | Write skip nếu nghiệp vụ cho phép |
| Database mất kết nối | Retry có giới hạn hoặc fail |
| Database hết dung lượng | Fail và xử lý hạ tầng |
| SQL sai hoặc schema sai | Fail |
| Lỗi lập trình trong processor | Fail, không skip rộng |

Ví dụ chỉ cho phép skip một số exception:

~~~java
.faultTolerant()
.skip(FlatFileParseException.class)
.skip(InvalidOrderException.class)
.skip(DuplicateOrderException.class)
.noSkip(FatalImportException.class)
.skipLimit(50)
~~~

Hãy chọn loại exception thực tế mà reader, processor hoặc writer ném ra. Nếu exception được bọc trong một exception khác, cần kiểm tra cause và skip classifier theo đúng kiểu exception mà framework nhìn thấy.

Tránh cấu hình skip Exception.class. Nếu làm vậy, một NullPointerException hoặc lỗi cấu hình cũng có thể bị coi là dữ liệu xấu và Job vẫn tiếp tục.

## 10. Dùng SkipPolicy tùy chỉnh

Khi quy tắc skip phụ thuộc vào nhiều điều kiện, có thể dùng SkipPolicy thay vì khai báo một danh sách class đơn giản.

Ví dụ một policy giới hạn tổng số lỗi và chỉ cho phép lỗi dữ liệu cụ thể:

~~~java
public class OrderSkipPolicy implements SkipPolicy {

    private static final int LIMIT = 50;

    @Override
    public boolean shouldSkip(
            Throwable exception,
            long skipCount) throws SkipLimitExceededException {

        if (skipCount >= LIMIT) {
            throw new SkipLimitExceededException(
                    LIMIT, exception);
        }

        Throwable cause = exception;

        while (cause.getCause() != null && cause.getCause() != cause) {
            cause = cause.getCause();
        }

        return cause instanceof InvalidOrderException
                || cause instanceof FlatFileParseException;
    }
}
~~~

Đăng ký policy:

~~~java
new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skipPolicy(new OrderSkipPolicy())
        .listener(skipListener)
        .build();
~~~

Ví dụ này minh họa việc phân loại theo nguyên nhân gốc. Trong ứng dụng thực tế, cần quyết định rõ cách unwrap exception; không phải lúc nào deepest cause cũng là loại cần phân loại. Có trường hợp wrapper exception cung cấp ngữ nghĩa quan trọng hơn cause bên trong.

Không cấu hình đồng thời nhiều skip policy theo cách không rõ ưu tiên. Khi dùng custom SkipPolicy, hãy để policy đó là nguồn quyết định chính và kiểm thử các exception đại diện.

## 11. Retry kết hợp với skip

Một lỗi có thể vừa retryable vừa skippable. Ví dụ writer gặp lỗi kết nối tạm thời; ứng dụng thử lại vài lần, nếu vẫn thất bại và nghiệp vụ cho phép loại item thì mới skip.

~~~java
new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .skip(InvalidOrderException.class)
        .skipLimit(50)
        .build();
~~~

Retry và skip có mục tiêu khác nhau:

- Retry cố hoàn thành cùng thao tác.
- Skip chấp nhận bỏ item.
- Khi retry hết giới hạn, chỉ có thể skip nếu exception được chính sách skip cho phép.
- Nếu exception không skippable, Step thất bại.

Không nên cấu hình một lỗi hạ tầng diện rộng vừa retry vừa skip chỉ để Job luôn hoàn tất. Database down không phải một item lỗi có thể bỏ qua; Step cần dừng để tránh mất dữ liệu.

## 12. Rollback và skip ở từng giai đoạn

Khi một exception skippable xảy ra, framework có thể rollback transaction hiện tại rồi tiếp tục theo quy trình fault-tolerant. Chi tiết phụ thuộc giai đoạn và loại reader/writer.

### Read skip

Reader ném exception khi parse một dòng. Framework phân loại lỗi, rollback nếu cần, ghi nhận skip và tiếp tục đọc. Với file reader, trạng thái dòng và khả năng restart phải được quản lý đúng để không lặp hoặc bỏ sót dòng.

### Process skip

Processor ném exception cho một item. Item đó không được chuyển tới writer. Các item khác của chunk có thể tiếp tục được xử lý sau khi framework hoàn tất quy trình skip.

### Write skip

Writer ném exception cho chunk. Framework có thể rollback lần ghi, sau đó xác định item gây lỗi bằng cách thử lại writer với tập con. Item lỗi được skip, các item ghi được có thể được ghi lại trong transaction phù hợp.

Điều cần nhớ là rollback của chunk không có nghĩa toàn bộ Job quay về từ đầu. Các chunk đã commit trước đó vẫn tồn tại. Nếu Step thất bại vì vượt skip limit, Job có thể restart từ checkpoint gần nhất đã lưu.

## 13. Side effect và tính idempotent khi skip

Writer có thể được gọi nhiều lần trong quá trình retry hoặc cô lập item lỗi cho write skip. Nếu writer gửi request tới API ngoài, một request đã thành công có thể bị gửi lại khi chunk rollback hoặc framework thử lại.

Ví dụ không an toàn:

~~~java
@Override
public void write(Chunk<? extends Order> chunk) {
    for (Order order : chunk) {
        shippingClient.createShipment(order);
    }
}
~~~

Nếu API tạo vận đơn thành công cho item đầu tiên nhưng item tiếp theo thất bại, lần thử lại có thể tạo vận đơn thứ hai cho cùng order.

Các cách bảo vệ:

- Dùng idempotency key ổn định theo order ID.
- Ghi yêu cầu tạo vận đơn vào outbox cùng transaction database.
- Worker riêng đọc outbox và gửi request.
- Lưu external request ID để đối soát.
- Tránh side effect không thể lặp an toàn trong writer.

Skip không bảo đảm side effect của item đã được hoàn tác. Nếu item bị skip sau khi một hệ thống ngoài đã nhận request, cần cơ chế bù trừ hoặc đối soát riêng.

## 14. Kiểm tra kết quả bằng StepExecution counters

Spring Batch cung cấp counter theo từng giai đoạn:

| Counter | Ý nghĩa |
|---|---|
| readSkipCount | Số item bị skip khi đọc |
| processSkipCount | Số item bị skip khi xử lý |
| writeSkipCount | Số item bị skip khi ghi |
| filterCount | Số item processor chủ động lọc bằng cách trả null |
| readCount | Số item đọc thành công theo thống kê Step |
| writeCount | Số item được ghi theo thống kê Step |
| rollbackCount | Số lần rollback được ghi nhận |

Có thể đọc counter sau khi Step kết thúc:

~~~java
@Override
public ExitStatus afterStep(StepExecution stepExecution) {
    long readSkips = stepExecution.getReadSkipCount();
    long processSkips = stepExecution.getProcessSkipCount();
    long writeSkips = stepExecution.getWriteSkipCount();

    long totalSkips = readSkips + processSkips + writeSkips;

    log.info(
            "Skip summary: read={}, process={}, write={}, total={}",
            readSkips,
            processSkips,
            writeSkips,
            totalSkips);

    return stepExecution.getExitStatus();
}
~~~

Counter giúp phân biệt lỗi tập trung ở nguồn đọc, quy tắc xử lý hay hệ thống ghi. Ví dụ readSkipCount tăng mạnh có thể cho thấy file nguồn sai schema; writeSkipCount tăng có thể chỉ ra constraint hoặc vấn đề ở database đích.

Không nên chỉ dựa vào tổng skip count. Hãy ghi nhận exception type và business key để tìm nguyên nhân cụ thể.

## 15. Kiểm thử read skip

Một test read skip nên tạo nguồn có một dòng lỗi giữa các dòng hợp lệ, sau đó xác nhận reader tiếp tục đọc phần sau.

Ví dụ dữ liệu:

~~~csv
id,orderNumber,amount
1,ORD-001,100.00
2,ORD-002,not-a-number
3,ORD-003,250.00
~~~

Các assertion cần có:

- Item 1 được đọc và ghi.
- Dòng 2 bị skip do parse exception.
- Item 3 vẫn được đọc và ghi.
- readSkipCount bằng 1.
- SkipListener nhận được FlatFileParseException và line number tương ứng.
- Step hoàn tất nếu skip limit chưa bị vượt.

Cũng cần test file không tồn tại. File thiếu thường là lỗi resource cấp Step/Job, không nên tự động xem như một dòng dữ liệu có thể skip.

## 16. Kiểm thử process skip

Tạo processor ném InvalidOrderException cho một business key xác định.

Ví dụ input:

~~~text
ORD-001 -> hợp lệ
ORD-002 -> thiếu order number
ORD-003 -> hợp lệ
~~~

Xác nhận:

- Processor được gọi cho từng item theo luồng xử lý.
- Item lỗi không được gửi tới writer.
- Hai item hợp lệ được ghi.
- processSkipCount bằng 1.
- filterCount không tăng vì item bị loại bằng exception, không phải trả null.
- SkipListener.onSkipInProcess nhận đúng item và exception.

Nếu processor có gọi dịch vụ ngoài, test cần xác nhận retry hoặc skip không tạo side effect trùng.

## 17. Kiểm thử write skip

Write skip cần test với writer có thể xác định item gây lỗi và database transaction thực tế.

Ví dụ:

- Writer nhận A, B, C.
- B vi phạm unique constraint.
- Framework rollback lần ghi chunk.
- Framework xác định B là item lỗi theo cơ chế fault-tolerant.
- A và C được ghi nếu policy cho phép.
- writeSkipCount bằng 1.
- SkipListener.onSkipInWrite nhận B.

Không chỉ mock writer rồi gọi listener trực tiếp; cách đó không xác nhận được hành vi fault-tolerant của Step. Nên dùng Step integration test với database test riêng, writer thực tế hoặc writer test double có hành vi transaction tương đương.

Nếu writer ghi API ngoài hoặc file thông thường, test phải kiểm tra side effect đã xảy ra trước rollback và bảo đảm idempotency hoặc cleanup.

## 18. Kiểm thử skip limit

Với skipLimit bằng 2, hãy kiểm thử ít nhất ba trường hợp:

| Số item bị skip | Kết quả mong đợi |
|---:|---|
| 0 | Step có thể hoàn tất |
| 2 | Step có thể hoàn tất nếu các điều kiện khác thành công |
| 3 | Step thất bại vì vượt giới hạn |

Kiểm thử thêm khi skip được phân bố giữa các giai đoạn. Ví dụ 1 read skip và 1 process skip đã dùng hết limit 2; write skip tiếp theo phải làm Step thất bại.

Khi vượt giới hạn, transaction của chunk hiện tại có thể rollback theo chính sách xử lý lỗi. Những chunk đã commit trước đó vẫn được giữ lại.

## 19. Những lỗi thường gặp

### Trả null khi reader gặp dòng lỗi

null biểu thị EOF. Trả null sớm có thể làm mất toàn bộ dữ liệu phía sau. Hãy ném exception skippable cho record lỗi.

### Coi filter là skip

Processor trả null làm tăng filterCount, không phải processSkipCount. Dùng exception khi cần ghi nhận một item lỗi.

### Dùng skip Exception.class

Có thể che giấu bug và lỗi hạ tầng. Chỉ skip các exception cụ thể được nghiệp vụ cho phép.

### Nghĩ skipLimit áp dụng riêng cho mỗi giai đoạn

skipLimit là giới hạn tổng read/process/write skip của Step. Theo dõi từng counter và tổng số.

### Giả định write skip chỉ gọi writer một lần

Framework có thể gọi writer lại để cô lập item lỗi. Writer phải transactional hoặc idempotent.

### Không ghi nhận item bị skip

Không thể điều tra, sửa hoặc chạy lại dữ liệu lỗi. Dùng SkipListener và lưu business key cùng nguyên nhân.

### Skip lỗi database diện rộng

Database down hoặc hết dung lượng không phải lỗi riêng lẻ của một item. Hãy retry có giới hạn hoặc fail Step.

### Gửi side effect trong SkipListener

Ghi database có thể tham gia transaction, nhưng email/API không tự rollback. Dùng outbox hoặc idempotency cho tác động ngoài.

## 20. Quy trình thiết kế skip cho một Step

Khi triển khai skip, hãy xác định:

1. Exception có thể xảy ra ở read, process và write.
2. Loại exception nào thực sự được phép skip theo nghiệp vụ.
3. Reader có ném exception đúng cách hay trả null nhầm khi gặp dữ liệu lỗi.
4. Process skip có lưu được input item và business key không.
5. Write skip có thể xác định chính xác item lỗi không.
6. Writer có an toàn khi được gọi lại không.
7. skipLimit tổng có phù hợp với quy mô và mức sai lệch cho phép không.
8. SkipListener có lưu giai đoạn, nguyên nhân và source location không.
9. Các thao tác ghi rejected record có tham gia transaction mong muốn không.
10. Side effect ngoài transaction có idempotency hoặc outbox không.
11. Metrics readSkipCount, processSkipCount và writeSkipCount có được theo dõi không.
12. Integration test bao phủ từng giai đoạn và trường hợp vượt skip limit chưa.

Read skip xử lý lỗi khi lấy dữ liệu, process skip xử lý lỗi khi biến đổi item, còn write skip xử lý item không thể ghi ra đích. Cả ba cùng tiêu thụ một skip limit của Step nhưng cung cấp thông tin khác nhau cho việc khôi phục và điều tra. Khi chọn exception hẹp, lưu bản ghi lỗi đầy đủ, giới hạn tổng skip và bảo vệ writer khỏi side effect trùng, Step có thể tiếp tục với dữ liệu hợp lệ mà vẫn giữ được khả năng kiểm soát chất lượng đầu vào.
