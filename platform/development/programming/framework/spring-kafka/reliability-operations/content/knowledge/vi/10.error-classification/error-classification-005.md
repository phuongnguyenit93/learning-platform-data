# Business validation failure

Business validation failure xảy ra khi message đọc được về mặt kỹ thuật nhưng dữ liệu hoặc trạng thái nghiệp vụ không đáp ứng quy tắc của hệ thống nhận. Ví dụ: đơn hàng có số lượng âm, loại tiền không được hỗ trợ, khách hàng không đủ điều kiện mua sản phẩm hoặc yêu cầu chuyển trạng thái đơn hàng không hợp lệ.

Trong Spring Kafka, consumer cần phân biệt lỗi nghiệp vụ không thể khắc phục bằng retry với lỗi chỉ tạm thời chưa đáp ứng điều kiện xử lý. Một message sai dữ liệu vĩnh viễn thường không nên được retry liên tục; message hợp lệ nhưng phụ thuộc vào dữ liệu chưa đồng bộ hoặc một bước nghiệp vụ chưa hoàn tất có thể cần retry có giới hạn. Lỗi database, network hoặc dịch vụ phụ trợ lại cần chính sách riêng.

Phân loại đúng giúp consumer tránh lặp vô ích, giữ message lỗi để điều tra, không làm mất dấu vết nghiệp vụ và cho phép replay sau khi nguyên nhân được sửa. Điểm quyết định là xác định message đã bị từ chối vĩnh viễn, đang chờ điều kiện tạm thời hay chưa thể xử lý vì hệ thống gặp sự cố.

## 1. Business validation failure là gì?

Một message có thể vượt qua bước deserialize và schema validation nhưng vẫn vi phạm quy tắc nghiệp vụ. Ví dụ payload JSON đúng cấu trúc, các trường có kiểu dữ liệu hợp lệ, nhưng `quantity` bằng 0 trong khi đơn hàng yêu cầu số lượng dương. Đây là lỗi semantic/business validation.

Phân biệt các lớp kiểm tra:

| Lớp kiểm tra | Câu hỏi | Ví dụ lỗi | Hướng xử lý thường gặp |
|---|---|---|---|
| Transport/format | Message có thể được đọc và giải mã không? | Byte payload hỏng, JSON không hợp lệ | Không retry payload không thể giải mã; quarantine/DLT để điều tra. |
| Schema/structural validation | Payload có đúng cấu trúc và kiểu trường không? | Thiếu `orderId`, trường `amount` sai kiểu | Thường không retry cho cùng payload; sửa producer/schema rồi xử lý lại có kiểm soát. |
| Business validation | Dữ liệu có thỏa quy tắc nghiệp vụ không? | Số lượng âm, tiền tệ bị cấm, trạng thái chuyển đổi không hợp lệ | Từ chối hoặc quarantine; chỉ retry nếu điều kiện có thể thay đổi theo thời gian. |
| Dependency/state precondition | Dữ liệu nghiệp vụ có sẵn để xử lý ngay không? | Customer chưa được đồng bộ, aggregate chưa tạo | Có thể retry có giới hạn hoặc đưa vào luồng chờ. |
| Technical/infrastructure | Hệ thống có thực hiện được thao tác không? | Database timeout, network error, broker unavailable | Retry có backoff nếu lỗi tạm thời; cảnh báo khi kéo dài. |

Không phải mọi exception phát sinh trong đoạn kiểm tra nghiệp vụ đều là permanent validation failure. Ví dụ, không tìm thấy customer có thể là lỗi vĩnh viễn nếu ID không tồn tại trong hệ thống nguồn, nhưng có thể chỉ là trạng thái tạm thời nếu customer event được publish trước event tạo đơn hàng. Cần xác định ý nghĩa theo hợp đồng sự kiện và mô hình nhất quán dữ liệu.

## 2. Phân loại permanent và transient business failure

### Lỗi nghiệp vụ vĩnh viễn

Đây là trường hợp dữ liệu hoặc yêu cầu không thể trở nên hợp lệ chỉ bằng cách chờ một khoảng thời gian. Ví dụ:

- `quantity` nhỏ hơn hoặc bằng 0.
- Mã tiền tệ không thuộc danh sách được hỗ trợ theo hợp đồng.
- Ngày hiệu lực nằm ngoài khoảng được phép và không thể thay đổi bằng cập nhật trạng thái.
- Một yêu cầu chuyển trạng thái từ `CANCELLED` sang `PAID` bị cấm bởi state machine.
- Một loại sản phẩm không được phép bán trong kênh hiện tại.
- Payload có định danh nghiệp vụ sai định dạng hoặc không thể ánh xạ đến một thực thể hợp lệ.

Retry cùng một message không làm dữ liệu tự thay đổi. Với nhóm này, có thể từ chối nghiệp vụ một cách rõ ràng hoặc chuyển message sang topic quarantine/DLT để lưu lại và điều tra. Nếu nghiệp vụ có khái niệm “rejected” hợp lệ, nên lưu kết quả từ chối có mã lỗi thay vì coi đó là lỗi hạ tầng.

### Lỗi nghiệp vụ tạm thời

Một số điều kiện nghiệp vụ có thể thay đổi sau khi một sự kiện khác được xử lý. Ví dụ:

- Đơn hàng tham chiếu đến customer vừa được tạo nhưng customer event chưa được consumer khác áp dụng.
- Aggregate chưa có trạng thái cần thiết vì event trước đó đang nằm trong backlog.
- Hạn mức chưa được cập nhật do một tiến trình đối soát đang chạy.
- Một quy trình phê duyệt chưa hoàn tất nhưng dự kiến sẽ hoàn tất trong một khoảng thời gian xác định.

Nhóm này cần chính sách retry có giới hạn, backoff và deadline. Nếu thứ tự sự kiện là yêu cầu bắt buộc, hãy thiết kế key/partition hoặc luồng chờ để event sau không vượt qua event trước. Retry blocking có thể giữ thứ tự trong partition nhưng chặn các message phía sau; retry topic có thể cho phép xử lý message sau trước, làm thay đổi thứ tự nghiệp vụ.

### Lỗi nghiệp vụ do dữ liệu đã lỗi thời

Có trường hợp event hợp lệ tại thời điểm phát sinh nhưng không còn phù hợp khi consumer nhận được. Ví dụ giá sản phẩm đã thay đổi, phiên bản aggregate đã tiến lên hoặc yêu cầu cập nhật dùng một version cũ. Hệ thống cần quy định rõ:

- Chấp nhận event theo snapshot tại thời điểm phát sinh.
- Từ chối event nếu version không còn mới nhất.
- Reconcile bằng cách đọc trạng thái hiện tại và áp dụng quy tắc bù.
- Đưa event vào hàng đợi điều tra khi không thể tự quyết định.

Không nên retry một event stale vô hạn nếu quy tắc hiện tại chắc chắn sẽ tiếp tục từ chối nó.

## 3. Xác thực ở producer và consumer

Producer nên kiểm tra dữ liệu trước khi publish để giảm message lỗi đi vào Kafka. Các kiểm tra như trường bắt buộc, định dạng ID, giới hạn kích thước, enum và schema compatibility có thể thực hiện tại biên phát sinh sự kiện.

Consumer vẫn phải xác thực độc lập. Producer có thể là service cũ, client khác, dữ liệu replay hoặc một tiến trình migration. Không nên tin rằng mọi message trong topic đều đã qua cùng một phiên bản validation.

Một quy trình hợp lý gồm:

1. Producer xác thực các trường và quy tắc mà nó sở hữu trước khi tạo event.
2. Schema registry hoặc serializer kiểm soát cấu trúc payload và khả năng tương thích schema nếu hệ thống sử dụng.
3. Consumer deserialize và kiểm tra cấu trúc trước khi gọi nghiệp vụ.
4. Domain service thực hiện business validation dựa trên dữ liệu và trạng thái nghiệp vụ hiện tại.
5. Kết quả được phân loại thành accepted, rejected, retryable hoặc technical failure.

Không đặt toàn bộ business rule ở producer. Consumer là nơi thực thi quy tắc bảo vệ trạng thái mà nó sở hữu. Cũng không sao chép business rule tùy tiện ở nhiều service mà không có một hợp đồng và nguồn sự thật rõ ràng.

