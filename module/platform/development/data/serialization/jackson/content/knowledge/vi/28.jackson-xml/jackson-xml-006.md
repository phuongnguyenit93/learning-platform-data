# Phân biệt phần tử vắng mặt, phần tử rỗng và giá trị null

XML có thể biểu diễn dữ liệu không có mặt, phần tử có nội dung rỗng và giá trị null theo những cách khác nhau. Ba trạng thái này thường bị gộp thành một khi ứng dụng chỉ nhìn vào giá trị Java sau deserialize. Điều đó dễ gây lỗi khi cập nhật dữ liệu, đọc message từ hệ thống khác hoặc chuyển đổi XML thành domain object.

Với Jackson XML, XmlMapper chuyển XML thành POJO thông qua cơ chế databinding của Jackson. Phần tử không xuất hiện thường không tạo ra lời gọi setter; phần tử rỗng có thể được đọc như chuỗi rỗng hoặc null tùy kiểu đích và cấu hình parser; giá trị null tường minh thường được biểu diễn bằng thuộc tính xsi:nil="true". Các collection, attribute và creator property còn có quy tắc riêng.

Muốn giữ đúng semantics, trước tiên phải định nghĩa hợp đồng XML: khi nào một field bị bỏ qua, khi nào nó được xóa, khi nào nó là chuỗi rỗng và khi nào collection rỗng khác collection null. Sau đó cấu hình XmlMapper, creator/setter và null policy theo hợp đồng đó, rồi kiểm thử bằng XML thực tế. Đừng suy ra trạng thái của XML chỉ từ một giá trị Java null sau deserialize.

## 1. Ba trạng thái trong XML

Giả sử model có property nickname. XML có thể thể hiện ba trạng thái:

### 1.1. Phần tử vắng mặt

```xml
<customer>
  <id>c-17</id>
</customer>
```

Không có phần tử nickname. Đây là trạng thái **missing**. Trong một bean mutable, Jackson thường không gọi setter cho property này; field giữ giá trị khởi tạo hoặc giá trị mặc định của Java. Với creator-based binding, property có thể được coi là thiếu và chịu chính sách required/missing creator.

### 1.2. Phần tử rỗng

```xml
<customer>
  <id>c-17</id>
  <nickname/>
</customer>
```

Hoặc cách viết tương đương:

```xml
<customer>
  <id>c-17</id>
  <nickname></nickname>
</customer>
```

Phần tử tồn tại nhưng không có nội dung text. Đây là **empty element**. Khi ánh xạ sang String, Jackson XML có thể biểu diễn thành chuỗi rỗng; feature FromXmlParser.Feature.EMPTY_ELEMENT_AS_NULL có thể thay đổi cách xử lý phần tử rỗng thành null. Vì vậy, phải chọn và kiểm thử cấu hình rõ ràng.

### 1.3. Giá trị null tường minh

XML Schema Instance định nghĩa thuộc tính xsi:nil để biểu diễn phần tử null:

```xml
<customer xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <id>c-17</id>
  <nickname xsi:nil="true"/>
</customer>
```

Phần tử nickname có mặt, nhưng được đánh dấu null. Jackson XML có thể xử lý marker này qua FromXmlParser.Feature.PROCESS_XSI_NIL. Khi feature được bật, xsi:nil="true" được chuyển thành null value cho databinding.

Ba dạng XML không đồng nghĩa:

| XML | Ý nghĩa dữ liệu | Trạng thái mong muốn |
|---|---|---|
| Không có phần tử nickname | Không cung cấp property | Missing |
| Phần tử nickname không có nội dung | Có property, text rỗng | Empty |
| Phần tử nickname có xsi:nil="true" | Có property, được đánh dấu null | Explicit null |

Trong một hợp đồng API, missing có thể có nghĩa “không thay đổi”, empty có thể có nghĩa “đặt thành chuỗi rỗng”, còn null có thể có nghĩa “xóa giá trị”. Nếu hệ thống không cần phân biệt, có thể chuẩn hóa chúng theo một policy; nhưng đó phải là quyết định có chủ đích.

## 2. XmlMapper và Jackson XML

Jackson XML được cung cấp bởi module jackson-dataformat-xml. XmlMapper là mapper chuyên xử lý XML:

```java
import com.fasterxml.jackson.dataformat.xml.XmlMapper;

XmlMapper mapper = new XmlMapper();
Customer customer = mapper.readValue(xml, Customer.class);
```

