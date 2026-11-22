# Đọc dữ liệu từ JsonParser với kiểm tra loại token

Khi cần đọc JSON theo cách có kiểm soát, Jackson Core cung cấp JsonParser để duyệt dữ liệu từng token. Mỗi lần gọi nextToken() đưa parser đến một phần tử của JSON như dấu bắt đầu object, tên field, chuỗi, số, boolean, null hoặc dấu kết thúc array/object.

Cách đọc này cho phép ứng dụng xác nhận loại token trước khi lấy giá trị. Ví dụ, nếu hợp đồng yêu cầu quantity là số nguyên, code có thể chỉ chấp nhận VALUE_NUMBER_INT thay vì để Jackson tự chuyển chuỗi "12", số 12.5 hoặc boolean thành một giá trị số theo quy tắc coercion.

Đọc trực tiếp từ JsonParser phù hợp khi cần kiểm soát chặt hình dạng input, xử lý dữ liệu lớn theo luồng hoặc triển khai custom deserializer. Với DTO thông thường, databinding tiêu chuẩn thường ngắn gọn hơn; chỉ nên tự duyệt token khi yêu cầu về cấu trúc và kiểu dữ liệu thực sự cần mức kiểm soát đó.

## 1. JsonParser đọc JSON theo token

JSON có object, array và các giá trị scalar. JsonParser chuyển văn bản JSON thành một chuỗi token theo thứ tự xuất hiện.

Ví dụ input:

~~~json
{
  "orderId": "ORD-100",
  "quantity": 2,
  "paid": true,
  "tags": ["priority", "online"]
}
~~~

Các token chính mà parser nhìn thấy có dạng:

~~~text
START_OBJECT
FIELD_NAME         orderId
VALUE_STRING       ORD-100
FIELD_NAME         quantity
VALUE_NUMBER_INT   2
FIELD_NAME         paid
VALUE_TRUE         true
FIELD_NAME         tags
START_ARRAY
VALUE_STRING       priority
VALUE_STRING       online
END_ARRAY
END_OBJECT
~~~

JsonToken mô tả loại token hiện tại. Parser không tự tạo DTO trong ví dụ này; ứng dụng quyết định cách đọc và kiểm tra từng token.

Một số token thường gặp:

| JsonToken | Ý nghĩa |
|---|---|
| START_OBJECT | Bắt đầu JSON object, ký tự { |
| END_OBJECT | Kết thúc JSON object, ký tự } |
| START_ARRAY | Bắt đầu JSON array, ký tự [ |
| END_ARRAY | Kết thúc JSON array, ký tự ] |
| FIELD_NAME | Tên thuộc tính bên trong object |
| VALUE_STRING | Giá trị chuỗi |
| VALUE_NUMBER_INT | Token số nguyên |
| VALUE_NUMBER_FLOAT | Token số có phần thập phân hoặc exponent |
| VALUE_TRUE | Giá trị boolean true |
| VALUE_FALSE | Giá trị boolean false |
| VALUE_NULL | Giá trị JSON null |

Các token cấu trúc như START_OBJECT và START_ARRAY cho biết parser đi vào một container. Những token VALUE_* biểu diễn giá trị scalar. FIELD_NAME là tên thuộc tính, không phải giá trị của thuộc tính đó.

## 2. Tạo parser và duyệt token

Có thể tạo JsonParser từ JsonFactory. ObjectMapper cũng cung cấp factory đã được cấu hình tương ứng.

~~~java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;

JsonFactory factory = new JsonFactory();

try (JsonParser parser = factory.createParser(json)) {
    JsonToken token;

    while ((token = parser.nextToken()) != null) {
        System.out.println(token);

        if (token == JsonToken.FIELD_NAME) {
            System.out.println("Field: " + parser.currentName());
        } else if (token == JsonToken.VALUE_STRING) {
            System.out.println("Text: " + parser.getText());
        }
    }
}
~~~

nextToken() di chuyển parser đến token kế tiếp và trả về loại token đó. Khi parser đã tiêu thụ hết một input hợp lệ, phương thức trả về null.

Các API thường dùng:

- currentToken() trả về loại token parser đang đứng tại thời điểm hiện tại.
- nextToken() chuyển sang token tiếp theo.
- currentName() hoặc getCurrentName() lấy tên field hiện tại trong object.
- getText() lấy nội dung dạng text của token hiện tại.
- getIntValue(), getLongValue(), getDecimalValue() lấy giá trị số sau khi đã xác nhận token phù hợp.
- skipChildren() bỏ qua toàn bộ object hoặc array con đang mở.
- getParsingContext() cung cấp thông tin về ngữ cảnh object/array hiện tại.

