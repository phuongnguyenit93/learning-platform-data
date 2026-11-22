# Ghi chuỗi và dữ liệu nhị phân với quy tắc thoát phù hợp

Khi ghi JSON bằng Jackson Streaming API, ứng dụng thường làm việc trực tiếp với `JsonGenerator`. Generator phát tên field, string, number, boolean, null, object và array theo đúng cấu trúc JSON. Với chuỗi, nó tự xử lý dấu nháy kép, dấu gạch chéo ngược và các ký tự điều khiển cần escape. Với dữ liệu nhị phân như ảnh, file hoặc chữ ký số, JSON không có kiểu binary riêng; ứng dụng thường mã hóa byte thành Base64 rồi ghi thành một JSON string.

Điều quan trọng là chọn đúng API theo loại dữ liệu. `writeString()` dành cho nội dung văn bản và tự escape theo quy tắc JSON; `writeBinary()` dành cho byte và mã hóa Base64; `writeRaw()` bỏ qua cơ chế escape và có thể phá hỏng JSON nếu dùng sai. Khi ghi ra stream, cần thống nhất UTF-8, quản lý vòng đời stream và cân nhắc kích thước payload.

## 1. JsonGenerator trong luồng ghi JSON

`JsonGenerator` thuộc module `jackson-core`. Nó cung cấp API streaming để ghi JSON từng token mà không cần tạo toàn bộ object tree hoặc ghép chuỗi thủ công.

Ví dụ JSON cần ghi:

```json
{
  "message": "Hello, An!",
  "active": true,
  "count": 3
}
```

Có thể phát dữ liệu theo từng bước:

```java
JsonFactory factory = new JsonFactory();

try (JsonGenerator generator = factory.createGenerator(outputStream)) {
    generator.writeStartObject();

    generator.writeStringField("message", "Hello, An!");
    generator.writeBooleanField("active", true);
    generator.writeNumberField("count", 3);

    generator.writeEndObject();
}
```

Các lệnh tương ứng với cấu trúc:

- `writeStartObject()`: bắt đầu JSON object.
- `writeStringField(name, value)`: ghi tên field và string value.
- `writeBooleanField(name, value)`: ghi boolean.
- `writeNumberField(name, value)`: ghi number.
- `writeEndObject()`: kết thúc object.

Generator tự quản lý dấu ngoặc, dấu phẩy, dấu hai chấm và escaping của field name/value. Nhờ vậy, code không phải tự ghép ký tự JSON.

### 1.1. Tạo generator cho UTF-8 OutputStream

Nếu đích là file, socket hoặc HTTP response body dạng byte, có thể tạo generator trực tiếp trên `OutputStream`:

```java
JsonFactory factory = new JsonFactory();

try (OutputStream output = Files.newOutputStream(Path.of("message.json"));
     JsonGenerator generator = factory.createGenerator(output, JsonEncoding.UTF8)) {

    generator.writeStartObject();
    generator.writeStringField("message", "Xin chào");
    generator.writeEndObject();
}
```

Khi truyền `JsonEncoding.UTF8`, encoding đầu ra được chỉ rõ. Đây là lựa chọn phù hợp với JSON trao đổi giữa các hệ thống.

Nếu tạo generator từ `Writer`, dữ liệu đã ở dạng ký tự; việc mã hóa thành byte do `Writer` và stream bên dưới quyết định. Hãy tránh dựa vào charset mặc định của máy.

### 1.2. Generator từ ObjectMapper

Khi ứng dụng đã có `ObjectMapper`, có thể lấy factory dùng chung:

```java
JsonFactory factory = mapper.getFactory();

try (JsonGenerator generator = factory.createGenerator(outputStream)) {
    generator.writeStartObject();
    generator.writeStringField("status", "ready");
    generator.writeEndObject();
}
```

Cách này giữ các cấu hình liên quan đến factory mà mapper đang dùng. Nếu cần cấu hình escaping hoặc output riêng cho một luồng, có thể đặt cấu hình trên generator được tạo ra.

## 2. Ghi chuỗi bằng writeString()

Dùng `writeString()` khi giá trị Java là văn bản:

```java
generator.writeString("Jackson streaming");
```

