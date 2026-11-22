# Exception contract

Trong Spring Batch, custom reader, processor, writer, tasklet và các thành phần hỗ trợ đều cần có quy ước rõ ràng về lỗi. Một component có thể gặp dữ liệu sai, lỗi kết nối tạm thời, lỗi cấu hình, lỗi tài nguyên hoặc lỗi lập trình. Nếu mọi lỗi đều bị chuyển thành cùng một exception chung, framework khó phân biệt trường hợp nào nên retry, trường hợp nào nên skip và trường hợp nào phải dừng job ngay.

**Exception contract** là thỏa thuận về loại lỗi mà component có thể phát sinh, ý nghĩa của từng lỗi, thông tin ngữ cảnh được giữ lại và cách lỗi được truyền cho Spring Batch. Một contract tốt giúp retry/skip policy phân loại chính xác, transaction rollback đúng lúc, log có thể điều tra và test có thể xác nhận hành vi.

Trong Spring Batch, các interface cốt lõi cho phép component ném exception. Ví dụ, ItemReader, ItemProcessor, ItemWriter và Tasklet đều có method khai báo throws Exception. Một custom component nên tận dụng contract đó, giữ nguyên nguyên nhân gốc và tránh che giấu lỗi. Việc ném exception, đánh dấu item là filtered, kết thúc step bằng ExitStatus và yêu cầu retry là các hành vi khác nhau, cần được dùng đúng mục đích.

## 1. Exception contract là gì?

Exception contract mô tả những điều caller có thể kỳ vọng khi một component không hoàn thành công việc. Contract nên trả lời:

- Component có thể phát sinh những nhóm lỗi nào?
- Lỗi nào là dữ liệu nghiệp vụ không hợp lệ?
- Lỗi nào là tạm thời và có thể retry?
- Lỗi nào là lỗi cấu hình hoặc lỗi không thể phục hồi?
- Lỗi xảy ra ở giai đoạn read, process, write hay lifecycle?
- Component có giữ nguyên cause khi chuyển đổi exception không?
- Transaction có nên rollback khi lỗi xảy ra không?
- Lỗi được skip, retry hay làm step/job thất bại?
- Log và metadata có đủ thông tin để tìm item/resource liên quan không?

Ví dụ một custom API reader có thể định nghĩa:

| Exception | Ý nghĩa | Hướng xử lý thường dùng |
|---|---|---|
| InvalidResponseException | Payload từ đối tác sai cấu trúc hoặc không đáp ứng contract | Dừng hoặc skip theo quy tắc dữ liệu |
| PartnerUnavailableException | API timeout hoặc trả lỗi tạm thời | Retry có giới hạn và backoff |
| AuthenticationConfigurationException | Credential/configuration không hợp lệ | Fail fast, không retry liên tục |
| SourceSnapshotChangedException | Nguồn đã thay đổi so với checkpoint | Dừng để tránh đọc sai dữ liệu |
| ItemNotFoundException | Không có dữ liệu tương ứng với key | Tùy nghiệp vụ: skip, filter hoặc fail |

Tên exception nên diễn tả ý nghĩa mà caller cần biết, không chỉ lặp lại tên kỹ thuật của thư viện gây lỗi.

## 2. Exception contract trong các interface Spring Batch

Các interface chính cho phép custom component báo lỗi bằng exception:

| Interface | Method | Contract quan trọng |
|---|---|---|
| ItemReader<T> | read() | Trả item kế tiếp, trả null khi hết dữ liệu, ném exception nếu không thể đọc |
| ItemProcessor<I,O> | process(I) | Trả output, trả null để filter item, ném exception nếu xử lý thất bại |
| ItemWriter<T> | write(Chunk<? extends T>) | Ghi chunk, ném exception nếu không thể hoàn thành theo contract |
| Tasklet | execute(...) | Trả RepeatStatus khi hoàn tất/lặp tiếp, ném exception khi lần thực thi thất bại |
| ItemStream | open/update/close | Quản lý lifecycle resource và state; dùng ItemStreamException cho lỗi lifecycle |

Các method của reader, processor, writer và tasklet khai báo có thể ném Exception. Vì vậy, custom implementation không bắt buộc phải bọc mọi checked exception thành RuntimeException. Hãy chọn exception có ý nghĩa, giữ nguyên cause và để framework nhận được lỗi.

Không nên dùng null hoặc một object rỗng để biểu diễn lỗi đọc. Với ItemReader, null có ý nghĩa cụ thể là hết dữ liệu. Với ItemProcessor, null có nghĩa item được filter khỏi output. Hai giá trị null này không thay thế exception khi có lỗi.

## 3. Phân biệt exception, EOF, filter và business status

Một số kết quả của component có vẻ giống nhau nhưng semantics rất khác:

| Kết quả | Ý nghĩa | Framework xử lý |
|---|---|---|
| ItemReader trả null | Không còn item | Kết thúc phần đọc |
| ItemProcessor trả null | Item bị filter theo chủ đích | Không chuyển item đó tới writer |
| Component ném exception | Thao tác thất bại | Áp dụng rollback/retry/skip/fail policy |
| Tasklet trả RepeatStatus.FINISHED | Tasklet đã hoàn tất | Step tiếp tục lifecycle hoàn tất |
| Step trả ExitStatus | Kết quả/nhãn trạng thái của step | Job flow có thể dùng để chọn nhánh |
| Job/Step BatchStatus | Trạng thái thực thi trong metadata | Phản ánh COMPLETED, FAILED, STOPPED... |

Không ném exception chỉ để báo rằng không có dữ liệu. Không trả null từ processor chỉ để che giấu lỗi dữ liệu. Không dùng exception cho một kết quả nghiệp vụ bình thường nếu có thể biểu diễn bằng output hoặc status rõ ràng.

Nếu cần phân biệt “không tìm thấy” là kết quả hợp lệ với “không tìm thấy” là lỗi, hãy định nghĩa contract theo nghiệp vụ. Ví dụ processor có thể trả null để filter một item không cần xuất, trong khi reader không tìm thấy nguồn bắt buộc phải ném SourceNotFoundException.

