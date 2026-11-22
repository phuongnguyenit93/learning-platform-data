# ItemReadListener

Trong Spring Batch, ItemReader chịu trách nhiệm lấy từng item từ nguồn dữ liệu. Khi cần quan sát quá trình đọc, ghi log, đo thời gian hoặc ghi nhận lỗi đọc, có thể dùng **ItemReadListener**. Listener này cung cấp callback trước khi reader được gọi, sau khi một item được đọc thành công và khi reader ném exception.

ItemReadListener là một phần của cơ chế listener trong chunk-oriented Step. Nó bổ sung hành vi quan sát quanh hoạt động đọc mà không cần đưa toàn bộ logic đó vào reader. Listener không thay thế ItemReader, không biến đổi item và cũng không tự quyết định một lỗi có được skip hay retry hay không.

## 1. ItemReadListener nằm ở đâu trong chunk processing?

Một chunk-oriented Step thường có luồng:

~~~text
ItemReader
    |
    +-- beforeRead()
    |
    +-- reader.read()
    |
    +-- afterRead(item) nếu trả về item
    |
    +-- hoặc onReadError(exception) nếu reader ném lỗi
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

ItemReadListener quan sát ranh giới gọi ItemReader. Ba callback được gọi theo vòng đời đọc:

- **beforeRead()**: được gọi trước khi Spring Batch gọi read() trên reader.
- **afterRead(item)**: được gọi sau khi reader trả về một item thành công.
- **onReadError(exception)**: được gọi khi reader ném exception trong quá trình đọc.

Reader trả về null để báo đã hết dữ liệu. Null không phải một item được chuyển tiếp đến processor hoặc writer, vì vậy không có item để xử lý trong afterRead. beforeRead vẫn có thể được gọi cho lần đọc cuối cùng dùng để phát hiện hết dữ liệu.

Listener không quyết định reader sẽ đọc item nào hoặc thứ tự đọc. Những việc đó vẫn thuộc về ItemReader và cấu hình nguồn dữ liệu.

## 2. Hợp đồng ItemReadListener

Interface ItemReadListener có ba phương thức:

~~~java
public interface ItemReadListener<T> {

    void beforeRead();

    void afterRead(T item);

    void onReadError(Exception ex);
}
~~~

Listener được tham số hóa theo kiểu item mà reader trả về. Nếu reader đọc OrderInput, listener nên triển khai ItemReadListener<OrderInput>.

### beforeRead()

Callback này chạy trước mỗi lần gọi reader. Có thể dùng để:

- Ghi log bắt đầu thao tác đọc.
- Bắt đầu đo thời gian đọc nếu có cơ chế lưu thời điểm tương ứng.
- Ghi nhận số lần reader được gọi.
- Thêm thông tin chẩn đoán cho một nguồn đọc cụ thể.

Không nên dùng beforeRead() để thay đổi trạng thái nguồn dữ liệu hoặc tự đọc trước item. Reader vẫn phải là thành phần duy nhất chịu trách nhiệm lấy item.

### afterRead(item)

Callback nhận item vừa được đọc thành công. Có thể dùng để:

- Ghi log mã định danh của item.
- Đếm số item đã được reader trả về.
- Ghi nhận kích thước hoặc loại dữ liệu.
- Phát metric phục vụ quan sát pipeline.

Không nên sửa item trong callback. Nếu cần chuẩn hóa hoặc biến đổi dữ liệu, hãy dùng ItemProcessor để trách nhiệm rõ ràng và dễ kiểm thử.

### onReadError(exception)

Callback này nhận exception do reader ném ra. Có thể dùng để:

- Ghi log loại lỗi và stack trace.
- Gắn thông tin nguồn đọc hoặc Job/Step vào log.
- Tăng metric lỗi đọc.
- Gửi tín hiệu quan sát đến hệ thống monitoring.

onReadError chỉ thông báo rằng một lần đọc đã gặp exception. Nó không tự quyết định exception được retry, skip hay làm Step thất bại. Quyết định đó phụ thuộc cơ chế fault-tolerant, retry/skip policy và loại exception.

## 3. Viết một ItemReadListener

Ví dụ listener cho reader đọc đơn hàng từ file:

~~~java
import org.springframework.batch.core.ItemReadListener;

