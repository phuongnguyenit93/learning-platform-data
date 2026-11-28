# Namespace, URI, prefix và tên đầy đủ QName

Trong **Spring Web Services (Spring-WS)**, một thông điệp SOAP được định tuyến và kiểm tra dựa trên cấu trúc XML của nó. Tên phần tử như `CreateOrderRequest` chỉ là một phần của danh tính: hệ thống còn cần biết phần tử thuộc **namespace** nào. Hiểu đúng namespace, URI, prefix và **QName** là nền tảng để thiết kế XSD/WSDL theo hướng **contract-first**, ánh xạ JAXB và tránh lỗi tích hợp khi hai bên dùng các prefix khác nhau.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao hai phần tử cùng tên cục bộ vẫn có thể là hai phần tử khác nhau.
- Phân biệt namespace URI, prefix, local name, QName và cách viết `{namespaceURI}localName`.
- Xác định namespace của phần tử, thuộc tính và giá trị QName khi đọc XML.
- Đối chiếu QName trong payload SOAP, khai báo XSD/WSDL, JAXB và `@PayloadRoot` của Spring-WS.
- Nhận diện lỗi namespace thường gặp và kiểm tra thông điệp từ phía client đến endpoint.

## 1. Vì sao XML cần namespace?

Giả sử doanh nghiệp tích hợp hệ thống bán hàng và kho vận. Cả hai đều dùng tên `id`, nhưng một bên muốn nói mã đơn hàng, bên kia muốn nói mã kiện hàng:

```xml
<order>
    <id>ORD-1024</id>
</order>

<parcel>
    <id>PKG-8899</id>
</parcel>
```

Trong ví dụ đơn giản này, cha của phần tử giúp người đọc suy luận ý nghĩa. Tuy nhiên, khi nhiều hệ thống cùng chia sẻ payload, chỉ dựa vào tên `id` hoặc `status` không đủ để xác định phần tử theo hợp đồng XML. Namespace cung cấp một không gian tên để tránh va chạm.

```xml
<ord:id xmlns:ord="https://example.org/contracts/order/v1">ORD-1024</ord:id>
<ship:id xmlns:ship="https://example.org/contracts/shipping/v1">PKG-8899</ship:id>
```

Hai phần tử đều có **local name** là `id`, nhưng có **namespace URI** khác nhau, nên chúng có **QName** khác nhau.

Về mặt danh tính, một tên phần tử có namespace được xác định bằng cặp:

**(namespace URI, local name)**

Prefix chỉ là cách viết ngắn trong tài liệu XML. Nó không tham gia quyết định hai tên có bằng nhau hay không.

## 2. Phân biệt namespace URI, prefix, local name và QName

Xem đoạn XML sau:

```xml
<ord:CreateOrderRequest
    xmlns:ord="https://example.org/contracts/order/v1">
    <ord:orderId>ORD-1024</ord:orderId>
</ord:CreateOrderRequest>
```

| Khái niệm | Giá trị trong ví dụ | Vai trò |
|---|---|---|
| **Namespace URI** | `https://example.org/contracts/order/v1` | Định danh không gian tên của hợp đồng. |
| **Prefix** | `ord` | Bí danh được khai báo bằng `xmlns:ord`, dùng để viết gọn trong phạm vi XML. |
| **Local name** | `CreateOrderRequest` | Phần tên nằm sau dấu `:`, hoặc toàn bộ tên nếu không có prefix. |
| **QName trong XML** | `ord:CreateOrderRequest` | Tên có prefix được phân giải theo các khai báo namespace đang có hiệu lực. |
| **Tên mở rộng (expanded name)** | `{https://example.org/contracts/order/v1}CreateOrderRequest` | Cách trình bày rõ cặp URI và local name, thường thấy trong thư viện Java và thông báo lỗi. |

**Namespace URI không nhất thiết là URL truy cập được.** Một URI dạng `https://...` có thể trông giống địa chỉ web, nhưng XML dùng nó làm định danh, không yêu cầu máy chủ trả về tài liệu tại địa chỉ ấy. URI dạng `urn:...` cũng hợp lệ nếu hệ thống cùng thống nhất sử dụng.

