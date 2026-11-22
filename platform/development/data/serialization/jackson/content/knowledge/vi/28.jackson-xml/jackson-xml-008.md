# Kết hợp annotation Jackson và annotation riêng của module XML

## 1. Vì sao cần hai nhóm annotation?

Jackson Databind cung cấp các annotation chung để mô tả cách một thuộc tính Java được đọc và ghi, chẳng hạn tên property, quyền truy cập, giá trị mặc định hoặc quy tắc bỏ qua. Các annotation này không gắn với riêng JSON; chúng mô tả metadata của property mà Jackson có thể sử dụng ở nhiều định dạng.

Khi dùng XML, module jackson-dataformat-xml bổ sung các annotation để mô tả cấu trúc đặc trưng của XML:

- Root element.
- Element và attribute.
- Namespace.
- Wrapper của collection.
- Text content và CDATA.

Do đó, một DTO có thể kết hợp cả hai nhóm:

- Annotation Jackson chung điều khiển tên logic, inclusion, creator, alias hoặc ignore.
- Annotation XML điều khiển cách biểu diễn property thành element, attribute, wrapper hay text.

Mục tiêu thường gặp là dùng cùng một mô hình Java để trao đổi cả JSON và XML mà không phải tạo hai bộ DTO hoàn toàn riêng biệt. Tuy nhiên, JSON object và XML document có cấu trúc khác nhau; không phải mọi hình dạng đều có thể dùng chung một lớp mà không cần quyết định rõ.

## 2. XmlMapper hiểu annotation Jackson và annotation XML

Module XML cung cấp XmlMapper, một mapper dựa trên Jackson Databind nhưng có khả năng đọc và ghi XML:

~~~java
import com.fasterxml.jackson.dataformat.xml.XmlMapper;

XmlMapper xmlMapper = new XmlMapper();
~~~

Với JSON, có thể dùng ObjectMapper hoặc JsonMapper:

~~~java
import com.fasterxml.jackson.databind.json.JsonMapper;

ObjectMapper jsonMapper = JsonMapper.builder().build();
~~~

XmlMapper nhận diện phần lớn annotation Jackson thông dụng, đồng thời hiểu các annotation riêng của module XML. Ví dụ:

| Annotation | Nhóm | Công dụng |
|---|---|---|
| JsonProperty | Jackson chung | Đặt tên property và điều khiển khả năng đọc/ghi |
| JsonIgnore | Jackson chung | Bỏ property trong binding thông thường |
| JsonInclude | Jackson chung | Quy định property nào được serialize |
| JsonCreator | Jackson chung | Chọn constructor hoặc factory method để tạo object |
| JsonAlias | Jackson chung | Chấp nhận tên thay thế khi deserialize |
| JsonFormat | Jackson chung | Điều khiển định dạng một số kiểu giá trị |
| JsonSetter | Jackson chung | Điều khiển cách gán property và null policy |
| JacksonXmlRootElement | XML riêng | Đặt tên và namespace của root element |
| JacksonXmlProperty | XML riêng | Đặt tên, namespace và xác định XML attribute |
| JacksonXmlElementWrapper | XML riêng | Đặt wrapper cho collection hoặc tắt wrapper |
| JacksonXmlText | XML riêng | Ánh xạ property vào text content của element |
| JacksonXmlCData | XML riêng | Yêu cầu ghi nội dung text dưới dạng CDATA |
| JacksonXmlTransient | XML riêng | Bỏ property trong ánh xạ XML |

Annotation Jackson chung thường được XmlMapper áp dụng cùng với annotation XML. Annotation XML-specific được JsonMapper/ObjectMapper thông thường bỏ qua vì chúng không điều khiển cấu trúc JSON.

## 3. Dùng JsonProperty cùng JacksonXmlProperty

JsonProperty có thể đặt tên property theo hợp đồng JSON. JacksonXmlProperty cho phép đặt tên XML riêng, chọn namespace hoặc chuyển property thành attribute.

