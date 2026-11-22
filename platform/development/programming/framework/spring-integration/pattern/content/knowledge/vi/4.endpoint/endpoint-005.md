# Transformer chuyển payload hoặc message

Trong **Spring Integration**, **Transformer** là endpoint chuyển một thông điệp từ dạng mà producer cung cấp sang dạng mà consumer cần. Transformer hỗ trợ nguyên tắc **loose coupling**: một hệ thống nhận đơn hàng dạng chuỗi/JSON không buộc mọi thành phần phía sau phải hiểu định dạng đầu vào; thay vào đó, một bước biến đổi có thể tạo payload nghiệp vụ thống nhất trước khi Router, Filter, Aggregator hoặc Gateway tiếp tục xử lý.

Bài thuộc chương **Endpoint** của module **SPRING_INTEGRATION_PATTERN**. Module hướng đến thực hành Enterprise Integration Patterns với Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation, đồng thời kiểm thử và quan sát các nhánh luồng. Ở đây, trọng tâm là **hai cách trả kết quả của Transformer**:

1. **Trả về payload**: framework đóng gói giá trị kết quả thành message đầu ra và, theo mặc định, truyền các headers hợp lệ từ đầu vào.
2. **Trả về `Message<?>`**: transformer đã tự xây dựng message hoàn chỉnh và chịu trách nhiệm về payload **lẫn** tập headers đầu ra.

Khác biệt này ảnh hưởng trực tiếp tới `traceId`, `tenantId`, `correlationId`, `replyChannel`, `errorChannel` và những luồng có Gateway hoặc Splitter/Aggregator.

## 1. Mục tiêu học tập

Hoàn thành bài học, bạn có thể:

- Nhận diện vai trò của Transformer trong EIP và phân biệt nó với Filter, Router, Service Activator và Message Converter.
- Xây dựng Transformer qua `@Transformer` và Java DSL `IntegrationFlow.transform(...)`.
- Chọn hợp lý giữa việc trả một object payload và trả `Message<T>`.
- Giải thích cơ chế truyền headers và quyết định header nào cần giữ, ghi đè hoặc bỏ khi tạo message mới.
- Giải thích vì sao Transformer không nên trả `null` và cách biểu diễn nhánh muốn loại bỏ message.
- Kết hợp Transformer với Router, Splitter, Aggregator, Gateway, retry và error channel.
- Viết kiểm thử kiểm chứng nội dung payload, header propagation và xử lý lỗi.

## 2. Vị trí của Transformer trong message flow

Spring Messaging có interface `Message<T>`, trong đó một message gồm hai phần:

- **Payload:** dữ liệu chính, chẳng hạn `RawOrder`, `String`, `byte[]` hoặc `NormalizedOrder`.
- **Headers:** metadata như `tenantId`, `traceId`, `contentType`, `correlationId`, `replyChannel`, `errorChannel`.

Transformer nhận message đầu vào và tạo kết quả biến đổi gửi đến output channel. Endpoint sở hữu Transformer được gọi khi message đi vào input channel.

~~~mermaid
flowchart LR
    IN["Inbound adapter / Gateway"] --> Q["Input channel"]
    Q --> T["Transformer"]
    T --> OUT["Output channel"]
    OUT --> R{"Router / Filter"}
    R --> A["Business handler A"]
    R --> B["Business handler B"]
~~~

Ví dụ trong nghiệp vụ:

- Checkout tạo `RawOrder(orderId, amountText, regionText)` với dữ liệu chưa chuẩn hóa.
- Transformer đổi `amountText` từ chuỗi sang `BigDecimal`, chuẩn hóa `regionText` và kiểm tra quy tắc chuyển đổi.
- Router đọc `region` hoặc thuộc tính của payload đã chuẩn hóa để chọn nhánh xử lý.
- Các nhánh có thể phát sự kiện, gửi email, gộp dữ liệu hoặc ghi kết quả.

Điểm quan trọng: **Transformer có trách nhiệm tạo biểu diễn mới**. Nó không tự quyết định chọn nhiều đích như Router và không có chức năng âm thầm loại message như Filter.

### So sánh nhanh các endpoint

| Thành phần | Vai trò chính | Kết quả điển hình |
|---|---|---|
| **Transformer** | Chuyển cấu trúc/giá trị dữ liệu | Payload mới hoặc `Message<?>` mới |
| **Filter** | Quyết định thông điệp có được đi tiếp | Chấp nhận hoặc loại |
| **Router** | Chọn channel/nhánh tiếp theo | Một hoặc nhiều channel đích tùy cấu hình |
| **Service Activator** | Gọi dịch vụ/logic ứng dụng | Có thể trả reply hoặc chỉ làm side effect |
| **Header Enricher** | Bổ sung hoặc tính toán headers | Message có metadata được làm giàu |
| **Splitter** | Tách một message thành nhiều phần | Nhiều message con |
| **Aggregator** | Ghép message liên quan thành nhóm | Kết quả tổng hợp |

Transformer có thể thay đổi headers, nhưng nếu mục tiêu **chỉ** là gắn metadata, Header Enricher thường biểu đạt ý định rõ hơn.

## 3. Hai hợp đồng trả kết quả: payload và Message

Xét cùng một message đầu vào:

~~~text
Message<RawOrder>
  payload:
    orderId = "order-1001"
    amountText = "120.50"
  headers:
    tenantId = "shop-a"
    traceId = "trace-1001"
    businessCorrelationId = "order-1001"
    id / timestamp = framework quản lý
~~~

