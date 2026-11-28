# Namespace mặc định và sự khác nhau giữa tên phần tử với tên thuộc tính

## 1. Vì sao cần hiểu quy tắc này khi xây dựng SOAP service?

Trong **Spring Web Services (Spring-WS)**, request SOAP không được nhận diện chỉ bằng chữ `GetCustomerRequest` nhìn thấy trên màn hình. Bộ định tuyến endpoint, bộ kiểm tra XSD, JAXB và các thành phần xử lý SOAP xác định một phần tử XML bằng **tên đầy đủ có namespace**. Sai namespace có thể làm request không đến đúng `@Endpoint`, không hợp lệ với XSD hoặc không ánh xạ được sang đối tượng Java.

Giả sử contract-first service quy định phần tử gốc của payload là `GetCustomerRequest` thuộc namespace `https://example.org/contracts/customer/v1`, có phần tử con `customerId` và thuộc tính `requestId`:

```xml
<GetCustomerRequest
    xmlns="https://example.org/contracts/customer/v1"
    requestId="req-001">
    <customerId>C-100</customerId>
</GetCustomerRequest>
```

Ba tên ở đây **không** thuộc cùng namespace:

| Tên xuất hiện trong XML | Loại tên | Namespace thực tế | Tên cục bộ (*local name*) |
| --- | --- | --- | --- |
| `GetCustomerRequest` | Phần tử | `https://example.org/contracts/customer/v1` | `GetCustomerRequest` |
| `customerId` | Phần tử | `https://example.org/contracts/customer/v1` | `customerId` |
| `requestId` | Thuộc tính | Không có namespace | `requestId` |

**Quy tắc cốt lõi:** `xmlns="..."` đặt **namespace mặc định cho tên phần tử không có prefix** trong phạm vi khai báo; nó **không** đưa tên thuộc tính không có prefix vào namespace đó.

Đây là nền tảng cần nắm trước khi thiết kế XSD/WSDL, sinh JAXB binding, viết `@PayloadRoot`, SOAP client, kiểm thử XML và xử lý SOAP Fault trong các tích hợp doanh nghiệp.

## 2. Tên XML có namespace được nhận diện như thế nào?

### 2.1. Namespace URI, prefix, local name và expanded name

Một tên XML có namespace được biểu diễn về mặt ngữ nghĩa bằng cặp:

```text
{namespace URI}localName
```

Cách viết này thường được gọi là **expanded name**. Ví dụ:

```text
{https://example.org/contracts/customer/v1}GetCustomerRequest
{https://example.org/contracts/customer/v1}customerId
{}requestId
```

Trong XML, có thể đặt **prefix** trước tên để chỉ namespace:

```xml
<c:GetCustomerRequest
    xmlns:c="https://example.org/contracts/customer/v1"
    requestId="req-001">
    <c:customerId>C-100</c:customerId>
</c:GetCustomerRequest>
```

Ở đây:

- `c` là **prefix**, chỉ là bí danh được khai báo bằng `xmlns:c`.
- `https://example.org/contracts/customer/v1` là **namespace URI**, định danh không gian tên.
- `GetCustomerRequest` và `customerId` là **local name**.
- Cặp namespace URI + local name mới là tên được dùng để phân biệt phần tử.

Prefix `c` có thể đổi thành `cust` mà không làm thay đổi tên đầy đủ, miễn là `cust` được ánh xạ đến **cùng URI**. Trái lại, chỉ đổi URI từ `/v1` sang `/v2` sẽ tạo ra namespace khác, dù local name vẫn y nguyên.

> Namespace URI thường trông giống địa chỉ web, nhưng XML không yêu cầu địa chỉ đó phải truy cập được. Trong hợp đồng SOAP, URI cần được chọn nhất quán, ổn định và so khớp chính xác; khác chữ hoa/chữ thường, dấu `/` hoặc `http`/`https` đều có thể dẫn đến tên khác.

### 2.2. Namespace mặc định dành cho phần tử

Khai báo:

```xml
xmlns="https://example.org/contracts/customer/v1"
```

thiết lập namespace mặc định trên phần tử chứa khai báo và các phần tử con thuộc phạm vi của nó, trừ khi bị khai báo lại. Vì vậy hai payload sau mang **cùng tên phần tử theo namespace**:

```xml
<!-- Cách 1: dùng namespace mặc định -->
<GetCustomerRequest xmlns="https://example.org/contracts/customer/v1"
                    requestId="req-001">
    <customerId>C-100</customerId>
</GetCustomerRequest>
```

```xml
<!-- Cách 2: dùng prefix tường minh -->
<cust:GetCustomerRequest
    xmlns:cust="https://example.org/contracts/customer/v1"
    requestId="req-001">
    <cust:customerId>C-100</cust:customerId>
</cust:GetCustomerRequest>
```

Trong cả hai ví dụ, phần tử gốc là `{https://example.org/contracts/customer/v1}GetCustomerRequest` và phần tử con là `{https://example.org/contracts/customer/v1}customerId`. Dù prefix khác nhau, chúng tương đương về **tên phần tử và nội dung dữ liệu**.

### 2.3. Thuộc tính không có prefix luôn không có namespace

Xét ví dụ:

```xml
<GetCustomerRequest
    xmlns="https://example.org/contracts/customer/v1"
    xmlns:meta="https://example.org/metadata/v1"
    requestId="req-001"
    meta:source="crm">
    <customerId>C-100</customerId>
</GetCustomerRequest>
```

| Tên XML | Expanded name |
| --- | --- |
| Phần tử `GetCustomerRequest` | `{https://example.org/contracts/customer/v1}GetCustomerRequest` |
| Phần tử `customerId` | `{https://example.org/contracts/customer/v1}customerId` |
| Thuộc tính `requestId` | `{}requestId` |
| Thuộc tính `meta:source` | `{https://example.org/metadata/v1}source` |

Khi muốn một thuộc tính có namespace, **phải gắn prefix được khai báo** vào tên thuộc tính. Namespace mặc định không tự bổ sung namespace cho thuộc tính.

Các khai báo `xmlns` và `xmlns:meta` là **khai báo namespace**, không phải những trường dữ liệu nghiệp vụ thông thường. Trong mô hình namespace/XML DOM, chúng được xử lý đặc biệt, không nên nhầm với thuộc tính `requestId` của hợp đồng.

### 2.4. Hai thuộc tính cùng local name vẫn có thể khác nhau

```xml
<Record xmlns="urn:example:records"
        xmlns:ext="urn:example:extensions"
        id="local-10"
        ext:id="external-88" />
```

`id` có expanded name `{}id`, còn `ext:id` là `{urn:example:extensions}id`; do đó đây là **hai thuộc tính khác nhau**. Ngược lại, nếu `a` và `b` cùng trỏ tới `urn:example:extensions`, việc viết cả `a:id` và `b:id` trên một phần tử là không hợp lệ theo quy tắc namespace vì hai thuộc tính có cùng expanded name.

## 3. Phạm vi áp dụng và cách đặt lại namespace mặc định

Namespace mặc định có phạm vi từ vị trí khai báo xuống các phần tử con. Có thể khai báo lại bằng một URI khác hoặc đặt `xmlns=""` để các tên phần tử không có prefix bên trong trở về trạng thái **không có namespace**.

```xml
<catalog xmlns="urn:example:catalog:v1">
    <item id="I-1">
        <title>SOAP Essentials</title>
        <notes xmlns="">
            <text>Internal only</text>
        </notes>
    </item>
</catalog>
```

Phân tích từng tên:

| Tên | Namespace URI | Lý do |
| --- | --- | --- |
| `catalog` | `urn:example:catalog:v1` | Chính phần tử khai báo namespace mặc định |
| `item` | `urn:example:catalog:v1` | Kế thừa khai báo của `catalog` |
| `title` | `urn:example:catalog:v1` | Vẫn trong phạm vi khai báo mặc định |
| `notes` | Không có | `xmlns=""` tác dụng ngay trên phần tử `notes` |
| `text` | Không có | Kế thừa mặc định rỗng từ `notes` |
| Thuộc tính `id` | Không có | Thuộc tính không có prefix không nhận namespace mặc định |

