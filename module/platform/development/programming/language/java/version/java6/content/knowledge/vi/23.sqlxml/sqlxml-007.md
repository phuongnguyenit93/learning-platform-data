# Kết hợp SQLXML với StAX để xử lý dữ liệu lớn trong JDBC (Java 17+)

## 1. Vấn đề: XML lớn nằm trong một cột của cơ sở dữ liệu

Một ứng dụng Java có thể nhận hàng chục nghìn bản ghi trong một tài liệu XML được lưu dưới **cột SQL XML**: lô đơn hàng, chứng từ tích hợp, nhật ký xuất dữ liệu, tập tài liệu nhiều ngôn ngữ hoặc thông điệp trao đổi giữa các hệ thống. Nếu tải toàn bộ tài liệu bằng `SQLXML.getString()` rồi dựng `Document` (DOM), phía ứng dụng phải giữ một chuỗi lớn và thường cả cây XML trong heap. Khi nhiều request xử lý đồng thời, cách đó có thể tạo áp lực bộ nhớ và GC đáng kể.

**JDBC `SQLXML` + StAX** giải quyết một phần bài toán bằng cách:
1. Lấy nội dung XML từ database qua `ResultSet.getSQLXML(...)`.
2. Chọn duy nhất **`SQLXML.getCharacterStream()`** để lấy một `java.io.Reader`.
3. Tạo một **`XMLStreamReader`** của StAX (Streaming API for XML) từ Reader.
4. Duyệt tuần tự từng sự kiện XML và xử lý bản ghi bằng trạng thái nhỏ, không dựng toàn bộ DOM trong application.
5. Đóng `XMLStreamReader`, `Reader`, gọi `SQLXML.free()` và kết thúc `ResultSet`/transaction đúng thứ tự.

Minh họa:

```text
Database: cột SQL XML có tài liệu lớn
                   |
          JDBC ResultSet.getSQLXML(...)
                   |
          SQLXML.getCharacterStream()  [chỉ một getter/instance]
                   |
            java.io.Reader
                   |
        XMLInputFactory (đã harden)
                   |
             XMLStreamReader
                   |
  START_ELEMENT / CHARACTERS / END_ELEMENT
                   |
   Đếm/tổng hợp/gửi từng record vào bộ xử lý
                   |
 Close parser -> Close Reader -> SQLXML.free()
                   |
        Close ResultSet / Statement
                   |
             Commit / Close
```

Bài này tập trung vào **cách ghép hai API, quản lý tài nguyên và XML security**, không chỉ dừng ở các method riêng lẻ. Dùng Java 17+ và các API còn được hỗ trợ hiện nay. Đặc biệt:
- Không mặc định mọi JDBC driver có native XML type hoặc hỗ trợ `SQLXML`.
- Không khẳng định gọi “streaming” đồng nghĩa O(1) memory ở driver/server.
- Không cho StAX parse external DTD/entities theo cấu hình mặc định khi XML không đáng tin.
- Không đánh đồng số byte UTF-8, code points Unicode và `char` UTF-16 của Java.

## 2. Ba tầng cần phân biệt

| Tầng | API | Trách nhiệm | Giới hạn |
| --- | --- | --- | --- |
| SQL/JDBC | `Types.SQLXML`, `SQLXML`, `Connection.createSQLXML`, `ResultSet.getSQLXML` | Ánh xạ dữ liệu kiểu SQL XML và quản lý vòng đời connection/transaction. | Tùy driver, schema, DBMS; JDBC không định nghĩa parser XML an toàn cho ứng dụng. |
| Java I/O | `Reader` / `Writer`, `InputStream` / `OutputStream` | Chuyển dữ liệu ký tự hoặc byte giữa nguồn và đích. | Reader là ký tự Java, không phải bytes UTF-8; streams có thể phụ thuộc driver. |
| StAX/JAXP | `XMLInputFactory`, `XMLStreamReader`, `XMLOutputFactory`, `XMLStreamWriter` | Pull parsing và streaming generation theo XML events. | Không tự validate XSD, không tự bảo đảm chống XXE hay giới hạn kích thước. |

**StAX là streaming parser, SQLXML là JDBC value mapping**. Chúng không thay thế nhau. Một XML file trên đĩa cũng có thể được xử lý bởi StAX mà không qua JDBC; còn JDBC có thể đọc XML bằng `getString()` hoặc `getSource(...)` không dùng StAX. Tác dụng của việc kết hợp là **đọc XML database qua Reader** với **phân tích incremental** trong ứng dụng.

Với Java 17+, các module chuẩn liên quan là:
- `java.sql` cho JDBC `SQLXML`, `Connection`, `PreparedStatement`, `ResultSet`.
- `java.xml` cho `javax.xml.stream` (StAX), `javax.xml.XMLConstants` và JAXP.
- `java.base` cho `Reader`, `Files`, `Path`, `StandardCharsets`.

Không cần thư viện StAX legacy ngoài JDK chỉ để dùng `XMLInputFactory`. Nếu dùng một parser provider bên thứ ba để có tính năng/performance riêng, phải kiểm tra security properties mà provider đó thực sự chấp nhận.

## 3. SQLXML: lấy dữ liệu từ SQL và đọc đúng một lần

JDBC SQLXML đại diện một giá trị SQL `XML`. Thông thường:

```java
SQLXML sqlxml = resultSet.getSQLXML("payload");

if (sqlxml != null) {
    try {
        try (Reader reader = sqlxml.getCharacterStream()) {
            // Đưa reader vào parser StAX đã cấu hình an toàn.
        }
    } finally {
        sqlxml.free();
    }
}
```

Đây là **snippet**, không phải chương trình độc lập: `resultSet` đang trỏ đến một row, `payload` phải là cột XML mà driver hỗ trợ, cần imports `java.sql.SQLXML` và `java.io.Reader`.

### 3.1. Một getter trên mỗi instance

Javadoc `SQLXML` quy định nội dung **có thể đọc hoặc ghi tối đa một lần trên cùng đối tượng**. Khi gọi một trong `getString()`, `getCharacterStream()`, `getBinaryStream()` hoặc `getSource(...)`, instance chuyển từ *readable* sang *not readable*. Nếu cần xử lý XML lớn bằng StAX, hãy chọn `getCharacterStream()` **một lần**:

```java
// Sai: getter thứ hai trên cùng SQLXML có thể ném SQLException.
SQLXML value = rs.getSQLXML("payload");
String asText = value.getString();
Reader again = value.getCharacterStream();
```

Đây là **mã sai có chủ ý** dùng để giải thích lifecycle, không nên chạy trong ứng dụng. Nếu business logic cần nhiều kết quả, hãy **tổng hợp mọi thông tin cần thiết trong một lượt StAX parse**, hoặc truy vấn lại theo contract driver và transaction. Đừng gọi nhiều getters liên tiếp trên cùng SQLXML.

### 3.2. Transaction và free()

`SQLXML` hợp lệ trong **transaction nơi nó được tạo**. Giữ `ResultSet`/`Connection` mở khi đang parse; sau khi kết thúc, đóng XML parser, đóng Reader, gọi `sqlxml.free()` rồi mới di chuyển cursor/đóng ResultSet hoặc commit/rollback.

`SQLXML` **không implements `AutoCloseable`** nên không dùng được `try (SQLXML value = ...)`. Gọi `free()` trong `finally`. `free()` làm SQLXML không thể đọc/ghi tiếp và có thể ném `SQLException`. Trong production, nếu parser đã ném lỗi, cân nhắc lưu lỗi cleanup dưới dạng suppressed exception để không che mất nguyên nhân gốc.

### 3.3. SQL NULL, không có row, XML rỗng

Ba trạng thái khác nhau:
- `rs.next() == false`: truy vấn **không có row**.
- `rs.getSQLXML("payload") == null`: row có cột SQL **NULL**.
- `rs.getSQLXML("payload") != null` và XML như `<orders/>`: **XML hợp lệ không có phần tử đơn hàng**.

