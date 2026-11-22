# StAX nâng cao: Ghi namespace, attribute và nội dung được escape

## Mục tiêu và phạm vi

Khi xuất XML từ Java, không nên nối các mảnh markup và dữ liệu người dùng bằng `String`. Ký tự `&`, `<`, `>` hoặc dấu `"` có ngữ nghĩa khác nhau trong **nội dung phần tử** và **giá trị thuộc tính**; tên phần tử có namespace lại cần cặp `prefix ↔ namespace URI` được khai báo đúng. StAX cung cấp các API chuẩn để **ghi XML theo luồng**: `XMLStreamWriter` (cursor-style writer) và `XMLEventWriter` (event writer), được tạo từ `XMLOutputFactory`.

Các API này thuộc module `java.xml`, package `javax.xml.stream` và **vẫn được hỗ trợ trong Java SE 26**. Bài học ưu tiên Java 17+ để có thể biên dịch/chạy trên nhiều bản JDK hiện hành; không sử dụng API đã legacy.

Sau bài này, bạn có thể:

1. Tạo `XMLStreamWriter` và ghi `writeStartDocument`, `writeStartElement`, `writeAttribute`, `writeCharacters`, `writeEndElement`, `writeEndDocument` theo đúng trạng thái.
2. Phân biệt **namespace URI**, **prefix**, **local name** và **QName**. Hiểu rằng một prefix như `m` không phải định danh nghiệp vụ; namespace URI là thành phần ngữ nghĩa.
3. Ghi khai báo mặc định bằng `writeDefaultNamespace` và khai báo prefix bằng `writeNamespace`; hiểu `setDefaultNamespace`/`setPrefix` cập nhật namespace context chứ không đồng nghĩa tự xuất `xmlns` khi tắt namespace repair.
4. Ghi attribute **không namespace** bằng `writeAttribute(localName, value)` và attribute **có namespace** bằng `writeAttribute(prefix, namespaceURI, localName, value)`.
5. Dùng `XMLOutputFactory.IS_REPAIRING_NAMESPACES` khi muốn writer tự khai báo hoặc sửa ánh xạ prefix; không dựa vào tên prefix được tự sinh.
6. Dùng `writeCharacters` cho text động, `writeAttribute` cho giá trị attribute động; biết cách chúng escape `&`, `<`, `>` và `"` đúng ngữ cảnh.
7. Tránh **double escaping** (`&` trở thành `&amp;amp;`), và nhận biết `writeCData` không thay `writeCharacters` khi nội dung tùy ý có thể chứa `]]>`.
8. Phân biệt **escaping** với kiểm tra **well-formed XML**, validation XML names/code points/schema và chống XXE ở phía parser.
9. Giữ encoding XML declaration phù hợp encoding thực của `OutputStream`; hiểu khác biệt `Writer` và `OutputStream`.
10. Đóng cả StAX writer và underlying stream theo đúng ownership; không suy ra `XMLStreamWriter.close()` tự đóng stream.
11. Tạo XML bằng `XMLEventFactory` và `XMLEventWriter` khi workflow thích hợp với event objects.
12. Chạy một chương trình Java 17+ độc lập có **33 assertion checks**: xuất XML tường minh, namespace repairing và event writer rồi parse ngược để kiểm tra QName, attribute, Unicode, escape, CDATA và vòng đời tài nguyên.

**Special Note:** Chỉ áp dụng tri thức còn hiệu lực. Các phương thức nêu dưới đây được mô tả trong Javadoc Java SE 26/24 của Oracle; mỗi điểm khác biệt giữa các providers được ghi rõ. Không dựa vào thứ tự attribute hay prefix tự sinh khi kiểm thử XML.

## 1. Ghi XML là tạo cấu trúc, không phải nối chuỗi

Giả sử bạn muốn tạo tài liệu:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<invoice xmlns="urn:example:orders"
         xmlns:m="urn:example:metadata"
         id="INV-42"
         m:trace="pha &quot;A&quot; &amp; &lt;B&gt; &gt; C">
  <item code="x&quot;&amp;&lt;&gt;">Xin chào &lt;Java&gt; &amp; bạn &gt; "đẹp" 🌏</item>
  <m:flag/>
  <raw><![CDATA[raw < & >]]></raw>
</invoice>
```

Đây là XML **minh họa đã thụt dòng để dễ đọc**. Chương trình ở mục 10 ghi XML gọn và có thể khác vị trí khoảng trắng hoặc cách serializer biểu diễn một empty tag. Những khác biệt đó không nhất thiết thay đổi nội dung XML.

Nếu chỉ nối:

```java
String xml = "<item code=\"" + userCode + "\">" + userText + "</item>";
```

đầu vào như `x"&<>` sẽ phá attribute, còn `<Java> & bạn` có thể phá cấu trúc và tạo markup ngoài ý muốn. Thay vì cố tự replace từng ký tự, hãy để writer xử lý **đúng context**.

```java
xml.writeStartElement("item");
xml.writeAttribute("code", userCode);
xml.writeCharacters(userText);
xml.writeEndElement();
```

Đây là **snippet bên trong method**, cần một `XMLStreamWriter xml` đang ở đúng trạng thái. Khi muốn ghi các element có namespace, cần dùng overload đúng và bảo đảm URI/prefix đã được khai báo hoặc bật repair; phần đó được giải thích tiếp.

## 2. Hai API chuẩn để xuất XML trong StAX

| API | Đối tượng / vai trò | Cách tiếp cận |
| --- | --- | --- |
| `XMLOutputFactory` | Tạo writer; cấu hình namespace repair | `newFactory()`, `createXMLStreamWriter`, `createXMLEventWriter` |
| `XMLStreamWriter` | Ghi trực tiếp từng thao tác XML | `writeStartElement`, `writeAttribute`, `writeCharacters` |
| `XMLEventWriter` | Ghi các `XMLEvent` objects | `add(XMLEvent)` |
| `XMLEventFactory` | Tạo `StartElement`, `Attribute`, `Namespace`, `Characters`, `EndElement` ... | `createStartElement`, `createAttribute`, `createNamespace` |
| `XMLInputFactory` + `XMLStreamReader` | Đọc/parse kết quả để xác minh ngữ nghĩa | `getName`, `getAttributeValue`, `getText` |

`XMLOutputFactory.newFactory()` tìm một implementation theo JAXP provider lookup. Cấu hình `IS_REPAIRING_NAMESPACES` có thể làm khác biểu diễn lexical; do đó **không so sánh nguyên chuỗi XML** khi cái bạn thực sự cần là đúng namespace URI/attribute value.

### Nhập xuất không có cùng mục đích

- **Output factory** quyết định cách viết XML; việc writer escape text không phải parser security policy.
- **Input factory** quyết định cách **đọc XML**; khi đọc dữ liệu ngoài ứng dụng cần tắt/hạn chế DTD/external entities và giới hạn tài nguyên.
- **XML Schema validation** (nếu cần) là bước riêng; StAX writer không tự kiểm tra document theo XSD.

## 3. Namespace URI và prefix: phân biệt rõ

XML namespace đặt một element/attribute vào **không gian tên ngữ nghĩa**. Ví dụ:

```xml
<o:invoice xmlns:o="urn:example:orders"
           xmlns:m="urn:example:metadata"
           m:trace="abc">
  <o:item code="A"/>
</o:invoice>
```

Trong XML này:

- `o:invoice` có `QName` theo ngữ nghĩa là `{urn:example:orders}invoice`.
- `o:item` là `{urn:example:orders}item`.
- `m:trace` là `{urn:example:metadata}trace`.
- `code` **không có prefix** nên **không có namespace URI**, dù element `o:item` có namespace.
- Prefix `o` và `m` chỉ là tên viết tắt có phạm vi; một serializer hợp lệ có thể đổi `o` thành `ns1` và XML vẫn tương đương theo namespace.

### Default namespace không áp dụng cho attribute không prefix

```xml
<invoice xmlns="urn:example:orders" id="42"/>
```

Ở đây `invoice` thuộc namespace `urn:example:orders`, còn `id` vẫn là unqualified attribute. Điều này quan trọng khi dùng `writeAttribute("id","42")`. **Đừng tự gắn URI của element vào mọi attribute**.

### Prefix phải được bind đúng