Điểm dễ bỏ sót: `xmlns=""` **không chỉ ảnh hưởng các phần tử con**. Chính phần tử chứa khai báo (`notes`) cũng không có namespace. Khi ra khỏi nhánh `notes`, các phần tử thuộc nhánh khác của `catalog` vẫn theo namespace ban đầu.

Nếu một phần tử đã có prefix, namespace của nó được quyết định bằng khai báo của prefix đó; việc đổi `xmlns="..."` không thay đổi namespace của tên có prefix.

## 4. XSD: phần tử và thuộc tính có quy tắc `form` khác nhau

Trong phát triển SOAP theo hướng **contract-first**, XSD quyết định tên XML nào hợp lệ. Một lược đồ thường khai báo namespace đích (`targetNamespace`) và quy tắc đối với khai báo phần tử, thuộc tính cục bộ:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:tns="https://example.org/contracts/customer/v1"
    targetNamespace="https://example.org/contracts/customer/v1"
    elementFormDefault="qualified"
    attributeFormDefault="unqualified">

    <xs:element name="GetCustomerRequest">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="customerId" type="xs:string" />
            </xs:sequence>
            <xs:attribute name="requestId"
                          type="xs:string"
                          use="required" />
        </xs:complexType>
    </xs:element>

    <xs:element name="GetCustomerResponse">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="customerName" type="xs:string" />
            </xs:sequence>
        </xs:complexType>
    </xs:element>

</xs:schema>
```

Ý nghĩa các cấu hình:

| Thuộc tính cấu hình XSD | Ý nghĩa trong ví dụ |
| --- | --- |
| `targetNamespace=".../v1"` | Namespace của các khai báo toàn cục như `GetCustomerRequest`, `GetCustomerResponse` |
| `elementFormDefault="qualified"` | Các **phần tử cục bộ** như `customerId`, `customerName` phải thuộc namespace đích, trừ khi có `form` ghi đè |
| `attributeFormDefault="unqualified"` | Các **thuộc tính cục bộ** như `requestId` phải không có namespace, trừ khi có `form` ghi đè |
| `use="required"` | Thuộc tính `requestId` là bắt buộc trên request |

**Phân biệt khai báo toàn cục và cục bộ:** Các phần tử/thuộc tính khai báo trực tiếp dưới `xs:schema` thuộc `targetNamespace` khi schema có namespace đích; `elementFormDefault` và `attributeFormDefault` chi phối các khai báo **cục bộ**. Mỗi khai báo cục bộ còn có thể ghi đè bằng `form="qualified"` hoặc `form="unqualified"` theo quy tắc XSD.

### 4.1. XML hợp lệ với schema trên

```xml
<GetCustomerRequest
    xmlns="https://example.org/contracts/customer/v1"
    requestId="req-001">
    <customerId>C-100</customerId>
</GetCustomerRequest>
```

- `GetCustomerRequest`: thuộc namespace đích vì là phần tử toàn cục.
- `customerId`: cũng thuộc namespace đích vì `elementFormDefault="qualified"`.
- `requestId`: không có namespace vì `attributeFormDefault="unqualified"`.

### 4.2. XML trông gần giống nhưng sai namespace

```xml
<c:GetCustomerRequest
    xmlns:c="https://example.org/contracts/customer/v1"
    c:requestId="req-001">
    <c:customerId>C-100</c:customerId>
