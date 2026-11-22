# Phân biệt xử lý null, giá trị thiếu và dữ liệu sai kiểu

## 1. Ba trạng thái đầu vào khác nhau

Khi Jackson đọc JSON vào một đối tượng Java, ba tình huống thường bị nhầm lẫn:

1. **Giá trị null tường minh:** property có mặt trong JSON và giá trị là null.
2. **Giá trị bị thiếu:** property hoàn toàn không xuất hiện trong JSON.
3. **Dữ liệu sai kiểu:** property có mặt nhưng giá trị không phù hợp với kiểu mà ứng dụng mong đợi.

Ví dụ, với property quantity:

~~~json
{}
~~~

Property quantity bị thiếu.

~~~json
{"quantity": null}
~~~

Property quantity có mặt với giá trị JSON null.

~~~json
{"quantity": "twelve"}
~~~

Property quantity có mặt nhưng mang kiểu string, trong khi ứng dụng có thể mong đợi một số nguyên.

Ba trạng thái này thường có ý nghĩa nghiệp vụ khác nhau. Trong một request cập nhật một phần:

- Thiếu trường có thể có nghĩa là giữ nguyên giá trị hiện tại.
- Null có thể có nghĩa là xóa giá trị hoặc đặt trạng thái chưa biết.
- Giá trị sai kiểu thường là dữ liệu không hợp lệ và cần báo lỗi.

Một custom deserializer cần tôn trọng sự khác biệt này. Điểm quan trọng là Jackson không xử lý cả ba trạng thái bằng cùng một lời gọi deserialize().

## 2. Jackson xử lý JSON null qua null value provider

Trong quá trình deserialization, khi parser gặp token JSON null, Jackson thường không gọi phương thức deserialize() của custom deserializer như với một giá trị không null. Thay vào đó, null được xử lý thông qua cơ chế null value provider của property, thường lấy giá trị từ phương thức getNullValue() của deserializer.

Ví dụ, custom deserializer:

~~~java
public class StrictIntegerDeserializer
        extends StdDeserializer<Integer> {

    public StrictIntegerDeserializer() {
        super(Integer.class);
    }

    @Override
    public Integer deserialize(
            JsonParser parser,
            DeserializationContext context
    ) throws IOException {
        // Xử lý token không null.
        return parser.getIntValue();
    }
}
~~~

Nếu JSON có:

~~~json
{"quantity": null}
~~~

không nên giả định đoạn code trong deserialize() sẽ nhận token VALUE_NULL. Với cách xử lý mặc định, Jackson hỏi deserializer giá trị null bằng getNullValue(context). Phương thức này mặc định trả về Java null trong nhiều deserializer.

Có thể override rõ ràng:

~~~java
@Override
public Integer getNullValue(DeserializationContext context)
        throws JsonMappingException {
    return null;
}
~~~

Khi property là wrapper Integer, Jackson có thể gán giá trị null này vào property. Nếu muốn null được chuyển thành một giá trị đặc biệt, có thể trả về giá trị đó từ getNullValue(), nhưng chỉ nên làm khi hợp đồng dữ liệu định nghĩa rõ ý nghĩa thay thế.

Ví dụ, chuyển null thành 0 có thể làm mất khác biệt giữa “client gửi null” và “client gửi số 0”. Không nên chọn giá trị thay thế chỉ để tránh null nếu hai trạng thái có ý nghĩa khác nhau.

## 3. Thuộc tính bị thiếu không tạo ra token JSON

Một property bị thiếu không có token tương ứng trong luồng JSON. Với bean mutable được tạo bằng constructor không tham số, Jackson thường chỉ gán property khi nó xuất hiện trong tài liệu. Nếu property không xuất hiện:

- Setter thường không được gọi.
- Field không được cập nhật bởi quá trình binding.
- Giá trị do field initializer hoặc constructor thiết lập được giữ lại.

Ví dụ:

~~~java
public class Settings {
    private Integer pageSize = 20;

    public Integer getPageSize() {
        return pageSize;
    }

    public void setPageSize(Integer pageSize) {
        this.pageSize = pageSize;
    }
}
~~~

Với JSON:

~~~json
{}
~~~

pageSize vẫn là 20 vì Jackson không nhận được property để gọi setter.

Với JSON:

~~~json
{"pageSize": null}
~~~

