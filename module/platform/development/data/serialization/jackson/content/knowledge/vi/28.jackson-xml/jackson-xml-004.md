# Quản lý namespace trong dữ liệu XML

XML namespace là cơ chế phân biệt các phần tử và thuộc tính có cùng tên cục bộ nhưng thuộc những vocabulary khác nhau. Trong tích hợp hệ thống, một tài liệu có thể kết hợp namespace của đơn hàng, khách hàng, địa chỉ và metadata của đối tác. Nếu chỉ nhìn vào tên như `id`, `name` hoặc `status`, ta có thể nhầm các phần tử có ý nghĩa hoàn toàn khác nhau.

Jackson XML hỗ trợ ánh xạ namespace thông qua các annotation như `@JacksonXmlRootElement`, `@JacksonXmlProperty` và `@JacksonXmlElementWrapper`. Khi làm việc với namespace, điều quan trọng là hiểu URI namespace, prefix, default namespace và phạm vi áp dụng của chúng. Prefix chỉ là bí danh trong văn bản XML; định danh thực sự là cặp namespace URI và local name.

Bài học này trình bày cách thiết kế DTO cho XML có namespace, cách cấu hình root/element/attribute/collection, cách kiểm tra XML bằng parser namespace-aware và các giới hạn cần lưu ý khi dùng `XmlMapper` trong hợp đồng tích hợp.

## 1. Namespace giải quyết vấn đề gì?

Giả sử một tài liệu XML có cả thông tin đơn hàng và thông tin khách hàng. Cả hai vocabulary đều có thể có phần tử `id`:

~~~xml
<order>
  <id>ORD-1001</id>
  <customer>
    <id>CUS-88</id>
  </customer>
</order>
~~~

Nhìn vào tên cục bộ, `order/id` và `customer/id` có vẻ rõ ràng trong ví dụ nhỏ. Nhưng khi nhiều schema được kết hợp trong một tài liệu lớn, tên trùng có thể gây nhập nhằng. Namespace giúp định danh chúng theo vocabulary:

~~~xml
<o:order xmlns:o="urn:acme:order:v1"
         xmlns:c="urn:acme:customer:v1">
  <o:id>ORD-1001</o:id>
  <c:customer>
    <c:id>CUS-88</c:id>
  </c:customer>
</o:order>
~~~

Ở đây:

- `o` là prefix gắn với namespace `urn:acme:order:v1`.
- `c` là prefix gắn với namespace `urn:acme:customer:v1`.
- `order`, `id` và `customer` là local name.
- Một tên phần tử được định danh bằng namespace URI cùng local name, thường được gọi là expanded name hoặc QName.

Hai phần tử có cùng local name nhưng namespace URI khác nhau là hai tên XML khác nhau. Ngược lại, cùng URI và local name thì vẫn là cùng tên phần tử dù prefix khác nhau.

## 2. Namespace URI và prefix không giống nhau

Một hiểu lầm phổ biến là xem prefix như một phần cố định của tên phần tử. Thực tế, prefix chỉ là bí danh được khai báo trong phạm vi XML.

Hai tài liệu sau tương đương về namespace của các phần tử:

~~~xml
<a:order xmlns:a="urn:acme:order:v1">
  <a:id>ORD-1001</a:id>
</a:order>
~~~

~~~xml
<order xmlns="urn:acme:order:v1">
  <id>ORD-1001</id>
</order>
~~~

Tài liệu thứ nhất dùng prefix `a`; tài liệu thứ hai dùng default namespace. Cả hai đều định danh phần tử `order` và `id` bằng URI `urn:acme:order:v1`.

Một tài liệu khác có thể dùng prefix `ord`:

~~~xml
<ord:order xmlns:ord="urn:acme:order:v1">
  <ord:id>ORD-1001</ord:id>
</ord:order>
~~~

Nếu ứng dụng cần xử lý theo namespace, hãy quan tâm đến URI và local name. Không viết code phụ thuộc vào chuỗi prefix như `ord:` hoặc `a:`. Prefix có thể được đổi mà không thay đổi ý nghĩa namespace.

Namespace URI là định danh, không nhất thiết là địa chỉ web cần truy cập. Nó được so sánh như một chuỗi URI theo quy tắc XML namespace; không tự động tải nội dung từ URI đó.

## 3. Khai báo namespace trong XML

Namespace được khai báo bằng thuộc tính đặc biệt:

~~~xml
xmlns="urn:acme:order:v1"
~~~