Không coi SQL NULL là một XML document rỗng; không dựng Reader rỗng rồi parse và mong StAX tự coi đó là `<orders/>`. Chuỗi `""` thường không phải một XML document well-formed.

### 3.4. Cột SQL XML không portable trên mọi DBMS

`Types.SQLXML` là JDBC type code; SQL DDL như:

```sql
CREATE TABLE xml_documents (
    id BIGINT PRIMARY KEY,
    payload XML
);
```

là **minh họa**, không phải SQL có thể chạy trên mọi hệ quản trị. Kiểu XML, mapping, performance, SQL CAST và hỗ trợ `createSQLXML`/`getSQLXML`/`setSQLXML` thay đổi theo PostgreSQL, SQL Server, Oracle và các hệ khác. Một số hệ dùng `VARCHAR/CLOB` để lưu XML text; với schema đó có thể phù hợp `getCharacterStream` thông thường hơn là `getSQLXML`. Phải dựa trên vendor docs và integration tests.

Để khảo sát mapping:

```java
ResultSetMetaData meta = rs.getMetaData();
int jdbcTypeCode = meta.getColumnType(1);
String databaseTypeName = meta.getColumnTypeName(1);
boolean xmlType = jdbcTypeCode == java.sql.Types.SQLXML;
```

Đây là **snippet**, cần import `java.sql.ResultSetMetaData` và có `ResultSet rs`. Metadata chỉ là tín hiệu; muốn tin rằng getter SQLXML hoạt động, hãy thử trên driver/version thực.

## 4. StAX: duyệt pull events thay vì DOM

Java StAX có hai phong cách chính:

| API | Tên | Đặc điểm |
| --- | --- | --- |
| Cursor | `XMLStreamReader` | Gọi `next()`, đọc event type và properties của event hiện tại, ít object wrappers. |
| Iterator | `XMLEventReader` | Gọi `nextEvent()` để nhận các object `XMLEvent`; có thể thuận tiện cho filters/pipelines. |
| Writer cursor | `XMLStreamWriter` | Tạo XML bằng các lời gọi `writeStartElement`, `writeAttribute`, `writeCharacters`… |
| Writer event | `XMLEventWriter` | Ghi các `XMLEvent`, phù hợp pipeline event-based. |

**`XMLStreamReader`** thường là lựa chọn trực tiếp khi chỉ cần quét một tài liệu XML lớn và tính thống kê/xử lý từng phần tử. Nó không tự dựng DOM tree; trạng thái ứng dụng có thể chỉ gồm bộ đếm, độ sâu, thuộc tính của phần tử hiện tại và một bộ nhớ giới hạn.

Những event được dùng nhiều:

| `XMLStreamConstants` | Ý nghĩa | Cách dùng |
| --- | --- | --- |
| `START_DOCUMENT` | Bắt đầu XML document. | Đọc metadata XML nếu cần. |
| `START_ELEMENT` | Bắt đầu một phần tử. | Kiểm tra `getLocalName()`, `getNamespaceURI()`, đọc attributes. |
| `CHARACTERS` | Nội dung text. | Xử lý `getTextCharacters()`, `getTextStart()`, `getTextLength()` hoặc `getText()` khi text nhỏ. |
| `CDATA` | Nội dung CDATA; tùy parser configuration có thể biểu diễn text qua event khác. | Xử lý như text theo contract. |
| `END_ELEMENT` | Kết thúc phần tử. | Kết thúc record, reset trạng thái/bộ đệm. |
| `DTD` | Khai báo DTD. | Từ chối theo security policy khi không cần DTD. |
| `END_DOCUMENT` | Kết thúc XML document. | Hoàn tất pipeline. |

**Không coi mỗi cặp `START_ELEMENT`/`END_ELEMENT` là luôn có đúng một `CHARACTERS` event.** Parser được phép chia text thành nhiều chunks; CDATA, entity references và whitespace còn làm event sequence khác đi. Nếu cần nội dung phần tử đầy đủ, phải xử lý nhiều sự kiện, hoặc `getElementText()` khi biết chắc element nhỏ và chỉ chứa text.

### 4.1. Khi nào không nên dùng getElementText()?

`XMLStreamReader.getElementText()` tiện với field nhỏ như `<customerId>42</customerId>` vì nó thu thập nội dung text của phần tử. Nhưng nếu element là `<body>...hàng trăm MB...</body>`, việc gom text vào `String` sẽ đi ngược mục tiêu streaming. Với field lớn, xử lý `CHARACTERS` theo từng chunk, ghi thẳng vào `Writer` hoặc trình tiêu thụ khác, áp dụng giới hạn dữ liệu.

`getText()` cũng tạo/trao chuỗi của event hiện tại; với payload lớn và lượng sự kiện nhiều, `getTextCharacters()` hoặc `getTextLength()` thường giúp giảm cấp phát. **Mảng ký tự trả từ `getTextCharacters()` có vòng đời gắn với event hiện tại**: xử lý/copy trước khi gọi `next()`; không lưu reference mảng nội bộ để xử lý bất đồng bộ sau.

### 4.2. Namespace và các thuộc tính

Khi XML có:

```xml
<o:order xmlns:o="urn:example:orders" id="7" amount="42">
  Đơn hàng thử
</o:order>
```

`getLocalName()` trả `order`, và `getNamespaceURI()` trả `urn:example:orders`. Một parser đúng nên kiểm tra **cặp namespace URI và local name** nếu tài liệu có nhiều namespace cùng tên element. `getAttributeValue(null, "amount")` truy cập attribute **không namespace**; attributes có prefix/namespace phải truyền đúng URI.

Không dựa vào namespace prefix `o` như định danh bất biến: prefix là cú pháp, URI mới xác định tên mở rộng. Với XML không đáng tin, kiểm tra depth, root name/namespace và các attributes bắt buộc trước khi dùng chúng.

## 5. Cấu hình XMLInputFactory an toàn chống XXE

**XML từ DB vẫn có thể không đáng tin.** Một row XML có thể bắt nguồn từ upload, import đối tác hoặc dữ liệu ứng dụng cũ. Nếu StAX tự tải external DTD/entities, parser có thể đọc local file, truy cập network (SSRF) hoặc bị lạm dụng tài nguyên.

Tạo factory riêng cho trường hợp XML không tin cậy:

```java
XMLInputFactory factory = XMLInputFactory.newDefaultFactory();
factory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
factory.setProperty(
        XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
factory.setXMLResolver((publicId, systemId, baseURI, namespace) -> {
    throw new XMLStreamException("External resource blocked");
});
```

Đây là **snippet trong method**, cần imports `javax.xml.stream.XMLInputFactory`, `javax.xml.stream.XMLStreamException` và `javax.xml.XMLConstants`.

Từng lớp phòng vệ:
1. `SUPPORT_DTD=false` yêu cầu không xử lý DTD.
2. `IS_SUPPORTING_EXTERNAL_ENTITIES=false` không resolve các external parsed entities.
3. `ACCESS_EXTERNAL_DTD=""` từ chối protocol truy cập external DTD/entities; JAXP 1.5+ có contract hỗ trợ cho thuộc tính này.
4. `setXMLResolver` cài resolver **fail closed** nếu parser vẫn cố tra resource ngoài.
5. Trong vòng `next()`, ứng dụng còn có thể **từ chối sự kiện `DTD`** nếu gặp.

**Lưu ý quan trọng:** đặt `SUPPORT_DTD=false` **không bắt buộc mọi StAX implementation phải ném lỗi ngay khi thấy `<!DOCTYPE ...>`**; có parser bỏ qua DTD và tiếp tục. Nếu business policy yêu cầu *không chấp nhận DOCTYPE*, phải kiểm tra thêm hoặc dùng cơ chế reject DTD phù hợp parser. Trong demo, ngoài cấu hình parser còn có nhánh chủ động ném `XMLStreamException` khi nhận event `DTD`. Trong một số implementation, XML khai báo entity bị lỗi từ trước; cả hai đều là kết quả **từ chối XML không được phép**.

