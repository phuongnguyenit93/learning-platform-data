# Retryable exception

Trong Spring Kafka, một exception phát sinh khi listener xử lý record không nhất thiết có cùng cách khắc phục. Lỗi timeout do dịch vụ phụ thuộc tạm thời không khả dụng có thể biến mất sau vài giây; payload sai định dạng hoặc vi phạm quy tắc nghiệp vụ thường vẫn thất bại dù được gửi lại nhiều lần. Vì vậy, hệ thống cần phân loại exception để quyết định record nào được retry, retry bao nhiêu lần, chờ bao lâu và khi nào chuyển sang luồng phục hồi như dead-letter topic (DLT).

Một exception được xem là **retryable** khi việc thử xử lý lại có cơ hội thành công sau khi chờ hoặc sau khi một điều kiện tạm thời được khôi phục. Exception **non-retryable** biểu thị lỗi không thể tự khắc phục bằng cách chạy lại cùng record trong cùng điều kiện. Phân loại này là quyết định vận hành và nghiệp vụ, không chỉ là thuộc tính của class Java.

Spring Kafka cung cấp các cơ chế như `DefaultErrorHandler`, exception classification, backoff, `DeadLetterPublishingRecoverer` và retry topics qua `@RetryableTopic`. Các cơ chế này cho phép triển khai chính sách retry rõ ràng, nhưng không tự làm cho thao tác nghiệp vụ idempotent hoặc bảo đảm record sẽ được xử lý thành công cuối cùng.

## 1. Retryable exception là gì?

Retryable exception là loại lỗi mà ứng dụng cho phép thử xử lý lại record. Việc thử lại có ý nghĩa khi nguyên nhân có khả năng thay đổi theo thời gian, chẳng hạn:

- Database tạm thời không nhận kết nối.
- HTTP service trả về timeout hoặc lỗi server tạm thời.
- Broker hoặc network vừa trải qua một lần chuyển leader.
- Một tài nguyên đang bị khóa và có thể được giải phóng.
- Một dependency bị throttling và có thể phục hồi sau khoảng chờ.

Non-retryable exception thường chỉ ra record hoặc yêu cầu không hợp lệ:

- Payload thiếu trường bắt buộc hoặc sai định dạng.
- Giá trị nằm ngoài miền nghiệp vụ cho phép.
- Event type không được consumer hỗ trợ.
- Schema không tương thích và cần producer phát lại dữ liệu đúng định dạng.
- Một thao tác bị từ chối vĩnh viễn theo chính sách nghiệp vụ.

Một số lỗi cần phân loại theo ngữ cảnh. HTTP 404 có thể là lỗi vĩnh viễn nếu resource không tồn tại, nhưng có thể là lỗi tạm thời nếu service đọc dữ liệu vừa tạo chưa đồng bộ. HTTP 409 có thể là xung đột cần retry sau khi làm mới trạng thái, hoặc là kết quả nghiệp vụ cuối cùng. Hãy phân loại dựa trên hợp đồng của dependency và ý nghĩa nghiệp vụ.

| Nhóm exception | Ví dụ | Chính sách thường dùng |
|---|---|---|
| Lỗi hạ tầng tạm thời | Timeout, connection reset, broker unavailable | Retry có backoff và giới hạn |
| Lỗi throttling | HTTP 429, quota tạm thời | Retry theo thời gian chờ được dependency khuyến nghị |
| Lỗi cạnh tranh dữ liệu | Deadlock, optimistic locking conflict | Retry hữu hạn nếu transaction có thể chạy lại an toàn |
| Lỗi dữ liệu | Validation failure, malformed payload | Không retry cùng payload; chuyển DLT hoặc luồng sửa dữ liệu |
| Lỗi cấu hình/quyền | ACL sai, credential hết hạn, topic không tồn tại | Cảnh báo và sửa cấu hình; retry dày đặc thường không hữu ích |
| Lỗi nghiệp vụ cuối cùng | Đơn hàng đã bị hủy, thao tác không được phép | Xử lý theo kết quả nghiệp vụ, không retry như lỗi hạ tầng |

## 2. Exception đi qua listener container như thế nào?

