# Xử lý phần tử thiếu, nhiều kết quả và chuyển kiểu giá trị XPath

## 1. Vì sao xử lý XPath phải bắt đầu từ «số lượng kết quả»?

Trong **Spring Web Services (Spring-WS)** theo hướng **contract-first**, XSD/WSDL quy định rõ SOAP Body được phép chứa những phần tử nào, phần tử nào bắt buộc, được lặp bao nhiêu lần và sử dụng kiểu dữ liệu gì. JAXB là lựa chọn phổ biến để ánh xạ XML sang Java object, nhưng có những trường hợp ứng dụng cần **đọc XML trực tiếp** qua DOM/XPath: kiểm tra một node trong SOAP Header, xử lý payload của đối tác cũ, trích xuất vài trường dữ liệu, hoặc kiểm tra thông điệp trước khi chuyển cho bộ xử lý khác.

XPath giúp chọn node rất nhanh, song một câu lệnh tưởng đơn giản như:

```java
String status = xpath.evaluate("./ord:status", orderElement);
```

có thể che giấu ba trường hợp khác nhau: *không có element*, *có element rỗng*, và *có nhiều element nhưng đang lấy giá trị của một element*. Khi chuyển sang `double` hoặc `boolean`, việc tự động ép kiểu theo XPath 1.0 còn dễ tạo ra lỗi nghiệp vụ.

Bài này tập trung xử lý ba câu hỏi:

1. **Thiếu phần tử:** làm sao phân biệt vắng mặt, chuỗi rỗng, khoảng trắng và `xsi:nil="true"`?
2. **Nhiều kết quả:** khi nào dùng `NodeList`, kiểm tra cardinality, giữ thứ tự và tránh chỉ đọc phần tử đầu?
3. **Chuyển kiểu:** giá trị `String`, `Double`, `Boolean` của XPath khác gì các kiểu XSD như `xs:decimal`, `xs:boolean`, `xs:date` và kiểu Java `BigDecimal`?

Nội dung áp dụng cho Java JAXP XPath, DOM và Spring-WS `@XPathParam`. Bài cũng kết nối đến XSD validation, SOAP Fault, XML security và kiểm thử liên thông, vì xử lý XML đúng về mặt cú pháp chưa chắc đã đúng hợp đồng doanh nghiệp.

### Kết quả cần đạt

Sau khi học, bạn có thể:

- Cấu hình XPath có namespace đúng, dùng biểu thức tương đối/đường dẫn tuyệt đối hợp lý.
- Lấy `NODE` khi chỉ mong đợi một node, `NODESET` khi có thể có nhiều node.
- Phân biệt **absent / nil / empty / text** mà không làm mất thông tin.
- Chuyển kiểu tiền tệ và số lượng an toàn; phát hiện kết quả `NaN` và bool chuyển sai.
- Viết một bộ đọc XML phòng thủ, giới hạn tài nguyên và kiểm chứng bằng schema.
- Dùng `@XPathParam` khi phù hợp, nhưng không mặc nhiên dựa vào chuyển kiểu tự động cho dữ liệu nghiệp vụ nhạy cảm.
- Xây ma trận test bao phủ 0/1/N kết quả, namespace, XPath injection, XXE và SOAP Fault.

## 2. Dữ liệu mẫu: ba đơn hàng, ba trạng thái của `note`

Giả sử ứng dụng nhận một payload XML `SearchOrdersResponse` dưới SOAP Body:

```xml
<ord:SearchOrdersResponse
    xmlns:ord="https://example.org/orders/v1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <ord:order>
    <ord:id>ORD-000123</ord:id>
    <ord:amount currency="VND">249000.00</ord:amount>
    <ord:paid>true</ord:paid>
    <ord:note xsi:nil="true"/>
  </ord:order>
  <ord:order>
    <ord:id>ORD-000124</ord:id>
    <ord:amount currency="USD">12.50</ord:amount>
    <ord:paid>false</ord:paid>
    <ord:note/>
  </ord:order>
  <ord:order>
    <ord:id>ORD-000125</ord:id>
    <ord:amount currency="VND">100000.00</ord:amount>
    <ord:paid>1</ord:paid>
    <!-- Không có phần tử note -->
  </ord:order>
</ord:SearchOrdersResponse>
```

Trong ví dụ này, `ord:order` lặp ba lần. Element `note` của đơn thứ nhất có `xsi:nil`; đơn thứ hai có `note` rỗng; đơn thứ ba hoàn toàn không có `note`. Đây là **ba trạng thái dữ liệu khác nhau** và thường cần quy tắc nghiệp vụ khác nhau.

### 2.1. Mô tả XSD tương ứng

Một phần schema theo XML Schema 1.0 có thể viết:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:tns="https://example.org/orders/v1"
           targetNamespace="https://example.org/orders/v1"
           elementFormDefault="qualified"
           attributeFormDefault="unqualified">

  <xs:complexType name="AmountType">
    <xs:simpleContent>
      <xs:extension base="xs:decimal">
        <xs:attribute name="currency"
                      type="xs:token"
                      use="required"/>
      </xs:extension>
    </xs:simpleContent>
  </xs:complexType>

  <xs:complexType name="OrderType">
    <xs:sequence>
      <xs:element name="id" type="xs:string"/>
      <xs:element name="amount" type="tns:AmountType"/>
      <xs:element name="paid" type="xs:boolean"/>
      <xs:element name="note"
                  type="xs:string"
                  minOccurs="0"
                  nillable="true"/>
    </xs:sequence>
  </xs:complexType>

  <xs:element name="SearchOrdersResponse">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="order"
                    type="tns:OrderType"
                    minOccurs="0"
                    maxOccurs="unbounded"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
