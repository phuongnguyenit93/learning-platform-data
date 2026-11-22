# Namespace, QName và phân biệt local name với prefix trong StAX

## 1. Bài toán: cùng một tên XML nhưng không nhất thiết cùng ý nghĩa

Khi xử lý XML bằng StAX, một ứng dụng Java có thể nhận các tài liệu từ nhiều nhà cung cấp. Cùng một phần tử logic có thể được viết bằng hai prefix khác nhau:

~~~xml
<a:item xmlns:a="urn:example:order"/>
~~~

~~~xml
<b:item xmlns:b="urn:example:order"/>
~~~

Hai phần tử này **cùng định danh XML theo namespace**, dù tên hiển thị khác nhau. Ngược lại:

~~~xml
<p:item xmlns:p="urn:example:order"/>
~~~

~~~xml
<p:item xmlns:p="urn:example:inventory"/>
~~~

Hai phần tử dùng **cùng prefix** `p` và cùng local name `item`, nhưng mang **hai định danh khác nhau** vì URI của namespace khác nhau.

Đây là lý do chính của bài học:

> Trong XML namespace-aware, định danh phần tử/thuộc tính là **expanded name = (namespace URI, local name)**. Prefix chỉ là bí danh cú pháp, phụ thuộc tài liệu và phạm vi khai báo.

StAX, viết đầy đủ là *Streaming API for XML*, có các API hiện hành thuộc module `java.xml`:

- `javax.xml.stream.XMLInputFactory` tạo parser có khả năng nhận diện namespace.
- `javax.xml.stream.XMLStreamReader` đọc XML theo các sự kiện (cursor API).
- `javax.xml.namespace.QName` lưu namespace URI, local part và một prefix để giữ thông tin lexical.
- `javax.xml.namespace.NamespaceContext` tra prefix trong phạm vi hiện tại.
- `javax.xml.stream.XMLOutputFactory` và `XMLStreamWriter` ghi XML, bao gồm prefix/namespace bindings.
- `XMLEventReader`/`StartElement` là lựa chọn event-object API nếu thích lưu các sự kiện độc lập hơn với cursor.

Các API này còn dùng được trên **Java 17+**, không cần thư viện XML đời cũ. Bài viết đi từ khái niệm tới hai chương trình Java độc lập đã biên dịch và chạy trên JDK 24 với `javac --release 17`.

## 2. Bốn thuật ngữ bắt buộc phân biệt

| Thuật ngữ | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Prefix** | `o` trong `o:item` | Bí danh ngắn được khai báo bằng `xmlns:o="..."` |
| **Local name / local part** | `item` | Phần tên sau dấu `:`; nếu không có prefix, là toàn bộ tên lexical |
| **Namespace URI** | `urn:example:order` | Chuỗi nhận diện namespace, được prefix/default namespace trỏ tới |
| **Expanded name** | `{urn:example:order}item` | Cặp **(namespace URI, local part)**, dùng để phân biệt tên logic |

Khi viết:

~~~xml
<o:item xmlns:o="urn:example:order"/>
~~~

thì:

~~~text
Lexical QName:   o:item
Prefix:          o
Local name:      item
Namespace URI:   urn:example:order
Expanded name:   {urn:example:order}item
~~~

**Namespace URI là định danh, không nhất thiết là URL cần truy cập mạng.** Ví dụ `urn:example:order` không phải địa chỉ để tải XML schema. Một namespace có dạng HTTP URL vẫn không ngụ ý StAX phải tải nội dung tại URL đó khi nhận diện tên phần tử. Đừng dùng network call chỉ để kiểm tra XML element thuộc namespace nào.

W3C quy định namespace URI được so sánh như chuỗi URI reference theo quy tắc XML namespace (case-sensitive); không tự chuẩn hóa `http://...` với `https://...`, không tự thêm dấu `/` hoặc percent-decode. Hai URI nhìn có vẻ liên quan nhưng **khác string** vẫn là hai namespace khác nhau.

### 2.1. Prefix không phải danh tính của một schema

Trong tài liệu:

~~~xml
<inv:order xmlns:inv="urn:example:order">
  <inv:item/>
</inv:order>
~~~

`inv` là prefix tác giả tài liệu chọn. Tài liệu khác có thể viết:

~~~xml
<order xmlns="urn:example:order">
  <item/>
</order>
~~~

Hai phiên bản dùng cùng URI và cùng local names, nên các phần tử tương ứng có expanded name như nhau. Bộ đọc đúng namespace sẽ nhận ra điều này; code tìm tên bằng `reader.getPrefix().equals("inv")` lại có thể bỏ sót tài liệu thứ hai.

### 2.2. Local name một mình cũng không đủ

Nếu tài liệu chứa:

~~~xml
<root xmlns:x="urn:example:order"
      xmlns:y="urn:example:product">
  <x:item/>
  <y:item/>
</root>
~~~

cả hai cùng `getLocalName() == "item"`, nhưng khác nghiệp vụ. Cách chọn các phần tử "order item" phải kiểm tra **cả namespace URI và local name**, ví dụ `new QName("urn:example:order", "item")`.

## 3. Default namespace: vì sao tên không có prefix vẫn có namespace?

Với:

~~~xml
<order xmlns="urn:example:order">
  <item/>
</order>
~~~

cả `order` và `item` không có prefix lexical, nhưng đều thuộc `urn:example:order`. Khi StAX đọc phần tử `item`:

~~~text
reader.getLocalName()    -> item
reader.getNamespaceURI() -> urn:example:order
reader.getPrefix()       -> null hoặc "" tùy provider/API contract
reader.getName()         -> {urn:example:order}item
~~~

Giá trị prefix của element **không nhất thiết là một chuỗi không-null có ý nghĩa**; JavaDoc cho phép `getPrefix()` trả `null` khi không có prefix. Dùng so sánh null-safe nếu cần hiển thị prefix. **Không** suy luận "prefix trống = namespace trống".

### 3.1. Default namespace có phạm vi (scope)

Một khai báo `xmlns="..."` có hiệu lực từ start-tag của phần tử khai báo tới end-tag tương ứng, ngoại trừ phạm vi con có khai báo default namespace mới.

~~~xml
<root xmlns="urn:example:order">
  <item/>
  <other xmlns="urn:example:other">
    <item/>
  </other>
  <plain xmlns="">
    <item/>
  </plain>
</root>
~~~

Các `item` có expanded names khác nhau:

| Đường dẫn | Expanded name |
| --- | --- |
| `root/item` | `{urn:example:order}item` |
| `root/other/item` | `{urn:example:other}item` |
| `root/plain/item` | `{}item`, nghĩa là **không có namespace** |

`xmlns=""` đặt lại default namespace thành **không có namespace** cho các phần tử không prefix trong phạm vi ấy (theo XML Namespaces 1.0). Nó **không** xóa các prefix riêng đã được khai báo, ví dụ `xmlns:m` vẫn có thể tồn tại cho thuộc tính hoặc phần tử m-prefixed.

### 3.2. Quy tắc rất quan trọng: default namespace **không áp dụng** cho thuộc tính không prefix

Xem:

~~~xml
<order xmlns="urn:example:order"
       xmlns:m="urn:example:meta"
       id="R1"
       m:id="M1"/>
~~~

Ở đây có **hai thuộc tính cùng local name `id`** nhưng không trùng định danh:

