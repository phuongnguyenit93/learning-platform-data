# SkipListener ghi nhận item bị bỏ qua

Trong Spring Batch, một Step có thể được cấu hình để bỏ qua một số item gặp lỗi thay vì dừng toàn bộ Job. Khi lỗi được phân loại là có thể skip và giới hạn skip chưa bị vượt, framework bỏ item đó khỏi luồng xử lý và tiếp tục với các item còn lại. `SkipListener` cung cấp các callback để ứng dụng ghi nhận item bị bỏ qua, nguyên nhân và giai đoạn xảy ra lỗi.

Listener này đặc biệt hữu ích trong các Job import dữ liệu, đối soát hoặc đồng bộ, nơi một số bản ghi không hợp lệ có thể được xử lý riêng sau khi batch chính hoàn tất. Thông tin skip có thể được lưu vào bảng lỗi, dead-letter store, audit log hoặc hệ thống theo dõi để người vận hành biết dữ liệu nào cần sửa và xử lý lại.

## 1. Skip trong Spring Batch có nghĩa là gì?

Trong chunk-oriented processing, Spring Batch đọc item, đưa item qua processor nếu có, rồi ghi các item đầu ra bằng writer. Nếu một exception xảy ra trong reader, processor hoặc writer, Step có thể:

- Thất bại ngay nếu exception không được cấu hình để retry hoặc skip.
- Thử lại thao tác nếu exception thuộc nhóm retryable.
- Bỏ qua item nếu exception được phân loại là skippable và skip limit cho phép.

Skip là quyết định có chủ đích của cấu hình Step. Nó không có nghĩa framework bỏ qua mọi exception. Ví dụ, ứng dụng có thể cho phép skip một dòng CSV sai định dạng, nhưng vẫn phải dừng Job khi database mất kết nối hoặc khi lỗi bảo mật xảy ra.

Ví dụ một file có 5 bản ghi:

```text
Input: A, B, C, D, E

A -> đọc, xử lý, ghi thành công
B -> lỗi validation -> SKIP
C -> đọc, xử lý, ghi thành công
D -> lỗi parse -> SKIP
E -> đọc, xử lý, ghi thành công

Kết quả:
  3 item được ghi
  2 item được ghi nhận là skipped
```

`SkipListener` được gọi khi Spring Batch đã xác định item thực sự bị bỏ qua theo chính sách skip. Nó giúp ghi nhận quyết định cuối cùng đó.

## 2. SkipListener cung cấp ba callback

Interface `SkipListener<I, O>` có ba phương thức tương ứng với ba giai đoạn của pipeline:

```java
public interface SkipListener<T, S> extends StepListener {

    void onSkipInRead(Throwable t);

    void onSkipInProcess(T item, Throwable t);

    void onSkipInWrite(S item, Throwable t);
}
```

Trong đó:

- `T` là kiểu item đầu vào được reader cung cấp cho processor.
- `S` là kiểu item đầu ra mà writer nhận.
- `Throwable` là nguyên nhân khiến item bị skip.

| Callback | Giai đoạn | Có item không? | Ý nghĩa |
|---|---|---|---|
| `onSkipInRead(Throwable)` | Reader | Không có item được tạo thành công | Reader gặp lỗi và item không thể được đọc |
| `onSkipInProcess(T, Throwable)` | Processor | Có item đầu vào | Item đã đọc nhưng xử lý bị lỗi và được bỏ qua |
| `onSkipInWrite(S, Throwable)` | Writer | Có item đầu ra | Item đã qua xử lý nhưng không ghi được và được bỏ qua |

Điểm khác biệt quan trọng là `onSkipInRead()` không nhận item. Khi reader ném exception, framework có thể chưa tạo được object đầu vào. Listener chỉ nhận exception để xác định nguyên nhân; tùy loại exception, có thể trích xuất thêm thông tin như số dòng hoặc nội dung đầu vào.

## 3. `onSkipInRead()` — ghi nhận lỗi khi đọc

`onSkipInRead()` được gọi khi reader ném exception và exception đó được chấp nhận để skip. Trường hợp phổ biến là đọc file có một dòng không đúng định dạng, thiếu cột hoặc không thể chuyển đổi kiểu dữ liệu.

