# XMLEventReader và mô hình đối tượng sự kiện trong StAX (Java 17+)

## 1. Mục tiêu: đọc XML bằng các đối tượng sự kiện

Khi ứng dụng Java xử lý XML từ file, HTTP, integration gateway hoặc cơ sở dữ liệu, StAX (Streaming API for XML) cho phép đọc tuần tự mà không cần dựng một cây DOM đầy đủ. Bên cạnh `XMLStreamReader` theo kiểu **cursor**, Java còn cung cấp **`XMLEventReader`** theo kiểu **iterator của các đối tượng sự kiện**.

Khởi đầu:

```java
XMLInputFactory factory = XMLInputFactory.newDefaultFactory();
XMLEventReader events = factory.createXMLEventReader(source);
```

Đây là **snippet minh họa**: `source` là `java.io.Reader` hoặc `InputStream` tương ứng overload, và khi nhận XML không đáng tin cần **cấu hình factory an toàn trước khi tạo reader** như ở mục 6. Không copy hai dòng này làm chương trình Java hoàn chỉnh.

Với `XMLEventReader`, thay vì gọi `cursor.next()` rồi đọc dữ liệu từ trạng thái của cursor, ứng dụng gọi `events.nextEvent()` để nhận một object triển khai `javax.xml.stream.events.XMLEvent`. Object ấy có loại sự kiện và các phương thức để đọc tên phần tử, thuộc tính, text, vị trí trong tài liệu…

**Mô hình đơn giản:**

```text
XML bytes hoặc XML characters
               |
     XMLInputFactory (đã harden)
               |
    createXMLEventReader(...)
               |
          XMLEventReader
               |
         peek / nextEvent
               |
      +--------+---------+
      |                  |
    XMLEvent         XMLEvent ...
      |
      +-- StartDocument / EndDocument
      +-- StartElement / EndElement
      +-- Characters / Comment
      +-- ProcessingInstruction
      +-- DTD / EntityReference (tùy cấu hình)
               |
        consumer / filter / writer
               |
 close XMLEventReader và input
```

Bài này thuộc **StAX nâng cao**, trọng tâm là **event-object model**, cách lấy dữ liệu từ các subtype, điều khiển iterator, lọc sự kiện, chuyển tiếp sang `XMLEventWriter`, bảo mật và hiệu năng. Các API đều đang được hỗ trợ trên Java 17+; package `javax.xml.stream` vẫn là một phần của module `java.xml` và **không phải API legacy**.

Sau bài, bạn sẽ có thể:
1. Phân biệt `XMLEventReader` với `XMLStreamReader` và DOM.
2. Tạo event reader qua `XMLInputFactory` từ `Reader`/`InputStream`.
3. Dùng `peek()`, `nextEvent()`, `hasNext()`, `nextTag()`, `getElementText()` đúng điều kiện.
4. Phân loại `XMLEvent` thành `StartElement`, `EndElement`, `Characters`, `Comment`, `StartDocument`… và xử lý `QName`/attributes/namespaces.
5. Lọc event bằng `EventFilter` và `createFilteredReader` mà không phá vỡ logic.
6. Phòng chống XXE, DTD/external entities, XML bombs và parser khác provider.
7. Đóng đúng nguồn và reader, xử lý lỗi/line location, kiểm thử Unicode.
8. Biên dịch và chạy hai ví dụ Java 17+: **đọc/lọc** XML và **tạo/đọc lại** các event.

## 2. XMLEventReader khác XMLStreamReader như thế nào?

Cùng là pull-parser StAX, nhưng **đối tượng trả về của mỗi lần đọc khác nhau**:

| Tiêu chí | `XMLStreamReader` (cursor) | `XMLEventReader` (event iterator) |
| --- | --- | --- |
| Lấy sự kiện | `int event = cursor.next()`. | `XMLEvent event = reader.nextEvent()`. |
| Dữ liệu sự kiện | Đọc từ cursor hiện tại: `getLocalName()`, `getText()`… | Nằm trong object `XMLEvent` hoặc subtype: `asStartElement()`, `asCharacters()`… |
| Nhìn trước | Có `getEventType()` cho trạng thái hiện tại; không có `peek()` đồng nghĩa với event reader. | `peek()` xem sự kiện kế tiếp mà **không tiêu thụ**. |
| Lọc | `StreamFilter` + `createFilteredReader(XMLStreamReader, StreamFilter)`. | `EventFilter` + `createFilteredReader(XMLEventReader, EventFilter)`. |
| Kết nối writer | `XMLStreamWriter` ghi theo từng method. | `XMLEventWriter.add(XMLEvent)` dễ chuyển tiếp event có lựa chọn. |
| Lưu event tạm | Cursor state thay đổi sau `next()`; phải copy thông tin cần dùng. | Event là value object; có thể giữ trong thời gian cần thiết, nhưng giữ quá nhiều thì tốn RAM. |
| Cấp phát | Thường ít wrapper objects hơn. | Tạo/đưa event objects; có chi phí allocation tùy provider. |
| DOM tree | Không tự dựng cây DOM đầy đủ. | Cũng không tự dựng DOM đầy đủ. |

**Không suy rằng event reader luôn chậm hơn cursor reader:** performance thực phụ thuộc implementation, dữ liệu, allocation/GC, cách lọc và logic ứng dụng. Chỉ benchmark với provider và XML thực tế mới đánh giá được. Event reader thuận tiện khi bạn cần event objects để kiểm tra, chuyển tiếp, lọc hoặc tách các bước xử lý.

Ví dụ hai cách tương đương về mục đích:

```java
// Cursor: các getter đọc state ở vị trí hiện tại.
int eventType = cursor.next();
if (eventType == XMLStreamConstants.START_ELEMENT) {
    String elementName = cursor.getLocalName();
}

// Event: getter đọc từ value object nhận được.
XMLEvent event = events.nextEvent();
if (event.isStartElement()) {
    String elementName =
            event.asStartElement().getName().getLocalPart();
}
```

Đây là **snippet so sánh**, chưa khai báo `cursor`, `events` và imports; không phải một chương trình độc lập. Cả hai đều đọc **tuần tự**, không tự hỗ trợ truy cập ngẫu nhiên đến một node bất kỳ của XML.

## 3. Tạo XMLEventReader đúng cách

`XMLInputFactory` có các overload liên quan:

```java
XMLEventReader createXMLEventReader(Reader reader);
XMLEventReader createXMLEventReader(InputStream stream);
XMLEventReader createXMLEventReader(
        InputStream stream, String encoding);
XMLEventReader createXMLEventReader(
        String systemId, Reader reader);
XMLEventReader createXMLEventReader(
        String systemId, InputStream stream);
XMLEventReader createXMLEventReader(Source source);
XMLEventReader createXMLEventReader(XMLStreamReader reader);
```

Đây là **chữ ký API tóm lược** từ `XMLInputFactory`, không phải định nghĩa class Java đầy đủ. Các overload có thể ném `XMLStreamException`.

**Chọn overload:**
- Đã có `String` XML: bọc bằng `new StringReader(xmlText)`.
- Đã có `Reader` UTF-8/Unicode: dùng `createXMLEventReader(reader)`.
- Có **bytes XML**: dùng `InputStream`; parser áp dụng quy tắc XML encoding/BOM/declaration.
- Có bytes với encoding đã biết chắc: overload `(InputStream, String encoding)`.
- Có JAXP `Source`: dùng overload `(Source)` nếu provider hỗ trợ source đó.
- Đang có một `XMLStreamReader`: có thể yêu cầu factory tạo event reader từ cursor, nhưng vẫn phải quản lý vòng đời reader/source và kiểm soát việc parser đã tiêu thụ sự kiện đến đâu.
- `systemId` là định danh nguồn/base URI, **không phải nội dung XML**; không truyền URL không đáng tin rồi cho phép truy cập external resources.

### 3.1. newDefaultFactory hay newFactory?

```java
XMLInputFactory defaultFactory =
        XMLInputFactory.newDefaultFactory();

XMLInputFactory discoveredFactory =
        XMLInputFactory.newFactory();
```

`newDefaultFactory()` (Java 9+) chọn StAX implementation system-default tích hợp JDK. `newFactory()` dùng cơ chế tìm JAXP service provider, có thể chọn thư viện bên thứ ba. Cả hai đều hợp lệ ở Java 17+. Với một ví dụ cần hành vi dự đoán được, dùng `newDefaultFactory()`; trong production nếu chọn provider khác, kiểm chứng security properties và hiệu năng của provider đó.

**Không tạo bằng `new XMLInputFactory()`:** đây là abstract class với constructor `protected`. Cũng không tưởng rằng factory mới tạo tự động chống XXE. Phải đặt chính sách trước khi tạo reader.

### 3.2. StringReader và Reader life cycle

```java
String sourceXml = "<msg><text>Xin chào</text></msg>";
XMLInputFactory factory = secureFactory();

try (Reader input = new StringReader(sourceXml)) {
    XMLEventReader reader = factory.createXMLEventReader(input);
    try {
        while (reader.hasNext()) {
            XMLEvent event = reader.nextEvent();
            // Xử lý sự kiện.
        }
    } finally {
        reader.close();
    }
}
```

