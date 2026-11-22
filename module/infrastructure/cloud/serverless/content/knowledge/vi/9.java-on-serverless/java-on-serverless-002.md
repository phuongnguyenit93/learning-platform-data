# Ánh xạ event thành DTO và kiểm soát serialization

Trong chương **Java trên serverless**, function thường nhận dữ liệu từ nhiều nguồn như HTTP API, queue, event bus, object storage hoặc scheduler. Mỗi nguồn có thể có cấu trúc request riêng, nhưng phần nghiệp vụ Java cần làm việc với các kiểu dữ liệu ổn định và dễ kiểm tra. Việc chuyển event thành DTO (Data Transfer Object) là ranh giới giúp tách định dạng của nền tảng khỏi mô hình ứng dụng.

Serialization là quá trình chuyển đối tượng Java thành định dạng có thể truyền hoặc lưu trữ, chẳng hạn JSON. Deserialization là quá trình đọc định dạng đó và tạo lại đối tượng Java. Nếu không kiểm soát hai chiều này, một thay đổi nhỏ ở tên trường, kiểu ngày giờ, enum hoặc null có thể khiến function lỗi khi nhận message, hoặc phát ra payload mà consumer khác không đọc được.

Bài học thuộc module **CLOUD_SERVERLESS**, tập trung vào phát triển và triển khai ứng dụng serverless, đặc biệt là Java function kích hoạt bởi HTTP, thông điệp hoặc sự kiện. Khi triển khai FaaS, cần thiết kế DTO và serialization sao cho tương thích với trigger, xử lý được dữ liệu không hợp lệ, hỗ trợ phiên bản hợp đồng và không làm lộ dữ liệu nhạy cảm trong log. Những quyết định này ảnh hưởng trực tiếp đến retry, idempotency, cold start và khả năng mở rộng.

Các ví dụ Java trong bài dùng record, text block và switch expression, vì vậy giả định runtime Java 17 trở lên. Jackson cần phiên bản hỗ trợ record (từ 2.12); module xử lý ngày giờ được cung cấp bởi gói jackson-datatype-jsr310. Nếu dự án dùng runtime cũ hơn, cần đổi DTO và cú pháp tương ứng, đồng thời kiểm tra ma trận tương thích của thư viện.

## 1. Vì sao cần ánh xạ event thành DTO?

Event từ nền tảng thường chứa cả thông tin vận chuyển và dữ liệu nghiệp vụ. Ví dụ, một HTTP request có method, headers, path, query parameters và body. Một message từ queue có message ID, receipt handle, thời điểm nhận, số lần giao và body. Một event từ object storage có bucket, object key, kích thước và metadata.

Logic nghiệp vụ thường chỉ cần một phần dữ liệu đó. Nếu domain service nhận trực tiếp kiểu event của nhà cung cấp, nó sẽ phụ thuộc vào cấu trúc transport và khó kiểm thử ngoài môi trường FaaS.

DTO tạo ra một hợp đồng rõ ràng ở ranh giới ứng dụng:

- Adapter nhận event từ trigger.
- Deserializer chuyển JSON hoặc payload thành kiểu DTO phù hợp.
- Validator kiểm tra cấu trúc và quy tắc dữ liệu đầu vào.
- Mapper chuyển DTO thành command hoặc mô hình nội bộ.
- Use case thực hiện nghiệp vụ.
- Response mapper hoặc serializer tạo kết quả trả về hoặc event phát đi.

~~~mermaid
flowchart LR
    T["HTTP / Queue / Event"] --> A["Trigger adapter"]
    A --> E["Envelope / raw payload"]
    E --> D["Deserializer"]
    D --> V["DTO validation"]
    V --> M["Mapper"]
    M --> C["Command / use case"]
    C --> R["Business result"]
    R --> S["Serializer"]
    S --> O["HTTP response / outgoing event"]
~~~

Tách các bước giúp xác định lỗi nằm ở đâu. JSON sai cú pháp là lỗi parse; thiếu trường bắt buộc là lỗi hợp đồng; giá trị hợp lệ về kiểu nhưng vi phạm quy tắc như quantity âm là lỗi validation nghiệp vụ; lỗi khi lưu dữ liệu là lỗi xử lý. Mỗi loại lỗi có chính sách retry và phản hồi khác nhau.

## 2. Phân biệt event envelope, payload và DTO

Không nên coi toàn bộ event là một DTO nghiệp vụ duy nhất. Một event có thể có ba lớp:

| Lớp | Nội dung | Ví dụ |
|---|---|---|
| Transport wrapper | Metadata do HTTP, queue hoặc nền tảng cung cấp | headers, messageId, receiptHandle |
| Event envelope | Ngữ cảnh chung của sự kiện | id, source, type, time |
| Business payload | Dữ liệu riêng của sự kiện | orderId, customerId, lines |

DTO có thể đại diện cho envelope, payload hoặc một request/response cụ thể. Nên đặt tên theo vai trò để tránh nhầm lẫn, ví dụ **CloudEventEnvelope<OrderPlacedData>**, **OrderPlacedData**, **PlaceOrderRequest** và **PlaceOrderCommand**.

Ví dụ JSON event:

~~~json
{
  "specversion": "1.0",
  "id": "evt-1001",
  "source": "urn:example:orders",
  "type": "com.example.orders.order-placed",
  "time": "2026-11-17T10:15:30Z",
  "data": {
    "orderId": "ORD-1001",
    "customerId": "CUS-2001",
    "totalAmount": 1250000,
    "currency": "VND"
  }
}
~~~

Envelope mô tả sự kiện và nguồn phát. Object data là payload nghiệp vụ. Java có thể biểu diễn hai phần bằng hai DTO riêng:

~~~java
import java.time.Instant;

public record EventEnvelope<T>(
        String specversion,
        String id,
        String source,
        String type,
        Instant time,
        T data) {
}

public record DetailedOrderPlacedData(
        String orderId,
        String customerId,
        long totalAmount,
        String currency) {
}
~~~

