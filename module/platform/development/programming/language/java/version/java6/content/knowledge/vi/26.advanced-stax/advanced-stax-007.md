# Xử lý tệp XML lớn theo từng bản ghi bằng StAX (Java 17+)

## 1. Bài toán: một tệp XML chứa hàng chục nghìn hoặc hàng triệu bản ghi

Một hệ thống nhận XML chứa danh sách đơn hàng, giao dịch, log sự kiện, bản ghi xuất từ ERP hoặc dữ liệu trao đổi giữa các dịch vụ. Tệp có thể lớn hơn rất nhiều so với bộ nhớ dành cho một request. Mỗi bản ghi có thể được xử lý độc lập về mặt **phân tích cú pháp**; không nhất thiết phải tạo cả một `Document` DOM hoặc một `List<Order>` khổng lồ.

Ví dụ cấu trúc:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<o:orders xmlns:o="urn:demo:orders">
  <o:order id="o00001">
    <o:customer>Tiếng Việt 😀</o:customer>
    <o:amount currency="USD">125.50</o:amount>
  </o:order>
  <o:order id="o00002">
    <o:customer>Customer 2</o:customer>
    <o:amount currency="USD">78.00</o:amount>
  </o:order>
</o:orders>
~~~

**Mục tiêu:** đọc lần lượt từng `<o:order>`, kiểm tra trường bắt buộc, chuyển thành một Java `record`, đưa ngay cho consumer, rồi **quên đối tượng vừa xử lý**. Với tệp lớn, tránh tích trữ toàn bộ đơn hàng; chỉ giữ một bản ghi hiện tại, vài bộ đếm/giới hạn và bộ đệm của XML parser.

Trong Java 17+ có **StAX — Streaming API for XML**, thuộc module `java.xml`, package `javax.xml.stream`. Ứng dụng điều khiển reader qua `XMLStreamReader.next()` và xử lý các `START_ELEMENT`, `CHARACTERS`, `END_ELEMENT`. API này vẫn có mặt trong tài liệu Java SE 25; không cần thêm JAR “StAX standalone” cũ hoặc chuyển package sang `jakarta.xml.stream`.

Đây là bài về **StAX nâng cao: xử lý tệp lớn theo từng bản ghi**, không phải chỉ duyệt in các tên thẻ. Trọng tâm là **ranh giới bản ghi, bảo toàn cấu trúc, tài nguyên, bảo mật, hiệu suất, giới hạn đầu vào và tính nguyên tử của thao tác downstream**.

## 2. “Streaming” có ba tầng, không phải một lời cam kết O(1) thần kỳ

~~~text
File / InputStream (bytes)
       │    giới hạn bytes + timeout
       ▼
XMLInputFactory + XMLStreamReader (events)
       │    giới hạn depth + events + characters
       ▼
Record parser (chỉ một <order> mỗi lúc)
       │    validate trường + tạo Order
       ▼
OrderSink.accept(Order)
       │
       ├── Stats / aggregation O(1)
       ├── bounded batch (ví dụ tối đa 500 records)
       ├── JDBC batch / staging table
       └── bounded queue / downstream API
       │
       ▼
END_DOCUMENT → xác nhận tệp đầy đủ, cleanup resources
~~~

Có ba loại bộ nhớ:

1. **Input/parser buffers:** StAX có internal buffers và có thể read-ahead từ InputStream. Thực tế không bảo đảm đúng 1 byte được đọc cho mỗi event.
2. **Record state:** ứng dụng chỉ giữ `id`, `customer`, `amount`, `currency` và một `StringBuilder` của trường hiện tại. Nếu có max field length, bộ nhớ ứng dụng dùng để parse một record được giới hạn.
3. **Downstream state:** nếu `sink.accept()` nối mọi record vào `ArrayList`, bạn vẫn giữ toàn bộ dữ liệu. Muốn streaming thật sự, sink phải xử lý/flush theo batch có giới hạn, hoặc tích lũy thống kê/aggregation nhỏ.

Do đó **độ phức tạp bộ nhớ ở lớp application** có thể gần **O(độ sâu XML + kích thước trường tối đa + batch size)**, **không** phải O(kích thước toàn tệp). Đây là phân tích điều kiện; code thực tế còn có parser buffers, caches, JIT/GC và tài nguyên I/O.

### StAX khác DOM và SAX

| Giải pháp | Mô hình | Phù hợp với tệp lớn? | Điểm cần lưu ý |
| --- | --- | --- | --- |
| DOM | Load toàn bộ cây `Document` | Chỉ nếu tệp vừa bộ nhớ, cần XPath/random access | Memory có thể cao hơn kích thước tệp |
| SAX | Push các callbacks | Có, nếu handler không tích trữ | Logic nghiệp vụ phân tán theo callback state |
| **StAX** | **Pull:** application gọi `next()` | **Có**, thuận tiện cho record-by-record | Cần giữ state/depth, không bỏ qua nested XML |
| `getElementText()` không giới hạn | Pull nhưng tạo `String` lớn | **Không an toàn** nếu một field có thể cực lớn | Giới hạn text length hoặc đọc từng `CHARACTERS` |
| Xử lý từng record nhưng lưu `List` mọi record | Parser stream, consumer tích lũy | Không đạt mục tiêu memory bounded | Đổi sang bounded batch hoặc sink có state nhỏ |

Không phải mọi file XML là danh sách các records đơn giản; nếu XML chứa mixed content, entities, nested records hoặc namespaces phức tạp, cần thiết kế parser theo schema thực tế, không chỉ tìm mọi thẻ có local name `order`.

## 3. Ranh giới bản ghi và state machine

Ta chọn cấu trúc domain cụ thể:

~~~text
Depth 1: <orders xmlns="urn:demo:orders">
Depth 2:   <order id="o00001">
Depth 3:     <customer>...</customer>
Depth 3:     <amount currency="USD">125.50</amount>
Depth 2:   </order>
Depth 1: </orders>
~~~

Khi gặp `START_ELEMENT` ở **depth 2**, parser bắt đầu một record mới, chỉ cho phép `order`. Khi gặp `START_ELEMENT` ở **depth 3**, parser tạo một `StringBuilder` giới hạn cho `customer` hoặc `amount`. Khi gặp `END_ELEMENT` ở depth 3, parser gán giá trị vào record state. Đến `END_ELEMENT` ở **depth 2**, parser xác nhận mọi field bắt buộc có mặt, gọi `sink.accept(new Order(...))` và **không đưa record vào List vô hạn**.

**Đọc đúng expanded XML name:** `XMLStreamReader.getLocalName()` phải đi kèm `getNamespaceURI()`. Hai thẻ cùng local name nhưng namespace khác có thể mang nghĩa hoàn toàn khác; một prefix như `o`/`x` chỉ là bí danh cho URI. Trong ví dụ, mọi element phải thuộc `urn:demo:orders`, còn `id` và `currency` là unprefixed attributes nên không có namespace.

### Vì sao không dùng `getElementText()` cho mọi field?

Method `XMLStreamReader.getElementText()` rất tiện cho **text-only element**, nhưng nó **tạo toàn bộ nội dung thành `String`** và tự tiêu thụ đến `END_ELEMENT`. Với input không tin cậy, một trường có thể dài hàng chục MB gây áp lực heap trước khi bạn áp giới hạn.

Code demo dùng `CHARACTERS`, `CDATA`, `SPACE` và:

~~~java
if (content.length() + reader.getTextLength() > MAX_FIELD_CHARS) {
    throw new XMLStreamException("Field too long");
}
content.append(reader.getTextCharacters(),
        reader.getTextStart(), reader.getTextLength());
~~~

Đây là **đoạn minh họa trong event loop**, `content`, `reader`, `MAX_FIELD_CHARS` có sẵn, cần import `javax.xml.stream.XMLStreamException`. Nhờ kiểm tra **trước khi append**, bộ đệm một field không lớn vượt ngưỡng application cho phép. Parser có thể đã đọc cả chunk vào bộ nhớ nội bộ của nó, nên đây không phải một bảo đảm tuyệt đối về toàn JVM memory; kết hợp với byte quota ở nguồn.

Text có thể được chia thành nhiều events. **Không** cho rằng một field luôn chỉ có một `CHARACTERS`, và không tự parse số tiền sau event đầu khi còn text events tiếp theo. Bản demo hoàn thiện field khi gặp **`END_ELEMENT` tương ứng**.

