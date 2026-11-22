# Bảo toàn Unicode và ký tự cần thoát trong chuỗi

JSON là định dạng văn bản dùng Unicode. Khi Jackson đọc hoặc ghi chuỗi, dữ liệu có thể chứa tiếng Việt có dấu, chữ viết của nhiều ngôn ngữ, emoji, dấu ngoặc kép, dấu gạch chéo ngược, ký tự xuống dòng và các ký tự điều khiển. Để dữ liệu không bị hỏng, cần phân biệt nội dung thực của chuỗi, cách biểu diễn chuỗi trong cú pháp JSON và cách mã hóa văn bản thành byte khi truyền hoặc lưu trữ.

Jackson xử lý phần lớn việc escape JSON tự động. Khi ghi một giá trị String, serializer sẽ đặt chuỗi trong dấu ngoặc kép và escape những ký tự bắt buộc theo cú pháp JSON. Khi đọc, parser diễn giải các escape sequence và trả về nội dung chuỗi trong Java. Ứng dụng nên để Jackson xử lý việc này thay vì tự ghép JSON bằng nối chuỗi.

## 1. Unicode trong JSON và Java

Unicode gán mã cho các ký tự của nhiều hệ chữ viết. Ví dụ, chữ tiếng Việt như ă, â, ê, ô, ơ, ư và các chữ có dấu là những ký tự Unicode bình thường. JSON có thể biểu diễn chúng trực tiếp trong văn bản UTF-8 hoặc dùng escape Unicode dạng \uXXXX.

Hai JSON sau biểu diễn cùng nội dung:

~~~json
{
  "message": "Xin chào Việt Nam"
}
~~~

~~~json
{
  "message": "Xin ch\u00e0o Vi\u1ec7t Nam"
}
~~~

Parser JSON giải mã các escape sequence để tạo cùng giá trị chuỗi. Dạng hiển thị khác nhau không có nghĩa nội dung chuỗi khác nhau.

Java String lưu văn bản theo UTF-16. Nhiều ký tự phổ biến nằm trong một code unit UTF-16; các ký tự ngoài Basic Multilingual Plane, ví dụ nhiều emoji, được biểu diễn bằng một cặp surrogate. Khi Jackson đọc JSON, parser chuyển chuỗi JSON thành Java String; khi ghi, generator chuyển Java String thành cú pháp JSON.

Ví dụ:

~~~java
ObjectMapper mapper = new ObjectMapper();

String json = """
    {
      "greeting": "Xin chào",
      "symbol": "😀"
    }
    """;

JsonNode root = mapper.readTree(json);
String greeting = root.get("greeting").asText();
String symbol = root.get("symbol").asText();
~~~

Ứng dụng nhận được các giá trị chuỗi Java có nội dung tương ứng. Không cần tự giải mã các mã Unicode trong chuỗi JSON sau khi Jackson đã đọc thành công.

## 2. Unicode trực tiếp và escape Unicode

Một ký tự Unicode có thể được biểu diễn trực tiếp hoặc bằng escape:

| Cách biểu diễn | Ví dụ | Ý nghĩa |
|---|---|---|
| Ký tự trực tiếp | ế | Ký tự xuất hiện trực tiếp trong văn bản JSON |
| Escape Unicode | \u1ebf | Mã UTF-16 của ký tự được viết bằng bốn chữ số hex |
| Emoji trực tiếp | 😀 | Ký tự ngoài BMP xuất hiện trực tiếp trong văn bản |
| Cặp escape surrogate | \uD83D\uDE00 | Hai code unit UTF-16 kết hợp thành emoji tương ứng |

JSON escape Unicode dùng cú pháp \u theo sau bởi đúng bốn chữ số thập lục phân. Escape này biểu diễn một code unit UTF-16. Với ký tự ngoài BMP, cần hai escape surrogate liền nhau.

Ví dụ, mặt cười có thể được biểu diễn như sau:

~~~json
{
  "face": "😀"
}
~~~

Hoặc:

~~~json
{
  "face": "\uD83D\uDE00"
}
~~~

