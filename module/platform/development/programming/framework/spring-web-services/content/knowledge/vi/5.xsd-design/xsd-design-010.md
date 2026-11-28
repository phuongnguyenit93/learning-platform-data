# Kiểu mở rộng, kiểu hạn chế và đánh đổi khi dùng kế thừa trong schema

> **Chương:** Thiết kế XSD  
> **Bối cảnh:** Thiết kế hợp đồng SOAP theo hướng contract-first với Spring Web Services (Spring-WS), XSD/WSDL, JAXB, endpoint, SOAP client và yêu cầu tương thích doanh nghiệp.

## 1. Mục tiêu và bản chất của kế thừa trong XSD

XML Schema Definition (XSD) cho phép định nghĩa kiểu mới dựa trên kiểu đã có, gọi là **type derivation**. Hai cơ chế cốt lõi:

- **`xs:extension` (mở rộng):** giữ nội dung của kiểu cơ sở rồi bổ sung nội dung được phép, chẳng hạn một request có `requestId` và request chuyên biệt bổ sung `orderId`.
- **`xs:restriction` (hạn chế):** thu hẹp tập giá trị hoặc cấu trúc XML được phép, chẳng hạn một số nguyên dương bị giới hạn từ 1 đến 100, hoặc một field vốn tùy chọn trở thành bắt buộc.

Kế thừa kiểu trong XSD **không đồng nhất** với Java `extends`. XSD mô tả tập XML instance hợp lệ; JAXB ánh xạ schema thành Java object; còn Spring-WS và SOAP client trao đổi XML thực tế qua WSDL contract. Một model Java biên dịch thành công không bảo đảm XML thỏa schema hoặc client cũ tương thích.

Bài học nhằm giúp bạn đọc, thiết kế và kiểm thử kiểu dẫn xuất; hiểu quy tắc về thứ tự phần tử, ràng buộc giá trị, namespace, đa hình XML; đánh giá lợi ích tái sử dụng so với chi phí versioning và tương thích.

## 2. Phân loại simple type và complex type

| Nhóm | Nội dung | Dẫn xuất thường gặp |
|---|---|---|
| **Simple type** | Một giá trị text như chuỗi, số, ngày, enum; không có phần tử con hay attribute riêng | `xs:restriction` với facet, hoặc `xs:list`, `xs:union` |
| **Complex type có complex content** | Các phần tử con và attribute | `xs:complexContent` chứa `xs:extension` hoặc `xs:restriction` |
| **Complex type có simple content** | Một giá trị text có thể kèm attribute | `xs:simpleContent` chứa `xs:extension` hoặc `xs:restriction` |

Không dùng `xs:extension` trực tiếp trên simple type để thêm một child element. Ví dụ cần số tiền đi kèm thuộc tính currency thì dùng complex type có **simple content**; nếu cần hai element `amount` và `currency` thì dùng **complex content**.

~~~mermaid
flowchart TD
    A["XSD named type"] --> B["Simple type"]
    A --> C["Complex type"]
    B --> D["Restriction: pattern, enum, min/max"]
    C --> E["Complex content extension: thêm cấu trúc"]
    C --> F["Complex content restriction: siết cấu trúc"]
    B --> G["Simple content extension: giá trị + attribute"]
~~~

Phân biệt **global element** (phần tử khai báo trực tiếp trong `xs:schema` và có thể được WSDL tham chiếu), **named type** (kiểu có `name` để tái sử dụng), và **QName** (namespace URI + local name). Type và element có thể có tên khác nhau; prefix XML chỉ là bí danh namespace.

## 3. Mở rộng complex type bằng xs:extension

### 3.1. Ví dụ XSD từ một SOAP request

Giả sử mọi request cần `requestId`; request tra cứu đơn hàng có thêm `orderId`. Schema XSD 1.0:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:tns="urn:demo:orders:v1"
           targetNamespace="urn:demo:orders:v1"
           elementFormDefault="qualified">

  <xs:complexType name="BaseRequestType">
    <xs:sequence>
      <xs:element name="requestId" type="xs:string"/>
    </xs:sequence>
  </xs:complexType>

  <xs:complexType name="GetOrderRequestType">
    <xs:complexContent>
      <xs:extension base="tns:BaseRequestType">
        <xs:sequence>
          <xs:element name="orderId" type="xs:string"/>
        </xs:sequence>
        <xs:attribute name="apiVersion"
                      type="xs:string" use="optional"/>
      </xs:extension>
    </xs:complexContent>
  </xs:complexType>

  <xs:element name="GetOrderRequest"
              type="tns:GetOrderRequestType"/>
