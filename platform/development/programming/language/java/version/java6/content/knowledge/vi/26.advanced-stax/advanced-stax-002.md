# StreamFilter, EventFilter và lọc dữ liệu trong StAX nâng cao

## 1. Từ XML đầy đủ đến luồng sự kiện có chọn lọc

StAX (*Streaming API for XML*) là bộ API Java để xử lý XML lần lượt theo các sự kiện, thay vì luôn dựng toàn bộ cây DOM trong bộ nhớ. Với dữ liệu lớn, ta thường muốn **chỉ nhìn thấy những sự kiện liên quan**, chẳng hạn các start element `<order>` đã thanh toán, hoặc loại các comment và whitespace chỉ dùng để thụt lề.

Trong Java hiện hành, hai interface nhỏ giải quyết nhu cầu này:

- **`javax.xml.stream.StreamFilter`** nhận **`XMLStreamReader`** đang ở một trạng thái sự kiện và quyết định trạng thái đó có được đưa ra từ một *filtered cursor reader* hay không.
- **`javax.xml.stream.EventFilter`** nhận đối tượng **`XMLEvent`** và quyết định đối tượng sự kiện đó có được đưa ra từ một *filtered event reader* hay không.

Cả hai đều làm việc qua các overload hiện hành của `XMLInputFactory.createFilteredReader`. Chúng **không thay thế XML parser**, **không xác thực XML Schema**, **không tự trích xuất subtree hoàn chỉnh** và **không bảo đảm chỉ parse những bytes đã chọn**. Parser bên dưới vẫn phải đọc dữ liệu để biết sự kiện nào phù hợp với predicate.

Tư duy quan trọng nhất:

> Filter chọn những **sự kiện được nhìn thấy bởi consumer**, chứ không tự tạo một XML document mới hoặc bảo đảm cấu trúc cha–con vẫn nguyên vẹn sau khi một số sự kiện bị ẩn.

Bài viết dùng Java 17+ và API `java.xml` hiện còn áp dụng, phân biệt rõ lựa chọn filter, xử lý dữ liệu, giới hạn bảo mật và trường hợp phải giữ nguyên cấu trúc XML. Ví dụ `StaxFilterDemo.java` đã biên dịch bằng `javac --release 17` và chạy thành công trên JDK 24.

## 2. Hai họ API của StAX

~~~text
XML bytes / characters
         |
         v
 XMLInputFactory
         |
         +--> XMLStreamReader (cursor)
         |          |
         |          +--> StreamFilter.accept(XMLStreamReader)
         |                       |
         |                       v
         |             filtered XMLStreamReader
         |
         +--> XMLEventReader (event objects)
                    |
                    +--> EventFilter.accept(XMLEvent)
                                 |
                                 v
                         filtered XMLEventReader
~~~

Cursor API và event API có những khác biệt thực tế:

| Khía cạnh | `StreamFilter` | `EventFilter` |
| --- | --- | --- |
| Input của predicate | `XMLStreamReader` | `XMLEvent` |
| API được bọc | `XMLStreamReader` | `XMLEventReader` |
| Kiểu kết quả | Filtered `XMLStreamReader` | Filtered `XMLEventReader` |
| Dạng đọc thông thường | `getEventType()`, `next()`, `getName()` | `nextEvent()`, `peek()`, `StartElement` |
| Truy cập thuộc tính | `getAttributeValue(...)` ở `START_ELEMENT` | `start.getAttributeByName(QName)` |
| Dữ liệu để giữ lại | Trạng thái cursor hiện tại, dễ bị thay đổi ở `next()` | Đối tượng sự kiện đã được tạo |
| Ưu điểm thường gặp | Ít lớp đối tượng trung gian, phù hợp loop thấp tầng | Cấu trúc event dễ chuyển qua nhiều bước xử lý |
| Cẩn thận | Filtered cursor có thể đã đứng tại một sự kiện accepted ngay khi khởi tạo | `peek()` không tiêu thụ; `hasNext()` có thể làm provider chuẩn bị sự kiện |
| Vòng đời | Đóng reader bằng `close()` và quản lý nguồn | Đóng event reader bằng `close()` và quản lý nguồn |

Hai chữ **Stream** và **Event** không có nghĩa một bên là “lọc nội dung” còn bên kia là “lọc XML tag”; cả hai đều lọc **events**, chỉ khác mô hình truy cập.

### 2.1. Đúng chữ ký method

~~~java
XMLStreamReader createFilteredReader(
        XMLStreamReader reader,
        StreamFilter filter) throws XMLStreamException;

XMLEventReader createFilteredReader(
        XMLEventReader reader,
        EventFilter filter) throws XMLStreamException;
~~~

Đây là **chữ ký minh họa** từ `XMLInputFactory`, không phải source khai báo để bạn biên dịch riêng. Chú ý overload thứ nhất trả **`XMLStreamReader`**, không phải `XMLEventReader`, dù một số bản hiển thị JavaDoc có thể có câu mô tả return bị nhầm. Type signature là nguồn quyết định khi viết code.

Một đoạn thiết lập:

~~~java
XMLInputFactory factory = XMLInputFactory.newFactory();

XMLStreamReader rawCursor =
        factory.createXMLStreamReader(sourceReader);
StreamFilter predicate = reader ->
        reader.getEventType() == XMLStreamConstants.START_ELEMENT;

XMLStreamReader filteredCursor =
        factory.createFilteredReader(rawCursor, predicate);
~~~

Đây là snippet với `sourceReader` được mở sẵn và import `javax.xml.stream.*`. Nó chọn START_ELEMENT trên cursor; **nó không có phần tử END_ELEMENT/CHARACTERS trong filtered output**.

Đối ứng với event reader:

~~~java
XMLEventReader rawEvents =
        factory.createXMLEventReader(sourceReader);
EventFilter predicate = XMLEvent::isStartElement;

XMLEventReader filteredEvents =
        factory.createFilteredReader(rawEvents, predicate);
~~~

Hai snippet là **hai cách dùng độc lập**; không dùng cùng một `Reader` đã bị tiêu thụ hết cho cả hai mà không mở lại. Không đồng thời dùng `rawCursor`/`rawEvents` để tiến parser trong khi wrapper đã sở hữu luồng đọc.

## 3. Interface `StreamFilter` chính xác làm gì?

Interface:

~~~java
@FunctionalInterface
public interface StreamFilter {
    boolean accept(XMLStreamReader reader);
}
~~~

Predicate được gọi với **cursor đang ở một event**. Nó trả:

- `true`: event hiện tại được filtered reader cho consumer nhìn thấy.
- `false`: event bị bỏ qua khỏi output của wrapper; underlying parser vẫn có thể đã đọc nó.

Một predicate chỉ lấy start elements:

~~~java
StreamFilter starts = reader ->
        reader.getEventType() == XMLStreamConstants.START_ELEMENT;
~~~

Trong `accept(...)`, **chỉ đọc thông tin của event hiện tại**. Không được gọi `reader.next()`, `nextTag()` hoặc `getElementText()` ngay trong predicate, vì làm như vậy **thay đổi trạng thái cursor dưới chân wrapper**; filter có thể bỏ sót events, gọi getter ở sai trạng thái hoặc không thể duy trì contract của `hasNext()`.

### 3.1. Chọn bằng QName thay vì prefix

Nếu cần phần tử `{urn:demo:orders}order`, viết:

~~~java
QName ORDER = new QName("urn:demo:orders", "order");

StreamFilter onlyOrders = reader ->
        reader.getEventType() == XMLStreamConstants.START_ELEMENT
        && ORDER.equals(reader.getName());
~~~

Đây là snippet. `QName.equals` so **namespace URI + local part**, không dựa vào lexical prefix. Hai phần tử:

~~~xml
<o:order xmlns:o="urn:demo:orders"/>
<order xmlns="urn:demo:orders"/>
~~~

có cùng expanded name `{urn:demo:orders}order`. Ngược lại:

~~~xml
<x:order xmlns:x="urn:demo:other"/>
~~~

