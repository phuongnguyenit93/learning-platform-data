# Phân biệt mô hình JSON và mô hình phần tử, thuộc tính XML

JSON và XML đều có thể biểu diễn dữ liệu có cấu trúc, nhưng chúng tổ chức thông tin theo hai mô hình khác nhau. JSON xoay quanh object, property, array và các giá trị scalar như string, number, boolean hoặc null. XML xoay quanh document có một root element, các element lồng nhau, attribute, text content, namespace và thứ tự node.

Sự khác biệt này ảnh hưởng trực tiếp đến cách Jackson ánh xạ một class Java. Với JSON, một property thường trở thành một key trong object. Với XML, cùng property đó có thể trở thành child element, XML attribute hoặc text của element bao quanh. Một List trong Java có thể được biểu diễn bằng wrapper element chứa nhiều element con, hoặc bằng nhiều element cùng tên đứng cạnh nhau.

Jackson XML module cung cấp XmlMapper và các annotation như JacksonXmlRootElement, JacksonXmlProperty, JacksonXmlElementWrapper và JacksonXmlText để mô tả hình dạng XML. Hiểu mô hình XML trước khi viết DTO giúp tránh giả định rằng JSON object và XML element là hai cách viết tương đương một-một.

## 1. JSON object và XML element không phải cùng một khái niệm

Một JSON object là tập hợp các property được đặt tên:

~~~json
{
  "id": 42,
  "name": "Mai",
  "active": true
}
~~~

Các key id, name và active đều là property của object. JSON không có cú pháp riêng để phân biệt một property là attribute hay element. Giá trị của property có thể là scalar, object, array hoặc null.

XML sử dụng element để tạo cây cấu trúc:

~~~xml
<user>
    <id>42</id>
    <name>Mai</name>
    <active>true</active>
</user>
~~~

Ở đây user là root element; id, name và active là child element. Giá trị của mỗi child element nằm trong text content giữa thẻ mở và thẻ đóng.

XML cũng có attribute:

~~~xml
<user id="42" active="true">
    <name>Mai</name>
</user>
~~~

id và active lúc này là attribute của element user, còn name vẫn là child element. Nếu chỉ nhìn vào dữ liệu nghiệp vụ, hai XML ví dụ có thể biểu diễn cùng thông tin, nhưng cấu trúc và quy tắc xử lý của chúng khác nhau.

Trong JSON không có một cú pháp chuẩn tương đương trực tiếp với XML attribute. Khi chuyển XML sang JSON hoặc ánh xạ XML vào Java, ứng dụng cần chọn một quy ước để phân biệt attribute với child element.

## 2. Mô hình dữ liệu của JSON

JSON có sáu nhóm giá trị cơ bản:

- Object: tập hợp property có tên.
- Array: danh sách giá trị có thứ tự.
- String: chuỗi ký tự.
- Number: số.
- Boolean: true hoặc false.
- Null: giá trị rỗng được biểu diễn tường minh.

Ví dụ một đơn hàng:

~~~json
{
  "orderId": "ORD-100",
  "status": "PAID",
  "customer": {
    "id": 42,
    "name": "Mai"
  },
  "items": [
    {
      "sku": "BOOK-01",
      "quantity": 2
    },
    {
      "sku": "PEN-02",
      "quantity": 5
    }
  ]
}
~~~

Object order có property customer là một object lồng nhau và items là một array object. Tên property cho biết vai trò của từng giá trị. JSON object không có khái niệm namespace, attribute, text node hay comment như XML.

JSON object không bắt buộc có root object; một JSON document có thể là object, array hoặc scalar tùy ngữ cảnh. Tuy nhiên, nhiều API chọn root object để biểu diễn một tài nguyên.

## 3. Mô hình dữ liệu của XML

XML document là một cây node có một document element duy nhất. Một element có thể chứa:

- Attribute.
- Text content.
- Child element.
- Comment hoặc processing instruction ở các vị trí XML cho phép.
- Các node text và element xen kẽ nhau trong nội dung hỗn hợp.

Ví dụ:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<order orderId="ORD-100" status="PAID">
    <customer id="42">
        <name>Mai</name>
    </customer>
    <items>
        <item sku="BOOK-01">
            <quantity>2</quantity>
        </item>
        <item sku="PEN-02">
            <quantity>5</quantity>
        </item>
    </items>
</order>
~~~

XML dùng element để tổ chức cây và attribute để gắn metadata vào một element. Element có thể chứa element con, text hoặc cả hai. Một attribute chỉ có một giá trị văn bản và không thể chứa một cây element lồng nhau.

XML cũng có namespace để phân biệt các tên element/attribute đến từ những miền từ vựng khác nhau. Hai element có cùng local name nhưng namespace URI khác nhau là hai tên XML khác nhau.

## 4. Bảng so sánh JSON và XML

| Khái niệm | JSON | XML |
|---|---|---|
| Đơn vị cấu trúc | Object và array | Element và document tree |
| Property có tên | Key trong object | Thường là child element hoặc attribute |
| Giá trị scalar | String, number, boolean, null | Text content hoặc attribute value |
| Danh sách | Array | Nhiều element cùng tên, thường có hoặc không có wrapper |
| Root | Có thể là object, array hoặc scalar | Một document element duy nhất |
| Metadata tên | Không có namespace chuẩn | Namespace URI và prefix |
| Nội dung văn bản | Giá trị string | Text node bên trong element |
| Thuộc tính | Không có loại riêng | Attribute trên start tag |
| Nội dung hỗn hợp | Không có text xen kẽ property theo mô hình XML | Có thể có text và child element xen kẽ |
| Comment | Không thuộc dữ liệu JSON chuẩn | Có thể xuất hiện trong XML document |
| Thứ tự | Thứ tự property object không nên mang ý nghĩa nghiệp vụ | Thứ tự child element có thể có ý nghĩa theo schema |
| Kiểu scalar | Number và boolean được biểu diễn trực tiếp | Thường là lexical text, cần schema hoặc kiểu đích để diễn giải |

Khác biệt lớn nhất đối với Jackson là một Java property không tự động có một biểu diễn XML duy nhất. Cần quyết định property đó sẽ là element, attribute, text content hay một cấu trúc collection.

## 5. Jackson xử lý XML bằng module riêng

Jackson Databind cung cấp ObjectMapper cho JSON. Để đọc và ghi XML, dự án cần module jackson-dataformat-xml và lớp XmlMapper.

Dependency Maven thường có dạng:

~~~xml
<dependency>
    <groupId>com.fasterxml.jackson.dataformat</groupId>
    <artifactId>jackson-dataformat-xml</artifactId>
    <version>phiên-bản-Jackson-đang-dùng</version>
</dependency>
~~~

Hãy đồng bộ phiên bản jackson-dataformat-xml với các artifact Jackson Core và Databind còn lại, thường bằng Jackson BOM hoặc dependency management của dự án. Không nên trộn các phiên bản khác nhau tùy tiện.

Tạo mapper:

~~~java
import com.fasterxml.jackson.dataformat.xml.XmlMapper;

XmlMapper xmlMapper = new XmlMapper();
~~~

XmlMapper dùng API databind quen thuộc:

~~~java
String xml = xmlMapper.writeValueAsString(value);
User user = xmlMapper.readValue(xml, User.class);
~~~

XmlMapper không biến JSON thành XML bằng cách đổi dấu ngoặc. Nó dùng XML parser/generator để đọc và ghi cấu trúc element, attribute và text theo quy tắc của module XML.

## 6. Một Java class có thể có biểu diễn JSON và XML khác nhau

Xét class:

~~~java
public class User {
    private long id;
    private String name;
    private boolean active;

    // Getter và setter
}
~~~

Với ObjectMapper JSON, output có thể là:

~~~json
{
  "id": 42,
  "name": "Mai",
  "active": true
}
~~~

Với XmlMapper, các property có thể trở thành child element:

~~~xml
<User>
    <id>42</id>
    <name>Mai</name>
    <active>true</active>
</User>
~~~

Đây là biểu diễn XML mặc định theo cách introspection của mapper và cấu hình tên hiện tại. Nếu hợp đồng yêu cầu root name, attribute hoặc wrapper cụ thể, hãy khai báo rõ bằng annotation XML.

Một class Java không tự nói rằng id phải là XML attribute. Điều đó là một quyết định của hợp đồng XML.

## 7. Các annotation XML chính của Jackson

Jackson XML module cung cấp các annotation trong package com.fasterxml.jackson.dataformat.xml.annotation:

