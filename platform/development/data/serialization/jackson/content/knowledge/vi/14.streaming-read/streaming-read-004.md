# Đọc tên trường và giá trị theo loại token

Trong Jackson Core, đọc JSON theo luồng có nghĩa là parser lần lượt cung cấp các token theo thứ tự xuất hiện trong văn bản. Thay vì tạo ngay một cây JSON hoặc một DTO hoàn chỉnh, ứng dụng có thể kiểm tra từng token, đọc tên trường, lấy giá trị theo đúng kiểu và quyết định cách xử lý tiếp theo.

Điểm cần nắm vững là **tên trường và giá trị của trường là hai token riêng biệt**. Trong một JSON object, Jackson phát ra token FIELD_NAME trước, sau đó mới phát ra token mô tả giá trị tương ứng như VALUE_STRING, VALUE_NUMBER_INT, VALUE_TRUE, START_OBJECT hoặc START_ARRAY. Cách đọc đúng phải dựa vào loại token hiện tại, không đoán kiểu chỉ từ tên trường hoặc gọi phương thức lấy giá trị tùy tiện.

## 1. Token là gì?

Token là đơn vị nhỏ mà JsonParser trả về khi duyệt JSON. Ví dụ:

~~~json
{
  "name": "Mai",
  "age": 25,
  "active": true
}
~~~

Luồng token có thể hình dung như sau:

~~~text
START_OBJECT
  FIELD_NAME       "name"
  VALUE_STRING     "Mai"
  FIELD_NAME       "age"
  VALUE_NUMBER_INT 25
  FIELD_NAME       "active"
  VALUE_TRUE       true
END_OBJECT
~~~

Token cho biết parser đang ở vị trí nào trong cấu trúc JSON và giá trị hiện tại thuộc dạng nào. Với object, tên trường được phát ra trước giá trị. Với array, parser phát ra token bắt đầu mảng, từng token phần tử và token kết thúc mảng.

Ứng dụng thường dùng JsonToken để phân nhánh:

- Nếu token là FIELD_NAME, đọc tên trường hiện tại.
- Nếu token là VALUE_STRING, đọc nội dung chuỗi.
- Nếu token là VALUE_NUMBER_INT hoặc VALUE_NUMBER_FLOAT, đọc giá trị số.
- Nếu token là VALUE_TRUE hoặc VALUE_FALSE, đọc boolean.
- Nếu token là VALUE_NULL, xử lý null.
- Nếu token là START_OBJECT hoặc START_ARRAY, xử lý cấu trúc lồng nhau.

## 2. JsonParser và JsonToken

JsonParser thuộc Jackson Core, chịu trách nhiệm đọc cú pháp JSON và phát ra token. JsonToken là enum mô tả loại token mà parser đang đứng tại.

Có thể tạo parser từ JsonFactory:

~~~java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;

JsonFactory factory = new JsonFactory();

try (JsonParser parser = factory.createParser(json)) {
    JsonToken token;
    while ((token = parser.nextToken()) != null) {
        System.out.println(token);
    }
}
~~~

Trong ứng dụng đã dùng ObjectMapper, có thể lấy JsonFactory từ mapper để dùng chung cấu hình nền tảng:

~~~java
JsonFactory factory = mapper.getFactory();
try (JsonParser parser = factory.createParser(json)) {
    // Đọc token
}
~~~

Phương thức nextToken() tiến parser đến token kế tiếp và trả về loại token đó. Khi hết nội dung, phương thức trả về null. Phương thức currentToken() trả về token hiện tại mà không tiến parser.

Một số token thường gặp:

| JsonToken | Ý nghĩa |
|---|---|
| START_OBJECT | Bắt đầu JSON object, ký tự { |
| END_OBJECT | Kết thúc JSON object, ký tự } |
| START_ARRAY | Bắt đầu JSON array, ký tự [ |
| END_ARRAY | Kết thúc JSON array, ký tự ] |
| FIELD_NAME | Tên một trường trong object |
| VALUE_STRING | Giá trị chuỗi |
| VALUE_NUMBER_INT | Giá trị số nguyên trong JSON |
| VALUE_NUMBER_FLOAT | Giá trị số có phần thập phân hoặc dạng số thực |
| VALUE_TRUE | Giá trị boolean true |
| VALUE_FALSE | Giá trị boolean false |
| VALUE_NULL | Giá trị null |
| VALUE_EMBEDDED_OBJECT | Giá trị object nhúng, thường gặp ở một số luồng hoặc định dạng mở rộng |
| NOT_AVAILABLE | Chưa có token sẵn, chủ yếu liên quan parser non-blocking |

Với JSON văn bản thông thường, các token quan trọng nhất là START_OBJECT, END_OBJECT, START_ARRAY, END_ARRAY, FIELD_NAME và các VALUE_*.

## 3. Phân biệt FIELD_NAME và token giá trị

Đây là nguyên tắc cốt lõi khi đọc object:

~~~json
{
  "city": "Hà Nội"
}
~~~

Parser không trả một token duy nhất chứa cả tên city và giá trị Hà Nội. Nó trả hai bước:

1. FIELD_NAME với nội dung tên trường là city.
2. VALUE_STRING với nội dung giá trị là Hà Nội.

Vì vậy, mẫu đọc phổ biến là:

~~~java
if (parser.nextToken() != JsonToken.START_OBJECT) {
    throw new IllegalStateException("Expected JSON object");
}

while (parser.nextToken() == JsonToken.FIELD_NAME) {
    String fieldName = parser.currentName();
    JsonToken valueToken = parser.nextToken();

    // Xử lý fieldName và valueToken
}
~~~

Sau khi nextToken() trả về FIELD_NAME, currentName() trả tên trường. Lần gọi nextToken() tiếp theo di chuyển đến token giá trị. Khi đã đọc xong giá trị, vòng lặp tiếp tục gọi nextToken() để đến FIELD_NAME kế tiếp hoặc END_OBJECT.

Không nên gọi nextToken() hai lần liên tiếp mà quên xử lý token ở giữa. Nếu bỏ qua token FIELD_NAME, ứng dụng sẽ mất tên trường cần thiết để diễn giải giá trị.

## 4. Đọc tên trường bằng currentName()

Khi parser đang ở token FIELD_NAME hoặc token giá trị thuộc một trường object, currentName() trả tên thuộc tính tương ứng trong ngữ cảnh object hiện tại.

Ví dụ:

~~~java
while (parser.nextToken() == JsonToken.FIELD_NAME) {
    String fieldName = parser.currentName();
    JsonToken valueToken = parser.nextToken();

    System.out.println("Field: " + fieldName);
    System.out.println("Value token: " + valueToken);
}
~~~

currentName() không tự tiến parser. Nó chỉ truy vấn tên trường gắn với vị trí hiện tại. Trong ngữ cảnh array, phần tử không có tên trường riêng; currentName() có thể phản ánh tên trường của object bao quanh array nếu có, vì vậy không nên dùng nó như tên của từng phần tử array.

