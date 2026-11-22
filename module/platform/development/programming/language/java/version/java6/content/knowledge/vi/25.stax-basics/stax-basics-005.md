# Đọc attribute và nội dung văn bản bằng StAX trong Java

**StAX (Streaming API for XML)** là API xử lý XML theo dòng sự kiện (*pull parsing*) trong module `java.xml` của Java. Khác với DOM, StAX có thể đọc tuần tự một tài liệu XML mà **không bắt buộc tạo cây DOM của toàn bộ tài liệu**. Bài học này tập trung hai thao tác cốt lõi: **đọc attribute tại thẻ mở** và **thu thập đúng nội dung văn bản của element**.

Với StAX, bạn thường lựa chọn một trong hai mô hình:

- **Cursor API — `XMLStreamReader`:** reader đang đứng tại một event hiện tại. Gọi `next()` để dịch chuyển và các method `getAttributeValue()`, `getAttributeCount()`, `getText()`, `getElementText()` để lấy dữ liệu. Nó phù hợp khi cần xử lý tuần tự và kiểm soát chặt state.
- **Event API — `XMLEventReader`:** `nextEvent()` trả object như `StartElement`, `Characters` hoặc `EndElement`. Bạn dùng `StartElement.getAttributeByName(QName)` và `XMLEvent.asCharacters().getData()` để truy xuất dữ liệu.

**Lưu ý:** attribute là thông tin gắn với **`START_ELEMENT`**, không phải một event văn bản tương đương `CHARACTERS`. Văn bản có thể xuất hiện thành **nhiều sự kiện liên tiếp**, có thể chứa CDATA, entity references và khoảng trắng. Vì vậy, không nên giả định một lời gọi `next()` sẽ cung cấp toàn bộ nội dung một element.

Bài thuộc nhóm **StAX cơ bản**, dùng những kiến thức **vẫn áp dụng trong Java 17+ và Java SE 26**. Hai chương trình chạy được trong bài đã được **biên dịch với `javac --release 17` và thực thi trên JDK 24**; gồm các trường hợp namespace, attribute thường và có prefix, văn bản có `&amp;`, CDATA, emoji, mixed content, chuỗi rỗng, whitespace, text buffer, stream lifecycle và những cách đọc sai.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Dùng `XMLInputFactory` tạo `XMLStreamReader` hoặc `XMLEventReader` từ `Reader`/`InputStream`.
2. Hiểu cursor khởi đầu tại `START_DOCUMENT` và di chuyển qua `START_ELEMENT`, `CHARACTERS`, `END_ELEMENT`…
3. Chỉ đọc `getAttributeCount()`, `getAttributeName(int)`, `getAttributeValue(...)` tại trạng thái thích hợp.
4. Phân biệt **attribute không namespace** và **attribute có namespace**, xử lý `QName`/URI chính xác, không dựa vào prefix.
5. Biết kết quả khi attribute **không tồn tại** là `null`, khác với attribute tồn tại nhưng rỗng `""`.
6. Dùng `getElementText()` cho **text-only elements**, hiểu nó dịch chuyển cursor đến thẻ đóng và thất bại nếu gặp nested element.
7. Tự thu thập văn bản **mixed content** bằng đếm độ sâu các thẻ hoặc xử lý cấu trúc khi cần giữ markup.
8. Đọc `CHARACTERS`/`CDATA`/`SPACE`, xử lý whitespace đúng yêu cầu sản phẩm và dùng `getTextCharacters()`/`getTextStart()`/`getTextLength()` đúng phạm vi.
9. Dùng Event API `StartElement.getAttributes()`/`getAttributeByName()` và `Characters.getData()`.
10. Bảo vệ XML parser khỏi DTD/XXE bằng cấu hình `XMLInputFactory` hiện hành.
11. Đóng reader và nguồn input riêng, xử lý `XMLStreamException` và giới hạn kích thước/độ sâu khi cần.
12. Chạy hai chương trình đầy đủ với output đối chiếu được, không chỉ đọc pseudocode.

## 2. XML được StAX nhìn như thế nào?

Giả sử XML đầu vào là:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<catalog xmlns="urn:books" xmlns:m="urn:meta" version="1">
  <book id="b1" m:lang="vi" available="true">
    <title>Java &amp; XML <![CDATA[streaming]]></title>
    <description>Văn bản <em>có thẻ</em> lồng nhau.</description>
    <note>Chào 😀</note>
  </book>
</catalog>
```

Các dữ liệu đáng chú ý:

- `catalog` khai báo **default namespace** `urn:books`, nên những element không prefix như `book`, `title` thuộc namespace đó.
- `xmlns:m="urn:meta"` khai báo prefix `m` liên kết với URI `urn:meta`.
- `book` có **ba attributes thông thường**: `id`, `m:lang`, `available`.
- `xmlns` và `xmlns:m` **là namespace declarations**, không được tính như attributes thông thường trong `getAttributeCount()` của `XMLStreamReader`.
- `title` chứa escaped entity `&amp;` và một CDATA section, nhưng giá trị văn bản nhận được là `Java & XML streaming`.
- `description` chứa **mixed content**: văn bản trực tiếp + phần tử con `em` + văn bản phía sau.
- `note` chứa tiếng Việt và emoji; Java `String` vẫn hỗ trợ UTF-16/supplementary characters.

Một chuỗi sự kiện ý tưởng:

```text
START_DOCUMENT
  START_ELEMENT catalog  [namespace declarations, version="1"]
    CHARACTERS whitespace
    START_ELEMENT book   [id="b1", m:lang="vi", available="true"]
      CHARACTERS whitespace
      START_ELEMENT title
        CHARACTERS "Java & XML "
        (CDATA hoặc CHARACTERS) "streaming"
      END_ELEMENT title
      CHARACTERS whitespace
      START_ELEMENT description
        CHARACTERS "Văn bản "
        START_ELEMENT em
          CHARACTERS "có thẻ"
        END_ELEMENT em
        CHARACTERS " lồng nhau."
      END_ELEMENT description
      START_ELEMENT note
        CHARACTERS "Chào 😀"
      END_ELEMENT note
    END_ELEMENT book
  END_ELEMENT catalog
END_DOCUMENT
```

**Đây không phải danh sách event chính xác bắt buộc của mọi parser.** StAX cho phép phân chia/ghép các phần văn bản khác nhau, đặc biệt theo `XMLInputFactory.IS_COALESCING`. Whitespace riêng cũng có thể được báo theo loại event mà implementation hỗ trợ. Viết code dựa trên **ngữ nghĩa** chứ không dựa trên giả định event count.

## 3. XMLInputFactory và hai loại reader

`javax.xml.stream.XMLInputFactory` tạo các đối tượng đọc. Hai API vẫn hoạt động trên Java 17+:

```java
XMLInputFactory factory = XMLInputFactory.newFactory();