| Annotation | Mục đích |
|---|---|
| JacksonXmlRootElement | Đặt tên và namespace cho root element của kiểu |
| JacksonXmlProperty | Đặt local name, namespace và xác định property là attribute |
| JacksonXmlElementWrapper | Điều khiển element wrapper bao quanh collection |
| JacksonXmlText | Ánh xạ property vào text content của element |
| JacksonXmlCData | Yêu cầu ghi text dưới dạng CDATA khi phù hợp |

Các annotation này mô tả cách một kiểu Java được biểu diễn trong XML. Có thể kết hợp chúng với annotation Jackson Databind thông thường như JsonIgnore, JsonProperty, JsonCreator hoặc JsonInclude khi mục tiêu và phiên bản hỗ trợ.

Không nên giả định mọi annotation JAXB hoặc annotation XML của thư viện khác đều được Jackson XML hiểu. Hãy dùng đúng annotation mà module XML hỗ trợ hoặc cấu hình annotation introspector tương ứng.

## 8. Đặt tên root element bằng JacksonXmlRootElement

Trong XML, root element là phần tử bao ngoài document. Có thể khai báo tên root bằng JacksonXmlRootElement:

~~~java
@JacksonXmlRootElement(localName = "user")
public class User {
    private long id;
    private String name;

    // Getter và setter
}
~~~

Serialize:

~~~java
User user = new User();
user.setId(42);
user.setName("Mai");

String xml = xmlMapper.writeValueAsString(user);
~~~

Root element sẽ mang tên user theo cấu hình. Nếu không chỉ định annotation, Jackson XML cần suy ra tên root theo quy tắc mặc định của module và kiểu Java. Với hợp đồng được công bố, nên chỉ định rõ tên thay vì phụ thuộc tên class.

Tên class Java có thể thay đổi do refactor package hoặc class. Tên XML là một phần hợp đồng bên ngoài và nên ổn định độc lập với tên class.

## 9. Đặt tên child element bằng JacksonXmlProperty

JacksonXmlProperty có thể chỉ định localName cho property:

~~~java
public class User {
    @JacksonXmlProperty(localName = "display-name")
    private String displayName;

    // Getter và setter
}
~~~

XML:

~~~xml
<user>
    <display-name>Mai</display-name>
</user>
~~~

Annotation giúp ánh xạ tên Java displayName sang tên XML display-name. Điều này hữu ích khi schema XML dùng tên có dấu gạch nối, chữ hoa hoặc quy ước tên khác với Java.

localName chỉ là phần tên cục bộ. Nếu XML dùng namespace, cần xem xét thêm thuộc tính namespace.

## 10. Phân biệt child element và XML attribute

JacksonXmlProperty có thuộc tính isAttribute. Mặc định property được biểu diễn như element; đặt isAttribute = true sẽ chuyển property thành XML attribute.

~~~java
@JacksonXmlRootElement(localName = "user")
public class User {
    @JacksonXmlProperty(isAttribute = true, localName = "id")
    private long id;

    @JacksonXmlProperty(localName = "name")
    private String name;

    // Getter và setter
}
~~~

XML:

~~~xml
<user id="42">
    <name>Mai</name>
</user>
~~~

id nằm trong start tag dưới dạng attribute. name là child element có nội dung văn bản.

Có thể hình dung:

~~~text
Java property id
    |
    +--> isAttribute = true
             |
             v
        user id="42"

Java property name
    |
    +--> property thông thường
             |
             v
        <name>Mai</name>
~~~

Đây là quyết định quan trọng khi tích hợp với XML schema có quy định rõ attribute và element.

## 11. Khi nào nên dùng attribute?

Attribute thường phù hợp với metadata ngắn gắn trực tiếp với element:

- Mã định danh của element.
- Loại hoặc trạng thái mô tả element.
- Đơn vị đo.
- Flag hoặc mã phân loại.
- Thuộc tính điều khiển schema.

Ví dụ:

~~~xml
<price currency="VND" taxIncluded="true">250000</price>
~~~

currency và taxIncluded là attribute mô tả giá trị price; số tiền là text content của element price.

Attribute chỉ chứa một giá trị văn bản. Nó không thể chứa child element, không có cấu trúc lồng nhau và không thể lặp lại nhiều lần với cùng tên trên một element.

Không nên đặt một object phức tạp hoặc một danh sách dài vào attribute. Hãy dùng child element:

~~~xml
<customer>
    <address>
        <city>Ha Noi</city>
        <postalCode>100000</postalCode>
    </address>
</customer>
~~~

## 12. Khi nào nên dùng child element?

Child element phù hợp với dữ liệu có cấu trúc hoặc có thể mở rộng:

- Object lồng nhau.
- Danh sách item.
- Nội dung có thể chứa text dài.
- Giá trị có thể cần attribute riêng.
- Dữ liệu có namespace hoặc schema phức tạp.

Ví dụ:

~~~xml
<order>
    <item sku="BOOK-01">
        <quantity>2</quantity>
        <price currency="VND">120000</price>
    </item>
</order>
~~~

Element item chứa attribute sku và các element quantity, price. Mỗi node có thể có metadata và cấu trúc riêng.

Với dữ liệu nghiệp vụ có khả năng phát triển, child element thường linh hoạt hơn attribute. Tuy nhiên, hãy tuân theo XML schema hoặc hợp đồng của hệ thống đối tác thay vì tự chọn cấu trúc theo sở thích.

## 13. XML attribute không giống JSON property

Hai XML sau biểu diễn các cấu trúc khác nhau:

~~~xml
<user id="42">
    <name>Mai</name>
</user>
~~~

~~~xml
<user>
    <id>42</id>
    <name>Mai</name>
</user>
~~~

Trong JSON, hai cấu trúc tương ứng thường được mô hình hóa như:

~~~json
{
  "id": 42,
  "name": "Mai"
}
~~~

Nếu chỉ nhìn JSON, không thể biết id trong XML gốc là attribute hay child element. Khi chuyển XML sang JSON, converter cần một quy ước như đặt attribute dưới một key đặc biệt, gộp vào object hoặc dùng schema/DTO để giữ sự phân biệt.

Vì vậy, không nên thiết kế một JSON DTO rồi mong XmlMapper tự đoán chính xác vị trí attribute của từng property. Hãy khai báo isAttribute rõ ràng khi hợp đồng XML yêu cầu.

## 14. Biểu diễn text content bằng JacksonXmlText

XML element có thể chứa text trực tiếp mà không cần child element:

~~~xml
<message priority="high">Urgent</message>
~~~

Ở đây:

- priority là attribute.
- Urgent là text content của element message.

Có thể ánh xạ bằng JacksonXmlText:

~~~java
@JacksonXmlRootElement(localName = "message")
public class Message {
    @JacksonXmlProperty(isAttribute = true)
    private String priority;

    @JacksonXmlText
    private String content;

    // Getter và setter
}
~~~

Property content được ghi trực tiếp vào nội dung text của element thay vì tạo child element tên content.

JacksonXmlText hữu ích với XML schema dùng simple content hoặc complex type có attribute đi cùng text value.

## 15. Text content khác child element

Hai XML sau không tương đương về cấu trúc:

~~~xml
<message>Urgent</message>
~~~

~~~xml
<message>
    <content>Urgent</content>
</message>
~~~

XML thứ nhất có text content trực tiếp. XML thứ hai có child element content.

Với Jackson:

- Dùng JacksonXmlText nếu property đại diện text của element bao quanh.
- Dùng JacksonXmlProperty với localName nếu property cần là child element.

Nếu chọn sai, output có thể không khớp XSD hoặc ứng dụng nhận XML của đối tác có thể không đọc được.

## 16. XML có mixed content

XML hỗ trợ nội dung hỗn hợp, nơi text và child element xen kẽ:

~~~xml
<p>
    Hello <b>world</b>, welcome.
</p>
~~~

Element p có text "Hello ", child element b, rồi text ", welcome.". Đây không phải một object thông thường có các property độc lập. Thứ tự xen kẽ của text và element là một phần nội dung.

Mô hình POJO với một field String text và một field List<Bold> thường không thể tự diễn tả đầy đủ thứ tự xen kẽ nếu không có cấu trúc node trung gian.

Jackson XML hỗ trợ nhiều dạng XML phổ biến nhưng không phải mọi cấu trúc XML đều ánh xạ tự nhiên sang bean property. Với mixed content phức tạp, hãy cân nhắc:

- Dùng StAX để xử lý event/node theo thứ tự.
- Dùng DOM hoặc một tree model XML phù hợp.
- Viết custom deserializer/serializer.
- Biểu diễn nội dung thành danh sách node có type và thứ tự rõ ràng.

Không nên giả định JacksonXmlText cộng với một List child element sẽ bảo toàn chính xác mọi đoạn text xen kẽ.

## 17. Biểu diễn collection bằng wrapper element

