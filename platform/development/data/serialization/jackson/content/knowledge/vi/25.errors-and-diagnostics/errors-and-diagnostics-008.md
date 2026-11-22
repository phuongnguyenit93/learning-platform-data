# Báo lỗi theo trường mà không sao chép toàn bộ dữ liệu nhạy cảm

Khi Jackson không thể đọc một property, thông tin hữu ích nhất thường là **trường nào sai, lỗi thuộc loại nào và parser phát hiện ở vị trí nào**. Để điều tra lỗi, ứng dụng không cần sao chép toàn bộ request JSON vào log hoặc response. Payload có thể chứa mật khẩu, token, số tài khoản, thông tin cá nhân hoặc dữ liệu nghiệp vụ mà người vận hành không cần nhìn thấy.

Jackson cung cấp các thông tin có thể dùng để mô tả lỗi theo ngữ cảnh: JsonMappingException có mapping path, JsonLocation có line/column và offset, còn DeserializationContext cho phép tạo lỗi gắn với kiểu đích. Ứng dụng có thể kết hợp những thông tin đó với mã lỗi ổn định và một đường dẫn trường đã được lọc.

Mục tiêu là tạo ra log và response đủ để tìm lỗi, nhưng không đưa giá trị nhạy cảm hoặc toàn bộ nội dung đầu vào vào nơi lưu trữ rộng hơn.

## 1. Vì sao không nên log toàn bộ JSON khi có lỗi?

Giả sử API nhận một request thanh toán:

~~~json
{
  "customerId": "CUS-100",
  "cardNumber": "4111111111111111",
  "securityCode": "123",
  "billingAddress": {
    "street": "12 Nguyen Hue",
    "city": "Ho Chi Minh City"
  },
  "amount": "not-a-number"
}
~~~

Lỗi thực sự chỉ nằm ở trường amount: API mong đợi một JSON number nhưng nhận string. Nếu log toàn bộ request để chẩn đoán, hệ thống còn lưu cả số thẻ, security code và địa chỉ.

Một log như sau đã đủ hữu ích hơn:

~~~text
event=JSON_MAPPING_FAILED
requestId=req-7f31
field=$.amount
errorCode=INVALID_NUMBER
line=6
column=13
~~~

Log này cho biết request nào thất bại, field nào sai, loại lỗi và vị trí gần lỗi. Nó không cần chứa giá trị amount, càng không cần chứa các field khác.

Những rủi ro khi sao chép payload vào log hoặc thông báo lỗi:

- **Lộ dữ liệu nhạy cảm**: log thường được gửi đến nhiều hệ thống và có nhiều người truy cập hơn dữ liệu nghiệp vụ.
- **Tạo thêm bản sao dữ liệu**: request body có thể xuất hiện trong application log, reverse proxy, tracing, APM và hệ thống tập trung.
- **Khó kiểm soát thời gian lưu trữ**: log có thể được giữ lâu hơn dữ liệu gốc.
- **Tăng kích thước log**: payload lớn làm tăng chi phí lưu trữ và gây khó tìm kiếm.
- **Lộ dữ liệu qua exception**: một số exception chuyển đổi kiểu có thể giữ lại giá trị đầu vào trong object hoặc message.

Hãy thiết kế thông tin lỗi dựa trên những gì người vận hành cần biết, thay vì ghi lại toàn bộ request theo thói quen.

## 2. Những thông tin Jackson có thể cung cấp

### 2.1. Mapping path

JsonMappingException giữ đường dẫn Jackson đã đi qua khi ánh xạ dữ liệu. Các thành phần đường dẫn có thể là:
- Tên property.
- Index của phần tử trong array/list.
- Đối tượng hoặc kiểu chứa property đó.

Các API thường dùng:

| API | Thông tin |
|---|---|
| getPath() | Danh sách các phần tử path |
| getPathReference() | Chuỗi mô tả path để chẩn đoán |
| getLocation() | Vị trí trong nguồn JSON |
| getOriginalMessage() | Thông điệp gốc của lỗi |

Ví dụ, với JSON:

~~~json
{
  "order": {
    "items": [
      {"sku": "KB-01", "quantity": 2},
      {"sku": "MS-02", "quantity": "many"}
    ]
  }
}
~~~

Path có thể chỉ đến property order, collection items, phần tử index 1 và property quantity.

