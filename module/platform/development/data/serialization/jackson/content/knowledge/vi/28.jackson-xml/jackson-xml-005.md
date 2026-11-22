# Ánh xạ collection có hoặc không có phần tử bao

XML biểu diễn một collection theo cách khác JSON. Trong JSON, một danh sách thường là array nằm dưới một property. Trong XML, một danh sách có thể được biểu diễn bằng một phần tử bao chứa các phần tử con, hoặc bằng nhiều phần tử cùng tên nằm trực tiếp dưới phần tử cha.

Jackson XML hỗ trợ cả hai kiểu biểu diễn thông qua **`@JacksonXmlElementWrapper`**. Annotation này cho biết collection có được đặt trong một wrapper element hay không. Kết hợp với **`@JacksonXmlProperty`**, ứng dụng có thể kiểm soát tên wrapper và tên của từng item.

Hai dạng XML phổ biến:

```xml
<order>
  <lines>
    <line>...</line>
    <line>...</line>
  </lines>
</order>
```

và:

```xml
<order>
  <line>...</line>
  <line>...</line>
</order>
```

Dạng đầu có wrapper `lines`; dạng sau không có wrapper và lặp lại element `line` trực tiếp bên trong `order`. Chọn đúng cách ánh xạ là điều cần thiết để serialize và deserialize khớp với XML contract của hệ thống bên ngoài.

## 1. Jackson XML và XmlMapper

Jackson XML nằm trong module `jackson-dataformat-xml`. Lớp chính để đọc/ghi XML là `XmlMapper`, một mapper được mở rộng từ Databind để làm việc với XML parser/generator.

Thêm dependency cùng dòng version với các module Jackson còn lại của ứng dụng.

**Maven:**

```xml
<dependency>
    <groupId>com.fasterxml.jackson.dataformat</groupId>
    <artifactId>jackson-dataformat-xml</artifactId>
    <version>${jackson.version}</version>
</dependency>
```

**Gradle:**

```groovy
implementation("com.fasterxml.jackson.dataformat:jackson-dataformat-xml:${jacksonVersion}")
```

Nếu project dùng Jackson BOM hoặc dependency management của framework, nên để BOM quản lý version thay vì đặt một version riêng có thể lệch với `jackson-core` và `jackson-databind`.

Tạo mapper:

```java
XmlMapper xmlMapper = new XmlMapper();
```

Hoặc dùng builder nếu project đang sử dụng API builder của version tương ứng:

```java
XmlMapper xmlMapper = XmlMapper.builder().build();
```

Các annotation XML thường dùng thuộc package:

```java
import com.fasterxml.jackson.dataformat.xml.XmlMapper;
import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlElementWrapper;
import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlProperty;
import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlRootElement;
```

Jackson XML dùng các annotation riêng vì khái niệm element, attribute và wrapper không hoàn toàn tương đương với property JSON.

## 2. Collection có phần tử bao (wrapped collection)

Giả sử một đơn hàng có nhiều dòng hàng:

```java
public class OrderLine {
    private String sku;
    private int quantity;

    public OrderLine() {
    }

    public OrderLine(String sku, int quantity) {
        this.sku = sku;
        this.quantity = quantity;
    }

    public String getSku() {
        return sku;
    }

    public void setSku(String sku) {
        this.sku = sku;
    }

    public int getQuantity() {
        return quantity;
    }

    public void setQuantity(int quantity) {
        this.quantity = quantity;
    }
}
```

DTO đơn hàng:

```java
@JacksonXmlRootElement(localName = "order")
public class Order {
    private String id;

    @JacksonXmlElementWrapper(localName = "lines")
    @JacksonXmlProperty(localName = "line")
    private List<OrderLine> lines;

    public Order() {
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public List<OrderLine> getLines() {
        return lines;
    }

    public void setLines(List<OrderLine> lines) {
        this.lines = lines;
    }
}
```

Hai annotation trên collection có nhiệm vụ khác nhau:

- `@JacksonXmlElementWrapper(localName = "lines")` tạo element bao tên `lines`.
- `@JacksonXmlProperty(localName = "line")` đặt tên cho mỗi item bên trong collection là `line`.

XML kết quả có dạng:

```xml
<order>
  <id>ORD-100</id>
  <lines>
    <line>
      <sku>BOOK-01</sku>
      <quantity>2</quantity>
    </line>
    <line>
      <sku>PEN-02</sku>
      <quantity>5</quantity>
    </line>
  </lines>
</order>
```

