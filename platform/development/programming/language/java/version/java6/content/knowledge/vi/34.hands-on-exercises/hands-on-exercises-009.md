# Ứng dụng JDBC dùng Unicode, SQLXML và phân loại ngoại lệ

## 1. Mục tiêu thực hành

Một ứng dụng Java cần lưu tên tiếng Việt, nội dung Nhật/emoji và một tài liệu XML trong database, rồi đọc lại chính xác. Trong quá trình đó nó có thể gặp lỗi trùng khóa, mất kết nối, timeout, transaction rollback, sai dữ liệu hoặc JDBC driver không hỗ trợ SQLXML. Nếu chỉ bắt `SQLException` rồi retry mọi thứ thì dễ tạo dữ liệu trùng, mất bản ghi hoặc lộ thông tin nhạy cảm.

Bài **“Ứng dụng JDBC dùng Unicode, SQLXML và phân loại ngoại lệ”**, thuộc nhóm **Thực hành**, module **Java 6**, dùng **kiến thức vẫn áp dụng ở Java SE 26**. Mã chạy đặt mức tương thích **Java 17**; bài kiểm thử được biên dịch bằng `javac --release 17`, chạy trên **OpenJDK 24** và **H2 JDBC 2.5.252** — một database **thực sự chạy trong bộ nhớ**, không dùng mock JDBC.

Bạn sẽ nắm:
- Unicode `String`, UTF-8 byte conversion, code units/code points.
- `PreparedStatement.setString`/`setSQLXML`, `Connection.createSQLXML` và `ResultSet.getSQLXML`.
- Viết XML với `XMLStreamWriter` để escape ký tự đặc biệt.
- Đọc XML bằng parser đã cấu hình từ chối DOCTYPE/XXE.
- Vòng đời và state one-shot của `SQLXML`, cách đóng Writer và `SQLXML.free`.
- JDBC transaction, commit/rollback, tài nguyên và commit outcome không xác định.
- Exception subtype/SQLState/vendor code, nhóm retry được hoặc phải khôi phục.
- Sự khác nhau giữa H2 `CLOB` và PostgreSQL/SQL Server có native XML.
- Một chương trình Java17 hoàn chỉnh, **77/77 assertions PASS trên 5 lần chạy JVM độc lập**.

Luồng xử lý:

```text
Java Unicode String (UTF-16)
       |
XMLStreamWriter -> well-formed escaped XML String
       |
Connection.createSQLXML -> SQLXML.setString/setCharacterStream
       |
PreparedStatement.setString + setSQLXML -> executeUpdate
       |
JDBC transaction COMMIT or ROLLBACK
       |
ResultSet.getString/getSQLXML -> SQLXML.getString
       |
Secure DOM parse, DOCTYPE/XXE disabled
       |
Verify original Unicode text
       |
SQLException subclass + SQLState + vendorCode
       |
Error classification and business-safe recovery policy
```

**Phạm vi đã kiểm chứng:** H2 2.5.252 lưu XML trong **CLOB**, nhưng code thực sự sử dụng `SQLXML` JDBC API; 77 assertions được chạy thành công trên DB thật. Không suy rằng H2 CLOB có native XML constraints, hoặc mọi DB/driver đều hỗ trợ cùng API.

## 2. Unicode Java vs SQL text vs XML

### 2.1. `String` Java và UTF-8

Java `String` là chuỗi Unicode được biểu diễn theo UTF-16 code units. `length()` đếm code units, không phải grapheme clusters. Ký tự ngoài BMP thường dùng surrogate pairs: `"🌸".length()==2`, nhưng một Unicode code point. Với văn bản ngoài BMP và kết hợp dấu tiếng Việt, byte count, code point count và số graphemes đều có thể khác.

Khi cần chuyển thành bytes, chỉ định charset tường minh:

```java
String unicode = "Hà Nội, 東京, 🌸";
byte[] utf8 = unicode.getBytes(StandardCharsets.UTF_8);
String restored = new String(utf8, StandardCharsets.UTF_8);
```

Đây là snippet, cần import `java.nio.charset.StandardCharsets`. Không mặc định dùng `getBytes()` mà không chỉ rõ charset trong các đường lưu file/network/database.

**JDBC text:** `PreparedStatement.setString` nhận Java `String` và JDBC driver chuyển sang character SQL type. Bạn không cần tự ép text thành byte array để lưu vào `VARCHAR`/`TEXT`.

### 2.2. `setString` khác `setNString`

| JDBC API | Kiểu dữ liệu hướng tới | Lưu ý |
| --- | --- | --- |
| `setString` | SQL character text như `VARCHAR`/`TEXT` | Phù hợp Unicode nếu DB encoding/column hỗ trợ |
| `setNString` | SQL national character như `NCHAR`/`NVARCHAR` | Cần driver và schema hỗ trợ |
| `setCharacterStream` | Text lớn qua `Reader` | Có thể giúp không materialize toàn chuỗi |
| `setNCharacterStream` | National-character stream | Tùy driver/SQL type |
| `setSQLXML` | JDBC SQL XML value | Optional feature, xem column/driver |

Không có quy tắc **cứ tiếng Việt là phải dùng `setNString`**. PostgreSQL UTF8 dùng `text`/`varchar` với `setString`; SQL Server phân biệt VARCHAR/NVARCHAR theo encoding/collation. Phải kiểm tra **charset, collation, column length và driver** theo DB đang triển khai.

`setUnicodeStream` đã deprecated; code mới dùng `setCharacterStream` hoặc `setNCharacterStream` phù hợp.

### 2.3. Normalization và SQL collation

Java `equals` so UTF-16 code units; database equality theo collation/schema. Hai chuỗi trông giống nhau có thể ở NFC/NFD khác nhau. Nếu cần canonicalization, định nghĩa rõ policy bằng `Normalizer.Form.NFC` và kiểm thử; không tự normalize passwords, chữ ký hoặc identifiers khi chưa có business contract. `VARCHAR(200)` không phải lúc nào cũng có cùng semantics đếm UTF-16 units/Unicode chars/bytes trên mọi DB.

## 3. Escape XML bằng writer, không nối chuỗi

`PreparedStatement` bảo vệ **SQL syntax**, không làm text thành XML hợp lệ. Ví dụ tự nối:

```java
String xml = "<title>" + title + "</title>";
```

sẽ sai nếu title chứa `&` hoặc `<`. Dùng StAX writer:

```java
StringWriter out = new StringWriter();
XMLStreamWriter writer =
        XMLOutputFactory.newFactory().createXMLStreamWriter(out);
try {
    writer.writeStartElement("document");
    writer.writeStartElement("title");
    writer.writeCharacters(title);
    writer.writeEndElement();
    writer.writeEndElement();
    writer.writeEndDocument();
    writer.flush();
} finally {
    writer.close();
}
String xml = out.toString();
```

Đây là snippet, cần imports `StringWriter`, `XMLStreamWriter`, `XMLOutputFactory` và biến `title`. `writeCharacters` escape XML markup, giữ tiếng Việt/emoji hợp lệ. Không đưa user-controlled text làm tag names/attribute names không validate.

**Encoding declaration:** `StringWriter` tạo **String**, chưa tạo UTF-8 bytes. Bài cố ý không ghi `encoding="UTF-8"` vào XML declaration để tránh khai báo charset không khớp bytes ở serializer. Nếu ghi vào OutputStream, byte charset và XML declaration phải nhất quán.

## 4. SQLXML có lifecycle riêng

`SQLXML` thuộc module `java.sql`. Các phương thức quan trọng:

| API | Chức năng | Ghi chú |
| --- | --- | --- |
| `Connection.createSQLXML()` | Tạo writable SQLXML rỗng | Driver có thể ném SQLFeatureNotSupportedException |
| `SQLXML.setString(xml)` | Nạp XML String | Không gọi set nhiều lần |
| `SQLXML.setCharacterStream()` | Ghi bằng Writer | Phải đóng Writer trước JDBC execute |
| `SQLXML.setBinaryStream()` | Ghi bytes | Kiểm tra charset/XML declaration |
| `SQLXML.setResult(...)` | Ghi DOM/SAX/StAX Result | Kiểm tra driver support |
| `PreparedStatement.setSQLXML(i,x)` | Bind SQL XML value | Driver và column quyết định |
| `ResultSet.getSQLXML(column)` | Lấy XML value từ row | Có thể trả null khi SQL NULL |
| `SQLXML.getString()` | Đọc String representation | Có thể materialize toàn XML |
| `SQLXML.getCharacterStream()` | Đọc qua Reader | Đóng stream trước free |
| `SQLXML.getSource(...)` | Đọc XML Source | Không mặc định parser secure |
| `SQLXML.free()` | Giải phóng SQLXML | Dùng trong finally |