Path giúp xác định trường gây lỗi mà không cần log các giá trị của object.

### 2.2. JsonLocation

JsonLocation có thể cung cấp:
- Line number.
- Column number.
- Byte offset.
- Character offset.
- Source reference.

Line, column và offset thường hữu ích để tìm vị trí parser phát hiện vấn đề. Nhưng không nên mặc nhiên ghi mọi trường của JsonLocation. Đặc biệt, source reference có thể mô tả nguồn hoặc chứa nội dung đầu vào tùy loại parser và cấu hình.

Để log an toàn, thường chỉ cần lấy các số line, column và offset nếu có. Không gọi location.toString() hoặc in source reference khi chưa hiểu nó chứa gì.

### 2.3. Exception có thể giữ giá trị đầu vào

Một số exception chuyển đổi, chẳng hạn InvalidFormatException, có method getValue() để truy xuất giá trị không chuyển đổi được. Đây là thông tin hữu ích khi debug cục bộ, nhưng có thể chứa dữ liệu nhạy cảm.

Không nên log trực tiếp:

~~~java
logger.warn("Invalid value: {}", exception.getValue());
~~~

Cũng không nên mặc định log toàn bộ exception.getMessage() hoặc exception.toString(). Message do Jackson hoặc custom deserializer tạo có thể chứa tên field, giá trị bị từ chối, source description hoặc thông tin khác mà ứng dụng không muốn phát tán.

Hãy ghi mã lỗi và metadata do ứng dụng kiểm soát. Nếu cần điều tra sâu hơn, sử dụng một kênh debug được giới hạn quyền và có chính sách lưu trữ phù hợp.

## 3. Phân biệt field path với giá trị field

Một thông báo lỗi tốt nên mô tả điều kiện mong đợi, không cần lặp lại dữ liệu đã gửi.

Ví dụ:

~~~text
Property 'quantity' must be a positive integer
~~~

Thông báo này hữu ích vì nêu:
- Tên property.
- Kiểu dữ liệu mong đợi.
- Điều kiện cơ bản của representation.

Thông báo sau kém an toàn hơn:

~~~text
Cannot parse quantity value 'customer-secret-123' as integer
~~~

Nó đưa chính giá trị đầu vào vào message. Nếu message được ghi log, gửi cho client hoặc lưu trong error tracking, dữ liệu đã bị sao chép.

Trong custom deserializer, nên viết message tĩnh hoặc dùng tên field đã được kiểm soát:

~~~java
if (token != JsonToken.VALUE_NUMBER_INT) {
    throw JsonMappingException.from(
            parser,
            "Property 'quantity' must be an integer"
    );
}
~~~

Không nối parser.getText(), node.toString() hoặc raw request vào message. Khi cần biểu diễn field path, hãy cân nhắc lọc tên property trước khi đưa vào log.

## 4. Tạo mapping exception mà không đưa giá trị nhạy cảm vào message

JsonMappingException.from(parser, message) tạo lỗi có thể gắn location của parser hiện tại:

~~~java
throw JsonMappingException.from(
        parser,
        "Property 'accountNumber' must be a string"
);
~~~

Cách này thường phù hợp khi custom deserializer phát hiện token sai kiểu.

Có thể dùng DeserializationContext.reportInputMismatch() để báo input không phù hợp với kiểu đích:

~~~java
return context.reportInputMismatch(
        PaymentRequest.class,
        "Property '%s' must be a decimal number",
        "amount"
);
~~~

Hoặc dùng handleUnexpectedToken() khi token hiện tại không đúng loại mà deserializer mong đợi:

~~~java
if (!parser.hasToken(JsonToken.START_OBJECT)) {
    return (PaymentRequest) context.handleUnexpectedToken(
            PaymentRequest.class,
            parser
    );
}
~~~

Các API này giúp Jackson tạo lỗi theo ngữ cảnh data binding. Dù vậy, ứng dụng vẫn phải kiểm soát message mình truyền vào. Không đưa raw value hoặc toàn bộ JSON vào message chỉ để làm lỗi dễ đọc hơn.

### 4.1. Ví dụ deserializer kiểm tra kiểu và báo lỗi an toàn

