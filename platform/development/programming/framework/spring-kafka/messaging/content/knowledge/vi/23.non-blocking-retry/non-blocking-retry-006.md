# Retry nhiều exception khác nhau với Non-blocking Retry

Trong Spring Kafka, non-blocking retry cho phép chuyển record lỗi sang retry topic thay vì giữ consumer thread chờ backoff. `@RetryableTopic` hỗ trợ phân loại nhiều exception: chỉ retry một nhóm exception được chọn, bỏ qua retry cho một nhóm exception khác, hoặc kiểm tra exception nằm bên trong chuỗi `cause`. Khi cần, ứng dụng còn có thể chuyển các loại lỗi khác nhau tới các dead-letter topic (DLT) riêng.

Điểm quan trọng là phân biệt hai quyết định:

- **Exception classification:** exception nào được retry, exception nào đi thẳng tới DLT.
- **DLT routing:** khi record phải tới DLT, chọn DLT nào dựa trên exception đã xảy ra.

Hai quyết định này có thể phối hợp nhưng không thay thế nhau. Ví dụ, `InvalidOrderException` có thể không được retry và đi thẳng tới `orders-validation-dlt`, trong khi `InventoryUnavailableException` được retry vài lần rồi mới đi tới `orders-dependency-dlt`.

## 1. Non-blocking retry xử lý exception như thế nào?

Khi listener ném exception, Spring Kafka xác định exception đó có thuộc nhóm được retry hay không. Nếu được retry và còn attempt, record được publish sang retry topic tương ứng với khoảng backoff. Retry consumer sẽ đọc lại record sau thời gian chờ. Nếu exception không được retry hoặc đã hết attempt, record được chuyển sang DLT theo cấu hình.

```mermaid
flowchart TD
    A[Main topic] --> B[@KafkaListener xử lý record]
    B --> C{Phân loại exception}
    C -->|Không retry| D[Chọn DLT theo exception]
    C -->|Được retry| E{Còn attempt?}
    E -->|Còn| F[Publish retry topic]
    F --> G[Retry consumer sau backoff]
    G --> B
    E -->|Hết attempt| D
    D --> H[DLT consumer / @DltHandler]
```

Với non-blocking retry, consumer của main topic có thể tiếp tục xử lý các record sau khi record lỗi được chuyển sang retry topic. Điều này giảm việc một record lỗi chặn cả partition, nhưng có thể làm thay đổi thứ tự xử lý nghiệp vụ: record đến sau có thể hoàn tất trước record đang chờ retry.

## 2. Phân biệt retry nhiều exception bằng include

`include` là allowlist: chỉ các kiểu exception được khai báo mới được retry theo policy của listener. Những exception khác không thuộc allowlist sẽ không đi qua retry topics và được chuyển tới DLT. Đây là cách phù hợp khi ứng dụng chỉ muốn retry một số lỗi tạm thời đã biết.

Ví dụ một dịch vụ đơn hàng phụ thuộc vào inventory và pricing:

```java
class InventoryUnavailableException extends RuntimeException {
    public InventoryUnavailableException(String message) {
        super(message);
    }
}

class PricingServiceUnavailableException extends RuntimeException {
    public PricingServiceUnavailableException(String message) {
        super(message);
    }
}

class InvalidOrderException extends RuntimeException {
    public InvalidOrderException(String message) {
        super(message);
    }
}
```

Chỉ retry hai lỗi phụ thuộc tạm thời:

```java
@Component
public class OrderListener {

    @RetryableTopic(
            attempts = "4",
            backoff = @Backoff(
                    delay = 1_000,
                    multiplier = 2.0,
                    maxDelay = 10_000),
            include = {
                    InventoryUnavailableException.class,
                    PricingServiceUnavailableException.class
            },
            traversingCauses = "true"
    )
    @KafkaListener(
            topics = "orders",
            groupId = "order-projection"
    )
    public void onOrder(OrderCreated event) {
        orderService.process(event);
    }
}
```

Trong ví dụ:

- `InventoryUnavailableException` và `PricingServiceUnavailableException` được retry.
- `InvalidOrderException` không nằm trong allowlist nên đi thẳng tới DLT.
- `attempts = "4"` tính cả lần xử lý ban đầu: một lần đầu và tối đa ba lần retry.
- Backoff tăng theo cấp số nhân: 1 giây, 2 giây, 4 giây, tối đa 10 giây.
- `traversingCauses = "true"` cho phép tìm exception được khai báo trong chuỗi `cause`.

Theo tài liệu Spring Kafka hiện hành, mặc định `attempts` là `3`, tức một lần ban đầu và hai lần retry; backoff mặc định là fixed delay 1 giây. Nên khai báo tường minh khi policy của hệ thống cần được review hoặc kiểm thử ổn định.

## 3. Dùng exclude khi muốn retry hầu hết exception

`exclude` là denylist: các exception được khai báo không được retry và sẽ đi thẳng tới DLT. Những exception khác được retry theo policy, ngoại trừ các exception nằm trong danh sách fatal toàn cục của Spring Kafka.

Ví dụ bỏ qua retry cho lỗi dữ liệu không thể tự sửa:

```java
@RetryableTopic(
        attempts = "5",
        backoff = @Backoff(delay = 2_000),
        exclude = {
                InvalidOrderException.class,
                UnsupportedCurrencyException.class,
                CustomerNotFoundException.class
        },
        traversingCauses = "true"
)
@KafkaListener(topics = "orders", groupId = "order-projection")
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
```

Chọn `include` khi chỉ có vài exception thực sự cần retry và muốn mặc định đưa lỗi lạ tới DLT. Chọn `exclude` khi phần lớn lỗi đều có thể tạm thời phục hồi và chỉ một nhóm lỗi nghiệp vụ cần loại khỏi retry.

Để policy dễ đọc, hãy chọn rõ chiến lược allowlist hoặc denylist cho từng listener. Nếu kết hợp cả `include` và `exclude`, cần kiểm tra quy tắc phân loại của phiên bản Spring Kafka đang dùng và viết test cho các trường hợp giao nhau; không nên dựa vào giả định về độ ưu tiên giữa hai danh sách.

## 4. Phân loại nhiều exception bằng RetryTopicConfigurationBuilder

Ngoài annotation, có thể khai báo policy bằng `RetryTopicConfigurationBuilder`. Cách này hữu ích khi muốn quản lý retry policy ở một class cấu hình và giới hạn nó cho các topic cụ thể.

```java
@Configuration
@EnableKafkaRetryTopic
public class OrderRetryConfiguration {

    @Bean
    public RetryTopicConfiguration orderRetryConfiguration(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {

        return RetryTopicConfigurationBuilder
                .newInstance()
                .includeTopics(List.of("orders"))
                .retryOn(List.of(
                        InventoryUnavailableException.class,
                        PricingServiceUnavailableException.class))
                .traversingCauses(true)
                .fixedBackOff(1_000L)
                .maxAttempts(4)
                .create(kafkaTemplate);
    }
}
```

Trong builder:

- `retryOn(List.of(...))` khai báo nhiều exception được retry.
- `notRetryOn(List.of(...))` khai báo nhiều exception không được retry.
- `traversingCauses(true)` bật kiểm tra chuỗi cause.
- `includeTopics(...)` giới hạn cấu hình vào topic `orders`.
- `fixedBackOff(...)` và `maxAttempts(...)` đặt lịch retry.

Nếu muốn dùng denylist, có thể thay `retryOn(...)` bằng:

```java
.notRetryOn(List.of(
        InvalidOrderException.class,
        UnsupportedCurrencyException.class))
```

Khi dùng `RetryTopicConfiguration` bean, cần bật retry-topic infrastructure theo hướng dẫn của phiên bản Spring Kafka. `@EnableKafkaRetryTopic` là cách bật infrastructure phổ biến. Nếu ứng dụng chọn mở rộng `RetryTopicConfigurationSupport` để cấu hình toàn cục, không đồng thời thêm `@EnableKafkaRetryTopic`; chỉ dùng một trong hai cách cấu hình global.

## 5. Cause traversal: exception bị bọc bên trong

Trong ứng dụng thực tế, exception nghiệp vụ thường bị bọc bởi exception ở tầng service, proxy hoặc adapter. Ví dụ:

```java
try {
    inventoryClient.reserve(event.orderId());
}
catch (SocketTimeoutException exception) {
    throw new InventoryUnavailableException(
            "Inventory request timed out", exception);
}
```

Listener có thể tiếp tục bọc exception:

```java
try {
    orderService.process(event);
}
catch (InventoryUnavailableException exception) {
    throw new RuntimeException("Order processing failed", exception);
}
```

Chuỗi exception có dạng:

```text
RuntimeException
  └── InventoryUnavailableException
        └── SocketTimeoutException
```

Nếu classifier chỉ xét exception ngoài cùng, `include = InventoryUnavailableException.class` có thể không khớp với `RuntimeException`. Bật cause traversal để classifier tìm loại exception trong chuỗi nguyên nhân:

```java
@RetryableTopic(
        include = {InventoryUnavailableException.class},
        traversingCauses = "true"
)
@KafkaListener(topics = "orders")
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
```

Mặc định Spring Kafka retry mọi exception và không duyệt cause khi không cấu hình include/exclude. Khi khai báo danh sách include hoặc exclude, API hiện hành mặc định bật cause traversal; tuy nhiên, nên đặt `traversingCauses` tường minh để policy không phụ thuộc default hoặc khác biệt phiên bản.

Cause traversal chỉ phân loại exception. Nó không tự unwrap, thay đổi exception được ném ra hoặc sửa lỗi gốc. Hãy giữ cause khi tạo exception mới bằng constructor có tham số `cause` để classifier và log có đủ thông tin.

## 6. Dùng includeNames và excludeNames

`@RetryableTopic` còn hỗ trợ `includeNames` và `excludeNames`, nhận tên class exception dưới dạng chuỗi. Cách này hữu ích khi không muốn tạo dependency compile-time tới class exception, chẳng hạn class nằm trong module tích hợp tùy chọn.

```java
@RetryableTopic(
        includeNames = {
                "com.acme.inventory.InventoryUnavailableException",
                "com.acme.pricing.PricingServiceUnavailableException"
        },
        traversingCauses = "true"
)
@KafkaListener(topics = "orders")
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
```

Tên class phải là fully qualified class name, phân biệt chính xác package và tên kiểu. Sai tên class có thể khiến exception không được phân loại như mong muốn. Nếu có thể tham chiếu trực tiếp class, `include` và `exclude` an toàn hơn vì compiler kiểm tra được kiểu.

## 7. Các exception fatal mặc định

Từ Spring Kafka 2.8.3, non-blocking retry có danh sách exception fatal toàn cục. Những lỗi này được chuyển thẳng tới DLT mà không tạo các lần retry, vì retry thường không thể sửa được nguyên nhân.

Danh sách mặc định được tài liệu Spring Kafka tham chiếu từ `DefaultErrorHandler`; các loại thường gặp gồm:

- `DeserializationException`.
- `MessageConversionException`.
- `ConversionException`.
- `MethodArgumentResolutionException`.
- `NoSuchMethodException`.
- `ClassCastException`.

Ví dụ, nếu payload không thể deserialize thành object hoặc listener method không nhận được kiểu tham số tương thích, gửi lại cùng bytes thường không giúp dữ liệu trở nên hợp lệ. Đưa record tới DLT ngay giúp tránh lặp retry vô ích.

Danh sách fatal là một lớp phân loại toàn cục, độc lập với policy include/exclude của từng listener. Khi điều tra vì sao một exception không xuất hiện trên retry topic, hãy kiểm tra cả classifier cục bộ lẫn danh sách fatal toàn cục.

## 8. Bổ sung exception vào danh sách fatal toàn cục

Nếu một loại exception cần đi thẳng DLT trên mọi listener sử dụng non-blocking retry, có thể thêm nó vào danh sách fatal toàn cục bằng cách mở rộng `RetryTopicConfigurationSupport`:

```java
@Configuration
@EnableKafka
public class GlobalRetryConfiguration extends RetryTopicConfigurationSupport {

    @Override
    protected void manageNonBlockingFatalExceptions(
            List<Class<? extends Throwable>> nonBlockingFatalExceptions) {

        nonBlockingFatalExceptions.add(InvalidMessageContractException.class);
    }
}
```