### 4.1. Read/write state machine và transaction lifetime

Theo Javadoc Java SE26, SQLXML là resource có state:
- Object mới tạo từ `createSQLXML` là writable nhưng chưa initialized.
- Các phương thức write (`setString`, `setCharacterStream`, `setBinaryStream`, `setResult`) chuyển instance sang **not writable**.
- Các phương thức read (`getString`, `getCharacterStream`, `getSource`, `getBinaryStream`) có thể chuyển instance sang **not readable**.
- Không giả định có thể set/get nhiều lần tùy thích.
- Sau `free`, các API đọc/ghi khác bị lỗi. `free` gọi lặp lại được và là no-op.
- SQLXML có lifetime gắn với transaction, ResultSet và connection liên quan; không giữ object để dùng sau đóng.

**Cách dùng đúng:** đọc SQLXML thành String/domain model khi ResultSet còn sống, free ngay sau đó. Nếu cần đọc thêm, dùng bản String đã copy; đừng gọi getString liên tục trên cùng SQLXML.

### 4.2. Điểm dễ sai về version Java: close() chỉ từ Java26

`SQLXML.free()` đã có lâu và vẫn được dùng. **SQLXML extends AutoCloseable, có default `close()` từ Java SE 26**, không phải từ Java17. Vì chương trình biên dịch với `javac --release 17`, dùng `try (SQLXML x = ...)` là **không tương thích**.

Giải pháp portable Java17:

```java
SQLXML xml = connection.createSQLXML();
try {
    xml.setString(xmlText);
    prepared.setSQLXML(3, xml);
    prepared.executeUpdate();
} finally {
    xml.free();
}
```

Đây là snippet cần `connection/prepared/xmlText`. **Giữ SQLXML sống tới sau `executeUpdate`**, vì driver có thể đọc lúc execute. Khi target Java26 API thật, try-with-resources hỗ trợ SQLXML.close (default gọi free).

### 4.3. Writer phải đóng trước setSQLXML/execute

```java
SQLXML value = connection.createSQLXML();
try {
    try (Writer writer = value.setCharacterStream()) {
        writer.write(xmlText);
    }
    prepared.setSQLXML(3, value);
    prepared.executeUpdate();
} finally {
    value.free();
}
```

Snippet này cần `Writer` và các biến đã khởi tạo. `PreparedStatement.setSQLXML` Javadoc cho biết có thể lỗi nếu `Writer`/`OutputStream`/`Result` đang viết XML chưa được đóng. Demo chạy thực đường streaming này.

### 4.4. `getSource(DOMSource)` không tự thay thế XML security

SQLXML `getSource`/`setResult` có thể tận dụng parser và driver optimizations, nhưng không chứng minh parser mặc định chặn XXE. Với XML không tin cậy, tự cấu hình DOM/SAX/StAX/XSLT security. Đừng dùng XML Source từ driver rồi bỏ qua external entity settings.

## 5. Cấu trúc bảng H2 trong thực hành

Demo chạy schema:

```sql
CREATE TABLE documents (
    id BIGINT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    body_xml CLOB NOT NULL
);
```

Với H2 2.5.252, `Connection.createSQLXML`, `PreparedStatement.setSQLXML` và `ResultSet.getSQLXML` được kiểm thử **thật**, nhưng `body_xml` vẫn là **CLOB chứa XML text**. CLOB **không tự** kiểm tra XML well-formed, DTD/XSD hay XML query semantics. App phải tạo XML đúng và parse an toàn.

Connection dùng:

```text
jdbc:h2:mem:jdbc_unicode_375;DB_CLOSE_DELAY=-1
```

Nó khởi tạo một DB in-memory **trong JVM test**; DB_CLOSE_DELAY=-1 giúp connection thứ hai đọc lại sau connection thứ nhất commit. Username `sa`, password rỗng **chỉ dùng để học với H2 local**, không dùng trong production hoặc DB reachable từ mạng.

Schema DDL được chạy lúc auto-commit; `setAutoCommit(false)` sau đó mới quản lý DML. **DDL commit/rollback không portable giữa các DB**, nên tách migrations khỏi transaction nghiệp vụ.

## 6. PreparedStatement và Unicode SQL injection test

Sử dụng bind parameters:

```java
try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO documents(id,title,body_xml) VALUES(?,?,?)")) {
    ps.setLong(1, id);
    ps.setString(2, title);
    ps.setSQLXML(3, xml);
    ps.executeUpdate();
}
```

Đây là snippet. `PreparedStatement` cho phép user text tồn tại như **value**, không phải SQL source. Demo ghi title đặc biệt:

```text
O'Connor'); DROP TABLE documents; -- 東京
```

sau đó đọc lại title và XML đúng, bảng không bị xóa. **SQL placeholders không thay được table/column identifiers**; identifiers động phải whitelist, không nối user string vào SQL fragment.

**Phân biệt:** SQL parameterization chống SQL injection, còn `XMLStreamWriter.writeCharacters` chống XML markup injection. Cần **cả hai**.

## 7. Đọc XML an toàn: chống DTD, XXE và XML bombs

Demo đọc SQLXML String rồi dùng `DocumentBuilderFactory` với:
- `XMLConstants.FEATURE_SECURE_PROCESSING=true`.
- `disallow-doctype-decl=true`.
- External general và parameter entities **false**.
- `ACCESS_EXTERNAL_DTD=""`, `ACCESS_EXTERNAL_SCHEMA=""`.
- `XIncludeAware=false`, `ExpandEntityReferences=false`.
- `EntityResolver` reject external lookups.
- `ErrorHandler` throw parse errors thay vì in payload.
- Guard length tối đa 64.000 UTF-16 units **cho fixture**.

```java
DocumentBuilderFactory f = DocumentBuilderFactory.newInstance();
f.setNamespaceAware(true);
f.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
f.setFeature(
    "http://apache.org/xml/features/disallow-doctype-decl", true);
f.setFeature(
    "http://xml.org/sax/features/external-general-entities", false);
f.setFeature(
    "http://xml.org/sax/features/external-parameter-entities", false);
f.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
f.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
f.setXIncludeAware(false);
f.setExpandEntityReferences(false);
```

Đây là snippet cấu hình, full file có `newDocumentBuilder`, resolver deny-all, error handler và `parse`. Nếu parser provider không nhận một feature security quan trọng, **fail closed**, không catch rồi parse insecurely.

**Tests thực tế:** từ chối DOCTYPE chứa internal entity, external file entity, malformed XML và input vượt limit. Không đọc external file hoặc mở HTTP trong test. Limit 64 KB **không thay thế** depth/event/time/memory budgets cho XML lớn; production cần thêm các guards.

## 8. JDBC transaction và resource ownership

`Connection` mặc định thường auto-commit. Với nhiều DML statements, dùng transaction tường minh:

```java
try (Connection con = dataSource.getConnection()) {
    con.setAutoCommit(false);
    try {
        // PreparedStatement DML operations.
        con.commit();
    } catch (SQLException primary) {
        try {
            con.rollback();
        } catch (SQLException secondary) {
            primary.addSuppressed(secondary);
        }
        throw primary;
    }
}
```

Đây là **snippet** cần `DataSource` và DML cụ thể. Với framework transaction manager phải phối hợp để không commit/rollback ngoài ý muốn.

**Cleanup:** `Connection`, `PreparedStatement` và `ResultSet` đóng qua try-with-resources; `SQLXML` dùng `free()` trong finally khi target Java17.

**Rollback failure:** giữ primary SQLException, gắn secondary vào suppressed. Sau connection failure, connection có thể hỏng; discard/reopen qua pool policy.

**Commit timeout:** Nếu mất kết nối trong/Ngay sau `COMMIT`, kết quả có thể **không xác định**: DB đã commit hoặc chưa. Không tự replay INSERT/payment/email; dùng idempotency keys, reconcile state sau reconnect và chỉ retry whole transaction khi business-safe.

## 9. Phân loại SQLException: subtype trước, SQLState sau

