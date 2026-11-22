# Filter theo payload

Trong **Spring Integration**, **Message Filter** là một endpoint thực hiện Enterprise Integration Pattern **Message Filter**: nó nhận một message, đánh giá một điều kiện (*predicate*) và quyết định **cho message đi tiếp** hoặc **từ chối message**. Khi **lọc theo payload**, điều kiện tập trung vào dữ liệu nghiệp vụ bên trong `Message.getPayload()`, chẳng hạn loại sự kiện, số tiền của đơn hàng, trạng thái thanh toán hoặc lựa chọn nhận thông báo của khách hàng.

Bài này thuộc chương **Filter** của module **SPRING_INTEGRATION_PATTERN**. Mục tiêu của module là triển khai Enterprise Integration Patterns với Spring Integration để tạo luồng thông điệp ít phụ thuộc, dễ mở rộng; thực hành Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation, đồng thời kiểm thử và quan sát các nhánh xử lý. Bài tập trung vào cách tạo predicate thuần, gắn predicate vào endpoint bằng `@Filter` hoặc Java DSL, xử lý message bị loại, bảo toàn headers và chứng minh hành vi bằng kiểm thử.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích sự khác nhau giữa **lọc theo payload**, lọc theo header và định tuyến message.
2. Thiết kế predicate có đầu vào và đầu ra rõ ràng, không có side effect, dễ kiểm thử độc lập với Spring.
3. Dùng `@Filter` và Java DSL `IntegrationFlow.filter(...)` để lọc các đối tượng payload có kiểu.
4. Hiểu chính xác hai nhánh của Filter: **accepted** và **rejected**.
5. Cấu hình `discardChannel` và giải thích lựa chọn báo lỗi bằng `throwExceptionOnRejection`.
6. Phân biệt kết quả `false` với exception phát sinh trong quá trình tính predicate.
7. Chứng minh message được giữ nguyên payload/header trên đường accepted/rejected và không bị xử lý nhầm ở downstream.
8. Viết unit test cho predicate và integration test với `DirectChannel` / `QueueChannel`.
9. Kết hợp Filter với Transformer, Router, Publish–Subscribe, Splitter/Aggregator, Gateway, retry và error channel.
10. Nhận diện rủi ro bảo mật, tính bất biến, hiệu năng và khả năng quan sát của lọc theo payload.

## 2. Filter theo payload hoạt động như thế nào?

Một message có thể được mô tả bằng:

~~~text
Message<OrderEvent>
  payload:
    eventId = "evt-1001"
    orderId = "order-1001"
    kind = CREATED
    amount = 750.00
    customerOptIn = true
  headers:
    traceId = "trace-1001"
    businessCorrelationId = "order-1001"
~~~

Giả sử nhánh gửi thông báo chỉ xử lý những sự kiện thỏa **tất cả** điều kiện:

- Loại sự kiện là `CREATED`.
- Khách hàng đã đồng ý nhận thông báo (`customerOptIn=true`).
- Tổng giá trị đơn hàng **từ 100.00 trở lên**.

Filter đánh giá payload và chọn:

~~~mermaid
flowchart LR
    P["Producer: OrderEvent"] --> C["orders.events"]
    C --> F{"Payload Filter"}
    F -->|"true: đủ điều kiện"| A["orders.notify"]
    F -->|"false: không phù hợp"| D["orders.skipped"]
    A --> H["Notification handler"]
    D --> M["Skip metrics / audit"]
~~~

**Filter không biến đổi payload.** Nếu message được chấp nhận, message đi tới output channel để handler kế tiếp xử lý. Nếu không đạt, message có thể đi tới discard channel hoặc bị loại theo cấu hình. Cấu trúc payload/header không trở thành một object khác chỉ vì predicate trả `true` hay `false`.

### 2.1. Filter trả lời một câu hỏi duy nhất

> **Message này có được phép tiếp tục đi theo nhánh này không?**

Predicate của Filter nên cho một quyết định rõ ràng: `true` hoặc `false`. Nếu phải chọn giữa `orders.priority`, `orders.review` và `orders.standard`, đó là bài toán **Router**, không phải cố viết nhiều Filter nối nhau một cách khó theo dõi.

### 2.2. So sánh các thành phần

| Thành phần | Trách nhiệm | Kết quả điển hình |
|---|---|---|
| **Filter** | Quyết định accept/reject một message | Message gốc đi tiếp hoặc bị loại |
| **Transformer** | Đổi biểu diễn payload/message | Payload mới hoặc `Message<?>` mới |
| **Router** | Chọn kênh đích theo nội dung/metadata | Một hoặc nhiều kênh theo thiết kế |
| **Header Enricher** | Bổ sung/tính lại metadata | Message với header được cập nhật |
| **Splitter** | Tách message thành nhiều phần | Nhiều message con |
| **Aggregator** | Ghép các message liên quan | Một kết quả tổng hợp |
| **Service Activator** | Gọi logic/side effect ứng dụng | Có thể tạo reply hoặc xử lý một chiều |

Không nên dùng Transformer trả `null` thay Filter; trong Spring Integration, Transformer trả null được xem là một tình huống lỗi transformation, không phải cách loại message theo chủ đích.

## 3. Thiết kế hợp đồng payload trước khi lọc

Filter nên hoạt động với một **kiểu payload xác định**, sau khi inbound adapter hoặc decoder đã giải mã và validation những trường tối thiểu.

Ví dụ Java 17+:

~~~java
import java.math.BigDecimal;
import java.util.Objects;

public enum OrderEventKind {
    CREATED,
    PAID,
    CANCELLED
}

public record OrderEvent(
        String eventId,
        String orderId,
        OrderEventKind kind,
        BigDecimal amount,
        boolean customerOptIn
) {
    public OrderEvent {
        if (eventId == null || eventId.isBlank()) {
            throw new IllegalArgumentException(
                    "eventId must not be blank");
        }
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException(
                    "orderId must not be blank");
        }
        Objects.requireNonNull(kind, "kind");
        Objects.requireNonNull(amount, "amount");
        if (amount.signum() < 0) {
            throw new IllegalArgumentException(
                    "amount must be non-negative");
        }
    }
}
~~~

`record` không có setter, các field trong ví dụ là giá trị bất biến. Trong project thật, các kiểu trên thường nằm trong **hai source file riêng**, hoặc đặt enum theo quy tắc visibility/package phù hợp của Java. Bài viết trình bày chúng cùng nhau để dễ đọc.

**Phân biệt hai tầng trách nhiệm:**

- **Validation:** đảm bảo payload có dữ liệu hợp lệ để hệ thống xử lý, ví dụ `eventId` không rỗng và `amount >= 0`.
- **Filtering:** payload có hợp lệ nhưng có **thuộc đối tượng mục tiêu của nhánh** hay không, ví dụ người dùng có opt-in và sự kiện là CREATED.

