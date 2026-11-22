# Chuyển đổi kiểu dữ liệu

Trong các hệ thống tích hợp, dữ liệu thường đến từ HTTP, file CSV, message broker hoặc API đối tác dưới dạng **chuỗi, byte, JSON, Map hoặc DTO có kiểu lỏng**. Trong khi đó, nghiệp vụ cần những kiểu dữ liệu rõ ràng: `BigDecimal` để tính tiền, `Instant` cho thời điểm, `enum` cho tập trạng thái và `boolean` cho quyết định đúng/sai. **Transformer** của Spring Integration giúp đặt bước chuyển đổi ấy vào một endpoint độc lập, có hợp đồng đầu vào/đầu ra, kiểm thử được và dễ quan sát.

Bài thuộc chương **Transformer** của module **SPRING_INTEGRATION_PATTERN**, tập trung áp dụng Enterprise Integration Patterns với Spring Integration để xây dựng luồng thông điệp ít phụ thuộc, dễ mở rộng. Bên cạnh Transformer, module còn thực hành Router, Filter, Splitter, Aggregator, Gateway, retry, error channel và correlation nhằm tổ chức các nhánh xử lý đáng tin cậy.

Chủ đề ở đây là **chuyển đổi kiểu dữ liệu**: làm sao biến payload thô thành dữ liệu có kiểu **đúng về ngữ nghĩa**, tránh mất độ chính xác, xử lý chuỗi không hợp lệ, giữ metadata của message và bảo đảm bước downstream chỉ nhận kiểu dữ liệu đã cam kết.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt việc **decode dữ liệu vận chuyển**, **chuyển đổi kiểu**, **chuẩn hóa**, **validation** và **xử lý nghiệp vụ**.
2. Thiết kế hợp đồng `RawOrder` → `TypedOrder` với các trường cần chuyển sang `BigDecimal`, `enum`, `Instant` và `boolean`.
3. Viết một converter Java thuần, từ chối dữ liệu không rõ nghĩa thay vì chuyển đổi âm thầm.
4. Tích hợp converter vào Spring Integration bằng `@Transformer` hoặc Java DSL `IntegrationFlow.transform(...)`.
5. Hiểu `ConversionService` của Spring Framework và khi nào nên dùng thay converter thủ công.
6. Giải thích sự khác nhau giữa Transformer trả **payload** và trả **Message hoàn chỉnh**.
7. Phân loại lỗi parse/type conversion, kết nối với error flow, retry và các bước Filter/Router.
8. Viết unit test, test ngưỡng và integration test kiểm tra payload cùng headers trên các channel thật.
9. Nhận diện rủi ro về locale, timezone, tiền tệ, null, độ chính xác, mutable data và contract version.
10. Đưa bước chuyển đổi thành một thành phần có thể tái sử dụng, quan sát và thay đổi an toàn.

## 2. Vị trí của Transformer trong pipeline

Một pipeline xử lý đơn hàng có thể gồm:

~~~mermaid
flowchart LR
    A["HTTP / MQ / CSV"] --> D["Decode: raw payload"]
    D --> S["Schema / giới hạn dữ liệu"]
    S --> T["Transformer: RawOrder → TypedOrder"]
    T --> V{"Validate typed invariants"}
    V -->|Valid| R{"Router"}
    V -->|Invalid| X["Reject/error"]
    R --> B["Priority handler"]
    R --> C["Standard handler"]
    T -->|Parse failure| E["Conversion error flow"]
~~~

Điều kiện quan trọng: các bước sau Transformer không cần tự phân tích chuỗi tiền hoặc đoán định dạng timestamp nữa. Chúng nhận một DTO có kiểu rõ ràng theo hợp đồng.

Ví dụ payload đầu vào:

~~~json
{
  "orderId": " ORDER-1001 ",
  "amount": "1250.50",
  "currency": "usd",
  "occurredAt": "2026-11-21T02:30:00Z",
  "priority": "TRUE"
}
~~~

Kết quả mong đợi:

~~~text
TypedOrder
  orderId: "ORDER-1001"                 String
  amount: 1250.50                       BigDecimal
  currency: USD                         CurrencyCode enum
  occurredAt: 2026-11-21T02:30:00Z     Instant
  priority: true                        boolean
~~~

Trong ví dụ, trường `amount` **không được phép** có dấu phân cách hàng nghìn, biểu thức khoa học hoặc nhiều hơn hai chữ số thập phân. Đây là một lựa chọn hợp đồng có chủ ý để tránh sự khác nhau giữa locale và producer.

### 2.1. Các khái niệm thường bị nhầm

| Công việc | Ví dụ | Thành phần phù hợp |
|---|---|---|
| Giải mã bytes/JSON | Chuỗi JSON → `RawOrder` | Inbound message converter, Jackson/decoder, adapter |
| Chuyển kiểu | `"1250.50"` → `BigDecimal` | Transformer/`ConversionService` |
| Chuẩn hóa | `"usd"` → `USD`, trim mã đơn | Transformer hoặc bước normalization rõ ràng |
| Kiểm tra invariant | `amount > 0`, mã tiền hỗ trợ | Validation ở ranh giới, có thể kết hợp converter theo contract |
| Chọn nhánh | `priority=true` → channel ưu tiên | Router |
| Loại message | Event không phù hợp | Filter |
| Ghi DB hoặc gọi API | Lưu đơn / gửi thanh toán | Service Activator, outbound adapter |

Một Transformer có thể vừa chuyển kiểu vừa xác minh định dạng cơ bản để không tạo ra object sai; tuy nhiên, những quy tắc nghiệp vụ phụ thuộc DB/trạng thái hiện tại nên nằm ở **handler hoặc service có transaction phù hợp**.

## 3. Vì sao chuyển đổi kiểu dữ liệu cần được thiết kế chặt chẽ?

Nếu chỉ dùng `String.valueOf`, `Boolean.parseBoolean`, `Double.parseDouble` và `LocalDateTime.parse` mà không xác định hợp đồng, hệ thống có thể tạo dữ liệu **trông có vẻ hợp lệ nhưng sai ý nghĩa**.

Ví dụ:

- `Boolean.parseBoolean("yes")` trả `false`, không ném lỗi. Producer gửi `"yes"` có thể bị hiểu là không ưu tiên.
- `Double.parseDouble("0.1")` cho giá trị dấu phẩy động nhị phân không biểu diễn chính xác 0.1. Chuyển nó sang `BigDecimal` theo cách bất cẩn gây rủi ro tính tiền.
- `"1,234.50"` có thể mang ý nghĩa khác `"1.234,50"` tùy locale.
- `"2026-11-21 09:30"` không chứa offset/timezone; chuyển ngay thành `Instant` phải **đưa thêm quy tắc múi giờ**.
- Enum parse theo `valueOf` sẽ thất bại với chữ thường nếu chưa normalize, nhưng normalize quá rộng cũng có thể che dữ liệu sai.
- Một DTO có field `amount=null` có thể bị bỏ qua nếu bước chuyển đổi mặc nhiên thay bằng 0.

**Nguyên tắc:** chuyển đổi phải rõ ràng về những biểu diễn được chấp nhận và hành vi khi không thể chuyển. Không tự chọn giá trị mặc định có tác động nghiệp vụ nếu producer chưa cam kết điều đó.

## 4. Định nghĩa kiểu đầu vào và đầu ra

Ví dụ dùng Java 17+ với `record` để giữ payload bất biến theo API.

### 4.1. DTO đầu vào

~~~java
public record RawOrder(
        String orderId,
        String amountText,
        String currencyText,
        String occurredAtText,
        String priorityText
) {}
~~~

Một inbound adapter có thể tạo `RawOrder` từ JSON, CSV hoặc các nguồn đã được giải mã. Class này giữ các trường dạng `String` như nhận từ bên ngoài; nó **không khẳng định** các giá trị đã được parse hay kiểm tra.

### 4.2. DTO có kiểu

~~~java
import java.math.BigDecimal;
import java.time.Instant;

public enum CurrencyCode {
    USD,
    EUR
}

public record TypedOrder(
        String orderId,
        BigDecimal amount,
        CurrencyCode currency,
        Instant occurredAt,
        boolean priority
) {}
~~~

