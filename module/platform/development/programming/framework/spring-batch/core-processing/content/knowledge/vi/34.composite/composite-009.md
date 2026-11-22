# Route item theo loại

Trong Spring Batch, một step có thể đọc nhiều loại item trong cùng một luồng dữ liệu. Ví dụ, một file tích hợp chứa cả customer, order và payment; hoặc một API trả về nhiều event có cấu trúc khác nhau. Mỗi loại item có thể cần logic xử lý, validation và nơi ghi riêng.

**Routing** là việc phân loại từng item rồi chuyển nó đến đúng processor hoặc writer. Spring Batch hỗ trợ mẫu này qua `ClassifierCompositeItemProcessor` và `ClassifierCompositeItemWriter`. Cả hai dùng một `Classifier` để chọn delegate dựa trên item hiện tại.

Routing theo item khác với `CompositeItemProcessor`: composite processor chạy nhiều processor theo một chuỗi cho cùng item, còn classifier composite chọn một nhánh xử lý dựa trên loại item. Chọn đúng mẫu giúp pipeline dễ đọc, tránh những chuỗi `if/else` lớn và giữ cho logic từng loại dữ liệu độc lập.

## 1. Khi nào cần route item theo loại?

Hãy xem một nguồn dữ liệu có các bản ghi như sau:

```text
CUSTOMER,C001,Nguyen An
ORDER,O100,C001,250.00
PAYMENT,P900,O100,250.00
CUSTOMER,C002,Tran Binh
```

Một reader có thể chuyển mỗi dòng thành một object đầu vào chung, nhưng cách xử lý phụ thuộc loại bản ghi:

- `CUSTOMER`: kiểm tra thông tin khách hàng và cập nhật customer repository.
- `ORDER`: kiểm tra customer tồn tại, chuẩn hóa đơn hàng và lưu order.
- `PAYMENT`: kiểm tra trạng thái thanh toán và ghi payment ledger.

Nếu tất cả logic nằm trong một processor hoặc writer duy nhất, class đó sẽ phải biết mọi loại dữ liệu và chứa nhiều nhánh điều kiện. Khi thêm loại record mới, code cũ dễ bị ảnh hưởng.

Routing tách luồng theo loại:

```text
                    ItemReader
                        |
                        v
                Input item chung
                        |
                        v
                    Classifier
                  /     |      \
                 /      |       \
                v       v        v
          Customer   Order    Payment
          processor processor processor
                \      |       /
                 \     |      /
                  v    v     v
                Output item chung
                        |
                        v
                 Writer hoặc tiếp tục
```

Mỗi item được phân loại riêng. Những item khác loại vẫn có thể nằm trong cùng chunk và được xử lý qua các nhánh khác nhau.

## 2. Phân biệt routing với CompositeItemProcessor

Hai component có tên gần nhau nhưng mục đích khác nhau:

| Component | Cách hoạt động | Khi phù hợp |
|---|---|---|
| `CompositeItemProcessor` | Chạy các delegate processor lần lượt theo thứ tự cấu hình. Output của processor trước là input của processor sau. | Một item cần qua nhiều bước biến đổi chung, ví dụ validate → normalize → enrich. |
| `ClassifierCompositeItemProcessor` | Chọn một processor dựa trên item rồi chạy processor được chọn. | Mỗi loại item cần một nhánh xử lý khác nhau. |
| `ClassifierCompositeItemWriter` | Chọn writer phù hợp cho từng item. | Các loại output cần ghi vào bảng, file hoặc đích khác nhau. |

Ví dụ chuỗi xử lý chung:

```text
CustomerInput
     |
     v
ValidateProcessor
     |
     v
NormalizeProcessor
     |
     v
EnrichProcessor
     |
     v
Customer
```

Đây là `CompositeItemProcessor`, vì mọi item đều đi qua các bước theo cùng một thứ tự.

Ví dụ xử lý theo loại:

```text
InboundEvent
     |
     v
  Classifier
    /    \
   v      v
Customer  Order
Processor Processor
```

Đây là `ClassifierCompositeItemProcessor`, vì classifier chọn đúng một nhánh cho item.

Hai mẫu có thể kết hợp: classifier chọn processor theo loại, rồi processor được chọn có thể là một `CompositeItemProcessor` để chạy nhiều bước biến đổi bên trong nhánh đó.

## 3. Thiết kế kiểu dữ liệu đầu vào chung

Một cách dễ kiểm soát routing là dùng interface hoặc sealed interface làm kiểu đầu vào chung.

Ví dụ với Java hiện đại:

```java
public sealed interface InboundEvent
        permits CustomerCreated, OrderPlaced, PaymentReceived {
}

public record CustomerCreated(
        String customerId,
        String name,
        String email) implements InboundEvent {
}

public record OrderPlaced(
        String orderId,
        String customerId,
        BigDecimal amount) implements InboundEvent {
}

public record PaymentReceived(
        String paymentId,
        String orderId,
        BigDecimal amount) implements InboundEvent {
}
```

`InboundEvent` là kiểu chung mà reader trả về. Mỗi record có cấu trúc riêng, nhưng tất cả đều có thể đi qua cùng một step:

```java
ItemReader<InboundEvent> eventReader = ...;
```

Nếu dùng Java version chưa hỗ trợ sealed interface/record, có thể dùng interface thông thường và các class implement interface đó.