Ví dụ với `FlatFileItemReader`, lỗi parse có thể là `FlatFileParseException`, cung cấp số dòng và input gây lỗi:

```java
@Override
public void onSkipInRead(Throwable t) {
    if (t instanceof FlatFileParseException ex) {
        log.warn("Skipped input at line {}: {}",
                ex.getLineNumber(),
                ex.getMessage());
    } else {
        log.warn("Skipped item during read: {}", t.toString());
    }
}
```

Vì không có object item, listener thường ghi nhận:

- Tên nguồn hoặc file đang đọc.
- Số dòng, offset hoặc vị trí đọc nếu exception cung cấp.
- Loại exception và thông báo lỗi đã được làm sạch.
- JobExecution ID, StepExecution ID hoặc batch ID nếu ứng dụng gắn được ngữ cảnh đó.

Không nên giả định mọi exception đọc đều có raw input hoặc line number. Với JDBC reader, lỗi có thể là lỗi kết nối hoặc truy vấn; với API reader, lỗi có thể là HTTP status hoặc timeout. Cần ghi nhận metadata phù hợp với từng nguồn.

## 4. `onSkipInProcess()` — ghi nhận item lỗi khi xử lý

`onSkipInProcess()` được gọi khi processor nhận item nhưng ném exception thuộc nhóm có thể skip. Listener nhận được item đầu vào và exception, vì vậy có thể lưu business key để tìm lại bản ghi.

Ví dụ processor kiểm tra đơn hàng:

```java
public class InvalidOrderException extends RuntimeException {
    public InvalidOrderException(String message) {
        super(message);
    }
}

@Component
public class OrderProcessor
        implements ItemProcessor<OrderInput, Order> {

    @Override
    public Order process(OrderInput input) {
        if (input.amount() == null || input.amount().signum() <= 0) {
            throw new InvalidOrderException(
                    "Order amount must be positive: " + input.orderId());
        }

        return new Order(input.orderId(), input.amount());
    }
}
```

Listener có thể ghi nhận order ID và lý do:

```java
@Override
public void onSkipInProcess(OrderInput item, Throwable t) {
    skippedOrderService.record(
            "PROCESS",
            item.orderId(),
            t.getClass().getSimpleName(),
            t.getMessage());
}
```

Item đầu vào được truyền vào callback là bản ghi đã đọc nhưng không thể chuyển thành output hợp lệ. Nếu cần xử lý lại sau này, hãy lưu đủ business key và tham chiếu đến nguồn dữ liệu để tìm lại bản ghi.

## 5. `onSkipInWrite()` — ghi nhận item lỗi khi ghi

`onSkipInWrite()` được gọi khi writer không ghi được một item và Spring Batch xác định item đó là skippable. Listener nhận item đầu ra kiểu `S` cùng exception.

Ví dụ writer ghi đơn hàng vào database nhưng một bản ghi vi phạm constraint được cho phép skip:

```java
@Override
public void onSkipInWrite(Order item, Throwable t) {
    skippedOrderService.record(
            "WRITE",
            item.orderId(),
            t.getClass().getSimpleName(),
            t.getMessage());
}
```

Trong trường hợp lỗi ghi theo chunk, writer ban đầu có thể nhận cả một nhóm item. Để xác định item gây lỗi, Spring Batch có thể phải thử lại hoặc cô lập các item trong chunk theo cơ chế fault tolerance. Vì vậy, writer cần có hành vi tương thích với retry/rollback và không được tạo tác dụng phụ không kiểm soát khi được gọi lại.

`onSkipInWrite()` nhận từng item thực sự bị bỏ qua, không phải toàn bộ danh sách item trong chunk. Nếu cả chunk thất bại và exception không được skip hoặc đã vượt giới hạn, listener không được xem như một cơ chế thay thế cho xử lý lỗi writer; Step sẽ thất bại.

## 6. Cấu hình skip và đăng ký SkipListener

Để callback được gọi, Step phải được cấu hình fault tolerance và quy tắc skip. Sau đó đăng ký listener vào Step.

Ví dụ Spring Batch 5:

```java
@Bean
Step importOrdersStep(
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
```

Trong ví dụ:

- Lỗi parse file và lỗi validation đơn hàng được cho phép skip.
- Tổng số skip được giới hạn ở 50.
- Listener được đăng ký để ghi nhận các item thực sự bị bỏ qua.
- Những exception không được phân loại skippable vẫn có thể làm Step thất bại.

`skipLimit(50)` cho phép tối đa 50 skip theo chính sách của Step. Khi có lần skip tiếp theo vượt giới hạn, Step thất bại thay vì tiếp tục bỏ qua. Giới hạn này áp dụng tổng thể cho các skip trong giai đoạn đọc, xử lý và ghi, không phải 50 cho mỗi callback.

Nếu không cấu hình skip cho exception phù hợp, chỉ đăng ký `SkipListener` sẽ không khiến exception tự động được bỏ qua. Listener chỉ quan sát các quyết định skip đã được Step cho phép.

## 7. Triển khai SkipListener đầy đủ

Một listener có thể triển khai cả ba callback và chuyển thông tin lỗi cho service lưu trữ:

```java
@Component
public class OrderSkipListener
        implements SkipListener<OrderInput, Order> {

    private final SkippedItemService skippedItemService;

    public OrderSkipListener(SkippedItemService skippedItemService) {
        this.skippedItemService = skippedItemService;
    }

    @Override
    public void onSkipInRead(Throwable t) {
        skippedItemService.recordReadFailure(
                t.getClass().getName(),
                safeMessage(t),
                extractLineNumber(t));
    }

    @Override
    public void onSkipInProcess(OrderInput item, Throwable t) {
        skippedItemService.recordItemFailure(
                "PROCESS",
                item.orderId(),
                t.getClass().getName(),
                safeMessage(t));
    }

    @Override
    public void onSkipInWrite(Order item, Throwable t) {
        skippedItemService.recordItemFailure(
                "WRITE",
                item.orderId(),
                t.getClass().getName(),
                safeMessage(t));
    }

    private String safeMessage(Throwable t) {
        return t.getMessage() == null
                ? "No error message"
                : t.getMessage();
    }

    private Long extractLineNumber(Throwable t) {
        if (t instanceof FlatFileParseException ex) {
            return (long) ex.getLineNumber();
        }
        return null;
    }
}
```

Các phương thức `recordReadFailure()` và `recordItemFailure()` là API minh họa của service lưu lỗi. Khi triển khai thực tế, có thể lưu vào bảng `BATCH_SKIPPED_ITEM` hoặc một bảng nghiệp vụ riêng với các trường như:

| Trường | Ý nghĩa |
|---|---|
| `job_execution_id` | Lần thực thi Job phát sinh skip |
| `step_execution_id` | Step phát sinh skip |
| `stage` | READ, PROCESS hoặc WRITE |
| `item_key` | Business key của item nếu có |
| `source_location` | File, dòng, offset hoặc tham chiếu nguồn |
| `exception_type` | Lớp exception |
| `error_message` | Thông báo lỗi đã được làm sạch |
| `created_at` | Thời điểm ghi nhận |
| `retry_status` | Trạng thái xử lý lại nếu có quy trình replay |

Với lỗi đọc, `item_key` có thể không có vì chưa tạo được item. Khi đó, `source_location` như file và số dòng có thể giúp tìm lại dữ liệu.

## 8. Ghi nhận skip vào database hoặc dead-letter store

Một cách phổ biến là dùng service hoặc repository để ghi item lỗi vào bảng riêng. Bảng này có thể hỗ trợ người vận hành xem lỗi, sửa dữ liệu và chạy lại những item đã được xử lý riêng.

Ví dụ một record đơn giản:

```java
public record SkippedItemRecord(
        String stage,
        String itemKey,
        String exceptionType,
        String errorMessage,
        Instant skippedAt) {
}
```

Service:

```java
@Service
public class SkippedItemService {

    private final SkippedItemRepository repository;

    public SkippedItemService(SkippedItemRepository repository) {
        this.repository = repository;
    }

    public void recordItemFailure(
            String stage,
            String itemKey,
            String exceptionType,
            String errorMessage) {

        repository.save(new SkippedItemRecord(
                stage,
                itemKey,
                exceptionType,
                errorMessage,
                Instant.now()));
    }
}
```