Trong project thực tế, khai báo `public enum CurrencyCode` và `public record TypedOrder` trong các source file riêng hoặc sắp xếp visibility/package hợp lệ theo Java. `BigDecimal`, `Instant`, `String` và enum đều là những giá trị bất biến; record không tạo setter.

**Ý nghĩa của kiểu:** khi một handler nhận `TypedOrder`, nó có thể gọi `order.amount().compareTo(...)` hoặc `order.occurredAt().isBefore(...)` mà không parse lại. Điều đó giảm duplication và lỗi giữa các nhánh.

### 4.3. Hợp đồng chuyển đổi

| Input `RawOrder` | Output `TypedOrder` | Quy tắc |
|---|---|---|
| `orderId` | `String` | Bắt buộc; bỏ khoảng trắng đầu/cuối |
| `amountText` | `BigDecimal` | Chỉ chữ số với phần thập phân tùy chọn, tối đa 2 số; phải lớn hơn 0 |
| `currencyText` | `CurrencyCode` | Trim, uppercase bằng `Locale.ROOT`; chỉ `USD` hoặc `EUR` |
| `occurredAtText` | `Instant` | Chuỗi timestamp ISO-8601 có thời điểm rõ ràng; ví dụ `...Z` |
| `priorityText` | `boolean` | Trim, không phân biệt chữ hoa/thường; chỉ `true` hoặc `false` |

Đây là quy tắc minh họa, không phải bắt buộc mọi hệ thống đều dùng hai chữ số thập phân hoặc chỉ USD/EUR. Khi ứng dụng hỗ trợ VND, JPY hay đơn vị có scale khác, cần thiết kế quy tắc theo từng currency thay vì sao chép nguyên mẫu số thập phân này.

## 5. Lỗi chuyển đổi cần có mã rõ ràng

Một lỗi như "không chuyển được" thường chưa đủ để debug hoặc trả phản hồi API. Ta định nghĩa một exception có mã ổn định, không buộc lộ giá trị thô nhạy cảm.

~~~java
public final class OrderConversionException
        extends RuntimeException {

    private final String code;

    public OrderConversionException(String code) {
        super(code);
        this.code = code;
    }

    public OrderConversionException(
            String code, Throwable cause) {
        super(code, cause);
        this.code = code;
    }

    public String code() {
        return code;
    }
}
~~~

Các mã gợi ý:

| Code | Trường | Ý nghĩa |
|---|---|---|
| `ORDER_ID_REQUIRED` | `orderId` | Thiếu/blank |
| `AMOUNT_REQUIRED` | `amountText` | Thiếu/blank |
| `INVALID_AMOUNT_FORMAT` | `amountText` | Không theo grammar quy định |
| `AMOUNT_MUST_BE_POSITIVE` | `amountText` | Giá trị bằng 0 hoặc âm |
| `CURRENCY_REQUIRED` | `currencyText` | Thiếu/blank |
| `UNSUPPORTED_CURRENCY` | `currencyText` | Không phải USD/EUR |
| `OCCURRED_AT_REQUIRED` | `occurredAtText` | Thiếu/blank |
| `INVALID_OCCURRED_AT` | `occurredAtText` | Không parse được thành `Instant` |
| `PRIORITY_REQUIRED` | `priorityText` | Thiếu/blank |
| `INVALID_PRIORITY` | `priorityText` | Không phải true/false |

Exception dùng để báo một vi phạm hợp đồng chuyển đổi, còn **rejection của Filter** là một lựa chọn bình thường đối với message hợp lệ nhưng không cần xử lý ở nhánh đó. Hai trường hợp không nên gộp chung trong metrics hoặc retry.

## 6. Converter Java thuần: String → BigDecimal/enum/Instant/boolean

Nên bắt đầu với một hàm không phụ thuộc Spring: nhận `RawOrder`, trả `TypedOrder` hoặc ném một lỗi chuyển đổi có mã cụ thể.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.Locale;
import java.util.Objects;
import java.util.regex.Pattern;

public final class OrderTypeConverter {

    // Chỉ nhận 1, 12, 12.3, 12.34; không nhận 1,000 hay 1e3.
    private static final Pattern AMOUNT =
            Pattern.compile("[0-9]+(\\.[0-9]{1,2})?");

    public TypedOrder convert(RawOrder raw) {
        Objects.requireNonNull(raw, "raw");

        String orderId =
                required(raw.orderId(), "ORDER_ID_REQUIRED");
        BigDecimal amount = parseAmount(raw.amountText());
        CurrencyCode currency =
                parseCurrency(raw.currencyText());
        Instant occurredAt =
                parseInstant(raw.occurredAtText());
        boolean priority =
                parsePriority(raw.priorityText());

        return new TypedOrder(
                orderId, amount, currency, occurredAt, priority);
    }

    private String required(String value, String code) {
        if (value == null || value.isBlank()) {
            throw new OrderConversionException(code);
        }
        return value.strip();
    }

    private BigDecimal parseAmount(String rawAmount) {
        String text = required(rawAmount, "AMOUNT_REQUIRED");

        if (!AMOUNT.matcher(text).matches()) {
            throw new OrderConversionException(
                    "INVALID_AMOUNT_FORMAT");
        }

        BigDecimal amount = new BigDecimal(text);

        if (amount.signum() <= 0) {
            throw new OrderConversionException(
                    "AMOUNT_MUST_BE_POSITIVE");
        }

        // Contract minh họa cho phép tối đa 2 số thập phân.
        // Không làm tròn một số có dữ liệu vượt quá độ chính xác.
        return amount.setScale(2, RoundingMode.UNNECESSARY);
    }

    private CurrencyCode parseCurrency(String rawCurrency) {
        String text = required(
                rawCurrency, "CURRENCY_REQUIRED")
                .toUpperCase(Locale.ROOT);

        return switch (text) {
            case "USD" -> CurrencyCode.USD;
            case "EUR" -> CurrencyCode.EUR;
            default -> throw new OrderConversionException(
                    "UNSUPPORTED_CURRENCY");
        };
    }

    private Instant parseInstant(String rawTimestamp) {
        String text = required(
                rawTimestamp, "OCCURRED_AT_REQUIRED");

        try {
            return Instant.parse(text);
        } catch (DateTimeParseException exception) {
            throw new OrderConversionException(
                    "INVALID_OCCURRED_AT", exception);
        }
    }

    private boolean parsePriority(String rawPriority) {
        String text = required(
                rawPriority, "PRIORITY_REQUIRED")
                .toLowerCase(Locale.ROOT);

        return switch (text) {
            case "true" -> true;
            case "false" -> false;
            default -> throw new OrderConversionException(
                    "INVALID_PRIORITY");
        };
    }
}
~~~

### 6.1. Tại sao đặt parse logic trong class riêng?

- Unit test chạy trực tiếp mà không cần `ApplicationContext`.
- Code không chứa channel name hay BeanFactory.
- Cùng input có cùng kết quả, nếu các lớp phụ thuộc giữ trạng thái bất biến.
- Có một nơi công bố grammar và mã lỗi.
- Nhiều flow có thể tái sử dụng converter mà không copy logic.
- Dễ tách lỗi dữ liệu khỏi lỗi hạ tầng và quyết định retry.

Trong một production service, bạn có thể dùng validator và bộ chuyển kiểu đã được chuẩn hóa của tổ chức. Ví dụ trên cố tình minh họa các quy tắc để người học nhìn thấy **chính xác dữ liệu nào được phép chuyển**.

### 6.2. Dùng biểu thức chính quy để làm gì?

`Pattern.compile("[0-9]+(\\.[0-9]{1,2})?")` mô tả:

- Một hoặc nhiều chữ số `0–9`.
- Có thể thêm dấu chấm và từ một đến hai chữ số phần thập phân.
- Không nhận dấu cộng/trừ, dấu phẩy, scientific notation hoặc ký tự lạ.

Chẳng hạn:

| Chuỗi đầu vào | Kết quả |
|---|---|
| `"1250.50"` | `1250.50` |
| `" 1250.5 "` | `1250.50` sau trim/scale |
| `"100"` | `100.00` |
| `"0"` | Lỗi `AMOUNT_MUST_BE_POSITIVE` |
| `"-1"` | Lỗi `INVALID_AMOUNT_FORMAT` |
| `"1,250.50"` | Lỗi `INVALID_AMOUNT_FORMAT` |
| `"1250,50"` | Lỗi `INVALID_AMOUNT_FORMAT` |
| `"1e3"` | Lỗi `INVALID_AMOUNT_FORMAT` |
| `"100.999"` | Lỗi `INVALID_AMOUNT_FORMAT` |

Điều này giúp hợp đồng minh bạch. Nếu muốn cho phép dấu âm để xử lý refund hoặc notation khác, hãy **thay đổi contract có chủ đích**, không chỉ bỏ regex và hy vọng `BigDecimal` tự đoán đúng mọi định dạng.

### 6.3. Vì sao không dùng Double cho tiền?

~~~java
// Không nên dùng cho giá trị tiền theo hợp đồng này:
double value = Double.parseDouble("0.1");
BigDecimal risky = new BigDecimal(value);

// Ưu tiên:
BigDecimal precise = new BigDecimal("0.1");
~~~

`double` biểu diễn nhị phân và không thể biểu diễn chính xác phần lớn phân số thập phân. `new BigDecimal(double)` làm lộ giá trị nhị phân gần đúng. Nếu nguồn là chuỗi thập phân, tạo `BigDecimal` **trực tiếp từ chuỗi** giữ đúng giá trị dự định.

### 6.4. Vì sao parsePriority không dùng Boolean.parseBoolean?

~~~java
Boolean.parseBoolean("true");  // true
Boolean.parseBoolean("false"); // false
Boolean.parseBoolean("yes");   // false
Boolean.parseBoolean("1");     // false
Boolean.parseBoolean("oops");  // false
~~~

Nếu nguồn gửi `"oops"`, trả `false` âm thầm có thể khiến đơn ưu tiên đi nhánh thường. Với trường bắt buộc, dùng switch trên tập từ vựng chấp nhận và báo lỗi cho những giá trị khác.

### 6.5. Thời gian: Instant khác LocalDateTime

`Instant` biểu diễn một điểm trên timeline, không tự giữ timezone gốc để hiển thị. `Instant.parse("2026-11-21T02:30:00Z")` trả một thời điểm có ý nghĩa toàn cầu. Ngược lại, chuỗi `"2026-11-21 09:30:00"` không cho biết vị trí múi giờ nên không thể suy ra một instant duy nhất.

Nếu contract cho phép ngày giờ địa phương, cần công bố `ZoneId` hoặc offset riêng:

~~~java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;

LocalDateTime local =
        LocalDateTime.parse("2026-11-21T09:30:00");

Instant instant = local
        .atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
        .toInstant();
~~~

Đây là một quy tắc **có thêm múi giờ từ nghiệp vụ**. Đừng tự lấy timezone mặc định của server để chuyển đổi dữ liệu của khách hàng, bởi deploy sang môi trường khác có thể tạo thời điểm khác. Với các vùng có daylight saving, cần thêm chính sách cho thời điểm bị lặp hoặc không tồn tại.

## 7. Đưa converter vào @Transformer

Spring Integration cung cấp `org.springframework.integration.annotation.Transformer`. Method có thể nhận **payload có kiểu** và trả **payload có kiểu mới**.

~~~java
import org.springframework.integration.annotation.Transformer;

public final class OrderTransformer {

    private final OrderTypeConverter converter;

    public OrderTransformer(OrderTypeConverter converter) {
        this.converter = converter;
    }

    @Transformer(
            inputChannel = "orders.raw",
            outputChannel = "orders.typed")
    public TypedOrder toTypedOrder(RawOrder raw) {
        return converter.convert(raw);
    }
}
~~~

Khi một `Message<RawOrder>` được gửi vào `orders.raw`:

1. Spring Integration nhận message ở endpoint transformer.
2. Nó cung cấp payload `RawOrder` cho method.
3. Method gọi converter Java thuần.
4. Nếu thành công, method trả `TypedOrder`.
5. Framework tạo message output và gửi tới `orders.typed` theo cấu hình.
6. Nếu converter ném exception, **không có payload kết quả hợp lệ** được đưa tới output channel qua lần xử lý đó.

### 7.1. Đăng ký bean và channels

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
public class OrderTransformerConfiguration {

    @Bean(name = "orders.raw")
    public MessageChannel rawOrders() {
        return new DirectChannel();
    }

    @Bean(name = "orders.typed")
    public PollableChannel typedOrders() {
        return new QueueChannel();
    }

    @Bean
    public OrderTypeConverter orderTypeConverter() {
        return new OrderTypeConverter();
    }

    @Bean
    public OrderTransformer orderTransformer(
            OrderTypeConverter converter) {
        return new OrderTransformer(converter);
    }
}
~~~

Các output `QueueChannel` trong ví dụ dùng cho test; trong hệ thống thật, output thường nối tới validator, router hoặc service activator. `QueueChannel` in-memory mặc định **không** bảo đảm bền vững khi ứng dụng restart.

Annotation `@Transformer` chỉ có tác dụng khi object được Spring quản lý và hạ tầng Integration annotation đã được bật. Gọi `new OrderTransformer(...)` bên ngoài Spring không tự tạo ra messaging endpoint.

### 7.2. Một ví dụ gửi message

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

void send(MessageChannel rawChannel) {
    RawOrder raw = new RawOrder(
            " ORDER-1001 ",
            "1250.50",
            "usd",
            "2026-11-21T02:30:00Z",
            "TRUE");

    Message<RawOrder> message =
            MessageBuilder.withPayload(raw)
                    .setHeader("traceId", "trace-1001")
                    .setHeader(
                            "businessCorrelationId", "ORDER-1001")
                    .build();

    rawChannel.send(message);
}
~~~

Sau khi transformer hoàn thành, output chứa `TypedOrder`. `traceId` và `businessCorrelationId` có thể được giữ trên output message theo cơ chế truyền headers của Transformer trả payload. Phần test sau sẽ **xác minh điều đó thực tế**, thay vì chỉ giả định.

### 7.3. Đừng thay cả payload lẫn side effect trong một Transformer

~~~java
// Anti-pattern minh họa:
@Transformer(inputChannel = "orders.raw")
public TypedOrder convertAndSave(RawOrder raw) {
    TypedOrder order = converter.convert(raw);
    repository.save(order);
    notificationService.send(order.orderId());
    return order;
}
~~~

Nếu việc gửi reply lỗi, message được retry, code có thể ghi DB/gửi notification lần nữa. Nên tách conversion thuần thành Transformer, ghi DB và gửi notification thành những handler riêng với transaction/idempotency thích hợp.

## 8. Dùng Java DSL transform(...)

Java DSL giúp nhìn rõ topology trên một đoạn cấu hình, đồng thời tái sử dụng converter thuần:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
public class TypedOrderDslConfiguration {

    @Bean
    public IntegrationFlow typedOrderFlow(
            OrderTypeConverter converter) {

        return IntegrationFlow.from("orders.dsl.raw")
                .transform(RawOrder.class, converter::convert)
                .channel("orders.dsl.typed")
                .get();
    }
}
~~~

Flow trên chỉ nhận payload `RawOrder` theo hợp đồng; nếu input là JSON string hoặc Map tùy ý, hãy decode/convert ở bước trước. Với các channel được đặt tên, khai báo bean/channel phù hợp để tránh nhầm lẫn khi test và deploy.

**Đây là cách viết thay thế** cho `@Transformer` ở mục 7, không đăng ký cả hai trên cùng `DirectChannel` nếu mục đích là một pipeline duy nhất. Khi có nhiều consumer trên `DirectChannel`, message thông thường không được phát broadcast tới mọi consumer.

### 8.1. Chuyển đổi đơn giản bằng lambda

~~~java
@Bean
IntegrationFlow simpleQuantityFlow() {
    return IntegrationFlow.from("quantity.raw")
            .transform(String.class, Integer::valueOf)
            .channel("quantity.number")
            .get();
}
~~~

