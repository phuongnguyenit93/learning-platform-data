# SQLXML: Reader, Writer, stream và thứ tự đóng tài nguyên trong JDBC

## 1. Vì sao thứ tự đóng quyết định tính đúng đắn?

`java.sql.SQLXML` là abstraction JDBC của một **giá trị SQL XML**. Nó có thể là một handle logic tới tài nguyên trong database thay vì một `String` trong RAM. API cho phép thao tác qua `String`, `Reader`, `Writer`, `InputStream`, `OutputStream` hoặc các XML APIs như DOM/StAX/SAX. Nếu mở một luồng ghi rồi execute khi luồng **chưa được đóng**, XML có thể chưa hoàn tất; theo JavaDoc hiện hành, các stream tạo XML **phải được đóng trước khi execute**, nếu không `SQLException` có thể xảy ra.

Đây là khác biệt giữa việc “đã gọi `write`” và việc “đã **hoàn thành** một giá trị SQLXML”. Chương trình cần quản lý riêng:

1. **Đầu ghi:** `Writer` hoặc `OutputStream` từ `setCharacterStream/setBinaryStream`, đóng **trước bind/execute**.
2. **Đầu đọc:** `Reader` hoặc `InputStream` từ `getCharacterStream/getBinaryStream`, đóng **sau khi đọc xong**, trước khi free SQLXML.
3. **SQLXML object:** `free()` sau khi statement dùng xong hoặc sau khi luồng đọc kết thúc.
4. **JDBC owner:** `ResultSet`, `PreparedStatement`, `Connection` được đóng/trả pool khi công việc tương ứng đã hoàn tất.

Hai sơ đồ ngắn:

~~~text
GHI:
Connection.createSQLXML
  -> SQLXML.setCharacterStream
  -> Writer.write
  -> Writer.close
  -> PreparedStatement.setSQLXML
  -> PreparedStatement.executeUpdate
  -> SQLXML.free
  -> PreparedStatement.close
  -> Connection.close/return-to-pool

ĐỌC:
ResultSet.next
  -> ResultSet.getSQLXML
  -> SQLXML.getCharacterStream
  -> Reader.read / parser xử lý XML
  -> Reader.close
  -> SQLXML.free
  -> ResultSet.close
  -> PreparedStatement.close
  -> Connection.close/return-to-pool
~~~

**Điểm theo phiên bản:** `SQLXML` trên **Java 17** chưa kế thừa `AutoCloseable`, vì vậy đặt `SQLXML` trực tiếp trong `try-with-resources` không biên dịch khi dùng `javac --release 17`. Java SE 26 đã cho `SQLXML extends AutoCloseable` và thêm `close()`. `free()` vẫn là API hiện hành, chạy được trên Java 17+, nên bài học dùng `try/finally` với `free()` để tương thích.

## 2. API quan trọng của SQLXML

| API | Dữ liệu nhận/trả | Mục đích và lifecycle |
| --- | --- | --- |
| `Connection.createSQLXML()` | `SQLXML` | Tạo một giá trị XML để **ghi** |
| `ResultSet.getSQLXML(index/label)` | `SQLXML` hoặc `null` | Đọc giá trị cột XML, SQL NULL trả null |
| `SQLXML.setString(xml)` | Nhận `String` | Ghi một lần bằng nội dung đã có sẵn |
| `SQLXML.setCharacterStream()` | Trả `Writer` | Ghi XML bằng ký tự Unicode, **đóng Writer trước execute** |
| `SQLXML.setBinaryStream()` | Trả `OutputStream` | Ghi XML bằng bytes, **đóng OutputStream trước execute** |
| `SQLXML.setResult(...)` | Trả XML `Result` | DOM/SAX/StAX/Stream transformation, phải hoàn thành trước execute |
| `SQLXML.getString()` | Trả `String` | Đọc XML một lần, có thể materialize toàn bộ |
| `SQLXML.getCharacterStream()` | Trả `Reader` | Đọc ký tự XML; đóng Reader trước khi free |
| `SQLXML.getBinaryStream()` | Trả `InputStream` | Đọc XML bytes theo XML encoding rules |
| `SQLXML.getSource(...)` | Trả XML `Source` | Đọc XML qua DOM/SAX/StAX/Stream |
| `PreparedStatement.setSQLXML(...)` | Nhận `SQLXML` | Bind giá trị XML vào parameter |
| `SQLXML.free()` | Không trả giá trị | Giải phóng XML/driver resources |
| `SQLXML.close()` | Không trả giá trị | Có ở Java SE mới; không dùng cho code target Java 17 |

Những phương thức này là **JDBC API chuẩn** còn đang áp dụng. Việc driver/database có hỗ trợ SQL XML thật hoặc hỗ trợ một `Source`/`Result` cụ thể cần được kiểm thử theo driver. `SQLFeatureNotSupportedException` có thể xuất hiện đối với một khả năng chưa hỗ trợ.

### 2.1. Một SQLXML không phải một StringBuilder được đọc/ghi vô hạn

Theo JavaDoc, đọc/ghi XML thông qua SQLXML có trạng thái khái niệm **readable** và **writable**; việc đọc/ghi có thể xảy ra tối đa một lần. Khi gọi một read method như `getString`, `getCharacterStream`, `getBinaryStream`, `getSource`, state chuyển sang **not readable**; tương tự một write method khiến state chuyển sang **not writable**. Implementation có thể đồng thời hạn chế state còn lại.

Vì vậy tránh:

~~~java
String first = sqlxml.getString();
Reader second = sqlxml.getCharacterStream(); // không portable
~~~

Đây là **anti-pattern**, không phải hai cách đọc độc lập được bảo đảm. Chọn một đường đọc và nếu cần sử dụng lại nội dung, chuyển sang representation do ứng dụng sở hữu trong scope hợp lệ. Đừng giữ một SQLXML locator rồi cố đọc nhiều lần sau transaction.

### 2.2. Reader/Writer không đồng nghĩa InputStream/OutputStream

