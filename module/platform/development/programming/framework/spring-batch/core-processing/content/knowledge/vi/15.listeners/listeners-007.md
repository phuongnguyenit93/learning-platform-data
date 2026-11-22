# SkipListener trong Spring Batch

Trong chunk-oriented processing, không phải mọi item đều có thể đọc, xử lý hoặc ghi thành công. Khi một exception được chính sách skip cho phép bỏ qua, Spring Batch có thể tiếp tục xử lý các item còn lại thay vì làm thất bại toàn bộ step. `SkipListener` là listener nhận thông báo khi một item bị bỏ qua, giúp ứng dụng ghi nhận dữ liệu lỗi, lưu thông tin phục vụ đối soát hoặc tạo bản ghi quarantine.

`SkipListener` tập trung vào **thông báo về item đã bị skip**. Nó không quyết định exception nào được skip; quyết định đó thuộc về fault-tolerant step và `SkipPolicy`. Hiểu rõ ba callback đọc, xử lý và ghi giúp ghi nhận đúng dữ liệu lỗi, đồng thời tránh nhầm skip với filtering hoặc retry.

## 1. Skip trong Spring Batch là gì?

Trong chunk processing, một item có thể gặp exception ở ba giai đoạn:

1. **Read:** reader không thể đọc hoặc parse một bản ghi.
2. **Process:** processor không thể xử lý item đầu vào.
3. **Write:** writer không thể ghi item đầu ra.

Nếu loại exception đó được cấu hình là skippable và giới hạn skip chưa bị vượt quá, Spring Batch bỏ qua item lỗi và tiếp tục theo chính sách của step.

Ví dụ, file CSV có 1.000 dòng, trong đó có một dòng sai định dạng. Nếu `FlatFileParseException` được phép skip, job có thể bỏ qua dòng lỗi, ghi nhận nó và tiếp tục với các dòng hợp lệ phía sau.

```text
Reader -> Processor -> Writer
   |          |          |
   v          v          v
 Read       Process     Write
 exception  exception   exception
   |          |          |
   +----------+----------+
              |
              v
      SkipPolicy cho phép?
              |
        +-----+-----+
        |           |
       Có          Không
        |           |
        v           v
 SkipListener     Step thất bại
 được gọi         hoặc retry theo cấu hình
        |
        v
 Tiếp tục xử lý item tiếp theo
```

Skip là một quyết định có chủ đích của ứng dụng. Không nên cho phép bỏ qua mọi exception chỉ để job luôn kết thúc thành công, vì lỗi hạ tầng hoặc lỗi lập trình có thể làm mất dữ liệu mà không được phát hiện.

## 2. SkipListener có vai trò gì?

`SkipListener` là callback được Spring Batch gọi khi một item bị skip. Ứng dụng thường dùng listener để:

- Ghi log loại lỗi và vị trí bản ghi.
- Lưu bản ghi lỗi vào bảng quarantine hoặc dead-letter storage.
- Ghi nhận mã nghiệp vụ để đối soát và xử lý lại sau này.
- Tăng metric theo loại lỗi và giai đoạn xảy ra lỗi.
- Tạo thông tin vận hành để người phụ trách biết vì sao item không được xử lý.

Listener chỉ được gọi sau khi framework xác định item sẽ bị skip theo policy. Nếu exception được retry và lần thử sau thành công, item không phải là item bị skip và callback skip tương ứng không được gọi cho lần lỗi tạm thời đó.

`SkipListener` không thay thế `ItemReadListener`, `ItemProcessListener` hoặc `ItemWriteListener`. Các listener này quan sát những sự kiện đọc, xử lý và ghi nói chung; `SkipListener` chỉ tập trung vào kết quả skip đã được chấp nhận.

## 3. Ba callback của SkipListener

Trong Spring Batch 5, interface có hai generic type: kiểu item đầu vào `I` và kiểu item đầu ra `O`.

```java
public interface SkipListener<I, O> extends StepListener {

    void onSkipInRead(Throwable t);

    void onSkipInProcess(I item, Throwable t);

    void onSkipInWrite(O item, Throwable t);
}
```

Mỗi callback tương ứng với một giai đoạn khác nhau:

| Callback | Khi nào được gọi? | Có nhận item không? |
| --- | --- | --- |
| `onSkipInRead(Throwable t)` | Một exception trong reader được policy cho phép skip. | Không; reader chưa tạo được item hợp lệ. |
| `onSkipInProcess(I item, Throwable t)` | Processor ném exception và item đầu vào được skip. | Có item đầu vào kiểu `I`. |
| `onSkipInWrite(O item, Throwable t)` | Writer không ghi được một item đầu ra và item đó được skip. | Có item đầu ra kiểu `O`. |

Sự khác nhau về kiểu item rất quan trọng. Nếu processor chuyển `Order` thành `OrderEntity`, `onSkipInProcess` nhận `Order`, còn `onSkipInWrite` nhận `OrderEntity`.

## 4. onSkipInRead: ghi nhận lỗi ở giai đoạn đọc

`onSkipInRead(Throwable t)` được gọi khi reader ném exception và exception đó được xác định là có thể skip. Callback không nhận item vì reader không trả về được một item hợp lệ.

Ví dụ với `FlatFileItemReader`, `FlatFileParseException` có thể cung cấp số dòng và nội dung đầu vào gây lỗi:

```java
public class OrderSkipListener
        implements SkipListener<Order, OrderEntity> {

    private static final Logger log =
        LoggerFactory.getLogger(OrderSkipListener.class);

    @Override
    public void onSkipInRead(Throwable t) {
        if (t instanceof FlatFileParseException parseException) {
            log.warn(
                "Skip invalid input at line {}: {}",
                parseException.getLineNumber(),
                parseException.getInput()
            );
            return;
        }

        log.warn("Skip input because reader failed", t);
    }

    @Override
    public void onSkipInProcess(Order item, Throwable t) {
        log.warn("Skip order {} during processing", item.getId(), t);
    }

    @Override
    public void onSkipInWrite(OrderEntity item, Throwable t) {
        log.warn("Skip order entity {} during writing", item.getOrderId(), t);
    }
}
```

Không phải mọi exception đọc đều có thể cung cấp nội dung bản ghi. Với lỗi mất kết nối database hoặc lỗi mở file, chỉ có exception và thông tin nguồn có thể được ghi nhận. Không nên giả định `onSkipInRead` luôn có raw item để lưu.

Đặc biệt, không nên chuyển lỗi kết nối hoặc lỗi cấu hình thành read skip nếu reader không thể tiếp tục an toàn. Skip read phù hợp nhất khi exception đại diện cho một bản ghi cụ thể có thể loại bỏ mà vẫn đọc tiếp được.

## 5. onSkipInProcess: ghi nhận item lỗi khi xử lý

`onSkipInProcess(I item, Throwable t)` được gọi khi processor ném exception và policy quyết định bỏ qua item đầu vào.

Ví dụ:

```java
@Override
public void onSkipInProcess(Order item, Throwable t) {
    log.warn(
        "Order {} cannot be processed: {}",
        item.getId(),
        t.getMessage()
    );
}
```

Callback này nhận được item đầu vào, vì vậy có thể trích xuất khóa nghiệp vụ để điều tra hoặc lưu thông tin lỗi. Tuy nhiên, chỉ nên ghi các trường cần thiết; tránh log toàn bộ object nếu chứa thông tin cá nhân, bí mật hoặc payload lớn.

Một ví dụ khác là ghi bản ghi lỗi vào một repository quarantine:

```java
@Override
public void onSkipInProcess(Order item, Throwable t) {
    rejectedOrderRepository.save(
        new RejectedOrder(item.getId(), "PROCESS", t.getMessage())
    );
}
```

Nếu repository này dùng cùng datasource và transaction manager với chunk step, thao tác lưu có thể tham gia transaction hiện tại. Nếu ghi sang datasource khác hoặc gọi API ngoài, cần cơ chế chống trùng và xử lý lỗi riêng. Listener không tự tạo transaction phân tán.

## 6. onSkipInWrite: ghi nhận item lỗi khi ghi

`onSkipInWrite(O item, Throwable t)` được gọi khi writer không ghi được item đầu ra và item đó được skip.

Ví dụ:

```java
@Override
public void onSkipInWrite(OrderEntity item, Throwable t) {
    log.error(
        "Cannot persist order {}: {}",
        item.getOrderId(),
        t.getMessage()
    );
}
```