Đây là default namespace. Nó áp dụng cho các phần tử không có prefix trong phạm vi khai báo.

Có thể khai báo prefix riêng:

~~~xml
xmlns:o="urn:acme:order:v1"
xmlns:c="urn:acme:customer:v1"
~~~

Khai báo có phạm vi từ phần tử đặt khai báo xuống các phần tử con, trừ khi một phần tử con khai báo lại cùng prefix hoặc đặt default namespace khác.

Ví dụ namespace có thể được đổi trong một nhánh:

~~~xml
<root xmlns="urn:acme:common">
  <item>common item</item>
  <external xmlns="urn:partner:external">
    <item>partner item</item>
  </external>
</root>
~~~

`root` và phần tử `item` đầu tiên thuộc `urn:acme:common`; `external` và `item` bên trong nó thuộc `urn:partner:external`.

Để đưa một phần tử không namespace trở lại trong phạm vi đang có default namespace, XML có thể dùng `xmlns=""`:

~~~xml
<root xmlns="urn:acme:common">
  <unqualified xmlns="">plain element</unqualified>
</root>
~~~

Điều này quan trọng khi tích hợp với schema có cả phần tử qualified và unqualified.

## 4. Default namespace không áp dụng cho thuộc tính không prefix

Một quy tắc XML namespace rất quan trọng: default namespace áp dụng cho tên phần tử không prefix, nhưng không tự áp dụng cho thuộc tính không prefix.

Ví dụ:

~~~xml
<order xmlns="urn:acme:order:v1" version="1">
  <id>ORD-1001</id>
</order>
~~~

Trong tài liệu trên:

- `order` thuộc namespace `urn:acme:order:v1`.
- `id` thuộc namespace `urn:acme:order:v1`.
- Thuộc tính `version` không thuộc namespace nào vì nó không có prefix.

Nếu thuộc tính cần namespace, nó phải được prefix:

~~~xml
<order xmlns="urn:acme:order:v1"
       xmlns:m="urn:acme:metadata:v1"
       m:version="1">
  <id>ORD-1001</id>
</order>
~~~

`m:version` thuộc `urn:acme:metadata:v1`, trong khi phần tử `order` và `id` thuộc `urn:acme:order:v1`.

Khi ánh xạ XML bằng Jackson, hãy khai báo rõ thuộc tính nào là attribute và namespace nào áp dụng. Không suy luận namespace của attribute từ default namespace của phần tử chứa nó.

## 5. Jackson XML và các annotation namespace

Jackson XML được cung cấp qua artifact `jackson-dataformat-xml`. Kiểu mapper chính là `XmlMapper`, mở rộng khả năng Databind để đọc và ghi XML qua StAX.

Các annotation thường dùng:

| Annotation | Vai trò |
|---|---|
| `@JacksonXmlRootElement` | Đặt local name và namespace cho root element của kiểu |
| `@JacksonXmlProperty` | Đặt local name, namespace và chọn element hay attribute cho property |
| `@JacksonXmlElementWrapper` | Cấu hình wrapper của collection |
| `@JacksonXmlText` | Ánh xạ property vào nội dung text của element |
| `@JacksonXmlCData` | Yêu cầu ghi nội dung text dưới dạng CDATA trong các trường hợp được hỗ trợ |

Namespace được khai báo bằng URI, không phải prefix. Các annotation không cung cấp một thuộc tính prefix ổn định để ép mọi tài liệu dùng đúng một bí danh cụ thể. Prefix được quyết định bởi XML writer/StAX implementation và cách namespace được khai báo khi ghi.

## 6. Thêm dependency và tạo XmlMapper

Với Gradle, khai báo module XML cùng dòng phiên bản Jackson đang được dự án quản lý:

~~~gradle
dependencies {
    implementation("com.fasterxml.jackson.dataformat:jackson-dataformat-xml")
}
~~~

Nếu dự án không dùng BOM hoặc dependency management, cần chỉ định version tương thích với các artifact Jackson khác. Tránh trộn các phiên bản khác nhau của `jackson-core`, `jackson-annotations`, `jackson-databind` và `jackson-dataformat-xml`.

Tạo mapper:

~~~java
import com.fasterxml.jackson.dataformat.xml.XmlMapper;

XmlMapper xmlMapper = new XmlMapper();
~~~

Hoặc dùng builder:

~~~java
XmlMapper xmlMapper = XmlMapper.builder()
    .build();
~~~