Một lựa chọn khác là dùng một DTO chung có trường `type`:

```java
public record IncomingRecord(
        String type,
        String recordId,
        Map<String, Object> payload) {
}
```

DTO chung hữu ích khi nguồn là JSON envelope hoặc message có discriminator. Tuy nhiên, `Map<String, Object>` làm giảm type safety và khiến việc chuyển đổi payload phức tạp hơn. Nếu cấu trúc từng loại rõ ràng, các class riêng thường dễ kiểm tra và bảo trì hơn.

## 4. Chọn loại item bằng discriminator

Classifier cần một quy tắc ổn định để xác định nhánh. Có thể dùng:

- Kiểu Java thực tế (`instanceof`, class metadata).
- Trường discriminator như `type`, `eventType`, `recordKind`.
- Mã nghiệp vụ hoặc prefix của record ID nếu đó là hợp đồng dữ liệu rõ ràng.
- Kết hợp nhiều trường khi một trường riêng lẻ không đủ phân biệt.

Ví dụ phân loại bằng Java type:

```java
Classifier<InboundEvent, String> eventTypeClassifier = event -> {
    if (event instanceof CustomerCreated) {
        return "CUSTOMER";
    }
    if (event instanceof OrderPlaced) {
        return "ORDER";
    }
    if (event instanceof PaymentReceived) {
        return "PAYMENT";
    }
    throw new IllegalArgumentException(
            "Unsupported event type: " + event.getClass().getName());
};
```

Ví dụ phân loại bằng discriminator:

```java
Classifier<IncomingRecord, String> recordTypeClassifier = record -> {
    return switch (record.type()) {
        case "CUSTOMER" -> "CUSTOMER";
        case "ORDER" -> "ORDER";
        case "PAYMENT" -> "PAYMENT";
        default -> throw new IllegalArgumentException(
                "Unsupported record type: " + record.type());
    };
};
```

Không nên suy đoán loại record từ một chuỗi tùy ý nếu format nguồn không quy định điều đó. Hãy validate discriminator ngay tại ranh giới đọc hoặc trong bước phân loại để dữ liệu không rõ loại không bị route nhầm.

## 5. Classifier là gì?

`Classifier<C, T>` là abstraction nhận một đối tượng đầu vào kiểu `C` và trả về một kết quả phân loại kiểu `T`:

```java
public interface Classifier<C, T> {
    T classify(C classifiable);
}
```

Classifier không bắt buộc phải trả về một chuỗi. Nó có thể trả về một processor, writer, strategy hoặc bất kỳ delegate nào phù hợp với mục tiêu routing.

Ví dụ classifier trả về tên nhánh:

```java
Classifier<InboundEvent, String> classifier = event -> {
    if (event instanceof CustomerCreated) return "customer";
    if (event instanceof OrderPlaced) return "order";
    if (event instanceof PaymentReceived) return "payment";
    throw new IllegalArgumentException("Unknown event");
};
```

Classifier trả về tên nhánh chỉ là một bước phân loại. `ClassifierCompositeItemProcessor` và `ClassifierCompositeItemWriter` thường dùng classifier trả trực tiếp delegate tương ứng để gọi xử lý.

Giữ classifier đơn giản, xác định và không có side effect. Không gọi API, ghi database hoặc thay đổi trạng thái nghiệp vụ trong `classify()`. Việc phân loại nên là một quyết định nhanh, có thể kiểm thử độc lập.

## 6. Route đến processor bằng ClassifierCompositeItemProcessor

`ClassifierCompositeItemProcessor<I, O>` chọn một `ItemProcessor` cho từng item đầu vào. Các processor được chọn phải tạo ra output tương thích với kiểu `O`.

Giả sử các event khác loại đều được chuyển thành một model chuẩn:

```java
public record NormalizedEvent(
        String eventId,
        String eventType,
        String aggregateId,
        String description) {
}
```

Các processor riêng:

```java
ItemProcessor<CustomerCreated, NormalizedEvent> customerProcessor = event ->
        new NormalizedEvent(
                event.customerId(),
                "CUSTOMER_CREATED",
                event.customerId(),
                "Customer " + event.name() + " created");

ItemProcessor<OrderPlaced, NormalizedEvent> orderProcessor = event ->
        new NormalizedEvent(
                event.orderId(),
                "ORDER_PLACED",
                event.orderId(),
                "Order amount " + event.amount());

ItemProcessor<PaymentReceived, NormalizedEvent> paymentProcessor = event ->
        new NormalizedEvent(
                event.paymentId(),
                "PAYMENT_RECEIVED",
                event.orderId(),
                "Payment amount " + event.amount());
```

Tạo classifier chọn processor:

```java
Classifier<InboundEvent, ItemProcessor<?, ? extends NormalizedEvent>> classifier = event -> {
    if (event instanceof CustomerCreated) {
        return customerProcessor;
    }
    if (event instanceof OrderPlaced) {
        return orderProcessor;
    }
    if (event instanceof PaymentReceived) {
        return paymentProcessor;
    }
    throw new IllegalArgumentException(
            "Unsupported event type: " + event.getClass().getName());
};

ClassifierCompositeItemProcessor<InboundEvent, NormalizedEvent> router =
        new ClassifierCompositeItemProcessor<>();
router.setClassifier(classifier);
```

