# XMLStreamException và thông tin vị trí lỗi trong StAX

## 1. Mục tiêu

StAX (Streaming API for XML) là API đọc/ghi XML theo dòng sự kiện trong Java. Khi XML sai cấu trúc, thiếu thẻ đóng, có namespace không hợp lệ hoặc một thao tác trên parser bị lỗi, Java có thể ném **`javax.xml.stream.XMLStreamException`**. Khác với việc chỉ có một chuỗi thông báo lỗi, StAX còn cung cấp **`javax.xml.stream.Location`** để truy xuất vị trí gần nơi lỗi: dòng, cột, offset và định danh nguồn XML.

Bài này thuộc **StAX cơ bản**, tập trung vào **“XMLStreamException và thông tin vị trí lỗi”**. Sau bài, bạn sẽ:

- Hiểu exception thuộc loại checked, các constructor và nested cause.
- Xử lý `getLocation()` có thể null; các giá trị line/column/offset có thể không được cung cấp.
- Phân biệt `XMLStreamException.getLocation()`, `XMLStreamReader.getLocation()` và `XMLEvent.getLocation()`.
- Giữ snapshot vị trí trước khi cursor di chuyển bằng `next()` hoặc `getElementText()`.
- Nắm byte offset so với character offset, tránh lấy tọa độ để cắt chuỗi sai.
- Gắn thông tin lỗi nghiệp vụ vào Location và giữ nguyên underlying cause.
- Xử lý malformed XML, từ chối DTD/external entity, đóng parser và underlying input đúng quyền sở hữu.
- Chạy chương trình Java 17+ với parser StAX thật và **35/35 kiểm thử PASS**.

**Phạm vi:** Các API `javax.xml.stream` vẫn hiện hành trong Java SE 26, module `java.xml`. Ví dụ có thể biên dịch với `javac --release 17` và đã chạy thành công trên OpenJDK 24. Không yêu cầu thư viện XML bên ngoài.

## 2. `XMLStreamException` là gì?

`javax.xml.stream.XMLStreamException` kế thừa `java.lang.Exception`, không kế thừa `RuntimeException`. Nó là một **checked exception** dùng cho unexpected processing errors và XML well-formedness errors.

```text
java.lang.Throwable
  └── java.lang.Exception
        └── javax.xml.stream.XMLStreamException
```

Trong chương trình xử lý StAX, những method có thể ném exception này bao gồm:

| API | Tình huống |
| --- | --- |
| `XMLInputFactory.createXMLStreamReader(...)` | Parser khởi tạo input bị lỗi |
| `XMLStreamReader.hasNext()` | Không thể xác định trạng thái tiếp theo |
| `XMLStreamReader.next()` | Đọc token gặp XML không hợp lệ |
| `XMLStreamReader.getElementText()` | Text-only element có nested element hoặc EOF bất thường |
| `XMLStreamReader.require(...)` | Current event không đúng kỳ vọng |
| `XMLStreamReader.close()` | Giải phóng parser gặp lỗi |
| `XMLEventReader.nextEvent()` | Đọc event gặp XML không hợp lệ |
| `XMLEventReader.close()` | Giải phóng event reader gặp lỗi |

Vì là checked exception, một method gọi những API đó phải `catch (XMLStreamException ex)` hoặc khai báo `throws XMLStreamException`.

### 2.1. Những ví dụ lỗi thường gặp

```xml
<!-- Thẻ đóng không khớp -->
<root>
  <item>Xin chào</wrong>
</root>
```

```xml
<!-- Thuộc tính bị trùng -->
<root id="1" id="2"/>
```

```xml
<!-- Prefix chưa được khai báo -->
<p:root/>
```

```xml
<!-- Kết thúc tài liệu quá sớm -->
<root><item>unfinished</item>
```

Với parser StAX thực, các ví dụ trên có thể gây `XMLStreamException` do XML không well-formed hoặc namespace không hợp lệ. Không phải mọi exception khi code thao tác với XML đều thuộc loại này: `IllegalStateException`, `IllegalArgumentException`, `IOException` hoặc exception nghiệp vụ có thể xuất hiện theo đúng từng API.

### 2.2. Các constructor

Javadoc Java SE 26 định nghĩa những constructor:

```java
new XMLStreamException();
new XMLStreamException("message");
new XMLStreamException(cause);
new XMLStreamException("message", cause);
new XMLStreamException("message", location);
new XMLStreamException("message", location, cause);
```

Đây là các lời gọi minh họa, không phải một file Java độc lập. `location` có kiểu `javax.xml.stream.Location`; `cause` có kiểu `Throwable`.

Thông tin có thể lấy từ exception:

- `getMessage()`: mô tả lỗi, nhưng format tùy parser.
- `getLocation()`: nơi lỗi được xác định, **có thể null**.
- `getNestedException()`: underlying Throwable nếu có.
- `getCause()`: nguyên nhân theo chuẩn `Throwable`.
- `getSuppressed()`: các exceptions phụ, ví dụ lỗi đóng reader sau một lỗi parse chính.

