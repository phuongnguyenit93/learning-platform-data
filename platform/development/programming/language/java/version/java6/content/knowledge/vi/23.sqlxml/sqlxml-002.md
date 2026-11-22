# SQLXML: `Connection.createSQLXML` và vòng đời đối tượng

## Mục tiêu học tập

JDBC hỗ trợ ánh xạ kiểu dữ liệu **SQL XML** sang `java.sql.SQLXML`. Khi muốn tạo một giá trị XML mới từ Java để lưu vào cột XML của cơ sở dữ liệu, `Connection.createSQLXML()` là factory chuẩn; nó tạo một đối tượng SQLXML **chưa chứa dữ liệu**, sau đó ứng dụng khởi tạo nội dung bằng **một** phương thức ghi như `setString`, `setCharacterStream`, `setBinaryStream` hoặc `setResult`.

Điểm đặc biệt: `SQLXML` có **trạng thái đọc/ghi** chặt chẽ. Không nên dùng nó như một chuỗi có thể ghi lại và đọc lại nhiều lần. Nó có thể được driver triển khai như một **logical pointer/locator** tới giá trị XML do database quản lý, với vòng đời liên quan đến `Connection` và transaction.

Sau bài này, bạn có thể:

- Phân biệt `SQLXML`, `String`, XML `Source`/`Result` và SQL `XML` column.
- Gọi `Connection.createSQLXML()`, hiểu đối tượng rỗng ban đầu và không nhầm với `ResultSet.getSQLXML(...)` (nhận XML đã lưu).
- Chọn **một** phương thức khởi tạo: `setString`, `setCharacterStream`, `setBinaryStream` hoặc `setResult`; hoàn thành stream/result đúng thời điểm.
- Dùng `PreparedStatement.setSQLXML` để bind vào câu SQL, không tự ghép nội dung XML vào SQL string.
- Hiểu **readable / not readable / writable / not writable / freed** theo Javadoc; thực hiện các thao tác đọc/ghi **tối đa một lần theo hướng được chọn**.
- Quản lý `free()`, đóng writer/stream, transaction/connection lifetime, lỗi `SQLException` và `SQLFeatureNotSupportedException`.
- Phân biệt **Java 17–25** (dọn bằng `free()`) với **JDK 26+** (SQLXML mới extends `AutoCloseable`, `close()` mặc định gọi `free()`).
- Biết cách sử dụng `Source`/`Result` với DOM, SAX, StAX và Stream XML APIs, cũng như hạn chế rủi ro XXE khi XML không đáng tin cậy.
- Biên dịch và chạy một ví dụ **Java 17+** độc lập không cần database: mô phỏng `Connection.createSQLXML()`, kiểm thử khởi tạo một lần, đọc một lần, stream, giải phóng và StAX escape ký tự.

**Special Note:** Chỉ dùng API và tri thức **vẫn áp dụng trong Java/JDBC hiện hành**. Các quy tắc vòng đời được đối chiếu với Javadoc Java SE 26, có kiểm tra tương thích đối với Java SE 17. Đoạn code nào cần database/driver hoặc chỉ biên dịch từ Java 26 trở lên đều được ghi rõ; không coi mã giả lập là driver JDBC thực.

## 1. SQLXML là gì?

`SQLXML` là giao diện trong package `java.sql`, module `java.sql`. Nó biểu diễn một giá trị kiểu **SQL XML** trong ánh xạ JDBC. Đây là **interface**, không phải class bạn thường tạo bằng `new SQLXML(...)`.

```java
import java.sql.Connection;
import java.sql.SQLXML;

SQLXML value = connection.createSQLXML();
```

Đây là đoạn mã **trong một method** có biến `connection` đã tồn tại, chưa phải chương trình độc lập. `createSQLXML()` tạo một đối tượng triển khai `SQLXML`. Ban đầu đối tượng này **chưa được khởi tạo nội dung XML**.

Một số DB có native XML column/type và cách lưu trữ tối ưu; một số database/driver **không hỗ trợ** kiểu SQL XML hoặc `createSQLXML`. Vì thế, API chuẩn tồn tại trong JDK **không đồng nghĩa mọi driver thực hiện thành công**.

### SQLXML không đồng nhất với văn bản XML thô

| Khái niệm | Vai trò |
| --- | --- |
| `java.sql.SQLXML` | Đối tượng JDBC ánh xạ kiểu SQL XML, có trạng thái và tài nguyên riêng |
| `String` | Chuỗi Java; chỉ là **một cách biểu diễn** tài liệu XML |
| `InputStream` / `OutputStream` | Dữ liệu XML ở dạng **byte stream**, phải quan tâm XML encoding |
| `Reader` / `Writer` | Nội dung XML ở dạng **character stream** |
| `javax.xml.transform.Source` | Đầu vào của XML parser/transformer, ví dụ `DOMSource` hoặc `StAXSource` |
| `javax.xml.transform.Result` | Đích nhận XML từ transform/serialization, ví dụ `DOMResult` hoặc `StreamResult` |
| `ResultSet.getSQLXML(...)` | Đọc một giá trị SQL XML từ kết quả query |
| `PreparedStatement.setSQLXML(...)` | Bind một `SQLXML` vào parameter của câu lệnh SQL |
| `SQLXML.free()` | Giải phóng tài nguyên của đối tượng SQLXML |

**Không nhầm XML và JDBC SQL:** `SQLXML` phục vụ SQL XML data type; nó không tạo bảng, không INSERT, không tự parse mọi tài liệu, và cũng không tự bảo đảm input XML của người dùng là an toàn.

## 2. `Connection.createSQLXML()` có hợp đồng gì?

Chữ ký của Java SE:

```java
SQLXML createSQLXML() throws SQLException;
```

Phương thức thuộc `java.sql.Connection` (JDBC 4.0, vẫn được hỗ trợ trong Java 26). Theo Javadoc:

1. Trả một đối tượng implement `SQLXML` **chưa chứa dữ liệu**.
2. Ứng dụng phải khởi tạo nội dung XML bằng một trong các phương thức ghi của interface.
3. `SQLException` có thể phát sinh khi không xây dựng được đối tượng, Connection đã đóng hoặc gặp lỗi database.
4. `SQLFeatureNotSupportedException` có thể phát sinh nếu JDBC driver không hỗ trợ kiểu dữ liệu/tính năng SQLXML.
5. Việc tạo object **không đồng nghĩa lưu nội dung vào DB**; ứng dụng phải bind/execute SQL hoặc dùng API cập nhật thích hợp.
6. Đối tượng SQLXML thường là **logical pointer** đến XML data của database, không phải `String` luôn nằm trong heap Java.
7. Tài nguyên có vòng đời, phải được giải phóng khi không cần.

### Dòng chảy điển hình

```text
Connection còn mở
    |
    v
createSQLXML() --> SQLXML chưa khởi tạo
    |
    +--> setString(xmlText)               [chọn 1 trong 4]
    +--> setCharacterStream() -> Writer   [chọn 1 trong 4]
    +--> setBinaryStream()    -> OutputStream
    +--> setResult(Class<? extends Result>)
    |
    v
hoàn tất XML / đóng Writer hoặc OutputStream
    |
    v
PreparedStatement.setSQLXML(index, xml)
    |
    v
executeUpdate() / execute()
    |
    v
SQLXML.free() khi hoàn tất sử dụng
    |
    v
commit/rollback/đóng connection theo transaction policy
```