Trong các phiên bản Jackson cũ có thể thấy getCurrentName(). API currentName() là cách gọi hiện đại; hãy dùng API phù hợp với phiên bản Jackson của dự án.

## 5. Đọc nội dung token bằng getText()

getText() trả về nội dung văn bản của token hiện tại. Kết quả phụ thuộc token:

| Token hiện tại | Giá trị getText() thường trả |
|---|---|
| FIELD_NAME | Tên trường |
| VALUE_STRING | Nội dung chuỗi đã được parser giải mã escape |
| VALUE_NUMBER_INT | Văn bản biểu diễn số nguyên |
| VALUE_NUMBER_FLOAT | Văn bản biểu diễn số thực |
| VALUE_TRUE | Chuỗi true |
| VALUE_FALSE | Chuỗi false |
| VALUE_NULL | Chuỗi null |

Ví dụ:

~~~java
String json = """
    {
      "name": "Mai",
      "score": 9.5
    }
    """;

try (JsonParser parser = factory.createParser(json)) {
    while (parser.nextToken() != null) {
        JsonToken token = parser.currentToken();

        if (token == JsonToken.FIELD_NAME) {
            System.out.println("Tên: " + parser.currentName());
        } else if (token == JsonToken.VALUE_STRING
                || token == JsonToken.VALUE_NUMBER_FLOAT) {
            System.out.println("Nội dung: " + parser.getText());
        }
    }
}
~~~

getText() hữu ích khi cần xem dạng văn bản của token. Tuy nhiên, với số, nếu ứng dụng cần một kiểu số Java cụ thể hoặc cần giữ độ chính xác, nên dùng các phương thức lấy số tương ứng thay vì tự parse chuỗi.

Với VALUE_STRING, getText() trả nội dung sau khi JSON escape được giải mã. Ví dụ JSON chứa chuỗi có escape newline thì giá trị Java có ký tự xuống dòng ở giữa hai phần văn bản.

## 6. Đọc chuỗi theo loại token

Nếu trường được kỳ vọng là chuỗi, nên kiểm tra token trước khi gọi getText():

~~~java
if (valueToken == JsonToken.VALUE_STRING) {
    String value = parser.getText();
} else if (valueToken == JsonToken.VALUE_NULL) {
    // Xử lý null
} else {
    throw new IllegalArgumentException("Expected a JSON string");
}
~~~

Cách làm này giúp hợp đồng dữ liệu rõ ràng: chuỗi phải được gửi bằng JSON string. Nếu ứng dụng muốn chấp nhận cả số hoặc boolean rồi chuyển thành chuỗi, có thể dùng API coercion như getValueAsString(), nhưng cần quyết định đó là yêu cầu thực sự của hợp đồng.

Ví dụ:

~~~java
String textValue = parser.getValueAsString();
~~~

getValueAsString() có thể chuyển một số scalar sang dạng chuỗi. Nó không tương đương với việc kiểm tra token VALUE_STRING. Nếu token là object hoặc array, phương thức này không biến toàn bộ cấu trúc thành JSON string.

Một overload cho phép chỉ định giá trị mặc định:

~~~java
String textValue = parser.getValueAsString("unknown");
~~~

Nếu token không thể chuyển thành chuỗi theo quy tắc của parser, giá trị mặc định có thể được trả về. Khi cần phân biệt rõ null, token sai loại và trường bị thiếu, hãy kiểm tra JsonToken trực tiếp.

## 7. Đọc số nguyên và số thực

JSON có hai nhóm token số chính:

- VALUE_NUMBER_INT: số nguyên trong văn bản JSON.
- VALUE_NUMBER_FLOAT: số có phần thập phân hoặc biểu diễn dạng số thực.

Parser cung cấp các phương thức lấy số:

| Phương thức | Kiểu Java |
|---|---|
| getIntValue() | int |
| getLongValue() | long |
| getBigIntegerValue() | BigInteger |
| getFloatValue() | float |
| getDoubleValue() | double |
| getDecimalValue() | BigDecimal |
| getNumberValue() | Number phù hợp với giá trị và parser |
| getNumberType() | Loại số mà parser đang sử dụng |

Ví dụ:

~~~java
if (valueToken == JsonToken.VALUE_NUMBER_INT) {
    int quantity = parser.getIntValue();
} else if (valueToken == JsonToken.VALUE_NUMBER_FLOAT) {
    BigDecimal amount = parser.getDecimalValue();
} else {
    throw new IllegalArgumentException("Expected a JSON number");
}
~~~

Nếu giá trị có thể vượt phạm vi int, dùng getLongValue() hoặc getBigIntegerValue() tùy hợp đồng. getIntValue() có thể phát sinh lỗi chuyển đổi nếu số nằm ngoài phạm vi int.

Đối với tiền hoặc số thập phân cần độ chính xác, getDecimalValue() thường phù hợp hơn getDoubleValue(). double dùng biểu diễn dấu phẩy động nhị phân nên không biểu diễn chính xác mọi số thập phân.

### Kiểm tra NumberType

getNumberType() cho biết parser đang biểu diễn giá trị số bằng kiểu nào:

~~~java
if (valueToken == JsonToken.VALUE_NUMBER_INT
        || valueToken == JsonToken.VALUE_NUMBER_FLOAT) {
    JsonParser.NumberType numberType = parser.getNumberType();
    Number number = parser.getNumberValue();
}
~~~

Các loại có thể gặp gồm INT, LONG, BIG_INTEGER, FLOAT, DOUBLE và BIG_DECIMAL tùy parser và cấu hình. Không nên giả định mọi số JSON đều trở thành Integer hoặc Double.

### Không dùng getValueAsInt khi cần kiểm tra nghiêm ngặt

getValueAsInt() và các overload getValueAsLong() có thể thực hiện coercion từ một số dạng scalar. Ví dụ, chuỗi số có thể được chuyển thành số nguyên theo quy tắc của parser. Overload có giá trị mặc định có thể trả fallback nếu không chuyển được.

~~~java
int value = parser.getValueAsInt(-1);
~~~

Đây là tiện ích cho dữ liệu linh hoạt, nhưng có thể che khuất khác biệt giữa trường bị thiếu, null và token sai loại. Nếu hợp đồng yêu cầu JSON number, hãy kiểm tra VALUE_NUMBER_INT trước khi gọi getIntValue().

## 8. Đọc Boolean và null

Boolean trong JSON có hai token riêng:

- VALUE_TRUE
- VALUE_FALSE

Null là VALUE_NULL và không phải boolean false.

~~~java
switch (valueToken) {
    case VALUE_TRUE -> {
        boolean enabled = true;
    }
    case VALUE_FALSE -> {
        boolean enabled = false;
    }
    case VALUE_NULL -> {
        // Không có giá trị
    }
    default -> throw new IllegalArgumentException(
        "Expected true, false or null"
    );
}
~~~

getBooleanValue() lấy giá trị boolean của token boolean. Nếu cần phân biệt null với false, phải kiểm tra token trước:

~~~java
Boolean enabled;

if (valueToken == JsonToken.VALUE_TRUE) {
    enabled = Boolean.TRUE;
} else if (valueToken == JsonToken.VALUE_FALSE) {
    enabled = Boolean.FALSE;
} else if (valueToken == JsonToken.VALUE_NULL) {
    enabled = null;
} else {
    throw new IllegalArgumentException("Expected boolean or null");
}
~~~

Không nên dùng getValueAsBoolean(false) nếu cần phân biệt token không hợp lệ với false. API có giá trị mặc định phù hợp khi muốn coercion có chủ đích, còn xử lý nghiêm ngặt nên dựa vào loại token.

## 9. Đọc một object và lấy giá trị theo tên trường

Ví dụ sau đọc một object có các trường name, age và active. Mỗi trường được kiểm tra loại token trước khi lấy giá trị:

~~~java
String json = """
    {
      "name": "Mai",
      "age": 25,
      "active": true
    }
    """;

String name = null;
Integer age = null;
Boolean active = null;

try (JsonParser parser = factory.createParser(json)) {
    if (parser.nextToken() != JsonToken.START_OBJECT) {
        throw new IllegalArgumentException("Expected an object");
    }

    JsonToken token;
    while ((token = parser.nextToken()) != JsonToken.END_OBJECT) {
        if (token == null) {
            throw new IllegalArgumentException("Unexpected end of JSON");
        }
        if (token != JsonToken.FIELD_NAME) {
            throw new IllegalArgumentException("Expected a field name");
        }

        String fieldName = parser.currentName();
        JsonToken valueToken = parser.nextToken();

        if (valueToken == null) {
            throw new IllegalArgumentException("Missing field value");
        }

        switch (fieldName) {
            case "name" -> {
                if (valueToken == JsonToken.VALUE_STRING) {
                    name = parser.getText();
                } else if (valueToken == JsonToken.VALUE_NULL) {
                    name = null;
                } else {
                    throw new IllegalArgumentException("name must be a string");
                }
            }
            case "age" -> {
                if (valueToken == JsonToken.VALUE_NUMBER_INT) {
                    age = parser.getIntValue();
                } else if (valueToken == JsonToken.VALUE_NULL) {
                    age = null;
                } else {
                    throw new IllegalArgumentException("age must be an integer");
                }
            }
            case "active" -> {
                if (valueToken == JsonToken.VALUE_TRUE) {
                    active = true;
                } else if (valueToken == JsonToken.VALUE_FALSE) {
                    active = false;
                } else if (valueToken == JsonToken.VALUE_NULL) {
                    active = null;
                } else {
                    throw new IllegalArgumentException("active must be boolean");
                }
            }
            default -> parser.skipChildren();
        }
    }
}
~~~

Mẫu này tách rõ bốn thao tác:

1. Đọc FIELD_NAME.
2. Lưu tên trường.
3. Tiến đến token giá trị.
4. Chọn phương thức đọc theo loại token và hợp đồng của trường.

Ví dụ cũng cho thấy trường chưa xuất hiện trong JSON sẽ giữ giá trị khởi tạo ban đầu của biến Java. Nếu cần bắt buộc trường phải có mặt, ứng dụng phải theo dõi việc đã đọc trường đó hay chưa và kiểm tra sau vòng lặp.

## 10. Đọc object lồng nhau

Một giá trị của field có thể là object khác:

~~~json
{
  "id": 10,
  "address": {
    "city": "Đà Nẵng",
    "country": "VN"
  }
}
~~~

Sau khi parser đọc FIELD_NAME address, lần nextToken() kế tiếp trả START_OBJECT. Ứng dụng cần đi sâu vào object con và đọc các field của nó cho đến END_OBJECT tương ứng.

~~~java
if ("address".equals(fieldName)
        && valueToken == JsonToken.START_OBJECT) {

    while (parser.nextToken() != JsonToken.END_OBJECT) {
        JsonToken childToken = parser.currentToken();
        if (childToken == null) {
            throw new IllegalArgumentException("Unexpected end in address");
        }
        if (childToken != JsonToken.FIELD_NAME) {
            throw new IllegalArgumentException("Expected address field");
        }

        String childName = parser.currentName();
        JsonToken childValueToken = parser.nextToken();

        if ("city".equals(childName)
                && childValueToken == JsonToken.VALUE_STRING) {
            city = parser.getText();
        } else if ("country".equals(childName)
                && childValueToken == JsonToken.VALUE_STRING) {
            country = parser.getText();
        } else {
            parser.skipChildren();
        }
    }
}
~~~

Ở đây vòng lặp bên trong tiêu thụ toàn bộ object address và kết thúc khi parser ở END_OBJECT của object con. Vòng lặp bên ngoài sau đó tiếp tục từ token kế tiếp sau object con.

Khi cấu trúc lồng nhau sâu hoặc có nhiều loại object, nên tách thành các phương thức đọc riêng như readAddress(parser), readCustomer(parser) để giữ code dễ hiểu. Mỗi phương thức cần quy định rõ parser phải đang đứng ở START_OBJECT khi được gọi và sẽ kết thúc ở END_OBJECT tương ứng.

## 11. Đọc array và từng phần tử

JSON array bắt đầu bằng START_ARRAY và kết thúc bằng END_ARRAY. Mỗi phần tử có thể là scalar, object hoặc một array khác.

Ví dụ:

~~~json
{
  "tags": ["java", "jackson", "json"]
}
~~~

Sau khi đọc tên tags, parser đến START_ARRAY. Có thể đọc từng phần tử:

~~~java
if ("tags".equals(fieldName)
        && valueToken == JsonToken.START_ARRAY) {

    List<String> tags = new ArrayList<>();

    JsonToken itemToken;
    while ((itemToken = parser.nextToken()) != JsonToken.END_ARRAY) {
        if (itemToken == null) {
            throw new IllegalArgumentException("Unexpected end of tags");
        }

        if (itemToken == JsonToken.VALUE_STRING) {
            tags.add(parser.getText());
        } else if (itemToken == JsonToken.VALUE_NULL) {
            tags.add(null);
        } else {
            throw new IllegalArgumentException("Tag must be a string");
        }
    }
}
~~~

Không có FIELD_NAME bên trong array trừ khi một phần tử của array là object. Parser chỉ trả token của từng phần tử theo thứ tự.

Với array object:

~~~json
{
  "items": [
    {"sku": "A01", "quantity": 2},
    {"sku": "B02", "quantity": 1}
  ]
}
~~~

Luồng token rút gọn:

~~~text
FIELD_NAME "items"
START_ARRAY
  START_OBJECT
    FIELD_NAME "sku"
    VALUE_STRING "A01"
    FIELD_NAME "quantity"
    VALUE_NUMBER_INT 2
  END_OBJECT
  START_OBJECT
    FIELD_NAME "sku"
    VALUE_STRING "B02"
    FIELD_NAME "quantity"
    VALUE_NUMBER_INT 1
  END_OBJECT
END_ARRAY
~~~

