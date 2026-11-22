# Kiểm thử XML không hợp lệ, null và dữ liệu chưa ghi hoàn tất với JDBC SQLXML

`java.sql.SQLXML` đại diện cho một giá trị SQL kiểu XML thông qua JDBC. Ứng dụng có thể tạo object bằng `Connection.createSQLXML()`, ghi nội dung qua `setString()`, `setCharacterStream()`, `setBinaryStream()` hoặc `setResult()`, gán vào `PreparedStatement.setSQLXML()`, rồi lấy lại qua `ResultSet.getSQLXML()`. API này có từ JDBC 4.0/Java 6 và **vẫn áp dụng trong Java 17+ lẫn JDK hiện hành**.

Nhưng một object `SQLXML` vừa được tạo **không đồng nghĩa đã chứa một XML document hoàn chỉnh**. Ba tình huống dễ gây lỗi cần được kiểm thử riêng:

1. **XML không hợp lệ:** ví dụ `<root><item></root>`, nhiều phần tử gốc, chuỗi rỗng, ký tự không hợp lệ theo XML hoặc XML chứa cấu trúc không được phép. Lỗi có thể xuất hiện lúc `setString()`/`setResult()`, lúc `PreparedStatement.setSQLXML()`, hoặc khi `execute()`/`executeUpdate()` giao giá trị cho DBMS.
2. **SQL NULL:** biểu thị **không có giá trị XML** ở cột, **khác** chuỗi XML rỗng `""`, object `SQLXML` chưa khởi tạo và chuỗi ký tự Java `"null"`. Thường bind bằng `setNull(index, Types.SQLXML)`; đọc lại bằng `getSQLXML(...) == null` và `ResultSet.wasNull()` ngay sau getter.
3. **Dữ liệu chưa ghi hoàn tất:** một `SQLXML` vừa được `createSQLXML()` nhưng chưa được gán XML, một `Writer`/`OutputStream` mở qua `setCharacterStream()`/`setBinaryStream()` chưa đóng, hoặc `Result` chưa hoàn tất. Theo hợp đồng JDBC, **phải hoàn tất và đóng các stream ghi trước khi truyền giá trị để thực thi SQL**. Không cố gán/chạy INSERT khi tài liệu đang viết dở.

**Tính đúng đắn không phụ thuộc vào một exception message cố định:** SQLXML có thể được hỗ trợ khác nhau giữa DBMS/driver. Một driver có thể kiểm tra cú pháp ngay, driver khác trì hoãn tới khi execute hoặc database validate. Vì vậy, thử nghiệm phải quan sát **giai đoạn lỗi, SQLState, vendor error code, dữ liệu cuối cùng**, và **rollback** để không lưu tài liệu lỗi.

Bài này tập trung đúng chủ đề **SQLXML**, gồm trạng thái object, lỗi XML, SQL NULL, stream chưa đóng, security/XXE, cách kiểm thử độc lập bằng Java 17+ và phép thử tích hợp với DBMS thật. Chỉ dùng kiến thức JDBC/JAXP còn được hỗ trợ hiện nay, tránh các giả định lỗi thời.

## 1. Mục tiêu bài học

Kết thúc bài, bạn sẽ:

- Phân biệt `SQLXML` **chưa khởi tạo**, **đã được ghi**, **đang viết qua stream**, **đọc được** và **đã giải phóng**.
- Nhận biết XML *not well-formed* (không đúng cú pháp) khác XML *well-formed but invalid against an XSD/DTD* (không đúng một schema cụ thể).
- Kiểm tra các nhóm input: XML hợp lệ, thẻ thiếu/không khớp, nhiều root, chuỗi rỗng, ký tự không hợp lệ, DOCTYPE, Java null và SQL NULL.
- Viết test để phát hiện rủi ro **chưa đóng `Writer`/`OutputStream`** trước `setSQLXML` hoặc `executeUpdate`.
- Bind/read SQL NULL đúng bằng `Types.SQLXML`, `ResultSet.getSQLXML` và `wasNull`.
- Hiểu ngoại lệ `SQLException` có thể phát sinh **nhiều thời điểm**, không chỉ khi gọi `execute()`.
- Quản lý `SQLXML.free()` đúng trong mã Java 17+, và biết thay đổi API mới từ **Java 26**.
- Cấu hình JAXP parser chống XXE/DOCTYPE khi xử lý XML từ nguồn không tin cậy.
- Xây test tích hợp theo **DBMS/driver/schema cụ thể**, không coi test JDK-only như bằng chứng DBMS PASS.
- Giảm resource leaks bằng `try-with-resources` cho `Connection`, `Statement`, `ResultSet` và stream; gọi `free()` cho `SQLXML` khi xong.

## 2. Đối tượng SQLXML và cách ghi/đọc

| API | Vai trò | Điều cần kiểm tra |
| --- | --- | --- |
| `Connection.createSQLXML()` | Tạo object để **ghi** một XML value. | Object ban đầu rỗng/chưa được khởi tạo; chưa phải SQL NULL. |
| `SQLXML.setString(String)` | Ghi một XML representation từ String. | Dữ liệu cần là XML hợp lệ; không mặc nhiên dùng null để bind SQL NULL. |
| `SQLXML.setCharacterStream()` | Nhận `Writer` cho nội dung XML dạng ký tự. | Đóng Writer **trước** khi bind/execute; Reader/Writer khác nhau. |
| `SQLXML.setBinaryStream()` | Nhận `OutputStream` cho dữ liệu XML theo XML encoding rules. | Byte encoding, BOM/declaration và đóng stream trước execute. |
| `SQLXML.setResult(Class)` | Nhận `Result` để ghi qua DOM, SAX, StAX hoặc Stream. | Hoàn tất parser/result; đóng stream/writer nếu applicable. |
| `PreparedStatement.setSQLXML(int, SQLXML)` | Bind một SQLXML object vào parameter. | Driver có thể phát hiện state chưa hoàn tất ngay tại bind. |
| `PreparedStatement.setNull(int, Types.SQLXML)` | Bind **SQL NULL** với type XML. | Cột phải nullable; driver có thể không hỗ trợ SQLXML. |
| `ResultSet.getSQLXML(int/String)` | Lấy XML value từ row. | Với SQL NULL thường trả `null`, kiểm tra `wasNull`. |
| `SQLXML.getString()` / `getCharacterStream()` | Đọc một XML value. | Readable state/lifetime, chỉ chọn **một cách đọc** cho object. |
| `SQLXML.getSource(Class)` | Đọc dưới dạng `Source` (DOM/SAX/StAX/Stream). | Parse/XSLT security, driver support, resource scope. |
| `SQLXML.free()` | Giải phóng tài nguyên của SQLXML. | Object không được dùng tiếp sau free. |

SQLXML có thể là **logical pointer** tới dữ liệu DB, không nhất thiết có toàn bộ văn bản XML trong bộ nhớ Java ngay khi gọi `getSQLXML`. Tài liệu Java nêu object hợp lệ trong phạm vi transaction mà nó được tạo, cho tới khi được giải phóng; driver có thể áp thêm giới hạn phù hợp. Đừng giữ reference `SQLXML` qua commit, close connection hoặc giữa các request mà không có hợp đồng của driver.

### 2.1. Luồng INSERT đúng cơ bản

```java
// Mảnh code tích hợp; connection là một JDBC Connection thật.
// Trong Java 17+, SQLXML chưa phải AutoCloseable; dùng free().
SQLXML xml = connection.createSQLXML();
try {
    xml.setString("<root><name>Hà Nội</name></root>");
    try (PreparedStatement ps = connection.prepareStatement(
            "INSERT INTO xml_values (id, payload) VALUES (?, ?)")) {
        ps.setLong(1, 1L);
        ps.setSQLXML(2, xml);
        ps.executeUpdate();
    }
} finally {
    xml.free();
}
```

Đây **không phải chương trình độc lập**: cần bảng `xml_values` với cột XML được DBMS/driver hỗ trợ. Chuỗi ở ví dụ là một XML document hợp lệ; object được giữ sống tới sau `executeUpdate()` rồi mới giải phóng.

### 2.2. Luồng đọc cơ bản

```java
// Mảnh code trong ResultSet đang mở và đứng tại một row hợp lệ.
SQLXML value = rs.getSQLXML("payload");
if (value == null) {
    boolean isNull = rs.wasNull(); // Gọi ngay sau getter.
    // Giá trị SQL NULL; không gọi value.getString().
} else {
    try {
        String xmlText = value.getString(); // Chọn một lần đọc.
        // Dùng parser bảo mật nếu cần kiểm tra/cấu trúc hóa XML.
    } finally {
        value.free();
    }
}
```

