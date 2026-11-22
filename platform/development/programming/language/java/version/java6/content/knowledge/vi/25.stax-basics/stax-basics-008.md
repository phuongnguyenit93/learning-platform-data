# Đóng StAX reader cùng nguồn I/O trong Java 17+: ownership, close và xử lý lỗi

## 1. Tại sao đọc XML xong mà tài nguyên vẫn có thể còn mở?

**StAX (Streaming API for XML)** xử lý XML theo mô hình *pull*: application chủ động gọi `XMLStreamReader.next()` hoặc `XMLEventReader.nextEvent()` để nhận sự kiện tiếp theo. Một StAX reader thường được tạo từ một `InputStream` hoặc `Reader` do ứng dụng mở từ file, HTTP request, network, hoặc một tầng dữ liệu khác.

Ở đây có **ít nhất hai tài nguyên khác nhau**:

1. **StAX reader**, chẳng hạn `javax.xml.stream.XMLStreamReader` hoặc `XMLEventReader`: giữ trạng thái parse, bộ đệm và tài nguyên riêng của XML processor.
2. **Nguồn I/O**, chẳng hạn `java.io.InputStream`/`Reader`: giữ file descriptor, socket, ZIP entry hoặc nguồn dữ liệu được application cung cấp.

**Javadoc Java SE 25 của cả `XMLStreamReader.close()` lẫn `XMLEventReader.close()` nêu rõ: method giải phóng tài nguyên của StAX reader nhưng *không đóng nguồn input bên dưới*.** Vì vậy một lời gọi `xml.close()` **không thay thế** `input.close()`/`reader.close()`. Ngược lại, chỉ đóng InputStream mà không đóng StAX reader cũng bỏ qua bước cleanup parser.

Đây là hợp đồng quan trọng nhất của bài:

~~~text
Application tạo và sở hữu nguồn I/O
         │
         ├── InputStream / Reader       <-- ứng dụng đóng nguồn
         │         │
         │         ▼
         └── XMLInputFactory
                     │
                     ▼
             XMLStreamReader / XMLEventReader
                     │
                     ├── next()/nextEvent()
                     └── close()         <-- ứng dụng đóng StAX reader

Thứ tự kết thúc:
    (1) Dừng đọc và đóng StAX reader
    (2) Đóng Reader/InputStream gốc nếu caller sở hữu
~~~

**Đóng theo thứ tự ngược lúc mở**: resource được tạo sau (StAX reader) đóng trước; resource được tạo trước (nguồn I/O) đóng sau. Phải giữ quy tắc này khi đọc hết, dừng sớm, XML sai, parser bị hủy do exception, hoặc downstream consumer thất bại.

Không phải mọi nguồn đều thuộc quyền sở hữu của method parse: `System.in`, một shared network stream hay stream được framework quản lý có thể là **borrowed resource**. Nếu method không sở hữu input, nó không nên tự đóng nguồn ấy; hợp đồng caller/callee phải rõ. Khi có yêu cầu ngăn parser/provider đóng borrowed source, có thể cần một **non-closing wrapper** được thiết kế và kiểm thử riêng.

Các API này vẫn là Java SE hiện hành, thuộc module `java.xml` và package `javax.xml.stream` trong **Java 17+**. Không dùng `jakarta.xml.stream` hoặc một JAR JSR 173 standalone cũ để thay thế JDK API khi không có yêu cầu đặc biệt.

## 2. Đọc đúng Javadoc: `close()` thực sự bảo đảm gì?

| API | Tên close | Đối tượng chịu trách nhiệm dọn | Có bảo đảm đóng I/O bên dưới không? |
| --- | --- | --- | --- |
| `XMLStreamReader` | `close()` | Trạng thái và tài nguyên riêng của cursor parser | **Không**; Javadoc nói rõ không đóng underlying input |
| `XMLEventReader` | `close()` | Trạng thái và tài nguyên riêng của event parser | **Không**; Javadoc nói rõ không đóng underlying input |
| `InputStream` | `close()` | Dữ liệu nguồn và I/O resource do stream quản lý | Có, theo implementation của stream |
| `Reader` | `close()` | Nguồn ký tự/bộ giải mã và tài nguyên do reader quản lý | Có, theo implementation của reader |
| `XMLStreamWriter` | `close()` | Trạng thái và tài nguyên riêng của XML writer | Javadoc nói rõ **không được đóng underlying output stream** |
| `OutputStream` / `Writer` | `close()` | Đích I/O do writer hoặc stream quản lý | Có, theo implementation của resource |
| `XMLEventWriter` | `close()` | Tài nguyên StAX event writer | Contract không nói rõ giống `XMLStreamWriter` về underlying output; tự quản lý ownership/kiểm thử provider |

StAX `close()` có thể ném **`XMLStreamException`**, vì parser hoặc provider vẫn phải giải phóng tài nguyên. `InputStream.close()` và `Reader.close()` có thể ném **`IOException`** tùy implementation. Nếu parse và close đều lỗi, phải giữ nguyên lỗi parse chính và thông tin về close lỗi — không được âm thầm nuốt một trong hai.

### Hai StAX reader interface có phải `AutoCloseable` không?

Không. Trong Java SE 17/25, **`XMLStreamReader` và `XMLEventReader` không khai báo kế thừa `AutoCloseable`**, dù cả hai có method tên `close()`. Vì vậy đoạn sau **không biên dịch** nếu kiểu biến là `XMLStreamReader`:

~~~java
// Sai: XMLStreamReader không implement AutoCloseable.
// try (XMLStreamReader xml = factory.createXMLStreamReader(input)) {
//     // ...
// }
~~~

Đây là **anti-pattern cố ý được comment**, không phải chương trình chạy. Java `try-with-resources` chỉ nhận các biến có kiểu triển khai `AutoCloseable`. Có hai lựa chọn hiện đại:

- Dùng **`try/finally`** để luôn gọi `xml.close()`, đồng thời bọc nguồn trong `try-with-resources`.
- Tạo **một adapter nhỏ `AutoCloseable`** bọc StAX reader, để Java try-with-resources đóng cả parser lẫn nguồn và tự giữ *suppressed exceptions*.

Không phải vì interface StAX không AutoCloseable mà cần thư viện legacy. Một adapter nhỏ Java 17 là đủ.

### Một nuance thực tế: đã parse đến EOF thì nguồn có thể bị provider tác động trước

Contract nói `XMLStreamReader.close()` và `XMLEventReader.close()` **không đóng input source**. Nhưng đừng biến câu đó thành giả định “nguồn chắc chắn còn mở cho đến sau `close()` bất kể quá trình parse”. Trong phép thử với **built-in `XMLEventReader` của OpenJDK 24.0.2**, khi application đã tiêu thụ **toàn bộ tài liệu**, đường implementation có thể gọi `close()` lên source ngay lúc đi đến cuối event stream — *trước cả lời gọi reader.close()*. Khi dừng **trước EOF** trong ví dụ chạy ở phần 6, `XMLEventReader.close()` để nguồn vẫn mở như API mô tả.