**Nhấn mạnh:** Không gọi đồng thời `setString` rồi `setCharacterStream` trên cùng một đối tượng mới; XML write APIs được thiết kế để **khởi tạo một lần**. Không gọi `free` trước khi driver đã tiêu thụ dữ liệu tại execute.

## 3. Trạng thái đối tượng: writable, readable, freed

Javadoc của `SQLXML` mô tả một mô hình trạng thái. Phía ứng dụng không có sẵn method `isWritable` hoặc `isReadable`; bạn phải quản lý cách dùng dựa trên hợp đồng.

### 3.1. Khởi tạo một lần

Một đối tượng vừa tạo là mục tiêu của một phương thức ghi:

```java
SQLXML xml = connection.createSQLXML();
xml.setString("<message>Xin chào</message>");
```

Sau khi `setString` được gọi, trạng thái **writable → not writable**. Nếu tiếp tục gọi `xml.setString(...)` hoặc `xml.setCharacterStream()`, sẽ gặp `SQLException` theo hợp đồng trạng thái.

Tương tự, khi bắt đầu `setBinaryStream`, `setCharacterStream` hoặc `setResult`, đối tượng đã được đánh dấu **không thể khởi tạo lại**; không nên đổi ý giữa chừng để gọi một phương thức ghi khác.

### 3.2. Đọc tối đa một lần

Các phương thức đọc:

- `getString()`
- `getBinaryStream()`
- `getCharacterStream()`
- `getSource(Class<T>)`

khi được gọi sẽ chuyển **readable → not readable**. Vì vậy:

```java
String once = sqlxml.getString();
// Đừng mặc định sqlxml.getString() lần nữa luôn được phép.
```

JDBC SQLXML **không phải** một `String`/`DOM Document` có thể được đọc vô hạn lần. Nếu cần duyệt nhiều lần, **materialize** kết quả từ một lần đọc vào cấu trúc do ứng dụng quản lý, nếu kích thước và yêu cầu bộ nhớ cho phép; hoặc query lại theo thiết kế rõ ràng.

### 3.3. Đọc sau khi ghi có chắc chắn dùng được?

**Không nên dựa vào điều đó.** Javadoc quy định sau khi một phương thức **ghi** được gọi, object chuyển sang **not writable**, và implementation **có thể** đồng thời chuyển nó sang **not readable**. Ngược lại, gọi một phương thức đọc cũng có thể khiến object **not writable**.

Do đó một object `SQLXML` đã gọi `setString` thường được **bind thẳng** vào `PreparedStatement`; không cần `getString` trên chính object để “kiểm tra lại”. Nếu muốn kiểm thử văn bản trước khi gửi, làm điều đó trên `String`/stream nguồn **trước** khi `setString`.

> Ví dụ mô phỏng ở mục 8 cho phép đọc lại một lần sau khi khởi tạo chỉ để biểu diễn state machine của test double. **Không coi hành vi read-after-write của mock là lời hứa của mọi JDBC driver.**

### 3.4. Khi nào object hết hiệu lực?

`free()` giải phóng tài nguyên. Sau `free`, các methods khác ngoài `free` (hoặc `close` ở Java 26+) sẽ ném `SQLException` theo Javadoc. Gọi `free` lần nữa không có hiệu ứng thêm theo contract.

```java
sqlxml.free();
// Không dùng lại sqlxml.getString(), setString(...), getSource(...), ...
```

Đối tượng còn có vòng đời **transaction/connection**: SQLXML thường chỉ hợp lệ trong transaction nơi nó được tạo. Đừng giữ tham chiếu qua các lần mượn connection từ pool hoặc truyền nó đến luồng xử lý khác sau khi transaction đã kết thúc.

## 4. Một phương thức khởi tạo: `setString`

Với XML nhỏ hoặc đã có sẵn `String` hợp lệ:

```java
String document = "<invoice><number>42</number></invoice>";
SQLXML xml = connection.createSQLXML();
try {
    xml.setString(document);
    // Bind và execute SQL trong phạm vi sử dụng hợp lệ.
} finally {
    xml.free();
}
```

Đây là **đoạn tích hợp**, cần `Connection` đã mở và bắt/khai báo `SQLException`. `setString` không trả nội dung, mà gán một biểu diễn XML cho đối tượng.

### Ưu điểm

- Dễ dùng cho tài liệu nhỏ và nội dung đã được tạo an toàn.
- Dữ liệu là Java characters, tránh thao tác bytes/charset thủ công.
- Thích hợp khi XML được tạo trước bằng DOM/StAX/XSLT/serializer và đã được kiểm tra.

### Giới hạn

- Nếu tài liệu lớn, `String` có thể tốn nhiều bộ nhớ.
- Không được tự ghép dữ liệu người dùng vào XML mà thiếu escaping.
- Một `String` có dấu ngoặc nhọn/ampersand sai vị trí có thể **không phải XML well-formed**.
- Driver có thể từ chối XML ngay ở `setString`, hoặc **trì hoãn lỗi đến `PreparedStatement.execute`**.
- Sau `setString`, không được **khởi tạo lại** cùng SQLXML bằng `setCharacterStream` hay `setResult`.

### Escape XML đúng cách

Không nên:

```java
String unsafe = "<name>" + userInput + "</name>";
```

Nếu `userInput` chứa `&`, `<` hoặc dấu ngoặc kép trong attribute, XML có thể bị sai cấu trúc hoặc tạo nội dung không mong đợi.

Dùng **StAX `XMLStreamWriter`**, DOM serializer hoặc thư viện XML được bảo trì để tạo văn bản hợp lệ. Ví dụ JDK 17+:

```java
StringWriter out = new StringWriter();
XMLStreamWriter writer =
        XMLOutputFactory.newFactory().createXMLStreamWriter(out);
writer.writeStartElement("message");
writer.writeCharacters("Chào & tạm biệt");
writer.writeEndElement();
writer.close();

String xmlText = out.toString();
// "<message>Chào &amp; tạm biệt</message>" ở fixture JDK 24.
```

Đây là **đoạn trích của chương trình chạy đầy đủ ở mục 8**; cần imports `java.io.StringWriter`, `javax.xml.stream.XMLStreamWriter` và `XMLOutputFactory`. Dấu `&` được serializer escape thành `&amp;`, thay vì tự nối chuỗi theo cú pháp XML.

**Lưu ý:** XML escaping khác với SQL injection prevention. Lúc lưu xuống DB vẫn phải dùng `PreparedStatement.setSQLXML`; đừng ghép XML text đã escape vào SQL literals.

## 5. Khởi tạo theo character stream: `setCharacterStream()`

Khi XML là dữ liệu ký tự lớn, `setCharacterStream` tạo một `Writer` để ứng dụng ghi XML vào SQLXML:

```java
SQLXML xml = connection.createSQLXML();
try {
    try (Writer writer = xml.setCharacterStream()) {
        writer.write("<message>Chào Việt Nam</message>");
    }
    // Writer đã đóng; sau đó bind xml, execute SQL.
} finally {
    xml.free();
}
```

Đây là snippet tích hợp, cần `java.io.Writer` và Connection đã mở.

### Những điểm bắt buộc

- Chỉ gọi `setCharacterStream()` **một lần** trên object mới.
- Writer nhận **characters**, không phải raw binary bytes.
- Hoàn thành và **đóng Writer trước khi thực thi SQL**; Javadoc nói các stream chưa đóng tại `execute` có thể gây `SQLException`.
- Một số driver có buffering; **streaming API không bảo đảm zero-copy hoặc luôn dùng O(1) memory**.
- Không gọi `setString` sau `setCharacterStream` để “ghi nốt”; trạng thái writable đã bị tiêu thụ.

