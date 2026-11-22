# Kiểm thử chính sách chuyển kiểu như một phần hợp đồng dữ liệu

JSON là định dạng có một số kiểu dữ liệu cơ bản: object, array, string, number, boolean và null. Java lại có nhiều kiểu đích hơn, chẳng hạn int, long, BigDecimal, enum, LocalDate, List<User> hoặc các value object do ứng dụng định nghĩa. Khi Jackson đọc JSON, đôi khi nó có thể chuyển một dạng input sang kiểu Java khác. Hành vi đó gọi là coercion (chuyển kiểu).

Ví dụ, một API khai báo thuộc tính quantity là int nhưng client gửi chuỗi "5". Jackson có thể chấp nhận và chuyển chuỗi thành số nguyên theo cấu hình tương thích. Nếu client gửi 5.8, Jackson có thể chuyển thành số nguyên theo quy tắc xử lý float-to-integer. Với một số target khác, chuỗi rỗng có thể được xem như null hoặc empty value.

Những chuyển đổi này ảnh hưởng trực tiếp đến hợp đồng API. Nếu hôm nay hệ thống chấp nhận "5" nhưng sau khi thay cấu hình lại từ chối, client có thể bị lỗi dù payload không thay đổi. Ngược lại, nếu ứng dụng âm thầm chuyển một giá trị sai thành 0 hoặc null, lỗi dữ liệu có thể đi sâu vào nghiệp vụ.

Vì vậy, **chính sách coercion cần được thiết kế và kiểm thử như một phần của hợp đồng dữ liệu**, cùng với tên field, kiểu dữ liệu, giá trị bắt buộc và quy tắc null.

## 1. Coercion là gì?

Coercion là quá trình Jackson chuyển một dạng JSON input sang kiểu Java đích theo quy tắc được phép.

Ví dụ DTO:

~~~java
public record CreateOrderRequest(
    int quantity,
    BigDecimal unitPrice,
    boolean confirmed
) {}
~~~

JSON có thể gửi các dạng:

~~~json
{
  "quantity": "5",
  "unitPrice": 120.50,
  "confirmed": "true"
}
~~~

Ở đây:

- quantity là JSON string nhưng target là int.
- unitPrice là JSON number và target là BigDecimal.
- confirmed là JSON string nhưng target là boolean.

Jackson có thể hỗ trợ một số chuyển đổi scalar theo cấu hình. Tuy nhiên, không nên giả định mọi dạng input đều được chấp nhận hoặc mọi phiên bản Jackson đều có cùng hành vi nếu ứng dụng chưa khóa chính sách.

### 1.1. Các dạng input cần quan tâm

Jackson phân biệt nhiều input shape:

| Input shape | Ví dụ JSON | Ý nghĩa |
|---|---|---|
| Integer | 12 | Số nguyên |
| Float | 12.5 | Số có phần thập phân hoặc dạng exponent |
| Boolean | true | Giá trị boolean |
| String | "12" | Chuỗi có nội dung |
| EmptyString | "" | Chuỗi rỗng |
| Array | [1, 2] | JSON array |
| EmptyArray | [] | Array rỗng |
| Object | {"value": 1} | JSON object |
| EmptyObject | {} | Object rỗng |
| Null | null | Giá trị null |

Không phải mọi input shape đều được chuyển sang mọi kiểu đích. Ví dụ object thường không thể chuyển trực tiếp thành int; array không thể tự động trở thành một object nghiệp vụ nếu không có quy tắc cụ thể.

Ngoài các dạng trên, Jackson còn có những quy tắc riêng cho kiểu ngày giờ, enum, collection, map và kiểu do ứng dụng định nghĩa.

### 1.2. Vì sao coercion có thể nguy hiểm?

Giả sử API nhận:

~~~json
{
  "quantity": 3.9
}
~~~

Nếu Jackson chuyển 3.9 thành 3, request vẫn deserialize thành công. Nhưng hệ thống đã thay đổi ý nghĩa dữ liệu mà client gửi.

