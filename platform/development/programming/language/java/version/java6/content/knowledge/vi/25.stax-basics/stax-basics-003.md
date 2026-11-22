# StAX cơ bản — Vòng lặp sự kiện start, text, end và kết thúc tài liệu

## Mục tiêu và phạm vi

**StAX (Streaming API for XML)** là API đọc XML kiểu **pull parser** trong Java SE: chương trình chủ động lấy từng sự kiện thay vì phải xây dựng toàn bộ cây DOM. StAX nằm trong module `java.xml` với package `javax.xml.stream` và vẫn được hỗ trợ trong **Java SE 26**. Việc package bắt đầu bằng `javax` không làm API này trở thành legacy.

Bài học tập trung trực tiếp vào chu trình **mở tài liệu → mở phần tử → xử lý mảnh văn bản → đóng phần tử → kết thúc tài liệu**. Sau bài này, bạn sẽ làm được:

1. Duyệt XML bằng `XMLEventReader.hasNext()` và `nextEvent()`, xử lý `START_DOCUMENT`, `START_ELEMENT`, `CHARACTERS`, `END_ELEMENT`, `END_DOCUMENT`.
2. Duyệt cùng tài liệu bằng `XMLStreamReader`, hiểu sự khác biệt của con trỏ ở **`START_DOCUMENT` ngay sau khi tạo**.
3. Lấy `QName`/namespace, attribute và text từ **đúng loại sự kiện**.
4. Tập hợp text bị chia thành nhiều fragments; không phụ thuộc vào số events, CDATA hay cấu hình coalescing.
5. Xử lý các phần tử lồng nhau, tag rỗng và mixed content bằng một `Deque`/stack.
6. Phân biệt **văn bản trực tiếp** của phần tử với toàn bộ văn bản của subtree.
7. Dùng `nextTag()` và `getElementText()` đúng điều kiện, biết vì sao chúng không thay thế vòng lặp tổng quát.
8. Hiểu `END_ELEMENT` của root **khác** `END_DOCUMENT`.
9. Đóng reader cùng nguồn `Reader/InputStream`, kiểm soát lỗi `XMLStreamException`.
10. Cấu hình XMLInputFactory chống xử lý DTD/external entities trái phép khi đầu vào không đáng tin; nhận biết giới hạn bảo mật theo provider.
11. Biên dịch chương trình Java 17+ độc lập với **26 phép kiểm tra tự động** đã chạy thành công trên JDK 24.

**Special Note:** Chỉ sử dụng các API và kiến thức còn hiệu lực hiện nay, không khuyến nghị cách làm đã bị loại bỏ. Toàn bộ code chạy được được biên dịch với `javac --release 17`; mọi snippet phụ thuộc biến bên ngoài hoặc chỉ mang tính minh họa đều được ghi rõ.

## 1. XML dưới góc nhìn một luồng sự kiện

Giả sử có tài liệu:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<catalog>
  <book id="a">Java</book>
  <book id="b">XML</book>
</catalog>
```

Một luồng sự kiện điển hình:

```text
START_DOCUMENT
START_ELEMENT catalog
  START_ELEMENT book (id=a)
  CHARACTERS "Java"
  END_ELEMENT book
  START_ELEMENT book (id=b)
  CHARACTERS "XML"
  END_ELEMENT book
