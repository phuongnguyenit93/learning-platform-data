# JSR 173 và xử lý XML theo mô hình pull với StAX (Java 17+)

## 1. StAX giải quyết vấn đề gì?

Khi làm việc với XML, ứng dụng có thể cần duyệt một tài liệu lớn nhưng chỉ lấy vài phần tử như mã sản phẩm, giá, tên sách hoặc một tập các giao dịch. Nếu luôn dựng toàn bộ cây DOM trước khi tìm dữ liệu, chương trình có thể dùng nhiều bộ nhớ không cần thiết. Nếu dùng SAX, parser liên tục **đẩy callbacks** tới application, khiến việc điều khiển luồng xử lý đôi khi khó theo dõi.

**StAX — Streaming API for XML** — cung cấp mô hình **pull parsing**: chính application gọi `next()` / `nextEvent()` để yêu cầu sự kiện XML tiếp theo, quyết định lúc nào đọc, cần giữ trạng thái nào, và khi nào có thể dừng. StAX cũng hỗ trợ **ghi XML tuần tự** bằng XMLStreamWriter hoặc XMLEventWriter.

StAX ra đời từ **JSR 173**, được phê duyệt năm 2004. JSR 173 có trạng thái **Withdrawn** trong JCP từ năm 2016 **vì không tiếp tục phân phối bản StAX standalone độc lập** sau khi công nghệ đã ổn định và được tích hợp vào nền tảng Java SE. Điều này **không có nghĩa API StAX bị loại bỏ hoặc deprecated**. Trong Java 17+ và Java SE 25, StAX vẫn nằm trong **module `java.xml`** và package **`javax.xml.stream`**, dùng bình thường mà không cần tải JAR StAX standalone đời cũ. JSR mang ý nghĩa **nguồn gốc và thiết kế API**; khi lập trình hiện tại, hãy theo **Javadoc Java SE**.

Những tình huống StAX phù hợp:

- Đọc nhiều phần tử lặp lại từ XML mà không cần giữ cả cây.
- Trích xuất một số trường và xử lý tuần tự theo thứ tự văn bản.
- Viết XML từ dữ liệu domain object theo thứ tự.
- Xử lý luồng XML theo nhu cầu ứng dụng: đọc một item, validate, xử lý/đưa sang consumer rồi đọc item tiếp.
- Tích hợp với `StAXSource`/`StAXResult` của JAXP hoặc thư viện hỗ trợ StAX.
- Kiểm soát parser và external resource policy trước khi parse dữ liệu không tin cậy.

**Ba phân biệt cốt lõi:** StAX là **pull** (ứng dụng lấy event), SAX là **push** (parser gọi handler), DOM là **tree model** (cấu trúc document đã materialize). StAX không phải ORM, không phải XML schema validator mặc định, và không tự bảo vệ khỏi XXE nếu factory/driver hoặc XML resolver được cấu hình không phù hợp.

## 2. Pull so với DOM và SAX

| Thuộc tính | DOM | SAX | StAX |
| --- | --- | --- | --- |
| Mô hình | Tạo cây `Document`/`Node` | Parser phát callbacks `ContentHandler` | Application yêu cầu event bằng `next` |
| Ai điều khiển event tiếp theo? | Không duyệt luồng trực tiếp; đã có cây | Parser chủ động gọi callback | **Application chủ động pull** |
| Bộ nhớ | Tỉ lệ với cây XML đã tạo | Thường nhỏ nếu handler không tích lũy | Thường nhỏ nếu caller xử lý/loại bỏ events |
| Random access / sửa node | Thuận tiện | Không, cần tự giữ trạng thái | Không, luồng tiến về phía trước |
| Đọc một phần rồi dừng | Có thể sau khi đã parse toàn bộ | Cần thiết kế abort callback | Có thể ngừng gọi `next()`, đóng reader/source |
| Kết hợp với business loop | Duyệt cây có sẵn | Code business chia vào callbacks | Dễ viết vòng `while` hoặc helper đọc sub-element |
| Bảo mật | Phụ thuộc DOM parser factory | Phụ thuộc SAX parser factory | Phụ thuộc StAX input factory và resolver |
| Ghi XML | DOM+Transformer, DOM APIs | SAX event producer/Result | `XMLStreamWriter` / `XMLEventWriter` |
| Chi phí bộ nhớ thực | Cây + dữ liệu | Parser + dữ liệu handler lưu | Parser + dữ liệu application tích lũy |

**Không tuyên bố StAX luôn O(1) bộ nhớ trong mọi ứng dụng.** Nếu parser ở chế độ stream và application chỉ giữ một số trạng thái nhỏ, memory thường gần với độ sâu XML/các buffer; nhưng nếu gọi `getElementText()` trên phần tử chứa hàng trăm MB text, hoặc đưa tất cả parsed objects vào `ArrayList`, bộ nhớ vẫn tăng. DTD/entity expansion, driver buffering và provider implementation cũng ảnh hưởng. Phải đặt giới hạn input và đo bằng workload thật.

### Dòng xử lý pull

~~~text
Nguồn XML (Reader / InputStream)
         │
         ▼
XMLInputFactory đã cấu hình
         │
         ▼
XMLStreamReader  (đang ở START_DOCUMENT)
         │
         ├── app: hasNext()?
         ├── app: next() -> START_ELEMENT <book>
         ├── app: đọc localName, namespace, attributes
         ├── app: next() -> CHARACTERS / START_ELEMENT ...
         ├── app: xử lý một bản ghi
         └── app: tiếp tục hoặc dừng và close()
~~~

**Lợi thế về cấu trúc code:** trạng thái parse có thể ở trong biến cục bộ hoặc một state machine tuần tự, không bắt buộc trải ra các callback methods. Nhưng bạn phải chủ động xử lý nested elements, whitespace, namespaces, DTD/security và kết thúc stream — parser không tự chuyển XML tùy ý thành domain object.

## 3. Các interface StAX còn dùng trong Java 17+

| Loại | Java API | Vai trò |
| --- | --- | --- |
| Factory đọc | `XMLInputFactory` | Tạo stream/event readers từ nguồn XML |
| Cursor reader | `XMLStreamReader` | API forward-only, truy cập **current event** qua các getters |
| Event reader | `XMLEventReader` | API iterator trả các `XMLEvent` objects |
| Factory ghi | `XMLOutputFactory` | Tạo stream/event writers |
| Cursor writer | `XMLStreamWriter` | Ghi document, elements, attributes, namespaces, text |
| Event writer | `XMLEventWriter` | Thêm `XMLEvent` events vào output |
| Event models | `XMLEvent`, `StartElement`, `EndElement`, `Characters`, `Attribute` | Object mô tả các sự kiện XML |
| Event factory | `XMLEventFactory` | Tạo events để đưa cho `XMLEventWriter` |
| Common constants | `XMLStreamConstants` | `START_DOCUMENT`, `START_ELEMENT`, `CHARACTERS`, `END_ELEMENT`, ... |
| Failure | `XMLStreamException` | Lỗi parsing, XML không well-formed, unsupported constraints |
| Resolver | `XMLResolver` | Quy định cách resolve XML resources; phải kiểm soát external access |
| Warning reporter | `XMLReporter` | Callback báo các non-fatal errors/warnings theo provider |

Các API này nằm trong `java.xml`, không phải một `javax.xml.stream` library ngoại vi cần thêm từ Maven cho ứng dụng Java 17+ thông thường. Tên package **`javax.xml.stream` vẫn đúng trong Java SE 25**; không đổi máy móc sang `jakarta.xml.stream`.

Factory minh họa:

~~~java
XMLInputFactory inputFactory = XMLInputFactory.newFactory();
XMLStreamReader stream = inputFactory.createXMLStreamReader(reader);
~~~

Đây là đoạn **trong method** với `java.io.Reader reader` đã mở, cần import `javax.xml.stream.*` và xử lý `XMLStreamException`. **Không dùng factory mặc định này cho XML không tin cậy mà chưa cấu hình security**. Trong ví dụ chạy đầy đủ bên dưới, ta dùng factory có policy explicit: disable DTD, external entities và external DTD access.