Ví dụ này minh họa cú pháp ngắn. Với dữ liệu sai như `"not-a-number"`, `Integer.valueOf` ném lỗi. Nếu đây là input đến từ bên ngoài, nên bổ sung giới hạn độ dài, phân loại lỗi và hợp đồng kết quả; đừng mặc định mọi chuỗi đều chuyển được.

### 8.2. Tách nhiều chuyển đổi có ý nghĩa

~~~mermaid
flowchart LR
    A["raw.order.json"] --> J["JSON decoder"]
    J --> B["RawOrder"]
    B --> C["Type Transformer"]
    C --> D["TypedOrder"]
    D --> V["Validation"]
    V --> R{"Router"}
    R --> P["Priority"]
    R --> N["Normal"]
~~~

Mỗi bước có thể có test riêng. Không nên tạo vô số Transformer chỉ để nối từng lời gọi `trim`, nhưng cũng đừng nhét toàn bộ decode/validation/DB/notification vào một method duy nhất nếu các lỗi và chính sách retry khác nhau.

## 9. ConversionService của Spring Framework

Spring Framework cung cấp `org.springframework.core.convert.ConversionService` để chuyển đổi kiểu qua những converter đã đăng ký. Với các kiểu đơn giản, nó giúp tránh lặp conversion logic.

~~~java
import org.springframework.core.convert.ConversionService;
import org.springframework.core.convert.support.DefaultConversionService;

ConversionService conversionService =
        new DefaultConversionService();

Integer quantity =
        conversionService.convert("42", Integer.class);

Boolean flag =
        conversionService.convert("true", Boolean.class);
~~~

Đây là ví dụ dùng trực tiếp Spring Framework, **không tự động là một Spring Integration Transformer endpoint**. Bạn có thể gọi `ConversionService` trong một Transformer hoặc đăng ký nó như bean phục vụ các điểm chuyển kiểu khác.

### 9.1. Khi nào dùng built-in converter?

| Nhu cầu | Hướng tiếp cận |
|---|---|
| `"42"` → `Integer` không thêm quy tắc | Built-in `ConversionService` hoặc `Integer.valueOf` |
| String → enum với quy tắc chuẩn của framework | Converter có sẵn, sau đó kiểm tra policy |
| `"TRUE"`/`"FALSE"` với tập giá trị hẹp theo contract | Converter custom như `OrderTypeConverter` |
| `"1250.50"` → `BigDecimal` với grammar/scale nghiêm ngặt | Converter custom hoặc converter được đăng ký rõ |
| `LocalDateTime` → `Instant` cần `ZoneId` của nghiệp vụ | Conversion có context/timezone tường minh |
| JSON → DTO | Message converter/decoder như Jackson tại boundary |
| `RawOrder` → `TypedOrder` với nhiều trường và mã lỗi | Domain-specific Transformer/converter |

**Điểm quan trọng:** những bộ chuyển đổi mặc định có thể chấp nhận những biểu diễn khác policy của ứng dụng. Việc dùng `ConversionService` không tự bảo đảm tiền tệ, timezone và các quy tắc nghiệp vụ là đúng.

### 9.2. Tạo converter tùy chỉnh cho ConversionService

Spring Framework có interface `Converter<S,T>`:

~~~java
import org.springframework.core.convert.converter.Converter;

public final class RawOrderToTypedOrderConverter
        implements Converter<RawOrder, TypedOrder> {

    private final OrderTypeConverter delegate;

    public RawOrderToTypedOrderConverter(
            OrderTypeConverter delegate) {
        this.delegate = delegate;
    }

    @Override
    public TypedOrder convert(RawOrder source) {
        return delegate.convert(source);
    }
}
~~~

Khi đăng ký converter này vào `FormattingConversionService` / `ConversionService` phù hợp, các thành phần dùng service đó có thể tái sử dụng nó. Hãy kiểm soát **phạm vi đăng ký**: một converter global sẽ ảnh hưởng tới mọi nơi framework dùng cùng service, không chỉ một flow. Với conversion có hậu quả nghiệp vụ, một Transformer tường minh thường dễ nhận biết hơn.

### 9.3. Không nhầm conversion ngầm với transformation tường minh

Một method `@Transformer` có tham số `TypedOrder` nhưng producer gửi `String` không bảo đảm Spring Integration biết cách convert một JSON string bất kỳ thành `TypedOrder`. Argument resolution và message conversion phụ thuộc cấu hình converters. Với flow quan trọng, nên biểu diễn **decoder/converter trước**, rồi method Transformer nhận type đã biết; test trực tiếp từ payload thực tế của inbound adapter.

## 10. JSON, CSV và Map: hiểu ranh giới decode

### 10.1. JSON → RawOrder trước khi chuyển kiểu

Với một API/broker gửi JSON:

~~~json
{
  "orderId": " ORDER-1001 ",
  "amountText": "1250.50",
  "currencyText": "USD",
  "occurredAtText": "2026-11-21T02:30:00Z",
  "priorityText": "true"
}
~~~

Một JSON decoder như Jackson có thể ánh xạ fields vào `RawOrder`. Sau đó `OrderTypeConverter` chuyển sang `TypedOrder`. Nếu một trường không tồn tại, kết quả có thể là `null` tùy cơ chế binding, và converter sẽ phát mã lỗi tương ứng.

Đừng trộn lỗi **JSON không hợp lệ cú pháp** với lỗi **`amountText` sai grammar**. Lỗi đầu xảy ra ở decoder; lỗi sau ở bước chuyển kiểu.

### 10.2. CSV và phân tách ký tự

Ví dụ:

~~~text
ORDER-1001,1250.50,USD,2026-11-21T02:30:00Z,true
~~~

CSV parser phải xử lý dấu phẩy trong giá trị được quote, escaping, encoding, BOM và header row trước khi tạo `RawOrder`. Không dùng `line.split(",")` làm một parser CSV chung trong production. Khi đã có DTO, converter không cần biết dữ liệu đến từ CSV hay JSON.

### 10.3. Map động

Khi inbound adapter trả `Map<String,Object>`, không nên ép các field như `(String) map.get("amount")` nếu giá trị thực có thể là `Integer`, `Double` hoặc `BigDecimal`. Nên xác định schema/value types trước và dùng một adapter có test để chuẩn hóa về `RawOrder` hoặc một DTO khác.

Những thao tác như `String.valueOf(map.get("amount"))` có thể biến `null` thành chuỗi `"null"`, hoặc làm mất khả năng phân biệt giữa giá trị gốc số và chuỗi. Nếu amount có thể là JSON number, kiểm tra cấu hình deserializer để giữ độ chính xác thập phân phù hợp.

## 11. Payload Transformer khác Message Transformer

Đây là một khác biệt quan trọng trong Spring Integration.

### 11.1. Trả payload mới

~~~java
@Transformer(
        inputChannel = "orders.raw",
        outputChannel = "orders.typed")
public TypedOrder convert(RawOrder input) {
    return converter.convert(input);
}
~~~

Framework tạo message output cho `TypedOrder`. Theo quy tắc truyền headers của Spring Integration, các header đầu vào phù hợp có thể được giữ lại tự động.

### 11.2. Trả một Message hoàn chỉnh

~~~java
import org.springframework.integration.annotation.Transformer;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Transformer(
        inputChannel = "orders.raw",
        outputChannel = "orders.typed")
public Message<TypedOrder> convertMessage(
        Message<RawOrder> input) {

    TypedOrder typed = converter.convert(input.getPayload());

    return MessageBuilder.withPayload(typed)
            .copyHeaders(input.getHeaders())
            .build();
}
~~~

Đây là **một phương án khác**, không khai báo đồng thời trên input channel đã có Transformer ở mục 11.1.

Khi return một `Message<?>` mới, code chịu trách nhiệm nội dung của message đó; không nên giả định mọi header từ request sẽ tự xuất hiện. `copyHeaders(...)` minh họa cách chủ động mang metadata, nhưng tại trust boundary cần có **whitelist** để tránh chuyển header nhạy cảm hay object không serializable sang hệ thống ngoài.

### 11.3. Header nào nên kiểm thử?

