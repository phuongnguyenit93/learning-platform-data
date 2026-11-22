# ItemProcessListener trong Spring Batch

Trong một chunk-oriented Step, **ItemProcessor** nhận từng item từ reader, kiểm tra hoặc biến đổi item rồi trả kết quả cho writer. Khi cần quan sát quá trình xử lý từng item, Spring Batch cung cấp **ItemProcessListener**. Listener này cho phép chạy logic trước khi processor được gọi, sau khi processor trả kết quả hoặc khi processor ném exception.

ItemProcessListener hữu ích cho logging, metrics, audit và theo dõi các trường hợp item bị lọc hoặc xử lý lỗi. Nó không thay thế ItemProcessor và không phải nơi phù hợp để đặt quy tắc biến đổi dữ liệu. Hiểu rõ thời điểm gọi từng callback giúp ứng dụng ghi nhận đúng trạng thái, đặc biệt khi processor trả về null, Step dùng skip/retry hoặc Job chạy song song.

## 1. ItemProcessListener là gì?

ItemProcessListener là một listener ở cấp item, được gọi xung quanh thao tác xử lý của ItemProcessor. Giao diện có ba callback chính:

~~~java
public interface ItemProcessListener<T, S> extends StepListener {

    void beforeProcess(T item);

    void afterProcess(T item, S result);

    void onProcessError(T item, Exception e);
}
~~~

Trong đó:

- `T` là kiểu item đầu vào mà reader cung cấp cho processor.
- `S` là kiểu kết quả mà processor trả về cho writer.
- `beforeProcess(...)` chạy trước khi gọi processor cho item.
- `afterProcess(...)` chạy sau khi processor trả về kết quả.
- `onProcessError(...)` chạy khi thao tác xử lý phát sinh exception.

Ví dụ, một Step nhập đơn hàng có thể đọc `OrderInput`, chuyển thành `Order` trong processor và ghi kết quả ra database. Listener có thể ghi nhận mã đơn trước khi xử lý, xác định item được xử lý thành công hay bị lọc, và ghi nhận lỗi khi processor thất bại.

~~~mermaid
flowchart TD
    A["ItemReader trả về item"] --> B["ItemProcessListener.beforeProcess"]
    B --> C["ItemProcessor.process(item)"]
    C --> D{"Kết quả"}
    D -- "Output" --> E["ItemProcessListener.afterProcess(item, output)"]
    D -- "null" --> F["ItemProcessListener.afterProcess(item, null)"]
    C -- "Exception" --> G["ItemProcessListener.onProcessError(item, exception)"]
    E --> H["Chunk tiếp tục"]
    F --> H
    G --> I["Step xử lý lỗi theo policy"]
~~~

Listener quan sát từng lần gọi processor. Nó không tự quyết định item được ghi hay bị loại, cũng không tự xử lý exception thay cho Step.

## 2. Ba callback của ItemProcessListener

### beforeProcess(item)

`beforeProcess` được gọi trước khi Spring Batch gọi `ItemProcessor.process(item)` cho một item.

Một số công việc phù hợp:

- Ghi log bắt đầu xử lý một item.
- Tăng metric số lần xử lý được bắt đầu.
- Gắn mã tương quan hoặc thông tin trace vào logging context.
- Ghi nhận thời điểm bắt đầu nếu cần đo thời gian xử lý.
- Thu thập thông tin định danh item phục vụ điều tra.

Ví dụ:

~~~java
@Override
public void beforeProcess(OrderInput item) {
    log.debug(
        "Bắt đầu xử lý orderId={}",
        item.orderId()
    );
}
~~~

Không nên đặt logic nghiệp vụ như kiểm tra hạn mức, thay đổi trạng thái đơn hoặc gọi dịch vụ thanh toán trong callback này. Các quy tắc đó thuộc processor hoặc service nghiệp vụ được processor sử dụng.

### afterProcess(item, result)

`afterProcess` được gọi sau khi processor trả về kết quả. Tham số `result` có thể là một object đầu ra hoặc `null` nếu processor chủ động lọc item.

Ví dụ:

~~~java
@Override
public void afterProcess(OrderInput item, Order result) {
    if (result == null) {
        log.info(
            "Đơn hàng bị lọc orderId={}",
            item.orderId()
        );
        return;
    }

    log.debug(
        "Xử lý thành công orderId={}",
        item.orderId()
    );
}
~~~

Điểm quan trọng: processor trả `null` là một kết quả xử lý hợp lệ để lọc item. Trong trường hợp đó, `afterProcess` vẫn được gọi với kết quả null. Item đã được đọc và xử lý nhưng không được chuyển đến writer.