Một JSON array:

~~~json
{
  "roles": [
    "ADMIN",
    "EDITOR"
  ]
}
~~~

Trong XML, có thể biểu diễn bằng một wrapper element roles chứa các element role:

~~~xml
<user>
    <roles>
        <role>ADMIN</role>
        <role>EDITOR</role>
    </roles>
</user>
~~~

Khai báo:

~~~java
public class User {
    @JacksonXmlElementWrapper(localName = "roles")
    @JacksonXmlProperty(localName = "role")
    private List<String> roles;

    // Getter và setter
}
~~~

JacksonXmlElementWrapper xác định element bao quanh collection. JacksonXmlProperty xác định tên từng item.

Wrapper giúp nhóm các phần tử cùng thuộc một property, đặc biệt khi XML có nhiều collection khác nhau hoặc schema quy định một container cụ thể.

## 18. Collection không có wrapper

Một schema khác có thể yêu cầu các element lặp trực tiếp bên trong parent:

~~~xml
<user>
    <role>ADMIN</role>
    <role>EDITOR</role>
</user>
~~~

Khi đó, dùng:

~~~java
public class User {
    @JacksonXmlElementWrapper(useWrapping = false)
    @JacksonXmlProperty(localName = "role")
    private List<String> roles;

    // Getter và setter
}
~~~

useWrapping = false cho biết collection không có container element riêng. Mỗi phần tử được ghi thành element role lặp lại.

Đây là khác biệt quan trọng giữa JSON array và XML repeated elements. JSON có một token array rõ ràng; XML thường biểu diễn collection bằng các sibling element có cùng tên.

## 19. Phân biệt wrapper và item element

Với collection object:

~~~java
public class Order {
    @JacksonXmlElementWrapper(localName = "items")
    @JacksonXmlProperty(localName = "item")
    private List<OrderItem> items;
}
~~~

XML:

~~~xml
<order>
    <items>
        <item>
            <sku>BOOK-01</sku>
            <quantity>2</quantity>
        </item>
        <item>
            <sku>PEN-02</sku>
            <quantity>5</quantity>
        </item>
    </items>
</order>
~~~

Hai annotation điều khiển hai cấp:

- JacksonXmlElementWrapper đặt tên container items.
- JacksonXmlProperty đặt tên từng phần tử item.

Nếu chỉ đặt tên wrapper mà không xác định item name, Jackson có thể dùng tên suy ra từ kiểu hoặc property theo cấu hình. Với schema XML công khai, nên khai báo cả hai để output ổn định.

## 20. Wrapper rỗng, collection rỗng và collection null

Các hình dạng XML có thể khác nhau:

~~~xml
<user>
    <roles/>
</user>
~~~

~~~xml
<user>
</user>
~~~

~~~xml
<user>
    <roles>
        <role>ADMIN</role>
    </roles>
</user>
~~~

Chúng có thể lần lượt biểu thị collection rỗng, property không xuất hiện hoặc collection có phần tử. Null còn phụ thuộc cách serializer biểu diễn và cấu hình inclusion/null handling.

Không nên giả định null, missing và empty list có cùng nghĩa. Hãy kiểm tra XML thực tế được sinh ra và cách reader của đối tác diễn giải.

Nếu schema yêu cầu một wrapper luôn tồn tại dù không có item, cần test trường hợp list rỗng. Nếu wrapper phải bị bỏ khi null, cần cấu hình inclusion phù hợp. Cách xử lý có thể phụ thuộc phiên bản module và annotation.

## 21. XML có thứ tự element

JSON object về mặt dữ liệu thường được xem là tập property, không nên dựa vào thứ tự key để mang ý nghĩa. XML là document có thứ tự node. Với một số schema và giao thức, thứ tự child element là bắt buộc.

Ví dụ XSD có thể yêu cầu:

~~~xml
<person>
    <firstName>Mai</firstName>
    <lastName>Nguyen</lastName>
</person>
~~~

Nếu consumer yêu cầu firstName trước lastName, output theo thứ tự khác có thể không hợp lệ với schema sequence.

Jackson thường dựa vào thứ tự property được introspect/serialize, và có thể cấu hình thứ tự bằng annotation hoặc cơ chế ordering phù hợp. Với XML contract có thứ tự nghiêm ngặt, hãy kiểm tra output thực tế và dùng JsonPropertyOrder hoặc cấu hình tương ứng khi phù hợp.

Ví dụ:

~~~java
@JsonPropertyOrder({"firstName", "lastName"})
public class Person {
    private String firstName;
    private String lastName;
}
~~~

Không nên dựa vào thứ tự field khai báo trong source như một bảo đảm schema nếu hợp đồng yêu cầu thứ tự cụ thể. Viết test kiểm tra sequence cần thiết.

## 22. Namespace là gì?

XML namespace giúp phân biệt tên element/attribute khi nhiều hệ thống hoặc vocabulary cùng dùng một local name.

Ví dụ:

~~~xml
<order xmlns="urn:shop">
    <id>100</id>
</order>
~~~

Element order và id thuộc namespace URI urn:shop do default namespace áp dụng cho element không có prefix trong phạm vi đó.

Một dạng khác dùng prefix:

~~~xml
<s:order xmlns:s="urn:shop">
    <s:id>100</s:id>
</s:order>
~~~

Prefix s chỉ là bí danh trong document. Danh tính của tên XML đến từ cặp namespace URI và local name, không phải prefix cụ thể. Hai document dùng prefix khác nhau nhưng cùng URI và local name vẫn có thể biểu diễn cùng tên mở rộng.

## 23. Khai báo namespace cho root element

Có thể khai báo namespace cho root:

~~~java
@JacksonXmlRootElement(
    localName = "order",
    namespace = "urn:shop"
)
public class Order {
    private String id;
}
~~~

Output có thể dùng default namespace hoặc prefix do XML writer chọn:

~~~xml
<order xmlns="urn:shop">
    <id>ORD-100</id>
</order>
~~~

Điều quan trọng là namespace URI đúng. Không nên kiểm thử bằng cách bắt buộc prefix phải là một chữ cụ thể nếu hợp đồng chỉ yêu cầu namespace URI.

## 24. Namespace trên property

JacksonXmlProperty cũng có thể khai báo namespace:

~~~java
public class Order {
    @JacksonXmlProperty(
        localName = "orderNumber",
        namespace = "urn:shop"
    )
    private String number;
}
~~~

Khi tích hợp nhiều namespace, có thể có các element đến từ các vocabulary khác nhau:

~~~xml
<s:order xmlns:s="urn:shop" xmlns:c="urn:common">
    <s:orderNumber>ORD-100</s:orderNumber>
    <c:currency>VND</c:currency>
</s:order>
~~~

Namespace cần được khai báo trên đúng property. Một class có thể chứa element thuộc nhiều namespace.

## 25. Default namespace và attribute

Trong XML Namespaces, default namespace áp dụng cho unprefixed element nhưng không tự áp dụng cho unprefixed attribute.

Ví dụ:

~~~xml
<user xmlns="urn:people" id="42">
    <name>Mai</name>
</user>
~~~

Element user và name thuộc urn:people. Attribute id không thuộc namespace đó vì nó không có prefix.

Nếu attribute cần namespace:

~~~xml
<user xmlns="urn:people"
      xmlns:m="urn:metadata"
      m:id="42">
    <name>Mai</name>
</user>
~~~

Khi dùng JacksonXmlProperty(namespace = ... , isAttribute = true), hãy xác nhận writer tạo namespace/prefix phù hợp và consumer nhận đúng expanded name. Không nên giả định namespace của root tự áp dụng cho attribute.

## 26. XML attribute và namespace trong Java

Ví dụ class:

~~~java
@JacksonXmlRootElement(
    localName = "user",
    namespace = "urn:people"
)
public class User {
    @JacksonXmlProperty(
        isAttribute = true,
        localName = "id",
        namespace = "urn:metadata"
    )
    private String id;

    @JacksonXmlProperty(
        localName = "name",
        namespace = "urn:people"
    )
    private String name;
}
~~~

Ý định của mapping:

- Root user thuộc urn:people.
- Attribute id thuộc urn:metadata.
- Child element name thuộc urn:people.

Prefix cụ thể trong output có thể được writer tạo tự động. Khi test, parse XML và kiểm tra namespace URI/local name sẽ bền vững hơn so sánh raw prefix.

## 27. Phân biệt local name và qualified name

Tên XML thường được hiểu qua:

- Namespace URI.
- Local name.

Ví dụ {urn:shop}order là tên mở rộng của element order trong namespace urn:shop. Prefix s trong s:order chỉ là cách viết trong document.

