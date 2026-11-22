# XMLInputFactory và tạo XMLStreamReader trong StAX (Java 17+)

## 1. Vấn đề và vai trò của XMLInputFactory

Trong Java, XML thường xuất hiện trong cấu hình, tích hợp hệ thống, dữ liệu xuất/nhập và tài liệu nghiệp vụ. Một cách đơn giản là đọc XML thành `String` rồi dựng cây DOM; tuy nhiên với tài liệu lớn, việc giữ toàn bộ XML và cây các node trong bộ nhớ có thể tốn heap. **StAX (Streaming API for XML)** cho phép ứng dụng đọc XML **theo sự kiện** thay vì bắt buộc tạo DOM.

Điểm khởi đầu phổ biến:

```java
XMLInputFactory factory = XMLInputFactory.newDefaultFactory();
XMLStreamReader xml = factory.createXMLStreamReader(reader);
```

Đây là **snippet**, chưa phải chương trình độc lập: `reader` là `java.io.Reader` đã mở, cần import `javax.xml.stream.XMLInputFactory` và `XMLStreamReader`. Trong ứng dụng thực, **không đưa XML không tin cậy vào factory chưa harden**; phần 5 và ví dụ hoàn chỉnh cấu hình bảo vệ trước khi gọi `createXMLStreamReader`.

Phân biệt hai đối tượng:

- **`XMLInputFactory`**: cấu hình/parser factory; chọn StAX implementation, đặt các properties (namespace, DTD, entities, coalescing…), resolver/reporter rồi **tạo ra** reader.
- **`XMLStreamReader`**: **cursor** trỏ tới một sự kiện XML tại một thời điểm. Ứng dụng gọi `next()`, `getEventType()`, `getLocalName()`, `getText()`, `getAttributeValue()`… để xử lý tuần tự.

StAX nằm trong module **`java.xml`**, package **`javax.xml.stream`**, vẫn được JDK 17+ hỗ trợ. Chữ `javax` trong tên package **không làm StAX thành legacy**: đây là API JAXP tiêu chuẩn còn áp dụng trên JDK hiện đại. Không cần mang một thư viện parser đời cũ vào project chỉ để đọc XML bằng StAX.

Mục tiêu bài học:
1. Biết cách chọn `newDefaultFactory()` hoặc `newFactory()` theo nhu cầu.
2. Hiểu các overload `createXMLStreamReader` cho `Reader`, `InputStream`, encoding và `Source`.
3. Thiết lập **namespace-aware**, tắt DTD/external entities và fail closed nếu không cấu hình được bảo mật.
4. Duyệt sự kiện với `hasNext()`, `next()`, `getEventType()`, `START_ELEMENT`, `CHARACTERS`, `END_ELEMENT`, v.v.
5. Hiểu các contract của `getElementText()`, `nextTag()`, `getTextCharacters()`, `getLocation()`.
6. Đóng **cả XMLStreamReader và nguồn** đúng cách; xử lý malformed XML, encoding, namespace, giới hạn tài nguyên.
7. Biên dịch và chạy demo Java 17+ xử lý XML tiếng Việt, emoji, số thập phân và thử nghiệm chặn external entity.

## 2. StAX cursor nằm ở đâu trong quy trình?

```text
File / Network / Database / String
                  |
       InputStream (bytes) hoặc Reader (chars)
                  |
             XMLInputFactory
            +-------------+
            | setProperty |
            | setResolver |
            +-------------+
                  |
        createXMLStreamReader(...)
                  |
            XMLStreamReader
                  |
     START_DOCUMENT -> START_ELEMENT
                  |
        ATTRIBUTE / CHARACTERS
                  |
          END_ELEMENT / ...
                  |
             END_DOCUMENT
                  |
     reader.close() + input.close()
```

`XMLStreamReader` là một **pull parser**: ứng dụng tự quyết định khi nào lấy sự kiện tiếp theo. So sánh:

| API | Mô hình | Khi phù hợp |
| --- | --- | --- |
| **StAX cursor** `XMLStreamReader` | Gọi `next()` và đọc event hiện tại. | Xử lý tuần tự tài liệu lớn, đọc từng order/record, trích số liệu. |
| **StAX event** `XMLEventReader` | Gọi `nextEvent()` và nhận object `XMLEvent`. | Pipeline sự kiện, filter, chuyển tiếp event. |
| DOM `DocumentBuilder` | Dựng toàn bộ cây node. | XML vừa/nhỏ, cần truy vấn nhiều vị trí hoặc chỉnh sửa cây. |
| SAX `XMLReader` | Gọi callback từ parser đến handler. | Xử lý theo luồng với callback-driven design. |
| `XMLStreamWriter` | Ghi từng sự kiện XML. | Tạo XML lớn có escaping đúng. |

**`XMLInputFactory` có thể tạo `XMLStreamReader` và `XMLEventReader`**. Với chủ đề này ta dùng nhánh cursor `XMLStreamReader`. Muốn tạo XML output, dùng `XMLOutputFactory` — **không** phải `XMLInputFactory`.

## 3. Khởi tạo XMLInputFactory trong Java hiện đại

### 3.1. newDefaultFactory()

```java
XMLInputFactory factory = XMLInputFactory.newDefaultFactory();
```

Method có từ Java 9 và hiện có trên Java 17+. Nó chọn **StAX implementation system-default tích hợp trong JDK**. Đây là lựa chọn thực tế nếu muốn **parser JDK có behavior tương đối dự đoán được** và không chủ ý cài StAX provider từ dependency ngoài.

**Không nên hiểu “default” là “tự chống mọi XML attack”**. Dù dùng built-in implementation, bạn vẫn phải đặt policy DTD/external entities, giới hạn tài nguyên và fail closed khi làm việc với XML không đáng tin.

### 3.2. newFactory() và newInstance()

```java
XMLInputFactory factory = XMLInputFactory.newFactory();
```

`newFactory()` sử dụng cơ chế **JAXP provider lookup**, có thể lựa chọn provider do ứng dụng/module cấu hình hoặc service provider. `newInstance()` là phương thức tương đương về cơ chế factory lookup. Nếu hệ thống chủ đích dùng parser khác (ví dụ để có behavior hoặc hiệu năng cụ thể), hãy khai báo dependency/provider phù hợp rồi **kiểm chứng lại toàn bộ security properties**, không chỉ compile API.

| Cách tạo | Ý nghĩa | Khuyến nghị |
| --- | --- | --- |
| `XMLInputFactory.newDefaultFactory()` | JDK system-default built-in provider. | Đơn giản, ổn định trong phạm vi JDK cụ thể; phù hợp tutorial Java 17+. |
| `XMLInputFactory.newFactory()` | Chọn provider qua factory lookup. | Dùng khi cần cơ chế plugin/provider deployment và có integration tests. |
| `XMLInputFactory.newInstance()` | Cách gọi factory lookup tương đương `newFactory()`. | Vẫn hỗ trợ nhưng không cần dùng cả hai trong code. |

**Không gọi `new XMLInputFactory()`**: constructor lớp là `protected` và đây là abstract class; phải dùng static factory methods hoặc implementation của provider.

### 3.3. Khi nào đặt cấu hình?

Thứ tự chuẩn:

```text
newDefaultFactory()
      |
setProperty / setXMLResolver / setXMLReporter
      |
createXMLStreamReader(...)
      |
read events
      |
close reader
```