Với record listener đồng bộ, exception được ném ra từ phương thức listener sẽ được chuyển đến error handler của listener container. Error handler quyết định retry, bỏ qua, recover hoặc gửi record sang DLT.

~~~text
Kafka consumer poll
        |
        v
Listener nhận record
        |
        v
Thực hiện nghiệp vụ
        |
   +----+----+
   |         |
Thành công  Exception
   |         |
   v         v
Ack/commit  CommonErrorHandler
             |
       +-----+------+
       |            |
    Retry       Hết retry
       |            |
       v            v
  Listener lại   Recoverer / DLT
                    |
                    v
              Xác nhận recovery
~~~

Nếu listener hoàn tất bình thường, container xử lý acknowledgement theo ack mode đã cấu hình. Nếu listener ném exception, error handler phân loại exception và áp dụng backoff. Sau khi hết retry, recoverer có thể ghi record vào DLT hoặc thực hiện hành động phục hồi khác.

Exception xảy ra ngoài luồng listener mà container quản lý có thể không được error handler nhìn thấy. Ví dụ, listener gửi task vào executor rồi trả về; exception xảy ra sau đó trong worker thread không tự động quay về listener container. Với xử lý bất đồng bộ, ứng dụng phải chuyển exception đến failure handler riêng và chỉ acknowledge khi công việc đã hoàn tất hoặc recovery đã lưu record bền vững.

## 3. Phân loại exception trong DefaultErrorHandler

`DefaultErrorHandler` là error handler phổ biến cho record listener. Nó kết hợp exception classification, `BackOff` và recoverer để xử lý record thất bại.

Theo chính sách mặc định của các phiên bản Spring Kafka có `DefaultErrorHandler`, phần lớn exception được retry; một số exception được xem là fatal và không retry vì thường không thể khắc phục bằng cách gửi lại cùng record. Các loại thường được xếp vào nhóm fatal gồm:

- `DeserializationException`
- `MessageConversionException`
- `ConversionException`
- `MethodArgumentResolutionException`
- `NoSuchMethodException`
- `ClassCastException`

Danh sách mặc định và hành vi phân loại có thể thay đổi theo phiên bản. Hãy kiểm tra tài liệu Spring Kafka tương ứng với dependency đang chạy. Có thể điều chỉnh classification bằng các phương thức như `addNotRetryableExceptions(...)` và `addRetryableExceptions(...)`.

### 3.1. Đánh dấu exception là non-retryable

Ví dụ một ứng dụng không muốn retry payload sai hoặc lệnh nghiệp vụ bị từ chối:

~~~java
@Bean
DefaultErrorHandler kafkaErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);

    FixedBackOff backOff = new FixedBackOff(1_000L, 2L);

    DefaultErrorHandler handler =
            new DefaultErrorHandler(recoverer, backOff);

    handler.addNotRetryableExceptions(
            InvalidOrderException.class,
            UnsupportedEventTypeException.class);

    return handler;
}
~~~

Trong ví dụ, `FixedBackOff(1_000L, 2L)` đặt khoảng chờ một giây và cho phép hai lần retry sau lần xử lý ban đầu. Tổng số lần listener có thể được gọi trong trường hợp này là ba nếu record tiếp tục thất bại. Recoverer chuyển record đã hết retry hoặc thuộc loại non-retryable sang DLT theo cấu hình đích.

### 3.2. Đánh dấu exception là retryable

Có thể thêm exception vào nhóm retryable:

~~~java
handler.addRetryableExceptions(
        TemporaryInventoryException.class,
        RemoteServiceUnavailableException.class);
~~~

Việc thêm explicit retryable hữu ích khi ứng dụng đã tùy chỉnh classification, thay đổi default value hoặc muốn thể hiện rõ hợp đồng lỗi của dependency trong cấu hình. Nếu exception vốn đã được retry theo default policy, thêm nó lần nữa có thể không làm thay đổi hành vi.

Không nên đưa tất cả exception vào nhóm retryable một cách máy móc. `NullPointerException`, `IllegalArgumentException` hoặc lỗi lập trình thường không tự biến mất sau vài lần chạy lại; retry chúng có thể làm chậm xử lý và che khuất lỗi code.