Điều này minh họa tại sao ứng dụng cần **ownership protocol**, thay vì kiểm tra cứng “source nhất định vẫn mở sau khi đọc đến END_DOCUMENT” hoặc dựa vào parser cleanup để đóng source. Tùy provider và thời điểm đọc, nguồn có thể đã đóng; lời gọi `close()` thứ hai trên nhiều streams JDK là an toàn nhưng **không tự suy ra mọi borrowed stream có cùng semantics**.

**Bài học thực hành:** nếu method **sở hữu nguồn**, nó phải đóng nguồn trong mọi đường thoát. Nếu method chỉ **mượn nguồn** và caller cần dùng tiếp, thiết kế explicit non-closing boundary hoặc đọc vào một stream độc lập theo policy; không trông chờ generic parser luôn giữ borrowed source còn mở.

## 3. Mẫu cơ bản: `try-with-resources` cho nguồn, `finally` cho StAX reader

Khi mở file bằng `Files.newInputStream`:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLStreamReader;

static void parseFile(Path file) throws Exception {
    XMLInputFactory factory = secureInputFactory();

    try (InputStream source = Files.newInputStream(file)) {
        XMLStreamReader xml = factory.createXMLStreamReader(source);
        try {
            while (xml.hasNext()) {
                int event = xml.next();
                // Xử lý sự kiện trong phạm vi file/reader còn mở.
            }
        } finally {
            xml.close(); // Dọn parser, dù đọc lỗi hoặc dừng sớm.
        }
    } // Dọn InputStream do phương thức mở.
}
~~~

**Đây là đoạn minh họa trong class**, cần có `secureInputFactory()` được implement bằng các StAX settings bảo mật ở phần 9. Không phải file độc lập để chạy; vì `throws Exception`, ví dụ truyền lại `IOException`/`XMLStreamException` cho caller. `XMLStreamReader` không nằm trực tiếp trong resource list vì nó không implement AutoCloseable.

**Điểm mạnh:** dễ hiểu, đóng đủ hai tầng, việc tạo parser nằm **bên trong** `try` của source. Nếu `factory.createXMLStreamReader(source)` ném exception khi khởi tạo, chưa có parser để đóng nhưng try-with-resources vẫn đóng `source` đã mở.

**Giới hạn:** nếu `xml.next()` ném một `XMLStreamException` rồi `xml.close()` trong `finally` cũng ném lỗi khác, lỗi close có thể thay thế lỗi parse gốc theo cơ chế `finally` thông thường. Với các đường xử lý có giá trị vận hành, hãy dùng adapter/try-with-resources như phần tiếp theo hoặc tự bảo toàn primary exception bằng `addSuppressed`.

### Mẫu tương tự cho `XMLEventReader`

~~~java
try (InputStream source = Files.newInputStream(file)) {
    XMLEventReader events = secureInputFactory().createXMLEventReader(source);
    try {
        while (events.hasNext()) {
            XMLEvent event = events.nextEvent();
            // Không giữ references đến nguồn sau khi scope kết thúc.
        }
    } finally {
        events.close();
    }
}
~~~

Đây cũng là đoạn **trong method** với `file` đã có; cần imports `java.io.InputStream`, `java.nio.file.Files`, `javax.xml.stream.XMLEventReader`, `javax.xml.stream.events.XMLEvent`. Thứ tự cleanup vẫn là **`events.close()` trước `source.close()`**.

### InputStream hay Reader?

Cả hai dùng được:

~~~java
// Bytes: XML parser tự xử lý BOM/declaration và encoding XML.
XMLStreamReader fromBytes = factory.createXMLStreamReader(inputStream);

// Characters: caller đã giải mã bytes trước khi đưa vào parser.
XMLStreamReader fromChars = factory.createXMLStreamReader(reader);
~~~

Hai dòng là **API minh họa**, mỗi dòng phải dùng một nguồn còn mở, parser phải đóng sau khi xong. Nếu XML file có declaration `encoding="UTF-8"` mà application tạo Reader với một charset khác, dữ liệu có thể sai trước khi StAX nhận được. Dùng InputStream có thể giúp XML parser tuân thủ encoding declaration/BOM. Dùng Reader phù hợp khi source đã là Unicode characters hoặc charset được chọn rõ ràng ở tầng I/O.

**Không** coi `StringReader` tự động là nguồn streaming từ disk: Java `String` đã được materialize trong RAM. Trong ví dụ chạy phần 6, `StringReader` chỉ để kiểm thử lifecycle độc lập với file system; trên hệ thống thật, thay bằng FileInputStream/BufferedReader/HTTP stream theo ownership contract.

## 4. Mẫu ít lỗi hơn: bọc StAX reader bằng `AutoCloseable` nhỏ

Java `try-with-resources` có ba tính năng rất hữu ích:

1. **Đóng resources theo thứ tự ngược lúc khai báo**.
2. Nếu tạo tài nguyên sau gặp lỗi, các tài nguyên đã tạo trước vẫn được đóng.
3. Nếu body ném lỗi và đóng tài nguyên cũng ném lỗi, body exception là **primary**; close errors trở thành **suppressed exceptions** (truy cập qua `getSuppressed()`).

Ta có thể dùng adapter:

~~~java
import javax.xml.stream.XMLStreamException;
import javax.xml.stream.XMLStreamReader;

record CursorLease(XMLStreamReader reader) implements AutoCloseable {
    @Override
    public void close() throws XMLStreamException {
        reader.close();
    }
}
~~~

`record` và `AutoCloseable` đều dùng được trên Java 17. Đây là **type có thể biên dịch** trong một file Java thích hợp; cần import `XMLStreamException`, `XMLStreamReader`. Adapter không sở hữu underlying InputStream, chỉ sở hữu parser; input được scope bên ngoài quản lý.

Đọc file bằng **một resource list**:

~~~java
try (InputStream source = Files.newInputStream(file);
     CursorLease cursor =
             new CursorLease(factory.createXMLStreamReader(source))) {
    while (cursor.reader().hasNext()) {
        cursor.reader().next();
        // Xử lý các event cần thiết.
    }
}
// Java đóng CursorLease trước, rồi mới đóng InputStream.
~~~

Đây là **đoạn trong method**, cần `factory` đã cấu hình an toàn, `file` và imports. Nếu `createXMLStreamReader` ném exception, Java tự đóng `source` do phần resource khai báo trước đã thành công. Nếu parse lỗi và cả close parser lỗi, thông tin close được thêm vào `getSuppressed()` của primary error.

### Adapter cho EventReader

~~~java
record EventLease(XMLEventReader reader) implements AutoCloseable {
    @Override
    public void close() throws XMLStreamException {
        reader.close();
    }
}
~~~

Class này chỉ cần imports `XMLEventReader`, `XMLStreamException` và được dùng theo cách tương tự. Không **cast** bừa `XMLEventReader` sang `AutoCloseable`, vì interface không cam kết implement và runtime có thể ném `ClassCastException`.

### Một adapter không nhất thiết phải là class lớn

Nếu muốn tránh tạo nhiều class adapter, có thể khai báo **resource `AutoCloseable` với method reference**:

~~~java
try (InputStream source = Files.newInputStream(file)) {
    XMLStreamReader reader = factory.createXMLStreamReader(source);
    try (AutoCloseable cleanup = reader::close) {
        while (reader.hasNext()) {
            reader.next();
        }
    }
}
~~~

Đây là **đoạn trong method**, không phải file độc lập. Vì biến `cleanup` được khai báo kiểu `AutoCloseable` nên `cleanup.close()` theo interface có thể ném `Exception`; method bên ngoài phải có `throws Exception` hoặc xử lý checked exception phù hợp. Method reference chỉ ghi lại cleanup action, không làm `XMLStreamReader` tự implement AutoCloseable. Khi nguồn được mượn, bỏ phần try-with-resources cho nguồn và để caller chịu trách nhiệm, nhưng vẫn close parser.

**Mẫu adapter record** có ưu thế về type clarity, dễ giữ `XMLStreamException` và kiểm thử ownership; method reference là lựa chọn gọn khi codebase chấp nhận `throws Exception` ở boundary.

## 5. Thứ tự tạo và đóng khi đọc XML có nhiều tầng I/O

Một pipeline có thể gồm nhiều layers:

~~~text
Files.newInputStream(path)     <- FileInputStream (file descriptor)
        │
        ▼
GZIPInputStream               <- decompression layer
        │
        ▼
InputStreamReader(UTF_8)       <- bytes -> Java chars (nếu có)
        │
        ▼
BufferedReader                <- buffer (nếu có)
        │
        ▼
XMLStreamReader               <- parser state
~~~

**Chỉ layer cao nhất mà application thực sự sở hữu cần close đúng scope để đóng tuần tự các layer bọc bên dưới**, nếu mỗi layer tuân thủ contract đóng delegate. Nếu dùng tất cả cùng try-with-resources, việc đóng lặp các delegates có thể dư thừa; tránh làm vậy khi source có close semantics đặc biệt. Ví dụ với GZIP:

~~~java
try (InputStream gzip = new java.util.zip.GZIPInputStream(
        Files.newInputStream(file))) {
    XMLStreamReader xml = factory.createXMLStreamReader(gzip);
    try {
        while (xml.hasNext()) {
            xml.next();
        }
    } finally {
        xml.close();
    }
}
// gzip.close() đóng stream gốc được bọc theo contract GZIPInputStream.
~~~

Đây là **đoạn minh họa trong method**: có `file`, `factory` và checked exceptions đã xử lý/khai báo. Nếu constructor của `GZIPInputStream` ném lỗi sau khi `Files.newInputStream(file)` đã trả stream, việc tạo trực tiếp như trên khiến trách nhiệm cleanup khi khởi tạo thất bại cần được xét kỹ. Khi cần bảo đảm cả **construction failure path**, khai báo raw stream thành resource trước:

~~~java
try (InputStream raw = Files.newInputStream(file);
     InputStream gzip = new java.util.zip.GZIPInputStream(raw);
     CursorLease cursor = new CursorLease(
             factory.createXMLStreamReader(gzip))) {
    while (cursor.reader().hasNext()) {
        cursor.reader().next();
    }
}
// Đóng: cursor -> gzip -> raw (raw có thể đã được gzip đóng).
~~~

**Mẫu thứ hai đảm bảo raw stream được đóng nếu constructor GZIP hoặc StAX parser lỗi.** `GZIPInputStream.close()` có thể đã đóng raw trước; với các Java file streams chuẩn, close lặp lại thường an toàn, nhưng với nguồn custom hãy xác định ownership tránh double-close gây tác dụng phụ không mong muốn.

### Nếu dùng HTTP body, socket, ZIP hoặc JDBC SQLXML

- **Java HttpClient với `BodyHandlers.ofInputStream()`:** caller nhận `InputStream` chứa HTTP response body và phải đóng khi không dùng. Nếu response/client framework có resource owner riêng, dùng đúng lifecycle của API đó.
- **Socket:** reader có thể bọc socket input. Đóng source có thể kết thúc kết nối hoặc nửa kết nối tùy API. Chỉ method sở hữu socket mới nên quyết định lifetime; không tự đóng shared connection sau khi parse một XML fragment.
- **ZIP/GZIP:** một stream có thể đại diện cả container; đóng `ZipInputStream` khi đọc xong toàn bộ phần công việc của ZIP. Nếu caller muốn duyệt entry tiếp theo, parser không được tùy tiện đóng nguồn gốc.
- **JDBC `SQLXML.getCharacterStream()`:** SQLXML thường gắn với connection/transaction và có `free()` riêng. Phải đóng reader/stream, gọi `SQLXML.free()` và quản lý JDBC `ResultSet/Statement/Connection` theo owner; không cache stream sau transaction.
- **Message queue/object storage SDK:** một payload có stream sẽ đi cùng một response/message handle mà SDK có thể yêu cầu close/ack. StAX parser cleanup **không thay thế** ack/nack/transaction completion của SDK.

**Đóng I/O có thể mang tác dụng ngoài việc giải phóng bộ nhớ**: với network stream nó có thể hủy request hoặc khiến caller không đọc tiếp được, nên ownership là một phần của **business/API contract**, không chỉ “tối ưu hiệu năng”.

## 6. Chương trình Java 17+ hoàn chỉnh: theo dõi parser và nguồn I/O đóng lúc nào

Ví dụ này dùng JDK thuần, **không cần Maven, file thật, database hoặc mạng**. Chúng ta tạo các nguồn theo dõi `close()`:

- `TrackedReader` kế thừa `StringReader` và báo khi bị đóng.
- `TrackedInputStream` kế thừa `ByteArrayInputStream` để theo dõi đóng stream bytes.
- `TrackedOutputStream` theo dõi đầu ra XML.
- `CursorLease`, `EventLease` và `WriterLease` implement `AutoCloseable`, bọc close của ba StAX interfaces.
- `readCursor()` dừng parse sớm khi gặp item đầu tiên, đóng StAX cursor trước, rồi mới đóng Reader.
- `readEvents()` cũng dừng **trước EOF** để minh họa `XMLEventReader.close()` không làm thay công việc đóng InputStream.
- `readMalformed()` cho parser cố ý gặp XML sai, chứng minh lỗi cũng không bỏ sót nguồn.
- `writeOutput()` cho thấy `XMLStreamWriter.close()` không đóng OutputStream, trong khi `writeCharacters` escape XML text.
- Factory chỉ sử dụng API hiện đại, cấm DTD/external entities và external DTD access.

Đây là phép thử **với default StAX provider của OpenJDK 24.0.2**, tương thích Java 17. Kết quả chi tiết giữa các providers có thể khác, nhất là khi parse đến EOF; nhưng trách nhiệm sở hữu I/O không thay đổi.

Tạo file **`StaxResourceDemo.java`** với mã đầy đủ:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.StringReader;
import java.nio.charset.StandardCharsets;
import javax.xml.XMLConstants;
import javax.xml.stream.XMLEventReader;
import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLOutputFactory;
import javax.xml.stream.XMLStreamConstants;
import javax.xml.stream.XMLStreamException;
import javax.xml.stream.XMLStreamReader;
import javax.xml.stream.XMLStreamWriter;
import javax.xml.stream.events.XMLEvent;