Transformer có thể trả một `NormalizedOrder` hoặc một `Message<NormalizedOrder>`. Cả hai cách đều hợp lệ nhưng quy tắc truyền headers khác nhau.

| Tiêu chí | Trả **payload** | Trả **Message** |
|---|---|---|
| Ví dụ kiểu trả | `NormalizedOrder` | `Message<NormalizedOrder>` |
| Ai đóng gói message đầu ra? | Framework | Code transformer |
| Header đầu vào | Thông thường được truyền sang đầu ra, trừ headers bị chặn/không phù hợp | **Không tự động sao chép** khi transformer trả message hoàn chỉnh |
| Muốn chỉnh metadata | Dùng bước enrich hoặc trả message | Dùng `MessageBuilder` để tạo headers chủ động |
| Rủi ro | Vô tình truyền header không nên đi tiếp | Vô tình **đánh rơi** trace/correlation/reply/error header |
| Nên chọn khi | Chỉ đổi nội dung nghiệp vụ | Cần kiểm soát cả payload lẫn metadata |

Quy tắc ngắn gọn:

> **Trả payload → framework lo tạo message và truyền headers thông thường. Trả Message → bạn định nghĩa toàn bộ message đầu ra.**

Đây là hành vi riêng cần chú ý của **Transformer** trong Spring Integration. Nhiều message-producing endpoint khác có cơ chế truyền headers vào reply ngay cả khi handler trả message, nhưng **Transformer trả message hoàn chỉnh là ngoại lệ** được tài liệu Spring Integration nêu rõ.

~~~mermaid
flowchart TD
    INPUT["Message<RawOrder>"] --> T{"Transformer trả loại gì?"}
    T -->|"NormalizedOrder"| P["Framework tạo Message đầu ra"]
    P --> PH["Payload mới + propagate headers hợp lệ"]
    T -->|"Message<NormalizedOrder>"| M["Giữ Message do transformer tạo"]
    M --> MH["Payload + headers do code quy định"]
    PH --> OUT["Output channel"]
    MH --> OUT
~~~

**Không được suy ra** rằng mọi header đều luôn được giữ bất kể cấu hình. Một số headers có thể bị loại bằng cấu hình not-propagated headers, và `id`/`timestamp` được quản lý theo vòng đời message. Khi qua adapter/protocol khác, quy tắc mapping headers cũng có thể khác.

## 4. Trường hợp 1: Transformer chỉ trả payload

Đây là cách đơn giản nhất và thường nên thử đầu tiên. Transformer nhận payload (hoặc cả message), xử lý và trả object mới.

### 4.1. Định nghĩa DTO đầu vào/đầu ra

Ví dụ dùng Java 17+ với `record`:

~~~java
import java.math.BigDecimal;

public record RawOrder(
        String orderId,
        String amountText,
        String regionText
) {}

public record NormalizedOrder(
        String orderId,
        BigDecimal amount,
        String region
) {}
~~~

`BigDecimal` tránh sai số của `double` khi biểu diễn tiền; trong hệ thống thật, vẫn cần định nghĩa currency, scale, rounding và quy tắc domain riêng.

### 4.2. Chuyển payload bằng annotation

~~~java
import java.math.BigDecimal;
import java.util.Locale;

import org.springframework.integration.annotation.Transformer;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Component;

@Component
public class NormalizeOrderTransformer {

    @Transformer(
            inputChannel = "orders.raw",
            outputChannel = "orders.normalized")
    public NormalizedOrder normalize(
            RawOrder input,
            @Header("tenantId") String tenantId) {

        if (input.orderId() == null || input.orderId().isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("tenantId is required");
        }

        BigDecimal amount = new BigDecimal(input.amountText());
        if (amount.signum() < 0) {
            throw new IllegalArgumentException("amount must be >= 0");
        }

        String region = input.regionText()
                .trim()
                .toUpperCase(Locale.ROOT);

        return new NormalizedOrder(
                input.orderId().trim(),
                amount,
                region);
    }
}
~~~

Ở đây, tham số `RawOrder input` được binding từ **payload**, còn `@Header("tenantId")` cho phép lấy metadata mà không cần ép kiểu thủ công từ `MessageHeaders`. Phương thức trả `NormalizedOrder`, vì vậy framework tạo message kết quả và theo mặc định giữ `tenantId`, `traceId`, `businessCorrelationId` nếu chúng được truyền từ đầu vào và không bị cấu hình loại.

Ví dụ producer:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<RawOrder> incoming = MessageBuilder
        .withPayload(new RawOrder(
                "order-1001", "120.50", " north "))
        .setHeader("tenantId", "shop-a")
        .setHeader("traceId", "trace-1001")
        .setHeader("businessCorrelationId", "order-1001")
        .build();
~~~

Sau khi message này đi qua endpoint `orders.raw`, message ở `orders.normalized` thường mang payload `NormalizedOrder("order-1001", 120.50, "NORTH")` và các header nghiệp vụ trên.

### 4.3. Transformer nhận cả Message nhưng vẫn chỉ trả payload

Có thể truy cập payload và headers qua object message rồi trả **chỉ payload**:

~~~java
import org.springframework.messaging.Message;

public NormalizedOrder normalizeWholeMessage(
        Message<RawOrder> input) {

    String tenantId = input.getHeaders()
            .get("tenantId", String.class);

    if (tenantId == null || tenantId.isBlank()) {
        throw new IllegalArgumentException("Missing tenantId");
    }

    RawOrder order = input.getPayload();

    return new NormalizedOrder(
            order.orderId(),
            new BigDecimal(order.amountText()),
            order.regionText().strip().toUpperCase(Locale.ROOT));
}
~~~