</xs:schema>
~~~

XML payload hợp lệ:

~~~xml
<ord:GetOrderRequest xmlns:ord="urn:demo:orders:v1"
                     apiVersion="1">
  <ord:requestId>REQ-001</ord:requestId>
  <ord:orderId>ORD-1001</ord:orderId>
</ord:GetOrderRequest>
~~~

Giải thích:

1. `GetOrderRequest` là **global element**, mang type `GetOrderRequestType`. Không cần thêm `xsi:type` vì element đã khai báo trực tiếp kiểu dẫn xuất.
2. Derived type có nội dung từ base, rồi **nối thêm** `orderId`. Trong `xs:sequence`, thứ tự phải là `requestId` trước `orderId`; đảo ngược có thể khiến XML bị từ chối.
3. Với `elementFormDefault="qualified"`, element con là `ord:requestId` và `ord:orderId`. Attribute `apiVersion` vẫn không mang namespace theo mặc định khi `attributeFormDefault` chưa được đổi.
4. Extension chỉ thay đổi **type content**, không tự tạo SOAP operation mới hoặc làm đổi QName của element root.

### 3.2. Extension có gì và không có gì?

| Mong muốn | Extension có làm trực tiếp được không? | Vì sao |
|---|---|---|
| Thêm `orderId` sau `requestId` | Có | Nối thêm cấu trúc derived type |
| Thêm attribute `apiVersion` | Có | Theo quy tắc attribute của extension |
| Xóa `requestId` bắt buộc | Không | Derived type vẫn mang nội dung từ base |
| Đổi `requestId` thành tùy chọn | Không | Extension không làm yếu ràng buộc base |
| Đổi type của một field inherited theo kiểu override Java | Không | Phải cân nhắc restriction hoặc schema mới |
| Chèn phần tử trước các phần tử của base trong sequence | Không theo extension thông thường | Nội dung bổ sung đứng sau base sequence |

Một base chứa nhiều field bắt buộc trở thành gánh nặng đối với mọi kiểu dẫn xuất. Base nên nhỏ, mang ý nghĩa nghiệp vụ rõ và ít thay đổi.

### 3.3. Simple content extension: giá trị có thuộc tính

Dữ liệu giá tiền có thể là một số thập phân kèm mã tiền tệ:

~~~xml
<xs:complexType name="PriceType">
  <xs:simpleContent>
    <xs:extension base="xs:decimal">
      <xs:attribute name="currency" type="xs:string"
                    use="required"/>
    </xs:extension>
  </xs:simpleContent>
</xs:complexType>

<xs:element name="price" type="tns:PriceType"/>
~~~

Instance:

~~~xml
<ord:price xmlns:ord="urn:demo:orders:v1"
           currency="VND">250000</ord:price>
~~~

Đây là text `250000` nằm trực tiếp trong element `price`, **khác** cấu trúc có child `<amount>`. Nếu hợp đồng yêu cầu element con, phải định nghĩa complex content riêng.

## 4. Hạn chế simple type bằng xs:restriction

Restriction làm tập giá trị được chấp nhận **chặt hơn**. Ví dụ mã đơn hàng dài 4–24 ký tự, chỉ dùng chữ Latin in hoa, số hoặc dấu gạch nối:

~~~xml
<xs:simpleType name="OrderIdType">
  <xs:restriction base="xs:string">
    <xs:minLength value="4"/>
    <xs:maxLength value="24"/>
    <xs:pattern value="[A-Z0-9-]+"/>
  </xs:restriction>
</xs:simpleType>
~~~

| Giá trị | Hợp lệ? | Lý do |
|---|---|---|
| `ORD-1001` | Có | Đủ độ dài, đúng bộ ký tự |
| `A12` | Không | Quá ngắn |
| `ord-1001` | Không | Chứa chữ thường |
| `ORD 1001` | Không | Chứa khoảng trắng |

Regex XSD có cú pháp và quy tắc matching riêng, không nhất thiết giống biểu thức Java regex. Test bằng XML Schema validator đúng phiên bản.

Hạn chế giá trị trạng thái:

~~~xml
<xs:simpleType name="OrderStatusType">
  <xs:restriction base="xs:string">
    <xs:enumeration value="NEW"/>
    <xs:enumeration value="PROCESSING"/>
    <xs:enumeration value="DONE"/>
  </xs:restriction>