~~~java
public class PaymentRequestDeserializer
        extends StdDeserializer<PaymentRequest> {

    public PaymentRequestDeserializer() {
        super(PaymentRequest.class);
    }

    @Override
    public PaymentRequest deserialize(
            JsonParser parser,
            DeserializationContext context
    ) throws IOException {

        if (!parser.isExpectedStartObjectToken()) {
            return (PaymentRequest) context.handleUnexpectedToken(
                    PaymentRequest.class,
                    parser
            );
        }

        String reference = null;
        BigDecimal amount = null;

        while (parser.nextToken() != JsonToken.END_OBJECT) {
            String field = parser.currentName();
            JsonToken token = parser.nextToken();

            if ("reference".equals(field)) {
                if (token != JsonToken.VALUE_STRING) {
                    throw JsonMappingException.from(
                            parser,
                            "Property 'reference' must be a string"
                    );
                }
                reference = parser.getText();

            } else if ("amount".equals(field)) {
                if (token != JsonToken.VALUE_NUMBER_INT
                        && token != JsonToken.VALUE_NUMBER_FLOAT) {
                    throw JsonMappingException.from(
                            parser,
                            "Property 'amount' must be a number"
                    );
                }
                amount = parser.getDecimalValue();

            } else {
                parser.skipChildren();
            }
        }

        if (reference == null) {
            throw JsonMappingException.from(
                    parser,
                    "Required property 'reference' is missing"
            );
        }
        if (amount == null) {
            throw JsonMappingException.from(
                    parser,
                    "Required property 'amount' is missing"
            );
        }

        return new PaymentRequest(reference, amount);
    }
}
~~~

Ví dụ tập trung vào message an toàn: lỗi chỉ nêu field và kiểu mong đợi. Trong deserializer production, cần bổ sung chính sách rõ ràng cho unknown property, null, duplicate property và EOF; ví dụ rút gọn này bỏ qua unknown field để tập trung vào cách tạo lỗi.

## 5. Không dùng getPathReference() một cách mù quáng

getPathReference() thuận tiện để đọc trong log, nhưng path có thể chứa tên property đến từ dữ liệu đầu vào, đặc biệt với map key hoặc cấu trúc JSON động.

Ví dụ:

~~~json
{
  "attributes": {
    "private-customer-identifier-987654": {
      "value": "..."
    }
  }
}
~~~

Nếu path được tạo từ key động, ghi nguyên chuỗi path có thể làm lộ dữ liệu hoặc identifier không cần thiết.

Một cách an toàn hơn là duyệt getPath() rồi chỉ ghi những field name nằm trong allowlist. Với key không nằm trong allowlist, thay bằng nhãn chung như <field>. Index của array có thể giữ lại nếu hệ thống cần biết phần tử nào gây lỗi.
## 6. Lọc mapping path bằng allowlist

Nếu ứng dụng chỉ có một schema đã biết, hãy cho phép log tên những field không nhạy cảm. Những tên khác được thay bằng nhãn chung. Cách này đặc biệt hữu ích khi path có thể chứa map key do client gửi.

~~~java
import com.fasterxml.jackson.databind.JsonMappingException;

import java.util.Set;

public final class SafeJsonPath {

    private static final Set<String> SAFE_FIELDS = Set.of(
            "order",
            "items",
            "sku",
            "quantity",
            "amount",
            "currency",
            "customer"
    );

    private SafeJsonPath() {
    }

    public static String from(JsonMappingException exception) {
        StringBuilder path = new StringBuilder("$");

        for (JsonMappingException.Reference reference
                : exception.getPath()) {

            if (reference.getIndex() >= 0) {
                path.append('[')
                        .append(reference.getIndex())
                        .append(']');
                continue;
            }

            String fieldName = reference.getFieldName();

            if (fieldName != null) {
                String safeName = SAFE_FIELDS.contains(fieldName)
                        ? fieldName
                        : "<field>";

                path.append('.').append(safeName);
            }
        }

        return path.toString();
    }
}
~~~

Ví dụ:
- Path nội bộ: $.order.items[2].quantity.
- Path đã lọc: $.order.items[2].quantity.
- Nếu một map key chứa customer identifier không nằm trong allowlist, path đã lọc chỉ hiển thị $.<field>.

Không đưa reference.getFrom() vào log vì đó có thể là object chứa dữ liệu nghiệp vụ. Không dùng reference.toString() nếu chưa kiểm soát cách nó định dạng field hoặc object.

### 6.1. Có nên giữ array index?