Jackson xử lý null theo null policy của property. Với hành vi mặc định thông thường, setter được gọi với Java null và giá trị initializer 20 bị thay thế.

Với JSON:

~~~json
{"pageSize": 50}
~~~

setter được gọi với 50.

Như vậy, initializer có thể giúp biểu diễn giá trị mặc định cho property bị thiếu, còn null tường minh vẫn có thể thay thế giá trị đó.

## 4. Ví dụ đầy đủ: phân biệt missing, null và số nguyên hợp lệ

Custom deserializer sau chỉ chấp nhận JSON integer token. Nó không chấp nhận chuỗi số, số thập phân, boolean, object hoặc array:

~~~java
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JsonMappingException;
import com.fasterxml.jackson.databind.deser.std.StdDeserializer;

import java.io.IOException;

public class StrictIntegerDeserializer
        extends StdDeserializer<Integer> {

    public StrictIntegerDeserializer() {
        super(Integer.class);
    }

    @Override
    public Integer deserialize(
            JsonParser parser,
            DeserializationContext context
    ) throws IOException {
        if (parser.currentToken() == JsonToken.VALUE_NUMBER_INT) {
            // getIntValue() cũng kiểm tra nếu số vượt miền int.
            return parser.getIntValue();
        }

        throw JsonMappingException.from(
                parser,
                "Expected a JSON integer token for quantity"
        );
    }

    @Override
    public Integer getNullValue(DeserializationContext context) {
        return null;
    }
}
~~~

Áp dụng deserializer cho một bean:

~~~java
import com.fasterxml.jackson.annotation.JsonSetter;
import com.fasterxml.jackson.annotation.Nulls;
import com.fasterxml.jackson.databind.annotation.JsonDeserialize;

public class QuantityRequest {
    private Integer quantity = 10;

    public Integer getQuantity() {
        return quantity;
    }

    @JsonSetter(nulls = Nulls.SET)
    @JsonDeserialize(using = StrictIntegerDeserializer.class)
    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }
}
~~~

Kết quả mong đợi:

| JSON | Hành vi | Giá trị quantity sau khi đọc |
|---|---|---:|
| {} | Setter không được gọi; giữ initializer | 10 |
| {"quantity": null} | Null handler trả về Java null; setter nhận null | null |
| {"quantity": 25} | Custom deserializer đọc integer token | 25 |
| {"quantity": "25"} | Custom deserializer từ chối string token | Lỗi mapping |
| {"quantity": 25.5} | Custom deserializer từ chối floating-point token | Lỗi mapping |
| {"quantity": true} | Custom deserializer từ chối boolean token | Lỗi mapping |

Đây là ví dụ về ba nhánh xử lý riêng:

~~~text
                 JSON object
                      |
             property quantity?
                /           \
              No             Yes
              |               |
       Giữ initializer    Giá trị là null?
                          /          \
                        Yes           No
                         |             |
                   getNullValue()   deserialize()
                         |             |
                    Java null      Kiểm tra token
                                      |
                               đúng kiểu / sai kiểu
                                  |       |
                                value    lỗi
~~~

## 5. Null policy với @JsonSetter

Jackson cho phép điều khiển null tường minh ở cấp property bằng @JsonSetter và enum Nulls. Chính sách này có thể thay đổi việc setter hoặc field được cập nhật như thế nào.

| Chính sách | Hành vi khi JSON property có giá trị null |
|---|---|
| Nulls.SET | Gán giá trị null do null provider cung cấp; đây là hành vi thông thường |
| Nulls.SKIP | Bỏ qua thao tác gán; giữ giá trị hiện tại |
| Nulls.FAIL | Báo lỗi khi gặp null |
| Nulls.AS_EMPTY | Dùng giá trị rỗng do deserializer định nghĩa |
| Nulls.DEFAULT | Dùng null policy mặc định của mapper/property |

### Giữ giá trị hiện tại khi nhận null

~~~java
public class UserPreferences {
    private Integer pageSize = 20;

    @JsonSetter(nulls = Nulls.SKIP)
    public void setPageSize(Integer pageSize) {
        this.pageSize = pageSize;
    }

    public Integer getPageSize() {
        return pageSize;
    }
}
~~~

Với JSON {"pageSize": null}, Jackson bỏ qua thao tác gán và pageSize giữ 20. Với JSON {"pageSize": 50}, giá trị được cập nhật thành 50. Với JSON {}, setter cũng không được gọi và initializer tiếp tục được giữ.