Ví dụ, `InvalidMessageContractException` biểu thị event không tuân thủ contract và không thể sửa bằng cách chờ dependency phục hồi. Thêm exception này vào danh sách fatal khiến record đi DLT mà không qua retry topics.

Chỉ dùng cấu hình global khi cùng một quyết định áp dụng cho toàn bộ non-blocking retry infrastructure. Nếu chỉ một listener có policy khác, ưu tiên `include` hoặc `exclude` trên listener đó.

Khi dùng `RetryTopicConfigurationSupport`, chỉ nên có một class cấu hình global mở rộng lớp này và dùng cách enable infrastructure theo tài liệu phiên bản đang chạy. Không kết hợp đồng thời với `@EnableKafkaRetryTopic`, vì có thể đăng ký trùng infrastructure beans.

## 9. Định tuyến nhiều loại exception tới DLT khác nhau

Phân loại retry trả lời câu hỏi “có retry không?”. `exceptionBasedDltRouting` trả lời câu hỏi “nếu record phải vào DLT thì gửi tới topic nào?”. Tính năng định tuyến DLT theo exception có từ Spring Kafka 3.2.0.

Ví dụ tách lỗi validation và lỗi dependency:

```java
@RetryableTopic(
        attempts = "4",
        include = {
                InventoryUnavailableException.class,
                PricingServiceUnavailableException.class
        },
        traversingCauses = "true",
        exceptionBasedDltRouting = {
                @ExceptionBasedDltDestination(
                        suffix = "-validation",
                        exceptions = {InvalidOrderException.class}
                ),
                @ExceptionBasedDltDestination(
                        suffix = "-dependency",
                        exceptions = {
                                InventoryUnavailableException.class,
                                PricingServiceUnavailableException.class
                        }
                )
        }
)
@KafkaListener(topics = "orders", groupId = "order-projection")
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
```

Với topic gốc `orders` và DLT suffix mặc định `-dlt`, các đích có thể là:

| Exception cuối cùng | Retry? | DLT đích |
|---|---|---|
| `InvalidOrderException` | Không, vì không nằm trong include | `orders-validation-dlt` |
| `InventoryUnavailableException` | Có, tới khi xử lý thành công hoặc hết attempt | `orders-dependency-dlt` nếu hết attempt |
| `PricingServiceUnavailableException` | Có, tới khi xử lý thành công hoặc hết attempt | `orders-dependency-dlt` nếu hết attempt |
| Exception khác | Không, vì không nằm trong include | DLT mặc định `orders-dlt` |

Suffix khai báo trong `@ExceptionBasedDltDestination` được đặt trước `dltTopicSuffix` chung. Việc định tuyến chỉ quyết định DLT cuối cùng; nó không tự thêm exception vào danh sách được retry.

## 10. Xử lý DLT bằng @DltHandler

Có thể khai báo phương thức `@DltHandler` trong cùng class với listener để xử lý record đã đi tới DLT:

```java
@DltHandler
public void onOrderDlt(OrderCreated event) {
    dltService.storeForInvestigation(event);
}
```

Nếu không khai báo `@DltHandler`, Spring Kafka tạo DLT consumer mặc định chỉ ghi log record. Trong production, nên quyết định rõ record DLT sẽ được lưu trữ, cảnh báo, tạo ticket hay chờ quy trình replay.

Nếu có nhiều DLT theo exception, handler cần có khả năng xác định nguồn lỗi hoặc dùng các listener riêng theo từng DLT topic. Không nên chỉ lưu payload mà bỏ qua exception metadata, topic gốc, partition, offset và số lần delivery.

## 11. Nhiều exception không đồng nghĩa nhiều retry topic

Các exception được phân loại bằng `include`/`exclude` thường dùng chung retry topology và backoff của listener. Việc có ba exception được retry không tự tạo ba nhóm retry topic riêng.

Nếu cần các nhóm lỗi có lịch retry khác nhau, có thể:

- Tách listener hoặc topic theo nhóm nghiệp vụ để mỗi nhóm có policy độc lập.
- Dùng nhiều `RetryTopicConfiguration` bean với phạm vi topic rõ ràng.
- Dùng custom backoff policy nếu cần quyết định delay dựa trên record/exception và API phiên bản hỗ trợ.
- Tách DLT theo exception bằng `exceptionBasedDltRouting` khi chỉ cần khác nơi lưu record cuối cùng.

Không nên tạo một danh sách exception lớn với nhiều lịch retry ngầm định khó hiểu. Hãy phân nhóm theo khả năng phục hồi: lỗi dependency tạm thời, lỗi rate limit, lỗi dữ liệu và lỗi contract.

## 12. Phân loại exception theo bản chất nghiệp vụ

Một policy thực tế có thể phân loại như sau:

| Nhóm lỗi | Ví dụ | Chính sách gợi ý |
|---|---|---|
| Dependency tạm thời | `InventoryUnavailableException`, `PricingServiceUnavailableException` | Retry với backoff tăng dần |
| Rate limit | `PartnerRateLimitException` | Retry với delay đủ dài theo quota hoặc `Retry-After` nếu được tích hợp |
| Dữ liệu không hợp lệ | `InvalidOrderException`, `UnsupportedCurrencyException` | Không retry; chuyển DLT để điều tra |
| Contract/schema không tương thích | `InvalidMessageContractException` | Thường đi DLT ngay |
| Lỗi lập trình không xác định | `NullPointerException`, lỗi invariant | Cần cân nhắc retry; thường không nên lặp vô hạn |

Không phân loại chỉ theo tên exception. Ví dụ `IllegalStateException` có thể biểu thị dependency chưa sẵn sàng trong một hệ thống nhưng lại là lỗi invariant trong hệ thống khác. Hãy tạo exception nghiệp vụ có ý nghĩa rõ và giữ nguyên cause.

## 13. Tương tác với blocking retry và DefaultErrorHandler

Non-blocking retry chuyển record qua retry topics; blocking retry giữ record ở consumer và retry theo error handler như `DefaultErrorHandler`. Có thể kết hợp hai cơ chế trong một số cấu hình, nhưng cần xác định rõ tầng nào xử lý exception trước và exception nào được chuyển tiếp.

Với yêu cầu thứ tự chặt chẽ trong một partition, blocking retry thường dễ giữ thứ tự hơn vì record lỗi tiếp tục chặn các record sau trong partition. Non-blocking retry cho phép main consumer đi tiếp, nên record sau có thể được xử lý trước record đang retry.

Không dùng cùng một exception classifier ở nhiều tầng mà không kiểm thử. Nếu `DefaultErrorHandler` retry trước rồi mới trả exception cho non-blocking retry, tổng số lần giao có thể khác với `attempts` mà người vận hành nhìn thấy ở retry-topic layer.

## 14. Giới hạn của non-blocking retry

Spring Kafka không hỗ trợ non-blocking retry với batch listener và cũng không thể kết hợp non-blocking retry với container transactions. Nếu listener cần batch hoặc transaction ở container, hãy chọn cơ chế error handling phù hợp khác, ví dụ `DefaultErrorHandler`/`DeadLetterPublishingRecoverer` cho batch hoặc `AfterRollbackProcessor` cho transaction.

Non-blocking retry cũng có thể thay đổi thứ tự xử lý do record lỗi được chuyển sang topic khác trong khi main topic tiếp tục tiêu thụ. Nếu thứ tự event là bất biến nghiệp vụ, cần đánh giá kỹ trước khi chọn retry topology này.

## 15. Kiểm thử exception classifier

Nên kiểm thử từng nhánh phân loại thay vì chỉ xác minh một exception được retry:

1. Exception nằm trong `include` được chuyển sang retry topic.
2. Exception ngoài `include` đi thẳng DLT.
3. Exception nằm trong `exclude` đi thẳng DLT.
4. Exception không nằm trong `exclude` vẫn được retry.
5. Exception lồng trong cause được nhận diện khi `traversingCauses=true`.
6. Cùng exception lồng trong cause không được match khi cause traversal tắt, nếu policy yêu cầu kiểm chứng khác biệt này.
7. Fatal exception toàn cục đi DLT mà không retry.
8. Exception được route tới đúng DLT suffix theo `exceptionBasedDltRouting`.
9. Retry hết `attempts` thì record đi DLT mặc định hoặc DLT tùy exception.
10. DLT handler lưu được payload và metadata phục vụ điều tra.