Nếu processor trả object đầu ra, `afterProcess` nhận object đó. Listener có thể ghi nhận kết quả hoặc metrics, nhưng không thay đổi object được trả về cho writer. Giá trị trả về của callback là void.

### onProcessError(item, exception)

`onProcessError` được gọi khi quá trình xử lý item phát sinh exception.

~~~java
@Override
public void onProcessError(
        OrderInput item,
        Exception exception) {

    log.warn(
        "Không xử lý được orderId={}",
        item.orderId(),
        exception
    );
}
~~~

Callback nhận item đầu vào và exception. Đây là nơi phù hợp để ghi nhận mã item và loại lỗi, giúp xác định bản ghi nào gây ra sự cố.

Listener không nên nuốt exception hoặc tự coi item là đã xử lý thành công. Exception vẫn được truyền vào cơ chế xử lý lỗi của Spring Batch. Tùy cấu hình, Step có thể retry, skip hoặc thất bại.

Nếu chính callback listener ném exception, nó có thể làm gián đoạn Step. Vì vậy, logic logging và metrics trong listener nên đơn giản, có khả năng chịu lỗi và không tạo thêm lỗi ngoài ý muốn.

## 3. Phân biệt output bình thường, filter và process error

Ba kết quả của processor có ý nghĩa khác nhau:

| Kết quả từ processor | Callback liên quan | Ý nghĩa |
|---|---|---|
| Trả về object | `afterProcess(item, result)` | Item được chuyển tiếp đến writer |
| Trả về null | `afterProcess(item, null)` | Item bị lọc, không chuyển đến writer |
| Ném exception | `onProcessError(item, exception)` | Xử lý thất bại; Step áp dụng policy |

Ví dụ processor:

~~~java
@Bean
ItemProcessor<OrderInput, Order> orderProcessor() {
    return input -> {
        if ("CANCELLED".equalsIgnoreCase(input.status())) {
            return null;
        }

        if (input.amount() == null || input.amount().signum() <= 0) {
            throw new IllegalArgumentException(
                "Số tiền không hợp lệ"
            );
        }

        return new Order(
            input.orderId(),
            input.customerId(),
            input.amount()
        );
    };
}
~~~

Listener có thể phân biệt:

- Đơn đã hủy: processor trả null, callback afterProcess nhận null.
- Đơn hợp lệ: processor trả Order, callback afterProcess nhận output.
- Số tiền không hợp lệ: processor ném exception, callback onProcessError được gọi.

### Filter không phải là exception

Nếu item bị loại theo quy tắc nghiệp vụ bình thường, processor nên trả null. Không nên ném exception chỉ để thể hiện rằng item không cần ghi.

Ví dụ, đơn hàng đã hủy có thể là một trường hợp nghiệp vụ hợp lệ để lọc. Nếu ném exception, ứng dụng phải cấu hình skip/retry và có thể làm tăng số liệu lỗi không cần thiết.

### Error không phải là filter

Nếu dữ liệu không thể xử lý do sai định dạng hoặc vi phạm quy tắc bắt buộc, không nên trả null để che giấu lỗi. Hãy ném exception phù hợp để Step ghi nhận lỗi và áp dụng chính sách.

Việc phân biệt rõ ba trường hợp giúp số liệu `filterCount`, process skip count và log lỗi phản ánh đúng bản chất dữ liệu.

## 4. Đăng ký listener vào Step

Trong Spring Batch 5, có thể đăng ký ItemProcessListener trực tiếp khi xây dựng Step bằng `.listener(...)`.

Ví dụ listener triển khai interface:

~~~java
@Bean
ItemProcessListener<OrderInput, Order> orderProcessListener() {
    return new ItemProcessListener<>() {

        @Override
        public void beforeProcess(OrderInput item) {
            log.debug("Bắt đầu orderId={}", item.orderId());
        }

        @Override
        public void afterProcess(OrderInput item, Order result) {
            if (result == null) {
                log.info("Đã lọc orderId={}", item.orderId());
            } else {
                log.debug("Đã xử lý orderId={}", item.orderId());
            }
        }

        @Override
        public void onProcessError(
                OrderInput item,
                Exception exception) {
            log.warn(
                "Lỗi xử lý orderId={}",
                item.orderId(),
                exception
            );
        }
    };
}
~~~

Gắn listener vào Step:

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        ItemWriter<Order> orderWriter,
        ItemProcessListener<OrderInput, Order> orderProcessListener) {

    return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .listener(orderProcessListener)
        .build();
}
~~~