Kiểu generic **EventEnvelope<T>** cho phép tái sử dụng cấu trúc envelope với nhiều payload. Khi deserialize, cần cung cấp đầy đủ kiểu generic cho Jackson; nếu chỉ truyền **EventEnvelope.class**, phần data có thể được tạo thành **Map** thay vì **DetailedOrderPlacedData**.

Trong hệ thống dùng CloudEvents, cần tuân thủ đúng thuộc tính và binding của CloudEvents. DTO trên chỉ là ví dụ envelope nội bộ rút gọn, không phải một implementation đầy đủ của đặc tả.

## 3. DTO nên phản ánh hợp đồng, không phản ánh cấu trúc database

DTO dùng để trao đổi dữ liệu ở ranh giới. Nó không nhất thiết giống entity trong database hoặc domain model.

Ví dụ payload nhận từ API:

~~~json
{
  "customerId": "CUS-2001",
  "items": [
    {
      "sku": "SKU-01",
      "quantity": 2
    }
  ],
  "requestedDeliveryDate": "2026-11-20"
}
~~~

DTO Java:

~~~java
import java.time.LocalDate;
import java.util.List;

public record PlaceOrderRequest(
        String customerId,
        List<OrderItemRequest> items,
        LocalDate requestedDeliveryDate) {
}

public record OrderItemRequest(
        String sku,
        int quantity) {
}
~~~

Domain model có thể dùng kiểu khác:

~~~java
public record PlaceOrderCommand(
        CustomerId customerId,
        List<OrderLine> lines,
        DeliveryDate requestedDeliveryDate) {
}
~~~

Mapper chuyển DTO sang command sau khi xác thực:

~~~java
public final class PlaceOrderMapper {
    public PlaceOrderCommand toCommand(PlaceOrderRequest request) {
        return new PlaceOrderCommand(
                new CustomerId(request.customerId()),
                request.items().stream()
                        .map(item -> new OrderLine(
                                new ProductSku(item.sku()),
                                item.quantity()))
                        .toList(),
                new DeliveryDate(request.requestedDeliveryDate()));
    }
}
~~~

Các kiểu **CustomerId**, **OrderLine**, **ProductSku** và **DeliveryDate** ở ví dụ là domain type minh họa. Ý chính là DTO chịu trách nhiệm biểu diễn hợp đồng truyền nhận; domain model chịu trách nhiệm bảo vệ quy tắc nghiệp vụ.

Không nên đưa entity JPA hoặc object có quan hệ lazy-loading trực tiếp vào event. Làm vậy có thể vô tình serialize trường nội bộ, vòng tham chiếu, proxy ORM hoặc dữ liệu nhạy cảm. Hãy tạo DTO rõ trường được phép công bố.

## 4. Chọn kiểu dữ liệu Java phù hợp

Kiểu dữ liệu trong DTO quyết định JSON được đọc và ghi như thế nào. Chọn kiểu quá rộng hoặc không phù hợp có thể gây mất độ chính xác, sai múi giờ hoặc khó xử lý giá trị thiếu.

| Dữ liệu | Kiểu Java nên cân nhắc | Lưu ý |
|---|---|---|
| Định danh dạng chuỗi | **String** hoặc value object | Kiểm tra định dạng và độ dài |
| Số lượng nguyên | **int**, **long** hoặc wrapper | Chọn giới hạn phù hợp; wrapper phân biệt null |
| Tiền và số thập phân chính xác | **BigDecimal** | Tránh **double** cho giá trị tiền |
| Ngày không có giờ | **LocalDate** | JSON thường dùng yyyy-MM-dd |
| Thời điểm tuyệt đối | **Instant** | Nên biểu diễn UTC |
| Ngày giờ có offset | **OffsetDateTime** | Giữ offset nếu hợp đồng cần |
| Danh sách | **List<T>** | Kiểm tra null, rỗng và kích thước |
| Giá trị có thể vắng mặt | Wrapper, **Optional<T>** hoặc quy ước riêng | Phân biệt missing và null |
| Trạng thái hữu hạn | **enum** hoặc chuỗi có kiểm soát | Có chính sách khi xuất hiện giá trị mới |

### 4.1. Tiền tệ và số thập phân

Không dùng **double** hoặc **float** để biểu diễn số tiền cần độ chính xác thập phân. Các kiểu dấu phẩy động nhị phân không biểu diễn chính xác mọi số thập phân.

Dùng **BigDecimal**:

~~~java
import java.math.BigDecimal;

public record PaymentData(
        String paymentId,
        BigDecimal amount,
        String currency) {
}
~~~

Trong JSON, amount có thể được biểu diễn bằng số:

~~~json
{
  "paymentId": "PAY-01",
  "amount": 1250000.50,
  "currency": "VND"
}
~~~

Hợp đồng cần quy định currency, scale, cách làm tròn và đơn vị. Một số hệ thống chọn gửi amount dưới dạng chuỗi thập phân để tránh client ở nền tảng khác tự chuyển sang kiểu dấu phẩy động. Nếu dùng chuỗi, schema phải mô tả rõ định dạng và consumer phải parse có kiểm soát.

### 4.2. Ngày và thời gian

**LocalDate** phù hợp với ngày lịch như ngày giao hàng. **Instant** phù hợp với thời điểm xảy ra event. Không dùng **LocalDateTime** cho một thời điểm toàn cầu nếu payload không có múi giờ hoặc offset, vì consumer không thể xác định chính xác thời điểm đó ở đâu.

Ví dụ:

~~~java
import java.time.Instant;
import java.time.LocalDate;

public record ShipmentEvent(
        String shipmentId,
        LocalDate deliveryDate,
        Instant createdAt) {
}
~~~

JSON tương ứng:

~~~json
{
  "shipmentId": "SHP-1001",
  "deliveryDate": "2026-11-20",
  "createdAt": "2026-11-17T10:15:30Z"
}
~~~

