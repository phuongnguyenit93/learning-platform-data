# Vai trò của module XML và XmlMapper

Jackson thường được dùng để đọc và ghi JSON, nhưng kiến trúc của nó không giới hạn ở một định dạng. Jackson tách phần xử lý dữ liệu Java khỏi phần đọc/ghi của từng định dạng. Với XML, thư viện cung cấp artifact **jackson-dataformat-xml** và lớp **XmlMapper**. XmlMapper giữ cách databinding quen thuộc của Jackson nhưng sử dụng parser/generator XML để chuyển giữa XML và object Java.

Điều này cho phép một ứng dụng dùng cùng DTO, một phần annotation và nhiều cơ chế Databind quen thuộc cho cả JSON lẫn XML. Tuy nhiên, XML có những khái niệm mà JSON không có, như element, attribute, namespace, text content và danh sách element lặp. Vì vậy, XML module bổ sung các annotation riêng để mô tả chính xác cấu trúc wire.

## 1. Module XML nằm ở đâu trong hệ sinh thái Jackson?

Các thành phần chính có vai trò khác nhau:

| Thành phần | Vai trò |
|---|---|
| jackson-core | API streaming, parser và generator cấp thấp |
| jackson-annotations | Annotation mô tả property, creator, format và metadata |
| jackson-databind | Ánh xạ giữa JSON/XML token và kiểu Java qua ObjectMapper |
| jackson-dataformat-xml | Parser/generator XML, XmlFactory, XmlMapper và annotation XML |
| StAX implementation | Bộ xử lý XML streaming được dùng bên dưới |

Jackson Core cung cấp abstraction đọc và ghi token. Databind sử dụng abstraction đó để tạo object Java. XML module bổ sung một XmlFactory và parser/generator hiểu XML, rồi kết nối chúng với cơ chế Databind.

Vì vậy, XmlMapper không phải một thư viện mapping hoàn toàn độc lập. Nó kế thừa mô hình sử dụng ObjectMapper và bổ sung cách xử lý XML.

## 2. Thêm dependency jackson-dataformat-xml

Ứng dụng cần dependency jackson-dataformat-xml:

~~~xml
<dependency>
    <groupId>com.fasterxml.jackson.dataformat</groupId>
    <artifactId>jackson-dataformat-xml</artifactId>
</dependency>
~~~

Với Gradle:

~~~groovy
dependencies {
    implementation("com.fasterxml.jackson.dataformat:jackson-dataformat-xml")
}
~~~

Nếu dự án quản lý phiên bản Jackson bằng BOM, hãy để BOM chọn phiên bản tương thích cho jackson-core, jackson-annotations, jackson-databind và jackson-dataformat-xml. Tránh trộn các artifact Jackson ở những phiên bản không tương thích.

XML module dùng StAX API để đọc và ghi XML. JDK có một StAX implementation; ứng dụng cũng có thể dùng một provider khác như Woodstox. Nếu dự án thêm provider riêng, hãy quản lý phiên bản và cấu hình của provider đó một cách nhất quán.

## 3. XmlMapper là gì?

XmlMapper nằm trong package com.fasterxml.jackson.dataformat.xml. Nó là mapper dành cho XML và cung cấp các API quen thuộc:

- readValue() đọc XML thành POJO, record hoặc kiểu Java khác.
- writeValueAsString() ghi object Java thành XML string.
- writeValue() ghi XML ra OutputStream, Writer hoặc đích phù hợp.
- readerFor() tạo ObjectReader cho kiểu đích và cấu hình đọc cụ thể.
- writerFor() tạo ObjectWriter cho kiểu nguồn và cấu hình ghi cụ thể.
- registerModule() đăng ký module Databind bổ sung.

Ví dụ:

~~~java
import com.fasterxml.jackson.dataformat.xml.XmlMapper;

XmlMapper xmlMapper = new XmlMapper();

OrderXml order = xmlMapper.readValue(xml, OrderXml.class);