Một số rủi ro thường gặp:

- Giá trị thập phân bị chuyển thành số nguyên, làm mất phần lẻ.
- Chuỗi không đúng định dạng được chuyển thành null hoặc giá trị mặc định.
- Field rỗng bị coi là không có dữ liệu.
- Một scalar được chấp nhận thành collection một phần tử.
- Field enum lạ bị chuyển thành null hoặc giá trị mặc định.
- Client gửi sai kiểu nhưng API không trả lỗi, khiến lỗi xuất hiện ở tầng nghiệp vụ sau đó.

Với dữ liệu có ý nghĩa về tiền, số lượng, trạng thái, quyền hoặc thời gian, coercion phải được quyết định rõ ràng.

## 2. Phân biệt parse, coercion và validation

Ba bước này giải quyết ba câu hỏi khác nhau:

| Bước | Câu hỏi | Ví dụ |
|---|---|---|
| Parse | Chuỗi byte/ký tự có phải JSON hợp lệ không? | Thiếu dấu ngoặc hoặc dấu phẩy |
| Coercion/binding | Giá trị JSON có chuyển được sang kiểu Java đích không? | String "5" vào int |
| Validation | Giá trị đã chuyển đổi có hợp lệ theo hợp đồng/nghiệp vụ không? | quantity phải lớn hơn 0 |

Ví dụ JSON:

~~~json
{
  "quantity": -2
}
~~~

JSON hợp lệ và Jackson có thể binding thành int thành công. Nhưng quantity âm có thể không hợp lệ theo nghiệp vụ. Bean Validation hoặc service/domain phải kiểm tra điều đó.

Ngược lại, JSON:

~~~json
{
  "quantity": "five"
}
~~~

có thể không binding được sang int nếu coercion không chuyển đổi được. Đây là lỗi binding, xảy ra trước validation nghiệp vụ.

Không dùng coercion để thay thế validation. Một giá trị có thể chuyển đổi được nhưng vẫn sai hợp đồng.

## 3. Chính sách coercion trong Jackson 2.12+

Jackson 2.12 bổ sung API CoercionConfig để cấu hình cách xử lý từng input shape theo nhóm kiểu dữ liệu hoặc kiểu Java cụ thể.

Các thành phần chính:

- LogicalType: nhóm kiểu đích như Integer, Float, Boolean, Textual, Enum, Collection, Map, POJO.
- CoercionInputShape: dạng input JSON như String, Integer, Float, EmptyString, Array hoặc Object.
- CoercionAction: hành động Jackson thực hiện khi gặp dạng input đó.

Bốn hành động phổ biến:

| CoercionAction | Hành vi |
|---|---|
| Fail | Từ chối chuyển đổi và ném lỗi mapping |
| TryConvert | Thử chuyển đổi theo logic deserializer |
| AsNull | Xem input như null |
| AsEmpty | Dùng empty value do deserializer của kiểu đích cung cấp |

AsEmpty không nhất thiết giống giá trị default nghiệp vụ. Empty value phụ thuộc kiểu đích và deserializer. Với một số kiểu, empty có thể là chuỗi rỗng, collection rỗng hoặc giá trị mặc định được deserializer định nghĩa. Nếu cần default cụ thể như pageSize = 20, hãy đặt default trong DTO, constructor hoặc builder.

### 3.1. Cấu hình theo LogicalType

Ví dụ muốn từ chối chuỗi khi target là kiểu số nguyên:

~~~java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.databind.type.LogicalType;
import com.fasterxml.jackson.databind.cfg.CoercionAction;
import com.fasterxml.jackson.databind.cfg.CoercionInputShape;

ObjectMapper mapper = JsonMapper.builder().build();

mapper.coercionConfigFor(LogicalType.Integer)
    .setCoercion(
        CoercionInputShape.String,
        CoercionAction.Fail
    );
~~~