### 3.3. Cấu hình classification theo chính sách

Khi có nhiều nhóm exception, hãy quản lý classification tập trung thay vì rải logic `instanceof` trong listener. Có thể dùng các API classification của Spring Kafka để khai báo class nào retryable và class nào không retryable.

Lưu ý rằng classification thường xét kiểu exception và có thể xét cả cause chain tùy cấu hình/phiên bản. Nếu exception nghiệp vụ được bọc trong `ListenerExecutionFailedException` hoặc exception wrapper khác, hãy xác nhận error handler nhận diện được exception gốc. Tránh dựa vào chuỗi message của exception vì message có thể thay đổi hoặc chứa dữ liệu động.

## 4. Thiết kế exception class rõ nghĩa

Exception type nên diễn đạt nguyên nhân và chính sách xử lý. Ví dụ:

~~~java
public class TemporaryInventoryException extends RuntimeException {
    public TemporaryInventoryException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class InvalidOrderException extends RuntimeException {
    public InvalidOrderException(String message) {
        super(message);
    }
}
~~~

Service gọi dependency có thể chuyển lỗi kỹ thuật thành exception có ý nghĩa:

~~~java
public Inventory reserve(String sku, int quantity) {
    try {
        return inventoryClient.reserve(sku, quantity);
    }
    catch (SocketTimeoutException ex) {
        throw new TemporaryInventoryException(
                "Inventory service timed out", ex);
    }
}
~~~

Không nên bắt mọi exception rồi bọc thành một exception retryable chung. Cách đó có thể biến lỗi validation, bug code, lỗi quyền và lỗi hạ tầng thành cùng một chính sách retry. Hãy giữ cause gốc để log và chẩn đoán, đồng thời phân loại dựa trên nguyên nhân thực sự.

### 4.1. Cause chain và exception wrapper

Một exception có thể được bọc qua nhiều tầng:

~~~text
ListenerExecutionFailedException
          |
          v
ServiceException
          |
          v
TemporaryInventoryException
          |
          v
SocketTimeoutException
~~~

Nếu classification chỉ nhìn exception ngoài cùng, chính sách có thể không khớp với exception gốc. Spring Kafka có hỗ trợ duyệt cause chain trong các API classification tương ứng; khả năng và mặc định phụ thuộc phiên bản. Hãy kiểm tra hành vi thực tế bằng integration test có exception wrapper.

Không phân loại chỉ dựa trên tên class chung như `RuntimeException` nếu trong hệ thống class đó đại diện cho nhiều nguyên nhân có chính sách khác nhau. Exception domain riêng giúp cấu hình dễ đọc và giảm nhầm lẫn.

## 5. Backoff và số lần retry

Retry ngay lập tức có thể tạo áp lực lớn lên dependency đang lỗi. Backoff đặt khoảng chờ giữa các lần thử để dependency có thời gian phục hồi và tránh retry storm.

Một số kiểu backoff:

| Kiểu | Cách hoạt động | Trường hợp phù hợp |
|---|---|---|
| Fixed | Mỗi lần retry chờ cùng một khoảng thời gian | Lỗi tạm thời đơn giản, cần chính sách dễ dự đoán |
| Exponential | Khoảng chờ tăng sau mỗi lần retry | Dependency cần thời gian phục hồi dài hơn |
| Exponential có max interval | Tăng dần nhưng không vượt mức tối đa | Cân bằng tốc độ phục hồi với giới hạn thời gian |
| Randomized/jitter | Thêm độ ngẫu nhiên vào khoảng chờ | Tránh nhiều consumer retry cùng thời điểm |

Ví dụ fixed backoff:

~~~java
new FixedBackOff(2_000L, 3L);
~~~

Giá trị trên cho phép ba lần retry, mỗi lần cách nhau hai giây sau lần xử lý ban đầu. Nếu record luôn thất bại, listener có thể được gọi tổng cộng bốn lần trước khi recovery.

Ví dụ exponential backoff:

~~~java
ExponentialBackOffWithMaxRetries backOff =
        new ExponentialBackOffWithMaxRetries(4);
backOff.setInitialInterval(1_000L);
backOff.setMultiplier(2.0);
backOff.setMaxInterval(10_000L);
~~~

Khoảng chờ tăng dần từ một giây, nhân đôi sau mỗi lần thử và bị giới hạn ở mười giây. `ExponentialBackOffWithMaxRetries(4)` biểu thị số lần retry theo API của Spring Kafka, tức bốn lần retry sau lần xử lý ban đầu. Cần kiểm tra phiên bản thư viện khi tính tổng số attempt và thời gian tối đa.

### 5.1. Tính tổng thời gian retry

Chính sách retry phải nằm trong ngân sách thời gian của nghiệp vụ. Nếu một record được phép hoàn tất trong tối đa 60 giây nhưng backoff và thời gian xử lý có thể kéo dài vài phút, record sẽ vi phạm SLA ngay cả khi cuối cùng thành công.

Tổng thời gian cần tính đến:

- Thời gian xử lý ban đầu.
- Số lần retry.
- Khoảng backoff giữa các lần thử.
- Thời gian mỗi lần gọi dependency.
- Thời gian publish DLT hoặc recovery.
- Thời gian consumer bị pause hoặc chờ record trong retry topic.

Không chỉ tính tổng khoảng backoff; một request timeout 30 giây lặp lại ba lần có thể chiếm phần lớn thời gian dù backoff ngắn.

## 6. Blocking retry với DefaultErrorHandler

Blocking retry thực hiện lại record trong luồng xử lý của listener container. Record lỗi có thể được seek/redeliver theo chính sách của error handler; các record sau trong cùng partition có thể phải chờ tùy cách container xử lý.

Ưu điểm:

- Dễ hiểu và cấu hình trong cùng listener container.
- Có thể giữ thứ tự xử lý trong partition tốt hơn so với chuyển record sang retry topic.
- Phù hợp với lỗi tạm thời có thời gian phục hồi ngắn.
- Không cần tạo thêm retry topic cho từng cấp backoff.

Đánh đổi:

- Consumer thread bị chiếm trong thời gian retry/backoff.
- Một record lỗi có thể làm chậm các record phía sau trong partition.
- Retry dài có thể làm tăng consumer lag hoặc tương tác với `max.poll.interval.ms`.
- Một lỗi dependency diện rộng có thể khiến nhiều consumer cùng retry và tạo thêm tải.

Blocking retry thường phù hợp khi dependency phục hồi nhanh và thứ tự trong partition quan trọng. Hãy giới hạn retry và backoff, đồng thời theo dõi thời gian xử lý và lag.

## 7. Non-blocking retry với retry topics

Spring Kafka hỗ trợ non-blocking retry bằng `@RetryableTopic`. Khi listener thất bại, record được chuyển sang topic retry phù hợp với mức backoff. Consumer của topic chính có thể tiếp tục xử lý các record tiếp theo trong khi record lỗi chờ đến lượt retry.

Ví dụ:

~~~java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(
                delay = 1_000,
                multiplier = 2.0,
                maxDelay = 10_000),
        include = {
                TemporaryInventoryException.class,
                RemoteServiceUnavailableException.class
        },
        exclude = {
                InvalidOrderException.class
        },
        dltTopicSuffix = ".DLT")