`Reader` và `Writer` thao tác **ký tự Java**, không nhận một charset cho mỗi lời gọi. `InputStream` và `OutputStream` thao tác **bytes**, với encoding của XML theo XML 1.0. Nếu XML có declaration `encoding="UTF-8"`, hãy chắc chắn bytes gửi qua `setBinaryStream` thực sự là UTF-8; không dùng platform-default charset tùy tiện.

Ví dụ một XML value:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<note>Xin chào &amp; JDBC 🚀</note>
~~~

Với `Reader`, ký tự emoji có thể được biểu diễn bởi hai UTF-16 code units trong Java; với `InputStream`, emoji được mã hóa thành nhiều bytes UTF-8. Một database có thể serialize XML theo hình thức bytes khác nhưng vẫn có cùng **nội dung XML có ý nghĩa**.

## 3. Mẫu ghi Writer đúng chuẩn trên Java 17+

Khi đã có `Connection connection` và cột XML thích hợp:

~~~java
SQLXML xml = connection.createSQLXML();
try {
    try (Writer writer = xml.setCharacterStream()) {
        writer.write("<note>Xin chào &amp; JDBC</note>");
    } // Writer đóng trước bind/execute

    try (PreparedStatement ps = connection.prepareStatement(
            "INSERT INTO xml_documents(id, payload) VALUES (?, ?)")) {
        ps.setLong(1, 42L);
        ps.setSQLXML(2, xml);
        ps.executeUpdate();
    }
} finally {
    xml.free();
}
~~~

**Đây là snippet tích hợp**, chưa phải chương trình độc lập: cần import `java.sql.SQLXML`, `java.sql.PreparedStatement`, `java.io.Writer` và database có bảng `xml_documents(id,payload)`. Nếu driver hỗ trợ, các bước xảy ra theo thứ tự:

- Tạo SQLXML trên connection.
- Lấy Writer qua `setCharacterStream` và viết toàn bộ tài liệu.
- `try-with-resources` đóng Writer, kể cả khi `write` có exception.
- Sau đó mới bind SQLXML vào `PreparedStatement`, rồi execute.
- Free SQLXML **sau khi execute hoàn tất**; đóng/trả connection theo owner lớn hơn.

**Không free SQLXML ngay sau `ps.setSQLXML` mà trước `executeUpdate`**, vì driver có thể chỉ tiêu thụ giá trị lúc execute. `setSQLXML` chưa chắc đã chuyển toàn bộ XML tới server.

### 3.1. Đóng Writer chưa đủ nếu dữ liệu không hoàn chỉnh

Nếu `writer.write(...)` hoặc `writer.close()` ném `IOException`, không được tiếp tục execute XML chưa hoàn chỉnh. XML invalid cũng có thể được driver phát hiện lúc `setSQLXML` hoặc `executeUpdate`. `flush()` **không thay thế `close()`**: flush không phải tín hiệu kết thúc stream.

Anti-pattern:

~~~java
SQLXML xml = connection.createSQLXML();
try {
    try (Writer writer = xml.setCharacterStream()) {
        writer.write("<note>unfinished</note>");
        ps.setSQLXML(1, xml);
        ps.executeUpdate(); // execute khi Writer còn mở: sai thứ tự
    }
} finally {
    xml.free();
}
~~~

Đoạn này minh họa lỗi. Đặt lời gọi `setSQLXML`/`executeUpdate` **bên ngoài scope Writer**. Theo tài liệu JDBC, streams ghi XML phải đóng trước execute; một implementation có thể phát `SQLException` sớm hơn ngay khi bind.

### 3.2. Tại sao cần finally với SQLXML?

`SQLXML.free()` giải phóng tài nguyên XML kể cả khi bind/execute thất bại. Trên Java 17, SQLXML không phải `AutoCloseable`, nên dùng `finally`. Trên Java SE 26, `close()` đã được hỗ trợ; tuy vậy `free()` vẫn là lựa chọn portable cho code cần build bằng `--release 17`.

Khi cleanup trong production, phải xử lý khả năng `free()` cũng phát `SQLException`. `finally` đơn giản có thể che khuất exception chính nếu cleanup cũng lỗi; một helper quản lý suppressed exceptions hoặc resource lifecycle của framework có thể cần thiết.

## 4. Mẫu đọc Reader đúng thứ tự

Khi dùng `ResultSet rs` có row hợp lệ:

~~~java
SQLXML xml = rs.getSQLXML("payload");
if (xml != null) {
    try {
        try (Reader reader = xml.getCharacterStream()) {
            // Đọc hoặc parse XML khi ResultSet vẫn mở.
        } // Reader.close()
    } finally {
        xml.free();
    }
}
~~~

Đây là snippet trong transaction/query đang mở. **Luồng đọc không được trả ra ngoài scope nếu ResultSet/connection sẽ đóng trước khi caller dùng xong**.

Một mẫu bao quanh đầy đủ:

~~~java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT payload FROM xml_documents WHERE id = ?")) {
    ps.setLong(1, 42L);
    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            SQLXML xml = rs.getSQLXML(1);
            if (xml != null) {
                try {
                    try (Reader reader = xml.getCharacterStream()) {
                        // Xử lý document.
                    }
                } finally {
                    xml.free();
                }
            }
        }
    }
}
~~~

Khi `ResultSet.getSQLXML(...)` trả `null`, cột chứa SQL NULL; không gọi `getCharacterStream()` hoặc `free()` trên null. Nếu dữ liệu lớn, đọc tuần tự theo buffer hoặc parser. `Reader.transferTo(StringWriter)` tiện trong demo nhưng vẫn materialize toàn XML trong RAM.

### 4.1. Reader phải kết thúc trước ResultSet

Một số JDBC driver dùng locator/cursor/transaction để cung cấp dữ liệu XML. Nếu đóng `ResultSet` hoặc trả connection về pool khi Reader vẫn đang đọc, phần còn lại có thể không truy cập được.

