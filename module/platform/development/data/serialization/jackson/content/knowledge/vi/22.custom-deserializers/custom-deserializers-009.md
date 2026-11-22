# Báo lỗi theo ngữ cảnh thay vì âm thầm dùng giá trị mặc định

Custom deserializer không chỉ chuyển JSON thành object Java. Nó còn quyết định dữ liệu đầu vào nào được chấp nhận và cách báo lỗi khi dữ liệu không đáp ứng hợp đồng.

Một lỗi thiết kế thường gặp là deserializer âm thầm thay dữ liệu sai bằng giá trị mặc định: field số không đọc được thì gán 0, field thiếu thì tự điền chuỗi rỗng, enum lạ thì chọn trạng thái đầu tiên, hoặc bắt exception rồi tiếp tục. Cách làm này khiến quá trình đọc có vẻ thành công nhưng object tạo ra không còn phản ánh dữ liệu client đã gửi. Lỗi thật có thể chỉ xuất hiện ở một bước nghiệp vụ xa hơn, khiến việc điều tra khó hơn.

Một deserializer tốt cần báo lỗi **đúng nơi, đúng trường và đúng nguyên nhân**. Jackson cung cấp JsonMappingException, JsonParseException, JsonLocation, DeserializationContext và các API hỗ trợ tạo lỗi theo kiểu đích. Bài học này tập trung vào cách dùng các cơ chế đó để từ chối dữ liệu sai một cách có ngữ cảnh, đồng thời phân biệt rõ property bị thiếu, null tường minh, sai kiểu và giá trị ngoài miền hợp lệ.

## 1. Vì sao không nên âm thầm dùng giá trị mặc định?

Giả sử ứng dụng nhận một sản phẩm:

~~~json
{
  "sku": "KB-01",
  "quantity": "many",
  "unitPrice": 250000
}
~~~

Class Java mong đợi quantity là số nguyên dương. Nếu custom deserializer bắt lỗi chuyển đổi rồi gán 0, object có thể được tạo thành công:

~~~java
int quantity = 0;

try {
    quantity = parser.getIntValue();
} catch (Exception ignored) {
    // Tiếp tục với giá trị mặc định.
}
~~~

Cách xử lý này che giấu lỗi đầu vào. Hệ thống có thể lưu sản phẩm với quantity bằng 0, tính sai tổng tiền hoặc từ chối đơn hàng ở một bước khác mà không chỉ ra nguyên nhân ban đầu là JSON gửi chuỗi "many".

Các rủi ro chính:

- **Mất dữ liệu đầu vào**: giá trị client gửi bị thay bằng một giá trị khác.
- **Lỗi bị trì hoãn**: exception xuất hiện ở service, database hoặc nghiệp vụ thay vì ngay tại ranh giới JSON.
- **Khó điều tra**: log không chỉ ra property nào sai và vì sao.
- **Che giấu lỗi tích hợp**: client gửi sai schema nhưng vẫn nhận response thành công.
- **Dữ liệu không nhất quán**: các request sai khác nhau có thể bị quy về cùng một giá trị mặc định.

Nguyên tắc phù hợp là: nếu giá trị là bắt buộc hoặc sai định dạng, hãy báo lỗi ngay khi deserializer nhận diện được vấn đề. Chỉ dùng giá trị mặc định khi hợp đồng dữ liệu quy định rõ property đó là tùy chọn và có default cụ thể.

## 2. Phân biệt các loại lỗi khi đọc JSON

Không phải mọi vấn đề đều cùng một loại. Phân biệt đúng giúp chọn exception và thông báo phù hợp.

| Trường hợp | Ví dụ | Loại xử lý |
|---|---|---|
| JSON sai cú pháp | {"sku": } | Parser báo lỗi cú pháp |
| Sai cấu trúc so với kiểu đích | Gửi array trong khi cần object | Lỗi mapping/token type |
| Property bắt buộc bị thiếu | Không có sku | Lỗi hợp đồng dữ liệu |
| Property có null không được phép | "sku": null | Lỗi null policy |
| Sai kiểu dữ liệu | "quantity": "many" | Lỗi mapping/type |
| Giá trị đúng kiểu nhưng ngoài miền hợp lệ | "quantity": -2 | Lỗi constraint/validation |
| Property không được hỗ trợ | "unknownField": 1 | Chính sách unknown property |
| Nguồn đọc bị ngắt | Socket đóng giữa document | Lỗi I/O hoặc EOF |

Có thể chia trách nhiệm thành ba lớp:

1. **Parser** kiểm tra cú pháp JSON và tạo token.
2. **Deserializer/data binding** kiểm tra JSON có thể ánh xạ vào kiểu Java và hợp đồng của kiểu đó hay không.
3. **Validation/nghiệp vụ** kiểm tra object đã tạo có đáp ứng constraint và quy tắc của ứng dụng hay không.

Custom deserializer phù hợp với lỗi về hình dạng, kiểu biểu diễn và quy tắc chuyển đổi của một kiểu cụ thể. Những quy tắc phụ thuộc database, quyền hoặc trạng thái hệ thống nên được kiểm tra ở service/domain layer.

## 3. Các exception Jackson thường dùng

### 3.1. JsonProcessingException

JsonProcessingException là lớp cha trong hệ exception xử lý JSON. Nó cung cấp thông tin như thông điệp gốc và vị trí lỗi trong nguồn.

~~~java
try {
    Product product = mapper.readValue(json, Product.class);
} catch (JsonProcessingException e) {
    System.err.println(e.getOriginalMessage());

    JsonLocation location = e.getLocation();
    if (location != null) {
        System.err.println(
                "line=" + location.getLineNr()
                        + ", column=" + location.getColumnNr()
        );
    }
}
~~~

Không nên bắt JsonProcessingException rồi trả về object rỗng hoặc object mặc định. Nếu không thể ánh xạ dữ liệu, hãy giữ nguyên lỗi hoặc chuyển nó thành lỗi ứng dụng có nguyên nhân gốc.

### 3.2. JsonParseException

JsonParseException thường xuất hiện khi cú pháp JSON không hợp lệ, ví dụ thiếu dấu phân cách, string chưa đóng hoặc escape sequence sai.

~~~json
{
  "sku": "KB-01",
  "quantity": ,
  "unitPrice": 250000
}
~~~

Custom deserializer thường không cần tự tạo JsonParseException cho mọi lỗi nghiệp vụ. Đây là loại lỗi parser nhận diện khi token stream không tuân theo cú pháp JSON.

### 3.3. JsonMappingException

JsonMappingException phù hợp với lỗi ánh xạ JSON vào kiểu Java: sai kiểu, thiếu dữ liệu theo hợp đồng của model, creator không thể tạo object hoặc giá trị không thể chuyển đổi.

Có thể tạo exception gắn với parser hiện tại:

~~~java
throw JsonMappingException.from(
        parser,
        "Property 'quantity' must be a positive integer"
);
~~~

from(parser, message) gắn thông tin vị trí hiện tại của parser vào exception nếu có. Nhờ vậy, log có thể chỉ ra dòng/cột nơi dữ liệu gây lỗi được đọc.

Khi viết custom deserializer, JsonMappingException thường là lựa chọn rõ ràng cho lỗi dữ liệu không phù hợp với kiểu đích.

## 4. Tạo lỗi qua DeserializationContext

DeserializationContext cung cấp các tiện ích để báo lỗi trong đúng ngữ cảnh data binding. Hai API đáng chú ý:

- handleUnexpectedToken(...): xử lý trường hợp token hiện tại không phải kiểu mà deserializer mong đợi.
- reportInputMismatch(...): báo dữ liệu đầu vào không đáp ứng điều kiện mong đợi cho kiểu đích.

Ví dụ kiểm tra root token:

~~~java
@Override
public Product deserialize(
        JsonParser parser,
        DeserializationContext context
) throws IOException {

    if (!parser.isExpectedStartObjectToken()) {
        return (Product) context.handleUnexpectedToken(
                Product.class,
                parser
        );
    }

    // Đọc các field tiếp theo.
}
~~~

handleUnexpectedToken() để Jackson tạo lỗi theo kiểu đích và token hiện tại. API này cũng có thể phối hợp với DeserializationProblemHandler nếu ứng dụng đăng ký handler xử lý tình huống bất thường.

Để báo một điều kiện cụ thể:

~~~java
return context.reportInputMismatch(
        Product.class,
        "Property '%s' is required",
        "sku"
);
~~~

reportInputMismatch() thường ném JsonMappingException; kiểu trả về generic cho phép viết trực tiếp trong câu lệnh return. Nếu chỉ muốn code dễ đọc và không cần tận dụng problem handler, có thể dùng JsonMappingException.from(parser, message).

Không nên tạo exception chung chung như RuntimeException("Invalid data") nếu có thể dùng exception Jackson mang location và mapping context.
## 5. Viết custom deserializer không âm thầm thay dữ liệu

Giả sử class:

~~~java
public class Product {
    private String sku;
    private int quantity;
    private BigDecimal unitPrice;

    public Product() {
    }

    public Product(String sku, int quantity, BigDecimal unitPrice) {
        this.sku = sku;
        this.quantity = quantity;
        this.unitPrice = unitPrice;
    }