Đây là ví dụ minh họa cấu trúc; repository và mapping database cần được triển khai theo schema của ứng dụng. Nên lưu cả JobExecution/StepExecution ID hoặc một business batch ID để liên kết bản ghi lỗi với lần chạy gốc.

### Vì sao thời điểm callback quan trọng?

Spring Batch gọi `SkipListener` ngay trước khi transaction của chunk được commit. Điều này giúp listener ghi nhận skip ở thời điểm item đã được xác định là bỏ qua và tránh callback bị gọi lặp do rollback của chunk trong những tình huống xử lý thông thường.

Nếu repository lưu skip record dùng cùng DataSource và transaction manager với Step, bản ghi skip có thể commit cùng transaction chunk. Nhờ vậy, dữ liệu đầu ra hợp lệ và thông tin skip có tính nhất quán trong cùng transaction.

Nếu listener ghi sang database khác, gọi HTTP API hoặc gửi message trực tiếp, thao tác đó không tự động thuộc transaction của chunk. Có thể xảy ra tình huống hệ thống ngoài đã nhận bản ghi lỗi nhưng transaction chunk sau đó rollback vì lỗi khác. Với yêu cầu audit bền vững, hãy cân nhắc transactional outbox hoặc cơ chế ghi nhận riêng có idempotency.

Nếu việc lưu skip record thất bại và exception thoát khỏi listener, chunk có thể thất bại/rollback. Đây thường là hành vi phù hợp khi yêu cầu nghiệp vụ bắt buộc mọi item bị skip phải được ghi nhận. Nếu chấp nhận mất một số log kỹ thuật, cần thiết kế kênh logging/metrics riêng và quyết định rõ chính sách thay vì âm thầm nuốt lỗi.

## 9. Phân biệt SkipListener với các Item Listener

Spring Batch có các listener để quan sát lỗi ở từng giai đoạn. Chúng có mục đích khác nhau:

| Listener | Callback lỗi | Khi nào được gọi? |
|---|---|---|
| `ItemReadListener` | `onReadError(Exception)` | Khi reader ném exception trong một lần đọc |
| `ItemProcessListener` | `onProcessError(item, Exception)` | Khi processor ném exception |
| `ItemWriteListener` | `onWriteError(Exception, items)` | Khi writer ném exception cho nhóm item |
| `SkipListener` | `onSkipInRead/Process/Write` | Khi exception được phân loại skippable và item thực sự bị bỏ qua |

Item listener quan sát lỗi phát sinh. SkipListener ghi nhận quyết định cuối cùng của fault-tolerant Step là bỏ qua item đó. Một exception có thể được retry trước; nếu retry thành công thì item không bị skip và `SkipListener` không được gọi cho item đó.

Ví dụ:

```text
Processor gặp lỗi
       |
       v
Exception có retry được?
    /         \
   Có          Không
   |             |
   v             v
 Retry        Xét skip policy
   |             |
   v             +---- Không skippable -> Step FAILED
 Thành công     |
   |             +---- Skippable và còn limit
   v                         |
 Tiếp tục                    v
 Không gọi SkipListener   SkipListener callback
```

Nếu exception vừa retryable vừa skippable, hành vi cuối cùng phụ thuộc retry/skip classification và cấu hình fault tolerance. Khi retry hết mà exception được phép skip, listener sẽ ghi nhận item bị bỏ qua. Cần thiết kế chính sách rõ ràng để tránh một lỗi tạm thời bị skip quá sớm.

## 10. Phân biệt skip với filter

Một processor có thể trả về `null` để chủ động loại item khỏi output:

```java
@Bean
ItemProcessor<OrderInput, Order> orderProcessor() {
    return input -> {
        if (input.isCancelled()) {
            return null; // Filter, không phải skip
        }
        return convert(input);
    };
}
```

Đây là **filter**, không phải skip. Không có exception và `SkipListener` không được gọi. Spring Batch ghi nhận trường hợp này bằng `filterCount`.

Ngược lại, nếu processor ném `InvalidOrderException` và Step cấu hình exception đó là skippable, item được bỏ qua do lỗi và `onSkipInProcess()` được gọi. Bộ đếm skip phản ánh trường hợp này.

