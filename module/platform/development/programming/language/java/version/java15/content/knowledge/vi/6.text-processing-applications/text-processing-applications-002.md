# JSON, XML, HTML và ranh giới giữa chuỗi với bộ phân tích trong Java 15+

> **Ngữ cảnh:** Bài thuộc nhóm **Ứng dụng văn bản** của Java 15. Text block giúp viết JSON, XML và HTML nhiều dòng gọn hơn; tuy nhiên, nó vẫn chỉ tạo ra một giá trị `String`. Khi cần hiểu cấu trúc, kiểm tra tính hợp lệ, lấy dữ liệu hoặc tạo đầu ra đúng chuẩn, chương trình phải dùng **parser/serializer theo định dạng**. Kiến thức và API trong bài vẫn áp dụng cho Java hiện đại.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Xác định ranh giới giữa **cú pháp Java**, **giá trị `String`** và **cú pháp JSON/XML/HTML**.
2. Giải thích vì sao text block **không phải trình phân tích**, cũng không tự bảo đảm văn bản bên trong hợp lệ.
3. Dùng parser JSON, XML và HTML phù hợp để biến văn bản thành cấu trúc có thể truy cập.
4. Dùng serializer hoặc DOM API để tạo tài liệu từ dữ liệu động, thay vì ghép chuỗi tùy ý.
5. Phân biệt escape ở lớp Java, escape của JSON, XML entity và HTML entity.
6. Nhận diện sai lầm về XML external entities (XXE), HTML không tin cậy (XSS), kiểm tra kiểu/giới hạn dữ liệu và xử lý lỗi parse.

## 1. Ba tầng phải phân biệt

Hãy hình dung luồng xử lý:

~~~text
Mã nguồn Java (literal / text block)
          |
          v
Java compiler: xử lý cú pháp, indentation, escape
          |
          v
Giá trị java.lang.String
          |
          |  Truyền cho parser phù hợp
          v
JSON tree / XML DOM / HTML DOM
          |
          |  Truy cập node, xác thực dữ liệu, xử lý nghiệp vụ
          v
Giá trị Java / cấu trúc miền nghiệp vụ
          |
          |  Serializer / DOM writer / template engine
          v
JSON / XML / HTML đầu ra
~~~

**Tầng 1 — Java:** Trình biên dịch chỉ cần literal có cú pháp Java hợp lệ. Dấu `"""` là cách viết nhiều dòng cho `String`, được chuẩn hóa trong Java 15. Java compiler có xử lý newline, indentation và escape sequence của text block.

**Tầng 2 — String:** Sau khi biên dịch, Java nắm **dãy ký tự**: `{`, `"`, `<`, `&`, dấu cách, newline... Một `String` không có trường “đã được xác thực JSON” hoặc “an toàn để render HTML”.

**Tầng 3 — Định dạng dữ liệu:** JSON parser kiểm tra token và dựng object/array/scalar; XML parser kiểm tra tài liệu XML và dựng cây/node hoặc phát sự kiện; HTML parser áp dụng quy tắc phân tích HTML, thường có khả năng phục hồi cú pháp thiếu chuẩn. Từng parser có quy tắc riêng, không thể thay lẫn.

### Ví dụ nhỏ: Java chấp nhận một văn bản JSON sai

**Tệp `StringIsNotParser.java` (độc lập, Java 17+):**