Trong code cần tương thích với nhiều phiên bản Jackson 2.x, có thể gặp cả tên API currentName() và getCurrentName(). Hãy dùng API có trong phiên bản dự án; các ví dụ bên dưới dùng currentName() của Jackson hiện đại.

Parser có trạng thái. Mỗi lần gọi nextToken() làm thay đổi vị trí hiện tại, vì vậy chỉ đọc getText() hoặc getIntValue() sau khi đã xác nhận parser đang ở đúng token.

## 3. Kiểm tra token trước khi đọc giá trị

Giả sử một field phải là chuỗi. Không nên gọi getText() một cách mù quáng rồi chấp nhận mọi dạng input. Hãy kiểm tra token:

~~~java
JsonToken token = parser.nextToken();

if (token != JsonToken.VALUE_STRING) {
    throw JsonMappingException.from(
        parser,
        "orderId must be a JSON string"
    );
}

String orderId = parser.getText();
~~~

Nếu input là:

~~~json
{ "orderId": 100 }
~~~

parser trả về VALUE_NUMBER_INT cho giá trị của orderId. Kiểm tra trên sẽ từ chối thay vì tự chuyển 100 thành chuỗi.

Tương tự, nếu field yêu cầu boolean:

~~~java
JsonToken token = parser.nextToken();

if (token != JsonToken.VALUE_TRUE
        && token != JsonToken.VALUE_FALSE) {
    throw JsonMappingException.from(
        parser,
        "enabled must be a JSON boolean"
    );
}

boolean enabled = token == JsonToken.VALUE_TRUE;
~~~

Cách này chỉ chấp nhận hai token boolean thật. Giá trị chuỗi "true", số 1 hoặc null không được coi là boolean hợp lệ.

Nếu hợp đồng cho phép null, hãy xử lý VALUE_NULL thành một nhánh riêng trước khi kiểm tra loại giá trị. Đừng gộp null với token sai kiểu nếu hai trường hợp cần trả lỗi khác nhau.

## 4. Phân biệt số nguyên với số dấu phẩy động

JSON có một kiểu number chung, nhưng Jackson phân biệt token số nguyên và token dấu phẩy động theo dạng biểu diễn.

Ví dụ:

~~~json
12
~~~

là VALUE_NUMBER_INT, trong khi:

~~~json
12.0
~~~

và:

~~~json
12.5
~~~

là VALUE_NUMBER_FLOAT. Cách viết exponent như 1e3 cũng được phân loại là token số dấu phẩy động, dù giá trị toán học của nó là 1000.

Nếu quantity phải được gửi dưới dạng số nguyên, hãy kiểm tra chính xác token:

~~~java
JsonToken token = parser.nextToken();

if (token != JsonToken.VALUE_NUMBER_INT) {
    throw JsonMappingException.from(
        parser,
        "quantity must use an integer JSON token"
    );
}

int quantity = parser.getIntValue();
~~~

Cách này từ chối 12.0, 12.5 và 1e3. Nó kiểm tra hình dạng token, không chỉ giá trị toán học.

Nếu hợp đồng cho phép 12.0 vì giá trị toán học vẫn là số nguyên, hãy đọc thành BigDecimal rồi kiểm tra scale và phạm vi. Không nên dùng getIntValue() trực tiếp nếu cần từ chối phần thập phân khác không.

Để kiểm tra phạm vi int mà không phụ thuộc vào ép kiểu, có thể đọc BigInteger:

~~~java
BigInteger value = parser.getBigIntegerValue();

if (value.compareTo(BigInteger.valueOf(Integer.MIN_VALUE)) < 0
        || value.compareTo(BigInteger.valueOf(Integer.MAX_VALUE)) > 0) {
    throw JsonMappingException.from(parser, "quantity is outside int range");
}

int quantity = value.intValue();
~~~

Đoạn này chỉ gọi sau khi đã xác nhận token là VALUE_NUMBER_INT. Nếu token là VALUE_NUMBER_FLOAT, cần từ chối hoặc xử lý theo một quy tắc decimal riêng.

## 5. Kiểm tra cấu trúc object và tên field

Khi đọc một object, parser thường đi qua các bước:

1. START_OBJECT.
2. FIELD_NAME.
3. Token giá trị của field.
4. FIELD_NAME tiếp theo hoặc END_OBJECT.

Ví dụ một vòng lặp cơ bản:

~~~java
if (parser.nextToken() != JsonToken.START_OBJECT) {
    throw JsonMappingException.from(parser, "Expected a JSON object");
}