Đây là **snippet**; `secureFactory()` có trong ví dụ đầy đủ mục 9. `XMLEventReader.close()` **không đóng nguồn bên dưới** theo Javadoc, vì vậy cần đóng `Reader` riêng trong try-with-resources. `XMLEventReader` không trực tiếp implements `AutoCloseable`, nên không thể dùng `try (XMLEventReader reader = ...)` như `Reader` Java.

Với `InputStream` cũng vậy: đóng event reader và đóng byte stream riêng. Nếu XML đến từ HTTP body hoặc JDBC `SQLXML`, nguồn còn liên quan đến response/transaction; không để event reader sống lâu hơn đối tượng nguồn.

### 3.3. Reader là ký tự, InputStream là bytes

- `Reader` cung cấp Java `char`/UTF-16 units đã được giải mã. Parser không tự dùng XML declaration để “sửa” charset đã decode sai trước đó.
- `InputStream` cung cấp bytes; parser phải xử lý XML encoding detection theo XML specification, với BOM/declaration khi có.
- `String.length()` và một `Reader` tính theo UTF-16 code units, không tương đương UTF-8 bytes hoặc số Unicode code points.
- Dữ liệu có tiếng Việt, emoji, ký tự kết hợp dấu và các encoding khác cần integration tests, nhất là khi XML đi qua database/HTTP.
- Không tự giả định XML output StringWriter có bytes UTF-8; StringWriter chỉ giữ ký tự Java, không mã hóa bytes.

**Nếu nguồn XML không đáng tin**, khóa external entities/DTD trước cả overload InputStream và Reader. Không có overload nào miễn trừ yêu cầu security.

## 4. XMLEventReader: iterator API và precondition

`XMLEventReader` extends `Iterator<Object>` và bổ sung các method chuyên biệt của StAX. Nên ưu tiên **`nextEvent()`** khi làm việc với XML, vì nó trả `XMLEvent` và có thể ném `XMLStreamException`.

| Method | Hoạt động | Chú ý |
| --- | --- | --- |
| `hasNext()` | Kiểm tra còn sự kiện hay không. | Không bảo đảm dữ liệu về sau well-formed; lỗi có thể chỉ xuất hiện khi đọc tiếp. |
| `nextEvent()` | Lấy và tiêu thụ sự kiện kế tiếp; trả `XMLEvent`. | Ném `XMLStreamException` cho lỗi parser, `NoSuchElementException` khi hết event. |
| `peek()` | Xem **sự kiện kế tiếp**, không tiêu thụ. | Có thể trả null khi không còn sự kiện. |
| `nextTag()` | Bỏ qua whitespace/comment/processing instructions phù hợp và trả START_ELEMENT/END_ELEMENT tiếp theo. | Không dùng để bỏ qua text dữ liệu có ý nghĩa; có thể ném `XMLStreamException`. |
| `getElementText()` | Đọc toàn text của element hiện tại. | Phải vừa tiêu thụ START_ELEMENT của **text-only** element; đến END_ELEMENT tương ứng. |
| `getProperty(name)` | Hỏi property của implementation. | Tên không hỗ trợ có thể ném `IllegalArgumentException`. |
| `close()` | Giải phóng resource của reader. | **Không tự đóng underlying input source**; có thể ném `XMLStreamException`. |
| `next()` từ Iterator | Trả `Object` theo Iterator API. | Với XML, `nextEvent()` rõ kiểu và cơ chế lỗi hơn. |

### 4.1. peek() để xem sự kiện trước khi đọc

Ngay sau khi `XMLInputFactory.createXMLEventReader`, reader thường có sự kiện `StartDocument` kế tiếp. Bạn có thể kiểm tra mà không tiêu thụ:

```java
XMLEvent preview = events.peek();

if (preview != null && preview.isStartDocument()) {
    // Có START_DOCUMENT ở phía trước.
}

XMLEvent consumed = events.nextEvent();
// consumed vẫn là event đã được xem bằng peek().
```

Đây là **snippet**, cần `XMLEventReader events` và `XMLEvent`. Không dựa vào `peek()` như giải pháp “lookahead vô hạn”: nó chỉ xem event kế tiếp. Nếu muốn lookahead nhiều events, phải thiết kế buffer giới hạn hoặc state machine riêng.

**Khác với cursor:** `XMLStreamReader.getEventType()` nói về sự kiện **hiện tại**, còn `XMLEventReader.peek()` nói về **sự kiện chưa tiêu thụ tiếp theo**. Đừng thay hai thao tác cho nhau khi chuyển code từ cursor sang event model.

### 4.2. getElementText() và trạng thái sau gọi

Khi vòng `nextEvent()` vừa trả về `StartElement` của một element nhỏ chứa văn bản:

```java
XMLEvent current = events.nextEvent();

if (current.isStartElement()
        && "customer".equals(
                current.asStartElement().getName().getLocalPart())) {
    String customer = events.getElementText();
    // Toàn bộ nội dung customer đã được lấy.
}
```

Đây là **snippet**, code mẫu đầy đủ ở mục 9 có kiểm tra namespace. **Precondition** của `getElementText()`: sự kiện hiện tại phải là `START_ELEMENT`. Nó tiêu thụ nội dung cho đến `END_ELEMENT` tương ứng; vị trí đọc tiếp đã thay đổi. Nếu element có **nested child element**, phương thức có thể ném `XMLStreamException` vì đây không phải text-only element.

**Không dùng `getElementText()` trên body XML cực lớn**: method tích lũy text thành một `String`, mất lợi ích bounded memory. Với text dài, duyệt `Characters` events theo chunks và ghi trực tiếp vào một `Writer` hoặc sink khác có giới hạn.

### 4.3. nextTag(): chỉ thích hợp cho element-only content

```java
XMLEvent tag = events.nextTag();

if (tag.isStartElement()) {
    StartElement element = tag.asStartElement();
    // Đọc tên/thông tin tag.
}
```

Đây là snippet khi reader đang ở vị trí mà event tiếp theo hợp lệ theo contract `nextTag()`. Method bỏ qua những event whitespace/comment/processing instructions không có ý nghĩa và kỳ vọng tag. Nếu gặp text như `"Hello"` giữa hai tags, có thể ném `XMLStreamException`. XML **mixed content** cần vòng `nextEvent()` để không làm mất text. Không dùng `nextTag()` để “nhảy tới đơn hàng kế tiếp” bất kể nội dung.

## 5. Mô hình đối tượng sự kiện: XMLEvent và các subtype

`javax.xml.stream.events.XMLEvent` là interface chung cho sự kiện XML. Mỗi instance có:
- `getEventType()`: số event type tương thích `XMLStreamConstants`.
- Các predicates như `isStartElement()`, `isEndElement()`, `isCharacters()`, `isStartDocument()`, `isEndDocument()`, `isAttribute()`, `isNamespace()`, `isEntityReference()`, `isProcessingInstruction()`.
- Các methods chuyên biệt `asStartElement()`, `asEndElement()`, `asCharacters()` — **chỉ gọi khi predicate/type phù hợp**.
- `getLocation()`: vị trí input gắn với event (line/column có thể không đầy đủ tùy parser).
- `getSchemaType()`: kiểu schema gắn với sự kiện khi implementation có thông tin; có thể null.

Các subtype trong package `javax.xml.stream.events`:

| Subtype | Loại nội dung | Method đáng chú ý |
| --- | --- | --- |
| `StartDocument` | XML declaration/document beginning. | `getVersion()`, `getCharacterEncodingScheme()`, `isStandalone()`. |
| `EndDocument` | Kết thúc XML document. | Dấu mốc cuối luồng sự kiện. |
| `StartElement` | Mở đầu tag và attributes/namespaces. | `getName()`, `getAttributes()`, `getAttributeByName()`, `getNamespaces()`. |
| `EndElement` | Kết thúc tag. | `getName()`, `getNamespaces()`. |
| `Characters` | Text/CDATA/whitespace event. | `getData()`, `isCData()`, `isWhiteSpace()`, `isIgnorableWhiteSpace()`. |
| `Attribute` | Thuộc tính của element. | `getName()`, `getValue()`, `isSpecified()`. |
| `Namespace` | Namespace declaration, một dạng chuyên biệt của Attribute. | `getPrefix()`, `getNamespaceURI()`, `isDefaultNamespaceDeclaration()`. |
| `Comment` | XML comment. | `getText()`. |
| `ProcessingInstruction` | Processing instruction. | `getTarget()`, `getData()`. |
| `DTD` | Khai báo DTD. | `getDocumentTypeDeclaration()` và thông tin entities tùy provider. |
| `EntityReference` | Entity reference nếu parser phát sinh event loại này. | `getName()`, `getDeclaration()`. |

**Không phải mọi input tạo một instance riêng của mọi subtype.** Ví dụ:
- Attributes thường được truy cập qua `StartElement.getAttributes()` thay vì đợi một `ATTRIBUTE` event độc lập ở top-level reader.
- Parser có thể chuyển CDATA thành `Characters` events, hoặc coalesce text theo config.
- Khi vô hiệu DTD/external entities, cách parser biểu diễn `DTD` và `EntityReference` thay đổi theo provider.
- Text có thể bị chia thành nhiều `Characters` events; không giả định mỗi text node tương ứng một event.

### 5.1. getEventType() kết hợp asStartElement()

