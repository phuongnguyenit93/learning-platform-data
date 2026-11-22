# SQLXML: getString, setString và xử lý dữ liệu vừa bộ nhớ trong JDBC

## 1. Mục tiêu bài học

Một số ứng dụng Java lưu cấu trúc XML trong cột có kiểu SQL `XML`: chứng từ, cấu hình có schema, payload tích hợp, thông tin phân cấp hoặc tài liệu nghiệp vụ. JDBC biểu diễn giá trị này bằng **`java.sql.SQLXML`**. Trong trường hợp nội dung XML **vừa bộ nhớ**, hai method đơn giản nhất thường là:

- **`SQLXML.setString(String xml)`**: cung cấp nội dung XML ở dạng `String` cho object vừa tạo.
- **`SQLXML.getString()`**: đọc nội dung XML từ một object SQLXML do JDBC trả về, dưới dạng `String`.

Tuy dễ sử dụng, hai methods này có các ràng buộc không thể bỏ qua: mỗi `SQLXML` có **trạng thái đọc/ghi một lần**, một số driver dùng **logical pointer** tới dữ liệu DB, object có **lifetime gắn với transaction**, XML lớn có thể tiêu tốn nhiều RAM, XML không hợp lệ có thể chỉ bị báo lỗi khi statement chạy, và XML đến từ nguồn không tin cậy phải được parse an toàn.

Bài tập trung vào đề bài **“getString, setString và xử lý dữ liệu vừa bộ nhớ”** thuộc chủ đề **SQLXML**. Nội dung chỉ dùng kiến thức JDBC/JAXP còn hiện hành, phân biệt Java 17 với những thay đổi có trong Java SE 26.

Sau bài, bạn có thể:

1. Tạo `SQLXML` bằng `Connection.createSQLXML()`, ghi bằng `setString`, bind bằng `PreparedStatement.setSQLXML`.
2. Đọc bằng `ResultSet.getSQLXML` rồi gọi `getString`, xử lý SQL `NULL`.
3. Hiểu **at-most-once read/write state**: không gọi `getString` hai lần hay `setString` hai lần trên cùng SQLXML.
4. Giải phóng tài nguyên bằng `free()`; biết `close()/AutoCloseable` chỉ xuất hiện ở Java SE 26, nên code target Java 17 không dùng `try (SQLXML ...)`.
5. Định nghĩa “vừa bộ nhớ” bằng giới hạn kích thước **có chủ đích**, tránh nhầm UTF-16 code units với UTF-8 bytes.
6. Escape dữ liệu người dùng khi xây XML, validate cú pháp, cấm external entities/DTD cho untrusted XML.
7. Phân biệt `String` APIs với `getCharacterStream()/setCharacterStream()` và `getSource()/setResult()` khi XML lớn hơn.
8. Kiểm thử supported/unsupported paths, one-shot, free, SQL NULL, kết nối đã đóng, và database driver thật.

**Ví dụ đầy đủ** ở phần 8 là Java 17+, không cần DB, không thêm dependencies. Nó sử dụng Java dynamic proxies để mô phỏng `Connection`, `PreparedStatement`, `ResultSet` và `SQLXML`. Đã biên dịch `javac --release 17`, chạy trên OpenJDK 24 với **27/27 assertions PASS**. Mọi code có SQL database thật được đánh dấu riêng là **snippet tích hợp**, không tự nhận là đã test với PostgreSQL/Oracle/SQL Server.

## 2. `java.sql.SQLXML` là gì?

`SQLXML` là mapping của kiểu SQL `XML` sang Java. Một database có thể lưu XML dưới dạng văn bản, binary XML hoặc representation được tối ưu hóa. JDBC cho phép ứng dụng xử lý dữ liệu thông qua giao diện chuẩn, thay vì giả định database lưu XML bằng UTF-8 text nguyên xi.

Theo Java SE 26 Javadoc:

- `SQLXML` có thể là **logical pointer** đến giá trị XML, không nhất thiết là bản sao dữ liệu trong JVM.
- Object `SQLXML` thường hợp lệ trong **transaction đã tạo ra nó**.
- Có thể đọc/ghi XML thông qua `String`, `Reader/Writer`, binary streams, `Source/Result`.
- Các thao tác đọc và ghi chỉ được thực hiện **tối đa một lần** theo conceptual state machine.
- Phải giải phóng tài nguyên với `free()` hoặc `close()` ở các Java targets hỗ trợ method mới.

Các entry points liên quan:

| API | Vai trò | Lưu ý |
| --- | --- | --- |
| `Connection.createSQLXML()` | Tạo SQLXML **trống** cho đường ghi | Driver có thể báo unsupported |
| `SQLXML.setString(xml)` | Đặt nội dung XML từ `String` | Chỉ ghi một lần, có thể trì hoãn validation |
| `PreparedStatement.setSQLXML(index, xml)` | Bind SQLXML vào SQL parameter | Phải execute trước khi giải phóng object nếu driver cần nội dung |
| `ResultSet.getSQLXML(index/label)` | Đọc SQL XML column dưới dạng SQLXML | Có thể trả `null` nếu SQL NULL |
| `SQLXML.getString()` | Trả một `String` chứa XML | Có thể materialize toàn bộ XML trong heap; chỉ đọc một lần |
| `SQLXML.getCharacterStream()` | Lấy `Reader` cho XML | Không đảm bảo driver không buffering |
| `SQLXML.setCharacterStream()` | Lấy `Writer` để cung cấp XML | Phải đóng stream trước khi execute |
| `SQLXML.getSource(SourceClass)` | Đưa XML sang JAXP `Source` | Có thể tối ưu representation nhưng phải bảo vệ XML parser |
| `SQLXML.setResult(ResultClass)` | Ghi thông qua JAXP `Result` | API cho DOM/SAX/StAX/Stream |
| `SQLXML.free()` | Giải phóng resources | Gọi sau khi đã dùng xong |
| `SQLXML.close()` | Đóng resources, API mới trong Java SE 26 | **Không** có trong `SQLXML` target Java 17 |

`PreparedStatement` parameter indexes và `ResultSet` column indexes bắt đầu từ **1**. Với label, nên dùng alias duy nhất như `xml_doc` trong query.

### SQLXML khác XML string column như thế nào?

Một cột `VARCHAR`/`CLOB` chứa chuỗi XML vẫn là kiểu text của database; `SQLXML` tương ứng với kiểu **SQL `XML`** có semantics do DB/driver quyết định. Không phải JDBC driver nào cũng hỗ trợ `SQLXML`, ngay cả khi database có thể lưu XML trong text column.

Nếu DB sử dụng cột text `VARCHAR/CLOB` thì `PreparedStatement.setString`/`setCharacterStream` phù hợp với text type hơn; không mặc định gọi `setSQLXML` cho mọi cột chứa dấu `<` và `>`.

## 3. Hợp đồng một lần đọc, một lần ghi

`SQLXML` không phải một mutable StringBuilder để gọi setter/getter tùy ý. Javadoc Java SE 17/26 nêu **reading and writing XML values to/from an SQLXML object can happen at most once**.

### 3.1. Đường ghi

`SQLXML` do `Connection.createSQLXML()` trả về **khởi đầu trống**, cho phép ứng dụng điền dữ liệu:

```java
SQLXML value = connection.createSQLXML();
value.setString("<note><title>Xin chào</title></note>");
```

Dòng trên là snippet cần một `Connection` thật. Sau `setString`:
- Object trở thành **not writable**: không gọi tiếp `setString` hoặc `setCharacterStream`.
- Driver **có thể** đồng thời chuyển object thành **not readable**. Vì thế **đừng trông đợi** `value.getString()` ngay sau `value.setString(...)` sẽ hoạt động.
- Bind object vào `PreparedStatement.setSQLXML` rồi execute; chỉ sau đó mới `free()`.
- Nếu XML invalid, lỗi có thể ném ngay ở `setString` **hoặc** khi statement execute.

**Không làm:**

```java
SQLXML value = connection.createSQLXML();
value.setString(firstXml);
value.setString(secondXml); // Sai: object đã ghi một lần.
```

### 3.2. Đường đọc

Một object lấy từ ResultSet đã có XML để đọc:

```java
SQLXML value = resultSet.getSQLXML("xml_doc");
if (value != null) {
    String xml = value.getString(); // Đọc đúng một lần.
}
```

Sau `getString`, object thành **not readable**. Gọi thêm `getString`, `getCharacterStream` hoặc `getSource` trên object đó có thể ném `SQLException`. Nếu cần nhiều phép xử lý, giữ **`String` đã lấy** trong scope đủ ngắn, hoặc thiết kế query lấy SQLXML object khác; không gọi getter lần nữa.

Sai:

```java
String first = value.getString();
String second = value.getString(); // Không portable, có thể SQLException.
```

Đúng:

```java
String xml = value.getString();
String copyForAnotherStep = xml; // Dùng lại String nếu vừa bộ nhớ.
```

Hai dòng đúng **không tạo bản sao deep copy** của String; chúng chỉ giữ references tới cùng immutable String. Đó là ưu điểm về logic, nhưng String vẫn chiếm bộ nhớ tương ứng.

### 3.3. Trạng thái conceptual

| State | Operation | State sau operation |
| --- | --- | --- |
| Writable/new | `setString(xml)` | **Not writable**; có thể not readable |
| Writable/new | `setCharacterStream()` | **Not writable**; Writer phải đóng |
| Readable | `getString()` | **Not readable**; có thể not writable |
| Readable | `getCharacterStream()` | **Not readable**; Reader phải đóng |
| Readable | `getSource(...)` | **Not readable**; parser có thể xử lý tiếp Source |
| Any valid state | `free()` | Resource released |
| Any valid state (Java SE 26+) | `close()` | Resource released |

State machine là **contract của JDBC**, không phải implementation fields dùng trong DB thật. Javadoc có những trường hợp driver có thể làm trạng thái còn lại không dùng được sau một operation; code portable phải giả định **mỗi SQLXML một đường sử dụng**.

## 4. `free()` và thay đổi ở Java SE 26

Một chi tiết version-sensitive quan trọng:

- Trong **Java 17**, `SQLXML` **không extends `AutoCloseable`**, không có method `close()` trong interface. Vì vậy `try (SQLXML value = ...)` **không biên dịch** với `javac --release 17`. Hãy dùng `free()` trong `finally`.
- Trong **Java SE 26**, `SQLXML` **extends `AutoCloseable`** và có default `close()` gọi `free()`. Javadoc đánh dấu `close()` **Since: 26**. Khi target Java SE 26+, có thể dùng try-with-resources với `SQLXML`, nhưng vẫn phải quản lý transaction/ResultSet/Statement scopes.

Ví dụ tương thích Java 17:

```java
SQLXML data = connection.createSQLXML();
try {
    data.setString(xml);
    try (PreparedStatement ps = connection.prepareStatement(
            "INSERT INTO docs(id, xml_doc) VALUES (?, ?)")) {
        ps.setLong(1, id);
        ps.setSQLXML(2, data);
        ps.executeUpdate();
    }
} finally {
    data.free();
}
```

Đây là **snippet tích hợp**; `connection`, `xml`, `id` phải được khai báo và DB hỗ trợ SQL `XML`. Method phải xử lý `SQLException`. Trong Java 17, dùng `try-with-resources` với `PreparedStatement` được, nhưng không dùng với `SQLXML`.

Từ Java 26, có thể viết dạng:

```java
// Java SE 26+ ONLY:
try (SQLXML data = connection.createSQLXML()) {
    data.setString(xml);
    // Bind và execute trước khi kết thúc scope SQLXML.
}
```

Không lấy version **runtime** của IDE làm căn cứ duy nhất: nếu project target `--release 17`, compiler phải tuân API Java 17 ngay cả khi chạy JDK 26.

### `free()` có đóng ResultSet/Connection không?

Không. `free()` giải phóng tài nguyên của **SQLXML object**, không thay thế `ResultSet.close`, `PreparedStatement.close` hoặc `Connection.close`. Mỗi JDBC resource có phạm vi sở hữu riêng. Kết nối do pool mượn vẫn phải close borrowed logical handle theo policy.

`SQLXML.free()` sau một lần free thường có no-effect nếu đã closed (theo tài liệu), nhưng **không** nên dùng object đó tiếp. Các thao tác khác sau khi đã đóng phải dẫn tới `SQLException` theo contract hiện hành.

## 5. Dữ liệu “vừa bộ nhớ” là bao nhiêu?

Không có con số chung như “XML dưới 1 MB luôn an toàn”. Với `setString`/`getString`, bạn phải xét:
- Giới hạn payload của ứng dụng (bytes, chars, nodes, nesting depth).
- Nhiều bản sao cùng tồn tại: input string, escaped string, SQLXML driver buffer, XML parser document tree, temporary output.
- Runtime heap của JVM, concurrent requests và GC pressure.
- Driver có buffering/copy không, DB/network behavior.
- Tập XML gồm ASCII, tiếng Việt, emoji và các code points khác.

**`String.length()` đếm UTF-16 code units**, không đếm Unicode code points hay UTF-8 bytes. Ví dụ:

```java
"🌿".length() == 2;
"🌿".getBytes(StandardCharsets.UTF_8).length == 4;
```

Trong Java 17+ với import `java.nio.charset.StandardCharsets`, hai biểu thức trên đều true. Tiếng Việt có dấu có thể có số UTF-8 bytes nhiều hơn `String.length()`.

### 5.1. Một giới hạn bytes phù hợp fixture

Trong demo, giả lập budget **32 KiB** chỉ để minh họa:

```java
private static final int MAX_UTF8_BYTES = 32 * 1024;

private static String withinBudget(String xml) {
    if (xml.length() > MAX_UTF8_BYTES
            || xml.getBytes(StandardCharsets.UTF_8).length
                    > MAX_UTF8_BYTES) {
        throw new IllegalArgumentException("XML exceeds budget");
    }
    return xml;
}
```

**Vì sao check chars trước?** Với mỗi UTF-16 code unit, UTF-8 output cho chuỗi hợp lệ có thể có nhiều bytes, nên một input đã dài hơn byte budget chắc chắn không vừa trong budget. Short-circuit giúp tránh allocation byte array cho input quá dài trong fixture. Tuy nhiên `getBytes` **vẫn cấp phát một byte array** để tính độ dài. Cách này hợp lý **cho dữ liệu đã được giới hạn nhỏ**, không phải giải pháp stream cho payload nhiều GB.

**Budget phải chọn theo sản phẩm.** 32 KiB không phải giới hạn JDBC, SQLXML hay PostgreSQL/Oracle. Một sản phẩm có thể chọn 64 KiB, 1 MiB, hoặc threshold khác dựa trên benchmark và memory budget. Đừng suy ngưỡng của tutorial là cấu hình production.

### 5.2. Guard trước và sau khi đọc

- Khi **input** là String đã ở JVM, check size **trước `createSQLXML`/`setString`** sẽ tránh gửi payload quá lớn.
- Khi **output** từ DB, gọi `SQLXML.getString()` có thể đã materialize toàn bộ nội dung trước khi bạn kiểm tra. **Kiểm tra size sau `getString()` không thể bảo đảm giới hạn peak memory**.
- Nếu database có thể trả XML lớn không kiểm soát, dùng database-level length/filtering/query limits, reader/stream path và parser bounds; thiết kế memory/timeout/cancellation policy.

Không khẳng định `getCharacterStream` luôn streaming thật: JDBC driver **có thể tự buffer** dữ liệu. Cần kiểm thử heap/memory trên driver thực tế.

### 5.3. String là Unicode characters, không phải XML bytes nguyên thủy

`getString()` trả **representation của XML value dưới dạng Java String**. Nếu DB từng nhận XML với encoding declaration khác, comment/whitespace/namespace representation cũng có thể được driver/DB xử lý theo cách riêng. Không dùng byte-for-byte equality như một tiêu chuẩn bắt buộc cho mọi database sau round-trip; so XML semantics/canonicalization theo yêu cầu sản phẩm.

## 6. Xây XML từ dữ liệu người dùng: escape và parse an toàn

Nếu ghép text vào XML:

```java
String unsafe = "<title>" + userText + "</title>";
```