Wrapper là một element riêng, bao quanh các item. Các item vẫn là những element lặp lại cùng tên.

### 2.1. Mặc định của wrapper

Jackson XML mặc định dùng wrapper cho collection trong cấu hình thông thường. Nếu không chỉ định annotation, tên wrapper và tên item có thể được suy ra từ tên property theo quy tắc introspection của mapper.

Ví dụ property `lines` có thể tạo cấu trúc dạng:

```xml
<lines>
  <lines>...</lines>
  <lines>...</lines>
</lines>
```

Khi XML contract yêu cầu tên wrapper và item khác nhau, hãy khai báo tường minh cả `@JacksonXmlElementWrapper` lẫn `@JacksonXmlProperty`. Điều này giúp tránh phụ thuộc vào tên mặc định và làm cấu trúc dễ đọc hơn.

### 2.2. Đổi tên wrapper

Tên wrapper được đặt bằng `localName`:

```java
@JacksonXmlElementWrapper(localName = "orderLines")
@JacksonXmlProperty(localName = "line")
private List<OrderLine> lines;
```

XML:

```xml
<orderLines>
  <line>...</line>
</orderLines>
```

Tên Java property vẫn là `lines`; chỉ tên element XML được thay đổi. Có thể dùng cách này khi XML contract đã tồn tại và không trùng với naming convention Java.

## 3. Collection không có phần tử bao (unwrapped collection)

Một số XML contract không dùng element container. Các item xuất hiện trực tiếp dưới element cha:

```xml
<order>
  <id>ORD-100</id>
  <line>
    <sku>BOOK-01</sku>
    <quantity>2</quantity>
  </line>
  <line>
    <sku>PEN-02</sku>
    <quantity>5</quantity>
  </line>
</order>
```

Để tạo cấu trúc này, dùng `useWrapping = false`:

```java
@JacksonXmlRootElement(localName = "order")
public class Order {
    private String id;

    @JacksonXmlElementWrapper(useWrapping = false)
    @JacksonXmlProperty(localName = "line")
    private List<OrderLine> lines;

    // Getter và setter
}
```

`@JacksonXmlElementWrapper(useWrapping = false)` yêu cầu Jackson không tạo element bao cho collection. Mỗi phần tử trong list được ghi trực tiếp thành một element `line` ở cấp của `order`.

### 3.1. Vì sao vẫn cần JacksonXmlProperty?

Khi bỏ wrapper, `@JacksonXmlElementWrapper` chỉ quyết định collection không có container. Tên của mỗi item được điều khiển bằng `@JacksonXmlProperty`:

```java
@JacksonXmlElementWrapper(useWrapping = false)
@JacksonXmlProperty(localName = "product")
private List<OrderLine> lines;
```

Kết quả là nhiều element `<product>` trực tiếp dưới `<order>`. Tên field Java `lines` không bắt buộc phải giống tên item XML.

Không nên chỉ đặt `useWrapping = false` rồi cho rằng Jackson sẽ tự chọn đúng tên item theo schema bên ngoài. Nếu tên element có ý nghĩa trong contract, hãy khai báo `localName` tường minh.

### 3.2. Dạng không wrapper phù hợp khi nào?

Dùng unwrapped collection khi:

- XML của hệ thống ngoài lặp lại cùng một element trực tiếp dưới parent.
- Schema XSD khai báo một phần tử có `maxOccurs` lớn hơn 1 nhưng không có container riêng.
- Cần tương thích với một XML format cũ không có wrapper.
- Parent element đã là container ngữ nghĩa và không cần thêm một cấp XML.

Nếu có quyền thiết kế schema mới, wrapper thường làm ranh giới collection rõ ràng hơn, đặc biệt khi cần biểu diễn trạng thái collection rỗng. Tuy nhiên, định dạng thực tế của hệ thống tích hợp luôn là yếu tố quyết định.

## 4. So sánh wrapped và unwrapped

Hai cách biểu diễn có cùng dữ liệu Java nhưng tạo ra XML khác nhau:

| Đặc điểm | Wrapped | Unwrapped |
|---|---|---|
| Wrapper element | Có | Không |
| Item element | Nằm bên trong wrapper | Nằm trực tiếp dưới parent |
| Annotation | `@JacksonXmlElementWrapper(localName = "lines")` | `@JacksonXmlElementWrapper(useWrapping = false)` |
| Tên item | `@JacksonXmlProperty(localName = "line")` | `@JacksonXmlProperty(localName = "line")` |
| Empty collection | Có thể biểu diễn bằng wrapper rỗng | Không có item nên thường không có dấu hiệu riêng để phân biệt empty với absent |
| Hợp đồng XSD | Thường là element container chứa item lặp | Thường là item lặp trực tiếp dưới parent |