Kiểu generic của listener nên khớp với kiểu input và output của processor. Trong ví dụ, listener nhận `OrderInput` và `Order` tương ứng với khai báo `.<OrderInput, Order>chunk(...)`.

Nếu Step không có ItemProcessor, ItemProcessListener không có thao tác xử lý item để quan sát. Khi cần theo dõi việc đọc hoặc ghi, dùng listener tương ứng là ItemReadListener hoặc ItemWriteListener.

## 5. Dùng annotation thay cho interface

Spring Batch cũng hỗ trợ khai báo listener bằng annotation. Cách này hữu ích khi muốn gom callback vào một class mà không cần triển khai trực tiếp interface.

~~~java
public class OrderProcessAuditListener {

    @BeforeProcess
    public void before(OrderInput item) {
        log.debug("Bắt đầu orderId={}", item.orderId());
    }

    @AfterProcess
    public void after(OrderInput item, Order result) {
        if (result == null) {
            log.info("Đơn bị lọc orderId={}", item.orderId());
        } else {
            log.debug("Đơn đã xử lý orderId={}", item.orderId());
        }
    }

    @OnProcessError
    public void onError(OrderInput item, Exception exception) {
        log.warn(
            "Lỗi xử lý orderId={}",
            item.orderId(),
            exception
        );
    }
}
~~~

Đăng ký class listener vào Step:

~~~java
@Bean
OrderProcessAuditListener orderProcessAuditListener() {
    return new OrderProcessAuditListener();
}
~~~

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
    .<OrderInput, Order>chunk(100, transactionManager)
    .reader(orderReader)
    .processor(orderProcessor)
    .writer(orderWriter)
    .listener(orderProcessAuditListener)
    .build();
~~~

Các annotation tương ứng:

| Annotation | Thời điểm gọi | Tham số |
|---|---|---|
| `@BeforeProcess` | Trước processor | Item đầu vào |
| `@AfterProcess` | Sau khi processor trả kết quả | Item đầu vào và kết quả |
| `@OnProcessError` | Khi processor ném exception | Item đầu vào và exception |

Chữ ký phương thức cần tương thích với callback tương ứng. Nếu dùng annotation, hãy để method public và khai báo kiểu tham số rõ ràng để Spring Batch có thể phát hiện và gọi đúng callback.

### Chọn interface hay annotation?

Dùng interface khi muốn có hợp đồng rõ ràng ở cấp Java, dễ mock và compiler kiểm tra đủ ba callback. Dùng annotation khi muốn một class chỉ khai báo những callback thực sự cần thiết hoặc đang tổ chức listener theo nhóm annotation.

Hai cách đều là cơ chế đăng ký listener. Không nên đăng ký cùng một logic hai lần bằng cả interface và annotation, vì callback có thể được thực hiện lặp.

## 6. ItemProcessListener và SkipListener

ItemProcessListener quan sát mỗi lần processor được gọi. SkipListener phản ánh item thực sự bị bỏ qua do chính sách skip.

Hai listener có mục đích khác nhau:

| Listener | Callback | Ý nghĩa |
|---|---|---|
| ItemProcessListener | `onProcessError(item, exception)` | Processor gặp exception trong một lần gọi |
| SkipListener | `onSkipInProcess(item, exception)` | Item bị skip trong giai đoạn process theo policy |
| ItemProcessListener | `afterProcess(item, null)` | Processor chủ động lọc item |
| SkipListener | `onSkipInRead(...)` | Item bị skip do lỗi đọc |
| SkipListener | `onSkipInWrite(...)` | Item bị skip do lỗi ghi |

Ví dụ, processor ném exception do một lỗi dữ liệu có thể retry. Trong mỗi lần processor thất bại, `onProcessError` có thể được gọi. Nếu cuối cùng exception được skip theo cấu hình, SkipListener ghi nhận item bị bỏ qua.

Ví dụ SkipListener:

~~~java
@Bean
SkipListener<OrderInput, Order> orderSkipListener(
        RejectedOrderService rejectedOrderService) {

    return new SkipListener<>() {

        @Override
        public void onSkipInProcess(
                OrderInput item,
                Throwable throwable) {
            rejectedOrderService.record(
                item.orderId(),
                throwable.getMessage()
            );
        }

        @Override
        public void onSkipInRead(Throwable throwable) {
            // Ghi nhận lỗi đọc nếu cần.
        }

        @Override
        public void onSkipInWrite(
                Order item,
                Throwable throwable) {
            // Ghi nhận lỗi ghi nếu cần.
        }
    };
}
~~~