Sau cấu hình này, các kiểu số nguyên thuộc nhóm LogicalType.Integer sẽ không chấp nhận JSON string chỉ nhờ coercion thông thường.

Có thể áp dụng cho các dạng input khác:

~~~java
mapper.coercionConfigFor(LogicalType.Integer)
    .setCoercion(
        CoercionInputShape.Float,
        CoercionAction.Fail
    )
    .setCoercion(
        CoercionInputShape.EmptyString,
        CoercionAction.Fail
    );
~~~

Ví dụ này thể hiện chính sách strict:

- Số nguyên JSON được chấp nhận.
- Số thập phân không được tự chuyển thành số nguyên.
- Chuỗi rỗng không được chuyển thành số nguyên.

Nếu ứng dụng cần chấp nhận chuỗi số nhưng từ chối số thập phân, chỉ cấu hình String là TryConvert hoặc giữ hành vi tương thích phù hợp, đồng thời cấu hình Float là Fail. Chính sách phải được kiểm thử với payload thật.

### 3.2. Cấu hình theo kiểu Java cụ thể

Ngoài LogicalType, có thể cấu hình coercion cho một kiểu Java cụ thể:

~~~java
mapper.coercionConfigFor(Integer.class)
    .setCoercion(
        CoercionInputShape.String,
        CoercionAction.Fail
    );
~~~

Cách này phù hợp khi chỉ một target type cần quy tắc riêng. Cấu hình theo class cụ thể giúp phạm vi hẹp hơn cấu hình theo LogicalType.

Khi tra cứu coercion, cấu hình cho kiểu cụ thể có thể được ưu tiên so với cấu hình logical type chung. Nếu cùng một kiểu bị tác động bởi nhiều cấp cấu hình, hãy kiểm thử trên đúng phiên bản Jackson mà ứng dụng sử dụng.

### 3.3. Cấu hình theo nhóm kiểu dữ liệu

Ví dụ từ chối chuỗi khi target là boolean:

~~~java
mapper.coercionConfigFor(LogicalType.Boolean)
    .setCoercion(
        CoercionInputShape.String,
        CoercionAction.Fail
    );
~~~

Nếu API khai báo confirmed là boolean, client phải gửi:

~~~json
{
  "confirmed": true
}
~~~

Thay vì:

~~~json
{
  "confirmed": "true"
}
~~~

Điều này làm hợp đồng JSON rõ ràng hơn và giúp phát hiện client gửi sai kiểu ngay ở tầng binding.

## 4. Kiểm soát String-to-Number

Đây là một trong những dạng coercion phổ biến nhất.

Giả sử DTO:

~~~java
public record ProductRequest(
    int quantity,
    BigDecimal price
) {}
~~~

Một số payload:

| JSON input | Ý nghĩa | Chính sách strict thường phù hợp |
|---|---|---|
| {"quantity": 5} | Integer JSON | Chấp nhận |
| {"quantity": "5"} | String chứa số | Từ chối nếu hợp đồng yêu cầu number |
| {"quantity": 5.0} | Float JSON | Từ chối nếu quantity phải là integer |
| {"quantity": ""} | Empty string | Từ chối |
| {"quantity": "abc"} | String không phải số | Từ chối |

Cấu hình:

~~~java
ObjectMapper strictMapper = JsonMapper.builder().build();

strictMapper.coercionConfigFor(LogicalType.Integer)
    .setCoercion(CoercionInputShape.String, CoercionAction.Fail)
    .setCoercion(CoercionInputShape.EmptyString, CoercionAction.Fail)
    .setCoercion(CoercionInputShape.Float, CoercionAction.Fail);

strictMapper.coercionConfigFor(LogicalType.Float)
    .setCoercion(CoercionInputShape.String, CoercionAction.Fail)
    .setCoercion(CoercionInputShape.EmptyString, CoercionAction.Fail);
~~~

LogicalType.Float bao gồm các target số có phần thập phân như float, double và các kiểu số tương ứng theo phân loại của Jackson. Hãy test riêng BigDecimal nếu ứng dụng phụ thuộc vào độ chính xác thập phân.

