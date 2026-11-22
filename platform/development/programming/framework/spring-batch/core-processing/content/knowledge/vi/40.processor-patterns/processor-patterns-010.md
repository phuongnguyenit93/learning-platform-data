# Processor retry và idempotency trong Spring Batch

Trong chunk-oriented Step, một item có thể được xử lý nhiều lần. Điều này có thể xảy ra khi processor ném exception tạm thời và Spring Batch retry, khi chunk rollback, hoặc khi Job được restart từ checkpoint. Nếu processor chỉ biến đổi dữ liệu trong bộ nhớ, việc chạy lại thường không gây vấn đề. Nhưng nếu processor gọi API, cập nhật database, gửi message hoặc tạo side effect khác, lần chạy lại có thể thực hiện cùng một hành động nhiều lần.

Hai khái niệm cần hiểu cùng nhau là **retry** và **idempotency**:

- Retry là cơ chế thử lại một thao tác sau lỗi được xem là có thể phục hồi.
- Idempotency là thuộc tính bảo đảm việc thực hiện cùng một thao tác nhiều lần không làm thay đổi kết quả nghiệp vụ sau lần đầu.

Retry giúp vượt qua lỗi tạm thời. Idempotency giúp xử lý an toàn khi cùng một item được thực hiện lại. Retry mà không có idempotency có thể nhân đôi side effect; idempotency mà không có retry thì thao tác có thể an toàn nhưng vẫn thất bại khi hệ thống tạm thời không sẵn sàng.

Trong Spring Batch, processor nên ưu tiên là một phép biến đổi thuần: nhận input, kiểm tra và trả output mới, không tạo side effect. Nếu nghiệp vụ bắt buộc cần gọi hệ thống ngoài, phải dùng khóa idempotency ổn định, xác định transaction boundary và kiểm thử các tình huống rollback/retry/restart.

Bài học này trình bày lifecycle của processor, nguyên nhân processor được gọi lại, cách phân loại exception, cấu hình retry/backoff/skip, thiết kế processor deterministic, idempotency cho database và API, inbox/outbox, quan hệ với chunk transaction, cùng cách kiểm thử.

## 1. Processor nằm ở đâu trong chunk lifecycle?

Một chunk-oriented Step đọc item, gọi processor nếu được cấu hình, gom output rồi chuyển chunk cho writer. Transaction thường bao quanh việc xử lý chunk theo cấu hình của Step.

~~~mermaid
flowchart TD
    A["Bắt đầu chunk transaction"] --> B["ItemReader đọc item"]
    B --> C["ItemProcessor xử lý item"]
    C --> D{"Processor trả kết quả?"}
    D -->|Item| E["Thêm output vào chunk"]
    D -->|null| F["Filter item"]
    E --> G{"Đã đủ chunk hoặc EOF?"}
    F --> G
    G -->|Chưa| B
    G -->|Đủ| H["ItemWriter ghi chunk"]
    H --> I["Commit transaction"]
~~~

Processor có interface đơn giản:

~~~java
public interface ItemProcessor<I, O> {
    O process(I item) throws Exception;
}
~~~

Trong đó:

- I là kiểu item đầu vào từ reader.
- O là kiểu item đầu ra cho writer.
- Trả về một object O để tiếp tục pipeline.
- Trả về null để filter item, tức item không được chuyển tới writer.
- Ném exception để báo lỗi xử lý.

Processor không điều khiển commit. Transaction và retry/skip policy thuộc Step. Tuy nhiên, processor chạy trong luồng xử lý item của Step nên thiết kế của nó phải tương thích với rollback và khả năng gọi lại.

## 2. Vì sao processor có thể được gọi nhiều lần?

Một processor không nên giả định mỗi item chỉ được gọi đúng một lần. Các tình huống phổ biến gồm:

1. Processor ném exception tạm thời và Step retry item.
2. Writer thất bại khiến chunk rollback; tùy cấu hình và reader, các item trong chunk có thể được xử lý lại.
3. Một lần retry của chunk làm framework thực hiện lại phần xử lý cần thiết.
4. Step thất bại và Job được restart từ checkpoint; item chưa được commit có thể được đọc/xử lý lại.
5. Người vận hành chạy lại một JobInstance hoặc tạo JobInstance mới trên cùng nguồn nghiệp vụ.
6. Nguồn phát lại cùng business event hoặc đưa cùng message vào batch nhiều lần.

Trong fault-tolerant Step, Spring Batch có thể buffer item đã đọc để dùng lại khi rollback, nhưng việc processor có được gọi lại và thời điểm gọi lại phụ thuộc loại reader, transaction và cấu hình. Quy tắc thiết kế an toàn là không dựa vào giả định processor chỉ chạy một lần.

Ví dụ một processor gọi API để tạo vận đơn. API tạo thành công nhưng response timeout. Spring Batch nhìn thấy exception và retry. Nếu lần gọi thứ hai không có idempotency key, hệ thống vận chuyển có thể tạo hai vận đơn cho cùng một đơn hàng.

Một processor an toàn cần xử lý được việc nhận lại cùng item mà không tạo thêm hiệu ứng nghiệp vụ ngoài dự kiến.

## 3. Retry và idempotency giải quyết hai vấn đề khác nhau

| Khái niệm | Câu hỏi được trả lời | Mục tiêu |
|---|---|---|
| Retry | Khi thao tác lỗi tạm thời, có nên thử lại không? | Tăng khả năng hoàn tất |
| Idempotency | Nếu thao tác được gọi lại, kết quả có bị nhân đôi không? | Bảo vệ tính đúng đắn |
| Deduplication | Đây có phải cùng một event đã xử lý không? | Nhận diện lần giao trùng |
| Restart | Job nên tiếp tục từ checkpoint nào? | Tiếp tục batch sau failure |

Retry là policy về thời điểm và số lần thực hiện lại. Idempotency là thuộc tính của thao tác hoặc workflow. Deduplication thường dựa vào một khóa ổn định để nhận ra event đã được áp dụng. Restart dùng metadata của Spring Batch để khôi phục tiến độ.