### Depth theo số START/END_ELEMENT

~~~text
START_ELEMENT root      → depth = 1
START_ELEMENT order     → depth = 2
START_ELEMENT customer  → depth = 3
CHARACTERS              → depth không đổi
END_ELEMENT customer    → xử lý value; depth = 2
END_ELEMENT order       → emit record; depth = 1
END_ELEMENT root        → rootClosed = true; depth = 0
END_DOCUMENT            → xác nhận hết tệp
~~~

Một cách viết dễ lỗi là gọi `nextTag()` hoặc `getElementText()` bên trong vòng lặp rồi vẫn tăng/giảm depth như thể event bị consume cũng được phát lại ở vòng ngoài. Khi chọn state machine tự quản, **mỗi START/END event chỉ xử lý đúng một lần**.

## 4. Nguồn dữ liệu: byte streams, charset, quota và file lifecycle

### Đọc qua InputStream để tôn trọng XML encoding

~~~java
try (InputStream input = Files.newInputStream(file)) {
    XMLStreamReader xml = secureFactory().createXMLStreamReader(input);
    try {
        while (xml.hasNext()) {
            int event = xml.next();
            // Parse...
        }
    } finally {
        xml.close();
    }
}
~~~

Đây là **đoạn minh họa trong method** với `Path file` và `secureFactory()` đã có, cần imports/checked exceptions. `XMLStreamReader.close()` **không có hợp đồng đóng underlying InputStream**; application đóng input bằng try-with-resources. Từ file bytes, parser có thể xử lý XML declaration/BOM và encoding theo XML specification. Nếu ứng dụng tạo `Reader`, byte→character decoding đã xảy ra từ trước, nên phải chọn charset đúng.

### Quota không chỉ kiểm tra `Files.size()` trước khi mở

Giới hạn ngay trên luồng dữ liệu. Một file có thể thay đổi trong khi đọc; mạng/ZIP/GZIP có thể cung cấp nhiều dữ liệu hơn metadata ban đầu. Vì thế dùng **counting/bounded input stream**:

~~~java
static final class LimitedInputStream extends FilterInputStream {
    private final long limit;
    private long used;

    LimitedInputStream(InputStream source, long limit) {
        super(source);
        this.limit = limit;
    }

    private void count(long n) throws IOException {
        if (n > 0 && n > limit - used) {
            throw new IOException("XML byte limit exceeded");
        }
        used += n;
    }

    @Override public int read() throws IOException {
        int value = in.read();
        if (value >= 0) count(1);
        return value;
    }

    @Override public int read(byte[] bytes, int offset, int length)
            throws IOException {
        int n = in.read(bytes, offset, length);
        if (n > 0) count(n);
        return n;
    }
}
~~~

Đây là **type Java bên trong class**, cần imports `FilterInputStream`, `InputStream` và `IOException`. Nếu parser đọc quá quota, wrapper ném lỗi và caller phải **hủy parsing**. Wrapper này **đếm sau khi delegate đã đọc**: nó chặn application xử lý dữ liệu vượt quota nhưng một lần `read(byte[])` có thể đã tiêu thụ bytes vượt ngưỡng từ nguồn. Nếu nghiệp vụ đòi **không tiêu thụ quá một giới hạn vật lý** (chẳng hạn stream nối nhiều thông điệp), nên hạn chế độ dài `read` truyền xuống delegate hoặc dùng một **framed/bounded stream** giới hạn trước khi đọc; đừng dùng wrapper này làm message framer.

Ngoài bytes, quota nên bao gồm số **XML events**, số **record**, độ sâu XML, số attributes và số ký tự mỗi field. Những giới hạn này bảo vệ các kiểu tệp nhỏ về bytes nhưng có cấu trúc phức tạp, hoặc tệp từ nguồn đã giải nén.

### Khi nguồn là GZIP/ZIP

Nếu parse XML từ `GZIPInputStream`, kiểm tra cả **compressed bytes** lẫn **decompressed bytes**. Limit trên file nén không ngăn zip bomb: một gói nhỏ có thể giải nén thành luồng XML khổng lồ. Với nhiều layers I/O, kiểm soát close ownership và failure khi tạo stream:

~~~java
try (InputStream raw = Files.newInputStream(file);
     InputStream gzip = new java.util.zip.GZIPInputStream(raw);
     InputStream limited = new LimitedInputStream(gzip, MAX_BYTES)) {
    XMLStreamReader xml = secureFactory().createXMLStreamReader(limited);
    try {
        // Parse một bản ghi mỗi lần.
    } finally {
        xml.close();
    }
}
~~~

Đây là snippet trong method cần `file`, `MAX_BYTES`, `LimitedInputStream` và factory. Nếu source không có compression, **không** tạo GZIPInputStream. Cách khai báo `raw` trước giúp Java vẫn đóng raw nếu constructor GZIP lỗi; close lặp các delegate chuẩn Java thường an toàn nhưng custom resource có thể cần chính sách riêng.

## 5. Chặn XML không tin cậy trước khi parse

Tệp lớn có thể mang **DTD**, external entities (XXE/SSRF), entity expansion hoặc nội dung nested rất sâu. Việc chọn StAX không làm parser tự động an toàn. Cần cấu hình `XMLInputFactory` **trước khi tạo reader**:

~~~java
XMLInputFactory factory = XMLInputFactory.newDefaultFactory();
factory.setProperty(XMLInputFactory.IS_NAMESPACE_AWARE, true);
factory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
factory.setProperty(XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
factory.setXMLResolver((publicId, systemId, baseUri, namespace) -> {
    throw new XMLStreamException("External entity blocked");
});
~~~

Đây là đoạn minh họa, các imports từ `javax.xml.stream` và `javax.xml.XMLConstants`. `newDefaultFactory()` chọn implementation mặc định tích hợp của JDK khi muốn tránh provider lookup. Nếu dự án dùng provider StAX ngoài JDK hoặc `newFactory()`, kiểm chứng từng security setting trên version production.

**Các điểm cần hiểu chính xác:**

- `SUPPORT_DTD=false` yêu cầu provider không xử lý DTD; nếu ứng dụng không cho phép DTD, còn cần **từ chối sự kiện `DTD`** nếu provider vẫn phát ra.
- `IS_SUPPORTING_EXTERNAL_ENTITIES=false` yêu cầu không hỗ trợ external entity resolution.
- `ACCESS_EXTERNAL_DTD=""` cấm các protocol external DTD/entity theo JAXP external access policy.
- `XMLResolver` có thể trả nội dung từ một nguồn khác. Trong demo, resolver ném lỗi để từ chối mọi yêu cầu external; **không** dùng resolver tự tải HTTP/file URLs từ input chưa kiểm soát.
- `XMLConstants.FEATURE_SECURE_PROCESSING` được áp dụng ở những JAXP factories khác, nhưng **không có cơ chế FSP tương tự bắt buộc cho StAX**; theo JAXP Security Guide, cần StAX properties và external access restrictions.
- Không catch `IllegalArgumentException` do `setProperty` không được provider hỗ trợ rồi bỏ qua; với XML không tin cậy phải **fail closed** hoặc đổi provider/configuration.
- Resource limits còn cần áp ở tầng ứng dụng. Trong code chạy, max bytes, events, depth, records, text field giúp giảm rủi ro cả khi DTD đã bị chặn.

Nếu parsing bị giới hạn mà lỗi xảy ra ở record thứ 100.001, có thể đã có 100.000 records được consumer nhận; đây là vấn đề **atomicity** ở downstream, không phải bug của StAX.

## 6. Chương trình chạy được: tạo XML 10.000 orders và đọc từng order

Mã Java 17+ dưới đây dùng **chỉ JDK chuẩn**, không cần thư viện/DB/network bên ngoài. Nó:
1. Tạo tệp XML tạm 10.000 orders bằng `XMLStreamWriter`, có khai báo namespace và encoding UTF-8.
2. Mở tệp bằng `Files.newInputStream()` rồi bọc `LimitedInputStream`.
3. Duyệt bằng `XMLStreamReader`; dùng depth 1/2/3 và các giới hạn để dựng **một** `Order` tại một thời điểm.
4. Gọi `OrderSink.accept` **ngay khi đóng `</order>`**. Demo chỉ tính count/sum, không giữ danh sách.
5. Kiểm tra đủ root/end document; đóng StAX reader và input trong mọi đường thoát.
6. Thử payload DTD có external entity và XML sai nesting; cả hai phải bị từ chối.
7. Xóa ba tệp tạm trong `finally`.

**Không có số đo heap cố định** vì JVM và provider có memory behavior khác nhau; chương trình chỉ chứng minh code của application không đưa tất cả orders vào `List`. Nó cũng không mô phỏng database transaction hoặc consumer side effects.

Tạo file **`LargeXmlOrdersDemo.java`** (tên khớp với `public class`):

~~~java
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;
import javax.xml.XMLConstants;
import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLOutputFactory;
import javax.xml.stream.XMLStreamConstants;
import javax.xml.stream.XMLStreamException;
import javax.xml.stream.XMLStreamReader;
import javax.xml.stream.XMLStreamWriter;

public final class LargeXmlOrdersDemo {
    private static final String NS = "urn:demo:orders";
    private static final long MAX_BYTES = 5_000_000;
    private static final long MAX_EVENTS = 500_000;
    private static final int MAX_RECORDS = 100_000;
    private static final int MAX_FIELD_CHARS = 120;
    private static final int MAX_DEPTH = 3;

    record Order(String id, String customer, BigDecimal amount, String currency) {}
    @FunctionalInterface interface OrderSink {
        void accept(Order value) throws Exception;
    }

    static final class Stats implements OrderSink {
        long processed;
        int unicodeRecords;
        BigDecimal total = BigDecimal.ZERO.setScale(2);
        @Override public void accept(Order order) {
            processed++;
            total = total.add(order.amount());
            if (order.customer().contains("\uD83D\uDE00")) unicodeRecords++;
        }
    }

    static final class LimitedInputStream extends FilterInputStream {
        private final long limit;
        private long used;
        LimitedInputStream(InputStream in, long limit) {
            super(in);
            this.limit = limit;
        }
        private void count(long n) throws IOException {
            if (n > 0 && (n > limit - used)) {
                throw new IOException("XML byte limit exceeded");
            }
            used += n;
        }
        @Override public int read() throws IOException {
            int value = in.read();
            if (value >= 0) count(1);
            return value;
        }
        @Override public int read(byte[] b, int offset, int length) throws IOException {
            int n = in.read(b, offset, length);
            if (n > 0) count(n);
            return n;
        }
    }

    static final class CursorLease implements AutoCloseable {
        final XMLStreamReader reader;
        CursorLease(XMLStreamReader reader) { this.reader = reader; }
        @Override public void close() throws XMLStreamException { reader.close(); }
    }

    static final class WriterLease implements AutoCloseable {
        final XMLStreamWriter writer;
        WriterLease(XMLStreamWriter writer) { this.writer = writer; }
        @Override public void close() throws XMLStreamException { writer.close(); }
    }

    static XMLInputFactory secureInputFactory() {
        XMLInputFactory factory = XMLInputFactory.newDefaultFactory();
        factory.setProperty(XMLInputFactory.IS_NAMESPACE_AWARE, true);
        factory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
        factory.setProperty(XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setXMLResolver((publicId, systemId, baseUri, namespace) -> {
            throw new XMLStreamException("External entity blocked");
        });
        return factory;
    }

    private static XMLStreamException invalid(String message, XMLStreamReader r) {
        return new XMLStreamException(message, r.getLocation());
    }

    static long streamOrders(Path file, OrderSink sink) throws Exception {
        XMLInputFactory factory = secureInputFactory();
        long records = 0;
        long events = 0;
        int depth = 0;
        boolean rootSeen = false;
        boolean rootClosed = false;

        String id = null;
        String customer = null;
        String currency = null;
        BigDecimal amount = null;
        String field = null;
        StringBuilder content = null;

        try (InputStream fileInput = Files.newInputStream(file);
             CursorLease lease = new CursorLease(factory.createXMLStreamReader(
                     new LimitedInputStream(fileInput, MAX_BYTES)))) {
            XMLStreamReader r = lease.reader;
            while (r.hasNext()) {
                if (++events > MAX_EVENTS) throw invalid("Too many XML events", r);
                int event = r.next();
                switch (event) {
                    case XMLStreamConstants.DTD, XMLStreamConstants.ENTITY_REFERENCE ->
                            throw invalid("DTD/entity references are not allowed", r);
                    case XMLStreamConstants.START_ELEMENT -> {
                        if (rootClosed || ++depth > MAX_DEPTH
                                || !NS.equals(r.getNamespaceURI())) {
                            throw invalid("Unexpected element/depth/namespace", r);
                        }
                        String name = r.getLocalName();
                        if (depth == 1) {
                            if (rootSeen || !"orders".equals(name)
                                    || r.getAttributeCount() != 0) {
                                throw invalid("Expected orders root", r);
                            }
                            rootSeen = true;
                        } else if (depth == 2) {
                            if (!"order".equals(name) || r.getAttributeCount() != 1) {
                                throw invalid("Expected order with one id", r);
                            }
                            id = r.getAttributeValue(null, "id");
                            if (id == null || !id.matches("o[0-9]{5}")) {
                                throw invalid("Invalid order id", r);
                            }
                            customer = null;
                            currency = null;
                            amount = null;
                        } else {
                            if (!"customer".equals(name) && !"amount".equals(name)) {
                                throw invalid("Unexpected order field", r);
                            }
                            if ("customer".equals(name)) {
                                if (customer != null || r.getAttributeCount() != 0) {
                                    throw invalid("Duplicate/invalid customer", r);
                                }
                            } else {
                                if (amount != null || r.getAttributeCount() != 1) {
                                    throw invalid("Duplicate/invalid amount", r);
                                }
                                currency = r.getAttributeValue(null, "currency");
                                if (!"USD".equals(currency)) {
                                    throw invalid("Unsupported currency", r);
                                }
                            }
                            field = name;
                            content = new StringBuilder();
                        }
                    }
                    case XMLStreamConstants.CHARACTERS,
                         XMLStreamConstants.CDATA,
                         XMLStreamConstants.SPACE -> {
                        if (depth == 3) {
                            if (content.length() + r.getTextLength() > MAX_FIELD_CHARS) {
                                throw invalid("Field too long", r);
                            }
                            content.append(r.getTextCharacters(),
                                    r.getTextStart(), r.getTextLength());
                        } else if (!r.isWhiteSpace()) {
                            throw invalid("Unexpected text outside fields", r);
                        }
                    }
                    case XMLStreamConstants.END_ELEMENT -> {
                        if (depth == 3) {
                            String value = content.toString();
                            if ("customer".equals(field)) {
                                if (value.isBlank()) throw invalid("Blank customer", r);
                                customer = value;
                            } else {
                                if (!value.matches("[0-9]{1,8}\\.[0-9]{2}")) {
                                    throw invalid("Invalid money format", r);
                                }
                                amount = new BigDecimal(value);
                            }
                            field = null;
                            content = null;
                        } else if (depth == 2) {
                            if (customer == null || amount == null || currency == null) {
                                throw invalid("Incomplete order", r);
                            }
                            if (++records > MAX_RECORDS) {
                                throw invalid("Too many records", r);
                            }
                            sink.accept(new Order(id, customer, amount, currency));
                        } else if (depth == 1) {
                            rootClosed = true;
                        } else {
                            throw invalid("Unexpected closing element", r);
                        }
                        depth--;
                    }
                    default -> {
                        // COMMENT and processing instructions are not domain records.
                    }
                }
            }
            if (!rootSeen || !rootClosed || depth != 0
                    || r.getEventType() != XMLStreamConstants.END_DOCUMENT) {
                throw invalid("Document incomplete", r);
            }
        }
        return records;
    }

    static void generate(Path file, int count) throws Exception {
        try (OutputStream out = Files.newOutputStream(file);
             WriterLease lease = new WriterLease(
                     XMLOutputFactory.newDefaultFactory()
                             .createXMLStreamWriter(out, "UTF-8"))) {
            XMLStreamWriter w = lease.writer;
            w.writeStartDocument("UTF-8", "1.0");
            w.setPrefix("o", NS);
            w.writeStartElement("o", "orders", NS);
            w.writeNamespace("o", NS);
            for (int i = 0; i < count; i++) {
                w.writeStartElement("o", "order", NS);
                w.writeAttribute("id", String.format(Locale.ROOT, "o%05d", i));
                w.writeStartElement("o", "customer", NS);
                w.writeCharacters(i == 5
                        ? "Ti\u1EBFng Vi\u1EC7t \uD83D\uDE00" : "Customer " + i);
                w.writeEndElement();
                w.writeStartElement("o", "amount", NS);
                w.writeAttribute("currency", "USD");
                w.writeCharacters(BigDecimal.valueOf(i).setScale(2).toPlainString());
                w.writeEndElement();
                w.writeEndElement();
            }
            w.writeEndElement();
            w.writeEndDocument();
            w.flush();
        }
    }

    public static void main(String[] args) throws Exception {
        Path input = Files.createTempFile("orders-demo-", ".xml");
        Path dangerous = Files.createTempFile("orders-xxe-", ".xml");
        Path malformed = Files.createTempFile("orders-bad-", ".xml");
        try {
            generate(input, 10_000);
            Stats stats = new Stats();
            long count = streamOrders(input, stats);
            System.out.println("processed orders: " + count);
            System.out.println("consumer calls: " + stats.processed);
            System.out.println("amount sum: " + stats.total.toPlainString());
            System.out.println("unicode records: " + stats.unicodeRecords);

            Files.writeString(dangerous, "<!DOCTYPE orders [<!ENTITY xxe "
                    + "SYSTEM \"file:///blocked.txt\">]>"
                    + "<orders xmlns=\"urn:demo:orders\">&xxe;</orders>",
                    StandardCharsets.UTF_8);
            boolean dtdRejected = false;
            try {
                streamOrders(dangerous, value -> {});
            } catch (XMLStreamException error) {
                dtdRejected = true;
            }
            System.out.println("DTD rejected: " + dtdRejected);

            Files.writeString(malformed,
                    "<orders xmlns=\"urn:demo:orders\"><order id=\"o00001\">"
                    + "<customer>A</customer></orders>", StandardCharsets.UTF_8);
            boolean malformedRejected = false;
            try {
                streamOrders(malformed, value -> {});
            } catch (XMLStreamException error) {
                malformedRejected = true;
            }
            System.out.println("malformed rejected: " + malformedRejected);
        } finally {
            Files.deleteIfExists(input);
            Files.deleteIfExists(dangerous);
            Files.deleteIfExists(malformed);
        }
    }
}
~~~

Chạy trong thư mục chứa `LargeXmlOrdersDemo.java`:

~~~bash
javac --release 17 LargeXmlOrdersDemo.java
java LargeXmlOrdersDemo
~~~

**Stdout chính xác**, đã biên dịch/chạy trên **OpenJDK 24.0.2** với `--release 17`:

~~~text
processed orders: 10000
consumer calls: 10000
amount sum: 49995000.00
unicode records: 1
DTD rejected: true
malformed rejected: true
~~~

### Điều gì đã được kiểm chứng?

- Chương trình tạo đúng **10.000** bản ghi trong tệp, rồi đọc tuần tự và gọi consumer một lần cho mỗi `</order>` hoàn chỉnh. `count` và `stats.processed` bằng nhau.
- Mỗi order `i` có `amount = i.00`, tổng từ 0 đến 9.999 bằng **49.995.000,00** theo định dạng decimal không có phân cách hàng nghìn (`49995000.00`).
- Đúng một customer chứa `Tiếng Việt 😀`. Việc dùng Unicode escapes trong Java source giữ example độc lập với charset console/source editor; trong runtime, chuỗi vẫn là Unicode.
- `writeCharacters(...)` tự escape text XML, `XMLStreamWriter` tạo namespaced elements; parser đọc lại.
- XML chứa `DOCTYPE`/external entity bị từ chối. `XMLStreamException` được bắt trong test, **không** phải dấu hiệu file độc hại đã được parser “xử lý an toàn” ở mọi StAX provider.
- XML sai lồng thẻ bị từ chối, ngay cả khi có các record trước đó có thể đã được consumer nhận.
- Parser và input/output streams được đóng bằng `CursorLease`/`WriterLease` và try-with-resources; đây là adapter vì `XMLStreamReader`/`XMLStreamWriter` không implement `AutoCloseable` trong Java 17.
- Demo không gửi records đến DB hay network và không tạo một List chứa toàn bộ orders; Stats giữ **count, sum và một counter Unicode**. Nó không đo peak heap hoặc chứng minh O(1) bộ nhớ của provider.
- Ba tệp tạm được xóa ở `finally` sau xử lý. Nếu việc tạo các tệp tạm thất bại trước khi vào `try`, hệ thống production nên có cơ chế cleanup/staging directory riêng; đây là demo của streaming parser.

### Những giới hạn nghiệp vụ được code cố ý áp dụng

| Giới hạn | Giá trị demo | Ý nghĩa |
| --- | ---: | --- |
| Input bytes | 5.000.000 | Ngăn đọc quá ngưỡng đã định của file demo |
| XML events | 500.000 | Hạn chế số bước parser |
| Tổng records | 100.000 | Tránh số lượng record vô hạn |
| XML element depth | 3 | Chỉ cho phép `orders/order/{customer,amount}` |
| Ký tự mỗi field | 120 UTF-16 code units | Không tích trữ text vô hạn trong StringBuilder |
| ID pattern | `o[0-9]{5}` | Domain-specific, không phải quy tắc StAX chung |
| Currency | `USD` | Demo chỉ chấp nhận một currency |
| Money string | `[0-9]{1,8}\.[0-9]{2}` | Decimal dương, đúng hai chữ số sau dấu thập phân |
| Element namespace | `urn:demo:orders` | Chặn tag cùng local name nhưng sai namespace |

Những con số ở bảng **không phải giá trị chuẩn của StAX hoặc production mặc định**. Hãy thay bằng limits theo schema, tài nguyên service, kích thước file, giao kèo dữ liệu và throughput mục tiêu.

### Cần xem xét gì nếu đổi ví dụ thành 1 triệu records?

- `MAX_RECORDS` hiện chỉ 100.000; đổi theo policy nếu thật sự cần 1.000.000.
- `MAX_BYTES` cần tăng tương ứng, nhưng dựa trên **giới hạn bộ nhớ, I/O budget, disk quota và maximum request size**.
- ID pattern `o[0-9]{5}` không đủ cho 1.000.000 IDs; cập nhật schema/domain parser.
- Stats vẫn giữ O(1) application state, nhưng xử lý lâu hơn và cần **deadline/cancellation**.
- Tránh `System.out.println` cho từng record; logging per-record khiến I/O thành nút cổ chai.
- Bắt buộc quan sát throughput, memory, GC và downstream latency; không suy diễn cùng tốc độ qua nhiều cấp độ quy mô.
- Nếu file không cần được tạo trước, đọc từ InputStream thực mà không staging nguyên file cũng có thể hợp lý, nhưng cần trust policy, size limits và cách khôi phục khi lỗi.

## 7. Vì sao code chỉ emit sau `END_ELEMENT order`?

Nếu `OrderSink.accept` được gọi ngay khi gặp `START_ELEMENT order`, bạn chưa biết dữ liệu `customer`/`amount` có đầy đủ hoặc hợp lệ. Nếu gọi sau `customer` nhưng trước `amount`, records có thể bị consumer nhận thiếu field. Vì vậy:

~~~text
START <order>      → tạo state của record mới
  START <customer> → bắt đầu text
  END </customer>  → validate text, gán customer
  START <amount>   → bắt đầu text, nhận currency
  END </amount>    → validate number, gán amount
END </order>       → validate đủ record, emit đúng một lần
~~~

Ngay cả khi bản ghi thứ 10.000 đã được emit, **toàn XML document chưa nhất thiết valid** cho đến khi parser đọc hết đến `END_DOCUMENT`. Một file có các records đúng ở đầu nhưng thẻ root sai ở cuối có thể khiến StAX phát hiện lỗi sau nhiều calls tới sink.

**Chia làm hai loại “đúng”:**

1. **Một record đúng:** có đúng namespace/path, fields bắt buộc, kiểu dữ liệu, quota và domain validation.
2. **Toàn file đúng:** toàn bộ XML well-formed, không có DTD ngoài policy, không vượt file-level quotas, kết thúc bằng root hợp lệ và `END_DOCUMENT`.

Nếu nghiệp vụ đòi “một file hoặc nhận hết, hoặc không nhận gì”, **StAX streaming không tự tạo transaction**. Cần staging, kiểm thử all-or-nothing hoặc transaction boundary phù hợp ở consumer.

## 8. Tích hợp sink với JDBC hoặc queue mà không làm heap phình lên

### Thống kê liên tục: O(1) state

Trong demo, `Stats.accept` chỉ thực hiện:

~~~java
processed++;
total = total.add(order.amount());
if (order.customer().contains("😀")) unicodeRecords++;
~~~

Snippet này nằm trong class `Stats` của demo, sử dụng `BigDecimal`, không lưu mỗi record. Nếu mục tiêu của hệ thống chỉ là tổng lượng hoặc giá trị aggregate, đừng tạo `List<Order>` rồi gọi `stream().reduce()` ở cuối khi có thể cập nhật biến aggregate trong lúc parse.

### Ghi JDBC theo batch cố định

Một sink có thể giữ **tối đa 500 records**, gọi `PreparedStatement.addBatch()/executeBatch()`, rồi `clearBatch()` và tiếp tục. Mô hình:

~~~text
Parser: Order 1 → OrderSink → batch size 1
Parser: Order 2 → OrderSink → batch size 2
...
Parser: Order 500 → OrderSink → executeBatch; clearBatch
Parser: Order 501 → OrderSink → batch size 1
...
Đến END_DOCUMENT: flush batch cuối và commit theo policy
~~~

**Đây là kiến trúc, không phải chương trình JDBC tự chạy**: cần DataSource/connection, bảng và transaction manager thật. Cẩn trọng:
- **Batch size** phải hữu hạn; mỗi item phải được validate trước khi bind.
- **Transactions:** commit mỗi batch làm dữ liệu có thể **được ghi một phần** nếu record muộn gặp lỗi. Chỉ phù hợp khi contract cho phép partial import và có checkpoint/recovery.
- Nếu yêu cầu **all-or-nothing**, dùng transaction rộng phù hợp hoặc staging table + atomic publish. Một transaction kéo dài cho file cực lớn có thể gây long-running locks, log growth hoặc timeout; cần thiết kế DB-specific.
- **Idempotency key:** nếu consumer đã commit vài batches rồi app retry từ đầu, phải tránh duplicate/overwrite không mong muốn bằng unique import ID + record key, upsert policy hoặc ledger.
- **Backpressure:** nếu DB chậm hơn parser, đừng nối records vào queue không giới hạn. Dùng bounded queue, blocking/suspension có deadline hoặc xử lý synchronous sink để parser tự chậm lại.
- **Error flow:** `OrderSink.accept` trong demo khai báo `throws Exception`; nếu sink báo lỗi, parser dừng và đóng resources. Đừng catch rồi tiếp tục im lặng khi đã mất dữ liệu.
- **Security:** dùng `PreparedStatement` parameters, không tạo SQL từ XML text bằng phép nối chuỗi.
- **Traceability:** ghi file/import ID, record sequence, lỗi validation đã sanitize, trạng thái import đang staging/committed/failed.

### Staging rồi publish: bảo toàn tính nguyên tử ở tầng ứng dụng

Một pipeline an toàn cho các file quan trọng:

~~~text
(1) Nhận file vào temp/object storage theo policy giới hạn.
(2) Parse record-by-record bằng StAX.
(3) Ghi vào staging với import_id và record_id,
    các thao tác ghi có giới hạn batch.
(4) Nếu bất kỳ lỗi XML/domain/size/DB → mark FAILED,
    loại staging hoặc giữ theo retention policy để điều tra.
(5) Nếu đã đọc đến END_DOCUMENT và mọi record hợp lệ →
    transaction publish/import visible; mark COMMITTED.
(6) Cleanup/quarantine source, emit metrics và thông báo.
~~~

Cách này không có nghĩa staging tự động an toàn trước concurrent writes: vẫn cần unique keys, access controls, tenant isolation, transaction/lock isolation và cleanup. Nhưng nó tách **quá trình parse lâu, có thể thất bại** khỏi **thời điểm dữ liệu chính thức có hiệu lực**, giúp tránh “nửa file đầu đã commit” ngoài ý muốn.

### Consumer qua queue hoặc HTTP

StAX không áp dụng backpressure cho network/queue một cách tự động. Nếu `sink.accept()` đồng bộ và có timeout rõ, parser sẽ chờ consumer trước khi gọi `next()` tiếp — đây là cơ chế tự giới hạn đơn giản. Nếu sink chuyển sang async, queue phải **bounded** và có chính sách lỗi/cancel/retry; nếu không, buffer sẽ tăng tới hàng triệu records dù parser luôn stream.

Không gửi emails/payments/external side effects cho từng record ngay khi parser chưa xác nhận whole-file validity nếu nghiệp vụ yêu cầu all-or-nothing. Nếu buộc phải xử lý incremental, thiết kế **idempotent consumer, deduplication và compensation**.

## 9. Xử lý XML schema phức tạp: record không luôn chỉ sâu 3 cấp

Trong nhiều dữ liệu thật, một `order` có `items`/`lineItem` lồng sâu, addresses, metadata, optional fields hoặc mixed content. Khi đó không thể áp quy tắc "depth 3 là customer/amount" của demo.

**Hai cách thiết kế:**

- **State machine/stack theo path:** stack lưu các qualified names, kiểm tra state hợp lệ và độ sâu; parse từng sub-record, emit khi đóng `</order>`.
- **Tách parser cho một subtree:** khi gặp `START_ELEMENT order`, tiêu thụ chính xác các events cho tới matching `END_ELEMENT` bằng depth counter, rồi trả domain object (hoặc stream nested elements). Nếu muốn giới hạn bộ nhớ, không dựng DOM cho toàn subtree lớn.

Ví dụ helper depth counter thuần ở mức khái niệm:

~~~java
static void skipElement(XMLStreamReader reader) throws XMLStreamException {
    if (reader.getEventType() != XMLStreamConstants.START_ELEMENT) {
        throw new XMLStreamException("Expected START_ELEMENT");
    }
    int nested = 1;
    while (nested > 0 && reader.hasNext()) {
        int event = reader.next();
        if (event == XMLStreamConstants.START_ELEMENT) nested++;
        else if (event == XMLStreamConstants.END_ELEMENT) nested--;
        else if (event == XMLStreamConstants.DTD) {
            throw new XMLStreamException("DTD is not allowed");
        }
    }
    if (nested != 0) throw new XMLStreamException("Incomplete element");
}
~~~

Đây là **method minh họa** trong class với XMLStreamReader đã cấu hình an toàn, không phải phần parser đơn hàng chuẩn ở trên. Nó chỉ bỏ qua một subtree, **không tự validate nội dung các phần tử bị bỏ qua**. Nếu policy cấm unknown elements, không nên gọi skipElement cho nội dung lạ; hãy từ chối input. Nếu policy cho phép extensions, skip có thể hữu ích nhưng cần **giới hạn depth/events/bytes áp cho cả subtree bị bỏ qua**, không chỉ phần được xử lý. Sau method, reader đứng ở `END_ELEMENT` của subtree đã bỏ qua; caller phải hiểu vị trí cursor để không xử lý lại hoặc bỏ sót event.

### Các bẫy state machine

1. Không validate namespace, chỉ so local name → chấp nhận sai schema.
2. Increment depth khi `getElementText()` đã consume END_ELEMENT nhưng không điều chỉnh → state lệch.
3. Nhận duplicate `<amount>` rồi cho giá trị sau ghi đè đầu → dữ liệu mơ hồ.
4. Chỉ kiểm tra field có mặt mà không xét thứ tự/multiplicity nếu schema đòi hỏi.
5. Coi `<customer><![CDATA[abc]]></customer>` khác ngữ nghĩa hẳn `<customer>abc</customer>`, trong khi thông tin text có thể tương đương.
6. Giả định mỗi `CHARACTERS` hoàn chỉnh một field; text có thể chia nhiều events.
7. Dùng `StringBuilder` không giới hạn để gom CDATA/text, phá mục tiêu memory bounded.
8. Đọc tới hết records dự kiến rồi bỏ qua phần đuôi XML, không phát hiện malformed suffix.
9. Không reset field state sau khi emit order, dẫn đến lẫn dữ liệu giữa records.
10. Tạo `Order` ngay ở START_ELEMENT trước khi validate nested fields.

**Một StAX parser streaming đủ nghiêm túc phải gắn với schema/domain contract rõ**, không phải một vòng lặp chỉ tìm tag theo tên.

## 10. Lỗi, chẩn đoán và kết thúc sạch

Các lỗi có thể phát sinh tại nhiều ranh giới:

| Nguồn lỗi | Ví dụ | Phản ứng phù hợp |
| --- | --- | --- |
| File I/O | File missing, permission, disk/network I/O | `IOException`, cleanup source, báo lỗi hệ thống |
| XML syntax | Unclosed tag, duplicate root, invalid character | `XMLStreamException`, không publish partial import |
| XML security | DTD/external entities, quota bytes/events/depth | Từ chối input, không tiếp tục parse |
| Domain validation | Thiếu `customer`, amount âm/không đúng format | Báo record/path, không accept như thành công |
| Format conversion | `BigDecimal` không parse được text | Validate regex/length trước conversion, không dùng double cho money |
| Backpressure | DB chậm, queue đầy, deadline hết | Dừng/đợi có giới hạn, release resources, retry có policy |
| Transaction/database | Constraint violation, batch error, commit uncertainty | Rollback/reconcile theo DBMS, idempotency |
| Cleanup | `XMLStreamReader.close()` hoặc source close lỗi | Giữ primary exception, suppressed cleanup errors |

Trong ví dụ, `invalid(String, XMLStreamReader)` tạo `XMLStreamException` với `Location` (line/column) từ parser. Đây là vị trí có ích cho debugging, nhưng **không** tự bao gồm một record index, ID an toàn hoặc business error type. Application production có thể giữ `file/import ID`, thứ tự record và loại lỗi để báo cáo mà không log XML payload chứa PII hoặc access tokens.

### Vì sao cần `CursorLease`?

`XMLStreamReader` có `close()` nhưng **không implement `AutoCloseable`** theo interface Java 17/25. Vì thế:

~~~java
static final class CursorLease implements AutoCloseable {
    final XMLStreamReader reader;
    CursorLease(XMLStreamReader reader) { this.reader = reader; }
    @Override public void close() throws XMLStreamException { reader.close(); }
}
~~~

Từ đó:

~~~java
try (InputStream raw = Files.newInputStream(file);
     CursorLease lease = new CursorLease(
             factory.createXMLStreamReader(raw))) {
    // Dùng lease.reader.
}
~~~

Đây là snippet nằm trong method. Java đóng `CursorLease` **trước** `InputStream` vì tài nguyên được đóng theo thứ tự ngược khai báo. Nếu parse lỗi và close cũng lỗi, try-with-resources giữ exception parse là primary, thêm exception cleanup vào `getSuppressed()`. Nếu factory tạo reader lỗi, input đã mở vẫn được đóng. Không đẩy trách nhiệm đóng file vào `XMLStreamReader.close()`.

### Reader có thể read-ahead

Sau khi parser đã đọc `START_ELEMENT` của record đầu, nó có thể đã prefetch dữ liệu của những record sau. Nếu nguồn chứa nhiều XML documents ghép nối tiếp hoặc một protocol có framing, không dùng cách “parse xong một record rồi trả nguồn cho người khác đọc” mà không có **explicit length framing/bounded stream**. Một XML parser không phải message framer, và XML chỉ có một document root hợp lệ theo cấu trúc thông thường.

### Đừng nuốt exception rồi báo thành công

~~~java
try {
    streamOrders(file, sink);
} catch (Exception error) {
    // Sai: chỉ log rồi báo import SUCCESS.
}
~~~

Đây là anti-pattern minh họa. Đọc được 9999/10000 records mà record cuối malformed vẫn là import failure nếu contract đòi whole-file correctness. Retry cần phân biệt lỗi nguồn, XML malformed (retry y nguyên sẽ lỗi lại), lỗi DB tạm thời và tình huống partial side effects. Không dùng blanket retry vô hạn.

## 11. Hiệu năng: đo đúng và tối ưu đúng chỗ

### Tại sao loop per-record thường nhanh và tiết kiệm?

- Không giữ toàn bộ XML DOM.
- Hạn chế tạo object `Order` chỉ khi một record đủ field.
- Chỉ giữ vài thuộc tính và text field được bound.
- Parser có thể xử lý nhiều events từ InputStream theo bộ đệm nội bộ.
- Consumer có thể aggregate tại chỗ hoặc flush batch có giới hạn.

Nhưng kết quả thực còn phụ thuộc workload, JVM/provider, I/O và consumer. Dữ liệu XML có hơn 50% thời gian nằm trong DB writes thì tối ưu `StringBuilder` có thể ít tác dụng; ngược lại, parsing XSD phức tạp có thể chiếm nhiều CPU.

### Một số thực hành có giá trị

| Kỹ thuật | Khi nào hữu ích? | Thận trọng |
| --- | --- | --- |
| `BufferedInputStream` | I/O từ file/remote stream nhỏ chunk | Provider có thể đã buffer; đo trước khi thêm |
| `XMLStreamReader` thay `XMLEventReader` | Khi cần ít object per event | Không cam kết nhanh hơn mọi provider |
| Dùng `BigDecimal` cho money | Không làm tròn sai kiểu floating point | Validate scale/precision/currency |
| Chỉ giữ một record | Tệp chứa rất nhiều records | Downstream phải bounded |
| Fixed batch size | Ghi JDBC nhiều rows | Transaction, failure semantics, pool pressure |
| Byte quota ở source | Input không tin cậy | Đo bytes ở đúng tầng (sau giải nén nếu cần) |
| Max events/depth/text length | Chống XML cấu trúc độc hại | Phải áp cả unknown subtrees |
| Hạn chế logging per record | Tệp lớn | Giữ aggregate metrics và error samples có giới hạn |
| Staging file/table | Cần all-or-nothing hoặc reprocessing | Disk/storage quota, cleanup và access control |
| Backpressure/deadline | Downstream chậm | Đừng để unbounded async queue |
| Reusable parser factory theo provider contract | Throughput cao | Không mutate factory concurrent nếu chưa chắc thread-safe |

### Đừng dùng DOM để “tiện validate” toàn file lớn

Nếu chỉ cần kiểm tra 3 trường trên mỗi record, DOM có thể lãng phí RAM. Nhưng nếu nghiệp vụ cần cross-record validation (unique IDs, tổng cross-file, tham chiếu nhiều record), streaming vẫn có thể cần **một tập trạng thái** (ví dụ set IDs) hoặc database index. Khi đó bộ nhớ không còn O(1) theo số records; có thể dùng **external sort/staging unique constraint** thay vì HashSet hàng triệu IDs trong heap.

Nếu cần XSD validation, `SchemaFactory`/`Validator` là thành phần JAXP khác, với security configuration riêng. StAX không có một switch chuẩn tự xác nhận mọi record theo XSD. Một streaming validation pipeline có thể dùng `StAXSource`/`Validator` nếu phù hợp, nhưng vẫn cần xử lý provider behavior và quotas. Không mặc định phần tử well-formed đồng nghĩa domain/schema hợp lệ.

### Benchmark phù hợp

Thử các file tăng dần (ví dụ 10k, 100k, 1M records), đồng nhất schema và dữ liệu, chạy trên JDK và StAX provider deployment thật. Đo:
- Wall-clock time và records/second.
- Allocation rate, peak heap, GC pauses.
- Bytes read và I/O throughput.
- CPU parser vs business validation vs downstream sink.
- Queue depth, batch flush latency, JDBC pool waits.
- End-to-end latency/deadlines và retry rate.

Không lấy stdout của demo làm benchmark. In sáu dòng tóm tắt không phản ánh peak memory; để xác nhận bounded-memory cần thử input vượt dung lượng heap trong **test môi trường cô lập** và so với DOM/naive approaches.

## 12. Bảo mật và tính đúng đắn ở cấp file

### XXE không phải rủi ro duy nhất

Ngoài external entities, còn có:
- Nested elements sâu gây stack/state explosion.
- Rất nhiều attributes/namespace declarations.
- Text nodes khổng lồ và Unicode edge cases.
- Data-decompression bombs nếu đọc ZIP/GZIP.
- Quá nhiều bản ghi làm DB/queue/logging overload.
- Không xác minh root/version/namespace nên chấp nhận schema khác.
- Malformed phần cuối file làm partial writes đã xảy ra.
- Duplicated record IDs hoặc order fields.
- SQL injection nếu consumer nối XML text vào SQL thay vì bind parameters.
- Việc output sang HTML/XML khác không escape theo context, có thể dẫn tới XSS hoặc XML injection.

Giới hạn bytes/events/depth/fields giúp giảm một số rủi ro, **không thay thế** authentication, authorization, quota per tenant, file lifecycle và transaction/business validation.

### UTF-8, Unicode và encoding declaration

StAX nhận `InputStream` có thể giải mã XML theo declaration/BOM. Tệp mẫu được ghi với `XMLOutputFactory.createXMLStreamWriter(out, "UTF-8")` và `writeStartDocument("UTF-8","1.0")`, bảo đảm declaration và output bytes nhất quán trong demo. Tiếng Việt và emoji đi qua Java `String`; ứng dụng không tự byte-encode/escape surrogate pairs trong nội dung XML.

Nếu file input khai báo encoding không khớp bytes, parser có thể lỗi hoặc tạo ký tự sai tùy provider; không “sửa” bằng cách mặc định chuyển mọi byte stream sang `UTF-8` theo ý mình rồi phớt lờ XML declaration. Khi dùng `Reader`, caller đã quyết định charset nên parser không thể suy ra bytes gốc.

### Kiểu tiền và validation

Trong ví dụ, `BigDecimal` được parse từ chuỗi có đúng 2 chữ số thập phân và currency `USD`. Đây là domain policy minh họa, không phải cú pháp money bắt buộc trong XML. Với hệ thống thật:
- Xác định scale theo currency và hợp đồng nghiệp vụ.
- Không dùng `double`/`float` cho giá trị tiền tệ chính xác.
- Kiểm tra giá trị âm, rất lớn, định dạng exponent, locale và rounding.
- Dùng typed validated value, không giữ raw user strings suốt downstream.
- Cân nhắc tổng số record và duplicate IDs trong staging/DB constraints.

## 13. Kiểm thử với tệp lớn: danh sách các tình huống cần có

| Test | Kỳ vọng |
| --- | --- |
| Tệp rỗng | Báo lỗi do thiếu root/XML declaration hợp lệ |
| Root `orders` đúng namespace | Đọc được records |
| Root cùng local name, sai namespace | Parser từ chối |
| Prefix `o` đổi thành `x` cùng URI | Parser vẫn đọc đúng |
| 0 records hợp lệ | Chấp nhận hay từ chối theo business policy riêng |
| 10.000 records | Count đúng, không tích trữ List |
| Hơn max records | Từ chối, cleanup resources |
| Field quá MAX_FIELD_CHARS | Từ chối trước khi append vượt quota |
| XML depth lớn hơn 3 | Từ chối nested element |
| Nhiều CHARACTERS events trong field | Ghép chính xác, không mất text |
| CDATA trong customer | Đọc như text theo policy |
| Duplicate customer/amount | Từ chối |
| Missing amount/currency | Từ chối |
| Wrong money format / huge exponent | Từ chối |
| Ngoài namespace hoặc unexpected element | Từ chối |
| Text không-whitespace giữa records | Từ chối |
| DTD/external entity | Bị chặn, không truy cập filesystem/mạng |
| Byte quota vượt | Ném lỗi và đóng file stream |
| Event quota vượt | Ném lỗi, không treo parse |
| XML thiếu end tag ở cuối | Fail whole-file dù records đầu đã emit |
| Consumer exception ở record thứ N | Stop ngay, cleanup và rollback/stage according policy |
| Source IOException khi đọc | Không báo import SUCCESS, close resources |
| EOF sau END_DOCUMENT | Đúng semantics xác nhận tệp |
| Unicode tiếng Việt/emoji | Giá trị `String` giữ đúng code points |
| File lớn có nhiều whitespace/comments | Quota events và bytes vẫn áp dụng |
| Non-closing borrowed stream | Caller còn quyền sở hữu, nhưng kiểm tra provider read-ahead |
| JDBC batch flush lỗi | Không có partial publish ngoài policy |
| Retry sau partial staging | Idempotency keys, cleanup/resume đúng |
| Concurrency nhiều file | Quota per tenant và pool limits, không share XMLStreamReader |
| Tệp nén rất nhỏ nhưng nở lớn | Decompressed byte limit hoạt động |

### Kiểm thử lỗi “gần cuối file” là đặc biệt quan trọng

Đừng chỉ test một XML sai từ byte đầu: nhiều bug xuất hiện khi đã emit hàng nghìn records rồi parser mới phát hiện unclosed root. Nếu consumer có side effects, cần xác nhận rollback, staging isolation hoặc compensation. Trong đơn vị test, một `OrderSink` có thể đếm các calls; trong integration test DB, kiểm tra **không có dữ liệu published** sau khi toàn file thất bại.

### Concurrency và factory lifecycle

`XMLStreamReader` giữ cursor state, không dùng chung một instance cho nhiều threads. `XMLInputFactory` có mutable properties; configure trước tạo readers và không mutate đồng thời nếu provider không bảo đảm thread-safety. Mỗi file nên có **reader/input scope độc lập** và quota rõ. Đừng tăng số parse workers đến mức hàng nghìn file descriptors/threads/DB connections bị giữ, ngay cả khi memory per parser nhỏ.

## 14. Những lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách làm |
| --- | --- | --- |
| Dùng DOM để đọc tệp khổng lồ không cần random access | Heap pressure/OOM | StAX/SAX streaming |
| Dùng StAX nhưng `List.add(record)` mọi record | Memory vẫn tăng theo input | Consumer bounded / staging |
| Coi StAX mặc định chống XXE | Có thể đọc file/SSRF | Disable DTD/external entities, EAP và resolver policy |
| Không giới hạn input bytes/events/depth | DoS parser hoặc consumer | Quotas từ input đến sink |
| Chỉ validate record, không đọc đến END_DOCUMENT | Malformed suffix không được phát hiện | Full-document validation |
| Emit ngay ở START_ELEMENT order | Record chưa đầy đủ | Emit sau END_ELEMENT |
| Dựa vào `getLocalName` mà bỏ namespace | Nhận sai XML schema | So namespace URI + local name |
| Cho phép unknown nested elements mà không có depth cap | Parser thiếu bảo vệ | State machine + max depth |
| Dùng `getElementText` cho field không giới hạn | Tạo String rất lớn | Bounded CHARACTERS buffer |
| Giả định một field là một CHARACTERS event | Mất dữ liệu text/CDATA | Ghép nhiều events có quota |
| Không reset state sau mỗi order | Lẫn dữ liệu records | Tạo/reset state per-record |
| Bỏ qua duplicate elements | Ghi đè value đầu | Validate multiplicity |
| Dùng `double` cho amount | Sai chính xác | BigDecimal + scale policy |
| Xem mọi XML well-formed là đúng nghiệp vụ | Thiếu field/schema constraints | Domain/XSD validation riêng |
| Dùng `XMLStreamReader` trực tiếp trong TWR | Interface không AutoCloseable | Adapter hoặc finally |
| Chỉ đóng parser, không đóng InputStream | Resource leak | Scope cả parser và nguồn |
| Đọc file xong commit batch đã flush dù tệp malformed | Partial import | Staging/transaction policy |
| Async sink unbounded | Queue OOM | Bounded queue/backpressure |
| Retry cả file sau partial commits không có idempotency | Trùng orders | import_id/record_id, dedup |
| Không phân biệt malformed XML với I/O lỗi | Retry sai | Error taxonomy rõ |
| Quá nhiều logs từng record | I/O bottleneck, PII exposure | Aggregate metrics + sampled sanitized diagnostics |
| Để raw URL/systemId tự mở external resource | XXE/SSRF | Không cho external access, resolver policy |
| Đổi XML prefix rồi coi khác schema | Sai XML namespaces | Expanded names dùng URI/localName |
| Coi demo 10.000 rows là benchmark production | Không đo memory/DB | Test provider/DB/production workload |
| Quên tăng ID/size quotas khi scale 1M | Input bị từ chối theo policy cũ | Thiết kế quotas theo thực tế, có test |

## 15. Checklist triển khai thực tế

1. **Định nghĩa schema/root/namespace** và đâu là một record hoàn chỉnh.
2. **Chọn XMLStreamReader** nếu muốn trực tiếp điều khiển vòng pull và state machine; chọn XMLEventReader khi cần event objects.
3. **Bảo vệ nguồn ngay lúc mở:** giới hạn bytes, I/O timeout, compressed/uncompressed quotas.
4. **Cấu hình XMLInputFactory** trước khi tạo reader, chặn DTD/external entities/URL resolution.
5. **Theo dõi depth, events, record count** và length/attribute quotas.
6. **Validate record fields trước khi emit**, tránh getElementText không giới hạn.
7. **Phát mỗi record đúng một lần** vào OrderSink với bounded memory.
8. **Thiết kế downstream contract:** đồng bộ có backpressure, bounded batch, idempotency, transaction hoặc staging.
9. **Đọc tới END_DOCUMENT** trước khi công bố “file import successful”.
10. **Đóng reader rồi input** trên cả success/error/cancellation; giữ suppressed errors.
11. **Không dùng mutable reader chung giữa threads**, tách scope từng file.
12. **Quan sát throughput/memory/GC**, file bytes, errors, record count, downstream waits.
13. **Test malformed cuối file, XXE, nested XML, huge text, duplicate fields, Unicode, quota.**
14. **Không log toàn XML**, sanitize error location và file/import IDs.
15. **Rà soát khi nâng JDK/provider** vì StAX property support và parser buffering có thể thay đổi.

## 16. Câu hỏi tự kiểm tra

1. **Tại sao StAX thích hợp tệp nhiều records?** Vì caller xử lý từng XML event/record, không cần dựng DOM toàn tệp.
2. **StAX có tự bảo đảm O(1) memory không?** Không; parser buffers, text fields và downstream collections có thể làm memory tăng.
3. **Khi nào emit một order?** Sau `END_ELEMENT order` khi mọi field đã được validate.
4. **Vì sao đếm depth?** Để xác định đúng ranh giới record, trường và chặn nested structure sai.
5. **`getElementText()` có rủi ro gì với tệp không tin cậy?** Nó materialize toàn bộ text field thành String trước khi app giới hạn.
6. **Text trong field có thể xuất hiện thành nhiều events không?** Có, nên phải append theo chunks có quota.
7. **Tại sao kiểm tra cả namespace URI và localName?** Prefix/local name riêng không đủ xác định element semantics.
8. **Vì sao dùng InputStream thay Reader khi muốn parser xử lý XML encoding declaration?** InputStream giữ bytes để parser tự decode theo XML rules.
9. **Quota byte stream nên đặt ở đâu?** Ở nguồn đang đọc; với nén cần giới hạn cả sau giải nén.
10. **Một byte quota có ngăn mọi XML bomb không?** Không, vẫn cần events, depth, attributes, field length và deadlines.
11. **Cấu hình StAX nào chống XXE?** Tắt DTD, external entities, hạn chế ACCESS_EXTERNAL_DTD, đặt XMLResolver có policy.
12. **StAX có FEATURE_SECURE_PROCESSING như DOM không?** Không theo cùng cách; dùng StAX properties và EAP.
13. **Vì sao `XMLStreamReader.close()` không đủ để đóng file?** Javadoc không hứa đóng underlying InputStream.
14. **Có thể đưa XMLStreamReader vào try-with-resources trực tiếp không?** Không theo interface; dùng AutoCloseable adapter hoặc finally.
15. **Vì sao streamOrders dùng `OrderSink` thay `List<Order>`?** Để downstream quyết định xử lý có giới hạn, không giữ toàn bộ records.
16. **Trong demo, 10.000 orders có tổng amount bao nhiêu?** `49995000.00` vì amount i.00 với i từ 0 tới 9999.
17. **Khi XML lỗi ở cuối, những records đầu đã emit có an toàn commit chưa?** Không tự động; cần staging/transaction policy.
18. **Nếu consumer báo lỗi, parser cần làm gì?** Dừng và cleanup nguồn/parser, để caller xử lý transaction/error.
19. **Tại sao cần MAX_RECORDS khi đã có MAX_BYTES?** Một file nhỏ có thể chứa rất nhiều records rất ngắn.
20. **Nếu đầu vào có element cùng localName nhưng namespace khác, chấp nhận không?** Không nếu schema yêu cầu một namespace cố định.
21. **XMLStreamWriter có tự escape `&` trong text?** Có qua `writeCharacters`.
22. **Một record có amount là `1E999999` nên làm gì?** Validate format/precision trước khi gọi BigDecimal, không tạo giá trị không giới hạn.
23. **Tại sao cần giới hạn queue size khi dùng async consumer?** Queue không giới hạn làm mất lợi thế streaming.
24. **XML prefixes khác nhau nhưng URI/localName giống nhau có cùng schema semantics không?** Có thể tương đương theo XML namespace rules.
25. **Khi nào chọn staging table?** Khi cần tránh partial publication dù parsing/batching diễn ra lâu.
26. **Có nên log nguyên XML khi parse lỗi?** Không, có thể chứa PII/secrets; log metadata đã sanitize.
27. **Làm sao biết whole XML document đã hợp lệ về cú pháp?** Tiếp tục parse đến `END_DOCUMENT` và kiểm tra error/limits.
28. **Nếu muốn XSD validation thì StAX tự làm không?** Không, cần SchemaFactory/Validator hoặc validation pipeline riêng.
29. **Nếu cần 1 triệu orders, thay đổi gì?** Quotas, ID format, throughput/deadline, staging/batch capacity, tests.
30. **Một unit test tệp 10.000 rows chứng minh điều gì?** Luồng application parse/aggregate đúng; không chứng minh memory/performance/DB transaction trong production.

## 17. Tài liệu chính thức còn áp dụng

- [Java SE 25 — javax.xml.stream package](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/stream/package-summary.html): StAX cursor/event readers, writers và XMLStreamException thuộc module `java.xml`.
- [Java SE 25 — XMLStreamReader](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/stream/XMLStreamReader.html): `next`, `hasNext`, `getTextCharacters`, `getTextLength`, `getElementText`, `getNamespaceURI`, `getAttributeValue` và `close`.
- [Java SE 25 — XMLInputFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/stream/XMLInputFactory.html): tạo StAX readers; `SUPPORT_DTD`, `IS_SUPPORTING_EXTERNAL_ENTITIES`, `IS_NAMESPACE_AWARE`.
- [Java SE 25 — XMLStreamConstants](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/stream/XMLStreamConstants.html): `START_ELEMENT`, `END_ELEMENT`, `CHARACTERS`, `CDATA`, `DTD`, `END_DOCUMENT`.
- [Java SE 25 — XMLStreamException](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/stream/XMLStreamException.html): lỗi XML và `Location` khi có.
- [Java SE 25 — XMLOutputFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/stream/XMLOutputFactory.html) và [XMLStreamWriter](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/stream/XMLStreamWriter.html): ghi XML từ từng bản ghi với namespace và UTF-8.
- [Java SE 25 — JAXP Security Guide](https://docs.oracle.com/en/java/javase/25/security/java-api-xml-processing-jaxp-security-guide.html): StAX external-access restrictions, DTD policy, processing limits và resolver security.
- [Java SE 25 — java.io.FilterInputStream](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/FilterInputStream.html): bọc stream với counting/limiting behavior.
- [Java SE 25 — java.nio.file.Files](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html): `newInputStream`, `newOutputStream`, file lifecycle và temporary files.
- [Java SE 25 — java.math.BigDecimal](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/math/BigDecimal.html): parse/tính toán decimal chính xác cho nghiệp vụ tiền tệ.
- [W3C — Namespaces in XML 1.0](https://www.w3.org/TR/xml-names/): phân biệt localName, namespace URI và prefix.

**Kết luận:** Với XML rất lớn, thành công không nằm ở việc chuyển `DocumentBuilder.parse` sang `XMLStreamReader.next` một cách máy móc. Hãy **tổ chức parser thành state machine theo ranh giới record**, giữ từng field có giới hạn, validate trước khi phát ra consumer, giới hạn I/O/DTD/depth/events/records, đóng parser và source có ownership rõ ràng, và thiết kế **staging/backpressure/transaction policy** để một lỗi ở cuối file không biến dữ liệu đã xử lý trước đó thành partial import không mong muốn.