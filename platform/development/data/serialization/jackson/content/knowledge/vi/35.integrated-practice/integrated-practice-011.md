# Đọc ghi CSV và XML bằng module tương ứng với hợp đồng tường minh

Jackson có thể làm việc với nhiều định dạng dữ liệu ngoài JSON. Khi ứng dụng cần trao đổi bảng dữ liệu, module CSV cung cấp CsvMapper và CsvSchema; khi cần tài liệu có cấu trúc phần tử, thuộc tính và namespace, module XML cung cấp XmlMapper cùng các annotation chuyên biệt. Cả hai module đều tận dụng Jackson Databind để ánh xạ dữ liệu sang Java object, nhưng mô hình dữ liệu của CSV và XML khác nhau đáng kể.

CSV thường biểu diễn một bảng phẳng gồm header và các dòng. Nó không có chuẩn thống nhất cho kiểu dữ liệu, null, nested object hay schema. Vì vậy, hợp đồng CSV phải quy định rõ tên cột, thứ tự, delimiter, quote, encoding, format của từng giá trị và cách xử lý dữ liệu thiếu.

XML biểu diễn cây phần tử, attribute, text, namespace và có thể có nội dung hỗn hợp. XmlMapper hỗ trợ ánh xạ phần lớn cấu trúc XML thông dụng sang POJO, nhưng XML không hoàn toàn tương đương với JSON object. Hợp đồng XML cần quy định root element, namespace URI, attribute/element, wrapper của collection, thứ tự phần tử khi XSD yêu cầu và quy tắc null.

Nguyên tắc xuyên suốt là: **định nghĩa hợp đồng trước, cấu hình mapper theo hợp đồng đó, rồi kiểm thử độc lập cả chiều đọc và chiều ghi**. Không nên để producer và consumer cùng dựa vào một schema suy luận ngầm rồi coi round-trip thành công là bằng chứng tương thích.

## 1. Hai module và vai trò của chúng

| Module | Artifact | Mapper chính | Mô hình dữ liệu |
|---|---|---|---|
| CSV | jackson-dataformat-csv | CsvMapper | Bảng gồm cột và dòng |
| XML | jackson-dataformat-xml | XmlMapper | Cây element, attribute và text |

Dependency Maven khi dùng Jackson BOM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson</groupId>
            <artifactId>jackson-bom</artifactId>
            <version>...</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.dataformat</groupId>
        <artifactId>jackson-dataformat-csv</artifactId>
    </dependency>
    <dependency>
        <groupId>com.fasterxml.jackson.dataformat</groupId>
        <artifactId>jackson-dataformat-xml</artifactId>
    </dependency>
</dependencies>
~~~

Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("com.fasterxml.jackson.dataformat:jackson-dataformat-csv")
    implementation("com.fasterxml.jackson.dataformat:jackson-dataformat-xml")
}
~~~

Dùng BOM hoặc dependency constraints để đồng bộ CSV/XML module với Jackson core, annotations và databind thuộc cùng release line. Không tự nâng riêng một dataformat module nếu chưa kiểm tra compatibility.

Module XML còn dựa vào StAX API và implementation để parse/generate XML. Tùy runtime và dependency set, ứng dụng có thể dùng StAX của JDK hoặc một implementation như Woodstox. Hãy kiểm tra dependency tree và cấu hình production, đặc biệt khi cần các tính năng parser hoặc giới hạn bảo mật cụ thể.

## 2. Hợp đồng dữ liệu là gì?

Hợp đồng dữ liệu là thỏa thuận giữa bên tạo và bên nhận về cách biểu diễn và diễn giải dữ liệu. Với CSV và XML, hợp đồng cần chi tiết hơn tên Java class.

Một hợp đồng nên ghi rõ:

- Định dạng và phiên bản hợp đồng.
- Encoding, thường là UTF-8.
- Cấu trúc tài liệu hoặc record.
- Tên field/cột chính xác.
- Kiểu dữ liệu và cách biểu diễn trên wire.
- Field bắt buộc, optional, nullable và default.
- Cách xử lý field/cột không biết.
- Quy tắc date/time, timezone, decimal và boolean.
- Quy tắc escaping, quoting và whitespace.
- Cách báo lỗi khi dữ liệu sai.
- Chính sách tương thích khi thêm, bỏ hoặc đổi field.

CSV không có schema tự mô tả bắt buộc. XML có thể đi kèm XSD, nhưng chỉ có XSD chưa đủ nếu ứng dụng còn có quy tắc nghiệp vụ như currency, quyền truy cập hoặc miền giá trị.

## 3. Khi nào chọn CSV, khi nào chọn XML?

| Nhu cầu | CSV | XML |
|---|---|---|
| Xuất dữ liệu dạng bảng | Rất phù hợp | Có thể làm nhưng dài hơn |
| Trao đổi với spreadsheet | Phổ biến | Ít thuận tiện hơn |
| Dữ liệu có object lồng nhau | Cần flatten hoặc quy ước riêng | Biểu diễn tự nhiên hơn |
| Attribute và namespace | Không có khái niệm tương ứng | Hỗ trợ |
| Schema chuẩn hóa | Cần hợp đồng riêng | Có thể dùng XSD |
| Comment và mixed content | Không có cấu trúc tương đương | XML hỗ trợ, nhưng XmlMapper không phải editor round-trip |
| Dữ liệu record lớn | Có thể đọc từng dòng/record | Có thể xử lý bằng StAX/token streaming |
| Tương thích hệ thống cũ | Thường gặp trong export/import bảng | Thường gặp trong enterprise integration |