Có thể dùng `@EmbeddedKafka` hoặc Testcontainers Kafka. Gửi event với ID riêng cho từng test, chờ retry/DLT bằng Awaitility hoặc polling có timeout, và xác minh topic nhận record. Không dựa vào `Thread.sleep` cố định vì backoff, broker scheduling và consumer startup có thể làm thời điểm nhận khác nhau.

Ví dụ kiểm thử nên đếm số lần listener được gọi và xác minh record cuối cùng ở retry topic/DLT. Đồng thời kiểm tra metadata như original topic, partition, offset và exception headers để bảo đảm quy trình điều tra sau lỗi hoạt động.

## 16. Lỗi thường gặp

**Khai báo include nhưng exception vẫn đi DLT:** kiểm tra exception thực tế có đúng kiểu được khai báo không, có bị bọc trong cause không và `traversingCauses` đã bật chưa.

**Khai báo exclude nhưng exception vẫn retry:** kiểm tra cause chain, class được ném thực tế và cấu hình retry topic đang áp dụng cho listener/topic.

**Exception không nằm trong include nhưng vẫn mong retry:** allowlist chỉ retry các kiểu được chỉ định; dùng `exclude` nếu muốn retry phần lớn exception.

**Quên fatal exception toàn cục:** một số lỗi deserialize/conversion được chuyển DLT ngay dù listener có cấu hình retry chung.

**Bật cause traversal nhưng exception vẫn không match:** exception wrapper có thể không giữ cause hoặc class thực tế khác với class đã khai báo. Log đầy đủ exception chain.

**Dùng includeNames sai tên class:** dùng fully qualified class name chính xác; ưu tiên class literal nếu có thể.

**Nghĩ exceptionBasedDltRouting tự bật retry:** tính năng này chỉ chọn DLT đích, còn include/exclude và fatal classifier quyết định retry.

**Một topic có nhiều listener dùng policy khác nhau:** Spring Kafka chỉ áp dụng một retry configuration cho một topic; các listener cùng topic nên thống nhất cấu hình.

**Dùng non-blocking retry với batch hoặc container transaction:** hai trường hợp này không được hỗ trợ. Chọn error handling strategy phù hợp.

**Mất thứ tự nghiệp vụ:** main consumer tiếp tục xử lý record sau trong lúc record trước đang ở retry topic. Đánh giá partition key và yêu cầu ordering.

## 17. Checklist production

- Đã chọn allowlist `include` hay denylist `exclude` theo bản chất lỗi.
- Danh sách exception dùng class cụ thể và có tên phản ánh nghiệp vụ.
- Đã quyết định có cần `traversingCauses` và cấu hình tường minh.
- Đã kiểm tra danh sách fatal exceptions toàn cục.
- `attempts` được hiểu là tổng số lần, bao gồm lần xử lý ban đầu.
- Backoff phù hợp SLA, thời gian phục hồi dependency và quota bên ngoài.
- Nếu dùng nhiều DLT, mỗi suffix có consumer/quy trình xử lý tương ứng.
- `@DltHandler` hoặc DLT consumer lưu được payload và metadata điều tra.
- Retry topic configuration được giới hạn đúng topic và không xung đột giữa nhiều listener.
- Đã đánh giá ordering khi main topic tiếp tục xử lý record sau.
- Không dùng non-blocking retry với batch listener hoặc container transaction.
- Có test cho include, exclude, nested cause, fatal exception, hết attempts và DLT routing.
- Có metric/log cho retry attempts, DLT count, exception type và lỗi publish retry/DLT.

## Tài liệu tham khảo

- [Spring Kafka – Non-Blocking Retries](https://docs.spring.io/spring-kafka/reference/retrytopic.html)
- [Spring Kafka – Retry Features and Exception Classifier](https://docs.spring.io/spring-kafka/reference/retrytopic/features.html)
- [Spring Kafka – Retry Configuration](https://docs.spring.io/spring-kafka/reference/retrytopic/retry-config.html)
- [Spring Kafka – Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
