# StAX cơ bản: next, nextTag, getElementText và điều kiện hợp lệ

## Mục tiêu học tập

**StAX (Streaming API for XML)** là API phân tích XML theo luồng trong **javax.xml.stream**, thuộc module chuẩn **java.xml**. Với **XMLStreamReader**, ứng dụng chủ động điều khiển một **con trỏ chỉ tiến về phía trước** qua các sự kiện của XML, thay vì tạo toàn bộ cây DOM trong heap.

Ba phương thức quan trọng nhất để điều khiển con trỏ là:

- **next()**: tiến tới **sự kiện kế tiếp**, không tự lọc text, comment hoặc processing instruction.
- **nextTag()**: tiến đến **START_ELEMENT hoặc END_ELEMENT** tiếp theo, chỉ bỏ qua các sự kiện **whitespace, COMMENT và PROCESSING_INSTRUCTION** phù hợp; **ném XMLStreamException** khi gặp character data không phải whitespace hoặc loại sự kiện không được phép.
- **getElementText()**: khi con trỏ **đang ở START_ELEMENT của phần tử chỉ chứa text**, đọc toàn bộ nội dung văn bản của phần tử đó, kết hợp các đoạn text cần thiết, và đưa con trỏ tới **END_ELEMENT tương ứng**. Nếu có phần tử con, hoặc con trỏ không ở START_ELEMENT, phương thức **ném XMLStreamException**.

Điều cần nhớ là các phương thức này **không chỉ trả dữ liệu**: chúng thay đổi **trạng thái con trỏ**. Nếu gọi đúng method nhưng ở sai event, chương trình vẫn sai. Sau bài, bạn có thể:

1. Hiểu sự khác nhau giữa **XMLStreamReader**, **XMLEventReader** và DOM ở mức cần thiết cho bài.
2. Đọc **getEventType()**, **hasNext()**, **START_DOCUMENT**, **START_ELEMENT**, **CHARACTERS**, **CDATA**, **END_ELEMENT**, **END_DOCUMENT**.
3. Chọn **next()** khi cần xử lý sự kiện chi tiết và text/mixed content.
4. Dùng **nextTag()** cho **element-only content** có whitespace/comment/processing instruction xen kẽ.
5. Dùng **getElementText()** cho **leaf element chỉ chứa text**, biết chính xác precondition/postcondition.
6. Hiểu XML empty element như **<empty/>** tạo cặp START_ELEMENT rồi END_ELEMENT.
7. Biết kiểm tra **require(...)**, **isStartElement()**, **getLocalName()**, **getText()** đúng event.
8. Xử lý XML với namespace, thuộc tính và Unicode một cách an toàn.
9. Tạo **XMLInputFactory** với DTD/external-entity access bị khóa khi xử lý XML không đáng tin.
10. Đóng **XMLStreamReader và underlying InputStream/Reader** đúng ownership.
11. Biên dịch/chạy ví dụ **Java 17+ độc lập**, kiểm tra **19 dòng stdout xác định**, cả các tình huống thành công và bị từ chối.
12. Tránh những anti-pattern gây skip dữ liệu, đọc sai cursor hoặc cạn heap vì `getElementText()` trên một trường XML lớn.

**Phạm vi hiện hành:** `XMLStreamReader`, `XMLInputFactory` và các hằng `XMLStreamConstants` vẫn được hỗ trợ ở Java SE 17 và Java SE 26. Ví dụ được kiểm thử trên **OpenJDK 24.0.2** với `javac --release 17`; không dùng cách làm đã lỗi thời/legacy.

## 1. Mô hình StAX cursor

Giả sử một XML:

~~~xml
<catalog>
  <item id="7">Xin chào</item>
  <empty/>
</catalog>
~~~

Khi tạo `XMLStreamReader`, event hiện tại ban đầu thường là **START_DOCUMENT** theo giao diện. Mỗi lời gọi `next()` đưa con trỏ sang một event tiếp theo:

~~~text
START_DOCUMENT
      │ next()
      ▼
START_ELEMENT catalog
      │ next()
      ▼
CHARACTERS whitespace
      │ next()
      ▼
START_ELEMENT item
      │ next()
      ▼
CHARACTERS "Xin chào"
      │ next()
      ▼
END_ELEMENT item
      │ ...
      ▼
START_ELEMENT empty
      │ next()
      ▼
END_ELEMENT empty
      │ ...
      ▼
END_ELEMENT catalog
      │ next()
      ▼
END_DOCUMENT
~~~

**Có thể xuất hiện thêm COMMENT, PROCESSING_INSTRUCTION, SPACE hoặc nhiều CHARACTERS events** tùy input, cách parser xử lý whitespace/CDATA và cấu hình coalescing. Trình tự trên diễn giải một XML cụ thể, **không phải cam kết mọi parser chia text giống nhau**.

Sự kiện hiện tại không đồng nghĩa “thẻ hiện tại đã đọc xong”:

- Tại **START_ELEMENT item**, bạn đang ở **thẻ mở** của item.
- Tại **CHARACTERS**, bạn đang ở text bên trong item.
- Tại **END_ELEMENT item**, bạn đã đi qua **thẻ đóng** của item.
- Tại **END_DOCUMENT**, `hasNext()` trả false; không gọi `next()` thêm.

### 1.1. Các event thường gặp

| Event | Hằng số | Nội dung |
| --- | --- | --- |
| Bắt đầu document | `XMLStreamConstants.START_DOCUMENT` | Điểm bắt đầu cursor |
| Thẻ mở | `START_ELEMENT` | Tên, namespace, attributes của phần tử |
| Văn bản | `CHARACTERS` | Text nội dung hoặc whitespace |
| CDATA | `CDATA` hoặc `CHARACTERS` theo parser/config | Text nằm trong CDATA |
| Whitespace phân loại riêng | `SPACE` | Whitespace event do parser phân loại |
| Comment | `COMMENT` | Nội dung comment |
| Processing instruction | `PROCESSING_INSTRUCTION` | Processing instruction |
| Thẻ đóng | `END_ELEMENT` | Kết thúc phần tử |
| DTD | `DTD` | DTD event nếu parser báo và cấu hình cho phép |
| Kết thúc document | `END_DOCUMENT` | Không còn event kế tiếp |

**Namespace declarations và attributes không nhất thiết xuất hiện như một event tuần tự riêng** khi bạn đọc XML bình thường bằng XMLStreamReader. Thông thường, bạn lấy chúng **ngay tại START_ELEMENT** qua `getAttributeCount()`, `getAttributeValue(...)`, `getNamespaceCount()` và methods liên quan.