Nếu đang ghi field trong object:

```java
generator.writeStringField("description", "Jackson streaming");
```

Generator tự thêm dấu nháy JSON và escape các ký tự đặc biệt. Không truyền sẵn dấu nháy bao quanh chuỗi; nếu làm vậy, dấu nháy đó sẽ trở thành nội dung của giá trị và tiếp tục được escape.

Ví dụ:

```java
generator.writeString("An nói: \"Xin chào\".");
```

JSON đầu ra hợp lệ:

```json
"An nói: \"Xin chào\"."
```

Chuỗi Java chứa dấu nháy kép thật; trong JSON, dấu nháy bên trong được biểu diễn bằng `\"`.

### 2.1. Ghi chuỗi từ char[]

Khi dữ liệu đang nằm trong một mảng ký tự, có thể ghi trực tiếp một đoạn:

```java
char[] text = "Hello Jackson".toCharArray();

generator.writeString(text, 0, text.length);
```

Các tham số là mảng ký tự, offset bắt đầu và độ dài cần ghi. Generator vẫn áp dụng quy tắc escape JSON như khi ghi từ `String`.

Cách này hữu ích khi ứng dụng đang xử lý buffer ký tự và muốn tránh tạo thêm một chuỗi trung gian.

### 2.2. Ghi tên field và giá trị tách rời

Ngoài các helper như `writeStringField()`, có thể điều khiển từng token:

```java
generator.writeFieldName("displayName");
generator.writeString("Nguyen An");
```

Cách này cần thiết khi field name hoặc value được quyết định động. Generator sẽ kiểm tra trạng thái cấu trúc để bảo đảm thứ tự token hợp lệ, ví dụ field name chỉ được ghi trong object.

### 2.3. Xử lý Java null

Java `null` và chuỗi văn bản `"null"` là hai giá trị khác nhau:

```java
generator.writeString("null"); // JSON string: "null"
generator.writeNull();        // JSON null: null
```

Khi biến Java có thể null, hãy rẽ nhánh tường minh:

```java
if (displayName == null) {
    generator.writeNullField("displayName");
} else {
    generator.writeStringField("displayName", displayName);
}
```

Không dùng `String.valueOf(value)` nếu muốn giữ JSON null. `String.valueOf(null)` tạo chuỗi ký tự `"null"`, khiến JSON đầu ra khác ý nghĩa.

## 3. Vì sao JSON cần escape chuỗi?

JSON string bắt đầu và kết thúc bằng dấu nháy kép. Một số ký tự không thể xuất hiện trực tiếp trong string theo cú pháp JSON và phải được biểu diễn bằng escape sequence.

Các trường hợp quan trọng:

| Ký tự/nội dung | Cách biểu diễn trong JSON string |
|---|---|
| Dấu nháy kép `"` | `\"` |
| Backslash `\` | `\\` |
| Xuống dòng | `\n` |
| Carriage return | `\r` |
| Tab | `\t` |
| Backspace | `\b` |
| Form feed | `\f` |
| Ký tự điều khiển U+0000 đến U+001F | Escape dạng ngắn nếu có hoặc `\u00XX` |

Ví dụ Java string chứa dấu nháy, backslash và newline:

```java
String message = "Dòng 1: \"Hello\"\\server\nDòng 2";

