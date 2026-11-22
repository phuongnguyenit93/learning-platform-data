# Kiểm thử Unicode, ký tự thoát và nội dung nhiều dòng

Khi kiểm thử Jackson, một chuỗi hiển thị đúng trên màn hình chưa chắc đã được serialize, truyền tải và deserialize đúng. Cần phân biệt ít nhất ba lớp: giá trị String trong Java, cách giá trị đó được escape trong JSON text và byte encoding dùng để truyền JSON qua file hoặc network.

Ví dụ, ký tự xuống dòng trong Java có thể là một newline thật. Trong JSON string, newline đó phải được biểu diễn bằng escape `\n`; parser đọc JSON sẽ chuyển escape trở lại thành newline trong Java String. Tương tự, một emoji có thể chiếm hai UTF-16 code unit nhưng chỉ là một Unicode code point. Hai chuỗi trông giống nhau cũng có thể dùng Unicode normalization khác nhau và không bằng nhau khi so sánh.

Bài học này trình bày cách viết test để xác nhận đúng giá trị dữ liệu, không phụ thuộc vào một cách escape cụ thể nếu hợp đồng không yêu cầu, đồng thời kiểm tra UTF-8, control characters và nội dung nhiều dòng qua Jackson.

## 1. Ba lớp cần phân biệt khi kiểm thử

Một chuỗi đi qua Jackson thường có ba dạng:

1. **Giá trị Java:** đối tượng `String` gồm các UTF-16 code unit.
2. **JSON representation:** chuỗi JSON có quote và escape theo cú pháp JSON.
3. **Byte representation:** byte của JSON document, thường dùng UTF-8 khi ghi file hoặc gửi HTTP.

Ví dụ giá trị Java:

~~~java
String message = "Dòng thứ nhất\nDòng thứ hai";
~~~

Giá trị này chứa một ký tự line feed ở giữa. Khi serialize thành JSON, Jackson phải escape ký tự đó:

~~~json
{"message":"Dòng thứ nhất\nDòng thứ hai"}
~~~

Trong JSON source, phần `\n` gồm hai ký tự: backslash và chữ n. Sau khi parse, Java String lại chứa một newline thật.

Nếu test chỉ so sánh chuỗi JSON bằng mắt, rất dễ nhầm giữa hai dạng này. Hãy kiểm tra giá trị sau deserialize bằng `assertEquals`, và chỉ kiểm tra JSON text trực tiếp khi format text là một phần của contract.

## 2. Unicode: byte, code unit, code point và ký tự hiển thị

Unicode có nhiều khái niệm khác nhau:

- **Byte:** đơn vị lưu trữ trong UTF-8 hoặc một encoding khác.
- **UTF-16 code unit:** đơn vị 16 bit mà Java String sử dụng nội bộ.
- **Unicode code point:** mã Unicode của một ký tự trừu tượng.
- **Grapheme cluster:** đơn vị người dùng thường cảm nhận là một ký tự hiển thị; có thể gồm nhiều code point.

Một ký tự ASCII thường chiếm một byte UTF-8, một UTF-16 code unit và một code point. Nhưng nhiều ký tự khác không có quan hệ một-một như vậy.

| Nội dung | Code point | UTF-16 code unit | Byte UTF-8 |
|---|---:|---:|---:|
| `A` | 1 | 1 | 1 |
| `é` dạng NFC | 1 | 1 | 2 |
| `é` dạng NFD: e + dấu sắc | 2 | 2 | 3 |
| `😀` | 1 | 2 | 4 |

Không dùng `String.length()` để đếm số ký tự người dùng nhìn thấy. Phương thức này trả về số UTF-16 code unit.

Đếm code point:

~~~java
String text = "A😀";

int utf16Units = text.length(); // 3
int codePoints = text.codePointCount(0, text.length()); // 2
~~~