Ví dụ `m:trace` phải được liên kết tới namespace URI bằng một khai báo có hiệu lực trong scope, như `xmlns:m="urn:example:metadata"`. Nếu chỉ xuất lexical prefix `m:` mà không có binding, tài liệu không namespace-well-formed. Đừng nghĩ tên prefix tự nói lên namespace URI.

### Khi nào cần namespace rỗng?

Một element không namespace trong một default namespace scope có thể cần `xmlns=""` để xóa default namespace cho subtree. Nếu muốn child tiếp tục thuộc namespace cha, **đừng ghi namespace rỗng vô tình**. Kết quả nên được xác minh bằng `XMLStreamReader.getName().getNamespaceURI()`.

## 4. Ghi namespace tường minh khi namespace repair bị tắt

`XMLOutputFactory.IS_REPAIRING_NAMESPACES` mặc định **false** theo Javadoc. Khi tắt, ứng dụng chịu trách nhiệm bảo đảm prefixes và namespace declarations phù hợp.

Mẫu:

```java
XMLOutputFactory factory = XMLOutputFactory.newFactory();
factory.setProperty(XMLOutputFactory.IS_REPAIRING_NAMESPACES, false);
XMLStreamWriter xml = factory.createXMLStreamWriter(out, "UTF-8");
try {
    xml.setDefaultNamespace("urn:example:orders");
    xml.setPrefix("m", "urn:example:metadata");
    xml.writeStartDocument("UTF-8", "1.0");
    xml.writeStartElement("", "invoice", "urn:example:orders");
    xml.writeDefaultNamespace("urn:example:orders");
    xml.writeNamespace("m", "urn:example:metadata");
    xml.writeAttribute("id", "INV-42");
    xml.writeAttribute("m", "urn:example:metadata", "trace", trace);
    xml.writeStartElement("", "item", "urn:example:orders");
    xml.writeAttribute("code", code);
    xml.writeCharacters(text);
    xml.writeEndElement();
    xml.writeEndElement();
    xml.writeEndDocument();
} finally {
    xml.close();
}
```

Đây là **snippet tích hợp**, cần `OutputStream out`, biến `trace`, `code`, `text` và imports. Nó tương ứng với chương trình hoàn chỉnh ở mục 10.

### 4.1. `writeStartElement(prefix, localName, namespaceURI)`

Thứ tự tham số của overload ba chuỗi là:

```java
xml.writeStartElement("m", "flag", "urn:example:metadata");
```

**Không nhầm thứ tự `prefix, namespaceURI, localName`**. Nếu đảo tham số, writer có thể viết sai tag hoặc báo lỗi.

### 4.2. `setPrefix` khác `writeNamespace`

- `setPrefix("m", META)`: khai báo mapping trong **namespace context của writer**, hỗ trợ cách writer tra prefix/URI.
- `writeNamespace("m", META)`: **ghi** declaration `xmlns:m="..."` lên XML output.
- Với namespace repair **tắt**, không nên chỉ `setPrefix` rồi suy ra XML đã có declaration thực tế.
- Nếu application cần prefix ổn định vì giao thức bên ngoài, quản lý namespace declarations **tường minh** và test lexical constraints bằng integration tests.

### 4.3. `setDefaultNamespace` khác `writeDefaultNamespace`

- `setDefaultNamespace(ORDER)`: bind default namespace trong writer context.
- `writeDefaultNamespace(ORDER)`: xuất `xmlns="urn:example:orders"`.
- Khi dùng nonrepairing mode, snippet làm **cả hai** trước hoặc trên start tag thích hợp, để namespace context và XML declaration nhất quán.

### 4.4. Thứ tự ghi attribute và namespace

`writeAttribute` và `writeNamespace` chỉ được gọi khi writer đang ở **start element tag chưa khép** và trạng thái cho phép. Đừng gọi sau `writeCharacters` hoặc sau khi `writeEndElement` đã khép element đó. Javadoc nêu `IllegalStateException` nếu trạng thái không còn cho phép ghi.

Một thứ tự dễ hiểu:

```text
writeStartElement("...", ...)
    writeDefaultNamespace(...)
    writeNamespace("m", ...)
    writeAttribute("id", ...)
    writeAttribute("m", ..., "trace", ...)
    writeCharacters(...)
    writeEndElement()
```

Thứ tự các **attributes** trong output không phải phần của XML information set; không nên assert một chuỗi thô có cùng thứ tự attribute giữa mọi serializers.

## 5. Attribute có namespace và attribute không namespace

### 5.1. Attribute không namespace

```java
xml.writeAttribute("id", "INV-42");
```

Overload này viết unprefixed attribute. Đừng gắn default namespace URI cho attribute này; namespace mặc định chỉ áp cho **unprefixed element names**, không áp cho unprefixed attribute names.

### 5.2. Attribute có namespace

```java
xml.writeAttribute("m", "urn:example:metadata", "trace",
                   "pha \"A\" & <B> > C");
```

Writer tạo attribute có prefix `m` trỏ tới URI `urn:example:metadata`, **nếu prefix được bind đúng hoặc mode repair xử lý mapping**. Đây là snippet bên trong element start tag.

Trong XML lexical, attribute value cần escape dấu `"` nếu dùng double quotes; method `writeAttribute` cũng escape `&`, `<` và `>`. Nội dung gốc vẫn được parser đọc lại là `pha "A" & <B> > C`.

### 5.3. Dùng overload namespace URI trong repairing mode

```java
xml.writeAttribute("urn:repair:attribute", "kind", "A & \"B\"");
```

Khi `IS_REPAIRING_NAMESPACES=true`, writer có thể tự chọn một prefix chưa dùng và sinh `xmlns:...` tương ứng. **Không assert tên prefix tự sinh**, vì mỗi provider có thể chọn cách đặt tên khác nhau.

Khi repair **false** và URI chưa được bind tới prefix hợp lệ, overload này có thể ném `XMLStreamException` theo Javadoc. Vì vậy portable code cần kiểm tra/bind namespace hoặc bật repair có chủ đích.

### 5.4. Các giá trị attribute nguy hiểm

Ví dụ ứng dụng nhận `userInput = "x\"&<>"`. Khi gọi `writeAttribute("code", userInput)`, writer phải escape theo context, giúp tránh chuỗi làm vỡ attribute. Tuy nhiên writer không xác minh rằng tên attribute `code` hay giá trị business logic có hợp lệ với schema ứng dụng. **Escape giải quyết syntax context, không phải authorization/schema validation**.

## 6. `writeCharacters` và quy tắc escape nội dung

Trong văn bản của một element, StAX `writeCharacters` xử lý:

| Ký tự trong Java `String` | Biểu diễn lexical XML thường gặp | Ghi chú |
| --- | --- | --- |
| `&` | `&amp;` | Nếu không escape sẽ bắt đầu entity reference |
| `<` | `&lt;` | Nếu không escape sẽ bắt đầu markup |
| `>` | `&gt;` | Javadoc yêu cầu escape; dùng test theo semantics khi portability |
| `"` | Có thể giữ nguyên trong element text | Dấu nháy đôi không bắt buộc escape trong text |
| `'` | Có thể giữ nguyên trong element text | Dấu nháy đơn không bắt buộc escape trong text |
| `🌏`/chữ Việt | UTF-8 bytes hoặc character references tùy output encoding | Không được làm sai Unicode |
| newline/tab | Có thể xuất theo XML rules | Khác giữa text và attribute normalization |

Javadoc chính thức `XMLStreamWriter` yêu cầu `writeCharacters` escape `&`, `<` và `>`, còn `writeAttribute` escape các ký tự đó **và** dấu `"`. Không tự viết các replacements `String.replace(...)` trước khi gọi writer.

### Ví dụ chính xác

```java
String value = "Xin chào <Java> & bạn > \"đẹp\" 🌏";
xml.writeCharacters(value);
```

Trong lần kiểm thử JDK 24, chuỗi XML thô chứa `&lt;Java&gt;` và `&amp; bạn`. Khi parse ngược, `XMLStreamReader.getText()` cho đúng **chuỗi Java gốc**: `Xin chào <Java> & bạn > "đẹp" 🌏`.

### Đừng double escape

Sai:

```java
String preEscaped = userInput.replace("&", "&amp;");
xml.writeCharacters(preEscaped); // '&' của &amp; có thể bị escape tiếp.
```