Khi đọc XML từ đối tác, không nên chỉ kiểm tra chuỗi tag s:order vì đối tác có thể đổi prefix thành ord:order mà không đổi namespace URI. Hãy so sánh namespace URI và local name.

Với Jackson annotation, localName đặt phần tên cục bộ; namespace đặt URI. Prefix thường được XML writer quản lý. Nếu hợp đồng yêu cầu prefix cố định vì một hệ thống cũ xử lý sai namespace, đó là yêu cầu đặc biệt cần xử lý ở tầng XML writer/namespace configuration thay vì nhầm prefix với danh tính namespace.

## 28. XML scalar là text, không có kiểu number/boolean trực tiếp trong cú pháp

JSON:

~~~json
{
  "quantity": 2,
  "active": true
}
~~~

XML:

~~~xml
<product>
    <quantity>2</quantity>
    <active>true</active>
</product>
~~~

Trong XML, nội dung quantity và active là text. Kiểu số nguyên hoặc boolean được diễn giải dựa trên kiểu Java đích, schema XSD hoặc quy tắc của ứng dụng.

XML Schema có các kiểu như xs:int, xs:decimal và xs:boolean, nhưng bản thân XML document thường không mang type annotation trực tiếp trên từng text node nếu schema không được tham chiếu hoặc áp dụng.

Với Jackson XML, property Java int có thể nhận text "2" và được convert thành số. Nếu text là "two", mapping có thể thất bại.

Đừng nhầm việc XML parser đọc được text với việc giá trị đó hợp lệ theo kiểu Java. Parse XML document và bind XML vào DTO là hai bước khái niệm khác nhau.

## 29. Number formatting trong XML

XML text chứa giá trị số theo lexical representation:

~~~xml
<amount>1250.50</amount>
~~~

Không nên tự ý dùng dấu phân tách hàng nghìn hoặc locale giao diện:

~~~xml
<amount>1.250,50</amount>
~~~

trừ khi schema/hợp đồng quy định format đó. Một số XML Schema datatype dùng lexical form chuẩn riêng. Với decimal, dấu chấm thường là dấu thập phân theo xs:decimal.

Nếu cần format khác, hãy dùng custom serializer hoặc chuyển đổi ở tầng DTO có chủ đích. Đừng phụ thuộc locale mặc định của máy chạy.

## 30. Boolean và các giá trị lexical trong XML

XML Schema boolean chấp nhận lexical forms như true, false, 1 và 0. Tuy nhiên, các consumer có thể chỉ hỗ trợ một tập con hoặc có quy định riêng.

Ví dụ:

~~~xml
<active>true</active>
~~~

~~~xml
<active>1</active>
~~~

Nếu tích hợp với hệ thống có yêu cầu chính xác, cần xác nhận giá trị writer phát ra và reader chấp nhận. Jackson thường ghi boolean theo dạng text phù hợp với serializer/type handling; custom serializer có thể thay đổi cách biểu diễn.

Không nên giả định mọi giá trị XML boolean tùy ý như yes/no/on/off đều được chuyển thành Java boolean.

## 31. Phân biệt element rỗng, text rỗng và nil

XML có một số cách biểu diễn không có nội dung:

~~~xml
<name/>
~~~

~~~xml
<name></name>
~~~

Hai dạng trên tương đương về mặt nội dung element rỗng trong XML.

Một trường hợp khác:

~~~xml
<name xsi:nil="true"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"/>
~~~

Đây là biểu diễn nil theo XML Schema Instance khi schema cho phép nillable. Nó khác với một element rỗng có mặt.

Element không xuất hiện:

~~~xml
<user/>
~~~

khác với element name xuất hiện nhưng rỗng. Với DTO Java, các trường hợp này có thể được chuyển thành null, empty string hoặc default tùy mapper, annotation và cấu hình.

Hãy test riêng:

- Property không có element.
- Element có mặt nhưng không có text.
- Element có text rỗng.
- Element có xsi:nil.

Không nên tự động coi chúng là cùng một trạng thái nghiệp vụ.

## 32. Null trong JSON và nil trong XML

JSON có giá trị null trực tiếp:

~~~json
{
  "name": null
}
~~~

XML không có literal null trong cú pháp cơ bản. XML Schema dùng xsi:nil để biểu diễn element được đánh dấu nil khi schema cho phép; ngoài ra, một element rỗng hoặc element bị lược bỏ có thể được dùng theo hợp đồng.

Ví dụ:

~~~xml
<user xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <name xsi:nil="true"/>
</user>
~~~

Jackson XML có các quy tắc riêng khi serialize/deserialze null và empty value. Hành vi cụ thể có thể phụ thuộc version, inclusion rule, XML module feature và cấu hình property. Vì vậy, hãy xác nhận output trên đúng phiên bản dependency.

Nếu đối tác phân biệt missing với xsi:nil, cần kiểm thử cả hai chiều. Không nên chỉ kiểm tra Java property là null rồi giả định XML output đã đúng hợp đồng.

## 33. Dùng JsonInclude cho inclusion nhưng hiểu giới hạn XML

Jackson Databind có JsonInclude để điều khiển property nào được ghi:

~~~java
@JsonInclude(JsonInclude.Include.NON_NULL)
public class User {
    private String name;
    private String email;
}
~~~

Với XmlMapper, annotation này có thể ảnh hưởng inclusion property theo cơ chế Databind. Tuy nhiên, việc một null property bị bỏ, ghi thành empty element hay biểu diễn nil còn phụ thuộc module XML và cấu hình.

Nếu schema yêu cầu chính xác:

- Không xuất element khi null.
- Xuất element rỗng khi null.
- Xuất xsi:nil khi null.

hãy kiểm tra tính năng XML tương ứng của phiên bản Jackson đang dùng và viết test output. Không nên suy luận chỉ từ hành vi JSON.

## 34. CData là gì?

CDATA là cách XML đánh dấu một vùng text để parser không diễn giải các ký tự như dấu ngoặc nhọn theo cú pháp markup:

~~~xml
<description><![CDATA[<strong>Special offer</strong>]]></description>
~~~

Nội dung bên trong CDATA vẫn là text, không phải child element strong.

Jackson XML có JacksonXmlCData để yêu cầu serialize text dưới dạng CDATA trong những trường hợp được hỗ trợ:

~~~java
public class Description {
    @JacksonXmlCData
    private String content;

    // Getter và setter
}
~~~

CDATA không làm thay đổi ý nghĩa dữ liệu text sau khi parser đọc. Nó chủ yếu ảnh hưởng cách text được viết ra trong XML. Nếu nội dung chứa chuỗi kết thúc CDATA, XML writer cần xử lý theo quy tắc XML.

Không nên dùng CDATA như một cách nhúng XML con nếu ứng dụng mong parser tạo child node. CDATA chỉ là text.

## 35. Attribute không thể thay thế text content

Ví dụ:

~~~xml
<price currency="VND">250000</price>
~~~

Ở đây amount là text content của price, còn currency là attribute. Có thể ánh xạ:

~~~java
public class Price {
    @JacksonXmlProperty(isAttribute = true)
    private String currency;

    @JacksonXmlText
    private BigDecimal amount;
}
~~~

Nếu dùng JacksonXmlProperty(isAttribute = true) cho amount, output sẽ thành:

~~~xml
<price currency="VND" amount="250000"/>
~~~

Đó là một schema khác. Hãy chọn annotation dựa trên cấu trúc XML mà đối tác yêu cầu.

## 36. XML có thể có element lặp cùng tên

JSON array biểu diễn danh sách tường minh:

~~~json
{
  "phoneNumbers": [
    "0900000001",
    "0900000002"
  ]
}
~~~

XML có thể dùng:

~~~xml
<contact>
    <phoneNumber>0900000001</phoneNumber>
    <phoneNumber>0900000002</phoneNumber>
</contact>
~~~

XML không cần một cú pháp array riêng. Sự lặp lại của element cùng tên trong cùng parent biểu diễn nhiều giá trị.

Jackson XML cần biết property Java là collection và cách đặt tên element. Nếu chỉ có một phần tử, XML vẫn có thể có đúng một element phoneNumber; reader vẫn cần biết property đó là List chứ không phải scalar.

Đây là một lý do nên khai báo kiểu Java đầy đủ và annotation collection rõ ràng.

## 37. XML wrapper và cấu trúc collection lồng nhau

Một collection có thể có wrapper:

~~~xml
<contact>
    <phoneNumbers>
        <phoneNumber>0900000001</phoneNumber>
        <phoneNumber>0900000002</phoneNumber>
    </phoneNumbers>
</contact>
~~~

Hoặc không có wrapper:

~~~xml
<contact>
    <phoneNumber>0900000001</phoneNumber>
    <phoneNumber>0900000002</phoneNumber>
