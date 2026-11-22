# SQLXML: getSource, setResult và tích hợp JAXP trong JDBC hiện đại

## 1. Đặt vấn đề: XML từ cơ sở dữ liệu không chỉ là String

Khi một hệ thống Java lưu tài liệu XML trong database, ứng dụng thường cần đọc dữ liệu để trích xuất các phần tử, kiểm tra cấu trúc, chuyển đổi nội dung hoặc ghi tài liệu mới. Có thể đọc XML như `String`, nhưng cách này dễ phát sinh chuỗi trung gian lớn, encode/decode nhiều lượt và code xử lý XML rải rác. JDBC có interface **`java.sql.SQLXML`** và các phương thức **`getSource(Class<T>)`** / **`setResult(Class<T>)`** để tích hợp dữ liệu kiểu SQL XML trực tiếp với **JAXP** — Java API for XML Processing.

Hai hướng chính:

- **Đọc:** `ResultSet.getSQLXML(...)` → một `SQLXML` có thể đọc → `sqlxml.getSource(DOMSource.class)` hoặc `StreamSource.class`/`SAXSource.class`/`StAXSource.class` → ứng dụng phân tích/biến đổi XML.
- **Ghi:** `Connection.createSQLXML()` → `xml.setResult(DOMResult.class)` hoặc `StreamResult.class`/`SAXResult.class`/`StAXResult.class` → ứng dụng tạo tài liệu XML → `PreparedStatement.setSQLXML(index, xml)` → `executeUpdate()`.

**Hai điều bắt buộc nhớ:**

1. `Source` là **đầu vào** cho xử lý XML; `Result` là **đích đầu ra**. `getSource` không trả `Result` và `setResult` không trả `Source`.
2. `SQLXML` có **trạng thái đọc/ghi một lần** và vòng đời tài nguyên đặc biệt: không phải container String dùng đi dùng lại thoải mái. Sau `free()`, nó không còn được đọc hoặc ghi; với các JDBC drivers thông dụng, việc truy cập XML còn gắn với connection/transaction đã tạo nó.

Java hiện đại vẫn hỗ trợ SQLXML và JAXP: `SQLXML` thuộc module `java.sql`, còn `javax.xml.transform`, `javax.xml.parsers`, `javax.xml.stream`, `javax.xml.xpath`, `org.w3c.dom` thuộc `java.xml`. Không đổi các package này thành `jakarta.xml...`: đây là các API Java SE vẫn còn được sử dụng trong **Java 17+**.

**Bảo mật có vai trò trung tâm.** XML không tin cậy có thể chứa DTD, external entities hoặc XSLT tham chiếu URL bên ngoài, dẫn tới **XXE**, SSRF, đọc file nội bộ hoặc tiêu tốn tài nguyên. Chỉ dùng `getSource(DOMSource.class)` rồi kiểm tra cấu trúc DOM **không tự chứng minh parser do JDBC driver tạo đã được cấu hình an toàn**. Bài giải thích cả con đường “JAXP thuận tiện” và con đường **tự cấu hình parser trước khi parse** khi input không tin cậy.

## 2. Những lớp và gói phải phân biệt

| Thành phần | Package / Module | Vai trò |
| --- | --- | --- |
| `SQLXML` | `java.sql` / `java.sql` | Interface JDBC đại diện giá trị SQL XML |
| `Connection.createSQLXML()` | `java.sql.Connection` | Tạo một SQLXML rỗng để **ghi** dữ liệu XML |
| `ResultSet.getSQLXML(...)` | `java.sql.ResultSet` | Lấy SQLXML hiện có từ cột SQL |
| `PreparedStatement.setSQLXML(i, xml)` | `java.sql.PreparedStatement` | Bind SQLXML vào parameter của câu SQL |
| `Source` | `javax.xml.transform` / `java.xml` | Trừu tượng đầu vào cho transform/XML processors |
| `Result` | `javax.xml.transform` / `java.xml` | Trừu tượng đích đầu ra cho transform/XML processors |
| `DOMSource` / `DOMResult` | `javax.xml.transform.dom` | Kết nối với DOM tree trong bộ nhớ |
| `SAXSource` / `SAXResult` | `javax.xml.transform.sax` | Kết nối với luồng SAX callbacks |
| `StAXSource` / `StAXResult` | `javax.xml.transform.stax` | Kết nối với StAX event/stream APIs |
| `StreamSource` / `StreamResult` | `javax.xml.transform.stream` | Kết nối với `Reader`, `InputStream`, `Writer` hoặc `OutputStream` |
| `TransformerFactory` / `Transformer` | `javax.xml.transform` | Identity transform hoặc XSLT |
| `DocumentBuilderFactory` | `javax.xml.parsers` | Cấu hình DOM parser trước khi parse |
| `XMLInputFactory` | `javax.xml.stream` | Cấu hình StAX pull parser |
| `XMLConstants` | `javax.xml` | Secure processing, giới hạn external access |

**JAXP không đồng nghĩa chỉ DOM.** DOM tạo cây trong bộ nhớ, SAX đọc theo callbacks, StAX đọc theo sự kiện/luồng pull, còn XSLT/Transformer biến một `Source` thành một `Result`. Chọn theo cấu trúc dữ liệu, yêu cầu truy cập ngẫu nhiên và quy mô XML.

Ví dụ một pipeline:

~~~text
                  JDBC / Database
                         |
               ResultSet.getSQLXML(...)
                         |
                  SQLXML (readable)
                         |
             getSource(DOMSource.class)
                         |
              DOM Document / XPath
                         |
                Transformer (JAXP)
                         |
                 DOMSource(Document)
                         |
                  StreamResult/DOMResult
                         |
                SQLXML.setResult(...)
                         |
             PreparedStatement.setSQLXML
                         |
                 Database SQL XML
~~~

**Sơ đồ là đường xử lý khái niệm, không có nghĩa bạn có thể gọi `getSource` rồi `setResult` trên cùng một SQLXML object.** Đọc dữ liệu cũ và ghi dữ liệu mới thường dùng **hai đối tượng SQLXML** có trạng thái/vòng đời độc lập.

## 3. API `SQLXML.getSource(Class<T>)`

Chữ ký trong Java SE 25:

~~~java
<T extends Source> T getSource(Class<T> sourceClass) throws SQLException;
~~~

Tham số `sourceClass` là **class của kiểu Source muốn nhận**. Các kiểu Javadoc yêu cầu được hỗ trợ tối thiểu khi driver hỗ trợ SQLXML:

~~~java
DOMSource    dom  = xml.getSource(DOMSource.class);
SAXSource    sax  = xml.getSource(SAXSource.class);
StAXSource   stax = xml.getSource(StAXSource.class);
StreamSource raw  = xml.getSource(StreamSource.class);
~~~

**Bốn dòng trên chỉ minh họa các overload**, **không** được chạy liên tiếp trên **cùng một** instance `xml`. Mỗi dòng cần một SQLXML ở trạng thái **readable chưa từng đọc**, hoặc một lần lookup mới. Phạm vi “chỉ đọc một lần” không phải một mẹo tối ưu hóa: nó là **hợp đồng trạng thái** của SQLXML.

Nếu truyền `null` cho `getSource(null)`, JDBC có thể trả **Source do vendor chọn**. Cách này hợp lệ theo API nhưng không nên cast cứng sang `DOMSource`/`StreamSource` nếu chưa kiểm tra kiểu thực tế. Trong app cần kiểu rõ, hãy truyền `DOMSource.class` hoặc loại phù hợp.

### `DOMSource`

~~~java
SQLXML xml = rs.getSQLXML("payload_xml");
if (xml != null) {
    try {
        DOMSource source = xml.getSource(DOMSource.class);
        Document document = (Document) source.getNode();
        String root = document.getDocumentElement().getLocalName();
    } finally {
        xml.free();
    }
}
~~~

Đây là **mã minh họa trong method**, cần `ResultSet rs` đang đứng tại row hợp lệ và imports `SQLXML`, `DOMSource`, `Document`. Khi dùng namespace-aware DOM, `getLocalName()` trả local name; với XML không có namespace và một số nguồn DOM khác, cần xác định cách gọi phù hợp như `getTagName()`.

**Lợi ích:** DOM thích hợp khi cần tìm nhiều node, XPath, cập nhật cấu trúc hoặc chuyển một cây đã có sang XML. **Hạn chế:** DOM thường cần bộ nhớ tương ứng với toàn tài liệu và driver có thể tạo Document **ngay trong `getSource`**, trước khi app kịp áp parser security options.

### `SAXSource`

