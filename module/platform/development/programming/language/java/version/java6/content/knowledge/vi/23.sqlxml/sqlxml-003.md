# SQLXML: PreparedStatement.setSQLXML và ResultSet.getSQLXML

## Mục tiêu học tập

Trong JDBC, **java.sql.SQLXML** là biểu diễn phía Java cho một giá trị kiểu **SQL XML** của database. Nó cho phép chương trình truyền và nhận XML bằng **String**, **Reader/Writer**, **InputStream/OutputStream** hoặc các API xử lý XML **Source/Result**. Hai thao tác quan trọng nhất khi làm việc với SQL XML columns là:

- **PreparedStatement.setSQLXML(int parameterIndex, SQLXML xmlObject)**: bind một giá trị SQLXML vào tham số của câu lệnh SQL.
- **ResultSet.getSQLXML(int columnIndex)** hoặc **getSQLXML(String columnLabel)**: lấy giá trị XML của cột tại dòng hiện tại dưới dạng SQLXML.

Để xây dựng SQLXML mới, ứng dụng dùng **Connection.createSQLXML()**, điền dữ liệu bằng một phương thức **set...** rồi bind đối tượng đó vào PreparedStatement. Để đọc, ứng dụng lấy SQLXML từ ResultSet, sử dụng **một phương thức get...** thích hợp rồi **free()** tài nguyên. Điều khác biệt với một String bình thường là **SQLXML có vòng đời, trạng thái chỉ đọc/ghi một lần và có thể là locator gắn với transaction/connection**.

Sau bài này, bạn sẽ:

1. Phân biệt SQL **XML type**, **SQLXML**, **CLOB**, **String** và tài nguyên XML của driver.
2. Tạo SQLXML bằng **Connection.createSQLXML()**, ghi bằng **setString**, **setCharacterStream**, **setBinaryStream** hoặc **setResult** và bind bằng **setSQLXML**.
3. Đọc XML qua **ResultSet.getSQLXML**, **getString**, **getCharacterStream**, **getBinaryStream** hoặc **getSource**, luôn xử lý SQL NULL.
4. Hiểu **nguyên tắc đọc/ghi một lần**, stream phải được đóng trước **execute** và **free()** sau khi sử dụng.
5. Phân biệt giới hạn giao diện JDBC với hỗ trợ thật của **driver/database/version**, nhất là column type và cách kiểm tra XML hợp lệ.
6. Sử dụng **StAX parser có cấu hình an toàn** khi XML đến từ nguồn không đáng tin; ngăn DOCTYPE/external entities và tránh XXE.
7. Chạy ví dụ Java 17+ có kiểm thử tự động bằng **in-memory JDBC test double**, sử dụng đúng chữ ký API, không đòi hỏi server hoặc credentials.
8. Áp dụng vào phương thức INSERT/SELECT dùng Connection thật và thiết kế integration tests với database được phép sử dụng.
9. Tránh các lỗi phổ biến: giải phóng quá sớm, đọc SQLXML hai lần, giữ SQLXML sau đóng ResultSet, copy XML quá lớn vào heap, nhầm lỗi parser với SQLException.

**Phạm vi:** Những API được trình bày vẫn được hỗ trợ trên JDK hiện đại. Ví dụ được biên dịch và chạy bằng **OpenJDK 24.0.2** với **javac --release 17**. Các khác biệt Java 17 và Java 26 về AutoCloseable được ghi rõ để không dùng một tính năng mới trong mã phải biên dịch với --release 17. Chỉ sử dụng kiến thức còn áp dụng hiện nay.

## 1. Bức tranh toàn cảnh: SQL XML từ ứng dụng đến database

Giả sử một bảng dữ liệu lưu bản XML mô tả một ghi chú:

~~~xml
<note lang="vi"><body>Xin chào &amp; Đặng</body></note>
~~~

Một SQL schema minh họa (cú pháp cụ thể tùy DBMS) có thể là:

~~~sql
CREATE TABLE messages (
    id BIGINT PRIMARY KEY,
    payload XML
);
~~~

**Cảnh báo về tính di động:** SQL XML type và cú pháp tạo column, XML indexing, namespaces, constraints và SQL functions khác nhau giữa database products. Không mặc định lệnh DDL trên chạy được nguyên xi ở mọi DBMS; xem tài liệu của database thực tế.

Dòng xử lý khi ghi:

~~~text
XML từ ứng dụng (String / Reader / Source)
                │
                ▼
      Connection.createSQLXML()
                │
     SQLXML.setString(...)
     hoặc setCharacterStream(...)
     hoặc setResult(...)
                │
                ▼
   PreparedStatement.setSQLXML(index, sqlxml)
                │
                ▼
        PreparedStatement.executeUpdate()
                │
                ▼
  Driver chuyển SQLXML thành SQL XML column value
                │
                ▼
      SQLXML.free() sau khi thao tác hoàn tất
~~~

Dòng xử lý khi đọc:

~~~text
Connection.prepareStatement("SELECT ...")
                  │
                  ▼
            executeQuery()
                  │
                  ▼
         ResultSet.next() == true
                  │
                  ▼
       ResultSet.getSQLXML("payload")
                  │
                  ├── null nếu SQL NULL
                  │
                  ▼
      SQLXML.getCharacterStream()
       hoặc getString(), getSource()
                  │
                  ▼
       Xử lý XML và đóng Reader/stream
                  │
                  ▼
            SQLXML.free()
                  │
                  ▼
     Đóng ResultSet / PreparedStatement
~~~

**Điểm cốt lõi:** một SQLXML Java object có thể giữ liên kết tới dữ liệu ở database thay vì chứa sẵn một Java String. Vì vậy nó không giống dữ liệu DTO có thể giữ bao lâu cũng được.

## 2. SQLXML, SQL XML type, String và CLOB khác nhau thế nào?

| Loại | Biểu diễn | Mục đích |
| --- | --- | --- |
| **SQL XML** | Kiểu dữ liệu của database | Lưu một giá trị XML theo semantics/khả năng của DBMS |
| **java.sql.SQLXML** | JDBC interface | Cầu nối giữa SQL XML value và Java API |
| **String** | Nội dung ký tự trong Java heap | Đơn giản với XML nhỏ, nhưng có thể tốn memory |
| **Reader/Writer** | Luồng ký tự | Xử lý văn bản XML theo phần, có quyền kiểm soát đọc/ghi |
| **InputStream/OutputStream** | Luồng bytes | Thích hợp khi xử lý XML encoding/binary source đã xác định rõ |
| **Clob** | JDBC character LOB | Dữ liệu ký tự dài, không tự có semantics của SQL XML type |
| **DOMSource / StAXSource / SAXSource** | javax.xml.transform.Source | Đưa dữ liệu XML tới các API xử lý XML |
| **DOMResult / StAXResult / SAXResult** | javax.xml.transform.Result | Nhận dữ liệu XML từ parser/transformer vào SQLXML |

**Không đồng nhất CLOB và SQL XML.** Một CLOB có thể chứa text giống XML nhưng database thường xem nó là chuỗi; SQL XML type có thể có validation/query/indexing riêng. Ngược lại, nếu DBMS không hỗ trợ SQL XML native, một hệ thống có thể chọn CLOB/JSON hay BLOB theo thiết kế dữ liệu, nhưng đó không còn là cùng một contract JDBC SQLXML.

Đối với một văn bản XML nhỏ, **SQLXML.setString(...)** dễ hiểu. Đối với XML lớn, nên xem các stream/Source/Result methods và đo cách driver xử lý thực tế. **API dạng stream không tự bảo đảm driver không buffer toàn bộ nội dung.**

### 2.1. SQL NULL khác một phần tử XML rỗng

Một column XML có thể là **SQL NULL**, khác với giá trị XML hợp lệ như **<empty/>**. Khi đọc:

~~~java
// Mảnh minh họa khi rs đang ở dòng hợp lệ.
SQLXML xml = rs.getSQLXML("payload");
if (xml == null) {
    // Column là SQL NULL; xử lý theo contract ứng dụng.
} else {
    try {
        // Đọc XML.
    } finally {
        xml.free();
    }
}
~~~

Khi ghi SQL NULL, dùng **PreparedStatement.setNull(index, java.sql.Types.SQLXML)** nếu driver hỗ trợ type này. Không thay một NULL có ý nghĩa nghiệp vụ bằng XML string rỗng hoặc một phần tử <empty/> mà không định nghĩa rõ.

## 3. Các API quan trọng

### 3.1. Connection.createSQLXML()

~~~java
SQLXML xml = connection.createSQLXML();
~~~

Phương thức này tạo đối tượng SQLXML **ban đầu chưa chứa dữ liệu**. Bạn phải ghi bằng một phương thức set phù hợp trước khi bind vào statement. Không được coi một SQLXML chưa khởi tạo là một XML document rỗng hợp lệ.

~~~java
// Mảnh minh họa.
SQLXML xml = connection.createSQLXML();
try {
    xml.setString("<note><body>Xin chào</body></note>");
    // Bind/execute trong khi xml còn hợp lệ.
} finally {
    xml.free();
}
~~~

**Connection.createSQLXML()** có thể ném SQLException hoặc **SQLFeatureNotSupportedException** nếu driver không hỗ trợ XML type/method. Một chương trình compile được với JDK không chứng minh database của nó hỗ trợ SQL XML.

### 3.2. PreparedStatement.setSQLXML(...)

~~~java
preparedStatement.setSQLXML(2, xml);
~~~

**parameterIndex tính từ 1**, không phải 0. Method nhận **SQLXML object**, không nhận một String trực tiếp. Khi execute, driver chuyển dữ liệu trong SQLXML sang SQL XML parameter phù hợp với database.

**Điểm rất quan trọng:** Nếu bạn tạo XML bằng **setCharacterStream()**, **setBinaryStream()** hoặc **setResult(...)**, phải hoàn tất việc ghi và đóng những stream/Writer hoặc hoàn thiện Result trước khi gọi **execute/executeUpdate/executeBatch**. SQLXML Javadoc và PreparedStatement Javadoc ghi rõ có thể ném SQLException nếu stream/Result chưa được đóng/hoàn tất.

Ví dụ dùng setString không có Writer cần đóng, nhưng bạn vẫn không được free SQLXML trước khi statement thực sự execute xong.

### 3.3. ResultSet.getSQLXML(...)

~~~java
SQLXML xmlByLabel = rs.getSQLXML("payload");
// Hoặc:
SQLXML xmlByIndex = rs.getSQLXML(2);
~~~

Đây là **hai cách lấy giá trị cột**, không phải lời khuyên gọi cả hai rồi đọc cả hai trên một driver/row cho cùng một dữ liệu lớn. Tên cột trong getter có thể là column label trong SELECT; index cũng bắt đầu từ 1.

Nếu column là NULL, getter trả null. Nếu column không tồn tại, result set đã đóng hoặc driver không hỗ trợ API, có thể ném SQLException/SQLFeatureNotSupportedException.

### 3.4. SQLXML.free()

~~~java
xml.free();
~~~

**free() giải phóng tài nguyên mà SQLXML object giữ**; nó **không thực hiện DELETE**, không tự rollback/commit, không hủy một XML value đã INSERT thành công và không xóa an toàn mọi bản sao XML trong Java heap. Sau khi free, các method khác của SQLXML không còn hợp lệ và phải báo SQLException theo contract.

Trong **Java SE 17**, interface **SQLXML chưa extends AutoCloseable** nên không được viết **try (SQLXML xml = ...)** khi dùng **--release 17**. Cách tương thích là **try/finally** để gọi **free()**.

Trong **Java SE 26**, SQLXML đã **extends AutoCloseable** và có default **close()**. Khi ứng dụng target đúng API mới, try-with-resources trực tiếp cho SQLXML là lựa chọn có hỗ trợ. Tuy nhiên bài này dùng free() để chạy được trên Java 17+.

## 4. Trạng thái chỉ đọc hoặc ghi một lần của SQLXML

Đây là **khác biệt lớn nhất** giữa SQLXML và Java String. Tài liệu SQLXML mô tả những method đọc/ghi có thể được thực hiện **tối đa một lần** cho một SQLXML instance.

### 4.1. Những cách đọc khác nhau, không phải chuỗi thao tác độc lập

Các phương thức đọc:

~~~java
xml.getString();
xml.getCharacterStream();
xml.getBinaryStream();
xml.getSource(DOMSource.class);
xml.getSource(StAXSource.class);
xml.getSource(SAXSource.class);
~~~

**Chọn một cách đọc phù hợp** cho một SQLXML object. Sau khi gọi **getString** hoặc **getCharacterStream**, trạng thái readable chuyển sang **not readable**. Đừng làm như sau:

~~~java
// SAI: không phải một contract đáng tin.
String text = xml.getString();
Reader reader = xml.getCharacterStream(); // Có thể SQLException.
~~~

Nếu cần vừa kiểm tra cấu trúc vừa tạo một String nhỏ, bạn có thể đọc một lần thành String rồi parse String bằng API XML; nhưng hãy giới hạn kích thước. Nếu cần nhiều cách đọc cho một XML lớn, bạn có thể re-query trong một transaction phù hợp, hoặc dùng một nguồn dữ liệu được ứng dụng quản lý. **Không giả định mỗi driver cho phép nhiều lần get... trên cùng SQLXML.**

### 4.2. Những cách ghi cũng chỉ chọn một

Các phương thức ghi:

~~~java
xml.setString("<note/>");
xml.setCharacterStream();
xml.setBinaryStream();
xml.setResult(DOMResult.class);
xml.setResult(StAXResult.class);
xml.setResult(SAXResult.class);
~~~

Chúng là **những lựa chọn thay thế**, không phải sáu bước gọi lần lượt. Một SQLXML được tạo mới có thể nhận **một lần setString** hoặc **một lần lấy Writer/Result để ghi**, sau đó không còn writable theo contract.

Ví dụ sai:

~~~java
// SAI: viết lại cùng SQLXML sau setString.
xml.setString("<a/>");
xml.setString("<b/>");
~~~

Nếu muốn đặt một XML mới, hãy yêu cầu **Connection.createSQLXML()** tạo một SQLXML object khác và quản lý vòng đời riêng.

### 4.3. Không assume đọc ngược ngay sau khi ghi

Sau khi gọi **setString(...)**, object chuyển sang trạng thái không ghi tiếp được. Implementation **có thể đồng thời không cho phép đọc ngược dữ liệu** trên chính instance vừa được ghi. Đừng viết integration test bắt mọi driver phải cho phép:

~~~java
// Không được kỳ vọng portable.
SQLXML x = connection.createSQLXML();
x.setString("<a/>");
String same = x.getString();
~~~

Cách xác nhận kết quả thật là **execute INSERT/UPDATE**, rồi query lại để nhận một SQLXML mới từ ResultSet. Test double trong bài có đường driver-internal riêng để mô phỏng lúc driver lấy dữ liệu bind, không phải sử dụng getString công khai trên object vừa ghi.

### 4.4. Bảng trạng thái

| Thời điểm | Việc nên làm | Việc tránh |
| --- | --- | --- |
| Vừa createSQLXML | Chọn một set... | Đọc khi chưa có XML |
| Sau setString hoặc lấy Writer | Hoàn tất nội dung và bind/execute | Gọi set... lần thứ hai |
| Sau setCharacterStream | Ghi và đóng Writer trước execute | Để Writer mở khi execute |
| Sau ResultSet.getSQLXML | Chọn một get... | Gọi nhiều get... trên cùng instance |
| Sau getCharacterStream | Đọc/đóng Reader, free | Giữ stream vượt transaction |
| Sau free | Bỏ reference và dọn scope | Tiếp tục gọi SQLXML methods |
| Sau transaction đóng | Không giữ locator ngoài scope | Kỳ vọng object còn dùng được |