## 4. Biểu diễn validation error rõ ràng

Một validation failure nên chứa mã lỗi ổn định và thông tin cần thiết để điều tra. Không nên chỉ ném `RuntimeException("Invalid message")` vì log và DLT khó phân loại.

Ví dụ exception riêng:

```java
public class BusinessValidationException extends RuntimeException {

    private final String errorCode;
    private final String field;

    public BusinessValidationException(
            String errorCode, String field, String message) {
        super(message);
        this.errorCode = errorCode;
        this.field = field;
    }

    public String getErrorCode() {
        return errorCode;
    }

    public String getField() {
        return field;
    }
}
```

Service có thể dùng exception này khi phát hiện quy tắc bị vi phạm:

```java
public void validate(OrderCreated event) {
    if (event.quantity() <= 0) {
        throw new BusinessValidationException(
                "ORDER_QUANTITY_INVALID",
                "quantity",
                "Quantity must be greater than zero");
    }

    if (!supportedCurrencies.contains(event.currency())) {
        throw new BusinessValidationException(
                "ORDER_CURRENCY_UNSUPPORTED",
                "currency",
                "Currency is not supported");
    }
}
```

Mã lỗi nên ổn định qua các phiên bản ứng dụng để dashboard, quy trình hỗ trợ và công cụ replay có thể phân nhóm. Message lỗi không nên chứa password, token, thông tin thẻ hoặc toàn bộ payload nhạy cảm. Nếu cần giá trị trường để điều tra, hãy áp dụng masking và chính sách lưu trữ phù hợp.

### Dùng Bean Validation

Jakarta Bean Validation có thể kiểm tra ràng buộc cấu trúc như `@NotNull`, `@Positive`, `@Size` và `@Pattern`:

```java
public record OrderCreated(
        @NotBlank String eventId,
        @NotBlank String orderId,
        @Positive int quantity,
        @NotBlank String currency) {
}
```

Có thể gọi `Validator` từ service hoặc dùng tích hợp validation của Spring theo cách phù hợp với listener signature. Cần chuyển violation thành exception nghiệp vụ có mã lỗi để error handler phân loại nhất quán. Không phải mọi ràng buộc Bean Validation đều đủ để xác nhận business rule; ví dụ `@Positive` kiểm tra số lượng dương nhưng không biết customer có được phép đặt sản phẩm đó hay không.

## 5. Chọn cách xử lý: reject, retry hay quarantine

Không nên dùng một chính sách duy nhất cho mọi validation failure. Quyết định dựa trên khả năng điều kiện thay đổi, tác động nghiệp vụ và khả năng phục hồi.

| Tình huống | Xử lý phù hợp | Lý do |
|---|---|---|
| Dữ liệu sai vĩnh viễn | Reject có mã lỗi hoặc chuyển quarantine/DLT | Retry không sửa được payload. |
| Điều kiện phụ thuộc có thể xuất hiện sau | Retry có giới hạn hoặc luồng chờ | Có khả năng xử lý thành công khi dữ liệu sẵn sàng. |
| State/version conflict có quy tắc bù | Reconcile hoặc từ chối theo domain policy | Retry mù quáng có thể không thay đổi kết quả. |
| Database/network tạm thời | Retry technical failure có backoff | Message có thể hợp lệ nhưng hệ thống chưa xử lý được. |
| Không thể xác định tính hợp lệ vì dependency không phản hồi | Xử lý như technical/transient failure | Không kết luận message sai khi chưa kiểm tra được trạng thái. |

### Reject như một kết quả nghiệp vụ

Nếu việc từ chối là kết quả hợp lệ trong domain, service có thể ghi nhận trạng thái rejected và trả về bình thường. Tuy nhiên, phải bảo đảm kết quả reject được lưu bền vững trước khi listener kết thúc. Ví dụ, lưu `eventId`, `rejectionCode`, thời điểm và thông tin tham chiếu vào database trong transaction. Nếu lưu kết quả reject thất bại do database timeout, exception kỹ thuật cần được ném ra để container retry.