Khi parser giải mã đúng cặp surrogate, Java String chứa cùng ký tự. Không nên tự chia một ký tự ngoài BMP thành hai ký tự riêng biệt hoặc bỏ một nửa surrogate pair.

## 3. Jackson mặc định ghi Unicode như thế nào?

Theo mặc định, Jackson thường ghi các ký tự Unicode có thể biểu diễn trực tiếp trong output thay vì escape tất cả thành ASCII. Ví dụ:

~~~java
ObjectMapper mapper = new ObjectMapper();

Map<String, String> data = Map.of(
    "greeting", "Xin chào Việt Nam",
    "city", "Thành phố Hồ Chí Minh",
    "emoji", "😀"
);

String json = mapper.writeValueAsString(data);
System.out.println(json);
~~~

Kết quả có thể chứa trực tiếp tiếng Việt và emoji. Đây là JSON hợp lệ nếu văn bản được truyền hoặc lưu với encoding phù hợp, thường là UTF-8.

Escape Unicode không phải điều kiện bắt buộc để JSON hợp lệ. Hai dạng sau tương đương về giá trị:

~~~json
{"city":"Th\u00e0nh ph\u1ed1 H\u1ed3 Ch\u00ed Minh"}
~~~

~~~json
{"city":"Thành phố Hồ Chí Minh"}
~~~

Khi trao đổi giữa các hệ thống, nên ưu tiên UTF-8 và để Jackson ghi Unicode trực tiếp trừ khi hệ thống đích yêu cầu ASCII-only hoặc có một quy ước escape cụ thể.

## 4. Bật chế độ escape ký tự ngoài ASCII

Một số hệ thống cũ chỉ xử lý an toàn dữ liệu ASCII, hoặc yêu cầu JSON đầu ra không chứa ký tự ngoài ASCII. Jackson có thể escape các ký tự ngoài ASCII bằng JsonWriteFeature.ESCAPE_NON_ASCII.

~~~java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.json.JsonWriteFeature;
import com.fasterxml.jackson.databind.ObjectMapper;

JsonFactory factory = JsonFactory.builder()
    .enable(JsonWriteFeature.ESCAPE_NON_ASCII)
    .build();

ObjectMapper mapper = new ObjectMapper(factory);

String json = mapper.writeValueAsString(
    Map.of("message", "Xin chào Việt Nam")
);
~~~

Khi bật tính năng này, các ký tự ngoài ASCII được biểu diễn bằng escape Unicode. Ví dụ chữ có dấu có thể xuất hiện dưới dạng \uXXXX, còn ký tự ngoài BMP có thể được biểu diễn bằng cặp surrogate escape.

Ở một số phiên bản Jackson cũ, có thể gặp API tương đương JsonGenerator.Feature.ESCAPE_NON_ASCII. API cũ được đánh dấu deprecated trong các phiên bản mới hơn; khi dự án đã dùng JsonWriteFeature, nên cấu hình qua JsonFactory builder như ví dụ.

ESCAPE_NON_ASCII chỉ thay đổi cách biểu diễn ký tự trong JSON. Nó không thay đổi giá trị chuỗi sau khi đọc lại và không phải bước mã hóa UTF-8. Dùng tính năng này khi cần tương thích với hệ thống ASCII-only, không cần bật chỉ vì JSON chứa tiếng Việt.

## 5. Các ký tự bắt buộc phải escape trong JSON string

Trong một JSON string, dấu ngoặc kép kép dùng để mở và đóng chuỗi. Vì vậy, nếu nội dung thực có dấu ngoặc kép, parser cần phân biệt nó với dấu kết thúc chuỗi. Dấu gạch chéo ngược cũng là ký tự mở đầu escape sequence.

Các ký tự sau có cách biểu diễn escape quen thuộc:

| Nội dung ký tự | JSON escape | Ý nghĩa |
|---|---|---|
| Dấu ngoặc kép kép | \" | Dấu ngoặc kép nằm trong chuỗi |
| Dấu gạch chéo ngược | \\ | Ký tự backslash nằm trong chuỗi |
| Backspace | \b | Ký tự điều khiển backspace |
| Form feed | \f | Ký tự điều khiển form feed |
| Line feed | \n | Xuống dòng |
| Carriage return | \r | Về đầu dòng |
| Tab | \t | Tab ngang |
| Ký tự điều khiển khác | \u00XX | Escape Unicode cho code unit điều khiển tương ứng |