@KafkaListener(topics = "orders", groupId = "billing")
public void consume(OrderCreated event) {
    billingService.process(event);
}
~~~

Trong annotation, `attempts` là tổng số lần thử theo quy ước của retry topic, bao gồm lần xử lý ban đầu. Ví dụ `attempts = "4"` thường có nghĩa một lần xử lý chính và tối đa ba lần retry. Hãy kiểm tra phiên bản Spring Kafka và exception classification thực tế, đặc biệt khi dùng `include`, `exclude` hoặc cấu hình retry topic tập trung.

Non-blocking retry phù hợp với lỗi cần chờ lâu hơn hoặc khi không muốn một record lỗi chặn toàn bộ tiến trình của partition chính. Tuy nhiên, record được retry có thể quay lại sau các record mới hơn. Vì vậy, thứ tự nghiệp vụ giữa các event cùng key có thể thay đổi.

Không dùng retry topic nếu nghiệp vụ bắt buộc mọi record của partition phải hoàn tất theo thứ tự ban đầu mà chưa có cơ chế bảo vệ thứ tự. Có thể cần blocking retry hoặc thiết kế workflow theo aggregate/version.

## 8. Phân loại exception trong retry topics

Retry topic có cơ chế phân loại exception riêng. Có thể khai báo class được retry bằng `include`, class không retry bằng `exclude`, hoặc cấu hình tên class qua các thuộc tính tương ứng tùy API phiên bản.