Cần phân biệt ba thứ dễ bị nhầm:

- **Namespace URI**: danh tính logic của nhóm tên XML.
- **Endpoint URL**: địa chỉ mạng mà SOAP client gửi HTTP request, chẳng hạn `https://api.example.org/ws`.
- **Đường dẫn schema**: vị trí tệp XSD để công cụ tải và kiểm tra hợp đồng, chẳng hạn `schemas/order-v1.xsd`.

Chúng có thể liên quan trong một dự án nhưng không thay thế cho nhau. Đổi endpoint URL không bắt buộc đổi namespace; ngược lại, đổi namespace URI có thể làm thay đổi QName trong payload và phá vỡ tương thích dù tên các phần tử giữ nguyên.

Namespace URI cần được so khớp chính xác. Ví dụ `https://example.org/contracts/order/v1` và `https://example.org/contracts/order/v1/` là hai chuỗi định danh khác nhau.

## 3. Prefix là bí danh có phạm vi, không phải định danh cố định

Hai tài liệu dưới đây biểu diễn cùng tên mở rộng của phần tử gốc:

```xml
<ord:CreateOrderRequest
    xmlns:ord="https://example.org/contracts/order/v1">
    <ord:orderId>ORD-1024</ord:orderId>
</ord:CreateOrderRequest>
```

```xml
<x:CreateOrderRequest
    xmlns:x="https://example.org/contracts/order/v1">
    <x:orderId>ORD-1024</x:orderId>
</x:CreateOrderRequest>
```

Vì `ord` và `x` đều trỏ đến cùng URI, hai phần tử gốc có cùng QName ở dạng mở rộng. SOAP endpoint tuân theo hợp đồng namespace sẽ xử lý chúng như cùng loại thông điệp.

Quy tắc quan trọng:

1. Prefix được khai báo bằng `xmlns:tenPrefix="namespaceURI"`; dùng prefix chưa khai báo khiến tài liệu XML không hợp lệ theo XML Namespaces.
2. Khai báo có hiệu lực trên phần tử chứa nó và các phần tử con, trừ khi bị khai báo lại trong phạm vi con.
3. Cùng prefix có thể được gán URI khác ở một phạm vi con; khi đó ý nghĩa QName cũng thay đổi.
4. Các prefix như `xml` và `xmlns` có quy tắc dành riêng của chuẩn; không tự dùng chúng cho namespace nghiệp vụ.
5. Prefix `tns` trong ví dụ XSD/WSDL chỉ là quy ước viết tắt của “this namespace”, không phải từ khóa đặc biệt.

Ví dụ cần đọc cẩn thận phạm vi:

```xml
<root xmlns:a="urn:example:orders">
    <a:id>ORD-1</a:id>
    <inner xmlns:a="urn:example:shipping">
        <a:id>PKG-1</a:id>
    </inner>
</root>
```

Hai thẻ `a:id` ở hai phạm vi có tên mở rộng khác nhau. Không thể kết luận cùng QName chỉ vì nhìn thấy cùng prefix và local name.

## 4. Default namespace và điểm khác biệt giữa phần tử với thuộc tính

Khai báo `xmlns="..."` thiết lập **default namespace** cho tên **phần tử không có prefix** trong phạm vi đó:

```xml
<CreateOrderRequest xmlns="https://example.org/contracts/order/v1">
    <orderId>ORD-1024</orderId>
</CreateOrderRequest>
```

Ở đây cả `CreateOrderRequest` và `orderId` đều thuộc namespace `https://example.org/contracts/order/v1`. Tên mở rộng tương ứng là:

- `{https://example.org/contracts/order/v1}CreateOrderRequest`
- `{https://example.org/contracts/order/v1}orderId`

**Default namespace không tự áp dụng cho tên thuộc tính không có prefix.** Ví dụ:

```xml
<order xmlns="urn:example:orders"
       xmlns:meta="urn:example:metadata"
       id="A01"
       meta:id="EXT-99">
    <orderId>ORD-1024</orderId>
    <debug xmlns="">no-namespace</debug>
</order>
```