Nên dùng cùng dòng version tương thích cho jackson-core, jackson-databind, jackson-annotations và jackson-dataformat-xml. Các feature XML và chi tiết token có thể thay đổi theo version, vì vậy hãy kiểm tra dependency thực tế của dự án.

Model có thể dùng annotation XML để đặt tên element, attribute và wrapper:

```java
@JacksonXmlRootElement(localName = "customer")
public class Customer {
    private String id;
    private String nickname;

    @JacksonXmlProperty(localName = "id")
    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    @JacksonXmlProperty(localName = "nickname")
    public String getNickname() { return nickname; }
    public void setNickname(String nickname) { this.nickname = nickname; }
}
```

Jackson XML sử dụng annotation databinding như JsonSetter, JsonCreator, JsonProperty và JsonInclude cùng với annotation riêng như JacksonXmlProperty, JacksonXmlElementWrapper và JacksonXmlRootElement.

## 3. Cấu hình phần tử rỗng và xsi:nil

Jackson XML có các feature đọc XML liên quan đến phần tử rỗng và marker null. Có thể cấu hình rõ khi tạo mapper:

```java
XmlMapper mapper = XmlMapper.builder()
    .enable(FromXmlParser.Feature.PROCESS_XSI_NIL)
    .disable(FromXmlParser.Feature.EMPTY_ELEMENT_AS_NULL)
    .build();
```

Ý nghĩa của cấu hình minh họa:

- PROCESS_XSI_NIL: xử lý xsi:nil như tín hiệu null trong XML.
- EMPTY_ELEMENT_AS_NULL: khi bật, phần tử XML rỗng được diễn giải thành null thay vì giá trị rỗng mặc định của parser.

Trong ví dụ trên, EMPTY_ELEMENT_AS_NULL bị tắt để giữ khả năng phân biệt phần tử rỗng dạng text với xsi:nil cho các property String. Nếu bật feature này, phần tử rỗng có thể đi vào cùng đường xử lý null và làm mất khác biệt giữa empty và null.

Đừng dựa vào default của thư viện mà không kiểm tra version và cấu hình mapper. Hãy tạo test cho cả phần tử nickname rỗng và phần tử nickname có xsi:nil bằng chính XmlMapper được ứng dụng sử dụng.

### 3.1. Ví dụ đọc ba trạng thái

```java
XmlMapper mapper = XmlMapper.builder()
    .enable(FromXmlParser.Feature.PROCESS_XSI_NIL)
    .disable(FromXmlParser.Feature.EMPTY_ELEMENT_AS_NULL)
    .build();

Customer missing = mapper.readValue(
    "<customer><id>c-17</id></customer>",
    Customer.class
);

Customer empty = mapper.readValue(
    "<customer><id>c-17</id><nickname/></customer>",
    Customer.class
);

Customer nil = mapper.readValue(
    """
    <customer xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
      <id>c-17</id>
      <nickname xsi:nil="true"/>
    </customer>
    """,
    Customer.class
);
```

Nếu nickname là field mutable được khởi tạo null, giá trị sau binding thường có thể là:

| Input | Giá trị nickname có thể quan sát |
|---|---|
| Missing | Giữ giá trị khởi tạo hiện có; trong ví dụ là null |
| Empty element | Chuỗi rỗng |
| xsi:nil="true" | null |

Hai trạng thái missing và null cùng cho kết quả Java null nếu field ban đầu null. Để phân biệt chúng, cần lưu presence riêng thay vì chỉ nhìn getter sau deserialize.

### 3.2. Explicit null cần đúng namespace

Marker null chuẩn dùng namespace XML Schema Instance:

```xml
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
```

Sau đó dùng xsi:nil="true" trên element. Prefix xsi chỉ là tên prefix quy ước; namespace URI mới xác định ý nghĩa. Có thể dùng prefix khác nếu nó ánh xạ tới đúng URI, nhưng nên giữ xsi để XML dễ đọc và nhất quán.

xsi:nil="false" không biểu diễn null. XML Schema boolean còn có lexical form 1 và 0, nhưng để tránh khác biệt giữa producer/consumer, nên thống nhất dùng true và false.

## 4. Phần tử rỗng không giống phần tử chỉ có whitespace

Hai phần tử sau có nội dung khác nhau:

```xml
<nickname/>
<nickname> </nickname>
```

Phần tử đầu không có text. Phần tử thứ hai chứa một ký tự khoảng trắng. Với String, parser có thể giữ khoảng trắng đó. Không tự động coi whitespace-only là empty nếu hợp đồng XML không quy định trim.

Các trường hợp:

```xml
<nickname></nickname>
<nickname>   </nickname>
<nickname> An </nickname>
```

Đều cần policy riêng:

- Empty text: có thể là chuỗi rỗng.
- Whitespace-only: có thể được giữ nguyên, trim hoặc từ chối.
- Text có khoảng trắng hai đầu: có thể giữ nguyên hoặc chuẩn hóa theo contract.

Nếu cần trim, thực hiện rõ trong creator/factory hoặc bước validation. Đừng bật một xử lý toàn cục làm thay đổi nội dung của mọi String, vì một số field có thể là password, mã ký hiệu hoặc nội dung văn bản mà whitespace có ý nghĩa.

## 5. Phần tử thiếu trong mutable bean

Với bean có constructor mặc định và setter, Jackson thường tạo instance trước rồi gán các property xuất hiện trong XML. Property không xuất hiện sẽ không được gán:

```java
public class Customer {
    private String nickname = "Guest";

    public String getNickname() {
        return nickname;
    }

    public void setNickname(String nickname) {
        this.nickname = nickname;
    }
}
```

Nếu XML không có nickname, field có thể giữ "Guest". Nếu XML có xsi:nil="true" và parser chuyển thành null, setter có thể nhận null và thay giá trị mặc định.

Có thể dùng JsonSetter(nulls = Nulls.SKIP) để bỏ qua explicit null:

```java
public class Customer {
    private String nickname = "Guest";

    @JsonSetter(value = "nickname", nulls = Nulls.SKIP)
    public void setNickname(String nickname) {
        this.nickname = nickname;
    }
}
```

Với cấu hình phù hợp, khi XML có xsi:nil="true", Jackson bỏ qua việc gán null và giá trị khởi tạo vẫn là "Guest". Missing cũng không gọi setter, nên cả hai trường hợp có thể cùng giữ default. Nếu nghiệp vụ cần phân biệt chúng, phải theo dõi presence riêng.

Các null policy chính:

| Nulls | Hành vi khi parser cung cấp null |
|---|---|
| SET | Gán null |
| SKIP | Không gán property |
| FAIL | Báo lỗi |
| AS_EMPTY | Dùng giá trị empty do deserializer của kiểu đích cung cấp |
| DEFAULT | Dùng chính sách mặc định |

Nulls áp dụng cho explicit null mà Jackson nhận được. Nếu EMPTY_ELEMENT_AS_NULL bật, empty element có thể cũng trở thành null và đi qua null policy. Vì vậy, cấu hình empty-element và null policy phải được xem xét cùng nhau.

## 6. Phần tử thiếu trong creator-based binding

Với constructor hoặc static factory dùng JsonCreator, Jackson thu thập creator properties rồi gọi creator. Missing property không giống explicit null:

```java
public final class CustomerName {
    private final String value;

    @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
    public CustomerName(
            @JsonProperty(value = "value", required = true) String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("value is required");
        }
        this.value = value;
    }

    public String getValue() {
        return value;
    }
}
```

Có thể bật feature để từ chối creator property bị thiếu hoặc null:

```java
XmlMapper mapper = XmlMapper.builder()
    .enable(DeserializationFeature.FAIL_ON_MISSING_CREATOR_PROPERTIES)
    .enable(DeserializationFeature.FAIL_ON_NULL_CREATOR_PROPERTIES)
    .build();
```

- FAIL_ON_MISSING_CREATOR_PROPERTIES từ chối property không xuất hiện trong XML.
- FAIL_ON_NULL_CREATOR_PROPERTIES từ chối creator property nhận null, ví dụ từ xsi:nil.

Đây là cấu hình ở mapper scope và có thể tác động đến mọi creator DTO. Nếu chỉ một vài property cần bắt buộc, hãy kiểm tra trong creator hoặc dùng cấu hình riêng cho boundary tương ứng.

JsonProperty(required = true) chủ yếu có ý nghĩa metadata cho creator property; không coi nó là validation tổng quát cho mọi field mutable hoặc setter. Với XML, cần test cả trường hợp element không xuất hiện và element có xsi:nil.

## 7. Attribute cũng có trạng thái thiếu và rỗng

XML attribute không phải element con:

```xml
<customer code="C-17"/>
```

Có thể ánh xạ bằng JacksonXmlProperty(isAttribute = true):

```java
public class Customer {
    private String code;

    @JacksonXmlProperty(isAttribute = true, localName = "code")
    public String getCode() {
        return code;
    }

    public void setCode(String code) {
        this.code = code;
    }
}
```

