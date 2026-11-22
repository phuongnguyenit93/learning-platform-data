# Mô hình token của JsonParser

Trong Jackson Streaming API, `JsonParser` đọc JSON theo từng bước và cung cấp cho chương trình một chuỗi **token**. Mỗi lần gọi `nextToken()`, parser tiến đến token tiếp theo trong tài liệu. Chương trình có thể kiểm tra loại token, đọc tên property hoặc giá trị hiện tại, rồi quyết định tiếp tục đọc, xử lý một phần dữ liệu hay bỏ qua cả một nhánh.

Mô hình token là nền tảng của cách đọc JSON theo luồng. Thay vì tạo toàn bộ cây `JsonNode` hoặc object graph trong bộ nhớ, parser cho phép xử lý tuần tự các cấu trúc JSON. Cách làm này hữu ích khi đọc file lớn, xử lý từng bản ghi hoặc cần kiểm soát chính xác thứ tự và kiểu dữ liệu.

## 1. JsonParser và mô hình pull parsing

`JsonParser` thuộc Jackson Core. Nó là một **pull parser**: chương trình chủ động yêu cầu token tiếp theo bằng `nextToken()`. Parser không gọi callback của ứng dụng cho từng token; ứng dụng điều khiển tiến trình đọc.

Luồng cơ bản:

```text
JSON input
    │
    ▼
JsonFactory.createParser(...)
    │
    ▼
JsonParser
    │
    ├── nextToken() ──> token hiện tại
    │                      │
    │                      ├── kiểm tra loại token
    │                      ├── đọc tên field / giá trị
    │                      ├── xử lý dữ liệu
    │                      └── skipChildren() nếu bỏ qua nhánh
    │
    └── nextToken() == null ──> hết tài liệu
```

Parser đọc đầu vào và duy trì trạng thái tại token hiện tại. Ứng dụng không cần tự tìm dấu ngoặc, dấu phẩy hoặc dấu hai chấm trong văn bản JSON; Jackson Core đã phân tích cú pháp và đưa ra token có cấu trúc.

`JsonParser` không phải một cây JSON. Nó không giữ sẵn mọi node để truy cập ngẫu nhiên. Thông thường, khi parser đã đi qua một token, muốn xử lý lại dữ liệu đó thì ứng dụng phải tự lưu giá trị cần thiết hoặc đọc lại nguồn đầu vào.

## 2. Token là gì?

**Token** là đơn vị cấu trúc hoặc giá trị mà parser phát hiện khi đọc JSON. Một token có loại xác định, ví dụ bắt đầu object, tên field, giá trị string hoặc kết thúc array.

Với JSON:

```json
{
  "name": "An",
  "age": 21,
  "active": true,
  "roles": ["ADMIN", "USER"]
}
```

Parser lần lượt cung cấp các token chính:

| Thứ tự | JsonToken | Nội dung hoặc ý nghĩa |
| ---: | --- | --- |
| 1 | `START_OBJECT` | Bắt đầu object gốc |
| 2 | `FIELD_NAME` | Tên field `name` |
| 3 | `VALUE_STRING` | Giá trị `An` |
| 4 | `FIELD_NAME` | Tên field `age` |
| 5 | `VALUE_NUMBER_INT` | Giá trị số nguyên `21` |
| 6 | `FIELD_NAME` | Tên field `active` |
| 7 | `VALUE_TRUE` | Boolean `true` |
| 8 | `FIELD_NAME` | Tên field `roles` |
| 9 | `START_ARRAY` | Bắt đầu array |
| 10 | `VALUE_STRING` | Phần tử `ADMIN` |
| 11 | `VALUE_STRING` | Phần tử `USER` |
| 12 | `END_ARRAY` | Kết thúc array |
| 13 | `END_OBJECT` | Kết thúc object gốc |

Parser không phát token riêng cho dấu phẩy, dấu hai chấm, dấu ngoặc kép hoặc khoảng trắng. Các ký hiệu cú pháp này được parser xử lý để xác định cấu trúc và ranh giới giá trị.

Tên field và giá trị của field là hai token riêng. Khi đọc object, ứng dụng thường nhận `FIELD_NAME` trước, sau đó gọi `nextToken()` lần nữa để tới token biểu diễn value.

## 3. Các nhóm JsonToken thường gặp

`JsonToken` là enum mô tả loại token hiện tại. Những token cần nhận diện khi đọc JSON thông thường gồm:

| Token | Ý nghĩa | Ví dụ JSON |
| --- | --- | --- |
| `START_OBJECT` | Bắt đầu object | `{` |
| `END_OBJECT` | Kết thúc object | `}` |
| `START_ARRAY` | Bắt đầu array | `[` |
| `END_ARRAY` | Kết thúc array | `]` |
| `FIELD_NAME` | Tên property trong object | `"username"` |
| `VALUE_STRING` | Giá trị string | `"An"` |
| `VALUE_NUMBER_INT` | Giá trị number dạng số nguyên | `42` |
| `VALUE_NUMBER_FLOAT` | Giá trị number có phần thập phân hoặc exponent | `12.5`, `1e3` |
| `VALUE_TRUE` | Boolean true | `true` |
| `VALUE_FALSE` | Boolean false | `false` |
| `VALUE_NULL` | Giá trị null | `null` |
| `VALUE_EMBEDDED_OBJECT` | Giá trị nhúng không phải token JSON văn bản thông thường | Có thể gặp khi parser xử lý biểu diễn nhị phân/giá trị mở rộng |

Với JSON chuẩn dạng văn bản, phần lớn ứng dụng sẽ xử lý các token object, array, field name và scalar. `VALUE_EMBEDDED_OBJECT` thường chỉ cần quan tâm khi dùng parser hoặc data format có hỗ trợ giá trị nhúng.

Một số parser bất đồng bộ có thể có trạng thái `NOT_AVAILABLE` khi chưa có đủ dữ liệu đầu vào để tạo token tiếp theo. Với parser đồng bộ đọc từ String, File, Reader hoặc InputStream thông thường, ứng dụng thường lặp đến khi `nextToken()` trả về `null`.

## 4. Vòng đời đọc token

Mẫu cơ bản:

```java
JsonFactory factory = new JsonFactory();

try (JsonParser parser = factory.createParser(json)) {
    JsonToken token;

    while ((token = parser.nextToken()) != null) {
        System.out.println(token);
    }
}
```

Các điểm cần nhớ:

1. `createParser` tạo parser cho nguồn dữ liệu.
2. Trước lần gọi `nextToken()` đầu tiên, parser chưa đứng trên token của tài liệu.
3. Mỗi lần gọi `nextToken()`, parser tiến đến token kế tiếp và trả về loại token đó.
4. `currentToken()` cho biết token hiện tại.
5. Khi đã đọc hết một JSON document, `nextToken()` trả về `null`.
6. Đóng parser sau khi dùng xong; try-with-resources giúp đảm bảo tài nguyên được giải phóng.

Có thể đọc một tài liệu JSON từ nhiều loại nguồn:

```java
try (JsonParser parser = factory.createParser(jsonString)) {
    // Đọc từ String
}

try (JsonParser parser = factory.createParser(jsonBytes)) {
    // Đọc từ byte[]
}

try (JsonParser parser = factory.createParser(inputStream)) {
    // Đọc từ InputStream
}

try (JsonParser parser = factory.createParser(file)) {
    // Đọc từ File
}
```

Các overload cụ thể phụ thuộc kiểu nguồn đầu vào. Khi parser được tạo từ một stream hoặc reader, hãy quản lý vòng đời nguồn dữ liệu rõ ràng và đóng tài nguyên theo đúng quyền sở hữu. Mặc định Jackson thường đóng source khi parser đóng nếu tính năng auto-close source đang bật; nếu ứng dụng cần giữ stream mở, hãy cấu hình chính sách đóng nguồn một cách tường minh.

## 5. Đọc token hiện tại

Sau khi gọi `nextToken()`, parser đứng tại token vừa trả về. Các method đọc giá trị phụ thuộc token hiện tại.

### 5.1. Đọc tên field

Khi token là `FIELD_NAME`, dùng `currentName()` để lấy tên property:

```java
try (JsonParser parser = factory.createParser(json)) {
    while (parser.nextToken() != null) {
        if (parser.currentToken() == JsonToken.FIELD_NAME) {
            String fieldName = parser.currentName();
            System.out.println(fieldName);
        }
    }
}
```

Tên field không phải giá trị string thông thường trong luồng token. Nó được biểu diễn bằng `FIELD_NAME`. Có thể dùng `getText()` ở token field name để lấy tên, nhưng `currentName()` diễn đạt rõ mục đích truy cập tên property hiện tại.