Callback nhận kiểu đầu ra `O`, không phải kiểu đầu vào `I`. Nếu processor đã chuyển đổi hoặc làm giàu dữ liệu, listener có thể ghi nhận thông tin của object sau xử lý.

Skip trong write có một điểm đặc biệt: writer thường nhận cả chunk, không phải một item duy nhất. Nếu ghi chunk thất bại, framework có thể rollback và thực hiện lại quá trình ghi theo cách giúp xác định item gây lỗi. Vì vậy, writer có thể được gọi nhiều lần trong quá trình cô lập item lỗi. Không nên giả định một lần writer thất bại luôn chỉ tạo một callback skip ngay lập tức.

Khi writer có side effect ngoài transaction, việc gọi lại để xác định item lỗi có thể tạo tác động trùng. Writer cần có transaction phù hợp hoặc idempotency; không nên dựa vào `SkipListener` để sửa chữa các side effect đã xảy ra.

## 7. Cấu hình skip policy trong chunk step

Để `SkipListener` được gọi, step phải cho phép skip và exception phải thuộc loại được policy chấp nhận. Ví dụ:

```java
@Bean
Step importOrdersStep(JobRepository jobRepository,
                      PlatformTransactionManager transactionManager,
                      ItemReader<Order> reader,
                      ItemProcessor<Order, OrderEntity> processor,
                      ItemWriter<OrderEntity> writer,
                      OrderSkipListener skipListener) {
    return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, OrderEntity>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(FlatFileParseException.class)
        .skip(InvalidOrderException.class)
        .skipLimit(20)
        .listener(skipListener)
        .build();
}
```

Trong ví dụ, `FlatFileParseException` và `InvalidOrderException` được phép skip. Tổng số skip được chấp nhận của step bị giới hạn bởi `skipLimit(20)`. Khi vượt quá giới hạn, step thất bại thay vì tiếp tục bỏ qua item.

Skip limit được áp dụng chung cho lỗi đọc, xử lý và ghi trong step, không phải 20 lỗi cho mỗi phase. Ví dụ, nếu đã có 12 read skip và 8 process skip, giới hạn 20 đã được sử dụng hết; một skip tiếp theo có thể làm step thất bại.

Không cấu hình `.skip(Exception.class)` một cách tùy tiện. Nếu cần khai báo loại rộng, hãy dùng `.noSkip(...)` cho các exception phải làm step thất bại và kiểm tra thứ tự/quy tắc phân loại theo API phiên bản đang dùng.

## 8. Retry, skip và filter khác nhau như thế nào?

Ba cơ chế này có ý nghĩa khác nhau:

| Cơ chế | Điều gì xảy ra? | SkipListener có được gọi không? |
| --- | --- | --- |
| Retry | Framework thử lại thao tác bị lỗi theo retry policy. | Không, nếu lần thử lại thành công. |
| Skip | Framework chấp nhận bỏ qua item lỗi theo skip policy. | Có, callback tương ứng với phase xảy ra lỗi được gọi. |
| Filter | Processor trả về `null` để loại item theo quy tắc nghiệp vụ. | Không; đây không phải exception và không phải skip. |

Ví dụ, một order đã hủy có thể được filter bằng cách processor trả về `null`. Một order có dữ liệu không hợp lệ khiến processor ném `InvalidOrderException`; nếu exception được phép skip, `onSkipInProcess` được gọi. Một lỗi database tạm thời trong writer có thể được retry; nếu retry thành công, không có write skip.

Phân biệt đúng giúp thống kê chất lượng dữ liệu chính xác. `filterCount` phản ánh item bị lọc, còn skip count phản ánh exception đã được bỏ qua. Không nên gộp chúng thành một loại “bản ghi lỗi” nếu ý nghĩa nghiệp vụ khác nhau.

## 9. SkipPolicy tùy chỉnh

Với quy tắc phân loại phức tạp, có thể dùng `SkipPolicy` thay cho danh sách `.skip(...)` đơn giản. Policy nhận exception và số lượng skip hiện tại, sau đó quyết định có cho phép bỏ qua hay không.

