# Xử lý văn bản và giới hạn của nội dung XML hỗn hợp

XML có thể chứa nhiều loại nội dung bên trong một element: text, element con, comment, processing instruction và các node đặc biệt khác. Một trường hợp quan trọng là **mixed content** — nội dung mà text và element con xen kẽ theo đúng thứ tự. Ví dụ:

```xml
<p>Jackson đọc <em>XML</em> và giữ phần văn bản còn lại.</p>
```

Trong element `p`, có text `Jackson đọc `, element con `em`, rồi lại có text ` và giữ phần văn bản còn lại.`. Thứ tự xen kẽ này mang ý nghĩa nội dung. Nếu gom toàn bộ text vào một chuỗi và gom element con vào một danh sách riêng, ta sẽ mất vị trí của từng đoạn text so với element con.

Jackson XML (`jackson-dataformat-xml`) hỗ trợ ánh xạ XML sang POJO, attribute, element và text content. Annotation `@JacksonXmlText` hữu ích cho element có simple text content, chẳng hạn `<price currency="VND">125000</price>`. Tuy nhiên, mô hình databinding theo property của Jackson XML không phải mô hình tổng quát để bảo toàn mọi chuỗi node text/element xen kẽ trong mixed content. Khi thứ tự xen kẽ phải được giữ chính xác, nên dùng StAX hoặc DOM và biểu diễn nội dung thành danh sách node/segment có thứ tự.

## 1. XML có những loại nội dung nào?

Một XML element có thể chứa:

- **Text node:** đoạn ký tự thông thường giữa các markup.
- **Child element:** element lồng bên trong.
- **Attribute:** metadata nằm trong start tag.
- **CDATA section:** vùng ký tự được viết giữa `<![CDATA[` và `]]>`; về mặt nội dung, nó vẫn biểu diễn text.
- **Comment:** ghi chú XML nằm giữa `<!--` và `-->`.
- **Processing instruction:** chỉ thị dành cho ứng dụng xử lý XML.

Ví dụ:

```xml
<article id="A-100">
  <title>Jackson XML</title>
  <p>Đọc <strong>và ghi</strong> XML.</p>
  <note><![CDATA[A < B là biểu thức văn bản.]]></note>
  <!-- nội dung bổ sung -->
</article>
```

Trong ví dụ này:

- `id` là attribute của `article`.
- `title`, `p`, `note` là child element.
- `p` chứa text, child element `strong`, rồi text tiếp theo: đây là mixed content.
- `note` chứa CDATA section.
- Comment là node riêng, không phải text của `note`.

Không phải mọi XML document đều dùng mixed content. Nhiều XML nghiệp vụ có cấu trúc element-only:

```xml
<order>
  <id>ORD-1001</id>
  <total>250.00</total>
  <status>PAID</status>
</order>
```

Mỗi element chứa text đơn giản hoặc element con theo schema. Mô hình này phù hợp với POJO databinding hơn nhiều so với tài liệu trộn văn bản và markup.

## 2. Phân biệt element-only, simple content và mixed content

Ba dạng nội dung thường gặp:

### 2.1. Element-only content

Element chứa các element con theo cấu trúc xác định:

```xml
<person>
  <name>An</name>
  <age>28</age>
</person>
```

Có thể ánh xạ thành POJO:

```java
public class Person {
    private String name;
    private int age;
}
```

Jackson XML có thể ánh xạ `name` và `age` thành property Java. Khoảng trắng dùng để thụt lề thường không mang ý nghĩa nghiệp vụ của element-only model.

### 2.2. Simple text content

Element có một giá trị text đơn giản, có thể kèm attribute:

```xml
<price currency="VND">125000.50</price>
```

Nội dung chính của element là một giá trị text; `currency` là attribute. Đây là trường hợp phù hợp với `@JacksonXmlText`.

### 2.3. Mixed content

Element chứa text xen kẽ với child element:

```xml
<p>Đọc <code>JsonParser</code> để xử lý <em>token</em>.</p>
```

Nội dung có thứ tự:

1. Text `Đọc `.
2. Element `code` với text `JsonParser`.
3. Text ` để xử lý `.
4. Element `em` với text `token`.
5. Text `.`.