Hãy chọn theo XML schema hoặc ví dụ payload thực tế, không chỉ theo cấu trúc List trong Java.

## 5. Đọc XML wrapped collection

Khi property được cấu hình wrapper, Jackson mong đợi element bao chứa các item. Ví dụ:

```xml
<order>
  <id>ORD-100</id>
  <lines>
    <line>
      <sku>BOOK-01</sku>
      <quantity>2</quantity>
    </line>
    <line>
      <sku>PEN-02</sku>
      <quantity>5</quantity>
    </line>
  </lines>
</order>
```

Deserialize:

```java
XmlMapper mapper = new XmlMapper();
Order order = mapper.readValue(xml, Order.class);

System.out.println(order.getLines().size());
System.out.println(order.getLines().get(0).getSku());
```

Jackson đi vào wrapper `lines`, đọc các element `line` bên trong rồi tạo `List<OrderLine>`.

Tên wrapper và tên item phải khớp với cấu hình. Nếu XML nguồn dùng `<items>` và `<item>`, annotation cũng cần phản ánh đúng hai tên đó.

## 6. Đọc XML unwrapped collection

Với cấu hình `useWrapping = false`, các item xuất hiện trực tiếp dưới parent:

```xml
<order>
  <id>ORD-100</id>
  <line>
    <sku>BOOK-01</sku>
    <quantity>2</quantity>
  </line>
  <line>
    <sku>PEN-02</sku>
    <quantity>5</quantity>
  </line>
</order>
```

Deserialize bằng cùng DTO unwrapped:

```java
Order order = mapper.readValue(xml, Order.class);

for (OrderLine line : order.getLines()) {
    System.out.println(line.getSku());
}
```

Jackson gom các element `line` lặp lại thành một collection. Không cần tự duyệt XML bằng DOM hoặc StAX cho trường hợp mapping bean thông thường.

Nếu bỏ `useWrapping = false` trong DTO nhưng XML không có wrapper, cấu trúc XML và mapping metadata không còn khớp. Hãy cấu hình rõ ràng và test với payload thật của đối tác.

## 7. Cấu hình wrapper mặc định trên JacksonXmlModule

Ngoài annotation ở từng property, Jackson XML cho phép đặt mặc định wrapper cho collection qua `JacksonXmlModule`:

```java
JacksonXmlModule xmlModule = new JacksonXmlModule();
xmlModule.setDefaultUseWrapper(false);

XmlMapper mapper = new XmlMapper(xmlModule);
```

Với cấu hình này, các collection không có annotation chỉ định riêng sẽ dùng mặc định không wrapper.

Nếu muốn giữ wrapper mặc định, có thể không gọi `setDefaultUseWrapper(false)` hoặc đặt `true` một cách tường minh:

```java
JacksonXmlModule xmlModule = new JacksonXmlModule();
xmlModule.setDefaultUseWrapper(true);

XmlMapper mapper = new XmlMapper(xmlModule);
```

### 7.1. Khi nào nên đổi default toàn mapper?

Global default hữu ích khi một XML schema dùng cùng quy ước cho hầu hết collection. Ví dụ, một hệ thống cũ luôn biểu diễn list bằng các sibling elements không có wrapper.

Tuy nhiên, một DTO có thể chứa nhiều collection với schema khác nhau. Khi đó, annotation ở property giúp thể hiện ngoại lệ rõ ràng:

```java
public class Catalog {
    @JacksonXmlElementWrapper(useWrapping = true, localName = "products")
    @JacksonXmlProperty(localName = "product")
    private List<Product> products;

    @JacksonXmlElementWrapper(useWrapping = false)
    @JacksonXmlProperty(localName = "category")
    private List<Category> categories;
}
```

Một mapper có thể xử lý cả wrapped và unwrapped collection. Không cần tạo mapper riêng chỉ vì một DTO có hai kiểu collection.

### 7.2. Cấu hình mapper trước khi sử dụng

Hãy cấu hình `JacksonXmlModule`, đăng ký module và tạo `XmlMapper` ở giai đoạn khởi tạo. Mapper nên được tái sử dụng sau khi đã cấu hình. Không thay đổi global wrapper policy theo từng request trên một mapper đang được chia sẻ.