Cấu hình **trước khi tạo `XMLStreamReader`** để reader nhận đúng policy. Đừng tạo reader rồi thay `XMLInputFactory` và tự cho rằng reader đang chạy sẽ đổi behavior theo. Parser factories có thể mutable và **không nên giả định thread-safe**; nếu tái sử dụng ở nhiều threads, phải kiểm tra provider documentation hoặc tạo một factory cho từng scope theo thiết kế hiệu năng.

## 4. Những overload tạo XMLStreamReader

`XMLInputFactory` có nhiều overload, cho phép đọc từ nguồn dạng ký tự, byte hoặc JAXP source.

| Overload | Dữ liệu đầu vào | Dùng khi |
| --- | --- | --- |
| `createXMLStreamReader(Reader)` | `Reader` đã giải mã ký tự. | `StringReader`, `Files.newBufferedReader(...)`, dữ liệu đã qua decoder rõ charset. |
| `createXMLStreamReader(InputStream)` | Raw bytes XML. | File/network bytes có BOM/XML encoding declaration theo XML specification. |
| `createXMLStreamReader(InputStream, String encoding)` | Bytes và chỉ định encoding. | Biết chính xác encoding thực của nguồn, cần explicit charset theo contract. |
| `createXMLStreamReader(String systemId, InputStream)` | Bytes cộng system ID. | Cần nguồn định danh hợp lệ cho location/relative reference policy. |
| `createXMLStreamReader(String systemId, Reader)` | Reader cộng system ID. | Cần base URI/tracing có kiểm soát. |
| `createXMLStreamReader(Source)` | JAXP `Source`. | Pipeline `StreamSource` hoặc source tương thích provider. |

Tất cả các overload này trả `XMLStreamReader`. **Không dùng `createXMLStreamReader(String)` rồi truyền trực tiếp XML text** vì đây **không phải** overload tiêu chuẩn nhận chuỗi XML raw. Với một chuỗi có sẵn, dùng `new StringReader(xmlText)`.

### 4.1. Từ String: StringReader

```java
String xmlText =
        "<note><title>Tiếng Việt &amp; XML</title></note>";

XMLInputFactory factory = secureFactory();
try (Reader input = new StringReader(xmlText)) {
    XMLStreamReader xml =
            factory.createXMLStreamReader(input);
    try {
        // Duyệt events của xml.
    } finally {
        xml.close();
    }
}
```

Đây là **snippet**, `secureFactory()` là method định nghĩa đầy đủ ở chương trình mục 8; cần `java.io.Reader`, `StringReader` và StAX imports. Đối với XML đã chứa toàn bộ trong `String` thì StringReader không tiết kiệm bộ nhớ dữ liệu gốc, nhưng vẫn cho phép xử lý dưới dạng cursor events.

**Lưu ý escaping:** String literal XML phải dùng `&amp;` thay vì dấu `&` thô trong text; XMLStreamReader sẽ trả nội dung `Tiếng Việt & XML` sau khi parse.

### 4.2. Từ file UTF-8: Files.newBufferedReader

```java
Path path = Path.of("orders.xml");

XMLInputFactory factory = secureFactory();
try (Reader input =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    XMLStreamReader xml =
            factory.createXMLStreamReader(input);
    try {
        while (xml.hasNext()) {
            int event = xml.next();
            // Xử lý từng event.
        }
    } finally {
        xml.close();
    }
}
```

Đây là **snippet**, cần `java.nio.file.Files`, `Path`, `StandardCharsets`, `Reader` và `XMLStreamReader`; `secureFactory` nằm trong ví dụ đầy đủ bên dưới.

Ở ranh giới byte-to-char, `Files.newBufferedReader(path, UTF_8)` giải mã bằng UTF-8 một cách rõ ràng. **Khi đã đưa vào `Reader`, encoding đã được quyết định ở phía ứng dụng**. XML declaration trong nội dung không được dùng như một cơ chế “tự giải mã lại” Reader.

### 4.3. Từ InputStream: để parser phát hiện XML encoding

```java
try (InputStream bytes = Files.newInputStream(Path.of("orders.xml"))) {
    XMLStreamReader xml =
            secureFactory().createXMLStreamReader(bytes);
    try {
        while (xml.hasNext()) {
            xml.next();
        }
    } finally {
        xml.close();
    }
}
```

Đây là **snippet**. Khi nhận bytes, StAX implementation áp dụng quy tắc XML encoding/BOM/XML declaration phù hợp. Nếu bạn thật sự biết encoding của nguồn, có thể chỉ định:

```java
XMLStreamReader xml =
        factory.createXMLStreamReader(inputStream, "UTF-8");
```

Đây là **snippet** với `factory` đã cấu hình và `InputStream inputStream` đã mở. Đừng truyền `"UTF-8"` nếu nguồn thực tế là UTF-16 hay encoding khác chỉ để code chạy; hãy giải quyết mâu thuẫn giữa bytes, BOM, declaration và charset.

**`InputStream` là byte stream; `Reader` là character stream**. Java `char` là đơn vị UTF-16, trong khi một Unicode code point ngoài BMP như emoji thường chiếm hai `char`. Không dùng số byte file làm số `char`, không coi `String.length()` là số ký tự nhìn thấy.

### 4.4. systemId và Source: cẩn thận nguồn không tin cậy

`systemId` hỗ trợ việc xác định nguồn/đường dẫn cơ sở đối với XML resource resolution tùy parser. Ví dụ:

```java
XMLStreamReader xml = factory.createXMLStreamReader(
        "urn:demo:orders", inputReader);
```

Đây là **snippet** với `factory` và `inputReader` đã được cấp và kiểm soát bởi ứng dụng; nó không tự mở một URL chỉ vì có chuỗi systemId. Tuy nhiên, **base URI/systemId có thể ảnh hưởng đến external references nếu DTD/entity loading được cho phép**. Không nhận untrusted URL làm systemId rồi mở network/file mà không có policy. Cấu hình chống external entities vẫn phải bật như mục 5.

Với JAXP `Source`:

```java
StreamSource source = new StreamSource(inputReader);
XMLStreamReader xml = factory.createXMLStreamReader(source);
```

Đây là **snippet**, cần import `javax.xml.transform.stream.StreamSource`. Hỗ trợ chính xác một số `Source` implementation có thể phụ thuộc provider. Nếu đã có `Reader` thì overload `createXMLStreamReader(Reader)` thường rõ nghĩa và dễ quản lý resource hơn.

## 5. Cấu hình quan trọng: properties và bảo mật

**Không parse XML không đáng tin bằng factory mới tạo mà chưa cấu hình.** XML từ API, tệp upload, email, cơ sở dữ liệu hoặc bên thứ ba có thể chứa DTD, external entities hay nội dung rất lớn. Nếu parser resolve references không phù hợp, có thể gây **XXE, SSRF, lộ file nội bộ hoặc resource exhaustion**.

### 5.1. Cấu hình khuyến nghị trên Java 17+

```java
static XMLInputFactory secureFactory() {
    XMLInputFactory factory =
            XMLInputFactory.newDefaultFactory();

    factory.setProperty(
            XMLInputFactory.IS_NAMESPACE_AWARE, true);
    factory.setProperty(
            XMLInputFactory.SUPPORT_DTD, false);
    factory.setProperty(
            XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
    factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");

    factory.setXMLResolver(
            (publicId, systemId, baseURI, namespace) -> {
                throw new XMLStreamException(
                        "External entity blocked");
            });

    return factory;
}
```