`XmlMapper` dùng parser/writer XML bên dưới thông qua StAX. Trong ứng dụng thực tế, nên cấu hình mapper một lần lúc khởi động và tái sử dụng sau khi cấu hình hoàn tất.

## 7. Đặt namespace cho root element

Dùng `@JacksonXmlRootElement` để xác định tên và namespace của root:

~~~java
import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlRootElement;

@JacksonXmlRootElement(
    localName = "order",
    namespace = OrderXml.ORDER_NS
)
public class OrderXml {
    public static final String ORDER_NS = "urn:acme:order:v1";

    private String id;

    // Getter và setter.
}
~~~

Khi serialize một `OrderXml` ở root, Jackson dùng local name `order` và namespace URI `urn:acme:order:v1`.

Không đặt prefix vào `localName`:

~~~java
// Không nên: localName chỉ là tên cục bộ.
@JacksonXmlRootElement(localName = "o:order")
~~~

Hãy khai báo namespace URI riêng. Prefix là phần trình bày của XML writer.

Nếu không khai báo `@JacksonXmlRootElement`, root name có thể được suy ra từ tên class theo quy tắc Jackson XML. Với hợp đồng tích hợp, nên khai báo tường minh để tránh tên class Java vô tình trở thành tên root công khai.

## 8. Đặt namespace cho element property

Dùng `@JacksonXmlProperty` để chỉ định local name và namespace của một property:

~~~java
import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlProperty;

@JacksonXmlRootElement(
    localName = "order",
    namespace = OrderXml.ORDER_NS
)
public class OrderXml {
    public static final String ORDER_NS = "urn:acme:order:v1";
    public static final String CUSTOMER_NS = "urn:acme:customer:v1";

    @JacksonXmlProperty(
        localName = "id",
        namespace = ORDER_NS
    )
    private String orderId;

    @JacksonXmlProperty(
        localName = "customerName",
        namespace = CUSTOMER_NS
    )
    private String customerName;

    // Getter và setter.
}
~~~

Ý nghĩa:

- Java property `orderId` được ghi/đọc theo tên XML `id` trong namespace đơn hàng.
- Java property `customerName` được ghi/đọc theo tên XML `customerName` trong namespace khách hàng.
- Tên Java và tên XML không cần giống nhau.

XML tương đương về mặt namespace có thể có dạng:

~~~xml
<order xmlns="urn:acme:order:v1"
       xmlns:c="urn:acme:customer:v1">
  <id>ORD-1001</id>
  <c:customerName>Lan</c:customerName>
</order>
~~~

Prefix `c` chỉ là ví dụ. Writer có thể chọn prefix khác hoặc dùng default namespace nếu phù hợp.

## 9. Một DTO kết hợp nhiều namespace

Một tài liệu thường kết hợp nhiều vocabulary. Ví dụ đơn hàng dùng namespace riêng, địa chỉ dùng namespace khách hàng và phần tiền tệ dùng namespace chung:

~~~xml
<order xmlns="urn:acme:order:v1"
       xmlns:c="urn:acme:customer:v1"
       xmlns:cm="urn:acme:common:v1">
  <id>ORD-1001</id>
  <c:customer>
    <c:id>CUS-88</c:id>
    <c:name>Lan</c:name>
  </c:customer>
  <cm:currency>VND</cm:currency>
</order>
~~~

Có thể mô hình hóa bằng các DTO lồng nhau:

~~~java
public final class XmlNamespaces {
    private XmlNamespaces() {
    }

    public static final String ORDER = "urn:acme:order:v1";
    public static final String CUSTOMER = "urn:acme:customer:v1";
    public static final String COMMON = "urn:acme:common:v1";
}

@JacksonXmlRootElement(
    localName = "order",
    namespace = XmlNamespaces.ORDER
)
public class OrderDocument {
    @JacksonXmlProperty(
        localName = "id",
        namespace = XmlNamespaces.ORDER
    )
    private String id;

    @JacksonXmlProperty(
        localName = "customer",
        namespace = XmlNamespaces.CUSTOMER
    )
    private CustomerDocument customer;

    @JacksonXmlProperty(
        localName = "currency",
        namespace = XmlNamespaces.COMMON
    )
    private String currency;

    // Getter và setter.
}

public class CustomerDocument {
    @JacksonXmlProperty(
        localName = "id",
        namespace = XmlNamespaces.CUSTOMER
    )
    private String id;

    @JacksonXmlProperty(
        localName = "name",
        namespace = XmlNamespaces.CUSTOMER
    )
    private String name;

    // Getter và setter.
}
~~~