```java
while (events.hasNext()) {
    XMLEvent event = events.nextEvent();

    if (event.isStartElement()) {
        StartElement start = event.asStartElement();
        QName qName = start.getName();
        String local = qName.getLocalPart();
        String namespaceUri = qName.getNamespaceURI();

    } else if (event.isEndElement()) {
        EndElement end = event.asEndElement();

    } else if (event.isCharacters()) {
        Characters chars = event.asCharacters();
        String text = chars.getData();
    }
}
```

Đây là **snippet**, các biến `local`, `namespaceUri`, `end`, `text` chỉ để minh họa; cần imports `XMLEventReader`, `XMLEvent`, `StartElement`, `EndElement`, `Characters`, `QName`. Khi chỉ cần đếm hoặc định tuyến sự kiện, có thể so sánh `event.getEventType() == XMLStreamConstants.START_ELEMENT` thay cho predicate.

**Đừng gọi `asCharacters()` tại event COMMENT hoặc START_ELEMENT:** điều đó không có nghĩa, có thể gây `ClassCastException`. Kiểm tra subtype trước.

### 5.2. StartElement, QName và namespace

XML ví dụ:

```xml
<o:order xmlns:o="urn:demo:orders"
         id="A-01" amount="12.50">
    <o:customer>Hà Nội</o:customer>
</o:order>
```

`StartElement start` ở tag order có:
- `start.getName()` là `QName` gồm namespace URI `urn:demo:orders`, local part `order` và prefix `o`.
- `start.getAttributeByName(new QName("amount"))` trả `Attribute` không namespace với giá trị `12.50`.
- `start.getAttributes()` cung cấp iterator cho các attributes.
- `start.getNamespaces()` cung cấp namespace declarations liên quan **chính tag đó**.
- `start.getNamespaceURI("o")` tìm URI theo prefix trong namespace context của start tag nếu được cung cấp.

**Namespace prefix không phải định danh nghiệp vụ ổn định**: `<o:order>` và `<x:order>` với cùng URI là cùng expanded name. Khi kiểm tra schema/route, so sánh **URI + local part**. `getAttributeByName(new QName("amount"))` chỉ tìm attribute **không namespace**; nếu attribute có prefix, phải tạo QName với URI đúng.

Lưu ý XML namespaces: một namespace mặc định trên element **không áp dụng tự động cho attributes không prefix**. Vì vậy, một attribute `id` không prefix thường có `QName` với namespace URI rỗng; không tìm nó bằng QName của element namespace.

### 5.3. Iterator của attributes và namespaces

```java
StartElement start = event.asStartElement();

Iterator<?> attributes = start.getAttributes();
while (attributes.hasNext()) {
    Attribute attribute = (Attribute) attributes.next();
    QName name = attribute.getName();
    String value = attribute.getValue();
}

Iterator<?> namespaces = start.getNamespaces();
while (namespaces.hasNext()) {
    Namespace ns = (Namespace) namespaces.next();
    String prefix = ns.getPrefix();
    String uri = ns.getNamespaceURI();
}
```

Đây là snippet minh họa với `event` chắc chắn là START_ELEMENT và imports `java.util.Iterator`, `StartElement`, `Attribute`, `Namespace`, `QName`. Trong ứng dụng thật nên dùng generic type do API cung cấp hoặc helper riêng để tránh cast mù. **Chỉ duyệt khi cần**: một tài liệu có nhiều attributes/ns declarations sẽ tạo nhiều objects; giới hạn số lượng/độ dài theo chính sách.

`Attribute.isSpecified()` phân biệt thuộc tính đã được chỉ rõ trong tài liệu và giá trị được khai báo mặc định trong DTD theo khả năng parser; nhưng khi DTD bị vô hiệu hóa để an toàn, đừng dựa vào DTD defaults. Không dùng `isSpecified()` để quyết định business security nếu input không đáng tin.

### 5.4. Characters, CDATA và whitespace

`Characters.getData()` trả text của **một event**. XML:

```xml
<message>Xin <![CDATA[chào]]> &amp; XML</message>
```

có thể sinh nhiều text events. Với `IS_COALESCING=true`, parser được yêu cầu gộp những text/CDATA gần nhau theo contract, nhưng implementation có thể buffer nhiều text hơn. Đừng dựa vào một event để nhận toàn bộ nội dung.

Các kiểm tra hữu ích:
- `event.isCharacters()` và `event.asCharacters().getData()`.
- `Characters.isCData()`: báo CDATA event theo parser representation.
- `Characters.isWhiteSpace()`: data toàn khoảng trắng theo định nghĩa XML.
- `Characters.isIgnorableWhiteSpace()`: whitespace được coi là ignorable trong một số ngữ cảnh xác định; không tự xóa whitespace nếu XML schema/mixed content cần bảo toàn.
- `Characters.getData().length()` đếm Java UTF-16 code units, **không phải bytes UTF-8 hay grapheme clusters**.

Với tài liệu text-heavy lớn, gọi `getData()` để chuyển sang một `Writer` rồi bỏ reference sớm. **Không tích lũy `StringBuilder` không giới hạn** chỉ để cuối cùng mới parse toàn bộ. Giới hạn field sizes/records và kiểm tra nguồn cấp dữ liệu có thể buffer nội bộ.

### 5.5. Event có thể giữ lại, nhưng không giữ tất cả

Khác với `XMLStreamReader` cursor state, `XMLEvent` là value object đại diện một event đã nhận, nên có thể chuyển cho handler hoặc lưu vài event cần thiết khi parser tiến tiếp. Tuy nhiên, giữ một `List<XMLEvent>` của hàng triệu events gần như mất lợi ích streaming. Đối với large XML:
- Chỉ lưu trạng thái của record hiện tại hoặc metadata nhỏ.
- Không giữ mọi event/text chunk.
- Khi consumer bất đồng bộ, chuyển **thông tin nghiệp vụ đã tách khỏi parser** qua một bounded queue.
- Nếu cần biến đổi XML nguyên vẹn, chuyển event trực tiếp sang `XMLEventWriter` trong phạm vi lifetime rõ ràng.

## 6. XMLInputFactory bảo mật khi tạo XMLEventReader

**Bảo mật áp dụng cho cả XMLEventReader lẫn XMLStreamReader** vì chúng đều do `XMLInputFactory` tạo. Input XML có thể đến từ đối tác, upload, database hoặc API không đáng tin. Nếu parser resolve external DTD/entities, có thể dẫn đến **XXE, SSRF, lộ file nội bộ** hoặc resource exhaustion.

Cấu hình an toàn được kiểm chứng trên JDK 17+:

```java
static XMLInputFactory secureFactory() {
    XMLInputFactory factory = XMLInputFactory.newDefaultFactory();

    factory.setProperty(XMLInputFactory.IS_NAMESPACE_AWARE, true);
    factory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
    factory.setProperty(
            XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
    factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");

    factory.setXMLResolver(
            (publicId, systemId, baseURI, namespace) -> {
                throw new XMLStreamException(
                        "External entity blocked");
            });

    return factory;
}
```

Đây là **method snippet** có imports `javax.xml.XMLConstants`, `javax.xml.stream.XMLInputFactory` và `XMLStreamException`; chương trình đầy đủ ở mục 9.

Ý nghĩa:
1. `IS_NAMESPACE_AWARE=true`: phân biệt namespace URI và local names.
2. `SUPPORT_DTD=false`: không xử lý DTD nếu ứng dụng không cần.
3. `IS_SUPPORTING_EXTERNAL_ENTITIES=false`: không resolve external parsed entities.
4. `ACCESS_EXTERNAL_DTD=""`: từ chối protocol truy cập DTD/external resource, nếu JAXP provider hỗ trợ setting.
5. `setXMLResolver`: resolver **ném exception**, không cho fallback mở file/network.
6. Trong vòng event loop, nếu `getEventType() == XMLStreamConstants.DTD`, ứng dụng có thể chủ động từ chối DOCTYPE theo policy.

**Đừng hiểu sai:** `SUPPORT_DTD=false` **không buộc mọi StAX provider ném exception cho mọi `<!DOCTYPE>`**. Có parser bỏ qua DTD và tiếp tục. Nếu quy định nghiệp vụ không cho phép DOCTYPE dưới bất kỳ hình thức nào, cần kiểm thử provider và dùng phương pháp reject phù hợp; không chỉ kiểm tra payload có external entity. Ví dụ có một payload external entity và chứng minh **payload đó** bị từ chối, không tuyên bố đã kiểm thử mọi dạng DOCTYPE.

StAX **không cung cấp `FEATURE_SECURE_PROCESSING` theo cơ chế đặt feature như DOM/SAX**. Sử dụng các properties StAX và giới hạn resource phù hợp. **Nếu một security setting bắt buộc không được hỗ trợ và `setProperty` ném `IllegalArgumentException`, phải fail closed**. Không catch lỗi hardening rồi parse theo cấu hình yếu hơn.

### 6.1. Giới hạn XML bombs và dữ liệu ác ý