Đây là **method snippet**; chương trình runnable đầy đủ ở mục 8 có imports và context. Yêu cầu `XMLInputFactory`, `XMLConstants` và `XMLStreamException`.

**Giải nghĩa từng dòng:**
- `IS_NAMESPACE_AWARE=true`: parser nhận biết namespace URI/local name, giúp phân biệt các element trùng tên nhưng khác namespace.
- `SUPPORT_DTD=false`: yêu cầu không hỗ trợ xử lý DTD.
- `IS_SUPPORTING_EXTERNAL_ENTITIES=false`: yêu cầu parser không resolve các external parsed entities.
- `ACCESS_EXTERNAL_DTD=""`: hạn chế giao thức truy cập external DTD/entity về tập rỗng trong JAXP implementations hỗ trợ thuộc tính chuẩn.
- `setXMLResolver(...)`: từ chối mọi yêu cầu resolver tới external resource, bổ sung một lớp fail-closed.
- Code ở `XMLStreamReader` có thể chủ động từ chối `XMLStreamConstants.DTD` nếu event này xuất hiện.

**Phân biệt “không xử lý DTD” với “từ chối mọi DOCTYPE”:** theo OWASP, `SUPPORT_DTD=false` **không bảo đảm** parser ném exception ngay khi gặp khai báo `<!DOCTYPE ...>`. Một implementation có thể bỏ qua nội dung DTD. Nếu chính sách nghiệp vụ **cấm hoàn toàn DOCTYPE**, cần test hành vi parser cụ thể hoặc dùng biện pháp đầu vào được kiểm chứng để từ chối DOCTYPE; không chỉ dựa vào một property. Ví dụ ở mục 8 chứng minh một **payload có external entity** bị từ chối trên JDK đã kiểm thử, **không** khẳng định mọi hình thức DOCTYPE đều bị reject tương tự.

**Đừng áp dụng nhầm `XMLConstants.FEATURE_SECURE_PROCESSING` vào StAX** như với `DocumentBuilderFactory`. StAX không có cơ chế property tương đương được đặc tả chung dưới tên đó; hãy dùng các StAX controls và giới hạn parser-specific phù hợp. Nếu cần DTD nội bộ thực sự, bảo mật phức tạp hơn: khóa external resolution, giới hạn expansion và test implementation; tránh bật DTD đại trà.

### 5.2. Danh sách properties thường gặp

| Hằng `XMLInputFactory` | Ý nghĩa | Ghi nhớ |
| --- | --- | --- |
| `IS_NAMESPACE_AWARE` | Bật/tắt nhận diện namespaces. | Nên bật khi XML dùng namespaces. |
| `IS_COALESCING` | Yêu cầu hợp nhất các `CHARACTERS` và `CDATA` liên tiếp thành text events theo contract. | Có thể làm parser buffer thêm text; không thay cho xử lý chunks. |
| `IS_REPLACING_ENTITY_REFERENCES` | Điều khiển cách thay thế entity references trong event stream. | **Không** thay cho chặn external entities. |
| `SUPPORT_DTD` | Hỗ trợ xử lý DTD. | Đặt false nếu không cần DTD. |
| `IS_SUPPORTING_EXTERNAL_ENTITIES` | Hỗ trợ resolution của external parsed entities. | Đặt false cho untrusted input. |
| `IS_VALIDATING` | Tùy chọn XML validation (không phải mọi implementation hỗ trợ). | Không coi StAX parser tự validate schema. |
| `XMLConstants.ACCESS_EXTERNAL_DTD` | Protocol policy cho external DTD/entity. | Đặt rỗng khi không cho phép. |

**Không tự suy rằng mọi property/value được mọi provider hỗ trợ.** `setProperty(String,Object)` có thể ném `IllegalArgumentException` nếu implementation không thể đặt giá trị mong muốn. Với bảo vệ cần thiết, **fail closed**: không catch rồi tiếp tục parse bằng cấu hình yếu hơn. `isPropertySupported(name)` giúp kiểm tra một tên property, nhưng **không chứng minh giá trị cụ thể đã được áp dụng**; đặt bằng `setProperty` và test behavior mới là bước chính.

`IS_REPLACING_ENTITY_REFERENCES=false` không đồng nghĩa XXE được chặn, vì external DTD/entity access còn nằm ở các settings khác. Tương tự, tắt namespace awareness làm việc đối chiếu `getLocalName()/getNamespaceURI()` kém đáng tin trong code dựa trên namespace.

### 5.3. XMLResolver và XMLReporter

`XMLInputFactory.setXMLResolver(XMLResolver)` cho phép điều khiển resource resolution. Ví dụ resolver **ném exception** khi có yêu cầu external resource. Trả `null` không phải chính sách an toàn thống nhất trên mọi provider, vì có parser có thể rơi về resolution mặc định.

`setXMLReporter(XMLReporter)` cài callback thông báo các **non-fatal XML issues** do implementation báo, không thay thế exception handling. Chỉ log những trường đã được duyệt; diagnostic message/location có thể chứa dữ liệu từ tài liệu không tin cậy. Reporter không phải một validator XSD và không bảo đảm mọi lỗi đều được báo như warning.

### 5.4. Giới hạn tài nguyên là một phần của “an toàn”

Một parser không tải external files vẫn có thể bị DoS nếu input chứa hàng triệu elements, độ sâu quá lớn hoặc một text element khổng lồ. Cần bổ sung:
- Maximum document bytes (ở tầng network/file/DB).
- Maximum number of elements, nesting depth và attributes.
- Maximum content length cho từng field; không gọi `getElementText()` không giới hạn trên payload rất lớn.
- Budget CPU/time, query/read timeout, cancellation và concurrency.
- Các giới hạn processing của JDK/provider nếu dùng; test chúng sau upgrade.
- Backpressure khi stream sang queue/sink; tránh danh sách kết quả không giới hạn.

Bản demo chỉ đặt giới hạn số `order` để minh họa, **chưa phải security gateway hoàn chỉnh**. Sản phẩm production cần validate schema/root/depth/size và kiểm thử hostile XML có kiểm soát.

## 6. Các sự kiện của XMLStreamReader

`XMLStreamReader` ban đầu thường ở `START_DOCUMENT`. Sau khi tạo reader, vòng lặp:

```java
try {
    while (xml.hasNext()) {
        int event = xml.next();
        // Phân nhánh theo event.
    }
} finally {
    xml.close();
}
```

Đây là **snippet**, có `XMLStreamReader xml` đã được tạo; nguồn Reader/InputStream phải được đóng riêng ở phạm vi bao ngoài.

`hasNext()` trả false khi cursor đã đến `END_DOCUMENT`; `next()` chuyển sang event tiếp theo hoặc ném `XMLStreamException` khi input XML lỗi. **Đừng nhầm `hasNext()` có nghĩa XML hợp lệ**: lỗi well-formed có thể chỉ xuất hiện khi parser đi đến một phần tiếp theo.