Các URI được đặt trong một class hằng số để tránh lỗi chính tả và giúp nhiều DTO dùng chung một định nghĩa. Giá trị dùng trong annotation phải là hằng số compile-time như ~public static final String~ được khởi tạo trực tiếp bằng literal.

Nếu một vocabulary có nhiều phiên bản, hãy xem URI namespace có phải versioned contract hay không. Đổi URI có thể tương đương với đổi schema identity, dù local name vẫn giữ nguyên.

## 10. Ánh xạ attribute có namespace

`@JacksonXmlProperty` có thuộc tính `isAttribute` để ghi property thành XML attribute thay vì child element.

Attribute không namespace:

~~~java
@JacksonXmlProperty(
    isAttribute = true,
    localName = "version"
)
private String version;
~~~

XML:

~~~xml
<order xmlns="urn:acme:order:v1" version="1">
  <id>ORD-1001</id>
</order>
~~~

Ở đây `version` không thuộc default namespace, đúng theo quy tắc XML.

Nếu attribute thuộc namespace metadata:

~~~java
@JacksonXmlProperty(
    isAttribute = true,
    localName = "source",
    namespace = XmlNamespaces.COMMON
)
private String source;
~~~

XML có thể được ghi tương tự:

~~~xml
<order xmlns="urn:acme:order:v1"
       xmlns:cm="urn:acme:common:v1"
       cm:source="partner-a">
  <id>ORD-1001</id>
</order>
~~~

Khi kiểm thử attribute có namespace, hãy kiểm tra cả namespace URI và local name của attribute bằng parser namespace-aware. Đừng chỉ kiểm tra chuỗi XML có chứa `source=` vì tên hiển thị còn phụ thuộc prefix.

## 11. Namespace của collection wrapper và phần tử con

Collection trong XML có thể được biểu diễn theo hai hình thức.

### 11.1. Có wrapper

~~~xml
<order xmlns="urn:acme:order:v1">
  <lines>
    <line>
      <sku>BOOK-1</sku>
      <quantity>2</quantity>
    </line>
    <line>
      <sku>BOOK-2</sku>
      <quantity>1</quantity>
    </line>
  </lines>
</order>
~~~

Ánh xạ:

~~~java
@JacksonXmlElementWrapper(
    localName = "lines",
    namespace = XmlNamespaces.ORDER
)
@JacksonXmlProperty(
    localName = "line",
    namespace = XmlNamespaces.ORDER
)
private List<OrderLineXml> lines;
~~~

`@JacksonXmlElementWrapper` mô tả element bao quanh collection; `@JacksonXmlProperty` mô tả tên và namespace của từng phần tử trong collection. Hai namespace có thể được cấu hình độc lập nếu schema yêu cầu wrapper và item thuộc các vocabulary khác nhau.

### 11.2. Không có wrapper

Một schema khác có thể yêu cầu các phần tử `line` lặp trực tiếp dưới `order`:

~~~xml
<order xmlns="urn:acme:order:v1">
  <id>ORD-1001</id>
  <line>
    <sku>BOOK-1</sku>
    <quantity>2</quantity>
  </line>
  <line>
    <sku>BOOK-2</sku>
    <quantity>1</quantity>
  </line>
</order>
~~~

Khai báo:

~~~java
@JacksonXmlElementWrapper(useWrapping = false)
@JacksonXmlProperty(
    localName = "line",
    namespace = XmlNamespaces.ORDER
)
private List<OrderLineXml> lines;
~~~

Không nhầm namespace của wrapper với namespace của item. Khi tích hợp schema của đối tác, hãy đối chiếu cả hai cấp trong XSD hoặc tài liệu mẫu.

## 12. Default namespace trong DTO

Nếu hầu hết element của một tài liệu thuộc cùng một namespace, XML writer có thể biểu diễn namespace đó bằng default namespace:

~~~xml
<order xmlns="urn:acme:order:v1">
  <id>ORD-1001</id>
  <status>CONFIRMED</status>
</order>
~~~

DTO vẫn nên khai báo URI namespace trên root và các property cần thuộc namespace đó. Không dựa vào việc phần tử con “kế thừa” namespace từ root trong code Java; namespace là thuộc tính của expanded name, còn default namespace chỉ là cách viết XML để gán URI cho các tên không prefix.

Nếu một property cần không namespace, hoặc cần thuộc namespace khác, hãy cấu hình rõ và kiểm tra XML đầu ra. Đặc biệt, khi chuyển từ default namespace sang một nhánh namespace khác, XML writer có thể sinh prefix hoặc khai báo namespace mới ở phần tử con.

