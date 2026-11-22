# Ánh xạ tên phần tử, thuộc tính và phần tử gốc

Khi dùng Jackson để chuyển đổi XML, tên class Java và tên property không nhất thiết giống tên phần tử hoặc thuộc tính trong XML. Một hệ thống có thể yêu cầu root element là `<order>`, mã đơn hàng nằm trong XML attribute `id`, tên khách hàng là element `<customer-name>` và danh sách dòng hàng được bao bởi `<lines>` với từng phần tử `<line>`.

Jackson XML module cung cấp `XmlMapper` cùng các annotation chuyên biệt để mô tả những quy tắc này. Ba annotation quan trọng nhất là:

- `@JacksonXmlRootElement`: đặt tên và namespace cho phần tử gốc của một kiểu.
- `@JacksonXmlProperty`: đặt tên/namespace cho property và chỉ định property đó là XML attribute.
- `@JacksonXmlElementWrapper`: điều khiển phần tử bao quanh collection.

Ngoài ra, `@JacksonXmlText` ánh xạ property vào nội dung văn bản trực tiếp của element. Khi thiết kế model, cần phân biệt rõ element, attribute, wrapper và root vì chúng có cấu trúc XML khác nhau dù đều được biểu diễn thành property Java.

Các ví dụ dùng Jackson 2.x với `jackson-dataformat-xml`. Hãy dùng cùng version cho `jackson-core`, `jackson-databind`, `jackson-annotations` và module XML, tốt nhất thông qua BOM của dự án.

## 1. Cài đặt và tạo `XmlMapper`

Để dùng XML, dự án cần dependency `jackson-dataformat-xml`:

```xml
<dependency>
    <groupId>com.fasterxml.jackson.dataformat</groupId>
    <artifactId>jackson-dataformat-xml</artifactId>
    <version>${jackson.version}</version>
</dependency>
```

`jackson.version` nên được quản lý tập trung bằng Jackson BOM hoặc dependency management hiện có để các module không lệch version.

Tạo mapper:

```java
import com.fasterxml.jackson.dataformat.xml.XmlMapper;

XmlMapper xmlMapper = new XmlMapper();
```

`XmlMapper` là mapper chuyên cho XML. Nó sử dụng Jackson Databind để ánh xạ object và Jackson XML module để đọc/ghi XML qua StAX. Không dùng `ObjectMapper` JSON mặc định để đọc XML; hãy dùng `XmlMapper` hoặc mapper được cấu hình với `XmlFactory`.

Ví dụ serialize và deserialize:

```java
String xml = xmlMapper.writeValueAsString(order);
Order restored = xmlMapper.readValue(xml, Order.class);
```

Kết quả phụ thuộc annotation trên model và cấu hình mapper. Nếu không khai báo tên tường minh, Jackson XML sẽ suy ra tên từ metadata/property theo quy tắc mặc định; với XML contract công khai, nên khai báo local name cần thiết để tránh phụ thuộc tên class hoặc accessor.

## 2. Phân biệt root element, child element và attribute

XML có cấu trúc khác JSON object. Một element có thể chứa attribute, child element và text content:

```xml
<order id="ORD-100" status="created">
    <customer-name>An Nguyen</customer-name>
    <total currency="VND">150000</total>
</order>
```

Trong ví dụ:

- `order` là **root element** của document.
- `id` và `status` là **XML attribute** của root.
- `customer-name` là **child element**.
- `total` là child element có attribute `currency` và text content `150000`.

Một model Java có thể biểu diễn các thành phần đó bằng property riêng, nhưng annotation quyết định chúng được ghi ở vị trí nào trong XML.

| Thành phần XML | Annotation Jackson XML thường dùng |
|---|---|
| Tên root element | `@JacksonXmlRootElement` |
| Tên child element | `@JacksonXmlProperty(localName = "...")` |
| Tên XML attribute | `@JacksonXmlProperty(isAttribute = true, localName = "...")` |
| Wrapper cho collection | `@JacksonXmlElementWrapper(localName = "...")` |
| Collection không có wrapper | `@JacksonXmlElementWrapper(useWrapping = false)` |
| Text trực tiếp bên trong element | `@JacksonXmlText` |

Không nhầm XML attribute với child element. Ví dụ `id="ORD-100"` khác `<id>ORD-100</id>` dù cả hai đều có thể được ánh xạ vào property Java tên `id`.

## 3. Đặt tên root element bằng `@JacksonXmlRootElement`

Mặc định, tên root element có thể được suy ra từ kiểu Java. Nếu XML contract yêu cầu root name cụ thể, hãy khai báo `@JacksonXmlRootElement` trên class:

```java
import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlRootElement;

@JacksonXmlRootElement(localName = "order")
public class Order {
    private String id;
    private String customerName;

    // constructors, getters và setters
}
```