Chống external entity **chưa đủ**: tài liệu có thể chứa hàng triệu phần tử lồng nhau, text cực lớn, attribute dài hoặc số lượng records vô hạn. Cần:
- Giới hạn **bytes đầu vào** trước/trong parse theo source (file/network/JDBC).
- Giới hạn độ sâu, số element, số attribute và số record.
- Giới hạn field length, digits, số phép tính và số objects giữ trong memory.
- Giới hạn thời gian parse, thread/concurrency, backpressure downstream.
- Kiểm thử XXE, SSRF, entity expansion, malformed input, XML sâu/rộng và cancellation.
- Nếu dùng validation/XSD/XSLT ở tầng khác, cấu hình security cho chính `SchemaFactory`/`TransformerFactory`; StAX settings không tự lan sang chúng.

Chương trình mục 9 giới hạn số order để minh họa, **chưa phải một XML security gateway hoàn chỉnh**. Với provider bên thứ ba, kiểm tra giới hạn parser và chính sách resolver thực tế sau mỗi upgrade.

### 6.2. DTD event và các entity-related events

`XMLEvent` có thể đại diện `DTD` hoặc `EntityReference` nếu provider cấu hình phát chúng. **Không dựa vào việc có/không có event để kết luận parser đã tiếp xúc network**. Chính sách phòng thủ phải được đặt **trước khi tạo reader**. Việc ném lỗi khi thấy DTD event là lớp kiểm tra thêm, không thay cho tắt resolver/external access.

Nếu ứng dụng cần dùng một DTD nội bộ tin cậy, yêu cầu an toàn phức tạp hơn: chỉ định nguồn allowlist, hạn chế entity expansion và kiểm tra provider; không bật `SUPPORT_DTD=true` đại trà cho XML tải từ người dùng.

## 7. Lọc sự kiện bằng EventFilter

`XMLInputFactory` cung cấp:

```java
XMLEventReader filtered =
        factory.createFilteredReader(original, eventFilter);
```

`EventFilter` là functional interface có method `boolean accept(XMLEvent event)`. Bộ lọc trả `true` cho event muốn người tiêu thụ nhìn thấy. Nó cho phép nhận một stream chỉ gồm những event phù hợp mà không phải viết `if` cho mọi loại ở consumer.

Ví dụ chỉ quan sát **START_ELEMENT** có tên order trong namespace mong muốn:

```java
EventFilter onlyOrders = event ->
        event.isStartElement()
        && "order".equals(
                event.asStartElement().getName().getLocalPart())
        && "urn:demo:orders".equals(
                event.asStartElement().getName().getNamespaceURI());

XMLEventReader filtered =
        factory.createFilteredReader(original, onlyOrders);

try {
    int count = 0;
    while (filtered.hasNext()) {
        filtered.nextEvent();
        count++;
    }
} finally {
    filtered.close();
}
```

Đây là **snippet**, `factory` đã harden và `original` là reader hợp lệ; quản lý nguồn/reader gốc riêng theo API/provider, như trong chương trình mẫu. Bộ lọc nêu trên đếm **START_ELEMENT order**, không dựng DOM và không giữ toàn bộ events.

### 7.1. Filter không phải validator hoặc sanitizer

Một lỗi rất thường gặp: lọc chỉ `START_ELEMENT` rồi gọi `getElementText()` trên filtered reader. Vì `EventFilter` đã ẩn `CHARACTERS` và `END_ELEMENT`, logic đọc text-only element có thể thiếu sự kiện cần thiết, tùy implementation. **Đừng sử dụng filtered reader như một parser XML đầy đủ sau khi đã bỏ các event quan trọng.**

- Nếu cần đọc các trường văn bản của một order, dùng unfiltered reader và state machine rõ.
- Nếu chỉ muốn đếm/routing start tags, filter có thể phù hợp.
- Nếu muốn chuyển một tài liệu XML qua writer, không lọc bừa `END_ELEMENT` hoặc namespace events kẻo output không well-formed.
- Filter chỉ ảnh hưởng events **được chuyển tới consumer**; parser gốc vẫn phải xử lý đủ XML input và áp dụng bảo mật từ factory. **Không phải cơ chế XXE prevention**.
- `EventFilter.accept` có thể được gọi bởi provider khi `peek`/`hasNext`/`nextEvent`; không đặt side effects không idempotent trong predicate. Viết bộ lọc thuần boolean càng tốt.

### 7.2. createFilteredReader có hai overload khác nhau

`XMLInputFactory.createFilteredReader(XMLEventReader, EventFilter)` trả `XMLEventReader`. Bản còn lại `createFilteredReader(XMLStreamReader, StreamFilter)` trả `XMLStreamReader`. Không dùng `StreamFilter` cho event reader hoặc cast hai loại reader; đó là hai cơ chế tương thích với hai mô hình StAX khác nhau.

## 8. XMLEventFactory và XMLEventWriter: tự tạo và chuyển tiếp event

Khi cần sinh XML hoặc xây dựng pipeline transform, sử dụng:
- `XMLEventFactory`: tạo các **đối tượng sự kiện** như `StartDocument`, `StartElement`, `Attribute`, `Characters`, `EndElement`, `EndDocument`.
- `XMLOutputFactory`: tạo output-side `XMLEventWriter`.
- `XMLEventWriter.add(event)`: ghi event vào XML output, thường có escaping phù hợp cho text được đưa qua `createCharacters()`.

Luồng:

```text
Ứng dụng / domain objects
           |
     XMLEventFactory
           |
  StartElement / Attribute
  Characters / EndElement
           |
     XMLEventWriter
           |
      Writer / OutputStream
           |
         XML text
```

Không nhầm **`XMLEventFactory`** với **`XMLInputFactory`**: một bên tạo event objects, bên kia tạo parser. `XMLEventWriter` cũng có `add(XMLEventReader)` để chuyển tiếp reader, nhưng khi input không đáng tin bạn vẫn phải parse bằng reader đã harden, và filter/transform cẩn thận để bảo toàn well-formedness.

### 8.1. Namespace declaration phải được ghi đúng

Nếu output dùng prefix `o`, cần có namespace declaration `xmlns:o="urn:demo:orders"` ở phạm vi phù hợp. Chỉ ghi `createStartElement("o", uri, "orders")` mà không khai báo prefix có thể tạo XML chưa hợp lệ về namespace tùy writer. Mẫu đầy đủ ở mục 10 thêm `events.createNamespace("o", NS)` ngay ở phần tử root.

### 8.2. XMLEventFactory.createCharacters() và escaping

`XMLEventFactory.createCharacters("Hà Nội & 🌏")` đại diện **text**, không phải markup. Khi ghi qua writer theo XML contract, dấu `&` phải được escape thành `&amp;` trong serialized XML. Khi đọc lại bằng parser, text content được khôi phục thành `Hà Nội & 🌏`.

**Đừng tự nối `"<order>" + untrustedInput + "</order>"`** nếu chưa encode XML text; dễ tạo XML malformed hoặc XML markup injection. Với những dữ liệu nhị phân, cần chiến lược biểu diễn khác (base64, attachment) thay vì đưa bytes bất kỳ vào `createCharacters()`.

### 8.3. Reader event → Writer event và tính toàn vẹn

Một pipeline `XMLEventWriter.add(XMLEventReader)` hoặc vòng `while (...) writer.add(reader.nextEvent())` có thể giữ **cấu trúc XML** nhưng không nhất thiết giữ nguyên **byte serialization**. Prefix, whitespace, attribute order, encoding declaration hoặc cách escape có thể thay đổi. Nếu dữ liệu có chữ ký số hoặc yêu cầu byte-exact, cần thiết kế canonicalization/integrity riêng.

## 9. Chương trình Java 17+ thứ nhất: XMLEventReaderDemo.java

Ví dụ **hoàn chỉnh, biên dịch/chạy được** với JDK 17+, không cần JDBC driver, database hoặc JAR ngoài. Nó:
1. Tạo một XML string có namespace, comment, hai order, tiền thập phân và tiếng Việt/emoji.
2. Cấu hình `XMLInputFactory` an toàn.
3. Dùng `peek()` xác nhận event `StartDocument` ở đầu.
4. Duyệt `XMLEventReader.nextEvent()`, phân loại `Comment`/`StartElement`/`DTD`.
5. Đọc `StartElement.getAttributeByName`, cộng `BigDecimal`.
6. Dùng `getElementText()` cho `customer` và `note` **nhỏ, text-only**.
7. Dùng `EventFilter` đếm riêng hai START_ELEMENT order.
8. Kiểm thử XML có external entity và xác nhận parser từ chối.
9. Đóng mọi event reader và Reader trong `finally`/try-with-resources.

### 9.1. Mã nguồn đầy đủ

Tạo file **`XMLEventReaderDemo.java`**:

```java
import java.io.Reader;
import java.io.StringReader;
import java.math.BigDecimal;
import javax.xml.XMLConstants;
import javax.xml.namespace.QName;
import javax.xml.stream.EventFilter;
import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLStreamConstants;
import javax.xml.stream.XMLStreamException;
import javax.xml.stream.XMLEventReader;
import javax.xml.stream.events.Attribute;
import javax.xml.stream.events.StartElement;
import javax.xml.stream.events.XMLEvent;

public final class XMLEventReaderDemo {
    private static final String NS = "urn:demo:orders";

    record Summary(int orders, BigDecimal total,
                   String firstCustomer, String firstNote,
                   int comments) {}

    static XMLInputFactory secureFactory() {
        XMLInputFactory factory = XMLInputFactory.newDefaultFactory();
        factory.setProperty(XMLInputFactory.IS_NAMESPACE_AWARE, true);
        factory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
        factory.setProperty(
                XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setXMLResolver(
                (publicId, systemId, baseURI, namespace) -> {
                    throw new XMLStreamException("External entity blocked");
                });
        return factory;
    }

    static Summary parse(XMLInputFactory factory, String input)
            throws Exception {
        try (Reader source = new StringReader(input)) {
            XMLEventReader events = factory.createXMLEventReader(source);
            try {
                boolean atDocumentStart =
                        events.peek() != null && events.peek().isStartDocument();
                System.out.println("startDocument=" + atDocumentStart);

                int orders = 0;
                BigDecimal total = BigDecimal.ZERO;
                String firstCustomer = "";
                String firstNote = "";
                int comments = 0;

                while (events.hasNext()) {
                    XMLEvent event = events.nextEvent();
                    if (event.getEventType() == XMLStreamConstants.DTD) {
                        throw new XMLStreamException("DOCTYPE not allowed");
                    }
                    if (event.getEventType() == XMLStreamConstants.COMMENT) {
                        comments++;
                        continue;
                    }
                    if (!event.isStartElement()) {
                        continue;
                    }
                    StartElement start = event.asStartElement();
                    QName name = start.getName();
                    if (!NS.equals(name.getNamespaceURI())) {
                        throw new XMLStreamException("Unexpected namespace");
                    }
                    if ("order".equals(name.getLocalPart())) {
                        if (++orders > 1000) {
                            throw new XMLStreamException("Too many orders");
                        }
                        Attribute amount =
                                start.getAttributeByName(new QName("amount"));
                        if (amount == null) {
                            throw new XMLStreamException("Missing amount");
                        }
                        total = total.add(new BigDecimal(amount.getValue()));
                    } else if ("customer".equals(name.getLocalPart())) {
                        String customer = events.getElementText();
                        if (orders == 1) firstCustomer = customer;
                    } else if ("note".equals(name.getLocalPart())) {
                        String note = events.getElementText();
                        if (orders == 1) firstNote = note;
                    }
                }
                return new Summary(
                        orders, total, firstCustomer, firstNote, comments);
            } finally {
                events.close();
            }
        }
    }

    static int countFilteredOrders(XMLInputFactory factory, String input)
            throws Exception {
        try (Reader source = new StringReader(input)) {
            XMLEventReader original = factory.createXMLEventReader(source);
            EventFilter onlyOrders = event ->
                    event.isStartElement()
                    && "order".equals(
                            event.asStartElement().getName().getLocalPart())
                    && NS.equals(
                            event.asStartElement().getName().getNamespaceURI());
            XMLEventReader filtered =
                    factory.createFilteredReader(original, onlyOrders);
            try {
                int count = 0;
                while (filtered.hasNext()) {
                    filtered.nextEvent();
                    count++;
                }
                return count;
            } finally {
                filtered.close();
                original.close();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        String xml = """
                <?xml version="1.0" encoding="UTF-8"?>
                <o:orders xmlns:o="urn:demo:orders">
                  <!-- Bản ghi hợp lệ -->
                  <o:order id="A-01" amount="12.50">
                    <o:customer>Hà Nội</o:customer>
                    <o:note>Xin chào &amp; 🌏</o:note>
                  </o:order>
                  <o:order id="A-02" amount="7.25">
                    <o:customer>Đà Nẵng</o:customer>
                    <o:note>Đã nhận</o:note>
                  </o:order>
                </o:orders>
                """;

        XMLInputFactory factory = secureFactory();
        Summary result = parse(factory, xml);
        int filteredOrders = countFilteredOrders(factory, xml);

        String malicious = """
                <!DOCTYPE o:orders [
                  <!ENTITY secret SYSTEM "file:///not-for-reading">
                ]>
                <o:orders xmlns:o="urn:demo:orders">&secret;</o:orders>
                """;
        boolean externalEntityRejected = false;
        try (Reader source = new StringReader(malicious)) {
            XMLEventReader events = factory.createXMLEventReader(source);
            try {
                while (events.hasNext()) {
                    XMLEvent event = events.nextEvent();
                    if (event.getEventType() == XMLStreamConstants.DTD) {
                        throw new XMLStreamException("DOCTYPE not allowed");
                    }
                }
            } catch (XMLStreamException expected) {
                externalEntityRejected = true;
            } finally {
                events.close();
            }
        }

        System.out.println("orders=" + result.orders());
        System.out.println("total=" + result.total());
        System.out.println("customer=" + result.firstCustomer());
        System.out.println("note=" + result.firstNote());
        System.out.println("comments=" + result.comments());
        System.out.println("filteredOrders=" + filteredOrders);
        System.out.println("externalEntityRejected=" + externalEntityRejected);
    }
}
```

### 9.2. Biên dịch và chạy

```bash
javac -encoding UTF-8 XMLEventReaderDemo.java
java XMLEventReaderDemo
```

Java `record` và text blocks đã là tính năng ổn định từ trước Java 17; mã chạy với JDK 17+ mà không cần `--enable-preview`. File nguồn lưu bằng UTF-8 để tiếng Việt/emoji hiển thị đúng.

**Stdout chính xác đã biên dịch và chạy kiểm chứng trên JDK:**

```text
startDocument=true
orders=2
total=19.75
customer=Hà Nội
note=Xin chào & 🌏
comments=1
filteredOrders=2
externalEntityRejected=true
```

**Giải thích:**
- `startDocument=true`: `peek()` nhìn trước `StartDocument` mà không tiêu thụ.
- `orders=2`: đọc hai StartElement với QName thuộc namespace `urn:demo:orders`.
- `total=19.75`: cộng `12.50` và `7.25` bằng `BigDecimal`, không mất độ chính xác thập phân do `double`.
- `customer=Hà Nội`: text có dấu tiếng Việt được đọc đúng.
- `note=Xin chào & 🌏`: `&amp;` trong XML serialization trở thành `&` trong nội dung, emoji được giữ nguyên.
- `comments=1`: phân loại một COMMENT event.
- `filteredOrders=2`: EventFilter chỉ cho qua hai START_ELEMENT order, không cần giữ danh sách event.
- `externalEntityRejected=true`: payload **có external entity được tham chiếu** bị từ chối trên parser đã cấu hình; không đọc file cục bộ được nhắc tới.

**Giới hạn demo:** code giả định XML theo một schema nhỏ và một namespace duy nhất; nó **chưa xác minh cấu trúc cha-con đủ chặt** cho input sản phẩm. Nếu có một `<order>` nằm sai vị trí, parser vẫn đếm. Production cần kiểm tra root, nesting depth, namespace, attribute value length/format, giá trị âm, XML size, max digits, entity/security policy và yêu cầu nghiệp vụ. Hàm `getElementText()` chỉ dùng với các field ngắn; không áp dụng cho body có kích cỡ không giới hạn.

**Về bảo mật test:** mục tiêu chỉ là xác minh một XML có DTD/external entity không được tiếp nhận. Không kết luận từ một test rằng provider sẽ ném lỗi với mọi DOCTYPE không có entity tham chiếu. Nếu policy cần cấm mọi DOCTYPE, viết thêm test về DOCTYPE đơn giản và enforce cách reject được provider hỗ trợ.

## 10. Chương trình Java 17+ thứ hai: XMLEventFactory + XMLEventWriter

Với event model, Java có thể **tạo từng XMLEvent**, ghi chúng thành XML rồi đọc lại để xác nhận nội dung. Chương trình thứ hai tập trung vào:
- `XMLEventFactory.newFactory()` tạo một event factory.
- `XMLOutputFactory.newDefaultFactory()` tạo XML event writer.
- `writer.add(...)` để ghi StartDocument, StartElement, Namespace, Attribute, Characters, EndElement, EndDocument.
- `createCharacters("Hà Nội & 🌏")` để writer escape ampersand đúng XML syntax.
- Đọc lại XML bằng `XMLEventReader` và `getElementText()`.
- Kiểm tra namespace URI, root và XML text sau khi parse.

### 10.1. File XMLEventWriterDemo.java