## 4. Thiết kế exception theo nhóm nguyên nhân

Một custom component thường cần ít nhất các nhóm:

1. **Lỗi dữ liệu:** record sai định dạng, thiếu trường bắt buộc, giá trị nằm ngoài miền cho phép.
2. **Lỗi tạm thời:** timeout, throttling, deadlock, kết nối bị ngắt trong thời gian ngắn.
3. **Lỗi cấu hình:** endpoint, credential, schema, tên bảng hoặc tham số job không hợp lệ.
4. **Lỗi tài nguyên:** file không tồn tại, quyền truy cập, disk full, resource bị đóng.
5. **Lỗi lập trình:** invariant bị vi phạm, trạng thái nội bộ không hợp lệ, null ngoài dự kiến.

Không phải mọi nhóm cần một class riêng. Tuy nhiên, những loại exception mà retry/skip policy cần phân biệt nên có type rõ ràng. Tránh một exception tổng quát như BatchProcessingException cho mọi trường hợp nếu caller không thể biết cách xử lý.

Một hierarchy đơn giản:

~~~java
public abstract class OrderImportException extends Exception {

    protected OrderImportException(String message) {
        super(message);
    }

    protected OrderImportException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class InvalidOrderException extends OrderImportException {

    public InvalidOrderException(String message) {
        super(message);
    }
}

public class TemporarySourceException extends OrderImportException {

    public TemporarySourceException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class SourceConfigurationException extends OrderImportException {

    public SourceConfigurationException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Ví dụ trên dùng checked exception để thể hiện lỗi thuộc contract của component. Ứng dụng cũng có thể dùng RuntimeException cho lỗi không mong muốn hoặc abstraction khác. Điều quan trọng là exception type phải có ý nghĩa và policy phân loại phải nhất quán.

## 5. Giữ nguyên nguyên nhân gốc khi chuyển exception

Custom component thường gọi thư viện ngoài như HTTP client, JDBC driver, parser hoặc filesystem API. Có thể cần chuyển exception kỹ thuật thành exception của domain để step policy không phụ thuộc trực tiếp vào thư viện.

Ví dụ:

~~~java
try {
    return partnerClient.fetchNextPage(pageToken);
} catch (SocketTimeoutException ex) {
    throw new TemporarySourceException(
            "Timed out while fetching the next order page", ex);
} catch (AuthenticationException ex) {
    throw new SourceConfigurationException(
            "Partner authentication failed", ex);
}
~~~

Cause gốc được truyền vào constructor để giữ stack trace và chi tiết kỹ thuật. Nếu chỉ tạo exception mới bằng message, thông tin về timeout, HTTP response hoặc driver error có thể bị mất.

Không bắt Exception rồi ném lại một exception chung không có cause. Cũng không bắt rồi chỉ log và tiếp tục như thể thao tác thành công. Nếu component không thể xử lý lỗi, hãy để lỗi truyền lên hoặc chuyển đổi có chủ đích.

## 6. Đừng dùng exception chung cho lỗi tạm thời và lỗi vĩnh viễn

Retry policy thường phân loại theo exception type. Nếu mọi lỗi API đều được bọc thành PartnerException, framework không thể dễ dàng phân biệt:

- HTTP 429 hoặc throttling có thể retry sau thời gian chờ.
- HTTP 503 có thể tạm thời.
- HTTP 400 do payload sai thường không tự hết khi retry.
- HTTP 401/403 thường cần sửa credential/quyền.
- HTTP 404 có thể là kết quả nghiệp vụ hoặc cấu hình endpoint sai.

Hãy phân loại theo semantics của hệ thống đối tác, không chỉ theo mã HTTP một cách máy móc. Ví dụ:

~~~java
if (response.statusCode() == 429 || response.statusCode() == 503) {
    throw new TemporarySourceException(
            "Partner service is temporarily unavailable", null);
}

if (response.statusCode() == 401 || response.statusCode() == 403) {
    throw new SourceConfigurationException(
            "Partner credentials or permissions are invalid", null);
}

if (response.statusCode() >= 400) {
    throw new InvalidOrderException(
            "Partner rejected the requested order data");
}
~~~

Đây chỉ là minh họa; cần giữ response/cause hữu ích và xử lý đúng contract cụ thể. Không retry vô hạn lỗi xác thực hoặc payload sai.

## 7. Exception contract của ItemReader

ItemReader có contract đơn giản nhưng quan trọng:

- Trả về một item khi đọc thành công.
- Trả null khi đã hết dữ liệu.
- Ném exception nếu không thể tiếp tục đọc theo contract.

Ví dụ custom reader:

~~~java
public class ApiOrderReader implements ItemStreamReader<OrderInput> {

    @Override
    public OrderInput read() throws Exception {
        try {
            return fetchNextOrder();
        } catch (SocketTimeoutException ex) {
            throw new TemporarySourceException(
                    "Order source timed out", ex);
        }
    }

    // open, update, close và fetchNextOrder được triển khai riêng.
}
~~~

Không trả null khi API timeout. Spring Batch sẽ hiểu null là hết dữ liệu và có thể hoàn tất step dù nguồn thực tế chưa đọc xong.

Không trả một item rỗng khi payload không parse được. Làm vậy có thể đưa dữ liệu giả vào processor/writer và che giấu lỗi nguồn.

Reader nên xác định rõ lỗi xảy ra trước hay sau khi nguồn đã tiêu thụ item. Nếu nguồn non-transactional đã consume record rồi reader ném exception trước khi trả item, framework không có item để buffer. Cần thiết kế replay, acknowledgement hoặc staging phù hợp.

## 8. Exception contract của ItemProcessor

Processor nhận một item và trả về output hoặc null để filter. Nếu không thể xử lý item, processor có thể ném exception:

~~~java
public class OrderProcessor
        implements ItemProcessor<OrderInput, OrderOutput> {

    @Override
    public OrderOutput process(OrderInput input) throws InvalidOrderException {
        if (input.getOrderId() == null) {
            throw new InvalidOrderException("orderId is required");
        }

        if (input.getAmount() == null || input.getAmount().signum() < 0) {
            throw new InvalidOrderException("amount must be non-negative");
        }

        return new OrderOutput(input.getOrderId(), input.getAmount());
    }
}
~~~

Ở đây, dữ liệu không hợp lệ được báo bằng exception để step có thể áp dụng skip/fail policy. Nếu item hợp lệ nhưng không cần ghi, processor có thể trả null theo quy tắc filter.

Không dùng null để biểu diễn “processor gặp lỗi nhưng muốn job tiếp tục”. Việc đó làm item biến mất khỏi pipeline mà không có skip count hoặc skip listener tương ứng.

## 9. Exception contract của ItemWriter

ItemWriter nhận một chunk và chịu trách nhiệm ghi các item theo contract. Nếu không thể ghi, writer ném exception:

~~~java
public class OrderAuditWriter implements ItemWriter<OrderOutput> {

    @Override
    public void write(Chunk<? extends OrderOutput> chunk) throws Exception {
        for (OrderOutput item : chunk) {
            writeOne(item);
        }
    }
}
~~~

Với writer ghi database trong cùng transaction manager/datasource, exception thường khiến chunk rollback. Với writer ghi file hoặc gọi API, cần hiểu cơ chế transaction của resource cụ thể; một side effect đã xảy ra bên ngoài transaction không tự được hoàn tác.

Writer không nên nuốt exception rồi trả về bình thường khi chỉ ghi được một phần chunk. Nếu caller nghĩ chunk đã ghi thành công, checkpoint có thể tiến lên và dữ liệu bị mất. Nếu writer cho phép partial success, contract phải thể hiện rõ item nào thành công, item nào thất bại và cách restart/đối soát.

Với writer chuẩn của Spring Batch, một exception từ write thường khiến chunk thất bại; framework có thể retry hoặc skip theo cấu hình. Writer tùy chỉnh cần bảo đảm hành vi tương thích với transaction và retry semantics.

## 10. Exception contract của Tasklet

Tasklet thực hiện một đơn vị công việc và trả RepeatStatus để cho biết đã hoàn tất hay cần lặp tiếp. Exception biểu thị lần thực thi thất bại:

~~~java
public class ValidateInputTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) throws Exception {

