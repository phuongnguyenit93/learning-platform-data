# StAX nâng cao: XMLOutputFactory, XMLStreamWriter và XMLEventWriter

## Mục tiêu học tập

Trong **StAX (Streaming API for XML)**, chúng ta có thể đọc XML theo cơ chế kéo (pull) bằng `XMLStreamReader` hoặc `XMLEventReader`. Ở chiều ngược lại, ứng dụng có thể **tạo XML theo luồng** bằng hai mô hình ghi:

- **`XMLStreamWriter`**: writer dạng **cursor**. Gọi lần lượt `writeStartDocument`, `writeStartElement`, `writeAttribute`, `writeCharacters`, `writeEndElement`, `writeEndDocument` để sinh XML.
- **`XMLEventWriter`**: writer dạng **event**. Tạo những đối tượng sự kiện XML bằng `XMLEventFactory`, sau đó gửi từng sự kiện vào writer qua `add(XMLEvent)` hoặc copy một `XMLEventReader` bằng `add(XMLEventReader)`.
- **`XMLOutputFactory`**: factory tạo **cả hai loại writer**, lựa chọn đích `OutputStream`, `Writer` hoặc một số kiểu JAXP `Result` được triển khai hỗ trợ, đồng thời cấu hình **namespace repairing**.

Bài này thuộc nhóm **StAX nâng cao**, đi sâu vào cách sinh XML **đúng cấu trúc, namespace, escaping, encoding và vòng đời tài nguyên**. Sau khi học, bạn có thể:

1. Giải thích vai trò của `XMLOutputFactory`, `XMLStreamWriter`, `XMLEventWriter`, `XMLEventFactory` và phân biệt chúng với parser `XMLInputFactory`.
2. Tạo XML bằng cursor writer từ đầu đến cuối, với **XML declaration, root, child elements, attributes, text, empty elements và end tags**.
3. Tạo cùng thông tin bằng event writer, hiểu **event objects, `add`, `flush`, `close`** và việc copy event stream.
4. Cấu hình **`XMLOutputFactory.IS_REPAIRING_NAMESPACES`**, nắm rõ giá trị mặc định và cách khai báo prefix/URI tường minh.
5. Phân biệt **escape character data**, **escape attribute value**, **CDATA**, **XML comments**, **processing instructions** và những trường hợp writer không tự kiểm tra XML well-formedness.
6. Chọn `OutputStream` hay `Writer` để **XML declaration encoding khớp bytes thực tế**.
7. Không nhầm **`flush()`** với **`close()`**, không dựa vào `close()` của writer để đóng luôn stream do caller sở hữu.
8. Biết rằng **việc writer escape text không đồng nghĩa parser XML của bạn an toàn trước XXE**; cấu hình an toàn ở phía input.
9. Chạy một chương trình **Java 17+ độc lập**, so sánh kết quả semantic của cả hai writers bằng `XMLStreamReader`, kiểm tra namespace repair và dữ liệu tiếng Việt/emoji.
10. Thiết kế ứng dụng streaming XML có **giới hạn tài nguyên, atomic file output, exception handling và integration tests**.

**Giới hạn phiên bản:** Những API này thuộc module chuẩn `java.xml`, hiện vẫn được hỗ trợ trong **Java 17** và **Java SE 26**. Ví dụ hoàn chỉnh được **biên dịch với `javac --release 17` và chạy trên OpenJDK 24.0.2**. Chỉ sử dụng kiến thức còn áp dụng hiện nay.

## 1. Kiến trúc đầu ra của StAX

Một luồng dữ liệu Java có thể được serialize thành tài liệu XML theo hai cách:

~~~text
                         XMLOutputFactory
                                  │
                ┌─────────────────┴─────────────────┐
                │                                   │
                ▼                                   ▼
       XMLStreamWriter                       XMLEventWriter
       (cursor-based)                        (event-based)
                │                                   ▲
  writeStartElement, writeCharacters,       XMLEventFactory
  writeAttribute, writeEndElement           tạo StartElement,
                │                           Characters, EndElement...
                │                                   │
                └─────────────────┬─────────────────┘
                                  ▼
                          Writer / OutputStream
                                  │
                                  ▼
                          XML serialized output
~~~

Điều quan trọng là `XMLOutputFactory` **không tự tạo XML document khi bạn khởi tạo factory**. Bạn phải gọi phương thức `createXMLStreamWriter(...)` hoặc `createXMLEventWriter(...)`, sau đó **chủ động ghi đúng chuỗi các sự kiện/thẻ**.

Phần lớn StAX writers **không thực hiện đầy đủ kiểm tra XML well-formedness cho input API**. Việc một đoạn code không ném exception khi gọi `writeStartElement` không chứng minh tài liệu thành phẩm hợp lệ. Cần xây dựng cấu trúc đúng và, với XML quan trọng, **parse lại đầu ra trong test**.

### 1.1. Những classes cần nhớ

| API | Package | Trách nhiệm |
| --- | --- | --- |
| `XMLOutputFactory` | `javax.xml.stream` | Tạo và cấu hình XML output writers |
| `XMLStreamWriter` | `javax.xml.stream` | Ghi XML theo từng lệnh cursor |
| `XMLEventWriter` | `javax.xml.stream` | Ghi XML bằng các đối tượng event |
| `XMLEventFactory` | `javax.xml.stream` | Tạo `StartElement`, `EndElement`, `Characters`, `Attribute`, `Namespace`... |
| `XMLEvent` | `javax.xml.stream.events` | Interface gốc của XML event |
| `QName` | `javax.xml.namespace` | Tên mở rộng `namespace URI + local name + prefix` |
| `XMLInputFactory` | `javax.xml.stream` | Tạo readers để parse/đọc XML |
| `XMLStreamReader` | `javax.xml.stream` | Đọc XML bằng cursor, hữu ích để kiểm thử output |
| `XMLEventReader` | `javax.xml.stream` | Đọc XML theo event objects, có thể feed sang XMLEventWriter |

**Đừng nhầm `XMLOutputFactory` với `XMLInputFactory`**: output factory quyết định cách **ghi**; input factory kiểm soát cách **parse**, bao gồm những thiết lập quan trọng về DTD/external entities.

### 1.2. Chọn cursor hay event writer?

| Nhu cầu | `XMLStreamWriter` | `XMLEventWriter` |
| --- | --- | --- |
| Tạo XML từ dữ liệu ứng dụng | Rất trực tiếp, ít object events | Tường minh các event types |
| Ghi root/child/attribute/text | Các methods `write...` | `XMLEventFactory` rồi `add(...)` |
| Pipeline đã có `XMLEventReader` | Phải tự chuyển event thành lệnh phù hợp | Có `add(XMLEventReader)` |
| Tùy biến/chèn/xóa events | Duyệt và tự điều khiển | Hợp với event transformations |
| Bảo đảm well-formedness tuyệt đối | Không | Không |
| Namespace handling | Factory repairing hoặc khai báo thủ công | Namespace events/context và factory policy |
| Quản lý tài nguyên | `flush()` và `close()` | `flush()` và `close()` |
| Đầu ra byte stream/file | Qua factory | Qua factory |

Không nên khẳng định một cách luôn **nhanh hơn** hoặc dùng **ít RAM hơn** trên mọi provider. Cursor writer thường ít phải tạo event objects ở application code, nhưng performance thực tế còn phụ thuộc factory implementation, serializer, output sink, XML kích thước và cách ứng dụng buffer.