Nếu source chứa `A & B`, bạn có thể tạo `A &amp;amp; B`, khiến parser sau khi đọc trả **`A &amp; B`** chứ không phải `A & B`. Đúng hơn là gọi `xml.writeCharacters(userInput)` một lần trên text gốc.

**Quy tắc:** Phân biệt *giá trị text* trong Java với *biểu diễn XML lexical*. Chỉ escape ở ranh giới serializer, không lặp lại tại business/domain layer.

## 7. `writeCData`, `writeComment` và giới hạn của escaping

CDATA phù hợp khi bạn **chủ ý** muốn giữ ký tự đặc biệt trong một vùng:

```java
xml.writeStartElement("raw");
xml.writeCData("raw < & >");
xml.writeEndElement();
```

XML được xuất dưới dạng `<![CDATA[raw < & >]]>` và giá trị text parser nhận là `raw < & >`. Nhưng **`writeCData` không tương đương `writeCharacters`**:

- CDATA không phải “escape mọi dữ liệu” để chống injection. Chuỗi có token `]]>` không được đặt nguyên vào một CDATA section; cần tách sections hoặc dùng `writeCharacters`.
- `writeComment` có giới hạn cú pháp comment XML (ví dụ không dùng `--` tùy tiện). StAX writer **không cam kết kiểm tra đầy đủ well-formedness** của mọi input.
- `writeDTD` và `writeEntityRef` dùng constructs XML nhạy cảm; không tự sinh DTD/external entities từ user input.
- Với text tùy ý của người dùng, **ưu tiên `writeCharacters`**, không tự chọn CDATA theo kiểu “khỏi cần escape”.

Trong fixture chạy đầy đủ, `writeCData("raw < & >")` chỉ được dùng với **hằng có kiểm soát** để minh họa cú pháp CDATA và parse round-trip.

## 8. Namespace repairing: tự sinh khai báo thay vì viết bằng tay

`XMLOutputFactory.IS_REPAIRING_NAMESPACES` (giá trị property `javax.xml.stream.isRepairingNamespaces`) có mặc định **false** và được Javadoc mô tả như cấu hình chuẩn.

```java
XMLOutputFactory factory = XMLOutputFactory.newFactory();
factory.setProperty(XMLOutputFactory.IS_REPAIRING_NAMESPACES, true);
StringWriter output = new StringWriter();
XMLStreamWriter xml = factory.createXMLStreamWriter(output);
try {
    xml.writeStartDocument();
    xml.writeStartElement("p", "root", "urn:repair:root");
    xml.writeAttribute("urn:repair:attribute", "kind", "A & \"B\"");
    xml.writeStartElement("urn:repair:child", "child");
    xml.writeCharacters("one < two & three");
    xml.writeEndElement();
    xml.writeEndElement();
    xml.writeEndDocument();
} finally {
    xml.close();
}
```

Đây là **snippet tích hợp Java 17+**, cần imports và biến. Mẫu được kiểm thử ở chương trình đầy đủ với text Unicode. Khi repair mode bật, writer có thể thêm prefix/namespace declarations để kết quả namespace-well-formed.

### Cơ chế repairing

- Nếu element/attribute có namespace URI nhưng chưa có prefix phù hợp, writer có thể tạo prefix/declaration.
- Nếu prefix bị dùng cho URI khác trong scope, writer có thể thay/bổ sung declaration hoặc chọn prefix thay thế.
- Nếu default namespace hợp lệ và phù hợp URI element, writer có thể dùng default namespace.
- Nếu attribute có namespace URI, thường cần **prefix**, vì default namespace không áp dụng cho unprefixed attributes.
- Khi có xung đột prefix, repair mode có thể đổi prefix nhưng **không được làm thay đổi namespace URI thực**.

### Kiểm thử đúng cách

Không viết:

```java
// Sai về tính portable:
assert xmlText.contains("xmlns:ns1=\"urn:repair:attribute\"");
```

Writer A có thể dùng `ns1`, writer B dùng `ns2`. Hãy parse XML đã sinh và kiểm tra:

```java
String attr = cursor.getAttributeValue("urn:repair:attribute", "kind");
```

Sau đó so sánh `attr` với giá trị ban đầu. Ngoài ra kiểm tra `cursor.getName().getNamespaceURI()` của elements để xác minh ngữ nghĩa.

## 9. So sánh sửa namespace tự động và tường minh

| Tiêu chí | Non-repairing (`false`) | Repairing (`true`) |
| --- | --- | --- |
| Prefix/URI mapping | App chủ động bind | Writer hỗ trợ khớp/sửa mapping |
| `xmlns` declarations | App chịu trách nhiệm viết | Writer có thể thêm tự động |
| Prefix lexical ổn định | Dễ kiểm soát hơn | Có thể tự sinh/đổi prefix |
| Nguy cơ thiếu namespace binding | Cao nếu app viết sai | Thấp hơn, nhưng vẫn cần test |
| Hỗ trợ protocol cần prefix cố định | Thích hợp khi quản lý tường minh | Cần xác minh prefix expectations |
| Namespace URI semantics | Phải đúng | Vẫn phải đúng |
| Escaping text/attribute | Writer đảm nhiệm | Writer đảm nhiệm |
| XML well-formedness đầy đủ | Không tự bảo đảm | **Cũng không** tự bảo đảm |

**Lựa chọn:** Khi XML phải tương thích với bên nhận yêu cầu **lexical prefixes cụ thể**, hãy khai báo tường minh và kiểm thử giao thức. Khi chỉ cần đúng namespace URI và muốn giảm việc quản lý prefix, repairing mode hữu ích. Cả hai vẫn phải validate đầu vào về tên, URI, giá trị XML và schema theo nghiệp vụ.

## 10. Ví dụ chạy được Java 17+: ba kiểu writer và round-trip

Tạo file **`StaxNamespaceWriterDemo.java`**. Chương trình tạo XML bằng:

1. **XMLStreamWriter non-repairing**: default namespace, prefix `m`, attribute unqualified/prefixed, Unicode + emoji, text escaping, CDATA, empty prefixed element, UTF-8 bytes.
2. **XMLStreamWriter repairing**: URI của elements và attribute khác nhau, writer tự tạo prefix/declarations.
3. **XMLEventWriter**: tạo events bằng `XMLEventFactory` và viết lần lượt với namespace/attribute.

Mỗi output được **parse ngược** bằng `XMLStreamReader` namespace-aware để kiểm tra thực sự. Parser demo được cấu hình tắt DTD/external entities, cấm external DTD protocols và dùng deny-all XMLResolver. Fixtures không cần driver, DB, Internet hay dependency ngoài JDK.

### 10.1. Mã nguồn hoàn chỉnh

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.StringReader;
import java.io.StringWriter;
import java.nio.charset.StandardCharsets;
import java.util.List;
import javax.xml.XMLConstants;
import javax.xml.stream.XMLEventWriter;
import javax.xml.stream.XMLEventFactory;
import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLOutputFactory;
import javax.xml.stream.XMLStreamConstants;
import javax.xml.stream.XMLStreamReader;
import javax.xml.stream.XMLStreamWriter;
import javax.xml.stream.XMLStreamException;
import javax.xml.namespace.QName;

public final class StaxNamespaceWriterDemo {
    private static final String ORDER = "urn:example:orders";
    private static final String META = "urn:example:metadata";
    private static final String TEXT = "Xin chào <Java> & bạn > \"đẹp\" 🌏";
    private static final String TRACE = "pha \"A\" & <B> > C";
    private static final String CODE = "x\"&<>";

    private static final class TrackedBytes extends ByteArrayOutputStream {
        boolean closed;
        @Override public void close() throws IOException {
            closed = true;
            super.close();
        }
    }