public class OrderReadListener
        implements ItemReadListener<OrderInput> {

    private static final Logger log =
            LoggerFactory.getLogger(OrderReadListener.class);

    @Override
    public void beforeRead() {
        log.debug("About to read an order record");
    }

    @Override
    public void afterRead(OrderInput item) {
        log.debug("Read orderId={}", item.getOrderId());
    }

    @Override
    public void onReadError(Exception ex) {
        log.error("Failed to read an order record", ex);
    }
}
~~~

beforeRead và afterRead giúp quan sát đường đọc bình thường. onReadError ghi lại exception để người vận hành biết reader đã gặp vấn đề gì.

Trong hệ thống thực tế, nên log mã định danh và thông tin kỹ thuật đủ để điều tra. Tránh log toàn bộ object nếu item có thông tin cá nhân, dữ liệu tài chính hoặc payload lớn. Không log credentials, token hoặc nội dung nhạy cảm.

## 4. Đăng ký listener vào Step

Có thể đăng ký listener trực tiếp khi cấu hình Step. Ví dụ với Spring Batch 5 trở lên:

~~~java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        ItemWriter<Order> orderWriter,
        OrderReadListener orderReadListener) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .listener(orderReadListener)
            .build();
}
~~~

Lệnh listener(orderReadListener) đăng ký listener vào Step. Spring Batch gọi các callback phù hợp khi reader được thực thi.

Có thể khai báo listener thành bean:

~~~java
@Bean
public OrderReadListener orderReadListener() {
    return new OrderReadListener();
}
~~~

Khi dùng listener chung cho nhiều Step, cần bảo đảm listener không giữ trạng thái riêng của một lần chạy nếu bean có thể được dùng đồng thời. Nếu cần thông tin theo từng StepExecution, hãy thiết kế scope và cách truy cập trạng thái phù hợp.

## 5. Dùng annotation thay cho interface

Spring Batch cũng hỗ trợ listener method thông qua annotation. Có thể viết một POJO với các phương thức được đánh dấu:

- @BeforeRead
- @AfterRead
- @OnReadError

Ví dụ:

~~~java
public class OrderReadAnnotationListener {

    private static final Logger log =
            LoggerFactory.getLogger(OrderReadAnnotationListener.class);

    @BeforeRead
    public void beforeRead() {
        log.debug("Starting to read an order");
    }

    @AfterRead
    public void afterRead(OrderInput item) {
        log.debug("Read orderId={}", item.getOrderId());
    }

    @OnReadError
    public void onReadError(Exception exception) {
        log.error("Order read failed", exception);
    }
}
~~~

POJO listener được đăng ký vào Step bằng listener(...) giống listener triển khai interface:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .listener(orderReadAnnotationListener)
        .build();
~~~

Annotation giúp viết listener gọn khi chỉ cần một vài callback. Interface phù hợp khi muốn thể hiện rõ hợp đồng, dùng type parameter hoặc cần triển khai logic có cấu trúc. Nên chọn một cách nhất quán trong cùng thành phần để người đọc dễ hiểu.

## 6. ItemReadListener và lỗi đọc

Lỗi đọc có thể phát sinh ở nhiều vị trí:

- Không mở được file hoặc resource.
- Dòng CSV sai định dạng hoặc không chuyển được kiểu.
- Database connection bị gián đoạn.
- Truy vấn reader thất bại.
- Dữ liệu nguồn không đáp ứng cấu trúc mà reader mong đợi.
- API nguồn trả lỗi hoặc timeout.

Khi reader ném exception trong lời gọi read(), onReadError được gọi để quan sát lỗi. Sau đó exception tiếp tục được xử lý theo cơ chế thực thi Step. Tùy cấu hình, Step có thể thất bại, retry hoặc skip lỗi đó.

Ví dụ:

~~~java
public class OrderReadListener
        implements ItemReadListener<OrderInput> {

    private static final Logger log =
            LoggerFactory.getLogger(OrderReadListener.class);

    @Override
    public void beforeRead() {
        log.debug("Reading next order input");
    }

    @Override
    public void afterRead(OrderInput item) {
        log.debug("Successfully read orderId={}", item.getOrderId());
    }

    @Override
    public void onReadError(Exception ex) {
        log.error(
                "Reader failed; exceptionType={}",
                ex.getClass().getSimpleName(),
                ex);
    }
}
~~~

Không nên bắt exception trong listener rồi coi thao tác đọc như thành công. Listener nên quan sát và để Step áp dụng chính sách lỗi. Nếu callback tự ném exception, exception từ listener cũng có thể làm gián đoạn Step; vì vậy callback nên ngắn, ổn định và tránh các thao tác có khả năng thất bại không cần thiết.