</contact>
~~~

Hai hình dạng có cùng dữ liệu nhưng schema khác nhau. Với JacksonXmlElementWrapper, hãy chỉ định useWrapping rõ để không phụ thuộc default của module.

## 38. Cấu hình default wrapper của module

Jackson XML có cơ chế cấu hình default wrapping cho collection thông qua JacksonXmlModule. Nếu dự án cần một quy ước chung, có thể cấu hình module trước khi tạo XmlMapper.

Ví dụ:

~~~java
JacksonXmlModule module = new JacksonXmlModule();
module.setDefaultUseWrapper(false);

XmlMapper xmlMapper = new XmlMapper(module);
~~~

Thiết lập này ảnh hưởng cách các collection không có annotation wrapper riêng được biểu diễn. Annotation trên property có thể chỉ định rõ wrapper hoặc không wrapper theo nhu cầu.

Với hợp đồng XML quan trọng, khai báo JacksonXmlElementWrapper trực tiếp trên property thường dễ đọc và ít phụ thuộc cấu hình toàn cục hơn.

## 39. Root element và XML document

XML document có một document element duy nhất. Một JSON value có thể là array hoặc scalar ở root, nhưng XML cần một element bao quanh nội dung.

JSON root array:

~~~json
[
  {"id": 1},
  {"id": 2}
]
~~~

XML thường cần wrapper:

~~~xml
<users>
    <user id="1"/>
    <user id="2"/>
</users>
~~~

Khi serialize một List trực tiếp bằng XmlMapper, module có thể tạo một root/wrapper theo cơ chế XML của nó và cấu hình hiện tại. Nếu hợp đồng yêu cầu tên root cụ thể, nên tạo wrapper class:

~~~java
@JacksonXmlRootElement(localName = "users")
public class Users {
    @JacksonXmlElementWrapper(useWrapping = false)
    @JacksonXmlProperty(localName = "user")
    private List<User> users;
}
~~~

Wrapper class làm rõ root element và tên phần tử lặp. Nó cũng tránh phụ thuộc vào cách mapper xử lý root collection trong một phiên bản cụ thể.

## 40. Ví dụ đầy đủ: ánh xạ Order sang XML

Model:

~~~java
@JacksonXmlRootElement(localName = "order")
public class Order {
    @JacksonXmlProperty(isAttribute = true, localName = "orderId")
    private String orderId;

    @JacksonXmlProperty(isAttribute = true, localName = "status")
    private String status;

    @JacksonXmlProperty(localName = "customer")
    private Customer customer;

    @JacksonXmlElementWrapper(localName = "items")
    @JacksonXmlProperty(localName = "item")
    private List<OrderItem> items;

    // Getter và setter
}
~~~

~~~java
public class Customer {
    @JacksonXmlProperty(isAttribute = true, localName = "id")
    private long id;

    @JacksonXmlProperty(localName = "name")
    private String name;

    // Getter và setter
}
~~~

~~~java
public class OrderItem {
    @JacksonXmlProperty(isAttribute = true, localName = "sku")
    private String sku;

    @JacksonXmlProperty(localName = "quantity")
    private int quantity;

    // Getter và setter
}
~~~

XML minh họa:

~~~xml
<order orderId="ORD-100" status="PAID">
    <customer id="42">
        <name>Mai</name>
    </customer>
    <items>
        <item sku="BOOK-01">
            <quantity>2</quantity>
        </item>
        <item sku="PEN-02">
            <quantity>5</quantity>
        </item>
    </items>
</order>
~~~

Trong ví dụ này:

- order là root element.
- orderId và status là attribute của order.
- customer là child element.
- id là attribute của customer.
- name là child element của customer.
- items là wrapper element.
- item là element lặp trong wrapper.
- sku là attribute của từng item.
- quantity là child element của item.

Mô hình Java và XML không cần có số lượng class hoặc property giống hệt số node XML. Annotation quyết định cách chuyển đổi giữa chúng.

## 41. Đọc và ghi XML bằng XmlMapper

Ghi:

~~~java
XmlMapper xmlMapper = new XmlMapper();

String xml = xmlMapper.writeValueAsString(order);
~~~

Đọc:

~~~java
Order restored = xmlMapper.readValue(xml, Order.class);
~~~

Có thể đọc từ file hoặc stream:

~~~java
try (InputStream input = Files.newInputStream(path)) {
    Order order = xmlMapper.readValue(input, Order.class);
}
~~~

~~~java
try (OutputStream output = Files.newOutputStream(path)) {
    xmlMapper.writeValue(output, order);
}
~~~

XmlMapper vẫn dùng exception và databind machinery của Jackson. Lỗi cú pháp XML, lỗi ánh xạ kiểu, lỗi I/O và lỗi cấu hình cần được phân biệt như khi làm việc với JSON, dù exception parser XML có thể khác parser JSON.

## 42. Một property có thể dùng tên khác nhau trong JSON và XML

Có trường hợp API JSON dùng camelCase nhưng XML schema dùng tên có dấu gạch nối hoặc tên viết hoa. Có thể kết hợp annotation JSON và XML để cùng Java model phục vụ hai định dạng, nhưng cần kiểm tra annotation introspection và phiên bản Jackson.

Ví dụ:

~~~java
public class User {
    @JsonProperty("displayName")
    @JacksonXmlProperty(localName = "display-name")
    private String displayName;
}
~~~

JSON:

~~~json
{
  "displayName": "Mai"
}
~~~

XML:

~~~xml
<User>
    <display-name>Mai</display-name>
</User>
~~~

Đây là một lợi ích của việc tách model Java khỏi tên wire format. Tuy nhiên, khi hai hợp đồng phát triển độc lập hoặc có cấu trúc khác nhau sâu hơn, DTO riêng thường dễ bảo trì hơn.

## 43. Có nên dùng chung một DTO cho JSON và XML?

Có thể dùng chung nếu:

- Cấu trúc nghiệp vụ tương đối giống nhau.
- Khác biệt chủ yếu nằm ở tên property hoặc cách biểu diễn attribute/element.
- Không có mixed content phức tạp.
- Collection và namespace có thể mô tả rõ bằng annotation.
- Hai hợp đồng thay đổi cùng nhau hoặc được quản lý chặt.

Nên dùng DTO riêng nếu:

- XML có nhiều attribute, namespace hoặc wrapper đặc thù.
- JSON có object/array shape khác đáng kể.
- XML có mixed content hoặc schema sequence nghiêm ngặt.
- Hai hệ thống có semantics khác nhau.
- Annotation định dạng làm class Java khó hiểu hoặc gây xung đột.

Một lựa chọn là dùng domain model chung và hai lớp DTO ở biên:

~~~text
              Domain model
               /       \
              v         v
        JSON DTO      XML DTO
              |         |
         ObjectMapper  XmlMapper
              |         |
              v         v
          JSON API    XML partner
~~~

DTO riêng làm rõ hợp đồng của từng định dạng và tránh để annotation XML chi phối thiết kế API JSON.

## 44. Annotation JSON có hoạt động với XmlMapper không?

Jackson XML dựa trên Jackson Databind nên nhiều annotation chung như JsonProperty, JsonIgnore, JsonCreator và JsonInclude có thể được sử dụng trong XML mapping.

Tuy nhiên:

- JsonProperty chủ yếu mô tả tên property theo cơ chế Databind; XML module còn có localName/namespace riêng.
- JsonIgnore có thể loại property khỏi cả JSON và XML nếu cùng model được dùng.
- JsonInclude ảnh hưởng inclusion nhưng biểu diễn null/empty trong XML cần được kiểm tra riêng.
- JsonTypeInfo có thể tham gia polymorphic mapping nhưng hình dạng XML không giống JSON.
- Annotation XML chuyên biệt quyết định attribute, wrapper, text và root.

Không nên giả định annotation JSON nào cũng có ý nghĩa tương đương trong XML. Hãy đọc output XML và test deserialize bằng đúng XmlMapper.

## 45. Không dùng ObjectMapper JSON để đọc XML

ObjectMapper JSON và XmlMapper có parser/generator khác nhau:

~~~java
ObjectMapper jsonMapper = new ObjectMapper();
XmlMapper xmlMapper = new XmlMapper();
~~~

JSON:

~~~java
User user = jsonMapper.readValue(json, User.class);
~~~

XML:

~~~java
User user = xmlMapper.readValue(xml, User.class);
~~~

Không nên gọi JSON ObjectMapper rồi kỳ vọng nó tự nhận diện XML. XML có cú pháp document và namespace khác với JSON grammar.

