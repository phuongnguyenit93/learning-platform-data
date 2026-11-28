# Vì sao mô hình đối tượng Java không ánh xạ hoàn toàn sang XML

Trong một ứng dụng Java thông thường, dữ liệu được tổ chức thành đối tượng, thuộc tính, collection và quan hệ giữa các đối tượng. Trong một dịch vụ SOAP, thông điệp được biểu diễn thành XML và thường phải tuân theo một hợp đồng XML Schema (XSD) được công bố qua WSDL. Hai cách mô hình hóa này có nhiều điểm tương đồng, nhưng **không tương đương hoàn toàn về cấu trúc, kiểu dữ liệu, ràng buộc và ngữ nghĩa**.

Đây là lý do quan trọng để học Spring Web Services (Spring-WS) theo hướng **contract-first**: thiết kế hợp đồng XSD/WSDL trước, sinh hoặc liên kết lớp Java qua JAXB, rồi chủ động xử lý những khác biệt ở ranh giới tích hợp. JAXB giúp chuyển đổi đối tượng và XML, nhưng không biến mô hình đối tượng Java thành bản sao đầy đủ của XML Schema.

## 1. Hai mô hình phục vụ hai mục đích khác nhau

**Mô hình đối tượng Java** ưu tiên biểu diễn trạng thái và hành vi bên trong chương trình:

- Một lớp định nghĩa field, method, constructor và các quan hệ kế thừa.
- Một đối tượng có danh tính (identity); nhiều biến có thể cùng tham chiếu đến một đối tượng.
- Kiểu dữ liệu được kiểm tra qua hệ thống kiểu của Java, generic và các điều kiện do lập trình viên viết.
- Collection thể hiện nhiều phần tử, nhưng bản thân kiểu như `List<T>` không mô tả đầy đủ số lượng tối thiểu/tối đa theo một giao thức trao đổi dữ liệu.
- Một tham chiếu có thể mang giá trị `null`, nhưng Java không có sẵn khái niệm “phần tử XML hoàn toàn vắng mặt” tách biệt với “phần tử XML có `xsi:nil`”.

**Mô hình XML/XSD** ưu tiên biểu diễn một tài liệu và các quy tắc để những hệ thống độc lập hiểu tài liệu đó:

- XML là cây nút gồm element, attribute, text, namespace và thứ tự con.
- Tên element được xác định bằng **QName**: cặp namespace URI và local name.
- XSD mô tả element/attribute, kiểu đơn/kiểu phức, thứ tự, lựa chọn, số lần xuất hiện, khả năng `nil` và các ràng buộc về giá trị.
- SOAP/WSDL còn xác định cấu trúc thông điệp và thao tác dịch vụ để các bên không dùng Java vẫn có thể trao đổi.

Một field Java và một element XML có thể chứa giá trị giống nhau, nhưng chưa chắc mang cùng ý nghĩa trong hợp đồng.

| Góc nhìn | Java | XML/XSD |
|---|---|---|
| Tên và phạm vi | Tên class/field, package | Element/attribute và namespace URI |
| Hình dạng dữ liệu | Đồ thị tham chiếu đối tượng | Cây XML có thứ tự |
| Giá trị thiếu | Thường dùng `null` hoặc wrapper | Vắng mặt, có mặt, `xsi:nil`, rỗng |
| Nhiều phần tử | Array, `List<T>`, `Set<T>` | `minOccurs`, `maxOccurs`, `xs:sequence`, `xs:choice` |
| Ràng buộc giá trị | Kiểu Java và logic kiểm tra | `pattern`, `minInclusive`, `maxLength`, `totalDigits`... |
| Kiểu thời gian | `LocalDate`, `Instant`, `OffsetDateTime`... | `xs:date`, `xs:dateTime`, quy tắc lexical và múi giờ |
| Mở rộng | Kế thừa, interface, generic | `xs:extension`, `xs:restriction`, substitution group, wildcard |
| Tính tương thích | Phụ thuộc API và runtime Java | Phụ thuộc XSD/WSDL và cấu trúc XML trao đổi |

## 2. Ví dụ: hợp đồng XML có nhiều thông tin hơn một DTO Java

Giả sử hệ thống đặt hàng công bố một yêu cầu gửi đơn. Một phần XSD của hợp đồng có dạng:

~~~xml
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:tns="urn:example:orders:v1"
    targetNamespace="urn:example:orders:v1"
    elementFormDefault="qualified">

    <xs:element name="SubmitOrderRequest" type="tns:SubmitOrderRequestType"/>

    <xs:complexType name="SubmitOrderRequestType">
        <xs:sequence>
            <xs:element name="customerId" type="xs:string"/>
            <xs:element name="deliveryNote"
                        type="xs:string"
                        minOccurs="0"
                        nillable="true"/>
            <xs:element name="item"
                        type="tns:OrderItemType"
                        minOccurs="1"
                        maxOccurs="unbounded"/>
        </xs:sequence>
        <xs:attribute name="externalId" type="xs:string" use="required"/>
    </xs:complexType>

    <xs:complexType name="OrderItemType">
        <xs:sequence>
            <xs:element name="sku" type="xs:string"/>
            <xs:element name="quantity" type="xs:positiveInteger"/>
            <xs:element name="unitPrice" type="xs:decimal"/>
        </xs:sequence>
    </xs:complexType>
</xs:schema>
~~~

Một XML hợp lệ theo cấu trúc trên có thể là:

~~~xml
<ord:SubmitOrderRequest
    xmlns:ord="urn:example:orders:v1"
    externalId="EXT-1042">
    <ord:customerId>CUS-17</ord:customerId>
    <ord:item>
        <ord:sku>BOOK-001</ord:sku>
        <ord:quantity>2</ord:quantity>
        <ord:unitPrice>125000.50</ord:unitPrice>
    </ord:item>
</ord:SubmitOrderRequest>
~~~

Nếu chỉ quan tâm nghiệp vụ, ta dễ viết một DTO:

~~~java
public record SubmitOrder(
    String externalId,
    String customerId,
    String deliveryNote,
    List<OrderItem> items
) {}

public record OrderItem(
    String sku,
    int quantity,
    BigDecimal unitPrice
) {}
~~~

DTO này có thể hữu ích cho tầng nghiệp vụ, nhưng **tự nó không mô tả chính xác hợp đồng XML**:

1. `externalId` nằm ở **attribute**; `customerId`, `deliveryNote`, `item` là **element** có thứ tự. Java record không chứa quy tắc đó.
2. `item` phải xuất hiện **ít nhất một lần**. `List<OrderItem>` vẫn có thể rỗng hoặc `null`.
3. `quantity` phải là số nguyên **lớn hơn 0**. `int` vẫn chấp nhận 0 và số âm.
4. `deliveryNote` cho phép **vắng mặt** hoặc **hiện diện với `xsi:nil="true"`**. Một `String` nullable không phân biệt rõ cả hai.
5. Tên element gốc có namespace `urn:example:orders:v1`. Tên class Java không xác định duy nhất QName này.
6. `xs:decimal` có quy tắc biểu diễn XML riêng; chọn `BigDecimal` giúp giữ độ chính xác, nhưng vẫn cần kiểm soát quy ước tiền tệ, làm tròn và validation nếu nghiệp vụ yêu cầu.

Do đó, không thể suy ra toàn bộ hợp đồng XSD chỉ từ chữ ký của DTO. Ngược lại, khi sinh Java từ XSD, nhiều quy tắc của XSD sẽ nằm trong annotation, lớp bổ trợ hoặc chỉ còn được kiểm tra bởi XML Schema validator.

## 3. Những khác biệt không thể bỏ qua

### 3.1. Element, attribute và namespace không phải field Java

Trong XML, hai tên cùng local name nhưng khác namespace là hai tên khác nhau:

~~~xml
<a:status xmlns:a="urn:example:order">PAID</a:status>
<b:status xmlns:b="urn:example:shipment">PAID</b:status>
~~~

Một field Java tên `status` không mang đủ thông tin về namespace. JAXB phải dựa vào metadata như `@XmlRootElement`, `@XmlElement`, `@XmlAttribute`, `@XmlType`, `@XmlSchema` hoặc `JAXBElement`/QName để chọn đúng biểu diễn XML.

Tương tự, Java không có sự phân biệt sẵn giữa attribute và child element:

~~~xml
<ord:order xmlns:ord="urn:example:orders:v1" externalId="EXT-1042">
    <ord:customerId>CUS-17</ord:customerId>