Để biểu diễn chính xác, mô hình Java phải giữ được danh sách các đoạn text và element con theo đúng thứ tự này. Một field `String text` cùng một field `List<Code>` riêng không thể biểu diễn vị trí xen kẽ một cách đầy đủ.

## 3. Jackson XML và @JacksonXmlText

Jackson XML cung cấp `@JacksonXmlText` để đánh dấu property đại diện cho text content trực tiếp của element. Annotation này thường được dùng cho simple content.

Ví dụ model:

```java
import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlProperty;
import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlRootElement;
import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlText;

import java.math.BigDecimal;

@JacksonXmlRootElement(localName = "price")
public class Price {
    @JacksonXmlProperty(isAttribute = true, localName = "currency")
    private String currency;

    @JacksonXmlText
    private BigDecimal amount;

    public String getCurrency() {
        return currency;
    }

    public void setCurrency(String currency) {
        this.currency = currency;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public void setAmount(BigDecimal amount) {
        this.amount = amount;
    }
}
```

Đọc XML:

```java
import com.fasterxml.jackson.dataformat.xml.XmlMapper;

XmlMapper xmlMapper = new XmlMapper();

String xml = "<price currency=\"VND\">125000.50</price>";
Price price = xmlMapper.readValue(xml, Price.class);

System.out.println(price.getCurrency()); // VND
System.out.println(price.getAmount());   // 125000.50
```

Ghi XML:

```java
String output = xmlMapper.writeValueAsString(price);
```

Jackson ghi `currency` thành attribute và `amount` thành text content bên trong element `price`. Đây là ánh xạ tự nhiên cho kiểu có một vùng text chính.

`@JacksonXmlText` không biến POJO thành một danh sách tổng quát chứa mọi text node và child element theo thứ tự. Một class thường có một property text đại diện cho nội dung text của element. Khi text bị ngắt thành nhiều đoạn bởi child element, một chuỗi duy nhất không đủ để giữ vị trí của từng đoạn.

## 4. Vì sao mixed content khó ánh xạ thành POJO thông thường?

POJO databinding thường tổ chức dữ liệu theo property:

```java
public class Paragraph {
    private String text;
    private List<Emphasis> emphasis;
}
```

Nhưng XML mixed content là một chuỗi node có thứ tự:

```xml
<p>Start <em>middle</em> end.</p>
```

Nếu tách thành `text = "Start end."` và `emphasis = ["middle"]`, mô hình không biết phải chèn `emphasis` vào giữa hai phần text ở đâu. Nếu gộp text thành `"Start middle end."`, lại không biết đoạn nào thuộc element `em`.

Vấn đề không chỉ là tên property hoặc thứ tự field khi serialize. Nó là vấn đề mô hình dữ liệu: XML cho phép nhiều loại node xen kẽ trong một danh sách có thứ tự, còn một POJO với các field riêng biệt thường không lưu được chuỗi node đó.

Jackson XML phù hợp với XML có cấu trúc dữ liệu kiểu object/collection và simple text property. Với mixed content cần round-trip đúng thứ tự, hãy dùng mô hình node/segment rõ ràng hoặc API XML cấp thấp.

## 5. Ví dụ model POJO không giữ được vị trí text

Xét XML:

```xml
<p>Xin chào <strong>Jackson</strong>, hôm nay ta học XML.</p>
```

Một POJO có thể mô tả phần text và child element riêng:

```java
public class Paragraph {
    @JacksonXmlText
    private String text;

    @JacksonXmlProperty(localName = "strong")
    private String strong;
}
```

Mô hình này không có cấu trúc biểu diễn ba đoạn theo đúng thứ tự:

```text
Text("Xin chào ")
Element("strong", Text("Jackson"))
Text(", hôm nay ta học XML.")
```

Một field text đơn không chứa được hai vị trí riêng biệt quanh `strong`. Một field `strong` riêng cũng không ghi lại vị trí của nó trong chuỗi nội dung. Vì vậy, không nên dựa vào một POJO như trên để bảo toàn mixed content khi đọc rồi ghi lại XML.

Nếu chỉ cần lấy một giá trị text đã được chuẩn hóa và không cần giữ vị trí markup, POJO có thể vẫn đáp ứng một phần yêu cầu. Nhưng nếu XML là nội dung biên tập, tài liệu, XHTML, SVG hoặc một định dạng mà markup nằm xen trong văn bản, thứ tự node thường là dữ liệu quan trọng.