Không lấy dòng/cột bằng cách regex trên `getMessage()`: parser/provider/locale khác nhau có thể đổi nội dung. `Location` mới là contract chuẩn.

## 3. Năm trường của `javax.xml.stream.Location`

`Location` là interface chứa:

```java
int getLineNumber();
int getColumnNumber();
int getCharacterOffset();
String getPublicId();
String getSystemId();
```

Theo Javadoc Java SE 26, **toàn bộ thông tin vị trí đều tùy chọn**. Không được giả định mọi provider cung cấp đủ năm trường.

| Method | Ý nghĩa | Không có dữ liệu |
| --- | --- | --- |
| `getLineNumber()` | Số dòng gần vị trí event/lỗi, thường bắt đầu từ 1 | `-1` |
| `getColumnNumber()` | Số cột gần vị trí event/lỗi | `-1` |
| `getCharacterOffset()` | Byte hoặc character offset vào input | `-1` |
| `getPublicId()` | XML public identifier | `null` |
| `getSystemId()` | XML system identifier, thường URI hoặc nguồn tài liệu | `null` |

**Lưu ý về offset:** Mặc dù tên method là `getCharacterOffset()`, Javadoc nêu khi đầu vào là **file/byte stream**, offset có thể tính theo **bytes**; khi đầu vào là **character media/Reader**, offset tính theo **characters**. XML có tiếng Việt, emoji hoặc entity references có thể làm các cách đếm khác nhau. Không dùng offset như Java `String` index cho mọi loại input.

Dòng/cột thường mô tả vị trí **event kết thúc hoặc điểm parser phát hiện lỗi**, không nhất thiết là ký tự đầu tiên tạo ra lỗi. Với thẻ sai `</wrong>`, parser có thể chỉ xác định lỗi khi đọc đến thẻ đóng. Do đó thông báo nên nói “gần dòng/cột”, không hứa chính xác mức ký tự trên mọi parser.

### 3.1. Xử lý null và -1

Sai:

```java
catch (XMLStreamException ex) {
    int line = ex.getLocation().getLineNumber();
    // Có thể NullPointerException.
}
```

Đúng:

```java
catch (XMLStreamException ex) {
    Location loc = ex.getLocation();
    String line = loc != null && loc.getLineNumber() > 0
            ? Integer.toString(loc.getLineNumber())
            : "không rõ";
    String column = loc != null && loc.getColumnNumber() > 0
            ? Integer.toString(loc.getColumnNumber())
            : "không rõ";
    System.err.println(
            "XML không hợp lệ gần dòng " + line
            + ", cột " + column);
}
```

Đây là snippet trong method Java có imports `javax.xml.stream.*`. Không nhầm `-1` với một dòng hợp lệ; nếu Location null hoặc có field không xác định thì hiển thị fallback.

## 4. Phân biệt ba loại vị trí trong StAX

### 4.1. Vị trí trên exception

Khi parser ném `XMLStreamException`, gọi `ex.getLocation()` để lấy vị trí **của lỗi** nếu provider có. Cần kiểm tra null và các field `-1`. Nếu wrap exception ở tầng khác, giữ nguyên cause và location/diagnostic.

### 4.2. Vị trí của current cursor

`XMLStreamReader` bắt đầu ở `START_DOCUMENT`, rồi di chuyển theo `next()`. `reader.getLocation()` trả Location của **current state**.

**Vòng đời:** Javadoc của `XMLStreamReader.getLocation()` nói thông tin này chỉ hợp lệ **đến khi gọi `next()` tiếp theo**. Một implementation có thể cập nhật object Location đang được tham chiếu. Nếu muốn lưu vị trí cho việc xử lý sau, hãy **copy các giá trị** trước khi reader di chuyển.

Sai:

```java
Location old = reader.getLocation();
reader.next();
System.out.println(old.getLineNumber()); // Không portable.
```

Đúng:

```java
Location loc = reader.getLocation();
int line = loc == null ? -1 : loc.getLineNumber();
int column = loc == null ? -1 : loc.getColumnNumber();
String systemId = loc == null ? null : loc.getSystemId();
reader.next();
// line, column, systemId đã là snapshot.
```

### 4.3. Vị trí của XMLEvent

`XMLEventReader` trả các `XMLEvent`. Javadoc `XMLEvent.getLocation()` nói Location **non-volatile**: event giữ vị trí của mình dù reader tiếp tục đọc.

```java
XMLEvent event = eventReader.nextEvent();
Location atEvent = event.getLocation();
// Có thể giữ event; location gắn với event ổn định.
```

Đây là snippet có `eventReader` đã khai báo. Không nhầm contract của XMLEvent với current Location của cursor.

