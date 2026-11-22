# Transformer có thể ném lỗi

## 1. Bối cảnh: chuyển đổi dữ liệu không phải lúc nào cũng thành công

Trong chương **Transformer** của module **SPRING_INTEGRATION_PATTERN**, chúng ta học cách triển khai các Enterprise Integration Patterns bằng **Spring Integration** để tạo luồng message ít phụ thuộc, dễ mở rộng và kiểm thử được. Transformer chuyển đổi nội dung của message để các bước tiếp theo xử lý theo một hợp đồng rõ ràng. Nó thường đứng trước Router, Filter, Splitter, Aggregator hoặc Gateway, vì những thành phần này cần payload có cấu trúc và kiểu dữ liệu ổn định.

Ví dụ một luồng tiếp nhận đơn hàng:

~~~mermaid
flowchart LR
    P["HTTP / Broker"] --> I["rawOrdersChannel"]
    I --> T["Order Transformer"]
    T -->|"Hợp lệ"| N["validatedOrdersChannel"]
    N --> R["Content-Based Router"]
    R --> A["Standard fulfillment"]
    R --> B["Manual review"]
    T -.->|"Thất bại"| E["Error handling / quarantine"]
~~~

Các input có thể chứa:

- Số tiền có định dạng không hợp lệ, chẳng hạn **abc** thay vì một số.
- Mã quốc gia bị thiếu, mã đơn hàng rỗng hoặc amount âm.
- JSON hỏng cú pháp, không tương thích schemaVersion hoặc có kiểu dữ liệu bất ngờ.
- Dữ liệu quá lớn khiến parser vượt giới hạn.
- Lỗi lập trình: NullPointerException, chuyển kiểu sai hoặc invariant không được kiểm tra.
- Lỗi I/O nếu một Transformer bị thiết kế để gọi dịch vụ ngoài.

Khi đó Transformer **có thể ném exception**. Phản ứng đúng phụ thuộc vào việc lỗi xuất hiện ở **thread đồng bộ hay bất đồng bộ**, có **retry** hay không, và message cần được **từ chối, cách ly hay xử lý lại**.

**Mục tiêu bài học**

1. Hiểu hợp đồng của Transformer: chuyển một input thành một output hợp lệ, không âm thầm trả null.
2. Nhận biết lỗi chuyển đổi, lỗi hợp đồng nghiệp vụ và lỗi hệ thống tạm thời.
3. Tổ chức exception trong Transformer thuần Java và để Spring Integration điều phối lỗi.
4. Phân biệt exception truyền trực tiếp qua **DirectChannel** và **ErrorMessage** trong đường bất đồng bộ.
5. Cấu hình error channel, quarantine, retry và idempotency phù hợp.
6. Viết unit test, integration test, kiểm tra lỗi, logging, correlation và tác động đến các nhánh downstream.

## 2. Transformer có hợp đồng gì?

Transformer nhận một Spring Message chứa **payload** và **headers**, rồi tạo payload hoặc Message mới. Một Transformer có thể đổi:

- **Kiểu dữ liệu**: JSON String → OrderCreated.
- **Định dạng**: XML → JSON, byte[] → object.
- **Nội dung**: giá trị đầu vào → DTO chuẩn hóa.
- **Headers**: loại bỏ hoặc bổ sung một số metadata phù hợp.

Mô hình:

~~~text
Message<RawOrder> --transform--> Message<ValidatedOrder>
~~~

Transformer nên chịu trách nhiệm **biến đổi hình dạng hoặc ngữ nghĩa của dữ liệu**, không đảm nhiệm mọi nhiệm vụ khác trong pipeline. Nếu chỉ muốn **giữ hoặc loại message** theo điều kiện, dùng **Message Filter**. Nếu muốn tác động nghiệp vụ và không có reply, cân nhắc **Service Activator**.

### 2.1. Transformer không được trả null

Theo tài liệu chính thức Spring Integration, **kể từ phiên bản 2.0, Transformer không được trả null**. Một phương thức chuyển đổi trả null sẽ gây **MessageTransformationException** vì Transformer luôn được kỳ vọng tạo ra một kết quả hợp lệ. Thuộc tính **requiresReply** của Transformer luôn là true và không được tắt để biến nó thành Filter.

**Phản ví dụ:**

~~~java
// Sai: null không có nghĩa "bỏ qua message" trong Transformer.
String transform(String input) {
    if (input.isBlank()) {
        return null;
    }
    return input.trim();
}
~~~

**Đúng nếu dữ liệu rỗng là lỗi:**

~~~java
String transform(String input) {
    if (input == null || input.isBlank()) {
        throw new IllegalArgumentException("EMPTY_INPUT");
    }
    return input.trim();
}
~~~

**Đúng nếu dữ liệu rỗng phải bị loại theo chính sách:**

~~~java
// Filter riêng quyết định message nào được phép đi tiếp.
@Bean
IntegrationFlow filterThenTransform() {
    return IntegrationFlow.from("textInputChannel")
            .filter(String.class, value -> !value.isBlank())
            .transform(String.class, String::trim)
            .channel("normalizedTextChannel")
            .get();
}
~~~

Ví dụ này cần khai báo hai channel và consumer phù hợp. Cần quyết định cách xử lý message bị Filter loại: được phép bỏ, gửi tới discard channel, hay báo lỗi. **Không đánh đồng discard với lỗi Transformer.**

### 2.2. Một lỗi của Transformer khác kết quả bị Filter loại

| Sự kiện | Thành phần chịu trách nhiệm | Hành vi nên có |
| --- | --- | --- |
| Input hợp lệ, chuyển đổi được | Transformer | Trả payload/Message đã chuẩn hóa |
| Input vi phạm hợp đồng và phải từ chối | Validation/Transformer | Ném lỗi có phân loại |
| Input được phép bỏ qua | Filter | Discard theo chính sách |
| Handler không có reply vì là tác vụ one-way | Service Activator | Có thể trả null nếu requiresReply=false |
| Transformer trả null | Transformer | Framework báo lỗi chuyển đổi |
| Output được tạo nhưng downstream lỗi | Router/handler phía sau | Xử lý lỗi downstream, không ghi nhầm là parse failure |

### 2.3. Transformation error và lỗi downstream có thể trông giống nhau

Nếu cùng một lời gọi send() tạo lỗi, nguyên nhân chưa chắc nằm ở Transformer. Ví dụ:

1. Transformer chuyển RawOrder thành ValidatedOrder thành công.
2. Router chọn manualReviewChannel.
3. Handler của manualReviewChannel ném exception.

Exception có thể đi ngược lên caller trong cùng thread. Nếu logging chỉ ghi **send failed**, người vận hành không biết lỗi thuộc bước **transform** hay **review**. Vì vậy cần đặt component ID, loại lỗi, eventId, schemaVersion và trace context rõ ràng.

## 3. Phân loại lỗi trước khi chọn retry

| Loại lỗi | Ví dụ | Retry cùng input có giúp? | Cách xử lý khởi điểm |
| --- | --- | --- | --- |
| **Malformed input** | JSON hỏng, amount là chữ | Thường không | Từ chối hoặc quarantine |
| **Validation failure** | Mã đơn hàng thiếu, tiền âm | Thường không | Trả lỗi có mã, ghi nhận an toàn |
| **Unsupported schema** | schemaVersion chưa được hỗ trợ | Không, trước khi nâng phiên bản | Quarantine, chuyển owner xử lý |
| **Conversion bug** | NPE hoặc ClassCastException do code | Thường không | Fail fast, cảnh báo và sửa code |
| **Resource limit** | Payload vượt kích thước cho phép | Không nếu dữ liệu giữ nguyên | Từ chối theo giới hạn |
| **Transient infrastructure** | Schema lookup service timeout | Có thể, nếu truy vấn idempotent | Retry có giới hạn/backoff |
| **Downstream failure** | DB insert fail sau Transformer | Không phải lỗi Transformer | Retry/error flow tại đúng nhánh |