### 5.2. Đọc giá trị string

Khi token là `VALUE_STRING`:

```java
if (parser.currentToken() == JsonToken.VALUE_STRING) {
    String value = parser.getText();
}
```

`getText()` trả về nội dung dạng text của token hiện tại. Với string JSON, parser đã xử lý các escape sequence theo cú pháp JSON, vì vậy ứng dụng nhận giá trị string đã được giải escape.

Ví dụ JSON:

```json
{"message": "Line 1\nLine 2"}
```

Giá trị trả về từ `getText()` chứa ký tự xuống dòng thực tế tương ứng với escape `\n` trong JSON.

### 5.3. Đọc số

Với token số nguyên, có thể dùng:

```java
if (parser.currentToken() == JsonToken.VALUE_NUMBER_INT) {
    long value = parser.getLongValue();
}
```

Với số thập phân:

```java
if (parser.currentToken() == JsonToken.VALUE_NUMBER_FLOAT) {
    BigDecimal value = parser.getDecimalValue();
}
```

Một số method số thường dùng:

| Method | Kết quả |
| --- | --- |
| `getIntValue()` | Đọc giá trị số nguyên thành int |
| `getLongValue()` | Đọc giá trị số nguyên thành long |
| `getBigIntegerValue()` | Đọc số nguyên lớn thành BigInteger |
| `getFloatValue()` | Đọc giá trị số thành float |
| `getDoubleValue()` | Đọc giá trị số thành double |
| `getDecimalValue()` | Đọc giá trị số thập phân thành BigDecimal |
| `getNumberValue()` | Lấy biểu diễn Number phù hợp với token và parser |

Chỉ gọi accessor phù hợp sau khi đã xác định token là số. `getIntValue()` hoặc `getLongValue()` có thể phát sinh lỗi nếu token không phải number hoặc giá trị nằm ngoài miền biểu diễn của kiểu đích.

Nếu cần giữ độ chính xác thập phân, dùng `getDecimalValue()` hoặc kiểu số phù hợp. Không đọc tiền tệ qua double rồi mới chuyển sang BigDecimal vì có thể đã mất độ chính xác.

### 5.4. Đọc boolean và null

Boolean được phân biệt bằng token:

```java
switch (parser.currentToken()) {
    case VALUE_TRUE -> {
        boolean value = true;
    }
    case VALUE_FALSE -> {
        boolean value = false;
    }
    case VALUE_NULL -> {
        // JSON null
    }
    default -> {
        // Token không thuộc nhóm boolean/null.
    }
}
```

`VALUE_TRUE` và `VALUE_FALSE` đã cho biết giá trị boolean. Với `VALUE_NULL`, không có nội dung scalar cần lấy bằng `getText()` để thay thế cho null.

## 6. Ví dụ in toàn bộ chuỗi token

Ví dụ sau in loại token và giá trị liên quan:

```java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;

public class TokenTraceExample {

    public static void main(String[] args) throws Exception {
        String json = """
            {
              "name": "An",
              "age": 21,
              "active": true,
              "roles": ["ADMIN", "USER"]
            }
            """;

        JsonFactory factory = new JsonFactory();

        try (JsonParser parser = factory.createParser(json)) {
            JsonToken token;

            while ((token = parser.nextToken()) != null) {
                System.out.print(token);

                if (token == JsonToken.FIELD_NAME
                        || token == JsonToken.VALUE_STRING
                        || token == JsonToken.VALUE_NUMBER_INT) {
                    System.out.print(" -> " + parser.getText());
                }

                System.out.println();
            }
        }
    }
}
```

Output có dạng:

```text
START_OBJECT
FIELD_NAME -> name
VALUE_STRING -> An
FIELD_NAME -> age
VALUE_NUMBER_INT -> 21
FIELD_NAME -> active
VALUE_TRUE
FIELD_NAME -> roles
START_ARRAY
VALUE_STRING -> ADMIN
VALUE_STRING -> USER
END_ARRAY
END_OBJECT
```

Ví dụ cho thấy parser cung cấp cấu trúc theo thứ tự xuất hiện trong JSON. Khi gặp array, parser phát token bắt đầu, các phần tử, rồi token kết thúc. Ứng dụng có thể dùng các token này để xử lý dữ liệu tuần tự.

## 7. Hiểu trạng thái parser khi đọc object

Khi parser đọc object, chuỗi token có quy luật:

```text
START_OBJECT
  FIELD_NAME
  VALUE hoặc START_OBJECT hoặc START_ARRAY
  FIELD_NAME
  VALUE hoặc START_OBJECT hoặc START_ARRAY
END_OBJECT
```

Với mỗi `FIELD_NAME`, token tiếp theo bắt đầu giá trị của property đó. Giá trị có thể là scalar, object lồng nhau hoặc array.

Ví dụ:

```json
{
  "id": 10,
  "address": {
    "city": "Da Nang"
  }
}
```

Token quan trọng:

```text
START_OBJECT
FIELD_NAME(id)
VALUE_NUMBER_INT(10)
FIELD_NAME(address)
START_OBJECT
FIELD_NAME(city)
VALUE_STRING(Da Nang)
END_OBJECT
END_OBJECT
```

Object lồng nhau tạo một cặp token bắt đầu/kết thúc riêng. Khi parser đã đọc xong object con, token tiếp theo thuộc cấp cha.

### 7.1. Đọc một object theo tên field

Ví dụ đọc một DTO đơn giản bằng token:

```java
public record UserSummary(long id, String name) {}

static UserSummary readUser(JsonParser parser) throws IOException {
    if (parser.currentToken() != JsonToken.START_OBJECT) {
        throw new IOException("Expected a JSON object");
    }

    Long id = null;
    String name = null;

    JsonToken token;
    while ((token = parser.nextToken()) != JsonToken.END_OBJECT) {
        if (token == null) {
            throw new IOException("Unexpected end of input");
        }

        if (token != JsonToken.FIELD_NAME) {
            throw new IOException("Expected a field name");
        }

        String fieldName = parser.currentName();
        JsonToken valueToken = parser.nextToken();

        if (valueToken == null) {
            throw new IOException("Missing value for " + fieldName);
        }

        switch (fieldName) {
            case "id" -> {
                if (valueToken != JsonToken.VALUE_NUMBER_INT) {
                    throw new IOException("id must be an integer");
                }
                id = parser.getLongValue();
            }
            case "name" -> {
                if (valueToken != JsonToken.VALUE_STRING) {
                    throw new IOException("name must be a string");
                }
                name = parser.getText();
            }
            default -> parser.skipChildren();
        }
    }

    if (id == null || name == null) {
        throw new IOException("Required user fields are missing");
    }

    return new UserSummary(id, name);
}
```

Method trên giả định parser đã được đặt tại `START_OBJECT` của user. Nó đọc từng field, kiểm tra token value, rồi tạo record sau khi đã có dữ liệu cần thiết.

Đây là ví dụ xử lý thủ công. Nếu cấu trúc object ổn định và không cần kiểm soát ở mức token, `ObjectMapper.readValue` vào DTO thường ngắn gọn và ít code hơn.

## 8. Đọc array và các phần tử lồng nhau

Array có chuỗi token:

```text
START_ARRAY
  VALUE hoặc START_OBJECT hoặc START_ARRAY
  VALUE hoặc START_OBJECT hoặc START_ARRAY
END_ARRAY
```

Ví dụ JSON:

```json
[
  {"id": 1, "name": "An"},
  {"id": 2, "name": "Binh"}
]
```

Parser lần lượt phát `START_ARRAY`, từng object con với cặp `START_OBJECT`/`END_OBJECT`, rồi `END_ARRAY`.

Có thể đọc từng phần tử và xử lý ngay, không cần giữ toàn bộ danh sách trong bộ nhớ:

```java
try (JsonParser parser = factory.createParser(inputStream)) {
    if (parser.nextToken() != JsonToken.START_ARRAY) {
        throw new IOException("Expected a JSON array");
    }

    while (parser.nextToken() != JsonToken.END_ARRAY) {
        if (parser.currentToken() != JsonToken.START_OBJECT) {
            throw new IOException("Expected an object item");
        }

        UserSummary user = readUser(parser);
        processUser(user);
    }
}
```

Trong ví dụ này, `readUser` kết thúc khi parser ở `END_OBJECT` của phần tử hiện tại. Vòng lặp bên ngoài tiếp tục gọi `nextToken()` để chuyển sang phần tử kế tiếp hoặc `END_ARRAY`.

Với file chứa hàng triệu phần tử, cách xử lý từng phần tử như vậy có thể giảm đáng kể bộ nhớ so với deserialize cả array thành `List<UserSummary>`. Ứng dụng vẫn cần lưu ý bộ nhớ mà logic `processUser` sử dụng.

