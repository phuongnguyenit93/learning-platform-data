# Lựa chọn StAX khi cần bộ nhớ giới hạn và đọc tuần tự

## 1. Bài toán: XML lớn, nhưng ứng dụng chỉ cần đọc từng bản ghi

Giả sử một hệ thống nhận file XML gồm hàng trăm nghìn phần tử `<record>`, trong khi yêu cầu thực tế chỉ là **đọc tuần tự, kiểm tra từng bản ghi và chuyển tiếp cho bước xử lý tiếp theo**. Nếu xây cả cây DOM trong bộ nhớ, chi phí heap có thể lớn hơn đáng kể kích thước file XML vì ứng dụng giữ nodes, attributes, text, quan hệ cha–con và những đối tượng liên quan.

**StAX** (*Streaming API for XML*) là API **pull parsing** của Java: ứng dụng điều khiển thời điểm lấy sự kiện/phần tử tiếp theo từ nguồn XML. Khi chỉ giữ dữ liệu của **một phần tử đang xử lý**, có thể giảm mạnh lượng dữ liệu XML phải giữ trong application heap so với DOM.

~~~text
File/InputStream/Reader XML
             |
             v
      XMLInputFactory
             |
             v
    XMLStreamReader (cursor)
             |
             | next() tiến về phía trước
             v
  START_ELEMENT -> CHARACTERS -> END_ELEMENT
             |
             v
  Validate + xử lý 1 record -> ghi/đẩy đi
             |
             v
  Bỏ tham chiếu record cũ, đọc record kế tiếp
~~~

**Quy tắc cần nhớ:** StAX không tự bảo đảm “bộ nhớ luôn là hằng số”. Tổng memory còn phụ thuộc **parser implementation, kích thước event/text buffer, độ sâu XML, namespace/DTD, việc coalescing, và đặc biệt cách application gom dữ liệu**. Nếu gọi `getElementText()` trên phần tử chứa vài GB text, hoặc thêm mọi record vào `ArrayList`, chương trình vẫn có thể hết bộ nhớ.

### Mục tiêu học tập

Sau bài này, bạn sẽ biết:

1. Khi nào chọn StAX thay vì DOM, SAX hoặc một parser mapping object.
2. Phân biệt `XMLStreamReader` (cursor) và `XMLEventReader` (event objects) của StAX.
3. Viết parser tuần tự bằng `XMLInputFactory.newFactory()`, `hasNext()`, `next()` và `XMLStreamConstants`.
4. Chỉ giữ trạng thái một record và giới hạn kích thước trường, độ sâu, số bản ghi.
5. Xử lý `CHARACTERS` chia thành nhiều chunks, XML namespaces, attributes, whitespace và vị trí cursor.
6. Khóa DTD, external entities và quyền truy cập external DTD; **fail-closed** nếu parser không hỗ trợ security configuration cần thiết.
7. Đóng `XMLStreamReader`/`XMLEventReader` **và** `InputStream/Reader`; hiểu vì sao đóng parser không mặc định đóng nguồn.
8. Kiểm thử chương trình Java 17+ trên dữ liệu XML sinh tuần tự, có case XXE và field oversized.
9. Đánh giá hiệu năng/memory bằng đo đạc trên **driver/parser và workload thật**, không khẳng định O(1) một cách tuyệt đối.

## 2. StAX vẫn là Java API hiện hành

StAX nằm trong module **`java.xml`**, packages:

- `javax.xml.stream`: `XMLInputFactory`, `XMLStreamReader`, `XMLEventReader`, `XMLStreamConstants`, `XMLStreamException`, `XMLOutputFactory`, `XMLStreamWriter`.
- `javax.xml.stream.events`: `XMLEvent`, `StartElement`, `EndElement`, `Characters`, `Attribute`...
- `javax.xml.namespace`: `QName` khi cần so sánh tên gồm namespace URI.
- `javax.xml.XMLConstants`: các thuộc tính hạn chế truy cập XML external resources.

StAX được đưa vào Java SE từ **Java 6** (Javadoc `Since: 1.6`) và **vẫn có trong Java SE 26**. Các ví dụ ở đây biên dịch bằng **`javac --release 17`**, dùng Java 17+ nhưng trọng tâm vẫn là StAX còn hỗ trợ — không dạy những đường API lỗi thời.

**Tên package `javax.xml.stream` là đúng** cho API StAX của Java SE hiện nay. Đừng tự đổi thành `jakarta.xml.stream`; đây không phải package tương ứng mà JDK dùng.

Một nguồn XML có thể đến từ `Files.newInputStream(path)`, `Files.newBufferedReader(path, UTF_8)`, HTTP body stream được giới hạn, hoặc stream nguồn khác. **Không bắt buộc đọc thành `String` hoặc `byte[]` trước khi parse**.

## 3. So sánh StAX, DOM, SAX và object binding

| Tiêu chí | DOM | SAX | StAX | XML-to-object binding |
| --- | --- | --- | --- | --- |
| Cách đọc | Xây cây document để duyệt tùy ý | Parser **đẩy** callbacks đến handler | Application **kéo** event/cursor bằng `next()` | Thường tạo object model; phụ thuộc cách binding |
| Chọn thời điểm đọc tiếp | Sau khi dựng cây | Do parser điều phối; callback-based | **Do vòng lặp của application** | Framework-dependent |
| Truy cập ngẫu nhiên | Thuận lợi: parent/children/siblings | Không thuận lợi | Không thuận lợi; thường chỉ tiến | Thuận tiện nếu object model đã materialize |
| Bộ nhớ ứng dụng | Thường tăng theo tổng kích thước cây | Có thể giữ ít nếu handler chỉ xử lý hiện tại | Có thể giữ ít nếu không tích lũy | Có thể lớn nếu build toàn bộ graph |
| State management | Dễ query nhiều vị trí | Callback phải quản lý trạng thái | Application quản lý state rõ ràng trong loop | Schema/domain-driven |
| Xử lý từng item và discard | Cần cố tránh dựng mọi nodes | Phù hợp | **Rất phù hợp** | Có thể có streaming APIs riêng |
| Sửa XML tại vị trí bất kỳ | DOM thuận tiện | Không | Không — cần viết output mới | Framework-dependent |
| Namespace-aware | Có | Có | Có | Có nếu mapping phù hợp |
| Kiểm soát XXE/resource limits | Phải cấu hình an toàn | Phải cấu hình an toàn | **Phải cấu hình an toàn** | Không được mặc định tin là an toàn |