    public String getSku() {
        return sku;
    }

    public int getQuantity() {
        return quantity;
    }

    public BigDecimal getUnitPrice() {
        return unitPrice;
    }
}
~~~

Hợp đồng đầu vào:
- sku là string bắt buộc, không rỗng.
- quantity là integer bắt buộc và phải lớn hơn 0.
- unitPrice là JSON number bắt buộc và không âm.
- Unknown property bị từ chối để phát hiện lỗi client.

Deserializer có thể đọc token theo thứ tự xuất hiện và giữ trạng thái riêng cho từng field:

~~~java
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JsonMappingException;
import com.fasterxml.jackson.databind.deser.std.StdDeserializer;

import java.io.IOException;
import java.math.BigDecimal;
import java.math.BigInteger;
import java.util.HashSet;
import java.util.Set;

public class ProductDeserializer extends StdDeserializer<Product> {

    public ProductDeserializer() {
        super(Product.class);
    }

    @Override
    public Product deserialize(
            JsonParser parser,
            DeserializationContext context
    ) throws IOException {

        if (!parser.isExpectedStartObjectToken()) {
            return (Product) context.handleUnexpectedToken(
                    Product.class,
                    parser
            );
        }

        String sku = null;
        Integer quantity = null;
        BigDecimal unitPrice = null;
        Set<String> seenFields = new HashSet<>();

        JsonToken token;

        while ((token = parser.nextToken()) != JsonToken.END_OBJECT) {
            if (token == null) {
                throw JsonMappingException.from(
                        parser,
                        "Unexpected end of input while reading Product"
                );
            }

            if (token != JsonToken.FIELD_NAME) {
                throw JsonMappingException.from(
                        parser,
                        "Expected a property name in Product object"
                );
            }

            String fieldName = parser.currentName();

            if (!seenFields.add(fieldName)) {
                throw JsonMappingException.from(
                        parser,
                        "Duplicate property '" + fieldName + "'"
                );
            }

            token = parser.nextToken();

            if (token == null) {
                throw JsonMappingException.from(
                        parser,
                        "Missing value for property '" + fieldName + "'"
                );
            }

            switch (fieldName) {
                case "sku" -> {
                    if (token == JsonToken.VALUE_NULL) {
                        throw JsonMappingException.from(
                                parser,
                                "Property 'sku' must not be null"
                        );
                    }
                    if (token != JsonToken.VALUE_STRING) {
                        throw JsonMappingException.from(
                                parser,
                                "Property 'sku' must be a JSON string"
                        );
                    }

                    sku = parser.getText();

                    if (sku.isBlank()) {
                        throw JsonMappingException.from(
                                parser,
                                "Property 'sku' must not be blank"
                        );
                    }
                }

                case "quantity" -> {
                    if (token == JsonToken.VALUE_NULL) {
                        throw JsonMappingException.from(
                                parser,
                                "Property 'quantity' must not be null"
                        );
                    }
                    if (token != JsonToken.VALUE_NUMBER_INT) {
                        throw JsonMappingException.from(
                                parser,
                                "Property 'quantity' must be an integer"
                        );
                    }

                    BigInteger value = parser.getBigIntegerValue();

                    if (value.signum() <= 0) {
                        throw JsonMappingException.from(
                                parser,
                                "Property 'quantity' must be greater than zero"
                        );
                    }

                    try {
                        quantity = value.intValueExact();
                    } catch (ArithmeticException e) {
                        throw JsonMappingException.from(
                                parser,
                                "Property 'quantity' is outside the supported integer range",
                                e
                        );
                    }
                }

                case "unitPrice" -> {
                    if (token == JsonToken.VALUE_NULL) {
                        throw JsonMappingException.from(
                                parser,
                                "Property 'unitPrice' must not be null"
                        );
                    }
                    if (token != JsonToken.VALUE_NUMBER_INT
                            && token != JsonToken.VALUE_NUMBER_FLOAT) {
                        throw JsonMappingException.from(
                                parser,
                                "Property 'unitPrice' must be a JSON number"
                        );
                    }

                    unitPrice = parser.getDecimalValue();

                    if (unitPrice.signum() < 0) {
                        throw JsonMappingException.from(
                                parser,
                                "Property 'unitPrice' must not be negative"
                        );
                    }
                }

                default -> throw JsonMappingException.from(
                        parser,
                        "Unknown Product property '" + fieldName + "'"
                );
            }
        }

        if (sku == null) {
            throw JsonMappingException.from(
                    parser,
                    "Required property 'sku' is missing"
            );
        }
        if (quantity == null) {
            throw JsonMappingException.from(
                    parser,
                    "Required property 'quantity' is missing"
            );
        }
        if (unitPrice == null) {
            throw JsonMappingException.from(
                    parser,
                    "Required property 'unitPrice' is missing"
            );
        }

        return new Product(sku, quantity, unitPrice);
    }
}
~~~