| `XMLStreamConstants` | Có ý nghĩa | Các method tiêu biểu |
| --- | --- | --- |
| `START_DOCUMENT` | Mở đầu tài liệu. | `getVersion()`, `getCharacterEncodingScheme()` tùy nguồn. |
| `START_ELEMENT` | Bắt đầu element. | `getLocalName()`, `getNamespaceURI()`, `getAttributeValue()`. |
| `CHARACTERS` | Text bên trong element. | `getText()`, `getTextCharacters()`, `getTextLength()`. |
| `CDATA` | CDATA section (tùy coalescing). | Xử lý text theo event contract. |
| `SPACE` | Whitespace event theo cách parser biểu diễn. | Không mặc định mọi whitespace là bỏ qua được. |
| `END_ELEMENT` | Kết thúc element. | `getLocalName()`, `getNamespaceURI()`. |
| `COMMENT` | XML comment. | `getText()` nếu event hỗ trợ. |
| `PROCESSING_INSTRUCTION` | Processing instruction. | `getPITarget()`, `getPIData()`. |
| `DTD` | DTD event. | Từ chối khi policy cấm DTD. |
| `ENTITY_REFERENCE` | Entity reference event theo parser settings. | Không tự resolve external entities. |
| `END_DOCUMENT` | Kết thúc tài liệu. | Có thể dừng sau khi tài liệu đã được parse hợp lệ. |

**Hằng event và API cursor khác nhau:** `XMLStreamReader.START_ELEMENT` cũng có thể truy cập do interface kế thừa `XMLStreamConstants`, nhưng sử dụng `XMLStreamConstants.START_ELEMENT` thường rõ ràng trong bài học.

### 6.1. Đọc tên, namespace và thuộc tính

Ví dụ XML:

```xml
<o:order xmlns:o="urn:demo:orders" id="A-01" amount="12.50">
    <o:customer>Hà Nội</o:customer>
</o:order>
```

Khi cursor ở `START_ELEMENT` của `order`:
- `xml.getLocalName()`: `"order"`.
- `xml.getNamespaceURI()`: `"urn:demo:orders"`.
- `xml.getName()`: một `QName` chứa namespace URI, local part và prefix.
- `xml.getAttributeValue(null, "id")`: `"A-01"` vì attribute `id` **không thuộc namespace**.
- `xml.getAttributeValue(null, "amount")`: `"12.50"`.

**Không đồng nhất namespace prefix với namespace URI**: hai tiền tố khác nhau có thể trỏ cùng namespace URI; prefix có thể thay đổi khi XML được serialize lại. Kiểm tra `namespaceURI + localName`, không chỉ chuỗi `"o:order"`. Với element không có namespace, một số method có thể trả null hoặc chuỗi rỗng tùy contract; code robust nên kiểm tra case đó rõ.

**Đọc attributes chỉ khi event phù hợp**, chủ yếu `START_ELEMENT`; không gọi `getAttributeValue` tại `CHARACTERS` hoặc `END_DOCUMENT` và mong behavior ổn định.

### 6.2. Text có thể bị chia thành nhiều events

Ví dụ:

```xml
<note>Xin <![CDATA[chào]]> &amp; XML</note>
```

Parser có thể cung cấp nhiều `CHARACTERS`/`CDATA` events thay vì một chuỗi duy nhất. Nếu cần text hoàn chỉnh:
- Với field **nhỏ, text-only**: `getElementText()`.
- Với text **rất lớn**: xử lý `CHARACTERS` chunks, không gom toàn bộ vào String.
- Nếu dùng `IS_COALESCING=true`, parser có thể gộp events theo contract, nhưng việc đó cũng có thể làm tăng buffering. Không dựa vào coalescing để thay thế giới hạn độ dài.

Khi sử dụng `getTextCharacters()`, `getTextStart()` và `getTextLength()`, xử lý dữ liệu **trước khi gọi `next()`**, vì buffer nội bộ có thể được tái sử dụng cho event sau:

```java
if (event == XMLStreamConstants.CHARACTERS
        || event == XMLStreamConstants.CDATA) {
    writer.write(
            xml.getTextCharacters(),
            xml.getTextStart(),
            xml.getTextLength());
}
```

Đây là **snippet**, có `Writer writer`, `int event` và `XMLStreamReader xml`. Nó copy các `char` đang có tại event vào writer; để tạo output XML hoàn chỉnh, bạn vẫn phải xử lý start/end elements và escaping đúng. **Không coi snippet trên là XML serializer**.

### 6.3. getElementText() và nextTag()

`getElementText()` chỉ gọi khi cursor đang ở **`START_ELEMENT`** của một element **text-only** (không chứa child elements). Nó đọc text và dừng tại **`END_ELEMENT` tương ứng**.

```java
if (event == XMLStreamConstants.START_ELEMENT
        && "customer".equals(xml.getLocalName())) {
    String name = xml.getElementText();
    // Cursor hiện ở END_ELEMENT của customer.
}
```

Đây là **snippet**. Nếu `customer` có nested child element, `getElementText()` ném `XMLStreamException`. Nếu customer chứa hàng GB text, method còn có thể tạo `String` quá lớn. Ví dụ runnable dùng cho tên khách hàng nhỏ; dữ liệu dài cần đọc từng `CHARACTERS` event với giới hạn.

`nextTag()` bỏ qua một số whitespace/comment/processing instructions và kỳ vọng sự kiện tiếp theo là `START_ELEMENT` hoặc `END_ELEMENT`. Nếu gặp text không phải whitespace, nó có thể ném `XMLStreamException`. Vì vậy **không dùng `nextTag()` để thay thế toàn bộ vòng `next()` trong tài liệu có mixed content**.

### 6.4. Location, error handling và vị trí lỗi

Khi XML malformed, StAX thường ném `XMLStreamException`. Có thể lấy vị trí:

```java
try {
    while (xml.hasNext()) {
        xml.next();
    }
} catch (XMLStreamException e) {
    Location loc = e.getLocation();
    if (loc != null) {
        System.err.println(
                "line=" + loc.getLineNumber()
                + ",column=" + loc.getColumnNumber());
    }
    throw e;
}
```

Đây là **snippet** trong method `throws XMLStreamException`, cần `javax.xml.stream.Location`. Vị trí của parser có thể là best effort/unknown tùy nguồn; không suy location luôn chính xác tới từng byte. Không log nguyên XML input hoặc giá trị business nhạy cảm khi báo lỗi.

`XMLStreamReader.getLocation()` mô tả vị trí event hiện tại, `XMLStreamException.getLocation()` mô tả vị trí lỗi khi có; hai giá trị không phải luôn cùng một offset. Với stream dữ liệu mạng, line/column không tự quy đổi thành byte offset.

## 7. Đóng XMLStreamReader và nguồn đầu vào

**Điểm dễ sai:** `XMLStreamReader.close()` giải phóng resource của parser **nhưng theo Javadoc không đóng underlying input source**. Do đó cần **đóng cả hai**:

```java
try (Reader input = Files.newBufferedReader(
        Path.of("orders.xml"), StandardCharsets.UTF_8)) {

    XMLStreamReader xml = secureFactory()
            .createXMLStreamReader(input);

    try {
        while (xml.hasNext()) {
            xml.next();
        }
    } finally {
        xml.close();
    }
}
```

Đây là **snippet**, cần imports `Reader`, `Files`, `Path`, `StandardCharsets` và StAX. `XMLStreamReader` không kế thừa `AutoCloseable` nên không đặt nó trực tiếp trong try-with-resources như nguồn `Reader`. `try/finally` là cách đóng cursor, còn try-with-resources đóng source.