Lưu ý: Nulls.SKIP có thể làm setter không được gọi cho null tường minh. Nếu setter đang dùng để đánh dấu rằng client đã gửi property, cờ presence sẽ không được bật trong trường hợp này. Hãy cân nhắc null policy cùng với yêu cầu theo dõi sự hiện diện.

### Từ chối null

~~~java
public class RequiredQuantityRequest {
    private Integer quantity;

    @JsonSetter(nulls = Nulls.FAIL)
    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }
}
~~~

Nulls.FAIL từ chối JSON {"quantity": null}. Nó không tự động từ chối JSON {} vì property bị thiếu không đi qua null handler. Nếu quantity bắt buộc phải xuất hiện, cần kiểm tra missing riêng.

### Giá trị rỗng không đồng nghĩa với null

Nulls.AS_EMPTY yêu cầu deserializer cung cấp giá trị rỗng qua getEmptyValue(). “Rỗng” phụ thuộc kiểu dữ liệu:

- Với collection, thường là collection rỗng.
- Với kiểu có custom deserializer, có thể là giá trị rỗng do deserializer định nghĩa.
- Không nên giả định mọi kiểu đều chuyển null thành 0, false hoặc chuỗi rỗng.

## 6. Null và dữ liệu thiếu trong creator hoặc record

Khi Jackson tạo object qua constructor hoặc creator, property bị thiếu có thể được xử lý khác bean mutable. Creator cần nhận một tập tham số để gọi constructor, vì vậy Jackson phải quyết định giá trị cho tham số không có trong JSON.

Các feature thường liên quan:

- FAIL_ON_MISSING_CREATOR_PROPERTIES: từ chối nếu tham số creator bắt buộc không được cung cấp.
- FAIL_ON_NULL_CREATOR_PROPERTIES: từ chối nếu tham số creator nhận null.
- FAIL_ON_NULL_FOR_PRIMITIVES: từ chối JSON null ánh xạ vào kiểu primitive.

Ví dụ với record:

~~~java
public record CreateOrder(
        String orderId,
        Integer quantity
) {
}
~~~

Có thể cấu hình strict:

~~~java
ObjectMapper strictMapper = JsonMapper.builder()
        .enable(DeserializationFeature.FAIL_ON_MISSING_CREATOR_PROPERTIES)
        .enable(DeserializationFeature.FAIL_ON_NULL_CREATOR_PROPERTIES)
        .enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES)
        .build();
~~~

Với cấu hình này, creator properties phải có mặt và không được null. Nếu ứng dụng cho phép một component tùy chọn, không nên bật chính sách bắt buộc toàn cục mà không xem xét từng kiểu dữ liệu.

### getAbsentValue() và getNullValue()

Trong các phiên bản Jackson có hỗ trợ getAbsentValue(), JsonDeserializer có thể cung cấp riêng giá trị cho creator property bị thiếu. Mặc định, getAbsentValue(context) thường ủy quyền cho getNullValue(context). Vì vậy, nếu custom deserializer thay đổi null value, cần hiểu rằng absent creator value có thể kế thừa hành vi đó nếu không override.

Có thể override riêng:

~~~java
@Override
public Integer getAbsentValue(DeserializationContext context)
        throws JsonMappingException {
    return null;
}
~~~

getNullValue() trả lời câu hỏi “JSON đã gửi null thì giá trị Java là gì?”. getAbsentValue() trả lời câu hỏi “creator property không được gửi thì dùng giá trị nào?”. Hai phương thức có thể trả cùng kết quả, nhưng không bắt buộc phải có cùng chính sách.

Đối với bean mutable thông thường, property bị thiếu thường không làm setter được gọi; không nên trông chờ getAbsentValue() là cách chung để nhận diện mọi property thiếu. Nếu cần phân biệt trạng thái ở mọi kiểu DTO, hãy dùng một mô hình presence rõ ràng hoặc đọc JsonNode trước.

## 7. Kiểu primitive và wrapper làm thay đổi kết quả null

Primitive không thể giữ Java null. Wrapper là kiểu tham chiếu và có thể giữ null.