```

Các quy tắc quan trọng:

| Khai báo | Ý nghĩa trong XML |
|---|---|
| `order minOccurs="0" maxOccurs="unbounded"` | Danh sách có thể rỗng hoặc chứa nhiều đơn |
| `id`, `amount`, `paid` mặc định `minOccurs="1"` | Mỗi order phải chứa đúng một element mỗi loại |
| `note minOccurs="0"` | Element `note` có thể không xuất hiện |
| `note nillable="true"` | Khi có mặt, `note` có thể mang `xsi:nil="true"` |
| `paid type="xs:boolean"` | Lexical value hợp lệ gồm `true`, `false`, `1`, `0` |
| `amount` mở rộng `xs:decimal` | Nội dung văn bản là số thập phân, có attribute `currency` |
| `attributeFormDefault="unqualified"` | Attribute cục bộ `currency` ở XML instance không có prefix namespace |

**Giới hạn cố ý:** schema trên minh họa cardinality và kiểu dữ liệu, chưa giới hạn pattern của `id`, enum `currency` hay số tiền không âm. Nếu cần các ràng buộc đó, hãy bổ sung kiểu XSD và quản lý thay đổi hợp đồng; đừng tự nhận một parser Java là đã kiểm tra toàn bộ chính sách nghiệp vụ.

## 3. Ngữ cảnh XPath và namespace: đúng node trước khi đọc giá trị

XPath Java JAXP phổ biến sử dụng ngữ nghĩa **XPath 1.0**. Với XML có namespace, tên phần tử không chỉ là local name: QName của root là `{https://example.org/orders/v1}SearchOrdersResponse`.

Nếu context node là **Document**, đường dẫn tuyệt đối có thể là:

```xpath
/ord:SearchOrdersResponse/ord:order
```

Nếu context node là chính element `SearchOrdersResponse` được Spring-WS chuyển cho handler, đường dẫn tương đối nên là:

```xpath
./ord:order
```

Nếu context node là một element `ord:order`, đường dẫn đọc mã đơn là:

```xpath
./ord:id
```

**Đừng sử dụng tùy tiện `//ord:order`**: nó tìm descendant trong phạm vi context và có thể bắt cả các element cùng tên bên trong cấu trúc con. Trong hợp đồng có dữ liệu lồng nhau, dùng một path tương đối xác định và ngắn thường dễ kiểm soát hơn.

### 3.1. Prefix XPath độc lập prefix trong XML

Một tài liệu có thể dùng `ord:order`, `o:order` hoặc default namespace mà vẫn cùng URI. Biểu thức XPath dùng `ord` được đúng khi chúng ta đăng ký:

```text
XPath prefix "ord" -> https://example.org/orders/v1
```

Không cần XML source sử dụng đúng chữ `ord`. Nhưng nếu biểu thức viết `./order` **không có prefix**, nó tìm element **không namespace** trong XPath 1.0, thường không khớp dữ liệu SOAP nghiệp vụ có namespace.

Attribute cục bộ `currency` ở ví dụ không mang namespace, nên dùng `@currency`. Attribute `xsi:nil` thuộc namespace XML Schema Instance, nên dùng `@xsi:nil` sau khi đăng ký prefix `xsi`.

### 3.2. Tránh `local-name()` như giải pháp mặc định

Biểu thức:

```xpath
//*[local-name()='order']
```

có thể khớp cả element `order` của namespace **khác**; việc mất ràng buộc namespace làm tăng nguy cơ đọc sai dữ liệu. Chỉ cân nhắc `local-name()` cho một chiến lược tương thích đã được định nghĩa, kết hợp kiểm tra namespace rõ ràng. Mặc định nên dùng QName.

### 3.3. Vị trí `[1]` có ý nghĩa

Trong XPath 1.0:

```xpath
(/ord:SearchOrdersResponse/ord:order)[1]
```

lấy **đơn hàng đầu tiên** trong toàn bộ tập kết quả. Trong khi:

```xpath
//ord:order[1]
```

có thể lấy **các `order` đầu tiên của nhiều parent khác nhau** vì predicate ràng buộc theo mỗi bước chọn; không phải cách viết thay thế tổng quát cho việc «lấy một kết quả đầu tiên». Nếu muốn xử lý tất cả các đơn, **không gắn `[1]`**.

## 4. Trả về kiểu nào từ Java XPath?

Java cung cấp `javax.xml.xpath.XPath`, `XPathExpression` và các kiểu trả về khai báo bởi `XPathConstants`. Dù JAXB ở Spring Boot 3 dùng `jakarta.xml.bind`, **XPath vẫn nằm trong `javax.xml.xpath` thuộc JDK**, không đổi thành `jakarta.xml.xpath`.

| `XPathConstants` | Java object thông dụng | Dùng khi nào |
|---|---|---|
| `NODE` | `org.w3c.dom.Node` hoặc `null` | Cần một node và muốn biết nó có tồn tại không |
| `NODESET` | `org.w3c.dom.NodeList` | Có thể có 0/1/nhiều node; cần lặp hoặc kiểm tra số lượng |
| `STRING` | `java.lang.String` | Đã xác định cardinality hoặc cần kết quả của XPath string expression |
| `NUMBER` | `java.lang.Double` | Tính toán kiểu number() theo XPath 1.0; **không dùng trực tiếp cho tiền tệ** |
| `BOOLEAN` | `java.lang.Boolean` | Dùng `exists-like boolean(node-set)`, điều kiện XPath hoặc so sánh rõ |

### 4.1. Điều gì xảy ra khi kết quả rỗng?

Giả sử trên một `ord:order` không có `note`:

```java
Node n = (Node) xpath.evaluate(
    "./ord:note", order, XPathConstants.NODE);        // null

NodeList list = (NodeList) xpath.evaluate(
    "./ord:note", order, XPathConstants.NODESET);     // length == 0

String text = (String) xpath.evaluate(
    "./ord:note", order, XPathConstants.STRING);      // ""

Double value = (Double) xpath.evaluate(
    "./ord:note", order, XPathConstants.NUMBER);      // NaN

Boolean exists = (Boolean) xpath.evaluate(
    "boolean(./ord:note)", order, XPathConstants.BOOLEAN); // false
```

Đối với `note` **có tồn tại nhưng rỗng**, `NODE` **khác null**, `NODESET` có độ dài 1, nhưng `STRING` vẫn trả `""`. Với `note xsi:nil="true"`, phần nội dung text cũng có thể là `""`. Nếu chỉ đọc `String`, cả ba có thể bị nhập nhằng.

**Kết luận quan trọng:** nếu ý nghĩa nghiệp vụ phụ thuộc việc element có tồn tại hay không, lấy `NODE`/`NODESET` **trước khi** đọc string.

### 4.2. Chuyển kiểu nhiều kết quả sang scalar

Trong XPath 1.0, khi dùng một node-set làm string, XPath lấy **string-value của node đầu tiên theo document order**. Khi chuyển một node-set thành number, giá trị string được chuyển tiếp thành số; giá trị không phải số tạo ra `NaN`.

Ví dụ:

```java
String firstId = (String) xpath.evaluate(
    "./ord:order/ord:id", responseRoot, XPathConstants.STRING);
```

Kết quả là `ORD-000123`, **không phải ba mã đơn nối lại**. Nếu đây là response tìm kiếm, đọc scalar làm mất hai đơn còn lại.

**Quy tắc:** để đọc collection, dùng `NODESET`; để đọc một trường đơn trị, kiểm tra số node có đúng 1 không rồi mới lấy text.

### 4.3. `BOOLEAN` không đọc nội dung lexical của phần tử

Một lỗi nguy hiểm:

```java
Boolean paid = (Boolean) xpath.evaluate(
    "boolean(./ord:paid)", order, XPathConstants.BOOLEAN);
```

Nếu element `paid` tồn tại và text là `false`, kết quả **vẫn là `true`**. Biểu thức trên hỏi **element có tồn tại?**, không hỏi **element có chứa giá trị boolean true?**.

Có thể viết XPath so sánh rõ:

```xpath
normalize-space(./ord:paid) = 'true' or
normalize-space(./ord:paid) = '1'
```

Tuy nhiên, phép so sánh này trả `false` cả cho `false` hợp lệ lẫn giá trị không hợp lệ. Khi cần báo lỗi rõ, nên đọc text, kiểm tra lexical value và chuyển kiểu bằng Java như mục 8.

## 5. Tạo một DOM parser có namespace và chặn XXE

Trong Spring-WS, SOAP message thường đã được framework phân tích thành XML trước khi đến endpoint; không phải mọi handler đều cần tự tạo DOM parser. Nhưng khi nhận XML qua file, integration adapter hoặc unit test, phải dùng parser có cấu hình an toàn.

Ví dụ Java 17+:

```java
import java.io.InputStream;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Document;

public final class SafeXml {
    private SafeXml() {}

    public static Document parse(InputStream input) throws Exception {
        DocumentBuilderFactory factory =
            DocumentBuilderFactory.newInstance();

        factory.setNamespaceAware(true);
        factory.setFeature(
            XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setFeature(
            "http://apache.org/xml/features/disallow-doctype-decl", true);
        factory.setFeature(
            "http://xml.org/sax/features/external-general-entities", false);
        factory.setFeature(
            "http://xml.org/sax/features/external-parameter-entities", false);
        factory.setXIncludeAware(false);
        factory.setExpandEntityReferences(false);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        return factory.newDocumentBuilder().parse(input);
    }
}
```

Ví dụ chủ động **fail closed**: nếu XML parser/provider không hỗ trợ một thiết lập an toàn cần thiết, đoạn code sẽ báo lỗi cấu hình thay vì lặng lẽ chấp nhận XML không được bảo vệ. Trên các stack JDK/provider khác nhau, cần kiểm thử những features/properties thực sự hỗ trợ.

Phải thực hiện cả các biện pháp ngoài parser:

- Giới hạn kích thước SOAP/HTTP body, số element, độ sâu và thời gian xử lý tại gateway/server.
- Không tải DTD, external entity, schema imports từ địa chỉ không tin cậy.
- Không parse lại toàn bộ Envelope chỉ để đọc vài child elements khi Spring-WS đã cung cấp payload XML.
- Không log raw XML chứa dữ liệu cá nhân, credential hoặc WS-Security Header.
- Phân quyền SOAP operation và xác minh TLS/WS-Security riêng; XPath không tự bảo vệ thông điệp.

XML parser an toàn giúp giảm XXE, nhưng **không thay thế XSD validation** hay business validation.

## 6. Đăng ký NamespaceContext cho XPath

JAXP không tự hiểu prefix `ord` hay `xsi` từ biểu thức nếu chưa được đăng ký. Có thể tạo một `XPath` mới cho mỗi lần xử lý request.

```java
import java.util.Collections;
import java.util.Iterator;
import javax.xml.XMLConstants;
import javax.xml.namespace.NamespaceContext;
import javax.xml.xpath.XPath;
import javax.xml.xpath.XPathFactory;

public final class OrderXPath {
    public static final String NS =
        "https://example.org/orders/v1";

    private OrderXPath() {}

    public static XPath create() {
        XPath xpath = XPathFactory.newInstance().newXPath();
        xpath.setNamespaceContext(new NamespaceContext() {
            @Override
            public String getNamespaceURI(String prefix) {
                if (prefix == null) {
                    throw new IllegalArgumentException("prefix");
                }
                return switch (prefix) {
                    case "ord" -> NS;
                    case "xsi" ->
                        XMLConstants.W3C_XML_SCHEMA_INSTANCE_NS_URI;
                    case "xml" -> XMLConstants.XML_NS_URI;
                    case "xmlns" -> XMLConstants.XMLNS_ATTRIBUTE_NS_URI;
                    default -> XMLConstants.NULL_NS_URI;
                };
            }

            @Override
            public String getPrefix(String uri) {
                if (NS.equals(uri)) return "ord";
                if (XMLConstants.W3C_XML_SCHEMA_INSTANCE_NS_URI.equals(uri))
                    return "xsi";
                if (XMLConstants.XML_NS_URI.equals(uri)) return "xml";
                if (XMLConstants.XMLNS_ATTRIBUTE_NS_URI.equals(uri))
                    return "xmlns";
                return null;
            }

            @Override
            public Iterator<String> getPrefixes(String uri) {
                String prefix = getPrefix(uri);
                return prefix == null
                    ? Collections.emptyIterator()
                    : Collections.singleton(prefix).iterator();
            }
        });
        return xpath;
    }
}
```

Code trên phù hợp Java 17+, sử dụng switch expression. Nếu dự án yêu cầu Java cũ hơn, có thể thay bằng `if/else`; ngữ nghĩa namespace không đổi.

Một số lưu ý:

- Prefix trong biểu thức là **bí danh do mã đọc XML chọn**; không cần giống prefix của XML source.
- `XPath` là đối tượng có state (resolver/namespace context) và JDK không cam kết thread-safe/reentrant. Để dễ kiểm soát, không chia sẻ một `XPath` mutable singleton giữa nhiều request thread.
- `XPathExpression` biên dịch sẵn có lợi cho các query cố định, nhưng phải quản lý thread-safety theo provider; không mặc nhiên coi nó an toàn để dùng chung giữa threads.
- Với expression cố định và payload nhỏ, tạo `XPath` mỗi lần thường dễ đọc, dễ kiểm thử. Nếu tối ưu bằng caching, phải đo và có concurrency tests.

## 7. Nhiều kết quả: dùng `NODESET` và kiểm tra cardinality

### 7.1. Lấy danh sách tất cả các đơn

Giả sử `responseRoot` là `Element` chứa `SearchOrdersResponse`:

```java
XPath xpath = OrderXPath.create();

NodeList orders = (NodeList) xpath.evaluate(
    "./ord:order",
    responseRoot,
    XPathConstants.NODESET
);

for (int i = 0; i < orders.getLength(); i++) {
    Element order = (Element) orders.item(i);
    String id = (String) xpath.evaluate(
        "./ord:id", order, XPathConstants.STRING);
    System.out.println(id);
}
```

Kết quả mẫu:

```text
ORD-000123
ORD-000124
ORD-000125
```

Không dùng `orders.item(0)` nếu hợp đồng cho phép nhiều kết quả và mục đích là xử lý tất cả. Khi `NodeList` có độ dài 0, vòng `for` không chạy; cần chủ động quyết định danh sách rỗng là một kết quả hợp lệ hay một lỗi nghiệp vụ.

`NodeList` của DOM **không phải `List<Node>` của Java Collections**: nó có `getLength()` và `item(i)`, không có `stream()`/`get(i)` mặc định.

### 7.2. Ràng buộc 0, 1 hoặc N kết quả

| Kỳ vọng theo XSD/contract | XPath result | Xử lý phù hợp |
|---|---|---|
| Chính xác 1 (`minOccurs=1`, `maxOccurs=1`) | `NODESET` có length 0 | Báo lỗi thiếu required element |
| Chính xác 1 | `NODESET` có length 2 | Báo lỗi trùng/lặp ngoài hợp đồng |
| 0 hoặc 1 | 0 kết quả | Trạng thái **absent**, không phải chuỗi rỗng |
| 0 hoặc 1 | 1 kết quả | Xử lý text/nil tùy metadata |
| 0 hoặc N (collection) | 0 kết quả | Trả collection rỗng nếu nghiệp vụ cho phép |
| 0 hoặc N | N kết quả | Duyệt, kiểm tra từng node và giới hạn tài nguyên |
| Ít nhất 1 | 0 kết quả | Lỗi cardinality; không silently fallback |

**Đừng dùng `XPathConstants.NODE` như một cách «lấy một» khi hợp đồng yêu cầu đúng một element**: nếu tài liệu sai và có nhiều element, việc chỉ lấy node đầu có thể che mất vi phạm cardinality. Dùng `NODESET`, kiểm tra length rồi mới đọc.

### 7.3. Hàm XPath `count()`

```java
Double count = (Double) xpath.evaluate(
    "count(./ord:order)",
    responseRoot,
    XPathConstants.NUMBER
);
```

Kết quả là `3.0` theo kiểu `Double`, không phải `int`. Để xử lý danh sách thực tế, `NodeList#getLength()` thuận tiện hơn và không cần convert từ floating point. `count()` phù hợp cho predicate hoặc thống kê nhỏ, nhưng không dùng nó thay thế việc kiểm tra giới hạn kích thước payload.

### 7.4. Chọn theo điều kiện nhưng không bỏ quên nhiều kết quả

```xpath
./ord:order[ord:paid='true' or ord:paid='1']
```

Biểu thức trả tất cả order có text `paid` đúng hai lexical value trên; dùng `NODESET` để đọc danh sách. Tuy nhiên, nếu trường có thể bị thiếu, có khoảng trắng hoặc sai schema, nên validate cấu trúc/lexical value trước. Một XPath predicate chỉ lọc kết quả; **nó không báo các phần tử khác có dữ liệu lỗi**.

### 7.5. Chọn giá trị theo index có chủ đích

```xpath
./ord:order[position() = 2]
```

XPath position là **1-based**, còn `NodeList#item(i)` là **0-based**. Chỉ dùng index khi hợp đồng và nghiệp vụ thực sự có thứ tự; đừng dùng «đơn đầu tiên» thay cho một khóa tra cứu ổn định.

## 8. Thiếu, rỗng, nil, whitespace: bốn trạng thái cần tách

Một optional element có thể có những tình huống sau:

| XML | Có node? | Text | `xsi:nil` | Ý nghĩa nên xử lý |
|---|---|---|---|---|
| Không có `note` | Không | Không áp dụng | Không | **ABSENT** |
| `<ord:note/>` | Có | `""` | Không | **EMPTY** |
| `<ord:note> </ord:note>` | Có | Một dấu cách | Không | **TEXT/WHITESPACE**, tùy chính sách |
| `<ord:note xsi:nil="true"/>` | Có | Thường rỗng | True | **NIL** |
| `<ord:note>Giao buổi chiều</ord:note>` | Có | Nội dung text | Không | **VALUE** |

Một schema có `minOccurs="0" nillable="true"` cho phép vừa **vắng mặt**, vừa **nil**; nó không nói hai trường hợp có cùng ý nghĩa nghiệp vụ. `xsi:nil="true"` chỉ hợp lệ nếu element được khai báo `nillable="true"` và đáp ứng các ràng buộc XSD khác.

### 8.1. Đừng đọc optional element bằng `STRING` trước

```java
// Không đủ nếu cần phân biệt absent và empty:
String note = xpath.evaluate("./ord:note", order);
```

Nếu `note` vắng mặt, `note` rỗng hoặc `note` nil, cách đọc trên thường cho kết quả `""`. Thay vào đó:

```java
NodeList found = (NodeList) xpath.evaluate(
    "./ord:note", order, XPathConstants.NODESET);

if (found.getLength() == 0) {
    // ABSENT
} else if (found.getLength() > 1) {
    throw new IllegalArgumentException("Duplicate note elements");
} else {
    Element noteElement = (Element) found.item(0);
    // Kiểm tra xsi:nil trước khi đọc text.
}
```

### 8.2. Kiểm tra `xsi:nil` theo namespace

```java
String nil = noteElement.getAttributeNS(
    XMLConstants.W3C_XML_SCHEMA_INSTANCE_NS_URI, "nil");

boolean isNil = "true".equals(nil) || "1".equals(nil);
```

Trong XML Schema, kiểu lexical boolean có `true`, `false`, `1` và `0`. Với `xsi:nil`, `true` và `1` biểu diễn nil; `false` và `0` nghĩa không nil. Nếu attribute có giá trị khác, phải **báo lỗi XML không hợp lệ** theo schema, thay vì silently coi là false.

`getAttributeNS(...)` trả chuỗi rỗng khi không có attribute; nếu cần phân biệt «attribute vắng mặt» và «attribute hiện diện nhưng rỗng», dùng `hasAttributeNS(...)`.

### 8.3. Có nên `trim()` dữ liệu?

Không tự động trim mọi `xs:string`: whitespace có thể mang ý nghĩa. Với `xs:token`, XML Schema chuẩn hóa whitespace theo quy tắc `collapse`, nhưng xử lý Java trực tiếp chưa chắc áp dụng đúng như schema-aware validation.

Nên:
 
1. Giữ nguyên text khi đọc nếu hợp đồng không nói phải chuẩn hóa.
2. Dùng quy tắc cụ thể cho từng kiểu: mã định danh có thể từ chối whitespace, số có thể trim lexical input trong xử lý nội bộ.
3. Phân biệt **empty** (độ dài 0) với **blank** (toàn whitespace) nếu nghiệp vụ cần.
4. Dùng schema validation để xác minh lexical value hợp đồng, không áp dụng normalization tùy ý để che lỗi.

## 9. Chuyển kiểu XPath: số, boolean, ngày và enum

### 9.1. `NUMBER` là `Double`, không phải `BigDecimal`

```java
Double amount = (Double) xpath.evaluate(
    "./ord:amount", order, XPathConstants.NUMBER);
```

Kết quả là `Double`, dễ gặp vấn đề biểu diễn dấu phẩy động và precision. Đối với tiền tệ, **đọc text từ element đã xác nhận tồn tại rồi dùng `BigDecimal`**:

```java
Element amountElement = requiredElement(
    xpath, order, "./ord:amount");

String lexical = amountElement.getTextContent().trim();
if (lexical.isEmpty()) {
    throw new IllegalArgumentException("Empty amount");
}

BigDecimal amount;
try {
    amount = new BigDecimal(lexical);
} catch (NumberFormatException e) {
    throw new IllegalArgumentException("Invalid decimal", e);
}
```

`requiredElement(...)` là helper sẽ được định nghĩa trong mục 10. Dùng `BigDecimal` giữ độ chính xác thập phân, nhưng **chưa thay thế XSD validation**: Java BigDecimal có thể chấp nhận một số dạng lexical mà `xs:decimal` không cho phép, hoặc chưa kiểm tra facets như `totalDigits`/`fractionDigits`/`minInclusive`.

Nếu giá trị số được dùng trong nghiệp vụ thanh toán, nên:

- Xác minh lexical format theo XSD trước.
- Dùng `BigDecimal`, giữ precision/scale và chính sách rounding rõ ràng.
- Kiểm tra currency, giới hạn số tiền và quy tắc nghiệp vụ.
- Không dùng `Double.parseDouble` hoặc `(double)` rồi chuyển ngược sang `BigDecimal` để mong lấy lại giá trị chính xác.

### 9.2. `NaN` không phải «giá trị thiếu» an toàn

Khi dùng XPath `number()` với text không phải số hoặc một node-set rỗng, XPath 1.0 có thể cho `NaN` (*Not a Number*). Trong Java:

```java
Double n = (Double) xpath.evaluate(
    "number(./ord:amount)", order, XPathConstants.NUMBER);

if (n.isNaN() || n.isInfinite()) {
    throw new IllegalArgumentException(
        "Invalid numeric XPath result");
}
```

**Không** biến `NaN` thành 0 rồi tiếp tục thanh toán hoặc tổng hợp số tiền. Cũng không coi `Double.NaN` là một null sentinel phù hợp với domain. Cần biết element thiếu hay lexical sai trước khi chuyển số.

### 9.3. Boolean theo `xs:boolean`

XML Schema boolean cho phép `true`, `false`, `1`, `0`. Java `Boolean.parseBoolean("1")` trả `false`, vì thế **không tương đương** với bộ chuyển đổi `xs:boolean`.

Dùng helper rõ ràng:

```java
static boolean parseXsBoolean(String text) {
    return switch (text.trim()) {
        case "true", "1" -> true;
        case "false", "0" -> false;
        default -> throw new IllegalArgumentException(
            "Invalid xs:boolean value");
    };
}
```

Ví dụ trả `true` cho `1` và `false` cho `0`; giá trị `yes`, `Y` hay `TRUE` bị từ chối thay vì đoán. Nếu schema quy định giá trị bắt buộc, thiếu `paid` phải được kiểm tra **trước** khi gọi helper.

### 9.4. Số nguyên và giới hạn kiểu

XPath `NUMBER` trả `Double`, không phải `Integer`/`Long`. Nếu quantity được định nghĩa là `xs:positiveInteger`, đọc text, kiểm tra XSD trước rồi chuyển bằng:

```java
BigInteger quantity = new BigInteger(rawQuantity.trim());
if (quantity.signum() <= 0) {
    throw new IllegalArgumentException("Quantity must be positive");
}
```

Sau đó chỉ dùng `quantity.intValueExact()` khi nghiệp vụ cần `int` và biết chắc giá trị nằm trong giới hạn; `intValue()` có thể làm mất dữ liệu nếu quá lớn.

### 9.5. Date, dateTime và timezone

Nếu XML có:

```xml
<ord:createdDate xmlns:ord="https://example.org/orders/v1">2026-11-27</ord:createdDate>
<ord:createdAt xmlns:ord="https://example.org/orders/v1">2026-11-27T09:30:00Z</ord:createdAt>
```

có thể dùng:

```java
LocalDate date = LocalDate.parse(createdDateText);
OffsetDateTime timestamp =
    OffsetDateTime.parse(createdAtText);
```

Đây là cách phù hợp khi **hợp đồng yêu cầu ISO date và dateTime có offset**. XML Schema `xs:dateTime` có những trường hợp timezone được bỏ qua hoặc lexical/canonical forms khác; không giả định `OffsetDateTime.parse` bao phủ mọi giá trị XSD hợp lệ. Nếu hợp đồng cần đầy đủ ngữ nghĩa XML Schema, dùng JAXB/`XMLGregorianCalendar` hoặc parser chuyên biệt và quy định rõ chính sách timezone.

Không dùng `new Date(string)` hoặc default system timezone để suy đoán thời điểm phát sinh đơn hàng. Timezone phải được công bố và kiểm thử.

### 9.6. Enum và mã nghiệp vụ

Nếu status là một enum, đọc `String` rồi kiểm tra thuộc danh sách được chấp thuận:

```java
String status = requiredElement(
    xpath, order, "./ord:status").getTextContent();

switch (status) {
    case "NEW", "CONFIRMED", "CANCELLED" -> { /* hợp lệ */ }
    default -> throw new IllegalArgumentException(
        "Unsupported order status");
}
```

Ví dụ giả định XSD hợp đồng đã công bố ba giá trị. Không đưa giá trị mới vào Java enum rồi cho phép SOAP response trả nó trước khi đánh giá tương thích với client đã sinh enum từ WSDL/XSD cũ.

## 10. Bộ đọc DOM/XPath mẫu: xử lý đủ 0/1/N và bốn trạng thái note

Dưới đây là ví dụ Java 17+ **tự chứa ở mức lớp xử lý DOM**. Input là element `SearchOrdersResponse` đã được parse an toàn và nên được XSD validate. Bộ đọc chủ động kiểm tra cardinality, kiểu số/boolean và metadata `xsi:nil`. Có thể dùng trong SOAP client nhận `DOMSource` hoặc trong endpoint đọc XML trực tiếp.

### 10.1. Class minh họa

```java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import javax.xml.XMLConstants;
import javax.xml.xpath.XPath;
import javax.xml.xpath.XPathConstants;
import javax.xml.xpath.XPathExpressionException;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;

public final class OrderXmlReader {
    private static final String NS =
        "https://example.org/orders/v1";

    private OrderXmlReader() {}

    public enum NoteState { ABSENT, NIL, EMPTY, VALUE }

    public record NoteValue(NoteState state, String text) {}

    public record OrderRow(
        String id,
        BigDecimal amount,
        String currency,
        boolean paid,
        NoteValue note
    ) {}

    public static List<OrderRow> read(Element responseRoot)
            throws XPathExpressionException {

        if (!NS.equals(responseRoot.getNamespaceURI())
                || !"SearchOrdersResponse"
                    .equals(responseRoot.getLocalName())) {
            throw new IllegalArgumentException(
                "Unexpected response root QName");
        }

        XPath xpath = OrderXPath.create();
        NodeList list = (NodeList) xpath.evaluate(
            "./ord:order", responseRoot, XPathConstants.NODESET);

        List<OrderRow> rows = new ArrayList<>();
        for (int i = 0; i < list.getLength(); i++) {
            Element order = (Element) list.item(i);

            String id = requiredElement(
                xpath, order, "./ord:id").getTextContent();

            Element amountNode = requiredElement(
                xpath, order, "./ord:amount");

            if (!amountNode.hasAttribute("currency")) {
                throw new IllegalArgumentException(
                    "Missing currency attribute");
            }
            String currency = amountNode.getAttribute("currency");
            if (currency.isBlank()) {
                throw new IllegalArgumentException(
                    "Blank currency attribute");
            }

            BigDecimal amount;
            try {
                amount = new BigDecimal(
                    amountNode.getTextContent().trim());
            } catch (NumberFormatException e) {
                throw new IllegalArgumentException(
                    "Invalid amount for " + id, e);
            }

            String paidText = requiredElement(
                xpath, order, "./ord:paid").getTextContent();
            boolean paid = parseXsBoolean(paidText);

            rows.add(new OrderRow(
                id, amount, currency, paid, readNote(xpath, order)));
        }

        return List.copyOf(rows);
    }

    private static Element requiredElement(
            XPath xpath, Node base, String expression)
            throws XPathExpressionException {

        NodeList nodes = (NodeList) xpath.evaluate(
            expression, base, XPathConstants.NODESET);

        if (nodes.getLength() != 1) {
            throw new IllegalArgumentException(
                expression + " must occur exactly once, found "
                    + nodes.getLength());
        }
        return (Element) nodes.item(0);
    }

    private static NoteValue readNote(XPath xpath, Element order)
            throws XPathExpressionException {

        NodeList matches = (NodeList) xpath.evaluate(
            "./ord:note", order, XPathConstants.NODESET);

        if (matches.getLength() == 0) {
            return new NoteValue(NoteState.ABSENT, null);
        }
        if (matches.getLength() > 1) {
            throw new IllegalArgumentException(
                "Duplicate optional note element");
        }

        Element element = (Element) matches.item(0);
        String nil = element.getAttributeNS(
            XMLConstants.W3C_XML_SCHEMA_INSTANCE_NS_URI, "nil");

        if ("true".equals(nil) || "1".equals(nil)) {
            return new NoteValue(NoteState.NIL, null);
        }
        if (!nil.isEmpty() && !"false".equals(nil) && !"0".equals(nil)) {
            throw new IllegalArgumentException("Invalid xsi:nil");
        }

        String text = element.getTextContent();
        if (text.isEmpty()) {
            return new NoteValue(NoteState.EMPTY, "");
        }
        return new NoteValue(NoteState.VALUE, text);
    }

    private static boolean parseXsBoolean(String text) {
        return switch (text.trim()) {
            case "true", "1" -> true;
            case "false", "0" -> false;
            default -> throw new IllegalArgumentException(
                "Invalid xs:boolean");
        };
    }
}
```

### 10.2. Ý nghĩa các quyết định trong bộ đọc

- `read(...)` xác minh **root QName** trước khi chọn các `order`. Nếu parser hoặc endpoint gửi nhầm XML ở namespace khác, kết quả không được chấp nhận.
- `NodeList list` cho phép kết quả rỗng hoặc nhiều order, khớp XSD `minOccurs="0" maxOccurs="unbounded"`.
- `requiredElement` dùng `NODESET` và yêu cầu đúng **1** element; không lấy node đầu nếu hợp đồng bị vi phạm.
- `currency` được đọc như **attribute không namespace**; `hasAttribute` phân biệt thiếu với giá trị rỗng.
- `amount` dùng `BigDecimal`, tránh mất precision khi xử lý tiền.
- `paid` chấp nhận đủ bốn lexical value của `xs:boolean`.
- `readNote` trả `ABSENT`, `NIL`, `EMPTY` hoặc `VALUE`, không ép tất cả thành `null`.
- Text chỉ có khoảng trắng được xem là `VALUE` trong ví dụ; nếu nghiệp vụ muốn coi là blank, thêm trạng thái hoặc validation rõ ràng.
- `List.copyOf(rows)` trả kết quả không sửa đổi được theo Java Collections.

**Giới hạn của code mẫu:** việc `xsi:nil="true"` chỉ hợp lệ khi element không mang nội dung theo XSD phải được kiểm tra bởi schema validator. Bộ đọc này không tự xác minh `amount` có thỏa `fractionDigits`, `id` có khớp pattern hay `currency` có trong enum hợp đồng. Trước khi xử lý XML không tin cậy, cần **XSD validation**, giới hạn kích thước và lỗi hiển thị an toàn. Nếu muốn tự kiểm tra mọi ràng buộc bằng Java, bạn đang lặp lại công việc của schema validator và dễ bỏ sót rule.

### 10.3. Cách gọi với Document đã parse an toàn

```java
Document xml = SafeXml.parse(inputStream);
List<OrderXmlReader.OrderRow> orders =
    OrderXmlReader.read(xml.getDocumentElement());

for (OrderXmlReader.OrderRow order : orders) {
    System.out.println(order.id() + " / " + order.amount());
}
```

Cần đặt các class helper vào package phù hợp, bổ sung imports `org.w3c.dom.Document`, `java.io.InputStream`, `java.util.List` và đảm bảo XSD validation trước khi tin dữ liệu. Ví dụ không bao gồm cơ chế tạo `inputStream` từ request HTTP và không tạo một dự án Spring Boot hoàn chỉnh.

## 11. `@XPathParam` của Spring-WS: tiện lợi nhưng cần hiểu chuyển kiểu

Spring-WS hỗ trợ `@XPathParam` để binding kết quả XPath vào tham số của method `@Endpoint`. Annotation `@Namespace` khai báo prefix được sử dụng trong biểu thức XPath.

Ví dụ **minh họa một SOAP operation one-way** (WSDL phải thực sự công bố operation tương ứng):

```java
import org.w3c.dom.NodeList;
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.Namespace;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.XPathParam;

@Endpoint
public class BatchOrdersEndpoint {
    private static final String NS =
        "https://example.org/orders/v1";

    @PayloadRoot(namespace = NS, localPart = "BatchOrdersRequest")
    @Namespace(prefix = "ord", uri = NS)
    public void receive(
        @XPathParam("/ord:BatchOrdersRequest/ord:order")
        NodeList orderNodes,
        @XPathParam("count(/ord:BatchOrdersRequest/ord:order)")
        double count) {

        // Chuyển NodeList thành domain objects và xác minh
        // count/cardinality theo XSD trước khi thực hiện nghiệp vụ.
        if (orderNodes.getLength() != count) {
            throw new IllegalArgumentException(
                "Inconsistent order count");
        }
    }
}
```

Đoạn trên chỉ minh họa injection XPath; một endpoint thực tế cần service xử lý, fault mapping và có thể có response tùy hợp đồng. Không dùng `void` cho operation đã công bố SOAP response nghiệp vụ.

Các kiểu kết quả cốt lõi mà `@XPathParam` hỗ trợ gồm `boolean/Boolean`, `double/Double`, `String`, `Node`, `NodeList`; Spring-WS cũng có thể chuyển đổi thêm type từ chuỗi qua `ConversionService` khi được cấu hình. **Không mặc định** annotation sẽ phân biệt missing/nil/empty hoặc chuyển chính xác mọi `xs:decimal` sang `BigDecimal` trong mọi cấu hình.

### 11.1. Chọn giữa `@XPathParam` và `@RequestPayload Element`

| Nhu cầu | Lựa chọn hợp lý |
|---|---|
| Lấy một XPath boolean/count/node đơn giản | `@XPathParam` khi processor hỗ trợ chữ ký |
| Lấy NodeList lặp với vài thao tác đơn giản | `@XPathParam NodeList` hoặc đọc DOM trực tiếp |
| Phân biệt absent, nil, empty | `@RequestPayload Element` + DOM/XPath explicit |
| Nhiều trường cần cardinality và chuyển kiểu nghiêm | Đọc DOM có helper hoặc sinh JAXB từ XSD |
| Cần tương thích WSDL/XSD và validation chặt | JAXB + schema validation thường dễ duy trì hơn |
| Payload rất lớn, không phù hợp DOM | Cân nhắc StAX/streaming thay vì tạo toàn bộ cây |

Một endpoint có thể nhận `@RequestPayload Element` nếu Spring-WS adapter hiện tại hỗ trợ DOM payload type:

```java
@PayloadRoot(
    namespace = "https://example.org/orders/v1",
    localPart = "BatchOrdersRequest")
public void receive(@RequestPayload Element payload) {
    // Đọc XPath tương đối từ chính payload root.
}
```

Ví dụ `void` chỉ phù hợp khi WSDL định nghĩa one-way. Nếu operation cần response, thêm `@ResponsePayload` cùng return value thuộc loại Spring-WS xử lý được theo hợp đồng. Không đăng ký hai endpoint trùng `@PayloadRoot` trong cùng context nếu chưa có chiến lược định tuyến rõ ràng.

### 11.2. Đừng nhầm ngữ cảnh XPath trong `@XPathParam`

Ví dụ dùng đường dẫn tuyệt đối `/ord:BatchOrdersRequest/ord:order` theo mô hình payload document mà Spring-WS cung cấp cho XPath resolver. Nếu bạn tự nhận `Element payload` rồi gọi JAXP với expression tương đối `./ord:order`, phải đánh giá trên **payload element**, không áp dụng bừa đường dẫn tuyệt đối và tương đối như nhau.

Cần kiểm thử biểu thức trên **phiên bản Spring-WS đang dùng** và xác minh QName/namespace bằng XML fixture, nhất là khi SOAP Body có nhiều element, custom payload root hoặc interceptor làm biến đổi payload.

## 12. XSD validation, nghiệp vụ và SOAP Fault: ba tầng không thay thế nhau

XPath trả kết quả là **query trên XML tree**. Nó không tự chứng minh XML hợp lệ theo hợp đồng.

| Tầng | Kiểm tra | Không tự kiểm tra |
|---|---|---|
| XML parser | Well-formed XML, namespace, policy DTD/entity | Ràng buộc XSD đầy đủ, nghiệp vụ |
| XPath/DOM extractor | Node nào được chọn, cardinality do code kiểm, chuyển kiểu do code kiểm | Toàn bộ XSD facets, WS-Security |
| XSD validator | Element, namespace, order, cardinality, lexical constraints, facet | Đơn hàng có tồn tại, người gọi có quyền không |
| Domain service | Quy tắc nghiệp vụ, tồn tại, quyền, idempotency | SOAP Envelope/security transport nếu không tích hợp rõ |
| Spring-WS security/transport | TLS/mTLS, WS-Security, chữ ký, token, timestamp theo policy | Tính đúng nghiệp vụ của số tiền |

Trong Spring-WS có `PayloadValidatingInterceptor` để validate SOAP Body đối chiếu XSD trước khi gọi endpoint, và có thể kiểm tra response theo cấu hình. Đừng chỉ dựa vào `readOrders(...)` vì XPath có thể bỏ qua các element mà code chưa hề kiểm tra.

### 12.1. Schema validation JAXP độc lập

Có thể kiểm chứng một XML payload trước khi đọc XPath:

```java
SchemaFactory schemaFactory = SchemaFactory.newInstance(
    XMLConstants.W3C_XML_SCHEMA_NS_URI);

schemaFactory.setFeature(
    XMLConstants.FEATURE_SECURE_PROCESSING, true);
schemaFactory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
schemaFactory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

Schema schema = schemaFactory.newSchema(
    new File("orders.xsd"));
Validator validator = schema.newValidator();
validator.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
validator.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

validator.validate(
    new DOMSource(document.getDocumentElement()));
```

Ví dụ cần imports các class từ `javax.xml.validation`, `javax.xml.transform.dom.DOMSource`, `javax.xml.XMLConstants` và `java.io.File`. Nếu schema dùng `xs:import`/`xs:include`, phải cung cấp bộ resolver/catalog đáng tin để không cần tải nguồn tùy ý qua internet. Nếu provider không hỗ trợ thuộc tính bảo vệ, fail closed và sửa cấu hình môi trường.

Khi validation phát hiện XML không hợp lệ, application nên phân loại lỗi đầu vào và ánh xạ sang SOAP Fault phù hợp policy. Tránh trả raw parser exception, file paths, stack traces hoặc nội dung cá nhân cho client.

### 12.2. Những lỗi nào nên được phản ánh thành SOAP Fault?

Ví dụ:
 
- Payload thiếu element bắt buộc, sai `xsi:nil` hoặc sai namespace → lỗi schema/request.
- XPath có 2 element nhưng hợp đồng yêu cầu đúng 1 → lỗi hợp đồng/request.
- Số tiền không parse được hoặc currency không hợp lệ → schema/request hoặc business rule tùy ràng buộc.
- Không tìm thấy đơn hàng nhưng ID hợp lệ → lỗi nghiệp vụ.
- Runtime XPath expression bị sai vì developer viết nhầm prefix → **lỗi triển khai nội bộ**, không giả mạo thành lỗi người dùng.
- Request thiếu WS-Security chữ ký hoặc bị từ chối TLS client certificate → xử lý theo security policy/transport, không đến nghiệp vụ.

SOAP 1.1 và SOAP 1.2 có mô hình Fault khác nhau; mã lỗi, HTTP status và detail XML phải phù hợp binding/hợp đồng. Những xử lý đó do fault resolver/transport pipeline quản lý, không tự xuất XML lỗi bằng string concatenation.

## 13. Hiệu năng và bảo mật khi dùng XPath trực tiếp

### 13.1. DOM và NodeList tốn bộ nhớ theo kích thước XML

DOM materialize toàn bộ cây. Với SOAP response có vài chục order, điều này thường dễ sử dụng. Với hàng trăm nghìn dòng dữ liệu hoặc payload không giới hạn, dùng DOM/XPath có thể gây allocation lớn, GC pressure và latency cao.

Cần:

- Giới hạn kích thước body và số lượng order theo hợp đồng.
- Dùng streaming XML (StAX/SAX) khi phải xử lý tài liệu rất lớn.
- Chỉ compile/evaluate các XPath cần thiết, tránh lặp query toàn bộ tree trong mỗi item.
- Đưa giới hạn vào gateway/transport trước khi tạo DOM; không dựa hoàn toàn vào `NodeList#getLength()` sau khi bộ nhớ đã bị dùng.
- Tránh `//*` hay `//ord:order` trên cây lớn nếu đường dẫn cụ thể đủ dùng.

### 13.2. Không xây XPath expression bằng chuỗi không tin cậy

Ví dụ nguy hiểm:

```java
String expression =
    "./ord:order[ord:id='" + userSuppliedId + "']";
```

Nếu `userSuppliedId` chứa dấu nháy hoặc XPath operators, biểu thức có thể bị thay đổi nghĩa. Đây là **XPath injection**, tương tự nguy cơ SQL injection ở tầng truy vấn.

Các cách an toàn hơn:

1. Dùng XPath cố định `./ord:order`, sau đó đọc giá trị `id` và so sánh bằng Java với input đã được kiểm tra.
2. Nếu cần XPath động, dùng `XPathVariableResolver` cho giá trị biến, không nối chuỗi nguồn ngoài vào biểu thức; kiểm soát tên biến và namespace.
3. Duy trì whitelist cho tên field/expression khi business thật sự cần truy vấn linh hoạt.
4. Giới hạn số kết quả, kích thước payload và tài nguyên xử lý.

Tương tự, **không** đưa trực tiếp giá trị bên ngoài vào XML string để tạo SOAP Fault/response mà không dùng serializer an toàn.

### 13.3. Thread-safety và caching

Một `XPath` có resolver và state nội bộ không nên được dùng đồng thời từ nhiều request thread. Cách đơn giản: tạo mới trong mỗi lời gọi extractor. Nếu muốn cache compiled expressions, phải xem contract thread-safety của provider và cân nhắc ThreadLocal hoặc pool có lifecycle rõ; đo trước khi tối ưu. Không giả định việc compile một lần là đã an toàn để share toàn cục.

## 14. Ma trận kiểm thử bắt buộc

Từ XML ở mục 2, tạo các biến thể và kiểm tra parser, schema validator, extractor và SOAP endpoint:

| Ca | Dữ liệu/XML | Kỳ vọng |
|---|---|---|
| Happy path | Ba `order` hợp lệ | Trả 3 rows đúng thứ tự, đúng amount |
| Danh sách rỗng | `<SearchOrdersResponse/>` đúng namespace | `NodeList length=0`, danh sách rỗng |
| Một order | Chỉ `ORD-000123` | Trả đúng một row |
| Nhiều order | Ba hoặc nhiều order | Không mất các item sau item đầu |
| Thiếu required `id` | Bỏ `ord:id` ở một order | Validator/extractor từ chối |
| Trùng required `id` | Hai `ord:id` trong cùng order | Validator/extractor từ chối, không lấy phần tử đầu |
| Thiếu `note` | Không có `ord:note` | `NoteState.ABSENT` |
| `note` rỗng | `<ord:note/>` | `NoteState.EMPTY` |
| `note` nil | `xsi:nil="true"` | `NoteState.NIL` |
| `note` có text | `<ord:note>abc</ord:note>` | `NoteState.VALUE` và text `abc` |
| `note` whitespace | `<ord:note> </ord:note>` | Không tự biến thành ABSENT/NIL |
| `note` trùng | Hai `note` trong một order | Validator/extractor từ chối |
| `xsi:nil` sai lexical | `xsi:nil="yes"` | Validator/extractor từ chối |
| `xsi:nil=true` có text | Nil và nội dung chữ | XSD validator từ chối |
| `paid=true` | Text `true` | Java boolean true |
| `paid=1` | Text `1` | Java boolean true |
| `paid=false` | Text `false` | Java boolean false (không dùng `boolean(node)`) |
| `paid=0` | Text `0` | Java boolean false |
| `paid=YES` | Giá trị không hợp lệ | Từ chối, không silently false |
| `amount=12.50` | Tiền USD | `BigDecimal("12.50")` |
| `amount=bad` | Giá trị không phải decimal | Từ chối, không coi `NaN` là 0 |
| `currency` thiếu | Không có attribute | Từ chối |
| `currency` có namespace sai | `ord:currency="USD"` thay `currency` | Validator/extractor từ chối |
| Root namespace sai | `https://wrong.example/v1` | Từ chối QName, không match theo local-name |
| Payload lớn | Nhiều phần tử vượt giới hạn | Bị chặn bởi limit ở transport/parser |
| XXE/DOCTYPE | XML có DTD/external entity | Parser từ chối |
| XPath injection | ID chứa nháy và XPath syntax | Không làm thay đổi expression được dùng |
| SOAP response sai schema | Element order sai thứ tự | XSD validation từ chối |
| Client khác nền tảng | WSDL contract-first và response hợp lệ | Client có thể đọc 0/1/N kết quả đúng |

### 14.1. JUnit minh họa cho bốn trạng thái

```java
@Test
void distinguishesMissingNilEmptyAndText() throws Exception {
    Document doc = SafeXml.parse(
        new ByteArrayInputStream(xmlFixture.getBytes(StandardCharsets.UTF_8)));

    List<OrderXmlReader.OrderRow> rows =
        OrderXmlReader.read(doc.getDocumentElement());

    assertEquals(3, rows.size());
    assertEquals(OrderXmlReader.NoteState.NIL,
                 rows.get(0).note().state());
    assertEquals(OrderXmlReader.NoteState.EMPTY,
                 rows.get(1).note().state());
    assertEquals(OrderXmlReader.NoteState.ABSENT,
                 rows.get(2).note().state());
    assertEquals(0,
        rows.get(0).amount()
            .compareTo(new BigDecimal("249000.00")));
    assertTrue(rows.get(0).paid());
    assertFalse(rows.get(1).paid());
    assertTrue(rows.get(2).paid()); // "1" theo xs:boolean
}
```

Test minh họa sử dụng JUnit 5; `xmlFixture` là XML mục 2 được nạp trong fixture test; cần imports `ByteArrayInputStream`, `StandardCharsets`, `Document`, `BigDecimal`, `List` và JUnit assertions. Đoạn test này chủ động so `BigDecimal.compareTo` để kiểm tra giá trị; nếu cần kiểm tra scale, thêm assertion cho `scale()` theo quy tắc tiền tệ.

### 14.2. Kiểm thử end-to-end bằng Spring-WS

Một bộ test đầy đủ cần có:

- **Đơn vị:** XPath helpers với `Document`/`Element` fixture.
- **Schema:** XML sai cardinality, lexical value, namespace phải bị từ chối.
- **Spring-WS pipeline:** `MockWebServiceClient` hoặc test client tương đương gửi SOAP payload và xác minh response/fault.
- **HTTP integration:** POST đến servlet/gateway đúng endpoint, SOAPAction và phiên bản SOAP.
- **Bảo mật:** request sai chữ ký, timestamp, cert/token phải không qua domain handler.
- **Interoperability:** client từ stack khác sinh mã từ WSDL và đọc cùng response 0/1/N.

**Cần phân biệt payload context:** trong test DOM/JAXP, có thể đánh giá trên `Document`; trong Spring-WS endpoint có thể chỉ có `Element` là root của SOAP Body payload. Kết quả XPath sẽ khác nếu dùng expression tuyệt đối/tương đối không phù hợp.

## 15. Bài tập tổng hợp

Hãy thiết kế SOAP operation `SearchOrders` có response theo XSD ở mục 2 và thử các yêu cầu:

1. Nhận `SearchOrdersResponse` với 0, 1 hoặc nhiều `ord:order` mà không làm mất dữ liệu.
2. Tạo cấu trúc Java giữ riêng bốn trạng thái `note`: ABSENT, NIL, EMPTY, VALUE.
3. Đối với `amount`, giữ chính xác số thập phân và attribute `currency`; không dùng `double`.
4. Đối với `paid`, hỗ trợ `true/false/1/0` và từ chối `yes`.
5. Cố tình bỏ `id`, nhân đôi `amount` và đổi namespace; kiểm tra lỗi cardinality/QName trước khi gọi nghiệp vụ.
6. Thử XPath `boolean(./ord:paid)` trên element có text `false`; giải thích tại sao trả true.
7. Thử XPath `./ord:order/ord:id` với `STRING` rồi `NODESET`; giải thích tại sao chỉ cách thứ hai trả đủ danh sách.
8. Thêm `@XPathParam` cho một field đơn giản và so sánh với cách đọc `Element` bằng JAXP khi thiếu/nil.
9. Bật schema validation, giới hạn kích thước request, cấm DTD/XXE và đánh giá rủi ro XPath injection.
10. Viết unit/integration tests, kiểm tra SOAP Fault đúng contract và chạy thử client từ công nghệ khác.

### Câu hỏi tự kiểm tra

1. Vì sao `XPathConstants.STRING` không giúp phân biệt `<note/>` với việc không có `note`?
2. `XPathConstants.NODE` khác `NODESET` ở mục đích kiểm tra cardinality thế nào?
3. Khi nào `number(...)` cho `NaN`, và vì sao chuyển `NaN` thành 0 nguy hiểm?
4. XPath `boolean(./paid)` có đọc lexical value `false` không?
5. Vì sao `BigDecimal` tốt hơn `Double` cho `xs:decimal` tiền tệ?
6. Một XPath expression có prefix `ord` có thể đọc element mang prefix `o` trong XML không?
7. Tại sao `@XPathParam` có `String`/`double` không tự bảo đảm các quy tắc XSD?
8. Vì sao `xsi:nil="true"` không tự đồng nghĩa với «không gửi element»?
9. SOAP endpoint có cần tự parse toàn bộ Envelope để đọc một element đã được Spring-WS cung cấp không?
10. Tại sao cần test trên XML fixture độc lập, thay vì chỉ round-trip cùng một implementation?

## 16. Checklist áp dụng trong hệ thống doanh nghiệp

- [ ] Hiểu rõ XSD `minOccurs`, `maxOccurs`, `nillable` và kiểu dữ liệu của các field cần đọc.
- [ ] XPath có namespace mapping đúng, chọn context node phù hợp, tránh `local-name()` quá rộng.
- [ ] Với trường đơn trị, đã kiểm tra số node đúng 1; với collection, đọc đủ `NODESET`.
- [ ] Với optional element, phân biệt ABSENT, NIL, EMPTY, VALUE khi nghiệp vụ yêu cầu.
- [ ] Không dùng `boolean(node-set)` để đọc giá trị `xs:boolean` của element.
- [ ] Không dùng `Double` cho số tiền hoặc số nguyên quá lớn; kiểm tra lexical value và facets bằng XSD.
- [ ] XML parser chặn DTD/XXE, external resources; kích thước payload và tài nguyên được giới hạn.
- [ ] XPath expressions không nối dữ liệu chưa tin cậy; dùng variable resolver hoặc lọc bằng Java.
- [ ] XML được schema validate trước khi xử lý nghiệp vụ; SOAP Fault không lộ dữ liệu nhạy cảm.
- [ ] Spring-WS endpoint, JAXB/client, interceptor, WSDL và SOAP binding được test đúng đường thực thi.
- [ ] Có test 0/1/N, namespace, nil/empty, sai số, nhiều kết quả, bảo mật và client liên thông.

**Ghi nhớ:** XPath là công cụ **chọn node và chuyển kiểu theo ngữ nghĩa XPath**, không phải bộ kiểm tra dữ liệu SOAP hoàn chỉnh. Muốn tích hợp ổn định, hãy **kiểm tra sự tồn tại và số lượng node trước**, đọc lexical value rõ ràng, chuyển sang kiểu Java phù hợp và dùng XSD/WS-Security cùng kiểm thử để bảo vệ hợp đồng đã phê duyệt.

## 17. Tài liệu tham khảo

- [W3C — XML Path Language (XPath) Version 1.0](https://www.w3.org/TR/xpath-10/): node-set, string, number, boolean, position/predicate và quy tắc chuyển kiểu.
- [Oracle JDK — `XPathConstants` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/xpath/XPathConstants.html): kết quả `NODE`, `NODESET`, `STRING`, `NUMBER`, `BOOLEAN`.
- [Oracle JDK — `XPath` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/xpath/XPath.html): biểu thức, namespace context, result conversion và thread-safety.
- [Spring Web Services — `@XPathParam` API](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/server/endpoint/annotation/XPathParam.html): kiểu tham số được hỗ trợ.
- [Spring Web Services — `@Namespace` API](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/server/endpoint/annotation/Namespace.html): ánh xạ prefix cho endpoint XPath.
- [Spring Web Services — Reference Documentation](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/): contract-first, XPathParam, endpoint method, validation, SOAP Fault và security.
- [W3C — XML Schema Part 1: Structures](https://www.w3.org/TR/xmlschema-1/) và [Part 2: Datatypes](https://www.w3.org/TR/xmlschema-2/): cardinality, `nillable`, boolean/decimal và schema validation.
- [OWASP — XML External Entity Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html): phòng ngừa XXE trong XML parsers.