| API | Vị trí mô tả | Cần làm gì |
| --- | --- | --- |
| `ex.getLocation()` | Lỗi parsing/processing | Kiểm tra nullable, hiển thị field khả dụng |
| `reader.getLocation()` | Current cursor event | Snapshot trước khi next |
| `event.getLocation()` | Event object cụ thể | Location non-volatile |
| Record snapshot của app | Giá trị đã copy | Có thể lưu độc lập với reader |

## 5. Đọc parser XML an toàn và giữ lỗi

Với XML từ user hoặc dịch vụ bên ngoài, ứng dụng phải bảo vệ khỏi XXE, external entity resolution, DTD/entity expansion và tài nguyên đầu vào quá lớn. Chỉ bắt `XMLStreamException` không làm parser an toàn.

Một cấu hình Java 17+ còn hiện hành:

```java
static XMLInputFactory secureFactory() {
    XMLInputFactory f = XMLInputFactory.newDefaultFactory();
    f.setProperty(XMLInputFactory.IS_NAMESPACE_AWARE, true);
    f.setProperty(XMLInputFactory.SUPPORT_DTD, false);
    f.setProperty(
            XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES,
            false);
    f.setXMLResolver(
            (publicID, systemID, baseURI, namespace) -> {
                throw new XMLStreamException(
                        "External entities are forbidden");
            });
    return f;
}
```

- Bật namespace-aware parsing.
- Yêu cầu không xử lý DTD.
- Tắt external parsed entities.
- Dùng resolver **từ chối** external entity requests.
- Nếu provider không hỗ trợ property, phải fail closed; không nuốt `IllegalArgumentException` rồi parse theo cấu hình nguy hiểm.

**Quan trọng:** `SUPPORT_DTD=false` không nhất thiết khiến mọi parser lập tức ném khi gặp DOCTYPE. Một provider có thể vẫn trả event `XMLStreamConstants.DTD`. Nếu chính sách **cấm DOCTYPE**, hãy chủ động từ chối event đó:

```java
if (type == XMLStreamConstants.DTD) {
    throw new XMLStreamException(
            "DOCTYPE is prohibited",
            reader.getLocation());
}
```

Đoạn này nằm trong loop có `type` là `reader.next()`. Nó biến vi phạm security policy thành `XMLStreamException` có Location nếu có.

### 5.1. Bảo toàn lỗi parse khi close cũng lỗi

`XMLStreamReader.close()` có thể ném `XMLStreamException`. Nếu bạn dùng `finally { reader.close(); }` đơn giản, exception close có thể che mất exception parse ban đầu.

Một pattern có chủ đích:

```java
XMLStreamException primary = null;
try {
    while (reader.hasNext()) {
        reader.next();
    }
} catch (XMLStreamException ex) {
    primary = ex;
    throw ex;
} finally {
    try {
        reader.close();
    } catch (XMLStreamException closeError) {
        if (primary == null) throw closeError;
        primary.addSuppressed(closeError);
    }
}
```

Đây là snippet trong method có `reader` được tạo trước đó. Nếu creation thất bại thì chưa có reader để đóng; caller vẫn phải quản lý nguồn input.

**Ownership:** Theo `XMLStreamReader.close()` Javadoc, việc close parser **không đóng underlying InputStream/Reader**. Nếu tự mở `InputStream` từ file hoặc HTTP body, hãy đóng nó bằng try-with-resources ở lớp sở hữu.

## 6. `getElementText()` làm thay đổi vị trí cursor

`XMLStreamReader.getElementText()` chỉ dùng khi current event là `START_ELEMENT` và phần tử có text-only content. Khi thành công, current event trở thành **`END_ELEMENT` tương ứng**.

Ví dụ:

```java
if ("item".equals(reader.getLocalName())) {
    Location before = reader.getLocation();
    int startLine = before == null ? -1
            : before.getLineNumber();
    String text = reader.getElementText();
    // reader đã chuyển đến END_ELEMENT của item.
}
```

Không coi `getElementText()` là đọc text nhưng giữ nguyên cursor ở start tag. Nếu element có nested child elements, nó có thể ném `XMLStreamException` theo contract. Nếu cần xử lý mixed content, đọc các sự kiện `START_ELEMENT`, `CHARACTERS`, `CDATA` và `END_ELEMENT` một cách tuần tự.

Điều này cũng liên quan việc lưu Location: nếu muốn báo nơi bắt đầu `<item>`, snapshot **trước** `getElementText()`, không đọc lại `reader.getLocation()` sau đó.

## 7. Tự tạo `XMLStreamException` có vị trí và nguyên nhân

Một XML có thể well-formed nhưng chứa giá trị nghiệp vụ sai, ví dụ số lượng âm. Ứng dụng có thể tạo lỗi giữ current location:

```java
if (quantity < 0) {
    throw new XMLStreamException(
            "Quantity must be non-negative",
            reader.getLocation());
}
```

Nếu underlying parsing/conversion failure đã có cause:

```java
try {
    int number = Integer.parseInt(rawNumber);
} catch (NumberFormatException cause) {
    throw new XMLStreamException(
            "Invalid integer",
            reader.getLocation(),
            cause);
}
```

