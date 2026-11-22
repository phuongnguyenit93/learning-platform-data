# SQLXML và ánh xạ cột XML trong JDBC (Java 17+)

## 1. Bài toán và mục tiêu

Một cơ sở dữ liệu quan hệ có thể lưu dữ liệu XML có cấu trúc: hóa đơn, thông điệp trao đổi với hệ thống khác, cấu hình, biểu mẫu, tài liệu nghiệp vụ hoặc metadata. Khi DBMS hỗ trợ kiểu SQL `XML`, JDBC cung cấp **`java.sql.SQLXML`** để ánh xạ giữa giá trị **cột XML trong database** và các API xử lý XML của Java.

Ví dụ ý tưởng:

```text
SQL column có kiểu XML
          |
          | ResultSet.getSQLXML("payload")
          v
      java.sql.SQLXML
          |
          +-- getString()           -> chuỗi XML
          +-- getCharacterStream()  -> Reader
          +-- getBinaryStream()     -> InputStream
          +-- getSource(...)        -> DOM/SAX/StAX/Stream Source

Java tạo giá trị để ghi:
Connection.createSQLXML()
          |
          +-- setString(xmlText)
          +-- setCharacterStream() -> Writer
          +-- setBinaryStream()    -> OutputStream
          +-- setResult(...)       -> DOM/SAX/StAX/Stream Result
          |
PreparedStatement.setSQLXML(index, value)
          |
          v
      SQL XML column
```

`SQLXML` là một **interface trong module `java.sql`**, không phải class tiện ích tự xây bằng `new SQLXML()`. Nó giúp JDBC driver chuyển dữ liệu XML qua các biểu diễn khác nhau. **Sự hỗ trợ thực tế phụ thuộc JDBC driver, database version và loại cột.** Một số hệ thống dùng loại cột XML riêng, hệ thống khác chỉ có text/CLOB/JSON. Không giả định mọi DBMS chấp nhận cùng một câu `CREATE TABLE ... XML`.

Sau bài, bạn sẽ hiểu:
1. Quan hệ giữa SQL `XML`, `java.sql.Types.SQLXML` và `java.sql.SQLXML`.
2. Cách tạo, bind, đọc và giải phóng đối tượng SQLXML.
3. Vì sao **đọc/ghi XML mỗi SQLXML instance tối đa một lần** theo hợp đồng API.
4. Khi nào dùng `String`, character/binary streams, `Source` hoặc `Result`; cách kết hợp DOM, SAX, StAX.
5. Vòng đời transaction, SQL NULL, driver support, updatable ResultSet và tài nguyên lớn.
6. Các rủi ro XXE, SSRF, entity expansion và cách cấu hình parser Java 17+ an toàn.
7. Ví dụ Java 17+ độc lập đã chạy kiểm chứng, cùng chương trình JDBC tích hợp đã biên dịch.

**Special Note:** chỉ sử dụng kiến thức và API còn được hỗ trợ hiện nay. Toàn bộ ví dụ dựa vào Java 17+; không dùng JAXB như thư viện tự có sẵn trong JDK mới, không hướng dẫn XML parser mở external entities mặc định.

## 2. SQL XML, JDBC SQLXML và XML text có gì khác?

| Thành phần | Vai trò | Chú ý |
| --- | --- | --- |
| Kiểu cột SQL `XML` | Một kiểu dữ liệu SQL nhằm biểu diễn giá trị XML. | DDL, kiểm tra hợp lệ, lưu trữ và truy vấn XML là **vendor-specific**. |
| `Types.SQLXML` | Hằng JDBC type code trong `java.sql.Types`. | Không đồng nghĩa rằng mọi DBMS tự có cột tên `SQLXML`. |
| `java.sql.SQLXML` | Interface ánh xạ giá trị SQL XML trong Java. | Đối tượng gắn với connection/transaction, cần `free()`. |
| `Connection.createSQLXML()` | Tạo SQLXML rỗng để ứng dụng ghi XML. | Có thể ném `SQLFeatureNotSupportedException`. |
| `PreparedStatement.setSQLXML` | Bind giá trị SQLXML vào tham số SQL. | Parameter index bắt đầu từ **1**. |
| `ResultSet.getSQLXML` | Lấy cột XML thành đối tượng SQLXML. | Trả `null` nếu giá trị SQL NULL; driver có thể không hỗ trợ. |
| `getString()/setString()` | Đọc/ghi XML serialization bằng chuỗi Java. | Với XML lớn, có chi phí materialize chuỗi. |
| `getSource()/setResult()` | Trao đổi XML thông qua JAXP Source/Result. | Cần phân biệt parser/transformer bảo mật và tài nguyên. |

Ví dụ DDL mang tính **minh họa** cho DBMS có SQL XML type:

```sql
CREATE TABLE xml_documents (
    id BIGINT PRIMARY KEY,
    payload XML
);
```

Đây **không phải DDL portable**: cách định nghĩa cột XML trong Oracle, PostgreSQL, SQL Server, các DBMS khác có thể khác hoặc thậm chí không có native XML column. Trước khi triển khai, đọc tài liệu DBMS và kiểm tra JDBC driver. **Không dùng cột `VARCHAR/CLOB` và `getSQLXML` một cách mặc định** nếu driver không công bố mapping đó; hãy chọn driver-supported text/CLOB APIs theo schema thực tế.

### 2.1. Kiểm tra mapping qua JDBC metadata

Một snippet khi đã có `ResultSet rs` với cột đầu là payload XML:

```java
ResultSetMetaData meta = rs.getMetaData();

int typeCode = meta.getColumnType(1);
String vendorName = meta.getColumnTypeName(1);

boolean reportedAsXml =
        (typeCode == java.sql.Types.SQLXML);
```

Đây là **snippet**, cần import `java.sql.ResultSetMetaData` và `java.sql.ResultSet`. `getColumnType(...)` dùng JDBC type code, còn `getColumnTypeName(...)` cho tên loại cột cụ thể của database. Có thể kiểm tra `DatabaseMetaData.getTypeInfo()` để biết driver công bố loại dữ liệu nào.

**Metadata không chứng minh mọi thao tác SQLXML hoạt động:** `getSQLXML`, `createSQLXML` và `setSQLXML` vẫn phải được kiểm thử trực tiếp với driver/schema/version triển khai.

## 3. Vòng đời SQLXML: phần quan trọng nhất

Theo Java SE 17 Javadoc:
- Một `SQLXML` thường là một **đối tượng quản lý/đại diện logic** cho giá trị XML, không nhất thiết giữ toàn bộ dữ liệu trong RAM.
- Đối tượng hợp lệ trong **transaction mà nó được tạo**.
- Đọc XML qua `getString`, `getSource`, `getBinaryStream` hoặc `getCharacterStream` làm chuyển trạng thái **readable → not readable**.
- Ghi XML qua `setString`, `setResult`, `setBinaryStream` hoặc `setCharacterStream` làm chuyển trạng thái **writable → not writable**.
- Việc đọc hoặc ghi trên **cùng instance chỉ thực hiện tối đa một lần** theo contract; implementation có thể thay đổi cả trạng thái đọc/ghi sau một thao tác.
- `free()` giải phóng resources, làm instance **không thể đọc hoặc ghi tiếp**. Gọi lại `free()` nhiều lần là no-op theo API.

Sơ đồ đơn giản:

```text
Tạo SQLXML rỗng bằng Connection.createSQLXML()
                  |
             writable
                  |
          setString(xmlText)   <-- ghi MỘT lần
                  |
          not writable
                  |
      PreparedStatement.setSQLXML(...)
                  |
          executeUpdate()
                  |
               free()
                  |
              invalid

Lấy SQLXML từ ResultSet.getSQLXML(...)
                  |
              readable
                  |
          getCharacterStream() <-- đọc MỘT lần
                  |
             not readable
                  |
         dùng và đóng Reader
                  |
               free()
                  |
              invalid
```

**Không được làm như sau với một instance:**

```java
SQLXML value = rs.getSQLXML("payload");
String xml = value.getString();
Reader reader = value.getCharacterStream(); // Không hợp lệ theo contract!
```

Đây là **ví dụ sai có chủ ý**, không được đưa vào ứng dụng: `getString()` đã tiêu thụ quyền đọc của instance. Nếu cần nhiều biểu diễn, đọc/parse dữ liệu **một lần** rồi chuyển đổi object Java đã có; hoặc thực hiện query/lookup lại nếu hợp đồng driver cho phép, không tùy ý gọi nhiều getter trên cùng `SQLXML`.

**`SQLXML` không implements `AutoCloseable`.** Bạn không thể dùng `try (SQLXML xml = ...)`. Phải gọi `free()` trong `finally`. Với `Reader`/`Writer` lấy từ SQLXML, dùng `try-with-resources` cho stream và đảm bảo đóng stream trước khi `free()` hoặc trước khi execute theo quy định.

## 4. Ghi XML vào database bằng createSQLXML và setSQLXML

Luồng thường dùng:

```java
SQLXML xml = connection.createSQLXML();

try {
    xml.setString("<note><title>Xin chào</title></note>");

    try (PreparedStatement ps = connection.prepareStatement(
            "INSERT INTO xml_documents (id, payload) VALUES (?, ?)")) {
        ps.setLong(1, id);
        ps.setSQLXML(2, xml);
        ps.executeUpdate();
    }
} finally {
    xml.free();
}
```

Đây là **snippet** khi `Connection connection` đang mở, `long id` là khóa hợp lệ và bảng tồn tại; cần imports `java.sql.SQLXML`, `java.sql.PreparedStatement`. Driver chuyển `SQLXML` thành SQL `XML` khi thực thi statement.

**Các điểm chính:**
1. `createSQLXML()` trả một SQLXML **rỗng, có thể ghi**.
2. `setString` truyền serialization XML vào đối tượng; nội dung phải là XML hợp lệ theo database/driver.
3. `ps.setSQLXML(2, xml)` bind tham số thứ hai; parameter index bắt đầu từ 1.
4. `ps.executeUpdate()` thực hiện câu SQL; XML có thể chỉ được kiểm tra hợp lệ tại thời điểm thực thi.
5. `xml.free()` giải phóng resources ngay cả nếu statement thất bại.

**Đừng gọi `xml.free()` trước `executeUpdate()`**: việc driver cần đọc nội dung lúc execute có thể khiến binding thất bại. Thêm nữa, đừng giữ `SQLXML` sau commit/rollback hoặc chuyển nó sang một connection khác vì Javadoc chỉ bảo đảm vòng đời trong transaction đã tạo.

### 4.1. Ghi lớn bằng Writer thay vì materialize String

`SQLXML.setCharacterStream()` trả một `Writer` để ghi serialization XML. Khi dữ liệu nằm trên file UTF-8 hoặc được sinh ra theo luồng:

```java
SQLXML xml = connection.createSQLXML();

try {
    try (Writer writer = xml.setCharacterStream();
         Reader source = Files.newBufferedReader(
                 inputPath, StandardCharsets.UTF_8)) {
        source.transferTo(writer);
    }

    try (PreparedStatement ps = connection.prepareStatement(
            "UPDATE xml_documents SET payload = ? WHERE id = ?")) {
        ps.setSQLXML(1, xml);
        ps.setLong(2, id);
        ps.executeUpdate();
    }
} finally {
    xml.free();
}
```

Đây là **snippet**, có `Connection connection`, `Path inputPath`, `long id` và imports `java.io.Writer`, `java.io.Reader`, `Files`, `StandardCharsets`, `SQLXML`, `PreparedStatement`. Kiểu XML phải được driver hỗ trợ.

**Thứ tự bắt buộc:** **đóng Writer trước khi bind/execute**; Javadoc yêu cầu stream ghi phải hoàn tất/đóng trước `execute()`, nếu không có thể ném `SQLException`. `Reader.transferTo` đếm đơn vị Java `char` đã chuyển, không phải bytes UTF-8. `Writer` này là dòng ký tự XML, nên đừng nhầm nó với binary stream.

Đây là API có thể hỗ trợ dữ liệu lớn mà không tạo một `String` ở business layer, **nhưng driver có thể buffer nội bộ**. Không hứa O(1) memory trên toàn bộ hệ thống trước khi đo với driver thật.

### 4.2. Ghi binary XML

`SQLXML.setBinaryStream()` trả `OutputStream`. Bytes của XML stream được hiểu theo quy tắc XML encoding (XML 1.0 Appendix F và khai báo encoding nếu có). Với nguồn UTF-8 đã có, cần bảo đảm XML prolog/encoding khớp bytes.

Không viết `String.getBytes()` với charset mặc định rồi đưa vào binary stream, vì encoding mặc định của OS/JVM không phải hợp đồng dữ liệu. Nếu có thể, dùng `setString`/`setCharacterStream` khi nguồn là text Unicode và chỉ dùng binary stream khi đã kiểm soát XML byte encoding.

## 5. Đọc XML từ ResultSet

Sau một truy vấn trả cột SQL XML:

```java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT payload FROM xml_documents WHERE id = ?")) {

    ps.setLong(1, id);

    try (ResultSet rs = ps.executeQuery()) {
        if (!rs.next()) {
            throw new SQLException("Document not found: " + id);
        }

        SQLXML xml = rs.getSQLXML("payload");

        if (xml == null) {
            // SQL NULL - xử lý khác document XML rỗng.
        } else {
            try {
                try (Reader reader = xml.getCharacterStream()) {
                    reader.transferTo(outputWriter);
                }
            } finally {
                xml.free();
            }
        }
    }
}
```

Đây là **snippet**, với `Connection connection`, `long id`, `Writer outputWriter` đã mở và imports JDBC/Reader phù hợp. Các resource `PreparedStatement`, `ResultSet` và Reader phải có vòng đời rõ.

**Đọc một lần:** `xml.getCharacterStream()` tiêu thụ quyền đọc instance; không gọi `xml.getString()` sau đó. Nếu chỉ cần một XML nhỏ, có thể chọn `getString()` ngay thay cho Reader; nhưng đừng gọi cả hai trên cùng object.

**SQL NULL:** `rs.getSQLXML(...)` trả `null` nếu column chứa SQL NULL. Khác với SQL NULL, XML element trống như `<note/>` vẫn là một giá trị XML hợp lệ, không phải `null`. Nếu query không có row, `rs.next()` là false, đây là trường hợp thứ ba.

**Ranh giới transaction và cursor:** SQLXML thường có vòng đời trong transaction hiện hành và có thể tham chiếu dữ liệu qua driver/server. Nên đọc xong, đóng stream và `free()` **trước khi chuyển cursor, đóng ResultSet/Connection hoặc commit/rollback**. Không trả SQLXML/Reader từ method sau khi connection đã về pool.