Một event `CANCELLED` hợp lệ không phải là lỗi; chỉ là nó không cần đi qua nhánh gửi thông báo tạo đơn.

### 3.1. Vì sao nên tránh lọc trực tiếp JSON string?

Nếu Filter có đoạn:

~~~java
// Anti-pattern: dễ phụ thuộc vào format chuỗi.
boolean accepted = json.contains("\"customerOptIn\":true");
~~~

thì chỉ cần thay khoảng trắng, thứ tự field hoặc encoding là kết quả có thể sai. Nên để JSON decoder/converter tạo `OrderEvent` có kiểu, validate schema rồi lọc theo thuộc tính. Khi nguồn dữ liệu không đáng tin cậy, nhớ giới hạn kích thước và cấu trúc ở adapter trước khi parse.

## 4. Viết predicate thuần để dễ kiểm thử

Một thiết kế tốt tách **chính sách chọn message** khỏi hạ tầng message channel. Predicate có dạng:

~~~text
boolean shouldNotify(OrderEvent event)
~~~

Không gọi DB, HTTP, email hoặc clock; cùng `OrderEvent` thì cho cùng kết quả.

~~~java
import java.math.BigDecimal;
import java.util.Objects;

public final class OrderNotificationPolicy {

    private static final BigDecimal MIN_AMOUNT =
            new BigDecimal("100.00");

    public boolean shouldNotify(OrderEvent event) {
        Objects.requireNonNull(event, "event");

        return event.kind() == OrderEventKind.CREATED
                && event.customerOptIn()
                && event.amount().compareTo(MIN_AMOUNT) >= 0;
    }
}
~~~

Predicate vừa đủ ngắn để code review và kiểm thử trực tiếp. Những ngưỡng lớn hơn trong production nên được định nghĩa qua immutable configuration có version, nếu yêu cầu replay phải tái hiện quyết định lịch sử.

### 4.1. Tại sao dùng BigDecimal.compareTo?

`BigDecimal.equals` xét cả scale: `new BigDecimal("100.0")` và `new BigDecimal("100.00")` có giá trị số bằng nhau nhưng `equals` trả `false`. Đối với điều kiện “ít nhất 100”, `compareTo(...) >= 0` phản ánh đúng thứ tự số.

### 4.2. Bảng quyết định

| Kind | Opt-in | Amount | Kết quả | Lý do |
|---|---|---:|---|---|
| CREATED | true | 750.00 | Accept | Đủ điều kiện |
| CREATED | true | 100.00 | Accept | Đúng ngưỡng |
| CREATED | true | 99.99 | Reject | Dưới ngưỡng |
| CREATED | false | 200.00 | Reject | Khách không opt-in |
| PAID | true | 500.00 | Reject | Không phải loại event yêu cầu |
| CANCELLED | true | 800.00 | Reject | Không gửi thông báo tạo đơn |
| CREATED | true | 100.0 | Accept | So sánh giá trị số, không so scale |

Bảng này là hợp đồng nghiệp vụ có thể biến thành `@ParameterizedTest`. Các giá trị âm không xuất hiện trong bảng vì `OrderEvent` từ chối từ constructor; đó là **lỗi dữ liệu**, không phải nhánh reject bình thường của Filter.

### 4.3. Những dấu hiệu predicate không còn thuần

~~~java
// Không nên nhét trực tiếp vào filter:
boolean accept(OrderEvent event) {
    boolean allowed = customerApi.isSubscribed(event.orderId());
    emailService.sendConfirmation(event.orderId());
    return allowed && LocalDate.now().getDayOfWeek()
            != DayOfWeek.SUNDAY;
}
~~~

Vấn đề:

- API timeout làm bộ lọc lỗi, nhưng không hẳn message phải bị reject.
- Việc gửi email diễn ra **trước** khi Filter quyết định.
- Retry có thể gửi email nhiều lần.
- Kết quả tùy thời gian tại máy chạy và trạng thái ngoài.
- Unit test phải mock nhiều dependency không thuộc bản chất Filter.

Thay vào đó, lấy thông tin cần thiết qua một **enrichment endpoint** có retry/timeout riêng, tạo snapshot đáng tin cậy rồi áp dụng predicate thuần. Side effect chỉ xảy ra **sau nhánh accepted** tại handler chuyên trách.

## 5. Lọc payload với annotation @Filter

Spring Integration hỗ trợ annotation `org.springframework.integration.annotation.Filter`. Ta dùng adapter mỏng gọi policy:

~~~java
import org.springframework.integration.annotation.Filter;

public final class OrderNotificationFilter {

    private final OrderNotificationPolicy policy;

    public OrderNotificationFilter(OrderNotificationPolicy policy) {
        this.policy = policy;
    }

    @Filter(
            inputChannel = "orders.events",
            outputChannel = "orders.notify",
            discardChannel = "orders.skipped")
    public boolean accept(OrderEvent event) {
        return policy.shouldNotify(event);
    }
}
~~~

Giải thích:

- `inputChannel` là nơi endpoint nhận message.
- Tham số `OrderEvent event` được bind từ **payload** theo cơ chế method invocation của Spring Integration.
- Method trả `boolean`; framework dùng kết quả làm quyết định Filter.
- `true`: message được chuyển đến `orders.notify`.
- `false`: message được chuyển đến `orders.skipped` nhờ `discardChannel`.
- `@Filter` không tự tạo một `OrderEvent` hay `Message` khác để gửi tiếp.

**Quan trọng:** class phải được đăng ký thành Spring bean và hạ tầng Spring Integration annotation được bật. Chỉ thêm annotation lên object tạo bằng `new` ngoài Spring không đủ để có endpoint nhận message.

### 5.1. Cấu hình channel và bean

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class OrderFilterConfiguration {

    @Bean(name = "orders.events")
    public MessageChannel input() {
        return new DirectChannel();
    }

    @Bean(name = "orders.notify")
    public PollableChannel accepted() {
        return new QueueChannel();
    }

    @Bean(name = "orders.skipped")
    public PollableChannel rejected() {
        return new QueueChannel();
    }

    @Bean
    public OrderNotificationPolicy notificationPolicy() {
        return new OrderNotificationPolicy();
    }

    @Bean
    public OrderNotificationFilter notificationFilter(
            OrderNotificationPolicy policy) {
        return new OrderNotificationFilter(policy);
    }
}
~~~

`DirectChannel` giúp lời gọi xử lý trong một thread cho ví dụ kiểm thử. Hai `QueueChannel` để **quan sát đầu ra trong test**; đây là channel in-memory, không phải nơi lưu trữ bền vững qua restart. Trong ứng dụng thật, `orders.notify` thường nối tới một Service Activator, còn `orders.skipped` có thể nối tới metrics/audit handler.

### 5.2. Gửi message có header

~~~java
import java.math.BigDecimal;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