</c:GetCustomerRequest>
```

Thuộc tính `c:requestId` ở đây có tên `{https://example.org/contracts/customer/v1}requestId`, **không trùng** với `{}requestId` được XSD yêu cầu. Nếu kiểm tra đúng schema đã cho, request này thiếu thuộc tính `requestId` không namespace và chứa một thuộc tính khác chưa được khai báo; nó không hợp lệ.

Ví dụ khác:

```xml
<GetCustomerRequest
    xmlns="https://example.org/contracts/customer/v1"
    requestId="req-001">
    <customerId xmlns="">C-100</customerId>
</GetCustomerRequest>
```

Phần tử `customerId` trong ví dụ này là `{}customerId`, nên không khớp `{https://example.org/contracts/customer/v1}customerId` mà schema khai báo.

### 4.3. Nếu muốn thuộc tính có namespace thì làm thế nào?

Trong một thiết kế **khác**, khai báo thuộc tính cục bộ có thể dùng `form="qualified"`:

```xml
<xs:attribute name="requestId"
              type="xs:string"
              use="required"
              form="qualified" />
```

Khi đó, XML instance phải biểu diễn tên thuộc tính bằng prefix trỏ tới namespace đích:

```xml
<GetCustomerRequest
    xmlns="https://example.org/contracts/customer/v1"
    xmlns:c="https://example.org/contracts/customer/v1"
    c:requestId="req-001">
    <customerId>C-100</customerId>
</GetCustomerRequest>
```

**Không** thể bỏ `c:` khỏi tên thuộc tính và mong `xmlns="..."` tự áp dụng. Cần nhớ rằng ví dụ này chỉ hợp lệ **sau khi XSD đã đổi** thành thuộc tính qualified; không phải payload hợp lệ cho XSD ở mục 4.

## 5. Namespace trong SOAP Envelope, Body và payload

SOAP có namespace riêng dành cho cấu trúc thông điệp; dữ liệu nghiệp vụ trong `Body` lại thuộc namespace contract. Đây là một thông điệp SOAP 1.1 hợp lệ theo XSD minh họa:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
    <soap:Header />
    <soap:Body>
        <GetCustomerRequest
            xmlns="https://example.org/contracts/customer/v1"
            requestId="req-001">
            <customerId>C-100</customerId>
        </GetCustomerRequest>
    </soap:Body>
</soap:Envelope>
```

Các tên có ý nghĩa khác nhau:

| Tên | Namespace | Vai trò |
| --- | --- | --- |
| `soap:Envelope` | `http://schemas.xmlsoap.org/soap/envelope/` | Vỏ thông điệp SOAP 1.1 |
| `soap:Header` | `http://schemas.xmlsoap.org/soap/envelope/` | Vùng header SOAP |
| `soap:Body` | `http://schemas.xmlsoap.org/soap/envelope/` | Vùng payload |
| `GetCustomerRequest` | `https://example.org/contracts/customer/v1` | Phần tử gốc payload, dùng để định tuyến endpoint |
| `customerId` | `https://example.org/contracts/customer/v1` | Dữ liệu do XSD nghiệp vụ định nghĩa |
| `requestId` | Không có | Thuộc tính nghiệp vụ unqualified |

Hai dạng sau là tương đương về tên XML của **payload**:

```xml
<!-- Dạng dùng namespace mặc định -->
<GetCustomerRequest xmlns="https://example.org/contracts/customer/v1"
                    requestId="req-001">
    <customerId>C-100</customerId>
</GetCustomerRequest>
```

```xml
<!-- Dạng dùng prefix -->
<c:GetCustomerRequest
    xmlns:c="https://example.org/contracts/customer/v1"
    requestId="req-001">
    <c:customerId>C-100</c:customerId>
</c:GetCustomerRequest>
```

Không nên căn cứ vào việc request dùng prefix hay namespace mặc định để suy đoán đây là hai loại request khác nhau. Bộ xử lý XML và Spring-WS dựa vào **namespace URI + local name**.

> Lưu ý phiên bản: SOAP 1.2 dùng namespace `http://www.w3.org/2003/05/soap-envelope`, khác với SOAP 1.1 ở ví dụ. Namespace của `Envelope` phải phù hợp với phiên bản SOAP mà hệ thống hỗ trợ; đây là một vấn đề riêng với namespace nghiệp vụ của payload.

## 6. Liên hệ WSDL, JAXB và `@PayloadRoot` trong Spring-WS

### 6.1. Trong WSDL, phần tử request thường được tham chiếu bằng QName

Ví dụ một đoạn WSDL 1.1 contract-first:

```xml
<wsdl:definitions
    xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
    xmlns:tns="https://example.org/contracts/customer/v1"
    targetNamespace="https://example.org/contracts/customer/v1">

    <!-- Phần tử GetCustomerRequest được khai báo trong XSD của contract. -->
    <wsdl:message name="GetCustomerInput">
        <wsdl:part name="parameters" element="tns:GetCustomerRequest" />
    </wsdl:message>

</wsdl:definitions>
```

Giá trị `tns:GetCustomerRequest` trong `element="..."` là **tham chiếu QName** tới khai báo phần tử của XSD. Prefix `tns` trỏ tới URI hợp đồng; prefix có thể thay đổi nếu ánh xạ vẫn đúng. Đoạn WSDL này chỉ minh họa quy tắc tên, **chưa phải WSDL đầy đủ** để triển khai service (thiếu types, portType, binding và service).

Đừng nhầm hai việc:

- `element="tns:GetCustomerRequest"`: tên **thuộc tính WSDL** là `element`, còn **giá trị** của nó là một QName có prefix `tns`.
- `requestId="req-001"`: `requestId` là tên thuộc tính XML trong payload; giá trị `req-001` chỉ là chuỗi dữ liệu.

Một giá trị thuộc tính chứa dấu `:` chỉ được hiểu là QName khi **đặc tả/kiểu dữ liệu của thuộc tính ấy** quy định như vậy. Không áp dụng quy tắc phân giải tên phần tử một cách máy móc cho mọi chuỗi nằm trong thuộc tính.

### 6.2. JAXB ánh xạ tên phần tử và thuộc tính riêng biệt

Khi sinh Java classes từ XSD bằng JAXB/XJC, cần kiểm tra namespace được sinh ra ở `package-info.java` và các annotation trên trường. Ví dụ minh họa về mặt ánh xạ:

```java
// package-info.java của package chứa các JAXB classes
@jakarta.xml.bind.annotation.XmlSchema(
    namespace = "https://example.org/contracts/customer/v1",
    elementFormDefault = jakarta.xml.bind.annotation.XmlNsForm.QUALIFIED
)
package org.example.customer.contract;
```

```java
@XmlAccessorType(XmlAccessType.FIELD)
@XmlRootElement(
    name = "GetCustomerRequest",
    namespace = "https://example.org/contracts/customer/v1"
)
public class GetCustomerRequest {

    @XmlElement(
        name = "customerId",
        namespace = "https://example.org/contracts/customer/v1",
        required = true
    )
    private String customerId;

    @XmlAttribute(name = "requestId", required = true)
    private String requestId;

    // Getter/setter được lược bỏ để tập trung vào namespace.
}
```

`@XmlElement` chỉ tới phần tử thuộc namespace nghiệp vụ, trong khi `@XmlAttribute` ở đây ánh xạ thuộc tính không namespace. Việc thêm `namespace="..."` vào `@XmlAttribute` mà không đổi XSD tương ứng có thể làm XML được marshal khác contract.

Đây là **ví dụ annotation để đọc hiểu**, không yêu cầu tự viết lại lớp JAXB trong dự án contract-first. Class thật do công cụ sinh có thể dùng `@XmlRootElement` hoặc `ObjectFactory`/`JAXBElement` tùy cấu trúc schema và cấu hình sinh mã; hãy kiểm tra mã được sinh và cấu hình `Jaxb2Marshaller` tương ứng. Với Spring-WS hiện đại, có thể gặp API `jakarta.xml.bind`; các stack Spring/JAXB cũ có thể dùng `javax.xml.bind`, nhưng quy tắc XML namespace không thay đổi.

### 6.3. Spring-WS định tuyến `@PayloadRoot` theo namespace và localPart

```java
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;

@Endpoint
public class CustomerEndpoint {

    private static final String NAMESPACE_URI =
        "https://example.org/contracts/customer/v1";

    private final CustomerService customerService;

    public CustomerEndpoint(CustomerService customerService) {
        this.customerService = customerService;
    }

    @PayloadRoot(namespace = NAMESPACE_URI, localPart = "GetCustomerRequest")
    @ResponsePayload
    public GetCustomerResponse getCustomer(
            @RequestPayload GetCustomerRequest request) {
        return customerService.lookup(request.getCustomerId());
    }
}
```

Ở ví dụ này, `CustomerService`, `GetCustomerRequest` và `GetCustomerResponse` là các thành phần ứng dụng/contract giả định. Đoạn mã tập trung minh họa mapping; dự án thực tế phải có lớp model hợp lệ, dependency Spring-WS và cấu hình JAXB thích hợp.

`@PayloadRoot` khớp với expanded name của **phần tử payload trong SOAP Body**:

```text
{https://example.org/contracts/customer/v1}GetCustomerRequest
```

Do đó request `<c:GetCustomerRequest ...>` và `<GetCustomerRequest xmlns="...">` đều khớp cùng endpoint, với điều kiện URI và local name giống nhau. Nếu client gửi `<GetCustomerRequest>` **không có khai báo namespace phù hợp**, tên thực tế sẽ là `{}GetCustomerRequest` và không khớp mapping trên.

### 6.4. `QName` trong Java giúp kiểm chứng trực tiếp

```java
import javax.xml.namespace.QName;

String namespace = "https://example.org/contracts/customer/v1";

QName byPrefix = new QName(namespace, "GetCustomerRequest", "c");
QName byDefaultNamespace = new QName(namespace, "GetCustomerRequest");

System.out.println(byPrefix.equals(byDefaultNamespace)); // true
System.out.println(byPrefix.getNamespaceURI());            // URI contract
System.out.println(byPrefix.getLocalPart());               // GetCustomerRequest
```

`QName.equals()` xét namespace URI và local part, không xét sự khác biệt của prefix. Khi debug payload, nên log/kiểm tra hai giá trị này thay vì chỉ nhìn chuỗi tên in ra trong XML.

## 7. XPath và kiểm thử: đừng chỉ so tên hiển thị

Một XPath có prefix tường minh có thể truy vấn SOAP 1.1 và payload ở mục 5 như sau:

```xpath
/soap:Envelope/soap:Body/c:GetCustomerRequest/c:customerId
```

Để XPath này chạy đúng, bộ xử lý XPath phải đăng ký các ánh xạ:

```text
soap -> http://schemas.xmlsoap.org/soap/envelope/
c    -> https://example.org/contracts/customer/v1
```

Trong **XPath 1.0**, tên không có prefix trong biểu thức XPath không tự động nhận namespace mặc định từ tài liệu XML. Vì vậy biểu thức `//GetCustomerRequest` thường **không chọn được** phần tử `{https://example.org/contracts/customer/v1}GetCustomerRequest`. Cách chắc chắn là đăng ký prefix trong `NamespaceContext` hoặc cơ chế tương đương của thư viện XPath.

Để chọn thuộc tính `requestId` không namespace trên phần tử request, dùng:

```xpath
/soap:Envelope/soap:Body/c:GetCustomerRequest/@requestId
```

Không dùng `@c:requestId` với schema đang có `attributeFormDefault="unqualified"` vì đây là hai tên khác nhau.

Khi cần kiểm tra một nút độc lập với prefix, có thể so **cả local name và namespace URI**:

```xpath
/*[local-name()='Envelope'
  and namespace-uri()='http://schemas.xmlsoap.org/soap/envelope/']
```

Chỉ dùng `local-name()='GetCustomerRequest'` để định tuyến hoặc kiểm thử hợp đồng là thiếu chặt chẽ: nó có thể chấp nhận nhầm phần tử cùng local name nhưng thuộc namespace khác.

Một bộ kiểm thử tích hợp tối thiểu nên có các trường hợp sau:

| Trường hợp | Kỳ vọng |
| --- | --- |
| Payload dùng namespace mặc định đúng URI | Được XSD chấp nhận và định tuyến đúng endpoint |
| Payload dùng prefix khác nhưng cùng URI | Vẫn được XSD chấp nhận và định tuyến đúng endpoint |
| Payload không có namespace | Không khớp phần tử toàn cục trong contract |
| Payload dùng URI khác, dù local name giống | Không khớp contract/`@PayloadRoot` |
| Thuộc tính `requestId` không prefix | Hợp lệ theo XSD minh họa |
| Thuộc tính `c:requestId` | Không hợp lệ theo XSD minh họa |
| Phần tử con `customerId` bị `xmlns=""` | Không hợp lệ theo XSD minh họa |

Kết quả cụ thể trên đường xử lý request phụ thuộc thứ tự áp dụng schema validation, endpoint mapping và fault resolver: một payload sai có thể bị chặn bởi kiểm tra schema, không tìm thấy endpoint hoặc dẫn đến SOAP Fault. Không nên dự đoán một mã Fault cố định khi chưa biết cấu hình service.

## 8. Các lỗi thường gặp khi tích hợp hệ thống doanh nghiệp

| Hiện tượng | Nguyên nhân có thể liên quan đến namespace | Cách xác minh/sửa |
| --- | --- | --- |
| Request nhìn đúng tên nhưng không vào `@Endpoint` | Payload root là `{}GetCustomerRequest` hoặc URI khác với `@PayloadRoot` | Lấy namespace URI và local name thực tế của phần tử đầu tiên trong `Body`; so với annotation và XSD |
| Báo thiếu `requestId` mặc dù trong XML có thuộc tính | Client gửi `c:requestId` nhưng XSD yêu cầu `{}requestId` | Kiểm tra `attributeFormDefault`, `form` của thuộc tính và bỏ prefix nếu schema là unqualified |
| JAXB đọc được payload nhưng trường bị `null`, hoặc marshal ra XML khác mẫu | Annotation/schema binding không thống nhất về tên phần tử/thuộc tính | So `@XmlElement`, `@XmlAttribute`, `@XmlSchema` với XSD; kiểm tra kết quả marshal/unmarshal |
| XPath trả về rỗng dù XML có phần tử | XPath dùng tên không prefix hoặc đăng ký sai URI | Đăng ký prefix truy vấn và dùng QName đầy đủ; đừng chỉ kiểm tra `local-name()` |
| Request bị lỗi sau khi đổi `/v1` thành `/v2` | URI mới nghĩa là namespace mới, không chỉ thay alias | Cập nhật nhất quán XSD/WSDL, endpoint, client, dữ liệu mẫu và kiểm thử tương thích |
| XML có `xmlns=""` ở một nhánh và validation thất bại | Phần tử của nhánh bị chuyển thành không namespace | Xóa khai báo rỗng khi không cần hoặc khôi phục namespace theo đúng schema |

Trong các hệ thống dùng WS-Security/XML Signature, cần còn cẩn thận hơn với thuộc tính có namespace, chẳng hạn `wsu:Id`: tên này **không** tương đương với thuộc tính thường `Id`. Các bộ xử lý bảo mật và tham chiếu chữ ký cần nhận diện đúng tên/ID theo profile và cấu hình tương ứng. Không tự sửa tên hoặc prefix một cách tùy tiện sau khi thông điệp đã được ký.

## 9. Quy trình đọc và sửa một lỗi namespace trong SOAP service

Khi gặp request bị từ chối, có thể đi theo thứ tự sau:

1. **Đọc XSD trước**: xác định `targetNamespace`, khai báo phần tử toàn cục, `elementFormDefault`, `attributeFormDefault` và mọi `form` ghi đè ở phần tử/thuộc tính cục bộ.
2. **Xác định expanded name của payload**: phân giải mọi prefix và `xmlns="..."`; ghi lại chính xác `{URI}localName` của request root, phần tử con và thuộc tính bị nghi ngờ.
3. **Đối chiếu WSDL**: kiểm tra phần tử mà `wsdl:part` tham chiếu và namespace được khai báo cho contract.
4. **Đối chiếu Spring-WS**: so namespace/localPart của payload root với `@PayloadRoot`, không so đơn thuần văn bản sau dấu `:`.
5. **Đối chiếu JAXB**: kiểm tra namespace của `@XmlRootElement`/`@XmlElement`/`@XmlAttribute` hoặc các declaration trong `ObjectFactory`, rồi marshal/unmarshal một request nhỏ.
6. **Chạy hai kiểu test độc lập**: gửi cùng một payload với prefix tường minh và với namespace mặc định; cả hai phải có cùng kết quả khi expanded names không đổi.

Khi giao tiếp với đối tác, cách mô tả rõ ràng nhất là cung cấp **namespace URI, local name, schema version và XML mẫu**, thay vì yêu cầu họ phải dùng đúng một prefix nào đó. Prefix chỉ là cách trình bày trong XML; namespace là một phần của hợp đồng.

## 10. Bài luyện tập có đáp án

### Bài 1: Xác định namespace của từng tên

Cho XML:

```xml
<a:Order xmlns:a="urn:orders:v1"
         xmlns="urn:orders:v1"
         xmlns:m="urn:meta:v1"
         id="O-10"
         m:id="M-20">
    <line>1</line>
    <note xmlns="">urgent</note>
</a:Order>
```

Hãy xác định expanded name của `a:Order`, `line`, `note`, `id`, `m:id`.

**Đáp án:**

| Tên | Expanded name |
| --- | --- |
| `a:Order` | `{urn:orders:v1}Order` |
| `line` | `{urn:orders:v1}line` |
| `note` | `{}note` |
| `id` | `{}id` |
| `m:id` | `{urn:meta:v1}id` |

`a:Order` có prefix riêng, `line` kế thừa namespace mặc định, `note` đặt lại mặc định thành rỗng; cả hai thuộc tính `id` khác nhau vì namespace khác nhau.

### Bài 2: Hai payload có được xem là cùng tên không?

```xml
<q:GetCustomerRequest
    xmlns:q="https://example.org/contracts/customer/v1"
    requestId="r-1">
    <q:customerId>C-1</q:customerId>
</q:GetCustomerRequest>
```

```xml
<GetCustomerRequest
    xmlns="https://example.org/contracts/customer/v1"
    requestId="r-1">
    <customerId>C-1</customerId>
</GetCustomerRequest>
```

**Đáp án:** Có. Mọi tên phần tử và thuộc tính nghiệp vụ đều có expanded name tương ứng giống nhau. Chỉ khác cách thể hiện namespace qua prefix hay mặc định.

### Bài 3: Sửa request sai theo XSD ở mục 4

Request hiện tại:

```xml
<c:GetCustomerRequest
    xmlns:c="https://example.org/contracts/customer/v1"
    c:requestId="r-2">
    <customerId>C-2</customerId>
</c:GetCustomerRequest>
```

**Đáp án:** Có hai lỗi: `c:requestId` đang qualified dù schema yêu cầu unqualified; `customerId` không có prefix và không có namespace mặc định nên đang thuộc namespace rỗng. Một bản sửa đúng:

```xml
<c:GetCustomerRequest
    xmlns:c="https://example.org/contracts/customer/v1"
    requestId="r-2">
    <c:customerId>C-2</c:customerId>
</c:GetCustomerRequest>
```

### Bài 4: Tại sao `@PayloadRoot` không khớp?

Endpoint khai báo:

```java
@PayloadRoot(
    namespace = "https://example.org/contracts/customer/v1",
    localPart = "GetCustomerRequest"
)
```

Client gửi `<GetCustomerRequest requestId="r-3">...</GetCustomerRequest>` trong SOAP Body, không có `xmlns` phù hợp và không có prefix.

**Đáp án:** Phần tử client gửi là `{}GetCustomerRequest`; endpoint yêu cầu `{https://example.org/contracts/customer/v1}GetCustomerRequest`. Chỉ giống local name là chưa đủ. Cần đặt namespace đúng trên payload hoặc dùng prefix đã khai báo trỏ đến URI hợp đồng.

## 11. Những điểm cần ghi nhớ

- Tên phần tử/thuộc tính có namespace được phân biệt bằng **namespace URI + local name**; prefix không phải danh tính của tên.
- `xmlns="URI"` áp dụng cho **phần tử không prefix**, bao gồm chính phần tử khai báo và phần tử con trong phạm vi; **không áp dụng** cho tên thuộc tính không prefix.
- Tên thuộc tính **không prefix luôn không có namespace**. Muốn thuộc tính có namespace, phải có prefix được khai báo.
- `xmlns=""` đặt lại namespace mặc định thành rỗng ngay tại phần tử mang khai báo và các phần tử con không prefix.
- Trong XSD contract-first, cần đọc cả `targetNamespace`, `elementFormDefault`, `attributeFormDefault` và các khai báo `form`; tránh nhầm global với local.
- SOAP `Envelope`/`Body` và payload thường thuộc **hai namespace khác nhau**. Spring-WS `@PayloadRoot`, JAXB, XPath và schema validator cần thống nhất tên đầy đủ của payload.

**Tài liệu tham khảo chuẩn:** [W3C — Namespaces in XML 1.0](https://www.w3.org/TR/xml-names/), [W3C — XML Schema Part 1: Structures](https://www.w3.org/TR/xmlschema-1/), [Spring Web Services — Reference Documentation](https://docs.spring.io/spring-ws/docs/current/reference/html/).