- Phần tử `order` và `orderId` thuộc `urn:example:orders`.
- Thuộc tính `id` nằm trong **namespace rỗng**; thuộc tính `meta:id` thuộc `urn:example:metadata`.
- `xmlns=""` hủy default namespace trong phạm vi `debug`, nên `debug` không thuộc namespace nào.

Khi dùng namespace trên một thuộc tính, phải chỉ rõ prefix, chẳng hạn `meta:id`. Một thuộc tính không có prefix và một thuộc tính có prefix có thể cùng local name nhưng vẫn là hai thuộc tính khác nhau nếu tên mở rộng khác nhau.

### Tên trong giá trị thuộc tính không tự động trở thành QName

Xét khai báo:

```xml
<item xmlns:ord="urn:example:orders" type="ord:OrderType"/>
```

Về mặt cú pháp XML thuần, `type` chỉ chứa một chuỗi ký tự. Chỉ khi đặc tả hoặc schema định nghĩa giá trị này có kiểu **QName** thì bộ xử lý mới phân giải `ord:OrderType` theo khai báo `xmlns:ord`. Các thuộc tính như `xsi:type`, `wsdl:part/@element` hay `ref` trong XSD có ngữ nghĩa QName; các thuộc tính nghiệp vụ tùy ý thì không mặc nhiên có ngữ nghĩa đó.

Để tránh mơ hồ trong các vị trí có giá trị kiểu QName, nên sử dụng một prefix được khai báo rõ ràng.

## 5. QName trong Java: URI và local name mới quyết định tính bằng nhau

Java cung cấp `javax.xml.namespace.QName` (thuộc JDK, vẫn dùng tên package này khi ứng dụng chuyển sang Jakarta XML Binding):

```java
import javax.xml.namespace.QName;

String ns = "https://example.org/contracts/order/v1";

QName first  = new QName(ns, "CreateOrderRequest", "ord");
QName second = new QName(ns, "CreateOrderRequest", "x");

System.out.println(first.equals(second)); // true
System.out.println(first);                // {https://example.org/contracts/order/v1}CreateOrderRequest
```

`QName` lưu namespace URI, local part và một prefix tùy chọn. Phép so sánh `equals` dựa trên **namespace URI và local part**, bỏ qua prefix. Dạng `{URI}localName` trong kết quả `toString()` là ký pháp quen dùng để mô tả tên mở rộng, không phải cú pháp thẻ XML mà ta trực tiếp viết vào tài liệu.

Ngược lại:

```java
QName v1 = new QName("urn:example:orders:v1", "CreateOrderRequest");
QName v2 = new QName("urn:example:orders:v2", "CreateOrderRequest");

System.out.println(v1.equals(v2)); // false
```

Việc thay đổi URI khi phiên bản hóa contract là quyết định ảnh hưởng trực tiếp đến định tuyến SOAP, các ràng buộc schema và client đã sinh mã. Không nên đổi namespace một cách tùy tiện chỉ để chỉnh tên thư mục hoặc vị trí lưu XSD.

## 6. Namespace trong XSD: `targetNamespace` và `elementFormDefault`

Với cách xây dựng dịch vụ SOAP **contract-first**, XSD thường là nguồn định nghĩa cấu trúc request/response trước khi sinh lớp JAXB và viết endpoint. Xét một schema tối giản:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:tns="https://example.org/contracts/order/v1"
    targetNamespace="https://example.org/contracts/order/v1"
    elementFormDefault="qualified"
    attributeFormDefault="unqualified">

    <xs:element name="CreateOrderRequest">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="orderId" type="xs:string"/>
                <xs:element name="amount" type="xs:decimal"/>
            </xs:sequence>
            <xs:attribute name="requestId" type="xs:string"/>
        </xs:complexType>
    </xs:element>

    <xs:element name="CreateOrderResponse">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="accepted" type="xs:boolean"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