Attribute có thể bị thiếu:

```xml
<customer/>
```

Hoặc xuất hiện nhưng rỗng:

```xml
<customer code=""/>
```

Đây là hai trạng thái khác nhau ở XML. Attribute không có cú pháp xsi:nil tương đương element; xsi:nil là thuộc tính điều khiển khả năng nil của element. Nếu cần biểu diễn null cho một giá trị dạng attribute, phải định nghĩa contract khác, ví dụ bỏ attribute và dùng metadata riêng hoặc chuyển giá trị đó thành child element nillable.

Với mutable bean, attribute bị thiếu thường để lại default; attribute rỗng có thể gán chuỗi rỗng. Nếu muốn từ chối attribute rỗng, kiểm tra trong setter/creator hoặc Bean Validation.

## 8. Collection: wrapper thiếu, wrapper rỗng và wrapper nil

Collection là nơi khác biệt giữa missing, empty và null đặc biệt quan trọng. Giả sử XML có wrapper items và mỗi phần tử là item:

```xml
<order>
  <items>
    <item><sku>A-1</sku></item>
    <item><sku>B-2</sku></item>
  </items>
</order>
```

Ánh xạ tường minh:

```java
public class Order {
    private List<Item> items;

    @JacksonXmlElementWrapper(localName = "items")
    @JacksonXmlProperty(localName = "item")
    public List<Item> getItems() {
        return items;
    }

    public void setItems(List<Item> items) {
        this.items = items;
    }
}
```

Ba dạng XML:

**Wrapper vắng mặt**

```xml
<order/>
```

**Wrapper có mặt nhưng không có item**

```xml
<order>
  <items/>
</order>
```

**Wrapper được đánh dấu null**

```xml
<order xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <items xsi:nil="true"/>
</order>
```

Ý nghĩa contract có thể là:

| Dạng | Semantics thường mong muốn |
|---|---|
| Không có wrapper | Không cung cấp danh sách; có thể giữ default/không cập nhật |
| Wrapper rỗng | Danh sách rỗng |
| Wrapper có xsi:nil | Danh sách null hoặc yêu cầu xóa danh sách |

Kết quả Java thực tế phụ thuộc XML module, empty-element feature, null handling, collection type và cách wrapper được cấu hình. Hãy dùng annotation wrapper tường minh và test bằng đúng version jackson-dataformat-xml.

### 8.1. Collection không có wrapper

Nếu schema XML dùng các item lặp trực tiếp:

```xml
<order>
  <item><sku>A-1</sku></item>
  <item><sku>B-2</sku></item>
</order>
```

Đánh dấu không dùng wrapper:

```java
@JacksonXmlElementWrapper(useWrapping = false)
@JacksonXmlProperty(localName = "item")
private List<Item> items;
```

Trong dạng này, không có element riêng để biểu diễn collection rỗng ngoài việc không có item nào. Vì vậy, missing và empty list có thể không phân biệt được chỉ từ XML. Nếu contract cần phân biệt, dùng wrapper hoặc một thuộc tính trạng thái riêng.

### 8.2. Phần tử item rỗng và item null

Trong wrapper, các dạng sau cũng khác nhau:

```xml
<items>
  <item/>
</items>
```

và:

```xml
<items xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <item xsi:nil="true"/>
</items>
```

Phần tử item rỗng có thể tạo một object con với các property mặc định hoặc một giá trị rỗng tùy kiểu item; xsi:nil biểu diễn phần tử item null nếu parser xử lý marker. Nếu list không cho phép phần tử null, có thể dùng JsonSetter(contentNulls = Nulls.FAIL) trên property collection hoặc kiểm tra trong custom deserializer.

## 9. Null policy cho collection content

JsonSetter có thể áp dụng policy riêng cho property và phần tử:

```java
public class Order {
    private List<Item> items;

    @JsonSetter(
        value = "items",
        nulls = Nulls.FAIL,
        contentNulls = Nulls.FAIL
    )
    @JacksonXmlElementWrapper(localName = "items")
    @JacksonXmlProperty(localName = "item")
    public void setItems(List<Item> items) {
        this.items = items;
    }
}
```

- nulls = Nulls.FAIL từ chối wrapper items được xử lý như null.
- contentNulls = Nulls.FAIL từ chối item null trong list.

Nếu wrapper rỗng được parser ánh xạ thành empty list, policy này vẫn cho phép list rỗng. Nếu bật EMPTY_ELEMENT_AS_NULL, wrapper rỗng có thể bị diễn giải thành null và bị từ chối bởi null policy. Điều này cho thấy hai feature cần được cấu hình cùng nhau.