`SQLException` chứa:
- `getSQLState()` — mã SQLState (X/Open hoặc SQL:2003), có thể null.
- `getErrorCode()` — integer vendor-specific, không portable.
- `getNextException()` — chain JDBC bổ sung.
- `getCause()` — Throwable cause theo Java, khác getNextException.
- `getSuppressed()` — cleanup/rollback/try-with-resources failures.
- `getMessage()` — human-readable text, không nên parse regex làm classifier.

### 9.1. Hệ phân cấp ngoại lệ còn áp dụng

| Java exception | Ý nghĩa | Xử lý phù hợp |
| --- | --- | --- |
| `SQLTimeoutException` | Extends `SQLTransientException`; timeout | Check cancellation/outcome trước retry |
| `SQLTransientConnectionException` | Temporary connection error | Reconnect nếu an toàn |
| `SQLTransactionRollbackException` | Transaction serialization/deadlock rollback | Retry **entire transaction** có giới hạn |
| `SQLTransientException` | Transient generic | Xét idempotency và context |
| `SQLRecoverableException` | Extends **trực tiếp SQLException** | Ít nhất đóng connection và lấy connection mới |
| `SQLNonTransientConnectionException` | Connection cần corrective action | Không retry mù |
| `SQLIntegrityConstraintViolationException` | PK/unique/FK/check | Conflict hoặc reconcile idempotency |
| `SQLDataException` | Data conversion/truncation | Fix payload/schema |
| `SQLInvalidAuthorizationSpecException` | Credentials/permissions | Fix config/roles |
| `SQLSyntaxErrorException` | SQL syntax/access rule | Fix query/schema |
| `SQLFeatureNotSupportedException` | Driver không hỗ trợ optional JDBC feature | Change driver/DB/route |
| `SQLNonTransientException` | Non-transient generic | Fix cause |
| `BatchUpdateException` | Partial batch results | Inspect update counts |
| `SQLWarning` | Warning subtype of SQLException | Không mặc định operation fail |

**Quan trọng:** Xét `SQLTimeoutException` trước `SQLTransientException` để không mất phân loại timeout. `SQLRecoverableException` **không phải** subtype transient. Nó yêu cầu recovery step, tối thiểu close old connection và mở new one rồi mới cân nhắc retry entire transaction.

### 9.2. SQLState classes

| SQLState prefix | Class semantics | Ví dụ |
| --- | --- | --- |
| `08` | Connection exception | `08006` |
| `40` | Transaction rollback | `40001`, `40P01` |
| `23` | Integrity constraint | `23505` |
| `22` | Data exception | `22001` |
| `28` | Invalid authorization | `28000` |
| `42` | Syntax/access rule | `42601` |
| `0A` | Feature not supported | `0A000` |

Classifier trong source **ưu tiên subclass** rồi fallback sang **hai ký tự đầu** của SQLState. Nếu không nhận diện thì `UNKNOWN`, không đoán retry. SQLState có thể là null, conventions khác nhau theo `DatabaseMetaData.getSQLStateType()`, vendor-specific codes còn cần mapping riêng.

**Timeout không có một SQLState chuẩn duy nhất** theo `SQLTimeoutException` Javadoc; driver có thể dùng `HYT00` hoặc giá trị khác. SQLState `57014` có thể là query cancellation do nhiều nguyên nhân, **không đủ** để tự kết luận timeout và retry safe. Fixture xác minh `SQLException("cancelled","57014")` trả `UNKNOWN`.

## 10. Retry policy không được chỉ dựa vào tên class

| Classifier kind | Mặc định an toàn |
| --- | --- |
| `QUERY_TIMEOUT` | Kiểm tra outcome, không replay non-idempotent writes |
| `TRANSIENT_CONNECTION` | Reconnect/health-check + kiểm tra transaction state |
| `RECOVER_CONNECTION` | Đóng connection cũ, lấy mới và cân nhắc whole transaction |
| `TRANSACTION_RETRY` | Bounded whole transaction retry, idempotency + backoff |
| `INTEGRITY` | Domain conflict hoặc reconcile idempotency key |
| `DATA` | Sửa payload/column mapping |
| `AUTHENTICATION` | Sửa credentials/permissions |
| `SQL_SYNTAX` | Sửa query/schema/access rules |
| `UNSUPPORTED` | Dùng API hỗ trợ hoặc đổi driver/schema |
| `TRANSIENT_OTHER` | Xác minh retryable context |
| `NON_TRANSIENT_OTHER` | Sửa nguyên nhân, không spam retry |
| `UNKNOWN` | Diagnostics/escalation, không tự retry |

**Không có khẳng định “SQLTransientException luôn an toàn khi thử lại”** đối với payment, INSERT không có idempotency key, webhook/email, COMMIT có outcome unknown. Giới hạn attempt count, backoff/jitter, circuit breaker. Dùng transactional outbox nếu external effects phải gắn logic DB.

Với `SQLRecoverableException`, Javadoc yêu cầu ít nhất close current connection, new connection và retry **entire transaction/branch** khi an toàn; không thử lại một statement cũ trên kết nối đã bị đánh dấu hỏng.

Với duplicate primary key, không retry cùng payload vô hạn. Nếu key là idempotency token thì kiểm tra record cũ trước khi xác nhận outcome, không trả success chỉ dựa vào SQLState 23.

## 11. SQLException chain, SQLWarning, BatchUpdateException

`getNextException()` khác với Java `getCause()`; `getSuppressed` có thể lưu rollback failure. Một `diagnosticChain(SQLException)` nên thu bounded entries với exception class, SQLState, vendor code, correlation/operation ID. Không log raw XML, SQL values, credentials.

`SQLWarning` thực sự extends `SQLException` nhưng được ứng dụng lấy qua `getWarnings` sau một operation có thể đã thành công. Không biến mọi warning thành fatal error. Nếu cần xử lý warnings có ảnh hưởng dữ liệu, đọc theo driver policy.

`BatchUpdateException` có `getUpdateCounts()`/`getLargeUpdateCounts()`; driver có thể dừng sớm hoặc tiếp tục sau item lỗi. `Statement.EXECUTE_FAILED` chỉ failure trong batch context, `Statement.SUCCESS_NO_INFO` là success không có row count. Không retry cả batch blind nếu một số items đã commit hoặc thực hiện side effects.

## 12. Chương trình hoàn chỉnh — Java 17 + H2 SQLXML

File `JdbcUnicodeSqlXmlDemo.java` bên dưới đã được **biên dịch và chạy trên OpenJDK24**, sử dụng database H2 **thật** qua JDBC `DriverManager`. Không mock interfaces, không mở network listener, không sửa database bên ngoài.

Tính năng trong chương trình:
1. Unicode title gồm tiếng Việt/Nhật/emoji, dấu `&`/`<`, quotes.
2. UTF-8 explicit roundtrip, code point vs code-unit test, NFC idempotency.
3. XML StAX writer và secure DOM parser deny DOCTYPE/XXE.
4. Exception classifier theo 13 kinds, subtype/SQLState/vendor code, chained exceptions, warning/batch.
5. JDBC connection/metadata, create H2 schema, manual DML transaction.
6. `Connection.createSQLXML`, `SQLXML.setString`, `PreparedStatement.setSQLXML`.
7. `ResultSet.getSQLXML`, `getString`, `SQLXML.free` và XML semantic parse.
8. Duplicate primary key và rollback không làm mất committed row.
9. Streaming SQLXML `setCharacterStream` với Writer đóng trước INSERT.
10. Unicode SQL injection-like title qua prepared parameters, table vẫn tồn tại.
11. Cross-connection committed readback và JDBC resource cleanup.
12. **77/77 PASS** lần đầu và bốn lượt chạy lại, mỗi lượt 77/77.

### 12.1. Tệp `JdbcUnicodeSqlXmlDemo.java`