*Lưu ý:* `@Transformer` đặt trên **một** phương thức endpoint thực tế (các ví dụ trên minh họa hai cách viết thay thế). Nhận `Message<RawOrder>` **không** làm thay đổi quy tắc truyền header; yếu tố quyết định là **kiểu giá trị trả về**.

## 5. Trường hợp 2: Transformer trả Message hoàn chỉnh

Chọn cách này khi đầu ra phải thay cả payload lẫn metadata, ví dụ:

- Gắn `schemaVersion` mới sau chuẩn hóa.
- Chọn lại `contentType` cho message được biến đổi.
- Chỉ giữ `tenantId`, `traceId` hoặc correlation key được cho phép khi chuyển ranh giới tin cậy.
- Tính `route` hoặc `validationResult` để Router/Filter ở bước sau sử dụng.
- Cần kiểm soát headers đặc biệt cho Gateway, lỗi và fan-in.

### 5.1. Tạo Message mới có header được chọn rõ ràng

~~~java
import java.math.BigDecimal;
import java.util.Locale;

import org.springframework.integration.annotation.Transformer;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;

@Component
public class CompleteOrderMessageTransformer {

    @Transformer(
            inputChannel = "orders.complete.input",
            outputChannel = "orders.complete.output")
    public Message<NormalizedOrder> transform(Message<RawOrder> input) {
        RawOrder raw = input.getPayload();

        NormalizedOrder normalized = new NormalizedOrder(
                raw.orderId().strip(),
                new BigDecimal(raw.amountText()),
                raw.regionText().strip().toUpperCase(Locale.ROOT));

        return MessageBuilder.withPayload(normalized)
                .setHeader("tenantId",
                        input.getHeaders().get("tenantId"))
                .setHeader("traceId",
                        input.getHeaders().get("traceId"))
                .setHeader("businessCorrelationId",
                        input.getHeaders().get("businessCorrelationId"))
                .setHeader("schemaVersion", 2)
                .build();
    }
}
~~~

Cách này chủ động xác định ba header được giữ và bổ sung `schemaVersion`. Header đầu vào khác **không tự nhiên đi theo** khi transformer trả một `Message` hoàn chỉnh. Nếu output còn cần `replyChannel`, `errorChannel` hoặc sequence metadata, code phải giữ các header cần thiết theo hợp đồng flow.

Ví dụ trên phù hợp với luồng xử lý một chiều. Đối với một flow request–reply, đừng loại `replyChannel`/`errorChannel` mà không xác minh cách Gateway nhận phản hồi và đường đi của lỗi.

### 5.2. Khi cần giữ hầu hết headers

Có thể dùng `MessageBuilder.fromMessage(...)` nếu **payload giữ nguyên**, hoặc `withPayload(...).copyHeaders(...)` nếu **payload mới**:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> incoming = MessageBuilder.withPayload("  order-1001  ")
        .setHeader("tenantId", "shop-a")
        .setHeader("traceId", "trace-1001")
        .build();

// Payload không đổi; thêm metadata
Message<String> tagged = MessageBuilder.fromMessage(incoming)
        .setHeader("validated", true)
        .build();

// Payload đổi; sao chép các header đầu vào
Message<String> normalized = MessageBuilder
        .withPayload(incoming.getPayload().strip().toUpperCase())
        .copyHeaders(incoming.getHeaders())
        .setHeader("normalized", true)
        .build();
~~~

`copyHeaders(...)` thuận tiện với luồng nội bộ đã kiểm soát metadata; nó không phải giải pháp phù hợp để sao chép mù mọi header qua API công khai, message broker hoặc kênh ra bên thứ ba. Trong những ranh giới ấy, hãy chọn **whitelist** các header thực sự cần thiết.

Khi tạo message mới bằng builder thông thường, `id` và `timestamp` được framework quản lý như metadata của message mới. Không dùng ID message làm khóa nghiệp vụ xuyên nhiều bước biến đổi; nếu cần liên kết toàn giao dịch, dùng một `businessCorrelationId` hoặc correlation ID theo hợp đồng EIP.

### 5.3. Giữ đúng header điều khiển và metadata fan-in

Khi dùng Gateway hoặc Aggregator, một số header có vai trò điều khiển luồng:

| Header | Được dùng để | Lưu ý khi trả Message |
|---|---|---|
| `MessageHeaders.REPLY_CHANNEL` | Channel nhận reply | Mất header này có thể làm gián đoạn trả lời trong một số kiến trúc |
| `MessageHeaders.ERROR_CHANNEL` | Channel nhận lỗi | Mất header khiến lỗi đi theo đường xử lý khác |
| `IntegrationMessageHeaderAccessor.CORRELATION_ID` | Gom nhóm message liên quan | Bảo toàn nếu Aggregator cần khóa nhóm đó |
| `IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER` | Thứ tự phần tử trong nhóm | Không tự đổi trừ khi thiết kế chuỗi mới |
| `IntegrationMessageHeaderAccessor.SEQUENCE_SIZE` | Số phần tử nhóm dự kiến | Nếu bị mất, release strategy có thể thay đổi hành vi |
| `traceId` (header nghiệp vụ) | Truy vết qua nhiều endpoint | Nên giữ nhất quán xuyên các nhánh cần quan sát |
| `tenantId` (header nghiệp vụ) | Định tuyến/kiểm soát ranh giới tenant | Cần kiểm tra độ tin cậy và chính sách tiết lộ |