Nếu nghiệp vụ giới hạn số ký tự tên hiển thị, cần quyết định giới hạn theo code point, grapheme cluster hay byte UTF-8. Các giới hạn này khác nhau.

## 3. Ký tự ngoài BMP và surrogate pair

Unicode code point lớn hơn `U+FFFF` được biểu diễn trong Java UTF-16 bằng một cặp surrogate: high surrogate và low surrogate.

Ví dụ emoji grinning face có code point `U+1F600`. Có thể tạo String bằng:

~~~java
String emoji = new String(Character.toChars(0x1F600));

System.out.println(emoji.length()); // 2 UTF-16 code units
System.out.println(
    emoji.codePointCount(0, emoji.length())
); // 1 code point
~~~

Jackson có thể serialize String này thành JSON Unicode. Tùy cấu hình generator, output có thể chứa emoji trực tiếp hoặc biểu diễn bằng hai Unicode escape tương ứng.

Hai dạng JSON sau có cùng giá trị sau khi parse:

~~~json
{"emoji":"😀"}
~~~

~~~json
{"emoji":"\uD83D\uDE00"}
~~~

Không nên yêu cầu serializer luôn chọn một trong hai cách trừ khi hệ thống có contract textual cụ thể. Test quan trọng là giá trị sau parse vẫn bằng String ban đầu.

Test:

~~~java
@Test
void roundTripsSupplementaryUnicodeCharacter() throws Exception {
    String emoji = new String(Character.toChars(0x1F600));

    String json = mapper.writeValueAsString(emoji);
    String restored = mapper.readValue(json, String.class);

    assertEquals(emoji, restored);
    assertEquals(1, restored.codePointCount(0, restored.length()));
    assertEquals(2, restored.length());
}
~~~

Tránh tự cắt chuỗi theo index UTF-16 mà không xét surrogate pair. Cắt giữa high và low surrogate có thể tạo String không hợp lệ về mặt Unicode scalar value.

## 4. Unicode normalization: NFC và NFD

Một ký tự nhìn giống nhau có thể được biểu diễn bằng nhiều chuỗi code point.

Ví dụ chữ é:

- NFC: một code point U+00E9.
- NFD: chữ e U+0065 theo sau combining acute accent U+0301.

Trong Java:

~~~java
import java.text.Normalizer;

String nfc = Normalizer.normalize("é", Normalizer.Form.NFC);
String nfd = Normalizer.normalize("é", Normalizer.Form.NFD);

System.out.println(nfc.equals(nfd)); // false
~~~

Jackson không tự động chuẩn hóa Unicode. Nó serialize và deserialize các code point trong String theo dữ liệu nhận được.

Vì vậy, test round-trip cần phân biệt hai mục tiêu:

- **Bảo toàn nguyên trạng:** kết quả phải giữ đúng chuỗi đầu vào, kể cả NFC/NFD.
- **Chuẩn hóa theo nghiệp vụ:** ứng dụng chủ động normalize trước khi lưu hoặc so sánh.

Nếu contract yêu cầu NFC, normalize ở boundary của ứng dụng:

~~~java
String normalized = Normalizer.normalize(input, Normalizer.Form.NFC);
~~~

Không tự normalize trong custom serializer nếu mục tiêu của serializer là bảo toàn dữ liệu. Chuẩn hóa có thể làm thay đổi chuỗi code point dù nội dung hiển thị không đổi.

Test bảo toàn nguyên trạng:

~~~java
@Test
void preservesUnicodeNormalizationForm() throws Exception {
    String nfc = Normalizer.normalize("é", Normalizer.Form.NFC);
    String nfd = Normalizer.normalize("é", Normalizer.Form.NFD);

    assertNotEquals(nfc, nfd);

    assertEquals(nfc, mapper.readValue(
        mapper.writeValueAsString(nfc),
        String.class
    ));

    assertEquals(nfd, mapper.readValue(
        mapper.writeValueAsString(nfd),
        String.class
    ));
}
~~~