Index thường không phải dữ liệu nhạy cảm và rất hữu ích để tìm phần tử lỗi. Tuy nhiên, nó vẫn có thể tiết lộ số lượng phần tử hoặc vị trí của một bản ghi. Nếu thông tin đó nhạy cảm trong hệ thống, thay index bằng nhãn chung như [item].

Có thể giới hạn index được ghi để log không chứa giá trị bất thường:

~~~java
private static void appendIndex(StringBuilder path, int index) {
    if (index >= 0 && index <= 100_000) {
        path.append('[').append(index).append(']');
    } else {
        path.append("[item]");
    }
}
~~~

Chọn chính sách theo schema và threat model. Mục tiêu là giữ đủ ngữ cảnh mà không để key động hoặc identifier đi vào log.

## 7. Ghi log exception mà không ghi payload

Một handler có thể ghi:
- Correlation/request ID.
- Mã lỗi do ứng dụng định nghĩa.
- Path đã lọc.
- Loại exception.
- Line, column và offset số nếu có.

Ví dụ:

~~~java
public void logMappingFailure(
        String requestId,
        JsonMappingException exception
) {
    JsonLocation location = exception.getLocation();

    Integer line = location == null || location.getLineNr() < 1
            ? null
            : location.getLineNr();

    Integer column = location == null || location.getColumnNr() < 1
            ? null
            : location.getColumnNr();

    logger.warn(
            "JSON_MAPPING_FAILED requestId={} path={} line={} column={} exceptionType={}",
            requestId,
            SafeJsonPath.from(exception),
            line,
            column,
            exception.getClass().getSimpleName()
    );
}
~~~

Điểm quan trọng là không truyền chính exception làm tham số cuối cho logger trong log thường ngày. Nhiều logging framework sẽ in stack trace cùng message của exception. Message có thể chứa giá trị đầu vào hoặc source detail.

Nếu cần stack trace để điều tra lỗi lập trình, hãy cân nhắc một log channel hạn chế quyền và bảo đảm exception message/cause không chứa dữ liệu nhạy cảm. Đối với lỗi dữ liệu client gửi sai, một event có mã lỗi, path đã lọc và location thường đủ để phân tích.

### 7.1. Xử lý parse error

Lỗi cú pháp có thể không có mapping path. Khi đó chỉ ghi loại lỗi và vị trí số:

~~~java
public void logParseFailure(
        String requestId,
        JsonParseException exception
) {
    JsonLocation location = exception.getLocation();

    logger.warn(
            "JSON_PARSE_FAILED requestId={} line={} column={} byteOffset={} exceptionType={}",
            requestId,
            safeLine(location),
            safeColumn(location),
            safeByteOffset(location),
            exception.getClass().getSimpleName()
    );
}
~~~

Các helper chỉ trả về số hoặc null:

~~~java
private static Integer safeLine(JsonLocation location) {
    return location == null || location.getLineNr() < 1
            ? null
            : location.getLineNr();
}

private static Integer safeColumn(JsonLocation location) {
    return location == null || location.getColumnNr() < 1
            ? null
            : location.getColumnNr();
}

private static Long safeByteOffset(JsonLocation location) {
    return location == null || location.getByteOffset() < 0
            ? null
            : location.getByteOffset();
}
~~~

Không log location.toString() hoặc location.getSourceRef(). Chỉ lấy các trường số cần thiết.

## 8. Tắt việc đưa source vào JsonLocation

Tùy phiên bản Jackson Core, location có thể giữ tham chiếu đến nguồn đầu vào. Khi source là một buffer hoặc một chuỗi JSON, thông tin này có thể làm exception hiển thị một phần nội dung đầu vào.

Có thể tắt tính năng include source trong location khi tạo JsonFactory:

~~~java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.StreamReadFeature;
import com.fasterxml.jackson.databind.ObjectMapper;

JsonFactory factory = JsonFactory.builder()
        .disable(StreamReadFeature.INCLUDE_SOURCE_IN_LOCATION)
        .build();

ObjectMapper mapper = new ObjectMapper(factory);
~~~

Tên API và khả năng cấu hình phụ thuộc phiên bản jackson-core. Ở các phiên bản cũ hơn, có thể gặp cấu hình tương ứng trên JsonFactory.Feature.INCLUDE_SOURCE_IN_LOCATION. Hãy kiểm tra phiên bản dependency thực tế của dự án trước khi chọn cú pháp.