### 4.1. Không nhầm số nguyên và số thập phân

Feature DeserializationFeature.ACCEPT_FLOAT_AS_INT của Jackson điều khiển việc chấp nhận floating-point input cho target integral type. Feature này mặc định bật trong nhiều cấu hình Jackson 2.

Có thể tắt:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .disable(DeserializationFeature.ACCEPT_FLOAT_AS_INT)
    .build();
~~~

Cấu hình này giúp từ chối các giá trị float khi target là kiểu số nguyên. Nếu đang dùng CoercionConfig, nên chọn một nơi thể hiện chính sách rõ ràng và test cả hai cơ chế để tránh hiểu nhầm về thứ tự/ưu tiên cấu hình.

Không dùng int cho dữ liệu cần phần thập phân. Không dùng double để lưu tiền nếu cần độ chính xác thập phân; hãy dùng BigDecimal và quy định scale/rounding ở tầng nghiệp vụ.

### 4.2. String number có thể là hợp đồng hợp lệ

Không phải API nào cũng cần strict tuyệt đối. Một hệ thống cũ có thể đã quy định quantity là chuỗi vì dữ liệu đi qua form hoặc CSV trước khi đến backend.

Nếu hợp đồng cho phép, có thể chấp nhận string number, nhưng phải xác định:

- Có cho phép dấu cộng/trừ không?
- Có cho phép khoảng trắng ở đầu/cuối không?
- Có cho phép dấu thập phân hoặc exponent không?
- Có cho phép dấu phân cách hàng nghìn không?
- Overflow được xử lý thế nào?
- Chuỗi rỗng có bị từ chối không?

Đừng để một quy tắc parse tổng quát vô tình quyết định các chi tiết nghiệp vụ này.

## 5. Kiểm soát EmptyString và EmptyArray/EmptyObject

Empty value là nguồn lỗi phổ biến vì nhiều client form gửi chuỗi rỗng thay cho null hoặc bỏ field.

### 5.1. EmptyString vào kiểu số hoặc boolean

Ví dụ:

~~~json
{
  "quantity": "",
  "active": ""
}
~~~

Không nên mặc định Jackson luôn chuyển chuỗi rỗng thành 0, false hoặc null. Hành vi phụ thuộc target type, coercion config và các feature tương thích.

Nếu hợp đồng yêu cầu từ chối:

~~~java
mapper.coercionConfigFor(LogicalType.Integer)
    .setCoercion(
        CoercionInputShape.EmptyString,
        CoercionAction.Fail
    );

mapper.coercionConfigFor(LogicalType.Boolean)
    .setCoercion(
        CoercionInputShape.EmptyString,
        CoercionAction.Fail
    );
~~~

Chuỗi chỉ có khoảng trắng như "   " là một trường hợp cần quyết định riêng. CoercionConfig có hỗ trợ cấu hình cách xem blank string thông qua acceptBlankAsEmpty ở cấp coercion config. Chỉ bật khi hợp đồng muốn coi chuỗi toàn khoảng trắng giống empty string; nếu không, hãy từ chối hoặc chuẩn hóa ở tầng phù hợp.

### 5.2. EmptyString vào POJO

Một JSON string rỗng không phải JSON object rỗng. Với target là một POJO, Jackson có các feature tương thích như ACCEPT_EMPTY_STRING_AS_NULL_OBJECT và coercion config cho logical type POJO.

Không nên bật chế độ này rộng chỉ vì một payload cũ gửi chuỗi rỗng. Nếu một field cần chấp nhận empty string như null, hãy giới hạn chính sách theo kiểu hoặc property và viết test.

### 5.3. EmptyArray và EmptyObject

Empty array và empty object cũng có semantics riêng:

~~~json
{
  "items": [],
  "metadata": {}
}
~~~

Đây là hai container có mặt nhưng không chứa phần tử/property. Chúng khác với missing và null.