public final class StaxResourceDemo {
    private static final String XML =
            "<items><item>A &amp; B</item><item>Ti\u1EBFng Vi\u1EC7t \uD83D\uDE00</item></items>";

    static final class TrackedReader extends StringReader {
        private boolean closed;
        TrackedReader(String value) { super(value); }
        @Override public void close() {
            closed = true;
            super.close();
        }
        boolean closed() { return closed; }
    }

    static final class TrackedInputStream extends ByteArrayInputStream {
        private boolean closed;
        TrackedInputStream(byte[] bytes) { super(bytes); }
        @Override public void close() throws IOException {
            closed = true;
            super.close();
        }
        boolean closed() { return closed; }
    }

    static final class TrackedOutputStream extends ByteArrayOutputStream {
        private boolean closed;
        @Override public void close() throws IOException {
            closed = true;
            super.close();
        }
        boolean closed() { return closed; }
    }

    // StAX API interfaces do not implement AutoCloseable in Java 17.
    // These small leases allow reverse-order try-with-resources cleanup.
    static final class CursorLease implements AutoCloseable {
        final XMLStreamReader reader;
        CursorLease(XMLStreamReader reader) { this.reader = reader; }
        @Override public void close() throws XMLStreamException { reader.close(); }
    }

    static final class EventLease implements AutoCloseable {
        final XMLEventReader reader;
        EventLease(XMLEventReader reader) { this.reader = reader; }
        @Override public void close() throws XMLStreamException { reader.close(); }
    }

    static final class WriterLease implements AutoCloseable {
        final XMLStreamWriter writer;
        WriterLease(XMLStreamWriter writer) { this.writer = writer; }
        @Override public void close() throws XMLStreamException { writer.close(); }
    }