void publish(MessageChannel input) {
    OrderEvent event = new OrderEvent(
            "evt-1001",
            "order-1001",
            OrderEventKind.CREATED,
            new BigDecimal("750.00"),
            true);

    Message<OrderEvent> message = MessageBuilder
            .withPayload(event)
            .setHeader("traceId", "trace-1001")
            .setHeader("businessCorrelationId", "order-1001")
            .build();

    input.send(message);
}
~~~

Message trên sẽ đi tới `orders.notify` nếu không có lỗi cấu hình. Những header quan trọng vẫn gắn với message được Filter chuyển tiếp. `send()==true` ở tầng channel **không** là bằng chứng notification đã gửi thành công ở một handler downstream, nhất là khi có xử lý bất đồng bộ.

## 6. Lọc theo payload bằng Java DSL

Spring Integration Java DSL cho phép khai báo flow ngay trong cấu hình:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
public class OrderNotificationDslConfiguration {

    @Bean
    public IntegrationFlow notificationFilterFlow(
            OrderNotificationPolicy policy) {

        return IntegrationFlow.from("orders.dsl.input")
                .filter(OrderEvent.class,
                        event -> policy.shouldNotify(event),
                        spec -> spec.discardChannel("orders.dsl.skipped"))
                .channel("orders.dsl.notify")
                .get();
    }
}
~~~

Ở đây, `filter(OrderEvent.class, ...)` ràng buộc predicate với **kiểu payload**, thay vì phải nhận `Message<?>` rồi ép kiểu thủ công. Nếu predicate trả `true`, message đi tiếp tới `orders.dsl.notify`; nếu `false`, message đi tới `orders.dsl.skipped`. Cần khai báo các channel hoặc để Java DSL tạo các channel thích hợp theo cách được dự án cấu hình; khi kiểm thử, nên khai báo rõ tên bean cho cả ba channel.

**Đây là phương án thay thế** cho cấu hình `@Filter` ở mục 5, không nên đăng ký hai filter cạnh tranh trên cùng `DirectChannel` nếu ý định là một tuyến duy nhất.

### 6.1. Predicate đơn giản viết ngay tại DSL

~~~java
@Bean
IntegrationFlow paidEventFlow() {
    return IntegrationFlow.from("payment.events")
            .filter(OrderEvent.class,
                    event -> event.kind() == OrderEventKind.PAID)
            .channel("payment.paidOnly")
            .get();
}
~~~

Ví dụ này có chủ đích **không khai báo discard channel**: sự kiện không phải PAID bị loại khỏi nhánh này theo cấu hình mặc định. Chỉ dùng kiểu lọc âm thầm khi đó là hành vi đã được chấp nhận trong hợp đồng. Nếu producer cần biết lý do message không được xử lý, nên cấu hình nhánh reject hoặc phản hồi có ý nghĩa.

### 6.2. Khi nào nên tách predicate thành bean?

Nên dùng bean riêng khi:

- Có hơn một điều kiện.
- Quy tắc cần dùng ở nhiều flow.
- Có bảng quyết định và nhiều test.
- Cần quản lý phiên bản rules.
- Muốn chạy unit test mà không khởi động Spring context.

Không cần tạo một service nhiều lớp cho điều kiện quá đơn giản như `kind == PAID`; tính rõ ràng quan trọng hơn số lớp code.

## 7. Nhánh accepted và rejected

Đây là trung tâm của Message Filter. Điều kiện không phải lúc nào cũng đưa tới một đường lỗi.

### 7.1. Accepted: message đi tiếp

Predicate trả `true` thì Filter chuyển message tới output channel. Nó không tự sửa business payload. Trong thiết kế thông thường, các headers `traceId`, `businessCorrelationId` và `tenantId` tiếp tục đi cùng message.

~~~mermaid
flowchart LR
    I["Input Message<OrderEvent>"] --> F{"Filter"}
    F -->|"true"| A["Accepted: Message<OrderEvent>"]
    A --> H["Notification handler"]
~~~

Filter **không kiểm tra** rằng Notification đã thực sự gửi email hoặc side effect thành công. Để theo dõi kết quả nghiệp vụ, cần metric/ack/reply ở handler downstream.

### 7.2. Rejected: discard channel hoặc bỏ message

Predicate trả `false` thì mặc định message có thể bị **bỏ khỏi tuyến chính**. Nếu `discardChannel` được khai báo, Filter chuyển message bị từ chối tới channel đó:

~~~java
@Filter(
        inputChannel = "orders.events",
        outputChannel = "orders.notify",
        discardChannel = "orders.skipped")
public boolean accept(OrderEvent event) {
    return policy.shouldNotify(event);
}
~~~

`orders.skipped` **không phải tự động là errorChannel hoặc dead-letter queue**. Nó chỉ là một channel được cấu hình; bạn phải gắn handler, audit hoặc adapter phù hợp nếu muốn xử lý nhánh reject lâu dài.

### 7.3. Rejected không có nghĩa exception

Có hai trường hợp khác nhau:

~~~java
// Một quyết định lọc bình thường:
return false;

// Một sự cố khi tính điều kiện:
throw new IllegalStateException("Subscriber lookup unavailable");
~~~

Trường hợp đầu là **rejection theo chính sách**. Trường hợp sau là **lỗi thực thi**, có thể nổi về sender trong luồng đồng bộ hoặc đi theo cơ chế error handling bất đồng bộ tùy topology.

Nếu business yêu cầu biến một rejection thành exception, Spring Integration hỗ trợ cấu hình `throwExceptionOnRejection`. Với cấu hình này, rejection có thể gây `MessageRejectedException`. Cần kiểm thử chính xác tương tác giữa cấu hình exception và `discardChannel` trên phiên bản đang sử dụng để tránh xử lý cùng một message như hai lỗi độc lập.

**Không đặt retry vô hạn cho predicate trả `false`.** Lọc một message không phù hợp là quyết định bình thường, không phải lỗi hạ tầng cần thử lại.

## 8. Phân biệt Filter với kiểm tra hợp lệ (validation)

Một sai lầm phổ biến là dùng Filter để "nuốt" tất cả input sai. Ví dụ:

~~~text
JSON lỗi cú pháp
  -> lỗi decoder / adapter

OrderEvent thiếu eventId hoặc amount âm
  -> lỗi schema/validation

OrderEvent hợp lệ nhưng kind=CANCELLED
  -> Filter của nhánh gửi notification trả false
~~~

Ba tình huống có ý nghĩa khác nhau.

| Tình huống | Ý nghĩa | Hướng xử lý gợi ý |
|---|---|---|
| JSON không parse được | Input không đúng định dạng | Trả lỗi decode hoặc error flow |
| Thiếu trường bắt buộc | Vi phạm hợp đồng dữ liệu | Validation/reject có lý do |
| Không có quyền theo tenant | Vi phạm authorization | Từ chối từ trust boundary |
| `kind=CANCELLED` | Event hợp lệ nhưng không thuộc nhánh notification | Filter trả `false` |
| `customerOptIn=false` | Event hợp lệ nhưng không được gửi notification | Filter trả `false` |
| Gọi API customer profile bị timeout | Lỗi tạm thời ở bước enrichment | Retry có giới hạn/error flow |
| Notification API bị 503 | Lỗi handler phía sau | Retry/idempotency downstream |