| Kiểu Java | JSON null mặc định thường được xử lý | Khi muốn từ chối |
|---|---|---|
| int | Giá trị primitive mặc định, thường là 0 | FAIL_ON_NULL_FOR_PRIMITIVES |
| long | Giá trị primitive mặc định, thường là 0L | FAIL_ON_NULL_FOR_PRIMITIVES |
| boolean | false | FAIL_ON_NULL_FOR_PRIMITIVES |
| Integer | Java null | Nulls.FAIL hoặc validation |
| Long | Java null | Nulls.FAIL hoặc validation |
| Boolean | Java null | Nulls.FAIL hoặc validation |

Với custom deserializer cho wrapper, getNullValue() có thể trả null. Với kiểu primitive, Java không thể chứa kết quả null; Jackson có các quy tắc riêng để xử lý null primitive hoặc từ chối qua feature tương ứng.

Nếu miền dữ liệu cần phân biệt “chưa có giá trị” với số 0 hoặc false, wrapper thường thể hiện rõ hơn. Tuy nhiên, wrapper không tự phân biệt property bị thiếu với property có null. Muốn biết client có gửi trường hay không, cần thêm presence tracking.

## 8. Phát hiện property thiếu và null bằng JsonNode

Khi cần kiểm soát rõ cả ba trạng thái trước khi binding, có thể đọc payload thành cây JSON:

~~~java
JsonNode root = mapper.readTree(json);

if (root == null || !root.isObject()) {
    throw new IllegalArgumentException("Expected a JSON object");
}

boolean present = root.has("quantity");
JsonNode quantityNode = root.get("quantity");

if (!present) {
    // Property không tồn tại.
} else if (quantityNode == null || quantityNode.isNull()) {
    // Property tồn tại nhưng giá trị JSON là null.
} else if (quantityNode.isIntegralNumber()) {
    int quantity = quantityNode.intValue();
    // Property có giá trị số nguyên.
} else {
    // Property có mặt nhưng sai kiểu.
}
~~~

Các API quan trọng:

| API | Kết quả |
|---|---|
| get("quantity") | Trả Java null nếu property không tồn tại; trả NullNode nếu property có JSON null |
| has("quantity") | true nếu property tồn tại, kể cả khi giá trị là JSON null |
| hasNonNull("quantity") | true nếu property tồn tại và không phải JSON null |
| path("quantity") | Trả MissingNode nếu không tồn tại, tránh Java null khi điều hướng |
| isMissingNode() | Kiểm tra node đại diện cho property không tồn tại |
| isNull() | Kiểm tra node có giá trị JSON null |
| isIntegralNumber() | Kiểm tra node là số nguyên |
| isTextual() | Kiểm tra node là string |

Không dùng hasNonNull() một mình nếu cần phân biệt missing và explicit null, vì cả hai đều cho kết quả false. Kết hợp has() với isNull() hoặc kiểm tra get() để xác định chính xác trạng thái.

## 9. Theo dõi presence bằng setter

Một cách khác dành cho bean mutable là lưu thêm cờ cho biết property đã xuất hiện trong JSON hay chưa:

~~~java
public class QuantityPatch {
    private Integer quantity;
    private boolean quantityProvided;

    @JsonSetter("quantity")
    @JsonDeserialize(using = StrictIntegerDeserializer.class)
    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
        this.quantityProvided = true;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public boolean isQuantityProvided() {
        return quantityProvided;
    }
}
~~~

Với null policy SET thông thường:

~~~java
QuantityPatch absent = mapper.readValue("{}", QuantityPatch.class);

QuantityPatch explicitNull = mapper.readValue(
        "{\"quantity\":null}",
        QuantityPatch.class
);

QuantityPatch supplied = mapper.readValue(
        "{\"quantity\":12}",
        QuantityPatch.class
);

System.out.println(absent.isQuantityProvided());       // false
System.out.println(explicitNull.isQuantityProvided()); // true
System.out.println(explicitNull.getQuantity() == null);// true
System.out.println(supplied.getQuantity());             // 12
~~~

Đối với payload có sai kiểu, custom deserializer ném lỗi trước khi setter nhận giá trị; request không được xem là hợp lệ. Nếu dùng Nulls.SKIP, null tường minh có thể không gọi setter và cờ presence sẽ không được bật. Nếu nghiệp vụ cần ghi nhận cả null tường minh, dùng Nulls.SET hoặc xử lý trạng thái trước khi áp dụng null policy.