Các nguyên tắc:

- Chỉ đưa exception tạm thời vào danh sách retry khi việc thử lại có cơ hội thành công.
- Đưa exception dữ liệu và nghiệp vụ cuối cùng vào nhóm không retry.
- Kiểm tra cách cause chain được xét khi listener ném exception wrapper.
- Không để `include` và `exclude` mâu thuẫn mà không hiểu precedence.
- Kiểm tra số attempt, tên retry topic, backoff và DLT được tạo ra như mong đợi.

Retry topic có thể tự tạo topic nếu cấu hình cho phép, nhưng môi trường production thường cần quản lý topic, partition, replication, ACL và retention theo quy trình hạ tầng. Không nên chỉ dựa vào auto-create mà bỏ qua chính sách cluster.

## 9. Deserialization và exception trước khi listener chạy

Không phải mọi exception đều phát sinh trong thân listener. Nếu consumer không deserialize được key hoặc value, listener có thể chưa nhận được object để xử lý. Đây là lý do các lỗi deserialization thường được phân loại fatal/non-retryable theo mặc định: gửi lại cùng bytes với cùng deserializer thường không sửa được payload.

Spring Kafka cung cấp `ErrorHandlingDeserializer` để bọc deserializer thực tế và chuyển thông tin lỗi cho cơ chế error handling. Cần cấu hình delegate đúng với định dạng producer và kiểm tra cách raw payload được giữ lại cho recovery.

Khi gặp lỗi deserialization:

1. Xác định payload và serializer/schema version đã phát.
2. Kiểm tra consumer deserializer, trusted packages và type header nếu dùng JSON.
3. Kiểm tra thay đổi schema gần nhất.
4. Giữ raw payload nếu chính sách dữ liệu cho phép.
5. Chuyển record lỗi vào DLT hoặc luồng điều tra.
6. Sửa producer/schema/consumer rồi replay có kiểm soát.

Retry cùng một payload không hợp lệ thường chỉ làm tăng lag và log noise. Chỉ retry deserialization nếu nguyên nhân thật sự tạm thời, chẳng hạn một thành phần schema lookup tạm thời không khả dụng và exception được phân loại phù hợp.

## 10. Retryable exception và idempotency

At-least-once delivery có thể giao lại record sau khi listener đã thực hiện một phần tác động nghiệp vụ nhưng chưa commit offset. Retry do exception cũng có thể chạy lại cùng một record nhiều lần. Do đó, mọi side effect cần có cơ chế chống xử lý trùng.

Với database, có thể lưu event id trong inbox table cùng transaction với thay đổi nghiệp vụ:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Luồng xử lý:

1. Bắt đầu database transaction.
2. Ghi event id vào `processed_events`.
3. Nếu event id đã tồn tại, không lặp lại tác động nghiệp vụ.
4. Nếu event id mới, thực hiện cập nhật nghiệp vụ.
5. Commit database transaction.
6. Để listener hoàn tất và container commit offset.

Với HTTP API, sử dụng idempotency key nếu API đích hỗ trợ. Nếu timeout khiến kết quả request không rõ, cần đối soát trước khi gửi lại một thao tác không thể lặp.

Không tạo event id mới cho mỗi lần retry. Retry và DLT phải giữ định danh gốc để deduplication nhận ra đây vẫn là cùng một sự kiện.

## 11. Retry nhiều tầng và retry storm

Một record có thể bị retry ở nhiều tầng:

- `DefaultErrorHandler` trong Spring Kafka.
- Retry topic qua `@RetryableTopic`.
- Spring Retry hoặc retry trong service.
- HTTP client retry.
- JDBC/database retry.
- Retry của chính dependency.