### `newFactory()` và `newDefaultFactory()`

`XMLInputFactory.newFactory()` có thể chọn implementation qua JAXP lookup/service provider rules, phù hợp khi application cho phép một StAX provider khác ngoài JDK. `XMLInputFactory.newDefaultFactory()` yêu cầu implementation mặc định built-in của JDK, tránh phụ thuộc provider discovery khi muốn đường đi rõ hơn. Cả hai là cách tạo API factory hiện đại, nhưng **không phải một giấy chứng nhận parser đã an toàn**; application vẫn phải cấu hình và kiểm tra chính xác những properties cần thiết.

Tương tự, `XMLOutputFactory.newFactory()` và `newDefaultFactory()` dùng để tạo writer factory. Không hardcode class nội bộ `com.sun.xml.internal.*` hoặc cố tải StAX standalone JAR lỗi thời: các class internal không phải public contract được hỗ trợ.

## 4. Cursor API: `XMLStreamReader` và current event

Với `XMLStreamReader`, reader mới tạo thường ở sự kiện **`START_DOCUMENT`**. Hầu hết thông tin được hỏi từ **current event**; lời gọi `next()` chuyển sang event kế tiếp và trả loại của event đó.

~~~java
XMLStreamReader xml = factory.createXMLStreamReader(reader);
try {
    System.out.println(xml.getEventType() == XMLStreamConstants.START_DOCUMENT);

    while (xml.hasNext()) {
        int event = xml.next();
        switch (event) {
            case XMLStreamConstants.START_ELEMENT -> {
                System.out.println(xml.getLocalName());
            }
            case XMLStreamConstants.CHARACTERS -> {
                System.out.println(xml.getText());
            }
            case XMLStreamConstants.END_ELEMENT -> {
                System.out.println("/" + xml.getLocalName());
            }
            default -> { /* Có thể là COMMENT, PI, DTD, SPACE... */ }
        }
    }
} finally {
    xml.close();
}
~~~

Đây là **đoạn minh họa trong method** với `factory` đã cấu hình và `reader` còn mở, không phải file Java độc lập. Reader chỉ tiến về phía trước; bạn không thể `previous()` để quay về event cũ.

**Trạng thái trước và sau `next()`:** khi gọi `xml.next()`, current event đã thay đổi. Các getter như `getLocalName()` hoặc `getAttributeCount()` chỉ hợp lệ ở các event types phù hợp; gọi chúng khi đứng ở `CHARACTERS` có thể ném `IllegalStateException`. Khi muốn đọc attributes, xử lý **ngay ở START_ELEMENT**, trước khi gọi next lần nữa.

### Những event types cơ bản

| Event | Khi xuất hiện | Nên đọc gì? |
| --- | --- | --- |
| `START_DOCUMENT` | Bắt đầu văn bản | Encoding/version nếu được provider cung cấp |
| `START_ELEMENT` | Thẻ mở `<book>` | `getName`, `getLocalName`, `getNamespaceURI`, attributes |
| `CHARACTERS` | Text giữa các tags | `getText`, `isWhiteSpace` |
| `SPACE` | Whitespace được báo riêng khi phù hợp | Có thể bỏ qua nếu schema cho phép |
| `CDATA` | Một CDATA section, tùy coalescing/parser | `getText` |
| `END_ELEMENT` | Thẻ đóng `</book>` | `getLocalName`, namespace |
| `COMMENT` | XML comment | Chỉ xử lý nếu nghiệp vụ cần |
| `PROCESSING_INSTRUCTION` | Processing instruction | Chỉ chấp nhận nếu cần và được validate |
| `DTD` | DTD declaration | Thường **từ chối** cho XML untrusted |
| `ENTITY_REFERENCE` | Tham chiếu entity (tùy cấu hình) | Không tự resolve external entities |
| `END_DOCUMENT` | Cuối tài liệu | Kết thúc parse |

Trên một số implementations, adjacent text có thể được chia thành nhiều sự kiện `CHARACTERS`; không giả định “mỗi element luôn có đúng một CHARACTERS event”. `XMLInputFactory.IS_COALESCING` có thể thay hành vi gộp text/CDATA, nhưng **không thay** việc element có nested children hay attribute/namespace.

### `getElementText()` cho phần tử chỉ chứa text

Khi current event là `START_ELEMENT` của một element không chứa nested element, có thể gọi:

~~~java
if (xml.getEventType() == XMLStreamConstants.START_ELEMENT
        && "title".equals(xml.getLocalName())) {
    String title = xml.getElementText();
    // Current event bây giờ ở END_ELEMENT của <title>.
}
~~~

`getElementText()` đọc nội dung text và gộp các text sections thành một `String`. Nó **yêu cầu current event là START_ELEMENT**; sau lời gọi thành công, reader đứng tại **END_ELEMENT tương ứng**. Nếu bên trong có nested START_ELEMENT, method sẽ ném `XMLStreamException` vì element không còn text-only. Nếu text quá lớn, `getElementText()` materialize cả nội dung vào String; khi cần giới hạn memory, duyệt `CHARACTERS` theo chunks với limit.

**Bẫy điều khiển cursor:** không gọi thêm `next()` vô điều kiện sau `getElementText()` nếu vòng lặp bên ngoài cũng sẽ tự next; bạn có thể bỏ qua sự kiện quan trọng. Trong ví dụ đầy đủ, helper loop đã biết `getElementText()` tiêu thụ đến END_ELEMENT và sau đó tiếp tục đúng chỗ.

### `nextTag()` khác `next()`

~~~java
int type = xml.nextTag();
if (type == XMLStreamConstants.START_ELEMENT) {
    String name = xml.getLocalName();
}
~~~

`nextTag()` bỏ qua whitespace text, comment và processing instruction được phép để tìm **START_ELEMENT** hoặc **END_ELEMENT** kế tiếp. Nếu gặp text **không phải whitespace** (nội dung hỗn hợp), nó có thể ném `XMLStreamException`; không dùng `nextTag()` cho mọi vị trí khi XML có free-form prose.

`next()` tổng quát hơn, dùng khi phải đọc text/CDATA/processing instructions, hoặc khi cần tự kiểm tra DTD. Cả `next()` và `nextTag()` đều có thể chạm lỗi XML malformed hoặc disallowed external content khi parser đọc thêm.

### Attributes chỉ đọc trên START_ELEMENT

~~~java
if (xml.getEventType() == XMLStreamConstants.START_ELEMENT) {
    String id = xml.getAttributeValue(null, "id");
    for (int i = 0; i < xml.getAttributeCount(); i++) {
        System.out.println(xml.getAttributeLocalName(i) + "="
                + xml.getAttributeValue(i));
    }
}
~~~

Đây là đoạn minh họa trong method có `xml`. `getAttributeValue(null, "id")` lấy attribute **không thuộc namespace** có local name `id`; nó **không phải** nội dung `<id>...</id>`. Với attribute có namespace, truyền đúng URI namespace. Một default namespace khai báo cho element **không tự áp vào unprefixed attributes** theo XML Namespaces.

## 5. Namespace và XML name: prefix không phải identity

Giả sử:

~~~xml
<catalog xmlns="urn:demo:catalog">
  <book id="b1">
    <title>Java &amp; XML</title>
  </book>
</catalog>
~~~

Với namespace-aware parser:

- `getLocalName()` trên `<book>` là `"book"`.
- `getNamespaceURI()` là `"urn:demo:catalog"`.
- `getPrefix()` thường là `""` hoặc thông tin prefix tương ứng.
- `getAttributeValue(null, "id")` trả `"b1"` vì attribute `id` không thuộc namespace.
- Text của title khi parse ra là `"Java & XML"`; entity predefined `&amp;` đã biến thành ký tự `&`.
- Không kiểm tra namespace bằng cách so prefix literal `c` hay `ns1`: prefix có thể khác mà XML semantics vẫn tương đương.