không được chọn. **Không** chỉ so `reader.getLocalName().equals("order")` nếu nhiều vocabularies có tên local `order` giống nhau.

### 3.2. Lọc thêm attribute

Giả sử XML:

~~~xml
<orders xmlns="urn:demo:orders">
  <order id="A" status="paid"/>
  <order id="B" status="pending"/>
</orders>
~~~

Muốn chọn start element của `order` có `status="paid"`:

~~~java
StreamFilter paidOrders = reader ->
        reader.getEventType() == XMLStreamConstants.START_ELEMENT
        && ORDER.equals(reader.getName())
        && "paid".equals(
                reader.getAttributeValue("", "status"));
~~~

Đây là snippet với biến `QName ORDER` ở trên. `getAttributeValue("", "status")` yêu cầu **attribute không có namespace**, thích hợp với `status` không prefix. Trong `XMLStreamReader.getAttributeValue(String namespaceURI, String localName)`, truyền namespace `null` mang nghĩa **bỏ qua kiểm tra namespace**; nó **không** luôn đồng nghĩa “chỉ lấy attribute no-namespace”. Vì thế nên dùng `""` khi chủ ý tìm thuộc tính không namespace.

Truy cập attribute chỉ hợp lệ khi reader ở event phù hợp, ở đây đã bảo vệ bằng điều kiện `START_ELEMENT` và toán tử ngắn mạch `&&`.

## 4. Interface `EventFilter` chính xác làm gì?

Interface:

~~~java
@FunctionalInterface
public interface EventFilter {
    boolean accept(XMLEvent event);
}
~~~

Khác cursor filter, predicate nhận một `XMLEvent`. Khi là start element:

~~~java
EventFilter onlyPaidOrders = event -> {
    if (!event.isStartElement()) {
        return false;
    }

    StartElement start = event.asStartElement();
    if (!ORDER.equals(start.getName())) {
        return false;
    }

    Attribute status =
            start.getAttributeByName(new QName("", "status"));
    return status != null
            && "paid".equals(status.getValue());
};
~~~

Đây là snippet. Cần import `javax.xml.stream.EventFilter`, `javax.xml.stream.events.StartElement`, `Attribute` và `QName`. `StartElement.getAttributeByName(QName)` cho phép chọn attribute bằng **expanded name** rõ ràng. Tên attribute không prefix không thừa hưởng default namespace của element.

Với `XMLEventReader`, bạn dùng `hasNext()`, `peek()` và `nextEvent()`:

~~~java
XMLEvent next = filteredEvents.peek();
if (next != null && next.isStartElement()) {
    QName name = next.asStartElement().getName();
}

while (filteredEvents.hasNext()) {
    XMLEvent accepted = filteredEvents.nextEvent();
    // Xử lý event đã qua predicate.
}
~~~

Đây là snippet. `peek()` nhìn event tiếp theo **mà không tiêu thụ** nó; `nextEvent()` lấy event và tiến consumer. Dùng `nextEvent()` khi cần checked `XMLStreamException`; interface `XMLEventReader` còn có `Iterator.next()`, nhưng kiểu lỗi từ `next()` và khả năng wrap checked exception khiến `nextEvent()` rõ ràng hơn cho xử lý StAX.

### 4.1. Event object không phải toàn bộ subtree

Một `StartElement` là **một sự kiện**, không sở hữu tự động toàn bộ các `CHARACTERS`, children, `EndElement` sau nó. Nếu filter chỉ nhận `StartElement` của order đã thanh toán, filtered iterator **chỉ phát ra start events đã chọn**, chứ không phát ra amount/title/comments dưới các order đó.

Muốn đọc số tiền `<amount>150</amount>` của đơn A, cần phương án khác:

- Lọc có bảo tồn cấu trúc và tiến hành parse có state, hoặc
- Dùng **reader chưa bị lọc cấu trúc**, theo dõi depth/parent path và chỉ lưu dữ liệu thuộc nhánh đã chọn.

Demo ở mục 9 cho thấy phương án thứ hai thông qua `paidAmounts()`.

## 5. Filter sự kiện khác với lọc cây con hoặc biến đổi tài liệu

Đây là bẫy kiến thức lớn nhất. Với:

~~~xml
<root>
  <order id="A"><amount>150</amount></order>
  <order id="B"><amount>200</amount></order>
</root>
~~~

Một filter chỉ accept `START_ELEMENT` của `order id="A"` sẽ cho bạn một **start event**, không cho output:

~~~xml
<order id="A"><amount>150</amount></order>
~~~

Lý do: events khác như `START_ELEMENT amount`, `CHARACTERS 150`, `END_ELEMENT amount` và `END_ELEMENT order` đã bị predicate từ chối.

**Nếu lọc START_ELEMENT mà bỏ END_ELEMENT, “stream” nhận được không còn là chuỗi event cân bằng để dựng XML hoàn chỉnh.** Không đưa thẳng chuỗi đó vào `XMLEventWriter` hoặc parser giả định event tree hoàn chỉnh.

### 5.1. Bốn bài toán khác nhau

| Nhu cầu | Chiến lược đúng |
| --- | --- |
| Đếm/ghi log các start elements có thuộc tính phù hợp | `StreamFilter` hoặc `EventFilter` chỉ chọn start events |
| Bỏ comment/whitespace thụt lề nhưng vẫn xử lý cây | Filter giữ tất cả START/END/CHARACTERS có nghĩa |
| Trích nguyên subtree `order id="A"` | Parse có **depth tracking**, hoặc transform/copy toàn bộ events của nhánh |
| Chuyển XML document sang document khác | Dùng transformer/writer phù hợp, giữ namespace bindings/END_ELEMENT đúng, không chỉ chọn lẻ các starts |

Nếu chỉ muốn query một giá trị nhỏ và XML không quá lớn, có thể đọc toàn bộ event stream rồi xử lý state, thường đơn giản hơn một filter phức tạp dễ làm hỏng cây.

### 5.2. Không dùng EventFilter để tự động “skip subtree”

Một `EventFilter` đơn giản:

~~~java
EventFilter keepPaidStarts = event ->
        event.isStartElement()
        && ORDER.equals(event.asStartElement().getName());
~~~

**Không làm** các children và end tags của đơn không hợp lệ biến mất theo một subtree rule. Nó chỉ chọn sự kiện start phù hợp về QName.

Nếu filter có state mutable `insideSelected`/`depth` trong `accept(...)`, cần rất thận trọng: các StAX providers có thể gọi predicate để xử lý lookahead, `hasNext()` hoặc `peek()` theo cách không tương đương “chính xác một lần cho mỗi event”. **Không đặt business side effects hoặc bộ đếm phụ thuộc số lần gọi `accept`**. Dùng parser loop sở hữu state, ghi nhận events theo thứ tự **đã tiêu thụ** ở consumer.

## 6. Bảo toàn cấu trúc: bỏ comment và whitespace đúng ngữ cảnh

Một filter bảo toàn cấu trúc có thể giữ:

- `START_DOCUMENT` và `END_DOCUMENT`.
- `START_ELEMENT` và `END_ELEMENT`.
- `CHARACTERS` có nội dung cần dùng.
- `CDATA` và các event đặc thù mà dữ liệu/serializer yêu cầu.
- Namespace declarations/attributes nằm trong start element; không bị hiểu nhầm như events lẻ.

Chỉ bỏ các loại mà nghiệp vụ xác nhận không cần. Ví dụ có thể bỏ `COMMENT` và whitespace **chỉ dùng để định dạng**.

### 6.1. Cursor filter

~~~java
StreamFilter keepStructure = reader -> {
    int type = reader.getEventType();
    return type != XMLStreamConstants.COMMENT
            && type != XMLStreamConstants.SPACE
            && !(type == XMLStreamConstants.CHARACTERS
                 && reader.isWhiteSpace());
};
~~~

Đây là snippet. Nó giữ các start/end tags và character data không chỉ có whitespace. `reader.isWhiteSpace()` chỉ cần gọi ở event `CHARACTERS` thích hợp; `&&` đảm bảo không gọi khi sai type.