## 6. @JacksonXmlText vẫn hữu ích trong những trường hợp nào?

Annotation này phù hợp khi:

- Element có một giá trị text đơn giản.
- Element có attribute mô tả giá trị text.
- XML schema mô tả simple content, ví dụ mã, số đo, giá tiền hoặc tên có thuộc tính đơn vị.
- Ứng dụng chỉ cần nội dung text tổng hợp và không cần giữ vị trí của child element.

Ví dụ:

```xml
<temperature unit="C">27.5</temperature>
```

```java
@JacksonXmlRootElement(localName = "temperature")
public class Temperature {
    @JacksonXmlProperty(isAttribute = true, localName = "unit")
    private String unit;

    @JacksonXmlText
    private BigDecimal value;
}
```

Đây là một text value duy nhất cùng một attribute. Không có child element chen giữa các đoạn text.

## 7. Text, whitespace và ý nghĩa nội dung

Trong XML, whitespace có thể mang ý nghĩa. Ví dụ:

```xml
<p>Hello <em>world</em> again.</p>
```

Khoảng trắng sau `Hello` và trước `again.` là một phần của văn bản. Nếu loại bỏ hoặc trim từng đoạn một cách tùy tiện, nội dung có thể biến thành `Helloworldagain.`.

Ngược lại, trong XML element-only được thụt lề:

```xml
<person>
  <name>An</name>
  <age>28</age>
</person>
```

Các đoạn whitespace giữa child element thường chỉ phục vụ định dạng. Ứng dụng có thể bỏ qua chúng nếu schema xác định element-only content và không có ý nghĩa văn bản.

Không nên áp dụng một quy tắc trim chung cho mọi XML. Hãy dựa vào content model:

- Với simple text content, xác định whitespace có được chuẩn hóa theo hợp đồng hay không.
- Với mixed content, giữ nguyên các đoạn whitespace nằm giữa text và element.
- Với element-only content, whitespace định dạng có thể được bỏ qua nếu ứng dụng không cần bảo toàn lexical form.

## 8. CDATA là text, không phải một kiểu dữ liệu Java riêng

CDATA section cho phép viết ký tự mà không cần escape markup theo cách thông thường:

```xml
<description><![CDATA[A < B && B > C]]></description>
```

Về nội dung XML, CDATA vẫn biểu diễn character data. Sau khi parse, ứng dụng thường quan tâm đến chuỗi ký tự `A < B && B > C`, không nhất thiết quan tâm nó được viết bằng CDATA hay bằng entity escaping:

```xml
<description>A &lt; B &amp;&amp; B &gt; C</description>
```

Hai cách viết có thể biểu diễn nội dung text tương đương. Jackson XML ánh xạ nội dung text vào kiểu Java như `String`; việc đọc thành `String` không bảo toàn ranh giới CDATA hoặc cách escape ban đầu.

Nếu yêu cầu chỉ là giữ giá trị text, điều này thường không phải vấn đề. Nếu cần giữ chính xác CDATA marker, entity spelling hoặc cách viết lexical ban đầu, POJO databinding không đủ; cần giữ raw XML hoặc dùng parser/serializer có chính sách bảo toàn lexical details phù hợp.

## 9. Dùng StAX khi cần giữ thứ tự node

StAX (Streaming API for XML) cung cấp event/stream reader để xử lý XML theo thứ tự xuất hiện. Với `XMLStreamReader`, ứng dụng có thể phân biệt:

- `START_ELEMENT` và `END_ELEMENT`.
- `CHARACTERS` và `SPACE`.
- `CDATA` nếu parser/provider phát event riêng.
- Comment và processing instruction nếu cần xử lý.

Đây là cách phù hợp để đọc mixed content vì mỗi đoạn text và element được xử lý theo thứ tự. Không cần tạo toàn bộ DOM nếu chỉ muốn duyệt tuần tự.

Ví dụ XML:

```xml
<p>Xin chào <strong>Jackson</strong>, hôm nay ta học XML.</p>
```

Một mô hình Java có thể giữ các phần theo thứ tự:

```java
sealed interface ContentPart permits TextPart, StrongPart {
}

record TextPart(String text) implements ContentPart {
}

record StrongPart(String text) implements ContentPart {
}

record Paragraph(List<ContentPart> content) {
}
```