**Nguyên tắc:** cùng một input bị lỗi parse cố định sẽ không trở nên hợp lệ chỉ vì retry thêm 100 lần. Trái lại, lỗi mạng tạm thời có thể phục hồi, nhưng nên tách I/O khỏi Transformer nếu có thể.

### 3.1. Error contract rõ ràng

Mỗi lỗi cần trả lời:

- **Mã lỗi ổn định** là gì? Ví dụ INVALID_AMOUNT, INVALID_COUNTRY, UNSUPPORTED_VERSION.
- Có phải lỗi **không thể retry** với cùng input?
- Input có cần **giữ lại để phát lại** sau khi sửa dữ liệu hoặc nâng version?
- Caller nào nhận được lỗi và bằng cách nào?
- EventId/correlation nào dùng để điều tra?
- Payload có thông tin nhạy cảm cần loại khỏi exception/log không?

Không xây dựng code chỉ bằng cách bắt **Exception** rồi tự trả một payload mặc định như đơn hàng có giá trị 0. Cách làm đó biến input sai thành **nghiệp vụ có vẻ hợp lệ**, đẩy lỗi sang các nhánh sau và khó truy vết.

## 4. Một Transformer Java thuần, dễ kiểm thử

Giả sử bên ngoài gửi payload dạng:

~~~json
{
  "orderId": "ORD-103",
  "amountVnd": "15000000",
  "destinationCountry": "SG"
}
~~~

Ta muốn chuyển sang kiểu mạnh hơn với số tiền **BigDecimal**, mã quốc gia đã chuẩn hóa và dữ liệu hợp lệ.

### 4.1. DTO đầu vào và đầu ra

~~~java
import java.math.BigDecimal;

record RawOrder(
        String orderId,
        String amountVnd,
        String destinationCountry) {}

record ValidatedOrder(
        String orderId,
        BigDecimal amountVnd,
        String destinationCountry) {}
~~~

**RawOrder** phản ánh dữ liệu chưa kiểm tra. **ValidatedOrder** phản ánh điều kiện tối thiểu mà downstream có thể tin dựa vào **hợp đồng nội bộ**, không phải chứng cứ người gửi có quyền truy cập đơn hàng.

### 4.2. Exception nghiệp vụ có mã phân loại

~~~java
final class InvalidOrderException extends RuntimeException {
    private final String errorCode;

    InvalidOrderException(String errorCode) {
        super(errorCode);
        this.errorCode = errorCode;
    }

    String errorCode() {
        return errorCode;
    }
}
~~~

Exception chỉ giữ **mã lỗi**, không giữ toàn bộ số thẻ, email hay payload. Thông tin kỹ thuật chi tiết nếu cần được ghi theo chính sách logging ở chỗ kiểm soát truy cập; tránh đưa dữ liệu nhạy cảm vào message của exception rồi truyền qua error channel.

### 4.3. Transformer thuần Java

~~~java
import java.math.BigDecimal;
import java.util.Locale;

final class OrderNormalizationTransformer {

    ValidatedOrder transform(RawOrder raw) {
        if (raw == null) {
            throw new InvalidOrderException("MISSING_ORDER");
        }
        String id = raw.orderId();
        if (id == null || !id.matches("ORD-[A-Za-z0-9-]{1,32}")) {
            throw new InvalidOrderException("INVALID_ORDER_ID");
        }

        String rawAmount = raw.amountVnd();
        if (rawAmount == null || rawAmount.isBlank()) {
            throw new InvalidOrderException("MISSING_AMOUNT");
        }

        BigDecimal amount;
        try {
            amount = new BigDecimal(rawAmount.trim());
        } catch (NumberFormatException ex) {
            throw new InvalidOrderException("INVALID_AMOUNT_FORMAT");
        }

        // Đơn vị VND ở ví dụ này chỉ dùng số tiền nguyên dương.
        if (amount.signum() <= 0
                || amount.stripTrailingZeros().scale() > 0) {
            throw new InvalidOrderException("INVALID_AMOUNT_VALUE");
        }

        String country = raw.destinationCountry();
        if (country == null || !country.trim()
                .matches("[A-Za-z]{2}")) {
            throw new InvalidOrderException("INVALID_COUNTRY");
        }

        return new ValidatedOrder(
                id,
                amount,
                country.trim().toUpperCase(Locale.ROOT));
    }
}
~~~

**Đặc điểm tốt của Transformer:**

1. **Không có side effect:** không ghi DB, không gửi HTTP, không phát sự kiện.
2. **Deterministic:** cùng input hợp lệ cho cùng output (trong cùng hợp đồng).
3. **Fail fast:** input sai ném lỗi trước khi downstream thực hiện giao dịch.
4. **Type-safe:** downstream nhận ValidatedOrder thay vì tự parse lại amountVnd.
5. **Dễ unit test:** không cần khởi động Spring để kiểm tra logic.

Trong thực tế, cần thêm giới hạn kích thước payload, ràng buộc số tiền tối đa, tập mã quốc gia được chấp nhận, schemaVersion và chính sách quốc tế hóa phù hợp. Regex hai ký tự chỉ kiểm tra **hình thức**, chưa chứng minh đó là mã quốc gia hợp lệ theo business.

### 4.4. Không gắn thêm I/O vào cùng phương thức nếu không cần

~~~java
// Cách này làm Transformer khó dự đoán và khó retry:
ValidatedOrder transform(RawOrder raw) {
    ValidatedOrder parsed = parser.transform(raw);
    riskClient.enrichFromRemoteService(parsed.orderId());
    return parsed;
}
~~~

Ví dụ là **phản ví dụ kiến trúc**; parser và riskClient là dependency giả định. Nếu có thể, tách:

~~~text
RawOrder
  -> Normalize Transformer
  -> Risk Enricher (timeout/retry/circuit breaker riêng)
  -> Content-Based Router
~~~

Nhờ vậy lỗi **input bất hợp lệ** không bị retry như lỗi mạng, và lỗi dịch vụ risk không bị báo nhầm là lỗi parse.

## 5. Gắn Transformer vào một IntegrationFlow đồng bộ

Spring Integration Java DSL hỗ trợ phương thức **transform** để chuyển dữ liệu qua một handler. Cấu hình sau khai báo ba DirectChannel: input, output đã chuẩn hóa và một đầu ra sau khi hoàn tất xử lý. Mục tiêu là minh họa nơi exception xuất hiện.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class OrderTransformationConfig {

    @Bean
    OrderNormalizationTransformer orderTransformer() {
        return new OrderNormalizationTransformer();
    }

    @Bean
    MessageChannel rawOrdersChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel validatedOrdersChannel() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow orderNormalizationFlow(
            OrderNormalizationTransformer transformer) {
        return IntegrationFlow.from("rawOrdersChannel")
                .transform(RawOrder.class, transformer::transform)
                .channel("validatedOrdersChannel")
                .get();
    }
}
~~~

**Đọc flow:**

1. Một message chứa **RawOrder** đến rawOrdersChannel.
2. Transformer gọi **OrderNormalizationTransformer.transform**.
3. Nếu trả về ValidatedOrder, framework phát message kết quả tới **validatedOrdersChannel**.
4. Nếu phương thức ném InvalidOrderException, bước chuyển đổi thất bại; message **không tiếp tục theo nhánh thành công**.
5. validatedOrdersChannel cần có subscriber hoặc IntegrationFlow downstream phù hợp. Nếu không có consumer, send có thể thất bại ở giai đoạn dispatch **sau khi transform đã thành công**.

Ví dụ consumer dùng port nghiệp vụ:

~~~java
interface ValidatedOrderPort {
    void accept(ValidatedOrder order);
}

// Đặt trong lớp @Configuration ở trên:
@Bean
IntegrationFlow acceptedOrderFlow(ValidatedOrderPort port) {
    return IntegrationFlow.from("validatedOrdersChannel")
            .handle(ValidatedOrder.class, (order, headers) -> {
                port.accept(order);
                return null; // Service Activator one-way kết thúc tại đây.
            })
            .get();
}
~~~