## 7. Phân biệt ItemReadListener với SkipListener

Hai listener này có liên quan khi xử lý lỗi đọc, nhưng mục đích khác nhau:

| Listener | Callback | Ý nghĩa |
| --- | --- | --- |
| ItemReadListener | onReadError(Exception ex) | Quan sát exception xảy ra trong lần đọc |
| SkipListener | onSkipInRead(Throwable t) | Được gọi khi exception đọc thực sự được phân loại và xử lý bằng skip |

onReadError không có nghĩa item đã bị skip. Exception có thể làm Step thất bại hoặc được retry. onSkipInRead chỉ phản ánh trường hợp exception được chính sách skip chấp nhận.

Ví dụ đăng ký skip listener:

~~~java
public class OrderSkipListener
        implements SkipListener<OrderInput, Order> {

    @Override
    public void onSkipInRead(Throwable t) {
        // Ghi nhận lỗi đọc không có item đã được tạo thành công.
    }

    @Override
    public void onSkipInProcess(OrderInput item, Throwable t) {
        // Ghi nhận input không hợp lệ trong processor.
    }

    @Override
    public void onSkipInWrite(Order item, Throwable t) {
        // Ghi nhận lỗi khi ghi output.
    }
}
~~~

Step có thể cấu hình skip cho exception đọc cụ thể:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(FlatFileParseException.class)
        .skipLimit(50)
        .listener(orderReadListener)
        .listener(orderSkipListener)
        .build();
~~~

Ví dụ minh họa cho phép skip tối đa 50 lỗi parse thuộc loại được cấu hình. Cần xác định chính xác exception mà reader phát ra trong ứng dụng và chỉ skip lỗi dữ liệu có thể bỏ qua theo yêu cầu nghiệp vụ. Không nên skip mọi Exception vì có thể che giấu lỗi hệ thống.

Với lỗi đọc, đôi khi không có item hợp lệ để truyền cho onSkipInRead; listener nhận exception và có thể trích xuất thông tin dòng hoặc nguồn nếu exception chứa chúng. Với FlatFileParseException, có thể có thông tin về input line và số dòng để phục vụ đối soát.

## 8. ItemReadListener không thay thế retry policy

Retry policy quyết định một lỗi có được thử lại hay không và tối đa bao nhiêu lần. ItemReadListener chỉ cung cấp callback quan sát.

Ví dụ Step có retry cho lỗi truy cập dữ liệu tạm thời:

~~~java
return new StepBuilder("readOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .listener(orderReadListener)
        .build();
~~~

Nếu reader ném TransientDataAccessException và lỗi được retry, callback đọc lỗi có thể được gọi cho lần đọc gặp lỗi. Khi lần thử tiếp theo thành công, afterRead được gọi cho item trả về thành công.

Không nên dùng listener để tự lặp gọi reader hoặc thực hiện retry bằng vòng lặp riêng. Làm vậy có thể phá vỡ quản lý transaction, retry context và metadata mà Spring Batch cung cấp.

Retry cũng có thể khiến một thao tác đọc được thực hiện lại. Reader nên có hành vi phù hợp khi đọc lại, đặc biệt nếu nguồn dữ liệu có trạng thái hoặc bị thay đổi giữa các lần thử.

## 9. ItemReadListener và transaction

Trong chunk-oriented Step, callback đọc diễn ra trong quá trình xử lý chunk và thường nằm trong transaction của chunk. Vì vậy, listener nên tránh các thao tác phụ kéo dài hoặc tạo side effect ngoài transaction.

Ví dụ, nếu afterRead gọi một REST API cho từng item, thời gian xử lý chunk có thể tăng và transaction database bị giữ mở trong lúc chờ mạng. Nếu API timeout, callback có thể làm Step thất bại dù việc đọc item đã thành công.

Các nguyên tắc thực hành:

- Giữ callback ngắn, ưu tiên log và metric nhẹ.
- Không thực hiện ghi database không cần thiết trong callback.
- Không gọi dịch vụ từ xa đồng bộ cho từng item nếu có thể xử lý ở bước khác.
- Không giả định side effect bên ngoài sẽ rollback cùng transaction của Step.
- Nếu cần ghi audit bền vững, hãy chọn transaction boundary và cơ chế outbox phù hợp.

Listener không phải nơi thích hợp để triển khai nghiệp vụ quan trọng mà kết quả cần được commit cùng item. Hãy đặt nghiệp vụ đó trong processor, writer hoặc service có transaction rõ ràng.

## 10. Thread safety và scope của listener

Với Step tuần tự, callback thường được gọi theo một luồng xử lý. Nhưng khi Step chạy đa luồng, reader hoặc các phần của pipeline có thể được gọi từ nhiều thread tùy cấu hình.

Nếu listener giữ state như counter, danh sách item hoặc timestamp trong field, các thread có thể truy cập đồng thời. Một biến long tăng đơn giản không tự bảo đảm an toàn khi nhiều thread cùng cập nhật.

Ví dụ listener có state dễ gặp race condition:

~~~java
public class CountingReadListener
        implements ItemReadListener<OrderInput> {

    private long readCount;

    @Override
    public void afterRead(OrderInput item) {
        readCount++;
    }
}
~~~

Nếu callback chạy đồng thời, giá trị có thể bị mất cập nhật. Nếu thực sự cần bộ đếm riêng trong listener, hãy dùng AtomicLong hoặc cơ chế đồng bộ phù hợp:

~~~java
private final AtomicLong readCount = new AtomicLong();

@Override
public void afterRead(OrderInput item) {
    readCount.incrementAndGet();
}
~~~

Tuy nhiên, nếu mục tiêu chỉ là biết số item đã đọc, nên ưu tiên các counter trong StepExecution hoặc metric được Spring Batch cung cấp thay vì tự duy trì một bộ đếm song song.

Không nên giả định @StepScope tự động làm một listener an toàn với mọi mô hình concurrency. Scope điều khiển vòng đời bean; thread safety vẫn phụ thuộc vào cách listener được gọi và state mà nó giữ. Listener stateless thường dễ dùng an toàn hơn.

## 11. Ghi nhận số liệu đọc

ItemReadListener có thể được dùng để phát metric hoặc log, nhưng StepExecution đã cung cấp các counter hữu ích:

- readCount: số item đã được đọc.
- readSkipCount: số lỗi đọc được skip.
- filterCount: số item bị filter bởi processor.
- writeCount: số item đã ghi.
- processSkipCount và writeSkipCount: số lỗi skip ở các giai đoạn tương ứng.

Các counter này giúp phân biệt số item reader trả về với số item được ghi cuối cùng. Ví dụ, nếu readCount cao nhưng writeCount thấp, có thể processor đã filter nhiều item hoặc có lỗi skip.

Có thể quan sát StepExecution qua listener vòng đời Step hoặc JobExplorer. Không nên chỉ dựa vào số lần beforeRead để suy ra số item hợp lệ vì lần đọc cuối trả null cũng có thể được gọi sau callback trước đọc.

Nếu cần metric riêng cho latency đọc, có thể đo khoảng thời gian giữa callback trước và sau. Với listener đa luồng, không dùng một biến timestamp dùng chung cho mọi lần đọc; hãy dùng state theo thread hoặc instrumentation an toàn.

## 12. Ví dụ hoàn chỉnh: cấu hình reader và listener

Ví dụ sau minh họa một Step đọc file, chuyển đổi dữ liệu và ghi vào đích:

~~~java
@Configuration
public class OrderImportConfiguration {

    @Bean
    public OrderReadListener orderReadListener() {
        return new OrderReadListener();
    }

    @Bean
    public Step importOrdersStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ItemReader<OrderInput> orderReader,
            ItemProcessor<OrderInput, Order> orderProcessor,
            ItemWriter<Order> orderWriter,
            OrderReadListener orderReadListener) {

        return new StepBuilder("importOrdersStep", jobRepository)
                .<OrderInput, Order>chunk(100, transactionManager)
                .reader(orderReader)
                .processor(orderProcessor)
                .writer(orderWriter)
                .listener(orderReadListener)
                .build();
    }
}
~~~

Listener quan sát ba thời điểm:

1. Trước mỗi lần reader được gọi.
2. Sau khi reader trả về một OrderInput.
3. Khi reader ném exception.

Nó không thay đổi dữ liệu và không quyết định cách xử lý lỗi. Các quyết định đó thuộc reader, processor, writer và cấu hình fault-tolerant của Step.

## 13. Kiểm thử ItemReadListener

Có thể kiểm thử listener độc lập bằng cách gọi trực tiếp các callback:

~~~java
class OrderReadListenerTest {

    @Test
    void afterReadAcceptsReadItem() {
        OrderReadListener listener = new OrderReadListener();
        OrderInput input = new OrderInput();
        input.setOrderId("ORD-1001");

        assertDoesNotThrow(() -> listener.afterRead(input));
    }