Nếu thực sự muốn đưa message này quay về Gateway, có thể chọn sao chép những header điều khiển đã được xác minh hoặc dùng `copyHeaders(input.getHeaders())` trong luồng nội bộ. Không lưu `MessageChannel` object trực tiếp vào định dạng truyền tin bên ngoài mà chưa có header mapper phù hợp.

### 5.4. Tránh sai lệch giữa payload và headers

Nếu payload đã đổi từ `RawOrder` sang `NormalizedOrder`, header `contentType`, `schemaVersion` hoặc `payloadType` do ứng dụng định nghĩa cũng có thể cần cập nhật. Không giữ metadata của định dạng cũ chỉ vì dùng `copyHeaders`.

~~~java
Message<NormalizedOrder> result = MessageBuilder
        .withPayload(normalizedOrder)
        .copyHeaders(input.getHeaders())
        .removeHeader("legacyPayloadType")
        .setHeader("schemaVersion", 2)
        .build();
~~~

Phần này minh họa biến `input` và `normalizedOrder` đã được định nghĩa trong logic transformer. Khi dùng converter/serializer ở adapter, hãy để converter và header mapper điều phối `contentType` theo cấu hình thực tế.

## 6. Cấu hình Transformer bằng Java DSL

Ngoài `@Transformer`, Spring Integration cung cấp `IntegrationFlow` và toán tử `transform(...)`. Ví dụ đơn giản dùng object service:

~~~java
import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
public class TransformFlowConfiguration {

    @Bean
    public IntegrationFlow normalizeTextFlow() {
        return IntegrationFlow.from("text.input")
                .transform(String.class,
                        text -> text.strip().toUpperCase(Locale.ROOT))
                .channel("text.output")
                .get();
    }
}
~~~

Với Spring Integration phiên bản hỗ trợ Java DSL tích hợp, `transform(String.class, ...)` ràng buộc hàm theo kiểu payload, còn `IntegrationFlow.from("text.input")` khai báo đầu vào và `channel("text.output")` quy định đầu ra. Khi producer gửi message chứa `String`, bước transform tạo chuỗi chuẩn hóa, đồng thời framework thường giữ headers đầu vào theo quy tắc trả payload.

Nếu cần logic nhiều nhánh/validation phức tạp, nên dùng phương thức/bean chuyên trách thay vì nhét mọi điều kiện vào lambda DSL.

### 6.1. Biến đổi bằng SpEL khi đủ đơn giản

~~~java
@Bean
public IntegrationFlow trimFlow() {
    return IntegrationFlow.from("trim.input")
            .transform("payload.trim()")
            .channel("trim.output")
            .get();
}
~~~

Expression trên giả định payload có method `trim()`, ví dụ `String`. Nếu đầu vào có thể là loại khác, cần xác nhận kiểu hoặc dùng Transformer Java có kiểm tra rõ ràng. Với hệ thống chứa nhiều schema, những biến đổi dài và có kiểm thử nên nằm trong một bean dễ bảo trì.

### 6.2. Khi nào dùng transformer dựng sẵn?

Spring Integration cung cấp một số transformer có sẵn cho việc đổi định dạng, ví dụ `ObjectToStringTransformer`. Chúng giúp tránh viết lặp code chuyển đổi đơn giản. Tuy nhiên, `toString()` thường dành cho biểu diễn văn bản tổng quát, **không phải** hợp đồng serialization ổn định cho trao đổi giữa các service.

Khi biến đổi giữa JSON/XML/POJO, hãy chọn transformer hoặc converter phù hợp với schema, media type và cơ chế validation, thay vì tin rằng mọi object có thể đi qua `toString()`.

## 7. Null là lỗi của Transformer, không phải cách Filter

Một Transformer có nghĩa vụ sinh đầu ra hợp lệ cho message đã nhận. Nếu phương thức biến đổi trả `null`, Spring Integration ném `MessageTransformationException` (thay vì âm thầm bỏ message).

~~~java
import org.springframework.integration.annotation.Transformer;

@Transformer(inputChannel = "orders.raw", outputChannel = "orders.normalized")
public NormalizedOrder invalidTransformer(RawOrder order) {
    if (order.amountText() == null) {
        return null; // Sai hợp đồng: transformer phải sinh kết quả
    }
    return normalize(order);
}
~~~

Đoạn trên chỉ minh họa **anti-pattern**, `normalize(order)` biểu thị hàm xử lý được viết riêng và chưa khai báo trong ví dụ này.

Nếu yêu cầu là bỏ đơn hàng không hợp lệ mà không phát output, hãy tách trách nhiệm:

~~~mermaid
flowchart LR
    IN["Incoming Message"] --> V{"Filter: valid?"}
    V -->|Yes| T["Transformer: normalize"]
    T --> OUT["Output channel"]
    V -->|No| REJECT["Discard / discardChannel / audit"]
~~~

Có thể dùng `Filter` với reject/`discardChannel` được cấu hình, hoặc Transformer ném exception để đi qua error flow khi input **đáng lẽ phải hợp lệ** nhưng biến đổi thất bại. Hai trường hợp có ý nghĩa nghiệp vụ khác nhau.

### 7.1. Phân biệt input không hợp lệ và lỗi hạ tầng