Đừng lẫn thứ tự:
1. Mở nguồn.
2. Tạo cursor từ factory đã cấu hình.
3. Duyệt/tiêu thụ events.
4. Đóng `XMLStreamReader`.
5. Đóng `Reader`/`InputStream`.

Nếu parser ném exception giữa chừng, `finally` vẫn đóng cursor. Nếu đang đọc từ JDBC `SQLXML.getCharacterStream()`, phải giữ `ResultSet`, transaction và `SQLXML` hợp lệ trong suốt parse; sau đó đóng reader, `SQLXML.free()`, rồi mới đóng statement/commit. Không trả cursor ra khỏi method sau khi nguồn đã đóng.

## 8. Chương trình Java 17+ hoàn chỉnh: XMLInputFactoryDemo.java

Ví dụ chạy không cần database hoặc dependency ngoài JDK. Nó thực hiện:
- Tạo XML tiếng Việt có namespace, hai đơn hàng, hai số tiền.
- Đọc **cùng tài liệu** qua `StringReader` và `ByteArrayInputStream` (UTF-8).
- Dùng factory đã harden chống external entities.
- Duyệt các `START_ELEMENT`, kiểm tra namespace, đọc thuộc tính `amount` rồi cộng bằng `BigDecimal`.
- Sử dụng `getElementText()` trên các field nhỏ `customer` và `note` của đơn hàng đầu.
- So sánh kết quả hai đường Reader/InputStream.
- Gửi payload chứa `DOCTYPE` và entity trỏ đến một đường dẫn giả, xác nhận **payload nguy hiểm cụ thể** bị từ chối.
- Đóng cursor trong `finally`, nguồn đầu vào trong try-with-resources.

### 8.1. Mã nguồn đầy đủ

Lưu file **`XmlInputFactoryDemo.java`** bằng UTF-8:

```java
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.io.Reader;
import java.io.StringReader;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import javax.xml.XMLConstants;
import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLStreamConstants;
import javax.xml.stream.XMLStreamException;
import javax.xml.stream.XMLStreamReader;

public final class XmlInputFactoryDemo {
    private static final String NS = "urn:demo:orders";

    record Summary(int orders, BigDecimal total,
                   String firstCustomer, String firstNote) {}

    static XMLInputFactory secureFactory() {
        XMLInputFactory factory = XMLInputFactory.newDefaultFactory();
        factory.setProperty(XMLInputFactory.IS_NAMESPACE_AWARE, true);
        factory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
        factory.setProperty(
                XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setXMLResolver(
                (publicId, systemId, baseURI, namespace) -> {
                    throw new XMLStreamException("External entity blocked");
                });
        return factory;
    }

    static Summary consume(XMLStreamReader xml) throws XMLStreamException {
        int orders = 0;
        BigDecimal total = BigDecimal.ZERO;
        String firstCustomer = "";
        String firstNote = "";
        try {
            while (xml.hasNext()) {
                int event = xml.next();
                if (event == XMLStreamConstants.DTD) {
                    throw new XMLStreamException("DOCTYPE not allowed");
                }
                if (event != XMLStreamConstants.START_ELEMENT) {
                    continue;
                }

                String name = xml.getLocalName();
                String ns = xml.getNamespaceURI();
                if (!NS.equals(ns)) {
                    throw new XMLStreamException("Unexpected namespace: " + ns);
                }
                if ("order".equals(name)) {
                    if (++orders > 1000) {
                        throw new XMLStreamException("Too many orders");
                    }
                    String amount = xml.getAttributeValue(null, "amount");
                    if (amount == null) {
                        throw new XMLStreamException("Missing amount");
                    }
                    total = total.add(new BigDecimal(amount));
                } else if ("customer".equals(name) && orders == 1) {
                    firstCustomer = xml.getElementText();
                } else if ("note".equals(name) && orders == 1) {
                    firstNote = xml.getElementText();
                }
            }
        } finally {
            xml.close();
        }
        return new Summary(orders, total, firstCustomer, firstNote);
    }

    public static void main(String[] args) throws Exception {
        String sample = """
                <?xml version="1.0" encoding="UTF-8"?>
                <o:orders xmlns:o="urn:demo:orders">
                  <o:order id="A-01" amount="12.50">
                    <o:customer>Hà Nội</o:customer>
                    <o:note>Xin chào &amp; 🌏</o:note>
                  </o:order>
                  <o:order id="A-02" amount="7.25">
                    <o:customer>Đà Nẵng</o:customer>
                    <o:note>Đã nhận</o:note>
                  </o:order>
                </o:orders>
                """;

        XMLInputFactory factory = secureFactory();
        Summary fromReader;
        try (Reader reader = new StringReader(sample)) {
            fromReader = consume(factory.createXMLStreamReader(reader));
        }

        Summary fromBytes;
        try (InputStream stream = new ByteArrayInputStream(
                sample.getBytes(StandardCharsets.UTF_8))) {
            fromBytes = consume(factory.createXMLStreamReader(stream));
        }

        String malicious = """
                <!DOCTYPE o:orders [
                  <!ENTITY secret SYSTEM "file:///not-for-reading">
                ]>
                <o:orders xmlns:o="urn:demo:orders">&secret;</o:orders>
                """;
        boolean externalEntityBlocked = false;
        try (Reader reader = new StringReader(malicious)) {
            try {
                consume(factory.createXMLStreamReader(reader));
            } catch (XMLStreamException expected) {
                externalEntityBlocked = true;
            }
        }

        System.out.println("readerOrders=" + fromReader.orders());
        System.out.println("readerTotal=" + fromReader.total());
        System.out.println("firstCustomer=" + fromReader.firstCustomer());
        System.out.println("firstNote=" + fromReader.firstNote());
        System.out.println("byteStreamSame=" + fromReader.equals(fromBytes));
        System.out.println("externalEntityBlocked=" + externalEntityBlocked);
    }
}
```

### 8.2. Lệnh biên dịch/chạy

Java 17 trở lên đã hỗ trợ **text blocks** (`"""`), `record` và switch expressions; sample dùng text blocks và record:

```bash
javac -encoding UTF-8 XmlInputFactoryDemo.java
java XmlInputFactoryDemo
```

Không cần `--enable-preview` hay external library trên JDK 17+. `javax.xml.stream` thuộc `java.xml` được cung cấp trong JDK. Chạy trên classpath mặc định đã có quyền truy cập tới module tiêu chuẩn này.

### 8.3. Stdout chính xác đã kiểm chứng

```text
readerOrders=2
readerTotal=19.75
firstCustomer=Hà Nội
firstNote=Xin chào & 🌏
byteStreamSame=true
externalEntityBlocked=true
```

Kết quả đã **được kiểm chứng** bằng cách biên dịch `XmlInputFactoryDemo.java` và chạy với JDK trong môi trường thử nghiệm.

Giải thích:
1. `readerOrders=2`: parser duyệt được hai `<o:order>`.
2. `readerTotal=19.75`: `BigDecimal` cộng `12.50` và `7.25`, không làm tròn qua `double`.
3. `firstCustomer=Hà Nội`: giữ dấu tiếng Việt sau XML parsing.
4. `firstNote=Xin chào & 🌏`: `&amp;` được giải mã về `&`, emoji Unicode được bảo toàn.
5. `byteStreamSame=true`: cùng XML đọc qua Reader và InputStream cho các thống kê tương đương.
6. `externalEntityBlocked=true`: payload có external entity bị từ chối, không dùng địa chỉ `file:///not-for-reading` để đọc tài nguyên.