### Copy từ Reader

```java
SQLXML xml = connection.createSQLXML();
try {
    try (Reader input = Files.newBufferedReader(path, StandardCharsets.UTF_8);
         Writer output = xml.setCharacterStream()) {
        input.transferTo(output);
    }
    // Bind / execute khi stream đã hoàn tất.
} finally {
    xml.free();
}
```

Đây là **snippet**, cần biến `path` kiểu `Path` và imports `java.nio.file.Files`, `StandardCharsets`, `Reader`, `Writer`. Mã không chạy độc lập nếu chưa có Connection và Path thực tế.

**Phân biệt hai encoding layers:** `Files.newBufferedReader(..., UTF_8)` giải mã bytes của file đầu vào thành Java characters. `SQLXML.setCharacterStream()` nhận characters. Nếu XML declaration mô tả một byte encoding không phù hợp với nội dung khi serialize, phải kiểm soát đường chuyển đổi để tránh mâu thuẫn; không suy diễn rằng SQLXML Writer tự tạo đúng XML declaration cho mọi nguồn.

## 6. Khởi tạo theo binary stream: `setBinaryStream()`

`SQLXML.setBinaryStream()` trả `OutputStream` để ghi bytes biểu diễn XML. Theo Javadoc, stream bắt đầu tại **position 0**. Điều này **khác** với các phương thức LOB như `Blob.setBytes(pos, ...)` dùng LOB position 1-based.

```java
SQLXML xml = connection.createSQLXML();
try {
    String body = "<message>Xin chào 🌏</message>";
    try (OutputStream output = xml.setBinaryStream()) {
        output.write(body.getBytes(StandardCharsets.UTF_8));
    }
    // Bind và execute SQL sau khi output stream đóng.
} finally {
    xml.free();
}
```

Đây là đoạn tích hợp, cần imports `OutputStream`/`StandardCharsets`.

### XML encoding quan trọng như thế nào?