Các ký tự điều khiển U+0000 đến U+001F không được xuất hiện trực tiếp trong JSON string. Chúng phải được escape. Jackson tự xử lý các trường hợp này khi ghi chuỗi.

Ví dụ nội dung Java:

~~~java
String text = "Anh ấy nói: \"Xin chào\".\nDòng thứ hai.\tKết thúc.";
String json = mapper.writeValueAsString(text);
~~~

JSON được tạo có thể có dạng:

~~~json
"Anh ấy nói: \"Xin chào\".\nDòng thứ hai.\tKết thúc."
~~~

Khi đọc lại:

~~~java
String restored = mapper.readValue(json, String.class);
~~~

Giá trị restored giữ lại dấu ngoặc kép, ký tự xuống dòng và tab như nội dung ban đầu. Escape sequence chỉ là cách biểu diễn trong JSON; parser giải mã chúng khi đọc.

## 6. Vì sao không nên tự escape chuỗi trước khi gọi Jackson?

Jackson tự escape nội dung chuỗi theo cú pháp JSON. Nếu ứng dụng tự thay dấu ngoặc kép thành backslash-quote rồi truyền chuỗi đã escape vào writeValueAsString, Jackson sẽ escape cả dấu gạch chéo ngược mà ứng dụng vừa thêm. Kết quả là dữ liệu có thể bị double-escape.

Ví dụ không nên làm:

~~~java
String original = "He said \"Hello\"";
String preEscaped = original.replace("\"", "\\\"");

String json = mapper.writeValueAsString(preEscaped);
~~~

Ở đây preEscaped không còn chứa nội dung gốc mà chứa thêm các ký tự backslash do ứng dụng tự chèn. Jackson tiếp tục escape những backslash đó như dữ liệu thật.

Cách đúng:

~~~java
String original = "He said \"Hello\"";
String json = mapper.writeValueAsString(original);
~~~

Không cần gọi replace để escape dấu ngoặc kép, dấu gạch chéo ngược, newline hoặc tab trước khi tuần tự hóa. Hãy đưa giá trị Java nguyên bản cho Jackson.

Tương tự, khi đọc JSON bằng readValue, không gọi một hàm unescape thủ công trước khi parser xử lý. Parser đã có trách nhiệm giải mã escape sequence.

## 7. Escape không giống với mã hóa ký tự (character encoding)

Đây là hai lớp xử lý khác nhau:

- **JSON escaping** chuyển một ký tự trong nội dung thành cú pháp escape, ví dụ newline thành hai ký tự backslash và n.
- **Character encoding** chuyển văn bản thành byte, ví dụ UTF-8 chuyển ký tự Unicode thành một hoặc nhiều byte.

Ví dụ chuỗi Java có nội dung tiếng Việt:

~~~java
String text = "Xin chào Việt Nam";
String json = mapper.writeValueAsString(text);
byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
~~~

Ở đây Jackson tạo văn bản JSON trong String. Lệnh getBytes(UTF_8) sau đó mã hóa văn bản JSON thành byte UTF-8. Nếu gửi dữ liệu qua HTTP, header Content-Type nên khai báo application/json và charset UTF-8 theo hợp đồng của hệ thống.

Không nên dùng charset mặc định của máy:

~~~java
// Không nên phụ thuộc platform default:
byte[] bytes = json.getBytes();
~~~

Máy phát và máy nhận có thể dùng charset mặc định khác nhau, khiến tiếng Việt bị lỗi dù JSON string ban đầu đã đúng.

## 8. Ghi JSON ra OutputStream, Writer và file

Jackson hỗ trợ ghi trực tiếp ra stream hoặc writer. Khi ghi ra OutputStream, JsonFactory thường dùng UTF-8 cho JSON byte output. Khi ghi ra Writer, encoding đã được quyết định bởi Writer mà ứng dụng cung cấp.

### Ghi ra OutputStream

~~~java
try (OutputStream output = Files.newOutputStream(path)) {
    mapper.writeValue(output, data);
}
~~~