| Thành phần | Prefix | Namespace URI | Local name |
| --- | --- | --- | --- |
| Element `order` | Không có | `urn:example:order` | `order` |
| Attribute `id` | Không có | **Không có** | `id` |
| Attribute `m:id` | `m` | `urn:example:meta` | `id` |

Điều này hợp lệ: hai thuộc tính chỉ bị coi trùng nếu expanded names của chúng trùng nhau. Ngược lại, viết `a:id` và `b:id` trên cùng start-tag khi `a` và `b` cùng URI **và cùng local name** tạo hai expanded names giống nhau, nên XML namespace-conforming sẽ không hợp lệ.

**Một lỗi rất phổ biến:** vì element nằm trong default namespace, code tưởng thuộc tính `id` cũng thuộc namespace ấy rồi tìm `new QName("urn:example:order", "id")`. Kết quả là không thấy thuộc tính.

## 4. Prefix có thể thay đổi ý nghĩa theo phạm vi

Prefix là một mapping **trong scope**, không phải từ khóa toàn cục bất biến:

~~~xml
<root xmlns:p="urn:one">
  <p:item/>
  <section xmlns:p="urn:two">
    <p:item/>
  </section>
  <p:item/>
</root>
~~~

Ở phần tử `p:item` đầu và cuối, `p` trỏ tới `urn:one`; trong `section` nó trỏ tới `urn:two`.

~~~text
item 1: {urn:one}item
item 2: {urn:two}item
item 3: {urn:one}item
~~~

Khi parser rời `section`, binding `p -> urn:two` hết hiệu lực và binding bên ngoài được khôi phục. **Không** giữ một `Map<String,String>` duy nhất từ root rồi áp cho toàn bộ document mà không xử lý namespace scope push/pop.

Một loại lỗi ngược lại: **hai prefix khác nhau cùng trỏ tới một URI**. Khi đó expanded names vẫn bằng nhau, và `QName.equals` theo Java cũng coi là bằng nhau.

### 4.1. Các prefix dành riêng

Theo XML Namespaces:

- `xml` được ràng buộc cố định với `http://www.w3.org/XML/1998/namespace`, dùng trong những thuộc tính chuẩn như `xml:lang`, `xml:space`.
- `xmlns` dành cho các khai báo namespace, không phải prefix người dùng tự dùng tùy ý cho tên phần tử.
- Không tự bind `xml` hay `xmlns` sang URI khác.
- Tránh sử dụng các prefix bắt đầu bằng "xml" theo mọi kiểu viết hoa/thường cho mục đích riêng, vì chúng được dành cho chuẩn.

Ví dụ `xml:lang="vi"` là **thuộc tính namespaced** với URI cố định `http://www.w3.org/XML/1998/namespace`. Nó không được xác định bằng default namespace của parent element.

## 5. QName trong Java: ba thành phần nhưng equals bỏ qua prefix

Class hiện hành `javax.xml.namespace.QName` có các constructor:

~~~java
QName name = new QName(
        "urn:example:order", // namespaceURI
        "item",              // localPart
        "o"                  // prefix (tuỳ chọn)
);
~~~

Đây là snippet. `QName` bất biến (*immutable*), có:

- `getNamespaceURI()`: trả namespace URI; nếu không có namespace, thường là chuỗi rỗng `XMLConstants.NULL_NS_URI`.
- `getLocalPart()`: trả local name.
- `getPrefix()`: trả prefix lưu trong object (có thể là `""`).
- `equals` và `hashCode`: **chỉ dựa vào namespace URI và local part**, không dựa vào prefix.
- `toString()`: định dạng `{namespaceURI}localPart` khi có namespace URI; **không in prefix**.
- `QName.valueOf(...)`: parse định dạng do `toString()` trả; **không tự resolve prefix lexical**.

Ví dụ:

~~~java
QName first = new QName("urn:example:order", "item", "a");
QName second = new QName("urn:example:order", "item", "b");
QName third = new QName("urn:example:other", "item", "a");

System.out.println(first.equals(second));
System.out.println(first.equals(third));
System.out.println(first.toString());
~~~

Kết quả:

~~~text
true
false
{urn:example:order}item
~~~

**Giải thích:** prefix `a` và `b` khác nhau không ảnh hưởng `equals`, nhưng namespace URI khác nhau thì không bằng. Điều này chính là cách bạn nên so sánh **tên logic** khi xử lý XML.

### 5.1. `new QName("urn:example:order", "item")` khác `new QName("o:item")`

Code:

~~~java
QName correct = new QName("urn:example:order", "item");
QName wrong = new QName("o:item");
~~~

`correct` có namespace URI và local part mong muốn. `wrong` **không phân tích dấu hai chấm để resolve namespace**; nó tạo QName với **localPart literal là `"o:item"`** và namespace URI rỗng. Constructor `QName(String localPart)` không làm nhiệm vụ parse lexical QName theo context XML.

Tương tự:

~~~java
QName parsed = QName.valueOf("{urn:example:order}item");
~~~

`valueOf` dùng định dạng kiểu Clark `{URI}local`, **không** biến chuỗi `"o:item"` thành URI nếu không có namespace context. Để resolve một lexical QName thực sự, cần đọc prefix/local part, tra binding **tại đúng element scope** rồi tạo `QName(namespaceURI, localPart, prefix)`.

### 5.2. Không đồng nhất QName với tên serialized XML

`QName.toString()` trả `{urn:...}item`, dùng tốt cho log và so sánh logic, nhưng **không phải cú pháp element tag hợp lệ trong XML**. Không viết:

~~~java
writer.writeStartElement(myQName.toString());
~~~

nếu `myQName` có namespace; vì XML tag name không có dạng `{URI}local`. Khi ghi XML, phải dùng overload nhận `prefix, localName, namespaceURI` và khai báo binding đúng; xem phần 11.

### 5.3. Prefix có thể mất khi chuyển QName sang String

Do `toString()` không lưu prefix, round-trip:

~~~java
QName input = new QName("urn:example:meta", "item", "m");
QName output = QName.valueOf(input.toString());
~~~

cho `input.equals(output) == true`, nhưng `input.getPrefix()` là `"m"`, còn `output.getPrefix()` thường là `""`. Nếu bạn cần giữ chính xác prefix lexical để tái tạo tài liệu với cách viết giống ban đầu, **đừng chỉ serialize QName bằng `toString()`**.

Ở nhiều ứng dụng XML, **expanded name** quan trọng hơn prefix gốc. Nhưng với digital signatures/canonical XML, namespace declaration/serialization có những yêu cầu chuyên biệt mà chỉ dùng `QName.equals` không đủ.

## 6. StAX XMLStreamReader: các API nên sử dụng

Khi `reader` đang trỏ tới sự kiện `START_ELEMENT`:

~~~java
QName expanded = reader.getName();
String local = reader.getLocalName();
String uri = reader.getNamespaceURI();
String prefix = reader.getPrefix();
~~~

Các method có ý nghĩa:

| API | Trả về | Lưu ý |
| --- | --- | --- |
| `getName()` | `QName` | Chứa expanded name + lexical prefix; dùng so sánh `QName` |
| `getLocalName()` | `String` | Chỉ local name, **không đủ** phân biệt namespace |
| `getNamespaceURI()` | `String` hoặc null | URI ràng buộc với current element/default namespace |
| `getPrefix()` | `String` hoặc null | Lexical prefix; không phải identity |
| `hasName()` | `boolean` | Kiểm tra event có name; thường START/END_ELEMENT |
| `getNamespaceCount()` | `int` | Số namespace declarations **ngay trên element hiện tại**, không phải toàn bộ in-scope |
| `getNamespacePrefix(i)` | `String` hoặc null | Prefix của declaration thứ i, null nếu default |
| `getNamespaceURI(i)` | `String` | URI của declaration thứ i |
| `getNamespaceURI(prefix)` | `String` hoặc null | Tra prefix binding **ở trạng thái hiện tại** |
| `getNamespaceContext()` | `NamespaceContext` | Context read-only **chỉ còn hợp lệ đến lần `next()` thay đổi state** |

**Quan trọng:** `getNamespaceURI()` **không tham số** lấy namespace của **element hiện tại**; `getNamespaceURI(String prefix)` hỏi mapping của một prefix; `getNamespaceURI(int index)` đọc namespace declaration tại vị trí trong danh sách. Tên giống nhau, nhưng ý nghĩa ba overload khác nhau.

### 6.1. Gọi getter đúng trạng thái sự kiện

`XMLStreamReader` bắt đầu tại `START_DOCUMENT`, sau đó `next()` tiến tới các sự kiện. Gọi `getName()` hay `getAttributeCount()` tại sự kiện `CHARACTERS`, `COMMENT` hoặc `START_DOCUMENT` là sai trạng thái và có thể ném `IllegalStateException`.

Mẫu:

~~~java
while (reader.hasNext()) {
    int event = reader.next();
    if (event == XMLStreamConstants.START_ELEMENT) {
        QName name = reader.getName();
        // Đọc name/attributes/namespace declarations ở đây.
    }
}
~~~

Đây là snippet trong method có `XMLStreamReader reader`; cần import `javax.xml.stream.XMLStreamConstants` và `javax.xml.namespace.QName`. Chỉ dùng `getAttributeCount()`/`getAttributeName()` khi event là `START_ELEMENT` (hoặc ATTRIBUTE state được provider sử dụng theo contract). `getName()` cũng dùng được với `END_ELEMENT`.

### 6.2. `getNamespaceCount` khác in-scope namespace map

Ví dụ:

~~~xml
<root xmlns:a="urn:one">
  <child>
    <a:item/>
  </child>
</root>
~~~

- Ở `root START_ELEMENT`: `getNamespaceCount()==1` vì trên root có khai báo `xmlns:a`.
- Ở `child START_ELEMENT`: `getNamespaceCount()==0` dù binding `a` **vẫn đang in scope**.
- Ở `a:item START_ELEMENT`: thường `getNamespaceCount()==0` dù prefix `a` được resolve thành `urn:one`.

Dùng `getNamespaceURI("a")` hoặc `getNamespaceContext().getNamespaceURI("a")` khi cần tra **mapping đang hiệu lực**; dùng `getNamespaceCount/getNamespacePrefix/getNamespaceURI(i)` khi cần enumerating **declarations tại element hiện tại**.

### 6.3. NamespaceContext là transient

JavaDoc `XMLStreamReader.getNamespaceContext()` nói rõ context read-only và **transient**, chỉ còn hợp lệ đến khi `reader.next()` thay đổi state. Nếu cần lưu binding sau khi cursor tiến, hãy **copy thông tin bạn cần ngay tại event**, không giữ reference context sống lâu rồi tra sau.

Với XML parser streaming, đây là một phần của nguyên tắc chung: nhiều dữ liệu của event chỉ được đảm bảo cho event hiện tại, không nên giữ object nội bộ qua lần `next()`.

## 7. Thuộc tính trong StAX: index 0-based và QName

Trên `START_ELEMENT`, dùng:

~~~java
for (int i = 0; i < reader.getAttributeCount(); i++) {
    QName attributeName = reader.getAttributeName(i);
    String value = reader.getAttributeValue(i);
    System.out.println(attributeName + " = " + value);
}
~~~

Đây là snippet. **Attribute indexes ở đây bắt đầu từ 0**, khác với JDBC parameter/ResultSet column indexes (bắt đầu từ 1). `getAttributeCount()` **không bao gồm namespace declarations** (`xmlns` và `xmlns:p`). Chúng được đọc bằng `getNamespaceCount()` và các namespace API riêng.

### 7.1. Cẩn thận với `getAttributeValue(null, localName)`

Theo JavaDoc `XMLStreamReader.getAttributeValue(String namespaceURI, String localName)`, **nếu `namespaceURI == null` thì namespace không được dùng để kiểm tra equality**. Nó **không có nghĩa** "chỉ tìm thuộc tính không namespace".

Với:

~~~xml
<order xmlns:m="urn:example:meta"
       id="R1"
       m:id="M1"/>
~~~

thì lời gọi:

~~~java
String ambiguous = reader.getAttributeValue(null, "id");
~~~

**không phải** phép tra cứu đặc hiệu cho `id` không namespace, vì hai attributes đều local name `id`. Kết quả có thể phụ thuộc thứ tự enumeration/implementation; đừng dựa vào nó để chọn dữ liệu nghiệp vụ.

Để chắc chắn, bạn có thể duyệt attributes rồi so `QName`:

~~~java
QName target = new QName("", "id");
String plainId = null;

for (int i = 0; i < reader.getAttributeCount(); i++) {
    if (target.equals(reader.getAttributeName(i))) {
        plainId = reader.getAttributeValue(i);
        break;
    }
}
~~~

Hoặc dùng `getAttributeValue("", "id")` nếu provider làm đúng namespace-aware contract cho chuỗi namespace rỗng. **Để xử lý hai attributes trùng local name từ các URI khác nhau**, chọn QName-based lookup là rõ ràng nhất.

### 7.2. Attribute namespace không thừa hưởng default namespace

Giả sử:

~~~xml
<item xmlns="urn:example:order" code="A" id="B"/>
~~~

- Element: `{urn:example:order}item`.
- Attribute `code`: `{}code`.
- Attribute `id`: `{}id`.

Với:

~~~xml
<item xmlns="urn:example:order"
      xmlns:o="urn:example:order"
      code="A"
      o:code="B"/>
~~~

có hai thuộc tính cùng local part `code` nhưng expanded names khác nhau: `{}code` và `{urn:example:order}code`. **Chúng có thể cùng tồn tại**, vì default namespace không áp lên unprefixed attributes.

### 7.3. Namespace declarations không phải business attributes

Khi đọc `<item xmlns="urn:x" xmlns:m="urn:m" id="1"/>`, `getAttributeCount()` thường bằng 1 (chỉ `id`), còn `getNamespaceCount()` là 2 (default và `m`). Không viết logic "tất cả thuộc tính với name bắt đầu xmlns" để tự phân tích namespace khi StAX đã cung cấp API namespace chuẩn.

## 8. Ví dụ Java 17+ chạy được: cùng expanded names dù prefix khác

### 8.1. Ý tưởng kiểm thử

Chương trình `StaxNamespaceDemo.java` tạo hai XML documents:

- Document **A** dùng default namespace `urn:example:order` cho `doc` và `item`, và prefix `m` cho `urn:example:meta`.
- Document **B** dùng prefix `o` cho cùng order URI và `info` cho cùng meta URI.
- Document A có `xmlns="urn:example:other"` ở một child rồi `xmlns=""` ở `raw` để thể hiện namespace scope/default reset.
- Document B dùng `x:item` cho other URI, còn `raw/item` không namespace.
- Cả hai có **cùng danh sách expanded element names**, dù lexical prefix khác.
- Root có `id="R1"` không namespace và `m:id="M1"` hoặc `info:id="M1"` có namespace.
- Chương trình cũng dùng `XMLStreamWriter` để ghi một document với prefix rõ ràng, parse ngược và kiểm tra URIs/attributes.

Parser bật namespace awareness, tắt DTD và external entities, đồng thời dùng resolver từ chối external references. Không cố phân tích các XML document không tin cậy bằng cấu hình mặc định.

### 8.2. File hoàn chỉnh `StaxNamespaceDemo.java`

~~~java
import java.io.StringReader;
import java.io.StringWriter;
import java.util.ArrayList;
import java.util.List;
import javax.xml.namespace.QName;
import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLOutputFactory;
import javax.xml.stream.XMLStreamConstants;
import javax.xml.stream.XMLStreamException;
import javax.xml.stream.XMLStreamReader;
import javax.xml.stream.XMLStreamWriter;

public final class StaxNamespaceDemo {
    private static final String ORDER = "urn:example:order";
    private static final String META = "urn:example:meta";

    record Scan(List<QName> names, int localItemCount,
                int qualifiedItemCount, String rootPrefix,
                int rootDeclarations, String plainId, String metaId) {}