</xs:simpleType>
~~~

Hạn chế số nguyên dương:

~~~xml
<xs:simpleType name="PageSizeType">
  <xs:restriction base="xs:positiveInteger">
    <xs:maxInclusive value="100"/>
  </xs:restriction>
</xs:simpleType>
~~~

`PageSizeType` chỉ nhận 1–100. **Không thể thêm giá trị enum mới bằng restriction** nếu giá trị ấy vốn không hợp lệ với enum base: restriction là thu hẹp, không phải mở rộng miền giá trị.

Một lưu ý quan trọng với JAXB: setter Java có thể chấp nhận chuỗi sai pattern hoặc số 200 dù schema giới hạn 100. **Marshalling/unmarshalling thành công chưa chứng minh XML đã qua schema validation.**

## 5. Hạn chế complex type bằng xs:restriction

Với complex content, restriction tạo một biến thể XML chặt hơn nhưng phải tuân thủ **quy tắc dẫn xuất cấu trúc của XSD**, phức tạp hơn việc thêm facet cho simple type.

### 5.1. Ví dụ: field tùy chọn thành bắt buộc, số có giới hạn

Schema XSD 1.0:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:tns="urn:demo:search:v1"
           targetNamespace="urn:demo:search:v1"
           elementFormDefault="qualified">

  <xs:simpleType name="PageSizeType">
    <xs:restriction base="xs:positiveInteger">
      <xs:maxInclusive value="100"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:complexType name="SearchCriteriaType">
    <xs:sequence>
      <xs:element name="query" type="xs:string"/>
      <xs:element name="pageSize"
                  type="xs:positiveInteger"
                  minOccurs="0"/>
    </xs:sequence>
  </xs:complexType>

  <xs:complexType name="StrictSearchCriteriaType">
    <xs:complexContent>
      <xs:restriction base="tns:SearchCriteriaType">
        <xs:sequence>
          <xs:element name="query" type="xs:string"/>
          <xs:element name="pageSize"
                      type="tns:PageSizeType"
                      minOccurs="1"/>
        </xs:sequence>
      </xs:restriction>
    </xs:complexContent>
  </xs:complexType>

  <xs:element name="SearchOrdersRequest"
              type="tns:StrictSearchCriteriaType"/>
</xs:schema>
~~~

XML hợp lệ:

~~~xml
<s:SearchOrdersRequest xmlns:s="urn:demo:search:v1">
  <s:query>ORD-</s:query>
  <s:pageSize>50</s:pageSize>
</s:SearchOrdersRequest>
~~~

Base `SearchCriteriaType` cho phép bỏ `pageSize`; derived yêu cầu field và chỉ chấp nhận giá trị 1–100. XML thiếu `pageSize` hoặc có `pageSize=200` không hợp lệ theo derived type. Khi khai báo restriction, cần **tái khai báo phần cấu trúc được giữ lại** theo quy tắc phù hợp với base; khác extension, không thể chỉ ghi một field muốn đổi rồi mong phần base tự nối vào.

### 5.2. Các ràng buộc cơ bản

- Có thể tăng `minOccurs` hoặc giảm `maxOccurs` khi vẫn tạo một particle restriction hợp lệ; không được làm ngược lại tùy tiện.
- Có thể dùng kiểu của phần tử được **dẫn xuất hạn chế hợp lệ** từ kiểu phần tử tương ứng trong base.
- Không thể bỏ field bắt buộc của base, tự thêm field không được base cho phép, hoặc tùy tiện thay thứ tự `xs:sequence`.
- Restriction trên cấu trúc có `xs:choice`, wildcard, nested model groups và attributes có nhiều quy tắc bổ sung. Một cấu trúc nhìn “giống tập con” vẫn có thể bị XSD validator báo lỗi *not a valid restriction of base type*.

Vì complex content restriction có khả năng làm mã sinh JAXB khó hiểu hoặc không như mong đợi, cần biên dịch schema và sinh client thử trước khi chọn nó cho hợp đồng doanh nghiệp. Với yêu cầu đơn giản, **simple type restriction cho giá trị cụ thể** thường dễ bảo trì hơn.

## 6. Đa hình XML qua xsi:type

Trường hợp phổ biến ở SOAP contract-first: element được khai báo với kiểu dẫn xuất cụ thể, như:

~~~xml
<xs:element name="GetOrderRequest"
            type="tns:GetOrderRequestType"/>