Nếu XML content lớn, `getString()` materialize thành String, có thể tốn bộ nhớ. `getCharacterStream()`/`getSource()` có thể phù hợp hơn, nhưng **không tự bảo đảm driver stream không buffer toàn bộ**. Đọc trong scope mà ResultSet/Connection/transaction còn hợp lệ.

## 3. Trạng thái SQLXML: writable và readable không phải mãi mãi

Java SE mô tả hai trạng thái khái niệm: **writable/not writable** và **readable/not readable**.

- Một SQLXML tạo qua `Connection.createSQLXML()` có thể ghi giá trị XML bằng **một trong các phương thức ghi**.
- Sau lần gọi `setString()`, `setCharacterStream()`, `setBinaryStream()` hoặc `setResult()`, object trở thành **not writable**. Không gọi thêm phương thức ghi trên cùng instance.
- Sau khi gọi `getString()`, `getCharacterStream()`, `getBinaryStream()` hoặc `getSource()`, object trở thành **not readable**. Một implementation có thể còn cấm chiều ghi.
- Khi `free()`/`close()` được gọi, object không còn readable/writable. Gọi các method khác tiếp sẽ dẫn tới `SQLException` theo contract.
- Đừng dùng “đọc một lần rồi đọc lại” như test khẳng định phải thành công; **hợp đồng chỉ cho phép một lần đọc**. Nếu cần dùng dữ liệu ở nhiều nơi, đọc vào một representation do ứng dụng quản lý với giới hạn bộ nhớ thích hợp.

### 3.1. Sơ đồ state đơn giản

```text
connection.createSQLXML()
        |
        v
   writable object
        |
        +-- setString(...) -------------------+
        |                                     |
        +-- setCharacterStream() -> Writer    |
        |                          write...   |
        |                          close()    |
        |                                     |
        +-- setBinaryStream() -> OutputStream |
        |                          write...   |
        |                          close()    |
        |                                     |
        +-- setResult(...) -> Result completed+
                                              |
                                              v
                             SQLXML value ready for binding
                                              |
                                              v
                             PreparedStatement.setSQLXML(...)
                                              |
                                              v
                                      executeUpdate()
                                              |
                                              v
                                         SQLXML.free()

ResultSet.getSQLXML() -> readable SQLXML -> one getter -> SQLXML.free()
```

Đây là **hình tư duy**. State transitions chính xác và thời điểm validation còn do driver quyết định trong giới hạn hợp đồng API. Đặc biệt, một SQLXML **đã đóng Writer** vẫn có thể chứa XML *không well-formed*; đóng stream chỉ hoàn tất thao tác ghi, **không tạo thêm các thẻ XML thiếu**.

### 3.2. Thay đổi API cần biết: Java 26

**Java 26 bổ sung `SQLXML extends AutoCloseable` và `SQLXML.close()`**, trong đó default `close()` gọi `free()`. Đây là API hiện hành, **không phải API có sẵn ở Java 17**. Vì bài có mã chạy với `javac --release 17`, mọi ví dụ runnable đều **gọi `free()` trong `finally`**, tránh viết `try (SQLXML xml = ...)` (cách này không biên dịch với `--release 17`).

Nếu codebase của bạn **chỉ target Java 26+**, có thể sử dụng try-with-resources với `SQLXML` theo API mới. Dù vậy vẫn phải hoàn tất/đóng **Writer/OutputStream** trước khi bind/execute và không dùng object sau khi đóng.

## 4. Phân biệt năm trường hợp dễ nhầm

| Đầu vào/trạng thái | Ý nghĩa | Kết quả hợp lý trong phép thử |
| --- | --- | --- |
| `"<root/>"` | XML document **well-formed**, không có nội dung bên trong. | Hợp lệ ở mức cú pháp; DBMS/schema vẫn có thể từ chối theo ràng buộc riêng. |
| `""` (empty string) | Không có phần tử gốc; **không phải XML document well-formed**. | Parse lỗi; không dùng thay SQL NULL. |
| `null` trong Java | Không có Java object/String. | Không đồng nhất SQL NULL nếu không bind đúng API. |
| `PreparedStatement.setNull(2, Types.SQLXML)` | Parameter có giá trị **SQL NULL**. | Thành công nếu column nullable/driver hỗ trợ, readback qua `getSQLXML()==null` và `wasNull()==true`. |
| `connection.createSQLXML()` rồi bind ngay | Object `SQLXML` chưa được ghi/khởi tạo. | Không coi là SQL NULL; cần test driver xử lý invalid/incomplete. |
| `setCharacterStream()` trả Writer chưa đóng | Một phép ghi **chưa hoàn tất** dù content trông có vẻ XML đúng. | Không bind/execute ở trạng thái này; JDBC yêu cầu close stream trước khi execute. |
| Writer đã đóng nhưng chỉ ghi `"<root><x>"` | Stream hoàn tất nhưng document **không well-formed**. | Có thể lỗi ở setter/bind/execute; DB XML column phải được kiểm thử riêng. |

**Đừng dùng `xml.setString(null)` để gán SQL NULL.** Một số driver từ chối, một số có behavior riêng. Đặt null ở **PreparedStatement parameter**, ví dụ `setNull(2, Types.SQLXML)`, rồi kiểm chứng với cột cho phép NULL. `ps.setSQLXML(2, null)` có thể được một số drivers hỗ trợ nhưng cách explicit `setNull` rõ hơn khi xây test portability.

Một cột SQL XML có ràng buộc `NOT NULL` sẽ từ chối `setNull` khi execute. Đó là lỗi schema constraint, **không phải chứng minh `SQLXML` không hỗ trợ SQL NULL**.

## 5. Tình huống XML không hợp lệ cần test

**Well-formedness** của XML nghĩa là cấu trúc tài liệu XML đúng cú pháp: root duy nhất, cặp thẻ khớp, ký tự escape hợp lệ, attribute quoting đúng và những ký tự XML được phép. **Schema validity** nghĩa là document phải khớp một XSD/DTD được xác định; một XML well-formed có thể không hợp lệ theo schema.

| Fixture | Loại | Ý nghĩa |
| --- | --- | --- |
| `<root><name>Hà Nội 😀</name></root>` | XML well-formed. | Baseline Unicode và cấu trúc. |
| `<root><x></root>` | Thẻ đóng sai. | Parser hoặc DB nên phát hiện lỗi cú pháp. |
| `<root><x>` | Thiếu phần kết. | Dữ liệu bị cắt giữa chừng, stream đã/ chưa đóng. |
| `<one/><two/>` | Hai root elements. | Không phải một XML document well-formed. |
| `""` | Chuỗi rỗng. | Không có root; không phải SQL NULL. |
| `"   "` | Chỉ whitespace. | Không có root. |
| `<root>a & b</root>` | Dấu `&` chưa escape. | Cần `&amp;` cho nội dung văn bản XML. |
| `<root>\u0000</root>` | NUL/U+0000. | Không phải ký tự hợp lệ trong XML 1.0. |
| `<root><x attr=no/></root>` | Attribute chưa quoted. | Cú pháp XML không hợp lệ. |
| `<!DOCTYPE root ...>` | Có DOCTYPE. | Có thể hợp lệ về XML nhưng **bị chặn theo security policy**. |
| `<root/>` | Root rỗng. | XML document hợp lệ, khác chuỗi rỗng. |
| `<root><x>ok</x></root>` | Document hoàn chỉnh. | Test viết đủ nội dung rồi đóng stream. |

**Không quy mọi “DOCTYPE bị chặn” thành lỗi XML well-formedness.** Một document có DOCTYPE có thể well-formed, nhưng ứng dụng chủ động **từ chối** nó để ngăn external entity resolution/XXE. Bài test nên tách *syntax validation* khỏi *security policy rejection*.

### 5.1. Đường đi lỗi: setter hay execute?

Tài liệu `SQLXML` của Oracle ghi **XML không hợp lệ/chưa hoàn chỉnh có thể gây `SQLException` khi set**, hoặc **lỗi chỉ phát sinh khi execute**. Một số driver parse XML thành cấu trúc nội bộ trước khi gửi; số khác chuyển dữ liệu tới server và dựa vào XML type/constraint của DBMS.

Vì thế test không nên viết:

```java
// Cách kiểm thử quá cứng và không portable:
assertThrows(SQLException.class, () -> xml.setString("<root>"));
```