generator.writeStringField("message", message);
```

JSON tương ứng có thể được hiển thị như sau:

```json
{
  "message": "Dòng 1: \"Hello\"\\server\nDòng 2"
}
```

Trong JSON, ký tự xuống dòng thực tế trong string được biểu diễn bằng hai ký tự escape `\n`, không phải một line break thô nằm giữa dấu nháy.

### 3.1. Những ký tự không bắt buộc phải escape

Theo JSON, các ký tự Unicode hợp lệ ngoài nhóm ký tự điều khiển có thể được ghi trực tiếp. Ví dụ tiếng Việt:

```java
generator.writeString("Xin chào Việt Nam");
```

Có thể được ghi trực tiếp dưới dạng Unicode trong JSON UTF-8. Không bắt buộc mọi ký tự ngoài ASCII phải chuyển thành `\uXXXX`.

Một số hệ thống chọn escape thêm Unicode để tương thích với consumer cũ hoặc để đáp ứng quy tắc tích hợp riêng. Đó là quyết định biểu diễn, không phải yêu cầu chung của JSON.

### 3.2. Escape trong JSON khác escape ở HTML, URL và SQL

Mỗi ngữ cảnh có quy tắc riêng:

- JSON escaping bảo vệ cú pháp JSON.
- HTML escaping bảo vệ ngữ cảnh HTML.
- URL encoding mã hóa thành phần URL.
- SQL parameterization/escaping xử lý dữ liệu trong câu truy vấn SQL.

Không dùng JSON escaping như một cơ chế bảo vệ tổng quát khi nhúng dữ liệu vào HTML hoặc SQL. Hãy encode theo đúng ngữ cảnh tiêu thụ và ưu tiên API an toàn như prepared statement.

## 4. Jackson tự escape những gì?

Khi dùng `writeString()`, Jackson xử lý các ký tự cần escape theo quy tắc JSON, bao gồm dấu nháy kép, backslash và ký tự điều khiển. Generator cũng xử lý encoding đầu ra theo cấu hình.

Ví dụ, code sau an toàn về cú pháp JSON:

```java
String untrustedText = userInput;

generator.writeStartObject();
generator.writeStringField("comment", untrustedText);
generator.writeEndObject();
```

Ngay cả khi `userInput` chứa dấu nháy, newline hoặc chuỗi giống JSON, generator vẫn ghi nó như một string value, không biến nội dung đó thành cấu trúc JSON mới.

Ví dụ input:

```text
"} , "admin": true, "
```

Khi ghi bằng `writeStringField()`, toàn bộ nội dung vẫn nằm trong giá trị string. Nó không thể tự đóng object hay thêm field JSON.

Đây là lý do nên dùng API typed của generator thay vì nối chuỗi bằng toán tử `+`.

## 5. Ghi chuỗi Unicode và UTF-8

JSON text có thể chứa Unicode. Khi ghi ra `OutputStream`, nên chọn UTF-8 rõ ràng:

```java
try (JsonGenerator generator =
        new JsonFactory().createGenerator(outputStream, JsonEncoding.UTF8)) {

    generator.writeStartObject();
    generator.writeStringField("greeting", "Xin chào, thế giới!");
    generator.writeEndObject();
}
```

UTF-8 mã hóa các ký tự Unicode thành một hoặc nhiều byte. Một ký tự tiếng Việt có thể chiếm nhiều hơn một byte; không được giả định số byte bằng số ký tự Java.

### 5.1. Không tự chuyển byte thành String bằng charset mặc định

Nếu dữ liệu gốc là byte nhị phân, không làm như sau:

```java
String text = new String(binaryBytes); // Không đúng nếu bytes không phải văn bản
generator.writeString(text);
```

Cách này diễn giải byte theo charset mặc định và có thể làm hỏng dữ liệu. Nếu byte là nội dung file hoặc ảnh, hãy ghi bằng `writeBinary()`. Nếu byte thực sự là văn bản đã mã hóa UTF-8, hãy giải mã với charset được chỉ định rồi dùng `writeString()`.

### 5.2. Escape Unicode không thay đổi ý nghĩa ký tự

Hai JSON string sau có thể biểu diễn cùng nội dung:

```json
"Tiếng Việt"
```

```json
"Ti\u1ebfng Vi\u1ec7t"
```

Một dạng ghi trực tiếp Unicode, dạng còn lại dùng Unicode escape. Sau khi parse, consumer nhận cùng chuỗi ký tự.

Không cần bật escape toàn bộ non-ASCII trừ khi hợp đồng hoặc hệ thống cũ yêu cầu. Ghi UTF-8 trực tiếp thường dễ đọc và gọn hơn.

## 6. Ghi dữ liệu nhị phân bằng writeBinary()

JSON không có kiểu dữ liệu binary riêng. Khi cần đưa byte vào JSON, cách phổ biến là mã hóa Base64 và ghi kết quả như một string.

Ví dụ byte array:

```java
byte[] imageBytes = Files.readAllBytes(Path.of("avatar.png"));