| Header | Mục đích | Ghi chú |
|---|---|---|
| `traceId` | Theo dõi các chặng | Nên giữ theo observability contract |
| `businessCorrelationId` | Gắn các message trong cùng nghiệp vụ | Không lấy Message ID làm correlation bền vững |
| `replyChannel` | Gateway/request–reply | Phải giữ khi flow vẫn cần reply |
| `errorChannel` | Đường lỗi trong topology tương ứng | Không sao chép qua boundary không hỗ trợ |
| `tenantId` | Scoping dữ liệu | Chỉ dùng khi đã được xác thực |
| `schemaVersion` | Diễn giải payload version | Có thể cần cập nhật khi đổi contract |
| `MessageHeaders.ID` | ID của message instance | Có thể được framework tạo mới; không đòi giữ nguyên |

**Không đổi `traceId` hay `businessCorrelationId` chỉ vì đổi payload từ String sang BigDecimal.** Đồng thời, nếu tạo DTO mới nhưng vẫn giữ `contentType=application/json` của raw bytes một cách mù quáng, downstream có thể hiểu sai message; kiểm tra mapping/metadata của từng adapter thực tế.

## 12. Một Transformer có được trả null không?

Không nên dùng `return null` để biểu diễn "chuyển đổi thất bại" hoặc "loại message".

~~~java
// Anti-pattern:
@Transformer(inputChannel = "orders.raw")
public TypedOrder unsafeConvert(RawOrder input) {
    if (input.amountText() == null) {
        return null;
    }
    return converter.convert(input);
}
~~~

Trong Spring Integration, Transformer được kỳ vọng tạo kết quả; trả `null` có thể dẫn tới `MessageTransformationException` hoặc lỗi tương đương. Nếu ý định là:

- **Reject một message hợp lệ không thuộc phạm vi:** dùng Filter với `discardChannel` nếu cần.
- **Không parse được dữ liệu:** ném exception chuyển đổi có ý nghĩa hoặc dùng result type tường minh.
- **Trả nhiều nhánh theo trạng thái:** dùng Router.
- **Chuyển một message thành collection/số lượng phần:** xem xét Transformer hoặc Splitter theo contract.

### 12.1. Result type tường minh thay cho exception

Nếu cần xử lý lỗi như **dữ liệu** thay vì throw:

~~~java
public sealed interface ConversionOutcome
        permits ConversionAccepted, ConversionRejected {}

public record ConversionAccepted(TypedOrder value)
        implements ConversionOutcome {}

public record ConversionRejected(
        String errorCode,
        String fieldName)
        implements ConversionOutcome {}
~~~

Một Transformer có thể trả `ConversionOutcome`, rồi Router đưa `ConversionAccepted` tới nhánh thành công và `ConversionRejected` tới nhánh reject. Mô hình này phù hợp khi mọi input phải sinh một kết quả được ghi nhận, nhất là khi consumer bất đồng bộ không có caller đang chờ exception.

Đổi lại, downstream phải xử lý sealed hierarchy, hoặc một Transformer bổ sung chuyển `ConversionAccepted.value()` thành `TypedOrder`. Không trộn mô hình result type với `throwExceptionOnRejection` của Filter rồi vô tình phản hồi lỗi hai lần.

## 13. Lỗi chuyển đổi trong sync và async flow

Khi converter ném `OrderConversionException`, Spring Integration có thể bọc nó trong một exception của messaging/transformer. Cách lỗi đến caller tùy topology:

| Topology | Đường lỗi thường gặp | Cần lưu ý |
|---|---|---|
| `DirectChannel` đồng bộ | Exception nổi về sender của `send()` hoặc Gateway | Caller có thể kiểm tra cause chain |
| `ExecutorChannel` | Lỗi phát sinh trên worker | Cần error handling thích hợp; caller gửi không nhất thiết thấy |
| Message-driven inbound adapter | Listener/container xử lý exception | Ack/retry/dead-letter tùy adapter |
| Gateway request–reply | Lỗi hoặc timeout theo cấu hình | Phải bảo đảm có phản hồi đúng contract |
| Router phía sau conversion | Không được gọi khi conversion thất bại | Test rằng typed channel trống trên lỗi |

### 13.1. Không retry dữ liệu sai cố định

`amountText="abc"` hoặc `priorityText="oops"` sẽ không tự trở nên hợp lệ khi thử lại cùng payload. Lỗi này nên được trả về producer, gửi tới reject/quarantine hoặc ghi trạng thái lỗi theo chính sách; không retry vô hạn.

Ngược lại, một Transformer làm thêm việc enrich từ API ngoài có thể gặp timeout tạm thời. Tốt hơn nên **tách enrichment** thành endpoint riêng để có chính sách retry khác với pure type conversion.

### 13.2. Lỗi chuyển đổi có thể được bọc

Đừng bắt buộc rằng exception ngoài cùng luôn là `OrderConversionException`. Handler framework có thể ném một loại `MessagingException` với cause là conversion exception. Khi xây error flow, tìm **nguyên nhân** trong cause chain có kiểm soát và map sang mã lỗi ổn định; không tự động trả stack trace hoặc giá trị raw nhạy cảm cho bên gửi.

### 13.3. Không coi errorChannel là tự động trong mọi flow

Trong luồng đồng bộ, exception có thể lan thẳng về caller. Với flow async, hạ tầng có thể phát `ErrorMessage` tới channel được cấu hình. **Đừng suy rằng chỉ cần thêm header `errorChannel` là mọi lỗi ở mọi endpoint đều tự đi vào đó**. Cần kiểm thử topology thực tế, nhất là khi MessageTransformer nằm sau Gateway hoặc broker consumer.

## 14. Unit test converter Java thuần

Unit test nên bắt đầu từ những trường hợp không cần Spring. JUnit 5 có thể kiểm tra cả thành công lẫn mã lỗi.

### 14.1. Trường hợp chuyển đổi thành công

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.time.Instant;

import org.junit.jupiter.api.Test;

class OrderTypeConverterTest {

    private final OrderTypeConverter converter =
            new OrderTypeConverter();

    @Test
    void convertsRawStringsToTypedValues() {
        RawOrder input = new RawOrder(
                " ORDER-1001 ",
                "1250.50",
                "usd",
                "2026-11-21T02:30:00Z",
                "TRUE");

        TypedOrder result = converter.convert(input);

        assertEquals("ORDER-1001", result.orderId());
        assertEquals(new BigDecimal("1250.50"), result.amount());
        assertEquals(CurrencyCode.USD, result.currency());
        assertEquals(
                Instant.parse("2026-11-21T02:30:00Z"),
                result.occurredAt());
        assertTrue(result.priority());
    }

    @Test
    void trimsAndUsesTwoDecimalPlacesWithoutRounding() {
        RawOrder input = new RawOrder(
                "ORDER-1002",
                " 100.5 ",
                "EUR",
                "2026-11-21T00:00:00Z",
                "false");

        TypedOrder result = converter.convert(input);

        assertEquals(new BigDecimal("100.50"), result.amount());
        assertFalse(result.priority());
    }
}
~~~

Những test này kiểm tra **kiểu và giá trị thực**, không chỉ kiểm tra DTO được tạo ra. Với `BigDecimal`, trong ví dụ scale 2 là một phần contract nên `assertEquals(new BigDecimal("100.50"),...)` có chủ ý.

### 14.2. Kiểm thử mã lỗi theo bảng dữ liệu

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.stream.Stream;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

class OrderTypeConverterInvalidInputTest {

    private final OrderTypeConverter converter =
            new OrderTypeConverter();

    static Stream<Arguments> invalidInputs() {
        return Stream.of(
                Arguments.of(
                        new RawOrder(" ", "1.00", "USD",
                                "2026-11-21T00:00:00Z", "true"),
                        "ORDER_ID_REQUIRED"),
                Arguments.of(
                        new RawOrder("A", null, "USD",
                                "2026-11-21T00:00:00Z", "true"),
                        "AMOUNT_REQUIRED"),
                Arguments.of(
                        new RawOrder("A", "1,000", "USD",
                                "2026-11-21T00:00:00Z", "true"),
                        "INVALID_AMOUNT_FORMAT"),
                Arguments.of(
                        new RawOrder("A", "0", "USD",
                                "2026-11-21T00:00:00Z", "true"),
                        "AMOUNT_MUST_BE_POSITIVE"),
                Arguments.of(
                        new RawOrder("A", "1.00", "JPY",
                                "2026-11-21T00:00:00Z", "true"),
                        "UNSUPPORTED_CURRENCY"),
                Arguments.of(
                        new RawOrder("A", "1.00", "USD",
                                "2026-11-21 09:30:00", "true"),
                        "INVALID_OCCURRED_AT"),
                Arguments.of(
                        new RawOrder("A", "1.00", "USD",
                                "2026-11-21T00:00:00Z", "yes"),
                        "INVALID_PRIORITY"));
    }

