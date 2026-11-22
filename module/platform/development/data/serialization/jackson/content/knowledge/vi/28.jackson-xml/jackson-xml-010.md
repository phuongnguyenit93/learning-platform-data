# Kiểm thử tương thích thay vì giả định đổi mapper giữ nguyên ngữ nghĩa

Trong một ứng dụng dùng Jackson, đổi từ `ObjectMapper` sang `XmlMapper`, thêm module, thay naming strategy hoặc nâng phiên bản thư viện có thể làm thay đổi dữ liệu được đọc và ghi. Hai mapper có thể cùng nhận một class Java nhưng không nhất thiết tạo ra cùng cấu trúc wire format. Một lần deserialize thành công cũng không chứng minh dữ liệu giữ nguyên ý nghĩa.

Với XML, khác biệt càng dễ bị bỏ sót vì cùng một thông tin có thể được biểu diễn bằng element, attribute, namespace, wrapper, text node hoặc `xsi:nil`. JSON không có những khái niệm tương đương hoàn toàn. Jackson XML cố gắng ánh xạ XML vào mô hình Java quen thuộc, nhưng không biến XML và JSON thành hai định dạng có ngữ nghĩa giống hệt nhau.

Cách đáng tin cậy là xác định hợp đồng dữ liệu trước, giữ các payload đại diện làm fixture và chạy kiểm thử tương thích khi thay mapper hoặc cấu hình. Bài học này tập trung vào cách kiểm tra ngữ nghĩa thực tế khi chuyển đổi giữa mapper JSON/XML hoặc thay đổi cấu hình Jackson, thay vì chỉ giả định cùng DTO sẽ giữ nguyên hành vi.

## 1. Mapper là cơ chế thực thi, không phải hợp đồng dữ liệu

`ObjectMapper` của Jackson Databind thường dùng JSON factory để đọc/ghi JSON. `XmlMapper` thuộc module `jackson-dataformat-xml`, kế thừa API Databind nhưng dùng XML factory/parser/generator và các quy tắc ánh xạ XML.

Ví dụ:

```java
ObjectMapper jsonMapper = new ObjectMapper();
XmlMapper xmlMapper = new XmlMapper();
```

Cả hai có thể deserialize vào cùng một kiểu Java:

```java
Customer customer = jsonMapper.readValue(json, Customer.class);

Customer customerFromXml =
    xmlMapper.readValue(xml, Customer.class);
```

Nhưng việc cùng trả về `Customer` không chứng minh hai payload có cùng hợp đồng. JSON object có property name và value; XML có element, attribute, namespace, text node và thứ tự node. Mapper quyết định cách chuyển những cấu trúc đó thành property Java.

Một số thay đổi có thể làm đổi ngữ nghĩa:

- JSON property được ánh xạ thành XML element thay vì attribute.
- Danh sách có wrapper element hoặc lặp trực tiếp các child element.
- Namespace URI thay đổi dù prefix nhìn có vẻ giống nhau.
- Element rỗng được đọc thành chuỗi rỗng hoặc `null` theo cấu hình.
- Property bị thiếu khác với `xsi:nil`.
- Enum hoặc ngày giờ được ghi thành text theo format khác.
- Unknown element bị bỏ qua hoặc gây lỗi.
- Module mới thay đổi serializer/deserializer được chọn.

Vì vậy, không nên xem việc thay class mapper là một thao tác thuần kỹ thuật không ảnh hưởng dữ liệu. Cần kiểm thử input và output theo hợp đồng của từng định dạng.

## 2. Phân biệt kiểm thử tương thích với kiểm thử round-trip

Round-trip thường có dạng:

```java
T value = mapper.readValue(input, T.class);
String output = mapper.writeValueAsString(value);
T restored = mapper.readValue(output, T.class);
```

Kiểm thử này hữu ích, nhưng có một giới hạn: serializer và deserializer có thể cùng mắc một lỗi. Nếu cả hai cùng đổi `customer_id` thành một tên khác, round-trip nội bộ vẫn có thể thành công trong khi client bên ngoài không còn đọc được dữ liệu.

Kiểm thử tương thích cần so sánh với hợp đồng độc lập:

1. Đọc fixture đã được công bố hoặc lưu từ hệ thống thực tế.
2. Kiểm tra object Java có đúng ý nghĩa nghiệp vụ không.
3. Ghi object ra định dạng wire.
4. So sánh output với schema hoặc fixture hợp đồng.
5. Kiểm tra consumer cũ có tiếp tục đọc được payload mới không.
6. Kiểm tra mapper mới có đọc được payload cũ không.

| Loại test | Câu hỏi trả lời |
| --- | --- |
| Unit test mapper | Một class được serialize/deserialize thế nào? |
| Round-trip test | Mapper có đọc lại được output của chính nó không? |
| Contract test | JSON/XML có đúng tên, kiểu, namespace và cấu trúc đã công bố không? |
| Compatibility test | Payload của phiên bản cũ và mới có được hai phía xử lý đúng không? |
| Schema validation | XML có tuân thủ XSD hoặc JSON có tuân thủ schema đã định nghĩa không? |