## 13. Đọc XML có prefix khác với prefix khi ghi

Một consumer nên chấp nhận cùng một namespace URI dù tài liệu dùng prefix khác nhau. Ví dụ DTO được định nghĩa với URI `urn:acme:order:v1`, nhưng input có thể là:

~~~xml
<x:order xmlns:x="urn:acme:order:v1">
  <x:id>ORD-1001</x:id>
</x:order>
~~~

hoặc:

~~~xml
<order xmlns="urn:acme:order:v1">
  <id>ORD-1001</id>
</order>
~~~

Không nên viết kiểm tra đầu vào bằng cách tìm chuỗi `<o:order`. Prefix không phải định danh ổn định.

Jackson XML sử dụng StAX để đọc XML. Namespace-aware parser cung cấp namespace URI và local name riêng. Tuy nhiên, mức độ kiểm tra namespace trong quá trình property matching có thể phụ thuộc phiên bản Jackson XML và cách ánh xạ được cấu hình; không nên giả định rằng strict unknown-property mode luôn xác minh đầy đủ mọi namespace URI. Nếu namespace là ranh giới bảo mật hoặc hợp đồng quan trọng, hãy kiểm tra QName bằng StAX hoặc validate tài liệu bằng XSD trước khi bind sang DTO.

## 14. Kiểm tra namespace bằng StAX

Có thể dùng `XMLInputFactory` và `XMLStreamReader` để kiểm tra tên phần tử theo namespace URI và local name:

~~~java
XMLInputFactory factory = XMLInputFactory.newFactory();
XMLStreamReader reader = factory.createXMLStreamReader(
    new StringReader(xml)
);

while (reader.hasNext()) {
    int event = reader.next();

    if (event == XMLStreamConstants.START_ELEMENT) {
        QName name = reader.getName();

        System.out.println("namespace = " + name.getNamespaceURI());
        System.out.println("localName = " + name.getLocalPart());
        break;
    }
}

reader.close();
~~~

`QName` tách namespace URI, local part và prefix. Khi so sánh hợp đồng, ưu tiên URI và local part:

~~~java
assertEquals(
    "urn:acme:order:v1",
    reader.getName().getNamespaceURI()
);
assertEquals("order", reader.getLocalName());
~~~

Không assert prefix như `o` hoặc `ord` nếu hợp đồng không bắt buộc prefix cụ thể. Nếu cần kiểm tra prefix do một đối tác yêu cầu vì một công cụ cũ không tuân chuẩn, hãy xem đó là ràng buộc tương thích đặc biệt và kiểm soát writer riêng.

## 15. Đọc và ghi bằng XmlMapper

Ví dụ đọc XML:

~~~java
XmlMapper mapper = new XmlMapper();

OrderDocument order = mapper.readValue(xml, OrderDocument.class);
~~~

Ghi XML:

~~~java
String xml = mapper.writeValueAsString(order);
~~~

Nếu muốn ghi vào file hoặc stream, có thể dùng overload tương ứng của `writeValue`. Đảm bảo charset và encoding của tài liệu phù hợp với hợp đồng. XML declaration có thể chứa encoding; khi ghi vào `Writer`, charset thực tế do writer quản lý, còn khi ghi vào byte stream, Jackson/StAX có thể tạo declaration dựa trên cấu hình đầu ra.

Không nối chuỗi XML thủ công để thêm `xmlns` sau khi serialize. Cách đó dễ tạo khai báo trùng, sai phạm vi hoặc XML không hợp lệ. Hãy để namespace được quản lý bởi annotation và StAX writer, hoặc dùng một XML writer chuyên biệt khi cần kiểm soát cấu trúc namespace nâng cao.

## 16. Kiểm thử round-trip theo namespace, không theo prefix

Một bài test tốt nên kiểm tra cả hai chiều:

~~~java
@Test
void serializesAndDeserializesOrderNamespace() throws Exception {
    XmlMapper mapper = new XmlMapper();

    OrderDocument order = new OrderDocument();
    order.setId("ORD-1001");
    order.setCurrency("VND");

    String xml = mapper.writeValueAsString(order);

    XMLInputFactory factory = XMLInputFactory.newFactory();
    XMLStreamReader reader = factory.createXMLStreamReader(
        new StringReader(xml)
    );

    while (reader.hasNext()
            && reader.next() != XMLStreamConstants.START_ELEMENT) {
        // Đi tới root element.
    }

    assertEquals("order", reader.getLocalName());
    assertEquals(XmlNamespaces.ORDER, reader.getNamespaceURI());
    reader.close();

    OrderDocument restored = mapper.readValue(xml, OrderDocument.class);
    assertEquals("ORD-1001", restored.getId());
    assertEquals("VND", restored.getCurrency());
}
~~~