Không nhầm **handler cuối trả null** với **Transformer trả null**: trong Service Activator one-way, return null có thể là kết thúc hợp lệ khi không yêu cầu reply; Transformer thì luôn phải tạo kết quả.

### 5.1. Producer và đường lỗi đồng bộ

~~~java
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

RawOrder raw = new RawOrder(
        "ORD-103", "abc", "SG");

// rawOrdersChannel là bean MessageChannel đã được inject.
rawOrdersChannel.send(
        MessageBuilder.withPayload(raw).build());
~~~

Trong cấu hình trên, **rawOrdersChannel là DirectChannel**, nên Transformer chạy trên **thread gọi send()**. Vì amountVnd là abc, phương thức chuyển đổi ném lỗi. Lỗi có thể được framework bọc thành **MessageTransformationException/MessagingException**, trong đó nguyên nhân gốc là InvalidOrderException.

**Không nên viết test phụ thuộc tuyệt đối vào một lớp wrapper** nếu không kiểm soát được version framework và kiểu endpoint; hãy kiểm tra **root cause**, component được báo lỗi và việc output không nhận message.

### 5.2. Một exception không đồng nghĩa tự gửi ErrorMessage

Đây là khác biệt quan trọng:

- Với **DirectChannel đồng bộ**, lỗi thông thường truyền qua call stack về sender. Nó **không mặc nhiên được publish** vào global errorChannel.
- Với một **TaskExecutor/poller** do Spring Integration quản lý, lỗi có thể được **bọc trong ErrorMessage** rồi gửi đến errorChannel theo cấu hình.

Nếu muốn đưa lỗi đồng bộ vào một message-based error flow thay vì để caller nhận exception, cần chủ động đặt ranh giới gateway/error handling hoặc recovery advice tương ứng. Chỉ thêm một bean tên errorChannel **không thay đổi** hành vi đồng bộ của DirectChannel.

## 6. Error handling: DirectChannel và ExecutorChannel khác nhau

### 6.1. So sánh đường đi

~~~mermaid
flowchart TD
    A["Caller / Producer"] --> D{"MessageChannel"}
    D -->|"DirectChannel"| T["Transformer cùng thread"]
    D -->|"ExecutorChannel"| X["TaskExecutor nhận việc"]
    X --> TA["Transformer trong worker"]
    T -->|"Exception"| C["Lỗi về caller"]
    TA -->|"Exception"| EM["ErrorMessage"]
    EM --> EC["errorChannel header hoặc global errorChannel"]
~~~

| Cơ chế | Ai chạy Transformer? | Caller có bắt được lỗi trực tiếp? | ErrorMessage hoạt động ra sao? |
| --- | --- | --- | --- |
| **DirectChannel** | Thread gửi message | Thường có | Không mặc định publish error |
| **ExecutorChannel** | Thread của TaskExecutor | Thông thường không, sau khi được dispatch | MessagePublishingErrorHandler có thể phát ErrorMessage |
| **QueueChannel + poller** | Thread poller | Không phải caller gửi message trước đó | Poller/error handler có thể phát ErrorMessage |
| **Inbound Gateway sync** | Tùy flow và gateway | Có thể trả lỗi cho caller | Gateway có thể được cấu hình error channel |
| **Broker adapter** | Tùy consumer container/adapter | Caller ban đầu thường không còn cùng call stack | Ack/requeue/error handling theo adapter |

**Không phải mọi Executor đều tự tạo ErrorMessage**. Cơ chế publish lỗi phụ thuộc Spring Integration task, executor, poller, error handler và phiên bản. Đối với tác vụ chạy bằng thread do ứng dụng tự tạo, không tự suy ra chúng sử dụng global errorChannel của Spring Integration.

### 6.2. ErrorMessage chứa những gì?

Trong mô hình lỗi message-oriented của Spring Integration, **ErrorMessage** là một Spring Message có payload kiểu **Throwable**. Payload có thể là MessagingException chứa thông tin failedMessage; một ErrorMessage cũng có thể có **originalMessage**, tùy loại lỗi và strategy tạo error.

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.ErrorMessage;

void inspectError(Message<?> incoming) {
    if (!(incoming instanceof ErrorMessage errorMessage)) {
        throw new IllegalArgumentException("Expected ErrorMessage");
    }

    Throwable failure = errorMessage.getPayload();
    Message<?> original = errorMessage.getOriginalMessage();

    // Sử dụng failure để phân loại lỗi.
    // original có thể null, không tự giả định luôn có payload gốc.
}
~~~

**Không log toàn bộ Throwable và originalMessage một cách vô điều kiện** khi payload chứa dữ liệu nhạy cảm. Exception message, stack trace và headers có thể lộ token, địa chỉ, PII hoặc dữ liệu giao dịch. Log một **errorCode**, **componentId**, **eventId** đã tin cậy và trace ID phù hợp; chỉ ghi chi tiết có kiểm soát.

### 6.3. Global errorChannel và header errorChannel

Khi thành phần xử lý lỗi bất đồng bộ cần gửi ErrorMessage, Spring Integration thường giải quyết destination theo thứ tự:

1. **errorChannel header** của request message nếu có và hợp lệ.
2. **Global errorChannel** do Spring Integration tạo hoặc do ứng dụng cung cấp.

Global errorChannel mặc định là **PublishSubscribeChannel**, thường có LoggingHandler để ghi lỗi. Điều này không có nghĩa mọi message lỗi được lưu bền, tự retry hoặc tự chuyển DLQ.

~~~text
Input Message
  headers:
    businessCorrelationId: ORD-103
    errorChannel: orderTransformationErrors
~~~

**Bảo mật:** không lấy errorChannel trực tiếp từ HTTP header do client tự cung cấp rồi tin như tên channel nội bộ. Giá trị điều khiển này cần được tạo hoặc xác minh tại trust boundary, vì nó ảnh hưởng đến nơi thông tin lỗi được gửi.

## 7. Tạo ranh giới bất đồng bộ và kênh lỗi riêng

Mục tiêu: gửi RawOrder vào một **ExecutorChannel**, để Transformer chạy trong thread worker. Khi transform thất bại, lỗi được gửi đến channel đã được cấu hình qua header; không coi send() trả true là đã chuyển đổi thành công.

### 7.1. Cấu hình executor có giới hạn

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class AsyncOrderTransformationConfig {

    @Bean
    ThreadPoolTaskExecutor normalizationExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("normalize-");
        return executor;
    }

    @Bean
    MessageChannel asyncOrderInputChannel(
            @Qualifier("normalizationExecutor")
            ThreadPoolTaskExecutor executor) {
        return new ExecutorChannel(executor);
    }

    @Bean
    MessageChannel normalizedOrderOutputChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel orderTransformationErrors() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow asyncOrderTransformFlow(
            OrderNormalizationTransformer transformer) {
        return IntegrationFlow.from("asyncOrderInputChannel")
                .transform(RawOrder.class, transformer::transform)
                .channel("normalizedOrderOutputChannel")
                .get();
    }
}
~~~

Ví dụ này cần @EnableIntegration trong application context (hoặc cấu hình Spring Boot Spring Integration tương đương), bean **OrderNormalizationTransformer** và consumer của cả output/error channel. ThreadPoolTaskExecutor được Spring quản lý lifecycle khi khai báo bằng @Bean.

ExecutorChannel tạo một **ranh giới async**; khi số task vượt capacity, dispatch có thể bị từ chối. Đây là lỗi admission/backpressure cần xử lý khác với InvalidOrderException bên trong Transformer. Không tăng queue đến vô hạn chỉ để che tắc nghẽn.

### 7.2. Producer chọn error channel đáng tin

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

RawOrder raw = new RawOrder(
        "ORD-109", "not-a-number", "VN");

Message<RawOrder> message = MessageBuilder.withPayload(raw)
        .setHeader("eventId", "evt-109")
        .setHeader("businessCorrelationId", raw.orderId())
        .setHeader(
                MessageHeaders.ERROR_CHANNEL,
                "orderTransformationErrors")
        .build();