Serialize:

```java
Order order = new Order();
order.setId("ORD-100");
order.setCustomerName("An Nguyen");

String xml = xmlMapper.writeValueAsString(order);
```

Root element được ghi với tên `order`:

```xml
<order>
    <id>ORD-100</id>
    <customerName>An Nguyen</customerName>
</order>
```

`localName` là phần tên cục bộ của QName. Nếu XML dùng namespace, có thể khai báo thêm `namespace`:

```java
@JacksonXmlRootElement(
        localName = "order",
        namespace = "urn:example:orders"
)
public class Order {
    // ...
}
```

Khi ghi XML, Jackson có thể tạo namespace declaration và prefix phù hợp. Prefix như `ns1` hoặc `ord` là bí danh trong tài liệu; namespace URI mới là định danh có ý nghĩa. Khi kiểm tra XML, nên so sánh namespace URI và local name thay vì phụ thuộc prefix cụ thể.

### 3.1. Root element không phải một property thông thường

`@JacksonXmlRootElement` áp dụng cho tên element bao quanh object ở cấp document. Nó không đổi tên một field bên trong object.

Ví dụ:

```java
@JacksonXmlRootElement(localName = "order")
public class Order {
    @JacksonXmlProperty(localName = "order-number")
    private String id;
}
```

XML có dạng:

```xml
<order>
    <order-number>ORD-100</order-number>
</order>
```

Root là `order`; child element là `order-number`. Hai tên được cấu hình ở hai annotation khác nhau.

### 3.2. Đọc root element

Đọc XML vào kiểu Java:

```java
Order order = xmlMapper.readValue(xml, Order.class);
```

Jackson XML đọc root element làm wrapper cho object và ánh xạ các attribute/child element bên trong vào property. `@JacksonXmlRootElement` là nơi khai báo tên root mong muốn của kiểu, đặc biệt quan trọng khi serialize.

Nếu hợp đồng yêu cầu bắt buộc root phải đúng một QName cụ thể, hãy kiểm tra điều đó bằng integration test và/hoặc kiểm tra StAX reader trước khi binding. Không nên giả định rằng chỉ truyền `Order.class` sẽ thay thế mọi bước xác thực root name ở mọi cấu hình và version. Tên root không phải một property Java có thể kiểm tra bằng `@NotBlank`.

## 4. Đổi tên child element bằng `@JacksonXmlProperty`

Tên Java property thường theo camelCase, trong khi XML contract có thể dùng kebab-case, snake_case hoặc tên legacy. Dùng `localName` để đặt tên element:

```java
import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlProperty;

public class Order {
    private String id;

    @JacksonXmlProperty(localName = "customer-name")
    private String customerName;

    // getters và setters
}
```

XML:

```xml
<order>
    <id>ORD-100</id>
    <customer-name>An Nguyen</customer-name>
</order>
```

`@JacksonXmlProperty(localName = "customer-name")` đổi tên property thành child element có local name `customer-name`. Nó không làm thay đổi tên field Java hoặc tên method.

Có thể đặt annotation trên field, getter hoặc setter theo cách Jackson phát hiện property. Trong một model, nên chọn cách đặt nhất quán để tránh metadata mâu thuẫn giữa field và accessor.

### 4.1. Tên property tường minh so với naming strategy

Jackson Databind có naming strategy như `SNAKE_CASE`, nhưng XML contract thường cần tên element chính xác. Dùng `@JacksonXmlProperty(localName = "...")` khi tên wire phải được cố định.

Ví dụ:

```java
@JacksonXmlProperty(localName = "customer-name")
private String customerName;
```

Nếu chỉ dựa vào naming strategy, tên có thể được chuyển theo quy tắc tổng quát và không nhất thiết khớp XML schema. Hãy test tên thực tế được ghi ra bởi `XmlMapper`.

### 4.2. Đặt tên element trên getter hoặc setter

Có thể gắn annotation lên accessor:

```java
public class Customer {
    private String displayName;

    @JacksonXmlProperty(localName = "display-name")
    public String getDisplayName() {
        return displayName;
    }

    @JacksonXmlProperty(localName = "display-name")
    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
```

Jackson tổng hợp field/getter/setter thành logical property theo quy tắc introspection. Nếu các vị trí mang annotation khác nhau, kết quả có thể khó hiểu. Cách dễ bảo trì là đặt annotation ở một vị trí rõ ràng hoặc giữ metadata tương thích trên các accessor liên quan.

## 5. Ánh xạ XML attribute bằng `isAttribute = true`

Để property Java được ghi thành XML attribute, dùng `@JacksonXmlProperty(isAttribute = true)`:

```java
public class Order {
    @JacksonXmlProperty(isAttribute = true, localName = "id")
    private String orderId;

    @JacksonXmlProperty(isAttribute = true, localName = "status")
    private String state;

    @JacksonXmlProperty(localName = "customer-name")
    private String customerName;

    // getters và setters
}
```

XML:

```xml
<order id="ORD-100" status="created">
    <customer-name>An Nguyen</customer-name>
</order>
```

Các điểm cần nhớ:

- `isAttribute = true` làm property trở thành XML attribute của element hiện tại.
- `localName` đặt tên attribute.
- Property không có `isAttribute = true` thường được biểu diễn bằng child element theo quy tắc XML module.
- Attribute là giá trị scalar; không dùng attribute để biểu diễn object con hoặc collection phức tạp.

### 5.1. Đọc attribute vào property Java

Với annotation trên, XML input:

```xml
<order id="ORD-100" status="created">
    <customer-name>An Nguyen</customer-name>
</order>
```

có thể được đọc:

```java
Order order = xmlMapper.readValue(xml, Order.class);

assertEquals("ORD-100", order.getOrderId());
assertEquals("created", order.getState());
assertEquals("An Nguyen", order.getCustomerName());
```

XML attribute thường được parse thành text trước khi chuyển đổi sang kiểu Java. Nếu property là `int`, `boolean`, enum hoặc kiểu ngày, Jackson tiếp tục áp dụng deserializer tương ứng. Giá trị attribute sai định dạng vẫn có thể gây mapping exception dù XML syntax hợp lệ.

### 5.2. Attribute và element cùng tên

XML cho phép attribute và child element có cùng local name trong cùng một element:

```xml
<item code="A-1">
    <code>display-code</code>
</item>
```

Trong model, cần phân biệt hai property bằng annotation và accessor phù hợp. Tuy nhiên, không nên thiết kế contract gây nhập nhằng nếu có thể chọn tên riêng, ví dụ `code` cho attribute và `display-code` cho child element.

### 5.3. Attribute không có cấu trúc lồng nhau

Không khai báo một object phức tạp thành attribute:

```java
@JacksonXmlProperty(isAttribute = true)
private Address address;
```

XML attribute chỉ chứa một giá trị văn bản, không thể mang cấu trúc con như element. Hãy biểu diễn `Address` bằng child element:

```xml
<customer>
    <address>
        <city>Hanoi</city>
        <street>Example Street</street>
    </address>
</customer>
```

## 6. Kết hợp root, attribute và child element trong một model

Ví dụ hoàn chỉnh:

```java
import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlProperty;
import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlRootElement;

@JacksonXmlRootElement(localName = "order")
public class Order {
    @JacksonXmlProperty(isAttribute = true, localName = "id")
    private String orderId;

    @JacksonXmlProperty(isAttribute = true, localName = "status")
    private String status;

    @JacksonXmlProperty(localName = "customer-name")
    private String customerName;

    public Order() {
    }

    public String getOrderId() {
        return orderId;
    }

    public void setOrderId(String orderId) {
        this.orderId = orderId;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public String getCustomerName() {
        return customerName;
    }

    public void setCustomerName(String customerName) {
        this.customerName = customerName;
    }
}
```

Tạo và serialize:

```java
XmlMapper mapper = new XmlMapper();

Order order = new Order();
order.setOrderId("ORD-100");
order.setStatus("created");
order.setCustomerName("An Nguyen");

String xml = mapper.writeValueAsString(order);
```

XML có cấu trúc tương đương:

```xml
<order id="ORD-100" status="created">
  <customer-name>An Nguyen</customer-name>
</order>
```

Deserialize:

```java
Order restored = mapper.readValue(xml, Order.class);

assertEquals("ORD-100", restored.getOrderId());
assertEquals("created", restored.getStatus());
assertEquals("An Nguyen", restored.getCustomerName());
```

XML serializer có thể chọn cách xuống dòng, indentation hoặc thứ tự attribute khác nhau. Nếu contract không yêu cầu định dạng byte-for-byte, hãy kiểm tra cấu trúc và giá trị thay vì so sánh nguyên chuỗi.

## 7. Ánh xạ collection có wrapper element

Một XML list thường có wrapper element chứa các item:

```xml
<order>
    <lines>
        <line sku="KB-01">
            <quantity>2</quantity>
        </line>
        <line sku="MS-02">
            <quantity>1</quantity>
        </line>
    </lines>
</order>
```

Ở đây:

- `lines` là wrapper element của collection.
- Mỗi `line` là một item element.
- `sku` là attribute của item.
- `quantity` là child element của item.

Khai báo:

```java
import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlElementWrapper;
import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlProperty;

public class Order {
    @JacksonXmlElementWrapper(localName = "lines")
    @JacksonXmlProperty(localName = "line")
    private List<OrderLine> lines;

    // getters và setters
}
```