**Giới hạn demo:** số lượng `order` bị chặn tại 1.000 và code kiểm tra namespace, nhưng chưa giới hạn đầy đủ document bytes, XML nesting depth, attribute lengths, số chữ số của `amount` hay tổng memory/CPU. Một tài liệu sai cấu trúc vẫn có thể cần thêm validation theo schema và business rules. `Long.parseLong`/`BigDecimal` cho dữ liệu không tin cậy cần kiểm tra độ dài và định dạng trước khi parse; demo dùng `BigDecimal` vì dữ liệu tiền tệ giả lập có phần lẻ.

**Không coi `externalEntityBlocked=true` là bằng chứng mọi `DOCTYPE` luôn bị parser loại bỏ**: trường hợp thử nghiệm có cả một external entity được tham chiếu. Một DOCTYPE không có entity dùng tới có thể có cách xử lý khác, tùy StAX provider. Nếu policy cấm tất cả DOCTYPE, phải test riêng và enforce chính sách đó.

## 9. Đưa XMLInputFactory vào ứng dụng thật

### 9.1. Đọc XML file đã được giới hạn kích thước

Một pattern đơn giản:

```java
Path inputFile = Path.of("import.xml");

// Giới hạn bytes trước khi parse; không phải toàn bộ biện pháp DoS.
long bytes = Files.size(inputFile);
if (bytes > 10_000_000L) {
    throw new IOException("XML file too large");
}

XMLInputFactory factory = XmlInputFactoryDemo.secureFactory();
try (Reader input = Files.newBufferedReader(
        inputFile, StandardCharsets.UTF_8)) {
    XmlInputFactoryDemo.Summary summary =
            XmlInputFactoryDemo.consume(
                    factory.createXMLStreamReader(input));
    System.out.println(summary.orders());
}
```

Đây là **snippet** trong cùng default package với class demo, cần imports `Path`, `Files`, `IOException`, `Reader`, `StandardCharsets`. Nếu đặt trong package khác, các helper `secureFactory`, `consume` và nested `Summary` ở ví dụ đang có package access, nên cần thay visibility phù hợp. **Không gọi snippet này chương trình standalone**.

Kiểm tra `Files.size` trước khi đọc chỉ có giá trị nếu file local không bị thay thế giữa check và read; với network streams và nguồn có thể thay đổi, cần **enforce limit ngay trong luồng đọc** và quyền truy cập file. Đừng tin filename/path từ người dùng không được validate; chống path traversal, giới hạn file types, xác định nơi lưu file.

### 9.2. XMLStreamReader từ HTTP/API response

Với HTTP response body:
1. Xác thực nguồn, URL/host allowlist, TLS và timeout.
2. Đọc response thành `InputStream` hoặc Reader với charset/encoding đúng contract.
3. Đưa nguồn vào `secureFactory().createXMLStreamReader(...)`.
4. Xử lý XML events theo business schema.
5. Đóng XMLStreamReader và response body/InputStream rõ ràng.
6. Đặt content-length/body-size limit và cancellation; không dùng response chưa kiểm soát để tải external references.

**External entity protection không thay cho SSRF protection của chính HTTP client.** XML parser không mở external DTD không có nghĩa ứng dụng được phép tự fetch URL do người dùng cung cấp. Đây là hai đường truy cập mạng khác nhau.

### 9.3. Nguồn JDBC SQLXML

Nếu dữ liệu đã ở cột SQL XML và driver hỗ trợ:

```java
SQLXML value = rs.getSQLXML("payload");
if (value != null) {
    try {
        try (Reader source = value.getCharacterStream()) {
            XMLStreamReader xml = secureFactory()
                    .createXMLStreamReader(source);
            try {
                while (xml.hasNext()) {
                    xml.next();
                }
            } finally {
                xml.close();
            }
        }
    } finally {
        value.free();
    }
}
```

Đây là **snippet**, có `ResultSet rs` và imports `SQLXML`, `Reader`, StAX; `secureFactory` là helper của chương trình mẫu. `SQLXML` có contract đọc **một lần trên mỗi instance**; sau `getCharacterStream()` không gọi thêm `getString()` trên cùng instance. Giữ `ResultSet`/transaction hợp lệ trong quá trình parse, đóng nguồn và `free()` trước khi kết thúc transaction/trả connection về pool.

**Không suy rằng SQLXML + StAX chắc chắn streaming qua network.** Driver có thể đã buffer toàn bộ SQLXML; StAX chỉ giúp application xử lý events mà không bắt buộc dựng DOM. Đo memory/network và JDBC driver behavior trong môi trường thực.

## 10. XMLInputFactory vs XMLEventReader vs XMLOutputFactory

Khi mới học StAX, dễ nhầm ba object:

```java
XMLInputFactory inputFactory = XMLInputFactory.newDefaultFactory();
XMLEventReader events =
        inputFactory.createXMLEventReader(inputReader);
```

Đây là **snippet**, cần import `javax.xml.stream.XMLEventReader`. `XMLEventReader` có API `nextEvent()` để nhận `XMLEvent` objects, không có cùng contract cursor `getLocalName()` như `XMLStreamReader` tại một thời điểm.

Tạo XML đầu ra:

```java
XMLOutputFactory outputFactory =
        XMLOutputFactory.newDefaultFactory();
XMLStreamWriter writer =
        outputFactory.createXMLStreamWriter(outputStream, "UTF-8");
```

Đây cũng là **snippet**, cần `XMLOutputFactory`, `XMLStreamWriter` và `OutputStream outputStream`. `XMLStreamWriter` ghi `writeStartDocument()`, `writeStartElement()`, `writeCharacters()`, `writeEndElement()`; không dùng `XMLInputFactory` để write.

### 10.1. Lúc nào cần event reader?

- Nếu muốn **filter/transform** sự kiện qua pipeline, `XMLEventReader` và `XMLEventWriter` có thể thuận tiện vì mỗi sự kiện được biểu diễn thành object.
- Nếu chỉ cần quét nhanh và lấy attributes/text, `XMLStreamReader` thường gọn hơn.
- Cả hai đều là StAX; cả hai cần security settings phù hợp.
- Không lưu danh sách toàn bộ `XMLEvent` cho tài liệu khổng lồ nếu mục tiêu là giảm bộ nhớ.

## 11. Lỗi thường gặp và nguyên nhân