Nếu các endpoint có contract XML khác nhau đáng kể, có thể tạo mapper riêng cho từng contract, mỗi mapper được cấu hình một lần và inject vào nơi sử dụng.

## 8. Phân biệt wrapper name và item name

Đây là điểm dễ nhầm khi dùng `@JacksonXmlElementWrapper` cùng `@JacksonXmlProperty`.

```java
@JacksonXmlElementWrapper(localName = "entries")
@JacksonXmlProperty(localName = "entry")
private List<Entry> values;
```

Ánh xạ:

```xml
<entries>
  <entry>...</entry>
  <entry>...</entry>
</entries>
```

- `entries` là wrapper element.
- `entry` là tên của từng item.
- `values` là tên property Java.

Ba tên này có thể khác nhau. Điều quan trọng là XML contract xác định đúng tên và mapper được cấu hình tương ứng.

### 8.1. Chỉ đổi tên wrapper

```java
@JacksonXmlElementWrapper(localName = "records")
private List<Record> records;
```

Wrapper có tên `records`. Tên element item theo mặc định của property/type introspection; nếu schema yêu cầu tên cụ thể, khai báo thêm `@JacksonXmlProperty(localName = "record")`.

### 8.2. Chỉ đổi tên item trong collection không wrapper

```java
@JacksonXmlElementWrapper(useWrapping = false)
@JacksonXmlProperty(localName = "record")
private List<Record> records;
```

Không có wrapper. Mỗi item là một element `record` trực tiếp dưới parent.

### 8.3. Tránh trùng tên wrapper và item nếu schema không yêu cầu

XML cho phép cùng tên element ở cấp lồng nhau:

```xml
<items>
  <items>first</items>
  <items>second</items>
</items>
```

Jackson có thể ánh xạ dạng này nếu metadata phù hợp, nhưng người đọc khó phân biệt container và item. Nếu có thể định nghĩa contract, dùng tên rõ như `items` và `item`.

## 9. Collection của scalar value

`@JacksonXmlElementWrapper` không chỉ dùng cho list POJO. Nó cũng áp dụng cho list các scalar như String, Integer hoặc enum.

Wrapped list:

```java
public class SearchResult {
    @JacksonXmlElementWrapper(localName = "tags")
    @JacksonXmlProperty(localName = "tag")
    private List<String> tags;
}
```

XML:

```xml
<searchResult>
  <tags>
    <tag>java</tag>
    <tag>jackson</tag>
  </tags>
</searchResult>
```

Unwrapped list:

```java
public class SearchResult {
    @JacksonXmlElementWrapper(useWrapping = false)
    @JacksonXmlProperty(localName = "tag")
    private List<String> tags;
}
```

XML:

```xml
<searchResult>
  <tag>java</tag>
  <tag>jackson</tag>
</searchResult>
```

Mỗi element `tag` chứa text node thay vì object con. Jackson vẫn gom các giá trị thành `List<String>`.

## 10. Collection lồng nhau và kiểu generic

Một collection có thể chứa POJO mà bên trong POJO lại có collection khác:

```java
public class Department {
    private String name;

    @JacksonXmlElementWrapper(localName = "employees")
    @JacksonXmlProperty(localName = "employee")
    private List<Employee> employees;
}

public class Company {
    @JacksonXmlElementWrapper(localName = "departments")
    @JacksonXmlProperty(localName = "department")
    private List<Department> departments;
}
```

XML:

```xml
<company>
  <departments>
    <department>
      <name>Engineering</name>
      <employees>
        <employee>
          <name>An</name>
        </employee>
        <employee>
          <name>Binh</name>
        </employee>
      </employees>
    </department>
  </departments>
</company>
```

Mỗi collection được cấu hình độc lập tại property của nó. Wrapper ngoài không tự quyết định wrapper bên trong.

Nếu cần collection lồng nhau nhiều cấp, hãy khai báo rõ từng wrapper và item name. Đừng chỉ dựa vào tên mặc định vì các cấp có thể tạo ra những element khó phân biệt.

## 11. Collection trong namespace XML

Một XML contract có thể sử dụng namespace cho wrapper hoặc item. `@JacksonXmlElementWrapper` và `@JacksonXmlProperty` đều hỗ trợ namespace:

```java
public class Order {
    @JacksonXmlElementWrapper(
        localName = "lines",
        namespace = "urn:example:orders"
    )
    @JacksonXmlProperty(
        localName = "line",
        namespace = "urn:example:orders"
    )
    private List<OrderLine> lines;
}
```