Chọn định dạng theo giao thức và consumer thực tế. Đừng chuyển một API JSON sang CSV chỉ vì CSV có vẻ nhẹ hơn nếu payload có cấu trúc lồng nhau, polymorphism hoặc metadata phức tạp.

## 4. Đọc và ghi CSV với CsvMapper

CsvMapper là mapper chuyên cho CSV, cung cấp databind API tương tự ObjectMapper. CsvSchema mô tả các cột, header và một số quy tắc format.

~~~java
import com.fasterxml.jackson.dataformat.csv.CsvMapper;
import com.fasterxml.jackson.dataformat.csv.CsvSchema;

CsvMapper csvMapper = new CsvMapper();
~~~

Ví dụ một DTO phẳng:

~~~java
public record OrderCsvRow(
    @JsonProperty("order_id") String orderId,
    @JsonProperty("customer_name") String customerName,
    @JsonProperty("total") BigDecimal total,
    @JsonProperty("currency") String currency
) {}
~~~

CSV contract:

~~~csv
order_id,customer_name,total,currency
ORD-100,An Nguyen,125.50,VND
ORD-101,Binh Tran,90.00,VND
~~~

Schema tường minh:

~~~java
CsvSchema schema = CsvSchema.builder()
    .addColumn("order_id")
    .addColumn("customer_name")
    .addColumn("total")
    .addColumn("currency")
    .build()
    .withHeader();
~~~

Đọc một record:

~~~java
OrderCsvRow row = csvMapper
    .readerFor(OrderCsvRow.class)
    .with(schema)
    .readValue(input);
~~~

Ghi một record:

~~~java
csvMapper.writer(schema).writeValue(output, row);
~~~

Schema định nghĩa cột và thứ tự rõ ràng. Annotation JsonProperty giúp property Java ánh xạ vào tên cột trong hợp đồng.

## 5. Header CSV và schema động

Khi file CSV có header do nguồn bên ngoài cung cấp, có thể dùng schema rỗng với header để CsvMapper đọc tên cột từ dòng đầu:

~~~java
CsvSchema readSchema = CsvSchema.emptySchema().withHeader();

MappingIterator<OrderCsvRow> rows = csvMapper
    .readerFor(OrderCsvRow.class)
    .with(readSchema)
    .readValues(input);
~~~

Đọc từng dòng:

~~~java
try (MappingIterator<OrderCsvRow> rows = csvMapper
        .readerFor(OrderCsvRow.class)
        .with(readSchema)
        .readValues(input)) {

    while (rows.hasNextValue()) {
        OrderCsvRow row = rows.nextValue();
        process(row);
    }
}
~~~

Cách này hữu ích khi thứ tự cột thay đổi nhưng header vẫn có tên ổn định. Tuy nhiên, không có nghĩa mọi header đều được chấp nhận. Consumer vẫn cần kiểm tra:

- Header bắt buộc có mặt.
- Không có header trùng.
- Không có cột ngoài hợp đồng nếu policy strict.
- Tên cột đúng chính tả và đúng case theo contract.
- Cột không được hoán đổi ý nghĩa chỉ vì vị trí khác nhau.

Nếu header không đáng tin, hãy xác thực header trước khi xử lý dòng dữ liệu. Có thể dùng schema tường minh với strict policy theo khả năng phiên bản module hoặc kiểm tra header bằng bước riêng.

## 6. Vì sao không nên chỉ suy luận schema từ DTO?

CsvMapper có thể suy ra schema từ class:

~~~java
CsvSchema schema = csvMapper
    .schemaFor(OrderCsvRow.class)
    .withHeader();
~~~

Cách này tiện cho export nội bộ hoặc trường hợp DTO chính là hợp đồng CSV. Nhưng schema suy luận có thể bị ảnh hưởng bởi:

- Thứ tự property do introspection hoặc annotation.
- Naming strategy.
- Thay đổi field/record component.
- Getter mới được thêm.
- Annotation mix-in.
- Phiên bản Jackson hoặc module.

Với giao thức bên ngoài, nên định nghĩa CsvSchema rõ ràng và kiểm tra JSON/CSV fixture cố định. Nếu dùng schemaFor(), vẫn cần test header và thứ tự cột đã công bố.

## 7. Tùy chỉnh delimiter, quote và line ending

CSV không chỉ có một kiểu phân tách. Một số hệ thống dùng dấu phẩy, hệ thống khác dùng dấu chấm phẩy hoặc tab. Contract phải ghi rõ.

Ví dụ schema:

~~~java
CsvSchema schema = CsvSchema.builder()
    .addColumn("order_id")
    .addColumn("customer_name")
    .addColumn("total")
    .addColumn("currency")
    .build()
    .withHeader()
    .withColumnSeparator(';')
    .withQuoteChar('"')
    .withLineSeparator("\r\n");
~~~

Kết quả có thể có dạng:

~~~csv
order_id;customer_name;total;currency
ORD-100;"An Nguyen";125.50;VND
ORD-101;"Binh Tran";90.00;VND
~~~

Các method cấu hình schema có thể khác theo version module. Hãy dùng API của Jackson CSV release line trong dự án và bảo vệ bằng fixture thực tế.

Quy tắc cần thống nhất:

- Column separator.
- Quote character.
- Escape character.
- Line ending LF hay CRLF.
- Có header hay không.
- Khoảng trắng có được giữ hay trim.
- Quy tắc quote field chứa delimiter, quote hoặc newline.
- BOM có được phép ở đầu file hay không.

Không tự tách dòng CSV bằng String.split(","). Một field có thể chứa dấu phẩy, dấu quote hoặc newline nếu được quote/escape đúng.

## 8. CSV là bảng phẳng: xử lý object lồng nhau

CSV không có object hoặc array lồng nhau như JSON. Nếu DTO có cấu trúc:

~~~java
public record Address(String city, String street) {}

public record Customer(
    String id,
    String name,
    Address address
) {}
~~~

không nên mặc định rằng CsvMapper sẽ tạo ra một representation portable cho address. Các consumer CSV thường mong một bảng phẳng.

Có thể thiết kế row DTO riêng:

~~~java
public record CustomerCsvRow(
    String customerId,
    String customerName,
    String addressStreet,
    String addressCity
) {}
~~~

Mapping từ domain model sang row model:

~~~java
CustomerCsvRow toCsvRow(Customer customer) {
    return new CustomerCsvRow(
        customer.id(),
        customer.name(),
        customer.address().street(),
        customer.address().city()
    );
}
~~~

Mapping ngược lại cũng cần explicit:

~~~java
Customer fromCsvRow(CustomerCsvRow row) {
    Address address = new Address(
        row.addressCity(),
        row.addressStreet()
    );

    return new Customer(
        row.customerId(),
        row.customerName(),
        address
    );
}
~~~

Row DTO là adapter cho hợp đồng CSV. Nó giúp domain model thay đổi mà không vô tình thay đổi tên cột hoặc cấu trúc file trao đổi.

Nếu cần biểu diễn danh sách con, hãy quyết định một trong các cách: một dòng cho mỗi child với khóa cha lặp lại, nhiều file CSV liên kết bằng ID, hoặc một cột chứa format con được quy định riêng. Không tự nhét JSON vào một cột mà không ghi rõ encoding và schema của cột đó.

## 9. Quy tắc giá trị trong CSV

CSV thường lưu giá trị dưới dạng text. Kiểu Java đích quyết định cách Jackson parse một giá trị, nhưng contract phải định nghĩa semantics.

| Kiểu nghiệp vụ | Ví dụ wire value | Quy tắc cần chốt |
|---|---|---|
| Identifier | 000123 | Giữ dạng String, không bỏ số 0 đầu |
| Integer | 42 | Miền giá trị và overflow |
| Decimal | 125.50 | Decimal separator, scale và rounding |
| Boolean | true | Có chấp nhận TRUE, yes/no, 1/0 không |
| Date | 2026-11-12 | Pattern và timezone nếu có |
| Timestamp | 2026-11-12T08:30:00Z | ISO format, UTC hay offset |
| Enum | PAID | Wire code và unknown value |
| Null | Quy ước riêng | Phân biệt null với empty string |
| Empty | Chuỗi rỗng | Có nghĩa là xóa, chưa biết hay giá trị rỗng |

Không dùng locale mặc định của máy để parse decimal hoặc date. Một file có giá trị 1,234 có thể có nghĩa khác nhau tùy locale và delimiter. Contract nên quy định decimal point là dấu chấm hoặc một format cụ thể.

### 9.1. Null, missing và empty trong CSV

CSV không có chuẩn phổ quát phân biệt null và empty string. Một ô rỗng có thể được hiểu là:

- Giá trị string rỗng.
- Giá trị null.
- Field không được cung cấp.
- Giá trị mặc định theo import policy.

Nếu cần phân biệt null với empty string, có thể dùng sentinel được thống nhất, ví dụ \N hoặc một token dành riêng, rồi cấu hình CsvSchema null value nếu phiên bản module hỗ trợ. Sentinel phải được escape khi nó xuất hiện như dữ liệu thật.

Không tự suy diễn rằng ô trống luôn là null. Hãy có fixture cho ô rỗng, quoted empty, sentinel, cột thiếu và dòng thiếu giá trị.

### 9.2. Date/time và decimal

Nếu dữ liệu CSV có timestamp, dùng format cố định như ISO-8601 và timezone rõ ràng. Có thể dùng JavaTimeModule hoặc serializer/deserializer riêng tùy cách CsvMapper và phiên bản module xử lý type.

Với BigDecimal, xác định scale có phải một phần hợp đồng không. 125.50 và 125.5 có cùng giá trị số nhưng biểu diễn khác scale. Nếu scale quan trọng trong báo cáo hoặc tài chính, test đúng lexical representation được ghi ra.

## 10. Đọc nhiều dòng CSV theo từng record

Với file lớn, dùng MappingIterator thay vì đọc toàn bộ thành List:

~~~java
CsvSchema schema = CsvSchema.emptySchema().withHeader();

try (MappingIterator<OrderCsvRow> rows = csvMapper
        .readerFor(OrderCsvRow.class)
        .with(schema)
        .readValues(input)) {

    while (rows.hasNextValue()) {
        OrderCsvRow row = rows.nextValue();
        validate(row);
        importOne(row);
    }
}
~~~

MappingIterator đọc tuần tự từng record. Nhưng memory vẫn có thể tăng nếu importOne() lưu tất cả row vào một collection. Hãy xử lý theo batch, ghi database hoặc phát sự kiện từng phần.

Đối với dữ liệu lớn, cần giới hạn:

- Kích thước file.
- Số cột.
- Số dòng.
- Độ dài field.
- Kích thước batch.
- Thời gian xử lý.
- Số lỗi cho phép trước khi dừng.

Quyết định xử lý lỗi theo dòng: dừng toàn bộ file, bỏ qua dòng lỗi có báo cáo, hay lưu vào error file. Đây là một phần của import contract.

## 11. Ghi nhiều dòng CSV

Dùng SequenceWriter để ghi từng row:

~~~java
CsvSchema schema = CsvSchema.builder()
    .addColumn("order_id")
    .addColumn("customer_name")
    .addColumn("total")
    .addColumn("currency")
    .build()
    .withHeader();

ObjectWriter writer = csvMapper.writer(schema);