    @ParameterizedTest
    @MethodSource("invalidInputs")
    void rejectsInvalidConversions(
            RawOrder input, String expectedCode) {

        OrderConversionException exception =
                assertThrows(
                        OrderConversionException.class,
                        () -> converter.convert(input));

        assertEquals(expectedCode, exception.code());
    }
}
~~~

Đây là bài test cho **lỗi chuyển kiểu**, không phải Filter reject. Ngoài các trường hợp trên, nên bổ sung timestamp với phần thập phân/offset hợp lệ theo contract, số rất lớn, khoảng trắng Unicode, field thiếu và dữ liệu bị cắt ở adapter.

### 14.3. Kiểm tra tính tất định

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class ConverterDeterminismTest {

    @Test
    void sameInputProducesSameTypedValue() {
        OrderTypeConverter converter =
                new OrderTypeConverter();

        RawOrder raw = new RawOrder(
                "A", "10.00", "USD",
                "2026-11-21T00:00:00Z", "true");

        TypedOrder first = converter.convert(raw);

        for (int i = 0; i < 100; i++) {
            assertEquals(first, converter.convert(raw));
        }
    }
}
~~~

Test này kiểm tra một đặc tính mong muốn nhưng **không chứng minh** tuyệt đối code không có side effect. Cần code review để bảo đảm Converter không gọi clock/DB/API hoặc mutate input.

## 15. Integration test qua MessageChannel

Unit test chưa xác nhận Spring đã tạo endpoint và truyền metadata. Một integration test sẽ gửi `Message<RawOrder>` vào `orders.raw`, nhận `Message<TypedOrder>` từ `orders.typed`.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.time.Instant;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = OrderTransformerConfiguration.class)
class OrderTransformerFlowTest {

    @Autowired
    @Qualifier("orders.raw")
    MessageChannel raw;

    @Autowired
    @Qualifier("orders.typed")
    PollableChannel typed;

    @Test
    void transformsPayloadAndPreservesTracingHeaders() {
        RawOrder input = new RawOrder(
                " ORDER-1001 ",
                "1250.50",
                "USD",
                "2026-11-21T02:30:00Z",
                "true");

        Message<RawOrder> message =
                MessageBuilder.withPayload(input)
                        .setHeader("traceId", "trace-1001")
                        .setHeader(
                                "businessCorrelationId", "ORDER-1001")
                        .build();

        assertTrue(raw.send(message));

        Message<?> output = typed.receive(1000);
        assertNotNull(output);
        assertInstanceOf(TypedOrder.class, output.getPayload());

        TypedOrder result = (TypedOrder) output.getPayload();

        assertEquals("ORDER-1001", result.orderId());
        assertEquals(new BigDecimal("1250.50"), result.amount());
        assertEquals(CurrencyCode.USD, result.currency());
        assertEquals(
                Instant.parse("2026-11-21T02:30:00Z"),
                result.occurredAt());
        assertTrue(result.priority());

        assertEquals(
                "trace-1001", output.getHeaders().get("traceId"));
        assertEquals(
                "ORDER-1001",
                output.getHeaders().get("businessCorrelationId"));
    }

    @Test
    void malformedAmountDoesNotReachTypedOutput() {
        RawOrder invalid = new RawOrder(
                "ORDER-1002",
                "not-a-number",
                "USD",
                "2026-11-21T02:30:00Z",
                "true");

        RuntimeException failure = assertThrows(
                RuntimeException.class,
                () -> raw.send(
                        MessageBuilder.withPayload(invalid).build()));

        Throwable cause = failure;
        while (cause != null
                && !(cause instanceof OrderConversionException)) {
            cause = cause.getCause();
        }

        assertInstanceOf(OrderConversionException.class, cause);
        assertEquals(
                "INVALID_AMOUNT_FORMAT",
                ((OrderConversionException) cause).code());

        assertNull(typed.receive(0));
    }
}
~~~

**Lưu ý quan trọng:** ví dụ dùng `DirectChannel` đồng bộ. Test bắt exception ngay từ `raw.send(...)` là hợp lý trong topology này; khi chuyển sang executor/broker, lỗi xảy ra ở thread khác và test phải quan sát error flow/ack/dead-letter phù hợp.

### 15.1. Test flow khác test converter ở đâu?

| Unit test converter | Integration test Spring |
|---|---|
| Kiểm tra quy tắc parse và error code | Kiểm tra annotation, bean và channel wiring |
| Không cần context | Cần Spring context |
| Nhanh, bao phủ nhiều trường hợp biên | Kiểm tra propagation của payload/headers |
| Không phát hiện sai `outputChannel` | Phát hiện lỗi không có channel đích |
| Không biết exception bị framework bọc thế nào | Quan sát cause chain thực tế |

Khi mở rộng test suite, nên giữ channel fixture riêng, không chạy nhiều test ghi/đọc cùng queue trên một context chia sẻ ngoài chủ đích. Các kết quả nhận qua `QueueChannel` chỉ chứng minh endpoint đã chuyển message trong bộ nhớ, không chứng minh database/broker downstream hoàn tất.

## 16. Thiết kế một pipeline end-to-end thực tế

Một ứng dụng nhận đơn qua HTTP và Kafka. Hai adapter có đặc điểm giao thức khác nhau nhưng sau decode có thể đưa chung một `RawOrder` tới converter.

~~~mermaid
flowchart TB
    HTTP["HTTP inbound adapter"] --> HDEC["HTTP JSON decode / limits"]
    KAFKA["Kafka inbound adapter"] --> KDEC["Kafka deserialize / schema"]
    HDEC --> RAW["orders.raw: RawOrder"]
    KDEC --> RAW
    RAW --> TRANS["Type Transformer"]
    TRANS --> TYPED["orders.typed: TypedOrder"]
    TYPED --> VAL{"Typed validation"}
    VAL -->|Pass| ROUTE{"Router: priority"}
    VAL -->|Fail| REJECT["Business reject"]
    TRANS -->|Parse failure| ERROR["Conversion error flow"]
    ROUTE --> PRI["Priority service"]
    ROUTE --> STD["Standard service"]
~~~

Phân chia trách nhiệm:

- **HTTP adapter:** xác thực caller, giới hạn body, chuyển JSON và xử lý HTTP response/error mapping.
- **Kafka adapter:** deserialization, schema/version, consumer acknowledgment, retry/quarantine.
- **Transformer:** chuyển kiểu theo hợp đồng thuần, không biết dữ liệu đến từ HTTP hay Kafka.
- **Validator:** kiểm tra invariant của DTO có kiểu và quy tắc nghiệp vụ phù hợp.
- **Router:** chọn priority/standard theo dữ liệu đã được xác minh.
- **Handler:** thao tác DB, gọi API, chịu trách nhiệm transaction và idempotency.
- **Error flow:** phân loại parse failure, validation failure và transient infrastructure failure.

### 16.1. Xử lý lỗi khác nhau giữa HTTP và Kafka

Một `OrderConversionException("INVALID_AMOUNT_FORMAT")` ở HTTP có thể được ánh xạ thành phản hồi 400/422 theo contract API. Với Kafka, không có caller HTTP đang chờ; consumer cần quyết định offset/ack, retry, dead-letter topic hoặc quarantine. **Không mặc định một loại exception Spring Integration sẽ tự tạo HTTP status hay DLQ**.

Nếu cùng một Transformer được gọi từ hai nguồn, error handling **ở ranh giới nguồn** có thể khác nhau, còn converter và mã lỗi vẫn có thể dùng chung.

### 16.2. Khi nào nên parse rồi validate lại?