    private static XMLInputFactory inputFactory() {
        XMLInputFactory in = XMLInputFactory.newFactory();
        in.setProperty(XMLInputFactory.IS_NAMESPACE_AWARE, true);
        in.setProperty(XMLInputFactory.SUPPORT_DTD, false);
        in.setProperty(XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
        in.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        in.setXMLResolver((publicId, systemId, baseUri, namespace) -> {
            throw new XMLStreamException("External resolution forbidden");
        });
        return in;
    }

    private static String writeExplicit(TrackedBytes out) throws Exception {
        XMLOutputFactory factory = XMLOutputFactory.newFactory();
        factory.setProperty(XMLOutputFactory.IS_REPAIRING_NAMESPACES, false);
        XMLStreamWriter xml = factory.createXMLStreamWriter(out, "UTF-8");
        try {
            xml.setDefaultNamespace(ORDER);
            xml.setPrefix("m", META);
            xml.writeStartDocument("UTF-8", "1.0");
            xml.writeStartElement("", "invoice", ORDER);
            xml.writeDefaultNamespace(ORDER);
            xml.writeNamespace("m", META);
            xml.writeAttribute("id", "INV-42");
            xml.writeAttribute("m", META, "trace", TRACE);
            xml.writeStartElement("", "item", ORDER);
            xml.writeAttribute("code", CODE);
            xml.writeCharacters(TEXT);
            xml.writeEndElement();
            xml.writeEmptyElement("m", "flag", META);
            xml.writeStartElement("", "raw", ORDER);
            xml.writeCData("raw < & >");
            xml.writeEndElement();
            xml.writeEndElement();
            xml.writeEndDocument();
            xml.flush();
        } finally {
            xml.close();
        }
        return out.toString(StandardCharsets.UTF_8);
    }

    private static String writeRepairing() throws Exception {
        XMLOutputFactory factory = XMLOutputFactory.newFactory();
        factory.setProperty(XMLOutputFactory.IS_REPAIRING_NAMESPACES, true);
        StringWriter result = new StringWriter();
        XMLStreamWriter xml = factory.createXMLStreamWriter(result);
        try {
            xml.writeStartDocument();
            xml.writeStartElement("p", "root", "urn:repair:root");
            xml.writeAttribute("urn:repair:attribute", "kind", TRACE);
            xml.writeStartElement("urn:repair:child", "child");
            xml.writeCharacters(TEXT);
            xml.writeEndElement();
            xml.writeEndElement();
            xml.writeEndDocument();
        } finally {
            xml.close();
        }
        return result.toString();
    }

    private static String writeEvent() throws Exception {
        XMLOutputFactory factory = XMLOutputFactory.newFactory();
        XMLEventFactory events = XMLEventFactory.newFactory();
        StringWriter out = new StringWriter();
        XMLEventWriter writer = factory.createXMLEventWriter(out);
        try {
            writer.add(events.createStartDocument("UTF-8", "1.0"));
            writer.add(events.createStartElement("e", "urn:event", "message",
                    List.of(events.createAttribute("code", CODE)).iterator(),
                    List.of(events.createNamespace("e", "urn:event")).iterator()));
            writer.add(events.createCharacters(TEXT));
            writer.add(events.createEndElement("e", "urn:event", "message"));
            writer.add(events.createEndDocument());
            writer.flush();
        } finally {
            writer.close();
        }
        return out.toString();
    }

    private static final class Facts {
        boolean startDocument;
        boolean endDocument;
        boolean rootNs;
        boolean traceNs;
        boolean rootId;
        boolean childNs;
        boolean code;
        boolean flagNs;
        boolean rawNs;
        boolean kindNs;
        boolean eventNs;
        int starts;
        int ends;
        String itemText = "";
        String rawText = "";
        String childText = "";
        String eventText = "";
        String topLocal = "";
    }

    private static Facts parse(String xml) throws Exception {
        Facts facts = new Facts();
        XMLStreamReader reader = inputFactory().createXMLStreamReader(new StringReader(xml));
        try {
            while (true) {
                switch (reader.getEventType()) {
                    case XMLStreamConstants.START_DOCUMENT -> facts.startDocument = true;
                    case XMLStreamConstants.START_ELEMENT -> {
                        facts.starts++;
                        QName name = reader.getName();
                        facts.topLocal = name.getLocalPart();
                        String uri = name.getNamespaceURI();
                        if (name.getLocalPart().equals("invoice")) {
                            facts.rootNs = ORDER.equals(uri);
                            facts.rootId = "INV-42".equals(reader.getAttributeValue(null, "id"));
                            facts.traceNs = TRACE.equals(reader.getAttributeValue(META, "trace"));
                        }
                        if (name.getLocalPart().equals("item")) {
                            facts.childNs = ORDER.equals(uri);
                            facts.code = CODE.equals(reader.getAttributeValue(null, "code"));
                        }
                        if (name.getLocalPart().equals("flag")) {
                            facts.flagNs = META.equals(uri);
                        }
                        if (name.getLocalPart().equals("raw")) {
                            facts.rawNs = ORDER.equals(uri);
                        }
                        if (name.getLocalPart().equals("root")) {
                            facts.rootNs = "urn:repair:root".equals(uri);
                            facts.kindNs = TRACE.equals(reader.getAttributeValue(
                                    "urn:repair:attribute", "kind"));
                        }
                        if (name.getLocalPart().equals("child")) {
                            facts.childNs = "urn:repair:child".equals(uri);
                        }
                        if (name.getLocalPart().equals("message")) {
                            facts.eventNs = "urn:event".equals(uri);
                            facts.code = CODE.equals(reader.getAttributeValue(null, "code"));
                        }
                    }
                    case XMLStreamConstants.CHARACTERS,
                         XMLStreamConstants.CDATA,
                         XMLStreamConstants.SPACE -> {
                        // The fixture has no nested text-bearing descendants.
                        switch (facts.topLocal) {
                            case "item" -> facts.itemText += reader.getText();
                            case "raw" -> facts.rawText += reader.getText();
                            case "child" -> facts.childText += reader.getText();
                            case "message" -> facts.eventText += reader.getText();
                            default -> { }
                        }
                    }
                    case XMLStreamConstants.END_ELEMENT -> {
                        facts.ends++;
                        facts.topLocal = "";
                    }
                    case XMLStreamConstants.END_DOCUMENT -> facts.endDocument = true;
                    default -> { }
                }
                if (!reader.hasNext()) break;
                reader.next();
            }
        } finally {
            reader.close();
        }
        return facts;
    }

    private static void check(String name, boolean ok) {
        if (!ok) throw new AssertionError(name);
        System.out.println(name + "=true");
    }

    public static void main(String[] args) throws Exception {
        TrackedBytes bytes = new TrackedBytes();
        String explicit = writeExplicit(bytes);
        Facts a = parse(explicit);
        check("streamNotClosedByWriter", !bytes.closed);
        check("explicitUtf8Declaration", explicit.contains("encoding=\"UTF-8\""));
        check("explicitNamespacesDeclared",
                explicit.contains("xmlns=\"" + ORDER + "\"")
                        && explicit.contains("xmlns:m=\"" + META + "\""));
        check("explicitAttributeEscaped", explicit.contains("&quot;")
                && explicit.contains("&amp;") && explicit.contains("&lt;"));
        check("explicitTextEscaped", explicit.contains("&lt;Java&gt;")
                && explicit.contains("&amp; bạn"));
        check("explicitNotDoubleEscaped", !explicit.contains("&amp;amp;"));
        check("explicitCdataWritten", explicit.contains("<![CDATA[raw < & >]]>"));
        check("explicitDocumentEvents", a.startDocument && a.endDocument);
        check("explicitBalancedElements", a.starts == 4 && a.ends == 4);
        check("explicitRootQName", a.rootNs);
        check("explicitRootId", a.rootId);
        check("explicitPrefixedTrace", a.traceNs);
        check("explicitChildQName", a.childNs);
        check("explicitUnprefixedAttribute", a.code);
        check("explicitEmptyPrefixedElement", a.flagNs);
        check("explicitRawQName", a.rawNs);
        check("explicitTextRoundTrip", TEXT.equals(a.itemText));
        check("explicitCdataRoundTrip", "raw < & >".equals(a.rawText));

        String repairing = writeRepairing();
        Facts b = parse(repairing);
        check("repairDocumentEvents", b.startDocument && b.endDocument);
        check("repairBalancedElements", b.starts == 2 && b.ends == 2);
        check("repairRootQName", b.rootNs);
        check("repairQualifiedAttribute", b.kindNs);
        check("repairChildQName", b.childNs);
        check("repairTextRoundTrip", TEXT.equals(b.childText));
        check("repairTextEscaped", repairing.contains("&lt;Java&gt;"));
        check("repairAttributeEscaped", repairing.contains("&quot;"));

        String eventXml = writeEvent();
        Facts c = parse(eventXml);
        check("eventDocumentEvents", c.startDocument && c.endDocument);
        check("eventBalancedElements", c.starts == 1 && c.ends == 1);
        check("eventRootNamespace", c.eventNs);
        check("eventUnprefixedAttribute", c.code);
        check("eventTextRoundTrip", TEXT.equals(c.eventText));
        check("eventTextEscaped", eventXml.contains("&lt;Java&gt;"));
        check("eventAttributeEscaped", eventXml.contains("&quot;")
                && eventXml.contains("&amp;"));
    }
}
```

### 10.2. Biên dịch và chạy

Trong thư mục có file `StaxNamespaceWriterDemo.java`:

```bash
javac --release 17 StaxNamespaceWriterDemo.java
java StaxNamespaceWriterDemo
```

Không cần Maven, driver, database hoặc external dependencies. JDK cung cấp `java.xml` và `java.base`. Nếu ứng dụng có `module-info.java`, khai báo `requires java.xml;`. Chương trình được biên dịch `--release 17` và chạy trên OpenJDK 24.

### 10.3. Stdout chính xác đã kiểm chứng (33/33)

```text
streamNotClosedByWriter=true
explicitUtf8Declaration=true
explicitNamespacesDeclared=true
explicitAttributeEscaped=true
explicitTextEscaped=true
explicitNotDoubleEscaped=true
explicitCdataWritten=true
explicitDocumentEvents=true
explicitBalancedElements=true
explicitRootQName=true
explicitRootId=true
explicitPrefixedTrace=true
explicitChildQName=true
explicitUnprefixedAttribute=true
explicitEmptyPrefixedElement=true
explicitRawQName=true
explicitTextRoundTrip=true
explicitCdataRoundTrip=true
repairDocumentEvents=true
repairBalancedElements=true
repairRootQName=true
repairQualifiedAttribute=true
repairChildQName=true
repairTextRoundTrip=true
repairTextEscaped=true
repairAttributeEscaped=true
eventDocumentEvents=true
eventBalancedElements=true
eventRootNamespace=true
eventUnprefixedAttribute=true
eventTextRoundTrip=true
eventTextEscaped=true
eventAttributeEscaped=true
```

**33/33 phép kiểm tra PASS.** Method `check` chỉ in `name=true` khi điều kiện đúng; sai ném `AssertionError`. File đã được chạy thật, không phải stdout dự đoán.

### 10.4. Chúng ta đã kiểm chứng điều gì?

| Nhóm | Ý nghĩa |
| --- | --- |
| `streamNotClosedByWriter` | `XMLStreamWriter.close` không đóng `OutputStream` gốc trong provider được kiểm thử; khớp Javadoc |
| `explicitUtf8Declaration` | XML declaration chứa encoding UTF-8 |
| `explicitNamespacesDeclared` | Có `xmlns` default và `xmlns:m` được ghi tường minh |
| `explicitAttributeEscaped` | Giá trị attribute đặc biệt được escape |
| `explicitTextEscaped` | Element text có `<Java>` và `&` được escape |
| `explicitNotDoubleEscaped` | Text gốc không bị escape lặp theo case thử |
| `explicitCdataWritten` | CDATA hằng được serialize theo cú pháp |
| `explicitDocumentEvents` | Parser xác nhận START_DOCUMENT/END_DOCUMENT |
| `explicitBalancedElements` | Bốn cặp element: invoice, item, flag, raw |
| `explicitRootQName` | Default namespace root đúng URI |
| `explicitRootId` | Attribute không prefix đọc lại đúng |
| `explicitPrefixedTrace` | Attribute có prefix `m` đọc đúng URI và value |
| `explicitChildQName` | Child item nhận default namespace đúng |
| `explicitUnprefixedAttribute` | Attribute code không có namespace vẫn đúng value |
| `explicitEmptyPrefixedElement` | Empty element `m:flag` đúng URI |
| `explicitRawQName` | Element raw thuộc default namespace |
| `explicitTextRoundTrip` | Tiếng Việt, emoji, dấu `&<>` và quotes được phục hồi chính xác |
| `explicitCdataRoundTrip` | CDATA sau parse thành text gốc |
| `repairDocumentEvents` | Repair output là XML document có ranh giới |
| `repairBalancedElements` | Repair output có hai cặp root/child |
| `repairRootQName` | Prefix root có thể thay đổi nhưng namespace URI đúng |
| `repairQualifiedAttribute` | Attribute có namespace được tạo và parse đúng |
| `repairChildQName` | Child namespace không bị gắn nhầm vào parent URI |
| `repairTextRoundTrip` | Text element ở repairing mode round-trip thành công |
| `repairTextEscaped`, `repairAttributeEscaped` | Escaping cũng đúng khi bật repairing |
| `eventDocumentEvents`, `eventBalancedElements` | XMLEventWriter xuất document và một element hợp lệ |
| `eventRootNamespace` | StartElement event mang namespace |
| `eventUnprefixedAttribute` | Attribute event giá trị đặc biệt đọc lại đúng |
| `eventTextRoundTrip` | Characters event giữ Unicode và special chars |
| `eventTextEscaped`, `eventAttributeEscaped` | XMLEventWriter escape text và attribute |

**Giới hạn:** Bộ kiểm thử dùng JDK 24 provider và các trường hợp input cụ thể. Nó không chứng minh tất cả parser/providers sẽ sinh cùng **lexical prefix**, cùng thứ tự attributes hoặc cùng thứ tự whitespace. Assertions ưu tiên semantic QName và text values.

## 11. XMLStreamWriter không đảm bảo mọi input đều well-formed

Đây là cảnh báo ngay trong Javadoc `XMLStreamWriter`: interface **không thực hiện kiểm tra toàn bộ tính well-formedness của đầu vào**. Escaping tự động chỉ giải quyết các ký tự đặc biệt trong **text** và **attribute values** khi gọi đúng method.

Các vấn đề vẫn thuộc trách nhiệm ứng dụng:

- Tên element/attribute phải là **XML Name/NCName** hợp lệ theo quy tắc namespace và XML version.
- Namespace prefix/URI phải được bind đúng; không tùy ý dùng `xml` hoặc `xmlns` làm prefix nghiệp vụ.
- XML 1.0 cấm một số control code points như NUL (`U+0000`). Không coi `writeCharacters` tự lọc tất cả ký tự bất hợp lệ.
- Java `String` có thể chứa unpaired UTF-16 surrogate; cần kiểm tra input nếu dữ liệu không đáng tin.
- Thứ tự mở/đóng elements phải hợp lệ, không phát nhiều root elements ngoài cấu trúc được cho phép.
- CDATA không được chứa `]]>` như một đoạn chưa xử lý.
- XML comments/PI/DTD/entity references có thêm hạn chế cú pháp và rủi ro bảo mật.
- XML document có thể well-formed nhưng **không thỏa schema/business rules**.

### 11.1. Khi tên element là dữ liệu động

Không nhận raw user input rồi đưa thẳng thành `writeStartElement(userInput)`. Ví dụ tên có khoảng trắng, `<` hoặc ký tự không hợp lệ có thể khiến output lỗi hoặc tạo tags ngoài dự kiến. Ánh xạ input business sang **tập tên XML được phép**, còn giá trị input đặt vào `writeCharacters`/`writeAttribute`.

### 11.2. XML schema và business validation

Ngay cả XML hợp lệ như `<order><units>-7</units></order>` cũng có thể sai nghiệp vụ. Nếu đối tác yêu cầu XSD, hãy validate theo schema bằng một XML validator được cấu hình an toàn, kèm resource limits. **StAX writer không phải XSD validator**.

### 11.3. Không coi escaping là chống XXE

XXE xảy ra khi **parse XML** cho phép external entities/DTD. Dùng `writeCharacters` là cách xuất text đúng context, nhưng khi nhận hoặc parse XML không đáng tin, **phải cấu hình parser riêng**. Demo dùng `XMLInputFactory` không resolve external entities; production cần kiểm thử provider cùng giới hạn tài nguyên.

## 12. Byte encoding, XML declaration và Unicode

### 12.1. `writeStartDocument` không tự đổi encoding thật

Theo Javadoc, `writeStartDocument("UTF-8", "1.0")` ghi **XML declaration**, chứ không tự thiết lập mã hóa của underlying output. Khi muốn ghi bytes UTF-8, tạo writer đúng cách:

```java
XMLStreamWriter xml =
        XMLOutputFactory.newFactory().createXMLStreamWriter(outputStream, "UTF-8");