| Tình huống | Cách thể hiện | Bộ đếm thường liên quan | SkipListener? |
|---|---|---|---|
| Chủ động loại item | Processor trả `null` | `filterCount` | Không |
| Item lỗi nhưng được phép bỏ qua | Reader/processor/writer ném exception skippable | Skip count theo giai đoạn | Có |
| Item lỗi không được phép bỏ qua | Exception không skippable hoặc vượt limit | Step thất bại | Không có callback skip thành công cho quyết định bị từ chối |
| Lỗi được retry và sau đó thành công | Retry thành công | Retry metrics/log tùy cấu hình | Không |

## 11. Skip limit và chính sách phân loại exception

`skipLimit(n)` giới hạn tổng số item được bỏ qua trong Step. Khi số lần skip vượt giới hạn, Step thất bại. Ví dụ, `skipLimit(10)` cho phép tối đa 10 item bị skip; lần skip tiếp theo vượt giới hạn và làm Step thất bại.

Có thể cấu hình loại exception được skip:

```java
.faultTolerant()
.skip(FlatFileParseException.class)
.skip(InvalidOrderException.class)
.skipLimit(10)
```

Hoặc chỉ định loại exception không được skip để loại trừ khỏi một nhóm rộng hơn:

```java
.faultTolerant()
.skip(Exception.class)
.noSkip(DeadlockLoserDataAccessException.class)
.skipLimit(20)
```

Ví dụ thứ hai chỉ nên dùng khi có lý do rõ ràng. Nếu skip mọi `Exception`, nhiều lỗi hạ tầng hoặc lỗi lập trình có thể bị bỏ qua ngoài ý muốn. Thông thường nên khai báo cụ thể exception nghiệp vụ có thể bỏ qua và để các lỗi không xác định làm Step thất bại.

Khi quy tắc phân loại phức tạp theo exception, loại dữ liệu hoặc ngữ cảnh, có thể triển khai `SkipPolicy` tùy chỉnh. Policy quyết định exception có thể skip hay không; `SkipListener` ghi nhận item sau khi quyết định skip đã được chấp nhận.

## 12. SkipListener và retry: tránh ghi nhận sai thời điểm

Một item có thể gặp lỗi nhưng chưa chắc sẽ bị skip. Ví dụ, processor gặp timeout khi gọi service ngoài. Spring Batch retry item; nếu lần retry tiếp theo thành công thì item vẫn được xử lý bình thường.

Do đó, không nên ghi item vào dead-letter store ngay trong `ItemProcessListener.onProcessError()` nếu mục tiêu là ghi nhận những item cuối cùng bị skip. Callback lỗi có thể xảy ra trong một lần thử mà sau đó thành công.

`SkipListener` phù hợp hơn cho việc ghi nhận kết quả cuối cùng: item đã bị loại khỏi pipeline theo skip policy. Đây cũng là lý do framework cung cấp listener riêng thay vì yêu cầu ứng dụng tự suy luận từ các callback lỗi.

Khi có retry, cần phân biệt:

- **Attempt error:** một lần thử gặp lỗi.
- **Retry:** framework thử lại thao tác hoặc item.
- **Skip:** item được chấp nhận bỏ qua sau khi áp dụng policy.
- **Step failure:** lỗi không được retry/skip hoặc đã vượt giới hạn.

Metrics retry và skip nên được theo dõi riêng. Một Job có nhiều retry nhưng không có skip có thể vẫn xử lý đầy đủ mọi item; ngược lại, nhiều skip có thể làm kết quả nghiệp vụ thiếu dữ liệu dù Job kết thúc `COMPLETED`.

## 13. Thiết kế dead-letter record để xử lý lại

Nếu cần xử lý lại item bị skip, bản ghi lỗi nên lưu đủ thông tin để tái tạo đầu vào và hiểu lý do thất bại.

Một thiết kế có thể gồm:

| Nhóm thông tin | Ví dụ |
|---|---|
| Định danh | JobExecution ID, StepExecution ID, batch ID, item key |
| Nguồn | File, line number, source system, input version |
| Lỗi | Stage, exception type, error code, message đã làm sạch |
| Payload | Nội dung cần thiết hoặc tham chiếu đến bản ghi nguồn |
| Trạng thái xử lý lại | NEW, INVESTIGATING, READY_TO_REPLAY, REPLAYED, PERMANENT_FAILURE |
| Audit | Người sửa, thời điểm sửa, replay execution ID |