Trong test thực tế, bổ sung các trường hợp:

- Input dùng prefix khác prefix được sinh ra khi serialize.
- Input dùng default namespace.
- Property thuộc namespace khác root.
- Attribute không namespace và attribute có namespace.
- Collection wrapper và item có namespace riêng.
- Namespace URI sai hoặc bị thiếu.
- Phần tử cùng local name nhưng thuộc namespace khác.
- Element không namespace nằm trong default namespace scope.
- Round-trip không làm mất dữ liệu hoặc tạo phần tử trùng.

Để kiểm tra QName của phần tử con, tiếp tục duyệt `XMLStreamReader` đến `START_ELEMENT` tương ứng và so sánh `getName()`. Đừng chỉ dùng `String.contains()` vì prefix và thứ tự khai báo namespace có thể thay đổi.

## 17. Validate XML bằng XSD khi namespace là một phần hợp đồng

`XmlMapper` tập trung vào data binding. Nó không thay thế việc kiểm tra đầy đủ một tài liệu có tuân thủ XML Schema hay không.

Nếu đối tác cung cấp XSD, có thể validate bằng JAXP trước khi bind:

~~~java
SchemaFactory schemaFactory = SchemaFactory.newInstance(
    XMLConstants.W3C_XML_SCHEMA_NS_URI
);

Schema schema = schemaFactory.newSchema(xsdSource);
Validator validator = schema.newValidator();

validator.validate(new StreamSource(new StringReader(xml)));

OrderDocument order = xmlMapper.readValue(xml, OrderDocument.class);
~~~

XSD có thể kiểm tra:

- Namespace target của schema.
- Phần tử và thuộc tính được phép.
- Kiểu dữ liệu và pattern.
- Thứ tự phần tử theo sequence.
- Cardinality như minOccurs/maxOccurs.
- Quan hệ giữa các kiểu và phần tử.
- Quy tắc import/include schema khác namespace.

Với schema có nhiều namespace, cần khai báo import/include và resolver phù hợp. Không tải XSD tùy ý từ URL do payload cung cấp. Hãy quản lý schema tin cậy trong ứng dụng hoặc dùng resolver có allowlist.

## 18. Prefix do StAX writer tạo ra

Các annotation Jackson XML khai báo namespace URI, không phải một prefix tùy ý để dùng ổn định. Writer có thể tạo prefix như `wstxns1`, dùng default namespace hoặc chọn cách khai báo khác tùy StAX provider và context.

Ví dụ hai output có thể khác cách viết nhưng mang cùng expanded name:

~~~xml
<o:order xmlns:o="urn:acme:order:v1">
  <o:id>ORD-1001</o:id>
</o:order>
~~~

~~~xml
<order xmlns="urn:acme:order:v1">
  <id>ORD-1001</id>
</order>
~~~

Nếu hệ thống nhận XML tuân chuẩn namespace, cả hai đều có cùng ý nghĩa namespace. Đừng coi prefix do writer sinh là một phần hợp đồng trừ khi tài liệu tích hợp quy định rõ.

Khi cần kiểm soát prefix cụ thể, có thể phải cấu hình underlying `XMLOutputFactory`/`XMLStreamWriter`, namespace repairing và cách writer khai báo prefix. Cách cấu hình cụ thể phụ thuộc StAX provider và phiên bản Jackson XML. Hãy kiểm tra API của phiên bản đang dùng, đồng thời viết test trên đúng provider trong production.

Không nên dùng regex thay prefix sau khi ghi XML. Regex không hiểu phạm vi khai báo, prefix shadowing, attribute namespace hoặc namespace reset bằng `xmlns=""`.

## 19. Namespace trong attribute và element có local name trùng nhau

XML cho phép attribute và child element có cùng local name vì chúng thuộc hai loại node khác nhau:

~~~xml
<item xmlns="urn:acme:catalog"
      id="A-1">
  <id>legacy-id</id>
</item>
~~~

Ở đây:

- Element `item` thuộc `urn:acme:catalog`.
- Attribute `id` không namespace.
- Child element `id` thuộc `urn:acme:catalog`.