String output = xmlMapper.writeValueAsString(order);
~~~

Cách sử dụng gần giống ObjectMapper. Điểm khác là parser và generator phía dưới làm việc với XML thay vì JSON.

Không dùng new ObjectMapper() để đọc XML thông thường. ObjectMapper mặc định sử dụng JSON factory; muốn xử lý XML, hãy dùng XmlMapper hoặc một ObjectMapper được xây dựng với XmlFactory tương ứng.

## 4. XmlFactory kết nối XmlMapper với parser/generator XML

XmlMapper sử dụng XmlFactory để tạo parser và generator XML. Trong trường hợp thông thường, chỉ cần:

~~~java
XmlMapper xmlMapper = new XmlMapper();
~~~

Nếu cần kiểm soát StAX provider hoặc cấu hình XML input/output, có thể tạo XmlFactory riêng rồi truyền vào mapper:

~~~java
import com.fasterxml.jackson.dataformat.xml.XmlFactory;
import com.fasterxml.jackson.dataformat.xml.XmlMapper;

XMLInputFactory inputFactory = XMLInputFactory.newFactory();
XMLOutputFactory outputFactory = XMLOutputFactory.newFactory();

XmlFactory xmlFactory =
    new XmlFactory(inputFactory, outputFactory);

XmlMapper xmlMapper = new XmlMapper(xmlFactory);
~~~

Cách này hữu ích khi cần cấu hình XML parser, kiểm soát provider hoặc tích hợp với hệ thống đã có StAX factory. API constructor/builder có thể khác theo phiên bản jackson-dataformat-xml; hãy xác nhận cách khởi tạo tương ứng với dependency đang dùng.

Thông thường không cần tự tạo XmlFactory nếu ứng dụng chỉ đọc và ghi XML theo cấu hình mặc định. Chỉ đưa factory riêng vào khi có yêu cầu rõ ràng về provider, bảo mật hoặc hành vi parsing.

## 5. Khác biệt giữa JSON và XML ảnh hưởng đến mapping

JSON object thường gồm các cặp tên/giá trị. XML có cấu trúc phong phú hơn:

~~~xml
<order id="ORD-100">
    <customer>
        <name>Linh</name>
    </customer>
    <items>
        <item>
            <sku>BOOK-01</sku>
            <quantity>2</quantity>
        </item>
    </items>
</order>
~~~

Trong ví dụ này có:

- order là root element.
- id là XML attribute.
- customer, name, items và item là elements.
- Linh, BOOK-01 và 2 là text content của element.
- item có thể lặp lại nhiều lần trong cùng một parent.

XML còn có namespace, mixed content, CDATA, attribute và element cùng tồn tại. Một property Java có thể được biểu diễn thành element hoặc attribute; vì vậy chỉ dựa vào tên property Java là chưa đủ để mô tả wire format.

XML cũng không có kiểu scalar tương tự JSON number/boolean theo cùng cách. Nội dung element và attribute thường được đọc dưới dạng text rồi chuyển sang kiểu Java theo quy tắc Databind.

## 6. Đặt tên root element bằng @JacksonXmlRootElement

Một class Java có thể được ánh xạ thành root element. Dùng @JacksonXmlRootElement để xác định tên XML rõ ràng:

~~~java
import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlRootElement;

@JacksonXmlRootElement(localName = "order")
public class OrderXml {
    public String id;
    public String status;
}
~~~

Với object:

~~~java
OrderXml order = new OrderXml();
order.id = "ORD-100";
order.status = "NEW";

String xml = xmlMapper.writeValueAsString(order);
~~~

Root element được đặt tên là order. Nếu không khai báo annotation, tên root có thể được suy ra từ kiểu Java hoặc quy tắc mặc định của mapper. Với một wire contract công khai, nên khai báo tường minh để việc đổi tên class không vô tình đổi XML.

@JacksonXmlRootElement có các thuộc tính như localName và namespace. Khi làm việc với namespace, hãy xác định URI namespace theo contract thay vì phụ thuộc vào prefix mà serializer chọn.