Đây là lựa chọn phù hợp khi muốn Jackson quản lý quá trình tạo JSON byte output. Với JSON byte output, dùng UTF-8 là lựa chọn tiêu chuẩn cho trao đổi dữ liệu hiện đại.

### Ghi qua Writer với UTF-8

~~~java
try (Writer writer = Files.newBufferedWriter(
        path,
        StandardCharsets.UTF_8)) {
    mapper.writeValue(writer, data);
}
~~~

Writer đã được tạo với UTF-8, vì vậy các ký tự Unicode được mã hóa theo encoding đó khi ghi file.

### Đọc file UTF-8

~~~java
try (Reader reader = Files.newBufferedReader(
        path,
        StandardCharsets.UTF_8)) {
    Data data = mapper.readValue(reader, Data.class);
}
~~~

Khi dùng Reader, ứng dụng chịu trách nhiệm chọn encoding lúc tạo Reader. Nếu file được đọc thành String trước, String đã là dữ liệu Unicode trong Java; encoding chỉ được xử lý ở bước đọc byte thành String.

Không nên tạo String từ byte bằng constructor không chỉ định charset:

~~~java
String json = new String(bytes, StandardCharsets.UTF_8);
Data data = mapper.readValue(json, Data.class);
~~~

Chỉ định UTF-8 làm cho việc giải mã byte nhất quán giữa các môi trường.

## 9. Escape dấu gạch chéo và các ký tự HTML

JSON bắt buộc escape dấu ngoặc kép, dấu gạch chéo ngược và các ký tự điều khiển. Dấu gạch chéo xuôi / không bắt buộc phải escape theo JSON. Vì vậy, Jackson thường có thể ghi dấu / trực tiếp.

Một số ứng dụng muốn escape thêm các ký tự như:

- < và > để tránh tạo chuỗi trông giống thẻ HTML khi JSON được nhúng vào tài liệu HTML.
- & để tránh một số cách diễn giải trong ngữ cảnh HTML.
- dấu nháy đơn để phù hợp với một số quy ước nhúng dữ liệu.

Đây là chính sách escape bổ sung của ứng dụng, không phải yêu cầu chung của cú pháp JSON.

Quan trọng: JSON escaping không đồng nghĩa với HTML escaping hoặc JavaScript escaping. Nếu đưa dữ liệu JSON vào HTML, thuộc tính HTML, nội dung script hoặc URL, phải tuân theo quy tắc bảo vệ của đúng ngữ cảnh đó. Chỉ bật escape Unicode không tự động làm mọi cách nhúng JSON an toàn trước XSS.

## 10. Tùy chỉnh ký tự cần escape bằng CharacterEscapes

Khi cần escape thêm một số ký tự ASCII, Jackson cung cấp CharacterEscapes. Lớp tùy chỉnh kế thừa CharacterEscapes, khai báo bảng escape cho ASCII và trả về chuỗi escape cho các ký tự được chọn.

Ví dụ escape các ký tự thường nhạy cảm khi JSON được nhúng trong một số ngữ cảnh HTML:

~~~java
import com.fasterxml.jackson.core.SerializableString;
import com.fasterxml.jackson.core.io.CharacterEscapes;
import com.fasterxml.jackson.core.io.SerializedString;

public final class HtmlSafeEscapes extends CharacterEscapes {

    private final int[] asciiEscapes;

    public HtmlSafeEscapes() {
        asciiEscapes = CharacterEscapes.standardAsciiEscapesForJSON();
        asciiEscapes['<'] = CharacterEscapes.ESCAPE_CUSTOM;
        asciiEscapes['>'] = CharacterEscapes.ESCAPE_CUSTOM;
        asciiEscapes['&'] = CharacterEscapes.ESCAPE_CUSTOM;
        asciiEscapes['\''] = CharacterEscapes.ESCAPE_CUSTOM;
    }

    @Override
    public int[] getEscapeCodesForAscii() {
        return asciiEscapes;
    }