Đối với `setBinaryStream`, bạn truyền **bytes**. XML encoding được diễn giải theo quy tắc XML 1.0 (bao gồm XML declaration khi có). Nếu dùng UTF-8, nên giữ văn bản và XML declaration nhất quán:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>Xin chào</message>
```

Không tự chuyển `String.getBytes()` theo **default charset** khác nhau giữa môi trường. Dùng `StandardCharsets.UTF_8` khi dữ liệu được xác định là UTF-8. Nếu stream có XML declaration khác charset thật, driver/parser có thể báo lỗi hoặc đọc sai.

### Khi nào không nên dùng binary stream?

Nếu nguồn dữ liệu đã ở dạng Java `String`/`Reader` và bạn không cần byte-level control, dùng `setString` hoặc `setCharacterStream` thường dễ tránh sai encoding hơn. Nếu XML là file lớn đã được tạo theo byte encoding rõ ràng và không muốn chuyển toàn bộ vào String, `setBinaryStream` phù hợp hơn.

**Không nên dùng `setBinaryStream()` để gửi file ảnh hoặc JSON** rồi coi đó là XML; kiểu SQL XML có yêu cầu nội dung XML, khác BLOB.

## 7. `setResult` và `getSource`: DOM, SAX, StAX, Stream

`SQLXML` tích hợp với Java XML processing APIs:

```java
<T extends Result> T setResult(Class<T> resultClass) throws SQLException;
<T extends Source> T getSource(Class<T> sourceClass) throws SQLException;
```

Đây là **chữ ký API**, không phải method mà app cần viết lại.

### 7.1. Các loại Source/Result

| Nhóm | Đọc với `getSource` | Ghi với `setResult` |
| --- | --- | --- |
| DOM | `DOMSource.class` | `DOMResult.class` |
| SAX | `SAXSource.class` | `SAXResult.class` |
| StAX | `StAXSource.class` | `StAXResult.class` |
| Stream | `StreamSource.class` | `StreamResult.class` |

Theo Javadoc, driver hỗ trợ SQLXML phải cung cấp các loại `Source`/`Result` tối thiểu này; khi truyền `null`, implementation có thể chọn một loại cụ thể theo vendor.

**Đừng coi `getSource` là thao tác “xem trước vô hại”:** nó là một **read API**, có thể chuyển object thành not readable. `setResult` là một **write API**, tiêu thụ quyền khởi tạo đối tượng.

### 7.2. Ghi một DOM Document

Ví dụ **tích hợp** với một `org.w3c.dom.Document` đã chuẩn bị:

```java
SQLXML xml = connection.createSQLXML();
try {
    DOMResult result = xml.setResult(DOMResult.class);
    result.setNode(document);
    // Sau khi dữ liệu Result đã hoàn tất, bind XML và execute SQL.
} finally {
    xml.free();
}
```

Cần imports `javax.xml.transform.dom.DOMResult` và biến `document` hợp lệ. `SQLXML` có thể được driver triển khai dưới dạng XML optimized; `setResult` có thể tránh bước serialize text không cần thiết. Không có bảo đảm rằng mọi driver đạt cùng performance.

### 7.3. Đọc qua DOMSource

```java
DOMSource source = xmlFromDb.getSource(DOMSource.class);
Document doc = (Document) source.getNode();
// Dùng doc khi còn trong phạm vi xử lý hợp lệ.
```

Đây là snippet, cần `xmlFromDb` đọc từ ResultSet và các imports DOM tương ứng. Đọc qua `getSource` là một **cách tiêu thụ** dữ liệu; không gọi thêm `getString` trên cùng object với giả định luôn được phép.

### 7.4. StAX và các luồng XML lớn

Với dữ liệu lớn, `StAXSource`/`StAXResult` cho phép làm việc theo luồng sự kiện, tùy driver. Nhưng cần quan tâm:

- Đóng/hoàn tất `XMLStreamWriter` trước khi bind/execute.
- Đảm bảo parser/transformer không còn tham chiếu tới stream đã bị đóng.
- Tránh materialize toàn bộ DOM nếu file XML lớn.
- Cấu hình parser chống XXE/DTD/external entity đối với XML không đáng tin cậy.

Không có quy tắc rằng `setResult(StAXResult.class)` luôn nhanh nhất. Hãy đo với driver/DB, kích thước XML, mức độ parse/validate và hệ thống thực.

## 8. Ví dụ Java 17+ hoàn chỉnh: SQLXML lifecycle mock

Ví dụ chạy độc lập sau dùng các interface chuẩn `java.sql.Connection` và `SQLXML`, đồng thời tạo **test double trong bộ nhớ** thay cho database. Nó cố ý mô phỏng:

- `createSQLXML()` tạo object mới.
- Đối tượng chỉ được **khởi tạo một lần**.
- Gọi `getString`/`getCharacterStream`/`getBinaryStream` đọc **một lần**.
- Đọc khi chưa khởi tạo hoặc stream ghi chưa đóng bị từ chối trong mock.
- `free` có tính idempotent; đọc lại sau `free` báo `SQLException`.
- `Connection.close` làm Connection không tạo tiếp SQLXML được.
- StAX escape `&` chính xác khi tạo XML text.

**Đây không phải JDBC driver.** Fixture mock chưa triển khai `getSource` và `setResult`, thay vào đó ném `SQLFeatureNotSupportedException`, nhằm giữ ví dụ tập trung vào vòng đời. Đối với một **driver thật hỗ trợ SQL XML**, Javadoc yêu cầu các methods của `SQLXML` được triển khai đầy đủ; không lấy hành vi thiếu của mock làm quy tắc cho driver. Mock chọn cho phép **một lần đọc sau khi ghi** để kiểm tra dữ liệu, trong khi Javadoc cho phép driver thật **không hỗ trợ read-after-write**.

### 8.1. Cấu trúc

```text
sqlxml-demo/
└── SqlXmlLifecycleDemo.java
```

Không cần driver JDBC hay cấu hình DB, chỉ cần JDK 17+.

### 8.2. Toàn bộ file `SqlXmlLifecycleDemo.java`

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.Reader;
import java.io.StringReader;
import java.io.StringWriter;
import java.io.Writer;
import java.lang.reflect.Proxy;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;
import java.sql.SQLXML;
import javax.xml.stream.XMLOutputFactory;
import javax.xml.stream.XMLStreamWriter;
import javax.xml.transform.Result;
import javax.xml.transform.Source;

public final class SqlXmlLifecycleDemo {
    private static final class MemorySQLXML implements SQLXML {
        private String data;
        private boolean initialized;
        private boolean writing;
        private boolean read;
        private boolean freed;

        private void active() throws SQLException {
            if (freed) throw new SQLException("SQLXML was freed");
        }
        private void beginWrite() throws SQLException {
            active();
            if (initialized) throw new SQLException("SQLXML already initialized");
            initialized = true;
        }
        private String readOnce() throws SQLException {
            active();
            if (!initialized || writing || read) {
                throw new SQLException("SQLXML is not readable");
            }
            read = true;
            return data;
        }

        @Override public void free() {
            freed = true;
            data = null;
            writing = false;
        }
        @Override public void setString(String value) throws SQLException {
            beginWrite();
            data = value;
        }
        @Override public String getString() throws SQLException {
            return readOnce();
        }
        @Override public Writer setCharacterStream() throws SQLException {
            beginWrite();
            writing = true;
            return new StringWriter() {
                private boolean closed;
                @Override public void close() {
                    if (!closed) {
                        data = toString();
                        writing = false;
                        closed = true;
                    }
                }
            };
        }
        @Override public OutputStream setBinaryStream() throws SQLException {
            beginWrite();
            writing = true;
            return new ByteArrayOutputStream() {
                private boolean closed;
                @Override public void close() throws IOException {
                    if (!closed) {
                        super.close();
                        data = new String(toByteArray(), StandardCharsets.UTF_8);
                        writing = false;
                        closed = true;
                    }
                }
            };
        }
        @Override public Reader getCharacterStream() throws SQLException {
            return new StringReader(readOnce());
        }
        @Override public InputStream getBinaryStream() throws SQLException {
            return new ByteArrayInputStream(
                    readOnce().getBytes(StandardCharsets.UTF_8));
        }
        @Override public <T extends Source> T getSource(Class<T> kind)
                throws SQLException {
            throw new SQLFeatureNotSupportedException("Test double: getSource");
        }
        @Override public <T extends Result> T setResult(Class<T> kind)
                throws SQLException {
            throw new SQLFeatureNotSupportedException("Test double: setResult");
        }
    }

    private static Connection memoryConnection() {
        final boolean[] closed = {false};
        return (Connection) Proxy.newProxyInstance(
            SqlXmlLifecycleDemo.class.getClassLoader(),
            new Class<?>[] {Connection.class},
            (proxy, method, args) -> {
                String name = method.getName();
                if (name.equals("close")) {closed[0] = true; return null;}
                if (name.equals("isClosed")) return closed[0];
                if (closed[0]) throw new SQLException("Connection is closed");
                if (name.equals("createSQLXML")) return new MemorySQLXML();
                throw new SQLFeatureNotSupportedException(
                        "Test double: " + name);
            });
    }

    @FunctionalInterface
    private interface SqlAction { void run() throws SQLException; }

    private static boolean throwsSqlException(SqlAction action) {
        try { action.run(); return false; }
        catch (SQLException expected) { return true; }
    }
    private static void check(String name, boolean ok) {
        if (!ok) throw new AssertionError(name);
        System.out.println(name + "=true");
    }

    public static void main(String[] args) throws Exception {
        Connection connection = memoryConnection();
        try (connection) {
            SQLXML first = connection.createSQLXML();
            try {
                check("factoryReturnsSQLXML", first instanceof SQLXML);
                check("uninitializedReadFails",
                        throwsSqlException(first::getString));
                first.setString("<note>Xin chào</note>");
                check("secondInitializationFails",
                        throwsSqlException(() -> first.setString("<again/>")));
                check("setStringValue",
                        first.getString().equals("<note>Xin chào</note>"));
                check("repeatedReadFails",
                        throwsSqlException(first::getString));
            } finally { first.free(); }
            first.free();
            check("readAfterFreeFails",
                    throwsSqlException(first::getString));

            SQLXML text = connection.createSQLXML();
            try {
                try (Writer writer = text.setCharacterStream()) {
                    writer.write("<text>Thảo luận</text>");
                    check("readBeforeWriterCloseFails",
                            throwsSqlException(text::getString));
                }
                try (Reader reader = text.getCharacterStream()) {
                    StringWriter copied = new StringWriter();
                    reader.transferTo(copied);
                    check("characterStreamValue",
                            copied.toString().equals("<text>Thảo luận</text>"));
                }
            } finally { text.free(); }

            SQLXML binary = connection.createSQLXML();
            try {
                String payload = "<binary>Tiếng Việt 🌏</binary>";
                try (OutputStream out = binary.setBinaryStream()) {
                    out.write(payload.getBytes(StandardCharsets.UTF_8));
                }
                try (InputStream in = binary.getBinaryStream()) {
                    check("binaryStreamValue",
                            new String(in.readAllBytes(), StandardCharsets.UTF_8)
                                .equals(payload));
                }
            } finally { binary.free(); }

            StringWriter xmlText = new StringWriter();
            XMLStreamWriter xmlWriter =
                    XMLOutputFactory.newFactory().createXMLStreamWriter(xmlText);
            xmlWriter.writeStartElement("message");
            xmlWriter.writeCharacters("Chào & tạm biệt");
            xmlWriter.writeEndElement();
            xmlWriter.close();
            SQLXML escaped = connection.createSQLXML();
            try {
                escaped.setString(xmlText.toString());
                check("staxEscapesMarkup",
                        escaped.getString().contains("Chào &amp; tạm biệt"));
            } finally { escaped.free(); }
        }
        check("connectionClosed", connection.isClosed());
        check("creationAfterCloseFails",
                throwsSqlException(connection::createSQLXML));
    }
}
```

### 8.3. Chạy chương trình

Ở thư mục chứa `SqlXmlLifecycleDemo.java`:

```bash
javac --release 17 SqlXmlLifecycleDemo.java
java SqlXmlLifecycleDemo
```

Ví dụ dùng `java.sql`, `java.xml` và các lớp chuẩn `java.base`, không cần thêm JAR bên ngoài. Mã biên dịch với `--release 17` để bảo đảm không vô tình dùng `SQLXML.close()` chỉ mới có từ JDK 26.

### 8.4. Stdout đã kiểm chứng bằng OpenJDK 24

```text
factoryReturnsSQLXML=true
uninitializedReadFails=true
secondInitializationFails=true
setStringValue=true
repeatedReadFails=true
readAfterFreeFails=true
readBeforeWriterCloseFails=true
characterStreamValue=true
binaryStreamValue=true
staxEscapesMarkup=true
connectionClosed=true
creationAfterCloseFails=true
```