Đây là pseudocode test framework, **không phải đoạn Java độc lập**. Không được mặc định lỗi luôn xuất hiện tại `setString`. Thiết kế test cần bao trùm `setString`, `setSQLXML` và `executeUpdate`, đồng thời rollback nếu có nguy cơ dữ liệu đã được ghi.

Không coi một `SQLException` bất kỳ là “XML validation PASS”; lỗi có thể do thiếu bảng, quyền, network, driver feature unsupported, cột sai type hoặc bảng `NOT NULL`. Dùng positive control trên cùng DB/driver/schema trước khi phân loại lỗi của negative test.

## 6. Dữ liệu chưa ghi hoàn tất: test Writer/OutputStream/Result

Đối với `SQLXML` được tạo mới, ta có thể lấy Writer:

```java
// Mảnh code được đặt trong method có Connection/PreparedStatement hợp lệ:
SQLXML value = connection.createSQLXML();
try {
    try (Writer writer = value.setCharacterStream()) {
        writer.write("<root><item>đã xong</item></root>");
    }
    preparedStatement.setSQLXML(1, value);
    preparedStatement.executeUpdate();
} finally {
    value.free();
}
```

**Thứ tự quan trọng:** hoàn tất `write()` → **`writer.close()`** → `setSQLXML()` → `executeUpdate()` → `value.free()`. `Writer.close()` không thay `SQLXML.free()`: method đầu hoàn tất đầu ra ký tự; method sau giải phóng SQLXML resource.

### 6.1. Negative test: Writer đang mở

```java
// Mảnh code cố ý sai, chỉ chạy trong test cô lập có rollback.
SQLXML value = connection.createSQLXML();
Writer writer = value.setCharacterStream();
writer.write("<root/>"); // Well-formed TEXT, nhưng Writer chưa close.
try {
    preparedStatement.setSQLXML(1, value);
    preparedStatement.executeUpdate();
    // Nếu không có lỗi, ghi lại là ACCEPTED_REVIEW; không khẳng định PASS.
} finally {
    try {
        writer.close();
    } finally {
        value.free();
    }
}
```

Dù XML string `"<root/>"` là well-formed, **Writer còn mở** khi bind/execute. Theo Java SE, các streams **phải được đóng trước execute**, nếu không một `SQLException` sẽ phát sinh. `PreparedStatement.setSQLXML` cũng có thể ném lỗi **ngay tại bind** nếu Writer/OutputStream/Result chưa hoàn tất.

**Lưu ý kỹ thuật:** nên bắt SQLException của **cả giai đoạn bind và execute** rồi ghi SQLState/vendor code. Không bắt `IOException` từ `writer.close()` rồi xóa mất lỗi SQL chính. Phần chương trình tích hợp ở dưới có try/finally để giải phóng và rollback sau test âm tính.

### 6.2. Negative test khác: Writer đã đóng nhưng thẻ XML thiếu

```java
SQLXML value = connection.createSQLXML();
try {
    try (Writer writer = value.setCharacterStream()) {
        writer.write("<root><item>");
    }
    // Writer ĐÃ đóng, nhưng nội dung XML vẫn KHÔNG hợp lệ.
    preparedStatement.setSQLXML(1, value);
    preparedStatement.executeUpdate();
} finally {
    value.free();
}
```

Hai trường hợp khác nhau:

- **Chưa đóng Writer:** vi phạm lifecycle của SQLXML output.
- **Đã đóng Writer nhưng XML chưa có thẻ kết:** vi phạm cú pháp XML.

Cần test **từng nguyên nhân** để biết driver có báo lỗi đúng nơi không; đừng gộp thành một kết luận “stream hỏng”.

### 6.3. `setBinaryStream()` và encoding

`setBinaryStream()` nhận `OutputStream`, ghi XML bằng bytes. Nội dung XML sẽ được diễn giải theo các quy tắc encoding của XML 1.0; phải xem **BOM**, XML declaration và byte encoding thực tế. Không mặc định ghi UTF-8 bytes cùng declaration `encoding="UTF-16"` mà vẫn đúng.

`setCharacterStream()` nhận **Unicode characters** từ Java Writer; XML declaration encoding trong chuỗi không làm Java String tự đổi thành byte encoding tương ứng. Khi test encoding, ghi rõ API nào được dùng.

### 6.4. `setResult()` có thể chưa hoàn thành

`setResult(DOMResult.class)`, `setResult(SAXResult.class)`, `setResult(StAXResult.class)` hoặc `setResult(StreamResult.class)` dùng các mô hình viết XML khác nhau.

- `DOMResult`: phải cung cấp Node/document hoàn chỉnh trước khi bind.
- `SAXResult`: phải phát các sự kiện hợp lệ với `startDocument`/`endDocument` và stack tags tương ứng.
- `StAXResult`: writer phải tạo complete document và hoàn tất flush/close theo contract.
- `StreamResult`: nếu có `Writer`/`OutputStream` do driver cấp, phải hoàn tất và đóng theo yêu cầu.
- Không tự gọi thêm `setString` sau khi đã `setResult` trên cùng `SQLXML`.

Đừng đoán rằng gọi `setResult` xong là nội dung tự động hoàn chỉnh; nó chỉ **chọn cách ghi**. Để kiểm thử, tạo một document có root đúng và một biến thể cố ý thiếu events/closing; quan sát đúng giai đoạn lỗi.

## 7. Kiểm tra XML độc lập với DBMS bằng JAXP

Trước khi dùng JDBC, có thể tạo bộ fixtures Java 17+ để kiểm chứng *XML syntax* và *security policy*. Đây là **test JDK-only**: nó không giả lập `SQLXML` của driver và **không kết luận database đã xử lý đúng dữ liệu**.

Một parser tiếp nhận XML không tin cậy cần chống **XXE (XML External Entity)**, external DTD/schema fetching và entity expansion bombs. Tài liệu JAXP Security Guide của Oracle khuyên **bật `FEATURE_SECURE_PROCESSING` rõ ràng** và khóa các *external access properties*.

Trong ví dụ bên dưới:

- `DocumentBuilderFactory.setNamespaceAware(true)`.
- `FEATURE_SECURE_PROCESSING = true`.
- `"http://apache.org/xml/features/disallow-doctype-decl" = true` để **chặn hẳn DOCTYPE**. Đây là feature của parser provider đang dùng trong JDK, **không portable với mọi JAXP implementation**; nếu không hỗ trợ, factory ném exception và chương trình **fail closed**, không tắt bảo vệ để test pass.
- `XMLConstants.ACCESS_EXTERNAL_DTD` và `ACCESS_EXTERNAL_SCHEMA` đặt chuỗi rỗng, chặn external protocols.
- `DefaultHandler` tùy biến để không in các thông báo lỗi cú pháp dựa trên stdout/stderr không ổn định giữa parser implementations.

### 7.1. File `XmlBoundaryChecks.java`

```java
import java.io.StringReader;
import java.io.StringWriter;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import org.xml.sax.InputSource;
import org.xml.sax.SAXException;
import org.xml.sax.SAXParseException;
import org.xml.sax.helpers.DefaultHandler;

public final class XmlBoundaryChecks {
    private static DocumentBuilder secureBuilder() throws Exception {
        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
        factory.setNamespaceAware(true);
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        DocumentBuilder builder = factory.newDocumentBuilder();
        builder.setErrorHandler(new DefaultHandler() {
            @Override
            public void error(SAXParseException e) throws SAXException { throw e; }
            @Override
            public void fatalError(SAXParseException e) throws SAXException { throw e; }
        });
        return builder;
    }

    private static boolean isWellFormed(String xml) throws Exception {
        if (xml == null) return false;
        try {
            secureBuilder().parse(new InputSource(new StringReader(xml)));
            return true;
        } catch (SAXException expected) {
            return false;
        }
    }

    private static void check(String name, boolean condition) {
        if (!condition) throw new AssertionError(name);
        System.out.println(name + "=PASS");
    }

    public static void main(String[] args) throws Exception {
        check("validUnicodeXml",
                isWellFormed("<root><name>Tiếng Việt 😀</name></root>"));
        check("missingClosingTag",
                !isWellFormed("<root><name></root>"));
        check("emptyStringNotXml",
                !isWellFormed(""));
        check("multipleRoots",
                !isWellFormed("<one/><two/>"));
        check("illegalXmlCharacter",
                !isWellFormed("<root>\u0000</root>"));
        check("doctypeBlocked",
                !isWellFormed("<!DOCTYPE root [<!ENTITY e SYSTEM 'file:///tmp/no.xml'>]>"
                        + "<root>&e;</root>"));
        check("javaNullNotXml",
                !isWellFormed(null));

        StringWriter pending = new StringWriter();
        pending.write("<root><item>");
        check("unfinishedDocument",
                !isWellFormed(pending.toString()));
        pending.write("ok</item></root>");
        check("completedDocument",
                isWellFormed(pending.toString()));
        System.out.println("checks=9");
    }
}
```