Một bộ kiểm thử tốt thường kết hợp các loại test này. Không nên dùng round-trip thay cho contract test.

## 3. Cùng DTO không có nghĩa cùng wire format

Giả sử model Java:

```java
public class Customer {
    private String id;
    private String displayName;
    private List<String> tags;

    public Customer() {
    }

    public Customer(String id, String displayName, List<String> tags) {
        this.id = id;
        this.displayName = displayName;
        this.tags = tags;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public List<String> getTags() {
        return tags;
    }

    public void setTags(List<String> tags) {
        this.tags = tags;
    }
}
```

JSON có thể là:

```json
{
  "id": "cus-1042",
  "displayName": "Nguyen An",
  "tags": ["premium", "newsletter"]
}
```

XML có thể là:

```xml
<Customer>
  <id>cus-1042</id>
  <displayName>Nguyen An</displayName>
  <tags>
    <tags>premium</tags>
    <tags>newsletter</tags>
  </tags>
</Customer>
```

Cả hai đều có thể bind vào `Customer`, nhưng cấu trúc khác nhau. Nếu hợp đồng XML yêu cầu:

```xml
<customer id="cus-1042">
  <display-name>Nguyen An</display-name>
  <tag>premium</tag>
  <tag>newsletter</tag>
</customer>
```

thì cần annotation XML cụ thể hoặc một DTO wire riêng. Không thể suy ra cấu trúc XML mong muốn chỉ từ tên property Java.

## 4. Khai báo cấu trúc XML công khai bằng annotation riêng

Jackson XML cung cấp các annotation trong package `com.fasterxml.jackson.dataformat.xml.annotation`:

- `@JacksonXmlRootElement`: đặt tên và namespace cho root element.
- `@JacksonXmlProperty`: đặt tên, namespace hoặc xác định property là attribute.
- `@JacksonXmlElementWrapper`: kiểm soát wrapper của collection.
- `@JacksonXmlText`: ánh xạ property thành text content của element.

Ví dụ DTO XML:

```java
import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlElementWrapper;
import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlProperty;
import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlRootElement;

@JacksonXmlRootElement(localName = "customer")
public class CustomerXml {

    @JacksonXmlProperty(isAttribute = true, localName = "id")
    private String id;

    @JacksonXmlProperty(localName = "display-name")
    private String displayName;

    @JacksonXmlElementWrapper(localName = "tags")
    @JacksonXmlProperty(localName = "tag")
    private List<String> tags;

    public CustomerXml() {
    }

    // Getters and setters
}
```

Kết quả XML có hình dạng:

```xml
<customer id="cus-1042">
  <display-name>Nguyen An</display-name>
  <tags>
    <tag>premium</tag>
    <tag>newsletter</tag>
  </tags>
</customer>
```

Đây là một wire contract được khai báo có chủ đích. Nó không phụ thuộc vào tên property Java `displayName` hoặc cách tổ chức domain model.

Nếu cùng dữ liệu cần cả JSON và XML, có thể dùng DTO riêng cho từng định dạng hoặc một model dùng annotation chung kết hợp annotation XML. DTO riêng thường dễ kiểm soát hơn khi hai định dạng có cấu trúc khác biệt đáng kể.

## 5. Element và attribute là hai cấu trúc khác nhau

JSON không có khái niệm attribute. Trong XML, hai dạng sau không tương đương về cấu trúc:

```xml
<customer id="cus-1042">
  <name>Nguyen An</name>
</customer>
```

```xml
<customer>
  <id>cus-1042</id>
  <name>Nguyen An</name>
</customer>
```

Cả hai có thể biểu đạt cùng thông tin nghiệp vụ, nhưng consumer XPath, XSD hoặc ứng dụng legacy có thể yêu cầu chính xác một dạng.

Với Jackson XML:

```java
@JacksonXmlProperty(isAttribute = true, localName = "id")
private String id;
```

ánh xạ `id` thành attribute.

Còn:

```java
@JacksonXmlProperty(localName = "id")
private String id;
```

ánh xạ thành child element theo quy tắc XML của mapper.

Khi đổi annotation hoặc mapper, hãy kiểm tra vị trí dữ liệu. Một test chỉ xác nhận `customer.getId()` có giá trị đúng có thể không phát hiện attribute đã biến thành element.

## 6. Wrapper của collection có thể làm đổi hợp đồng

Một danh sách có thể được biểu diễn theo hai cách:

Có wrapper:

```xml
<customer>
  <tags>
    <tag>premium</tag>
    <tag>newsletter</tag>
  </tags>
</customer>
```

Không có wrapper:

```xml
<customer>
  <tag>premium</tag>
  <tag>newsletter</tag>
</customer>
```