Jackson có feature ACCEPT_EMPTY_ARRAY_AS_NULL_OBJECT cho một số tình huống chuyển empty array thành null khi target là POJO. CoercionConfig cũng cho phép định nghĩa hành vi theo input shape và logical type.

Không nên bật chấp nhận empty array/object cho POJO nếu hợp đồng yêu cầu object có cấu trúc. Một object rỗng có thể deserialize thành instance với toàn bộ field mặc định, khiến payload thiếu dữ liệu nhưng vẫn được chấp nhận.

## 6. Scalar thành Collection và Collection thành Scalar

Ngoài chuyển kiểu giá trị, Jackson còn có thể chuyển đổi hình dạng JSON.

Ví dụ target là List<String> nhưng input là scalar:

~~~json
{
  "tags": "java"
}
~~~

Nếu bật DeserializationFeature.ACCEPT_SINGLE_VALUE_AS_ARRAY, Jackson có thể xem scalar như collection một phần tử:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .enable(DeserializationFeature.ACCEPT_SINGLE_VALUE_AS_ARRAY)
    .build();
~~~

Kết quả:

~~~java
List.of("java")
~~~

Điều này hữu ích khi tích hợp với API không nhất quán, lúc gửi một phần tử thì trả scalar, lúc gửi nhiều phần tử thì trả array. Tuy nhiên, nó làm hợp đồng kém rõ ràng vì cùng một field có hai hình dạng JSON.

Chiều ngược lại, UNWRAP_SINGLE_VALUE_ARRAYS cho phép một array chỉ có một phần tử được đọc thành scalar:

~~~json
{
  "quantity": [5]
}
~~~

Nếu bật feature này, target int có thể nhận 5 từ array một phần tử. Chỉ bật khi đối tác thực sự yêu cầu và có test cho array rỗng, array nhiều phần tử và scalar.

Trong API do mình kiểm soát, nên yêu cầu field collection luôn là JSON array, kể cả khi chỉ có một phần tử.

## 7. Kiểm soát kiểu Enum và giá trị không biết

Enum là một dạng coercion/compatibility riêng. Ví dụ:

~~~java
public enum OrderStatus {
    NEW,
    PROCESSING,
    COMPLETED
}
~~~

JSON:

~~~json
{
  "status": "PROCESSING"
}
~~~

Nếu client gửi "IN_PROGRESS" mà enum không có giá trị đó, Jackson thường báo lỗi. Đây có thể là hành vi tốt cho API strict vì giúp phát hiện producer và consumer không đồng bộ.

Jackson có các feature:

- READ_UNKNOWN_ENUM_VALUES_AS_NULL: chuyển enum value không biết thành null.
- READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE: dùng constant được đánh dấu @JsonEnumDefaultValue nếu có.
- @JsonEnumDefaultValue: đánh dấu enum constant làm fallback cho giá trị không biết.

Ví dụ:

~~~java
public enum OrderStatus {
    NEW,
    PROCESSING,
    COMPLETED,

    @JsonEnumDefaultValue
    UNKNOWN
}
~~~

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .enable(DeserializationFeature.READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE)
    .build();
~~~

Giá trị không biết sẽ thành UNKNOWN nếu enum có constant mặc định được đánh dấu.

Đây là quyết định hợp đồng quan trọng. Nếu trạng thái lạ có thể ảnh hưởng thanh toán hoặc chuyển trạng thái đơn hàng, âm thầm chuyển thành UNKNOWN có thể không đủ an toàn. Có thể cần từ chối request và ghi log để producer sửa. Nếu consumer cần forward event mà không hiểu mọi enum mới, fallback có kiểm soát có thể phù hợp hơn.

## 8. Date/time và các chuyển đổi định dạng

Date/time không nên được xem là một kiểu scalar chung. Jackson cần module hỗ trợ kiểu java.time và quy tắc định dạng rõ ràng.

Ví dụ DTO:

~~~java
public record BookingRequest(
    LocalDate date,
    Instant createdAt
) {}
~~~

Một hợp đồng JSON có thể yêu cầu:

~~~json
{
  "date": "2026-11-12",
  "createdAt": "2026-11-12T08:30:00Z"
}
~~~

Cần quyết định:

- Có chỉ chấp nhận ISO-8601 string hay chấp nhận numeric timestamp?
- Timestamp tính bằng giây hay millisecond?
- Có bắt buộc timezone/offset không?
- LocalDateTime được hiểu theo timezone nào?
- Có chấp nhận chuỗi chỉ có ngày cho kiểu Instant không?
- Precision đến giây, millisecond hay nanosecond?

JavaTimeModule và các feature liên quan như WRITE_DATES_AS_TIMESTAMPS ảnh hưởng biểu diễn. Cấu hình timezone và date format cũng có thể tác động kết quả.

Hãy test payload đúng và sai format. Không nên chấp nhận nhiều dạng ngày giờ ngoài ý muốn chỉ để một mapper dùng chung với mọi đối tác.

## 9. Kiểm thử coercion như contract test

Một contract test nên kiểm tra cả payload được chấp nhận và payload phải bị từ chối. Chỉ test happy path không thể chứng minh chính sách coercion đã được thực thi.

Ví dụ DTO:

~~~java
public record QuantityRequest(int quantity) {}
~~~

Tạo mapper strict:

~~~java
ObjectMapper strictMapper = JsonMapper.builder()
    .disable(DeserializationFeature.ACCEPT_FLOAT_AS_INT)
    .build();

strictMapper.coercionConfigFor(LogicalType.Integer)
    .setCoercion(CoercionInputShape.String, CoercionAction.Fail)
    .setCoercion(CoercionInputShape.EmptyString, CoercionAction.Fail)
    .setCoercion(CoercionInputShape.Float, CoercionAction.Fail);
~~~

Test input hợp lệ:

~~~java
@Test
void acceptsJsonIntegerForQuantity() throws Exception {
    QuantityRequest request = strictMapper.readValue(
        """
        {"quantity": 5}
        """,
        QuantityRequest.class
    );

    assertEquals(5, request.quantity());
}
~~~

Test từ chối string number:

~~~java
@Test
void rejectsStringForIntegerQuantity() {
    assertThrows(JsonMappingException.class, () ->
        strictMapper.readValue(
            """
            {"quantity": "5"}
            """,
            QuantityRequest.class
        )
    );
}
~~~

Test từ chối decimal:

~~~java
@Test
void rejectsDecimalForIntegerQuantity() {
    assertThrows(JsonMappingException.class, () ->
        strictMapper.readValue(
            """
            {"quantity": 5.8}
            """,
            QuantityRequest.class
        )
    );
}
~~~

Test từ chối chuỗi rỗng:

~~~java
@Test
void rejectsEmptyStringForIntegerQuantity() {
    assertThrows(JsonMappingException.class, () ->
        strictMapper.readValue(
            """
            {"quantity": ""}
            """,
            QuantityRequest.class
        )
    );
}
~~~

Các test này khóa hành vi của hợp đồng. Nếu sau này ai đó bật lại scalar coercion hoặc đổi mapper, test sẽ phát hiện thay đổi.

## 10. Dùng parameterized test để kiểm tra nhiều input shape

JUnit 5 hỗ trợ parameterized test, giúp kiểm tra nhiều payload có cùng kỳ vọng.

~~~java
@ParameterizedTest
@ValueSource(strings = {
    "{\"quantity\": \"5\"}",
    "{\"quantity\": 5.8}",
    "{\"quantity\": \"\"}",
    "{\"quantity\": true}"
})
void rejectsInvalidQuantityShapes(String json) {
    assertThrows(JsonMappingException.class, () ->
        strictMapper.readValue(json, QuantityRequest.class)
    );
}
~~~

Có thể mở rộng với @MethodSource nếu mỗi test case cần mô tả input, target type và expected result.