## 7. Đặt tên element và attribute bằng @JacksonXmlProperty

@JacksonXmlProperty điều khiển cách một property Java được biểu diễn trong XML. Nó có thể xác định tên local, namespace và property là attribute hay element.

Ví dụ class Order:

~~~java
import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlProperty;
import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlRootElement;

@JacksonXmlRootElement(localName = "order")
public class OrderXml {

    @JacksonXmlProperty(isAttribute = true, localName = "id")
    public String orderId;

    @JacksonXmlProperty(localName = "status")
    public String status;
}
~~~

XML tương ứng có dạng:

~~~xml
<order id="ORD-100">
    <status>NEW</status>
</order>
~~~

orderId vẫn là tên property Java, còn tên wire là attribute id. status được ghi thành child element.

Các điểm cần nhớ:

- isAttribute = true yêu cầu ghi property thành XML attribute.
- Mặc định property thường được ghi thành element.
- localName xác định tên XML.
- namespace xác định namespace URI cho property.
- Annotation này không thay đổi tên accessor Java.

Hãy dùng tên XML tường minh khi contract yêu cầu tên khác với tên Java hoặc khi cần phân biệt attribute và element.

## 8. Biểu diễn text content bằng @JacksonXmlText

Một XML element có thể chứa text trực tiếp thay vì một child element có tên. @JacksonXmlText đánh dấu property dùng làm text content của element.

Ví dụ:

~~~java
import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlProperty;
import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlText;
import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlRootElement;

@JacksonXmlRootElement(localName = "note")
public class NoteXml {

    @JacksonXmlProperty(isAttribute = true, localName = "lang")
    public String language;

    @JacksonXmlText
    public String text;
}
~~~

XML:

~~~xml
<note lang="vi">Xin chào</note>
~~~

Ở đây language là attribute và text là nội dung trực tiếp bên trong element. Nếu không dùng @JacksonXmlText, property text có thể được biểu diễn thành một child element theo quy tắc mặc định.

Một XML element thường có một vùng text chính được ánh xạ theo cách này. Cấu trúc mixed content phức tạp, ví dụ text xen kẽ nhiều child element, không phải lúc nào cũng ánh xạ tự nhiên vào một POJO đơn giản.

## 9. Dùng CDATA khi hợp đồng XML yêu cầu

CDATA cho phép chứa đoạn text mà XML parser không diễn giải các ký tự như dấu ngoặc nhọn hoặc dấu ampersand theo cú pháp markup thông thường.

Jackson XML có annotation @JacksonXmlCData để yêu cầu ghi property dạng text bằng CDATA:

~~~java
import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlCData;
import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlText;

public class ScriptXml {

    @JacksonXmlText
    @JacksonXmlCData
    public String content;
}
~~~

Nội dung có thể được ghi dưới dạng:

~~~xml
<script><![CDATA[if (a < b && b > 0) { run(); }]]></script>
~~~

CDATA vẫn là text content trong mô hình XML. Khi đọc, ứng dụng nhận giá trị ký tự; không nên dựa vào việc CDATA và text thường phải được giữ nguyên khác biệt sau round-trip.

CDATA không phải cách mã hóa dữ liệu nhị phân hoặc một biện pháp bảo mật. XML writer vẫn phải tuân thủ quy tắc XML, và nội dung có chuỗi kết thúc CDATA cần được xử lý đúng theo chuẩn.

## 10. Ánh xạ collection bằng @JacksonXmlElementWrapper

JSON array có dấu ngoặc vuông. XML thường biểu diễn collection bằng một element wrapper chứa nhiều child element lặp lại.

Ví dụ:

~~~xml
<order>
    <items>
        <item>
            <sku>BOOK-01</sku>
            <quantity>2</quantity>
        </item>
        <item>
            <sku>PEN-02</sku>
            <quantity>3</quantity>
        </item>
    </items>