END_ELEMENT catalog
END_DOCUMENT
```

**Lưu ý:** Dòng ví dụ bỏ qua whitespace-only events do indentation. Nếu đọc XML thật, parser có thể báo các đoạn khoảng trắng giữa những tags. StAX cũng có thể báo COMMENT, PROCESSING_INSTRUCTION, CDATA, SPACE, DTD hoặc ENTITY_REFERENCE theo cấu hình và XML cụ thể.

### Ba ranh giới khác nhau

- `START_DOCUMENT`: sự kiện tài liệu bắt đầu, **không phải** tên của root element.
- `END_ELEMENT catalog`: thẻ root đã đóng, nhưng chưa nhất thiết đã thấy terminal event.
- `END_DOCUMENT`: sự kiện cuối của tài liệu khi parse đầy đủ và hợp lệ.

Một ứng dụng muốn xác nhận toàn bộ nguồn XML well-formed nên tiếp tục duyệt đến `END_DOCUMENT`. Không chỉ dừng ở EOF vật lý mà bỏ qua `XMLStreamException`; XML bị cắt ở giữa thẻ không phải tài liệu hợp lệ.

### Pull parsing và streaming

StAX cho phép xử lý từng bước, theo luồng. Nếu một file có hàng triệu phần tử, chương trình có thể emit record ngay tại END_ELEMENT rồi bỏ state cũ. Tuy nhiên, nếu tự lưu toàn bộ events hoặc nối tất cả text vào một StringBuilder không giới hạn, ứng dụng vẫn có thể tốn RAM tương ứng kích thước dữ liệu. Lợi ích streaming phụ thuộc **cách dùng**, không chỉ việc chọn StAX.

## 2. Hai interface đọc StAX

| Đặc điểm | Event API | Cursor API |
| --- | --- | --- |
| Interface | `XMLEventReader` | `XMLStreamReader` |
| Tạo qua factory | `createXMLEventReader(...)` | `createXMLStreamReader(...)` |
| Bước tiến | `nextEvent()` | `next()` |
| Dữ liệu hiện tại | `XMLEvent` object trả về | Event hiện tại trong reader |
| Xác định loại | `event.isStartElement()`, `getEventType()` | `cursor.getEventType()` |
| Tên thẻ | `event.asStartElement().getName()` | `cursor.getName()` |
| Văn bản | `event.asCharacters().getData()` | `cursor.getText()` |
| Trạng thái đầu | Chưa lấy event | Đang ở `START_DOCUMENT` |
| Đóng | `reader.close()` | `cursor.close()` |
| Cách dùng | Dễ viết xử lý theo event objects | Ít object và thao tác trực tiếp lên cursor |

Cả hai là APIs chuẩn hiện hành, phù hợp các nhu cầu khác nhau. Không tự khẳng định Cursor API luôn nhanh hơn: performance phụ thuộc provider, XML input, cấu hình và cách phân bổ bộ nhớ.

## 3. Vòng lặp Event API chuẩn

Đây là **snippet trong một method** (cần tạo/đóng reader và xử lý exception):

```java
while (events.hasNext()) {
    XMLEvent event = events.nextEvent();

    if (event.isStartDocument()) {
        // Bắt đầu tài liệu.
    } else if (event.isStartElement()) {
        StartElement element = event.asStartElement();
        System.out.println("START " + element.getName());
    } else if (event.isCharacters()) {
        Characters characters = event.asCharacters();
        String fragment = characters.getData();
        // Ghép fragment vào phần tử đang mở.
    } else if (event.isEndElement()) {
        System.out.println("END " + event.asEndElement().getName());
    } else if (event.isEndDocument()) {
        // Đã tiêu thụ terminal END_DOCUMENT.
    }
}
```

### Các loại sự kiện trong vòng lặp

- `XMLEvent.isStartDocument()`: sự kiện bắt đầu document.
- `XMLEvent.isStartElement()`: mở phần tử; `asStartElement()` trả `StartElement`.
- `XMLEvent.isCharacters()`: có character data; `asCharacters().getData()` trả **một fragment**.
- `XMLEvent.isEndElement()`: đóng phần tử; `asEndElement()` trả `EndElement`.
- `XMLEvent.isEndDocument()`: terminal event.
- Các types khác cần chính sách riêng, không được mặc định chuyển `event.toString()` thành text.

**Không gọi `asStartElement` trên CHARACTERS** hoặc `asCharacters` trên START_ELEMENT: các method as-type chỉ hợp lệ khi event có type tương ứng. Kiểm tra helper `is...` trước.

### `XMLEventReader.hasNext` và `nextEvent`

`hasNext()` hỏi còn parsing events không; `nextEvent()` lấy và tiêu thụ event tiếp theo. Nếu parser không thể xử lý XML, `XMLStreamException` có thể phát sinh khi tạo reader/đọc events. Đừng catch rồi đổi lỗi thành một document rỗng thành công.

## 4. START_ELEMENT: tên, namespace và attributes

Giả sử XML:

```xml
<doc xmlns="urn:demo" version="2">
  <item id="a">Xin chào</item>
</doc>
```

Khi đã xác nhận `event.isStartElement()`:

```java
StartElement se = event.asStartElement();
QName qname = se.getName();
String localName = qname.getLocalPart();
String namespaceUri = qname.getNamespaceURI();

Attribute id = se.getAttributeByName(new QName("id"));
String value = id == null ? null : id.getValue();
```

Snippet cần imports `javax.xml.namespace.QName` và `javax.xml.stream.events.Attribute`. `QName` giúp phân biệt hai tags có cùng local name nhưng khác namespace URI.

### Namespace mặc định và thuộc tính không prefix

`<item>` ở trên nằm trong `urn:demo` nhờ default namespace. Nhưng `id` không có prefix **không tự động thuộc default namespace**. Vì vậy `new QName("id")` là cách lấy unprefixed attribute.

Đừng dùng chỉ `qname.getLocalPart()` để khóa dữ liệu nếu tài liệu có hai namespaces khác nhau cùng tag `item`.

### Attribute không nhất thiết là một event giữa START và TEXT

Trong luồng sự kiện khi đọc tài liệu XML thông thường, `StartElement` cung cấp các thuộc tính của thẻ. Không nên viết logic buộc mỗi attribute phải trở thành một event `ATTRIBUTE` riêng. Phần lớn code đọc XML lấy thuộc tính **ngay lúc gặp START_ELEMENT**.

## 5. CHARACTERS, CDATA, entity và text fragments

Với XML:

```xml
<item>Xin <![CDATA[chào]]> &amp; bạn</item>
```

Giá trị text có ý nghĩa là:

```text
Xin chào & bạn
```

Parser có thể trả một hoặc nhiều `CHARACTERS` events tùy coalescing, CDATA, entity và buffer. **Không assert số lượng text chunks cụ thể.** Hãy nối dữ liệu theo phần tử đang được xử lý.

```java
StringBuilder result = new StringBuilder();
// Trong nhánh event.isCharacters():
result.append(event.asCharacters().getData());
```

Đây chỉ là một đoạn của state machine. Nếu có nhiều phần tử, một StringBuilder dùng cho toàn document dễ làm **trộn nội dung**; hãy đặt một builder theo current element frame hoặc field đang thu thập.

### Bật coalescing

```java
factory.setProperty(XMLInputFactory.IS_COALESCING, true);
```

Property này yêu cầu gộp các mảnh character data kề nhau. Nó không biến mixed content có child tags thành một event duy nhất và không bảo đảm mọi provider báo đúng một event text cho toàn bộ phần tử.

### CDATA vẫn là character data

CDATA giữ các dấu markup như ký tự literal trong một vùng text. Khi coalescing bật, ranh giới CDATA có thể không được bảo toàn như một event riêng. Nếu cần bảo toàn chính xác biểu diễn lexical XML, cần lựa chọn parser/serializer phù hợp thay vì chỉ xem text value.

### Entity thường được decode

`&amp;` trong XML text được đọc thành ký tự `&`, không phải chuỗi literal năm ký tự `&amp;`. Không bật phân giải external entities chỉ để xử lý `&amp;` và các predefined XML entities.

### Whitespace có nghĩa

Không dùng `getData().trim()` trên từng fragment nếu text có thể chứa khoảng trắng có ý nghĩa. Ví dụ `<p>Xin <b>chào</b> bạn</p>`: khoảng trắng sau `Xin` và trước `bạn` là một phần của nội dung. Tùy nghiệp vụ, có thể bỏ indentation-only whitespace nhưng phải làm có điều kiện, không phá mixed content.

## 6. END_ELEMENT và stack khi XML lồng nhau

Dùng `Deque<Frame>` hoặc một stack để theo dõi cấu trúc:

```text
START doc       -> push doc
  START item    -> push item
    TEXT "ABC"  -> append vào item
  END item      -> pop item, hoàn tất item