Khi dùng Jackson, cần đăng ký **JavaTimeModule** để serialize/deserialize các kiểu **java.time**. Nên thống nhất ISO-8601 và UTC cho thời điểm xuyên hệ thống.

### 4.3. Primitive và wrapper

**int** không thể nhận null. Nếu JSON không có trường quantity, Jackson có thể gán giá trị mặc định 0 cho primitive tùy cấu hình. Điều đó làm mất khác biệt giữa “người gửi không cung cấp” và “người gửi gửi 0”.

Nếu trường bắt buộc, hãy kiểm tra presence hoặc dùng wrapper **Integer** kết hợp validation. Nếu 0 là giá trị hợp lệ và trường phải luôn có mặt, cần cấu hình deserialization/validation để phát hiện trường bị thiếu.

Lưu ý: **FAIL_ON_NULL_FOR_PRIMITIVES** chỉ làm Jackson từ chối giá trị null tường minh cho primitive; nó không tự phát hiện một thuộc tính primitive bị lược khỏi JSON. Trường hợp bị thiếu có thể nhận giá trị mặc định của Java, chẳng hạn 0. Nếu cần phân biệt missing với 0, dùng wrapper và validation, hoặc theo dõi presence bằng custom deserializer/DTO chuyên biệt.

## 5. Cấu hình Jackson cho Java serverless

Jackson là thư viện phổ biến để xử lý JSON trong Java. **ObjectMapper** thực hiện serialization và deserialization. Trong ứng dụng serverless, nên cấu hình mapper một lần trong quá trình khởi tạo environment và tái sử dụng qua các invocation.

Ví dụ cấu hình:

~~~java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

public final class Json {
    private static final ObjectMapper MAPPER = createMapper();

    private Json() {
    }

    private static ObjectMapper createMapper() {
        ObjectMapper mapper = new ObjectMapper();

        mapper.registerModule(new JavaTimeModule());
        mapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);

        mapper.enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
        mapper.enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES);

        return mapper;
    }

    public static ObjectMapper mapper() {
        return MAPPER;
    }
}
~~~

Cấu hình trên là một chính sách minh họa cho hợp đồng chặt chẽ. Trong hệ thống cần tương thích với producer có thể bổ sung trường, có thể cho phép bỏ qua trường chưa biết ở một số DTO. Quyết định đó cần được áp dụng có chủ đích, không bật/tắt tùy tiện trong từng handler.