Mỗi START_OBJECT có thể được giao cho một phương thức đọc item. Phương thức đó đọc đến END_OBJECT tương ứng, sau đó vòng lặp array tiếp tục đến phần tử kế tiếp.

## 12. skipChildren() để bỏ qua cấu trúc không cần thiết

Khi parser đang ở START_OBJECT hoặc START_ARRAY, skipChildren() bỏ qua toàn bộ nội dung lồng nhau và dừng tại END_OBJECT hoặc END_ARRAY tương ứng.

Ví dụ:

~~~json
{
  "id": 10,
  "debug": {
    "trace": ["a", "b", "c"],
    "details": {
      "source": "internal"
    }
  },
  "name": "Mai"
}
~~~

Nếu ứng dụng không cần debug, có thể bỏ qua:

~~~java
if ("debug".equals(fieldName)) {
    parser.skipChildren();
}
~~~

Sau khi skipChildren() hoàn tất, parser đang ở token kết thúc cấu trúc con. Lần gọi nextToken() tiếp theo sẽ đi đến token tiếp theo trong object cha, ở ví dụ này là FIELD_NAME name.

skipChildren() hữu ích khi JSON có các nhánh lớn nhưng ứng dụng chỉ cần một số trường. Nó cũng giúp xử lý field chưa biết mà không cần tự duyệt từng cấp. Với token scalar, skipChildren() không bỏ thêm cấu trúc nào.

## 13. Đọc field theo cách tối ưu bằng nextFieldName()

JsonParser cung cấp nextFieldName() để tiến đến field kế tiếp và lấy tên trường nếu token mới là FIELD_NAME. Phương thức trả về null nếu token tiếp theo không phải field name hoặc đã hết nội dung object.

~~~java
if (parser.nextToken() != JsonToken.START_OBJECT) {
    throw new IllegalArgumentException("Expected object");
}

String fieldName;
while ((fieldName = parser.nextFieldName()) != null) {
    JsonToken valueToken = parser.nextToken();

    if ("name".equals(fieldName)
            && valueToken == JsonToken.VALUE_STRING) {
        name = parser.getText();
    } else {
        parser.skipChildren();
    }
}
~~~

nextFieldName() là cách viết gọn cho mẫu gọi nextToken() rồi kiểm tra FIELD_NAME. Một số parser có thể tối ưu việc so sánh tên trường, đặc biệt khi dùng overload nhận SerializableString.

Ví dụ:

~~~java
SerializedString expectedName = new SerializedString("name");

if (parser.nextFieldName(expectedName)) {
    JsonToken valueToken = parser.nextToken();
    // Đọc giá trị của field name
}
~~~

Overload nhận SerializableString hữu ích khi đọc một cấu trúc có tên trường đã biết trước và cần tối ưu. Với code thông thường, nextToken() và currentName() thường dễ đọc hơn.

Lưu ý: nextFieldName() trả null ở nhiều tình huống không phải field name. Nếu cần phân biệt END_OBJECT với EOF hoặc token khác, hãy kiểm tra currentToken() hoặc dùng vòng lặp nextToken() tường minh.

## 14. Các phương thức đọc nhanh nextTextValue(), nextIntValue() và nextBooleanValue()

Jackson có một số phương thức kết hợp việc tiến parser và lấy giá trị nếu token kế tiếp đúng loại:

| Phương thức | Hành vi |
|---|---|
| nextTextValue() | Tiến token; trả nội dung nếu token mới là VALUE_STRING |
| nextIntValue(defaultValue) | Tiến token; trả int nếu token mới phù hợp, nếu không trả default |
| nextLongValue(defaultValue) | Tương tự cho long |
| nextBooleanValue() | Tiến token; trả Boolean cho VALUE_TRUE/FALSE, nếu không có thể trả null |

Ví dụ:

~~~java
if (parser.nextToken() == JsonToken.FIELD_NAME
        && "name".equals(parser.currentName())) {
    String name = parser.nextTextValue();
}
~~~

nextTextValue() đã gọi nextToken() để đi đến giá trị tiếp theo. Không gọi nextToken() thêm lần nữa trước khi xử lý giá trị, nếu không parser sẽ bỏ qua token đó.

Các phương thức đọc nhanh có thể trả cùng một giá trị mặc định hoặc null cho nhiều tình huống: token sai loại, token null hoặc hết dữ liệu tùy phương thức. Nếu cần phân biệt chính xác các trường hợp, hãy dùng nextToken() và kiểm tra JsonToken trực tiếp.

## 15. Đọc theo tên field và kiểm tra loại token

Một lỗi thường gặp là chỉ kiểm tra tên trường rồi gọi phương thức lấy giá trị mà không xác nhận token. Ví dụ:

~~~java
if ("age".equals(parser.currentName())) {
    int age = parser.getIntValue();
}
~~~

Đoạn này chỉ an toàn nếu parser chắc chắn đang ở token số. Nếu giá trị thực tế là string, null hoặc object, lời gọi có thể thất bại hoặc không đáp ứng hợp đồng.

Nên kiểm tra cả tên và token:

~~~java
if (token == JsonToken.FIELD_NAME
        && "age".equals(parser.currentName())) {

    JsonToken valueToken = parser.nextToken();

    if (valueToken == JsonToken.VALUE_NUMBER_INT) {
        int age = parser.getIntValue();
    } else if (valueToken == JsonToken.VALUE_NULL) {
        // Chính sách null
    } else {
        throw new IllegalArgumentException("age must be an integer");
    }
}
~~~

Tên field xác định ý nghĩa nghiệp vụ; token xác định hình dạng dữ liệu thực tế. Cả hai cần được kiểm tra trước khi chuyển đổi.

## 16. Phân biệt getText(), getValueAsString() và getXxxValue()

Các phương thức này phục vụ mục đích khác nhau:

| Phương thức | Mục đích | Khi nên dùng |
|---|---|---|
| getText() | Lấy biểu diễn văn bản của token hiện tại | Đọc chuỗi, xem nội dung tên trường hoặc văn bản số |
| getValueAsString() | Lấy giá trị scalar dưới dạng String, có thể coercion | Khi hợp đồng cho phép chuyển một số scalar thành chuỗi |
| getIntValue() | Lấy giá trị số nguyên int | Khi token đã được xác nhận là số và phạm vi phù hợp |
| getDecimalValue() | Lấy số dưới dạng BigDecimal | Khi cần độ chính xác thập phân |
| getBooleanValue() | Lấy boolean từ token boolean | Khi đã xác nhận VALUE_TRUE/FALSE |
| getEmbeddedObject() | Lấy object nhúng | Với parser/format có hỗ trợ embedded object |

Không nên dùng getText() rồi tự parse mọi thứ nếu Jackson đã cung cấp phương thức typed accessor. Ngược lại, không nên dùng getValueAsXxx() để che giấu token sai loại khi hợp đồng cần nghiêm ngặt.

## 17. Đọc giá trị theo switch trên JsonToken