</order>
~~~

DTO:

~~~java
import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlElementWrapper;
import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlProperty;

public class OrderXml {

    @JacksonXmlElementWrapper(localName = "items")
    @JacksonXmlProperty(localName = "item")
    public List<ItemXml> items;
}
~~~

@JacksonXmlElementWrapper xác định element bao quanh collection. @JacksonXmlProperty xác định tên mỗi phần tử bên trong.

Nên khai báo rõ cả wrapper và item name khi XML contract đã được công bố. Nếu để mapper tự suy ra tên, tên element có thể phụ thuộc property Java hoặc quy tắc mặc định.

## 11. Collection không có wrapper element

Một số schema XML yêu cầu các item lặp trực tiếp dưới parent, không có element bao ngoài:

~~~xml
<order>
    <item>
        <sku>BOOK-01</sku>
    </item>
    <item>
        <sku>PEN-02</sku>
    </item>
</order>
~~~

Có thể dùng useWrapping = false:

~~~java
public class OrderXml {

    @JacksonXmlElementWrapper(useWrapping = false)
    @JacksonXmlProperty(localName = "item")
    public List<ItemXml> items;
}
~~~

Đây là một khác biệt quan trọng so với việc serialize một List theo mặc định. Wrapper có thể là một phần bắt buộc của schema hoặc bị cấm theo contract.

Đừng nhầm tên property Java items với tên element lặp item. Hai tên có thể khác nhau và cần được khai báo riêng.

Nếu collection rỗng hoặc null, XML output có thể khác tùy inclusion policy và cấu hình wrapper. Hãy test các trường hợp collection thiếu, null, rỗng và có phần tử.

## 12. Namespace: dùng URI thay vì phụ thuộc prefix

XML namespace phân biệt các tên bằng namespace URI và local name. Prefix chỉ là bí danh trong tài liệu XML.

Ví dụ:

~~~xml
<ord:order xmlns:ord="urn:example:orders" ord:id="ORD-100">
    <ord:status>NEW</ord:status>
</ord:order>
~~~

Có thể khai báo namespace trong annotation:

~~~java
@JacksonXmlRootElement(
    localName = "order",
    namespace = "urn:example:orders"
)
public class OrderXml {

    @JacksonXmlProperty(
        isAttribute = true,
        localName = "id",
        namespace = "urn:example:orders"
    )
    public String id;

    @JacksonXmlProperty(
        localName = "status",
        namespace = "urn:example:orders"
    )
    public String status;
}
~~~

Serializer hoặc StAX provider có thể chọn prefix khác, ví dụ ns2, nhưng URI namespace vẫn là phần quan trọng của tên mở rộng XML.

Khi kiểm thử, nên xác nhận namespace URI và local name thay vì so sánh cứng toàn bộ prefix. Cũng cần lưu ý quy tắc namespace của attribute khác element: default namespace không tự áp dụng cho attribute không có prefix. Nếu attribute thuộc namespace, hãy khai báo namespace rõ và kiểm tra XML thực tế.

## 13. Ví dụ đầy đủ: Order XML với attribute, element và list

Một DTO có thể mô tả cấu trúc đơn hàng:

~~~java
@JacksonXmlRootElement(localName = "order")
public class OrderXml {

    @JacksonXmlProperty(isAttribute = true, localName = "id")
    public String id;

    @JacksonXmlProperty(localName = "customer")
    public CustomerXml customer;

    @JacksonXmlElementWrapper(localName = "items")
    @JacksonXmlProperty(localName = "item")
    public List<ItemXml> items;
}

public class CustomerXml {
    @JacksonXmlProperty(localName = "name")
    public String name;
}

public class ItemXml {
    @JacksonXmlProperty(localName = "sku")
    public String sku;

    @JacksonXmlProperty(localName = "quantity")
    public int quantity;
}
~~~

Tạo dữ liệu:

~~~java
OrderXml order = new OrderXml();
order.id = "ORD-100";

