# StAXSource, StAXResult và tích hợp JAXP

## 1. Bài toán tích hợp giữa hai thế giới xử lý XML

StAX (*Streaming API for XML*) là API **pull parsing**: chương trình Java chủ động gọi `next()` hoặc `nextEvent()` để lấy từng sự kiện XML. Trong khi đó, các phần khác của JAXP (*Java API for XML Processing*) nhận hai abstraction chung:

- `javax.xml.transform.Source`: nguồn XML dùng cho transformation hoặc validation.
- `javax.xml.transform.Result`: nơi nhận kết quả XML đã xử lý.

Khi một ứng dụng đã đọc XML bằng StAX, không cần chuyển toàn bộ input thành `String` hay dựng cây DOM chỉ để gọi JAXP. Java có hai adapter:

- **`StAXSource`** bọc `XMLStreamReader` hoặc `XMLEventReader` để cung cấp một `Source` cho `Transformer` và `Validator`.
- **`StAXResult`** bọc `XMLStreamWriter` hoặc `XMLEventWriter` để cung cấp một `Result` cho `Transformer` và các APIs tương thích.

Hai lớp nằm ở **`javax.xml.transform.stax`**, thuộc **module `java.xml`**, có từ **Java 6 (Since: 1.6)** và **vẫn được hỗ trợ trong Java SE 26**.

~~~text
XML input bytes/Reader
          |
          v
   XMLInputFactory
          |
          v
 XMLStreamReader / XMLEventReader
          |
          v
      StAXSource  ---------------------> Transformer hoặc Validator
                                              |
                                              v
                                         StAXResult
                                              |
                                              v
                                   XMLStreamWriter / XMLEventWriter
                                              |
                                              v
                                         XML output
~~~

**Cần phân biệt:** StAX adapters không tự bảo đảm toàn bộ pipeline dùng bộ nhớ cố định. `Transformer` áp dụng XSLT có thể dựng cây nội bộ, `Validator` có thể giữ state schema, còn `StringWriter` sẽ giữ toàn bộ XML output. Lợi ích thực tế phụ thuộc **provider + stylesheet/schema + source/sink + thiết kế application**.

### Kết quả cần đạt

Sau bài này bạn có thể:

1. Phân biệt `StAXSource`, `StAXResult`, `StreamSource`, `StreamResult` và `DOMSource/DOMResult`.
2. Dùng cả hai constructor `StAXSource(XMLStreamReader)` và `StAXSource(XMLEventReader)`.
3. Dùng cả hai constructor `StAXResult(XMLStreamWriter)` và `StAXResult(XMLEventWriter)`.
4. Tuân thủ điều kiện **`START_DOCUMENT` hoặc `START_ELEMENT`** của StAXSource và hiểu Source **chỉ được tiêu thụ một lần**.
5. Tạo identity transformer, XSLT transformer, kiểm tra `StAXSource.FEATURE` và `StAXResult.FEATURE`.
6. Validate XSD bằng `Validator.validate(StAXSource)` hoặc `Validator.validate(StAXSource, StAXResult)`, không ghép Source/Result sai họ.
7. Cấu hình bảo mật XXE/DTD/external references ở **XMLInputFactory, TransformerFactory, SchemaFactory, Validator**.
8. Đóng đúng StAX reader/writer **và** Java InputStream/Reader/OutputStream/Writer.
9. Chạy hai ví dụ độc lập Java 17+ (transformation và schema validation), kiểm tra stdout, lỗi schema và cặp API không hợp lệ.

## 2. Bản đồ API còn áp dụng

| API | Package | Vai trò |
| --- | --- | --- |
| `XMLInputFactory` | `javax.xml.stream` | Tạo StAX readers, cấu hình parser |
| `XMLStreamReader` | `javax.xml.stream` | Cursor event, đọc sự kiện tại vị trí hiện tại |
| `XMLEventReader` | `javax.xml.stream` | Iterator trả `XMLEvent` objects |
| `StAXSource` | `javax.xml.transform.stax` | StAX reader thành JAXP `Source` |
| `TransformerFactory` | `javax.xml.transform` | Tạo identity hoặc XSLT transformer |
| `Transformer` | `javax.xml.transform` | `transform(Source, Result)` |
| `XMLOutputFactory` | `javax.xml.stream` | Tạo StAX output writers |
| `XMLStreamWriter` | `javax.xml.stream` | Writer dạng cursor |
| `XMLEventWriter` | `javax.xml.stream` | Writer nhận event objects |
| `StAXResult` | `javax.xml.transform.stax` | StAX writer thành JAXP `Result` |
| `SchemaFactory` / `Schema` | `javax.xml.validation` | Biên dịch schema XSD |
| `Validator` | `javax.xml.validation` | Kiểm tra tài liệu XML theo schema |
| `XMLConstants` | `javax.xml` | Các constants bảo mật và schema |
| `StreamSource/StreamResult` | `javax.xml.transform.stream` | Source/Result trực tiếp từ streams |
| `DOMSource/DOMResult` | `javax.xml.transform.dom` | Source/Result dựa trên DOM tree |

Đây là những API Java SE đang được hỗ trợ. Package `javax.xml.stream` vẫn là tên tiêu chuẩn trong JDK hiện đại, **không** tự thay thành `jakarta.xml.stream`.

### 2.1. Không phải lúc nào cũng cần StAX adapter

Nếu chỉ cần `Transformer` đọc trực tiếp một file và ghi ra file khác, `new StreamSource(InputStream)` và `new StreamResult(OutputStream)` thường đủ, vẫn có thể xử lý stream mà không phải gọi `Files.readString`. `StAXSource` có ý nghĩa đặc biệt khi bạn **đã có StAX reader** (hoặc cần cấu hình/quản lý parser đó) trước khi đưa dữ liệu cho JAXP.

Nếu cần sửa/cập nhật nhiều nodes tùy ý, DOM phù hợp với document nhỏ/giới hạn, dù sử dụng nhiều heap hơn. Không ép StAX vào mọi tình huống.

## 3. StAXSource: chuyển reader thành Source, không phải copy XML

Hai constructor:

~~~java
StAXSource fromCursor = new StAXSource(xmlStreamReader);
StAXSource fromEvents = new StAXSource(xmlEventReader);
~~~

**Đoạn trích**, không phải file runnable; bạn cần `import javax.xml.transform.stax.StAXSource`, và các reader đã được tạo từ `XMLInputFactory`.

### 3.1. Precondition của trạng thái

Theo Oracle Javadoc, reader phải:

- Khác `null`.
- Đang ở **`XMLStreamConstants.START_DOCUMENT` hoặc `START_ELEMENT`**.

Reader tại `CHARACTERS`, `END_ELEMENT` hay `END_DOCUMENT` có thể làm constructor ném `IllegalStateException`. Nếu reader null thì `IllegalArgumentException`. Ví dụ từ factory cho XML document thường ở `START_DOCUMENT`, thuận tiện bọc ngay. Nếu cần transform từ một subtree, đặt reader ở `START_ELEMENT` tương ứng và xem xét namespace/context.

~~~java
// Phản ví dụ: reader có thể bị đẩy tới event không hợp lệ.
XMLStreamReader reader = factory.createXMLStreamReader(input);
reader.next();
reader.next();
StAXSource source = new StAXSource(reader); // Có thể IllegalStateException.
~~~

Đây là **đoạn trích cố ý mô tả lỗi**. Việc hai `next()` đưa reader tới đâu phụ thuộc input; không coi đoạn này là test có stdout cố định.

### 3.2. StAXSource là single-use

Javadoc ghi `StAXSource` **bị tiêu thụ khi xử lý và không reusable**. Việc gọi `Transformer.transform` hoặc `Validator.validate` tiến reader về trước, có thể tới `END_DOCUMENT`.

~~~java
// Sai: Source đã tiêu thụ không tự rewind.
transformer.transform(source, firstResult);
transformer.transform(source, secondResult);
~~~

**Phản ví dụ:** cần mở lại nguồn rồi tạo **reader + StAXSource mới** cho lần transform thứ hai. Không kỳ vọng một InputStream bất kỳ hỗ trợ mark/reset; việc cố chạy lại từ cursor `END_DOCUMENT` không đúng.

Đối với workflow **validate rồi transform**, có thể cần hai lượt đọc file an toàn, hoặc một pipeline validation/transform theo kiến trúc chuyên biệt, không phải dùng lại StAXSource vừa bị Validator tiêu thụ.

### 3.3. Getter và system ID

`getXMLStreamReader()` hoặc `getXMLEventReader()` cho phép truy lại reader đúng loại được bọc; accessor còn lại có thể `null`. `getSystemId()` có thể dựa trên location của reader, nhưng `StAXSource.setSystemId(...)` **không phải cách hợp lệ** để tự tùy chỉnh system ID như một StreamSource thông thường.

Nếu XML có reference tương đối, base/system ID có thể ảnh hưởng resolution. Với input không tin cậy, kiểm soát **external-access properties và resolver** mới là cách bảo vệ chính.

## 4. StAXResult: đưa JAXP output tới StAX writer

Có hai constructor:

~~~java
StAXResult cursorOutput = new StAXResult(xmlStreamWriter);
StAXResult eventOutput = new StAXResult(xmlEventWriter);
~~~

**Đoạn trích:** `StAXResult` không tự tạo writer hoặc quản lý file. Writer được tạo bằng `XMLOutputFactory`, thường gắn với `OutputStream` hoặc `Writer` do application sở hữu.

Ví dụ:

~~~text
Transformer / Validator
      |
      v
StAXResult
      |
      v
XMLStreamWriter / XMLEventWriter
      |
      v
BufferedWriter, OutputStream, network sink, ...
~~~

Chính caller phải **`flush()`/`close()` writer** và **đóng stream đích** theo lifecycle; không giả định đóng StAX writer cũng đóng underlying stream.

### 4.1. XMLStreamWriter và XMLEventWriter

- `XMLStreamWriter` hoạt động qua các lời gọi như `writeStartElement`, `writeCharacters`, `writeEndElement` và `writeEndDocument`.
- `XMLEventWriter` nhận những `XMLEvent` objects, thuận tiện nếu pipeline dùng event API.
- Cả hai đều có thể dùng trong `StAXResult`. Không có quy tắc mọi `XMLStreamWriter` nhanh hơn mọi `XMLEventWriter`: benchmark theo provider/data.

### 4.2. Khi dùng StreamResult thay vì StAXResult

Nếu không cần StAX writer, `new StreamResult(outputStream)` đơn giản hơn. Nếu cần xử lý XML events theo lớp riêng, kiểm soát writer hoặc đã có writer trong ứng dụng, `StAXResult` là adapter đúng.

**Lưu ý compatibility:** `Validator.validate(StAXSource, StreamResult)` **không hợp lệ** dù cả hai đều là các interface `Source/Result`. Mục 6 giải thích bảng hỗ trợ.

## 5. Tích hợp Transformer: identity và XSLT

### 5.1. Identity transform

`TransformerFactory.newTransformer()` (không stylesheet) tạo identity transformer:

~~~java
Transformer transformer = transformerFactory.newTransformer();
transformer.transform(new StAXSource(reader), new StAXResult(writer));
~~~

**Đoạn trích**: `transformerFactory` phải đã cấu hình bảo mật, `reader` và `writer` đang mở. Transformer đọc qua StAXSource và ghi output vào StAXResult.

Identity transform bảo tồn **cấu trúc/nội dung XML theo semantics của parser**, nhưng không bảo đảm XML output giống byte-for-byte input. Serializer có thể khác dấu nháy, XML declaration, namespace prefix, whitespace hoặc cách viết empty elements. Với chữ ký số XML, cần canonicalization đúng chuẩn, không thay bằng một identity transform.

### 5.2. XSLT transform

Khi có một XSLT stylesheet, dùng `TransformerFactory.newTransformer(Source stylesheet)`, ví dụ stylesheet nội bộ từ `StreamSource`, rồi truyền StAXSource và StAXResult cho `transform`:

~~~java
Transformer xslt = transformerFactory.newTransformer(
        new StreamSource(new StringReader(stylesheetXml)));
xslt.transform(new StAXSource(reader), new StAXResult(writer));
~~~