END doc         -> pop doc
END_DOCUMENT    -> stack phải rỗng
```

Khi END_ELEMENT:

```java
QName closing = event.asEndElement().getName();
// Pop frame, so sánh QName, lưu/emit record hoàn tất.
```

Một `Frame` có thể chứa `QName`, `StringBuilder directText` và thông tin nghiệp vụ. Nếu đọc một danh sách items, khi item đóng có thể chuyển thành DTO/emit rồi bỏ frame. Đây là lợi thế của pull parsing.

### Phần tử rỗng

`<empty/>` được báo thành **START_ELEMENT** và **END_ELEMENT**. Không nhất thiết xuất hiện một sự kiện `CHARACTERS ""` ở giữa; nếu muốn kết quả text rỗng, khởi tạo builder rỗng ở START rồi đọc nó ở END.

### Mixed content: direct text khác subtree text

Với `<mixed>Trước <b>đậm</b> sau</mixed>`:

- Direct text của `mixed` là `Trước  sau`.
- Direct text của `b` là `đậm`.
- Text của cả subtree theo thứ tự là `Trước đậm sau`.

Chương trình thực hành dùng **direct text của frame trên cùng**. Nếu muốn subtree text, cần cộng text descendants theo đúng thứ tự xuất hiện và định nghĩa rõ kết quả cần lấy. Không dùng một biến `currentTag` duy nhất vì thẻ con sẽ ghi đè trạng thái thẻ cha.

## 7. END_DOCUMENT và vòng lặp Cursor API

Khi dùng `XMLStreamReader`, ngay sau khi tạo reader, **current event** là `START_DOCUMENT`. Vì vậy vòng lặp nên đọc current event trước:

```java
while (true) {
    int kind = cursor.getEventType();

    if (kind == XMLStreamConstants.START_DOCUMENT) {
        // Đầu tài liệu.
    } else if (kind == XMLStreamConstants.START_ELEMENT) {
        QName name = cursor.getName();
    } else if (kind == XMLStreamConstants.CHARACTERS
            || kind == XMLStreamConstants.CDATA
            || kind == XMLStreamConstants.SPACE) {
        String text = cursor.getText();
    } else if (kind == XMLStreamConstants.END_ELEMENT) {
        QName name = cursor.getName();
    } else if (kind == XMLStreamConstants.END_DOCUMENT) {
        // Kết thúc tài liệu.
    }

    if (!cursor.hasNext()) break;
    cursor.next();
}
```

Đây là snippet nằm trong method có `cursor` và exception handling. `getText()` không dùng tùy ý ở `START_ELEMENT` hay `END_DOCUMENT`; các getters của cursor có tập event states hợp lệ, được Javadoc mô tả. Gọi ở state sai có thể ném `IllegalStateException`.

### Vì sao không bắt đầu bằng `cursor.next()`?

Vì `XMLStreamReader` **đã đứng ở START_DOCUMENT**. Gọi next trước khi xử lý current event sẽ bỏ qua START_DOCUMENT. Nếu ứng dụng cố tình không quan tâm, đó có thể là lựa chọn hợp lệ, nhưng đề bài yêu cầu quan sát cả vòng đời document nên xử lý nó.

### END_ELEMENT root và END_DOCUMENT

Đóng thẻ root chưa có nghĩa parser đã tiêu thụ tất cả input. Tùy tài liệu có thể còn comment/PI và terminal END_DOCUMENT. Với cursor sau khi `END_DOCUMENT`, `hasNext()` trả `false`. Không gọi `next()` vô điều kiện sau terminal state.

### EOF không tương đương XML hợp lệ

Nếu input là `<root><child></root>` hoặc bị cắt dở, parser báo `XMLStreamException`. Đừng diễn giải việc input stream hết bytes là hoàn thành tài liệu có cấu trúc đúng.

## 8. `nextTag()` và `getElementText()`

`nextTag()` thuận tiện khi XML chứa những elements ngăn cách bằng whitespace/comment/PI mà code chỉ muốn đến start/end tag. Nó **không phải** cách đọc mọi text trong mixed content.

```java
int type = cursor.nextTag();
if (type == XMLStreamConstants.START_ELEMENT) {
    String text = cursor.getElementText();
    // Cursor hiện đang ở matching END_ELEMENT.
}
```

`getElementText()` chỉ phù hợp khi phần tử hiện tại có **text-only content**. Nó có thể gom các text fragments và CDATA; nó ném `XMLStreamException` nếu gặp một child `START_ELEMENT` trong nội dung cần đọc.

Ví dụ:

```xml
<value>A &amp; <![CDATA[B]]></value>
```

`getElementText()` trả `A & B` từ element `value`.

Nhưng:

```xml
<value>A<child/>B</value>
```

`getElementText()` ném `XMLStreamException` vì có nested element. Với trường hợp này phải dùng vòng lặp start/text/end thông thường.

Event API cũng có `XMLEventReader.nextTag()` và `getElementText()`; method lấy text làm reader tiến tới matching END_ELEMENT. Không tiếp tục xử lý cùng START/END như thể helper không thay đổi vị trí.

## 9. Xử lý errors và đóng tài nguyên

### XMLStreamException và vị trí lỗi

`XMLStreamException` có thể phát sinh khi tạo/đọc/đóng reader. Thông tin vị trí có thể lấy qua `getLocation()`:

```java
try {
    while (events.hasNext()) {
        XMLEvent e = events.nextEvent();
        // Xử lý...
    }
} catch (XMLStreamException failure) {
    var loc = failure.getLocation();
    int line = loc == null ? -1 : loc.getLineNumber();
    int column = loc == null ? -1 : loc.getColumnNumber();
    // Log metadata an toàn; không phát tán raw XML nhạy cảm.
    throw failure;
} finally {
    events.close();
}
```

Snippet cần biến `events` đã tạo và method khai báo `throws XMLStreamException`. Nếu dữ liệu XML có thể chứa thông tin cá nhân, không log nguyên XML để debug.

### Đóng cả parser lẫn nguồn

`XMLStreamReader.close()` giải phóng tài nguyên liên quan tới reader nhưng **không đóng underlying input source** theo Javadoc. Để tránh leak file/stream, quản lý input riêng:

```java
try (Reader source = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    XMLEventReader events = factory.createXMLEventReader(source);
    try {
        while (events.hasNext()) {
            // Xử lý events.
            events.nextEvent();
        }
    } finally {
        events.close();
    }
}
```

Đoạn này là snippet cần `path` kiểu `Path`, `factory` đã cấu hình và imports `Files`, `StandardCharsets`, `Reader`. Chỉ dùng charset UTF-8 ở đây khi file thật sự có encoding đó; nếu XML dùng một encoding khác và đưa qua Reader đã giải mã sai, XML declaration không thể sửa lại bytes gốc. Với `InputStream`, parser xử lý raw bytes và XML encoding rules.

Không chia sẻ **một** reader đang được duyệt cho nhiều threads. Nếu cần xử lý song song, tách records đã parse thành DTO có ownership rõ ràng.

## 10. Bảo mật XML khi đọc input không đáng tin

Đọc XML từ HTTP request, file upload hoặc external service cần hạn chế DTD, external entities, URL/file access và resource exhaustion. Các settings Java hiện đại:

```java
XMLInputFactory factory = XMLInputFactory.newFactory();
factory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
factory.setProperty(XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
factory.setXMLResolver((publicId, systemId, baseUri, namespace) -> {
    throw new XMLStreamException("External references are disabled");
});
```

Giải thích:

- `SUPPORT_DTD=false` yêu cầu processor không xử lý DTD; **không mặc định bảo đảm mọi provider luôn ném ngay khi thấy DOCTYPE**. Nếu chính sách cấm DOCTYPE hoàn toàn, cần kiểm thử và áp dụng cơ chế từ chối cụ thể.
- `IS_SUPPORTING_EXTERNAL_ENTITIES=false` yêu cầu không resolve external entities.
- `XMLConstants.ACCESS_EXTERNAL_DTD=""` không cho protocol truy cập external DTD/ENTITY. Đây là property được hỗ trợ trong JAXP hiện đại; JDK 24 test đã xác nhận thiết lập.
- `XMLResolver` từ chối external references khi được gọi, như lớp bảo vệ bổ sung.

`setProperty` có thể ném `IllegalArgumentException` nếu provider không hỗ trợ property/value. Khi input không tin cậy, nên **fail closed** thay vì bỏ qua lỗi cấu hình. Cũng cần giới hạn input bytes, depth, số elements, kích thước text, thời gian xử lý và XML parser resource limits. **Chỉ cài vài properties không có nghĩa hệ thống đã chống mọi dạng XML attacks.**

Bài này không dạy cách bật DTD/external entity resolution không cần thiết. Không thực thi external file/network access trong ví dụ.

## 11. Ví dụ đầy đủ Java 17+: hai vòng lặp và 26 kiểm tra

Fixture dùng `StringReader` với input XML nhỏ có namespace, attribute, CDATA, entity, empty element và nested mixed content. `IS_COALESCING=true` được thiết lập nhưng không phụ thuộc số chunks. `Deque` lưu frames đang mở; mỗi fragment text được nối vào frame trên cùng.

**Giới hạn của fixture:** `Facts.directText` dùng local name làm key vì XML kiểm thử không có hai elements trùng tên. Với XML lớn/nhiều item, production parser cần keyed-by-path/QName hoặc danh sách records, nếu không map sẽ bị ghi đè. Assertions kiểm chứng JDK 24 provider; không thay tests cho provider khác.

### File `StaxEventLoopDemo.java`

```java
import java.io.Reader;
import java.io.StringReader;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import javax.xml.XMLConstants;
import javax.xml.namespace.QName;
import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLEventReader;
import javax.xml.stream.XMLStreamConstants;
import javax.xml.stream.XMLStreamException;
import javax.xml.stream.XMLStreamReader;
import javax.xml.stream.events.Attribute;
import javax.xml.stream.events.Characters;
import javax.xml.stream.events.StartElement;
import javax.xml.stream.events.XMLEvent;

public final class StaxEventLoopDemo {
    private static final String XML =
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>" +
        "<doc xmlns=\"urn:demo\" version=\"2\">" +
        "<item id=\"a\">Xin <![CDATA[chào]]> &amp; bạn</item>" +
        "<empty/>" +
        "<mixed>Trước <b>đậm</b> sau</mixed>" +
        "</doc>";

    private static final class Frame {
        final QName name;
        final StringBuilder directText = new StringBuilder();
        Frame(QName name) { this.name = name; }
    }

    private static final class Facts {
        final Map<String, String> directText = new LinkedHashMap<>();
        final List<String> tags = new ArrayList<>();
        boolean startDocument;
        boolean endDocument;
        boolean itemId;
        boolean rootNamespace;
        boolean cursorEnded;
        int starts;
        int ends;
        int textChunks;
    }

    private static XMLInputFactory secureFactory() {
        XMLInputFactory factory = XMLInputFactory.newFactory();
        factory.setProperty(XMLInputFactory.IS_NAMESPACE_AWARE, true);
        factory.setProperty(XMLInputFactory.IS_COALESCING, true);
        factory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
        factory.setProperty(XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setXMLResolver((publicId, systemId, baseUri, namespace) -> {
            throw new XMLStreamException("External references are disabled");
        });
        return factory;
    }

    private static void start(Facts facts, Deque<Frame> stack,
                              QName name, String id, String version) {
        facts.starts++;
        stack.push(new Frame(name));
        facts.tags.add("START:" + name);
        if (name.getLocalPart().equals("doc")) {
            facts.rootNamespace = name.getNamespaceURI().equals("urn:demo")
                    && "2".equals(version);
        }
        if (name.getLocalPart().equals("item")) {
            facts.itemId = "a".equals(id)
                    && name.getNamespaceURI().equals("urn:demo");
        }
    }

    private static void text(Facts facts, Deque<Frame> stack, String value) {
        facts.textChunks++;
        if (!stack.isEmpty()) stack.peek().directText.append(value);
    }

    private static void end(Facts facts, Deque<Frame> stack, QName name)
            throws XMLStreamException {
        if (stack.isEmpty()) throw new XMLStreamException("Unexpected end");
        Frame frame = stack.pop();
        if (!frame.name.equals(name)) {
            throw new XMLStreamException("Element mismatch: " + frame.name + " vs " + name);
        }
        facts.ends++;
        facts.tags.add("END:" + name);
        facts.directText.put(name.getLocalPart(), frame.directText.toString());
    }

    private static Facts eventLoop(String xml) throws Exception {
        Facts facts = new Facts();
        Deque<Frame> stack = new ArrayDeque<>();
        XMLInputFactory factory = secureFactory();
        try (Reader source = new StringReader(xml)) {
            XMLEventReader reader = factory.createXMLEventReader(source);
            try {
                while (reader.hasNext()) {
                    XMLEvent event = reader.nextEvent();
                    if (event.isStartDocument()) {
                        facts.startDocument = true;
                    } else if (event.isStartElement()) {
                        StartElement se = event.asStartElement();
                        Attribute id = se.getAttributeByName(new QName("id"));
                        Attribute version = se.getAttributeByName(new QName("version"));
                        start(facts, stack, se.getName(),
                                id == null ? null : id.getValue(),
                                version == null ? null : version.getValue());
                    } else if (event.isCharacters()) {
                        Characters characters = event.asCharacters();
                        text(facts, stack, characters.getData());
                    } else if (event.isEndElement()) {
                        end(facts, stack, event.asEndElement().getName());
                    } else if (event.isEndDocument()) {
                        facts.endDocument = true;
                    }
                    // COMMENT, PROCESSING_INSTRUCTION, DTD etc. require
                    // a deliberate policy; they are not element text here.
                }
            } finally {
                reader.close();
            }
        }
        if (!stack.isEmpty()) throw new XMLStreamException("Unclosed element");
        return facts;
    }

    private static Facts cursorLoop(String xml) throws Exception {
        Facts facts = new Facts();
        Deque<Frame> stack = new ArrayDeque<>();
        XMLInputFactory factory = secureFactory();
        try (Reader source = new StringReader(xml)) {
            XMLStreamReader cursor = factory.createXMLStreamReader(source);
            try {
                while (true) {
                    int type = cursor.getEventType(); // includes initial START_DOCUMENT
                    if (type == XMLStreamConstants.START_DOCUMENT) {
                        facts.startDocument = true;
                    } else if (type == XMLStreamConstants.START_ELEMENT) {
                        String id = cursor.getAttributeValue(null, "id");
                        String version = cursor.getAttributeValue(null, "version");
                        start(facts, stack, cursor.getName(), id, version);
                    } else if (type == XMLStreamConstants.CHARACTERS
                            || type == XMLStreamConstants.CDATA
                            || type == XMLStreamConstants.SPACE) {
                        text(facts, stack, cursor.getText());
                    } else if (type == XMLStreamConstants.END_ELEMENT) {
                        end(facts, stack, cursor.getName());
                    } else if (type == XMLStreamConstants.END_DOCUMENT) {
                        facts.endDocument = true;
                    }
                    if (!cursor.hasNext()) {
                        facts.cursorEnded =
                            cursor.getEventType() == XMLStreamConstants.END_DOCUMENT;
                        break;
                    }
                    cursor.next();
                }
            } finally {
                cursor.close();
            }
        }
        if (!stack.isEmpty()) throw new XMLStreamException("Unclosed element");
        return facts;
    }

    private static String cursorElementText(String xml) throws Exception {
        XMLInputFactory factory = secureFactory();
        try (Reader source = new StringReader(xml)) {
            XMLStreamReader cursor = factory.createXMLStreamReader(source);
            try {
                int next = cursor.nextTag();
                if (next != XMLStreamConstants.START_ELEMENT)
                    throw new XMLStreamException("Expected start tag");
                String value = cursor.getElementText();
                if (cursor.getEventType() != XMLStreamConstants.END_ELEMENT)
                    throw new XMLStreamException("Expected end tag");
                return value;
            } finally {
                cursor.close();
            }
        }
    }

    private static String eventElementText(String xml) throws Exception {
        XMLInputFactory factory = secureFactory();
        try (Reader source = new StringReader(xml)) {
            XMLEventReader events = factory.createXMLEventReader(source);
            try {
                XMLEvent tag = events.nextTag();
                if (!tag.isStartElement())
                    throw new XMLStreamException("Expected start tag");
                return events.getElementText();
            } finally {
                events.close();
            }
        }
    }

    private static void check(String name, boolean ok) {
        if (!ok) throw new AssertionError(name);
        System.out.println(name + "=true");
    }

    public static void main(String[] args) throws Exception {
        Facts event = eventLoop(XML);
        Facts cursor = cursorLoop(XML);
        check("eventStartDocument", event.startDocument);
        check("eventEndDocument", event.endDocument);
        check("eventBalancedElements", event.starts == 5 && event.ends == 5);
        check("eventRootNamespace", event.rootNamespace);
        check("eventItemAttribute", event.itemId);
        check("eventItemText", "Xin chào & bạn".equals(event.directText.get("item")));
        check("eventNestedBold", "đậm".equals(event.directText.get("b")));
        check("eventMixedDirectText", "Trước  sau".equals(event.directText.get("mixed")));
        check("eventEmptyElement", "".equals(event.directText.get("empty")));
        check("eventTextChunksPresent", event.textChunks >= 3);
        check("cursorStartDocument", cursor.startDocument);
        check("cursorEndDocument", cursor.endDocument);
        check("cursorBalancedElements", cursor.starts == 5 && cursor.ends == 5);
        check("cursorRootNamespace", cursor.rootNamespace);
        check("cursorItemAttribute", cursor.itemId);
        check("cursorTextMatchesEvents", cursor.directText.equals(event.directText));
        check("cursorTagOrderMatchesEvents", cursor.tags.equals(event.tags));
        check("cursorReachedTerminalEvent", cursor.cursorEnded);
        check("cursorTextChunksPresent", cursor.textChunks >= 3);
        String textOnly = "<value>Hi &amp; <![CDATA[chào]]></value>";
        check("cursorGetElementText",
                "Hi & chào".equals(cursorElementText(textOnly)));
        check("eventGetElementText",
                "Hi & chào".equals(eventElementText(textOnly)));
        boolean mixedRejected = false;
        try {
            cursorElementText("<value>A<child/>B</value>");
        } catch (XMLStreamException expected) {
            mixedRejected = true;
        }
        check("mixedGetElementTextRejected", mixedRejected);
        boolean malformedRejected = false;
        try {
            eventLoop("<root><child></root>");
        } catch (XMLStreamException expected) {
            malformedRejected = true;
        }
        check("malformedXmlRejected", malformedRejected);
        XMLInputFactory security = secureFactory();
        check("dtdSupportDisabled",
                Boolean.FALSE.equals(security.getProperty(XMLInputFactory.SUPPORT_DTD)));
        check("externalEntitiesDisabled",
                Boolean.FALSE.equals(
                    security.getProperty(XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES)));
        check("externalDtdProtocolsDenied",
                "".equals(security.getProperty(XMLConstants.ACCESS_EXTERNAL_DTD)));
    }
}
```

### Lệnh biên dịch và chạy

```bash
javac --release 17 StaxEventLoopDemo.java
java StaxEventLoopDemo
```

Không cần dependency ngoài JDK. Trong ứng dụng dùng `module-info.java`, khai báo `requires java.xml;`. Chương trình đã biên dịch với `--release 17` và chạy trên OpenJDK 24; không phải ví dụ giả định chưa kiểm thử.

### Stdout chính xác (OpenJDK 24)

```text
eventStartDocument=true
eventEndDocument=true
eventBalancedElements=true
eventRootNamespace=true
eventItemAttribute=true
eventItemText=true
eventNestedBold=true
eventMixedDirectText=true
eventEmptyElement=true
eventTextChunksPresent=true
cursorStartDocument=true
cursorEndDocument=true
cursorBalancedElements=true
cursorRootNamespace=true
cursorItemAttribute=true
cursorTextMatchesEvents=true
cursorTagOrderMatchesEvents=true
cursorReachedTerminalEvent=true
cursorTextChunksPresent=true
cursorGetElementText=true
eventGetElementText=true
mixedGetElementTextRejected=true
malformedXmlRejected=true
dtdSupportDisabled=true
externalEntitiesDisabled=true
externalDtdProtocolsDenied=true
```

Đây là **26/26 assertions PASS**. Mỗi dòng chỉ được in nếu `check` xác nhận đúng; sai sẽ ném `AssertionError`. Code chạy bằng StAX provider trên JDK 24. Số chunks được kiểm tra theo bất đẳng thức, không khẳng định số lượng tuyệt đối trên mọi provider.

### Đọc các nhóm kết quả

| Nhóm | Ý nghĩa |
| --- | --- |
| `eventStartDocument`/`eventEndDocument` | EventReader thấy đủ hai ranh giới tài liệu |
| `eventBalancedElements` | Năm cặp start/end của doc, item, empty, mixed, b |
| `eventRootNamespace` | Root namespace `urn:demo` và attribute version đúng |
| `eventItemAttribute` | Lấy unprefixed attribute `id="a"` |
| `eventItemText` | CDATA + entity tạo đúng `Xin chào & bạn` |
| `eventNestedBold` | Text của thẻ con `b` được giữ riêng |
| `eventMixedDirectText` | Parent direct text `Trước  sau` |
| `eventEmptyElement` | Empty element vẫn có cặp start/end |
| `cursorStartDocument`/`cursorEndDocument` | Cursor xử lý current START_DOCUMENT và terminal END_DOCUMENT |
| `cursorTextMatchesEvents`/`cursorTagOrderMatchesEvents` | Hai cách đọc cho cùng kết quả ngữ nghĩa và thứ tự thẻ |
| `cursorReachedTerminalEvent` | Cursor ở END_DOCUMENT khi hết events |
| `cursorGetElementText`/`eventGetElementText` | Text-only helpers đọc đúng và ghép entity/CDATA |
| `mixedGetElementTextRejected` | getElementText không phù hợp khi có nested element |
| `malformedXmlRejected` | Parser báo lỗi khi XML sai cấu trúc |
| `dtdSupportDisabled`, `externalEntitiesDisabled`, `externalDtdProtocolsDenied` | Factory được harden theo settings được kiểm thử |

## 12. Kết quả nào không nên suy rộng từ fixture?

1. **Số mảnh text không cố định.** `IS_COALESCING` giảm một số chia tách kề nhau nhưng không biến mọi document thành một CHARACTERS duy nhất.
2. **Map theo local name không phù hợp dữ liệu lặp.** Demo có từng local name độc nhất; production parser cần danh sách/path/QName kết hợp key nghiệp vụ.
3. **Security factory settings cần kiểm thử theo provider.** Demo cho biết JDK 24 chấp nhận settings; không chứng minh mọi XML provider khác hành xử đồng nhất.
4. **Đọc đến END_DOCUMENT không đồng nghĩa business validation thành công.** XML well-formed có thể vẫn có amount âm, thiếu field hoặc dữ liệu không hợp lệ.
5. **StringReader không kiểm thử raw-byte decoding.** XML declaration chứa UTF-8 chỉ là nội dung text ở fixture; với InputStream thật cần kiểm tra BOM/charset.
6. **Mixed content có nhiều semantics.** Demo chọn direct text. Muốn full subtree text hoặc giữ markup/CDATA boundaries cần cấu trúc output khác.
7. **Thứ tự/comment/PI tùy input.** Demo tập trung start/text/end; ứng dụng cần policy cho events khác nếu document cho phép.
8. **StAX không phải XML signature validator.** Nếu dữ liệu cần xác thực chữ ký/schema/authorization, triển khai lớp kiểm tra riêng phù hợp.

## 13. Checklist lỗi thường gặp

| Sai lầm | Điều chỉnh |
| --- | --- |
| `asCharacters` không kiểm tra event type | `event.isCharacters()` trước |
| Gọi `next()` trước khi đọc initial cursor event | Đọc `getEventType()` ở START_DOCUMENT |
| Dừng sau END_ELEMENT root | Tiếp tục/đối chiếu END_DOCUMENT nếu cần parse hết |
| Nối toàn bộ text vào một builder chung | Builder theo frame/field |
| `trim()` mọi character fragment | Giữ whitespace theo nghĩa |
| Coi CDATA là một thẻ con | Xử lý như character data khi parse |
| Coi `<empty/>` không có END_ELEMENT | Luôn xử lý cặp start/end |
| Đòi mọi text element có một CHARACTERS | Chấp nhận nhiều fragments |
| So sánh localName mà bỏ namespace | Dùng `QName` |
| Bỏ qua attribute ở START_ELEMENT | Lấy từ StartElement hoặc cursor khi đúng state |
| `getElementText` trên XML có child | Dùng vòng lặp tổng quát |
| `nextTag` cho text có nghĩa | Dùng next/nextEvent |
| Coi END_DOCUMENT là EOF không lỗi | Bảo toàn XMLStreamException |
| Không đóng underlying FileInputStream | Dùng try-with-resources cho source |
| XML không đáng tin mà cho external entities mặc định | Harden XMLInputFactory và test |
| Không giới hạn XML depth/text length | Thêm quota cho parser/pipeline |
| Chỉ test trên một provider rồi khóa số chunks | Assert text/hierarchy thay vì chunks |
| Parser thành công thì auto-commit dữ liệu | Tách XML parse correctness khỏi DB transaction policy |

## 14. Bài tập tự luyện

### Bài 1: XML đơn giản

Dùng Event API với `<data><name>Lan</name></data>`. Ghi nhận START_DOCUMENT, START_ELEMENT data, START_ELEMENT name, text Lan, hai END_ELEMENT và END_DOCUMENT. Viết assertions kiểm tra stack trở về rỗng.

### Bài 2: CDATA và entity

Đổi text thành `Xin <![CDATA[chào]]> &amp; bạn` và thử `IS_COALESCING=true/false`. So sánh các chunks quan sát được; giá trị cuối cùng phải là `Xin chào & bạn`. Không assert số chunks cố định.

### Bài 3: Phần tử rỗng

Thêm `<empty/>` vào root và kiểm tra hai structural events, nhưng không yêu cầu một CHARACTERS rỗng được tạo.

### Bài 4: Lặp phần tử

Tạo hai `<item id="a">A</item>`, `<item id="b">B</item>`. Thay Map key localName trong fixture bằng `List<Item>` để không ghi đè. Emit Item tại END_ELEMENT.

### Bài 5: Mixed content

Với `<p>Trước <strong>đậm</strong> sau</p>`, tính direct text và subtree text riêng. Hãy xác định rõ mục tiêu trước khi nối.

### Bài 6: Cursor event đầu

Thử gọi `cursor.next()` trước vòng lặp và quan sát assertion START_DOCUMENT sai. Khôi phục vòng lặp xử lý current event trước next.

### Bài 7: Error location

Đưa `<root><child></root>` vào parser, catch XMLStreamException rồi lấy `getLocation().getLineNumber()` nếu có; không coi input lỗi là parse thành công.

### Bài 8: ElementText

Thử `<x>A &amp; B</x>` với `getElementText` rồi thử `<x>A<b>B</b>C</x>`. Giải thích vì sao trường hợp thứ hai không phải text-only.

### Bài 9: Dữ liệu lớn

Thiết kế parser streaming cho `<orders><order>...</order>...</orders>`; giữ tối đa một order DTO và stack. Chỉ commit batch khi yêu cầu tính nguyên tử và toàn bộ document đã được kiểm tra đến END_DOCUMENT.

### Bài 10: Untrusted XML

Xác nhận các factory properties như trong demo. Viết test cho DTD/external entity mà **không truy cập tài nguyên thật có dữ liệu nhạy cảm**, và kiểm tra parser không tự truy cập network/file ngoài policy.

## 15. Câu hỏi kiểm tra kiến thức

**1. StAX là pull hay push parser?** Pull: ứng dụng gọi next/nextEvent để lấy dữ liệu.

**2. `XMLEventReader` trả gì sau `nextEvent()`?** Một `XMLEvent` object biểu diễn sự kiện kế tiếp.

**3. `XMLStreamReader` đang ở đâu ngay sau khi tạo?** `START_DOCUMENT`.

**4. `END_ELEMENT` của root đã là `END_DOCUMENT` chưa?** Chưa. Hai event khác nhau.

**5. Một `<empty/>` có cần CHARACTERS event không?** Không, nhưng có cặp start/end.

**6. XML có CDATA và entity cần bao nhiêu text events?** Không cố định. Ghép fragments đúng scope.

**7. `getData()` với XML `&amp;` sẽ trả gì?** Ký tự `&` trong text đã decode.

**8. Bỏ whitespace bằng trim trên từng chunk có an toàn không?** Không với mixed text; có thể mất khoảng trắng có nghĩa.

**9. `QName` giúp gì?** Phân biệt local name và namespace URI.

**10. Thuộc tính `id` không prefix có thuộc default namespace không?** Không.

**11. `getElementText` hỗ trợ nested element không?** Không; có thể ném XMLStreamException.

**12. `nextTag` có thay thế nextEvent tổng quát không?** Không khi cần xử lý text có nghĩa.

**13. Một reader.close có luôn close underlying source không?** Không nên giả định; đóng nguồn riêng.

**14. Khi input malformed có thể coi parser hết input là thành công không?** Không; phải xử lý XMLStreamException.

**15. XMLInputFactory mặc định có đủ chống XXE không?** Không được dựa vào defaults; cấu hình và kiểm thử.

**16. StAX có tự validate business data không?** Không; nó xử lý XML parsing.

**17. Muốn xử lý XML lớn tiết kiệm memory nên làm gì?** Emit records ở END_ELEMENT, giới hạn buffers/depth.

**18. Vì sao demo không test chính xác số text chunks?** Vì segmentation phụ thuộc provider/cấu hình.

## Tài liệu hiện hành

- [Oracle Java SE 26 — XMLInputFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLInputFactory.html) — tạo event/cursor readers và security properties.
- [Oracle Java SE 26 — XMLEventReader](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLEventReader.html) — hasNext/nextEvent/nextTag/getElementText/close.
- [Oracle Java SE 26 — XMLStreamReader](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLStreamReader.html) — current event, next, hasNext, getters hợp lệ, END_DOCUMENT.
- [Oracle Java SE 26 — XMLEvent](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/events/XMLEvent.html) — event types và as/is helpers.
- [Oracle Java SE 26 — StartElement](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/events/StartElement.html) — QName, namespaces và attributes.
- [Oracle Java SE 26 — Characters](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/events/Characters.html) — getData, whitespace và CDATA.
- [Oracle Java SE 26 — EndElement](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/events/EndElement.html) — closing QName.
- [Oracle Java SE 26 — XMLStreamConstants](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLStreamConstants.html) — các event codes.
- [Oracle Java SE 26 — XMLStreamException](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLStreamException.html) — parse errors, location.
- [Oracle Java SE 26 — QName](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/namespace/QName.html) — namespace-aware names.
- [Oracle Java SE 26 — XMLConstants](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/XMLConstants.html) — external DTD protocol access control.
- [Oracle Java API for XML Processing Security Guide](https://docs.oracle.com/en/java/javase/26/security/java-api-xml-processing-jaxp-security-guide.html) — cấu hình chống XXE/DTD và resource limits.

**Ghi nhớ:** Vòng lặp StAX xử lý **START_DOCUMENT → START_ELEMENT → CHARACTERS (có thể nhiều mảnh) → END_ELEMENT → END_DOCUMENT**. Event reader dùng `nextEvent`, cursor reader xử lý `getEventType` hiện tại trước `next`. Luôn ghép text đúng element scope, phân biệt namespace và mixed content, đọc đến END_DOCUMENT nếu cần xác minh toàn tài liệu, đóng parser/nguồn, xử lý XMLStreamException và cấu hình XMLInputFactory an toàn cho đầu vào không đáng tin.