Jackson XML có thể dùng `@JacksonXmlElementWrapper` để mô tả wrapper và `useWrapping = false` để yêu cầu lặp trực tiếp element:

```java
@JacksonXmlElementWrapper(useWrapping = false)
@JacksonXmlProperty(localName = "tag")
private List<String> tags;
```

Khi dùng wrapper tường minh:

```java
@JacksonXmlElementWrapper(localName = "tags")
@JacksonXmlProperty(localName = "tag")
private List<String> tags;
```

Ngoài annotation, `JacksonXmlModule` có cấu hình mặc định về wrapper. Nếu đổi module hoặc `defaultUseWrapper`, output của collection không có annotation riêng có thể thay đổi.

Hãy kiểm thử riêng ba trường hợp:

- Collection có nhiều phần tử.
- Collection rỗng.
- Collection là `null`.

Một danh sách rỗng có thể được ghi thành wrapper rỗng, không có element nào hoặc biểu diễn khác tùy cấu hình. Đừng giả định các dạng đó tương đương với consumer.

## 7. Namespace phải được kiểm tra bằng URI, không chỉ prefix

XML namespace được xác định bằng URI. Prefix chỉ là bí danh trong tài liệu XML.

Hai tài liệu sau có thể có cùng namespace URI và cùng ngữ nghĩa:

```xml
<customer xmlns="urn:example:customer">
  <name>Nguyen An</name>
</customer>
```

```xml
<c:customer xmlns:c="urn:example:customer">
  <c:name>Nguyen An</c:name>
</c:customer>
```

Prefix `c` và default namespace khác nhau, nhưng namespace URI là `urn:example:customer`.

Ngược lại, cùng prefix nhưng URI khác nhau là hai namespace khác nhau:

```xml
<c:customer xmlns:c="urn:old:customer"/>
```

```xml
<c:customer xmlns:c="urn:new:customer"/>
```

Khi kiểm thử tương thích:

- So sánh namespace URI và local name.
- Không chỉ so sánh chuỗi prefix.
- Kiểm tra namespace của root và các child element.
- Kiểm tra attribute namespace riêng; default namespace của element không tự áp dụng cho attribute không có prefix.
- Kiểm tra schema/XPath consumer sử dụng namespace nào.

Annotation XML có thể khai báo namespace:

```java
@JacksonXmlRootElement(
    localName = "customer",
    namespace = "urn:example:customer"
)
public class CustomerXml {
    @JacksonXmlProperty(
        localName = "display-name",
        namespace = "urn:example:customer"
    )
    private String displayName;
}
```

Prefix được generator chọn không nhất thiết là một phần của hợp đồng, trừ khi hệ thống bên ngoài có yêu cầu không chuẩn phụ thuộc prefix. URI mới là định danh namespace cần giữ ổn định.

## 8. Empty element, null và phần tử bị thiếu

XML có nhiều cách biểu diễn trạng thái không có dữ liệu:

```xml
<customer/>
```

```xml
<customer>
  <nickname/>
</customer>
```

```xml
<customer>
  <nickname></nickname>
</customer>
```

```xml
<customer xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <nickname xsi:nil="true"/>
</customer>
```

```xml
<customer></customer>
```

Các trường hợp này không nhất thiết được ánh xạ thành cùng một giá trị Java:

- Child element bị thiếu có thể để property ở trạng thái chưa được gán.
- Empty element có thể được đọc thành chuỗi rỗng hoặc null theo parser feature và kiểu đích.
- `xsi:nil="true"` là một tín hiệu null theo XML Schema Instance.
- Element có text whitespace có thể khác element rỗng sau xử lý nội dung.

Jackson XML có các feature của `FromXmlParser`, ví dụ `EMPTY_ELEMENT_AS_NULL` và `PROCESS_XSI_NIL`. Hành vi cụ thể cần được kiểm tra trên phiên bản module đang sử dụng.

Ví dụ cấu hình parser feature:

```java
XmlMapper mapper = new XmlMapper();

mapper.configure(
    FromXmlParser.Feature.EMPTY_ELEMENT_AS_NULL,
    true
);

mapper.configure(
    FromXmlParser.Feature.PROCESS_XSI_NIL,
    true
);
```

Đây là quyết định hợp đồng. Nếu consumer dùng empty string để biểu thị giá trị rỗng và `xsi:nil` để biểu thị null, cần kiểm thử riêng cả hai dạng. Không gộp chúng thành một test “nickname không có giá trị”.

## 9. Kiểu dữ liệu và coercion cần được kiểm tra

XML element content về cơ bản là text. Jackson chuyển text thành kiểu Java đích theo deserializer/coercion policy.

Ví dụ:

```xml
<order>
  <quantity>12</quantity>
  <active>true</active>
  <price>19.95</price>
</order>
```

Model Java có thể dùng:

```java
public class OrderXml {
    private int quantity;
    private boolean active;
    private BigDecimal price;

    // Getters and setters
}
```