## 9. Bỏ qua một object hoặc array con bằng skipChildren

Khi parser đang ở `START_OBJECT` hoặc `START_ARRAY`, method `skipChildren()` có thể nhảy qua toàn bộ cấu trúc con cho đến token kết thúc tương ứng.

Ví dụ:

```json
{
  "id": 10,
  "debug": {
    "request": {
      "headers": ["A", "B"],
      "payload": {"raw": true}
    }
  },
  "name": "An"
}
```

Nếu ứng dụng không cần property `debug`, không cần tự duyệt từng token bên trong:

```java
while (parser.nextToken() != JsonToken.END_OBJECT) {
    String fieldName = parser.currentName();
    JsonToken valueToken = parser.nextToken();

    if ("id".equals(fieldName)) {
        long id = parser.getLongValue();
    } else if ("name".equals(fieldName)) {
        String name = parser.getText();
    } else {
        parser.skipChildren();
    }
}
```

Khi token value là object hoặc array, `skipChildren()` đưa parser đến token kết thúc của nhánh đó. Vòng lặp bên ngoài sau đó gọi `nextToken()` để tiếp tục tại property tiếp theo của object cha.

Nếu token hiện tại là scalar, `skipChildren()` không có nhánh con để bỏ qua. Tuy nhiên, khi code cần rõ ràng hơn, có thể chỉ gọi method này khi token là `START_OBJECT` hoặc `START_ARRAY`.

Đây là một kỹ thuật quan trọng để xử lý schema lớn nhưng chỉ quan tâm một vài field.

## 10. Đọc một cấu trúc lồng nhau có chọn lọc

Giả sử payload:

```json
{
  "eventId": "evt-100",
  "type": "USER_CREATED",
  "payload": {
    "user": {
      "id": 42,
      "name": "An"
    },
    "debug": {
      "rawHeaders": ["x-a", "x-b"]
    }
  },
  "metadata": {
    "source": "identity-service"
  }
}
```

Ứng dụng chỉ cần `eventId`, `payload.user` và bỏ qua `debug` cùng metadata. Có thể đọc tuần tự, gọi helper cho từng object con và dùng `skipChildren()` cho nhánh không cần.

Một quy tắc quan trọng: helper đọc object nên có hợp đồng rõ ràng về vị trí parser khi gọi và khi trả về. Ví dụ:

- Khi gọi helper, parser đang ở `START_OBJECT`.
- Khi helper kết thúc, parser đang ở `END_OBJECT` tương ứng.
- Helper không đọc vượt sang token kế tiếp của object cha.

Quy ước này giúp ghép các hàm parser lồng nhau mà không bỏ mất token hoặc xử lý trùng một field.

Khi cấu trúc có nhiều nhánh và quy tắc phức tạp, hãy cân nhắc tách thành các method như `readEnvelope`, `readPayload`, `readUser`. Mỗi method xử lý đúng một cấp cấu trúc và mô tả rõ vị trí parser đầu/cuối.

## 11. Đọc giá trị và vị trí trong nguồn bằng JsonLocation

Parser có thể cung cấp vị trí token để hỗ trợ thông báo lỗi và debug:

- `getTokenLocation()`: vị trí bắt đầu của token hiện tại.
- `currentLocation()`: vị trí hiện tại của parser sau khi đọc token.
- `getParsingContext()`: thông tin ngữ cảnh cấu trúc hiện tại, ví dụ đang ở object/array nào.

Ví dụ:

```java
JsonToken token = parser.nextToken();

JsonLocation tokenLocation = parser.getTokenLocation();
JsonLocation currentLocation = parser.currentLocation();

System.out.println("Token: " + token);
System.out.println("Starts at: " + tokenLocation);
System.out.println("Current at: " + currentLocation);
```

Thông tin vị trí thường bao gồm offset và dòng/cột tùy loại nguồn. Nó hữu ích khi file JSON lớn và parser báo lỗi tại một vị trí cụ thể.

Không nên giả định mọi nguồn đều có số dòng/cột giống nhau. Với byte stream, encoding và buffer có thể ảnh hưởng cách hiển thị vị trí. Hãy dùng thông tin location để định vị tương đối và kết hợp với exception message.

## 12. Token text, giá trị đã parse và coercion