Item:

```java
public class OrderLine {
    @JacksonXmlProperty(isAttribute = true, localName = "sku")
    private String sku;

    @JacksonXmlProperty(localName = "quantity")
    private int quantity;

    // getters và setters
}
```

`@JacksonXmlElementWrapper(localName = "lines")` đặt tên cho element bao quanh collection. `@JacksonXmlProperty(localName = "line")` đặt tên cho từng phần tử trong collection.

### 7.1. Vì sao cần khai báo cả wrapper và item name?

Wrapper và item là hai cấp khác nhau. Nếu chỉ đổi tên wrapper, tên item có thể vẫn được suy ra từ tên property hoặc kiểu phần tử theo quy tắc mặc định. Để XML contract rõ ràng, khai báo cả hai khi schema yêu cầu tên cụ thể.

Ví dụ:

```java
@JacksonXmlElementWrapper(localName = "order-lines")
@JacksonXmlProperty(localName = "order-line")
private List<OrderLine> lines;
```

XML:

```xml
<order-lines>
    <order-line>...</order-line>
    <order-line>...</order-line>
</order-lines>
```

## 8. Collection không có wrapper bằng `useWrapping = false`

Một số XML schema yêu cầu các item lặp trực tiếp dưới root, không có element bao ngoài:

```xml
<order>
    <line sku="KB-01">
        <quantity>2</quantity>
    </line>
    <line sku="MS-02">
        <quantity>1</quantity>
    </line>
</order>
```

Dùng:

```java
@JacksonXmlElementWrapper(useWrapping = false)
@JacksonXmlProperty(localName = "line")
private List<OrderLine> lines;
```

`useWrapping = false` yêu cầu Jackson không tạo wrapper riêng cho collection. Mỗi phần tử được ghi thành một child element lặp lại.

Đọc XML cùng cấu trúc vào `List<OrderLine>` cũng dùng annotation trên property. Nếu XML có wrapper nhưng model khai báo `useWrapping = false`, cấu trúc có thể không khớp; hãy đồng bộ annotation với XSD hoặc contract thực tế.

### 8.1. So sánh hai kiểu collection

| Cấu trúc | Annotation |
|---|---|
| `<lines><line/> <line/></lines>` | `@JacksonXmlElementWrapper(localName = "lines")` + `@JacksonXmlProperty(localName = "line")` |
| `<line/> <line/>` trực tiếp dưới root | `@JacksonXmlElementWrapper(useWrapping = false)` + `@JacksonXmlProperty(localName = "line")` |

Không nhầm wrapper element với item element. Khi đọc một schema XML có tên phức tạp, hãy xác định chính xác element nào đại diện cho collection và element nào đại diện cho từng record.

## 9. Tên phần tử trong collection và kiểu scalar

Collection không chỉ chứa object; nó cũng có thể chứa scalar như string hoặc integer.

Ví dụ XML:

```xml
<customer>
    <phone>0900000001</phone>
    <phone>0900000002</phone>
</customer>
```

Model:

```java
public class Customer {
    @JacksonXmlElementWrapper(useWrapping = false)
    @JacksonXmlProperty(localName = "phone")
    private List<String> phones;

    // getter và setter
}
```

Mỗi phần tử `phone` ánh xạ thành một string trong list. Nếu schema có wrapper:

```xml
<customer>
    <phones>
        <phone>0900000001</phone>
        <phone>0900000002</phone>
    </phones>
</customer>
```

thì khai báo wrapper `phones` và item `phone` tương ứng.

Đối với collection scalar, hãy kiểm tra trường hợp list rỗng, thiếu wrapper, một item và nhiều item. Một số schema phân biệt wrapper không xuất hiện với wrapper rỗng; model `List<T>` có thể không giữ được toàn bộ khác biệt này nếu không dùng kiểu biểu diễn bổ sung.

## 10. Ánh xạ text content bằng `@JacksonXmlText`

XML element có thể chứa text trực tiếp cùng attribute:

```xml
<price currency="VND">150000</price>
```

Property `currency` là attribute; giá trị `150000` là text content của element `price`, không nằm trong child element tên `value`.

Model:

```java
import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlText;

public class Price {
    @JacksonXmlProperty(isAttribute = true, localName = "currency")
    private String currency;

    @JacksonXmlText
    private BigDecimal amount;

    // getters và setters
}
```

`@JacksonXmlText` đánh dấu property chứa nội dung văn bản trực tiếp của element. Nó thường được dùng cho kiểu scalar hoặc nội dung đơn giản, kết hợp với attribute.