~~~

Khi đó XML có thẻ `GetOrderRequest`, không cần khai báo kiểu động bằng `xsi:type`.

Trường hợp khác: element được khai báo theo base type, nhưng một instance muốn chứa nội dung derived. Nếu schema ở mục 3 bổ sung:

~~~xml
<xs:element name="GenericRequest"
            type="tns:BaseRequestType"/>
~~~

thì một XML instance có thể chỉ định derived type:

~~~xml
<ord:GenericRequest
    xmlns:ord="urn:demo:orders:v1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:type="ord:GetOrderRequestType">
  <ord:requestId>REQ-001</ord:requestId>
  <ord:orderId>ORD-1001</ord:orderId>
</ord:GenericRequest>
~~~

Điều kiện cần: schema phía nhận **biết** `GetOrderRequestType`, nó hợp lệ khi dẫn xuất từ `BaseRequestType`, quá trình thay thế kiểu không bị chặn và XML thỏa các ràng buộc của derived type. Nếu bỏ `xsi:type` trong trường hợp `GenericRequest` khai báo type base, phần tử `orderId` bổ sung không tự động được chấp nhận.

| Cơ chế | Đặt ở đâu? | Công dụng |
|---|---|---|
| `final` | Khai báo type | Hạn chế cách **dẫn xuất kiểu mới** từ type đó |
| `block` | Khai báo element | Ngăn một số cách thay thế type/substitution tại vị trí element |
| `abstract="true"` | Type hoặc element theo quy tắc của XSD | Không dùng trực tiếp kiểu/phần tử trừu tượng |
| `xsi:type` | XML instance | Chọn kiểu động dẫn xuất khi schema và ràng buộc cho phép |

**Không mặc định dùng xsi:type chỉ vì Java có subclass.** Client JAXB hoặc .NET đã sinh mã từ WSDL cũ có thể không biết derived type mới; cần thực nghiệm với đúng công cụ và contract phía đối tác.

## 7. Từ XSD type sang WSDL message và SOAP Body

WSDL 1.1 trong thiết kế document/literal thường tham chiếu **global element**:

~~~xml
<wsdl:message name="GetOrderRequestMessage">
  <wsdl:part name="parameters"
             element="tns:GetOrderRequest"/>
</wsdl:message>
~~~

Payload SOAP 1.1 tương ứng với XSD extension:

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:demo:orders:v1">
  <soapenv:Body>
    <ord:GetOrderRequest>
      <ord:requestId>REQ-001</ord:requestId>
      <ord:orderId>ORD-1001</ord:orderId>
    </ord:GetOrderRequest>
  </soapenv:Body>
</soapenv:Envelope>
~~~

Quan hệ cần nắm:

1. **Global element** `GetOrderRequest` quyết định QName của payload root: `{urn:demo:orders:v1}GetOrderRequest`.
2. **Derived type** `GetOrderRequestType` quyết định field và thứ tự hợp lệ bên trong payload.
3. **WSDL operation** quy định thao tác của dịch vụ; tên operation không tự tạo kiểu dẫn xuất hoặc thay QName của element.
4. **Java/JAXB model** mô tả nội dung XML bằng các class/property nhưng không thay thế XSD contract.

Một thay đổi ở `BaseRequestType` có thể ảnh hưởng **nhiều SOAP operation** vốn dùng các derived type từ nó, dù các tên operation và tên element trong WSDL không đổi. Khi review contract, cần xem cả các file XSD được `xs:include` hoặc `xs:import`, không chỉ diff của WSDL chính.

## 8. JAXB mapping và endpoint Spring-WS

### 8.1. Schema inheritance có thể thành Java inheritance

Bộ sinh JAXB/XJC có thể ánh xạ complex content extension sang các lớp như sau:

~~~java
// Minh họa hình dạng class, không phải mã sinh đầy đủ.
public class BaseRequestType {
    protected String requestId;

    public String getRequestId() { return requestId; }
    public void setRequestId(String value) { requestId = value; }
}

public class GetOrderRequestType extends BaseRequestType {
    protected String orderId;

    public String getOrderId() { return orderId; }
    public void setOrderId(String value) { orderId = value; }
}
~~~