XMLStreamReader cursor = factory.createXMLStreamReader(reader);
XMLEventReader events = factory.createXMLEventReader(reader);
```

Đây là mảnh code minh họa, không phải chương trình độc lập: biến `reader` là nguồn `java.io.Reader` đã được khởi tạo. Mỗi reader StAX cần nguồn riêng hoặc nguồn được reset đúng; **không** dùng chung một Reader đang đọc dở cho cả hai.

Bảng so sánh:

| Khía cạnh | `XMLStreamReader` | `XMLEventReader` |
| --- | --- | --- |
| Cách tiến | `next()` trả mã `int`. | `nextEvent()` trả `XMLEvent`. |
| Trạng thái | Có một event hiện tại. | Duyệt các event objects; có `peek()`. |
| Thẻ bắt đầu | `event == START_ELEMENT` hoặc `isStartElement()`. | `event.isStartElement()`, `asStartElement()`. |
| Attribute | `getAttributeCount`/`getAttributeValue`/`getAttributeName`. | `StartElement.getAttributes`/`getAttributeByName`. |
| Văn bản | `getText`/`getElementText`/`getTextCharacters`. | `Characters.getData`/`XMLEventReader.getElementText`. |
| Thẻ kết thúc | `END_ELEMENT` hoặc `isEndElement()`. | `event.isEndElement()`. |
| Dòng xử lý | Ít object sự kiện hơn về ý tưởng. | Event objects dễ xử lý theo kiểu filter/dispatch. |
| Khi dữ liệu rất lớn | Có thể đọc từng event. | Cũng streaming; cần quản lý reference/copy. |

**Không tự cho rằng một API luôn nhanh hơn API còn lại trong mọi môi trường.** Driver XML parser, phiên bản JDK, kích thước tài liệu, text allocations và cách xử lý của ứng dụng quyết định hiệu năng thực.

### 3.1. Factory theo Java API, không nhầm với DOM

StAX thuộc `javax.xml.stream`, khác `javax.xml.parsers.DocumentBuilderFactory` (DOM) hoặc `SAXParserFactory` (SAX). Không gọi những method chỉ dành cho DOM, ví dụ `DocumentBuilderFactory.setFeature(...)`, trên `XMLInputFactory`. Cấu hình bảo vệ StAX được trình bày ở mục 12.

## 4. Đọc attribute bằng XMLStreamReader

`XMLStreamReader` được khởi tạo tại `START_DOCUMENT`. Gọi `next()` để tiến tới event tiếp theo, và chỉ đọc thuộc tính khi reader đứng tại **`START_ELEMENT`**.

```java
// Mảnh code, giả sử XMLStreamReader r đã tạo:
while (r.hasNext()) {
    int event = r.next();
    if (event == XMLStreamConstants.START_ELEMENT
            && r.getLocalName().equals("book")
            && r.getNamespaceURI().equals("urn:books")) {

        String id = r.getAttributeValue(null, "id");
        String language = r.getAttributeValue("urn:meta", "lang");
        int count = r.getAttributeCount();
    }
}
```

Các method tiêu biểu:

| Method | Giá trị |
| --- | --- |
| `getAttributeCount()` | Số attributes thông thường trên `START_ELEMENT`, không gồm namespace declarations. |
| `getAttributeName(i)` | `QName` của attribute tại index i. |
| `getAttributeLocalName(i)` | Local name (không gồm prefix). |
| `getAttributePrefix(i)` | Prefix trong XML, nếu có. |
| `getAttributeNamespace(i)` | Namespace URI của attribute, nếu có. |
| `getAttributeValue(i)` | Giá trị attribute tại index i. |
| `getAttributeValue(namespaceURI, localName)` | Tra theo namespace URI và local name. Trả `null` nếu không tìm thấy. |
| `getAttributeType(i)` | Kiểu XML của attribute theo parser/DTD information. |
| `isAttributeSpecified(i)` | Attribute có được chỉ định trực tiếp hay do default declaration. |

**Đừng gọi `getAttributeCount()` tại `CHARACTERS`, `END_ELEMENT` hoặc `START_DOCUMENT`**. Javadoc xác định trạng thái hợp lệ cho mỗi method; gọi sai có thể ném `IllegalStateException`.

### 4.1. Index bắt đầu từ 0; thứ tự attribute không có ý nghĩa nghiệp vụ

```java
if (r.getEventType() == XMLStreamConstants.START_ELEMENT) {
    for (int i = 0; i < r.getAttributeCount(); i++) {
        QName attributeName = r.getAttributeName(i);
        String attributeValue = r.getAttributeValue(i);
        // Xử lý theo QName + value; đừng dựa vào thứ tự.
    }
}
```

Đây là mảnh code cần import `javax.xml.namespace.QName` và `javax.xml.stream.XMLStreamConstants`. Không viết “attribute đầu tiên là id” vì **thứ tự attributes trong XML không mang ngữ nghĩa** và parser có thể trả theo thứ tự khác. Để lấy một field cụ thể, tra tên thay vì index cố định.

### 4.2. Missing attribute, empty attribute và required field

Cho hai trường hợp:

```xml
<book id="b1" enabled="" />
<book id="b2" />
```

- Với `enabled=""`, `getAttributeValue(null,"enabled")` trả `""` (empty Java String).
- Với attribute không có, method trả **`null`**.
- Không đánh đồng `null` và `""` nếu schema/ứng dụng phân biệt “missing” và “được cung cấp nhưng rỗng”.
- Nếu attribute là bắt buộc, kiểm tra rõ thay vì gọi `Long.parseLong` hoặc `Boolean.parseBoolean` ngay.

```java
String id = r.getAttributeValue(null, "id");
if (id == null || id.isBlank()) {
    throw new XMLStreamException("Missing/blank book id",
            r.getLocation());
}
```

Đây là mảnh code tích hợp, không phải chương trình độc lập. Trong production, ứng dụng cần quyết định chính sách **whitespace-only ID**; `isBlank()` dùng được trên Java 17.

### 4.3. Attribute là String, không tự thành boolean/number

`XMLStreamReader.getAttributeValue(...)` trả `String`. XML:

```xml
<book available="true" pages="12"/>
```

`available` và `pages` chưa được StAX chuyển thành kiểu Java boolean/int. Với boolean trong định dạng đã định nghĩa rõ `true/false`:

```java
String raw = r.getAttributeValue(null, "available");
if (!"true".equals(raw) && !"false".equals(raw)) {
    throw new XMLStreamException("Invalid boolean attribute",
            r.getLocation());
}
boolean available = Boolean.parseBoolean(raw);
```

`Boolean.parseBoolean("maybe")` **trả false**, không ném lỗi, nên đừng gọi trực tiếp nếu cần bắt input sai.

Với số nguyên:

```java
String pagesText = r.getAttributeValue(null, "pages");
if (pagesText == null) {
    throw new XMLStreamException("Missing pages",
            r.getLocation());
}
int pages;
try {
    pages = Integer.parseInt(pagesText);
} catch (NumberFormatException ex) {
    throw new XMLStreamException("Invalid pages", r.getLocation(), ex);
}
if (pages < 0) {
    throw new XMLStreamException("Negative pages", r.getLocation());
}
```

`Integer.parseInt` có thể ném `NumberFormatException` cho input trống, ký tự lạ hoặc vượt giới hạn int. `getLocation()` giúp báo vị trí XML liên quan.

## 5. Namespace trên element khác namespace của attribute

Với:

```xml
<book xmlns="urn:books" xmlns:m="urn:meta"
      id="b1" m:lang="vi" />
```

- Element `book` thuộc `urn:books` do **default namespace**.
- Attribute **không prefix** `id` **không tự thuộc default namespace**; nó là unqualified attribute.
- Attribute `m:lang` thuộc namespace URI `urn:meta`.
- `xmlns="urn:books"` và `xmlns:m="urn:meta"` là declarations của namespace, **không phải** ordinary attributes.
- URI, không phải chuỗi prefix `m`, mới là danh tính namespace. XML khác có thể dùng prefix `meta` nhưng cùng URI.

Ở cursor API:

```java
String lang = r.getAttributeValue("urn:meta", "lang");
String id = r.getAttributeValue(null, "id");
```

Theo Javadoc, khi `namespaceURI == null`, `getAttributeValue` **không kiểm tra namespace**. Vì vậy, `getAttributeValue(null, "lang")` có thể vô tình chọn một `lang` không đúng namespace nếu document có các attributes với cùng local name. Khi có namespace, **luôn truyền đúng namespace URI**.

Trong ví dụ cố định, `id` chỉ xuất hiện một lần và không prefix nên lookup `null` không nhập nhằng. Với XML có dữ liệu không tin cậy và nhiều namespace, nên xác minh `QName`/namespace URI cụ thể thay vì dựa vào local name.

### 5.1. QName là tên đầy đủ

`javax.xml.namespace.QName` lưu:

- Namespace URI
- Local part
- Prefix (tùy trường hợp; prefix không dùng để quyết định equality như namespace URI + local part)

Với Event API:

```java
StartElement start = event.asStartElement();
Attribute lang = start.getAttributeByName(
        new QName("urn:meta", "lang"));