**StAX không có `XMLConstants.FEATURE_SECURE_PROCESSING` tương đương DOM/SAX theo cùng cách cấu hình.** Đừng copy `DocumentBuilderFactory` settings một cách máy móc. Thay vào đó dùng các StAX properties nói trên, hạn chế tài nguyên và policy của runtime/provider. Nếu một bảo vệ bắt buộc không được parser hỗ trợ và `setProperty` ném `IllegalArgumentException`, hãy **dừng xử lý XML không tin cậy**, không lặng lẽ tiếp tục với parser yếu hơn.

### 5.1. Vì sao newDefaultFactory()?

`XMLInputFactory.newDefaultFactory()` có trên Java 17+; nó chọn default implementation của platform JDK thay vì tìm ngẫu nhiên qua provider discovery. Nếu bạn dùng `newFactory()` hoặc một StAX provider third-party, hãy test security properties và limits của chính provider được chọn. Trên Java 17+ không cần mang một StAX parser legacy không cần thiết vào project chỉ để có cursor parsing.

### 5.2. Giới hạn độ sâu, số records, text và thời gian

Không có thiết lập StAX đơn giản duy nhất bảo đảm chặn mọi XML bomb/depth/memory attack. Production cần nhiều lớp:
- Giới hạn **số bytes XML** được nạp/stream từ database hoặc tầng chuyển tiếp.
- Giới hạn **số phần tử**, độ sâu lồng nhau, số attributes và độ dài giá trị field.
- Giới hạn **số ký tự** đã xử lý/ghi; dừng khi vượt ngân sách.
- Thời gian xử lý/query timeout, cancellation và giới hạn số concurrent parsers.
- Các limits JAXP/JDK phù hợp; kiểm thử trên provider cụ thể.
- Khi parse XML không tin cậy, không đưa parser tới URL system ID do user cung cấp nếu không có allowlist/authorization.

Mã demo đặt giới hạn **10.000 records** để minh họa một chặn số phần tử. Đó **không phải** giới hạn hoàn chỉnh chống DoS cho mọi XML; trong production cần thêm giới hạn trước/trong parse, đặc biệt với một element text cực lớn hoặc hàng triệu attributes.

## 6. Demo Java 17+ đầy đủ: phát sinh và đọc 10.000 XML records

Demo không cần database, không cần JAR ngoài. Nó minh họa **phần StAX sẽ dùng lại khi ghép với `SQLXML.getCharacterStream()`**:
- Sinh 10.000 `<order>` vào một **file tạm UTF-8** thông qua `XMLStreamWriter` (không build một `String` XML rất lớn).
- Đọc file bằng `Files.newBufferedReader(..., UTF_8)`.
- Tạo `XMLStreamReader` hardened, duyệt từng event, lấy `amount` của mỗi order.
- Tính số record, tổng amount và tổng độ dài text theo Java `char` units.
- Kiểm thử XML độc hại có `DOCTYPE`/external entity và xác nhận bị từ chối.
- Xóa file tạm trong `finally`.

Đây là **bài thử parse XML theo luồng**, không phải chứng nhận driver JDBC nào đó stream dữ liệu không buffer.

### 6.1. File StaxStreamingDemo.java

```java
import java.io.OutputStream;
import java.io.Reader;
import java.io.StringReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import javax.xml.XMLConstants;
import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLOutputFactory;
import javax.xml.stream.XMLStreamConstants;
import javax.xml.stream.XMLStreamException;
import javax.xml.stream.XMLStreamReader;
import javax.xml.stream.XMLStreamWriter;

public final class StaxStreamingDemo {

    static record Stats(
            long records, long amountSum, long textUnits) {
    }

    static Stats parse(Reader source) throws XMLStreamException {
        XMLInputFactory factory = XMLInputFactory.newDefaultFactory();
        factory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
        factory.setProperty(
                XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setXMLResolver(
                (publicId, systemId, baseURI, namespace) -> {
                    throw new XMLStreamException(
                            "External resource blocked");
                });

        XMLStreamReader xml = factory.createXMLStreamReader(source);
        long records = 0;
        long amountSum = 0;
        long textUnits = 0;
        boolean insideRecord = false;

        try {
            while (xml.hasNext()) {
                int event = xml.next();

                if (event == XMLStreamConstants.DTD) {
                    throw new XMLStreamException("DOCTYPE not allowed");
                }

                if (event == XMLStreamConstants.START_ELEMENT
                        && xml.getLocalName().equals("order")) {
                    insideRecord = true;
                    records++;

                    if (records > 10000) {
                        throw new XMLStreamException("Too many orders");
                    }

                    amountSum += Long.parseLong(
                            xml.getAttributeValue(null, "amount"));

                } else if (insideRecord && (
                        event == XMLStreamConstants.CHARACTERS
                        || event == XMLStreamConstants.CDATA)) {
                    textUnits += xml.getTextLength();

                } else if (event == XMLStreamConstants.END_ELEMENT
                        && xml.getLocalName().equals("order")) {
                    insideRecord = false;
                }
            }
        } finally {
            xml.close();
        }

        return new Stats(records, amountSum, textUnits);
    }

    static void generate(Path file) throws Exception {
        XMLOutputFactory factory =
                XMLOutputFactory.newDefaultFactory();

        try (OutputStream bytes = Files.newOutputStream(file)) {
            XMLStreamWriter xml =
                    factory.createXMLStreamWriter(bytes, "UTF-8");

            try {
                xml.writeStartDocument("UTF-8", "1.0");
                xml.writeStartElement("orders");

                for (int i = 1; i <= 10000; i++) {
                    xml.writeStartElement("order");
                    xml.writeAttribute("id", Integer.toString(i));
                    xml.writeAttribute("amount",
                            Integer.toString(i % 7));
                    xml.writeCharacters("Đơn hàng " + i + " 🌏");
                    xml.writeEndElement();
                }

                xml.writeEndElement();
                xml.writeEndDocument();
                xml.flush();
            } finally {
                xml.close();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile(
                "xml-orders-", ".xml");

        Stats result;
        boolean dtdBlocked = false;
        boolean deleted;

        try {
            generate(file);

            try (Reader input = Files.newBufferedReader(
                    file, StandardCharsets.UTF_8)) {
                result = parse(input);
            }

            String hostile =
                    "<!DOCTYPE orders [<!ENTITY x "
                    + "SYSTEM 'file:///etc/passwd'>]>"
                    + "<orders>&x;</orders>";

            try (Reader input = new StringReader(hostile)) {
                try {
                    parse(input);
                } catch (XMLStreamException expected) {
                    dtdBlocked = true;
                }
            }

        } finally {
            deleted = Files.deleteIfExists(file);
        }

        System.out.println("records=" + result.records());
        System.out.println("amountSum=" + result.amountSum());
        System.out.println("textUnits=" + result.textUnits());
        System.out.println("doctypeRejected=" + dtdBlocked);
        System.out.println("temporaryFileDeleted=" + deleted);
    }
}
```

### 6.2. Chạy bằng JDK 17+

Tạo file UTF-8 và chạy:

```bash
javac -encoding UTF-8 StaxStreamingDemo.java
java StaxStreamingDemo
```

**Stdout chính xác đã biên dịch và chạy kiểm chứng:**

```text
records=10000
amountSum=29998
textUnits=158894
doctypeRejected=true
temporaryFileDeleted=true
```