```java
@KafkaListener(topics = "orders.created")
public void onOrderCreated(OrderCreated event) {
    ValidationResult result = orderPolicy.validate(event);

    if (result.isRejected()) {
        rejectionService.recordRejectionIdempotently(
                event.eventId(), result.errorCode(), result.message());
        return; // Chỉ return sau khi rejection đã được lưu bền vững.
    }

    orderService.createIdempotently(event);
}
```

Ở đây, `recordRejectionIdempotently()` phải dùng transaction và khóa duy nhất theo event ID hoặc cơ chế tương đương. Nếu phương thức ném lỗi khi database không sẵn sàng, listener không được nuốt lỗi. Khi listener trả về bình thường, container có thể commit offset theo AckMode.

### Quarantine hoặc DLT

Nếu message cần được điều tra hoặc sửa dữ liệu rồi replay, có thể chuyển nó sang topic riêng như `orders.invalid` hoặc DLT. DLT giữ bản gốc và metadata nguồn, còn topic quarantine có thể được thiết kế như một luồng nghiệp vụ riêng cho các message bị từ chối.

Không dùng DLT như một nơi xóa message lỗi khỏi tầm nhìn. Cần có owner, retention, dashboard, quy trình xử lý và chính sách replay. Message nhạy cảm phải được bảo vệ tương tự topic nguồn.

## 6. Phân loại BusinessValidationException trong DefaultErrorHandler

Với Spring Kafka 2.8 trở lên, `DefaultErrorHandler` có thể phân loại exception để quyết định retry. Nếu `BusinessValidationException` biểu diễn lỗi vĩnh viễn, có thể đánh dấu loại exception này là không retry và cấu hình recoverer chuyển record sang DLT.

```java
@Bean
DefaultErrorHandler businessErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(
                    kafkaTemplate,
                    (record, exception) -> new TopicPartition(
                            record.topic() + ".DLT",
                            record.partition()));

    DefaultErrorHandler handler = new DefaultErrorHandler(
            recoverer,
            new ExponentialBackOffWithMaxRetries(3));

    handler.addNotRetryableExceptions(
            BusinessValidationException.class);

    return handler;
}
```

Trong ví dụ này, lỗi nghiệp vụ vĩnh viễn được đưa thẳng đến recovery thay vì retry nhiều lần. Các exception khác có thể được retry theo backoff mặc định của handler hoặc cấu hình bổ sung. Nếu muốn retry một số business precondition tạm thời, hãy dùng exception type riêng, ví dụ `BusinessStateNotReadyException`, và không đánh dấu nó là non-retryable.

Topic DLT phải tồn tại và có partition phù hợp nếu resolver gửi record về đúng partition nguồn. Nếu topic đích ít partition hơn nguồn, cần chọn partition hợp lệ bằng resolver. Producer dùng để publish DLT phải có serializer tương thích với key/value của record.

### Phân loại bằng exception cụ thể

Tránh đánh dấu `IllegalArgumentException` là không retry cho mọi listener nếu ứng dụng dùng exception này cả cho lỗi lập trình hoặc lỗi chuyển đổi tạm thời. Exception riêng giúp thể hiện ý nghĩa domain:

```java
public class BusinessStateNotReadyException extends RuntimeException {
    public BusinessStateNotReadyException(String message) {
        super(message);
    }
}

public class BusinessValidationException extends RuntimeException {
    public BusinessValidationException(String message) {
        super(message);
    }
}
```

Ví dụ `BusinessValidationException` là permanent, còn `BusinessStateNotReadyException` được retry trong thời gian giới hạn. Khi hết retry, hệ thống có thể chuyển state-not-ready sang một topic chờ riêng thay vì dùng cùng luồng với dữ liệu sai vĩnh viễn.

## 7. Retry blocking và retry topic cho business precondition

### Blocking retry

`DefaultErrorHandler` có thể retry ngay trong luồng xử lý partition với backoff. Cách này giữ record lỗi ở vị trí cần xử lý trước khi consumer tiếp tục, phù hợp khi thứ tự partition là bắt buộc và thời gian chờ không quá dài.