</ord:order>
~~~

Trong đoạn này, `externalId` là attribute không có namespace theo cách khai báo trên; `customerId` là element thuộc namespace của hợp đồng. Hai giá trị có thể cùng là `String` trong Java, nhưng có vị trí và QName khác nhau trong XML.

**Hệ quả:** Đổi package hay tên field không tự động là một thay đổi tương thích của SOAP contract. Khi sửa XSD, cần kiểm tra QName, element/attribute và namespace chứ không chỉ so sánh tên property Java.

### 3.2. Vắng mặt, `xsi:nil` và chuỗi rỗng là ba trạng thái khác nhau

Với `deliveryNote minOccurs="0" nillable="true"`, có ít nhất ba cách biểu diễn hợp lệ:

**Không gửi phần tử:**

~~~xml
<!-- Không xuất hiện deliveryNote -->
~~~

**Gửi phần tử nhưng đánh dấu nil:**

~~~xml
<ord:deliveryNote
    xmlns:ord="urn:example:orders:v1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:nil="true"/>
~~~

**Gửi phần tử có chuỗi rỗng:**

~~~xml
<ord:deliveryNote xmlns:ord="urn:example:orders:v1"></ord:deliveryNote>
~~~

Trong nghiệp vụ, ba trường hợp có thể mang ba ý nghĩa khác nhau, chẳng hạn: không cập nhật ghi chú, chủ động xóa ghi chú, hoặc đặt ghi chú thành chuỗi rỗng.

Nếu chỉ ánh xạ sang `String deliveryNote`, cả **vắng mặt** và **nil** thường dễ bị gom về `null`; còn chuỗi rỗng có thể là `""`. Với trường cần bảo toàn sự phân biệt, JAXB có thể dùng `JAXBElement<String>` hoặc một cấu trúc theo dõi việc element có xuất hiện hay không. Cách mã JAXB thực tế được sinh ra phụ thuộc XSD và cấu hình binding, vì vậy cần đọc lớp sinh ra và kiểm thử round-trip.

**Phân biệt thêm:**

- `minOccurs="0"`: element có thể **không xuất hiện**.
- `nillable="true"`: element **đã xuất hiện** có thể mang `xsi:nil="true"`.
- `required=true` trong một annotation JAXB diễn tả metadata ánh xạ; không thay thế việc chạy XML Schema validation đầy đủ ở runtime.

### 3.3. Thứ tự, số lượng và lựa chọn trong XSD không tự động được bảo vệ bởi kiểu Java

Trong `xs:sequence`, phần tử phải có thứ tự khai báo: `customerId`, rồi `deliveryNote` nếu có, sau đó là `item`. Java object không đặt ra thứ tự tự nhiên cho field theo quy tắc XSD.

XSD còn có `xs:choice`, nghĩa là chọn một trong các nhánh:

~~~xml
<xs:choice>
    <xs:element name="personId" type="xs:string"/>
    <xs:element name="organizationId" type="xs:string"/>
</xs:choice>
~~~

Một DTO viết tay như sau không bảo đảm quy tắc “chọn đúng một”:

~~~java
public class CustomerIdentity {
    private String personId;
    private String organizationId;
}
~~~

DTO này cho phép cả hai thuộc tính đều có giá trị, hoặc cả hai đều `null`. Trong khi đó, `xs:choice` ở ví dụ yêu cầu đúng một nhánh khi xuất hiện. JAXB có thể biểu diễn choice bằng nhiều cấu trúc khác nhau (ví dụ property được gắn `@XmlElements`, một kiểu chung hoặc `JAXBElement`), nhưng **người sử dụng mô hình Java vẫn phải bảo đảm trạng thái hợp lệ**.

Với `maxOccurs="unbounded"`, JAXB thường dùng `List<T>`, nhưng `List<T>` không thể hiện `minOccurs="1"` trong hệ thống kiểu. Quy tắc này phải được kiểm tra qua XSD validator hoặc validation nghiệp vụ thích hợp.

### 3.4. Ràng buộc XSD phong phú hơn kiểu Java

XSD có thể mô tả:

~~~xml
<xs:simpleType name="ProductCode">
    <xs:restriction base="xs:string">
        <xs:pattern value="[A-Z]{3}-[0-9]{4}"/>
    </xs:restriction>
