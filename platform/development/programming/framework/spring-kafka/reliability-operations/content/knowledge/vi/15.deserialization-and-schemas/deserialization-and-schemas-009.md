# Unknown field và missing field

Trong hệ thống Spring Kafka, producer và consumer thường được triển khai độc lập, không nhất thiết cùng phiên bản. Một producer có thể bổ sung trường mới vào JSON trong khi consumer cũ chưa được nâng cấp; ngược lại, một consumer mới có thể chờ một trường mà các record cũ trong Kafka chưa từng có. Hai tình huống này dẫn tới các khái niệm **unknown field** và **missing field** trong deserialization và schema evolution.

- **Unknown field:** payload chứa một trường mà kiểu dữ liệu hoặc schema của consumer chưa biết.
- **Missing field:** payload không chứa một trường mà kiểu dữ liệu hoặc schema của consumer dự kiến có.

Cả hai đều liên quan đến tương thích phiên bản, nhưng cách xử lý không giống nhau. Unknown field thường có thể được bỏ qua nếu consumer không cần nó. Missing field cần được đánh giá theo ý nghĩa nghiệp vụ: có thể dùng default khi trường là tùy chọn, nhưng phải từ chối record nếu thiếu dữ liệu bắt buộc. Bài này tập trung vào Spring Kafka với JSON/Jackson, đồng thời so sánh quy tắc liên quan trong Avro và Protobuf.

## 1. Ví dụ thay đổi cấu trúc event

Giả sử topic `orders.created` đang chứa sự kiện phiên bản 1:

~~~json
{
  "eventId": "evt-001",
  "orderId": "ord-100",
  "amount": 125000
}
~~~

Sau khi producer được nâng cấp lên phiên bản 2, sự kiện có thêm trường `currency`:

~~~json
{
  "eventId": "evt-002",
  "orderId": "ord-101",
  "amount": 125000,
  "currency": "VND"
}
~~~

Có hai hướng phát sinh vấn đề:

1. **Consumer v1 đọc event v2:** `currency` là unknown field vì model v1 chưa khai báo nó.
2. **Consumer v2 đọc event v1:** `currency` là missing field vì JSON cũ không chứa nó.

Nếu `currency` chỉ để hiển thị, consumer cũ có thể bỏ qua. Nếu consumer mới dùng currency để tính tiền, mặc định ngầm `VND` cho mọi event cũ có thể sai khi dữ liệu thực tế còn nhiều loại tiền. Quyết định fallback phải dựa trên hợp đồng event, không chỉ để code không ném exception.

## 2. Phân biệt unknown, missing, null và sai kiểu

Bốn trường hợp thường bị đánh đồng:

| Tình huống | JSON đầu vào | Model mong đợi | Nguyên nhân |
|---|---|---|---|
| Unknown field | Có `couponCode` | Model không có `couponCode` | Producer gửi dữ liệu mới |
| Missing field | Không có `currency` | Model có `currency` | Producer cũ hoặc payload thiếu |
| Explicit null | `"currency": null` | Model có `currency` | Producer chủ động gửi null |
| Type mismatch | `"amount": "abc"` | Model cần số | Dữ liệu không chuyển thành kiểu mong đợi |

Missing khác explicit null: không gửi trường nghĩa là trường vắng mặt; gửi `null` nghĩa là trường có mặt nhưng giá trị là JSON null. Với nhiều kiểu Java, Jackson có thể ánh xạ cả hai thành `null`, nhưng yêu cầu nghiệp vụ vẫn có thể khác.

Một số nguyên nhân khác cần phân biệt:

- **Tên trường đổi:** producer gửi `customerId` trong khi consumer còn đọc `buyerId`.
- **Kiểu trường đổi:** số nguyên thành object hoặc chuỗi ký tự.
- **Enum value mới:** producer gửi `SHIPPED_BACK` mà enum ở consumer chưa khai báo.
- **Trường lồng nhau:** object `address` có thêm trường mà nested DTO không biết.
- **Payload không phải JSON hợp lệ:** lỗi cú pháp, encoding hoặc dữ liệu bị cắt cụt.

Không nên coi mọi lỗi deserialize là unknown/missing field. Chẩn đoán cần xem loại exception và payload thực tế.

## 3. Jackson xử lý unknown field như thế nào?

Jackson dùng `ObjectMapper` để ánh xạ JSON thành Java class hoặc record. Tùy cấu hình, unknown field có thể bị bỏ qua hoặc làm deserialization thất bại.

Model v1:

~~~java
public record OrderCreatedV1(
        String eventId,
        String orderId,
        BigDecimal amount) {
}
~~~

Nếu JSON có thêm `currency`, và mapper bật `FAIL_ON_UNKNOWN_PROPERTIES`, Jackson có thể ném `UnrecognizedPropertyException`.

Ví dụ cấu hình nghiêm ngặt:

~~~java
ObjectMapper strictMapper = JsonMapper.builder()
        .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
        .build();

OrderCreatedV1 event = strictMapper.readValue(
        jsonWithCurrency,
        OrderCreatedV1.class
);
~~~

Ngược lại, có thể cho phép unknown field:

~~~java
ObjectMapper tolerantMapper = JsonMapper.builder()
        .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
        .build();
~~~

Khi đó, trường `currency` không được khai báo sẽ bị bỏ qua trong quá trình ánh xạ. Model `OrderCreatedV1` nhận được `eventId`, `orderId`, `amount` mà không có thông tin `currency`.