Nhược điểm là record lỗi có thể chặn các record phía sau trong cùng partition. Nếu lỗi là “customer chưa được tạo”, các customer event hoặc order event đứng sau có thể không được xử lý để giải quyết chính điều kiện đang thiếu. Cần kiểm tra dependency ordering trước khi chọn blocking retry.

### Retry topic

Spring Kafka hỗ trợ non-blocking retry bằng `@RetryableTopic` ở các phiên bản phù hợp. Message được chuyển sang retry topic và xử lý lại sau khoảng backoff. Topic gốc có thể tiếp tục với record sau.

Ví dụ khái quát:

```java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(delay = 2_000, multiplier = 2.0),
        include = BusinessStateNotReadyException.class,
        exclude = BusinessValidationException.class)
@KafkaListener(topics = "orders.created")
public void onOrderCreated(OrderCreated event) {
    orderService.create(event);
}
```

Đây là ví dụ minh họa; các thuộc tính annotation và hỗ trợ exception filtering phụ thuộc phiên bản Spring Kafka. Kiểm tra API tương ứng trong dự án. Non-blocking retry có thể làm record sau được xử lý trước record đang retry, vì vậy không phù hợp với mọi nghiệp vụ cần thứ tự nghiêm ngặt. Không áp dụng retry topic cho mọi exception nếu chỉ một số business precondition có thể hồi phục.

### Chọn deadline thay vì retry vô hạn

Business precondition thường có một thời hạn hợp lý. Ví dụ customer event dự kiến được áp dụng trong 30 giây. Hãy định nghĩa tổng retry window, số attempt, backoff và hành động sau deadline. Khi hết thời hạn, chuyển message sang trạng thái chờ điều tra hoặc DLT có mã lỗi rõ ràng.

Retry vô hạn có thể làm tăng backlog, giữ partition, tăng chi phí và che giấu việc producer phát sự kiện sai thứ tự. Hãy theo dõi tuổi của message trong retry topic và số lần thử, không chỉ số lượng record.

## 8. Bảo toàn dữ liệu và metadata khi chuyển DLT

Khi chuyển message lỗi sang DLT/quarantine, cần lưu đủ thông tin để tái hiện và điều tra:

- Topic, partition và offset nguồn.
- Key, timestamp và headers gốc.
- `eventId`, correlation ID và aggregate ID nếu có.
- Validation error code, field hoặc rule bị vi phạm.
- Exception class, thời điểm lỗi và số lần thử.
- Phiên bản ứng dụng, schema hoặc rule version nếu có thể xác định.

Spring Kafka `DeadLetterPublishingRecoverer` có thể bổ sung các header chứa topic/partition/offset nguồn và thông tin exception. Các tên header cụ thể được cung cấp qua `KafkaHeaders`, ví dụ `DLT_ORIGINAL_TOPIC`, `DLT_ORIGINAL_PARTITION`, `DLT_ORIGINAL_OFFSET`, `DLT_EXCEPTION_FQCN` và `DLT_EXCEPTION_MESSAGE`. Cần kiểm tra đúng header API của phiên bản đang sử dụng.

Nếu exception message chứa dữ liệu nhạy cảm, không lưu nguyên văn vào header hoặc log. Chuyển thông tin chi tiết vào kho có kiểm soát quyền truy cập và chỉ đưa mã tham chiếu vào message DLT.

## 9. Replay sau khi sửa business rule hoặc dữ liệu

Replay là thao tác đưa message đã bị quarantine/DLT trở lại luồng xử lý. Trước khi replay, cần biết vì sao message bị từ chối và điều gì đã thay đổi:

- Payload được sửa do producer phát sai dữ liệu.
- Business rule được cập nhật và message cũ giờ đã hợp lệ.
- Dependency đã sẵn sàng, ví dụ customer đã được tạo.
- Một lỗi trong code validation đã được khắc phục.
- Message cần được xử lý bù bằng một event mới thay vì phát lại nguyên bản.

Không phải mọi message DLT đều nên replay. Một số message là yêu cầu bị từ chối đúng theo chính sách tại thời điểm xử lý; nếu business policy không thay đổi, replay chỉ tạo thêm một lần từ chối.

### Quy trình replay có kiểm soát