mà `userText` chứa `&` hoặc `<`, XML sẽ hỏng hoặc bị hiểu thành markup. Tối thiểu khi đặt dữ liệu vào **element text**, escape:

```java
static String escapeText(String s) {
    return s.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;");
}
```

**Đây là helper chỉ dành cho XML text nodes**. Nó không phải XML serializer tổng quát: còn quy tắc attributes/quotes, control characters, character encoding, namespaces và cấu trúc tài liệu. Với dữ liệu phức tạp, ưu tiên tạo XML bằng DOM/StAX writer hoặc một XML library đáng tin cậy thay vì tự nối chuỗi.

Ví dụ:

```java
String title = "Xin chào & Java <17> 🌿";
String xml = "<doc><title>" + escapeText(title)
        + "</title><count>42</count></doc>";
```

XML tạo ra có dạng:

```xml
<doc><title>Xin chào &amp; Java &lt;17&gt; 🌿</title><count>42</count></doc>
```

XML parser sau đó sẽ đọc text node ra chính xác `Xin chào & Java <17> 🌿`.

### 6.1. `getString` không tự chống XXE

Một chuỗi có cú pháp XML có thể chứa DTD và external entity references. Nếu ứng dụng **parse** XML chưa được tin cậy bằng DOM/SAX/StAX mà bật external entity resolution, nó có nguy cơ XXE/SSRF/local-file read. `getString()` chỉ là **API đọc text**; nó không tự làm XML an toàn.

OWASP hiện hành khuyến nghị:
- Cấm DOCTYPE nếu không cần DTD.
- Chặn external DTDs, external entities, schemas và stylesheet access theo API thích hợp.
- Dùng `FEATURE_SECURE_PROCESSING` kết hợp access restrictions, **không coi nó là thay thế** cho việc cấm external entities.
- Không nuốt exceptions khi cấu hình security bị từ chối.
- Giới hạn kích thước, nesting depth, số entity expansions và processing time theo trust boundary.

### 6.2. DOM parser đã harden cho ví dụ Java 17

```java
static Document secureParse(String xml) throws Exception {
    DocumentBuilderFactory f =
            DocumentBuilderFactory.newDefaultInstance();
    f.setNamespaceAware(true);
    f.setXIncludeAware(false);
    f.setFeature(
            "http://apache.org/xml/features/disallow-doctype-decl",
            true);
    f.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
    f.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
    f.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

    DocumentBuilder builder = f.newDocumentBuilder();
    builder.setErrorHandler(new DefaultHandler() {
        @Override
        public void fatalError(SAXParseException error)
                throws SAXException {
            throw error;
        }
    });
    return builder.parse(new InputSource(new StringReader(xml)));
}
```

Method trên là một phần của chương trình đầy đủ ở phần 8. `newDefaultInstance` dùng JAXP implementation của JDK; với provider khác bạn phải kiểm tra hỗ trợ các security features. Nếu cấu hình thất bại, chương trình **fail closed** thay vì tiếp tục parse untrusted XML.

Trong ví dụ, một XML chứa `<!DOCTYPE ...>` và một XML có end tag sai đều bị từ chối bằng `SAXException`. Không gọi URL/file access để “kiểm tra” XXE.

### 6.3. XML schema và nghiệp vụ

XML **well-formed** không tự đồng nghĩa hợp lệ với **XSD** hoặc nghiệp vụ. Nếu sản phẩm yêu cầu schema, dùng `SchemaFactory`/`Validator` cấu hình an toàn, giới hạn external schema access. Nếu người dùng chỉ cần lưu một XML fragment, kiểm tra DB có yêu cầu document root không; XML value semantics phụ thuộc database/SQL type.

Đừng tự tin rằng `SQLXML.setString` sẽ validate đủ cả schema/security trước khi execute. Javadoc nói XML invalid có thể gây `SQLException` ngay tại setter **hoặc lúc execute**. Kiểm tra ứng dụng trước khi gửi có thể nâng UX, nhưng database vẫn là nguồn kiểm tra cuối.

## 7. Quy trình JDBC insert và select dữ liệu XML vừa bộ nhớ

### 7.1. Viết SQLXML

Trình tự thực tế:

```text
Input data (đã validate/escape)
      |
      v
String XML, within approved budget
      |
      v
Connection.createSQLXML() -> empty SQLXML
      |
      v
SQLXML.setString(xml) -> one write
      |
      v
PreparedStatement.setSQLXML(index, value)
      |
      v
executeUpdate()
      |
      v
SQLXML.free() trong finally
```

Trong Java 17:

```java
SQLXML sqlxml = conn.createSQLXML();
try {
    sqlxml.setString(xml);
    try (PreparedStatement ps = conn.prepareStatement(
            "INSERT INTO docs (id, payload) VALUES (?, ?)")) {
        ps.setInt(1, id);
        ps.setSQLXML(2, sqlxml);
        ps.executeUpdate();
    }
} finally {
    sqlxml.free();
}
```

Đây là **snippet tích hợp**, không standalone. Cần `conn` thật, kiểu SQL XML trên column `payload` và JDBC driver hỗ trợ `SQLXML`. `id`/`xml` là biến ứng dụng. **SQL syntax và XML data type là database-dependent**; không có database thật trong demo của bài.

**Chú ý:** Không `free()` trước `executeUpdate()` vì driver có thể cần đọc SQLXML khi execute, chứ không phải ngay lúc `setSQLXML`.

### 7.2. Đọc SQLXML

```java
try (PreparedStatement ps = conn.prepareStatement(
        "SELECT payload FROM docs WHERE id = ?")) {
    ps.setInt(1, id);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            SQLXML value = rs.getSQLXML("payload");
            if (value != null) {
                try {
                    String xml = value.getString();
                    // Xử lý xml trong memory budget.
                } finally {
                    value.free();
                }
            }
        }
    }
}
```

**SQL `NULL`:** `ResultSet.getSQLXML` có thể trả `null` nếu cột mang SQL NULL. Không gọi `value.free()` hoặc `value.getString()` khi value null.

**Một lần đọc:** Biến `xml` là String đã materialize. Không gọi lại `value.getString` sau đó.

**Kết nối và transaction:** Với SQLXML logical pointer, cần xử lý trước khi transaction chứa object kết thúc. Nếu ResultSet/PreparedStatement bị đóng hoặc connection trả về pool trước khi SQLXML được đọc hết, behavior có thể fail. Hãy xử lý trong nested resource scopes.

## 8. Chương trình Java 17+ tự chạy: 27 phép kiểm tra

Chương trình này không kết nối DB. Nó dùng **dynamic proxy** để triển khai đúng **những method cần test** của JDBC interfaces, còn những methods khác trả `SQLFeatureNotSupportedException`. Nó không phải driver thật và **không** cam kết các `Reader/Writer/Source/Result` methods đầy đủ như một JDBC driver có SQLXML support. Mục tiêu là mô phỏng **getString/setString, one-shot states, bind, read và cleanup** trong môi trường không cần database.

Sơ đồ:

```text
MiniDb (in-memory mock)
  └── Connection proxy
      ├── createSQLXML() -> XML object writable
      │      └── setString(xml) one time
      ├── PreparedStatement proxy (INSERT)
      │      ├── setInt(...)
      │      ├── setSQLXML(...)
      │      └── executeUpdate() -> one row
      └── PreparedStatement proxy (SELECT)
             └── ResultSet proxy
                    └── getSQLXML("payload")
                           └── SQLXML object readable
                                  └── getString() one time
```

### 8.1. Lưu file `SqlXmlStringDemo.java`