Tắt source inclusion giúp giảm nguy cơ source reference bị đưa vào thông tin location hoặc exception. Nó không thay thế việc kiểm soát log: custom deserializer vẫn có thể tự đưa raw value vào message, và middleware HTTP vẫn có thể ghi request body.

### 8.1. Không ghi source reference

Ngay cả khi source inclusion đã tắt, hãy giữ nguyên nguyên tắc không truy cập source reference trong code log:

~~~java
JsonLocation location = exception.getLocation();

if (location != null) {
    int line = location.getLineNr();
    int column = location.getColumnNr();

    // Ghi line và column nếu có.
    // Không ghi location.getSourceRef().
}
~~~

Tránh các cách sau trong log production:

~~~java
logger.warn("Location: {}", exception.getLocation());
logger.warn("Source: {}", exception.getLocation().getSourceRef());
logger.warn("Mapping failed: {}", exception);
~~~

Các biểu thức này có thể gọi toString() trên object chứa source detail hoặc exception message.

## 9. Chuẩn hóa lỗi trả về client

Log nội bộ và response API phục vụ hai mục đích khác nhau.

Log nội bộ có thể chứa:
- Request ID.
- Error code.
- Safe field path.
- Line/column.
- Exception class.
- Thông tin tracing không nhạy cảm.

Response cho client chỉ nên chứa thông tin cần thiết để sửa request:
- Mã lỗi ổn định.
- Field path đã được lọc.
- Message tĩnh, dễ hiểu.
- Correlation ID để liên hệ support.

Ví dụ response:

~~~json
{
  "code": "INVALID_FIELD_TYPE",
  "field": "$.amount",
  "message": "Field must be a number",
  "requestId": "req-7f31"
}
~~~

Không trả:
- Stack trace.
- Class name hoặc package nội bộ.
- Raw JSON request.
- Giá trị sai mà client vừa gửi.
- Source reference hoặc buffer nội bộ.
- SQL, token, file path hoặc chi tiết hạ tầng không cần thiết.

### 9.1. DTO lỗi có cấu trúc

~~~java
public record ApiFieldError(
        String code,
        String field,
        String message,
        String requestId
) {
}
~~~

Trong exception handler:

~~~java
@ExceptionHandler(JsonMappingException.class)
public ResponseEntity<ApiFieldError> handleMapping(
        JsonMappingException exception,
        HttpServletRequest request
) {
    String requestId = request.getHeader("X-Request-Id");

    String safePath = SafeJsonPath.from(exception);

    ApiFieldError body = new ApiFieldError(
            "INVALID_FIELD",
            safePath,
            "A field has an invalid value or type",
            requestId
    );

    return ResponseEntity.badRequest().body(body);
}
~~~

Ví dụ này dùng message chung để không phải chuyển nguyên văn exception message ra ngoài. Trong ứng dụng thật, nên dùng mã lỗi cụ thể theo loại lỗi đã xác định trong deserializer hoặc exception mapper.

Không nên lấy request ID từ header không tin cậy rồi dùng trực tiếp nếu hệ thống yêu cầu định dạng ID cụ thể. Có thể tạo correlation ID ở gateway/server và dùng giá trị đã được xác thực, chuẩn hóa.

## 10. Phân loại lỗi bằng mã ổn định

Thay vì dựa vào message của Jackson, ứng dụng có thể ánh xạ exception sang mã lỗi do mình định nghĩa.

| Nguyên nhân | Mã lỗi API gợi ý | Message công khai |
|---|---|---|
| Token sai kiểu | INVALID_FIELD_TYPE | Field has an invalid type |
| Property bắt buộc thiếu | REQUIRED_FIELD_MISSING | Required field is missing |
| Null không được phép | NULL_NOT_ALLOWED | Field must not be null |
| Giá trị ngoài range | VALUE_OUT_OF_RANGE | Field is outside the allowed range |
| JSON sai cú pháp | MALFORMED_JSON | Request body is not valid JSON |
| Type discriminator không biết | UNKNOWN_TYPE | Field contains an unsupported type |
| Lỗi mapping không phân loại được | INVALID_REQUEST | Request body cannot be mapped |

Mã lỗi ổn định giúp client và monitoring không phụ thuộc vào message có thể thay đổi giữa các phiên bản Jackson.