Nếu mỗi tầng có ba lần retry, tổng số lần gọi dependency có thể nhân lên rất nhanh. Ví dụ, ba tầng với ba attempt mỗi tầng có thể tạo tới 27 lần gọi trong một số cách lồng retry.

Hãy xác định một tầng chịu trách nhiệm chính cho từng loại lỗi. Nếu dependency client đã retry timeout, listener error handler không nên lặp lại một chuỗi retry dài mà không tính tổng thời gian. Đặt giới hạn attempt và deadline tổng thể, đồng thời truyền correlation id và event id qua các lần thử.

Retry storm xảy ra khi nhiều consumer cùng retry liên tục vào một dependency đang lỗi. Backoff có jitter, giới hạn concurrency, circuit breaker và rate limit có thể giảm áp lực. Khi dependency phục hồi, tránh để toàn bộ backlog retry dồn vào nó cùng lúc.

## 12. Chọn retry policy theo loại lỗi

Một bảng chính sách giúp đội phát triển và vận hành dùng cùng một cách phân loại:

| Exception/condition | Retry? | Backoff | Hành động sau khi hết retry |
|---|---|---|---|
| Socket timeout tạm thời | Có | Exponential, giới hạn | DLT và alert nếu vẫn lỗi |
| HTTP 503 | Có | Exponential có jitter | DLT hoặc retry topic dài hơn theo SLA |
| HTTP 429 | Có, theo hợp đồng API | Tôn trọng Retry-After nếu có | DLT/alert khi vượt deadline |
| Database deadlock | Có giới hạn | Ngắn, có jitter | DLT hoặc xử lý thủ công |
| Invalid payload | Không | Không retry | DLT và sửa dữ liệu |
| Unsupported event type | Không | Không retry | DLT, kiểm tra producer/consumer compatibility |
| Authorization failure | Thường không retry dày | Có thể thử lại sau khi credential/config được sửa | Alert vận hành |
| Business rule rejection | Tùy kết quả nghiệp vụ | Thường không retry | Ghi nhận kết quả từ chối |

Đây là gợi ý khởi đầu. Một lỗi chỉ nên được retry khi dependency có thể phục hồi trong thời hạn cho phép và việc gọi lại không tạo side effect trùng.

## 13. DLT và recovery sau khi hết retry

Khi một exception không retry hoặc record đã hết số lần retry, recoverer có thể gửi record sang DLT. DLT giúp consumer group tiếp tục xử lý các record khác trong khi giữ lại dữ liệu cần điều tra.

Thông tin nên được giữ:

- Topic, partition và offset nguồn.
- Key và event id gốc.
- Exception class và thông điệp lỗi.
- Thời điểm thất bại và số lần thử nếu có.
- Correlation id hoặc trace id để tìm log liên quan.
- Schema version hoặc metadata cần cho replay.

Không ghi toàn bộ payload nhạy cảm vào log. Hạn chế quyền đọc DLT và đặt retention đủ dài cho quy trình điều tra.

### 13.1. Không xác nhận offset nguồn trước khi recovery bền vững

Nếu publish DLT thất bại, không được coi record đã recover thành công. Hãy cấu hình recoverer và error handler để lỗi gửi DLT được quan sát và không commit offset nguồn theo cách làm mất record. Với các phiên bản Spring Kafka hỗ trợ, có thể cấu hình recoverer chờ kết quả publish và báo lỗi nếu gửi thất bại.

### 13.2. Replay DLT

Replay phải giữ event id gốc và được thực hiện sau khi nguyên nhân đã được sửa. Trước khi replay:

1. Phân loại record và xác định nguyên nhân.
2. Sửa code, schema, dữ liệu hoặc dependency.
3. Kiểm thử với một số record đại diện.
4. Replay theo batch có giới hạn tốc độ.
5. Theo dõi số record thành công và số record tiếp tục lỗi.
6. Đối soát tác động nghiệp vụ để phát hiện duplicate hoặc missing event.

Không replay toàn bộ DLT tự động ngay sau deploy mà chưa kiểm tra nguyên nhân và side effect.