Đặt validation gần ingress giúp các bước sau nhận một `OrderEvent` hợp lệ. Khi đó predicate có thể giả định `amount` đã không âm, `kind` tồn tại và không cần trộn quá nhiều lệnh kiểm tra hợp đồng trong từng nhánh.

### 8.1. Filter không phải biện pháp bảo mật duy nhất

Một payload có thể chứa `isAdmin=true` hoặc `tenantId="shop-a"`, nhưng nó không chứng minh caller có quyền. Authorization cần dùng principal/context đáng tin cậy ở ranh giới security. Lọc theo payload có thể được dùng **sau** khi thông tin quyền được xác thực, nhưng không thay thế xác thực và kiểm soát truy cập.

## 9. Kiểu payload ảnh hưởng thế nào đến Filter?

### 9.1. Payload là String

~~~java
import org.springframework.integration.annotation.Filter;

@Filter(
        inputChannel = "text.input",
        outputChannel = "text.nonBlank")
public boolean nonBlank(String text) {
    return !text.isBlank();
}
~~~

Điều kiện đơn giản này loại các chuỗi rỗng/toàn khoảng trắng. Nó không thay đổi text; ví dụ `"  OK  "` được chấp nhận với khoảng trắng còn nguyên. Nếu muốn trim, dùng Transformer trước hoặc sau Filter theo contract.

### 9.2. Payload là DTO/record

~~~java
@Filter(
        inputChannel = "orders.events",
        outputChannel = "orders.highValue")
public boolean highValue(OrderEvent event) {
    return event.amount().compareTo(
            new java.math.BigDecimal("1000.00")) >= 0;
}
~~~

Đây là điều kiện giá trị đơn hàng; nó không đồng nghĩa đơn đã thanh toán hoặc khách được quyền hưởng ưu đãi. Hãy diễn giải đúng ý nghĩa nghiệp vụ.

### 9.3. Payload là một collection

~~~java
import java.util.List;

@Filter(
        inputChannel = "batches.input",
        outputChannel = "batches.nonEmpty")
public boolean hasElements(List<?> items) {
    return !items.isEmpty();
}
~~~

Một Filter ở cấp batch chấp nhận/loại **cả message mang List**, không lọc từng phần tử trong List. Nếu muốn bỏ những phần tử riêng lẻ, có thể dùng Transformer tạo collection mới hoặc Splitter → Filter từng item → Aggregator, tùy ngữ nghĩa của quy trình.

### 9.4. Payload là Map động

~~~java
@Filter(
        inputChannel = "legacy.input",
        outputChannel = "legacy.active")
public boolean isActive(java.util.Map<String, Object> value) {
    return Boolean.TRUE.equals(value.get("active"));
}
~~~

Lọc trực tiếp `Map` hữu ích khi tích hợp legacy nhưng yếu về type safety: `"true"` dạng chuỗi không giống `Boolean.TRUE`. Với payload phức tạp, nên decode/validate thành DTO trước để giảm lỗi ép kiểu và ràng buộc dữ liệu.

### 9.5. Payload sai kiểu không nhất thiết thành reject

Nếu endpoint được khai báo cho `OrderEvent` nhưng producer gửi một kiểu khác, framework có thể không bind/convert được tham số và gây exception. Không được mặc nhiên coi đó là `false` để đưa sang discard channel. Cần kiểm tra converter, validation và error handling của inbound adapter.

## 10. Thứ tự Filter và Transformer

Không có một thứ tự đúng cho mọi trường hợp. Quyết định phụ thuộc cách dữ liệu được chuẩn hóa và ý nghĩa của điều kiện.

### 10.1. Filter trước Transformer

~~~mermaid
flowchart LR
    IN["OrderEvent đã decode"] --> F{"Filter: cần notification?"}
    F -->|Yes| T["Transformer: tạo email request"]
    T --> OUT["Email adapter"]
    F -->|No| SKIP["Skip"]
~~~

Ưu điểm: chỉ các message có khả năng được xử lý mới tốn chi phí tạo template, gọi enrichment hoặc chuẩn bị email. Phù hợp khi predicate dùng các trường đơn giản đã hợp lệ.

### 10.2. Transformer trước Filter

~~~mermaid
flowchart LR
    IN["RawOrder"] --> T["Transformer: normalize"]
    T --> F{"Filter: điều kiện trên NormalizedOrder"}
    F -->|Yes| OUT["Downstream"]
    F -->|No| SKIP["Discard"]
~~~

Phù hợp khi điều kiện phụ thuộc dữ liệu **đã chuẩn hóa**, ví dụ region `" north "` phải được coi là `"NORTH"`, hoặc giá tiền đến dưới dạng chuỗi và cần parse trước khi so sánh.

### 10.3. Đừng làm mất header khi tạo message mới

Transformer trả **payload** thường để Spring Integration tạo message mới và truyền headers đầu vào theo quy tắc framework. Transformer trả **`Message<?>` hoàn chỉnh** cần chủ động bảo toàn metadata cần thiết. Nếu sau biến đổi mất `traceId` hoặc correlation, Filter vẫn có thể quyết định đúng nhưng downstream mất khả năng truy vết.

## 11. Filter với Router và Publish–Subscribe

### 11.1. Filter trước Router

~~~mermaid
flowchart LR
    IN["Input"] --> F{"Filter: eligible?"}
    F -->|Yes| R{"Router: region"}
    R --> N["NORTH"]
    R --> S["SOUTH"]
    F -->|No| D["Discard"]
~~~

Filter giảm số message phải định tuyến, còn Router chọn **đích xử lý** cho message được chấp nhận.

### 11.2. Filter trong một nhánh Publish–Subscribe

~~~mermaid
flowchart TB
    IN["OrderEvent"] --> PUB(("PublishSubscribeChannel"))
    PUB --> AUD["Audit subscriber"]
    PUB --> NTF{"Notification Filter"}
    PUB --> ANA["Analytics subscriber"]
    NTF -->|Yes| EMAIL["Email sender"]
    NTF -->|No| SKIP["No notification"]
~~~

Ở đây, một Filter trả `false` trong nhánh notification **không mặc nhiên loại message khỏi các subscriber Audit/Analytics**. Mỗi nhánh có trách nhiệm riêng; nếu muốn loại message ngay trước khi fan-out, đặt Filter **upstream** của `PublishSubscribeChannel`.

### 11.3. Filter sau Splitter, trước Aggregator

Sau Splitter, có thể lọc từng phần tử. Nhưng Aggregator thường dùng `correlationId`, `sequenceNumber` và `sequenceSize` để biết khi nào nhóm đủ.