while (parser.nextToken() != JsonToken.END_OBJECT) {
    if (parser.currentToken() != JsonToken.FIELD_NAME) {
        throw JsonMappingException.from(parser, "Expected a field name");
    }

    String fieldName = parser.currentName();
    JsonToken valueToken = parser.nextToken();

    if (valueToken == null) {
        throw JsonMappingException.from(parser, "Unexpected end of JSON input");
    }

    // Kiểm tra valueToken và xử lý fieldName tại đây.
}
~~~

Đừng giả định field xuất hiện theo thứ tự khai báo trong class hoặc theo thứ tự của ví dụ JSON. JSON object không yêu cầu thứ tự field cố định. Hãy phân nhánh theo tên field.

Nếu một field bắt buộc không xuất hiện, vòng lặp vẫn có thể kết thúc bình thường bằng END_OBJECT. Ứng dụng cần theo dõi những field đã thấy và kiểm tra sau khi object kết thúc.

Nếu input kết thúc trước END_OBJECT, parser có thể ném JsonEOFException khi nextToken() cần thêm dữ liệu. Không nên tự coi null ở giữa object là kết thúc hợp lệ.

## 6. Ví dụ đọc object với kiểm tra loại token

Giả sử request có hợp đồng:

~~~json
{
  "orderId": "ORD-100",
  "quantity": 2
}
~~~

orderId là chuỗi bắt buộc; quantity là số nguyên bắt buộc trong phạm vi int. Ví dụ sau minh họa cách đọc trực tiếp:

~~~java
public record OrderRequest(String orderId, int quantity) {}

public OrderRequest readOrder(JsonParser parser) throws IOException {
    if (parser.currentToken() == null
            && parser.nextToken() != JsonToken.START_OBJECT) {
        throw JsonMappingException.from(parser, "Expected an object");
    }

    if (parser.currentToken() != JsonToken.START_OBJECT) {
        throw JsonMappingException.from(parser, "Expected an object");
    }

    String orderId = null;
    Integer quantity = null;

    while (parser.nextToken() != JsonToken.END_OBJECT) {
        if (parser.currentToken() != JsonToken.FIELD_NAME) {
            throw JsonMappingException.from(parser, "Expected a field name");
        }

        String name = parser.currentName();
        JsonToken valueToken = parser.nextToken();

        if (valueToken == null) {
            throw JsonMappingException.from(parser, "Unexpected end of input");
        }

        switch (name) {
            case "orderId" -> {
                if (valueToken != JsonToken.VALUE_STRING) {
                    throw JsonMappingException.from(
                        parser,
                        "orderId must be a string"
                    );
                }
                orderId = parser.getText();
            }
            case "quantity" -> {
                if (valueToken != JsonToken.VALUE_NUMBER_INT) {
                    throw JsonMappingException.from(
                        parser,
                        "quantity must be an integer"
                    );
                }
                quantity = parser.getIntValue();
            }
            default -> parser.skipChildren();
        }
    }

    if (orderId == null) {
        throw JsonMappingException.from(parser, "Missing orderId");
    }

    if (quantity == null) {
        throw JsonMappingException.from(parser, "Missing quantity");
    }

    return new OrderRequest(orderId, quantity);
}
~~~

Ví dụ giả định parser đang ở START_OBJECT khi hàm được gọi, hoặc chưa có token và cần nextToken() để đến START_OBJECT. Khi triển khai custom deserializer, Jackson thường đã đặt parser tại token bắt đầu giá trị cần deserialize.

Trong code production, nên kiểm tra trùng tên field nếu hợp đồng yêu cầu từ chối duplicate keys. Cũng cần quyết định rõ unknown field sẽ bị bỏ qua hay từ chối; skipChildren() chỉ bỏ qua dữ liệu, không tự xác nhận field đó được phép.

## 7. Đọc array và kiểm tra từng phần tử

Array bắt đầu bằng START_ARRAY và kết thúc bằng END_ARRAY. Các phần tử có thể là scalar, object hoặc array lồng nhau.

Giả sử tags phải là array chỉ chứa string:

~~~json
{
  "tags": ["java", "jackson"]
}
~~~

Có thể đọc như sau:

~~~java
List<String> readStringArray(JsonParser parser) throws IOException {
    if (parser.currentToken() != JsonToken.START_ARRAY) {
        throw JsonMappingException.from(parser, "Expected an array");
    }

    List<String> values = new ArrayList<>();

    JsonToken token;
    while ((token = parser.nextToken()) != JsonToken.END_ARRAY) {
        if (token == null) {
            throw JsonMappingException.from(
                parser,
                "Unexpected end of array"
            );
        }

        if (token != JsonToken.VALUE_STRING) {
            throw JsonMappingException.from(
                parser,
                "Every array element must be a string"
            );
        }

        values.add(parser.getText());
    }

    return values;
}
~~~