</xs:simpleType>

<xs:simpleType name="Quantity">
    <xs:restriction base="xs:positiveInteger">
        <xs:maxInclusive value="100"/>
    </xs:restriction>
</xs:simpleType>

<xs:simpleType name="UnitPrice">
    <xs:restriction base="xs:decimal">
        <xs:totalDigits value="12"/>
        <xs:fractionDigits value="2"/>
    </xs:restriction>
</xs:simpleType>
~~~

Khi ánh xạ sang `String`, `BigInteger` hoặc `BigDecimal`, kiểu Java tương ứng **không tự biết** pattern, giới hạn 100, tổng số chữ số hoặc số chữ số thập phân. Một đối tượng Java có thể được khởi tạo thành công nhưng không thỏa XSD.

Ví dụ: `new BigDecimal("12.345")` là giá trị Java hợp lệ, nhưng có thể vi phạm `fractionDigits=2` theo quy tắc XSD của contract. Tương tự, `new BigInteger("0")` hợp lệ trong Java nhưng vi phạm `xs:positiveInteger`.

Điều này làm rõ sự khác nhau giữa **ánh xạ kiểu** và **xác thực hợp đồng**. JAXB chịu trách nhiệm chuyển đổi biểu diễn; việc bảo đảm XML hợp lệ theo toàn bộ XSD cần được cấu hình kiểm tra schema và bổ sung quy tắc nghiệp vụ nếu cần.

### 3.5. Đồ thị đối tượng Java khác cây XML

Trong Java, hai field có thể tham chiếu cùng một instance:

~~~java
Address shared = new Address("Hà Nội");
customer.setBillingAddress(shared);
customer.setShippingAddress(shared);

// Hai field cùng tham chiếu một đối tượng:
boolean same = customer.getBillingAddress() == customer.getShippingAddress();
~~~

XML thông thường có cấu trúc cây. Nếu ta tuần tự hóa hai địa chỉ thành hai nhánh con riêng, tài liệu có thể giữ **giá trị** nhưng không bảo toàn quan hệ “cùng một instance”. Một đồ thị có vòng tham chiếu cũng không thể được trải vô hạn vào một cây XML hữu hạn.

XML/XSD có cơ chế tham chiếu như `xs:ID`, `xs:IDREF`; JAXB có hỗ trợ `@XmlID`, `@XmlIDREF`. Tuy nhiên, để dùng chúng cần chủ động thiết kế contract và quy tắc nhận dạng. Không phải mọi quan hệ Java đều tự trở thành tham chiếu XML có ý nghĩa tương đương.

**Hệ quả:** Tránh coi payload SOAP là ảnh chụp toàn bộ domain object graph. Hợp đồng tích hợp thường nên diễn đạt dữ liệu cần trao đổi bằng cấu trúc rõ ràng, giới hạn và ổn định.

### 3.6. Kế thừa Java và đa hình XML/XSD không đồng nhất

Java có class inheritance, interface và polymorphism ở runtime. XSD có `xs:extension`, `xs:restriction`, `xsi:type`, substitution group và những giới hạn xuất hiện trong content model.

Ví dụ, một XML có thể dùng `xsi:type` để chỉ định kiểu phái sinh hợp lệ theo XSD. Điều đó không đồng nghĩa mọi đối tượng implement cùng Java interface đều có thể đưa vào vị trí đó. Ngược lại, substitution group có thể cho phép nhiều **tên element khác nhau** thay thế một head element, trong khi Java kế thừa chủ yếu nói về quan hệ giữa các **kiểu**.

JAXB có thể hỗ trợ nhiều cách biểu diễn đa hình, nhưng cần đủ thông tin về QName, `@XmlSeeAlso`, `@XmlElementRef`, `@XmlElements` hoặc binding tương ứng. Không nên mặc định một sơ đồ class inheritance là hợp đồng XML tương đương.

### 3.7. Mixed content, wildcard và extension point không có đối ứng đơn giản

XML có thể xen kẽ text và element:

~~~xml
<description xmlns="urn:example:catalog">
    Sách <emphasis>Spring-WS</emphasis> dành cho tích hợp.
</description>
~~~

