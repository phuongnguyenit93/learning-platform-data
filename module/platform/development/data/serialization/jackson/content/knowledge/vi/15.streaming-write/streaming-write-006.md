# Sao chép token hoặc một cấu trúc từ parser sang generator

Jackson Core cho phép chuyển dữ liệu trực tiếp từ `JsonParser` sang `JsonGenerator`. Thay vì đọc toàn bộ JSON thành một object Java hoặc `JsonNode`, ứng dụng có thể lấy token từ nguồn và ghi token tương ứng sang đích.

Hai phương thức quan trọng nhất là:

- `JsonGenerator.copyCurrentEvent(parser)`: sao chép đúng token mà parser đang đứng tại.
- `JsonGenerator.copyCurrentStructure(parser)`: sao chép token hiện tại cùng toàn bộ cấu trúc con nếu token đó mở đầu object hoặc array.

Cách làm này phù hợp khi chuyển tiếp JSON giữa các nguồn, tách một nhánh dữ liệu, bỏ qua trường không cần thiết hoặc biến đổi một vài giá trị trong tài liệu lớn. Điều quan trọng là hiểu parser đang đứng ở token nào, phương thức sao chép làm parser di chuyển ra sao và generator đang ở trạng thái cấu trúc nào.

## 1. Parser và generator đảm nhiệm hai chiều khác nhau

Trong Jackson Core:

- `JsonParser` đọc JSON từ nguồn như String, file, byte array hoặc InputStream.
- `JsonGenerator` ghi JSON ra đích như OutputStream, Writer hoặc một nguồn ký tự khác.
- `JsonFactory` tạo parser và generator.

Luồng sao chép cơ bản:

```text
JSON source
    |
    v
JsonParser
    |
    | current token / current structure
    v
JsonGenerator
    |
    v
JSON destination
```

Parser và generator hoạt động độc lập. Parser biết token đang đọc; generator biết đang ghi ở root, trong object hay trong array. Khi sao chép, ứng dụng phải giữ cho các thao tác đọc và ghi tương ứng với nhau để tạo ra một tài liệu JSON hợp lệ.

Ví dụ tạo parser và generator:

```java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.core.JsonParser;

JsonFactory factory = new JsonFactory();

try (JsonParser parser = factory.createParser(inputStream);
     JsonGenerator generator = factory.createGenerator(outputStream)) {
    // Đọc từ parser và ghi sang generator
}
```

Đóng parser/generator bằng try-with-resources giúp giải phóng tài nguyên. Generator thường flush khi đóng; nếu cần dữ liệu được đẩy ra đích trước khi kết thúc, có thể gọi `flush()` sau khi ghi xong.

## 2. Sao chép một token bằng copyCurrentEvent()

`copyCurrentEvent(parser)` ghi token hiện tại của parser sang generator. Phương thức này không tự đọc token kế tiếp cho parser. Ứng dụng vẫn chịu trách nhiệm gọi `nextToken()` để di chuyển.

Ví dụ sao chép toàn bộ token của một tài liệu:

```java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;

JsonFactory factory = new JsonFactory();

try (JsonParser parser = factory.createParser(inputStream);
     JsonGenerator generator = factory.createGenerator(outputStream)) {

    JsonToken token;

    while ((token = parser.nextToken()) != null) {
        generator.copyCurrentEvent(parser);
    }
}
```

Nếu nguồn là:

```json
{
  "id": 42,
  "name": "An",
  "active": true
}
```

thì generator ghi ra một JSON document có cùng cấu trúc và giá trị:

```json
{"id":42,"name":"An","active":true}
```

Đầu ra có thể khác khoảng trắng hoặc cách trình bày vì generator chịu trách nhiệm định dạng. Nội dung JSON vẫn tương đương về cấu trúc và giá trị.

### 2.1. copyCurrentEvent không tự sao chép các token con

Giả sử parser đang ở `START_OBJECT`. Gọi:

```java
generator.copyCurrentEvent(parser);
```