**Đọc kết quả:**
- `records=10000`: đúng 10.000 phần tử `<order>` do writer phát sinh.
- `amountSum=29998`: tổng `i % 7` với `i` từ 1 đến 10.000.
- `textUnits=158894`: tổng số Java `char` units trong text của các order; có emoji ngoài BMP nên không bằng số Unicode code points hay UTF-8 bytes.
- `doctypeRejected=true`: parser không chấp nhận input có DOCTYPE và external entity. Chương trình **không đọc file hệ thống** được nêu trong chuỗi XML thử nghiệm.
- `temporaryFileDeleted=true`: file tạm được xóa thành công ở cuối chương trình.

### 6.3. Vì sao bản demo không dùng getElementText()?

Mỗi order có text `Đơn hàng N 🌏`. Ví dụ **không** dùng `getElementText()`; nó chỉ cộng `xml.getTextLength()` từ các event `CHARACTERS`/`CDATA` khi `insideRecord` là true, do đó không tích lũy một `String` text lớn cho tất cả records. `getTextLength()` đếm độ dài ký tự trong event (đơn vị `char`), không phải byte. Đây là kỹ thuật tốt khi chỉ cần thống kê; nếu cần lưu nội dung từng record, có thể ghi trực tiếp event text vào một sink giới hạn.

**Giới hạn của demo:** nó chỉ nhận diện local name `order` và chưa validate root/namespace/schema hay cấu trúc nested phức tạp. `Long.parseLong` có thể ném `NumberFormatException` nếu attribute amount không phải số. Trong production, kiểm tra cả namespace, root/depth, attribute presence/size, loại dữ liệu, giá trị âm/dương, overflow và contract XML của nhà cung cấp. Giới hạn 10.000 records là ví dụ học tập; không coi là giải pháp chống DoS toàn diện.

### 6.4. Tại sao dùng XMLStreamWriter để sinh dữ liệu?

`XMLOutputFactory` + `XMLStreamWriter` ghi sự kiện XML trực tiếp xuống `OutputStream`. Nó tự escape nội dung khi cần theo XML syntax (ví dụ với `writeCharacters`), giúp tránh tạo chuỗi XML khổng lồ bằng nối `String`. Khi kết thúc, gọi `writeEndDocument`, `flush`, `close` rồi đóng `OutputStream` bên ngoài; không coi `XMLStreamWriter.close()` là cam kết đóng stream nguồn/đích.

Nếu dữ liệu có cấu trúc từ ứng dụng, dùng StAX writer phù hợp hơn việc tự nối `"<order>" + userText + "</order>"`: phép nối thiếu escaping có thể tạo XML malformed hoặc tiêm XML markup ngoài ý muốn.

## 7. Ghép SQLXML với StAX: chương trình JDBC thực tế

Bây giờ ta tái sử dụng **`StaxStreamingDemo.parse(Reader)`** từ ví dụ đã biên dịch để đọc một SQL XML column qua JDBC. File thứ hai là **`JdbcSqlXmlStaxExport.java`**, đặt cùng thư mục với `StaxStreamingDemo.java`.

**Điều kiện chạy thực:** có JDBC driver hỗ trợ SQLXML, kết nối database, bảng `xml_documents` với cột `payload` kiểu XML được driver ánh xạ, có hàng với `id` đã chỉ định, và quyền SELECT. Nếu database dùng kiểu text/LOB thay XML, phải sửa getter/binding cho đúng driver. Chương trình **biên dịch** chỉ với JDK; không có stdout cố định trên mọi database.

### 7.1. File JdbcSqlXmlStaxExport.java

```java
import java.io.Reader;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.SQLXML;
import java.util.Properties;

public final class JdbcSqlXmlStaxExport {

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println(
                    "Usage: java JdbcSqlXmlStaxExport <jdbc-url> <id>");
            return;
        }

        long id = Long.parseLong(args[1]);

        Properties login = new Properties();
        String user = System.getenv("DB_USER");
        String password = System.getenv("DB_PASSWORD");
        if (user != null) {
            login.setProperty("user", user);
        }
        if (password != null) {
            login.setProperty("password", password);
        }

        try (Connection connection =
                     DriverManager.getConnection(args[0], login)) {
            connection.setAutoCommit(false);

            try {
                try (PreparedStatement ps =
                        connection.prepareStatement(
                            "SELECT payload FROM xml_documents "
                            + "WHERE id = ?")) {

                    ps.setLong(1, id);

                    try (ResultSet rs = ps.executeQuery()) {
                        if (!rs.next()) {
                            throw new SQLException(
                                    "Row not found: " + id);
                        }

                        SQLXML value = rs.getSQLXML("payload");

                        if (value == null) {
                            System.out.println("xmlIsNull=true");
                        } else {
                            try {
                                try (Reader source =
                                        value.getCharacterStream()) {
                                    StaxStreamingDemo.Stats stats =
                                            StaxStreamingDemo.parse(source);

                                    System.out.println(
                                            "records=" + stats.records());
                                    System.out.println(
                                            "amountSum=" + stats.amountSum());
                                }
                            } finally {
                                value.free();
                            }
                        }
                    }
                }

                connection.commit();

            } catch (Exception failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    failure.addSuppressed(rollbackError);
                }
                throw failure;
            }
        }
    }
}
```

Để chương trình này chạy, **file `StaxStreamingDemo.java` ở mục 6 cũng phải có mặt** trong cùng default package hoặc cùng classpath đã compile. `StaxStreamingDemo.Stats` là record nested với package access, đủ để hai class ở cùng package dùng chung. Nếu đưa vào packages/module dự án thực, hãy thiết kế visibility/API hợp lệ và đổi imports tương ứng.

### 7.2. Biên dịch và chạy

Biên dịch bằng Java 17+:

```bash
javac -encoding UTF-8 StaxStreamingDemo.java JdbcSqlXmlStaxExport.java
```

Trên Linux/macOS khi có JAR driver tên giả định `driver.jar`:

```bash
java -cp ".:driver.jar" JdbcSqlXmlStaxExport "$JDBC_URL" 1001
```

Trên Windows PowerShell:

```powershell
java -cp '.;driver.jar' JdbcSqlXmlStaxExport $env:JDBC_URL 1001
```

`driver.jar` là **placeholder cho dependency thực của vendor**, không phải JAR JDK tự cung cấp. `JDBC_URL` là connection URL cho database test; nên tránh nhét password vào URL/process arguments. Demo đọc `DB_USER`/`DB_PASSWORD` từ environment nếu được đặt. Với production, ưu tiên secret manager, datasource/pool và TLS theo chính sách tổ chức.

### 7.3. Vòng đời trong code

1. Chương trình mở connection và `setAutoCommit(false)` để SQLXML được đọc trong transaction còn hiệu lực.
2. PreparedStatement sử dụng parameterized query, không nối `id` từ user vào SQL text.
3. `rs.next()` phân biệt không có row; `rs.getSQLXML(...) == null` phân biệt SQL NULL.
4. Với SQLXML không null, gọi duy nhất `getCharacterStream()`. Reader này có thể phụ thuộc vào cursor/transaction.
5. `StaxStreamingDemo.parse(source)` tạo StAX parser hardened và quét một lần, không dựng DOM.
6. Method `parse` đóng `XMLStreamReader` trong `finally`, nhưng **không đóng Reader**.
7. `try (Reader source = ...)` đóng Reader; `finally { value.free(); }` giải phóng SQLXML.
8. ResultSet và PreparedStatement đóng sau khi parse hoàn tất; sau đó mới `commit()`.
9. Nếu parse/XMLStreamException/JDBC exception xảy ra, catch dùng `rollback()`; nếu rollback cũng lỗi, thêm vào suppressed exceptions trước khi ném lại nguyên nhân.

**Không coi lời gọi SELECT đơn giản là bảo đảm SQLXML tồn tại sau commit.** Ta cố tình đọc và free trước khi kết thúc transaction. Không truyền `SQLXML`, `Reader` hay `XMLStreamReader` sang thread khác sau khi trả connection về pool.