### 1.2. Những API cần phối hợp

~~~java
// Mảnh minh họa; biến reader là XMLStreamReader đã được tạo.
int current = reader.getEventType();
boolean more = reader.hasNext();
int nextEvent = reader.next();

if (reader.isStartElement()) {
    String local = reader.getLocalName();
}

if (reader.isCharacters()) {
    String text = reader.getText();
}
~~~

`getEventType()` **không tiến con trỏ**. `next()` và `nextTag()` thì có. `getElementText()` tự tiến qua nhiều sự kiện cho đến thẻ đóng tương ứng.

## 2. next(): đọc mọi sự kiện kế tiếp

Chữ ký:

~~~java
int next() throws XMLStreamException;
~~~

`next()` **di chuyển con trỏ** tới sự kiện kế tiếp và trả về số nguyên mã hóa event type. Mã này khớp các hằng trong **XMLStreamConstants**.

Mẫu cơ bản:

~~~java
// Mảnh minh họa.
while (reader.hasNext()) {
    int event = reader.next();
    if (event == XMLStreamConstants.START_ELEMENT) {
        System.out.println("START " + reader.getLocalName());
    } else if (event == XMLStreamConstants.CHARACTERS) {
        System.out.println("TEXT " + reader.getText());
    } else if (event == XMLStreamConstants.END_ELEMENT) {
        System.out.println("END " + reader.getLocalName());
    }
}
~~~

Lý do dùng `hasNext()` là `next()` khi không còn event sẽ ném **NoSuchElementException**, còn lỗi XML parsing phát sinh **XMLStreamException**. Sau **END_DOCUMENT**, `hasNext()` phải false theo contract.

### 2.1. next() không tự bỏ qua comment hoặc text

Với:

~~~xml
<a>hi<!-- comment --><b/>!</a>
~~~

Các sự kiện có thể gồm:

~~~text
START_ELEMENT a
CHARACTERS hi
COMMENT
START_ELEMENT b
END_ELEMENT b
CHARACTERS !
END_ELEMENT a
END_DOCUMENT
~~~

Nếu chỉ kiểm tra `START_ELEMENT` mà không xử lý text, bạn có thể **bỏ sót nội dung cần dùng**. Khi parser có cấu hình coalescing, các đoạn ký tự liền kề có thể được hợp nhất; khi không, có thể xuất hiện nhiều CHARACTERS events.

**Không viết logic đòi một phần tử có đúng một CHARACTERS event**, kể cả phần tử chỉ có một text node theo cách nhìn của DOM.

### 2.2. XML empty element có hai sự kiện

~~~xml
<empty/>
~~~

Về event model, empty element tương đương:

~~~xml
<empty></empty>
~~~

Nó tạo **START_ELEMENT empty** rồi **END_ELEMENT empty**; có thể **không có CHARACTERS event** ở giữa vì không có text.

Nếu code chỉ chờ CHARACTERS để kết thúc phần tử, nó sẽ không xử lý được empty element. Dùng event START/END hoặc `getElementText()` nếu phần tử đúng kiểu chỉ chứa text.

### 2.3. Dữ liệu text có thể được chia nhiều chunks

Với:

~~~xml
<message>Xin <![CDATA[chào]]> &amp; Việt Nam</message>
~~~

Một parser có thể chia nội dung theo text/CDATAs/entity boundaries thành nhiều events, hoặc kết hợp các đoạn tùy cấu hình `XMLInputFactory.IS_COALESCING`. Nếu bạn cần giữ text theo chunks, dùng `next()` và append/copy từng event text.

**Nếu chỉ cần String đầy đủ của một phần tử nhỏ không chứa element con**, `getElementText()` thường gọn hơn. Nếu text rất lớn, `getElementText()` materialize một String và có thể tốn bộ nhớ; cân nhắc xử lý từng text event với `next()`.

### 2.4. getText() chỉ đúng khi event hợp lệ

`getText()` dành cho các **text-like events**, ví dụ `CHARACTERS`, `CDATA`, `SPACE`, `COMMENT` và các trạng thái được API cho phép. Không gọi `getText()` tại **START_ELEMENT** rồi mong nhận nội dung của cả phần tử.

Tương tự, `getLocalName()` chỉ hợp lệ khi event có tên phù hợp, thường là START_ELEMENT hoặc END_ELEMENT. Nếu gọi getter không hợp lệ theo event-state, **IllegalStateException** có thể phát sinh theo contract.

## 3. nextTag(): chỉ tiến qua phần element-only content

Chữ ký:

~~~java
int nextTag() throws XMLStreamException;
~~~

`nextTag()` được thiết kế để đọc XML có **các phần tử con được ngăn cách bởi whitespace, comments hoặc processing instructions**. Nó gọi `next()` nội bộ và bỏ qua những sự kiện không mang text thực theo quy tắc rõ ràng.

### 3.1. Những sự kiện nextTag được phép bỏ qua

- `CHARACTERS` nếu **isWhiteSpace() == true**.
- `CDATA` nếu nó chỉ là whitespace.
- `SPACE`.
- `COMMENT`.
- `PROCESSING_INSTRUCTION`.

Khi gặp **START_ELEMENT hoặc END_ELEMENT**, phương thức **dừng và trả chính event đó**.

Đối với **CHARACTERS chứa nội dung không phải whitespace**, hoặc một event khác không được phép bỏ qua, nó ném **XMLStreamException**. Nó không phải “skip mọi thứ cho đến tag”. Chính điều kiện này giúp tránh âm thầm bỏ text.

### 3.2. Ví dụ đúng

~~~xml
<catalog>
  <!-- nội dung phân loại theo phần tử -->
  <?stage test?>
  <item/>
  <item/>
</catalog>
~~~

Nếu con trỏ đang ở START_ELEMENT catalog:

~~~java
// Mảnh minh họa.
int e1 = reader.nextTag(); // START_ELEMENT item thứ nhất.
int e2 = reader.nextTag(); // END_ELEMENT item thứ nhất, do <item/>.
int e3 = reader.nextTag(); // START_ELEMENT item thứ hai.
~~~

Lệnh thứ hai không tự nhảy đến item tiếp theo, vì `nextTag()` có quyền trả cả **END_ELEMENT**. Muốn duyệt cây đúng, phải xét `START_ELEMENT` và `END_ELEMENT`, không chỉ assume mỗi lần gọi trả một thẻ mở.

### 3.3. Ví dụ sai: mixed content