order.customer = new CustomerXml();
order.customer.name = "Linh";

ItemXml first = new ItemXml();
first.sku = "BOOK-01";
first.quantity = 2;

ItemXml second = new ItemXml();
second.sku = "PEN-02";
second.quantity = 3;

order.items = List.of(first, second);

XmlMapper mapper = new XmlMapper();
String xml = mapper.writeValueAsString(order);
~~~

XML có cấu trúc tương đương:

~~~xml
<order id="ORD-100">
    <customer>
        <name>Linh</name>
    </customer>
    <items>
        <item>
            <sku>BOOK-01</sku>
            <quantity>2</quantity>
        </item>
        <item>
            <sku>PEN-02</sku>
            <quantity>3</quantity>
        </item>
    </items>
</order>
~~~

Đọc lại:

~~~java
OrderXml restored = mapper.readValue(xml, OrderXml.class);
~~~

Đây là ví dụ POJO mutable để làm rõ mapping. Có thể dùng record hoặc immutable DTO trên phiên bản Jackson hỗ trợ phù hợp, nhưng hãy kiểm thử constructor binding với cấu trúc XML thực tế.

## 14. Annotation JSON nào có thể dùng chung?

XmlMapper kế thừa nhiều khả năng Databind của ObjectMapper, vì vậy nhiều annotation Jackson thông dụng vẫn có thể áp dụng:

- @JsonIgnore bỏ property.
- @JsonProperty cung cấp tên hoặc metadata property.
- @JsonAlias chấp nhận tên đầu vào thay thế.
- @JsonFormat định dạng giá trị phù hợp.
- @JsonInclude điều khiển inclusion.
- @JsonCreator mô tả cách tạo object.
- @JsonIgnoreProperties bỏ qua một số property.

Tuy nhiên, các annotation XML chuyên biệt mới thể hiện rõ những khái niệm như attribute, element wrapper, root element và text content:

| Yêu cầu XML | Annotation XML |
|---|---|
| Root element | @JacksonXmlRootElement |
| Element hoặc attribute | @JacksonXmlProperty |
| Wrapper của collection | @JacksonXmlElementWrapper |
| Text content | @JacksonXmlText |
| Ghi text bằng CDATA | @JacksonXmlCData |

Không nên mặc định một annotation JSON có thể mô tả mọi cấu trúc XML. Ví dụ, @JsonProperty("id") có thể ảnh hưởng tên property, nhưng để khẳng định nó là XML attribute phải dùng @JacksonXmlProperty(isAttribute = true).

## 15. Dùng cùng DTO cho JSON và XML

Một ứng dụng đôi khi cần một model Java được trao đổi dưới cả JSON lẫn XML. Có thể kết hợp annotation chung và annotation XML:

~~~java
public class CustomerDto {

    @JsonProperty("customer_id")
    @JacksonXmlProperty(isAttribute = true, localName = "id")
    public String id;

    @JsonProperty("display_name")
    @JacksonXmlProperty(localName = "name")
    public String displayName;
}
~~~

JSON mapper có thể dùng tên customer_id và display_name; XmlMapper có thể dùng attribute id và element name.

Điều này tiện khi hai wire contract tương đối gần nhau, nhưng có thể khiến DTO mang nhiều metadata định dạng. Nếu JSON và XML khác nhau nhiều về cấu trúc, hãy cân nhắc dùng DTO riêng và mapper/adapter riêng cho từng định dạng.

Không nên ép một class phục vụ hai định dạng nếu điều đó làm tên field, null semantics, collection wrapper hoặc cấu trúc lồng nhau trở nên khó hiểu.

## 16. Đăng ký module Databind bổ sung với XmlMapper

XmlMapper là một ObjectMapper chuyên cho XML, vì vậy nó cũng có thể nhận các module Databind như Java Time hoặc custom module.

Ví dụ đăng ký JavaTimeModule:

~~~java
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import com.fasterxml.jackson.dataformat.xml.XmlMapper;