Khi đọc, danh sách có thể là:

```java
List<ContentPart> content = List.of(
        new TextPart("Xin chào "),
        new StrongPart("Jackson"),
        new TextPart(", hôm nay ta học XML.")
);
```

Khác với POJO có hai field `text` và `strong`, `List<ContentPart>` giữ đúng thứ tự xen kẽ. Ví dụ dùng sealed interface/record yêu cầu Java 17; có thể thay bằng interface và class thông thường trên phiên bản Java cũ hơn.

## 10. Đọc mixed content bằng XMLStreamReader

Đoạn code sau minh họa một paragraph chỉ có text và element `strong` chứa text đơn giản:

```java
import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLStreamConstants;
import javax.xml.stream.XMLStreamReader;
import java.io.StringReader;
import java.util.ArrayList;
import java.util.List;

String xml = "<p>Xin chào <strong>Jackson</strong>, hôm nay ta học XML.</p>";

XMLInputFactory inputFactory = XMLInputFactory.newFactory();
XMLStreamReader reader = inputFactory.createXMLStreamReader(
        new StringReader(xml)
);

List<ContentPart> parts = new ArrayList<>();

while (reader.hasNext() && reader.getEventType() != XMLStreamConstants.START_ELEMENT) {
    reader.next();
}

if (!"p".equals(reader.getLocalName())) {
    throw new IllegalArgumentException("Root element phải là p");
}

while (reader.hasNext()) {
    int event = reader.next();

    if (event == XMLStreamConstants.CHARACTERS
            || event == XMLStreamConstants.CDATA
            || event == XMLStreamConstants.SPACE) {
        parts.add(new TextPart(reader.getText()));
    } else if (event == XMLStreamConstants.START_ELEMENT) {
        if (!"strong".equals(reader.getLocalName())) {
            throw new IllegalArgumentException("Element con không được hỗ trợ");
        }

        // getElementText() đọc text của strong và đặt reader ở END_ELEMENT.
        String strongText = reader.getElementText();
        parts.add(new StrongPart(strongText));
    } else if (event == XMLStreamConstants.END_ELEMENT
            && "p".equals(reader.getLocalName())) {
        break;
    }
}

reader.close();
```

Ví dụ giả định `strong` chỉ chứa text, không có element con. `getElementText()` không phù hợp với một element chứa markup lồng nhau; nếu `strong` có con, cần duyệt đệ quy hoặc dùng stack để giữ cấu trúc node.

Trong code production, nên đóng reader bằng `try/finally` hoặc quản lý `XMLStreamReader` theo vòng đời của nguồn. XMLStreamReader không phải mọi implementation đều triển khai `AutoCloseable` theo cùng cách sử dụng của try-with-resources; có thể gọi `close()` rõ ràng trong `finally`.

### 10.1. Không tự ý loại bỏ text whitespace

Đoạn code trên thêm mọi event text vào danh sách, kể cả đoạn chỉ có whitespace. Đây là chủ ý để không phá nội dung mixed content. Nếu schema xác định whitespace-only event chỉ là định dạng, ứng dụng có thể bỏ qua sau khi kiểm tra content model; không nên gọi `trim()` trên mọi đoạn text.

### 10.2. Event text có thể bị chia nhỏ

Parser có thể phát một đoạn văn bản thành nhiều event `CHARACTERS`. Điều này không nhất thiết có nghĩa nội dung XML có thêm node logic mới. Nếu ứng dụng chỉ cần chuỗi text liên tục, có thể gộp các event text liền kề; nhưng phải giữ ranh giới khi giữa chúng có element, comment hoặc event mà ứng dụng cần bảo toàn.

## 11. Viết lại mixed content bằng XMLStreamWriter

Khi đã có danh sách segment theo thứ tự, `XMLStreamWriter` có thể ghi lại nội dung:

```java
import javax.xml.stream.XMLOutputFactory;
import javax.xml.stream.XMLStreamWriter;
import java.io.StringWriter;

StringWriter output = new StringWriter();
XMLStreamWriter writer = XMLOutputFactory.newFactory()
        .createXMLStreamWriter(output);

writer.writeStartElement("p");

for (ContentPart part : parts) {
    if (part instanceof TextPart text) {
        writer.writeCharacters(text.text());
    } else if (part instanceof StrongPart strong) {
        writer.writeStartElement("strong");
        writer.writeCharacters(strong.text());
        writer.writeEndElement();
    }
}

writer.writeEndElement();
writer.flush();
writer.close();

String result = output.toString();
```