xml.writeStartDocument("UTF-8", "1.0");
```

Nếu encoding declaration không khớp encoding của output writer, `XMLStreamException` có thể phát sinh. Trong thực tế, mọi bytes gửi qua HTTP/file/DB phải nhất quán với declaration và transport metadata nếu có.

### 12.2. `StringWriter` có semantics khác `OutputStream`

`StringWriter` giữ Unicode `char` trong Java, chưa tạo file bytes. Vì vậy `writeStartDocument("UTF-8","1.0")` trên một `StringWriter` không tự chứng minh dữ liệu sau này được gửi bằng UTF-8. Khi cuối cùng chuyển `String` thành bytes, chọn charset rõ ràng và không phát declaration mâu thuẫn.

### 12.3. Giữ Unicode tiếng Việt và supplementary code points

Dữ liệu như `Xin chào 🌏` chứa Unicode code point ngoài BMP. Khi dùng UTF-8 output, writer phải serialize thành bytes hợp lệ để parser có thể khôi phục các ký tự. Demo round-trip kiểm tra **so sánh `String.equals`**, không chỉ so độ dài hoặc nhìn console.

### 12.4. XML escaping và HTML escaping khác nhau

XML text có quy tắc riêng. Không dùng bộ HTML entity escaping với các named HTML entities như `&nbsp;` rồi mong XML parser chấp nhận nếu không khai báo entity. Với XML thông thường, dùng StAX methods, XML predefined entities và numeric character references hợp lệ khi thực sự cần.

## 13. Đóng writer và stream đúng quyền sở hữu

`XMLStreamWriter.close()` giải phóng tài nguyên writer nhưng Javadoc quy định **không đóng underlying OutputStream/Writer**. Với stream tự mở, bạn vẫn cần đóng nó:

```java
try (OutputStream out = Files.newOutputStream(path)) {
    XMLStreamWriter xml = XMLOutputFactory.newFactory()
            .createXMLStreamWriter(out, "UTF-8");
    try {
        xml.writeStartDocument("UTF-8", "1.0");
        xml.writeStartElement("root");
        xml.writeCharacters("Xin chào");
        xml.writeEndElement();
        xml.writeEndDocument();
        xml.flush();
    } finally {
        xml.close();
    }
}
```

Đây là **snippet tích hợp**, cần `Path path`, imports `java.nio.file.Files`/`java.io.OutputStream`. Mã không chạy độc lập nếu `path` chưa có. Không giả định `XMLStreamWriter` là `AutoCloseable` có thể đặt trực tiếp trong resource declaration của Java 17.

### Vì sao `flush` không bằng `close`?

- `flush` yêu cầu đẩy dữ liệu cached từ writer ra underlying output, nhưng writer vẫn có thể tiếp tục được dùng.
- `close` giải phóng writer resources; không tự đảm nhận ownership của underlying stream.
- `writeEndDocument` đóng cấu trúc document trong quá trình serialize; **không đồng nghĩa đã đóng OutputStream**.
- Nếu một network protocol yêu cầu gửi bytes hoàn tất và đóng stream, code bên ngoài phải quyết định thời điểm đóng đúng.

Trong demo, `TrackedBytes` ghi nhận `XMLStreamWriter.close` không gọi `OutputStream.close`. Tuy nhiên đây là một output **trong bộ nhớ**; khi dùng file/socket cần flush và close thật sự theo ownership.

### Try-with-resources và exception suppression

Với `OutputStream`, try-with-resources giữ lỗi body là primary và cleanup error thành suppressed. Với `XMLStreamWriter`, bạn thường dùng `finally` vì nó không implement AutoCloseable trong API dùng cho Java 17; nếu release cũng lỗi, cần chính sách bảo toàn lỗi chính. Có thể tạo adapter application-owned để quản lý `XMLStreamWriter.close` qua AutoCloseable, nhưng không phải một thành phần của StAX API.

## 14. Ghi bằng XMLEventWriter

`XMLEventWriter` phù hợp nếu ứng dụng đã làm việc với `XMLEvent` objects, ví dụ khi transform một luồng events hoặc tạo đầu ra theo event model. `XMLEventFactory` tạo ra các objects:

```java
XMLEventFactory f = XMLEventFactory.newFactory();
XMLEventWriter writer =
        XMLOutputFactory.newFactory().createXMLEventWriter(out);