### 7.2. Biên dịch và chạy

```bash
javac --release 17 -encoding UTF-8 XmlBoundaryChecks.java
java XmlBoundaryChecks
```

**Stdout đã kiểm chứng với JDK 24:**

```text
validUnicodeXml=PASS
missingClosingTag=PASS
emptyStringNotXml=PASS
multipleRoots=PASS
illegalXmlCharacter=PASS
doctypeBlocked=PASS
javaNullNotXml=PASS
unfinishedDocument=PASS
completedDocument=PASS
checks=9
```

Có **9 assertions PASS và 10 dòng stdout** (dòng cuối là tổng). Ví dụ đã được biên dịch với `javac --release 17` và chạy thành công trên OpenJDK 24.

### 7.3. Kết quả này chứng minh điều gì?

- `validUnicodeXml`: một document có tiếng Việt và emoji là XML well-formed.
- `missingClosingTag`: parser từ chối thẻ đóng không khớp.
- `emptyStringNotXml`: `""` không phải XML document hoàn chỉnh.
- `multipleRoots`: không có đúng một root.
- `illegalXmlCharacter`: U+0000 không hợp lệ trong XML 1.0.
- `doctypeBlocked`: parser chặn DOCTYPE **theo chính sách an ninh**, không kết luận mọi DOCTYPE trên thế giới đều sai cú pháp.
- `javaNullNotXml`: Java null bị loại khỏi parser; SQL NULL phải được kiểm tra riêng ở tầng JDBC.
- `unfinishedDocument`: một `StringWriter` đang chứa văn bản thiếu thẻ kết chưa là document hợp lệ.
- `completedDocument`: sau khi bổ sung thẻ, nội dung trở thành well-formed.

**Điều chưa chứng minh:** Object `StringWriter` của JDK **không phải** `Writer` do `SQLXML.setCharacterStream()` cấp; `StringWriter.close()` không phản ánh contract JDBC. Chỉ integration test trên DBMS/driver mới chứng minh lúc nào `setSQLXML/execute` phát hiện writer chưa đóng. Cũng chưa có DBMS nào được đánh giá PASS bởi chương trình JDK-only này.

## 8. Tích hợp JDBC thật: kiểm thử bốn nhánh riêng

Chương trình tiếp theo dùng một DBMS/driver thật và bảng test XML đã chuẩn bị trước:

1. **Positive control:** ghi một XML hợp lệ rồi SELECT lại thành `SQLXML`.
2. **SQL NULL:** bind `setNull(Types.SQLXML)`, đọc lại `getSQLXML()==null` và `wasNull()==true`.
3. **Malformed XML:** gọi `setString("<root><item></root>")` rồi bind/execute, ghi nhận giai đoạn bị `SQLException`. Nếu hệ chấp nhận, đánh dấu **ACCEPTED_REVIEW** chứ không gán PASS.
4. **Writer chưa đóng:** ghi `"<root/>"` (cú pháp hợp lệ) vào `SQLXML.setCharacterStream()` nhưng cố tình **không đóng Writer** trước bind/execute, quan sát `SQLException` hoặc trường hợp phải điều tra.

Chúng ta **không tự tạo/drop bảng** trong chương trình vì DDL có thể auto-commit trên một số DBMS. Mỗi case kết thúc bằng `rollback()` riêng, tránh case lỗi khiến transaction bị abort rồi ảnh hưởng các case sau.

### 8.1. Chuẩn bị database cô lập

Schema **khái niệm** của bảng test:

```sql
-- ĐÂY LÀ DDL minh họa, không bảo đảm mọi DBMS dùng cú pháp y hệt.
CREATE TABLE jdbc_sqlxml_probe (
    id BIGINT PRIMARY KEY,
    payload XML NULL
);
```

DBMS phải hỗ trợ **SQL XML type** cùng JDBC `SQLXML`; tên SQL type, nullability, constraints và implementation khác nhau giữa vendors. Nếu DB không có native XML type hoặc JDBC driver không hỗ trợ `createSQLXML`/`setSQLXML`, ghi kết quả **UNSUPPORTED**, không chuyển bài test sang cột TEXT rồi tuyên bố XML type PASS.

Điều kiện trước khi chạy:

- JDBC driver JAR đúng version ở runtime classpath/module path, tự đăng ký service đúng.
- Database test riêng, quyền INSERT/SELECT, bảng `jdbc_sqlxml_probe` đã tồn tại và cho phép SQL NULL.
- Bảng/engine hỗ trợ transactions và rollback cho dữ liệu INSERT.
- `JDBC_URL` do bạn cung cấp, `JDBC_USER`/`JDBC_PASSWORD` nếu DB yêu cầu, `JDBC_TEST_TABLE` tùy chọn.
- Không dùng tài khoản production hoặc dữ liệu khách hàng thực trong test.
- Kết quả SQLState/error codes sẽ khác DBMS và không có stdout “chuẩn” cố định.

### 8.2. File `JdbcSqlXmlProbe.java`

```java
import java.io.Writer;
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;
import java.sql.SQLXML;
import java.sql.Types;
import java.util.Properties;
import java.util.concurrent.ThreadLocalRandom;

public final class JdbcSqlXmlProbe {
    private static final String VALID =
            "<root><name>Tiếng Việt 😀 &amp; SQLXML</name></root>";
    private static final String MALFORMED = "<root><item></root>";

    private static String required(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank())
            throw new IllegalArgumentException("Missing environment variable: " + key);
        return value;
    }

    private static void insert(Connection connection, String table, long id,
                               SQLXML xml) throws SQLException {
        try (PreparedStatement ps = connection.prepareStatement(
                "INSERT INTO " + table + " (id, payload) VALUES (?, ?)")) {
            ps.setLong(1, id);
            ps.setSQLXML(2, xml);
            if (ps.executeUpdate() != 1)
                throw new SQLException("Expected exactly one row inserted");
        }
    }

    private static void testValid(Connection connection, String table, long id)
            throws Exception {
        SQLXML xml = connection.createSQLXML();
        try {
            xml.setString(VALID);
            insert(connection, table, id, xml);
            try (PreparedStatement ps = connection.prepareStatement(
                    "SELECT payload FROM " + table + " WHERE id = ?")) {
                ps.setLong(1, id);
                try (ResultSet rs = ps.executeQuery()) {
                    if (!rs.next()) throw new AssertionError("Missing valid row");
                    SQLXML fromDb = rs.getSQLXML(1);
                    if (fromDb == null || rs.wasNull())
                        throw new AssertionError("Valid XML returned as SQL NULL");
                    try {
                        String got = fromDb.getString();
                        if (got == null || !got.contains("Tiếng Việt"))
                            throw new AssertionError("Text content missing");
                        System.out.println("valid=READABLE");
                    } finally {
                        fromDb.free();
                    }
                    if (rs.next()) throw new AssertionError("Duplicate row");
                }
            }
        } finally {
            try { connection.rollback(); }
            finally { xml.free(); }
        }
    }

    private static void testSqlNull(Connection connection, String table, long id)
            throws Exception {
        try {
            try (PreparedStatement ps = connection.prepareStatement(
                    "INSERT INTO " + table + " (id, payload) VALUES (?, ?)")) {
                ps.setLong(1, id);
                ps.setNull(2, Types.SQLXML);
                if (ps.executeUpdate() != 1)
                    throw new SQLException("Expected exactly one NULL row");
            }
            try (PreparedStatement ps = connection.prepareStatement(
                    "SELECT payload FROM " + table + " WHERE id = ?")) {
                ps.setLong(1, id);
                try (ResultSet rs = ps.executeQuery()) {
                    if (!rs.next()) throw new AssertionError("Missing NULL row");
                    SQLXML fromDb = rs.getSQLXML(1);
                    boolean nullFlag = rs.wasNull();
                    if (fromDb != null) fromDb.free();
                    if (fromDb != null || !nullFlag)
                        throw new AssertionError("SQL NULL mapping mismatch");
                    System.out.println("sqlNull=PASS");
                }
            }
        } finally { connection.rollback(); }
    }

    private static void testMalformed(Connection connection, String table, long id)
            throws Exception {
        SQLXML xml = connection.createSQLXML();
        try {
            try {
                xml.setString(MALFORMED);
                insert(connection, table, id, xml);
                System.out.println("malformed=ACCEPTED_REVIEW_DB_XML_TYPE");
            } catch (SQLFeatureNotSupportedException e) {
                System.out.println("malformed=UNSUPPORTED");
            } catch (SQLException e) {
                System.out.println("malformed=REJECTED_SQLSTATE_" + e.getSQLState());
            }
        } finally {
            try { connection.rollback(); }
            finally { xml.free(); }
        }
    }

    private static void testWriterStillOpen(Connection connection, String table, long id)
            throws Exception {
        SQLXML xml = connection.createSQLXML();
        Writer writer = null;
        try {
            writer = xml.setCharacterStream();
            writer.write("<root/>");
            // Intentionally do NOT close writer before setSQLXML/execute.
            try {
                insert(connection, table, id, xml);
                System.out.println("writerOpen=ACCEPTED_REVIEW_DRIVER");
            } catch (SQLFeatureNotSupportedException e) {
                System.out.println("writerOpen=UNSUPPORTED");
            } catch (SQLException e) {
                System.out.println("writerOpen=REJECTED_SQLSTATE_" + e.getSQLState());
            }
        } finally {
            try { connection.rollback(); }
            finally {
                try { if (writer != null) writer.close(); }
                finally { xml.free(); }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        String url = required("JDBC_URL");
        String table = System.getenv().getOrDefault(
                "JDBC_TEST_TABLE", "jdbc_sqlxml_probe");
        if (!table.matches("[A-Za-z_][A-Za-z0-9_]*"))
            throw new IllegalArgumentException("Invalid table identifier");
        Properties props = new Properties();
        String user = System.getenv("JDBC_USER");
        String password = System.getenv("JDBC_PASSWORD");
        if (user != null) props.setProperty("user", user);
        if (password != null) props.setProperty("password", password);
        long baseId = ThreadLocalRandom.current().nextLong(1, Long.MAX_VALUE - 4);

        try (Connection connection = DriverManager.getConnection(url, props)) {
            DatabaseMetaData meta = connection.getMetaData();
            System.out.println("db=" + meta.getDatabaseProductName());
            System.out.println("driver=" + meta.getDriverName());
            if (!meta.supportsTransactions())
                throw new SQLException("This probe needs transactional table");
            boolean previous = connection.getAutoCommit();
            connection.setAutoCommit(false);
            try {
                testValid(connection, table, baseId);
                testSqlNull(connection, table, baseId + 1);
                testMalformed(connection, table, baseId + 2);
                testWriterStillOpen(connection, table, baseId + 3);
            } finally {
                try { connection.rollback(); }
                finally { connection.setAutoCommit(previous); }
            }
        }
    }
}
```

