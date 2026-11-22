# Xác định chính sách cho thuộc tính không nhận diện

Khi Jackson đọc một JSON object và gặp một tên thuộc tính không khớp với property nào của kiểu Java đích, ứng dụng cần có một chính sách rõ ràng. Có thể từ chối payload để bảo vệ hợp đồng, bỏ qua field lạ để tương thích với phiên bản producer mới hơn, giữ field đó để chuyển tiếp, hoặc xử lý một số tên động theo allowlist. Mỗi lựa chọn ảnh hưởng đến khả năng tương thích, an toàn dữ liệu, khả năng quan sát và cách API tiến hóa.

Trong Jackson Databind, hành vi cơ bản được điều khiển bởi `DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES`. Ngoài cấu hình mapper, có thể dùng `@JsonIgnoreProperties`, `@JsonAnySetter` hoặc `DeserializationProblemHandler` để định nghĩa chính sách theo kiểu dữ liệu hoặc theo logic ứng dụng.

Điều quan trọng là phân biệt **thuộc tính không nhận diện** với **thuộc tính đã nhận diện nhưng có giá trị sai kiểu**. Ví dụ, DTO có field `quantity` kiểu `int` nhưng JSON gửi chuỗi không chuyển đổi được; đây là lỗi mapping của property đã biết, không phải unknown property. Tắt `FAIL_ON_UNKNOWN_PROPERTIES` không làm cho dữ liệu sai kiểu trở nên hợp lệ.

## 1. Thuộc tính không nhận diện là gì?

Giả sử DTO chỉ khai báo:

~~~java
public class CustomerRequest {
    private String name;
    private String email;

    // Getter và setter.
}
~~~

Nhưng JSON gửi đến có thêm:

~~~json
{
  "name": "Lan",
  "email": "lan@example.com",
  "preferredLanguage": "vi",
  "marketingSource": "campaign-2026"
}
~~~

Nếu Jackson không tìm thấy property, setter, field, creator parameter, alias hoặc any-setter phù hợp cho `preferredLanguage` và `marketingSource`, chúng được xem là thuộc tính không nhận diện đối với `CustomerRequest`.

Một thuộc tính có thể bị xem là unknown do:

- DTO thực sự chưa có field tương ứng.
- JSON dùng tên khác với tên Java và chưa khai báo `@JsonProperty` hoặc `@JsonAlias`.
- Naming strategy giữa producer và consumer không khớp.
- Getter/setter không được Jackson nhận diện do visibility hoặc cấu hình accessor.
- Property bị loại khỏi quá trình deserialize bởi annotation hoặc mix-in.
- Consumer đang dùng phiên bản DTO cũ hơn schema của producer.

Trước khi quyết định bỏ qua hay từ chối, hãy xác nhận field đó thực sự không thuộc hợp đồng hiện tại. Một lỗi chính tả như `customerNmae` thay vì `customerName` cũng có thể trông giống một field mới.

## 2. Hành vi mặc định của Jackson

Với một `ObjectMapper` Jackson Databind được tạo trực tiếp và không thay đổi cấu hình, `DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES` được bật mặc định. Khi một object chứa property không nhận diện, Jackson thường ném `UnrecognizedPropertyException`, một loại `JsonMappingException`.

Ví dụ:

~~~java
ObjectMapper mapper = new ObjectMapper();

CustomerRequest request = mapper.readValue(
    json,
    CustomerRequest.class
);
~~~

Nếu JSON có `preferredLanguage` nhưng DTO không có property tương ứng và không có cơ chế xử lý unknown property, thao tác có thể thất bại với lỗi tương tự:

~~~text
Unrecognized field "preferredLanguage"
(class CustomerRequest), not marked as ignorable
~~~

Lỗi này có ích khi API muốn schema đóng: client gửi field sai tên hoặc field không được hỗ trợ sẽ nhận lỗi sớm. Nó cũng giúp phát hiện producer và consumer không đồng bộ.

Tuy nhiên, mặc định của một `ObjectMapper` được tạo trực tiếp không nhất thiết giống cấu hình của framework. Spring Boot, thư viện tích hợp hoặc cấu hình mapper riêng có thể bật/tắt feature. Vì vậy, hãy kiểm tra mapper thực sự đang được dùng thay vì suy luận từ hành vi của một unit test độc lập.

## 3. Bốn chính sách thường gặp

Có thể chia cách xử lý unknown property thành bốn nhóm:

| Chính sách | Hành vi | Lợi ích chính | Rủi ro hoặc chi phí |
|---|---|---|---|
| Strict / reject | Từ chối khi gặp field không nhận diện | Phát hiện sai schema và typo sớm | Consumer cũ có thể hỏng khi producer thêm field |
| Ignore / skip | Bỏ qua field không nhận diện | Tương thích với field mới không ảnh hưởng consumer | Có thể che giấu typo hoặc dữ liệu cần thiết |
| Capture / preserve | Thu field lạ vào map hoặc cây JSON | Giữ dữ liệu để lưu trữ/chuyển tiếp | Cần giới hạn, validate và kiểm soát rò rỉ |
| Selective handling | Chỉ xử lý các key động được cho phép | Linh hoạt nhưng vẫn kiểm soát | Cần allowlist và logic bổ sung |