`writeCharacters()` tự escape ký tự cần thiết trong text content. Ví dụ ký tự `<` được ghi theo cách an toàn trong XML. Không nên tự nối chuỗi markup từ input vì dễ tạo XML sai hoặc tạo injection.

Ví dụ này bảo toàn thứ tự segment ở mức nội dung XML, nhưng không bảo toàn chính xác cách viết lexical ban đầu như khoảng trắng giữa attribute, dấu nháy đơn/kép, entity reference gốc hoặc CDATA delimiter. XML parser/writer thường chuẩn hóa cách biểu diễn trong khi vẫn giữ ý nghĩa dữ liệu.

## 12. Dùng DOM khi cần truy cập node theo cây và giữ thứ tự con

DOM biểu diễn XML thành cây node. Một element có danh sách child node theo thứ tự, trong đó có thể xen kẽ text node, element node, comment và CDATA node.

Ví dụ duyệt child node của `<p>`:

```java
NodeList children = paragraphElement.getChildNodes();

for (int i = 0; i < children.getLength(); i++) {
    Node child = children.item(i);

    switch (child.getNodeType()) {
        case Node.TEXT_NODE -> {
            String text = child.getNodeValue();
            // Thêm TextPart(text).
        }
        case Node.CDATA_SECTION_NODE -> {
            String text = child.getNodeValue();
            // Có thể giữ loại CDATA riêng nếu ứng dụng cần.
        }
        case Node.ELEMENT_NODE -> {
            Element element = (Element) child;
            // Xử lý element con tại đúng vị trí trong danh sách.
        }
        case Node.COMMENT_NODE -> {
            // Giữ hoặc bỏ comment theo yêu cầu.
        }
        default -> {
            // Xử lý loại node khác nếu cần.
        }
    }
}
```

DOM thuận tiện khi cần duyệt nhiều lần, chỉnh sửa node hoặc truy cập theo XPath. Đổi lại, DOM thường giữ toàn bộ document trong bộ nhớ nên không phù hợp với XML rất lớn nếu ứng dụng chỉ cần xử lý tuần tự.

Nếu cần bảo toàn thứ tự mixed content nhưng document vừa phải, DOM là lựa chọn trực quan. Nếu document lớn và xử lý tuần tự, StAX thường tiết kiệm bộ nhớ hơn.

## 13. StAX và DOM không đồng nghĩa với bảo toàn từng byte XML

Có hai yêu cầu khác nhau:

- **Bảo toàn cấu trúc/nội dung theo XML:** giữ thứ tự text và element, giá trị attribute, namespace và các node cần thiết.
- **Bảo toàn lexical form:** giữ đúng từng ký tự trong tài liệu gốc, bao gồm prefix namespace, cách dùng quote, entity spelling, CDATA marker, khoảng trắng và định dạng dòng.

StAX và DOM giúp bảo toàn cấu trúc/nội dung ở mức mô hình XML, nhưng không đảm bảo output giống hệt từng byte input. Parser có thể chuẩn hóa line ending, giải entity reference thành ký tự, gộp hoặc chia text event, và writer có thể chọn cách escape khác.

Nếu cần lưu nguyên văn XML gốc để ký số, so sánh byte, lưu trữ chứng cứ hoặc chuyển tiếp không thay đổi, hãy giữ raw bytes/string gốc. Nếu cần sửa một phần nhưng giữ lexical details của phần còn lại, cần một công cụ có khả năng round-trip lexical preservation phù hợp; POJO databinding thông thường không đáp ứng yêu cầu đó.

## 14. Namespace và thứ tự mixed content

XML namespace xác định tên mở rộng bằng namespace URI và local name. Prefix chỉ là bí danh trong tài liệu:

```xml
<x:p xmlns:x="urn:example">Hello <x:em>world</x:em>.</x:p>
```

Khi đọc bằng StAX, nên kiểm tra namespace URI và local name thay vì chỉ so sánh prefix:

```java
String localName = reader.getLocalName();
String namespaceUri = reader.getNamespaceURI();
```