        if (!inputIsValid()) {
            throw new InvalidInputException("Input validation failed");
        }

        return RepeatStatus.FINISHED;
    }
}
~~~

Không trả RepeatStatus.FINISHED khi validation thất bại. Cũng không trả CONTINUABLE để yêu cầu retry một lỗi không có điều kiện kết thúc. Nếu cần polling một trạng thái bên ngoài, xác định timeout, giới hạn số lần lặp và khoảng nghỉ rõ ràng.

Tasklet có thể chạy trong transaction theo cấu hình step. Exception từ execute thường làm lần thực thi hiện tại thất bại và transaction rollback theo semantics của transaction manager.

## 11. Exception trong ItemStream lifecycle

Reader/writer có resource hoặc state thường triển khai ItemStream. Các method lifecycle có contract riêng:

- open(ExecutionContext): mở resource và khôi phục state.
- update(ExecutionContext): cập nhật state để framework lưu checkpoint.
- close(): đóng resource và giải phóng tài nguyên.

Các method này dùng ItemStreamException để báo lỗi lifecycle. Ví dụ:

~~~java
@Override
public void open(ExecutionContext context) throws ItemStreamException {
    try {
        openInput();
        restorePosition(context);
    } catch (IOException ex) {
        throw new ItemStreamException("Cannot open input resource", ex);
    }
}
~~~

Lỗi open thường xảy ra trước khi chunk processing bắt đầu. Lỗi update có thể ảnh hưởng việc lưu checkpoint. Lỗi close có thể khiến step không hoàn tất bình thường dù phần xử lý item đã chạy xong.

Không bỏ qua lỗi close nếu resource chưa được giải phóng hoặc dữ liệu chưa được flush. Với file output, close có thể là thời điểm hoàn tất cấu trúc tài liệu; nếu close thất bại, không publish artifact đó như một output hợp lệ.

## 12. Listener callback cũng có contract lỗi

Listener cung cấp hook để quan sát hoặc thực hiện hành động quanh read/process/write/chunk/step/job. Một số callback có method signature không khai báo checked exception. Nếu listener ném unchecked exception, nó vẫn có thể làm gián đoạn execution.

Các ví dụ:

- ItemReadListener.onReadError(Exception ex).
- ItemProcessListener.onProcessError(item, Exception ex).
- ItemWriteListener.onWriteError(Exception ex).
- SkipListener ghi nhận item bị skip.
- StepExecutionListener.afterStep(...) có thể trả về ExitStatus.

Listener nên ưu tiên quan sát, audit hoặc cập nhật thông tin phù hợp. Tránh dùng listener để thay thế reader/writer hoặc thực hiện side effect không idempotent. Nếu audit bắt buộc phải ghi bền vững, cần transaction và failure policy rõ ràng.

Đặc biệt, listener không nên bắt exception gốc rồi che giấu nó. Nếu callback audit gặp lỗi, quyết định rõ lỗi audit có được phép làm job fail hay chỉ log/đưa vào kênh phụ. Đây là một phần của contract vận hành.

## 13. Exception classification: retry, skip hay fail

Spring Batch không tự biết mọi exception có thể xử lý theo cách nào. Step cần policy phù hợp:

| Phân loại | Ý nghĩa | Ví dụ |
|---|---|---|
| Retryable | Có khả năng thành công nếu thử lại | Timeout, deadlock, throttling |
| Skippable | Có thể bỏ item lỗi mà vẫn bảo đảm tính đúng đắn nghiệp vụ | Một record độc lập có dữ liệu không hợp lệ |
| Fatal/non-retryable | Thử lại không giúp ích hoặc tiếp tục sẽ làm sai dữ liệu | Sai cấu hình, schema không tương thích, credential lỗi |
| Unknown | Chưa được phân loại | Thường nên fail an toàn cho tới khi có quy tắc rõ |

Một exception có thể retryable nhưng không skippable. Ví dụ database deadlock nên retry transaction; nếu hết retry limit, thường không nên bỏ qua chunk như thể item đó là record xấu.

Một exception có thể skippable nhưng không retryable. Ví dụ InvalidOrderException có thể được ghi vào error report và bỏ qua item theo chính sách nghiệp vụ.

Không cấu hình retry và skip một cách rộng rãi cho Exception.class nếu chưa hiểu các loại lỗi bên trong. Chính sách quá rộng có thể khiến lỗi cấu hình bị retry nhiều lần hoặc dữ liệu quan trọng bị bỏ qua.

## 14. Cấu hình retry cho custom exception

Ví dụ cấu hình retry cho lỗi nguồn tạm thời:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, OrderOutput>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .retry(TemporarySourceException.class)
        .retryLimit(3)
        .build();
~~~

retryLimit(3) giới hạn số lần retry theo semantics của builder/version đang dùng; cần đọc rõ cách framework tính lần thử ban đầu và các lần retry trong phiên bản dự án. Với lỗi có backoff, có thể cấu hình policy/backoff tương ứng để tránh gọi hệ thống ngoài liên tục.

Retry chỉ phù hợp khi thao tác có thể thực hiện lại an toàn. Nếu API đã tạo side effect nhưng response bị timeout, retry có thể tạo tác dụng phụ trùng. Dùng idempotency key hoặc truy vấn trạng thái trước khi thử lại.

## 15. Cấu hình skip cho custom exception

Ví dụ bỏ qua item có dữ liệu nghiệp vụ không hợp lệ:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, OrderOutput>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skipLimit(50)
        .build();
~~~

Skip limit giới hạn số item lỗi được bỏ qua theo policy của step. Khi vượt giới hạn, step thất bại.

Chỉ skip nếu item có thể được loại bỏ mà không phá vỡ invariant nghiệp vụ. Ví dụ một order độc lập có amount âm có thể được đưa vào error report; nhưng một record định nghĩa tỷ giá hoặc số dư mở đầu có thể ảnh hưởng mọi record sau và không nên skip.

Nếu cần audit item bị skip, dùng SkipListener để ghi business key, loại lỗi và lý do. Tránh ghi toàn bộ payload nhạy cảm vào log.

## 16. Retry và skip là hai quyết định riêng

Một số lỗi cần retry trước; nếu vẫn không thành công, step có thể thất bại. Một số lỗi dữ liệu có thể skip ngay. Không nên coi skip là retry cuối cùng cho mọi lỗi.

Ví dụ:

| Exception | Retry | Skip | Lý do |
|---|---|---|---|
| TemporarySourceException | Có, giới hạn | Thường không | Nguồn tạm thời có thể phục hồi |
| InvalidOrderException | Thường không | Có nếu nghiệp vụ cho phép | Dữ liệu record không thay đổi khi retry |
| SourceConfigurationException | Không | Không | Cần sửa cấu hình/credential |
| DeadlockLoserDataAccessException | Có | Thường không | Retry transaction có thể thành công |
| DuplicateBusinessKeyException | Tùy semantics | Tùy policy | Có thể là duplicate hợp lệ hoặc lỗi dữ liệu |

Nếu một exception được cấu hình cả retry và skip, cần hiểu thứ tự policy và cách framework phân loại trong phiên bản đang dùng. Tốt nhất là tránh overlap không cần thiết và viết test cho từng exception type.

## 17. noRollback không đồng nghĩa với skip

Fault-tolerant step có thể cấu hình exception không làm rollback transaction bằng noRollback(...). Đây là một trục quyết định khác với retry/skip:

- Retry quyết định có thử lại thao tác hay không.
- Skip quyết định có bỏ item lỗi và tiếp tục hay không.
- noRollback quyết định exception có làm transaction hiện tại rollback hay không.

Ví dụ khái quát:

~~~java
.faultTolerant()
.noRollback(NonCriticalValidationException.class)
~~~

Chỉ dùng noRollback khi exception thực sự không yêu cầu hoàn tác các thay đổi trong transaction. Nếu writer đã ghi một phần dữ liệu rồi ném exception, giữ transaction có thể để lại trạng thái không nhất quán.

noRollback không tự động biến exception thành kết quả thành công, không tự skip item và không bảo đảm step tiếp tục. Hãy kiểm tra cách exception được xử lý trong reader/processor/writer và viết test cho transaction behavior cụ thể.

## 18. Rollback và custom writer có side effect

Một custom writer có thể thực hiện nhiều thao tác cho mỗi chunk:

1. Ghi một số item vào database.
2. Gọi API bên ngoài.
3. Ghi file audit.
4. Ném exception khi thao tác tiếp theo thất bại.

Nếu tất cả thao tác không nằm trong cùng một transaction, rollback database không thể hoàn tác API hoặc file đã ghi. Khi framework retry chunk, side effect có thể bị thực hiện lần nữa.

Thiết kế an toàn hơn:

- Ưu tiên ghi các thay đổi database trong transaction của chunk.
- Dùng transactional outbox để phát sự kiện sau commit.
- Dùng idempotency key cho API.
- Ghi file vào staging và publish sau khi job/step hoàn tất.
- Dùng unique business key để chống duplicate.
- Có cơ chế reconciliation cho trạng thái không xác định sau timeout/crash.

Exception contract phải nói rõ writer có thể đã tạo side effect nào trước khi ném lỗi. Nếu không thể bảo đảm atomicity, caller cần biết cách xử lý retry và đối soát.

## 19. Không nuốt exception trong custom component

Một lỗi thường gặp:

~~~java
try {
    return client.fetch();
} catch (Exception ex) {
    log.error("Fetch failed", ex);
    return null;
}
~~~

Trong reader, null được hiểu là hết dữ liệu. Job có thể hoàn tất với output thiếu mà không có dấu hiệu failure.

Một lỗi khác:

~~~java
try {
    repository.save(item);
} catch (Exception ex) {
    log.error("Save failed", ex);
}
~~~

Writer trả về bình thường dù item chưa được ghi. Framework có thể commit checkpoint và không bao giờ thử lại item đó.

Hãy truyền lỗi lên:

~~~java
try {
    repository.save(item);
} catch (DataAccessException ex) {
    throw new OrderWriteException(
            "Cannot persist order " + item.getOrderId(), ex);
}
~~~

Chỉ bắt exception khi component có thể xử lý hoàn toàn hoặc cần chuyển đổi sang một contract rõ ràng. Nếu đã log ở tầng thấp và tầng trên cũng log lại, có thể tạo log duplicate; chọn một tầng chịu trách nhiệm ghi stack trace đầy đủ.

## 20. Không dùng catch-all để biến lỗi thành skip

Đoạn code sau nguy hiểm:

~~~java
try {
    return transform(item);
} catch (Exception ex) {
    return null;
}
~~~

Nó biến mọi lỗi thành filter, bao gồm lỗi lập trình, lỗi cấu hình và lỗi dữ liệu. Không có skip count, không có SkipListener và không có thông tin cho người vận hành.

Nếu chỉ một nhóm lỗi dữ liệu được phép bỏ qua, hãy ném exception cụ thể và cấu hình skip policy cho đúng loại. Nếu item không cần xử lý theo business rule, trả null có chủ đích mà không bắt exception.

## 21. Exception trong open, update và close

Custom ItemStream cần có contract rõ cho các giai đoạn ngoài read/write:

- open: nếu resource không thể mở hoặc checkpoint không thể khôi phục, ném ItemStreamException.
- update: nếu không thể lưu state cần thiết, báo lỗi để framework không coi checkpoint đã được cập nhật thành công.
- close: nếu flush/close resource thất bại, báo lỗi; không publish output chưa hoàn tất.

Ví dụ:

~~~java
@Override
public void update(ExecutionContext context) throws ItemStreamException {
    try {
        context.putLong("lastOrderId", lastOrderId);
    } catch (RuntimeException ex) {
        throw new ItemStreamException("Cannot update reader checkpoint", ex);
    }
}
~~~

ExecutionContext thường là object key/value mà framework sẽ persist qua JobRepository. Không cần bắt mọi RuntimeException từ put method nếu không thể xử lý; ví dụ trên chỉ minh họa việc chuyển lỗi theo lifecycle contract.

Nếu update thất bại, không được tự giả định step có thể restart chính xác. Checkpoint cũ có thể khiến reader đọc lại dữ liệu; output phải idempotent để xử lý tình huống đó.

## 22. Listener và lỗi audit

SkipListener thường được dùng để ghi nhận item bị skip. Ví dụ:

~~~java
public class OrderSkipListener
        implements SkipListener<OrderInput, OrderOutput> {

    @Override
    public void onSkipInRead(Throwable t) {
        log.warn("Order input could not be read: {}", t.toString());
    }

    @Override
    public void onSkipInProcess(OrderInput item, Throwable t) {
        log.warn("Skipping order {}: {}",
                item.getOrderId(), t.toString());
    }

    @Override
    public void onSkipInWrite(OrderOutput item, Throwable t) {
        log.warn("Skipping order {} during write: {}",
                item.getOrderId(), t.toString());
    }
}
~~~

Các callback thể hiện lỗi xảy ra ở giai đoạn nào. Read skip không có item đã được đọc thành công, nên callback nhận throwable; process/write skip có item tương ứng.

Nếu listener ghi error table, cần xác định transaction của thao tác audit và đảm bảo ghi nhận không bị mất khi chunk rollback. Listener không nên gửi email hoặc gọi API không idempotent mỗi lần callback nếu callback có thể được gọi lại trong những tình huống retry.

## 23. Không nhầm exception với ExitStatus

Exception báo một thao tác thất bại và tham gia xử lý rollback/retry/skip. ExitStatus biểu diễn kết quả của step và có thể dùng để điều khiển job flow.

Ví dụ, một step kiểm tra có thể hoàn thành về mặt kỹ thuật nhưng trả custom exit code NO_DATA để job đi sang nhánh khác. Đây không nhất thiết là exception:

~~~java
@Override
public ExitStatus afterStep(StepExecution stepExecution) {
    if (stepExecution.getReadCount() == 0) {
        return new ExitStatus("NO_DATA");
    }
    return stepExecution.getExitStatus();
}
~~~

Sau đó job flow có thể dùng on("NO_DATA") để chọn nhánh phù hợp. Không ném exception chỉ để biểu diễn một kết quả nghiệp vụ hợp lệ như “không có dữ liệu trong kỳ”.

Ngược lại, nếu không thể đọc nguồn do database unavailable, đó là lỗi thực thi và cần exception để framework áp dụng failure policy. ExitStatus không thay thế exception classification.

## 24. Không nhầm BatchStatus với exception type

BatchStatus phản ánh trạng thái thực thi như STARTING, STARTED, COMPLETED, FAILED hoặc STOPPED. Nó không phải class exception và không mô tả chi tiết nguyên nhân lỗi.

Một job có thể FAILED vì:

- Reader ném exception.
- Processor ném exception không được skip.
- Writer ném exception.
- Listener hoặc lifecycle resource thất bại.
- Step bị dừng theo một điều kiện vận hành.

Muốn biết nguyên nhân, cần xem failure exceptions của StepExecution/JobExecution và log liên quan. Không chỉ kiểm tra BatchStatus rồi suy đoán lỗi.

## 25. Phân loại lỗi đọc, xử lý và ghi

Vị trí lỗi ảnh hưởng cách framework có thể khôi phục:

| Giai đoạn | Ví dụ | Điểm cần quan tâm |
|---|---|---|
| Reader | JSON parse lỗi, API timeout, file permission | Item có được trả về chưa? Nguồn đã consume chưa? |
| Processor | Validation fail, mapping rule sai | Item đã đọc có thể được giữ/buffer để retry/skip không? |
| Writer | Unique constraint, database timeout, file I/O | Có side effect một phần không? Transaction có rollback được không? |
| Stream open | File không tồn tại, cursor không mở được | Step chưa bắt đầu xử lý item |
| Stream update | Không lưu được checkpoint | Restart có thể không chính xác |
| Stream close | Flush/close thất bại | Output chưa chắc hoàn chỉnh |

Ví dụ reader đã lấy một message từ nguồn non-transactional rồi ném lỗi trước khi return item. Spring Batch chưa có item để buffer. Ngược lại, processor ném lỗi sau khi reader đã trả item; framework có thể dùng item đã đọc trong cơ chế fault tolerance phù hợp.

Khi thiết kế custom component, hãy xác định chính xác thời điểm side effect xảy ra và thời điểm item được coi là đã chuyển giao cho framework.

## 26. SkipPolicy tùy chỉnh

Nếu quy tắc skip phức tạp hơn một danh sách class, có thể implement SkipPolicy để quyết định một exception có thể skip hay không dựa trên exception và số lần skip đã dùng.

Ví dụ khung:

~~~java
public class OrderSkipPolicy implements SkipPolicy {