- `NumberFormatException` khi parse `amountText` có thể là dữ liệu đầu vào không hợp lệ: quyết định đưa vào reject flow, dead-letter hoặc thông báo cho producer.
- Timeout khi truy vấn hệ thống ngoài từ một transformer thường là lỗi tạm thời: cân nhắc retry theo chính sách, đặt giới hạn thời gian.
- Lỗi code như `NullPointerException` có thể là bug: ghi nhận nguyên nhân gốc và thông tin correlation.

Không nên áp dụng retry vô hạn cho dữ liệu không thể chuyển đổi; retry không sửa được `amountText="invalid"`. Nếu transform có side effect, cần xem xét idempotency khi retry; một Transformer thuần túy và không side effect sẽ dễ kiểm thử hơn.

## 8. Transformer và metadata: chi tiết truyền headers

Spring Integration có quy tắc chung: những message-producing endpoint thường truyền các headers đầu vào sang message đầu ra nếu header đó chưa được đặt tại đầu ra. Tuy nhiên:

- **Transformer trả payload:** framework tạo message output và mặc định truyền các headers đầu vào có thể truyền, trừ trường hợp được loại bởi cấu hình hoặc ràng buộc của framework.
- **Transformer trả `Message`:** framework sử dụng message do transformer cung cấp; tác giả transformer tự chịu trách nhiệm tập headers. Đây là ngoại lệ đã được tài liệu Spring Integration nêu rõ.
- **Không có bảo đảm bất biến sâu:** dù cấu trúc `MessageHeaders` read-only, object bên trong payload và giá trị header vẫn có thể mutable.
- **Headers dành riêng cho hệ thống:** `id`, `timestamp` gắn với message instance; correlation key nghiệp vụ cần được bảo toàn một cách rõ ràng, không suy từ ID mới.

### 8.1. Ví dụ mất trace ID khi trả Message

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public Message<String> withoutTrace(Message<String> incoming) {
    return MessageBuilder
            .withPayload(incoming.getPayload().strip().toUpperCase())
            .build();
}
~~~

Kết quả chỉ có payload mới và headers mà builder/framework tự tạo. Không có `traceId` đầu vào trừ khi code đặt lại. Nếu sau đó một Router hoặc logging handler dựa trên `traceId`, luồng có thể mất khả năng truy vết.

Cách khắc phục có chủ đích:

~~~java
public Message<String> withTrace(Message<String> incoming) {
    return MessageBuilder
            .withPayload(incoming.getPayload().strip().toUpperCase())
            .setHeader("traceId", incoming.getHeaders().get("traceId"))
            .setHeader("businessCorrelationId",
                    incoming.getHeaders().get("businessCorrelationId"))
            .build();
}
~~~

Trong flow nội bộ với nhiều metadata cần giữ, có thể dùng `copyHeaders(...)` như mục 5.2. Đối với edge công khai, ưu tiên danh sách header cho phép.

### 8.2. Header có giá trị mutable

~~~java
import java.util.ArrayList;
import java.util.List;

List<String> flags = new ArrayList<>(List.of("validated"));
Message<RawOrder> input = MessageBuilder
        .withPayload(rawOrder)
        .setHeader("flags", flags)
        .build();

flags.add("processed");
// Cấu trúc headers vẫn bất biến, nhưng giá trị List bên trong thay đổi.
~~~

Đoạn này giả định `rawOrder` đã được khởi tạo từ một bản ghi nghiệp vụ. Để giữ một snapshot ổn định, có thể dùng `List.copyOf(flags)`; với object lồng nhau, cần quyết định deep-copy hoặc DTO bất biến. Điều này quan trọng với `PublishSubscribeChannel`, async channels và các endpoint có thể cùng nắm tham chiếu tới message.

## 9. Kết hợp Transformer với các pattern khác

### 9.1. Transformer trước Router và Filter

Transformer chuẩn hóa dữ liệu trước, giúp các pattern sau không phải lặp việc parse và canonicalize.

~~~mermaid
flowchart LR
    I["Raw order"] --> T["Transformer: normalize"]
    T --> F{"Filter: valid amount?"}
    F -->|Yes| R{"Router: region"}
    F -->|No| D["Reject channel"]
    R -->|NORTH| N["North process"]
    R -->|OTHER| O["Other process"]
~~~

Ví dụ, nếu vùng được nhập `" north "` hoặc `"NORTH"`, bước transform chuẩn hóa thành `"NORTH"`. Router so sánh một dạng duy nhất; nếu không có bước này, nhiều nhánh có thể tự cắt khoảng trắng và chuẩn hóa không đồng nhất.

### 9.2. Transformer với Splitter/Aggregator

Giả sử đơn hàng có nhiều dòng:

1. Splitter tách đơn thành `OrderLine` message riêng, thường gắn correlation/sequence metadata.
2. Transformer của mỗi dòng tính thuế hoặc chuyển sang `PricedLine`.
3. Aggregator gom các dòng dựa trên correlation/release strategy.

~~~mermaid
flowchart LR
    ORDER["Order with lines"] --> SPLIT["Splitter"]
    SPLIT --> LINE["OrderLine messages"]
    LINE --> T["Transformer: price each line"]
    T --> AGG["Aggregator"]
    AGG --> RESULT["PricedOrder"]
~~~

Nếu transformer trả **payload** `PricedLine`, headers tương quan/sequence thường được truyền theo mặc định. Nếu transformer trả **Message<PricedLine>** nhưng quên sao chép `correlationId`, `sequenceNumber` hoặc `sequenceSize`, Aggregator có thể nhóm sai hoặc không đủ điều kiện release.