Nếu collection bắt buộc không rỗng, contentNulls = FAIL chưa đủ; nó chỉ từ chối phần tử null. Hãy thêm constraint như NotEmpty, kiểm tra trong constructor/factory hoặc custom deserializer để từ chối list rỗng.

## 10. xsi:nil và XML Schema

xsi:nil thuộc XML Schema Instance namespace. Trong một schema XSD, element cần được khai báo nillable="true" nếu producer muốn dùng nil một cách hợp lệ:

```xml
<xs:element name="nickname" type="xs:string" nillable="true" minOccurs="0"/>
```

Hai thuộc tính schema này diễn tả hai khả năng khác nhau:

- minOccurs="0" cho phép element vắng mặt.
- nillable="true" cho phép element xuất hiện nhưng mang nil.

Nếu minOccurs="1", element phải xuất hiện theo schema. Nếu nillable="false", xsi:nil="true" không hợp lệ theo schema.

Jackson XML tập trung vào parse và databinding; không tự động thực thi toàn bộ XSD contract chỉ vì XML chứa namespace hoặc schema location. Nếu cần xác thực XSD, phải cấu hình validation riêng bằng API XML phù hợp hoặc tích hợp schema validator ở boundary.

Ví dụ schema:

```xml
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="customer">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="id" type="xs:string" minOccurs="1"/>
        <xs:element name="nickname" type="xs:string"
                    minOccurs="0" nillable="true"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
```

Schema trên cho phép nickname bị thiếu hoặc xuất hiện với xsi:nil="true". Nó không tự quyết định ứng dụng có muốn coi empty string là null hay không; đó là một quy tắc khác cần được nêu rõ.

## 11. Kết hợp XmlMapper với Bean Validation

Bean Validation kiểm tra object sau khi Jackson tạo nó:

```java
public class CustomerRequest {
    @NotBlank
    @Size(max = 80)
    private String displayName;

    @Email
    private String email;

    // Getters and setters
}
```

Trong Spring MVC:

```java
@PostMapping(
    path = "/customers",
    consumes = MediaType.APPLICATION_XML_VALUE
)
public CustomerView create(
        @Valid @RequestBody CustomerRequest request) {
    return customerService.create(request);
}
```

Khi endpoint được cấu hình với XML message converter dựa trên Jackson XML, @Valid có thể kích hoạt Bean Validation sau deserialize. Cần bảo đảm converter thực sự dùng XmlMapper và dependency validation đã được cấu hình.

@NotBlank từ chối null, chuỗi rỗng và chuỗi chỉ có whitespace. Nó phù hợp khi empty và null đều không hợp lệ. Nếu contract cần phân biệt missing với null hoặc empty, Bean Validation trên giá trị cuối cùng có thể không đủ; hãy giữ presence riêng trong DTO hoặc custom deserializer.

Bean Validation không thay thế XSD validation, giới hạn kích thước request hoặc quy tắc nghiệp vụ cần database/actor context.

## 12. Giữ presence khi cần phân biệt missing với null

Với mutable bean thông thường, nếu field ban đầu null thì cả missing và explicit nil có thể cho ra getter null. Có thể giữ cờ presence:

```java
public class CustomerPatch {
    private String nickname;
    private boolean nicknamePresent;

    @JsonSetter("nickname")
    public void setNickname(String nickname) {
        this.nicknamePresent = true;
        this.nickname = nickname;
    }

    public boolean isNicknamePresent() {
        return nicknamePresent;
    }

    public String getNickname() {
        return nickname;
    }
}
```

Khi xsi:nil được chuyển thành null và setter được gọi, nicknamePresent là true. Khi element vắng mặt, setter không được gọi và cờ vẫn false.

Nếu EMPTY_ELEMENT_AS_NULL bật, phần tử rỗng cũng có thể được chuyển thành null và setter được gọi với null. Khi đó cờ presence phân biệt missing với present, nhưng không phân biệt empty với nil. Nếu cần cả ba trạng thái, phải giữ thêm loại trạng thái hoặc tắt empty-as-null và kiểm tra parser behavior.

### 12.1. Dùng kiểu trạng thái tường minh

Một kiểu wrapper có thể biểu diễn rõ:

```java
public sealed interface XmlField<T> {
    record Missing<T>() implements XmlField<T> {}
    record Nil<T>() implements XmlField<T> {}
    record Empty<T>() implements XmlField<T> {}
    record Value<T>(T value) implements XmlField<T> {}
}
```