```java
public class OrderSkipPolicy implements SkipPolicy {

    @Override
    public boolean shouldSkip(Throwable throwable, long skipCount)
            throws SkipLimitExceededException {

        if (throwable instanceof InvalidOrderException) {
            return skipCount < 20;
        }

        if (throwable instanceof FlatFileParseException) {
            return skipCount < 20;
        }

        return false;
    }
}
```

Đăng ký policy:

```java
.faultTolerant()
.skipPolicy(new OrderSkipPolicy())
.listener(skipListener)
```

Khi dùng custom policy, policy chịu trách nhiệm quyết định giới hạn và loại exception. Hãy ném `SkipLimitExceededException` hoặc trả về kết quả phù hợp theo hợp đồng API để framework xử lý khi giới hạn bị vượt. Không kết hợp một custom policy với `.skipLimit(...)` theo cách khiến logic giới hạn bị hiểu sai; chọn một nơi rõ ràng để quản lý giới hạn.

Skip policy không thay thế listener. Policy quyết định **có skip hay không**; listener thông báo **item nào đã bị skip và lỗi gì xảy ra**.

## 10. Đăng ký SkipListener với step

Có thể triển khai interface và đăng ký trực tiếp với step builder:

```java
@Bean
OrderSkipListener orderSkipListener(
        RejectedOrderRepository rejectedOrderRepository) {
    return new OrderSkipListener(rejectedOrderRepository);
}

@Bean
Step importOrdersStep(JobRepository jobRepository,
                      PlatformTransactionManager transactionManager,
                      ItemReader<Order> reader,
                      ItemProcessor<Order, OrderEntity> processor,
                      ItemWriter<OrderEntity> writer,
                      OrderSkipListener orderSkipListener) {
    return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, OrderEntity>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skip(FlatFileParseException.class)
        .skipLimit(20)
        .listener(orderSkipListener)
        .build();
}
```

Spring Batch nhận diện listener theo interface và gọi callback phù hợp. Dùng bean Spring giúp inject repository, logger hoặc metric service cần thiết. Nếu một listener được dùng ở nhiều step, cần đảm bảo state nội bộ của nó an toàn với phạm vi và concurrency của các step đó.

## 11. Dùng annotation cho skip callback

Ngoài cách triển khai interface, Spring Batch hỗ trợ các annotation listener:

- `@OnSkipInRead` cho exception khi đọc.
- `@OnSkipInProcess` cho item đầu vào và exception khi xử lý.
- `@OnSkipInWrite` cho item đầu ra và exception khi ghi.

Ví dụ:

```java
public class OrderSkipAnnotationListener {

    @OnSkipInRead
    public void onReadError(Throwable t) {
        // Ghi nhận lỗi reader; không có item hợp lệ.
    }

    @OnSkipInProcess
    public void onProcessError(Order item, Throwable t) {
        // Ghi nhận item đầu vào bị skip.
    }

    @OnSkipInWrite
    public void onWriteError(OrderEntity item, Throwable t) {
        // Ghi nhận item đầu ra bị skip.
    }
}
```

Đăng ký object listener với step bằng `.listener(annotationListener)`. Kiểu tham số method phải phù hợp với phase và generic type của step. Nếu method signature không tương thích, listener có thể không được gọi như mong đợi hoặc cấu hình có thể thất bại khi khởi tạo.

Với listener có nhiều dependency hoặc cần kiểm soát rõ generic type, triển khai `SkipListener<I,O>` thường dễ đọc và dễ kiểm thử hơn.

## 12. Thời điểm callback và transaction

Spring Batch thiết kế skip callback để được gọi ngay trước khi transaction của chunk commit. Điều này quan trọng khi listener ghi một bản ghi lỗi vào cùng database và transaction manager với step: bản ghi quarantine có thể được commit cùng chunk chứa quyết định skip.

Ví dụ:

```text
Chunk transaction
    |
    +-- Reader/Processor/Writer gặp item lỗi
    |
    +-- SkipPolicy cho phép bỏ qua
    |
    +-- SkipListener ghi rejected-item record
    |
    +-- Cập nhật metadata và bộ đếm
    |
    +-- COMMIT
```