## 10. Thiết kế kiểu ba trạng thái cho request PATCH

Trong một API PATCH, có thể cần biểu diễn ba trạng thái rõ ràng:

~~~java
public enum FieldState {
    ABSENT,
    NULL,
    VALUE
}

public record PatchField<T>(FieldState state, T value) {
    public static <T> PatchField<T> absent() {
        return new PatchField<>(FieldState.ABSENT, null);
    }

    public static <T> PatchField<T> explicitNull() {
        return new PatchField<>(FieldState.NULL, null);
    }

    public static <T> PatchField<T> of(T value) {
        return new PatchField<>(FieldState.VALUE, value);
    }
}
~~~

Sau khi đọc JsonNode, có thể tạo PatchField:

~~~java
PatchField<Integer> readQuantityPatch(JsonNode root) {
    if (!root.has("quantity")) {
        return PatchField.absent();
    }

    JsonNode value = root.get("quantity");
    if (value == null || value.isNull()) {
        return PatchField.explicitNull();
    }

    if (!value.isIntegralNumber() || !value.canConvertToInt()) {
        throw new IllegalArgumentException(
                "quantity must be a 32-bit integer or null"
        );
    }

    return PatchField.of(value.intValue());
}
~~~

Tầng nghiệp vụ có thể xử lý rõ từng trạng thái:

~~~java
switch (patch.state()) {
    case ABSENT -> {
        // Giữ quantity hiện tại.
    }
    case NULL -> {
        // Xóa quantity nếu hợp đồng cho phép.
    }
    case VALUE -> {
        // Cập nhật bằng patch.value().
    }
}
~~~

Đây là một mô hình hữu ích khi API cần semantics rõ ràng. Nó tránh việc dùng một giá trị sentinel như -1 hoặc 0 để biểu diễn “không gửi”, vì các giá trị đó có thể hợp lệ trong miền dữ liệu.

## 11. Phân biệt dữ liệu sai kiểu với dữ liệu có thể coercion

Jackson có thể chuyển đổi một số kiểu đầu vào theo coercion policy. Ví dụ, một số cấu hình có thể cho phép đọc chuỗi số thành số hoặc chuyển số thập phân sang số nguyên. Hành vi cụ thể phụ thuộc kiểu đích, phiên bản Jackson và cấu hình coercion.

Nếu dùng custom deserializer kiểm tra trực tiếp JsonToken như ví dụ StrictIntegerDeserializer, chương trình có thể chủ động từ chối string token và floating-point token, thay vì dựa vào coercion mặc định.

Nếu muốn chấp nhận nhiều dạng:

- JSON integer: chấp nhận 25.
- JSON string: có thể chấp nhận "25" nếu hợp đồng cho phép.
- JSON floating point: quyết định có cho phép 25.0 hay phải từ chối.
- Boolean, object, array: thường từ chối nếu field là số nguyên.

Hãy viết quy tắc rõ ràng. Đừng dùng getValueAsInt() một cách vô điều kiện nếu muốn phân biệt sai kiểu, vì các phương thức tiện ích có thể trả giá trị fallback hoặc chuyển đổi theo cách không thể hiện lỗi rõ ràng.

### Ví dụ chấp nhận string số có chủ đích

~~~java
@Override
public Integer deserialize(
        JsonParser parser,
        DeserializationContext context
) throws IOException {
    JsonToken token = parser.currentToken();

    if (token == JsonToken.VALUE_NUMBER_INT) {
        return parser.getIntValue();
    }

    if (token == JsonToken.VALUE_STRING) {
        String text = parser.getText().trim();
        if (text.isEmpty()) {
            throw JsonMappingException.from(
                    parser,
                    "Empty string is not a valid integer"
            );
        }

        try {
            return Integer.valueOf(text);
        } catch (NumberFormatException error) {
            throw JsonMappingException.from(
                    parser,
                    "String value is not a valid 32-bit integer"
            );
        }
    }

    throw JsonMappingException.from(
            parser,
            "Expected an integer number or numeric string"
    );
}
~~~

Đây là chính sách coercion do ứng dụng định nghĩa. Nếu API không muốn chấp nhận string số, bỏ nhánh VALUE_STRING. Nếu muốn chấp nhận decimal có phần lẻ, phải định nghĩa cách làm tròn hoặc từ chối phần lẻ; không nên âm thầm cắt phần thập phân.