Custom deserializer hoặc adapter có thể tạo một trong bốn trạng thái. Khi đó service có thể áp dụng:

| Trạng thái | Ý nghĩa ví dụ trong PATCH |
|---|---|
| Missing | Giữ giá trị cũ |
| Nil | Xóa giá trị |
| Empty | Đặt chuỗi rỗng |
| Value | Đặt giá trị được gửi |

Đây là mô hình ứng dụng, không phải kiểu mặc định mà Jackson XML tự tạo. Cần viết custom deserializer/adapter để chuyển đúng từng dạng XML vào wrapper này.

### 12.2. Theo dõi trạng thái trong custom deserializer

Khi cần kiểm soát tuyệt đối, custom deserializer có thể theo dõi field đã xuất hiện và token của nó:

```java
public final class CustomerPatchValueDeserializer
        extends JsonDeserializer<CustomerPatchValue> {

    @Override
    public CustomerPatchValue deserialize(
            JsonParser parser,
            DeserializationContext context) throws IOException {

        // XML module exposes the element through Jackson tokens.
        // Verify the exact token sequence with the XmlMapper version in use.
        if (parser.currentToken() == JsonToken.VALUE_NULL) {
            return CustomerPatchValue.nil();
        }
        if (parser.currentToken() == JsonToken.VALUE_STRING
                && parser.getText().isEmpty()) {
            return CustomerPatchValue.empty();
        }
        if (parser.currentToken() == JsonToken.VALUE_STRING) {
            return CustomerPatchValue.value(parser.getText());
        }

        throw JsonMappingException.from(
            parser, "nickname must be text or nil"
        );
    }
}
```

Đoạn code minh họa xử lý value sau khi parser đã nhận diện property; nó không tự phát hiện missing vì deserializer của property không được gọi khi element vắng mặt. Để biểu diễn Missing, lớp chứa phải khởi tạo wrapper là Missing và chỉ thay đổi nó khi property xuất hiện, hoặc một deserializer cấp cha phải đọc toàn bộ element và theo dõi cờ seen.

Jackson XML có thể trình bày empty element thành token khác nhau tùy feature/version và kiểu property. Trước khi dùng token-level logic cho production, hãy viết test nhỏ để quan sát token thực tế từ XmlMapper đang chạy.

## 13. Phần tử có text và attribute cùng lúc

XML có thể chứa cả attribute và text:

```xml
<label lang="vi">Xin chào</label>
```

Ánh xạ:

```java
public class Label {
    @JacksonXmlProperty(isAttribute = true, localName = "lang")
    private String language;

    @JacksonXmlText
    private String text;
}
```

Trong trường hợp này:

- Attribute lang bị thiếu khác với lang rỗng.
- Text rỗng khác với text chứa whitespace.
- xsi:nil áp dụng lên element label, không phải riêng phần text property.

XML mixed content có thể phức tạp hơn khi text và child element xen kẽ. Jackson XML không phải lúc nào cũng giữ nguyên mọi chi tiết lexical của mixed content theo cách một DOM model làm được. Nếu contract phụ thuộc thứ tự text/node hoặc cần giữ raw XML, cân nhắc StAX/DOM trực tiếp thay vì chỉ dùng POJO binding.

## 14. Phần tử rỗng khi serialize

Chiều serialize cũng cần thống nhất semantics. Một String null có thể bị bỏ qua, ghi thành empty element hoặc ghi thành xsi:nil, tùy inclusion policy và cấu hình XML generator.

Có thể dùng JsonInclude để bỏ null:

```java
@JsonInclude(JsonInclude.Include.NON_NULL)
public class Customer {
    private String nickname;
}
```

Khi property null, NON_NULL yêu cầu bỏ property khỏi output. Kết quả khác với việc ghi một element có xsi:nil.

Jackson XML có feature ghi null bằng marker XSI nil:

```java
XmlMapper mapper = XmlMapper.builder()
    .enable(ToXmlGenerator.Feature.WRITE_NULLS_AS_XSI_NIL)
    .build();
```

Với feature này, null property có thể được ghi dưới dạng element nil theo cơ chế của XML generator. Nếu feature không bật, null output có thể có representation khác theo serializer/inclusion config. Hãy kiểm tra XML sinh ra bằng test thay vì giả định null luôn thành element rỗng.

### 14.1. Empty string và null khi ghi

Empty string:

```xml
<nickname></nickname>
```

Nil:

```xml
<nickname xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:nil="true"/>
```