    static XMLInputFactory secureFactory() {
        XMLInputFactory factory = XMLInputFactory.newDefaultFactory();
        factory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
        factory.setProperty(XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setXMLResolver((publicId, systemId, baseUri, namespace) -> {
            throw new XMLStreamException("External XML resource forbidden");
        });
        return factory;
    }

    static void readCursor() throws XMLStreamException {
        TrackedReader input = new TrackedReader(XML);
        try (input) {
            try (CursorLease lease = new CursorLease(
                    secureFactory().createXMLStreamReader(input))) {
                XMLStreamReader reader = lease.reader;
                while (reader.hasNext()) {
                    if (reader.next() == XMLStreamConstants.START_ELEMENT
                            && "item".equals(reader.getLocalName())) {
                        System.out.println("cursor first item: " + reader.getElementText());
                        break;
                    }
                }
            }
            System.out.println("cursor close leaves Reader open: " + !input.closed());
        }
        System.out.println("Reader closed after scope: " + input.closed());
    }

    static void readEvents() throws Exception {
        TrackedInputStream input = new TrackedInputStream(
                XML.getBytes(StandardCharsets.UTF_8));
        try (input) {
            try (EventLease lease = new EventLease(
                    secureFactory().createXMLEventReader(input))) {
                int consumed = 0;
                while (lease.reader.hasNext()) {
                    XMLEvent event = lease.reader.nextEvent();
                    if (event.isStartElement()
                            && "item".equals(event.asStartElement()
                                    .getName().getLocalPart())) {
                        consumed++;
                        break; // Stop before EOF; main purpose is close ownership.
                    }
                }
                System.out.println("event items consumed: " + consumed);
            }
            System.out.println("event close leaves InputStream open: " + !input.closed());
        }
        System.out.println("InputStream closed after scope: " + input.closed());
    }

    static void readMalformed() throws XMLStreamException {
        TrackedReader input = new TrackedReader("<items><item>broken</items>");
        boolean rejected = false;
        try (input) {
            try (CursorLease lease = new CursorLease(
                    secureFactory().createXMLStreamReader(input))) {
                while (lease.reader.hasNext()) {
                    lease.reader.next();
                }
            } catch (XMLStreamException malformed) {
                rejected = true;
            }
        }
        System.out.println("malformed XML rejected: " + rejected);
        System.out.println("malformed source closed: " + input.closed());
    }

    static void writeOutput() throws Exception {
        TrackedOutputStream output = new TrackedOutputStream();
        try (output) {
            try (WriterLease lease = new WriterLease(
                    XMLOutputFactory.newDefaultFactory()
                            .createXMLStreamWriter(output, "UTF-8"))) {
                XMLStreamWriter writer = lease.writer;
                writer.writeStartDocument("UTF-8", "1.0");
                writer.writeStartElement("items");
                writer.writeStartElement("item");
                writer.writeCharacters("A & B");
                writer.writeEndElement();
                writer.writeEndElement();
                writer.writeEndDocument();
                writer.flush();
            }
            System.out.println("writer close leaves OutputStream open: " + !output.closed());
            System.out.println("XML escaping valid: "
                    + output.toString(StandardCharsets.UTF_8).contains("A &amp; B"));
        }
        System.out.println("OutputStream closed after scope: " + output.closed());
    }

    public static void main(String[] args) throws Exception {
        readCursor();
        readEvents();
        readMalformed();
        writeOutput();
    }
}
~~~

Biên dịch và chạy với JDK **17 hoặc mới hơn**, trong thư mục chứa file:

~~~bash
javac --release 17 StaxResourceDemo.java
java StaxResourceDemo
~~~

**Stdout chính xác**, kiểm thử bằng **OpenJDK 24.0.2** với `--release 17`:

~~~text
cursor first item: A & B
cursor close leaves Reader open: true
Reader closed after scope: true
event items consumed: 1
event close leaves InputStream open: true
InputStream closed after scope: true
malformed XML rejected: true
malformed source closed: true
writer close leaves OutputStream open: true
XML escaping valid: true
OutputStream closed after scope: true
~~~

### Đọc kết quả cho đúng

- `cursor first item: A & B`: parser giải `&amp;` thành ký tự `&`. Demo dừng sớm trước EOF, vì chủ đề cần chứng minh cleanup khi **không** đọc hết.
- `cursor close leaves Reader open: true`: ngay sau đóng StAX cursor, nguồn `StringReader` chưa bị đóng trong phép thử. Khi thoát scope nguồn, `Reader closed after scope: true`.
- `event items consumed: 1`: event reader cũng dừng ở item đầu; không cố đọc hết `END_DOCUMENT`. `XMLEventReader.close()` không làm nguồn InputStream đóng trong kịch bản kiểm thử này; **outer scope** đóng InputStream.
- Nếu bạn sửa demo để đọc **đến EOF**, trạng thái nguồn ngay trước outer close có thể khác vì provider có quyền quản lý buffer/decoder và có thể chủ động đóng nguồn khi kết thúc. Không dùng boolean trung gian làm contract portability.
- `malformed XML rejected: true`: parser phát hiện XML sai nesting. `malformed source closed: true` chứng minh cleanup chạy dù parse ném exception.
- `writer close leaves OutputStream open: true`: Writer StAX được đóng trước, stream đích vẫn mở để có thể xem dữ liệu. `OutputStream closed after scope: true` xác nhận caller sở hữu và đóng output.
- `XML escaping valid: true`: writer escape ký tự `&` khi ghi XML text. Nguồn I/O không bao giờ được đóng thay cho việc kết thúc cấu trúc XML (thiếu `writeEndElement` có thể để output sai).
- `TrackedInputStream`, `TrackedReader` và `TrackedOutputStream` là **classes dùng để test**, không phải công cụ production. Chúng chỉ đếm trạng thái close của Java objects; không xác nhận driver XML ngoài hay network socket thật.
- `finally` trong Java đóng cả parser lẫn nguồn; try-with-resources adapter còn giữ lỗi cleanup trong suppressed exceptions nếu body đã lỗi.

### Một giới hạn quan trọng của demo

`readCursor()`, `readEvents()` cố ý dừng sau item đầu để làm nổi bật ownership và cleanup. Khi untrusted XML cần **toàn document well-formed**, dừng sớm đồng nghĩa chưa kiểm tra phần còn lại. Trong production, hoặc parse/validate hết trước khi commit dữ liệu, hoặc thiết kế staging/transaction theo chính sách nghiệp vụ. Không gửi thanh toán hay commit thay đổi không thể rollback chỉ sau khi đọc một item đầu của XML chưa được validate đầy đủ.

## 7. Dừng sớm, lỗi parse và hủy request: cleanup vẫn phải chạy

### Early return hoặc break

Một method parse một item rồi trả về:

~~~java
static String firstTitle(XMLStreamReader xml) throws XMLStreamException {
    while (xml.hasNext()) {
        if (xml.next() == XMLStreamConstants.START_ELEMENT
                && "title".equals(xml.getLocalName())) {
            return xml.getElementText();
        }
    }
    return null;
}
~~~

Đây là helper Java trong class. Nếu caller đã tạo `xml` trong try-with-resources **adapter**, cú pháp `return` từ helper không đóng parser tự động; nhưng khi scope caller kết thúc, parser và source vẫn được đóng. Không đưa responsibility đóng nguồn vào `firstTitle` nếu nó chỉ nhận một **borrowed parser** do caller sở hữu.

### XML malformed

`xml.next()` có thể ném `XMLStreamException` khi tài liệu không well-formed, DTD bị chặn hoặc parser gặp lỗi I/O. Cả parser và source vẫn phải đóng:

~~~text
Input source OPEN
     |
StAX parser created
     |
parse next() throws XMLStreamException
     |
try-with-resources adapter closes parser
     |
try-with-resources closes InputStream
     |
Exception propagates with close failures suppressed
~~~

Đừng catch `XMLStreamException` rồi trả một object “thành công một phần” nếu nghiệp vụ đòi tài liệu toàn vẹn. Nếu source là HTTP upload, nên trả lỗi validation và đóng/cancel body stream theo framework; không để connection/request giữ tài nguyên mãi.

### `close()` cũng có thể thất bại

Nếu XML parsing exception và `InputStream.close()` đều lỗi, TWR giữ nguyên primary error và thêm lỗi close vào `Throwable.getSuppressed()`. Khi logger hiển thị chain, bạn có thể phân biệt parse invalid và close failure. Nếu dùng `finally` thường, cleanup exception có thể che mất parse exception; đây là lý do adapter đáng giá khi quản lý nhiều resources.

~~~java
static void logFailure(Exception ex) {
    System.err.println("Primary type: " + ex.getClass().getSimpleName());
    for (Throwable suppressed : ex.getSuppressed()) {
        System.err.println("Cleanup type: "
                + suppressed.getClass().getSimpleName());
    }
}
~~~

Đây là method minh họa trong class. Production cần logging có kiểm soát, tránh in XML/URI/token và thông tin nhạy cảm. `getSuppressed()` có thể bao gồm nhiều lỗi (đóng StAX reader, đóng InputStream). Không viết `catch(Exception e) { }` để nuốt lỗi parse hoặc close chỉ vì muốn “đảm bảo đóng”.

### Factory lỗi khi tạo reader

Đúng:

~~~java
try (InputStream input = Files.newInputStream(file)) {
    XMLStreamReader xml = factory.createXMLStreamReader(input);
    try {
        // Parse...
    } finally {
        xml.close();
    }
}
~~~

Sai:

~~~java
InputStream input = Files.newInputStream(file);
XMLStreamReader xml = factory.createXMLStreamReader(input);
// Nếu factory ném XMLStreamException trước khi vào try/finally,
// input có thể không bao giờ được đóng.
try {
    // Parse...
} finally {
    xml.close();
    input.close();
}
~~~

Hai đoạn đều chỉ minh họa trong method, cần imports và checked exception handling. Khi có code tạo resource **trước** scope cleanup, một construction failure có thể leak tài nguyên. Đặt việc tạo StAX reader vào scope đã bảo vệ source.

### Cancellation / interruption

Khi request timeout hoặc thread bị interrupt, code có thể ngừng gọi `next()`. Chỉ thiết lập một timeout không làm StAX reader tự close. Giữ resource scopes ở vòng quản lý request/worker task. Với network I/O bị block, còn cần timeout/cancel ở transport; `XMLStreamReader.close()` **không** là một cơ chế cancellation cho mọi HTTP/socket provider.

**Đừng dùng `finalize()` hoặc GC làm cơ chế đóng** file/socket: GC không bảo đảm thời điểm giải phóng tài nguyên. Tài nguyên I/O cần close đúng scope, với error handling tường minh.

## 8. Borrowed stream: khi nào KHÔNG được đóng nguồn?

Có tình huống parse method chỉ được **mượn** `Reader` hoặc `InputStream`:

- Một CLI dùng `System.in` cho nhiều commands.
- Framework giữ stream để xử lý nhiều subdocuments hoặc nhiều tầng protocol.
- Một `ZipInputStream` đang ở entry hiện tại nhưng caller cần đọc entry kế tiếp.
- Một socket connection được multiplex hoặc server framework quản lý.
- Một Reader được chia sẻ trong một task lớn, với ownership thuộc caller.

Nếu helper nhận một `InputStream` từ caller, nên đặt hợp đồng rõ:

~~~java
// Hợp đồng: helper đóng StAX parser mà helper tạo;
// không trực tiếp đóng InputStream do caller cung cấp.
// Caller quyết định vòng đời của input.
static void parseBorrowed(InputStream input) throws XMLStreamException {
    XMLStreamReader xml = secureInputFactory().createXMLStreamReader(input);
    try {
        while (xml.hasNext()) {
            xml.next();
        }
    } finally {
        xml.close();
    }
}
~~~

Đây là snippet minh họa trong class, cần `secureInputFactory()`. **Cảnh báo thực tế:** Javadoc `close()` không đóng input source, nhưng một số provider khi đi đến EOF có thể đóng nguồn I/O trong quá trình parse. Nếu caller bắt buộc giữ stream sau đó, không thể chỉ dựa vào signature helper này mà đảm bảo điều đó với **mọi** provider.

### Non-closing wrapper khi caller cần giữ stream

Nếu không được phép đóng `InputStream` của caller, có thể dùng một wrapper **chặn lệnh close tới underlying delegate**:

~~~java
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;

static InputStream nonClosing(InputStream borrowed) {
    return new FilterInputStream(borrowed) {
        @Override public void close() throws IOException {
            // Không close nguồn borrowed; caller sở hữu.
        }
    };
}
~~~

Đây là helper Java có thể biên dịch. Khi dùng:

~~~java
InputStream safeView = nonClosing(borrowedInput);
XMLStreamReader xml = secureInputFactory().createXMLStreamReader(safeView);
try {
    // Xử lý XML theo protocol phù hợp.
} finally {
    xml.close();
}
// Không close borrowedInput; caller đóng lúc toàn bộ công việc kết thúc.
~~~

Đây là snippet trong method với `borrowedInput` do caller cung cấp. **Điều kiện:** wrapper chỉ ngăn `close` lan truyền, **không** ngăn parser đọc trước (read-ahead) hoặc lấy mất bytes của document tiếp theo. Trước khi parse XML concatenated messages/shared stream, phải có **framing** đúng (length-prefix, bounded stream hoặc một protocol parser) vì StAX có thể đọc quá điểm mà caller dự định. Không dùng non-closing wrapper như công cụ che giấu trách nhiệm cleanup; owner cuối cùng vẫn phải đóng nguồn.

**Không** dùng `try (InputStream in = System.in)` nếu ứng dụng còn cần đọc stdin sau method, vì try-with-resources sẽ đóng `System.in`. Với tài nguyên borrowed, đóng **parser** theo đúng scope nhưng chỉ owner mới đóng I/O source.

## 9. Bảo mật khi mở và đóng reader: không chỉ cleanup

Đóng tài nguyên đúng giúp tránh descriptor leaks, nhưng **không tự chống XXE**. Với XML không tin cậy, phải cấu hình parser **trước khi** gọi `createXMLStreamReader` hoặc `createXMLEventReader`.

~~~java
import javax.xml.XMLConstants;
import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLStreamException;

static XMLInputFactory secureInputFactory() {
    XMLInputFactory factory = XMLInputFactory.newDefaultFactory();
    factory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
    factory.setProperty(XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
    factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
    factory.setXMLResolver((publicId, systemId, baseUri, namespace) -> {
        throw new XMLStreamException("External resource not allowed");
    });
    return factory;
}
~~~

Đây là method Java17+ hợp lệ trong class. `newDefaultFactory` chọn provider mặc định tích hợp của JDK; nếu app dùng `newFactory` và provider discovery, phải test các security properties trên **implementation thực**.

Bốn trách nhiệm khác nhau:

1. `SUPPORT_DTD=false`: yêu cầu parser không hỗ trợ xử lý DTD.
2. `IS_SUPPORTING_EXTERNAL_ENTITIES=false`: yêu cầu không resolve external parsed entities.
3. `ACCESS_EXTERNAL_DTD=""`: cấm external DTD/entity protocols theo JAXP external access policy.
4. `setXMLResolver(...)`: fail closed nếu parser yêu cầu resolver của application lấy external resource.

JAXP Security Guide cho Java SE 25 nêu StAX **không dùng `FEATURE_SECURE_PROCESSING` theo cách áp dụng ở DOM/SAX/Transformer**; dùng StAX properties và external access restrictions, đồng thời giới hạn tài nguyên. Nếu một provider không hỗ trợ cấu hình bảo mật cần thiết và ném `IllegalArgumentException`, **không lặng lẽ bỏ qua** rồi parse untrusted XML.

### Resource limits đi cùng ownership

Đóng sớm khi quá giới hạn:

- Giới hạn **bytes/characters đầu vào**, độ sâu lồng phần tử, số attributes và tổng số elements.
- Tránh `getElementText()` không giới hạn trên text node rất lớn.
- Đặt **deadline và I/O timeout** khi nguồn là HTTP/network; close và cancellation thuộc transport.
- Chặn DTD/entity expansion/XXE, giới hạn parser processing work.
- Giới hạn số records giữ trong RAM; StAX streaming không giúp khi code vẫn gom mọi item vào `List` vô hạn.
- Tách parse/validate với side effects; nếu dừng sớm, chưa chứng minh phần còn lại well-formed.

Một hệ thống có thể **đóng đúng hết resources mà vẫn bị XML bomb tấn công trước khi đến close**. Do đó security và liveness cần được thiết kế đồng thời.

## 10. Đóng writer và output destination — quy tắc đối xứng có khác biệt

StAX writer không phải reader nhưng nguyên tắc **separate owner** tương tự:

~~~java
try (OutputStream output = Files.newOutputStream(file)) {
    XMLStreamWriter xml = XMLOutputFactory.newDefaultFactory()
            .createXMLStreamWriter(output, "UTF-8");
    try {
        xml.writeStartDocument("UTF-8", "1.0");
        xml.writeStartElement("note");
        xml.writeCharacters("Tiếng Việt & XML");
        xml.writeEndElement();
        xml.writeEndDocument();
        xml.flush();
    } finally {
        xml.close();
    }
}
// OutputStream của file được đóng bởi caller.
~~~

Đây là đoạn minh họa trong method, `file` cần được cung cấp, import `OutputStream`/`Files`/`XMLOutputFactory`/`XMLStreamWriter`. `XMLStreamWriter.close()` theo Javadoc **không được đóng underlying output stream**; cần đóng `OutputStream` riêng. `writeEndDocument()` hoàn thiện markup, `flush()` đẩy buffers của writer xuống output mechanism; **đóng stream không thay thế thao tác hoàn thành document**.

Với `XMLEventWriter.close()`, tài liệu chỉ yêu cầu giải phóng các tài nguyên của writer, không diễn đạt cùng câu “must not close underlying” như `XMLStreamWriter`. Vì thế ứng dụng vẫn cần quản lý output ownership và test library/provider được sử dụng; đừng suy diễn tất cả writer implementations hành xử y hệt trong mọi đường EOF/close.

**Encoding:** khi dùng `XMLOutputFactory.createXMLStreamWriter(OutputStream, "UTF-8")`, encoding output được thiết lập tại factory method. Tham số `writer.writeStartDocument("UTF-8", "1.0")` là XML declaration; không dùng declaration “UTF-8” để sửa một OutputStreamWriter thực tế đang encode theo charset khác. Với Writer-based output, chính caller chịu trách nhiệm mã hóa chars thành bytes.

## 11. Resource ownership khi lồng parser, transformer và SQLXML

Một application có thể dùng StAX chung với các tầng xử lý:

~~~text
HTTP response / SQLXML / file / ZIP
        |
   InputStream / Reader  (owner rõ)
        |
 XMLInputFactory + StAX Reader
        |
   StAXSource / Transformer / Validator
        |
    DOMResult / StreamResult
        |
 OutputStream / Writer (owner rõ)
~~~

Mỗi tầng có contract riêng. **`StAXSource`** chỉ là một adapter đưa `XMLStreamReader` hoặc `XMLEventReader` vào JAXP Transformer; nó **không tự biến input thành một resource có ownership mới**. Cần biết Transformer/Validator tiêu thụ reader đến đâu, có đóng source hay không, và giữ parser/source scopes sống đến khi xử lý hoàn tất.

### Ví dụ với JDBC SQLXML

~~~java
SQLXML sqlxml = rs.getSQLXML("payload");
if (sqlxml != null) {
    try {
        try (Reader characters = sqlxml.getCharacterStream()) {
            XMLStreamReader xml = secureInputFactory()
                    .createXMLStreamReader(characters);
            try {
                while (xml.hasNext()) {
                    xml.next();
                }
            } finally {
                xml.close();
            }
        }
    } finally {
        sqlxml.free();
    }
}
~~~

Đây là **mã minh họa trong method** với `ResultSet rs` đang đứng trên row hợp lệ, cần imports `java.sql.SQLXML`/`java.io.Reader`/`XMLStreamReader`, SQLException/IO/XMLStreamException handling. `SQLXML` có one-shot state: sau `getCharacterStream()` không gọi tiếp `getSource()`/`getString()` trên cùng instance. `SQLXML.free()` dọn tài nguyên riêng, **không đồng nghĩa đóng JDBC connection/transaction**. `SQLXML` không implement `AutoCloseable`; dùng finally.

Thứ tự cleanup là: **StAX reader → character stream → SQLXML.free() → JDBC ResultSet/Statement/Connection** theo owner, trong transaction đã tạo nguồn. Nếu `getCharacterStream` trả null/unsupported hay driver dùng logical pointer khác, cần kiểm tra và xử lý theo driver documentation. Không mang reader hoặc SQLXML ra khỏi transaction scope đã đóng rồi tiếp tục parse.

### Trường hợp framework tự sở hữu nguồn

Một framework có thể cấp `InputStream` rồi mong callback của bạn trả về mà **không đóng** source. Khi đó helper phải tôn trọng contract, đóng parser đã tạo nhưng không đóng framework stream nếu nó còn được framework tái sử dụng. Nếu framework API yêu cầu callback **phải** đóng resource thì làm theo tài liệu ấy. Không có quy tắc “hễ nhận InputStream là luôn close nó” nếu chưa biết ai sở hữu.

## 12. Những lỗi và hiểu lầm phổ biến

| Nhầm lẫn | Vấn đề thực tế | Cách sửa |
| --- | --- | --- |
| “`XMLStreamReader.close()` cũng đóng file.” | Javadoc không bảo đảm; file descriptor có thể leak | Đóng `InputStream`/`Reader` độc lập |
| “`XMLEventReader.close()` chắc chắn đóng HTTP body.” | Không có bảo đảm portable | Caller quản lý body/source scope |
| “Chỉ đóng InputStream là đủ.” | Parser có buffers/tài nguyên riêng | Close cả StAX reader |
| “Đóng thứ tự nào cũng được.” | Parser có thể cần nguồn khi cleanup | Đóng parser trước, source sau |
| “Reader là AutoCloseable nên XMLStreamReader cũng thế.” | Hai interface khác nhau | `finally` hoặc adapter AutoCloseable |
| “`try(XMLStreamReader xml = ...)` biên dịch.” | XMLStreamReader không implements AutoCloseable | Bọc CursorLease/AutoCloseable |
| “Dừng `break` thì không cần close.” | Vẫn phải dọn parser và I/O | Scope cleanup cả early exit |
| “XML malformed tự đóng hết streams.” | Không bảo đảm mọi provider/đường lỗi | Cleanup theo try/finally hoặc TWR |
| “Nếu factory.createXMLStreamReader lỗi thì input sẽ tự đóng.” | Sai khi mở input ngoài scope | Mở input trong try-with-resources trước create |
| “`finally` luôn giữ exception parse gốc.” | Cleanup exception có thể che primary | Adapter TWR + suppressed errors |
| “Resource đã ở EOF vẫn chắc chắn mở.” | Provider có thể tự đóng vào lúc EOF | Không dựa vào trạng thái trung gian |
| “Parser.close() có thể dùng để cancel mọi network read.” | Timeout/cancel thuộc transport và provider | Đặt deadline và I/O timeout riêng |
| “`System.in` có thể try-with-resources như file.” | Có thể đóng stdin dùng chung | Ownership rõ, borrowed boundary |
| “Non-closing wrapper bảo đảm không read-ahead.” | Nó chỉ ngăn close lan truyền | Framing/bounded stream theo protocol |
| “Đóng GZIP wrapper luôn giải quyết constructor failure.” | Raw stream có thể leak nếu constructor ném trước try | Khai báo raw trước trong TWR |
| “Đóng XML stream nghĩa là dữ liệu XML được validate.” | Early stop chưa đọc suffix | Validate full document trước commit nếu cần |
| “XMLStreamWriter.close() đóng OutputStream.” | Javadoc yêu cầu không đóng source đích | Đóng output riêng |
| “Chỉ close writer là XML tự well-formed.” | Có thể còn thiếu end elements | `writeEndElement`/`writeEndDocument`, test roundtrip |
| “Close luôn fail-proof.” | `XMLStreamException`/`IOException` vẫn xảy ra | Propagate, log suppressed metadata |
| “Close đúng là đủ an toàn trước XXE.” | XXE xảy ra **trong parse**, trước cleanup | Harden factory, limit resources |
| “Mọi provider có cùng semantics EOF.” | Implementation differences | Test JDK/provider thật, ownership rõ |

## 13. Checklist và kiểm thử

### Checklist triển khai

1. **Nguồn input thuộc ai?** Caller tự mở (owned) hay framework cấp (borrowed)?
2. **Nguồn là gì?** FileInputStream, Reader, BufferedReader, network body, ZIP, SQLXML stream?
3. **StAX reader thuộc ai?** Module nào gọi `createXMLStreamReader`/`createXMLEventReader` thì thường chịu trách nhiệm đóng nó.
4. **Parser được tạo trong scope nguồn?** Đảm bảo construction failure không leak nguồn.
5. **Thứ tự close?** Reader StAX trước, nguồn I/O sau.
6. **Dừng sớm/lỗi parse có cleanup?** Kiểm thử `break`, `return`, malformed XML và consumer exception.
7. **Đã xử lý close failures?** Preserve primary exception và suppressed errors.
8. **Có borrowed source cần giữ mở không?** Nếu có, quy định rõ và kiểm tra read-ahead/provider behavior; dùng wrapper nếu cần.
9. **Có chính sách DTD/XXE?** Cấu hình trước parse, chặn external access, resolver có policy.
10. **Có input size/depth/time limits?** Resource limits không thay thế cleanup.
11. **Có xử lý output writer?** Flush/hoàn thiện XML, close writer rồi output stream.
12. **Test JDK/provider thực tế?** Không dựa vào một hành vi tình cờ của parser ở EOF.
13. **Nếu là SQLXML/HTTP response?** Thêm lifecycle cleanup do API cấp nguồn yêu cầu.
14. **Không commit partial XML sai?** Xác định early-stop semantics và validation boundary.

### Test matrix

| Kịch bản | Expected invariant |
| --- | --- |
| XML well-formed đọc hết | Parser và source đều được owner cleanup |
| Dừng ở item đầu | Parser và source vẫn được cleanup |
| XML malformed giữa chừng | Exception phù hợp; không leak source |
| DTD bị chặn | Không đọc file/network; cleanup vẫn chạy |
| Factory tạo parser thất bại | Source mở trước vẫn được đóng |
| Parser.close ném XMLStreamException | Caller nhận/ghi nhận lỗi; nguồn vẫn được close |
| InputStream.close ném IOException | Cleanup exception được giữ, không nuốt parse error |
| XMLStreamReader.close với source owned | Không dựa vào nó để đóng InputStream |
| XMLEventReader tới EOF | Không assert source vẫn mở ở thời điểm trước outer cleanup |
| Borrowed System.in | Helper không chủ động đóng System.in |
| Non-closing borrowed wrapper | Caller vẫn giữ quyền đóng nguồn, không chặn read-ahead |
| GZIP/ZIP/multipart source | Đúng ownership và close chains |
| SQLXML character stream | StAX reader, character Reader, SQLXML.free và JDBC resources đều dọn |
| XMLStreamWriter output | Writer đóng; output stream do caller đóng |
| Có exception khi đóng cả parser và stream | Lỗi chính + suppressed errors không mất |
| File input 10.000 lần | Không tăng số file descriptors/sockets còn mở liên tục |

### Đo leak như thế nào?

Không nên chỉ nhìn `System.gc()` hoặc heap chart. Với file/network, theo dõi open file handles/descriptors, số active HTTP sockets, pool pending requests, thời gian I/O và memory buffers. Trong unit test có thể dùng `TrackedReader`/`TrackedInputStream` như demo. Trong integration test, dùng temp files/socket endpoint hoặc HTTP mocks để đo cleanup thực tế. Giữ số vòng lặp lớn ở test môi trường cô lập; đừng spam external services chỉ để thử leak.

## 14. Câu hỏi tự kiểm tra

1. **`XMLStreamReader.close()` có đóng `InputStream` gốc theo Javadoc không?** Không.
2. **`XMLEventReader.close()` có bảo đảm đóng `Reader` gốc không?** Không.
3. **Vậy ai đóng nguồn I/O?** Owner của nguồn, thường method đã mở nó.
4. **Ai đóng StAX reader?** Thành phần đã tạo/sở hữu parser, sau khi xử lý xong.
5. **Thứ tự close an toàn?** StAX parser trước, I/O source sau.
6. **Có thể đặt `XMLStreamReader` trực tiếp vào try-with-resources không?** Không, interface không implement AutoCloseable.
7. **Có mẫu gọn nào để giữ suppressed exceptions?** Bọc parser bằng AutoCloseable adapter và dùng TWR.
8. **Nếu `createXMLStreamReader` ném exception thì sao?** Khi source mở trong TWR, Java vẫn đóng source.
9. **Nếu `xml.next()` ném XMLStreamException thì sao?** Cleanup parser/source vẫn diễn ra nhờ try/finally hoặc TWR.
10. **Khi parser close cũng lỗi, chuyện gì xảy ra với exception parse?** TWR giữ parse error làm primary và close failures suppressed.
11. **Có được đóng `System.in` sau mỗi đoạn XML không?** Không nếu stdin còn được dùng; xác định ownership.
12. **Non-closing wrapper bảo vệ điều gì?** Ngăn close lan đến borrowed stream, không ngăn parser read-ahead.
13. **Đọc tới EOF có chứng minh nguồn vẫn mở không?** Không; provider có thể tự đóng source khi kết thúc.
14. **StAX có tự chặn DTD/XXE không?** Không được giả định; phải cấu hình secure InputFactory.
15. **Có thể coi parse một item đầu là toàn document hợp lệ không?** Không.
16. **`XMLStreamWriter.close()` có đóng underlying OutputStream không?** Không, theo Javadoc.
17. **Nếu source là GZIP wrapper, đóng nó có đóng raw stream không?** Theo contract GZIPInputStream có; nhưng vẫn bảo vệ construction-failure bằng TWR raw resource riêng.
18. **Nếu source là JDBC SQLXML, cleanup thêm gì?** Reader/stream, `SQLXML.free()` và JDBC transaction/resources theo owner.
19. **Reader/Stream có thể được parse lại sau StAX close không?** Không được suy diễn; provider có thể đã tiêu thụ hoặc đóng nguồn, input position đã thay đổi.
20. **Tại sao không dùng GC/finalize thay close?** Không có guarantee thời điểm giải phóng file/socket.
21. **Đầu vào XML rất lớn vẫn có thể OOM dù đóng đúng không?** Có, nếu parse/memory expansion đã xảy ra trước close hoặc app tích lũy dữ liệu.
22. **Nên test những exit paths nào?** EOF, break, return, factory failure, malformed XML, close failure, cancellation.

## 15. Tài liệu chính thức còn áp dụng

- [Java SE 25 — XMLStreamReader](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/stream/XMLStreamReader.html): `close()` không đóng underlying input source, cursor events, next()/hasNext().
- [Java SE 25 — XMLEventReader](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/stream/XMLEventReader.html): `close()` không đóng underlying input source, nextEvent()/peek().
- [Java SE 25 — XMLStreamWriter](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/stream/XMLStreamWriter.html): `close()` không được đóng underlying output, flush() và XML structure.
- [Java SE 25 — XMLEventWriter](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/stream/XMLEventWriter.html): close/flush contracts của event writer.
- [Java SE 25 — XMLInputFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/stream/XMLInputFactory.html): tạo StAX readers từ InputStream/Reader, DTD và external entity policies.
- [Java SE 25 — XMLOutputFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/stream/XMLOutputFactory.html): tạo StAX writers từ OutputStream/Writer.
- [Java SE 25 — XMLStreamException](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/stream/XMLStreamException.html): parse và cleanup failures, location information.
- [Java SE 25 — AutoCloseable](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/AutoCloseable.html): hợp đồng `close()` và cấu trúc try-with-resources.
- [Java SE 25 — JAXP Security Guide](https://docs.oracle.com/en/java/javase/25/security/java-api-xml-processing-jaxp-security-guide.html): StAX không dùng FSP như DOM/SAX, security properties, external access và resource limits.
- [Java SE 25 — java.sql.SQLXML](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/SQLXML.html): SQLXML one-shot behavior và `free()` nếu nguồn XML đến từ JDBC.
- [Java SE 25 — java.util.zip.GZIPInputStream](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/zip/GZIPInputStream.html): cleanup layered compression stream.

**Kết luận:** `XMLStreamReader.close()` và `XMLEventReader.close()` giải phóng tài nguyên **StAX parser**, không thay thế việc đóng **InputStream/Reader** do bạn sở hữu. Mở nguồn trong scope được bảo vệ, tạo parser bên trong, đóng parser trước rồi đóng nguồn (ưu tiên AutoCloseable adapter + try-with-resources để giữ suppressed errors). Đừng đóng nhầm borrowed stream; đừng dựa vào hành vi EOF của một provider; và luôn kết hợp cleanup với DTD/XXE restrictions, timeout và resource limits.