### 6.2. Event filter

~~~java
EventFilter keepStructure = event ->
        event.getEventType() != XMLStreamConstants.COMMENT
        && !(event.isCharacters()
             && event.asCharacters().isWhiteSpace());
~~~

Predicate này có cùng mục đích trên `XMLEventReader`. Nó giữ event bắt đầu/kết thúc và không tự lọc theo tên element.

**Điều kiện để bỏ whitespace:** XML có nhiều định dạng sử dụng whitespace như dữ liệu có nghĩa: prose mixed content, `xml:space="preserve"`, code snippets, nội dung text. Trong các trường hợp ấy, **không bỏ trắng chỉ vì `isWhiteSpace()==true`**. Phải hiểu XML vocabulary/schema. Nếu không chắc, **giữ whitespace**. Demo chọn XML có khoảng trắng ngoài các scalar fields, nên bỏ whitespace thụt lề vẫn hợp lệ với mục đích đếm cấu trúc.

### 6.3. XML text có thể chia thành nhiều sự kiện

Một chuỗi text có thể xuất hiện qua nhiều `CHARACTERS` events (CDATA boundaries, entity handling, parser buffers). Không giả định một `getText()` là toàn bộ nội dung của `<title>...`. Có thể dùng `getElementText()` khi event hiện tại là start của **text-only element** và dữ liệu không có nested child elements; phương thức này **tiêu thụ** những events cho tới end tag tương ứng.

Đừng dùng `getElementText()` trên filtered reader **chỉ giữ START_ELEMENT**: character/end events đã bị ẩn, nên phương thức có thể thiếu nội dung, báo lỗi hoặc thay đổi vị trí cursor ngoài dự kiến. Trong ví dụ độc lập, `paidAmounts()` cố ý dùng **unfiltered cursor**, rồi gọi `getElementText()` chỉ tại `<amount>` đơn giản.

### 6.4. `nextTag()` cũng có precondition

`nextTag()` bỏ qua các events như whitespace/comments theo API rồi chuyển tới START_ELEMENT hoặc END_ELEMENT; nhưng nó **không xử lý văn bản có ý nghĩa như một child element tùy tiện**. Nếu dùng trên luồng chỉ có start events đã lọc, cây logic không còn cân bằng. Đừng coi nextTag/getElementText là shortcut luôn an toàn sau mọi dạng filter.

## 7. Bẫy cursor: sự kiện accepted đầu tiên có thể là trạng thái hiện tại

StAX `XMLStreamReader` khác `XMLEventReader` ở chỗ cursor **có trạng thái hiện tại**, ngay sau khi được tạo. Khi bọc `createFilteredReader(raw, filter)`, một implementation có thể **định vị filtered cursor ở sự kiện hợp lệ đầu tiên trước khi ứng dụng gọi `next()`**.

Ví dụ với bộ lọc chỉ nhận start element `<order status="paid">`: trên JDK 24 đã kiểm thử, ngay sau khi tạo wrapper:

~~~text
filtered.getEventType() == START_ELEMENT
~~~

và nó đang ở order A. Nếu lập tức chạy:

~~~java
while (filtered.hasNext()) {
    filtered.next();
    process(filtered); // Sai: có thể bỏ qua A!
}
~~~

thì A bị bỏ sót, output chỉ còn C. Đây là **một lỗi dễ xảy ra với filtered cursor**.

### 7.1. Pattern đúng: xử lý trạng thái hiện tại nếu phù hợp

~~~java
if (filtered.getEventType()
        == XMLStreamConstants.START_ELEMENT) {
    processCurrentStart(filtered);
}

while (filtered.hasNext()) {
    int type = filtered.next();
    if (type == XMLStreamConstants.START_ELEMENT) {
        processCurrentStart(filtered);
    }
}
~~~

Đây là snippet, `processCurrentStart(...)` là helper ứng dụng, không phải method có sẵn của JDK. Trong chương trình hoàn chỉnh ở mục 9, handler thực sự là `ids.add(filtered.getAttributeValue("", "id"))`.

Pattern này cho phép xử lý event hiện tại một lần nếu filtered reader được tạo đã đứng ở event đó, rồi mới xử lý những events sau khi `next()`. **Luôn kiểm tra getEventType**, không giả định event ban đầu luôn `START_DOCUMENT` khi dùng wrapper.

Ngược lại với `XMLEventReader`, `peek()` nhìn **event kế tiếp chưa tiêu thụ**, còn `nextEvent()` tiêu thụ nó. Demo xác minh `peek()` nhìn thấy A và vòng lặp `nextEvent()` vẫn bắt đầu từ A.

### 7.2. Filter callback có thể được gọi khi định vị/lookahead

Vì wrapper có thể đi tìm event hợp lệ đầu tiên trong constructor và làm lookahead ở `hasNext()`/`peek()`, **đừng tăng business counter trong `accept(...)`**:

~~~java
StreamFilter wrong = reader -> {
    totalOrders++; // Sai chỗ: số lần accept() không phải số event tiêu thụ.
    return reader.isStartElement();
};
~~~

Đây là **anti-pattern** có biến `totalOrders` minh họa. Nếu cần đếm, tăng **khi consumer đọc được event đã lọc**; không dựa vào số lần filter được nhà cung cấp StAX gọi.

## 8. Namespace và thuộc tính khi lọc dữ liệu

Trong XML:

~~~xml
<orders xmlns="urn:demo:orders"
        xmlns:other="urn:demo:other">
  <order id="A" status="paid"/>
  <other:order id="X" status="paid"/>
</orders>
~~~

cả hai có local name `order` và `status="paid"`. Nhưng chỉ phần tử đầu thuộc `urn:demo:orders`. Một filter bảo thủ nên so:

~~~java
QName wanted = new QName("urn:demo:orders", "order");

boolean match = reader.getEventType()
        == XMLStreamConstants.START_ELEMENT
        && wanted.equals(reader.getName())
        && "paid".equals(
                reader.getAttributeValue("", "status"));
~~~

Đây là snippet. **Prefix trong XML không phải danh tính**; `QName.equals` dựa trên namespace URI và local part. Một phần tử dùng prefix `o:order` hay default namespace vẫn có thể cùng expanded name. Trong khi đó `other:order` của URI khác phải bị loại.

Với EventFilter, so `StartElement.getName()` và lấy `Attribute` bằng `getAttributeByName(new QName("", "status"))`. Điều này cũng tránh lỗi default namespace: **default namespace áp cho unprefixed elements, không áp cho unprefixed attributes**.

### 8.1. Lọc attribute phức tạp hơn string comparison

Nếu `status` có thể là `paid`, `PAID`, `paid ` hoặc namespace-qualified, **đừng tự trim/ignore-case tuỳ tiện** khi schema quy định giá trị exact. Lọc chính xác theo contract nghiệp vụ, rồi validate values. Nếu số tiền là kiểu decimal, parse bằng `BigDecimal` khi cần; không dùng `double` cho money và không tin dữ liệu chưa validate.

Nếu XML có attribute `id` lặp lexical từ nhiều namespaces:

~~~xml
<order xmlns="urn:demo:orders"
       xmlns:m="urn:demo:meta"
       id="A"
       m:id="EXTERNAL-A"/>
~~~

thì `getAttributeValue(null, "id")` mang tính wildcard namespace theo contract; không dùng như cách chắc chắn lấy unqualified `id`. Dùng `getAttributeValue("", "id")` ở cursor API, hoặc `getAttributeByName(new QName("", "id"))` ở event API.

## 9. Ví dụ Java 17+ độc lập: lọc đơn hàng theo namespace và status

### 9.1. Tình huống

Chương trình `StaxFilterDemo.java` dùng XML chứa bốn phần tử có local name `order`:

- A: order namespace, `status="paid"`, amount `150`.
- B: order namespace, `status="pending"`, amount `200`.
- X: **other namespace**, `status="paid"`, amount `900`.
- C: order namespace, `status="paid"`, amount `300`.