Nhưng cần kiểm tra các trường hợp biên:

- `quantity` thiếu.
- `quantity` rỗng.
- `quantity` có text không phải số.
- `active` dùng chữ hoa/thường khác nhau.
- `price` có dấu phẩy thập phân thay vì dấu chấm.
- `price` có scale lớn hơn dự kiến.
- Numeric text có khoảng trắng đầu/cuối.

Một mapper có thể chấp nhận một số dạng coercion trong khi mapper/cấu hình khác từ chối. Đừng dựa vào coercion ngầm làm hợp đồng công khai. Quy định format và kiểm thử input hợp lệ lẫn không hợp lệ.

## 10. Ngày giờ và enum cũng cần fixture độc lập

Ngày giờ XML thường được biểu diễn bằng text:

```xml
<created-at>2026-04-18T09:30:00Z</created-at>
```

Khi dùng `java.time`, đăng ký `JavaTimeModule` và cấu hình định dạng rõ ràng nếu hợp đồng yêu cầu:

```java
XmlMapper mapper = new XmlMapper();
mapper.registerModule(new JavaTimeModule());
mapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
```

Kiểm tra:

- Có timezone/offset hay không.
- Độ chính xác phần giây.
- UTC `Z` hay offset cụ thể.
- Giá trị ngày không có giờ.
- Hành vi khi timezone thiếu.

Enum cũng cần code wire ổn định. Không nên giả định tên constant Java luôn là mã XML được consumer mong đợi. Có thể dùng DTO string, `@JsonValue`/`@JsonCreator` hoặc custom serializer/deserializer, nhưng cần test cả hai chiều và giá trị không biết.

## 11. XML declaration, encoding và formatting

Một XML document có thể bắt đầu bằng declaration:

```xml
<?xml version="1.0" encoding="UTF-8"?>
```

Jackson XML có feature để ghi XML declaration, ví dụ `ToXmlGenerator.Feature.WRITE_XML_DECLARATION`:

```java
XmlMapper mapper = new XmlMapper();

mapper.configure(
    ToXmlGenerator.Feature.WRITE_XML_DECLARATION,
    true
);
```

Các khác biệt sau thường không đổi ngữ nghĩa XML:

- Xuống dòng và indentation.
- Khoảng trắng giữa các element.
- Dùng single quote hay double quote cho attribute.
- Thứ tự attribute.
- Prefix namespace khác nhau nhưng cùng URI.

Tuy nhiên, consumer yếu hoặc hệ thống legacy đôi khi so sánh chuỗi thô thay vì parse XML. Khi đó formatting có thể trở thành yêu cầu tương thích thực tế. Hãy xác định consumer xử lý XML theo parser hay string matching trước khi quyết định test.

Không nên dùng exact string comparison cho mọi XML output nếu formatting không thuộc hợp đồng. Ngược lại, nếu hệ thống yêu cầu declaration hoặc encoding cụ thể, hãy kiểm tra riêng yêu cầu đó.

## 12. Thứ tự element và mixed content

XML có thứ tự các child node. Với một số schema, thứ tự element là một phần của hợp đồng:

```xml
<person>
  <first-name>An</first-name>
  <last-name>Nguyen</last-name>
</person>
```

Một XSD có thể yêu cầu `first-name` trước `last-name`. Nếu mapper ghi ngược thứ tự, tài liệu có thể không hợp lệ dù cả hai field đều tồn tại.

Có thể điều khiển thứ tự property bằng `@JsonPropertyOrder`:

```java
@JsonPropertyOrder({"firstName", "lastName"})
public class PersonXml {
    private String firstName;
    private String lastName;

    // Getters and setters
}
```

Tuy nhiên, hãy kiểm tra output thực tế và validate bằng XSD nếu thứ tự có ý nghĩa.

Mixed content là trường hợp element chứa cả text và child element xen kẽ:

```xml
<p>
  Read <em>this</em> carefully.
</p>
```

Đây không phải cấu trúc bean thông thường. Jackson XML có giới hạn với mixed content và không nên giả định nó sẽ bảo toàn chính xác vị trí xen kẽ của text/element. Với tài liệu có mixed content phức tạp, cân nhắc StAX, DOM hoặc một mô hình XML chuyên biệt, rồi viết test fixture cụ thể.

## 13. Root element và tên root cũng là một phần hợp đồng

JSON object không có root element name theo cách XML có. XML bắt buộc có một document element duy nhất.

Jackson XML có thể dùng tên class hoặc cấu hình root name mặc định nếu không khai báo rõ. Điều đó có thể đổi khi class được rename hoặc mapper config thay đổi.

Dùng:

```java
@JacksonXmlRootElement(localName = "customer")
public class CustomerXml {
    // ...
}
```

Nếu hợp đồng yêu cầu root `customer`, hãy test root local name và namespace. Không chỉ kiểm tra các property con sau khi deserialize, vì mapper có thể chấp nhận nhiều root name khác nhau mà không làm test object-level thất bại.