### 5.1. SQLXML.getString hay ResultSet.getString?

`rs.getString("payload")` có thể hoạt động với cột XML tùy driver; `rs.getSQLXML("payload")` phản ánh **mapping SQL XML chuẩn của JDBC** và cho phép chọn nhiều phương thức đọc từ instance. Nếu XML nhỏ và driver hỗ trợ, `getString` tiện; với tài liệu lớn, Reader/Source có thể giảm materialization ở application.

**Không giả định byte-for-byte XML serialization được bảo toàn.** DBMS có thể thay đổi encoding declaration, thứ tự attributes, namespace prefixes, whitespace hoặc cách serialize nội dung XML. Để kiểm thử semantics, có thể parse và so sánh cây dữ liệu/giá trị XPath; chỉ kiểm tra byte equality nếu database/vendor cam kết lưu serialization nguyên vẹn.

## 6. Bốn kiểu đọc và bốn kiểu ghi

| Đọc từ SQLXML | Kiểu kết quả | Khi nên dùng |
| --- | --- | --- |
| `getString()` | `String` | XML nhỏ hoặc khi đã cần toàn chuỗi trong bộ nhớ. |
| `getCharacterStream()` | `Reader` | Copy/parse XML theo luồng ký tự. |
| `getBinaryStream()` | `InputStream` | Xử lý XML serialization dạng bytes và encoding XML. |
| `getSource(Class<T>)` | `Source` | Kết hợp DOM, SAX, StAX, JAXP transformations. |

| Ghi vào SQLXML | Giá trị đầu vào | Khi nên dùng |
| --- | --- | --- |
| `setString(String)` | `String` | XML nhỏ đã được serialize hợp lệ. |
| `setCharacterStream()` | `Writer` | Sinh/copy XML Unicode từ nguồn Reader. |
| `setBinaryStream()` | `OutputStream` | Ghi XML bytes đã xác định đúng encoding. |
| `setResult(Class<T>)` | `Result` | Đưa XML qua DOM, SAX, StAX hoặc transformer pipeline. |

**Chọn một phương thức cho một instance.** Đừng dùng `getSource` rồi `getString` cùng trên SQLXML object để “kiểm tra lại”; contract chỉ cho phép một lần đọc. Tương tự, không `setString` rồi tiếp tục `setResult` trên object vừa ghi.

### 6.1. Source và Result nào được hỗ trợ?

Javadoc nêu bốn biến thể chuẩn tối thiểu:

| Dạng | Đọc | Ghi | Ý nghĩa |
| --- | --- | --- | --- |
| DOM | `DOMSource` | `DOMResult` | Cây `org.w3c.dom.Node`. |
| SAX | `SAXSource` | `SAXResult` | SAX event parsing/handling. |
| StAX | `StAXSource` | `StAXResult` | Pull/event-based XML processing. |
| Stream | `StreamSource` | `StreamResult` | Reader/InputStream/Writer/OutputStream qua JAXP. |

`getSource(null)`/`setResult(null)` có thể trả **vendor-specific implementation**. Khi cần một biểu diễn cụ thể, yêu cầu bằng class tương ứng như `DOMSource.class` hoặc `StAXResult.class`. Khi có class `Source`, các APIs `Transformer`, `XPath` hay XML parser có thể làm việc với dữ liệu mà không cần tự coi toàn bộ nội dung chỉ là String.

**Thận trọng bảo mật:** `sqlxml.getSource(DOMSource.class)` có thể khiến driver/JAXP tự parse XML. Bạn không nhất thiết kiểm soát cấu hình parser dùng bên trong. Với **XML không đáng tin**, tránh giả định `getSource` tự chống XXE; ưu tiên lấy `Reader` một lần rồi parse bằng **factory đã cấu hình an toàn** hoặc chọn API secure provider có tài liệu rõ.

## 7. Ví dụ Java 17+ hoàn chỉnh không cần database: XML parser an toàn

Trước khi trộn XML với JDBC, hãy xác minh rằng Java xử lý XML nội dung tiếng Việt và **từ chối DOCTYPE** khi dữ liệu không tin cậy. Ví dụ này chỉ dùng `java.xml` trong JDK 17+, không cần external dependency.

Tạo file **`SafeXmlDemo.java`**:

```java
import java.io.Reader;
import java.io.StringReader;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.xml.sax.InputSource;
import org.xml.sax.SAXException;
import org.xml.sax.SAXParseException;
import org.xml.sax.helpers.DefaultHandler;

public final class SafeXmlDemo {
    static Document parseSecurely(Reader input) throws Exception {
        DocumentBuilderFactory factory =
                DocumentBuilderFactory.newDefaultInstance();
        factory.setNamespaceAware(true);
        factory.setXIncludeAware(false);
        factory.setFeature(
                "http://apache.org/xml/features/disallow-doctype-decl", true);
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        DocumentBuilder builder = factory.newDocumentBuilder();
        builder.setErrorHandler(new DefaultHandler() {
            @Override
            public void fatalError(SAXParseException error)
                    throws SAXException {
                throw error;
            }
        });
        return builder.parse(new InputSource(input));
    }

    static String text(Element root, String tag) {
        return root.getElementsByTagName(tag)
                .item(0).getTextContent();
    }

    public static void main(String[] args) throws Exception {
        String xml =
                "<note id=\"N-7\"><title>Ti\u1ebfng Vi\u1ec7t &amp; XML</title>"
                + "<body>Xin ch\u00e0o \uD83C\uDF0F</body></note>";

        Document document = parseSecurely(new StringReader(xml));
        Element root = document.getDocumentElement();

        System.out.println("root=" + root.getTagName());
        System.out.println("id=" + root.getAttribute("id"));
        System.out.println("title=" + text(root, "title"));
        System.out.println("body=" + text(root, "body"));

        String malicious =
                "<!DOCTYPE note [<!ENTITY secret SYSTEM "
                + "\"file:///etc/passwd\">]><note>&secret;</note>";

        boolean blocked = false;
        try {
            parseSecurely(new StringReader(malicious));
        } catch (SAXException expected) {
            blocked = true;
        }
        System.out.println("doctypeRejected=" + blocked);
    }
}
```

### 7.1. Chạy và kết quả

```bash
javac -encoding UTF-8 SafeXmlDemo.java
java SafeXmlDemo
```

**Stdout chính xác** đã chạy kiểm chứng bằng JDK:

```text
root=note
id=N-7
title=Tiếng Việt & XML
body=Xin chào 🌏
doctypeRejected=true
```

**Giải thích:**
1. `newDefaultInstance()` chọn factory XML built-in của JDK, phù hợp Java 17+.
2. `setNamespaceAware(true)` hỗ trợ XML namespaces; `setXIncludeAware(false)` chặn XInclude.
3. Feature `disallow-doctype-decl` từ chối `DOCTYPE` trong XML không tin cậy, ngăn khai báo external entities ngay từ đầu.
4. `FEATURE_SECURE_PROCESSING` bật giới hạn xử lý an toàn; `ACCESS_EXTERNAL_DTD` và `ACCESS_EXTERNAL_SCHEMA` đặt rỗng để không cho truy cập external resources từ parser.
5. `parseSecurely` sử dụng `InputSource(Reader)`: không tự mở URL/file được gắn qua input bất kỳ.
6. Tên tiêu đề có `&amp;` trong XML nhưng trả text Java `Tiếng Việt & XML` khi parse.
7. Chuỗi emoji đi qua Unicode DOM parsing nguyên vẹn, không bị mất dấu.
8. `doctypeRejected=true` xác nhận parser **từ chối DOCTYPE** trước khi có thể mở resource `file:///etc/passwd`. Chương trình **không đọc nội dung file** ở đường dẫn này.
9. ErrorHandler được đặt để lỗi fatal không in thông báo phụ không kiểm soát lên stderr trong demo.