Không nhất thiết phải lưu toàn bộ payload vào bảng lỗi. Nếu dữ liệu chứa thông tin cá nhân hoặc nhạy cảm, có thể lưu business key và tham chiếu đến nguồn được bảo vệ. Nếu cần lưu payload, hãy áp dụng mã hóa, phân quyền và chính sách retention phù hợp.

Quy trình replay nên tạo một lần thực thi có thể truy vết, giữ business key ổn định và bảo đảm writer idempotent. Không nên sửa trực tiếp JobRepository metadata để ép item được đọc lại; hãy dùng bảng dead-letter hoặc nguồn đầu vào đã được quản lý.

## 14. Listener có thể dùng annotation không?

Ngoài cách triển khai interface, Spring Batch hỗ trợ các annotation listener tương ứng:

- `@OnSkipInRead`
- `@OnSkipInProcess`
- `@OnSkipInWrite`

Ví dụ:

```java
public class AnnotatedOrderSkipListener {

    @OnSkipInRead
    public void onReadSkip(Throwable t) {
        log.warn("Read skip: {}", t.toString());
    }

    @OnSkipInProcess
    public void onProcessSkip(OrderInput item, Throwable t) {
        log.warn("Process skip for order {}: {}",
                item.orderId(), t.toString());
    }

    @OnSkipInWrite
    public void onWriteSkip(Order item, Throwable t) {
        log.warn("Write skip for order {}: {}",
                item.orderId(), t.toString());
    }
}
```

Đăng ký object chứa các method annotation với Step bằng `.listener(annotatedOrderSkipListener)`. Tham số method cần phù hợp với loại callback: read nhận exception; process và write nhận item cùng exception. Interface `SkipListener` thường dễ đọc và an toàn kiểu hơn khi muốn triển khai đầy đủ cả ba callback.

## 15. Thread safety và nhiều Step chạy song song

Nếu Step hoặc Job có xử lý song song, listener bean có thể được gọi từ nhiều thread. Không nên lưu item hiện tại hoặc exception hiện tại trong mutable field của singleton listener:

```java
// Không an toàn khi nhiều thread cùng gọi listener
private String currentOrderId;
```

Hãy dùng biến cục bộ trong callback và chuyển dữ liệu trực tiếp cho service. Repository lưu skip record cần chịu được ghi đồng thời; nên có khóa duy nhất phù hợp để tránh bản ghi trùng khi có retry hoặc khi hệ thống gửi lại cùng một sự kiện.

Nếu cần ghi tên Job, Step hoặc execution ID, có thể lấy ngữ cảnh Step hiện tại qua scope phù hợp hoặc `StepSynchronizationManager` trong lúc callback được thực thi. Cần tránh giữ `StepExecution` hoặc context của một thread trong field để dùng ở thread khác.

Khi nhiều worker cùng ghi một bảng dead-letter, nên tạo index theo batch ID, execution ID và item key để hỗ trợ tra cứu, đồng thời thiết kế unique key theo nghiệp vụ nếu một item chỉ nên có một bản ghi skip cho một lần chạy logic.

## 16. Logging, metrics và bảo mật

SkipListener là nơi phù hợp để tạo log hoặc metrics cho item bị bỏ qua. Các thông tin hữu ích:

- Tổng skip theo giai đoạn READ, PROCESS và WRITE.
- Tỷ lệ skip trên tổng số item đọc.
- Nhóm exception thường gặp.
- Top source file hoặc source system có nhiều lỗi.
- Số item chờ replay và thời gian tồn đọng.
- JobExecution/StepExecution liên quan.

Không nên log toàn bộ raw line hoặc object nếu chứa email, số điện thoại, thông tin tài khoản hay dữ liệu nhạy cảm. Chỉ ghi business key và phần thông tin tối thiểu để điều tra. Thông báo exception có thể chứa SQL, đường dẫn nội bộ hoặc dữ liệu đầu vào; hãy làm sạch trước khi lưu vào nơi có nhiều người truy cập.