~~~java
public class StringIsNotParser {
    public static void main(String[] args) {
        String looksLikeJson = """
            {"name": "Lan",}
            """;

        System.out.println(looksLikeJson.contains("Lan"));
        System.out.println(looksLikeJson instanceof String);
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 StringIsNotParser.java
java StringIsNotParser
~~~

Kết quả:

~~~text
true
true
~~~

Đây là Java hợp lệ, nhưng văn bản `{"name": "Lan",}` có **dấu phẩy cuối** không được phép trong JSON chuẩn. Hai dòng `true` chỉ cho thấy nó là `String` và có chứa từ `Lan`; chúng **không chứng minh tính hợp lệ của JSON**. Việc parser ném lỗi mới phát hiện cú pháp JSON sai.

## 2. Text block thuận tiện cho dữ liệu nhiều dòng, nhưng không thay parser

Ví dụ ba hằng chuỗi:

~~~java
String json = """
    {
      "name": "Lan",
      "active": true
    }
    """;

String xml = """
    <person id="7">
      <name>Lan &amp; Minh</name>
    </person>
    """;

String html = """
    <section>
      <h2>Thông báo</h2>
      <p>Xin chào <strong>Lan</strong></p>
    </section>
    """;
~~~

Đây là **đoạn mã minh họa đặt bên trong một phương thức Java**, không phải tệp độc lập. Tất cả biến đều có kiểu `String`. Các dấu ngoặc nhọn, thẻ XML/HTML, khóa JSON và entity `&amp;` chỉ được hiểu như **ký tự** tại tầng String. Chỉ khi truyền cho parser tương ứng, chương trình mới có thể xác định node `name`, thuộc tính `id` hay phần tử `h2`.

### Những quy tắc text block quan trọng

- Dấu mở `"""` phải theo sau bởi một line terminator trong mã nguồn; line terminator ngay sau dấu mở không tự trở thành ký tự đầu tiên của giá trị.
- Trình biên dịch chuẩn hóa line terminator của text block thành LF, loại bỏ **incidental indentation** và trailing whitespace phụ.
- Dấu đóng `"""` trên dòng riêng thường tạo **LF ở cuối** giá trị; đặt dấu đóng ngay cuối nội dung cuối thì có thể không có LF cuối.
- Escape như `\n`, `\t`, `\s` và `\\` được **Java** xử lý sau bước loại bỏ khoảng trắng.
- Sau các bước trên, kết quả là `String` bình thường; parser JSON/XML/HTML nhận đúng chuỗi này, không nhìn thấy cách mã nguồn ban đầu được viết.

Nếu khoảng trắng có ý nghĩa (nội dung `<pre>` của HTML, XML mixed content, giá trị chuỗi JSON), hãy xác nhận **giá trị sau xử lý của Java** bằng test. Text block không tự đảm bảo indentation hoặc newline bên trong phù hợp mong muốn.

## 3. Hai lớp escape: Java và định dạng đích

**Đừng nhầm escape của Java với escape của JSON/XML/HTML.** Một ký tự có thể phải đi qua nhiều lớp trước khi trở thành dữ liệu cuối cùng.

| Dữ liệu mong muốn | Lớp Java | Lớp tài liệu |
| --- | --- | --- |
| Newline trong một giá trị JSON string | Java phải tạo ra dấu gạch chéo ngược + chữ `n` trong văn bản JSON | JSON parser đọc `\n` và trả về newline trong giá trị |
| Dấu `"` trong giá trị JSON | Java `String` có thể chứa dấu ngoặc kép thông thường | JSON serializer phải escape nó khi đặt trong JSON string |
| Ký tự `&` trong nội dung XML | Java lưu `&` như ký tự bình thường | XML serializer xuất thành `&amp;` trong text node |
| Ký tự `<` trong XML text node | Java lưu `<` bình thường | XML serializer xuất `&lt;` |
| Văn bản người dùng chứa `<` trong HTML | Java lưu đúng giá trị đầu vào | Template engine/output encoder phải escape theo **ngữ cảnh HTML** |

### Ví dụ: muốn JSON chứa escape `\n`

**Tệp `JsonEscapeLayers.java` (độc lập, Java 17+):**

~~~java
public class JsonEscapeLayers {
    public static void main(String[] args) {
        String json = """
            {"message": "A\\nB"}
            """;

        System.out.println(json.contains("\\n"));
        System.out.println(json.contains("A\nB"));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 JsonEscapeLayers.java
java JsonEscapeLayers
~~~

Kết quả:

~~~text
true
false
~~~

Giải thích: Viết `\\n` trong mã nguồn text block khiến Java tạo **hai ký tự** `\` và `n` ở văn bản JSON. Đó chính là escape `\n` mà JSON parser có thể nhận. Nếu viết `\n` của Java ở bên trong một JSON string literal, Java biến nó thành newline thực **ngay trong dấu ngoặc kép JSON**, thường khiến JSON không hợp lệ.

**Quy tắc khi có dữ liệu động:** Đừng tự xây dựng JSON qua `"\"message\":\"" + input + "\""` hoặc `formatted(input)`. Dấu ngoặc kép, newline, backslash và các ký tự điều khiển trong `input` có thể phá định dạng; dùng **JSON serializer** để mã hóa dữ liệu.

## 4. JSON: parse thành dữ liệu có kiểu, serialize từ dữ liệu Java

JSON có các kiểu cấu trúc **object**, **array** và giá trị **string**, **number**, **boolean**, **null**. JSON chuẩn yêu cầu:
- Tên thuộc tính object là chuỗi trong dấu ngoặc kép.
- Dấu ngoặc kép bên trong string phải được escape.
- Không sử dụng comment kiểu `//` hoặc `/* ... */`.
- Không có dấu phẩy cuối trong array/object.
- Giá trị số, boolean và null có cú pháp riêng; `"true"` là string, `true` là boolean.

JDK không cung cấp một JSON tree parser phổ quát sẵn trong `java.base`. Trong các ứng dụng Java hiện đại, có thể dùng thư viện chuyên dụng như **Jackson** để parse và serialize JSON. Ví dụ dưới đây dùng **Jackson 3.2.4** (Java 17+), thuộc nhánh đang được phát triển, với package `tools.jackson.*`. Không trộn import của Jackson 2 (`com.fasterxml.jackson.*`) vào ví dụ Jackson 3.

### 4.1. Cài thư viện cho hai ví dụ JSON/HTML

Với một **ứng dụng Gradle Java đơn giản**, tạo `build.gradle` như sau:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'tools.jackson.core:jackson-databind:3.2.4'
    implementation 'org.jsoup:jsoup:1.24.1'
}

application {
    mainClass = 'JsonBoundaryDemo'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Đặt mã Java ở `src/main/java/JsonBoundaryDemo.java`. Nếu dự án đã có Gradle Wrapper, chạy `./gradlew run` trên macOS/Linux hoặc `gradlew.bat run` trên Windows; nếu Gradle đã cài toàn cục, dùng `gradle run`. Với ví dụ HTML bên dưới, đổi `mainClass` thành `HtmlBoundaryDemo` rồi chạy tương tự. Hai dependency được nêu cụ thể để ví dụ có thể biên dịch trong dự án có kết nối Maven Central.

Nếu ứng dụng hiện có sử dụng một phiên bản Jackson/jsoup khác, tuân theo BOM/quản lý phiên bản của dự án; giữ **package và API** nhất quán với major version đang dùng.

### 4.2. Ví dụ JSON hoàn chỉnh: parse + serialize

**Tệp `src/main/java/JsonBoundaryDemo.java`:**

~~~java
import java.util.Map;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

public class JsonBoundaryDemo {
    public static void main(String[] args) {
        JsonMapper mapper = JsonMapper.builder().build();

        String json = """
            {
              "name": "Lan",
              "active": true
            }
            """;

        JsonNode root = mapper.readTree(json);
        System.out.println(root.path("name").asString());
        System.out.println(root.path("active").booleanValue());

        String userInput = "A \"VIP\"\nB";
        String encoded = mapper.writeValueAsString(
            Map.of("message", userInput)
        );

        JsonNode roundTrip = mapper.readTree(encoded);
        System.out.println(
            roundTrip.path("message").asString().equals(userInput)
        );
        System.out.println(encoded.contains("\\n"));
    }
}
~~~

Chạy qua Gradle theo mục 4.1. Kết quả:

~~~text
Lan
true
true
true
~~~

`readTree()` chuyển văn bản thành **`JsonNode` tree**; `path("name").asString()` đọc giá trị. `writeValueAsString()` lấy dữ liệu Java và tạo **văn bản JSON hợp lệ**, tự escape dấu ngoặc kép và newline trong `userInput`. Parse lại rồi `equals()` chứng minh giá trị được giữ nguyên.

**Đừng dùng `asString()`/`asInt()` như phép xác thực schema duy nhất:** Những accessor có thể hỗ trợ chuyển kiểu. Nếu hợp đồng yêu cầu trường bắt buộc, đúng kiểu, đúng khoảng giá trị, phải kiểm tra trường tồn tại và loại node (hoặc deserialize vào kiểu/record có validation). JSON hợp lệ về cú pháp vẫn có thể sai yêu cầu nghiệp vụ.

**Không dùng regex/`substring()` để parse JSON tổng quát:** Ký tự `{`, `,` hoặc `"` có thể xuất hiện trong string đã escape, dữ liệu có thể lồng nhiều cấp, và thứ tự trường không nhất thiết cố định. Chọn parser để hiểu token và cấu trúc.

## 5. XML: parse có cấu trúc và khóa truy cập tài nguyên ngoài

XML có khái niệm **element**, **attribute**, **text node**, **namespace** và **entity reference**. Ví dụ `&amp;` trong XML source biểu diễn ký tự `&` trong nội dung text sau khi parse. XML parser nghiêm ngặt về tài liệu *well-formed*: thẻ đóng/mở khớp nhau, attribute được quote, ký tự đặc biệt trong text phải được escape phù hợp.

Java cung cấp **JAXP** trong module `java.xml`. Các lựa chọn vẫn được sử dụng:
- **DOM (`DocumentBuilderFactory`):** Dựng cây `Document` để truy cập/sửa node; hợp với dữ liệu vừa phải.
- **SAX:** Parser theo sự kiện, thuận lợi khi đọc tài liệu lớn theo luồng.
- **StAX (`XMLInputFactory`):** Duyệt sự kiện/pull parser, kiểm soát luồng theo nhu cầu.
- **Transformer/DOM API:** Tạo hoặc xuất XML từ cấu trúc, tránh ghép dấu `<` và `&` vào văn bản tùy ý.

### 5.1. Vì sao phải cấu hình XML parser an toàn?

Với XML **không tin cậy**, DTD và external entities có thể khiến parser cố đọc tệp nội bộ, truy cập tài nguyên mạng hoặc tiêu tốn tài nguyên. Đây là rủi ro **XML External Entity (XXE)**. Nếu ứng dụng không cần DTD, nên **từ chối DOCTYPE** và chặn truy cập tài nguyên ngoài.

- Bật `XMLConstants.FEATURE_SECURE_PROCESSING` để kích hoạt các giới hạn bảo vệ của JAXP.
- Từ chối `DOCTYPE` bằng feature thích hợp với parser đang dùng.
- Đặt `XMLConstants.ACCESS_EXTERNAL_DTD` và `ACCESS_EXTERNAL_SCHEMA` thành chuỗi rỗng để cấm giao thức ngoài.
- Không bật XInclude nếu không có nhu cầu đã được kiểm soát.
- Nếu parser/provider không hỗ trợ một thiết lập bảo vệ bắt buộc, **dừng xử lý** thay vì bỏ qua lỗi rồi tiếp tục parse.

### 5.2. Ví dụ XML hoàn chỉnh: DOM parser an toàn

**Tệp `XmlBoundaryDemo.java` — chỉ cần JDK 17+, không cần thư viện thứ ba:**

~~~java
import java.io.StringReader;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Document;
import org.xml.sax.InputSource;

public class XmlBoundaryDemo {
    public static void main(String[] args) throws Exception {
        String xml = """
            <order id="7">
              <customer>Lan &amp; Minh</customer>
              <amount currency="USD">15</amount>
            </order>
            """;

        DocumentBuilderFactory factory =
                DocumentBuilderFactory.newDefaultInstance();
        factory.setNamespaceAware(true);
        factory.setFeature(
                "http://apache.org/xml/features/disallow-doctype-decl",
                true);
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        factory.setXIncludeAware(false);

        Document doc = factory.newDocumentBuilder().parse(
                new InputSource(new StringReader(xml))
        );

        System.out.println(doc.getDocumentElement().getTagName());
        System.out.println(doc.getDocumentElement().getAttribute("id"));
        System.out.println(
                doc.getElementsByTagName("customer")
                   .item(0).getTextContent()
        );
        System.out.println(
                doc.getElementsByTagName("amount")
                   .item(0).getTextContent()
        );
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 XmlBoundaryDemo.java
java XmlBoundaryDemo
~~~

Kết quả:

~~~text
order
7
Lan & Minh
15
~~~

`"Lan &amp; Minh"` nằm trong **String XML thô**. Sau khi đi qua DOM parser, `getTextContent()` trả về `"Lan & Minh"`. Việc parse cũng tách được `id="7"` khỏi phần text và xác định phần tử `customer`.

Đoạn mã dùng **JAXP default implementation của JDK** qua `newDefaultInstance()` để các thiết lập bảo vệ có hành vi xác định hơn. Khi sử dụng provider XML khác, vẫn phải kiểm tra khả năng hỗ trợ và thực thi các thiết lập bảo vệ. Trong ứng dụng thực, hãy giới hạn kích thước đầu vào, số node/độ sâu và xử lý exception theo chính sách; riêng việc chặn XXE **không thay thế** giới hạn tài nguyên.

**Tạo XML động:** Hãy tạo `Document`/`Element`, dùng `setTextContent(input)` cho text node hoặc `setAttribute(name, value)` cho attribute, rồi xuất qua serializer/Transformer được cấu hình an toàn. Serializer sẽ xử lý `&`, `<` và dấu ngoặc theo đúng ngữ cảnh. Ghép thủ công `"<name>" + input + "</name>"` dễ tạo XML hỏng hoặc thay đổi cấu trúc nếu input có `<` hay `&`.

### 5.3. XML String và encoding

Với tài liệu được đọc từ **bytes**, decoding từ UTF-8/UTF-16 phải được thực hiện nhất quán với khai báo encoding và giao thức truyền nhận. Nếu đã truyền một `StringReader` cho parser, nội dung **đã là các ký tự Java**; parser không còn giải mã lại từ byte stream. Không tự sửa encoding declaration mà không hiểu dữ liệu nguồn, và đừng nhầm `String.length()` với số byte trên dây.

## 6. HTML: parser phục hồi cú pháp, sanitizer quyết định nội dung an toàn

HTML và XML **không dùng cùng một bộ quy tắc phân tích**. HTML parser có thể tự đóng thẻ, bổ sung các nút `html`/`head`/`body` còn thiếu hoặc sửa nhiều cấu trúc không chuẩn theo HTML parsing rules. XML parser thường báo lỗi khi tài liệu không well-formed.

Trong Java, **jsoup** là một lựa chọn phổ biến để parse HTML thành DOM:
- `Jsoup.parse(html)` chuyển `String` sang `Document`.
- `doc.selectFirst("h2")` truy vấn theo CSS selector.
- `element.text()` lấy **văn bản**, giải mã HTML entities phù hợp và bỏ cấu trúc thẻ trong cách lấy text.
- `Jsoup.clean(untrustedHtml, Safelist.basic())` lọc một **HTML fragment** theo danh sách cho phép (safelist) về thẻ, thuộc tính và giao thức URL.

**Rất quan trọng:** `Jsoup.parse()` **chỉ phân tích** HTML, không tự làm sạch mọi nội dung độc hại. Khi render HTML từ người dùng, cần **output encoding đúng ngữ cảnh** hoặc **sanitization theo safelist phù hợp**. Dù đã parse được, nội dung vẫn phải được xem là không tin cậy.

### Ví dụ HTML hoàn chỉnh: parse + sanitize

**Tệp `src/main/java/HtmlBoundaryDemo.java` (jsoup 1.24.1):**

~~~java
import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;
import org.jsoup.safety.Safelist;

public class HtmlBoundaryDemo {
    public static void main(String[] args) {
        String html = """
            <section>
              <h2>Thông báo</h2>
              <p>Lan &amp; Minh</p>
            </section>
            """;

        Document doc = Jsoup.parse(html);
        System.out.println(doc.selectFirst("h2").text());
        System.out.println(doc.selectFirst("p").text());

        String untrusted =
                "<p>Chào <b>Lan</b></p><script>alert(1)</script>";
        String sanitized = Jsoup.clean(untrusted, Safelist.basic());

        System.out.println(sanitized.contains("<script"));
        System.out.println(
                Jsoup.parseBodyFragment(sanitized)
                     .selectFirst("p").text()
        );
    }
}
~~~

Đổi `application.mainClass` trong `build.gradle` thành `'HtmlBoundaryDemo'` và chạy `./gradlew run` hoặc `gradlew.bat run`. Kết quả:

~~~text
Thông báo
Lan & Minh
false
Chào Lan
~~~

`Jsoup.parse()` chuyển HTML thành cây; entity `&amp;` được đọc thành ký tự `&` trong text. `Jsoup.clean()` loại các thẻ và thuộc tính không nằm trong `Safelist.basic()`, bao gồm thẻ `script` trong trường hợp trên.

**Phạm vi của sanitizer:** `Safelist.basic()` dành cho **HTML fragment**, không phải một cơ chế xác thực toàn bộ website. Chỉ mở rộng safelist khi có nhu cầu và đã xem xét thẻ, thuộc tính URL, giao thức và ngữ cảnh render. Nếu nội dung là **plain text**, cách đơn giản hơn thường là render qua template engine có cơ chế **HTML escaping** mặc định, thay vì cho phép raw HTML.

### 6.1. Đọc HTML khác đưa HTML lên trang

- **Đọc dữ liệu:** `Jsoup.parse(...)`, DOM traversal, selector, `text()`.
- **Render dữ liệu người dùng như văn bản:** escape theo ngữ cảnh HTML text node hoặc dùng API frontend như `textContent`.
- **Render một đoạn HTML được cho phép:** sanitize với safelist phù hợp rồi đưa vào đúng vị trí được thiết kế để nhận HTML.
- **Render trong thuộc tính, URL, JavaScript hoặc CSS:** mỗi ngữ cảnh có quy tắc riêng. Chỉ thay `<` thành `&lt;` hoặc gọi HTML sanitizer không tự động làm an toàn mọi ngữ cảnh chèn dữ liệu.

## 7. Khác biệt về escape và kiểm tra tính hợp lệ

| Góc nhìn | JSON | XML | HTML |
| --- | --- | --- | --- |
| Cấu trúc | Object, array, string, number, boolean, null | Element, attribute, text, namespace | DOM HTML với tag, attribute, text |
| Hành vi với cú pháp sai | Parser chuẩn thường báo lỗi | Parser strict báo lỗi tài liệu không well-formed | Parser có thể tự sửa/khôi phục nhiều lỗi |
| Văn bản `&amp;` | Chỉ là các ký tự trong JSON string nếu đã escape đúng | Entity trong XML text; khi parse thành `&` | HTML entity; khi lấy text thành `&` |
| Dữ liệu động | JSON serializer | DOM/writer/serializer XML | Output encoder hoặc sanitized HTML |
| API Java minh họa | Jackson `JsonMapper` | JAXP `DocumentBuilderFactory` | jsoup `Jsoup.parse` |
| Rủi ro thường gặp | Ghép chuỗi sai escape; thiếu kiểm tra kiểu/giới hạn | External entities/DTD, XInclude, resource exhaustion | XSS qua HTML không tin cậy hoặc ngữ cảnh render sai |
| “Parse thành công” đủ an toàn? | **Không**, còn validation/schema và giới hạn tài nguyên | **Không**, còn chính sách external access và dữ liệu | **Không**, parsing khác sanitization |

**Phân biệt ba khái niệm:**

1. **Syntax validation:** Có thể parse theo grammar không? JSON thiếu dấu ngoặc kép hoặc XML không đóng thẻ sẽ lỗi.
2. **Structural/schema validation:** Có đúng những trường, kiểu, namespace, schema và ràng buộc cần thiết không? Một JSON object hợp lệ vẫn có thể thiếu trường bắt buộc.
3. **Business/security validation:** Giá trị có hợp lệ, kích thước hợp lý, có bị chèn cấu trúc vào đầu ra hay tạo thao tác ngoài ý muốn không?

Parser đảm nhiệm tầng cú pháp/cấu trúc cơ bản; các tầng còn lại cần thiết kế và kiểm thử độc lập.

## 8. Hướng dẫn chọn cách làm trong ứng dụng thực tế

### Trường hợp A — Viết mẫu tĩnh trong source

Dùng text block để giữ một JSON/XML/HTML **cố định, do lập trình viên kiểm soát**. Dùng parser tương ứng hoặc test để chắc chắn mẫu hợp lệ. Đây là trường hợp text block hữu ích nhất: dễ đọc nhiều dòng, dễ so sánh nội dung.

### Trường hợp B — Chèn dữ liệu thay đổi vào cấu trúc

Dùng parser/model/serializer: với JSON, tạo Java object/record/Map rồi serialize; với XML, tạo node và xuất qua XML serializer; với HTML, dùng template engine có encoding mặc định hoặc HTML sanitizer nếu chủ đích chấp nhận markup. **Không dùng `String.formatted()` hay nối chuỗi làm bộ escape.**

### Trường hợp C — Xử lý dữ liệu từ bên ngoài

Giới hạn số byte/ký tự, độ sâu và số phần tử trước hoặc trong quá trình parse; xác thực cấu trúc, kiểu và giá trị; bắt lỗi để trả thông báo hữu ích mà không lộ dữ liệu nhạy cảm; cấu hình XML external-access; xử lý HTML theo mức tin cậy và ngữ cảnh render. Với dữ liệu lớn, cân nhắc streaming parser/generator thay vì giữ toàn bộ cây trong bộ nhớ.

### Trường hợp D — Dùng dữ liệu đã parse để tạo đầu ra mới

Đừng coi `doc.toString()` hay `node.text()` là phép chuyển đổi tương đương cho mọi yêu cầu. `text()` trả **nội dung text** và bỏ cấu trúc; serializer đưa ra **markup có cấu trúc**. Hai mục đích khác nhau và có thể làm thay đổi whitespace, entity hoặc cách format.

## 9. Lỗi phổ biến

1. **“Text block Java biên dịch được thì JSON/XML/HTML chắc chắn hợp lệ.”** Sai; compiler chỉ xử lý cú pháp Java. Phải parse/validate bằng công cụ của định dạng.
2. **Dùng `contains()`, `split()` hoặc regex để parse toàn bộ JSON/XML/HTML.** Sai khi dữ liệu lồng nhau, có entity hoặc ký tự được escape. Dùng parser.
3. **Chèn dữ liệu người dùng bằng `formatted()` vào JSON.** Có thể phá cú pháp hoặc thay đổi cấu trúc nếu có dấu `"`, backslash hoặc newline. Dùng serializer.
4. **Nhầm `\n` của Java với `\n` của JSON.** Để JSON thô chứa literal `\n`, Java source cần tạo ra backslash + `n`, chẳng hạn bằng `\\n`.
5. **Cho rằng `&amp;` trong một String XML đã là ký tự `&`.** Java String có thể còn chứa `&amp;`; XML parser mới giải entity trong text.
6. **Parse XML không tin cậy với cấu hình mặc định bất kỳ.** Có thể gặp XXE, DTD hoặc external-resource access. Cấm các khả năng không cần thiết và giới hạn tài nguyên.
7. **Cho rằng `Jsoup.parse()` tự làm HTML an toàn để render.** Parsing và sanitization là hai việc khác nhau. Dùng safelist/output encoding thích hợp.
8. **Áp dụng cách xử lý XML cho HTML.** HTML parser có quy tắc sửa lỗi và cấu trúc riêng; không thể coi HTML tổng quát là XML well-formed.
9. **Cho rằng parse hợp lệ đồng nghĩa dữ liệu nghiệp vụ hợp lệ.** Cần kiểm tra field bắt buộc, kiểu, miền giá trị và ràng buộc thực tế.
10. **Bỏ qua newline cuối và indentation text block.** Giá trị Java truyền cho parser có thể có whitespace ngoài dự kiến. Test chuỗi thực và parser behavior.
11. **Phụ thuộc serializer tạo output byte-for-byte giống source.** Parser/serializer có thể thay đổi indentation, attribute order, cách thể hiện entities hoặc style. So sánh theo cấu trúc/ngữ nghĩa khi phù hợp, theo byte chỉ khi hợp đồng yêu cầu.
12. **Tự ý biến văn bản ngoài thành HTML mà không escape đúng ngữ cảnh.** Chuỗi dữ liệu và mã đánh dấu có ranh giới bảo mật; để renderer/encoder xử lý.

## 10. Tự kiểm tra

**Câu 1:** Text block chứa `{"a": 1,}` được Java biên dịch. Có nghĩa nó là JSON hợp lệ không?

**Đáp án:** Không. Text block là `String`; JSON chuẩn không chấp nhận dấu phẩy cuối. JSON parser phải nhận dữ liệu và kiểm tra.

**Câu 2:** Dữ liệu đầu vào là `A "VIP"`. Cách an toàn để xuất trường JSON `message`?

**Đáp án:** Tạo đối tượng Java/Map chứa chuỗi gốc rồi gọi JSON serializer (`writeValueAsString`). Không tự lắp dấu ngoặc kép bằng nối chuỗi.

**Câu 3:** Vì sao XML thô chứa `Lan &amp; Minh` nhưng `getTextContent()` trả `Lan & Minh`?

**Đáp án:** XML parser giải entity `&amp;` thành ký tự `&` của text node.

**Câu 4:** Có thể render ngay chuỗi HTML do người dùng nhập sau `Jsoup.parse()` không?

**Đáp án:** Không tự động. Parse không phải sanitize; phải xác định mức tin cậy, dùng output encoding hoặc safelist thích hợp với vị trí render.

**Câu 5:** Khi nhận XML từ phía ngoài, nên làm gì với DOCTYPE và external entities nếu ứng dụng không dùng chúng?

**Đáp án:** Từ chối DOCTYPE, cấm truy cập DTD/schema ngoài, bật secure processing và dừng nếu thiết lập bảo vệ bắt buộc không áp dụng được.

## Ghi nhớ

- **Text block là cú pháp tạo `String`**; nó không parse hoặc bảo đảm JSON, XML, HTML hợp lệ.
- **Parser biến văn bản thành cấu trúc**; **serializer biến cấu trúc thành văn bản định dạng đúng**.
- **Escape có nhiều tầng:** Java, JSON, XML và HTML xử lý ký tự khác nhau; không lấy cách escape của tầng này thay cho tầng khác.
- **Đầu vào không tin cậy cần thêm kiểm tra:** XML phải hạn chế external access; HTML phải encode hoặc sanitize theo ngữ cảnh; JSON cần validation kiểu/giới hạn.
- **Khi có dữ liệu động, hãy tạo cấu trúc rồi serialize** thay vì dùng text block + nối chuỗi để tự tạo cú pháp.

## Tài liệu tham khảo hiện hành

- [Oracle – Text Blocks](https://docs.oracle.com/en/java/javase/25/language/text-blocks.html)
- [Jackson 3 migration guide](https://github.com/FasterXML/jackson/blob/main/jackson3/MIGRATING_TO_JACKSON_3.md)
- [Jackson 3.2.4 JsonNode API](https://javadoc.io/static/tools.jackson.core/jackson-databind/3.2.4/tools.jackson.databind/tools/jackson/databind/JsonNode.html)
- [Java – JAXP Security Guide](https://docs.oracle.com/en/java/javase/25/security/java-api-xml-processing-jaxp-security-guide.html)
- [OWASP – XML External Entity Prevention](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html)
- [jsoup – Parse HTML](https://jsoup.org/cookbook/input/parse-document-from-string)
- [jsoup – Sanitize untrusted HTML](https://jsoup.org/cookbook/cleaning-html/safelist-sanitizer)