`getText()` trả về dạng text của token hiện tại. Với number, nó thường thể hiện phần văn bản số trong input. Các accessor như `getLongValue()` hoặc `getDecimalValue()` trả về giá trị đã được parser chuyển thành kiểu số.

Ví dụ:

```json
{"amount": 1250.75}
```

Có thể đọc:

```java
if (parser.currentToken() == JsonToken.VALUE_NUMBER_FLOAT) {
    String rawNumberText = parser.getText();
    BigDecimal amount = parser.getDecimalValue();
}
```

Sự khác biệt:

- `getText()` hữu ích khi cần dạng chữ của token.
- `getNumberValue()` trả về Number.
- `getDecimalValue()` hữu ích khi cần số thập phân chính xác.
- `getLongValue()` phù hợp với số nguyên trong miền long.

Đừng dùng accessor kiểu số để đọc token string rồi kỳ vọng parser tự thực hiện mọi coercion như Databind. Ở tầng streaming, hãy kiểm tra loại token và quyết định cách chuyển đổi rõ ràng. Nếu ứng dụng muốn chấp nhận string số, có thể đọc `getText()` rồi parse bằng API Java phù hợp, đồng thời xử lý lỗi định dạng.

## 13. Các method tiện ích thường gặp

Ngoài `nextToken()` và `getText()`, `JsonParser` cung cấp một số method hỗ trợ:

| Method | Công dụng |
| --- | --- |
| `currentToken()` | Lấy loại token hiện tại |
| `nextToken()` | Tiến đến token tiếp theo |
| `currentName()` | Lấy tên field hiện tại nếu có |
| `getText()` | Lấy nội dung dạng text của token |
| `getValueAsString()` | Lấy giá trị theo dạng String với quy tắc chuyển đổi tiện ích |
| `getValueAsInt()` | Lấy giá trị theo dạng int với coercion/default của API |
| `getValueAsBoolean()` | Lấy giá trị theo dạng boolean |
| `getNumberValue()` | Lấy giá trị Number |
| `getDecimalValue()` | Lấy BigDecimal từ token số |
| `getTokenLocation()` | Lấy vị trí bắt đầu token |
| `currentLocation()` | Lấy vị trí parser hiện tại |
| `getParsingContext()` | Lấy ngữ cảnh object/array hiện tại |
| `skipChildren()` | Bỏ qua object/array con hiện tại |
| `nextFieldName()` | Tiện ích đọc nhanh tên field tiếp theo trong một số vòng lặp |
| `nextTextValue()` | Tiện ích chuyển tới token kế và lấy text nếu token là string |

Các method `getValueAs...` có thể áp dụng quy tắc chuyển đổi và giá trị mặc định tiện ích. Khi cần validation nghiêm ngặt, nên kiểm tra `currentToken()` trước rồi gọi accessor cụ thể thay vì chấp nhận mọi kiểu đầu vào.

### 13.1. nextFieldName và nextTextValue

Trong vòng lặp tối ưu cho một cấu trúc đã biết, có thể dùng method tiện ích:

```java
if (parser.nextToken() == JsonToken.START_OBJECT) {
    while (parser.nextToken() != JsonToken.END_OBJECT) {
        String fieldName = parser.currentName();

        if (parser.nextToken() == JsonToken.VALUE_STRING) {
            String value = parser.getText();
        } else {
            parser.skipChildren();
        }
    }
}
```

`nextFieldName()` có thể giúp so sánh tên field mà không cần lấy String riêng trong một số pattern đọc. `nextTextValue()` tiến đến token kế tiếp và trả text khi token đó là string. Đây là các tiện ích tối ưu và rút gọn code; khi mới học, vòng lặp `nextToken()` tường minh thường dễ hiểu hơn.

## 14. Kiểm tra JSON root và token đầu tiên

Không phải tài liệu nào cũng bắt đầu bằng object. JSON root có thể là object, array hoặc scalar. Hãy kiểm tra token đầu tiên trước khi xử lý:

```java
try (JsonParser parser = factory.createParser(json)) {
    JsonToken rootToken = parser.nextToken();

    if (rootToken == null) {
        throw new IOException("Empty JSON input");
    }

    switch (rootToken) {
        case START_OBJECT -> readRootObject(parser);
        case START_ARRAY -> readRootArray(parser);
        case VALUE_STRING -> readRootString(parser.getText());
        case VALUE_NUMBER_INT -> readRootNumber(parser.getLongValue());
        case VALUE_NUMBER_FLOAT -> readRootDecimal(parser.getDecimalValue());
        case VALUE_TRUE -> readRootBoolean(true);
        case VALUE_FALSE -> readRootBoolean(false);
        case VALUE_NULL -> handleNullRoot();
        default -> throw new IOException("Unsupported root token: " + rootToken);
    }
}
```