## 2. Tạo XMLOutputFactory

Cách hiện hành:

~~~java
import javax.xml.stream.XMLOutputFactory;

XMLOutputFactory factory = XMLOutputFactory.newFactory();
~~~

`newFactory()` dùng **JAXP provider lookup mechanism**, nên ứng dụng có thể dùng provider khác nhau theo runtime/classpath/module configuration. `newDefaultFactory()` là cách chọn **implementation mặc định được tích hợp trong JDK**, hữu ích khi bạn muốn tránh lựa chọn provider qua lookup.

Không cần tự dùng những overload **deprecated** của `newInstance(String, ClassLoader)`; hãy dùng `newFactory()` hoặc overload tương ứng hiện hành khi thật sự cần.

### 2.1. Các cách tạo writer

~~~java
// Mảnh minh họa: writerSink là java.io.Writer.
XMLStreamWriter cursor = factory.createXMLStreamWriter(writerSink);
XMLEventWriter events = factory.createXMLEventWriter(writerSink);
~~~

Khi ghi bytes, có các overload nhận `OutputStream` và có thể nhận `encoding`:

~~~java
// Mảnh minh họa, OutputStream output đã mở.
XMLStreamWriter cursor = factory.createXMLStreamWriter(output, "UTF-8");

// Hoặc:
XMLEventWriter eventWriter = factory.createXMLEventWriter(output, "UTF-8");
~~~

**Đừng tạo đồng thời cả hai writers trên cùng một OutputStream rồi ghi xen kẽ**, trừ khi đã có một thiết kế phối hợp rất rõ; hai serializers có state riêng và dễ tạo XML hỏng. Nếu muốn so sánh, ghi **hai tài liệu độc lập vào hai sinks riêng** như demo.

Các overload dùng **JAXP `Result`** như `StreamResult` có thể **không được provider hỗ trợ**. Tài liệu `XMLOutputFactory` đánh dấu các overload tạo writer từ `Result` là tùy chọn; có thể ném `UnsupportedOperationException`.

### 2.2. Vì sao cấu hình factory trước khi tạo writer?

Factory giữ properties được dùng để tạo các writer tiếp theo. Cấu hình namespace repairing **trước khi gọi `createXMLStreamWriter` hoặc `createXMLEventWriter`**, không kỳ vọng thay đổi property trên factory sẽ retroactively sửa một writer đã tạo.

`XMLOutputFactory.newFactory()` có thể ném `FactoryConfigurationError` nếu provider không thể khởi tạo. Tùy ứng dụng, đây là lỗi cấu hình/runtime cần báo rõ, không mặc định retry tạo factory vô hạn.

## 3. XMLStreamWriter: ghi XML theo thứ tự

`XMLStreamWriter` là một **stateful writer**. Bạn phải cân bằng các thẻ mở/đóng, thêm attributes/namespaces đúng thời điểm và kết thúc tài liệu.

### 3.1. Ví dụ đơn giản

~~~java
// Mảnh minh họa với XMLStreamWriter writer đã tạo.
writer.writeStartDocument("UTF-8", "1.0");
writer.writeStartElement("user");
writer.writeAttribute("id", "42");
writer.writeStartElement("name");
writer.writeCharacters("Đặng & Lan");
writer.writeEndElement(); // </name>
writer.writeEndElement(); // </user>
writer.writeEndDocument();
writer.flush();
~~~

Một dạng output hợp lệ:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<user id="42"><name>Đặng &amp; Lan</name></user>
~~~

**Output minh họa không cam kết ký tự whitespace, quote style hoặc XML declaration formatting giống mọi provider.** Điều quan trọng là tài liệu XML tương đương về cấu trúc và content.

### 3.2. Quy tắc thực thi

1. **`writeStartDocument(...)`** nếu muốn XML declaration, trước root element.
2. **`writeStartElement(...)`** để mở root/child.
3. Ngay sau thẻ mở, có thể **`writeNamespace(...)`** và **`writeAttribute(...)`** khi start tag còn ở trạng thái nhận metadata.
4. **`writeCharacters(...)`** để ghi **text content**, không phải markup.
5. Mỗi start element cần end element tương ứng; dùng **`writeEndElement()`**.
6. Dùng **`writeEmptyElement(...)`** để tạo phần tử rỗng như `<empty/>`.
7. **`writeEndDocument()`** sau khi document hoàn tất; `flush()` để đẩy buffer.
8. Luôn **`close()` trong `finally`**, đồng thời đóng underlying stream/Writer ở scope sở hữu tương ứng.

`writeEndElement()` đóng **phần tử gần nhất trong stack của writer**. Nó không nhận name nên phải đảm bảo thứ tự đúng. `writeEndDocument()` có thể đóng những start tags còn đang mở theo contract, nhưng **đừng dùng nó để che một lỗi ghép thẻ**. Hãy chủ động cân bằng root/children và parse lại tài liệu trong test.

### 3.3. `writeEmptyElement` không phải `writeEndElement`

~~~java
// Mảnh minh họa, writer đang ở bên trong root.
writer.writeEmptyElement("empty");
// Tạo một empty element.
// Không tiếp tục gọi writeEndElement() chỉ để đóng empty một lần nữa.
~~~

Nếu gọi thêm `writeEndElement()` với suy nghĩ nó đóng empty element vừa ghi, bạn có thể đóng nhầm **parent**. Empty element không được đưa vào stack mở như một `writeStartElement` chưa đóng.

### 3.4. Attributes phải được ghi ở đúng trạng thái

~~~java
writer.writeStartElement("account");
writer.writeAttribute("status", "active");
writer.writeCharacters("Nội dung");
writer.writeEndElement();
~~~

Nếu ghi characters trước rồi cố thêm attribute sau, start tag đã hoàn thành; writer có thể ném `IllegalStateException` hoặc `XMLStreamException` tùy điều kiện/provider. Attribute luôn phải nằm trong **start tag** của phần tử, không phải trong text.

`writeAttribute(localName, value)` là attribute **không có prefix**. Với namespaced attribute, cần đúng overload có namespace và một prefix binding hợp lệ hoặc bật repairing namespaces.

## 4. Escaping: tránh tạo XML không hợp lệ và injection

Một lý do quan trọng để dùng writer thay vì tự ghép chuỗi XML là **các phương thức dành riêng cho character data/attribute value có escaping theo contract**.

### 4.1. Character data

~~~java
writer.writeCharacters("Xin <chào> & Đặng");
~~~

Dữ liệu được biểu diễn trong XML serialized output với những ký tự đặc biệt được escaped, ví dụ:

~~~xml
Xin &lt;chào&gt; &amp; Đặng
~~~

`XMLStreamWriter.writeCharacters` phải escape **`&`, `<`, `>`** theo interface contract, không coi input là markup. Khi parse lại, XML reader sẽ trả **`Xin <chào> & Đặng`** như data.

### 4.2. Attribute values

~~~java
writer.writeAttribute("code", "A&B");
~~~

Kết quả có thể là:

~~~xml
code="A&amp;B"
~~~

`writeAttribute` thực hiện escaping thích hợp cho attribute (bao gồm double quote khi cần). Không cần tự gọi một hàm replace `&` sang `&amp;` trước khi truyền data vào writer: làm vậy dễ **double escape** và khiến nội dung khác ban đầu.

### 4.3. Escaping không phải validation toàn bộ XML