generator.writeStartObject();
generator.writeBinaryField("avatar", imageBytes);
generator.writeEndObject();
```

Nếu API không có helper `writeBinaryField()` trong phiên bản đang dùng hoặc cần chỉ định Base64 variant, có thể ghi tách rời:

```java
generator.writeFieldName("avatar");
generator.writeBinary(Base64Variants.getDefaultVariant(),
        imageBytes, 0, imageBytes.length);
```

JSON đầu ra có dạng:

```json
{
  "avatar": "iVBORw0KGgoAAAANSUhEUg..."
}
```

Giá trị `avatar` là Base64 string. Nó không phải byte trực tiếp và cũng không phải một JSON array số nguyên.

### 6.1. Base64 hoạt động như thế nào?

Base64 biến mỗi nhóm 3 byte (24 bit) thành 4 ký tự trong bảng chữ cái Base64. Nếu số byte không chia hết cho 3, output có thể có ký tự padding `=`.

Kích thước văn bản Base64 xấp xỉ:

```text
4 * ceil(binaryLength / 3)
```

Vì vậy, Base64 thường làm dữ liệu tăng khoảng một phần ba, chưa tính overhead của JSON string. Đây là đánh đổi để byte có thể truyền qua định dạng văn bản JSON.

### 6.2. Chọn Base64 variant

Jackson cung cấp các `Base64Variant` qua `Base64Variants`. Variant quy định bảng ký tự và quy tắc padding/linefeed. Khi producer và consumer đều dùng mặc định tương thích, các API đơn giản như `writeBinary(byte[])` và `getBinaryValue()` thường là đủ.

Nếu hợp đồng yêu cầu variant cụ thể, hãy chỉ định cùng variant ở cả hai phía:

```java
Base64Variant variant = Base64Variants.getDefaultVariant();