Gắn SkipListener vào Step bằng `.listener(...)` tương tự.

### Vì sao không dùng onProcessError thay cho SkipListener?

`onProcessError` cho biết một lần gọi processor đã gặp lỗi. Nó không khẳng định item cuối cùng sẽ bị skip. Item có thể được retry và xử lý thành công ở lần tiếp theo.

SkipListener phù hợp khi cần ghi nhận quyết định skip cuối cùng. Nếu ghi reject record hoặc gửi thông báo trong mọi lần `onProcessError`, cùng một item có thể bị ghi nhận nhiều lần do retry.

## 7. Listener hoạt động thế nào khi có retry?

Khi Step được cấu hình retry, processor có thể được gọi lại cho cùng một item. Các callback của ItemProcessListener gắn với từng lần gọi processor.

Ví dụ một item gặp lỗi tạm thời ở hai lần đầu rồi thành công:

~~~text
Attempt 1:
  beforeProcess(item)
  process(item) -> exception
  onProcessError(item, exception)

Attempt 2:
  beforeProcess(item)
  process(item) -> exception
  onProcessError(item, exception)

Attempt 3:
  beforeProcess(item)
  process(item) -> output
  afterProcess(item, output)
~~~

Đây là lý do listener cần phân biệt **số lần thử xử lý** và **số item cuối cùng thành công**.

Nếu tăng counter thành công trong `beforeProcess`, số liệu sẽ đếm cả lần thất bại. Nếu ghi audit "đã xử lý xong" trong `onProcessError`, thông tin sẽ sai. Hãy đặt metric đúng callback:

- Số lần bắt đầu: `beforeProcess`.
- Số lần processor trả kết quả: `afterProcess`.
- Số lần processor trả null: `afterProcess` với result null.
- Số lần xử lý gặp exception: `onProcessError`.
- Số item bị skip cuối cùng: SkipListener.

Nếu muốn đếm item logic duy nhất, cần dùng khóa item và chiến lược deduplication phù hợp. Không thể lấy số callback làm số lượng item duy nhất khi retry xảy ra.

## 8. Listener không thay thế ItemProcessor

ItemProcessListener chỉ nhận thông báo về quá trình xử lý. Nó không trả về output và không có cơ chế thay đổi kết quả mà processor tạo ra.

Không nên viết logic nghiệp vụ trong listener như:

- Chuyển đổi số tiền.
- Chuẩn hóa mã khách hàng.
- Quyết định item có hợp lệ hay không.
- Tính thuế hoặc phí.
- Thay đổi trạng thái đơn hàng.
- Gọi service để cập nhật dữ liệu nghiệp vụ.

Những công việc đó thuộc ItemProcessor hoặc service nghiệp vụ mà processor gọi.

Ví dụ phân chia trách nhiệm:

~~~java
@Bean
ItemProcessor<OrderInput, Order> orderProcessor(
        OrderValidationService validationService) {

    return input -> {
        validationService.validate(input);

        if ("CANCELLED".equals(input.status())) {
            return null;
        }

        return new Order(
            input.orderId(),
            input.customerId().trim(),
            input.amount().setScale(2, RoundingMode.HALF_UP)
        );
    };
}
~~~

Listener chỉ quan sát kết quả:

~~~java
@Override
public void afterProcess(OrderInput item, Order result) {
    if (result == null) {
        log.info("Đơn hàng bị lọc orderId={}", item.orderId());
    } else {
        log.debug("Đơn hàng sẵn sàng ghi orderId={}", item.orderId());
    }
}
~~~

Cách phân chia này giúp processor dễ kiểm thử nghiệp vụ, còn listener tập trung vào quan sát và tích hợp vận hành.

## 9. Ghi log và audit trong listener

Listener là nơi thuận tiện để ghi nhận các sự kiện quanh quá trình xử lý. Tuy nhiên, mỗi item có thể kích hoạt nhiều callback và một Job có thể xử lý hàng triệu item. Log quá chi tiết có thể làm tăng dung lượng log và giảm hiệu năng.

### Ghi thông tin định danh

Ưu tiên ghi mã nghiệp vụ hoặc mã tương quan thay vì toàn bộ object:

~~~java
@Override
public void beforeProcess(OrderInput item) {
    log.debug(
        "Processing orderId={}",
        item.orderId()
    );
}
~~~

Tránh ghi toàn bộ nội dung item nếu chứa email, số điện thoại, thông tin thanh toán hoặc dữ liệu cá nhân.