Sau khi helper xử lý object hoặc array, parser cần ở đúng token kết thúc của root. Nếu hợp đồng yêu cầu chỉ một JSON value, có thể gọi `nextToken()` thêm lần nữa để kiểm tra không còn token dữ liệu phía sau. Với Databind, có feature `FAIL_ON_TRAILING_TOKENS`; khi dùng Core trực tiếp, ứng dụng tự kiểm tra phần còn lại.

Không nên mặc định root luôn là `START_OBJECT` nếu nguồn dữ liệu có thể trả array hoặc scalar.

## 15. Parser và JsonGenerator

`JsonParser` là API đọc token. API ghi token tương ứng là `JsonGenerator`.

| API | Vai trò |
| --- | --- |
| `JsonParser` | Đọc JSON và cung cấp token theo thứ tự |
| `JsonGenerator` | Phát token để ghi JSON |
| `JsonFactory` | Tạo parser và generator |

Ví dụ generator:

```java
JsonFactory factory = new JsonFactory();

try (JsonGenerator generator = factory.createGenerator(outputStream)) {
    generator.writeStartObject();
    generator.writeNumberField("id", 42);
    generator.writeStringField("name", "An");
    generator.writeBooleanField("active", true);
    generator.writeEndObject();
}
```

Kết quả là JSON object được ghi ra output stream. Generator giúp ứng dụng kiểm soát thứ tự field và giá trị mà không cần dựng DTO hoặc nối chuỗi JSON thủ công.

Trong một pipeline streaming, ứng dụng có thể đọc token từ parser, chọn lọc hoặc biến đổi rồi ghi token tương ứng sang generator. Cách này có thể xử lý dữ liệu lớn mà không tạo toàn bộ tree hoặc object graph.

## 16. Streaming API và Data Binding

Cả streaming API và databind đều có chỗ dùng riêng:

| Tiêu chí | Streaming với JsonParser | Data Binding với ObjectMapper |
| --- | --- | --- |
| Đơn vị xử lý | Token | Object/collection/giá trị Java |
| Kiểm soát | Rất chi tiết | Cao ở mức kiểu dữ liệu |
| Code cần viết | Nhiều hơn, tự quản lý trạng thái | Thường ít hơn |
| Bộ nhớ | Có thể xử lý tuần tự, giữ ít dữ liệu | Thường tạo object graph cho phần được bind |
| Phù hợp | File lớn, chọn lọc field, xử lý record tuần tự | DTO ổn định, request/response, cấu trúc đã biết |
| Rủi ro | Dễ sai khi quản lý token/nesting | Cần mô hình kiểu và cấu hình phù hợp |

Không phải cứ dùng `InputStream` là đã dùng streaming token. Ví dụ `mapper.readValue(inputStream, List.class)` vẫn deserialize thành collection trong bộ nhớ. Muốn xử lý token tuần tự, ứng dụng phải làm việc trực tiếp với `JsonParser` hoặc một API iterator có hành vi streaming phù hợp.

Có thể kết hợp hai tầng: dùng parser tìm một object con trong file lớn, sau đó dùng `ObjectMapper` để bind phần object đó thành DTO nếu cần. Hãy chọn ranh giới sao cho vừa kiểm soát bộ nhớ vừa giữ code dễ hiểu.

## 17. Lỗi thường gặp khi đọc token

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `nextToken()` trả null ngay | Input rỗng hoặc parser đã ở cuối tài liệu | Kiểm tra nguồn và vị trí parser |
| Đọc nhầm tên field thành value | Quên rằng `FIELD_NAME` và value là hai token riêng | Gọi `nextToken()` sau field name |
| Gọi `getLongValue()` trên token string | Không kiểm tra loại token trước | Kiểm tra `VALUE_NUMBER_INT` hoặc parse text tường minh |
| Bỏ qua nhầm field kế tiếp | Helper đọc vượt khỏi cấu trúc được giao | Quy định rõ token đầu/cuối của từng helper |
| Vòng lặp array kết thúc sai | Không xử lý `END_ARRAY` hoặc `END_OBJECT` đúng cấp | Theo dõi cặp start/end tương ứng |
| Đọc object lồng nhau làm mất đồng bộ | Không xử lý token kết thúc của object con | Để helper kết thúc đúng tại END_OBJECT con |
| Dữ liệu không cần thiết vẫn bị duyệt | Tự lặp qua mọi token con | Dùng `skipChildren()` cho nhánh không cần |
| Parser báo lỗi cú pháp | JSON không hợp lệ hoặc parser feature không phù hợp | Đọc exception và location |
| File lớn vẫn dùng nhiều bộ nhớ | Ứng dụng tích lũy mọi kết quả vào List/Map | Xử lý từng record và giải phóng tham chiếu sau khi dùng |
| Parser hoặc stream không được đóng | Không quản lý resource | Dùng try-with-resources và xác định quyền sở hữu source |