Hai filters chỉ được chọn **A và C**. Chương trình cố ý còn một `COMMENT` và các khoảng trắng thụt lề, để test structural filters. Một method khác không dùng filtered reader để trích amount cùng `getElementText()` và chỉ lấy số tiền của A và C.

Factory:

- Bật namespace awareness.
- Không hỗ trợ DTD cho trường hợp dữ liệu này.
- Tắt external entities.
- Resolver từ chối external resources.

Các flags bảo mật là baseline, không thay thế giới hạn bytes/depth/time và việc kiểm tra provider nếu input không tin cậy.

### 9.2. Code hoàn chỉnh `StaxFilterDemo.java`

~~~java
import java.io.StringReader;
import java.util.ArrayList;
import java.util.List;
import javax.xml.namespace.QName;
import javax.xml.stream.EventFilter;
import javax.xml.stream.StreamFilter;
import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLStreamConstants;
import javax.xml.stream.XMLStreamException;
import javax.xml.stream.XMLStreamReader;
import javax.xml.stream.XMLEventReader;
import javax.xml.stream.events.Attribute;
import javax.xml.stream.events.StartElement;
import javax.xml.stream.events.XMLEvent;

public final class StaxFilterDemo {
    private static final String NS = "urn:demo:orders";
    private static final QName ORDER = new QName(NS, "order");
    private static final QName AMOUNT = new QName(NS, "amount");
    private static final QName ID = new QName("", "id");
    private static final QName STATUS = new QName("", "status");
    private static final String XML = """
            <orders xmlns="urn:demo:orders" xmlns:other="urn:demo:other">
              <order id="A" status="paid"><amount>150</amount></order>
              <order id="B" status="pending"><amount>200</amount></order>
              <other:order id="X" status="paid"><amount>900</amount></other:order>
              <!-- audit comment -->
              <order id="C" status="paid"><amount>300</amount></order>
            </orders>
            """;