Do đó, **fan-in là ca kiểm thử bắt buộc** khi đổi kiểu trả của transformer từ payload sang message.

### 9.3. Transformer với Gateway

Gateway gửi request vào flow và chờ reply theo cấu hình. Nếu Transformer là một bước trên đường phản hồi, việc bảo toàn các header điều khiển như `replyChannel`/`errorChannel` có thể quan trọng tùy cách output message được chuyển đi.

Các điểm cần kiểm tra:

- Có một output message hợp lệ hay không.
- Khi trả `Message`, đã mang theo metadata cần cho reply/error hay chưa.
- Có bị xóa header cần cho correlation của request–reply hay không.
- Nếu flow qua `ExecutorChannel` hoặc message broker, timeout và error flow có xử lý đúng không.

### 9.4. Transformer với retry và error channel

Biến đổi dữ liệu thuần túy, không có side effect, thường dễ retry. Khi transformer gọi database, HTTP hoặc ghi side effect, nó trở thành điểm có rủi ro lặp công việc. Hãy cân nhắc dời side effect sang Service Activator hoặc adapter phù hợp.

Exception trong handler đồng bộ có thể truyền về phía caller; trong flow bất đồng bộ, lỗi thường được chuyển qua error handling của channel/endpoint theo cấu hình. Mỗi tình huống cần được kiểm thử riêng; không kết luận rằng một `send()` trả `true` nghĩa là transformer và downstream đã hoàn tất trong mọi chế độ.

## 10. Kiến trúc mẫu: chuẩn hóa đơn hàng trước khi xử lý

Một flow đơn giản:

~~~text
orders.raw
   -> NormalizeOrderTransformer
orders.normalized
   -> Validate/Filter
orders.validated
   -> RegionRouter
orders.north / orders.other
   -> Service Activator
   -> orders.completed
~~~

Gợi ý hợp đồng dữ liệu theo từng chặng:

| Chặng | Payload | Headers cần bảo toàn |
|---|---|---|
| Inbound | `RawOrder` | `tenantId`, `traceId`, `businessCorrelationId` |
| Sau Transformer | `NormalizedOrder` | Giữ trace/correlation; có thể thêm `schemaVersion` |
| Sau Filter | `NormalizedOrder` | Vẫn giữ metadata cho router |
| Sau Router | `NormalizedOrder` | `tenantId`, `traceId` |
| Sau Service Activator | `CompletedOrder` | Correlation cho việc theo dõi/reply |

Nếu Transformer chỉ đổi payload, có thể trả `NormalizedOrder` để giữ header propagation mặc định. Nếu Transformer đánh dấu `schemaVersion=2`, trả `Message<NormalizedOrder>` hoặc tách thành Transformer + Header Enricher tùy hợp đồng thiết kế.

## 11. Kiểm thử Transformer qua channel thực

Kiểm thử trực tiếp phương thức biến đổi có ích cho business logic, nhưng chưa chứng minh **header propagation của Spring Integration endpoint**. Để kiểm tra điều đó, test nên gửi message qua input channel và đọc output channel.

### 11.1. Cấu hình hai Transformer để so sánh

Ví dụ Java 17+, JUnit Jupiter 5 và `spring-test`, sử dụng `@EnableIntegration` và `@SpringJUnitConfig`. Đây là một test class tự chứa với bean transformer được đăng ký trong Spring context.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Locale;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.Transformer;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = TransformerHeaderPropagationTest.Config.class)
class TransformerHeaderPropagationTest {

    @Configuration
    @EnableIntegration
    static class Config {

        @Bean("payloadInput")
        DirectChannel payloadInput() { return new DirectChannel(); }

        @Bean("payloadOutput")
        QueueChannel payloadOutput() { return new QueueChannel(); }

        @Bean("messageInput")
        DirectChannel messageInput() { return new DirectChannel(); }

        @Bean("messageOutput")
        QueueChannel messageOutput() { return new QueueChannel(); }

        @Bean
        SampleTransformers sampleTransformers() {
            return new SampleTransformers();
        }
    }

    public static class SampleTransformers {

        @Transformer(
                inputChannel = "payloadInput",
                outputChannel = "payloadOutput")
        public String returnPayload(String input) {
            return input.strip().toUpperCase(Locale.ROOT);
        }

        @Transformer(
                inputChannel = "messageInput",
                outputChannel = "messageOutput")
        public Message<String> returnMessage(Message<String> input) {
            return MessageBuilder
                    .withPayload(input.getPayload()
                            .strip().toUpperCase(Locale.ROOT))
                    .setHeader("schemaVersion", 2)
                    .build();
        }
    }

    @Autowired
    @Qualifier("payloadInput")
    MessageChannel payloadInput;

    @Autowired
    @Qualifier("payloadOutput")
    PollableChannel payloadOutput;

    @Autowired
    @Qualifier("messageInput")
    MessageChannel messageInput;

    @Autowired
    @Qualifier("messageOutput")
    PollableChannel messageOutput;

    @Test
    void payloadReturnPropagatesInboundHeader() {
        Message<String> input = MessageBuilder
                .withPayload("  order-1001  ")
                .setHeader("traceId", "trace-1001")
                .setHeader("tenantId", "shop-a")
                .build();

        assertTrue(payloadInput.send(input));

        Message<?> output = payloadOutput.receive(1000);
        assertNotNull(output);
        assertEquals("ORDER-1001", output.getPayload());
        assertEquals("trace-1001",
                output.getHeaders().get("traceId"));
        assertEquals("shop-a",
                output.getHeaders().get("tenantId"));
    }