    @Override
    public SerializableString getEscapeSequence(int ch) {
        return switch (ch) {
            case '<' -> new SerializedString("\\u003C");
            case '>' -> new SerializedString("\\u003E");
            case '&' -> new SerializedString("\\u0026");
            case '\'' -> new SerializedString("\\u0027");
            default -> null;
        };
    }
}
~~~

Đăng ký với JsonFactory:

~~~java
JsonFactory factory = new JsonFactory();
factory.setCharacterEscapes(new HtmlSafeEscapes());

ObjectMapper mapper = new ObjectMapper(factory);
~~~

Khi ghi, các ký tự đã chọn sẽ được biểu diễn bằng escape Unicode. Ví dụ, dấu nhỏ hơn có thể xuất hiện là \u003C thay vì ký tự nhỏ hơn.

CharacterEscapes tác động đến quá trình ghi JSON qua factory/generator đó. Cần cấu hình trước khi mapper được chia sẻ và sử dụng. Hãy kiểm tra API của phiên bản Jackson đang dùng vì một số API factory/builder có thể khác giữa các phiên bản.

Custom escaping chỉ giải quyết cách biểu diễn đầu ra. Nó không thay thế việc encode HTML đúng ngữ cảnh, kiểm soát dữ liệu đầu vào hoặc xây dựng chính sách bảo mật cho ứng dụng.

## 11. Dùng JsonGenerator để ghi chuỗi thủ công an toàn

Khi cần kiểm soát luồng ghi hoặc ghi JSON theo từng phần, có thể dùng JsonGenerator. Các phương thức ghi string của generator tự xử lý dấu ngoặc kép và escape:

~~~java
StringWriter output = new StringWriter();

try (JsonGenerator generator = mapper.getFactory()
        .createGenerator(output)) {
    generator.writeStartObject();
    generator.writeStringField("message", "Xin chào \"mọi người\"");
    generator.writeStringField("path", "C:\\temp\\report.txt");
    generator.writeEndObject();
}

String json = output.toString();
~~~

Trong ví dụ, writeStringField nhận nội dung Java nguyên bản. Generator sẽ escape dấu ngoặc kép bên trong message và dấu gạch chéo ngược trong đường dẫn Windows.

Các phương thức thường dùng:

| Phương thức | Tác dụng |
|---|---|
| writeString(value) | Ghi một JSON string |
| writeStringField(name, value) | Ghi tên field và giá trị string trong object |
| writeStartObject() / writeEndObject() | Bắt đầu/kết thúc JSON object |
| writeStartArray() / writeEndArray() | Bắt đầu/kết thúc JSON array |
| writeRaw(value) | Ghi raw JSON text mà không tự thêm cấu trúc string |
| writeRawValue(value) | Ghi một giá trị JSON raw |

Với dữ liệu chuỗi thông thường, dùng writeString hoặc writeStringField. Không dùng writeRaw để ghi nội dung do người dùng cung cấp.

## 12. Rủi ro khi dùng writeRaw, writeRawValue và @JsonRawValue

writeRaw và writeRawValue bỏ qua một phần cơ chế tạo cấu trúc JSON an toàn của generator. Chúng phù hợp khi ứng dụng đã có một đoạn JSON hợp lệ, đáng tin cậy và cần chèn nguyên văn vào output.

Ví dụ:

~~~java
generator.writeRawValue("{\\"approved\\":true}");
~~~

Đoạn JSON được ghi trực tiếp. Nếu dữ liệu đầu vào chứa dấu ngoặc kép, dấu phẩy hoặc nội dung không hợp lệ, output có thể bị hỏng hoặc thay đổi cấu trúc JSON.

Annotation @JsonRawValue cũng yêu cầu Jackson ghi nội dung của thuộc tính như JSON raw thay vì như một chuỗi JSON thông thường:

~~~java
public class RawPayload {
    @JsonRawValue
    private String json;

    public RawPayload(String json) {
        this.json = json;
    }
}
~~~

Nếu json là {"ok":true}, Jackson chèn object đó vào output. Nếu json là văn bản không phải JSON hợp lệ, output có thể không còn là JSON hợp lệ.

So sánh:

| API | Cách xử lý |
|---|---|
| writeString / writeStringField | Escape nội dung chuỗi theo JSON |
| writeRaw / writeRawValue | Ghi văn bản raw theo yêu cầu của caller |
| @JsonRawValue | Tuần tự hóa thuộc tính như JSON raw |

Chỉ dùng raw output cho dữ liệu JSON đã được tạo hoặc xác thực bởi một nguồn đáng tin cậy. Nếu muốn ghi một chuỗi có nội dung trông giống JSON nhưng thực chất là văn bản, hãy dùng writeString.

## 13. Bảo toàn ký tự xuống dòng, tab và ký tự điều khiển

Java String có thể chứa ký tự newline hoặc tab. Khi Jackson ghi JSON, các ký tự này được escape để không phá vỡ cú pháp string.

~~~java
String message = "Dòng một\\nDòng hai\\tCó tab";
String json = mapper.writeValueAsString(message);

String restored = mapper.readValue(json, String.class);
~~~

Giá trị restored chứa newline và tab thật. Khi in ra terminal, chúng có thể làm văn bản xuống dòng hoặc tạo khoảng cách tab. Đừng nhầm cách terminal hiển thị với nội dung JSON được lưu.

Các ký tự điều khiển khác không có escape ngắn tương ứng có thể được ghi bằng escape Unicode. Ví dụ, một ký tự điều khiển có mã U+0001 có thể được biểu diễn trong JSON là \u0001.

Không nên xóa tất cả ký tự điều khiển một cách máy móc. Một số dữ liệu văn bản hợp lệ có thể cần tab hoặc newline. Nếu ứng dụng muốn cấm các ký tự đó vì quy tắc nghiệp vụ, hãy validate riêng thay vì dựa vào thao tác escape.

## 14. Surrogate pair và ký tự ngoài Basic Multilingual Plane

Java String dùng UTF-16. Một code point ngoài BMP được biểu diễn bởi hai code unit: high surrogate và low surrogate. Emoji là ví dụ dễ gặp.

~~~java
String emoji = "😀";
System.out.println(emoji.length()); // thường là 2 code unit UTF-16
System.out.println(emoji.codePointCount(0, emoji.length())); // 1 code point
~~~

Sự khác nhau giữa length() và codePointCount() là quan trọng khi xử lý ký tự Unicode. length() đếm code unit UTF-16, không phải số ký tự Unicode theo code point.

Jackson có thể ghi ký tự này trực tiếp trong output Unicode hoặc escape thành cặp surrogate tùy cấu hình. Khi đọc JSON có cặp escape đúng, parser tạo lại cặp surrogate trong Java String.

Không nên cắt chuỗi Unicode bằng chỉ số char tùy tiện nếu có khả năng cắt giữa surrogate pair. Nếu cần duyệt hoặc cắt theo code point, dùng các phương thức như codePointAt, offsetByCodePoints và codePointCount.

### Tránh surrogate không ghép cặp

Một Java String có thể bị tạo ra với high surrogate hoặc low surrogate không có cặp. Đây là chuỗi UTF-16 không hợp lệ theo nghĩa Unicode scalar sequence và có thể gây khác biệt giữa parser, encoder hoặc hệ thống nhận.

Nếu dữ liệu đến từ nguồn ngoài, có thể kiểm tra tính hợp lệ của surrogate pair trước khi lưu hoặc gửi. Với dữ liệu nghiệp vụ thông thường, hãy giữ nguyên ký tự hợp lệ và tránh cắt chuỗi ở giữa một cặp surrogate.

## 15. Unicode normalization: ký tự nhìn giống nhau chưa chắc giống nhau

Một số chữ có dấu có thể được biểu diễn theo nhiều chuỗi code point Unicode tương đương về mặt hiển thị. Ví dụ, một ký tự có dấu có thể là:

- Một code point đã được dựng sẵn (precomposed).
- Một chữ cái cơ sở theo sau bởi combining mark.

Hai chuỗi có thể hiển thị giống nhau nhưng so sánh String.equals() vẫn cho kết quả false nếu chuỗi code point khác nhau.