### 7.4. Vì sao không có một stdout cố định cho JDBC demo?

Trên database có hàng với XML đúng cấu trúc `orders/order`, chương trình có thể in `records` và `amountSum`. Nhưng nếu thiếu row, null column, XML schema khác, driver không hỗ trợ `getSQLXML`, hoặc connection lỗi, kết quả khác/exception. **Không có cơ sở để tuyên bố đã chạy chương trình này trên một DB thật** khi chưa được cung cấp driver, schema và credentials.

Cả **`StaxStreamingDemo.java` và `JdbcSqlXmlStaxExport.java` đã được biên dịch** trên JDK hiện đại; chỉ demo không cần database đã được chạy kiểm tra stdout. Việc này phân biệt rõ test cú pháp Java với integration test JDBC.

## 8. Khi nào dùng getSource(StAXSource.class) thay vì Reader?

JDBC `SQLXML.getSource(Class<T>)` hỗ trợ các dạng `Source` cho SAX/DOM/StAX/Stream theo contract. Ví dụ:

```java
StAXSource source = sqlxml.getSource(StAXSource.class);
```

Đây là **snippet**, cần import `javax.xml.transform.stax.StAXSource` và đã có `SQLXML sqlxml` readable. `StAXSource` bọc một StAX reader/event reader do implementation cung cấp.

**Điểm khác biệt quan trọng khi XML không đáng tin:**
- Qua `getSource(StAXSource.class)`, parser/reader có thể do JDBC driver/JAXP provider dựng, nên ứng dụng **chưa chắc kiểm soát được security properties**.
- Qua `getCharacterStream()`, ứng dụng tự tạo `XMLInputFactory` hardened trước khi parse.
- Do `SQLXML` chỉ đọc một lần, **không gọi `getSource` rồi `getCharacterStream`** trên cùng instance để “thử cả hai”.
- Với dữ liệu tin cậy và driver đã được audit, `getSource(StAXSource.class)` có thể tiện hoặc hiệu quả. Với XML đến từ nguồn không tin cậy, thường ưu tiên **Reader + parser cấu hình rõ**.

`StAXSource` không phải `XMLInputFactory`. Nếu nhận một `StAXSource`, bạn chỉ có thể làm việc với reader/events được bọc trong nó; không nhất thiết thay được factory/provider hoặc bật lại security features sau khi input đã bắt đầu parse.

## 9. Ghi XML lớn: SQLXML.setCharacterStream + XMLStreamWriter

StAX không chỉ dùng để đọc; bạn cũng có thể **sinh XML theo từng event và ghi vào SQLXML**. Luồng logic:

```text
Records/objects từ ứng dụng
            |
        XMLStreamWriter
            |
         java.io.Writer
            |
    SQLXML.setCharacterStream()
            |
     [đóng XMLStreamWriter và Writer]
            |
    PreparedStatement.setSQLXML(...)
            |
       executeUpdate()
            |
         SQLXML.free()
```

Snippet chính:

```java
SQLXML value = connection.createSQLXML();

try {
    try (Writer target = value.setCharacterStream()) {
        XMLStreamWriter xmlWriter =
                XMLOutputFactory.newDefaultFactory()
                        .createXMLStreamWriter(target);

        try {
            xmlWriter.writeStartDocument();
            xmlWriter.writeStartElement("orders");

            for (Order order : orders) {
                xmlWriter.writeStartElement("order");
                xmlWriter.writeAttribute(
                        "id", Long.toString(order.id()));
                xmlWriter.writeCharacters(order.description());
                xmlWriter.writeEndElement();
            }

            xmlWriter.writeEndElement();
            xmlWriter.writeEndDocument();
            xmlWriter.flush();
        } finally {
            xmlWriter.close();
        }
    }

    try (PreparedStatement ps = connection.prepareStatement(
            "UPDATE xml_documents SET payload = ? WHERE id = ?")) {
        ps.setSQLXML(1, value);
        ps.setLong(2, documentId);
        ps.executeUpdate();
    }
} finally {
    value.free();
}
```

Đây là **snippet tích hợp**, không phải chương trình standalone: cần `Connection connection`, `long documentId`, kiểu `Order` do ứng dụng định nghĩa, `Iterable<Order> orders` và imports `java.sql.SQLXML`, `java.sql.PreparedStatement`, `java.io.Writer`, `javax.xml.stream.XMLOutputFactory`, `XMLStreamWriter`. Không thể copy code để biên dịch nếu chưa tạo model Order và bảng SQL.

**Những điểm bắt buộc:**
- `Connection.createSQLXML()` tạo giá trị writable; gọi **một** setter `setCharacterStream()` trên instance.
- `XMLStreamWriter.writeCharacters` escape nội dung text theo XML syntax; không tự nối chuỗi XML chưa escape.
- `XMLStreamWriter.close()` không mặc nhiên đóng underlying `Writer`; dùng try-with-resources cho `Writer`.
- **Phải đóng output stream ghi SQLXML trước `executeUpdate()`.** Javadoc yêu cầu các output streams đóng trước khi statement execute, nếu không có thể ném `SQLException`.
- SQLXML chỉ hợp lệ trong transaction; `free()` ở `finally` sau execute.
- Dù phía app không tạo một XML String lớn, driver có thể buffer nội dung trong RAM hoặc temporary storage trước khi gửi lên DB. Benchmark thật.

Với XML cần gửi dữ liệu bytes có encoding declaration đặc biệt, `setBinaryStream()` là một API khác; bytes phải thống nhất với XML encoding. Với text Unicode Java, `setCharacterStream()` + StAX writer thường dễ kiểm soát hơn.

## 10. Streaming parse mà không giữ toàn bộ bản ghi

Một chiến lược thường dùng: giữ trạng thái khi vào `<order>`, xử lý fields trong một lượt, rồi gửi kết quả đến consumer. Ví dụ nếu mỗi order nhỏ:

```java
// Pseudocode Java, không phải chương trình standalone.
// Trong vòng lặp XMLStreamReader.next():

if (event == XMLStreamConstants.START_ELEMENT
        && xml.getLocalName().equals("order")) {
    currentId = xml.getAttributeValue(null, "id");
    // Khởi tạo state cho một record.
} else if (event == XMLStreamConstants.CHARACTERS) {
    // Tiêu thụ chunk ký tự; chỉ cộng dồn nếu field có giới hạn.
} else if (event == XMLStreamConstants.END_ELEMENT
        && xml.getLocalName().equals("order")) {
    // Xác thực record và gửi sang sink/downstream.
}
```

**Đây là pseudocode**, có những biến chưa khai báo (`event`, `xml`, `currentId`, sink) nhằm mô tả state machine; không phải mã Java hoàn chỉnh.

Khi format phức tạp, cần theo dõi **stack/độ sâu XML** để không nhầm phần tử `<order>` nằm trong vùng không hợp lệ. Xử lý phần tử có namespace bằng `getNamespaceURI()` + `getLocalName()`. Không dùng `getElementText()` với field không giới hạn kích cỡ; không lưu mọi record vào `List` rồi mới xử lý nếu mục tiêu là giảm memory.

### 10.1. Chuyển sang downstream không đồng nghĩa không có backpressure

Nếu gửi từng record vào queue/service:
- Hạn chế queue length và concurrency; **không** tạo queue vô hạn cho một XML source lớn.
- Nếu downstream chậm, dừng/tạm ngừng đọc hoặc dùng bounded buffer thay vì tiếp tục tiêu thụ DB stream.
- Giữ JDBC connection trong thời gian parse có thể làm **pool starvation**. Với dataset quá lớn, thiết kế batch/offline job riêng hoặc chia tài liệu thành đơn vị nhỏ phù hợp.
- Đừng chia sẻ `XMLStreamReader` cho nhiều threads: parser/cursor không nên coi là thread-safe. Có thể gửi **bản ghi độc lập đã tách khỏi stream**, nhưng memory/ordering phải được kiểm soát.
- Với hiệu ứng ghi DB khác, thiết kế transaction boundaries/idempotency; không coi toàn bộ processing distributed là atomic chỉ vì input là một XML document.