Khi xử lý một trường có thể chứa nhiều kiểu scalar, switch trên token giúp code rõ ràng:

~~~java
Object readScalar(JsonParser parser) throws IOException {
    JsonToken token = parser.currentToken();

    return switch (token) {
        case VALUE_STRING -> parser.getText();
        case VALUE_NUMBER_INT -> parser.getNumberValue();
        case VALUE_NUMBER_FLOAT -> parser.getDecimalValue();
        case VALUE_TRUE -> Boolean.TRUE;
        case VALUE_FALSE -> Boolean.FALSE;
        case VALUE_NULL -> null;
        default -> throw new IllegalArgumentException(
            "Expected a scalar value, got " + token
        );
    };
}
~~~

Phương thức này giả định parser đang đứng ở token giá trị, không phải FIELD_NAME hoặc token bắt đầu object/array. Với JSON number, cách lấy Number hoặc BigDecimal phụ thuộc chính sách độ chính xác của ứng dụng.

Nếu muốn hỗ trợ object và array, cần xử lý START_OBJECT và START_ARRAY bằng parser con hoặc một cơ chế tree/Databind; không thể lấy toàn bộ cấu trúc bằng getText().

## 18. Đọc dữ liệu theo cấu trúc và bỏ qua field chưa biết

Khi đọc JSON streaming, ứng dụng có thể chọn chỉ xử lý những field cần thiết. Các field khác được bỏ qua:

~~~java
while (parser.nextToken() == JsonToken.FIELD_NAME) {
    String fieldName = parser.currentName();
    JsonToken valueToken = parser.nextToken();

    switch (fieldName) {
        case "id" -> {
            if (valueToken == JsonToken.VALUE_NUMBER_INT) {
                id = parser.getLongValue();
            } else {
                throw new IllegalArgumentException("id must be an integer");
            }
        }
        case "name" -> {
            if (valueToken == JsonToken.VALUE_STRING) {
                name = parser.getText();
            } else {
                throw new IllegalArgumentException("name must be a string");
            }
        }
        default -> parser.skipChildren();
    }
}
~~~

skipChildren() giúp bỏ qua field chưa biết ngay cả khi giá trị của field là object hoặc array lồng nhau. Điều này hữu ích khi consumer cần tương thích với JSON có thêm trường mới.

Tuy nhiên, bỏ qua field chưa biết là quyết định về hợp đồng. Với dữ liệu cần kiểm tra nghiêm ngặt, ứng dụng có thể từ chối field lạ thay vì bỏ qua. Streaming API cho phép triển khai cả hai chính sách.

## 19. Đọc token trong array ở root

JSON root không nhất thiết phải là object. Một tài liệu có thể bắt đầu trực tiếp bằng array:

~~~json
[
  {"id": 1, "name": "Mai"},
  {"id": 2, "name": "An"}
]
~~~

Mẫu đọc:

~~~java
if (parser.nextToken() != JsonToken.START_ARRAY) {
    throw new IllegalArgumentException("Expected array");
}

while (parser.nextToken() != JsonToken.END_ARRAY) {
    if (parser.currentToken() == null) {
        throw new IllegalArgumentException("Unexpected end of array");
    }

    if (parser.currentToken() == JsonToken.START_OBJECT) {
        User user = readUser(parser);
        process(user);
    } else {
        parser.skipChildren();
    }
}
~~~

readUser(parser) cần đọc từ START_OBJECT đến END_OBJECT tương ứng. Khi trả về, parser phải đang ở END_OBJECT của user hiện tại để vòng lặp array có thể gọi nextToken() và đến phần tử kế tiếp.

## 20. Đọc object lồng nhau bằng phương thức riêng

Tách logic đọc object con thành hàm giúp quản lý vị trí parser rõ ràng:

~~~java
private User readUser(JsonParser parser) throws IOException {
    if (parser.currentToken() != JsonToken.START_OBJECT) {
        throw new IllegalArgumentException("Expected user object");
    }

    Long id = null;
    String name = null;

    JsonToken token;
    while ((token = parser.nextToken()) != JsonToken.END_OBJECT) {
        if (token == null) {
            throw new IllegalArgumentException("Unexpected end of user");
        }
        if (token != JsonToken.FIELD_NAME) {
            throw new IllegalArgumentException("Expected user field");
        }

        String fieldName = parser.currentName();
        JsonToken valueToken = parser.nextToken();

        switch (fieldName) {
            case "id" -> {
                if (valueToken == JsonToken.VALUE_NUMBER_INT) {
                    id = parser.getLongValue();
                } else if (valueToken == JsonToken.VALUE_NULL) {
                    id = null;
                } else {
                    throw new IllegalArgumentException("Invalid id");
                }
            }
            case "name" -> {
                if (valueToken == JsonToken.VALUE_STRING) {
                    name = parser.getText();
                } else if (valueToken == JsonToken.VALUE_NULL) {
                    name = null;
                } else {
                    throw new IllegalArgumentException("Invalid name");
                }
            }
            default -> parser.skipChildren();
        }
    }

    return new User(id, name);
}
~~~

Hàm này chỉ đọc đúng một object. Nó không tự gọi nextToken() sau END_OBJECT trước khi trả về. Đây là hợp đồng vị trí parser quan trọng khi phối hợp các hàm đọc lồng nhau.

Trong một dự án thực tế, có thể tạo DTO immutable hoặc mutable tùy thiết kế. Điều cốt lõi ở đây là quy ước rõ ràng: hàm nhận parser tại START_OBJECT và trả về khi parser đứng tại END_OBJECT tương ứng.

## 21. Đọc số và giữ độ chính xác

Token số có thể được lấy theo nhiều kiểu. Ví dụ JSON:

~~~json
{
  "quantity": 3,
  "amount": 125000.50,
  "largeId": 123456789012345678901234
}
~~~

Có thể đọc:

~~~java
if (valueToken == JsonToken.VALUE_NUMBER_INT) {
    BigInteger integer = parser.getBigIntegerValue();
}

if (valueToken == JsonToken.VALUE_NUMBER_FLOAT) {
    BigDecimal decimal = parser.getDecimalValue();
}
~~~

Nếu biết giới hạn dữ liệu, có thể chọn int hoặc long. Nếu cần giữ số nguyên rất lớn, dùng BigInteger. Với tiền hoặc decimal chính xác, dùng BigDecimal.

getText() có thể trả dạng văn bản số ban đầu, nhưng tự parse chuỗi sẽ khiến ứng dụng phải tự xử lý định dạng, overflow và lỗi số. Typed accessor của parser làm rõ kiểu đích và báo lỗi chuyển đổi phù hợp.

## 22. Đọc giá trị null, field thiếu và field lặp

Streaming parser cho phép phân biệt:

- Field không xuất hiện: vòng lặp không gặp FIELD_NAME tương ứng.
- Field có giá trị null: parser phát VALUE_NULL.
- Field có giá trị rỗng: parser phát VALUE_STRING với nội dung chuỗi rỗng, hoặc START_ARRAY/END_ARRAY cho mảng rỗng.