Trong thực tế, JAXB bổ sung annotation như `@XmlType`, `@XmlElement`, `@XmlAttribute`; tùy XSD và tool có thể sinh `JAXBElement` qua `ObjectFactory` thay vì class có `@XmlRootElement`. **Complex content restriction không bảo đảm biến thành Java subclass theo cách giống extension**. Không suy ra cấu trúc Java từ XML bằng tưởng tượng; hãy sinh mã và kiểm tra interface, annotation cùng XML được marshal.

Ví dụ với `PageSizeType`, generated setter có thể nhận `200` mà không ném exception: JAXB unmarshalling/marshalling thành công chưa đồng nghĩa **schema validation** thành công. Facet về pattern, enum, độ dài, giá trị tối đa và cấu trúc phức tạp cần được kiểm chứng bằng validator.

### 8.2. Spring-WS dispatch theo payload element

~~~java
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;

@Endpoint
public class OrderEndpoint {
    private static final String NS = "urn:demo:orders:v1";

    @PayloadRoot(namespace = NS, localPart = "GetOrderRequest")
    @ResponsePayload
    public GetOrderResponse getOrder(
            @RequestPayload GetOrderRequest request) {
        return orderService.findOrder(request);
    }
}
~~~

Đây là phần minh họa ranh giới endpoint: `orderService`, response schema và các class JAXB cần định nghĩa trong ứng dụng thực; một số thiết kế XSD sẽ sinh `GetOrderRequestType` và `JAXBElement<GetOrderRequestType>` thay cho class `GetOrderRequest`. Cần dùng đúng signature, endpoint adapter và cấu hình XML binding của phiên bản Spring-WS đang chạy.

`@PayloadRoot` nhận diện **QName của element SOAP Body root**, không dựa trên tên type hay tên Java method. Nếu đổi tên global element mà giữ type thì giá trị `localPart` vẫn phải cập nhật theo contract.

Phía SOAP client dùng `WebServiceTemplate` hoặc proxy JAX-WS/CXF đều cần gửi XML có QName và schema đúng. Spring-WS không buộc mọi client phải viết bằng Spring; CXF/JAX-WS và .NET vẫn có thể giao tiếp nếu thống nhất WSDL/XSD và các chính sách vận hành.

### 8.3. XSD validation trong Spring-WS

Spring-WS hỗ trợ `PayloadValidatingInterceptor`, ví dụ cấu hình minh họa:

~~~java
@Configuration
@EnableWs
public class WsConfig implements WsConfigurer {
    @Bean
    public XsdSchema ordersSchema() {
        return new SimpleXsdSchema(
                new ClassPathResource("orders.xsd"));
    }

    @Override
    public void addInterceptors(
            List<EndpointInterceptor> interceptors) {
        PayloadValidatingInterceptor interceptor =
                new PayloadValidatingInterceptor();
        interceptor.setXsdSchema(ordersSchema());
        interceptor.setValidateRequest(true);
        interceptor.setValidateResponse(true);
        interceptors.add(interceptor);
    }
}
~~~

Cần import lớp, khai báo dependency và đăng ký servlet đúng phiên bản Spring Framework/Spring-WS. Đây chưa phải ứng dụng chạy độc lập. Nếu schema được chia nhiều file hoặc namespace, phải bảo đảm các import/include được giải quyết đúng. Khi bật response validation, mọi response/fault hợp lệ cần được kiểm tra và xử lý lỗi phù hợp.

**Schema validation** giúp kiểm tra cấu trúc, kiểu, facet và thứ tự XML; **validation nghiệp vụ** như đơn hàng tồn tại, hạn mức hoặc quyền truy cập thuộc business service. Chúng bổ sung, không thay thế nhau.

## 9. Khi nào composition tốt hơn kế thừa?

Nếu nhiều nghiệp vụ chỉ chia sẻ nhóm metadata, chưa chắc nên tạo một cây `BaseRequestType` nhiều tầng. **Composition** là nhúng type chung như một element con:

~~~xml
<xs:complexType name="RequestMetadataType">
  <xs:sequence>
    <xs:element name="requestId" type="xs:string"/>
    <xs:element name="traceId" type="xs:string"
                minOccurs="0"/>
  </xs:sequence>
</xs:complexType>

<xs:complexType name="GetOrderRequestType">
  <xs:sequence>
    <xs:element name="metadata"
                type="tns:RequestMetadataType"/>
    <xs:element name="orderId" type="xs:string"/>
  </xs:sequence>
</xs:complexType>
~~~

XML tương ứng:

~~~xml
<ord:GetOrderRequest xmlns:ord="urn:demo:orders:v1">
  <ord:metadata>
    <ord:requestId>REQ-001</ord:requestId>
    <ord:traceId>TRACE-99</ord:traceId>
  </ord:metadata>
  <ord:orderId>ORD-1001</ord:orderId>
</ord:GetOrderRequest>
~~~

| Tiêu chí | Extension / restriction | Composition |
|---|---|---|
| Ý nghĩa | “A là biến thể của B” | “A có thành phần B” |
| XML on the wire | Field inherited thường cùng cấp field mới | Dữ liệu dùng chung nằm dưới element lồng nhau |
| JAXB mapping | Có thể biểu diễn Java inheritance | Thường biểu diễn bằng một property object |
| Phụ thuộc | Tuân theo quy tắc type derivation | Tuân theo kiểu được nhúng |
| Trường hợp tốt | Subtype ổn định về ngữ nghĩa | Tái sử dụng metadata, địa chỉ hoặc nhóm field chung |

Composition cũng có phụ thuộc: nếu `RequestMetadataType` đổi, mọi message dùng nó đều có thể bị ảnh hưởng. Ưu điểm là ranh giới dữ liệu rõ, dễ hiểu hơn khi không thực sự có quan hệ subtype.

**Không tự chuyển inheritance ↔ composition ở một service đang hoạt động.** Hình dạng XML thay đổi, nên phải đánh giá là thay đổi hợp đồng và phối hợp nâng version với client.

## 10. Đánh đổi khi dùng kế thừa trong schema doanh nghiệp

### Lợi ích

- **Tái sử dụng:** không phải định nghĩa lại các field ổn định của request/response.
- **Nhất quán:** ràng buộc tại một base type có thể áp dụng cho nhiều derived type.
- **Mô hình rõ quan hệ:** type derivation diễn đạt subtype mạnh hơn việc copy-paste XML fields.
- **Hỗ trợ tooling:** validator có thể xác minh quan hệ base/derived theo XSD.

### Chi phí

- **Coupling lan rộng:** sửa base có thể thay đổi nhiều request/response vốn dùng derived type khác nhau.
- **Thứ tự sequence cố định:** extension đặt field bổ sung sau phần nội dung base, gây khó khăn khi muốn thêm field vào giữa.
- **Complex restriction khó bảo trì:** định nghĩa lại particle và tuân thủ quy tắc dẫn xuất không đơn giản; công cụ code generation có thể khác nhau.
- **Đa hình XML phức tạp:** `xsi:type` đòi hỏi client biết kiểu dẫn xuất; client cũ có thể không hiểu.
- **Khó versioning:** không dễ nâng một operation mà không tác động các operation còn lại dùng base.
- **Khó lần theo contract:** người đọc phải theo chuỗi type, import/include schema mới biết XML instance thực.

Đây là lý do không nên tạo một `EnterpriseBaseRequest` chứa rất nhiều field tùy tiện chỉ để giảm lặp. Base type tốt cần có **ý nghĩa nghiệp vụ rõ, phạm vi ổn định và chủ sở hữu**. Composition hoặc type độc lập phù hợp hơn khi các operation không có quan hệ “is-a” thật.

## 11. Khả năng tương thích và thay đổi phiên bản

Giả sử schema v1 có base chỉ gồm `requestId`. Schema v2 thêm `tenantId` vào cuối sequence:

~~~xml
<xs:element name="tenantId" type="xs:string"
            minOccurs="0"/>
~~~

Field optional có thể giúp client cũ vẫn gửi request không có `tenantId` đến server dùng schema mới. Tuy nhiên, nếu server gửi response **có** field mới, client dùng schema cũ có thể từ chối element lạ. Vì vậy, **optional không tự động bảo đảm tương thích hai chiều**.

| Thay đổi | Tác động thường gặp |
|---|---|
| Thêm field **bắt buộc** vào base | Request cũ thiếu field không hợp lệ với schema mới |
| Thêm field **tùy chọn** vào base | Request cũ có thể hợp lệ; response mới vẫn có thể gây lỗi ở client cũ |
| Siết `minLength`, `maxInclusive`, `pattern` | Giá trị đã hợp lệ có thể bị từ chối |
| Thay enum hoặc thêm giá trị trạng thái | Client có thể không xử lý được trạng thái mới; xóa giá trị phá hợp đồng cũ |
| Đổi thứ tự `xs:sequence` | XML theo thứ tự cũ có thể không qua schema validation |
| Đổi global element hoặc namespace | Thay QName payload, có thể làm endpoint không dispatch |
| Đổi inheritance sang composition | Đổi cấu trúc XML trên wire |
| Thêm kiểu động qua `xsi:type` | Client cũ có thể chưa biết derived type |