```java
import java.io.StringReader;
import java.io.StringWriter;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.sql.BatchUpdateException;
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.SQLDataException;
import java.sql.SQLFeatureNotSupportedException;
import java.sql.SQLIntegrityConstraintViolationException;
import java.sql.SQLInvalidAuthorizationSpecException;
import java.sql.SQLNonTransientConnectionException;
import java.sql.SQLNonTransientException;
import java.sql.SQLRecoverableException;
import java.sql.SQLSyntaxErrorException;
import java.sql.SQLTimeoutException;
import java.sql.SQLTransactionRollbackException;
import java.sql.SQLTransientConnectionException;
import java.sql.SQLTransientException;
import java.sql.SQLWarning;
import java.sql.SQLXML;
import java.sql.Statement;
import java.text.Normalizer;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.stream.XMLOutputFactory;
import javax.xml.stream.XMLStreamWriter;
import org.w3c.dom.Document;
import org.xml.sax.InputSource;
import org.xml.sax.SAXException;
import org.xml.sax.SAXParseException;
import org.xml.sax.helpers.DefaultHandler;

public final class JdbcUnicodeSqlXmlDemo {
    private static int passed;
    private static final String URL =
            "jdbc:h2:mem:jdbc_unicode_375;DB_CLOSE_DELAY=-1";
    private static final String TITLE =
            "Tiếng Việt: Hà Nội, 東京, 👩🏽‍💻 & <chào> \"thử\"";
    private static final String NOTE =
            "Đường phố 🌸, café, một ký tự < và dấu &.";

    enum Kind {
        QUERY_TIMEOUT,
        TRANSIENT_CONNECTION,
        RECOVER_CONNECTION,
        NON_TRANSIENT_CONNECTION,
        TRANSACTION_RETRY,
        INTEGRITY,
        DATA,
        AUTHENTICATION,
        SQL_SYNTAX,
        UNSUPPORTED,
        TRANSIENT_OTHER,
        NON_TRANSIENT_OTHER,
        UNKNOWN
    }

    static void check(String label, boolean condition) {
        if (!condition) throw new AssertionError("FAIL " + label);
        System.out.println("PASS " + label);
        passed++;
    }

    static boolean throwsLike(Class<? extends Throwable> expected,
                              Checked action) {
        try {
            action.run();
            return false;
        } catch (Throwable t) {
            if (!expected.isInstance(t)) {
                throw new AssertionError("Unexpected error " + t, t);
            }
            return true;
        }
    }

    @FunctionalInterface
    interface Checked {
        void run() throws Exception;
    }

    static Kind classify(SQLException e) {
        // Specific subclass checks FIRST: timeout extends transient.
        if (e instanceof SQLTimeoutException)
            return Kind.QUERY_TIMEOUT;
        if (e instanceof SQLRecoverableException)
            return Kind.RECOVER_CONNECTION;
        if (e instanceof SQLTransientConnectionException)
            return Kind.TRANSIENT_CONNECTION;
        if (e instanceof SQLNonTransientConnectionException)
            return Kind.NON_TRANSIENT_CONNECTION;
        if (e instanceof SQLTransactionRollbackException)
            return Kind.TRANSACTION_RETRY;
        if (e instanceof SQLIntegrityConstraintViolationException)
            return Kind.INTEGRITY;
        if (e instanceof SQLDataException)
            return Kind.DATA;
        if (e instanceof SQLInvalidAuthorizationSpecException)
            return Kind.AUTHENTICATION;
        if (e instanceof SQLSyntaxErrorException)
            return Kind.SQL_SYNTAX;
        if (e instanceof SQLFeatureNotSupportedException)
            return Kind.UNSUPPORTED;

        // SQLState prefix is a fallback, not a universal retry policy.
        String state = e.getSQLState();
        if (state != null && state.length() >= 2) {
            return switch (state.substring(0, 2)) {
                case "08" -> Kind.RECOVER_CONNECTION;
                case "40" -> Kind.TRANSACTION_RETRY;
                case "23" -> Kind.INTEGRITY;
                case "22" -> Kind.DATA;
                case "28" -> Kind.AUTHENTICATION;
                case "42" -> Kind.SQL_SYNTAX;
                case "0A" -> Kind.UNSUPPORTED;
                default -> fallback(e);
            };
        }
        return fallback(e);
    }

    private static Kind fallback(SQLException e) {
        if (e instanceof SQLTransientException)
            return Kind.TRANSIENT_OTHER;
        if (e instanceof SQLNonTransientException)
            return Kind.NON_TRANSIENT_OTHER;
        return Kind.UNKNOWN;
    }

    static List<String> diagnosticChain(SQLException e) {
        List<String> result = new ArrayList<>();
        Set<SQLException> seen = new HashSet<>();
        for (SQLException current = e;
             current != null && seen.add(current) && result.size() < 16;
             current = current.getNextException()) {
            result.add(current.getClass().getSimpleName()
                    + "|" + String.valueOf(current.getSQLState())
                    + "|" + current.getErrorCode());
        }
        return List.copyOf(result);
    }

    static String buildXml(String title, String note) throws Exception {
        StringWriter sink = new StringWriter();
        XMLStreamWriter writer =
                XMLOutputFactory.newFactory().createXMLStreamWriter(sink);
        try {
            // XML declaration encoding is intentionally omitted:
            // this output is a Java String, not a UTF-8 byte stream.
            writer.writeStartElement("document");
            writer.writeAttribute("locale", "vi-VN");
            writer.writeStartElement("title");
            writer.writeCharacters(title);
            writer.writeEndElement();
            writer.writeStartElement("note");
            writer.writeCharacters(note);
            writer.writeEndElement();
            writer.writeEndElement();
            writer.writeEndDocument();
            writer.flush();
        } finally {
            writer.close();
        }
        return sink.toString();
    }

    static Document parseXmlSecurely(String xml) throws Exception {
        if (xml.length() > 64_000)
            throw new IllegalArgumentException("XML too large");
        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
        factory.setNamespaceAware(true);
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setFeature(
                "http://apache.org/xml/features/disallow-doctype-decl",
                true);
        factory.setFeature(
                "http://xml.org/sax/features/external-general-entities",
                false);
        factory.setFeature(
                "http://xml.org/sax/features/external-parameter-entities",
                false);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        factory.setXIncludeAware(false);
        factory.setExpandEntityReferences(false);
        DocumentBuilder builder = factory.newDocumentBuilder();
        builder.setEntityResolver((publicId, systemId) -> {
            throw new SAXException("External DTD/entities forbidden");
        });
        builder.setErrorHandler(new DefaultHandler() {
            @Override
            public void error(SAXParseException e) throws SAXException {
                throw e;
            }
            @Override
            public void fatalError(SAXParseException e)
                    throws SAXException {
                throw e;
            }
        });
        return builder.parse(new InputSource(new StringReader(xml)));
    }

    static String text(Document document, String localName) {
        return document.getDocumentElement()
                .getElementsByTagName(localName)
                .item(0)
                .getTextContent();
    }

    static void testPureUnicodeAndXml() throws Exception {
        check("utf8-roundtrip-title",
                TITLE.equals(new String(TITLE.getBytes(
                        StandardCharsets.UTF_8), StandardCharsets.UTF_8)));
        check("unicode-has-supplementary-codepoints",
                TITLE.codePointCount(0, TITLE.length()) < TITLE.length());
        check("unicode-nfc-idempotent",
                Normalizer.normalize(
                        Normalizer.normalize(TITLE, Normalizer.Form.NFC),
                        Normalizer.Form.NFC)
                        .equals(Normalizer.normalize(
                                TITLE, Normalizer.Form.NFC)));
        String xml = buildXml(TITLE, NOTE);
        check("xml-escapes-ampersand", xml.contains("&amp;"));
        check("xml-escapes-less-than", xml.contains("&lt;"));
        check("xml-has-locale", xml.contains("locale=\"vi-VN\""));
        Document doc = parseXmlSecurely(xml);
        check("safe-xml-title-unchanged",
                TITLE.equals(text(doc, "title")));
        check("safe-xml-note-unchanged",
                NOTE.equals(text(doc, "note")));
        check("safe-xml-document-root",
                "document".equals(
                        doc.getDocumentElement().getTagName()));
        check("safe-parser-rejects-doctype",
                throwsLike(SAXException.class,
                        () -> parseXmlSecurely(
                                "<!DOCTYPE document [<!ENTITY x 'BAD'>]>"
                                + "<document><title>&x;</title></document>")));
        check("safe-parser-rejects-external-entity",
                throwsLike(SAXException.class,
                        () -> parseXmlSecurely(
                                "<!DOCTYPE document [<!ENTITY x SYSTEM "
                                + "'file:///no/such/file'>]>"
                                + "<document><title>&x;</title></document>")));
        check("safe-parser-rejects-malformed-xml",
                throwsLike(SAXException.class,
                        () -> parseXmlSecurely("<document><title>x</document>")));
        check("safe-parser-rejects-size-limit",
                throwsLike(IllegalArgumentException.class,
                        () -> parseXmlSecurely("<x>" + "a".repeat(64_001)
                                + "</x>")));
    }

    static void testClassification() throws Exception {
        check("classify-timeout-before-transient",
                classify(new SQLTimeoutException("timeout", "HYT00", 101))
                        == Kind.QUERY_TIMEOUT);
        check("classify-recoverable",
                classify(new SQLRecoverableException("reconnect", "08006"))
                        == Kind.RECOVER_CONNECTION);
        check("classify-transient-connection",
                classify(new SQLTransientConnectionException("retry", "08001"))
                        == Kind.TRANSIENT_CONNECTION);
        check("classify-nontransient-connection",
                classify(new SQLNonTransientConnectionException("closed", "08003"))
                        == Kind.NON_TRANSIENT_CONNECTION);
        check("classify-transaction-rollback",
                classify(new SQLTransactionRollbackException("deadlock", "40001"))
                        == Kind.TRANSACTION_RETRY);
        check("classify-integrity",
                classify(new SQLIntegrityConstraintViolationException(
                        "duplicate", "23505")) == Kind.INTEGRITY);
        check("classify-invalid-data",
                classify(new SQLDataException("bad", "22001"))
                        == Kind.DATA);
        check("classify-authentication",
                classify(new SQLInvalidAuthorizationSpecException(
                        "denied", "28000")) == Kind.AUTHENTICATION);
        check("classify-syntax",
                classify(new SQLSyntaxErrorException("syntax", "42601"))
                        == Kind.SQL_SYNTAX);
        check("classify-feature-unsupported",
                classify(new SQLFeatureNotSupportedException("no XML","0A000"))
                        == Kind.UNSUPPORTED);
        check("classify-general-transient",
                classify(new SQLTransientException("try again"))
                        == Kind.TRANSIENT_OTHER);
        check("classify-general-nontransient",
                classify(new SQLNonTransientException("fix request"))
                        == Kind.NON_TRANSIENT_OTHER);
        check("classify-state-08-fallback",
                classify(new SQLException("lost", "08006"))
                        == Kind.RECOVER_CONNECTION);
        check("classify-state-40-fallback",
                classify(new SQLException("rollback", "40P01"))
                        == Kind.TRANSACTION_RETRY);
        check("classify-state-23-fallback",
                classify(new SQLException("duplicate", "23505"))
                        == Kind.INTEGRITY);
        check("classify-state-22-fallback",
                classify(new SQLException("too long", "22001"))
                        == Kind.DATA);
        check("classify-state-28-fallback",
                classify(new SQLException("auth", "28000"))
                        == Kind.AUTHENTICATION);
        check("classify-state-42-fallback",
                classify(new SQLException("syntax", "42601"))
                        == Kind.SQL_SYNTAX);
        check("classify-state-0A-fallback",
                classify(new SQLException("feature", "0A000"))
                        == Kind.UNSUPPORTED);
        check("classify-unknown-null-state",
                classify(new SQLException("unknown"))
                        == Kind.UNKNOWN);
        check("classify-unknown-other-state",
                classify(new SQLException("unknown", "ZZ999"))
                        == Kind.UNKNOWN);
        check("query-cancellation-not-unconditionally-timeout",
                classify(new SQLException("cancelled", "57014"))
                        == Kind.UNKNOWN);
        check("classify-specific-override-sqlstate",
                classify(new SQLIntegrityConstraintViolationException(
                        "driver subclass wins", "ZZ999"))
                        == Kind.INTEGRITY);
        SQLException outer = new SQLException("outer", "08006", 700);
        outer.setNextException(new SQLDataException("nested", "22001", 701));
        check("next-exception-linked",
                outer.getNextException() instanceof SQLDataException);
        check("diagnostics-contains-two",
                diagnosticChain(outer).size() == 2);
        check("diagnostics-root-state-and-code",
                diagnosticChain(outer).get(0).equals(
                        "SQLException|08006|700"));
        check("diagnostics-chained-state-and-code",
                diagnosticChain(outer).get(1).equals(
                        "SQLDataException|22001|701"));
        SQLWarning warning = new SQLWarning("warning", "01000");
        check("sqlwarning-is-sqlexception-subclass",
                warning instanceof SQLException);
        check("sqlwarning-class01",
                warning.getSQLState().startsWith("01"));
        BatchUpdateException batch = new BatchUpdateException(
                "batch", "23505", 10, new int[]{1, 1, Statement.EXECUTE_FAILED});
        check("batch-update-exception-counts",
                batch.getUpdateCounts().length == 3);
        check("batch-update-sqlstate",
                batch.getSQLState().equals("23505"));
        check("batch-update-state-fallback",
                classify(batch) == Kind.INTEGRITY);
    }

    static void initSchema(Connection connection) throws SQLException {
        try (Statement statement = connection.createStatement()) {
            statement.execute("""
                    CREATE TABLE documents (
                        id BIGINT PRIMARY KEY,
                        title VARCHAR(200) NOT NULL,
                        body_xml CLOB NOT NULL
                    )
                    """);
        }
    }

    static int insert(Connection connection, long id,
                      String title, String xml) throws SQLException {
        // SQLXML is transaction-scoped. Java 17: always call free();
        // SQLXML.close()/AutoCloseable support was added only in Java 26.
        SQLXML toBind = connection.createSQLXML();
        try {
            toBind.setString(xml);
            try (PreparedStatement insert = connection.prepareStatement(
                    "INSERT INTO documents(id,title,body_xml) VALUES(?,?,?)")) {
                insert.setQueryTimeout(5);
                insert.setLong(1, id);
                insert.setString(2, title);
                insert.setSQLXML(3, toBind);
                return insert.executeUpdate();
            }
        } finally {
            toBind.free();
        }
    }

    static String[] read(Connection c, long id) throws Exception {
        try (PreparedStatement ps = c.prepareStatement(
                "SELECT title,body_xml FROM documents WHERE id=?")) {
            ps.setQueryTimeout(5);
            ps.setLong(1, id);
            try (ResultSet rows = ps.executeQuery()) {
                if (!rows.next())
                    throw new AssertionError("Missing id " + id);
                String title = rows.getString("title");
                SQLXML readXml = rows.getSQLXML("body_xml");
                if (readXml == null)
                    throw new AssertionError("Unexpected NULL XML");
                String xml;
                try {
                    xml = readXml.getString();
                } finally {
                    readXml.free();
                }
                if (rows.next())
                    throw new AssertionError("Unexpected duplicate id");
                return new String[] {title, xml};
            }
        }
    }

    static void testRealJdbc() throws Exception {
        try (Connection connection =
                DriverManager.getConnection(URL, "sa", "")) {
            DatabaseMetaData meta = connection.getMetaData();
            check("real-h2-jdbc-driver-connected",
                    "H2".equals(meta.getDatabaseProductName()));
            check("database-transaction-support",
                    meta.supportsTransactions());
            check("connection-default-autocommit",
                    connection.getAutoCommit());
            initSchema(connection); // DDL stays separate from DML transaction.

            connection.setAutoCommit(false);
            check("explicit-transaction-enabled",
                    !connection.getAutoCommit());
            String xml = buildXml(TITLE, NOTE);
            try {
                check("prepared-sqlxml-insert-one-row",
                        insert(connection, 1L, TITLE, xml) == 1);
                connection.commit();
            } catch (SQLException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }

            String[] read = read(connection, 1L);
            check("db-unicode-varchar-preserved",
                    TITLE.equals(read[0]));
            Document doc = parseXmlSecurely(read[1]);
            check("db-sqlxml-xml-title-preserved",
                    TITLE.equals(text(doc, "title")));
            check("db-sqlxml-xml-note-preserved",
                    NOTE.equals(text(doc, "note")));
            check("db-sqlxml-root-preserved",
                    "document".equals(doc.getDocumentElement().getTagName()));

            SQLXML scratch = connection.createSQLXML();
            check("sqlxml-instance-created", scratch != null);
            try {
                scratch.setString(xml);
                check("sqlxml-write-then-read-at-most-once",
                        scratch.getString() != null);
            } finally {
                scratch.free();
            }
            check("sqlxml-rejects-use-after-free",
                    throwsLike(SQLException.class, scratch::getString));
            scratch.free();
            check("sqlxml-free-is-idempotent",
                    throwsLike(SQLException.class, scratch::getString));

            try {
                insert(connection, 1L, TITLE, xml);
                throw new AssertionError("Duplicate PK unexpectedly accepted");
            } catch (SQLException expected) {
                check("db-duplicate-pk-sqlstate-23",
                        expected.getSQLState() != null
                                && expected.getSQLState().startsWith("23"));
                check("db-duplicate-pk-classified-integrity",
                        classify(expected) == Kind.INTEGRITY);
                check("db-duplicate-pk-has-vendor-code",
                        expected.getErrorCode() != 0);
                connection.rollback();
            }
            check("db-rollback-keeps-committed-row",
                    read(connection, 1L)[0].equals(TITLE));

            try {
                check("prepared-second-row-insert",
                        insert(connection, 2L, "Sẽ rollback", xml) == 1);
                connection.rollback();
            } catch (SQLException failure) {
                connection.rollback();
                throw failure;
            }
            check("db-rolled-back-row-not-visible",
                    noRow(connection, 2L));
            check("db-original-row-still-present",
                    !noRow(connection, 1L));
            // SQLXML streaming path: writer must be closed before setSQLXML.
            String textWithQuotes =
                    "O'Connor'); DROP TABLE documents; -- 東京";
            String dangerousXml = buildXml(textWithQuotes, NOTE);
            SQLXML xmlStreamed = connection.createSQLXML();
            try {
                try (Writer writer = xmlStreamed.setCharacterStream()) {
                    writer.write(dangerousXml);
                }
                try (PreparedStatement insert = connection.prepareStatement(
                        "INSERT INTO documents(id,title,body_xml) VALUES(?,?,?)")) {
                    insert.setLong(1, 3L);
                    insert.setString(2, textWithQuotes);
                    insert.setSQLXML(3, xmlStreamed);
                    check("db-sqlxml-writer-stream-insert",
                            insert.executeUpdate() == 1);
                }
            } finally {
                xmlStreamed.free();
            }
            connection.commit();
            check("prepared-statement-defeats-sql-injection",
                    textWithQuotes.equals(read(connection, 3L)[0]));
            check("db-xml-stream-title-roundtrip",
                    textWithQuotes.equals(text(
                            parseXmlSecurely(read(connection, 3L)[1]),
                            "title")));
            check("db-xml-stream-note-roundtrip",
                    NOTE.equals(text(
                            parseXmlSecurely(read(connection, 3L)[1]),
                            "note")));
            try (Connection second =
                    DriverManager.getConnection(URL, "sa", "")) {
                check("other-connection-sees-committed-title",
                        TITLE.equals(read(second, 1L)[0]));
                check("other-connection-sees-committed-xml",
                        TITLE.equals(text(
                                parseXmlSecurely(read(second, 1L)[1]),
                                "title")));
                check("other-connection-sees-committed-stream-row",
                        textWithQuotes.equals(read(second, 3L)[0]));
            }

            try (PreparedStatement ps = connection.prepareStatement(
                    "SELECT title FROM documents WHERE id=?")) {
                ps.setLong(1, 1L);
                try (ResultSet rs = ps.executeQuery()) {
                    check("db-resultset-has-one-row", rs.next());
                    check("db-resultset-title-roundtrip",
                            TITLE.equals(rs.getString(1)));
                    check("db-resultset-no-extra-row", !rs.next());
                }
            }
            PreparedStatement closed =
                    connection.prepareStatement("SELECT 1");
            closed.close();
            check("db-preparedstatement-reports-closed",
                    closed.isClosed());
            connection.commit();
            check("database-connection-still-open-before-close",
                    !connection.isClosed());
        }
    }

    static boolean noRow(Connection connection, long id)
            throws SQLException {
        try (PreparedStatement ps = connection.prepareStatement(
                "SELECT id FROM documents WHERE id=?")) {
            ps.setLong(1, id);
            try (ResultSet rs = ps.executeQuery()) {
                return !rs.next();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        testPureUnicodeAndXml();
        testClassification();
        testRealJdbc();
        System.out.println("passed=" + passed);
    }
}
```