try (SequenceWriter rows = writer.writeValues(output)) {
    for (OrderCsvRow row : orderRows) {
        rows.write(row);
    }
}
~~~

Cách này không cần tạo một String CSV khổng lồ trước khi ghi. Nó phù hợp với export theo cursor hoặc batch.

Nếu dữ liệu nguồn là database cursor, bảo đảm cursor và output stream được đóng đúng lifecycle. Khi ghi lỗi giữa chừng, file có thể không hoàn chỉnh; nên ghi file tạm rồi đổi tên sau khi hoàn tất nếu cần tính nguyên tử.

## 12. Kiểm tra CSV header và schema evolution

CSV thường được consumer đọc bằng tên cột hoặc vị trí cột. Hai cách này có tác động khác nhau:

- Header-based: thứ tự có thể thay đổi nếu consumer map theo tên.
- Position-based: thứ tự cột là một phần bắt buộc của hợp đồng.

Khi thay đổi schema:

| Thay đổi | Rủi ro | Hướng xử lý |
|---|---|---|
| Thêm cột optional cuối | Consumer theo vị trí cũ có thể xử lý sai | Version hoặc quy tắc unknown column |
| Đổi tên cột | Consumer theo tên không tìm thấy field | Giữ alias/import adapter hoặc version mới |
| Đổi thứ tự cột | Consumer position-based bị lệch | Giữ thứ tự hoặc phát hành version mới |
| Bỏ cột | Consumer cũ thiếu dữ liệu | Deprecation và migration |
| Đổi format decimal/date | Parse sai hoặc mất precision | Contract version và fixture |
| Đổi null sentinel | Null bị hiểu thành empty/string | Version và test dữ liệu cũ |

Đừng thêm cột vào file production mà không biết consumer xử lý unknown header ra sao. Một số consumer bỏ qua, một số fail, một số đọc theo vị trí và gán nhầm dữ liệu.

## 13. XML với XmlMapper

Module XML cung cấp XmlMapper, là mapper mở rộng từ Jackson Databind để đọc/ghi XML:

~~~java
import com.fasterxml.jackson.dataformat.xml.XmlMapper;

XmlMapper xmlMapper = new XmlMapper();
~~~

Đọc XML:

~~~java
OrderXml order = xmlMapper.readValue(xml, OrderXml.class);
~~~

Ghi XML:

~~~java
String xml = xmlMapper.writeValueAsString(order);
~~~

XmlMapper tái sử dụng nhiều annotation Jackson như JsonProperty, JsonIgnore, JsonInclude và custom serializer/deserializer, đồng thời cung cấp annotation riêng cho XML.

XML có root element, element con, attribute, namespace và text node. Vì vậy, DTO XML cần mô tả cách mỗi property xuất hiện trong tài liệu.

## 14. Root element và XML property

Dùng @JacksonXmlRootElement để xác định tên root element:

~~~java
@JacksonXmlRootElement(localName = "order")
public class OrderXml {
    // Properties và accessors
}
~~~

Dùng @JacksonXmlProperty để đặt tên element hoặc attribute:

~~~java
public class OrderXml {

    @JacksonXmlProperty(isAttribute = true, localName = "id")
    private String id;

    @JacksonXmlProperty(localName = "customer")
    private String customer;

    public OrderXml() {
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getCustomer() {
        return customer;
    }

    public void setCustomer(String customer) {
        this.customer = customer;
    }
}
~~~

XML có thể có dạng:

~~~xml
<order id="ORD-100">
    <customer>An Nguyen</customer>
</order>
~~~

Attribute và element không tương đương về semantics. Đừng đổi từ attribute sang element chỉ vì Java property vẫn có cùng tên.

## 15. Collection wrapper trong XML

XML thường biểu diễn collection bằng wrapper element chứa các item:

~~~xml
<order>
    <lines>
        <line>
            <sku>SKU-1</sku>
            <quantity>2</quantity>
        </line>
        <line>
            <sku>SKU-2</sku>
            <quantity>1</quantity>
        </line>
    </lines>
</order>
~~~

Khai báo rõ wrapper và item:

~~~java
public class OrderXml {

    @JacksonXmlElementWrapper(localName = "lines")
    @JacksonXmlProperty(localName = "line")
    private List<OrderLineXml> lines;

    // Constructor/accessors
}
~~~

Nếu hợp đồng yêu cầu các item lặp trực tiếp dưới root, không có wrapper:

~~~java
@JacksonXmlElementWrapper(useWrapping = false)
@JacksonXmlProperty(localName = "line")
private List<OrderLineXml> lines;
~~~

Cấu hình wrapper mặc định có thể khác kỳ vọng của consumer. Luôn khai báo rõ và giữ fixture XML để kiểm tra cấu trúc đầu ra.

## 16. Attribute, text và element

Một XML element có thể chứa:

- Attribute: metadata nằm trong thẻ mở.
- Child element: phần tử con.
- Text content: nội dung văn bản bên trong.
- Mixed content: text xen kẽ với child element.

Jackson XML hỗ trợ các annotation:

| Annotation | Vai trò |
|---|---|
| @JacksonXmlRootElement | Tên root element và namespace |
| @JacksonXmlProperty | Tên element, namespace hoặc attribute |
| @JacksonXmlElementWrapper | Wrapper của collection |
| @JacksonXmlText | Ánh xạ property vào text content của element |

Ví dụ text content:

~~~java
public class DescriptionXml {

    @JacksonXmlText
    private String value;

    public DescriptionXml() {
    }

    public String getValue() {
        return value;
    }