Hai tài liệu có thể dùng prefix khác nhau nhưng cùng namespace URI và local name. Nếu lưu event model, hãy giữ QName/namespace URI, prefix nếu cần tái tạo cách viết, và thứ tự node.

Với Jackson XML, có thể dùng `@JacksonXmlProperty(namespace = "...")` hoặc cấu hình namespace theo khả năng của module. Tuy nhiên, annotation namespace không giải quyết giới hạn của việc biểu diễn mixed content thành các property POJO riêng biệt.

## 15. Attribute không phải là text node

Attribute nằm trong start tag và được ánh xạ riêng với `@JacksonXmlProperty(isAttribute = true)`:

```xml
<measurement unit="kg">12.5</measurement>
```

```java
public class Measurement {
    @JacksonXmlProperty(isAttribute = true)
    private String unit;

    @JacksonXmlText
    private BigDecimal value;
}
```

Không nên gộp attribute vào chuỗi text hoặc coi attribute là một segment xen kẽ trong mixed content. XML quy định attribute thuộc element, còn thứ tự attribute không mang ý nghĩa như thứ tự child node.

Nếu dùng StAX, đọc attribute tại `START_ELEMENT` qua `getAttributeCount()`, `getAttributeLocalName(i)`, `getAttributeNamespace(i)` và `getAttributeValue(i)`. Sau đó tiếp tục xử lý các text/element event theo thứ tự.

## 16. Mapping collection element không giải quyết mixed content

Jackson XML hỗ trợ collection và wrapper element:

```xml
<paragraph>
  <segments>
    <segment>First</segment>
    <segment>Second</segment>
  </segments>
</paragraph>
```

Có thể ánh xạ collection bằng `@JacksonXmlElementWrapper` và `@JacksonXmlProperty`:

```java
public class Paragraph {
    @JacksonXmlElementWrapper(localName = "segments")
    @JacksonXmlProperty(localName = "segment")
    private List<String> segments;
}
```

Đây là danh sách element có thứ tự, không phải mixed content. Nếu schema được thiết kế lại để mọi phần văn bản đều nằm trong element `segment`, thứ tự có thể được biểu diễn bằng collection. Nhưng nếu phải đọc XML hiện có với text trực tiếp xen giữa element markup, không thể giả định Jackson sẽ tự biến chúng thành danh sách segment đồng nhất.

Nếu kiểm soát được XML schema, một thiết kế element-only như `<segment type="text">...</segment>` và `<segment type="emphasis">...</segment>` có thể giúp databinding đơn giản hơn. Nếu không kiểm soát schema, dùng StAX/DOM để giữ cấu trúc gốc.

## 17. Khi nào nên dùng custom deserializer?

Custom deserializer có thể giúp khi cần biến một phần XML thành mô hình Java riêng. Tuy nhiên, khi dùng `XmlMapper`, custom deserializer vẫn làm việc thông qua token abstraction của Jackson XML. Nếu abstraction đó không biểu diễn đầy đủ ranh giới và thứ tự mixed content cần giữ, custom deserializer không thể tự khôi phục thông tin đã bị mất ở tầng parser/databinding.

Hãy cân nhắc:

- Nếu chỉ cần đọc simple text, dùng `@JacksonXmlText`.
- Nếu cần ánh xạ element/attribute thông thường, dùng POJO và annotation Jackson XML.
- Nếu cần danh sách node mixed content theo thứ tự, dùng StAX hoặc DOM.
- Nếu cần một domain model thống nhất, có thể đọc bằng StAX rồi chuyển event/node sang DTO/segment model.
- Nếu bắt buộc tích hợp vào pipeline Jackson, hãy thử nghiệm token stream thực tế của phiên bản `jackson-dataformat-xml` đang dùng trước khi thiết kế custom deserializer.

Không nên viết custom deserializer dựa trên giả định rằng mọi text node xen kẽ sẽ luôn xuất hiện như các token riêng biệt theo cách mong muốn. Kiểm tra input thực tế và phiên bản module là bắt buộc.

## 18. Chọn mô hình Java cho mixed content

Một mô hình tổng quát có thể dùng danh sách các node nội dung:

```java
sealed interface XmlContent permits XmlText, XmlElement {
}

record XmlText(String value) implements XmlContent {
}

record XmlElement(
        String namespaceUri,
        String localName,
        Map<QName, String> attributes,
        List<XmlContent> children
) implements XmlContent {
}
```