Không nên dùng `@JacksonXmlText` cho nhiều property text độc lập trong cùng một element. XML element có một vùng text content, có thể xen kẽ child element trong mixed content; một POJO thông thường không thể biểu diễn mọi thứ tự xen kẽ một cách tự động.

## 11. Namespace cho root và child element

XML namespace phân biệt element theo namespace URI và local name. Ví dụ:

```xml
<ord:order xmlns:ord="urn:example:orders" id="ORD-100">
    <ord:customer-name>An Nguyen</ord:customer-name>
</ord:order>
```

Prefix `ord` liên kết với namespace URI `urn:example:orders`. Prefix chỉ là bí danh; một tài liệu tương đương có thể dùng prefix khác hoặc default namespace:

```xml
<order xmlns="urn:example:orders" id="ORD-100">
    <customer-name>An Nguyen</customer-name>
</order>
```

Khai báo namespace trong annotation:

```java
@JacksonXmlRootElement(
        localName = "order",
        namespace = "urn:example:orders"
)
public class Order {
    @JacksonXmlProperty(
            localName = "customer-name",
            namespace = "urn:example:orders"
    )
    private String customerName;
}
```

`namespace` là URI, không phải prefix. Không ghi `namespace = "ord"` chỉ vì XML đang dùng prefix `ord`.

### 11.1. Namespace của attribute có quy tắc khác element

Trong XML Namespaces, default namespace áp dụng cho element không prefix, nhưng không tự áp dụng cho attribute không prefix. Ví dụ trong:

```xml
<order xmlns="urn:example:orders" id="ORD-100"/>
```

element `order` thuộc namespace `urn:example:orders`, còn attribute `id` không thuộc namespace nào.

Nếu attribute cần namespace, phải khai báo namespace phù hợp và kiểm tra XML được ghi ra với prefix/namespace declaration đúng schema. Đừng suy luận rằng attribute tự động kế thừa default namespace của element.

### 11.2. Kiểm thử namespace bằng QName

Không nên chỉ kiểm tra chuỗi `<ord:order>` vì prefix có thể được đổi mà namespace vẫn giống nhau. Khi kiểm thử bằng StAX hoặc DOM, hãy so sánh:

- `localPart`: tên cục bộ, ví dụ `order`.
- `namespaceURI`: URI namespace, ví dụ `urn:example:orders`.

Đó mới là định danh đầy đủ của element theo namespace-aware XML.

## 12. XML root name và `@JsonRootName`

Jackson Databind có `@JsonRootName`, còn Jackson XML cung cấp `@JacksonXmlRootElement`. Khi làm việc với XML, nên dùng annotation XML chuyên biệt để thể hiện rõ ý định về root element và namespace.

Ví dụ:

```java
@JacksonXmlRootElement(localName = "customer")
public class Customer {
    // ...
}
```

Không nhầm `SerializationFeature.WRAP_ROOT_VALUE` của JSON với cơ chế root element XML. XML luôn có một document element theo cấu trúc tài liệu; `XmlMapper` xử lý root element theo XML format. Nếu ứng dụng dùng chung model cho JSON và XML, cần test cả hai mapper vì annotation/root behavior có thể khác theo format.

## 13. Điều khiển root name và kiểu wrapper khi serialize

Khi serialize một object trực tiếp, `@JacksonXmlRootElement` quy định root name. Nếu serialize collection hoặc muốn một root wrapper có cấu trúc riêng, cần model wrapper rõ ràng thay vì dựa vào tên collection hoặc một list ở root.

Ví dụ:

```java
@JacksonXmlRootElement(localName = "orders")
public class OrdersDocument {
    @JacksonXmlElementWrapper(useWrapping = false)
    @JacksonXmlProperty(localName = "order")
    private List<Order> orders;

    // getters và setters
}
```

XML:

```xml
<orders>
    <order id="ORD-100">...</order>
    <order id="ORD-101">...</order>
</orders>
```

Wrapper class giúp đặt tên root ổn định và mô tả rõ document contract. Nó cũng là nơi thích hợp để thêm metadata như `generatedAt`, `schemaVersion` hoặc source system.

## 14. Phân biệt property thiếu, null và element rỗng

XML có nhiều cách biểu diễn trạng thái không có dữ liệu:

```xml
<customer/>
```

```xml
<customer><name/></customer>
```

```xml
<customer><name></name></customer>
```

```xml
<customer><name xsi:nil="true" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"/></customer>
```

Các trường hợp này không nhất thiết tương đương về schema hoặc binding. Element không xuất hiện, element rỗng và element có `xsi:nil` có thể được xử lý khác nhau tùy kiểu Java, annotation và cấu hình module.

Nếu contract cần phân biệt các trạng thái, hãy tạo test cụ thể với XML thật. Không giả định mọi dạng rỗng đều trở thành `null` hoặc empty string. Với collection, wrapper thiếu và wrapper rỗng cũng có thể mang ý nghĩa khác nhau.