**Lưu ý mặc định:** Jackson `ObjectMapper` thuần có cấu hình mặc định khác với mapper được Spring Boot hoặc Spring Kafka dựng sẵn. Nhiều cấu hình Spring Boot và enhanced mapper của Spring Kafka thường vô hiệu hóa `FAIL_ON_UNKNOWN_PROPERTIES`. Không đoán chế độ đang chạy; xác định `ObjectMapper` mà `JsonDeserializer` thực sự sử dụng.

## 4. Bỏ qua unknown field ở mức DTO

Nếu chỉ một DTO cần chấp nhận trường mới, có thể dùng `@JsonIgnoreProperties(ignoreUnknown = true)`:

~~~java
@JsonIgnoreProperties(ignoreUnknown = true)
public record OrderCreatedV1(
        String eventId,
        String orderId,
        BigDecimal amount) {
}
~~~

Lựa chọn này hữu ích khi muốn giữ mapper nghiêm ngặt cho đa số payload nhưng cho phép một event có khả năng mở rộng từng bước.

Có ba mức quyết định chính:

| Vị trí cấu hình | Phạm vi | Ưu điểm | Rủi ro |
|---|---|---|---|
| `ObjectMapper` chung | Nhiều DTO được mapper xử lý | Nhất quán, dễ triển khai | Che giấu sai chính tả trường ở nhiều event |
| `@JsonIgnoreProperties` | Một DTO/class cụ thể | Chính sách theo hợp đồng event | Có thể bỏ sót nested DTO cần cấu hình riêng |
| Kiểm tra schema/validator | Theo schema hoặc rule nghiệp vụ | Có thể kiểm soát chặt lỗi cấu trúc | Cần thêm schema và quy trình versioning |

Nếu consumer có nhiệm vụ trung gian đọc rồi xuất lại record, bỏ qua unknown field có thể **làm mất thông tin** khi serialize object mới. Ví dụ một service nhận `currency` nhưng DTO không biết nó; khi service phát lại cùng event từ DTO v1, trường `currency` biến mất. Đừng dùng ignoreUnknown như cách bảo toàn payload.

Nếu cần giữ trường chưa biết, cân nhắc lưu raw payload, một extension map thông qua `@JsonAnySetter`, hoặc cơ chế schema-aware forwarding phù hợp.

## 5. Missing field trong Java DTO và record

Với DTO thông thường, Jackson thường không tự coi việc thiếu một property là lỗi. Đối với field tham chiếu như `String` hoặc `BigDecimal`, nếu không có giá trị, kết quả thường là `null`. Đối với primitive Java, giá trị mặc định thường là `0`, `false` hoặc một default khác tùy cách khởi tạo và cấu hình mapper.

Ví dụ:

~~~java
public record OrderCreatedV2(
        String eventId,
        String orderId,
        BigDecimal amount,
        String currency) {
}
~~~

Đọc JSON v1 không có `currency` có thể tạo:

~~~text
OrderCreatedV2[
  eventId=evt-001,
  orderId=ord-100,
  amount=125000,
  currency=null
]
~~~

Nếu listener giả định `currency` luôn khác null:

~~~java
String normalized = event.currency().toUpperCase();
~~~

thì chương trình có thể gặp `NullPointerException` **sau** deserialize. Khi đó, vấn đề là validation hoặc logic nghiệp vụ chứ không nhất thiết là lỗi của JSON parser.

Trường primitive đặc biệt nguy hiểm:

~~~java
public record InventoryAdjusted(
        String itemId,
        int quantity,
        boolean confirmed) {
}
~~~

Khi `quantity` hoặc `confirmed` bị thiếu, giá trị 0 hoặc false có thể được sử dụng mà không báo lỗi. Consumer không phân biệt được “producer gửi số lượng bằng 0” với “producer bỏ quên trường”, trừ khi dùng kiểu nullable, creator validation hoặc schema rule phù hợp.

## 6. Explicit null có cần được xử lý khác missing?

Ví dụ:

~~~json
{"orderId":"ord-100"}
~~~

và:

~~~json
{"orderId":"ord-100","currency":null}
~~~

Hai payload có ý nghĩa khác nhau nếu hợp đồng quy định `currency` không được bỏ trống nhưng cho phép explicit null trong thao tác xóa giá trị, hoặc ngược lại.

Một số chiến lược:

- Field thật sự tùy chọn: cho phép vắng mặt và null, dùng logic fallback rõ ràng.
- Field bắt buộc: từ chối cả vắng mặt và null.
- Field có nghĩa cập nhật từng phần (patch semantics): vắng mặt là “không thay đổi”, null là “xóa giá trị”; cần kiểu dữ liệu hoặc parser giữ được phân biệt này.
- Field được phép null nhưng không được vắng mặt: cần kiểm tra sự hiện diện trong JSON hoặc schema trước khi bind.

Không sử dụng `Optional<T>` trong mọi DTO chỉ để tránh null. Với Jackson và các module hỗ trợ, cách ánh xạ `Optional` phụ thuộc cấu hình; quan trọng hơn là hợp đồng event phải xác định rõ ý nghĩa của thiếu trường.

## 7. Bắt buộc field bằng creator properties

Có thể dùng `@JsonCreator` và `@JsonProperty(required = true)` để chỉ rõ các tham số constructor/creator bắt buộc:

~~~java
public final class PaymentRequested {

    private final String paymentId;
    private final BigDecimal amount;

    @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
    public PaymentRequested(
            @JsonProperty(value = "paymentId", required = true)
            String paymentId,
            @JsonProperty(value = "amount", required = true)
            BigDecimal amount) {

        this.paymentId = Objects.requireNonNull(
                paymentId, "paymentId is required");
        this.amount = Objects.requireNonNull(
                amount, "amount is required");
    }

    public String getPaymentId() {
        return paymentId;
    }

    public BigDecimal getAmount() {
        return amount;
    }
}
~~~

Ở creator-based deserialization, `required = true` có thể khiến Jackson từ chối một tham số **vắng mặt**. Tuy nhiên, thuộc tính `required` không phải một validator tổng quát cho mọi Java field hoặc setter. Đồng thời, “required” và “không null” không đồng nhất: constructor trong ví dụ dùng `requireNonNull` để kiểm tra giá trị.

Các tính năng Jackson cần biết:

- `FAIL_ON_MISSING_CREATOR_PROPERTIES`: từ chối creator property không có trong payload theo chính sách mapper, kể cả khi không khai báo `required`.
- `FAIL_ON_NULL_CREATOR_PROPERTIES`: từ chối giá trị null đối với creator property.
- `FAIL_ON_NULL_FOR_PRIMITIVES`: kiểm soát việc ánh xạ JSON null sang Java primitive.
- `FAIL_ON_UNKNOWN_PROPERTIES`: độc lập với ba tùy chọn trên; kiểm soát trường nằm ngoài model.

Ví dụ mapper nghiêm ngặt cho hợp đồng thanh toán:

~~~java
ObjectMapper mapper = JsonMapper.builder()
        .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
        .enable(DeserializationFeature.FAIL_ON_MISSING_CREATOR_PROPERTIES)
        .enable(DeserializationFeature.FAIL_ON_NULL_CREATOR_PROPERTIES)
        .enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES)
        .build();
~~~

Không bật tất cả tùy chọn này toàn cục chỉ vì một event cần strict mode. Các DTO có trường tùy chọn hoặc creator property với default hợp lệ có thể bị từ chối ngoài dự kiến. Chọn mapper, schema và DTO theo từng hợp đồng.

## 8. Validation nghiệp vụ sau deserialize

Ngay cả khi JSON hợp lệ và Jackson tạo được object, event vẫn có thể không hợp lệ về mặt nghiệp vụ: amount âm, orderId rỗng, currency không được hỗ trợ, hoặc giá trị không khớp trạng thái đơn hàng.

Có thể dùng Jakarta Bean Validation:

~~~java
public record OrderCreated(
        @NotBlank String eventId,
        @NotBlank String orderId,
        @NotNull @DecimalMin("0.01") BigDecimal amount,
        @NotBlank String currency) {
}
~~~

Nếu gọi validator rõ ràng trong service:

~~~java
public void process(OrderCreated event) {
    Set<ConstraintViolation<OrderCreated>> violations =
            validator.validate(event);

    if (!violations.isEmpty()) {
        throw new InvalidOrderEventException(
                "Invalid order event: " + violations.size() + " violations");
    }

    orderService.handle(event);
}
~~~

Đoạn trên giả định `validator` là `jakarta.validation.Validator` và `InvalidOrderEventException` do ứng dụng định nghĩa. Không nên ghi chi tiết dữ liệu cá nhân từ violation message vào log.

Spring Kafka listener có thể tích hợp validation qua `@Valid` hoặc Kafka listener validator tùy cấu hình/version, nhưng không giả định annotation tự động hoạt động với mọi kiểu listener và message converter. Trong bài, validation tường minh minh họa ranh giới rõ ràng: JSON đã deserialize thành công, rồi mới xác định dữ liệu có hợp lệ về nghiệp vụ hay không.

## 9. Chọn mặc định an toàn cho missing field

Một field mới thường cần giá trị mặc định để consumer mới đọc được record cũ đang tồn tại trong Kafka.

Ví dụ phiên bản 2 thêm `priority`:

~~~json
{
  "eventId": "evt-003",
  "orderId": "ord-102",
  "amount": 99000,
  "priority": "NORMAL"
}
~~~

Nếu hợp đồng quy định trước đây mọi order đều có mức NORMAL, consumer v2 có thể áp dụng default `NORMAL` khi field vắng mặt. Điều này giữ được ý nghĩa dữ liệu lịch sử.

Nhưng đối với `currency`, không nên mặc định VND chỉ vì phần lớn đơn hàng là VND nếu không thể chứng minh dữ liệu cũ cùng dùng VND. Một default sai có thể gây tính tiền sai nhưng không tạo exception, khó phát hiện hơn lỗi deserialize rõ ràng.

Quy trình quyết định:

1. Field mới có bắt buộc cho logic nghiệp vụ không?
2. Có thể suy ra giá trị đúng của record cũ không?
3. Default có làm thay đổi số tiền, quyền truy cập hoặc trạng thái không?
4. Record tồn tại trong retention/backlog bao lâu?
5. Có cần version marker hoặc migration dữ liệu cũ không?
6. Producer và consumer cần được triển khai theo thứ tự nào?

Default nên thể hiện quy tắc miền nghiệp vụ, không phải giải pháp kỹ thuật để tránh NullPointerException.