chỉ ghi token `START_OBJECT`. Nó không tự duyệt các field và giá trị bên trong object. Ứng dụng phải tiếp tục đọc rồi sao chép từng token, bao gồm `END_OBJECT`.

Tương tự:

- Sao chép `START_ARRAY` không tự sao chép các phần tử.
- Sao chép `FIELD_NAME` chỉ ghi tên field, chưa ghi giá trị.
- Sao chép `VALUE_STRING`, `VALUE_NUMBER_INT`, `VALUE_TRUE` hoặc `VALUE_NULL` ghi một giá trị scalar tương ứng.

Vì vậy, `copyCurrentEvent()` phù hợp khi muốn kiểm soát từng token hoặc cần biến đổi một phần dữ liệu. Nếu muốn sao chép nguyên một nhánh lồng nhau, `copyCurrentStructure()` thường gọn hơn.

## 3. Sao chép toàn bộ cấu trúc bằng copyCurrentStructure()

`copyCurrentStructure(parser)` sao chép token hiện tại và toàn bộ nội dung con nếu token hiện tại là object hoặc array. Nó xử lý đệ quy các field, giá trị và cấu trúc lồng nhau.

Ví dụ:

```java
JsonToken first = parser.nextToken();

if (first != null) {
    generator.copyCurrentStructure(parser);
}
```

Nếu parser đang ở `START_OBJECT`, generator nhận toàn bộ object, bao gồm mọi object/array lồng nhau và token kết thúc tương ứng. Nếu parser đang ở scalar token, chỉ giá trị scalar đó được sao chép.

Ví dụ nguồn:

```json
{
  "user": {
    "id": 42,
    "roles": ["ADMIN", "USER"]
  }
}
```

Khi parser đứng tại `START_OBJECT` của root, `copyCurrentStructure(parser)` ghi toàn bộ cây JSON vào generator.

### 3.1. Vị trí parser sau khi sao chép

Đây là điểm quan trọng khi kết hợp với vòng lặp đọc:

- Nếu token hiện tại là scalar, parser vẫn ở token scalar đó.
- Nếu token hiện tại là `START_OBJECT` hoặc `START_ARRAY`, parser được đưa đến token kết thúc tương ứng (`END_OBJECT` hoặc `END_ARRAY`) sau khi toàn bộ cấu trúc đã được sao chép.
- Nếu token hiện tại là `FIELD_NAME`, phương thức xử lý cả tên field và giá trị của nó; parser tiến đến value và nếu value là container thì kết thúc tại token đóng container đó.

Do parser đã được di chuyển qua cấu trúc con, không gọi thêm `nextToken()` cho từng token bên trong cấu trúc vừa sao chép. Chỉ gọi tiếp để đến token sau cấu trúc đó.

Ví dụ sao chép từng giá trị root khi nguồn có nhiều root value:

```java
JsonToken token;

while ((token = parser.nextToken()) != null) {
    generator.copyCurrentStructure(parser);
}
```

Mẫu này có thể hữu ích với luồng chứa nhiều JSON value nối tiếp nhau, nếu định dạng nguồn và cấu hình parser cho phép nhiều root value. Với một JSON document thông thường, chỉ có một root value.

## 4. Sao chép một object hoặc array lồng nhau

Có thể dùng `copyCurrentStructure()` để sao chép một nhánh cụ thể trong object ngoài.

Ví dụ chỉ muốn giữ trường `payload`:

```json
{
  "requestId": "req-123",
  "debug": {
    "trace": "abc"
  },
  "payload": {
    "user": {
      "id": 42,
      "name": "An"
    },
    "roles": ["ADMIN", "USER"]
  }
}
```

Ta đọc object ngoài, ghi tên field cần giữ, sau đó sao chép toàn bộ value của field đó:

```java
try (JsonParser parser = factory.createParser(inputStream);
     JsonGenerator generator = factory.createGenerator(outputStream)) {

    if (parser.nextToken() != JsonToken.START_OBJECT) {
        throw new IllegalArgumentException("Expected a JSON object");
    }

    generator.writeStartObject();

    while (parser.nextToken() == JsonToken.FIELD_NAME) {
        String fieldName = parser.currentName();
        JsonToken valueToken = parser.nextToken();

        if ("payload".equals(fieldName)) {
            generator.writeFieldName(fieldName);
            generator.copyCurrentStructure(parser);
        } else {
            parser.skipChildren();
        }
    }

    if (parser.currentToken() != JsonToken.END_OBJECT) {
        throw new IllegalArgumentException("Incomplete JSON object");
    }

    generator.writeEndObject();
}
```

Kết quả chỉ còn:

```json
{
  "payload": {
    "user": {
      "id": 42,
      "name": "An"
    },
    "roles": ["ADMIN", "USER"]
  }
}
```

Ở ví dụ này:

1. Parser đọc đến tên field.
2. Nếu là `payload`, generator ghi field name rồi sao chép nguyên cấu trúc value.
3. Nếu không phải `payload`, parser bỏ qua value; `skipChildren()` xử lý cả object/array lồng nhau.
4. Sau khi hết field, generator đóng object ngoài.

Với value scalar không cần `skipChildren()`; parser đang đứng ở scalar và vòng lặp sẽ gọi `nextToken()` để đi tiếp.

## 5. Phân biệt copyCurrentEvent, copyCurrentStructure và skipChildren

Ba phương thức có vai trò khác nhau:

| Phương thức | Tác động lên generator | Tác động lên parser |
|---|---|---|
| `copyCurrentEvent(parser)` | Ghi một token hiện tại | Không tự di chuyển parser |
| `copyCurrentStructure(parser)` | Ghi token hiện tại và toàn bộ value/container con | Tiến qua cấu trúc được sao chép; với container dừng ở token đóng tương ứng |
| `skipChildren()` | Không ghi gì | Bỏ qua nội dung con của object/array hiện tại |

Ví dụ:

- Muốn sao chép từng token và tự kiểm soát: dùng `copyCurrentEvent()`.
- Muốn sao chép nguyên object/array lồng nhau: dùng `copyCurrentStructure()`.
- Muốn loại bỏ một nhánh khỏi đầu ra: dùng `skipChildren()` khi parser đang ở đầu container cần bỏ.

Không nhầm `skipChildren()` với sao chép. Phương thức này chỉ di chuyển parser, không tạo dữ liệu trong generator.

## 6. Sao chép và đổi tên field

Có thể đổi tên field mà vẫn giữ nguyên cấu trúc value. Đọc tên field từ parser, ghi tên mới sang generator, rồi sao chép value:

```java
if (parser.nextToken() != JsonToken.START_OBJECT) {
    throw new IllegalArgumentException("Expected object");
}

generator.writeStartObject();

while (parser.nextToken() == JsonToken.FIELD_NAME) {
    String sourceName = parser.currentName();
    JsonToken valueToken = parser.nextToken();

    String targetName = "full_name".equals(sourceName)
        ? "display_name"
        : sourceName;

    generator.writeFieldName(targetName);
    generator.copyCurrentStructure(parser);
}

generator.writeEndObject();
```

Nguồn:

```json
{
  "id": 42,
  "full_name": "An"
}
```

Đầu ra:

```json
{
  "id": 42,
  "display_name": "An"
}
```

Cấu trúc của value được giữ nguyên dù value là scalar, object hay array. Nếu đổi tên field, cần bảo đảm tên đích không tạo ra key trùng nhau ngoài ý muốn. JSON cho phép một số parser đọc key trùng lặp, nhưng nhiều hệ thống xử lý chúng không nhất quán; tốt nhất là xác định chính sách cho duplicate field.

## 7. Sao chép token và biến đổi một giá trị

Nếu chỉ một giá trị cần thay đổi, có thể dùng `copyCurrentEvent()` cho các token còn lại và ghi giá trị đã biến đổi bằng generator.

Ví dụ đổi giá trị của field `name` thành chữ hoa:

```java
while ((token = parser.nextToken()) != null) {
    if (token == JsonToken.VALUE_STRING
            && "name".equals(parser.currentName())) {
        generator.writeString(
            parser.getText().toUpperCase(Locale.ROOT)
        );
    } else {
        generator.copyCurrentEvent(parser);
    }
}
```

Nguồn:

```json
{
  "name": "An",
  "city": "Hanoi"
}
```

Đầu ra:

```json
{
  "name": "AN",
  "city": "Hanoi"
}
```

Ví dụ này minh họa cách phối hợp hai cơ chế: token cần đổi được đọc và ghi thủ công; các token khác được sao chép trực tiếp.

Nếu JSON có nhiều object lồng nhau cùng chứa field tên `name`, điều kiện trên sẽ đổi tất cả các field có tên đó. Nếu chỉ muốn đổi một đường dẫn cụ thể, cần kiểm tra parsing context/path trước khi ghi.

### 7.1. Đổi kiểu giá trị cần ghi đúng token

Ví dụ chuyển một field số nguyên thành string:

```java
if (token == JsonToken.VALUE_NUMBER_INT
        && "code".equals(parser.currentName())) {
    generator.writeString(parser.getText());
} else {
    generator.copyCurrentEvent(parser);
}
```

Đầu vào:

```json
{"code": 123}
```

Đầu ra:

```json
{"code": "123"}
```

Việc này làm thay đổi kiểu JSON của field. Chỉ thực hiện khi hợp đồng đích yêu cầu string. Nếu cần bảo toàn kiểu số và độ chính xác, hãy dùng API số phù hợp thay vì đọc mọi số qua `double`.

## 8. Tự ghi cấu trúc bằng generator khi cần lọc sâu

Khi muốn lọc field trong nhiều cấp, có thể duyệt token thủ công và ghi các token cấu trúc tương ứng. Ví dụ chỉ giữ `id` và `name` bên trong mỗi object của array `users`:

```java
if (parser.nextToken() != JsonToken.START_OBJECT) {
    throw new IllegalArgumentException("Expected root object");
}

generator.writeStartObject();

while (parser.nextToken() == JsonToken.FIELD_NAME) {
    String fieldName = parser.currentName();
    JsonToken valueToken = parser.nextToken();

    if ("users".equals(fieldName)
            && valueToken == JsonToken.START_ARRAY) {
        generator.writeArrayFieldStart("users");

        while (parser.nextToken() == JsonToken.START_OBJECT) {
            generator.writeStartObject();

            while (parser.nextToken() == JsonToken.FIELD_NAME) {
                String userField = parser.currentName();
                JsonToken userValue = parser.nextToken();

                if ("id".equals(userField) || "name".equals(userField)) {
                    generator.writeFieldName(userField);
                    generator.copyCurrentStructure(parser);
                } else {
                    parser.skipChildren();
                }
            }

            generator.writeEndObject();
        }

        if (parser.currentToken() != JsonToken.END_ARRAY) {
            throw new IllegalArgumentException("Invalid users array");
        }

        generator.writeEndArray();
    } else {
        parser.skipChildren();
    }
}

generator.writeEndObject();
```

Mẫu trên minh họa cách tự quản lý các cặp object/array ở những cấp cần lọc. Với cấu trúc phức tạp hơn, nên tách logic thành hàm xử lý từng object hoặc array để dễ theo dõi parser state và generator context.

Khi parser và generator cùng đi qua cấu trúc, mỗi `writeStartObject()` phải có `writeEndObject()`, mỗi `writeStartArray()` phải có `writeEndArray()`. Mỗi field trong object cần có một value hợp lệ. Việc bỏ sót token đóng hoặc ghi value ở sai context sẽ khiến generator báo lỗi hoặc tạo JSON không hợp lệ.

## 9. Generator context và cấu trúc đầu ra

Generator duy trì trạng thái ghi hiện tại. Có thể kiểm tra bằng:

```java
JsonStreamContext context = generator.getOutputContext();

System.out.println("in object: " + context.inObject());
System.out.println("in array: " + context.inArray());
System.out.println("current name: " + context.getCurrentName());
```

Một số quy tắc cần nhớ:

- Trong object, sau `writeStartObject()`, cần ghi field name trước khi ghi value.
- Trong array, có thể ghi value trực tiếp mà không có field name.
- Sau `writeFieldName()`, cần ghi đúng một value.
- Sau `writeStartArray()`, cần ghi các phần tử rồi đóng bằng `writeEndArray()`.
- Sau `writeStartObject()`, cần ghi các field rồi đóng bằng `writeEndObject()`.

Các phương thức `copyCurrentEvent()` và `copyCurrentStructure()` tự ghi token theo context generator. Nếu generator đang ở sai context, thao tác copy có thể thất bại vì token không hợp lệ tại vị trí đó.

Ví dụ, không thể ghi `FIELD_NAME` trực tiếp ở root mà chưa mở object. Tương tự, không thể ghi `END_ARRAY` khi chưa có array đang mở.

## 10. Sao chép nhiều root value và NDJSON

Một JSON document chuẩn có một root value: object, array hoặc scalar. Tuy nhiên, một số định dạng truyền tải như NDJSON (Newline Delimited JSON) chứa nhiều JSON document riêng biệt, mỗi document trên một dòng.

Ví dụ:

```text
{"id":1,"name":"An"}
{"id":2,"name":"Bình"}
{"id":3,"name":"Chi"}
```

Có thể đọc từng root value rồi sao chép cấu trúc tương ứng:

```java
JsonToken token;

while ((token = parser.nextToken()) != null) {
    generator.copyCurrentStructure(parser);
    generator.writeRaw('\n');
}
```

Đoạn này cần được dùng với định dạng đầu ra NDJSON và cấu hình generator phù hợp. `writeRaw('\n')` ghi dấu xuống dòng thô giữa các JSON document; nó không phải một token JSON. Không dùng mẫu này nếu đầu ra phải là một JSON array chuẩn.

Nếu muốn gom nhiều root value thành một JSON array, hãy tự mở array trước vòng lặp, copy từng cấu trúc, rồi đóng array:

```java
generator.writeStartArray();

while (parser.nextToken() != null) {
    generator.copyCurrentStructure(parser);
}

generator.writeEndArray();
```

Khi nguồn là một JSON document đơn có root object, mẫu trên tạo array có một phần tử object. Chỉ dùng khi đó là chuyển đổi schema mà ứng dụng mong muốn.

## 11. Sao chép không đồng nghĩa với sao chép byte nguyên vẹn

Parser và generator làm việc ở cấp cấu trúc JSON token. Vì vậy, copy không bảo đảm byte đầu ra giống hệt byte đầu vào.

Các khác biệt có thể xuất hiện:

- Khoảng trắng và xuống dòng có thể thay đổi.
- Pretty printer có thể định dạng lại object/array.
- Escape của string có thể được ghi theo cách khác nhưng vẫn biểu diễn cùng giá trị.
- Cách biểu diễn số có thể được chuẩn hóa theo parser/generator và kiểu số được đọc.
- Encoding đầu ra có thể khác encoding nguồn nếu generator dùng Writer/OutputStream với cấu hình khác.

Ví dụ các JSON sau tương đương về giá trị:

```json
{"amount":1.0}
```

```json
{
  "amount": 1.0
}
```

Generator có thể thay đổi khoảng trắng mà không làm thay đổi dữ liệu. Nếu cần bảo toàn chữ ký số, hash hoặc byte payload chính xác, không nên parse rồi generate lại; hãy giữ byte gốc hoặc dùng một cơ chế canonicalization được định nghĩa rõ cho chữ ký.

### 11.1. Duplicate field và thứ tự field