Nếu ứng dụng hỗ trợ cả hai định dạng, hãy xác định media type hoặc định dạng nguồn trước rồi chọn mapper tương ứng. Không nên đoán định dạng bằng cách thử parse lần lượt nếu giao thức đã cung cấp Content-Type.

## 46. XML declaration và encoding

XML document có thể có declaration:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
~~~

Declaration mô tả XML version và encoding. JSON không có declaration tương đương trong nội dung document; encoding thường được quy định bởi giao thức hoặc cách truyền byte.

Khi ghi XML cho đối tác, cần kiểm tra:

- Có yêu cầu XML declaration hay không.
- Encoding phải là UTF-8 hay một encoding khác.
- Output stream và declaration có nhất quán không.
- Có BOM hay không theo yêu cầu tích hợp.

Khi đọc từ InputStream, XML parser có thể dựa vào byte order mark và declaration để xác định encoding. Khi đọc từ Reader, ứng dụng đã giải mã byte thành character và chịu trách nhiệm chọn charset đúng.

Không nên chỉ đổi chuỗi XML thành byte bằng charset mặc định của JVM. Hãy dùng UTF-8 tường minh nếu hợp đồng yêu cầu UTF-8.

## 47. XML comment và processing instruction không phải POJO property thông thường

XML có thể chứa comment:

~~~xml
<!-- generated by billing service -->
<invoice>
    <id>INV-100</id>
</invoice>
~~~

Và processing instruction:

~~~xml
<?xml-stylesheet type="text/xsl" href="invoice.xsl"?>
~~~

Các node này thuộc cấu trúc document XML, nhưng không tự động trở thành property thông thường của một JavaBean. Nếu ứng dụng cần bảo toàn comment, processing instruction hoặc lexical details, databind POJO có thể không đủ.

Hãy dùng parser/tree API phù hợp hoặc xử lý trực tiếp XML document nếu cần giữ các node ngoài dữ liệu nghiệp vụ.

## 48. XML schema và thứ tự bắt buộc

Một XSD có thể quy định sequence:

~~~xml
<xs:sequence>
    <xs:element name="id" type="xs:string"/>
    <xs:element name="name" type="xs:string"/>
    <xs:element name="active" type="xs:boolean"/>
</xs:sequence>
~~~

Điều này yêu cầu các child element xuất hiện theo thứ tự id, name, active trong XML hợp lệ theo schema.

Jackson XmlMapper không tự động thay thế một XSD validator đầy đủ. Nó tập trung vào parse/generate XML và ánh xạ dữ liệu. Nếu cần xác nhận document tuân thủ XSD, hãy dùng validator XML Schema riêng sau khi serialize hoặc trước khi bind theo quy trình phù hợp.

Ví dụ Java có thể tạo được XML well-formed nhưng vẫn không hợp lệ với XSD vì thiếu element bắt buộc, sai thứ tự hoặc namespace sai.

## 49. Well-formed XML khác valid XML

Một document well-formed tuân theo cú pháp XML:

- Có một root element.
- Thẻ mở/đóng khớp nhau.
- Attribute được đặt trong dấu nháy.
- Element lồng nhau đúng cấu trúc.
- Tên và ký tự tuân theo quy tắc XML.

Một document valid theo XSD còn phải đáp ứng schema:

- Element bắt buộc phải có.
- Kiểu dữ liệu phù hợp.
- Cardinality đúng.
- Thứ tự element đúng nếu sequence yêu cầu.
- Attribute và namespace đúng.

XmlMapper có thể đọc một XML well-formed nhưng không đúng XSD nếu kiểu Java cho phép ánh xạ. Nếu hợp đồng yêu cầu schema validation, hãy thực hiện bước validation riêng.

## 50. XML tree model và JsonNode

Jackson có tree model JsonNode. XmlMapper cũng có thể đọc XML vào cây Jackson:

~~~java
JsonNode root = xmlMapper.readTree(xml);
~~~

Tree này vẫn là mô hình node của Jackson, không phải một DOM XML đầy đủ. Cách biểu diễn attribute, repeated element, text và namespace trong tree phụ thuộc quy tắc của Jackson XML module.

Ví dụ, khi XML có nhiều element cùng tên, module có thể cần biểu diễn chúng thành array-like node. Attribute và text có thể được biểu diễn theo quy ước riêng của module. Vì vậy, không nên tự đoán key nội bộ trong JsonNode nếu chưa kiểm tra output trên phiên bản đang dùng.

Nếu cần xử lý XML theo QName, node type, comment hoặc mixed content, DOM/StAX thường thể hiện mô hình XML trực tiếp và rõ ràng hơn.

## 51. DOM và StAX khác gì với XmlMapper?

XmlMapper phù hợp khi muốn ánh xạ XML vào POJO theo cách gần giống Databind JSON.

DOM tạo một cây tài liệu trong bộ nhớ:

- Dễ truy cập node bất kỳ.
- Có thể chỉnh sửa cấu trúc document.
- Có thể tốn bộ nhớ với file lớn.

StAX là API streaming/event:

- Đọc hoặc ghi tuần tự.
- Phù hợp với tài liệu lớn.
- Có thể xử lý mixed content và thứ tự node rõ ràng.
- Cần viết logic xử lý event chi tiết hơn.

Lựa chọn:

| Nhu cầu | Công cụ phù hợp |
|---|---|
| XML có cấu trúc ổn định, ánh xạ vào DTO | XmlMapper |
| Cần tree XML để truy vấn/chỉnh sửa nhiều node | DOM |
| File lớn hoặc xử lý tuần tự | StAX |
| Mixed content phức tạp, cần giữ thứ tự text/element | StAX hoặc DOM |
| Cần kiểm tra XSD | XML Schema Validator kết hợp parser phù hợp |

Không nên ép mọi XML vào POJO nếu cấu trúc của nó thực chất là document markup.

## 52. XML attribute và element có thể cùng tên không?

Một element có thể có attribute và child element cùng local name:

~~~xml
<item code="A1">
    <code>Display code</code>
</item>
~~~

Về cú pháp XML, attribute code và child element code là hai node khác nhau. Trong một Java class, việc ánh xạ hai property cùng localName có thể gây xung đột hoặc cần cấu hình cẩn thận.

Nếu schema có cấu trúc như vậy, hãy dùng property Java có tên phân biệt và annotation XML rõ ràng. Sau đó kiểm tra xem phiên bản Jackson XML xử lý metadata đó ra sao; nếu không biểu diễn được rõ, custom serializer/deserializer hoặc StAX có thể phù hợp hơn.

## 53. Một element có thể có cả attribute và child element

Ví dụ:

~~~xml
<product sku="BOOK-01" category="books">
    <name>Jackson Guide</name>
    <price currency="VND">250000</price>
</product>
~~~

Product có attribute sku và category, đồng thời có child element name và price. Price cũng có attribute currency và text content.

Java model:

~~~java
public class Product {
    @JacksonXmlProperty(isAttribute = true)
    private String sku;

    @JacksonXmlProperty(isAttribute = true)
    private String category;

    @JacksonXmlProperty(localName = "name")
    private String name;

    @JacksonXmlProperty(localName = "price")
    private Price price;
}
~~~

~~~java
public class Price {
    @JacksonXmlProperty(isAttribute = true)
    private String currency;

    @JacksonXmlText
    private BigDecimal amount;
}
~~~

Mỗi element có thể kết hợp metadata attribute với text hoặc child element. Điều này không tương đương với một JSON property đơn giản nếu không có quy ước chuyển đổi rõ ràng.

## 54. Xử lý tên XML có dấu gạch nối

Tên XML có thể dùng dấu gạch nối:

~~~xml
<customer-info>
    <first-name>Mai</first-name>
    <last-name>Nguyen</last-name>
</customer-info>
~~~

Java convention thường dùng camelCase. Có thể ánh xạ:

~~~java
@JacksonXmlRootElement(localName = "customer-info")
public class CustomerInfo {
    @JacksonXmlProperty(localName = "first-name")
    private String firstName;

    @JacksonXmlProperty(localName = "last-name")
    private String lastName;
}
~~~

Không nên giả định naming strategy JSON như SNAKE_CASE sẽ tự tạo đúng mọi tên XML theo schema. Nếu XML contract dùng tên đặc thù, annotation localName tường minh dễ kiểm soát hơn.

## 55. Namespace và tên property khi deserialize

Khi đọc XML, prefix không phải định danh ổn định. Ví dụ hai document:

~~~xml
<s:order xmlns:s="urn:shop">
    <s:id>100</s:id>
</s:order>
~~~

~~~xml
<ord:order xmlns:ord="urn:shop">
    <ord:id>100</ord:id>
</ord:order>
~~~