### Ghi lỗi có ngữ cảnh

~~~java
@Override
public void onProcessError(
        OrderInput item,
        Exception exception) {

    log.error(
        "Process failed for orderId={}, exceptionType={}",
        item.orderId(),
        exception.getClass().getSimpleName(),
        exception
    );
}
~~~

Thông tin hữu ích gồm mã item, tên Step, mã batch hoặc JobExecution ID nếu có thể truy cập an toàn, loại exception và stack trace phù hợp.

Không nên ghi token, secret hoặc toàn bộ tham số nhạy cảm vào log.

### Audit khác với logging

Log phục vụ vận hành và chẩn đoán. Audit thường là dữ liệu có cấu trúc, cần truy vấn và lưu giữ theo chính sách.

Nếu cần audit item được xử lý, nên xác định rõ sự kiện nào được lưu:

- Bắt đầu thử xử lý.
- Processor trả output.
- Item bị lọc.
- Một lần xử lý gặp lỗi.
- Item thực sự bị skip.
- Item được writer commit thành công.

ItemProcessListener chỉ quan sát đến kết quả của processor. Nó không chứng minh item đã được writer ghi và transaction đã commit. Nếu audit yêu cầu xác nhận ghi thành công, cần dùng ItemWriteListener hoặc cơ chế audit gắn với transaction/đích dữ liệu.

## 10. Đo thời gian xử lý từng item

Có thể dùng listener để đo thời gian processor thực hiện. Tuy nhiên, không nên lưu thời điểm bắt đầu trong một field dùng chung duy nhất nếu Step có thể xử lý đồng thời.

Với Step đơn luồng, một cách đơn giản là dùng cấu trúc theo item hoặc ThreadLocal. Tuy nhiên, cách an toàn hơn là dùng metrics hỗ trợ timer hoặc ghi thời gian ngay trong processor decorator.

Ví dụ minh họa listener cho Step đơn luồng:

~~~java
public class TimedOrderProcessListener
        implements ItemProcessListener<OrderInput, Order> {

    private long startedAt;

    @Override
    public void beforeProcess(OrderInput item) {
        startedAt = System.nanoTime();
    }

    @Override
    public void afterProcess(OrderInput item, Order result) {
        long elapsed = System.nanoTime() - startedAt;

        log.debug(
            "orderId={}, processTimeNanos={}",
            item.orderId(),
            elapsed
        );
    }

    @Override
    public void onProcessError(
            OrderInput item,
            Exception exception) {
        long elapsed = System.nanoTime() - startedAt;

        log.warn(
            "orderId={}, process failed after {} ns",
            item.orderId(),
            elapsed
        );
    }
}
~~~

Ví dụ này chỉ phù hợp với xử lý tuần tự, vì field `startedAt` bị ghi đè nếu nhiều thread gọi listener cùng lúc. Với xử lý song song, hãy dùng timer metrics hoặc lưu thời điểm theo ngữ cảnh thread/item một cách thread-safe.

Nếu processor được retry, thời gian ở trên đo từng lần thử. Muốn đo tổng thời gian từ lần đầu đến khi item hoàn tất hoặc bị skip, cần một cơ chế theo dõi riêng và xử lý trạng thái retry rõ ràng.

## 11. Listener và transaction boundary

ItemProcessListener được gọi trong luồng xử lý chunk. Vì vậy, callback thường chạy trong phạm vi xử lý transaction của chunk, nhưng tác động bên ngoài transaction không tự được rollback.

Ví dụ listener ghi audit bằng JdbcTemplate cùng DataSource với Step có thể tham gia transaction hiện tại. Nếu chunk rollback, bản ghi audit đó cũng có thể rollback.

Ngược lại, nếu listener:

- Gửi email.
- Gọi HTTP API.
- Gửi message tới broker không tham gia transaction.
- Ghi file qua filesystem.
- Ghi database bằng một transaction độc lập.

thì side effect đó có thể tồn tại dù chunk rollback hoặc processor được retry.

### Không gửi thông báo thành công trong afterProcess

`afterProcess` chỉ cho biết processor đã trả về kết quả. Writer có thể thất bại sau đó, hoặc transaction của chunk có thể rollback.

Nếu gửi email "đơn hàng đã nhập thành công" ngay trong `afterProcess`, thông báo có thể được gửi dù đơn hàng chưa được ghi bền vững.

Nếu cần thông báo sau khi dữ liệu commit, hãy dùng cơ chế sau commit phù hợp, outbox pattern hoặc một Step publish riêng sau khi Step ghi dữ liệu đã hoàn tất.