**Nguyên tắc:** version cả XSD/WSDL như một hợp đồng công khai. Nếu bắt buộc thay đổi breaking, công bố phiên bản mới (namespace, operation, endpoint tùy thỏa thuận), duy trì v1 trong giai đoạn migration, và test với client thật. Đừng đánh giá thay đổi schema qua số dòng diff; phải xem ảnh hưởng lên mọi derived type và XML đã ký kết.

## 12. SOAP Fault, XML security, WS-Security và chứng chỉ

Type derivation ảnh hưởng trực tiếp đến XML validation nhưng **không tự giải quyết** bảo mật và lỗi ở mức SOAP. Các yêu cầu thường gặp:

- **Schema validation:** restriction có thể khiến XML bị từ chối trước khi vào endpoint. Cần chuyển lỗi phù hợp thành SOAP Fault và không phơi bày Java stack trace.
- **SOAP Fault:** mã lỗi, reason và detail cần ổn định theo WSDL và quy ước đối tác. Mô hình lỗi nghiệp vụ phải được phân biệt với lỗi XML không hợp lệ.
- **EndpointInterceptor / validation:** Spring-WS cung cấp interceptor và fault resolver để xử lý các quan tâm xuyên suốt. Luồng xử lý lỗi phải được thử thực tế.
- **XML security:** bảo vệ parser khỏi XXE, external entity, schema import không tin cậy; đặt giới hạn kích thước, độ sâu, số lượng phần tử và thời gian xử lý. XSD hợp lệ không đồng nghĩa an toàn tài nguyên.
- **WS-Security:** chữ ký XML, mã hóa, timestamp và token ở cấp SOAP message. Đổi cấu trúc phần tử có thể tác động phần tham chiếu chữ ký/canonicalization.
- **Chứng chỉ và HTTPS:** cấu hình keystore, truststore, xác minh chứng chỉ, thời hạn và rotation. TLS bảo vệ kênh truyền, còn WS-Security bảo vệ nội dung thông điệp theo policy phù hợp.
- **Client tương thích:** dùng một client độc lập như JAX-WS/CXF hoặc .NET để thử đúng XML, SOAP Fault và WS-SecurityPolicy mà đối tác yêu cầu.

Ví dụ: server đổi một base response để thêm field required trong SOAP Body. Dù server và client đều dùng JAXB, request/response mới có thể không hợp lệ với schema cũ, khiến lỗi validation hoặc chữ ký XML thất bại. Không được coi đó chỉ là thay đổi Java class.

## 13. Quy trình chọn extension, restriction hoặc composition

1. **Chốt hợp đồng XML trước:** xác định global element, QName, thứ tự, field bắt buộc/tùy chọn, SOAP version và WSDL.
2. **Tìm quan hệ nghiệp vụ:** nếu type mới thật sự là biến thể của base ổn định, xem extension; nếu chỉ muốn dùng lại metadata, xem composition.
3. **Giới hạn miền giá trị bằng facet:** ưu tiên simple type restriction cho pattern, enum, khoảng số; dùng complex content restriction khi cần thật và tooling hỗ trợ.
4. **Biên dịch XSD 1.0:** validate schema và các file import/include; không dựa trên suy đoán khi có choice, wildcard, group hay mixed content.
5. **Kiểm thử XML instance:** tạo mẫu đúng/sai cho missing field, min/max, sequence, enum, `xsi:type` và attribute namespace.
6. **Sinh Java binding:** kiểm tra JAXB class, `JAXBElement`, marshalling/unmarshalling, tương thích `javax.*`/`jakarta.*` và runtime Spring-WS/CXF.
7. **Kiểm thử tích hợp:** thử với client độc lập, SOAP fault, WS-Security, TLS, chứng chỉ, endpoint URI và schema validation thực tế.
8. **Lập phương án versioning:** đánh giá mọi operation và đối tác dùng base/shared type trước khi thay đổi hợp đồng.