XmlMapper mapper = new XmlMapper();
mapper.registerModule(new JavaTimeModule());
~~~

Module này giúp Databind xử lý các kiểu java.time theo chính sách đã cấu hình. Nếu cần định dạng ngày giờ cụ thể trong XML, hãy xác định format bằng annotation hoặc serializer tương ứng và kiểm tra XML output.

Custom serializer/deserializer được đăng ký cho một kiểu cũng có thể được dùng bởi XmlMapper, nhưng serializer phải ghi token phù hợp với XML generator. Một serializer được viết riêng cho JSON và giả định root luôn là JSON object có thể không hoạt động như mong muốn khi chạy trên XML.

Nên kiểm thử từng module với đúng mapper đích. Việc đã đăng ký JavaTimeModule hoặc custom module vào ObjectMapper JSON không tự động đăng ký nó vào một XmlMapper khác.

## 17. Không phải mọi JSON feature đều có cùng ý nghĩa với XML

Một số feature Databind dùng được ở cả hai mapper, nhưng cách biểu diễn định dạng khác nhau.

Ví dụ:
- FAIL_ON_UNKNOWN_PROPERTIES vẫn liên quan đến property không được ánh xạ.
- @JsonInclude vẫn có thể quyết định bỏ null hoặc empty.
- @JsonFormat có thể định dạng scalar phù hợp.
- @JsonPropertyOrder có thể ảnh hưởng thứ tự property được ghi, nhưng XML attribute order không phải cách biểu diễn ý nghĩa như element order.
- JSON array và XML repeated element có quy tắc cấu trúc khác nhau.
- JSON null và XML empty element hoặc xsi:nil không hoàn toàn tương đương.

Đừng sao chép nguyên cấu hình JSON rồi giả định XML contract sẽ giống hệt. Hãy kiểm tra output XML và input XML thật, đặc biệt với null, empty, collection và namespace.

## 18. Empty element, null và phần tử bị thiếu

XML có thể biểu diễn một số trạng thái theo nhiều cách:

~~~xml
<customer/>
~~~

~~~xml
<customer></customer>
~~~

~~~xml
<customer xsi:nil="true" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"/>
~~~

~~~xml
<!-- Không có element customer -->
~~~

Hai dạng đầu thường tương đương về nội dung XML rỗng. xsi:nil biểu thị nil theo XML Schema Instance nếu schema và parser xử lý theo quy ước đó. Không có element lại là trạng thái property bị thiếu.

Không nên giả định các dạng này luôn ánh xạ giống nhau thành Java null hoặc object rỗng. Hành vi còn phụ thuộc XML module, annotation, feature và cấu trúc DTO.

Nếu contract phân biệt missing, empty và nil, hãy viết test cho từng dạng XML và xác nhận XmlMapper phiên bản đang dùng tạo ra giá trị Java mong muốn. Nếu cần tuân thủ XSD, hãy dùng bước schema validation riêng thay vì dựa hoàn toàn vào databinding.

## 19. Giới hạn của XML mapping và mixed content

Jackson XML rất hữu ích cho các cấu trúc XML thông dụng, nhưng không phải mọi XML document đều ánh xạ tự nhiên thành POJO.

Những trường hợp cần cân nhắc kỹ:

- Mixed content: text xen kẽ child element.
- Nhiều namespace lồng nhau và quy tắc prefix phức tạp.
- XML Schema với substitution group, choice hoặc type derivation phức tạp.
- Element có cùng tên nhưng ý nghĩa phụ thuộc context.
- Attribute và element có tên gần nhau nhưng thuộc namespace khác.
- XML cần giữ nguyên thứ tự mọi node hoặc whitespace.
- Document cần round-trip mà không được thay đổi cấu trúc hoặc formatting.

Ví dụ mixed content:

~~~xml
<p>Hello <b>world</b>, welcome back.</p>
~~~