Trong cấu hình Spring, có thể khai báo router thành bean và inject các delegate processor qua constructor/method parameter. Classifier đảm bảo `CustomerCreated` đi đến `customerProcessor`, `OrderPlaced` đi đến `orderProcessor` và `PaymentReceived` đi đến `paymentProcessor`.

Các delegate có input type khác nhau, vì vậy classifier phải chọn đúng processor cho đúng loại object. Nếu chọn nhầm, generic cast bên trong routing component có thể gây `ClassCastException` khi processor được gọi. Không nên dựa vào generic type để thay thế kiểm tra discriminator.

## 7. Route processor trong cấu hình Spring

Có thể khai báo từng processor thành bean riêng rồi kết hợp:

```java
@Bean
ItemProcessor<CustomerCreated, NormalizedEvent> customerCreatedProcessor() {
    return event -> new NormalizedEvent(
            event.customerId(),
            "CUSTOMER_CREATED",
            event.customerId(),
            event.name());
}

@Bean
ItemProcessor<OrderPlaced, NormalizedEvent> orderPlacedProcessor() {
    return event -> new NormalizedEvent(
            event.orderId(),
            "ORDER_PLACED",
            event.orderId(),
            event.amount().toPlainString());
}

@Bean
ClassifierCompositeItemProcessor<InboundEvent, NormalizedEvent> eventRouter(
        ItemProcessor<CustomerCreated, NormalizedEvent> customerCreatedProcessor,
        ItemProcessor<OrderPlaced, NormalizedEvent> orderPlacedProcessor) {

    ClassifierCompositeItemProcessor<InboundEvent, NormalizedEvent> router =
            new ClassifierCompositeItemProcessor<>();

    router.setClassifier(event -> {
        if (event instanceof CustomerCreated) {
            return customerCreatedProcessor;
        }
        if (event instanceof OrderPlaced) {
            return orderPlacedProcessor;
        }
        throw new IllegalArgumentException("Unsupported event: " + event);
    });

    return router;
}
```

Ví dụ rút gọn chỉ khai báo hai loại event; nếu có `PaymentReceived`, cần thêm processor và nhánh tương ứng. Trong ứng dụng lớn, có thể tách phần xây dựng classifier thành factory/configuration riêng để không làm cấu hình step phình to.

## 8. Kết hợp routing với CompositeItemProcessor

Một nhánh có thể cần nhiều bước xử lý tuần tự. Khi đó, tạo `CompositeItemProcessor` cho từng loại rồi để classifier chọn composite phù hợp.

Ví dụ:

```java
ItemProcessor<CustomerCreated, NormalizedEvent> customerPipeline =
        new CompositeItemProcessorBuilder<CustomerCreated, NormalizedEvent>()
                .delegates(
                        validateCustomerCreated,
                        normalizeCustomerCreated,
                        mapCustomerCreated)
                .build();

ItemProcessor<OrderPlaced, NormalizedEvent> orderPipeline =
        new CompositeItemProcessorBuilder<OrderPlaced, NormalizedEvent>()
                .delegates(
                        validateOrderPlaced,
                        normalizeOrderPlaced,
                        mapOrderPlaced)
                .build();
```

Sau đó classifier chọn `customerPipeline` hoặc `orderPipeline` theo loại event. Cấu trúc này giúp tách hai quyết định:

1. Chọn nhánh nào cho item?
2. Trong nhánh đó, item đi qua những transformation nào?

Đây là cách kết hợp phù hợp khi mỗi loại dữ liệu có một pipeline riêng nhưng output cuối cùng vẫn dùng chung một kiểu.

## 9. Route item đến writer bằng ClassifierCompositeItemWriter

Đôi khi processor chuẩn hóa dữ liệu nhưng output vẫn có nhiều loại và cần ghi vào các đích khác nhau. `ClassifierCompositeItemWriter<T>` chọn writer dựa trên từng item.

Ví dụ output chung:

```java
public sealed interface ExportRecord
        permits CustomerExport, OrderExport {
}

public record CustomerExport(
        String customerId,
        String name) implements ExportRecord {
}

public record OrderExport(
        String orderId,
        BigDecimal amount) implements ExportRecord {
}
```

Giả sử có hai writer chuyên biệt:

```java
ItemWriter<CustomerExport> customerExportWriter = ...;
ItemWriter<OrderExport> orderExportWriter = ...;
```

`ClassifierCompositeItemWriter<ExportRecord>` cần các delegate có kiểu nhận tương thích với kiểu item chung. Có thể tạo adapter để kiểm tra kiểu và chuyển chunk sang writer chuyên biệt:

```java
ItemWriter<ExportRecord> customerWriterAdapter = items -> {
    Chunk<CustomerExport> customerItems = new Chunk<>();
    for (ExportRecord item : items) {
        if (!(item instanceof CustomerExport customer)) {
            throw new IllegalArgumentException("Expected CustomerExport");
        }
        customerItems.add(customer);
    }
    customerExportWriter.write(customerItems);
};

ItemWriter<ExportRecord> orderWriterAdapter = items -> {
    Chunk<OrderExport> orderItems = new Chunk<>();
    for (ExportRecord item : items) {
        if (!(item instanceof OrderExport order)) {
            throw new IllegalArgumentException("Expected OrderExport");
        }
        orderItems.add(order);
    }
    orderExportWriter.write(orderItems);
};
```

Classifier chọn adapter:

```java
Classifier<ExportRecord, ItemWriter<? super ExportRecord>> writerClassifier = record -> {
    if (record instanceof CustomerExport) {
        return customerWriterAdapter;
    }
    if (record instanceof OrderExport) {
        return orderWriterAdapter;
    }
    throw new IllegalArgumentException(
            "Unsupported export record: " + record.getClass().getName());
};

ClassifierCompositeItemWriter<ExportRecord> routingWriter =
        new ClassifierCompositeItemWriter<>();
routingWriter.setClassifier(writerClassifier);
```

Adapter giữ type check ở một nơi và bảo vệ writer chuyên biệt khỏi nhận nhầm loại item. Với hệ thống nhiều loại record, có thể tạo adapter generic dùng `Class<T>` để kiểm tra/cast và chuyển đổi chunk.

## 10. Lưu ý về generic type khi route writer

Java generics không cho phép coi `ItemWriter<CustomerExport>` là `ItemWriter<ExportRecord>`. Đây là tính invariant của generic type. Dù `CustomerExport` là subtype của `ExportRecord`, writer chuyên biệt chỉ biết ghi `CustomerExport`, không thể an toàn nhận một `OrderExport`.

Vì vậy, khi dùng `ClassifierCompositeItemWriter<ExportRecord>`, các delegate cần nhận `ExportRecord` hoặc một supertype phù hợp. Adapter kiểm tra từng phần tử rồi chuyển sang `Chunk<CustomerExport>` hoặc `Chunk<OrderExport>` là một cách rõ ràng để giữ type safety ở ranh giới.

Tránh ép kiểu raw như:

```java
ItemWriter rawWriter = customerExportWriter;
```

Raw type bỏ qua kiểm tra compile-time và có thể đẩy lỗi sang runtime. Nếu buộc phải cast, hãy cô lập cast trong adapter nhỏ, có kiểm tra `instanceof` và test loại dữ liệu.

## 11. Khai báo routing writer trong step

Một step có thể dùng classifier writer như writer chính:

```java
@Bean
Step exportRecordsStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<ExportRecord> exportRecordReader,
        ItemProcessor<ExportRecord, ExportRecord> exportProcessor,
        ClassifierCompositeItemWriter<ExportRecord> routingWriter) {

    return new StepBuilder("exportRecordsStep", jobRepository)
            .<ExportRecord, ExportRecord>chunk(200, transactionManager)
            .reader(exportRecordReader)
            .processor(exportProcessor)
            .writer(routingWriter)
            .build();
}
```

Nếu delegate writer triển khai `ItemStream` hoặc `StepExecutionListener`, cần bảo đảm chúng được đăng ký với step để lifecycle callback được gọi. Một composite/router không nhất thiết tự động chuyển tiếp mọi lifecycle contract của delegate.

Ví dụ với writer stateful:

```java
return new StepBuilder("exportRecordsStep", jobRepository)
        .<ExportRecord, ExportRecord>chunk(200, transactionManager)
        .reader(exportRecordReader)
        .processor(exportProcessor)
        .writer(routingWriter)
        .stream(customerFileWriter)
        .stream(orderFileWriter)
        .build();
```

Đăng ký stream rõ ràng đặc biệt quan trọng với file writer cần `open`, `update` và `close` để lưu checkpoint. Nếu delegate không được mở/đóng đúng lifecycle, restart có thể không hoạt động hoặc tài nguyên không được giải phóng.

## 12. Route theo loại hay route theo điều kiện nghiệp vụ?

Classifier không nhất thiết phải dựa trên class. Nó có thể dựa trên một thuộc tính hoặc trạng thái nghiệp vụ.

Ví dụ:

```java
Classifier<Payment, ItemWriter<? super Payment>> paymentWriterClassifier = payment -> {
    return switch (payment.status()) {
        case SETTLED -> settledPaymentWriter;
        case REFUNDED -> refundedPaymentWriter;
        case PENDING -> pendingPaymentWriter;
    };
};
```

Routing theo loại phù hợp khi cấu trúc hoặc handler khác nhau theo loại record. Routing theo trạng thái phù hợp khi cùng một kiểu object cần xử lý khác nhau theo trạng thái.

Nếu điều kiện phân loại phụ thuộc vào truy vấn hoặc logic phức tạp, nên tách thành một policy/service thuần để kiểm thử riêng. Tránh nhúng các lời gọi I/O vào classifier vì classifier có thể được gọi cho từng item và làm tăng độ trễ/khó kiểm soát retry.

## 13. Xử lý loại item không được hỗ trợ

Một classifier cần định nghĩa rõ hành vi khi gặp loại không biết. Có ba chiến lược phổ biến:

**Fail fast:** ném exception và làm step thất bại. Dùng khi loại không biết cho thấy dữ liệu hoặc schema version không được hỗ trợ.

```java
default -> throw new UnsupportedRecordTypeException(record.type());
```

**Route to rejected writer:** chuyển item sang nơi lưu dữ liệu không được hỗ trợ để đội vận hành điều tra. Cách này cần giữ raw payload, source reference và lý do reject.

**Ignore có kiểm soát:** chỉ dùng khi hợp đồng nguồn cho phép bỏ qua loại event nhất định và việc bỏ qua được ghi nhận. Không dùng default no-op nếu điều đó có thể làm mất dữ liệu âm thầm.