### 8.3. Giải thích cách chạy và diễn giải

`JdbcSqlXmlProbe` **không phải chương trình có thể chạy thành công nếu chưa chuẩn bị DBMS/driver/schema**. Nó chủ ý không nhúng credentials, connection URL hoặc tên driver vendor giả định. `insert` dùng `PreparedStatement` cho dữ liệu và kiểm tra update count.

- `testValid` tạo XML, `setString`, bind/execute rồi `getSQLXML`; chỉ đọc `getString` **một lần**, kiểm tra text cơ bản và `free`. XML DBMS có thể reserialize whitespace/attribute order, vì vậy đoạn này không bắt buộc byte-for-byte equality của XML serialization. Nếu nghiệp vụ cần bảo đảm cấu trúc, bổ sung secure DOM/XPath assertions.
- `testSqlNull` tạo row với `setNull(Types.SQLXML)`, dùng `getSQLXML` + `wasNull` ngay sau getter. Nếu DBMS không cho nullable hoặc driver không hỗ trợ type, đây là **unsupported/schema mismatch**, không phải lỗi “XML không hợp lệ”.
- `testMalformed` bắt các SQLException từ `setString` **hoặc** `setSQLXML`/**executeUpdate`. Nếu driver không hỗ trợ method, báo UNSUPPORTED. Nếu chấp nhận, báo `ACCEPTED_REVIEW_DB_XML_TYPE` để điều tra cột DB thực sự có type XML hay text, chứ không gọi PASS.
- `testWriterStillOpen` cố tình ghi nội dung `"<root/>"` đúng cú pháp nhưng **không đóng Writer trước bind/execute**. Nếu bị từ chối, ghi SQLState; nếu driver nhận, báo `ACCEPTED_REVIEW_DRIVER` để đánh giá việc tuân thủ JDBC.
- Mỗi case có `connection.rollback()` riêng trong `finally`. Nếu một lần execute làm transaction bị abort (ví dụ PostgreSQL), việc rollback trước case tiếp theo là quan trọng.
- `SQLXML.free()` được gọi sau các JDBC operations liên quan, vì object có thể cần sống tới execute.
- Code không giả định ngôn ngữ lỗi của driver; `SQLState` có thể là `null` và vendor code cần bổ sung vào báo cáo QA thực tế.

**Không hiểu nhầm:** một `SQLException` từ `testMalformed` không chứng minh chắc chắn **chính cú pháp XML** đã bị từ chối. Positive control phải chạy thành công; kiểm tra mã lỗi, server logs, column metadata và validation policy. Trong một số drivers, `createSQLXML` hoặc `setCharacterStream` có thể ném `SQLFeatureNotSupportedException` ngay trước nhánh `catch` cụ thể; đây là tín hiệu feature **UNSUPPORTED**, không phải bằng chứng một XML test đã PASS.

### 8.4. Biên dịch

```bash
javac --release 17 -encoding UTF-8 JdbcSqlXmlProbe.java
```

Đã kiểm chứng biên dịch thành công với **JDK 24, `--release 17`**, không cần JDBC driver cho bước compile vì API `java.sql` nằm trong JDK.

### 8.5. Chạy với DBMS của bạn

Trên Linux/macOS, chỉ sau khi cấu hình biến môi trường thật cho **database sandbox**:

```bash
# Các biến JDBC_URL/JDBC_USER/JDBC_PASSWORD được cung cấp
# bởi environment hoặc secret manager, không hardcode trong README.
export JDBC_URL
export JDBC_USER
export JDBC_PASSWORD
export JDBC_TEST_TABLE=jdbc_sqlxml_probe

# driver.jar là JDBC driver thực đã được cài đúng.
java -cp "driver.jar:." JdbcSqlXmlProbe
```

Trên Windows PowerShell:

```powershell
# JDBC_URL, JDBC_USER, JDBC_PASSWORD được cấu hình trước.
$env:JDBC_TEST_TABLE = "jdbc_sqlxml_probe"
java -cp 'driver.jar;.' JdbcSqlXmlProbe
```

Hai lệnh `export JDBC_URL` ở Bash không tự đặt URL; nếu biến chưa được cung cấp, chương trình báo thiếu biến để bạn không vô tình kết nối tới một địa chỉ giả. Windows classpath phân tách bằng `;`, Linux/macOS bằng `:`.

**Không có stdout DBMS được “xác nhận” trong bài này.** Phần test XML độc lập ở mục 7 đã **chạy PASS**, còn chương trình `JdbcSqlXmlProbe` **mới được biên dịch** do không có DBMS/schema/driver và credentials trong phạm vi này. Kết quả `db=...`, `driver=...`, `valid=READABLE`, `sqlNull=PASS`, `malformed=...`, `writerOpen=...` chỉ có giá trị sau khi chạy thật, phải ghi lại DBMS/driver versions.

## 9. Ma trận kiểm thử cần ghi cho một DBMS thật

| Case | API khởi tạo/bind | Đầu vào | Mong đợi / Phân loại |
| --- | --- | --- | --- |
| XML hợp lệ | `createSQLXML → setString → setSQLXML` | `<root/>` | Có thể INSERT/SELECT thành công nếu DB hỗ trợ XML. |
| XML Unicode | `setString`, `getString`/`getSource` | Tiếng Việt, emoji, `&amp;` | Giữ cấu trúc/ký tự; XML serialization có thể thay đổi. |
| SQL NULL | `setNull(index, Types.SQLXML)` | NULL | Trả SQL NULL nếu cột nullable; `getSQLXML()==null` và `wasNull`. |
| Java `null` truyền cho `setString` | `SQLXML.setString(null)` | null | Không dùng thay SQL NULL; ghi vendor behavior nếu khảo sát. |
| Empty XML text | `setString("")` | Rỗng | Không phải document hợp lệ; không nhầm NULL. |
| Missing end tag | `setString` | `<root><x>` | Error tại setter/bind/execute hoặc thành công bất thường cần review. |
| Mismatched tags | `setString` | `<root><x></root>` | Error ở giai đoạn driver/DB validate. |
| Multiple roots | `setString` | `<a/><b/>` | Phát hiện document không well-formed. |
| Illegal U+0000 | `setString` | XML chứa NUL | Reject XML 1.0 illegal character. |
| Writer chưa đóng | `setCharacterStream` → `setSQLXML` | `<root/>`, Writer OPEN | Phải đóng Writer trước execute; theo dõi SQLException. |
| Writer đã đóng nhưng thiếu tag | `setCharacterStream` → close → bind | `<root><x>` | Lỗi cú pháp, không phải lỗi Writer lifecycle. |
| SQLXML chưa được set | `createSQLXML` → bind ngay | Chưa có document | Không nhầm với SQL NULL; cần kiểm tra driver từ chối. |
| Double write | `setString` hai lần | Hai XML strings | SQLXML không còn writable sau lần ghi đầu. |
| Double read | `getString` rồi `getSource` | Readable SQLXML | Không portable; contract chỉ một lần đọc. |
| Read after free | `free` → `getString` | Object freed | SQLException cho use-after-free. |
| Driver không hỗ trợ SQLXML | `createSQLXML`/`setSQLXML` | Bất kỳ | Ghi **UNSUPPORTED**, không gán FAIL về XML data. |

Đối với các case có thể thành công bất thường, test phải ghi **ACCEPTED_REVIEW** và giữ toàn bộ SQLState/vendor details, kiểm tra SQL column có native XML type hay đang lưu plain TEXT. Không giả định mọi DBMS đều có XML data type đúng như SQL standard.

### 9.1. Metadata và driver capabilities

`DatabaseMetaData.getTypeInfo()` có thể liệt kê type codes, nhưng **không phải bảo đảm mọi SQLXML API được driver triển khai đầy đủ**. Có thể thăm dò:

```java
// Mảnh code, connection là một Connection thật:
DatabaseMetaData meta = connection.getMetaData();
System.out.println(meta.getDatabaseProductName());
System.out.println(meta.getDatabaseProductVersion());
System.out.println(meta.getDriverName());
System.out.println(meta.getDriverVersion());
```

Kiểm tra `Types.SQLXML`/`getTypeInfo`, `ResultSetMetaData.getColumnType`, `SQLFeatureNotSupportedException` cùng thực tế bind/read. Khi báo lỗi, ghi **method, giai đoạn, SQLState, vendor code, DBMS/driver version và schema**; tránh chỉ sao chép English message.

## 10. SQL NULL, XML rỗng và XML element rỗng

| Biểu diễn | Có giá trị SQL? | Có XML document well-formed? |
| --- | --- | --- |
| SQL `NULL` | Không | Không áp dụng; không phải một XML document. |
| Java String `null` | Không có String | Không tự động trở thành SQL NULL. |
| `SQLXML` vừa `createSQLXML` | Chưa khởi tạo content | Không coi nó là SQL NULL. |
| `""` | Có String dài 0 | Không, vì thiếu root element. |
| `"<root/>"` | Có XML value | Có, root rỗng là hợp lệ. |
| `"<root></root>"` | Có XML value | Có, tương đương về structure với self-closing root. |
| `"<root> </root>"` | Có XML value | Có, chứa whitespace text. |

`ResultSet.wasNull()` phản ánh getter **ngay trước đó**, vì vậy phải gọi ngay sau `getSQLXML` thay vì sau một getter khác. Trước khi đọc `getString()`, kiểm tra SQLXML có phải null không. Gọi `xml.getString()` trên Java null sẽ ném `NullPointerException` phía Java, không phải `SQLException` từ driver.

Một số DBMS có hành vi SQL empty string khác nhau với text columns; **không sao chép những khác biệt đó thành quy tắc chung cho XML**. Dùng cột XML thực và test.

## 11. XML parser security: XXE, DOCTYPE và entity bombs

XML đầu vào từ người dùng, từ database hoặc từ hệ thống tích hợp vẫn có thể chứa **external entity declarations**, DTD, schema location, entity expansions hoặc payload lớn. SQLXML API **không tự hứa mọi `Source`/`Result` đều áp dụng security policy của ứng dụng**.

Khi ứng dụng chủ động parse XML:

1. Bật `XMLConstants.FEATURE_SECURE_PROCESSING` rõ ràng.
2. Cấu hình `XMLConstants.ACCESS_EXTERNAL_DTD = ""` và `ACCESS_EXTERNAL_SCHEMA = ""` cho factory hỗ trợ.
3. Với tài liệu không cần DTD, **chặn DOCTYPE** bằng feature phù hợp với parser đã kiểm chứng.
4. Kiểm soát entity expansion/DOM nesting/input size/depth và tài nguyên CPU/RAM.
5. Không tự ý mở network/file paths trong entity resolver; không dùng permissive external protocol access để “chữa lỗi XML”.
6. Nếu transform XML bằng XSLT, cấu hình riêng `TransformerFactory`, external stylesheet access, secure processing và extension functions.
7. Nếu dùng SAX/StAX/XMLInputFactory, kiểm tra security properties **của factory đó**, không giả định thiết lập của DOM tự lan sang StAX.
8. Không dùng `getSource(DOMSource.class)` của driver rồi tự tin rằng parser nội bộ luôn có cùng security settings; driver implementation khác nhau.
9. Khi lưu XML chưa tin cậy, có policy content validation trước DB nếu yêu cầu sản phẩm, không dựa chỉ vào DB XML type.
10. Nếu bạn không cần entity expansion, chặn DTD giúp đơn giản hóa threat model.

Đừng đánh đồng **XSD validation** với **XML well-formedness**. `DocumentBuilder` mặc định có thể parse một document well-formed không tuân theo domain schema. Nếu nghiệp vụ yêu cầu `<invoice>` với các element bắt buộc, cần validate XSD (hoặc business schema) theo policy, và bảo vệ external schema access như trên.

## 12. Quản lý resource và thời điểm free()

`SQLXML` có thể giữ tài nguyên DB/driver, buffer hoặc locator. `free()` nên được gọi khi không còn cần XML object; sau đó object không còn usable.

### 12.1. Thứ tự tài nguyên đúng

```text
Connection mở
  PreparedStatement tạo
    SQLXML = connection.createSQLXML()
      Writer/OutputStream mở (nếu cần)
      write(...) hoàn tất
      Writer/OutputStream đóng
    PreparedStatement.setSQLXML(...)
    PreparedStatement.executeUpdate(...)
    SQLXML.free()
  PreparedStatement đóng
Connection commit/rollback theo transaction
Connection đóng
```

Đây là thứ tự nguyên tắc. Trong code thực, dùng `try/finally` để free XML và `try-with-resources` cho JDBC statements/streams. Nếu `free()` ném SQLException trong lúc cleanup sau một lỗi chính, không được âm thầm nuốt nguyên nhân quan trọng; Java suppressed exceptions hoặc logging framework giúp lưu cả hai.

### 12.2. Một số anti-pattern

**Dùng SQLXML sau khi free:**

```java
SQLXML value = connection.createSQLXML();
value.setString("<root/>");
value.free();
preparedStatement.setSQLXML(1, value); // Không hợp lệ: đã free.
```

**Ghi hai lần vào một SQLXML:**

```java
SQLXML value = connection.createSQLXML();
value.setString("<root/>");
value.setString("<again/>"); // Không còn writable; SQLException theo contract.
```

**Đọc nhiều lần:**

```java
SQLXML value = resultSet.getSQLXML(1);
String first = value.getString();
String second = value.getString(); // Không portable: object đã not readable.
```

Các đoạn này **minh họa hành vi sai**, không chạy trong ứng dụng thật và cần cleanup tài nguyên nếu dùng khi test. Mọi phép test kiểu “expect SQLException” phải thực thi với driver xác định, không giả định exception message.

### 12.3. Java 17 versus Java 26 AutoCloseable

`SQLXML.free()` **có từ Java 6 và còn dùng được trên Java 17+**. Từ **Java 26**, `SQLXML` còn extends `AutoCloseable` và bổ sung default `close()` gọi `free()`. Vì thế:

- Source target `--release 17`: dùng `try/finally { xml.free(); }`.
- Source target Java 26+ mới: có thể `try (SQLXML xml = connection.createSQLXML())`.
- Không đưa API `SQLXML.close()` mới vào code biên dịch `--release 17`.
- Bất kể version, stream ghi vào XML phải được close **trước execute**; SQLXML.close/free không tự hoàn tất XML đang viết dở.

## 13. Khi nào XML hợp lệ về cú pháp nhưng vẫn thất bại?

Một XML document như:

```xml
<invoice currency="USD">
    <amount>-10</amount>
</invoice>
```

là well-formed, nhưng có thể sai nghiệp vụ nếu `amount` phải không âm hoặc một schema yêu cầu thêm `customerId`. Kết quả sẽ khác tùy DBMS có XML Schema Collection/constraint không.

Những nguyên nhân độc lập cần ghi rõ:

- **SQLXML API feature unsupported:** `createSQLXML/setSQLXML/getSQLXML` không được driver triển khai.
- **XML syntax invalid:** root/tag/escape/Unicode rules sai.
- **Schema or domain invalid:** well-formed nhưng thiếu elements/attributes hoặc sai type theo XSD.
- **SQL NULL constraint:** column `NOT NULL` từ chối NULL.
- **SQL column type mismatch:** truyền XML object vào TEXT/JSON/binary column sai mapping.
- **Driver conversion error:** encoding/representation không được hỗ trợ.
- **Resource lifecycle error:** Writer chưa đóng, SQLXML đã free, object bị đọc/ghi nhiều lần.
- **Transaction error:** transaction aborted do exception trước, nếu chưa rollback.
- **Server limits:** max document size, XML depth, entity/DTD restrictions hoặc query timeout.
- **Security policy:** từ chối DOCTYPE, external entities dù XML well-formed.

Một bảng test tốt có **positive control** cùng schema/driver; nếu positive case cũng thất bại, không thể diễn giải các negative cases là “validation thành công”.

## 14. Quy trình kiểm thử theo DBMS/driver thực tế

### 14.1. Trước khi chạy

- Xác định DBMS + version, JDBC driver + version, Java runtime + version.
- Xác nhận DBMS hỗ trợ **native XML type** và driver mapping `Types.SQLXML`; nếu không, ghi UNSUPPORTED.
- Tạo bảng test XML **trong sandbox**; không dùng bảng production hoặc lưu PII.
- Dùng quyền tối thiểu, có quota storage/resource và rollback.
- Xác nhận `setNull(Types.SQLXML)` phù hợp với cột nullable.
- Kiểm tra một XML hợp lệ được ghi và đọc lại; chỉ sau đó chạy invalid tests.
- Bảo đảm test không lưu XML xấu khi có driver nhận bất thường, bằng transaction rollback.
- Nếu driver báo transaction abort, rollback giữa các cases.

### 14.2. Khi chạy

- Quan sát lỗi tại `createSQLXML()`, `setString()`, `setCharacterStream()`, `setSQLXML()`, `executeUpdate()` hay `getSQLXML()`.
- Với XML không hợp lệ, đừng chỉ check “đã ném SQLException”; ghi **operation** và **SQLState/vendor code** để xem đúng bản chất lỗi.
- Với SQL NULL, check `getSQLXML()==null` + `wasNull()==true` ngay sau getter.
- Với Writer mở, test bằng **XML text well-formed** để tách lifecycle error khỏi syntax error.
- Với Writer đã đóng nhưng tài liệu thiếu tag, test riêng để xác nhận lỗi cú pháp.
- Với `setResult(StreamResult.class)` và `StAXResult`, test complete/incomplete writes theo khả năng của driver.
- Với XML lớn, đo memory và stream/serialization behavior, không mặc định XML document sẽ được giữ theo dạng text.
- Khi xảy ra lỗi, rollback và xác minh bảng test không còn row đã chèn.

### 14.3. Báo cáo kết quả

| Trạng thái | Khi nào dùng |
| --- | --- |
| **PASS** | Điều kiện kiểm thử cụ thể được xác minh bằng dữ liệu và assertion. |
| **REJECTED_AT_SET** | Invalid XML bị SQLException tại `setString`/`setResult`. |
| **REJECTED_AT_BIND** | Driver từ chối tại `setSQLXML` vì state/content lỗi. |
| **REJECTED_AT_EXECUTE** | Server/driver từ chối khi thực thi SQL. |
| **UNSUPPORTED** | Driver/DBMS không triển khai SQLXML method/type cho bài test. |
| **ACCEPTED_REVIEW** | Input sai hoặc stream mở mà driver chấp nhận; phải điều tra, không gọi PASS. |
| **BLOCKED_BY_ENVIRONMENT** | Không có DBMS/schema/driver/credentials; không có kết luận integration. |
| **FAIL** | Hợp đồng sản phẩm bị vi phạm (ví dụ NULL readback không đúng hoặc dữ liệu lỗi được lưu ngoài mong đợi). |

Nếu driver phát sinh một `SQLException` khác về network/authorization/schema, nó không đồng nghĩa `REJECTED_AT_SET` do invalid XML. **Phân loại dựa vào cause, stage và positive controls**.

## 15. Lỗi thường gặp và cách sửa

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `createSQLXML()` thành công nhưng bind ngay lỗi | Chưa gán XML content. | Khởi tạo bằng **một** setter hợp lệ trước bind. |
| `setCharacterStream` trả Writer, `execute` lỗi | Writer chưa đóng. | Hoàn tất write, đóng Writer rồi bind/execute. |
| Writer đã đóng mà DB vẫn báo malformed | Nội dung thiếu tag hoặc ký tự XML sai. | Validate syntax độc lập trước JDBC. |
| `setString("<root>")` không lỗi nhưng execute lỗi | Driver trì hoãn validation. | Bắt SQLException xuyên setter/bind/execute, rollback. |
| `setString("")` được coi là NULL | Empty String không có root, khác SQL NULL. | Dùng `setNull(index, Types.SQLXML)`. |
| `setString(null)` để lưu SQL NULL | Nhầm Java null với SQL NULL parameter. | Bind SQL NULL ở PreparedStatement. |
| `rs.getSQLXML(...).getString()` ném NPE | Cột SQL NULL làm getter trả Java null. | Kiểm tra SQLXML object và `rs.wasNull` trước. |
| `getString` lần thứ hai lỗi | SQLXML đã not readable sau getter đầu. | Đọc đúng một lần hoặc lưu bản sao ở app với giới hạn. |
| `setString` lần thứ hai lỗi | SQLXML đã not writable. | Tạo SQLXML mới cho lần ghi mới. |
| `getString` sau `free` lỗi | Object đã giải phóng. | Không dùng lại sau free; quản lý scope. |
| `try (SQLXML xml = ...)` không biên dịch Java 17 | `SQLXML.close()/AutoCloseable` chỉ mới có từ Java 26. | Trên Java 17 dùng `free()` trong finally. |
| XML có DOCTYPE được parser mở file/network | Chưa khóa JAXP external access. | Explicit secure processing, chặn DOCTYPE/DTD/XXE. |
| XML well-formed nhưng business validation fail | XSD/domain rules khác well-formedness. | Validate schema riêng có security policy. |
| `setResult(StAXResult.class)` lỗi khi bind | StAX writer chưa hoàn tất document. | End/flush/close theo contract trước bind. |
| XML output byte khác dù cấu trúc giống | DB nội bộ reserialize XML. | So DOM/semantic equivalence khi phù hợp. |
| DB không có SQL XML native type | Feature unsupported hoặc column mapping sai. | Ghi UNSUPPORTED, không gọi PASS trên TEXT. |
| SQL NULL bị DB từ chối | Cột NOT NULL hoặc type mapping khác. | Kiểm tra DDL và parameter `Types.SQLXML`. |
| SQLException bị nuốt khiến row test tồn tại | Thiếu rollback/finally. | Test trong transaction sandbox và rollback mỗi case. |
| XML quá lớn gây heap pressure | `getString`/DOM materialize toàn document. | Dùng stream/streaming parser và resource limits. |
| Test sai vì stdout DBMS khác | Error text/SQLState/vendor khác nhau. | Ghi diagnostics, không hardcode English exception message. |

## 16. Checklist triển khai và kiểm thử

- [ ] Đã xác định DBMS/driver/JDK versions và XML column type thực tế?
- [ ] Đã xác nhận driver hỗ trợ `createSQLXML`, `setSQLXML` và `getSQLXML`?
- [ ] Positive control XML well-formed có thể INSERT/SELECT trong môi trường thử?
- [ ] Có fixture thẻ thiếu, thẻ đóng sai, nhiều root, empty string, ký tự XML illegal?
- [ ] Có phân biệt **XML syntax invalid** với **schema invalid** và **DOCTYPE blocked**?
- [ ] Java null/SQL NULL/empty XML text/SQLXML chưa initialized được test riêng?
- [ ] SQL NULL bind qua `setNull(..., Types.SQLXML)` và readback qua `wasNull`?
- [ ] Writer/OutputStream/Result đều hoàn tất và đóng **trước execute**?
- [ ] Đã test Writer **chưa đóng nhưng content well-formed** để cô lập lifecycle error?
- [ ] Đã test Writer đóng rồi nhưng XML text còn thiếu closing tags?
- [ ] Đã test read/write một lần và free/use-after-free theo driver?
- [ ] Với Java 17 target, dùng `free()` thay vì `SQLXML.close()` của Java 26?
- [ ] JAXP parser được cấu hình secure processing, external access blocked và DOCTYPE policy?
- [ ] Không parse XML untrusted bằng parser mặc định chưa kiểm chứng security settings?
- [ ] SQLException được ghi theo **stage**, SQLState và vendor code, không chỉ message?
- [ ] Mỗi negative test rollback và không lưu dữ liệu xấu?
- [ ] DB XML serialization có thể thay đổi, assertions so cấu trúc thay vì byte text khi cần?
- [ ] LOB/large XML có được đọc theo stream và giới hạn memory/size?
- [ ] Không coi JDK-only tests là kết quả của DBMS integration tests?
- [ ] Không ghi credentials hoặc thông tin DB nhạy cảm vào README/log/test artifacts?

## 17. Bài tập thực hành

**Bài A — Syntax:** mở `XmlBoundaryChecks.java`, bổ sung fixture sai escape `<root>A & B</root>` và attribute thiếu dấu ngoặc kép; kiểm tra parser trả false. Phân biệt lỗi này với policy chặn DOCTYPE.

**Bài B — NULL:** trong sandbox có cột SQL XML nullable, so sánh `setNull(index, Types.SQLXML)`, `setSQLXML(index,null)` và `setString("")` nếu driver cho phép; ghi rõ mỗi nhánh và đừng mặc định chúng giống nhau.

**Bài C — Unclosed Writer:** thử `setCharacterStream`, ghi `"<root/>"` nhưng không close trước `setSQLXML`; ghi giai đoạn từ chối. Đóng Writer trong finally rồi free SQLXML; không chạy trên database production.

**Bài D — Closed but malformed:** dùng Writer viết `"<root><a>"` rồi close; khác nhánh “Writer còn mở” như thế nào, có SQLException ở setter/bind/execute?

**Bài E — Double use:** với driver thật, gọi `setString` hai lần trên một `SQLXML` để quan sát not writable; gọi `getString` hai lần trên readable SQLXML để quan sát not readable. Luôn free và rollback.

**Bài F — Secure parsing:** dùng một XML có DOCTYPE tham chiếu `file:` hoặc `http:` trong sandbox; xác nhận parser **từ chối trước khi truy cập external resource**, không thực hiện network/file requests.

**Bài G — DB schema constraints:** tạo một well-formed XML không thỏa XSD/domain constraint của ứng dụng. Phân biệt lỗi schema với XML malformed và null constraint.

**Bài H — XML lớn:** thử một XML document lớn có tiếng Việt/emoji trên DB test; so sánh đọc bằng `getString` và `getCharacterStream` về heap/throughput. Nhớ rằng driver có thể buffer.

**Bài I — Version compatibility:** biên dịch code dùng `SQLXML.free()` với `--release 17`. Nếu môi trường có JDK 26+, thử API `SQLXML.close()` mới trong một target riêng và quan sát compile failure khi dùng `--release 17`.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** `SQLXML` vừa `createSQLXML` có phải SQL NULL?

**Đáp án:** Không. Đây là một object để ghi XML chưa được khởi tạo nội dung. SQL NULL phải bind bằng API parameter thích hợp.

**Câu 2.** `setString("<root>")` có bắt buộc ném SQLException ngay không?

**Đáp án:** Không. JDBC cho phép kiểm tra XML sai/incomplete ở giai đoạn set hoặc khi execute. Test phải xem cả pipeline.

**Câu 3.** Vì sao XML `"<root/>"` có thể gây lỗi khi bind dù bản thân well-formed?

**Đáp án:** Nếu nó được ghi bằng `SQLXML.setCharacterStream()` nhưng Writer còn mở, **lifecycle output chưa hoàn tất**.

**Câu 4.** `""`, `"<root/>"` và SQL NULL có giống nhau không?

**Đáp án:** Không. Chuỗi rỗng thiếu root XML; root rỗng là XML well-formed; SQL NULL là không có giá trị.

**Câu 5.** Tại sao đọc SQL NULL cần kiểm tra `rs.wasNull()` ngay sau `getSQLXML`?

**Đáp án:** `wasNull` mô tả kết quả getter gần nhất; getter SQLXML của cột NULL có thể trả Java null nên không thể gọi `getString` trực tiếp.

**Câu 6.** Đã đóng Writer thì chắc chắn XML hợp lệ?

**Đáp án:** Không. Writer có thể ghi thiếu thẻ hoặc có ký tự bất hợp lệ; đóng Writer chỉ hoàn tất tài nguyên ghi.

**Câu 7.** Dùng `SQLXML.close()` trong code `--release 17` có hợp lệ?

**Đáp án:** Không. Java 26 mới bổ sung AutoCloseable/close trên SQLXML. Với Java 17 dùng `SQLXML.free()` trong finally.

**Câu 8.** `SQLXML.getString()` có phải được gọi bao nhiêu lần cũng được?

**Đáp án:** Không. Hợp đồng chỉ cho phép một lần đọc SQLXML object; getter làm nó chuyển sang not readable.

**Câu 9.** Có thể coi XML chứa DOCTYPE là “không well-formed” không?

**Đáp án:** Không nhất thiết. DOCTYPE có thể hợp lệ về cú pháp, nhưng được parser **chủ động chặn theo security policy** để giảm rủi ro XXE.

**Câu 10.** Vì sao test JDK-only 9 PASS không chứng minh DBMS hỗ trợ SQLXML?

**Đáp án:** Vì test độc lập chỉ dùng JAXP, không gọi JDBC driver/DBMS. Muốn kết luận về SQLXML và SQL NULL phải chạy integration tests trên một DBMS/driver/schema cụ thể.

## 19. Nguồn API và hướng dẫn chính thức hiện hành

- [SQLXML — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLXML.html): states, set/get methods, incomplete/invalid XML, streams và `free()/close()` (Java 26+).
- [SQLXML — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLXML.html): phiên bản phù hợp `--release 17`, `free()`.
- [Connection — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Connection.html): `createSQLXML()` và transaction lifecycle.
- [PreparedStatement — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/PreparedStatement.html): `setSQLXML` và `setNull`.
- [ResultSet — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/ResultSet.html): `getSQLXML` và `wasNull`.
- [Types — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Types.html): constant `Types.SQLXML`.
- [SQLException — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLException.html): SQLState, vendor code và exception chaining.
- [JAXP Security Guide — Java SE 25](https://docs.oracle.com/en/java/javase/25/security/java-api-xml-processing-jaxp-security-guide.html): secure processing, external access restrictions, XML parser security.
- [Microsoft JDBC Driver: Programming with SQLXML](https://learn.microsoft.com/en-us/sql/connect/jdbc/programming-with-sqlxml): một ví dụ cụ thể về SQLXML support/NULL/lifecycle của **vendor**, không phải contract chung cho mọi driver.

**Ghi nhớ:** SQLXML không tự trở thành XML hợp lệ chỉ vì gọi `createSQLXML`. **XML sai** có thể lỗi tại set/bind/execute; **SQL NULL** phải bind bằng parameter null chứ không dùng chuỗi rỗng; **Writer/OutputStream/Result ghi XML phải được hoàn tất/đóng trước execute**. Với Java 17+ tương thích, quản lý tài nguyên bằng `SQLXML.free()`; riêng Java 26 bổ sung `AutoCloseable/close()`. Luôn tách kiểm thử JAXP độc lập khỏi kiểm thử driver/DBMS thực tế, và bảo vệ parser trước XXE.
