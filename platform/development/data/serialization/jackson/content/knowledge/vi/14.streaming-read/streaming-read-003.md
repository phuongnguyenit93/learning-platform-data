# Duyệt token và kiểm tra vị trí trong cấu trúc JSON

Jackson Core cung cấp streaming API để đọc JSON tuần tự theo từng token. Thay vì dựng toàn bộ tài liệu thành object Java hoặc cây `JsonNode`, ứng dụng có thể đọc token hiện tại, xem nó thuộc object hay array nào, xác định tên field và vị trí trong tài liệu, rồi quyết định đọc tiếp, bỏ qua một nhánh hoặc ánh xạ một phần dữ liệu.

Khả năng này hữu ích khi xử lý file lớn, message stream, log, dữ liệu lồng nhau hoặc khi cần báo lỗi với vị trí cụ thể. Để sử dụng tốt streaming parser, cần hiểu `JsonParser`, `JsonToken`, cách di chuyển bằng `nextToken()`, cách kiểm tra parsing context và cách lấy line/column của token.

## 1. Streaming parser hoạt động theo token

JSON là cấu trúc gồm object, array và các giá trị scalar. Jackson Core đọc cấu trúc này thành một chuỗi token.

Ví dụ JSON:

```json
{
  "id": 42,
  "name": "An",
  "active": true,
  "roles": ["ADMIN", "USER"],
  "address": {
    "city": "Hanoi"
  }
}
```

Một luồng token tương ứng có dạng:

```text
START_OBJECT
FIELD_NAME("id")
VALUE_NUMBER_INT(42)
FIELD_NAME("name")
VALUE_STRING("An")
FIELD_NAME("active")
VALUE_TRUE
FIELD_NAME("roles")
START_ARRAY
  VALUE_STRING("ADMIN")
  VALUE_STRING("USER")
END_ARRAY
FIELD_NAME("address")
START_OBJECT
  FIELD_NAME("city")
  VALUE_STRING("Hanoi")
END_OBJECT
END_OBJECT
```

Parser không cần tạo ngay một object `User` hay `JsonNode`. Nó báo cho ứng dụng biết token kế tiếp là gì và ứng dụng có thể xử lý tại chỗ.

### 1.1. Các nhóm JsonToken thường gặp

| Token | Ý nghĩa |
|---|---|
| `START_OBJECT` | Bắt đầu JSON object `{` |
| `END_OBJECT` | Kết thúc JSON object `}` |
| `START_ARRAY` | Bắt đầu JSON array `[` |
| `END_ARRAY` | Kết thúc JSON array `]` |
| `FIELD_NAME` | Tên một thuộc tính trong object |
| `VALUE_STRING` | Giá trị string |
| `VALUE_NUMBER_INT` | Giá trị số nguyên |
| `VALUE_NUMBER_FLOAT` | Giá trị số thập phân |
| `VALUE_TRUE` / `VALUE_FALSE` | Giá trị boolean |
| `VALUE_NULL` | Giá trị null |

Ngoài các token trên, parser còn có thể phát hiện token không hợp lệ hoặc kết thúc đầu vào. `nextToken()` trả về `null` khi không còn token nào trong nguồn.

## 2. Tạo JsonParser

Trong Jackson 2.x, `JsonFactory` là thành phần tạo parser và generator. Có thể lấy factory từ `ObjectMapper` hoặc tạo riêng.

```java
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
```

Nếu ứng dụng đã có mapper:

```java
JsonParser parser = mapper.getFactory().createParser(inputStream);
```

Dùng try-with-resources để đóng parser và nguồn tài nguyên do đoạn code sở hữu. Với parser tạo từ file hoặc InputStream, việc đóng parser thường cũng đóng nguồn bên dưới theo cấu hình auto-close mặc định. Nếu nguồn do một tầng khác quản lý và cần tiếp tục sử dụng, hãy thống nhất quyền sở hữu hoặc cấu hình auto-close phù hợp.