```

Có bốn điểm cần nắm:

- `xmlns:xs` chỉ định namespace của **ngôn ngữ XML Schema**. Nó cho phép công cụ hiểu `xs:element`, `xs:string` và `xs:complexType`. URI này không phải namespace của dữ liệu nghiệp vụ.
- `targetNamespace` là namespace mà các **khai báo toàn cục** của schema này thuộc về, chẳng hạn phần tử `CreateOrderRequest`.
- `xmlns:tns` tạo prefix thuận tiện để **tham chiếu** các khai báo trong cùng namespace, ví dụ `type="tns:OrderType"` nếu có kiểu toàn cục đó. `targetNamespace` không tự tạo ra prefix `tns`.
- `elementFormDefault="qualified"` làm cho **phần tử cục bộ** như `orderId` và `amount` phải xuất hiện trong target namespace, trừ trường hợp có cấu hình `form` riêng. `attributeFormDefault="unqualified"` giữ thuộc tính cục bộ `requestId` ở namespace rỗng, trừ khi khai báo khác.

Một XML instance phù hợp với schema này là:

```xml
<ord:CreateOrderRequest
    xmlns:ord="https://example.org/contracts/order/v1"
    requestId="REQ-88">
    <ord:orderId>ORD-1024</ord:orderId>
    <ord:amount>125.50</ord:amount>
</ord:CreateOrderRequest>
```

Nếu gửi `<orderId>` không có prefix và không khai báo default namespace, phần tử đó ở namespace rỗng, trái với quy định `elementFormDefault="qualified"` trong schema này. Dù nội dung văn bản có đúng, bộ kiểm tra XSD vẫn có thể từ chối thông điệp.

### `xs:import` và `xs:include` khác nhau ở namespace

Khi chia schema thành nhiều tệp:

- `xs:include` dùng cho các schema thuộc cùng target namespace (hoặc trường hợp schema được include không khai báo target namespace theo quy tắc của XSD).
- `xs:import` dùng để khai báo phụ thuộc sang **namespace khác**, sau đó dùng prefix đã khai báo để tham chiếu kiểu/phần tử bên ngoài.

Ví dụ schema đơn hàng cần một phần tử được định nghĩa ở namespace khách hàng:

```xml
<xs:import
    namespace="https://example.org/contracts/customer/v1"
    schemaLocation="customer-v1.xsd"/>
```

`namespace` cho biết **danh tính** của namespace được import; `schemaLocation` là gợi ý **nơi tìm schema**. Chúng không phải hai cách viết cùng một giá trị.

## 7. Namespace trong WSDL và SOAP message

WSDL 1.1 sử dụng namespace riêng cho các thành phần mô tả dịch vụ; nó đồng thời có thể tham chiếu các phần tử do XSD khai báo.

Ví dụ rút gọn về một `wsdl:message`:

```xml
<wsdl:definitions
    xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
    xmlns:ord="https://example.org/contracts/order/v1"
    targetNamespace="https://example.org/wsdl/order-service">

    <wsdl:message name="CreateOrderInput">
        <wsdl:part name="parameters" element="ord:CreateOrderRequest"/>
    </wsdl:message>
</wsdl:definitions>
```

Ở đây:

- `wsdl:definitions`, `wsdl:message` và `wsdl:part` là các phần tử thuộc namespace WSDL.
- `targetNamespace` của **WSDL** định danh các cấu phần WSDL được khai báo trong đó; nó có thể khác `targetNamespace` của **XSD**.
- `element="ord:CreateOrderRequest"` tham chiếu đến **phần tử toàn cục trong XSD** theo QName. Để tài liệu WSDL đầy đủ hợp lệ và dùng được, phần tử đó phải hiện diện trong schema được nhúng hoặc import ở phần `wsdl:types`.

Trong SOAP, lớp vỏ (Envelope) và phần tử nghiệp vụ (payload) thuộc những namespace khác nhau:

```xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="https://example.org/contracts/order/v1">
    <soap:Header/>
    <soap:Body>
        <ord:CreateOrderRequest requestId="REQ-88">
            <ord:orderId>ORD-1024</ord:orderId>
            <ord:amount>125.50</ord:amount>
        </ord:CreateOrderRequest>
    </soap:Body>
</soap:Envelope>
```

Đây là SOAP **1.1**, có Envelope namespace `http://schemas.xmlsoap.org/soap/envelope/`. SOAP **1.2** dùng Envelope namespace `http://www.w3.org/2003/05/soap-envelope`. Hai URI này không hoán đổi cho nhau; client và server phải thống nhất phiên bản SOAP, định dạng thông điệp và binding liên quan.