Namespace URI là định danh namespace; prefix hiển thị trong XML do writer quyết định và không nên được xem là một phần của identity. Hai prefix khác nhau vẫn có thể đại diện cùng namespace URI.

Nếu wrapper và item thuộc namespace khác nhau, khai báo namespace riêng cho từng annotation theo XSD. Khi deserialize, Jackson cần nhận đúng namespace URI, không chỉ đúng local name.

### 11.1. Root element và namespace

Có thể đặt root element:

```java
@JacksonXmlRootElement(
    localName = "order",
    namespace = "urn:example:orders"
)
public class Order {
    // Properties
}
```

Root element, wrapper và item là ba cấp độc lập. Nếu XML contract có namespace, hãy kiểm tra cả ba cấp thay vì chỉ đặt namespace trên class root.

## 12. Attribute bên cạnh collection

XML cho phép attribute trên element bao hoặc element cha. `@JacksonXmlProperty(isAttribute = true)` dùng để ánh xạ property thành attribute.

Ví dụ:

```java
@JacksonXmlRootElement(localName = "order")
public class Order {
    @JacksonXmlProperty(isAttribute = true, localName = "id")
    private String id;

    @JacksonXmlElementWrapper(localName = "lines")
    @JacksonXmlProperty(localName = "line")
    private List<OrderLine> lines;
}
```

XML:

```xml
<order id="ORD-100">
  <lines>
    <line>...</line>
  </lines>
</order>
```

Collection wrapper vẫn là element; attribute `id` thuộc root `order`. Không nhầm `@JacksonXmlElementWrapper` với annotation điều khiển attribute.

Nếu XML schema dùng attribute trên wrapper element thay vì parent, cần model hóa wrapper như một kiểu Java riêng để biểu diễn cả attribute lẫn danh sách item. `@JacksonXmlElementWrapper` chủ yếu điều khiển container element và không phải một DTO wrapper đầy đủ có thể mang metadata tùy ý.

## 13. Collection rỗng, null và property bị thiếu

Một trong những khác biệt quan trọng nhất giữa wrapped và unwrapped collection là khả năng biểu diễn collection không có phần tử.

### 13.1. Wrapped collection rỗng

Một wrapper có thể xuất hiện dù không có item:

```xml
<order>
  <lines/>
</order>
```

hoặc:

```xml
<order>
  <lines></lines>
</order>
```

Wrapper rỗng cung cấp một dấu hiệu cấu trúc cho biết property `lines` có mặt nhưng không chứa item. Khi deserialize, Jackson thường có thể ánh xạ nó thành collection rỗng; kết quả cụ thể còn phụ thuộc kiểu property, giá trị khởi tạo và cấu hình mapper.

### 13.2. Unwrapped collection rỗng

Với unwrapped collection, khi không có item thì XML chỉ còn:

```xml
<order>
  <id>ORD-100</id>
</order>
```

Không có element `line`. Điều này có thể giống với property bị thiếu trong XML. Vì không có wrapper riêng, định dạng không cung cấp một dấu hiệu rõ ràng để phân biệt “collection rỗng” với “property không được gửi”.

Nếu hợp đồng cần phân biệt hai trạng thái, wrapper thường phù hợp hơn hoặc cần một field/attribute trạng thái riêng.

### 13.3. Null khác collection rỗng

Trong Java:

- `lines == null`: chưa có giá trị collection hoặc biểu diễn null.
- `lines.isEmpty()`: collection tồn tại nhưng không có phần tử.
- `lines` có item: collection chứa dữ liệu.

XML không phải lúc nào cũng biểu diễn rõ ba trạng thái này theo cùng một cách. Kết quả serialize của null, empty và absent chịu ảnh hưởng bởi null serializer, `@JsonInclude`, giá trị khởi tạo và cấu hình Jackson XML.

Nếu cần semantics rõ ràng, hãy định nghĩa contract và test riêng:

| Trạng thái Java | Câu hỏi cần xác nhận trong XML contract |
|---|---|
| `null` | Bỏ wrapper, ghi element rỗng hay dùng `xsi:nil`? |
| List rỗng | Ghi wrapper rỗng hay không ghi element nào? |
| List có một item | Ghi đúng một item dưới wrapper hay một sibling element? |
| List có nhiều item | Tên và vị trí của từng item là gì? |
| Property không có trong XML | Giữ initializer, nhận null hay dùng default? |

Không suy ra semantics của null chỉ từ việc dùng `useWrapping = false`. Hãy viết round-trip test cho mapper thực tế.

### 13.4. Khởi tạo collection trong DTO