Một test matrix hữu ích:

| Target type | Input shape | Strict contract |
|---|---|---|
| int | Integer JSON | Chấp nhận |
| int | Float JSON | Từ chối |
| int | String số | Từ chối nếu không cho phép string number |
| int | EmptyString | Từ chối |
| int | Null | Từ chối nếu bật FAIL_ON_NULL_FOR_PRIMITIVES |
| BigDecimal | Float/Integer JSON | Chấp nhận theo độ chính xác và format đã chọn |
| BigDecimal | String số | Theo hợp đồng; không tự mặc định chấp nhận |
| boolean | Boolean JSON | Chấp nhận |
| boolean | String "true" | Theo coercion policy |
| List<T> | Array JSON | Chấp nhận |
| List<T> | Scalar JSON | Từ chối nếu không bật ACCEPT_SINGLE_VALUE_AS_ARRAY |
| Enum | Giá trị đã biết | Chấp nhận |
| Enum | Giá trị lạ | Từ chối hoặc fallback theo contract |

Không nên viết một test chỉ xác nhận deserialize không ném lỗi. Hãy assert giá trị cuối cùng, kiểu phần tử và hành vi với dữ liệu sai.

## 11. Contract fixture và bảo vệ tương thích

Ngoài unit test cho CoercionConfig, nên lưu JSON fixture đại diện cho hợp đồng đã phát hành.

Ví dụ cấu trúc:

~~~text
src/test/resources/contracts/
├── public-api/
│   ├── create-order-valid.json
│   ├── create-order-invalid-string-number.json
│   └── create-order-invalid-decimal.json
├── partner-api/
│   ├── order-valid-v1.json
│   └── order-valid-v2-with-extra-field.json
└── webhook/
    ├── event-known-type.json
    └── event-future-field.json
~~~

Test đọc fixture giúp người review thấy chính xác payload nào được chấp nhận và payload nào bị từ chối. Khi nâng Jackson, thêm module hoặc thay cấu hình, chạy lại bộ test để phát hiện thay đổi behavior.

Nếu hợp đồng có nhiều version, hãy tổ chức fixture theo version. Đừng ghi đè payload cũ chỉ vì producer đã phát hành format mới; consumer có thể vẫn cần đọc dữ liệu lịch sử.

## 12. Phân biệt coercion với validation và normalization

Coercion chỉ quyết định Jackson có thể chuyển dạng input sang kiểu Java hay không. Sau đó, dữ liệu vẫn cần validation.

Ví dụ:

~~~java
public record CreateProductRequest(
    @Min(1) int quantity,
    @DecimalMin("0.01") BigDecimal price
) {}
~~~

JSON:

~~~json
{
  "quantity": 0,
  "price": 0
}
~~~

Cả hai giá trị đều có thể binding thành công. Bean Validation mới kiểm tra quantity và price có đạt quy tắc không.

Normalization là bước khác nữa. Ví dụ, trim khoảng trắng của mã sản phẩm, chuyển email về dạng chuẩn hoặc chuẩn hóa currency code. Không nên dùng coercion để làm các thao tác này vì coercion thường xảy ra ở tầng binding và không thể hiện đầy đủ ý nghĩa nghiệp vụ.

Có thể tổ chức pipeline:

~~~text
JSON bytes
    |
    v
JSON parsing
    |
    v
Type coercion / databinding
    |
    v
Bean Validation
    |
    v
Business validation
    |
    v
Normalization / domain mapping
    |
    v
Business operation
~~~

Tùy kiến trúc, normalization có thể diễn ra trước hoặc trong domain mapping. Điều quan trọng là không nhầm các bước và không để Jackson tự quyết định quy tắc nghiệp vụ.

## 13. Tổ chức cấu hình strict và compatible

Một ứng dụng có thể cần hai chính sách:

- Strict: yêu cầu đúng kiểu JSON, từ chối chuyển đổi ngoài hợp đồng.
- Compatible: chấp nhận một số biến thể input đã được xác định để tích hợp hệ thống cũ.