## 14. Unknown element và strictness

JSON mapper thường có `FAIL_ON_UNKNOWN_PROPERTIES`. Jackson XML cũng sử dụng Databind behavior cho property không được nhận diện, nhưng cấu trúc XML có các node và namespace cần xem xét.

Có thể cấu hình:

```java
XmlMapper mapper = new XmlMapper();

mapper.enable(
    DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES
);
```

Hoặc cho phép bỏ qua unknown property trên DTO khi hợp đồng cần khả năng tương thích tiến:

```java
@JsonIgnoreProperties(ignoreUnknown = true)
public class CustomerXml {
    // Known contract properties
}
```

Chọn chính sách theo consumer:

- Strict input hữu ích để phát hiện typo hoặc XML không đúng schema.
- Lenient reader có thể giúp client cũ bỏ qua element mới.
- Hệ thống forward XML có thể cần giữ unknown content thay vì bỏ đi.

Nếu cần bảo toàn extension element, chỉ bật ignore unknown là chưa đủ; cần thiết kế extension point hoặc dùng DOM/StAX để giữ dữ liệu không biết. Hãy kiểm thử việc đọc rồi ghi lại xem unknown element có bị mất không.

## 15. Polymorphism và discriminator trong XML

Nếu một property có nhiều subtype, JSON thường dùng field discriminator. XML có thể dùng attribute hoặc element:

```xml
<notification type="email">
  <recipient>an@example.com</recipient>
  <subject>Welcome</subject>
</notification>
```

hoặc:

```xml
<notification>
  <type>email</type>
  <recipient>an@example.com</recipient>
  <subject>Welcome</subject>
</notification>
```

Đây là hai wire shape khác nhau. `@JsonTypeInfo` và subtype mapping cần được kiểm thử trên `XmlMapper` thực tế; không giả định cách biểu diễn discriminator trong JSON sẽ tự chuyển thành XML attribute/element như mong muốn.

Chỉ cho phép các subtype được liệt kê rõ. Không dùng class name hoặc package name từ input XML như một cơ chế khởi tạo class tùy ý.

Với contract XML legacy, có thể cần DTO riêng hoặc custom type resolver để giữ đúng vị trí discriminator.

## 16. Cấu hình mapper có thể làm đổi semantics

Khi so sánh hai mapper hoặc hai cấu hình, cần ghi nhận các khác biệt liên quan:

| Thành phần | Ảnh hưởng có thể có |
| --- | --- |
| `JsonFactory` / `XmlFactory` | Parser/generator và quy tắc xử lý định dạng |
| `JacksonXmlModule` | Wrapper mặc định và module XML |
| `JavaTimeModule` | Định dạng ngày giờ |
| Naming strategy | Tên property |
| `SerializationFeature` | Inclusion, date output, ordering |
| `DeserializationFeature` | Unknown property, coercion liên quan |
| `FromXmlParser.Feature` | Empty element, `xsi:nil` và hành vi XML |
| `ToXmlGenerator.Feature` | XML declaration và cách ghi XML |
| Mix-in/annotation | Tên, visibility và mapping |
| Custom serializer/deserializer | Biến đổi giá trị và cấu trúc |

Không chỉ ghi nhận version của `jackson-databind`. `jackson-dataformat-xml`, `jackson-core`, `jackson-annotations` và module datatype cũng cần tương thích. Dùng Jackson BOM hoặc dependency management phù hợp để tránh các artifact lệch release train.

## 17. Lưu fixture đại diện cho hợp đồng

Fixture là payload mẫu được lưu cùng test. Fixture nên đến từ hợp đồng đã công bố, hệ thống producer thực tế hoặc ví dụ được consumer xác nhận.

Ví dụ cấu trúc test resources:

```text
src/test/resources/contracts/
  customer/
    customer-v1.xml
    customer-v1-empty-tags.xml
    customer-v1-nil-nickname.xml
    customer-v1-namespaced.xml
    customer-v1-invalid.xml
```

Nên có fixture cho:

- Payload hợp lệ tối thiểu.
- Payload đầy đủ các field.
- Collection có nhiều phần tử.
- Collection rỗng và null.
- Element bị thiếu, element rỗng và `xsi:nil`.
- Namespace mặc định và namespace có prefix.
- Giá trị biên của number/date/enum.
- Unknown element nếu hợp đồng cho phép.
- Payload không hợp lệ cần bị từ chối.

Không tạo fixture chỉ từ output của mapper đang kiểm thử rồi xem nó là chuẩn duy nhất. Nếu mapper đã ghi sai cấu trúc, fixture sinh từ chính nó sẽ đóng băng lỗi đó.

## 18. Test serialize theo cấu trúc XML, không so sánh chuỗi mù quáng

Ví dụ test với XMLUnit:

```java
import org.junit.jupiter.api.Test;
import org.xmlunit.builder.DiffBuilder;
import org.xmlunit.diff.Diff;

import static org.junit.jupiter.api.Assertions.assertFalse;

@Test
void writesCustomerXmlContract() throws Exception {
    CustomerXml customer = new CustomerXml();
    customer.setId("cus-1042");
    customer.setDisplayName("Nguyen An");
    customer.setTags(List.of("premium", "newsletter"));

    String actual = xmlMapper.writeValueAsString(customer);

    String expected = """
        <customer id="cus-1042">
          <display-name>Nguyen An</display-name>
          <tags>
            <tag>premium</tag>
            <tag>newsletter</tag>
          </tags>
        </customer>
        """;

    Diff diff = DiffBuilder.compare(expected)
        .withTest(actual)
        .ignoreWhitespace()
        .checkForSimilar()
        .build();

    assertFalse(diff.hasDifferences(), diff.toString());
}
```

XMLUnit so sánh cấu trúc XML nên không phụ thuộc indentation hoặc thứ tự attribute như string equality. Nhưng cần hiểu chính sách comparison của test:

- Namespace URI cần được so sánh.
- Thứ tự child element có thể có ý nghĩa và phải được kiểm tra.
- Text content phải được giữ.
- Attribute phải ở đúng vị trí attribute.
- Wrapper và child element phải đúng tên.
- Nếu XML declaration/encoding là yêu cầu, kiểm tra riêng.

Đối với một số contract, XPath assertion giúp thông báo lỗi chính xác hơn:

```java
// Pseudocode: parse XML namespace-aware, then assert:
assertEquals("customer", root.getLocalName());
assertEquals("cus-1042", root.getAttribute("id"));
assertEquals("Nguyen An", displayNameElement.getTextContent());
```

Nếu dùng DOM/XPath, bật namespace awareness và kiểm tra URI, không chỉ prefix.

## 19. Test deserialize fixture thành ý nghĩa nghiệp vụ

Kiểm tra object sau khi đọc fixture:

```java
@Test
void readsCustomerXmlFixture() throws Exception {
    CustomerXml customer = xmlMapper.readValue(
        resource("contracts/customer/customer-v1.xml"),
        CustomerXml.class
    );

    assertEquals("cus-1042", customer.getId());
    assertEquals("Nguyen An", customer.getDisplayName());
    assertEquals(
        List.of("premium", "newsletter"),
        customer.getTags()
    );
}
```

Test này chứng minh mapper hiểu fixture. Nó nên đi kèm contract test output để tránh chỉ xác nhận object mapping mà bỏ qua wire shape.

Với empty/null, test riêng từng trạng thái:

```java
@Test
void distinguishesMissingEmptyAndNilNickname() throws Exception {
    CustomerXml missing = readFixture("customer-missing-nickname.xml");
    CustomerXml empty = readFixture("customer-empty-nickname.xml");
    CustomerXml nil = readFixture("customer-nil-nickname.xml");

    // Assert the exact contract semantics for this application.
}
```

Các assertion cần phản ánh hợp đồng đã chọn. Không mặc định rằng cả ba giá trị đều phải thành null.

## 20. Validate XML bằng XSD khi schema có quy định

XML contract thường có XSD. Jackson Databind ánh xạ XML vào Java; XSD validation là bước độc lập để kiểm tra cấu trúc XML theo schema.

Có thể dùng JAXP:

```java
SchemaFactory schemaFactory = SchemaFactory.newInstance(
    XMLConstants.W3C_XML_SCHEMA_NS_URI
);

Schema schema = schemaFactory.newSchema(xsdFile);

Validator validator = schema.newValidator();
validator.validate(new StreamSource(new StringReader(xml)));
```

Test output theo hai bước:

1. Serialize object thành XML.
2. Validate XML output bằng XSD.

Tương tự, fixture đầu vào có thể được validate trước khi deserialize để tách lỗi schema khỏi lỗi mapping.

Nếu XSD import/include schema khác, cấu hình resolver và nguồn schema một cách kiểm soát. Không cho phép tài liệu không đáng tin cậy tùy ý truy cập file hoặc URL bên ngoài trong quá trình resolve schema.

## 21. Test tương thích khi thay mapper hoặc nâng phiên bản

Khi thay `XmlMapper`, module hoặc Jackson version, chạy cùng bộ fixture qua cấu hình cũ và mới.

Một ma trận cơ bản:

| Test | Mapper/cấu hình cũ | Mapper/cấu hình mới | Mục tiêu |
| --- | --- | --- | --- |
| Đọc fixture XML cũ | Đọc được | Đọc được | Backward compatibility |
| Ghi object mẫu | Output theo contract | Output theo contract | Không đổi wire shape ngoài ý muốn |
| Empty/null fixture | Semantics cũ | Semantics mới đã xác nhận | Không đổi meaning âm thầm |
| Namespace fixture | URI đúng | URI đúng | Giữ namespace contract |
| Collection fixture | Wrapper/order đúng | Wrapper/order đúng | Giữ cấu trúc danh sách |
| Invalid fixture | Từ chối đúng | Từ chối đúng | Không nới validation ngoài ý muốn |
| Unknown element | Policy đã định | Policy đã định | Giữ strict/lenient behavior |