    private final long skipLimit;

    public OrderSkipPolicy(long skipLimit) {
        this.skipLimit = skipLimit;
    }

    @Override
    public boolean shouldSkip(Throwable throwable, long skipCount)
            throws SkipLimitExceededException {

        if (throwable instanceof InvalidOrderException
                && skipCount < skipLimit) {
            return true;
        }

        return false;
    }
}
~~~

Policy phải thận trọng với cause chain: lỗi có thể được bọc trong exception khác. Nếu cần tìm cause, tránh duyệt vòng lặp vô hạn khi exception chain bị tạo sai. Cũng không skip mọi exception chỉ vì root cause thuộc một class chung nếu context nghiệp vụ không cho phép.

Custom SkipPolicy nên có test cho từng nhánh: loại lỗi được skip, loại lỗi không được skip và trường hợp vượt limit. Nếu chỉ cần class-based rule, builder skip(...) đơn giản và dễ hiểu hơn.

## 27. RetryPolicy tùy chỉnh và backoff

Khi số lần retry hoặc điều kiện retry phụ thuộc vào trạng thái, có thể dùng retry policy phù hợp với Spring Retry/Spring Batch version. Với trường hợp thông thường, builder retry(...), retryLimit(...) và backoff policy đủ rõ.

Retry cần có:

- Giới hạn số lần thử.
- Khoảng nghỉ hoặc exponential backoff khi nguồn có rate limit.
- Phân loại lỗi tạm thời.
- Timeout tổng thể để job không treo vô hạn.
- Idempotency cho side effect.
- Log/metric số lần retry và exception cuối cùng.

Không retry lỗi do cấu hình sai hoặc dữ liệu bất biến. Không đặt backoff quá dài mà không tính đến SLA và thời gian chạy của job.

## 28. Exception contract cho lỗi duplicate

Duplicate có thể mang nhiều ý nghĩa:

- Item đã được ghi trong một lần chạy trước và retry đang gửi lại.
- Nguồn chứa hai record có cùng business key.
- Consumer đã xử lý message nhưng broker redeliver.
- Writer chạy lại sau crash window.

Không nên dùng một DuplicateException chung rồi luôn skip. Nếu duplicate là kết quả idempotent hợp lệ, writer có thể dùng upsert/unique key và coi thao tác đã hoàn thành. Nếu hai record nguồn có cùng key nhưng payload khác nhau, đó có thể là lỗi dữ liệu cần báo.

Exception contract nên phân biệt:

- DuplicateSamePayloadException: cùng key và cùng nội dung; có thể coi là đã xử lý nếu policy cho phép.
- ConflictingDuplicateException: cùng key nhưng nội dung khác; thường cần fail hoặc đưa vào reconciliation.
- DuplicateDeliveryException: message được giao lại; consumer dedup theo event ID.

Việc phân loại này giúp tránh bỏ qua một xung đột dữ liệu thật chỉ vì nó có vẻ giống duplicate retry.

## 29. Exception message và dữ liệu nhạy cảm

Exception message cần đủ ngữ cảnh để điều tra nhưng không nên chứa bí mật hoặc toàn bộ payload:

- Không log password, token, API key hoặc authorization header.
- Không đưa dữ liệu cá nhân đầy đủ vào message nếu business key là đủ.
- Tránh log toàn bộ JSON record khi chỉ cần order ID và field lỗi.
- Giữ correlation ID, source identifier và item key phù hợp.
- Giữ cause để có stack trace kỹ thuật.

Ví dụ message tốt:

~~~text
Cannot map amount for orderId=1001, source=orders-2026-11-15.json
~~~

Ví dụ message không nên dùng:

~~~text
Failed for payload: {full customer record including credentials and personal data}
~~~

Exception contract nên quy định thông tin được phép ghi log, đặc biệt khi component xử lý dữ liệu từ hệ thống bên ngoài.

## 30. Exception và retry trong multi-threaded step

Trong step chạy song song, nhiều item có thể phát sinh exception đồng thời. Cần bảo đảm:

- Custom exception là immutable hoặc không chia sẻ mutable context giữa thread.
- Reader/processor/writer không lưu current item trong field singleton dùng chung.
- Log có business key/correlation ID để xác định thread và item.
- Retry policy không tạo side effect duplicate.
- Skip listener hoặc audit writer thread-safe nếu được gọi đồng thời.
- Exception không làm lộ dữ liệu item của thread khác.

Không dùng một biến toàn cục để ghi exception gần nhất. Khi nhiều worker lỗi, thông tin có thể bị ghi đè và không còn tương ứng với item thực tế.

## 31. Exception contract khi dùng parallel flow hoặc partition

Trong parallel flow, lỗi của một flow có thể ảnh hưởng trạng thái job tổng thể và các flow khác. Cần xác định:

- Flow nào là bắt buộc?
- Một partition thất bại thì toàn bộ step/job có phải thất bại không?
- Có được retry riêng partition không?
- Output của partition thành công có được giữ làm staging không?
- Khi restart, partition nào chạy lại và checkpoint nào được khôi phục?

Không biến exception của worker thành status thành công chỉ để flow tổng thể tiếp tục. Nếu partial completion là kết quả nghiệp vụ hợp lệ, hãy mô hình hóa nó rõ ràng bằng status/manifest và có bước tổng hợp kiểm tra completeness.

## 32. Test exception contract của custom component

Mỗi custom component nên có test cho cả đường thành công và các loại lỗi được công bố trong contract.

Với reader:

- Trả item khi nguồn có dữ liệu.
- Trả null khi EOF.
- Timeout được chuyển thành TemporarySourceException và giữ cause.
- Payload sai được chuyển thành InvalidResponseException.
- Không trả null khi lỗi nguồn.
- Nếu nguồn consume trước khi lỗi, test xác nhận cơ chế replay/ack phù hợp.

Với processor:

- Item hợp lệ tạo output đúng.
- Item bị filter trả null.
- Item dữ liệu sai ném đúng exception type.
- Không nuốt exception hoặc trả null khi có lỗi.

Với writer:

- Chunk hợp lệ được ghi đầy đủ.
- Lỗi database được truyền lên với cause.
- Không báo thành công khi chỉ ghi một phần.
- Retry không tạo side effect duplicate.
- Rollback giữ trạng thái output theo contract.

Với ItemStream:

- open khôi phục checkpoint.
- open/update/close lỗi được bọc thành ItemStreamException với cause.
- Resource được giải phóng khi failure.

## 33. Unit test cho exception type và cause

Ví dụ test reader chuyển timeout:

~~~java
@Test
void wrapsTimeoutAsTemporarySourceException() {
    when(client.fetchNextPage()).thenThrow(
            new SocketTimeoutException("read timed out"));

    TemporarySourceException exception = assertThrows(
            TemporarySourceException.class,
            reader::read);

    assertInstanceOf(
            SocketTimeoutException.class,
            exception.getCause());
}
~~~

Test xác nhận cả loại exception public mà caller nhìn thấy và cause kỹ thuật được giữ lại. Không chỉ assert rằng có exception, vì khi type sai, retry policy có thể không hoạt động như mong đợi.

Với processor, kiểm tra InvalidOrderException chỉ được ném cho điều kiện dữ liệu được quy định. Với writer, kiểm tra exception không bị nuốt và item key được đưa vào message ở mức an toàn.

## 34. Integration test retry và skip

Unit test exception không chứng minh step builder đã cấu hình policy đúng. Cần integration test cho hành vi framework:

1. Tạo reader/processor/writer test double có thể ném exception theo item hoặc số lần gọi.
2. Cấu hình retry cho TemporarySourceException với limit nhỏ.
3. Cấu hình skip cho InvalidOrderException.
4. Launch job.
5. Xác nhận lỗi tạm thời được thử lại và cuối cùng thành công hoặc fail khi hết limit.
6. Xác nhận item invalid được skip đúng số lượng và listener nhận callback.
7. Xác nhận lỗi cấu hình không bị retry/skip ngoài ý muốn.
8. Kiểm tra output cuối và StepExecution metrics.

Ví dụ một reader test double:

~~~java
public class RetryOnceReader implements ItemReader<String> {