Nếu Splitter tạo 5 phần và Filter loại 2 phần, Aggregator có thể vẫn đang chờ 5 phần theo release strategy mặc định. Cần chọn chiến lược release, timeout hoặc biểu diễn kết quả bị loại một cách tường minh. **Không chỉ thêm Filter rồi giả định Aggregator tự biết còn 3 phần.**

## 12. Filter trong luồng đồng bộ và bất đồng bộ

Trong topology đồng bộ với `DirectChannel`, một lời gọi `send()` có thể chạy filter ngay trên thread producer. Nếu predicate ném exception, lỗi có thể quay về sender. Khi dùng `ExecutorChannel` hoặc message-driven inbound adapter bất đồng bộ, việc tính predicate diễn ra trên thread xử lý; exception có thể đi qua `errorChannel`/error handling tùy cấu hình.

| Hành vi | Đồng bộ | Bất đồng bộ |
|---|---|---|
| Predicate trả `true` | Message chuyển tiếp trong cùng chuỗi xử lý | Có thể được chuyển tiếp trên worker thread |
| Predicate trả `false` | Discard/reject theo cấu hình | Discard/reject theo cấu hình |
| Predicate ném exception | Có thể nổi về sender | Thường đi qua error handling của worker |
| `send()==true` | Không là bằng chứng toàn bộ nghiệp vụ thành công | Có thể trả trước khi downstream hoàn tất |
| Thứ tự xử lý | Theo topology đồng bộ | Cần xem xét concurrency và ordering |
| Retry | Do advice/adapter/flow cấu hình | Do cơ chế retry và error handling của worker/consumer |

Một predicate thuần, không side effect sẽ dễ retry và tái hiện hơn. Nhưng **retry toàn message** sau lỗi downstream có thể làm những handler upstream chạy lại; các side effect cần idempotency riêng.

## 13. Kiểm thử predicate bằng JUnit 5

Unit test nên bắt đầu ở lớp policy **không phụ thuộc Spring context**.

### 13.1. Parameterized tests cho bảng quyết định

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;
import java.util.stream.Stream;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

class OrderNotificationPolicyTest {

    private final OrderNotificationPolicy policy =
            new OrderNotificationPolicy();

    static Stream<Arguments> cases() {
        return Stream.of(
                Arguments.of(OrderEventKind.CREATED, true,
                        "750.00", true),
                Arguments.of(OrderEventKind.CREATED, true,
                        "100.00", true),
                Arguments.of(OrderEventKind.CREATED, true,
                        "99.99", false),
                Arguments.of(OrderEventKind.CREATED, false,
                        "200.00", false),
                Arguments.of(OrderEventKind.PAID, true,
                        "500.00", false),
                Arguments.of(OrderEventKind.CANCELLED, true,
                        "800.00", false),
                Arguments.of(OrderEventKind.CREATED, true,
                        "100.0", true));
    }

    @ParameterizedTest
    @MethodSource("cases")
    void filtersPayloadAsExpected(
            OrderEventKind kind,
            boolean optIn,
            String amount,
            boolean expected) {

        OrderEvent event = new OrderEvent(
                "evt-1001", "order-1001",
                kind, new BigDecimal(amount), optIn);

        assertEquals(expected, policy.shouldNotify(event));
    }
}
~~~

Test này kiểm chứng chính xác hợp đồng ngưỡng, opt-in và event kind. Bởi method không đọc Spring context, test chạy nhanh và có thể mở rộng thêm hàng chục trường hợp.

### 13.2. Kiểm thử dữ liệu không hợp lệ riêng biệt

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

class OrderEventContractTest {

    @Test
    void negativeAmountIsInvalidPayload() {
        assertThrows(IllegalArgumentException.class,
                () -> new OrderEvent(
                        "evt-1002", "order-1002",
                        OrderEventKind.CREATED,
                        new BigDecimal("-1.00"),
                        true));
    }

    @Test
    void missingOrderIdIsInvalidPayload() {
        assertThrows(IllegalArgumentException.class,
                () -> new OrderEvent(
                        "evt-1003", "  ",
                        OrderEventKind.CREATED,
                        new BigDecimal("150.00"),
                        true));
    }
}
~~~

Hai test này xác nhận **invariant của payload**, không phải việc Filter từ chối một event hợp lệ. Đặt đúng test ở đúng tầng sẽ giúp phân tích lỗi rõ hơn.

### 13.3. Kiểm thử tính tất định

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

class NotificationDeterminismTest {

    @Test
    void samePayloadAlwaysProducesSameDecision() {
        OrderNotificationPolicy policy =
                new OrderNotificationPolicy();

        OrderEvent event = new OrderEvent(
                "evt-1", "order-1",
                OrderEventKind.CREATED,
                new BigDecimal("250.00"),
                true);

        boolean first = policy.shouldNotify(event);
        for (int i = 0; i < 100; i++) {
            assertEquals(first, policy.shouldNotify(event));
        }
    }
}
~~~

Đây là smoke test, không thay thế review rằng method không có side effect, phụ thuộc thời gian hoặc trạng thái mutable.

## 14. Kiểm thử tích hợp Filter qua channel thực

Để xác nhận `@Filter` đã được Spring đăng ký và các output channel đúng tên, cần một test gửi **Message<OrderEvent>** qua input channel rồi đọc đúng nhánh.

Ví dụ Java 17+, JUnit Jupiter 5, Spring Test và Spring Integration:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = OrderFilterConfiguration.class)
class OrderFilterFlowTest {

    @Autowired
    @Qualifier("orders.events")
    MessageChannel input;

    @Autowired
    @Qualifier("orders.notify")
    PollableChannel accepted;

    @Autowired
    @Qualifier("orders.skipped")
    PollableChannel rejected;

    @Test
    void eligibleEventGoesOnlyToNotifyChannel() {
        OrderEvent event = new OrderEvent(
                "evt-1001", "order-1001",
                OrderEventKind.CREATED,
                new BigDecimal("500.00"),
                true);

        Message<OrderEvent> message = MessageBuilder
                .withPayload(event)
                .setHeader("traceId", "trace-1001")
                .setHeader("businessCorrelationId", "order-1001")
                .build();

        assertTrue(input.send(message));

        Message<?> output = accepted.receive(1000);

        assertNotNull(output);
        assertEquals(event, output.getPayload());
        assertEquals("trace-1001",
                output.getHeaders().get("traceId"));
        assertEquals("order-1001",
                output.getHeaders().get("businessCorrelationId"));

        assertNull(rejected.receive(0));
    }

    @Test
    void nonEligibleEventGoesOnlyToDiscardChannel() {
        OrderEvent event = new OrderEvent(
                "evt-1002", "order-1002",
                OrderEventKind.CREATED,
                new BigDecimal("200.00"),
                false);

        Message<OrderEvent> message = MessageBuilder
                .withPayload(event)
                .setHeader("traceId", "trace-1002")
                .build();

        assertTrue(input.send(message));

        Message<?> discarded = rejected.receive(1000);

        assertNotNull(discarded);
        assertEquals(event, discarded.getPayload());
        assertEquals("trace-1002",
                discarded.getHeaders().get("traceId"));

        assertNull(accepted.receive(0));
    }