**QName của payload** trong ví dụ là `{https://example.org/contracts/order/v1}CreateOrderRequest`. QName này độc lập với prefix `soap` dùng ở Envelope và với địa chỉ HTTP đích.

## 8. Liên hệ với JAXB và endpoint Spring Web Services

Spring-WS có thể định tuyến request theo QName của **phần tử gốc bên trong SOAP Body**. Khi dùng `@PayloadRoot`, namespace và local part phải khớp với contract:

```java
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;

@Endpoint
public class OrderEndpoint {
    private static final String ORDER_NS =
            "https://example.org/contracts/order/v1";

    @PayloadRoot(namespace = ORDER_NS, localPart = "CreateOrderRequest")
    @ResponsePayload
    public CreateOrderResponse handle(
            @RequestPayload CreateOrderRequest request) {
        CreateOrderResponse response = new CreateOrderResponse();
        response.setAccepted(true);
        return response;
    }
}
```

Đoạn mã minh họa giả định các lớp `CreateOrderRequest` và `CreateOrderResponse` được ánh xạ JAXB thành phần tử gốc tương ứng từ XSD. Trong dự án thật, kiểu tham số/trả về phụ thuộc mã JAXB đã sinh, cấu hình marshaller và việc lớp được gắn `@XmlRootElement` hay cần `JAXBElement` cùng `ObjectFactory`.

Định tuyến cần so khớp:

```text
SOAP Body child QName:
{https://example.org/contracts/order/v1}CreateOrderRequest
                       │
                       ▼
@PayloadRoot(namespace = ORDER_NS, localPart = "CreateOrderRequest")
                       │
                       ▼
             OrderEndpoint.handle(...)
```

Nếu SOAP client chọn prefix `x` thay cho `ord` nhưng vẫn giữ cùng namespace URI, endpoint vẫn có thể được định tuyến đúng. Nếu client thay **URI** hoặc **local name**, `@PayloadRoot` trên sẽ không còn khớp.

Ở phía JAXB, namespace có thể xuất hiện trong các annotation như `@XmlRootElement`, `@XmlElement` và `@XmlSchema`. Với Jakarta XML Binding, khai báo ở `package-info.java` có thể có dạng:

```java
@jakarta.xml.bind.annotation.XmlSchema(
    namespace = "https://example.org/contracts/order/v1",
    elementFormDefault =
        jakarta.xml.bind.annotation.XmlNsForm.QUALIFIED
)
package org.example.orders.contract;
```

Điều này giúp thống nhất namespace của các phần tử được ánh xạ trong package. Trên các phiên bản Spring/JAXB cũ, annotation có thể thuộc `javax.xml.bind.annotation`; cần dùng bộ thư viện thống nhất với phiên bản framework đang chạy. Riêng `javax.xml.namespace.QName` vẫn là lớp của JDK.

Khi sinh mã từ XSD, nên coi QName trong XSD là nguồn sự thật: chỉnh sửa thủ công annotation JAXB mà không sửa contract có thể khiến request/response không còn tương thích với phía đối tác.

## 9. Các lỗi namespace thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Không tìm thấy endpoint cho payload | QName của phần tử đầu tiên trong SOAP Body không khớp `@PayloadRoot`. | In namespace URI và local name của payload; so với annotation; đừng chỉ nhìn prefix. |
| JAXB báo `unexpected element` | Namespace hoặc tên phần tử thực tế khác khai báo JAXB, hoặc loại root element đã ánh xạ không đúng. | So `{URI}localName` trong lỗi với XSD và mapping JAXB. |
| XML parser báo prefix chưa khai báo | Dùng `ord:...` nhưng thiếu `xmlns:ord` ở phạm vi đang có hiệu lực. | Tìm khai báo `xmlns:ord` gần nhất ở phần tử hoặc tổ tiên. |
| XSD validation báo không tìm thấy khai báo phần tử | Phần tử được gửi ở namespace rỗng/sai namespace, hoặc schema import chưa phù hợp. | So `targetNamespace`, `elementFormDefault`, QName phần tử và `xs:import`. |
| Cùng prefix nhưng hệ thống coi là hai phần tử khác nhau | Prefix được gán hai URI khác nhau tại các phạm vi khác nhau. | Kiểm tra từng khai báo `xmlns:prefix` cùng phạm vi áp dụng. |
| Đổi sang SOAP 1.2 gây lỗi Envelope/binding | Namespace SOAP Envelope và phiên bản protocol không khớp cấu hình dịch vụ. | Xác nhận SOAP 1.1/1.2, namespace Envelope và binding WSDL. |
| Đường dẫn XSD tải được nhưng payload vẫn sai | Có file schema không đồng nghĩa namespace của XML đã đúng. | Kiểm tra namespace URI trong XML, không chỉ `schemaLocation` hay endpoint URL. |