### Không ghi audit thành công trước commit

Tương tự, `afterProcess` không chứng minh item đã được writer ghi thành công. Nếu audit cần phản ánh dữ liệu đã commit, hãy đặt audit cùng transaction với writer hoặc phát sinh từ trạng thái đã commit.

## 12. Xử lý exception trong listener

Callback `onProcessError` nhận exception do quá trình xử lý phát sinh. Listener nên ghi nhận và để exception tiếp tục được Spring Batch xử lý.

Không nên:

~~~java
@Override
public void onProcessError(OrderInput item, Exception exception) {
    log.error("Processing error", exception);
    // Không có cách nào biến lỗi thành thành công chỉ bằng callback này.
}
~~~

Không cố sửa item hoặc tự gọi lại processor trong callback. Retry thuộc cấu hình fault-tolerant của Step.

### Listener cũng có thể phát sinh exception

Nếu listener gọi dịch vụ audit hoặc metrics bên ngoài và dịch vụ đó thất bại, exception từ listener có thể làm Step thất bại. Vì vậy:

- Ưu tiên thao tác nhanh và đơn giản.
- Không gọi API chậm trong callback cho từng item.
- Dùng timeout khi gọi dịch vụ bên ngoài.
- Xử lý lỗi telemetry theo chính sách riêng nếu có thể.
- Không để lỗi logging làm mất khả năng xử lý dữ liệu nếu logging không phải yêu cầu nghiệp vụ bắt buộc.

Nếu audit là yêu cầu bắt buộc, cần thiết kế audit như một phần của luồng dữ liệu có transaction và retry rõ ràng thay vì dựa vào một callback best-effort.

## 13. Thread safety và trạng thái listener

Listener thường được khai báo thành Spring bean và có thể tồn tại lâu hơn một lần xử lý item. Nếu Step dùng TaskExecutor, partitioning hoặc một cơ chế xử lý đồng thời, nhiều callback có thể được thực hiện đồng thời tùy cấu hình.

Tránh dùng field mutable không đồng bộ:

~~~java
public class UnsafeListener
        implements ItemProcessListener<OrderInput, Order> {

    private long processedCount;

    @Override
    public void afterProcess(OrderInput item, Order result) {
        processedCount++;
    }
}
~~~

Trong xử lý đồng thời, phép tăng trên có thể mất cập nhật. Dùng MeterRegistry, LongAdder hoặc bộ đếm thread-safe phù hợp.

Ví dụ:

~~~java
public class OrderMetricsListener
        implements ItemProcessListener<OrderInput, Order> {

    private final LongAdder processed = new LongAdder();
    private final LongAdder filtered = new LongAdder();
    private final LongAdder failures = new LongAdder();

    @Override
    public void afterProcess(OrderInput item, Order result) {
        if (result == null) {
            filtered.increment();
        } else {
            processed.increment();
        }
    }

    @Override
    public void onProcessError(
            OrderInput item,
            Exception exception) {
        failures.increment();
    }

    public long processedCount() {
        return processed.sum();
    }

    public long filteredCount() {
        return filtered.sum();
    }

    public long failureCount() {
        return failures.sum();
    }
}
~~~

Các bộ đếm này phản ánh callback trong vòng đời listener. Nếu listener bean được chia sẻ giữa nhiều JobExecution hoặc StepExecution, cần xác định phạm vi reset và đọc số liệu. Không nên giả định một field counter luôn tương ứng với đúng một Job.

### Không giữ item hiện tại trong field dùng chung

Không nên gán item trong `beforeProcess` vào một field rồi đọc lại trong `afterProcess` nếu listener có thể được gọi đồng thời. Callback của các item khác có thể ghi đè field.

Nếu cần đo thời gian hoặc liên kết callback theo item, dùng metrics phù hợp hoặc một cấu trúc theo thread/identifier có vòng đời và cleanup rõ ràng.

## 14. Truy cập thông tin StepExecution khi cần

ItemProcessListener nhận item và kết quả, nhưng không nhận trực tiếp StepExecution trong các callback. Nếu cần thông tin Step như tên Step hoặc JobExecution ID, có thể dùng StepExecutionListener kết hợp với listener process, hoặc lấy thông tin qua các cơ chế scope/context phù hợp.

Ví dụ một listener có thể triển khai cả hai interface:

~~~java
public class OrderStepListener
        implements StepExecutionListener,
                   ItemProcessListener<OrderInput, Order> {

    private String stepName;

    @Override
    public void beforeStep(StepExecution stepExecution) {
        this.stepName = stepExecution.getStepName();
    }

    @Override
    public void beforeProcess(OrderInput item) {
        log.debug(
            "step={}, orderId={}",
            stepName,
            item.orderId()
        );
    }

    @Override
    public void afterProcess(OrderInput item, Order result) {
        // Ghi nhận kết quả xử lý.
    }

    @Override
    public void onProcessError(
            OrderInput item,
            Exception exception) {
        log.warn(
            "step={}, orderId={} failed",
            stepName,
            item.orderId(),
            exception
        );
    }
}
~~~

Gắn listener vào Step bằng `.listener(...)`. Nếu cùng một object triển khai nhiều listener interface, Spring Batch có thể đăng ký các callback tương ứng từ object đó.

Ví dụ trên giả định listener instance thuộc một Step execution phù hợp. Nếu cùng một singleton instance được chia sẻ giữa các Step chạy song song, field `stepName` có thể bị ghi đè. Trong trường hợp đó, dùng Step scope hoặc thiết kế listener stateless để tránh trạng thái dùng chung.

## 15. Kết hợp ItemProcessListener với metrics

Một hệ thống batch lớn thường cần theo dõi:

- Tổng số lần processor được gọi.
- Số lần processor trả output.
- Số item bị filter.
- Số lần xử lý phát sinh exception.
- Thời gian xử lý trung bình và phân vị.
- Tỷ lệ lỗi theo loại dữ liệu hoặc loại exception.

Có thể dùng Micrometer MeterRegistry để ghi nhận metrics. Ví dụ minh họa:

~~~java
public class OrderProcessMetricsListener
        implements ItemProcessListener<OrderInput, Order> {

    private final Counter processed;
    private final Counter filtered;
    private final Counter errors;

    public OrderProcessMetricsListener(MeterRegistry registry) {
        this.processed = registry.counter("batch.order.processed");
        this.filtered = registry.counter("batch.order.filtered");
        this.errors = registry.counter("batch.order.process.errors");
    }

    @Override
    public void afterProcess(OrderInput item, Order result) {
        if (result == null) {
            filtered.increment();
        } else {
            processed.increment();
        }
    }

    @Override
    public void onProcessError(
            OrderInput item,
            Exception exception) {
        errors.increment();
    }
}
~~~

Cần chú ý rằng retry làm tăng số lần `onProcessError` nhưng không nhất thiết làm tăng số item cuối cùng bị skip. Vì vậy, tên metric nên phản ánh chính xác nó đếm lần thử lỗi hay item lỗi duy nhất.

Tránh đưa orderId, customerId hoặc giá trị không giới hạn vào metric tag vì sẽ tạo cardinality rất lớn. Dùng tag có tập giá trị nhỏ như job name, step name, loại exception hoặc trạng thái xử lý.

## 16. Kiểm thử ItemProcessListener

Nên kiểm thử listener ở cả mức callback và mức tích hợp Step.

### Kiểm thử callback riêng

Có thể gọi trực tiếp từng method để xác nhận listener ghi log hoặc cập nhật metrics đúng với input:

| Tình huống | Callback mong đợi |
|---|---|
| Bắt đầu xử lý item | `beforeProcess(item)` |
| Processor trả object | `afterProcess(item, result)` |
| Processor trả null | `afterProcess(item, null)` |
| Processor ném exception | `onProcessError(item, exception)` |

Kiểm thử trực tiếp hữu ích để xác nhận logic trong listener. Tuy nhiên, nó không chứng minh listener đã được đăng ký vào Step.

### Kiểm thử tích hợp Step

Trong test context Spring Batch, chạy Step với reader, processor và writer kiểm thử. Dùng mock hoặc spy listener để xác nhận callback được gọi trong luồng thật.

Các tình huống nên có:

1. Processor trả output cho item hợp lệ.
2. Processor trả null cho item bị lọc.
3. Processor ném exception và Step thất bại.
4. Processor ném exception nhưng item được retry thành công.
5. Processor ném exception và item bị skip.
6. Listener được đăng ký đúng một lần.
7. Listener không làm thay đổi kết quả processor hoặc dữ liệu writer.
8. Callback được gọi đúng số lần trong trường hợp không có retry.

Nếu test có retry, không nên mong đợi mỗi item chỉ có một cặp callback. Hãy kiểm tra số lần thử và kết quả cuối cùng theo policy đã cấu hình.

### Kiểm thử lỗi trong listener