Một quy tắc hữu ích là viết helper theo hợp đồng token. Ví dụ `readUser(parser)` nhận parser tại `START_OBJECT` và trả về khi parser đang ở `END_OBJECT` tương ứng. Quy ước này làm code lồng nhau dễ kiểm soát hơn.

## 18. Bài thực hành tổng hợp

Tạo một JSON array chứa nhiều user:

```json
[
  {
    "id": 1,
    "name": "An",
    "active": true,
    "roles": ["ADMIN", "EDITOR"],
    "debug": {"trace": "a-1"}
  },
  {
    "id": 2,
    "name": "Binh",
    "active": false,
    "roles": ["READER"],
    "debug": {"trace": "b-2"}
  }
]
```

Thực hiện:

1. Tạo `JsonFactory` và `JsonParser` từ chuỗi JSON.
2. In tất cả token bằng `nextToken()`.
3. Ghi lại thứ tự `START_ARRAY`, `START_OBJECT`, `FIELD_NAME`, value và token kết thúc.
4. Đọc riêng `id`, `name` và `active` cho từng user.
5. Duyệt array `roles` và lấy từng string.
6. Dùng `skipChildren()` để bỏ qua object `debug`.
7. Tách helper `readUser` và quy định rõ vị trí parser khi gọi/trả về.
8. Ghi location của token khi gặp giá trị sai kiểu.
9. Thử input sai cú pháp và quan sát exception.
10. Thử root object, root scalar và input rỗng để kiểm tra logic root token.
11. Ghi lại kết quả qua `JsonGenerator` vào OutputStream.
12. So sánh với cách đọc toàn bộ array thành `List<UserDto>` bằng `ObjectMapper`.

Bài thực hành hoàn thành khi có thể dự đoán chuỗi token từ JSON, đọc đúng từng cấp cấu trúc và xử lý một phần tử mà không cần tạo toàn bộ danh sách trong bộ nhớ.

## 19. Nguyên tắc ghi nhớ

- `JsonParser` là pull parser của Jackson Core: ứng dụng gọi `nextToken()` để yêu cầu token kế tiếp.
- Token mô tả cấu trúc như object/array, tên field và giá trị scalar.
- `FIELD_NAME` và value là hai token riêng trong object.
- `START_OBJECT`/`END_OBJECT` và `START_ARRAY`/`END_ARRAY` xác định ranh giới cấu trúc lồng nhau.
- `currentToken()` cho biết token hiện tại; `nextToken()` tiến parser và trả null khi hết tài liệu đồng bộ.
- Dùng accessor phù hợp với token; kiểm tra kiểu trước khi đọc số hoặc string.
- `skipChildren()` giúp bỏ qua cả object/array con khi không cần xử lý.
- `getTokenLocation()` và `currentLocation()` hỗ trợ định vị lỗi.
- `JsonParser` đọc token; `JsonGenerator` ghi token; cả hai được tạo từ `JsonFactory`.
- Streaming token có thể tiết kiệm bộ nhớ, nhưng ứng dụng phải quản lý trạng thái và không tích lũy toàn bộ kết quả.
- `ObjectMapper.readValue(InputStream, List.class)` vẫn là data binding; chỉ dùng `JsonParser` trực tiếp mới cho phép xử lý từng token theo ý muốn.

Khi làm việc với mô hình token, hãy luôn xác định parser đang đứng ở token nào, token tiếp theo thuộc cấp cấu trúc nào và helper cần kết thúc ở đâu. Nắm được trạng thái đó là nền tảng để đọc JSON lồng nhau chính xác và xây dựng pipeline streaming có thể kiểm soát.