### 12.2. Cài H2 driver cho bài thực hành

H2 2.5.252 là release 2026-09 của H2. Đặt file `h2-2.5.252.jar` (dependency duy nhất) cùng thư mục source; artifact chính thức trên Maven Central:

```text
https://repo.maven.apache.org/maven2/com/h2database/h2/2.5.252/h2-2.5.252.jar
```

Maven dependency cho test scope:

```xml
<dependency>
  <groupId>com.h2database</groupId>
  <artifactId>h2</artifactId>
  <version>2.5.252</version>
  <scope>test</scope>
</dependency>
```

Production cần JDBC driver/runtime dependencies đúng phiên bản, connection pool và credentials được quản lý an toàn; H2 user `sa` không mật khẩu chỉ là ví dụ in-memory test.

### 12.3. Chạy trên Windows PowerShell

```powershell
javac --release 17 -encoding UTF-8 -cp h2-2.5.252.jar JdbcUnicodeSqlXmlDemo.java
java -cp ".;h2-2.5.252.jar" JdbcUnicodeSqlXmlDemo
```

Classpath Windows phân cách bằng dấu `;`.

### 12.4. Chạy trên Linux/macOS

```bash
javac --release 17 -encoding UTF-8 -cp h2-2.5.252.jar JdbcUnicodeSqlXmlDemo.java
java -cp ".:h2-2.5.252.jar" JdbcUnicodeSqlXmlDemo
```