## 12. Dùng CoercionConfig cho kiểu chuẩn

Nếu chỉ cần điều chỉnh coercion của kiểu chuẩn như Integer, có thể xem xét CoercionConfig thay vì viết custom deserializer. Jackson Databind 2.12+ cung cấp API cấu hình coercion theo logical type hoặc kiểu Java.

Ví dụ khái niệm:

~~~java
ObjectMapper mapper = JsonMapper.builder().build();

mapper.coercionConfigFor(LogicalType.Integer)
        .setCoercion(
                CoercionInputShape.String,
                CoercionAction.Fail
        );
~~~

Với cấu hình này, ứng dụng có thể từ chối string khi ánh xạ sang logical integer type. Có thể cấu hình các input shape khác theo hợp đồng.

CoercionConfig phù hợp khi muốn áp dụng quy tắc thống nhất cho kiểu dữ liệu chuẩn. Custom deserializer phù hợp khi quy tắc phụ thuộc vào domain, cần thông báo lỗi riêng hoặc cần chuyển đổi sang một kiểu nghiệp vụ không được Jackson hỗ trợ sẵn.

Khi một property đã gắn custom deserializer, logic trong deserializer có thể quyết định trực tiếp token nào được chấp nhận. Hãy tránh cấu hình coercion ở mapper rồi giả định custom deserializer sẽ tự động tuân theo mọi chính sách đó; cần kiểm thử đúng đường xử lý thực tế.

## 13. Null trong collection và phần tử collection

Một property collection có thể nhận null ở hai cấp:

~~~json
{"tags": null}
~~~

~~~json
{"tags": ["java", null, "jackson"]}
~~~

Trường hợp đầu, chính property tags là null. Trường hợp thứ hai, collection tồn tại nhưng một phần tử là null. Jackson cho phép đặt chính sách riêng bằng nulls và contentNulls:

~~~java
public class TagRequest {
    @JsonSetter(
            nulls = Nulls.AS_EMPTY,
            contentNulls = Nulls.FAIL
    )
    private List<String> tags;

    public List<String> getTags() {
        return tags;
    }

    public void setTags(List<String> tags) {
        this.tags = tags;
    }
}
~~~

Với cấu hình trên, null của property được chuyển thành giá trị rỗng theo deserializer của List; null ở một phần tử bị từ chối. Điều này minh họa rằng null policy của container và null policy của nội dung là hai quy tắc riêng.

Nếu một phần tử có sai kiểu, ví dụ số thay cho string, deserializer của phần tử sẽ xử lý coercion hoặc báo lỗi theo cấu hình. contentNulls chỉ điều khiển null, không thay thế validation kiểu cho mọi phần tử.

## 14. Tạo thông báo lỗi hữu ích

Một custom deserializer nên báo rõ:

- Tên hoặc ý nghĩa field nếu biết.
- Kiểu JSON thực tế nhận được.
- Kiểu mà ứng dụng mong đợi.
- Giá trị có thể hợp lệ nếu quy tắc không hiển nhiên.

Ví dụ:

~~~java
throw JsonMappingException.from(
        parser,
        "Expected a JSON integer for quantity, but received "
                + parser.currentToken()
);
~~~

Jackson có thể bọc lỗi trong một ngoại lệ mapping kèm path đến property. Thông tin path giúp xác định vị trí sai trong payload lồng nhau.

Không nên đưa toàn bộ giá trị đầu vào vào log hoặc thông báo lỗi công khai nếu nó có thể chứa dữ liệu nhạy cảm. Tên field, token type và đường dẫn thường đủ để chẩn đoán.

## 15. Ma trận kiểm thử cho custom deserializer

Một custom deserializer cần được kiểm thử riêng cho từng trạng thái:

| Ca | Payload | Mục tiêu |
|---|---|---|
| T01 | {} | Property thiếu; xác nhận initializer hoặc absent policy |
| T02 | {"quantity": null} | Explicit null; xác nhận getNullValue/null policy |
| T03 | {"quantity": 12} | Giá trị đúng kiểu |
| T04 | {"quantity": "12"} | String token; chấp nhận hoặc từ chối theo hợp đồng |
| T05 | {"quantity": 12.5} | Floating-point token; kiểm tra chính sách decimal |
| T06 | {"quantity": true} | Boolean token phải bị từ chối với integer field |
| T07 | {"quantity": {}} | Object token phải bị từ chối |
| T08 | {"quantity": []} | Array token phải bị từ chối |
| T09 | {"quantity": 2147483648} | Số vượt miền int |
| T10 | {"quantity": null} với Nulls.SKIP | Setter có bị bỏ qua theo null policy không |
| T11 | Creator property bị thiếu | FAIL_ON_MISSING_CREATOR_PROPERTIES hoặc getAbsentValue |
| T12 | Creator property null | FAIL_ON_NULL_CREATOR_PROPERTIES hoặc getNullValue |

Ví dụ kiểm thử JUnit cho bean:

~~~java
class QuantityRequestTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void missingPropertyKeepsInitializer() throws Exception {
        QuantityRequest request = mapper.readValue(
                "{}",
                QuantityRequest.class
        );

        assertEquals(10, request.getQuantity());
    }

    @Test
    void explicitNullSetsWrapperToNull() throws Exception {
        QuantityRequest request = mapper.readValue(
                "{\"quantity\":null}",
                QuantityRequest.class
        );

        assertNull(request.getQuantity());
    }

    @Test
    void validIntegerIsAccepted() throws Exception {
        QuantityRequest request = mapper.readValue(
                "{\"quantity\":25}",
                QuantityRequest.class
        );

        assertEquals(25, request.getQuantity());
    }

    @Test
    void stringIsRejectedByStrictDeserializer() {
        assertThrows(
                JsonMappingException.class,
                () -> mapper.readValue(
                        "{\"quantity\":\"25\"}",
                        QuantityRequest.class
                )
        );
    }
}
~~~

Các test nên chạy trên đúng phiên bản Jackson mà ứng dụng sử dụng. Null provider, creator handling và coercion có thể chịu ảnh hưởng bởi phiên bản và cấu hình mapper; fixture giúp ghi lại hành vi hợp đồng mong muốn.

## 16. Chọn cơ chế phù hợp với yêu cầu

| Yêu cầu | Cơ chế nên xem xét |
|---|---|
| Chuyển explicit null thành Java null | getNullValue() hoặc Nulls.SET |
| Từ chối explicit null | Nulls.FAIL |
| Bỏ qua explicit null và giữ giá trị cũ | Nulls.SKIP |
| Dùng giá trị rỗng cho explicit null | Nulls.AS_EMPTY và getEmptyValue() |
| Bắt buộc creator property phải xuất hiện | FAIL_ON_MISSING_CREATOR_PROPERTIES |
| Bắt buộc creator property không được null | FAIL_ON_NULL_CREATOR_PROPERTIES |
| Từ chối null cho primitive | FAIL_ON_NULL_FOR_PRIMITIVES |
| Phân biệt missing với explicit null trong bean PATCH | Setter presence flag hoặc JsonNode |
| Kiểm soát kiểu JSON được chấp nhận | Custom deserializer kiểm tra JsonToken |
| Điều chỉnh coercion của kiểu chuẩn | CoercionConfig |
| Giữ trạng thái ABSENT/NULL/VALUE rõ ràng | PatchField hoặc kiểu tri-state riêng |

Không nên viết custom deserializer cho mọi property chỉ để xử lý null. Các annotation và feature có sẵn thường đủ cho chính sách chung. Custom deserializer hữu ích khi cần quy tắc kiểu dữ liệu cụ thể, validation token nghiêm ngặt hoặc thông báo lỗi theo domain.

## 17. Kết luận

Jackson xử lý explicit JSON null qua null value provider, thường là getNullValue(), chứ custom deserialize() không nhất thiết nhận token VALUE_NULL. Property bị thiếu không tạo token; với bean mutable, setter thường không được gọi và initializer được giữ nguyên. Với creator hoặc record, cần xem xét absent-value handling và các feature kiểm tra creator property. Dữ liệu sai kiểu đi qua deserializer và nên được kiểm tra token hoặc coercion theo hợp đồng. Nếu API cần phân biệt ABSENT, NULL và VALUE, hãy theo dõi presence bằng setter hoặc đọc JsonNode trước khi binding. Khi ba trạng thái được xử lý riêng, custom deserializer có thể báo lỗi chính xác mà không vô tình biến dữ liệu thiếu, null và sai kiểu thành cùng một giá trị.