## 14. Quan sát retry và exception classification

Metrics và log cần cho biết record đang retry vì lỗi gì, đã thử bao nhiêu lần và còn bao lâu trước khi hết deadline.

Metrics nên theo dõi:

- Listener exception rate theo nhóm lỗi.
- Retry count/rate và thời gian backoff.
- Số record chuyển vào retry topic.
- DLT incoming rate và tuổi record cũ nhất.
- Consumer lag và processing duration.
- Dependency timeout/error rate.
- Số lần publish DLT thất bại.

Log nên có event id, topic, partition, offset, consumer group, exception class và attempt number nếu có. Không dùng event id hoặc offset làm metric tag có cardinality cao; lưu chúng trong log có cấu trúc để truy vấn từng record.

Alert nên dựa trên xu hướng và SLA:

- Retry rate tăng kéo dài.
- Một exception class xuất hiện đột biến sau deploy.
- DLT có record mới hoặc tăng nhanh.
- Tuổi record cũ nhất vượt thời hạn nghiệp vụ.
- Dependency error rate tăng đồng thời với retry.
- Consumer lag tăng dù incoming rate không đổi.

## 15. Runbook cho các tình huống thường gặp

### 15.1. Retry tăng đột biến

1. Nhóm exception theo class và dependency.
2. Xác định thời điểm bắt đầu và thay đổi release/config gần nhất.
3. Kiểm tra dependency latency, timeout, throttling và health.
4. Xác định retry có đang tạo tải bổ sung lên dependency không.
5. Giới hạn retry hoặc concurrency theo chính sách nếu cần.
6. Theo dõi lag và thời gian phục hồi sau khi dependency ổn định.

### 15.2. Exception không retry dù được xem là tạm thời

1. Kiểm tra exception ngoài cùng và cause chain.
2. Xác nhận exception class đã được thêm vào classification đúng error handler.
3. Kiểm tra listener có dùng đúng container factory không.
4. Xác nhận không có classification khác đánh dấu exception non-retryable.
5. Kiểm tra phiên bản Spring Kafka và hành vi cause traversal.
6. Tạo integration test cho exception wrapper thực tế.

### 15.3. Exception dữ liệu bị retry liên tục

1. Xác định class exception và record mẫu.
2. Kiểm tra classification mặc định và cấu hình tùy chỉnh.
3. Đánh dấu exception dữ liệu là non-retryable nếu gửi lại cùng payload không thể sửa lỗi.
4. Chuyển record sang DLT.
5. Sửa producer hoặc dữ liệu nguồn rồi replay có kiểm soát.

### 15.4. DLT tăng sau một lần deploy

1. Nhóm DLT theo exception class, schema version và listener.
2. So sánh thời điểm lỗi với release/config change.
3. Kiểm tra serialization, validation và dependency.
4. Rollback hoặc phát hành bản sửa nếu nguyên nhân nằm trong code.
5. Kiểm thử record đại diện trước khi replay.
6. Đối soát kết quả nghiệp vụ sau replay.

### 15.5. Consumer lag tăng dù retry có vẻ thành công

1. Kiểm tra blocking backoff có giữ partition quá lâu không.
2. Kiểm tra số tầng retry và tổng thời gian dependency call.
3. Nếu dùng retry topic, xem lag của cả topic chính và retry topics.
4. Kiểm tra hot partition và downstream capacity.
5. Điều chỉnh backoff/attempts theo SLA và quan sát tuổi record cũ nhất.

## 16. Kiểm thử exception classification

Không nên chỉ kiểm tra happy path. Integration test cần chứng minh exception được phân loại đúng và offset chỉ tiến lên sau khi xử lý hoặc recovery an toàn.

Các kịch bản cần có:

1. Một exception retryable thất bại hai lần rồi thành công.
2. Một exception retryable thất bại hết retry và được chuyển DLT.
3. Một exception non-retryable được chuyển recovery mà không retry.
4. Exception được bọc trong cause chain vẫn được phân loại đúng.
5. Publish DLT thất bại và nguồn không bị xác nhận mất record.
6. Consumer restart sau khi database commit nhưng trước offset commit; idempotency ngăn side effect lặp.
7. Dependency trả về 429/503 và backoff phù hợp.
8. Retry topic làm thay đổi thứ tự; nghiệp vụ vẫn xử lý đúng hoặc thiết kế chọn blocking retry.
9. Worker bất đồng bộ thất bại ngoài listener thread và failure handler nhận được exception.