Element cha giữ:

```java
record XmlParagraph(List<XmlContent> content) {
}
```

Với XML:

```xml
<p>Hello <em>world</em> and <code>Jackson</code>.</p>
```

Danh sách content có thể chứa:

```text
XmlText("Hello ")
XmlElement(localName="em", children=[XmlText("world")])
XmlText(" and ")
XmlElement(localName="code", children=[XmlText("Jackson")])
XmlText(".")
```

Mô hình này có thể biểu diễn nested mixed content vì mỗi element cũng có danh sách child content. Nếu cần bảo toàn comment, processing instruction hoặc CDATA distinction, hãy thêm loại node tương ứng thay vì gộp tất cả thành `XmlText`.

Đây là mô hình ứng dụng, không phải kiểu POJO mà Jackson XML tự động ánh xạ đầy đủ mọi mixed content. Có thể dùng StAX/DOM để xây dựng và ghi lại mô hình này.

## 19. Những thông tin có thể bị mất khi round-trip qua POJO

Khi đọc XML thành POJO rồi ghi lại bằng `XmlMapper`, hãy xác định thông tin nào cần giữ:

| Thành phần | POJO databinding thông thường | Hướng xử lý nếu cần giữ |
| --- | --- | --- |
| Attribute có mapping rõ ràng | Có thể giữ bằng property | `@JacksonXmlProperty(isAttribute = true)` |
| Element con có mapping rõ ràng | Có thể giữ bằng property/collection | `@JacksonXmlProperty`, `@JacksonXmlElementWrapper` |
| Simple text content | Có thể giữ bằng `@JacksonXmlText` | Dùng một property text |
| Text xen kẽ child element | Không bảo toàn đầy đủ thứ tự bằng field tách riêng | StAX/DOM và ordered segment list |
| Whitespace có ý nghĩa trong mixed content | Có thể bị chuẩn hóa/gộp nếu mô hình không giữ segment | Giữ text event và không trim tùy tiện |
| CDATA delimiter | Thường chỉ giữ giá trị text, không giữ cách viết CDATA | Parser/event handling chuyên biệt nếu cần |
| Comment/processing instruction | Không phải property POJO thông thường | DOM/StAX và mô hình node riêng |
| Prefix namespace ban đầu | Không nhất thiết giữ nguyên | Lưu prefix nếu lexical form quan trọng |
| Quote style và entity spelling | Không bảo toàn từng byte | Giữ raw XML nếu cần lexical fidelity |

Không phải mọi ứng dụng cần giữ tất cả thông tin. Ví dụ, một service chỉ đọc giá trị giá tiền không cần giữ comment hoặc cách viết CDATA. Nhưng một hệ thống quản lý tài liệu có thể cần giữ thứ tự markup và whitespace.

## 20. Kiểm thử mixed content

Khi dùng Jackson XML với nội dung text, hãy tạo test thể hiện rõ yêu cầu:

1. Element chỉ có text.
2. Element có attribute và text.
3. Element-only content với nhiều child.
4. Text trước child element.
5. Text giữa hai child element.
6. Text sau child element.
7. Text có whitespace ở đầu/cuối.
8. CDATA và entity-escaped text.
9. Child element lồng nhiều tầng.
10. Namespace và prefix khác nhau.

Nếu ứng dụng cần round-trip mixed content, test không chỉ so sánh giá trị text tổng hợp. Hãy so sánh thứ tự segment/node sau khi parse và sau khi serialize lại. Nếu yêu cầu là bảo toàn lexical form, so sánh byte/string gốc là một tiêu chí khác và cần công cụ phù hợp.

Ví dụ test cho mô hình segment:

```java
assertEquals(5, paragraph.content().size());
assertEquals(new XmlText("Hello "), paragraph.content().get(0));
assertTrue(paragraph.content().get(1) instanceof XmlElement);
assertEquals(new XmlText(" and "), paragraph.content().get(2));
assertEquals(new XmlText("."), paragraph.content().get(4));
```

Test này xác nhận thứ tự nội dung, điều mà một phép so sánh chuỗi text đã nối có thể bỏ sót.

## 21. Bảo mật khi đọc XML không tin cậy