    public void setValue(String value) {
        this.value = value;
    }
}
~~~

XML:

~~~xml
<description>Priority shipment</description>
~~~

Mixed content phức tạp, chẳng hạn text xen giữa nhiều element con, không phải lúc nào cũng ánh xạ tự nhiên vào POJO. Nếu cần giữ nguyên thứ tự text/element, comment hoặc processing instruction, nên cân nhắc StAX/DOM hoặc công cụ XML chuyên dụng thay vì ép toàn bộ vào DTO.

## 17. Namespace trong XML

Namespace URI là một phần của tên XML. Prefix chỉ là bí danh có thể thay đổi.

Ví dụ:

~~~xml
<ord:order xmlns:ord="urn:example:orders" id="ORD-100">
    <ord:customer>An Nguyen</ord:customer>
</ord:order>
~~~

Có thể cấu hình namespace:

~~~java
@JacksonXmlRootElement(
    localName = "order",
    namespace = "urn:example:orders"
)
public class OrderXml {

    @JacksonXmlProperty(
        localName = "customer",
        namespace = "urn:example:orders"
    )
    private String customer;

    // Constructor/accessors
}
~~~

Khi kiểm thử, ưu tiên xác nhận namespace URI và local name, không phụ thuộc prefix cụ thể do generator chọn. Hai tài liệu dùng prefix khác nhau nhưng cùng namespace URI có thể tương đương về XML semantics.

Nếu schema dùng nhiều namespace, hãy khai báo rõ từng property và test với tài liệu thực từ đối tác.

## 18. Thứ tự XML element

Trong XML, thứ tự child element có thể là một phần của XSD sequence. Nếu consumer yêu cầu thứ tự, hãy định nghĩa rõ bằng property order hoặc cách ghi tương ứng:

~~~java
@JsonPropertyOrder({
    "id",
    "customer",
    "lines"
})
@JacksonXmlRootElement(localName = "order")
public class OrderXml {
    // Properties
}
~~~

Property order là một phần output contract khi XSD hoặc consumer yêu cầu sequence cụ thể. Không nên dựa vào thứ tự field tình cờ trong class hoặc reflection.

Nếu thứ tự không có ý nghĩa theo schema, test nên kiểm tra cấu trúc/giá trị thay vì so sánh chuỗi XML nguyên văn.

## 19. XML attribute và element có kiểu dữ liệu

XML biểu diễn hầu hết giá trị dưới dạng lexical text. Jackson bind text vào kiểu Java theo target type và serializer/deserializer.

Ví dụ:

~~~xml
<product id="P-100">
    <price>125.50</price>
    <available>true</available>
    <release-date>2026-11-12</release-date>
</product>
~~~

DTO:

~~~java
@JacksonXmlRootElement(localName = "product")
public class ProductXml {

    @JacksonXmlProperty(isAttribute = true, localName = "id")
    private String id;

    @JacksonXmlProperty(localName = "price")
    private BigDecimal price;

    @JacksonXmlProperty(localName = "available")
    private boolean available;

    @JacksonXmlProperty(localName = "release-date")
    private LocalDate releaseDate;