**Đúng:** Reader.close → SQLXML.free → ResultSet.close → Statement.close → Connection.close/return pool.

**Sai:** đóng ResultSet trước, rồi trả Reader cho một thread khác tiếp tục sử dụng.

### 4.2. Lấy XML dạng String khi nào?

Với XML rất nhỏ:

~~~java
SQLXML xml = rs.getSQLXML(1);
if (xml != null) {
    try {
        String document = xml.getString(); // một cách đọc
        // Xử lý document.
    } finally {
        xml.free();
    }
}
~~~

Đây là snippet, không phải lệnh chạy độc lập. `getString` có thể gây cấp phát lớn với tài liệu hàng MB/GB. Nếu cần streaming, ưu tiên Reader/StAX/SAX và kiểm chứng khả năng streaming thật của driver.

## 5. Binary stream: hoàn thành bytes trước execute

Đường ghi bằng bytes tương tự Writer:

~~~java
SQLXML xml = connection.createSQLXML();
try {
    byte[] bytes = """
            <?xml version="1.0" encoding="UTF-8"?>
            <note>Tiếng Việt</note>
            """.getBytes(StandardCharsets.UTF_8);

    try (OutputStream output = xml.setBinaryStream()) {
        output.write(bytes);
    }
    try (PreparedStatement ps = connection.prepareStatement(
            "INSERT INTO xml_documents(payload) VALUES (?)")) {
        ps.setSQLXML(1, xml);
        ps.executeUpdate();
    }
} finally {
    xml.free();
}
~~~

Đây là snippet cần Java 17+, JDBC driver và schema, cùng import `java.io.OutputStream`, `StandardCharsets`. XML declaration và bytes phải nhất quán: ở đây dùng UTF-8. **Đóng OutputStream trước bind/execute**, không chỉ gọi `flush`.

Đường đọc:

~~~java
SQLXML xml = rs.getSQLXML(1);
if (xml != null) {
    try {
        try (InputStream input = xml.getBinaryStream()) {
            // Parse XML qua parser xử lý encoding, hoặc copy bytes.
        }
    } finally {
        xml.free();
    }
}
~~~

Lưu ý DB/driver có thể serialize lại XML thành bytes khác đầu vào; không dùng `Arrays.equals` trên original bytes và returned bytes như một bảo đảm semantic equality trong integration test. Với XML document có namespace/whitespace/encoding khác cách biểu diễn mà tương đương về nội dung, nên kiểm tra cấu trúc bằng parser an toàn hoặc canonicalization khi phù hợp.

## 6. Source/Result, XML parser và security

`SQLXML.getSource` và `setResult` cho phép làm việc với `DOMSource`, `StAXSource`, `SAXSource`, `StreamSource`, `DOMResult`, `StAXResult`, `SAXResult`, `StreamResult` tùy khả năng driver. Ví dụ:

~~~java
DOMSource source = xml.getSource(DOMSource.class);
Document document = (Document) source.getNode();
~~~

Đây là snippet, cần import `javax.xml.transform.dom.DOMSource` và `org.w3c.dom.Document`. Với ghi, `sqlxml.setResult(StAXResult.class)` có thể cấp `XMLStreamWriter`; phải kết thúc document và hoàn tất writer/output trước execute.

Không giả định mọi `Result` có method `close()` giống Writer: `DOMResult` là holder của DOM node, còn `StAXResult` chứa writer. Tuân thủ cách hoàn tất của API tương ứng và tài liệu driver, đồng thời đảm bảo **mọi stream mở để ghi XML đã được đóng trước execute**.

Nếu XML không tin cậy, phải cấu hình parser chống **XXE/external entities/DTD expansion**, giới hạn kích thước, độ sâu và thời gian xử lý. Ví dụ StAX:

~~~java
XMLInputFactory factory = XMLInputFactory.newFactory();
factory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
factory.setProperty(
        XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
~~~

Đây là snippet. Nếu parser không hỗ trợ thuộc tính bảo mật bắt buộc, nên từ chối xử lý hoặc chọn provider an toàn khác; không âm thầm parse external entities. Đừng coi việc dữ liệu đi qua `SQLXML` là cơ chế bảo vệ khỏi XXE.

### 6.1. Đóng StAX parser không tự thay thế việc đóng Reader

Một thứ tự khi parse:

~~~text
rs.getSQLXML
  -> xml.getCharacterStream()
  -> XMLInputFactory.createXMLStreamReader(reader)
  -> parser.next() ...
  -> XMLStreamReader.close()
  -> Reader.close()
  -> SQLXML.free()
  -> ResultSet.close()
~~~

`XMLStreamReader.close()` không được giả định sẽ tự đóng Reader do ứng dụng cấp. Nếu Reader có riêng ownership, phải dùng `try-with-resources` cho Reader bên ngoài scope parser. SAX/DOM/Transformer cũng có contract tương tự về InputSource/StreamSource, output streams và parser lifecycle.

## 7. Ví dụ Java 17+ tự chạy: strict test double xác minh thứ tự

### 7.1. Cơ chế kiểm thử

JDK có `java.sql.SQLXML` interface, nhưng không có một database XML nào được đảm bảo sẵn trên mọi máy. Để học nguyên lý đóng stream và API state, ví dụ `SqlXmlResourceDemo.java` tạo **strict in-memory test double**:

- `StrictXml` implement `SQLXML` nhưng chỉ lưu nội dung trong Java memory.
- `setCharacterStream` và `setBinaryStream` trả Writer/OutputStream ghi dữ liệu và chỉ đánh dấu complete **khi close**.
- Proxy `PreparedStatement` từ chối bind nếu stream còn mở; ghi lại thời điểm bind/execute.
- Proxy `ResultSet` tạo một SQLXML dành cho đọc, cho phép một lần đọc rồi chặn lần hai.
- `free` đánh dấu object đã hết hiệu lực.
- Event logs ghi rõ thứ tự `writer.close`, `sqlxml.bind`, `statement.execute`, `sqlxml.free`, `statement.close`; tương tự với Reader và binary streams.

Đây là **test double** của logic application, **không** kết nối database và không khẳng định driver production nội bộ làm giống proxy. Nó chỉ sử dụng Java SE 17+ và đã được biên dịch/chạy bằng JDK 24.

### 7.2. Code hoàn chỉnh: `SqlXmlResourceDemo.java`

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.Reader;
import java.io.StringReader;
import java.io.StringWriter;
import java.io.Writer;
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Proxy;
import java.nio.charset.StandardCharsets;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;
import java.sql.SQLXML;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import javax.xml.transform.Result;
import javax.xml.transform.Source;

public class SqlXmlResourceDemo {
    private static final String XML =
            "<note>Xin ch\u00E0o &amp; JDBC \uD83D\uDE80</note>";

    static final class StrictXml implements SQLXML {
        private final List<String> events;
        private final boolean fromDatabase;
        private String content;
        private boolean writingStarted;
        private boolean writingDone;
        private boolean readDone;
        private boolean freed;

        StrictXml(List<String> events) {
            this.events = events;
            this.fromDatabase = false;
        }

        StrictXml(String content, List<String> events) {
            this.events = events;
            this.fromDatabase = true;
            this.content = content;
        }

        private void live() throws SQLException {
            if (freed) throw new SQLException("SQLXML freed");
        }

        private void mayWrite() throws SQLException {
            live();
            if (fromDatabase || writingStarted) {
                throw new SQLException("SQLXML not writable");
            }
            writingStarted = true;
        }

        private void mayRead() throws SQLException {
            live();
            if (!fromDatabase || readDone) {
                throw new SQLException("SQLXML not readable");
            }
            readDone = true;
        }

        boolean isComplete() {
            return !freed && writingDone;
        }

        String writtenValue() {
            return content;
        }

        @Override public Writer setCharacterStream() throws SQLException {
            mayWrite();
            StringBuilder buffer = new StringBuilder();
            return new Writer() {
                private boolean closed;
                private void ensureOpen() throws IOException {
                    if (closed) throw new IOException("Writer closed");
                }
                @Override public void write(char[] chars, int off, int len)
                        throws IOException {
                    ensureOpen();
                    buffer.append(chars, off, len);
                }
                @Override public void flush() throws IOException {
                    ensureOpen();
                }
                @Override public void close() {
                    if (!closed) {
                        closed = true;
                        content = buffer.toString();
                        writingDone = true;
                        events.add("writer.close");
                    }
                }
            };
        }

        @Override public OutputStream setBinaryStream() throws SQLException {
            mayWrite();
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            return new OutputStream() {
                private boolean closed;
                private void ensureOpen() throws IOException {
                    if (closed) throw new IOException("OutputStream closed");
                }
                @Override public void write(int b) throws IOException {
                    ensureOpen();
                    bytes.write(b);
                }
                @Override public void write(byte[] b, int off, int len)
                        throws IOException {
                    ensureOpen();
                    bytes.write(b, off, len);
                }
                @Override public void close() {
                    if (!closed) {
                        closed = true;
                        content = bytes.toString(StandardCharsets.UTF_8);
                        writingDone = true;
                        events.add("output.close");
                    }
                }
            };
        }

        @Override public Reader getCharacterStream() throws SQLException {
            mayRead();
            return new StringReader(content) {
                private boolean closed;
                @Override public void close() {
                    if (!closed) {
                        closed = true;
                        events.add("reader.close");
                    }
                    super.close();
                }
            };
        }

        @Override public InputStream getBinaryStream() throws SQLException {
            mayRead();
            return new ByteArrayInputStream(content.getBytes(
                    StandardCharsets.UTF_8)) {
                private boolean closed;
                @Override public void close() throws IOException {
                    if (!closed) {
                        closed = true;
                        events.add("input.close");
                    }
                    super.close();
                }
            };
        }

        @Override public String getString() throws SQLException {
            mayRead();
            return content;
        }

        @Override public void setString(String value) throws SQLException {
            mayWrite();
            content = value;
            writingDone = true;
            events.add("setString");
        }

        @Override public <T extends Source> T getSource(Class<T> cls)
                throws SQLException {
            throw new SQLFeatureNotSupportedException("getSource");
        }

        @Override public <T extends Result> T setResult(Class<T> cls)
                throws SQLException {
            throw new SQLFeatureNotSupportedException("setResult");
        }

        @Override public void free() {
            if (!freed) {
                freed = true;
                events.add("sqlxml.free");
            }
        }
    }

    static PreparedStatement statement(List<String> events) {
        final String[] bound = {null};
        InvocationHandler handler = (proxy, method, args) -> {
            return switch (method.getName()) {
                case "setSQLXML" -> {
                    StrictXml xml = (StrictXml) args[1];
                    if (!xml.isComplete()) {
                        throw new SQLException("Close XML writer before bind");
                    }
                    bound[0] = xml.writtenValue();
                    events.add("sqlxml.bind");
                    yield null;
                }
                case "executeUpdate" -> {
                    if (bound[0] == null) {
                        throw new SQLException("No XML bound");
                    }
                    events.add("statement.execute");
                    yield 1;
                }
                case "close" -> {
                    events.add("statement.close");
                    yield null;
                }
                default -> throw new SQLFeatureNotSupportedException(
                        method.getName());
            };
        };
        return (PreparedStatement) Proxy.newProxyInstance(
                PreparedStatement.class.getClassLoader(),
                new Class<?>[] {PreparedStatement.class}, handler);
    }

    static ResultSet resultSet(String value, List<String> events) {
        final boolean[] advanced = {false};
        InvocationHandler handler = (proxy, method, args) -> {
            return switch (method.getName()) {
                case "next" -> !advanced[0] && (advanced[0] = true);
                case "getSQLXML" -> new StrictXml(value, events);
                case "close" -> {
                    events.add("resultset.close");
                    yield null;
                }
                default -> throw new SQLFeatureNotSupportedException(
                        method.getName());
            };
        };
        return (ResultSet) Proxy.newProxyInstance(
                ResultSet.class.getClassLoader(),
                new Class<?>[] {ResultSet.class}, handler);
    }

    public static void main(String[] args) throws Exception {
        List<String> writeEvents = new ArrayList<>();
        StrictXml forWrite = new StrictXml(writeEvents);
        try (PreparedStatement ps = statement(writeEvents)) {
            try {
                try (Writer writer = forWrite.setCharacterStream()) {
                    writer.write(XML);
                    try {
                        ps.setSQLXML(1, forWrite);
                        throw new AssertionError("Open Writer accepted");
                    } catch (SQLException expected) {
                        System.out.println(
                                "Open Writer before bind: rejected");
                    }
                }
                ps.setSQLXML(1, forWrite);
                System.out.println("Character bind complete: "
                        + forWrite.isComplete());
                System.out.println("Execute update count: "
                        + ps.executeUpdate());
            } finally {
                forWrite.free();
            }
        }
        System.out.println("Write close order: "
                + String.join(" > ", writeEvents));

        List<String> readEvents = new ArrayList<>();
        try (ResultSet rs = resultSet(XML, readEvents)) {
            if (!rs.next()) throw new AssertionError("No row");
            SQLXML fromDb = rs.getSQLXML(1);
            try {
                StringWriter text = new StringWriter();
                try (Reader reader = fromDb.getCharacterStream()) {
                    reader.transferTo(text);
                }
                System.out.println("Character Reader intact: "
                        + XML.equals(text.toString()));
                try {
                    fromDb.getString();
                    throw new AssertionError("Second read accepted");
                } catch (SQLException expected) {
                    System.out.println("Second read: rejected");
                }
            } finally {
                fromDb.free();
            }
            try {
                fromDb.getString();
                throw new AssertionError("Read after free accepted");
            } catch (SQLException expected) {
                System.out.println("Read after free: rejected");
            }
        }
        System.out.println("Read close order: "
                + String.join(" > ", readEvents));

        List<String> binaryEvents = new ArrayList<>();
        StrictXml binary = new StrictXml(binaryEvents);
        try (PreparedStatement ps = statement(binaryEvents)) {
            try {
                try (OutputStream output = binary.setBinaryStream()) {
                    output.write(XML.getBytes(StandardCharsets.UTF_8));
                }
                ps.setSQLXML(1, binary);
                ps.executeUpdate();
            } finally {
                binary.free();
            }
        }
        List<String> binaryReadEvents = new ArrayList<>();
        try (ResultSet rs = resultSet(XML, binaryReadEvents)) {
            if (!rs.next()) throw new AssertionError("No binary row");
            SQLXML fromDb = rs.getSQLXML(1);
            try {
                try (InputStream input = fromDb.getBinaryStream()) {
                    byte[] bytes = input.readAllBytes();
                    System.out.println("Binary UTF-8 intact: "
                            + Arrays.equals(bytes,
                                    XML.getBytes(StandardCharsets.UTF_8)));
                }
            } finally {
                fromDb.free();
            }
        }
        System.out.println("Binary write order: "
                + String.join(" > ", binaryEvents));
        System.out.println("Binary read order: "
                + String.join(" > ", binaryReadEvents));
        System.out.println("Test double only (no database): true");
    }
}
~~~

### 7.3. Lệnh chạy và output chính xác

Lưu đúng tên `SqlXmlResourceDemo.java` rồi chạy trong thư mục chứa file:

~~~sh
javac --release 17 SqlXmlResourceDemo.java
java SqlXmlResourceDemo
~~~

**Stdout chính xác** đã kiểm chứng khi biên dịch bằng `javac --release 17` và chạy trên JDK 24:

~~~text
Open Writer before bind: rejected
Character bind complete: true
Execute update count: 1
Write close order: writer.close > sqlxml.bind > statement.execute > sqlxml.free > statement.close
Character Reader intact: true
Second read: rejected
Read after free: rejected
Read close order: reader.close > sqlxml.free > resultset.close
Binary UTF-8 intact: true
Binary write order: output.close > sqlxml.bind > statement.execute > sqlxml.free > statement.close
Binary read order: input.close > sqlxml.free > resultset.close
Test double only (no database): true
~~~

Các dòng thể hiện ý nghĩa cụ thể:

- `Open Writer before bind: rejected`: strict test double từ chối bind trước Writer.close.
- `Write close order`: hoàn tất Writer rồi mới bind, execute, free SQLXML và đóng statement.
- `Second read: rejected`: SQLXML read path không được giả định có khả năng replay.
- `Read after free: rejected`: SQLXML không còn hợp lệ sau free.
- `Binary UTF-8 intact: true`: các bytes UTF-8 được giữ chính xác **trong in-memory fixture**; không khẳng định DB thật sẽ serialize y hệt bytes.
- Các event logs cho thấy Reader/InputStream đóng trước SQLXML.free và ResultSet.close.
- `Test double only` nhắc rõ không có driver/database round-trip ở chương trình này.

Unicode trong source được biểu diễn qua `\u00E0` và `\uD83D\uDE80` để compiler có thể đọc file ASCII; khi runtime, đó là ký tự “à” và emoji 🚀 thật. Một phép biên dịch Java 17 riêng đã xác nhận cả dấu và supplementary code point.

## 8. Ví dụ JDBC thật có cấu hình bảo vệ: LiveSqlXmlProbe

Nếu có database/driver hỗ trợ cột SQL `XML`, một chương trình thật có thể được viết như sau. Chương trình không tự tạo bảng; trước khi chạy phải có bảng `xml_documents(id, payload)`, trong đó `id` nhận UUID dạng chuỗi và `payload` nhận SQL XML value.

### 8.1. Source hoàn chỉnh: `LiveSqlXmlProbe.java`

~~~java
import java.io.Reader;
import java.io.StringWriter;
import java.io.Writer;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLXML;
import java.util.Properties;
import java.util.UUID;

public class LiveSqlXmlProbe {
    public static void main(String[] args) throws Exception {
        String url = System.getenv("JDBC_URL");
        if (url == null || url.isBlank()) {
            System.out.println(
                    "Set JDBC_URL and install a JDBC XML-capable driver.");
            return;
        }
        Properties props = new Properties();
        String user = System.getenv("JDBC_USER");
        String password = System.getenv("JDBC_PASSWORD");
        if (user != null) props.setProperty("user", user);
        if (password != null) props.setProperty("password", password);

        try (Connection connection =
                     DriverManager.getConnection(url, props)) {
            String id = UUID.randomUUID().toString();
            SQLXML value = connection.createSQLXML();
            try {
                try (Writer writer = value.setCharacterStream()) {
                    writer.write("<note>Xin ch\u00E0o &amp; JDBC</note>");
                }

                try (PreparedStatement ps = connection.prepareStatement(
                        "INSERT INTO xml_documents(id, payload) VALUES (?, ?)")) {
                    ps.setString(1, id);
                    ps.setSQLXML(2, value);
                    ps.executeUpdate();
                }
            } finally {
                value.free();
            }

            try (PreparedStatement ps = connection.prepareStatement(
                    "SELECT payload FROM xml_documents WHERE id = ?")) {
                ps.setString(1, id);
                try (ResultSet rs = ps.executeQuery()) {
                    if (rs.next()) {
                        SQLXML fromDb = rs.getSQLXML(1);
                        if (fromDb != null) {
                            try {
                                StringWriter output = new StringWriter();
                                try (Reader reader =
                                             fromDb.getCharacterStream()) {
                                    reader.transferTo(output);
                                }
                                System.out.println(
                                        "Read XML characters: "
                                        + output.toString().length());
                            } finally {
                                fromDb.free();
                            }
                        }
                    }
                }
            }
        }
    }
}
~~~

### 8.2. Biên dịch và giới hạn kiểm thử

~~~sh
javac --release 17 LiveSqlXmlProbe.java
java LiveSqlXmlProbe
~~~

Đã biên dịch thành công trên JDK 24. Nếu **`JDBC_URL` chưa được cấu hình**, stdout chính xác:

~~~text
Set JDBC_URL and install a JDBC XML-capable driver.
~~~

Nhánh guard đã được chạy. Chưa có driver/database/XML schema được cung cấp để thực hiện SQL thật, nên **không tuyên bố đã kiểm tra live round-trip**. Khi có driver, đặt `JDBC_URL`, `JDBC_USER` và `JDBC_PASSWORD` phù hợp, thêm JDBC driver JAR vào runtime classpath. Đừng ghi cứng credentials trong mã nguồn hoặc log.

Một lệnh mẫu Linux/macOS:

~~~sh
java -cp ".:/path/to/driver.jar" LiveSqlXmlProbe
~~~

Trên Windows, classpath separator là `;`, ví dụ:

~~~text
java -cp ".;C:\drivers\driver.jar" LiveSqlXmlProbe
~~~

Đường dẫn JAR chỉ để minh họa. DBMS có thể serialize lại XML (khác declaration, namespace prefixes, whitespace) và có thể không hỗ trợ tất cả phương thức `SQLXML`. Chương trình in **số ký tự XML thực tế đọc được**, không đặt một stdout giả định cho database chưa được kiểm thử.

## 9. Thứ tự đóng khi dùng Source/Result với StAX

Nếu dùng parser xử lý XML lớn:

~~~text
SQLXML.getCharacterStream
  -> XMLInputFactory.createXMLStreamReader(reader)
  -> XMLStreamReader.next() ...
  -> XMLStreamReader.close()
  -> Reader.close()
  -> SQLXML.free()
  -> ResultSet.close()
~~~

Một snippet:

~~~java
XMLInputFactory factory = XMLInputFactory.newFactory();
factory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
factory.setProperty(
        XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);

SQLXML xml = rs.getSQLXML(1);
if (xml != null) {
    try {
        try (Reader reader = xml.getCharacterStream()) {
            XMLStreamReader parser =
                    factory.createXMLStreamReader(reader);
            try {
                while (parser.hasNext()) {
                    parser.next();
                }
            } finally {
                parser.close();
            }
        }
    } finally {
        xml.free();
    }
}
~~~

Đây là snippet trong context có `ResultSet rs` và `javax.xml.stream` imports. Khi thực thi thật, bổ sung giới hạn kích thước/depth/processing time; không dùng XMLInputFactory chưa harden trên XML không tin cậy. Nếu parser provider không hỗ trợ các thuộc tính bảo mật bắt buộc, hãy **fail closed**.

StAX parser.close không nhất thiết đóng Reader đầu vào, nên đóng **cả hai** theo ownership. Nếu sử dụng SAX/DOM/Transformer, xem contract của API tương ứng và đừng để ResultSet đóng khi parser còn đọc.

## 10. Error handling khi stream và SQLXML cùng phát lỗi

| Giai đoạn | Lỗi có thể gặp | Cách xử lý |
| --- | --- | --- |
| `Connection.createSQLXML` | `SQLFeatureNotSupportedException`, connection lỗi | Kiểm tra driver và kiểu SQL XML |
| `setCharacterStream/setBinaryStream` | State không writable, driver lỗi | Dừng operation và cleanup |
| `Writer.write/OutputStream.write` | `IOException` | Không bind XML không hoàn chỉnh |
| `Writer.close/OutputStream.close` | Lỗi finalize/flush | Không execute; giải phóng tài nguyên |
| `PreparedStatement.setSQLXML` | Đầu ghi chưa đóng, type mismatch | Đảm bảo thứ tự và schema đúng |
| `executeUpdate` | XML invalid, DB/transaction error | Xử lý `SQLException`, rollback nếu cần |
| `ResultSet.getSQLXML` | SQL NULL hoặc driver error | Kiểm tra null |
| `getCharacterStream/getBinaryStream` | SQLXML đã đọc, đã free, không readable | Tôn trọng state một lần |
| `Reader.read/InputStream.read` | `IOException`/parse error | Đóng stream và free trong finally |
| `SQLXML.free` | `SQLException` cleanup | Log/suppress đúng để không che nguyên nhân |

Với `try-with-resources`, nếu code trong try ném exception và `close` cũng lỗi, Java có cơ chế **suppressed exceptions**. Với `SQLXML.free` gọi trong `finally` trên Java 17, nếu free cũng ném exception khi một operation đang thất bại, cần thiết kế helper logging/suppressed handling để không che lỗi chính trong production.

Không catch `IOException` rồi tiếp tục `setSQLXML/execute` như không có gì xảy ra. Lúc đó document có thể chưa được viết đủ hoặc chưa được đóng đúng cách.

## 11. Transaction, connection pool và XML ownership

`SQLXML` có thể là logical locator hợp lệ trong **transaction tạo ra nó**. Không cache SQLXML làm field của entity hoặc đưa Reader của SQLXML sang thread khác sau khi transaction đã đóng.

Trong ứng dụng dùng pool:

~~~text
Borrow Connection
  -> create/get SQLXML
  -> write XML + close Writer hoặc read XML + close Reader
  -> execute/consume XML
  -> SQLXML.free()
  -> close ResultSet/Statement
  -> commit/rollback theo transaction policy
  -> return Connection to pool
~~~

Khi `Connection.close()` trên pooled handle, thường là **trả về pool** chứ không nhất thiết đóng physical socket. Nhưng các tài nguyên con như XML locator/Reader/ResultSet vẫn cần dọn sạch trước khi trả connection. Tránh truy cập SQLXML từ một request sau khi connection đã được pool tái cấp cho request khác.

Không chia sẻ cùng SQLXML mutable giữa nhiều threads; state readable/writable của nó không phải một cấu trúc thread-safe.

### 11.1. Nếu phải trả XML trong HTTP response

Không làm:

~~~java
Reader stream = xml.getCharacterStream();
xml.free();
return stream; // Reader có thể đã vô hiệu
~~~

Đây là **anti-pattern**. Nếu HTTP streaming cần duy trì kết nối DB suốt quá trình gửi, phải có lifecycle/timeout/backpressure rõ ràng. Cách đơn giản hơn với XML nhỏ là materialize một representation hợp lệ trong scope JDBC rồi đóng DB trước khi trả response. Với XML lớn, xây streaming pipeline có ownership xuyên request và kiểm soát hủy giữa chừng, không return một Reader JDBC bị orphan.

## 12. Performance: stream không tự bảo đảm không buffer

Dùng `getCharacterStream` không mặc nhiên chứng minh driver streaming end-to-end. Driver có thể materialize XML trước, sau đó cấp Reader trên buffer. Ngược lại, `getSource`/`setResult` có thể cho phép driver tối ưu không cần serialize/parse lại.

Khi tối ưu, đo:

- Memory peak và GC với XML nhỏ/lớn.
- Latency của `createSQLXML`, `setSQLXML`, `execute` và XML parser.
- Số bytes/network round trips.
- Backpressure: XML parse chậm giữ connection pool slot bao lâu.
- Kết quả khi đóng Reader sớm hoặc hủy request.
- Khả năng streaming thực tế và việc database serialize lại XML.
- Chi phí DOM tree so với SAX/StAX event-based processing.

Với dữ liệu rất lớn, tránh `Reader.transferTo(StringWriter)` trong hot path nếu không có memory budget; dùng writer/file hoặc event processor theo nhu cầu. Test demo dùng `StringWriter` để assert chính xác một document ngắn, không phải pattern hiệu năng cho XML hàng GB.

## 13. Ma trận test trước khi dùng trên production

| Test | Cần gì? | Assertion |
| --- | --- | --- |
| Writer đóng đúng thứ tự | Unit test double | `writer.close` trước bind/execute |
| Bind khi Writer đang mở | Strict mock/driver integration | Bị từ chối hoặc không được phép trong code path |
| Binary OutputStream đóng | Unit/integration | `output.close` trước execute |
| Reader và SQLXML free | Unit/integration | Reader đóng trước `free` và ResultSet |
| InputStream và SQLXML free | Unit/integration | InputStream đóng trước `free` |
| Đọc hai lần cùng XML object | Unit/integration | Không phụ thuộc replay; xử lý `SQLException` |
| Dùng XML sau free | Unit/integration | Không truy cập nữa; driver có thể báo `SQLException` |
| SQL NULL | DB integration | `ResultSet.getSQLXML` trả null |
| XML không hợp lệ | DB integration | Lỗi được phát hiện ở giai đoạn phù hợp |
| Ký tự Việt, emoji | Java17/DB | Không mất Unicode, encoding nhất quán |
| Binary XML declaration khác encoding | Parser/DB | Validation không chấp nhận dữ liệu không nhất quán |
| XML không tin cậy | Hardened parser | DTD/entities ngoài bị từ chối |
| XML nhiều MB | Driver/database | Memory/latency trong giới hạn |
| Java17 build | JDK17 API | Dùng `free`, không yêu cầu `SQLXML.close` |
| Java26 build | JDK26 API | Có thể dùng AutoCloseable khi runtime được phép |
| Pool/transaction | DB integration | Không leak Reader, ResultSet, SQLXML hay connection |

Không thử kill connection trên production. Dùng môi trường tích hợp/CI với driver, database và schema riêng để kiểm tra lỗi/transaction semantics thật.

## 14. Những lỗi phổ biến cần nhớ

1. **Gọi execute khi Writer còn mở:** vi phạm thứ tự; đóng Writer trước.
2. **Gọi flush rồi tưởng XML hoàn tất:** flush không thay close.
3. **Free SQLXML trước execute:** driver có thể chưa dùng xong giá trị.
4. **Đóng ResultSet trước Reader:** Reader có thể phụ thuộc cursor/transaction.
5. **Trả JDBC Reader ra khỏi method đã đóng connection:** tạo dangling resource.
6. **Đọc lại cùng SQLXML bằng getter khác:** trạng thái one-read không đảm bảo.
7. **Để `SQLXML` trong try-with-resources khi `--release 17`:** không compile; dùng finally/free.
8. **Chỉ đóng XMLStreamReader mà không đóng source Reader:** có nguy cơ leak.
9. **Dùng getString cho XML cực lớn:** memory/GC tăng.
10. **Nhầm bytes với characters:** lỗi XML declaration/encoding.
11. **Mặc định parser cho XML ngoài:** có nguy cơ XXE/DTD expansion.
12. **Coi XML raw string equality là semantic equality:** DB có thể serialize lại.
13. **Nuốt IOException khi write hoặc close:** XML incomplete vẫn bị gửi đi.
14. **Quên cleanup trong nhánh exception:** mất cursor/LOB resource.
15. **Tưởng SQLXML luôn tồn tại ở mọi DBMS:** driver có thể không hỗ trợ SQL XML.
16. **Mock thành công rồi kết luận DB thật hỗ trợ:** phải có integration test.
17. **Lưu XML locator qua transaction:** object có thể không còn hợp lệ.
18. **Đóng connection trước khi consume XML:** data/Reader có thể hỏng.

## 15. Câu hỏi và bài tập tự kiểm tra

**Câu 1.** Khi dùng `SQLXML.setCharacterStream()`, đóng Writer trước hay sau `PreparedStatement.executeUpdate()`?

**Trả lời:** **Trước**, tốt nhất kết thúc scope Writer trước khi gọi `setSQLXML` hoặc `executeUpdate`.

**Câu 2.** `SQLXML.free()` có thay cho `Writer.close()` được không?

**Trả lời:** Không. Writer.close hoàn tất stream ghi; SQLXML.free giải phóng toàn object.

**Câu 3.** Thứ tự đọc đúng từ ResultSet là gì?

**Trả lời:** `ResultSet.getSQLXML` → `SQLXML.getCharacterStream` → đọc xong → `Reader.close` → `SQLXML.free` → `ResultSet.close`.

**Câu 4.** `sqlxml.getString()` rồi `sqlxml.getBinaryStream()` có portable không?

**Trả lời:** Không. Theo state rules, SQLXML có thể được đọc tối đa một lần; chọn một đường đọc.

**Câu 5.** `XMLStreamReader.close()` có đảm bảo đóng source Reader không?

**Trả lời:** Không được dựa vào điều đó. Đóng parser và Reader riêng, sau đó free SQLXML.

**Câu 6.** Trên Java 17, có thể viết `try (SQLXML x = connection.createSQLXML())` không?

**Trả lời:** Không; SQLXML Java 17 chưa `AutoCloseable`. Dùng `try/finally { x.free(); }`. Java mới có `SQLXML.close()` khi target release hỗ trợ.

**Câu 7.** `setBinaryStream` có cần theo XML encoding declaration không?

**Trả lời:** Có. Bytes phải đúng chuẩn XML encoding, không tự giải mã/ghi bằng platform default charset.

**Câu 8.** XML đã viết qua Writer mà `execute` ném SQLException, cần làm gì?

**Trả lời:** Đóng stream và SQLXML, xử lý transaction/rollback, ghi nhận SQLState/vendor code; không tiếp tục dùng XML incomplete hoặc giả định DB đã lưu thành công.

**Câu 9.** `getCharacterStream` có luôn ít tốn bộ nhớ hơn `getString` không?

**Trả lời:** Không được đảm bảo vì driver có thể buffer. Cần đo và chọn parser/driver strategy phù hợp.

**Câu 10.** Tại sao strict mock không chứng minh PostgreSQL/SQL Server/Oracle xử lý giống nhau?

**Trả lời:** Strict mock chỉ ghi các sự kiện Java trong bộ nhớ; driver thật có storage/transaction/parser semantics riêng. Phải chạy integration test với schema và version thực tế.

**Câu 11.** Nếu HTTP response muốn stream dữ liệu XML sau khi Connection đã được trả pool, nên làm gì?

**Trả lời:** Không trả thẳng Reader từ SQLXML đã free. Thiết kế streaming scope giữ connection còn hợp lệ đến khi hoàn tất hoặc materialize output độc lập trong scope JDBC.

**Câu 12.** Có thể an toàn parse XML do user cung cấp bằng DOM/StAX mặc định không?

**Trả lời:** Không nên. Cần chặn DTD/external entities, giới hạn kích thước/độ sâu/thời gian và fail closed khi parser không đáp ứng security policy.

**Ghi nhớ:** **Ghi SQLXML:** Writer/OutputStream đóng → bind `setSQLXML` → execute → `SQLXML.free()`. **Đọc SQLXML:** Reader/InputStream đóng → `SQLXML.free()` → ResultSet/Statement/Connection đóng. Tôn trọng state đọc/ghi một lần, xử lý lỗi cleanup và dùng `free()` để tương thích Java 17+. Khi XML tới từ bên ngoài, XML parser phải được harden, và driver/database cần integration tests riêng.

### Tài liệu chính thức (Java SE hiện hành)

- [Oracle Java SE 26 — SQLXML](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLXML.html): one-read/one-write state, streams phải đóng trước execute, free và close.
- [Oracle Java SE 17 — SQLXML](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLXML.html): API Java 17 dùng free().
- [Oracle Java SE 26 — PreparedStatement](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/PreparedStatement.html): setSQLXML và điều kiện Writer/OutputStream/Result đã hoàn tất.
- [Oracle Java SE 26 — ResultSet](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/ResultSet.html): getSQLXML, ResultSet lifetime.
- [Oracle Java SE 26 — Connection](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Connection.html): createSQLXML và tài nguyên connection.
- [Oracle Java SE 26 — XMLInputFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLInputFactory.html): StAX properties.
- [Oracle Java SE 26 — XMLStreamReader](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLStreamReader.html): parser và close.