```java
import java.io.StringReader;
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;
import java.sql.SQLXML;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Document;
import org.xml.sax.InputSource;
import org.xml.sax.SAXException;
import org.xml.sax.SAXParseException;
import org.xml.sax.helpers.DefaultHandler;

public final class SqlXmlStringDemo {
    private static final int MAX_UTF8_BYTES = 32 * 1024;
    private static int passed;

    private static void check(String label, boolean ok) {
        if (!ok) throw new AssertionError(label);
        System.out.println("PASS " + label);
        passed++;
    }

    @FunctionalInterface
    interface SqlCall {
        void run() throws SQLException;
    }

    private static boolean sqlError(SqlCall action) {
        try {
            action.run();
            return false;
        } catch (SQLException expected) {
            return true;
        }
    }

    private static String escapeText(String s) {
        return s.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;");
    }

    private static String withinBudget(String xml) {
        if (xml.length() > MAX_UTF8_BYTES
                || xml.getBytes(StandardCharsets.UTF_8).length
                        > MAX_UTF8_BYTES) {
            throw new IllegalArgumentException("XML exceeds budget");
        }
        return xml;
    }

    static Document secureParse(String xml) throws Exception {
        DocumentBuilderFactory f =
                DocumentBuilderFactory.newDefaultInstance();
        f.setNamespaceAware(true);
        f.setXIncludeAware(false);
        f.setFeature(
                "http://apache.org/xml/features/disallow-doctype-decl",
                true);
        f.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        f.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        f.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        DocumentBuilder builder = f.newDocumentBuilder();
        builder.setErrorHandler(new DefaultHandler() {
            @Override
            public void fatalError(SAXParseException error)
                    throws SAXException {
                throw error;
            }
        });

        return builder.parse(
                new InputSource(new StringReader(xml)));
    }

    static final class XmlState implements InvocationHandler {
        private String xml;
        private boolean canRead;
        private boolean canWrite;
        private boolean freed;

        XmlState(String xml, boolean canRead, boolean canWrite) {
            this.xml = xml;
            this.canRead = canRead;
            this.canWrite = canWrite;
        }

        static SQLXML output() {
            return new XmlState(null, false, true).proxy();
        }

        static SQLXML input(String xml) {
            return new XmlState(xml, true, false).proxy();
        }

        SQLXML proxy() {
            return (SQLXML) Proxy.newProxyInstance(
                    SqlXmlStringDemo.class.getClassLoader(),
                    new Class<?>[] { SQLXML.class },
                    this);
        }

        String snapshotForStatement() throws SQLException {
            if (freed || xml == null) {
                throw new SQLException(
                        "SQLXML has no complete value");
            }
            return xml;
        }

        @Override
        public Object invoke(Object p, Method m, Object[] args)
                throws SQLException {
            String n = m.getName();

            if (m.getDeclaringClass() == Object.class) {
                return switch (n) {
                    case "toString" -> "sqlxml-mock";
                    case "hashCode" ->
                            System.identityHashCode(p);
                    case "equals" -> p == args[0];
                    default ->
                            throw new IllegalStateException(n);
                };
            }

            if (n.equals("free")) {
                freed = true;
                canRead = false;
                canWrite = false;
                xml = null;
                return null;
            }

            if (freed) {
                throw new SQLException("SQLXML already freed");
            }

            if (n.equals("setString")) {
                if (!canWrite) {
                    throw new SQLException("not writable");
                }
                xml = (String) args[0];
                canWrite = false;
                canRead = false;
                return null;
            }

            if (n.equals("getString")) {
                if (!canRead) {
                    throw new SQLException("not readable");
                }
                canRead = false;
                return xml;
            }

            throw new SQLFeatureNotSupportedException(
                    "Mock only implements string access: " + n);
        }
    }

    @SuppressWarnings("unchecked")
    private static <T> T proxy(
            Class<T> api, InvocationHandler h) {
        return (T) Proxy.newProxyInstance(
                SqlXmlStringDemo.class.getClassLoader(),
                new Class<?>[] { api },
                h);
    }

    static final class MiniDb {
        private String stored;
        private int storedId = -1;
        private final boolean supportsXml;

        MiniDb(boolean supportsXml) {
            this.supportsXml = supportsXml;
        }

        Connection connection() {
            return proxy(Connection.class,
                    new InvocationHandler() {
                boolean closed;

                @Override
                public Object invoke(
                        Object p, Method m, Object[] args)
                        throws SQLException {
                    return switch (m.getName()) {
                        case "close" -> {
                            closed = true;
                            yield null;
                        }
                        case "isClosed" -> closed;
                        default -> {
                            if (closed) {
                                throw new SQLException(
                                        "closed connection");
                            }
                            if (m.getName().equals(
                                    "createSQLXML")) {
                                if (!supportsXml) {
                                    throw new SQLFeatureNotSupportedException(
                                            "SQLXML unsupported");
                                }
                                yield XmlState.output();
                            }
                            if (m.getName().equals(
                                    "prepareStatement")) {
                                yield statement(
                                        (String) args[0]);
                            }
                            throw new SQLFeatureNotSupportedException(
                                    m.getName());
                        }
                    };
                }
            });
        }

        PreparedStatement statement(String sql) {
            boolean insert = sql.equals(
                    "INSERT INTO docs (id, payload) VALUES (?, ?)");
            boolean select = sql.equals(
                    "SELECT payload FROM docs WHERE id = ?");

            if (!insert && !select) {
                throw new IllegalArgumentException(
                        "Unknown SQL for mock");
            }

            return proxy(PreparedStatement.class,
                    new InvocationHandler() {
                boolean closed;
                Integer id;
                SQLXML bound;

                @Override
                public Object invoke(
                        Object p, Method m, Object[] args)
                        throws SQLException {
                    return switch (m.getName()) {
                        case "close" -> {
                            closed = true;
                            yield null;
                        }
                        case "isClosed" -> closed;
                        default -> {
                            if (closed) {
                                throw new SQLException(
                                        "statement closed");
                            }
                            yield switch (m.getName()) {
                                case "setInt" -> {
                                    if ((Integer) args[0] != 1) {
                                        throw new SQLException(
                                                "parameter");
                                    }
                                    id = (Integer) args[1];
                                    yield null;
                                }

                                case "setSQLXML" -> {
                                    if (!insert
                                            || (Integer) args[0] != 2) {
                                        throw new SQLException(
                                                "parameter");
                                    }
                                    bound = (SQLXML) args[1];
                                    yield null;
                                }

                                case "executeUpdate" -> {
                                    if (!insert
                                            || id == null
                                            || bound == null) {
                                        throw new SQLException(
                                                "invalid insert");
                                    }
                                    XmlState state = (XmlState)
                                            Proxy.getInvocationHandler(
                                                    bound);
                                    stored =
                                            state.snapshotForStatement();
                                    storedId = id;
                                    yield 1;
                                }

                                case "executeQuery" -> {
                                    if (!select || id == null) {
                                        throw new SQLException(
                                                "invalid select");
                                    }
                                    yield result(id);
                                }

                                default ->
                                        throw new SQLFeatureNotSupportedException(
                                                m.getName());
                            };
                        }
                    };
                }
            });
        }

        ResultSet result(int id) {
            return proxy(ResultSet.class,
                    new InvocationHandler() {
                boolean closed;
                boolean visited;
                boolean row;

                @Override
                public Object invoke(
                        Object p, Method m, Object[] args)
                        throws SQLException {
                    return switch (m.getName()) {
                        case "close" -> {
                            closed = true;
                            yield null;
                        }
                        case "isClosed" -> closed;
                        default -> {
                            if (closed) {
                                throw new SQLException(
                                        "result closed");
                            }
                            yield switch (m.getName()) {
                                case "next" -> {
                                    row = !visited
                                            && (id == storedId
                                                || id == 8);
                                    visited = true;
                                    yield row;
                                }

                                case "getSQLXML" -> {
                                    if (!row) {
                                        throw new SQLException(
                                                "no row");
                                    }
                                    Object col = args[0];
                                    if (!(col.equals(1)
                                            || col.equals(
                                                    "payload"))) {
                                        throw new SQLException(
                                                "unknown column");
                                    }
                                    yield id == 8
                                            ? null
                                            : XmlState.input(stored);
                                }

                                default ->
                                        throw new SQLFeatureNotSupportedException(
                                                m.getName());
                            };
                        }
                    };
                }
            });
        }
    }

    public static void main(String[] args)
            throws Exception {

        String title = "Xin chào & Java <17> 🌿";
        String xml = "<doc><title>"
                + escapeText(title)
                + "</title><count>42</count></doc>";

        check("escaped-ampersand",
                xml.contains("&amp;"));
        check("escaped-angle-brackets",
                xml.contains("&lt;17&gt;"));
        check("unicode-preserved",
                xml.contains("🌿"));
        check("unicode-utf8-differs-from-chars",
                xml.getBytes(StandardCharsets.UTF_8).length
                        > xml.length());
        check("emoji-two-utf16-units",
                "🌿".length() == 2
                && "🌿".getBytes(StandardCharsets.UTF_8)
                        .length == 4);
        check("budget-accept",
                withinBudget(xml).equals(xml));

        boolean largeRejected = false;
        try {
            withinBudget(
                    "<doc>" + "x".repeat(33000) + "</doc>");
        } catch (IllegalArgumentException expected) {
            largeRejected = true;
        }
        check("budget-reject", largeRejected);

        Document document = secureParse(xml);
        check("xml-root",
                document.getDocumentElement()
                        .getTagName().equals("doc"));
        check("xml-text",
                document.getElementsByTagName("title")
                        .item(0).getTextContent()
                        .equals(title));
        check("xml-count",
                document.getElementsByTagName("count")
                        .item(0).getTextContent()
                        .equals("42"));

        boolean doctypeRejected = false;
        try {
            secureParse(
                    "<!DOCTYPE d [<!ENTITY e SYSTEM "
                    + "\"file:///no-secret\">]>"
                    + "<d>&e;</d>");
        } catch (SAXException expected) {
            doctypeRejected = true;
        }
        check("doctype-rejected", doctypeRejected);

        boolean malformedRejected = false;
        try {
            secureParse("<doc><title></doc>");
        } catch (SAXException expected) {
            malformedRejected = true;
        }
        check("malformed-xml-rejected",
                malformedRejected);

        MiniDb db = new MiniDb(true);
        Connection c = db.connection();

        try {
            SQLXML outgoing = c.createSQLXML();
            try {
                outgoing.setString(xml);
                check("setstring-once",
                        sqlError(
                                () -> outgoing.setString(xml)));
                check("written-object-not-readable-in-mock",
                        sqlError(outgoing::getString));

                try (PreparedStatement ps =
                        c.prepareStatement(
                                "INSERT INTO docs (id, payload)"
                                + " VALUES (?, ?)")) {
                    ps.setInt(1, 7);
                    ps.setSQLXML(2, outgoing);
                    check("jdbc-insert-one",
                            ps.executeUpdate() == 1);
                }
            } finally {
                outgoing.free();
                outgoing.free();
            }

            check("freed-outgoing-rejected",
                    sqlError(outgoing::getString));

            try (PreparedStatement ps =
                    c.prepareStatement(
                            "SELECT payload FROM docs WHERE id = ?")) {
                ps.setInt(1, 7);

                try (ResultSet rs = ps.executeQuery()) {
                    check("jdbc-row-exists", rs.next());

                    SQLXML incoming =
                            rs.getSQLXML("payload");
                    check("getsqlxml-not-null",
                            incoming != null);

                    try {
                        check("incoming-read-only",
                                sqlError(
                                        () -> incoming.setString(xml)));

                        String fromDb = incoming.getString();
                        check("getstring-equal",
                                fromDb.equals(xml));
                        check("second-read-rejected",
                                sqlError(incoming::getString));
                    } finally {
                        incoming.free();
                    }

                    check("freed-incoming-rejected",
                            sqlError(incoming::getString));
                    check("resultset-exhausted",
                            !rs.next());
                }
            }

            try (PreparedStatement ps =
                    c.prepareStatement(
                            "SELECT payload FROM docs WHERE id = ?")) {
                ps.setInt(1, 8);

                try (ResultSet rs = ps.executeQuery()) {
                    check("sql-null-row", rs.next());
                    check("sql-null-returns-null",
                            rs.getSQLXML(1) == null);
                }
            }
        } finally {
            c.close();
        }

        check("connection-closed", c.isClosed());

        MiniDb unsupported = new MiniDb(false);
        try (Connection noXml = unsupported.connection()) {
            check("unsupported-create-sqlxml",
                    sqlError(noXml::createSQLXML));
        }

        System.out.println("passed=" + passed);
    }
}
```