Đây là các snippets yêu cầu biến `reader`, `quantity`, `rawNumber` trong scope thích hợp. Khi xử lý tầng nghiệp vụ phức tạp, bạn cũng có thể dùng domain-specific exception chứa position record. Không cần dùng `XMLStreamException` cho mọi validation error; chỉ cần **không làm mất vị trí và nguyên nhân**.

### 7.1. Immutable snapshot với record Java 17

```java
record Position(
        int line,
        int column,
        int offset,
        String publicId,
        String systemId) {

    static Position copy(Location loc) {
        if (loc == null) {
            return new Position(-1, -1, -1, null, null);
        }
        return new Position(
                loc.getLineNumber(),
                loc.getColumnNumber(),
                loc.getCharacterOffset(),
                loc.getPublicId(),
                loc.getSystemId());
    }
}
```

Snapshot giúp lưu thông tin sau khi parser đã di chuyển. **Không** đưa `systemId` thẳng lên UI nếu có thể chứa đường dẫn nội bộ hoặc URL chứa thông tin nhạy cảm.

## 8. Ví dụ Java 17+ đầy đủ: 35 kiểm thử StAX thực

Chương trình `StaxLocationDemo.java` dùng `XMLInputFactory.newDefaultFactory()`, `XMLStreamReader` và `XMLEventReader` của JDK. Nó:
- Đọc XML nhiều dòng chứa tiếng Việt và emoji.
- Kiểm tra số lượng start/end elements và `getElementText()`.
- Chụp Location theo current event, kiểm tra `systemId` khi được truyền.
- Bắt lỗi mismatched tags, thiếu closing tag, duplicate attributes, undeclared prefix.
- Cấm DOCTYPE và external entities.
- Tạo `XMLStreamException` với custom Location và IOException cause.
- Xử lý Location null, `-1` và optional IDs.
- Kiểm chứng non-volatile `XMLEvent.getLocation()`.
- Giữ parse failure khi reader cleanup lỗi.

### 8.1. File `StaxLocationDemo.java`

