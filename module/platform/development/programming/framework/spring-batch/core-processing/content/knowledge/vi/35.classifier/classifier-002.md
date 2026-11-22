# Phân loại theo payload type

Trong Spring Batch, một chunk đôi khi chứa nhiều loại payload khác nhau. Ví dụ, một luồng tích hợp có thể nhận `OrderCreated`, `OrderCancelled` và `PaymentReceived` trong cùng một lần đọc. Mỗi loại payload cần được ghi đến bảng, file hoặc hệ thống đích riêng. Khi đó, ứng dụng cần phân loại item theo kiểu payload và chọn writer phù hợp.

Spring Batch cung cấp `ClassifierCompositeItemWriter<T>` để định tuyến item đến writer delegate dựa trên một `Classifier`. Classifier nhận item và trả về writer sẽ xử lý item đó. Cách này phù hợp khi mỗi item chỉ cần đi đến writer được chọn. Nếu mọi item phải được ghi đến tất cả writer, dùng `CompositeItemWriter` thay vì classifier writer.

Việc phân loại có thể dựa trên kiểu Java thực tế của object, một trường discriminator như `payloadType` trong JSON, hoặc một thuộc tính nghiệp vụ. Cần xác định rõ contract của payload, xử lý loại không được hỗ trợ và giữ việc mapping type an toàn, tường minh.

## 1. Payload type là gì?

Payload là phần dữ liệu mang thông tin nghiệp vụ. Trong một hệ thống event hoặc import tổng hợp, payload có thể đại diện cho nhiều loại sự kiện:

```text
Input stream
    |
    +--> OrderCreated
    |
    +--> OrderCancelled
    |
    +--> PaymentReceived
    |
    +--> RefundRequested
```

Mỗi loại có thể có cấu trúc và quy tắc ghi khác nhau:

| Payload type | Dữ liệu chính | Đích ghi ví dụ |
|---|---|---|
| `OrderCreated` | Order ID, customer, amount | Bảng đơn hàng |
| `OrderCancelled` | Order ID, reason, cancelledAt | Bảng lịch sử hủy |
| `PaymentReceived` | Payment ID, order ID, amount | Bảng thanh toán |
| `RefundRequested` | Payment ID, refund amount, reason | Bảng yêu cầu hoàn tiền |

Nếu tất cả payload được đọc thành một kiểu chung, chẳng hạn `DomainEvent`, processor có thể xử lý phần logic chung và writer có thể phân loại theo subtype để ghi đến đúng đích.

## 2. Hai cách xác định payload type

Có hai nguồn thông tin thường được dùng để phân loại.

**Kiểu Java runtime:** item đã được deserialize thành object cụ thể. Có thể dùng `instanceof` hoặc kiểm tra class/interface để xác định subtype.

```java
if (payload instanceof OrderCreated created) {
    // Xử lý OrderCreated
} else if (payload instanceof PaymentReceived payment) {
    // Xử lý PaymentReceived
}
```

**Discriminator trong dữ liệu:** payload ban đầu có một trường như `type`, `eventType` hoặc `payloadType`. Ví dụ JSON có `"type": "ORDER_CREATED"`. Ứng dụng đọc discriminator, kiểm tra allowlist rồi deserialize phần dữ liệu thành class tương ứng.

Hai cách có thể phối hợp: discriminator quyết định class khi deserialize; sau đó Classifier định tuyến dựa trên kiểu Java thực tế. Cách này giúp writer làm việc với domain model có type rõ ràng thay vì liên tục parse chuỗi JSON.

## 3. Mô hình payload dùng chung một interface

Khi các payload thuộc cùng một miền nghiệp vụ, nên khai báo một interface hoặc base class chung:

```java
public sealed interface DomainEvent
        permits OrderCreated, OrderCancelled, PaymentReceived {
}

public record OrderCreated(
        long orderId,
        long customerId,
        BigDecimal amount
) implements DomainEvent {
}

public record OrderCancelled(
        long orderId,
        String reason
) implements DomainEvent {
}

public record PaymentReceived(
        long paymentId,
        long orderId,
        BigDecimal amount
) implements DomainEvent {
}
```

Trong ví dụ Java 17, `sealed interface` giới hạn các subtype được phép. Nếu dự án dùng Java phiên bản cũ hơn, có thể dùng interface thông thường hoặc abstract class.

Reader có thể trả về `DomainEvent`; classifier nhận kiểu chung này và chọn writer theo subtype. Một kiểu chung giúp Step có contract rõ ràng mà vẫn giữ được thông tin type cụ thể của từng item.

## 4. Classifier trong Spring

`Classifier<C, T>` là một abstraction đơn giản: nhận một đối tượng đầu vào và trả về một kết quả phân loại. Với writer routing, đầu vào là payload và kết quả là writer delegate.

Về ý nghĩa, classifier có dạng:

```java
public interface Classifier<C, T> {
    T classify(C classifiable);
}
```

Ví dụ classifier cho `DomainEvent`:

```java
public class DomainEventWriterClassifier
        implements Classifier<DomainEvent, ItemWriter<? super DomainEvent>> {

    private final ItemWriter<? super DomainEvent> orderWriter;
    private final ItemWriter<? super DomainEvent> cancellationWriter;
    private final ItemWriter<? super DomainEvent> paymentWriter;

    public DomainEventWriterClassifier(
            ItemWriter<? super DomainEvent> orderWriter,
            ItemWriter<? super DomainEvent> cancellationWriter,
            ItemWriter<? super DomainEvent> paymentWriter) {
        this.orderWriter = orderWriter;
        this.cancellationWriter = cancellationWriter;
        this.paymentWriter = paymentWriter;
    }

    @Override
    public ItemWriter<? super DomainEvent> classify(DomainEvent event) {
        if (event instanceof OrderCreated) {
            return orderWriter;
        }
        if (event instanceof OrderCancelled) {
            return cancellationWriter;
        }
        if (event instanceof PaymentReceived) {
            return paymentWriter;
        }

        throw new IllegalArgumentException(
                "Unsupported payload type: " + event.getClass().getName()
        );
    }
}
```

Classifier nên là logic xác định, dễ kiểm thử và không tạo side effect. Nó chỉ chọn đích ghi; việc ghi dữ liệu thuộc trách nhiệm của writer delegate.

## 5. Dùng ClassifierCompositeItemWriter

`ClassifierCompositeItemWriter<T>` nhận một classifier để quyết định writer cho từng item. Có thể cấu hình bằng builder:

```java
@Bean
public ClassifierCompositeItemWriter<DomainEvent> eventWriter(
        Classifier<DomainEvent, ItemWriter<? super DomainEvent>> eventWriterClassifier) {

    return new ClassifierCompositeItemWriterBuilder<DomainEvent>()
            .classifier(eventWriterClassifier)
            .build();
}
```

Khi Step gọi writer với một chunk gồm nhiều subtype, classifier xác định delegate phù hợp cho từng item. Các item được phân loại đến cùng delegate được chuyển cho delegate đó để ghi.

Ví dụ chunk hỗn hợp:

```text
Chunk<DomainEvent>
  [OrderCreated, PaymentReceived, OrderCancelled, OrderCreated]
                    |
                    v
          ClassifierCompositeItemWriter
                    |
          +---------+----------+
          |         |          |
          v         v          v
      OrderWriter PaymentWriter CancellationWriter
       [2 items]   [1 item]       [1 item]
```

Khác với `CompositeItemWriter`, classifier writer không gửi mọi item đến mọi delegate. Mỗi item được định tuyến theo kết quả phân loại.

## 6. Writer delegate có kiểu chung

Nếu các writer có thể nhận kiểu chung `DomainEvent`, cấu hình khá đơn giản:

```java
@Bean
public ItemWriter<DomainEvent> orderEventWriter(OrderRepository repository) {
    return chunk -> {
        for (DomainEvent event : chunk) {
            OrderCreated created = (OrderCreated) event;
            repository.insert(created.orderId(), created.customerId(), created.amount());
        }
    };
}
```

Tuy nhiên, kiểu chung có thể khiến code phải cast ở bên trong writer. Nếu writer delegate chuyên biệt muốn nhận `ItemWriter<OrderCreated>`, cần một adapter có trách nhiệm kiểm tra và chuyển kiểu từ interface chung sang subtype.

## 7. Adapter an toàn kiểu cho writer chuyên biệt

Một adapter có thể triển khai `ItemWriter<DomainEvent>`, kiểm tra từng item có đúng subtype, rồi chuyển chunk sang writer chuyên biệt:

```java
public class TypedEventWriter<P extends DomainEvent>
        implements ItemWriter<DomainEvent> {

    private final Class<P> payloadType;
    private final ItemWriter<P> delegate;

    public TypedEventWriter(Class<P> payloadType, ItemWriter<P> delegate) {
        this.payloadType = payloadType;
        this.delegate = delegate;
    }

    @Override
    public void write(Chunk<? extends DomainEvent> chunk) throws Exception {
        Chunk<P> typedChunk = new Chunk<>();

        for (DomainEvent event : chunk) {
            if (!payloadType.isInstance(event)) {
                throw new IllegalArgumentException(
                        "Expected " + payloadType.getName()
                                + " but received " + event.getClass().getName()
                );
            }
            typedChunk.add(payloadType.cast(event));
        }

        delegate.write(typedChunk);
    }
}
```

Adapter giúp giữ writer nghiệp vụ có generic type cụ thể, đồng thời đáp ứng kiểu writer chung mà classifier cần trả về. Kiểm tra subtype tại adapter giúp lỗi cấu hình classifier được phát hiện sớm thay vì cast không an toàn sâu trong writer.

Nếu adapter bọc một delegate triển khai `ItemStream`, adapter cũng phải chuyển tiếp `open()`, `update()` và `close()`, hoặc Step cần đăng ký delegate stream tường minh. Không được bỏ qua lifecycle khi writer con có state/checkpoint.

## 8. Cấu hình đầy đủ với các writer chuyên biệt

Giả sử có ba writer:

```java
@Bean
public ItemWriter<OrderCreated> orderCreatedWriter(OrderRepository repository) {
    return chunk -> repository.insertCreatedOrders(chunk.getItems());
}

@Bean
public ItemWriter<OrderCancelled> orderCancelledWriter(OrderRepository repository) {
    return chunk -> repository.insertCancellations(chunk.getItems());
}

@Bean
public ItemWriter<PaymentReceived> paymentReceivedWriter(PaymentRepository repository) {
    return chunk -> repository.insertPayments(chunk.getItems());
}
```

Tạo adapter cho từng subtype:

```java
@Bean
public ItemWriter<DomainEvent> orderCreatedAdapter(
        ItemWriter<OrderCreated> orderCreatedWriter) {
    return new TypedEventWriter<>(OrderCreated.class, orderCreatedWriter);
}

@Bean
public ItemWriter<DomainEvent> orderCancelledAdapter(
        ItemWriter<OrderCancelled> orderCancelledWriter) {
    return new TypedEventWriter<>(OrderCancelled.class, orderCancelledWriter);
}

@Bean
public ItemWriter<DomainEvent> paymentReceivedAdapter(
        ItemWriter<PaymentReceived> paymentReceivedWriter) {
    return new TypedEventWriter<>(PaymentReceived.class, paymentReceivedWriter);
}
```

Classifier:

```java
@Bean
public Classifier<DomainEvent, ItemWriter<? super DomainEvent>> eventWriterClassifier(
        ItemWriter<DomainEvent> orderCreatedAdapter,
        ItemWriter<DomainEvent> orderCancelledAdapter,
        ItemWriter<DomainEvent> paymentReceivedAdapter) {

    return event -> {
        if (event instanceof OrderCreated) {
            return orderCreatedAdapter;
        }
        if (event instanceof OrderCancelled) {
            return orderCancelledAdapter;
        }
        if (event instanceof PaymentReceived) {
            return paymentReceivedAdapter;
        }
        throw new IllegalArgumentException(
                "Unsupported event: " + event.getClass().getName()
        );
    };
}
```

Classifier composite:

```java
@Bean
public ClassifierCompositeItemWriter<DomainEvent> domainEventWriter(
        Classifier<DomainEvent, ItemWriter<? super DomainEvent>> eventWriterClassifier) {

    return new ClassifierCompositeItemWriterBuilder<DomainEvent>()
            .classifier(eventWriterClassifier)
            .build();
}
```

Mỗi writer chuyên biệt chỉ nhận đúng subtype. Adapter thực hiện kiểm tra kiểu và chuyển chunk trước khi gọi delegate.

## 9. Phân loại bằng instanceof hay getClass()?

Hai cách kiểm tra thường gặp:

```java
if (payload instanceof OrderCreated) {
    // route
}
```

và:

```java
if (payload.getClass() == OrderCreated.class) {
    // route
}
```

`instanceof` chấp nhận object là instance của subtype hoặc implementation phù hợp. `getClass() == ...` chỉ khớp chính xác class runtime đó.

Thông thường, `instanceof` phù hợp hơn khi phân loại theo polymorphism, nhất là khi có subclass hoặc proxy. Kiểm tra class chính xác chỉ nên dùng khi contract yêu cầu loại trừ mọi subtype.

Tránh phân loại bằng `getClass().getSimpleName()` hoặc chuỗi class name vì dễ hỏng khi rename/refactor và khó kiểm soát dữ liệu đầu vào. Dùng kiểu Java, enum discriminator hoặc registry tường minh.

## 10. Phân loại bằng discriminator field

Không phải lúc nào reader cũng tạo được subtype Java ngay từ đầu. Một payload có thể được đọc thành envelope:

```java
public record EventEnvelope(
        String payloadType,
        JsonNode payload
) {
}
```

JSON ví dụ:

```json
{
  "payloadType": "PAYMENT_RECEIVED",
  "payload": {
    "paymentId": 9001,
    "orderId": 1001,
    "amount": 125.50
  }
}
```

Có thể dùng registry allowlist để chuyển discriminator thành subtype:

```java
public class EventPayloadMapper {

    private final ObjectMapper objectMapper;

    public EventPayloadMapper(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public DomainEvent toDomainEvent(EventEnvelope envelope) throws JsonProcessingException {
        return switch (envelope.payloadType()) {
            case "ORDER_CREATED" -> objectMapper.treeToValue(
                    envelope.payload(), OrderCreated.class);
            case "ORDER_CANCELLED" -> objectMapper.treeToValue(
                    envelope.payload(), OrderCancelled.class);
            case "PAYMENT_RECEIVED" -> objectMapper.treeToValue(
                    envelope.payload(), PaymentReceived.class);
            default -> throw new IllegalArgumentException(
                    "Unknown payloadType: " + envelope.payloadType());
        };
    }
}
```

Sau bước mapping, writer classifier chỉ cần phân loại subtype Java. Cách tách này giữ việc đọc/deserialize dữ liệu khỏi quyết định writer đích.

Không dùng class name tùy ý từ payload để gọi `Class.forName()` hoặc bật polymorphic deserialization rộng cho dữ liệu không tin cậy. Discriminator phải được ánh xạ qua danh sách type được phép.

## 11. Khi nào nên phân loại trước ở processor?