Nếu muốn property luôn có collection rỗng khi XML không cung cấp item, có thể khởi tạo:

```java
public class Order {
    @JacksonXmlElementWrapper(useWrapping = false)
    @JacksonXmlProperty(localName = "line")
    private List<OrderLine> lines = new ArrayList<>();

    public List<OrderLine> getLines() {
        return lines;
    }

    public void setLines(List<OrderLine> lines) {
        this.lines = lines;
    }
}
```

Tuy nhiên, setter có thể được gọi với null tùy input/configuration. Nếu invariant yêu cầu list không bao giờ null, hãy bảo đảm điều đó ở setter, constructor hoặc factory, đồng thời xác định semantics của `null` đầu vào.

## 14. Một item hay nhiều item

Collection XML thường có thể chứa 0, 1 hoặc nhiều item. Khi có một item:

Wrapped:

```xml
<lines>
  <line>
    <sku>BOOK-01</sku>
  </line>
</lines>
```

Unwrapped:

```xml
<line>
  <sku>BOOK-01</sku>
</line>
```

Jackson vẫn có thể ánh xạ một item thành list một phần tử khi property được khai báo là `List<OrderLine>`. Không cần đổi kiểu Java thành `OrderLine` chỉ vì một payload cụ thể chỉ có một element.

Điểm cần lưu ý là XML contract có thể cho phép một hoặc nhiều element cùng tên (`minOccurs`/`maxOccurs` trong XSD). DTO nên dùng collection nếu contract thực sự cho phép lặp. Nếu schema chỉ cho phép đúng một element, dùng property scalar sẽ thể hiện đúng hơn.

Không nên bật cơ chế chấp nhận scalar thành collection chỉ để che giấu XML không đúng schema. Hãy phân biệt một item hợp lệ trong collection với một property scalar có cấu trúc khác.

## 15. Tên item trong collection và root element

Tên root của POJO có thể được khai báo bằng `@JacksonXmlRootElement`:

```java
@JacksonXmlRootElement(localName = "order")
public class Order {
    // Collection properties
}
```

Tên root khác với tên wrapper và tên item. Ví dụ:

```java
@JacksonXmlRootElement(localName = "order")
public class Order {
    @JacksonXmlElementWrapper(localName = "items")
    @JacksonXmlProperty(localName = "item")
    private List<OrderLine> lines;
}
```

XML:

```xml
<order>
  <items>
    <item>...</item>
  </items>
</order>
```

Nếu cần XML root là `<orders>` chứa nhiều `<order>`, có thể dùng một wrapper DTO:

```java
@JacksonXmlRootElement(localName = "orders")
public class OrdersDocument {
    @JacksonXmlElementWrapper(useWrapping = false)
    @JacksonXmlProperty(localName = "order")
    private List<Order> orders;
}
```

Wrapper DTO làm rõ root document và collection item, đồng thời giúp gắn metadata hoặc version attribute ở cấp document khi cần.

## 16. Tương thích với XSD và XML từ hệ thống bên ngoài

Khi XML được định nghĩa bởi XSD, hãy đọc phần khai báo element tương ứng để biết collection có wrapper hay không.

Ví dụ schema có wrapper:

```xml
<xs:element name="lines">
  <xs:complexType>
    <xs:sequence>
      <xs:element name="line" type="LineType" minOccurs="0" maxOccurs="unbounded"/>
    </xs:sequence>
  </xs:complexType>
</xs:element>
```

Ánh xạ tương ứng:

```java
@JacksonXmlElementWrapper(localName = "lines")
@JacksonXmlProperty(localName = "line")
private List<OrderLine> lines;
```

Nếu schema khai báo item lặp trực tiếp dưới parent mà không có element `lines` bao quanh, dùng:

```java
@JacksonXmlElementWrapper(useWrapping = false)
@JacksonXmlProperty(localName = "line")
private List<OrderLine> lines;
```

### 16.1. Jackson mapping không tự thay thế XSD validation

`XmlMapper` có thể bind XML vào DTO nhưng không tự xác nhận mọi constraint của XSD như cardinality, restriction, pattern, choice hoặc identity constraint. Nếu contract yêu cầu validation XSD, cần tích hợp XML validation riêng (ví dụ `SchemaFactory`/`Validator` của JAXP) trước hoặc trong pipeline đọc XML.

Một XML có thể deserialize được vào DTO nhưng vẫn vi phạm XSD. Ví dụ schema yêu cầu `line` ít nhất một lần nhưng DTO có thể nhận list rỗng nếu mapper không validate schema.