// Bean asyncOrderInputChannel được inject.
boolean submitted = asyncOrderInputChannel.send(message);
~~~

**submitted=true** nghĩa là thao tác gửi được chấp nhận theo semantics của ExecutorChannel, **không** nghĩa là Transformer đã thành công. ErrorMessage của failure có thể đến **sau** khi send() trả về.

Tại ingress, eventId và errorChannel phải được gắn bởi code nội bộ đáng tin, không sao chép nguyên dữ liệu chưa xác thực từ client. Với broker, phải kiểm tra việc chuyển tiếp errorChannel qua adapter; có thể cần cấu hình error channel của inbound endpoint thay vì phụ thuộc header đi qua wire.

### 7.3. Consumer lỗi và phân loại nguyên nhân

Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;

interface InvalidOrderPort {
    void recordFailure(
            String errorCode,
            String eventId,
            String component);
}

@Bean
IntegrationFlow transformErrorFlow(InvalidOrderPort errors) {
    return IntegrationFlow.from("orderTransformationErrors")
            .handle(message -> {
                if (!(message instanceof ErrorMessage error)) {
                    throw new IllegalArgumentException(
                            "Expected ErrorMessage");
                }

                Throwable failure = error.getPayload();
                Throwable current = failure;
                while (current.getCause() != null
                        && current.getCause() != current) {
                    current = current.getCause();
                }

                String code = current instanceof InvalidOrderException invalid
                        ? invalid.errorCode()
                        : "UNEXPECTED_TRANSFORMATION_FAILURE";

                String eventId = "UNKNOWN";
                if (failure instanceof MessagingException messaging
                        && messaging.getFailedMessage() != null) {
                    Object candidate = messaging.getFailedMessage()
                            .getHeaders().get("eventId");
                    if (candidate instanceof String valid) {
                        eventId = valid;
                    }
                }

                errors.recordFailure(
                        code, eventId, "orderNormalizationTransformer");
            })
            .get();
}
~~~

Đây là mảnh cấu hình đặt cùng @Configuration có channel tương ứng. **InvalidOrderPort** do ứng dụng triển khai để quarantine/log với quyền và retention phù hợp. Trong bản triển khai thật, có thể tìm originalMessage nếu failedMessage không có; phải xử lý trường hợp không có cả hai.

**Đừng chỉ nhìn root cause rồi retry tất cả.** Một lỗi parse không thể tự khỏi. Ngược lại, lỗi I/O từ một bước enrichment có thể cần retry đúng bước với giới hạn.

Nếu error handler tự ném exception, việc xử lý ErrorMessage cũng có thể thất bại. Cần cơ chế giám sát lỗi trên đường lỗi, khả năng lưu bền nếu yêu cầu và tránh routing vòng lặp errorChannel → chính flow lỗi.

## 8. Retry Transformer: khi nào có ích, khi nào nguy hiểm?

Một Transformer **thuần Java** thực hiện parse, validate và chuẩn hóa nên gần như luôn deterministic. Với input không đổi, một lỗi INVALID_AMOUNT_FORMAT sẽ lặp lại như cũ. Đặt retry ba lần cho lỗi này chỉ tăng tải và làm chậm việc nhận ra message không hợp lệ.

Trong một số trường hợp, một Transformer thực tế còn chứa bước tương tác với hệ thống khác: đọc schema từ registry, chuyển đổi bằng một service bên ngoài hoặc lấy thông tin bổ sung. Lúc đó phải phân biệt:

- **Lỗi cố định**: dữ liệu không hợp lệ, schema không hỗ trợ, bug.
- **Lỗi tạm thời**: timeout, kết nối mất, hệ thống registry tạm gián đoạn.
- **Kết quả chưa rõ**: request ra ngoài có thể đã thực hiện side effect, nhưng response bị mất.

### 8.1. Ma trận chính sách

| Lỗi | Retry cùng input? | Nơi xử lý phù hợp |
| --- | --- | --- |
| INVALID_ORDER_ID | Không | Trả lỗi/quarantine |
| INVALID_AMOUNT_FORMAT | Không | Trả lỗi/quarantine |
| UNSUPPORTED_SCHEMA_VERSION | Không trước khi cập nhật consumer | Quarantine để replay sau nâng cấp |
| NullPointerException do code | Không tự động lặp vô hạn | Fail fast, alert, sửa bug |
| Schema Registry timeout | Có thể, có giới hạn | Enrichment/lookup riêng |
| Database connection timeout | Có thể | Endpoint thao tác DB, transaction/retry riêng |
| HTTP provider timeout sau request có side effect | Chỉ khi idempotent hoặc reconcile | Gateway/service adapter có khóa ổn định |

**Tách lỗi theo nguyên nhân** giúp retry không trở thành nguồn gây queue backlog hoặc duplicate side effect.

### 8.2. RequestHandlerRetryAdvice

Spring Integration cung cấp **RequestHandlerRetryAdvice** để retry một handler/endpoint. Khi gắn advice vào **đúng Transformer hoặc bước enrichment có thể phục hồi**, nó có thể thử lại một số lỗi theo policy. Có thể cấu hình RecoveryCallback, ví dụ dùng **ErrorMessageSendingRecoverer** để chuyển lỗi cuối cùng thành ErrorMessage sau khi hết retry.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.integration.handler.advice.ErrorMessageSendingRecoverer;
import org.springframework.messaging.MessageChannel;

// Chỉ dùng cho những lỗi có khả năng phục hồi và adapter phù hợp.
@Bean
RequestHandlerRetryAdvice transientLookupRetry(
        MessageChannel transientLookupRecoveryChannel) {
    RequestHandlerRetryAdvice advice =
            new RequestHandlerRetryAdvice();
    advice.setRecoveryCallback(
            new ErrorMessageSendingRecoverer(
                    transientLookupRecoveryChannel));
    return advice;
}
~~~

Đây là cấu hình thành phần **advice**, chưa phải flow hoàn chỉnh. Muốn nó có tác dụng, phải gắn advice vào endpoint liên quan bằng DSL endpointConfigurer hoặc adviceChain tương ứng. Cần chọn số lần thử/backoff và recovery policy theo **version Spring Integration/Spring Retry** đang dùng. Không gắn advice vào toàn bộ luồng nếu việc retry lại Router/Aggregator/Gateway có thể lặp những nhánh đã thực hiện side effect.

**Điểm cần lưu ý:** hành vi mặc định về số lần retry/backoff thay đổi theo API và version; không dựa vào default khi nghiệp vụ có hạn mức nghiêm ngặt. Phải cấu hình tường minh, test số lần gọi và đo thời gian chờ.

### 8.3. Retry stateless và redelivery stateful

| Phương thức | Ai thực hiện lần thử tiếp? | Hệ quả |
| --- | --- | --- |
| **Stateless retry trong advice** | Endpoint thử lại ngay/trong cùng tiến trình | Giữ thread/đợi backoff; có thể làm tăng latency |
| **Stateful retry/redelivery** | Nguồn như JMS/Kafka/broker đưa message tới lại | Cần key ổn định, ack/requeue và store trạng thái phù hợp |
| **Manual replay từ quarantine** | Người vận hành/job phát lại sau khi sửa lỗi | Cần schemaVersion, eventId, idempotency và audit trail |

Không tự cấu hình retry bất tận. Thêm backoff, jitter khi phù hợp, giới hạn attempts, theo dõi số message lỗi và đưa sang DLQ/quarantine khi không thể tự phục hồi.

## 9. Idempotency: Transformer thuần khác Transformer có side effect

### 9.1. Với Transformer thuần

Một phép chuẩn hóa như RawOrder → ValidatedOrder có thể được tính lại mà không thay đổi trạng thái bên ngoài. Nếu message lặp vì broker redelivery, việc **chạy lại phép chuẩn hóa** thường không gây duplicate effect.

Tuy nhiên, cần nhớ:

- Transformer có thể tạo **Message mới**, MessageHeaders.ID có thể khác.
- Những bước **sau Transformer** có thể ghi database, gửi email hoặc charge payment.
- Một payload chuẩn hóa giống nhau không bảo đảm downstream đã xử lý đúng một lần.

Vì vậy eventId nghiệp vụ phải ổn định qua các lần gửi lại, thay vì tạo một eventId mới trong Transformer.

### 9.2. Với Transformer có side effect

**Không khuyến khích** dùng Transformer như nơi cập nhật database hoặc gửi external API, vì việc chạy lại sẽ có nguy cơ lặp. Nếu không thể tránh, mỗi effect phải có **idempotency key, transaction hoặc cơ chế đối soát** như một endpoint nghiệp vụ đúng nghĩa.

Ví dụ nguy hiểm:

~~~java
ValidatedOrder transform(RawOrder raw) {
    ValidatedOrder order = parser.transform(raw);
    stockClient.reserve(order.orderId()); // Side effect.
    return order;
}
~~~

Nếu stockClient.reserve thành công rồi handler bị lỗi lúc gửi reply, retry có thể giữ hàng lần nữa. Một thiết kế rõ hơn:

~~~text
RawOrder
  -> OrderNormalizationTransformer (pure)
  -> InventoryReservation Service Activator
     (idempotencyKey = eventId + ":reserve-inventory")
  -> Fulfillment Router
~~~

**Không dùng MessageHeaders.ID làm business idempotency key mặc định.** Nếu Transformer tạo message mới hoặc adapter serializes/recreates message, ID kỹ thuật có thể khác giữa các lần retry.

### 9.3. ErrorMessage không phải DLQ bền

Khi một Transformer lỗi, ErrorMessage gửi tới errorChannel **chưa đồng nghĩa** dữ liệu đã được lưu để phục hồi qua restart. Nếu hợp đồng yêu cầu replay:

1. Ghi **eventId**, loại lỗi, schemaVersion và payload cần thiết vào storage/broker bền.
2. Bảo vệ dữ liệu nhạy cảm và thời hạn lưu.
3. Đánh dấu trạng thái **pending-review**, **replayable**, **rejected** hoặc **completed**.
4. Chỉ replay sau khi sửa dữ liệu, bổ sung converter hoặc phục hồi hạ tầng.
5. Đảm bảo các nhánh có side effect downstream xử lý lặp an toàn.

Một channel tên **deadLetterChannel** không tự tạo dead-letter semantics. Phải cấu hình consumer, store, retry/ack và vận hành thực.

## 10. Message headers và correlation khi Transformer ném lỗi

Spring Integration có thể bảo toàn/lan truyền headers trong quá trình transform tùy cách trả payload/Message và loại endpoint. Vì vậy cần kiểm tra rõ **trường nào từ input đi tới output**.

| Header | Ý nghĩa | Yêu cầu khi transform |
| --- | --- | --- |
| **eventId** | Định danh logical event ổn định | Giữ hoặc sinh ở trust boundary trước transform |
| **businessCorrelationId** | Liên kết cùng order/payment | Không thay tùy ý khi gặp lỗi |
| **traceId / tracing context** | Quan sát theo luồng | Giữ ngữ cảnh phù hợp adapter |
| **replyChannel** | Đường trả lời Gateway | Không vô tình xóa giữa request/reply |
| **errorChannel** | Đường xử lý ErrorMessage | Chỉ giữ giá trị đến từ nguồn đáng tin |
| **sequenceNumber / sequenceSize** | Nhóm từ Splitter/Aggregator | Không tự sửa khi cần ghép nhóm |
| **schemaVersion** | Phiên bản hợp đồng payload | Kiểm tra hỗ trợ trước chuyển đổi |

### 10.1. Header do client gửi có thể giả mạo

Nếu nhận message từ HTTP hoặc broker chưa tin cậy, không sao chép nguyên **replyChannel**, **errorChannel**, **routingSlip**, **tenantId**, **role** hoặc **trustedRoute** vào message nội bộ. Đây là những giá trị có thể ảnh hưởng việc gửi message và quyền nghiệp vụ.

Hãy xây dựng message nội bộ từ payload đã xác thực và **allowlist metadata**; gắn tenant từ verified principal. Nếu Transform tạo message mới, cần kiểm thử header propagation để bảo đảm những giá trị ngoài ý muốn không tiếp tục theo downstream.

### 10.2. Không đưa payload raw vào exception

Với JSON bị lỗi, một cách làm nguy hiểm là ném exception chứa cả input:

~~~java
// Tránh: nguyên input có thể chứa dữ liệu cá nhân hoặc bí mật.
throw new IllegalArgumentException("Invalid JSON: " + rawBody);
~~~

Thay bằng error code, bounded reason và vị trí sai đã loại dữ liệu nhạy cảm. Nếu cần lưu payload vào quarantine, mã hóa, kiểm soát quyền và retention theo chính sách dữ liệu. Một error channel có nhiều subscriber có thể khiến raw payload bị phát tới những nơi không có quyền nhận.

## 11. Transformer, Filter, Router và Gateway phối hợp xử lý lỗi

Không nên để một Transformer thực hiện toàn bộ quyết định nghiệp vụ. Một pipeline rõ trách nhiệm:

~~~mermaid
flowchart LR
    I["Ingress"] --> V["Schema validation"]
    V --> T["Pure Transformer"]
    T --> F{"Message Filter"}
    F -->|"Hợp lệ để xử lý"| R{"Content-Based Router"}
    R --> S["Standard handler"]
    R --> M["Manual review"]
    T -.->|"Exception"| E["Error handling"]
    F -->|"Discard theo policy"| D["Discard handler"]
    S -.->|"Downstream error"| X["Service error handler"]
~~~

**Phân biệt trách nhiệm:**

- **Transformer**: dữ liệu đầu vào chuyển sang định dạng có hợp đồng; lỗi khi không thể chuyển đổi.
- **Filter**: thông điệp có được tiếp tục hay không; discard là kết quả của policy, không phải tự động lỗi.
- **Router**: chọn channel từ dữ liệu hợp lệ; key không map có thể được đưa fallback.
- **Gateway**: đưa request vào flow và có thể chờ reply; cần timeout và error contract rõ.
- **Retry**: áp dụng ở đúng endpoint có lỗi có thể phục hồi.
- **Error channel**: vận chuyển thông tin lỗi trong những ngữ cảnh được cấu hình; không tự sửa dữ liệu hoặc đảm bảo retry.
- **Correlation**: giúp theo dõi một logical event; không đảm bảo exactly-once side effect.

### 11.1. Giao tiếp request/reply khi parse lỗi

Nếu API cần trả HTTP 400 cho input không hợp lệ, có thể validation ở controller trước khi phát message hoặc đặt gateway/error flow chuyển InvalidOrderException thành response nghiệp vụ. **Không dùng exception của Transformer như dữ liệu phản hồi thành công** nếu hợp đồng không công bố rõ.

Nếu pipeline chạy bất đồng bộ và endpoint HTTP đã trả 202 Accepted, nó thường không thể tự sửa phản hồi thành 400 sau khi worker bắt đầu chạy. Cần một hợp đồng **accepted for processing** và kênh thông báo trạng thái/lỗi về sau.

### 11.2. Kết hợp Splitter/Aggregator

Một Transformer nằm giữa Splitter và Aggregator có thể nhận message con có **correlationId**, **sequenceNumber** và **sequenceSize**. Nếu một message con transform lỗi, Aggregator có thể **không nhận đủ nhóm**, dẫn đến timeout hoặc giữ message chờ.

Giải pháp tùy nghiệp vụ:

- Ném lỗi và đánh dấu cả group thất bại.
- Gửi một **failure result có cấu trúc** vào một nhánh tổng hợp, nếu Aggregator thực sự được thiết kế cho partial results.
- Retry đúng message con khi có lỗi tạm thời.
- Cấu hình release strategy, group timeout, message store và xử lý nhóm không hoàn chỉnh.