generator.writeBinary(variant, bytes, 0, bytes.length);
```

Không tự chèn line break hoặc thay ký tự Base64 bằng tay sau khi generator đã mã hóa. Hãy để Jackson thực hiện theo variant được chọn.

## 7. Ghi binary lớn từ InputStream

Nếu file lớn, `Files.readAllBytes()` tạo một byte array chứa toàn bộ nội dung trong heap. Có thể dùng overload nhận `InputStream` để generator đọc và Base64 encode theo luồng:

```java
try (InputStream input = Files.newInputStream(Path.of("archive.zip"));
     OutputStream output = Files.newOutputStream(Path.of("payload.json"));
     JsonGenerator generator =
             new JsonFactory().createGenerator(output, JsonEncoding.UTF8)) {

    generator.writeStartObject();
    generator.writeFieldName("archive");
    generator.writeBinary(input, (int) Files.size(Path.of("archive.zip")));
    generator.writeEndObject();
}
```

Overload nhận stream cần độ dài dữ liệu. Ví dụ trên giả định kích thước file nằm trong miền `int`; với file lớn hơn, cần chọn cách xử lý/chia phần phù hợp với giới hạn API và hợp đồng truyền tải. Có thể lấy kích thước trước khi mở stream hoặc quản lý metadata kích thước từ nguồn.

Nếu dữ liệu được tạo theo luồng và không biết trước độ dài, hãy xem overload và giới hạn của phiên bản Jackson đang dùng; không nên giả định mọi generator/backend xử lý stream không độ dài giống nhau.

### 7.1. Khi nào nên tránh Base64 trong JSON?

Base64 phù hợp với ảnh nhỏ, token, chữ ký hoặc binary payload có kích thước vừa phải. Với file lớn, gửi toàn bộ Base64 trong một JSON document có thể:

- Tăng kích thước request/response.
- Tăng chi phí CPU cho encode/decode.
- Tăng áp lực bộ nhớ ở producer và consumer.
- Làm việc retry, cache và streaming khó hơn.

Với file lớn, thường nên truyền metadata trong JSON và nội dung file qua binary endpoint, multipart upload hoặc object storage. JSON có thể chứa URL, checksum, content type và kích thước thay vì nhúng toàn bộ byte.

## 8. Đọc lại Base64 thành byte

Khi parser đọc một JSON string được tạo bởi `writeBinary()`, có thể giải mã thành byte array:

```java
try (JsonParser parser = new JsonFactory().createParser(json)) {
    while (parser.nextToken() != null) {
        if (parser.currentToken() == JsonToken.FIELD_NAME
                && "avatar".equals(parser.currentName())) {
            parser.nextToken();
            byte[] imageBytes = parser.getBinaryValue();
            Files.write(Path.of("avatar-copy.png"), imageBytes);
        }
    }
}
```

Ở ví dụ thực tế, cần kiểm tra token hiện tại là `VALUE_STRING` trước khi gọi `getBinaryValue()`. Parser giải mã Base64 string thành byte.

Có thể dùng variant tường minh:

```java
byte[] decoded = parser.getBinaryValue(Base64Variants.getDefaultVariant());
```

Producer và consumer phải thống nhất Base64 variant. Nếu chuỗi không phải Base64 hợp lệ, parser có thể phát sinh lỗi xử lý nội dung.

### 8.1. Đọc binary lớn ra OutputStream

Để tránh giữ toàn bộ dữ liệu giải mã trong một byte array, parser có API ghi decoded bytes trực tiếp vào `OutputStream`:

```java
try (JsonParser parser = new JsonFactory().createParser(input);
     OutputStream file = Files.newOutputStream(Path.of("download.bin"))) {

    while (parser.nextToken() != null) {
        if (parser.currentToken() == JsonToken.FIELD_NAME
                && "content".equals(parser.currentName())) {
            parser.nextToken();

            if (parser.currentToken() != JsonToken.VALUE_STRING) {
                throw new IOException("content phải là Base64 string");
            }

            parser.readBinaryValue(file);
        }
    }
}
```

Cách này giúp giảm nhu cầu tạo byte array lớn trong ứng dụng. Dù vậy, toàn bộ JSON vẫn phải được parse theo cấu trúc; cần giới hạn kích thước payload và xử lý lỗi I/O.

## 9. Phân biệt writeString, writeRaw và writeRawValue

Ba API này có mục đích rất khác nhau. Nhầm lẫn giữa chúng là nguyên nhân phổ biến tạo JSON sai hoặc tạo lỗ hổng injection.

| API | Hành vi | Dùng khi nào |
|---|---|---|
| `writeString(text)` | Ghi text như một JSON string và tự escape | Nội dung văn bản, kể cả dữ liệu không tin cậy |
| `writeRaw(text)` | Ghi ký tự thô, không thêm dấu nháy và không escape | Chỉ dùng khi đang điều khiển output thô có chủ đích |
| `writeRawValue(jsonValue)` | Ghi một đoạn text thô như một JSON value | Chỉ dùng với JSON fragment đã được tạo/kiểm tra là hợp lệ |

### 9.1. writeString: lựa chọn mặc định cho văn bản

```java
generator.writeString(userInput);
```

Nếu `userInput` chứa dấu nháy hoặc ký tự điều khiển, Jackson escape chúng. Nội dung vẫn là một string value.

### 9.2. writeRaw: bỏ qua cú pháp string

```java
generator.writeRaw(userInput);
```

Lệnh này không tự thêm dấu nháy JSON và không escape nội dung. Nếu `userInput` chứa ký tự không phù hợp với vị trí hiện tại, JSON có thể bị hỏng.

Ví dụ, ghi raw text ngay sau một field name không bảo đảm tạo ra JSON hợp lệ. Không dùng `writeRaw()` để ghi nội dung người dùng hoặc để “tránh escape”.

### 9.3. writeRawValue: ghi một JSON fragment

Nếu đã có một JSON value được tạo và xác thực ở nơi khác:

```java
generator.writeFieldName("metadata");
generator.writeRawValue("{\"source\":\"import\",\"version\":2}");
```

Kết quả là field `metadata` chứa object JSON, không phải string chứa ký tự JSON.

Nếu dùng `writeString()` thay thế, kết quả sẽ là:

```json
{
  "metadata": "{\"source\":\"import\",\"version\":2}"
}
```

Đó là một string value, khác hoàn toàn object JSON.

`writeRawValue()` không nên được coi là một JSON validator. Chỉ truyền fragment đáng tin cậy đã được serialize bằng Jackson hoặc đã được xác thực theo hợp đồng. Nếu dữ liệu đến từ bên ngoài, parse thành node rồi ghi node bằng API phù hợp.

## 10. Tùy chỉnh escaping với CharacterEscapes

Mặc định của Jackson đáp ứng escaping cần thiết để tạo JSON hợp lệ. Một số hệ thống cần escape thêm các ký tự ASCII, chẳng hạn `<`, `>` và `&` khi JSON được nhúng vào một ngữ cảnh HTML đặc thù.

Có thể tùy chỉnh bằng `CharacterEscapes`:

```java
public class HtmlSafeEscapes extends CharacterEscapes {
    private final int[] asciiEscapes;