Không nên route mọi loại không biết sang writer thành công mặc định. Một loại mới xuất hiện có thể là thay đổi schema quan trọng; bỏ qua nó có thể làm batch hoàn tất nhưng thiếu dữ liệu.

## 14. Phân biệt lỗi routing với skip

Không tìm được delegate là lỗi cấu hình/logic routing, không tự động là skip. Nếu classifier ném exception, step xử lý nó theo fault tolerance policy của step.

Ví dụ:

```java
.faultTolerant()
.skip(InvalidCustomerRecordException.class)
.skipLimit(100)
```

Nếu classifier ném `UnsupportedRecordTypeException`, exception chỉ được skip nếu được cấu hình phù hợp. Tuy nhiên, không nên đưa lỗi classifier vào skip policy chỉ để job tiếp tục; hãy xác định đây có phải lỗi riêng của một item và nghiệp vụ có chấp nhận loại bỏ hay không.

Với dữ liệu không biết loại, thường nên ghi rejected item có đầy đủ payload và nguyên nhân. Với lỗi classifier do thiếu delegate bean hoặc cấu hình sai, nên làm step thất bại để sửa lỗi triển khai.

## 15. Filter sau khi route processor

Processor được chọn vẫn có thể trả `null` để filter item. Khi đó item đã được phân loại và xử lý trong nhánh, nhưng không có output đưa đến writer.

Ví dụ:

```java
ItemProcessor<CustomerCreated, NormalizedEvent> customerProcessor = event -> {
    if (event.email() == null || event.email().isBlank()) {
        return null; // Chỉ filter nếu đây là quy tắc nghiệp vụ được chấp nhận.
    }
    return normalize(event);
};
```

Nếu email bắt buộc và thiếu email là lỗi dữ liệu, nên ném `InvalidCustomerException` thay vì filter. Điều đó cho phép skip policy và `SkipListener` ghi nhận item lỗi.

Classifier không thay đổi semantics của processor. `null` từ processor vẫn là filter; exception vẫn được xử lý theo retry/skip/fail policy của step.

## 16. Routing và transaction boundary

Các nhánh writer thường được gọi trong cùng chunk transaction của step. Nếu các writer cùng ghi vào một database và tham gia cùng transaction manager, transaction có thể rollback các thay đổi database khi một delegate writer thất bại.

Tuy nhiên, nếu routing writer gửi dữ liệu tới nhiều loại tài nguyên:

- Database A.
- Database B.
- File system.
- HTTP API hoặc message broker.

thì một transaction local không tự bảo đảm tất cả tài nguyên commit/rollback nguyên tử. Ví dụ writer A đã ghi file, writer B ghi database rồi phát sinh lỗi; transaction database có thể rollback nhưng file đã được ghi không tự động xóa.

Các cách giảm rủi ro:

- Route tới writer cùng transaction resource khi cần atomicity.
- Dùng staging file rồi publish sau khi database transaction hoàn tất.
- Dùng outbox để phát event sau commit.
- Dùng idempotency key cho API/broker.
- Có quy trình reconciliation cho các nhánh không thể rollback cùng nhau.

Routing giúp tách logic đích ghi, nhưng không tạo distributed transaction.

## 17. Thứ tự ghi và tính nhất quán

Một chunk có thể chứa nhiều loại item. Classifier writer sẽ chuyển từng item đến delegate tương ứng. Không nên dựa vào thứ tự gọi delegate writer nếu thứ tự đó không được quy định trong hợp đồng của component/phiên bản đang dùng.

Ví dụ chunk:

```text
Customer C1
Order O1
Customer C2
Payment P1
Order O2
```

Nếu dữ liệu được nhóm theo writer, thứ tự ghi giữa các loại có thể khác với thứ tự ban đầu. Điều này có thể ảnh hưởng khi:

- Một writer phụ thuộc dữ liệu do writer khác tạo.
- File output phải giữ nguyên thứ tự nguồn.
- Sự kiện cần được phát theo thứ tự aggregate.
- Consumer dựa vào thứ tự record để xử lý.

Nếu thứ tự toàn cục là yêu cầu, hãy dùng một writer duy nhất có logic dispatch theo thứ tự, hoặc chia flow thành các step có thứ tự rõ ràng. Nếu mỗi item độc lập, routing theo delegate thường phù hợp hơn.

## 18. Khi nào nên tách thành nhiều step thay vì routing trong một step?

Routing theo item phù hợp khi các loại record cùng thuộc một nguồn và cần xử lý trong cùng vòng đời chunk. Nhưng nếu các loại cần cấu hình transaction, checkpoint, retry, skip hoặc lịch chạy khác nhau, nhiều step có thể dễ vận hành hơn.

| Nhu cầu | Lựa chọn phù hợp |
|---|---|
| Mỗi item chọn một processor trong cùng chunk | `ClassifierCompositeItemProcessor`. |
| Mỗi output item chọn writer riêng trong cùng step | `ClassifierCompositeItemWriter`. |
| Mỗi loại có chunk size, retry/skip policy riêng | Tách thành các step riêng hoặc phân tách input trước. |
| Mỗi loại cần job flow riêng | Conditional flow hoặc nhiều job/step. |
| Cần xử lý đồng thời các luồng độc lập | Partitioning hoặc split flow sau khi phân chia dữ liệu. |
| Cần giữ thứ tự toàn cục giữa các loại | Một writer có dispatch tuần tự hoặc một pipeline có thứ tự rõ. |