## 15. Kiểm tra tên root trước khi bind khi hợp đồng yêu cầu nghiêm ngặt

`XmlMapper.readValue(xml, Order.class)` ánh xạ nội dung XML vào `Order`. Nếu hệ thống cần xác nhận root QName chính xác, có thể kiểm tra bằng StAX trước khi Databind.

Ví dụ minh họa:

```java
XMLInputFactory inputFactory = XMLInputFactory.newFactory();
inputFactory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
inputFactory.setProperty("javax.xml.stream.isSupportingExternalEntities", false);

try (StringReader input = new StringReader(xml)) {
    XMLStreamReader reader = inputFactory.createXMLStreamReader(input);

    while (reader.hasNext()
            && reader.getEventType() != XMLStreamConstants.START_ELEMENT) {
        reader.next();
    }

    QName rootName = reader.getName();
    if (!"order".equals(rootName.getLocalPart())
            || !"urn:example:orders".equals(rootName.getNamespaceURI())) {
        throw new InvalidXmlRootException("Unexpected XML root element");
    }

    reader.close();
}

Order order = xmlMapper.readValue(xml, Order.class);
```

Đoạn minh họa dùng `XMLInputFactory` và StAX API; code production cần đóng reader trong `finally`/try-with-resources phù hợp với API thực tế. Ví dụ cũng thể hiện việc tắt DTD và external entity ở StAX factory để tránh XML external entity (XXE) nếu parser provider hỗ trợ các property này. Cần xác nhận cấu hình bảo mật trên provider đang chạy.

Nếu muốn tránh parse XML hai lần, có thể xây dựng pipeline dùng cùng StAX reader/`XmlFactory` cho bước xác thực và binding. Điều đó cần cấu hình đúng ownership của reader và version Jackson XML. Với payload nhỏ, parse root trước rồi bind lại có thể đơn giản nhưng tạo thêm chi phí.

## 16. Đọc và ghi XML với ví dụ hoàn chỉnh

Model:

```java
@JacksonXmlRootElement(localName = "order")
public class Order {
    @JacksonXmlProperty(isAttribute = true, localName = "id")
    private String id;

    @JacksonXmlProperty(localName = "customer-name")
    private String customerName;

    @JacksonXmlElementWrapper(localName = "lines")
    @JacksonXmlProperty(localName = "line")
    private List<OrderLine> lines;

    public Order() {
    }

    // getters và setters
}

public class OrderLine {
    @JacksonXmlProperty(isAttribute = true, localName = "sku")
    private String sku;

    @JacksonXmlProperty(localName = "quantity")
    private int quantity;

    public OrderLine() {
    }

    // getters và setters
}
```

Ghi:

```java
XmlMapper mapper = new XmlMapper();

Order order = new Order();
order.setId("ORD-100");
order.setCustomerName("An Nguyen");
order.setLines(List.of(
        new OrderLine("KB-01", 2),
        new OrderLine("MS-02", 1)
));

String xml = mapper.writeValueAsString(order);
```

XML mong đợi về cấu trúc:

```xml
<order id="ORD-100">
  <customer-name>An Nguyen</customer-name>
  <lines>
    <line sku="KB-01">
      <quantity>2</quantity>
    </line>
    <line sku="MS-02">
      <quantity>1</quantity>
    </line>
  </lines>
</order>
```

Đọc:

```java
Order restored = mapper.readValue(xml, Order.class);

assertEquals("ORD-100", restored.getId());
assertEquals("An Nguyen", restored.getCustomerName());
assertEquals(2, restored.getLines().size());
assertEquals("KB-01", restored.getLines().get(0).getSku());
```

Khi viết code thật, hãy bổ sung constructor phù hợp, getter/setter hoặc creator mà Jackson cần. Ví dụ trên tập trung vào annotation định hình XML.

## 17. Kiểm thử XML theo cấu trúc thay vì so sánh chuỗi mong manh

XML serializer có thể thay đổi indentation, quote style, namespace prefix hoặc thứ tự attribute mà không làm thay đổi ý nghĩa XML. Vì vậy, test nên kiểm tra cấu trúc bằng XML-aware parser hoặc XPath khi contract không yêu cầu byte-for-byte.

Ví dụ dùng DOM:

```java
DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
factory.setNamespaceAware(true);

DocumentBuilder builder = factory.newDocumentBuilder();
Document document = builder.parse(new InputSource(new StringReader(xml)));

Element root = document.getDocumentElement();
assertEquals("order", root.getLocalName() == null
        ? root.getNodeName()
        : root.getLocalName());
assertEquals("ORD-100", root.getAttribute("id"));
```