Nếu DTO có hai property cần ánh xạ đến attribute và element, hãy khai báo `isAttribute = true` cho property attribute và đặt tên/namespace rõ ràng. Nếu hai property Java cùng ánh xạ một tên XML không thể phân biệt, mapping có thể xung đột hoặc không diễn đạt được schema; cần đổi DTO hoặc dùng custom deserializer.

## 20. Namespace không phải một property dữ liệu thông thường

Không tạo field Java tên `xmlns` chỉ để cố ghi namespace:

~~~java
// Không nên mô hình namespace declaration như field business.
private String xmlns;
~~~

Namespace declaration là metadata của XML element và được quản lý bởi XML writer. Nó không phải dữ liệu nghiệp vụ của object.

Hãy khai báo URI trong annotation hoặc quản lý StAX writer khi cần kiểm soát namespace nâng cao. Nếu cần giữ toàn bộ thông tin XML, bao gồm prefix, namespace declarations, comments hoặc processing instructions, `XmlMapper` có thể không phải công cụ bảo toàn nguyên bản phù hợp; hãy cân nhắc StAX, DOM hoặc lưu payload gốc.

## 21. Những giới hạn của Jackson XML cần biết

Jackson XML là data binding module, không phải một bộ công cụ xử lý mọi tính năng XML. Một số tình huống cần cân nhắc:

- Prefix không được điều khiển trực tiếp như một phần của annotation namespace.
- XML có mixed content phức tạp (text xen kẽ nhiều element con) có thể khó ánh xạ thành bean đơn giản.
- XML attributes và elements có quy tắc namespace khác nhau.
- Namespace declaration không nên được mô hình hóa như property thông thường.
- Một số hành vi namespace matching khi deserialize cần được kiểm chứng trên phiên bản module cụ thể.
- XML schema validation cần được thực hiện riêng nếu hợp đồng yêu cầu XSD.
- XML round-trip qua object model không bảo đảm giữ nguyên whitespace, prefix, thứ tự namespace declaration hoặc lexical form ban đầu.

Nếu yêu cầu là đọc/ghi XML nghiệp vụ có cấu trúc ổn định, `XmlMapper` rất tiện. Nếu yêu cầu là chỉnh sửa XML mà phải bảo toàn nguyên bản mọi node và namespace declaration, hãy dùng API XML chuyên dụng.

## 22. Bảo vệ parser XML đầu vào

Namespace không thay thế các biện pháp bảo vệ XML parser. Khi đọc XML từ nguồn không tin cậy, cần xem xét DTD và external entity (XXE), kích thước tài liệu, độ sâu lồng nhau và giới hạn thời gian xử lý.

Jackson XML sử dụng StAX provider. Có thể cấu hình underlying `XMLInputFactory` để tắt DTD và external entities theo các property mà provider hỗ trợ, ví dụ `XMLInputFactory.SUPPORT_DTD` và `javax.xml.stream.isSupportingExternalEntities`. Hãy xác nhận property được provider chấp nhận và viết test chứng minh parser không truy cập tài nguyên ngoài ý muốn.

Ngoài ra:

- Giới hạn kích thước request trước khi parse.
- Giới hạn độ sâu và độ dài text.
- Không tải schema hoặc DTD từ địa chỉ do client cung cấp.
- Quản lý XSD tin cậy trong ứng dụng.
- Không log toàn bộ XML nếu có dữ liệu cá nhân hoặc bí mật.
- Kiểm thử với StAX provider thực tế được đóng gói trong ứng dụng.

## 23. Những lỗi thường gặp

### Dùng prefix như một phần của localName

Đặt `localName = "o:order"` làm mapping phụ thuộc prefix. Hãy dùng `localName = "order"` và khai báo namespace URI riêng.

### Chỉ khai báo namespace trên root

Root có namespace không có nghĩa mọi property trong DTO tự động được khai báo đúng namespace theo ý muốn. Gắn URI rõ ràng cho property theo schema và kiểm tra XML thực tế.

### Cho rằng default namespace áp dụng cho attribute

Attribute không prefix không thuộc default namespace. Nếu attribute cần namespace, phải ánh xạ namespace riêng và kiểm tra QName của nó.

### Chỉ kiểm tra chuỗi XML

Prefix và thứ tự khai báo namespace có thể khác nhau. Dùng parser namespace-aware và so sánh URI/local name.

### Dùng @JsonIgnoreProperties để xử lý namespace mismatch

Unknown-property policy và namespace identity là hai vấn đề khác nhau. Nếu namespace quan trọng, validate QName hoặc XSD.