Nếu XML được viết lại:

~~~xml
<c:catalog xmlns:c="urn:demo:catalog">
  <c:book id="b1"><c:title>Java &amp; XML</c:title></c:book>
</c:catalog>
~~~

Application nên nhận ra cùng cấu trúc khi **localName + namespace URI** khớp, dù prefix thay đổi. `QName` biểu diễn tên có namespace; đối với StAX event API dùng `StartElement.getName()` để nhận `QName`.

**Không** tắt namespace-awareness chỉ để tiện so tên `"book"` nếu dữ liệu có namespaces quan trọng. Một payload có cùng localName nhưng namespace độc hại/khác business schema có thể không hợp lệ.

### Cây đơn giản nhưng có child elements lồng nhau

Với XML:

~~~xml
<book xmlns="urn:demo:catalog">
  <title><em>Java</em> &amp; XML</title>
</book>
~~~

`getElementText()` **không phù hợp** để đọc title vì có child `<em>`. Cần một state machine theo **độ sâu phần tử**, hoặc một parser hỗ trợ mixed content. Không bắt `XMLStreamException` rồi bỏ qua nested children nếu yêu cầu nghiệp vụ phải giữ đúng nội dung văn bản.

## 6. `XMLEventReader`: pull events như các objects

Bên cạnh cursor API, `XMLEventReader` trả từng `XMLEvent`:

~~~java
XMLEventReader events = factory.createXMLEventReader(reader);
try {
    while (events.hasNext()) {
        XMLEvent event = events.nextEvent();
        if (event.isStartElement()) {
            StartElement start = event.asStartElement();
            System.out.println(start.getName().getLocalPart());
        }
    }
} finally {
    events.close();
}
~~~

Đây là đoạn minh họa trong method cần import `XMLEventReader`, `XMLEvent`, `StartElement` và có `factory` đã harden, `Reader reader` còn mở. Các event objects cho phép code chuyển event sang consumer khác hoặc kiểm tra thêm metadata như namespace/attribute khi đúng event type.

### Cursor API và event API khác gì?

| `XMLStreamReader` | `XMLEventReader` |
| --- | --- |
| Getter nhìn vào **current event** của parser | `nextEvent()` trả object biểu diễn event |
| `getEventType()`/`next()` | `peek()`, `nextEvent()`, `nextTag()` |
| Thường ít object allocation hơn với cursor style | Thường dễ truyền event object qua layers |
| Phải đọc attributes/text trước khi reader chuyển current event | Có thể thao tác event đã lấy theo contract của event object |
| Hợp loop hiệu năng cao và state machine | Hợp event processing, filtering/transform pipelines |

Không khẳng định event API “bao giờ cũng chậm hơn đúng N lần”: phụ thuộc implementation và workload. Lựa chọn theo độ rõ code và phép đo thật.

### `peek()` và `nextEvent()`

`peek()` cho phép nhìn **next event** mà chưa consume, hữu ích khi muốn quyết định parse tiếp. `nextEvent()` consume và trả event; `hasNext()` kiểm tra sự kiện còn lại. `XMLEventReader.nextTag()` bỏ qua một số ignorable events và trả next start/end element, nhưng vẫn có thể ném XMLStreamException khi gặp non-whitespace text.

Với `XMLEventReader`, `event.asStartElement().getAttributeByName(new QName("id"))` có thể đọc attribute `id`. `new QName("id")` tạo QName không có namespace; nếu attribute có namespace, phải chỉ định namespace URI. `event.asCharacters().getData()` lấy text của một `Characters` event; nhiều text events liên tiếp vẫn có thể cần ghép có kiểm soát.

### Khi chọn mô hình nào?

Nếu chỉ muốn stream qua hàng triệu `<record>`, dùng `XMLStreamReader` thường dễ tránh nhiều allocations. Nếu cần chuyển/ghi events, tạo pipeline hoặc kết hợp `XMLEventWriter`, `XMLEventReader` hữu ích. **Hai API đều là pull**, không phải SAX callbacks.

## 7. Chương trình Java 17+ hoàn chỉnh: đọc, ghi, round-trip và chặn DTD

Ví dụ sau là **một file Java chạy được** chỉ với JDK 17+; không cần Maven, database, mạng hoặc thư viện XML bên ngoài. Chương trình dùng:

1. `XMLInputFactory.newDefaultFactory()` với namespace-aware, `SUPPORT_DTD=false`, `IS_SUPPORTING_EXTERNAL_ENTITIES=false`, `ACCESS_EXTERNAL_DTD=""`, và resolver từ chối external XML resources.
2. `XMLStreamReader` duyệt catalog XML, đọc `book`/`title`/`price`, lấy thuộc tính `id`/`currency` và chuyển `BigDecimal`.
3. `XMLEventReader` đếm số `book` START_ELEMENT events.
4. `XMLOutputFactory.newDefaultFactory()` và `XMLStreamWriter` ghi lại XML, escape `&` đúng quy tắc, khai báo namespace.
5. Đọc lại XML vừa ghi và xác nhận giá trị domain objects không đổi.
6. Thử một payload có `DOCTYPE`/external entity; parser cấu hình an toàn hoặc kiểm tra DTD event sẽ từ chối.

**Hạn chế của demo:** input XML là trusted literal trong source, nên không cần reader giới hạn kích thước. Đối với untrusted input production phải có **payload-size, nesting-depth, item-count và text-length limits**; ví dụ không chứng minh mọi parser provider đều có cơ chế chặn DTD y hệt, chỉ kiểm chứng built-in provider của JDK đã chạy. Mọi xử lý XML outside JDK boundaries phải kiểm tra thêm.

Tạo file **`StaxPullDemo.java`** với mã Java 17 sau:

~~~java
import java.io.StringReader;
import java.io.StringWriter;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import javax.xml.XMLConstants;
import javax.xml.stream.XMLEventReader;
import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLOutputFactory;
import javax.xml.stream.XMLStreamConstants;
import javax.xml.stream.XMLStreamException;
import javax.xml.stream.XMLStreamReader;
import javax.xml.stream.XMLStreamWriter;
import javax.xml.stream.events.XMLEvent;

public final class StaxPullDemo {
    private static final String NS = "urn:demo:catalog";
    private static final String INPUT = """
            <?xml version="1.0" encoding="UTF-8"?>
            <catalog xmlns="urn:demo:catalog">
              <book id="b1">
                <title>Java &amp; XML</title>
                <price currency="USD">12.50</price>
              </book>
              <book id="b2">
                <title>Ti\u1EBFng Vi\u1EC7t \uD83D\uDE00</title>
                <price currency="VND">99</price>
              </book>
            </catalog>
            """;
    record Book(String id, String title, BigDecimal price, String currency) {}