Không nên dùng classifier để gom mọi logic khác biệt vào một step nếu các nhánh có yêu cầu vận hành hoàn toàn khác nhau. Tách step giúp có status, metrics, restart boundary và cấu hình fault tolerance độc lập.

## 19. Routing bằng map classifier

Khi số loại lớn, một map từ type đến delegate có thể gọn hơn nhiều nhánh `if/else`. Có thể dùng `SubclassClassifier` hoặc một `Classifier` tự viết tra cứu map.

Ví dụ tự tạo classifier dựa trên class:

```java
Map<Class<?>, ItemProcessor<?, ? extends NormalizedEvent>> processors =
        new HashMap<>();
processors.put(CustomerCreated.class, customerProcessor);
processors.put(OrderPlaced.class, orderProcessor);
processors.put(PaymentReceived.class, paymentProcessor);

Classifier<InboundEvent, ItemProcessor<?, ? extends NormalizedEvent>> classifier = event -> {
    ItemProcessor<?, ? extends NormalizedEvent> processor =
            processors.get(event.getClass());

    if (processor == null) {
        throw new UnsupportedRecordTypeException(
                event.getClass().getName());
    }
    return processor;
};
```

Tra cứu `event.getClass()` chỉ khớp class chính xác. Nếu có subclass/proxy, hãy quyết định có muốn tìm theo superclass/interface hay không. `SubclassClassifier` có thể hữu ích khi muốn phân loại theo cây kế thừa; cần cấu hình default value hoặc hành vi không tìm thấy rõ ràng.

Map classifier nên được tạo bất biến sau khi cấu hình để tránh một thread thay đổi delegate map trong lúc step đang chạy.

## 20. Routing theo enum hoặc discriminator đã chuẩn hóa

Nếu item là một DTO chung, nên parse chuỗi type thành enum sớm:

```java
public enum RecordType {
    CUSTOMER,
    ORDER,
    PAYMENT
}

public record IncomingRecord(
        RecordType type,
        String id,
        String payload) {
}
```

Classifier có thể dùng switch expression:

```java
Classifier<IncomingRecord, RecordHandler> handlerClassifier = record ->
        switch (record.type()) {
            case CUSTOMER -> customerHandler;
            case ORDER -> orderHandler;
            case PAYMENT -> paymentHandler;
        };
```

Khi parse `type` từ String, cần xử lý giá trị null/không nhận diện trước khi tạo enum. Nếu parse enum thất bại, có thể reject record hoặc fail job theo hợp đồng. Đừng gán mặc định một loại bất kỳ chỉ để tránh exception.

## 21. Classifier và tính idempotent của delegate

Routing có thể khiến một item đi vào một delegate cụ thể, nhưng retry/restart vẫn có thể gọi delegate nhiều lần nếu transaction rollback hoặc step được chạy lại.

Ví dụ payment event được route tới `paymentWriter`. Nếu writer gọi API đối tác rồi timeout, lần retry có thể gửi lại payment. Classifier không biết API đã xử lý request hay chưa.

Delegate cần được thiết kế theo semantics của nguồn/đích:

- Database: unique key, upsert hoặc kiểm tra trạng thái đã xử lý.
- HTTP API: idempotency key ổn định theo event ID.
- Message broker: transactional outbox hoặc deduplication key.
- File: output riêng theo batch/partition và checkpoint writer.
- External side effect: lưu trạng thái/đối soát nếu kết quả request không xác định.

Idempotency key nên dựa trên identity nghiệp vụ ổn định, không tạo UUID mới mỗi lần retry. Ví dụ `paymentId` hoặc `eventId` có thể dùng để phát hiện lần xử lý lặp.

## 22. Đăng ký delegate stream và listener

Composite/routing component thường chỉ cung cấp contract chính của nó, ví dụ `ItemProcessor` hoặc `ItemWriter`. Delegate bên trong có thể triển khai thêm `ItemStream` hoặc listener interface.

Nếu delegate writer là `FlatFileItemWriter`, nó cần được mở, cập nhật state và đóng theo lifecycle của step. Nếu composite không chuyển tiếp `ItemStream`, hãy đăng ký delegate bằng `.stream(...)` trong cấu hình step.

Tương tự, nếu delegate cần `StepExecutionListener`, `ChunkListener` hoặc listener khác, hãy xác nhận lifecycle callback được đăng ký. Không giả định Spring Batch tự tìm mọi object nằm sâu bên trong một classifier.

Ví dụ:

```java
return new StepBuilder("routeAndWriteStep", jobRepository)
        .<InboundEvent, ExportRecord>chunk(100, transactionManager)
        .reader(eventReader)
        .processor(eventRouter)
        .writer(routingWriter)
        .stream(customerFileWriter)
        .stream(orderFileWriter)
        .listener(stepSummaryListener)
        .build();
```

Các delegate cần được inject và đăng ký đúng instance mà classifier đang sử dụng. Nếu classifier tạo writer mới mỗi lần `classify`, step không thể quản lý lifecycle hoặc checkpoint nhất quán cho các instance đó.

## 23. Theo dõi số item theo từng nhánh

Các counter chuẩn của `StepExecution` cung cấp tổng số item đọc, filter, write và skip. Chúng không tự động cho biết mỗi loại item đã đi qua nhánh nào.

Có thể bổ sung metric theo loại:

- `routed.customer.count`
- `routed.order.count`
- `routed.payment.count`
- `routed.unknown.count`
- Thời gian xử lý theo processor.
- Số lỗi theo delegate/exception type.

Không nên tạo metric tag có cardinality cao như customer ID, order ID hoặc payment ID. Dùng loại record và kết quả làm tag; lưu business key trong log có correlation ID hoặc bảng audit.

Có thể tăng counter ngay trong classifier, nhưng classifier nên thuần và nhanh. Một cách khác là dùng wrapper processor/decorator ghi metric khi delegate được gọi, hoặc listener/observer ở boundary phù hợp. Đảm bảo metric không làm thay đổi kết quả nghiệp vụ nếu metrics backend tạm thời lỗi.

## 24. Kiểm thử classifier độc lập

Classifier là logic thuần nên dễ kiểm thử riêng. Test cần bao phủ mọi loại được hỗ trợ và loại không được hỗ trợ.

```java
@Test
void classifiesEachSupportedEventType() {
    assertThat(classifier.classify(
            new CustomerCreated("C001", "An", "an@example.com")))
            .isSameAs(customerProcessor);

    assertThat(classifier.classify(
            new OrderPlaced("O001", "C001", new BigDecimal("20.00"))))
            .isSameAs(orderProcessor);
}

@Test
void rejectsUnsupportedEventType() {
    InboundEvent unsupported = createUnsupportedEventForTest();

    assertThatThrownBy(() -> classifier.classify(unsupported))
            .isInstanceOf(UnsupportedRecordTypeException.class);
}
```

Với sealed interface, compiler có thể giúp phát hiện khi thêm subtype mới trong một switch expression exhaustive. Nếu dùng interface mở hoặc discriminator String, test cần xác nhận default branch hoạt động.

## 25. Kiểm thử ClassifierCompositeItemProcessor

Test processor router cần xác nhận item được chuyển đến đúng delegate và output đúng loại/chuyển đổi.

```java
@Test
void routesCustomerAndOrderToDifferentProcessors() throws Exception {
    NormalizedEvent customerOutput = router.process(
            new CustomerCreated("C001", "Nguyen An", "an@example.com"));

    NormalizedEvent orderOutput = router.process(
            new OrderPlaced("O001", "C001", new BigDecimal("20.00")));

    assertThat(customerOutput.eventType()).isEqualTo("CUSTOMER_CREATED");
    assertThat(orderOutput.eventType()).isEqualTo("ORDER_PLACED");
}
```

Ngoài output, nên dùng mock/spy để xác nhận processor đúng được gọi một lần và processor nhánh khác không được gọi. Test loại không hỗ trợ phải xác nhận exception phù hợp.

Nếu delegate processor có side effect, hãy kiểm tra routing không gọi nhầm delegate và retry không tạo side effect lặp. Tốt nhất processor nên tập trung biến đổi dữ liệu, còn I/O được đặt ở writer hoặc service có idempotency.

## 26. Kiểm thử ClassifierCompositeItemWriter

Writer router cần xác nhận mỗi item đi tới đúng writer. Ví dụ chunk trộn nhiều loại:

```text
CustomerExport C001
OrderExport O100
CustomerExport C002
OrderExport O101
```

Test nên xác nhận:

- Customer writer chỉ nhận `CustomerExport`.
- Order writer chỉ nhận `OrderExport`.
- Không có item bị mất hoặc ghi hai lần.
- Writer nhận chunk rỗng hay không được xử lý đúng theo semantics của component/version.
- Loại không hỗ trợ gây lỗi hoặc được route vào rejected writer theo thiết kế.
- Exception từ một delegate được truyền lên để step áp dụng transaction/fault tolerance.

Có thể dùng `ItemWriter` mock để capture các chunk được chuyển đến từng delegate. Với writer adapter có cast, cần test cả trường hợp adapter nhận nhầm item để bảo đảm lỗi được phát hiện rõ ràng.

## 27. Kiểm thử tích hợp routing trong chunk step

Unit test classifier không chứng minh toàn bộ step hoạt động đúng. Integration test nên chạy job/step với một nguồn chứa nhiều loại record và kiểm tra các output tương ứng.

Một test tích hợp nên xác nhận:

1. Reader tạo đúng subtype hoặc discriminator cho từng record.
2. Classifier chọn đúng processor.
3. Processor output có kiểu/metadata mong đợi.
4. Writer router chuyển item đến đúng delegate.
5. Tất cả writer/stream được mở và đóng đúng lifecycle.
6. Transaction rollback khi delegate writer thất bại theo resource transaction.
7. Skip/retry được áp dụng đúng cho loại exception đã cấu hình.
8. Counter/metric phản ánh đúng số item từng loại.
9. Restart không ghi trùng hoặc mất item.

Nếu delegate ghi vào nhiều resource khác nhau, test cần xác nhận hành vi khi một resource thành công và resource khác thất bại. Không giả định transaction database tự hoàn tác file hoặc HTTP call.