**12 phép kiểm tra đã chạy và đạt.** `check` ném `AssertionError` nếu điều kiện sai, nên `...=true` không phải kết quả được in mặc định. Chương trình đã được chạy thực tế với `javac --release 17` và JDK 24 trên Windows; các file test tạm đã được xóa.

### 8.5. Đọc từng phép thử

| Tên | Ý nghĩa |
| --- | --- |
| `factoryReturnsSQLXML` | `Connection.createSQLXML` trong mock trả object implement `SQLXML`. |
| `uninitializedReadFails` | Mock không cho đọc khi object chưa được khởi tạo. |
| `secondInitializationFails` | Đã `setString` thì không thể khởi tạo lại qua `setString` lần nữa. |
| `setStringValue` | Mock lưu và trả nội dung trong một lần đọc sau khi ghi (không bảo đảm ở mọi driver). |
| `repeatedReadFails` | Mock áp quy tắc read-once. |
| `readAfterFreeFails` | Sau `free`, thao tác đọc bị từ chối. |
| `readBeforeWriterCloseFails` | Mock chặn đọc khi writer ghi chưa đóng. |
| `characterStreamValue` | Nội dung văn bản tiếng Việt được chuyển qua Writer và Reader. |
| `binaryStreamValue` | XML chứa chữ Việt và emoji được truyền bằng UTF-8 bytes; đầu ra khớp. |
| `staxEscapesMarkup` | StAX escape ampersand trong XML text thành `&amp;`. |
| `connectionClosed` | `Connection` được đóng bằng try-with-resources. |
| `creationAfterCloseFails` | Mock từ chối tạo SQLXML từ Connection đã đóng. |

**Hạn chế của test double:** Nó chỉ mô phỏng một phần JDBC và chủ ý cấm một số state transitions. Tài liệu JDBC cho phép driver thật làm đối tượng **không đọc được ngay sau khi ghi**. Mock không thể kiểm chứng khả năng lưu SQL XML trên PostgreSQL, SQL Server, Oracle hoặc một DBMS cụ thể; cần integration test độc lập.

## 9. Đưa SQLXML vào database bằng `PreparedStatement.setSQLXML`

Đây là **ví dụ tích hợp**, không chạy độc lập nếu thiếu JDBC driver, DB schema, credentials và Connection thật:

```java
static int saveXml(Connection connection, String document) throws SQLException {
    SQLXML value = connection.createSQLXML();
    try {
        value.setString(document);
        try (PreparedStatement ps = connection.prepareStatement(
                "INSERT INTO xml_documents(payload) VALUES (?)")) {
            ps.setSQLXML(1, value);
            return ps.executeUpdate();
        }
    } finally {
        value.free();
    }
}
```

Method cần imports `java.sql.Connection`, `PreparedStatement`, `SQLXML` và `SQLException`. Cột `xml_documents.payload` cần là kiểu dữ liệu XML tương thích trên DBMS.

### Vì sao dùng parameter binding?

- `?` là placeholder cho SQL parameter, được gán bằng `ps.setSQLXML(1, value)`.
- XML value được truyền qua driver theo protocol tương ứng, không bị ghép vào SQL string.
- Nếu document chứa dấu nháy hoặc ký tự XML đặc biệt, câu SQL vẫn được parameterized đúng.
- Driver có thể tối ưu hóa XML storage/validation theo kiểu SQL XML thay vì một chuỗi `VARCHAR` thường.

**Không mặc định dữ liệu XML đã được validate:** XML malformed có thể gây `SQLException` ở `setString`, `setSQLXML` hoặc `executeUpdate`, tùy implementation. Ứng dụng phải xử lý lỗi và rollback phù hợp.

### SQL column phải tồn tại

DDL của kiểu XML **không thống nhất hoàn toàn giữa DBMS**. Một số hệ quản trị dùng `XML`, số khác có kiểu `XMLTYPE` hoặc không hỗ trợ XML native. Đừng copy một DDL mẫu của DBMS A sang DBMS B rồi nghĩ đó là “JDBC SQL chuẩn”. Nếu DB không có SQL XML type, phải đánh giá dùng text/LOB hoặc storage khác và phương thức bind tương ứng.

### `createSQLXML` không tự INSERT

`Connection.createSQLXML()` tạo một đối tượng JDBC; **không tự chèn một hàng** vào database. Khi `ps.executeUpdate()` hoàn tất thành công và transaction commit theo quy tắc ứng dụng, dữ liệu mới được persist theo hợp đồng DB.

### Khi nào gọi `free`?

Trong đoạn trên, `free` nằm trong `finally` và được gọi **sau khi `executeUpdate` đã hoàn tất** (hoặc có lỗi). Không gọi `free` ngay sau `ps.setSQLXML` mà trước `executeUpdate`, vì driver có thể chỉ tiêu thụ dữ liệu khi thực thi statement.

## 10. Nhận SQLXML từ ResultSet

Đối tượng SQLXML không nhất thiết được tạo từ `Connection`. Khi đọc dữ liệu đã lưu, dùng:

```java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT payload FROM xml_documents WHERE id = ?")) {
    ps.setLong(1, id);
    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            SQLXML xml = rs.getSQLXML(1);
            if (xml != null) {
                try {
                    String text = xml.getString();
                    // Xử lý text (tránh gọi getString lần hai).
                } finally {
                    xml.free();
                }
            }
        }
    }
}
```

Đây là snippet tích hợp, cần `Connection`, ID và SQL schema thật; không nằm trong chương trình mô phỏng.

### Đọc chỉ một lần

Sau `getString()`, SQLXML đã chuyển sang **not readable**. Nếu muốn dùng nội dung nhiều lần ở application layer, sử dụng chính `String text` được lưu từ lần đọc đó. Với XML quá lớn, dùng `getCharacterStream`/`getBinaryStream` để xử lý theo luồng và giải phóng sau khi dữ liệu đã được tiêu thụ.

### SQL NULL

`ResultSet.getSQLXML(...)` có thể trả `null` khi cột SQL là `NULL`. Hãy kiểm tra null trước khi gọi `free`/`getString`.

**Đừng nhầm:** một `SQLXML` chưa khởi tạo từ `Connection.createSQLXML()` khác với cột SQL `NULL`; chúng không thay thế nhau. Đối tượng mới **chưa có XML value**, còn SQL NULL là một giá trị database đặc biệt.

### Transaction lifetime

Javadoc mô tả SQLXML thường có hiệu lực **trong transaction nơi được tạo**, trừ khi `free` được gọi sớm. Không trả một `SQLXML` từ repository rồi đóng ResultSet/Connection và mong service tầng trên vẫn đọc được. Đọc và materialize hoặc stream hết trong phạm vi quản lý resource hợp lệ.

## 11. Vòng đời cùng transaction và connection pool

Trong ứng dụng có DataSource/connection pool:

```text
request nhận Connection logical handle
      |
      +--> createSQLXML
      |        |
      |        +--> initialize exactly once
      |        +--> close Writer/OutputStream
      |        +--> setSQLXML / execute
      |        +--> free
      |
      +--> commit/rollback khi cần
      |
      +--> close logical Connection handle
            (pool quyết định trả về pool hay đóng vật lý)
```

### Không giữ SQLXML qua request

Tránh cache một `SQLXML` trong singleton hoặc gửi chính đối tượng đến background process sau khi Connection đã được trả về pool. Nếu SQLXML là locator, nó có thể trỏ tới transaction/session đã hết hiệu lực.