1. Phân loại DLT theo error code, source topic và phiên bản ứng dụng.
2. Xác nhận nguyên nhân gốc và quyết định payload có cần sửa không.
3. Kiểm tra event ID đã được xử lý hoặc từ chối trước đó chưa.
4. Thử replay một số message trong môi trường kiểm soát hoặc theo lô nhỏ.
5. Giới hạn tốc độ để không gây tải đột biến cho consumer và downstream.
6. Theo dõi kết quả accepted/rejected, duplicate và lỗi mới.
7. Ghi lại người thực hiện, thời gian, số lượng, nguồn DLT và kết quả replay.

Giữ nguyên `eventId` khi replay cùng một sự kiện để cơ chế idempotency nhận diện duplicate. Nếu cần sửa payload, lưu liên kết giữa message gốc và phiên bản đã sửa; không âm thầm ghi đè bằng chứng ban đầu.

### Idempotency trong consumer

Consumer nên dùng `eventId` hoặc khóa nghiệp vụ ổn định để tránh áp dụng cùng một event nhiều lần. Một inbox table với unique constraint có thể ghi nhận event đã xử lý trong cùng transaction database với cập nhật nghiệp vụ. Khi replay, insert trùng được nhận diện và tác động không bị lặp.

Nếu kết quả từ chối cũng cần được lưu, hãy ghi rejection với event ID và error code theo cách idempotent. Nhờ đó, replay cùng message không tạo nhiều bản ghi từ chối hoặc thông báo trùng.

## 10. Observability cho business validation failure

Đội vận hành cần phân biệt tỷ lệ business rejection với technical failure. Nếu chỉ theo dõi tổng exception, một đợt dữ liệu sai từ producer có thể bị nhầm với database outage hoặc network incident.

| Chỉ số | Phân nhóm | Mục đích |
|---|---|---|
| Validation failure count | `errorCode`, topic, producer/source, schema version | Tìm rule hoặc nguồn phát sinh dữ liệu sai. |
| Rejection rate | accepted/rejected theo topic và thời gian | Phát hiện thay đổi bất thường trong chất lượng dữ liệu. |
| Retry count | exception type, retry topic, attempt | Phát hiện precondition tạm thời kéo dài hoặc retry policy quá rộng. |
| DLT/quarantine rate | source topic, error code, thời gian | Theo dõi message cần điều tra và mức độ tích tụ. |
| Message age | thời gian từ event timestamp đến xử lý/replay | Phát hiện message nằm lâu trong retry hoặc quarantine. |
| Replay outcome | accepted, rejected, duplicate, failed | Đo hiệu quả khắc phục và kiểm soát tác động. |
| Technical error rate | database, network, timeout, authentication | Tách sự cố hạ tầng khỏi lỗi nghiệp vụ. |

Log có cấu trúc nên chứa `eventId`, topic, partition, offset, error code, field/rule, exception type, attempt và correlation ID. Không dùng `eventId` hoặc order ID làm metric label có cardinality cao; dùng chúng trong log/trace, còn metric label nên là các nhóm hữu hạn như error code hoặc topic.

Dashboard nên có tỷ lệ rejected theo thời gian, top error code, số message trong DLT, tuổi message lâu nhất và tỷ lệ replay thành công. Cảnh báo khi rejection rate tăng đột ngột, DLT backlog vượt ngưỡng hoặc một error code mới xuất hiện với số lượng lớn.

## 11. Runbook theo tình huống

### Validation failure tăng đột biến sau khi triển khai producer

1. Nhóm message theo `errorCode`, source topic, producer application và schema version.
2. Xác định thời điểm bắt đầu và so sánh với phiên bản producer vừa triển khai.
3. Lấy một số record đại diện từ DLT/quarantine, kiểm tra metadata và payload theo chính sách dữ liệu.
4. Xác định producer phát sai contract hay consumer vừa thay đổi business rule.
5. Dừng hoặc giới hạn nguồn phát sinh dữ liệu sai nếu cần; tránh retry hàng loạt.
6. Sửa producer/schema hoặc phối hợp thay đổi rule có kiểm soát.
7. Replay lô nhỏ sau khi xác nhận dữ liệu hợp lệ và theo dõi kết quả.