Nếu payload đầu vào là một envelope hoặc kiểu chung, `ItemProcessor` có thể chuyển nó thành subtype cụ thể trước khi writer chạy. Sau đó classifier writer định tuyến theo runtime type.

```java
@Bean
public ItemProcessor<EventEnvelope, DomainEvent> eventProcessor(
        EventPayloadMapper payloadMapper) {
    return payloadMapper::toDomainEvent;
}
```

Luồng:

```text
ItemReader<EventEnvelope>
          |
          v
ItemProcessor<EventEnvelope, DomainEvent>
          |
          v
ClassifierCompositeItemWriter<DomainEvent>
          |
          +--> OrderCreated writer
          +--> OrderCancelled writer
          +--> PaymentReceived writer
```

Processor phù hợp để parse discriminator, chuẩn hóa payload và validate dữ liệu. Classifier writer tập trung vào quyết định đích ghi. Phân chia trách nhiệm giúp test từng phần độc lập.

Nếu việc phân loại không cần biến đổi object, có thể classifier trực tiếp dựa vào trường hoặc subtype hiện có. Không cần tạo processor chỉ để chuyển một enum sang writer nếu classifier có thể làm điều đó đơn giản.

## 12. Fallback cho payload type không được hỗ trợ

Không nên bỏ qua loại payload lạ một cách âm thầm. Có hai chiến lược thường gặp:

**Fail fast:** ném exception khi gặp subtype không được hỗ trợ. Phù hợp khi payload mới cho thấy schema contract đã thay đổi và cần cập nhật ứng dụng.

**Route đến quarantine/dead-letter writer:** lưu payload chưa hỗ trợ vào nơi cách ly để điều tra, nếu nghiệp vụ cho phép Job tiếp tục.

Ví dụ classifier có fallback:

```java
return event -> {
    if (event instanceof OrderCreated) {
        return orderCreatedAdapter;
    }
    if (event instanceof OrderCancelled) {
        return orderCancelledAdapter;
    }
    if (event instanceof PaymentReceived) {
        return paymentReceivedAdapter;
    }
    return unsupportedEventWriter;
};
```

Fallback writer nên ghi đủ thông tin để điều tra, chẳng hạn event ID, discriminator, source file, batch ID và lý do không hỗ trợ. Không ghi secret hoặc toàn bộ dữ liệu nhạy cảm vào log.

Nếu dùng fallback, cần quyết định kết quả Step có được xem là hoàn tất bình thường hay cần custom `ExitStatus` như `COMPLETED_WITH_UNSUPPORTED_PAYLOADS`. Theo dõi số lượng item vào quarantine và đặt ngưỡng nghiệp vụ nếu cần.

## 13. Classifier theo enum hoặc thuộc tính nghiệp vụ

Không phải payload nào cũng có subtype riêng. Có thể tất cả item cùng kiểu Java nhưng có thuộc tính `category` hoặc `destination`:

```java
public record TransactionPayload(
        String transactionId,
        TransactionType type,
        BigDecimal amount
) {
}

public enum TransactionType {
    DEPOSIT,
    WITHDRAWAL,
    FEE
}
```

Classifier có thể dựa vào enum:

```java
Classifier<TransactionPayload, ItemWriter<? super TransactionPayload>> classifier = payload ->
        switch (payload.type()) {
            case DEPOSIT -> depositWriter;
            case WITHDRAWAL -> withdrawalWriter;
            case FEE -> feeWriter;
        };
```

Cách này phù hợp khi cấu trúc payload giống nhau nhưng quy tắc ghi khác nhau theo category. Nếu type quyết định schema và field khác nhau, subtype Java thường thể hiện contract tốt hơn.

## 14. ClassifierCompositeItemWriter và CompositeItemWriter

Hai writer có tên gần nhau nhưng hành vi khác nhau:

| Nhu cầu | Writer phù hợp |
|---|---|
| Mỗi item ghi đến mọi đích | `CompositeItemWriter` |
| Mỗi item chọn một writer theo payload type | `ClassifierCompositeItemWriter` |
| Một số item cần ghi đến nhiều đích, số khác chỉ một đích | Classifier trả về một composite writer phù hợp cho từng nhóm, hoặc thiết kế routing riêng |
| Chọn processor theo loại input | `ClassifierCompositeItemProcessor` |

Không dùng `CompositeItemWriter` nếu mục tiêu là phân luồng loại payload, vì nó sẽ gọi tất cả delegate cho cùng chunk. Điều đó có thể khiến một payment bị ghi vào bảng order hoặc ngược lại.

## 15. ClassifierCompositeItemProcessor có vai trò gì?

`ClassifierCompositeItemProcessor<I, O>` là cơ chế tương tự ở giai đoạn process: classifier chọn `ItemProcessor` phù hợp cho item. Nó không chọn writer.

Ví dụ:

```java
ClassifierCompositeItemProcessor<DomainEvent, ProcessedEvent> processor =
        new ClassifierCompositeItemProcessorBuilder<DomainEvent, ProcessedEvent>()
                .classifier(event -> {
                    if (event instanceof OrderCreated) {
                        return orderCreatedProcessor;
                    }
                    if (event instanceof PaymentReceived) {
                        return paymentReceivedProcessor;
                    }
                    return defaultEventProcessor;
                })
                .build();
```

Chọn classifier processor khi mỗi payload type có quy tắc xử lý khác nhau. Chọn classifier writer khi mục tiêu là đưa item đã xử lý đến đúng đích ghi. Có thể dùng cả hai trong cùng Step nếu nghiệp vụ yêu cầu.

## 16. Đăng ký classifier writer trong Step

Sau khi tạo `ClassifierCompositeItemWriter`, truyền nó vào Step:

```java
@Bean
public Step routeDomainEventsStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<DomainEvent> eventReader,
        ItemProcessor<DomainEvent, DomainEvent> eventProcessor,
        ClassifierCompositeItemWriter<DomainEvent> eventWriter) {

    return new StepBuilder("routeDomainEventsStep", jobRepository)
            .<DomainEvent, DomainEvent>chunk(100, transactionManager)
            .reader(eventReader)
            .processor(eventProcessor)
            .writer(eventWriter)
            .build();
}
```

Spring Batch gọi classifier writer ở bước write của mỗi chunk. Reader và processor vẫn hoạt động theo contract bình thường. Nếu processor trả `null`, item bị filter và không được đưa đến writer.

Nếu các writer delegate có state như file writer, cần bảo đảm lifecycle `ItemStream` được quản lý. `ClassifierCompositeItemWriter` và builder có hỗ trợ stream tùy theo phiên bản Spring Batch; kiểm tra API đang dùng. Nếu delegate stream không được composite tự quản lý, đăng ký delegate bằng `.stream(...)` trên Step hoặc bọc lifecycle tường minh. Tránh gọi `open/update/close` hai lần cho cùng delegate.

## 17. Transaction khi định tuyến đến nhiều writer

Một chunk có thể chứa nhiều payload type nên trong một lần ghi, classifier writer có thể gọi nhiều delegate khác nhau. Transaction boundary vẫn do Step và `PlatformTransactionManager` quản lý.

Nếu các delegate ghi vào cùng database và cùng transaction, các thay đổi có thể rollback cùng chunk. Nhưng nếu một delegate ghi file, gửi HTTP hoặc publish message, transaction database không tự thu hồi side effect đó.

Ví dụ chunk gồm:

```text
[OrderCreated, PaymentReceived, OrderCancelled]
```

Classifier có thể gọi ba writer tương ứng. Nếu writer thanh toán ghi thành công rồi writer hủy đơn ném exception, chunk transaction có thể rollback những database operation tham gia cùng transaction. Side effect bên ngoài cần cơ chế riêng.