Không nhất thiết output mới phải byte-for-byte giống output cũ. Nếu prefix namespace hoặc indentation đổi nhưng XML infoset và contract vẫn tương đương, đó có thể là thay đổi không ảnh hưởng consumer. Tuy nhiên, nếu consumer so sánh raw text hoặc chữ ký số được tính trên bytes, byte-level compatibility có thể là yêu cầu thật và cần test riêng.

## 22. Kiểm thử cả hai chiều khi dùng JSON và XML cho cùng domain

Nếu hệ thống cung cấp cùng dữ liệu qua JSON và XML, hãy định nghĩa một domain expectation độc lập:

```java
Customer expected = new Customer(
    "cus-1042",
    "Nguyen An",
    List.of("premium", "newsletter")
);
```

Sau đó đọc từng fixture vào DTO/domain tương ứng rồi so sánh các giá trị có ý nghĩa:

```java
Customer fromJson = jsonMapper.readValue(jsonFixture, Customer.class);
Customer fromXml = xmlMapper.readValue(xmlFixture, Customer.class);

assertEquals(expected.getId(), fromJson.getId());
assertEquals(expected.getId(), fromXml.getId());

assertEquals(expected.getDisplayName(), fromJson.getDisplayName());
assertEquals(expected.getDisplayName(), fromXml.getDisplayName());

assertEquals(expected.getTags(), fromJson.getTags());
assertEquals(expected.getTags(), fromXml.getTags());
```

Đây là semantic equivalence test: hai định dạng có thể có cấu trúc khác nhau nhưng biểu đạt cùng dữ liệu nghiệp vụ.

Không so sánh JSON string với XML string. Cũng không dùng một mapper để tự tạo cả hai fixture rồi coi chúng là hai nguồn độc lập. Fixture nên được xác nhận theo từng hợp đồng.

## 23. Kiểm tra bảo mật parser XML

XML có các tính năng như DTD và external entity. Khi đọc XML từ nguồn không đáng tin cậy, cần kiểm tra cấu hình StAX/XML parser mà `XmlFactory` sử dụng.

Các rủi ro cần tránh:

- External entity có thể yêu cầu đọc file hoặc truy cập tài nguyên bên ngoài.
- DTD/entity expansion có thể gây tiêu thụ tài nguyên.
- Schema resolver có thể tải tài liệu từ vị trí không mong muốn.
- Payload lớn hoặc sâu vẫn cần giới hạn kích thước và độ sâu.

Không giả định việc dùng `XmlMapper` tự động giải quyết mọi chính sách bảo mật của XML parser. Cấu hình XML input factory theo phiên bản và provider StAX đang dùng, sau đó viết test xác nhận DTD/external entity bị từ chối theo chính sách ứng dụng.

Các kiểm thử bảo mật này cần chạy trên runtime thực tế vì provider StAX khác nhau có thể hỗ trợ feature khác nhau.

## 24. Lỗi thường gặp khi đổi mapper

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Object Java đọc được nhưng XML output sai shape | Chỉ dùng annotation JSON, chưa khai báo XML root/attribute/wrapper | So sánh XML với fixture contract |
| Collection thêm wrapper ngoài ý muốn | Default wrapper của `JacksonXmlModule` hoặc annotation thay đổi | Test nhiều phần tử, rỗng và null |
| Attribute biến thành element | Thiếu hoặc đổi `isAttribute = true` | Assert node type và vị trí trong XML |
| Namespace prefix khác | Generator chọn prefix khác | So sánh namespace URI và local name |
| XML hợp lệ cú pháp nhưng consumer từ chối | Sai namespace, order, wrapper hoặc XSD | Validate bằng XSD và test consumer contract |
| Empty element thành null | `FromXmlParser.Feature` hoặc coercion policy | Fixture riêng cho empty và `xsi:nil` |
| Date/time đổi format | Thiếu `JavaTimeModule` hoặc config timestamp khác | Assert lexical format và timezone |
| Unknown element bị mất | Bật ignore unknown nhưng không có extension storage | Test deserialize rồi serialize lại |
| Test round-trip vẫn pass dù contract sai | Serializer/deserializer cùng dùng sai quy tắc | So sánh với fixture độc lập |
| Upgrade Jackson làm thay đổi output | Module/config/default khác giữa version | Chạy compatibility matrix trên fixture |
| Test fail vì whitespace/prefix | So sánh raw string quá chặt | XML-aware comparison, giữ assertion cho phần thực sự có nghĩa |
| Test pass dù thứ tự child sai | Comparison policy không kiểm tra thứ tự | Assert sequence hoặc validate XSD |

## 25. Quy trình kiểm thử tương thích