### Dùng try-with-resources đúng cấp

Ở Java 17, `Connection`, `PreparedStatement`, `ResultSet`, `InputStream` và `Writer` là những `AutoCloseable` phù hợp trong try-with-resources. Nhưng **SQLXML chưa extends AutoCloseable ở Java 17**; dùng `free` trong `finally`.

```java
try (Connection c = dataSource.getConnection()) {
    SQLXML xml = c.createSQLXML();
    try {
        xml.setString(document);
        try (PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setSQLXML(1, xml);
            ps.executeUpdate();
        }
    } finally {
        xml.free();
    }
}
```

Đây là **snippet tích hợp** cần `dataSource`, `document`, `sql` từ ứng dụng. Nếu transaction manual, thêm `commit`/`rollback` đúng cách; try-with-resources chỉ đóng Connection, không tự hiện thực policy transaction mong muốn.

### `free` có thể ném SQLException

Đôi khi cả thao tác chính lẫn `free` đều lỗi. Khi dùng `finally` trực tiếp, exception từ dọn dẹp có thể che lỗi ban đầu. Trong production cần xử lý/ghi suppressed exception phù hợp (hoặc dùng cách quản lý AutoCloseable khi target JDK 26+), nhưng không được âm thầm bỏ qua mọi lỗi release.

## 12. Thay đổi quan trọng của JDK 26: `SQLXML extends AutoCloseable`

**Java SE 26/JDBC 4.5** đã bổ sung `AutoCloseable` cho một số SQL types, bao gồm **`SQLXML`**. Phương thức `close()` mặc định gọi `free()`.

| Phiên bản biên dịch | SQLXML là AutoCloseable trực tiếp? | Cách quản lý |
| --- | --- | --- |
| **Java 17–25** | **Chưa** | `SQLXML.free()` trong `finally` |
| **Java 26+** | **Có**; `close()` mặc định gọi `free()` | Có thể `try (SQLXML x = ...)`; `free` vẫn hợp lệ |

### 12.1. Code chạy từ Java 17 trở lên

```java
SQLXML xml = connection.createSQLXML();
try {
    xml.setString(document);
    // Bind và execute SQL.
} finally {
    xml.free();
}
```

Đây là cách giữ tương thích Java 17/21/24 và vẫn đúng trong JDK 26.

### 12.2. Code chỉ dành cho JDK 26+

```java
// Chỉ compile khi target Java 26 hoặc cao hơn.
try (SQLXML xml = connection.createSQLXML()) {
    xml.setString(document);
    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        ps.setSQLXML(1, xml);
        ps.executeUpdate();
    }
}
// Tự động gọi close() -> free().
```

Đây là đoạn minh họa **JDK 26+**, không được biên dịch trong fixture Java 17 của mục 8. Nếu dùng `javac --release 17`, cú pháp `try(SQLXML ...)` **không compile**, vì SQLXML của Java 17 chưa implement `AutoCloseable`.

### 12.3. Đừng hiểu sai “AutoCloseable” thành “tự lưu”

`close`/`free` chỉ giải phóng tài nguyên SQLXML, không tự INSERT/UPDATE, không COMMIT và cũng không quản lý vòng đời `Connection` thay bạn. Đặt block try-with-resources **sao cho SQL statement đã tiêu thụ dữ liệu trước khi SQLXML được đóng**.

Nguồn hiện hành: [Oracle JDK 26 Release Notes — Add JDBC 4.5 MR Support](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html); [Java SE 26 — `SQLXML`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLXML.html).

## 13. XML security: XXE, entity expansion, DTD và input validation

`Connection.createSQLXML` là một **API lưu trữ**, không phải bộ lọc bảo mật XML. Nếu nhận XML từ nguồn không đáng tin, cần có chính sách riêng trước khi xử lý/parse.

### 13.1. Khi nào có nguy cơ XXE?

Các XML parsers/transformers có thể được cấu hình cho phép tải external entities, external DTD hoặc tài nguyên qua URL/file system. XML độc hại có thể yêu cầu đọc tài nguyên trái phép hoặc tiêu thụ rất nhiều CPU/memory qua entity expansion.

**Không suy ra:** vì JDBC nhận một `SQLXML` nên XML đó đã được kiểm tra chống XXE. Khi ứng dụng gọi parser, cần cấu hình an toàn cho JAXP/StAX/SAX/DOM theo trust model và phiên bản thư viện.

### 13.2. Một số nguyên tắc hiện hành

- Với dữ liệu XML không tin cậy, **giới hạn hoặc tắt DTD/external entities** khi không có lý do nghiệp vụ để bật.
- Dùng `XMLConstants.ACCESS_EXTERNAL_DTD` và `ACCESS_EXTERNAL_SCHEMA` với phạm vi phù hợp; cân nhắc `FEATURE_SECURE_PROCESSING` và các hạn mức parser.
- Với DOM, cấu hình `DocumentBuilderFactory` trước khi parse; với StAX, cấu hình `XMLInputFactory` trước khi tạo reader.
- Tránh để parser tự mở URL hoặc file từ untrusted XML. Áp dụng giới hạn kích thước, nesting depth và thời gian xử lý.
- Không coi `getSource(DOMSource.class)` luôn dùng parser do ứng dụng kiểm soát; implementation có thể dùng logic parsing riêng. Nếu cần chính sách bảo mật XML nghiêm ngặt, có thể đọc stream và parse bằng parser đã được cấu hình ở tầng ứng dụng.
- XML escaping ở nội dung/attribute cần thư viện serializer; không tự ghép user input vào raw XML.
- Cấu hình bảo mật phải được kiểm thử theo JDK/provider; không giả định một feature URI được mọi XML implementation bên ngoài hỗ trợ như nhau.

### 13.3. Snippet cấu hình DOM parser

Đây là **snippet minh họa** cho XML không tin cậy, không nằm trong chương trình SQLXML mock:

```java
DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
factory.setNamespaceAware(true);
factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
factory.setXIncludeAware(false);

DocumentBuilder parser = factory.newDocumentBuilder();
Document document = parser.parse(inputStream);
```

Cần imports từ `javax.xml.parsers`, `javax.xml.XMLConstants`, `org.w3c.dom` và `InputStream`. Khi XML factory provider không hỗ trợ một property/feature, cần **xử lý lỗi cấu hình rõ ràng** thay vì tiếp tục parse không có protection; trên JDK tích hợp hiện đại những settings nêu trên có thể được áp dụng. Không đồng nghĩa đoạn này bảo vệ hết các loại XML attacks; vẫn phải giới hạn kích thước, xử lý XSLT/schema separately khi có.