**free() không khôi phục trạng thái readable/writable**. Một đối tượng đã giải phóng không được tái sử dụng để đọc/ghi dữ liệu mới.

## 5. Chọn cách biểu diễn XML: String, stream hay Source/Result

### 5.1. setString và getString

Với XML nhỏ hoặc cấu trúc được tạo từ dữ liệu đã kiểm soát:

~~~java
SQLXML xml = connection.createSQLXML();
try {
    xml.setString("<note lang=\"vi\"><body>Đặng</body></note>");
    try (PreparedStatement ps = connection.prepareStatement(
            "INSERT INTO messages(id, payload) VALUES (?, ?)")) {
        ps.setInt(1, 100);
        ps.setSQLXML(2, xml);
        ps.executeUpdate();
    }
} finally {
    xml.free();
}
~~~

**Mảnh code cần Connection và bảng XML thực**, không phải một chương trình tự chạy. Dùng PreparedStatement để bind XML thay vì tự ghép chuỗi XML có đầu vào người dùng vào SQL literal. Nhưng **setString** không thay thế việc escape XML content: ký tự đặc biệt như **&**, **<** trong text cần được serialize đúng.

Ví dụ text **“Xin chào & Đặng”** trong XML source phải có **&amp;** hoặc được một XML writer/DOM/serializer hợp lệ xử lý.

### 5.2. setCharacterStream / getCharacterStream

Nếu có dữ liệu XML dài ở dạng ký tự, **Writer/Reader** là lựa chọn rõ ràng:

~~~java
SQLXML xml = connection.createSQLXML();
try {
    try (Writer writer = xml.setCharacterStream()) {
        writer.write("<note><body>Xin chào</body></note>");
    } // Writer đã đóng trước execute.
    try (PreparedStatement ps = connection.prepareStatement(
            "INSERT INTO messages(id, payload) VALUES (?, ?)")) {
        ps.setInt(1, 100);
        ps.setSQLXML(2, xml);
        ps.executeUpdate();
    }
} finally {
    xml.free();
}
~~~

**Đừng free trước executeUpdate** vì driver có thể chưa đọc dữ liệu bound. Đồng thời, **Writer.close() khác SQLXML.free()**: close hoàn tất stream ghi; free giải phóng SQLXML sau khi hoàn tất câu lệnh.

Khi đọc:

~~~java
SQLXML xml = rs.getSQLXML("payload");
if (xml != null) {
    try {
        try (Reader reader = xml.getCharacterStream()) {
            // Đưa Reader vào XML parser hoặc xử lý theo chunks.
        }
    } finally {
        xml.free();
    }
}
~~~

Dạng stream giúp ứng dụng không bắt buộc gọi getString trên một XML lớn, nhưng JDBC driver/XML parser có thể vẫn buffer tùy implementation. Cần benchmark theo driver.

### 5.3. setBinaryStream / getBinaryStream

Những method này đưa dữ liệu qua InputStream/OutputStream. XML bytes cần có encoding hợp lệ, và nếu XML declaration có **encoding=...**, nó phải phù hợp với byte representation.

~~~java
// Mảnh minh họa, fileXml là Path của file XML đã được tin cậy.
SQLXML xml = connection.createSQLXML();
try {
    try (InputStream in = Files.newInputStream(fileXml);
         OutputStream out = xml.setBinaryStream()) {
        in.transferTo(out);
    }
    // Bind vào PreparedStatement và execute trước khi free.
} finally {
    xml.free();
}
~~~

**Mảnh code trên bỏ qua phần PreparedStatement để tập trung vào stream**; muốn ghi database, phải bind/execute trước khi free. Nếu có XML không đáng tin, phải validate cấu trúc, giới hạn kích thước và cấu hình parser an toàn; đừng nghĩ byte stream bảo vệ khỏi XXE hoặc XML entity expansion.

### 5.4. getSource và setResult

SQLXML tích hợp các Java XML APIs:

| Method | Hướng dữ liệu | Ví dụ |
| --- | --- | --- |
| **getSource(DOMSource.class)** | SQLXML → DOM | Phù hợp tree manipulation với XML không quá lớn |
| **getSource(StAXSource.class)** | SQLXML → StAX stream | Phù hợp xử lý event/stream theo khả năng driver |
| **getSource(SAXSource.class)** | SQLXML → SAX events | Phù hợp streaming callbacks |
| **setResult(DOMResult.class)** | DOM node → SQLXML | Biểu diễn DOM output |
| **setResult(StAXResult.class)** | StAX writer → SQLXML | Ghi XML theo StAX |
| **setResult(SAXResult.class)** | SAX events → SQLXML | Ghi XML theo SAX |
| **getSource(StreamSource.class)** | SQLXML → XML Source qua stream | Tùy driver hỗ trợ |
| **setResult(StreamResult.class)** | XML Result qua stream → SQLXML | Tùy driver hỗ trợ |

API **<T extends Source> T getSource(Class<T>)** và **<T extends Result> T setResult(Class<T>)** có thể ném **SQLFeatureNotSupportedException** nếu loại Source/Result được yêu cầu không được driver hỗ trợ.

**Một số driver có thể xử lý Source/Result hiệu quả hơn** vì tránh serialize sang XML text rồi parse lại ở ứng dụng. Nhưng vì parser/transformer có thể thuộc implementation của driver, **không mặc định dữ liệu không đáng tin đã được parse với cấu hình chống XXE mong muốn**. Nếu security policy yêu cầu cấm DTD/external entities rõ ràng, hãy chủ động kiểm soát parser và kiểm chứng với driver thật.

## 6. Ví dụ Java 17+ hoàn chỉnh: JDBC SQLXML test double và StAX an toàn

Để có một ví dụ **biên dịch và chạy được ngay** mà không cần cài DBMS, phần này dùng dynamic proxy triển khai **Connection/PreparedStatement/ResultSet tối thiểu**, và một class **MemorySqlXml** implement SQLXML cho vài method được sử dụng trong bài. Nó mô phỏng database bằng một Map **id → XML string**.

**Đây là test double, không phải JDBC driver production.** Nó xác nhận cách chương trình gọi đúng interface/overload/lifecycle và giúp minh họa tình huống một-shot. Nó **không chứng minh bất kỳ database vendor nào hỗ trợ SQL XML**, không kiểm tra SQL parser, wire protocol, transaction locator, schema validation hay hiệu năng. Trong test double, một vài SQLXML methods không dùng được chủ động ném SQLFeatureNotSupportedException; driver thực có contract đầy đủ khác.

Chương trình kiểm thử:

1. **Connection.createSQLXML()** tạo object writable.
2. **setString()** điền XML có tiếng Việt và entity escaping.
3. **PreparedStatement.setSQLXML(...)** bind, **executeUpdate()** mô phỏng lưu.
4. **ResultSet.getSQLXML(...)** tạo một object readable mới, đọc qua **Reader**.
5. Lần đọc công khai thứ hai trên cùng object bị từ chối.
6. **free()** làm object không sử dụng lại được.
7. Lấy một SQLXML mới từ ResultSet, parse bằng **StAX** có DTD/external entities disabled.
8. Ghi một XML khác bằng **setCharacterStream()** và đóng Writer trước execute.
9. Một XML có **DOCTYPE** và external entity bị parser an toàn từ chối.
10. So khớp đúng chín dòng stdout để dễ kiểm chứng.

### 6.1. File SqlXmlDemo.java