### 3.1. Chọn StAX khi nào?

Chọn StAX khi:

- File XML **lớn** và cấu trúc đủ đều để đi từ đầu tới cuối.
- Bạn chỉ cần đọc các `record/item`, bỏ qua phần không liên quan.
- Có thể xử lý **từng record độc lập** rồi ghi DB, gửi batch có giới hạn hoặc aggregate.
- Muốn tạm dừng đọc khi downstream chậm (backpressure ứng dụng ở mức tự điều phối).
- Muốn dừng sớm sau khi tìm được phần tử cần thiết.
- Không cần XPath tùy ý trên toàn bộ cây đang giữ.
- Có thể kiểm soát depth/field sizes, namespace và input limits.

Ví dụ log import:

~~~text
<records>
    <record id="1"><name>Người 1</name></record>
    <record id="2"><name>Người 2</name></record>
    ...
    <record id="10000"><name>Người 10000</name></record>
</records>
~~~

Nếu application chỉ cần `id` và `name` của mỗi record, StAX có thể parse event cho record 1, xử lý xong rồi tiếp tục record 2 mà **không giữ cả 10.000 record**.

### 3.2. Khi nào DOM hợp lý hơn?

Khi document **nhỏ và có giới hạn kích thước rõ**, cần tìm node nhiều lần, duyệt ngược, chỉnh cây, hoặc sử dụng thao tác cây phức tạp/XPath theo yêu cầu. DOM có thể làm code đơn giản và rẻ hơn chi phí state machine thủ công. Đừng chọn StAX máy móc chỉ vì “streaming tốt hơn”.

### 3.3. Khi nào SAX hợp lý hơn?

SAX (push) cũng có thể dùng bộ nhớ thấp và rất hữu ích khi xử lý theo callbacks phù hợp với ứng dụng hoặc thư viện hiện có. StAX có lợi khi muốn **vòng lặp tuần tự ở tầng gọi** điều khiển khi nào đọc phần tử tiếp theo; SAX có lợi khi logic callback dễ tổ chức hơn. Không có một đáp án hiệu năng universal; benchmark.

### 3.4. Khi nào không nên chọn StAX đơn thuần?

Nếu nghiệp vụ phải nhìn lại nhiều nodes, join dữ liệu giữa phần tử cách xa nhau hoặc sửa sâu XML tại vị trí bất kỳ, có thể cần index/spool tạm, DB staging, parser object model, DOM cho những phần nhỏ, hoặc cấu trúc xử lý khác. Lúc ấy StAX vẫn có thể là bước đầu đọc, nhưng bộ nhớ của **application pipeline** mới là yếu tố quyết định.

## 4. Hai API pull parsing: cursor và event

### 4.1. XMLStreamReader — cursor API

`XMLInputFactory.createXMLStreamReader(...)` trả `XMLStreamReader`. Parser có vị trí hiện tại, kiểu event lấy từ `getEventType()` hoặc kết quả `next()`. API cung cấp:

- `hasNext()`/`next()` để tiến về phía trước.
- `getLocalName()`, `getNamespaceURI()`, `getName()` cho tên element.
- `getAttributeValue(namespaceURI, localName)` / `getAttributeCount()` cho attributes tại `START_ELEMENT`.
- `getTextCharacters()`, `getTextStart()`, `getTextLength()`, `getText()` cho text tại text events.
- `getLocation()` để hỗ trợ chẩn đoán line/column.
- `nextTag()` để bỏ qua whitespace/comment trong những cấu trúc tag-only thích hợp.
- `getElementText()` để đọc text của một element khi đáp ứng contract, **nhưng sẽ tạo String cho toàn bộ nội dung element**.

Cursor thường có ít event-object allocations hơn event API, nhưng **điều đó không tự bảo đảm nhanh hơn trong mọi parser và workload**.

### 4.2. XMLEventReader — iterator/event API

`XMLInputFactory.createXMLEventReader(...)` trả `XMLEventReader`. `nextEvent()` trả các event objects:

- `event.isStartElement()` / `event.asStartElement()`.
- `StartElement.getName()` (QName), `getAttributeByName(QName)`.
- `event.isCharacters()` / `event.asCharacters().getData()`.
- `event.isEndElement()` / `event.asEndElement()`.
- `peek()` cho phép xem event kế tiếp mà không tiến ngay.

Event API thuận tiện khi muốn giữ một event ngắn hạn, chuyển event giữa vài bước, hoặc cần tầng xử lý mang tính object hơn. Đổi lại nó có thể tạo nhiều objects hơn, nên **hãy đo allocation/GC** nếu throughput/heap là điểm quan trọng.

### 4.3. Không nhầm việc “pull” với “tải cả file”

`next()` có thể kích hoạt parser đọc thêm bytes từ source và parse XML. Nó không yêu cầu tải cả file vào String. Nhưng provider có thể dùng internal buffers, đọc trước, hoặc materialize một số construct; vì vậy “StAX = luôn O(1) tổng memory” là kết luận quá mạnh.

## 5. Mô hình event khi đọc tuần tự

Với XML:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<records>
  <record id="7"><name>Xin chào</name></record>
</records>
~~~

Vòng lặp StAX nhận (đơn giản hóa):

~~~text
START_DOCUMENT
START_ELEMENT records
CHARACTERS whitespace
START_ELEMENT record [attribute id=7]
START_ELEMENT name
CHARACTERS "Xin chào"
END_ELEMENT name
END_ELEMENT record
CHARACTERS whitespace
END_ELEMENT records
END_DOCUMENT
~~~

Số lượng `CHARACTERS` và việc trả về `CDATA` riêng phụ thuộc `XMLInputFactory.IS_COALESCING` và provider. **Một node text logic không chắc là một event duy nhất**. Code đúng phải tích lũy *có giới hạn* từng fragment hoặc xử lý từng fragment incremental.

### 5.1. Chỉ gọi getters đúng event

`getLocalName()` chỉ có nghĩa ở `START_ELEMENT`/`END_ELEMENT` phù hợp; `getAttributeValue()` thường dùng ở `START_ELEMENT`; `getTextCharacters()` chỉ khi event có text tương ứng. Gọi accessor sai trạng thái có thể gây `IllegalStateException`/`XMLStreamException` theo contract.