Không có chính sách nào đúng cho mọi loại payload. Ví dụ, request thanh toán hoặc lệnh thay đổi quyền có thể cần strict schema. Event relay có thể cần giữ field mới để forward. Một webhook từ đối tác có thể bỏ qua metadata không dùng đến nhưng vẫn phải kiểm tra những field nghiệp vụ bắt buộc.

## 4. Chính sách strict bằng FAIL_ON_UNKNOWN_PROPERTIES

Nếu payload phải khớp chính xác với DTO, hãy giữ hoặc bật feature:

~~~java
ObjectMapper strictMapper = JsonMapper.builder()
    .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
    .build();
~~~

Khi parse:

~~~java
CustomerRequest request = strictMapper.readValue(
    json,
    CustomerRequest.class
);
~~~

Cách này phù hợp với:

- Command thay đổi trạng thái hoặc dữ liệu nhạy cảm.
- Hợp đồng nội bộ có version đồng bộ và được kiểm soát.
- Payload mà field sai tên có thể làm thay đổi ý nghĩa nghiệp vụ.
- Những API muốn phát hiện client gửi dữ liệu ngoài hợp đồng.
- Các DTO mà mọi field được gửi đều cần được xử lý rõ ràng.

Strict mode giúp lỗi xuất hiện gần đầu vào thay vì âm thầm bỏ field. Nếu producer gửi nhầm `accountId` thành `acountId`, ứng dụng có thể từ chối thay vì tiếp tục với account ID bị thiếu.

### 4.1. Chỉ bật strict cho một kiểu hoặc một luồng đọc

Không nhất thiết phải thay đổi mapper toàn cục. Có thể tạo reader riêng:

~~~java
ObjectReader strictCustomerReader = mapper
    .readerFor(CustomerRequest.class)
    .with(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
~~~

Dùng reader:

~~~java
CustomerRequest request = strictCustomerReader.readValue(json);
~~~

Cách này hữu ích khi cùng ứng dụng có nhiều hợp đồng: một số request cần strict, trong khi một số event forward-compatible có thể bỏ qua field mới. Reader được tạo từ mapper đã cấu hình và có thể được tái sử dụng.

Đừng bật/tắt feature trên một mapper singleton theo từng request. Thay đổi cấu hình mapper dùng chung trong khi nhiều thread đang deserialize có thể khiến hành vi khó dự đoán. Hãy tạo reader có cấu hình riêng hoặc mapper riêng khi thực sự cần chính sách khác nhau.

## 5. Bỏ qua field lạ ở cấp mapper

Nếu consumer chỉ cần các field mà DTO đã biết và có thể bỏ qua field mới, hãy tắt feature:

~~~java
ObjectMapper tolerantMapper = JsonMapper.builder()
    .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
    .build();
~~~

Hoặc dùng reader riêng:

~~~java
ObjectReader tolerantReader = mapper
    .readerFor(CustomerRequest.class)
    .without(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
~~~

Khi đó, field không nhận diện được bỏ qua trong quá trình đọc. Các field đã biết vẫn được ánh xạ và kiểm tra kiểu như bình thường.

Ví dụ, JSON có thêm `marketingSource` sẽ được đọc thành `CustomerRequest` với `name` và `email`. Field `marketingSource` không được giữ lại trong object.

### 5.1. Bỏ qua không có nghĩa là chấp nhận mọi dữ liệu

Tắt `FAIL_ON_UNKNOWN_PROPERTIES` chỉ thay đổi cách xử lý field không nhận diện. Nó không vô hiệu hóa mọi lỗi deserialize:

- Field đã biết nhưng sai kiểu vẫn có thể gây mapping exception.
- JSON sai cú pháp vẫn gây parse exception.
- Constructor hoặc creator có thể từ chối dữ liệu.
- Custom deserializer có thể tự ném lỗi.
- Validation nghiệp vụ vẫn phải được thực hiện sau khi tạo DTO.
- Giới hạn parser và giới hạn request vẫn có hiệu lực.

Không nên dùng tolerant mode như cách bỏ qua mọi lỗi đầu vào.

### 5.2. Rủi ro che giấu typo

Nếu DTO có `customerName` nhưng producer gửi `custmerName`, tolerant mode có thể bỏ qua field sai. Kết quả là `customerName` có thể null hoặc mang giá trị mặc định. Lỗi chỉ xuất hiện muộn hơn ở validation hoặc nghiệp vụ.

Vì vậy, nếu chọn ignore unknown, hãy bảo đảm các field quan trọng được kiểm tra bằng validation và có test cho những tên property dễ nhầm. Tolerant mode phù hợp nhất khi field mới thực sự có thể xuất hiện mà không ảnh hưởng ý nghĩa của các field đã biết.

## 6. Bỏ qua field lạ cho một DTO bằng @JsonIgnoreProperties

Nếu chỉ một kiểu DTO cần tolerant mode, có thể dùng annotation:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public class CustomerRequest {
    private String name;
    private String email;

    // Getter và setter.
}
~~~

Annotation này yêu cầu Jackson bỏ qua các property không được nhận diện khi deserialize kiểu đó, ngay cả khi mapper đang bật `FAIL_ON_UNKNOWN_PROPERTIES`.

Điều này phù hợp khi:

- DTO đại diện cho payload từ một nguồn có thể thêm metadata.
- Kiểu đó có hợp đồng tolerant rõ ràng.
- Không muốn thay đổi chính sách unknown property của các DTO khác.

### 6.1. Bỏ qua một số tên cụ thể

`@JsonIgnoreProperties` cũng có thể liệt kê các property cần bỏ qua:

~~~java
@JsonIgnoreProperties({"legacyFlag", "deprecatedMetadata"})
public class CustomerRequest {
    private String name;
    private String email;
}
~~~

Cách này phù hợp khi một số field cũ được biết rõ và không còn được sử dụng. Các field khác vẫn chịu chính sách unknown property chung của mapper.

Cần phân biệt:

- `ignoreUnknown = true`: bỏ qua mọi field không nhận diện.
- `value = {...}`: bỏ qua các tên cụ thể được liệt kê.

Annotation có thể được đặt trên class hoặc mix-in. Nếu class thuộc thư viện bên thứ ba, mix-in cho phép áp dụng chính sách mà không sửa nguồn class.

### 6.2. Annotation không làm mất yêu cầu validation

Nếu field bắt buộc như `email` bị thiếu, `ignoreUnknown = true` không làm field đó hợp lệ. Nó chỉ bỏ qua tên lạ. Hãy tiếp tục dùng Bean Validation hoặc kiểm tra application-level cho những property đã biết.

## 7. Capture field lạ bằng @JsonAnySetter

Nếu không muốn bỏ dữ liệu chưa biết, có thể thu chúng vào map bằng `@JsonAnySetter`.

~~~java
import com.fasterxml.jackson.annotation.JsonAnySetter;
import com.fasterxml.jackson.databind.JsonNode;
import java.util.LinkedHashMap;
import java.util.Map;

public class PartnerEvent {
    private String eventId;
    private String eventType;
    private final Map<String, JsonNode> extensions = new LinkedHashMap<>();

    public String getEventId() {
        return eventId;
    }

    public void setEventId(String eventId) {
        this.eventId = eventId;
    }

    public String getEventType() {
        return eventType;
    }

    public void setEventType(String eventType) {
        this.eventType = eventType;
    }

    @JsonAnySetter
    public void addExtension(String name, JsonNode value) {
        extensions.put(name, value);
    }

    public Map<String, JsonNode> getExtensions() {
        return extensions;
    }
}
~~~

Khi Jackson đọc:

~~~json
{
  "eventId": "evt-1001",
  "eventType": "order.created",
  "partnerRegion": "south",
  "retryCount": 2,
  "metadata": {
    "source": "partner-a"
  }
}
~~~

Các field đã biết được gán vào property tĩnh; những field còn lại được chuyển tới any-setter và lưu trong map.

Dùng `Map<String, JsonNode>` giúp giữ loại JSON rõ ràng: string, number, boolean, null, array và object. Nếu dùng `Map<String, Object>`, kiểu Java runtime của số có thể thay đổi theo giá trị và cấu hình deserialization, khiến code cần nhiều kiểm tra `instanceof` hơn.

### 7.1. Flatten extension khi serialize

Có thể dùng `@JsonAnyGetter` để ghi map thành các property cùng cấp:

~~~java
@JsonAnyGetter
public Map<String, JsonNode> any() {
    return extensions;
}
~~~

JSON đầu ra có dạng:

~~~json
{
  "eventId": "evt-1001",
  "eventType": "order.created",
  "partnerRegion": "south",
  "retryCount": 2,
  "metadata": {
    "source": "partner-a"
  }
}
~~~

Nếu không dùng `@JsonAnyGetter`, map có thể xuất hiện dưới property `extensions`. Hai hình thức có hợp đồng khác nhau. Hãy chọn rõ việc extension được flatten hay được bọc trong object riêng.

### 7.2. Giới hạn và kiểm tra extension

Một map mở không nên nhận dữ liệu không giới hạn. Any-setter có thể kiểm tra tên và số lượng key:

~~~java
private static final int MAX_EXTENSION_COUNT = 50;
private static final int MAX_KEY_LENGTH = 80;

@JsonAnySetter
public void addExtension(String name, JsonNode value) {
    if (name == null || name.isBlank() || name.length() > MAX_KEY_LENGTH) {
        throw new IllegalArgumentException("Invalid extension name");
    }

    if (!extensions.containsKey(name)
            && extensions.size() >= MAX_EXTENSION_COUNT) {
        throw new IllegalArgumentException("Too many extension properties");
    }

    extensions.put(name, value);
}
~~~

Đây chỉ là giới hạn ở mức DTO sau khi Jackson đã đọc property. Cần kết hợp giới hạn body, độ sâu lồng nhau, độ dài chuỗi/số và thời gian xử lý ở tầng parser/server.

Không tự động áp dụng extension map vào entity bằng reflection. Một field lạ như `role`, `isAdmin` hoặc `accountStatus` không được phép thay đổi quyền hoặc trạng thái chỉ vì nó xuất hiện trong JSON.

## 8. Xử lý có chọn lọc bằng DeserializationProblemHandler

Đôi khi ứng dụng muốn nhận biết unknown property nhưng không muốn đưa tất cả vào DTO. Ví dụ:

- Bỏ qua một số field metadata đã biết.
- Từ chối các tên có prefix nhạy cảm.
- Ghi nhận metric khi producer gửi field mới.
- Cho phép field lạ chỉ trên một nhóm class.
- Chuyển unknown property thành lỗi có message riêng.

Jackson cung cấp `DeserializationProblemHandler` để xử lý các tình huống mà Databind không thể giải quyết theo cách thông thường.

Ví dụ handler bỏ qua unknown property sau khi ghi nhận tên:

~~~java
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JsonDeserializer;
import com.fasterxml.jackson.databind.deser.DeserializationProblemHandler;
import java.io.IOException;

public final class UnknownFieldHandler
        extends DeserializationProblemHandler {

    @Override
    public boolean handleUnknownProperty(
            DeserializationContext context,
            JsonParser parser,
            JsonDeserializer<?> deserializer,
            Object beanOrClass,
            String propertyName) throws IOException {

        if (beanOrClass == null) {
            return false;
        }
        Class<?> targetType = beanOrClass instanceof Class<?> type
            ? type
            : beanOrClass.getClass();
        if (!CustomerRequest.class.isAssignableFrom(targetType)) {
            return false;
        }

        // Ghi metric hoặc diagnostic event theo chính sách.
        parser.skipChildren();
        return true;
    }
}
~~~

Đăng ký handler:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .addHandler(new UnknownFieldHandler())
    .build();
~~~

Khi handler trả về `true`, nó cho Jackson biết property đã được xử lý. Nếu chỉ muốn bỏ qua giá trị, gọi `parser.skipChildren()` để tiêu thụ object/array con của property hiện tại trước khi trả về true. Nếu trả về `false`, handler từ chối xử lý và Jackson tiếp tục các handler khác hoặc áp dụng chính sách unknown property mặc định.

### 8.1. Phạm vi tác động của problem handler

Handler đăng ký trên mapper có thể được gọi cho nhiều kiểu dữ liệu. Vì vậy, nếu chỉ muốn áp dụng cho một DTO, hãy kiểm tra `beanOrClass` hoặc dùng mapper/reader có phạm vi hẹp.

Không ghi mọi tên field tùy ý thành label metric. Một client có thể gửi hàng nghìn tên khác nhau và tạo cardinality lớn. Có thể đếm tổng số unknown property theo endpoint/loại DTO, hoặc chỉ ghi tên từ tập nhỏ được kiểm soát. Không log raw value vì có thể chứa dữ liệu nhạy cảm.

Nếu chỉ cần bỏ qua mọi field lạ, `FAIL_ON_UNKNOWN_PROPERTIES` hoặc `@JsonIgnoreProperties(ignoreUnknown = true)` đơn giản hơn. Dùng handler khi thực sự cần logic tùy chỉnh.

## 9. Thứ tự xử lý và các cơ chế tương tác

Jackson có nhiều cơ chế để giải quyết một property. Một field đã được nhận diện bằng setter, field, creator property, alias hoặc mix-in sẽ được xử lý theo cơ chế đó. `@JsonAnySetter` nhận những property còn lại chưa được xử lý như property thông thường. Problem handler được gọi trong luồng xử lý unknown property khi các cơ chế thông thường không xử lý được.

Nếu không có cơ chế nào xử lý property:

- `FAIL_ON_UNKNOWN_PROPERTIES` bật: Jackson ném lỗi.
- Feature tắt: Jackson bỏ qua property và bỏ qua nội dung con.
- Annotation hoặc handler có thể thay đổi kết quả theo phạm vi áp dụng.

Một số annotation như `@JsonIgnoreProperties` có thể đánh dấu property cụ thể là ignorable. Đây là chính sách riêng, khác với việc một property hoàn toàn không được biết đến.

Khi debug, hãy kiểm tra cấu hình và annotation thực tế của DTO. Đừng giả định handler sẽ nhận mọi field lạ nếu any-setter đã thu chúng trước đó.

## 10. Phân biệt unknown property với property sai kiểu

Giả sử DTO:

~~~java
public class PaymentRequest {
    private long amount;
    private String currency;

    // Getter và setter.
}
~~~

Payload A:

~~~json
{
  "amount": 1000,
  "currency": "VND",
  "traceLabel": "mobile"
}
~~~

`traceLabel` là unknown property nếu DTO không khai báo nó.

Payload B:

~~~json
{
  "amount": "one thousand",
  "currency": "VND"
}
~~~

`amount` là property đã biết nhưng giá trị không chuyển được thành `long` theo cấu hình. Tắt `FAIL_ON_UNKNOWN_PROPERTIES` không giải quyết lỗi này.

Payload C:

~~~json
{
  "amount": null,
  "currency": "VND"
}
~~~

Đây là property đã biết có giá trị null. Cách xử lý phụ thuộc kiểu đích, null handling, creator và cấu hình coercion.

Payload D:

~~~json
{
  "amount": 1000
}
~~~

Đây là trường hợp thiếu `currency`. Unknown property policy không quyết định field bắt buộc có được phép thiếu hay không. Cần validation hoặc constructor/creator phù hợp.

Phân biệt bốn trường hợp giúp chọn đúng công cụ: unknown policy, coercion/type handling, null policy và required-field validation.

## 11. Tên property không khớp: kiểm tra alias và naming strategy

Một field có thể bị xem là unknown vì tên JSON khác tên mà Jackson nhận diện.

Ví dụ producer gửi `customer_name`, còn DTO dùng `customerName`. Có thể khai báo:

~~~java
public class CustomerRequest {
    @JsonProperty("customer_name")
    private String customerName;
}
~~~

Hoặc chấp nhận cả tên mới và tên cũ:

~~~java
public class CustomerRequest {
    @JsonAlias({"customer_name", "client_name"})
    private String customerName;
}
~~~

`@JsonProperty` xác định tên property chính trong JSON; `@JsonAlias` cho phép các tên thay thế khi deserialize. Alias không nhất thiết thay đổi tên được ghi ra khi serialize.

Nếu mapper dùng `PropertyNamingStrategies.SNAKE_CASE`, hãy xác nhận producer cũng dùng quy ước tương ứng. Không nên tắt strict mode để che một lỗi naming mismatch có thể sửa được.

## 12. Chính sách theo loại hợp đồng

Có thể dùng các chính sách khác nhau cho từng nhóm dữ liệu:

| Loại payload | Chính sách thường phù hợp | Lý do |
|---|---|---|
| Command cập nhật tài khoản, quyền hoặc thanh toán | Strict | Field sai tên hoặc field ngoài hợp đồng cần được phát hiện |
| Request public có thể nhận metadata mới không ảnh hưởng nghiệp vụ | Ignore có kiểm soát | Cho phép producer bổ sung thông tin tương thích |
| Event relay cần chuyển tiếp field chưa biết | Capture/preserve | Consumer trung gian không làm mất dữ liệu mới |
| Webhook đối tác có tập extension được công bố | Selective handling | Chấp nhận key đã đăng ký, kiểm soát key còn lại |
| File import theo schema version | Strict theo version hoặc tolerant có migration | Cần biết dữ liệu thuộc schema nào |
| Log/event telemetry | Ignore hoặc capture theo giới hạn | Tránh làm hỏng pipeline vì field metadata mới, đồng thời kiểm soát kích thước |

Đây là hướng dẫn lựa chọn, không phải quy tắc cứng. Quyết định cuối cùng phải dựa trên hậu quả nếu field bị bỏ qua, được giữ lại hoặc bị từ chối.

## 13. Forward compatibility và schema evolution

Tolerant mode thường được dùng để hỗ trợ forward compatibility: producer thêm field mới, consumer cũ vẫn đọc được những field mà nó hiểu.

Ví dụ phiên bản 1:

~~~json
{
  "id": "evt-1",
  "type": "order.created"
}
~~~

Phiên bản 2 bổ sung:

~~~json
{
  "id": "evt-1",
  "type": "order.created",
  "region": "south"
}
~~~

Consumer phiên bản 1 có thể bỏ qua `region` nếu field đó không ảnh hưởng logic. Tuy nhiên, nếu field mới làm thay đổi ý nghĩa của event hoặc thay đổi quy tắc tính toán, việc bỏ qua có thể khiến consumer xử lý sai mà không báo lỗi.

Forward compatibility chỉ an toàn khi field mới là optional/additive và consumer cũ có thể bỏ qua nó mà vẫn giữ đúng semantics. Nếu schema thay đổi theo cách breaking, cần versioning hoặc một cơ chế tương thích rõ ràng.

### 13.1. Version schema trong envelope

Một event có thể chứa version:

~~~json
{
  "schemaVersion": 2,
  "eventType": "order.created",
  "payload": {
    "id": "evt-1",
    "region": "south"
  }
}
~~~

Application có thể chọn DTO/deserializer theo version:

~~~java
switch (schemaVersion) {
    case 1 -> mapper.readValue(payload, OrderCreatedV1.class);
    case 2 -> mapper.readValue(payload, OrderCreatedV2.class);
    default -> throw new UnsupportedSchemaVersionException(schemaVersion);
}
~~~

Nếu version không được hỗ trợ, từ chối rõ ràng thường an toàn hơn việc parse vào DTO cũ và bỏ qua các field có ý nghĩa mới.

### 13.2. Không nhầm tolerant parsing với backward compatibility hoàn chỉnh

Bỏ qua field lạ chỉ xử lý một chiều: consumer cũ nhận payload có thêm field. Nó không tự xử lý trường hợp producer bỏ field bắt buộc, đổi kiểu field, đổi semantics hoặc đổi tên mà không có alias. Các thay đổi đó cần migration, default value có chủ đích hoặc versioning.

## 14. Rủi ro bảo mật khi bỏ qua hoặc capture field lạ

Unknown property policy có thể ảnh hưởng đến an toàn dữ liệu.

### 14.1. Mass assignment

Nếu capture field lạ rồi áp dụng map vào entity hoặc object cấu hình bằng reflection, client có thể gửi tên property nhạy cảm như `role`, `isAdmin`, `ownerId` hoặc `balance`. Không dùng map mở làm cơ chế cập nhật tùy ý.

Hãy dùng allowlist và command có kiểu. Các field quyền, chủ sở hữu, trạng thái và số dư phải được kiểm soát bởi use case và authorization.

### 14.2. Rò rỉ dữ liệu khi phát lại extension

Nếu DTO dùng `@JsonAnyGetter`, mọi extension được giữ có thể xuất hiện lại trong JSON. Một field lạ có thể chứa token, dữ liệu cá nhân hoặc metadata nội bộ từ producer. Chỉ phát lại extension đã được phân loại và cho phép; response public nên dùng DTO riêng hoặc allowlist output.

### 14.3. Log dữ liệu không tin cậy

Không log nguyên giá trị unknown property. Payload có thể chứa secret, thông tin cá nhân, dữ liệu rất dài hoặc ký tự điều khiển. Nếu cần quan sát, ghi số lượng, tên field đã chuẩn hóa/được giới hạn và request ID.

### 14.4. DoS qua payload lớn hoặc nhiều field

Tắt strict mode không làm payload rẻ hơn. Parser vẫn phải đọc token và bỏ qua cấu trúc con. Cần giới hạn body, độ sâu lồng nhau, độ dài chuỗi/số, số lượng key, thời gian xử lý và số request đồng thời. Với capture mode, giới hạn số entry và kích thước extension còn quan trọng hơn.

## 15. Cấu hình trong Spring Boot

Spring Boot có thể cấu hình Jackson qua application properties. Với các phiên bản Boot hỗ trợ property tương ứng, có thể đặt:

~~~yaml
spring:
  jackson:
    deserialization:
      fail-on-unknown-properties: true
~~~

Để bỏ qua field không nhận diện trên mapper do Boot quản lý:

~~~yaml
spring:
  jackson:
    deserialization:
      fail-on-unknown-properties: false
~~~

Tên property ánh xạ tới `DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES`. Hãy xác nhận phiên bản Spring Boot và cấu hình mapper thực tế, đặc biệt khi ứng dụng tự khai báo `ObjectMapper` bean, `Jackson2ObjectMapperBuilderCustomizer` hoặc HTTP message converter riêng.

Nếu chỉ một DTO cần tolerant mode, `@JsonIgnoreProperties(ignoreUnknown = true)` thường diễn đạt phạm vi rõ hơn việc tắt feature toàn cục.

Không tạo `new ObjectMapper()` trong controller để áp dụng một chính sách riêng; mapper đó có thể thiếu module Java Time, custom serializer, naming strategy và các cấu hình chung. Dùng `ObjectReader` cho một luồng đọc riêng hoặc cấu hình DTO theo hợp đồng.

## 16. Kiểm tra mapper thực sự đang dùng

Khi một field lạ bị bỏ qua hoặc làm request thất bại ngoài dự kiến, hãy kiểm tra trạng thái feature:

~~~java
boolean failOnUnknown = mapper.isEnabled(
    DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES
);
~~~

Trong test, có thể assert cấu hình mong muốn:

~~~java
assertTrue(strictMapper.isEnabled(
    DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES
));

assertFalse(tolerantMapper.isEnabled(
    DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES
));
~~~

Trong ứng dụng Spring, cần kiểm tra mapper được inject vào converter hoặc component thực sự xử lý request. Một test tạo mapper mới có thể cho kết quả khác mapper production.

Nếu có nhiều mapper hoặc reader, hãy tài liệu hóa chính sách của từng ranh giới: REST request, event consumer, file import, webhook và internal message. Không giả định mọi JSON trong ứng dụng đều cần cùng một unknown-property policy.

## 17. Kiểm thử strict và tolerant policy

Một test đơn giản xác nhận strict mode từ chối field lạ:

~~~java
@Test
void strictMapperRejectsUnknownProperty() {
    ObjectMapper mapper = JsonMapper.builder()
        .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
        .build();

    String json = """
        {
          "name": "Lan",
          "email": "lan@example.com",
          "newField": true
        }
        """;

    assertThrows(
        UnrecognizedPropertyException.class,
        () -> mapper.readValue(json, CustomerRequest.class)
    );
}
~~~

Test tolerant mode:

~~~java
@Test
void tolerantMapperSkipsUnknownProperty() throws Exception {
    ObjectMapper mapper = JsonMapper.builder()
        .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
        .build();

    String json = """
        {
          "name": "Lan",
          "email": "lan@example.com",
          "newField": true
        }
        """;

    CustomerRequest request = mapper.readValue(json, CustomerRequest.class);

    assertEquals("Lan", request.getName());
    assertEquals("lan@example.com", request.getEmail());
}
~~~

Test annotation trên DTO:

~~~java
@Test
void dtoCanIgnoreUnknownFieldsIndependently() throws Exception {
    ObjectMapper mapper = JsonMapper.builder()
        .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
        .build();

    String json = """
        {
          "name": "Lan",
          "futureMetadata": {
            "source": "partner-a"
          }
        }
        """;

    CustomerRequest request = mapper.readValue(json, CustomerRequest.class);

    assertEquals("Lan", request.getName());
}
~~~

Test any-setter capture:

~~~java
@Test
void capturesUnknownPropertiesIntoExtensionMap() throws Exception {
    ObjectMapper mapper = new ObjectMapper();

    PartnerEvent event = mapper.readValue(
        """
        {
          "eventId": "evt-1",
          "eventType": "order.created",
          "retryCount": 2
        }
        """,
        PartnerEvent.class
    );

    assertEquals(2, event.getExtensions().get("retryCount").asInt());
}
~~~

Ngoài các test trên, nên xác nhận:

- Field đã biết vẫn được ánh xạ khi tolerant mode.
- Field đã biết sai kiểu vẫn gây lỗi mapping.
- Field bắt buộc thiếu vẫn bị validation từ chối.
- Any-setter áp dụng giới hạn key và kích thước.
- Problem handler chỉ tác động tới kiểu được chỉ định.
- Field unknown không bị phát lại ngoài ý muốn.
- DTO không liên quan vẫn giữ chính sách strict/tolerant của nó.

## 18. Ví dụ selective policy bằng ProblemHandler

Giả sử chỉ cho phép bỏ qua một vài field metadata đã biết trên `CustomerRequest`. Những tên lạ khác vẫn phải bị từ chối.

~~~java
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JsonDeserializer;
import com.fasterxml.jackson.databind.deser.DeserializationProblemHandler;
import java.io.IOException;
import java.util.Set;

public final class CustomerUnknownFieldHandler
        extends DeserializationProblemHandler {

    private static final Set<String> IGNORED_FIELDS = Set.of(
        "traceLabel",
        "clientBuild"
    );

    @Override
    public boolean handleUnknownProperty(
            DeserializationContext context,
            JsonParser parser,
            JsonDeserializer<?> deserializer,
            Object beanOrClass,
            String propertyName) throws IOException {

        if (beanOrClass == null) {
            return false;
        }
        Class<?> targetType = beanOrClass instanceof Class<?> type
            ? type
            : beanOrClass.getClass();
        if (!CustomerRequest.class.isAssignableFrom(targetType)) {
            return false;
        }

        if (!IGNORED_FIELDS.contains(propertyName)) {
            return false;
        }

        parser.skipChildren();
        return true;
    }
}
~~~

Mapper vẫn bật strict mode:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
    .addHandler(new CustomerUnknownFieldHandler())
    .build();
~~~

Với cấu hình này:

- `traceLabel` và `clientBuild` được handler xử lý và bỏ qua.
- Một field khác không nhận diện sẽ không được handler chấp nhận; Jackson tiếp tục áp dụng strict policy và ném lỗi.
- Các DTO khác không bị handler này bỏ qua field lạ.

Đây là cách dùng problem handler để tạo chính sách selective. Nếu danh sách bỏ qua chỉ áp dụng cho một class và có thể khai báo bằng annotation, `@JsonIgnoreProperties(value = {...})` có thể đơn giản hơn.

## 19. Những lỗi thường gặp

### Tắt strict mode toàn cục để sửa một request

Một field sai tên có thể bị bỏ qua âm thầm ở mọi DTO. Nếu chỉ một DTO cần tolerant mode, dùng annotation hoặc reader riêng.

### Nhầm unknown property với sai kiểu

`FAIL_ON_UNKNOWN_PROPERTIES` không xử lý chuỗi không parse được thành số, null không hợp lệ hoặc field bắt buộc bị thiếu. Xử lý từng loại ở đúng tầng.

### Bỏ qua field lạ nhưng không validate field bắt buộc

Payload có thể parse thành công nhưng thiếu dữ liệu quan trọng. Dùng Bean Validation và kiểm tra nghiệp vụ sau deserialize.

### Dùng @JsonAnySetter mà không giới hạn map

Client có thể gửi rất nhiều key, key dài hoặc cấu trúc lồng sâu. Giới hạn body, parser constraints và số entry extension.

### Capture rồi echo mọi field

Dữ liệu nhạy cảm hoặc metadata nội bộ có thể bị phát lại. Dùng output allowlist hoặc response DTO riêng.

### Dùng ProblemHandler cho mọi thứ

Handler toàn cục có thể làm các DTO khác bị ảnh hưởng. Kiểm tra kiểu đích và chỉ dùng khi cần logic tùy chỉnh.

### Cho rằng Spring Boot có cùng default với ObjectMapper mới

Framework có thể tùy chỉnh feature. Kiểm tra mapper production và test slice thực tế.

### Không nhận diện alias/naming mismatch

Một field hợp lệ có thể bị coi là unknown vì producer và consumer dùng tên khác. Dùng @JsonProperty, @JsonAlias hoặc naming strategy phù hợp.

### Bỏ qua field mới làm thay đổi semantics

Nếu field mới thay đổi cách hiểu event hoặc command, consumer cũ không thể an toàn chỉ bằng cách bỏ qua. Dùng schema version hoặc từ chối version chưa hỗ trợ.

## 20. Quy trình xác định chính sách unknown property

1. Xác định payload thuộc hợp đồng nào: command, response, event, webhook hay file import.
2. Kiểm tra tên field có phải typo hoặc naming mismatch không.
3. Xác định hậu quả nếu field bị bỏ qua, giữ lại hoặc từ chối.
4. Chọn strict, ignore, capture hoặc selective handling.
5. Nếu strict, bật `FAIL_ON_UNKNOWN_PROPERTIES` ở mapper/reader phù hợp.
6. Nếu ignore một DTO, dùng `@JsonIgnoreProperties(ignoreUnknown = true)` hoặc cấu hình reader riêng.
7. Nếu capture, dùng `@JsonAnySetter` với map có kiểu rõ ràng, giới hạn key và kiểm soát output.
8. Nếu selective, dùng danh sách key cụ thể hoặc `DeserializationProblemHandler` có phạm vi hẹp.
9. Tách unknown-property policy khỏi type coercion, null handling và required-field validation.
10. Kiểm tra mapper thực tế của framework và mọi mapper/reader khác trong ứng dụng.
11. Xác định schema version và forward compatibility cho producer/consumer.
12. Đánh giá mass assignment, rò rỉ dữ liệu, log và giới hạn tài nguyên.
13. Viết test cho field mới, typo, sai kiểu, field thiếu, extension capture và response output.
14. Tài liệu hóa chính sách theo từng ranh giới dữ liệu để producer và consumer hiểu cùng một hợp đồng.

## 21. Bảng ghi nhớ

| Nhu cầu | Cách làm |
|---|---|
| Từ chối mọi field không nhận diện | Bật `DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES` |
| Bỏ qua field lạ cho một mapper/reader | `without(FAIL_ON_UNKNOWN_PROPERTIES)` |
| Bỏ qua field lạ trên một DTO | `@JsonIgnoreProperties(ignoreUnknown = true)` |
| Bỏ qua một số tên cụ thể | `@JsonIgnoreProperties(value = {...})` |
| Giữ field chưa biết | `@JsonAnySetter` với Map hoặc JsonNode |
| Ghi extension thành field cùng cấp | `@JsonAnyGetter` |
| Xử lý field lạ theo logic tùy chỉnh | `DeserializationProblemHandler` |
| Chấp nhận tên cũ/tên thay thế | `@JsonAlias` |
| Đổi tên JSON chính thức | `@JsonProperty` |
| Field đã biết nhưng sai kiểu | Type/coercion policy và validation |
| Field bắt buộc bị thiếu | Creator/Bean Validation/application validation |
| Payload có schema thay đổi lớn | Versioning và migration |
| Tránh ảnh hưởng mapper toàn cục | Reader hoặc mapper riêng, cấu hình trước khi dùng |

## 22. Kết luận

Thuộc tính không nhận diện là một phần của hợp đồng dữ liệu, không chỉ là một lỗi kỹ thuật của Jackson. Với hợp đồng đóng, strict mode qua `FAIL_ON_UNKNOWN_PROPERTIES` giúp phát hiện typo và schema mismatch sớm. Với payload cần forward compatibility, có thể bỏ qua field lạ bằng cấu hình mapper/reader hoặc `@JsonIgnoreProperties`. Nếu phải giữ dữ liệu để chuyển tiếp, dùng `@JsonAnySetter` với giới hạn và kiểm soát đầu ra. Khi cần xử lý một số key động có chọn lọc, `DeserializationProblemHandler` cho phép áp dụng logic riêng trong phạm vi phù hợp.

Hãy tách unknown-property policy khỏi lỗi sai kiểu, null và field bắt buộc; kiểm tra mapper thực tế thay vì giả định framework dùng default giống mapper mới; và đánh giá tác động đến bảo mật, mass assignment, rò rỉ dữ liệu, logging cùng giới hạn tài nguyên. Chọn chính sách theo từng hợp đồng và kiểm thử cả field mới lẫn typo để hệ thống vừa tương thích vừa không âm thầm chấp nhận dữ liệu sai.