Nếu listener ghi audit hoặc metrics qua service, hãy kiểm tra hành vi khi service đó thất bại. Xác định rõ ứng dụng có chấp nhận tiếp tục xử lý hay yêu cầu Step thất bại khi không thể ghi audit.

Với audit bắt buộc, cần kiểm thử transaction và restart để tránh mất hoặc ghi trùng audit event.

## 17. Những lỗi thiết kế thường gặp

### Dùng listener để biến đổi dữ liệu

ItemProcessListener không trả về item đầu ra. Logic chuẩn hóa, lọc và kiểm tra phải nằm trong processor.

### Nhầm filter với process error

Processor trả null là lọc có chủ đích và đi qua afterProcess. Processor ném exception đi qua onProcessError và được Step xử lý theo policy.

### Dùng onProcessError để ghi nhận item đã skip

Một lỗi có thể được retry và thành công. Dùng SkipListener để ghi nhận item thực sự bị skip.

### Gửi thông báo thành công trong afterProcess

Processor trả output chưa có nghĩa writer đã ghi hoặc transaction đã commit. Publish thông báo sau commit hoặc qua outbox/Step riêng.

### Ghi audit lặp khi retry

Một item có thể kích hoạt onProcessError nhiều lần. Nếu cần ghi một bản ghi reject duy nhất, hãy dùng khóa deduplication hoặc SkipListener cho sự kiện skip cuối cùng.

### Listener làm chậm từng item

Gọi API đồng bộ hoặc truy vấn database nặng trong callback có thể làm giảm throughput đáng kể. Giữ callback nhẹ hoặc dùng cơ chế thu thập metrics phù hợp.

### Dùng field mutable không thread-safe

Listener có thể được gọi đồng thời trong cấu hình xử lý song song. Dùng state stateless, thread-safe counter hoặc scope phù hợp.

### Log toàn bộ item

Item có thể chứa dữ liệu nhạy cảm. Ghi mã định danh cần thiết và thông tin lỗi đã được kiểm soát.

### Đăng ký cùng listener hai lần

Nếu cùng một logic được đăng ký qua nhiều cơ chế, callback có thể bị gọi lặp. Chỉ đăng ký một cách rõ ràng cho mỗi Step.

## 18. Quy trình triển khai ItemProcessListener

Khi thêm listener vào một Step, có thể thực hiện theo trình tự:

1. **Xác định mục đích:** logging, metrics, audit hay trace.
2. **Xác định callback:** before, after hoặc error; chỉ triển khai callback cần thiết.
3. **Phân biệt kết quả:** output, filter null và exception.
4. **Tách trách nhiệm:** giữ logic nghiệp vụ trong ItemProcessor.
5. **Đăng ký listener:** dùng interface hoặc annotation và gắn vào đúng Step.
6. **Xử lý retry/skip:** phân biệt lần thử lỗi với item bị skip cuối cùng.
7. **Kiểm soát side effect:** không gửi thông báo thành công trước commit.
8. **Bảo vệ dữ liệu:** chỉ log trường định danh cần thiết.
9. **Bảo đảm thread safety:** tránh trạng thái mutable dùng chung không đồng bộ.
10. **Kiểm thử:** xác nhận callback trong luồng thành công, filter, exception, retry và skip.

## 19. Những điểm cần nhớ

- ItemProcessListener quan sát quá trình gọi ItemProcessor cho từng item.
- `beforeProcess` chạy trước processor.
- `afterProcess` chạy khi processor trả kết quả; result có thể là null nếu item bị lọc.
- `onProcessError` chạy khi processor phát sinh exception.
- Listener không thay đổi input, output hoặc quyết định filter.
- Dùng ItemProcessor cho logic nghiệp vụ và SkipListener cho item thực sự bị skip.
- Retry có thể làm callback được gọi nhiều lần cho cùng item.
- `afterProcess` không chứng minh writer đã ghi thành công hoặc transaction đã commit.
- Side effect bên ngoài trong listener có thể không rollback cùng chunk.
- Giữ callback nhẹ, không ghi dữ liệu nhạy cảm và bảo đảm thread safety.
- Đăng ký listener vào Step bằng `.listener(...)` hoặc cơ chế annotation tương ứng.
- Kiểm thử cả callback riêng và tích hợp Step với filter, exception, retry và skip.

ItemProcessListener giúp quan sát rõ vòng đời xử lý từng item trong Spring Batch. Khi đặt đúng logic vào từng callback và phân biệt kết quả xử lý với quyết định commit của chunk, listener cung cấp log, metrics và audit hữu ích mà không làm luồng nghiệp vụ trở nên khó kiểm soát.