```java
import java.io.IOException;
import java.io.StringReader;
import javax.xml.stream.Location;
import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLEventReader;
import javax.xml.stream.XMLStreamConstants;
import javax.xml.stream.XMLStreamException;
import javax.xml.stream.XMLStreamReader;
import javax.xml.stream.events.XMLEvent;

public final class StaxLocationDemo {
    private static int passed;

    private static void check(String label, boolean ok) {
        if (!ok) throw new AssertionError("FAIL " + label);
        System.out.println("PASS " + label);
        passed++;
    }

    record Position(int line, int column, int offset,
                    String publicId, String systemId) {
        static Position copy(Location loc) {
            if (loc == null) return new Position(
                    -1, -1, -1, null, null);
            return new Position(loc.getLineNumber(),
                    loc.getColumnNumber(),
                    loc.getCharacterOffset(),
                    loc.getPublicId(),
                    loc.getSystemId());
        }

        String safeText() {
            return "line=" + (line > 0 ? line : "?")
                    + ",column=" + (column > 0 ? column : "?")
                    + ",offset=" + (offset >= 0 ? offset : "?");
        }
    }

    record StaticLocation(int line, int column, int offset,
                          String publicId, String systemId)
            implements Location {
        @Override public int getLineNumber() { return line; }
        @Override public int getColumnNumber() { return column; }
        @Override public int getCharacterOffset() { return offset; }
        @Override public String getPublicId() { return publicId; }
        @Override public String getSystemId() { return systemId; }
    }

    record Scan(int starts, int ends, String itemText,
                Position root, Position item) { }

    private static XMLInputFactory secureFactory() {
        XMLInputFactory f = XMLInputFactory.newDefaultFactory();
        f.setProperty(XMLInputFactory.IS_NAMESPACE_AWARE, true);
        f.setProperty(XMLInputFactory.SUPPORT_DTD, false);
        f.setProperty(
                XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES,
                false);
        f.setXMLResolver(
                (publicID, systemID, baseURI, namespace) -> {
                    throw new XMLStreamException(
                            "External entities are forbidden");
                });
        return f;
    }

    static Scan read(String xml, String systemId)
            throws XMLStreamException {

        XMLStreamReader reader =
                secureFactory().createXMLStreamReader(
                        systemId, new StringReader(xml));
        XMLStreamException failure = null;

        try {
            int starts = 0;
            int ends = 0;
            Position root = null;
            Position item = null;
            String itemText = null;

            while (reader.hasNext()) {
                int type = reader.next();

                if (type == XMLStreamConstants.DTD) {
                    throw new XMLStreamException(
                            "DOCTYPE is prohibited",
                            reader.getLocation());
                }

                if (type == XMLStreamConstants.START_ELEMENT) {
                    starts++;
                    if ("root".equals(reader.getLocalName())) {
                        root = Position.copy(reader.getLocation());
                    } else if ("item".equals(
                            reader.getLocalName())) {
                        item = Position.copy(reader.getLocation());
                        itemText = reader.getElementText();
                        ends++; // Reader now at END_ELEMENT.
                    }
                } else if (type == XMLStreamConstants.END_ELEMENT) {
                    ends++;
                }
            }

            return new Scan(starts, ends, itemText, root, item);
        } catch (XMLStreamException ex) {
            failure = ex;
            throw ex;
        } finally {
            try {
                reader.close();
            } catch (XMLStreamException closeFailure) {
                if (failure == null) throw closeFailure;
                failure.addSuppressed(closeFailure);
            }
        }
    }

    static XMLStreamException thrownFrom(String xml) {
        try {
            read(xml, "urn:demo:broken");
        } catch (XMLStreamException failure) {
            return failure;
        }
        throw new AssertionError("Expected XMLStreamException");
    }

    public static void main(String[] args) throws Exception {
        final String good = "<root>\n"
                + "  <item>Xin chào 🌿</item>\n"
                + "</root>";

        Scan ok = read(good, "urn:demo:valid");
        check("starts-count", ok.starts() == 2);
        check("ends-count", ok.ends() == 2);
        check("unicode-item-text",
                ok.itemText().equals("Xin chào 🌿"));
        check("root-location-reported",
                ok.root() != null
                && ok.root().line() == 1
                && ok.root().column() > 0);
        check("item-on-second-line",
                ok.item() != null
                && ok.item().line() == 2);
        check("source-system-id",
                "urn:demo:valid".equals(ok.item().systemId()));
        check("snapshot-independent-root",
                ok.root().line() == 1
                && ok.item().line() == 2);
        check("snapshot-has-position",
                ok.root().safeText().contains("line=1"));

        XMLStreamException malformed = thrownFrom(
                "<root>\n  <item>x</wrong>\n</root>");
        Location problem = malformed.getLocation();
        check("mismatched-tags-throws", malformed != null);
        check("parser-error-has-location", problem != null);
        check("malformed-second-line",
                problem != null
                && problem.getLineNumber() == 2);
        check("malformed-column-available",
                problem != null
                && problem.getColumnNumber() > 0);
        check("error-position-copied",
                Position.copy(problem).line() == 2);
        check("malformed-has-message",
                malformed.getMessage() != null
                && !malformed.getMessage().isBlank());

        XMLStreamException missingEnd = thrownFrom(
                "<root><item>unfinished</item>");
        check("missing-close-throws", missingEnd != null);
        check("missing-close-location",
                missingEnd.getLocation() != null);

        XMLStreamException duplicate = thrownFrom(
                "<root a='1' a='2'/>");
        check("duplicate-attribute-rejected",
                duplicate != null);

        XMLStreamException badPrefix = thrownFrom("<p:root/>");
        check("undeclared-prefix-rejected", badPrefix != null);

        XMLStreamException dtd = thrownFrom(
                "<!DOCTYPE root [<!ENTITY secret SYSTEM "
                + "\"file:///dummy\">]><root>&secret;</root>");
        check("doctype-rejected", dtd != null);
        check("doctype-location",
                dtd.getLocation() != null);

        StaticLocation at = new StaticLocation(
                7, 15, 84, null, "urn:demo:custom");
        IOException rootCause = new IOException("I/O failure");
        XMLStreamException domain = new XMLStreamException(
                "Invalid item value", at, rootCause);

        check("custom-location-preserved",
                domain.getLocation() == at);
        check("custom-line-column",
                domain.getLocation().getLineNumber() == 7
                && domain.getLocation().getColumnNumber() == 15);
        check("custom-offset-preserved",
                domain.getLocation().getCharacterOffset() == 84);
        check("nested-exception",
                domain.getNestedException() == rootCause);
        check("cause-recoverable",
                domain.getCause() == rootCause);
        check("checked-exception",
                domain instanceof Exception);
        check("custom-system-id", "urn:demo:custom".equals(
                domain.getLocation().getSystemId()));

        XMLStreamException noLocation =
                new XMLStreamException("No source location");
        check("location-may-be-null",
                noLocation.getLocation() == null);
        check("unknown-line-fallback",
                Position.copy(null).safeText().contains("line=?"));

        StaticLocation unknown =
                new StaticLocation(-1, -1, -1, null, null);
        check("unknown-values-are-optional",
                Position.copy(unknown).safeText().equals(
                        "line=?,column=?,offset=?"));
        check("public-id-optional",
                unknown.getPublicId() == null);
        check("system-id-optional",
                unknown.getSystemId() == null);

        XMLInputFactory factory = secureFactory();
        XMLEventReader events = factory.createXMLEventReader(
                new StringReader(good));
        XMLEvent savedRoot = null;
        Position eventPosition = null;
        int startEvents = 0;

        try {
            while (events.hasNext()) {
                XMLEvent event = events.nextEvent();
                if (event.isStartElement()) {
                    startEvents++;
                    if (savedRoot == null) {
                        savedRoot = event;
                        eventPosition =
                                Position.copy(event.getLocation());
                    }
                }
            }
        } finally {
            events.close();
        }

        check("event-api-start-elements", startEvents == 2);
        check("event-location-nonvolatile",
                savedRoot != null
                && Position.copy(savedRoot.getLocation())
                        .equals(eventPosition));
        check("event-position-line-one",
                eventPosition != null
                && eventPosition.line() == 1);

        System.out.println("passed=" + passed);
    }
}
```