**Không sửa sequenceSize một cách tùy ý để Aggregator “đủ”**, vì có thể che mất dữ liệu chưa được xử lý. ErrorMessage và kết quả nghiệp vụ thất bại là hai loại message khác nhau; nếu dùng chung một aggregator, phải có hợp đồng rõ.

## 12. Unit test Transformer thuần Java

Trước khi chạy Spring context, kiểm thử hàm transform như một hàm bình thường. Dùng **JUnit 5** kiểm tra cả happy path và từng lỗi có mã.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class OrderNormalizationTransformerTest {
    private final OrderNormalizationTransformer transformer =
            new OrderNormalizationTransformer();

    @Test
    void normalizesValidOrder() {
        ValidatedOrder result = transformer.transform(
                new RawOrder("ORD-103", "15000000", "sg"));

        assertEquals("ORD-103", result.orderId());
        assertEquals(new BigDecimal("15000000"), result.amountVnd());
        assertEquals("SG", result.destinationCountry());
    }

    @Test
    void rejectsMalformedAmountWithStableErrorCode() {
        InvalidOrderException error = assertThrows(
                InvalidOrderException.class,
                () -> transformer.transform(
                        new RawOrder("ORD-103", "abc", "SG")));

        assertEquals("INVALID_AMOUNT_FORMAT", error.errorCode());
    }

    @Test
    void rejectsNegativeAndFractionalVnd() {
        InvalidOrderException negative = assertThrows(
                InvalidOrderException.class,
                () -> transformer.transform(
                        new RawOrder("ORD-104", "-10", "VN")));
        assertEquals("INVALID_AMOUNT_VALUE", negative.errorCode());

        InvalidOrderException fractional = assertThrows(
                InvalidOrderException.class,
                () -> transformer.transform(
                        new RawOrder("ORD-105", "12.5", "VN")));
        assertEquals("INVALID_AMOUNT_VALUE", fractional.errorCode());
    }

    @Test
    void rejectsInvalidCountryWithoutLeakingRawPayload() {
        InvalidOrderException error = assertThrows(
                InvalidOrderException.class,
                () -> transformer.transform(
                        new RawOrder("ORD-106", "12000", "UNKNOWN")));
        assertEquals("INVALID_COUNTRY", error.errorCode());
    }

    @Test
    void rejectsMissingOrder() {
        InvalidOrderException error = assertThrows(
                InvalidOrderException.class,
                () -> transformer.transform(null));
        assertEquals("MISSING_ORDER", error.errorCode());
    }
}
~~~

Unit test không chứng minh Spring Integration đã nối channel và gửi ErrorMessage đúng. Vì vậy cần integration test.

## 13. Integration test với DirectChannel: lỗi tới caller

Dùng QueueChannel làm **đầu ra chỉ phục vụ kiểm thử** để lấy message ngay bằng receive(0). Không cần tạo subscriber giả hoặc dùng Thread.sleep.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(SynchronousTransformerTest.Config.class)
class SynchronousTransformerTest {

    @Configuration
    @EnableIntegration
    static class Config {
        @Bean
        OrderNormalizationTransformer transformer() {
            return new OrderNormalizationTransformer();
        }

        @Bean
        MessageChannel testInput() {
            return new DirectChannel();
        }

        @Bean
        QueueChannel testOutput() {
            return new QueueChannel();
        }

        @Bean
        IntegrationFlow testTransformFlow(
                OrderNormalizationTransformer transformer) {
            return IntegrationFlow.from("testInput")
                    .transform(RawOrder.class, transformer::transform)
                    .channel("testOutput")
                    .get();
        }
    }

    @Autowired
    @Qualifier("testInput")
    MessageChannel input;

    @Autowired
    @Qualifier("testOutput")
    QueueChannel output;

    @Test
    void validPayloadProducesOneOutputMessage() {
        RawOrder raw = new RawOrder(
                "ORD-201", "100000", "vn");

        assertTrue(input.send(
                MessageBuilder.withPayload(raw).build()));

        Message<?> received = output.receive(0);
        assertNotNull(received);
        ValidatedOrder normalized =
                (ValidatedOrder) received.getPayload();
        assertEquals("VN", normalized.destinationCountry());
        assertEquals(new BigDecimal("100000"), normalized.amountVnd());
        assertNull(output.receive(0));
    }

    @Test
    void invalidPayloadThrowsAndDoesNotProduceOutput() {
        RawOrder raw = new RawOrder(
                "ORD-202", "broken", "VN");

        RuntimeException failure = assertThrows(
                RuntimeException.class,
                () -> input.send(
                        MessageBuilder.withPayload(raw).build()));

        Throwable root = failure;
        while (root.getCause() != null && root.getCause() != root) {
            root = root.getCause();
        }
        assertInstanceOf(InvalidOrderException.class, root);
        assertEquals(
                "INVALID_AMOUNT_FORMAT",
                ((InvalidOrderException) root).errorCode());
        assertNull(output.receive(0));
    }
}
~~~

**Điều test chứng minh:** với DirectChannel đồng bộ, caller thấy exception và nhánh output không nhận message khi Transformer lỗi. Test không đòi hỏi rằng mọi exception luôn có cùng một wrapper class: nó truy đến nguyên nhân gốc.

**Điều test chưa chứng minh:** ErrorMessage trong flow async, broker redelivery, DLQ bền, retry sau restart hoặc idempotency của downstream. Các chủ đề này phải kiểm thử riêng.

### 13.1. Test null result

Đối với một Transformer cố tình trả null, một integration test riêng có thể thiết lập flow:

~~~java
@Bean
IntegrationFlow invalidNullTransformExample() {
    return IntegrationFlow.from("nullTransformInputChannel")
            .transform(String.class, text -> (String) null)
            .channel("unusedOutputChannel")
            .get();
}
~~~

Đây là **ví dụ kiểm thử phản quy tắc**, cần khai báo hai channel trong test context; không triển khai flow này vào production. Gửi một String không null vào nullTransformInputChannel sẽ gây lỗi chuyển đổi thay vì coi đó là message bị Filter loại.

## 14. Integration test với ExecutorChannel: lỗi đi theo ErrorMessage

Ví dụ dưới đây dùng **CountDownLatch** để quan sát ErrorMessage trên channel lỗi. Ta không giả định rằng lỗi sẽ quay về thread gọi send().

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(AsyncTransformerFailureTest.Config.class)
class AsyncTransformerFailureTest {

    static final class FailureProbe {
        final CountDownLatch received = new CountDownLatch(1);
        final AtomicReference<Throwable> failure = new AtomicReference<>();
    }

    @Configuration
    @EnableIntegration
    static class Config {
        @Bean
        OrderNormalizationTransformer transformer() {
            return new OrderNormalizationTransformer();
        }

        @Bean
        FailureProbe failureProbe() {
            return new FailureProbe();
        }

        @Bean
        ThreadPoolTaskExecutor testExecutor() {
            ThreadPoolTaskExecutor executor =
                    new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(2);
            executor.setQueueCapacity(10);
            executor.setThreadNamePrefix("test-transform-");
            return executor;
        }

        @Bean
        MessageChannel asyncInput(
                @Qualifier("testExecutor")
                ThreadPoolTaskExecutor executor) {
            return new ExecutorChannel(executor);
        }

        @Bean
        QueueChannel successOutput() {
            return new QueueChannel();
        }

        @Bean
        MessageChannel testErrorChannel() {
            return new DirectChannel();
        }

        @Bean
        IntegrationFlow transformerFlow(
                OrderNormalizationTransformer transformer) {
            return IntegrationFlow.from("asyncInput")
                    .transform(RawOrder.class, transformer::transform)
                    .channel("successOutput")
                    .get();
        }

        @Bean
        IntegrationFlow failureFlow(FailureProbe probe) {
            return IntegrationFlow.from("testErrorChannel")
                    .handle(message -> {
                        if (message instanceof ErrorMessage error) {
                            probe.failure.set(error.getPayload());
                            probe.received.countDown();
                        }
                    })
                    .get();
        }
    }