~~~java
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.io.IOException;
import java.io.Reader;
import java.io.StringReader;
import java.io.StringWriter;
import java.io.Writer;
import java.lang.reflect.Proxy;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;
import java.sql.SQLXML;
import java.util.HashMap;
import java.util.Map;
import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLStreamConstants;
import javax.xml.stream.XMLStreamException;
import javax.xml.stream.XMLStreamReader;
import javax.xml.transform.Result;
import javax.xml.transform.Source;

public final class SqlXmlDemo {
    private static final String XML =
            "<note lang=\"vi\"><body>Xin chào &amp; Đặng</body></note>";

    public static void main(String[] args) throws Exception {
        FakeJdbc db = new FakeJdbc();
        try (Connection conn = db.connection()) {
            SQLXML outgoing = conn.createSQLXML();
            try {
                outgoing.setString(XML);
                try (PreparedStatement ps = conn.prepareStatement(
                        "INSERT INTO messages(id, payload) VALUES (?, ?)")) {
                    ps.setInt(1, 7);
                    ps.setSQLXML(2, outgoing);
                    System.out.println("rowsInserted=" + ps.executeUpdate());
                }
            } finally {
                outgoing.free();
            }

            try (PreparedStatement ps = conn.prepareStatement(
                    "SELECT payload FROM messages WHERE id = ?")) {
                ps.setInt(1, 7);
                try (ResultSet rs = ps.executeQuery()) {
                    if (!rs.next()) throw new AssertionError("Missing id=7");
                    SQLXML sqlxml = rs.getSQLXML("payload");
                    try {
                        String result;
                        try (Reader reader = sqlxml.getCharacterStream()) {
                            StringWriter buffer = new StringWriter();
                            reader.transferTo(buffer);
                            result = buffer.toString();
                        }
                        System.out.println("readerEquals=" + XML.equals(result));
                        boolean secondReadRejected = false;
                        try { sqlxml.getString(); }
                        catch (SQLException ok) { secondReadRejected = true; }
                        System.out.println("oneShotRead=" + secondReadRejected);
                    } finally {
                        sqlxml.free();
                    }
                    boolean afterFreeRejected = false;
                    try { sqlxml.getString(); }
                    catch (SQLException ok) { afterFreeRejected = true; }
                    System.out.println("afterFreeRejected=" + afterFreeRejected);
                }
            }

            try (PreparedStatement ps = conn.prepareStatement(
                    "SELECT payload FROM messages WHERE id = ?")) {
                ps.setInt(1, 7);
                try (ResultSet rs = ps.executeQuery()) {
                    rs.next();
                    SQLXML sqlxml = rs.getSQLXML("payload");
                    try {
                        try (Reader in = sqlxml.getCharacterStream()) {
                            String[] parts = parseSecure(in);
                            System.out.println("xmlRoot=" + parts[0]);
                            System.out.println("xmlBody=" + parts[1]);
                        }
                    } finally {
                        sqlxml.free();
                    }
                }
            }

            SQLXML fromWriter = conn.createSQLXML();
            try {
                try (Writer w = fromWriter.setCharacterStream()) {
                    w.write("<note><body>Stream writer</body></note>");
                }
                try (PreparedStatement ps = conn.prepareStatement(
                        "INSERT INTO messages(id, payload) VALUES (?, ?)")) {
                    ps.setInt(1, 8);
                    ps.setSQLXML(2, fromWriter);
                    System.out.println("writerRowsInserted=" + ps.executeUpdate());
                }
            } finally {
                fromWriter.free();
            }
            System.out.println("writerClosedBeforeExecute="
                    + db.rows.get(8).contains("Stream writer"));

            String bad = "<!DOCTYPE note [<!ENTITY xxe SYSTEM "
                    + "\"file:///somewhere/secret\">]><note>&xxe;</note>";
            boolean rejected = false;
            try { parseSecure(new StringReader(bad)); }
            catch (XMLStreamException expected) { rejected = true; }
            System.out.println("doctypeRejected=" + rejected);
        }
    }