Không nên phân loại mọi JsonMappingException thành một mã duy nhất nếu ứng dụng có thể nhận diện nguyên nhân cụ thể. Ngược lại, cũng không nên cố phân tích chuỗi message của Jackson bằng regex để tạo mã lỗi vì format message không phải contract ổn định.
## 11. InvalidFormatException và các lỗi có giá trị bị từ chối

Một số lỗi mapping được biểu diễn bằng subclass cụ thể. Chẳng hạn InvalidFormatException có thể cung cấp:
- Kiểu Java đích.
- Giá trị gây lỗi qua getValue().
- Thông tin location và path kế thừa từ JsonMappingException.

Đây là thông tin rất hữu ích trong debugger hoặc test. Tuy nhiên, getValue() có thể là mật khẩu, token, số tài khoản hoặc nội dung riêng tư.

Có thể phân loại exception mà không đọc giá trị:

~~~java
catch (InvalidFormatException exception) {
    logger.warn(
            "JSON_INVALID_FORMAT requestId={} path={} targetType={}",
            requestId,
            SafeJsonPath.from(exception),
            exception.getTargetType() == null
                    ? "unknown"
                    : exception.getTargetType().getSimpleName()
    );

    throw new InvalidRequestException(
            "INVALID_FIELD_FORMAT",
            "A field has an unsupported format"
    );
}
~~~

Ví dụ trên không ghi getValue(), exception message hay toàn bộ exception. Nếu ứng dụng cần biết kiểu token thực tế, có thể lưu loại token do parser cung cấp tại thời điểm phát hiện lỗi, nhưng không lưu text value.

Không nên ghi giá trị bị từ chối chỉ vì exception có API cho phép truy cập nó. Quyền truy cập trong code không đồng nghĩa với việc dữ liệu đó phù hợp để ghi log.

## 12. Validation sau khi deserialize cũng cần lọc dữ liệu

Sau khi Jackson tạo object, ứng dụng có thể dùng Jakarta Bean Validation. ConstraintViolation có:
- Property path.
- Message.
- Message template.
- Root bean.
- Invalid value.

Không nên log toàn bộ ConstraintViolation hoặc gọi getInvalidValue() trong log thông thường. Invalid value có thể chứa dữ liệu nhạy cảm.

Ví dụ chỉ lấy path và template đã được ứng dụng kiểm soát:

~~~java
for (ConstraintViolation<?> violation : violations) {
    logger.warn(
            "VALIDATION_FAILED requestId={} field={} constraint={}",
            requestId,
            safeValidationPath(violation.getPropertyPath()),
            violation.getMessageTemplate()
    );
}
~~~

Hàm safeValidationPath() nên áp dụng allowlist tương tự mapping path. Message template thường ổn định hơn message đã interpolate, nhưng custom constraint có thể tự nhúng giá trị vào template/message. Hãy dùng template do ứng dụng định nghĩa và không chứa rejected value.

Response cho client có thể dùng message chung:

~~~json
{
  "code": "VALIDATION_FAILED",
  "field": "$.quantity",
  "message": "Field must be greater than zero",
  "requestId": "req-7f31"
}
~~~

Không trả object ConstraintViolation trực tiếp qua API vì nó có thể chứa root bean, invalid value và metadata nội bộ.

## 13. Không để tầng HTTP ghi request body ngoài ý muốn

Ngay cả khi exception handler không ghi payload, request body vẫn có thể bị ghi ở tầng khác:
- HTTP access log mở rộng.
- Reverse proxy hoặc API gateway.
- Servlet filter tự cache body.
- Request/response logging middleware.
- Distributed tracing instrumentation.
- APM agent hoặc công cụ quan sát hệ thống.

Hãy kiểm tra các thành phần này khi thiết kế logging cho API có dữ liệu nhạy cảm. Nếu cần log request, chỉ ghi metadata như method, route template, status, duration, content length và request ID. Không bật body logging toàn cục cho endpoint nhận thông tin xác thực hoặc thanh toán.

Nếu cần debug một request cụ thể, dùng cơ chế opt-in có kiểm soát:
- Quyền truy cập hạn chế.
- Thời gian bật ngắn.
- Dữ liệu đã mask hoặc synthetic.
- Không ghi secret hoặc token.
- Có giới hạn kích thước và thời gian lưu trữ.