Một field String không thể biểu diễn đầy đủ thứ tự xen kẽ giữa text Hello, element b và text , welcome back. Với nội dung như vậy, có thể cần DOM, StAX trực tiếp hoặc custom deserializer/serializer chuyên biệt.

Nếu cần validate XML theo XSD, hãy thực hiện schema validation bằng XML validation API hoặc thư viện phù hợp. XmlMapper tập trung vào mapping giữa XML và Java; việc tạo DTO thành công không chứng minh tài liệu đã thỏa mọi ràng buộc XSD.

## 20. Bảo mật khi đọc XML: DTD và external entities

XML parser có thể hỗ trợ DTD và external entity. Nếu ứng dụng đọc XML không đáng tin cậy, cấu hình parser không phù hợp có thể dẫn đến truy cập tài nguyên ngoài dự kiến hoặc các kiểu XML entity expansion attack.

Khi tạo XmlMapper với StAX factory riêng, có thể cấu hình tắt DTD và external entity:

~~~java
XMLInputFactory inputFactory = XMLInputFactory.newFactory();

inputFactory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
inputFactory.setProperty(
    "javax.xml.stream.isSupportingExternalEntities",
    false
);

XMLOutputFactory outputFactory = XMLOutputFactory.newFactory();

XmlFactory xmlFactory =
    new XmlFactory(inputFactory, outputFactory);

XmlMapper secureMapper = new XmlMapper(xmlFactory);
~~~

Khả năng hỗ trợ property phụ thuộc StAX provider. Hãy xác nhận provider thực sự áp dụng các thiết lập này; nếu provider không hỗ trợ một thiết lập bảo mật bắt buộc, không nên âm thầm bỏ qua rồi tiếp tục đọc XML không tin cậy.

Ngoài DTD/external entities, vẫn cần giới hạn kích thước body, timeout và tài nguyên xử lý. Cấu hình parser an toàn không thay thế giới hạn request hoặc validation dữ liệu.

Không dùng XML parser được cấu hình mặc định mà chưa hiểu chính sách DTD/XXE khi đọc dữ liệu từ client, file upload hoặc đối tác bên ngoài.

## 21. Phân biệt XML well-formed, mapping thành công và schema hợp lệ

Có ba mức kiểm tra khác nhau:

| Mức | Điều được xác nhận |
|---|---|
| XML well-formed | Cú pháp XML đúng: tag đóng/mở, nesting, attribute và encoding hợp lệ |
| Jackson databinding | XML có thể ánh xạ vào kiểu Java đích theo cấu hình mapper |
| XSD/business validation | Tài liệu thỏa schema hoặc quy tắc nghiệp vụ của ứng dụng |

Một XML có thể well-formed nhưng thiếu element bắt buộc. XmlMapper có thể tạo object với field null nếu cấu hình cho phép. Điều đó không đồng nghĩa XML hợp lệ theo XSD.

Nếu cần XSD, có thể validate trước hoặc sau mapping bằng SchemaFactory và Validator tương ứng. Chọn vị trí validation dựa trên yêu cầu bảo mật, hiệu năng và cách framework tiếp nhận XML.

Các kiểm tra nghiệp vụ như mã đơn hàng tồn tại, quantity dương hoặc ngày giao hàng hợp lệ vẫn cần được thực hiện sau khi binding.

## 22. Kiểm thử XmlMapper với round-trip

Test nên kiểm tra XML output và khả năng đọc lại, không chỉ kiểm tra không có exception.

Ví dụ:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.dataformat.xml.XmlMapper;
import org.junit.jupiter.api.Test;

class XmlMapperTest {

    @Test
    void writesAndReadsOrderXml() throws Exception {
        XmlMapper mapper = new XmlMapper();

        OrderXml order = new OrderXml();
        order.id = "ORD-100";
        order.status = "NEW";

        String xml = mapper.writeValueAsString(order);

        assertTrue(xml.contains("<order"));
        assertTrue(xml.contains("id=\"ORD-100\""));
        assertTrue(xml.contains("<status>NEW</status>"));

        OrderXml restored = mapper.readValue(xml, OrderXml.class);

        assertEquals("ORD-100", restored.id);
        assertEquals("NEW", restored.status);
    }
}
~~~