    static XMLInputFactory secureInputFactory() {
        XMLInputFactory factory = XMLInputFactory.newDefaultFactory();
        factory.setProperty(XMLInputFactory.IS_NAMESPACE_AWARE, true);
        factory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
        factory.setProperty(XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setXMLResolver((publicId, systemId, baseUri, namespace) -> {
            throw new XMLStreamException("External XML resolution blocked");
        });
        return factory;
    }

    static List<Book> readBooks(String xml) throws XMLStreamException {
        List<Book> books = new ArrayList<>();
        try (StringReader source = new StringReader(xml)) {
            XMLStreamReader reader = secureInputFactory().createXMLStreamReader(source);
            try {
                while (reader.hasNext()) {
                    int type = reader.next();
                    if (type == XMLStreamConstants.DTD) {
                        throw new XMLStreamException("DOCTYPE is not allowed");
                    }
                    if (type == XMLStreamConstants.START_ELEMENT
                            && NS.equals(reader.getNamespaceURI())
                            && "book".equals(reader.getLocalName())) {
                        String id = reader.getAttributeValue(null, "id");
                        String title = null;
                        String currency = null;
                        BigDecimal price = null;

                        while (reader.hasNext()) {
                            type = reader.next();
                            if (type == XMLStreamConstants.DTD) {
                                throw new XMLStreamException("DOCTYPE is not allowed");
                            }
                            if (type == XMLStreamConstants.START_ELEMENT
                                    && NS.equals(reader.getNamespaceURI())) {
                                if ("title".equals(reader.getLocalName())) {
                                    title = reader.getElementText();
                                } else if ("price".equals(reader.getLocalName())) {
                                    currency = reader.getAttributeValue(null, "currency");
                                    price = new BigDecimal(reader.getElementText());
                                }
                            } else if (type == XMLStreamConstants.END_ELEMENT
                                    && "book".equals(reader.getLocalName())
                                    && NS.equals(reader.getNamespaceURI())) {
                                break;
                            }
                        }
                        if (title == null || price == null || currency == null) {
                            throw new XMLStreamException("Book missing required data");
                        }
                        books.add(new Book(id, title, price, currency));
                    }
                }
            } finally {
                reader.close();
            }
        }
        return books;
    }

    static int countBooksWithEvents(String xml) throws XMLStreamException {
        int books = 0;
        try (StringReader source = new StringReader(xml)) {
            XMLEventReader reader = secureInputFactory().createXMLEventReader(source);
            try {
                while (reader.hasNext()) {
                    XMLEvent event = reader.nextEvent();
                    if (event.getEventType() == XMLStreamConstants.DTD) {
                        throw new XMLStreamException("DOCTYPE is not allowed");
                    }
                    if (event.isStartElement()
                            && NS.equals(event.asStartElement()
                                    .getName().getNamespaceURI())
                            && "book".equals(event.asStartElement()
                                    .getName().getLocalPart())) {
                        books++;
                    }
                }
            } finally {
                reader.close();
            }
        }
        return books;
    }

    static String writeBooks(List<Book> books) throws XMLStreamException {
        StringWriter text = new StringWriter();
        XMLStreamWriter writer = XMLOutputFactory.newDefaultFactory()
                .createXMLStreamWriter(text);
        try {
            writer.writeStartDocument();
            writer.setPrefix("c", NS);
            writer.writeStartElement("c", "catalog", NS);
            writer.writeNamespace("c", NS);

            for (Book book : books) {
                writer.writeStartElement("c", "book", NS);
                writer.writeAttribute("id", book.id());

                writer.writeStartElement("c", "title", NS);
                writer.writeCharacters(book.title());
                writer.writeEndElement();

                writer.writeStartElement("c", "price", NS);
                writer.writeAttribute("currency", book.currency());
                writer.writeCharacters(book.price().toPlainString());
                writer.writeEndElement();

                writer.writeEndElement();
            }
            writer.writeEndElement();
            writer.writeEndDocument();
            writer.flush();
        } finally {
            writer.close();
        }
        return text.toString();
    }

    public static void main(String[] args) throws XMLStreamException {
        List<Book> books = readBooks(INPUT);
        System.out.println("stream books: " + books.size());
        System.out.println("first id: " + books.get(0).id());
        System.out.println("first title: " + books.get(0).title());
        System.out.println("second unicode exact: "
                + "Ti\u1EBFng Vi\u1EC7t \uD83D\uDE00".equals(books.get(1).title()));
        System.out.println("event reader books: " + countBooksWithEvents(INPUT));

        String serialized = writeBooks(books);
        System.out.println("escaped ampersand: " + serialized.contains("&amp;"));
        System.out.println("writer round-trip: "
                + books.equals(readBooks(serialized)));

        String dangerous = "<!DOCTYPE catalog [<!ENTITY xxe SYSTEM "
                + "\"file:///dont-read-secret.txt\">]>"
                + "<catalog xmlns=\"urn:demo:catalog\">&xxe;</catalog>";
        boolean blocked = false;
        try {
            readBooks(dangerous);
        } catch (XMLStreamException securityRejection) {
            blocked = true;
        }
        System.out.println("DOCTYPE blocked: " + blocked);
    }
}
~~~

Lệnh biên dịch/chạy, trong thư mục có `StaxPullDemo.java`:

~~~bash
javac --release 17 StaxPullDemo.java
java StaxPullDemo
~~~

**Stdout chính xác**, đã biên dịch và chạy bằng **OpenJDK 24.0.2** với target `--release 17`:

~~~text
stream books: 2
first id: b1
first title: Java & XML
second unicode exact: true
event reader books: 2
escaped ampersand: true
writer round-trip: true
DOCTYPE blocked: true
~~~

### Giải thích kết quả và tài nguyên

- Parser đọc hai phần tử `book`, nên `stream books: 2`. `record Book` dùng Java record hỗ trợ từ Java 16, hợp lệ với Java 17+.
- `first title: Java & XML` chứng minh `getElementText()` đọc văn bản từ `&amp;` thành `&`.
- `second unicode exact: true` kiểm tra Java `String.equals` với tiếng Việt và emoji U+1F600, không phụ thuộc terminal có hiển thị glyph đúng không.
- `event reader books: 2` xác nhận event API duyệt cùng nội dung mà không dùng DOM.
- `escaped ampersand: true` xác nhận XMLStreamWriter escape `&` khi ghi text; không nối raw XML.
- `writer round-trip: true` chứng minh danh sách record sau khi ghi/đọc lại vẫn bằng danh sách ban đầu. Đây là phép thử **giá trị application**, không phải so raw bytes hay XML declaration.
- `DOCTYPE blocked: true` xác nhận payload DTD được từ chối ở **đường code chạy trên JDK được kiểm thử**. Parser do ứng dụng cấu hình không cho external resource, đồng thời code từ chối event DTD.
- `XMLStreamReader.close()` và `XMLEventReader.close()` giải phóng tài nguyên **bên trong reader**, nhưng **không bảo đảm đóng `Reader`/`InputStream` bên ngoài**. Ví dụ dùng `try (StringReader source = ...)` để sở hữu cả nguồn.
- `XMLStreamWriter.close()` đóng writer StAX; nguồn `StringWriter` được giữ lại để đọc kết quả. Với `OutputStream`/`Writer` thật, ownership/flush/close của underlying stream cần làm rõ.
- Fake XML không có network và không cần SQL; kiểm thử production phải giới hạn input size/depth và cùng StAX provider đang triển khai.
- `new BigDecimal(reader.getElementText())` trong ví dụ có thể ném `NumberFormatException` nếu price không hợp lệ. Production cần validate numeric format, range, currency và biến lỗi thành phản hồi có ngữ cảnh mà không rò rỉ dữ liệu XML nhạy cảm.

**Giới hạn quan trọng của parser này:** Khi gặp một `<book>` lồng nhiều levels hoặc unexpected children, vòng lặp inner này chưa phải một strict schema validator và không kiểm tra maximum depth, duplicate IDs, nhiều title/price hoặc content model. Đây là ví dụ StAX cơ bản, không phải parser cho XML tùy ý/độc hại. Một hệ thống thật phải xác thực namespaces, element order, multiplicity và schema/domain constraints.

## 8. StAX writer và `XMLOutputFactory`

StAX không chỉ đọc pull; nó còn cung cấp API **ghi XML có cấu trúc**. `XMLStreamWriter` giúp tạo elements, attributes, namespaces, character data và comment/processing instruction khi cần.

Ví dụ tách nhỏ:

~~~java
XMLStreamWriter writer = outputFactory.createXMLStreamWriter(output);
try {
    writer.writeStartDocument();
    writer.writeStartElement("message");
    writer.writeAttribute("lang", "vi");
    writer.writeStartElement("text");
    writer.writeCharacters("Xin chào & tạm biệt");
    writer.writeEndElement();
    writer.writeEndElement();
    writer.writeEndDocument();
    writer.flush();
} finally {
    writer.close();
}
~~~

Đây là **đoạn minh họa trong method** với `outputFactory` và `output` đã được cung cấp, cần imports và xử lý `XMLStreamException`. `writeCharacters` escape các ký tự đặc biệt trong text, còn `writeAttribute` escape nội dung attribute theo XML rules của writer. **Không nối các giá trị user input trực tiếp thành chuỗi XML markup**.

### Namespace khi ghi XML

StAX writer có nhiều overload:

~~~java
writer.setPrefix("c", "urn:demo:catalog");
writer.writeStartElement("c", "catalog", "urn:demo:catalog");
writer.writeNamespace("c", "urn:demo:catalog");
writer.writeEndElement();
~~~

Như trong demo, code **khai báo namespace** cho prefix dùng trong element. `setPrefix` thiết lập mapping trên writer, còn `writeNamespace` ghi XML namespace declaration vào output theo API. Không giả định việc đặt prefix trong internal namespace context luôn tự in `xmlns:c` theo mọi writer/configuration. `XMLOutputFactory.IS_REPAIRING_NAMESPACES` là property liên quan namespace repair; nếu bật, writer có thể tự tạo/bổ sung declarations tùy implementation. Không dựa vào prefix textual cố định để xác minh XML semantics sau serialize: kiểm tra URI và local name khi parse lại.

### `XMLEventWriter` và `XMLEventFactory`

Khi application đã có các `XMLEvent` objects, có thể viết bằng event writer:

~~~java
XMLEventFactory eventFactory = XMLEventFactory.newFactory();
XMLEventWriter eventWriter = outputFactory.createXMLEventWriter(output);
try {
    eventWriter.add(eventFactory.createStartDocument());
    eventWriter.add(eventFactory.createStartElement("", "", "message"));
    eventWriter.add(eventFactory.createCharacters("Xin chào"));
    eventWriter.add(eventFactory.createEndElement("", "", "message"));
    eventWriter.add(eventFactory.createEndDocument());
    eventWriter.flush();
} finally {
    eventWriter.close();
}
~~~

Đoạn này là **minh họa** với `outputFactory`/`output` hợp lệ và imports tương ứng. `XMLEventWriter.add(XMLEventReader)` cũng hữu ích cho một số event-copy pipelines, nhưng phải chú ý ownership readers/writers, namespaces, external entities và event filters. Chuyển nguyên events từ XML không tin cậy sang output **không tự làm sạch dữ liệu nghiệp vụ hoặc bảo đảm policy XML**.

### Serialization không đồng nghĩa canonicalization

`XMLStreamWriter` có thể thay đổi XML declaration, quote style, whitespace hoặc namespace prefixes mà vẫn biểu diễn cùng dữ liệu XML. Không so serialized bytes bằng `String.equals` nếu yêu cầu là semantics; hãy parse lại và so XML structure/text/QNames. Nếu XML được **ký số**, cần một canonical XML algorithm và XML signature security model được thiết kế riêng; `XMLStreamWriter` không phải một công cụ canonicalization tự động.

## 9. Bảo mật StAX hiện đại: DTD, XXE, SSRF và giới hạn tài nguyên

**XML parse là một boundary bảo mật.** XML từ upload, request, message queue, database hoặc filesystem có thể chứa references tới tài nguyên khác. Nếu external entity resolution không bị hạn chế, parser có thể đọc local files hoặc gửi requests tới mạng nội bộ (XXE/SSRF).

### Tạo input factory với policy rõ ràng

Trong ví dụ runnable:

~~~java
XMLInputFactory factory = XMLInputFactory.newDefaultFactory();
factory.setProperty(XMLInputFactory.IS_NAMESPACE_AWARE, true);
factory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
factory.setProperty(XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
factory.setXMLResolver((publicId, systemId, baseUri, namespace) -> {
    throw new XMLStreamException("External XML resolution blocked");
});
~~~

Các lựa chọn:

- `SUPPORT_DTD=false`: không cho provider xử lý DTD theo policy của factory. Một số providers vẫn có thể báo DTD event hoặc throw lỗi khi gặp DTD.
- `IS_SUPPORTING_EXTERNAL_ENTITIES=false`: tắt việc hỗ trợ external parsed entities.
- `XMLConstants.ACCESS_EXTERNAL_DTD=""`: không cho phép protocol ngoài cho DTD/external entities. Trong JAXP hiện đại đây là property cần hỗ trợ; thiết lập rõ ràng để tránh phụ thuộc defaults.
- `XMLResolver`: resolver tùy chỉnh ở ví dụ **ném exception nếu bị yêu cầu resolve**, ngăn application cung cấp external content.
- Ở vòng `next()`/`nextEvent()`, ứng dụng kiểm tra và từ chối `XMLStreamConstants.DTD` như một **defense in depth**.

Nếu provider ném `IllegalArgumentException` vì không hỗ trợ một security property cần thiết, **fail closed**: từ chối parse XML không tin cậy, không catch rồi dùng parser chưa harden. Hãy kiểm thử với StAX provider/version mà sản phẩm triển khai; việc chọn `newDefaultFactory` giúp ví dụ dùng implementation mặc định, không bảo đảm phù hợp mọi third-party provider.

**Không** coi riêng `SUPPORT_DTD=false` là bằng chứng mọi đường external resource đã bị vô hiệu hóa. Security posture phải xét cả external entities, XMLResolver và system/JAXP policy. Trong các hệ thống có resource catalogs được quản lý, resolver có thể cung cấp nội dung ngoại lai được allowlist; chính resolver cần có policy rõ.

### Vì sao `FEATURE_SECURE_PROCESSING` không phải cài đặt chính của StAX?

Các parser DOM/SAX hoặc JAXP Transformer có `XMLConstants.FEATURE_SECURE_PROCESSING`; **StAX XMLInputFactory không có cơ chế tương đương bắt buộc cùng cách đó**. Hãy dùng các **StAX properties đúng** như `SUPPORT_DTD`, `IS_SUPPORTING_EXTERNAL_ENTITIES` và `ACCESS_EXTERNAL_DTD`. Nếu ứng dụng dùng cả DOM, SAX, XSLT và StAX, hãy cấu hình từng loại factory riêng, không copy-paste một option rồi nghĩ tất cả parsers an toàn.

StAX cho phép XMLInputFactory tạo parser ở bước đầu; **cần khóa trước khi tạo XMLStreamReader/XMLEventReader**. Nếu một thư viện nhận XMLInputFactory từ bên ngoài hoặc trả XMLStreamReader đã tạo sẵn, việc cấu hình một factory khác sau đó không “sửa lại” parser đã parse.

### Giới hạn kích thước và tài nguyên

Ngay cả khi XML không có DTD, input vẫn có thể làm chương trình hao RAM/CPU:

- XML rất dài hoặc một text node có kích thước lớn khiến `getElementText()` tạo một String khổng lồ.
- XML lồng nhau rất sâu, gây độ sâu trạng thái lớn hoặc lỗi khi xử lý nested content.
- Hàng triệu `<book>` khiến `ArrayList<Book>` chiếm RAM, dù parser xử lý từng event nhỏ.
- Tên element, attributes hoặc namespace declarations cực lớn có thể tiêu tốn bộ nhớ.
- Input compressed (zip/gzip) có thể mở rộng vượt giới hạn sau giải nén.
- XML có DTD/entity expansion có thể gây entity bomb nếu parser chưa khóa.
- Parser có thể đọc dữ liệu từ network streams; request deadline và cancellation phải phối hợp với I/O timeout.

Production cần đặt **giới hạn byte/character count ở input boundary**, giới hạn **số elements**, **độ sâu**, **số attributes**, **độ dài text**, **số domain records**, và có **deadline**. Oracle JAXP Security Guide mô tả thêm implementation limits và system properties; dùng những hạn mức theo JDK/provider đang chạy và không trông chờ mọi provider hỗ trợ cùng tên property.

### Không tin dữ liệu đã qua StAX là hợp lệ nghiệp vụ

StAX là streaming XML parser, không phải XSD validator mặc định. Nó có thể xác nhận document well-formed khi đọc đến hết và báo lỗi parsing, nhưng **không** mặc nhiên xác nhận:

- Document hợp với XSD/schema mong muốn.
- Có đúng một root theo business contract, đúng namespace/version.
- Trường tiền nằm trong khoảng hợp lệ, currency thuộc danh sách được phép.
- IDs không trùng, không thiếu required children.
- Không có phần tử lạ hoặc một `<book>` bị nested theo cách business không chấp nhận.
- Không có nội dung HTML/script gây XSS khi dữ liệu XML được đưa lên web.

Muốn XSD validation, dùng `SchemaFactory`/`Validator` theo JAXP với security policy phù hợp, hoặc một **streaming validation pipeline** đã kiểm chứng. Đừng nhầm `XMLInputFactory.IS_VALIDATING` với cam kết mọi StAX provider hỗ trợ XML Schema validation; JSR 173 không đặt validation API thành mục tiêu.

## 10. Dùng StAX với nguồn dữ liệu thật

### Đọc file có encoding rõ ràng

~~~java
try (InputStream input = Files.newInputStream(Path.of("catalog.xml"))) {
    XMLStreamReader xml = secureInputFactory()
            .createXMLStreamReader(input);
    try {
        while (xml.hasNext()) {
            int type = xml.next();
            // Xử lý START_ELEMENT, CHARACTERS, END_ELEMENT...
        }
    } finally {
        xml.close();
    }
}
~~~

Đây là **đoạn minh họa trong method** cần `Files`, `Path`, `InputStream` và `secureInputFactory()` có sẵn, xử lý `IOException`/`XMLStreamException`. Khi dùng `InputStream`, parser xử lý **XML declaration / BOM / XML encoding** theo chuẩn XML và provider; phù hợp cho file có XML declaration encoding rõ ràng. Với `Reader`, việc decode bytes đã diễn ra trước parser, vì vậy application phải chọn đúng charset khi tạo Reader. Không ép mọi file XML thành UTF-8 bằng một Reader nếu XML declaration và actual bytes không khớp.

**Quan trọng:** `XMLStreamReader.close()` không có nghĩa underlying `InputStream` đã được đóng; hãy để try-with-resources sở hữu stream gốc. Nếu app lấy stream từ HTTP upload, cũng cần giới hạn kích thước đọc, timeout và không cho URI/systemId tùy ý từ input kích hoạt network access.

### Đọc từ String/Reader

~~~java
try (StringReader input = new StringReader(xmlText)) {
    XMLStreamReader xml = secureInputFactory()
            .createXMLStreamReader(input);
    try {
        // Pull events...
    } finally {
        xml.close();
    }
}
~~~

Đây là đoạn minh họa; `xmlText` là Java String đã được tạo an toàn. XML text dạng String đã được materialize trong RAM, nên **không** phải streaming end-to-end từ network. Nếu XML lớn, nhận byte/char stream trực tiếp từ nguồn đáng tin với bounded reader để giảm một bản sao bộ nhớ.

### StAX và JDBC SQLXML

Nếu database hỗ trợ `SQLXML`, `SQLXML.getSource(StAXSource.class)` có thể trả một `StAXSource` chứa `XMLStreamReader` hoặc `XMLEventReader`. Nhưng **driver có thể đã tạo parser trước khi application nhận reader**; với XML untrusted, cần kiểm tra security policy của driver hoặc lấy raw `SQLXML.getCharacterStream()`/`getBinaryStream()` và tạo parser đã harden, nếu JDBC driver hỗ trợ. `SQLXML` thường là one-shot và phải `free()` đúng transaction lifetime. Đây là một điểm tích hợp giữa StAX và JDBC, **không làm thay đổi** nguyên tắc JSR 173 là pull parsing.

### StAX với network và message queues

Khi nguồn là `InputStream` từ HTTP/S3/object storage hoặc queue payload, application có thể dừng giữa stream để hạn chế parsing khi đã đủ dữ liệu. Nhưng thực tế kết nối mạng, buffering, close và cancellation thuộc transport; StAX không tự lập HTTP request deadlines. Đặt max input bytes, read timeout, quota và cancellation tại **nguồn**; không để parser giữ connection vô thời hạn sau khi đã hoàn thành business decision.

## 11. Xử lý lỗi và resource lifecycle

### `XMLStreamException` và vị trí lỗi

Các parse operations thường ném `XMLStreamException`. Tùy provider, exception có `getLocation()` (line/column/systemId) và cause. Khi XML không well-formed, xử lý như **validation failure** ở input boundary; đừng trả một domain object nửa vời làm như thành công.

~~~java
try {
    consumeXml();
} catch (XMLStreamException ex) {
    Location loc = ex.getLocation();
    if (loc != null) {
        System.err.println("XML error at line " + loc.getLineNumber()
                + ", column " + loc.getColumnNumber());
    }
    throw ex;
}
~~~

Đây là **đoạn minh họa trong method** cần `consumeXml()` và imports `XMLStreamException`/`Location`. Production logging không nên in nguyên XML payload, URI chứa secrets, access token hoặc full PII; chỉ ghi correlation ID, loại lỗi, vị trí và metadata đã sanitize.

### Error taxonomy

| Triệu chứng | Nguyên nhân thường gặp | Cách khắc phục |
| --- | --- | --- |
| Factory `setProperty` thất bại | Provider không hỗ trợ security property | Fail closed với untrusted XML, đổi provider/cấu hình |
| `XMLStreamException` khi `next()` | XML malformed, DTD bị cấm, external access bị từ chối | Báo lỗi dữ liệu, không tiếp tục với partial object |
| `IllegalStateException` ở `getAttributeCount` | Current event không phải `START_ELEMENT` | Kiểm tra `getEventType` trước khi đọc |
| `getElementText` báo nested element | Element không phải text-only | Duyệt state machine/stack và child nodes |
| `NumberFormatException` từ BigDecimal | Text money không hợp lệ | Validate giá trị, biến thành domain input error |
| `getLocalName` khớp nhưng sai business record | Namespace URI khác | So cả URI + localName |
| Không đọc được XML nhiều namespace prefixes | So prefix literal thay cho QName | Dùng `QName`/namespace URI |
| Text bị tách nhiều event | Parser không coalescing / mixed content | Ghép chunks có giới hạn hoặc dùng getElementText khi hợp lệ |
| `nextTag` ném exception | Gặp non-whitespace text | Dùng `next` và xử lý text |
| XML output thiếu `xmlns` | Chưa khai báo prefix namespace | `writeNamespace`/namespace repairing policy |
| XML output có `&amp;amp;` | Tự escape trước `writeCharacters` | Truyền raw Java text vào writer |
| Output XML invalid / thiếu close tags | Quên `writeEndElement`/`writeEndDocument` | Kiểm tra cân bằng events/round-trip |
| Leak stream/file descriptors | Close StAX reader nhưng không đóng InputStream | Sở hữu underlying stream bằng try-with-resources |
| OOM dù dùng StAX | App giữ List lớn hoặc getElementText dài | Process incrementally, limits và backpressure |
| XML DTD trỏ file/http được mở | Factory/resolver chưa khóa | Disable DTD/external entities/access, test XXE |
| Test chỉ assert XML serialized bytes | Prefix/declaration/whitespace khác | Assert semantic round-trip, namespaces và text |

### Tính đồng thời (concurrency)

`XMLStreamReader`/`XMLEventReader` là cursor/iterator có trạng thái; **không chia sẻ một reader cho nhiều threads** đang gọi `next`. Với mỗi request/stream, tạo reader riêng và đóng đúng lúc. `XMLInputFactory` là mutable object với các properties và provider-specific thread safety behavior; không sửa properties đồng thời với việc tạo readers nếu chưa biết thread-safety contract. Một cách thận trọng là cấu hình factory ở initialization rồi tạo reader trong một scope rõ, và test provider; nếu API/provider không bảo đảm thread safety, cân nhắc factory per task hoặc synchronization phù hợp.

### Chỉ xử lý một phần XML có an toàn không?

Nếu dừng sau khi đọc vài records, bạn **chưa xác nhận phần còn lại của tài liệu well-formed**. Với một nguồn untrusted mà business contract yêu cầu **toàn document hợp lệ**, cần parse đến END_DOCUMENT (hoặc dùng một validation pass) trước khi coi dữ liệu là hợp lệ. Early stop có thể phù hợp khi chỉ cần một prefix event stream trong ứng dụng tin cậy, nhưng phải có ranh giới trust và semantics rõ.

Đừng làm các side effects không thể rollback (gửi email, thanh toán, ghi sang hệ ngoài) ngay khi vừa đọc record đầu của XML chưa được validate toàn bộ. Nếu parse ở record thứ 100 lỗi, những 99 side effects trước đó có thể không thể thu hồi; nên validate trước hoặc thiết kế staging/transaction/outbox.

## 12. Quy trình production: pull một bản ghi và xử lý an toàn

Một pipeline khái niệm:

~~~text
InputStream (bounded, authenticated source)
      │
      ▼
Secure XMLInputFactory (DTD/XXE restrictions)
      │
      ▼
XMLStreamReader
      │
      ├─ START_DOCUMENT / root namespace validation
      ├─ <record> + attributes
      ├─ fields: text-only / nested state machine
      ├─ validate domain fields + limits
      ├─ emit validated record to bounded sink
      └─ END_DOCUMENT + final document checks
      │
      ▼
Commit staged work / publish safely
      │
      ▼
Close XMLStreamReader + underlying InputStream
~~~

Ứng dụng có thể dùng callback consumer riêng:

~~~java
@FunctionalInterface
interface RecordConsumer {
    void accept(Book book) throws Exception;
}
~~~

Đây là một interface minh họa, `Book` là record của domain. Khi consumer có side effects, cần **chính sách lỗi và transaction** rõ ràng: nếu consumer ném exception ở item thứ 100, 99 items trước đã được xử lý như thế nào? Khi untrusted XML cần toàn tài liệu đúng, staging rồi commit hoặc validation pass trước khi commit an toàn hơn.

Thêm validation trong parser production:

- Nhận đúng root/namespace/version; từ chối unexpected elements.
- Không chấp nhận duplicate IDs/fields khi domain cấm; giới hạn số lượng records.
- Giới hạn max depth, maximum text length, total bytes, max attributes và wall-clock deadline.
- Kiểm tra tên phần tử/text/price/currency ở đúng schema path.
- Không cho XML entity/Dtd fetch tài nguyên ngoài.
- Dừng sạch nếu consumer quá chậm; không giữ connection/streams mãi.
- Nếu cần bảo đảm all-or-nothing, staging và transaction commit đúng ranh giới.
- Có test Unicode, namespaces, CDATA, whitespace, malformed XML và XXE.

**StAX cho phép pull lúc bạn muốn, không tự cung cấp HTTP backpressure hoặc transaction management**. Một Java app phải kết nối các tầng này bằng thiết kế pipeline hợp lý.

## 13. Kiểm thử StAX: từ unit đến integration

### Ma trận dữ liệu

| Trường hợp | Kỳ vọng |
| --- | --- |
| Root `<catalog>` và namespace chính xác | Được parse, namespace URI đúng |
| Root cùng localName nhưng URI khác | Bị domain parser từ chối |
| Hai `<book>` | Cursor/event readers đếm đúng 2 |
| Một `<book>` thiếu title | Domain validation báo lỗi |
| Attribute `id` không có namespace | `getAttributeValue(null, "id")` đúng |
| XML default namespace đổi sang prefix `c:` | Domain result không đổi nếu URI/localName giống |
| Text `Java &amp; XML` | `getElementText` trả `Java & XML` |
| Unicode tiếng Việt + emoji | `String.equals` giữ chính xác code points |
| CDATA/text chia thành nhiều events | Parser xử lý/ghép đúng mà không bỏ sót |
| Title có nested `<em>` | `getElementText` ném hoặc domain parser xử lý mixed content |
| Whitespace/indentation | Không tạo record rác |
| `nextTag` gặp nonwhitespace text | Hành vi XMLStreamException phù hợp |
| XML malformed | `XMLStreamException`, no partial commit |
| `DOCTYPE`/external entity | Bị từ chối, không đọc file hoặc SSRF |
| Entity expansion/nesting extreme | Resource limits hoạt động |
| Output XML chứa `&` | `writeCharacters` escape, parse round-trip |
| Output namespaces | `xmlns` hợp lệ, URI/localName khớp sau parse |
| Output schema/encoding/declaration | Đúng policy, không dựa byte identity nếu không cần |
| Dừng sớm | Reader/source được đóng, semantics ứng dụng rõ |
| Concurrency | Mỗi parse có reader riêng, không share mutable state |
| Big input | Đo memory/CPU và bounded buffering |

### Các assertions trong demo

Kết quả trong phần 7 xác minh:
- `XMLStreamReader` và `XMLEventReader` thấy cùng số items.
- `getElementText` giải entity predefined đúng.
- `XMLStreamWriter` tạo output well-formed với namespace.
- Read-after-write giữ domain values.
- Parser/config reject DTD trong JDK đang dùng.

**Demo không thay thế** việc đo parser throughput, size limits và correctness với XML production. Với tài liệu quá lớn, thay vì trả `List<Book>`, một production reader có thể đọc từng `Book`, validate rồi phát sang bounded consumer (có staging/transaction policy).

### Đo performance đúng

Đừng benchmark chỉ thời gian parse một XML 50 bytes rồi kết luận parser nào tốt nhất. Hãy dùng data sizes/structures thực tế, warm-up phù hợp, đo allocations, resident heap, GC pauses, latency, throughput và số domain objects giữ lại. Một `XMLStreamReader` thường giảm số event object allocations so với `XMLEventReader` nhưng khác biệt phụ thuộc JAXP provider và logic application; độ phức tạp code đôi khi quan trọng hơn tốc độ.

Nếu code dùng `getElementText()` cho một text node lớn, memory tăng dù cursor API vẫn là “streaming”. Nếu code dùng XMLInputFactory từ một thư viện bên ngoài hoặc JAXP provider thay thế, hãy chạy đầy đủ security tests trước deployment.

## 14. Những nhầm lẫn phổ biến

| Nhận định sai | Điều đúng |
| --- | --- |
| “JSR 173 Withdrawn nên StAX bị xóa khỏi Java.” | JSR standalone kết thúc; **StAX vẫn là Java SE API**, `java.xml` |
| “Java 17 phải thêm StAX standalone JAR cũ.” | Thông thường không, module `java.xml` đã chứa API |
| “`javax.xml.stream` phải đổi sang `jakarta.xml.stream`.” | Java SE hiện hành vẫn dùng `javax.xml.stream` |
| “StAX là SAX với tên mới.” | SAX push callbacks; StAX caller pull events |
| “StAX giống DOM, có thể sửa bất cứ node nào.” | StAX là forward streaming, không có random-access document tree |
| “StAX luôn O(1) RAM.” | Caller có thể giữ List hoặc text rất lớn; parser cũng có buffers |
| “`hasNext()` tự chuyển reader sang event tiếp.” | `next()` mới di chuyển current event |
| “`getAttributeValue` gọi ở CHARACTERS cũng hợp lệ.” | Attributes thuộc START_ELEMENT |
| “`getElementText` đọc được mọi nested XML.” | Chỉ text-only element, ném nếu có nested START_ELEMENT |
| “Sau `getElementText` cursor vẫn đứng START_ELEMENT.” | Cursor đã ở END_ELEMENT |
| “`nextTag` luôn dùng thay `next` được.” | Non-whitespace text có thể gây exception |
| “Một element luôn đúng một CHARACTERS event.” | Text có thể được chia thành nhiều events |
| “Prefix khác nghĩa XML khác.” | Namespace URI + localName xác định expanded name |
| “Default namespace áp cả cho unprefixed attributes.” | Không, attribute id không có namespace |
| “StAX mặc định chặn hết XXE.” | Phải cấu hình factory, external access và resolver, kiểm thử provider |
| “FEATURE_SECURE_PROCESSING là StAX property chung.” | StAX dùng SUPPORT_DTD/external entity/EAP properties |
| “Chỉ set SUPPORT_DTD=false là đủ cho mọi provider.” | Phải kiểm soát external entities, resolver, resource limits và fail closed |
| “Parser tự xác nhận XSD/schema của app.” | StAX không phải schema validator mặc định |
| “`XMLStreamReader.close()` chắc chắn đóng InputStream.” | Không bảo đảm; owner đóng underlying stream |
| “`writeCharacters` nhận raw XML markup để inject vào document.” | Nó ghi **text** với XML escaping; dùng element methods cho markup |
| “Output XML phải byte-identical mới đúng.” | Namespace prefix/whitespace/declaration có thể khác nhưng semantic-equivalent |
| “Dừng sau hai items nghĩa là XML hoàn toàn well-formed.” | Phần còn lại chưa được parse/validate |
| “Mỗi request chia sẻ một XMLStreamReader cho nhẹ.” | Reader có cursor mutable, không thread-safe theo thiết kế |
| “Tăng số event loops là tự có transaction/backpressure.” | Cần tích hợp deadline, bounded queues, staging, transaction |
| “XML có chữ Việt/emoji cần encode lại thủ công trong String.” | Java String là Unicode; chỉ phải chọn charset đúng khi bytes↔characters |

## 15. Câu hỏi tự kiểm tra

1. **StAX từ JSR nào?** JSR 173 — Streaming API for XML.
2. **JSR 173 Withdrawn có làm API StAX lỗi thời không?** Không; các API được tích hợp và vẫn nằm trong Java SE hiện hành.
3. **StAX là push hay pull?** Pull: application gọi `next()`/`nextEvent()`.
4. **StAX thuộc module và package nào?** `java.xml` và `javax.xml.stream`.
5. **Hai reader API chính?** `XMLStreamReader` (cursor) và `XMLEventReader` (event objects).
6. **Sự khác nhau giữa SAX và StAX?** SAX parser gọi callback, StAX caller yêu cầu event.
7. **Reader mới bắt đầu ở event nào?** Thông thường `START_DOCUMENT` với XMLStreamReader.
8. **`hasNext()` có consume một event không?** Không, `next()` mới chuyển.
9. **`getElementText()` có thể dùng khi nào?** Đang ở START_ELEMENT của phần tử text-only.
10. **Sau `getElementText()` reader đứng đâu?** Tại END_ELEMENT tương ứng.
11. **`nextTag()` có bỏ qua text không-whitespace không?** Không; thường ném XMLStreamException.
12. **Đọc attribute `id` khi nào?** Ở START_ELEMENT; dùng `getAttributeValue(null, "id")` nếu id không có namespace.
13. **Namespace đúng nên so theo gì?** Namespace URI + localName, không so literal prefix.
14. **Dữ liệu text `Java &amp; XML` đọc thành gì?** Java `"Java & XML"`.
15. **Tại sao không gọi `getElementText` trên `<title><em>Java</em></title>`?** Có nested element, không phải text-only.
16. **Dùng `writeCharacters("A & B")` có cần tự escape `&` trước không?** Không; writer escape theo XML rules.
17. **`newDefaultFactory` dùng để làm gì?** Chọn built-in default provider thay vì lookup provider ngoài.
18. **Ba cài đặt StAX chống XXE chính?** Disable DTD, disable external entities, restrict ACCESS_EXTERNAL_DTD; kiểm soát resolver và limits.
19. **StAX có tự validate XSD không?** Không, cần bước validation riêng theo policy.
20. **Vì sao Reader/Stream vẫn phải được đóng?** `XMLStreamReader.close` không bảo đảm đóng nguồn bên ngoài.
21. **Nếu dừng parse sớm, có biết XML đoạn còn lại well-formed không?** Không.
22. **`XMLEventReader.peek` khác `nextEvent` thế nào?** Peek không consume, nextEvent consume.
23. **`XMLStreamWriter` và `XMLEventWriter` khác nhau thế nào?** Một bên ghi qua method từng cấu trúc, bên kia nhận events.
24. **InputFactory được chia sẻ giữa requests có chắc thread-safe không?** Không mặc định; tránh mutation concurrent, xem provider contract.
25. **Tại sao test round-trip bằng domain values tốt hơn so raw XML String?** Serializer có thể đổi prefix/whitespace/escaping mà nghĩa không đổi.
26. **StAX giúp xử lý tệp rất lớn luôn an toàn không?** Chỉ khi ứng dụng không tích lũy dữ liệu không giới hạn và có limits.
27. **Khi đọc XML từ SQLXML, có cần xem driver parser security không?** Có, driver có thể tạo parser trước khi app can thiệp.
28. **Vì sao không dùng text-only getElementText cho XML mixed content?** Nó không xử lý nested child elements.
29. **Exception chuẩn khi StAX parse lỗi?** `XMLStreamException`, có thể có `Location`.
30. **Nếu writer không khai báo namespace thì sao?** XML có thể thiếu `xmlns`/prefix mapping; dùng writeNamespace/repairing policy.
31. **Nếu XML chứa external DTD dù business không cần, xử lý thế nào?** Từ chối DTD, không fetch external resources.
32. **JSR 173 có cung cấp XML schema validation API không?** Không phải mục tiêu của JSR; validation là layer riêng.

## 16. Nguồn chính thức còn áp dụng

- [JCP — JSR 173: Streaming API for XML](https://jcp.org/en/jsr/detail?id=173): lịch sử, mục đích pull parser và lý do chấm dứt phân phối standalone JSR, **không có nghĩa API Java SE bị loại bỏ**.
- [Java SE 25 — javax.xml.stream package](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/stream/package-summary.html): các factory, readers/writers và XMLStreamException còn trong `java.xml`.
- [Java SE 25 — XMLInputFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/stream/XMLInputFactory.html): `newFactory`, `newDefaultFactory`, `SUPPORT_DTD`, `IS_SUPPORTING_EXTERNAL_ENTITIES`, `IS_COALESCING` và external-access property.
- [Java SE 25 — XMLStreamReader](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/stream/XMLStreamReader.html): `next`, `nextTag`, `getElementText`, event state, namespaces, attributes.
- [Java SE 25 — XMLEventReader](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/stream/XMLEventReader.html): `nextEvent`, `peek`, `nextTag`.
- [Java SE 25 — XMLStreamWriter](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/stream/XMLStreamWriter.html): elements, attributes, namespaces và escaping.
- [Java SE 25 — XMLOutputFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/stream/XMLOutputFactory.html): tạo `XMLStreamWriter`/`XMLEventWriter` và namespace repair properties.
- [Java SE 25 — XMLEventFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/stream/XMLEventFactory.html): tạo XMLEvents để ghi.
- [Java SE 25 — XMLStreamConstants](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/stream/XMLStreamConstants.html): event type constants.
- [Java SE 25 — XMLConstants](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/XMLConstants.html): `ACCESS_EXTERNAL_DTD` và các XML security properties.
- [Java SE 25 — JAXP Security Guide](https://docs.oracle.com/en/java/javase/25/security/java-api-xml-processing-jaxp-security-guide.html): giới hạn external access, entity processing và resource limits.
- [W3C — Namespaces in XML 1.0](https://www.w3.org/TR/xml-names/): URI/localName vs prefix, unprefixed attributes và expanded names.

**Tổng kết:** JSR 173 giới thiệu **StAX**, và dù quá trình duy trì **standalone specification** đã kết thúc, **StAX pull model vẫn là Java SE API hiện hành**. Lập trình viên chủ động kéo XML events bằng `XMLStreamReader` hoặc `XMLEventReader`, xử lý tuần tự thay vì dựng DOM hoặc nhận SAX callbacks. Muốn code đúng và an toàn, phải giữ current-event invariants, xử lý text/nested structure/namespaces, đóng cả reader lẫn nguồn dữ liệu, cấu hình DTD/XXE restrictions **trước khi parse** và thiết lập input/resource limits cho XML không tin cậy.