### Nối xmlns bằng chuỗi sau khi serialize

Có thể tạo khai báo sai phạm vi hoặc XML không hợp lệ. Dùng annotation/StAX writer.

### Cho rằng XmlMapper validate XSD

Data binding không đồng nghĩa schema validation. Dùng JAXP Validator khi cần kiểm tra hợp đồng XSD.

### Không kiểm soát StAX provider

Prefix generation, namespace repairing và một số chi tiết ghi XML phụ thuộc writer. Kiểm thử đúng provider của production nếu có ràng buộc tương thích.

### Dùng XmlMapper để bảo toàn nguyên văn XML

Object binding thường chuẩn hóa lại cách ghi. Nếu cần giữ prefix, comments, whitespace hoặc lexical representation, lưu payload gốc hoặc dùng XML API phù hợp.

## 24. Quy trình thiết kế namespace cho tích hợp XML

1. Thu thập XML mẫu và XSD của producer/consumer.
2. Liệt kê namespace URI, local name, prefix mẫu và target namespace của từng schema.
3. Phân biệt element namespace với attribute namespace.
4. Xác định default namespace, các namespace con và nơi có `xmlns=""`.
5. Định nghĩa hằng số URI dùng chung trong DTO.
6. Gắn `@JacksonXmlRootElement` cho root.
7. Gắn `@JacksonXmlProperty` cho element và attribute.
8. Dùng `@JacksonXmlElementWrapper` và `@JacksonXmlProperty` để mô tả wrapper/item của collection.
9. Dùng `XmlMapper` đã cấu hình module cần thiết để đọc/ghi.
10. Kiểm thử bằng StAX theo namespace URI và local name, không phụ thuộc prefix.
11. Validate XSD riêng nếu namespace/schema là ranh giới hợp đồng.
12. Kiểm tra các trường hợp namespace sai, thiếu namespace, default namespace và attribute.
13. Kiểm soát DTD/XXE, kích thước và độ sâu của XML không tin cậy.
14. Nếu cần prefix cố định hoặc bảo toàn nguyên bản, đánh giá StAX/DOM thay vì dựa vào annotation.
15. Tài liệu hóa namespace URI và quy tắc versioning như một phần của hợp đồng tích hợp.

## 25. Bảng ghi nhớ

| Nhu cầu | Cách làm |
|---|---|
| Khai báo namespace cho root | `@JacksonXmlRootElement(localName, namespace)` |
| Khai báo namespace cho property | `@JacksonXmlProperty(localName, namespace)` |
| Ghi property thành attribute | `@JacksonXmlProperty(isAttribute = true, ...)` |
| Cấu hình namespace của collection wrapper | `@JacksonXmlElementWrapper(localName, namespace)` |
| Cấu hình namespace của item | `@JacksonXmlProperty(localName, namespace)` |
| Không ghi wrapper cho collection | `@JacksonXmlElementWrapper(useWrapping = false)` |
| Đọc/ghi XML | `XmlMapper` |
| Kiểm tra tên XML | StAX `QName`: namespace URI + local part |
| Xác minh schema | JAXP `SchemaFactory` và `Validator` |
| Kiểm soát prefix cụ thể | Cấu hình StAX writer/provider và kiểm thử thực tế |
| Bảo toàn XML nguyên bản | StAX/DOM hoặc lưu payload gốc |
| Bảo vệ parser | Tắt DTD/external entities và giới hạn tài nguyên |

## 26. Kết luận

Quản lý namespace đúng cách bắt đầu từ việc hiểu namespace URI là định danh thực sự, còn prefix chỉ là bí danh trong văn bản XML. Default namespace áp dụng cho element không prefix nhưng không áp dụng cho attribute không prefix. Khi dùng Jackson XML, hãy khai báo root bằng `@JacksonXmlRootElement`, property bằng `@JacksonXmlProperty`, và tách namespace của collection wrapper với item khi cần.

Hãy kiểm thử XML theo QName bằng parser namespace-aware thay vì so sánh prefix hoặc chuỗi XML. Nếu namespace là một phần quan trọng của hợp đồng, validate XSD riêng và xác nhận hành vi trên đúng Jackson/StAX provider đang chạy. `XmlMapper` phù hợp với data binding XML có cấu trúc; khi cần kiểm soát prefix tuyệt đối hoặc bảo toàn nguyên bản mọi chi tiết XML, hãy dùng StAX/DOM hoặc giữ lại payload gốc.