Ví dụ trên minh họa các điểm quan trọng:
- Kiểm tra root token trước khi đọc field.
- Dùng wrapper Integer và BigDecimal trong biến tạm để phân biệt property chưa xuất hiện với giá trị mặc định.
- Từ chối null tường minh nếu hợp đồng không cho phép.
- Kiểm tra token type trước khi gọi API lấy giá trị.
- Kiểm tra miền hợp lệ sau khi chuyển đổi.
- Phát hiện property trùng và property không được hỗ trợ theo chính sách strict.
- Chỉ tạo Product sau khi đã đọc đủ các field bắt buộc.

Trong code thực tế, có thể dùng context.reportInputMismatch() thay cho một số lệnh JsonMappingException.from() để tích hợp với problem handler. Điều quan trọng là lỗi phải được phát ra thay vì biến dữ liệu sai thành một object có giá trị giả định.

## 6. Missing, null và giá trị mặc định phải được xử lý riêng

Đối với một property, ít nhất cần phân biệt ba trạng thái:

~~~json
{}
~~~

~~~json
{"quantity": null}
~~~

~~~json
{"quantity": 0}
~~~

Ý nghĩa:
- Không có khóa quantity: client không gửi property.
- Có khóa quantity với null: client gửi null tường minh.
- Có quantity bằng 0: client gửi một số nguyên có giá trị 0.

Nếu dùng primitive int và khởi tạo biến tạm bằng 0, hai trường hợp thiếu và gửi 0 dễ bị nhập làm một. Dùng wrapper Integer quantity = null trong lúc đọc giúp nhận diện missing; kiểm tra token VALUE_NULL giúp nhận diện explicit null; token số cho biết client gửi một giá trị thực.

### 6.1. Khi property bắt buộc

Nếu quantity bắt buộc:
- Missing: báo "Required property 'quantity' is missing".
- Null: báo "Property 'quantity' must not be null".
- Số 0 hoặc số âm: báo vi phạm miền hợp lệ.
- String hoặc object: báo sai kiểu JSON.

Thông báo riêng giúp client biết cần sửa điều gì.

### 6.2. Khi property tùy chọn có default được quy định

Không phải mọi giá trị mặc định đều sai. Ví dụ hợp đồng quy định currency mặc định là VND nếu property bị thiếu:

~~~java
String currency = "VND";
boolean currencyProvided = false;
~~~

Khi gặp field currency:
- Nếu token là string hợp lệ, gán giá trị và đánh dấu đã gửi.
- Nếu token là null, có thể từ chối hoặc xử lý theo hợp đồng.
- Nếu field không xuất hiện, giữ default VND.

Điều quan trọng là default phải được quy định và áp dụng có chủ đích. Không dùng default để che giấu sai kiểu, dữ liệu ngoài miền hoặc lỗi parser.

### 6.3. Default khác với fallback khi parse thất bại

Hợp lệ:

~~~java
// Contract quy định currency có default nếu property bị thiếu.
String currency = "VND";
~~~

Không hợp lệ:

~~~java
// Không được nuốt lỗi và gán số lượng giả định.
int quantity = 1;

try {
    quantity = parser.getIntValue();
} catch (Exception ignored) {
    // Dữ liệu sai bị che giấu.
}
~~~

Nếu parse thất bại, hãy báo lỗi. Nếu property vắng mặt và hợp đồng có default, chỉ dùng default cho đúng trường hợp vắng mặt đó.

## 7. Kiểm tra kiểu trước khi chuyển đổi

Các method tiện ích như getValueAsInt(), asInt() hoặc asText() có thể trả về giá trị mặc định khi token không đúng kiểu hoặc không chuyển đổi được theo quy tắc của API. Điều này hữu ích trong một số trường hợp linh hoạt, nhưng không phù hợp nếu hợp đồng yêu cầu từ chối dữ liệu sai.

Ví dụ, với field integer:

~~~java
if (parser.currentToken() != JsonToken.VALUE_NUMBER_INT) {
    throw JsonMappingException.from(
            parser,
            "Property 'quantity' must be an integer"
    );
}

int quantity = parser.getIntValue();
~~~

Nếu cần kiểm tra range lớn hơn kiểu đích, đọc thành BigInteger rồi kiểm tra giới hạn trước khi chuyển:

~~~java
BigInteger value = parser.getBigIntegerValue();

if (value.compareTo(BigInteger.ONE) < 0) {
    throw JsonMappingException.from(
            parser,
            "Property 'quantity' must be at least 1"
    );
}

try {
    int quantity = value.intValueExact();
} catch (ArithmeticException e) {
    throw JsonMappingException.from(
            parser,
            "Property 'quantity' exceeds the supported range",
            e
    );
}
~~~

Với tiền hoặc số thập phân cần độ chính xác, dùng BigDecimal và kiểm tra sign/scale theo hợp đồng thay vì chuyển qua double.
## 8. Báo lỗi theo property path

Khi custom deserializer được gọi cho một property nằm sâu trong object graph, lỗi nên cho biết cả đường dẫn từ root đến field gây lỗi.

Ví dụ JSON:

~~~json
{
  "order": {
    "product": {
      "sku": "KB-01",
      "quantity": "many"
    }
  }
}
~~~

Lỗi có thể cần chỉ ra order, product và quantity.

JsonMappingException cung cấp:
- getPath(): danh sách thành phần đường dẫn.
- getPathReference(): chuỗi mô tả đường dẫn.
- getLocation(): vị trí trong JSON input.
- getOriginalMessage(): thông điệp gốc.

Ví dụ log:

~~~java
catch (JsonMappingException e) {
    System.err.println("Reason: " + e.getOriginalMessage());
    System.err.println("Path: " + e.getPathReference());

    JsonLocation location = e.getLocation();
    if (location != null) {
        System.err.println(
                "Line " + location.getLineNr()
                        + ", column " + location.getColumnNr()
        );
    }

    throw e;
}
~~~

Path reference phục vụ chẩn đoán; không nên phụ thuộc vào format chuỗi cụ thể để xử lý nghiệp vụ.

### 8.1. Bổ sung path khi tự gọi logic lồng nhau

Nếu custom deserializer tự gọi một hàm đọc object con hoặc tự chuyển đổi field, có thể bổ sung path bằng JsonMappingException.wrapWithPath():

~~~java
try {
    details = readDetails(parser, context);
} catch (JsonMappingException e) {
    throw JsonMappingException.wrapWithPath(
            e,
            Product.class,
            "details"
    );
}
~~~

API này bọc exception và thêm thông tin về property/đối tượng chứa lỗi. Có overload nhận object hoặc class làm tham chiếu. Dùng nó khi ứng dụng tự điều phối việc đọc lồng nhau và Jackson không tự bổ sung path cho đoạn code đó.

Không nên bắt exception rồi chỉ ném một exception mới không giữ cause/path, vì sẽ làm mất vị trí và thông tin chẩn đoán ban đầu.

### 8.2. Path trong collection

Khi lỗi xảy ra ở phần tử thứ ba của items, mapping path có thể chứa index 2 cùng property items. Điều này giúp phân biệt lỗi ở bản ghi nào trong array.

~~~json
{
  "items": [
    {"sku": "A", "quantity": 1},
    {"sku": "B", "quantity": 2},
    {"sku": "C", "quantity": "many"}
  ]
}
~~~

Nếu Jackson đang ánh xạ list bằng cơ chế chuẩn, nó có thể thêm index vào path. Nếu custom code tự lặp array, cần giữ index hiện tại và bổ sung path khi bọc lỗi để log không chỉ ghi chung chung "invalid item".

## 9. Báo lỗi đúng vị trí parser

JsonMappingException.from(parser, message) tạo mapping exception gắn với parser hiện tại. Vì vậy, nên phát hiện lỗi ngay khi đang ở token liên quan.

Ví dụ:

~~~java
if (token != JsonToken.VALUE_STRING) {
    throw JsonMappingException.from(
            parser,
            "Property 'sku' must be a JSON string"
    );
}
~~~

Lỗi được tạo khi parser đang đứng tại value của sku, nên location thường gần vị trí đầu vào gây lỗi.

Nếu đọc toàn bộ object thành JsonNode trước rồi mới kiểm tra, parser có thể đã ở cuối object khi phát hiện field sai. Khi đó location không còn sát token ban đầu. Có thể vẫn báo đúng property bằng message/path, nhưng nếu cần vị trí token chính xác, hãy kiểm tra khi parser đang ở field value hoặc lưu lại JsonLocation tương ứng.

~~~java
JsonLocation valueLocation = parser.currentTokenLocation();
~~~

Có thể lưu location này trong biến tạm cùng với tên field và dùng khi tạo lỗi sau đó. Không nên giả định location của parser sau readTree() vẫn là vị trí của từng field.

## 10. Unknown property: bỏ qua hay từ chối?