Trong ví dụ, `text(root, tag)` giả định tài liệu đúng schema và luôn có child element tương ứng. Production cần kiểm tra `NodeList.getLength()`, xử lý nhiều namespace, missing elements, dữ liệu quá dài và validation theo schema nghiệp vụ.

**Đây là ví dụ về XML handling, không phải kết nối DB.** `SQLXML` là tầng ánh xạ JDBC. Với dữ liệu XML trong SQLXML do database trả về, bạn có thể lấy `Reader` và gọi cùng `parseSecurely(reader)`; chương trình tích hợp ở mục sau làm điều đó.

## 8. Chương trình JDBC Java 17+: ánh xạ cột XML thực tế

Ví dụ tiếp theo dùng **`Connection.createSQLXML()`, `SQLXML.setString`, `PreparedStatement.setSQLXML`, `ResultSet.getSQLXML` và `SQLXML.getCharacterStream`**, rồi parse XML bằng phương thức hardened của `SafeXmlDemo`.

**Cần có thật:** JDBC driver tương thích, database có bảng `xml_documents`, cột `payload` được map sang SQL XML, quyền INSERT/SELECT và một ID chưa tồn tại. Code biên dịch với JDK 17+ mà không cần thêm library, nhưng để **chạy** phải có JDBC driver và DB phù hợp. Không công bố stdout cụ thể cho mọi DB.

### 8.1. File JdbcSqlXmlRoundTrip.java

Đặt file này **cùng thư mục** với `SafeXmlDemo.java` ở trên:

```java
import java.io.Reader;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.SQLXML;
import java.util.Properties;
import org.w3c.dom.Document;
import org.w3c.dom.Element;

public final class JdbcSqlXmlRoundTrip {

    private static void insert(
            Connection connection, long id, String documentXml)
            throws SQLException {

        SQLXML value = connection.createSQLXML();
        try {
            value.setString(documentXml);

            try (PreparedStatement ps = connection.prepareStatement(
                    "INSERT INTO xml_documents (id, payload) VALUES (?, ?)")) {
                ps.setLong(1, id);
                ps.setSQLXML(2, value);

                if (ps.executeUpdate() != 1) {
                    throw new SQLException("Expected one inserted row");
                }
            }
        } finally {
            value.free();
        }
    }

    private static void display(Connection connection, long id)
            throws Exception {

        try (PreparedStatement ps = connection.prepareStatement(
                "SELECT payload FROM xml_documents WHERE id = ?")) {
            ps.setLong(1, id);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException("Missing id: " + id);
                }

                SQLXML value = rs.getSQLXML("payload");
                if (value == null) {
                    System.out.println("xmlIsNull=true");
                    return;
                }

                try {
                    try (Reader reader = value.getCharacterStream()) {
                        Document parsed =
                                SafeXmlDemo.parseSecurely(reader);

                        Element root = parsed.getDocumentElement();
                        System.out.println("root=" + root.getTagName());
                        System.out.println("title=" +
                                SafeXmlDemo.text(root, "title"));
                    }
                } finally {
                    value.free();
                }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println(
                    "Usage: java JdbcSqlXmlRoundTrip <jdbc-url> <id>");
            return;
        }

        long id = Long.parseLong(args[1]);

        Properties properties = new Properties();
        String user = System.getenv("DB_USER");
        String password = System.getenv("DB_PASSWORD");

        if (user != null) {
            properties.setProperty("user", user);
        }
        if (password != null) {
            properties.setProperty("password", password);
        }

        String xml =
                "<note><title>Ti\u1ebfng Vi\u1ec7t &amp; XML</title></note>";

        try (Connection connection =
                     DriverManager.getConnection(args[0], properties)) {
            connection.setAutoCommit(false);
            try {
                insert(connection, id, xml);
                display(connection, id);
                connection.commit();
            } catch (Exception error) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            }
        }
    }
}
```

### 8.2. Biên dịch và chạy

Giả sử đã tạo bảng XML phù hợp bằng DDL của vendor và đã có `driver.jar` (đây chỉ là tên ví dụ cho file JDBC driver thật).

```bash
javac -encoding UTF-8 SafeXmlDemo.java JdbcSqlXmlRoundTrip.java
java -cp ".:driver.jar" JdbcSqlXmlRoundTrip "$JDBC_URL" 1001
```

Lệnh trên là cho **Linux/macOS**; `JDBC_URL` là biến môi trường chứa URL không có password. Trên **PowerShell** dùng classpath separator `;`:

```powershell
javac -encoding UTF-8 SafeXmlDemo.java JdbcSqlXmlRoundTrip.java
java -cp '.;driver.jar' JdbcSqlXmlRoundTrip $env:JDBC_URL 1001
```

Nếu cần, cung cấp `DB_USER`/`DB_PASSWORD` qua biến môi trường trên máy thử. Với production ưu tiên vault/secret manager thay vì hard-code password, và không đưa credentials vào URL, command line hay logs.

**Ý nghĩa các bước:**
1. Tạo kết nối và tắt auto-commit để giữ SQLXML trong cùng transaction.
2. `insert` tạo đối tượng SQLXML rỗng, ghi string XML **một lần**, bind vào parameter thứ 2 và thực hiện INSERT.
3. Giải phóng SQLXML dùng để ghi trong `finally` ngay sau execute.
4. `display` SELECT cùng id trong transaction, nhận SQLXML của cột, lấy Reader **một lần** rồi parse bằng hardened DOM builder.
5. `Reader` đóng trước khi `SQLXML.free()`; object được free trước khi ResultSet/Connection đóng.
6. Commit khi insert+read thành công; rollback nếu SQL/parser/IO exception và thêm lỗi rollback vào suppressed exceptions nếu rollback cũng gặp lỗi.
7. Vì `id` là primary key, chạy lại cùng ID sẽ thất bại với duplicate-key nếu row trước đã commit. Production cần chiến lược idempotency hoặc UPDATE/UPSERT vendor-specific.

**Stdout phụ thuộc database:** Nếu driver/schema đã hỗ trợ XML hoàn chỉnh và không có lỗi, có thể in:

```text
root=note
title=Tiếng Việt & XML
```

Đây là **kết quả kỳ vọng có điều kiện**, **không phải stdout đã xác minh trên mọi DB**. DBMS có thể từ chối `createSQLXML()` hoặc loại cột XML, hoặc có cách serialize riêng; không giả định hoàn thành trước khi có integration test thật.

**Đã kiểm tra cú pháp Java:** cả `SafeXmlDemo.java` và `JdbcSqlXmlRoundTrip.java` đã được biên dịch bằng JDK hiện đại; chỉ `SafeXmlDemo` được thực thi độc lập vì nó không cần JDBC driver/DB.

## 9. Xử lý SQL NULL và giá trị XML không hợp lệ

### 9.1. SQL NULL

Đặt SQL NULL vào column XML (nếu column cho phép):

```java
ps.setNull(2, java.sql.Types.SQLXML);
```