Theo Oracle Javadoc, **`XMLStreamWriter` không thực hiện kiểm tra well-formedness đầy đủ trên input**; `XMLEventWriter` cũng **không bắt buộc phải validate form của XML**. Tên element/attribute, event ordering, comment data, CDATA và những ký tự không hợp lệ trong XML vẫn cần được kiểm soát.

**Không đưa giá trị người dùng vào `writeStartElement` như một XML name chưa validate.** `writeCharacters` bảo vệ text content, không biến một XML name tùy ý thành name hợp lệ. Với document/schema có business constraints, hãy validate đầu vào và parse output trong test.

### 4.4. CDATA là lựa chọn biểu diễn, không phải “escape thần kỳ”

~~~java
// Mảnh minh họa:
writer.writeCData("A < B");
~~~

Thông thường sẽ tạo một CDATA section. Tuy nhiên CDATA **không thể chứa literal chuỗi `]]>` nguyên vẹn trong một section**. `writeCData` không phải cách để thoát mọi tình huống. Với text từ client không kiểm soát, ưu tiên **`writeCharacters`** và chỉ dùng CDATA khi sản phẩm có yêu cầu serialization cụ thể, với xử lý tách CDATA an toàn nếu cần.

### 4.5. Comments và processing instructions

~~~java
writer.writeComment("generated document");
writer.writeProcessingInstruction("mode", "fast");
~~~

XML comments không được chứa những chuỗi không hợp lệ như **`--`** bên trong; processing instruction có quy tắc riêng cho target/data. Không nhét raw untrusted text vào các API này rồi mặc định serializer sẽ làm sạch. Chỉ sử dụng giá trị được kiểm soát hoặc validate theo XML grammar.

Không gọi `writeDTD` trên arbitrary user input. Với XML do ứng dụng tạo, nếu không cần DTD thì **đừng sinh DTD**. Bảo mật XXE chủ yếu liên quan **đọc/parsing XML**, nhưng không tạo ra external entity references ngoài ý muốn cũng là một chính sách hợp lý.

## 5. XML namespace và `IS_REPAIRING_NAMESPACES`

XML namespace tách **prefix hiển thị** khỏi **namespace URI thực sự**. Một tên XML được hiểu theo **namespace URI + local name**, còn prefix như `p` là nhãn có thể khác nhau giữa serializations.

Ví dụ:

~~~xml
<p:catalog xmlns:p="urn:demo">
  <p:item code="A&amp;B">Xin chào</p:item>
</p:catalog>
~~~

`p` là prefix; `urn:demo` là namespace URI. Một serializer khác có thể dùng `n1` thay `p` mà cùng semantics nếu các binding URI/name tương đương.

### 5.1. Mặc định: namespace repairing tắt

Property chuẩn:

~~~java
XMLOutputFactory factory = XMLOutputFactory.newFactory();
factory.setProperty(
        XMLOutputFactory.IS_REPAIRING_NAMESPACES, Boolean.FALSE);
~~~

Theo Javadoc, **mặc định là `false`**, và property `javax.xml.stream.isRepairingNamespaces` có mức hỗ trợ **required** theo bảng cấu hình.

Ở chế độ này, **ứng dụng chịu trách nhiệm khai báo namespace binding hợp lệ**. Khi cần tên có prefix, có thể dùng:

~~~java
writer.writeStartElement("p", "catalog", "urn:demo");
writer.writeNamespace("p", "urn:demo");
writer.writeStartElement("p", "item", "urn:demo");
writer.writeCharacters("Xin chào");
writer.writeEndElement();
writer.writeEndElement();
~~~

Đừng tưởng `setPrefix("p", "urn:demo")` ở writer luôn tự viết **`xmlns:p`** ra output khi repairing=false. Prefix mapping trong writer và **namespace declaration được serialize** là hai khái niệm cần hiểu đúng; hãy khai báo rõ bằng `writeNamespace` hoặc `writeDefaultNamespace` nơi cần, rồi parse output để xác minh.

Nếu gọi một overload yêu cầu `namespaceURI` đã được bind nhưng binding không tồn tại khi **repairing=false**, API có thể báo `XMLStreamException`.

### 5.2. Khi repairing=true

~~~java
XMLOutputFactory factory = XMLOutputFactory.newFactory();
factory.setProperty(
        XMLOutputFactory.IS_REPAIRING_NAMESPACES, Boolean.TRUE);
~~~

Khi đó writer có thể **tự thêm namespace declarations, gán prefix phù hợp hoặc sửa prefix xung đột** theo thuật toán mà Javadoc mô tả.

~~~java
// Mảnh minh họa: writer được tạo từ factory repairing=true.
writer.writeStartElement("urn:repair", "root");
writer.writeAttribute("urn:repair", "id", "7");
writer.writeEndElement();
~~~

Với API này, writer có thể tạo prefix tự động cho namespaced attribute. **Không hardcode kỳ vọng prefix cụ thể**, vì provider có thể chọn các tên khác nhau, như `zdef...`, `ns...` hay dùng default namespace phù hợp.

### 5.3. Attribute và default namespace không giống element

Theo quy tắc XML Namespaces, **unprefixed attribute không tự thuộc default namespace của element**. Vì vậy:

~~~xml
<item xmlns="urn:items" code="A"/>
~~~

element `item` có namespace `urn:items`, nhưng attribute `code` **không có namespace**. Nếu nghiệp vụ cần attribute có namespace riêng, phải có prefix phù hợp:

~~~xml
<item xmlns="urn:items" xmlns:m="urn:meta" m:code="A"/>
~~~

Khi bật namespace repairing, thư viện có thể bổ sung prefix/declaration cần thiết cho attribute. Nhưng bạn vẫn phải truyền **đúng namespace URI** khi gọi API.

### 5.4. Không so sánh serialization bằng raw string khi chỉ cần XML semantics

Hai tài liệu có thể biểu diễn cùng XML content nhưng khác:

- Prefix được tạo (`p` so với `ns1`).
- Quote style của attributes.
- Cách viết empty elements (`<e/>` và `<e></e>`).
- Whitespace/formatting.
- XML declaration style và thứ tự namespace/attribute declarations.

Nếu chỉ kiểm tra nghiệp vụ, hãy **parse output rồi so sánh structure/namespace URI/attribute/text**. Nếu ứng dụng cần exact byte-for-byte XML (chữ ký số hoặc hash), phải có **canonicalization và charset policy** riêng; StAX không tự bảo đảm canonical XML.

## 6. XMLEventWriter và XMLEventFactory

`XMLEventWriter` nhận những event objects thuộc `javax.xml.stream.events`. Nó phù hợp khi ứng dụng đã đọc/biến đổi XML ở mức event hoặc muốn tạo sự kiện độc lập với thứ tự gọi nhiều phương thức `write...`.

### 6.1. Tạo event writer

~~~java
XMLOutputFactory output = XMLOutputFactory.newFactory();
XMLEventFactory events = XMLEventFactory.newFactory();
XMLEventWriter writer = output.createXMLEventWriter(target);
~~~

`target` có thể là `Writer` do ứng dụng sở hữu. `XMLEventFactory.newFactory()` tạo các đối tượng `StartDocument`, `StartElement`, `EndElement`, `Characters`, `Attribute`, `Namespace`...

### 6.2. Ghi tuần tự bằng add