Nếu transaction rollback, các thao tác transactional của listener trong cùng resource cũng có thể rollback. Khi chunk được thử lại, ứng dụng cần để framework thực hiện đúng vòng đời callback. Spring Batch cung cấp bảo đảm callback skip được thông báo theo semantics của skip processing, nhưng điều đó không phải bảo đảm exactly-once phân tán cho email, HTTP API hoặc message broker.

Nếu listener ghi sang hệ thống ngoài transaction, callback có thể tạo side effect mà database không thể hoàn tác. Hãy dùng idempotency key, outbox hoặc một cơ chế ghi nhận bền vững phù hợp. Tránh gửi email trực tiếp từ listener nếu việc gửi trùng là không chấp nhận được.

Listener cũng cần xử lý lỗi của chính nó. Nếu việc ghi quarantine thất bại, quyết định skip có thể không hoàn tất như mong muốn và chunk/job có thể thất bại. Không nên nuốt lỗi ghi nhận nếu dữ liệu lỗi bắt buộc phải được lưu để đối soát.

## 13. Lưu item bị skip vào bảng quarantine

Một use case phổ biến là lưu thông tin item lỗi vào bảng riêng để người vận hành có thể xem và xử lý lại.

Ví dụ entity:

```java
public record RejectedOrder(
    String orderId,
    String phase,
    String errorType,
    String errorMessage
) {}
```

Listener:

```java
public class OrderQuarantineSkipListener
        implements SkipListener<Order, OrderEntity> {

    private final RejectedOrderRepository repository;

    public OrderQuarantineSkipListener(RejectedOrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public void onSkipInRead(Throwable t) {
        if (t instanceof FlatFileParseException parseException) {
            repository.save(new RejectedOrder(
                "line-" + parseException.getLineNumber(),
                "READ",
                t.getClass().getSimpleName(),
                parseException.getMessage()
            ));
        }
    }

    @Override
    public void onSkipInProcess(Order item, Throwable t) {
        repository.save(new RejectedOrder(
            item.getId(),
            "PROCESS",
            t.getClass().getSimpleName(),
            t.getMessage()
        ));
    }

    @Override
    public void onSkipInWrite(OrderEntity item, Throwable t) {
        repository.save(new RejectedOrder(
            item.getOrderId(),
            "WRITE",
            t.getClass().getSimpleName(),
            t.getMessage()
        ));
    }
}
```

Đây là ví dụ minh họa; model thực tế có thể cần `jobExecutionId`, `stepExecutionId`, batch ID, file name, line number, event ID và thời điểm lỗi. Với lỗi đọc, `orderId` có thể chưa biết nên cần lưu định danh nguồn như file/line hoặc raw record nếu exception cung cấp.

Nếu bảng quarantine nằm cùng database và cùng transaction manager, thao tác save có thể commit cùng chunk. Nên có khóa duy nhất phù hợp để chống ghi trùng khi job được restart hoặc dữ liệu lỗi được xử lý lại trong một execution khác. Cần cân nhắc lưu stack trace đầy đủ hay chỉ mã lỗi/thông điệp đã làm sạch, tránh ghi dữ liệu nhạy cảm vào bảng lỗi.

## 14. SkipListener và writer lỗi theo chunk

Lỗi writer có thể phức tạp hơn lỗi đọc hoặc xử lý vì writer thường nhận nhiều item cùng lúc. Ví dụ chunk gồm `[A, B, C, D]`, writer thất bại khi ghi một item. Framework có thể rollback chunk và thử ghi từng item hoặc dùng cơ chế scan để xác định item gây lỗi.

```text
Writer nhận [A, B, C, D]
          |
          v
      write thất bại
          |
          v
      rollback chunk
          |
          v
Framework cô lập item lỗi theo cơ chế xử lý write skip
          |
          +-- A ghi được
          +-- B ghi được
          +-- C lỗi và được skip -> onSkipInWrite(C, exception)
          +-- D ghi được
```

Sơ đồ là mô tả khái niệm; số lần gọi writer và thứ tự thao tác thực tế phụ thuộc cấu hình step và cơ chế xử lý lỗi. Điều quan trọng là writer phải có thể được gọi lại. Nếu writer gọi API ngoài hoặc ghi một phần vào resource không rollback, việc xác định item lỗi có thể lặp side effect.