Đây là snippet với `PreparedStatement ps` và SQL parameter thứ 2. Driver vẫn có thể báo `SQLFeatureNotSupportedException` nếu type `Types.SQLXML` không được hỗ trợ.

Khi đọc:

```java
SQLXML value = rs.getSQLXML("payload");
if (value == null) {
    // SQL NULL, không có nội dung XML.
}
```

**Khác biệt:**
- **Không có hàng:** `rs.next() == false`.
- **Hàng có SQL NULL:** `rs.getSQLXML("payload") == null`.
- **Hàng có XML hợp lệ:** SQLXML khác null, nội dung có thể là `<note/>`.
- **Chuỗi rỗng `""`** thường không phải một document XML hoàn chỉnh; có thể bị từ chối khi set/execute, tùy XML content model của database.

Không tự biến SQL NULL thành `<note/>` hoặc ngược lại nếu ứng dụng cần phân biệt về nghiệp vụ.

### 9.2. Invalid XML phát hiện lúc nào?

Một XML serialization không hợp lệ như:

```xml
<note><title>Thiếu thẻ đóng</note>
```

có thể gây `SQLException` trong `SQLXML.setString`, `setCharacterStream` hoặc chỉ lúc `PreparedStatement.executeUpdate()`. Driver có thể validate sớm hoặc muộn.

Với input không tin cậy:
- **Parse an toàn/validate** trước khi gửi nếu cần bảo đảm XML well-formed và tuân theo schema.
- Không bỏ qua kiểm tra server-side: DBMS vẫn có thể có XML constraints khác ứng dụng.
- Phân biệt lỗi **XML malformed**, **schema invalid**, **SQL data conversion**, **driver unsupported** và **connection/transaction error** bằng SQLState/vendor diagnostics.
- Không log toàn bộ XML payload nhạy cảm trong exception/trace.

## 10. DOM, SAX, StAX, XPath và performance

### 10.1. DOM

`DOMSource`/`DOMResult` mô hình hóa tài liệu dưới dạng cây nodes. Phù hợp khi cần truy cập linh hoạt nhiều vị trí hoặc sửa cấu trúc trong văn bản không quá lớn. Tuy nhiên, DOM thường **materialize toàn bộ XML** vào bộ nhớ; tránh dùng DOM cho XML khổng lồ trong ứng dụng tài nguyên hạn chế.

Javadoc minh họa:

```java
DOMSource source = sqlxml.getSource(DOMSource.class);
Document document = (Document) source.getNode();
```

Đây là snippet chỉ an toàn khi XML/trusted driver parser được kiểm soát; **không phải ví dụ parser hardened cho untrusted XML**. Với dữ liệu không tin cậy, ưu tiên Reader + `SafeXmlDemo.parseSecurely` và áp dụng resource limits.

### 10.2. SAX / StAX

SAX dùng callbacks theo stream; StAX cho phép ứng dụng pull từng XML event. Chúng phù hợp khi muốn đọc XML lớn mà không xây DOM đầy đủ.

Ví dụ **StAX parser hardening** từ hướng dẫn OWASP, khi xử lý XML không tin cậy:

```java
XMLInputFactory factory = XMLInputFactory.newDefaultFactory();
factory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
factory.setProperty(
        XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);

factory.setXMLResolver((publicId, systemId, baseURI, namespace) -> {
    throw new XMLStreamException(
            "External references are not allowed");
});

XMLStreamReader xmlReader = factory.createXMLStreamReader(reader);
try {
    while (xmlReader.hasNext()) {
        int event = xmlReader.next();
        // Xử lý event theo XML schema và nhu cầu nghiệp vụ.
    }
} finally {
    xmlReader.close();
}
```

Đây là **snippet nội bộ** khi đã có `java.io.Reader reader`, cần import các lớp `javax.xml.stream.XMLInputFactory`, `XMLStreamReader`, `XMLStreamException`. Không phải chương trình độc lập. `XMLStreamReader.close()` đóng parser, **không mặc nhiên đóng `reader` nguồn**, vì vậy Reader phải được đóng riêng trong try-with-resources bên ngoài.

Nếu runtime không hỗ trợ một thuộc tính bảo mật cần thiết, **fail closed**, không catch lỗi cấu hình rồi tiếp tục parse với XXE có thể bật. StAX `SUPPORT_DTD=false` không phải lúc nào cũng từ chối nguyên `DOCTYPE` token; ứng dụng cần policy về DTD và entity rõ ràng.

### 10.3. XPath và namespace

XPath giúp tra cứu nội dung từ DOM, ví dụ `/note/title/text()`. Trong hệ thống dữ liệu thực cần phân biệt:
- **XML namespace URI** khác namespace prefix.
- Default namespaces có thể khiến XPath đơn giản không match nếu không cấu hình `NamespaceContext`.
- XPath từ input người dùng có thể dẫn đến **XPath injection** hoặc chi phí xử lý lớn. Không nối trực tiếp input chưa validate vào XPath expression.
- Với untrusted XML, parse bằng hardened DOM factory trước khi chạy XPath, không dùng overload của XPath tự parse input bằng parser không kiểm soát.

### 10.4. Transformer / XSLT

`Transformer` có thể chuyển một `Source` sang `Result`. Nếu XSLT hoặc nguồn XML không đáng tin:
- Vô hiệu external stylesheet/DTD access qua JAXP security properties.
- Dùng `URIResolver` không cho truy cập resource ngoài allowlist.
- Không load stylesheet qua user-controlled URL thiếu kiểm soát.
- Cân nhắc dùng safe `SAXSource` từ hardened XMLReader khi đưa untrusted XML vào transformer.

**Chỉ bật `FEATURE_SECURE_PROCESSING` chưa đủ để vô hiệu mọi external-resource access trong mọi JAXP provider**. Cần cấu hình đầy đủ theo OWASP và kiểm tra JDK/vendor library thực tế.

## 11. Ghi qua SQLXML.setResult(...)

Ngoài setString/Writer, JDBC cho phép writer XML ở cấp JAXP:

```java
SQLXML xml = connection.createSQLXML();

try {
    DOMResult result = xml.setResult(DOMResult.class);
    result.setNode(domDocument);

    try (PreparedStatement ps = connection.prepareStatement(
            "INSERT INTO xml_documents (id, payload) VALUES (?, ?)")) {
        ps.setLong(1, id);
        ps.setSQLXML(2, xml);
        ps.executeUpdate();
    }
} finally {
    xml.free();
}
```

Đây là **snippet**, yêu cầu `org.w3c.dom.Document domDocument` đã được tạo an toàn, `long id` và imports `java.sql.SQLXML`, `java.sql.PreparedStatement`, `javax.xml.transform.dom.DOMResult`. Đọc tài liệu driver để bảo đảm `setResult(DOMResult.class)` và việc gán node được thực thi như mong đợi.

**Lưu ý quan trọng:** Khi dùng `setResult(StreamResult.class)` hoặc XML `Writer/OutputStream`, phải **đóng toàn bộ streams trước khi statement execute**. Với DOMResult/SAXResult/StAXResult, cần **hoàn tất việc tạo cây hoặc phát XML events** trước khi bind/execute; kiểm tra driver lifecycle. Không gọi `setResult` hai lần trên cùng SQLXML object.

Tùy DBMS, `getSource()/setResult()` có thể hoạt động hiệu quả nhờ biểu diễn XML tối ưu mà không cần serialize toàn bộ thành String; nhưng hiệu năng **không được bảo đảm** trên mọi driver. Benchmark với kích cỡ dữ liệu thật.