try {
    writer.add(f.createStartDocument("UTF-8", "1.0"));
    writer.add(f.createStartElement("e", "urn:event", "message",
            List.of(f.createAttribute("code", "x\"&<>")).iterator(),
            List.of(f.createNamespace("e", "urn:event")).iterator()));
    writer.add(f.createCharacters("Xin chào <Java> & bạn"));
    writer.add(f.createEndElement("e", "urn:event", "message"));
    writer.add(f.createEndDocument());
    writer.flush();
} finally {
    writer.close();
}
```

Đây là snippet tích hợp, cần `Writer out` và imports từ `javax.xml.stream`, `java.util.List`. Chương trình mục 10 có phương thức `writeEvent()` chạy đầy đủ.

### Điểm cần nhớ với event writer

- `createStartElement` có overload nhận **attribute iterator** và **namespace iterator**.
- `createNamespace(prefix, URI)` là declaration event; đừng nhầm với `createAttribute("xmlns:...", value)`.
- `createAttribute("code", value)` tạo unqualified attribute event; attribute có namespace phải dùng overload chứa prefix/namespaceURI.
- `createCharacters(value)` tạo text event, không phải một đoạn XML markup tự do.
- `createEndElement` phải phù hợp với start QName.
- `add` ghi events; `flush`, `close` quản lý tài nguyên của event writer.
- Namespace repair rules vẫn được áp dụng theo cấu hình output factory/provider; đừng suy ra prefix lexical cố định.

## 15. Round-trip parse: kiểm tra **ngữ nghĩa** chứ không chỉ chuỗi XML

Để xác minh output:

```java
XMLStreamReader reader = inputFactory.createXMLStreamReader(new StringReader(xml));
try {
    while (true) {
        int event = reader.getEventType();
        if (event == XMLStreamConstants.START_ELEMENT) {
            QName name = reader.getName();
            String uri = name.getNamespaceURI();
            String attr = reader.getAttributeValue("urn:example:metadata", "trace");
            // Kiểm tra name/uri/attr theo schema mong đợi.
        } else if (event == XMLStreamConstants.CHARACTERS
                || event == XMLStreamConstants.CDATA) {
            String fragment = reader.getText();
            // Ghép fragments và so sánh giá trị gốc.
        }
        if (!reader.hasNext()) break;
        reader.next();
    }
} finally {
    reader.close();
}
```

Đây là snippet tích hợp. `getAttributeValue` chỉ được dùng ở `START_ELEMENT`; một XMLStreamReader có các getter với điều kiện state nhất định. XML parser có thể chia text thành nhiều chunks, đặc biệt khi CDATA/entities; đừng assert một phần tử có đúng một `CHARACTERS`.

### Không so sánh prefix lexical như identity

Cả `<a:item xmlns:a="urn:x">` và `<b:item xmlns:b="urn:x">` đều có expanded QName `{urn:x}item`. Nếu hệ thống đích không yêu cầu prefix cố định, hãy so sánh **namespace URI + local name**.

### Không so sánh nguyên XML text nếu serializer có quyền khác biểu diễn

Các serializers có thể khác về:

- Prefix do repairing mode sinh.
- Thứ tự attributes và declarations.
- Cú pháp `<empty/>` so với `<empty></empty>`.
- Cách biểu diễn một số entities và character references.
- Khoảng trắng/indentation ngoài nội dung thực.
- UTF-8 bytes so với Java String đang giữ characters.

**Test đúng thứ cần đúng:** element QNames, attribute qualified/unqualified values, text sau parse, số cặp start/end, END_DOCUMENT, và security policy.

### Parser cần harden khi input không đáng tin

Ví dụ fixture:

```java
XMLInputFactory in = XMLInputFactory.newFactory();
in.setProperty(XMLInputFactory.IS_NAMESPACE_AWARE, true);
in.setProperty(XMLInputFactory.SUPPORT_DTD, false);
in.setProperty(XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
in.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
in.setXMLResolver((publicId, systemId, baseUri, namespace) -> {
    throw new XMLStreamException("External resolution forbidden");
});
```

Các properties này được JDK 24 provider chấp nhận trong test. Nếu provider production không chấp nhận security property, cần **fail closed** hoặc chọn provider đáp ứng. Đồng thời áp dụng giới hạn kích thước input, entity expansions, depth, số elements và timeout theo threat model.

## 16. Performance và streaming thực tế

Với XML lớn, `XMLStreamWriter` cho phép ghi từng record mà không cần một DOM tree:

```java
xml.writeStartDocument("UTF-8", "1.0");
xml.writeStartElement("orders");
for (Order order : orders) {
    xml.writeStartElement("order");
    xml.writeAttribute("id", order.id());
    xml.writeStartElement("message");
    xml.writeCharacters(order.message()); // Tự escape trong element text.
    xml.writeEndElement();
    xml.writeEndElement();
}
xml.writeEndElement();
xml.writeEndDocument();
```

Đây là **pseudocode Java theo model nghiệp vụ**: cần kiểu `Order` với methods tương ứng, `orders` và `xml` đang hoạt động; không phải file biên dịch độc lập. Nếu output cần namespace, dùng overload namespace-aware và khai báo phù hợp. Không gọi `writeStartDocument` lặp trong mỗi order.

Khi ghi qua file/network, cân nhắc:

- Buffering phù hợp và `flush` theo nhu cầu.
- Giới hạn kích thước total output và số records.
- Thao tác cancellation khi client hủy request.
- Lỗi I/O và cách cleanup OutputStream.
- Nếu người nhận cần document hoàn chỉnh trước khi commit, ghi vào staging file/buffer với giới hạn rồi publish **chỉ sau `writeEndDocument`/close thành công**.
- Không ghi raw user input thành tag names nếu không được validate.

**Không đánh đồng StAX streaming với streaming pipeline hoàn toàn**: nếu ứng dụng đã giữ cả triệu records trong List trước khi bắt đầu write, heap vẫn tốn theo records đó. Muốn streaming thực sự, nguồn records cũng cần cơ chế duyệt/emit từng phần.

## 17. Troubleshooting

| Triệu chứng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| XML parse lỗi do `&` trong text | Tự nối text vào markup | Dùng `writeCharacters` |
| XML parse lỗi do `"` trong attribute | Nối attribute thủ công | Dùng `writeAttribute` |
| Text đọc lại là `&amp;` thay vì `&` | Escape quá sớm rồi writer escape lần nữa | Truyền text gốc một lần |
| XML có prefix nhưng không có `xmlns:prefix` | Chỉ `setPrefix`, không khai báo output khi repair off | Dùng `writeNamespace` tường minh |
| Attribute namespace bị rơi | Dùng unprefixed overload | Dùng overload prefix/namespaceURI |
| Prefix tự sinh khác dự đoán | Repairing mode tự đặt prefix | So sánh namespace URI, không so prefix |
| Default namespace không áp trên attribute | Đúng theo XML Namespaces | Ghi qualified attribute có prefix nếu cần |
| `XMLStreamException` khi ghi namespace URI | Prefix/URI chưa bind và repair off | Bind + declaration hoặc bật repair |
| `IllegalStateException` khi `writeAttribute` | Đã ghi text/đóng start tag | Ghi attr ngay sau `writeStartElement` |
| Output có XML declaration nhưng bytes sai charset | Encoding XML declaration không khớp output | Tạo XMLStreamWriter với encoding đúng |
| `writeCData` gây malformed XML | Dữ liệu chứa `]]>` | Dùng `writeCharacters` hoặc split CDATA an toàn |
| XML có control codes bất hợp lệ | Writer không validate mọi XML chars | Validate XML 1.0 code points |
| Writer close nhưng file handle còn | Underlying stream chưa đóng | Dùng try-with-resources cho OutputStream |
| XML bị cắt khi lỗi ghi | Stream/network lỗi giữa document | Dùng staging/atomic publish khi cần |
| Parser test báo khác raw output | Khác prefix, attr order hoặc entities | Test semantic round-trip |
| Input XML không tin cậy dẫn tới external resource access | Parser thiếu cấu hình XXE | Harden XMLInputFactory, giới hạn resources |
| Test chỉ dùng string contains `xmlns:ns1` | Prefix auto-generated không ổn định | Parse QName và attribute namespace |
| Writer xuất XML nhưng schema bị từ chối | Writer không validate XSD | Validate schema/business riêng |

## 18. Checklist triển khai

1. Chọn `XMLStreamWriter` khi muốn ghi thao tác trực tiếp; chọn `XMLEventWriter` nếu pipeline làm việc theo XMLEvents.
2. Biết XML document và phiên bản, encoding thực của output.
3. Chọn nonrepairing mode nếu cần prefix lexical cụ thể; quản lý prefixes và declarations rõ ràng.
4. Chọn repairing mode nếu chỉ cần URI semantics, không phụ thuộc tên prefix tự sinh.
5. Ghi `writeStartDocument` đúng một lần khi muốn XML declaration.
6. Dùng đúng overload `writeStartElement(prefix, localName, namespaceURI)`.
7. Bảo đảm default namespace và prefixed namespace declarations được ghi ở scope thích hợp.
8. Viết `writeAttribute` ngay trong open start tag, trước text/child elements.
9. Nhớ unprefixed attribute **không kế thừa default namespace**.
10. Với attribute có namespace, dùng prefix/namespace URI đúng hoặc repairing mode.
11. Dùng `writeCharacters` cho dữ liệu text động, không tự escape trước.
12. Không dựa vào `writeCData` với input chứa `]]>`.
13. Không coi XML writer là full well-formedness checker hoặc validator XSD.
14. Kiểm tra XML names, code points, namespace reserved prefixes nếu nhận input không tin cậy.
15. Không tự ghép raw XML/namespace/attribute data từ user input.
16. Kiểm tra encoding XML declaration khớp encoding OutputStream.
17. Đóng writer, rồi đóng underlying stream theo ownership.
18. Khi xử lý XML từ bên ngoài, cấu hình parser tránh XXE/DTD/external entities.
19. Kiểm thử round-trip bằng namespace-aware parser, không chỉ text comparison.
20. Đừng assert thứ tự attributes, whitespace tùy serializer hoặc generated prefixes.
21. Với XML lớn, stream records, giới hạn memory/depth/size.
22. Có integration test với JDK/provider mục tiêu và tài liệu nhận XML thật.

## 19. Bài tập thực hành

### Bài 1 — Attribute chứa ký tự đặc biệt

Đổi `CODE` thành `"x\"&<> ñ"` trong demo. Dùng writer như cũ và xác nhận parse ngược `getAttributeValue(null, "code")` khớp đúng `String`. Quan sát raw XML có `&quot;`, `&amp;` và `&lt;`.

### Bài 2 — Text và double escaping

Đổi `TEXT` thành `"A & B < C > D"` rồi cố tình escape `&` trước khi `writeCharacters`. Xem parser trả lại khác như thế nào, sau đó bỏ pre-escape và assert round-trip đúng.

### Bài 3 — Prefix khác nhưng QName như nhau

Trong XML nonrepairing, đổi `m` thành `info` ở `setPrefix`, `writeNamespace` và `writeAttribute`. Parse ngược, xác nhận attribute vẫn có URI `urn:example:metadata` và localName `trace`, dù raw XML đổi prefix.

### Bài 4 — Default namespace không áp cho attribute

Giữ element `item` thuộc `urn:example:orders`. Dùng `writeAttribute("id", "x")` và xác nhận `getAttributeValue(null, "id")` đúng; `getAttributeValue(ORDER, "id")` **không** chứa giá trị đó.

### Bài 5 — Auto repair prefix

Bật `IS_REPAIRING_NAMESPACES` và ghi một attribute có namespace URI chưa khai báo. In XML raw để quan sát namespace declaration tự tạo; không viết assertion cứng về tên prefix.

### Bài 6 — Thứ tự writer state

Thử gọi `xml.writeAttribute("late", "value")` sau `writeCharacters` hoặc `writeEndElement`. Dự đoán lỗi trạng thái; **không** đưa anti-pattern vào production.

### Bài 7 — CDATA delimiter

Chuẩn bị text có `]]>`. So sánh an toàn khi ghi qua `writeCharacters` với rủi ro khi đưa thẳng vào một `writeCData`. Với CDATA thật sự bắt buộc, nghiên cứu cách chia CDATA sections có kiểm soát.

### Bài 8 — UTF-8 bytes

Thay `TrackedBytes` bằng `Files.newOutputStream(path)` và tạo XMLStreamWriter với encoding UTF-8. Sau khi đóng stream, đọc lại file bằng `XMLInputFactory.createXMLStreamReader(InputStream)` và xác minh Unicode + namespace.

### Bài 9 — Event API

Thêm namespace thứ hai vào `XMLEventFactory.createStartElement`. Tạo thuộc tính qualified bằng `createAttribute(prefix, uri, localName, value)` và namespace declaration tương ứng; parse ngược để kiểm tra URI.

### Bài 10 — Kiểm tra XML không hợp lệ

Thử write một control char không hợp lệ của XML 1.0 vào text. Không khẳng định writer nào cũng reject ở cùng bước. Parse output với parser an toàn, sau đó thêm validation input trước writer.

### Bài 11 — Document lớn

Viết một vòng lặp xuất 100.000 `<item>` từ nguồn stream records. Đo memory trong ứng dụng, không materialize toàn bộ XML. Xác nhận chỉ một root, các end tags cân bằng và END_DOCUMENT hiện diện khi parse output.

### Bài 12 — Bảo mật parser

Test XML từ đầu vào không tin cậy với `SUPPORT_DTD=false`, external entities disabled và `ACCESS_EXTERNAL_DTD=""`. Không cho test mở file/network thực chứa dữ liệu nhạy cảm. Nếu provider bỏ qua một setting thiết yếu, fail closed.

## 20. Câu hỏi tự kiểm tra

**1. `XMLOutputFactory.IS_REPAIRING_NAMESPACES` mặc định là gì?**

`false` theo Javadoc; ứng dụng phải chủ động quản lý mappings và declarations trong nonrepairing mode.

**2. `setPrefix` có tự ghi `xmlns` chưa?**

Không được coi như vậy. Nó bind prefix trong writer context; khi không repair phải ghi namespace declaration thích hợp bằng `writeNamespace`.

**3. Khi nào dùng `writeDefaultNamespace`?**

Khi muốn xuất declaration `xmlns="namespaceURI"` cho default namespace ở scope hiện tại.

**4. Một unprefixed attribute có thuộc default namespace không?**

Không. Default namespace không áp cho unprefixed attributes.

**5. `writeAttribute("code", "x\"&<>")` có phải escape dấu `"` không?**

Có. Javadoc quy định attribute escaping bao gồm `&`, `<`, `>` và `"`.

**6. `writeCharacters` có escape `"` bắt buộc không?**

Không như attribute value; dấu nháy không cần được escape trong element text thường. Writer chịu trách nhiệm các ký tự quan trọng như `&`, `<` và `>`.

**7. Vì sao không pre-escape `&` trước khi gọi writer?**

Vì writer có thể escape thêm lần nữa, tạo `&amp;amp;` và làm thay đổi giá trị text sau khi parse.

**8. `writeCData` có an toàn cho mọi user input không?**

Không. Token `]]>` làm hỏng CDATA section nếu không được xử lý; ưu tiên `writeCharacters` với dữ liệu tùy ý.

**9. Namespace repairing có cho phép so sánh prefix raw chính xác không?**

Không nên. Writer có thể tự sinh hoặc thay prefix; kiểm tra QName/URI.

**10. XML writer có validate XML Schema không?**

Không. Writer không phải XSD validator, và Javadoc lưu ý nó không kiểm tra toàn bộ well-formedness.

**11. `writeStartDocument("UTF-8","1.0")` có tự làm bytes là UTF-8 không?**

Không. Encoding thực phải được cấu hình khi tạo writer trên underlying output.

**12. `XMLStreamWriter.close()` có đóng luôn OutputStream không?**

Theo Javadoc, không. Quản lý/đóng stream riêng.

**13. Một element và attribute dùng cùng prefix có thể trỏ khác URI trong cùng scope không?**

Không thể dùng một mapping prefix một cách mâu thuẫn trong cùng namespace context. Repairing mode có thể tạo prefix khác; nonrepairing mode phải quản lý tường minh.

**14. Làm sao xác minh attribute có namespace đúng?**

Parse với namespace-aware parser, dùng `getAttributeValue(namespaceURI, localName)`.

**15. Vì sao không nên so sánh toàn chuỗi XML từ hai providers?**

Vì prefixes, thứ tự attributes và một số biểu diễn lexical có thể khác mà semantics vẫn đúng.

**16. `XMLEventWriter` nhận gì?**

Các `XMLEvent`, được tạo bởi `XMLEventFactory`; ví dụ `StartElement`, `Characters`, `EndElement`.

**17. Có thể coi XML có text được escape đúng là XML well-formed chắc chắn không?**

Không. Vẫn có thể có tên XML sai, namespace binding sai, invalid code points, CDATA lỗi hoặc thẻ không cân bằng.

**18. Vì sao ví dụ parse ngược phải harden XMLInputFactory?**

Vì parsing và serialization là hai security boundaries khác nhau; khi xử lý XML không đáng tin cần hạn chế DTD/external entities/resource access.

**19. Khi XML rất lớn, dùng StringWriter có giới hạn gì?**

`StringWriter` materialize toàn bộ XML trong memory; dùng OutputStream streaming và thiết kế quota nếu cần giới hạn RAM.

**20. Cách kiểm tra correctness ưu tiên là gì?**

Round-trip parse và assert **namespace URI, local name, attribute values, text values và document structure**, thay vì phụ thuộc raw XML.

## Tài liệu chính thức còn hiệu lực

- [Oracle Java SE 26 — XMLOutputFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLOutputFactory.html): tạo writers, `IS_REPAIRING_NAMESPACES`, thuật toán namespace repair và default false.
- [Oracle Java SE 26 — XMLStreamWriter](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLStreamWriter.html): `writeNamespace`, `writeAttribute`, `writeCharacters`, `writeCData`, `writeStartDocument`, `close` và trạng thái writer.
- [Oracle Java SE 24 — XMLStreamWriter](https://docs.oracle.com/en/java/javase/24/docs/api/java.xml/javax/xml/stream/XMLStreamWriter.html): đối chiếu cùng interface trên JDK được dùng để chạy fixture, bảng namespace repair và escaping.
- [Oracle Java SE 26 — XMLEventFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLEventFactory.html): tạo StartElement/EndElement/Attribute/Namespace/Characters events.
- [Oracle Java SE 26 — XMLEventWriter](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLEventWriter.html): ghi chuỗi events, `add`, `flush`, `close`.
- [Oracle Java SE 26 — XMLInputFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLInputFactory.html): namespace-aware parsing, kiểm soát DTD/external entities.
- [Oracle Java SE 26 — XMLStreamReader](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLStreamReader.html): parse round-trip, QName, namespace URI, attribute getter và text fragments.
- [Oracle Java SE 26 — QName](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/namespace/QName.html): expanded QName và namespace URI.
- [Oracle Java SE 26 — XMLConstants](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/XMLConstants.html): external DTD access control.
- [Oracle Java API for XML Processing Security Guide](https://docs.oracle.com/en/java/javase/26/security/java-api-xml-processing-jaxp-security-guide.html): XXE, external resources và parser limits.

**Ghi nhớ:** Đối với StAX XML output, hãy dùng **`writeStartElement` + `writeNamespace/writeDefaultNamespace` + `writeAttribute` + `writeCharacters` + `writeEndElement`** đúng trạng thái. **Prefix và namespace URI là hai khái niệm khác nhau**; attribute không prefix không kế thừa default namespace. `writeCharacters`/`writeAttribute` tự escape theo ngữ cảnh, nên **không tự escape trước**. Bật `IS_REPAIRING_NAMESPACES` khi muốn tự quản lý prefix ít hơn, nhưng vẫn kiểm tra **ngữ nghĩa QName/URI** và không coi writer là validator. Giữ encoding chính xác, đóng writer/underlying output đúng owner, và dùng parser được cấu hình an toàn để round-trip test.