Các overload `createParser` có thể nhận String, byte array, File, InputStream, Reader và một số nguồn khác. Chọn nguồn phù hợp để tránh tạo bản sao dữ liệu không cần thiết.

## 3. Duyệt token bằng nextToken()

`nextToken()` di chuyển parser đến token kế tiếp và trả về token đó. Parser giữ trạng thái tại token hiện tại cho đến khi ứng dụng gọi phương thức di chuyển tiếp.

```java
try (JsonParser parser = factory.createParser(json)) {
    JsonToken token;

    while ((token = parser.nextToken()) != null) {
        switch (token) {
            case START_OBJECT -> System.out.println("Object begins");
            case END_OBJECT -> System.out.println("Object ends");
            case START_ARRAY -> System.out.println("Array begins");
            case END_ARRAY -> System.out.println("Array ends");
            case FIELD_NAME ->
                System.out.println("Field: " + parser.currentName());
            case VALUE_STRING ->
                System.out.println("String: " + parser.getText());
            case VALUE_NUMBER_INT ->
                System.out.println("Integer: " + parser.getLongValue());
            case VALUE_NUMBER_FLOAT ->
                System.out.println("Decimal: " + parser.getDecimalValue());
            case VALUE_TRUE -> System.out.println("Boolean: true");
            case VALUE_FALSE -> System.out.println("Boolean: false");
            case VALUE_NULL -> System.out.println("Null");
            default -> {
                // Có thể xử lý các token khác nếu ứng dụng cần
            }
        }
    }
}
```

Với một JSON object, thứ tự thường là:

1. `START_OBJECT`.
2. `FIELD_NAME`.
3. Token biểu diễn giá trị của field.
4. Lặp lại FIELD_NAME và value cho các thuộc tính tiếp theo.
5. `END_OBJECT`.

Với array, parser phát `START_ARRAY`, sau đó là token của từng phần tử, rồi `END_ARRAY`. Phần tử có thể là scalar, object hoặc array lồng nhau.

### 3.1. FIELD_NAME và value là hai token khác nhau

Xét:

```json
{
  "age": 25
}
```

Parser không trả về một token chứa cả cặp `age: 25`. Nó phát hai token:

```text
FIELD_NAME("age")
VALUE_NUMBER_INT(25)
```

Khi parser đang ở `FIELD_NAME`, dùng `currentName()` để lấy tên field. Sau đó gọi `nextToken()` hoặc `nextValue()` để đến token giá trị.

```java
if (parser.nextToken() == JsonToken.START_OBJECT) {
    while (parser.nextToken() == JsonToken.FIELD_NAME) {
        String fieldName = parser.currentName();
        JsonToken valueToken = parser.nextToken();

        System.out.printf(
            "field=%s, valueToken=%s%n",
            fieldName,
            valueToken
        );

        if (valueToken == JsonToken.VALUE_NUMBER_INT) {
            long value = parser.getLongValue();
            System.out.println(value);
        }
    }
}
```

Đoạn code trên minh họa một object chỉ có các giá trị scalar. Nếu giá trị là object hoặc array lồng nhau, parser cần đi qua các token con hoặc bỏ qua nhánh đó bằng `skipChildren()`.

## 4. Đọc nhanh tên field với nextFieldName()

Khi đang duyệt object, `nextFieldName()` là một tiện ích giúp tiến đến field kế tiếp và trả về tên field nếu token đó là `FIELD_NAME`.

```java
if (parser.nextToken() == JsonToken.START_OBJECT) {
    String fieldName;

    while ((fieldName = parser.nextFieldName()) != null) {
        JsonToken valueToken = parser.nextToken();

        if ("id".equals(fieldName)
                && valueToken == JsonToken.VALUE_NUMBER_INT) {
            long id = parser.getLongValue();
            System.out.println("id = " + id);
        } else if ("name".equals(fieldName)
                && valueToken == JsonToken.VALUE_STRING) {
            String name = parser.getText();
            System.out.println("name = " + name);
        } else if (valueToken == JsonToken.START_OBJECT
                || valueToken == JsonToken.START_ARRAY) {
            parser.skipChildren();
        }
    }
}
```