Không nên thêm một filter sao chép toàn bộ InputStream chỉ để tạo thông báo lỗi chi tiết. Điều đó làm tăng bộ nhớ, độ trễ và số bản sao của dữ liệu nhạy cảm.

## 14. Masking và redaction khi thật sự cần một phần giá trị

Có trường hợp người vận hành cần một dấu hiệu về định dạng dữ liệu, ví dụ biết mã tài khoản có đúng độ dài hay không. Khi đó chỉ nên tạo một representation đã mask, theo quy tắc riêng cho từng loại dữ liệu.

Ví dụ, với một mã tham chiếu không bí mật:

~~~java
static String safeReference(String value) {
    if (value == null || value.length() < 4) {
        return "<redacted>";
    }

    return "..." + value.substring(value.length() - 4);
}
~~~

Không dùng một hàm mask chung cho mọi dữ liệu. Với số thẻ, token, mật khẩu và số định danh, chính sách có thể yêu cầu không ghi bất kỳ phần nào. Với một ID nghiệp vụ công khai, có thể cho phép log toàn bộ.

Một số nguyên tắc:
- Mặc định loại bỏ giá trị.
- Chỉ mask khi có nhu cầu vận hành cụ thể.
- Không mask bằng cách chỉ xóa vài ký tự nếu phần còn lại vẫn đủ để nhận diện người dùng.
- Không ghi raw value vào exception trước rồi mới mask khi log; dữ liệu có thể đã xuất hiện trong stack trace hoặc error tracking.
- Kiểm thử redaction với dữ liệu thật giả lập và các dạng input bất thường.

## 15. Kiểm thử để bảo đảm lỗi không làm lộ payload

Test nên kiểm tra cả hành vi từ chối dữ liệu và nội dung response/log.

### 15.1. Response không chứa giá trị nhạy cảm

~~~java
@Test
void errorResponseDoesNotEchoRejectedValue() throws Exception {
    String secret = "customer-secret-123";
    String json = """
            {
              "reference": "PAY-001",
              "amount": "%s"
            }
            """.formatted(secret);

    MvcResult result = mockMvc.perform(
            post("/payments")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(json)
    ).andExpect(status().isBadRequest())
     .andReturn();

    String responseBody = result.getResponse().getContentAsString();

    assertFalse(responseBody.contains(secret));
    assertFalse(responseBody.contains(json));
    assertTrue(responseBody.contains("INVALID_FIELD"));
}
~~~

Ví dụ dùng Spring MockMvc và Java text block. Nếu project không dùng Spring, có thể test trực tiếp exception mapper hoặc hàm tạo ApiFieldError.

### 15.2. Log không chứa raw value

Có thể dùng test appender của logging framework để thu log phát ra trong test:

~~~java
@Test
void mappingFailureLogDoesNotContainRejectedValue() {
    String secret = "private-value-9981";

    JsonMappingException exception = createInvalidInputException(secret);

    logMappingFailure("req-test", exception);

    String emittedLogs = testAppender.getLoggedText();

    assertFalse(emittedLogs.contains(secret));
    assertFalse(emittedLogs.contains("cardNumber"));
    assertTrue(emittedLogs.contains("JSON_MAPPING_FAILED"));
}
~~~

Test appender là helper phụ thuộc logging framework của project. Điều cần kiểm tra là log thực tế, không chỉ kiểm tra một hàm sanitize riêng lẻ.

### 15.3. Path động được thay thế

~~~java
@Test
void redactsDynamicMapKeysFromPath() {
    JsonMappingException exception =
            createMappingExceptionForDynamicKey(
                    "private-customer-identifier-987654"
            );

    String path = SafeJsonPath.from(exception);

    assertFalse(path.contains("987654"));
    assertTrue(path.contains("<field>"));
}
~~~

Test này giúp ngăn việc thay đổi schema hoặc thêm map key động vô tình đưa identifier vào log.

## 16. Những lỗi triển khai thường gặp