### 8.2. Build và chạy

Tại thư mục chứa file `SqlXmlStringDemo.java`:

```bash
javac --release 17 -encoding UTF-8 SqlXmlStringDemo.java
java SqlXmlStringDemo
```

Hai lệnh dùng được trên Linux/macOS hoặc Windows PowerShell có JDK 17+ trên PATH.

**Không dùng `try (SQLXML ...)` trong file này** vì chương trình target Java 17. Trong `MiniDb`, XML values được mô phỏng bằng proxy: test `setString` thì mock chuyển sang not writable và not readable; test `getString` thì chuyển sang not readable; `free()` xóa dữ liệu và đánh dấu object đã được giải phóng. Đây là một lựa chọn mock phù hợp với contract, không có nghĩa driver thật phải áp dụng tất cả flags y hệt.

### 8.3. Stdout chính xác được xác minh

```text
PASS escaped-ampersand
PASS escaped-angle-brackets
PASS unicode-preserved
PASS unicode-utf8-differs-from-chars
PASS emoji-two-utf16-units
PASS budget-accept
PASS budget-reject
PASS xml-root
PASS xml-text
PASS xml-count
PASS doctype-rejected
PASS malformed-xml-rejected
PASS setstring-once
PASS written-object-not-readable-in-mock
PASS jdbc-insert-one
PASS freed-outgoing-rejected
PASS jdbc-row-exists
PASS getsqlxml-not-null
PASS incoming-read-only
PASS getstring-equal
PASS second-read-rejected
PASS freed-incoming-rejected
PASS resultset-exhausted
PASS sql-null-row
PASS sql-null-returns-null
PASS connection-closed
PASS unsupported-create-sqlxml
passed=27
```

Chương trình đã được biên dịch bằng `javac --release 17` và chạy trên OpenJDK 24: **27/27 kiểm thử PASS**.

### 8.4. Kiểm thử gì và chưa kiểm thử gì?

| Nhóm | Kiểm thử trong demo | Ý nghĩa |
| --- | --- | --- |
| XML escaping | `escaped-ampersand`, `escaped-angle-brackets` | Dữ liệu text không bị hiểu nhầm là markup |
| Unicode | `unicode-preserved`, `emoji-two-utf16-units` | Không nhầm UTF-16 vs UTF-8 |
| Size budget | `budget-accept/reject` | Có giới hạn ứng dụng trước khi ghi |
| XML validity | `xml-root/text/count` | XML đọc được, nội dung semantic đúng |
| XXE prevention | `doctype-rejected` | Parser không cho DOCTYPE |
| Bad XML | `malformed-xml-rejected` | XML không well-formed bị từ chối |
| One-shot write | `setstring-once` | Không thể write hai lần vào cùng mock SQLXML |
| One-shot read | `second-read-rejected` | Không thể read hai lần trên cùng mock SQLXML |
| State separation | `written-object-not-readable-in-mock`, `incoming-read-only` | Không tự dùng object ghi làm object đọc |
| JDBC bind | `jdbc-insert-one` | `PreparedStatement.setSQLXML` trên mock |
| JDBC result | `getsqlxml-not-null`, `getstring-equal` | `ResultSet.getSQLXML`, `getString` trên fresh mock |
| SQL NULL | `sql-null-returns-null` | Caller xử lý null |
| Cleanup | `freed-...`, `connection-closed` | Object sau free không dùng lại |
| Driver unsupported | `unsupported-create-sqlxml` | Driver có thể không hỗ trợ SQLXML |

**Giới hạn chứng cứ:** Demo là **test double** của JDBC API, không là database engine; nó không chứng minh một driver cụ thể sẽ không copy XML, khi nào SQL schema validation chạy, XML serialization có giữ nguyên bytes hay cột SQL XML có thể được tạo bằng mọi dialect. Cần integration test trên DB/driver thật.

## 9. Code tích hợp với database thật

Giả sử ứng dụng có bảng `docs` với cột `id` và `payload` kiểu XML theo dialect hiện tại. Dưới đây là phương pháp **JDBC portable ở tầng method**, không khẳng định DDL SQL XML là portable giữa các DB.

### 9.1. Insert XML nhỏ từ `String`

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLXML;
import java.sql.SQLException;