Đoạn code từ chối:

~~~json
["java", 10, true]
~~~

vì phần tử thứ hai không phải VALUE_STRING.

Nếu array được phép chứa null, hãy thêm nhánh VALUE_NULL và quyết định biểu diễn null trong List. Nếu array chứa object con, cần đọc object đó theo một hàm riêng hoặc dùng databinding cho từng phần tử.

Với array rất lớn, có thể xử lý từng phần tử ngay khi parser đến thay vì giữ tất cả trong List. Tuy nhiên, chỉ commit một phần tử sau khi token và cấu trúc của phần tử đó đã hoàn chỉnh.

## 8. Đọc object lồng nhau và bỏ qua subtree

Khi parser đang đứng ở START_OBJECT hoặc START_ARRAY của một field không cần xử lý, skipChildren() sẽ bỏ qua toàn bộ subtree và đặt parser tại token kết thúc container tương ứng.

Ví dụ:

~~~java
String name = parser.currentName();
JsonToken valueToken = parser.nextToken();

if ("metadata".equals(name)) {
    parser.skipChildren();
} else {
    // Xử lý field khác.
}
~~~

Nếu metadata là object hoặc array, parser bỏ qua nội dung lồng bên trong. Nếu metadata là scalar, skipChildren() không cần làm gì.

Đây là cách hữu ích khi schema có nhiều field nhưng một consumer chỉ cần một vài field. Nó giúp tránh phải tự duyệt từng cấp của subtree không liên quan.

Không nên gọi skipChildren() trước khi xử lý field cần giữ. Một khi parser đã bỏ qua subtree, các token con không còn được đọc lại từ vị trí hiện tại. Nếu cần xử lý nhiều lần, có thể lưu node, buffer dữ liệu hoặc parse riêng theo thiết kế.

## 9. Phân biệt null, thiếu field và sai kiểu token

Ba trường hợp này khác nhau:

~~~json
{}
~~~

~~~json
{ "quantity": null }
~~~

~~~json
{ "quantity": "2" }
~~~

- Không có quantity: field bị thiếu.
- VALUE_NULL: field có mặt và explicit null.
- VALUE_STRING: field có mặt nhưng sai kiểu nếu hợp đồng yêu cầu number.

Khi đọc thủ công, ứng dụng có thể giữ sự khác biệt bằng cách theo dõi field đã thấy:

~~~java
boolean quantitySeen = false;
Integer quantity = null;

// Khi gặp field quantity:
quantitySeen = true;

if (valueToken == JsonToken.VALUE_NULL) {
    throw JsonMappingException.from(parser, "quantity must not be null");
}

if (valueToken != JsonToken.VALUE_NUMBER_INT) {
    throw JsonMappingException.from(parser, "quantity must be an integer");
}
~~~

Sau khi END_OBJECT:

~~~java
if (!quantitySeen) {
    throw JsonMappingException.from(parser, "quantity is required");
}
~~~

Với kiểu tham chiếu, dùng một biến boolean hoặc tập tên field đã thấy nếu cần phân biệt missing và null. Chỉ kiểm tra biến giá trị khác null là chưa đủ nếu null được phép nhưng field bắt buộc phải xuất hiện.

Với primitive int, Java có giá trị mặc định là 0. Nếu dùng biến primitive để theo dõi parse, không thể biết 0 đến từ input hay chỉ là giá trị khởi tạo. Dùng Integer hoặc một cờ presence trong giai đoạn đọc, rồi mới tạo DTO primitive sau khi kiểm tra.

## 10. Xử lý field không biết và field trùng

Khi parser gặp FIELD_NAME không thuộc schema, ứng dụng có hai lựa chọn chính:

**Bỏ qua field không biết:**

~~~java
default -> parser.skipChildren();
~~~

Cách này giúp consumer tương thích với producer có thể bổ sung field mới. Nếu giá trị là object hoặc array, skipChildren() bỏ toàn bộ nội dung của nó.

**Từ chối field không biết:**

~~~java
default -> throw JsonMappingException.from(
    parser,
    "Unknown property: " + name
);
~~~

Cách này phù hợp với hợp đồng đóng, nơi mọi field đều phải được khai báo.

Field trùng cũng cần chính sách rõ ràng. Ví dụ:

~~~json
{
  "quantity": 2,
  "quantity": 9
}
~~~

Nếu parser đọc lần lượt và code gán lại biến, giá trị sau có thể ghi đè giá trị trước. Muốn từ chối duplicate name, theo dõi tên đã thấy:

~~~java
Set<String> seen = new HashSet<>();

if (!seen.add(name)) {
    throw JsonMappingException.from(
        parser,
        "Duplicate property: " + name
    );
}
~~~

Hoặc bật StreamReadFeature.STRICT_DUPLICATE_DETECTION trên JsonFactory để parser phát hiện tên lặp trong object. Cơ chế parser-wide này hữu ích khi nhiều loại object cần cùng chính sách.

Không nên dựa vào việc consumer thường lấy giá trị đầu hay cuối của duplicate key. Các parser và hệ thống có thể xử lý khác nhau.

## 11. Kiểm tra loại token cho object lồng nhau

Giả sử field customer phải là object:

~~~json
{
  "customer": {
    "id": "CUS-17",
    "name": "Linh"
  }
}
~~~

Trước khi đọc field con, xác nhận token là START_OBJECT:

~~~java
if (valueToken != JsonToken.START_OBJECT) {
    throw JsonMappingException.from(parser, "customer must be an object");
}
~~~

Sau đó duyệt các FIELD_NAME bên trong và kiểm tra token của từng giá trị. Không dùng parser.getText() để giả định mọi giá trị đều là chuỗi.

Nếu field con là array, xác nhận START_ARRAY. Nếu là scalar, xác nhận token VALUE_* tương ứng. Cấu trúc lồng nhau nên được tách thành các hàm nhỏ như readCustomer(), readTags() hoặc readAddress() để logic token rõ ràng và dễ kiểm thử.

Khi hàm con kết thúc, parser phải ở đúng token END_OBJECT hoặc END_ARRAY của subtree đó. Nếu hàm con tiêu thụ quá nhiều token hoặc dừng quá sớm, vòng lặp cha sẽ mất đồng bộ.

## 12. Đọc dữ liệu bằng custom JsonDeserializer

Khi muốn tích hợp token validation với ObjectMapper, hãy viết JsonDeserializer<T>. Jackson gọi deserialize() tại đúng vị trí parser của giá trị cần chuyển đổi.

Ví dụ hoàn chỉnh:

~~~java
public record OrderRequest(
    String orderId,
    int quantity,
    List<String> tags
) {}
~~~

Deserializer:

~~~java
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JsonMappingException;
import com.fasterxml.jackson.databind.deser.std.StdDeserializer;

import java.io.IOException;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public final class OrderRequestDeserializer
        extends StdDeserializer<OrderRequest> {

    public OrderRequestDeserializer() {
        super(OrderRequest.class);
    }

    @Override
    public OrderRequest deserialize(
            JsonParser parser,
            DeserializationContext context) throws IOException {

        if (parser.currentToken() == null
                && parser.nextToken() != JsonToken.START_OBJECT) {
            throw JsonMappingException.from(parser, "Expected an object");
        }

        if (parser.currentToken() != JsonToken.START_OBJECT) {
            throw JsonMappingException.from(parser, "Expected an object");
        }

        String orderId = null;
        Integer quantity = null;
        List<String> tags = new ArrayList<>();

        Set<String> seen = new HashSet<>();

        JsonToken token;
        while ((token = parser.nextToken()) != JsonToken.END_OBJECT) {
            if (token == null) {
                throw JsonMappingException.from(
                    parser,
                    "Unexpected end of OrderRequest"
                );
            }

            if (token != JsonToken.FIELD_NAME) {
                throw JsonMappingException.from(parser, "Expected a field name");
            }

            String name = parser.currentName();

            if (!seen.add(name)) {
                throw JsonMappingException.from(
                    parser,
                    "Duplicate property: " + name
                );
            }

            JsonToken valueToken = parser.nextToken();

            if (valueToken == null) {
                throw JsonMappingException.from(
                    parser,
                    "Missing value for property " + name
                );
            }

            switch (name) {
                case "orderId" -> {
                    if (valueToken != JsonToken.VALUE_STRING) {
                        throw JsonMappingException.from(
                            parser,
                            "orderId must be a string"
                        );
                    }
                    orderId = parser.getText();
                }
                case "quantity" -> {
                    if (valueToken != JsonToken.VALUE_NUMBER_INT) {
                        throw JsonMappingException.from(
                            parser,
                            "quantity must be an integer"
                        );
                    }
                    quantity = parser.getIntValue();
                }
                case "tags" -> {
                    if (valueToken != JsonToken.START_ARRAY) {
                        throw JsonMappingException.from(
                            parser,
                            "tags must be an array"
                        );
                    }

                    tags.clear();

                    JsonToken element;
                    while ((element = parser.nextToken()) != JsonToken.END_ARRAY) {
                        if (element == null) {
                            throw JsonMappingException.from(
                                parser,
                                "Unexpected end of tags array"
                            );
                        }

                        if (element != JsonToken.VALUE_STRING) {
                            throw JsonMappingException.from(
                                parser,
                                "Every tag must be a string"
                            );
                        }

                        tags.add(parser.getText());
                    }
                }
                default -> parser.skipChildren();
            }
        }

        if (orderId == null) {
            throw JsonMappingException.from(parser, "Missing orderId");
        }

        if (quantity == null) {
            throw JsonMappingException.from(parser, "Missing quantity");
        }

        return new OrderRequest(orderId, quantity, List.copyOf(tags));
    }
}
~~~