| Vấn đề | Nguyên nhân phổ biến | Hướng xử lý |
| --- | --- | --- |
| `XMLStreamException` khi parse | XML malformed: thiếu closing tag, sai escaping, sai namespace… | Kiểm tra well-formedness, location và validation. |
| `XMLStreamException` do external entity | Parser đã chặn tài nguyên ngoài theo policy. | Giữ fail-closed, không bật DTD để “chạy được”. |
| `IllegalArgumentException` khi `setProperty` | Provider không hỗ trợ tên/giá trị property. | Kiểm tra provider và fail nếu đây là security setting bắt buộc. |
| `FactoryConfigurationError` khi dùng `newFactory()` | JAXP provider lookup/configuration lỗi. | Kiểm tra service/provider deployment; dùng built-in khi phù hợp. |
| `getElementText()` ném lỗi | Chưa đứng ở START_ELEMENT hoặc element có child elements. | Chỉ gọi trên text-only element; dùng event loop cho mixed/nested content. |
| `nextTag()` ném lỗi | Có non-whitespace text giữa tags. | Dùng `next()` nếu cần xử lý mixed content. |
| `getAttributeValue` cho null | Attribute không tồn tại hoặc sai namespace URI. | Kiểm tra required attributes/namespace, báo lỗi rõ. |
| Tiếng Việt/emoji bị lỗi | Decode file bằng sai charset hoặc XML declaration mâu thuẫn bytes. | Dùng Reader/UTF-8 rõ ràng, test Unicode round-trip. |
| `Reader` còn mở sau `xml.close()` | XMLStreamReader.close không đóng input source. | Đóng nguồn riêng bằng try-with-resources. |
| Heap tăng rất cao | Dùng `getElementText()` trên field rất dài hoặc gom mọi records vào List. | Xử lý text events theo chunks, giới hạn field/list. |
| Mất prefix XML | Code chỉ kiểm tra `getLocalName()` không có URI. | Đối chiếu namespaceURI + localName; prefix có thể thay đổi. |
| Báo `NoSuchElementException` | Gọi `next()` sau END_DOCUMENT/không có event. | Kiểm tra `hasNext()`, dừng đúng. |
| Parse chậm/memory tăng | Driver/network buffer, entity expansion hoặc XML quá sâu. | Profile toàn stack, hardening và limits. |
| XML comments/CDATA cho output sai | Parser chia text thành nhiều events, code chỉ xử lý một event. | Xử lý CHARACTERS/CDATA đúng contract. |
| Code compile nhưng `java.xml` không có trong custom runtime image | Image tạo bằng jlink thiếu module cần thiết. | Đưa `java.xml` vào runtime image và test. |
| Provider khác JDK chạy khác | `newFactory()` chọn third-party provider. | Audit provider, test properties và behavior. |

### 11.1. Malformed XML và message location

XML parser cần đọc tới vị trí lỗi mới có thể biết input không well-formed; vì vậy exception có thể xảy ra ngay khi tạo reader hoặc muộn hơn ở `next()`/`getElementText()`. `getLocation()` giúp điều tra, nhưng không tự tạo diagnostics an toàn nếu bạn log nguyên document. Không đưa raw XML từ người dùng vào logs hoặc HTTP response khi tài liệu có dữ liệu nhạy cảm.

### 11.2. XML encoding không giống SQL encoding

StAX có thể parse XML từ `Reader`, file hoặc HTTP. JDBC/SQLXML chỉ là một nguồn trong số đó; character encoding của database và byte encoding của HTTP/file phải được xử lý ở đúng boundary. **Không có thuộc tính `XMLInputFactory` nào tự sửa mọi dữ liệu đã bị decode sai trước khi parser nhìn thấy.**

## 12. Thiết kế ứng dụng: streaming, bounded memory và thread safety

**StAX cursor giảm nhu cầu materialize tree ở application**, nhưng không bảo đảm toàn pipeline O(1) memory. Những điểm cần xem xét:

1. **Nguồn byte**: HTTP client/driver có thể buffer trước khi trả InputStream.
2. **Parser buffer**: một text event dài, namespace maps hoặc DTD processing có thể tốn memory.
3. **Business state**: nếu bạn thu hết records vào `List`, lợi ích streaming sẽ biến mất.
4. **Downstream**: queue vô hạn hoặc batch quá lớn sẽ gây memory pressure.
5. **Concurrency**: nhiều readers đồng thời có thể làm tăng CPU/heap dù mỗi reader dùng buffer nhỏ.
6. **Factory/threading**: không giả định XMLInputFactory mutable thread-safe; parser cursors stateful cũng không để chia sẻ giữa threads.
7. **Resource lifetime**: với JDBC, XMLStreamReader đang đọc có thể giữ connection/transaction lâu; với HTTP, giữ response body đang mở.
8. **Timeout/cancellation**: cần đóng input source khi request/job bị hủy để giải phóng underlying network/file resources.

Nếu chỉ có XML vài KB và cần truy vấn nhiều trường không theo thứ tự, DOM đôi khi đơn giản hơn. Chọn StAX khi cần tuần tự, documents lớn hoặc tiết kiệm bộ nhớ — và có biện pháp validate business schema riêng.

## 13. Cách kiểm thử XMLInputFactory/XMLStreamReader

### 13.1. Unit tests không cần network/database

- XML cơ bản với root/child và attribute.
- XML có tiếng Việt, emoji, escaping `&amp;`, `&lt;` và Unicode ngoài BMP.
- XML có namespace prefix và default namespace, kiểm tra URI/local name.
- Text chia thành nhiều events, CDATA, whitespace.
- `getElementText()` cho text-only element và trường hợp nested child (phải báo lỗi).
- `nextTag()` khi có whitespace và khi có text không phải whitespace.
- InputStream UTF-8 vs Reader UTF-8, cùng nội dung => cùng dữ liệu semantics.
- SQL NULL không thuộc parser: nếu nguồn từ DB, xử lý null trước khi tạo XMLStreamReader.
- Tài liệu malformed báo `XMLStreamException`, không tạo object domain thiếu trường.

### 13.2. Security tests

- XML có DOCTYPE/internal và external DTD/entity, bảo đảm external resource **không bị truy cập**.
- XML có entity trỏ tới `file://`/`http://`; theo dõi request và xác nhận bị chặn trong test environment.
- `setProperty` của provider không hỗ trợ setting bảo mật: ứng dụng phải **fail closed**.
- XML rất sâu/nhiều element/rất dài/nhiều attributes: áp giới hạn cụ thể và dừng an toàn.
- Tài liệu có tên/namespace/attributes sai business schema: từ chối có kiểm soát.
- Không dùng tài liệu thật chứa PII/credentials làm test log.
- Nếu ứng dụng cần **cấm bất kỳ DOCTYPE nào**, test DOCTYPE không có entity và enforce reject độc lập với `SUPPORT_DTD=false`.

### 13.3. Integration tests

- Nâng JDK hoặc thay JAXP/StAX provider: test lại security config và event behavior.
- Nếu dùng SQLXML, test với JDBC driver/DBMS và transaction/cursor lifecycle thật.
- Nếu dùng HTTP, test timeout, max response bytes, TLS, cancellation và closing.
- Nếu xử lý stream rất lớn, đo peak heap, GC, throughput, latency, queue depth và file descriptors.
- Nếu có schema validation, kiểm tra qua validator được harden riêng (StAX well-formedness không đồng nghĩa XSD validity).
- Nếu có transform/XSLT, khóa external stylesheet/DTD trong `TransformerFactory` riêng; StAX security settings không tự truyền sang transformer.

### 13.4. Kiểm tra output và assertions có giá trị

Demo ở mục 8 dùng `Summary` record có `equals` theo giá trị, nên `byteStreamSame=true` là phép so sánh các trường kết quả, **không phải so sánh bytes của hai nguồn**. Nếu cần integrity cho dữ liệu nhạy cảm/giá trị ký số, phải xác định contract đối chiếu đúng: byte equality, canonical XML hay semantic equality. Dùng `String.equals` giữa hai XML serializations có thể thất bại dù cấu trúc tương đương do whitespace/attribute order/prefix.

## 14. Những câu hỏi thường gặp

**Câu 1. `XMLInputFactory` và `XMLStreamReader` có khác nhau không?**