Khi hết field, `nextFieldName()` trả về null và parser đang ở token kết thúc object. Cách này phù hợp khi biết mình đang duyệt một object cụ thể.

Lưu ý: nếu giá trị field là object/array và ứng dụng không xử lý nhánh đó, cần gọi `skipChildren()` để parser bỏ qua toàn bộ nội dung lồng nhau. Nếu không, vòng lặp có thể tiếp tục nhìn thấy các FIELD_NAME bên trong object con và nhầm chúng là field của object ngoài.

## 5. Dùng nextValue() để bỏ qua bước FIELD_NAME

`nextValue()` di chuyển đến token tiếp theo nhưng nếu token hiện tại là `FIELD_NAME`, nó tiến thêm một bước để đến token biểu diễn giá trị. Điều này tiện khi xử lý từng cặp key/value.

```java
if (parser.nextToken() == JsonToken.START_OBJECT) {
    while (parser.nextToken() == JsonToken.FIELD_NAME) {
        String fieldName = parser.currentName();
        JsonToken valueToken = parser.nextValue();

        if ("enabled".equals(fieldName)) {
            if (valueToken == JsonToken.VALUE_TRUE) {
                System.out.println("enabled=true");
            } else if (valueToken == JsonToken.VALUE_FALSE) {
                System.out.println("enabled=false");
            }
        } else if (valueToken == JsonToken.START_OBJECT
                || valueToken == JsonToken.START_ARRAY) {
            parser.skipChildren();
        }
    }
}
```

Ở đây, vòng lặp gọi `nextToken()` để đến field tiếp theo; `nextValue()` lấy giá trị của field đó. Đây là một mẫu hữu ích cho object phẳng. Với cấu trúc lồng sâu, hãy quản lý context hoặc dùng parser state rõ ràng để không nhầm field con với field cha.

## 6. Kiểm tra vị trí trong cấu trúc JSON

Parser không chỉ cho biết token hiện tại. Nó còn duy trì parsing context để biểu diễn parser đang ở root, object hay array nào.

Lấy context:

```java
import com.fasterxml.jackson.core.JsonStreamContext;

JsonStreamContext context = parser.getParsingContext();

System.out.println("in object: " + context.inObject());
System.out.println("in array: " + context.inArray());
System.out.println("field name: " + context.getCurrentName());
System.out.println("array index: " + context.getCurrentIndex());
```

Các phương thức quan trọng:

- `inRoot()`: context hiện tại là root context.
- `inObject()`: parser đang ở bên trong một object.
- `inArray()`: parser đang ở bên trong một array.
- `getCurrentName()`: tên field hiện tại trong object context, nếu có.
- `getCurrentIndex()`: chỉ số phần tử hiện tại trong array context.
- `getParent()`: context cha, giúp đi ngược lên cấu trúc bên ngoài.

Ví dụ với JSON:

```json
{
  "users": [
    {
      "id": 42,
      "name": "An"
    }
  ]
}
```

Khi parser đang đọc giá trị `name`, context gần nhất là object của phần tử array. Context cha là array `users`, và context phía trên nữa là object gốc. Nhờ đi ngược qua `getParent()`, ứng dụng có thể biết token thuộc nhánh nào.

### 6.1. In toàn bộ context stack

```java
private static void printContext(JsonParser parser) throws IOException {
    JsonStreamContext context = parser.getParsingContext();

    for (JsonStreamContext current = context;
         current != null;
         current = current.getParent()) {

        String kind = current.inRoot()
            ? "ROOT"
            : current.inObject()
                ? "OBJECT"
                : "ARRAY";

        System.out.printf(
            "kind=%s, name=%s, index=%d%n",
            kind,
            current.getCurrentName(),
            current.getCurrentIndex()
        );
    }
}
```