Khi thay mapper, module hoặc phiên bản Jackson:

1. Xác định JSON/XML contract hiện tại và consumer thực tế.
2. Lưu fixture độc lập cho các payload quan trọng.
3. Ghi nhận phiên bản Core, Databind, XML module và datatype module.
4. Cấu hình mapper mới tường minh về root, namespace, attribute, wrapper, null và date/time.
5. Chạy fixture cũ qua mapper mới để kiểm tra đọc.
6. Serialize object chuẩn và so sánh với contract fixture/schema.
7. Kiểm tra empty, missing, null, collection, unknown element và invalid input.
8. Validate XML bằng XSD nếu hợp đồng có schema.
9. So sánh semantic object giữa JSON/XML khi hai định dạng cùng biểu đạt domain.
10. Chạy compatibility matrix trước và sau thay đổi.
11. Chỉ chấp nhận output khác khi có quyết định hợp đồng rõ ràng.
12. Cập nhật fixture/schema/tài liệu cùng lúc với thay đổi breaking đã được phê duyệt.

## 26. Bài thực hành tổng hợp

Tạo một model Customer và hai wire format.

### Phần A — JSON contract

1. Tạo JSON fixture có `id`, `displayName` và `tags`.
2. Đọc bằng `ObjectMapper`.
3. Assert các giá trị nghiệp vụ.
4. Serialize lại và so sánh với JSON contract bằng JSON tree, không phụ thuộc whitespace.

### Phần B — XML contract

1. Tạo `CustomerXml` với `@JacksonXmlRootElement`.
2. Ánh xạ `id` thành attribute.
3. Ánh xạ `displayName` thành element `display-name`.
4. Cấu hình collection có wrapper `tags` và item `tag`.
5. Đọc XML fixture bằng `XmlMapper`.
6. Serialize lại và so sánh cấu trúc bằng XMLUnit.
7. Assert namespace URI, root name, attribute, wrapper và thứ tự child nếu contract yêu cầu.

### Phần C — Trạng thái biên

Tạo fixture cho:

1. Element bị thiếu.
2. Empty element.
3. `xsi:nil`.
4. Collection rỗng.
5. Collection null.
6. Unknown element.
7. Namespace URI không đúng.
8. Giá trị number/date sai format.

Viết assertion riêng theo semantics đã chọn.

### Phần D — Compatibility khi thay mapper

1. Giữ mapper/cấu hình cũ trong test migration nếu có thể.
2. Chạy cùng fixture với mapper mới.
3. So sánh object/domain values.
4. So sánh output với contract fixture.
5. Validate XSD.
6. Ghi lại mọi khác biệt có chủ đích và cập nhật tài liệu hợp đồng.
7. Không chấp nhận khác biệt chỉ vì round-trip mới vẫn thành công.

Bài thực hành hoàn thành khi có thể chứng minh mapper mới đọc được dữ liệu cũ, ghi đúng wire contract và giữ nguyên ý nghĩa nghiệp vụ trên các trường hợp biên quan trọng.

## 27. Nguyên tắc ghi nhớ

- `ObjectMapper` và `XmlMapper` dùng các backend định dạng khác nhau; cùng DTO không bảo đảm cùng wire semantics.
- XML có element, attribute, namespace, root, wrapper, text node và thứ tự child; JSON không có cấu trúc tương đương trực tiếp.
- Dùng annotation XML để xác định root, attribute, element, namespace và collection wrapper.
- Kiểm tra collection có wrapper hay lặp trực tiếp; test cả nhiều phần tử, rỗng và null.
- Namespace URI quan trọng hơn prefix; attribute không tự nhận default namespace của element.
- Missing, empty element và `xsi:nil` là các trạng thái cần kiểm thử riêng.
- Coercion của number, boolean, date/time và enum phải được quy định, không dựa vào mặc định ngầm.
- Root element, thứ tự child, XML declaration và encoding có thể là yêu cầu của consumer.
- Round-trip chỉ chứng minh mapper tự đọc được output của mình; contract fixture độc lập mới kiểm tra wire format.
- Dùng XML-aware comparison và XSD validation khi phù hợp; không so sánh raw string nếu whitespace/prefix không thuộc hợp đồng.
- Khi cùng domain có JSON và XML, so sánh semantic object qua expectation độc lập.
- Nâng Jackson hoặc đổi module phải chạy compatibility matrix trên fixture cũ và mới.
- Kiểm tra cấu hình DTD/external entity và giới hạn tài nguyên khi đọc XML không đáng tin cậy.

Khi thay mapper hoặc cấu hình Jackson, hãy kiểm thử dữ liệu như một hợp đồng độc lập. Giữ fixture đại diện, xác nhận cấu trúc XML/JSON thực tế và so sánh ý nghĩa nghiệp vụ; chỉ khi những kiểm tra đó chứng minh tương thích mới có thể kết luận thay đổi mapper giữ nguyên hành vi mà consumer đang phụ thuộc.