Deserializer này áp dụng chính sách cụ thể:

- Root phải là object.
- orderId phải là VALUE_STRING.
- quantity phải là VALUE_NUMBER_INT và nằm trong phạm vi int.
- tags nếu xuất hiện phải là array chỉ chứa string.
- tags bị thiếu được xem như danh sách rỗng.
- Field không biết được bỏ qua.
- Field trùng bị từ chối.
- Explicit null cho các field đã khai báo bị từ chối vì không khớp loại token yêu cầu.

Nếu muốn tags cho phép null, cần thêm nhánh VALUE_NULL và định nghĩa kết quả Java tương ứng. Nếu muốn unknown field bị từ chối, thay default bằng JsonMappingException. Đây là chính sách của hợp đồng cụ thể, không phải quy tắc bắt buộc của mọi deserializer.

## 13. Đăng ký custom deserializer

Có thể đăng ký deserializer qua SimpleModule:

~~~java
SimpleModule module = new SimpleModule();
module.addDeserializer(
    OrderRequest.class,
    new OrderRequestDeserializer()
);

ObjectMapper mapper = JsonMapper.builder()
    .addModule(module)
    .build();
~~~

Sau đó dùng ObjectMapper như bình thường:

~~~java
OrderRequest request = mapper.readValue(json, OrderRequest.class);
~~~

Nếu chỉ một property cần cách đọc riêng, có thể gắn @JsonDeserialize(using = ...) trên property hoặc kiểu tương ứng.

Module nên được đăng ký khi mapper được xây dựng, trước khi mapper được chia sẻ giữa các luồng. Không nên thêm module hoặc thay đổi cấu hình mapper sau khi ứng dụng đã bắt đầu xử lý request đồng thời.

Nếu Spring Boot tự cấu hình ObjectMapper, hãy đăng ký module vào mapper thực sự được HTTP message converter sử dụng. Tạo một mapper mới trong service không tự thay đổi cách framework deserialize @RequestBody.

## 14. Parser position khi Jackson gọi custom deserializer

Một lỗi phổ biến là gọi nextToken() quá nhiều lần ở đầu deserialize().

Khi Jackson Databind gọi custom deserializer cho một object property, parser thường đã đứng tại token đầu tiên của giá trị, ví dụ START_OBJECT. Nếu code luôn gọi nextToken() ngay lập tức, nó có thể bỏ qua token bắt đầu và đứng ở FIELD_NAME.

Mẫu an toàn thường là:

~~~java
JsonToken current = parser.currentToken();

if (current == null) {
    current = parser.nextToken();
}

if (current != JsonToken.START_OBJECT) {
    throw JsonMappingException.from(parser, "Expected an object");
}
~~~

Sau đó, vòng lặp mới gọi nextToken() để lấy FIELD_NAME tiếp theo.

Khi viết hàm đọc riêng được gọi từ code streaming thủ công, hãy ghi rõ hợp đồng vị trí parser: hàm nhận parser đang ở token nào và trả về khi parser ở token nào. Điều này giúp tránh việc hàm cha và hàm con cùng tiêu thụ một token.

Với custom deserializer cho scalar hoặc array, logic tương tự: xác nhận currentToken() trước khi đọc giá trị hoặc duyệt phần tử.

## 15. skipChildren() và việc giữ đồng bộ parser

skipChildren() hữu ích nhưng cần hiểu vị trí sau khi gọi.

Nếu parser đang ở START_OBJECT hoặc START_ARRAY, phương thức bỏ qua toàn bộ nội dung lồng nhau và dừng tại END_OBJECT hoặc END_ARRAY tương ứng.