    static String[] parseSecure(Reader reader) throws XMLStreamException {
        XMLInputFactory factory = XMLInputFactory.newFactory();
        factory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
        factory.setProperty(XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
        factory.setXMLResolver((publicId, systemId, baseUri, namespace) -> {
            throw new XMLStreamException("External XML entity blocked");
        });
        XMLStreamReader x = factory.createXMLStreamReader(reader);
        String root = "";
        StringBuilder body = new StringBuilder();
        boolean inBody = false;
        try {
            while (x.hasNext()) {
                int type = x.next();
                if (type == XMLStreamConstants.DTD) {
                    throw new XMLStreamException("DOCTYPE is not allowed");
                }
                if (type == XMLStreamConstants.START_ELEMENT) {
                    if (root.isEmpty()) root = x.getLocalName();
                    if ("body".equals(x.getLocalName())) inBody = true;
                }
                if (type == XMLStreamConstants.CHARACTERS && inBody) {
                    body.append(x.getText());
                }
                if (type == XMLStreamConstants.END_ELEMENT
                        && "body".equals(x.getLocalName())) inBody = false;
            }
            return new String[] {root, body.toString()};
        } finally {
            x.close();
        }
    }

    static final class FakeJdbc {
        final Map<Integer, String> rows = new HashMap<>();
        Connection connection() {
            return (Connection) Proxy.newProxyInstance(
                    SqlXmlDemo.class.getClassLoader(),
                    new Class<?>[] {Connection.class},
                    (p, m, a) -> {
                        switch (m.getName()) {
                            case "createSQLXML": return new MemorySqlXml(true, null);
                            case "prepareStatement": return statement((String)a[0]);
                            case "close": return null;
                            default: throw new SQLFeatureNotSupportedException(m.getName());
                        }
                    });
        }
        PreparedStatement statement(String sql) {
            final Object[] params = new Object[3];
            return (PreparedStatement) Proxy.newProxyInstance(
                    SqlXmlDemo.class.getClassLoader(),
                    new Class<?>[] {PreparedStatement.class},
                    (p, m, a) -> {
                        switch (m.getName()) {
                            case "setInt": params[(int)a[0]] = a[1]; return null;
                            case "setSQLXML": params[(int)a[0]] = a[1]; return null;
                            case "executeUpdate":
                                rows.put((int)params[1],
                                        ((MemorySqlXml)params[2]).driverRead());
                                return 1;
                            case "executeQuery": return result(rows.get((int)params[1]));
                            case "close": return null;
                            default: throw new SQLFeatureNotSupportedException(m.getName());
                        }
                    });
        }
        ResultSet result(String data) {
            final boolean[] advanced = {false};
            return (ResultSet) Proxy.newProxyInstance(
                    SqlXmlDemo.class.getClassLoader(),
                    new Class<?>[] {ResultSet.class},
                    (p, m, a) -> {
                        switch (m.getName()) {
                            case "next":
                                if (!advanced[0] && data != null) {
                                    advanced[0] = true; return true;
                                }
                                return false;
                            case "getSQLXML":
                                if (!advanced[0]) throw new SQLException("No row");
                                return data == null ? null : new MemorySqlXml(false, data);
                            case "close": return null;
                            default: throw new SQLFeatureNotSupportedException(m.getName());
                        }
                    });
        }
    }

    static final class MemorySqlXml implements SQLXML {
        private String data;
        private boolean freed;
        private boolean readAllowed;
        private boolean writeAllowed;
        private boolean writerOpen;
        MemorySqlXml(boolean newObject, String data) {
            this.data = data;
            this.writeAllowed = newObject;
            this.readAllowed = !newObject;
        }
        void ensureOpen() throws SQLException {
            if (freed) throw new SQLException("SQLXML freed");
        }
        String driverRead() throws SQLException {
            ensureOpen();
            if (writerOpen) throw new SQLException("Close writer before execute");
            if (data == null) throw new SQLException("Uninitialized SQLXML");
            return data;
        }
        private String consumeRead() throws SQLException {
            ensureOpen();
            if (!readAllowed) throw new SQLException("SQLXML read already used");
            readAllowed = false;
            return data;
        }
        @Override public String getString() throws SQLException {
            return consumeRead();
        }
        @Override public Reader getCharacterStream() throws SQLException {
            return new StringReader(consumeRead());
        }
        @Override public InputStream getBinaryStream() throws SQLException {
            return new ByteArrayInputStream(
                    consumeRead().getBytes(StandardCharsets.UTF_8));
        }
        @Override public void setString(String value) throws SQLException {
            ensureOpen();
            if (!writeAllowed) throw new SQLException("SQLXML write already used");
            this.data = value;
            writeAllowed = false;
        }
        @Override public Writer setCharacterStream() throws SQLException {
            ensureOpen();
            if (!writeAllowed) throw new SQLException("SQLXML write already used");
            writeAllowed = false;
            writerOpen = true;
            return new StringWriter() {
                @Override public void close() throws IOException {
                    super.close();
                    data = toString();
                    writerOpen = false;
                }
            };
        }
        @Override public java.io.OutputStream setBinaryStream() throws SQLException {
            throw new SQLFeatureNotSupportedException("Fake only");
        }
        @Override public <T extends Source> T getSource(Class<T> type) throws SQLException {
            throw new SQLFeatureNotSupportedException("Fake only");
        }
        @Override public <T extends Result> T setResult(Class<T> type) throws SQLException {
            throw new SQLFeatureNotSupportedException("Fake only");
        }
        @Override public void free() {
            freed = true;
            data = null;
        }
    }
}
~~~

### 6.2. Lệnh biên dịch và chạy

Với JDK 17 trở lên, tại thư mục chứa **SqlXmlDemo.java**:

~~~bash
javac -encoding UTF-8 --release 17 SqlXmlDemo.java
java SqlXmlDemo
~~~

Hai lệnh cũng dùng được trên Windows PowerShell. Chương trình không yêu cầu driver JDBC vendor, credentials, connection URL, SQL server hoặc dependency ngoài JDK; nó cố ý sử dụng fake JDBC interfaces để kiểm thử.

### 6.3. Stdout chính xác, đã kiểm chứng

~~~text
rowsInserted=1
readerEquals=true
oneShotRead=true
afterFreeRejected=true
xmlRoot=note
xmlBody=Xin chào & Đặng
writerRowsInserted=1
writerClosedBeforeExecute=true
doctypeRejected=true
~~~

**Đã chạy và kiểm tra đúng cả 9 dòng trên OpenJDK 24.0.2**, biên dịch bằng **--release 17**.

### 6.4. Giải thích stdout

- **rowsInserted=1**: fake PreparedStatement mô phỏng một row được lưu từ SQLXML được setString. Không phải một INSERT thực vào DB.
- **readerEquals=true**: XML đã bind trong fake được đọc lại qua SQLXML.getCharacterStream và so sánh nguyên văn, giữ dấu tiếng Việt và XML escaping.
- **oneShotRead=true**: fake chủ động ném SQLException khi gọi getString lần thứ hai trên cùng SQLXML sau khi đã getCharacterStream. Điều này minh họa trạng thái one-shot của API.
- **afterFreeRejected=true**: fake từ chối getString sau free, tương ứng contract object không còn hợp lệ.
- **xmlRoot=note**: StAX parser đọc root element từ XML.
- **xmlBody=Xin chào & Đặng**: XML parser decode **&amp;** thành ký tự **&** và giữ Unicode.
- **writerRowsInserted=1**: fake lưu XML khác được ghi qua setCharacterStream.
- **writerClosedBeforeExecute=true**: writer được đóng trước execute; fake kiểm tra tình trạng writer đã hoàn tất.
- **doctypeRejected=true**: parser an toàn phát hiện hoặc từ chối XML có DOCTYPE/external entity; không đọc file hệ thống.

**Không dùng test double để kết luận một JDBC driver cụ thể có SQL XML native, giữ một-shot state hay execute/streaming đúng như fake.** Đó là những điều cần được xác minh bằng integration test.

### 6.5. Vì sao fake driver không dùng SQL thật?

**Connection**, **PreparedStatement** và **ResultSet** có rất nhiều methods. Để một ví dụ độc lập không cần database, dynamic Proxy chỉ mô phỏng đúng những methods bài cần kiểm tra; các methods còn lại chủ động ném **SQLFeatureNotSupportedException**. Đây không phải cách viết một JDBC driver thực sự hoàn chỉnh.

Fake Map còn dùng SQL string thuần làm nhãn kiểm thử, không parse SQL, không có transaction/rollback, không enforce schema, SQL NULL, SQL XML validation hay security permissions. Trong production, hãy tạo database test được cấp phép và sử dụng driver vendor chính thức.

## 7. Mẫu triển khai với JDBC Connection thật

Giả sử ứng dụng có **DataSource** được cấu hình an toàn và một bảng có cột SQL XML thực sự được driver hỗ trợ.

### 7.1. INSERT qua createSQLXML + setSQLXML

~~~java
// Mảnh code: Connection conn và bảng messages có thật.
SQLXML xml = conn.createSQLXML();
try {
    xml.setString("<note lang=\"vi\"><body>Xin chào</body></note>");

    try (PreparedStatement ps = conn.prepareStatement(
            "INSERT INTO messages(id, payload) VALUES (?, ?)")) {
        ps.setLong(1, 42L);
        ps.setSQLXML(2, xml);
        int rows = ps.executeUpdate();
        // Kiểm tra rows theo business contract.
    }
} finally {
    xml.free();
}
~~~

**Những ràng buộc:**

- **createSQLXML** phải thành công, không phải mọi driver implement XML type.
- XML phải hợp lệ theo DBMS/column constraints. Driver có thể phát hiện lỗi ở setString, setSQLXML hoặc execute.
- XML object phải còn sống ít nhất đến sau execute.
- Không commit/close Connection trong helper nếu transaction do caller quản lý.
- **free()** phải chạy ngay cả khi execute ném SQLException.
- Nếu free cũng ném, cần giữ primary exception và xử lý cleanup failure trong production.
- Không tự ghép XML user input vào SQL string; dùng bind parameter và XML serializer an toàn.

### 7.2. SELECT qua ResultSet.getSQLXML

~~~java
// Mảnh code: Connection conn có thật.
try (PreparedStatement ps = conn.prepareStatement(
        "SELECT payload FROM messages WHERE id = ?")) {
    ps.setLong(1, 42L);
    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            SQLXML xml = rs.getSQLXML("payload");
            if (xml != null) {
                try {
                    try (Reader reader = xml.getCharacterStream()) {
                        // Parse bằng StAX an toàn hoặc stream tới sink.
                        // Không giữ reader vượt transaction của locator.
                    }
                } finally {
                    xml.free();
                }
            }
        }
    }
}
~~~

Nếu query không trả row, nhánh **rs.next()** là false. Nếu XML column là SQL NULL, getSQLXML trả null. Một XML value tồn tại nhưng không được phép truy cập có thể ném SQLException; không biến mọi SQLException thành null.

### 7.3. UPDATE và SQL NULL

~~~java
// Mảnh minh họa với PreparedStatement có đúng hai parameters.
try (PreparedStatement ps = conn.prepareStatement(
        "UPDATE messages SET payload = ? WHERE id = ?")) {
    ps.setNull(1, java.sql.Types.SQLXML);
    ps.setLong(2, 42L);
    ps.executeUpdate();
}
~~~

Một SQL NULL khác với văn bản XML rỗng. Chỉ dùng **setNull** nếu business contract yêu cầu xóa nội dung cột XML về NULL, và xác nhận driver/server hỗ trợ type tương ứng.

### 7.4. Đóng đúng thứ tự