static int insertDocument(
        Connection conn, long id, String xml)
        throws SQLException {

    // Đặt kiểm tra size/schema/security policy trước đây.
    SQLXML value = conn.createSQLXML();
    try {
        value.setString(xml);

        try (PreparedStatement ps = conn.prepareStatement(
                "INSERT INTO docs(id, payload) VALUES (?, ?)")) {
            ps.setLong(1, id);
            ps.setSQLXML(2, value);
            return ps.executeUpdate();
        }
    } finally {
        value.free();
    }
}
```

Đây là **method minh họa cần DB thật**; `SQLXML` có thể bị driver từ chối. Gọi từ transaction boundary phù hợp. Nếu database type/driver không hỗ trợ, code có thể báo `SQLFeatureNotSupportedException`. Nếu XML invalid, exception có thể xuất hiện ở setter hoặc execute.

Tại sao dùng `ps.setSQLXML` thay vì `ps.setString`? Vì cột có kiểu **SQL XML** và driver có API typed conversion. `setString` trực tiếp lên PreparedStatement có thể cần casts SQL hoặc driver-specific conversion; không giả định mọi DB hiểu nó giống nhau.

### 9.2. Đọc XML nhỏ thành String

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLXML;
import java.sql.SQLException;

static String readDocument(Connection conn, long id)
        throws SQLException {

    try (PreparedStatement ps = conn.prepareStatement(
            "SELECT payload FROM docs WHERE id = ?")) {
        ps.setLong(1, id);

        try (ResultSet rs = ps.executeQuery()) {
            if (!rs.next()) {
                return null; // Không có hàng.
            }

            SQLXML value = rs.getSQLXML(1);
            if (value == null) {
                return null; // Có hàng nhưng SQL NULL.
            }

            try {
                return value.getString();
            } finally {
                value.free();
            }
        }
    }
}
```

**Lưu ý về API:** Method trả `null` cho cả “không có row” và “row có SQL NULL”; nếu nghiệp vụ phải phân biệt, trả một kiểu result có status rõ thay vì gộp hai trường hợp. Method này trả String còn sống sau khi SQLXML được free vì nó đã materialize dữ liệu, nhưng **không** đọc XML hai lần.

**Không an toàn nếu XML có thể cực lớn:** `getString` có thể cấp phát lượng memory lớn trước khi application đọc độ dài. Dùng kích thước DB/query limit hoặc streaming và driver testing.

### 9.3. Không dùng `SQLXML` sau `commit()/rollback()` tùy tiện

`SQLXML` mặc định được mô tả như logical pointer hợp lệ trong transaction tạo nó. Nếu caller thực hiện `commit` trước khi đọc hết hoặc kết thúc vòng đời SQLXML, object có thể không còn hợp lệ. Với connection pool, cũng không được giữ SQLXML sau khi borrowed connection đã trả về pool.

Thứ tự thiết kế:
1. Borrow connection/transaction.
2. Tạo/đọc SQLXML.
3. Hoàn thành thao tác parse/bind/execute trong scope đó.
4. `free()` SQLXML.
5. Commit/rollback và close các JDBC resources theo ownership.

Nếu framework đang quản lý transaction, hãy theo framework, không tự gọi commit trong helper làm mất tính nhất quán.

## 10. Dữ liệu lớn hơn: Reader/Writer và Source/Result

`getString/setString` thích hợp khi **toàn bộ XML** đủ nhỏ để đi qua memory budget. Nếu XML có thể vượt giới hạn, JDBC còn cung cấp:

```java
Reader reader = sqlxml.getCharacterStream();
Writer writer = sqlxml.setCharacterStream();

InputStream bytes = sqlxml.getBinaryStream();
OutputStream output = sqlxml.setBinaryStream();
```

Đây là **tập chữ ký minh họa**; mỗi SQLXML chỉ chọn **một** reading path hoặc **một** writing path theo contract. Không gọi `getString` rồi `getCharacterStream` trên cùng SQLXML.

### 10.1. Ghi bằng Writer

Ví dụ khi một SQLXML mới và bạn muốn ghi theo từng chunk:

```java
SQLXML value = conn.createSQLXML();
try {
    try (Writer writer = value.setCharacterStream()) {
        writer.write("<root>");
        writer.write("<item>");
        writer.write(escapedText);
        writer.write("</item>");
        writer.write("</root>");
    }

    try (PreparedStatement ps = conn.prepareStatement(
            "INSERT INTO docs(id, payload) VALUES (?, ?)")) {
        ps.setLong(1, id);
        ps.setSQLXML(2, value);
        ps.executeUpdate();
    }
} finally {
    value.free();
}
```

Đây là **snippet tích hợp**, cần imports, `conn/id/escapedText` và DB. **Đóng Writer trước `executeUpdate`**; Javadoc JDBC nêu statement có thể ném `SQLException` nếu Writer/OutputStream/Result chưa hoàn tất/đóng. Không dùng `setCharacterStream` **sau** `setString`.

**Không có bảo đảm zero-copy:** Một JDBC driver có thể buffer Writer trước khi gửi XML; nếu memory là vấn đề nghiêm trọng, benchmark và kiểm tra đặc tính driver.

### 10.2. Đọc bằng Reader

```java
SQLXML value = rs.getSQLXML("payload");
if (value != null) {
    try {
        try (Reader reader = value.getCharacterStream()) {
            char[] buffer = new char[8192];
            int n;
            while ((n = reader.read(buffer)) != -1) {
                // Đưa chunks vào parser/consumer có giới hạn.
            }
        }
    } finally {
        value.free();
    }
}
```

Snippet này **không tự parse XML**; nó mô tả cách đọc character chunks. Không nối tất cả chunks vào `StringBuilder` nếu mục tiêu là xử lý XML lớn không phụ thuộc heap size: làm vậy lại materialize toàn bộ.

### 10.3. `getSource()/setResult()` và JAXP

SQLXML hỗ trợ `Source/Result` cho:
- DOM: `DOMSource/DOMResult`.
- SAX: `SAXSource/SAXResult`.
- StAX: `StAXSource/StAXResult`.
- Stream: `StreamSource/StreamResult`.

Với XML lớn, một **SAX/StAX event pipeline** có thể giảm cần dựng DOM toàn bộ, nhưng chỉ khi driver/source/provider thực sự cho phép streaming hiệu quả. `DOMSource` bản chất là tree trong memory và có thể tiêu tốn nhiều heap hơn String.

**Security vẫn cần cấu hình:** Không coi `getSource` là parser an toàn tự động. Khi nhận `SAXSource` hay `StAXSource` từ driver, cần hiểu parser đã được cấu hình thế nào; nếu không kiểm soát parser/DTD policy, cân nhắc lấy stream và truyền vào JAXP parser đã harden.

### 10.4. XMLStreamReader được cấu hình an toàn

Một minh họa API StAX hiện hành cho XML không tin cậy:

```java
XMLInputFactory factory = XMLInputFactory.newDefaultFactory();
factory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
factory.setProperty(
        XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES,
        false);
factory.setXMLResolver(
        (publicId, systemId, baseURI, namespace) -> {
            throw new XMLStreamException(
                    "External references are not allowed");
        });
```

Snippet này cần imports `javax.xml.stream.*` và phải tạo `XMLStreamReader` trên input stream/reader phù hợp, xử lý events và close reader. Đây là một lựa chọn để **không tạo DOM tree**, nhưng cũng cần limits cho số events/depth/characters và driver-specific streaming verification.

## 11. SQLXML và encoding

Khi gọi `SQLXML.setString/getString`, bạn đang xử lý **Java `String`**, tức Unicode characters trong JVM. Không cần tự khai báo Java String là UTF-8. Nếu đưa String trực tiếp qua typed JDBC API, driver sẽ chịu trách nhiệm tương tác với SQL XML representation.