## 10. Đổi tên field và alias

Một vấn đề thường gặp là producer đổi tên `buyerId` thành `customerId`. Consumer mới đọc sự kiện cũ sẽ thiếu `customerId`, dù thực chất thông tin vẫn có trong `buyerId`.

Jackson hỗ trợ `@JsonAlias` để nhận thêm tên cũ khi deserialize:

~~~java
public record OrderCreated(
        String eventId,
        String orderId,
        @JsonAlias("buyerId") String customerId,
        BigDecimal amount) {
}
~~~

Consumer có thể đọc cả:

~~~json
{"eventId":"evt-1","orderId":"ord-1","buyerId":"cus-1","amount":100}
~~~

và:

~~~json
{"eventId":"evt-2","orderId":"ord-2","customerId":"cus-2","amount":200}
~~~

`@JsonAlias` dùng chủ yếu cho **đọc**; khi serialize, tên property chính vẫn là `customerId` trừ khi cấu hình khác. Điều này quan trọng nếu ứng dụng vừa consume vừa republish event: producer phía sau có thể chỉ nhận tên mới.

Khi có cả `buyerId` và `customerId` với hai giá trị khác nhau, phải có chính sách rõ ràng; không dựa vào thứ tự property trong JSON để quyết định ngẫu nhiên giá trị nào thắng.

## 11. Schema compatibility: backward và forward

Schema evolution có hai hướng:

- **Backward compatibility:** consumer mới đọc được dữ liệu do producer cũ tạo ra. Missing field là tình huống trọng tâm; field mới thường cần default hoặc tùy chọn.
- **Forward compatibility:** consumer cũ đọc được dữ liệu do producer mới tạo ra. Unknown field là tình huống trọng tâm; consumer cũ phải có khả năng bỏ qua hoặc hiểu giá trị mới.
- **Full compatibility:** cả hai hướng đều đáp ứng quy tắc tương thích.

Đây là cách giải thích trực quan cho event; các chế độ compatibility cụ thể của Schema Registry (BACKWARD, FORWARD, FULL, biến thể transitive) có ngữ nghĩa kiểm tra schema riêng. Không thể kết luận một thay đổi JSON tự do là tương thích chỉ vì Jackson đang ignore unknown field.

Ví dụ bảng:

| Thay đổi | Consumer cũ đọc producer mới | Consumer mới đọc producer cũ | Điều kiện |
|---|---|---|---|
| Thêm field tùy chọn | Có thể, nếu ignore unknown | Có thể, nếu có default/null hợp lệ | Xác định default |
| Thêm field bắt buộc không default | Có thể nếu ignore unknown | Thường lỗi hoặc thiếu dữ liệu | Cần migration/version |
| Xóa field | Consumer cũ có thể thiếu field | Consumer mới có thể bỏ qua field cũ | Kiểm tra contract |
| Đổi tên field | Thường gây unknown và missing | Thường gây missing | Alias hoặc versioning |
| Đổi kiểu field | Có thể lỗi kiểu | Có thể lỗi kiểu | Cần schema conversion |
| Thêm enum value | Consumer cũ có thể không hiểu | Consumer mới thường hiểu giá trị cũ | Đặt fallback có chủ đích |

Trong hệ thống có backlog dài hoặc replay thường xuyên, consumer mới vẫn cần đọc record cũ nhiều tháng sau triển khai. Tương thích không chỉ xảy ra trong lúc rolling deployment.

## 12. Cách Spring Kafka deserialize JSON

Luồng thông dụng:

    Broker record bytes
             |
             v
       Kafka Consumer poll()
             |
             v
       JsonDeserializer
             |
       +-----+----------------+
       |                      |
       v                      v
    Thành công             Exception
       |                      |
       v                      v
    OrderCreated        Lỗi trước listener
       |                      |
       v                      |
    @KafkaListener            |
       |                      |
       +--- validation --------+
                  |
                  v
        CommonErrorHandler / recovery

Hai lỗi có đường đi khác nhau:

1. **Deserialization error:** JSON sai cú pháp, unknown field ở strict mode, sai kiểu dữ liệu, thiếu creator property bắt buộc. Exception có thể xảy ra trước khi listener được gọi.
2. **Business validation error:** deserialize thành công, nhưng listener hoặc validator phát hiện field bắt buộc về nghiệp vụ bị thiếu hoặc không hợp lệ.

Nếu JsonDeserializer ném lỗi ngay trong poll(), error handling cần cấu hình phù hợp để container nhận biết record lỗi và vẫn có thể tiếp tục. Đó là mục đích quan trọng của ErrorHandlingDeserializer.

## 13. Cấu hình ErrorHandlingDeserializer

Spring Kafka có `ErrorHandlingDeserializer` bao bọc deserializer thực tế, ghi thông tin lỗi deserialize vào header cho container xử lý, thay vì để một record lỗi cấu trúc luôn phá vỡ vòng poll.

Ví dụ YAML với value là JSON:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.events.OrderCreated
        spring.json.trusted.packages: com.example.events
        spring.json.use.type.headers: false
    listener:
      ack-mode: record
~~~

Trong ví dụ:

- `ErrorHandlingDeserializer` bao bọc `JsonDeserializer`.
- `spring.json.value.default.type` chỉ kiểu payload mặc định khi không dựa vào type header.
- `spring.json.trusted.packages` giới hạn các package được tin cậy cho type mapping.
- `spring.json.use.type.headers=false` phù hợp khi topic có một kiểu event đã biết và không muốn phụ thuộc type header của producer.
- `enable-auto-commit=false` để container kiểm soát commit offset theo AckMode.

Các thuộc tính cho JsonDeserializer có thể khác theo phiên bản hoặc cách khởi tạo bằng bean. Nếu consumer sử dụng custom ObjectMapper, việc bật strict mode cho unknown field phải được cấu hình trực tiếp ở mapper được truyền vào JsonDeserializer; không giả định một YAML property bất kỳ sẽ đổi được `FAIL_ON_UNKNOWN_PROPERTIES`.

Không mở `spring.json.trusted.packages=*` tùy tiện cho event từ nguồn không đáng tin cậy. Trusted packages và unknown field policy giải quyết hai vấn đề khác nhau: giới hạn type được deserialize và quyết định có bỏ qua JSON property lạ hay không.

## 14. Cấu hình strict ObjectMapper trong ConsumerFactory

Khi cần xử lý JSON unknown field bằng exception và chuyển sang DLT, có thể cấp một ObjectMapper riêng cho JsonDeserializer:

~~~java
@Bean
ConsumerFactory<String, OrderCreated> orderConsumerFactory(
        KafkaProperties kafkaProperties) {

    ObjectMapper mapper = JsonMapper.builder()
            .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
            .build();

    JsonDeserializer<OrderCreated> json =
            new JsonDeserializer<>(OrderCreated.class, mapper, false);

    ErrorHandlingDeserializer<OrderCreated> valueDeserializer =
            new ErrorHandlingDeserializer<>(json);

    return new DefaultKafkaConsumerFactory<>(
            kafkaProperties.buildConsumerProperties(),
            new StringDeserializer(),
            valueDeserializer
    );
}
~~~

Đây là ví dụ định hướng cho Spring Kafka 3.x và các phiên bản Spring Boot có API `KafkaProperties.buildConsumerProperties()` phù hợp; chữ ký có thể thay đổi khi nâng version. Tham số `false` của JsonDeserializer trong ví dụ biểu thị không dùng type headers theo constructor tương ứng của phiên bản đã chọn. Nếu dự án có custom ConsumerFactory, cần gắn đúng instance vào listener container factory.

Với Spring Kafka đã khởi tạo JsonDeserializer bằng code, một số thuộc tính `spring.json.*` cấu hình qua property map có thể không được áp dụng theo cách mong đợi khi trộn setter API và property-based configuration. Hãy chọn một cách cấu hình nhất quán và xác nhận behavior trong integration test.

Strict mapper phù hợp cho event có contract chặt chẽ, nhưng có thể khiến consumer cũ không đọc được event mới chỉ vì producer bổ sung trường không ảnh hưởng tới consumer. Cần phối hợp chính sách strict với kế hoạch versioning.

## 15. DefaultErrorHandler và DLT cho record lỗi schema

Với ErrorHandlingDeserializer, Spring Kafka container có thể xử lý lỗi deserialize và chuyển record tới recoverer/DLT sau khi áp dụng chính sách error handler.

~~~java
@Bean
CommonErrorHandler kafkaErrorHandler(
        KafkaTemplate<Object, Object> dltTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(dltTemplate);

    DefaultErrorHandler handler = new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L)
    );

    handler.addNotRetryableExceptions(
            InvalidOrderEventException.class
    );

    return handler;
}
~~~

Với lỗi cấu trúc cố định (unknown field strict, missing required creator field, sai kiểu không thể chuyển), retry nguyên record nhiều lần thường không giúp ích. Nên phân loại lỗi đúng và chuyển DLT sớm. DefaultErrorHandler có các exception loại không retry mặc định tùy phiên bản; xem exception thực tế và policy hiện tại trước khi bổ sung classification.

Khi ErrorHandlingDeserializer không thể dựng value, recoverer có thể nhận byte[] dữ liệu gốc hoặc dữ liệu dự phòng tùy loại lỗi và phiên bản. **DLT producer phải serialize được kiểu value thực tế**, không thể giả định mọi record lỗi đều là OrderCreated. Có thể cần DelegatingByTypeSerializer hoặc một KafkaTemplate có serializer xử lý cả object bình thường lẫn raw bytes.

Không commit offset nguồn như đã xử lý nếu thao tác publish DLT thực tế thất bại. Thiết kế recovery cần theo dõi send result, producer timeout và khả năng retry khi broker/DLT topic không sẵn sàng.

## 16. Ví dụ listener kiểm tra missing field

Một listener có thể chấp nhận optional field nhưng phải từ chối field bắt buộc:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "billing-service"
)
public void consume(OrderCreated event) {

    if (event.orderId() == null || event.orderId().isBlank()) {
        throw new InvalidOrderEventException(
                "Missing required orderId");
    }

    if (event.currency() == null || event.currency().isBlank()) {
        throw new InvalidOrderEventException(
                "Missing required currency");
    }

    billingService.createInvoice(event);
}
~~~

Trong ví dụ, một event JSON thiếu currency vẫn có thể được deserialize thành OrderCreated, nhưng listener cố ý từ chối trước khi tạo hóa đơn. Exception được đưa tới DefaultErrorHandler để chuyển DLT theo classification đã cấu hình.