Ví dụ:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlProperty;

public class Customer {
    @JsonProperty("customerId")
    @JacksonXmlProperty(localName = "id", isAttribute = true)
    private String id;

    @JsonProperty("displayName")
    @JacksonXmlProperty(localName = "display-name")
    private String name;

    public Customer() {
    }

    public Customer(String id, String name) {
        this.id = id;
        this.name = name;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
~~~

Với JsonMapper, property có tên customerId và displayName:

~~~json
{
  "customerId": "C-100",
  "displayName": "Lan"
}
~~~

Với XmlMapper, property id là attribute và name là child element:

~~~xml
<Customer id="C-100">
  <display-name>Lan</display-name>
</Customer>
~~~

Tên root trong ví dụ vẫn là tên mặc định của lớp. Có thể đặt root element bằng JacksonXmlRootElement ở phần tiếp theo.

Ý tưởng quan trọng:

- JsonProperty mô tả tên property theo quy ước Jackson chung, đặc biệt hữu ích cho JSON.
- JacksonXmlProperty mô tả cách property đó xuất hiện trong XML.
- localName là tên XML cụ thể khi muốn XML có cách đặt tên khác với tên JSON.
- isAttribute = true biến property thành XML attribute thay vì element.

Nếu cả hai annotation cùng xuất hiện, hãy quy định rõ tên canonical cho từng định dạng. Tránh khai báo tên mâu thuẫn trên field, getter và setter của cùng một property vì metadata được Jackson tổng hợp từ các thành viên đó.

## 4. Đặt tên root element bằng JacksonXmlRootElement

XML document có một root element. JacksonXmlRootElement cho phép đặt tên và namespace cho root:

~~~java
import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlRootElement;

@JacksonXmlRootElement(
        localName = "customer",
        namespace = "urn:example:customer"
)
public class Customer {
    // properties
}
~~~

XmlMapper có thể ghi root theo tên customer và namespace được chỉ định. Prefix XML được dùng để biểu diễn namespace có thể do StAX writer lựa chọn; hợp đồng nên dựa trên namespace URI và local name, không nên phụ thuộc vào một prefix cụ thể nếu không có yêu cầu riêng.

JacksonXmlRootElement là annotation XML. JsonMapper không dùng annotation này để đổi tên root JSON. Nếu JSON cũng cần root wrapping, hãy xem xét JsonRootName cùng cấu hình WRAP_ROOT_VALUE/UNWRAP_ROOT_VALUE của Jackson.

## 5. Phân biệt XML element và attribute

XML có hai cách biểu diễn dữ liệu thường gặp:

~~~xml
<customer id="C-100">
  <name>Lan</name>
</customer>
~~~

Ở đây:

- id là attribute của customer.
- name là child element.

JacksonXmlProperty điều khiển cả hai:

~~~java
public class Customer {
    @JacksonXmlProperty(
            localName = "id",
            isAttribute = true
    )
    private String id;

    @JacksonXmlProperty(localName = "name")
    private String name;
}
~~~

Mặc định, property được biểu diễn dưới dạng element. Chỉ đặt isAttribute = true khi schema XML yêu cầu attribute.

Attribute phù hợp với metadata ngắn như ID, mã loại hoặc cờ đơn giản. Element thường phù hợp hơn với dữ liệu có cấu trúc, nội dung dài, collection hoặc giá trị có thể cần namespace riêng.

Một object phức tạp không thể được biểu diễn tùy ý thành một attribute XML có nhiều field con. Nếu property là object hoặc collection, hãy dùng element và wrapper theo schema.

## 6. Đặt tên wrapper và item của collection

Trong XML, một collection có thể được biểu diễn theo hai hình thức:

### Có wrapper

~~~xml
<order>
  <lineItems>
    <line>
      <sku>KB-01</sku>
      <quantity>2</quantity>
    </line>
    <line>
      <sku>MS-02</sku>
      <quantity>1</quantity>
    </line>
  </lineItems>
</order>
~~~

### Không có wrapper

~~~xml
<order>
  <line>
    <sku>KB-01</sku>
    <quantity>2</quantity>
  </line>
  <line>
    <sku>MS-02</sku>
    <quantity>1</quantity>
  </line>
</order>
~~~

JacksonXmlElementWrapper điều khiển wrapper; JacksonXmlProperty điều khiển tên của từng item:

~~~java
public class Order {
    @JsonProperty("items")
    @JacksonXmlElementWrapper(localName = "lineItems")
    @JacksonXmlProperty(localName = "line")
    private List<OrderLine> items;

    // getters/setters
}
~~~

Nếu schema yêu cầu các item lặp lại trực tiếp dưới root, không có container:

~~~java
public class Order {
    @JacksonXmlElementWrapper(useWrapping = false)
    @JacksonXmlProperty(localName = "line")
    private List<OrderLine> items;

    // getters/setters
}
~~~

Trong JSON, collection vẫn là một array dưới property items. Annotation wrapper chỉ thay đổi cách XmlMapper bố trí các element XML.

Không nên nhầm wrapper element với item element. Wrapper bao quanh toàn bộ collection; item element đại diện cho từng phần tử.

## 7. Kết hợp JsonProperty với collection XML

Một DTO có thể dùng tên property JSON và hai tên XML khác nhau cho wrapper/item:

~~~java
public class Order {
    @JsonProperty("orderId")
    @JacksonXmlProperty(localName = "id", isAttribute = true)
    private String id;

    @JsonProperty("items")
    @JacksonXmlElementWrapper(localName = "lineItems")
    @JacksonXmlProperty(localName = "line")
    private List<OrderLine> items;

    // getters/setters
}
~~~

JSON:

~~~json
{
  "orderId": "O-200",
  "items": [
    {"sku": "KB-01", "quantity": 2},
    {"sku": "MS-02", "quantity": 1}
  ]
}
~~~

XML:

~~~xml
<order id="O-200">
  <lineItems>
    <line>
      <sku>KB-01</sku>
      <quantity>2</quantity>
    </line>
    <line>
      <sku>MS-02</sku>
      <quantity>1</quantity>
    </line>
  </lineItems>
</order>
~~~

Ví dụ minh họa cách tổ chức annotation; trong lớp thực tế, Order nên có JacksonXmlRootElement(localName = "order") để bảo đảm root đúng schema XML.

## 8. Ánh xạ property thành text content

Một XML element có thể chứa text trực tiếp thay vì một child element:

~~~xml
<description>Wireless keyboard</description>
~~~

JacksonXmlText đánh dấu property được ghi vào nội dung text của element:

~~~java
public class Description {
    @JacksonXmlText
    private String value;

    public Description() {
    }

    public Description(String value) {
        this.value = value;
    }

    public String getValue() {
        return value;
    }

    public void setValue(String value) {
        this.value = value;
    }
}
~~~

Nếu dùng cùng DTO với JSON, có thể đặt JsonProperty cho property value:

~~~java
public class Description {
    @JsonProperty("value")
    @JacksonXmlText
    private String value;
}
~~~

JSON sẽ biểu diễn value như một property thông thường; XML biểu diễn nó thành text content của element. Không nên dùng JacksonXmlText cho nhiều property trong cùng một kiểu mà không có schema và kiểm thử cụ thể.

XML mixed content có thể xen kẽ text và child elements theo thứ tự. Mô hình bean thông thường không phải lúc nào cũng bảo toàn được thứ tự mixed content phức tạp. Nếu schema phụ thuộc thứ tự xen kẽ, hãy đánh giá khả năng của XML module hoặc dùng StAX trực tiếp để kiểm soát sự kiện XML.

## 9. Ghi CDATA bằng JacksonXmlCData

CDATA là một cách viết nội dung text trong XML:

~~~xml
<message><![CDATA[<hello>& welcome]]></message>
~~~

JacksonXmlCData yêu cầu XmlMapper ghi property text dưới dạng CDATA:

~~~java
public class Message {
    @JacksonXmlText
    @JacksonXmlCData
    private String content;

    public String getContent() {
        return content;
    }

    public void setContent(String content) {
        this.content = content;
    }
}
~~~

CDATA không tạo ra một kiểu dữ liệu khác trong XML data model. Khi parser đọc XML, nội dung CDATA và text đã escape thường trở thành cùng một giá trị chuỗi. Vì vậy, không nên mong đợi deserialize có thể xác định chuỗi ban đầu được viết bằng CDATA hay text thông thường.

CDATA cũng có quy tắc riêng đối với chuỗi chứa dấu kết thúc CDATA. Hãy kiểm thử nội dung có ký tự đặc biệt và không dựa vào CDATA như một cơ chế mã hóa hoặc bảo mật.

## 10. Namespace trên root, element và attribute

XML namespace phân biệt tên theo namespace URI và local name. Hai element có cùng local name nhưng namespace URI khác nhau là hai tên XML khác nhau.

Có thể khai báo namespace ở root:

~~~java
@JacksonXmlRootElement(
        localName = "customer",
        namespace = "urn:example:customer"
)
public class Customer {
    @JacksonXmlProperty(
            localName = "name",
            namespace = "urn:example:customer"
    )
    private String name;
}
~~~

JacksonXmlProperty có thuộc tính namespace để gắn property vào namespace URI. Cần kiểm tra schema XML đích, vì namespace mặc định áp dụng cho element nhưng không tự động áp dụng cho unprefixed attribute theo quy tắc namespace của XML.

Ví dụ khái niệm:

~~~xml
<customer xmlns="urn:example:customer">
  <name>Lan</name>
</customer>
~~~

Nếu attribute cần namespace, phải khai báo rõ và kiểm tra prefix/namespace trong XML đầu ra. Không nên so sánh XML bằng chuỗi prefix cố định nếu prefix không phải một phần bắt buộc của hợp đồng; nên kiểm tra namespace URI và local name bằng XML-aware parser.

## 11. Kết hợp JsonIgnore và JacksonXmlTransient

Hai annotation này có phạm vi khác nhau:

- JsonIgnore là annotation Jackson chung; property bị bỏ qua trong các mapper hiểu annotation này, bao gồm cả JSON và XML.
- JacksonXmlTransient là annotation XML-specific; nó dùng để bỏ property khỏi ánh xạ XML trong khi property vẫn có thể tham gia JSON mapping.

Ví dụ một giá trị nội bộ không xuất hiện trong cả hai định dạng:

~~~java
public class Customer {
    private String name;

    @JsonIgnore
    private String internalToken;
}
~~~

Ví dụ một property chỉ dùng trong JSON:

~~~java
public class Customer {
    private String name;

    @JacksonXmlTransient
    private String jsonOnlyMetadata;
}
~~~

Với lớp thứ hai, JsonMapper có thể serialize/deserialize jsonOnlyMetadata theo visibility và metadata Jackson chung; XmlMapper bỏ qua property đó theo annotation XML-specific.

Nếu mục tiêu là một property chỉ có trong XML, hãy kiểm tra xem JsonProperty.Access hoặc cơ chế visibility có thể diễn đạt chính sách đó rõ hơn hay không. Đừng giả định JacksonXmlTransient tự tạo một property XML-only trong mọi cấu hình.

## 12. Kết hợp JsonInclude và null/empty values

JsonInclude là annotation chung điều khiển property nào được đưa vào output:

~~~java
@JsonInclude(JsonInclude.Include.NON_NULL)
public class Customer {
    private String name;
    private String phone;
}
~~~

XmlMapper cũng có thể áp dụng inclusion rule này khi serialize. Nếu phone là null, property có thể bị bỏ khỏi XML theo chính sách NON_NULL.

Điều này khác với việc ghi một element có nội dung rỗng:

~~~xml
<phone/>
~~~

và khác với element có text:

~~~xml
<phone></phone>
~~~

XML không có một giá trị null duy nhất tương đương JSON null. Cách biểu diễn có thể phụ thuộc schema, annotation, null serializer và cấu hình module. Nếu hợp đồng yêu cầu xsi:nil, empty element hoặc bỏ element, hãy kiểm thử và cấu hình cụ thể thay vì suy ra từ hành vi JSON.

Ở chiều đọc, JsonSetter(nulls = ...) là annotation Jackson chung và có thể ảnh hưởng cách xử lý null khi XmlMapper bind property. Tuy nhiên, XML parser có thể cung cấp trạng thái khác nhau cho element thiếu, element rỗng và element có xsi:nil; cần xác định rõ schema và test từng trường hợp.

## 13. JsonCreator và constructor binding trong XML

Các annotation creator của Jackson có thể được dùng với XmlMapper:

~~~java
public class ProductCode {
    private final String value;

    @JsonCreator
    public ProductCode(
            @JsonProperty("value") String value
    ) {
        this.value = value;
    }

    @JsonProperty("value")
    public String getValue() {
        return value;
    }
}
~~~

JsonCreator và JsonProperty mô tả cách tạo object và gán tham số. XmlMapper có thể dùng metadata này khi bind XML vào cùng kiểu Java.

Tuy nhiên, XML có element và attribute, trong khi creator thường nhận tham số theo tên property. Nếu constructor cần bind một attribute hoặc một element có localName riêng, hãy kiểm thử đúng cấu hình XML và không chỉ dựa vào test JSON.

Với DTO immutable, record hoặc constructor nhiều tham số, cần xác nhận tên tham số, alias, namespace và null policy. Nếu XML schema có hình dạng khác JSON đáng kể, DTO riêng cho XML có thể đơn giản và an toàn hơn một lớp dùng quá nhiều annotation.

## 14. JsonAlias và tên XML legacy

JsonAlias là annotation Jackson chung để chấp nhận tên thay thế khi deserialize. Nó có thể hữu ích khi cần đọc payload JSON cũ hoặc tên property legacy.

Ví dụ:

~~~java
public class Customer {
    @JsonProperty("displayName")
    @JsonAlias("name")
    private String displayName;
}
~~~

Đối với XML, alias có thể tương tác với local name do XML annotation cung cấp và cách XML introspector tạo property. Không nên giả định alias JSON tự động giải quyết mọi biến thể tên XML hoặc namespace cũ.

Nếu cần hỗ trợ hai element XML khác nhau trong giai đoạn chuyển tiếp, hãy tạo test với XmlMapper cho từng tên thực tế. Với schema migration phức tạp, có thể dùng DTO XML legacy hoặc adapter chuyển đổi về model canonical.

Không nên để cả tên cũ và tên mới cùng ghi vào một property mà không có quy tắc xung đột. Nếu payload có cả hai, hãy từ chối hoặc xác định quy tắc ưu tiên rõ ràng.

## 15. Annotation XML và thứ tự/metadata property

Jackson tổng hợp metadata của một property từ field, getter, setter và creator parameter. Nếu các thành viên của cùng property có annotation khác nhau, kết quả có thể khó dự đoán.

Ví dụ dễ gây nhầm:

~~~java
public class Customer {
    @JsonProperty("displayName")
    private String name;

    @JacksonXmlProperty(localName = "full-name")
    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
~~~

Trong trường hợp này, metadata JSON và XML được đặt ở hai thành viên khác nhau của cùng property. Jackson có cơ chế hợp nhất annotation, nhưng nếu có xung đột tên hoặc access rule, việc hiểu kết quả chỉ từ một annotation riêng lẻ sẽ khó.

Thực hành tốt:

- Chọn một vị trí nhất quán để khai báo annotation, thường là field hoặc getter/setter theo convention của project.
- Nếu dùng field annotation, kiểm tra visibility và access strategy.
- Nếu dùng creator, đặt JsonProperty trên tham số và đồng bộ tên với property.
- Đặt XML localName/namespace ở đúng property cần điều khiển XML.
- Viết test riêng cho JSON và XML để xác nhận metadata cuối cùng.

## 16. XmlMapper được cấu hình annotation introspection như thế nào?

XmlMapper được module XML cấu hình để hiểu annotation Jackson thông thường và annotation XML-specific. Trong ứng dụng bình thường, không cần tự thay annotation introspector chỉ để dùng JacksonXmlProperty hoặc JacksonXmlRootElement.

Nếu ứng dụng thay AnnotationIntrospector bằng một implementation riêng, cần cẩn thận: thay toàn bộ introspector có thể làm mất khả năng nhận diện một số annotation đã được mapper sử dụng. Với cấu hình nâng cao, hãy kết hợp các introspector phù hợp bằng AnnotationIntrospectorPair và xác định thứ tự ưu tiên primary/secondary theo mục tiêu.

Không nên thay introspector chỉ để sửa một property. Trước tiên hãy xem annotation có đang được đặt đúng thành viên không, có xung đột giữa field/getter không và XmlMapper có được tạo từ đúng module/phiên bản hay không.

## 17. Ví dụ DTO dùng chung cho JSON và XML

Ví dụ tổng hợp:

~~~java
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlElementWrapper;
import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlProperty;
import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlRootElement;
import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlTransient;

import java.util.List;

@JsonInclude(JsonInclude.Include.NON_NULL)
@JacksonXmlRootElement(
        localName = "order",
        namespace = "urn:example:orders"
)
public class Order {
    @JsonProperty("orderId")
    @JacksonXmlProperty(localName = "id", isAttribute = true)
    private String id;

    @JsonProperty("customerName")
    @JacksonXmlProperty(localName = "customer-name")
    private String customerName;

    @JsonProperty("items")
    @JacksonXmlElementWrapper(localName = "lineItems")
    @JacksonXmlProperty(localName = "line")
    private List<OrderLine> items;

    @JsonProperty("internalNote")
    @JacksonXmlTransient
    private String internalNote;

    // getters/setters
}
~~~

Lớp OrderLine có thể dùng annotation Jackson chung:

~~~java
public class OrderLine {
    @JsonProperty("sku")
    private String sku;

    @JsonProperty("quantity")
    private Integer quantity;

    // getters/setters
}
~~~

JSON có dạng:

~~~json
{
  "orderId": "O-200",
  "customerName": "Lan",
  "items": [
    {"sku": "KB-01", "quantity": 2}
  ],
  "internalNote": "warehouse-only"
}
~~~

XML có hình dạng:

~~~xml
<order xmlns="urn:example:orders" id="O-200">
  <customer-name>Lan</customer-name>
  <lineItems>
    <line>
      <sku>KB-01</sku>
      <quantity>2</quantity>
    </line>
  </lineItems>
</order>
~~~

internalNote có thể xuất hiện trong JSON theo JsonProperty nhưng bị bỏ qua trong XML do JacksonXmlTransient. JsonInclude(NON_NULL) được áp dụng cho cả hai mapper theo chính sách chung.

## 18. Tạo mapper và căn chỉnh dependency

Để dùng XML module, cần dependency jackson-dataformat-xml cùng dòng phiên bản với Jackson Core và Databind:

~~~xml
<dependency>
    <groupId>com.fasterxml.jackson.dataformat</groupId>
    <artifactId>jackson-dataformat-xml</artifactId>
</dependency>
~~~

Nên dùng Jackson BOM hoặc dependency management của framework để căn chỉnh phiên bản. Trộn các phiên bản XML module, Databind và Core có thể gây lỗi liên kết binary hoặc hành vi không tương thích.

Tạo mapper:

~~~java
ObjectMapper jsonMapper = JsonMapper.builder()
        .build();

XmlMapper xmlMapper = XmlMapper.builder()
        .build();
~~~

Nếu cần module bổ sung như JavaTimeModule, đăng ký nhất quán cho cả hai mapper:

~~~java
ObjectMapper jsonMapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .build();

XmlMapper xmlMapper = XmlMapper.builder()
        .addModule(new JavaTimeModule())
        .build();
~~~

Khả năng serialize ngày giờ thành chuỗi hoặc dạng khác còn phụ thuộc feature và serializer. Hãy kiểm thử riêng định dạng JSON và XML thay vì giả định hai định dạng có cùng cú pháp.

## 19. Kiểm thử cùng DTO qua hai mapper

Một DTO dùng chung cần test cả hai chiều và cả hai định dạng:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.dataformat.xml.XmlMapper;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class CustomerFormatTest {
    private final ObjectMapper jsonMapper = JsonMapper.builder().build();
    private final XmlMapper xmlMapper = XmlMapper.builder().build();

    @Test
    void jsonUsesJacksonPropertyNames() throws Exception {
        Customer customer = new Customer("C-100", "Lan");

        String json = jsonMapper.writeValueAsString(customer);
        JsonNode tree = jsonMapper.readTree(json);

        assertEquals("C-100", tree.path("customerId").asText());
        assertEquals("Lan", tree.path("displayName").asText());
    }

    @Test
    void xmlUsesXmlSpecificNamesAndAttribute() throws Exception {
        Customer customer = new Customer("C-100", "Lan");

        String xml = xmlMapper.writeValueAsString(customer);

        assertTrue(xml.contains("id=\"C-100\""));
        assertTrue(xml.contains("<display-name>Lan</display-name>"));
    }

    @Test
    void xmlCanReadItsOwnRepresentation() throws Exception {
        String xml = """
                <Customer id="C-100">
                  <display-name>Lan</display-name>
                </Customer>
                """;

        Customer customer = xmlMapper.readValue(xml, Customer.class);

        assertEquals("C-100", customer.getId());
        assertEquals("Lan", customer.getName());
    }
}
~~~

Các test này là khung minh họa; nếu lớp Customer dùng JacksonXmlRootElement hoặc namespace, fixture XML phải phản ánh đúng root và namespace đó. Với XML, nên dùng XML-aware parser để kiểm tra namespace URI, local name, attribute và cấu trúc thay vì chỉ so sánh toàn bộ chuỗi.

Các trường hợp bổ sung nên kiểm thử:

- Root element và namespace.
- Attribute so với child element.
- Collection có wrapper và không wrapper.
- Null, empty string và empty collection.
- Text content và CDATA.
- Property bị ignore trong một định dạng nhưng vẫn hiện diện ở định dạng còn lại.
- Creator/record binding.
- Alias hoặc tên XML legacy.
- Kiểu ngày giờ và enum.

## 20. Khi nào nên dùng DTO riêng cho XML?

Dùng chung DTO tiện lợi khi JSON và XML biểu diễn gần như cùng một domain structure. Tuy nhiên, hai định dạng có mô hình khác nhau:

- XML có attribute, namespace, mixed content và wrapper.
- JSON có object member và array nhưng không có attribute hoặc namespace.
- XML schema có thể yêu cầu thứ tự element hoặc wrapper cụ thể.
- Một số hệ thống XML legacy có tên element không giống tên field Java hoặc JSON.

Nếu một DTO chứa quá nhiều annotation XML và JSON xung đột, cân nhắc tách:

~~~text
JSON payload ---> JSON DTO ---\
                               \
                                ---> Domain model
                               /
XML payload ----> XML DTO ----/
~~~

Adapter chuyển đổi DTO định dạng riêng về domain model chung. Domain model không cần biết chi tiết XML wrapper, attribute hoặc namespace.

DTO riêng thường phù hợp khi:

- XML schema được quản lý độc lập và có nhiều quy tắc đặc biệt.
- JSON API có naming convention khác hoàn toàn.
- XML cần mixed content hoặc thứ tự element quan trọng.
- Cùng một field có semantics khác nhau giữa hai giao thức.
- Một định dạng cần compatibility alias hoặc legacy mapping riêng.

Đừng ép một lớp duy nhất đại diện cho hai hợp đồng nếu điều đó làm annotation trở nên khó hiểu hoặc khiến thay đổi một định dạng vô tình làm hỏng định dạng còn lại.

## 21. Những lỗi thường gặp

### Nghĩ rằng JsonProperty đủ để mô tả XML schema

JsonProperty đặt tên property chung nhưng không mô tả đầy đủ attribute, namespace, root hoặc collection wrapper. Dùng annotation XML cho các đặc điểm đó.

### Dùng JacksonXmlProperty nhưng mong JSON đổi tên

JsonMapper không dùng annotation XML-specific. Nếu cần tên JSON khác, dùng JsonProperty.

### Nhầm wrapper với item element

JacksonXmlElementWrapper đặt tên container; JacksonXmlProperty đặt tên từng item. Cần khai báo đúng cả hai khi schema yêu cầu.

### Dùng JsonIgnore khi chỉ muốn bỏ property khỏi XML

JsonIgnore ảnh hưởng cả JSON và XML. Dùng JacksonXmlTransient nếu chỉ cần bỏ property trong XML.

### Cho rằng CDATA là kiểu dữ liệu khác

CDATA chỉ là cách biểu diễn text trong XML. Khi parse, nội dung thường trở thành cùng một chuỗi như text đã escape.

### So sánh XML bằng prefix hoặc chuỗi thô

Prefix namespace có thể khác nhưng namespace URI và local name vẫn giống nhau. Dùng XML-aware parser để kiểm tra cấu trúc.

### Gắn annotation mâu thuẫn trên field và getter

Jackson hợp nhất metadata của property. Annotation không nhất quán có thể tạo kết quả khó dự đoán; chọn một convention và test cả hai mapper.

### Chỉ test JSON vì DTO dùng chung

XML module có quy tắc root, wrapper, attribute và namespace riêng. Cần test XmlMapper độc lập.

## 22. Quy trình thiết kế annotation cho DTO đa định dạng

Khi một DTO cần hỗ trợ cả JSON và XML:

1. Xác định tên property canonical trong Java/domain.
2. Xác định tên JSON cho từng property bằng annotation Jackson chung khi cần.
3. Xác định root, element, attribute, namespace và wrapper theo XML schema.
4. Dùng JacksonXmlRootElement, JacksonXmlProperty và JacksonXmlElementWrapper tại đúng property.
5. Chọn JsonIgnore hay JacksonXmlTransient theo phạm vi định dạng cần bỏ.
6. Xác định null, empty và collection semantics riêng cho XML.
7. Kiểm tra annotation trên field/getter/creator không xung đột.
8. Tạo JsonMapper và XmlMapper đã cấu hình xong.
9. Viết fixture JSON và XML độc lập, test cả serialize lẫn deserialize.
10. Nếu hai hợp đồng quá khác nhau, tách DTO và chuyển đổi qua domain model.

## 23. Kết luận

Có thể kết hợp annotation Jackson chung với annotation riêng của module XML để một DTO hỗ trợ cả JSON và XML. JsonProperty, JsonIgnore, JsonInclude, JsonCreator và các annotation Databind khác mô tả metadata chung của property; JacksonXmlRootElement, JacksonXmlProperty, JacksonXmlElementWrapper, JacksonXmlText, JacksonXmlCData và JacksonXmlTransient mô tả hình dạng XML. Dùng JsonProperty cho tên JSON và JacksonXmlProperty cho element/attribute XML khi hai hợp đồng cần tên khác nhau. Wrapper và item phải được khai báo đúng, namespace cần kiểm tra theo URI, còn CDATA chỉ là cách viết text. XmlMapper hiểu cả hai nhóm annotation; JsonMapper bỏ qua annotation XML-specific. Hãy giữ metadata nhất quán trên từng property, kiểm thử riêng hai định dạng và tách DTO nếu cấu trúc XML/JSON khác nhau quá nhiều.