Một quy trình chẩn đoán có thể áp dụng khi tích hợp Spring-WS:

1. **Lấy SOAP XML thực tế** trên dây truyền hoặc từ test, chú ý phần tử trực tiếp trong `Body`.
2. **Phân giải QName** của phần tử đó: tìm prefix, truy vết `xmlns` có hiệu lực và ghi lại `{URI}localName`. Nếu không có prefix, kiểm tra default namespace.
3. **Đối chiếu XSD**: kiểm tra global element, `targetNamespace`, quy tắc `elementFormDefault` và các `import`.
4. **Đối chiếu Spring-WS/JAXB**: kiểm tra `@PayloadRoot`, các annotation XML binding, root element được sinh và cấu hình marshaller.
5. **Kiểm tra phiên bản SOAP** nếu lỗi liên quan Envelope, binding hoặc xử lý SOAP Fault.

Khi triển khai kiểm thử tương thích giữa nhiều client, nên có ít nhất hai ca: một thông điệp dùng prefix quen thuộc và một thông điệp dùng prefix khác nhưng cùng namespace URI. Cả hai phải được xử lý như cùng một QName. Thêm ca dùng URI khác để xác nhận contract từ chối hoặc báo lỗi đúng kỳ vọng.

## 10. Bài thực hành đọc QName

Cho tài liệu XML:

```xml
<env:Envelope
    xmlns:env="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns="https://example.org/contracts/order/v1"
    xmlns:a="https://example.org/contracts/audit/v1">
    <env:Body>
        <CreateOrderRequest a:traceId="T-42" source="B2B">
            <orderId>ORD-1024</orderId>
        </CreateOrderRequest>
    </env:Body>
</env:Envelope>
```

Hãy phân giải tên mở rộng của các phần tử và thuộc tính sau. Kết quả:

| Thành phần | Tên mở rộng |
|---|---|
| `env:Body` | `{http://schemas.xmlsoap.org/soap/envelope/}Body` |
| `CreateOrderRequest` | `{https://example.org/contracts/order/v1}CreateOrderRequest` |
| `orderId` | `{https://example.org/contracts/order/v1}orderId` |
| Thuộc tính `a:traceId` | `{https://example.org/contracts/audit/v1}traceId` |
| Thuộc tính `source` | `source`, thuộc namespace rỗng |

Ví dụ cho thấy có thể không dùng prefix cho payload nhưng vẫn khớp `@PayloadRoot(namespace = "...", localPart = "CreateOrderRequest")`. Phần tử và thuộc tính được phân giải namespace theo hai quy tắc khác nhau.

## Tổng kết

Để đọc chính xác một hợp đồng SOAP, hãy luôn xác định **namespace URI + local name** trước khi so sánh tên XML. Prefix và default namespace quyết định cách viết tên trong phạm vi tài liệu; `targetNamespace` và quy tắc `form` trong XSD quyết định các QName hợp lệ; WSDL tham chiếu QName của các thành phần contract; JAXB và `@PayloadRoot` của Spring-WS phải ánh xạ đúng các QName đó.

Khi gặp lỗi tích hợp, kiểm tra QName thực tế của payload thường hiệu quả hơn việc chỉ so tên thẻ, prefix, URL dịch vụ hoặc đường dẫn tệp XSD.