Missing:

```xml
<customer/>
```

Nếu client downstream phân biệt ba trạng thái, output phải giữ đúng hợp đồng. NON_EMPTY có thể bỏ empty string/empty collection, làm mất trạng thái empty; NON_NULL chỉ loại null. Chọn inclusion policy dựa trên semantics mong muốn.

### 14.2. Wrapper collection khi ghi

Collection rỗng có thể cần được ghi thành wrapper rỗng:

```xml
<order>
  <items/>
</order>
```

Collection null có thể được bỏ hoặc ghi nil theo cấu hình. Nếu dùng NON_EMPTY, wrapper có thể bị loại khi list rỗng. Điều này khiến client không phân biệt được empty list và missing wrapper.

Với contract cần phân biệt, tránh áp NON_EMPTY một cách rộng cho wrapper. Test riêng null, empty list, list có item và list có null item.

## 15. Không nhầm XML element null với chuỗi ký tự "null"

Các XML sau có ý nghĩa khác nhau:

```xml
<nickname>null</nickname>
<nickname xsi:nil="true"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"/>
<nickname/>
```

- Text null là chuỗi gồm bốn ký tự n, u, l, l.
- xsi:nil="true" là null theo XML Schema Instance.
- Empty element không có text.

Jackson không nên tự diễn giải chuỗi "null" thành Java null trong XML text thông thường. Nếu hệ thống legacy dùng chuỗi đặc biệt "null", hãy viết mapping rõ ràng và xử lý nó như một convention riêng, không nhầm với XML nil.

## 16. XML parser và schema validation

XmlMapper thường dựa trên StAX parser để đọc XML. Cần bảo vệ cả parser lẫn lớp binding:

- Chỉ chấp nhận XML cần thiết cho ứng dụng.
- Cấu hình parser an toàn theo hướng dẫn của StAX implementation.
- Tắt xử lý external entities/DTD nếu không cần và bảo đảm không mở đường đọc tài nguyên ngoài.
- Giới hạn kích thước request body và thời gian đọc.
- Giới hạn độ sâu, độ dài text và số phần tử theo khả năng của parser/binding.
- Dùng XSD validation riêng nếu contract yêu cầu minOccurs, nillable, type/range và thứ tự element.

Không giả định XmlMapper tự validate XSD chỉ vì có xsi:nil hoặc xsi:schemaLocation. XML well-formed và XML hợp lệ theo schema là hai mức kiểm tra khác nhau.

Với XML không tin cậy, cần đặc biệt chú ý XXE (XML External Entity). Việc cấu hình phụ thuộc StAX factory được dùng; kiểm tra tài liệu implementation và test rằng DTD/external entity không thể đọc file hoặc gọi network ngoài ý muốn.

## 17. Kiểm thử ba trạng thái bằng XmlMapper

Test nên chạy trên đúng mapper được cấu hình trong ứng dụng. Ví dụ:

```java
class CustomerXmlTest {
    private final XmlMapper mapper = XmlMapper.builder()
        .enable(FromXmlParser.Feature.PROCESS_XSI_NIL)
        .disable(FromXmlParser.Feature.EMPTY_ELEMENT_AS_NULL)
        .build();

    @Test
    void distinguishesEmptyFromNilForString() throws Exception {
        Customer empty = mapper.readValue(
            "<customer><nickname/></customer>",
            Customer.class
        );

        Customer nil = mapper.readValue(
            """
            <customer xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
              <nickname xsi:nil="true"/>
            </customer>
            """,
            Customer.class
        );

        assertEquals("", empty.getNickname());
        assertNull(nil.getNickname());
    }
}
```

Test trên minh họa cấu hình empty-element-as-null bị tắt để String rỗng được giữ là empty. Hãy xác nhận behavior trên Jackson XML version của dự án và thêm test cho element bị thiếu.

### 17.1. Test missing không gọi setter

Có thể dùng setter theo dõi presence:

```java
public class PresenceProbe {
    private String value = "initial";
    private boolean setterCalled;

    public String getValue() { return value; }

    @JsonSetter("value")
    public void setValue(String value) {
        setterCalled = true;
        this.value = value;
    }

    public boolean isSetterCalled() { return setterCalled; }
}
```

Đọc một probe không có child value và xác nhận setter không được gọi; đọc probe có value rỗng hoặc element nil và xác nhận setter được gọi theo parser behavior đã chọn. Không dùng side effect thật trong setter để kiểm thử; cờ boolean cục bộ là đủ.

### 17.2. Test wrapper collection