    @Test
    void paidEventDoesNotReachNotification() {
        OrderEvent event = new OrderEvent(
                "evt-1003", "order-1003",
                OrderEventKind.PAID,
                new BigDecimal("1000.00"),
                true);

        assertTrue(input.send(
                MessageBuilder.withPayload(event).build()));

        assertNotNull(rejected.receive(1000));
        assertNull(accepted.receive(0));
    }
}
~~~

Điểm test này chứng minh:

- `@Filter` thực sự được kích hoạt bởi message trên `orders.events`.
- Payload đạt điều kiện đi tới `orders.notify`.
- Payload không đạt điều kiện đi tới `orders.skipped`, **không** lọt nhánh notification.
- Headers phục vụ correlation/tracing vẫn đi theo message được chuyển tiếp.
- Trường hợp event kind khác được xử lý đúng dù số tiền đủ ngưỡng.

**Lưu ý:** các test có thể dùng cùng cached Spring test context. Mỗi test ở trên lấy hết message mà chính nó gửi, nhưng với suite lớn hoặc chạy song song, nên tạo fixture/context cô lập, hoặc dọn queue một cách có kiểm soát để không bị ảnh hưởng bởi test khác.

### 14.1. Kiểm thử không có side effect sau rejected

Nếu `orders.notify` nối tới một NotificationService thật, điều quan trọng nhất là chứng minh **message rejected không gọi sender**. Có thể dùng fake sender có `AtomicInteger` hoặc Mockito mock thay cho adapter:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

class FakeNotificationSender {
    private final AtomicInteger deliveries = new AtomicInteger();

    void deliver(OrderEvent event) {
        deliveries.incrementAndGet();
    }

    int deliveryCount() {
        return deliveries.get();
    }
}
~~~

Ở integration test mở rộng, gắn fake sender vào accepted channel qua `@ServiceActivator`, gửi event có opt-in false, assert `deliveryCount()==0`. Không cần gửi email thực để chứng minh semantics của Filter.

### 14.2. Unit test và integration test bổ sung cho nhau

| Unit test policy | Integration test channel |
|---|---|
| Kiểm tra logic domain | Kiểm tra wiring Spring Integration |
| Không cần Spring context | Cần context + endpoint/channel |
| Nhanh, dễ phủ nhiều edge cases | Bắt được sai tên channel hoặc bean |
| Không chứng minh headers được truyền | Quan sát message sau Filter |
| Không biết discardChannel có tồn tại | Xác minh accept/reject đến đúng nơi |

## 15. Bảo toàn headers và correlation

Filter thường chuyển tiếp **message gốc** cho nhánh accepted hoặc discard; điều đó giúp giữ metadata có trên message.

Ví dụ:

~~~java
Message<OrderEvent> input = MessageBuilder
        .withPayload(event)
        .setHeader("traceId", "trace-1001")
        .setHeader("tenantId", "shop-a")
        .setHeader("businessCorrelationId", "order-1001")
        .build();
~~~

Trong flow notification, `traceId` giúp nối log, `businessCorrelationId` gắn những bước của đơn hàng. `tenantId` chỉ nên dùng để quyết định phân quyền khi nó đến từ **nguồn đã xác thực**; client tự khai báo tenantId không chứng minh quyền.

### 15.1. Filter theo payload không nên mutate message

~~~java
// Anti-pattern: predicate sửa payload đang chia sẻ.
public boolean accept(MutableOrder payload) {
    payload.setStatus("PROCESSED");
    return payload.getAmount() > 100;
}
~~~

Một message có thể được chia sẻ giữa nhiều subscriber hoặc đi qua async flow. Nếu Filter sửa payload, các consumer khác có thể nhìn thấy trạng thái bị thay đổi ngoài dự kiến. Dùng DTO bất biến và Transformer khi thật sự cần tạo payload mới.

### 15.2. Filter không tự đặt header lý do reject

Một `boolean` không cho biết **vì sao** message bị loại. Nếu cần lý do cụ thể, có thể:

- Ghi metric tại một bước quan sát có kiểm soát, dựa trên cùng quyết định.
- Tạo `ValidationResult` hoặc `EligibilityDecision` trong một bước trước Filter.
- Dùng Router theo reason code thay vì Filter nếu có nhiều nhánh reject.
- Dùng một exception có ý nghĩa nếu đây là vi phạm hợp đồng và caller cần nhận lỗi.

Không tự gắn header vào message đầu vào trong predicate bằng việc mutate `MessageHeaders`; cấu trúc headers của Spring message không cho sửa trực tiếp và việc tạo message mới thuộc trách nhiệm Transformer/Header Enricher.

## 16. Thiết kế nhiều điều kiện Filter

### 16.1. Một predicate có nhiều điều kiện

~~~java
return event.kind() == OrderEventKind.CREATED
        && event.customerOptIn()
        && event.amount().compareTo(MIN_AMOUNT) >= 0;
~~~

Ưu điểm: một quyết định nhất quán, một chỗ review và một bảng test. Hạn chế: khi có quá nhiều nhánh hoặc reason code, khó biết điều kiện nào gây reject.

### 16.2. Nhiều Filter nối tiếp

~~~mermaid
flowchart LR
    I["OrderEvent"] --> K{"Filter: CREATED?"}
    K -->|Yes| O{"Filter: opt-in?"}
    O -->|Yes| A{"Filter: amount >= 100?"}
    A -->|Yes| N["Notification"]
    K -->|No| D["Skip"]
    O -->|No| D
    A -->|No| D
~~~

Ưu điểm: dễ đo lý do tại từng nhánh và thay đổi điều kiện độc lập. Hạn chế: nhiều endpoint hơn, phải xác định discard channel của từng chặng; có thể mất ngữ cảnh nếu Filter nào đó bỏ message âm thầm.

Chọn một predicate hoặc chuỗi Filter tùy độ phức tạp, sự cần thiết của reason code và khả năng quan sát. Tránh tạo hàng chục Filter nhỏ mà không ai quản lý thứ tự hoặc nơi rejected message đi tới.

### 16.3. Quy tắc phụ thuộc thời gian

Nếu nhánh notification chỉ hoạt động trong giờ làm việc, đừng để predicate trực tiếp gọi `LocalTime.now()` rồi làm kết quả khó tái hiện. Có thể truyền **thời gian sự kiện** hoặc một snapshot business calendar đáng tin cậy làm dữ liệu đầu vào. Với quy tắc cần trạng thái runtime, xác định rõ vì sao lọc tại thời điểm nhận hay tại thời điểm xử lý.

## 17. Lỗi, retry và error channel

Điều kiện `false` không phải exception. Khi predicate ném exception, hệ thống cần biết **nguyên nhân**:

| Tình huống | Loại | Xử lý phù hợp |
|---|---|---|
| CREATED nhưng opt-in false | Rejection bình thường | Discard/skip, không retry |
| PAID trong nhánh notification CREATED | Rejection bình thường | Skip |
| Payload thiếu field bắt buộc | Validation failure | Reject theo hợp đồng, có lý do |
| Payload sai kiểu | Binding/conversion failure | Error handling tại adapter/endpoint |
| API enrich timeout | Lỗi hạ tầng trước Filter | Retry có giới hạn |
| Filter code NPE do bug | Lỗi chương trình | Error flow, điều tra |
| Handler gửi notification lỗi 503 | Downstream failure | Retry/idempotency riêng |

### 17.1. Error channel khác discard channel

- **discardChannel** nhận message mà Filter **chủ động từ chối** theo policy.
- **errorChannel** xử lý lỗi theo cơ chế messaging/error handling của topology, thường quan trọng trong luồng bất đồng bộ.
- Trong **DirectChannel đồng bộ**, exception có thể lan về thread gọi `send()`; không thể suy rằng cứ khai báo errorChannel là mọi exception được gửi vào đó.
- Nếu Filter được cấu hình `throwExceptionOnRejection`, một rejection có thể đi theo đường exception; cần thiết kế tránh xử lý trùng với discard.

### 17.2. Retry có thể làm phát sinh side effect trùng

Lọc thuần không có side effect là nền tảng tốt cho retry. Nhưng nếu message đã vượt Filter và NotificationService đã gửi email trước khi một bước sau lỗi, replay toàn event có thể gửi lại email. Đặt `eventId` ổn định và idempotency ở handler downstream, không dùng riêng `MessageHeaders.ID` làm khóa nghiệp vụ xuyên replay.

## 18. Quan sát Filter trong vận hành

Với hệ thống nhiều nguồn dữ liệu, nên đo tỷ lệ accept/reject và lý do ở mức an toàn.

| Chỉ số | Câu hỏi | Gợi ý |
|---|---|---|
| `filter_accepted_total{flow}` | Có bao nhiêu message qua filter? | Label flow có cardinality thấp |
| `filter_rejected_total{flow,reason}` | Những trường hợp nào bị loại? | Reason code ổn định |
| `filter_errors_total{flow,type}` | Filter có gặp exception? | Tách exception khỏi rejection |
| `filter_duration_seconds{flow}` | Predicate có chậm bất thường? | Predicate thuần nên rẻ |
| `notification_deliveries_total` | Handler đã gửi thành công bao nhiêu? | Không đồng nhất với accepted |
| `traceId` / `businessCorrelationId` | Message nào bị ảnh hưởng? | Ghi trong trace/log, tránh metric label |

### 18.1. Không log payload nhạy cảm

Payload có thể chứa email, địa chỉ, thông tin thanh toán. Đừng log toàn bộ object mỗi khi Filter reject chỉ để có khả năng chẩn đoán. Ghi `eventId`, flow, outcome, reason code và correlation ID với chính sách bảo mật phù hợp.

### 18.2. Rejection tăng đột ngột có thể là tín hiệu lỗi upstream

Nếu tỷ lệ rejected tăng từ 5% lên 80%, không nhất thiết predicate bị sai: có thể producer đổi schema, converter đổi cách map enum, hoặc opt-in mặc định đang bị false. Đặt cảnh báo theo tỉ lệ và kiểm tra dữ liệu đầu vào; một Filter "đúng code" vẫn có thể đang loại message ngoài dự kiến vì contract thay đổi.

## 19. Những lỗi phổ biến

### Lỗi 1 — Dùng Filter để thay Transformer

**Dấu hiệu:** predicate vừa chuẩn hóa amount/region vừa trả boolean. Những handler khác thấy payload đã bị sửa.

**Khắc phục:** tạo Transformer cho bước chuẩn hóa, Filter chỉ đưa ra quyết định accept/reject.

### Lỗi 2 — Không cấu hình discard channel cho message quan trọng

**Dấu hiệu:** một số đơn không còn thấy downstream và không có log lý do.

**Khắc phục:** cấu hình `discardChannel`, audit/metrics hoặc reply rejection theo hợp đồng. Với event chỉ nhằm chọn đối tượng quan tâm, loại âm thầm có thể chấp nhận nhưng phải là quyết định có chủ đích.

### Lỗi 3 — Xem `send()==true` là notification thành công

**Dấu hiệu:** producer báo gửi email thành công vì gửi được vào channel đầu vào.

**Khắc phục:** đo kết quả ở NotificationService/adapter, không suy từ giá trị trả về của message channel.

### Lỗi 4 — Predicate gọi API/DB

**Dấu hiệu:** timeout khiến Filter chậm, khó kiểm thử và retry không rõ trách nhiệm.

**Khắc phục:** tách enrichment trước Filter, truyền snapshot dữ liệu đã kiểm chứng, đặt timeout/retry ở endpoint gọi hệ thống ngoài.

### Lỗi 5 — Ép kiểu payload không kiểm tra

**Dấu hiệu:** message có payload String hoặc Map được gửi vào handler mong `OrderEvent` gây lỗi conversion.

**Khắc phục:** dùng decoder/validation ở ingress và hợp đồng payload rõ ràng; kiểm thử nguồn dữ liệu thực.

### Lỗi 6 — Filter ở nhánh Publish–Subscribe bị hiểu thành Filter toàn bộ event

**Dấu hiệu:** người thiết kế tưởng notification reject thì audit/analytics cũng sẽ bỏ event.

**Khắc phục:** xác định Filter được đặt trước hay sau fan-out; với nhiều subscriber, mỗi nhánh có quyết định riêng.

### Lỗi 7 — Loại các phần của Splitter mà không sửa release strategy

**Dấu hiệu:** Aggregator chờ không bao giờ đủ các thành phần.

**Khắc phục:** định nghĩa behavior với part bị loại, sequence size, timeout và partial group rõ ràng.

### Lỗi 8 — Quy tắc filter thay đổi mà không có test biên

**Dấu hiệu:** đơn đúng 100.00 bị loại sau một thay đổi so sánh `>` thay cho `>=`.

**Khắc phục:** parameterized test quanh ngưỡng 99.99, 100.00 và 100.01; kiểm tra opt-in, event kind và trường hợp chồng điều kiện.

### Lỗi 9 — Retry không giới hạn cho rejection

**Dấu hiệu:** event có opt-in false bị gửi lại hàng trăm lần.

**Khắc phục:** không retry chính sách `false`; chỉ retry lỗi có khả năng hồi phục, có backoff và số lần giới hạn.

### Lỗi 10 — Điều kiện nghiệp vụ dựa vào field chưa tin cậy

**Dấu hiệu:** client tự khai `isPremium=true` để lọt vào nhánh ưu tiên.