Khi viết custom deserializer, ứng dụng phải chọn cách xử lý field không biết.

### 10.1. Strict mode: từ chối field lạ

~~~java
default -> throw JsonMappingException.from(
        parser,
        "Unknown Product property '" + fieldName + "'"
);
~~~

Phù hợp khi:
- Schema cần chặt chẽ.
- Field lạ thường chỉ ra lỗi đánh máy.
- Client và server cần phát hiện sai hợp đồng sớm.
- Việc bỏ qua field có thể làm mất ý nghĩa nghiệp vụ.

### 10.2. Forward-compatible mode: bỏ qua field lạ

~~~java
default -> parser.skipChildren();
~~~

Phù hợp khi:
- API cần tương thích với field mới từ producer.
- Consumer chỉ quan tâm một tập field nhỏ.
- Hợp đồng quy định rõ field chưa biết được bỏ qua.

Nếu token hiện tại là object hoặc array, skipChildren() bỏ qua toàn bộ nội dung lồng nhau. Nếu là scalar, parser đã ở value đó và vòng lặp tiếp tục sang token sau.

Không nên bỏ qua unknown field chỉ vì việc triển khai dễ hơn. Hãy quyết định dựa trên chính sách tương thích của API. Nếu chọn bỏ qua, vẫn nên log hoặc đo lường field lạ khi điều đó hữu ích, nhưng tránh log giá trị nhạy cảm.

## 11. Enum và giá trị không biết

Enum là trường hợp dễ bị xử lý sai bằng fallback.

~~~java
public enum PaymentStatus {
    PENDING,
    PAID,
    CANCELLED
}
~~~

Nếu JSON gửi:

~~~json
{
  "status": "REFUNDED"
}
~~~

Không nên âm thầm chọn PENDING hoặc CANCELLED. Giá trị không biết có thể là lỗi chính tả, client và server lệch phiên bản hoặc một trạng thái mới chưa được hỗ trợ.

Một creator rõ ràng có thể từ chối:

~~~java
@JsonCreator
public static PaymentStatus fromJson(String value) {
    if (value == null) {
        throw new IllegalArgumentException("Payment status is required");
    }

    try {
        return PaymentStatus.valueOf(value);
    } catch (IllegalArgumentException e) {
        throw new IllegalArgumentException(
                "Unsupported payment status: " + value,
                e
        );
    }
}
~~~

Jackson có thể bọc lỗi creator thành lỗi mapping. Nếu hệ thống cần hỗ trợ giá trị unknown, hãy định nghĩa một hằng UNKNOWN và quy định rõ nghiệp vụ không được thực hiện hành động nhạy cảm dựa trên trạng thái đó.

Fallback có chủ đích khác với việc âm thầm dùng một trạng thái hợp lệ bất kỳ.

## 12. Khi nào dùng Bean Validation thay vì custom deserializer?

Không nên biến custom deserializer thành nơi chứa mọi quy tắc của ứng dụng.

Custom deserializer phù hợp với:
- JSON value phải có hình dạng đặc biệt.
- Một field cần chuyển đổi từ representation riêng.
- Property bắt buộc theo định dạng message.
- Kiểu dữ liệu không thể ánh xạ bằng deserializer chuẩn.
- Cần từ chối token sai ngay trong lúc parse/mapping.

Jakarta Bean Validation phù hợp với constraint trên object sau khi được tạo:
- @NotBlank
- @Size
- @Min, @Max
- @Positive
- @Email
- Constraint tùy chỉnh trên nhiều field.

Ví dụ DTO:

~~~java
public class ProductRequest {

    @NotBlank
    private String sku;

    @Min(1)
    private Integer quantity;

    @NotNull
    @DecimalMin("0.00")
    private BigDecimal unitPrice;

    // Getter và setter.
}
~~~

Jackson có thể ánh xạ JSON vào DTO. Sau đó ứng dụng gọi validator.validate(request) hoặc để framework như Spring kích hoạt validation.

Phân chia trách nhiệm:
- Jackson trả lời: JSON có thể chuyển thành kiểu Java này không?
- Bean Validation trả lời: object có đáp ứng các constraint dữ liệu không?
- Domain service trả lời: thao tác có hợp lệ trong trạng thái hệ thống hiện tại không?

Nếu custom deserializer kiểm tra một số điều kiện representation, vẫn nên giữ constraint nghiệp vụ ở đúng tầng để tránh logic bị trùng lặp.
## 13. Đăng ký custom deserializer

Có thể gắn trực tiếp trên class:

~~~java
@JsonDeserialize(using = ProductDeserializer.class)
public class Product {
    // Field và method.
}
~~~