~~~java
SAXSource source = xml.getSource(SAXSource.class);
XMLReader reader = source.getXMLReader();
reader.setContentHandler(myContentHandler);
reader.parse(source.getInputSource());
~~~

Đây là đoạn minh họa, cần một `SQLXML xml` còn readable và một `ContentHandler` đã có. SAX là **push/callback**: handler nhận `startElement`, `characters`, `endElement`; thường không giữ cả document trong RAM. Driver/JAXP có thể cung cấp XMLReader và InputSource theo cách implementation-dependent; kiểm tra null và hướng dẫn driver nếu cần.

**An toàn:** cấu hình parser ở đúng lớp chịu trách nhiệm parse, hoặc ưu tiên lấy text/character stream rồi tạo `XMLReader` đã được harden trước. Nếu `getSource(SAXSource.class)` trả một reader mà driver đã cấu hình sẵn, không được giả định nó chặn DTD/XXE chỉ vì bạn dự định gắn handler.

### `StAXSource`

~~~java
StAXSource source = xml.getSource(StAXSource.class);
XMLStreamReader stream = source.getXMLStreamReader();
// Xử lý stream events; đóng XMLStreamReader khi xong nếu thuộc quyền sở hữu.
~~~

Đây là đoạn minh họa, driver có thể trả `XMLEventReader` thay vì `XMLStreamReader` tùy kiểu StAXSource; kiểm tra accessor thực tế và driver docs. StAX là **pull parser**: application gọi `next()` và quyết định cách xử lý, thích hợp XML lớn, nhưng vẫn phải cấu hình **DTD/external entity policy** trước khi parse tài liệu không tin cậy.

### `StreamSource`

~~~java
StreamSource source = xml.getSource(StreamSource.class);
Reader reader = source.getReader();
// Nếu driver cấp Reader: đưa vào parser đã cấu hình bảo mật rồi đóng Reader.
~~~

`StreamSource` có thể có `Reader` hoặc `InputStream` hoặc `systemId` tùy implementation. **Không được giả định `getReader()` luôn khác null.** Nếu chỉ có `systemId`, một JAXP processor có thể cố mở URL đó; cần kiểm soát scheme, resolver và external access policy. Nếu chỉ có `InputStream`, việc parse trực tiếp bytes cần XML encoding xử lý đúng. Với dữ liệu không tin cậy và không có kênh stream usable, hãy kiểm tra driver capability/fallback chính thức thay vì tự cho transformer truy cập một URI không được kiểm soát.

### Lợi ích hiệu năng có điều kiện

Javadoc `SQLXML` ghi nhận database có thể lưu XML dạng tối ưu; dùng `getSource`/`setResult` **có thể** tránh một số bước chuyển sang text stream rồi parse lại. Nhưng không có bảo đảm mọi driver nhanh hơn với mọi kiểu Source/Result. `DOMSource` vẫn có thể rất tốn RAM; `StreamSource` và `StAXSource` có thể tiết kiệm bộ nhớ nếu driver thực sự stream. Đo trên driver/DBMS, kích thước tài liệu và truy vấn thật.

## 4. API `SQLXML.setResult(Class<T>)`

Chữ ký:

~~~java
<T extends Result> T setResult(Class<T> resultClass) throws SQLException;
~~~

Các kiểu `Result` được JDBC yêu cầu hỗ trợ tối thiểu khi driver hỗ trợ SQLXML:

~~~java
DOMResult    dom  = writableXml.setResult(DOMResult.class);
SAXResult    sax  = writableXml.setResult(SAXResult.class);
StAXResult   stax = writableXml.setResult(StAXResult.class);
StreamResult out  = writableXml.setResult(StreamResult.class);
~~~

**Cảnh báo:** Bốn lời gọi ở đây cũng **chỉ minh họa lựa chọn riêng**, không được thực hiện trên **cùng** `writableXml`. Một SQLXML writable chỉ nhận **một lần chọn kênh ghi**; sau `setResult` nó chuyển sang trạng thái không ghi lại được theo API, dù ứng dụng còn cần hoàn thành việc ghi vào Result vừa nhận.

### `DOMResult`

~~~java
SQLXML newXml = connection.createSQLXML();
try {
    DOMResult result = newXml.setResult(DOMResult.class);
    result.setNode(document);
    // Sau khi hoàn thành DOM, có thể bind newXml vào PreparedStatement.
} finally {
    newXml.free();
}
~~~

Đoạn này **chỉ minh họa**: `connection`, `Document document` và JDBC statement thực tế cần được cấu hình, và phải **bind/execute trước `free()`**, không copy try/finally một cách làm mất dữ liệu. Driver có thể cung cấp một `DOMResult` có sẵn `Node`; trong trường hợp đó, đừng mặc định việc `setNode` thay hẳn target đã được driver thiết lập luôn có semantics đồng nhất giữa vendors. Hãy kiểm thử đúng kiểu Result mà driver trả về.

Trong code production, một quy trình hoàn chỉnh phải bảo đảm:
1. Tạo SQLXML khi connection còn sống.
2. Chọn `setResult(DOMResult.class)` đúng một lần.
3. Điền một **XML Document well-formed** theo contract driver.
4. Bind bằng `PreparedStatement.setSQLXML` và execute.
5. `free()` trong `finally`, dọn Result/JAXP resources cần thiết.

### `SAXResult` và `StAXResult`

`SAXResult` có `getHandler()` trả `ContentHandler` dùng để nhận các SAX events. `StAXResult` có thể chứa `XMLStreamWriter` hoặc `XMLEventWriter`, dùng để ghi XML events. Không tự xây parser/serializer rồi nối vào một Result mà không xem nó chứa writer/handler nào. Với SAX cần phát đủ `startDocument/startElement/characters/endElement/endDocument` hợp lệ; với StAX cần hoàn thành/flush/close writer theo driver và ownership.

### `StreamResult`

~~~java
StreamResult sink = xml.setResult(StreamResult.class);
Transformer transform = safeTransformerFactory.newTransformer();
transform.transform(new DOMSource(document), sink);
if (sink.getWriter() != null) {
    sink.getWriter().close();
}
~~~

Đây là **đoạn minh họa trong method**, `safeTransformerFactory` là factory **đã cấu hình bảo mật**, `xml` là SQLXML writable, `document` là Document. `StreamResult` có thể trả `Writer` hoặc `OutputStream` hoặc output destination do driver cung cấp: xử lý đúng resource có thật. Javadoc SQLXML yêu cầu **mọi output streams phải đóng trước khi `execute()`**; áp dụng quy trình flush/close theo driver, không để output dang dở rồi bind/execute. Không dùng `System.out` làm Result của SQLXML cần lưu DB.

Nếu truyền `setResult(null)`, Result class do vendor chọn. Với code cần behavior xác định và testable, ưu tiên loại tường minh.

## 5. Luồng dữ liệu JDBC hoàn chỉnh: đọc XML đang lưu

Một phương thức repository đọc SQL XML rồi chuyển thành DOM có thể có dạng:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.SQLXML;
import javax.sql.DataSource;
import javax.xml.transform.dom.DOMSource;
import org.w3c.dom.Document;

public final class XmlReaderRepository {
    private final DataSource source;

    public XmlReaderRepository(DataSource source) {
        this.source = source;
    }

    public Document findDocument(long id) throws SQLException {
        String sql = "SELECT payload_xml FROM document_store WHERE id = ?";
        try (Connection connection = source.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, id);

            try (ResultSet rows = statement.executeQuery()) {
                if (!rows.next()) return null; // Không có row.
                SQLXML value = rows.getSQLXML(1);
                if (value == null) return null; // Có row nhưng SQL NULL.

                try {
                    DOMSource dom = value.getSource(DOMSource.class);
                    if (!(dom.getNode() instanceof Document document)) {
                        throw new SQLException("Driver did not return a Document node");
                    }
                    return document;
                } finally {
                    value.free();
                }
            }
        }
    }
}
~~~

Đây là một **class Java 17 biên dịch được** với JDK chuẩn, nhưng **không chạy độc lập**: cần `DataSource` thật, JDBC driver/database có cột kiểu SQL XML, quyền SELECT và schema `document_store` phù hợp. `Document` trả về cần độc lập với vòng đời `SQLXML`/connection theo semantics driver; nếu driver dùng document backed bởi tài nguyên lazy, cần materialize/copy trong lúc connection còn sống và test portability.