## 28. Các lỗi thường gặp khi route item

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `ClassCastException` trong processor | Classifier chọn delegate có input type khác item thực tế. | Kiểm tra subtype/discriminator và giữ adapter type-safe. |
| Item đi sai writer | Mapping discriminator sai hoặc default route quá rộng. | Chuẩn hóa type trước routing và test mọi nhánh. |
| Loại mới bị bỏ qua âm thầm | Default delegate là no-op hoặc filter không ghi nhận. | Fail fast hoặc route rejected với audit. |
| Một item được xử lý nhiều nhánh | Dùng nhiều `if` độc lập thay vì chọn đúng một delegate. | Dùng switch/else-if hoặc classifier trả một delegate duy nhất. |
| Processor sau không chạy | Một processor trong chain trả `null` và filter item. | Phân biệt composite chain với classifier routing và kiểm tra filter. |
| Writer không restart được | Delegate `ItemStream` chưa được đăng ký với step. | Đăng ký `.stream(delegate)` và giữ tên/resource ổn định. |
| Listener delegate không được gọi | Listener nằm trong composite nhưng chưa đăng ký. | Đăng ký listener rõ ràng ở step hoặc dùng wrapper chuyển tiếp. |
| Ghi một phần sang nhiều hệ thống | Các delegate dùng resource/transaction manager khác nhau. | Dùng outbox, staging, idempotency và reconciliation. |
| Thứ tự output thay đổi | Writer router nhóm/gọi delegate theo cách không bảo toàn thứ tự toàn cục. | Không phụ thuộc thứ tự ngầm; dùng một writer tuần tự nếu thứ tự là yêu cầu. |
| Metric tăng sai | Đếm trong classifier nhiều lần hoặc khi retry. | Định nghĩa metric là attempt hay item cuối cùng và đặt tại boundary phù hợp. |
| Cấu hình step quá phức tạp | Mỗi loại có retry/skip/chunk policy riêng nhưng bị gom chung. | Tách thành các step hoặc job flow riêng. |

## 29. Quy trình thiết kế routing theo loại

Khi triển khai routing, hãy xác định các quyết định theo thứ tự:

1. **Định nghĩa loại item:** subtype, enum discriminator hay field trong payload?
2. **Xác định output contract:** các nhánh có cùng output type hay mỗi nhánh có output riêng?
3. **Chọn vị trí routing:** trước processor, sau processor hay tại writer?
4. **Chọn component:** `ClassifierCompositeItemProcessor`, `ClassifierCompositeItemWriter` hoặc custom router.
5. **Tạo delegate:** mỗi nhánh có một processor/writer rõ trách nhiệm và kiểu dữ liệu phù hợp.
6. **Xử lý loại không biết:** fail, reject hoặc ignore có audit theo hợp đồng nghiệp vụ.
7. **Bảo vệ generic type:** dùng interface chung hoặc adapter có kiểm tra type; tránh raw cast.
8. **Đăng ký lifecycle:** bảo đảm delegate `ItemStream` và listener được step quản lý.
9. **Xác định transaction:** kiểm tra các delegate dùng chung transaction resource hay cần outbox/staging.
10. **Xác định thứ tự:** nếu output cần giữ thứ tự nguồn, không dựa vào thứ tự gọi delegate ngầm.
11. **Bảo đảm idempotency:** retry/restart không tạo side effect trùng.
12. **Đo lường:** theo dõi số item và lỗi theo nhánh mà không tạo metric cardinality cao.
13. **Kiểm thử:** test classifier, từng delegate, router writer và toàn bộ chunk step.

## 30. Những điểm cần ghi nhớ

- Routing chọn processor hoặc writer theo từng item; nó không phải chuỗi transformation tuần tự.
- `CompositeItemProcessor` chạy tất cả delegate theo thứ tự; `ClassifierCompositeItemProcessor` chọn một delegate theo classifier.
- `ClassifierCompositeItemWriter` chọn writer phù hợp với từng output item.
- `Classifier` là logic phân loại thuần, nên dựa trên subtype hoặc discriminator rõ ràng và tránh I/O/side effect.
- Các nhánh processor có thể nhận subtype khác nhau nhưng nên tạo output contract chung nếu pipeline cần một kiểu output.
- Generic type của Java invariant; `ItemWriter<Subtype>` không thể tự động thay thế `ItemWriter<Supertype>`. Dùng adapter có kiểm tra kiểu khi cần.
- Loại không hỗ trợ cần được fail, reject hoặc ignore có audit; không để default no-op làm mất dữ liệu âm thầm.
- Có thể kết hợp classifier với `CompositeItemProcessor` để mỗi nhánh có pipeline tuần tự riêng.
- Delegate `ItemStream`/listener cần được đăng ký với step nếu composite không chuyển tiếp lifecycle.
- Routing trong một chunk không tạo distributed transaction; nhiều resource cần outbox, staging, idempotency hoặc reconciliation.
- Không giả định thứ tự gọi delegate writer bảo toàn thứ tự toàn cục của input.
- Nếu các loại cần chunk size, retry/skip hoặc restart policy khác nhau, cân nhắc tách thành step riêng.
- Test mọi nhánh, loại không biết, filter, writer failure, transaction, lifecycle và restart.

Route item theo loại giúp một step xử lý nhiều dạng dữ liệu mà vẫn giữ logic từng loại độc lập. Hãy xác định discriminator ổn định, chọn đúng một delegate cho mỗi item, dùng kiểu dữ liệu chung hoặc adapter có kiểm tra type, và làm rõ hành vi với loại không hỗ trợ. Khi delegate được quản lý đúng lifecycle, transaction và idempotency, classifier routing trở thành cách tổ chức pipeline dễ mở rộng và vận hành trong Spring Batch.