    @Autowired
    @Qualifier("asyncInput")
    MessageChannel input;

    @Autowired
    @Qualifier("successOutput")
    QueueChannel output;

    @Autowired
    FailureProbe probe;

    @Test
    void malformedPayloadProducesErrorMessage() throws Exception {
        Message<RawOrder> message = MessageBuilder
                .withPayload(
                        new RawOrder("ORD-300", "oops", "VN"))
                .setHeader(
                        MessageHeaders.ERROR_CHANNEL,
                        "testErrorChannel")
                .setHeader("eventId", "evt-300")
                .build();

        assertTrue(input.send(message));

        assertTrue(probe.received.await(5, TimeUnit.SECONDS));
        assertNotNull(probe.failure.get());
        assertNull(output.receive(0));
    }
}
~~~

**Điều test chứng minh:** khi Spring Integration xử lý message trong ExecutorChannel và gửi lỗi theo header errorChannel hợp lệ, một consumer lỗi có thể nhận ErrorMessage **sau** thao tác send(). Thời gian chờ 5 giây là timeout kiểm thử, không phải bảo đảm hiệu năng thực tế.

**Lưu ý:** nếu hệ thống có các executor/error handler tùy chỉnh, hoặc message được xử lý bởi library thread không nằm trong Spring Integration task, cần kiểm tra riêng đường publish lỗi. Không khẳng định rằng đặt header là đủ để bắt mọi exception trên mọi thread.

## 15. Những ca kiểm thử còn thiếu

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Input hợp lệ | Có đúng một output kiểu ValidatedOrder |
| Amount không parse được | INVALID_AMOUNT_FORMAT và không có output thành công |
| Amount âm hoặc có phần thập phân | INVALID_AMOUNT_VALUE |
| Mã quốc gia thiếu | INVALID_COUNTRY |
| Transformer trả null | Lỗi chuyển đổi, không tự discard |
| Downstream handler ném exception | Không gắn nhầm mã lỗi parse |
| ErrorMessage không có originalMessage | Error handler không NPE |
| Header errorChannel không đáng tin | Ingress loại/thay bằng channel nội bộ |
| Lỗi schemaVersion không hỗ trợ | Quarantine hoặc reject, không retry vô hạn |
| Lỗi transient ở bước lookup riêng | Retry có giới hạn và có RecoveryCallback |
| Quá tải ExecutorChannel | Admission failure/backpressure được phát hiện |
| QueueChannel không có consumer | Monitoring phát hiện backlog, không nhầm parse failure |
| Splitter con bị transform lỗi | Aggregator có timeout/partial policy rõ |
| Replay sau sửa schema | Cùng eventId, downstream idempotency được áp dụng |
| Consumer lỗi trong error flow | Có cảnh báo/đường xử lý lỗi thứ cấp |

## 16. Observability cho Transformer

Một luồng có nhiều bước dễ khiến mọi lỗi được gom chung vào nhãn “message failed”. Nên đo riêng giai đoạn chuyển đổi:

| Tín hiệu | Mục đích |
| --- | --- |
| **transform_attempts_total{transformer}** | Tổng số lần thử chuyển đổi |
| **transform_success_total{transformer}** | Chuyển đổi thành công |
| **transform_failed_total{transformer,error_code}** | Lỗi phân loại được |
| **transform_duration_seconds{transformer}** | Latency p50/p95/p99 |
| **transform_retry_total{transformer}** | Số retry khi có policy |
| **transform_quarantine_pending_total** | Số message cần điều tra/replay |
| **error_channel_delivery_failed_total** | Đường thông báo lỗi cũng thất bại |
| **downstream_failed_total{component}** | Không nhầm lỗi sau Transformer với lỗi parse |

Metric label nên có **tập giá trị giới hạn** như tên Transformer hoặc mã lỗi. Không đặt orderId, eventId, nội dung exception hay raw input làm label vì cardinality và nguy cơ lộ dữ liệu.

### 16.1. Log có cấu trúc

Ví dụ một sự kiện bị từ chối:

~~~json
{
  "eventId": "evt-109",
  "component": "orderNormalizationTransformer",
  "errorCode": "INVALID_AMOUNT_FORMAT",
  "schemaVersion": 1,
  "retryable": false,
  "outcome": "QUARANTINED"
}
~~~

Một log như trên thể hiện **nguyên nhân và quyết định xử lý**, không chứa amount raw hoặc toàn bộ payload. Nếu cần đối chiếu, lưu bản gốc an toàn tại quarantine storage riêng có access control và retention.

### 16.2. Alert và vận hành

Nên cảnh báo khi:

- Tỷ lệ INVALID_AMOUNT_FORMAT tăng đột biến, có thể producer đổi format.
- Sự kiện UNSUPPORTED_SCHEMA_VERSION xuất hiện sau deploy.
- Global errorChannel nhận lượng ErrorMessage cao bất thường.
- ErrorMessage không có subscriber phù hợp hoặc error handler liên tục lỗi.
- Queue chứa failed/retry messages tích tụ, tuổi message tăng.
- Thành công của Transformer ổn định nhưng lỗi downstream tăng: đây có thể là sự cố hệ thống đích, không phải converter.

Không tạo vòng lặp **transform error → retry nguyên input → transform error** không có giới hạn. Với lỗi đầu vào cố định, chỉ nên replay sau khi có thay đổi dữ liệu, schema hoặc code.

## 17. Bài thực hành: JSON event bị lỗi trong luồng thanh toán

Xây dựng một ứng dụng Spring Integration nhận sự kiện:

~~~json
{
  "eventId": "evt-801",
  "eventType": "payment.completed",
  "schemaVersion": 1,
  "paymentId": "pay-801",
  "amountVnd": "2400000",
  "currency": "VND"
}
~~~

**Yêu cầu:**

1. Nhận JSON String từ một channel đầu vào.
2. Chuyển JSON thành **PaymentEvent** có số tiền kiểu BigDecimal và currency hợp lệ.
3. Từ chối JSON sai cú pháp, thiếu paymentId hoặc amount không hợp lệ.
4. Với schemaVersion chưa được hỗ trợ, đưa event vào quarantine thay vì retry vô hạn.
5. Với dữ liệu hợp lệ, Router chọn một trong **accountingChannel** và **auditChannel** theo hợp đồng nghiệp vụ đã công bố. Nếu một event cần đồng thời cả hai, sử dụng Recipient List thay vì giả định router chỉ chọn một.
6. Với luồng đồng bộ, caller phải thấy lỗi convert; với luồng bất đồng bộ, ErrorMessage phải tới kênh xử lý đã cấu hình.
7. ErrorMessage không được làm lộ dữ liệu cá nhân, token hay thông tin thanh toán bí mật.
8. EventId giữ ổn định qua replay; accounting consumer phải có idempotency.

### Gợi ý thiết kế

~~~mermaid
flowchart LR
    P["Producer"] --> I["rawPaymentEvents"]
    I --> V["JSON schema validation"]
    V --> T["Payment Transformer"]
    T --> R["Recipient List / Router"]
    R --> A["Accounting"]
    R --> B["Audit"]
    V -.->|"Malformed"| Q["Quarantine"]
    T -.->|"Invalid amount"| Q
    R -.->|"Downstream failure"| E["Retry / error flow của recipient"]
~~~

### Các bước thực hiện

1. Viết record RawPaymentEvent và PaymentEvent, trong đó PaymentEvent dùng BigDecimal.
2. Tạo **PaymentEventTransformer** thuần Java, đặt errorCode cho mỗi lỗi dữ liệu.
3. Cấu hình IntegrationFlow với Transformer và channel đầu ra riêng.
4. Viết test chuyển đổi thành công và test trả null có chủ đích để quan sát MessageTransformationException.
5. Viết test DirectChannel: input sai ném exception, không tạo output.
6. Đổi input qua ExecutorChannel với bounded executor và errorChannel riêng.
7. Dùng CountDownLatch trong test để xác nhận nhận được ErrorMessage, không phụ thuộc Thread.sleep.
8. Thêm bước lookup schema từ một mock service có thể timeout; áp dụng retry chỉ cho lỗi tạm thời ở bước này.
9. Mô phỏng consumer accounting đã ghi database nhưng response bị mất; kiểm tra eventId và unique constraint/idempotency.
10. Thiết kế quarantine có lưu trữ bền, trạng thái replay, giới hạn số lần thử và metrics.