~~~xml
<p>Hello <em>world</em>!</p>
~~~

Nếu con trỏ ở START_ELEMENT p và gọi `nextTag()`, nó gặp **CHARACTERS "Hello "**, không phải whitespace-only, nên **ném XMLStreamException**. Điều đó là đúng theo contract: `nextTag()` không dành cho **mixed content**.

Với mixed content, hãy dùng **next()** để xử lý cả text và nested elements.

**Không sửa lỗi bằng cách catch rồi tiếp tục nextTag vô hạn**: khi parser đã báo lỗi cấu trúc/event, vị trí sau exception không nên được giả định là một mốc phục hồi đáng tin cậy. Tốt hơn hãy coi document không phù hợp với parser contract hoặc tạo một luồng xử lý mixed content riêng.

### 3.4. Không gọi nextTag() ở cuối tài liệu

`nextTag()` di chuyển bằng các events nội bộ. Nếu không còn sự kiện, nó có thể ném **NoSuchElementException**; nếu gặp `END_DOCUMENT` trong lúc tìm tag, nó có thể báo **XMLStreamException** vì event này không phải START_ELEMENT/END_ELEMENT.

Đừng viết:

~~~java
// SAI: gọi vô hạn đến khi exception.
while (true) {
    reader.nextTag();
}
~~~

Thay vào đó, quản lý **độ sâu và thẻ đóng của phần tử đang xử lý**, hoặc kiểm tra `hasNext()` và loại event, không dùng exception làm điều kiện dừng bình thường.

## 4. getElementText(): lấy text từ leaf element

Chữ ký:

~~~java
String getElementText() throws XMLStreamException;
~~~

Đây là phương thức tiện dụng nhưng có **precondition rất chặt**:

**Trước khi gọi:** con trỏ phải ở **START_ELEMENT** của phần tử mà bên trong **chỉ chứa text-like content, comment hoặc processing instruction**, **không chứa phần tử con**.

**Sau khi gọi thành công:** con trỏ ở **END_ELEMENT tương ứng** với phần tử vừa đọc. `getElementText()` không để con trỏ ở CHARACTERS, không tự di chuyển tới START_ELEMENT sibling.

### 4.1. Ví dụ hợp lệ: text, CDATA và entity XML chuẩn

~~~xml
<item id="7">Xin <![CDATA[chào]]> &amp; Việt Nam</item>
~~~

Khi con trỏ đang ở START_ELEMENT item:

~~~java
// Mảnh minh họa.
String value = reader.getElementText();
// value: "Xin chào & Việt Nam"
// reader.getEventType(): END_ELEMENT
// reader.getLocalName(): "item"
~~~

Theo Javadoc, `getElementText()` trả nội dung đã **coalesced**, **bất kể cấu hình XMLInputFactory.IS_COALESCING**. Các text, CDATA, SPACE và entity-reference values được xử lý theo semantics XML; comments và processing instructions được bỏ qua.

Nếu XML chứa **&amp;**, parser trả ký tự **&** chứ không trả nguyên chuỗi "&amp;". Điều này không có nghĩa mọi entity tùy ý đều được phép: với XML không đáng tin, cần chặn DTD/external entities theo security policy.

### 4.2. Ví dụ hợp lệ: phần tử rỗng

~~~xml
<empty/>
~~~

Nếu con trỏ đang ở START_ELEMENT empty, `getElementText()` trả **chuỗi rỗng ""** và để con trỏ ở **END_ELEMENT empty**.

Phân biệt:

- **Không có text:** `""` hợp lệ.
- **Chỉ có whitespace:** kết quả có thể chứa whitespace, không tự trim.
- **Có text:** trả text đã kết hợp.
- **Có phần tử con:** ném XMLStreamException.

Nếu nghiệp vụ muốn trim whitespace, hãy thực hiện **sau khi đọc** và hiểu xem whitespace có ý nghĩa trong schema không.

### 4.3. Ví dụ không hợp lệ: nested element

~~~xml
<person>
  <name>Lan</name>
</person>
~~~

Khi con trỏ ở **START_ELEMENT person**, gọi `getElementText()` là sai: bên trong person có một **START_ELEMENT name**. Phương thức ném **XMLStreamException** vì person **không phải text-only leaf element**.

Cách đúng là dùng `nextTag()` đến START_ELEMENT name, sau đó gọi `getElementText()` cho name nếu name thực sự chỉ chứa text.

~~~java
// Mảnh minh họa, reader đang ở START_ELEMENT person.
reader.nextTag();            // START_ELEMENT name.
String name = reader.getElementText(); // "Lan", dừng ở END_ELEMENT name.
reader.nextTag();            // END_ELEMENT person, bỏ qua whitespace.
~~~

Không gọi `getElementText()` trên một container có nhiều children rồi mong nhận toàn bộ text của những descendants.

### 4.4. Ví dụ không hợp lệ: sai vị trí con trỏ

~~~java
// Mảnh minh họa.
reader.nextTag();   // START_ELEMENT a.
reader.next();      // CHARACTERS bên trong a.
reader.getElementText(); // XMLStreamException: không ở START_ELEMENT.
~~~

Ngay cả khi văn bản còn lại trong a là text-only, gọi ở CHARACTERS vẫn sai vì **precondition bắt buộc START_ELEMENT**.

Sau khi đã gọi `getElementText()` thành công, không gọi nó lần thứ hai ngay vì event hiện tại là **END_ELEMENT**.

### 4.5. Lưu ý tài nguyên

`getElementText()` tạo một **String chứa toàn bộ text của phần tử**. Với phần tử nhỏ hoặc trung bình, rất tiện. Nếu nội dung có thể dài hàng trăm MB, việc trả String có thể làm tăng heap và gây OutOfMemoryError. Dùng `next()` và xử lý các text events từng phần nếu không cần giữ tất cả trong RAM.

StAX là streaming API, nhưng **không phải mọi phương thức của StAX đều O(1) bộ nhớ**.

## 5. So sánh next, nextTag và getElementText