**Quan trọng về an toàn:** ví dụ `getSource(DOMSource.class)` thích hợp khi XML đã qua trust boundary và driver được xác minh cấu hình; nếu XML có thể do bên ngoài đưa vào, bạn cần **kiểm soát parser mà thực sự phân tích bytes**, thường theo `getCharacterStream`/`getBinaryStream` với một `DocumentBuilderFactory` đã harden hoặc một driver-specific secure parsing contract. Nếu driver đã parse bên trong `getSource(DOMSource.class)`, việc kiểm tra DOCTYPE/DOM **sau đó** có thể đã quá muộn để ngăn XXE trong quá trình parse.

### SQL NULL khác XML literal hoặc root rỗng

- `rows.next() == false`: **không có row**, không phải cùng nghĩa một row có SQL NULL.
- `rows.getSQLXML(...) == null`: row tồn tại, cột có **SQL NULL**. Gọi `rows.wasNull()` ngay sau getter nếu cần xác nhận.
- XML text `<note/>`: một tài liệu XML hợp lệ có root element rỗng, **không** phải SQL NULL.
- String `""`: **không phải một XML document well-formed** với root element; driver/DBMS có thể reject, không được dùng làm “XML rỗng”.
- `<note xsi:nil="true"/>`: đó là dữ liệu XML có attribute `xsi:nil` theo một schema/namespace, **không tự chuyển thành SQL NULL** ở JDBC.

Nếu domain cần phân biệt no-row, SQL NULL và XML document rỗng, nên dùng một result type có cấu trúc (ví dụ `Optional<Record>` với field nullable hoặc sealed result) thay vì trả `null` cho cả hai trạng thái.

## 6. Luồng JDBC hoàn chỉnh: viết `SQLXML` vào database

Một cách ghi bằng `setResult(StreamResult.class)` trong code có JDBC connection thật:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.SQLXML;
import javax.sql.DataSource;
import javax.xml.transform.Transformer;
import javax.xml.transform.dom.DOMSource;
import javax.xml.transform.stream.StreamResult;
import org.w3c.dom.Document;

public final class XmlWriterRepository {
    private final DataSource dataSource;

    public XmlWriterRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void insert(long id, Document document) throws Exception {
        try (Connection connection = dataSource.getConnection()) {
            SQLXML value = connection.createSQLXML();
            try {
                StreamResult target = value.setResult(StreamResult.class);

                Transformer transform = XmlSecurity.safeTransformer();
                transform.transform(new DOMSource(document), target);

                if (target.getWriter() != null) target.getWriter().close();
                if (target.getOutputStream() != null) target.getOutputStream().close();

                String sql =
                        "INSERT INTO document_store (id, payload_xml) VALUES (?, ?)";
                try (PreparedStatement statement = connection.prepareStatement(sql)) {
                    statement.setLong(1, id);
                    statement.setSQLXML(2, value);
                    statement.executeUpdate();
                }
            } finally {
                value.free();
            }
        }
    }
}
~~~

**Mã minh họa class**, cần một `XmlSecurity.safeTransformer()` được implement theo phần bảo mật bên dưới, JDBC driver/DBMS/schema thật và xử lý lifecycle. Không có `main`; không phải ví dụ tự chạy độc lập. Trong app dùng transaction manager, không tự commit hoặc thay connection scope bất chấp framework.

**Thứ tự là quan trọng:** `createSQLXML()` → `setResult()` → **hoàn thành và đóng output streams** → `setSQLXML()` → `executeUpdate()` → `free()`. Nếu gọi `free` trước execute, đối tượng không còn hợp lệ. Một driver có thể chỉ phát hiện XML malformed khi `setSQLXML` hoặc `executeUpdate` chứ không nhất thiết lỗi ngay trong `setResult`.

**SQL type và driver:** `SQLXML` là mapping cho kiểu SQL XML; không phải mọi database/driver hỗ trợ `Connection.createSQLXML` hoặc việc bind cột XML giống nhau. PostgreSQL có XML type và driver mappings riêng; SQL Server có `xml` type; các DBMS khác có naming/capabilities khác. Cần kiểm tra `DatabaseMetaData`, driver version, SQL column type, feature support và integration test.

Nếu `payload_xml` là SQL NULL, cách bind rõ nghĩa theo schema là:

~~~java
statement.setNull(2, java.sql.Types.SQLXML);
~~~

Đây là đoạn minh họa với `statement` có parameter thứ hai là SQL XML type. **Không** dùng `connection.createSQLXML()` rỗng rồi cho rằng nó tương đương SQL NULL: XML chưa được gán giá trị có thể gây lỗi hoặc trạng thái không hợp lệ. Với application dùng cột dạng VARCHAR/CLOB chứa XML text thay vì kiểu SQL XML, mapping/SQL type khác và có thể không hỗ trợ `SQLXML`.

## 7. Vòng đời và state machine của `SQLXML` — phần dễ sai nhất

Javadoc Java SE 25 mô tả **đọc và ghi nội dung XML tối đa một lần** trên một instance SQLXML. Trạng thái khái niệm:

~~~text
SQLXML from ResultSet: READABLE
      |
      +-- getSource() / getString() / getCharacterStream() / getBinaryStream()
      |          |
      |          v
      |      NOT READABLE
      |          |
      |          +--> free() --> FREED
      |
      +-- free() --> FREED

SQLXML from Connection.createSQLXML(): WRITABLE
      |
      +-- setResult() / setString() / setCharacterStream() / setBinaryStream()
      |          |
      |          v
      |      NOT WRITABLE (điền nốt Result/stream đã nhận)
      |          |
      |          +--> setSQLXML + execute
      |          +--> free() --> FREED
      |
      +-- free() --> FREED
~~~

Một lần gọi getter làm object **not readable**; implementation có thể đồng thời làm nó **not writable**. Một lần gọi setter làm object **not writable**; implementation có thể đồng thời làm nó **not readable**. `free()` giải phóng tài nguyên và làm object **không đọc/ghi được**. Gọi `free()` nhiều lần là **no-op** theo contract, nhưng sau free mà gọi những method khác thì ném `SQLException`.

| Phép thao tác | Đúng/sai |
| --- | --- |
| `xml.getSource(DOMSource.class)` đúng một lần | Hợp lệ nếu SQLXML readable |
| Gọi `xml.getString()` **sau** `getSource()` | **Không hợp lệ theo trạng thái read-once** |
| `xml.getSource(DOMSource.class)` rồi `getSource(StreamSource.class)` | **Không hợp lệ**, cần XML object khác |
| `writable.setResult(StreamResult.class)` một lần, ghi vào Result vừa nhận | Cách ghi hợp lệ |
| `writable.setResult(DOMResult.class)` lần hai | **Không hợp lệ**, writable state đã bị dùng |
| `writable.getString()` để “kiểm tra” sau `setResult` | **Không portable** và có thể sai state; test ở lớp riêng |
| `xml.free()` khi xong | Giải phóng tài nguyên, nên gọi trong `finally` |
| Đọc `xml.getSource` sau `free()` | `SQLException` |
| Đọc/gửi SQLXML sau khi connection/transaction đã kết thúc | Không bảo đảm, object có thể là logical pointer tới DB |
| Chia sẻ cùng SQLXML cho nhiều threads | Không phù hợp mô hình one-shot; cần quản lý ownership |

**`SQLXML` không implement `AutoCloseable`.** Do đó không được đặt nó vào try-with-resources như `Connection`; hãy dùng `try/finally` và `free()`. Streams/Readers/Writers do SQLXML cung cấp lại **có thể là AutoCloseable** và cần được đóng theo ownership, nhất là trước JDBC `execute()`.

SQLXML thông thường chỉ hợp lệ trong **thời gian transaction** tạo ra nó; Javadoc nêu driver thường lưu con trỏ logic tới XML hơn là copy dữ liệu. Đừng cache SQLXML vào singleton, lưu vào HTTP session, return qua boundary khi connection đóng, hoặc xử lý stream sau khi commit mà không xác minh driver. Nếu cần dữ liệu sống lâu, materialize nội dung **an toàn và có giới hạn kích thước** trong phạm vi connection/transaction rồi chuyển thành DTO.

## 8. Chương trình Java 17+ chạy độc lập: mô phỏng `getSource` và `setResult`

Để chứng minh **JAXP integration** mà không buộc người học cài database, chương trình này dùng một lớp `MemorySqlXml` implement `java.sql.SQLXML` theo **một tập con có chủ đích** của API:

- `getSource(DOMSource.class)` phân tích XML bằng một `DocumentBuilderFactory` đã khóa external access và trả `DOMSource`.
- `getSource(StreamSource.class)` trả `StreamSource` từ `StringReader`; caller tự điều khiển **secure parser**.
- `setResult(StreamResult.class)` trả `StreamResult` có writer trong bộ nhớ; JAXP identity transformer serialize DOM vào đó.
- `MemorySqlXml` thực thi trạng thái one-shot và `free()`. Những API chưa được mô phỏng ném `SQLFeatureNotSupportedException`.
- Kiểm thử Unicode, XML escaping, DOM root, read-once/write-once, invalidation sau free và từ chối một XML có DTD external entity.