| Cách làm | Rủi ro | Cách xử lý |
|---|---|---|
| Log toàn bộ request body khi parse thất bại | Lộ mọi field, kể cả field không liên quan | Ghi request ID, mã lỗi, path đã lọc và location |
| Log exception object trực tiếp | Stack trace/message có thể chứa dữ liệu đầu vào | Ghi exception class và metadata đã kiểm soát |
| Log InvalidFormatException.getValue() | Ghi raw value bị từ chối | Chỉ ghi target type và safe path |
| Gọi JsonLocation.toString() | Có thể hiển thị source reference | Chỉ lấy line/column/offset |
| Gọi getSourceRef() | Có thể truy cập buffer/source | Không ghi source reference |
| Dùng getPathReference() cho map key tùy ý | Path có thể chứa identifier hoặc key nhạy cảm | Duyệt path và dùng allowlist |
| Trả exception message nguyên văn cho client | Lộ class, source hoặc giá trị | Dùng error code và message tĩnh |
| Log ConstraintViolation trực tiếp | Có thể chứa invalid value/root bean | Ghi safe path và constraint code |
| Chỉ mask ở log sink | Raw value đã có thể nằm trong exception/tracing | Không đưa raw value vào message ngay từ đầu |
| Bật body logging toàn cục | Nhiều endpoint cùng lộ dữ liệu | Tắt body logging; cấu hình theo route và chính sách |
| Dùng regex trên exception message | Message không phải contract ổn định | Phân loại bằng exception type hoặc mã lỗi do ứng dụng tạo |

## 17. Quy trình báo lỗi an toàn theo trường

Khi thiết kế một endpoint dùng Jackson, có thể áp dụng trình tự:

1. Xác định field nào nhạy cảm và field nào được phép xuất hiện trong log.
2. Tạo mã lỗi ổn định cho các loại lỗi đầu vào.
3. Trong custom deserializer, tạo message chỉ nêu field và điều kiện mong đợi.
4. Không nối raw value, JSON tree hoặc request body vào exception message.
5. Khi bắt JsonMappingException, lấy path và lọc bằng allowlist.
6. Khi lấy JsonLocation, chỉ lấy line, column và offset số.
7. Không ghi source reference, getValue(), exception message hoặc exception object nếu chưa kiểm soát nội dung.
8. Ánh xạ lỗi thành response DTO có mã lỗi và message tĩnh.
9. Kiểm tra HTTP middleware, proxy, tracing và APM để chắc chắn không có body logging ngoài ý muốn.
10. Viết test xác nhận response, log và path đều không chứa dữ liệu nhạy cảm.

Một event lỗi điển hình có thể trông như sau:

~~~json
{
  "event": "JSON_MAPPING_FAILED",
  "requestId": "req-7f31",
  "code": "INVALID_FIELD_TYPE",
  "field": "$.order.items[2].quantity",
  "line": 18,
  "column": 21,
  "exceptionType": "MismatchedInputException"
}
~~~

Đây là metadata được tạo có chủ đích. Nó không cần chứa request body, giá trị bị từ chối hay source reference.

## 18. Những điểm cần nhớ

- Báo lỗi theo field bằng mapping path, error code và location; không cần sao chép toàn bộ JSON.
- JsonMappingException.getPath() cho phép xây dựng đường dẫn có chọn lọc.
- getPathReference() tiện đọc nhưng cần thận trọng với map key và tên property động.
- JsonLocation có line, column và offset; tránh ghi source reference hoặc gọi toString() một cách mù quáng.
- InvalidFormatException.getValue() có thể chứa raw input và không nên log mặc định.
- Không log exception object hoặc message nếu chưa biết chắc chúng không chứa dữ liệu đầu vào.
- Dùng message tĩnh trong custom deserializer và không nối parser.getText() vào lỗi.
- Dùng allowlist để lọc field path, thay key động bằng nhãn chung.
- Tắt INCLUDE_SOURCE_IN_LOCATION nếu phiên bản Jackson hỗ trợ và ứng dụng không cần source reference.
- Response API nên dùng mã lỗi ổn định, field đã lọc và message công khai; không trả stack trace.
- Kiểm tra cả HTTP middleware, proxy, tracing và APM.
- Kiểm thử log và response để chứng minh rejected value không bị echo.

Báo lỗi theo trường giúp người gửi biết cần sửa property nào, còn người vận hành có thể tìm request và vị trí lỗi mà không cần lưu lại toàn bộ dữ liệu nhạy cảm. Hãy giữ thông tin chẩn đoán ở dạng metadata có kiểm soát: mã lỗi, path đã lọc, location số và request ID. Cách làm này vừa hỗ trợ điều tra vừa hạn chế việc nhân bản dữ liệu riêng tư trong log và hệ thống quan sát.