    @Test
    void fullMessageReturnOwnsItsHeaders() {
        Message<String> input = MessageBuilder
                .withPayload("  order-1001  ")
                .setHeader("traceId", "trace-1001")
                .setHeader("tenantId", "shop-a")
                .build();

        assertTrue(messageInput.send(input));

        Message<?> output = messageOutput.receive(1000);
        assertNotNull(output);
        assertEquals("ORDER-1001", output.getPayload());
        assertEquals(2, output.getHeaders().get("schemaVersion"));
        assertNull(output.getHeaders().get("traceId"));
        assertNull(output.getHeaders().get("tenantId"));
    }
}
~~~

Hai test cho thấy điều xảy ra **qua framework**, khác với việc gọi trực tiếp `returnPayload(...)` hoặc `returnMessage(...)`. Test thứ hai cố ý không copy `traceId` để chỉ ra tác động của việc trả `Message` hoàn chỉnh. Ở hệ thống thực, cần sửa transformer để bảo toàn những headers bắt buộc.

Nếu ứng dụng đã khai báo các channel/bean trùng tên, hãy đổi tên test channels hoặc dùng test configuration độc lập.

### 11.2. Kiểm thử unit cho business logic

Một transformer tốt nên có business logic kiểm thử được ngoài Spring:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

class OrderNormalizationTest {

    @Test
    void normalizesValidRawOrder() {
        RawOrder input =
                new RawOrder("order-1001", "120.50", " north ");

        NormalizedOrder output = normalize(input);

        assertEquals("order-1001", output.orderId());
        assertEquals(new BigDecimal("120.50"), output.amount());
        assertEquals("NORTH", output.region());
    }

    // Ví dụ triển khai thuần Java cho test này:
    private NormalizedOrder normalize(RawOrder input) {
        return new NormalizedOrder(
                input.orderId().strip(),
                new BigDecimal(input.amountText()),
                input.regionText().strip().toUpperCase(
                        java.util.Locale.ROOT));
    }
}
~~~

Test logic thuần Java xác nhận output nghiệp vụ. Test channel ở mục 11.1 xác nhận hành vi infrastructure (tạo message, truyền headers).

### 11.3. Kiểm thử lỗi dữ liệu

Khi transformer parse số thất bại, test nên xác định:

1. Input sai định dạng được ghi nhận đúng là lỗi validation hay transformation.
2. Exception đi đến caller hoặc error channel theo topology thực tế.
3. Không có output “thành công” bị tạo khi transform lỗi.
4. Retry, nếu có, không chạy vô hạn trên lỗi dữ liệu cố định.
5. Trace/correlation ID vẫn xuất hiện trong log và báo lỗi theo chính sách dữ liệu.

Không assert rằng `timestamp` của hai message phải khác nhau tuyệt đối: message tạo trong cùng mili giây có thể có timestamp bằng nhau.

## 12. Các lỗi phổ biến khi chuyển payload hoặc message

### Lỗi 1 — Trả Message nhưng quên headers

~~~java
// Sai nếu downstream bắt buộc có traceId:
return MessageBuilder.withPayload(normalized).build();

// Đúng nếu muốn bảo toàn traceId:
return MessageBuilder.withPayload(normalized)
        .setHeader("traceId", input.getHeaders().get("traceId"))
        .build();
~~~

Các biến `normalized` và `input` nằm trong phạm vi method transformer của ứng dụng.

### Lỗi 2 — Dùng `return null` để loại message

Transformer yêu cầu đầu ra hợp lệ. Hãy dùng Filter với reject/discard flow hoặc ném exception có ý nghĩa để error handling xử lý.

### Lỗi 3 — Đổi payload nhưng giữ metadata cũ không phù hợp

Khi đổi từ JSON text sang DTO hoặc từ v1 sang v2, một số header mô tả định dạng có thể lỗi thời. Kiểm tra `contentType`, `schemaVersion` và headers custom; đừng sao chép mọi thứ vô điều kiện.

### Lỗi 4 — Đánh mất correlation của Splitter/Aggregator

Nếu message là một phần trong nhóm, cần giữ correlation/sequence đúng khi trả `Message`. Nếu không, Aggregator có thể xem các phần là nhóm khác hoặc không giải phóng kết quả.

### Lỗi 5 — Biến đổi object mutable “tại chỗ”

~~~java
// Không nên: sửa dữ liệu đầu vào đang được các consumer khác tham chiếu
input.getPayload().getItems().clear();
return input.getPayload();
~~~

Chọn DTO bất biến, tạo object mới hoặc defensive copy. Metadata `MessageHeaders` có cấu trúc read-only nhưng không tự khóa sâu toàn bộ object trong payload.

### Lỗi 6 — Trộn parsing, I/O và side effect trong một transformer

Khi một method vừa parse JSON vừa gọi HTTP vừa ghi DB vừa phát email, trách nhiệm khó kiểm thử và retry có thể lặp side effect. Tách normalization thuần dữ liệu vào Transformer, giao tiếp ngoài vào adapter/handler phù hợp.

### Lỗi 7 — Cho rằng Transformer tự bảo đảm transaction hoặc delivery

Transformer là một endpoint trong message flow. Nó không mặc định cung cấp message durability, exactly-once semantics hay transaction xuyên nhiều hệ thống. Những bảo đảm này phụ thuộc channel, adapter, broker, transaction manager và chính sách idempotency.

## 13. Bài thực hành: chuẩn hóa sự kiện đơn hàng