Trong test thực tế, các DTO tương ứng cần được khai báo/import. Nếu XML output có thể thay đổi prefix namespace hoặc khoảng trắng theo StAX provider, hãy parse XML rồi so sánh local name, namespace URI, attribute và text thay vì so sánh nguyên chuỗi.

Bổ sung test cho:
- Root element name.
- Attribute và child element.
- Collection có wrapper và không wrapper.
- Collection rỗng, null và thiếu.
- Namespace URI.
- Text content và CDATA.
- Date/time và custom module.
- XML sai cú pháp.
- DTD/external entity bị từ chối theo policy.
- XML well-formed nhưng sai schema hoặc thiếu dữ liệu nghiệp vụ.

## 23. Chọn XmlMapper hay ObjectMapper?

| Nhu cầu | Công cụ |
|---|---|
| Đọc/ghi JSON | ObjectMapper |
| Đọc/ghi XML | XmlMapper |
| Điều khiển parser/generator XML | XmlFactory và StAX |
| Ánh xạ attribute, element, wrapper, text | Annotation của jackson-dataformat-xml |
| Custom Databind logic dùng chung | Serializer/deserializer hoặc Module |
| Xử lý XML mixed content phức tạp | DOM, StAX trực tiếp hoặc custom XML processing |
| Xác thực theo XSD | XML Schema validation API |
| Giữ XML nguyên dạng hoặc xử lý node-level | DOM/StAX hoặc mô hình XML chuyên dụng |

Nếu ứng dụng chỉ cần JSON, không cần thêm XML module. Nếu phải trao đổi XML, XmlMapper giúp tái sử dụng nhiều cơ chế Databind quen thuộc nhưng vẫn cần mô tả XML shape cụ thể.

## 24. Quy trình tích hợp XML vào ứng dụng

Khi thêm XML support, hãy thực hiện theo trình tự:

1. Thêm jackson-dataformat-xml với phiên bản đồng bộ cùng Jackson Databind.
2. Xác định StAX provider và cấu hình bảo mật cho input không tin cậy.
3. Tạo XmlMapper riêng cho XML.
4. Định nghĩa root element bằng @JacksonXmlRootElement.
5. Đánh dấu attribute và element bằng @JacksonXmlProperty.
6. Khai báo wrapper và tên item cho collection.
7. Dùng @JacksonXmlText hoặc CDATA khi wire contract yêu cầu.
8. Khai báo namespace URI rõ ràng.
9. Đăng ký các module Databind bổ sung vào chính XmlMapper.
10. Kiểm thử serialize/deserialize với XML fixture thật.
11. Validate XSD và nghiệp vụ nếu contract yêu cầu.
12. Đặt giới hạn body, timeout và chính sách DTD/external entity.

## Kết luận

jackson-dataformat-xml bổ sung khả năng đọc và ghi XML vào hệ sinh thái Jackson. XmlMapper cung cấp API databinding quen thuộc của ObjectMapper, còn XmlFactory kết nối mapper với parser/generator XML dựa trên StAX. Các annotation như @JacksonXmlRootElement, @JacksonXmlProperty, @JacksonXmlElementWrapper và @JacksonXmlText mô tả root, attribute, element, collection và text content.

Hãy dùng XmlMapper riêng cho XML, khai báo wire structure tường minh và đăng ký các module Databind cần thiết vào đúng mapper. XML có namespace, mixed content, empty/nil và quy tắc schema riêng nên không thể giả định mọi cấu hình JSON đều chuyển nguyên vẹn sang XML. Với dữ liệu không tin cậy, cấu hình StAX để hạn chế DTD/external entities, giới hạn tài nguyên và kiểm thử cả XML well-formed lẫn contract/schema trước khi đưa vào nghiệp vụ.