String value = lang == null ? null : lang.getValue();
```

Đây là mảnh code cần import `QName`, `StartElement` và `Attribute`. `getAttributeByName` trả `null` nếu attribute không có. Tránh tự parse tên XML thành chuỗi `"m:lang"` để so với prefix cố định.

### 5.2. Đọc namespace declarations không qua attribute count

Cursor cung cấp:

```java
if (r.isStartElement()) {
    for (int i = 0; i < r.getNamespaceCount(); i++) {
        String prefix = r.getNamespacePrefix(i);
        String uri = r.getNamespaceURI(i);
        // Namespace declarations trên START_ELEMENT hiện tại.
    }
}
```

Cần lưu ý `getNamespaceCount` ở một element chỉ nói các declarations **tại element/event đó**, không phải toàn bộ namespaces trong mọi ancestor. `getNamespaceContext()` hoặc `getNamespaceURI(prefix)` phù hợp nếu cần tra mapping đang có hiệu lực từ cha.

## 6. Đọc văn bản bằng XMLStreamReader

Nội dung văn bản trong StAX không phải một field cố định trên `START_ELEMENT`. Để đọc trực tiếp từng event, duyệt tới các loại văn bản:

```java
int event = r.next();
if (event == XMLStreamConstants.CHARACTERS
        || event == XMLStreamConstants.CDATA
        || event == XMLStreamConstants.SPACE) {
    String chunk = r.getText();
}
```

API có các event types:

| Event | Ý nghĩa |
| --- | --- |
| `CHARACTERS` | Dữ liệu ký tự. |
| `CDATA` | CDATA section nếu parser báo riêng, nhưng có implementation báo như characters. |
| `SPACE` | Khoảng trắng có ý nghĩa phân loại theo parser, thường từ DTD-aware processing. |
| `ENTITY_REFERENCE` | Tham chiếu entity được báo riêng nếu không thay thế bằng character data; cần policy rõ. |
| `COMMENT` | Comment, không tự thuộc giá trị văn bản của element. |
| `PROCESSING_INSTRUCTION` | Processing instruction; không phải text nội dung thông thường. |
| `START_ELEMENT` / `END_ELEMENT` | Cấu trúc thẻ, dùng để xác định phạm vi thu thập text. |

Với `XMLInputFactory.IS_COALESCING` đặt `true`, parser được yêu cầu **gộp contiguous character data và CDATA** thành những sự kiện văn bản thích hợp. Nếu `false`, các chunks có thể tách. **Không viết code dựa vào số lượng chunks**: XML parser vẫn có thể tách văn bản theo ranh giới buffer/input.

### 6.1. Escaped entity và CDATA

XML:

```xml
<title>Java &amp; XML <![CDATA[streaming]]></title>
```

Ở mức text, kết quả là:

```text
Java & XML streaming
```

`&amp;` được parser chuyển thành ký tự `&`. CDATA giữ các ký tự literal trong source cho đến `]]>`, nhưng khi đọc **text content**, các ký tự đó vẫn là nội dung văn bản. `getElementText` trả văn bản đã được hợp nhất, không trả chuỗi lexical `<![CDATA[...]]>`.

**Không đồng nhất text content với XML source nguyên văn.** Nếu bạn cần round-trip bảo toàn CDATA boundaries, khoảng trắng trong source, thứ tự attributes, comments hoặc quote styles, chỉ ghép `getText()` sẽ **không đủ**. Hãy chọn một giải pháp phù hợp với yêu cầu về XML serialization/canonicalization, không dùng StAX text-only extraction để giả định giữ nguyên toàn bộ byte đầu vào.

### 6.2. Khoảng trắng có phải dữ liệu?

Ví dụ:

```xml
<note>  Xin chào  </note>
```

Giá trị văn bản có **hai khoảng trắng trước/sau**, và đó có thể là dữ liệu nghiệp vụ. `getElementText()` thường trả text **giữ nguyên nội dung whitespace**. Không tự gọi `trim()`/`strip()` khi cần bảo toàn chính xác.

Ngược lại, indentation giữa các child elements như:

```xml
<catalog>
    <book/>
</catalog>
```

cũng có thể tạo `CHARACTERS` whitespace-only events. Khi chỉ duyệt cây element, có thể bỏ qua loại whitespace-only bằng `r.isWhiteSpace()` hoặc dùng `nextTag()`, **nhưng chỉ khi thiết kế XML thực sự thuộc loại element-only content**.

**Sai lầm điển hình:** bỏ qua tất cả text chunks mà `isWhiteSpace()==true` rồi áp dụng cho `<note>  </note>`, khiến dữ liệu là hai dấu cách bị mất.

## 7. getElementText(): tiện nhưng chỉ cho text-only element

Cách đọc nhanh nội dung của element không chứa child elements:

```java
if (r.isStartElement() && r.getLocalName().equals("title")) {
    String text = r.getElementText();
}
```

**Tiền điều kiện:** cursor đang ở `START_ELEMENT`.

**Hậu điều kiện:** cursor được đặt ở `END_ELEMENT` tương ứng sau khi method hoàn tất thành công.

`getElementText()` đọc các character events, CDATA, SPACE, entity reference được resolve và có thể bỏ qua comment/processing instruction theo contract. Nó trả **content đã gộp**, không phụ thuộc `IS_COALESCING`. Với element rỗng `<empty/>`, kết quả là **`""`**.

**Không dùng trên mixed content** có child tags:

```xml
<description>Văn bản <em>có thẻ</em> lồng nhau.</description>
```

Một lời gọi `getElementText()` tại `<description>` sẽ ném `XMLStreamException` khi gặp `<em>`, bởi đây **không còn là text-only element**. Ví dụ chính kiểm chứng trường hợp này.

### 7.1. Tránh nhảy qua thẻ sau getElementText

Nếu bạn đang ở `START_ELEMENT title` và gọi `r.getElementText()`, cursor đã chuyển tới **`END_ELEMENT title`**. Vòng `while(r.hasNext()) { int type=r.next(); ... }` thông thường sẽ tiếp tục từ sau thẻ đóng, không cần một lời gọi `next()` khác ngay trong nhánh `title`.

Ngược lại, gọi `next()` ngay sau một `getElementText` chỉ để “bỏ qua thẻ đóng” có thể làm bạn **bỏ mất event kế tiếp**.

### 7.2. Khi nào không nên dùng getElementText?

- Element có child elements (mixed content).
- Document có text quá dài và cần streaming **không tạo một `String` chứa toàn bộ**.
- Cần giữ comments, CDATA boundaries hoặc markup bên trong.
- Cần xử lý từng chunk với giới hạn kích thước sớm.
- Cần phân biệt text trực tiếp của parent và text của descendant.

## 8. Đọc mixed content bằng đếm độ sâu

Nếu XML có nội dung vừa văn bản vừa thẻ con:

```xml
<description>Văn bản <em>có thẻ</em> lồng nhau.</description>
```

và yêu cầu ứng dụng là **chỉ lấy text của toàn bộ subtree**, một cách là duyệt các events với `depth`:

```java
// Method minh họa, cần XMLStreamReader đang ở START_ELEMENT.
// Bỏ markup nhưng giữ thứ tự văn bản của subtree.
static String mixedText(XMLStreamReader r) throws XMLStreamException {
    int depth = 1;
    StringBuilder result = new StringBuilder();
    while (r.hasNext()) {
        int event = r.next();
        if (event == XMLStreamConstants.START_ELEMENT) {
            depth++;
        } else if (event == XMLStreamConstants.END_ELEMENT) {
            if (--depth == 0) return result.toString();
        } else if (event == XMLStreamConstants.CHARACTERS
                || event == XMLStreamConstants.CDATA
                || event == XMLStreamConstants.SPACE) {
            result.append(r.getText());
        } else if (event == XMLStreamConstants.ENTITY_REFERENCE) {
            throw new XMLStreamException(
                    "Unexpected entity reference in restricted parser");
        }
    }
    throw new XMLStreamException("Missing closing element");
}
```

Trả về:

```text
Văn bản có thẻ lồng nhau.
```

Ý nghĩa `depth`:

1. Bắt đầu ở `START_ELEMENT description` nên `depth=1`.
2. Gặp `START_ELEMENT em` tăng lên 2.
3. Gặp `END_ELEMENT em` giảm còn 1; **chưa kết thúc description**.
4. Gặp `END_ELEMENT description` giảm về 0, trả text.
5. Các chunks `CHARACTERS` giữ thứ tự xuất hiện.

**Đây là phép trích xuất text của cả subtree**, không phải chỉ text trực tiếp của `description`. Nếu muốn chỉ văn bản trực tiếp, chỉ append khi `depth==1`; khi đó kết quả là `"Văn bản  lồng nhau."` (có thể có hai khoảng trắng cạnh nhau vì bỏ text của child). Nếu cần giữ markup `<em>`, phải xây output có cấu trúc hoặc dùng XML writer, không chỉ `StringBuilder`.

### 8.1. Guard chống tài liệu quá sâu hoặc quá lớn

Với XML từ nguồn không tin cậy, có thể giới hạn depth và lượng text tích lũy:

```java
if (depth > 64) {
    throw new XMLStreamException("XML nesting too deep");
}
if (result.length() > 1_000_000) {
    throw new XMLStreamException("Text too large");
}
```

Giới hạn ở trên là **chính sách ví dụ**, không phải giới hạn JDBC/StAX chung. Trong production, kiểm soát kích thước **trước khi append** để không vượt giới hạn nhiều nếu một chunk quá lớn, và cân nhắc stream output sang downstream consumer thay vì giữ một `StringBuilder` khổng lồ.

## 9. Ví dụ đầy đủ: Cursor và Event API trên cùng một XML

Chương trình sau dùng một tài liệu XML có namespace, attributes, escaped `&amp;`, CDATA, mixed content và emoji. Nó minh họa **hai cách đọc** cùng dữ liệu với hai readers độc lập. Cuối cùng, nó cố ý gọi `getElementText()` trên element lồng thẻ để xác nhận `XMLStreamException`.

**Tệp:** `StaxAttributeTextDemo.java`

```java
import java.io.StringReader;
import javax.xml.XMLConstants;
import javax.xml.namespace.QName;
import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLStreamConstants;
import javax.xml.stream.XMLStreamException;
import javax.xml.stream.XMLStreamReader;
import javax.xml.stream.XMLEventReader;
import javax.xml.stream.events.Attribute;
import javax.xml.stream.events.StartElement;
import javax.xml.stream.events.XMLEvent;