### Tiêu chí đánh giá

| Tiêu chí | Đạt khi |
| --- | --- |
| Pure transformation | Không gọi DB, email hoặc payment API trong Transformer |
| Error classification | Có mã lỗi phân biệt dữ liệu và hạ tầng |
| Null contract | Không dùng null để biểu diễn discard |
| Sync path | Lỗi về caller khi dùng DirectChannel |
| Async path | ErrorMessage được xử lý đúng kênh, có timeout test |
| Retry | Chỉ lỗi có thể phục hồi được thử lại |
| Idempotency | Replay không tạo tác động accounting trùng |
| Observability | Trace và error code có thể đối chiếu mà không lộ dữ liệu nhạy cảm |

## 18. Tình huống nâng cao để tự phân tích

### Tình huống A: lỗi ở từng message con của Splitter

Một Splitter tạo 100 invoice items rồi Transformer chuyển mỗi item thành DTO cho Aggregator. Item thứ 43 sai định dạng tiền tệ.

Hãy quyết định:

- Cả batch phải thất bại hay chỉ item 43?
- Có cần gửi một **failure result** có cấu trúc vào Aggregator không?
- Group có timeout và release strategy như thế nào?
- Nếu retry item 43 sau khi sửa dữ liệu, có trùng item đã hoàn tất không?
- CorrelationId và sequence metadata nào cần giữ?

### Tình huống B: dữ liệu mới khi consumer chưa nâng version

Producer bắt đầu gửi schemaVersion=2 nhưng consumer chỉ hỗ trợ version 1. Transformer lỗi **UNSUPPORTED_SCHEMA_VERSION**.

Hãy nêu tại sao retry ngay với payload không đổi không có ích, cách giữ event trong quarantine, việc triển khai consumer mới và nguyên tắc replay bằng eventId cũ.

### Tình huống C: lỗi xuất hiện sau một bước enrich qua HTTP

Một workflow dùng Transformer chuẩn hóa trước, rồi enrich bằng HTTP lookup. HTTP lookup bị timeout liên tục và operator bật retry toàn bộ pipeline.

Hãy kiểm tra chi phí retry parse lại, nguy cơ lặp các bước trước đã có side effect và cân nhắc đưa retry vào riêng HTTP endpoint với circuit breaker và timeout.

### Tình huống D: lỗi xuất hiện sau khi send() thành công

Caller gửi message tới ExecutorChannel, nhận true và lập tức trả HTTP 200 cho client. Vài giây sau Transformer phát hiện JSON không hợp lệ.

Hãy đề xuất hợp đồng trạng thái bất đồng bộ (ví dụ HTTP 202 cùng tracking ID), nơi thông báo thất bại, retention của event và cách client tra cứu trạng thái hoàn tất.

## 19. Câu hỏi tự kiểm tra

1. Vì sao Transformer không được trả null? Message Filter khác Transformer ở điểm nào?
2. Khi nào một phương thức Service Activator được phép trả null?
3. Lỗi INVALID_AMOUNT_FORMAT có nên retry với cùng input không? Tại sao?
4. Khi dùng DirectChannel, exception từ Transformer được truyền đi như thế nào?
5. Vì sao tạo bean global errorChannel không tự bắt mọi exception đồng bộ?
6. ErrorMessage chứa gì ở payload? Original message có luôn tồn tại không?
7. Khi nào errorChannel header được ưu tiên hơn global errorChannel?
8. Vì sao không nên tin errorChannel do HTTP client gửi?
9. RequestHandlerRetryAdvice có nhiệm vụ gì, và vì sao nó cần gắn vào đúng endpoint?
10. Khi nào nên dùng ErrorMessageSendingRecoverer?
11. Vì sao replay một event có MessageHeaders.ID mới vẫn phải được coi là cùng logical event?
12. Điều gì xảy ra nếu một message con lỗi trước Aggregator?
13. Một lỗi downstream xảy ra sau Transformer có nên được thống kê như lỗi parse không?
14. Có thể dùng ErrorMessage hoặc một channel tên DLQ làm bằng chứng message được lưu bền không?
15. Test đồng bộ và test bất đồng bộ khác nhau ở cách chờ và quan sát kết quả ra sao?

## 20. Checklist trước khi triển khai

- Transformer có hợp đồng input/output rõ ràng, không dùng null để bỏ message.
- Dữ liệu thô được validate và giới hạn kích thước trước khi parse tốn kém.
- Exception được phân loại theo mã lỗi ổn định và khả năng retry.
- Không giấu lỗi bằng payload mặc định có vẻ hợp lệ.
- Pure transformation không gây side effect; I/O được tách sang adapter/enricher phù hợp.
- Java DSL nối input/output channel đúng, output có consumer thật.
- Ranh giới **DirectChannel vs ExecutorChannel/QueueChannel** được xác định và kiểm thử.
- Đã cấu hình error channel đúng với ingress/gateway và nguồn dữ liệu đáng tin.
- Error handler xử lý được thiếu originalMessage hoặc failedMessage.
- Mỗi retry policy có số lần thử, backoff, timeout và recovery rõ ràng.
- Malformed/unsupported message không bị retry vô hạn; có quarantine hoặc reject có chủ đích.
- Message quan trọng cần replay được lưu bền, có eventId, schemaVersion và retention phù hợp.
- Replay downstream có idempotency khi tác vụ nghiệp vụ có side effect.
- Headers reply/error/correlation được quản lý bởi thành phần tin cậy và giữ đúng nơi cần dùng.
- Log, trace, metric đủ quan sát nhưng không lộ raw payload hoặc header nhạy cảm.
- Unit test bao phủ valid/invalid/null; integration test bao phủ sync/async/error flow.
- Lỗi đường xử lý ErrorMessage có alert và không gây vòng lặp vô hạn.

**Kết luận:** Transformer được phép **ném lỗi** khi không thể tạo kết quả hợp lệ. Đó là một hành vi đúng theo hợp đồng, không phải lý do để tự trả null hay chuyển dữ liệu sai sang downstream. Trong Spring Integration, nơi lỗi xuất hiện và đường xử lý phụ thuộc vào **ranh giới channel/thread**: đồng bộ thường truyền exception về caller, còn xử lý bất đồng bộ cần **ErrorMessage/errorChannel** phù hợp. Kết hợp phân loại lỗi, pure transformation, retry đúng bước, quarantine, correlation và kiểm thử đầy đủ sẽ giúp luồng Transformer an toàn, quan sát được và có khả năng phục hồi.

## Tài liệu tham khảo

- [Spring Integration Reference — Transformer](https://docs.spring.io/spring-integration/reference/transformer.html): hợp đồng Transformer, null return, MessageTransformationException và annotation.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): DirectChannel, ExecutorChannel, ErrorMessage, errorChannel và poller.
- [Spring Integration API — MessageTransformationException](https://docs.spring.io/spring-integration/api/org/springframework/integration/transformer/MessageTransformationException.html): loại exception chuyên biệt cho transformation errors.
- [Spring Integration Reference — Provided Advice Classes](https://docs.spring.io/spring-integration/reference/handler-advice/classes.html): RequestHandlerRetryAdvice, stateless/stateful retry và recovery.
- [Spring Integration API — ErrorMessageSendingRecoverer](https://docs.spring.io/spring-integration/api/org/springframework/integration/handler/advice/ErrorMessageSendingRecoverer.html): phục hồi bằng ErrorMessage sau khi hết retry.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): DirectChannel, ExecutorChannel, QueueChannel và ranh giới xử lý.
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): cấu hình IntegrationFlow, Transformer và các endpoint.