Với writer database tham gia cùng transaction, rollback giúp loại bỏ các thay đổi dở dang trước khi framework cô lập item lỗi. Với writer tùy chỉnh, hãy bảo đảm thao tác ghi có tính nguyên tử phù hợp hoặc có idempotency key.

## 15. SkipListener có thể dùng để ghi metric và audit

Ngoài quarantine, listener có thể cập nhật metric theo phase và loại exception:

```java
public class SkipMetricsListener implements SkipListener<Order, OrderEntity> {

    private final Counter readSkips;
    private final Counter processSkips;
    private final Counter writeSkips;

    public SkipMetricsListener(MeterRegistry registry) {
        this.readSkips = registry.counter("batch.skip", "phase", "read");
        this.processSkips = registry.counter("batch.skip", "phase", "process");
        this.writeSkips = registry.counter("batch.skip", "phase", "write");
    }

    @Override
    public void onSkipInRead(Throwable t) {
        readSkips.increment();
    }

    @Override
    public void onSkipInProcess(Order item, Throwable t) {
        processSkips.increment();
    }

    @Override
    public void onSkipInWrite(OrderEntity item, Throwable t) {
        writeSkips.increment();
    }
}
```

Metric giúp theo dõi xu hướng lỗi theo thời gian. Nếu số read skip tăng đột biến, có thể file đầu vào thay đổi định dạng; nếu write skip tăng, có thể constraint hoặc chất lượng dữ liệu đích đang có vấn đề.

Với metric in-memory hoặc hệ thống metrics ngoài transaction, một lần callback có thể làm bộ đếm tăng ngay cả khi chunk transaction sau đó rollback. Vì vậy, metric callback phù hợp cho quan sát vận hành, nhưng không nên dùng metric đơn thuần làm nguồn dữ liệu nghiệp vụ có tính chính xác kế toán. Nếu cần audit bền vững, lưu bản ghi trong transaction hoặc dùng outbox.

## 16. Kiểm thử SkipListener

Nên kiểm thử cả ba callback và hành vi tích hợp với skip policy. Unit test trực tiếp listener phù hợp để xác nhận cách nó trích xuất thông tin và ghi quarantine:

```java
@ExtendWith(MockitoExtension.class)
class OrderSkipListenerTest {

    @Mock
    RejectedOrderRepository repository;

    @Test
    void recordsProcessSkip() {
        OrderSkipListener listener = new OrderSkipListener(repository);
        Order order = new Order("ORDER-42");
        InvalidOrderException error =
            new InvalidOrderException("Missing customer id");

        listener.onSkipInProcess(order, error);

        verify(repository).save(argThat(rejected ->
            rejected.orderId().equals("ORDER-42")
                && rejected.phase().equals("PROCESS")
        ));
    }
}
```

Unit test không chứng minh Spring Batch sẽ gọi callback. Cần thêm integration test với fault-tolerant step.

Ví dụ, processor ném exception cho một item:

```java
ItemProcessor<Order, OrderEntity> processor = order -> {
    if ("ORDER-BAD".equals(order.getId())) {
        throw new InvalidOrderException("Invalid order");
    }
    return new OrderEntity(order.getId());
};
```

Step cấu hình `.skip(InvalidOrderException.class).skipLimit(5).listener(skipListener)`. Khi chạy job test với các item `[ORDER-1, ORDER-BAD, ORDER-2]`, có thể xác nhận:

- Job/step hoàn tất nếu không có lỗi khác và skip limit chưa bị vượt.
- `readCount` phản ánh số item reader đã cung cấp.
- `processSkipCount` tăng một.
- `writeCount` chỉ phản ánh các output được ghi.
- `onSkipInProcess` được gọi với `ORDER-BAD` và exception tương ứng.
- Bảng quarantine có bản ghi cho item bị skip nếu listener ghi vào database test.

Để kiểm tra read skip, dùng reader test ném exception có kiểm soát tại một lần đọc và cấu hình loại exception đó được skip. Với write skip, dùng writer test thất bại trên một output item cụ thể và xác nhận `onSkipInWrite` nhận đúng kiểu output. Không nên chỉ test một phase rồi giả định hai phase còn lại có cùng dữ liệu đầu vào.

## 17. Kiểm thử skip limit và retry