## 12. ResultSet.updateSQLXML và lưu thay đổi

Với **ResultSet updatable**, JDBC hỗ trợ:

```java
rs.updateSQLXML("payload", updatedXml);
rs.updateRow();
```

Đây là snippet có `ResultSet rs` kiểu `CONCUR_UPDATABLE` và `SQLXML updatedXml` hợp lệ. `updateSQLXML` thay đổi **row buffer**, **không trực tiếp ghi ngay xuống database**. Cần `updateRow()` để áp dụng với hàng đang chọn; `insertRow()` khi làm việc với insert row nếu phù hợp.

**Không nên mặc định updatable ResultSet được hỗ trợ.** Driver/câu SELECT/schema có thể chỉ trả `CONCUR_READ_ONLY`; update method có thể ném `SQLFeatureNotSupportedException` hoặc `SQLException`. Trong các ứng dụng backend thông thường, `PreparedStatement UPDATE ... SET payload = ? WHERE id = ?` với `setSQLXML` và transaction rõ ràng thường đơn giản và dễ kiểm thử hơn.

Với CallableStatement, `getSQLXML` cũng có thể đọc SQL XML output parameter khi driver/stored procedure hỗ trợ; đây là một integration case riêng.

## 13. Vòng đời transaction, exception và connection pool

**SQLXML hợp lệ trong transaction nơi nó được tạo.** Việc một driver cụ thể materialize value không cho phép ứng dụng giả định SQLXML độc lập với connection. Những quy tắc nên áp dụng:

1. **Viết:** tạo SQLXML từ chính connection sẽ dùng để `setSQLXML`, ghi XML một lần, hoàn tất/đóng stream, bind và execute, rồi `free()`.
2. **Đọc:** trong lúc ResultSet/transaction còn mở, `getSQLXML`, chọn một getter, đọc xong, đóng stream và `free()` trước khi close/commit.
3. **Rollback khi lỗi:** SQL update và parsing/validation trong cùng transaction; dùng rollback nếu chính sách yêu cầu. Không tự giả định XML side effect ngoài DB sẽ rollback theo.
4. **Pool:** không trả connection về pool trước khi SQLXML/Reader/ResultSet đã kết thúc; tránh dùng SQLXML object qua request khác.
5. **Thread safety:** không dùng chung mutable JDBC Connection/SQLXML/Reader/ResultSet giữa threads nếu driver không bảo đảm. Dùng scope per operation/request.
6. **Cleanup failures:** `SQLXML.free()` có thể ném `SQLException`. Trong code dùng `finally`, cân nhắc bảo toàn lỗi gốc (thêm suppressed exception) nếu cleanup cũng thất bại; không bỏ qua thất bại giải phóng tài nguyên trong production.
7. **Large XML:** DOM có thể tăng heap, Reader/StAX giảm materialization ở application nhưng driver vẫn có thể buffer. Đo memory/throughput trên DB thật.
8. **Timeout/cancellation:** giới hạn XML size, query duration và số concurrent long XML operations để tránh chiếm hết connection pool.
9. **Cách xem SQL state:** `SQLException.getSQLState()` và `getErrorCode()` giúp chẩn đoán lỗi vendor; không in XML payload hoặc credentials vào logs.

### 13.1. SQLFeatureNotSupportedException

`Connection.createSQLXML()`, `PreparedStatement.setSQLXML`, `ResultSet.getSQLXML` hoặc `SQLXML` methods có thể ném `SQLFeatureNotSupportedException` nếu driver không triển khai. Đây là subclass của `SQLException`, nên muốn xử lý riêng hãy catch trước:

```java
try {
    SQLXML value = connection.createSQLXML();
    try {
        value.setString("<note/>");
        // Bind và execute trong phạm vi connection/transaction phù hợp.
    } finally {
        value.free();
    }
} catch (SQLFeatureNotSupportedException unsupported) {
    // Driver không hỗ trợ: kiểm tra mapping/vendor.
} catch (SQLException databaseError) {
    // Các lỗi JDBC khác.
}
```

Đây là **snippet**, có `Connection connection` và import `SQLXML`, `SQLFeatureNotSupportedException`, `SQLException`. Không nên tự động fallback sang `setString` trên một cột XML nếu database bắt buộc explicit cast hoặc vendor-specific binding khác. **Chọn giải pháp đã kiểm chứng** theo driver (ví dụ text XML + SQL CAST đúng vendor) thay vì đoán.

## 14. Bảo mật: XXE, SSRF và XML bombs

**SQLXML không tự làm XML trở nên đáng tin.** XML trong database có thể đến từ người dùng, đối tác, import file hoặc integration service. Đọc XML rồi đưa vào parser không được cấu hình an toàn có thể gây:
- **XXE:** đọc local files hoặc truy cập network resources qua external entity/DTD.
- **SSRF:** server thực hiện outbound requests không mong muốn.
- **Entity expansion / XML bombs:** CPU/memory exhaustion khi entity expansion không bị giới hạn.
- **XSLT external access:** stylesheet hoặc transformer tải tài nguyên ngoài.
- **Large/deep documents:** tree depth, attribute count hoặc text size gây DoS dù không có DOCTYPE.
- **XPath injection:** khi biểu thức XPath được ghép từ dữ liệu không tin cậy.

**Chính sách mặc định khuyến nghị:**
- Từ chối `DOCTYPE` ở DOM/SAX khi không cần DTD; ngoài ra khóa external access DTD/schema/stylesheet.
- Dùng built-in JAXP factory Java 17+ hoặc xác minh provider bên thứ ba và các security features nó hỗ trợ.
- Không bỏ qua lỗi khi set security property. Nếu hardening thất bại, **dừng xử lý XML không tin cậy**.
- Dùng `Reader`/`InputStream` đã mở từ nguồn được cấp quyền; không tự nhận URL/path input chưa validate.
- Có giới hạn kích cỡ, độ sâu, thời gian và concurrency trên cả application và DB.
- Không đưa XML payload nguyên vẹn vào logs hoặc exception message gửi tới người dùng.

**Ví dụ `SafeXmlDemo` đã từ chối DOCTYPE và test điều đó**. Khi triển khai với SAX/StAX/DOM/Transformers khác, dùng OWASP XML External Entity Prevention Cheat Sheet để cấu hình tương ứng; không suy rằng hardening một loại parser có hiệu lực cho tất cả APIs.

### 14.1. SQL injection vẫn phải được phòng tránh

`SQLXML` chỉ là kiểu bind cho XML data; nó không làm các câu SQL tự an toàn khi build bằng nối chuỗi:

```java
// Mẫu an toàn: SQL cố định, data được bind qua tham số.
try (PreparedStatement ps = connection.prepareStatement(
        "UPDATE xml_documents SET payload = ? WHERE id = ?")) {
    ps.setSQLXML(1, sqlxml);
    ps.setLong(2, id);
    ps.executeUpdate();
}
```

Đây là **snippet**, `sqlxml` là SQLXML đã ghi hoàn chỉnh và chưa `free()`; cần gọi `free()` sau execute theo lifecycle. Tên bảng/cột động nếu có phải dùng allowlist, không bind bằng `?` và không nối trực tiếp input từ người dùng.

## 15. XML namespaces, encoding và tính toàn vẹn

### 15.1. XML có namespace

Ví dụ:

```xml
<doc:note xmlns:doc="urn:example:notes">
    <doc:title>Tiếng Việt</doc:title>
</doc:note>
```

Khi parse DOM với `setNamespaceAware(true)`, nên dùng `getElementsByTagNameNS("urn:example:notes", "title")` nếu cần truy vấn namespace chính xác. `getElementsByTagName("title")` có thể không tìm `doc:title` vì qualified name gồm prefix. Namespace prefix là cú pháp, **namespace URI** mới là định danh; XML database có thể serialize lại prefix nhưng giữ ý nghĩa.

### 15.2. Character stream vs binary stream

`SQLXML.getCharacterStream` trả Reader chứa ký tự Unicode. Trong `Reader` Java, `char` thường là đơn vị UTF-16, không phải bytes UTF-8. `SQLXML.getBinaryStream` trả bytes có encoding theo quy tắc XML serialization; không mặc định mọi byte stream là UTF-8 nếu XML document/declaration có encoding khác.

Với XML text là `String` Java, `setString` và `getString` làm việc trên ký tự. Nếu xuất file:
- Dùng `Files.newBufferedWriter(path, StandardCharsets.UTF_8)` để chọn charset rõ ràng.
- Nếu XML declaration chứa `encoding="ISO-8859-1"` nhưng file được ghi UTF-8, cần sửa declaration/serialization policy cho nhất quán.
- Khi so sánh bản trước/sau DB, XML serialization có thể thay đổi: whitespace, attribute order, prefix/encoding declarations. Khi dữ liệu yêu cầu so sánh **ngữ nghĩa**, parse rồi so sánh cấu trúc/giá trị.
- Đừng tự normalization Unicode, bỏ dấu tiếng Việt hoặc đổi escaping `&amp;` chỉ vì đang đọc XML qua JDBC.

### 15.3. XML well-formed và schema

Một XML document well-formed chưa chắc phù hợp schema nghiệp vụ. Nếu DB có XML schema collection hoặc constraint, nó có thể từ chối value mà parser Java vẫn parse được. Nếu ứng dụng xác thực bằng XSD:
- Bật JAXP secure-processing và khóa external schema/DTD access.
- Chỉ lấy schema từ trusted resources, hạn chế include/import hoặc resolve theo allowlist.
- Đặt giới hạn payload, độ sâu, số nodes và thời gian validation.
- Bảo đảm Java và DB thống nhất schema/version, không chỉ dựa vào XML syntax.

## 16. Performance: SQLXML không đồng nghĩa streaming tuyệt đối

| Cách đọc/ghi | Bộ nhớ ở application | Hạn chế |
| --- | --- | --- |
| `setString/getString` | Có một chuỗi XML materialized. | Dễ hiểu, nhưng không lý tưởng cho XML rất lớn. |
| `setCharacterStream/getCharacterStream` | Có thể xử lý theo chunk. | Driver vẫn có thể buffer; Reader/Writer lifecycle quan trọng. |
| `getSource(DOMSource.class)` | Có thể dựng cả DOM tree. | Không phù hợp XML cực lớn; parser security cần được xét. |
| SAX / StAX | Có thể duyệt events mà không giữ cả cây. | Business logic phức tạp hơn, cần hardening DTD/entities. |
| DB native XML operations | Có thể dùng chỉ mục/khả năng XML của DBMS. | SQL syntax, index, performance phụ thuộc vendor. |

JDBC `SQLXML` là **hợp đồng truy cập XML**, không phải cam kết driver sẽ truyền theo chunk qua network. Chỉ test load/bộ nhớ trên phiên bản DBMS/driver cụ thể mới có thể xác nhận performance.

Một số DB có chỉ mục/SQL XML query operators để lọc/thao tác XML bên server, nhưng cú pháp khác nhau. Nếu ứng dụng thường xuyên truy xuất một vài trường cố định, xem xét thiết kế schema quan hệ riêng hoặc indexes thay vì luôn tải và parse toàn bộ XML về Java.

## 17. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân khả dĩ | Giải pháp |
| --- | --- | --- |
| `SQLFeatureNotSupportedException` tại `createSQLXML` | Driver/DB không triển khai mapping XML. | Kiểm tra driver version và vendor documentation, chọn mapping khác đã test. |
| `SQLException` tại `setSQLXML` hoặc execute | XML invalid, mismatch cột, connection/transaction lỗi hoặc stream chưa đóng. | Kiểm tra schema, well-formed XML, thứ tự đóng Writer và exception cause. |
| `SQLXML.free()` rồi `getString()` | Đối tượng đã invalid. | Chỉ dùng `free` ở cuối lifecycle. |
| `getString()` sau `getCharacterStream()` | SQLXML đã bị đọc một lần. | Chọn một getter hoặc query lại tạo instance mới. |
| `getSQLXML(...) == null` | SQL column là SQL NULL. | Xử lý null khác XML element trống. |
| `rs.next()` false | Không có row. | Kiểm tra row count/ID; không nhầm với SQL NULL. |
| XXE/SSRF khi parse | Parser cho external entities/DTD. | Harden factory, từ chối DOCTYPE, khóa external access. |
| XML “trông đúng” nhưng DB từ chối | DB có XML schema/validation riêng. | Phân biệt syntax và schema, test DB constraints. |
| Code chạy trên DB này nhưng hỏng trên DB khác | XML column/SQL casting và driver mapping không portable. | Kiểm tra `Types.SQLXML`, vendor docs và integration tests. |
| XML content mất nguyên byte format | DB serialize lại XML. | So sánh dữ liệu cấu trúc thay vì bytes nếu semantics là mục tiêu. |
| XML lớn gây OOM | `getString`/DOM hoặc driver buffer toàn bộ. | Reader + StAX/SAX, giới hạn size, profile driver. |
| `setResult(StreamResult.class)` thất bại | Writer/OutputStream chưa đóng/transform chưa hoàn tất. | Hoàn tất và đóng stream trước execute. |
| XML chưa được commit | Transaction rollback hoặc auto-commit disabled. | Commit có chủ đích, dùng rollback khi lỗi. |
| Lỗi sau khi trả connection pool | SQLXML/Reader còn phụ thuộc transaction. | Đọc hết, đóng và free trước khi trả pool. |
| `ResultSet.updateSQLXML` không lưu được | ResultSet read-only hoặc chưa gọi `updateRow()`. | Dùng PreparedStatement UPDATE hoặc updatable result set đúng cách. |
| Thư viện JAXB missing | Jakarta XML Binding không còn được đóng sẵn trong Java 17. | Khai báo dependency Jakarta XML Binding nếu thật sự cần, hoặc dùng JAXP sẵn trong JDK. |
| Test XML text equality fail | Prefixes, whitespace, attribute order/encoding thay đổi. | So sánh cấu trúc/giá trị XML khi phù hợp. |

## 18. Checklist kiểm thử thực tế

**Test 1 — Driver support:** kiểm tra `createSQLXML`, `setSQLXML`, `getSQLXML` và loại cột XML thật. Đừng kết luận “DB hỗ trợ XML” chỉ vì driver cho phép `getString`.

**Test 2 — Round-trip Unicode:** ghi/đọc văn bản tiếng Việt, CJK, emoji, XML escaping và namespaces. Xác định policy so sánh structural equality hay serialized bytes.

**Test 3 — NULL và missing row:** phân biệt `rs.next()==false`, `rs.getSQLXML()==null` và XML element rỗng.