**Đoạn trích**, các biến do caller cung cấp và phải quản lý resources. Dùng XSLT 1.0 trong ví dụ Java 17+, không mặc định JDK provider hỗ trợ XSLT 2.0/3.0.

### 5.3. Kiểm tra feature của provider

Các constant `StAXSource.FEATURE`, `StAXResult.FEATURE` dùng được với:

~~~java
if (!transformerFactory.getFeature(StAXSource.FEATURE)
        || !transformerFactory.getFeature(StAXResult.FEATURE)) {
    throw new IllegalStateException("StAX adapters unsupported");
}
~~~

Đây là đoạn trích; XML transformation provider có thể được lựa chọn qua JAXP service discovery, dependencies hoặc cấu hình hệ thống. `getFeature(true)` là dấu hiệu **hỗ trợ API input/output type**, không chứng minh XSLT cụ thể sẽ chạy đúng hoặc đạt SLA memory.

### 5.4. Bảo mật XSLT: không chỉ secure processing

XSLT có thể tham chiếu stylesheet ngoài (`xsl:include`/`xsl:import`) hoặc tài liệu ngoài (hàm `document()`), thậm chí vendor extensions. Với XML/XSLT không tin cậy cần:

- `transformerFactory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true)`.
- `setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "")` để chặn external DTD.
- `setAttribute(XMLConstants.ACCESS_EXTERNAL_STYLESHEET, "")` để chặn import/include/document access.
- `setURIResolver(...)` không cho tải đường dẫn/URL bất ngờ.
- Cấu hình bảo mật **XMLInputFactory** trước khi tạo StAX reader; không chờ tới Transformer mới chặn XXE.
- Giới hạn tổng bytes, thời gian, recursion/template complexity và output; `FEATURE_SECURE_PROCESSING` không phải bảo đảm heap hoặc thời gian.
- Nếu provider từ chối security property bắt buộc, **fail-closed**, không catch rồi bỏ qua.

## 6. Tích hợp Validator và cặp Source/Result hợp lệ

`javax.xml.validation.SchemaFactory` tạo `Schema` từ XSD, sau đó `Schema.newValidator()` tạo `Validator`. StAXSource có thể được sử dụng làm input:

~~~java
validator.validate(new StAXSource(reader)); // Chỉ validate.
validator.validate(new StAXSource(reader), new StAXResult(writer));
~~~

Đây là **hai cách thay thế**; không dùng lại cùng một reader sau khi nó đã bị tiêu thụ. Kết quả thứ hai có thể chứa XML đã được **augmented** theo schema/implementation, không đảm bảo byte-for-byte giữ nguyên serialized input.

### 6.1. Bảng compatibility do JAXP Validator quy định

| Source | Result có thể đi cùng |
| --- | --- |
| `StreamSource` | `null` hoặc `StreamResult` |
| `SAXSource` | `null` hoặc `SAXResult` |
| `DOMSource` | `null` hoặc `DOMResult` |
| **`StAXSource`** | **`null` hoặc `StAXResult`** |

Điểm quan trọng: `Validator.validate(StAXSource, StreamResult)` phải ném `IllegalArgumentException`, không phải tự chuyển kiểu output. Khi muốn đổi từ StAXSource sang StreamResult, một **identity Transformer** là lựa chọn thích hợp, không phải Validator với cặp Result bị cấm.

### 6.2. SchemaFactory không tự kiểm soát mọi external references

Trước khi biên dịch XSD, dùng:

~~~java
schemaFactory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
schemaFactory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
schemaFactory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
~~~

**Đoạn trích:** `schemaFactory` là `SchemaFactory`. Validator mới tạo cũng nên đặt external access properties phù hợp. Nếu schema cần các imports nội bộ đã được kiểm duyệt, dùng `LSResourceResolver`/local catalog hoặc allowlist chặt, không cấp quyền `"all"` cho upload từ ngoài.

### 6.3. Thread safety

`Validator` **không thread-safe/reentrant**; `SchemaFactory` cũng không thread-safe. `Transformer`, readers và writers mang mutable state nên không share đồng thời mà không có provider-specific guarantee. Thường tạo reader/writer/validator/transformer theo request; các compiled artifacts như `Schema` hoặc `Templates` có thể được quản lý/cache theo hợp đồng thread-safety và provider.

### 6.4. Validation khác transformation

- Validation kiểm tra XML theo XSD (ví dụ số tiền phải dương).
- Transformation theo XSLT có thể đổi tên element, bỏ/thêm fields và thứ tự.
- Input hợp XSD **không bảo đảm** output sau XSLT hợp XSD, và ngược lại.
- Nếu workflow cần **validate rồi transform**, tạo nguồn mới ở lượt sau hoặc một pipeline kết hợp được kiểm thử; StAXSource đã consumed không rewind.

## 7. Bảo mật nhiều tầng và quản lý tài nguyên

### 7.1. Bảo mật input StAX

Một cấu hình phổ biến cho untrusted XML:

~~~java
XMLInputFactory factory = XMLInputFactory.newFactory();
factory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
factory.setProperty(XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
factory.setXMLResolver((publicId, systemId, baseUri, namespace) -> {
    throw new XMLStreamException("External entity denied");
});
~~~

**Đoạn trích:** imports từ `javax.xml.stream.*` và `javax.xml.XMLConstants`. Những properties phải được thiết lập **trước khi tạo reader**. `SUPPORT_DTD=false` và `IS_SUPPORTING_EXTERNAL_ENTITIES=false` ngăn DTD/entity processing theo contract/provider; external access property cấm protocols; resolver deny adds another safeguard.

`setProperty` có thể ném `IllegalArgumentException` nếu provider không chấp nhận security property. Nếu cần chặn XXE, **không tiếp tục parse khi cấu hình bảo mật thất bại**.

### 7.2. Đường cursor từ chối DTD rõ ràng

Ví dụ runnable phần 8 dùng `StreamReaderDelegate`: mỗi lần `next()` nếu event là `DTD` hoặc `ENTITY_REFERENCE` thì ném `XMLStreamException`. Dùng cùng việc tắt external access để từ chối DOCTYPE theo policy, không chỉ dựa vào việc provider lờ DTD.

**Không suy rộng sang mọi provider:** demo XMLEventReader trong XSLT đã chặn external entities/DTD nhưng không cài event-filter chủ động cho mọi DTD event. Khi cần quy tắc “mọi DOCTYPE bị cấm” trên event path, viết filter tương đương và test trên provider thực tế.

### 7.3. Resource ownership

| Đối tượng | Đóng thế nào? |
| --- | --- |
| `InputStream` hoặc `Reader` nguồn | Caller dùng try-with-resources |
| `XMLStreamReader` hoặc `XMLEventReader` | Caller gọi `close()` trong finally |
| `StAXSource` | Adapter không có lifecycle đóng source hộ caller |
| `Transformer`/`Validator` | Không làm StAXSource reusable |
| `XMLStreamWriter` hoặc `XMLEventWriter` | Caller `flush()` rồi `close()` |
| `StAXResult` | Adapter không tự đóng writer |
| `OutputStream` hoặc `Writer` đích | Caller đóng riêng |

**Không giả định** `XMLStreamReader.close()` đóng InputStream hoặc `XMLStreamWriter.close()` đóng OutputStream. Trong demo, source và sink dùng try-with-resources; StAX reader/writer dùng `finally`. Ở production nên xử lý cả primary/suppressed exceptions nếu `transform` và cleanup cùng ném lỗi.

### 7.4. Giới hạn đầu vào/đầu ra

Các lớp StAX/JAXP **không tự đặt quota nghiệp vụ**. XML upload cần max total bytes, max depth, number of attributes/events, entity expansion restrictions, field lengths, CPU/time deadline, concurrency và bounded output. XSLT có thể tạo output lớn hơn nhiều input. Nếu destination là file, cần temp file, size-check và publish an toàn để không để lại file XML nửa chừng sau exception.

## 8. Ví dụ Java 17+: identity + XSLT, dùng cả hai loại StAX adapter

`StaxJaxpTransformDemo.java` là một chương trình độc lập:

- Identity: `XMLStreamReader → StAXSource → Transformer → StAXResult(XMLStreamWriter)`.
- XSLT 1.0: `XMLEventReader → StAXSource → Transformer → StAXResult(XMLEventWriter)`.
- Input parser và TransformerFactory có security settings chặn DTD/external references.
- `StAXSource.FEATURE`/`StAXResult.FEATURE` được kiểm tra.
- Output XML được parse lại để so sánh dữ liệu có ý nghĩa, không hardcode serialization byte-for-byte.
- Test DOCTYPE trên **đường identity cursor** bảo đảm error, không hứa cho mọi vendor/provider.

**Lưu ý:** `StringWriter`, `List<String>` và `getElementText()` xuất hiện vì fixture có **hai record nhỏ**. Đây **không** phải pattern giữ bộ nhớ giới hạn cho file lớn; phần 10 giải thích.

### 8.1. File StaxJaxpTransformDemo.java

~~~java
import java.io.*;
import java.util.*;
import javax.xml.XMLConstants;
import javax.xml.stream.*;
import javax.xml.stream.util.StreamReaderDelegate;
import javax.xml.transform.*;
import javax.xml.transform.stax.*;
import javax.xml.transform.stream.*;

public final class StaxJaxpTransformDemo {
    private static final String INPUT =
            "<catalog><book code='A'><title>Xin &amp; chào</title></book>"
          + "<book code='B'><title>Java StAX</title></book></catalog>";

    private static final String XSLT = """
            <xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
                            version="1.0">
              <xsl:output method="xml" omit-xml-declaration="yes"/>
              <xsl:template match="/catalog">
                <summary>
                  <xsl:for-each select="book">
                    <item><xsl:value-of select="title"/></item>
                  </xsl:for-each>
                </summary>
              </xsl:template>
            </xsl:stylesheet>
            """;

    static XMLInputFactory secureInputFactory() {
        XMLInputFactory f = XMLInputFactory.newFactory();
        f.setProperty(XMLInputFactory.SUPPORT_DTD, false);
        f.setProperty(XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
        f.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        f.setXMLResolver((publicId, systemId, baseUri, namespace) -> {
            throw new XMLStreamException("External entity forbidden");
        });
        return f;
    }

    static TransformerFactory secureTransformerFactory() throws Exception {
        TransformerFactory factory = TransformerFactory.newInstance();
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_STYLESHEET, "");
        factory.setURIResolver((href, base) -> {
            throw new TransformerException("External stylesheet/document forbidden");
        });
        if (!factory.getFeature(StAXSource.FEATURE)
                || !factory.getFeature(StAXResult.FEATURE)) {
            throw new IllegalStateException("This transformer lacks StAX bridges");
        }
        return factory;
    }

    static XMLStreamReader rejectingDtdReader(XMLInputFactory f, Reader source)
            throws XMLStreamException {
        XMLStreamReader delegate = f.createXMLStreamReader(source);
        return new StreamReaderDelegate(delegate) {
            @Override public int next() throws XMLStreamException {
                int kind = super.next();
                if (kind == XMLStreamConstants.DTD
                        || kind == XMLStreamConstants.ENTITY_REFERENCE) {
                    throw new XMLStreamException("DOCTYPE/entities not permitted");
                }
                return kind;
            }
        };
    }

    static String identity(String input) throws Exception {
        XMLInputFactory inFactory = secureInputFactory();
        TransformerFactory transforms = secureTransformerFactory();
        try (StringReader source = new StringReader(input);
             StringWriter sink = new StringWriter()) {
            XMLStreamReader reader = rejectingDtdReader(inFactory, source);
            XMLStreamWriter writer = XMLOutputFactory.newFactory()
                    .createXMLStreamWriter(sink);
            try {
                Transformer t = transforms.newTransformer();
                t.transform(new StAXSource(reader), new StAXResult(writer));
                writer.flush();
                return sink.toString();
            } finally {
                writer.close();
                reader.close();
            }
        }
    }

    static String xslt(String input) throws Exception {
        XMLInputFactory inFactory = secureInputFactory();
        TransformerFactory transforms = secureTransformerFactory();
        try (StringReader source = new StringReader(input);
             StringReader stylesheet = new StringReader(XSLT);
             StringWriter sink = new StringWriter()) {
            XMLEventReader reader = inFactory.createXMLEventReader(source);
            XMLEventWriter writer = XMLOutputFactory.newFactory()
                    .createXMLEventWriter(sink);
            try {
                Transformer t = transforms.newTransformer(
                        new StreamSource(stylesheet));
                t.transform(new StAXSource(reader), new StAXResult(writer));
                writer.flush();
                return sink.toString();
            } finally {
                writer.close();
                reader.close();
            }
        }
    }

    static List<String> titles(String xml, String tag) throws Exception {
        List<String> result = new ArrayList<>();
        try (StringReader source = new StringReader(xml)) {
            XMLStreamReader reader =
                    secureInputFactory().createXMLStreamReader(source);
            try {
                while (reader.hasNext()) {
                    if (reader.next() == XMLStreamConstants.START_ELEMENT
                            && reader.getLocalName().equals(tag)) {
                        result.add(reader.getElementText());
                    }
                }
            } finally {
                reader.close();
            }
        }
        return result;
    }

    static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    public static void main(String[] args) throws Exception {
        String identity = identity(INPUT);
        List<String> original = titles(identity, "title");
        check(original.equals(List.of("Xin & chào", "Java StAX")),
                "identity output mismatch: " + identity);
        System.out.println("identity-titles=" + original.size());
        System.out.println("identity-first=" + original.get(0));

        String transformed = xslt(INPUT);
        List<String> values = titles(transformed, "item");
        check(values.equals(List.of("Xin & chào", "Java StAX")),
                "XSLT output mismatch: " + transformed);
        System.out.println("xslt-items=" + values.size());
        System.out.println("xslt-second=" + values.get(1));

        String hostile = "<!DOCTYPE catalog [<!ENTITY secret "
                + "SYSTEM 'file:///not-allowed-secret'>]>"
                + "<catalog><book><title>&secret;</title></book></catalog>";
        boolean blocked = false;
        try {
            identity(hostile);
        } catch (TransformerException | XMLStreamException expected) {
            blocked = true;
        }
        check(blocked, "DOCTYPE should be rejected");
        System.out.println("doctype-blocked=true");
        System.out.println("tests=PASS");
    }
}
~~~

### 8.2. Lệnh chạy và stdout chính xác

~~~bash
javac -encoding UTF-8 --release 17 StaxJaxpTransformDemo.java
java StaxJaxpTransformDemo
~~~

Đã biên dịch và chạy thành công trên **OpenJDK 24, target Java 17**, stdout:

~~~text
identity-titles=2
identity-first=Xin & chào
xslt-items=2
xslt-second=Java StAX
doctype-blocked=true
tests=PASS
~~~

Giải thích: identity giữ đúng hai `title`; `&amp;` trong XML được giải mã thành ký tự `&` khi kiểm tra text. XSLT 1.0 đổi `catalog/book/title` thành `summary/item`; event writer tạo output mà parser đọc lại thành công. DTD/XXE payload của fixture bị từ chối trên JDK provider đã thử. **Không coi kết quả này là bằng chứng mọi XSLT provider đều stream bộ nhớ O(1)**.

### 8.3. Vì sao không in raw XML output?

Serialization XML có thể khác XML declaration, attribute quotes hoặc prefix nhưng cùng ý nghĩa. Demo so sánh dữ liệu parse lại, tránh hứa output **byte-for-byte** mà identity transformation không bảo đảm.

## 9. Ví dụ Java 17+: XSD validation từ StAXSource ra StAXResult

`StaxJaxpValidationDemo.java` chứng minh việc **validator nhận StAX input**, XSD validation và kết quả output đúng cặp:

- Dùng `SchemaFactory.newInstance(XMLConstants.W3C_XML_SCHEMA_NS_URI)`.
- Bật `FEATURE_SECURE_PROCESSING`, chặn `ACCESS_EXTERNAL_DTD` và `ACCESS_EXTERNAL_SCHEMA`.
- `Validator.validate(StAXSource, StAXResult)` cho XML hợp lệ.
- `Validator.validate(StAXSource)` (Result null) từ chối `amount=-3` vì `xs:positiveInteger`.
- `Validator.validate(StAXSource, StreamResult)` bị từ chối vì cặp Source/Result không tương thích.

### 9.1. File StaxJaxpValidationDemo.java

~~~java
import java.io.*;
import javax.xml.XMLConstants;
import javax.xml.stream.*;
import javax.xml.transform.*;
import javax.xml.transform.stax.*;
import javax.xml.transform.stream.*;
import javax.xml.validation.*;
import org.xml.sax.SAXException;

public final class StaxJaxpValidationDemo {
    private static final String XSD = """
            <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
              <xs:element name="orders">
                <xs:complexType><xs:sequence>
                  <xs:element name="order" minOccurs="1" maxOccurs="unbounded">
                    <xs:complexType><xs:sequence>
                      <xs:element name="amount" type="xs:positiveInteger"/>
                    </xs:sequence>
                      <xs:attribute name="id" type="xs:string" use="required"/>
                    </xs:complexType>
                  </xs:element>
                </xs:complexType>
              </xs:element>
            </xs:schema>
            """;
    private static final String VALID =
            "<orders><order id='A'><amount>12</amount></order>"
          + "<order id='B'><amount>7</amount></order></orders>";
    private static final String INVALID =
            "<orders><order id='A'><amount>-3</amount></order></orders>";

    static XMLInputFactory secureInputFactory() {
        XMLInputFactory f = XMLInputFactory.newFactory();
        f.setProperty(XMLInputFactory.SUPPORT_DTD, false);
        f.setProperty(XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
        f.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        f.setXMLResolver((publicId, systemId, base, ns) -> {
            throw new XMLStreamException("External resource denied");
        });
        return f;
    }

    static Schema safeSchema() throws Exception {
        SchemaFactory factory =
                SchemaFactory.newInstance(XMLConstants.W3C_XML_SCHEMA_NS_URI);
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        try (StringReader schemaText = new StringReader(XSD)) {
            return factory.newSchema(new StreamSource(schemaText));
        }
    }

    static Validator newSafeValidator(Schema schema) throws Exception {
        Validator validator = schema.newValidator();
        validator.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        validator.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        return validator;
    }

    static String validateToStax(Schema schema, String xml) throws Exception {
        try (StringReader source = new StringReader(xml);
             StringWriter destination = new StringWriter()) {
            XMLStreamReader reader =
                    secureInputFactory().createXMLStreamReader(source);
            XMLStreamWriter writer = XMLOutputFactory.newFactory()
                    .createXMLStreamWriter(destination);
            try {
                newSafeValidator(schema).validate(
                        new StAXSource(reader), new StAXResult(writer));
                writer.flush();
                return destination.toString();
            } finally {
                writer.close();
                reader.close();
            }
        }
    }

    static boolean rejectsBadAmount(Schema schema) throws Exception {
        try (StringReader source = new StringReader(INVALID)) {
            XMLStreamReader reader =
                    secureInputFactory().createXMLStreamReader(source);
            try {
                newSafeValidator(schema).validate(new StAXSource(reader));
                return false;
            } catch (SAXException expected) {
                return true;
            } finally {
                reader.close();
            }
        }
    }

    static boolean rejectsMismatchedResult(Schema schema) throws Exception {
        try (StringReader source = new StringReader(VALID);
             StringWriter sink = new StringWriter()) {
            XMLStreamReader reader =
                    secureInputFactory().createXMLStreamReader(source);
            try {
                newSafeValidator(schema).validate(
                        new StAXSource(reader), new StreamResult(sink));
                return false;
            } catch (IllegalArgumentException expected) {
                return true;
            } finally {
                reader.close();
            }
        }
    }

    static int countOrders(String xml) throws Exception {
        int count = 0;
        try (StringReader source = new StringReader(xml)) {
            XMLStreamReader reader =
                    secureInputFactory().createXMLStreamReader(source);
            try {
                while (reader.hasNext()) {
                    if (reader.next() == XMLStreamConstants.START_ELEMENT
                            && reader.getLocalName().equals("order")) count++;
                }
            } finally {
                reader.close();
            }
        }
        return count;
    }

    public static void main(String[] args) throws Exception {
        Schema schema = safeSchema();
        String output = validateToStax(schema, VALID);
        int orders = countOrders(output);
        if (orders != 2) throw new AssertionError("validated output invalid: " + output);
        System.out.println("validated-orders=" + orders);
        if (!rejectsBadAmount(schema)) {
            throw new AssertionError("Schema must reject negative amount");
        }
        System.out.println("invalid-amount-rejected=true");
        if (!rejectsMismatchedResult(schema)) {
            throw new AssertionError("StAXSource to StreamResult must be rejected");
        }
        System.out.println("cross-result-rejected=true");
        System.out.println("tests=PASS");
    }
}
~~~

### 9.2. Lệnh chạy và stdout chính xác

~~~bash
javac -encoding UTF-8 --release 17 StaxJaxpValidationDemo.java
java StaxJaxpValidationDemo
~~~

Đã compile/run trên OpenJDK 24 với Java 17 target, stdout:

~~~text
validated-orders=2
invalid-amount-rejected=true
cross-result-rejected=true
tests=PASS
~~~

Ý nghĩa:
- `validated-orders=2`: XML input hai `order` hợp XSD và validated output qua StAXResult có thể parse lại.
- `invalid-amount-rejected=true`: `xs:positiveInteger` từ chối giá trị âm.
- `cross-result-rejected=true`: `StAXSource + StreamResult` bị JAXP Validator từ chối đúng contract.
- `tests=PASS`: các assertions chạy thành công trên JDK provider đã thử; không chứng minh các provider khác hoặc mọi schema sẽ cho cùng performance.

**Chú ý:** ứng dụng nên validate output sau XSLT nếu hợp đồng đòi kết quả cũng tuân XSD. Input valid không có nghĩa stylesheet không làm thay đổi cấu trúc sang một output không hợp schema.

## 10. Giới hạn bộ nhớ và lifecycle: điều adapter không giải quyết hộ

### 10.1. XSLT có thể materialize tree

Dù input là StAXSource và output StAXResult, transformer cần truy cập XPath qua nhiều nodes, sorting/grouping, ancestor/descendant relations hoặc cross-document references có thể dùng cây nội bộ/buffers. **StAXSource không hứa XSLT sẽ dùng O(1) heap**.

Với yêu cầu streaming nghiêm ngặt, cân nhắc xử lý record bằng **XMLStreamReader → XMLStreamWriter** trực tiếp hoặc provider XSLT có streaming contract đã được kiểm chứng. So sánh peak heap, GC allocations, CPU, throughput trên cùng XML và stylesheet thực.

### 10.2. Output cũng phải bounded

`StringWriter` và `ByteArrayOutputStream` giữ **toàn bộ output** trong RAM; `DOMResult` giữ DOM tree. Demo sử dụng StringWriter vì XML nhỏ và cần assert. Với dữ liệu lớn, ghi vào file/OutputStream/queue **có giới hạn**, áp dụng backpressure. Tuy nhiên ngay cả output streaming không loại bỏ buffering của transformer.

### 10.3. Input StreamSource không mặc định đọc toàn bộ

Một `StreamSource(InputStream)` có thể được đọc tuần tự bởi JAXP provider, nhưng không đảm bảo internal algorithm memory. Nếu bạn **không cần** StAX reader do application quản lý, StreamSource/StreamResult có thể đủ đơn giản. Đừng tự `Files.readString` tạo một String lớn rồi kết luận “JAXP không thể stream”.

### 10.4. Close đúng

- Caller sở hữu `InputStream`/`Reader`, phải đóng riêng.
- `XMLStreamReader.close()`/`XMLEventReader.close()` không bắt buộc đóng source đã truyền.
- `XMLStreamWriter.close()`/`XMLEventWriter.close()` không bắt buộc đóng underlying Writer/OutputStream.
- StAXSource/StAXResult không cung cấp ownership wrapper kiểu try-with-resources.
- Nên dùng `finally` cho StAX reader/writer và try-with-resources cho source/sink.
- Nếu transform/validate và cleanup cùng lỗi, bảo toàn primary và suppressed errors.
- Một writer có thể cần `flush()` trước khi đọc output/đóng sink.

### 10.5. XML file output có thể bị ghi một phần

Nếu Transformer lỗi khi ghi file, file đích có thể chỉ chứa nửa XML. Với dữ liệu quan trọng, ghi vào temp file, verify hoàn chỉnh/XSD/size/checksum rồi publish atomically nếu filesystem hỗ trợ. Kiểm tra path traversal, quyền ghi, symlink, disk quotas và cancellation.

## 11. Những lỗi tích hợp thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `StAXSource` ném `IllegalStateException` | Reader ở event sai | Đặt START_DOCUMENT/START_ELEMENT |
| StAXSource được transform hai lần | Reader đã consumed | Tạo reader/source mới |
| Validator nhận `StAXSource+StreamResult` | Cặp Result không hợp lệ | Dùng StAXResult hoặc identity Transformer |
| Quên cấu hình XMLInputFactory | XXE/DTD còn khả năng hoạt động | DTD/external access off, deny resolver |
| Cấu hình Transformer nhưng không cấu hình XSD | Schema import có thể tải URL | ACCESS_EXTERNAL_SCHEMA ở SchemaFactory/Validator |
| Chỉ bật FEATURE_SECURE_PROCESSING | Chưa kiểm soát mọi refs/quotas | Đặt ACCESS_EXTERNAL_* rõ và bounds |
| Catch rồi bỏ qua unsupported security property | Provider parse không an toàn | Fail closed hoặc thay provider |
| XSLT gọi document() tới URL | Có nguy cơ SSRF/file access | ACCESS_EXTERNAL_STYLESHEET="", deny resolver |
| XML có DTD được event parser xử lý | Thiếu event-specific rejection | Filter/từ chối DTD, test provider |
| Đóng StAX reader mà không đóng InputStream | Leak file/socket resources | Source try-with-resources |
| Đóng StAX writer nhưng không đóng OutputStream | Leak/partial output | Sink try-with-resources, flush |
| Identity output khác dấu nháy/whitespace | Serialization không byte-identical | So XML semantics, canonicalize đúng chuẩn nếu cần |
| XSLT tốn heap mặc dù dùng StAXSource | Transformer materialize tree | Benchmark; dùng direct StAX khi phù hợp |
| Output dùng StringWriter quá lớn | Giữ cả output trong RAM | Stream to bounded sink |
| Validate input rồi reuse Source để transform | StAXSource single-use | Reopen input/new reader |
| Share một Validator giữa nhiều threads | Validator not thread-safe | Tạo mỗi request hoặc quản lý pool chuẩn |
| XML đúng XSD nhưng sai business rule | XSD chưa bao phủ nghiệp vụ | Business validation bổ sung |
| Parser/provider thay sau deploy | Features/behavior khác | Integration tests với provider/version |

## 12. Kiểm thử thực tế và các tình huống cần QA

| Test | Đầu ra mong đợi |
| --- | --- |
| StAXSource cursor START_DOCUMENT | Transformer xử lý đúng |
| StAXSource event reader START_DOCUMENT | XSLT xử lý đúng |
| StAXSource cursor START_ELEMENT subtree | Tên/namespace/context hợp lệ |
| Reader tại CHARACTERS hoặc END_DOCUMENT | Bị từ chối precondition |
| StAXSource bị tiêu thụ rồi reuse | Không chạy lại; dùng reader mới |
| StAXResult XMLStreamWriter | XML parse lại hợp lệ |
| StAXResult XMLEventWriter | XML parse lại hợp lệ |
| Identity transform | Bảo toàn dữ liệu có ý nghĩa |
| XSLT transform | Cấu trúc output đúng |
| getFeature SOURCE/RESULT | Provider báo hỗ trợ |
| XSLT import/include/document() | External access bị chặn |
| XML DOCTYPE/entities | Không đọc file/network bất hợp pháp |
| XSD import/include | ACCESS_EXTERNAL_SCHEMA hoạt động |
| Validator StAXSource + null | Valid/invalid phát hiện |
| Validator StAXSource + StAXResult | Validated output đúng |
| Validator StAXSource + StreamResult | IllegalArgumentException |
| Malformed XML | Exception chứa diagnostics phù hợp |
| Unicode/emoji/namespaces | Không mất ký tự hoặc nhầm prefixes |
| Rất nhiều elements/text dài | Heap/GC/timeouts nằm trong budget |
| Sink failure giữa transform | No partial publish, resources closed |
| Provider đổi version | Compatibility/security không suy từ demo JDK |
| Concurrent requests | Không share readers/validators mutable state |

### 12.1. So sánh performance một cách công bằng

Sử dụng cùng JDK/provider, XML/XSD/XSLT/output semantics, đo warmup, peak heap, allocations, GC pauses, time/record và native/temp disk. Với XSLT sort/group rất lớn có thể không đạt memory bound dù StAX adapter có mặt; benchmark chính pipeline chứ không chỉ số lần gọi `reader.next()`.

### 12.2. Không có “XML streaming = luôn an toàn”

StAX chỉ cung cấp cách kéo dữ liệu. XXE, entity expansion, XML quá sâu, input vô hạn, output amplification, XSLT recursion và path access vẫn cần kiểm soát. Thực thi security policy ở **mọi tầng** và **fail closed** nếu provider không hỗ trợ thuộc tính bắt buộc.

## 13. Câu hỏi tự đánh giá

**1.** StAXSource bọc gì?

**Đáp án:** XMLStreamReader hoặc XMLEventReader thành JAXP Source.

**2.** StAXResult bọc gì?

**Đáp án:** XMLStreamWriter hoặc XMLEventWriter thành JAXP Result.

**3.** Các adapter nằm ở đâu, có lỗi thời không?

**Đáp án:** `javax.xml.transform.stax`, module `java.xml`, từ Java 6 và còn hỗ trợ ở Java SE 26.

**4.** Reader phải ở event nào lúc tạo StAXSource?

**Đáp án:** `START_DOCUMENT` hoặc `START_ELEMENT`, và reader không null.

**5.** Có thể dùng cùng StAXSource cho validate rồi transform?

**Đáp án:** Không. Nguồn bị tiêu thụ; cần reader/source mới hoặc pipeline khác.

**6.** Identity Transformer có bảo đảm cùng bytes với XML đầu vào?

**Đáp án:** Không. XML serializer có thể khác XML declaration, whitespace/quotes/prefixes dù cấu trúc đúng.

**7.** Validator có chấp nhận StAXSource cùng StreamResult?

**Đáp án:** Không. Dùng null/StAXResult, hoặc dùng identity Transformer nếu muốn chuyển kiểu.

**8.** Có thể dùng `StAXResult` để ghi file không?

**Đáp án:** Có nếu underlying XMLStreamWriter/XMLEventWriter được tạo trên file/stream sink, nhưng adapter không tự quản lý file.

**9.** StAXSource có bảo đảm XSLT O(1) memory?

**Đáp án:** Không. Transformer có thể giữ cây/buffer nội bộ; cần benchmark.

**10.** Vì sao dùng ACCESS_EXTERNAL_STYLESHEET với XSLT?

**Đáp án:** Chặn stylesheet imports/includes và external document() access, tránh file/network exposure.

**11.** Vì sao dùng ACCESS_EXTERNAL_SCHEMA với XSD?

**Đáp án:** Chặn external schema references, không nhầm với stylesheet property.

**12.** Vì sao close StAX reader chưa đủ?

**Đáp án:** Caller vẫn phải close InputStream/Reader nguồn.

**13.** Vì sao demo dùng StringWriter nhưng production nên cẩn thận?

**Đáp án:** StringWriter giữ toàn bộ XML output trên heap; chỉ hợp lý cho output nhỏ/giới hạn.

**14.** `Validator` có thread-safe không?

**Đáp án:** Không. Tạo validator phù hợp mỗi request/operation.

### Bài tập thực hành

1. Chạy `StaxJaxpTransformDemo`, thêm title có tiếng Việt/emoji, kiểm tra dữ liệu parse lại.
2. Thay identity `XMLStreamReader` bằng `XMLEventReader`, so sánh constructor.
3. Viết identity Transformer output qua StreamResult thay cho StAXResult, xác nhận cả hai cách hợp lệ với Transformer provider.
4. Di chuyển reader tới CHARACTERS trước khi tạo StAXSource, quan sát exception.
5. Thử dùng một StAXSource hai lần, rồi sửa bằng cách mở nguồn mới.
6. Đổi XSLT 1.0 để lọc book theo attribute, xác nhận kết quả.
7. Viết test XSLT dùng `document()` và bảo đảm bị deny.
8. Chạy `StaxJaxpValidationDemo`, sửa amount thành -3 để xác nhận SAXException.
9. Thử cặp StAXSource/StreamResult trong Validator và ghi nhận IllegalArgumentException.
10. Thêm XSD import từ URL trong môi trường test và xác nhận external access bị chặn.
11. Thiết kế đoạn code đọc XML từ file lớn và ghi XML ra temp file, không dùng StringWriter.
12. Benchmark StAXSource + XSLT so với direct StAX reader→writer trên dữ liệu lớn.
13. Kiểm tra behavior và security khi thay JAXP provider/version khác.
14. Viết workflow validate → transform → validate output, mỗi lượt có reader riêng.
15. Dùng checksum + atomic publish để tránh file XML nửa chừng khi output sink thất bại.

## 14. Tài liệu chính thức và nguồn tham khảo

- [Oracle Java SE 26 — StAXSource](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/transform/stax/StAXSource.html): single-use, constructor preconditions, FEATURE.
- [Oracle Java SE 26 — StAXResult](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/transform/stax/StAXResult.html): XMLStreamWriter/XMLEventWriter adapter.
- [Oracle Java SE 26 — package javax.xml.transform.stax](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/transform/stax/package-summary.html): Source/Result mapping.
- [Oracle Java SE 26 — TransformerFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/transform/TransformerFactory.html): identity/XSLT, features, external access.
- [Oracle Java SE 26 — Transformer](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/transform/Transformer.html): transform(Source, Result).
- [Oracle Java SE 26 — Source](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/transform/Source.html): abstraction đầu vào.
- [Oracle Java SE 26 — Result](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/transform/Result.html): abstraction đầu ra.
- [Oracle Java SE 26 — XMLInputFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLInputFactory.html): StAX parser security properties.
- [Oracle Java SE 26 — XMLStreamReader](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLStreamReader.html): cursor and close.
- [Oracle Java SE 26 — XMLEventReader](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLEventReader.html): event reader.
- [Oracle Java SE 26 — XMLOutputFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLOutputFactory.html): tạo XML writers.
- [Oracle Java SE 26 — XMLStreamWriter](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLStreamWriter.html): writer contract.
- [Oracle Java SE 26 — XMLEventWriter](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLEventWriter.html): event writer.
- [Oracle Java SE 26 — Validator](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/validation/Validator.html): cặp Source/Result hợp lệ.
- [Oracle Java SE 26 — SchemaFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/validation/SchemaFactory.html): XSD compilation.
- [Oracle Java SE 26 — XMLConstants](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/XMLConstants.html): FEATURE_SECURE_PROCESSING, ACCESS_EXTERNAL_*.
- [Oracle Java SE 26 — java.xml module](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/module-summary.html): API hiện hành.
- [Oracle Java SE 17 — StAXSource](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/transform/stax/StAXSource.html): tham chiếu cho `javac --release 17`.
- [OWASP — XML External Entity Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html): chống XML XXE/SSRF.

**Ghi nhớ:** `StAXSource` đưa **StAX reader** vào JAXP `Source`, `StAXResult` đưa JAXP `Result` ra **StAX writer**. Đây là các API Java 6 còn áp dụng, giúp tích hợp identity/XSLT transformation và XSD validation mà không buộc application tự tạo DOM. Nhưng `StAXSource` bị **tiêu thụ sau một lần dùng**, `Validator` chỉ cho cặp `StAXSource+StAXResult` hoặc Result null, và **adapter không bảo đảm XSLT dùng bộ nhớ O(1)**. Luôn cấu hình DTD/external access ở mọi tầng, giới hạn input/output và đóng cả reader/writer lẫn source/sink.