Một `String description` chỉ giữ văn bản, khó bảo toàn đầy đủ thứ tự giữa các đoạn text và các element con. JAXB có thể dùng `@XmlMixed` và danh sách nội dung hỗn hợp, nhưng API Java nhận được thường phức tạp hơn nhiều so với một DTO thông thường.

XSD còn cho phép `xs:any`, `xs:anyAttribute` để chừa điểm mở rộng. Phần XML chưa biết trước có thể được giữ dưới dạng DOM node hoặc `Object`/cấu trúc JAXB phù hợp. Không phải mọi extension element đều có class Java đã biết khi biên dịch.

Với dữ liệu đặc biệt giàu cấu trúc XML, đôi khi giữ `Element`, `Source` hoặc XML fragment ở ranh giới là hợp lý hơn ép mọi thứ vào các field nghiệp vụ.

### 3.8. Kiểu thời gian và biểu diễn lexical không phải lúc nào cũng tương đương

XML Schema phân biệt `xs:date`, `xs:time`, `xs:dateTime` và các quy tắc về timezone. Trong khi đó, Java có `LocalDate`, `LocalDateTime`, `OffsetDateTime`, `ZonedDateTime`, `Instant` và nhiều API khác.

Chẳng hạn:

~~~xml
<createdAt>2026-11-27T09:30:00+07:00</createdAt>
~~~

Giá trị này có offset `+07:00`. Với một số trường hợp `xs:dateTime`, dữ liệu XML còn có thể **không cung cấp timezone**. Vì vậy, ép mọi `xs:dateTime` thành `Instant` mà không quy định timezone có thể làm mất thông tin hoặc tạo ra giả định sai.

JAXB sinh từ XSD thường dùng `XMLGregorianCalendar` cho một số kiểu lịch/thời gian; có thể dùng `XmlAdapter` để chuyển sang kiểu `java.time` khi phù hợp. Cần quyết định rõ cách xử lý timezone, precision và thời điểm không có offset.

Ngoài ra, chuyển đổi kiểu giá trị không bảo toàn nhất thiết hình thức văn bản gốc. Ví dụ, hai cách viết số hoặc datetime khác nhau có thể biểu thị cùng giá trị đã chuẩn hóa. **Round-trip về mặt giá trị** không có nghĩa là khôi phục chính xác từng byte XML, prefix namespace hoặc cách định dạng nguồn.

## 4. JAXB làm được gì và ranh giới của JAXB nằm ở đâu?

JAXB (Jakarta XML Binding trong hệ Spring-WS hiện đại) có thể:

- Ánh xạ nhiều kiểu XSD phổ biến sang kiểu Java thích hợp.
- Sinh lớp Java từ XSD thông qua công cụ hỗ trợ JAXB/XJC.
- Dựa trên annotation và metadata để marshal đối tượng thành XML, unmarshal XML thành đối tượng.
- Xử lý element/attribute, namespace, thứ tự, collection, một phần đa hình và một số cấu trúc đặc thù XML.

Ví dụ, một kiểu do JAXB sinh ra hoặc được khai báo tương đương có thể chứa:

~~~java
@XmlAccessorType(XmlAccessType.FIELD)
@XmlType(
    name = "OrderItemType",
    propOrder = {"sku", "quantity", "unitPrice"}
)
public class OrderItemType {

    @XmlElement(required = true)
    protected String sku;

    @XmlElement(required = true)
    protected BigInteger quantity;

    @XmlElement(required = true)
    protected BigDecimal unitPrice;

    // Getter/setter lược bỏ để tập trung vào ý chính.
}
~~~

Các annotation và kiểu Java giúp JAXB tạo XML đúng vị trí, nhưng **không đủ để kết luận `quantity > 0` hoặc `unitPrice` đáp ứng mọi facet của XSD**. JAXB runtime có cơ chế gắn `Schema` cho `Marshaller`/`Unmarshaller` khi ứng dụng cần XML Schema validation; nếu không cấu hình, không nên giả định toàn bộ ràng buộc XSD sẽ tự được kiểm tra.

Một cách nhìn hữu ích là phân chia bốn lớp trách nhiệm:

| Lớp | Cần bảo đảm điều gì? | Công cụ/biện pháp |
|---|---|---|
| Hợp đồng | Tên message, QName, cấu trúc XML, số lần xuất hiện, kiểu và facet | XSD/WSDL |
| Chuyển đổi | Chuyển XML sang đối tượng và ngược lại | JAXB, annotation, `JAXBElement`, adapter |
| Kiểm tra thông điệp | Payload có tuân theo XSD không? | XML Schema validation, interceptor |
| Nghiệp vụ | Khách hàng có tồn tại? đơn hàng có thể tạo? giá có hợp lệ theo quy định? | Service/domain validation |

Bốn lớp phối hợp với nhau. Không lớp nào tự thay thế hoàn toàn lớp còn lại.

## 5. Áp dụng trong Spring Web Services theo contract-first

Spring-WS đặt XML message và hợp đồng dịch vụ ở vị trí trung tâm. Một luồng thiết kế phổ biến là:

~~~mermaid
flowchart LR
    A["Thiết kế XSD"] --> B["Công bố WSDL / SOAP contract"]
    A --> C["Sinh Java binding bằng JAXB"]
    D["SOAP XML từ client"] --> E["Kiểm tra XSD"]
    E --> F["JAXB unmarshal"]
    F --> G["Spring-WS @Endpoint"]
    G --> H["Ánh xạ domain & xử lý nghiệp vụ"]
    H --> I["Tạo response JAXB"]
    I --> J["Marshal XML & trả SOAP"]
~~~

### Bước 1: Thiết kế hợp đồng trước đối tượng nội bộ

Xác định element gốc cho request/response, QName, thứ tự, cardinality, `nillable`, kiểu tiền tệ/thời gian, khả năng mở rộng và cách biểu diễn lỗi. Thiết kế xuất phát từ dữ liệu trao đổi và yêu cầu tương thích của các bên tích hợp, không mặc định công bố nguyên trạng entity JPA hoặc domain object.

### Bước 2: Sinh JAXB binding và đọc hiểu các lớp được tạo ra

Từ XSD, công cụ JAXB/XJC có thể sinh `ObjectFactory`, các class kiểu phức, package-level `@XmlSchema` và các `JAXBElement` cần thiết. Việc xuất hiện một kiểu như `XMLGregorianCalendar`, `BigInteger`, `JAXBElement<String>` hoặc live `List<T>` thường phản ánh đặc điểm của XSD.

Không sửa trực tiếp mã sinh tự động để “làm đẹp” mô hình. Nếu cần API nghiệp vụ gọn hơn, ánh xạ từ binding class sang domain model riêng.

### Bước 3: Dùng endpoint để chuyển giao giữa XML contract và nghiệp vụ

Một endpoint Spring-WS định tuyến dựa trên payload root, tức QName của request:

~~~java
@Endpoint
public class SubmitOrderEndpoint {

    private static final String NAMESPACE =
        "urn:example:orders:v1";

    private final OrderApplicationService service;

    public SubmitOrderEndpoint(OrderApplicationService service) {
        this.service = service;
    }

    @PayloadRoot(
        namespace = NAMESPACE,
        localPart = "SubmitOrderRequest"
    )
    @ResponsePayload
    public SubmitOrderResponse submit(
            @RequestPayload SubmitOrderRequest request) {

        return service.submit(request);
    }
}
~~~

Ví dụ này minh họa cách định tuyến và ranh giới xử lý, giả định binding Java đã có kiểu root request/response tương ứng, được JAXB nhận diện và application service trả về response phù hợp. Với một XSD khác, công cụ có thể sinh `JAXBElement<SubmitOrderRequestType>` thay cho lớp root có `@XmlRootElement`; lúc đó chữ ký endpoint và cách marshal phải điều chỉnh theo lớp thực sự được sinh ra.

Endpoint nên chuyển dữ liệu sang model nghiệp vụ sau khi request hợp lệ, xử lý lệnh và ánh xạ kết quả trở lại response của hợp đồng.

### Bước 4: Kiểm tra XSD ở biên SOAP

Một cách cấu hình Spring-WS là đăng ký `PayloadValidatingInterceptor` để xác thực payload theo schema:

~~~java
@Configuration
@EnableWs
public class WebServiceConfig implements WsConfigurer {

    private final XsdSchema ordersSchema;

    public WebServiceConfig(XsdSchema ordersSchema) {
        this.ordersSchema = ordersSchema;
    }