Nếu hợp đồng ghi rõ currency là tùy chọn trên event v1 và có thể xác định một giá trị mặc định đúng từ dữ liệu cũ, logic fallback nên nằm ở bước normalize/adapter riêng, kèm kiểm thử và metric. Không tự động chấp nhận null khi nó làm sai số tiền.

Nếu `billingService.createInvoice` có side effect, hãy làm nó idempotent theo eventId. Một record có thể được giao lại sau lỗi commit offset kể cả khi validation và deserialize đều thành công.

## 17. JSON Schema và kiểm tra trước khi bind

Jackson phản ánh ràng buộc của Java type và mapper, nhưng không nhất thiết thể hiện toàn bộ hợp đồng event. JSON Schema có thể mô tả:

- Danh sách field bắt buộc qua `required`.
- Kiểu dữ liệu qua `type`.
- Giá trị ràng buộc qua `enum`, `minimum`, `pattern`.
- Có cho phép field không khai báo hay không qua `additionalProperties`.
- Định dạng và cấu trúc object lồng nhau.

Ví dụ JSON Schema giản lược:

~~~json
{
  "type": "object",
  "required": ["eventId", "orderId", "amount"],
  "properties": {
    "eventId": {"type": "string"},
    "orderId": {"type": "string"},
    "amount": {"type": "number", "minimum": 0},
    "currency": {"type": "string"}
  },
  "additionalProperties": true
}
~~~

Trong schema này, currency không bắt buộc, và các field mới được phép xuất hiện. Nếu thay `additionalProperties` thành `false`, một field mới như couponCode có thể bị từ chối bởi schema validator.

JSON Schema `required` kiểm tra sự hiện diện của property; nếu muốn cấm JSON null, schema cần khai báo kiểu không chấp nhận null. Đây là điểm khác với việc chỉ dùng `@JsonProperty(required=true)` trên Java class.

Dùng JSON Schema khi cần hợp đồng ngoài Java, đặc biệt khi nhiều ngôn ngữ producer/consumer cùng trao đổi sự kiện. Nhưng việc có schema không tự bảo đảm producer kiểm tra trước khi publish hoặc consumer kiểm tra trước khi xử lý; quy trình validation cần được thực thi.

## 18. Khác biệt với Avro

Với Avro, schema resolution diễn ra dựa trên writer schema và reader schema. Hai chiều thay đổi có hành vi khác với JSON/Jackson.

**Producer mới thêm field, consumer cũ chưa có:** reader schema cũ thường bỏ qua field có trong writer schema nhưng không nằm trong reader schema. Điều này giống việc bỏ qua unknown field.

**Consumer mới yêu cầu field mà writer cũ không gửi:** nếu reader schema có field mới, Avro cần default thích hợp cho field đó khi đọc dữ liệu do writer schema cũ tạo ra. Nếu thiếu default và writer không có field, schema resolution có thể thất bại.

Ví dụ Avro schema mới có default:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "example.events",
  "fields": [
    {"name": "eventId", "type": "string"},
    {"name": "orderId", "type": "string"},
    {"name": "amount", "type": "long"},
    {"name": "currency", "type": "string", "default": "VND"}
  ]
}
~~~

Default VND ở đây chỉ đúng nếu đó là quy ước lịch sử của dữ liệu. Avro cho phép khai báo default theo schema, nhưng không bảo đảm default hợp nghiệp vụ.

Với union nullable, schema có thể khai báo ví dụ `["null","string"]` và default null theo quy tắc Avro tương ứng. Đừng mặc định rằng một field chỉ vì có thể null sẽ tự đọc được dữ liệu cũ khi thiếu default; hãy kiểm tra schema resolution và compatibility của registry.

Schema Registry giúp kiểm tra compatibility khi đăng ký schema mới theo policy của subject, nhưng policy này phải được cấu hình và quản lý. Không thay thế kiểm thử tích hợp bằng việc chỉ kiểm tra schema đăng ký thành công.

## 19. Khác biệt với Protobuf

Protobuf gán mỗi field một **field number** trên wire format. Một consumer cũ đọc message mới có thể gặp field number chưa biết. Nhiều runtime Protobuf giữ unknown fields ở dạng unknown field set khi parse binary, nhưng cách giữ, tuần tự hóa lại và chuyển sang JSON có thể khác theo runtime hoặc cấu hình.

Một field không hiện diện trong proto3 có thể được đọc thành default của kiểu: số bằng 0, boolean false, string rỗng. Vì vậy, thiếu field và field có giá trị default không luôn phân biệt được nếu không dùng presence semantics.

Với `optional` hoặc message field hỗ trợ presence, ứng dụng có thể kiểm tra field có thật sự được set hay không. Khi thiết kế schema cần quyết định field nào cần biết sự hiện diện và field nào có thể nhận default.

Nếu bỏ field Protobuf, dùng `reserved` cho field number/name đã ngừng sử dụng để tránh vô tình tái dùng số field cũ với ý nghĩa mới. Việc tái sử dụng field number có thể gây lỗi dữ liệu nguy hiểm hơn một exception deserialize rõ ràng.

Đối với Protobuf JSON mapping, parser có thể có chính sách riêng cho unknown JSON fields. Không đồng nhất cách xử lý unknown field trong Protobuf binary với cách Jackson xử lý JSON.

## 20. Enum value mới và tính tương thích

Giả sử producer bổ sung trạng thái `ON_HOLD`:

~~~json
{
  "eventId": "evt-007",
  "orderId": "ord-105",
  "status": "ON_HOLD"
}
~~~

Consumer cũ chỉ có:

~~~java
enum OrderStatus {
    CREATED,
    CONFIRMED,
    CANCELLED
}
~~~

Dù tên field `status` được biết, giá trị `ON_HOLD` vẫn là **unknown enum value**, không phải unknown property. Jackson có thể ném exception nếu không thể map enum.

Một số cấu hình Jackson như `READ_UNKNOWN_ENUM_VALUES_AS_NULL` hoặc `READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE` có thể cho phép fallback. Nếu dùng default enum, cần xác định trạng thái `UNKNOWN` có ý nghĩa an toàn:

~~~java
enum OrderStatus {
    CREATED,
    CONFIRMED,
    CANCELLED,

    @JsonEnumDefaultValue
    UNKNOWN
}
~~~

Không nên ánh xạ mọi trạng thái mới về CREATED chỉ để consumer cũ tiếp tục xử lý. Làm vậy có thể kích hoạt workflow sai. Với trạng thái tác động quyền, thanh toán hoặc hoàn tiền, từ chối hoặc cách ly event thường an toàn hơn suy diễn.

## 21. Sự cố triển khai: thêm field mới trong rolling deployment

Một thay đổi được coi là an toàn thường cần chuẩn bị cả producer và consumer.

Ví dụ thêm trường tùy chọn `couponCode`:

1. Xác định hợp đồng: couponCode vắng mặt nghĩa là không có mã giảm giá.
2. Consumer mới chấp nhận record cũ không có couponCode.
3. Consumer cũ chấp nhận record mới có couponCode nếu không ảnh hưởng nghiệp vụ.
4. Triển khai consumer có khả năng đọc cả hai dạng.
5. Sau đó producer bắt đầu phát couponCode.
6. Theo dõi deserialization error, validation error và DLT.
7. Chỉ xóa logic tương thích cũ khi backlog/retention và chính sách replay cho phép.

Nếu thêm field bắt buộc không có default an toàn, có thể cần topic/schema version mới, migration record cũ hoặc bước chuyển tiếp. Một thay đổi có thể chạy tốt trên dữ liệu hiện tại nhưng vẫn thất bại khi phát lại dữ liệu cũ từ DLT hoặc backup.

Đừng gộp “producer và consumer deploy cùng thời điểm” làm giả định về tính tương thích. Trong distributed system, một số instance có thể chạy phiên bản cũ lâu hơn dự kiến.

## 22. Unknown field có thể che giấu lỗi dữ liệu

Tolerant reader là chiến lược hữu ích, nhưng bỏ qua mọi trường lạ có thể khiến producer gửi sai tên property mà không được phát hiện.

Ví dụ producer vô tình gửi `amunt` thay vì `amount`:

~~~json
{
  "eventId": "evt-008",
  "orderId": "ord-106",
  "amunt": 150000
}
~~~

Nếu consumer ignore unknown field, nó bỏ `amunt` và đồng thời thấy `amount` missing. Nếu missing field không được kiểm tra, `amount` có thể thành null hoặc 0, gây lỗi nghiệp vụ.

Có thể giảm rủi ro bằng cách:

- Kiểm tra các required field ngay khi deserialize hoặc validate.
- Chỉ cho phép unknown field trên những event được thiết kế mở rộng.
- Theo dõi schema/version mismatch ở producer/consumer.
- Dùng schema contract test trong CI.
- Ghi metric cho producer version nếu event chứa version marker.
- Phân biệt lỗi malformed payload với lỗi nghiệp vụ downstream.

Nếu muốn biết tần suất xuất hiện unknown field khi mapper đang ignore chúng, cần instrument parser, validation hoặc schema diff. Không giả định Jackson luôn phát metric cho field đã bỏ qua.

## 23. Kiểm thử trong Spring Kafka

Kiểm thử nên có cả hai hướng schema evolution, không chỉ một JSON mẫu “đúng”.

| Trường hợp | Payload | Kết quả mong đợi |
|---|---|---|
| Unknown field, tolerant reader | Có couponCode mới | Deserialize thành công; field không dùng bị bỏ qua |
| Unknown field, strict reader | Có couponCode mới | Deserialization failure |
| Missing optional field | Không có couponCode | Default hoặc null đã định nghĩa |
| Missing required creator property | Thiếu orderId | Deserialization failure |
| Missing required business field | Thiếu currency | Validation/recovery theo policy |
| Explicit null | `"currency":null` | Theo rule null riêng |
| Wrong type | `"amount":"abc"` | Lỗi chuyển đổi kiểu |
| Typo property | `amunt` | Không silently tạo amount hợp lệ |
| Unknown enum | `"status":"ON_HOLD"` | Fallback có chủ đích hoặc DLT |
| JSON malformed | Thiếu dấu ngoặc, sai encoding | ErrorHandlingDeserializer/recovery |
| DLT re-drive | Dữ liệu v1 phát lại vào consumer v2 | Không mất event; policy hợp lệ |

Unit test mapper có thể kiểm tra tương thích cơ bản:

~~~java
@Test
void ignoresNewOptionalPropertyWhenConfigured() throws Exception {
    String json = """
        {"eventId":"evt-1","orderId":"ord-1",
         "amount":100,"couponCode":"SAVE10"}
        """;

    ObjectMapper mapper = JsonMapper.builder()
            .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
            .build();

    OrderCreatedV1 event =
            mapper.readValue(json, OrderCreatedV1.class);

    assertThat(event.orderId()).isEqualTo("ord-1");
}
~~~