Ví dụ cấu hình strict:

~~~java
ObjectMapper strictMapper = JsonMapper.builder()
    .disable(DeserializationFeature.ACCEPT_FLOAT_AS_INT)
    .enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES)
    .build();

strictMapper.coercionConfigFor(LogicalType.Integer)
    .setCoercion(CoercionInputShape.String, CoercionAction.Fail)
    .setCoercion(CoercionInputShape.EmptyString, CoercionAction.Fail);

strictMapper.coercionConfigFor(LogicalType.Boolean)
    .setCoercion(CoercionInputShape.String, CoercionAction.Fail)
    .setCoercion(CoercionInputShape.EmptyString, CoercionAction.Fail);
~~~

Mapper compatible có thể giữ hoặc cấu hình một số chuyển đổi được hợp đồng cũ cho phép. Không nên đơn giản hóa thành "strict là tốt, compatible là xấu". Một API cũ có client thực tế đang gửi string number có thể cần giữ tương thích trong thời gian chuyển đổi.

Nếu cần nới lỏng chính sách, hãy giới hạn theo endpoint/đối tác, ghi nhận metric hoặc log về payload dạng cũ, đặt thời hạn hỗ trợ và có kế hoạch loại bỏ. Không bật permissive mode cho toàn bộ ứng dụng chỉ để sửa một tích hợp.

## 14. Lưu ý khi nâng phiên bản Jackson

Coercion behavior và API cấu hình có thể thay đổi hoặc được tinh chỉnh giữa các phiên bản. Khi nâng Jackson:

1. Kiểm tra release notes và migration notes của dòng phiên bản.
2. Xác nhận BOM quản lý đồng bộ core, databind và module.
3. Chạy contract fixture cho mọi input shape quan trọng.
4. Kiểm tra các feature tương thích như ACCEPT_FLOAT_AS_INT, ACCEPT_SINGLE_VALUE_AS_ARRAY và unknown enum handling.
5. Kiểm tra CoercionConfig theo logical type và class cụ thể.
6. Xem xét thay đổi trong Spring Boot dependency management nếu nâng qua Boot.
7. Ghi lại các thay đổi contract có chủ ý.

Không nên dựa vào default của Jackson làm tài liệu hợp đồng. Default có thể khác giữa phiên bản hoặc bị thay đổi bởi framework. Nếu một dạng input phải được chấp nhận hoặc từ chối, hãy cấu hình và test tường minh.

## 15. Checklist thiết kế coercion contract

- [ ] Đã liệt kê kiểu JSON hợp lệ cho từng field.
- [ ] Đã quyết định có chấp nhận string number hay không.
- [ ] Đã quyết định float có được chuyển thành integer không.
- [ ] Đã quyết định empty string có được xem là null/empty không.
- [ ] Đã xác định scalar có được chấp nhận thành collection một phần tử không.
- [ ] Đã quy định enum value lạ sẽ bị từ chối hay fallback.
- [ ] Đã thống nhất date/time format và timezone.
- [ ] Đã phân biệt coercion với Bean Validation và normalization.
- [ ] Đã cấu hình theo LogicalType hoặc kiểu cụ thể trong phạm vi cần thiết.
- [ ] Đã viết test cho input được chấp nhận và input bị từ chối.
- [ ] Đã có fixture bảo vệ các hợp đồng đã phát hành.
- [ ] Đã chạy lại contract test khi nâng Jackson hoặc Spring Boot.

Chính sách chuyển kiểu là một phần của hợp đồng dữ liệu vì nó quyết định ứng dụng hiểu payload của client như thế nào. Hãy định nghĩa input shape được phép, cấu hình coercion trong phạm vi nhỏ nhất cần thiết và khóa hành vi bằng contract test. Khi đó, thay đổi thư viện hoặc cấu hình sẽ không âm thầm làm thay đổi ý nghĩa request.