```java
import java.io.StringReader;
import java.io.StringWriter;
import javax.xml.XMLConstants;
import javax.xml.namespace.QName;
import javax.xml.stream.XMLEventFactory;
import javax.xml.stream.XMLEventReader;
import javax.xml.stream.XMLEventWriter;
import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLOutputFactory;
import javax.xml.stream.XMLStreamException;
import javax.xml.stream.events.StartElement;
import javax.xml.stream.events.XMLEvent;

public final class XMLEventWriterDemo {
    private static final String NS = "urn:demo:orders";

    static String buildXml() throws Exception {
        StringWriter output = new StringWriter();
        XMLEventFactory events = XMLEventFactory.newFactory();
        XMLOutputFactory outputFactory =
                XMLOutputFactory.newDefaultFactory();
        XMLEventWriter writer =
                outputFactory.createXMLEventWriter(output);
        try {
            writer.add(events.createStartDocument());
            writer.add(events.createStartElement("o", NS, "orders"));
            writer.add(events.createNamespace("o", NS));
            writer.add(events.createStartElement("o", NS, "order"));
            writer.add(events.createAttribute("amount", "12.50"));
            writer.add(events.createCharacters("Hà Nội & 🌏"));
            writer.add(events.createEndElement("o", NS, "order"));
            writer.add(events.createEndElement("o", NS, "orders"));
            writer.add(events.createEndDocument());
            writer.flush();
        } finally {
            writer.close();
        }
        return output.toString();
    }

    public static void main(String[] args) throws Exception {
        String xml = buildXml();
        XMLInputFactory input = XMLInputFactory.newDefaultFactory();
        input.setProperty(XMLInputFactory.SUPPORT_DTD, false);
        input.setProperty(
                XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
        input.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        input.setXMLResolver((publicId, systemId, baseURI, namespace) -> {
            throw new XMLStreamException("External entity blocked");
        });
        String root = "";
        String body = "";
        String namespace = "";
        XMLEventReader reader =
                input.createXMLEventReader(new StringReader(xml));
        try {
            while (reader.hasNext()) {
                XMLEvent event = reader.nextEvent();
                if (event.isStartElement()) {
                    StartElement start = event.asStartElement();
                    QName name = start.getName();
                    if ("orders".equals(name.getLocalPart())) {
                        root = name.getLocalPart();
                        namespace = name.getNamespaceURI();
                    }
                    if ("order".equals(name.getLocalPart())) {
                        body = reader.getElementText();
                    }
                }
            }
        } finally {
            reader.close();
        }
        System.out.println("root=" + root);
        System.out.println("namespace=" + namespace);
        System.out.println("orderText=" + body);
        System.out.println("escapedAmpersand=" + xml.contains("&amp;"));
    }
}
```

**Lưu ý:** `StringWriter` và `StringReader` không giữ OS handle nhưng dùng bộ nhớ, phù hợp demo nhỏ. Với XML lớn, mở `Writer`/`OutputStream` từ file/network và đóng nguồn riêng bằng try-with-resources. `XMLEventWriter.close()` **không bảo đảm đóng underlying Writer/OutputStream** theo API; cần quản lý nguồn/đích bên ngoài theo contract của nó.

### 10.2. Biên dịch, chạy và stdout

```bash
javac -encoding UTF-8 XMLEventWriterDemo.java
java XMLEventWriterDemo
```

**Stdout chính xác đã chạy kiểm chứng trên JDK:**

```text
root=orders
namespace=urn:demo:orders
orderText=Hà Nội & 🌏
escapedAmpersand=true
```

**Giải thích:**
1. `root=orders` và `namespace=urn:demo:orders`: event writer đã ghi declaration namespace hợp lệ.
2. `orderText=Hà Nội & 🌏`: reader đọc lại Unicode và text đã được XML-escape khi serialize.
3. `escapedAmpersand=true`: output XML chứa `&amp;` thay cho dấu `&` thô.
4. `XMLEventFactory` tạo events; `XMLEventWriter` serialize; `XMLEventReader` parse ngược để kiểm tra semantic integrity.

**Mở rộng:** Nếu mục tiêu là xuất XML lớn, thay `StringWriter` bằng `Files.newBufferedWriter(path, UTF_8)` và đưa dữ liệu từng record vào writer. Dù input/output có thể được xử lý theo luồng, application vẫn cần giới hạn số records, độ dài text, cancellation và backpressure.

## 11. Kiến trúc xử lý sự kiện trong ứng dụng thực

### 11.1. Duyệt record theo state machine

Khi XML có nhiều record, bạn có thể xử lý một lượt mà không tạo DOM:
1. Bắt `StartElement` `order` ở namespace hợp lệ.
2. Đọc attributes `id`/`amount`.
3. Bắt đầu một object domain nhỏ hoặc trạng thái cho record hiện tại.
4. Nhận text/nested elements, áp các giới hạn field.
5. Khi nhận `EndElement` `order` tương ứng, validate record rồi gửi tới sink.
6. Giải phóng trạng thái record trước khi đọc record tiếp theo.

Nếu XML cho phép nested elements cùng tên, **không chỉ dùng một boolean `insideOrder`**. Cần quản lý depth/stack và QName để xác định điểm kết thúc chính xác, tránh đóng record quá sớm hoặc nhận tag không thuộc parent mong đợi.

Sơ đồ:

```text
StartElement(orders)
    |
StartElement(order) -> đọc attributes
    |
  StartElement(customer)
    |
    Characters chunks -> tích lũy có giới hạn
    |
  EndElement(customer)
    |
  StartElement(note)
    |
    Characters chunks -> xử lý/ghi output
    |
  EndElement(note)
    |
EndElement(order) -> validate + emit record
    |
[next order] ...
    |
EndElement(orders)
```

Với field lớn, **không gọi `getElementText()`**. Thay vào đó, khi đang ở vùng text tương ứng, xử lý `event.asCharacters().getData()` theo chunks. Không giữ `List<XMLEvent>` toàn bộ tài liệu rồi mới phân tích.

### 11.2. EventHandler riêng thay vì một vòng lặp khổng lồ

Một kiến trúc hữu ích:
- **XML layer:** tạo factory, hardening, đóng reader/source.
- **Parser state layer:** chuyển events hợp lệ thành domain objects, kiểm soát QName/depth.
- **Validation layer:** kiểm tra field sizes, types, business rules.
- **Sink layer:** ghi database, message queue, file hoặc batch consumer.
- **Observability layer:** đếm records/errors, đo time, không log payload nhạy cảm.

Nếu sink chậm, dùng bounded queue/backpressure để tránh parser đẩy các records vào RAM vô hạn. Trong asynchronous processing, không chuyển `XMLEventReader` cho thread khác rồi đóng nguồn ở thread ban đầu; parser và nguồn phải sống trong một ownership/lifetime rõ ràng. XMLEvent objects tuy có thể lưu nhưng cũng chứa text/metadata, không miễn phí.

### 11.3. Error policy: malformed, policy reject và lỗi sink

Phân biệt:
- **XMLStreamException**: malformed XML, parser error, DTD policy reject.
- **IllegalArgumentException**: cấu hình factory property không hỗ trợ/giá trị không chấp nhận.
- **NumberFormatException**: attribute không phải số, quá lớn.
- **IOException**: nguồn/đích đọc ghi lỗi (tùy API wrapper).
- **SQLException** hoặc lỗi downstream: lưu dữ liệu từ parser vào database thất bại.

Không retry cùng payload XML malformed hoặc XML có entity bị security policy từ chối. Với lỗi I/O tạm thời, muốn retry cần **mở một nguồn mới**; event reader cũ đã đọc đến đâu không tự rewind. Nếu downstream đã nhận một phần records, cần idempotency/checkpoint/rollback policy để tránh ghi trùng.

## 12. XML namespaces và validation thực tế

### 12.1. QName, local part, prefix và URI

`javax.xml.namespace.QName` có ba phần phổ biến: `namespaceURI`, `localPart` và `prefix`. Dùng `getNamespaceURI()` và `getLocalPart()` cho business routing; prefix chỉ là cách viết trên tài liệu XML.

Ví dụ hai documents sau có expanded names tương đương:

```xml
<a:order xmlns:a="urn:demo:orders" amount="12.50"/>
```

```xml
<b:order xmlns:b="urn:demo:orders" amount="12.50"/>
```

Nếu code so sánh string literal `"a:order"`, nó có thể fail với `"b:order"` dù namespace giống nhau. Dùng QName để tránh lỗi. `StartElement.getAttributeByName` cũng cần QName đúng namespace của attribute.

### 12.2. StAX là parser, không phải XSD validator mặc định

`XMLEventReader` parse **well-formed XML** theo parser/config. Nó không tự bảo đảm:
- Element root/child đúng thứ tự theo schema doanh nghiệp.
- Attribute `amount` luôn có, là số hợp lệ, không vượt precision.
- Dữ liệu text tuân thủ length/normalization policy.
- XML đạt XSD validation.
- Nội dung không chứa thông tin nhạy cảm hoặc dữ liệu độc hại ở cấp domain.

Nếu cần XSD, dùng `SchemaFactory`/`Validator` được harden riêng, khóa external schema/DTD access và chỉ dùng schema tin cậy. StAX security settings **không tự áp dụng** lên một validator hay transformer khác. Validate schema và xử lý business có thể cần hai lượt đọc hoặc streaming validator phù hợp provider; thiết kế kích cỡ và quyền truy cập dữ liệu cẩn thận.

## 13. Bảo toàn dữ liệu, encoding và event locations

### 13.1. Input encoding

`Reader` đã decode; `InputStream` là bytes. Nếu XML có XML declaration `encoding="UTF-8"` nhưng application tự decode bằng sai charset trước khi tạo `Reader`, StAX không thể sửa toàn bộ lỗi đã xảy ra. Dùng `Files.newBufferedReader(path, StandardCharsets.UTF_8)` khi biết chắc file UTF-8, hoặc cung cấp `InputStream` để parser nhận diện XML encoding theo specification.

Với output từ event writer, tránh khai `UTF-8` trong XML declaration nhưng ghi ra byte stream bằng charset khác. Khi ký số XML hoặc so sánh tài liệu, xác định liệu sản phẩm cần **cùng ngữ nghĩa XML** hay **byte-for-byte equality**: parser/writer có thể thay escaping, attribute order, namespace prefixes, whitespace hoặc encoding declaration.