Các cơ chế này bổ trợ cho nhau nhưng không thay thế nhau. ExecutionContext không tự bảo đảm side effect bên ngoài chỉ xảy ra một lần. Một idempotency key cũng không cho reader biết cần tiếp tục đọc từ đâu.

## 4. Processor nên là phép biến đổi thuần

Một processor thuần chỉ dùng input và cấu hình đã được xác định để tạo output. Nó không gọi hệ thống ngoài, không ghi database và không sửa trạng thái dùng chung.

Ví dụ:

~~~java
public record RawOrder(
    String orderId,
    String customerId,
    BigDecimal amount,
    String currency
) {
}

public record NormalizedOrder(
    String orderId,
    String customerId,
    BigDecimal amount,
    String currency,
    boolean highValue
) {
}
~~~

Processor:

~~~java
public final class NormalizeOrderProcessor
        implements ItemProcessor<RawOrder, NormalizedOrder> {

    private final BigDecimal highValueLimit;

    public NormalizeOrderProcessor(BigDecimal highValueLimit) {
        this.highValueLimit = highValueLimit;
    }

    @Override
    public NormalizedOrder process(RawOrder item) {
        if (item.amount() == null || item.amount().signum() < 0) {
            throw new InvalidOrderException(
                "Order amount không hợp lệ: " + item.orderId()
            );
        }

        String orderId = item.orderId().trim();
        String customerId = item.customerId().trim();
        String currency = item.currency().trim().toUpperCase(Locale.ROOT);

        boolean highValue =
            item.amount().compareTo(highValueLimit) >= 0;

        return new NormalizedOrder(
            orderId,
            customerId,
            item.amount(),
            currency,
            highValue
        );
    }
}
~~~

Cùng một RawOrder và cùng một highValueLimit sẽ tạo cùng một NormalizedOrder. Processor không sửa item đầu vào, không ghi dữ liệu và không phụ thuộc trạng thái của lần gọi trước.

Đây là kiểu processor dễ retry: nếu Spring Batch gọi lại, phép biến đổi tạo cùng kết quả.

### Không sửa item đầu vào nếu không cần

Ví dụ sau có thể gây vấn đề:

~~~java
public Order process(Order item) {
    item.setStatus("NORMALIZED");
    item.setAmount(item.getAmount().setScale(2));
    return item;
}
~~~

Nếu cùng object được giữ trong buffer hoặc được sử dụng ở một lần thử khác, processor có thể nhìn thấy dữ liệu đã bị thay đổi từ lần trước. Điều này làm kết quả phụ thuộc lịch sử gọi.

Ưu tiên object bất biến như Java record hoặc tạo object output mới. Nếu model mutable là bắt buộc, hãy tạo bản sao trước khi thay đổi.

## 5. Deterministic processing

Một processor deterministic trả cùng kết quả khi nhận cùng input và cùng cấu hình nghiệp vụ. Các yếu tố có thể làm processor không deterministic gồm:

- Đọc thời gian hiện tại bằng Clock.systemUTC() ở mỗi lần gọi.
- Sinh UUID mới cho cùng một item.
- Dùng số ngẫu nhiên.
- Đọc cấu hình mutable thay đổi giữa các lần retry.
- Gọi API trả trạng thái khác nhau giữa các lần gọi.
- Dựa vào biến đếm hoặc thứ tự item đã xử lý trước đó.
- Dùng dữ liệu database có thể thay đổi mà không snapshot.

Ví dụ không deterministic:

~~~java
public EnrichedOrder process(RawOrder order) {
    return new EnrichedOrder(
        order.orderId(),
        Instant.now(),
        UUID.randomUUID().toString()
    );
}
~~~

Nếu processor được gọi lại, timestamp và ID sẽ thay đổi. Điều đó có thể làm output khác nhau cho cùng một item.

Có thể khắc phục bằng cách snapshot giá trị trước khi chạy Step:

~~~java
public record BatchContext(
    Instant processingTime,
    String runId
) {
}
~~~

Đưa processingTime và runId vào JobParameters hoặc JobExecutionContext, rồi inject qua StepScope. Cùng JobInstance sẽ dùng cùng snapshot theo thiết kế.

Nếu cần tạo event ID, nên tạo ở boundary tạo business event và lưu ổn định cùng dữ liệu đầu vào, không tạo lại mỗi lần processor chạy.

## 6. Phân loại exception trước khi cấu hình retry

Không phải lỗi nào cũng nên retry. Retry chỉ hữu ích khi có khả năng trạng thái hệ thống sẽ thay đổi và lần thử tiếp theo có thể thành công.

| Nhóm lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Lỗi tạm thời | Timeout, connection reset, HTTP 503 | Retry có giới hạn |
| Rate limit | HTTP 429 | Retry theo Retry-After hoặc backoff |
| Dữ liệu không hợp lệ | Thiếu ID, amount âm | Thường không retry; reject/skip |
| Lỗi cấu hình | Sai URL, thiếu credential | Fail sớm |
| Lỗi mapping/schema | Field không parse được | Thường không retry |
| Conflict đồng thời | Optimistic lock/deadlock | Có thể retry có giới hạn |
| Business rejection | Không đủ điều kiện xử lý | Không retry nếu trạng thái không đổi |

Exception cần có ý nghĩa để policy phân loại đúng:

~~~java
public class TransientPricingException extends RuntimeException {
    public TransientPricingException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class InvalidOrderException extends RuntimeException {
    public InvalidOrderException(String message) {
        super(message);
    }
}
~~~

Không bắt mọi exception rồi ném cùng một RuntimeException chung. Nếu tất cả lỗi đều bị xem là retryable, một item sai dữ liệu có thể được thử lại nhiều lần mà không có cơ hội thành công.

## 7. Cấu hình retry cho processor trong Step

Retry được cấu hình ở cấp fault-tolerant Step. Ví dụ:

~~~java
@Bean
Step enrichOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<RawOrder> reader,
        ItemProcessor<RawOrder, EnrichedOrder> processor,
        ItemWriter<EnrichedOrder> writer) {

    return new StepBuilder("enrichOrdersStep", jobRepository)
        .<RawOrder, EnrichedOrder>chunk(50, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientPricingException.class)
        .retryLimit(3)
        .skip(InvalidOrderException.class)
        .skipLimit(100)
        .build();
}
~~~