### 5.2. Phần tử rỗng vẫn có hai events

`<name/>` được StAX biểu diễn như `START_ELEMENT name` rồi `END_ELEMENT name`. Không mong một event “EMPTY_ELEMENT” riêng ở cursor API.

### 5.3. Namespace: URI khác prefix

Với:

~~~xml
<a:record xmlns:a="urn:example:records" id="1"/>
<b:record xmlns:b="urn:example:records" id="2"/>
~~~

Hai phần tử (đứng trong một root hợp lệ) **cùng expanded name** `{urn:example:records}record` dù prefix khác. Khi schema định nghĩa namespace, dùng `getNamespaceURI()` + `getLocalName()` hoặc `QName`; **không** chỉ so prefix `a`/`b`. Ví dụ runnable ở mục 8 chủ động chỉ chấp nhận **không namespace** theo input contract của chính nó; muốn hỗ trợ namespace khác phải sửa validation, không tắt namespace processing để “dễ”.

## 6. Bộ nhớ của StAX bị chi phối bởi chính application

Một parser có thể đọc 10.000 records tuần tự nhưng application vẫn hết bộ nhớ nếu:

~~~java
// Phản ví dụ, đây là ý tưởng chứ không phải file độc lập.
List<Record> allRecords = new ArrayList<>();
while (reader.hasNext()) {
    // Parse record...
    allRecords.add(parsedRecord); // Giữ tất cả đến cuối file.
}
~~~

Đây là **đoạn minh họa sai mục tiêu**. Dù StAX parse streaming, `allRecords` làm heap tăng theo số lượng records.

Một pipeline giới hạn memory sẽ:

1. Giữ **current record** hoặc một batch có kích thước tối đa rõ.
2. Xử lý/validate từng record rồi phát ra downstream (DB writer, bounded queue, sink).
3. Không giữ mọi events/nodes/records.
4. Giới hạn **độ dài field**, số nested elements, số attributes, tổng record count và tổng document bytes nếu nguồn không tin cậy.
5. Hạn chế string builder/serialization buffers; kiểm tra parser buffering nếu có element text rất dài.
6. Đóng stream/parser đúng cách cả khi exception.

**Ước lượng ứng dụng:** lượng state do code giữ có thể gần `O(depth + maxCurrentRecordSize + boundedBatchSize)`, **không phụ thuộc trực tiếp số records đã xử lý**. Nhưng đây là giới hạn của thiết kế state trong application, **không phải** lời hứa cứng về heap toàn JVM/JAXP provider.

### 6.1. Vì sao getElementText dễ làm mất lợi ích?

~~~java
// Giả sử reader đang ở START_ELEMENT <payload>.
String payload = reader.getElementText();
~~~

Đây là **đoạn trích**, không chạy độc lập. `getElementText()` trả toàn bộ text của element trong một `String`; một field cực lớn có thể cấp phát lượng RAM lớn. Nó phù hợp với field **đã có giới hạn nhỏ và được tin cậy**, không nên dùng vô điều kiện với XML tải từ bên ngoài.

Ở ví dụ đầy đủ, parser dùng `getTextLength()` + `getTextCharacters()` và **kiểm tra giới hạn trước khi append**.

### 6.2. Coalescing và memory

`XMLInputFactory.IS_COALESCING` khi đặt `true` yêu cầu gộp các đoạn text liền kề/CDATA tương ứng thành một `CHARACTERS` event. Điều này tiện cho code xử lý text nhưng có thể khiến parser **buffer nội dung text lớn hơn**. Ví dụ chọn `false` để dễ kiểm soát fragments. Tuy nhiên không nên hứa `false` là giới hạn tuyệt đối cho buffer của mọi implementation.

### 6.3. Backpressure phải nằm trong pipeline

Nếu bước sau lưu vào database chậm, vòng lặp parser có thể **không gọi `next()` tiếp** khi chưa xử lý xong record. Nếu dùng queue/song song, queue phải **bounded**; một `LinkedBlockingQueue` không giới hạn có thể làm ứng dụng giữ hàng triệu records dù parser chỉ đọc tuần tự.

## 7. Bảo mật StAX khi đầu vào không tin cậy

**XXE (XML External Entity)** có thể cho phép parser truy cập file/network hoặc mở rộng entity gây rò rỉ dữ liệu/DoS nếu cấu hình không an toàn. Đừng dùng các defaults không rõ của provider cho XML upload.

Với `XMLInputFactory` hiện đại, các biện pháp thường cần:

~~~java
XMLInputFactory factory = XMLInputFactory.newFactory();
factory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
factory.setProperty(XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
factory.setXMLResolver((publicId, systemId, baseUri, namespace) -> {
    throw new XMLStreamException("External entity resolution denied");
});
~~~

Đây là **đoạn trích** cần imports từ `javax.xml.stream.*`, `javax.xml.XMLConstants`. Cấu hình cần được thiết lập **trước khi tạo parser**. Ví dụ runnable ở mục 8 dùng cả các biện pháp này và còn **từ chối sự kiện DTD** nếu provider phát ra. Theo Oracle Java SE 26, `ACCESS_EXTERNAL_DTD=""` nghĩa là không cấp quyền giao thức external DTD/DTD entities; đây là thuộc tính có ý nghĩa hiện hành, không phải API legacy.

### 7.1. Fail-closed nếu provider không chấp nhận cấu hình

`XMLInputFactory.setProperty` có thể ném `IllegalArgumentException` nếu property không được hỗ trợ. **Đừng catch rồi lờ đi** các thuộc tính bảo mật bắt buộc. Với untrusted XML, nếu không thể chứng minh parser cấu hình đúng, hãy **từ chối xử lý hoặc chọn provider được kiểm thử**.

Một số implementations có cách quản lý resolver/DTD khác nhau. Cần kiểm thử chính provider thực sự được nạp trong môi trường (classpath/module path) thay vì chỉ chạy với JDK mặc định.

### 7.2. DTD bị vô hiệu hóa chưa thay thế input bounds

Chặn external entities không giới hạn:

- Số bytes XML toàn bộ.
- Số records và elements.
- Độ sâu nesting.
- Số attributes và độ dài attribute.
- Kích thước mỗi text field.
- CPU parsing time, heap, I/O timeout, quota concurrency.
- Dữ liệu sau parse (DB constraints/business validation).

Ví dụ đầy đủ đặt `MAX_DEPTH=8`, `MAX_NAME_UNITS=128` và `MAX_RECORDS=20000`. **Đó không phải giới hạn tổng bytes input**; trong production cần thêm byte-counting wrapper hoặc size policy ở ingestion. `Files.size(path)` chỉ đáng tin với file ổn định và đã được access-control, không phải cơ chế đủ cho một network InputStream không biết length.

### 7.3. Entity expansion, external schema và validation

StAX không mặc định là XSD validator. Nếu nghiệp vụ cần XML Schema validation, dùng `javax.xml.validation.SchemaFactory/Validator` hoặc pipeline tương ứng được cấu hình **hạn chế external DTD/schema**, secure processing và resource limits. `XMLConstants.ACCESS_EXTERNAL_SCHEMA` áp dụng ở validation APIs tương ứng; đừng nhầm `XMLInputFactory` đơn thuần tự validate XSD.

### 7.4. XMLInputFactory từ nhiều providers

`XMLInputFactory.newFactory()` dùng cơ chế chọn provider theo môi trường. Có thể là provider của JDK hoặc một thư viện StAX được đưa vào. Điều kiện hỗ trợ properties và performance có thể khác. Với production, **test security properties và XXE attempts trên provider được deploy**, kiểm tra libraries và không tin defaults.

## 8. Java 17+ runnable: sinh và đọc 10.000 record mà không dựng DOM

Ví dụ `StaxBoundedReaderDemo.java` dùng:

- `BufferedWriter` sinh file UTF-8 10.000 records tuần tự, **không xây một XML String lớn trong bộ nhớ**.
- `XMLStreamReader` đi từng event bằng `reader.next()`.
- Chỉ giữ `recordId`, `currentName`, một `StringBuilder` tối đa 128 UTF-16 code units, `first/last` và thống kê.
- Kiểm tra `depth`, `record count`, tên record và namespace.
- Từ chối `DTD`, không resolve external entities, hạn chế external DTD.
- Test tên quá dài và nested markup bất ngờ.
- Đóng parser bằng `close()` trong `finally`, đóng nguồn `InputStream` bằng try-with-resources; xóa file tạm sau test.

**Giới hạn scope:** parser minh họa chấp nhận duy nhất schema giản lược `<records><record id="..."><name>...</name></record>...</records>` **không namespace**. Nó **không** phải XML schema validator tổng quát; production phải điều chỉnh cho schema thực tế.

### 8.1. File StaxBoundedReaderDemo.java (độc lập)

~~~java
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import javax.xml.XMLConstants;
import javax.xml.stream.*;

public final class StaxBoundedReaderDemo {
    private static final int MAX_DEPTH = 8;
    private static final int MAX_NAME_UNITS = 128;
    private static final int MAX_RECORDS = 20_000;

    record Stats(int records, String first, String last, long nameUnits) {}

    static XMLInputFactory secureFactory() {
        XMLInputFactory factory = XMLInputFactory.newFactory();
        // Fail rather than silently continue if required security controls
        // are not supported by the provider.
        factory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
        factory.setProperty(XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setProperty(XMLInputFactory.IS_COALESCING, false);
        factory.setXMLResolver((publicId, systemId, baseUri, namespace) -> {
            throw new XMLStreamException("External entity resolution denied");
        });
        return factory;
    }

    static Stats parse(InputStream input) throws XMLStreamException {
        XMLStreamReader reader = secureFactory().createXMLStreamReader(input);
        int depth = 0;
        int records = 0;
        boolean inRecord = false;
        String recordId = null;
        String currentName = null;
        String first = null;
        String last = null;
        long units = 0;
        StringBuilder name = null;
        try {
            while (reader.hasNext()) {
                int kind = reader.next();
                switch (kind) {
                    case XMLStreamConstants.DTD:
                        throw new XMLStreamException("DOCTYPE is forbidden");
                    case XMLStreamConstants.START_ELEMENT: {
                        depth++;
                        if (depth > MAX_DEPTH) {
                            throw new XMLStreamException("Depth limit exceeded");
                        }
                        String tag = reader.getLocalName();
                        if (reader.getNamespaceURI() != null
                                && !reader.getNamespaceURI().isEmpty()) {
                            throw new XMLStreamException("Unexpected namespace");
                        }
                        if (depth == 1 && "records".equals(tag)) {
                            // root
                        } else if (depth == 2 && "record".equals(tag)) {
                            if (inRecord) throw new XMLStreamException("Nested record");
                            recordId = reader.getAttributeValue(null, "id");
                            if (recordId == null || recordId.isBlank()) {
                                throw new XMLStreamException("Missing record id");
                            }
                            currentName = null;
                            inRecord = true;
                        } else if (depth == 3 && inRecord && "name".equals(tag)) {
                            if (name != null || currentName != null) {
                                throw new XMLStreamException("Duplicate name");
                            }
                            name = new StringBuilder();
                        } else {
                            throw new XMLStreamException("Unexpected element " + tag);
                        }
                        break;
                    }
                    case XMLStreamConstants.CDATA:
                    case XMLStreamConstants.CHARACTERS:
                    case XMLStreamConstants.SPACE: {
                        if (name != null) {
                            int length = reader.getTextLength();
                            if (length > MAX_NAME_UNITS - name.length()) {
                                throw new XMLStreamException("Name size limit exceeded");
                            }
                            name.append(reader.getTextCharacters(),
                                    reader.getTextStart(), length);
                        } else if (!reader.isWhiteSpace()) {
                            throw new XMLStreamException("Text outside name");
                        }
                        break;
                    }
                    case XMLStreamConstants.END_ELEMENT: {
                        String tag = reader.getLocalName();
                        if (depth == 3 && "name".equals(tag) && name != null) {
                            currentName = name.toString().trim();
                            name = null;
                        } else if (depth == 2 && "record".equals(tag)) {
                            if (!inRecord || currentName == null
                                    || currentName.isEmpty()) {
                                throw new XMLStreamException("Invalid record");
                            }
                            records++;
                            if (records > MAX_RECORDS) {
                                throw new XMLStreamException("Record limit exceeded");
                            }
                            if (records == 1) first = recordId + ":" + currentName;
                            last = recordId + ":" + currentName;
                            units += currentName.length();
                            inRecord = false;
                        }
                        depth--;
                        break;
                    }
                    default:
                        break;
                }
            }
            if (depth != 0 || inRecord || name != null) {
                throw new XMLStreamException("Incomplete XML");
            }
            return new Stats(records, first, last, units);
        } finally {
            reader.close();  // Does not guarantee closing the InputStream.
        }
    }

    static Stats parseString(String xml) throws Exception {
        try (InputStream input = new ByteArrayInputStream(
                xml.getBytes(StandardCharsets.UTF_8))) {
            return parse(input);
        }
    }

    static boolean rejected(String xml) throws Exception {
        try {
            parseString(xml);
            return false;
        } catch (XMLStreamException expected) {
            return true;
        }
    }

    public static void main(String[] args) throws Exception {
        Path path = Files.createTempFile("stax-records-", ".xml");
        try {
            try (BufferedWriter out = Files.newBufferedWriter(path,
                    StandardCharsets.UTF_8)) {
                out.write("<?xml version=\"1.0\" encoding=\"UTF-8\"?><records>");
                for (int i = 1; i <= 10_000; i++) {
                    out.write("<record id=\"" + i + "\"><name>Người "
                            + i + "</name></record>");
                }
                out.write("</records>");
            }

            Stats stats;
            try (InputStream input = Files.newInputStream(path)) {
                stats = parse(input);
            }

            if (stats.records() != 10_000
                    || !"1:Người 1".equals(stats.first())
                    || !"10000:Người 10000".equals(stats.last())) {
                throw new AssertionError("Unexpected stream result: " + stats);
            }
            System.out.println("records=" + stats.records());
            System.out.println("first=" + stats.first());
            System.out.println("last=" + stats.last());
            System.out.println("name-units=" + stats.nameUnits());

            String doctype = "<!DOCTYPE records [<!ENTITY secret "
                    + "SYSTEM 'file:///nonexistent-private-file'>]>"
                    + "<records><record id='1'><name>&secret;</name></record></records>";
            if (!rejected(doctype)) throw new AssertionError("DTD not blocked");
            System.out.println("doctype-blocked=true");

            String hugeName = "<records><record id='2'><name>"
                    + "x".repeat(129) + "</name></record></records>";
            if (!rejected(hugeName)) throw new AssertionError("Field limit failed");
            System.out.println("oversize-name-blocked=true");

            String nested = "<records><record id='1'><name>"
                    + "<deep>x</deep></name></record></records>";
            if (!rejected(nested)) throw new AssertionError("Unexpected element accepted");
            System.out.println("nested-element-blocked=true");
            System.out.println("tests=PASS");
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
~~~

### 8.2. Biên dịch và chạy

Lưu file đúng tên `StaxBoundedReaderDemo.java`, dùng JDK 17+:

~~~bash
javac -encoding UTF-8 --release 17 StaxBoundedReaderDemo.java
java StaxBoundedReaderDemo
~~~

**Stdout chính xác**, đã compile/run trên OpenJDK 24 với `--release 17`:

~~~text
records=10000
first=1:Người 1
last=10000:Người 10000
name-units=98894
doctype-blocked=true
oversize-name-blocked=true
nested-element-blocked=true
tests=PASS
~~~

### 8.3. Giải thích kết quả

- `records=10000`: parser xử lý 10.000 `record` trong một vòng duyệt tuần tự; không tạo DOM hay một list của 10.000 records.
- `first=1:Người 1` và `last=10000:Người 10000`: code chỉ giữ **bản ghi đầu/cuối ở dạng chuỗi ngắn** để minh họa, không giữ cả danh sách.
- `name-units=98894`: tổng **UTF-16 code units** theo Java `String.length()` của các tên; đây không phải tổng bytes UTF-8 hay số grapheme clusters.
- `doctype-blocked=true`: đầu vào có DOCTYPE/external entity bị từ chối trên **JDK provider đã kiểm thử**. Không suy rằng mọi provider khác sẽ phản ứng đúng như vậy nếu chưa test.
- `oversize-name-blocked=true`: tên dài 129 chars vượt `MAX_NAME_UNITS=128` và bị từ chối trước khi append.
- `nested-element-blocked=true`: schema giản lược không cho phép `<deep>` trong `<name>`.
- `tests=PASS`: các assertions hoàn thành và file tạm được dọn trong `finally`.

**Ranh giới kết quả:** code không in mức heap thực. Nó **minh họa thiết kế không giữ toàn bộ object graph**, chứ **không chứng minh một giới hạn byte heap tuyệt đối** cho mọi JVM/parser. Muốn chứng minh memory target, phải benchmark trên workload/provider thật và so sánh GC allocation.

### 8.4. Vì sao code không dùng getElementText?

Để kiểm tra giới hạn **trước khi tích lũy**, code lấy từng fragment qua `getTextLength()` và `getTextCharacters()` rồi append vào `StringBuilder` tối đa 128 UTF-16 units. Với `getElementText()`, toàn bộ element text có thể thành một String trước khi có cơ hội kiểm tra length.

### 8.5. Resource ownership trong ví dụ

`XMLStreamReader.close()` không có nghĩa buộc phải đóng `InputStream` được truyền vào. Ví dụ dùng:

~~~java
try (InputStream input = Files.newInputStream(path)) {
    Stats stats = parse(input);
    // Sử dụng kết quả đã tóm tắt.
}
~~~

Đây là **đoạn trích**, cần `path`, `parse` và `Stats` của ví dụ đầy đủ. `parse` tự `reader.close()`; caller vẫn **đóng source bằng try-with-resources**. Nếu dùng `Reader` thay `InputStream`, cũng phải đóng Reader riêng nếu bạn sở hữu nó.

## 9. Java 17+ runnable: XMLEventReader khi muốn các event objects

Trong chương trình trước, cursor API luôn giữ **một vị trí event hiện tại**. Nếu code cần object event riêng để dispatch sang handler hoặc xem event tiếp theo bằng `peek()`, `XMLEventReader` thường dễ dùng hơn.

Ví dụ `StaxEventReaderDemo.java` vẫn **không dựng DOM** và chỉ giữ một `StringBuilder` trong item hiện tại. Nó dùng XML input nhỏ để quan sát sự khác biệt giữa cursor và event.

### 9.1. File StaxEventReaderDemo.java (độc lập)

~~~java
import java.io.*;
import javax.xml.XMLConstants;
import javax.xml.stream.*;
import javax.xml.stream.events.*;

public final class StaxEventReaderDemo {
    public static void main(String[] args) throws Exception {
        XMLInputFactory factory = XMLInputFactory.newFactory();
        factory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
        factory.setProperty(XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setXMLResolver((publicId, systemId, baseUri, namespace) -> {
            throw new XMLStreamException("External entity denied");
        });

        String xml = "<r><item id='1'>Một</item><item id='2'>Hai</item></r>";
        try (StringReader source = new StringReader(xml)) {
            XMLEventReader events = factory.createXMLEventReader(source);
            try {
                String id = null;
                StringBuilder text = null;
                int count = 0;
                while (events.hasNext()) {
                    XMLEvent event = events.nextEvent();
                    if (event.isStartElement()) {
                        StartElement element = event.asStartElement();
                        if (element.getName().getLocalPart().equals("item")) {
                            Attribute attr = element.getAttributeByName(
                                    new javax.xml.namespace.QName("id"));
                            if (attr == null) throw new XMLStreamException("Missing id");
                            id = attr.getValue();
                            text = new StringBuilder();
                        }
                    } else if (event.isCharacters() && text != null) {
                        Characters characters = event.asCharacters();
                        if (characters.getData().length() > 64 - text.length()) {
                            throw new XMLStreamException("Item too long");
                        }
                        text.append(characters.getData());
                    } else if (event.isEndElement()) {
                        EndElement element = event.asEndElement();
                        if (element.getName().getLocalPart().equals("item")) {
                            if (id == null || text == null) {
                                throw new XMLStreamException("Missing item state");
                            }
                            System.out.println("event-item=" + id + ":" + text);
                            count++;
                            id = null;
                            text = null;
                        }
                    }
                }
                System.out.println("event-count=" + count);
            } finally {
                events.close();  // Close source separately.
            }
        }
    }
}
~~~

### 9.2. Lệnh chạy và stdout

~~~bash
javac -encoding UTF-8 --release 17 StaxEventReaderDemo.java
java StaxEventReaderDemo
~~~

**Stdout chính xác**, đã chạy trên OpenJDK 24 với `--release 17`:

~~~text
event-item=1:Một
event-item=2:Hai
event-count=2
~~~

### 9.3. Cursor hay event nên chọn cách nào?

- Muốn parse nhiều records theo vòng lặp chặt, có ít event object allocations: **bắt đầu với `XMLStreamReader`**, đo thực tế.
- Muốn sử dụng `StartElement`, `Attribute`, `Characters` và chia pipeline theo event types: **`XMLEventReader`**.
- Cả hai đều có thể xử lý tuần tự và không phải lưu toàn bộ document.
- **Không chọn XMLEventReader vì tưởng “events tự lưu hết vào bộ nhớ”**. Mỗi `nextEvent()` đưa event tiếp theo; memory tăng chủ yếu khi code giữ tất cả events trong collection.
- Trong ví dụ event, text được giới hạn 64 code units; với schema phức tạp cần giới hạn depth/record count tương tự ví dụ cursor.

## 10. Đưa StAX vào luồng import file thật

Một chương trình thực tế thường nhận path/upload và cần validate trước khi bắt đầu. Sơ đồ:

~~~text
Untrusted upload/file/network input
             |
             v
Check auth, content length/quota, file access, max bytes
             |
             v
Open InputStream (bounded)
             |
             v
XMLInputFactory configured XXE/DTD security
             |
             v
XMLStreamReader
             |
             +-- read event, validate schema subset
             |
             +-- complete one <record>
             |
             +-- validate fields, types, IDs, business rules
             |
             +-- write to bounded batch/transactional sink
             |
             +-- release record state
             |
             +-- next()
             |
             v
Close parser and InputStream
             |
             v
Finalize transaction/outbox/result/report
~~~

### 10.1. Không cho phép stream vô hạn

Đối với nguồn không tin cậy, chỉ dùng `MAX_RECORDS` vẫn chưa đủ: một single element có comment/PI/whitespace rất lớn cũng có thể làm parser tiêu tốn bytes/time. Cần **max total bytes**, time budget và số lượng events/attributes. Có thể bọc `InputStream` bằng một counting/limiting stream hoặc giới hạn ở ingestion layer, lưu ý khi parser có read-ahead và content encoding.

**Đừng lấy `InputStream.available()` làm tổng độ dài XML**: nó không có nghĩa “số bytes còn lại của toàn nguồn”.

### 10.2. Xử lý record theo batch có giới hạn

Nếu sink là JDBC:

- Tạo `PreparedStatement` và map record hiện tại vào parameters; không tích lũy mọi records.
- Chỉ giữ một **batch nhỏ có giới hạn** nếu `executeBatch` thích hợp, sau đó clear/execute trước khi nhận batch tiếp.
- Dùng đúng transaction boundaries và error policy: file lớn có thể cần checkpoint/idempotency nhưng phải hiểu partial commits.
- Nếu parser lỗi giữa file, đừng báo “import thành công” cho toàn file khi chỉ một phần đã lưu.
- Không đưa DTD/external entity vào truy cập file/network của server.
- Theo dõi lỗi XML với line/column (khi có) và record index để chẩn đoán; không log nội dung nhạy cảm của document.

### 10.3. Transaction và rollback

StAX chỉ parse XML, không quản lý DB transactions. Nếu yêu cầu import **atomic toàn bộ file**, cần transaction DB bao phủ toàn bộ, nhưng một transaction quá dài có thể gây locks/log growth. Nếu cho phép partial progress, cần checkpoint, dedup keys và API báo trạng thái partial chính xác. Quyết định theo business constraints, không phụ thuộc parser.

### 10.4. Stop early và skip

Ưu điểm pull là có thể dừng khi tìm được record theo ID hoặc khi đạt business limit. Tuy nhiên:

- Nếu dừng sớm, không thể nói “toàn bộ XML well-formed” nếu **chưa đọc tới cuối**.
- Nếu bỏ qua phần tử bằng cách chỉ gọi `next()` thì vẫn phải xử lý đúng độ sâu để biết lúc nào ra khỏi subtree.
- Không có truy cập ngẫu nhiên (random-access) chỉ vì parser có `peek()`; `peek()` thuộc event reader và chỉ quan sát event kế tiếp theo contract.

## 11. Các lỗi StAX dễ mắc

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Dùng DOM cho XML rất lớn dù chỉ xử lý tuần tự | Giữ nguyên cây object graph | Xem StAX/SAX và streaming pipeline |
| Dùng StAX nhưng `List.add(record)` cho mọi record | Application vẫn giữ mọi objects | Xử lý ngay, bounded batch/queue |
| Gọi `getElementText()` trên payload không giới hạn | Materialize một String lớn | Đọc text fragments và giới hạn |
| Giả định một element text = một `CHARACTERS` | Parser có thể chia chunks | Append/stream fragments đúng thứ tự |
| Gọi `getText()` tại START_ELEMENT | Sai event state | Kiểm tra `XMLStreamConstants` trước |
| So tên bằng prefix thay vì namespace URI | Prefix là alias không ổn định | URI + localName/QName |
| Tắt namespace processing chỉ để né check | Dễ sai schema | Namespace-aware true và validate rõ |
| Không disable DTD/external entities | XXE/SSRF/local file exposure | Set security properties trước parse |
| Catch `IllegalArgumentException` khi set security rồi bỏ qua | Parser có thể vẫn không an toàn | Fail closed/chọn provider tested |
| Chỉ tắt DTD nhưng cho phép file vô hạn | Có thể DoS bằng size/depth/CPU | Giới hạn input bytes/events/fields |
| Đặt `IS_COALESCING=true` và tin không buffer | Parser có thể gộp text rất lớn | Benchmark, hạn chế long field |
| `XMLStreamReader.close()` nhưng không đóng InputStream | Source có thể vẫn mở | try-with-resources riêng cho source |
| Không close khi parse exception | Leak file/network resource | `finally` cho parser, try-with source |
| Trả XMLStreamReader ra khỏi scope InputStream | Parser phụ thuộc nguồn đã đóng | Xử lý trong cùng lifecycle |
| So output theo exact whitespace dù input thay đổi | Whitespace/CDATA/normalization có thể khác | Xác định normalization contract |
| Tin `XMLInputFactory.newFactory` luôn chọn JDK provider | Classpath có provider khác | Test thực provider/version |
| Chạy một test nhỏ rồi tuyên bố heap cố định | Chưa có benchmark lớn | Đo heap/GC/throughput với workload |
| Không validate record schema | XML well-formed chưa chắc đúng nghiệp vụ | Validate tags/attrs/types/ordering |
| Stop parser sau record đầu nhưng báo toàn file hợp lệ | Chưa parse phần còn lại | Nếu cần validity, đọc tới END_DOCUMENT |

## 12. Kiểm thử đúng cho nhu cầu bộ nhớ giới hạn

Hai chương trình ở trên đã chứng minh **logic ứng dụng và cách dùng API**, chưa đo heap allocation thực tế. Để ra quyết định production:

| Test | Mục tiêu |
| --- | --- |
| File nhỏ đúng schema | Parser trả đúng count/fields |
| 10.000/100.000 records | Xác nhận không build toàn bộ object graph |
| Text split thành nhiều CHARACTERS | Ghép đúng từng fragment |
| CDATA trong name | Không bỏ sót text |
| Empty elements | Không đọc sai state |
| Namespace URI khác/prefix khác | So QName đúng schema |
| DTD/external entity | Không đọc file/network ngoài ý muốn |
| Invalid XML | Ném XMLStreamException với vị trí phù hợp |
| Deep nesting | Bị từ chối khi quá MAX_DEPTH |
| Oversize field | Không append vượt max |
| Too many records | Dừng theo MAX_RECORDS |
| Too many bytes/events/attributes | Có quota thực |
| Unicode và emoji | Không mất ký tự |
| Slow downstream | Bounded queue không phình heap |
| Partial DB failure | Transaction/checkpoint/idempotency đúng |
| File close | Không rò file handles/stream |
| Provider swap | Security config và parsing vẫn đúng |
| DOM vs StAX vs SAX | Benchmark end-to-end với cùng workload |

### 12.1. Đo benchmark như thế nào?

- Dùng **cùng file**, encoding, schema, validation và output semantics.
- Warm up JVM/parser, đo nhiều lần để tránh JIT và filesystem cache làm lệch.
- Đo **peak heap, allocations/op, GC pause, native/temp memory, throughput records/sec**, không chỉ wall-clock.
- So sánh cả **parser + business processing + sink**, không đo riêng XML reader nếu bottleneck là DB.
- Đo cấu hình `IS_COALESCING`, kích thước input buffer và batch size.
- Test provider thực tế, JDK version thật và giới hạn memory container thật.
- Không đưa cả XML input vào `String` trước khi benchmark streaming, vì sẽ che mất lợi ích source streaming.

### 12.2. Bản chất “bộ nhớ giới hạn”

Khi chỉ lưu một record tối đa R, depth tối đa D và batch tối đa B, application state về cơ bản bị chặn bởi R/D/B; nhưng parser nội bộ và nguồn `InputStream` có thể buffer, XML entity/DTD có thể nở dữ liệu, và downstream có thể giữ thêm. Vì vậy dùng **bảo vệ ở nhiều tầng** và đo thực tế mới có SLA đáng tin.

## 13. Câu hỏi tự đánh giá

**1.** StAX là push hay pull parser?

**Đáp án:** Pull: application chủ động gọi `next()/nextEvent()` để lấy event kế tiếp.

**2.** Khi XML rất lớn và chỉ cần đọc record từ đầu đến cuối, DOM hay StAX thường hợp lý hơn?

**Đáp án:** StAX (hoặc SAX) thường phù hợp hơn nếu ứng dụng không tích lũy toàn bộ records; vẫn cần benchmark và giới hạn state.

**3.** `XMLStreamReader` và `XMLEventReader` khác gì?

**Đáp án:** Cursor API cho phép đọc trạng thái event hiện tại với getters, thường ít event objects; event API trả `XMLEvent` objects thuận tiện cho processing và `peek()`.

**4.** Có thể giả định một element text luôn là một `CHARACTERS` event?

**Đáp án:** Không. Parser có thể chia text chunks; cần ghép có giới hạn hoặc xử lý incrementally.

**5.** Vì sao `getElementText()` có thể gây OOM?

**Đáp án:** Nó trả toàn bộ element text thành String; nếu element rất lớn, code có thể materialize dữ liệu quá giới hạn.

**6.** `IS_COALESCING=true` có luôn tốt hơn không?

**Đáp án:** Không. Nó gộp text events, dễ code hơn nhưng có thể tăng buffering cho text dài. Chọn và đo theo workload.

**7.** `reader.close()` có chắc đóng `InputStream` ban đầu không?

**Đáp án:** Không được giả định. Application sở hữu InputStream phải đóng riêng bằng try-with-resources.

**8.** Tại sao so XML namespace URI quan trọng hơn prefix?

**Đáp án:** Prefix có thể đổi nhưng expanded name `{URI}localName` vẫn cùng ý nghĩa.

**9.** Chỉ đặt `SUPPORT_DTD=false` rồi cho XML không giới hạn kích thước có an toàn không?

**Đáp án:** Không. Cần hạn chế external access, bytes, depth, fields, events và compute time.

**10.** Nếu provider ném `IllegalArgumentException` khi đặt security property bắt buộc?

**Đáp án:** Fail-closed hoặc chọn provider đã kiểm chứng. Không tiếp tục parse untrusted XML với cấu hình yếu.

**11.** Vì sao mẫu `StaxBoundedReaderDemo` có `MAX_NAME_UNITS`?

**Đáp án:** Để chặn text field từ nguồn untrusted trước khi `StringBuilder` vượt giới hạn; không dùng getElementText cho field không giới hạn.

**12.** Parser xử lý xong record đầu có thể khẳng định cả XML well-formed không?

**Đáp án:** Không. Muốn kiểm tra toàn file phải parse tới cuối, trừ khi contract chấp nhận stop early mà không chứng nhận toàn bộ.

**13.** `records=10000` và `name-units=98894` có chứng minh heap tối đa cố định?

**Đáp án:** Không. Chúng xác nhận dữ liệu/logic fixture; memory phải được đo riêng.

**14.** Vì sao dùng StAX để import DB vẫn cần transaction/idempotency?

**Đáp án:** Parser chỉ chuyển XML thành events; không quyết định hiệu ứng của DB transaction, partial failure, retry hay duplicate records.

### Bài tập thực hành

1. Chạy `StaxBoundedReaderDemo`, đổi số records thành 15.000 và kiểm tra thống kê.
2. Đổi thành 20.001 records, xác nhận `MAX_RECORDS` chặn input.
3. Tạo tên dài 129 chars và giải thích vì sao bị từ chối **trước append**.
4. Bổ sung kiểm tra `id` chỉ được chứa số, có tối đa 20 digits và không bị tràn `long`.
5. Tạo XML có namespaces và sửa parser so URI + localName thay vì từ chối mọi namespace.
6. Thử CDATA: `<name>Xin <![CDATA[chào]]></name>`, xác nhận các fragments được ghép đúng.
7. Tạo file có whitespace nhiều nơi; làm rõ có nên giữ/trim text theo business contract.
8. Bổ sung giới hạn total bytes bằng counting InputStream cho input không biết độ dài.
9. Viết output sink nhận từng record ngay lập tức, không tạo List của toàn file.
10. Benchmark heap/GC bằng 10K, 100K và 1M records với StAX, SAX và DOM (có giới hạn an toàn).
11. Test provider khác JDK mặc định nếu ứng dụng dùng library bên thứ ba, xác minh các XXE controls.
12. Thay `XMLStreamReader` bằng `XMLEventReader` và so cách đọc attribute/text.
13. Tạo XML sai closing tag và xác nhận `XMLStreamException.getLocation()` nếu parser cung cấp.
14. Thiết kế importer hỗ trợ checkpoint và idempotency khi DB commit từng batch.

## 14. Tài liệu chính thức còn áp dụng

- [Oracle Java SE 26 — XMLInputFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLInputFactory.html): properties, `newFactory`, tạo stream/event readers, DTD và external DTD access.
- [Oracle Java SE 26 — XMLStreamReader](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLStreamReader.html): forward-only pull cursor, event states, text fragments, `getElementText`, `close`.
- [Oracle Java SE 26 — XMLEventReader](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLEventReader.html): event pull reader, `nextEvent`, `peek`, `close`.
- [Oracle Java SE 26 — XMLStreamConstants](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLStreamConstants.html): `START_ELEMENT`, `CHARACTERS`, `END_ELEMENT`, `DTD` và các event types.
- [Oracle Java SE 26 — XMLStreamException](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLStreamException.html): parse exceptions và `getLocation`.
- [Oracle Java SE 26 — XMLEvent](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/events/XMLEvent.html): event objects.
- [Oracle Java SE 26 — StartElement](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/events/StartElement.html): QName và attributes.
- [Oracle Java SE 26 — Characters](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/events/Characters.html): character events.
- [Oracle Java SE 26 — QName](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/namespace/QName.html): namespace URI + local part.
- [Oracle Java SE 26 — XMLConstants](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/XMLConstants.html): `ACCESS_EXTERNAL_DTD`/external access semantics.
- [Oracle Java SE 26 — java.xml module](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/module-summary.html): JAXP/StAX/XML security.
- [Oracle Java SE 26 — XMLOutputFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLOutputFactory.html): tạo streaming XML writer khi cần output mới.
- [Oracle Java SE 17 — XMLInputFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/stream/XMLInputFactory.html): tham chiếu đúng cho `javac --release 17`.
- [Oracle Java Tutorials — Using StAX](https://docs.oracle.com/javase/tutorial/jaxp/stax/using.html): giới thiệu cursor/event processing (tài liệu hướng dẫn cũ; đối chiếu Javadoc Java26 để dùng API hiện hành).
- [OWASP — XML External Entity Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html): khuyến nghị chặn DTD/external entities ở StAX, secure XML parsing.

**Ghi nhớ:** Khi XML lớn và bài toán chỉ cần **đọc tuần tự**, StAX là lựa chọn hợp lý vì application có thể **điều khiển event tiếp theo và xử lý xong từng record rồi bỏ trạng thái cũ**. Nhưng memory vẫn phụ thuộc parser, text fragments, độ sâu XML, cách gom records và downstream; hãy **giới hạn input và state, khóa DTD/XXE, đóng reader lẫn source, đo trên workload thật**. Không dùng `getElementText()`/`List` không giới hạn rồi tuyên bố đang streaming tiết kiệm bộ nhớ.