Ví dụ:

~~~json
{
  "name": null,
  "tags": [],
  "note": ""
}
~~~

name là null; tags là array rỗng; note là chuỗi rỗng. Chúng không tương đương nhau.

JSON cũng có thể chứa tên field lặp:

~~~json
{
  "role": "user",
  "role": "admin"
}
~~~

Parser streaming có thể phát ra cả hai lần xuất hiện theo thứ tự trong input. Ứng dụng cần quyết định chính sách: từ chối tên lặp, dùng giá trị đầu, dùng giá trị cuối hoặc xử lý từng lần xuất hiện. Nếu hợp đồng yêu cầu tên field duy nhất, cần kiểm tra bằng Set tên đã gặp.

~~~java
Set<String> seen = new HashSet<>();

while (parser.nextToken() == JsonToken.FIELD_NAME) {
    String fieldName = parser.currentName();
    if (!seen.add(fieldName)) {
        throw new IllegalArgumentException(
            "Duplicate field: " + fieldName
        );
    }

    JsonToken valueToken = parser.nextToken();
    // Xử lý giá trị
}
~~~

Không nên dựa vào Map trung gian để phát hiện field trùng vì Map thường chỉ giữ một value cho mỗi key và có thể làm mất thông tin lần xuất hiện trước.

## 23. Đọc token mà không giữ toàn bộ nội dung trong bộ nhớ

Lợi ích chính của streaming là ứng dụng có thể xử lý dữ liệu khi parser đi qua từng token. Với array lớn, không cần tạo một List chứa toàn bộ phần tử:

~~~java
try (JsonParser parser = factory.createParser(inputStream)) {
    if (parser.nextToken() != JsonToken.START_ARRAY) {
        throw new IllegalArgumentException("Expected array");
    }

    while (parser.nextToken() != JsonToken.END_ARRAY) {
        if (parser.currentToken() == JsonToken.START_OBJECT) {
            User user = readUser(parser);
            process(user);
        } else {
            parser.skipChildren();
        }
    }
}
~~~

Ở đây, từng User được tạo, xử lý rồi có thể giải phóng trước khi parser đọc phần tử tiếp theo. Bộ nhớ cần thiết phụ thuộc vào phần tử đang xử lý và trạng thái nghiệp vụ, thay vì toàn bộ array.

Nếu process(user) lưu tất cả phần tử vào một collection, lợi ích tiết kiệm bộ nhớ sẽ giảm. Streaming hiệu quả nhất khi có thể xử lý tuần tự, ghi ra đích hoặc tổng hợp kết quả tăng dần.

## 24. Vị trí parser sau mỗi thao tác

Lỗi phổ biến trong streaming là không biết parser đang đứng ở token nào sau khi gọi một phương thức đọc.

| Thao tác | Vị trí parser sau thao tác |
|---|---|
| nextToken() | Token kế tiếp |
| currentToken() | Không di chuyển, chỉ trả token hiện tại |
| currentName() | Không di chuyển, trả tên field trong ngữ cảnh hiện tại |
| getText() | Không di chuyển, lấy nội dung token hiện tại |
| getIntValue()/getDecimalValue() | Không di chuyển, chuyển giá trị token hiện tại |
| skipChildren() khi ở START_OBJECT/START_ARRAY | Đứng tại END_OBJECT/END_ARRAY tương ứng |
| nextFieldName() | Di chuyển đến token kế tiếp; trả tên nếu token đó là FIELD_NAME |
| nextTextValue() | Di chuyển đến token kế tiếp; trả text nếu token đó là VALUE_STRING |

Khi viết helper method, hãy ghi rõ điều kiện đầu vào và vị trí đầu ra. Ví dụ, readAddress nhận parser đang ở START_OBJECT và trả về khi parser ở END_OBJECT. Nhờ đó, caller biết chính xác khi nào cần gọi nextToken() tiếp theo.

## 25. Đọc văn bản lớn bằng getTextCharacters()

Với một giá trị string rất lớn, getText() tạo hoặc trả về một String hoàn chỉnh. Nếu cần xử lý trực tiếp dữ liệu ký tự để giảm cấp phát, JsonParser cung cấp:

- getTextCharacters(): mảng ký tự chứa nội dung token hiện tại.
- getTextOffset(): vị trí bắt đầu của nội dung trong mảng.
- getTextLength(): độ dài nội dung hợp lệ.

Ví dụ:

~~~java
if (parser.currentToken() == JsonToken.VALUE_STRING) {
    char[] buffer = parser.getTextCharacters();
    int offset = parser.getTextOffset();
    int length = parser.getTextLength();

    processCharacters(buffer, offset, length);
}
~~~

Không giả định nội dung luôn bắt đầu ở chỉ số 0 hoặc chiếm toàn bộ mảng. Chỉ đoạn từ offset với length mới thuộc token hiện tại.

Mảng ký tự có thể được parser tái sử dụng khi tiến sang token tiếp theo. Không giữ tham chiếu đến buffer để dùng lâu dài sau khi parser di chuyển. Nếu cần lưu dữ liệu, hãy sao chép phần ký tự cần thiết hoặc xử lý ngay trong lúc buffer còn hợp lệ.

Tối ưu này chỉ đáng dùng khi profiling cho thấy chuỗi lớn hoặc cấp phát String là điểm nghẽn. Với phần lớn trường dữ liệu thông thường, getText() dễ đọc và đủ hiệu quả.

## 26. Đọc tên field và giá trị với JsonLocation

Khi JSON sai cấu trúc hoặc có giá trị không hợp lệ, vị trí token giúp chẩn đoán lỗi:

~~~java
JsonLocation tokenLocation = parser.getTokenLocation();
JsonLocation currentLocation = parser.getCurrentLocation();

System.out.println(tokenLocation.getLineNr());
System.out.println(tokenLocation.getColumnNr());
~~~

getTokenLocation() cho vị trí bắt đầu token hiện tại; getCurrentLocation() cho vị trí parser hiện tại trong input. Tùy nguồn đầu vào, JsonLocation có thể cung cấp byte offset hoặc character offset cùng thông tin dòng/cột.

Ví dụ khi trường age không phải số:

~~~java
if (valueToken != JsonToken.VALUE_NUMBER_INT) {
    JsonLocation location = parser.getTokenLocation();
    throw new IllegalArgumentException(
        "age must be an integer at line "
            + location.getLineNr()
            + ", column "
            + location.getColumnNr()
    );
}
~~~

Thông tin vị trí hữu ích khi đọc file lớn hoặc nhận payload phức tạp. Với lỗi cú pháp JSON, Jackson thường ném JsonParseException có thông tin vị trí và parsing context.

## 27. Kết hợp streaming parser với Databind

Không phải lúc nào cũng cần tự ánh xạ từng field. Có thể dùng JsonParser để tìm đúng vị trí hoặc xử lý cấu trúc lớn, sau đó giao một object con cho ObjectMapper đọc thành DTO.

Ví dụ:

~~~java
try (JsonParser parser = mapper.getFactory().createParser(json)) {
    if (parser.nextToken() != JsonToken.START_OBJECT) {
        throw new IllegalArgumentException("Expected root object");
    }

    while (parser.nextToken() == JsonToken.FIELD_NAME) {
        String fieldName = parser.currentName();
        JsonToken valueToken = parser.nextToken();

        if ("payload".equals(fieldName)
                && valueToken == JsonToken.START_OBJECT) {
            User user = mapper.readValue(parser, User.class);
            process(user);
        } else {
            parser.skipChildren();
        }
    }
}
~~~

ObjectMapper đọc object hiện tại thành User và tiêu thụ nội dung object đó. Sau khi đọc xong, parser đứng ở token kết thúc object payload; vòng lặp bên ngoài tiếp tục từ token kế tiếp. Cần giữ nhất quán quy ước vị trí parser để không bỏ qua field sau payload.

Cách kết hợp này phù hợp khi root chứa nhiều phần dữ liệu nhưng chỉ một số nhánh cần DTO. Parser streaming điều khiển luồng lớn; Databind xử lý chi tiết object con.

## 28. Kiểm tra token trước khi đọc giá trị

Một số phương thức tiện ích giúp xác định cấu trúc:

- isExpectedStartObjectToken(): kiểm tra token hiện tại là START_OBJECT.
- isExpectedStartArrayToken(): kiểm tra token hiện tại là START_ARRAY.
- currentToken().isScalarValue(): kiểm tra token hiện tại là scalar.
- currentToken().isNumeric(): kiểm tra token số.
- currentToken().isStructStart(): kiểm tra token mở cấu trúc.
- currentToken().isStructEnd(): kiểm tra token đóng cấu trúc.

Ví dụ:

~~~java
JsonToken token = parser.currentToken();

if (token != null && token.isScalarValue()) {
    String scalarText = parser.getText();
} else if (token == JsonToken.START_OBJECT) {
    // Đọc object con
} else if (token == JsonToken.START_ARRAY) {
    // Đọc array con
}
~~~

Các predicate trên giúp code tổng quát hơn, nhưng khi hợp đồng yêu cầu kiểu cụ thể như Integer hoặc Boolean, nên so sánh trực tiếp với VALUE_NUMBER_INT hoặc VALUE_TRUE/VALUE_FALSE.

## 29. Đọc một tài liệu JSON hoàn chỉnh và kiểm tra phần dư

Một JSON document chuẩn thường có một giá trị root. Sau khi xử lý xong root, có thể gọi nextToken() thêm một lần để xác nhận không còn token dư:

~~~java
try (JsonParser parser = factory.createParser(json)) {
    JsonToken rootToken = parser.nextToken();
    if (rootToken == null) {
        throw new IllegalArgumentException("Empty JSON input");
    }

    // Đọc giá trị root theo loại token.
    readRoot(parser, rootToken);

    if (parser.nextToken() != null) {
        throw new IllegalArgumentException("Trailing JSON content");
    }
}
~~~

Điều này hữu ích khi ứng dụng tự viết vòng lặp streaming và muốn từ chối dữ liệu có thêm một giá trị JSON khác sau root. Nếu parser được dùng để đọc chuỗi nhiều JSON value liên tiếp theo một giao thức riêng, quy tắc sẽ khác và caller cần quản lý từng root.

## 30. Những lỗi thường gặp khi đọc tên và giá trị

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Mất tên trường | Chỉ gọi nextToken() đến value rồi không lưu FIELD_NAME | Lưu currentName() trước khi tiến đến value |
| Bỏ qua giá trị | Gọi nextToken() thêm lần nữa sau khi đã đến value | Theo dõi token hiện tại và chỉ tiến khi đã xử lý xong |
| Gọi getIntValue() trên chuỗi | Không kiểm tra JsonToken | Xác nhận VALUE_NUMBER_INT trước |
| Nhầm null với false hoặc 0 | Dùng API coercion có giá trị mặc định | Kiểm tra VALUE_NULL riêng |
| Dừng nhầm object cha | Không quản lý END_OBJECT lồng nhau | Tách helper và xác định rõ token bắt đầu/kết thúc |
| Bỏ qua field kế tiếp | skipChildren() đã đưa parser đến END của nhánh con | Lần nextToken() tiếp theo mới đến field kế tiếp |
| Mất field lạ | Bỏ qua mọi token không nhận diện nhưng không thống nhất hợp đồng | Chọn rõ chính sách ignore hoặc reject |
| Sai kiểu số hoặc overflow | Dùng accessor có phạm vi quá nhỏ | Chọn long, BigInteger hoặc BigDecimal phù hợp |
| Ép scalar ngoài ý muốn | Dùng getValueAsXxx() mà không kiểm tra token | Dùng typed accessor sau khi xác nhận token |
| Dùng buffer ký tự sau khi parser tiến | Parser tái sử dụng buffer | Xử lý ngay hoặc sao chép dữ liệu |

## 31. Ví dụ tổng hợp đọc tên trường và giá trị theo token

Ví dụ sau đọc một đơn hàng có scalar, object lồng nhau và array. Nó chỉ giữ các trường cần thiết và bỏ qua field chưa biết:

~~~java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;

import java.io.IOException;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

public class OrderStreamReader {

    private final JsonFactory factory = new JsonFactory();

    public OrderData read(String json) throws IOException {
        try (JsonParser parser = factory.createParser(json)) {
            if (parser.nextToken() != JsonToken.START_OBJECT) {
                throw new IllegalArgumentException("Expected order object");
            }

            Long orderId = null;
            String customerName = null;
            List<ItemData> items = new ArrayList<>();

            JsonToken token;
            while ((token = parser.nextToken()) != JsonToken.END_OBJECT) {
                if (token == null) {
                    throw new IllegalArgumentException("Unexpected end of order");
                }
                if (token != JsonToken.FIELD_NAME) {
                    throw new IllegalArgumentException("Expected order field");
                }

                String fieldName = parser.currentName();
                JsonToken valueToken = parser.nextToken();

                switch (fieldName) {
                    case "orderId" -> {
                        if (valueToken == JsonToken.VALUE_NUMBER_INT) {
                            orderId = parser.getLongValue();
                        } else if (valueToken != JsonToken.VALUE_NULL) {
                            throw new IllegalArgumentException("Invalid orderId");
                        }
                    }
                    case "customer" -> {
                        if (valueToken == JsonToken.START_OBJECT) {
                            customerName = readCustomerName(parser);
                        } else if (valueToken != JsonToken.VALUE_NULL) {
                            throw new IllegalArgumentException("Invalid customer");
                        }
                    }
                    case "items" -> {
                        if (valueToken == JsonToken.START_ARRAY) {
                            items = readItems(parser);
                        } else if (valueToken != JsonToken.VALUE_NULL) {
                            throw new IllegalArgumentException("Invalid items");
                        }
                    }
                    default -> parser.skipChildren();
                }
            }

            if (parser.nextToken() != null) {
                throw new IllegalArgumentException("Trailing JSON content");
            }

            return new OrderData(orderId, customerName, items);
        }
    }