Có. `XMLInputFactory` là factory cấu hình và tạo parser; `XMLStreamReader` là cursor duyệt events của một XML input cụ thể.

**Câu 2. Java 17 có cần cài `javax.xml.stream` bằng Maven không?**

Không trong runtime JDK tiêu chuẩn có module `java.xml`. Chỉ thêm dependency nếu dự án chủ đích dùng StAX provider bên thứ ba đã được kiểm soát. Nếu dùng custom jlink image, phải bảo đảm module tương ứng.

**Câu 3. `newDefaultFactory()` và `newFactory()` khác thế nào?**

`newDefaultFactory()` chọn built-in JDK provider; `newFactory()` dùng cơ chế JAXP lookup có thể chọn implementation khác qua provider registration/config. Cả hai đều cần hardening.

**Câu 4. XML text đang có trong String thì truyền thẳng vào createXMLStreamReader được không?**

Không có overload chuẩn nhận raw XML `String`. Dùng `new StringReader(xmlText)` hoặc InputStream bytes với encoding rõ.

**Câu 5. Vì sao `xml.close()` chưa đủ?**

Javadoc `XMLStreamReader.close()` không đóng underlying input source. Phải đóng nguồn `Reader` hoặc `InputStream` riêng.

**Câu 6. `SUPPORT_DTD=false` có bảo đảm parser ném lỗi trên mọi DOCTYPE không?**

Không. Nó vô hiệu DTD processing, nhưng một số provider có thể bỏ qua DOCTYPE mà không throw. Nếu cần cấm hoàn toàn DOCTYPE, phải enforce policy và test provider.

**Câu 7. `IS_REPLACING_ENTITY_REFERENCES=false` có tự chống XXE không?**

Không. Cần tắt `SUPPORT_DTD`, `IS_SUPPORTING_EXTERNAL_ENTITIES`, hạn chế `ACCESS_EXTERNAL_DTD`, resolver deny và limits phù hợp.

**Câu 8. Khi nào dùng `getElementText()`?**

Khi XMLStreamReader đang ở `START_ELEMENT` của field text-only với kích thước có giới hạn. Method tiêu thụ content tới END_ELEMENT; không dùng với nested elements hay field rất lớn.

**Câu 9. `nextTag()` có thay thế vòng `next()` trong XML mixed content không?**

Không. Nó bỏ qua whitespace/comment/PI và kỳ vọng tag; gặp text không phải whitespace có thể ném `XMLStreamException`.

**Câu 10. Làm sao biết tên element chính xác nếu tài liệu có namespace?**

So sánh `getNamespaceURI()` và `getLocalName()`, không giả định prefix cố định.

**Câu 11. Đọc bằng StAX có bảo đảm memory O(1) không?**

Không cho toàn bộ ứng dụng. Parser có thể xử lý theo sự kiện nhưng nguồn, driver, business state và sink vẫn có thể buffer dữ liệu; cần profile thực tế.

**Câu 12. Nếu code gặp `XMLStreamException` có nên retry toàn bộ parser?**

Không tự động. Nếu input malformed hoặc bị security policy từ chối, retry y nguyên là vô ích. Với lỗi I/O tạm thời, cần mở lại nguồn và đánh giá idempotency/timeout theo workflow.

**Câu 13. `XMLInputFactory.IS_VALIDATING=true` có thể dùng thay XSD validation không?**

Không nên dựa vào đó. Validation support của StAX là tùy provider; kiểm tra nhu cầu schema bằng `SchemaFactory`/`Validator` đã harden hoặc giải pháp vendor phù hợp.

**Câu 14. Vì sao demo dùng `BigDecimal` thay `double`?**

Vì `amount` là số thập phân có ngữ nghĩa tiền giả lập, `BigDecimal` tránh sai số nhị phân khi cộng. Production còn phải validate scale, precision, sign, currency và độ dài input.

## 15. Checklist triển khai Java 17+

1. **Chọn factory đúng:** `newDefaultFactory()` cho built-in JDK provider, `newFactory()` khi cần lookup implementation có kiểm soát.
2. **Cấu hình trước tạo parser:** namespace, DTD disabled, external entities disabled, external DTD access rỗng và deny resolver.
3. **Fail closed** nếu không đặt được security setting bắt buộc.
4. **Chọn nguồn hợp lý:** `Reader` cho chars đã decode, `InputStream` cho bytes XML, explicit encoding khi có contract đúng.
5. **Không truyền raw XML String trực tiếp vào factory**; dùng StringReader.
6. **Không tải XML từ URL không tin cậy** do người dùng cung cấp chỉ vì một method nhận `systemId`.
7. **Duyệt events đúng trạng thái:** `hasNext()`, `next()`, `getEventType()`, `START_ELEMENT`, `CHARACTERS`, `END_ELEMENT`.
8. **Đọc attributes và namespaces đúng event**, phân biệt namespace URI với prefix.
9. **Chỉ dùng `getElementText()` cho text-only field nhỏ** và nhớ cursor tới END_ELEMENT sau khi gọi.
10. **Xử lý text có nhiều events/chunks**; không gom tài liệu lớn vào String/List không giới hạn.
11. **Đóng parser và input source riêng**, đúng thứ tự và trên mọi đường exception.
12. **Đặt giới hạn size/depth/element count/time**, kèm backpressure và concurrency limits.
13. **Kiểm thử XXE/SSRF/XML bombs** và chính sách cấm DOCTYPE riêng khi cần.
14. **Xác minh Unicode/encoding**, gồm tiếng Việt, emoji, BOM, declaration và XML escaping.
15. **Không nhầm StAX parsing với XSD validation** hoặc với DOM/XSLT hardening.
16. **Nếu đọc từ JDBC SQLXML**, giữ cursor/transaction hợp lệ và giải phóng SQLXML đúng lifecycle.
17. **Kiểm thử JDK/implementation thực tế** trước production, đặc biệt khi thay provider.
18. **Ưu tiên API đang còn hỗ trợ** trong `java.xml` trên Java 17+; không cần hướng dẫn cũ/lỗi thời.

## 16. Nguồn tài liệu chính thức

- [Java SE 17 — XMLInputFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/stream/XMLInputFactory.html): `newDefaultFactory()`, `newFactory()`, parser creation overloads, properties và resolver.
- [Java SE 17 — XMLStreamReader](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/stream/XMLStreamReader.html): cursor events, `next`, `getElementText`, `nextTag`, `getTextCharacters`, `close`.
- [Java SE 17 — XMLStreamConstants](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/stream/XMLStreamConstants.html): event types.
- [Java SE 17 — XMLStreamException](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/stream/XMLStreamException.html): parsing errors và location.
- [Java SE 17 — XMLResolver](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/stream/XMLResolver.html): external entity resolution control.
- [Java SE 17 — XMLEventReader](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/stream/XMLEventReader.html): so sánh event API với cursor.
- [Java SE 17 — XMLConstants](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/XMLConstants.html): `ACCESS_EXTERNAL_DTD` và JAXP security constants.
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): tạo file Reader/InputStream với explicit encoding.
- [OWASP — XML External Entity Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html): cấu hình StAX bảo vệ XXE/SSRF; cảnh báo `SUPPORT_DTD=false` không tự ném lỗi trên mọi DOCTYPE.
- [Java SE 25 — XMLInputFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/stream/XMLInputFactory.html): đối chiếu API vẫn còn được hỗ trợ trong JDK hiện đại.