| Khía cạnh | next() | nextTag() | getElementText() |
| --- | --- | --- | --- |
| Trả về | `int` event type | `int`: START_ELEMENT hoặc END_ELEMENT | `String` |
| Di chuyển con trỏ | 1 event | 1 hoặc nhiều events đến tag | Qua toàn bộ phần text-only |
| Được dùng khi | Cần xử lý chi tiết event/mixed content | Element-only content, khoảng trắng xen giữa | Một leaf element có text |
| Bỏ qua comment/PI | Không, caller phải xử lý | Có | Có, trong phần tử text-only |
| Text không phải whitespace | Trả CHARACTERS | **XMLStreamException** | Được lấy vào String |
| Phần tử con | Trả START_ELEMENT và caller xử lý | Có thể trả START_ELEMENT của child | **XMLStreamException** |
| Vị trí sau thành công | Event vừa chuyển đến | START_ELEMENT/END_ELEMENT | END_ELEMENT tương ứng |
| Có thể tạo String lớn | Không tự tạo String toàn phần tử | Không | **Có** |
| Cần điều kiện event cụ thể | `hasNext()` trước khi gọi | XML phải phù hợp element-only | **Hiện tại phải là START_ELEMENT** |

**Quy tắc chọn nhanh:**

- Nếu cần đọc **nội dung pha trộn text + nested tags** → dùng **next()**.
- Nếu đang đi qua **cấu trúc các thẻ con cách nhau bằng whitespace** → dùng **nextTag()**.
- Nếu đã xác nhận **thẻ hiện tại là leaf chỉ chứa text** → dùng **getElementText()**.
- Nếu không rõ schema có cho nested elements không, **đừng dùng getElementText một cách mù quáng**.

## 6. Điều kiện hợp lệ của các getter khác

Các methods của XMLStreamReader phụ thuộc trạng thái con trỏ:

| Method | Trạng thái hợp lệ hoặc điều kiện |
| --- | --- |
| `getEventType()` | Dùng để biết event hiện tại, không di chuyển |
| `hasNext()` | Kiểm tra còn events, có thể ném XMLStreamException |
| `next()` | Khi còn event; thường bao bằng `hasNext()` |
| `nextTag()` | Duyệt element-only content như contract |
| `getElementText()` | **START_ELEMENT**, text-only element |
| `getLocalName()` | Event có tên như START_ELEMENT/END_ELEMENT; không gọi tại text |
| `getText()` | Các text-like event như CHARACTERS/CDATA/SPACE/COMMENT |
| `getAttributeValue(...)` | **START_ELEMENT** |
| `getAttributeCount()` | **START_ELEMENT** (hoặc ATTRIBUTE theo API state table) |
| `getNamespaceURI()` | Phải hiểu namespace context/current named element |
| `isStartElement()`/`isEndElement()` | Có thể dùng để guard trước getter yêu cầu element |
| `isCharacters()` | Dùng để kiểm tra text event |
| `require(type, namespace, name)` | So sánh event/name hiện tại, không tiến cursor |
| `getLocation()` | Vị trí parser hiện tại để diagnostics, có thể không chính xác tuyệt đối với mọi source |

Theo bảng trạng thái của Java SE 26 XMLStreamReader, nếu gọi một getter không hợp lệ ở event hiện tại, nó có thể ném **IllegalStateException**. Riêng `getElementText()` sai precondition được tài liệu hóa là **XMLStreamException**. Phân biệt exception của **API misuse** với exception do XML input không hợp lệ.

### 6.1. require(...) để kiểm tra contract rõ ràng

~~~java
// Mảnh minh họa, reader đang ở START_ELEMENT person.
reader.require(XMLStreamConstants.START_ELEMENT, null, "person");
~~~

`require(eventType, namespaceURI, localName)` **không di chuyển con trỏ**, chỉ xác minh current event phù hợp.

- Tham số `namespaceURI == null`: **bỏ qua kiểm tra namespace URI**, không phải luôn yêu cầu namespace rỗng.
- Tham số `localName == null`: **bỏ qua kiểm tra local name**.
- Nếu event, namespace hoặc local name không khớp, ném **XMLStreamException**.

Không dùng `require(...)` như một phương thức tìm thẻ; nó không gọi `next()` giúp bạn.

### 6.2. Namespace và prefix

~~~xml
<r:root xmlns:r="urn:demo">
  <r:message lang="vi">Xin chào</r:message>
</r:root>
~~~

Để kiểm tra message, nên dựa trên **namespace URI + local name** thay vì so sánh raw prefix `r`. Prefix có thể thay đổi nhưng namespace URI giữ semantics.

~~~java
// Mảnh minh họa khi cursor ở START_ELEMENT message.
reader.require(XMLStreamConstants.START_ELEMENT, "urn:demo", "message");
String lang = reader.getAttributeValue(null, "lang");
String text = reader.getElementText();
~~~

`getAttributeValue(null, "lang")` tra attribute không có namespace trong ví dụ. **Default namespace của element không tự áp cho unprefixed attributes**, nên phải hiểu XML namespace rules khi lấy attributes.

## 7. Công thức đọc một cấu trúc đơn giản

Ví dụ XML:

~~~xml
<user>
  <id>42</id>
  <name>Đặng</name>
</user>
~~~

Khi cursor bắt đầu START_DOCUMENT:

~~~java
// Mảnh minh họa; cần reader từ XMLInputFactory đã cấu hình an toàn.
reader.nextTag();  // START_ELEMENT user.
reader.require(XMLStreamConstants.START_ELEMENT, null, "user");

reader.nextTag();  // START_ELEMENT id.
reader.require(XMLStreamConstants.START_ELEMENT, null, "id");
String id = reader.getElementText();  // END_ELEMENT id.

reader.nextTag();  // START_ELEMENT name.
reader.require(XMLStreamConstants.START_ELEMENT, null, "name");
String name = reader.getElementText(); // END_ELEMENT name.

reader.nextTag();  // END_ELEMENT user.
reader.require(XMLStreamConstants.END_ELEMENT, null, "user");
~~~

**Điều kiện để pattern này đúng:**

1. `user` chỉ chứa các phần tử con và whitespace/comment/PI giữa chúng.
2. `id` và `name` chỉ chứa text (không có nested element).
3. Cấu trúc là đúng thứ tự yêu cầu.
4. Namespaces được kiểm tra nếu schema có namespace URI.
5. Parser không cho XML không đáng tin truy cập DTD/external entities.
6. Không đọc thêm `nextTag()` sau END_ELEMENT user nếu đã đạt scope đích.
7. XML malformed phải được xử lý như lỗi input, không silently skip.

Đây là code minh họa có assumptions; với schema phức tạp, viết state machine hoặc parser rõ depth và element names, thay vì ép mọi XML vào chuỗi nextTag cố định.

## 8. Ví dụ Java 17+ hoàn chỉnh: kiểm thử trạng thái con trỏ

Để kiểm chứng chính xác các điều kiện, ví dụ độc lập **StaxCursorRulesDemo.java** dùng **XMLInputFactory** chuẩn của JDK, **XMLStreamReader** và chuỗi XML tự tạo trong memory. Không cần Maven, Gradle, database, internet hay thư viện bên thứ ba.