## 14. Những trạng thái lỗi và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| `SQLFeatureNotSupportedException` tại `createSQLXML` | Driver không hỗ trợ SQL XML type/factory | Kiểm tra DBMS, driver version, schema |
| `SQLException` khi tạo SQLXML từ Connection | Connection đóng hoặc lỗi database | Kiểm tra logical connection, network, transaction |
| `SQLException` khi gọi `setString` lần hai | Object đã được khởi tạo, không writable | Tạo **SQLXML mới** cho nội dung mới |
| `SQLException` ở `getString` lần hai | Object đã not readable | Materialize từ lần đọc đầu, đừng gọi lại |
| Không đọc được sau khi vừa ghi | Implementation chuyển object sang not readable khi set | Bind trực tiếp vào PreparedStatement, không dùng read-after-write |
| `SQLException` khi execute với stream ghi | Writer/OutputStream/Result chưa được hoàn tất hoặc XML không hợp lệ | Đóng stream/result trước execute; kiểm tra XML input |
| `SQLException` khi dùng sau `free` | SQLXML đã hết hiệu lực | Không tái sử dụng, tạo object mới |
| XML có dấu tiếng Việt bị sai | Byte encoding/charset declaration không khớp | Kiểm tra `setString` vs `setBinaryStream`, encoding thực |
| Query trả `null` | Cột XML là SQL NULL | Kiểm tra `rs.getSQLXML(index) != null` |
| XML vượt bộ nhớ khi `getString` | Materialize toàn bộ tài liệu quá lớn | Dùng Reader/InputStream/Source theo thiết kế |
| XXE/DTD file access | Parser không được khóa theo trust model | Secure XML parser settings và input limits |
| XML khác dạng text sau khi đọc | Driver/DB có thể canonicalize/serialize lại XML | Kiểm tra semantics XML, không dựa exact whitespace khi DB tối ưu |
| SQLXML “sống” sau Connection close không ổn định | Locator/transaction đã hết lifetime | Xử lý trong connection scope |
| `try (SQLXML ...)` không compile với `--release 17` | SQLXML chỉ extends AutoCloseable từ JDK 26 | Dùng `free()` khi target Java 17–25 |

### XML validation có thể xảy ra muộn

Một số driver đánh giá XML value ở bước set; một số khác trì hoãn đến bước `ps.executeUpdate`/`execute`. Vì vậy thành công của `xml.setString(raw)` **không chứng minh SQL XML đã hợp lệ hoặc đã được database nhận**. Nếu nghiệp vụ cần đảm bảo XML well-formed trước khi gửi, validate bằng một parser an toàn có giới hạn tài nguyên.

### Transaction rollback không phải SQLXML.free

`rollback` hủy các thay đổi trong transaction theo DB semantics. `free` dọn tài nguyên Java/JDBC đại diện SQLXML. Chúng là **hai trách nhiệm khác nhau**. Dùng đúng cả hai khi cần, đừng thay `rollback` bằng `free` hoặc ngược lại.

## 15. So sánh SQLXML, CLOB và JSON

| Loại | Nội dung | Đặc điểm |
| --- | --- | --- |
| `SQLXML` | XML document/value theo SQL XML type | Có XML-specific JDBC APIs, `Source`/`Result`, state/lifetime riêng |
| `Clob` | Dữ liệu ký tự lớn | Không đương nhiên parse/validate XML hay có XML query semantics |
| `NClob` | Character large object theo national character SQL type | Không đồng nghĩa XML, khác `SQLXML` |
| `String` / `VARCHAR` | Chuỗi text | Không có lifecycle locator và XML-specific interface |
| Native JSON/SQL JSON | JSON theo DB schema/driver hỗ trợ | Không phải XML; lưu JSON bằng SQLXML là sai kiểu dữ liệu |

Nếu DB không hỗ trợ native XML, có thể cân nhắc lưu XML text trong `CLOB`/`VARCHAR` phù hợp với schema, nhưng điều đó **không tạo ra SQLXML type** và không tự bổ sung XML storage/index/XQuery của database. Giải pháp đúng phụ thuộc yêu cầu ứng dụng, driver và DBMS.

**Nhắc lại:** Chủ đề ở đây là `Connection.createSQLXML` và **vòng đời SQLXML**, không phải một bài về toàn bộ XML databases hay parser frameworks.

## 16. Checklist sản phẩm

1. Xác nhận database và driver hỗ trợ **SQL XML data type** và `Connection.createSQLXML()`.
2. Chuẩn bị DDL/schema thật; không tự giả định mọi DBMS đều khai báo kiểu XML giống nhau.
3. Giữ Connection mở suốt thời gian tạo, khởi tạo và bind/execute SQL.
4. **Tạo đối tượng rỗng** bằng `createSQLXML`; đừng nghĩ nó đã lưu data.
5. Chọn **một** đường khởi tạo: String, character stream, binary stream hoặc Result.
6. Đóng hoàn chỉnh **Writer/OutputStream** trước khi gọi `PreparedStatement.execute`.
7. Đừng gọi hai `set...` methods trên cùng SQLXML; nếu cần thay nội dung, tạo object mới.
8. Đừng đọc SQLXML nhiều lần hoặc đọc sau khi `free`; dùng dữ liệu materialized nếu thật sự cần.
9. Không giả định mọi driver cho đọc lại cùng SQLXML sau khi khởi tạo để ghi.
10. `PreparedStatement.setSQLXML` dùng placeholder; không ghép XML text vào SQL string.
11. Dùng StAX/DOM serializer để escape XML khi tạo document từ dữ liệu người dùng.
12. Xác định đúng encoding khi chọn binary streams; với text streams dùng characters.
13. Khi nhận XML không đáng tin, cấu hình parser/transformer an toàn chống XXE và giới hạn resources.
14. Không để parser tự tải external DTD/schema/file không được cho phép.
15. Đọc `ResultSet.getSQLXML` trong phạm vi ResultSet, Connection và transaction, kiểm tra SQL NULL.
16. Dùng `free()` trong `finally` cho Java 17–25; JDK 26+ có `AutoCloseable.close()`.
17. Quản lý `Connection`/`PreparedStatement`/`ResultSet` riêng; `free` không thay `commit/rollback`.
18. Dùng stream cho XML lớn, tránh `getString` nếu có nguy cơ áp lực bộ nhớ.
19. Khi đổi JDBC driver/version, kiểm tra lại `getSource`/`setResult` và khả năng tối ưu hóa XML.
20. Test cả chuỗi XML có Unicode tiếng Việt, supplementary code points và entity escaping.
21. Viết integration tests cho XML malformed, DTD/XXE, SQL NULL, transaction rollback, timeout và connection close.
22. Phân biệt **mock behavior** và **driver/database behavior**, không khẳng định test double xác minh DB thật.

## 17. Bài tập thực hành

### Bài tập 1 — Khởi tạo một lần

Trong `SqlXmlLifecycleDemo`, thử gọi `first.setString("<again/>")` sau lần set đầu. Chương trình đã có assertion `secondInitializationFails=true`. Hãy giải thích vì sao đối tượng không writable nữa, và sửa luồng nghiệp vụ bằng cách **tạo SQLXML mới** nếu muốn gửi tài liệu thứ hai.

### Bài tập 2 — Đọc một lần

Chạy `getString` hai lần trên cùng một instance trong mock; giải thích assertion `repeatedReadFails=true`. Với driver thật, chọn một lần `getString` hoặc `getCharacterStream`; nếu cần hai phép xử lý khác nhau, dùng cùng `String`/stream đã materialized một cách có kiểm soát.

### Bài tập 3 — Stream chưa đóng

Thử đọc mock khi `Writer` vẫn mở, quan sát `readBeforeWriterCloseFails=true`. Với database thật, câu hỏi quan trọng là **đã đóng stream trước `PreparedStatement.execute` chưa**, không phải driver có cho read-back hay không.

### Bài tập 4 — Unicode và escaping

Thay text bằng `"Tên <Phương> & bạn"` rồi tạo XML bằng `XMLStreamWriter.writeCharacters`. Quan sát `<` thành `&lt;` và `&` thành `&amp;` trong nội dung element; xác nhận text gốc có thể khôi phục bằng parser an toàn.

### Bài tập 5 — Đọc từ database thật