Cả hai dùng cùng namespace URI urn:shop và local name order/id. Reader đúng chuẩn cần quan tâm expanded name, không phải chuỗi prefix.

Khi dùng JacksonXmlRootElement và JacksonXmlProperty, khai báo namespace URI cần thiết. Test với document dùng prefix khác nhau để xác nhận reader không phụ thuộc bí danh prefix cụ thể.

## 56. Không đồng nhất XML attribute với annotation JsonProperty

JsonProperty chỉ định tên property trong cơ chế Databind. Nó không tự biến property thành XML attribute.

Ví dụ:

~~~java
public class User {
    @JsonProperty("user_id")
    private long id;
}
~~~

Với JSON, key có thể là user_id. Với XML, property vẫn cần annotation XML nếu muốn nó là attribute:

~~~java
public class User {
    @JsonProperty("user_id")
    @JacksonXmlProperty(isAttribute = true, localName = "userId")
    private long id;
}
~~~

JSON và XML có thể dùng hai tên khác nhau nhưng cùng ánh xạ đến field Java id. Hãy kiểm tra cả hai mapper vì annotation và property introspection có thể tương tác.

## 57. XML polymorphism khác JSON polymorphism

JSON thường đặt type discriminator trong object:

~~~json
{
  "kind": "card",
  "amount": 250000
}
~~~

XML có thể dùng attribute:

~~~xml
<payment kind="card">
    <amount>250000</amount>
</payment>
~~~

Hoặc dùng element:

~~~xml
<payment>
    <kind>card</kind>
    <amount>250000</amount>
</payment>
~~~

Hai cấu trúc XML này khác nhau. Khi dùng JsonTypeInfo với XmlMapper, cần xác nhận hình dạng type metadata mà module XML tạo ra và cách reader của đối tác yêu cầu. Nếu schema XML có discriminator attribute cụ thể, có thể cần cấu hình type property/annotation XML hoặc custom type resolver.

Không nên suy luận rằng include = PROPERTY trong JSON sẽ luôn tạo cùng một hình dạng property trong XML. Hãy viết test XML thực tế cho từng subtype.

## 58. XML element order và collection order

Một collection trong XML thường được biểu diễn bằng các element lặp. Thứ tự phần tử có thể mang ý nghĩa:

~~~xml
<steps>
    <step>Validate</step>
    <step>Authorize</step>
    <step>Capture</step>
</steps>
~~~

List Java giữ thứ tự phần tử, nên Jackson có thể ghi theo thứ tự List. Không nên dùng Set nếu thứ tự trong XML có ý nghĩa.

Với object property, cần chú ý thứ tự child element nếu XSD dùng sequence. Có thể sử dụng JsonPropertyOrder hoặc cơ chế sắp xếp phù hợp để bảo đảm output.

## 59. XML attribute order không nên mang ý nghĩa

Hai start tag:

~~~xml
<user id="42" active="true"/>
~~~

~~~xml
<user active="true" id="42"/>
~~~

Tương đương về mặt XML. Thứ tự attribute không có ý nghĩa ngữ nghĩa như thứ tự child element trong một sequence.

Do đó, test XML không nên thất bại chỉ vì writer đổi thứ tự attribute, trừ khi đang kiểm tra một hệ thống cũ có hành vi không chuẩn và yêu cầu đặc biệt.

## 60. XML parser và bảo mật nguồn dữ liệu

XML có các tính năng như DTD và entity. Khi đọc XML từ nguồn không tin cậy, cần bảo đảm parser được cấu hình theo chính sách an toàn của ứng dụng, đặc biệt với external entity và truy cập tài nguyên bên ngoài.

Jackson XML sử dụng StAX implementation ở bên dưới. Hành vi bảo mật có thể phụ thuộc StAX provider và cấu hình factory. Không nên giả định mọi runtime đều có cùng mặc định.

Với dữ liệu không tin cậy:

- Dùng phiên bản thư viện parser được cập nhật.
- Kiểm tra cấu hình DTD/external entity theo StAX provider.
- Không cho phép XML document tùy ý truy cập file hoặc URL bên ngoài.
- Giới hạn kích thước, độ sâu và thời gian xử lý nếu nguồn có thể gây tải lớn.
- Kiểm thử bằng cấu hình runtime production.

Đây là phần cấu hình parser ở tầng XML, khác với việc chọn property là attribute hay element, nhưng cần được xem xét khi đưa XML vào hệ thống.

## 61. Kiểm thử XML bằng cấu trúc thay vì raw string

So sánh raw XML string dễ bị ảnh hưởng bởi:

- Khoảng trắng và xuống dòng.
- Thứ tự attribute.
- Prefix namespace.
- XML declaration.
- Cách escape text.
- Cách writer tự chọn prefix.

Nếu hợp đồng không yêu cầu byte-for-byte equality, hãy parse XML và kiểm tra node:

~~~java
DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
factory.setNamespaceAware(true);

DocumentBuilder builder = factory.newDocumentBuilder();
Document document = builder.parse(
    new InputSource(new StringReader(xml))
);

Element root = document.getDocumentElement();
assertEquals("order", root.getLocalName());
assertEquals("ORD-100", root.getAttribute("orderId"));
~~~

Trong ứng dụng thực tế, parser dùng trong test cũng cần cấu hình an toàn và namespace-aware. Với XML có namespace, kiểm tra localName và namespace URI thay vì chỉ tagName.

## 62. Kiểm thử round-trip XML

Một test cơ bản:

~~~java
Order original = createOrder();

String xml = xmlMapper.writeValueAsString(original);
Order restored = xmlMapper.readValue(xml, Order.class);

assertEquals(original.getOrderId(), restored.getOrderId());
assertEquals(original.getStatus(), restored.getStatus());
assertEquals(
    original.getItems().size(),
    restored.getItems().size()
);
~~~

Round-trip kiểm tra mapper đọc được output của chính nó. Nhưng điều đó chưa đủ để chứng minh tương thích với XML của đối tác. Hai chiều có thể cùng sai theo một cách giống nhau.

Hãy thêm fixture XML do đối tác cung cấp hoặc XML mẫu theo XSD:

~~~java
Order order = xmlMapper.readValue(partnerFixture, Order.class);
~~~

Sau đó xác nhận property, namespace, attribute, collection và giá trị text đúng.

## 63. Kiểm thử attribute và element riêng

Nếu schema yêu cầu id là attribute:

~~~java
JsonNode tree = xmlMapper.readTree(xml);
~~~

Tree model có thể giúp kiểm tra output ở mức Jackson, nhưng biểu diễn attribute trong tree có quy ước riêng. Đối với hợp đồng XML, DOM hoặc XPath thường rõ ràng hơn:

~~~java
XPath xpath = XPathFactory.newInstance().newXPath();
String id = xpath.evaluate("/user/@id", document);
String name = xpath.evaluate("/user/name/text()", document);
~~~

Test xác nhận:

- id xuất hiện ở attribute.
- name xuất hiện ở child element.
- Không có child element id ngoài ý muốn.
- Namespace đúng nếu có.

## 64. Kiểm thử collection wrapper và không wrapper

Với wrapper:

~~~xml
<user>
    <roles>
        <role>ADMIN</role>
        <role>EDITOR</role>
    </roles>
</user>
~~~

Test cần xác nhận có node roles và các node role nằm bên trong.

Với unwrapped:

~~~xml
<user>
    <role>ADMIN</role>
    <role>EDITOR</role>
</user>
~~~

Test cần xác nhận các node role là sibling trực tiếp của user và không có wrapper roles.

Kiểm tra list có 0, 1 và nhiều phần tử. Trường hợp một phần tử đặc biệt quan trọng vì một số công cụ XML hoặc schema có thể diễn giải sai nếu reader không biết property là collection.

## 65. Kiểm thử namespace bằng URI

Với namespace, nên kiểm tra:

~~~java
assertEquals("urn:shop", root.getNamespaceURI());
assertEquals("order", root.getLocalName());
~~~

Không nên chỉ:

~~~java
assertEquals("s:order", root.getTagName());
~~~

vì prefix có thể thay đổi mà namespace URI không đổi.

Hãy có fixture dùng prefix khác nhau nhưng cùng namespace URI để xác nhận reader nhận diện đúng expanded name.

## 66. Kiểm thử null, empty và missing

Với một property XML có thể vắng mặt, rỗng hoặc nil, tạo các fixture riêng:

~~~xml
<user/>
~~~

~~~xml
<user>
    <name/>
</user>
~~~

~~~xml
<user xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <name xsi:nil="true"/>
</user>
~~~

Xác nhận Java property nhận null, empty string hoặc default theo đúng contract. Nếu cần phân biệt tất cả trạng thái, có thể cần một DTO/kiểu dữ liệu biểu diễn presence riêng thay vì chỉ String nullable.