Hoặc đăng ký qua module:

~~~java
SimpleModule module = new SimpleModule("product-module");

module.addDeserializer(
        Product.class,
        new ProductDeserializer()
);

ObjectMapper mapper = JsonMapper.builder()
        .addModule(module)
        .build();
~~~

Cách dùng module hữu ích khi class thuộc thư viện bên ngoài hoặc muốn tập trung cấu hình mapping. Chỉ nên có một chính sách deserializer rõ ràng cho cùng một kiểu để tránh khó đoán serializer nào được chọn.

Không nên tạo và cấu hình lại ObjectMapper cho mỗi request. Cấu hình module trước khi chia sẻ mapper, sau đó tái sử dụng mapper đã cấu hình.

## 14. Kiểm thử lỗi có ngữ cảnh

Test không chỉ xác nhận rằng có exception. Nó nên kiểm tra loại lỗi và thông điệp đủ rõ để phát hiện việc deserializer vô tình dùng default.

### 14.1. Property bắt buộc bị thiếu

~~~java
@Test
void rejectsMissingQuantity() {
    String json = """
            {
              "sku": "KB-01",
              "unitPrice": 250000
            }
            """;

    JsonMappingException exception = assertThrows(
            JsonMappingException.class,
            () -> mapper.readValue(json, Product.class)
    );

    assertTrue(
            exception.getOriginalMessage().contains("quantity")
    );
    assertTrue(
            exception.getOriginalMessage().contains("missing")
    );
}
~~~

### 14.2. Property null tường minh

~~~java
@Test
void rejectsNullQuantity() {
    String json = """
            {
              "sku": "KB-01",
              "quantity": null,
              "unitPrice": 250000
            }
            """;

    JsonMappingException exception = assertThrows(
            JsonMappingException.class,
            () -> mapper.readValue(json, Product.class)
    );

    assertTrue(
            exception.getOriginalMessage().contains("must not be null")
    );
}
~~~

### 14.3. Sai kiểu dữ liệu

~~~java
@Test
void rejectsStringForIntegerQuantity() {
    String json = """
            {
              "sku": "KB-01",
              "quantity": "many",
              "unitPrice": 250000
            }
            """;

    JsonMappingException exception = assertThrows(
            JsonMappingException.class,
            () -> mapper.readValue(json, Product.class)
    );

    assertTrue(
            exception.getOriginalMessage().contains("must be an integer")
    );
    assertNotNull(exception.getLocation());
}
~~~

### 14.4. Giá trị ngoài miền hợp lệ

~~~java
@Test
void rejectsNegativeQuantity() {
    String json = """
            {
              "sku": "KB-01",
              "quantity": -2,
              "unitPrice": 250000
            }
            """;

    JsonMappingException exception = assertThrows(
            JsonMappingException.class,
            () -> mapper.readValue(json, Product.class)
    );

    assertTrue(
            exception.getOriginalMessage().contains("greater than zero")
    );
}
~~~

### 14.5. Không biến dữ liệu sai thành object mặc định

~~~java
@Test
void doesNotSilentlyReplaceInvalidQuantityWithZero() {
    String json = """
            {
              "sku": "KB-01",
              "quantity": "many",
              "unitPrice": 250000
            }
            """;

    assertThrows(
            JsonMappingException.class,
            () -> mapper.readValue(json, Product.class)
    );
}
~~~

Ngoài ra nên kiểm thử:
- Sai root token.
- String rỗng cho field không cho phép rỗng.
- Number vượt phạm vi int.
- Giá âm.
- Unknown property theo chính sách đã chọn.
- Duplicate property nếu ứng dụng từ chối.
- JSON sai cú pháp và JSON bị cắt cụt.

## 15. Thông báo lỗi nên đủ cụ thể nhưng không làm lộ dữ liệu

Một thông báo tốt thường gồm:
- Tên property.
- Kiểu hoặc điều kiện mong đợi.
- Nguyên nhân không đáp ứng.
- Location và path nếu có.

Ví dụ tốt:

~~~text
Property 'quantity' must be an integer
Path: Product["quantity"]
Location: line 4, column 19
~~~

Ví dụ quá chung chung:

~~~text
Invalid input
~~~

Ví dụ không nên dùng:

~~~text
Invalid product: {"cardNumber":"4111111111111111", ...}
~~~

Không đưa toàn bộ payload vào exception message hoặc log nếu có dữ liệu nhạy cảm. Hãy log request ID, tên nguồn, property path, location và mã lỗi. Giá trị đầu vào chỉ nên được ghi khi đã có chính sách che/mã hóa phù hợp.