### 10.2. Nếu cần tính tổng tiền chính xác

Demo cộng `amount` kiểu `long` vì đó là **số nguyên thử nghiệm**. Khi dữ liệu là tiền tệ với số thập phân:
- Parse theo contract XML bằng `BigDecimal`, không dùng `double` để cộng tiền.
- Dùng `Currency` hoặc metadata tiền tệ đúng nghiệp vụ.
- Giới hạn số chữ số/scale và kiểm tra overflow, giá trị âm, precision.
- Không tin một attribute `amount` tùy ý từ XML input chỉ vì StAX đọc được string.

## 11. Độ dài ký tự, mã hóa và XML declaration

Trong demo, `textUnits=158894` đến từ `XMLStreamReader.getTextLength()`. Đây là **số Java `char` units của các text events**, không phải:
- Số bytes của file UTF-8.
- Số Unicode code points.
- Số grapheme clusters (ký tự mắt người nhìn thấy).
- Số bytes mà JDBC đã chuyển qua network.

Ví dụ emoji `🌏` là một code point nhưng thường chiếm **hai Java UTF-16 code units**. Dấu tiếng Việt, CJK và emoji có độ dài bytes UTF-8 khác nhau. `Reader` làm việc với ký tự, `InputStream` làm việc với bytes.

### 11.1. XML prolog và encoding

StAX reader nhận **`Reader`** đã decode ký tự. Nếu nguồn XML là một UTF-8 file, `Files.newBufferedReader(path, StandardCharsets.UTF_8)` chỉ rõ charset; còn `SQLXML.getCharacterStream()` trả luồng ký tự Unicode do driver tạo. Với `XMLStreamReader` nhận Reader, parsing sẽ làm việc trên ký tự đã decode, không cần đọc lại bytes theo XML prolog.

Nếu XML bắt đầu từ **`InputStream`**, parser có thể dùng XML encoding declaration/BOM để nhận dạng charset theo XML specification. Không coi mọi XML binary stream luôn UTF-8 nếu declaration báo encoding khác.

**Phải nhất quán:** khi xuất XML bytes qua writer UTF-8, XML declaration không được khai một encoding khác. Nếu giữ nguyên XML serialization từng byte là yêu cầu pháp lý/ký số, SQL XML mapping có thể không bảo toàn encoding/attribute ordering/namespace prefixes sau khi DB xử lý; cần thiết kế lưu trữ và chữ ký dựa trên contract cụ thể.

### 11.2. XML escaping và dữ liệu giữ nguyên

`XMLStreamWriter.writeCharacters("A & B")` sẽ ghi representation XML đúng như `A &amp; B`; parser trả text content `A & B`. Đừng nhầm khác biệt serialization này với dữ liệu bị sửa.

Database có thể serialize lại XML khác thứ tự attributes, whitespace, namespace prefixes hoặc declaration mà vẫn tương đương về **cấu trúc/ngữ nghĩa**. Nếu sản phẩm cần so sánh XML chính xác, quyết định dùng canonical XML hoặc domain-specific structural comparison phù hợp, không tự mặc định `String.equals` giữa hai XML serializations phải true.

## 12. DOM, SAX, StAX: chọn cách xử lý theo kích thước và nghiệp vụ

| Cách | Lợi ích | Đánh đổi |
| --- | --- | --- |
| `SQLXML.getString` rồi DOM | Dễ truy cập bất kỳ node nào, XPath thuận tiện. | Materialize chuỗi và tree, tốn heap với XML lớn. |
| `getCharacterStream` + StAX cursor | Xử lý một lượt theo events, có thể giữ trạng thái nhỏ. | Phải quản lý state, namespaces, validation và resource lifetime. |
| `getCharacterStream` + SAX | Callback streaming, phù hợp parser pipeline. | Logic điều khiển nằm trong handlers, có thể khó theo dõi. |
| `SQLXML.getSource(StAXSource.class)` | Truy cập StAX source do driver cung cấp. | Khó chắc chắn kiểm soát parser hardening khi nguồn không đáng tin. |
| Server-side XML query/index | Giảm lượng XML cần chuyển về app nếu DB hỗ trợ. | SQL và performance phụ thuộc vendor, có thể tốn tài nguyên server. |

**StAX không phải luôn tốt hơn DOM.** Với tài liệu nhỏ và cần XPath qua nhiều phần, DOM có thể đơn giản và đủ nhanh. StAX rất có giá trị khi tài liệu lớn, chỉ cần đọc một lần, hoặc cần transform/export từng records mà không giữ cả cây.

**XML lớn không nhất thiết nên nằm nguyên trong một row.** Nếu thường xuyên truy vấn từng order trong một XML document khổng lồ, có thể cân nhắc schema relational (order rows), JSON/XML indexes theo DBMS hoặc lưu file/object storage kèm metadata ở database. Thiết kế vật lý là bài toán dữ liệu riêng; `SQLXML + StAX` là một phương pháp truy cập chứ không tự tối ưu mô hình dữ liệu.

## 13. Cách xử lý lỗi và rollback

Các nhóm lỗi quan trọng:

| Tình huống | Exception/triệu chứng | Hướng xử lý |
| --- | --- | --- |
| JDBC driver không hỗ trợ SQLXML | `SQLFeatureNotSupportedException`. | Kiểm tra driver và kiểu cột; dùng mapping thay thế đã test, không fallback mù. |
| SQL column là NULL | `getSQLXML(...) == null`. | Phân biệt với document rỗng/không có row. |
| SQLXML bị đọc hai lần hoặc đã free | `SQLException` theo trạng thái object. | Một getter/instance, free sau khi parse. |
| Kết nối/transaction đóng trước parse | Driver stream lỗi hoặc `SQLException`. | Giữ Reader, SQLXML, ResultSet, connection hợp lệ. |
| XML malformed | `XMLStreamException`, có thể có location line/column. | Báo lỗi hợp lý; không log XML payload nhạy cảm. |
| DOCTYPE/external entity | `XMLStreamException` vì security policy. | Fail closed; không chuyển sang parser yếu hơn để “đọc cho được”. |
| Missing/invalid amount | `NumberFormatException` hoặc null attribute. | Validate schema/attributes và quy tắc domain; không parse tùy tiện. |
| Document quá lớn/sâu | Giới hạn size/depth/time vượt ngưỡng. | Ngừng parse, rollback/cancel và cleanup resources. |
| Memory tăng dù dùng StAX | Driver buffer, một event text quá lớn hoặc app gom records. | Heap profiling, bounded buffers, đổi driver/mapping/chunking. |
| `XMLStreamReader.close()` đã gọi nhưng DB stream còn mở | Parser.close không bắt buộc đóng Reader nguồn. | Đóng Reader riêng bằng try-with-resources. |
| `SQLXML.free()` che lỗi parse gốc | Cleanup cũng ném `SQLException`. | Bảo toàn lỗi gốc bằng suppressed exceptions khi cần. |
| Output writer ghi dở giữa chừng | I/O/network failure. | Temp file + cleanup hoặc idempotent output, không coi transaction DB rollback là rollback file. |
| Pool cạn connection | Giữ connection quá lâu khi parse document lớn. | Giới hạn concurrency/timeout, batch processing riêng. |

### 13.1. Bắt ngoại lệ chuyên biệt đúng thứ tự

`SQLFeatureNotSupportedException` là subclass `SQLException`, nên nếu cùng block try có hai catch, đặt subclass trước:

```java
try {
    SQLXML xml = connection.createSQLXML();
    try {
        xml.setString("<orders/>");
        // Bind/execute nếu database thực sự hỗ trợ.
    } finally {
        xml.free();
    }
} catch (SQLFeatureNotSupportedException unsupported) {
    // Chọn phương án được driver/vendor xác nhận.
} catch (SQLException sqlError) {
    // Các lỗi JDBC khác.
}
```

Đây là **snippet**, không phải chương trình hoàn chỉnh; yêu cầu imports `java.sql.SQLXML`, `SQLException`, `SQLFeatureNotSupportedException` và `Connection connection`. Khi StAX parse trong JDBC pipeline, `XMLStreamException` không phải subclass `SQLException`: hãy phân loại riêng lỗi XML input và lỗi database. Nếu conversion exception đã được JDBC bọc, xem `getCause()` và `getNextException()` theo chính sách logs an toàn.

### 13.2. Transaction không thay thế resource cleanup

Nếu `connection.setAutoCommit(false)`, có thể rollback SQL work khi parse thất bại. Nhưng rollback không tự đóng mọi Reader/SQLXML hoặc xóa output file đã viết một phần. Hãy quản lý riêng:
- Java resources qua try-with-resources/finally.
- DB state qua commit/rollback.
- File output qua temp file/atomic rename khi phù hợp.
- Job processing state và retry/idempotency theo nghiệp vụ.

Đừng retry cùng một `Reader` đã bị consume sau lỗi. Với JDBC stream muốn retry, phải **mở lại nguồn/đọc lại SQLXML instance mới** trong transaction hợp lệ.

## 14. Performance: streaming ở đâu, buffer ở đâu?

### 14.1. Bên ứng dụng

Một `XMLStreamReader` thường không dựng DOM cho toàn tài liệu. Nếu code chỉ giữ counters và trạng thái của record hiện tại, lượng dữ liệu do application chủ động giữ có thể nhỏ so với toàn XML. Với dữ liệu hàng chục nghìn orders, giảm tạo `String`/`List` lớn cũng giúp GC.

### 14.2. Bên JDBC driver và database

Không có cam kết chung rằng `SQLXML.getCharacterStream()` luôn fetch dữ liệu từng chunk qua mạng. Driver có thể:
- Materialize SQLXML trong bộ nhớ trước khi trả Reader.
- Buffer từng phần hoặc toàn bộ XML.
- Sử dụng server-side XML value/LOB streaming nếu hỗ trợ.
- Giữ transaction/cursor lâu trong khi app parse.
- Serialize lại XML trước khi chuyển sang Java, làm tăng chi phí CPU/IO.

Cần đo với **đúng DBMS, JDBC driver, JDK, XML size và query plan**. Một chiến lược StAX tốt ở app chưa chắc tối ưu mọi tầng.

### 14.3. Các metric có giá trị

Theo dõi:
- Peak heap và GC pause khi xuất/đọc XML.
- Time-to-first-event, tổng latency, throughput records/s.
- Số connection bị giữ và thời gian giữ connection.
- Network traffic, DB CPU, I/O và temporary storage.
- Kích thước queue/downstream, số records lỗi/DTD blocked.
- Tài liệu quá sâu/quá lớn bị từ chối và nguyên nhân.

Tránh **logging toàn bộ XML** hoặc entity values chỉ để đo hiệu năng; payload có thể chứa PII, bí mật hoặc dữ liệu khách hàng.

### 14.4. Không tái sử dụng parser/Reader bất cẩn

`XMLStreamReader` là stateful cursor, không nên được chia sẻ giữa các request/threads. `XMLInputFactory` cũng có thể có state/provider-specific thread-safety behavior; nếu tái sử dụng, cần kiểm tra documentation, hoặc tạo factory theo scope phù hợp và cache config immutable đã kiểm thử. `Reader` từ JDBC có thể chỉ tồn tại cho transaction hiện tại; không gửi nó qua asynchronous job sau khi method/connection đã đóng.

## 15. Kịch bản tạo XML trực tiếp trong DB và chuyển đổi XML

Nếu mục tiêu là **chuyển đổi** XML lớn sang XML khác, có thể đọc bằng StAX và ghi bằng `XMLStreamWriter` mà không materialize DOM:
1. Đọc event hiện tại.
2. Xác minh element/attribute theo schema.
3. Ghi lại một event tương ứng hoặc thay đổi có kiểm soát.
4. Chặn DTD/external references và giới hạn payload.
5. Đóng output writer trước khi bind SQLXML mới vào statement.

Khi chuyển đổi namespace/encoding hoặc thêm elements, cần đảm bảo output vẫn well-formed và không làm hỏng semantics. Với yêu cầu XSLT, có thể dùng `Transformer` trên nguồn SAX/StAX đã harden, nhưng giới hạn external stylesheet/DTD qua JAXP riêng. Không nên đưa một `StAXSource` không kiểm soát parser vào transformer rồi mặc định an toàn.

Nếu chỉ cần trích một vài trường để analytics, **đừng ghi lại toàn bộ XML** nếu không cần. StAX event processing + sink database/batch phù hợp hơn.

## 16. Kiểm thử tích hợp cần có trước production

**Test 1 — Driver/column mapping:** kiểm tra native XML type/`Types.SQLXML`, `getSQLXML`, `createSQLXML` và `setSQLXML` theo driver thực; không giả định một DDL cho mọi database.

**Test 2 — Unicode và namespace:** XML có tiếng Việt, CJK, emoji, XML escapes (`&amp;`), namespace prefixes; xác nhận thông tin/ngữ nghĩa sau round-trip.

**Test 3 — SQL NULL:** row có SQL NULL trả SQLXML null; row không tồn tại khác XML `<orders/>`.

**Test 4 — Single-use SQLXML:** chỉ một getter trên một instance, gọi `free` ở cuối. Giữ parser trong transaction, không dùng sau commit.

**Test 5 — Nhiều CHARACTERS events:** đưa text có CDATA, whitespace và encoding khác; parser không được giả định mỗi element có đúng một event text.

**Test 6 — XXE/SSRF:** feed DOCTYPE, external entity file/http, và parser configuration failure; không được phát sinh file/network access ngoài phép.

**Test 7 — XML bombs:** XML rất sâu, rất nhiều attributes, text dài, entity expansion; xác nhận giới hạn hoạt động, không làm sập JVM.

**Test 8 — Errors:** XML malformed, amount không phải số, thiếu namespace/root, sai schema; phân biệt `XMLStreamException` với SQLExceptions.

**Test 9 — Large XML:** so sánh getString+DOM với Reader+StAX về memory, GC, CPU, network và connection-pool occupancy.

**Test 10 — Slow downstream:** giả lập consumer chậm/queue đầy; xác nhận backpressure/bounded memory, timeout và hủy bỏ được.

**Test 11 — Writer closure:** khi ghi XML qua `SQLXML.setCharacterStream`, kiểm tra đóng `XMLStreamWriter` và Writer trước khi `PreparedStatement.executeUpdate`.

**Test 12 — Transaction failure:** parse nửa chừng rồi exception, rollback SQL, đóng/free hết resources, xử lý retry với nguồn mới và idempotency.

**Test 13 — Serialization differences:** DB có thể thay whitespace/attribute order/prefix. So sánh dựa trên XML semantics/canonicalization policy phù hợp.

**Test 14 — Pool reuse:** sau khi đọc XML lớn, connection được trả pool không còn unclosed cursor/Reader/SQLXML và không bị giữ vô hạn.

**Test 15 — Parser provider upgrade:** nếu thay StAX provider/JDK, chạy lại security/property compatibility tests; không coi mọi parser có behavior giống nhau.