~~~java
// Mảnh minh họa, writer và events đã được tạo.
writer.add(events.createStartDocument("UTF-8", "1.0"));
writer.add(events.createStartElement("", "", "user"));
writer.add(events.createStartElement("", "", "name"));
writer.add(events.createCharacters("Đặng & Lan"));
writer.add(events.createEndElement("", "", "name"));
writer.add(events.createEndElement("", "", "user"));
writer.add(events.createEndDocument());
writer.flush();
~~~

Các event tạo ra **một cấu trúc XML tương đương** với ví dụ cursor writer. `createCharacters` mang text data và output writer serialize thành text XML escaped thích hợp, nhưng không vì vậy mà event writer bảo đảm kiểm tra cấu trúc/nesting đầy đủ.

### 6.3. Attributes và namespaces trong StartElement event

`XMLEventFactory` có overload `createStartElement` nhận **iterators của attributes và namespaces**:

~~~java
writer.add(events.createStartElement(
        "p", "urn:demo", "catalog",
        java.util.List.of(
                events.createAttribute("version", "1")).iterator(),
        java.util.List.of(
                events.createNamespace("p", "urn:demo")).iterator()));
~~~

Ví dụ trên đặt **namespace declaration cùng StartElement event**. Khi writer ở repairing=false, cách này giúp XML serialized output có binding hợp lệ.

**Không lẫn thứ tự tham số:** `XMLStreamWriter.writeStartElement(prefix, localName, namespaceURI)` khác với `XMLEventFactory.createStartElement(prefix, namespaceURI, localName)`. Đây là một lỗi thường gặp khi chuyển từ cursor writer sang event writer.

### 6.4. Các event cần thiết

| XMLEventFactory method | Event |
| --- | --- |
| `createStartDocument(...)` | XML declaration / document start |
| `createEndDocument()` | Kết thúc document |
| `createStartElement(...)` | Thẻ mở, kèm attributes/namespaces nếu cần |
| `createEndElement(...)` | Thẻ đóng |
| `createCharacters(...)` | Text |
| `createSpace(...)` | Whitespace event |
| `createAttribute(...)` | Attribute object |
| `createNamespace(...)` | Namespace declaration object |
| `createComment(...)` | Comment |
| `createProcessingInstruction(...)` | Processing instruction |
| `createCData(...)` | CDATA content event |

`XMLEventWriter` cung cấp **`add(XMLEvent)`** và **`add(XMLEventReader)`**. Với overload nhận reader, implementation sẽ consume events từ input đến khi `hasNext()` false và thêm từng event vào writer; đây là một tiện ích stream copy, không phải một bộ lọc tự động xóa DTD hoặc sanitization.

### 6.5. Copy event reader qua event writer

~~~java
// Mảnh minh họa khi XMLEventReader eventReader đã được tạo an toàn.
XMLEventWriter out = XMLOutputFactory.newFactory()
        .createXMLEventWriter(output);
try {
    out.add(eventReader);
    out.flush();
} finally {
    out.close();
}
~~~

**Đầu vào phải được parse bằng XMLInputFactory có policy bảo mật**, đồng thời cần áp size/depth/event quotas phù hợp. `add(eventReader)` không tự biến một document nguy hiểm hoặc invalid thành hợp lệ.

Việc copy cũng không đảm bảo output **byte-for-byte giống input**: parser/serializer có thể thay đổi CDATA/text splitting, prefix, whitespace hoặc XML declaration. Nếu cần giữ chữ ký byte chính xác, không nên dựa vào generic parse-and-reserialize.

## 7. Encoding: declaration khác bytes thực tế

Một trong những lỗi output phổ biến là ghi XML declaration có **`encoding="UTF-8"`** nhưng ghi bytes bằng một charset khác.

`XMLStreamWriter.writeStartDocument(encoding, version)` **chỉ mô tả encoding trong XML declaration**; theo Javadoc, phương thức này **không tự đặt charset cho underlying output**. Encoding thực tế phải được xác định khi tạo writer/sink.

### 7.1. Cách rõ ràng với OutputStream

~~~java
// Mảnh minh họa: Path destination đã được ứng dụng kiểm soát.
try (java.io.OutputStream bytes =
        java.nio.file.Files.newOutputStream(destination)) {
    XMLOutputFactory output = XMLOutputFactory.newFactory();
    XMLStreamWriter xml = output.createXMLStreamWriter(bytes, "UTF-8");
    try {
        xml.writeStartDocument("UTF-8", "1.0");
        xml.writeStartElement("message");
        xml.writeCharacters("Xin chào Việt Nam 😀");
        xml.writeEndElement();
        xml.writeEndDocument();
        xml.flush();
    } finally {
        xml.close();
    }
}
~~~

**Trong đoạn minh họa**, OutputStream do try-with-resources của application sở hữu. XMLStreamWriter được đóng trong finally và không thay việc đóng OutputStream.

### 7.2. Dùng Writer với charset cụ thể

~~~java
// Mảnh minh họa với Path destination.
try (java.io.Writer sink =
        java.nio.file.Files.newBufferedWriter(
                destination, java.nio.charset.StandardCharsets.UTF_8)) {
    XMLStreamWriter xml = XMLOutputFactory.newFactory()
            .createXMLStreamWriter(sink);
    try {
        xml.writeStartDocument("UTF-8", "1.0");
        xml.writeStartElement("message");
        xml.writeCharacters("Đặng & Lan");
        xml.writeEndElement();
        xml.writeEndDocument();
        xml.flush();
    } finally {
        xml.close();
    }
}
~~~

Ở đây charset thật được quyết định bởi **Files.newBufferedWriter(..., UTF_8)**. Với một `StringWriter` trong memory, dữ liệu là Java characters; chỉ khi serialize String thành bytes sau đó mới có một charset cụ thể. Nếu ghi XML declaration UTF-8 rồi sau đó tự chuyển String thành bytes bằng charset khác, contract sẽ sai.

### 7.3. Tại sao không dùng platform default?

Nếu bạn chuyển String XML thành bytes bằng **`getBytes()` không chỉ rõ charset**, output có thể phụ thuộc môi trường hoặc không đồng bộ với giao thức. Dùng **StandardCharsets.UTF_8** hoặc encoding được specification của ứng dụng quy định.

Khi truyền XML qua HTTP/gRPC/file, cần nhất quán giữa **actual bytes**, **XML declaration** và **Content-Type charset** nếu giao thức áp dụng. Không chỉ sửa phần declaration mà quên encoding ở sink.

## 8. Ví dụ Java 17+ hoàn chỉnh: cursor writer, event writer và namespace repair

Chương trình **StaxOutputDemo.java** bên dưới chạy độc lập bằng JDK, không cần DBMS hoặc thư viện bên ngoài. Nó tạo hai XML documents có cùng semantics:

- `streamDocument()`: dùng `XMLStreamWriter`, tự khai báo namespace `p` khi repairing=false, ghi attribute và text có ký tự đặc biệt, một empty element.
- `eventDocument()`: dùng `XMLEventFactory` + `XMLEventWriter` để tạo StartElement/EndElement/Characters events với cùng nội dung và namespace.
- `inspect(...)`: parse lại bằng **XMLStreamReader cấu hình an toàn** rồi trích root, namespace URI, item text, attribute và empty-element count.
- `repairedDocument()`: bật **IS_REPAIRING_NAMESPACES=true**, không tự chọn prefix và để writer tạo binding cho root/attribute namespaced.
- `main()`: đối chiếu escaping của text/attribute, semantic equality và namespace repairing, không dựa vào prefix tự sinh.