Trong XML file/byte stream có thể có declaration:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<note>Xin chào</note>
```

Tuy nhiên declaration này mô tả encoding của **byte serialization**. `getString` trả Java characters; không dùng XML declaration để suy rằng `String.length()` phải bằng số UTF-8 bytes. Tương tự, `getCharacterStream` trả character stream, dù XML bên trong có encoding declaration theo cách driver serialize.

Nếu ứng dụng tự encode:

```java
byte[] bytes = xml.getBytes(StandardCharsets.UTF_8);
```

thì bytes là UTF-8 theo lựa chọn của ứng dụng. Khi dùng `getBinaryStream()/setBinaryStream()`, JDBC xác định XML byte stream theo XML 1.0 encoding rules; không tự giả định mọi driver stream đều UTF-8 nếu dữ liệu/declaration khác.

**Luôn phân biệt**:
- Java heap String size.
- UTF-8 payload bytes.
- XML logical content.
- DB internal storage size.
- Wire/network representation.
- XML parser DOM memory footprint.

## 12. Trạng thái lỗi, SQL NULL và unsupported driver

| Lỗi / hiện tượng | Khả năng | Cách xử lý |
| --- | --- | --- |
| `createSQLXML` ném `SQLFeatureNotSupportedException` | Driver không hỗ trợ SQL XML | Dùng kiểu text/CLOB hoặc giải pháp driver-specific nếu sản phẩm cho phép |
| `setString` lần thứ hai ném `SQLException` | SQLXML đã not writable | Tạo SQLXML mới cho giá trị khác |
| `getString` lần thứ hai ném `SQLException` | SQLXML đã not readable | Dùng String đã đọc, không gọi getter lại |
| `getString` sau `setString` fail | Driver cho object trở thành not readable | Không dùng object write làm object read |
| `getSQLXML` trả `null` | SQL XML column là SQL NULL | Phân biệt NULL với empty XML/text |
| `setString` nhận XML sai | Input malformed/invalid | Validate trước; vẫn xử lý SQLException khi set/execute |
| `executeUpdate` fail | XML error/permission/type conversion/unclosed stream | Đóng Writer/Result, kiểm tra DB+driver, transaction rollback |
| `getString` hết heap | XML quá lớn, nhiều copies, concurrent load | Đặt DB limit, stream path, heap measurements |
| `free()` xong rồi gọi get | SQLXML object đã đóng | Không dùng reference sau free |
| Connection trả về pool | SQLXML logical pointer mất lifetime phù hợp | Xử lý trước close/commit theo contract |
| Parser đọc local file/URL | XXE/DTD external resource processing | Cấm DOCTYPE và external access, fail closed |
| XML có `&`/`<` chưa escape | XML malformed/markup injection | Dùng DOM/StAX serializer hoặc escape đúng context |

Không dùng `catch (Exception ignored)` để mặc định bỏ lỗi XML vì kết quả có thể là dữ liệu không được lưu, transaction rollback hoặc security violation. Hãy phân biệt unsupported feature, invalid input, database error và resource exhaustion.

## 13. Thiết kế giới hạn bộ nhớ cho production

Một thiết kế production nên có **request budget**, **database budget** và **parser budget**, không chỉ một dòng `xml.length()`.

### Input từ HTTP/file

1. Giới hạn request body bytes **trước khi tạo String** nếu cần hard memory limit.
2. Kiểm tra content-type và charset; nếu input là bytes thì decode đúng.
3. Chặn XML size quá lớn và quá sâu; kiểm tra root/schema.
4. Tạo XML bằng XML builder/serializer đáng tin cậy khi chứa dữ liệu người dùng.
5. Chỉ `setString` khi payload đã vừa budget.
6. Dùng `setSQLXML` và execute trong transaction.
7. `free` và close JDBC resources.

**Không** chỉ tin `Content-Length`; client có thể gửi chunked transfer hoặc khai báo sai. Server/network layer cần tự giới hạn bytes thực nhận.

### Output từ database

1. Hạn chế dữ liệu qua query nếu DB hỗ trợ và business use case cho phép.
2. Nếu XML có thể lớn, tránh `getString` trừ khi đã có size bounds đáng tin cậy.
3. Chọn `getCharacterStream` + bounded SAX/StAX processing khi driver thực sự hỗ trợ.
4. Kiểm soát processing time, XML depth, entity expansions, output size.
5. Không dùng DOM cho payload rất lớn khi chỉ cần đọc một vài nodes.
6. Đóng Reader, free SQLXML, đóng ResultSet/Statement theo scope.
7. Benchmark heap+GC với **nhiều requests đồng thời**, không chỉ một file.

Ví dụ nếu mỗi request giữ 4 copies của XML 1 MiB thì 100 concurrent requests đã tiêu tốn đáng kể memory trước khi tính overhead parser, buffers, objects. Con số ví dụ chỉ minh họa trade-off, không là guarantee về Java String internal representation.

### Dữ liệu XML nên lưu như XML hay JSON/text?

Quyết định phụ thuộc schema, query requirements, index, vendor capabilities và hệ sinh thái. `SQLXML` phù hợp khi cần SQL XML type thật sự. Nếu ứng dụng chỉ lưu một string text và không dùng DB XML functionality, chọn CLOB/VARCHAR có thể đơn giản hơn; ngược lại nếu DB cần XQuery/XML indexes/schema, SQL XML có thể có ý nghĩa.

Đừng chọn SQLXML vì nghĩ “mọi database JDBC đều có cùng XML support”. API tồn tại trong `java.sql`, nhưng support vẫn phụ thuộc driver/database.

## 14. Integration testing trên database thật

Mock ở phần 8 không kiểm tra XML SQL type của database. Với production, dựng test container/DB instance phù hợp và chạy:

| Tình huống | Test | Kỳ vọng |
| --- | --- | --- |
| Tạo SQLXML | `Connection.createSQLXML()` | Thành công hoặc báo unsupported rõ |
| Ghi vừa budget | `setString(validXml)`, `setSQLXML`, execute | Insert/update thành công |
| Đọc vừa budget | `getSQLXML`, `getString` | XML content đúng theo semantic test |
| NULL | Column SQL NULL | `getSQLXML` trả null |
| One-shot read | Gọi getter hai lần | Không được dựa vào lần thứ hai |
| One-shot write | Gọi setter hai lần | Không được dựa vào lần thứ hai |
| Cleanup | `free()` sau execute/read | Không leak resource |
| Lifetime | Commit/close connection | Không giữ SQLXML qua transaction |
| XML malformed | Broken start/end tags | Bị reject ở parse/set/execute theo driver |
| DTD/XXE | Untrusted XML với DOCTYPE | App parser từ chối, không truy cập external resources |
| Encoding | Vietnamese, emoji, escaping | Text sau parse đúng |
| XML declaration | `encoding` có trong input | No incorrect byte assumptions |
| Size threshold | Input > budget | Chặn trước khi tạo SQLXML |
| Large read | Server trả XML vượt budget | Có streaming/query limit policy |
| Stream writing | `setCharacterStream` rồi close Writer | `setSQLXML` + execute thành công nếu driver hỗ trợ |
| Driver unsupported | XML type/method absent | Fallback theo thiết kế |
| Transaction rollback | XML invalid sau execute | Rollback rõ; không để partial update |
| Pool | Borrowed logical Connection | SQLXML xử lý trước khi return pool |
| Driver upgrade | Nâng driver/JDK | Không regression về XML representation/stream support |

### So sánh XML đúng cách

Với XML stored/retrieved, **đừng mặc định raw string equality là contract của mọi DB**: database có thể chuẩn hóa whitespace, namespace declarations hoặc serialization. Test nên so DOM tree/schema/semantic values theo nhu cầu, hoặc XML canonicalization khi business yêu cầu; chỉ dùng byte-for-byte equality nếu hệ thống thực sự có contract lưu giữ bản văn chính xác.

Fixture ở phần 8 dùng String equality vì mock **cố ý lưu nguyên String**, không phải vì Java SE buộc mọi SQLXML database bảo toàn serialization bytes.

## 15. Những lỗi phổ biến

**1. Gọi `getString` hai lần trên một SQLXML.**  
Sai vì SQLXML đọc tối đa một lần. Lưu String đã đọc để dùng lại.

**2. Gọi `setString` hai lần, tưởng setter thay thế giá trị trước.**  
Không. SQLXML object chuyển sang not writable sau lần ghi đầu; tạo object mới.

**3. Gọi `getString` ngay sau `setString` để tự kiểm tra.**  
Không portable. Driver có thể chuyển object write thành not readable. Validate XML String **trước** khi set.

**4. `free()` SQLXML trước khi PreparedStatement execute.**  
Sai nếu driver cần đọc object ở lúc execute. Free sau khi hoàn tất operation.

**5. Gọi `setSQLXML` nhưng không chạy statement.**  
Bind không đồng nghĩa dữ liệu đã được lưu. Phải execute và kiểm tra update count/transaction.

**6. Quên đóng Writer từ `setCharacterStream`.**  
JDBC yêu cầu stream/result hoàn thành/đóng trước execute; có thể ném SQLException.

**7. Viết `try (SQLXML x = ...)` trong project target Java 17.**  
Không compile: `SQLXML` chỉ extends `AutoCloseable` từ Java SE 26. Với Java 17 dùng `free()` trong finally.

**8. Quên `free()` vì nghĩ close Connection là đủ.**  
JDBC quy định giải phóng SQLXML resources; không trông chờ implicit cleanup là chính sách.

**9. Không check `getSQLXML(...) == null`.**  
SQL NULL là trường hợp hợp lệ, không phải XML rỗng.

**10. Sử dụng `getString` cho XML quá lớn.**  
Materialize cả XML trong JVM có thể OOM. Dùng query/size bounds và stream path nếu phù hợp.

**11. Nhầm `String.length()` là số UTF-8 bytes.**  
Java String dùng UTF-16 code units; emoji và tiếng Việt có byte lengths khác.

**12. Tin rằng `getCharacterStream` chắc chắn memory O(1).**  
Driver có thể buffer. Test thực tế về heap/copy/network.

**13. Ghép raw user input vào XML.**  
`&`, `<`, dấu quote trong attributes và characters không hợp lệ có thể phá XML hoặc inject markup. Dùng XML serializer/escaping đúng context.

**14. Parse XML untrusted bằng `DocumentBuilderFactory.newInstance()` mặc định rồi nghĩ tự chống XXE.**  
Không bảo đảm. Cấm DOCTYPE/external access, bật secure processing và fail closed.

**15. Chỉ bật `FEATURE_SECURE_PROCESSING` và quên external entity restrictions.**  
OWASP nhấn mạnh cần tách hai lớp kiểm soát; secure processing không thay thế cấm external resources.

**16. Nhầm SQL XML type với VARCHAR chứa XML text.**  
JDBC setSQLXML/getSQLXML phụ thuộc SQL type và driver; dùng API typed đúng schema.

**17. Giả định mọi JDBC driver hỗ trợ SQLXML.**  
Không. `Connection.createSQLXML` có thể ném `SQLFeatureNotSupportedException`.

**18. Gửi XML String có DOCTYPE rồi kỳ vọng database tự chặn truy cập file.**  
Ứng dụng phải tự bảo vệ parser và DB/server policy; không dựa vào XML parser không rõ cấu hình.

**19. Giữ SQLXML sau khi commit/Connection đã return pool.**  
Object mặc định có transaction lifetime; xử lý trước boundary, không cache pointer.

**20. Test so raw XML bytes trên mọi database.**  
SQL XML logical content khác serialized bytes. So semantics trừ khi byte-preservation được quy định.

**21. Dùng regex tổng quát để validate XML.**  
XML có namespaces/entities/CDATA/encodings; dùng JAXP parser/validator được harden.

**22. Bắt `SQLException` từ XML invalid rồi vẫn commit.**  
Nếu statement thất bại, rollback theo transaction policy, đừng để trạng thái partial/không rõ.

**23. Cho rằng `free()` cũng đóng ResultSet/Statement.**  
Không. Mỗi JDBC resource có ownership riêng, dùng try-with-resources đúng loại.

**24. Coi việc size check trên XML đã `getString` là hard memory bound.**  
Quá muộn: String đã được tạo. Cần giới hạn từ nguồn hoặc stream.

## 16. Câu hỏi tự kiểm tra

**1. Method nào tạo SQLXML để ghi?**  
`Connection.createSQLXML()` tạo một object SQLXML ban đầu trống.

**2. Method nào đưa Java String vào SQLXML?**  
`SQLXML.setString(String)`; chỉ ghi một lần.

**3. Cách bind vào SQL statement?**  
`PreparedStatement.setSQLXML(index, sqlXml)`, sau đó execute.

**4. Cách lấy XML từ ResultSet?**  
`ResultSet.getSQLXML(index/label)` rồi một lần `getString()` nếu không null.

**5. Có được gọi `getString()` hai lần?**  
Không dựa vào điều đó; JDBC one-shot state khiến lần hai có thể SQLException.

**6. Có thể đọc ngay SQLXML vừa `setString` không?**  
Không portable. Driver được phép làm object not readable.

**7. Nên gọi `free()` khi nào?**  
Sau khi đã hoàn thành bind/execute hoặc đọc/parse XML và vẫn trong scope transaction/connection hợp lệ.

**8. `SQLXML` dùng được trong try-with-resources với `--release 17` không?**  
Không; `SQLXML` không extends AutoCloseable trong Java 17. Java SE 26 mới thêm `close()`/AutoCloseable.

**9. `getString()` có đảm bảo XML không vượt RAM không?**  
Không. Nó có thể materialize XML lớn; cần database/driver/query bounds.

**10. Vì sao `"🌿".length() == 2` nhưng UTF-8 bytes là 4?**  
Vì Java String đếm UTF-16 code units; emoji đó được mã hóa bằng surrogate pair và bốn UTF-8 bytes.

**11. Tại sao chỉ escape `&`, `<`, `>` không đủ cho mọi trường hợp?**  
Helper đó chỉ xử lý text-node content; attributes/controls/namespaces cần XML writer/serializer phù hợp.

**12. Nguy cơ chính khi parse XML untrusted là gì?**  
XXE, external entities, SSRF/local-file access, entity expansion và resource exhaustion. Cấm DOCTYPE/external access, áp limits.

**13. SQL NULL trong XML column biểu diễn thế nào?**  
`ResultSet.getSQLXML` trả `null`; phân biệt với empty XML content.

**14. Vì sao mock 27 PASS chưa bảo đảm driver production hoạt động?**  
Vì mock không mô phỏng SQL type/serialization/server/driver buffering/transaction thật. Cần integration test.

**15. Khi nào nên đổi từ getString sang streaming API?**  
Khi dữ liệu vượt budget hoặc cần xử lý incremental; vẫn phải xác minh driver thực sự hỗ trợ behavior tiết kiệm memory.

## 17. Tài liệu chính thức còn hiệu lực

- [Oracle Java SE 26 — `java.sql.SQLXML`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLXML.html): mapping, one-shot states, String/Stream/Source/Result, resource lifetime và `close()` Since 26.
- [Oracle Java SE 17 — `java.sql.SQLXML`](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLXML.html): contract target Java 17; không có AutoCloseable/close trong interface.
- [Oracle Java SE 26 — `Connection.createSQLXML`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Connection.html#createSQLXML()): SQLXML mới rỗng, có thể unsupported.
- [Oracle Java SE 26 — `PreparedStatement.setSQLXML`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/PreparedStatement.html#setSQLXML(int,java.sql.SQLXML)): bind SQL XML typed value; error khi stream/result chưa đóng.
- [Oracle Java SE 26 — `ResultSet.getSQLXML`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/ResultSet.html): đọc SQL XML column và SQL NULL handling.
- [Oracle Java SE 26 — `SQLFeatureNotSupportedException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLFeatureNotSupportedException.html): khi driver thiếu chức năng.
- [Oracle Java SE 26 — `DocumentBuilderFactory`](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/parsers/DocumentBuilderFactory.html): hardening DOM parsing.
- [Oracle Java SE 26 — `XMLInputFactory`](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLInputFactory.html): StAX parsing và external entity settings.
- [OWASP — XML External Entity Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html): hướng dẫn cập nhật để chặn DTD/XXE và external resources.

**Ghi nhớ:** `SQLXML.getString/setString` là lối đi gọn cho **XML đủ nhỏ để materialize**, không phải lời hứa về memory hay API getter/setter tùy ý. Mỗi SQLXML chỉ dùng **một đường đọc hoặc một đường ghi**, kiểm tra kích thước và well-formedness trước khi ghi, bảo vệ parser khỏi XXE, luôn `free()` khi xong ở Java 17, xử lý SQL NULL và unsupported drivers, rồi integration-test với database thật trước khi triển khai.