    // Constructor/accessors
}
~~~

Nếu dùng Java Time, đăng ký JavaTimeModule tương thích với Jackson version. Date/time format trong XML cần được quy định rõ; không phụ thuộc locale hoặc timezone mặc định của JVM.

Với BigDecimal, xác định decimal point, scale và rounding. Với enum, xác định wire value, không mặc định rằng tên enum Java sẽ luôn là contract lâu dài.

## 20. XML null, missing và empty element

Các biểu diễn sau có semantics khác nhau:

~~~xml
<customer>
    <name>An</name>
</customer>
~~~

~~~xml
<customer>
    <name></name>
</customer>
~~~

~~~xml
<customer>
    <name/>
</customer>
~~~

Một schema XML có thể còn dùng xsi:nil:

~~~xml
<customer xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <name xsi:nil="true"/>
</customer>
~~~

Không nên giả định XmlMapper tự giữ nguyên mọi khác biệt giữa missing, empty và xsi:nil theo đúng nghiệp vụ. Behavior còn phụ thuộc type Java, annotation, module version và cấu hình parser/databind.

Nếu hợp đồng cần phân biệt:

- Element không xuất hiện.
- Element rỗng.
- Element có whitespace.
- Element nil.
- Element có giá trị.

hãy tạo fixture riêng cho từng trường hợp và kiểm tra object sau deserialize cũng như XML được ghi ra. Có thể cần custom deserializer hoặc XML adapter nếu semantics phức tạp hơn mapping mặc định.

## 21. XSD và validation

XmlMapper đảm nhiệm data binding. Nó không tự thay thế bước validate tài liệu với XSD.

Nếu hợp đồng XML có XSD, nên xác thực tài liệu theo schema ở boundary trước khi đưa vào business processing hoặc sau khi tạo XML trước khi phát hành.

Ví dụ dùng JAXP:

~~~java
SchemaFactory schemaFactory = SchemaFactory.newInstance(
    XMLConstants.W3C_XML_SCHEMA_NS_URI
);

schemaFactory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
schemaFactory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

Schema schema = schemaFactory.newSchema(xsdSource);

Validator validator = schema.newValidator();
validator.validate(new StreamSource(new StringReader(xml)));
~~~

XSD có thể kiểm tra:

- Root element và namespace.
- Element/attribute bắt buộc.
- Thứ tự element theo sequence.
- Kiểu dữ liệu lexical.
- Min/max occurrence.
- Enumeration và pattern.
- Nillable/default/fixed theo schema.

XSD không thay thế business validation. Ví dụ currency code có thể hợp lệ về pattern nhưng không được hỗ trợ trong một nghiệp vụ cụ thể.

Khi load XSD từ nguồn bên ngoài, cần kiểm soát external schema access và nguồn import/include. Không cho validator tải schema tùy ý từ network nếu policy không cho phép.

## 22. XML security: DTD và external entity

XML parser có thể hỗ trợ DTD và external entities. Nếu xử lý XML không tin cậy, cấu hình parser để vô hiệu hóa các tính năng không cần thiết nhằm giảm rủi ro XXE và truy cập tài nguyên ngoài ý muốn.

Ví dụ cấu hình StAX input factory:

~~~java
XMLInputFactory inputFactory = XMLInputFactory.newFactory();

inputFactory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
inputFactory.setProperty(
    XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES,
    false
);
~~~

Sau đó truyền input factory đã cấu hình vào XmlFactory/XmlMapper theo API được hỗ trợ bởi Jackson XML version đang dùng:

~~~java
XmlFactory xmlFactory = XmlFactory.builder()
    .xmlInputFactory(inputFactory)
    .build();

XmlMapper xmlMapper = new XmlMapper(xmlFactory);
~~~

Tên builder method và constructor có thể khác theo release line. Nếu StAX implementation không hỗ trợ property bảo mật, không âm thầm bỏ qua rồi tiếp tục parse dữ liệu không tin cậy; hãy xác nhận cấu hình tương đương hoặc dùng implementation đã được kiểm soát.

Ngoài XXE, cần giới hạn:

- Kích thước tài liệu.
- Độ sâu element.
- Số lượng node/record.
- Độ dài text.
- Thời gian parse.
- Kích thước sau giải nén.
- Schema import/include và external resource.

Không bật DTD hoặc external entity chỉ vì một file legacy yêu cầu, nếu chưa có đánh giá và kiểm soát nguồn tài liệu.

## 23. CSV security và spreadsheet formula injection

CSV export thường được mở bằng spreadsheet. Một ô chứa dữ liệu bắt đầu bằng các ký tự như dấu bằng, cộng, trừ hoặc @ có thể bị spreadsheet diễn giải như công thức thay vì text, tùy ứng dụng.

Ví dụ dữ liệu do người dùng cung cấp:

~~~csv
customer_name,note
An Nguyen,=HYPERLINK("https://example.invalid","open")
~~~

Nếu export dữ liệu không tin cậy cho spreadsheet, cần có policy chống formula injection. Có thể prefix/escape các giá trị nguy hiểm theo quy tắc của consumer, nhưng thao tác này làm thay đổi representation nên phải được áp dụng có chủ đích cho spreadsheet export.

Không tự động sửa dữ liệu CSV machine-to-machine nếu hợp đồng yêu cầu giữ nguyên giá trị. Tách rõ export dành cho spreadsheet với CSV dùng trong giao thức hệ thống.

Cũng cần quote/escape đúng delimiter, quote và newline. Không tự nối chuỗi để tạo CSV vì có thể làm hỏng cấu trúc hoặc tạo injection.

## 24. Streaming với XML

XmlMapper có thể đọc từ InputStream:

~~~java
try (InputStream input = Files.newInputStream(path)) {
    OrderXml order = xmlMapper.readValue(input, OrderXml.class);
}
~~~

Ghi ra OutputStream:

~~~java
try (OutputStream output = Files.newOutputStream(path)) {
    xmlMapper.writeValue(output, order);
}
~~~

Nhưng readValue(InputStream, LargeDocument.class) vẫn tạo toàn bộ object graph đích. Nếu XML chứa hàng triệu record và chỉ cần xử lý từng record, cần dùng StAX streaming hoặc parser API phù hợp thay vì bind toàn bộ document.

Jackson XML sử dụng StAX ở tầng parser/generator. Có thể tạo XMLStreamReader từ XMLInputFactory rồi dùng XmlMapper đọc một subtree/element theo nhu cầu; chi tiết API cần đối chiếu version module và test kỹ vì cursor position sau khi bind là một phần quan trọng của logic.

Khi cần kiểm soát memory chặt, xử lý theo từng record XML bằng StAX, validate boundary và chuyển từng record thành DTO. Không giữ tất cả record trong List nếu mục tiêu là streaming.

## 25. Streaming với CSV

CsvMapper hỗ trợ đọc tuần tự bằng MappingIterator và ghi tuần tự bằng SequenceWriter. Đây thường là lựa chọn đơn giản cho bảng lớn.

~~~text
CSV file
   |
   v
CsvMapper + CsvSchema
   |
   v
MappingIterator<RowDto>
   |
   +--> validate row
   |
   +--> process row
   |
   +--> record error
~~~

Đọc từng record:

~~~java
try (MappingIterator<OrderCsvRow> rows = csvMapper
        .readerFor(OrderCsvRow.class)
        .with(CsvSchema.emptySchema().withHeader())
        .readValues(input)) {

    while (rows.hasNextValue()) {
        OrderCsvRow row = rows.nextValue();
        process(row);
    }
}
~~~

Ghi từng record:

~~~java
try (SequenceWriter rows = csvMapper
        .writer(schema)
        .writeValues(output)) {

    for (OrderCsvRow row : source) {
        rows.write(row);
    }
}
~~~

Streaming giảm nhu cầu giữ toàn bộ bảng trong bộ nhớ, nhưng ứng dụng vẫn cần kiểm soát số lượng lỗi, batch size và tài nguyên nguồn.

## 26. Spring integration cho CSV và XML

Spring MVC có converter riêng cho XML trong hệ sinh thái Jackson, ví dụ MappingJackson2XmlHttpMessageConverter ở các stack dùng Jackson 2. Converter cần được đăng ký và cấu hình với XmlMapper phù hợp.

CSV thường không được tự động hỗ trợ như JSON trong mọi cấu hình Spring Boot. Có thể tạo converter riêng hoặc xử lý file import/export tại service boundary bằng CsvMapper.

Ví dụ converter XML:

~~~java
@Bean
MappingJackson2XmlHttpMessageConverter xmlConverter(
        XmlMapper xmlMapper) {
    return new MappingJackson2XmlHttpMessageConverter(xmlMapper);
}
~~~

API và package có thể khác giữa Spring Framework/Spring Boot major versions. Kiểm tra converter thực tế được đăng ký, Content-Type và Accept negotiation.

Media type thường dùng:

| Định dạng | Content-Type thường gặp |
|---|---|
| CSV | text/csv; charset=UTF-8 |
| XML | application/xml |

Không gửi CSV bytes dưới Content-Type application/json hoặc XML text dưới Content-Type khác với contract. Nếu endpoint hỗ trợ nhiều representation, client và server phải thống nhất Accept/Content-Type, status code và lỗi khi format không được hỗ trợ.

## 27. Kiểm thử CSV contract

Nên giữ fixture CSV độc lập trong test resources:

~~~csv
order_id,customer_name,total,currency
ORD-100,"An Nguyen",125.50,VND
ORD-101,"Binh, Tran",90.00,VND
~~~

Test đọc:

~~~java
@Test
void readsCsvFixtureWithQuotedDelimiter() throws Exception {
    CsvSchema schema = CsvSchema.emptySchema().withHeader();

    List<OrderCsvRow> rows;
    try (MappingIterator<OrderCsvRow> iterator = csvMapper
            .readerFor(OrderCsvRow.class)
            .with(schema)
            .readValues(fixtureInput)) {

        rows = iterator.readAll();
    }

    assertEquals(2, rows.size());
    assertEquals("Binh, Tran", rows.get(1).customerName());
    assertEquals(new BigDecimal("90.00"), rows.get(1).total());
}
~~~

Test ghi nên so sánh output với fixture hoặc parse lại theo schema độc lập:

~~~java
String csv = csvMapper.writer(schema).writeValueAsString(row);
~~~

Không chỉ assert round-trip với cùng mapper. Producer và consumer có thể cùng hiểu sai header hoặc null semantics theo một cách nhất quán.

Các trường hợp cần test:

- Header đúng tên và đúng thứ tự.
- Cột bị thiếu hoặc dư.
- Header trùng.
- Field có delimiter, quote hoặc newline.
- Unicode và UTF-8.
- Empty string, null sentinel và missing value.
- Date/time, decimal và boolean.
- Dòng rỗng và dòng bị cắt cụt.
- Field quá dài hoặc sai số cột.
- Formula injection nếu export cho spreadsheet.

## 28. Kiểm thử XML contract

Giữ XML fixture độc lập:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<order xmlns="urn:example:orders" id="ORD-100">
    <customer>An Nguyen</customer>
    <lines>
        <line>
            <sku>SKU-1</sku>
            <quantity>2</quantity>
        </line>
    </lines>
</order>
~~~

Test đọc:

~~~java
@Test
void readsXmlFixtureWithNamespaceAndWrappedCollection() throws Exception {
    OrderXml order = xmlMapper.readValue(xmlFixture, OrderXml.class);

    assertEquals("ORD-100", order.getId());
    assertEquals("An Nguyen", order.getCustomer());
    assertEquals(1, order.getLines().size());
    assertEquals("SKU-1", order.getLines().get(0).getSku());
}
~~~

Test ghi:

- Parse output XML bằng XML parser.
- Kiểm tra root local name và namespace URI.
- Kiểm tra attribute và child element.
- Kiểm tra wrapper và item element.
- Kiểm tra thứ tự nếu XSD yêu cầu.
- Validate output bằng XSD nếu contract có schema.
- Không phụ thuộc prefix hoặc indentation nếu chúng không thuộc hợp đồng.

Test thêm:

- Element missing, empty và xsi:nil.
- Unknown element/attribute.
- Namespace URI sai.
- XML malformed hoặc truncated.
- DTD/external entity bị từ chối.
- Text có ký tự cần escape.
- Unicode.
- Date/time và decimal lexical format.
- Collection rỗng và collection có nhiều phần tử.

## 29. Kiểm thử hai chiều độc lập

Một round-trip:

~~~java
T source = sample();
String document = mapper.writeValueAsString(source);
T restored = mapper.readValue(document, targetType);
assertEquals(source, restored);
~~~

chỉ chứng minh serializer và deserializer của cùng cấu hình có thể hiểu nhau. Nó không chứng minh tài liệu đúng với đối tác hoặc XSD đã công bố.

Nên có:

1. Fixture do consumer/đối tác hoặc contract review cung cấp để test đọc.
2. Expected document độc lập để test ghi.
3. Schema validation nếu có XSD.
4. Test lỗi và compatibility với tài liệu version cũ.
5. Integration test qua HTTP/file/message boundary thực tế.

Với CSV, fixture phải cố định header, delimiter, quote, line ending và null representation. Với XML, fixture phải cố định namespace, root, attribute/element và collection wrapper.

## 30. Quản lý version và schema evolution

CSV và XML đều cần versioning. Không giả định việc thêm field luôn tương thích.

Có thể version bằng:

- Version trong tên file hoặc metadata transport.
- Header/schema version riêng cho CSV.
- Attribute hoặc element version trong XML.
- Endpoint/media type version.
- Message envelope bên ngoài tài liệu.

Khi thay đổi contract, hãy phân loại:

| Thay đổi | CSV | XML |
|---|---|---|
| Thêm optional field | Có thể phá consumer theo vị trí | Có thể phá XSD sequence hoặc strict consumer |
| Đổi tên field | Đổi header | Đổi element/attribute name |
| Đổi kiểu | Thay lexical value | Thay text/type/schema |
| Thay null semantics | Ô rỗng/sentinel thay đổi | Empty/nil/missing thay đổi |
| Đổi thứ tự | Có thể phá position-based reader | Có thể phá XSD sequence |
| Thay namespace | Không áp dụng | Thay đổi identity của element |

Giữ fixture của version cũ và test consumer mới đọc được nếu chính sách backward compatibility yêu cầu. Không xóa cột hoặc element trước khi biết consumer nào còn dùng.

## 31. Các lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Tách CSV bằng split dấu phẩy | Không xử lý quote/newline | Dùng CsvMapper/CsvSchema |
| Chỉ dùng schemaFor() cho public contract | Schema phụ thuộc model introspection | Định nghĩa schema và fixture tường minh |
| Header đổi thứ tự làm sai dữ liệu | Consumer map theo vị trí | Map theo header hoặc khóa thứ tự contract |
| Ô rỗng bị coi là null ngoài ý muốn | CSV không chuẩn hóa null | Quy định sentinel và test |
| Nested DTO không có representation ổn định | CSV là bảng phẳng | Dùng row DTO và flatten explicit |
| Decimal/date phụ thuộc locale | Không quy định lexical format | Chốt decimal/date/time format |
| Export CSV bị formula injection | Cell không tin cậy được spreadsheet thực thi | Policy escape cho spreadsheet export |
| XML root sai tên | Không khai báo root rõ | @JacksonXmlRootElement |
| List có wrapper ngoài ý muốn | Dựa vào default collection wrapping | @JacksonXmlElementWrapper tường minh |
| Attribute thành element | Thiếu isAttribute=true | Khai báo XML property role |
| Namespace prefix bị assert cứng | Nhầm prefix với namespace identity | Assert URI và local name |
| XML output sai thứ tự | Không định nghĩa property order | @JsonPropertyOrder khi schema yêu cầu |
| Mixed content bị mất | Ép XML phức tạp vào POJO | Dùng StAX/DOM hoặc XML-specific model |
| XSD không được kiểm tra | Nhầm databind với schema validation | Validate riêng bằng Validator |
| XML parser cho phép external entity | Thiếu hardening StAX | Tắt DTD/external entities |
| Round-trip pass nhưng đối tác fail | Hai chiều cùng dùng giả định | Fixture độc lập và schema validation |
| Đọc file lớn thành List | Materialize toàn bộ records | MappingIterator hoặc StAX streaming |

## 32. Quy trình xây dựng hợp đồng CSV/XML

1. Xác định consumer và mục đích trao đổi.
2. Chọn CSV cho bảng phẳng hoặc XML cho cây phần tử/namespace theo nhu cầu.
3. Định nghĩa wire contract độc lập với Java DTO.
4. Chốt encoding, media type và version.
5. Với CSV, chốt header, thứ tự cột, delimiter, quote, line ending và null sentinel.
6. Với XML, chốt root, namespace URI, attribute/element, wrapper, order và XSD.
7. Tạo DTO adapter phù hợp với từng format.
8. Dùng CsvMapper/CsvSchema hoặc XmlMapper/XML annotations tường minh.
9. Cấu hình parser bảo mật và giới hạn kích thước.
10. Xác định validation, unknown field và error policy.
11. Dùng MappingIterator/SequenceWriter hoặc StAX cho dữ liệu lớn.
12. Viết fixture độc lập cho cả đọc và ghi.
13. Kiểm tra schema evolution và tài liệu version cũ.
14. Test qua HTTP, file hoặc message adapter thực tế.
15. Lưu hợp đồng, fixture và version cùng release.

## 33. Nguyên tắc nên giữ

- CSV và XML là hai mô hình dữ liệu khác nhau; không áp một cách mapping chung cho cả hai.
- Dùng jackson-dataformat-csv với CsvMapper và CsvSchema.
- Dùng jackson-dataformat-xml với XmlMapper và annotation XML.
- Đồng bộ dataformat module với Jackson core/databind qua BOM hoặc constraints.
- Định nghĩa CSV header, thứ tự cột, delimiter, quote và null semantics tường minh.
- Dùng row DTO phẳng cho CSV; flatten nested object bằng adapter có chủ đích.
- Không tự tách CSV bằng String.split().
- Quy định date/time, decimal, boolean và identifier theo wire format cố định.
- Có policy formula injection riêng cho CSV export dành cho spreadsheet.
- Định nghĩa XML root, namespace URI, attribute/element và collection wrapper.
- Dùng namespace URI làm identity, không phụ thuộc prefix.
- Dùng XSD validation khi hợp đồng yêu cầu schema XML.
- Không giả định XmlMapper bảo toàn comment, mixed content hoặc toàn bộ XML infoset.
- Vô hiệu hóa DTD/external entities khi xử lý XML không tin cậy.
- Phân biệt readValue(InputStream, DTO) với xử lý từng record; dùng MappingIterator hoặc StAX khi cần streaming.
- Test fixture độc lập hai chiều, schema validation và compatibility.

Đọc ghi CSV và XML bằng module tương ứng giúp Jackson tái sử dụng databind mà vẫn tôn trọng đặc điểm của từng định dạng. CsvMapper cần một CsvSchema rõ ràng để giữ ổn định cột và quy tắc text; XmlMapper cần annotation và namespace rõ ràng để tạo đúng cây element/attribute. Khi hợp đồng được mô tả độc lập với DTO, có fixture thực tế, validation và chính sách bảo mật, producer và consumer có thể trao đổi dữ liệu ổn định ngay cả khi model Java bên trong thay đổi.