public final class StaxAttributeTextDemo {
    private static final String XML = """
            <?xml version="1.0" encoding="UTF-8"?>
            <catalog xmlns="urn:books" xmlns:m="urn:meta" version="1">
              <book id="b1" m:lang="vi" available="true">
                <title>Java &amp; XML <![CDATA[streaming]]></title>
                <description>Văn bản <em>có thẻ</em> lồng nhau.</description>
                <note>Chào 😀</note>
              </book>
            </catalog>
            """;

    private static XMLInputFactory factory() {
        XMLInputFactory f = XMLInputFactory.newFactory();
        f.setProperty(XMLInputFactory.IS_NAMESPACE_AWARE, true);
        f.setProperty(XMLInputFactory.IS_COALESCING, false);
        f.setProperty(XMLInputFactory.SUPPORT_DTD, false);
        f.setProperty(XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
        f.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        return f;
    }

    private static String mixedText(XMLStreamReader r) throws XMLStreamException {
        int depth = 1;
        StringBuilder result = new StringBuilder();
        while (r.hasNext()) {
            int event = r.next();
            if (event == XMLStreamConstants.START_ELEMENT) {
                depth++;
            } else if (event == XMLStreamConstants.END_ELEMENT) {
                if (--depth == 0) return result.toString();
            } else if (event == XMLStreamConstants.CHARACTERS
                    || event == XMLStreamConstants.CDATA
                    || event == XMLStreamConstants.SPACE) {
                result.append(r.getText());
            } else if (event == XMLStreamConstants.ENTITY_REFERENCE) {
                throw new XMLStreamException(
                        "Entity references not supported in this demo");
            }
        }
        throw new XMLStreamException("Missing closing element");
    }

    private static String mixedText(XMLEventReader r) throws XMLStreamException {
        int depth = 1;
        StringBuilder result = new StringBuilder();
        while (r.hasNext()) {
            XMLEvent event = r.nextEvent();
            if (event.isStartElement()) {
                depth++;
            } else if (event.isEndElement()) {
                if (--depth == 0) return result.toString();
            } else if (event.isCharacters()) {
                result.append(event.asCharacters().getData());
            } else if (event.isEntityReference()) {
                throw new XMLStreamException(
                        "Entity references not supported in this demo");
            }
        }
        throw new XMLStreamException("Missing closing element");
    }

    private static void cursorExample(XMLInputFactory factory) throws Exception {
        XMLStreamReader reader =
                factory.createXMLStreamReader(new StringReader(XML));
        try {
            while (reader.hasNext()) {
                int event = reader.next();
                if (event != XMLStreamConstants.START_ELEMENT) continue;
                String name = reader.getLocalName();
                if (name.equals("book")) {
                    System.out.println("cursor.book.id="
                            + reader.getAttributeValue(null, "id"));
                    System.out.println("cursor.book.lang="
                            + reader.getAttributeValue("urn:meta", "lang"));
                    System.out.println("cursor.book.available="
                            + reader.getAttributeValue(null, "available"));
                    System.out.println("cursor.attributeCount="
                            + reader.getAttributeCount());
                    System.out.println("cursor.book.namespace="
                            + reader.getNamespaceURI());
                } else if (name.equals("title")) {
                    System.out.println("cursor.title=" + reader.getElementText());
                } else if (name.equals("description")) {
                    System.out.println("cursor.description=" + mixedText(reader));
                } else if (name.equals("note")) {
                    System.out.println("cursor.note=" + reader.getElementText());
                }
            }
        } finally {
            reader.close();
        }
    }

    private static void eventsExample(XMLInputFactory factory) throws Exception {
        XMLEventReader reader =
                factory.createXMLEventReader(new StringReader(XML));
        try {
            while (reader.hasNext()) {
                XMLEvent event = reader.nextEvent();
                if (!event.isStartElement()) continue;
                StartElement start = event.asStartElement();
                String name = start.getName().getLocalPart();
                if (name.equals("book")) {
                    Attribute id = start.getAttributeByName(new QName("id"));
                    Attribute lang = start.getAttributeByName(
                            new QName("urn:meta", "lang"));
                    System.out.println("event.book.id="
                            + (id == null ? "missing" : id.getValue()));
                    System.out.println("event.book.lang="
                            + (lang == null ? "missing" : lang.getValue()));
                } else if (name.equals("title")) {
                    System.out.println("event.title=" + reader.getElementText());
                } else if (name.equals("description")) {
                    System.out.println("event.description=" + mixedText(reader));
                } else if (name.equals("note")) {
                    System.out.println("event.note=" + reader.getElementText());
                }
            }
        } finally {
            reader.close();
        }
    }

    private static void negativeExample(XMLInputFactory factory) throws Exception {
        XMLStreamReader reader = factory.createXMLStreamReader(
                new StringReader("<p>hello <b>world</b></p>"));
        try {
            while (reader.hasNext()) {
                int event = reader.next();
                if (event == XMLStreamConstants.START_ELEMENT) {
                    try {
                        reader.getElementText();
                        throw new AssertionError(
                                "Expected getElementText to reject nested element");
                    } catch (XMLStreamException expected) {
                        System.out.println("nested.getElementText=REJECTED");
                    }
                    break;
                }
            }
        } finally {
            reader.close();
        }
    }

    public static void main(String[] args) throws Exception {
        XMLInputFactory f = factory();
        cursorExample(f);
        eventsExample(f);
        negativeExample(f);
    }
}
```

### 9.1. Biên dịch và chạy

Tạo file UTF-8 không BOM có tên chính xác `StaxAttributeTextDemo.java`, sau đó:

```bash
javac --release 17 -encoding UTF-8 StaxAttributeTextDemo.java
java StaxAttributeTextDemo
```

Chỉ cần JDK 17+; code dùng **text blocks** và `StringReader`, không cần external XML library hoặc database.

### 9.2. Stdout chính xác đã kiểm chứng trên JDK 24

```text
cursor.book.id=b1
cursor.book.lang=vi
cursor.book.available=true
cursor.attributeCount=3
cursor.book.namespace=urn:books
cursor.title=Java & XML streaming
cursor.description=Văn bản có thẻ lồng nhau.
cursor.note=Chào 😀
event.book.id=b1
event.book.lang=vi
event.title=Java & XML streaming
event.description=Văn bản có thẻ lồng nhau.
event.note=Chào 😀
nested.getElementText=REJECTED
```

**14 dòng stdout.** Tệp này đã được biên dịch `--release 17` và chạy trên JDK 24; cấu hình namespace, attributes và dữ liệu text đều được kiểm chứng.

### 9.3. Giải thích điểm quan trọng

**`cursor.book.id=b1`:** `getAttributeValue(null,"id")` tìm attribute không nhập nhằng trong fixture. Nếu nguồn XML có nhiều namespace và trùng local name, phải dùng URI cụ thể để tránh lấy sai attribute.

**`cursor.book.lang=vi`:** `getAttributeValue("urn:meta","lang")` dùng namespace URI, **không** dùng `"m:lang"` làm local name. Attribute có prefix được truy cập bằng URI + local part.

**`cursor.attributeCount=3`:** chỉ đếm `id`, `m:lang`, `available`; namespace declarations `xmlns`/`xmlns:m` không nằm trong số ba ordinary attributes.

**`cursor.book.namespace=urn:books`:** default namespace áp dụng cho element `book`; không tự áp cho attribute không prefix `id`.

**`cursor.title=Java & XML streaming`:** `&amp;` được unescape thành `&`, CDATA được đọc như văn bản. `getElementText()` tự tổng hợp text chunks của element chỉ chứa văn bản.

**`cursor.description=Văn bản có thẻ lồng nhau.`:** `mixedText` dùng depth để thu text từ cả descendants; không cố dùng `getElementText` trên phần tử lồng thẻ.

**`cursor.note=Chào 😀`:** Java String hỗ trợ Unicode, including emoji. Khi dùng `StringReader`, không có byte-encoding conversion trong bước đọc; code vẫn có XML declaration để định dạng minh họa rõ ràng.

**`event.*`:** Event API dùng `StartElement.getAttributeByName(QName)` và `XMLEventReader.getElementText()`/`Characters.getData()` tương đương. Code minh họa chỉ so local part với names trên **fixture cố định**; production nên xác thực cả namespace URI/`QName` khi input không tin cậy.

**`nested.getElementText=REJECTED`:** cách đọc text-only bị từ chối khi gặp `START_ELEMENT b`. Đây là lỗi **dùng sai API cho mixed content**, không chứng minh XML đầu vào malformed — XML `<p>hello <b>world</b></p>` là hợp lệ.

### 9.4. Giới hạn của ví dụ

- `mixedText` xây `StringBuilder` cho toàn bộ subtree, nên không phù hợp với văn bản vô hạn; thêm size limits hoặc stream output nếu cần.
- Code xử lý XML fixture đã biết cấu trúc; với format nhiều namespace/element cùng tên, validate qualified names và schema cụ thể.
- Cấu hình security dùng JDK StAX implementation hỗ trợ các property được đặt. Provider khác phải được kiểm chứng; đừng silently bỏ security property nếu provider từ chối.
- Không đo thời gian thực thi/heap; ví dụ chỉ kiểm chứng API và output.
- Đọc text khác với bảo toàn markup/serialization gốc.

## 10. XMLEventReader: attribute qua StartElement và văn bản qua Characters

Event API không có “cursor đứng ở một START_ELEMENT” như XMLStreamReader. `XMLEventReader.nextEvent()` trả một `XMLEvent`, và bạn chuyển thành subtype khi kiểm tra đúng loại:

```java
XMLEvent event = events.nextEvent();
if (event.isStartElement()) {
    StartElement start = event.asStartElement();
    QName name = start.getName();
    Attribute id = start.getAttributeByName(new QName("id"));
}
if (event.isCharacters()) {
    String chunk = event.asCharacters().getData();
}
```

Các API quan trọng:

| Interface/method | Mục đích |
| --- | --- |
| `XMLEvent.isStartElement()` | Kiểm tra event có phải start element. |
| `XMLEvent.asStartElement()` | Lấy `StartElement` từ event đúng loại. |
| `StartElement.getName()` | `QName` của element. |
| `StartElement.getAttributes()` | `Iterator<Attribute>` của attributes thông thường. |
| `StartElement.getAttributeByName(QName)` | Tìm attribute theo QName. |
| `StartElement.getNamespaces()` | Namespace declarations xuất hiện tại element. |
| `XMLEvent.isCharacters()` | Kiểm tra character event. |
| `XMLEvent.asCharacters().getData()` | Lấy text data. |
| `Characters.isCData()` / `isWhiteSpace()` | Phân biệt CDATA/whitespace khi parser cung cấp đặc tính đó. |
| `XMLEventReader.peek()` | Xem event kế tiếp mà không tiêu thụ nó. |
| `XMLEventReader.getElementText()` | Đọc text-only content sau StartElement đã lấy từ reader, bỏ qua các event cần thiết. |
| `XMLEventReader.nextTag()` | Tiến tới start/end tag khi content phù hợp. |

### 10.1. Không dựa vào thứ tự Iterator attributes

`StartElement.getAttributes()` trả một iterator có thể duyệt tất cả attributes thông thường, **nhưng thứ tự của attributes không được bảo đảm có ý nghĩa**. Với dữ liệu cần một attribute cụ thể, dùng `getAttributeByName`.

```java
Iterator<Attribute> attrs = start.getAttributes();
while (attrs.hasNext()) {
    Attribute attr = attrs.next();
    QName qname = attr.getName();
    String value = attr.getValue();
    // Ghi nhận QName + value, không dựa index cố định.
}
```

Mảnh code cần import `java.util.Iterator`, `Attribute`, `QName`. Chỉ dùng iterator khi bạn cần duyệt tất cả properties, không cần để đọc từng field xác định.

### 10.2. Event-based getElementText cũng có điều kiện

Với `XMLEventReader`, gọi `getElementText()` **ngay sau khi đã lấy `StartElement`** thích hợp từ `nextEvent()`; method sẽ tiêu thụ nội dung đến end tag tương ứng. Nếu child elements xuất hiện, nó ném `XMLStreamException`.

Đừng gọi `events.nextEvent()` trước để “đi vào text” rồi mới `events.getElementText()`; bạn có thể phá tiền điều kiện và làm parser bỏ event.

## 11. Edge cases: empty text, whitespace, buffer và nextTag

StAX thường phát ra các trường hợp dễ bị hiểu sai:

- `<empty/>` có **START_ELEMENT và END_ELEMENT riêng**, không tạo một text chunk rỗng bắt buộc.
- `getElementText()` trên `<empty/>` trả `""`.
- `getAttributeValue(...,"missing")` trả `null`.
- `nextTag()` bỏ qua whitespace, comments và processing instructions để tìm START/END tag; nó **không** được dùng khi có non-whitespace text đáng kể.
- `getTextCharacters()` có thể trả một array chứa nhiều ký tự không thuộc event hiện tại, kết hợp với offset/length.
- `XMLStreamReader.close()` không đảm bảo đóng `Reader`/`InputStream` đã cấp, nên quản lý nguồn input riêng.

Ví dụ thứ hai kiểm chứng tất cả những điểm này.

### 11.1. File `StaxEdgeCases.java`

```java
import java.io.StringReader;
import javax.xml.XMLConstants;
import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLStreamConstants;
import javax.xml.stream.XMLStreamException;
import javax.xml.stream.XMLStreamReader;

public final class StaxEdgeCases {
    static XMLInputFactory factory() {
        XMLInputFactory f = XMLInputFactory.newFactory();
        f.setProperty(XMLInputFactory.IS_NAMESPACE_AWARE, true);
        f.setProperty(XMLInputFactory.SUPPORT_DTD, false);
        f.setProperty(XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
        f.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        return f;
    }

    static void check(String name, boolean condition) {
        if (!condition) throw new AssertionError(name);
        System.out.println(name + "=PASS");
    }

    static final class TrackReader extends StringReader {
        boolean closed;
        TrackReader(String source) { super(source); }
        @Override public void close() { closed = true; super.close(); }
    }

    public static void main(String[] args) throws Exception {
        XMLInputFactory f = factory();
        TrackReader stream = new TrackReader(
                "<root xmlns='urn:root' id='7'>\n  <!-- a -->\n  <empty/>\n"
                + "  <text>  A&amp;B 😀  </text>\n</root>");
        XMLStreamReader r = f.createXMLStreamReader(stream);
        try {
            check("startAtDocument",
                    r.getEventType() == XMLStreamConstants.START_DOCUMENT);
            check("rootTag",
                    r.nextTag() == XMLStreamConstants.START_ELEMENT
                    && r.getLocalName().equals("root"));
            check("missingAttribute",
                    r.getAttributeValue(null, "missing") == null);
            check("idValue",
                    "7".equals(r.getAttributeValue(null, "id")));
            check("skipsWhitespaceAndComment",
                    r.nextTag() == XMLStreamConstants.START_ELEMENT
                    && r.getLocalName().equals("empty"));
            check("emptyElementText", r.getElementText().isEmpty());
            check("nextTagToText",
                    r.nextTag() == XMLStreamConstants.START_ELEMENT
                    && r.getLocalName().equals("text"));

            StringBuilder text = new StringBuilder();
            while (r.hasNext()) {
                int event = r.next();
                if (event == XMLStreamConstants.CHARACTERS
                        || event == XMLStreamConstants.CDATA
                        || event == XMLStreamConstants.SPACE) {
                    char[] chars = r.getTextCharacters();
                    int start = r.getTextStart();
                    int length = r.getTextLength();
                    String slice = new String(chars, start, length);
                    if (!slice.equals(r.getText()))
                        throw new AssertionError("buffer mismatch");
                    text.append(slice);
                } else if (event == XMLStreamConstants.END_ELEMENT
                        && r.getLocalName().equals("text")) {
                    break;
                }
            }
            check("textExact", "  A&B 😀  ".equals(text.toString()));
        } finally {
            r.close();
        }
        check("closeDoesNotCloseReader", !stream.closed);
        stream.close();
        check("manualReaderClose", stream.closed);

        XMLStreamReader mixed = f.createXMLStreamReader(
                new StringReader("<root>text<child/></root>"));
        try {
            mixed.nextTag();
            try {
                mixed.nextTag();
                throw new AssertionError("Expected nextTag to reject text");
            } catch (XMLStreamException expected) {
                System.out.println("nextTagRejectsText=PASS");
            }
        } finally {
            mixed.close();
        }
    }
}
```

### 11.2. Biên dịch và chạy

```bash
javac --release 17 -encoding UTF-8 StaxEdgeCases.java
java StaxEdgeCases
```

**Stdout chính xác từ JDK 24:**

```text
startAtDocument=PASS
rootTag=PASS
missingAttribute=PASS
idValue=PASS
skipsWhitespaceAndComment=PASS
emptyElementText=PASS
nextTagToText=PASS
textExact=PASS
closeDoesNotCloseReader=PASS
manualReaderClose=PASS
nextTagRejectsText=PASS
```

**11/11 checks PASS.** Ví dụ chứng minh `getTextCharacters` cần offset/length và `getText` có nội dung trùng đúng với slice. Đồng thời, trong JDK implementation được thử, `XMLStreamReader.close()` không đóng source `Reader`. Theo contract, ứng dụng nên quản lý source independently.

### 11.3. getTextCharacters: transient buffer

`XMLStreamReader.getTextCharacters()` có thể cho một `char[]` **tạm thời** do parser sở hữu. Để đọc đúng chunk hiện tại, phải dùng:

```java
char[] buffer = r.getTextCharacters();
int offset = r.getTextStart();
int count = r.getTextLength();
String data = new String(buffer, offset, count);
```

**Không** dùng `new String(buffer)` vì array có thể chứa dữ liệu không thuộc current event. **Không sửa buffer** vì Javadoc yêu cầu nó được xem như read-only. **Không giữ reference của mảng sau khi gọi `r.next()`**, vì parser có thể tái sử dụng bộ nhớ.

Với input lớn, có overload `getTextCharacters(int sourceStart, char[] target, int targetStart, int length)` để copy một phần sang buffer do ứng dụng sở hữu. Nhưng đó vẫn là **text của current event**, không bao phủ tất cả events của element; bạn phải lặp qua events nếu cần toàn bộ nội dung.

### 11.4. nextTag chỉ dùng cho element-only content

Tài liệu có:

```xml
<root>
  <!-- comment -->
  <child/>
</root>
```

`nextTag()` có thể bỏ qua indentation và comment, tiến tới `START_ELEMENT child`.

Nhưng:

```xml
<root>text<child/></root>
```

Có non-whitespace text `"text"`, nên `nextTag()` **không được dùng** để nhảy qua dữ liệu đó; theo API nó ném `XMLStreamException`. Nếu bạn chỉ muốn bỏ qua text bằng mục đích rõ ràng, hãy dùng `next()` và xử lý/ghi nhận văn bản trước, không dùng `nextTag()` sai hợp đồng.

## 12. Bảo mật XML: cấu hình StAX chống XXE/DTD

XML từ HTTP upload, message queue, database hoặc dịch vụ khác có thể chứa **DOCTYPE**, external entity references, expansion bombs hoặc payload quá lớn. Nếu không có bảo vệ, parser có thể truy cập file/network ngoài ý muốn (XXE/SSRF) hoặc tốn nhiều CPU/RAM.

Một cấu hình StAX dựa trên các API còn áp dụng:

```java
XMLInputFactory factory = XMLInputFactory.newFactory();
factory.setProperty(XMLInputFactory.IS_NAMESPACE_AWARE, true);
factory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
factory.setProperty(XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
```

Các settings này được sử dụng trong cả hai chương trình đã chạy.

| Setting | Tác dụng |
| --- | --- |
| `IS_NAMESPACE_AWARE=true` | Cho parser nhận biết namespace URIs và qualified names. |
| `SUPPORT_DTD=false` | Yêu cầu StAX processor không hỗ trợ DTD; hữu ích giảm bề mặt tấn công. |
| `IS_SUPPORTING_EXTERNAL_ENTITIES=false` | Không resolve external parsed entities. |
| `ACCESS_EXTERNAL_DTD=""` | Không cho phép external protocols truy cập DTD/entities qua JAXP property (implementation hỗ trợ). |
| `IS_COALESCING=false/true` | Cách parser gộp text chunks; **không phải** property bảo mật. |

**Khác DOM/SAX:** StAX không hỗ trợ `XMLConstants.FEATURE_SECURE_PROCESSING` theo cách các DOM/SAX factory hỗ trợ. Không gọi `factory.setProperty(XMLConstants.FEATURE_SECURE_PROCESSING, true)` rồi coi đó là security policy StAX. Oracle JAXP Security Guide mô tả StAX cần được bảo vệ bằng DTD properties, external-access restrictions và processing limits phù hợp.

### 12.1. Fail closed khi không hỗ trợ property bảo mật

`XMLInputFactory.setProperty` có thể ném `IllegalArgumentException` với một property không được implementation hỗ trợ. Không catch rồi **bỏ qua** setting DTD/external entities khiến parser trở nên không an toàn. Nếu ứng dụng dùng provider khác ngoài JDK, hãy kiểm tra thuộc tính có hỗ trợ và hiệu lực thực tế bằng security tests.

Ngoài flags trên, với XML untrusted còn nên:

- Giới hạn input bytes, số elements, attributes, text length, nesting depth và thời gian xử lý.
- Sử dụng JDK XML processing limits hoặc configuration phù hợp với runtime, được kiểm chứng.
- Kiểm soát external URI resolvers/catal​ogs nếu nghiệp vụ thực sự cần một số tài nguyên được phép.
- Không dựa vào XML parser như cơ chế xác thực business schema; nếu phải validate XSD, cấu hình bảo vệ `SchemaFactory`/validator riêng.
- Không coi external entities đã được chặn nếu chỉ đặt `IS_COALESCING` hoặc `IS_NAMESPACE_AWARE`.
- Phân biệt error do XML malformed với error do security policy từ chối DOCTYPE.
- Kiểm thử thực tế với XML có `DOCTYPE`, external references và nested entities **trong sandbox**, tránh truy cập file hoặc network ngoài ý muốn.

### 12.2. Text content không phải nơi thực thi code

Khi đọc text:

```xml
<note>&lt;script&gt;hello&lt;/script&gt;</note>
```

StAX trả văn bản `<script>hello</script>`; parser **không tự thực thi JavaScript**. Nhưng nếu ứng dụng đưa text này vào HTML mà không escape đúng ngữ cảnh, có thể tạo XSS. Vì vậy, **XML decoding không thay thế output encoding** ở HTML/SQL/URL/logs. Với SQL, dùng prepared statements; với HTML, escape theo HTML context.

## 13. Đọc input stream và quản lý tài nguyên

StAX reader có method `close()`, nhưng điều đó **không được dùng để suy rằng file/InputStream/Reader gốc đã đóng**. Khi tự mở input source, bạn phải tự quản lý nó.

Ví dụ cấu trúc xử lý file XML UTF-8 trong ứng dụng:

```java
// Mảnh code, imports java.nio.file.*, java.io.*,
// javax.xml.stream.*; factory đã được cấu hình an toàn.
try (InputStream input = Files.newInputStream(path)) {
    XMLStreamReader r = factory.createXMLStreamReader(input);
    try {
        while (r.hasNext()) {
            int event = r.next();
            // Đọc attribute / text theo START_ELEMENT hoặc CHARACTERS.
        }
    } finally {
        r.close();
    }
}
```

`InputStream` trong try-with-resources được đóng **ngoài** reader.close(). Đối với nguồn byte, parser có thể suy luận encoding từ BOM/XML declaration theo XML rules; nếu áp dụng một encoding cưỡng bức vào `Reader` từ bên ngoài, cần bảo đảm khớp nội dung thật.

### 13.1. Reader và InputStream khác nhau

- `createXMLStreamReader(Reader)`: ứng dụng cung cấp **characters đã được decode**, phù hợp khi biết encoding ở tầng đọc input và muốn chủ động kiểm soát malformed byte sequences.
- `createXMLStreamReader(InputStream)`: parser nhận **bytes**, có thể dùng BOM/XML declaration để xử lý encoding theo XML rules.
- Trong test `StringReader`, không thể kết luận gì về một file UTF-8/UTF-16 bị lỗi encoding; dữ liệu đã là Java String.
- File chứa UTF-8 không hợp lệ nên được test riêng bằng `InputStream` và decoder strict nếu yêu cầu; không tự cho rằng parser luôn thay thế ký tự theo cùng policy.

### 13.2. XMLStreamException có vị trí lỗi

`XMLStreamException` có thể cung cấp `getLocation()`. Nếu có, có thể lấy line/column, nhưng chúng chỉ mang ý nghĩa tương đối với source mà parser báo. Không giả định vị trí luôn đầy đủ hoặc là offset của original network bytes.

```java
try {
    // Đọc XML từ StAX.
} catch (XMLStreamException ex) {
    var location = ex.getLocation();
    int line = location == null ? -1 : location.getLineNumber();
    int column = location == null ? -1 : location.getColumnNumber();
    // Log type, line, column và một correlation ID an toàn.
    // Tránh log nguyên XML chứa PII hoặc secrets.
    throw ex;
}
```

Đây là mảnh code được đặt trong method `throws XMLStreamException`, không phải chương trình độc lập. `var` dùng được trong Java 17.

### 13.3. Reader đã đóng thì không được next tiếp

`XMLStreamReader.close()` giải phóng resource liên quan đến parser; đừng gọi thêm `next()` hay `getText()` sau khi close. Ngược lại, nếu bạn sở hữu file handle, dùng thêm try-with-resources để bảo đảm source không leak ngay cả khi parser ném lỗi.

## 14. Hiệu năng và dữ liệu văn bản lớn

StAX phù hợp để đọc XML lớn nhưng không tự bảo đảm memory cực nhỏ nếu code gom hết text vào một `StringBuilder` hoặc dùng `getElementText()` trên một element chứa hàng trăm MB text.

### 14.1. Chọn cách đọc theo nhu cầu

| Trường hợp | Cách đọc | Vì sao |
| --- | --- | --- |
| Attribute ngắn | `getAttributeValue(...)`. | Truy xuất trực tiếp lúc START_ELEMENT. |
| Element text-only ngắn | `getElementText()`. | Tiện, tự gộp chunks. |
| Element mixed content | Duyệt `next()` và depth. | Cần xử lý START/END lồng nhau. |
| Text dài, muốn stream | Duyệt CHARACTERS/CDATA events, xử lý chunks ngay. | Tránh tạo full String. |
| Chỉ cần element tags | `nextTag()` khi content element-only. | Bỏ qua whitespace/comments hợp lệ. |
| Cần mọi attributes | `getAttributeCount()` + loop hoặc `StartElement.getAttributes()`. | Không phụ thuộc thứ tự. |
| Cần namespace-aware matching | `getNamespaceURI()` + `getLocalName()` hoặc `QName`. | Prefix có thể thay đổi. |
| Cần giữ XML markup | Xây structured representation/serialize bằng XML writer. | Text-only extraction làm mất markup. |

### 14.2. Chi phí getElementText và StringBuilder

`getElementText()` trả `String`, nên cần đủ bộ nhớ cho toàn bộ nội dung. Nếu element có vài triệu ký tự, việc tạo String có thể gây memory pressure dù parser đọc streaming. Với một export/indexing job, có thể xử lý từng text event và gửi sang downstream writer/consumer rồi bỏ buffer cũ.

Đừng đo hiệu suất bằng cách lấy `System.currentTimeMillis` cho một lần chạy trên input nhỏ. Cần benchmark với realistic XML size, namespaces, text length, CDATA, encoding và provider; đo throughput/heap/GC, không chỉ một con số latency.

### 14.3. Event boundaries không phải business record boundaries

StAX có thể chia văn bản một element thành nhiều chunks. Không xem một event `CHARACTERS` là một “record hoàn chỉnh”, cũng không xem một event CDATA là một lời gọi phải tạo riêng. Business record thường được nhận diện bằng **START_ELEMENT và END_ELEMENT** của element tương ứng, sau đó tích lũy các field bên trong.

## 15. Những lỗi phổ biến và cách sửa

| Lỗi | Nguyên nhân | Cách đúng |
| --- | --- | --- |
| `getAttributeValue` ở CHARACTERS | Method chỉ hợp lệ khi có start element. | Kiểm tra `START_ELEMENT`. |
| `getAttributeCount()==0` dù có xmlns | Namespace declarations khác ordinary attributes. | Dùng `getNamespaceCount`. |
| Chọn attribute theo index 0 | XML attribute order không đáng tin. | Tìm theo QName/URI+local. |
| Tìm `"m:lang"` làm local name | Namespace prefix không thuộc local part. | Dùng `"urn:meta","lang"`. |
| Default namespace áp cho `id` | Unprefixed attribute không kế thừa default namespace. | Phân biệt element và attribute QNames. |
| `getAttributeValue(null,"lang")` luôn an toàn | Null khiến namespace không được so. | Với namespaced attribute, truyền URI. |
| Missing attribute bị coi empty | Không có trả null, empty attribute trả "". | Kiểm tra riêng. |
| Parse boolean bằng `Boolean.parseBoolean("maybe")` | Trả false thay vì throw. | Validate true/false trước. |
| Parse int không bắt lỗi | Có thể NumberFormatException. | Catch và báo XML location. |
| `getText()` chỉ lấy một chunk là đủ | Parser có thể tách văn bản nhiều events. | Duyệt tới END_ELEMENT tương ứng. |
| `getElementText()` được dùng cho mixed content | Nested START_ELEMENT gây XMLStreamException. | Dùng depth-aware event loop. |
| Gọi next sau getElementText để bỏ END | Cursor đã ở END_ELEMENT tương ứng. | Tiếp tục event loop bình thường. |
| Dùng nextTag để bỏ qua text | nextTag từ chối significant text. | Dùng next và xử lý text. |
| `getTextCharacters()` toàn mảng là content | Array có offset/length và có thể được reuse. | Dùng getTextStart/getTextLength. |
| Giữ char[] sau next | Buffer là transient. | Copy trước khi di chuyển. |
| Luôn trim/strip text | Có thể mất whitespace có nghĩa. | Làm theo schema/business policy. |
| Đếm CHARACTERS events để suy số words | Chunk boundaries phụ thuộc parser. | Ghép theo scope hoặc stream consumer. |
| Nhầm CDATA thành markup | CDATA trả text content. | Không tự khôi phục lexical CDATA. |
| Coalescing=true bảo đảm ít memory | Có thể tạo String text lớn. | Giới hạn size/stream processing. |
| Chỉ disable external entities, vẫn xử lý DTD tùy ý | Có thể có entity expansion/DTD risks. | Disable DTD, external access và limits. |
| Dùng DOM FEATURE_SECURE_PROCESSING cho StAX | StAX factory không có cùng FSP mechanism. | Dùng StAX/JAXP properties đúng. |
| Im lặng bỏ qua unsupported security property | Parser có thể chạy kém an toàn. | Fail closed và test provider. |
| Đóng XMLStreamReader rồi tưởng InputStream đã đóng | Source lifecycle độc lập. | Đóng cả hai. |
| Chỉ catch IOException khi parse | StAX thường báo XMLStreamException. | Catch XMLStreamException, lấy location. |
| Dựa vào localName, bỏ namespace trên XML untrusted | Có thể nhận nhầm element từ namespace khác. | So namespace URI + local. |
| Nghĩ parser giữ original XML bytes | Text extraction làm mất lexical details. | Dùng XML serialization/canonicalization theo mục tiêu. |

## 16. Checklist trước khi dùng StAX trong production

- [ ] Đã dùng `XMLInputFactory` phù hợp và cấu hình security **trước** khi tạo reader?
- [ ] `SUPPORT_DTD=false` và external entity access bị khóa khi không cần DTD?
- [ ] Có kiểm thử provider thực đang chạy, không bỏ qua security property unsupported?
- [ ] Có giới hạn input bytes/text/depth/attributes phù hợp với sản phẩm?
- [ ] Đã phân biệt cursor `XMLStreamReader` và event `XMLEventReader`?
- [ ] Chỉ đọc attribute tại START_ELEMENT và truy xuất theo QName?
- [ ] Không nhầm namespace declarations với attributes thông thường?
- [ ] Đã kiểm tra attr thiếu (null) khác attr rỗng (empty string)?
- [ ] Có validate boolean/number/enum attributes, không nhận input bừa?
- [ ] Dùng namespace URI thay vì prefix cứng khi match element/attribute?
- [ ] Chỉ dùng getElementText khi element không có child elements?
- [ ] Với mixed content, có depth-aware processing và rõ giữ markup hay chỉ text?
- [ ] Có xử lý CHARACTERS/CDATA/SPACE và whitespace đúng policy?
- [ ] Không phụ thuộc số chunks/event segmentation hay thứ tự attributes?
- [ ] Nếu dùng getTextCharacters, có offset/length đúng và copy trước next?
- [ ] Có đóng XMLStreamReader/XMLEventReader và InputStream/Reader gốc riêng?
- [ ] Có phân biệt XMLStreamException malformed XML với lỗi IO/security?
- [ ] Không log raw XML chứa PII/secrets, có correlation ID và vị trí lỗi?
- [ ] Có chạy tests cho emoji/CDATA/&amp;/namespaces/nested content/empty text?
- [ ] Không biến XML text extraction thành xử lý HTML/SQL thiếu output encoding?

## 17. Bài tập tự thực hành

**Bài A — Attribute có namespace.** Đổi prefix `m` thành `meta` nhưng giữ URI `urn:meta`, rồi chạy lại. Giá trị `lang` có đổi không? Vì sao matching dựa trên URI tốt hơn prefix?

**Bài B — Missing/empty.** Thêm attribute `optional=""` và thử lấy `missing` không tồn tại. Giải thích vì sao phải phân biệt `null`/`""`.

**Bài C — Numeric validation.** Thêm `pages="12"`, chuyển thành int có kiểm soát, sau đó thử `pages="x"`, `pages="-1"`, `pages="99999999999999999"`.

**Bài D — Boolean validation.** Thay `available="true"` thành `"maybe"`. So sánh việc gọi `Boolean.parseBoolean` trực tiếp với cách check explicit.

**Bài E — CDATA.** Thay title thành ba chunks text/CDATA liên tiếp. Nếu `IS_COALESCING=false`, kiểm tra output `getElementText` có đổi không. Không assert số lượng events cố định.

**Bài F — Mixed content.** Với `description` chứa hai thẻ con, nâng code `mixedText` để chỉ lấy text tại depth 1. So sánh output với toàn subtree text.

**Bài G — Whitespace.** Đổi `note` thành `<note>  </note>`, kiểm tra `getElementText().length()`. Nếu gọi `trim`, mất dữ liệu gì?

**Bài H — getTextCharacters.** Dùng `getTextStart`/`getTextLength` để tái tạo từng chunk, so với `getText`; sau khi gọi next, kiểm tra vì sao không được giữ buffer cũ.

**Bài I — nextTag.** Dùng hai input `<root> \n <child/></root>` và `<root>text<child/></root>`. Vì sao chỉ cái đầu hợp lệ với nextTag từ root?

**Bài J — XML security.** Trong sandbox, thử XML có DOCTYPE và external entity với parser được cấu hình fail-closed. Quan sát errors mà không để parser truy cập file/network.

**Bài K — Resource lifecycle.** Tạo custom Reader đếm close, kiểm tra `XMLStreamReader.close` so với tự đóng nguồn. Test lại trên provider bạn dùng nếu khác JDK.

**Bài L — Large data.** Tạo một XML vài MB với hàng nghìn book elements, xử lý từng book và chuyển ra consumer; đo heap trước/sau so với cách gom toàn bộ document thành String.

## 18. Câu hỏi tự kiểm tra

**1.** Attribute có được phát như `CHARACTERS` event không? — **Không.** Đọc nó trên `START_ELEMENT` bằng attribute APIs.

**2.** `getAttributeValue(null,"id")` trả gì khi thiếu? — **`null`**; khác `id=""` trả chuỗi rỗng.

**3.** Dùng `getAttributeValue(null,"lang")` có luôn chọn namespaced `m:lang` đúng không? — **Không.** NamespaceURI null không so namespace, nên cần truyền URI cụ thể.

**4.** Default namespace `xmlns="urn:books"` có áp lên `id` unprefixed không? — **Không**. Nó áp cho elements nhưng không tự áp cho unqualified attributes.

**5.** Vì sao `getAttributeCount` trả 3 trong chương trình chính dù có hai xmlns declarations? — Vì `xmlns` là namespace declarations, không phải ordinary attributes.

**6.** `getElementText` có dùng được cho `<p>hello <b>world</b></p>` không? — **Không.** Nested element khiến method ném XMLStreamException.

**7.** Sau `getElementText`, cursor đứng ở đâu? — **END_ELEMENT tương ứng**; không tự gọi next thêm một lần để bỏ thẻ đó.

**8.** `getElementText` có trả đúng văn bản dù chia thành nhiều CHARACTERS events không? — **Có**, nó tổng hợp nội dung text-only.

**9.** XML `<empty/>` có bắt buộc tạo CHARACTERS event rỗng không? — **Không**. getElementText trả `""` và cấu trúc có START/END.

**10.** `getTextCharacters()` có thể dùng nguyên mảng mà bỏ offset/length không? — **Không**. Phải đọc đúng `getTextStart`/`getTextLength`; array transient.

**11.** `nextTag()` dùng để bỏ qua văn bản có nghĩa được không? — **Không**; nó có thể ném XMLStreamException khi gặp significant text.

**12.** `IS_COALESCING=true` có thay thế việc hiểu mixed content không? — **Không**. Nó chỉ ảnh hưởng gộp character data/CDATA, không loại bỏ nested elements.

**13.** Đã đóng XMLStreamReader thì InputStream nguồn cũng chắc chắn đóng? — **Không**. Nên quản lý InputStream riêng.

**14.** StAX có dùng `XMLConstants.FEATURE_SECURE_PROCESSING` giống DOM không? — **Không**. Dùng StAX-specific DTD/entity settings và JAXP external access limits thích hợp.

**15.** Hai chương trình đã được kiểm chứng bằng môi trường nào? — `javac --release 17` và Java runtime JDK 24; không cần database hoặc dependency ngoài JDK.

## 19. Tài liệu chính thức hiện hành

- [XMLStreamReader — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLStreamReader.html): current event, `getAttributeValue`, `getText`, `getElementText`, `getTextCharacters`, `nextTag`, reader lifecycle.
- [XMLEventReader — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLEventReader.html): event access, `nextEvent`, `peek`, `getElementText`.
- [StartElement — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/events/StartElement.html): `getAttributes`, `getAttributeByName`, `getNamespaces`.
- [Attribute — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/events/Attribute.html): `getName`, `getValue`, `isSpecified`.
- [Characters — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/events/Characters.html): `getData`, `isCData`, `isWhiteSpace`.
- [XMLInputFactory — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLInputFactory.html): namespace/coalescing/DTD/external entity properties, cursor/event factories.
- [XMLStreamConstants — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLStreamConstants.html): `START_ELEMENT`, `CHARACTERS`, `CDATA`, `SPACE`, `END_ELEMENT`.
- [XMLStreamException — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLStreamException.html): lỗi XML parsing và location.
- [QName — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/namespace/QName.html): namespace URI/local part/prefix.
- [JAXP Security Guide — Java SE 25](https://docs.oracle.com/en/java/javase/25/security/java-api-xml-processing-jaxp-security-guide.html): StAX DTD restrictions, external access properties, entity limits và khác biệt với DOM/SAX FSP.
- [XMLStreamReader — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/stream/XMLStreamReader.html): tương thích source target `--release 17`.

**Ghi nhớ:** Với StAX, **attribute được đọc ở `START_ELEMENT`**, chọn bằng namespace URI + local name khi cần; **văn bản thường có nhiều events**, có thể ghép bằng `getElementText()` khi element **chỉ chứa text**, hoặc dùng một vòng **depth-aware** cho mixed content. Không dựa vào thứ tự attributes, số chunks hoặc prefix XML; xử lý whitespace có chủ đích, đóng tài nguyên và cấu hình bảo mật DTD/XXE trước khi parse.