    private final SerializableString lessThan =
            new SerializedString("\\u003C");
    private final SerializableString greaterThan =
            new SerializedString("\\u003E");
    private final SerializableString ampersand =
            new SerializedString("\\u0026");

    public HtmlSafeEscapes() {
        asciiEscapes = CharacterEscapes.standardAsciiEscapesForJSON();
        asciiEscapes['<'] = CharacterEscapes.ESCAPE_CUSTOM;
        asciiEscapes['>'] = CharacterEscapes.ESCAPE_CUSTOM;
        asciiEscapes['&'] = CharacterEscapes.ESCAPE_CUSTOM;
    }

    @Override
    public int[] getEscapeCodesForAscii() {
        return asciiEscapes;
    }

    @Override
    public SerializableString getEscapeSequence(int ch) {
        return switch (ch) {
            case '<' -> lessThan;
            case '>' -> greaterThan;
            case '&' -> ampersand;
            default -> null;
        };
    }
}
```

Gắn vào generator:

```java
try (JsonGenerator generator = factory.createGenerator(outputStream)) {
    generator.setCharacterEscapes(new HtmlSafeEscapes());

    generator.writeStartObject();
    generator.writeStringField("text", "<script>alert('x')</script>");
    generator.writeEndObject();
}
```

Các ký tự được cấu hình sẽ được ghi dưới dạng Unicode escape, ví dụ `\u003C`. Sau khi parse JSON, giá trị string vẫn là nội dung ban đầu.

### 10.1. CharacterEscapes không thay thế output encoding theo ngữ cảnh

Escape thêm `<`, `>` và `&` có thể hữu ích khi JSON được đặt trong một số ngữ cảnh HTML, nhưng không phải giải pháp bảo mật tổng quát cho mọi nơi. Nếu nhúng JSON vào HTML, cần tuân thủ quy tắc của HTML/script context và cách framework render. Nếu gửi JSON qua HTTP với content type JSON, thường nên trả JSON riêng và để trình duyệt parse bằng API phù hợp.

Không tự viết một bộ escape thay thế toàn bộ logic JSON của Jackson nếu không có yêu cầu rõ. Dùng `CharacterEscapes` cho phần mở rộng có chủ đích và giữ các escape chuẩn bằng `standardAsciiEscapesForJSON()`.

## 11. Ghi string và binary trong cùng một object

Một payload có thể có metadata dạng string và một phần nội dung binary mã hóa Base64:

```java
public void writeAttachment(
        OutputStream output,
        String fileName,
        String contentType,
        byte[] content
) throws IOException {

    JsonFactory factory = new JsonFactory();

    try (JsonGenerator generator =
            factory.createGenerator(output, JsonEncoding.UTF8)) {

        generator.writeStartObject();
        generator.writeStringField("fileName", fileName);
        generator.writeStringField("contentType", contentType);
        generator.writeNumberField("size", content.length);

        generator.writeFieldName("content");
        generator.writeBinary(content);

        generator.writeEndObject();
    }
}
```

Kết quả minh họa:

```json
{
  "fileName": "avatar.png",
  "contentType": "image/png",
  "size": 1024,
  "content": "iVBORw0KGgoAAAANSUhEUg..."
}
```

Ở đây:

- `fileName` và `contentType` là string nên dùng `writeStringField()`.
- `size` là number nên dùng `writeNumberField()`.
- `content` là byte nên dùng `writeBinary()`.
- Không tự chuyển byte thành chuỗi bằng charset.
- Không tự Base64 encode trước rồi lại gọi `writeBinary()`, vì khi đó Jackson sẽ mã hóa chuỗi Base64 như byte lần nữa.

Nếu dữ liệu đầu vào đã là Base64 string và hợp đồng yêu cầu giữ nguyên string, dùng `writeString()`. Nếu dữ liệu đầu vào là byte thô, dùng `writeBinary()`.

## 12. Ghi JSON vào String hay OutputStream?

Jackson cung cấp các kiểu đích khác nhau:

| API | Kết quả | Khi phù hợp |
|---|---|---|
| `writeValueAsString(value)` | Java String | Cần JSON text trong bộ nhớ |
| `writeValueAsBytes(value)` | byte array | Cần byte JSON để truyền hoặc lưu |
| `writeValue(outputStream, value)` | Ghi trực tiếp ra stream | Muốn tránh giữ toàn bộ JSON trong String |
| `JsonGenerator` trên OutputStream | Ghi token từng bước | Muốn kiểm soát cấu trúc và xử lý streaming |
| `JsonGenerator` trên Writer | Ghi ký tự từng bước | Đã có writer và encoding được quản lý bên ngoài |

Nếu payload lớn, ghi trực tiếp ra stream thường tránh được một bản sao chuỗi JSON lớn trong heap. Nếu cần xây dựng JSON động theo từng nhánh, generator cũng tránh phải tạo toàn bộ tree model.

Khi dùng try-with-resources, cần hiểu ai sở hữu stream. Đóng generator có thể đóng target stream theo cấu hình mặc định. Nếu stream do framework quản lý và không được phép đóng tại đây, hãy cấu hình `JsonGenerator.Feature.AUTO_CLOSE_TARGET` phù hợp hoặc tuân thủ lifecycle mà framework quy định. Đừng để generator vô tình đóng HTTP response stream trước khi framework hoàn tất response.

## 13. Các lỗi thường gặp

**Tự ghép JSON bằng chuỗi.** Dấu nháy, backslash, newline hoặc Unicode có thể làm hỏng cú pháp. Dùng `writeString()` và các API typed.

**Dùng writeRaw cho nội dung người dùng.** Raw API không escape. Dữ liệu có thể phá cấu trúc JSON hoặc chèn thêm token. Dùng `writeString()`.

**Nhầm writeRawValue với writeString.** Một cái ghi JSON fragment, một cái ghi string chứa text. Hãy xác định consumer cần object/array/value hay một chuỗi văn bản.

**Chuyển byte nhị phân thành String.** Byte ảnh hoặc file không phải văn bản. Dùng `writeBinary()` để Base64 encode.

**Base64 encode hai lần.** Nếu đã có byte thô, gọi `writeBinary()`; nếu đã có Base64 text cần giữ nguyên, gọi `writeString()`. Không biến Base64 string thành byte rồi lại ghi binary nếu không muốn mã hóa thêm lần nữa.

**Dùng sai Base64 variant.** Producer và consumer phải thống nhất alphabet và quy tắc padding/linefeed. Chọn variant tường minh nếu hợp đồng yêu cầu.

**Không kiểm tra null.** `null` Java, chuỗi `"null"` và JSON null là ba điều khác nhau. Dùng `writeNull()` hoặc `writeNullField()` cho JSON null.

**Cho rằng Unicode phải escape hết.** UTF-8 có thể mang Unicode trực tiếp. Chỉ escape thêm khi có yêu cầu tương thích hoặc ngữ cảnh output cụ thể.

**Ghi file lớn bằng readAllBytes.** Có thể tạo byte array lớn trong heap. Dùng overload `writeBinary(InputStream, dataLength)` khi phù hợp hoặc truyền file qua giao thức binary riêng.

**Đóng nhầm stream.** Generator có thể đóng target stream khi đóng chính nó. Cần xác định rõ quyền sở hữu và lifecycle.

## 14. Kiểm thử string escaping và binary round-trip

Một test nên parse lại JSON sau khi ghi để xác nhận nội dung không bị thay đổi:

```java
@Test
void shouldEscapeStringAndPreserveItsValue() throws Exception {
    ObjectMapper mapper = new ObjectMapper();
    String original = "Quote: \" ; slash: \\ ; line1\nline2 ; tiếng Việt";

    String json = mapper.writeValueAsString(original);
    String restored = mapper.readValue(json, String.class);

    assertEquals(original, restored);
}
```

Với binary:

```java
@Test
void shouldRoundTripBinaryThroughBase64Json() throws Exception {
    ObjectMapper mapper = new ObjectMapper();
    byte[] original = new byte[] {0, 1, 2, 10, 13, 127, (byte) 0xFF};

    String json = mapper.writeValueAsString(original);
    byte[] restored = mapper.readValue(json, byte[].class);

    assertArrayEquals(original, restored);
}
```

Jackson databind mặc định serialize `byte[]` thành Base64 string trong JSON. Nếu dùng `JsonGenerator` trực tiếp, test tương tự có thể ghi `writeBinary()` rồi parse bằng `getBinaryValue()`.

Nên bổ sung test cho:

- String rỗng.
- Dấu nháy kép và backslash.
- Tab, carriage return, newline và ký tự điều khiển.
- Unicode tiếng Việt và ký tự ngoài BMP.
- Java null và JSON null.
- Binary rỗng.
- Binary có byte âm khi biểu diễn dưới kiểu Java `byte`.
- Payload binary lớn và stream bị thiếu byte so với độ dài khai báo.
- Raw fragment hợp lệ và trường hợp fragment không hợp lệ (nếu ứng dụng có dùng raw API).

## 15. Chọn API theo loại dữ liệu

| Dữ liệu đầu vào | API nên dùng | Dạng JSON |
|---|---|---|
| Văn bản Java `String` | `writeString()` / `writeStringField()` | JSON string có escape |
| Đoạn ký tự `char[]` | `writeString(char[], offset, len)` | JSON string có escape |
| Java null | `writeNull()` / `writeNullField()` | JSON null |
| Byte array | `writeBinary()` | Base64 JSON string |
| InputStream binary | `writeBinary(input, length)` | Base64 JSON string |
| JSON fragment đã tin cậy và hợp lệ | `writeRawValue()` | Giá trị JSON thô |
| Nội dung raw ở mức generator | `writeRaw()` | Không tự bảo đảm JSON hợp lệ |

Nguyên tắc đơn giản là mô tả đúng loại dữ liệu với API tương ứng. Hãy để generator quản lý JSON syntax và escaping; chỉ dùng raw API khi thật sự đang ghi một fragment đã được kiểm soát.

## 16. Kết luận

Với Jackson Streaming API, `JsonGenerator.writeString()` ghi văn bản thành JSON string và tự escape các ký tự cần thiết. Dữ liệu nhị phân phải được mã hóa, thường bằng Base64, rồi ghi qua `writeBinary()`; khi đọc lại có thể dùng `getBinaryValue()` hoặc `readBinaryValue()`. JSON không có binary type nguyên bản, vì vậy Base64 làm tăng kích thước dữ liệu và có thể không phù hợp với file lớn.

`writeRaw()` và `writeRawValue()` bỏ qua một phần bảo vệ của API typed và chỉ nên dùng với nội dung được kiểm soát. Khi ghi ra stream, hãy chỉ rõ UTF-8, quản lý stream theo đúng lifecycle và kiểm thử round-trip cho string/binary. Dùng đúng API theo loại dữ liệu giúp JSON luôn hợp lệ, giữ nguyên nội dung và giảm nguy cơ injection hoặc mất dữ liệu.

## Tài liệu tham khảo

- [Jackson Core — JsonGenerator API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-core/latest/com/fasterxml/jackson/core/JsonGenerator.html)
- [Jackson Core — JsonParser API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-core/latest/com/fasterxml/jackson/core/JsonParser.html)
- [Jackson Core — CharacterEscapes API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-core/latest/com/fasterxml/jackson/core/io/CharacterEscapes.html)
- [Jackson Core — Base64Variants API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-core/latest/com/fasterxml/jackson/core/Base64Variants.html)
- [RFC 8259 — The JavaScript Object Notation (JSON) Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259)