**Không có database, JDBC driver, SQL INSERT hoặc server.** Kết quả là kiểm thử Java XML/JDBC-interface contract; nó **không** khẳng định driver thật sẽ trả đúng loại DOM node, hỗ trợ mọi Source/Result bằng cùng cách nội bộ, hay áp dụng security policy của fake.

Tạo file **`SqlXmlJaxpDemo.java`** với mã đầy đủ:

~~~java
import java.io.InputStream;
import java.io.OutputStream;
import java.io.Reader;
import java.io.StringReader;
import java.io.StringWriter;
import java.io.Writer;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;
import java.sql.SQLXML;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.transform.Result;
import javax.xml.transform.Source;
import javax.xml.transform.Transformer;
import javax.xml.transform.TransformerFactory;
import javax.xml.transform.OutputKeys;
import javax.xml.transform.dom.DOMSource;
import javax.xml.transform.stream.StreamResult;
import javax.xml.transform.stream.StreamSource;
import org.w3c.dom.Document;
import org.xml.sax.InputSource;
import org.xml.sax.SAXException;
import org.xml.sax.SAXParseException;
import org.xml.sax.helpers.DefaultHandler;

public final class SqlXmlJaxpDemo {
    static Document parseSafely(Reader source) throws Exception {
        DocumentBuilderFactory factory = DocumentBuilderFactory.newDefaultNSInstance();
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        factory.setXIncludeAware(false);
        factory.setExpandEntityReferences(false);
        DocumentBuilder builder = factory.newDocumentBuilder();
        builder.setErrorHandler(new DefaultHandler() {
            @Override public void fatalError(SAXParseException e) throws SAXException {
                throw e;
            }
        });
        return builder.parse(new InputSource(source));
    }

    static Transformer identityTransformer() throws Exception {
        TransformerFactory factory = TransformerFactory.newDefaultInstance();
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_STYLESHEET, "");
        Transformer transformer = factory.newTransformer();
        transformer.setOutputProperty(OutputKeys.OMIT_XML_DECLARATION, "yes");
        return transformer;
    }

    static final class MemorySqlXml implements SQLXML {
        private final String input;
        private StringWriter output;
        private boolean used;
        private boolean freed;

        MemorySqlXml(String xml) { this.input = xml; }
        MemorySqlXml() { this(null); }

        private void require(boolean correctMode) throws SQLException {
            if (freed || used || !correctMode)
                throw new SQLException("SQLXML not in the required state");
            used = true;
        }

        @Override public <T extends Source> T getSource(Class<T> type)
                throws SQLException {
            if (type != DOMSource.class && type != StreamSource.class)
                throw new SQLFeatureNotSupportedException("Demo supports DOM/Stream only");
            require(input != null);
            try {
                if (type == DOMSource.class) {
                    try (StringReader reader = new StringReader(input)) {
                        return type.cast(new DOMSource(parseSafely(reader)));
                    }
                }
                return type.cast(new StreamSource(new StringReader(input)));
            } catch (Exception e) {
                throw new SQLException("Invalid XML", e);
            }
        }

        @Override public <T extends Result> T setResult(Class<T> type)
                throws SQLException {
            if (type != StreamResult.class)
                throw new SQLFeatureNotSupportedException("Demo supports StreamResult only");
            require(input == null);
            output = new StringWriter();
            return type.cast(new StreamResult(output));
        }

        String demoSnapshot() throws SQLException {
            if (freed || output == null)
                throw new SQLException("No writable XML or already freed");
            return output.toString();
        }

        @Override public void free() { freed = true; output = null; }
        @Override public InputStream getBinaryStream() throws SQLException {
            throw new SQLFeatureNotSupportedException();
        }
        @Override public OutputStream setBinaryStream() throws SQLException {
            throw new SQLFeatureNotSupportedException();
        }
        @Override public Reader getCharacterStream() throws SQLException {
            throw new SQLFeatureNotSupportedException();
        }
        @Override public Writer setCharacterStream() throws SQLException {
            throw new SQLFeatureNotSupportedException();
        }
        @Override public String getString() throws SQLException {
            throw new SQLFeatureNotSupportedException();
        }
        @Override public void setString(String value) throws SQLException {
            throw new SQLFeatureNotSupportedException();
        }
    }

    public static void main(String[] args) throws Exception {
        String xml = "<note lang=\"vi\">Ti\u1EBFng Vi\u1EC7t &amp; \uD83D\uDE00</note>";
        Document document;

        MemorySqlXml readable = new MemorySqlXml(xml);
        try {
            DOMSource source = readable.getSource(DOMSource.class);
            document = (Document) source.getNode();
            System.out.println("DOM root: " + document.getDocumentElement().getTagName());
            System.out.println("DOM attribute: " + document.getDocumentElement().getAttribute("lang"));
            System.out.println("DOM Unicode text exact: "
                    + "Ti\u1EBFng Vi\u1EC7t & \uD83D\uDE00".equals(
                            document.getDocumentElement().getTextContent()));
            boolean secondReadRejected = false;
            try {
                readable.getSource(StreamSource.class);
            } catch (SQLException e) {
                secondReadRejected = true;
            }
            System.out.println("second read rejected: " + secondReadRejected);
        } finally {
            readable.free();
        }

        MemorySqlXml streamSqlXml = new MemorySqlXml(xml);
        try {
            StreamSource source = streamSqlXml.getSource(StreamSource.class);
            try (Reader reader = source.getReader()) {
                Document parsed = parseSafely(reader);
                System.out.println("StreamSource root: "
                        + parsed.getDocumentElement().getTagName());
            }
        } finally {
            streamSqlXml.free();
        }

        MemorySqlXml writable = new MemorySqlXml();
        try {
            StreamResult result = writable.setResult(StreamResult.class);
            identityTransformer().transform(new DOMSource(document), result);
            if (result.getWriter() != null) result.getWriter().close();
            String serialized = writable.demoSnapshot();
            System.out.println("StreamResult escaped ampersand: "
                    + serialized.contains("&amp;"));
            try (StringReader reader = new StringReader(serialized)) {
                System.out.println("StreamResult parsed root: "
                        + parseSafely(reader).getDocumentElement().getTagName());
            }

            boolean secondWriteRejected = false;
            try {
                writable.setResult(StreamResult.class);
            } catch (SQLException e) {
                secondWriteRejected = true;
            }
            System.out.println("second write rejected: " + secondWriteRejected);
        } finally {
            writable.free();
        }

        boolean freeInvalidated = false;
        try {
            writable.setResult(StreamResult.class);
        } catch (SQLException e) {
            freeInvalidated = true;
        }
        System.out.println("free invalidates: " + freeInvalidated);

        String dangerous = "<!DOCTYPE note [<!ENTITY xxe SYSTEM "
                + "\"file:///blocked.txt\">]><note>&xxe;</note>";
        boolean doctypeRejected = false;
        try (StringReader reader = new StringReader(dangerous)) {
            parseSafely(reader);
        } catch (SAXException e) {
            doctypeRejected = true;
        }
        System.out.println("DOCTYPE blocked: " + doctypeRejected);
    }
}
~~~

Biên dịch và chạy trong thư mục chứa file với JDK 17 trở lên:

~~~bash
javac --release 17 SqlXmlJaxpDemo.java
java SqlXmlJaxpDemo
~~~

**Stdout chính xác** đã kiểm thử trên **OpenJDK 24.0.2**, dùng `javac --release 17`:

~~~text
DOM root: note
DOM attribute: vi
DOM Unicode text exact: true
second read rejected: true
StreamSource root: note
StreamResult escaped ampersand: true
StreamResult parsed root: note
second write rejected: true
free invalidates: true
DOCTYPE blocked: true
~~~

### Giải thích từng phần quan trọng