### 16.2. Kiểm tra namespace cùng local name

XSD có thể định nghĩa namespace mặc định hoặc namespace riêng cho từng element. Hai element cùng local name nhưng khác namespace URI là hai tên XML khác nhau. Hãy khai báo namespace đúng trên wrapper và item, sau đó test bằng payload thật.

## 17. Kết hợp annotation trên collection với property khác

Một DTO có thể trộn scalar, attribute, wrapped list và unwrapped list:

```java
@JacksonXmlRootElement(localName = "catalog")
public class Catalog {
    @JacksonXmlProperty(isAttribute = true, localName = "version")
    private String version;

    @JacksonXmlElementWrapper(localName = "products")
    @JacksonXmlProperty(localName = "product")
    private List<Product> products;

    @JacksonXmlElementWrapper(useWrapping = false)
    @JacksonXmlProperty(localName = "category")
    private List<Category> categories;

    private String generatedAt;
}
```

XML có thể có dạng:

```xml
<catalog version="2">
  <products>
    <product>...</product>
    <product>...</product>
  </products>
  <category>...</category>
  <category>...</category>
  <generatedAt>2026-11-12T10:00:00Z</generatedAt>
</catalog>
```

Mỗi property được ánh xạ độc lập theo annotation. Thứ tự element đầu ra có thể chịu ảnh hưởng thứ tự property và cấu hình mapper; nếu thứ tự là yêu cầu của schema/consumer, hãy khai báo thứ tự tường minh và kiểm tra output.

## 18. Kiểm thử serialize và deserialize

Vì wrapped và unwrapped tạo XML khác nhau, nên test cả output và round-trip.

### 18.1. Test wrapped collection

```java
class WrappedOrderXmlTest {
    private final XmlMapper mapper = new XmlMapper();

    @Test
    void writesItemsInsideWrapper() throws Exception {
        Order order = new Order();
        order.setId("ORD-100");
        order.setLines(List.of(
            new OrderLine("BOOK-01", 2),
            new OrderLine("PEN-02", 5)
        ));

        String xml = mapper.writeValueAsString(order);

        assertTrue(xml.contains("<lines>"));
        assertTrue(xml.contains("<line>"));
    }

    @Test
    void readsItemsFromWrapper() throws Exception {
        String xml = """
            <order>
              <id>ORD-100</id>
              <lines>
                <line><sku>BOOK-01</sku><quantity>2</quantity></line>
                <line><sku>PEN-02</sku><quantity>5</quantity></line>
              </lines>
            </order>
            """;

        Order order = mapper.readValue(xml, Order.class);

        assertEquals(2, order.getLines().size());
        assertEquals("PEN-02", order.getLines().get(1).getSku());
    }
}
```

Test dùng DTO được annotation theo wrapped format. Nếu test XML exact string, cân nhắc whitespace/indentation và XML declaration; so sánh cấu trúc XML thường bền hơn so sánh chuỗi thô.

### 18.2. Test unwrapped collection

```java
class UnwrappedOrderXmlTest {
    private final XmlMapper mapper = new XmlMapper();

    @Test
    void writesRepeatedSiblingElementsWithoutWrapper() throws Exception {
        UnwrappedOrder order = new UnwrappedOrder();
        order.setId("ORD-100");
        order.setLines(List.of(
            new OrderLine("BOOK-01", 2),
            new OrderLine("PEN-02", 5)
        ));

        String xml = mapper.writeValueAsString(order);

        assertFalse(xml.contains("<lines>"));
        assertEquals(2, countOccurrences(xml, "<line>"));
    }

    @Test
    void readsRepeatedSiblingElementsIntoList() throws Exception {
        String xml = """
            <order>
              <id>ORD-100</id>
              <line><sku>BOOK-01</sku><quantity>2</quantity></line>
              <line><sku>PEN-02</sku><quantity>5</quantity></line>
            </order>
            """;

        UnwrappedOrder order = mapper.readValue(xml, UnwrappedOrder.class);

        assertEquals(2, order.getLines().size());
        assertEquals("BOOK-01", order.getLines().get(0).getSku());
    }
}
```

Trong test, `UnwrappedOrder` là DTO riêng có `@JacksonXmlElementWrapper(useWrapping = false)` trên `lines`. Không dùng cùng một DTO cho hai schema khác nhau trừ khi mapper/configuration được thiết kế rõ để hỗ trợ cả hai.

### 18.3. Test empty, null và missing

Hãy có test riêng cho:

- Wrapped `<lines/>`.
- XML không có `lines`.
- Unwrapped XML không có `line`.
- Java list rỗng khi serialize.
- Java list null khi serialize.
- Một item và nhiều item.

Các trường hợp này dễ khác nhau theo giá trị khởi tạo, setter, `@JsonInclude` và version Jackson XML. Test cần xác nhận semantics mà ứng dụng muốn giữ, không chỉ kiểm tra số item khi list có dữ liệu.

## 19. Những lỗi thường gặp

**Quên `useWrapping = false` khi XML chứa sibling elements.** Mapper mặc định có thể mong wrapper. Khai báo unwrapped collection rõ ràng.

**Nhầm tên wrapper với tên item.** `@JacksonXmlElementWrapper` điều khiển container; `@JacksonXmlProperty` điều khiển property/item element. Khai báo cả hai khi tên XML phải chính xác.

**Chỉ đổi localName của wrapper và mong item cũng đổi theo.** Tên item cần được xác định riêng nếu schema yêu cầu.

**Dùng `useWrapping = false` cho collection nhưng quên item name.** Tên item có thể theo property name mặc định. Dùng `@JacksonXmlProperty(localName = "...")` để rõ ràng.

**Áp dụng wrapper annotation lên scalar property.** Annotation dành cho collection-like property; scalar element không cần collection wrapper.

**Dùng một DTO cho hai XML contract khác cấu trúc.** Wrapped và unwrapped không tương đương. Dùng DTO riêng, mix-in hoặc cấu hình riêng nếu phải hỗ trợ cả hai format.

**Giả định empty, null và absent giống nhau.** Đặc biệt với unwrapped collection, không có item không tạo wrapper rỗng. Xác định contract và test từng trạng thái.

**Không khai báo namespace cho wrapper/item.** Local name đúng nhưng namespace URI sai vẫn có thể làm XML không khớp schema.

**Cho rằng XmlMapper tự validate XSD.** Data binding và schema validation là hai bước riêng. Dùng JAXP hoặc validator phù hợp nếu contract yêu cầu XSD.

**Đặt global default wrapper mà không kiểm tra ngoại lệ.** Một mapper có thể có cả collection wrapped và unwrapped. Dùng annotation trên từng property cho ngoại lệ.

**Không kiểm tra XML thực tế từ đối tác.** XML có namespace, attribute, wrapper và item name cụ thể. Dùng fixture thật hoặc XSD để kiểm tra mapping.

## 20. Quy trình ánh xạ collection

1. Xác định XML contract có element bao riêng cho collection hay các item lặp trực tiếp dưới parent.
2. Đọc XSD hoặc payload mẫu để xác nhận wrapper name, item name, namespace và cardinality.
3. Tạo property Java bằng `List<T>`, `Set<T>` hoặc array theo nhu cầu domain.
4. Nếu có wrapper, dùng `@JacksonXmlElementWrapper(localName = "...")`.
5. Nếu không có wrapper, dùng `@JacksonXmlElementWrapper(useWrapping = false)`.
6. Dùng `@JacksonXmlProperty(localName = "...")` để đặt tên item.
7. Khai báo namespace riêng cho wrapper/item khi schema yêu cầu.
8. Chỉ thay global default của `JacksonXmlModule` nếu quy ước áp dụng cho phần lớn collection.
9. Xác định semantics cho null, empty, missing, một item và nhiều item.
10. Serialize và deserialize bằng `XmlMapper` đã cấu hình thực tế.
11. Validate XSD riêng nếu hợp đồng yêu cầu kiểm tra schema đầy đủ.
12. Dùng fixture XML đại diện để bảo đảm tương thích với hệ thống tích hợp.

## Kết luận

Jackson XML ánh xạ collection theo hai dạng: wrapped collection có một element bao chứa các item, và unwrapped collection có các item lặp trực tiếp dưới element cha. `@JacksonXmlElementWrapper(localName = "...")` xác định wrapper; `@JacksonXmlElementWrapper(useWrapping = false)` loại bỏ wrapper; `@JacksonXmlProperty(localName = "...")` xác định tên từng item. Có thể đặt mặc định cho toàn mapper bằng `JacksonXmlModule.setDefaultUseWrapper()`, nhưng annotation trên property phù hợp khi một DTO có nhiều contract collection khác nhau. Hãy xác nhận root, wrapper, item, namespace và cardinality theo XSD/payload thực tế, đồng thời kiểm thử riêng collection rỗng, null, absent, một item và nhiều item.