Không giả định mọi writer sẽ được commit nguyên tử chỉ vì được gọi từ cùng classifier composite. Nếu cần consistency giữa database và message/file, cân nhắc outbox, idempotency key hoặc tách publish thành Step riêng.

## 18. Retry, skip và idempotency

Khi một delegate lỗi, exception được trả về Step và fault-tolerance policy có thể retry hoặc skip tùy loại lỗi. Trong lần retry, classifier và writer có thể được gọi lại cho cùng item/chunk.

Các nguyên tắc:

- Classifier nên deterministic: cùng payload phải chọn cùng writer trong cùng phiên bản logic.
- Writer cần idempotent nếu side effect có thể được thực hiện nhiều lần.
- Dùng business key hoặc event ID để chống ghi trùng.
- Không skip lỗi routing không rõ nguyên nhân; payload không có writer thường là lỗi contract.
- Nếu fallback quarantine, ghi nhận số lượng và lý do để vận hành theo dõi.
- Không retry lỗi cấu hình như thiếu writer hoặc subtype không được hỗ trợ nếu retry không thể làm thay đổi kết quả.

Ví dụ cấu hình retry lỗi database tạm thời:

```java
return new StepBuilder("routeDomainEventsStep", jobRepository)
        .<DomainEvent, DomainEvent>chunk(100, transactionManager)
        .reader(eventReader)
        .writer(eventWriter)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
```

Chỉ cấu hình exception phù hợp với delegate thực tế. Không dùng `retry(Exception.class)` hoặc `skip(Exception.class)` rộng vì có thể che giấu lỗi mapping và routing.

## 19. Quản lý thứ tự và tính xác định

Classifier writer lựa chọn writer theo item. Khi một chunk có nhiều loại payload, không nên dựa vào thứ tự giữa các delegate để thiết lập quan hệ phụ thuộc nghiệp vụ.

Ví dụ không nên giả định `OrderCreated` luôn được ghi trước `PaymentReceived` chỉ vì nó xuất hiện trước trong chunk hoặc vì writer order được khai báo trước. Nếu payment cần order đã tồn tại, hãy:

- Sắp xếp và xử lý dữ liệu theo quy tắc rõ ràng trước khi write nếu có thể.
- Tách các loại event thành các Step có thứ tự.
- Dùng foreign key/retry/reconciliation phù hợp.
- Thiết kế writer để xử lý thứ tự đến không đảm bảo.

Classifier nên chỉ quyết định route. Nếu logic phụ thuộc thứ tự, đó là một yêu cầu điều phối khác cần được thể hiện tường minh.

## 20. Quan sát payload routing

Khi vận hành, cần biết mỗi loại payload được route đi đâu và có bao nhiêu item bị từ chối. Có thể ghi metric hoặc log trong classifier, nhưng tránh tạo side effect ảnh hưởng xử lý chính.

Các metric hữu ích:

- Số `OrderCreated` được chuyển đến order writer.
- Số `PaymentReceived` được chuyển đến payment writer.
- Số item vào fallback/quarantine.
- Số lỗi mapping discriminator.
- Số lỗi delegate theo loại payload.
- Thời gian ghi theo từng đích.

Với log, nên ghi event ID, payload type, JobExecution ID hoặc batch ID và đích ghi. Không log toàn bộ payload nếu có thông tin cá nhân, thông tin thanh toán hoặc dữ liệu nhạy cảm.

Có thể dùng `StepExecution` counters cho số item tổng thể, nhưng muốn thống kê theo payload type thì cần metric riêng hoặc listener/writer wrapper có nhãn type.

## 21. Kiểm thử classifier và writer routing

Nên kiểm thử classifier độc lập và kiểm thử writer composite với chunk có nhiều loại payload.

Ví dụ unit test classifier:

```java
@Test
void routesPaymentReceivedToPaymentWriter() {
    ItemWriter<DomainEvent> paymentWriter = chunk -> { };
    ItemWriter<DomainEvent> orderWriter = chunk -> { };

    Classifier<DomainEvent, ItemWriter<? super DomainEvent>> classifier = event ->
            event instanceof PaymentReceived ? paymentWriter : orderWriter;

    assertSame(paymentWriter, classifier.classify(
            new PaymentReceived(9001L, 1001L, new BigDecimal("25.00"))
    ));
}
```

Các trường hợp nên kiểm thử:

1. Mỗi subtype được route đến đúng delegate.
2. Chunk hỗn hợp được phân chia đúng theo payload type.
3. Payload type không được hỗ trợ đi đến fallback hoặc làm Step thất bại theo chính sách.
4. Discriminator không hợp lệ bị từ chối trước khi ghi.
5. Adapter từ chối subtype sai thay vì cast không an toàn.
6. Writer delegate nhận đúng item và đúng kiểu dữ liệu.
7. Delegate lỗi làm Step xử lý transaction/retry theo cấu hình.
8. Retry không tạo duplicate ở database, API hoặc broker.
9. Delegate triển khai `ItemStream` được open/update/close đúng lifecycle.
10. Job restart giữ nguyên routing logic và input version cần thiết.

Unit test classifier không chứng minh được transaction behavior. Cần integration test với JobRepository, transaction manager và resource thực tế để xác nhận rollback, retry, restart và side effect.

## 22. Những lỗi thường gặp

**Dùng CompositeItemWriter khi cần route theo type.** Composite writer gửi mọi item đến mọi delegate. Dùng `ClassifierCompositeItemWriter` khi mỗi item chọn một writer.

**So sánh class bằng tên chuỗi.** Rename class có thể làm routing hỏng. Dùng `instanceof`, enum hoặc registry allowlist.

**Không xử lý payload type lạ.** Classifier có thể ném exception hoặc route đến quarantine. Đừng để item bị bỏ qua không có dấu vết.

**Dùng cast không kiểm tra trong writer.** Một item sai subtype có thể gây `ClassCastException` trong lúc ghi. Dùng adapter kiểm tra kiểu.

**Cho phép discriminator chọn class tùy ý.** Dữ liệu bên ngoài không được quyết định class runtime bằng `Class.forName()` tùy tiện. Dùng mapping tường minh.

**Giả định các writer chạy theo thứ tự nghiệp vụ.** Routing không thay thế orchestration. Tách Step hoặc thiết kế dependency rõ ràng nếu thứ tự quan trọng.

**Cho rằng transaction của Step rollback được mọi đích.** File, HTTP và broker có thể giữ side effect. Dùng idempotency, outbox hoặc reconciliation.

**Quên lifecycle delegate.** Writer stateful cần `ItemStream` được đăng ký đúng. Kiểm tra composite và Step configuration.

## 23. Khi nào nên dùng ClassifierCompositeItemWriter?

Dùng `ClassifierCompositeItemWriter` khi chunk có thể chứa nhiều payload type và mỗi item cần được ghi đến một writer phù hợp. Định nghĩa một kiểu chung cho payload, viết classifier deterministic dựa trên subtype hoặc thuộc tính nghiệp vụ, rồi cấu hình writer delegate có kiểu tương thích.

Nếu payload đến từ JSON có discriminator, validate type bằng allowlist và deserialize thành subtype Java trước khi routing. Dùng adapter khi writer chuyên biệt cần generic type riêng. Xác định fallback cho type lạ, quản lý lifecycle của delegate stateful và bảo đảm writer idempotent khi retry/restart.

Nếu mọi item cần ghi đến tất cả đích, dùng `CompositeItemWriter`. Nếu cần chọn processor theo payload type, dùng `ClassifierCompositeItemProcessor`. Phân biệt đúng ba nhu cầu giúp pipeline dễ đọc, type-safe hơn và tránh ghi nhầm dữ liệu sang đích không phù hợp.