**Test 4 — Single-use:** thử gọi hai getters trên cùng SQLXML trong integration test; xác minh contract/sai lầm phổ biến và sửa code để đọc một lần.

**Test 5 — Writer closure:** ghi bằng `setCharacterStream()`; xác minh stream đã đóng trước execute.

**Test 6 — Transaction lifecycle:** đọc SQLXML trong transaction trước commit/rollback; đừng giữ object sau khi transaction kết thúc.

**Test 7 — Invalid XML:** malformed tags, namespace sai, không hợp lệ XSD; phân biệt exception của Java parser và DBMS.

**Test 8 — XXE:** đưa XML có DOCTYPE/external entity vào parser trên môi trường test; bảo đảm hardening từ chối, không truy cập file/network.

**Test 9 — Large document:** đo heap/GC/latency/network/connection pool với dữ liệu tương đương production.

**Test 10 — Updatable ResultSet:** nếu dùng `updateSQLXML`, xác minh driver cho updatable cursor và gọi `updateRow`.

**Test 11 — Portability:** chạy trên các versions JDBC driver/JDK/DBMS thực tế của sản phẩm; đặc biệt kiểm tra SQL XML DDL và vendor casts.

**Test 12 — Cleanup failure:** giả lập exception giữa statement và `free()`, xác nhận resource/transaction được xử lý và lỗi gốc không bị mất.

**Test 13 — Security limits:** XML quá sâu/quá lớn, entity expansion, XSLT external URI và concurrency; áp chính sách size/time/allowlist.

## 19. Câu hỏi ôn tập

**Câu 1.** SQL `XML` và Java `SQLXML` có giống nhau không?

**Đáp án:** Không. SQL `XML` là loại dữ liệu của database; `java.sql.SQLXML` là interface JDBC ánh xạ giá trị cột đó cho Java.

**Câu 2.** Muốn ghi XML qua PreparedStatement, trình tự API cơ bản là gì?

**Đáp án:** `connection.createSQLXML()` → `sqlxml.setString(...)` hoặc Writer/Result (một lần) → `ps.setSQLXML(index, sqlxml)` → `executeUpdate()` → `sqlxml.free()`.

**Câu 3.** Có thể dùng `getString` rồi `getSource` với cùng instance SQLXML không?

**Đáp án:** Không. Mỗi SQLXML instance được đọc tối đa một lần theo contract; getter đầu tiên chuyển trạng thái không còn readable.

**Câu 4.** Có được dùng `try (SQLXML value = ...)` không?

**Đáp án:** Không. `SQLXML` không phải `AutoCloseable`; dùng `finally { value.free(); }`.

**Câu 5.** Vì sao dùng `getSource(DOMSource.class)` trên XML không đáng tin phải cẩn thận?

**Đáp án:** Parser nội bộ có thể do driver/provider điều khiển và chưa chắc áp dụng XXE security policy của ứng dụng. Với untrusted XML, parse `getCharacterStream()` qua hardened DocumentBuilder hoặc hardened SAX/StAX parser.

**Câu 6.** `ResultSet.getSQLXML` trả null là trường hợp nào?

**Đáp án:** Khi giá trị SQL column là NULL; cần phân biệt với không có row hoặc XML element trống.

**Câu 7.** Vì sao phải đóng Writer được trả từ `setCharacterStream` trước khi execute?

**Đáp án:** Javadoc yêu cầu XML output stream phải hoàn tất/đóng trước statement execution; nếu không có thể ném `SQLException`.

**Câu 8.** XML serialization thay đổi sau khi lưu DB có luôn nghĩa dữ liệu bị hỏng không?

**Đáp án:** Không. DBMS có thể serialize lại namespace prefixes, attributes, encoding/whitespace mà giữ nội dung XML tương đương; cần so sánh theo contract của dữ liệu.

**Câu 9.** `updateSQLXML` có tự cập nhật DB ngay không?

**Đáp án:** Với updatable ResultSet, nó thay đổi row buffer; cần `updateRow` hoặc `insertRow` tương ứng.

**Câu 10.** Chỉ bật `FEATURE_SECURE_PROCESSING` đã đủ chống XXE cho mọi Java XML API chưa?

**Đáp án:** Chưa. Cần từ chối DTD/external entities, khóa external access, cấu hình từng parser/transformer và giới hạn tài nguyên theo OWASP.

**Câu 11.** Java 17 có sẵn JAXB như trước Java 8 không?

**Đáp án:** Không. Nếu cần Jakarta XML Binding, phải khai báo dependencies phù hợp; JAXP DOM/SAX/StAX/Transformer APIs vẫn có trong JDK.

## 20. Checklist trước production

- Xác nhận database **có native XML type/mapping** và driver hỗ trợ `Types.SQLXML`, `Connection.createSQLXML`, `setSQLXML`, `getSQLXML`.
- Không giả định SQL DDL `payload XML` chạy giống nhau trên mọi DBMS.
- Xác định **một cách đọc/ghi** cho mỗi SQLXML instance; không dùng getters hoặc setters lặp.
- Giữ XML object trong transaction; gọi `free()` đúng thời điểm và quản lý cleanup exceptions.
- Với `setCharacterStream`/`setBinaryStream`, đóng output stream trước statement execute.
- Với XML untrusted, **hardening DOM/SAX/StAX** và fail closed nếu cấu hình bảo mật không được hỗ trợ.
- Không bỏ qua XXE, external DTD, SSRF, entity expansion, schema/XSLT external-resource risks.
- Giới hạn XML size, depth, thời gian parse/execute, concurrency và connection-pool occupancy.
- Bind SQL bằng `PreparedStatement`, không nối XML text hay user input vào SQL.
- Xử lý SQL NULL khác row không tồn tại hoặc XML element rỗng.
- Test namespaces, Unicode text, XML escaping, DB schema constraints và serialization differences.
- Đo driver buffering và memory của DOM/stream, không giả định mọi đường SQLXML là streaming.
- Với `ResultSet.updateSQLXML`, dùng đúng updatable cursor và `updateRow`.
- Kiểm tra dependency/runtime modules: `java.sql` và `java.xml` là API tiêu chuẩn Java 17+; Jakarta XML Binding cần dependency riêng nếu sử dụng.

## 21. Tài liệu tham khảo chính thức và bảo mật

- [Java SE 17 — SQLXML](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLXML.html): toàn bộ methods, state machine single-read/write, source/result, transaction validity và `free()`.
- [Java SE 17 — Connection](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html): `createSQLXML()` và transaction lifecycle.
- [Java SE 17 — PreparedStatement](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html): `setSQLXML()`, parameter binding, stream-close requirements.
- [Java SE 17 — ResultSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html): `getSQLXML()`, `updateSQLXML()` và updatable ResultSet.
- [Java SE 17 — Types](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Types.html): `Types.SQLXML`.
- [Java SE 17 — DocumentBuilderFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/parsers/DocumentBuilderFactory.html): cấu hình DOM parser.
- [Java SE 17 — XMLInputFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/stream/XMLInputFactory.html): StAX streaming XML parsing.
- [Java SE 17 — XMLConstants](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/XMLConstants.html): security processing, external-access attributes.
- [OWASP — XML External Entity Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html): cấu hình chống XXE/SSRF trên DOM, SAX, StAX và transformers.
- [Java SE 25 — SQLXML](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/SQLXML.html): đối chiếu API hiện vẫn được hỗ trợ trên JDK hiện đại.