### Consumer retry liên tục vì customer hoặc aggregate chưa tồn tại

1. Xác định đây là dependency tạm thời hay ID sai vĩnh viễn.
2. Đối chiếu event time, partition/key và thứ tự publish của các event liên quan.
3. Kiểm tra consumer group của dependency có lag hoặc lỗi không.
4. Chọn blocking retry, retry topic hoặc luồng chờ theo yêu cầu thứ tự và deadline.
5. Đặt giới hạn attempt/time window; sau deadline chuyển sang quarantine hoặc xử lý bù.
6. Theo dõi tuổi message và tỷ lệ precondition được giải quyết.

### Message bị chuyển DLT dù có thể hợp lệ

1. Kiểm tra exception type và classification trong `DefaultErrorHandler`.
2. Xác định exception có bị đánh dấu non-retryable quá rộng không.
3. Kiểm tra rule version, dữ liệu tham chiếu và trạng thái dependency tại thời điểm xử lý.
4. Sửa exception classification hoặc rule theo đúng semantics.
5. Kiểm tra khả năng replay, idempotency và số lượng message bị ảnh hưởng trước khi chạy lại.

### DLT publish thất bại

1. Kiểm tra exception từ `DeadLetterPublishingRecoverer` và future gửi DLT.
2. Xác nhận topic đích tồn tại, partition resolver hợp lệ và serializer tương thích.
3. Kiểm tra ACL, broker availability, producer timeout và header size.
4. Xác nhận error handler không coi recovery thất bại là thành công và commit offset nguồn.
5. Khôi phục quyền/kết nối/cấu hình rồi để record được xử lý lại theo policy.

### Replay tạo duplicate hoặc trạng thái sai

1. Dừng replay nếu phát hiện tác động nghiệp vụ trùng.
2. Đối chiếu event ID gốc, event ID đã sửa và trạng thái inbox/rejection.
3. Kiểm tra idempotency key có được giữ nguyên qua replay không.
4. Xác định message đã được áp dụng một phần ở hệ thống ngoài Kafka hay chưa.
5. Bổ sung cơ chế deduplication hoặc thao tác bù trước khi tiếp tục.
6. Replay thử một lô nhỏ và xác nhận trạng thái database/đích nhận.

## 12. Bảng kiểm soát business validation failure

| Điểm kiểm soát | Câu hỏi cần trả lời | Bằng chứng vận hành |
|---|---|---|
| Contract | Payload có đúng schema và cấu trúc không? | Schema version, deserialize result và validation errors. |
| Business rule | Rule nào bị vi phạm và có thể thay đổi theo thời gian không? | Error code, rule version và dữ liệu tham chiếu. |
| Classification | Lỗi là permanent rejection, transient precondition hay technical failure? | Exception type và error handler classification. |
| Retry | Có retry đúng nhóm lỗi, có deadline và backoff không? | Attempt count, retry age và retry topic metrics. |
| Recovery | Message đã được lưu bền vững vào DLT/quarantine chưa? | DLT publish result, source metadata và recovery exception. |
| Rejection | Kết quả từ chối có được ghi idempotent không? | Event ID, rejection code và database transaction. |
| Replay | Có điều kiện replay, giới hạn tốc độ và audit trail không? | Replay batch ID, operator, count và outcome. |
| Observability | Có tách business rejection khỏi technical errors không? | Dashboard theo error code, DLT backlog và technical error rate. |
| Data protection | Log/DLT có tránh lộ payload nhạy cảm không? | Masking, ACL, retention và audit access. |

Business validation failure cần được xem là một kết quả phân loại của luồng message. Dữ liệu sai vĩnh viễn nên được từ chối hoặc quarantine với mã lỗi rõ ràng; điều kiện nghiệp vụ có thể thay đổi nên được retry có giới hạn; sự cố kỹ thuật cần chính sách phục hồi riêng. Khi consumer giữ metadata nguồn, ghi nhận kết quả reject idempotent và kiểm soát replay, đội vận hành có thể khắc phục dữ liệu lỗi mà vẫn giữ được tính đúng đắn của trạng thái nghiệp vụ.