Classpath POSIX dùng dấu `:`. Nếu quên driver JAR sẽ có lỗi “No suitable driver”; đó không phải SQLXML/Unicode bug.

### 12.5. Stdout đã kiểm chứng

```text
PASS utf8-roundtrip-title
PASS unicode-has-supplementary-codepoints
PASS unicode-nfc-idempotent
PASS xml-escapes-ampersand
PASS xml-escapes-less-than
PASS xml-has-locale
PASS safe-xml-title-unchanged
PASS safe-xml-note-unchanged
PASS safe-xml-document-root
PASS safe-parser-rejects-doctype
PASS safe-parser-rejects-external-entity
PASS safe-parser-rejects-malformed-xml
PASS safe-parser-rejects-size-limit
PASS classify-timeout-before-transient
PASS classify-recoverable
PASS classify-transient-connection
PASS classify-nontransient-connection
PASS classify-transaction-rollback
PASS classify-integrity
PASS classify-invalid-data
PASS classify-authentication
PASS classify-syntax
PASS classify-feature-unsupported
PASS classify-general-transient
PASS classify-general-nontransient
PASS classify-state-08-fallback
PASS classify-state-40-fallback
PASS classify-state-23-fallback
PASS classify-state-22-fallback
PASS classify-state-28-fallback
PASS classify-state-42-fallback
PASS classify-state-0A-fallback
PASS classify-unknown-null-state
PASS classify-unknown-other-state
PASS query-cancellation-not-unconditionally-timeout
PASS classify-specific-override-sqlstate
PASS next-exception-linked
PASS diagnostics-contains-two
PASS diagnostics-root-state-and-code
PASS diagnostics-chained-state-and-code
PASS sqlwarning-is-sqlexception-subclass
PASS sqlwarning-class01
PASS batch-update-exception-counts
PASS batch-update-sqlstate
PASS batch-update-state-fallback
PASS real-h2-jdbc-driver-connected
PASS database-transaction-support
PASS connection-default-autocommit
PASS explicit-transaction-enabled
PASS prepared-sqlxml-insert-one-row
PASS db-unicode-varchar-preserved
PASS db-sqlxml-xml-title-preserved
PASS db-sqlxml-xml-note-preserved
PASS db-sqlxml-root-preserved
PASS sqlxml-instance-created
PASS sqlxml-write-then-read-at-most-once
PASS sqlxml-rejects-use-after-free
PASS sqlxml-free-is-idempotent
PASS db-duplicate-pk-sqlstate-23
PASS db-duplicate-pk-classified-integrity
PASS db-duplicate-pk-has-vendor-code
PASS db-rollback-keeps-committed-row
PASS prepared-second-row-insert
PASS db-rolled-back-row-not-visible
PASS db-original-row-still-present
PASS db-sqlxml-writer-stream-insert
PASS prepared-statement-defeats-sql-injection
PASS db-xml-stream-title-roundtrip
PASS db-xml-stream-note-roundtrip
PASS other-connection-sees-committed-title
PASS other-connection-sees-committed-xml
PASS other-connection-sees-committed-stream-row
PASS db-resultset-has-one-row
PASS db-resultset-title-roundtrip
PASS db-resultset-no-extra-row
PASS db-preparedstatement-reports-closed
PASS database-connection-still-open-before-close
passed=77
```