## 67. Những lỗi mapping XML thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Root element sai tên | Phụ thuộc tên class/default | Dùng JacksonXmlRootElement |
| Property thành element nhưng schema cần attribute | Chưa đặt isAttribute | Dùng JacksonXmlProperty(isAttribute = true) |
| Collection có wrapper thừa hoặc thiếu | Default wrapping khác hợp đồng | Khai báo JacksonXmlElementWrapper rõ |
| Tên item sai | Chỉ cấu hình wrapper | Đặt JacksonXmlProperty cho item |
| Text bị tạo thành child element | Thiếu JacksonXmlText | Ánh xạ text content đúng |
| Prefix namespace khác dự kiến | Nhầm prefix với namespace URI | Kiểm tra URI/local name |
| XML đọc được nhưng XSD không hợp lệ | Sai thứ tự, namespace hoặc cardinality | Validate bằng XSD |
| Reader mất field chưa biết | POJO chỉ giữ property đã khai báo | Dùng JsonNode, extension map hoặc parser tree |
| Mixed content bị mất thứ tự | POJO không mô tả được xen kẽ text/element | Dùng StAX/DOM hoặc custom mapping |
| Null và empty bị nhập làm một | Chưa định nghĩa biểu diễn XML | Test missing/empty/xsi:nil |

## 68. Quy trình thiết kế DTO XML

Khi nhận một XML schema hoặc mẫu XML, hãy phân tích theo thứ tự:

1. Xác định root element và namespace URI.
2. Liệt kê child element trực tiếp.
3. Liệt kê attribute của từng element.
4. Xác định element nào chứa text trực tiếp.
5. Xác định collection dùng wrapper hay repeated sibling.
6. Ghi nhận thứ tự child element nếu schema có sequence.
7. Xác định namespace của từng element và attribute.
8. Phân biệt element missing, empty và xsi:nil.
9. Xác định scalar type và lexical format.
10. Kiểm tra mixed content, comment hoặc node cần bảo toàn.
11. Chọn POJO/XmlMapper hay DOM/StAX.
12. Viết fixture test cho cả read và write.

Sơ đồ phân tích một element:

~~~text
Element XML
    |
    +--> Attribute?
    |       |
    |       +--> Java property với isAttribute = true
    |
    +--> Child element?
    |       |
    |       +--> Java property/POJO lồng nhau
    |
    +--> Repeated child?
    |       |
    |       +--> List + wrapper hoặc unwrapped
    |
    +--> Text content?
    |       |
    |       +--> JacksonXmlText
    |
    +--> Text và element xen kẽ?
            |
            +--> Cân nhắc StAX/DOM/custom mapping
~~~

## 69. Khi nào nên chọn DTO XML riêng?

Một DTO riêng thường đáng dùng nếu XML có cấu trúc rất khác domain model:

~~~java
public class Order {
    private String id;
    private Customer customer;
    private List<OrderItem> items;
}
~~~

Domain model có thể được ánh xạ sang DTO XML:

~~~java
@JacksonXmlRootElement(localName = "PurchaseOrder")
public class PurchaseOrderXml {
    @JacksonXmlProperty(isAttribute = true, localName = "OrderNo")
    private String orderNumber;

    @JacksonXmlProperty(localName = "Buyer")
    private BuyerXml buyer;

    @JacksonXmlElementWrapper(localName = "Lines")
    @JacksonXmlProperty(localName = "Line")
    private List<OrderLineXml> lines;
}
~~~

Service chuyển domain model sang DTO XML rồi dùng XmlMapper. Lớp domain không cần mang annotation của một schema đối tác.

DTO riêng cũng giúp tránh việc annotation XML vô tình thay đổi JSON output nếu cùng class được dùng với ObjectMapper.

## 70. Phân biệt mapping với validation XML Schema

XmlMapper đảm nhiệm chuyển đổi giữa XML và Java. Nó không tự động bảo đảm mọi quy tắc XSD của đối tác đều được kiểm tra.

Ví dụ XSD có thể quy định:

- Element orderId bắt buộc.
- Attribute status chỉ nhận một tập giá trị.
- items phải có ít nhất một item.
- quantity phải là số nguyên dương.
- price phải xuất hiện trước tax.
- Element customer thuộc namespace urn:customer.

Một DTO Java có thể nhận được XML well-formed nhưng thiếu một quy tắc XSD. Nếu cần validate, dùng javax.xml.validation hoặc API XML Schema tương ứng của JDK:

~~~java
SchemaFactory schemaFactory =
    SchemaFactory.newInstance(XMLConstants.W3C_XML_SCHEMA_NS_URI);

Schema schema = schemaFactory.newSchema(xsdPath.toFile());
Validator validator = schema.newValidator();
validator.validate(new StreamSource(new StringReader(xml)));
~~~

Sau khi validation thành công, có thể dùng XmlMapper để bind XML vào POJO. Hoặc tổ chức quy trình sao cho cùng nguồn byte được parse/validate an toàn trước khi databind.

## 71. Không dùng annotation để che giấu schema không phù hợp

Nếu XML của đối tác dùng mixed content hoặc thứ tự node phức tạp, thêm nhiều annotation vào POJO có thể làm mô hình khó hiểu mà vẫn không bảo toàn đầy đủ document.

Ví dụ:

~~~xml
<paragraph>
    Intro
    <emphasis>important</emphasis>
    continuation
    <link href="https://example.test">details</link>
    ending
</paragraph>
~~~

Đây là một document markup có thứ tự text/element. Nếu ứng dụng cần giữ nguyên nội dung để chỉnh sửa hoặc phát lại, DOM/StAX hoặc một mô hình node riêng thường phù hợp hơn.

## 72. Chọn giữa JSON và XML theo hợp đồng tích hợp

JSON thường thuận tiện cho API ứng dụng vì:

- Cấu trúc object/array rõ.
- Scalar type được biểu diễn trực tiếp.
- Dễ ánh xạ với JavaScript và các API web hiện đại.
- Ít cú pháp hơn cho dữ liệu object phổ biến.

XML thường phù hợp khi:

- Hệ thống đối tác đã có XSD hoặc SOAP/XML contract.
- Namespace là một phần quan trọng của schema.
- Cần attribute và element theo cấu trúc tài liệu.
- Có mixed content hoặc markup.
- Hệ sinh thái tích hợp yêu cầu XML.

Không nên chọn XML chỉ vì có thể biểu diễn attribute, hoặc chọn JSON chỉ vì POJO ánh xạ đơn giản hơn. Hãy dùng định dạng mà giao thức và hệ thống tiêu thụ yêu cầu.

## 73. Nguyên tắc thực hành

- Xem JSON object và XML element là hai mô hình dữ liệu khác nhau.
- Xác định root element bằng JacksonXmlRootElement khi hợp đồng yêu cầu tên ổn định.
- Dùng JacksonXmlProperty để đặt local name, namespace và phân biệt attribute.
- Chỉ dùng isAttribute cho giá trị scalar phù hợp với XML attribute.
- Dùng JacksonXmlText cho text content trực tiếp của element.
- Dùng JacksonXmlElementWrapper để điều khiển collection wrapper.
- Đặt tên item bằng JacksonXmlProperty.
- Khai báo namespace URI, không phụ thuộc prefix cụ thể.
- Phân biệt attribute namespace với default namespace của element.
- Kiểm tra thứ tự child element nếu XSD dùng sequence.
- Phân biệt missing, empty và xsi:nil.
- Không giả định JsonInclude trong XML có hành vi giống JSON ở mọi trường hợp.
- Không dùng JsonProperty để thay thế cấu hình attribute/element.
- Dùng DTO XML riêng khi schema khác domain hoặc JSON model đáng kể.
- Dùng DOM/StAX cho mixed content, node order phức tạp hoặc tài liệu lớn.
- Validate XSD riêng nếu hợp đồng yêu cầu.
- Test output bằng parser/XML tree và kiểm tra namespace URI/local name.
- Dùng fixture của đối tác để kiểm tra chiều deserialize.
- Cấu hình encoding và parser an toàn theo nguồn XML.

JSON mô tả dữ liệu bằng object, property và array; XML mô tả document bằng element, attribute, text và namespace. XmlMapper giúp Jackson ánh xạ XML vào Java nhưng không xóa đi những khác biệt của hai mô hình. Khi xác định rõ property nào là attribute, element, text hay collection, khai báo namespace và wrapper tường minh, rồi kiểm thử theo XML schema thực tế, DTO sẽ phản ánh đúng hợp đồng thay vì chỉ tạo ra một XML có vẻ hợp lệ.