Viết test riêng cho:

- Wrapper items bị thiếu.
- Wrapper items rỗng.
- Wrapper items có xsi:nil.
- Wrapper chứa item rỗng.
- Wrapper chứa item có xsi:nil.
- Wrapper có nhiều item.

Kiểm tra cả giá trị list và các phần tử. Nếu cần phân biệt missing với empty trong PATCH, kiểm tra cờ presence hoặc wrapper state thay vì chỉ so sánh list.

### 17.3. Test attribute

Kiểm tra:

- Attribute bị thiếu.
- Attribute có giá trị.
- Attribute có chuỗi rỗng.
- Attribute có whitespace.

Không giả định xsi:nil có thể dùng cho attribute.

### 17.4. Test serialize/deserialize round-trip

Tạo object với nickname null, empty string và giá trị bình thường; serialize rồi parse lại. Xác nhận XML output dùng đúng representation đã quy định và object sau round-trip giữ đúng semantics. Nếu dùng NON_NULL, NON_EMPTY hoặc WRITE_NULLS_AS_XSI_NIL, test từng cấu hình riêng.

## 18. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Missing và nil đều thành Java null | Field ban đầu null và không có presence flag | Theo dõi setter/presence hoặc dùng wrapper state. |
| Empty element thành null ngoài ý muốn | EMPTY_ELEMENT_AS_NULL đang bật | Tắt feature nếu cần giữ empty string; kiểm thử version cụ thể. |
| xsi:nil bị đọc như property lạ | XSI nil processing không được bật/hỗ trợ như mong đợi | Kiểm tra PROCESS_XSI_NIL, namespace và Jackson XML version. |
| Whitespace bị coi là empty | Code tự trim mọi text | Chỉ chuẩn hóa field theo contract. |
| Empty list bị biến thành null hoặc missing | Wrapper và empty-element policy không thống nhất | Dùng wrapper tường minh và test ba trường hợp. |
| Không phân biệt được empty list với missing | Dùng collection không wrapper | Dùng wrapper hoặc trạng thái riêng trong XML contract. |
| Null output thành element rỗng | XML generator null feature/inclusion policy | Cấu hình WRITE_NULLS_AS_XSI_NIL hoặc bỏ null có chủ đích. |
| NotBlank không phân biệt missing với nil | Validation chỉ nhìn giá trị cuối | Giữ presence metadata khi contract cần phân biệt. |
| XSD cho phép thiếu nhưng không cho nil | minOccurs và nillable là hai quy tắc khác nhau | Khai báo đúng cả hai trong schema. |
| XML parse được nhưng không đúng schema | Chỉ dùng XmlMapper, không chạy XSD validation | Thêm schema validation ở boundary. |

## 19. Quy trình thiết kế contract XML

1. Liệt kê từng property có thể bị thiếu, rỗng hoặc null.
2. Quy định ý nghĩa của missing, empty text và xsi:nil trong hợp đồng XML.
3. Với element cần nil, khai báo nillable="true" trong XSD nếu schema validation được dùng.
4. Với element có thể vắng mặt, khai báo minOccurs="0" theo schema.
5. Cấu hình PROCESS_XSI_NIL và EMPTY_ELEMENT_AS_NULL phù hợp với semantics mong muốn.
6. Dùng annotation XML tường minh cho root, element, attribute và collection wrapper.
7. Dùng creator/setter null policy cho required, explicit null và collection content.
8. Giữ presence riêng nếu application phải phân biệt missing với null sau binding.
9. Dùng Bean Validation cho constraint trên object và XSD validation khi contract yêu cầu.
10. Kiểm tra request size, parser security và giới hạn collection ở boundary.
11. Test empty, nil, missing, whitespace, attribute, wrapper và round-trip bằng đúng XmlMapper production.
12. Tài liệu hóa semantics cho producer/consumer để hai phía không diễn giải khác nhau.

XML có thể biểu diễn phần tử vắng mặt, phần tử rỗng và null tường minh, nhưng các trạng thái đó chỉ được giữ nếu contract và cấu hình Jackson cùng bảo vệ chúng. xsi:nil là cách biểu diễn null chuẩn của XML Schema Instance; empty element là phần tử không có nội dung; missing nghĩa là element không xuất hiện. Khi cần cập nhật dữ liệu hoặc đồng bộ giữa nhiều hệ thống, hãy giữ presence metadata và kiểm thử từng dạng XML để không vô tình biến “không gửi”, “xóa” và “đặt rỗng” thành cùng một thao tác.