Với XML có namespace, bật `namespaceAware` và kiểm tra `getLocalName()` cùng `getNamespaceURI()`. Nếu test chỉ dùng `getNodeName()`, prefix có thể khiến assertion phụ thuộc cách serializer đặt prefix.

Trong test dùng parser XML trên dữ liệu không tin cậy, cấu hình DTD/external entity an toàn như phần trước; đừng dùng parser test không an toàn rồi sao chép cấu hình đó vào production.

### 17.1. Kiểm tra XML output

```java
@Test
void writesRootAttributeAndNamedElement() throws Exception {
    Order order = new Order();
    order.setId("ORD-100");
    order.setCustomerName("An Nguyen");

    String xml = mapper.writeValueAsString(order);
    Document document = parseSecurely(xml);
    Element root = document.getDocumentElement();

    assertEquals("order", root.getLocalName());
    assertEquals("ORD-100", root.getAttribute("id"));
    assertEquals("An Nguyen",
            root.getElementsByTagName("customer-name")
                    .item(0).getTextContent());
}
```

`parseSecurely()` là helper test cần cấu hình namespace-aware và tắt DTD/external entity. Nếu XML có namespace, dùng `getElementsByTagNameNS(namespaceUri, localName)` thay cho tìm theo tên không namespace.

### 17.2. Kiểm tra deserialize

```java
@Test
void readsAttributeAndElementIntoProperties() throws Exception {
    String xml = """
            <order id="ORD-100">
                <customer-name>An Nguyen</customer-name>
            </order>
            """;

    Order order = mapper.readValue(xml, Order.class);

    assertEquals("ORD-100", order.getId());
    assertEquals("An Nguyen", order.getCustomerName());
}
```

Test serialize và deserialize riêng giúp xác định annotation đang ảnh hưởng chiều nào. Thêm round-trip test khi cần bảo đảm XML output của ứng dụng có thể đọc lại thành cùng dữ liệu.

## 18. Khi XML schema có element name khác Java type

Một số schema dùng tên số nhiều cho wrapper, tên số ít cho item và tên viết tắt cho field. Không cần đổi tên Java class hoặc field để chạy theo schema.

Ví dụ:

```java
@JacksonXmlRootElement(localName = "invoice-document")
public class Invoice {
    @JacksonXmlProperty(isAttribute = true, localName = "invoice-no")
    private String number;

    @JacksonXmlProperty(localName = "bill-to")
    private Customer customer;

    @JacksonXmlElementWrapper(localName = "invoice-lines")
    @JacksonXmlProperty(localName = "invoice-line")
    private List<InvoiceLine> lines;
}
```

Tên Java vẫn có thể là `Invoice`, `number`, `customer`, `lines`; annotation giữ wire format đúng schema. Điều này giúp domain model không bị buộc phải dùng naming convention của một đối tác XML cụ thể.

Nếu nhiều hệ thống có schema khác nhau, cân nhắc DTO riêng cho từng integration hoặc mix-in. Không nên làm một model có quá nhiều annotation và điều kiện để phục vụ mọi schema không liên quan.

## 19. XML namespace và nhiều schema cùng local name

Hai element có cùng local name nhưng namespace khác nhau là hai QName khác nhau:

```xml
<a:status xmlns:a="urn:system-a">active</a:status>
```

```xml
<b:status xmlns:b="urn:system-b">active</b:status>
```

Nếu model chỉ cấu hình `localName = "status"` mà bỏ qua namespace trong một integration có nhiều vocabulary, có thể ánh xạ nhầm element hoặc không khớp schema.

Khai báo namespace:

```java
@JacksonXmlProperty(
        localName = "status",
        namespace = "urn:system-a"
)
private String status;
```

Hãy ghi rõ URI trong annotation khi namespace là một phần của contract. Khi test, so sánh URI thay vì prefix. XML prefix có thể thay đổi mà không làm thay đổi QName.

## 20. Sự khác biệt giữa XML attribute và element trong schema

Một XSD có thể quy định field là attribute:

```xml
<xs:complexType name="OrderType">
    <xs:sequence>
        <xs:element name="customer-name" type="xs:string"/>
    </xs:sequence>
    <xs:attribute name="id" type="xs:string" use="required"/>
</xs:complexType>
```

Trong model Jackson:

```java
@JacksonXmlProperty(isAttribute = true, localName = "id")
private String id;

@JacksonXmlProperty(localName = "customer-name")
private String customerName;
```

Jackson XML annotation điều khiển mapping; nó không tự thực hiện đầy đủ XSD validation. Nếu cần xác nhận `id` bắt buộc, thứ tự element, occurrence, restriction, namespace hoặc pattern theo XSD, cần chạy XML Schema validation riêng bằng JAXP hoặc công cụ schema phù hợp.