**ObjectMapper** nên được cấu hình xong trước khi dùng đồng thời. Sau khi được sử dụng, không thay đổi cấu hình toàn cục giữa các invocation. Nếu cần chính sách khác nhau, tạo mapper hoặc **ObjectReader**/**ObjectWriter** riêng trước khi dùng.

### 5.1. Deserialize JSON thành DTO

~~~java
String json = """
        {
          "customerId": "CUS-2001",
          "items": [
            {"sku": "SKU-01", "quantity": 2}
          ],
          "requestedDeliveryDate": "2026-11-20"
        }
        """;

PlaceOrderRequest request =
        Json.mapper().readValue(json, PlaceOrderRequest.class);
~~~

Nếu JSON không hợp lệ hoặc kiểu dữ liệu không tương thích, Jackson ném exception như **JsonProcessingException** hoặc một subtype. Adapter cần phân loại đây là lỗi payload, ghi log an toàn và trả phản hồi hoặc đưa message vào luồng lỗi theo trigger.

### 5.2. Serialize DTO thành JSON

~~~java
PlaceOrderRequest request = new PlaceOrderRequest(
        "CUS-2001",
        List.of(new OrderItemRequest("SKU-01", 2)),
        LocalDate.of(2026, 11, 20));

String json = Json.mapper().writeValueAsString(request);
~~~

Trong production, không nên log toàn bộ JSON nếu payload chứa dữ liệu cá nhân, token hoặc thông tin thanh toán. Nếu cần log, chỉ ghi metadata hoặc trường đã được lọc.

### 5.3. Hỗ trợ kiểu generic

Khi deserialize envelope có payload generic, dùng **TypeReference** để giữ thông tin kiểu:

~~~java
import com.fasterxml.jackson.core.type.TypeReference;

TypeReference<EventEnvelope<OrderPlacedData>> eventType =
        new TypeReference<>() {};

EventEnvelope<OrderPlacedData> event =
        Json.mapper().readValue(json, eventType);
~~~

Nếu chỉ dùng **EventEnvelope.class**, thông tin generic bị xóa ở runtime. Jackson có thể tạo **LinkedHashMap** cho data. Điều này buộc code phải ép kiểu thủ công và làm mất kiểm tra kiểu ở compile time.

## 6. Điều khiển tên trường JSON

Tên trường trong JSON có thể khác tên thuộc tính Java. Ví dụ producer dùng **order_id**, trong khi Java dùng **orderId**.

### 6.1. Dùng JsonProperty

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;

public record OrderPlacedDto(
        @JsonProperty("order_id") String orderId,
        @JsonProperty("customer_id") String customerId) {
}
~~~

**JsonProperty** xác định tên thuộc tính trong quá trình đọc và ghi JSON. Đây là cách rõ ràng khi một hợp đồng có tên trường cố định hoặc khác quy ước Java.

### 6.2. Dùng naming strategy

Nếu toàn bộ payload dùng snake_case, có thể cấu hình naming strategy:

~~~java
import com.fasterxml.jackson.databind.PropertyNamingStrategies;

ObjectMapper mapper = new ObjectMapper();
mapper.setPropertyNamingStrategy(
        PropertyNamingStrategies.SNAKE_CASE);
~~~

Khi đó **customerId** được ánh xạ sang **customer_id**. Naming strategy giúp giảm annotation lặp lại, nhưng cần tránh áp dụng toàn cục nếu cùng một function nhận nhiều hợp đồng với quy ước tên khác nhau.

### 6.3. Chấp nhận tên cũ bằng JsonAlias

Khi producer đang chuyển đổi tên trường, consumer có thể chấp nhận cả tên cũ và tên mới:

~~~java
import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonProperty;

public record CustomerDto(
        @JsonProperty("customerId")
        @JsonAlias({"customer_id", "clientId"})
        String customerId) {
}
~~~

**JsonProperty** xác định tên dùng khi serialize; **JsonAlias** cho phép nhận thêm tên khi deserialize. Alias hữu ích trong giai đoạn chuyển đổi, nhưng không nên giữ vô thời hạn nếu các producer đã được cập nhật.

## 7. Missing, null, empty và default

Một nguồn lỗi thường gặp là coi các trạng thái sau giống nhau:

- Trường không xuất hiện trong JSON.
- Trường xuất hiện với giá trị null.
- Trường xuất hiện với chuỗi rỗng "".
- Trường xuất hiện với danh sách rỗng [].
- Trường xuất hiện với giá trị mặc định như 0 hoặc false.

Các trạng thái này có thể mang ý nghĩa khác nhau. Ví dụ, với API cập nhật hồ sơ, trường không xuất hiện có thể nghĩa là “giữ nguyên giá trị cũ”, trong khi null có thể nghĩa là “xóa giá trị”. Nếu deserializer tự gán default, ứng dụng có thể ghi đè dữ liệu ngoài ý muốn.

Có thể biểu diễn rõ hơn bằng wrapper hoặc kiểu dữ liệu riêng. Với DTO đơn giản, dùng **Integer** thay cho **int** để phân biệt null với 0. Nếu cần phân biệt cả missing và null, cần dùng cơ chế theo dõi presence, custom deserializer hoặc kiểu wrapper có trạng thái như **Absent**, **Present(null)** và **Present(value)**.

Ví dụ kiểm tra trường bắt buộc:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Positive;
import jakarta.validation.Valid;
import java.util.List;

public record CreateOrderDto(
        @NotBlank String customerId,
        @NotEmpty List<@Valid OrderLineDto> lines) {
}

public record OrderLineDto(
        @NotBlank String sku,
        @Positive int quantity) {
}
~~~

Bean Validation có thể kiểm tra **@NotBlank**, **@NotEmpty**, **@Positive** và các ràng buộc tương tự. Ứng dụng cần gọi validator rõ ràng sau khi deserialize. Jackson chỉ tạo object; nó không tự thực thi đầy đủ quy tắc validation của ứng dụng.

## 8. Enum và giá trị mới từ producer

Enum giúp mô hình Java thể hiện một tập trạng thái hữu hạn:

~~~java
public enum OrderStatus {
    PENDING,
    CONFIRMED,
    CANCELLED
}

public record OrderStatusDto(
        String orderId,
        OrderStatus status) {
}
~~~

Tuy nhiên, producer có thể bổ sung trạng thái mới trước khi consumer được triển khai. Nếu Jackson không nhận ra giá trị enum, deserialization có thể thất bại và message bị retry liên tục.

Có một số cách xử lý:

1. **Strict enum:** Từ chối giá trị chưa biết. Phù hợp khi giá trị mới có thể làm thay đổi logic quan trọng và cần cập nhật consumer trước.
2. **Default enum value:** Dùng **@JsonEnumDefaultValue** cùng cấu hình **READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE**. Chỉ an toàn khi có trạng thái UNKNOWN và logic xử lý nó rõ ràng.
3. **Giữ giá trị dưới dạng String:** Chuyển thành enum hoặc domain value sau khi kiểm tra. Cách này hữu ích khi consumer cần lưu hoặc chuyển tiếp giá trị chưa biết.

Ví dụ với giá trị mặc định:

~~~java
import com.fasterxml.jackson.annotation.JsonEnumDefaultValue;

public enum OrderStatus {
    PENDING,
    CONFIRMED,
    CANCELLED,

    @JsonEnumDefaultValue
    UNKNOWN
}
~~~

Cấu hình:

~~~java
mapper.enable(
        DeserializationFeature.READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE);
~~~

Không nên âm thầm biến mọi trạng thái chưa biết thành PENDING hoặc CONFIRMED. Giá trị mặc định phải phản ánh rõ “consumer chưa hiểu trạng thái này” và tránh tạo quyết định nghiệp vụ sai.

## 9. DTO lồng nhau, collection và generic payload

Event thường chứa danh sách hoặc object lồng nhau. Hãy khai báo kiểu cụ thể để compiler và validator hỗ trợ kiểm tra.

~~~java
import java.math.BigDecimal;
import java.util.List;

public record OrderPlacedData(
        String orderId,
        String customerId,
        List<OrderLineData> lines,
        BigDecimal totalAmount,
        String currency) {
}

public record OrderLineData(
        String productId,
        int quantity,
        BigDecimal unitPrice) {
}
~~~

Khi deserialize:

~~~java
OrderPlacedData data =
        Json.mapper().readValue(json, OrderPlacedData.class);
~~~

Nếu payload là danh sách top-level, dùng **TypeReference<List<OrderPlacedData>>**:

~~~java
List<OrderPlacedData> orders = Json.mapper().readValue(
        json,
        new TypeReference<List<OrderPlacedData>>() {});
~~~

Tránh dùng **List<Object>** hoặc **Map<String, Object>** làm mô hình chính cho hợp đồng đã biết. Các kiểu động phù hợp cho metadata linh hoạt, nhưng payload nghiệp vụ nên có DTO cụ thể để kiểm soát schema và lỗi kiểu.

## 10. Custom serializer và deserializer

Đôi khi hợp đồng ngoài dùng định dạng khác với kiểu Java mong muốn. Ví dụ, producer gửi mã tiền tệ dạng số, nhưng ứng dụng muốn dùng enum **CurrencyCode**; hoặc timestamp có định dạng riêng.

Có thể dùng custom deserializer để chuyển đổi:

~~~java
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JsonDeserializer;
import java.io.IOException;

public final class CurrencyCodeDeserializer
        extends JsonDeserializer<CurrencyCode> {

    @Override
    public CurrencyCode deserialize(
            JsonParser parser,
            DeserializationContext context) throws IOException {

        String value = parser.getValueAsString();

        try {
            return CurrencyCode.valueOf(value);
        } catch (IllegalArgumentException failure) {
            return (CurrencyCode) context.handleWeirdStringValue(
                    CurrencyCode.class,
                    value,
                    "Unsupported currency code");
        }
    }
}
~~~

Gắn deserializer vào DTO:

~~~java
import com.fasterxml.jackson.databind.annotation.JsonDeserialize;

public record PaymentDto(
        String paymentId,
        @JsonDeserialize(using = CurrencyCodeDeserializer.class)
        CurrencyCode currency) {
}
~~~

Custom serializer cũng có thể dùng để định dạng giá trị khi phát event. Tuy nhiên, không nên viết serializer riêng nếu Jackson đã hỗ trợ kiểu dữ liệu theo chuẩn. Logic chuyển đổi cần có kiểm thử, xử lý lỗi rõ và không phụ thuộc trạng thái mutable toàn cục.

## 11. Polymorphic event và lựa chọn handler theo type

Một subscription có thể nhận nhiều loại event. Ví dụ OrderPlaced, OrderCancelled và PaymentSucceeded có payload khác nhau. Có thể dùng **type** của envelope để chọn DTO và handler.

Cách rõ ràng là dispatch bằng registry:

~~~java
public final class EventDispatcher {
    private final OrderPlacedHandler orderPlacedHandler;
    private final OrderCancelledHandler orderCancelledHandler;

    public EventDispatcher(
            OrderPlacedHandler orderPlacedHandler,
            OrderCancelledHandler orderCancelledHandler) {
        this.orderPlacedHandler = orderPlacedHandler;
        this.orderCancelledHandler = orderCancelledHandler;
    }

    public void dispatch(String type, JsonNode data) throws Exception {
        switch (type) {
            case "com.example.orders.order-placed" -> {
                OrderPlacedData dto = Json.mapper().treeToValue(
                        data, OrderPlacedData.class);
                orderPlacedHandler.handle(dto);
            }
            case "com.example.orders.order-cancelled" -> {
                OrderCancelledData dto = Json.mapper().treeToValue(
                        data, OrderCancelledData.class);
                orderCancelledHandler.handle(dto);
            }
            default -> throw new UnsupportedOperationException(
                    "Unsupported event type: " + type);
        }
    }
}
~~~

Ví dụ trên giả định **JsonNode** đã được import từ Jackson và envelope đã được xác thực. Registry có thể được xây dựng bằng map từ type đến handler để dễ mở rộng.

Không nên bật Jackson default typing cho payload không đáng tin cậy hoặc để JSON chỉ định trực tiếp tên class Java cần khởi tạo. Việc deserialize class tùy ý có thể tạo rủi ro bảo mật. Nếu dùng polymorphic deserialization, cần allowlist type rõ ràng và kiểm soát nguồn dữ liệu. Với event bus, dispatch theo type đã đăng ký thường dễ kiểm soát hơn.

## 12. Ánh xạ event theo từng trigger

Cùng một payload nghiệp vụ có thể đến từ các trigger khác nhau, nhưng wrapper bên ngoài thường khác nhau.

### 12.1. HTTP trigger

Một HTTP adapter có thể nhận request body và headers:

~~~java
public record HttpEvent(
        String method,
        Map<String, String> headers,
        String body,
        String requestId) {
}
~~~

Handler parse body thành DTO:

~~~java
public final class PlaceOrderHttpHandler {
    private final PlaceOrderUseCase useCase;

    public PlaceOrderHttpHandler(PlaceOrderUseCase useCase) {
        this.useCase = useCase;
    }

    public HttpResponse handle(HttpEvent event) throws Exception {
        PlaceOrderRequest request = Json.mapper().readValue(
                event.body(), PlaceOrderRequest.class);

        // Validation và mapping được thực hiện trước use case.
        PlaceOrderCommand command = mapAndValidate(request);
        PlaceOrderResult result = useCase.execute(command);

        return new HttpResponse(
                201,
                Json.mapper().writeValueAsString(result));
    }
}
~~~

Các kiểu **HttpResponse**, **PlaceOrderUseCase**, **PlaceOrderCommand** và **PlaceOrderResult** là kiểu minh họa. Trong một nền tảng cụ thể, adapter phải dùng đúng request/response class và quy ước mã HTTP. Cần kiểm tra body rỗng, Content-Type, kích thước payload, encoding và xác thực danh tính trước khi gọi nghiệp vụ.

### 12.2. Queue trigger

Message từ queue thường có wrapper chứa metadata vận chuyển và body:

~~~java
public record QueueRecord(
        String messageId,
        String body,
        int receiveCount,
        String sentTimestamp) {
}
~~~

Body được parse thành DTO riêng:

~~~java
public void handle(QueueRecord record) throws Exception {
    OrderPlacedData eventData = Json.mapper().readValue(
            record.body(), OrderPlacedData.class);

    orderPlacedUseCase.processOnce(
            record.messageId(),
            eventData);
}
~~~

Trong thực tế, nếu body chứa CloudEvent thì phải parse envelope trước, sau đó parse **data**. Không được giả định mọi queue đều đặt payload trực tiếp trong body. Một số nền tảng có thể bọc message trong một event object khác hoặc mã hóa body dưới dạng Base64.

### 12.3. Event bus hoặc stream

Với event bus, function có thể nhận một batch record. Mỗi record có thể có **source**, **detail-type**, **detail** hoặc cấu trúc tương đương tùy nền tảng.

Adapter cần chuyển cấu trúc provider-specific sang mô hình nội bộ:

~~~java
public record NormalizedEvent(
        String eventId,
        String source,
        String type,
        Instant time,
        JsonNode payload) {
}
~~~

Sau đó dispatcher ánh xạ **type** và payload sang DTO cụ thể. Cách này giúp use case không phụ thuộc tên trường của event wrapper do nhà cung cấp quy định.

## 13. Kiểm soát unknown properties và schema evolution

Khi producer thêm trường mới, consumer cũ có thể nhận payload có thuộc tính chưa biết. Chính sách **FAIL_ON_UNKNOWN_PROPERTIES** quyết định Jackson có từ chối hay bỏ qua các trường đó.

Có hai lựa chọn thường gặp:

| Chính sách | Hành vi | Phù hợp khi |
|---|---|---|
| Strict | Từ chối thuộc tính chưa biết | Hợp đồng đóng, cần phát hiện thay đổi ngay |
| Tolerant | Bỏ qua thuộc tính chưa biết | Hợp đồng cho phép mở rộng thêm trường tương thích |

Tolerant không có nghĩa là bỏ qua mọi thay đổi. Nếu producer đổi kiểu của một trường đã biết hoặc đổi ý nghĩa nghiệp vụ, consumer vẫn có thể lỗi hoặc xử lý sai.

Có thể cho phép unknown properties trên một DTO cụ thể:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record CustomerUpdatedEvent(
        String customerId,
        String displayName) {
}
~~~

Không nên bật tolerant toàn cục mà không có kiểm thử. Các trường quan trọng như amount, currency, tenantId hoặc authorization context phải được kiểm tra rõ. Một trường lạ có thể là dấu hiệu producer gửi nhầm loại event hoặc phiên bản payload không tương thích.

### 13.1. Quy tắc thay đổi schema

Thường có thể thêm trường tùy chọn mới nếu consumer cũ bỏ qua được. Các thay đổi như xóa trường bắt buộc, đổi kiểu dữ liệu, đổi đơn vị hoặc thay đổi ngữ nghĩa thường phá vỡ tương thích.

Quản lý phiên bản có thể dùng:

- Version trong **dataschema**.
- Event type mới cho một hợp đồng mới.
- Trường **schemaVersion** trong payload theo quy ước nội bộ.
- Consumer hỗ trợ nhiều phiên bản trong giai đoạn chuyển đổi.

Không thay đổi ý nghĩa của event nhưng giữ nguyên type. Nếu **OrderPlaced** trước đây có nghĩa đơn đã được ghi nhận, không nên dùng lại type đó cho trạng thái đơn đã thanh toán.

## 14. Validation: parse được chưa có nghĩa là dữ liệu hợp lệ

Deserialization chỉ chứng minh JSON có thể được chuyển thành object theo kiểu Java. Nó không bảo đảm dữ liệu đáp ứng quy tắc nghiệp vụ.

Có thể chia validation thành ba lớp:

1. **Cấu trúc:** JSON đúng cú pháp, field có kiểu phù hợp, envelope có các thuộc tính cần thiết.
2. **Dữ liệu:** chuỗi không rỗng, số nằm trong giới hạn, danh sách có kích thước hợp lý, ngày tháng hợp lệ.
3. **Nghiệp vụ:** khách hàng tồn tại, đơn có thể được đặt, trạng thái cho phép chuyển đổi, số lượng còn khả dụng.

Ví dụ Bean Validation:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Positive;
import java.util.List;

public record CreateOrderDto(
        @NotBlank String customerId,
        @NotEmpty List<@Valid CreateOrderLineDto> lines) {
}

public record CreateOrderLineDto(
        @NotBlank String sku,
        @Positive int quantity) {
}
~~~

Validator:

~~~java
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;

public final class DtoValidator {
    private static final ValidatorFactory FACTORY =
            Validation.buildDefaultValidatorFactory();

    private static final Validator VALIDATOR =
            FACTORY.getValidator();

    private DtoValidator() {
    }

    public static <T> void validate(T dto) {
        var violations = VALIDATOR.validate(dto);

        if (!violations.isEmpty()) {
            throw new IllegalArgumentException(
                    "Payload validation failed: " + violations);
        }
    }
}
~~~

Ví dụ này minh họa cách gọi Jakarta Bean Validation. Trong production, không nên đưa toàn bộ violation object hoặc payload nhạy cảm vào log. Hãy tạo mã lỗi và thông tin chẩn đoán đã lọc.

## 15. Xử lý lỗi serialization trong serverless

Lỗi parse và validation cần được phân biệt với lỗi tạm thời của hệ thống phụ thuộc.

| Loại lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| JSON không hợp lệ | Thiếu dấu ngoặc, encoding sai | Từ chối payload; thường không retry vô hạn |
| Không tương thích kiểu | Chuỗi gửi vào trường số | Đưa vào luồng lỗi hoặc DLQ theo chính sách |
| Thiếu trường bắt buộc | Không có orderId | Lỗi hợp đồng; cần điều tra producer |
| Sai quy tắc dữ liệu | quantity âm | Từ chối hoặc cách ly |
| Không hỗ trợ event type | Consumer chưa có handler | Định tuyến DLQ, cảnh báo hoặc bỏ qua theo hợp đồng |
| Lỗi tạm thời khi xử lý nghiệp vụ | Database timeout | Retry có giới hạn và backoff |
| Lỗi khi serialize kết quả | Kiểu dữ liệu không hỗ trợ hoặc custom serializer lỗi | Ghi nhận lỗi nội bộ, không phát payload dở dang |

Với queue, lỗi payload vĩnh viễn có thể khiến message bị giao lại liên tục nếu handler chỉ ném exception. Cần xác định lỗi nào được retry và lỗi nào cần chuyển DLQ. Với HTTP, trả mã lỗi phù hợp như 400 cho request không hợp lệ, nhưng không tiết lộ stack trace hoặc chi tiết nội bộ.

Không trả success hoặc ACK message trước khi đã hoàn tất các bước cần thiết. Nếu function xử lý thành công nhưng response bị mất, message có thể được gửi lại; use case cần idempotent.

## 16. Serialization đầu ra và hợp đồng event

Khi phát event, serializer tạo JSON từ DTO. Cần kiểm soát những trường được đưa ra ngoài, tên trường, null, định dạng thời gian và phiên bản schema.

Ví dụ DTO outbound:

~~~java
import com.fasterxml.jackson.annotation.JsonInclude;
import java.time.Instant;
import java.util.List;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record OrderConfirmedEvent(
        String orderId,
        String customerId,
        Instant confirmedAt,
        List<String> productIds) {
}
~~~

**@JsonInclude(NON_NULL)** bỏ qua thuộc tính có giá trị null khi serialize. Tuy nhiên, việc bỏ trường null có thể khác ý nghĩa với gửi "field": null. Cần thống nhất hợp đồng với consumer.

Không serialize trực tiếp domain entity hoặc object chứa:

- Password, token hoặc secret.
- Trường nội bộ chỉ phục vụ persistence.
- Lazy proxy hoặc quan hệ vòng.
- Dữ liệu cá nhân không cần cho consumer.
- Trường debug hoặc thông tin runtime.

Tốt nhất tạo outbound DTO riêng, chỉ gồm các trường được phép công bố.

## 17. Kích thước payload, encoding và dữ liệu nhị phân

Event có thể chứa file hoặc dữ liệu nhị phân, nhưng không nên mặc định nhúng file lớn vào JSON. Base64 làm kích thước dữ liệu tăng khoảng một phần ba và tăng chi phí bộ nhớ khi serialize/deserialize.

Với object storage, thường chỉ gửi tham chiếu:

~~~json
{
  "fileId": "FILE-1001",
  "bucket": "documents",
  "objectKey": "invoices/2026/INV-1001.pdf",
  "contentType": "application/pdf",
  "sizeBytes": 245760
}
~~~

Consumer dùng quyền phù hợp để đọc object. Không gửi URL có chữ ký dài hạn hoặc credential trong event. Nếu dùng pre-signed URL, cần thời hạn ngắn, giới hạn quyền và cân nhắc việc event có thể bị lưu hoặc phát lại sau khi URL hết hạn.

Cần giới hạn kích thước body trước khi parse, đặc biệt với HTTP trigger công khai. Serializer/deserializer cũng có thể tiêu thụ bộ nhớ lớn nếu payload lồng nhau quá sâu hoặc có mảng khổng lồ. Nên đặt giới hạn request size, nesting depth và số phần tử theo khả năng nền tảng.

## 18. Bảo mật khi deserialize dữ liệu không đáng tin cậy

JSON từ HTTP, queue hoặc event bus phải được xem là dữ liệu đầu vào cần xác thực. Những biện pháp cơ bản:

- Chỉ nhận Content-Type và encoding được hỗ trợ.
- Giới hạn kích thước payload và độ sâu cấu trúc.
- Kiểm tra event type, source và schema trước khi gọi nghiệp vụ.
- Không bật polymorphic default typing cho dữ liệu không đáng tin.
- Không deserialize trực tiếp class tùy ý dựa trên tên class trong JSON.
- Kiểm tra giá trị số, chuỗi, danh sách và URI theo giới hạn hợp đồng.
- Không log toàn bộ payload hoặc credential.
- Xác thực nguồn phát và quyền publish/subscribe ở tầng transport.

Nếu dùng custom deserializer, phải xử lý lỗi có kiểm soát. Không cho phép giá trị đầu vào kích hoạt truy cập file, tải URL tùy ý, thực thi biểu thức hoặc tạo object ngoài allowlist.

## 19. Kiểm thử DTO và serialization

Serialization là hợp đồng giữa nhiều thành phần, vì vậy nên có kiểm thử tập trung vào JSON thực tế, không chỉ kiểm tra getter/setter.

Các loại kiểm thử hữu ích:

- **Round-trip:** DTO serialize rồi deserialize lại giữ nguyên giá trị quan trọng.
- **Golden JSON:** So sánh JSON phát ra với mẫu hợp đồng đã công bố.
- **Compatibility:** Consumer mới đọc được event phiên bản cũ; consumer cũ xử lý đúng thay đổi tương thích.
- **Invalid payload:** JSON sai cú pháp, thiếu trường, sai kiểu hoặc vượt giới hạn phải tạo lỗi mong đợi.
- **Unknown field/enum:** Xác minh chính sách strict hoặc tolerant.
- **Date/time and decimal:** Kiểm tra UTC, offset, scale và độ chính xác.
- **Security:** Đảm bảo secret và trường nội bộ không xuất hiện trong JSON đầu ra.

Ví dụ JUnit:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.Test;

class OrderPlacedSerializationTest {
    @Test
    void roundTripPreservesOrderData() throws Exception {
        OrderPlacedData original = new OrderPlacedData(
                "ORD-1001",
                "CUS-2001",
                List.of(new OrderLineData(
                        "SKU-01", 2, new BigDecimal("500000.00"))),
                new BigDecimal("1250000.00"),
                "VND");

        String json = Json.mapper().writeValueAsString(original);

        OrderPlacedData restored = Json.mapper().readValue(
                json, OrderPlacedData.class);

        assertEquals(original, restored);
    }
}
~~~

Record Java tự cung cấp equals theo giá trị thành phần, nên kiểm thử này có thể so sánh hai DTO. Với DTO mutable hoặc có kiểu đặc biệt, hãy so sánh các trường quan trọng và kiểm tra chính xác định dạng JSON.

## 20. Tối ưu serialization trong môi trường FaaS

Serialization có thể ảnh hưởng cold start, CPU, bộ nhớ và latency. Một số cách tối ưu:

- Tái sử dụng **ObjectMapper** đã cấu hình thay vì tạo mới trong mỗi invocation.
- Dùng DTO gọn, không serialize entity hoặc object graph lớn.
- Tránh parse cùng một JSON nhiều lần qua nhiều lớp.
- Chọn Jackson module cần thiết, không đăng ký thư viện không dùng.
- Dùng streaming API cho payload lớn nếu cần xử lý từng phần.
- Giới hạn batch size để tránh giữ nhiều object trong heap.
- Đo thời gian parse, validate, mapping và serialize riêng nếu cần tối ưu.

Không nên tối ưu bằng cách bỏ validation hoặc nới lỏng hợp đồng khi chưa đo được vấn đề. Một mapper dùng chung cần được cấu hình xong trước khi có nhiều invocation đồng thời; không sửa cấu hình global trong lúc xử lý request.

## 21. Quy trình ánh xạ event thành DTO

Một quy trình có thể áp dụng cho mỗi trigger:

1. **Nhận raw event:** Xác định nguồn HTTP, queue, stream hay event bus và kiểu wrapper mà nền tảng cung cấp.
2. **Xác thực transport:** Kiểm tra danh tính nguồn, Content-Type, encoding, request size và quyền truy cập.
3. **Tách envelope và payload:** Đọc message metadata hoặc event context, xác định loại event và schema version.
4. **Deserialize:** Chọn DTO đúng theo event type và phiên bản schema.
5. **Validate:** Kiểm tra cấu trúc, kiểu dữ liệu, trường bắt buộc và quy tắc miền.
6. **Map sang command:** Chuyển DTO thành kiểu nội bộ để use case không phụ thuộc transport.
7. **Xử lý idempotent:** Dùng event ID, message ID hoặc idempotency key để chống hiệu ứng lặp.
8. **Xử lý lỗi:** Phân biệt lỗi payload vĩnh viễn với lỗi hạ tầng tạm thời; chọn response, retry hoặc DLQ.
9. **Serialize đầu ra:** Dùng outbound DTO và schema đã công bố.
10. **Theo dõi:** Ghi event ID, type, correlation ID và kết quả mà không log dữ liệu nhạy cảm.

## 22. Những lỗi thường gặp

**Dùng event wrapper làm domain model:** Logic nghiệp vụ phụ thuộc cấu trúc nhà cung cấp và khó kiểm thử. Tạo DTO nội bộ và mapper ở ranh giới.

**Dùng Map<String, Object> cho mọi payload:** Mất kiểm tra kiểu và phát sinh ép kiểu thủ công. Dùng DTO cụ thể cho event đã biết; chỉ dùng map cho metadata thực sự linh hoạt.

**Không giữ generic type khi deserialize:** Payload trở thành map thay vì DTO. Dùng TypeReference hoặc JavaType.

**Dùng double cho tiền:** Có thể gây sai số thập phân. Dùng BigDecimal hoặc đơn vị tiền nhỏ nhất theo hợp đồng.

**Dùng LocalDateTime cho thời điểm toàn cầu:** Không có múi giờ nên khó xác định thời điểm. Dùng Instant hoặc OffsetDateTime.

**Bỏ qua unknown fields một cách toàn cục:** Có thể che giấu producer gửi nhầm hợp đồng. Chọn strict/tolerant theo từng loại event và kiểm thử tương thích.

**Enum không chịu được giá trị mới:** Consumer lỗi liên tục khi producer mở rộng trạng thái. Chọn strict, UNKNOWN hoặc chuỗi có kiểm soát theo nghiệp vụ.

**Deserialize rồi gọi use case ngay:** Parse được không có nghĩa dữ liệu hợp lệ. Thực hiện validation trước khi gọi nghiệp vụ.

**Serialize entity database:** Có thể lộ trường nội bộ, lazy proxy hoặc dữ liệu nhạy cảm. Dùng outbound DTO riêng.

**Tạo ObjectMapper trong mỗi invocation:** Tăng allocation và chi phí khởi tạo. Tái sử dụng mapper bất biến sau cấu hình.

**Bật default typing cho dữ liệu không tin cậy:** Có thể mở ra rủi ro deserialize class tùy ý. Dùng allowlist và dispatch theo event type.

**Retry vô hạn lỗi serialization:** Payload không hợp lệ sẽ tiếp tục thất bại. Phân loại lỗi và chuyển DLQ hoặc luồng cách ly.

## 23. Checklist trước khi triển khai

- [ ] Đã xác định rõ transport wrapper, event envelope và business payload.
- [ ] DTO tách biệt với entity database và domain model.
- [ ] Mỗi event type ánh xạ đến đúng DTO và handler.
- [ ] Generic payload được deserialize với đầy đủ type information.
- [ ] Tên trường JSON, alias và naming strategy đã được thống nhất.
- [ ] Kiểu tiền, ngày giờ, enum và null/missing được chọn có chủ đích.
- [ ] ObjectMapper được cấu hình một lần và tái sử dụng an toàn.
- [ ] Java Time module và module cần thiết đã được đăng ký.
- [ ] Chính sách unknown property và enum mới được xác định.
- [ ] Payload được validate cấu trúc, dữ liệu và nghiệp vụ.
- [ ] Có giới hạn kích thước và độ sâu payload.
- [ ] Không deserialize class tùy ý từ dữ liệu không đáng tin.
- [ ] Outbound DTO chỉ chứa trường được phép công bố.
- [ ] Có kiểm thử round-trip, golden JSON và schema compatibility.
- [ ] Lỗi parse/validation được phân biệt với lỗi tạm thời để xử lý retry đúng.
- [ ] Có event ID/correlation ID và log an toàn để truy vết.

## Kết luận

Ánh xạ event thành DTO tạo ranh giới rõ giữa định dạng trigger và logic nghiệp vụ Java. Envelope cung cấp ngữ cảnh vận chuyển hoặc sự kiện; payload được deserialize thành DTO cụ thể; validator kiểm tra dữ liệu; mapper chuyển DTO thành command; use case thực hiện nghiệp vụ. Chiều ngược lại, outbound DTO và serializer tạo payload đúng hợp đồng cho consumer.

Trong serverless, cần tái sử dụng ObjectMapper đã cấu hình, chọn kiểu dữ liệu chính xác, kiểm soát null và unknown fields, quản lý schema version, giới hạn payload và phân loại lỗi serialization. Khi hợp đồng được kiểm thử và consumer xử lý được message lặp, các Java function có thể nhận và phát event ổn định qua HTTP, queue hoặc event bus mà không phụ thuộc chặt vào cấu trúc riêng của nền tảng.