Nếu skip rate vượt một ngưỡng nghiệp vụ, có thể để Step thất bại qua `skipLimit` hoặc kiểm tra tỷ lệ lỗi ở Step tổng hợp. Job `COMPLETED` không đồng nghĩa dữ liệu không có lỗi; cần đánh giá cả số lượng và tỷ lệ skip trước khi công bố kết quả.

## 17. Kiểm thử SkipListener

Nên kiểm thử từng callback và hành vi tổng thể của Step:

1. Reader ném exception skippable: xác nhận `onSkipInRead()` được gọi.
2. Processor ném exception skippable: xác nhận item đầu vào được truyền vào `onSkipInProcess()`.
3. Writer không ghi được một item skippable: xác nhận `onSkipInWrite()` nhận đúng item đầu ra.
4. Exception được retry rồi thành công: xác nhận item không bị ghi nhận là skipped.
5. Processor trả `null`: xác nhận đây là filter và SkipListener không được gọi.
6. Vượt `skipLimit`: xác nhận Step thất bại và không tiếp tục bỏ qua vô hạn.
7. Ghi dead-letter record lỗi: xác nhận hành vi transaction và trạng thái Step đúng với chính sách mong muốn.
8. Chạy song song: xác nhận listener và repository không có race condition hoặc ghi trùng ngoài ý muốn.

Có thể dùng mock service để kiểm tra callback và Spring Batch test utilities để chạy Job/Step trong môi trường kiểm thử. Với trường hợp write skip, nên kiểm tra cả writer có thể được gọi lại trong quá trình cô lập item và mọi thao tác ghi đều an toàn khi retry.

## 18. Các lỗi thường gặp

**Chỉ đăng ký SkipListener mà không cấu hình skip:** listener không tự cho phép bỏ qua exception. Cần `.faultTolerant()` và quy tắc `.skip(...)` hoặc `SkipPolicy`.

**Nhầm lỗi với skip:** một exception phát sinh chưa chắc item đã bị skip. Retry có thể thành công hoặc Step có thể thất bại.

**Dùng `onSkipInRead()` để lấy item:** callback này không nhận item vì reader có thể chưa tạo được object. Hãy trích xuất vị trí hoặc dữ liệu từ exception nếu có.

**Dùng ItemProcessListener để ghi dead-letter cuối cùng:** callback lỗi xử lý có thể xảy ra trong lần retry sau đó thành công. Dùng SkipListener để ghi nhận item thực sự bị bỏ qua.

**Coi filter là skip:** processor trả `null` là filter, không phải exception skip; listener không được gọi.

**Skip mọi exception:** có thể che giấu lỗi hạ tầng, lỗi lập trình hoặc lỗi làm mất dữ liệu. Chỉ cho phép skip các exception có ý nghĩa nghiệp vụ rõ ràng.

**Bỏ qua skip limit:** giới hạn giúp Job dừng khi dữ liệu lỗi vượt mức chấp nhận. Không nên để một Job hoàn tất với tỷ lệ lỗi không kiểm soát.

**Gửi API hoặc email trực tiếp trong callback:** tác dụng phụ bên ngoài không tự rollback cùng transaction. Dùng outbox hoặc idempotency nếu cần bảo đảm giao nhận.

**Lưu payload nhạy cảm vào log:** có thể làm lộ dữ liệu. Chỉ lưu business key và thông tin tối thiểu đã được làm sạch.

## Kết luận

`SkipListener` ghi nhận item mà Spring Batch đã quyết định bỏ qua trong một fault-tolerant Step. `onSkipInRead()` nhận exception khi không đọc được item; `onSkipInProcess()` nhận item đầu vào và exception khi xử lý thất bại; `onSkipInWrite()` nhận item đầu ra và exception khi ghi thất bại. Listener chỉ được gọi khi exception thực sự được skip theo policy và giới hạn, không phải với mọi lỗi, retry thành công hoặc item bị filter. Hãy lưu business key, giai đoạn và nguyên nhân vào dead-letter/audit store, hiểu callback được gọi ngay trước khi transaction chunk commit và bảo đảm thao tác lưu lỗi an toàn khi retry hoặc chạy song song. Cấu hình skip có giới hạn và theo dõi skip rate giúp Job tiếp tục xử lý dữ liệu hợp lệ mà vẫn giữ khả năng điều tra và xử lý lại các item lỗi.