    private String readCustomerName(JsonParser parser) throws IOException {
        String name = null;

        JsonToken token;
        while ((token = parser.nextToken()) != JsonToken.END_OBJECT) {
            if (token == null) {
                throw new IllegalArgumentException("Unexpected end of customer");
            }
            if (token != JsonToken.FIELD_NAME) {
                throw new IllegalArgumentException("Expected customer field");
            }

            String fieldName = parser.currentName();
            JsonToken valueToken = parser.nextToken();

            if ("name".equals(fieldName)) {
                if (valueToken == JsonToken.VALUE_STRING) {
                    name = parser.getText();
                } else if (valueToken != JsonToken.VALUE_NULL) {
                    throw new IllegalArgumentException("Invalid customer name");
                }
            } else {
                parser.skipChildren();
            }
        }

        return name;
    }

    private List<ItemData> readItems(JsonParser parser) throws IOException {
        List<ItemData> items = new ArrayList<>();

        JsonToken token;
        while ((token = parser.nextToken()) != JsonToken.END_ARRAY) {
            if (token == null) {
                throw new IllegalArgumentException("Unexpected end of items");
            }

            if (token == JsonToken.START_OBJECT) {
                items.add(readItem(parser));
            } else if (token == JsonToken.VALUE_NULL) {
                // Chính sách ví dụ: bỏ qua phần tử null.
            } else {
                throw new IllegalArgumentException("Item must be an object");
            }
        }

        return items;
    }

    private ItemData readItem(JsonParser parser) throws IOException {
        String sku = null;
        Integer quantity = null;
        BigDecimal price = null;

        JsonToken token;
        while ((token = parser.nextToken()) != JsonToken.END_OBJECT) {
            if (token == null) {
                throw new IllegalArgumentException("Unexpected end of item");
            }
            if (token != JsonToken.FIELD_NAME) {
                throw new IllegalArgumentException("Expected item field");
            }

            String fieldName = parser.currentName();
            JsonToken valueToken = parser.nextToken();

            switch (fieldName) {
                case "sku" -> {
                    if (valueToken == JsonToken.VALUE_STRING) {
                        sku = parser.getText();
                    } else if (valueToken != JsonToken.VALUE_NULL) {
                        throw new IllegalArgumentException("Invalid sku");
                    }
                }
                case "quantity" -> {
                    if (valueToken == JsonToken.VALUE_NUMBER_INT) {
                        quantity = parser.getIntValue();
                    } else if (valueToken != JsonToken.VALUE_NULL) {
                        throw new IllegalArgumentException("Invalid quantity");
                    }
                }
                case "price" -> {
                    if (valueToken == JsonToken.VALUE_NUMBER_INT
                            || valueToken == JsonToken.VALUE_NUMBER_FLOAT) {
                        price = parser.getDecimalValue();
                    } else if (valueToken != JsonToken.VALUE_NULL) {
                        throw new IllegalArgumentException("Invalid price");
                    }
                }
                default -> parser.skipChildren();
            }
        }

        return new ItemData(sku, quantity, price);
    }

    public record OrderData(
        Long orderId,
        String customerName,
        List<ItemData> items
    ) {}

    public record ItemData(
        String sku,
        Integer quantity,
        BigDecimal price
    ) {}
}
~~~

JSON đầu vào minh họa:

~~~json
{
  "orderId": 501,
  "customer": {
    "name": "Mai",
    "country": "VN"
  },
  "items": [
    {
      "sku": "P01",
      "quantity": 2,
      "price": 125000.50
    },
    {
      "sku": "P02",
      "quantity": 1,
      "price": 45000
    }
  ],
  "trace": {
    "source": "mobile"
  }
}
~~~

Ví dụ thể hiện các điểm chính:

1. FIELD_NAME được đọc riêng trước value token.
2. Scalar được lấy bằng accessor phù hợp với loại token.
3. Object customer được đọc trong một phương thức riêng.
4. Array items được duyệt từng phần tử.
5. Mỗi item object được đọc đến END_OBJECT tương ứng.
6. Field trace chưa cần dùng được bỏ qua bằng skipChildren().
7. Giá trị price dùng BigDecimal để giữ độ chính xác thập phân.
8. Parser được đóng bằng try-with-resources.

## 32. Khi nào nên dùng streaming token thay vì DTO hoặc JsonNode?

| Cách đọc | Phù hợp khi | Đặc điểm |
|---|---|---|
| ObjectMapper sang DTO | Cấu trúc ổn định và cần object Java đầy đủ | Ít code thủ công, dễ dùng trong nghiệp vụ |
| JsonNode tree model | Cần kiểm tra hoặc sửa cấu trúc linh hoạt | Giữ toàn bộ cây trong bộ nhớ |
| JsonParser streaming | Dữ liệu lớn hoặc chỉ cần một phần thông tin | Xử lý từng token, kiểm soát chính xác luồng |

Streaming đòi hỏi quản lý vị trí parser và loại token cẩn thận hơn. Đổi lại, ứng dụng có thể bỏ qua nhánh không cần thiết, xử lý array lớn tuần tự và tránh tạo toàn bộ cây JSON.

Nếu chỉ cần ánh xạ một request API thông thường thành DTO, Databind thường ngắn gọn hơn. Nếu cần đọc log lớn, file JSON nhiều bản ghi hoặc payload có nhiều nhánh không cần thiết, streaming có thể phù hợp hơn.

## 33. Nguyên tắc thực hành

- Luôn phân biệt FIELD_NAME với token giá trị của field.
- Lưu tên trường trước khi gọi nextToken() để đọc value.
- Kiểm tra JsonToken trước khi gọi getIntValue(), getText() hoặc getBooleanValue() nếu hợp đồng yêu cầu kiểu nghiêm ngặt.
- Dùng BigDecimal cho số thập phân cần độ chính xác.
- Phân biệt VALUE_NULL, chuỗi rỗng và trường bị thiếu.
- Với object/array lồng nhau, quản lý đúng START và END token tương ứng.
- Dùng skipChildren() để bỏ qua nhánh không cần xử lý.
- Chỉ dùng các phương thức coercion như getValueAsString() khi muốn chấp nhận chuyển đổi scalar.
- Xác định rõ vị trí parser trước và sau mỗi helper method.
- Dùng getTextCharacters() chỉ khi cần tối ưu và xử lý buffer trước khi parser tiến tiếp.
- Kiểm tra token dư sau root nếu giao thức yêu cầu đúng một JSON document.

Đọc tên trường và giá trị theo loại token là nền tảng của Jackson streaming. Khi hiểu thứ tự FIELD_NAME rồi đến token giá trị, ứng dụng có thể đọc scalar chính xác, đi sâu vào object và array, bỏ qua phần dữ liệu không cần thiết và xử lý JSON lớn mà không phải nạp toàn bộ cấu trúc vào bộ nhớ.