**Khắc phục:** authentication/authorization và enrichment giá trị đáng tin ở ranh giới đầu vào, không coi dữ liệu client gửi là bằng chứng quyền.

## 20. Bài tập thực hành

**Bài 1 — Predicate Java thuần.** Viết `OrderNotificationPolicy` cho event CREATED, amount từ 100 và opt-in. Dùng `@ParameterizedTest` cho ít nhất 8 input; xác minh ngưỡng và các sự kiện khác loại.

**Bài 2 — @Filter.** Tạo input `orders.events`, accepted `orders.notify` và rejected `orders.skipped`. Gửi message với `traceId` và assert đúng một channel nhận mỗi message.

**Bài 3 — Java DSL.** Viết lại flow trên bằng `IntegrationFlow.filter(OrderEvent.class, ...)`. Giữ cùng policy và cùng kết quả JUnit; bảo đảm không cùng lúc khai báo hai consumer cạnh tranh trên một `DirectChannel`.

**Bài 4 — Xử lý rejection.** Gắn một handler nhận `orders.skipped` ghi `eventId` và reason code an toàn. Phân biệt opt-in false và sự kiện PAID/CANCELLED. Không log toàn bộ payload.

**Bài 5 — Kết hợp Transformer.** Nhận `RawOrderEvent` từ JSON với amount dạng chuỗi, decode/normalize thành `OrderEvent` rồi lọc. Test rằng sự khác nhau về format không khiến event hợp lệ bị reject sai.

**Bài 6 — Publish–Subscribe.** Tạo Audit và Analytics luôn nhận message, Notification Filter chỉ chấp nhận một phần. Kiểm tra event bị filter ở Notification vẫn được Audit nhận.

**Bài 7 — Splitter/Aggregator.** Split một đơn thành nhiều dòng, lọc các dòng số tiền 0 hoặc không hợp lệ, sau đó gom lại. Thiết kế release strategy/timeout sao cho Aggregator không đợi vô hạn các dòng bị loại.

**Bài 8 — Error flow.** Cho predicate ném một exception có chủ đích trên input đặc biệt. So sánh kết quả qua DirectChannel và một flow bất đồng bộ có error channel. Không coi exception là discard bình thường.

**Bài 9 — Idempotency.** Giả lập một NotificationService gửi email thành công rồi bước downstream lỗi và message bị replay. Dùng `eventId` để chống gửi trùng; giải thích vì sao Filter thuần không giải quyết side effect downstream.

### Câu hỏi tự kiểm tra

1. Filter theo payload khác Header-Based Router ở điểm nào?
2. Predicate trả `false` có mặc nhiên là lỗi hệ thống không?
3. Khi không cấu hình discard channel, điều gì có thể xảy ra với message rejected?
4. Vì sao `@Filter` trả boolean không thể tự tạo nội dung lý do từ chối?
5. Payload có hợp lệ nhưng không opt-in nên đi rejection hay exception?
6. Tại sao `BigDecimal.compareTo` phù hợp cho ngưỡng tiền?
7. Filter có thay đổi payload/header của message không?
8. Trường hợp nào cần Transformer trước Filter?
9. Vì sao test policy thuần không đủ chứng minh channel output tồn tại?
10. Nếu Filter nằm trong một nhánh Publish–Subscribe, các nhánh khác có bị ảnh hưởng không?
11. Nếu Filter bỏ phần tử sau Splitter, Aggregator cần chú ý gì?
12. Vì sao không retry vô hạn message có opt-in false?
13. Làm sao phân biệt kết quả message channel với kết quả gửi email thực tế?
14. Cần giữ loại metadata nào để theo dõi accepted và rejected message?

## 21. Checklist trước khi triển khai

- [ ] Đã định nghĩa kiểu payload và validation ở ingress.
- [ ] Predicate chỉ thực hiện accept/reject, không mutate payload/header hoặc tạo side effect.
- [ ] Bảng quyết định có cả ngưỡng, giá trị biên và các điều kiện chồng lấn.
- [ ] `@Filter` hoặc Java DSL được khai báo đúng và không tạo nhiều consumer ngoài ý muốn.
- [ ] Output channel và discard channel (nếu cần) đều tồn tại và có handler theo hợp đồng.
- [ ] Đã phân biệt rejection bình thường với exception/error flow.
- [ ] Không cho rằng `send()==true` là nghiệp vụ đã hoàn tất.
- [ ] Trace/correlation/header cần thiết được giữ qua accepted/rejected paths.
- [ ] Với Filter sau Splitter, đã xét sequence/correlation và release strategy.
- [ ] Với Publish–Subscribe, đã xác định Filter áp dụng ở đầu fan-out hay riêng một nhánh.
- [ ] Handler có side effect sử dụng idempotency khi message có thể replay.
- [ ] Không tin các trường payload từ client khi dùng cho quyết định security.
- [ ] Có unit test predicate và integration test gửi/nhận qua channel.
- [ ] Có metric accepted/rejected/error và quy định an toàn khi log payload.
- [ ] Cấu hình retry, timeout và xử lý lỗi hạ tầng tách khỏi rejection cố định.

## 22. Tổng kết

**Filter theo payload** là một bước lựa chọn trong Spring Integration: **predicate trả `true`** thì message được phép tiếp tục, **trả `false`** thì message bị loại hoặc chuyển tới `discardChannel` theo cấu hình. Filter không có nhiệm vụ thay đổi payload như Transformer, cũng không chọn nhiều nhánh nghiệp vụ như Router. Đặt chính sách dưới dạng **hàm thuần** giúp dễ hiểu, kiểm thử nhanh và tránh side effect bất ngờ khi retry.

Trong **SPRING_INTEGRATION_PATTERN**, một Filter đáng tin cậy nên được đặt sau bước decode/validation phù hợp, chạy trước những handler đắt đỏ nếu điều kiện có thể xác định sớm, và có đường reject/quan sát rõ ràng. Khi phối hợp với Publish–Subscribe, Splitter/Aggregator, Gateway, Router, retry và error channel, cần hiểu scope của Filter, bảo toàn metadata và kiểm thử topology thực. Làm tốt những điều này sẽ giúp hệ thống thông điệp ít phụ thuộc, dễ mở rộng và dễ vận hành hơn.

### Tài liệu tham khảo

- Spring Integration Reference — Filter: https://docs.spring.io/spring-integration/reference/filter.html
- Spring Integration Reference — Java DSL: https://docs.spring.io/spring-integration/reference/dsl.html
- Spring Integration Reference — Message Channel Implementations: https://docs.spring.io/spring-integration/reference/channel/implementations.html
- Spring Integration API — Filter annotation: https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/Filter.html
- Spring Integration API — MessageFilter: https://docs.spring.io/spring-integration/api/org/springframework/integration/filter/MessageFilter.html
- JUnit 5 User Guide — Parameterized Tests: https://junit.org/junit5/docs/current/user-guide/#writing-tests-parameterized-tests