Sau khi converter tạo `TypedOrder`, có thể dùng Bean Validation hoặc custom validator để kiểm tra quan hệ giữa các trường, giới hạn domain và policy theo ngữ cảnh. Ví dụ: đơn priority có tối thiểu giá trị khác, currency chỉ áp dụng ở một vùng, hay occurredAt không được cách thời điểm nhận quá xa.

Với điều kiện phụ thuộc **thời điểm hiện tại**, không nên gọi clock bên trong converter nếu mục tiêu là chuyển kiểu tất định. Hãy đưa `receivedAt` vào một context có kiểm soát và đặt rule tại bước validation nghiệp vụ.

## 17. Những vấn đề về hiệu năng và dữ liệu lớn

Transformer thuần có thể chạy nhanh nhưng vẫn cần quản lý tài nguyên:

1. **Giới hạn dữ liệu trước parse.** Một chuỗi số dài hàng triệu chữ số không nên được phép đến `BigDecimal` converter mà không giới hạn kích thước ở adapter/schema.
2. **Pattern và formatter dùng lại có kiểm soát.** `Pattern` là immutable/thread-safe khi dùng để tạo matcher mới; `DateTimeFormatter` immutable, phù hợp để tái sử dụng.
3. **Không tạo HTTP/DB call trong converter.** Chuyển kiểu nên CPU-local và có thể test.
4. **Dùng immutable DTO.** Với collections hoặc nested objects mutable, cân nhắc defensive copy.
5. **Tránh parse lặp lại.** Khi đã có `TypedOrder`, downstream không cần `new BigDecimal(order.amount().toString())`.
6. **Thận trọng với timezone mặc định.** Phụ thuộc host timezone có thể thay đổi khi deploy sang container/region khác.
7. **Không tạo queue vô hạn.** Transformer không tự có backpressure. Với xử lý async, theo dõi độ dài hàng đợi, timeout và bộ nhớ.
8. **Không tự động retry parse failure cố định.** Giải phóng tài nguyên và đưa dữ liệu sai vào đường xử lý thích hợp.

Nếu payload rất lớn hoặc stream, cần thiết kế cơ chế xử lý theo lô/stream và giới hạn bộ nhớ riêng. Một Transformer trả một object duy nhất không tự làm giảm mọi chi phí parse hoặc serialization.

## 18. Observability: theo dõi conversion outcome

Nếu một nguồn dữ liệu đổi format, tỷ lệ lỗi chuyển kiểu thường tăng đột ngột. Cần đo cả **thành công**, **thất bại** và tác động tới downstream.

| Chỉ số | Ý nghĩa | Gợi ý |
|---|---|---|
| `conversion_success_total{flow}` | Số message chuyển kiểu thành công | Label flow có cardinality thấp |
| `conversion_failure_total{code}` | Số lỗi theo mã ổn định | Không dùng raw value làm label |
| `conversion_duration_seconds{flow}` | Latency của converter | So sánh trước/sau thay đổi |
| `typed_validation_rejected_total{rule}` | Lỗi nghiệp vụ sau conversion | Tách khỏi lỗi parse |
| `source_schema_version` | Version producer | Dùng để điều tra thay đổi hợp đồng |
| `traceId` / `eventId` | Truy vết message cụ thể | Đặt trong trace/log theo chính sách bảo mật |

### 18.1. Không log toàn bộ payload

Raw payload có thể chứa thông tin cá nhân, tài chính hoặc token. Khi conversion fail, nên log `errorCode`, field name, source/schema version và correlation, tránh ghi cả giá trị bị từ chối. Một số lỗi format có thể phát sinh từ injection hoặc data exfiltration; hãy sanitize nội dung được gửi tới log, dashboard và client.

### 18.2. Không biến observability thành side effect của pure converter

Để giữ converter thuần, ghi metric/log ở adapter Transformer hoặc advice/error handler, không gọi network/DB từ `parseAmount`. Nếu metrics backend lỗi, conversion vẫn nên có hành vi được xác định độc lập theo SLO của hệ thống.

## 19. Những lỗi thường gặp

### Lỗi 1 — Dùng double rồi chuyển sang BigDecimal

**Triệu chứng:** số tiền có nhiều chữ số thập phân không mong đợi, phép so sánh ngưỡng sai.

**Khắc phục:** tạo `BigDecimal` từ chuỗi gốc, kiểm soát grammar/scale/rounding policy.

### Lỗi 2 — Boolean.parseBoolean chấp nhận sai dưới dạng false

**Triệu chứng:** producer gửi `"yes"` hoặc `"1"` nhưng message bị hiểu là không ưu tiên.

**Khắc phục:** định nghĩa tập chuỗi hợp lệ, chuyển đổi nghiêm ngặt hoặc công bố rõ tập token mở rộng.

### Lỗi 3 — Parse timestamp thiếu timezone bằng timezone server

**Triệu chứng:** cùng dữ liệu tạo thời điểm khác nhau giữa môi trường local và cloud.

**Khắc phục:** yêu cầu offset/UTC hoặc truyền `ZoneId` đáng tin cậy theo hợp đồng, test nhiều múi giờ.

### Lỗi 4 — Dùng Transformer để nuốt input sai bằng null

**Triệu chứng:** `MessageTransformationException` hoặc message không tới nhánh mong đợi.

**Khắc phục:** throw lỗi chuyển kiểu có mã rõ ràng; nếu cần result theo luồng, dùng `ConversionOutcome` và Router; Filter dành cho message hợp lệ không phù hợp.

### Lỗi 5 — Message mới làm mất trace/correlation

**Triệu chứng:** payload chuyển đúng nhưng Gateway timeout hoặc log mất correlation.

**Khắc phục:** hiểu sự khác nhau giữa Transformer trả payload và trả Message; chủ động giữ headers phù hợp, test thật với `replyChannel` khi có Gateway.

### Lỗi 6 — Code tự convert JSON string mà không quản lý schema

**Triệu chứng:** thiếu field hoặc đổi tên field làm ra null/sai kiểu khó hiểu.

**Khắc phục:** dùng decoder/schema có contract, sau đó mới type Transformer; version payload khi producer thay đổi.

### Lỗi 7 — Retry lỗi cố định vô hạn

**Triệu chứng:** input `amountText="abc"` được gửi đi gửi lại, chiếm queue và CPU.

**Khắc phục:** phân loại non-retryable conversion failure, trả lỗi/quarantine, chỉ retry transient error có triển vọng hồi phục.

### Lỗi 8 — Kết hợp conversion với DB/API

**Triệu chứng:** unit test phụ thuộc network, retry tạo side effect trùng và lỗi conversion khó phân biệt timeout.

**Khắc phục:** tách converter thuần, enrichment service và handler nghiệp vụ thành các endpoint có chính sách lỗi riêng.

### Lỗi 9 — Dữ liệu sai được mặc định hóa âm thầm

**Triệu chứng:** currency trống thành USD, timestamp trống thành now, amount trống thành zero mà không có policy.

**Khắc phục:** chỉ áp dụng default khi contract công bố rõ và cần có thông tin nguồn/phiên bản, không tự bịa giá trị nghiệp vụ.

### Lỗi 10 — Validation sau conversion bị bỏ qua

**Triệu chứng:** parse thành công nhưng nghiệp vụ nhận một trạng thái không cho phép.

**Khắc phục:** sau type conversion vẫn có bước validation domain, kiểm tra authorization và invariants phụ thuộc trạng thái tại transaction phù hợp.

### Lỗi 11 — Sai tên channel hoặc hai endpoint tranh một DirectChannel

**Triệu chứng:** test converter xanh nhưng message không đến đúng nhánh trong runtime.

**Khắc phục:** test integration wiring, chọn một phương án @Transformer hoặc Java DSL cho cùng input; nhớ DirectChannel không phải broadcast.

### Lỗi 12 — Chuyển JSON number sang Double làm mất độ chính xác trước Transformer

**Triệu chứng:** `RawOrder` đã chứa biểu diễn số được tạo từ double, converter không thể khôi phục giá trị nguyên thủy.

**Khắc phục:** cấu hình JSON decoder phù hợp, ưu tiên string hoặc BigDecimal trong contract khi cần giữ giá trị tiền tệ chính xác.

## 20. Bài thực hành