~~~text
Borrow Connection / begin transaction theo application owner
                    │
                    ▼
              createSQLXML
                    │
                    ▼
                set... XML
                    │
                    ▼
             PreparedStatement
                    │
                    ▼
                 setSQLXML
                    │
                    ▼
              executeUpdate()
                    │
                    ▼
            close PreparedStatement
                    │
                    ▼
                 SQLXML.free()
                    │
                    ▼
       commit/rollback theo transaction owner
                    │
                    ▼
       return Connection to pool
~~~

Khi đọc, giữ **ResultSet + Connection + transaction** hợp lệ trong suốt thời gian đang xử lý SQLXML stream/Source. Đóng stream trước, free SQLXML, rồi mới đóng ResultSet/statement theo ownership.

### 7.5. Vì sao không trả SQLXML từ service method?

Nếu method trả một SQLXML object rồi đóng Connection hoặc transaction trước khi caller dùng nó, object có thể trở thành **locator không hợp lệ**. Tốt hơn:

- Parse/copy dữ liệu trong scope kết nối còn sống và trả DTO đã tách khỏi JDBC object.
- Với XML lớn, stream sang sink hoặc staging file được kiểm soát trong khi connection còn hợp lệ.
- Nếu cần giữ dữ liệu lâu, lưu dữ liệu ở application-owned format/safe storage rồi free SQLXML.
- Không cache SQLXML objects qua request hoặc giữa các lần mượn Connection pool.

## 8. XML parsing an toàn: chống XXE, DTD và entity expansion

SQLXML là một container/bridge; **nó không tự bảo đảm XML đáng tin cậy**. XML từ DB có thể từng được người dùng, external partner hoặc ETL job ghi vào. Nếu parser mở external entities, có nguy cơ **XML External Entity (XXE)**, đọc local files, truy cập network nội bộ hoặc gây cạn tài nguyên.

Với XML không đáng tin:

1. **Không chấp nhận DOCTYPE/DTD** nếu nghiệp vụ không cần.
2. **Không resolve external entities**.
3. Không để parser truy cập arbitrary filesystem/network.
4. Giới hạn kích thước XML và complexity (số elements, độ sâu, text length, attributes).
5. Hạn chế XSLT imports/document() và external stylesheet access nếu dùng transformations.
6. Với DOM, lưu ý memory tỷ lệ kích thước cây; với XML lớn, StAX/SAX thường dễ kiểm soát memory hơn, nhưng vẫn cần giới hạn.
7. Cấu hình an toàn các XML factories **tự mình kiểm soát**. Không giả định driver.getSource(DOMSource.class) dùng cùng một parser-security policy.

### 8.1. StAX với DTD disabled và resolver từ chối external entities

Hàm **parseSecure** trong chương trình đầy đủ ở phần 6 minh họa:

~~~java
// Mảnh minh họa; parseSecure hoàn chỉnh ở phần 6.
XMLInputFactory factory = XMLInputFactory.newFactory();
factory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
factory.setProperty(XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
factory.setXMLResolver((publicId, systemId, baseUri, namespace) -> {
    throw new XMLStreamException("External XML entity blocked");
});

XMLStreamReader reader = factory.createXMLStreamReader(xmlCharacters);
try {
    while (reader.hasNext()) {
        int type = reader.next();
        if (type == XMLStreamConstants.DTD) {
            throw new XMLStreamException("DOCTYPE is not allowed");
        }
        // Đọc elements/characters theo contract.
    }
} finally {
    reader.close();
}
~~~

**xmlCharacters** phải là một Reader do caller cung cấp. Trong một ứng dụng thực tế, hãy đảm bảo runtime XMLInputFactory implementation hỗ trợ các security properties đã yêu cầu. Nếu nó không hỗ trợ, **fail closed**, không silently bỏ qua cấu hình.

Đoạn demo còn từ chối DTD event, không chỉ dựa trên default parser configuration. Parser có thể báo XMLStreamException thay vì phát ra event nếu DOCTYPE/DTD bị cấm; cả hai đều được xem là từ chối payload không được phép.

### 8.2. Nếu dùng DOM/Transformer

Với DocumentBuilderFactory, cần tắt DOCTYPE/external entities và external DTD/schema access theo contract của JAXP implementation. Với TransformerFactory, xem **XMLConstants.ACCESS_EXTERNAL_DTD**, **ACCESS_EXTERNAL_STYLESHEET** và **FEATURE_SECURE_PROCESSING**. **Không đặt các properties một cách mù quáng** rồi ignore ParserConfigurationException hoặc IllegalArgumentException khi runtime không hỗ trợ.

Không dùng một XML parser có cấu hình mặc định trong production cho arbitrary user XML chỉ vì dữ liệu nằm trong SQL XML column.

### 8.3. XML escaping và Unicode

Ví dụ:

~~~xml
<note lang="vi"><body>Xin chào &amp; Đặng</body></note>
~~~

XML text có **&amp;**. Khi parse, giá trị text trở thành **Xin chào & Đặng**. Unicode tiếng Việt được giữ nguyên nếu encoding và database conversion đúng.

Với XML text thực tế, không tự xây bằng string concatenation từ user inputs nếu bạn chưa escape **<**, **&**, quotes theo context attribute/text. Nên dùng DOM/StAX writer hoặc XML serializer phù hợp, có giới hạn kích thước và validation.

## 9. Stream, charset và memory

### 9.1. getCharacterStream khác getBinaryStream

**getCharacterStream()** trả **Reader** phục vụ ký tự Java. Nếu bạn cần nội dung text tiếng Việt, Reader là con đường rõ ràng, không phải tự decode bằng charset mặc định của máy.

**getBinaryStream()** trả **InputStream** chứa XML bytes theo encoding do driver/representation cung cấp. Nếu bạn cần parse XML bytes, để XML parser xử lý declaration/encoding theo XML specification, hoặc định nghĩa rõ input encoding nếu parser API yêu cầu.

**Không dùng new String(bytes)** mà không truyền Charset khi byte encoding không được đảm bảo. Trong code ứng dụng bạn tự quản lý file UTF-8, dùng StandardCharsets.UTF_8.

### 9.2. Tránh getString với XML rất lớn

Nếu XML nặng hàng trăm MB, **getString()** có thể materialize XML trong heap. Cũng không nên gọi **readAllBytes()** khi mục tiêu chỉ là scan một số XML events. Chọn Reader/StAX streaming và giới hạn bytes/chars/elements, nhưng nhớ **driver có thể buffer**.

**Đừng coi stream API là phép bảo đảm O(1) RAM**. Một số driver có thể materialize XML khi lấy SQLXML, hoặc XMLSource có thể tạo DOM tree. Cần đo heap, network throughput và transaction duration với driver/server đang dùng.

### 9.3. Giới hạn trong ứng dụng

Hệ thống cần giới hạn:

- Tổng số bytes/characters XML được chấp nhận.
- Số elements, depth và số attributes.
- Tốc độ ingest và processing time.
- Connection/statement timeout và transaction lifetime.
- Số luồng XML xử lý đồng thời.
- Kích thước response/export nếu XML được tải về client.

Nếu một client hủy request giữa lúc export, cần đóng stream, free SQLXML, dọn temporary output và xử lý transaction/Connection theo pool policy.

## 10. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Cách giải quyết |
| --- | --- | --- |
| **SQLFeatureNotSupportedException** khi createSQLXML | Driver/DBMS không hỗ trợ SQL XML API/type | Kiểm tra driver version và SQL XML schema support |
| **SQLException** ở setSQLXML | Sai parameter index, XML object chưa hoàn thành hoặc driver lỗi | Kiểm tra index 1-based, close writer/stream trước execute |
| **SQLException** tại executeUpdate | XML không hợp lệ, column constraints, Result/Writer chưa đóng | Xem SQLState/vendor code và log nguyên nhân phù hợp |
| **SQLException** khi đọc SQLXML lần 2 | SQLXML là one-shot readable | Chọn một get... mỗi instance, query mới khi cần |
| **SQLException** sau free | Object đã được giải phóng | Không giữ SQLXML ngoài scope; tạo/lấy lại object mới |
| **NullPointerException** ở getCharacterStream | SQL column là NULL → getSQLXML null | Kiểm tra null trước khi mở stream |
| XML sai dấu hoặc lỗi encoding | Nhầm byte/char streams hoặc charset | Dùng Reader cho text, xác định charset bytes |
| **XMLStreamException** khi parse | XML không well-formed, DOCTYPE bị cấm, external entities bị chặn | Validate XML và security policy, không nới lỏng bừa |
| XXE hoặc file/network access khi parse | Parser cho external entities/DTD | Disable DTD/entities, deny external access, limit XML complexity |
| XML parser/transformer chậm hoặc OOM | XML lớn, DOM tree hoặc entity expansion | Giới hạn kích thước và dùng StAX/SAX khi thích hợp |
| Reader/OutputStream chưa đóng khi execute | Driver đọc incomplete data | Đóng Writer/stream/Result trước khi execute |
| XML đọc được trong transaction nhưng fail sau commit | SQLXML có thể là database locator | Đọc hết trước khi transaction kết thúc |
| Test chạy được fake nhưng fail DB | Test double không phải driver thật | Chạy integration tests trên DBMS + driver thực |
| XML dạng String nhưng column CLOB | Schema/type không phải SQL XML | Xem SQL type mapping và driver docs |
| Cùng XML nhưng serialized text khác | Namespace order/whitespace/serialization của DB/parser | So sánh XML semantics khi cần, không always compare bytes |
| Đóng Connection nhưng còn SQLXML | Locator không còn session hợp lệ | Đọc/ghi/free trong scope Connection |
| free làm mất dữ liệu? | Nhầm free với DELETE | free chỉ giải phóng object resources, SQL state theo transaction |
| try(SQLXML ...) không compile với --release 17 | Java 17 SQLXML không AutoCloseable | Dùng finally/free, hoặc đổi target API hợp lệ |
| Cấu hình parser không được hỗ trợ | XMLInputFactory implementation khác | Fail closed và test XML security properties |

### 10.1. Chẩn đoán theo thứ tự

1. Kiểm tra database có SQL XML type và driver hỗ trợ SQLXML.
2. Xác nhận statement parameter index, column label và SQL schema.
3. Xác nhận XML well-formed và encoding, không ghép user text trực tiếp không escape.
4. Kiểm tra SQLXML đã được set một lần trước khi bind chưa.
5. Nếu dùng Writer/Result, kiểm tra đã close/hoàn tất trước execute.
6. Nếu đọc, kiểm tra SQLXML mới từ ResultSet có bị getString/getSource/getCharacterStream trước đó chưa.
7. Kiểm tra SQL NULL, ResultSet row/connection/transaction còn hợp lệ.
8. Theo dõi SQLState, SQLException chain, vendor code nhưng không log XML nhạy cảm.
9. Nếu parser lỗi, tách vấn đề security rules, well-formedness và database serialization.
10. Nếu data thay đổi, xem XML canonicalization/whitespace/namespace/encoding policy của product.
11. Nếu memory cao, đo JDBC driver buffering và parser memory, không chỉ byte[] do code ứng dụng cấp phát.
12. Nếu dùng pool, đảm bảo SQLXML không thoát ra khỏi transaction/borrow scope.

## 11. XML equality: chuỗi không phải lúc nào là cấu trúc

Database có thể lưu XML dưới dạng representation tối ưu, và serializer có thể điều chỉnh spacing, encoding declaration hoặc thứ tự thuộc tính theo implementation. Vì vậy:

~~~xml
<note lang="vi"><body>Xin chào</body></note>
~~~

và

~~~xml
<note lang='vi'>
    <body>Xin chào</body>
</note>
~~~

là những chuỗi bytes khác nhau nhưng có thể có cùng thông tin cấu trúc (tùy xem whitespace text có ý nghĩa hay không). **Không luôn dùng String.equals** để kết luận XML value sai sau DB round-trip.

Khi test:

- Dữ liệu cần giữ nguyên byte-for-byte: định nghĩa rõ XML canonicalization, encoding và storage policy.
- Dữ liệu XML theo cấu trúc: parse XML an toàn rồi so sánh element/namespace/attribute/text semantics theo product contract.
- Whitespace có thể có ý nghĩa trong text nodes hoặc mixed content; đừng tự trim mọi text mà không có hợp đồng dữ liệu.
- Namespace prefixes có thể thay đổi trong serialization trong khi expanded namespace names giữ ý nghĩa; khi cần kiểm tra XPath, xác định namespace context đúng.
- XML declaration có thể được driver/serializer tạo lại hoặc bỏ đi; không coi nó là dữ liệu nghiệp vụ nếu contract không yêu cầu giữ nguyên.

**Bài test double** cố tình lưu nguyên một String để dễ kiểm chứng, nhưng nó không mô phỏng normalizing/serialization của database thật.

## 12. SQLXML và connection pooling / transaction boundaries

SQLXML có thể là locator liên kết tới transaction đã tạo đối tượng. Vì vậy:

1. **Không trả SQLXML** từ một repository method đã đóng ResultSet/Connection.
2. **Không cache SQLXML** theo id trong singleton.
3. **Không dùng một SQLXML object trên nhiều threads** mà không có thread-safety/ownership contract từ driver.
4. **Không gọi free() trước executeUpdate()** với một SQLXML đã bind mà driver còn cần.
5. Khi đã đọc stream xong, đóng Reader/InputStream rồi free SQLXML.
6. Khi gửi XML ra HTTP response, cân nhắc giữ database Connection lâu; nếu response chậm, có thể dùng staging storage theo policy.
7. Với pool, **Connection.close()** thường chỉ trả logical handle; điều đó không cho phép giữ SQLXML locator vô thời hạn.
8. Nếu cleanup xảy ra khi Connection đã hỏng, phải ghi nhận error/evict connection tùy pool API.

### 12.1. Nếu free() cũng ném SQLException?

**free()** có thể báo SQLException. Khi operation chính đã lỗi và finally lại ném, code có thể che lỗi chính nếu không xử lý cẩn thận. Với ứng dụng production, giữ **primary failure** và gắn cleanup failure dưới dạng **suppressed** hoặc ghi sự kiện cleanup riêng; nếu session có nguy cơ hỏng, pool policy cần giải quyết.

Try-with-resources tự quản lý suppressed exceptions cho **PreparedStatement, ResultSet, Reader/Writer** mà nó sở hữu. Vì **SQLXML trên Java 17 không implement AutoCloseable**, bạn phải chủ động thiết kế tương đương khi cần nhiều cleanup errors.

### 12.2. Transaction không kiểm soát mọi I/O ngoài DB

Nếu bạn đọc XML trong DB rồi ghi ra file, DB rollback không tự xóa file đã tạo. Nếu bạn upload XML từ file rồi INSERT, file nguồn không biến mất chỉ vì commit hoặc free. Thiết kế đồng bộ tài nguyên ngoài DB, staging/temp file và retry policy riêng.

## 13. Kiểm thử integration với JDBC driver thật

Không cần kết nối DB production để học API. Nhưng trước khi dùng trong hệ thống có dữ liệu thật, cần test:

| Trường hợp | Điều cần xác minh |
| --- | --- |
| createSQLXML | Driver hỗ trợ, SQLXML ban đầu writable |
| setString và setSQLXML | INSERT/UPDATE thành công với XML well-formed |
| ResultSet.getSQLXML | SELECT trả dữ liệu, SQL NULL → null |
| getString | XML nhỏ parse/serialization đúng kỳ vọng |
| getCharacterStream | Unicode tiếng Việt và entity escaping đúng |
| getBinaryStream | XML encoding bytes phù hợp parser |
| setCharacterStream | Writer đóng trước execute, dữ liệu đủ |
| setBinaryStream | OutputStream đóng trước execute, bytes/encoding hợp lệ |
| getSource(DOM/StAX/SAX) | Driver hỗ trợ loại Source được yêu cầu |
| setResult(DOM/StAX/SAX) | Driver hỗ trợ loại Result và flush/close đúng |
| One-shot state | Gọi get/set lần thứ hai không được giả định thành công |
| free() | Giải phóng locator và không dùng lại |
| SQL XML schema | Constraints và XML indexes/query semantics thực tế |
| Invalid XML | Thời điểm SQLException xuất hiện: set, bind hay execute |
| Transaction | Locator hợp lệ trong phạm vi đọc/ghi cần thiết |
| Parser security | DOCTYPE/XXE không vượt qua được policy |
| XML lớn | Memory, round trip, latency, buffering, quota |
| Concurrency | Không dùng chung SQLXML/Connection sai lifecycle |
| Pool reuse | Không để XML streams/locators chưa đóng |
| DB migration | Driver/version và XML type mapping được kiểm thử lại |

### 13.1. Ví dụ test data hữu ích

~~~xml
<message lang="vi">
  <title>Đăng nhập</title>
  <body>Xin chào &amp; Đặng</body>
  <emoji>😀</emoji>
</message>
~~~

Test cả XML có **namespace**, attributes, CDATA, empty element và mixed content khi nghiệp vụ dùng chúng. Dữ liệu có dấu tiếng Việt, emoji và **&amp;** giúp phát hiện lỗi charset/escaping.

### 13.2. Không giả định hỗ trợ vì JDK có API

**java.sql.SQLXML** là interface của Java SE, nhưng nó không tạo ra XML type ở database. Vendor drivers phải triển khai cách truyền/nạp và server phải có representation phù hợp. Một số implementation có thể sử dụng CLOB/driver-specific XML handling hoặc không hỗ trợ một số Source/Result methods.

Chạy integration test trên **driver + DBMS version** thực tế, không chỉ unit test với MemorySqlXml. Nếu chức năng SQL XML quan trọng, xem release notes của vendor khi nâng cấp driver/server.

## 14. Bài tập tự luyện

1. Thay XML đầu vào bằng một đoạn văn tiếng Việt khác, giữ **&amp;** đúng chỗ rồi kiểm chứng readerEquals và xmlBody.
2. Trong fake, gọi **getString()** lần thứ hai trên cùng SQLXML thay vì dùng instance mới; quan sát SQLException.
3. Gọi **free()** trước executeUpdate trong test double; giải thích vì sao driver không còn đọc được SQLXML và vì sao đây là sai lifecycle.
4. Gọi **setCharacterStream()** nhưng cố tình không close Writer trước execute, quan sát fake từ chối thao tác.
5. Thử setString rồi setString lần nữa; nêu lý do writer state chỉ cho phép một lần.
6. Thêm một XML có nested elements, namespaces và attributes; dùng StAX đọc localName/namespaceURI.
7. Thử XML không well-formed, ví dụ **<note><body></note>**, xác minh XMLStreamException khi parse.
8. Thử XML có DOCTYPE và external entity, giữ policy không cho phép DTD/XXE; tuyệt đối không thay bằng parser insecure.
9. Thêm SQL NULL case trong một integration test với database thử nghiệm, phân biệt null với XML document hợp lệ rỗng.
10. So sánh DOMSource và StAXSource cho cùng một XML nhỏ trên JDBC driver có hỗ trợ, đo memory/latency.
11. Dùng Writer từ setCharacterStream để ghi XML lớn nhưng kiểm tra giới hạn kích thước; không tạo String khổng lồ trước.
12. Thiết kế helper insertXml(Connection,id,Reader) có ownership rõ ràng của Reader và SQLXML; đảm bảo close stream trước execute.
13. Viết query lấy XML và parse nội dung trong cùng transaction, free trước khi return dữ liệu DTO; không return SQLXML.
14. Thử Java 26 SQLXML với try-with-resources trực tiếp và giải thích vì sao không compile dưới --release 17.
15. Xây test XML canonicalization khi nghiệp vụ cần equality theo cấu trúc, phân biệt whitespace có ý nghĩa.
16. Thêm metrics về SQLXML cleanup, parser errors và payload size mà không log full XML chứa dữ liệu nhạy cảm.

## 15. Checklist đưa vào production

- [ ] Database và JDBC driver thực sự hỗ trợ SQL XML type và setSQLXML/getSQLXML.
- [ ] Cột SQL XML và JDBC parameter/column labels được cấu hình đúng.
- [ ] Dùng Connection.createSQLXML trước khi set và bind.
- [ ] Chỉ dùng một cách ghi (setString/setCharacterStream/setBinaryStream/setResult) cho mỗi SQLXML instance.
- [ ] Đóng Writer/OutputStream/hoàn tất Result trước execute.
- [ ] Không free SQLXML trước khi statement thực thi xong.
- [ ] Khi đọc, kiểm tra SQL NULL và lấy đúng column label/index.
- [ ] Chỉ dùng một cách đọc (getString/getCharacterStream/getBinaryStream/getSource) cho mỗi SQLXML instance.
- [ ] Đóng Reader/InputStream rồi free SQLXML, trong khi transaction/Connection còn hợp lệ.
- [ ] Không return/cached SQLXML locator ra ngoài scope JDBC.
- [ ] Trên Java 17, dùng finally + free; với Java 26, cân nhắc AutoCloseable khi target API cho phép.
- [ ] Không tự xây XML không escape từ user input; dùng XML serializers/writers.
- [ ] Chặn DOCTYPE, external entities và giới hạn XML complexity khi parse không đáng tin.
- [ ] Không giả định getSource/setResult nào cũng được driver hỗ trợ.
- [ ] Với XML lớn, không mặc định getString/DOM; đo buffering/memory của driver/parser.
- [ ] Tránh log XML có PII/secrets; giữ quyền truy cập/retention phù hợp.
- [ ] Xử lý SQLException, SQLFeatureNotSupportedException, XMLStreamException, IOException riêng theo ngữ cảnh.
- [ ] Cleanup errors không che primary failure; có chính sách pool connection invalidation.
- [ ] Integration test trên đúng driver/server versions, transaction settings và XML schema.
- [ ] Khi test XML equality, biết khi nào cần so sánh semantics thay vì String bytes.

## Kết luận

**PreparedStatement.setSQLXML** và **ResultSet.getSQLXML** tạo một cầu nối typed giữa SQL XML columns và Java XML APIs. Khi ghi, bạn **createSQLXML → chọn một set... → bind → execute → free**. Khi đọc, bạn **getSQLXML → chọn một get... → dùng/đóng stream → free**. **SQLXML là đối tượng có trạng thái và vòng đời giới hạn**, không phải String có thể đọc hoặc ghi vô hạn.

API tiếp tục được hỗ trợ trên JDK hiện đại, nhưng database driver có thể khác về XML type, Source/Result support, buffering và transaction-locator behavior. Với đầu vào không đáng tin, việc dùng SQL XML type **không thay thế parser security**: hãy chặn XXE/DTD, escape đúng và có limits. Biên dịch ví dụ bằng **Java 17+**, dùng **free()** rõ ràng và kiểm tra thực tế với JDBC driver trước khi áp dụng production.

**Tham khảo chính thức, hiện hành:**

- [SQLXML — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLXML.html)
- [SQLXML — Java SE 26 (AutoCloseable và close)](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLXML.html)
- [Connection — Java SE 26 (createSQLXML)](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Connection.html)
- [PreparedStatement — Java SE 26 (setSQLXML)](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/PreparedStatement.html)
- [ResultSet — Java SE 26 (getSQLXML)](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/ResultSet.html)
- [XMLInputFactory — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLInputFactory.html)
- [XMLStreamReader — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLStreamReader.html)
- [XMLConstants — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/XMLConstants.html)