Hàm này hữu ích khi debug cấu trúc lồng nhau. Nó in context hiện tại trước, sau đó lần lượt in context cha cho đến root.

### 6.2. Tạo JSON Pointer từ context

Đối với token giá trị hoặc field đang nằm trong một object/array, có thể dựng đường dẫn theo JSON Pointer bằng cách duyệt context stack từ trong ra ngoài. JSON Pointer escape `~` thành `~0` và `/` thành `~1` trong tên property.

```java
import com.fasterxml.jackson.core.JsonStreamContext;
import java.util.ArrayDeque;
import java.util.Deque;

private static String currentPath(JsonParser parser) {
    Deque<String> segments = new ArrayDeque<>();

    for (JsonStreamContext context = parser.getParsingContext();
         context != null && !context.inRoot();
         context = context.getParent()) {

        if (context.inObject()) {
            String name = context.getCurrentName();
            if (name != null) {
                segments.push(name.replace("~", "~0").replace("/", "~1"));
            }
        } else if (context.inArray()) {
            segments.push(Integer.toString(context.getCurrentIndex()));
        }
    }

    StringBuilder path = new StringBuilder("#");
    while (!segments.isEmpty()) {
        path.append('/').append(segments.pop());
    }
    return path.toString();
}
```

Ví dụ đường dẫn có thể có dạng:

```text
#/users/0/name
```

Đây là JSON Pointer dạng URI fragment, phù hợp để log hoặc báo lỗi. Khi parser đang ở token bắt đầu của một container rỗng hoặc trước phần tử đầu tiên của array, index có thể chưa đại diện cho phần tử cụ thể; chỉ nên diễn giải path theo trạng thái token hiện tại.

## 7. Phân biệt token location và current location

Jackson cung cấp hai loại vị trí hữu ích:

- `getTokenLocation()`: vị trí bắt đầu của token hiện tại trong nguồn.
- `getCurrentLocation()`: vị trí hiện tại của parser trong nguồn, thường là điểm parser đã đọc tới sau token hoặc phần dữ liệu đang xử lý.

Ví dụ:

```java
JsonLocation tokenLocation = parser.getTokenLocation();
JsonLocation currentLocation = parser.getCurrentLocation();

System.out.printf(
    "token starts at line %d, column %d%n",
    tokenLocation.getLineNr(),
    tokenLocation.getColumnNr()
);

System.out.printf(
    "parser is at line %d, column %d%n",
    currentLocation.getLineNr(),
    currentLocation.getColumnNr()
);
```

`JsonLocation` có thể cung cấp:

| Phương thức | Ý nghĩa |
|---|---|
| `getLineNr()` | Số dòng |
| `getColumnNr()` | Số cột |
| `getCharOffset()` | Offset ký tự nếu nguồn hỗ trợ |
| `getByteOffset()` | Offset byte nếu nguồn hỗ trợ |
| `sourceDescription()` | Mô tả nguồn dữ liệu |

Line và column thường được biểu diễn theo cách đếm bắt đầu từ 1. Byte/character offset có thể không có sẵn cho mọi loại nguồn; giá trị không xác định thường được biểu diễn bằng số âm. Vì vậy, không nên giả định parser luôn biết byte offset khi nguồn là Reader hoặc String.

### 7.1. Báo lỗi cùng vị trí token

```java
if (token == JsonToken.VALUE_NUMBER_INT) {
    long value = parser.getLongValue();

    if (value < 0) {
        JsonLocation location = parser.getTokenLocation();

        throw new IllegalArgumentException(
            "Value must be non-negative at line "
                + location.getLineNr()
                + ", column "
                + location.getColumnNr()
        );
    }
}
```

Trong ứng dụng thực tế, nên gắn thêm đường dẫn field hoặc context hiện tại để người dùng biết lỗi xảy ra ở đâu, ví dụ:

```text
Invalid value at $["users"][2]["age"], line 8, column 17
```

Line/column giúp định vị trong tài liệu; path giúp định vị trong cấu trúc dữ liệu. Kết hợp hai loại thông tin giúp xử lý lỗi dễ hơn.

## 8. Bỏ qua một object hoặc array bằng skipChildren()

Khi parser đang ở `START_OBJECT` hoặc `START_ARRAY`, `skipChildren()` bỏ qua toàn bộ nội dung lồng nhau và dừng ở token kết thúc tương ứng.

Ví dụ:

```json
{
  "id": 42,
  "debug": {
    "request": {
      "headers": {
        "trace": "abc"
      }
    }
  },
  "name": "An"
}
```

Nếu ứng dụng chỉ cần `id` và `name`, không cần duyệt mọi token bên trong `debug`:

```java
while (parser.nextToken() != null) {
    if (parser.currentToken() == JsonToken.FIELD_NAME) {
        String fieldName = parser.currentName();
        JsonToken valueToken = parser.nextToken();

        if ("debug".equals(fieldName)
                && valueToken == JsonToken.START_OBJECT) {
            parser.skipChildren();
        } else if ("id".equals(fieldName)
                && valueToken == JsonToken.VALUE_NUMBER_INT) {
            long id = parser.getLongValue();
        } else if ("name".equals(fieldName)
                && valueToken == JsonToken.VALUE_STRING) {
            String name = parser.getText();
        }
    }
}
```

Trong ví dụ này, `skipChildren()` giúp bỏ qua nhánh lớn mà không cần tạo object hoặc JsonNode cho nhánh đó. Parser tiếp tục từ sau `END_OBJECT` của nhánh `debug`.

Nếu cần kiểm tra các field con hoặc xác thực chúng, không được skip nhánh đó.

## 9. Duyệt array lớn mà không giữ toàn bộ dữ liệu trong bộ nhớ

Một trường hợp phổ biến là file JSON chứa một array rất lớn:

```json
[
  {"id": 1, "name": "An"},
  {"id": 2, "name": "Bình"},
  {"id": 3, "name": "Chi"}
]
```

Có thể đọc từng phần tử và xử lý ngay:

```java
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.databind.ObjectMapper;

try (JsonParser parser = mapper.getFactory().createParser(inputStream)) {
    if (parser.nextToken() != JsonToken.START_ARRAY) {
        throw new IllegalArgumentException("Expected a JSON array");
    }

    while (parser.nextToken() == JsonToken.START_OBJECT) {
        User user = mapper.readValue(parser, User.class);

        // Xử lý từng user rồi giải phóng tham chiếu khi không còn dùng
        process(user);
    }

    if (parser.currentToken() != JsonToken.END_ARRAY) {
        throw new IllegalArgumentException("Unexpected JSON structure");
    }
}
```

Ở đây:

1. Parser tiến đến `START_ARRAY`.
2. Mỗi lần `nextToken()`, parser tiến đến object kế tiếp.
3. `mapper.readValue(parser, User.class)` ánh xạ object hiện tại thành một User.
4. Ứng dụng xử lý user ngay rồi tiếp tục phần tử tiếp theo.
5. Khi đến `END_ARRAY`, vòng lặp kết thúc.

Cách này không cần tạo một `List<User>` chứa toàn bộ phần tử. Bộ nhớ chủ yếu phụ thuộc vào một object đang xử lý và trạng thái parser, miễn là ứng dụng không giữ lại mọi object trong `process`.

Nếu JSON array chứa primitive hoặc cấu trúc khác, cần kiểm tra token tương ứng và xử lý theo kiểu dữ liệu đó.

## 10. Duyệt array thủ công và đọc một phần object

Khi muốn tự kiểm soát từng field, có thể không dùng databind mà đọc token trực tiếp:

```java
try (JsonParser parser = mapper.getFactory().createParser(inputStream)) {
    if (parser.nextToken() != JsonToken.START_ARRAY) {
        throw new IllegalArgumentException("Expected array");
    }

    while (parser.nextToken() == JsonToken.START_OBJECT) {
        Long id = null;
        String name = null;

        while (parser.nextToken() == JsonToken.FIELD_NAME) {
            String field = parser.currentName();
            JsonToken valueToken = parser.nextToken();

            switch (field) {
                case "id" -> {
                    if (valueToken == JsonToken.VALUE_NUMBER_INT) {
                        id = parser.getLongValue();
                    } else {
                        throw new IllegalArgumentException(
                            "id must be an integer"
                        );
                    }
                }
                case "name" -> {
                    if (valueToken == JsonToken.VALUE_STRING) {
                        name = parser.getText();
                    } else {
                        throw new IllegalArgumentException(
                            "name must be a string"
                        );
                    }
                }
                default -> {
                    if (valueToken == JsonToken.START_OBJECT
                            || valueToken == JsonToken.START_ARRAY) {
                        parser.skipChildren();
                    }
                }
            }
        }

        process(id, name);
    }
}
```

Đây là cách phù hợp khi schema nhỏ, cần kiểm tra kiểu token nghiêm ngặt hoặc chỉ cần một vài field. Với DTO lớn và ổn định, databind thường dễ bảo trì hơn. Có thể kết hợp streaming parser với `readValue(parser, Type.class)` cho các object con cần ánh xạ đầy đủ.

## 11. Phân biệt parser context với object path

Một số khái niệm dễ nhầm:

- **Token hiện tại:** loại token mà parser đang đứng tại, ví dụ `VALUE_STRING`.
- **Current field name:** tên field đang chứa token hiện tại, ví dụ `name`.
- **Parsing context:** object/array hiện tại và các context cha.
- **Token location:** vị trí bắt đầu token trong tài liệu.
- **Current location:** vị trí parser đã đọc tới.
- **JSON path:** đường dẫn logic từ root tới giá trị, ví dụ `$["users"][0]["name"]`.

Không nên dùng line/column thay cho JSON path. Line/column chỉ ra vị trí ký tự trong file, trong khi path chỉ ra vị trí logic trong cấu trúc. Một JSON minified có thể chỉ có một dòng nhưng chứa hàng nghìn field; path lúc đó đặc biệt hữu ích.

## 12. Xử lý lỗi parse và lỗi cấu trúc

Parser có thể phát sinh lỗi khi JSON sai cú pháp, ví dụ thiếu dấu ngoặc, dấu phẩy sai vị trí hoặc chuỗi không đóng. Jackson thường báo `JsonParseException` cùng vị trí lỗi.

Lỗi ánh xạ khi dùng databind có thể là `JsonMappingException`. Loại exception này có thể chứa path reference để chỉ ra field hoặc index liên quan.

Ví dụ bắt lỗi. Đặt đoạn này trong một method khai báo `throws IOException` để các lỗi I/O không thuộc `JsonProcessingException` được chuyển tiếp lên tầng gọi:

```java
import com.fasterxml.jackson.core.JsonLocation;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.io.InputStream;

private static void readJson(
        ObjectMapper mapper,
        InputStream inputStream) throws IOException {

    try (JsonParser parser = mapper.getFactory().createParser(inputStream)) {
        while (parser.nextToken() != null) {
            // Xử lý token
        }
    } catch (JsonProcessingException ex) {
        JsonLocation location = ex.getLocation();

        if (location != null) {
            System.err.printf(
                "JSON error at line %d, column %d: %s%n",
                location.getLineNr(),
                location.getColumnNr(),
                ex.getOriginalMessage()
            );
        } else {
            System.err.println(ex.getOriginalMessage());
        }
    }
}
```

Nếu code xử lý token tự ném exception nghiệp vụ, hãy bổ sung path và location từ parser tại nơi phát hiện lỗi. Đừng biến mọi lỗi thành một thông báo chung như "Invalid JSON" nếu cần hỗ trợ người gửi sửa payload.