**Bối cảnh:** Ứng dụng nhận thông điệp:

~~~json
{
  "orderId": "order-1001",
  "amountText": "120.50",
  "regionText": " north "
}
~~~

Headers:

~~~text
tenantId: shop-a
traceId: trace-1001
businessCorrelationId: order-1001
schemaVersion: 1
~~~

**Yêu cầu triển khai theo từng bước:**

1. Tạo một `RawOrder` và `NormalizedOrder` như mục 4.1; xác định hợp đồng đầu ra.
2. Viết Transformer **A** trả `NormalizedOrder`: chuẩn hóa vùng, parse số tiền và từ chối giá trị âm.
3. Dùng `DirectChannel` input và `QueueChannel` output để kiểm tra payload đầu ra cùng `traceId`, `tenantId`, `businessCorrelationId`.
4. Viết Transformer **B** trả `Message<NormalizedOrder>`: tăng `schemaVersion` lên 2, chỉ giữ những headers nghiệp vụ được cho phép.
5. Thêm test chứng minh Transformer B **không tự copy** headers khi trả full Message.
6. Gắn Router phía sau, phân nhánh theo `region`. Bổ sung Filter để loại đơn không hợp lệ theo chính sách đã định.
7. Tình huống nâng cao: đặt Transformer sau Splitter rồi trước Aggregator; kiểm tra metadata correlation/sequence được giữ và nhóm được release đúng.
8. Thêm logging với `traceId` khi transform thất bại; kiểm chứng lỗi dữ liệu không bị retry vô hạn.

**Tiêu chí hoàn thành:** cả hai cách trả về đều có output đúng, quy tắc truyền header được kiểm tra qua flow thật, một input sai không tạo output thành công, và các nhánh router không phụ thuộc định dạng đầu vào chưa chuẩn hóa.

### Câu hỏi tự kiểm tra

1. Transformer trả `NormalizedOrder` và Transformer trả `Message<NormalizedOrder>` khác nhau ở bước tạo output message thế nào?
2. Vì sao việc nhận tham số `Message<RawOrder>` **không** quyết định header propagation?
3. Khi nào nên dùng Header Enricher thay vì trả full `Message` chỉ để thêm một header?
4. Transformer có nên trả `null` để bỏ message? Pattern nào phù hợp hơn?
5. Nếu Aggregator không gom đủ sau khi thay đổi Transformer, bạn sẽ kiểm tra những header nào trước?
6. Nếu input có `replyChannel`, việc tạo full `Message` thiếu header này có thể ảnh hưởng đến flow request–reply ra sao?
7. Tại sao `copyHeaders` không nên dùng vô điều kiện khi xuất dữ liệu sang hệ thống ngoài?
8. Làm thế nào phân biệt test business logic của Transformer với test header propagation của endpoint?

## 14. Checklist áp dụng trong dự án

- [ ] Đã mô tả input payload, output payload và phiên bản schema mong muốn.
- [ ] Chỉ chuyển đổi dữ liệu bằng Transformer; loại message qua Filter, định tuyến qua Router.
- [ ] Chọn có chủ đích kiểu trả **payload** hay **Message**.
- [ ] Nếu trả Message, xác định rõ danh sách header cần giữ, bỏ, sửa.
- [ ] Không suy rằng ID message mới là correlation key của cả nghiệp vụ.
- [ ] Trước Gateway/Aggregator, đã kiểm tra reply/error/correlation/sequence metadata.
- [ ] Kiểu dữ liệu header và payload bảo đảm an toàn khi chạy song song; không mutate input ngoài hợp đồng.
- [ ] Input không hợp lệ được xử lý rõ qua reject flow hoặc exception; không dùng `return null`.
- [ ] Các bước có side effect có retry/idempotency phù hợp; không retry vô hạn cho lỗi cố định.
- [ ] Kiểm thử qua channel thật để xác nhận header propagation và đường đi của lỗi.
- [ ] Log có correlation/trace cần thiết, không tiết lộ secret hoặc dữ liệu nhạy cảm.

## 15. Tổng kết

**Transformer chuyển payload hoặc message** là một quyết định thiết kế nhỏ nhưng tác động rộng tới toàn bộ flow. Nếu chỉ cần chuẩn hóa dữ liệu, **trả payload** giúp giữ logic gọn và tận dụng cơ chế truyền headers mặc định của Spring Integration. Nếu cần định nghĩa đầu ra cả về dữ liệu lẫn metadata, **trả `Message<?>`** giúp kiểm soát rõ ràng nhưng đòi hỏi chịu trách nhiệm đầy đủ với những headers downstream cần.

Trong các Enterprise Integration Patterns, hãy xem `traceId`, tenant, correlation và sequence như một phần **hợp đồng** giữa endpoint. Test không chỉ nội dung nghiệp vụ mà cả headers sau biến đổi, nhất là ở Gateway, Splitter/Aggregator, error channel và retry. Giữ Transformer dễ hiểu, ít side effect và làm rõ trường hợp lỗi sẽ giúp luồng thông điệp linh hoạt, dễ mở rộng và quan sát được.

### Tài liệu tham khảo

- Spring Integration Reference — **Transformer**: https://docs.spring.io/spring-integration/reference/transformer.html
- Spring Integration Reference — **Message / Header Propagation**: https://docs.spring.io/spring-integration/reference/message.html
- Spring Framework — **MessageBuilder API**: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageBuilder.html
- Spring Integration Reference — **Message Channel Implementations**: https://docs.spring.io/spring-integration/reference/channel/implementations.html