Ví dụ:

~~~java
JsonToken valueToken = parser.nextToken();

if (valueToken == JsonToken.START_OBJECT
        || valueToken == JsonToken.START_ARRAY) {
    parser.skipChildren();
}
~~~

Sau lời gọi, vòng lặp bên ngoài có thể gọi nextToken() để chuyển sang field tiếp theo. Không cần tự gọi nextToken() thêm một lần để bỏ qua token END_* vì skipChildren() đã đưa parser đến token kết thúc container.

Nếu gọi skipChildren() khi parser đang ở scalar, phương thức không bỏ qua token kế tiếp. Vì vậy, chỉ dùng nó sau khi đã biết token hiện tại là container hoặc khi chấp nhận hành vi no-op đối với scalar.

## 16. Kiểm tra root và dữ liệu sau root

Một custom deserializer thường chỉ chịu trách nhiệm đọc giá trị của kiểu mà nó xử lý. Việc xác nhận toàn bộ input chỉ có một root JSON value là chính sách ở cấp ObjectReader hoặc ObjectMapper.

Nếu hợp đồng yêu cầu một document duy nhất, bật FAIL_ON_TRAILING_TOKENS:

~~~java
ObjectReader strictReader = mapper
    .readerFor(OrderRequest.class)
    .with(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);

OrderRequest request = strictReader.readValue(json);
~~~

Deserializer đọc xong END_OBJECT của OrderRequest. Reader strict tiếp tục kiểm tra token còn lại và từ chối nếu có một root value thứ hai.

Ví dụ input:

~~~text
{"orderId":"ORD-100","quantity":2} true
~~~

Object đầu tiên hợp lệ, nhưng boolean đứng sau là dữ liệu dư. Đây là lỗi ở ranh giới document, khác với việc một field bên trong object có token sai loại.

## 17. Xử lý EOF và lỗi parse trong quá trình đọc token

Nếu nguồn kết thúc khi parser vẫn cần thêm token để đóng object hoặc array, Jackson có thể ném JsonEOFException hoặc JsonParseException tương ứng.

Ví dụ:

~~~json
{
  "orderId": "ORD-100",
  "tags": ["java"
~~~

Đừng bắt lỗi rồi trả về DTO được tạo từ các field đã đọc trước đó. Một object chỉ hợp lệ khi toàn bộ cấu trúc đã được đọc hoàn chỉnh.

JsonMappingException dùng cho input có cấu trúc parse được nhưng vi phạm quy tắc ánh xạ hoặc kiểu token mà deserializer yêu cầu. JsonEOFException phản ánh nguồn kết thúc khi cú pháp chưa hoàn chỉnh. IOException còn có thể xuất phát từ file, socket hoặc transport.

Hãy để lỗi parse/I/O đi lên tầng adapter phù hợp. Tại đó, ứng dụng quyết định trả HTTP 400, đánh dấu message lỗi hoặc yêu cầu producer gửi lại. Không nên coi mọi lỗi là dữ liệu sai kiểu; lỗi transport có chính sách retry khác với lỗi hợp đồng.

## 18. Kiểm thử token validation bằng JUnit

Test nên xác nhận cả input đúng và các token sai kiểu:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.databind.module.SimpleModule;
import org.junit.jupiter.api.Test;

class OrderRequestDeserializerTest {

    private final ObjectMapper mapper;

    OrderRequestDeserializerTest() {
        SimpleModule module = new SimpleModule();
        module.addDeserializer(
            OrderRequest.class,
            new OrderRequestDeserializer()
        );

        mapper = JsonMapper.builder()
            .addModule(module)
            .build();
    }

    @Test
    void readsExpectedTokenTypes() throws Exception {
        String json = """
            {
              "quantity": 2,
              "tags": ["java", "jackson"],
              "orderId": "ORD-100"
            }
            """;

        OrderRequest request = mapper.readValue(json, OrderRequest.class);

        assertEquals("ORD-100", request.orderId());
        assertEquals(2, request.quantity());
        assertEquals(List.of("java", "jackson"), request.tags());
    }

    @Test
    void rejectsStringForIntegerField() {
        String json = """
            {
              "orderId": "ORD-100",
              "quantity": "2"
            }
            """;

        assertThrows(
            JsonProcessingException.class,
            () -> mapper.readValue(json, OrderRequest.class)
        );
    }

    @Test
    void rejectsFloatingPointTokenForIntegerField() {
        String json = """
            {
              "orderId": "ORD-100",
              "quantity": 2.0
            }
            """;

        assertThrows(
            JsonProcessingException.class,
            () -> mapper.readValue(json, OrderRequest.class)
        );
    }

    @Test
    void rejectsNonStringArrayElement() {
        String json = """
            {
              "orderId": "ORD-100",
              "quantity": 2,
              "tags": ["java", 10]
            }
            """;

        assertThrows(
            JsonProcessingException.class,
            () -> mapper.readValue(json, OrderRequest.class)
        );
    }
}
~~~

Các import cho List, OrderRequest và những kiểu trong deserializer cần được thêm trong project thực tế. Test trên kiểm tra token type, không chỉ kiểm tra giá trị cuối cùng.

Nên bổ sung test cho:

- Root là array hoặc scalar thay vì object.
- Field bắt buộc bị thiếu.
- Explicit null.
- Field không biết.
- Duplicate field.
- Integer vượt phạm vi.
- Array hoặc object lồng nhau bị cắt dở.
- Một root value thứ hai sau object hợp lệ.

Nếu dự án có chính sách cho phép null hoặc unknown fields, test phải phản ánh đúng chính sách đó.

## 19. Khi nào nên dùng JsonParser thay vì readValue hoặc readTree?

| Cách đọc | Phù hợp khi |
|---|---|
| readValue() vào DTO | Schema ổn định, kiểu Java rõ ràng và coercion mặc định đáp ứng hợp đồng. |
| readTree() thành JsonNode | Cần kiểm tra hoặc sửa cấu trúc linh hoạt, nhưng chấp nhận giữ tree trong bộ nhớ. |
| JsonParser token-by-token | Cần kiểm tra token chính xác, xử lý payload lớn hoặc đọc tuần tự. |
| Custom JsonDeserializer | Muốn token validation tùy biến nhưng vẫn tích hợp với ObjectMapper và DTO. |

JsonParser cho quyền kiểm soát cao nhưng code dài và dễ sai nếu quản lý vị trí token không chặt. Với dữ liệu thông thường, hãy ưu tiên databinding và các feature/annotation phù hợp. Khi cần từ chối một dạng token cụ thể hoặc xử lý schema phức tạp, custom deserializer là nơi hợp lý để tập trung quy tắc.

Tree model nằm giữa hai hướng: dễ thao tác hơn streaming nhưng giữ toàn bộ cây trong bộ nhớ. Nếu payload rất lớn, streaming thường tiết kiệm bộ nhớ hơn.

## 20. Quy trình viết bộ đọc token an toàn

Khi triển khai parser hoặc custom deserializer, hãy đi theo trình tự:

1. Xác định root phải là object, array hay scalar.
2. Kiểm tra currentToken() trước khi tiêu thụ token.
3. Với object, đọc FIELD_NAME rồi mới đọc token giá trị.
4. Kiểm tra JsonToken trước khi gọi getter lấy giá trị.
5. Phân biệt VALUE_NULL, field bị thiếu và token sai kiểu.
6. Kiểm tra phạm vi số trước khi chuyển sang primitive.
7. Dùng skipChildren() cho subtree không cần xử lý.
8. Theo dõi field đã thấy nếu cần phát hiện missing hoặc duplicate.
9. Đọc đến END_OBJECT/END_ARRAY của root.
10. Dùng FAIL_ON_TRAILING_TOKENS nếu chỉ cho phép một root value.
11. Để lỗi EOF và I/O được xử lý ở tầng adapter phù hợp.
12. Chỉ tạo hoặc commit kết quả nghiệp vụ sau khi toàn bộ giá trị đã đọc hoàn chỉnh.

## Kết luận

JsonParser cung cấp cách đọc JSON theo token và cho phép kiểm tra loại dữ liệu trước khi chuyển thành giá trị Java. Bằng cách xác nhận START_OBJECT, FIELD_NAME, VALUE_STRING, VALUE_NUMBER_INT, START_ARRAY và các token tương ứng, ứng dụng có thể thực thi hợp đồng input chặt chẽ và tránh coercion ngoài ý muốn.

Hãy dùng JsonParser trực tiếp khi cần streaming hoặc kiểm soát token ở mức thấp; dùng custom JsonDeserializer khi muốn đóng gói quy tắc đó trong ObjectMapper. Quản lý vị trí parser, phân biệt missing/null/sai kiểu, bỏ qua subtree đúng cách và đọc hết root sẽ giúp bộ đọc dễ dự đoán. Với DTO thông thường, databinding tiêu chuẩn vẫn là lựa chọn đơn giản hơn; chỉ chuyển sang token-level validation khi yêu cầu của hợp đồng thực sự cần nó.