Nếu API chọn NFC, hãy test riêng rằng bước normalization của ứng dụng trả về NFC; đừng gán trách nhiệm đó cho Jackson.

## 5. Những ký tự cần escape trong JSON string

JSON string bắt đầu và kết thúc bằng dấu quote kép. Một số ký tự phải được escape để không phá cú pháp:

| Ký tự trong giá trị | Dạng escape JSON phổ biến |
|---|---|
| Quote kép `"` | `\"` |
| Backslash `\` | `\\` |
| Backspace | `\b` |
| Form feed | `\f` |
| Newline / LF | `\n` |
| Carriage return / CR | `\r` |
| Tab | `\t` |
| Control character U+0000 đến U+001F | `\uXXXX` |

JSON không cho phép các control character U+0000 đến U+001F xuất hiện thô bên trong string. Chúng phải được escape.

Ví dụ giá trị Java:

~~~java
String value = "quote: \" ; path: C:\\temp\\file.txt ; tab:\tend";
~~~

Jackson tự escape quote, backslash và tab khi serialize:

~~~java
String json = mapper.writeValueAsString(value);
~~~

Không tự thay quote hoặc backslash trước khi đưa String vào Jackson. Làm vậy có thể khiến dữ liệu bị escape hai lần.

## 6. Kiểm tra escape bằng round-trip

Một test tốt có thể kết hợp nhiều ký tự đặc biệt:

~~~java
@Test
void roundTripsQuotesBackslashesAndControlCharacters()
        throws Exception {

    String original =
        "quote=\"; slash=\\; tab=\t; backspace=\b; formfeed=\f";

    String json = mapper.writeValueAsString(original);
    String restored = mapper.readValue(json, String.class);

    assertEquals(original, restored);
}
~~~

Test này xác nhận giá trị sau deserialize đúng bằng đầu vào, bao gồm cả ký tự điều khiển.

Có thể kiểm tra một số escape bắt buộc trong output nếu cần xác nhận JSON text hợp lệ:

~~~java
assertTrue(json.contains("\\\""));
assertTrue(json.contains("\\\\"));
assertTrue(json.contains("\\t"));
~~~

Lưu ý: cách serializer chọn escape cho một số ký tự có thể thay đổi theo cấu hình hoặc phiên bản. Chỉ assert spelling cụ thể nếu nó là yêu cầu của contract. Với phần lớn ứng dụng, round-trip và parseability quan trọng hơn một chuỗi JSON có hình thức chính xác từng ký tự.

## 7. Escape Unicode và ký tự Unicode literal có cùng giá trị

Một ký tự có thể xuất hiện trực tiếp trong JSON UTF-8 hoặc được viết bằng Unicode escape.

Hai JSON string:

~~~json
{"city":"Hồ Chí Minh"}
~~~

~~~json
{"city":"H\u1ED3 Ch\u00ED Minh"}
~~~

sau parse phải tạo cùng một Java String.

Ví dụ test:

~~~java
@Test
void parsesLiteralAndEscapedUnicodeToSameValue() throws Exception {
    String literal = "{\"city\":\"Hồ Chí Minh\"}";
    String escaped = "{\"city\":\"H\\u1ED3 Ch\\u00ED Minh\"}";

    JsonNode literalNode = mapper.readTree(literal);
    JsonNode escapedNode = mapper.readTree(escaped);

    assertEquals(
        literalNode.get("city").textValue(),
        escapedNode.get("city").textValue()
    );
}
~~~

Trong Java source, dấu backslash của JSON escape phải được viết thành `\\` để nó còn tồn tại trong String đưa cho Jackson. Nếu viết một Unicode escape không được escape trong source code Java, compiler có thể xử lý nó ngay từ giai đoạn tiền xử lý source.

JSON parser chuyển cả literal Unicode và escape Unicode thành cùng giá trị String. Vì vậy, đừng so sánh raw JSON text khi điều bạn cần kiểm tra là giá trị dữ liệu.

## 8. JSON string không được chứa newline thô

Đây là một lỗi phổ biến khi tạo JSON thủ công. JSON cho phép whitespace giữa các token, nhưng không cho phép line break thô nằm bên trong string literal.

JSON hợp lệ:

~~~json
{"message":"Dòng 1\nDòng 2"}
~~~

JSON không hợp lệ:

~~~text
{"message":"Dòng 1
Dòng 2"}
~~~

Dạng thứ hai có newline thật giữa hai dấu quote. Parser phải báo lỗi cú pháp.

Test:

~~~java
@Test
void rejectsRawNewlineInsideJsonString() {
    String invalidJson = "{\"message\":\"Dòng 1\nDòng 2\"}";

    assertThrows(
        JsonProcessingException.class,
        () -> mapper.readTree(invalidJson)
    );
}
~~~

Không nhầm newline trong JSON source với newline trong giá trị sau parse. JSON escape `\n` hợp lệ và được chuyển thành newline trong Java String.

## 9. Nội dung nhiều dòng trong Java text block

Java text block giúp viết JSON nhiều dòng dễ đọc, nhưng cần phân biệt newline thuộc format JSON với newline thuộc giá trị string.

Ví dụ JSON document nhiều dòng, trong đó giá trị message có newline được escape:

~~~java
String json = """
    {
      "message": "Dòng thứ nhất\\nDòng thứ hai"
    }
    """;

Message message = mapper.readValue(json, Message.class);

assertEquals("Dòng thứ nhất\nDòng thứ hai", message.message());
~~~

Trong Java text block, `\\n` tạo ra hai ký tự backslash và n trong JSON text. Jackson parse escape đó thành newline trong giá trị.

Nếu viết `\n` đơn trong phần JSON string của Java text block, Java sẽ tạo newline thật bên trong JSON string và làm JSON không hợp lệ.

Text block cũng loại bỏ incidental indentation theo quy tắc Java. Nếu test cần xác nhận chính xác whitespace đầu dòng hoặc cuối dòng, hãy tạo expected value rõ ràng và kiểm tra bằng `assertEquals` thay vì dựa vào cách căn lề của source.

## 10. Phân biệt LF, CRLF và CR

Hệ điều hành có thể dùng quy ước line ending khác nhau:

- LF: U+000A, thường dùng trên Linux/macOS.
- CRLF: U+000D theo sau U+000A, thường dùng trên Windows.
- CR: U+000D, xuất hiện trong một số dữ liệu cũ.

Trong một JSON document, line ending giữa các property là whitespace bên ngoài string và thường không làm thay đổi giá trị sau parse.

Nhưng nếu line ending nằm trong giá trị string, CR và LF là hai code point khác nhau. Không tự thay CRLF thành LF nếu contract yêu cầu bảo toàn nguyên trạng.

Test đọc JSON document có CRLF bên ngoài string:

~~~java
@Test
void parsesDocumentWithCrLfWhitespace() throws Exception {
    String json = "{\r\n  \"name\": \"An\",\r\n  \"active\": true\r\n}";

    JsonNode node = mapper.readTree(json);

    assertEquals("An", node.get("name").textValue());
    assertTrue(node.get("active").booleanValue());
}
~~~

Test giá trị có CRLF bên trong string:

~~~java
@Test
void preservesCrLfInsideStringValue() throws Exception {
    String original = "first\r\nsecond";

    String json = mapper.writeValueAsString(original);
    String restored = mapper.readValue(json, String.class);

    assertEquals(original, restored);
    assertTrue(restored.contains("\r\n"));
}
~~~

Đừng dùng `trim()` hoặc thay newline toàn cục trong pipeline serialize nếu whitespace là nội dung người dùng nhập.

## 11. Ghi JSON ra UTF-8 bytes và đọc lại

`writeValueAsString()` trả Java String. Nó không kiểm tra cách chuỗi được encode khi ghi ra file hoặc HTTP.

Để kiểm tra UTF-8 byte representation:

~~~java
import java.nio.charset.StandardCharsets;

@Test
void writesAndReadsJsonAsUtf8Bytes() throws Exception {
    Message original = new Message("Tiếng Việt và emoji 😀");

    byte[] jsonBytes = mapper.writeValueAsBytes(original);

    String jsonText = new String(jsonBytes, StandardCharsets.UTF_8);
    assertTrue(jsonText.contains("Tiếng Việt"));

    Message restored = mapper.readValue(jsonBytes, Message.class);
    assertEquals(original, restored);
}
~~~

Jackson dùng UTF-8 cho `writeValueAsBytes()` của JSON mapper. Khi tự chuyển String thành bytes, luôn chỉ rõ charset:

~~~java
byte[] utf8 = jsonText.getBytes(StandardCharsets.UTF_8);
String decoded = new String(utf8, StandardCharsets.UTF_8);
~~~

Tránh các overload `getBytes()` hoặc `new String(bytes)` không chỉ định charset vì chúng phụ thuộc default charset của runtime.

Nếu dùng `OutputStream`, có thể tạo generator với encoding rõ ràng:

~~~java
JsonFactory factory = new JsonFactory();

try (JsonGenerator generator =
         factory.createGenerator(output, JsonEncoding.UTF8)) {
    generator.writeStartObject();
    generator.writeStringField("message", "Xin chào 😀");
    generator.writeEndObject();
}
~~~

Ở chiều đọc, parser có thể nhận UTF-8 bytes trực tiếp từ `InputStream`. Không cần decode toàn bộ stream thành String trước khi parse.

## 12. Literal Unicode hay escape toàn bộ ký tự ngoài ASCII?

Mặc định, JSON generator thường có thể ghi nhiều ký tự Unicode trực tiếp trong output UTF-8. Ví dụ:

~~~json
{"message":"Xin chào"}
~~~

Một số hệ thống muốn mọi ký tự ngoài ASCII được ghi bằng Unicode escape:

~~~json
{"message":"Xin ch\u00E0o"}
~~~

Hai dạng có cùng giá trị sau parse. Việc escape toàn bộ non-ASCII có thể hữu ích với consumer legacy hoặc nơi chỉ chấp nhận ASCII text, nhưng làm output khó đọc hơn và tăng kích thước.

Jackson có feature để escape non-ASCII; tên API phụ thuộc release line. Ở các bản Jackson Core cũ thường gặp `JsonGenerator.Feature.ESCAPE_NON_ASCII`; các bản mới có API feature tương ứng trong `JsonWriteFeature`.

Không nên viết test yêu cầu mọi ký tự ngoài ASCII luôn được escape nếu contract chỉ yêu cầu JSON UTF-8 hợp lệ. Thay vào đó, parse output và so sánh giá trị. Nếu contract thật sự yêu cầu ASCII-only output, test riêng chính sách generator đó.

## 13. U+2028, U+2029 và các ký tự Unicode đặc biệt

Unicode có một số ký tự phân tách dòng/đoạn như U+2028 LINE SEPARATOR và U+2029 PARAGRAPH SEPARATOR. Chúng khác LF và CR.

Trong JSON, chúng có thể xuất hiện dưới dạng Unicode literal hoặc escape tùy serializer và cấu hình. Consumer Java thường có thể giữ chúng như các ký tự trong String.

Test nên kiểm tra giá trị sau parse:

~~~java
@Test
void roundTripsUnicodeLineAndParagraphSeparators() throws Exception {
    String original = "before\u2028middle\u2029after";

    String json = mapper.writeValueAsString(original);
    String restored = mapper.readValue(json, String.class);

    assertEquals(original, restored);
}
~~~

Nếu JSON được nhúng trong JavaScript hoặc một context khác có quy tắc escaping riêng, hãy áp dụng policy của context đó ở lớp output tương ứng. Không nhầm escaping JSON với HTML/JavaScript escaping.

## 14. Malformed escape và Unicode surrogate không hợp lệ

Một số JSON string sai cú pháp:

~~~text
{"value":"bad\q"}
{"value":"bad\u12G4"}
{"value":"trailing\"}
~~~

Các trường hợp này chứa escape không hợp lệ hoặc string chưa đóng. Jackson cần từ chối thay vì âm thầm sửa nội dung.

Test có thể xác nhận parser ném lỗi:

~~~java
@Test
void rejectsMalformedJsonEscapes() {
    assertThrows(
        JsonProcessingException.class,
        () -> mapper.readTree("{\"value\":\"bad\\q\"}")
    );

    assertThrows(
        JsonProcessingException.class,
        () -> mapper.readTree("{\"value\":\"bad\\u12G4\"}")
    );
}
~~~

Unicode supplementary characters được biểu diễn trong UTF-16 bằng surrogate pair. Một high surrogate không có low surrogate tương ứng hoặc một low surrogate đứng riêng không phải Unicode scalar value hợp lệ.

Cách parser/generator phản ứng với unpaired surrogate có thể phụ thuộc phiên bản, input source và cấu hình. Không dựa vào việc chúng luôn được thay thế hay luôn bị từ chối. Ở boundary của ứng dụng, nếu dữ liệu phải là Unicode hợp lệ, hãy xác thực surrogate pair và có policy rõ ràng cho dữ liệu lỗi.

## 15. Kiểm thử property name có Unicode

Tên property JSON cũng là string, nên có thể chứa Unicode và escape:

~~~json
{
  "thành_phố": "Đà Nẵng"
}
~~~

hoặc:

~~~json
{
  "th\u00E0nh_ph\u1ED1": "Đà Nẵng"
}
~~~

Parser sẽ giải mã tên field trước khi Jackson tìm property. Nếu DTO dùng `@JsonProperty`, tên phải khớp với tên JSON sau khi giải mã.

~~~java
public record Location(
    @JsonProperty("thành_phố") String city
) {}
~~~

Test:

~~~java
@Test
void bindsUnicodePropertyName() throws Exception {
    String json = "{\"th\\u00E0nh_ph\\u1ED1\":\"Đà Nẵng\"}";

    Location location = mapper.readValue(json, Location.class);

    assertEquals("Đà Nẵng", location.city());
}
~~~

Nếu tên property có thể được gửi theo nhiều Unicode normalization form, cần quy định rõ có normalize field name hay không. Jackson không tự chuẩn hóa tên property; NFC và NFD có thể được xem là hai tên khác nhau.

## 16. So sánh giá trị, không phụ thuộc cách viết escape

Các JSON string sau có thể cùng biểu diễn một giá trị:

~~~json
{"value":"A"}
~~~

~~~json
{"value":"\u0041"}
~~~

Dạng thứ hai là cách viết escape hợp lệ của chữ A. Cả hai parse thành cùng một Java String.

Test hợp đồng nên ưu tiên:

~~~java
JsonNode node = mapper.readTree(json);
assertEquals("A", node.get("value").textValue());
~~~

Chỉ so sánh raw JSON text khi format byte/text là một phần của giao thức, ví dụ chữ ký số trên canonical JSON, snapshot output có chủ đích hoặc một hệ thống downstream yêu cầu một dạng escape cố định.

Nếu cần canonical JSON để ký hoặc hash, dùng một canonicalization scheme được xác định rõ. `writeValueAsString()` mặc định không tự đảm bảo mọi cách serialize tương đương sẽ cho cùng byte sequence.

## 17. Ví dụ JUnit hoàn chỉnh cho nội dung nhiều dòng và Unicode

Một test DTO có thể bao gồm tiếng Việt, emoji, quote, backslash, tab và newline:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class UnicodeJsonTest {
    private final ObjectMapper mapper = new ObjectMapper();

    record Message(String text) {}

    @Test
    void roundTripsUnicodeAndMultilineText() throws Exception {
        String original =
            "Xin chào 😀\nDòng thứ hai\t\"quoted\" và path C:\\temp";

        String json = mapper.writeValueAsString(new Message(original));

        assertTrue(json.contains("\\n"));
        assertTrue(json.contains("\\t"));

        Message restored = mapper.readValue(json, Message.class);

        assertEquals(original, restored.text());
    }

    @Test
    void parsesEscapedUnicode() throws Exception {
        String json = "{\"text\":\"H\\u1ED3 Ch\\u00ED Minh\"}";

        Message restored = mapper.readValue(json, Message.class);

        assertEquals("Hồ Chí Minh", restored.text());
    }

    @Test
    void preservesUtf8WhenWritingBytes() throws Exception {
        Message original = new Message("Tiếng Việt 😀");

        byte[] bytes = mapper.writeValueAsBytes(original);
        Message restored = mapper.readValue(bytes, Message.class);

        assertEquals(original, restored);
    }
}
~~~

Test này kiểm tra giá trị round-trip và một số escape bắt buộc. Nó không bắt buộc serializer phải ghi tiếng Việt hoặc emoji theo một dạng escape cụ thể.

## 18. Kiểm thử nhiều dòng trong file JSON và JSON Lines

Một JSON document có thể được format nhiều dòng bằng whitespace bên ngoài string:

~~~json
{
  "name": "An",
  "message": "Dòng 1\nDòng 2"
}
~~~

Jackson parse được document đó như một root value.

JSON Lines/NDJSON là định dạng khác: mỗi dòng chứa một JSON document độc lập. Ví dụ:

~~~text
{"id":1,"message":"Dòng 1\nDòng 2"}
{"id":2,"message":"Xin chào"}
~~~

Newline vật lý phân tách record; newline nằm bên trong một string phải được escape thành `\n`. Không đặt raw multiline JSON string trên nhiều dòng trong một record NDJSON.

Khi test NDJSON, đọc từng dòng rồi parse độc lập:

~~~java
@Test
void parsesEachJsonLineAsSeparateRecord() throws Exception {
    String ndjson = """
        {"id":1,"message":"Dòng 1\\nDòng 2"}
        {"id":2,"message":"Xin chào"}
        """;

    List<MessageRecord> records = new ArrayList<>();

    for (String line : ndjson.lines().toList()) {
        records.add(mapper.readValue(line, MessageRecord.class));
    }

    assertEquals(2, records.size());
    assertEquals("Dòng 1\nDòng 2", records.get(0).message());
}
~~~

Ví dụ dùng Java 16+ cho `Stream.toList()`. Với Java version cũ hơn, dùng collector tương ứng. Nếu file có dòng trắng hoặc record lỗi, hành vi bỏ qua/từ chối cần theo contract của ứng dụng.

## 19. Test property-based và test dữ liệu biên

Ngoài một vài ví dụ cố định, có thể sinh chuỗi chứa nhiều loại code point để kiểm tra round-trip:

- ASCII.
- Tiếng Việt có dấu.
- CJK.
- Emoji ngoài BMP.
- Combining marks.
- Quote và backslash.
- Tab, CR, LF.
- Control characters hợp lệ để escape.
- U+2028 và U+2029.

Ví dụ helper kiểm tra một chuỗi:

~~~java
static void assertStringRoundTrip(ObjectMapper mapper, String value)
        throws Exception {
    String json = mapper.writeValueAsString(value);
    String restored = mapper.readValue(json, String.class);

    assertEquals(value, restored);
}
~~~

Nếu dùng property-based testing library, tạo các String có kiểm soát để tránh vô tình sinh unpaired surrogate khi mục tiêu là kiểm tra Unicode scalar values hợp lệ. Có thể tạo code point hợp lệ rồi ghép bằng `appendCodePoint`.

Đối với dữ liệu không hợp lệ, tạo nhóm test riêng cho malformed escape và surrogate sai thay vì trộn với nhóm round-trip hợp lệ.

## 20. Những điều không nên assert trong test

Tránh các assertion quá phụ thuộc cách serializer trình bày:

- Không bắt buộc chữ Việt phải luôn là literal hoặc luôn là `\uXXXX` nếu contract không yêu cầu.
- Không bắt buộc emoji phải xuất hiện trực tiếp thay vì surrogate escapes.
- Không so sánh toàn bộ JSON text khi thứ tự property hoặc escape spelling không phải contract.
- Không dùng `String.length()` làm số ký tự hiển thị.
- Không normalize chuỗi trong test expected nếu ứng dụng phải bảo toàn nguyên trạng.
- Không bỏ qua CR/LF hoặc trim whitespace nếu chúng là nội dung.
- Không dùng default charset của máy chạy test.

Thay vào đó, parse JSON và so sánh giá trị Java, hoặc so sánh UTF-8 bytes khi byte representation thực sự là điều cần kiểm tra.

## 21. Các lỗi thường gặp

**Tự escape String trước khi serialize.** Jackson đã escape quote, backslash và control characters. Escape trước có thể tạo double escaping.

**Nhầm `\n` trong JSON với newline trong giá trị.** JSON source chứa backslash+n; Java String sau parse chứa line feed.

**Đưa raw newline vào JSON string.** Đây là JSON không hợp lệ; serializer sẽ tự escape newline trong giá trị.

**Dùng `String.length()` để đếm Unicode character.** Emoji có thể chiếm hai UTF-16 code unit nhưng một code point.

**Giả định Jackson tự normalize Unicode.** NFC và NFD được giữ riêng nếu ứng dụng không chủ động chuẩn hóa.

**So sánh raw JSON khi chỉ cần so sánh giá trị.** Literal Unicode và `\uXXXX` có thể parse thành cùng String.

**Dùng default charset.** Ghi/đọc file hoặc network nên chỉ định UTF-8 rõ ràng.

**Trim hoặc đổi CRLF thành LF toàn cục.** Điều này có thể làm thay đổi nội dung nhiều dòng mà người dùng gửi.

**Bỏ qua malformed escape.** Escape sai cú pháp phải được từ chối; không âm thầm sửa dữ liệu không tin cậy.

**Kỳ vọng output escape giống nhau ở mọi phiên bản.** Cấu hình generator có thể thay đổi cách biểu diễn text; hãy test contract thực sự cần thiết.

## 22. Ghi nhớ

- Kiểm thử riêng Java String value, JSON escape representation và UTF-8 byte representation.
- JSON string phải escape quote, backslash và control characters; raw newline không được xuất hiện bên trong string literal.
- Jackson tự escape khi serialize và giải mã escape khi deserialize; không escape thủ công trước khi gọi mapper.
- Emoji ngoài BMP chiếm hai UTF-16 code unit trong Java nhưng một Unicode code point.
- NFC và NFD có thể nhìn giống nhau nhưng là hai chuỗi khác nhau; Jackson không tự normalize.
- Nội dung nhiều dòng trong JSON được biểu diễn bằng escape như `\n`; Java text block cần giữ backslash cho JSON input.
- LF, CRLF và CR có thể khác nhau trong giá trị string; không trim hoặc chuyển đổi nếu contract yêu cầu bảo toàn.
- Dùng UTF-8 rõ ràng khi ghi/đọc bytes; không dựa vào default charset.
- So sánh giá trị sau parse thay vì raw JSON text, trừ khi textual/canonical form là một phần của contract.
- Test cả Unicode literal, `\uXXXX`, supplementary characters, control characters, malformed escapes và nhiều dòng.