    static XMLInputFactory secureFactory() throws XMLStreamException {
        XMLInputFactory factory = XMLInputFactory.newFactory();
        factory.setProperty(XMLInputFactory.IS_NAMESPACE_AWARE, true);
        factory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
        factory.setProperty(
                XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
        factory.setXMLResolver((publicId, systemId, baseUri, namespace) -> {
            throw new XMLStreamException("External resource forbidden");
        });
        return factory;
    }

    static List<String> paidStream(XMLInputFactory factory)
            throws XMLStreamException {
        XMLStreamReader raw =
                factory.createXMLStreamReader(new StringReader(XML));
        StreamFilter onlyPaid = reader ->
                reader.getEventType() == XMLStreamConstants.START_ELEMENT
                && ORDER.equals(reader.getName())
                && "paid".equals(reader.getAttributeValue("", "status"));
        XMLStreamReader filtered =
                factory.createFilteredReader(raw, onlyPaid);
        try {
            List<String> ids = new ArrayList<>();
            boolean onAcceptedStart = filtered.getEventType()
                    == XMLStreamConstants.START_ELEMENT;
            System.out.println("StreamFilter initial accepted event: "
                    + onAcceptedStart);
            if (onAcceptedStart) {
                ids.add(filtered.getAttributeValue("", "id"));
            }
            while (filtered.hasNext()) {
                if (filtered.next() == XMLStreamConstants.START_ELEMENT) {
                    ids.add(filtered.getAttributeValue("", "id"));
                }
            }
            return ids;
        } finally {
            filtered.close();
        }
    }

    static List<String> paidEvents(XMLInputFactory factory)
            throws XMLStreamException {
        XMLEventReader raw =
                factory.createXMLEventReader(new StringReader(XML));
        EventFilter onlyPaid = event -> {
            if (!event.isStartElement()) return false;
            StartElement start = event.asStartElement();
            if (!ORDER.equals(start.getName())) return false;
            Attribute status = start.getAttributeByName(STATUS);
            return status != null && "paid".equals(status.getValue());
        };
        XMLEventReader filtered =
                factory.createFilteredReader(raw, onlyPaid);
        try {
            XMLEvent first = filtered.peek();
            Attribute firstId =
                    first.asStartElement().getAttributeByName(ID);
            System.out.println("EventFilter peek first: "
                    + firstId.getValue());
            List<String> ids = new ArrayList<>();
            while (filtered.hasNext()) {
                XMLEvent event = filtered.nextEvent();
                ids.add(event.asStartElement()
                        .getAttributeByName(ID).getValue());
            }
            System.out.println("EventFilter peek non-consuming: "
                    + (ids.size() == 2 && "A".equals(ids.get(0))));
            return ids;
        } finally {
            filtered.close();
        }
    }

    static int[] streamStructural(XMLInputFactory factory)
            throws XMLStreamException {
        XMLStreamReader raw =
                factory.createXMLStreamReader(new StringReader(XML));
        StreamFilter keepStructure = reader -> {
            int type = reader.getEventType();
            return type != XMLStreamConstants.COMMENT
                    && type != XMLStreamConstants.SPACE
                    && !(type == XMLStreamConstants.CHARACTERS
                         && reader.isWhiteSpace());
        };
        XMLStreamReader filtered =
                factory.createFilteredReader(raw, keepStructure);
        try {
            int start = 0;
            int end = 0;
            int comment = 0;
            if (filtered.getEventType() == XMLStreamConstants.START_ELEMENT)
                start++;
            if (filtered.getEventType() == XMLStreamConstants.END_ELEMENT)
                end++;
            while (filtered.hasNext()) {
                int type = filtered.next();
                if (type == XMLStreamConstants.START_ELEMENT) start++;
                if (type == XMLStreamConstants.END_ELEMENT) end++;
                if (type == XMLStreamConstants.COMMENT) comment++;
            }
            return new int[] {start, end, comment};
        } finally {
            filtered.close();
        }
    }

    static int[] eventStructural(XMLInputFactory factory)
            throws XMLStreamException {
        XMLEventReader raw =
                factory.createXMLEventReader(new StringReader(XML));
        EventFilter keepStructure = event ->
                event.getEventType() != XMLStreamConstants.COMMENT
                && !(event.isCharacters()
                     && event.asCharacters().isWhiteSpace());
        XMLEventReader filtered =
                factory.createFilteredReader(raw, keepStructure);
        try {
            int start = 0;
            int end = 0;
            int comment = 0;
            while (filtered.hasNext()) {
                XMLEvent event = filtered.nextEvent();
                if (event.isStartElement()) start++;
                if (event.isEndElement()) end++;
                if (event.getEventType() == XMLStreamConstants.COMMENT)
                    comment++;
            }
            return new int[] {start, end, comment};
        } finally {
            filtered.close();
        }
    }

    static List<String> paidAmounts(XMLInputFactory factory)
            throws XMLStreamException {
        XMLStreamReader reader =
                factory.createXMLStreamReader(new StringReader(XML));
        try {
            List<String> records = new ArrayList<>();
            String currentId = null;
            while (reader.hasNext()) {
                int type = reader.next();
                if (type == XMLStreamConstants.START_ELEMENT) {
                    if (ORDER.equals(reader.getName())) {
                        currentId = "paid".equals(
                                reader.getAttributeValue("", "status"))
                                ? reader.getAttributeValue("", "id")
                                : null;
                    } else if (AMOUNT.equals(reader.getName())
                            && currentId != null) {
                        records.add(currentId + "="
                                + reader.getElementText());
                    }
                } else if (type == XMLStreamConstants.END_ELEMENT
                        && ORDER.equals(reader.getName())) {
                    currentId = null;
                }
            }
            return records;
        } finally {
            reader.close();
        }
    }

    public static void main(String[] args) throws Exception {
        XMLInputFactory factory = secureFactory();
        List<String> streamIds = paidStream(factory);
        List<String> eventIds = paidEvents(factory);
        System.out.println("StreamFilter paid IDs: " + streamIds);
        System.out.println("EventFilter paid IDs: " + eventIds);
        System.out.println("Filters agree: " + streamIds.equals(eventIds));
        int[] cursor = streamStructural(factory);
        int[] event = eventStructural(factory);
        System.out.println("Cursor structural START/END/COMMENT: "
                + cursor[0] + "/" + cursor[1] + "/" + cursor[2]);
        System.out.println("Event structural START/END/COMMENT: "
                + event[0] + "/" + event[1] + "/" + event[2]);
        System.out.println("Unfiltered paid amount data: "
                + paidAmounts(factory));
        System.out.println("Foreign namespace ignored: "
                + !streamIds.contains("X"));
    }
}
~~~

### 9.3. Biên dịch và chạy

Lưu source vào file **`StaxFilterDemo.java`** (khớp public class), rồi chạy:

~~~sh
javac --release 17 StaxFilterDemo.java
java StaxFilterDemo
~~~

Chỉ cần JDK 17+; `javax.xml.stream` là Java SE API thuộc module `java.xml`. Không cần Maven, Gradle, JDBC driver hoặc database.

**Stdout chính xác**, đã biên dịch với `javac --release 17` và chạy trên JDK 24:

~~~text
StreamFilter initial accepted event: true
EventFilter peek first: A
EventFilter peek non-consuming: true
StreamFilter paid IDs: [A, C]
EventFilter paid IDs: [A, C]
Filters agree: true
Cursor structural START/END/COMMENT: 9/9/0
Event structural START/END/COMMENT: 9/9/0
Unfiltered paid amount data: [A=150, C=300]
Foreign namespace ignored: true
~~~

Dòng `StreamFilter initial accepted event: true` mô tả **implementation đã kiểm thử trên JDK 24**, không nên coi đây là invariant cho mọi provider. Source xử lý trường hợp current event START_ELEMENT và các events ở những lần `next()` sau; vì thế A không bị mất.

### 9.4. Giải thích từng kết quả

**`[A, C]` ở hai phương pháp:** A và C vừa thuộc `urn:demo:orders`, vừa có status `paid`. B bị loại vì `pending`. X bị loại vì thuộc `urn:demo:other`, dù cùng local name `order` và cũng `paid`.

**`EventFilter peek first: A`:** trước khi consume, peek nhìn thấy start event A. Vòng lặp `nextEvent()` vẫn bắt đầu từ A, chứng minh peek không tiêu thụ.

**`9/9/0`:** nguồn XML có chín start element và chín end element; structural filter giữ đủ pairs và bỏ `COMMENT`. Số lượng được kiểm bằng consumer trên filtered output, không bằng side effects bên trong `accept()`.

**`[A=150, C=300]`:** method `paidAmounts` không dùng start-only filtered reader. Nó theo dõi `currentId` khi gặp đúng `ORDER` và chỉ gọi `getElementText()` ở phần tử `AMOUNT` thuộc một order đã thanh toán.

**Không có claim về streaming memory tuyệt đối:** ví dụ dùng `StringReader` và lưu IDs vào `List` vì tài liệu ngắn. Trong hệ thống thật, XML bytes có thể đi qua `InputStream` và consumer có thể ghi kết quả ra downstream ngay thay vì giữ tất cả trong List.

### 9.5. Tại sao không đọc `amount` từ filtered reader chỉ giữ order starts?

Vì filtered cursor chỉ có các start events của A và C; events của `<amount>`, `CHARACTERS 150/300` và các end tags đã bị bỏ. `getElementText()` yêu cầu trình tự events hợp lệ cho nội dung của một element. Không nên gọi nó sau khi loại mất toàn bộ child text/end events.

Nếu cần dữ liệu **của từng subtree**, phương án tốt là dùng **unfiltered cursor** với state/depth, hoặc filter chỉ bỏ những events thật sự không ảnh hưởng cấu trúc và nội dung cần giữ.

## 10. Trích xuất dữ liệu có cấu trúc thay vì chỉ lọc sự kiện

Trong `paidAmounts()` của ví dụ:

~~~java
String currentId = null;

while (reader.hasNext()) {
    int type = reader.next();
    if (type == XMLStreamConstants.START_ELEMENT) {
        if (ORDER.equals(reader.getName())) {
            currentId = "paid".equals(
                    reader.getAttributeValue("", "status"))
                    ? reader.getAttributeValue("", "id")
                    : null;
        } else if (AMOUNT.equals(reader.getName())
                && currentId != null) {
            records.add(currentId + "="
                    + reader.getElementText());
        }
    } else if (type == XMLStreamConstants.END_ELEMENT
            && ORDER.equals(reader.getName())) {
        currentId = null;
    }
}
~~~

Đây là **đoạn trích method**, dùng biến `records`, `reader`, `ORDER`, `AMOUNT` đã khai báo trong file hoàn chỉnh. Nó phù hợp với schema ví dụ: `order` không lồng bên trong `order`, và `amount` là child text-only. Đừng tái sử dụng nguyên trạng cho XML có orders lồng nhau hoặc `amount` ở vị trí bất kỳ; khi ấy cần depth tracking và stack biểu diễn parent/child.

### 10.1. Lọc subtree đúng cần theo dõi độ sâu

Khi bắt đầu một `<order>` phù hợp:

~~~text
START order selected          depth = 1
  START customer              depth = 2
    CHARACTERS...             giữ
  END customer                depth = 1
  START amount                depth = 2
    CHARACTERS...             giữ
  END amount                  depth = 1
END order                     depth = 0, hoàn tất subtree
~~~

Khi chưa ở trong selected subtree, bỏ qua việc **lưu dữ liệu** nhưng vẫn tiến parser và phân tích start/end để biết đang ở đâu. Nếu cần copy thành XML fragment:

- Bắt đầu ghi với START_ELEMENT của root được chọn.
- Copy đủ mọi START_ELEMENT/END_ELEMENT/CHARACTERS/CDATA có ý nghĩa bên trong.
- Copy các attributes/namespace declarations cần thiết cho output well-formed.
- Khi root selected có prefix được khai báo **trên ancestor không được copy**, phải khai báo binding ấy lại trên fragment root.
- Không serialize các sự kiện bằng cách ghép chuỗi thủ công mà bỏ escaping.
- Đóng output writer đúng scope và giới hạn kích thước fragment.

**Đặc biệt:** một start-event-only EventFilter không tự thu thập hoặc copy các descendants như vậy.

### 10.2. Tránh giữ toàn bộ XML trong RAM

Dù StAX là streaming-oriented, đoạn code như `List<String> ids` vẫn gom kết quả vào RAM. Nếu XML có hàng triệu records:

- Xử lý mỗi accepted event khi đến, ghi vào batch/output với giới hạn.
- Không tạo một `StringBuilder` toàn document trừ khi nghiệp vụ yêu cầu.
- Đặt max records, max characters, max attributes, max depth, size/time limits.
- Áp backpressure và cancellation khi downstream chậm.
- Giữ nguồn `InputStream` mở tới khi cursor/event reader đã tiêu thụ xong.
- Nếu cần trạng thái parent-child, dùng stack hoặc counter nhỏ, không dựng DOM toàn bộ.

Filtered reader có thể giảm lượng **sự kiện được ứng dụng xử lý**, nhưng không bảo đảm parser không allocate hay không đọc các phần bị bỏ. Với tài liệu lớn, benchmark trên runtime/provider thật.

## 11. Vòng đời tài nguyên: wrapper, parser và source

Một XML pipeline có ít nhất:

~~~text
File/InputStream/Reader
       |
       v
raw XMLStreamReader hoặc XMLEventReader
       |
       v
filtered reader
       |
       v
application consumer
~~~

Filter không tự đóng input. Khi dùng nguồn file thật:

~~~java
try (Reader source = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {

    XMLStreamReader raw =
            factory.createXMLStreamReader(source);
    XMLStreamReader filtered =
            factory.createFilteredReader(raw, filter);

    try {
        while (filtered.hasNext()) {
            filtered.next();
            // Consume accepted events.
        }
    } finally {
        filtered.close();
    }
}
~~~

Đây là snippet với `path`, `factory`, `filter` đã có; cần imports `java.io.Reader`, `java.nio.file.Files`, `java.nio.charset.StandardCharsets`. Nếu dùng filtered reader, tránh tiến `raw` độc lập sau khi đã wrap. **Đóng wrapper và đóng Reader source theo ownership**; việc `XMLStreamReader.close()` không nhất thiết đóng underlying Java `Reader`.

`XMLStreamReader` và `XMLEventReader` trên Java 17 **có method `close()` nhưng không implement `AutoCloseable`**. Do đó đừng đặt trực tiếp chúng trong `try-with-resources` khi build `--release 17`. Dùng `try/finally` cho StAX reader và `try-with-resources` cho `Reader/InputStream` bên dưới.

Có thể một provider đóng cả underlying raw reader khi wrapper.close, hoặc yêu cầu lifecycle management riêng; không mượn lại raw reader sau khi wrapper đã hoàn tất. Nếu bạn xây custom wrapper, cần document rõ ai sở hữu raw reader để tránh đóng hai lần hoặc leak.

### 11.1. Vì sao input encoding quan trọng?

`StringReader` nhận ký tự Java đã được giải mã. Với `InputStream` bytes XML, parser phải xử lý XML declaration/encoding theo XML rules. Không lấy bytes UTF-8 rồi giải mã bằng platform-default charset trước khi đưa cho StringReader khi document đã khai encoding khác.

Đối với XML từ bên ngoài, tạo `InputStream` từ nguồn có timeout/size limit. Với file rất lớn, không nên đọc toàn bộ thành `String` chỉ để lọc vài events; đưa stream trực tiếp vào XMLInputFactory nếu phù hợp.

## 12. Bảo mật: filter không ngăn XXE, DTD hay XML bomb

Một `StreamFilter` chỉ accept order elements **không có nghĩa** các parts khác được bỏ qua trước khi XML parser xử lý chúng. Nếu XML có DTD/external entities hoặc kích thước lớn, parser vẫn phải diễn giải tài liệu để phát events.

Với XML không tin cậy:

~~~java
XMLInputFactory factory = XMLInputFactory.newFactory();
factory.setProperty(XMLInputFactory.IS_NAMESPACE_AWARE, true);
factory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
factory.setProperty(
        XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
factory.setXMLResolver((publicId, systemId, baseUri, namespace) -> {
    throw new XMLStreamException("External XML resource forbidden");
});
~~~

Đây là snippet; cấu hình được dùng trong chương trình đầy đủ. Java 17+ còn có các JAXP external-access properties, ví dụ `XMLConstants.ACCESS_EXTERNAL_DTD` khi provider hỗ trợ. Không bỏ qua `IllegalArgumentException` khi một policy bắt buộc không thể được đặt.

Ngoài cấu hình:

- Chặn hoặc kiểm soát DTD và external entity resolution.
- Giới hạn tổng bytes/characters input trước và trong parse.
- Giới hạn XML depth, số lượng attributes, text lengths, document events.
- Có timeout/cancellation cho việc đọc source và xử lý business data.
- Tránh gửi dữ liệu nhạy cảm trong messages/log của `XMLStreamException` hoặc ghi nguyên văn XML không tin cậy.
- Test payloads XXE/entity expansion theo **đúng provider và cấu hình** sẽ chạy production; fail closed nếu không thể đảm bảo policy.

**Lưu ý chính xác:** `SUPPORT_DTD=false` là yêu cầu parser không hỗ trợ DTD trong quá trình xử lý, nhưng không nên diễn giải thành quy tắc mọi provider bắt buộc ném lỗi trên mọi `DOCTYPE`. Nếu ứng dụng cần **từ chối hoàn toàn mọi DOCTYPE**, phải bổ sung kiểm tra/layer theo contract nhà cung cấp và test fail-closed.

## 13. Chọn StreamFilter hay EventFilter trong thiết kế ứng dụng?

### 13.1. Chọn StreamFilter khi

- Đã có code xử lý `XMLStreamReader` theo cursor API.
- Predicate đơn giản: event type, `QName`, một vài attributes.
- Muốn giảm số event callbacks ở consumer.
- Cần truy cập properties của reader hiện tại mà không tạo event object rõ trong code.

Cần kiểm soát **current cursor state** sau khi tạo wrapper và tránh gọi `next()` bên trong `accept(...)`. Khi cần parent/child, dùng application state bên ngoài filter hoặc plain reader.

### 13.2. Chọn EventFilter khi

- Pipeline dùng `XMLEventReader`/`XMLEventWriter` và event objects.
- Cần `peek()` để xem event kế tiếp mà chưa tiêu thụ.
- Dùng `StartElement.getName` và `Attribute` thuận tiện.
- Muốn chuyển các sự kiện độc lập giữa nhiều lớp xử lý.

Cần nhớ event objects vẫn là **đơn vị riêng lẻ**, không phải subtree. Nếu filter bỏ một số END_ELEMENT hoặc START_ELEMENT, output có thể không còn là document hợp lệ để writer khác serialize lại.

### 13.3. Khi nào không nên dùng filter wrapper?

Không nên dùng khi:

- Cần trích **toàn subtree** và mọi text/attributes theo quan hệ cha–con.
- XML có mixed content/whitespace mang ý nghĩa.
- Logic lọc phụ thuộc **state phức tạp giữa nhiều events** (cần stack/depth/validation).
- Muốn rewrite/copy XML thành một document hợp lệ.
- Muốn schema validation, XSD, signature verification hoặc XML canonicalization.
- Muốn loại DTD/XXE trước parse (filter chạy quá muộn).

Trong các trường hợp ấy, dùng unfiltered reader kết hợp state machine, SAX/StAX handler, validator hoặc XML transform/stream writer phù hợp. Filter wrapper là công cụ **chọn sự kiện**, không phải giải pháp cho mọi bước XML processing.

## 14. Nhìn rõ sự khác nhau giữa `peek()`, `nextEvent()` và `next()`

| API | Reader | Ý nghĩa |
| --- | --- | --- |
| `XMLStreamReader.getEventType()` | Cursor | Đọc trạng thái hiện tại, không tiến |
| `XMLStreamReader.next()` | Cursor | Tiến tới event tiếp theo, trả mã int |
| `XMLStreamReader.hasNext()` | Cursor | Có event tiếp theo không (có thể throws XMLStreamException) |
| `XMLEventReader.peek()` | Event | Xem event tiếp theo mà không consume, trả `XMLEvent` hoặc null |
| `XMLEventReader.nextEvent()` | Event | Consume và trả event kế tiếp, có checked `XMLStreamException` |
| `XMLEventReader.hasNext()` | Event | Có event tiếp theo không |
| `XMLEventReader.nextTag()` | Event | Skip một số loại events để tới start/end tag theo API preconditions |

Sự khác nhau ảnh hưởng trực tiếp đến filtering. **Đừng bê vòng lặp cursor sang event reader mà không đổi cách xử lý first/current event.**

### 14.1. Khi filter bỏ hết events

Một filter như:

~~~java
EventFilter none = event -> false;
~~~

khi wrapped reader không có event được accept, consumer phải **xử lý trường hợp kết quả rỗng**. `peek()` có thể trả null; `hasNext()` có thể false. Không gọi vô điều kiện `peek().asStartElement()` hoặc `nextEvent()` nếu chưa có event phù hợp. Mọi code production nên dùng null check và boundary tests.

Bản demo biết chắc A tồn tại nên mới gọi `first.asStartElement()` sau `peek()`; đừng copy giả định ấy vào code nhận XML tùy ý.

### 14.2. Filter không thay cho XPath

Một predicate `ORDER.equals(start.getName())` chỉ nhìn event hiện tại và một số thuộc tính, không trực tiếp biểu đạt XPath như “`/orders/order[status='paid']/amount`” có điều kiện trên children. Nếu yêu cầu phụ thuộc sibling/ancestor/descendant, parser cần state hoặc dùng XPath với engine/giới hạn hiệu năng thích hợp.

## 15. Những tình huống khó: CDATA, comments, whitespace, entities

### 15.1. Whitespace có thể có nghĩa

Với:

~~~xml
<p>Hello <em>world</em> !</p>
~~~

khoảng trắng trước/sau `<em>` có thể mang ý nghĩa hiển thị. Filter loại `CHARACTERS` chỉ chứa whitespace có thể biến đổi văn bản mà consumer đọc được, nhất là XML dạng narrative/document.

Ngược lại, với XML dữ liệu cấu trúc:

~~~xml
<orders>
  <order id="A"/>
  <order id="B"/>
</orders>
~~~

các newline/thụt lề có thể chỉ là formatting. Nhưng hãy dựa vào vocabulary/schema và `xml:space` thay vì một giả định toàn cục.

### 15.2. CDATA là data, không phải comment

CDATA:

~~~xml
<message><![CDATA[<b>không phải tag thật</b>]]></message>
~~~

là character content. Tùy `XMLInputFactory.IS_COALESCING` và provider, data có thể được báo bằng `CHARACTERS`/`CDATA` events hoặc được gộp. Nếu filter chỉ giữ duy nhất `CHARACTERS` mà không xét `CDATA` và coalescing, bạn có thể bỏ mất nội dung.

Filter có mục tiêu “chỉ lấy text” nên căn cứ trên `reader.isCharacters()`/`XMLEvent.isCharacters()`, cùng hiểu biết về CDATA và parser features, thay vì hardcode duy nhất một integer constant rồi cho rằng toàn bộ text đều đã được lấy.

### 15.3. Comments và processing instructions

`COMMENT` không phải element data trong nhiều tài liệu nghiệp vụ, nhưng có XML tools sử dụng comment cho chú giải. `PROCESSING_INSTRUCTION` có thể mang thông tin điều khiển theo vocabulary. **Chỉ loại nếu schema và yêu cầu ứng dụng cho phép.**

### 15.4. Entity references và DTD

Nếu parser xử lý entity references, các `ENTITY_REFERENCE` events hoặc character replacements phụ thuộc parser settings. Tuy nhiên **không bật external entity resolution chỉ để filter dễ hơn**. Bảo vệ XXE/DTD luôn được cấu hình **trước khi tạo raw reader**, không sau khi event đã được parse.

## 16. Tính đúng đắn: không nhầm event acceptance với business result

Một record XML có thể chứa:

~~~xml
<order id="A" status="paid">
  <amount currency="USD">150</amount>
  <refund>20</refund>
</order>
~~~

Filter chỉ nhìn `status="paid"` sẽ chọn start event của order A. Nhưng **kết quả nghiệp vụ đúng** còn phụ thuộc amount, refund, currency, chữ ký, schema, ID uniqueness và các rules khác.

Vì vậy:

1. Filter đơn giản để thu hẹp events mục tiêu.
2. Consumer kiểm tra các thuộc tính/children cần thiết.
3. Validate types, ranges, required fields, duplicate IDs và structural constraints.
4. Chỉ khi record hợp lệ mới cập nhật trạng thái business.
5. Nếu có writes tới database/queue, dùng transaction/idempotency phù hợp.

Đừng để predicate `accept(...)` tự ghi database hoặc gọi API bên ngoài. Provider có thể gọi predicate nhiều lần/lookahead; một side effect như trừ tiền trong `accept()` có thể bị lặp.

## 17. Độ phức tạp và hiệu năng

Một bộ lọc StAX không tự biến một document có N events thành công việc O(K) ở parser khi chỉ K events được accept. **Để biết event nào match, underlying parser vẫn phải đọc qua các sự kiện khác**. Phức tạp duyệt XML thường vẫn gắn với kích thước input, dù consumer xử lý ít events hơn.

Các tối ưu thực tế:

- Đặt predicate rẻ trước, ví dụ kiểm tra event type trước `QName`, rồi mới đọc attribute.
- Dùng hằng `QName` được tạo một lần, không tạo mới cho mỗi element.
- Tránh regex/string allocation trong `accept(...)`.
- Tránh giữ toàn bộ event objects khi chỉ cần một số trường scalar.
- Không dùng predicate có side effects hoặc state phụ thuộc số lần gọi.
- Cân nhắc cursor API nếu không cần event objects; benchmark trên JDK/provider thực.
- Nếu muốn parse sớm ngừng khi đã đủ K records, consumer có thể dừng, **đóng reader/source đúng cách**, và chỉ làm thế nếu nghiệp vụ không yêu cầu validate toàn bộ XML.
- Đối với XML không tin cậy, cần đọc/validate toàn bộ hoặc fail closed theo security requirements; dừng parse sớm có thể bỏ qua dữ liệu sai nằm cuối document.

Không tuyên bố một filter luôn nhanh hơn việc dùng unfiltered cursor + `if`. Thêm wrapper có thể mang overhead; lựa chọn dựa trên readability và profiling.

## 18. Kiểm thử cần có trước khi áp dụng production

| Test | Tình huống | Kỳ vọng |
| --- | --- | --- |
| StreamFilter chọn đúng start | `order status=paid` | Chỉ nhận record phù hợp |
| EventFilter chọn đúng start | Cùng XML | Cùng IDs với cursor |
| Initial cursor accepted | JDK provider đặt cursor ở first match | Không mất phần tử đầu |
| EventReader peek | Gọi peek trước nextEvent | Peek không tiêu thụ |
| Prefix rewrite | Đổi alias namespace | Kết quả không đổi |
| Namespace collision | `other:order` cũng `paid` | Không bị chọn |
| Attribute no-namespace | `status` không prefix | Lookup đúng QName/no-ns |
| Missing status | `<order id="A"/>` | Không bị NullPointerException |
| Comment và indentation | XML có COMMENT/SPACE | Structural filter loại nếu policy cho phép |
| Whitespace meaningful | Mixed content | Không loại bừa |
| CDATA | Nội dung CDATA | Không mất text có nghĩa |
| Entity refs/DTD | External entities | Security policy chặn |
| Missing matches | Chỉ pending orders | Filtered reader cho kết quả rỗng an toàn |
| Malformed XML | Mất end tag | `XMLStreamException`, cleanup |
| Subtree extraction | Nested children | Depth tracking giữ đúng parent/content |
| START/END balance | Structural filter | Event pairs còn cân bằng |
| Filter creates side effects | `accept` có logging/mutation | Bỏ pattern; chỉ làm trong consumer |
| Large input | Nhiều MB | Có size/depth/time budget |
| Canceled/partial parse | Ngừng giữa chừng | Đóng parser/source |
| Provider compatibility | JDK built-in và provider khác | Recheck initial state/peek/whitespace/coalescing |
| Java 17 | `javac --release 17` | Toàn bộ API dùng được; close trong finally |

Đừng dùng một XML sample có duy nhất một phần tử được chọn rồi tin rằng pipeline đúng. Test ít nhất **hai accepted records** để phát hiện lỗi bỏ sự kiện đầu, thêm foreign namespace và có both accepted/rejected statuses.

## 19. Lỗi phổ biến và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ `while(hasNext){next();...}` với filtered cursor | Có thể bỏ event đầu đã accepted | Kiểm tra `getEventType()` ngay sau wrap |
| Dùng `StreamFilter.accept` để gọi `next()` | Cursor bị phá trạng thái | Predicate chỉ đọc current event |
| Tăng business counter trong `accept` | Đếm sai do lookahead/lời gọi lặp | Đếm ở consumer khi consume |
| So prefix `o` thay QName | Đổi prefix sẽ bỏ match | So URI + local part |
| Chỉ so local `order` | Lẫn foreign vocabulary | So expanded QName |
| `getAttributeValue(null,"status")` hiểu là no-ns | Null là wildcard | Dùng `""` hoặc QName |
| `EventFilter` START_ONLY rồi gọi `getElementText` | Mất CHARACTERS/END_ELEMENT | Dùng unfiltered/stateful parser |
| Tưởng filter chọn root tự lấy toàn children | Mất subtree | Depth tracking/copy events cân bằng |
| Bỏ mọi whitespace trong XML có mixed content | Nội dung thay đổi | Giữ whitespace theo schema |
| Bỏ mọi CDATA vì type khác CHARACTERS | Mất text | Xét `isCharacters` và parser settings |
| Mặc định `peek()` luôn non-null | NPE khi không có match | Kiểm tra null/hasNext |
| Không đóng StAX reader | Rò parser resources | `close()` trong finally |
| Nghĩ StAX reader Java17 AutoCloseable | Không compile try-with-resources | Dùng finally cho StAX reader |
| Nghĩ close parser tự đóng Java Reader | Có thể leak input | Đóng source ở scope riêng |
| Dùng XMLInputFactory mặc định cho untrusted XML | XXE/DTD/memory risks | Harden trước parse, resource limits |
| Nghĩ filter từ chối event sẽ ngăn parser đọc dữ liệu đó | Security/CPU assumptions sai | Lọc là consumer-level, không phải byte firewall |
| Ghi accepted starts vào XMLEventWriter để tạo XML | Output không cân bằng | Copy full selected subtrees + namespaces |
| Hardcode XML attributes không validate | Business data sai | Schema/range/required-field validation |
| So XML raw string để kiểm tra equivalence | Prefix/namespace/serialization khác | Validate XML structure/expanded names |
| Dùng source Reader đã tiêu thụ cho hai parser | Parser thứ hai không còn dữ liệu | Tạo Reader mới/đọc lại input |
| Bỏ qua `XMLStreamException` | Che malformed XML | Propagate/log với location đã redacted |

## 20. Câu hỏi tự kiểm tra

**Câu 1.** `StreamFilter` nhận gì và trả gì?

**Trả lời:** Một `XMLStreamReader` đang ở event hiện tại; `accept` trả boolean quyết định event đó có được đưa ra từ filtered cursor reader hay không.

**Câu 2.** `EventFilter` nhận gì?

**Trả lời:** Một đối tượng `XMLEvent`; `accept` trả true/false. Wrapper là filtered `XMLEventReader`.

**Câu 3.** Hai overload của `XMLInputFactory.createFilteredReader` khác nhau ở đâu?

**Trả lời:** `XMLStreamReader + StreamFilter -> XMLStreamReader`; `XMLEventReader + EventFilter -> XMLEventReader`.

**Câu 4.** Vì sao không được gọi `reader.next()` trong `StreamFilter.accept`?

**Trả lời:** Predicate chỉ được kiểm tra event hiện tại. Tự tiến cursor thay đổi trạng thái của parser/wrapper, gây skip và sai semantics.

**Câu 5.** Vì sao phải kiểm tra `filtered.getEventType()` ngay sau khi wrap cursor?

**Trả lời:** Một implementation có thể đã định vị cursor ở first accepted event. Nếu gọi `next()` ngay sẽ bỏ qua event đó. Chương trình đã kiểm thử trường hợp này trên JDK24.

**Câu 6.** `peek()` của XMLEventReader có tiêu thụ event không?

**Trả lời:** Không. `nextEvent()` sau đó vẫn nhận event đã peek, nếu không có consumer khác làm thay đổi reader.

**Câu 7.** Một EventFilter chỉ nhận `StartElement` của order A có trích cả subtree A không?

**Trả lời:** Không. Nó chỉ nhận start event đó, không tự nhận descendants, text hoặc end tags.

**Câu 8.** Vì sao `other:order status="paid"` không được nhận bởi filter QName order?

**Trả lời:** Vì namespace URI khác dù cùng local name `order` và cùng status. `QName.equals` xét URI + local part.

**Câu 9.** Có nên dùng `getElementText()` sau start-only filtered reader?

**Trả lời:** Không. Các text/end events cần cho method có thể đã bị filter ẩn; dùng unfiltered parser hoặc filter giữ cấu trúc và text.

**Câu 10.** `StreamFilter` có thay XML Schema validation không?

**Trả lời:** Không. Nó lọc sự kiện do parser tạo; không kiểm chứng toàn bộ schema/quan hệ cha–con hay business constraints.

**Câu 11.** Tại sao cần phân biệt comment với CDATA?

**Trả lời:** Comment thường là metadata có thể bỏ theo yêu cầu; CDATA chứa dữ liệu ký tự có nghĩa. Không dùng một whitelist quá hẹp gây mất text.

**Câu 12.** Vì sao không đếm số lần `accept` được gọi?

**Trả lời:** Provider có thể dùng predicate khi tìm first accepted event hoặc lookahead ở hasNext/peek, nên số lần accept không tương đương số event tiêu thụ.

**Câu 13.** Khi nào được loại whitespace-only events?

**Trả lời:** Khi vocabulary/schema xác nhận đó là formatting không mang ý nghĩa. Với mixed content hoặc `xml:space`, whitespace có thể là data và phải giữ.

**Câu 14.** `XMLStreamReader` có dùng try-with-resources trực tiếp trên Java17 không?

**Trả lời:** Không. Interface có `close()` nhưng chưa implement `AutoCloseable` ở Java17; dùng `finally` và quản lý Reader/InputStream nguồn riêng.

**Câu 15.** Filter chỉ chọn vài events có ngăn XXE hoặc giúp parse đầu vào không cần đọc hết các bytes bị bỏ không?

**Trả lời:** Không. Parser xử lý input trước khi filter quyết định visibility; phải harden XMLInputFactory, deny external resolver và đặt resource limits.

**Câu 16.** Khi nào dùng plain cursor có depth tracking?

**Trả lời:** Khi cần giữ toàn bộ subtree, quan hệ cha–con, nested elements, hoặc trích nhiều fields của một record. Một start-only EventFilter không đủ.

**Câu 17.** Tại sao Structural filter giữ đủ START_ELEMENT và END_ELEMENT?

**Trả lời:** Vì các consumers/writers cần cặp open/close để hiểu cây XML; bỏ một phía có thể tạo event stream không còn well-formed.

**Câu 18.** Làm gì khi filtered EventReader không có events accepted?

**Trả lời:** Kiểm tra `peek()==null`/`hasNext()==false` trước khi dùng nextEvent/asStartElement; xem đây là kết quả rỗng hợp lệ nếu nghiệp vụ cho phép.

**Ghi nhớ:** `StreamFilter` và `EventFilter` đều là **bộ lọc sự kiện StAX**. Sử dụng `StreamFilter` khi đã có `XMLStreamReader`, và `EventFilter` khi dùng `XMLEventReader`. Filter không tự sao chép subtree hay thay parser validation. Với cursor filter, **kiểm tra current event ngay sau khi tạo wrapper** để không bỏ first accepted event. Với event filter, `peek` nhìn trước nhưng không tiêu thụ. Hãy so `QName(namespace URI, local part)`, giữ cấu trúc START/END và text cần thiết, tránh side effects trong `accept`, và bảo vệ XMLInputFactory trước khi đọc input không tin cậy.

### Tài liệu chính thức hiện hành

- [Oracle Java SE 26 — XMLInputFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLInputFactory.html): cả hai overload `createFilteredReader`, cấu hình parser.
- [Oracle Java SE 26 — StreamFilter](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/StreamFilter.html): `accept(XMLStreamReader)`.
- [Oracle Java SE 26 — EventFilter](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/EventFilter.html): `accept(XMLEvent)`.
- [Oracle Java SE 26 — XMLStreamReader](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLStreamReader.html): cursor methods, event state, `getElementText`, `nextTag`.
- [Oracle Java SE 26 — XMLEventReader](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLEventReader.html): `peek`, `nextEvent`, `close`.
- [Oracle Java SE 26 — StartElement](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/events/StartElement.html): `getName`, `getAttributeByName`.
- [Oracle Java SE 26 — QName](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/namespace/QName.html): so expanded names.
- [OWASP — XML External Entity Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html): chặn XXE và cấu hình StAX an toàn.