Ý nghĩa:

- faultTolerant() bật cấu hình retry/skip cho Step.
- retry(...) khai báo exception có thể thử lại.
- retryLimit(...) giới hạn số lần retry theo semantics của phiên bản Spring Batch đang dùng.
- skip(...) cho phép bỏ qua exception dữ liệu được xác định.
- skipLimit(...) giới hạn tổng số lần skip.

Retry policy ở cấp Step có thể áp dụng cho các giai đoạn đọc, process hoặc write tùy exception và cấu hình. Không nên cho rằng mọi exception phát sinh đều đến từ processor. Khi cần phân biệt lỗi ở từng giai đoạn, dùng exception type rõ ràng, listener và test Step.

### Retry limit và lần thử đầu tiên

Các API builder và cách mô tả retry limit có thể khác theo phiên bản Spring Batch/Spring Retry. Hãy kiểm tra dependency version của dự án và xác nhận số lần thực tế bằng test. Đừng suy luận số tổng attempt chỉ từ tên thuộc tính retryLimit.

### Loại trừ exception khỏi retry

Nếu cần chỉ retry một nhóm lỗi cụ thể, dùng retry(...) cho nhóm đó và noRetry(...) cho lỗi không được thử lại theo API của version đang dùng. Một exception validation không nên được retry chỉ vì nó là RuntimeException.

## 8. Backoff giữa các lần retry

Retry liên tiếp không có delay có thể tạo tải lớn lên dịch vụ đang gặp sự cố. Backoff đặt khoảng chờ giữa các lần thử.

Ví dụ exponential backoff:

~~~java
ExponentialBackOffPolicy backOffPolicy =
    new ExponentialBackOffPolicy();

backOffPolicy.setInitialInterval(500L);
backOffPolicy.setMultiplier(2.0);
backOffPolicy.setMaxInterval(8000L);
~~~

Gắn policy vào fault-tolerant Step theo API của phiên bản đang dùng:

~~~java
return new StepBuilder("enrichOrdersStep", jobRepository)
    .<RawOrder, EnrichedOrder>chunk(50, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .retry(TransientPricingException.class)
    .retryLimit(3)
    .backOffPolicy(backOffPolicy)
    .build();
~~~

Với cấu hình minh họa, khoảng chờ tăng theo các lần retry cho đến giới hạn tối đa. Giá trị thực tế nên dựa trên timeout của dịch vụ, latency, throughput và retry budget.

### Jitter và retry storm

Nếu hàng nghìn item cùng lỗi tại một thời điểm và tất cả đều retry sau đúng 1, 2, 4 giây, chúng có thể tạo tải đồng loạt lên dịch vụ. Jitter thêm độ ngẫu nhiên có kiểm soát vào khoảng chờ để phân tán retry.

Không phải mọi BackOffPolicy mặc định đều có jitter. Nếu dịch vụ có rate limit, có thể cần policy tùy chỉnh hoặc tôn trọng Retry-After của response HTTP.

## 9. Retry budget và timeout

Retry không nên kéo dài vô hạn. Hãy xác định tổng thời gian tối đa cho một item và cho toàn Step.

Ví dụ:

- Timeout một lần gọi: 2 giây.
- Tối đa 3 lần retry.
- Backoff: 0.5, 1 và 2 giây.
- Tổng thời gian dự kiến cho item phải nằm trong SLA của Job.

Cần tính cả thời gian kết nối, thời gian server xử lý, backoff và transaction. Nếu Step giữ transaction lâu trong lúc chờ API, connection database hoặc lock có thể bị giữ lâu hơn cần thiết.

Một số thiết kế tách enrichment API thành bước riêng hoặc dùng bulk API để giảm số lần gọi. Retry chỉ là cơ chế phục hồi, không thay thế việc thiết kế throughput và timeout đúng.

## 10. Retry processor có thể làm lặp side effect

Ví dụ processor:

~~~java
public EnrichedOrder process(RawOrder order) {
    shippingClient.createShipment(order);
    return map(order);
}
~~~

Giả sử API tạo shipment thành công nhưng response bị timeout. Processor ném exception; Spring Batch retry. API nhận request thứ hai và tạo thêm shipment.

Ngay cả khi lần đầu trả response thành công, writer có thể thất bại sau đó và chunk rollback. Nếu processor chạy lại trong quá trình retry chunk, API có thể được gọi lần nữa.

Cách tốt hơn là tách transformation và side effect:

~~~java
public ShipmentCommand process(RawOrder order) {
    return new ShipmentCommand(
        order.orderId(),
        order.customerId(),
        order.shippingAddress(),
        order.shipmentEventId()
    );
}
~~~

Processor chỉ tạo command. Writer hoặc application service thực hiện side effect bằng idempotency key ổn định.

Nếu API hỗ trợ header Idempotency-Key, dùng cùng key cho mọi lần retry của cùng business operation.

## 11. Idempotency key phải ổn định

Một idempotency key đại diện cho một business operation. Nó phải được tạo một lần và giữ nguyên qua:

- Retry nội bộ của Spring Batch.
- Rollback và xử lý lại chunk.
- Job restart.
- Broker redelivery nếu item đến từ message.
- Producer retry hoặc replay.
- Retry HTTP do timeout.

Ví dụ command:

~~~java
public record ShipmentCommand(
    String orderId,
    String customerId,
    Address address,
    String idempotencyKey
) {
}
~~~

Key có thể là shipment event ID do producer tạo, hoặc composite key theo business contract, chẳng hạn orderId + shipmentVersion. Không nên tạo UUID mới trong mỗi lần process().

### Phân biệt idempotency key và attempt ID

- Idempotency key giữ nguyên cho cùng một nghiệp vụ.
- Attempt ID có thể thay đổi ở mỗi lần thử để theo dõi lần gọi.
- Correlation ID liên kết log/trace qua nhiều service.
- Message delivery tag có thể thay đổi qua mỗi lần broker giao.

Không dùng attempt ID hoặc delivery tag làm idempotency key vì chúng không nhận diện cùng business operation.

## 12. Idempotency tại API bên ngoài

Nếu writer gọi API hỗ trợ idempotency:

~~~java
public ShipmentResult createShipment(ShipmentCommand command) {
    return shippingClient.createShipment(
        command,
        command.idempotencyKey()
    );
}
~~~

API bên ngoài cần định nghĩa rõ:

- Phạm vi duy nhất của key.
- Thời gian lưu key.
- Hành vi khi cùng key được gửi lại với payload giống nhau.
- Hành vi khi cùng key được gửi lại với payload khác.
- Response trả lại cho lần request đã xử lý.
- Cách xử lý request đồng thời có cùng key.

Nếu server nhận cùng key và payload tương đương, nó nên trả lại kết quả đã lưu thay vì tạo shipment mới.

Nếu cùng key nhưng payload khác, thông thường cần trả conflict hoặc lỗi rõ ràng. Không âm thầm chấp nhận vì có thể che giấu lỗi producer.

### Timeout không chứng minh request thất bại

Khi client timeout, server có thể đã thực hiện side effect nhưng response không đến được client. Không được tạo key mới chỉ vì lần gọi trước timeout. Retry cùng key hoặc thực hiện reconciliation bằng business operation ID.

Nếu API không hỗ trợ idempotency và không có cách truy vấn kết quả theo business key, không thể bảo đảm side effect exactly-once chỉ bằng logic ở processor.

## 13. Idempotency trong database

Nếu business update và idempotency record nằm trong cùng database, có thể bảo vệ bằng unique constraint và transaction.

Ví dụ bảng:

~~~sql
CREATE TABLE processed_operation (
    operation_key VARCHAR(200) PRIMARY KEY,
    operation_type VARCHAR(100) NOT NULL,
    payload_hash VARCHAR(128) NOT NULL,
    processed_at TIMESTAMP NOT NULL
);
~~~

Service thực hiện operation:

~~~java
@Transactional
public ProcessingResult applyOnce(ShipmentCommand command) {
    boolean inserted = operationRepository.insertIfAbsent(
        command.idempotencyKey(),
        "CREATE_SHIPMENT",
        hash(command)
    );

    if (!inserted) {
        return ProcessingResult.ALREADY_APPLIED;
    }

    shipmentRepository.createShipment(command);

    return ProcessingResult.APPLIED;
}
~~~

Điểm quan trọng là insert operation key và business update cùng transaction. Nếu business update thất bại, operation record phải rollback cùng. Nếu transaction commit, lần retry sau sẽ gặp unique key và không tạo side effect lần nữa.

Câu lệnh insert-if-absent phụ thuộc database. Ví dụ PostgreSQL:

~~~sql
INSERT INTO processed_operation (
    operation_key,
    operation_type,
    payload_hash,
    processed_at
)
VALUES (?, ?, ?, CURRENT_TIMESTAMP)
ON CONFLICT (operation_key) DO NOTHING;
~~~

Không dùng mô hình SELECT trước rồi INSERT như cơ chế duy nhất. Hai worker đồng thời có thể cùng thấy key chưa tồn tại. Unique constraint ở database là lớp bảo vệ cuối cùng.

### Cùng key nhưng payload khác

Lưu payload hash hoặc business fields quan trọng để phân biệt duplicate hợp lệ với key reuse sai. Nếu key đã tồn tại nhưng payload hash khác, báo lỗi hoặc đưa vào quarantine theo policy. Không coi mọi conflict đều là duplicate vô hại.

## 14. Processor có nên kiểm tra idempotency store?

Có thể viết processor kiểm tra xem key đã tồn tại và trả null nếu item đã xử lý. Nhưng cách này thường không đủ an toàn:

~~~java
public ShipmentCommand process(RawOrder order) {
    if (operationRepository.exists(order.eventId())) {
        return null;
    }

    return createCommand(order);
}
~~~

Vấn đề:

- SELECT và write không atomic.
- Hai worker có thể cùng thấy key chưa tồn tại.
- State có thể thay đổi giữa processor và writer.
- Processor có thể được gọi lại.
- Trả null làm tăng filterCount, có thể gây nhầm duplicate với business filtering.
- Nếu check tạo marker hoặc side effect, transaction boundary càng khó kiểm soát.

Có thể dùng processor để đọc thông tin hoặc đánh dấu duplicate dự kiến nếu đó là optimization, nhưng writer/service vẫn phải bảo vệ thao tác bằng unique constraint hoặc API idempotency key.

Nếu cần phân biệt duplicate trong báo cáo, output có thể chứa route/result như NEW, ALREADY_APPLIED hoặc REJECTED, thay vì âm thầm filter mà không có audit.

## 15. Idempotency trong writer và transaction của chunk

Với database writer, business update thường chạy trong transaction của chunk nếu dùng đúng DataSource và transaction manager. Nếu chunk rollback, các update trong cùng transaction được rollback. Khi Step retry, thao tác có thể chạy lại trên trạng thái chưa commit.

Điều đó giúp database writer có thể an toàn hơn nếu:

- Tất cả update tham gia cùng transaction.
- Không dùng propagation độc lập để commit side effect ngoài chunk.
- Unique constraint bảo vệ business key.
- SQL update có điều kiện phù hợp.
- Các trigger hoặc stored procedure cũng không tạo side effect ngoài transaction.

Ví dụ writer:

~~~java
public class ShipmentWriter implements ItemWriter<ShipmentCommand> {

    private final ShipmentService shipmentService;

    public ShipmentWriter(ShipmentService shipmentService) {
        this.shipmentService = shipmentService;
    }

    @Override
    public void write(Chunk<? extends ShipmentCommand> chunk) {
        for (ShipmentCommand command : chunk.getItems()) {
            shipmentService.applyOnce(command);
        }
    }
}
~~~

Service dùng cùng transaction manager và DataSource với Step. Không tự mở transaction REQUIRES_NEW cho operation key nếu business update vẫn nằm trong transaction ngoài; điều đó có thể commit marker trước khi business update commit.

### Transaction propagation cần được hiểu rõ

- REQUIRED thường tham gia transaction hiện tại nếu có.
- REQUIRES_NEW tạo transaction độc lập và suspend transaction hiện tại.
- NOT_SUPPORTED có thể chạy ngoài transaction hiện tại.

Nếu inbox marker commit trong REQUIRES_NEW nhưng writer business update rollback, lần retry sau có thể bị coi là duplicate dù business update chưa hoàn tất. Hãy chọn propagation có chủ đích và test bằng database thật.

## 16. Processor side effect với transaction manager khác

Một processor có thể gọi repository dùng cùng transaction manager của Step. Nếu database operation tham gia transaction chunk, rollback có thể hoàn tác nó. Tuy nhiên, việc đặt side effect trong processor vẫn khiến code khó hiểu và có thể không an toàn nếu:

- Dependency dùng DataSource hoặc transaction manager khác.
- Method dùng REQUIRES_NEW.
- Processor gọi API hoặc broker ngoài transaction.
- Có async task chạy sau khi process() trả về.
- Side effect được commit trước khi writer hoàn tất.
- Retry policy gọi lại processor ngoài transaction dự kiến.

Ưu tiên processor thuần và đặt side effect ở writer/service được thiết kế cho transaction. Nếu phải dùng processor có side effect, cần mô tả rõ transaction ownership và test các crash window.

## 17. Outbox Pattern cho side effect publish message

Một use case thường gặp là processor/writer cập nhật database rồi cần publish event. Gọi broker trực tiếp sau database update tạo cửa sổ lỗi:

- DB commit nhưng publish thất bại: downstream không nhận event.
- Publish thành công nhưng DB rollback: downstream nhận event không có state tương ứng.
- Publish thành công nhưng response timeout: retry có thể publish trùng.

Outbox Pattern lưu ý định publish cùng transaction với business update.

~~~sql
CREATE TABLE outbox_event (
    event_id VARCHAR(200) PRIMARY KEY,
    aggregate_id VARCHAR(200) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP NULL
);
~~~

Trong cùng transaction:

1. Ghi operation/idempotency key.
2. Cập nhật business data.
3. Insert outbox event.
4. Commit.

Publisher riêng đọc outbox và gửi message. Nếu publisher crash sau khi publish nhưng trước khi đánh dấu published, event có thể được gửi lại. Consumer downstream vẫn cần idempotency.

Outbox làm cho business update và ý định publish atomic trong database; nó không biến broker delivery thành exactly-once.

## 18. Phân biệt retryable và non-retryable trong business processor

Ví dụ processor gọi pricing service:

~~~java
public EnrichedOrder process(RawOrder order) {
    try {
        PriceQuote quote = pricingClient.quote(order.productId());
        return new EnrichedOrder(order, quote);
    } catch (SocketTimeoutException ex) {
        throw new TransientPricingException(
            "Pricing service timeout",
            ex
        );
    } catch (InvalidProductException ex) {
        throw new InvalidOrderException(
            "Product không hợp lệ: " + order.productId()
        );
    }
}
~~~

Timeout có thể retry. Product không tồn tại là lỗi dữ liệu hoặc business rejection, thường không retry nếu dữ liệu không thay đổi.

Nếu pricing service trả HTTP 429, hãy tôn trọng Retry-After nếu client và retry policy hỗ trợ. HTTP 5xx có thể tạm thời; HTTP 4xx thường là lỗi request/validation nhưng có ngoại lệ như 408 hoặc 429. Phân loại theo contract API thay vì chỉ dựa vào nhóm status.

Không retry tất cả IOException một cách mù quáng. Một số lỗi là cấu hình hoặc lỗi payload không thể phục hồi.

## 19. Skip sau khi retry hết

Một exception có thể được cấu hình vừa retry vừa skip. Khi retry đã hết, Step có thể áp dụng skip policy nếu exception đó được phép skip.

Ví dụ:

~~~java
return new StepBuilder("enrichOrdersStep", jobRepository)
    .<RawOrder, EnrichedOrder>chunk(50, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .retry(TransientPricingException.class)
    .retryLimit(3)
    .skip(InvalidOrderException.class)
    .skipLimit(100)
    .build();
~~~

Ở ví dụ này, lỗi pricing tạm thời được retry. Lỗi InvalidOrderException có thể được skip. Nếu muốn một lỗi tạm thời sau khi hết retry được skip, cần thêm nó vào skip policy và xác định rõ hậu quả nghiệp vụ. Không nên skip lỗi hạ tầng chỉ để Job có trạng thái COMPLETED.

### SkipListener và reject output

Nếu cần lưu item bị skip để điều tra, có thể dùng SkipListener hoặc reject writer. Listener không nên tạo side effect không idempotent vì callback có thể chịu ảnh hưởng transaction/rollback và lifecycle của Step.

Một reject store bền vững có thể dùng unique key theo JobInstance + item business key để tránh ghi reject trùng.

## 20. Processor trả null khác với retry và skip

ItemProcessor trả null có nghĩa filter item. Đây không phải exception, không phải retry và cũng không nhất thiết là skip.

Ví dụ:

~~~java
public NormalizedOrder process(RawOrder order) {
    if (order.isTestRecord()) {
        return null;
    }

    return normalize(order);
}
~~~

Khi item bị filter:

- Không chuyển item tới writer.
- filterCount tăng theo semantics của Step.
- Không có exception để retry.
- Không tăng processSkipCount chỉ vì trả null.

Nếu processor trả null vì phát hiện event đã xử lý, cần cân nhắc có muốn tính đó là filter hay duplicate. Với audit nghiệp vụ, có thể trả một outcome rõ ràng hoặc ghi metric riêng trong thành phần idempotency.

## 21. Stateful processor và concurrency

Processor có field mutable có thể tạo lỗi khi retry hoặc chạy song song:

~~~java
public class UnsafeProcessor
        implements ItemProcessor<Order, Order> {

    private int processedCount;

    @Override
    public Order process(Order order) {
        processedCount++;
        order.setSequence(processedCount);
        return order;
    }
}
~~~

Kết quả phụ thuộc thứ tự và số lần gọi. Nếu item được retry, sequence có thể thay đổi. Nếu Step chạy nhiều thread, counter có thể race.

Không dùng processor để tạo sequence nghiệp vụ bằng counter trong memory. Dùng ID từ nguồn, database sequence hoặc một cơ chế cấp phát có transaction và semantics rõ ràng.

Nếu processor cần cache, hãy bảo đảm cache chỉ là optimization và không làm thay đổi kết quả. Cache mutable dùng chung phải thread-safe và không được trở thành nguồn chân lý cho business state.

### StepScope không tự làm processor thread-safe

@StepScope tạo target bean gắn với StepExecution, nhưng một multi-threaded Step vẫn có thể gọi cùng target từ nhiều thread. Nếu processor có state mutable, cần đồng bộ hóa hoặc thiết kế lại thành stateless.

Partitioning thường tạo StepExecution riêng cho từng partition, phù hợp hơn khi cần state riêng theo worker.

## 22. Snapshot cấu hình và dữ liệu phụ thuộc thời gian

Processor có thể dùng ngưỡng, tỷ giá, policy hoặc business date. Nếu các giá trị này thay đổi giữa retry hoặc restart, cùng item có thể được xử lý khác nhau.

Ví dụ high-value threshold:

~~~java
@Bean
@StepScope
ItemProcessor<RawOrder, EnrichedOrder> orderProcessor(
        @Value("#{jobParameters['highValueLimit']}") BigDecimal limit,
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    return new OrderProcessor(limit, LocalDate.parse(businessDate));
}
~~~

Nếu JobInstance cần giữ cùng rule, các tham số phải ổn định qua restart. Dùng identifying JobParameters khi giá trị là một phần identity của lần chạy; nếu không, lưu metadata snapshot rõ ràng và bảo đảm restart khôi phục cùng giá trị.

Không đọc ngưỡng từ một config server mutable ở mỗi lần process nếu thay đổi đó có thể làm kết quả khác nhau giữa các lần thử.

## 23. Retry và side effect bất đồng bộ

Một processor có thể gửi công việc vào executor hoặc gọi async service rồi trả về trước khi hoàn tất. Điều này làm transaction boundary của chunk không còn bao phủ công việc bất đồng bộ.

Ví dụ nguy hiểm:

~~~java
public OrderCommand process(Order order) {
    executor.submit(() -> externalClient.publish(order));
    return toCommand(order);
}
~~~

Nếu Step rollback sau khi task async đã chạy, side effect vẫn có thể xảy ra. Retry sẽ submit thêm task. Việc đóng Job không nhất thiết chờ hoặc hủy đúng các task đã submit.

Nếu cần asynchronous processing, hãy dùng một mô hình có acknowledgment và durable queue rõ ràng, hoặc ghi outbox trong transaction rồi để publisher riêng xử lý. Không fire-and-forget side effect từ processor.

## 24. Retry của processor và retry của writer

Một Step có thể retry exception phát sinh ở nhiều giai đoạn. Cần biết side effect nằm ở đâu:

| Giai đoạn | Ví dụ lỗi | Rủi ro khi retry |
|---|---|---|
| Reader | Timeout khi lấy input | Đọc trùng hoặc bỏ sót nếu cursor/ack sai |
| Processor | API enrichment timeout | API có thể đã thực hiện side effect |
| Writer | DB deadlock hoặc API timeout | Một phần write có thể đã xảy ra |
| Commit | Connection mất khi commit | Client có thể không biết transaction đã commit hay chưa |

Processor thường nên không có side effect. Writer thường là nơi ghi output và có thể dựa vào transaction của chunk nếu resource tham gia cùng transaction manager. External writer vẫn cần idempotency.

Không cho rằng retry một exception luôn có nghĩa thao tác trước đó chưa xảy ra. Timeout thường chỉ nói client không nhận được kết quả đúng hạn.

## 25. Retry policy không thay thế circuit breaker

Retry phù hợp với lỗi ngắn hạn. Nếu dịch vụ ngoài đang down kéo dài, mọi item tiếp tục retry sẽ làm Job chậm và tăng tải lên hệ thống lỗi.

Circuit breaker có thể tạm ngừng gọi dịch vụ sau một số lỗi liên tiếp, để hệ thống phục hồi. Khi circuit mở, processor có thể ném exception có ý nghĩa để Step dừng hoặc chờ retry theo một workflow riêng.

Các nguyên tắc:

- Retry budget hữu hạn.
- Timeout cho mỗi request.
- Backoff và jitter.
- Circuit breaker khi dependency có thể lỗi kéo dài.
- Rate limiter để không vượt quota.
- Metrics cho attempt, latency và failure.
- Không retry validation hoặc lỗi cấu hình.

Retry, circuit breaker và rate limiter giải quyết các vấn đề khác nhau; chúng có thể phối hợp nhưng cần tránh nhiều lớp retry lồng nhau làm số attempt tăng ngoài dự kiến.

## 26. Kiểm thử processor thuần

Vì processor thuần không phụ thuộc Spring Batch context, unit test rất đơn giản:

~~~java
@Test
void normalizesOrderDeterministically() throws Exception {
    NormalizeOrderProcessor processor =
        new NormalizeOrderProcessor(new BigDecimal("1000.00"));

    RawOrder input = new RawOrder(
        " O-1001 ",
        " C-10 ",
        new BigDecimal("1200.00"),
        "usd"
    );

    NormalizedOrder first = processor.process(input);
    NormalizedOrder second = processor.process(input);

    assertEquals(first, second);
    assertEquals("O-1001", first.orderId());
    assertEquals("C-10", first.customerId());
    assertEquals("USD", first.currency());
    assertTrue(first.highValue());
}
~~~

Test gọi cùng input hai lần và xác nhận kết quả tương đương. Đây là cách đơn giản để kiểm tra deterministic behavior.

Nếu processor trả object không override equals, hãy assert từng field. Có thể dùng record để value equality được tạo sẵn.

### Kiểm tra không sửa input

Với input mutable, chụp trạng thái trước khi gọi process rồi xác nhận không thay đổi. Tốt hơn là dùng immutable input để không cần test nhiều biến thể mutation.

## 27. Kiểm thử retry bằng mock dependency

Nếu processor gọi dependency có thể timeout, test nên mô phỏng lỗi rồi thành công:

~~~java
@Test
void processorCanRecoverFromTransientDependencyFailure()
        throws Exception {

    when(pricingClient.quote("SKU-1"))
        .thenThrow(new TransientPricingException("timeout", null))
        .thenReturn(new PriceQuote(new BigDecimal("25.00")));

    PricingProcessor processor =
        new PricingProcessor(pricingClient);

    assertThrows(
        TransientPricingException.class,
        () -> processor.process(orderWithSku("SKU-1"))
    );

    EnrichedOrder result =
        processor.process(orderWithSku("SKU-1"));

    assertEquals(new BigDecimal("25.00"), result.price());
    verify(pricingClient, times(2)).quote("SKU-1");
}
~~~

Test này chỉ xác nhận processor có thể phát sinh lỗi và thành công ở lần gọi tiếp theo. Nó chưa kiểm tra Spring Batch retry policy. Để kiểm tra retry của Step, cần chạy Step thật với processor/dependency giả và xác nhận số attempt.

## 28. Kiểm thử idempotency của side effect

Với service dùng idempotency key:

~~~java
@Test
void appliesSameOperationOnlyOnce() {
    ShipmentCommand command = new ShipmentCommand(
        "O-1001",
        "C-10",
        address(),
        "shipment-event-9001"
    );

    when(operationRepository.insertIfAbsent(
        "shipment-event-9001",
        "CREATE_SHIPMENT",
        expectedHash(command)
    )).thenReturn(true, false);

    shipmentService.applyOnce(command);
    shipmentService.applyOnce(command);

    verify(shipmentRepository, times(1))
        .createShipment(command);
}
~~~

Test xác nhận cùng key chỉ tạo side effect một lần trong service logic. Với database thật, cần integration test để xác nhận unique constraint và transaction rollback.

### Test cùng key nhưng payload khác

Tạo hai command cùng key nhưng amount/address khác. Service phải phát hiện key reuse không hợp lệ hoặc trả conflict theo contract. Không được im lặng bỏ qua payload khác.

## 29. Kiểm thử retry của Step bằng spring-batch-test

Dùng JobLauncherTestUtils để chạy Step và xác nhận fault-tolerant behavior.

Ví dụ cấu hình test có processor chỉ thất bại ở lần đầu:

~~~java
AtomicInteger attempts = new AtomicInteger();

ItemProcessor<RawOrder, EnrichedOrder> processor = item -> {
    if (attempts.incrementAndGet() == 1) {
        throw new TransientPricingException(
            "Temporary failure",
            null
        );
    }

    return enrich(item);
};
~~~

Chạy Step với reader có một item và writer giả hoặc database test. Sau khi launch:

- Xác nhận Step COMPLETED nếu retry thành công.
- Xác nhận processor được gọi lại theo policy.
- Xác nhận writer nhận item đúng một lần.
- Xác nhận không có duplicate business record.
- Xác nhận retry metrics/listener nếu ứng dụng theo dõi.

Để test retry limit, cấu hình processor luôn ném exception. Xác nhận Step thất bại sau số lần thử theo version/configuration thực tế. Không chỉ assert exception được ném từ unit test; hãy kiểm tra StepExecution và JobExecution.

## 30. Kiểm thử chunk rollback và processor được gọi lại

Một test quan trọng là làm writer thất bại sau khi processor đã xử lý item. Với fault-tolerant Step, tùy cấu hình, item có thể được xử lý lại trong quá trình rollback/retry.

Mô phỏng:

1. Reader trả hai item.
2. Processor tạo output và đếm số lần gọi.
3. Writer ném exception tạm thời ở lần ghi đầu.
4. Retry policy cho phép thử lại.
5. Writer thành công ở lần sau.
6. Xác nhận output cuối không có duplicate.
7. Xác nhận processor không tạo side effect ngoài transaction hoặc side effect được bảo vệ bằng idempotency key.

Không nên khẳng định processor luôn được gọi lại trong mọi cấu hình rollback. Test phải mô phỏng reader/transaction và fault-tolerance behavior của ứng dụng thực tế.

## 31. Kiểm thử restart sau failure

Job restart test cần dùng cùng JobInstance và identifying JobParameters. Cần tạo một failure sau khi có ít nhất một chunk đã commit.

Xác nhận:

- Chunk đã commit không bị ghi lại ngoài idempotency policy.
- Item chưa commit được xử lý tiếp.
- Processor có thể được gọi lại cho item thuộc chunk thất bại.
- Side effect ngoài database không bị lặp.
- Idempotency key vẫn giữ nguyên.
- JobRepository lưu checkpoint đúng.
- Output writer khôi phục trạng thái phù hợp.

Nếu processor phụ thuộc thời gian hoặc cấu hình, test restart phải bảo đảm snapshot giữ nguyên giữa hai execution.

## 32. Retry listener và observability

Khi cần theo dõi retry, có thể dùng listener phù hợp với Spring Batch/Spring Retry version đang dùng. Listener giúp quan sát:

- Exception type.
- Item business key.
- Số lần attempt.
- Thời gian chờ.
- Kết quả cuối cùng.
- JobExecution và StepExecution ID.

Không log toàn bộ payload nếu có dữ liệu nhạy cảm. Dùng correlation ID hoặc business key.

Metric có thể gồm:

- processor.process.count
- processor.retry.count
- processor.failure.count
- processor.skip.count
- processor.duration
- processor.idempotency.hit.count
- external.api.timeout.count
- external.api.idempotency.conflict.count

Retry rate tăng có thể báo hiệu dependency đang suy giảm. Idempotency hit tăng có thể là redelivery bình thường hoặc producer gửi lặp; cần quan sát cùng broker delivery metrics.

## 33. Những lỗi triển khai thường gặp

### Cho rằng processor chỉ được gọi một lần

Retry, rollback và restart có thể khiến cùng item được xử lý lại. Thiết kế processor an toàn cho nhiều lần gọi.

### Gửi message hoặc gọi API có side effect trong processor

Retry có thể gửi hoặc thực hiện hành động trùng. Tách transformation và side effect, hoặc dùng idempotency key ổn định.

### Tạo UUID mới mỗi lần process()

Cùng operation nhận key khác nhau và không deduplicate được. Tạo key tại nguồn business event và giữ nguyên.

### Retry mọi exception

Lỗi dữ liệu và cấu hình không tự hết. Chỉ retry lỗi tạm thời hoặc conflict có thể phục hồi.

### Retry không giới hạn

Có thể giữ chunk/Job quá lâu và tạo retry storm. Dùng limit, timeout, backoff và retry budget.

### Chỉ SELECT để kiểm tra đã xử lý chưa

Race condition vẫn có thể tạo duplicate. Dùng unique constraint và atomic insert/update.

### Commit idempotency marker riêng

Marker có thể commit trong khi business update rollback. Đặt cả hai trong cùng transaction nếu cùng database.

### Dùng REQUIRES_NEW không có chủ đích

Marker có thể commit độc lập với chunk. Kiểm tra transaction propagation.

### Coi HTTP timeout là request thất bại

Server có thể đã thực hiện operation. Retry cùng key hoặc reconciliation.

### Dùng counter hoặc mutable field trong processor

Retry và concurrency làm kết quả phụ thuộc lịch sử gọi. Processor nên stateless.

### Đọc thời gian hiện tại hoặc random trong processor

Cùng item có thể cho output khác nhau sau retry. Snapshot giá trị theo JobInstance hoặc đưa vào input.

### Nhầm filter với skip

Trả null là filter, không phải exception/skip. Theo dõi filterCount và skipCount riêng.

### Cho rằng database và broker cùng transaction

Không có transaction coordination thì commit database và ack broker vẫn có cửa sổ lỗi. Dùng inbox/outbox và idempotency.

### Chỉ test processor đơn lẻ

Unit test không chứng minh Step retry, rollback và restart đúng. Bổ sung Step integration test.

## 34. Quy trình thiết kế processor retry và idempotency

Khi triển khai processor có khả năng retry, hãy làm theo trình tự:

1. **Xác định side effect:** processor chỉ biến đổi dữ liệu hay gọi database/API/broker?
2. **Ưu tiên phép biến đổi thuần:** tạo output mới, deterministic và không sửa input.
3. **Phân loại lỗi:** transient, validation, business rejection, configuration hoặc concurrency conflict.
4. **Chọn retry policy:** chỉ retry lỗi có khả năng phục hồi.
5. **Đặt retry budget:** limit, timeout, backoff, jitter và tổng thời gian.
6. **Thiết kế idempotency key:** ổn định qua retry, rollback, restart và redelivery.
7. **Đặt side effect đúng nơi:** writer/service với transaction rõ ràng; external API cần idempotency key.
8. **Bảo vệ database:** unique constraint, insert-if-absent và business update cùng transaction.
9. **Dùng outbox:** nếu cần publish event sau business update.
10. **Giữ cấu hình deterministic:** snapshot business date, threshold, policy version và run ID.
11. **Kiểm thử:** cùng input nhiều lần, dependency transient failure, retry limit, chunk rollback và restart.
12. **Theo dõi:** retry rate, failure, skip, idempotency hit và external API timeout.

## 35. Những điểm cần nhớ

- ItemProcessor có thể được gọi nhiều lần cho cùng item do retry, rollback hoặc restart.
- Retry là cơ chế thử lại; idempotency là khả năng xử lý lặp mà không nhân đôi hiệu ứng nghiệp vụ.
- Processor nên là phép biến đổi thuần, deterministic và không tạo side effect.
- Ưu tiên input/output bất biến và không sửa object đầu vào.
- Không tạo UUID, timestamp hoặc random value mới cho cùng operation trong mỗi lần process().
- Phân loại exception thành transient, validation, business rejection và configuration.
- Retry có giới hạn, timeout, backoff và jitter; không retry mọi lỗi.
- Retry policy của Step có thể ảnh hưởng read/process/write, tùy exception và cấu hình.
- Side effect database phải tham gia transaction phù hợp; chú ý propagation như REQUIRES_NEW.
- External API cần idempotency key ổn định; timeout không chứng minh request chưa được xử lý.
- Unique constraint và atomic insert bảo vệ database trước duplicate đồng thời.
- Inbox lưu event đã nhận; outbox lưu ý định publish cùng business update.
- ExecutionContext checkpoint không thay thế idempotency store.
- Trả null từ processor là filter, không phải retry hoặc skip.
- Test cả processor thuần, retry của Step, chunk rollback và Job restart.
- Theo dõi attempt, retry, skip, idempotency hit và lỗi dependency.

Retry giúp Spring Batch phục hồi trước lỗi tạm thời, còn idempotency bảo vệ dữ liệu khi một item được xử lý lại. Khi processor giữ vai trò biến đổi thuần, side effect được đặt trong transaction hoặc API có idempotency key, và retry policy có giới hạn rõ ràng, pipeline batch có thể phục hồi mà không tạo ra kết quả nghiệp vụ trùng lặp.