    @Test
    void onReadErrorAcceptsReaderException() {
        OrderReadListener listener = new OrderReadListener();
        Exception exception = new IllegalStateException("Read failed");

        assertDoesNotThrow(() -> listener.onReadError(exception));
    }
}
~~~

Nếu listener phát metric hoặc ghi audit, có thể mock collaborator để xác nhận callback gọi đúng dependency với dữ liệu cần thiết.

Ở mức Step test, nên kiểm tra:

- beforeRead được gọi khi reader được yêu cầu đọc.
- afterRead nhận đúng item reader trả về.
- onReadError nhận exception từ reader.
- Lỗi đọc được xử lý đúng theo skip/retry policy.
- onSkipInRead chỉ được gọi khi exception thực sự bị skip.
- Listener không làm thay đổi item hoặc kết quả nghiệp vụ.

Không nên chỉ kiểm thử callback bằng cách gọi thủ công rồi kết luận toàn bộ wiring của Step đúng. Một Step test với reader giả lập sẽ xác nhận listener đã được đăng ký và được framework gọi ở đúng vị trí.

## 14. Những lỗi thường gặp

### Dùng afterRead để biến đổi item

Listener chỉ nên quan sát. Nếu cần thay đổi item, hãy dùng ItemProcessor để thể hiện transformation rõ ràng.

### Nghĩ onReadError có nghĩa item đã bị skip

Callback chỉ báo lỗi đọc. Exception có thể làm Step fail hoặc được retry. Dùng SkipListener.onSkipInRead để ghi nhận trường hợp thực sự bị skip.

### Bắt exception và không cho Step biết lỗi

Nếu listener nuốt lỗi hoặc can thiệp vào luồng xử lý, trạng thái Step có thể không phản ánh đúng sự cố. Để reader và fault-tolerant policy xử lý exception.

### Ghi toàn bộ item vào log

Payload có thể lớn hoặc chứa dữ liệu nhạy cảm. Chỉ ghi mã định danh và thông tin cần thiết để điều tra.

### Thực hiện gọi API trong afterRead

Gọi dịch vụ từ xa cho mỗi item làm chậm pipeline và có thể giữ transaction mở. Chuyển nghiệp vụ đó sang processor/writer hoặc một Step phù hợp.

### Giữ state không thread-safe

Listener dùng chung trong môi trường đa luồng có thể gặp race condition. Ưu tiên listener stateless hoặc dùng cơ chế đồng bộ phù hợp.

### Dùng listener thay cho reader

Listener không phải nơi lấy dữ liệu, retry hoặc tự điều khiển nguồn đọc. Những trách nhiệm đó thuộc ItemReader và cơ chế thực thi Step.

### Cho rằng callback được gọi đúng một lần cho mỗi item nghiệp vụ

Retry, rollback và restart có thể làm một thao tác đọc được thử lại. Listener quan sát các lần gọi thực tế; không dùng callback như một nguồn duy nhất để tạo số thứ tự nghiệp vụ bền vững.

## 15. Cách thiết kế ItemReadListener

Khi thêm listener cho một Step, hãy xác định:

1. Cần quan sát trước đọc, sau đọc hay khi đọc lỗi?
2. Thông tin nào đủ để điều tra mà không làm lộ payload nhạy cảm?
3. Có cần metric riêng hay counter của StepExecution đã đáp ứng?
4. Lỗi đọc nào được retry, lỗi nào được skip và lỗi nào phải làm Step thất bại?
5. Có cần SkipListener để lưu bản ghi bị từ chối không?
6. Callback có thực hiện I/O hoặc side effect kéo dài không?
7. Listener có giữ state và có thể được gọi đồng thời không?
8. Có thể kiểm thử listener độc lập và kiểm thử wiring của Step không?

Một ItemReadListener tốt giữ callback nhỏ, không thay đổi dữ liệu, không nuốt exception và cung cấp đủ thông tin quan sát để vận hành Step.

## Kết luận

ItemReadListener cung cấp ba callback beforeRead, afterRead và onReadError để quan sát vòng đời đọc item trong Spring Batch. Nó phù hợp cho log, metric và chẩn đoán lỗi quanh ItemReader. Listener không thay thế retry/skip policy: onReadError chỉ ghi nhận lỗi, còn SkipListener xác nhận exception thực sự được skip. Hãy giữ callback ngắn, tránh thay đổi item hoặc side effect không cần thiết, và bảo đảm thread safety khi Step chạy đồng thời.