**Bối cảnh:** hệ thống nhận đơn hàng qua HTTP và Kafka; hai nguồn giải mã thành `RawOrder`. Trước khi routing, payload phải được chuẩn hóa thành `TypedOrder`.

### Bài 1 — Conversion cơ bản

Tạo hai record `RawOrder` và `TypedOrder`, enum `CurrencyCode`, `OrderConversionException` cùng `OrderTypeConverter`. Viết test cho dữ liệu:

~~~text
" ORDER-1001 ", "1250.50", "usd",
"2026-11-21T02:30:00Z", "TRUE"
~~~

Xác nhận orderId được trim, amount là `BigDecimal("1250.50")`, currency `USD`, time đúng `Instant` và priority true.

### Bài 2 — Dữ liệu sai có mã lỗi

Kiểm thử các trường: amount bằng 0, âm, dùng dấu phẩy, hơn hai chữ số thập phân, currency không hỗ trợ, thời gian thiếu timezone và priority là `"yes"`. Assert mã lỗi ổn định.

### Bài 3 — Annotation Transformer

Cấu hình `orders.raw` → `OrderTransformer` → `orders.typed`. Gửi một `Message<RawOrder>` có `traceId` và `businessCorrelationId`. Assert payload output đúng kiểu và headers vẫn có mặt.

### Bài 4 — Java DSL

Viết lại pipeline bằng `.transform(RawOrder.class, converter::convert)`, không đăng ký hai consumer trên cùng DirectChannel. So sánh kết quả integration test với cấu hình annotation.

### Bài 5 — Error flow

Gửi input `amountText="bad"`; với DirectChannel, quan sát exception và cause chain. Chuyển sang ExecutorChannel hoặc inbound broker adapter rồi thiết kế cách nhận `ErrorMessage`/reject phù hợp. Giải thích vì sao lỗi cố định không nên retry.

### Bài 6 — Chuyển đổi timezone

Cho phép thêm chuỗi ngày giờ địa phương từ một producer riêng, kèm field timezone. Viết conversion tường minh qua `ZoneId` và test trường hợp timezone không hợp lệ, daylight-saving gap/overlap ở vùng có DST.

### Bài 7 — ConversionService tùy chỉnh

Viết `Converter<RawOrder, TypedOrder>` dựa trên `OrderTypeConverter` và đăng ký vào service theo phạm vi phù hợp. Kiểm tra những nơi khác dùng service có thể chuyển đổi hay không; thảo luận tác động của đăng ký converter toàn cục.

### Bài 8 — Kết hợp Router và Filter

Sau `TypedOrder`, dùng Router tách `priority=true` khỏi nhánh thường và Filter loại những event không thuộc một chương trình khuyến mại. Assert các endpoint không phải parse string lại.

### Bài 9 — Header propagation

Tạo một Transformer trả `TypedOrder` payload, một Transformer khác trả `Message<TypedOrder>`. So sánh headers, đặc biệt `traceId`, `replyChannel` và `businessCorrelationId`. Bổ sung một Gateway chờ reply để kiểm tra hành vi thực tế.

### Bài 10 — Thay đổi schema có phiên bản

Producer v2 thêm currency mới hoặc thay biểu diễn priority thành `"1"/"0"`. Thiết kế cách version hóa converter hoặc chuyển đổi trước, bảo đảm dữ liệu v1 không bị hiểu sai âm thầm.

### Câu hỏi tự kiểm tra

1. Transformer khác decoder JSON và Filter như thế nào?
2. Vì sao nên dùng `BigDecimal` trực tiếp từ chuỗi thay vì parse `double`?
3. `Boolean.parseBoolean("yes")` trả gì, và vì sao điều đó có thể nguy hiểm?
4. Khi một timestamp không có timezone, còn thiếu thông tin nào để tạo `Instant`?
5. Vì sao một Converter được đăng ký toàn cục có thể tác động đến nhiều flow?
6. Nếu method @Transformer trả null, có được hiểu là Filter reject không?
7. Transformer trả payload khác trả `Message<?>` về header propagation thế nào?
8. Lỗi `INVALID_AMOUNT_FORMAT` có nên retry nhiều lần không?
9. Vì sao unit test converter chưa chứng minh channel đích tồn tại?
10. Khi một message qua Transformer, metadata nào giúp truy vết và giữ request–reply?
11. Vì sao không nên dùng giá trị default "USD" cho currency thiếu nếu hợp đồng chưa quy định?
12. Nếu dữ liệu đã sai do JSON decoder chuyển sang Double, Transformer có thể khôi phục tính chính xác không?
13. Làm sao đo conversion failure mà không lộ toàn bộ raw payload?
14. Khi có Splitter/Aggregator, việc đổi payload có ảnh hưởng tới correlation/sequence metadata không?

## 21. Checklist thiết kế

- [ ] Đã xác định contract đầu vào và DTO có kiểu đầu ra.
- [ ] Decode/validation tối thiểu được thực hiện trước Transformer theo ranh giới tin cậy.
- [ ] Amount dùng BigDecimal, có grammar, scale và rounding policy rõ ràng.
- [ ] Boolean và enum chỉ nhận các token được công bố.
- [ ] Timestamp có offset/timezone rõ hoặc có quy tắc `ZoneId` tường minh.
- [ ] Không có biến đổi âm thầm từ dữ liệu sai sang default nghiệp vụ.
- [ ] Converter thuần, không DB/API/clock/side effect.
- [ ] Exception chuyển kiểu có mã ổn định, không tiết lộ raw input nhạy cảm.
- [ ] Chọn một kiểu @Transformer hoặc Java DSL phù hợp, wiring channel rõ ràng.
- [ ] Không dùng return null để Filter message.
- [ ] Hiểu payload return và full Message return cùng quy tắc header propagation.
- [ ] Đã kiểm thử traceId/correlation/replyChannel cần thiết.
- [ ] Lỗi dữ liệu cố định không retry vô hạn; lỗi hạ tầng dùng retry có giới hạn.
- [ ] Có unit tests, parameterized tests và integration tests.
- [ ] Các consumer downstream nhận `TypedOrder`, không parse String lại.
- [ ] Có monitoring cho success, conversion failure, latency và schema changes.
- [ ] Khi qua broker/store, đã xem xét serialization và giới hạn trust boundary.
- [ ] Có phương án versioning khi producer thay đổi định dạng.

## 22. Tổng kết

**Chuyển đổi kiểu dữ liệu** là một trách nhiệm tự nhiên của **Transformer** trong Spring Integration. Một raw payload có thể chứa những chuỗi mô tả tiền tệ, thời gian và cờ logic; Transformer chuyển chúng thành `BigDecimal`, `Instant`, enum và boolean theo **hợp đồng rõ ràng**, để các bước Filter/Router/Service Activator phía sau không phải lặp lại parse hoặc chấp nhận dữ liệu mơ hồ.

Cách tiếp cận thực tế là: **decode ở ranh giới giao thức → converter Java thuần → @Transformer hoặc Java DSL → validation nghiệp vụ → routing/processing**. Hãy phân biệt lỗi chuyển đổi với rejection bình thường, bảo toàn metadata phù hợp, dùng idempotency ở những handler có side effect và kiểm thử qua channel thật. Nhờ đó module **SPRING_INTEGRATION_PATTERN** có thể kết hợp Transformer với Gateway, Router, Filter, Splitter/Aggregator, retry và error channel trong luồng dễ kiểm soát, dễ mở rộng và dễ quan sát.

### Tài liệu tham khảo

- Spring Integration Reference — Transformer: https://docs.spring.io/spring-integration/reference/transformer.html
- Spring Integration Reference — Java DSL: https://docs.spring.io/spring-integration/reference/dsl.html
- Spring Integration API — `@Transformer`: https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/Transformer.html
- Spring Framework Reference — Spring Type Conversion: https://docs.spring.io/spring-framework/reference/core/validation/convert.html
- Spring Framework API — ConversionService: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/ConversionService.html
- Spring Framework API — Converter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/converter/Converter.html
- Java SE API — BigDecimal: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html
- Java SE API — Instant: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html
- JUnit 5 User Guide — Parameterized Tests: https://junit.org/junit5/docs/current/user-guide/#writing-tests-parameterized-tests