**Validation:** `javac --release 17` PASS; OpenJDK24 + H2 2.5.252 **77/77 PASS**, thêm **4 JVM independent runs** mỗi lần **77/77 PASS**. H2 in-memory DB được tạo mới mỗi process, không có network connection, không có user data.

## 13. Hiểu kết quả kiểm thử

| Assertion | Điều đã được chứng minh |
| --- | --- |
| `utf8-roundtrip-title` | Unicode Java String → UTF-8 bytes → String khớp |
| `unicode-has-supplementary-codepoints` | Ký tự ngoài BMP có surrogate pairs |
| `xml-escapes-ampersand`, `xml-escapes-less-than` | StAX writer bảo toàn XML well-formed |
| `safe-parser-rejects-doctype` | Không chấp nhận DTD |
| `safe-parser-rejects-external-entity` | Chặn XML external entity |
| `safe-parser-rejects-malformed-xml` | Parser xác định syntax errors |
| `classify-timeout-before-transient` | SQLTimeout được ưu tiên trước transient |
| `classify-recoverable` | SQLRecoverable được phân loại riêng |
| `classify-state-23-fallback` | SQLState class 23 fallback |
| `query-cancellation-not-unconditionally-timeout` | Không suy `57014` luôn timeout |
| `diagnostics-chained-state-and-code` | JDBC next-exception chain không mất |
| `real-h2-jdbc-driver-connected` | Một JDBC database thật, không mock |
| `prepared-sqlxml-insert-one-row` | `createSQLXML/setSQLXML` thực sự lưu |
| `db-sqlxml-xml-title-preserved` | XML Unicode roundtrip |
| `sqlxml-rejects-use-after-free` | SQLXML resource invalid sau free |
| `db-duplicate-pk-classified-integrity` | DB duplicate PK đúng SQLState class |
| `db-rolled-back-row-not-visible` | DML rollback thật |
| `db-sqlxml-writer-stream-insert` | Writer streaming đóng trước execute |
| `prepared-statement-defeats-sql-injection` | SQL-like text vẫn là bound value |
| `other-connection-sees-committed-xml` | Commit visible từ connection thứ hai |
| `db-preparedstatement-reports-closed` | JDBC resource cleanup |

**Giới hạn của test:** H2 CLOB hỗ trợ SQLXML mapping nhưng không có native XML constraints/XPath/indexing. H2 test không xác minh SQL Server/PostgreSQL JDBC driver, network failover, JTA/XA, production TLS, connection pool hay performance.

## 14. Chuyển ứng dụng sang PostgreSQL native XML

PostgreSQL có native `xml` type, khác cột H2 `CLOB`. DDL tham khảo cho PostgreSQL (chưa chạy trong fixture):

```sql
CREATE TABLE documents (
  id BIGINT PRIMARY KEY,
  title TEXT NOT NULL,
  body_xml XML NOT NULL
);
```

PostgreSQL native XML type **kiểm tra XML well-formedness**, nhưng theo PostgreSQL docs **không tự validate DTD/XSD schema**. Nếu business cần schema validation, thêm application-level validation với cấu hình an toàn. PostgreSQL hỗ trợ XML “document” và “content”; default session XML option có thể ảnh hưởng conversion. XML charset handling client/server có thể chuẩn hóa encoding declaration; không đòi lexical XML string khớp hoàn toàn sau DB roundtrip. Kiểm tra **semantic parsed content**.

Khi đổi từ H2 sang PostgreSQL:
1. Dùng PostgreSQL server/pgJDBC driver thật trong môi trường test.
2. Dùng schema `XML`, kiểm tra `setSQLXML/getSQLXML` và driver behavior.
3. Kiểm tra client/server UTF-8, XML declaration, JDBC text/binary mapping.
4. Test duplicate `23505`, rollback SQLStates `40001`/`40P01`, cancellation/timeout.
5. Không sử dụng số **77/77** của H2 như bằng chứng đã kiểm thử PostgreSQL.

**SQL Server:** native `xml` và Microsoft JDBC Driver hỗ trợ SQLXML; documentation phân biệt readable vs writable SQLXML objects. Không chắc một SQLXML đọc từ ResultSet có thể truyền lại như write parameter; tạo writable object từ Connection và test theo driver.

Nếu driver không hỗ trợ SQLXML và schema chỉ có CLOB/TEXT, có thể dùng `setCharacterStream`/`setString` cùng XML parser được cấu hình đúng, **nếu business cho phép**. Nếu native XML/SQLXML bắt buộc thì phải báo unsupported, không silently degrade.

## 15. Tình huống thực tế và quyết định xử lý

### 15.1. Tiếng Việt/emoji bị biến thành `?`

Xác nhận Java String ban đầu đúng, kiểm tra encode/decode trung gian có explicit charset, DB/client/server charset/collation, column size, JDBC driver conversion và SQLState class `22`. Đừng giải quyết bằng việc loại bỏ non-ASCII hoặc ép mọi thứ sang `setNString`.

### 15.2. XML lỗi vì `&` hoặc `<`

Thay concatenation bằng XML writer, không thay giải pháp bằng SQL escaping. Kiểm tra XML root, namespace, content schema và parser DTD/XXE protections. Raw XML không tin cậy cần bound kích thước/độ sâu.

### 15.3. SQLXML unsupported

Nhận `SQLFeatureNotSupportedException` hoặc class SQLState `0A`; xác minh method nào không hỗ trợ (createSQLXML/setSQLXML/getSQLXML/getSource), schema column type, driver version. Nếu được phép fallback sang CLOB text, cần validation riêng; nếu native XML required, đổi driver/database hoặc báo incompatibility.

### 15.4. INSERT timeout, COMMIT chưa rõ outcome

Không replay non-idempotent writes. Đóng/discard connection không đáng tin, kiểm tra trạng thái qua idempotency key, reconciled reads và transaction/audit log. Retry chỉ khi business cho phép, có capped attempts và backoff.

### 15.5. Duplicate PK sau retry

SQLState `23` báo constraint, không nhất thiết một outage. Nếu key là idempotency token, kiểm tra record/payload đã có trước khi xác nhận; nếu thực sự conflict thì trả conflict.

### 15.6. SQLRecoverableException sau connection drop

Đóng connection cũ, lấy mới, không reuse ResultSet/SQLXML/PreparedStatement cũ; chỉ retry **whole transaction** có idempotency và xác minh outcome.

## 16. Lỗi phổ biến

**1. Coi Java String là UTF-8 bytes.** Nó dùng UTF-16 representation.

**2. Gọi `String.getBytes()` thiếu charset.** Chọn `StandardCharsets.UTF_8` khi cần bytes.

**3. Tự encode bytes rồi bind vào SQL text column.** Dùng `setString` hoặc stream characters.

**4. Cho rằng mọi tiếng Việt phải dùng `setNString`.** Phụ thuộc schema/driver.

**5. Dùng `String.length` làm số grapheme.** Đó là UTF-16 units.

**6. Nghĩ SQL collation giống Java equals.** Có thể khác do normalization/case folding.

**7. Ghép raw user text vào XML.** Ký tự ampersand/angle bracket làm malformed XML.

**8. Nghĩ PreparedStatement tự escape XML.** Nó chỉ xử lý SQL parameters.

**9. Ghi XML declaration `UTF-8` nhưng output thực tế là charset khác.** Dễ mojibake.

**10. Dùng DOM parser mặc định cho untrusted XML.** XXE, SSRF và DTD risk.

**11. Bỏ qua lỗi security feature rồi parse insecure.** Phải fail closed.

**12. Không giới hạn XML size, depth hoặc processing time.** XML bombs/DoS risk.

**13. Gọi `getString` trên SQLXML đã free.** Resource invalid.

**14. Gọi `setString` nhiều lần trên một SQLXML.** Write state one-shot.

**15. Coi `getString` có thể đọc vô hạn lần.** Read state có thể bị consume.

**16. Free trước `PreparedStatement.executeUpdate`.** Driver có thể chưa tiêu thụ XML.

**17. Quên đóng Writer trước `setSQLXML`.** JDBC có thể báo lỗi.

**18. Dùng `try(SQLXML x=...)` trong code Java17.** `close()`/AutoCloseable chỉ từ Java26.