### 13.2. Event getLocation()

`XMLEvent.getLocation()` trả `Location` hỗ trợ line/column/public ID/system ID khi provider có dữ liệu. `XMLStreamException.getLocation()` giúp chỉ ra vị trí lỗi parser, nhưng line/column có thể unknown hoặc best effort; không tự suy số byte chính xác từ line/column.

Ví dụ snippet:

```java
try {
    while (events.hasNext()) {
        XMLEvent event = events.nextEvent();
        Location location = event.getLocation();
        if (location != null
                && event.isStartElement()) {
            System.out.println(
                    "line=" + location.getLineNumber());
        }
    }
} catch (XMLStreamException e) {
    Location error = e.getLocation();
    if (error != null) {
        System.err.println(
                "invalidXmlAtLine=" + error.getLineNumber());
    }
    throw e;
}
```

Đây là **snippet**, cần import `javax.xml.stream.Location`, `XMLEventReader`, `XMLEvent`, `XMLStreamException`, và method `throws XMLStreamException`. Không có stdout cố định vì line/column thay đổi theo tài liệu và provider. **Đừng log toàn bộ XML payload hoặc URL nguồn có secret** chỉ để debug line location.

### 13.3. Unicode và phân tích text

`Characters.getData()` là `String` Java. `String.length()` đếm **UTF-16 code units**. Emoji `🌏` thường chiếm hai `char`, trong khi số code points của nó là một. Nếu áp giới hạn field tính theo bytes, characters, code points hoặc grapheme clusters, phải xác định rõ đơn vị theo nghiệp vụ; đừng dùng byte size để thay cho số code points.

Trong ví dụ, `"Xin chào &amp; 🌏"` ở XML được parser chuyển thành `"Xin chào & 🌏"`. Đây là XML unescaping bình thường, **không có nghĩa mất dữ liệu**. Nếu luồng XML được serialize lại, các biểu diễn khác nhau của cùng text có thể tương đương.

## 14. Hiệu năng và bộ nhớ của event-object model

Một `XMLEventReader` tạo/trả các event objects. Nó hữu ích khi:
- Cần đưa sự kiện tới pipeline xử lý nhiều bước.
- Cần gọi `peek()` để định tuyến sự kiện kế tiếp.
- Cần một predicate `EventFilter` để nhận subset events.
- Cần chuyển một luồng XML sang `XMLEventWriter`.

Nhưng có đánh đổi:
- Nhiều events tạo allocation và tăng GC so với cursor style trong một số provider.
- `getElementText()` có thể gom cả nội dung phần tử thành `String` lớn.
- `XMLEvent` có thể giữ references tới strings/attributes/ns; cache quá nhiều events làm tăng heap.
- `createFilteredReader` phải tiêu thụ events từ parser gốc để bỏ qua; filter không thay đổi kích thước input hay bảo đảm mọi XML đã an toàn.
- Nếu input đến từ JDBC/HTTP, driver/client có thể buffer trước khi đưa Reader.
- Một XML element text cực lớn hoặc namespace maps có thể tạo memory spikes dù không có DOM.

### 14.1. Benchmark có ý nghĩa

Đo trên dữ liệu và provider thật:
1. **Peak heap / allocation rate / GC pause** giữa `XMLStreamReader` và `XMLEventReader`.
2. **Events/s** và **records/s**, latency tổng và time-to-first-record.
3. Kích thước input, độ sâu, số attributes, Unicode và text lengths.
4. Số objects/records application giữ.
5. Network/database buffering, pool occupancy nếu nguồn là SQLXML.
6. XML validation/hardening overhead và tác động của filter.

Nếu cần rất ít thông tin ở mỗi event, cursor API thường đơn giản hơn về allocation. Nếu pipeline yêu cầu event objects, event reader giúp giảm boilerplate khi chuyển tiếp/transform. **Chọn theo correctness và benchmark, không theo tên “nâng cao”**.

### 14.2. Thread safety và ownership

`XMLEventReader` giữ trạng thái tuần tự; không chia sẻ một reader giữa các threads/request. `XMLInputFactory` mutable và threading contract tùy provider; đừng thay đổi properties của cùng một factory khi đang tạo parsers song song mà chưa kiểm chứng. `XMLEventFactory`/`XMLEventWriter` cũng cần xem docs provider nếu muốn share.

Một pattern rõ ràng là **mỗi parsing operation sở hữu source + event reader**, đóng chúng trong cùng scope; các giá trị domain đã parse có thể được chuyển downstream qua interfaces độc lập và bounded queues.

## 15. Các lỗi phổ biến khi sử dụng XMLEventReader

| Vấn đề | Vì sao xảy ra | Cách sửa |
| --- | --- | --- |
| `nextEvent()` ném `XMLStreamException` | Malformed XML, input/encoding lỗi hoặc security policy reject. | Kiểm tra input, parser location, hardening, không tắt bảo mật để “chạy”. |
| `nextEvent()` gặp EOF nhưng vẫn gọi tiếp | Không check `hasNext()`. | Dùng vòng `while (reader.hasNext())`. |
| `peek()` trả null rồi cast | Không còn event. | Kiểm tra null trước. |
| Gọi `asStartElement()` trên Characters | Type không phù hợp. | `event.isStartElement()` trước khi cast. |
| `getAttributeByName` trả null | Attribute vắng hoặc QName namespace sai. | Kiểm tra null, namespace, schema. |
| `getElementText()` ném lỗi | Không ở START_ELEMENT hoặc có nested child. | Chỉ dùng với text-only element nhỏ; nếu phức tạp dùng event loop. |
| `nextTag()` ném lỗi | Non-whitespace text/mixed content. | Dùng `nextEvent()` đầy đủ. |
| Filter chỉ giữ START_ELEMENT rồi parse text | CHARACTERS/END_ELEMENT đã bị ẩn. | Không dùng filtered reader như cây XML đầy đủ. |
| Parser vẫn gọi external URL | Factory chưa tắt DTD/entities/resolver. | Harden factory trước tạo reader, fail closed. |
| Thấy SUPPORT_DTD=false nên khẳng định DOCTYPE luôn throw | Có provider bỏ qua DTD. | Enforce/test DOCTYPE reject policy riêng. |
| `XMLEventReader.close()` xong file còn bị giữ | Close parser không đóng underlying input source. | Đóng Reader/InputStream riêng. |
| Toàn bộ event stream bị giữ trong `List` | Mất streaming và có thể OOM. | Chỉ giữ record/state nhỏ, dùng bounded sink. |
| Mất dữ liệu tiếng Việt/emoji | Decode sai charset hoặc xử lý code units sai. | UTF-8 explicit ở byte boundary, round-trip test. |
| So sánh prefix `o` cứng | XML có prefix khác cùng namespace. | QName URI + local part. |
| `createCharacters` ghi XML sai do tự nối markup | Input chưa escape và writer bị dùng sai. | EventFactory + EventWriter đúng API. |
| Không ghi namespace declarations | XML output có prefix chưa bind. | Thêm `createNamespace(prefix, URI)` ở scope phù hợp. |
| Test đếm orders thành công nhưng XML không đúng schema | Demo không validate cấu trúc đầy đủ. | Kiểm tra root/depth/schema/business constraints. |
| XSD validation tải network | Validator/schema factory chưa harden. | Khóa external schema/DTD, allowlist trusted schema. |

## 16. Checklist kiểm thử trước production

**Test 1 — Loại sự kiện.** XML chứa START/END_DOCUMENT, START/END_ELEMENT, COMMENT, CHARACTERS, CDATA, PI; xác minh phân loại đúng theo provider.

**Test 2 — Namespace.** Thay prefix `o` bằng prefix `x` vẫn giữ URI; parser không thay đổi kết quả nghiệp vụ.

**Test 3 — Attribute.** Thiếu `amount`, giá trị không phải số, số quá dài, thuộc tính thuộc namespace khác; code phải báo lỗi có kiểm soát.

**Test 4 — Unicode.** Tiếng Việt, CJK, emoji, XML escaping; text sau parse vẫn đúng với expectation.

**Test 5 — Peek.** Hai lần `peek()` không tiêu thụ event; `nextEvent()` sau đó nhận event đã xem.

**Test 6 — getElementText.** Trường hợp text-only hoạt động; nested child/mixed content gây lỗi theo contract; dữ liệu lớn không được gom vô giới hạn.

**Test 7 — nextTag.** Chạy trên whitespace-only giữa tags và non-whitespace text; tránh mất dữ liệu.

**Test 8 — Filter.** Đếm START_ELEMENT được lọc, không áp `getElementText()` trên stream đã bỏ CHARACTERS/END_ELEMENT.

**Test 9 — Writer.** `XMLEventFactory`/`XMLEventWriter` tạo XML có namespace/escaping, parse ngược và đối chiếu nội dung.

**Test 10 — External entities.** DTD chứa external file/HTTP reference; xác nhận không có file/network access và payload bị từ chối theo policy.

**Test 11 — DOCTYPE độc lập.** Nếu business yêu cầu cấm mọi DOCTYPE, test cả DOCTYPE không có entity được tham chiếu; kiểm tra provider reject behavior.