## 17. Sai lầm phổ biến và cách tránh

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| `sqlxml.getString()` rồi `getCharacterStream()` | SQLXML bị đọc hai lần. | Chọn một getter; parse một lượt. |
| `try (SQLXML x = ...)` | Không compile vì SQLXML không AutoCloseable. | `try/finally` với `free()`. |
| Đóng JDBC ResultSet trước StAX parse | Reader có thể không còn hợp lệ. | Đọc xong trong transaction/cursor scope. |
| Chỉ gọi `XMLStreamReader.close()` | Underlying Reader có thể còn mở. | Đóng Reader riêng. |
| Chỉ tắt `SUPPORT_DTD` rồi khẳng định DOCTYPE luôn bị reject | Có parser bỏ qua DTD mà vẫn tiếp tục parse. | Kết hợp external entity disable, resolver và policy reject DTD. |
| Không cấu hình external entities | Rủi ro XXE/SSRF. | Harden XMLInputFactory và fail closed. |
| Gọi `getElementText()` trên field không giới hạn | Materialize String lớn. | Xử lý CHARACTERS chunks. |
| Giữ `List` mọi records sau parse | Mất lợi ích bounded memory. | Dùng sink/batch/queue giới hạn. |
| Tin `getCharacterStream` bảo đảm zero-copy | Driver có thể buffer. | Benchmark driver/DBMS thực. |
| Dùng XML prefix làm định danh cố định | Xử lý sai namespaces. | Kiểm tra namespace URI + local name. |
| Dùng `getTextLength()` làm số UTF-8 bytes | Sai đơn vị. | Phân biệt char units/bytes/codepoints. |
| `writeCharacters` xong quên đóng writer | Stream không hoàn tất trước SQL execute. | Đóng XMLStreamWriter và Writer trước execute. |
| Xây SQL bằng nối chuỗi ID/XML text | SQL injection/escaping. | PreparedStatement bind params. |
| Parse amount tiền tệ bằng double | Sai precision. | BigDecimal + validation. |
| Retry trên Reader đã tiêu thụ | Stream EOF, dữ liệu thiếu. | Mở nguồn/SQLXML mới. |
| Kết luận lỗi XML dựa trên một driver | Hành vi vendor khác nhau. | Integration test đúng stack. |

## 18. Câu hỏi ôn tập

**Câu 1.** Tại sao nên kết hợp `SQLXML.getCharacterStream()` với StAX khi XML rất lớn?

**Đáp án:** Nó cho phép application xử lý XML từng event, tránh bắt buộc tạo một `String`/DOM tree cho toàn bộ XML. Tuy nhiên driver/server vẫn có thể buffer nội bộ; cần đo thực tế.

**Câu 2.** Có thể gọi `getSource(StAXSource.class)` rồi `getCharacterStream()` trên cùng SQLXML không?

**Đáp án:** Không. Một SQLXML instance chỉ được đọc tối đa một lần. Chọn một getter theo mức kiểm soát parser mong muốn.

**Câu 3.** `XMLStreamReader.close()` có tự đóng JDBC `Reader` nguồn không?

**Đáp án:** Không nên giả định. Hợp đồng StAX không yêu cầu parser đóng stream đầu vào; dùng try-with-resources cho Reader riêng.

**Câu 4.** `SUPPORT_DTD=false` có đảm bảo mọi DOCTYPE làm parser ném exception ngay không?

**Đáp án:** Không. Có implementation bỏ qua DTD; để enforce cấm DOCTYPE cần kết hợp policy/DTD-event rejection hoặc cơ chế riêng của provider, ngoài việc khóa external entities.

**Câu 5.** Vì sao `getElementText()` không thích hợp cho nội dung hàng trăm MB?

**Đáp án:** Method thu thập text của element thành String, làm mất lợi ích streaming ở tầng app. Xử lý các CHARACTERS chunks có giới hạn sẽ phù hợp hơn.

**Câu 6.** Sau khi `getSQLXML` trả null, có nên parse bằng StAX không?

**Đáp án:** Không. Đây là SQL NULL; phải phân biệt với document XML rỗng và với không có row.

**Câu 7.** `getTextLength` đo đơn vị nào?

**Đáp án:** Độ dài text event theo Java `char` units; không phải bytes UTF-8 hay số code points Unicode.

**Câu 8.** Để ghi XML lớn vào SQLXML bằng StAX, cần đóng gì trước `executeUpdate()`?

**Đáp án:** Hoàn tất/đóng `XMLStreamWriter` và Writer được trả từ `SQLXML.setCharacterStream()` rồi mới bind/execute. Cuối cùng `SQLXML.free()`.

**Câu 9.** Có thể dùng riêng StAX parser để xác minh XSD nghiệp vụ không?

**Đáp án:** Không. Pull parsing chỉ bảo đảm XML well-formed theo parser; validation theo XSD/contract là bước riêng cần schema/validator bảo mật.

**Câu 10.** Vì sao cần test riêng `SQLXML + StAX` trên driver thật?

**Đáp án:** SQL XML type/mapping, buffering, transaction và stream lifetime là driver/DBMS-specific; demo StAX standalone không xác minh chúng.

## 19. Checklist triển khai

1. Xác minh cột DB map sang SQL XML và JDBC driver hỗ trợ `SQLXML`.
2. Giữ `ResultSet`/transaction mở trong suốt parse; `SQLXML.getCharacterStream()` chỉ được gọi một lần.
3. Tạo `XMLInputFactory` an toàn: tắt DTD/external entities, khóa external DTD access, resolver fail closed.
4. Nếu policy cấm DOCTYPE, **thực thi reject** chứ không chỉ hy vọng `SUPPORT_DTD=false` tự ném lỗi.
5. Duyệt `XMLStreamReader.next()` theo event/state, không build toàn bộ DOM/String/records.
6. Với text lớn, xử lý `getTextCharacters`/`getTextLength` theo chunks, áp giới hạn.
7. Kiểm tra XML namespaces, root, depth, attribute/data types và domain schema.
8. Không coi StAX là validator XSD mặc định.
9. Đóng parser, Reader, gọi SQLXML.free, rồi mới đóng ResultSet/commit/return connection.
10. Dùng PreparedStatement bind SQL parameters, không nối XML/ID từ input vào SQL.
11. Bảo vệ tài nguyên: size, depth, timeout, concurrency, downstream queue và connection pool.
12. Đo memory/GC/latency trên driver thực, không tự kết luận streaming toàn hệ thống.
13. Khi ghi XML: tạo SQLXML, dùng StAX writer, **đóng output trước execute**, free sau.
14. Test XML lỗi, SQL NULL, Unicode, namespace, XXE, driver thiếu tính năng, rollback và retry.
15. Áp dụng kiến thức Java 17+ còn hỗ trợ, không cần parser/JDBC XML API legacy.

## 20. Tài liệu chính thức và bảo mật

- [Java SE 17 — SQLXML](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLXML.html): single-read/write, transaction validity, streams, `getSource` và `free()`.
- [Java SE 17 — Connection](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html): `createSQLXML` và transaction.
- [Java SE 17 — ResultSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html): `getSQLXML` và row/stream scope.
- [Java SE 17 — PreparedStatement](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html): `setSQLXML`, bind và execute.
- [Java SE 17 — XMLInputFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/stream/XMLInputFactory.html): StAX security properties và factory.
- [Java SE 17 — XMLStreamReader](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/stream/XMLStreamReader.html): event cursor, `getTextCharacters`, `getTextLength` và `close`.
- [Java SE 17 — XMLOutputFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/stream/XMLOutputFactory.html): writer factory.
- [Java SE 17 — XMLStreamWriter](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/stream/XMLStreamWriter.html): tạo XML theo events.
- [Java SE 17 — XMLConstants](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/XMLConstants.html): `ACCESS_EXTERNAL_DTD`.
- [OWASP — XML External Entity Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html): StAX chống XXE, external entities, resolver.
- [Java SE 25 — SQLXML](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/SQLXML.html): API được hỗ trợ trong JDK hiện đại.