### 8.2. Lệnh biên dịch và chạy

```bash
javac --release 17 -encoding UTF-8 StaxLocationDemo.java
java StaxLocationDemo
```

Lệnh dùng được trên Linux/macOS hoặc Windows PowerShell với JDK 17+ trên PATH. Chương trình không cần database, H2 hay XML libraries bên ngoài.

### 8.3. Stdout chính xác trên OpenJDK 24

```text
PASS starts-count
PASS ends-count
PASS unicode-item-text
PASS root-location-reported
PASS item-on-second-line
PASS source-system-id
PASS snapshot-independent-root
PASS snapshot-has-position
PASS mismatched-tags-throws
PASS parser-error-has-location
PASS malformed-second-line
PASS malformed-column-available
PASS error-position-copied
PASS malformed-has-message
PASS missing-close-throws
PASS missing-close-location
PASS duplicate-attribute-rejected
PASS undeclared-prefix-rejected
PASS doctype-rejected
PASS doctype-location
PASS custom-location-preserved
PASS custom-line-column
PASS custom-offset-preserved
PASS nested-exception
PASS cause-recoverable
PASS checked-exception
PASS custom-system-id
PASS location-may-be-null
PASS unknown-line-fallback
PASS unknown-values-are-optional
PASS public-id-optional
PASS system-id-optional
PASS event-api-start-elements
PASS event-location-nonvolatile
PASS event-position-line-one
passed=35
```

**35/35 PASS** với `javac --release 17`, thực thi trên OpenJDK 24. Ví dụ dùng StAX parser thật, không mô phỏng exception bằng cách tự ném ở các test malformed XML (ngoại trừ policy tự chặn DTD). Tuy vậy, một provider khác có thể báo cột/offset khác, hoặc không cung cấp Location cho một số lỗi.

### 8.4. Giải thích nhóm kết quả

| Nhóm | Các phép kiểm tra | Ý nghĩa |
| --- | --- | --- |
| Parsing XML cơ bản | `starts-count`, `ends-count` | Hai start elements và hai end elements |
| Unicode | `unicode-item-text` | `getElementText` giữ tiếng Việt và emoji |
| Position current | `root-location-reported`, `item-on-second-line` | Dòng/cột được provider hiện tại báo |
| Source identity | `source-system-id` | Truyền URI đầu vào và đọc lại từ Location |
| Snapshot | `snapshot-independent-root` | Vị trí root không bị thay đổi bởi bước đọc item |
| Malformed tags | `mismatched-tags-throws`, `malformed-second-line` | Error StAX có line gần nơi sai |
| Các lỗi XML khác | `missing-close-throws`, `duplicate-attribute-rejected`, `undeclared-prefix-rejected` | Phát hiện EOF, duplicate, namespace |
| Security | `doctype-rejected` | DTD bị từ chối |
| Custom exception | `custom-location-*` | Constructor với Location tùy chỉnh |
| Causes | `nested-exception`, `cause-recoverable` | Giữ underlying IOException |
| Missing fields | `location-may-be-null`, `unknown-values-are-optional` | Không báo lỗi khi không có vị trí |
| Event API | `event-location-nonvolatile` | Event vị trí ổn định sau khi duyệt |

**Không tự kết luận** “parser nào cũng báo malformed XML ở dòng 2, cột X”. Đây là output đã test trên một provider/JDK cụ thể; code production vẫn phải xử lý Location null/-1 và khác biệt provider.

## 9. Code tích hợp: xử lý InputStream thật

Với XML từ HTTP upload, file, object storage hoặc message broker:
1. Giới hạn **số bytes đầu vào** trước khi parse (không chỉ `Content-Length`).
2. Tạo StAX factory đã cấu hình an toàn.
3. Tạo parser từ `InputStream` hoặc `Reader`.
4. Đọc tuần tự, kiểm soát số events/depth/total text.
5. Catch `XMLStreamException`, lấy Location nếu có và trả domain diagnostic.
6. Đóng parser riêng, đóng underlying input bằng owner scope.
7. Không log nguyên XML chứa bí mật; không hiện raw systemId có đường dẫn nội bộ.

Ví dụ skeleton:

```java
import java.io.InputStream;
import javax.xml.stream.*;

static void readUploadedXml(InputStream input)
        throws XMLStreamException {
    XMLInputFactory factory = XMLInputFactory.newDefaultFactory();
    factory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
    factory.setProperty(
            XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES,
            false);
    factory.setXMLResolver((pub, sys, base, ns) -> {
        throw new XMLStreamException("External reference forbidden");
    });

    XMLStreamReader reader = factory.createXMLStreamReader(input);
    XMLStreamException primary = null;

    try {
        while (reader.hasNext()) {
            int kind = reader.next();
            if (kind == XMLStreamConstants.DTD) {
                throw new XMLStreamException(
                        "DOCTYPE forbidden",
                        reader.getLocation());
            }
            // Process bounded events and track depth.
        }
    } catch (XMLStreamException ex) {
        primary = ex;
        throw ex;
    } finally {
        try {
            reader.close();
        } catch (XMLStreamException closeError) {
            if (primary == null) throw closeError;
            primary.addSuppressed(closeError);
        }
    }
}
```

**Đây là method minh họa**: giới hạn input bytes/events/depth phải được triển khai ở tầng ứng dụng. Caller chịu trách nhiệm đóng `input`, vì `XMLStreamReader.close()` không đóng underlying input source. Đừng đưa input từ URL không tin cậy vào resolver hoặc mở external entities.

Khi XML error được đưa ra HTTP API, nên trả một code như `INVALID_XML`, một dòng/cột nếu có và tên tài liệu an toàn, không trả toàn bộ stacktrace, raw XML hoặc URI private.

## 10. Phân biệt StAX exception với SAX/DOM

| API | Exception thường gặp | Cách lấy vị trí |
| --- | --- | --- |
| StAX cursor | `XMLStreamException` | `ex.getLocation()`, `reader.getLocation()` |
| StAX event | `XMLStreamException` | `ex.getLocation()`, `XMLEvent.getLocation()` |
| SAX | `SAXParseException` | `getLineNumber()`, `getColumnNumber()` trực tiếp |
| DOM qua `DocumentBuilder` | `SAXException` / `SAXParseException` | Nếu là `SAXParseException`, đọc vị trí qua SAX |

Không cast `XMLStreamException` sang `SAXParseException`. Nếu một dịch vụ có nhiều XML parsers, hãy chuẩn hóa chúng về **record diagnostic của ứng dụng**, thay vì cố dùng cùng các getters giữa hai exception classes khác nhau.

StAX có ưu điểm xử lý tuần tự theo sự kiện, nhưng nếu bạn thu mọi sự kiện vào một list hoặc nối mọi text vào StringBuilder, ứng dụng vẫn có thể dùng nhiều RAM. `Location` không phải cơ chế bảo vệ memory.

## 11. Lỗi thường gặp

**1. Không kiểm tra null từ `getLocation()`.**  
Dẫn tới NPE trong chính error handler. Luôn có fallback.

**2. In số dòng `-1` như một vị trí hợp lệ.**  
`-1` nghĩa là không có thông tin; hiển thị “không rõ”.

**3. Giả định `getCharacterOffset` luôn là index của Java String.**  
Có thể là byte offset với InputStream hoặc character offset với Reader.

**4. Lấy line/column bằng regex từ `XMLStreamException.getMessage`.**  
Format message khác nhau theo provider; dùng `Location`.

**5. Giữ reference tới current `reader.getLocation()` qua nhiều `next()`.**  
Location current event chỉ có hiệu lực trước lần di chuyển kế tiếp. Copy fields.

**6. Coi `XMLEvent.getLocation()` cũng biến đổi sau nextEvent.**  
Không. Javadoc nói XMLEvent Location là non-volatile.

**7. Quên `getElementText()` di chuyển reader tới matching END_ELEMENT.**  
Dễ đếm thiếu/thừa hoặc bỏ qua events.

**8. Bắt XMLStreamException rồi tiếp tục xử lý một tài liệu đã malformed.**  
Parser state có thể không còn tin cậy; nên fail fast.

**9. Coi mọi parser exception có line/column dương.**  
Thông tin có thể thiếu hoặc được báo ở vị trí khác.

**10. Hardcode cột lỗi trong golden test áp dụng mọi StAX implementations.**  
Không portable; kiểm tra lỗi xảy ra, vị trí hợp lý khi được báo.

**11. Tạo exception mới chỉ có message, bỏ mất cause.**  
Dùng constructor có `Location` và `Throwable` khi thích hợp.

**12. Không gắn vị trí cho lỗi nghiệp vụ khi đang parse event.**  
Snapshot current Location để người dùng sửa đúng trường.

**13. Dùng `catch (Exception)` rồi coi lỗi encoding, I/O và domain đều là XML syntax.**  
Phân loại đúng lỗi và cause.

**14. Cho rằng `SUPPORT_DTD=false` luôn ném lỗi với DOCTYPE.**  
Nó có thể chỉ tắt processing; thêm kiểm tra event `DTD` nếu muốn cấm.

**15. Không tắt external entities hoặc không có resolver chặn.**  
XML từ nguồn không tin cậy có thể gây XXE/SSRF/local-file access.