**Lưu ý về stdout:** Dòng `differentSerialization=true` là kết quả trên **OpenJDK 24.0.2** do hai writers có thể serialize empty element khác nhau. Đó **không phải contract portability**; provider khác hoàn toàn có thể cho raw XML strings giống nhau dù semantics vẫn đúng. Trong integration test đa provider, nên assert `sameSemantics=true`, không assert raw serialization luôn khác.

### 8.1. File duy nhất: StaxOutputDemo.java

~~~java
import java.io.StringReader;
import java.io.StringWriter;
import java.util.List;
import java.util.Objects;
import javax.xml.XMLConstants;
import javax.xml.stream.XMLEventFactory;
import javax.xml.stream.XMLEventWriter;
import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLOutputFactory;
import javax.xml.stream.XMLStreamConstants;
import javax.xml.stream.XMLStreamException;
import javax.xml.stream.XMLStreamReader;
import javax.xml.stream.XMLStreamWriter;

public final class StaxOutputDemo {
    private static final String NS = "urn:demo";
    private static final String TEXT = "Xin <chào> & Đặng 😀";

    record Report(String root, String item, String code, String version,
                  int emptyCount, String namespace) {}

    static String streamDocument() throws XMLStreamException {
        StringWriter target = new StringWriter();
        XMLOutputFactory factory = XMLOutputFactory.newFactory();
        factory.setProperty(XMLOutputFactory.IS_REPAIRING_NAMESPACES, Boolean.FALSE);
        XMLStreamWriter writer = factory.createXMLStreamWriter(target);
        try {
            writer.writeStartDocument("UTF-8", "1.0");
            writer.writeStartElement("p", "catalog", NS);
            writer.writeNamespace("p", NS);
            writer.writeAttribute("version", "1");
            writer.writeStartElement("p", "item", NS);
            writer.writeAttribute("code", "A&B");
            writer.writeCharacters(TEXT);
            writer.writeEndElement();
            writer.writeEmptyElement("p", "empty", NS);
            writer.writeEndElement();
            writer.writeEndDocument();
            writer.flush();
        } finally {
            writer.close();
        }
        return target.toString();
    }

    static String eventDocument() throws XMLStreamException {
        StringWriter target = new StringWriter();
        XMLOutputFactory output = XMLOutputFactory.newFactory();
        XMLEventFactory events = XMLEventFactory.newFactory();
        XMLEventWriter writer = output.createXMLEventWriter(target);
        try {
            writer.add(events.createStartDocument("UTF-8", "1.0"));
            writer.add(events.createStartElement("p", NS, "catalog",
                    List.of(events.createAttribute("version", "1")).iterator(),
                    List.of(events.createNamespace("p", NS)).iterator()));
            writer.add(events.createStartElement("p", NS, "item",
                    List.of(events.createAttribute("code", "A&B")).iterator(),
                    List.of(events.createNamespace("p", NS)).iterator()));
            writer.add(events.createCharacters(TEXT));
            writer.add(events.createEndElement("p", NS, "item"));
            writer.add(events.createStartElement("p", NS, "empty"));
            writer.add(events.createEndElement("p", NS, "empty"));
            writer.add(events.createEndElement("p", NS, "catalog"));
            writer.add(events.createEndDocument());
            writer.flush();
        } finally {
            writer.close();
        }
        return target.toString();
    }