1. `new MemorySqlXml(xml)` là **SQLXML giả lập ở trạng thái đọc được**. Nó tự bảo vệ DOM parse bằng JAXP settings. Driver thật có thể dùng parser/streaming path khác.
2. `getSource(DOMSource.class)` trả DOM tree, root `note` có attribute `lang="vi"`. Text thực đọc là `Tiếng Việt & 😀`; entity `&amp;` đã được parse thành `&`. Console chỉ in boolean để tránh phụ thuộc encoding hiển thị của terminal.
3. Thử `getSource(StreamSource.class)` lần hai trên **cùng** object bị từ chối, minh họa trạng thái read-once.
4. Một `MemorySqlXml` **khác** tạo `StreamSource` với Reader. Ứng dụng gọi `parseSafely(reader)`, chứng minh có thể cấu hình parser **trước** khi xử lý XML raw stream. `StreamSource` do driver thật cấp có thể không luôn chứa Reader.
5. `new MemorySqlXml()` ở trạng thái ghi được; `setResult(StreamResult.class)` trả writer đích. JAXP identity transformer ghi DOM vào writer.
6. XML serializer escape dấu `&` trong text thành `&amp;`: kiểm tra theo **XML semantics** thay vì so sánh bytes trước/sau transform. Serializer có thể thêm/bỏ XML declaration, đổi thứ tự attributes hoặc cách escape mà nội dung XML vẫn tương đương.
7. `demoSnapshot()` là **method chỉ tồn tại trong fake**, không phải method chuẩn của interface `SQLXML`. Nó giúp bài kiểm tra nội dung đã ghi mà **không vi phạm one-shot SQLXML contract** bằng cách gọi `getString()` trên object vừa `setResult`.
8. Lần thứ hai gọi `setResult` bị từ chối; sau `free()`, mọi API tiếp tục thao tác XML bị từ chối theo mô phỏng. Driver thật có thêm chi tiết lỗi/sqlstate riêng.
9. XML có `DOCTYPE` chứa external entity bị parser do ứng dụng cấu hình từ chối, trước khi có bất kỳ truy cập tài nguyên ngoài nào. **Không suy diễn** rằng mọi `getSource(DOMSource.class)` của mọi driver sẽ tự động áp chính sách này.

### Vì sao giả lập chứ không “viết một JDBC driver XML”?

Một JDBC driver thật cần hỗ trợ connection, prepareStatement, result metadata, SQL type mappings, DB wire protocol, transaction và nhiều method khác. Bài này chỉ kiểm tra hai API đích là `getSource`/`setResult` cùng các thành phần JAXP. Muốn chứng minh driver thật, phải chạy **integration test** với DB hỗ trợ SQLXML.

## 9. Cấu hình JAXP an toàn: XXE, external DTD, XSLT và giới hạn tài nguyên

### 9.1. `FEATURE_SECURE_PROCESSING` chưa đủ nếu không xem external access

Oracle JAXP Security Guide (Java 25) hướng dẫn:

- Bật `XMLConstants.FEATURE_SECURE_PROCESSING` **tường minh** cho các factories như `DocumentBuilderFactory` và `TransformerFactory`.
- Đặt `XMLConstants.ACCESS_EXTERNAL_DTD`, `ACCESS_EXTERNAL_SCHEMA`, `ACCESS_EXTERNAL_STYLESHEET` thành chuỗi **`""`** khi không cho phép truy cập protocol nào.
- Khi nghiệp vụ không cần DTD, nên **từ chối DTD** hoàn toàn. Với DOM/SAX JDK parser có thể dùng feature `http://apache.org/xml/features/disallow-doctype-decl`.
- Đặt **resource/processing limits** cho kích thước tài liệu, entity expansion, độ sâu, số thuộc tính, XPath/XSLT complexity và thời gian xử lý.
- Với parser/Transformer không hỗ trợ security properties cần thiết, **fail closed**: không lặng lẽ bỏ qua lỗi cấu hình rồi parse dữ liệu untrusted.

Dù JDK có nhiều secure defaults, tài liệu nêu external connections **không nhất thiết bị cấm nếu chỉ dựa vào mặc định**. Cấu hình ở factory có hiệu lực rõ ràng hơn. Đồng thời có những tình huống resolver/catalog chủ động cung cấp tài nguyên mà external access property không chặn: phải kiểm soát **cả resolver**.

### 9.2. Tạo DOM parser có cấu hình an toàn

Trích từ phương thức `parseSafely` trong chương trình đã chạy:

~~~java
DocumentBuilderFactory factory = DocumentBuilderFactory.newDefaultNSInstance();
factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
factory.setXIncludeAware(false);
factory.setExpandEntityReferences(false);

DocumentBuilder builder = factory.newDocumentBuilder();
Document doc = builder.parse(new InputSource(reader));
~~~

Đây là **đoạn minh họa** trong method có `reader` và được phép ném checked exceptions; trong file demo hoàn chỉnh có error handler phù hợp để không in lỗi parser ra console không kiểm soát. `newDefaultNSInstance()` sử dụng builtin default implementation có namespace processing bật — hữu ích để tránh phụ thuộc JAXP provider tùy ý khi ứng dụng muốn built-in JDK parser (Java 17+).

**Lưu ý support:** feature disallow-doctype-decl dùng tên URI cụ thể và có thể không tồn tại trong **third-party parser**. Nếu factory ném `ParserConfigurationException` hoặc `IllegalArgumentException` khi thiết lập security property, không tiếp tục parse untrusted XML với parser không được cấu hình như yêu cầu.

**Đặc biệt:** cấu hình này chỉ bảo vệ khi **chính DocumentBuilder được cấu hình ấy thực sự parse dữ liệu**. Nếu `getSource(DOMSource.class)` đã parse trước, không thể gắn lại DocumentBuilder sau khi đã nhận `Document` để làm quá trình trước đó an toàn retroactively.

### 9.3. Transformer / XSLT an toàn

`TransformerFactory` có thể tạo identity transform `newTransformer()` hoặc XSLT transform `newTransformer(stylesheetSource)`. Khi dùng untrusted input/XSLT:

~~~java
TransformerFactory factory = TransformerFactory.newDefaultInstance();
factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_STYLESHEET, "");

Transformer transform = factory.newTransformer();
transform.transform(source, result);
~~~

Đây là đoạn minh họa, `source` và `result` có sẵn, cần import `TransformerFactory`, `Transformer`, `XMLConstants`; xử lý `TransformerException` và cấu hình không được hỗ trợ. `newTransformer()` **không có stylesheet** thực hiện identity transform. `newTransformer(new StreamSource(xsltReader))` mới là XSLT thực sự; phải kiểm soát nguồn stylesheet, `xsl:include`, `xsl:import`, hàm `document()` và extension functions.

**Bảo mật identity transform cũng quan trọng** khi `source` là `StreamSource` chưa parse: Transformer có thể cần parser nội bộ. Cài factory security settings **trước khi tạo transformer**; đối với môi trường có provider JAXP khác, kiểm thử cùng implementation production.

Nếu chấp nhận một URIResolver của ứng dụng, xem nó có truy cập file/network ngoài allowlist hay không. Restrict `ACCESS_EXTERNAL_STYLESHEET` **không tự phủ định dữ liệu do custom resolver chủ động trả về**.

### 9.4. SAX và StAX

DOM có cây và memory cost; SAX/StAX phù hợp luồng nhưng **không tự nhiên an toàn**:

- Với SAX, dùng `SAXParserFactory`/`XMLReader` đã cấu hình chống external entities và DTD; kiểm soát `EntityResolver` nếu có.
- Với StAX, sử dụng `XMLInputFactory.SUPPORT_DTD = false` và `XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES = false` khi không cần DTD/external references, cùng external access settings nếu provider hỗ trợ.
- **JAXP FEATURE_SECURE_PROCESSING không áp dụng cho StAX factory theo cùng cách DOM/SAX/Transformer**; phải dùng các thuộc tính đúng của StAX và EAP/resolver policy.
- XML source từ `SQLXML.getSource(StAXSource.class)` có thể chứa một stream reader **đã do driver tạo**; cấu hình một XMLInputFactory mới **sau đó không làm stream reader cũ an toàn**. Muốn kiểm soát đầy đủ, tự tạo StAX parser trên raw Reader/InputStream lấy được từ driver.

Mã minh họa tạo factory khi ứng dụng sở hữu parser:

~~~java
XMLInputFactory inputFactory = XMLInputFactory.newFactory();
inputFactory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
inputFactory.setProperty(
        XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
XMLStreamReader xmlReader = inputFactory.createXMLStreamReader(reader);
try {
    while (xmlReader.hasNext()) {
        xmlReader.next();
        // Giới hạn số events, depth, text length theo policy.
    }
} finally {
    xmlReader.close();
}
~~~

Đoạn này cần `reader`, imports `javax.xml.stream.*` và xử lý `XMLStreamException`. Một số StAX providers có hỗ trợ property khác nhau; test/fail closed khi không thể cấm DTD/external access và thêm input size/depth limits. Không coi việc `hasNext()` chạy được là XML đã được validate an toàn.

### 9.5. Source/Result kiểu DOM vẫn có thể mang dữ liệu không tin cậy

Nếu ứng dụng nhận `Document` từ một nguồn khác, parser của nguồn ấy có thể đã xử lý external entities hoặc khai triển tài liệu từ trước. `DOMSource(document)` không tự “khử độc” dữ liệu. Trước khi đưa vào XSLT/XPath hoặc lưu SQLXML, cần có trust model, kiểm tra doctype/schema/cấu trúc và giới hạn tài nguyên. Đừng cố chèn một XSLT stylesheet không tin cậy vào `newTransformer(stylesheet)` rồi kỳ vọng FSP là sandbox hoàn chỉnh.

## 10. XSLT, XPath và namespaces: kết hợp `getSource` đúng cách

### XPath với DOM

`DOMSource` thường hữu ích để chạy XPath:

~~~java
DOMSource dom = sqlxml.getSource(DOMSource.class);
Document doc = (Document) dom.getNode();

XPathFactory factory = XPathFactory.newDefaultInstance();
factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
XPath xpath = factory.newXPath();

String title = xpath.evaluate("/note/title/text()", doc);
~~~

Đây là đoạn **minh họa trong method**, cần `sqlxml` còn readable, imports DOM/JAXP và checked exceptions; nên dùng document đã parse an toàn. **Không** đưa XPath expression tạo từ input user bằng cách nối text mù quáng, vì có thể gây sai semantics hoặc XPath injection. Dữ liệu nghiệp vụ cần được truyền bằng cách an toàn (ví dụ XPathVariableResolver) nếu cho phép dynamic filtering.

Với XML namespaces:

~~~xml
<n:note xmlns:n="urn:demo:notes">
  <n:title>Xin chào</n:title>
</n:note>
~~~

XPath `/note/title` sẽ **không** khớp nếu document sử dụng namespace. Cần `NamespaceContext` ánh xạ prefix trong **expression** đến URI `urn:demo:notes`, ví dụ `/n:note/n:title`. Namespace prefix trong expression có thể khác prefix literal trong XML, miễn cùng namespace URI. Cấu hình DOM parser namespace-aware trước khi parse; `DOMSource` do driver tạo có thể namespace processing bật theo Javadoc nhưng vẫn cần kiểm thử driver.

### XSLT với `Source`/`Result`

Với một stylesheet đã review và được load qua nguồn an toàn:

~~~java
TransformerFactory transformerFactory = TransformerFactory.newDefaultInstance();
transformerFactory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
transformerFactory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
transformerFactory.setAttribute(XMLConstants.ACCESS_EXTERNAL_STYLESHEET, "");

Transformer xslt = transformerFactory.newTransformer(
        new StreamSource(trustedStylesheetReader));
xslt.transform(sqlxml.getSource(StreamSource.class), outputResult);
~~~

Đoạn này **minh họa trong method**, `trustedStylesheetReader` và `outputResult` phải tồn tại, `SQLXML sqlxml` còn readable và phải được `free()` đúng lúc; phải đóng input/output streams theo ownership. Đây là **XSLT thực sự**, khác với `newTransformer()` identity transform. Khi document có systemId/URI references, không mặc định XPath/XSLT không truy cập ngoại mạng; security settings và resolver policy phải được kiểm tra.

### Schema validation

`SchemaFactory` và `Validator` là phần của JAXP, nhưng không phải hai method trực tiếp trên `SQLXML`. Nếu business đòi XML tuân thủ XSD, hãy cấu hình `SchemaFactory` với `ACCESS_EXTERNAL_DTD=""`, `ACCESS_EXTERNAL_SCHEMA=""` và secure processing/limits, nạp schema **từ nguồn tin cậy**, tạo `Validator` và validate một `Source` phù hợp.

Schema invalid **khác** XML không well-formed. Một document có XML syntax đúng vẫn có thể sai XSD, thiếu required elements hoặc vi phạm business rules. Không coi `setResult` hay `Transformer.transform` là đã validate XML theo schema; nó chỉ ghi/chuyển representation, trừ khi bạn đã gọi một bước validator rõ ràng.

## 11. Source/Result nào nên chọn?

| Yêu cầu | Lựa chọn gợi ý | Lưu ý |
| --- | --- | --- |
| Cần đọc/cập nhật nhiều node hoặc XPath | `DOMSource` và `DOMResult` | Có thể tạo toàn cây DOM, tốn RAM; bảo đảm parser trust |
| Xử lý tuần tự XML rất lớn | `SAXSource`, `StAXSource` hoặc `StreamSource` | Tránh giữ DOM; kiểm soát stream lifecycle/depth/limits |
| Xuất tài liệu từ DOM hiện có | `StreamResult` nhận `Writer/OutputStream` do driver cấp | Transformer serialization, close trước execute |
| Ghi DOM node vào SQLXML | `DOMResult` | Driver semantics của result node cần test |
| SAX events được producer phát ra | `SAXResult` | Handler lifecycle, well-formed events |
| Producer dùng `XMLStreamWriter` | `StAXResult` | Complete document, flush/close đúng kiểu writer |
| XSLT chuyển cấu trúc | `Source` bất kỳ → JAXP `Transformer` → `Result` | Restrict stylesheet/external access |
| Đọc raw text kiểm soát parser | `getCharacterStream` hoặc `StreamSource` có Reader | Một lần đọc, parse bằng factory đã harden |
| XML đơn giản vài KB, không xử lý cấu trúc | `getString` hoặc `setString` | Không tạo transformer không cần thiết; vẫn validate/security |
| Cột là XML nhưng database/driver không hỗ trợ SQLXML | Vendor XML APIs hoặc text mapping đã kiểm chứng | Không ép `SQLXML` khi `SQLFeatureNotSupportedException` |

Đây là **hướng lựa chọn**, không phải cam kết performance. Đo với dữ liệu thật: một tài liệu 100 MB có thể làm DOM chiếm nhiều hơn rất nhiều bộ nhớ; Stream API chỉ tiết kiệm nếu toàn pipeline (driver, parser, output) thực sự stream.

### Encoding và XML declaration

JDBC `SQLXML.getCharacterStream`/`setCharacterStream` trao đổi Java characters (Unicode) qua `Reader`/`Writer`. Với **binary streams**, XML encoding declaration/BOM và XML 1.0 rules có liên quan. Không đổi `Reader` thành bytes `UTF-8` tùy tiện rồi gắn một XML declaration `encoding="UTF-16"` không đúng thực tế.

`Transformer` có `OutputKeys.ENCODING`, `OMIT_XML_DECLARATION`, `INDENT`; serializer/driver có thể tạo một representation khác về spacing, quote style, entity escape hoặc XML declaration mà nội dung XML tương đương. Vì vậy kiểm thử round-trip nên so **cấu trúc XML/namespace/text**, không chỉ so raw strings byte-for-byte. Nếu nghiệp vụ đòi **XML canonicalization** để ký số, dùng thuật toán canonical XML/certificate/signature riêng; identity transform **không đồng nghĩa canonicalization**.

## 12. Lỗi JDBC/JAXP nên bắt và xử lý thế nào?

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `Connection.createSQLXML()` ném lỗi | Driver/database không hỗ trợ SQLXML hoặc connection invalid | Kiểm tra driver/version, metadata và SQL type |
| `getSource(DOMSource.class)` ném `SQLException` | XML malformed, state đã read, driver parsing error | Không đọc lần hai; kiểm tra cause/SQLState và nguồn XML |
| `getSource` không hỗ trợ loại muốn dùng | Driver chưa đủ tính năng hoặc mapping khác | Kiểm tra Javadoc/driver, thử đường API mà vendor hỗ trợ |
| `setResult` lần hai thất bại | One-shot writable state | Tạo SQLXML mới cho một lần ghi mới |
| `getString` sau `getSource` thất bại | One-shot readable state | Đọc qua Source đã nhận, không gọi getter khác |
| `SQLXML` dùng sau `free` ném `SQLException` | Đã giải phóng | Chỉ gọi `free` sau cùng |
| SQLXML đọc sau transaction kết thúc | Driver giữ logical pointer | Materialize trong transaction, không trả SQLXML qua boundary |
| `ResultSet.getSQLXML` trả `null` | Cột là SQL NULL | Xử lý null riêng, không gọi `getSource` trên null |
| `StreamResult.getWriter() == null` | Driver cấp output stream/systemId thay vì writer | Kiểm tra output target thực tế; không tự giả định |
| `StreamSource.getReader() == null` | Driver cấp InputStream/systemId | Chọn parser hợp lệ, kiểm soát external access và encoding |
| Parser ném `SAXParseException` | XML không well-formed/DTD bị cấm/limits | Trả lỗi validation an toàn, không log toàn bộ payload |
| XSLT ném `TransformerException` | Stylesheet lỗi, external access bị chặn hoặc input sai | Kiểm tra trusted stylesheet, error listener, giới hạn tài nguyên |
| `XMLStreamException` | DTD/namespace/stream lỗi | Cấu hình StAX, đóng reader/stream |
| XML có `DOCTYPE` làm request outbound | XXE/SSRF do parser chưa khóa | Cấu hình parser **trước parse**, block DTD/external access |
| XML có nhiều nested entities gây OOM | Entity expansion/large input | Kích thước tối đa, FSP, entity/depth/attribute limits |
| XML text khác raw sau transform | Serializer whitespace/escaping/encoding | So semantics; nếu cần canonical XML dùng quy trình riêng |
| XML in DB có nội dung sai | Schema/type/driver conversion | Integration test; kiểm tra SQLXML hỗ trợ thật |

**Exception boundaries:** JDBC thao tác thường ném `SQLException` (bao gồm `SQLFeatureNotSupportedException`); JAXP parser/transformer có thể ném `ParserConfigurationException`, `SAXException`, `TransformerException`, `XMLStreamException` và `IOException`. Không catch tất cả rồi trả `null` hoặc XML rỗng: lỗi parse khác SQL NULL/không có row, phải được phân biệt trong application result type.

### Không log XML payload bừa bãi

XML có thể chứa tên, địa chỉ, token, số tài khoản hoặc dữ liệu y tế. Khi parser lỗi, log **loại lỗi, correlation ID, schema version và vị trí dòng/cột khi an toàn**, không in toàn bộ XML, credential hoặc URI có secret. Với untrusted XML, hạn chế log một chuỗi lỗi có thể chứa URL file nội bộ từ XML entity.

## 13. Các rủi ro bảo mật và giới hạn tài nguyên cần kiểm thử

Một pipeline an toàn nên kiểm tra ít nhất:

1. **XXE file read:** input có `<!ENTITY xxe SYSTEM "file:///...">` phải bị từ chối khi policy không cần DTD.
2. **SSRF external entity:** URL `http://127.0.0.1/...` hoặc URL metadata service không được parser liên hệ.
3. **XML entity expansion bomb:** nested entities phải bị chặn hoặc giới hạn, không khiến JVM dùng quá nhiều RAM/CPU.
4. **DTD không cần thiết:** reject `DOCTYPE` trước expansion; không rely chỉ vào `setExpandEntityReferences(false)`.
5. **External XSLT includes/imports:** cấm protocol ngoài khi stylesheet không tin cậy; kiểm soát `URIResolver`.
6. **XSD schema imports:** cấm external schema retrieval hoặc allowlist/local catalog được quản lý.
7. **StAX parser:** `SUPPORT_DTD=false`, external entities off, limits trên event count và max depth.
8. **JDBC driver parsing path:** nếu driver tạo DOM trước ứng dụng, kiểm tra vendor-specific secure parser settings hoặc thay bằng raw stream + hardened JAXP parser.
9. **Payload size:** đặt giới hạn byte/character count từ HTTP layer, database column size, JDBC stream và parser.
10. **Timeout/cancellation:** XML rất lớn có thể ảnh hưởng thread pool, request deadline và connection pool; không xử lý vô hạn.
11. **Namespace/XPath:** validate expected namespace URI và expression; không nối user text tùy ý vào XPath/XSLT.
12. **Result hoàn chỉnh:** producer phải ghi một XML document well-formed, đóng writer/stream trước JDBC execute.
13. **SQL security:** XML cũng là dữ liệu SQL; dùng `PreparedStatement.setSQLXML` thay vì nối nội dung XML vào SQL literal.
14. **Output security:** nếu XML được hiển thị trong trình duyệt, cần xử lý content type, escaping, CSP và script policy ở tầng web; JDBC SQLXML không tự chống XSS.
15. **Access control:** người có thể đọc tài liệu XML trong database phải được phân quyền theo tenant/record; việc XML parse thành công không cấp quyền truy cập.

Đặt global JAXP security properties có thể tác động thành phần khác trong JVM; ưu tiên cấu hình **tại factory/processors sở hữu bởi module** và triển khai ứng dụng có policy thống nhất. Không “tạm tắt” secure processing toàn JVM để một XML lỗi chạy qua.

## 14. Kiểm thử với JDBC driver/database thật

### Test matrix

| Trường hợp | Kỳ vọng |
| --- | --- |
| SQL NULL trong cột XML | `ResultSet.getSQLXML` trả null, không được gọi `getSource` |
| Tài liệu nhỏ well-formed | `getSource` trả một Source phù hợp, root/namespace/text đúng |
| Document có Unicode `Tiếng Việt 😀` | Round-trip giữ code points và XML text đúng |
| XML với `&amp;`/CDATA/entities nội bộ hợp lệ | Parse ra text đúng, serialize có thể khác bytes |
| DOMSource | Có thể lấy Document/Node và xử lý trong transaction |
| StreamSource | Có Reader/InputStream/systemId phù hợp driver; parser được cấu hình trước |
| SAXSource/StAXSource | API hỗ trợ, event sequence đúng, parser restrictions được kiểm thử |
| DOMResult | Bind/execute XML mới được driver chấp nhận |
| StreamResult | Ghi/đóng stream, `setSQLXML`/`executeUpdate` thành công |
| Gọi `getSource` lần hai | Thường ném SQLException theo read-once contract |
| Gọi `setResult` lần hai | Thường ném SQLException theo write-once contract |
| `free` sau khi hoàn tất | Không còn dùng lại được; free lặp no-op |
| XML chưa hoàn chỉnh | SQLException có thể xảy ra khi set hoặc execute |
| XML DOCTYPE/XXE | Bị từ chối theo policy, không truy cập ngoại mạng/files |
| DTD/XSLT payload lớn | Processing limits/resource governance hoạt động |
| SQLXML từ transaction đã đóng | App không phụ thuộc việc đọc sau khi kết thúc |
| Nhiều docs lớn đồng thời | Không làm tràn heap, connection pool hoặc thread limits |
| Một driver/version khác | Có integration tests để phát hiện differences |

Ví dụ SQL type giả định:

~~~sql
CREATE TABLE document_store (
    id BIGINT PRIMARY KEY,
    payload_xml XML
);
~~~

DDL này là **minh họa**, cần xác nhận database hỗ trợ `XML` type và cú pháp tương ứng. Không phải mọi DBMS có type SQL XML giống nhau; một số dùng text/CLOB, một số có XML native có validation/indexing riêng. Test phải chạy với schema/driver thật, không “pass” chỉ vì Java code biên dịch.

### Round-trip đúng cách

1. Tạo `SQLXML` qua `Connection.createSQLXML()`.
2. Ghi bằng **một** `setResult`, hoàn thành JAXP output và đóng streams.
3. Bind `setSQLXML`, execute trong transaction test và `free` đúng lúc.
4. SELECT lại row bằng **một SQLXML object mới** từ `ResultSet.getSQLXML`.
5. Đọc **một lần** qua `getSource` hoặc `getCharacterStream` và parser an toàn.
6. Assert root localName/namespace URI, attributes, text nodes, count, Unicode code points và schema validity, không chỉ XML raw string equality.
7. Validate SQL NULL khác XML root rỗng và row không tồn tại.
8. Cleanup rows, connection, result set và XML objects trong `finally` / try-with-resources.
9. Chạy test trên driver/JDK/DB version đang triển khai production.
10. Đo memory/latency cho DOM vs stream trên kích thước tài liệu thực tế.

### Performance measurement

Hãy so chi phí memory/CPU của:
- `getString` rồi parse DOM;
- `getCharacterStream` và hardened streaming parser;
- `getSource(DOMSource.class)`;
- `getSource(StAXSource.class)` hoặc `StreamSource.class`;
- `setResult(StreamResult.class)` với JAXP identity transform;
- `setResult(DOMResult.class)` khi đầu vào vốn đã là Document.

Không tuyên bố con đường Source/Result luôn **zero-copy**. Javadoc chỉ nói nó **có thể cải thiện hiệu suất**, vì database có thể có biểu diễn XML tối ưu; hiệu quả phụ thuộc driver. Khi input XML nhỏ vài KB, sự đơn giản và độ an toàn có thể quan trọng hơn vài microseconds.

## 15. Những hiểu lầm phổ biến

| Nhầm lẫn | Điều đúng |
| --- | --- |
| “SQLXML giống String, có thể getSource nhiều lần.” | SQLXML có one-shot readable state |
| “`getSource` trả ra Result để lưu XML.” | `getSource` đọc; `setResult` tạo destination để ghi |
| “`setResult` viết được nhiều tài liệu liên tiếp.” | Chỉ một lần chọn kênh ghi; tạo SQLXML mới cho dữ liệu khác |
| “Sau `setResult` gọi `getString` để verify luôn.” | Không portable; state có thể không cho đọc |
| “`SQLXML` implement AutoCloseable.” | Không; gọi `free()` trong `finally` |
| “`free` là commit XML vào DB.” | Không; ghi qua `setSQLXML + execute` |
| “Cứ đóng Connection là có thể dùng SQLXML về sau.” | SQLXML thường gắn với transaction/driver resource |
| “Nếu getSQLXML null thì XML root rỗng.” | SQL NULL khác một document well-formed `<note/>` |
| “`getSource(DOMSource.class)` chắc chắn an toàn trước XXE.” | Driver có thể parse trước khi app cấu hình security |
| “JAXP mặc định chặn tất cả external entities.” | Phải cấu hình và kiểm tra FSP/EAP/DTD policy |
| “FSP luôn làm StAX an toàn.” | StAX cần config riêng, FSP không áp dụng giống DOM/SAX |
| “`StreamSource.getReader` luôn tồn tại.” | Có thể có InputStream/systemId thay thế |
| “`StreamResult.getWriter` luôn tồn tại.” | Có thể là OutputStream hoặc systemId theo driver |
| “`DOMSource` không có rủi ro memory.” | DOM có thể tạo toàn cây XML lớn |
| “XSLT không bao giờ đọc URL.” | Stylesheet include/import và document() có thể truy cập resources |
| “Identity transform là canonical XML.” | Serializer có thể đổi whitespace/escaping; canonicalization là kỹ thuật khác |
| “Dùng SQLXML là khỏi cần PreparedStatement.” | Vẫn bind `setSQLXML`, không nối XML literal vào SQL |
| “Java 17 phải chuyển `javax.xml.transform` sang Jakarta.” | JAXP Java SE vẫn dùng `javax.xml.*` |
| “Cứ có kiểu XML thì mọi driver đều hỗ trợ getSource/setResult.” | Kiểm tra JDBC feature support/driver version |
| “XML well-formed nghĩa là schema và business rules đúng.” | Cần validation XSD/domain riêng |
| “Parser bị lỗi có thể đổi thành XML rỗng.” | Phải phân biệt lỗi với null/empty document |
| “Chỉ test fake là đủ.” | Fake không kiểm chứng DB encoding, SQL type, driver parsing và performance |

## 16. Câu hỏi tự kiểm tra

1. **`SQLXML.getSource` trả cái gì?** Một `Source` dùng làm đầu vào xử lý XML, có kiểu cụ thể do caller yêu cầu.
2. **`SQLXML.setResult` trả cái gì?** Một `Result` làm đích ghi dữ liệu XML vào SQLXML.
3. **Bốn Source classes phổ biến?** `DOMSource`, `SAXSource`, `StAXSource`, `StreamSource`.
4. **Bốn Result classes tương ứng?** `DOMResult`, `SAXResult`, `StAXResult`, `StreamResult`.
5. **`getSource(null)` có chắc trả DOMSource?** Không, vendor có thể chọn Source khác.
6. **Có thể gọi `getSource` và `getString` lần lượt trên cùng SQLXML?** Không theo read-once contract.
7. **Có thể gọi `setResult` hai lần trên cùng SQLXML?** Không theo write-once contract.
8. **`free()` có làm SQLXML trở thành AutoCloseable không?** Không; đó là method dọn riêng, cần `finally`.
9. **Khi dùng StreamResult để ghi DB, phải làm gì trước execute?** Hoàn thành transform, flush/close mọi output streams có liên quan.
10. **Nếu XML chỉ có `<note/>` thì đó có phải SQL NULL?** Không, đó là một XML document hợp lệ.
11. **Vì sao không thể coi DOMSource từ driver là XXE-safe tự động?** Driver có thể đã parse tài liệu trước khi app gắn parser security.
12. **JAXP chống XXE bằng gì?** Cấu hình parser/Transformer FSP, reject DTD khi không cần, restrict external DTD/schema/stylesheet, resource limits.
13. **Tại sao StAX cần policy riêng?** FSP không áp dụng như DOM/SAX, cần `SUPPORT_DTD`/external-entity settings và limits.
14. **`StreamSource.getReader()` luôn khác null?** Không, có thể dùng InputStream hoặc systemId.
15. **`TransformerFactory.newTransformer()` làm gì khi không có stylesheet?** Identity transform.
16. **Dùng XSLT thì cần phòng vấn đề nào?** External includes/imports, document(), resolvers, extension functions và resource limits.
17. **XPath với XML namespace cần gì?** Namespace-aware parse và NamespaceContext map prefix sang URI.
18. **Identity serialization có bảo đảm raw XML bytes không đổi?** Không; so XML structure, không so bytes nếu yêu cầu là semantic.
19. **Tại sao SQLXML không nên được cache sau transaction?** Nó có thể là logical DB pointer, valid trong transaction theo contract.
20. **Nếu database XML type không được driver hỗ trợ?** Kiểm tra metadata/vendor docs, chọn mapping được hỗ trợ và test DB thật; không ép SQLXML.
21. **Một fake SQLXML demo chứng minh được gì?** Hợp đồng Java/JAXP được mô phỏng; không chứng minh driver hoặc DB thật.
22. **Khi nào cần DOM so với SAX/StAX?** DOM cho truy cập/cập nhật cây; SAX/StAX cho xử lý tuần tự/streaming dữ liệu lớn.
23. **`SAXResult` nhận dữ liệu bằng gì?** ContentHandler SAX events, không phải XMLReader parse input.
24. **`StAXResult` có thể chứa writer nào?** `XMLStreamWriter` hoặc `XMLEventWriter`, tùy implementation.
25. **Nếu XSD validation thành công, business validation đã đủ chưa?** Chưa; cần domain rules và security policy.
26. **Đâu là ranh giới tài nguyên đúng khi ghi SQLXML?** Tạo/gán/execute/free trong transaction và đóng streams theo driver contract.

## 17. Tham khảo chính thức và hiện hành

- [Java SE 25 — java.sql.SQLXML](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/SQLXML.html): state read/write once, `getSource`, `setResult`, `getString`, `free`, supported Source/Result classes.
- [Java SE 25 — java.sql.Connection](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/Connection.html): `createSQLXML` và quản lý Connection.
- [Java SE 25 — java.sql.ResultSet](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/ResultSet.html): `getSQLXML`, SQL NULL handling.
- [Java SE 25 — java.sql.PreparedStatement](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/PreparedStatement.html): `setSQLXML`, `setNull`, parameter binding.
- [Java SE 25 — javax.xml.transform.TransformerFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/transform/TransformerFactory.html): `newTransformer`/`newTemplates`, identity transformation, FSP, external access.
- [Java SE 25 — javax.xml.parsers.DocumentBuilderFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/parsers/DocumentBuilderFactory.html): secure DOM parser configuration, namespace processing.
- [Java SE 25 — javax.xml.stream.XMLInputFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/stream/XMLInputFactory.html): StAX parser properties, DTD and external-entity handling.
- [Java SE 25 — javax.xml.XMLConstants](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/XMLConstants.html): secure-processing và các ACCESS_EXTERNAL properties.
- [Java SE 25 — JAXP Security Guide](https://docs.oracle.com/en/java/javase/25/security/java-api-xml-processing-jaxp-security-guide.html): FSP, EAP, DTD restrictions, parser limits, resolver/catalog và các khuyến nghị hiện hành.
- [Java SE 25 — javax.xml.xpath.XPathFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/xpath/XPathFactory.html): XPath engine và secure-processing.
- [JDBC Driver for SQL Server — SQLXML Interface](https://learn.microsoft.com/en-us/sql/connect/jdbc/sqlxml-interface): ví dụ một vendor triển khai SQLXML và trạng thái XML objects; luôn đối chiếu driver đang dùng.

**Ghi nhớ:** `SQLXML.getSource` mở một kênh **đọc một lần** vào JAXP; `SQLXML.setResult` mở một kênh **ghi một lần** từ JAXP. Chọn DOM/SAX/StAX/Stream theo yêu cầu, bảo đảm hoàn thành streams trước JDBC execute, `free()` trong vòng đời transaction, và cấu hình XML security **trước parse/transform thật sự**. Với XML không tin cậy, không mặc định parser do JDBC driver tạo là an toàn; ưu tiên đường raw stream với JAXP factory đã harden hoặc chứng minh driver security bằng integration test.