**16. Nuốt lỗi cấu hình security properties.**  
Nếu provider không hỗ trợ setting, phải fail closed.

**17. Không giới hạn kích thước/depth/event count.**  
StAX streaming không tự chống mọi resource exhaustion.

**18. Tưởng `reader.close()` cũng đóng FileInputStream.**  
Javadoc quy định không đóng underlying source; caller phải đóng.

**19. Để close failure ghi đè parse failure.**  
Giữ original exception, gắn close failure qua `addSuppressed`.

**20. Trả raw systemId/stacktrace ra UI.**  
Có thể lộ đường dẫn, URL nội bộ hoặc secrets. Redact và dùng document identifier an toàn.

**21. Coi XMLStreamException là unchecked.**  
Nó là checked exception extends Exception.

**22. Coi StAX Location có thể dùng để seek/backtrack trong XMLStreamReader.**  
Cursor API đọc tiến; Location chỉ là metadata.

**23. So `getLineNumber()` với số dòng của file đã bị normalize/transform mà không mapping.**  
Vị trí có thể tương ứng nguồn parser đã nhận, không nhất thiết file hiển thị ban đầu.

**24. Test chỉ valid XML.**  
Cần mismatched tags, missing close, duplicates, undeclared namespace, DTD/external cases.

## 12. Câu hỏi tự kiểm tra

**1. Lỗi chuẩn StAX có tên gì?**  
`javax.xml.stream.XMLStreamException`.

**2. Đó có phải checked exception không?**  
Có; nó extends `Exception`.

**3. Lấy dòng/cột từ XMLStreamException thế nào?**  
Qua `Location loc = ex.getLocation()`, kiểm tra null, rồi gọi `loc.getLineNumber()/getColumnNumber()`.

**4. Nếu Location null thì sao?**  
Hiển thị vị trí không rõ và vẫn giữ exception/cause.

**5. `-1` trong Location nghĩa là gì?**  
Vị trí không được cung cấp.

**6. Offset với Reader và InputStream khác thế nào?**  
Character source dùng character offset; byte source có thể dùng byte offset.

**7. `XMLStreamReader.getLocation()` có ổn định khi parser gọi next tiếp không?**  
Không được dựa vào. Chụp snapshot trước next.

**8. `XMLEvent.getLocation()` thì sao?**  
Non-volatile, gắn với event.

**9. Cách tạo lỗi nghiệp vụ có cause và Location?**  
`new XMLStreamException(message, reader.getLocation(), cause)`.

**10. Có nên parse exception message bằng regex để lấy tọa độ không?**  
Không; dùng Location.

**11. `getElementText()` để reader ở đâu khi thành công?**  
Ở matching `END_ELEMENT`.

**12. Tại sao phải từ chối DTD/external entities cho XML không tin cậy?**  
Để ngăn XXE, file/network access không mong muốn và entity abuse.

**13. `SUPPORT_DTD=false` có đủ để luôn từ chối DOCTYPE không?**  
Không nhất thiết; check `DTD` event theo security policy.

**14. `XMLStreamReader.close()` có đóng underlying InputStream không?**  
Không. Input owner phải đóng.

**15. Tại sao dùng `addSuppressed` nếu close cũng lỗi?**  
Để giữ parse failure chính và vẫn ghi nhận lỗi cleanup.

**16. Tại sao 35 PASS của fixture không bảo đảm mọi provider báo cùng vị trí lỗi?**  
Vì implementation có thể chọn vị trí phát hiện khác hoặc thiếu optional Location fields.

## 13. Tài liệu chính thức còn hiệu lực

- [Java SE 26 — `XMLStreamException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLStreamException.html): constructors, getLocation, nested cause và checked exception.
- [Java SE 26 — `Location`](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/Location.html): optional line/column/offset/publicId/systemId, byte vs character offset.
- [Java SE 26 — `XMLStreamReader`](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLStreamReader.html): current cursor, next, getElementText, Location lifecycle và close.
- [Java SE 26 — `XMLInputFactory`](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLInputFactory.html): XML reader factories và DTD/external entity properties.
- [Java SE 26 — `XMLResolver`](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLResolver.html): external reference resolution.
- [Java SE 26 — `XMLEventReader`](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLEventReader.html): event reader.
- [Java SE 26 — `XMLEvent`](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/events/XMLEvent.html): non-volatile event location.
- [Java SE 26 — `XMLStreamConstants`](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLStreamConstants.html): START_ELEMENT, END_ELEMENT, DTD và các loại events.
- [OWASP — XML External Entity Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html): bảo vệ parser khỏi XXE và external resources.

**Ghi nhớ:** Khi StAX ném `XMLStreamException`, dùng **`getLocation()`** để có thông tin dòng/cột/offset **nếu có**, không phân tích message và không giả định vị trí tuyệt đối trên mọi parser. Chụp snapshot `XMLStreamReader` trước khi gọi `next()`, giữ causes, từ chối external entities/DTD khi XML chưa tin cậy và đóng parser/input đúng ownership.