    private int attempts;

    @Override
    public String read() throws Exception {
        attempts++;
        if (attempts == 1) {
            throw new TemporarySourceException(
                    "Temporary failure", new IOException("connection reset"));
        }
        if (attempts == 2) {
            return "order-1";
        }
        return null;
    }
}
~~~

Đây là test double đơn giản để mô phỏng lỗi trước khi trả item. Với reader có checkpoint hoặc nguồn transactional, cần test semantics cụ thể của nguồn và không chỉ dựa vào counter trong memory.

## 35. Test transaction rollback và side effect

Một integration test quan trọng là tạo lỗi sau khi writer đã thực hiện một phần thao tác. Xác nhận:

- Database transaction rollback những thay đổi thuộc transaction.
- Chunk được retry/skip/fail theo cấu hình.
- Writer không để lại side effect ngoài transaction mà không có idempotency.
- Error report phản ánh item thực sự bị skip.
- Checkpoint không tiến qua item chưa được xử lý thành công.

Với external API hoặc message broker, dùng fake server/broker test để mô phỏng timeout sau khi server đã nhận request nhưng trước khi client nhận response. Test phải xác nhận idempotency key ngăn side effect bị thực hiện hai lần.

## 36. Kiểm thử ItemStream lifecycle

Với custom reader/writer có state, test riêng từng lifecycle:

- open với ExecutionContext mới.
- open với checkpoint đã lưu.
- update sau khi đọc/ghi một số item.
- restart từ context đã lưu.
- close giải phóng resource.
- open/update/close ném ItemStreamException khi lỗi tương ứng.

Ví dụ:

~~~java
ExecutionContext context = new ExecutionContext();
reader.open(context);

reader.read();
reader.update(context);
reader.close();

CustomReader restarted = new CustomReader(source);
restarted.open(context);
// Xác nhận item tiếp theo bắt đầu sau checkpoint.
restarted.close();
~~~

Đây là khung test; cần xác định reader lưu checkpoint theo offset, item count, page token hay business key. Không chỉ assert key có trong context; phải xác nhận reader khôi phục đúng item tiếp theo.

## 37. Không biến lỗi kỹ thuật thành kết quả thành công trong listener

Một số listener trả về ExitStatus hoặc được gọi sau khi step xử lý xong. Không nên sửa status thành COMPLETED nếu step đã thất bại chỉ để job flow tiếp tục mà không có quy tắc nghiệp vụ rõ.

Nếu lỗi là một kết quả nghiệp vụ có thể chấp nhận, hãy:

- Mô hình hóa status riêng như NO_DATA hoặc VALIDATION_WARNING.
- Ghi rõ dữ liệu nào được xử lý và dữ liệu nào chưa.
- Dùng transition rõ trong job flow.
- Kiểm tra downstream không coi partial output là kết quả hoàn chỉnh.

Nếu lỗi là kỹ thuật và làm dữ liệu không đáng tin cậy, giữ trạng thái failure để operator có thể xử lý.

## 38. Exception contract và observability

Một exception type tốt cần hỗ trợ vận hành:

- Tên class thể hiện nhóm nguyên nhân.
- Message có business key/source identifier phù hợp.
- Cause giữ stack trace gốc.
- Log có job name, job execution ID, step name và correlation ID.
- Metric phân biệt retry, skip và failure.
- Error report lưu item key và error code, không nhất thiết lưu payload đầy đủ.
- Alert chỉ phát cho lỗi cần can thiệp, tránh gửi alert cho mọi lần retry tạm thời.

Nếu mọi exception đều chỉ log “Batch failed”, việc phân tích lỗi production sẽ tốn thời gian. Nếu log toàn bộ payload, hệ thống có thể lộ dữ liệu nhạy cảm. Hãy cân bằng giữa khả năng truy vết và giới hạn dữ liệu.

## 39. Các lỗi thiết kế thường gặp

| Tình huống | Nguyên nhân | Cách xử lý |
|---|---|---|
| Reader kết thúc sớm khi API lỗi | Bắt exception rồi trả null | Chỉ trả null khi EOF; ném exception khi đọc thất bại |
| Processor âm thầm mất item | Bắt mọi lỗi rồi trả null | Dùng null chỉ cho filter có chủ đích; ném lỗi dữ liệu |
| Writer commit checkpoint dù ghi thất bại | Nuốt exception và trả bình thường | Truyền exception lên để framework xử lý |
| Retry không chạy | Exception bị bọc thành type khác policy không nhận diện | Giữ cause và phân loại đúng exception type |
| Lỗi vĩnh viễn bị retry nhiều lần | Retry quá rộng trên Exception.class | Chỉ retry loại lỗi tạm thời |
| Dữ liệu xấu bị retry mãi | Lỗi validation không được phân loại skip/fail | Dùng exception nghiệp vụ và policy rõ |
| Item bị bỏ qua không có audit | Không đăng ký SkipListener | Ghi nhận business key và nguyên nhân skip |
| Duplicate side effect sau retry | Writer gọi API ngoài transaction | Idempotency key, outbox hoặc reconciliation |
| Rollback không hoàn tác file/API | Resource ngoài transaction | Staging, publish hoặc cơ chế bù trừ |
| Lỗi checkpoint bị che | update bắt exception rồi bỏ qua | Ném ItemStreamException với cause |
| Job báo COMPLETED dù lỗi | Listener đổi status không đúng semantics | Dùng exception cho lỗi thực thi và ExitStatus cho nhánh nghiệp vụ |
| Log chứa dữ liệu nhạy cảm | Đưa toàn bộ payload vào message | Log business key/correlation ID và làm sạch dữ liệu |
| Skip quá nhiều record | Skip policy quá rộng | Giới hạn skip và chỉ skip lỗi được nghiệp vụ cho phép |
| Test chỉ xác nhận có exception | Không kiểm tra type/cause/policy | Assert exception contract và hành vi step |

## 40. Quy trình thiết kế exception contract

1. **Liệt kê các boundary:** reader, processor, writer, tasklet, stream lifecycle và listener.
2. **Phân loại nguyên nhân:** dữ liệu, tạm thời, cấu hình, tài nguyên và lỗi lập trình.
3. **Định nghĩa exception type:** chỉ tạo class riêng khi caller/policy cần phân biệt.
4. **Giữ nguyên cause:** chuyển exception kỹ thuật sang domain exception nhưng không làm mất root cause.
5. **Quy định return semantics:** null chỉ cho EOF/filter đúng contract; không dùng để che lỗi.
6. **Chọn retry/skip/fail:** giới hạn retry, skip limit và backoff theo nghiệp vụ.
7. **Quyết định rollback:** chỉ dùng noRollback khi transaction không cần hoàn tác.
8. **Xem xét side effect:** xác định thao tác nào ngoài transaction và cần idempotency/outbox.
9. **Thiết kế audit/log:** ghi business key và correlation ID, không log bí mật/payload không cần thiết.
10. **Kiểm thử từng boundary:** assert exception class, cause, listener, rollback, retry, skip và output.
11. **Kiểm thử restart:** xác nhận checkpoint và resource phục hồi đúng sau failure.
12. **Theo dõi production:** metric retry/skip/failure và alert theo nhóm nguyên nhân.

## 41. Những nguyên tắc cần nhớ

- Exception contract mô tả loại lỗi, ý nghĩa, cause, ngữ cảnh và cách caller xử lý.
- ItemReader trả null khi EOF; không trả null để che timeout hoặc lỗi parse.
- ItemProcessor trả null để filter có chủ đích; lỗi xử lý phải được thể hiện bằng exception.
- ItemWriter phải ném exception nếu không thể hoàn thành contract ghi; không nuốt lỗi rồi để checkpoint tiến lên.
- ItemStream dùng ItemStreamException cho lỗi open/update/close.
- Tasklet ném exception khi execute thất bại; RepeatStatus biểu diễn việc hoàn tất/lặp tiếp.
- Giữ cause khi bọc exception kỹ thuật thành domain exception.
- Retry dành cho lỗi có khả năng phục hồi; skip dành cho item có thể loại bỏ an toàn; lỗi cấu hình thường phải fail.
- noRollback, retry và skip là các quyết định riêng; noRollback không tự biến exception thành thành công.
- Side effect ngoài transaction cần idempotency, outbox, staging hoặc reconciliation.
- Listener nên quan sát/audit theo contract; không che giấu lỗi gốc hoặc thay đổi status tùy tiện.
- ExitStatus và BatchStatus không thay thế exception type.
- Exception message phải đủ ngữ cảnh nhưng không chứa bí mật hoặc payload nhạy cảm.
- Test phải xác nhận type/cause và hành vi retry/skip/rollback/restart, không chỉ assert rằng có exception.

Một exception contract rõ ràng giúp custom component hòa nhập đúng với fault tolerance của Spring Batch. Khi mỗi component phân biệt được EOF, filter và failure; khi exception giữ nguyên nguyên nhân; và khi retry, skip, rollback cùng side effect được thiết kế nhất quán, job có thể phục hồi có kiểm soát mà không che giấu lỗi hoặc làm sai dữ liệu.