## 13. Các lưu ý khi làm việc với streaming parser

**Parser có trạng thái.** Mỗi lần gọi `nextToken()`, `nextValue()`, `nextFieldName()` hoặc `skipChildren()` đều thay đổi vị trí parser. Cần biết rõ token hiện tại trước khi gọi phương thức tiếp theo.

**Không gọi getText() cho mọi token.** Các token cấu trúc như START_OBJECT không có giá trị văn bản nghiệp vụ. Hãy kiểm tra token trước khi đọc scalar.

**Phân biệt integer và float.** Dùng `VALUE_NUMBER_INT` và `VALUE_NUMBER_FLOAT` nếu hợp đồng yêu cầu kiểu số cụ thể. Không nên ép mọi number sang double nếu cần giữ độ chính xác số nguyên lớn hoặc decimal.

**Không bỏ qua nhánh khi vẫn cần kiểm tra nó.** `skipChildren()` rất hữu ích nhưng cũng bỏ qua toàn bộ nội dung con.

**Giữ parser mở trong suốt quá trình đọc.** Không đóng parser trước khi hoàn tất. Khi dùng try-with-resources, đặt toàn bộ vòng lặp bên trong block.

**Streaming đầu vào không đồng nghĩa với bộ nhớ hằng số cho mọi ứng dụng.** Nếu code thêm mọi bản ghi vào một List hoặc cache toàn bộ kết quả, bộ nhớ vẫn tăng theo kích thước dữ liệu.

**Đặt giới hạn tài nguyên.** Với nguồn không tin cậy, cân nhắc giới hạn độ sâu lồng nhau, độ dài chuỗi, số token, kích thước request và thời gian xử lý theo yêu cầu hệ thống.

## 14. Khi nào nên dùng streaming API?

| Tình huống | Cách tiếp cận |
|---|---|
| JSON nhỏ, schema ổn định | `ObjectMapper.readValue` vào DTO |
| JSON cần truy vấn linh hoạt | `readTree` thành `JsonNode` |
| Array rất lớn, xử lý từng bản ghi | `JsonParser` + databind từng phần tử |
| Chỉ cần một vài field từ tài liệu lớn | Streaming parser và bỏ qua nhánh không cần |
| Cần báo lỗi chính xác theo vị trí | Streaming parser + parsing context + JsonLocation |
| Cần kiểm tra token trước khi bind | Streaming parser hoặc `JsonNode` |

Streaming API không phải lúc nào cũng là lựa chọn tốt nhất. Với request nhỏ và DTO rõ ràng, `ObjectMapper` ít mã hơn và dễ bảo trì hơn. Streaming phát huy lợi thế khi cần kiểm soát luồng đọc, giảm dữ liệu trung gian hoặc xử lý cấu trúc rất lớn.

## 15. Ghi nhớ

- `JsonParser` đọc JSON tuần tự và phát ra `JsonToken`; `nextToken()` di chuyển đến token kế tiếp.
- `FIELD_NAME` và value là hai token riêng; dùng `currentName()` để lấy tên field.
- `nextFieldName()` và `nextValue()` giúp viết vòng lặp object ngắn gọn hơn.
- `skipChildren()` bỏ qua toàn bộ object/array lồng nhau khi không cần xử lý nhánh đó.
- `getParsingContext()` cung cấp object/array hiện tại, tên field, index và context cha.
- `getTokenLocation()` chỉ vị trí bắt đầu token; `getCurrentLocation()` chỉ vị trí parser hiện tại.
- Kết hợp JSON path với line/column để báo lỗi dễ định vị.
- Có thể dùng `mapper.readValue(parser, Type.class)` để ánh xạ từng object trong array lớn mà không cần giữ toàn bộ danh sách.
- Streaming chỉ tiết kiệm bộ nhớ nếu ứng dụng xử lý từng phần và không tích lũy toàn bộ kết quả.