Khi dùng StAX hoặc DOM cho XML bên ngoài, cấu hình parser an toàn. XML có thể chứa DTD hoặc external entity reference; nếu parser cho phép truy cập tài nguyên bên ngoài, ứng dụng có thể gặp rủi ro XXE hoặc đọc tài nguyên nội bộ.

Với StAX, có thể tắt DTD và external entity theo khả năng provider:

```java
XMLInputFactory inputFactory = XMLInputFactory.newFactory();
inputFactory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
inputFactory.setProperty(
        "javax.xml.stream.isSupportingExternalEntities",
        false
);
```

Một số provider có thể không hỗ trợ property hoặc có hành vi khác nhau; hãy kiểm tra và test cấu hình thực tế. Nếu không thể đặt thuộc tính bảo mật, fail closed hoặc chọn provider đã được cấu hình an toàn. Không bật DTD/external entity chỉ để parse một tài liệu hoạt động.

Ngoài XXE, vẫn cần giới hạn kích thước document, độ sâu, số node và thời gian parse. StAX tiết kiệm bộ nhớ hơn DOM khi streaming, nhưng không tự đặt giới hạn tài nguyên cho ứng dụng.

## 22. Chọn Jackson XML, StAX hay DOM?

| Nhu cầu | Lựa chọn phù hợp |
| --- | --- |
| XML có schema object/collection rõ ràng | `XmlMapper` và POJO |
| Element có attribute và một text value | `@JacksonXmlText` kết hợp `@JacksonXmlProperty(isAttribute = true)` |
| XML có mixed content cần giữ thứ tự text/element | StAX hoặc DOM với ordered node model |
| Document rất lớn, xử lý tuần tự | StAX |
| Document vừa phải, cần truy cập/chỉnh sửa nhiều lần theo cây | DOM |
| Chỉ cần giá trị text và không quan tâm vị trí markup | `XmlMapper`/`@JacksonXmlText` có thể đủ |
| Cần bảo toàn từng byte/lexical spelling ban đầu | Giữ raw XML hoặc dùng giải pháp lexical-preserving chuyên biệt |
| Muốn chuyển mixed content sang DTO nghiệp vụ | Đọc StAX/DOM rồi map sang domain model |

Jackson XML không phải lựa chọn sai cho mọi tài liệu có text. Giới hạn nằm ở việc biểu diễn text xen kẽ với element con bằng các property POJO tách rời. Hãy chọn công cụ dựa trên mức độ trung thực cần giữ của nội dung XML.

## 23. Ghi nhớ

- XML element có thể chứa text, child element, attribute, CDATA, comment và processing instruction.
- Simple text content như `<price currency="VND">125000</price>` phù hợp với `@JacksonXmlText`.
- Mixed content là text và child element xen kẽ theo thứ tự, ví dụ `<p>Hello <em>world</em> again.</p>`.
- Một field `String` cùng một field danh sách element không thể biểu diễn vị trí của nhiều đoạn text quanh các child element.
- Jackson XML POJO databinding phù hợp với cấu trúc object/collection và simple text; không nên dựa vào nó để round-trip đầy đủ thứ tự mixed content.
- Với mixed content, dùng StAX event stream hoặc DOM child-node list để giữ thứ tự; biểu diễn nội dung bằng danh sách segment/node có thứ tự.
- Không trim hoặc bỏ whitespace tùy tiện trong mixed content vì khoảng trắng có thể là một phần của văn bản.
- CDATA là cách viết character data; ánh xạ thành String thường giữ giá trị text chứ không giữ delimiter CDATA hoặc entity spelling.
- StAX/DOM giữ cấu trúc node ở mức XML nhưng không bảo đảm bảo toàn từng byte lexical form.
- Namespace nên được nhận diện bằng namespace URI và local name; prefix có thể thay đổi.
- Khi đọc XML không tin cậy bằng StAX/DOM, tắt DTD/external entities theo khả năng provider và giới hạn tài nguyên.

Khi XML chứa văn bản xen kẽ markup, hãy quyết định trước liệu ứng dụng chỉ cần giá trị text hay cần giữ nguyên thứ tự từng đoạn text và element. `@JacksonXmlText` đáp ứng tốt simple content; với mixed content thực sự, StAX hoặc DOM cùng một mô hình segment có thứ tự sẽ giữ được cấu trúc mà POJO databinding thông thường không thể biểu diễn đầy đủ.