Đây là Java text block (Java 15+). `OrderCreatedV1` là record đã định nghĩa ở trên. Các import JUnit/AssertJ tùy test stack.

Test tích hợp với Embedded Kafka hoặc Testcontainers cần xác nhận hành vi thực tế của JsonDeserializer, ErrorHandlingDeserializer, listener container, DefaultErrorHandler và DLT. Đặc biệt, record lỗi trước khi listener được gọi có thể cần value serializer khác khi recoverer publish sang DLT.

## 24. Quan sát unknown/missing field trong production

Một hệ thống có schema evolution tốt cần phân biệt các lỗi:

**Deserialization**

- Số lỗi parse JSON, type mismatch, unknown strict field.
- Số lỗi missing creator property hoặc enum không được hỗ trợ.
- Tỷ lệ lỗi theo topic, event type, producer version và consumer version.
- Số record có deserialization header được chuyển DLT.

**Validation**

- Số record thiếu required business field.
- Số record có explicit null không hợp lệ.
- Tỷ lệ lỗi theo field code, không ghi toàn bộ payload.
- Số event cần fallback giá trị mặc định.

**Vận hành**

- Consumer lag, retry count và DLT growth.
- Thời gian từ sự kiện phát ra đến khi được xử lý thành công.
- Số record re-drive thành công/thất bại.
- Lỗi producer serializer và compatibility check trong CI.

Log cần có eventId, topic, partition, offset, schema/version marker, exception class và mã lỗi ngắn. Tránh log toàn bộ payload chứa dữ liệu cá nhân; có thể trích tên field lỗi khi an toàn.

Không tự động retry vô hạn một record có field bị thiếu cố định. Nếu dữ liệu không thể tự sửa, chuyển DLT và điều tra producer/schema. Với lỗi transient như Schema Registry tạm thời không truy cập được, có thể retry theo chính sách riêng; cần phân biệt với payload thật sự không hợp lệ.

## 25. Quy trình xử lý sự cố

Khi consumer mới triển khai và tỷ lệ lỗi deserialize tăng:

1. Xác định topic, partition, offset và event type bị lỗi.
2. Phân biệt unknown field, missing field, explicit null, sai kiểu và JSON malformed.
3. Kiểm tra producer version/schema ID và consumer version.
4. Kiểm tra ObjectMapper/JsonDeserializer thực tế: strict hay tolerant, type headers và trusted packages.
5. Nếu lỗi xảy ra trước listener, kiểm tra ErrorHandlingDeserializer và DLT producer.
6. Nếu deserialize thành công nhưng nghiệp vụ lỗi, kiểm tra validation và default policy.
7. Đánh giá có thể rollout tolerant reader an toàn hay phải yêu cầu producer sửa event.
8. Giữ eventId và original metadata để re-drive có kiểm soát.
9. Sau khi sửa schema/logic, phát lại tập record lỗi nhỏ trước rồi mới mở rộng.
10. Bổ sung contract test để tránh tái diễn lỗi cùng loại.

Không sửa dữ liệu DLT theo cách xóa trường một cách máy móc mà chưa hiểu ý nghĩa. Với trường bắt buộc, bổ sung một default không đúng có thể tạo lỗi nghiệp vụ không thể đảo ngược.

## 26. Nguyên tắc áp dụng

- Xem unknown field và missing field là hai chiều tương thích khác nhau.
- Dùng tolerant reader cho trường mới không ảnh hưởng nghiệp vụ; dùng strict reader khi hợp đồng đòi hỏi từ chối trường lạ.
- Không mặc định Jackson luôn ignore unknown field: kiểm tra ObjectMapper thực tế.
- Với missing field, xác định rõ optional/default/required theo nghiệp vụ.
- Phân biệt vắng mặt với explicit null khi ý nghĩa của chúng khác nhau.
- Đừng dùng primitive default 0/false nếu cần biết producer có gửi trường hay không.
- Dùng creator validation, Bean Validation hoặc schema rule cho field bắt buộc.
- Xác định rõ hướng backward/forward compatibility và thứ tự rollout.
- Dùng ErrorHandlingDeserializer để lỗi trước listener đi vào luồng recovery.
- Chuyển lỗi schema cố định sang DLT thay vì retry vô hạn.
- Chuẩn bị DLT producer xử lý payload lỗi có thể là raw bytes.
- Đối với Avro, kiểm tra reader/writer schema và default; đối với Protobuf, kiểm tra field number và presence.
- Giữ eventId và thiết kế consumer idempotent cho retry/replay.
- Kiểm thử cả record cũ và mới, dữ liệu thiếu, null, enum mới, malformed payload và DLT re-drive.

Unknown field không nhất thiết là lỗi nếu consumer được thiết kế để chấp nhận phiên bản producer mới. Missing field cũng không nhất thiết là lỗi nếu hợp đồng đã định nghĩa một default đúng. Độ tin cậy của Spring Kafka phụ thuộc vào việc phân biệt hai trường hợp này, bảo vệ required business data, quản lý schema evolution có chủ đích và bảo đảm những record không thể deserialize hoặc validate được đưa vào luồng recovery có thể quan sát.