**19. Coi H2 CLOB là native SQL XML.** Demo chỉ dùng SQLXML API trên CLOB.

**20. Giả định mọi database tự validate XML theo XSD/DTD.** Không đúng.

**21. Nối user input vào SQL source.** Dùng PreparedStatement placeholders.

**22. Dùng `?` cho identifiers.** PreparedStatement không bind tên table/column.

**23. Không tách DDL migrations khỏi DML transaction.** DDL commit semantics khác vendor.

**24. Coi timeout nghĩa write chưa xảy ra.** Outcome có thể unknown.

**25. Retry mọi SQLTransientException vô hạn.** Idempotency/capped retries cần thiết.

**26. Nhầm SQLRecoverableException là con của SQLTransientException.** Không phải.

**27. Catch SQLTransient trước SQLTimeout.** Mất phân loại timeout.

**28. Tách lỗi theo exception message text.** Không portable qua vendor/locale.

**29. Nhầm SQLState với vendor error code.** SQLState string, vendor code int.

**30. Coi SQLState `57014` luôn là timeout.** Có thể là cancellation khác.

**31. Bỏ qua getNextException và suppressed rollback error.** Mất thông tin chẩn đoán.

**32. Coi SQLWarning luôn là statement failure.** Warning có thể kèm success.

**33. Retry cả batch mà không đọc updateCounts.** Dễ double insert.

**34. Log XML, SQL values hoặc secrets trong diagnostics.** Rò rỉ dữ liệu.

**35. Dùng Connection/SQLXML cùng lúc từ nhiều threads không kiểm tra contract.** Driver/transaction-safety khác nhau.

**36. Đóng ResultSet/Connection muộn.** Rò rỉ cursors, locks, pool slots.

**37. Báo H2 77/77 PASS đồng nghĩa PostgreSQL 77/77 PASS.** Phải test vendor riêng.

## 17. Checklist thực hành

- [ ] JDBC driver/database được pin version và test.
- [ ] Schema/DB encoding hỗ trợ Unicode mong muốn.
- [ ] Dùng `setString`/`getString` đúng character SQL column.
- [ ] Không dùng deprecated `setUnicodeStream`.
- [ ] Explicit UTF-8 khi cần bytes.
- [ ] Validate collation, normalization và column lengths.
- [ ] Tạo XML bằng XML writer, không nối raw text.
- [ ] DOM/StAX/XML security chặn DOCTYPE/XXE/external resources.
- [ ] XML input có size/depth/time budgets.
- [ ] SQLXML support kiểm tra theo driver và column type.
- [ ] SQLXML có read/write lifetime đúng, `free` trong finally Java17.
- [ ] Đóng Writer/OutputStream trước setSQLXML/execute.
- [ ] PreparedStatement bind user values; whitelist identifiers.
- [ ] Transaction commit/rollback và cleanup đúng.
- [ ] Rollback failure không che primary error.
- [ ] SQLState/subtype/vendorCode/next chain được giữ trong diagnostics.
- [ ] Retry chỉ khi idempotent và transaction outcome được xử lý.
- [ ] Connection hỏng phải được discard theo pool policy.
- [ ] SQLXML unsupported không silent fallback khi native XML bắt buộc.
- [ ] H2 test không thay thế PostgreSQL/SQL Server integration tests.
- [ ] Không ghi raw SQL parameters/credentials/XML cá nhân vào logs.

## 18. Câu hỏi tự kiểm tra

**1. Java String lưu UTF-8 bytes?** Không, UTF-16 code units.

**2. Khi nào gọi StandardCharsets.UTF_8?** Khi chuyển String thành/đọc từ bytes.

**3. Dùng setNString cho mọi tiếng Việt?** Không, theo national SQL column type/driver.

**4. Ai escape `&` trong XML text?** XMLStreamWriter.writeCharacters.

**5. PreparedStatement bảo vệ gì?** SQL value placeholders, không XML syntax.

**6. Tạo SQLXML từ đâu?** Connection.createSQLXML().

**7. Lưu SQLXML bằng gì?** PreparedStatement.setSQLXML().

**8. Đọc SQLXML bằng gì?** ResultSet.getSQLXML rồi getString/Source/Reader.

**9. SQLXML là resource có thể đọc lại bao nhiêu lần?** Không giả định nhiều lần; read state có thể bị consume.

**10. Java17 phải dọn SQLXML bằng gì?** free() trong finally.

**11. SQLXML.close()/AutoCloseable có từ phiên bản nào?** Java SE26.

**12. Trong H2 demo cột XML là gì?** CLOB, không phải native XML type.

**13. XML untrusted nên chặn gì?** DOCTYPE/XXE/external DTD, XInclude và resource DoS.

**14. SQLTimeoutException extends gì?** SQLTransientException.

**15. SQLRecoverableException có phải SQLTransientException?** Không.

**16. SQLState `23` thường biểu thị gì?** Integrity constraint.

**17. SQLState `08` thường biểu thị gì?** Connection exception.

**18. getErrorCode có portable không?** Không, vendor-specific.

**19. SQLWarning có extends SQLException không?** Có, nhưng có warning semantics riêng.

**20. Timeout ở COMMIT có chắc chưa commit?** Không.

**21. Khi SQLRecoverableException xảy ra tối thiểu phải làm gì?** Đóng connection cũ và lấy connection mới trước khi cân nhắc retry cả transaction.

**22. Test trong bài đã dùng PostgreSQL chưa?** Chưa; H2 2.5.252 real in-memory.

**23. Có bao nhiêu assertions mỗi lượt test?** 77, qua 5 JVM executions.

## 19. Tài liệu tham khảo hiện hành

- [Oracle Java SE 26 — SQLXML](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLXML.html): read/write state, lifetime, free, `close() since 26`.
- [Oracle Java SE 26 — Connection](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Connection.html): createSQLXML, auto-commit, commit/rollback.
- [Oracle Java SE 26 — PreparedStatement](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/PreparedStatement.html): setString, setSQLXML, streaming and timeout.
- [Oracle Java SE 26 — ResultSet](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/ResultSet.html): getSQLXML and resource handling.
- [Oracle Java SE 26 — SQLException](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLException.html): SQLState, vendor code, chains.
- [Oracle Java SE 26 — SQLTransientException](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLTransientException.html): transient semantics.
- [Oracle Java SE 26 — SQLNonTransientException](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLNonTransientException.html): non-transient errors.
- [Oracle Java SE 26 — SQLRecoverableException](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLRecoverableException.html): recovery with new connection.
- [Oracle Java SE 26 — SQLTimeoutException](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLTimeoutException.html): timeout and non-fixed SQLState.
- [Oracle Java SE 26 — SQLFeatureNotSupportedException](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLFeatureNotSupportedException.html): optional features, class 0A.
- [Oracle Java SE 26 — BatchUpdateException](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/BatchUpdateException.html): update counts.
- [Oracle Java SE 26 — XMLConstants](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/XMLConstants.html): external access restrictions.
- [Oracle Java SE 26 — DocumentBuilderFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/parsers/DocumentBuilderFactory.html): secure parser configuration.
- [Oracle Java SE 26 — XMLStreamWriter](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLStreamWriter.html): XML character escaping.
- [H2 Database Engine — Version 2.5.252](https://h2database.github.io/): test DB/driver release.
- [H2 JdbcConnection](https://h2database.github.io/javadoc/org/h2/jdbc/JdbcConnection.html): H2 `createSQLXML` implementation.
- [H2 JdbcResultSet](https://h2database.github.io/javadoc/org/h2/jdbc/JdbcResultSet.html): H2 `getSQLXML`.
- [PostgreSQL XML type](https://www.postgresql.org/docs/current/datatype-xml.html): native XML well-formedness, DTD/XSD limits and encoding.
- [Microsoft JDBC Driver — Programming with SQLXML](https://learn.microsoft.com/en-us/sql/connect/jdbc/programming-with-sqlxml?view=sql-server-ver17): SQL Server XML driver semantics.

**Kết luận:** Unicode đúng phụ thuộc Java String, driver encoding và database column; XML đúng phụ thuộc escaping và parser security; SQLXML đúng phụ thuộc JDBC support, read/write state và lifetime; SQLException đúng phải được phân loại có cấu trúc và retry theo business safety. Bài thực hành chạy thật với H2, chứng minh Unicode XML roundtrip, transaction, SQL injection resistance và lỗi JDBC; đồng thời phân biệt rõ H2 CLOB và native XML của DB khác.