Jackson bảo toàn nội dung chuỗi theo dữ liệu nhận được; nó không tự động chuẩn hóa Unicode về NFC hoặc NFD. Nếu hệ thống cần chuẩn hóa để so sánh, tìm kiếm hoặc tạo khóa nhất quán, hãy thực hiện rõ ràng ở tầng nghiệp vụ:

~~~java
String normalized = Normalizer.normalize(
    input,
    Normalizer.Form.NFC
);
~~~

Chỉ chuẩn hóa khi hợp đồng dữ liệu yêu cầu. Tự ý đổi dạng Unicode có thể làm thay đổi biểu diễn gốc mà một hệ thống khác cần bảo toàn, ví dụ dữ liệu ký số, dữ liệu định danh hoặc nội dung cần so sánh byte chính xác.

## 16. Line separator, paragraph separator và các ký tự đặc biệt

Unicode có những ký tự phân tách dòng như U+2028 (LINE SEPARATOR) và U+2029 (PARAGRAPH SEPARATOR). Chúng khác newline ASCII thông thường. JSON có thể biểu diễn chúng trực tiếp hoặc bằng escape Unicode tùy generator và cấu hình.

Khi JSON được nhúng trực tiếp vào một số ngữ cảnh JavaScript hoặc HTML, các ký tự phân tách này có thể cần xử lý bổ sung theo quy tắc của ngữ cảnh nhúng. Không nên giả định mọi parser JavaScript cũ hoặc mọi cách chèn JSON vào script đều xử lý giống nhau.

Nếu JSON chỉ được gửi như body application/json và được parse bằng thư viện JSON chuẩn, hãy dùng JSON serialization bình thường. Nếu cần nhúng vào HTML, dùng cơ chế serialize an toàn cho ngữ cảnh HTML/JavaScript của framework hoặc một chính sách escape đã được xác định rõ.

## 17. Không nhầm JSON escaping với URL encoding, HTML escaping hoặc Base64

Các cơ chế này giải quyết các vấn đề khác nhau:

| Cơ chế | Mục đích | Ví dụ |
|---|---|---|
| JSON escaping | Bảo đảm chuỗi tuân theo cú pháp JSON | Dấu ngoặc kép thành backslash-quote |
| UTF-8 encoding | Chuyển văn bản Unicode thành byte | Chuỗi tiếng Việt thành byte UTF-8 |
| HTML escaping | Bảo vệ/biểu diễn văn bản trong ngữ cảnh HTML | Dấu nhỏ hơn thành entity HTML |
| URL encoding | Biểu diễn dữ liệu trong thành phần URL | Dấu cách thành %20 |
| Base64 | Biểu diễn byte dưới dạng ký tự ASCII | Byte thành chuỗi Base64 |

Không nên Base64 một chuỗi chỉ để tránh escape JSON. Không URL-encode nội dung trước khi ghi JSON trừ khi giá trị của field thực sự là URL-encoded data theo hợp đồng. Cũng không nên HTML-escape toàn bộ JSON rồi gửi dưới Content-Type application/json; client sẽ nhận các entity HTML như dữ liệu văn bản thay vì ký tự gốc.

## 18. Kiểm tra round-trip Unicode

Một cách đơn giản để kiểm tra việc bảo toàn nội dung là ghi đối tượng thành JSON rồi đọc lại:

~~~java
ObjectMapper mapper = new ObjectMapper();

String original = "Tiếng Việt: ă â ê ô ơ ư; emoji: 😀; quote: \"xin chào\"";

String json = mapper.writeValueAsString(original);
String restored = mapper.readValue(json, String.class);

if (!original.equals(restored)) {
    throw new IllegalStateException("Unicode round-trip failed");
}
~~~

Kiểm tra này xác nhận giá trị Java được bảo toàn qua serializer và parser. Nó không kiểm tra encoding byte của file hoặc HTTP; nếu có bước chuyển byte, cần kiểm tra thêm ở tầng đó.

Ví dụ kiểm tra byte UTF-8:

~~~java
byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
String decoded = new String(bytes, StandardCharsets.UTF_8);

String restoredFromBytes = mapper.readValue(decoded, String.class);
assertEquals(original, restoredFromBytes);
~~~

Nếu cần kiểm tra file, ghi bằng UTF-8 rồi đọc lại bằng UTF-8:

~~~java
Path path = Path.of("unicode-data.json");

try (Writer writer = Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
    mapper.writeValue(writer, original);
}

String fileJson = Files.readString(path, StandardCharsets.UTF_8);
String fileValue = mapper.readValue(fileJson, String.class);
assertEquals(original, fileValue);
~~~

## 19. Ví dụ kiểm tra các ký tự cần escape

JUnit có thể xác nhận nội dung sau khi đọc lại và kiểm tra các escape bắt buộc trong JSON output:

~~~java
class JsonStringTest {

    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void preservesUnicodeAndSpecialCharacters() throws Exception {
        String original =
            "Xin chào \"Mai\"\\\\server\\nDòng hai\\t😀";

        String json = mapper.writeValueAsString(original);
        String restored = mapper.readValue(json, String.class);

        assertEquals(original, restored);
        assertTrue(json.contains("\\\""));
        assertTrue(json.contains("\\\\"));
        assertTrue(json.contains("\\n"));
        assertTrue(json.contains("\\t"));
    }
}
~~~

Các assert về escape giả định generator dùng cách escape JSON thông thường. Nếu ứng dụng bật custom CharacterEscapes hoặc ESCAPE_NON_ASCII, biểu diễn chính xác của JSON có thể khác, nhưng giá trị sau khi đọc lại vẫn cần bằng chuỗi ban đầu.

Nên ưu tiên kiểm tra giá trị round-trip và tính hợp lệ JSON. Chỉ kiểm tra chính xác chuỗi escape khi định dạng escape là một phần của hợp đồng bên ngoài.

## 20. Ghi chú khi tích hợp HTTP

Khi gửi JSON qua HTTP, cần giữ đúng hai lớp:

1. Jackson tạo văn bản JSON hợp lệ.
2. HTTP client hoặc server chuyển văn bản đó thành byte với encoding thống nhất.

Nếu dùng Spring MVC hoặc Spring Boot, các HTTP message converter thường quản lý việc serialize/deserialize body JSON và encoding. Không cần tự chuyển String sang byte rồi ghép header thủ công trong controller nếu framework đã đảm nhiệm việc đó.

Nếu tự tạo HTTP request, hãy gửi body dưới dạng byte UTF-8 hoặc dùng API client có hỗ trợ JSON, đồng thời khai báo Content-Type là application/json. Tránh chuyển JSON thành một chuỗi theo charset hệ thống rồi gửi byte bằng một charset khác.

Với response JSON, client phải parse body theo đúng encoding. Nếu byte đã bị giải mã sai trước khi Jackson nhận String, Jackson không thể khôi phục lại các ký tự đã hỏng.

## 21. Nguyên tắc thực hành

- Lưu và truyền JSON bằng UTF-8 trong các hệ thống mới.
- Đưa chuỗi Java nguyên bản cho ObjectMapper; không tự escape trước khi serialize.
- Dùng readValue để parser giải mã escape sequence; không tự unescape sau khi đọc.
- Bật ESCAPE_NON_ASCII chỉ khi hệ thống đích yêu cầu ASCII-only hoặc một quy ước cụ thể.
- Dùng CharacterEscapes khi thật sự cần escape bổ sung, ví dụ một số ký tự nhạy cảm trong cách nhúng HTML.
- Phân biệt JSON escaping với HTML escaping, URL encoding và Base64.
- Tránh writeRaw, writeRawValue và @JsonRawValue với dữ liệu không tin cậy.
- Không cắt chuỗi UTF-16 tùy tiện giữa một surrogate pair.
- Chỉ chuẩn hóa Unicode khi hợp đồng nghiệp vụ yêu cầu.
- Kiểm tra round-trip cả ở mức String và ở mức byte/file/HTTP khi dữ liệu đi qua các tầng encoding.

Jackson bảo toàn nội dung Unicode bằng cách kết hợp parser, serializer và generator theo đúng cú pháp JSON. Ứng dụng chỉ cần xác định rõ encoding ở ranh giới byte, chọn chính sách escape khi có yêu cầu tương thích và tránh can thiệp thủ công vào chuỗi trước hoặc sau quá trình databinding.