Chương trình kiểm thử:

1. Ban đầu là START_DOCUMENT.
2. nextTag bỏ whitespace/comment để tới catalog/item.
3. Đọc `id=7` đúng START_ELEMENT.
4. `getElementText()` kết hợp text, CDATA và XML entity **&amp;**, giữ tiếng Việt.
5. Sau getElementText, event là END_ELEMENT của item.
6. `<empty/>` trả text dài 0 và có cả START_ELEMENT/END_ELEMENT.
7. `next()` duyệt được chuỗi chi tiết START/TEXT/END.
8. `hasNext()` false sau END_DOCUMENT.
9. nextTag từ nonwhitespace CHARACTERS ném XMLStreamException.
10. getElementText khi gặp child element ném XMLStreamException.
11. getElementText khi ở CHARACTERS thay vì START_ELEMENT ném XMLStreamException.
12. `require(...)` kiểm tra đúng/sai localName.
13. XML có DOCTYPE/external entity bị parser-security path từ chối trong JDK được kiểm thử.

**Giới hạn:** Ví dụ được chạy trên **OpenJDK 24.0.2**. Với provider StAX khác, cơ chế báo DTD hoặc cách chia CHARACTERS có thể khác; security rules phải được integration test theo factory implementation. 19 dòng stdout được xác minh cho input và runtime test, không phải cam kết toàn bộ provider có mọi chi tiết giống nhau.

### 8.1. File StaxCursorRulesDemo.java

~~~java
import java.io.StringReader;
import java.util.ArrayList;
import java.util.List;
import javax.xml.XMLConstants;
import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLStreamConstants;
import javax.xml.stream.XMLStreamException;
import javax.xml.stream.XMLStreamReader;