Test nên kiểm tra số lần listener được gọi, topic nhận record, offset committed và kết quả nghiệp vụ. Không chỉ xác nhận exception đã được log.

## 17. Những lỗi thiết kế thường gặp

**Retry mọi exception:** Bug code, payload sai và lỗi nghiệp vụ cuối cùng không tự sửa sau retry. Hãy phân loại theo nguyên nhân.

**Retry vô hạn:** Một record lỗi có thể giữ partition hoặc tạo backlog không giới hạn. Đặt attempt và deadline tổng thể.

**Backoff quá ngắn:** Consumer có thể tạo retry storm vào dependency đang lỗi. Dùng backoff phù hợp và jitter khi cần.

**Bọc mọi lỗi thành một exception retryable:** Làm mất thông tin nguyên nhân và khiến lỗi vĩnh viễn bị retry.

**Không giữ cause gốc:** Khi chỉ còn wrapper chung, classification và điều tra trở nên khó khăn.

**Retry nhiều tầng không tính tổng:** Số lần gọi dependency có thể tăng theo cấp số nhân.

**Ack trước khi side effect bền vững:** Có thể mất tác động nghiệp vụ nếu record không được giao lại.

**Xem DLT là nơi lưu trữ vô thời hạn:** DLT cần ACL, retention, alert, ownership và quy trình replay.

**Cho rằng retry topic giữ thứ tự:** Non-blocking retry có thể cho phép record mới vượt qua record đang chờ retry.

## 18. Checklist triển khai

### Phân loại exception

- [ ] Đã phân biệt lỗi tạm thời, dữ liệu, cấu hình và nghiệp vụ.
- [ ] Exception class diễn đạt nguyên nhân đủ rõ.
- [ ] Cause chain được xử lý theo phiên bản Spring Kafka đang dùng.
- [ ] Default fatal/non-retryable classification đã được kiểm tra.
- [ ] Retryable và non-retryable exception được cấu hình tập trung.

### Retry policy

- [ ] Có số lần retry hữu hạn.
- [ ] Backoff phù hợp với dependency và SLA.
- [ ] Đã tính tổng thời gian xử lý và timeout của từng lần thử.
- [ ] Không chồng nhiều tầng retry ngoài dự kiến.
- [ ] Blocking retry hoặc retry topics được chọn theo yêu cầu thứ tự.

### Recovery và độ tin cậy

- [ ] Recoverer/DLT được cấu hình và có đủ partition, ACL, retention.
- [ ] Publish DLT thất bại không làm offset nguồn được xác nhận sai.
- [ ] Consumer idempotent khi record được giao lại.
- [ ] Replay có giới hạn tốc độ và có audit.
- [ ] Có metrics, alert và runbook cho retry/DLT.

### Kiểm thử

- [ ] Retryable exception được retry đúng số lần.
- [ ] Non-retryable exception không bị retry không cần thiết.
- [ ] Cause chain và exception wrapper được kiểm thử.
- [ ] DLT failure và consumer crash được kiểm thử.
- [ ] Side effect không bị lặp khi record được giao lại.

## Kết luận

Retryable exception xác định loại lỗi có cơ hội phục hồi khi thử lại record. Spring Kafka cho phép cấu hình classification trong `DefaultErrorHandler`, đặt backoff hữu hạn và chuyển record không thể xử lý sang recoverer hoặc DLT; retry topics hỗ trợ chờ lâu mà không giữ record ở luồng chính. Chính sách đúng cần dựa trên nguyên nhân lỗi, thời hạn nghiệp vụ, thứ tự partition và khả năng chịu duplicate. Hãy giữ exception type rõ nghĩa, giới hạn tổng retry, bảo đảm idempotency và kiểm thử cả đường recovery để record không bị mất khi dependency hoặc DLT gặp sự cố.