    static XMLInputFactory safeInputFactory() {
        XMLInputFactory f = XMLInputFactory.newFactory();
        f.setProperty(XMLInputFactory.SUPPORT_DTD, false);
        f.setProperty(XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
        f.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        f.setXMLResolver((publicId, systemId, baseUri, namespace) -> {
            throw new XMLStreamException("External entity forbidden");
        });
        return f;
    }

    static Report inspect(String xml) throws XMLStreamException {
        XMLStreamReader reader = safeInputFactory()
                .createXMLStreamReader(new StringReader(xml));
        String root = null, item = null, code = null, version = null, ns = null;
        int empties = 0;
        try {
            while (reader.hasNext()) {
                int kind = reader.next();
                if (kind == XMLStreamConstants.DTD) {
                    throw new XMLStreamException("DOCTYPE forbidden");
                }
                if (kind != XMLStreamConstants.START_ELEMENT) continue;
                String local = reader.getLocalName();
                if ("catalog".equals(local)) {
                    root = local;
                    ns = reader.getNamespaceURI();
                    version = reader.getAttributeValue(null, "version");
                } else if ("item".equals(local)) {
                    code = reader.getAttributeValue(null, "code");
                    item = reader.getElementText();
                } else if ("empty".equals(local)) {
                    if (!reader.getElementText().isEmpty()) {
                        throw new XMLStreamException("Expected empty element");
                    }
                    empties++;
                }
            }
        } finally {
            reader.close();
        }
        return new Report(root, item, code, version, empties, ns);
    }

    static String repairedDocument() throws XMLStreamException {
        StringWriter target = new StringWriter();
        XMLOutputFactory factory = XMLOutputFactory.newFactory();
        factory.setProperty(XMLOutputFactory.IS_REPAIRING_NAMESPACES, Boolean.TRUE);
        XMLStreamWriter writer = factory.createXMLStreamWriter(target);
        try {
            writer.writeStartDocument("UTF-8", "1.0");
            writer.writeStartElement("urn:repair", "root");
            writer.writeAttribute("urn:repair", "id", "7");
            writer.writeEndElement();
            writer.writeEndDocument();
        } finally {
            writer.close();
        }
        return target.toString();
    }

    public static void main(String[] args) throws Exception {
        String cursorXml = streamDocument();
        String eventXml = eventDocument();
        Report cursor = inspect(cursorXml);
        Report events = inspect(eventXml);

        System.out.println("cursorEscapesText="
                + cursorXml.contains("Xin &lt;chào&gt; &amp; Đặng"));
        System.out.println("eventEscapesText="
                + eventXml.contains("Xin &lt;chào&gt; &amp; Đặng"));
        System.out.println("cursorEscapesAttribute="
                + cursorXml.contains("A&amp;B"));
        System.out.println("eventEscapesAttribute="
                + eventXml.contains("A&amp;B"));
        System.out.println("sameSemantics=" + cursor.equals(events));
        System.out.println("root=" + cursor.root());
        System.out.println("namespace=" + cursor.namespace());
        System.out.println("item=" + cursor.item());
        System.out.println("code=" + cursor.code());
        System.out.println("version=" + cursor.version());
        System.out.println("emptyCount=" + cursor.emptyCount());

        String repaired = repairedDocument();
        XMLStreamReader reader = safeInputFactory()
                .createXMLStreamReader(new StringReader(repaired));
        try {
            while (reader.hasNext()
                    && reader.next() != XMLStreamConstants.START_ELEMENT) {}
            System.out.println("repairNamespace=" + reader.getNamespaceURI());
            System.out.println("repairAttribute="
                    + reader.getAttributeValue("urn:repair", "id"));
        } finally {
            reader.close();
        }
        System.out.println("differentSerialization="
                + !Objects.equals(cursorXml, eventXml));
    }
}
~~~

### 8.2. Biên dịch và chạy

Lưu file chính xác tên **StaxOutputDemo.java**. Từ thư mục chứa file, dùng JDK 17 hoặc mới hơn:

~~~bash
javac -encoding UTF-8 --release 17 StaxOutputDemo.java
java StaxOutputDemo
~~~

Các lệnh này cũng dùng được trong Windows PowerShell. Không cần Maven, Gradle, JDBC driver hay thư viện bên ngoài JDK.

### 8.3. Stdout chính xác đã kiểm chứng

~~~text
cursorEscapesText=true
eventEscapesText=true
cursorEscapesAttribute=true
eventEscapesAttribute=true
sameSemantics=true
root=catalog
namespace=urn:demo
item=Xin <chào> & Đặng 😀
code=A&B
version=1
emptyCount=1
repairNamespace=urn:repair
repairAttribute=7
differentSerialization=true
~~~

Đã **biên dịch/chạy trên OpenJDK 24.0.2 với `--release 17`**, so khớp chính xác **14 dòng stdout**. `differentSerialization=true` phụ thuộc implementation, không phải điều kiện phải đúng ở mọi provider.

### 8.4. Giải thích các phép kiểm tra

- **`cursorEscapesText=true`** và **`eventEscapesText=true`**: text đầu vào có `<`, `>` và `&` được xuất thành XML-escaped text thích hợp.
- **`cursorEscapesAttribute=true`** và **`eventEscapesAttribute=true`**: attribute value chứa `&` đã được serialize với `&amp;`.
- **`sameSemantics=true`**: parse lại hai outputs cho cùng một record `Report` với root, item text, attribute, namespace và count. Đây là kiểm tra semantics, không phải so raw strings.
- **`root=catalog`**, **`namespace=urn:demo`**: cả hai writers đều tạo root theo cùng expanded name.
- **`item=Xin <chào> & Đặng 😀`**: parser decode entity escaping và giữ Unicode tiếng Việt/emoji.
- **`code=A&B`**: attribute được trả ở dạng giá trị gốc, không có chuỗi escaped trong Java value.
- **`version=1`**: metadata attribute đúng.
- **`emptyCount=1`**: cả hai outputs có đúng một empty element theo semantics, dù serialized text có thể là `<p:empty/>` hoặc `<p:empty></p:empty>`.
- **`repairNamespace=urn:repair`**: writer repairing đã tạo element thuộc namespace URI đúng.
- **`repairAttribute=7`**: attribute trong `urn:repair` có thể được truy xuất bằng namespace URI + local name, không cần biết prefix được tạo.
- **`differentSerialization=true`**: chỉ cho thấy các writers trên JDK được kiểm thử có text output khác nhau. **Không dùng dòng này làm invariant đa provider**.

### 8.5. Vì sao inspect dùng XMLStreamReader?

`inspect(...)` kiểm tra XML bằng cách parse lại từ **StringReader**. Nó không chỉ tìm chuỗi literal trong output, mà còn đọc **root, namespace, attributes, leaf text và số phần tử rỗng**. Đây là một pattern hữu ích khi viết **unit/integration test cho XML serializers**.

Input factory của test bật những biện pháp chính để chặn **DTD/external entities**. Đối với production, cần kiểm soát kích thước XML, độ sâu element, schema và security behavior của provider thật. Hàm inspect trong demo không đặt quota vì input rất nhỏ, do chính chương trình tạo.

### 8.6. Test đã chứng minh điều gì và chưa chứng minh điều gì?

**Đã chứng minh trên JDK 24.0.2:**

- Code dùng những Java APIs có sẵn ở target `--release 17`.
- Cursor/event output tạo cùng XML semantics với input tự tạo.
- Text/attributes có escape cần thiết.
- Namespace repairing tạo đúng expanded names.
- Các writer được đóng rõ ràng trong `finally`, không còn tài nguyên do app quản lý trong ví dụ in-memory.

**Chưa chứng minh:**

- Mọi provider khác serialize giống hệt byte-for-byte.
- Writer tự validate mọi XML name, comment, CDATA, control character.
- Lưu file/network với mọi charset hoặc I/O failure đều an toàn.
- Parser input không đáng tin trên mọi runtime/provider đều có cùng settings.
- XMLEventWriter luôn có hiệu năng tốt hơn/kém hơn XMLStreamWriter.
- Một output lớn luôn dùng O(1) RAM khi ứng dụng chọn `StringWriter`.

`StringWriter` trong demo cố tình giữ toàn bộ XML trong memory để so sánh ngắn; production tạo XML lớn cần ghi vào OutputStream/Writer streaming thực, kèm giới hạn và chính sách file atomicity.

## 9. `flush()`, `close()` và underlying output ownership

Cả `XMLStreamWriter` và `XMLEventWriter` đều có:

~~~java
writer.flush();
writer.close();
~~~

**`flush()`** đẩy dữ liệu đang buffer xuống output mechanism. Nó **không kết thúc XML document**, không đóng writer và không bảo đảm durable storage trên disk.

**`close()`** giải phóng tài nguyên writer. Với `XMLStreamWriter`, Javadoc quy định `close()` **không được đóng underlying output stream**. Với `XMLEventWriter`, contract nói free resources associated with writer; vì vậy ứng dụng vẫn nên **quản lý underlying Writer/OutputStream theo ownership của riêng nó**, không dựa vào implementation-specific side effects.

### 9.1. Writer interfaces trên Java 17

Trong **Java 17**, `XMLStreamWriter` và `XMLEventWriter` có phương thức `close()` nhưng **không phải AutoCloseable để dùng trực tiếp như `try (XMLStreamWriter w = ...)`**. Vì thế ví dụ chính dùng:

~~~java
XMLStreamWriter xml = factory.createXMLStreamWriter(sink);
try {
    // Ghi tài liệu.
} finally {
    xml.close();
}
~~~

Underlying `Writer` hoặc `OutputStream` của Java là AutoCloseable, nên có thể dùng try-with-resources **bên ngoài**.

Lưu ý khi `xml.close()` cũng ném `XMLStreamException` trong finally, nó có thể che exception trước đó nếu không có exception policy. Với ứng dụng quan trọng, giữ **primary failure** và gắn cleanup failure dưới dạng **suppressed exception** hoặc báo riêng theo kiến trúc.

### 9.2. Mở file và xuất an toàn

Một luồng file hợp lý:

~~~text
Validate destination và quota
       │
       ▼
Tạo temporary file trong thư mục được phép
       │
       ▼
Mở OutputStream/Writer với charset rõ
       │
       ▼
XMLOutputFactory → XMLStreamWriter hoặc XMLEventWriter
       │
       ▼
Ghi XML hoàn chỉnh, flush, close writer
       │
       ▼
Đóng underlying stream
       │
       ▼
Validate thành phẩm nếu nghiệp vụ yêu cầu
       │
       ▼
Atomic move/publish khi filesystem hỗ trợ
       │
       ▼
Dọn temp file khi lỗi
~~~

Đừng ghi file đến path do user tự cung cấp mà không kiểm tra, đừng giữ temporary files chứa dữ liệu nhạy cảm mãi sau request lỗi. Nếu output được gửi qua network, kiểm soát backpressure, timeout/cancellation và client disconnect.

### 9.3. Streaming không tự có giới hạn memory

Khi writer ghi vào `StringWriter`, toàn bộ output vẫn nằm trong heap. Khi ghi vào `OutputStream` hoặc buffered `Writer` trực tiếp tới file/socket, ứng dụng **có thể** giảm việc materialize toàn document, nhưng provider vẫn có buffer và các structures riêng. Đo memory với payload thật, không suy từ tên API.

Nếu một ứng dụng cần tạo XML nhiều GB, hãy lấy input theo streaming batches, serialize incremental, không gom toàn bộ objects thành List hoặc String lớn trước, áp quota và xử lý lỗi giữa chừng.

## 10. Bảo mật XML ở chiều ghi và chiều đọc

### 10.1. Chiều ghi: output encoding và cấu trúc

- **Không tự ghép XML string** từ user-supplied data khi có serializer hỗ trợ.
- Dùng `writeCharacters` hoặc `createCharacters` cho **text**, `writeAttribute`/`createAttribute` cho **attribute value**.
- Validate **element/attribute name, namespace URI** theo application schema.
- Không đưa chuỗi chưa kiểm tra vào `writeCData`, `writeComment`, `writeProcessingInstruction`, `writeDTD` hoặc entity reference.
- Đảm bảo **XML well-formedness, nesting, exactly one root**, và parse lại khi cần.
- Giới hạn output size và content depth, tránh denial of service do input làm tăng output bất thường.
- Bảo mật file paths/temp files/logging; không log toàn bộ XML chứa secrets/PII.

### 10.2. Chiều đọc: XXE và XML bombs

Nếu có `XMLEventReader` hoặc `XMLStreamReader` đọc XML từ nguồn không đáng tin để sau đó đưa vào writer:

~~~java
// Mảnh minh họa factory đầu vào với chính sách chặn external access.
XMLInputFactory input = XMLInputFactory.newFactory();
input.setProperty(XMLInputFactory.SUPPORT_DTD, false);
input.setProperty(XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
input.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
input.setXMLResolver((publicId, systemId, baseUri, namespace) -> {
    throw new XMLStreamException("External entity forbidden");
});
~~~

**Không im lặng bỏ qua lỗi setProperty** nếu provider không hỗ trợ một chính sách bắt buộc. Một ứng dụng nhạy cảm cần fail closed và test bằng XML có DOCTYPE/internal/external entities trong môi trường an toàn. Đồng thời, áp giới hạn bytes, element depth, entity expansion và processing time khi thích hợp.

**Escaping đầu ra không tự ngăn XXE ở đầu vào.** Một event writer chỉ ghi các events nó nhận; nếu parser đầu vào đã mở external entities, thiệt hại có thể xảy ra **trước khi writer xuất dữ liệu**.

### 10.3. Không coi event copy là sanitizer

~~~java
// Mảnh minh họa:
out.add(eventReader);
~~~

Overload này chỉ tiện để copy event stream. Nó không thay chính sách **validate/sanitize/whitelist** XML. Nếu pipeline có yêu cầu chỉ giữ một số elements/attributes, hãy xây bộ lọc ở tầng event parsing/transform, kiểm tra names/values và output đúng schema.

## 11. Debug lỗi khi ghi XML

| Triệu chứng | Nguyên nhân có thể | Cách khắc phục |
| --- | --- | --- |
| `XMLStreamException` vì prefix chưa bind | Repairing=false nhưng namespace URI chưa có binding | `writeNamespace`/`writeDefaultNamespace` hoặc repairing=true |
| Element đúng tên nhưng sai namespace | Prefix/URI mapping không đúng | Parse lại và so expanded name |
| `IllegalStateException` khi ghi attribute | Ghi attribute sau khi đã ghi text/child | Viết attribute khi start tag còn mở |
| XML output không well-formed | Thứ tự event hoặc end tags sai | Cân bằng cấu trúc; parse output |
| Text chứa `&amp;amp;` | Đã escape thủ công rồi writer escape thêm | Truyền raw text vào writeCharacters |
| Attribute chứa ký tự lạ | Dùng raw markup hoặc code escape không đúng | Dùng writeAttribute, validate tên |
| CDATA làm XML hỏng | Text chứa chuỗi `]]>` | Dùng writeCharacters hoặc xử lý split CDATA |
| Namespace prefix ngẫu nhiên | Repairing=true có thể sinh prefix | So URI/local name, không hardcode raw output |
| Output chỉ có một phần | Chưa flush/close hoặc I/O lỗi | Ghi end document, flush/close, xử lý IOException |
| XML declaration encoding sai | Charset sink khác declaration | Tạo writer với UTF-8 thật, ghi declaration phù hợp |
| Ghi ra StringWriter rồi OOM | Giữ toàn bộ output trong RAM | OutputStream/Writer streaming và quota |
| SAX/DOM/JAXP Result chưa hỗ trợ | Optional provider feature | Dùng supported Writer/OutputStream overload |
| Event writer tạo XML khác cursor | Khác lexical serialization | So semantics sau parse |
| Event copy chứa DTD độc hại | Input factory insecure hoặc thiếu validation | Khóa DTD/entities, kiểm tra events |
| Writer close che lỗi write trước | finally cleanup exception | Giữ primary, add suppressed theo policy |
| Gửi XML tới path sai/quá quyền | Không validate output destination | Allowlist path, temp file/atomic publish |
| Provider mới cho output khác | JAXP service-provider resolution | Integration test trên JDK/provider deployed |

### 11.1. Debug theo trình tự

1. Xác định writer thực tế là **XMLStreamWriter** hay **XMLEventWriter** và provider nào từ factory.
2. Kiểm tra `IS_REPAIRING_NAMESPACES` cùng thời điểm cấu hình.
3. Kiểm tra mỗi element được mở/đóng đúng.
4. Kiểm tra attributes/namespaces được ghi trước character content.
5. Kiểm tra namespace URI và localName bằng một parser, không chỉ nhìn prefix.
6. Kiểm tra text/attribute escaping và encoding của sink.
7. Kiểm tra đã gọi writeEndDocument/createEndDocument rồi flush/close đúng.
8. Kiểm tra underlying output stream có được chủ sở hữu đóng không.
9. Nếu đọc XML đầu vào, kiểm tra XMLInputFactory DTD/XXE security.
10. Nếu lỗi chỉ xuất hiện với XML lớn, đo buffering, output quota, I/O timeouts.
11. Nếu lỗi khác nhau theo môi trường, so sánh provider/JDK versions và input/output encoding.
12. Nếu parser validation fail, giữ diagnostics an toàn, không log raw PII document.

## 12. Thiết kế test cho các XML writers

| Test | Kết quả mong đợi |
| --- | --- |
| Cursor writer cơ bản | Có XML declaration, root, child và end tags hợp lệ |
| Event writer cơ bản | Same XML semantics sau parse |
| Text có `<`, `>` và `&` | Escape khi serialize, roundtrip text gốc |
| Attribute chứa `&`/quote | Escape đúng, getAttributeValue trả giá trị gốc |
| Tiếng Việt và emoji | Không mất Unicode với UTF-8 |
| Empty element | Đếm đúng và parse được với 2 lexical forms |
| Prefix thủ công | `xmlns:p` hợp lệ khi repairing=false |
| Repairing namespaces=true | Expanded name đúng, không phụ thuộc generated prefix |
| Namespaced attribute | Đọc lại bằng URI/local name |
| Factory provider khác | Không assume raw serialization giống hệt |
| `writeCharacters` cho input chứa markup | Input được coi là text, không thành XML tags |
| Invalid element name | Policy validate hoặc parse lại bắt lỗi |
| CDATA chứa `]]>` | Application kiểm soát/từ chối/tách đúng |
| Comment `--` | Input validation chặn comment không hợp lệ |
| Encoding mismatch | Test phát hiện XML declaration khác bytes thật |
| `flush`/`close` | Output đầy đủ và underlying stream ownership đúng |
| I/O write fail giữa chừng | Dọn file dở, primary exception còn |
| Big payload | Memory/throughput phù hợp quota |
| EventReader→EventWriter pipeline | Copy event đúng và không mở XXE |
| Multiple threads | Không chia sẻ một mutable writer không được bảo đảm thread-safe |
| JAXP Result overload | Không assume provider bắt buộc hỗ trợ |

### 12.1. Kiểm thử semantic thay vì raw bytes

Khi nghiệp vụ quan tâm XML document data, hãy kiểm tra:

- Root localName + namespaceURI.
- Các child elements theo thứ tự có ý nghĩa.
- Attributes theo QName/namespace.
- Character text sau khi decode XML escaping.
- Số lượng elements và empty-element semantics.
- Whitespace khi schema có ý nghĩa.
- XML declaration/encoding contract, nếu quan trọng.
- Không chứa DTD/external entity theo policy.

Nếu cần **canonical byte representation** cho XML signature/hashing, chỉ parse-and-reserialize bằng StAX là không đủ. Phải định nghĩa XML canonicalization và chữ ký đúng chuẩn.

## 13. Bài tập tự luyện

1. Chạy chương trình, giải thích vì sao `sameSemantics=true` nhưng `differentSerialization=true` trên JDK đã thử.
2. Thêm `<p:price currency="VND">100</p:price>` bằng cả cursor và event writers rồi so sánh sau parse.
3. Thay TEXT bằng `Đặng & Lan <Tốt>`; xác minh escaping và roundtrip.
4. Thêm attribute value chứa double quote; kiểm tra `writeAttribute` escape.
5. Tắt repairing và cố ghi một namespaced attribute với URI chưa bind; ghi nhận XMLStreamException theo provider.
6. Bật repairing và so sánh **namespace URIs**, không dựa vào prefix được sinh.
7. Thử `writeEmptyElement` và một cặp `writeStartElement`/`writeEndElement`, so parse result.
8. Dùng `XMLEventFactory.createComment` và `createProcessingInstruction` với dữ liệu hợp lệ.
9. Tạo một event reader từ XML an toàn rồi dùng `XMLEventWriter.add(eventReader)`, parse lại output.
10. Thử `writeCharacters("<admin>true</admin>")` và xác minh không trở thành element admin.
11. Dùng OutputStream/Writer UTF-8 để ghi document ra temp file, so roundtrip với emoji.
12. Cố tình chọn một charset không khớp XML declaration rồi test parser báo lỗi hoặc nhận sai nội dung; không dùng dữ liệu production.
13. Gọi attribute method sau character data, quan sát exception trên provider được dùng.
14. Thiết kế một helper `writeXmlSafely(OutputStream, Consumer<XMLStreamWriter>)` có owner rõ ràng cho sink và xử lý cleanup failures.
15. Tạo document có nested elements, áp giới hạn độ sâu và số nodes được xuất.
16. Tạo một XML schema validation test riêng cho document output; nhớ writer không validate toàn bộ grammar.
17. Xử lý output file bằng temp rồi atomic rename khi filesystem hỗ trợ.
18. Dùng profiler so StringWriter với BufferedOutputStream cho XML lớn, ghi nhớ provider buffering.
19. Thử một JAXP provider khác và so semantics; không coi generated namespace prefix là cố định.
20. Viết unit test chống XXE cho input factory trước khi dùng event copy pipeline.

## 14. Checklist đưa vào production

- [ ] Sử dụng `XMLOutputFactory.newFactory()` hoặc `newDefaultFactory()` theo provider policy rõ ràng.
- [ ] Chọn XMLStreamWriter cho cursor-style; XMLEventWriter + XMLEventFactory cho event-style.
- [ ] Không sử dụng overload deprecated để tìm provider khi API hiện hành có thay thế.
- [ ] Cấu hình `IS_REPAIRING_NAMESPACES` trước khi tạo writer.
- [ ] Hiểu mặc định repairing=false và phải khai báo bindings hợp lệ.
- [ ] Kiểm tra namespace bằng URI + localName, không phụ thuộc raw prefix.
- [ ] Với attribute có namespace, dùng overload và prefix/repairing đúng.
- [ ] Cân bằng start/end elements, xử lý empty element đúng.
- [ ] Ghi attributes/namespaces trong start tag trước khi chuyển sang body.
- [ ] Ghi user text bằng `writeCharacters`/`createCharacters`, không nối XML raw.
- [ ] Không double-escape ký tự & hoặc markup characters.
- [ ] Validate XML names, comments, CDATA và processing instructions chưa được writer kiểm chứng đầy đủ.
- [ ] XML declaration encoding khớp charset sink thực tế.
- [ ] Đóng writer bằng close và flush khi cần; đóng underlying stream riêng.
- [ ] Không coi flush là fsync/durable storage hoặc close là commit.
- [ ] Xử lý I/O failure, cleanup failures và partial output.
- [ ] Có size/depth/attribute/event quotas và cancellation.
- [ ] Ghi file/response vào vùng được phép, dọn temp output khi lỗi.
- [ ] Nếu nhận input XML, khóa DTD/external entities và test security provider.
- [ ] Không dùng XMLEventWriter.add(XMLEventReader) như một sanitizer.
- [ ] Unit/integration test roundtrip semantic và exact bytes khi contract yêu cầu.
- [ ] Không suy performance hoặc serialization từ một provider sang mọi provider.
- [ ] Chỉ dựa vào kiến thức/API vẫn được hỗ trợ ở JDK hiện hành.

## Kết luận

**`XMLOutputFactory`** là entrypoint để cấu hình và tạo hai loại output writers của StAX. **`XMLStreamWriter`** ghi XML bằng các phương thức `write...` theo trạng thái con trỏ, thích hợp khi ứng dụng tự xây tài liệu. **`XMLEventWriter`** ghi bằng các `XMLEvent` từ `XMLEventFactory`, thích hợp cho event-oriented transformations và pipelines.

Cả hai đều cần **cấu trúc đúng, namespace bindings, escaping và encoding phù hợp**, đồng thời phải **flush/close đúng ownership**. Bật **`IS_REPAIRING_NAMESPACES`** giúp writer bổ sung/sửa namespace prefixes/declarations, nhưng không thay thế yêu cầu xác định đúng namespace URI/local names. Với dữ liệu ngoài đáng tin cậy, áp parser security trên chiều đọc; với dữ liệu xuất, kiểm tra XML bằng **roundtrip parse tests**.

**Tài liệu tham khảo chính thức, còn áp dụng:**

- [XMLOutputFactory — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/stream/XMLOutputFactory.html)
- [XMLOutputFactory — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLOutputFactory.html)
- [XMLStreamWriter — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/stream/XMLStreamWriter.html)
- [XMLEventWriter — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/stream/XMLEventWriter.html)
- [XMLEventFactory — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLEventFactory.html)
- [XMLEvent — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/events/XMLEvent.html)
- [XMLInputFactory — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/stream/XMLInputFactory.html)
- [XMLStreamReader — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/stream/XMLStreamReader.html)
- [XMLConstants — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/XMLConstants.html)
- [JAXP Security Guide — Java SE 17](https://docs.oracle.com/en/java/javase/17/security/java-api-xml-processing-jaxp-security-guide.html)