Test nên bao gồm tình huống số skip nằm dưới giới hạn và tình huống vượt giới hạn. Ví dụ với `skipLimit(2)`, hai exception được chấp nhận có thể được skip; exception tiếp theo làm step thất bại theo quy tắc skip limit.

Nếu cấu hình retry cùng với skip, hãy test cả hai nhánh:

- Exception tạm thời được retry rồi thành công: không ghi nhận skip.
- Exception tiếp tục xảy ra và thuộc skip policy: item bị skip, callback tương ứng được gọi.
- Exception không thuộc skip policy: step thất bại khi retry đã hết hoặc policy từ chối.

Khi test callback count, dùng item có định danh riêng và kiểm tra repository/recording listener. Đối với writer lỗi, nhớ rằng framework có thể gọi writer nhiều lần trong quá trình cô lập item; số lần `write()` không đồng nghĩa số lần `onSkipInWrite()`.

## 18. Các lỗi thường gặp khi dùng SkipListener

**Cho rằng listener quyết định skip:** listener chỉ nhận thông báo. Phải cấu hình `.faultTolerant()`, `.skip(...)`, `.skipLimit(...)` hoặc `SkipPolicy`.

**Nhầm phase và kiểu item:** `onSkipInProcess` nhận input `I`; `onSkipInWrite` nhận output `O`; `onSkipInRead` chỉ nhận exception.

**Dùng skip cho lỗi hạ tầng:** lỗi kết nối, credential hoặc nguồn không thể tiếp tục thường không phải item lỗi riêng lẻ. Retry hoặc fail có thể phù hợp hơn.

**Cấu hình skip quá rộng:** `.skip(Exception.class)` có thể che giấu lỗi lập trình và lỗi hệ thống. Chỉ cho phép các exception đã được đánh giá là an toàn.

**Nhầm filter với skip:** processor trả về `null` không gọi `SkipListener`. Đó là filtering, không phải exception.

**Giả định read skip có item:** reader không trả về item hợp lệ, vì vậy callback chỉ nhận exception. Trích xuất line/input từ exception nếu reader cung cấp.

**Ghi side effect không idempotent trong listener:** callback có thể tương tác với transaction/retry; email hoặc API ngoài database có thể bị lặp hoặc không rollback. Dùng outbox/khóa chống trùng.

**Nuốt lỗi khi lưu quarantine:** nếu việc lưu bản ghi lỗi là bắt buộc, không nên bỏ qua exception từ repository mà không có phương án dự phòng.

**Ghi quá nhiều dữ liệu nhạy cảm:** log hoặc quarantine chỉ nên chứa thông tin cần thiết và tuân theo chính sách bảo vệ dữ liệu.

## 19. Cách thiết kế SkipListener trong production

Trước tiên, xác định rõ exception nào được phép skip ở từng phase. Dùng `.skip(...)` và `.noSkip(...)` cho trường hợp đơn giản hoặc `SkipPolicy` khi cần quy tắc phức tạp. Đặt skip limit dựa trên mức lỗi nghiệp vụ có thể chấp nhận; khi vượt ngưỡng, để step thất bại và cảnh báo người vận hành.

Tiếp theo, triển khai listener theo đúng phase. Với read skip, ghi nhận thông tin nguồn như file, dòng hoặc cursor vì không có item hợp lệ. Với process skip, lưu định danh item đầu vào. Với write skip, lưu định danh và dữ liệu output cần thiết để điều tra. Tách log/metric khỏi dữ liệu quarantine bền vững nếu yêu cầu vận hành khác nhau.

Cuối cùng, kiểm thử từng callback với skip policy thật, xác nhận skip count và dữ liệu lỗi được lưu đúng. Bảo đảm thao tác lưu quarantine tham gia transaction phù hợp hoặc có idempotency nếu nằm ngoài transaction. Theo dõi skip rate theo phase và loại exception để phát hiện thay đổi chất lượng nguồn dữ liệu.

`SkipListener` giúp Spring Batch biến những lần bỏ qua item thành thông tin có thể quan sát và xử lý. Khi kết hợp listener đúng phase với skip policy rõ ràng, giới hạn hợp lý và cách ghi nhận an toàn, ứng dụng có thể tiếp tục xử lý dữ liệu hợp lệ mà vẫn giữ được dấu vết của những item không xử lý được.