    @Override
    public void addInterceptors(List<EndpointInterceptor> interceptors) {
        PayloadValidatingInterceptor validator =
            new PayloadValidatingInterceptor();

        validator.setXsdSchema(ordersSchema);
        validator.setValidateRequest(true);
        validator.setValidateResponse(true);

        interceptors.add(validator);
    }
}
~~~

Đoạn mã minh họa giả định `XsdSchema` đã được tạo thành Spring bean và các import Spring-WS tương ứng đã có. Với dịch vụ thực tế, cấu hình schema có thể gồm nhiều XSD import/include; cần bảo đảm validator nắm đủ tập schema của contract.

Khi payload sai cấu trúc hoặc vi phạm XSD, cần xử lý nhất quán bằng cơ chế SOAP Fault/phản hồi lỗi phù hợp. Schema validation bổ sung cho kiểm tra nghiệp vụ; ví dụ XSD có thể biết `quantity > 0`, nhưng không tự biết SKU còn hàng hay khách hàng được phép đặt hàng.

### Bước 5: Tách SOAP binding khỏi domain model

Một kiến trúc thường dễ duy trì hơn:

~~~text
SOAP XML / WSDL / XSD
        |
   JAXB binding
        |
Endpoint + mapper
        |
Application service
        |
  Domain model
~~~

Cách tách này cho phép domain model dùng những kiểu Java phù hợp (`Instant`, value object, enum nghiệp vụ...) trong khi lớp SOAP binding giữ đúng ý nghĩa XML cần trao đổi. Nếu schema cần versioning, ảnh hưởng có thể được cô lập ở endpoint, mapper và lớp binding.

## 6. Các tình huống dễ gặp lỗi khi tích hợp

| Tình huống | Hiểu nhầm phổ biến | Cách xử lý |
|---|---|---|
| Element `minOccurs="0" nillable="true"` | Cứ dùng một field `String` là đủ | Quy định rõ ý nghĩa absent/nil/empty; chọn binding giữ được trạng thái nếu nghiệp vụ cần |
| `xs:positiveInteger` | Java `int`/ `BigInteger` luôn phù hợp | Xác thực XSD; kiểm tra thêm giới hạn nghiệp vụ |
| `xs:sequence` / `xs:choice` | Property Java có thể tùy ý kết hợp | Dựa trên schema, cấu trúc JAXB và kiểm thử từng nhánh |
| `xs:decimal` | Dùng `double` cho mọi số | Ưu tiên `BigDecimal` với tiền; định nghĩa scale/rounding phù hợp |
| `xs:dateTime` | Mọi datetime đều là `Instant` | Xác định có timezone hay không; dùng adapter rõ ràng khi cần |
| Hai object cùng identity | XML tự lưu được shared reference | Thiết kế `ID`/`IDREF` khi cần; tránh lộ nguyên object graph |
| `xs:any` / mixed content | Mọi nội dung đều có class Java cố định | Dùng cơ chế DOM/extension phù hợp và xác định chính sách xử lý |
| Đổi class/package Java | WSDL tự tương thích | So sánh QName/XSD/WSDL và kiểm thử từ SOAP client độc lập |
| JAXB marshal thành công | XML chắc chắn hợp XSD và nghiệp vụ | Bật validation; bổ sung domain validation; test trường hợp sai |

Một lỗi thực tế đặc biệt khó tìm là **schema hợp lệ nhưng dữ liệu bị mất nghĩa**. Ví dụ request cập nhật có `deliveryNote` vắng mặt để giữ nguyên giá trị, nhưng mapper biến nó thành `null` rồi service hiểu là “xóa ghi chú”. XML có thể hoàn toàn hợp lệ và unmarshalling vẫn thành công, trong khi kết quả nghiệp vụ lại sai. Đây là lý do phải kiểm tra ngữ nghĩa, không chỉ kiểm tra XML parse được.

## 7. Cách kiểm thử để phát hiện khoảng cách ánh xạ

Với một SOAP contract quan trọng, nên có các kiểm thử tối thiểu sau:

1. **Contract validation:** Kiểm tra XML request/response với XSD được công bố, gồm cả mẫu hợp lệ và không hợp lệ (thiếu element bắt buộc, sai thứ tự, sai facet, sai QName).
2. **Phân biệt absent/nil/empty:** Tạo ba SOAP payload cho trường optional-nillable; xác nhận binding và nghiệp vụ xử lý theo đúng ý nghĩa đã chọn.
3. **Cardinality và choice:** Test danh sách rỗng, một phần tử, nhiều phần tử; test từng nhánh `xs:choice` và tình huống xuất hiện đồng thời nhiều nhánh.
4. **Kiểu số/thời gian:** Test số thập phân có precision lớn, timezone có/không có offset, các mốc thời gian biên.
5. **Round-trip theo ngữ nghĩa:** Marshal rồi unmarshal và so sánh dữ liệu có ý nghĩa; không yêu cầu XML giống từng byte nếu contract không bắt buộc dạng lexical.
6. **Tương thích đa nền tảng:** Dùng sample SOAP hoặc client độc lập với Java để xác nhận QName, namespace, cấu trúc và SOAP Fault; tránh chỉ kiểm thử hai phía đều dùng cùng lớp JAXB sinh ra.
7. **Thay đổi hợp đồng:** Khi nâng version XSD/WSDL, chạy lại các contract test với client hiện hữu hoặc bộ thông điệp đại diện.

Đối với XML từ bên ngoài, cũng cần cấu hình parser và pipeline SOAP an toàn (chẳng hạn hạn chế truy xuất thực thể ngoài và tài nguyên ngoài theo chính sách bảo mật), cùng những yêu cầu chữ ký/chứng chỉ/WS-Security nếu hệ thống tích hợp đòi hỏi. Các biện pháp này nằm ngoài bài toán Java–XML mapping, nhưng góp phần làm contract-first SOAP service vận hành ổn định.

## 8. Khi nào ánh xạ gần như trực tiếp là đủ?

Với XML đơn giản, chỉ gồm các element có kiểu cơ bản, cây không có vòng tham chiếu, không dùng mixed content/choice phức tạp, và không yêu cầu phân biệt nhiều trạng thái optional, JAXB thường cho trải nghiệm gần như ánh xạ trực tiếp.

Ví dụ:

~~~xml
<GetBalanceRequest xmlns="urn:example:account:v1">
    <accountId>A-100</accountId>
</GetBalanceRequest>
~~~

Một lớp binding với `accountId` kiểu `String` có thể thể hiện khá trọn vẹn phần payload liên quan. Tuy nhiên, ngay trong ví dụ đơn giản này, QName `{urn:example:account:v1}GetBalanceRequest`, quy tắc có mặt của `accountId`, và các yêu cầu bên ngoài payload (SOAP operation, fault, bảo mật) vẫn thuộc về hợp đồng XML/WSDL.

Khi mô hình phức tạp hơn, sự khác biệt tăng lên. Lúc đó hãy giữ XSD/WSDL làm nguồn sự thật cho giao diện SOAP, dùng JAXB để chuyển đổi, validate ở biên và chủ động ánh xạ sang model Java phù hợp với nghiệp vụ.

## 9. Ghi nhớ

- **Java object model** mô tả đối tượng, tham chiếu và hành vi; **XML/XSD** mô tả tài liệu, QName, thứ tự, số lần xuất hiện, nil và các ràng buộc dữ liệu.
- **JAXB là công cụ binding**, không phải bằng chứng rằng mọi trạng thái Java tương ứng một-một với một trạng thái XML hợp lệ.
- Những điểm cần kiểm soát rõ nhất là **namespace/QName**, **absent–nil–empty**, **sequence/choice/cardinality**, **schema facets**, **object identity**, **polymorphism** và **kiểu thời gian/số**.
- Với Spring-WS, hướng **contract-first + JAXB binding + XML Schema validation + mapping sang domain model + interoperability test** giúp hạn chế lỗi tích hợp khó phát hiện giữa các hệ thống doanh nghiệp.

Câu hỏi tự kiểm tra: *Nếu một SOAP request có element `deliveryNote` mang `minOccurs="0" nillable="true"`, bạn sẽ thiết kế lớp binding và phép ánh xạ nghiệp vụ thế nào để phân biệt “không thay đổi ghi chú”, “xóa ghi chú” và “đặt ghi chú thành chuỗi rỗng”?*