**Test 12 — Unsupported security setting.** Giả lập/thay provider không chấp nhận `ACCESS_EXTERNAL_DTD` hoặc property bắt buộc; application **fail closed**.

**Test 13 — XML bombs.** Tài liệu rất sâu/rộng, text lớn, nhiều attributes/records; kiểm tra limits và bounded memory.

**Test 14 — I/O failure.** Nguồn đang đọc bị đóng, timeout hoặc bị hủy; bảo đảm close reader/source, không retry trên nguồn đã tiêu thụ.

**Test 15 — Provider upgrades.** Nâng JDK hoặc thay StAX implementation; chạy lại security và event-model tests.

**Test 16 — Integration.** Đọc từ SQLXML, HTTP, file lớn; xác nhận life cycle connection/transaction/source, metric GC/network/latency, không log raw payload nhạy cảm.

## 17. Bài tập nâng cao

1. **Phân tích namespace:** với XML dùng hai namespace có cùng local name `order`, chỉ đếm element thuộc `urn:demo:orders`.
2. **Đọc attribute:** thêm `currency` cho order, validate allowlist `VND`/`USD` và dùng `BigDecimal` để tính số tiền mà không dùng `double`.
3. **Thống kê an toàn:** thay `getElementText()` bằng xử lý `Characters` events theo chunks, giới hạn text tối đa 1.024 Java `char` units cho customer.
4. **EventFilter:** tạo filter trả cả START_ELEMENT và END_ELEMENT cho một namespace. Giải thích vì sao chỉ giữ start/end vẫn chưa đủ để tái tạo dữ liệu text.
5. **Streaming transform:** dùng `XMLEventReader` và `XMLEventWriter` để bỏ comment khỏi XML mà giữ cấu trúc/tên/namespace; có test document well-formed.
6. **Security test:** thêm DOCTYPE không tham chiếu entity, kiểm tra provider có ném lỗi hay chỉ bỏ qua; nếu policy cấm, điều chỉnh cơ chế reject đã được kiểm chứng.
7. **Location diagnostics:** lấy `XMLEvent.getLocation()` khi thiếu required attribute; chỉ log line/column, không log raw XML với PII.
8. **JDBC source:** đọc `SQLXML.getCharacterStream()` từ cơ sở dữ liệu test (nếu driver hỗ trợ) và đưa vào `createXMLEventReader`; quản lý SQLXML `free()`/transaction.
9. **Throughput test:** so sánh event/cursor API trên file đủ lớn, đo heap/GC/events/s, không kết luận hiệu năng từ một XML nhỏ.

## 18. Câu hỏi ôn tập

**Câu 1. XMLEventReader khác XMLStreamReader ở điểm cốt lõi nào?**

`XMLEventReader` trả các `XMLEvent` objects qua `nextEvent()`, còn `XMLStreamReader` di chuyển cursor bằng `next()` rồi đọc dữ liệu từ trạng thái hiện tại.

**Câu 2. `peek()` có tiêu thụ event không?**

Không. Nó nhìn sự kiện kế tiếp mà không di chuyển iterator. Trả null nếu không còn sự kiện theo contract.

**Câu 3. `getElementText()` dùng được cho mọi START_ELEMENT không?**

Không. Nó dành cho element **text-only** và nội dung cần có kích thước hợp lý; nested child có thể gây `XMLStreamException`, text quá lớn gây memory pressure.

**Câu 4. `nextTag()` có thể bỏ qua mọi text giữa các elements không?**

Không. Nó chỉ bỏ qua những sự kiện không quan trọng theo contract; gặp non-whitespace text/mixed content có thể ném exception.

**Câu 5. Làm sao đọc tên và attribute của StartElement?**

Dùng `event.asStartElement().getName()` để nhận `QName`, `getAttributeByName(QName)` cho thuộc tính; kiểm tra null và namespace đúng.

**Câu 6. `Characters.getData()` chắc chứa toàn bộ text của một element không?**

Không. Parser có thể chia text thành nhiều Characters/CDATA events; muốn text lớn phải xử lý nhiều chunks.

**Câu 7. EventFilter có tự giúp chống XXE không?**

Không. Bộ lọc chỉ chọn events phía consumer nhìn thấy. Cần cấu hình `XMLInputFactory` để chặn external DTD/entities **trước khi parse**.

**Câu 8. `SUPPORT_DTD=false` có chứng minh mọi DOCTYPE sẽ bị reject?**

Không. Có provider không xử lý DTD nhưng vẫn chấp nhận DOCTYPE declaration. Cần test/enforce policy theo yêu cầu.

**Câu 9. Có thể đóng XMLEventReader mà không đóng InputStream không?**

Không nên. Javadoc `XMLEventReader.close()` không tự đóng underlying input source; dùng try-with-resources cho source riêng.

**Câu 10. XMLEventFactory và XMLInputFactory khác nhau thế nào?**

`XMLEventFactory` tạo đối tượng sự kiện để write/transform. `XMLInputFactory` tạo parser/reader đọc XML.

**Câu 11. Vì sao writer cần createNamespace?**

Khi output dùng prefix như `o:orders`, prefix phải được ràng buộc với namespace URI bằng declaration `xmlns:o` ở scope hợp lệ.

**Câu 12. Giữ lại tất cả XMLEvent có còn là streaming tiết kiệm RAM không?**

Không. Event objects chứa text/metadata và vẫn tiêu thụ heap. Giữ vừa đủ state, dùng giới hạn/bounded sinks.

**Câu 13. Java 17 có cần thêm StAX parser legacy không?**

Không. `javax.xml.stream` trong module chuẩn `java.xml`. Chỉ dùng provider bên thứ ba khi có lý do và đã audit về security/compatibility.

**Câu 14. Vì sao dùng BigDecimal cho amount?**

Vì số tiền thập phân cần tính chính xác; cộng qua `double` có thể sai số. Còn phải kiểm soát precision, scale và giới hạn input ở production.

## 19. Checklist ứng dụng hiện đại

- Chọn `XMLInputFactory.newDefaultFactory()` (JDK provider) hoặc `newFactory()` có kiểm soát.
- Đặt `IS_NAMESPACE_AWARE=true` và các chính sách DTD/external entities **trước** khi tạo event reader.
- Fail closed nếu bắt buộc security setting mà parser/provider không hỗ trợ.
- Ưu tiên `nextEvent()`, `peek()`, `hasNext()` cho event-object model.
- Dùng `XMLEvent` predicates/getEventType trước khi `asStartElement()`/`asCharacters()`.
- Đọc `QName` qua namespace URI + local name, không hardcode prefix.
- Dùng `getElementText()` chỉ với text-only, bounded fields; không dùng trên body rất lớn.
- Dùng `nextTag()` chỉ khi thật sự xử lý element-only content.
- Xử lý Characters/CDATA có thể chia nhiều events; đừng giả định mỗi element chỉ có một.
- Tách `XMLEventReader`, `EventFilter`, `XMLEventWriter` theo đúng contract; filter không phải validator.
- Đóng event reader **và** Reader/InputStream; không share stateful reader qua threads.
- Với JDBC/HTTP, giữ nguồn/connection/response mở tới khi parse xong; dọn resources đúng thứ tự.
- Giới hạn bytes, depth, attributes, record count, text length, processing time và concurrency.
- Kiểm thử XXE/SSRF/DTD, Unicode, namespaces, malformed input, provider upgrades.
- Không log payload XML chứa PII/secrets, URL có credential hay dynamic input tùy ý.
- Dùng API Java 17+ đang hỗ trợ; không cần thư viện XML legacy cho StAX cơ bản/nâng cao.

## 20. Tài liệu tham khảo chính thức

- [Java SE 17 — XMLEventReader](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/stream/XMLEventReader.html): `nextEvent`, `peek`, `getElementText`, `nextTag`, `close` và contract event reader.
- [Java SE 17 — XMLEvent](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/stream/events/XMLEvent.html): predicates, `getEventType`, `asStartElement`, `asCharacters`, `getLocation`.
- [Java SE 17 — XMLInputFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/stream/XMLInputFactory.html): tạo event readers từ Reader/InputStream, `createFilteredReader`, security properties.
- [Java SE 17 — StartElement](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/stream/events/StartElement.html): `QName`, attributes, namespaces.
- [Java SE 17 — EndElement](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/stream/events/EndElement.html): close tag và namespace.
- [Java SE 17 — Characters](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/stream/events/Characters.html): text, CDATA, whitespace.
- [Java SE 17 — EventFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/stream/EventFilter.html): lọc XMLEvent.
- [Java SE 17 — XMLEventFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/stream/XMLEventFactory.html): tạo sự kiện XML.
- [Java SE 17 — XMLEventWriter](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/stream/XMLEventWriter.html): ghi sự kiện XML.
- [Java SE 17 — XMLStreamException](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/stream/XMLStreamException.html): lỗi parse và vị trí.
- [Java SE 17 — XMLConstants](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/XMLConstants.html): các thuộc tính giới hạn external access.
- [OWASP — XML External Entity Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html): hardening StAX, XXE và bảo vệ khỏi truy cập tài nguyên ngoài.
- [Java SE 25 — XMLEventReader](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/stream/XMLEventReader.html): đối chiếu API hiện hành trên JDK mới.