Tạo bảng có XML column theo cú pháp đúng của DB đang sử dụng, ghi bằng `PreparedStatement.setSQLXML`, đọc bằng `ResultSet.getSQLXML`, đối chiếu **semantic XML**. Không bắt buộc byte-for-byte XML serialization giống nhau vì DB/driver có thể tối ưu hóa biểu diễn.

### Bài tập 6 — So sánh target Java

Biên dịch chương trình chính bằng `javac --release 17`; thử đoạn `try (SQLXML x = ...)` từ mục 12 bằng compiler target JDK 26. Giải thích khác biệt `AutoCloseable` giữa các API versions và vì sao `free()` vẫn hữu ích trong dự án cần chạy nhiều Java versions.

### Bài tập 7 — Xử lý XML không đáng tin cậy

Tạo XML với một khai báo `DOCTYPE` ngoài ý muốn, dùng parser cấu hình an toàn để kiểm tra tình huống DTD bị chặn. Đừng dùng test đọc file/network thật ngoài môi trường kiểm thử được kiểm soát. Mục tiêu là nhận ra **SQLXML chỉ là phần ánh xạ JDBC**, không phải lớp chống XXE.

## 18. Câu hỏi tự kiểm tra

**1. `Connection.createSQLXML()` có đưa nội dung XML vào DB ngay không?**

Không. Nó tạo đối tượng `SQLXML` rỗng; cần khởi tạo nội dung và bind/execute SQL.

**2. Các phương thức ghi có thể dùng để khởi tạo SQLXML?**

`setString`, `setCharacterStream`, `setBinaryStream` và `setResult`. Chọn **một** đường trên object mới.

**3. Sau `setString` có nên `setString` lần hai để sửa giá trị?**

Không. SQLXML đã not writable; tạo instance mới nếu cần giá trị khác.

**4. Sau `getString` một lần, có nên gọi `getBinaryStream` để đọc tiếp?**

Không được mặc định. Theo mô hình SQLXML, read API đã tiêu thụ trạng thái readable. Muốn tái sử dụng, materialize dữ liệu từ lần đọc đầu.

**5. SQLXML được tạo để ghi có luôn đọc lại được qua `getString` trước khi bind không?**

Không. Implementation có thể đánh dấu not readable ngay khi bắt đầu ghi. Dùng dữ liệu nguồn để kiểm tra, bind SQLXML trực tiếp.

**6. `free` có nghĩa gì?**

Giải phóng tài nguyên của `SQLXML`, khiến object không còn dùng được (ngoài `free`/`close` theo JDK). Nó không commit/rollback transaction.

**7. Vì sao phải đóng OutputStream/Writer trước execute?**

Vì stream còn mở có thể khiến dữ liệu XML chưa hoàn tất; Javadoc nêu `SQLException` khi execute với XML streams chưa đóng.

**8. Java 17 có thể `try (SQLXML xml = connection.createSQLXML())` không?**

Không, SQLXML chỉ extends `AutoCloseable` từ JDK 26; Java 17 cần `free` tường minh.

**9. `ResultSet.getSQLXML` khác `Connection.createSQLXML` thế nào?**

`getSQLXML` đọc giá trị từ DB; `createSQLXML` tạo object mới chưa có dữ liệu để ghi.

**10. Nếu muốn xem XML nhiều lần, phải làm gì?**

Lấy một lần thành `String`/DOM hoặc dữ liệu khác nếu kích thước cho phép, rồi dùng representation do app sở hữu; không đọc SQLXML lặp đi lặp lại.

**11. Có thể truyền một hình JPEG vào `setBinaryStream` của SQLXML không?**

Không có lý do hợp lệ: đó là bytes của XML theo XML encoding rules, không phải binary arbitrary. Với ảnh, cân nhắc BLOB/object storage.

**12. XML với DTD và external entity có tự an toàn chỉ vì lưu bằng SQLXML?**

Không. Parser/transformer có thể cần cấu hình phòng XXE, chặn external resources và giới hạn kích thước/nesting.

**13. SQLXML mới có sống mãi sau khi Connection/transaction đóng không?**

Không được giả định. Nó có thể là locator, theo Javadoc hợp lệ trong transaction nơi được tạo. Xử lý trong lifetime và `free` đúng lúc.

**14. `setSQLXML` có tự escape XML text chưa?**

Nó bind SQL parameter, không phải XML serializer. Phải tạo XML well-formed/escape content bằng XML API trước đó.

**15. Driver không hỗ trợ createSQLXML thì nên làm gì?**

Nhận `SQLFeatureNotSupportedException`, xác định DB schema/driver và lựa chọn lưu text hoặc loại dữ liệu khác **nếu nghiệp vụ cho phép**, không âm thầm làm sai kiểu.

**16. Source/Result nào được hỗ trợ chuẩn?**

DOM, SAX, StAX và Stream variants được nêu trong Java SE `SQLXML` Javadoc. Đừng truyền class tùy ý không thuộc hierarchy `Source`/`Result`.

## Tài liệu chính thức hiện hành

- [Oracle Java SE 26 — `java.sql.Connection`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Connection.html): `createSQLXML`, điều kiện lỗi, connection lifetime.
- [Oracle Java SE 26 — `java.sql.SQLXML`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLXML.html): đầy đủ state model, stream, `setString`, `getString`, `getSource`, `setResult`, `free` và `close`.
- [Oracle Java SE 17 — `SQLXML`](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLXML.html): đối chiếu Java 17 chưa extends AutoCloseable; `free` là đường cleanup tương thích.
- [Oracle Java SE 26 — `PreparedStatement`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/PreparedStatement.html): `setSQLXML`, bind parameters, execute.
- [Oracle Java SE 26 — `ResultSet`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/ResultSet.html): `getSQLXML`, SQL NULL.
- [Oracle Java SE 26 — `SQLFeatureNotSupportedException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLFeatureNotSupportedException.html): driver có thể không hỗ trợ SQL XML type.
- [Oracle Java SE 26 — `SQLException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLException.html): xử lý lỗi JDBC.
- [Oracle JDK 26 Release Notes — JDBC 4.5 MR](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html): `SQLXML`/`Blob`/`Clob`/`NClob` mới hỗ trợ `AutoCloseable`.
- [Oracle Java SE 26 — `XMLStreamWriter`](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLStreamWriter.html): ghi XML theo StAX với escaping.
- [Oracle Java SE 26 — `XMLConstants`](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/XMLConstants.html): xử lý external resource access và secure XML processing.
- [Oracle Java SE 26 — `DocumentBuilderFactory`](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/parsers/DocumentBuilderFactory.html): parser XML configurable.
- [Oracle Java SE 26 — `javax.xml.transform.Source`](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/transform/Source.html), [`Result`](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/transform/Result.html): XML source/result API.

**Ghi nhớ:** `Connection.createSQLXML()` tạo **SQLXML mới, chưa có XML value**. Hãy **chọn một phương thức ghi**, đóng stream/Result trước SQL execute, **bind `PreparedStatement.setSQLXML`**, rồi **giải phóng bằng `free()`** trong Java 17+. SQLXML có trạng thái **một lần đọc/một lần ghi**, thường phụ thuộc connection/transaction, không phải String có thể tái sử dụng. Từ **Java 26**, `SQLXML` mới hỗ trợ `AutoCloseable.close()` để dọn tài nguyên qua try-with-resources; điều đó không thay quy tắc khởi tạo một lần, SQL execution hoặc bảo mật XML.