    static Scan inspect(String xml) throws XMLStreamException {
        XMLInputFactory factory = XMLInputFactory.newFactory();
        factory.setProperty(XMLInputFactory.IS_NAMESPACE_AWARE, true);
        factory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
        factory.setProperty(
                XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
        factory.setXMLResolver((publicId, systemId, baseUri, namespace) -> {
            throw new XMLStreamException("External XML resource forbidden");
        });

        XMLStreamReader reader =
                factory.createXMLStreamReader(new StringReader(xml));
        try {
            List<QName> names = new ArrayList<>();
            int localItems = 0;
            int orderItems = 0;
            String rootPrefix = "";
            int rootDeclarations = -1;
            String plainId = null;
            String metaId = null;

            while (reader.hasNext()) {
                if (reader.next() != XMLStreamConstants.START_ELEMENT) {
                    continue;
                }
                QName name = reader.getName();
                names.add(name);
                if ("item".equals(reader.getLocalName())) {
                    localItems++;
                }
                if (new QName(ORDER, "item").equals(name)) {
                    orderItems++;
                }
                if (new QName(ORDER, "doc").equals(name)) {
                    rootPrefix = reader.getPrefix();
                    rootDeclarations = reader.getNamespaceCount();
                    for (int i = 0; i < reader.getAttributeCount(); i++) {
                        QName attr = reader.getAttributeName(i);
                        if (new QName("", "id").equals(attr)) {
                            plainId = reader.getAttributeValue(i);
                        } else if (new QName(META, "id").equals(attr)) {
                            metaId = reader.getAttributeValue(i);
                        }
                    }
                }
            }
            return new Scan(names, localItems, orderItems,
                    rootPrefix, rootDeclarations, plainId, metaId);
        } finally {
            reader.close();
        }
    }

    static String writeXml() throws XMLStreamException {
        StringWriter chars = new StringWriter();
        XMLStreamWriter writer =
                XMLOutputFactory.newFactory().createXMLStreamWriter(chars);
        try {
            writer.setPrefix("o", ORDER);
            writer.setPrefix("m", META);
            writer.writeStartDocument("UTF-8", "1.0");
            writer.writeStartElement("o", "doc", ORDER);
            writer.writeNamespace("o", ORDER);
            writer.writeNamespace("m", META);
            writer.writeAttribute("id", "R1");
            writer.writeAttribute("m", META, "id", "M1");
            writer.writeStartElement("o", "item", ORDER);
            writer.writeEndElement();
            writer.writeEndElement();
            writer.writeEndDocument();
        } finally {
            writer.close();
        }
        return chars.toString();
    }

    public static void main(String[] args) throws Exception {
        String a = """
                <doc xmlns="urn:example:order" xmlns:m="urn:example:meta"
                     id="R1" m:id="M1">
                  <item/>
                  <m:item/>
                  <item xmlns="urn:example:other"/>
                  <raw xmlns=""><item/></raw>
                </doc>
                """;
        String b = """
                <o:doc xmlns:o="urn:example:order" xmlns:info="urn:example:meta"
                       id="R1" info:id="M1">
                  <o:item/>
                  <info:item/>
                  <x:item xmlns:x="urn:example:other"/>
                  <raw><item/></raw>
                </o:doc>
                """;

        Scan first = inspect(a);
        Scan second = inspect(b);
        System.out.println("Root A prefix: "
                + (first.rootPrefix().isEmpty() ? "<default>"
                                                : first.rootPrefix()));
        System.out.println("Root B prefix: " + second.rootPrefix());
        System.out.println("Root A local name: "
                + first.names().get(0).getLocalPart());
        System.out.println("Root A namespace URI: "
                + first.names().get(0).getNamespaceURI());
        System.out.println("Namespace declarations on root A: "
                + first.rootDeclarations());
        System.out.println("Unqualified attribute id: " + first.plainId());
        System.out.println("Qualified attribute meta:id: " + first.metaId());
        System.out.println("Attribute QNames distinct: "
                + !new QName("", "id").equals(new QName(META, "id")));
        System.out.println("Local item count: " + first.localItemCount());
        System.out.println("Expanded-name order item count: "
                + first.qualifiedItemCount());
        System.out.println("Expanded names equal after prefix rewrite: "
                + first.names().equals(second.names()));
        QName itemM = new QName(META, "item", "m");
        QName itemInfo = new QName(META, "item", "info");
        System.out.println("QName equality ignores prefix: "
                + itemM.equals(itemInfo));
        System.out.println("QName string: " + itemM);
        System.out.println("QName valueOf roundtrip: "
                + QName.valueOf(itemM.toString()).equals(itemM));

        Scan generated = inspect(writeXml());
        System.out.println("Writer element namespace correct: "
                + generated.names().get(0).equals(new QName(ORDER, "doc")));
        System.out.println("Writer attributes preserved: "
                + ("R1".equals(generated.plainId())
                    && "M1".equals(generated.metaId())));
    }
}
~~~

### 8.3. Biên dịch và chạy

Lưu đúng tên `StaxNamespaceDemo.java`. Dùng JDK 17 hoặc mới hơn:

~~~sh
javac --release 17 StaxNamespaceDemo.java
java StaxNamespaceDemo
~~~

**Stdout chính xác**, đã biên dịch bằng `javac --release 17` và chạy trên JDK 24:

~~~text
Root A prefix: <default>
Root B prefix: o
Root A local name: doc
Root A namespace URI: urn:example:order
Namespace declarations on root A: 2
Unqualified attribute id: R1
Qualified attribute meta:id: M1
Attribute QNames distinct: true
Local item count: 4
Expanded-name order item count: 1
Expanded names equal after prefix rewrite: true
QName equality ignores prefix: true
QName string: {urn:example:meta}item
QName valueOf roundtrip: true
Writer element namespace correct: true
Writer attributes preserved: true
~~~

Đây là **chương trình Java SE độc lập**, không dùng database, không cần dependency ngoài JDK.

### 8.4. Phân tích vì sao output có các con số đó

**Root A namespace declarations = 2:** ở root của A có `xmlns="urn:example:order"` và `xmlns:m="urn:example:meta"`. Đây là hai declarations của element, không phải `getAttributeCount()` và không đại diện cho toàn bộ namespace bindings của tất cả descendants.

**Local item count = 4:** trong A xuất hiện bốn `item` về mặt local name:

1. `<item/>` trong namespace `urn:example:order`.
2. `<m:item/>` trong namespace `urn:example:meta`.
3. `<item xmlns="urn:example:other"/>` trong namespace `urn:example:other`.
4. `<item/>` nằm dưới `<raw xmlns="">`, không namespace.

**Expanded-name order item count = 1:** chỉ phần tử đầu tiên có expanded name `{urn:example:order}item`. Nếu code lọc bằng local name thì sẽ chọn nhầm ba phần tử không thuộc namespace mục tiêu.

**A/B element expanded names equal = true:** `List<QName>.equals` so từng `QName` bằng `QName.equals`, vốn bỏ qua prefix. Vì thế tài liệu A dùng default namespace + m và B dùng o + info vẫn có cùng danh sách expanded names. Bài demo **không kết luận hai tài liệu XML bất kỳ là semantically equivalent** chỉ từ một danh sách tên; một XML có thể khác attributes, text, thứ tự children, namespaces trong QName-typed content hoặc cấu trúc dữ liệu.

**Attributes:** `id` không namespace và `m:id` có namespace khác nhau, nên đều xuất hiện hợp lệ và được nhận diện độc lập.

**Writer:** `XMLOutputFactory` tạo `XMLStreamWriter`, code gọi `setPrefix` và viết `writeNamespace` bindings rồi `writeStartElement`/`writeAttribute` theo namespace URI. Dữ liệu ghi ra được parse lại để xác minh **đúng expanded name và cả hai attribute values**, thay vì so sánh bytes hay prefix cụ thể.

## 9. Ví dụ thứ hai: cùng prefix, namespace URI thay đổi giữa các scopes

Không chỉ có chuyện **khác prefix nhưng cùng URI**. Một prefix cũng có thể được **rebind** trong scope con. Ví dụ thứ hai đã biên dịch/chạy độc lập:

### 9.1. File `NamespaceShadowDemo.java`

~~~java
import java.io.StringReader;
import javax.xml.namespace.QName;
import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLStreamConstants;
import javax.xml.stream.XMLStreamException;
import javax.xml.stream.XMLStreamReader;

public final class NamespaceShadowDemo {
    public static void main(String[] args) throws XMLStreamException {
        String xml = """
                <root xmlns:p="urn:one">
                  <p:item/>
                  <section xmlns:p="urn:two"><p:item/></section>
                  <p:item/>
                </root>
                """;
        XMLInputFactory f = XMLInputFactory.newFactory();
        f.setProperty(XMLInputFactory.IS_NAMESPACE_AWARE, true);
        f.setProperty(XMLInputFactory.SUPPORT_DTD, false);
        f.setProperty(XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
        f.setXMLResolver((publicId, systemId, baseUri, namespace) -> {
            throw new XMLStreamException("External resource forbidden");
        });

        XMLStreamReader r = f.createXMLStreamReader(new StringReader(xml));
        try {
            int count = 0;
            while (r.hasNext()) {
                if (r.next() == XMLStreamConstants.START_ELEMENT
                        && "item".equals(r.getLocalName())) {
                    count++;
                    QName name = r.getName();
                    System.out.println("item " + count + ": prefix="
                            + r.getPrefix() + ", expanded=" + name);
                }
            }
        } finally {
            r.close();
        }
    }
}
~~~

### 9.2. Chạy và kiểm chứng

~~~sh
javac --release 17 NamespaceShadowDemo.java
java NamespaceShadowDemo
~~~

Stdout chính xác trên JDK 24:

~~~text
item 1: prefix=p, expanded={urn:one}item
item 2: prefix=p, expanded={urn:two}item
item 3: prefix=p, expanded={urn:one}item
~~~

Một parser dùng duy nhất string prefix `p` để phân loại sẽ phân loại sai phần tử thứ hai. Nhờ StAX resolve namespace **ở vị trí hiện tại**, `QName` đúng cho từng scope. Khi `section` kết thúc, mapping gốc lại có hiệu lực.

## 10. Ghi XML đúng namespace với XMLStreamWriter

Đọc namespace đúng là một nửa; **ghi** cũng phải bind prefix chính xác. Khi gọi:

~~~java
XMLStreamWriter writer =
        XMLOutputFactory.newFactory().createXMLStreamWriter(output);
writer.setPrefix("o", "urn:example:order");
writer.writeStartDocument("UTF-8", "1.0");
writer.writeStartElement("o", "order", "urn:example:order");
writer.writeNamespace("o", "urn:example:order");
writer.writeEndElement();
writer.writeEndDocument();
writer.close();
~~~

Đây là snippet với `output` là một `Writer`/destination hợp lệ. Các method `setPrefix` và `writeNamespace` **không đồng nghĩa tuyệt đối**:

- `setPrefix(prefix, uri)` thiết lập binding trong namespace context của writer.
- `writeNamespace(prefix, uri)` ghi namespace declaration ra output XML.
- `writeStartElement(prefix, localName, uri)` ghi element với prefix/URI tương ứng.
- `writeAttribute(prefix, uri, localName, value)` ghi thuộc tính có namespace, nhưng prefix tương ứng phải được bind/declared đúng trong output.

Một số providers hỗ trợ **namespace repairing mode** `XMLOutputFactory.IS_REPAIRING_NAMESPACES`, cho phép writer cố tạo declaration/điều chỉnh prefix tự động. Mặc định **không nên coi repairing luôn bật**; cách portable và dễ kiểm soát trong bài là khai báo rõ prefixes và viết namespace declarations.

### 10.1. Default namespace khi ghi

Nếu muốn ghi elements không prefix trong default namespace, dùng `setDefaultNamespace(uri)` và `writeDefaultNamespace(uri)` theo writer API, sau đó `writeStartElement("", localName, uri)` ở context phù hợp. Cần kiểm chứng serialization trên provider cụ thể, vì namespace repairing và default binding có thể ảnh hưởng output.

Ví dụ XML mục tiêu:

~~~xml
<order xmlns="urn:example:order">
  <item code="A"/>
</order>
~~~

Dù `order` và `item` không có prefix, cả hai mang URI `urn:example:order`. Thuộc tính `code` vẫn **không namespace**. Nếu muốn thuộc tính namespace-aware, ghi prefix rõ ràng và declaration tương ứng.

### 10.2. Cẩn thận với `writeAttribute("id", "...")`

Overload `writer.writeAttribute("id", "R1")` tạo thuộc tính **không prefix**, nên không có namespace ngay cả khi element đang trong default namespace.

Để ghi thuộc tính có namespace:

~~~java
writer.writeAttribute(
        "m", "urn:example:meta", "id", "M1");
~~~

Đây là snippet trong scope đã khai báo `xmlns:m="urn:example:meta"`; không đưa prefix `m` vào local name. Đừng viết localName `"m:id"` vào overload chuyên nhận `localName`.

### 10.3. So sánh expanded names sau ghi, không ép prefix giống input

Một serializer/transformer có thể đổi từ `m:item` sang `info:item` mà vẫn giữ expanded name. Nếu ứng dụng quan tâm nội dung và schema, test nên **parse lại rồi so `QName(namespaceURI, localPart)`**. Nếu bài toán cần chữ ký XML, canonicalization hay bảo toàn prefix lexical, đó là một contract serialization đặc biệt, phải dùng công cụ XML signature/canonicalization phù hợp.

## 11. XMLEventReader và StartElement: lựa chọn cùng kiến thức namespace

StAX có hai họ API:

| Họ API | Lớp chính | Cách lấy tên |
| --- | --- | --- |
| Cursor | `XMLStreamReader` | `getName()`, `getLocalName()`, `getNamespaceURI()`, `getPrefix()` |
| Event | `XMLEventReader`, `StartElement`, `Attribute`, `Namespace` | `startElement.getName()`, `attribute.getName()` |

Nếu dùng `XMLEventReader`, một phần tử bắt đầu có `StartElement.getName()` trả `QName`; vẫn so bằng URI + local part, không theo prefix.

Một snippet:

~~~java
while (events.hasNext()) {
    XMLEvent event = events.nextEvent();
    if (event.isStartElement()) {
        QName name = event.asStartElement().getName();
        if (new QName("urn:example:order", "item").equals(name)) {
            // Đúng phần tử item trong order namespace.
        }
    }
}
~~~

Đây là snippet với `XMLEventReader events` đã tạo; cần import `javax.xml.stream.events.XMLEvent` và `javax.xml.namespace.QName`. Lựa chọn cursor/event API không làm thay đổi semantics của XML namespace.

Event API có thể phù hợp khi cần pass sự kiện qua nhiều lớp; cursor API có thể ít object allocations hơn theo provider. Hiệu năng phụ thuộc parser, document và workload, không coi một cách luôn nhanh hơn trong mọi trường hợp.

## 12. Lexical QName trong giá trị thuộc tính hoặc text: xử lý riêng

Namespace trong XML phân giải **tên element và attribute** theo cấu trúc XML. Nhưng trong một số XML vocabularies, giá trị của attribute hoặc text **cũng được schema định nghĩa là kiểu QName**.

Ví dụ khái niệm:

~~~xml
<request xmlns:t="urn:example:types"
         xsi:type="t:Order"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"/>
~~~

Ở đây `xsi:type` là một thuộc tính có expanded name trong namespace XML Schema Instance; **giá trị** `t:Order` được vocabulary/schema hiểu như một lexical QName. XML parser bình thường có thể trả **chuỗi giá trị `"t:Order"`**, không tự convert thành `QName` tương ứng.

Để resolve `"t:Order"` trong context:

1. Tách lexical prefix `t` và local part `Order` **theo grammar QName**.
2. Tra `t` qua namespace context hiện tại (khi parser đang đứng ở element mang attribute).
3. Kiểm tra prefix có binding, validate local part theo quy tắc XML Names.
4. Tạo `new QName("urn:example:types", "Order", "t")`.
5. Không giữ `reader.getNamespaceContext()` để tra sau khi cursor tiến, vì context là transient.

**Đặc biệt:** không phải mọi chuỗi chứa dấu `:` đều là QName typed value. Chỉ xử lý như QName khi schema/vocabulary thật sự yêu cầu. Default namespace và unprefixed QName-valued text có thể có quy tắc do datatype/vocabulary xác định; đừng áp máy móc quy tắc element names cho mọi nội dung text.

### 12.1. Vì sao `QName.valueOf("t:Order")` không đủ?

`QName.valueOf` hiểu format từ `QName.toString`, chẳng hạn `{urn:example:types}Order`. Nó **không truy cập StAX namespace context**, nên không biết `t` được bind với URI nào trong XML hiện tại. Nhầm hai cách này có thể khiến code bỏ mất namespace hoặc xem cả `"t:Order"` như một localPart literal.

## 13. Bảo mật StAX: namespace đúng nhưng parser cũng phải an toàn

Bài toán namespace thường gặp trong XML đến từ bên ngoài: SOAP, RSS/Atom, import/export, webhook XML, XML config, tài liệu nghiệp vụ. XML không tin cậy có thể chứa DTD, external entities hoặc cấu trúc quá lớn gây tấn công tài nguyên (XXE/entity expansion/DoS).

Một cấu hình cơ bản:

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

Đây là snippet Java 17+, cần import `javax.xml.stream.XMLInputFactory` và `XMLStreamException`. Các flags giảm thiểu rủi ro; nên bổ sung giới hạn kích thước XML, độ sâu, số lượng events/attributes, processing time và giới hạn JAXP/provider khi cần.

**Lưu ý an toàn:** `SUPPORT_DTD=false` không đồng nghĩa mọi StAX provider đều bắt buộc từ chối toàn bộ văn bản chứa `DOCTYPE`; semantics xử lý DTD phụ thuộc hợp đồng và implementation. Với input không tin cậy, nên kết hợp external-entity disable, deny-all resolver, resource limits và test bằng payload DTD/external entity của provider sử dụng. Nếu parser không thể đáp ứng chính sách yêu cầu, **fail closed** thay vì âm thầm parse với khả năng truy cập external resources.

Namespace URI **không phải external entity URI**: một namespace tên `https://example.com/ns/order` không làm parser phải fetch URL đó chỉ vì nó là namespace. Mối nguy XXE chủ yếu đến từ entities, DTD và những tham chiếu external khác, không phải bản thân tên URI namespace.

### 13.1. Reader/InputStream và encoding

Khi dùng `factory.createXMLStreamReader(new StringReader(xml))`, đầu vào là ký tự Java; source đã được giải mã. Khi dùng `InputStream` chứa bytes, parser có thể xử lý XML encoding declaration theo đặc tả XML.

Không tự chuyển bytes qua charset mặc định rồi mới parse, nhất là XML có declaration `encoding="UTF-8"`. Nếu ứng dụng cần kiểm soát encoding, dùng một luồng byte và contract nhất quán; với XML input không đáng tin cần đặt giới hạn đọc dữ liệu ngay cả trước parser.

### 13.2. Đóng XMLStreamReader và nguồn dữ liệu

Mẫu an toàn khi source do caller tạo:

~~~java
try (Reader source = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    XMLStreamReader reader = factory.createXMLStreamReader(source);
    try {
        while (reader.hasNext()) {
            reader.next();
        }
    } finally {
        reader.close();
    }
}
~~~

Đây là snippet với `path` và `factory` đã có, cần imports `java.io.Reader`, `java.nio.file.Files`, `StandardCharsets`. **Đóng XMLStreamReader không được tự xem là thay thế việc đóng Reader nguồn**, nên quản lý cả hai resources. StAX XMLStreamReader không bắt buộc AutoCloseable trong Java 17; dùng `try/finally` cho parser.

## 14. Cách lọc element đúng namespace trong dự án thật

Hàm nhỏ hữu ích:

~~~java
static boolean isElement(XMLStreamReader reader, QName wanted) {
    return reader.getEventType() == XMLStreamConstants.START_ELEMENT
            && wanted.equals(reader.getName());
}
~~~

Đây là snippet method, import `XMLStreamReader`, `XMLStreamConstants` và `QName`. Không gọi `getName()` khi event không có name.

Dùng:

~~~java
QName wanted = new QName("urn:example:order", "item");

while (reader.hasNext()) {
    reader.next();
    if (isElement(reader, wanted)) {
        // Đã gặp <item>, <o:item>, <x:item>... cùng expanded name.
    }
}
~~~

Nhưng **nhận diện phần tử đúng tên chưa đủ cho mọi nghiệp vụ**: một `item` hợp lệ có thể xuất hiện ở vị trí không đúng schema (chẳng hạn ngoài `order`). Muốn parse chính xác, cần theo dõi depth, parent path/expected state hoặc XML Schema validation có cấu hình an toàn. Đừng chỉ so QName rồi bỏ qua cấu trúc tài liệu.

### 14.1. Dùng `XMLStreamReader.require` đúng cách

`reader.require(eventType, namespaceURI, localName)` kiểm tra type và (nếu tham số khác null) namespace URI/local name:

~~~java
reader.require(
        XMLStreamConstants.START_ELEMENT,
        "urn:example:order",
        "item");
~~~

Đây là snippet với reader hiện đang trỏ tới start element mong muốn. **Không truyền namespaceURI null nếu bạn muốn xác nhận không namespace**: theo JavaDoc, null ở `require` có nghĩa **không kiểm tra namespace URI**. Để kiểm tra no-namespace một cách rõ ràng, so `reader.getName()` với `new QName("", "item")`.

Tương tự, `reader.getAttributeValue(null, "id")` cho phép bất kỳ namespace nào có local `id`, không phải no-namespace. Những overload có null như wildcard là nguồn lỗi logic rất khó phát hiện.

### 14.2. Đừng hardcode prefix của partner

Không nên:

~~~java
if ("o".equals(reader.getPrefix())
        && "item".equals(reader.getLocalName())) {
    // Có thể bỏ sót document hợp lệ dùng default namespace.
}
~~~

Nên:

~~~java
if (new QName("urn:example:order", "item")
        .equals(reader.getName())) {
    // Match theo expanded name.
}
~~~

Đây là snippets tại `START_ELEMENT`. Prefix của partner có thể thay đổi khi họ refactor XML serializer, thêm default namespace hoặc rebind prefix ở một scope con, dù semantic schema vẫn giữ nguyên.

## 15. Các bài kiểm thử cần có

| Test case | Input | Kỳ vọng |
| --- | --- | --- |
| Đổi prefix | `a:item` → `b:item` với cùng URI | Cùng QName expanded |
| Đổi default namespace | `xmlns="urn:one"` → `xmlns="urn:two"` | Khác QName |
| Default reset | `<raw xmlns=""><item/></raw>` | Child `item` không namespace |
| Cùng local name | `o:item`, `m:item` | Phân biệt theo URI |
| Prefix shadowing | `xmlns:p` ở child khác root | Expanded name thay đổi theo scope |
| Unprefixed attribute | `id="R1"` trong element default ns | `id` không namespace |
| Namespaced attribute | `m:id="M1"` | QName có namespace META |
| Hai id attributes | `id` và `m:id` cùng tag | Được phép vì expanded names khác |
| Trùng expanded attr | `a:id` và `b:id` cùng URI/local | XML namespace-conforming từ chối |
| `getAttributeValue(null,"id")` | Có hai id khác URI | Không dùng làm lookup đặc hiệu |
| `getNamespaceCount` ở child | Binding chỉ khai báo trên parent | 0 nếu child không khai báo mới |
| `QName.equals` | Khác prefix cùng URI/local | true |
| `QName.toString` | QName có prefix | String bỏ prefix |
| Unbound prefix | `<p:item/>` không khai báo `p` | Namespace-aware parser phải báo XML error |
| Wrong event | `getAttributeCount` tại text event | `IllegalStateException` theo API |
| XML input có DTD/XXE | External entity payload | Bị chặn theo security policy |
| Stream rất lớn | XML nhiều MB | Giới hạn memory/time, đóng resources |
| Writer round-trip | XMLStreamWriter rồi XMLStreamReader | Same expanded names & attributes |
| QName-typed value | `xsi:type="p:Order"` | Resolve prefix tại event scope theo schema |
| URI gần giống nhau | `urn:one` và `URN:one` | Không bằng do khác chuỗi |
| XML path sai | `item` ở parent không hợp lệ | Structural validator từ chối |

### 15.1. Bài tập A: lọc đúng một loại item

Với XML `A` của ví dụ chính, hãy đổi điều kiện:

~~~java
if ("item".equals(reader.getLocalName())) {
    count++;
}
~~~

thành:

~~~java
QName expected = new QName("urn:example:order", "item");
if (expected.equals(reader.getName())) {
    count++;
}
~~~

Kỳ vọng từ chương trình:

~~~text
Local item count: 4
Expanded-name order item count: 1
~~~

Hãy lý giải vì sao ba `item` còn lại không thuộc order namespace. Khi gặp cùng local name từ những vocabulary khác nhau, chỉ so local name có thể làm xử lý nhầm dữ liệu.

### 15.2. Bài tập B: thay prefix mà giữ nguyên nghĩa

Đổi Document B từ `o` thành `booking` và `info` thành `metadata`, giữ các namespace URIs nguyên. Parser vẫn phải in:

~~~text
Expanded names equal after prefix rewrite: true
~~~

Điều kiện: thay **cả tên các phần tử/thuộc tính và khai báo xmlns tương ứng**. Nếu chỉ sửa tên tag nhưng quên khai báo prefix, XML không còn namespace-well-formed.

### 15.3. Bài tập C: thay URI mà giữ prefix

Trong `NamespaceShadowDemo`, đổi child binding `xmlns:p="urn:two"` thành `xmlns:p="urn:three"`. Kỳ vọng dòng giữa đổi thành:

~~~text
item 2: prefix=p, expanded={urn:three}item
~~~

Các dòng đầu/cuối vẫn `urn:one`. Điều này chứng minh prefix không phải identifier duy nhất.

### 15.4. Bài tập D: truy xuất thuộc tính chính xác

Thử document:

~~~xml
<doc xmlns="urn:example:order"
     xmlns:m="urn:example:meta"
     id="R1" m:id="M1"/>
~~~

Hãy tìm cả hai `id` bằng `getAttributeCount` + `getAttributeName` so `QName` rồi xác minh values khác nhau. Không dùng `getAttributeValue(null,"id")` vì null namespace ở API này là wildcard.

## 16. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| `getPrefix()` dùng làm identity | Đổi alias là parser lỗi logic | So expanded QName |
| Chỉ so `getLocalName()` | Trộn nhiều vocabulary cùng local name | So cả namespace URI |
| Prefix rỗng được coi là no-namespace | Default namespace bị bỏ qua | Xem `getNamespaceURI/getName` |
| Default namespace áp cho thuộc tính `id` | Không tìm được attribute hoặc mapping sai | Unprefixed attribute **không namespace** |
| `getAttributeValue(null,"id")` để lấy no-ns | Null nghĩa wildcard namespace | So `QName("", "id")` hoặc namespace rỗng |
| Coi `xmlns` là attribute kinh doanh | Đếm sai hoặc parse nhầm config | Dùng namespace APIs |
| `getNamespaceCount()` là số in-scope bindings | Bỏ sót declarations trên ancestors | Phân biệt local declarations và NamespaceContext |
| Lưu `NamespaceContext` qua `next()` | Context transient, kết quả sai | Copy binding cần thiết tại event |
| `QName.equals` phụ thuộc prefix | Xử lý sai case đổi prefix | equals dùng URI + local |
| `QName.valueOf("m:item")` tự resolve m | Tạo QName sai namespace | Tra namespace context theo scope |
| `new QName("m:item")` được xem là tên qualified | Chỉ là localPart literal | Dùng constructor có URI |
| `QName.toString()` được ghi làm tag name | XML output không hợp lệ | Writer overload prefix/local/URI |
| `writeStartElement` mà quên `writeNamespace` | Prefix unbound trong output | Bind và declare rõ ràng |
| Giả định writer luôn auto-repair namespace | Output thiếu binding theo provider | Cấu hình repairing hoặc khai báo rõ |
| Gọi `getName()` ở `CHARACTERS` | `IllegalStateException` | Kiểm tra event state |
| Nhầm attribute index với JDBC index | Off-by-one | StAX attr index 0-based |
| Nghĩ URI namespace phải có trang web | Network call thừa | URI là identifier |
| Dùng XMLInputFactory mặc định cho untrusted input | XXE/DoS risk | Tắt DTD/entities, deny resolver, limits |
| Chỉ đóng XMLStreamReader | Có thể leak source Reader/InputStream | Đóng cả source |
| Chỉ so danh sách names rồi kết luận XML tương đương | Bỏ qua text/attrs/path/order/typed values | Validate toàn cấu trúc đúng schema |
| Hardcode prefix từ sample document | Partner đổi prefix, parser hỏng | Xây QName constant từ URI/local |

## 17. Câu hỏi tự kiểm tra

**Câu 1.** `prefix` trong `p:item` có phải danh tính lâu dài của phần tử không?

**Trả lời:** Không. Prefix là alias scoped, có thể thay đổi giữa documents hoặc được rebind trong child scope. Identity là namespace URI + local part.

**Câu 2.** `<item xmlns="urn:one"/>` và `<x:item xmlns:x="urn:one"/>` có cùng QName không?

**Trả lời:** Có; cả hai là `{urn:one}item`, dù một tên không prefix và một tên có prefix.

**Câu 3.** `<p:item xmlns:p="urn:one"/>` và `<p:item xmlns:p="urn:two"/>` có cùng QName không?

**Trả lời:** Không, vì namespace URI khác nhau dù lexical prefix/local name giống.

**Câu 4.** `getLocalName()` trả gì khi đọc `m:title`?

**Trả lời:** `"title"`. Nó không chứa `m` hay URI của `m`.

**Câu 5.** `QName.equals` có xét prefix không?

**Trả lời:** Không. Chỉ xét namespace URI và local part. Prefix dùng để giữ lexical information, không nằm trong equals/hashCode.

**Câu 6.** Vì sao `id` trong element có `xmlns="urn:one"` vẫn không namespace?

**Trả lời:** Theo W3C Namespaces, default namespace áp cho **unprefixed element names**, không áp cho unprefixed attribute names.

**Câu 7.** Khi nào `getNamespaceCount()` bằng 0 dù prefix đang được dùng?

**Trả lời:** Khi element hiện tại không khai báo namespace mới nhưng kế thừa binding từ ancestor. Count chỉ đo declarations trên element hiện tại.

**Câu 8.** Muốn tra URI của prefix `p` tại vị trí cursor thì dùng gì?

**Trả lời:** `getNamespaceURI("p")` hoặc `getNamespaceContext().getNamespaceURI("p")` ở event hiện tại. Không giữ transient NamespaceContext qua `next()`.

**Câu 9.** Vì sao `getAttributeValue(null,"id")` không thích hợp để tìm `id` no-namespace?

**Trả lời:** Vì JavaDoc nói namespaceURI null làm **bỏ qua kiểm tra namespace**, nên nó có thể match attribute khác namespace cùng local name. Dùng QName-based search để chính xác.

**Câu 10.** Trong `QName("urn:one","item","p")`, `getPrefix()` trả gì?

**Trả lời:** `"p"`. Nhưng `toString()` thường là `"{urn:one}item"`, không giữ prefix.

**Câu 11.** `QName.valueOf("p:item")` có tra `xmlns:p` không?

**Trả lời:** Không. Nó không có namespace context. Muốn resolve lexical QName phải tra binding đúng scope.

**Câu 12.** `XMLStreamReader.getName()` có thể gọi trên mọi event không?

**Trả lời:** Không. Chủ yếu hợp lệ trên `START_ELEMENT` và `END_ELEMENT`; gọi sai state gây `IllegalStateException` theo API.

**Câu 13.** Namespace URI `https://example.com/ns` có bắt buộc StAX tải URL đó không?

**Trả lời:** Không. Namespace URI là tên nhận diện; các truy vấn external entities/DTD là cơ chế khác và cần bảo vệ riêng.

**Câu 14.** Vì sao cần viết `writeNamespace` khi ghi với XMLStreamWriter?

**Trả lời:** Vì đặt binding trong writer context và **ghi declaration ra XML** là hai hành động khác nhau; muốn output hợp lệ, prefix phải được khai báo trong scope đúng.

**Câu 15.** Dấu `:` trong một attribute value có nghĩa value chắc chắn là QName không?

**Trả lời:** Không. Chỉ những fields được vocabulary/schema xác định là QName-valued mới cần resolve prefix; nội dung text thông thường không tự bị StAX chuyển thành QName.

**Câu 16.** Một chương trình XML parser nhận tài liệu từ user cần biện pháp gì ngoài namespace-aware?

**Trả lời:** Tắt DTD/external entity resolution, deny-all resolver, giới hạn size/depth/time, test provider và đóng parser/source resources; fail closed nếu không đáp ứng chính sách.

**Tóm tắt:** StAX phân biệt **local name**, **prefix** và **namespace URI**. Tên logic của element/attribute là expanded name **(URI, local name)**. `QName.equals` bỏ qua prefix; default namespace áp cho **elements không prefix** nhưng không áp cho **attributes không prefix**. Prefix mappings có scope và có thể rebind; `XMLStreamReader.getNamespaceCount()` chỉ đếm declarations tại element, còn `NamespaceContext` là transient. Hãy so `QName` khi nhận diện phần tử, bind/declare namespace rõ ràng khi viết XML, và luôn cấu hình StAX an toàn với XML không tin cậy.

### Tài liệu tham khảo chính thức và hiện hành

- [Oracle Java SE 26 — XMLStreamReader](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLStreamReader.html): `getName`, `getLocalName`, `getNamespaceURI`, attributes, transient NamespaceContext.
- [Oracle Java SE 26 — QName](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/namespace/QName.html): `equals` bỏ qua prefix, `toString` và `valueOf`.
- [Oracle Java SE 26 — XMLInputFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLInputFactory.html): namespace-aware parser và các security properties.
- [Oracle Java SE 26 — XMLStreamWriter](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLStreamWriter.html): `setPrefix`, `writeNamespace`, `writeStartElement`, `writeAttribute`.
- [Oracle Java SE 26 — XMLOutputFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLOutputFactory.html): namespace repairing mode.
- [Oracle Java SE 26 — XMLEventReader](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLEventReader.html): StAX event API.
- [W3C — Namespaces in XML 1.0 (Third Edition)](https://www.w3.org/TR/xml-names/): expanded names, default namespace, prefix scope, attribute uniqueness.
- [OWASP — XML External Entity Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html): StAX/XMLInputFactory parser hardening.