public final class StaxCursorRulesDemo {
    private static XMLInputFactory secureFactory() {
        XMLInputFactory f = XMLInputFactory.newFactory();
        f.setProperty(XMLInputFactory.SUPPORT_DTD, false);
        f.setProperty(XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
        f.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        f.setXMLResolver((publicId, systemId, base, ns) -> {
            throw new XMLStreamException("External entity blocked");
        });
        return f;
    }

    private static XMLStreamReader from(String xml) throws XMLStreamException {
        return secureFactory().createXMLStreamReader(new StringReader(xml));
    }

    private static void validTagAndText() throws XMLStreamException {
        String doc = "<catalog><!--comment-->\n"
                + "<item id='7'>Xin <![CDATA[chào]]> &amp; Việt Nam</item>\n"
                + "<empty/>\n</catalog>";
        XMLStreamReader r = from(doc);
        try {
            System.out.println("initial=" + (r.getEventType() == XMLStreamConstants.START_DOCUMENT));
            System.out.println("root=" + name(r, r.nextTag()));
            System.out.println("item=" + name(r, r.nextTag()));
            System.out.println("itemId=" + r.getAttributeValue(null, "id"));
            System.out.println("itemText=" + r.getElementText());
            System.out.println("afterText=" + name(r, r.getEventType()));
            System.out.println("emptyStart=" + name(r, r.nextTag()));
            System.out.println("emptyTextLength=" + r.getElementText().length());
            System.out.println("emptyEnd=" + name(r, r.getEventType()));
            System.out.println("rootEnd=" + name(r, r.nextTag()));
            System.out.println("endDocument=" +
                    (r.next() == XMLStreamConstants.END_DOCUMENT));
        } finally {
            r.close();
        }
    }

    private static String name(XMLStreamReader r, int kind) {
        if (kind == XMLStreamConstants.START_ELEMENT) {
            return "START:" + r.getLocalName();
        }
        if (kind == XMLStreamConstants.END_ELEMENT) {
            return "END:" + r.getLocalName();
        }
        return String.valueOf(kind);
    }

    private static void nextEvents() throws XMLStreamException {
        XMLStreamReader r = from("<a>hi<b/>!</a>");
        List<String> events = new ArrayList<>();
        try {
            while (r.hasNext()) {
                int kind = r.next();
                if (kind == XMLStreamConstants.START_ELEMENT ||
                        kind == XMLStreamConstants.END_ELEMENT) {
                    events.add(name(r, kind));
                } else if (kind == XMLStreamConstants.CHARACTERS) {
                    events.add("TEXT:" + r.getText());
                } else if (kind == XMLStreamConstants.END_DOCUMENT) {
                    events.add("END_DOCUMENT");
                }
            }
            System.out.println("nextEvents=" + String.join("|", events));
            System.out.println("hasNextAfterEnd=" + r.hasNext());
        } finally {
            r.close();
        }
    }

    private static void invalidCases() throws XMLStreamException {
        XMLStreamReader a = from("<a>hello<b/></a>");
        try {
            a.nextTag(); // START_ELEMENT a
            boolean rejected = false;
            try {
                a.nextTag();
            } catch (XMLStreamException expected) {
                rejected = true;
            }
            System.out.println("nextTagTextRejected=" + rejected);
        } finally {
            a.close();
        }

        XMLStreamReader b = from("<a><b>child</b></a>");
        try {
            b.nextTag(); // START_ELEMENT a
            boolean rejected = false;
            try {
                b.getElementText();
            } catch (XMLStreamException expected) {
                rejected = true;
            }
            System.out.println("elementTextChildRejected=" + rejected);
        } finally {
            b.close();
        }

        XMLStreamReader c = from("<a>hello</a>");
        try {
            c.nextTag();
            c.next(); // CHARACTERS
            boolean rejected = false;
            try {
                c.getElementText();
            } catch (XMLStreamException expected) {
                rejected = true;
            }
            System.out.println("elementTextWrongStateRejected=" + rejected);
        } finally {
            c.close();
        }

        XMLStreamReader d = from("<a><b/></a>");
        try {
            d.nextTag();  // START_ELEMENT a
            d.require(XMLStreamConstants.START_ELEMENT, null, "a");
            System.out.println("requireMatched=true");
            boolean rejected = false;
            try {
                d.require(XMLStreamConstants.START_ELEMENT, null, "b");
            } catch (XMLStreamException expected) {
                rejected = true;
            }
            System.out.println("requireWrongNameRejected=" + rejected);
        } finally {
            d.close();
        }
    }

    private static void forbiddenDtd() throws XMLStreamException {
        String xml = "<!DOCTYPE a [<!ENTITY x SYSTEM 'file:///private/data'>]><a>&x;</a>";
        XMLStreamReader r = from(xml);
        boolean rejected = false;
        try {
            while (r.hasNext()) {
                int kind = r.next();
                if (kind == XMLStreamConstants.DTD) {
                    throw new XMLStreamException("DOCTYPE forbidden");
                }
            }
        } catch (XMLStreamException expected) {
            rejected = true;
        } finally {
            r.close();
        }
        System.out.println("dtdRejected=" + rejected);
    }

    public static void main(String[] args) throws Exception {
        validTagAndText();
        nextEvents();
        invalidCases();
        forbiddenDtd();
    }
}
~~~

### 8.2. Biên dịch và chạy

Lưu file đúng tên **StaxCursorRulesDemo.java**, tại thư mục chứa file và với **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 --release 17 StaxCursorRulesDemo.java
java StaxCursorRulesDemo
~~~

Hai lệnh trên cũng hoạt động trong Windows PowerShell. Không cần dependency bên ngoài JDK; StAX thuộc module chuẩn **java.xml**.

### 8.3. Stdout chính xác sau kiểm thử

~~~text
initial=true
root=START:catalog
item=START:item
itemId=7
itemText=Xin chào & Việt Nam
afterText=END:item
emptyStart=START:empty
emptyTextLength=0
emptyEnd=END:empty
rootEnd=END:catalog
endDocument=true
nextEvents=START:a|TEXT:hi|START:b|END:b|TEXT:!|END:a|END_DOCUMENT
hasNextAfterEnd=false
nextTagTextRejected=true
elementTextChildRejected=true
elementTextWrongStateRejected=true
requireMatched=true
requireWrongNameRejected=true
dtdRejected=true
~~~

**Đã chạy và kiểm tra chính xác 19 dòng stdout bằng OpenJDK 24.0.2** với `--release 17`. Dòng **dtdRejected=true** thể hiện parser-security path trên JDK đã thử nghiệm, không có nghĩa mọi StAX provider đều báo cùng một sự kiện DTD trong mọi cấu hình.

### 8.4. Ý nghĩa những dòng quan trọng

- **initial=true**: XMLStreamReader bắt đầu ở START_DOCUMENT.
- **root/item**: `nextTag()` có thể bỏ qua whitespace và COMMENT để tìm START_ELEMENT tiếp theo.
- **itemId=7**: thuộc tính được lấy khi con trỏ ở START_ELEMENT item.
- **itemText**: `getElementText()` đã kết hợp **Xin**, CDATA **chào**, entity **&amp;** và chữ Việt.
- **afterText=END:item**: postcondition bắt buộc sau `getElementText()` thành công.
- **emptyStart/emptyEnd**: XML empty element có cả START/END; text dài 0.
- **rootEnd=END:catalog**: `nextTag()` **có thể trả END_ELEMENT**, không phải chỉ START.
- **endDocument=true** và **hasNextAfterEnd=false**: dừng đúng end-of-document.
- **nextEvents=...**: `next()` không bỏ text của mixed-content `<a>hi<b/>!</a>`.
- **nextTagTextRejected=true**: nonwhitespace text không hợp lệ cho `nextTag()`.
- **elementTextChildRejected=true**: nested element không hợp lệ với `getElementText()`.
- **elementTextWrongStateRejected=true**: `getElementText()` chỉ được gọi ở START_ELEMENT.
- **requireMatched=true**, **requireWrongNameRejected=true**: kiểm tra contract hiện tại, không di chuyển con trỏ.
- **dtdRejected=true**: XML có DOCTYPE/external entity bị từ chối trong test JDK.

## 9. Security: không dùng StAX mặc định cho XML không đáng tin

XML có thể chứa **DTD, external entity references, entity expansion** hoặc cấu trúc lớn gây tiêu tốn memory. StAX không tự bảo vệ đầy đủ chỉ bởi vì nó là streaming parser.

Với XML từ upload/API/partner hoặc các nguồn chưa được kiểm soát:

1. **Tắt DTD support** khi business không cần.
2. **Không hỗ trợ external entities**.
3. **Chặn external DTD access** bằng `XMLConstants.ACCESS_EXTERNAL_DTD`.
4. Cấu hình **XMLResolver từ chối network/file access**.
5. Nếu parser có trả **DTD event** khi đầu vào có DOCTYPE, **chủ động từ chối** theo policy.
6. Kiểm soát **size, depth, number of elements, attributes và tổng text**.
7. Bắt **XMLStreamException** và không cố nuốt lỗi để tiếp tục phần còn lại.
8. Không bỏ qua **IllegalArgumentException** khi factory không chấp nhận security property; fail closed hoặc dùng provider đã kiểm chứng.
9. Không mặc định `getElementText()` an toàn với phần tử có text nhiều GB: nó vẫn phải tạo String.
10. Kiểm thử cấu hình trên **StAX provider và JDK runtime** mà ứng dụng thật sự sử dụng.

### 9.1. Mẫu factory

~~~java
XMLInputFactory factory = XMLInputFactory.newFactory();
factory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
factory.setProperty(XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
factory.setXMLResolver((publicId, systemId, base, namespace) -> {
    throw new XMLStreamException("External XML entity blocked");
});
~~~

Đây là mảnh minh họa với các imports từ ví dụ đầy đủ. **Không bắt rồi bỏ qua lỗi setProperty** nếu provider không hỗ trợ một thiết lập bảo mật cần thiết.

Lưu ý: `XMLConstants.FEATURE_SECURE_PROCESSING` thường được dùng ở các JAXP parser/transformer factories khác, nhưng **StAX dùng cơ chế external-access restrictions và properties riêng**. Không đơn giản copy cách cấu hình DOM/SAX rồi giả định đã khóa StAX.

### 9.2. Không chỉ dựa vào một kiểm tra DTD event

Tắt DTD support và external entities là lớp phòng thủ nền tảng. Việc ứng dụng chủ động từ chối `XMLStreamConstants.DTD` khi parser thông báo là lớp bổ sung. Một provider khác có thể **ném lỗi trước khi trả DTD**, hoặc có cách báo khác. Phải test fail-closed behavior cho **DOCTYPE, internal entities, external files/URLs và entity expansion** trên chính runtime/provider.

**Đừng đưa một XML nguy hiểm có đường dẫn thật tới tài nguyên riêng tư vào test production**. Dùng đường dẫn giả, sandbox và input được kiểm soát.

## 10. Quản lý tài nguyên

`XMLStreamReader.close()` giải phóng tài nguyên gắn với parser, nhưng **không đóng underlying input source** theo Javadoc. Với file/network stream, ứng dụng phải sở hữu và đóng cả hai.

### 10.1. Ví dụ xử lý file UTF-8

~~~java
// Mảnh minh họa với Path inputFile do ứng dụng xác thực.
try (java.io.Reader input =
        java.nio.file.Files.newBufferedReader(
                inputFile, java.nio.charset.StandardCharsets.UTF_8)) {
    XMLStreamReader reader = secureFactory().createXMLStreamReader(input);
    try {
        while (reader.hasNext()) {
            int event = reader.next();
            if (event == XMLStreamConstants.DTD) {
                throw new XMLStreamException("DOCTYPE forbidden");
            }
            // Xử lý event theo schema và giới hạn an toàn.
        }
    } finally {
        reader.close();
    }
}
~~~

Đây là mảnh minh họa dùng helper `secureFactory()` ở ví dụ đầy đủ. Input file phải có nguồn gốc và kích thước được phép; không nhận tùy ý một path không kiểm soát từ client.

**Trong Java 17, XMLStreamReader không implement AutoCloseable**, nên gọi `close()` trong `finally` như trên. Underlying `Reader` là AutoCloseable, do đó dùng try-with-resources. Nếu parser.close cũng ném XMLStreamException sau khi parse đã lỗi, cần chính sách giữ primary failure/suppressed thay vì che lỗi quan trọng.

### 10.2. Không giữ mảng text nội bộ sau next

`XMLStreamReader.getTextCharacters()` có thể trả một **mảng nội bộ tạm thời, read-only**, chỉ có hiệu lực đến khi con trỏ chuyển sang event kế tiếp. Không sửa mảng đó và không cache reference sau `next()`.

Nếu cần giữ text, **copy** phần liên quan sang buffer do ứng dụng sở hữu. Với XML rất lớn, ưu tiên xử lý incremental và quota thay vì gom tất cả text.

### 10.3. Không chia sẻ một XMLStreamReader giữa nhiều threads

XMLStreamReader có **cursor mutable**. Nếu hai threads cùng gọi `next()`/`nextTag()`/`getElementText()`, chúng sẽ làm thay đổi vị trí của nhau và dễ gây invalid-state errors. Mỗi parser scope nên có một owner rõ ràng; không giả định thread-safety khi provider không bảo đảm.

## 11. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| `nextTag()` ném XMLStreamException | XML có text không phải whitespace giữa các tags | Dùng next() cho mixed content |
| `getElementText()` ném trên container | Có nested START_ELEMENT | Chỉ dùng cho leaf text-only, duyệt child bằng nextTag |
| `getElementText()` ném tại CHARACTERS | Cursor không ở START_ELEMENT | Kiểm tra getEventType()/isStartElement() |
| Gọi nextTag và bỏ mất END_ELEMENT | Giả định nextTag chỉ trả START | Xử lý cả START và END |
| Gọi next() sau END_DOCUMENT | Hết events | Kiểm tra hasNext(), quản lý scope |
| Đọc `<empty/>` không nhận text event | Empty element không cần CHARACTERS | Xử lý START/END hoặc getElementText() trả "" |
| Text bị thiếu một phần | Parser chia text thành nhiều CHARACTERS events | Append/copy mọi text events thuộc phạm vi |
| `getText()` ném IllegalStateException | Gọi sai event | Kiểm tra event hiện tại trước getter |
| `getLocalName()` ở text event | Text không có element name | Chỉ lấy name tại START/END |
| `getAttributeValue` sai vị trí | Không ở START_ELEMENT | Lấy attribute trước khi advance |
| Đọc nhầm namespace | So prefix thay vì URI/local name | Dùng require/namespaceURI/localName |
| `getElementText()` trả whitespace | XML có whitespace text thực | Trim chỉ khi schema cho phép |
| XML entity &amp; trở thành & | Parser decode entity chuẩn | Đúng semantics; không double-escape |
| DTD/external entity bị xử lý | Parser cấu hình mặc định không đủ an toàn | Disable DTD/entities, block external access |
| parser.close nhưng file còn mở | close không đóng underlying source | Đóng Reader/InputStream riêng |
| XML lớn gây heap pressure | Gom text bằng StringBuilder/getElementText | Stream incremental với limit |
| Parser lỗi nhưng code tiếp tục | Swallow XMLStreamException | Dừng, trả input error, đóng resources |
| `require` báo mismatch | Event/name/namespace không như expected | Kiểm tra schema, không bỏ qua |
| Test trên JDK pass, provider khác sai | Khác về coalescing/security behavior | Integration tests trên provider thật |

### 11.1. Phân biệt lỗi input và lỗi dùng API

- **XMLStreamException** có thể do XML malformed, thiếu thẻ đóng, DTD bị cấm hoặc gọi nextTag/getElementText sai contract.
- **IllegalStateException** thường liên quan đọc getter ở event state không hợp lệ.
- **NoSuchElementException** có thể xảy ra khi `next()`/`nextTag()` được gọi sau khi hết events.
- **IllegalArgumentException** có thể xảy ra nếu factory không hỗ trợ một property value.
- **IOException** thuộc underlying InputStream/Reader khi đọc file hoặc network; tùy parser nó có thể được bọc trong XMLStreamException.

Không tự chuyển tất cả thành “XML invalid” nếu lỗi thực tế là code đang gọi sai API state. Logging nội bộ cần phân biệt input lỗi với parser misuse/implementation limitation.

## 12. Thiết kế test cho các điều kiện hợp lệ

| Test | Kỳ vọng |
| --- | --- |
| Initial parser | `getEventType() == START_DOCUMENT` |
| `next()` mixed content | Không bỏ text và các thẻ con |
| `next()` + `hasNext()` | Dừng ở END_DOCUMENT |
| `nextTag()` có whitespace | Bỏ whitespace đến START/END |
| `nextTag()` có comment và PI | Bỏ qua đúng event types |
| `nextTag()` gặp nonwhitespace text | XMLStreamException |
| `nextTag()` đi qua empty element | START_ELEMENT rồi END_ELEMENT |
| `getElementText()` tại text-only leaf | Trả text |
| `getElementText()` với CDATA/escaped ampersand | Hợp nhất theo XML semantics |
| `getElementText()` tại empty leaf | Trả chuỗi rỗng |
| `getElementText()` có child element | XMLStreamException |
| `getElementText()` tại CHARACTERS | XMLStreamException |
| `require(...)` đúng type/name | Không đổi cursor |
| `require(...)` sai type/name | XMLStreamException |
| `getAttributeValue` tại START_ELEMENT | Trả value chính xác |
| Unicode tiếng Việt | Giữ nguyên dấu và text |
| Namespace URI | Dùng expanded name thay prefix |
| DTD/external entity | Không đọc filesystem/network; từ chối theo policy |
| Parser close | Không rò resource, input stream tự đóng |
| XML lớn | Giới hạn bytes, depth, elements, memory |
| Multiple StAX providers | Security properties và event handling được xác minh |

Test cụ thể của ví dụ đã kiểm tra nhiều mục trong bảng. Các trường hợp namespace phức tạp, file/network size và provider-specific behavior cần integration tests riêng.

## 13. Bài tập tự luyện

1. Chạy ví dụ và giải thích vì sao `itemText` có ký tự `&` chứ không có chuỗi `&amp;`.
2. Thay `nextTag()` bằng `next()` tại bước tìm item, quan sát whitespace/COMMENT events và tự kiểm tra event type.
3. Đổi `<item>` thành `<item><strong>Xin</strong> chào</item>`, giải thích vì sao getElementText() phải throw.
4. Tại START_ELEMENT item, gọi `getElementText()` hai lần liên tiếp, dự đoán exception của lần thứ hai.
5. Thử `<empty/>` và `<empty></empty>`, so sánh START/END events.
6. Thử `<item>   </item>`, phân biệt whitespace String với empty String.
7. Bỏ comment trong catalog rồi thêm processing instruction, test nextTag bỏ qua.
8. Thêm nonwhitespace text giữa hai item, xem nextTag ném XMLStreamException đúng chỗ.
9. Thêm CDATA chứa text, so sánh next() events khi IS_COALESCING true/false.
10. Dùng getEventType() trước/sau getElementText(), ghi lại trạng thái chính xác.
11. Dùng require START_ELEMENT với local name sai để chủ động báo lỗi cấu trúc.
12. Đổi XML sang namespace `urn:example`, kiểm tra URI/local name và unprefixed attribute.
13. Viết phương thức đọc một document có nhiều `<item>` với nextTag(), xử lý đúng END_ELEMENT của root.
14. Viết parser mixed-content `<p>Hello <em>world</em>!</p>` bằng next() mà không bỏ text.
15. Dùng next() và StringBuilder có giới hạn để đọc text nhiều events, không gọi getElementText() cho XML quá lớn.
16. Giả lập XML có DOCTYPE và external entity; kiểm tra factory từ chối, không thực sự đọc file bí mật.
17. Bỏ ACCESS_EXTERNAL_DTD rồi xem vì sao không được tin kết quả production chỉ dựa trên một máy.
18. Tạo file UTF-8 có tiếng Việt; đóng Reader lẫn XMLStreamReader theo ownership.
19. Kiểm tra hasNext() sau END_DOCUMENT; không dùng exception làm điểm dừng vòng lặp.
20. So sánh lỗi XMLStreamException do malformed XML với IllegalStateException do gọi sai getter.

## 14. Checklist trước production

- [ ] Dùng XMLStreamReader cho streaming pull parsing, không giả định mọi API đều tiết kiệm RAM.
- [ ] Biết cursor bắt đầu START_DOCUMENT và `next()` di chuyển tới một event.
- [ ] Kiểm tra hasNext trước next, xử lý END_DOCUMENT đúng scope.
- [ ] Không giả định text là đúng một CHARACTERS event.
- [ ] Không bỏ CHARACTERS/CDATA cần thiết khi XML mixed-content.
- [ ] `nextTag()` chỉ dành cho element-only content có whitespace/comment/PI phù hợp.
- [ ] Khi dùng nextTag, xử lý cả START_ELEMENT lẫn END_ELEMENT.
- [ ] `getElementText()` chỉ được gọi ở START_ELEMENT của text-only leaf.
- [ ] Sau getElementText, cursor đang ở END_ELEMENT tương ứng.
- [ ] Không gọi getElementText cho container có nested elements.
- [ ] Không gọi getText/getLocalName/getAttributeValue ở event state không hợp lệ.
- [ ] Nếu cần, dùng require(event, namespaceURI, localName) để xác minh contract.
- [ ] Không suy namespace theo raw prefix, dùng URI/local name.
- [ ] Với XML không đáng tin, khóa DTD, external entities và external DTD access.
- [ ] XMLInputFactory security property không được hỗ trợ → fail closed.
- [ ] Có quota độ dài XML, độ sâu, elements, attributes và xử lý timeout/cancellation.
- [ ] Parser.close và underlying input đều được đóng đúng ownership.
- [ ] Không cache mảng getTextCharacters() sau khi cursor tiến.
- [ ] Không share một XMLStreamReader giữa threads không có contract phù hợp.
- [ ] Test Unicode, empty element, comments, whitespace, mixed text và nested elements.
- [ ] Test trên StAX provider/runtime thực tế, đặc biệt security và event behavior.

## Kết luận

**next()** đọc **từng event** và là lựa chọn tổng quát nhất khi cần xử lý text, comments hoặc mixed content. **nextTag()** là thao tác tiện lợi nhưng có điều kiện: chỉ bỏ qua whitespace/comment/processing instruction để tìm START_ELEMENT hoặc END_ELEMENT, và **không bỏ qua text có ý nghĩa**. **getElementText()** chỉ hợp lệ ở **START_ELEMENT của phần tử chứa text-only content**, trả một String đã kết hợp và **để cursor tại END_ELEMENT tương ứng**.

Muốn sử dụng StAX đúng, hãy thiết kế theo **cursor state**, không chỉ theo tên thẻ. Đồng thời, với XML không đáng tin, **khóa DTD/external entities, quản lý giới hạn và đóng tài nguyên**. Toàn bộ nội dung dùng API StAX còn được hỗ trợ hiện nay và ví dụ Java 17+ đã được kiểm thử thực tế.

**Tài liệu chính thức còn áp dụng:**

- [XMLStreamReader — Java SE 26 (next, nextTag, getElementText, state table)](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLStreamReader.html)
- [XMLStreamReader — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/stream/XMLStreamReader.html)
- [XMLInputFactory — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLInputFactory.html)
- [XMLInputFactory — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/stream/XMLInputFactory.html)
- [XMLStreamConstants — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLStreamConstants.html)
- [XMLStreamException — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLStreamException.html)
- [XMLConstants — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/XMLConstants.html)
- [JAXP Security Guide — Java SE 17](https://docs.oracle.com/en/java/javase/17/security/java-api-xml-processing-jaxp-security-guide.html)