Deserialize thành công không chứng minh tài liệu tuân thủ toàn bộ XSD. Jackson XML là data binding, không phải thay thế schema validator.

## 21. Giới hạn khi ánh xạ mixed content

XML có thể xen kẽ text và child element:

```xml
<description>
    This product supports <em>fast</em> charging.
</description>
```

Đây là mixed content. Một POJO đơn giản có property `String text` và property `List<Emphasis> emphasis` không nhất thiết giữ nguyên thứ tự xen kẽ text/element khi round-trip.

`@JacksonXmlText` phù hợp với text content đơn giản, thường kết hợp attribute, nhưng không phải giải pháp tổng quát để tái tạo mọi mixed-content document. Nếu thứ tự nội dung là quan trọng, cân nhắc:

- Dùng DOM/StAX để xử lý trực tiếp event sequence.
- Giữ nội dung trong một cấu trúc node chuyên biệt.
- Dùng một model XML riêng thay vì ép vào POJO thông thường.
- Viết custom serializer/deserializer nếu schema ổn định và logic có thể kiểm soát.

## 22. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Root element có tên class thay vì tên schema | Chưa khai báo `@JacksonXmlRootElement` | Đặt `localName` rõ ràng trên class |
| Field được ghi thành element nhưng schema yêu cầu attribute | Thiếu `isAttribute = true` | Dùng `@JacksonXmlProperty(isAttribute = true)` |
| XML có `<lines><line/></lines>` nhưng model đọc không đúng | Wrapper và item name không khớp | Khai báo `@JacksonXmlElementWrapper` và `@JacksonXmlProperty` |
| XML yêu cầu item lặp trực tiếp nhưng output có wrapper | Collection đang dùng wrapping mặc định | Đặt `@JacksonXmlElementWrapper(useWrapping = false)` |
| Tên element sai convention | Dựa vào tên Java hoặc naming strategy | Đặt `localName` theo XML contract |
| Namespace không khớp | Nhầm prefix với URI hoặc bỏ namespace | Khai báo URI và test QName |
| Attribute không thuộc namespace mong đợi | Nghĩ rằng default namespace áp dụng cho attribute không prefix | Khai báo namespace attribute rõ ràng nếu schema yêu cầu |
| Text content bị đưa vào child element | Chưa dùng `@JacksonXmlText` | Ánh xạ text trực tiếp khi model phù hợp |
| Round-trip mixed content mất thứ tự | POJO không giữ được event order của mixed content | Dùng StAX/DOM hoặc model XML chuyên biệt |
| Deserialize thành công nhưng sai XSD | Jackson binding không thay thế schema validation | Chạy XSD validator riêng |
| Test thất bại do prefix/indentation | So sánh nguyên chuỗi XML | Parse XML và assert QName/attribute/element |

## 23. Quy trình ánh xạ một XML contract

Khi nhận schema hoặc mẫu XML từ đối tác, hãy làm theo trình tự:

1. Xác định root element và namespace URI.
2. Liệt kê attribute của root và child element trực tiếp.
3. Với mỗi collection, xác định có wrapper không và tên item element.
4. Phân loại property nào là attribute, element hay text content.
5. Tạo DTO Java độc lập với naming convention của XML.
6. Dùng `@JacksonXmlRootElement` cho root và `@JacksonXmlProperty` cho property.
7. Dùng `@JacksonXmlElementWrapper` để mô tả wrapper/list item.
8. Dùng `@JacksonXmlText` chỉ khi nội dung thực sự là text trực tiếp.
9. Khai báo namespace URI ở đúng element/attribute.
10. Kiểm tra trường hợp thiếu, rỗng, nil, một item và nhiều item.
11. Test serialize và deserialize riêng; test QName thay vì prefix.
12. Nếu XSD là hợp đồng bắt buộc, chạy schema validation độc lập.

## 24. Ghi nhớ

Trong Jackson XML, `@JacksonXmlRootElement` đặt tên root element; `@JacksonXmlProperty(localName = ...)` đặt tên child element; `@JacksonXmlProperty(isAttribute = true)` ánh xạ property thành XML attribute; `@JacksonXmlElementWrapper` điều khiển wrapper của collection; và `@JacksonXmlText` ánh xạ nội dung văn bản trực tiếp.

Hãy đọc XML schema theo đúng cấu trúc root, attribute, child element, collection wrapper và namespace rồi mới thiết kế model. Tên Java có thể giữ theo convention của ứng dụng trong khi annotation đảm bảo tên XML khớp hợp đồng. Kiểm tra bằng `XmlMapper` ở cả hai chiều, so sánh QName/structure thay vì phụ thuộc prefix hoặc indentation, và dùng XSD validator riêng khi cần xác nhận tài liệu tuân thủ schema đầy đủ.