Sao chép token theo thứ tự parser phát ra sẽ giữ thứ tự các field và có thể giữ cả tên field lặp. Tuy nhiên, JSON object thường được xử lý như tập hợp key/value và nhiều thư viện sẽ chọn một giá trị khi có key trùng lặp. Không nên dựa vào duplicate key như một cơ chế dữ liệu.

Nếu cần phát hiện duplicate field, có thể theo dõi tên field trong từng object bằng một Set khi duyệt thủ công, rồi từ chối hoặc xử lý theo chính sách rõ ràng.

## 12. Xử lý lỗi và vòng đời tài nguyên

Một thao tác copy có thể thất bại vì:

- JSON nguồn sai cú pháp.
- Parser đang không ở token hợp lệ.
- Generator đang ở context không cho phép token đó.
- InputStream/OutputStream gặp lỗi I/O.
- Ứng dụng tự bỏ sót token đóng hoặc field value.
- Dữ liệu vượt quá giới hạn tài nguyên của parser/generator.

Ví dụ method sao chép một luồng JSON:

```java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.core.JsonParser;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

private static void copy(
        JsonFactory factory,
        InputStream inputStream,
        OutputStream outputStream) throws IOException {

    try (JsonParser parser = factory.createParser(inputStream);
         JsonGenerator generator = factory.createGenerator(outputStream)) {

        while (parser.nextToken() != null) {
            generator.copyCurrentEvent(parser);
        }

        generator.flush();
    }
}
```

`JsonProcessingException` là loại lỗi chuyên biệt cho quá trình xử lý JSON. Nếu cần phân biệt nó với lỗi I/O thuần, caller có thể bắt `JsonProcessingException` trước `IOException`; nếu không cần phân loại, khai báo `throws IOException` như ví dụ trên là đủ cho Jackson 2.x.

Khi parser/generator được tạo trong try-with-resources, chúng được đóng cả khi copy phát sinh exception. Không đóng stream nguồn/đích sớm khi generator vẫn đang ghi dữ liệu.
## 13. Khi nào nên dùng từng cách?

| Nhu cầu | Cách tiếp cận |
|---|---|
| Chuyển tiếp toàn bộ JSON, không thay đổi nội dung | `copyCurrentEvent()` trong vòng lặp token hoặc `copyCurrentStructure()` cho root |
| Sao chép một object/array lồng nhau | `copyCurrentStructure()` |
| Chỉ giữ một số field | Duyệt FIELD_NAME, copy value được chọn, `skipChildren()` cho nhánh bị loại |
| Đổi tên field | Ghi field name mới rồi `copyCurrentStructure()` cho value |
| Đổi một vài giá trị scalar | Ghi token đã biến đổi, copy token còn lại |
| Kiểm tra sâu hoặc biến đổi schema lớn | Duyệt thủ công và ghi cấu trúc bằng generator |
| Bảo toàn byte chính xác | Giữ byte nguồn; không parse/generate lại |

Nếu mục tiêu chỉ là chuyển tiếp một JSON document, `copyCurrentStructure()` thường ngắn gọn. Nếu cần lọc hoặc biến đổi từng token, `copyCurrentEvent()` và các phương thức ghi thủ công cho quyền kiểm soát cao hơn.

## 14. Ghi nhớ

- `JsonParser` đọc token; `JsonGenerator` ghi token.
- `copyCurrentEvent(parser)` chỉ sao chép token hiện tại và không tự di chuyển parser.
- `copyCurrentStructure(parser)` sao chép toàn bộ object/array từ vị trí hiện tại; với container, parser kết thúc tại token đóng tương ứng.
- `skipChildren()` chỉ bỏ qua nhánh trong parser, không ghi nhánh đó ra generator.
- Khi lọc hoặc đổi tên field, ghi field name trước rồi sao chép value bằng `copyCurrentStructure()`.
- Mỗi token ghi ra phải phù hợp với generator context; đóng đầy đủ object và array.
- Copy ở cấp token không bảo toàn byte, khoảng trắng hoặc cách escape nguyên gốc.
- Dùng parser/generator trong try-with-resources và không đóng tài nguyên trước khi hoàn tất copy.