Nếu exception được trả về client, không gửi stack trace hoặc thông tin class nội bộ. Hãy ánh xạ lỗi Jackson thành response có mã lỗi ổn định và message phù hợp với API.

## 16. Các lỗi triển khai thường gặp

| Cách làm | Vấn đề | Cách xử lý |
|---|---|---|
| Bắt Exception rồi gán 0/null | Che giấu lỗi dữ liệu | Ném mapping exception có ngữ cảnh |
| Dùng primitive để phát hiện field bắt buộc | Missing và giá trị mặc định có thể bị nhập làm một | Dùng wrapper trong lúc đọc hoặc presence flag |
| Dùng asInt() mà không kiểm tra token | String/object có thể bị chuyển thành default | Kiểm tra JsonToken trước |
| Trả object rỗng khi gặp lỗi | Caller tưởng dữ liệu hợp lệ | Fail fast và giữ nguyên cause |
| Chỉ ghi Invalid JSON | Không biết field nào sai | Ghi field, expected type, location và path |
| Bỏ qua mọi unknown property | Có thể che lỗi đánh máy | Chọn strict hoặc forward-compatible theo contract |
| Chuyển mọi lỗi thành IllegalArgumentException | Mất thông tin Jackson location/path | Giữ JsonMappingException hoặc bọc có cause |
| Tự parse field lồng nhau nhưng không thêm path | Log thiếu ngữ cảnh | Dùng wrapWithPath() khi tự điều phối mapping |
| Dùng default cho cả missing lẫn null | Client không thể chủ động biểu đạt trạng thái | Xử lý hai trạng thái riêng |
| Log toàn bộ payload | Có thể lộ dữ liệu nhạy cảm | Log metadata và vị trí, che giá trị |

## 17. Quy trình xử lý lỗi trong custom deserializer

Khi viết deserializer cho một kiểu dữ liệu, có thể theo trình tự:

1. Kiểm tra root token có đúng cấu trúc mong đợi không.
2. Đọc từng property và giữ trạng thái presence riêng.
3. Với mỗi property, phân biệt missing, null và value.
4. Kiểm tra token type trước khi lấy giá trị.
5. Chuyển đổi bằng API phù hợp với miền giá trị.
6. Kiểm tra range/format nếu đó là điều kiện của representation.
7. Từ chối unknown hoặc duplicate field theo chính sách đã công bố.
8. Khi lỗi xảy ra, tạo JsonMappingException gắn với parser hiện tại hoặc dùng DeserializationContext.
9. Khi tự đọc object lồng nhau, bổ sung path bằng wrapWithPath() nếu cần.
10. Chỉ tạo object sau khi các dữ liệu bắt buộc đã được xác nhận.
11. Để Bean Validation/domain layer kiểm tra các constraint thuộc trách nhiệm của chúng.
12. Kiểm thử từng trường hợp sai, không chỉ happy path.

## 18. Những điểm cần nhớ

- Custom deserializer không nên âm thầm biến dữ liệu sai thành giá trị mặc định.
- Missing, explicit null, string rỗng, số 0 và false là các trạng thái khác nhau.
- Dùng wrapper hoặc biến trạng thái presence để phân biệt property bị thiếu với giá trị mặc định của primitive.
- Kiểm tra JsonToken trước khi gọi method chuyển đổi.
- Dùng JsonMappingException.from(parser, message) để tạo lỗi có location.
- Dùng DeserializationContext.handleUnexpectedToken() khi token không đúng kiểu mong đợi.
- Dùng reportInputMismatch() cho điều kiện input không đáp ứng contract.
- Dùng getPathReference() và getLocation() để ghi log có ngữ cảnh.
- Dùng wrapWithPath() khi tự điều phối mapping lồng nhau và cần thêm property/index path.
- Chỉ dùng default khi hợp đồng quy định rõ trường hợp áp dụng; không dùng default để che lỗi parse hoặc conversion.
- Phân chia rõ lỗi parse, lỗi mapping, validation và business rule.
- Không ghi toàn bộ payload nhạy cảm vào exception hoặc log.
- Kiểm thử missing, null, sai kiểu, ngoài range, unknown field và dữ liệu hợp lệ.

Báo lỗi theo ngữ cảnh giúp dữ liệu sai bị phát hiện ngay tại ranh giới JSON, trước khi đi sâu vào nghiệp vụ. Custom deserializer cần nêu rõ property nào sai, kiểu hoặc điều kiện nào được mong đợi và vị trí lỗi nếu có. Khi giữ nguyên nguyên nhân, location và mapping path, ứng dụng dễ chẩn đoán hơn và không vô tình tạo ra object có dữ liệu giả định.