| Bài toán | Giải pháp nên cân nhắc |
|---|---|
| Một request chuyên biệt cần thêm `orderId` sau `requestId` | `complexContent/extension` |
| Mã đơn hàng phải đúng pattern/độ dài | `simpleType/restriction` |
| Request chuyên biệt buộc `pageSize` có mặt và ≤100 | `complexContent/restriction` với type số hạn chế |
| Nhiều dịch vụ dùng metadata chung, không có quan hệ subtype | Composition với `RequestMetadataType` |
| Đối tác đã có WSDL/XSD chính thức | Giữ contract hiện hữu, không tự viết lại hierarchy |
| Cần thêm trạng thái nghiệp vụ ngoài enum cũ | Đánh giá tác động client và version, không dùng restriction để mở rộng tập |

## 14. Bài tập thực hành có đáp án

### Bài 1 — Thứ tự phần tử

Base type có `requestId`; derived extension thêm `customerId` rồi `orderId` trong `xs:sequence`. Client gửi thứ tự `orderId`, `requestId`, `customerId`. Request hợp lệ không?

**Đáp án:** Không. Cấu trúc derived gồm sequence base trước, sau đó sequence extension, nên phải là `requestId`, `customerId`, `orderId`.

### Bài 2 — Hạn chế số

Base cho phép `pageSize` là `xs:positiveInteger` tùy chọn. Derived yêu cầu field đó bắt buộc và ≤100. Cách nào phù hợp?

**Đáp án:** Complex content restriction có thể siết `minOccurs` từ 0 thành 1 và dùng simple type dẫn xuất từ `xs:positiveInteger` với facet `maxInclusive="100"`. Phải khai báo lại đúng các particle và dùng validator kiểm tra schema.

### Bài 3 — JAXB và facet

Java setter nhận `pageSize=200` dù XSD hạn chế tối đa 100. Điều này chứng minh XSD sai?

**Đáp án:** Không. Setter không bảo đảm facet validation. Cần chạy XSD validation cho XML nhận/gửi và kiểm tra nghiệp vụ riêng.

### Bài 4 — Tương thích hai chiều

Schema v2 thêm `tenantId` optional vào base type. Client v1 vẫn gửi được request cho server v2. Đã có thể tuyên bố hoàn toàn tương thích chưa?

**Đáp án:** Chưa. Client v1 có thể từ chối response v2 chứa field lạ, hoặc gặp lỗi với derived type/`xsi:type` mới. Cần kiểm thử wire format, schema cũ/mới, SOAP Fault và WS-Security.

### Bài 5 — Tránh kế thừa không cần thiết

Ba SOAP service thanh toán, CRM và kho cùng có `traceId` nhưng không cùng bản chất nghiệp vụ. Có nhất thiết tạo `EnterpriseBaseRequest`?

**Đáp án:** Không. Composition qua `RequestMetadataType` thường diễn đạt quan hệ “has-a” rõ hơn và giúp quản lý cấu trúc XML trực quan, dù việc thay đổi shared type vẫn cần versioning.

## 15. Checklist trước khi công bố XSD/WSDL

- [ ] Global element và named type có QName, namespace rõ ràng; `wsdl:part` trỏ đúng payload element.
- [ ] Extension giữ cấu trúc inherited, đúng thứ tự `xs:sequence` và attribute namespace.
- [ ] Restriction siết ràng buộc hợp lệ, không thêm dữ liệu ngoài phần base cho phép.
- [ ] XSD validator chấp nhận mẫu hợp lệ và từ chối mẫu sai về enum, facet, occurrence, thứ tự.
- [ ] Mọi schema import/include được giải quyết đúng, đặc biệt khi hợp đồng chia nhiều file.
- [ ] JAXB model và SOAP client được sinh từ đúng phiên bản schema; marshal/unmarshal đúng XML.
- [ ] Spring-WS endpoint dispatch theo QName của payload root, validation và SOAP Fault hoạt động.
- [ ] Đã kiểm tra mọi derived type khi base type thay đổi; có kế hoạch migration/version nếu breaking.
- [ ] Có thử tích hợp với client độc lập, WS-SecurityPolicy, chứng chỉ, TLS và giới hạn XML parser.
- [ ] Không nhầm schema validation với business authorization hoặc các kiểm tra nghiệp vụ khác.

**Ghi nhớ:** `xs:extension` thêm cấu trúc vào một kiểu cơ sở; `xs:restriction` làm chặt tập XML được chấp nhận. Trong Spring Web Services, mục tiêu cao nhất của thiết kế XSD không phải giảm lặp Java, mà là bảo toàn một **hợp đồng SOAP rõ ràng, kiểm chứng được và tương thích với client** qua nhiều vòng phát triển.
