# Ánh xạ header vào phương thức bằng @SoapHeader

## 1. Mục tiêu và bối cảnh

Trong một dịch vụ SOAP phát triển bằng **Spring Web Services (Spring-WS)**, dữ liệu nghiệp vụ thường nằm trong `SOAP Body` và được ánh xạ từ XML thành Java object thông qua JAXB/OXM. Tuy nhiên, yêu cầu tích hợp doanh nghiệp còn mang những thông tin **liên quan đến việc xử lý thông điệp**, như correlation ID để truy vết, mã tenant đã được đối chiếu, version của context, hoặc metadata phục vụ policy. Những thông tin này có thể được công bố trong **SOAP Header** thay vì nhét chung vào phần tử nghiệp vụ.

Spring-WS cung cấp annotation **`@SoapHeader`** để đưa **một header element xác định bằng QName** vào tham số của phương thức `@Endpoint`. Nhờ đó, endpoint có thể nhận payload và header trong cùng lời gọi nhưng vẫn giữ rõ hai trách nhiệm:

- `@RequestPayload`: ánh xạ **phần tử gốc trong SOAP Body** thành request nghiệp vụ.
- `@SoapHeader`: lấy **SOAP Header element** theo QName để code đọc hoặc ánh xạ tiếp.

Bài học nằm trong chương **Header và ngữ cảnh** của module **SPRING_WEB_SERVICES**, gắn với cách phát triển SOAP **contract-first**, thiết kế XSD/WSDL, JAXB, xây dựng endpoint và SOAP client. Nội dung cũng chỉ rõ ranh giới với SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích.

Sau bài này, bạn có thể:

1. Phân biệt SOAP Header, SOAP Body và HTTP Header về cấu trúc, phạm vi và quy tắc xử lý.
2. Sử dụng `@SoapHeader("{namespace-uri}localName")` với tham số `SoapHeaderElement` đúng QName.
3. Chuyển XML header thành một JAXB object hoặc application context bằng một adapter riêng.
4. Công bố và kiểm thử header contract trong XSD/WSDL 1.1 document/literal.
5. Gửi SOAP Header từ `WebServiceTemplate`, không trộn dữ liệu header với request body.
6. Thiết kế xử lý header thiếu, trùng, không hợp lệ, `mustUnderstand` và SOAP Fault.
7. Phân biệt metadata do client khai báo với danh tính/quyền **đã xác thực** bởi WS-Security hoặc TLS.
8. Kiểm tra khả năng tương tác Java/.NET và giới hạn khi truyền ngữ cảnh qua các luồng hoặc hệ thống khác.

## 2. Đặt SOAP Header trong đúng lớp giao thức

Một SOAP 1.1 message có dạng:

```xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:order:service:v1"
    xmlns:ctx="urn:example:order:context:v1">
  <soapenv:Header>
    <ctx:RequestContext>
      <ctx:CorrelationId>CORR-1042</ctx:CorrelationId>
      <ctx:TenantCode>TENANT-A</ctx:TenantCode>
    </ctx:RequestContext>
  </soapenv:Header>
  <soapenv:Body>
    <ord:GetOrderRequest>
      <ord:OrderId>ORD-00042</ord:OrderId>
    </ord:GetOrderRequest>
  </soapenv:Body>
</soapenv:Envelope>
```

Ở ví dụ trên:

- `Envelope` nhận diện thông điệp SOAP và phiên bản SOAP qua namespace `http://schemas.xmlsoap.org/soap/envelope/`.
- `Header` chứa block `ctx:RequestContext`, một metadata contract có QName riêng.
- `Body` chứa `ord:GetOrderRequest`, là phần tử gốc của operation nghiệp vụ.
- `CorrelationId` được dùng để liên kết logs/traces qua các chặng.
- `TenantCode` chỉ là **một giá trị được gửi kèm**; chưa phải bằng chứng caller có quyền truy cập dữ liệu của tenant đó.

### 2.1. Ba loại header dễ nhầm

| Loại | Vị trí | Ví dụ | Thành phần xử lý |
| --- | --- | --- | --- |
| **HTTP header** | Bên ngoài XML, trong HTTP request | `Content-Type`, `Authorization`, `SOAPAction` | HTTP client/server, reverse proxy, security filter hoặc transport adapter |
| **SOAP Header** | `Envelope/Header` | `RequestContext`, WS-Addressing, WS-Security | SOAP message stack, interceptor và `@SoapHeader` |
| **Payload field** | `Envelope/Body/...` | `OrderId`, `Amount`, `CustomerId` | JAXB/OXM, `@RequestPayload`, domain mapper |

**`@SoapHeader` không đọc HTTP `Authorization` hoặc `SOAPAction`.** Nếu cần HTTP header, hãy cấu hình transport/servlet/security boundary tương ứng; không đổi tên một HTTP header thành SOAP header chỉ vì cả hai cùng gọi là “header”.

### 2.2. Chọn thông tin đặt trong header hay body

Một quy tắc thực dụng:

- **Body**: dữ liệu làm nên ý nghĩa của operation — ví dụ tạo đơn hàng nào, mặt hàng nào, số lượng và tiền tệ.
- **Header**: metadata liên quan đến xử lý, routing, tracing hoặc protocol — ví dụ correlation ID, security token hoặc thông tin context được contract quy định.
- **Authentication/authorization context**: đối tượng tin cậy của ứng dụng hình thành từ cơ chế xác thực; có thể được suy ra từ TLS/mTLS hoặc WS-Security, **không chỉ đọc một chuỗi trong Header**.

Ranh giới này không tuyệt đối. Một `requestId` phục vụ idempotency nghiệp vụ có thể cần nằm trong Body nếu nó là một phần ngữ nghĩa command. Nếu contract đặt request ID trong Header, tất cả client, interceptor và use case phải thống nhất rằng giá trị ấy là khóa idempotency, được bảo vệ/kiểm tra ra sao và tồn tại trong bao lâu.

## 3. QName là khóa của @SoapHeader

Header block được nhận diện bằng **QName** gồm `namespace URI` và `localPart`. Ví dụ:

```text
{urn:example:order:context:v1}RequestContext
```

Ký hiệu này được dùng trong `@SoapHeader` bằng cú pháp expanded QName:

```java
@SoapHeader("{urn:example:order:context:v1}RequestContext")
SoapHeaderElement contextHeader
```

Hai cách viết XML sau là cùng QName:

```xml
<ctx:RequestContext
    xmlns:ctx="urn:example:order:context:v1"/>
```

```xml
<x:RequestContext
    xmlns:x="urn:example:order:context:v1"/>
```

Ngược lại, phần tử không có namespace là **QName khác**:

```xml
<RequestContext/>
```

Các lỗi thường gặp:

- Dùng prefix `ctx:RequestContext` trong annotation thay vì expanded QName.
- So sánh local name `RequestContext` mà bỏ namespace.
- Cho rằng vì Body dùng namespace v1 thì Header mặc nhiên cũng thuộc v1; hai namespace có thể độc lập.
- Đổi namespace Header trong một lần triển khai mà không nâng contract và kiểm thử client.
- Cho rằng `xsi:schemaLocation` hoặc URL dịch vụ là căn cứ xác định QName.

Với SOAP 1.1/1.2, namespace của Envelope thay đổi nhưng QName của **custom header contract** có thể giữ nguyên nếu hai binding cùng công bố nó.

## 4. Annotation @SoapHeader hỗ trợ việc gì?

Điểm cần nhớ trong Spring-WS: **`@SoapHeader` dùng để chọn một SOAP Header element theo QName**, và một cách dùng được hỗ trợ là binding phần tử đó vào **`SoapHeaderElement`** trong handler method.

Các class/annotation liên quan:

```java
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;
import org.springframework.ws.soap.SoapHeaderElement;
import org.springframework.ws.soap.server.endpoint.annotation.SoapHeader;
```

Các thành phần nằm ở những package khác nhau:

| Thành phần | Ý nghĩa |
| --- | --- |
| `@Endpoint` | Đánh dấu bean chứa SOAP handler methods. |
| `@PayloadRoot` | Chọn method theo QName của phần tử gốc trong SOAP Body. |
| `@RequestPayload` | Liên kết Body payload với tham số request (ví dụ JAXB object). |
| **`@SoapHeader`** | Chọn header element theo QName được chỉ định trong annotation. |
| **`SoapHeaderElement`** | Đối tượng biểu diễn header block được chọn, có thể đọc nội dung XML và thuộc tính SOAP. |
| `@ResponsePayload` | Cho phép method trả về payload cho SOAP Body. |
| `Jaxb2Marshaller` | Spring OXM adapter dùng JAXB để đổi Java object ↔ XML. |

**Đừng nhầm hai điều sau:**

1. Có `@SoapHeader` không có nghĩa Spring-WS tự unmarshalling custom header vào một Java business class bất kỳ.
2. `@SoapHeader` không tự xác thực chữ ký, certificate, token, quyền tenant hay schema validation.

Tùy kiểu method argument được cấu hình hỗ trợ, code có thể cần dùng `SoapHeaderElement.getSource()`, sau đó nhờ JAXB/OXM hoặc parser thích hợp đọc XML và chuyển thành kiểu dữ liệu mong muốn.

### 4.1. Cú pháp chuẩn, không dùng tên tham số để định tuyến

```java
@SoapHeader("{urn:example:order:context:v1}RequestContext")
SoapHeaderElement header
```

Tên biến `header` chỉ ảnh hưởng code Java. Spring-WS không chọn theo tên Java variable, cũng không chọn theo prefix XML. Khi review, hãy đối chiếu **QName viết trong annotation** với phần tử trong XSD/WSDL đã công bố.

### 4.2. Header và payload được bind độc lập

Một handler có thể đồng thời có:

```java
@ResponsePayload
public GetOrderResponse getOrder(
    @RequestPayload GetOrderRequest request,
    @SoapHeader("{urn:example:order:context:v1}RequestContext")
    SoapHeaderElement contextHeader) {
    // ...
}
```

QName của Body được chọn ở `@PayloadRoot` trên method, còn QName của custom Header được chọn bởi `@SoapHeader` trên tham số. **Không mặc định một header sai/missing sẽ chọn sang endpoint khác**; tùy resolver và chính sách, request có thể thất bại ngay khi resolve tham số hoặc trong validation. Hành vi này phải được kiểm thử với phiên bản Spring-WS dùng trong dự án.

## 5. Ví dụ contract-first: tra cứu đơn hàng có RequestContext

Ta xây dựng một operation `GetOrder` với hai namespace:

- Payload service: `urn:example:order:service:v1`.
- Context header: `urn:example:order:context:v1`.

Hai XSD là artifact độc lập để client Java/JAXB, .NET hoặc SOAP stack khác đọc theo WSDL 1.1.

### 5.1. XSD dành cho Body

File ví dụ `order-service-v1.xsd`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:ord="urn:example:order:service:v1"
    targetNamespace="urn:example:order:service:v1"
    elementFormDefault="qualified">

  <xs:simpleType name="OrderIdType">
    <xs:restriction base="xs:token">
      <xs:minLength value="1"/>
      <xs:maxLength value="40"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="GetOrderRequest">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="OrderId"
                    type="ord:OrderIdType"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

  <xs:element name="GetOrderResponse">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="OrderId"
                    type="ord:OrderIdType"/>
        <xs:element name="Status"
                    type="xs:string"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
```

Dữ liệu nghiệp vụ tập trung trong Body. Schema xác định namespace và `xs:sequence`; không có correlation ID vì ví dụ xem đó là thông tin xử lý xuyên chặng.

### 5.2. XSD dành cho Header

File ví dụ `order-context-v1.xsd`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:ctx="urn:example:order:context:v1"
    targetNamespace="urn:example:order:context:v1"
    elementFormDefault="qualified">

  <xs:simpleType name="CorrelationIdType">
    <xs:restriction base="xs:token">
      <xs:minLength value="1"/>
      <xs:maxLength value="64"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="RequestContext">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="CorrelationId"
                    type="ctx:CorrelationIdType"/>
        <xs:element name="TenantCode"
                    type="xs:token"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
```

XSD công bố một **global element** `RequestContext` để WSDL `soap:header` có thể tham chiếu, giúp việc sinh JAXB header model và kiểm thử XML không phụ thuộc Java implementation.

**Giới hạn của XSD này:** `TenantCode` chỉ có kiểu `xs:token`, chưa thể xác nhận tenant được phép, caller thuộc tenant nào, hay CorrelationId có thực sự độc nhất. Những điều đó thuộc chính sách ứng dụng và bảo mật.

### 5.3. SOAP 1.1 request hoàn chỉnh

```xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:order:service:v1"
    xmlns:ctx="urn:example:order:context:v1">
  <soapenv:Header>
    <ctx:RequestContext>
      <ctx:CorrelationId>CORR-1042</ctx:CorrelationId>
      <ctx:TenantCode>TENANT-A</ctx:TenantCode>
    </ctx:RequestContext>
  </soapenv:Header>
  <soapenv:Body>
    <ord:GetOrderRequest>
      <ord:OrderId>ORD-00042</ord:OrderId>
    </ord:GetOrderRequest>
  </soapenv:Body>
</soapenv:Envelope>
```

**Tín hiệu định tuyến** là `{urn:example:order:service:v1}GetOrderRequest` trong Body. **Header được chọn** là `{urn:example:order:context:v1}RequestContext`. Chúng là hai QName khác nhau và có thể được đổi prefix độc lập.

### 5.4. SOAP 1.1 response ví dụ

```xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:order:service:v1">
  <soapenv:Body>
    <ord:GetOrderResponse>
      <ord:OrderId>ORD-00042</ord:OrderId>
      <ord:Status>SHIPPED</ord:Status>
    </ord:GetOrderResponse>
  </soapenv:Body>
</soapenv:Envelope>
```

Response không cần lặp lại request header nếu hợp đồng không yêu cầu. Nếu đối tác đòi `CorrelationId` trong response header, phải công bố response header tương ứng trong WSDL/binding và tạo nó tại SOAP response boundary; không tự thêm mà không thông báo.

## 6. WSDL 1.1 công bố SOAP Header ra sao?

XSD chỉ quy định phần tử; WSDL 1.1 có thể dùng **`soap:header` trong binding** để cho client biết một SOAP Header block thuộc operation. Một WSDL rút gọn nhưng đủ cấu trúc:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<wsdl:definitions
    xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
    xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:tns="urn:example:order:service:v1"
    xmlns:ctx="urn:example:order:context:v1"
    targetNamespace="urn:example:order:service:v1"
    name="OrderService">

  <wsdl:types>
    <xs:schema>
      <xs:import namespace="urn:example:order:service:v1"
                 schemaLocation="order-service-v1.xsd"/>
      <xs:import namespace="urn:example:order:context:v1"
                 schemaLocation="order-context-v1.xsd"/>
    </xs:schema>
  </wsdl:types>

  <wsdl:message name="GetOrderInput">
    <wsdl:part name="parameters"
               element="tns:GetOrderRequest"/>
  </wsdl:message>

  <wsdl:message name="GetOrderOutput">
    <wsdl:part name="parameters"
               element="tns:GetOrderResponse"/>
  </wsdl:message>

  <wsdl:message name="RequestContextHeaderMessage">
    <wsdl:part name="context"
               element="ctx:RequestContext"/>
  </wsdl:message>

  <wsdl:portType name="OrderPortType">
    <wsdl:operation name="GetOrder">
      <wsdl:input message="tns:GetOrderInput"/>
      <wsdl:output message="tns:GetOrderOutput"/>
    </wsdl:operation>
  </wsdl:portType>

  <wsdl:binding name="OrderSoap11Binding"
                type="tns:OrderPortType">
    <soap:binding style="document"
                  transport="http://schemas.xmlsoap.org/soap/http"/>
    <wsdl:operation name="GetOrder">
      <soap:operation
          soapAction="urn:example:order:service:v1/GetOrder"/>
      <wsdl:input>
        <soap:body use="literal"/>
        <soap:header
            message="tns:RequestContextHeaderMessage"
            part="context"
            use="literal"/>
      </wsdl:input>
      <wsdl:output>
        <soap:body use="literal"/>
      </wsdl:output>
    </wsdl:operation>
  </wsdl:binding>

  <wsdl:service name="OrderService">
    <wsdl:port name="OrderSoap11Port"
               binding="tns:OrderSoap11Binding">
      <soap:address
          location="https://soap.example.invalid/ws/orders"/>
    </wsdl:port>
  </wsdl:service>
</wsdl:definitions>
```

Địa chỉ `example.invalid` chỉ mang tính minh họa, không phải endpoint gọi được.

Những điểm cần nhận diện:

1. `wsdl:message` `GetOrderInput` mô tả Body request, còn `RequestContextHeaderMessage` mô tả Header.
2. `soap:body use="literal"` và `soap:header use="literal"` giúp binding tham chiếu XML elements rõ ràng.
3. `soap:header` tham chiếu `message` và `part` chứa global element `ctx:RequestContext`; không dùng Java class name.
4. `@SoapHeader` trong endpoint nhận header theo **QName của XSD**, không theo tên WSDL message `RequestContextHeaderMessage`.
5. WSDL declaration và `@SoapHeader` không tự bật WS-Security, schema validation hay chính sách header bắt buộc.
6. Công cụ client .NET/Java có thể sinh representation header khác nhau; phải kiểm chứng HTTP/SOAP thực.
7. Hai file XSD import phải resolve được trên CI/client codegen; việc tham chiếu `schemaLocation` cần được phân phối cùng WSDL.

Nếu hợp đồng cần khẳng định Header bắt buộc ở cấp ứng dụng, WSDL 1.1 `soap:header` đơn thuần chưa thay thế quy tắc runtime kiểm tra absent/duplicate và policy; hãy công bố rõ requirement và kiểm thử.

## 7. Endpoint nhận payload và Header trong cùng phương thức

Ví dụ Spring-WS endpoint nhận request JAXB từ Body và một `SoapHeaderElement` từ Header:

```java
package com.example.orders.soap;

import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;
import org.springframework.ws.soap.SoapHeaderElement;
import org.springframework.ws.soap.server.endpoint.annotation.SoapHeader;

@Endpoint
public final class OrderEndpoint {
    private static final String BODY_NS =
            "urn:example:order:service:v1";

    private final OrderQueryService queries;
    private final OrderContractMapper mapper;
    private final RequestContextDecoder contextDecoder;
    private final CallerIdentityProvider identities;

    public OrderEndpoint(OrderQueryService queries,
                         OrderContractMapper mapper,
                         RequestContextDecoder contextDecoder,
                         CallerIdentityProvider identities) {
        this.queries = queries;
        this.mapper = mapper;
        this.contextDecoder = contextDecoder;
        this.identities = identities;
    }

    @PayloadRoot(namespace = BODY_NS, localPart = "GetOrderRequest")
    @ResponsePayload
    public GetOrderResponse getOrder(
        @RequestPayload GetOrderRequest request,
        @SoapHeader("{urn:example:order:context:v1}RequestContext")
        SoapHeaderElement contextHeader) {

        RequestContextData context =
                contextDecoder.decode(contextHeader);

        AuthenticatedCaller caller =
                identities.requireAuthenticatedCaller();

        OrderSnapshot snapshot = queries.findAuthorized(
                caller, context.tenantCode(), request.getOrderId());

        return mapper.toResponse(snapshot);
    }
}
```

`OrderQueryService`, `OrderContractMapper`, `RequestContextDecoder`, `CallerIdentityProvider`, `AuthenticatedCaller` và `OrderSnapshot` là thành phần ứng dụng giả định. `GetOrderRequest`/`GetOrderResponse` là JAXB model từ Body XSD; package/import thực tế phụ thuộc build sinh mã.

**Nhiệm vụ của endpoint chỉ là phối hợp:**

- Framework định tuyến bằng `@PayloadRoot` theo Body QName.
- Framework lấy custom Header theo `@SoapHeader`.
- Decoder chuyển Header XML thành context đã kiểm tra cấu trúc.
- Security boundary cung cấp danh tính đã xác thực.
- Application service **tự kiểm tra quyền** của caller trên tenant và đơn hàng.
- Mapper tạo response JAXB theo WSDL/XSD.

Không nên mở HTTP connection, parse XML bằng regex hay truy vấn database trực tiếp trong endpoint.

### 7.1. Vì sao phải có `RequestContextDecoder`?

`SoapHeaderElement` là đối tượng XML của Spring-WS, không nên lan vào domain. Decoder gom việc đọc `Source`, giải mã JAXB, kiểm tra cấu trúc và lỗi:

```text
SOAP Header element
       |
       v
RequestContextDecoder (SOAP/XML adapter)
       |
       v
RequestContextData (immutable application data)
       |
       v
Authorization + business use case
```

Vì thế, nếu đối tác đổi JAXB package hoặc XSD header sang v2, thay đổi chủ yếu nằm trong decoder và contract adapter.

## 8. Giải mã SoapHeaderElement bằng JAXB/OXM

Với XSD ở mục 5.2, XJC thường tạo kiểu `RequestContext` có `@XmlRootElement` và các getter `getCorrelationId()`/`getTenantCode()`. Hình dạng thực tế phụ thuộc JAXB generator; có schema/binding trả về `JAXBElement<T>`.

Một adapter đọc XML header có thể dùng Spring OXM `Unmarshaller`:

```java
import jakarta.xml.bind.JAXBElement;
import org.springframework.oxm.Unmarshaller;
import org.springframework.ws.soap.SoapHeaderElement;

public final class RequestContextDecoder {
    private final Unmarshaller headerUnmarshaller;

    public RequestContextDecoder(Unmarshaller headerUnmarshaller) {
        this.headerUnmarshaller = headerUnmarshaller;
    }

    public RequestContextData decode(SoapHeaderElement header) {
        if (header == null) {
            throw new InvalidRequestContextException(
                    "Missing RequestContext header");
        }

        Object decoded = headerUnmarshaller.unmarshal(
                header.getSource());

        if (decoded instanceof JAXBElement<?> element) {
            decoded = element.getValue();
        }

        if (!(decoded instanceof RequestContext context)) {
            throw new InvalidRequestContextException(
                    "Unexpected RequestContext XML type");
        }

        String correlationId = context.getCorrelationId();
        String tenantCode = context.getTenantCode();

        if (correlationId == null || correlationId.isBlank()
                || correlationId.length() > 64) {
            throw new InvalidRequestContextException(
                    "Invalid correlation identifier");
        }

        if (tenantCode == null || tenantCode.isBlank()) {
            throw new InvalidRequestContextException(
                    "Missing tenant code");
        }

        return new RequestContextData(
                correlationId.trim(), tenantCode.trim());
    }
}
```

Đây là mẫu code để minh họa adapter; `RequestContext` là generated JAXB type và `InvalidRequestContextException` là exception ứng dụng cần định nghĩa. `RequestContextData` có thể là Java record:

```java
public record RequestContextData(
        String correlationId,
        String tenantCode) {}
```

Cần bảo đảm `RequestContextDecoder` nhận **marshaller của Header JAXB package**, không dùng nhầm context chỉ chứa Body classes. Vì `@SoapHeader` chọn QName, việc unmarshal bên trong decoder cần xác nhận kiểu JAXB và (khi cần) đúng root QName thêm một lần để giảm nhầm lẫn do binding tùy biến.

**Lưu ý:** validator của XSD và quy tắc authorization không được thay thế bằng `String.trim()`. Ví dụ trên chỉ minh họa kiểm tra tối thiểu khi chuyển đổi vào application data; trong hệ thống thật cần schema validation và các chính sách về độ dài, ký tự, tenant ID theo hợp đồng.

### 8.1. Cấu hình OXM cho riêng Header

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;

@Configuration
public class OrderHeaderOxmConfig {

    @Bean("requestContextMarshaller")
    public Jaxb2Marshaller requestContextMarshaller() {
        Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
        marshaller.setContextPath("com.example.orders.header.v1");
        return marshaller;
    }
}
```

Bean `Jaxb2Marshaller` thực hiện cả `Marshaller` và `Unmarshaller`, nên có thể inject vào decoder và client callback tương ứng. Nếu context có nhiều beans loại `Marshaller`/`Unmarshaller`, hãy dùng `@Qualifier("requestContextMarshaller")` hoặc explicit wiring, tránh injection ambiguity.

Đây là ví dụ Jakarta JAXB theo Spring Framework/Spring-WS hiện đại; các generated classes phải dùng `jakarta.xml.bind.annotation.*`. Với Spring-WS/Java EE cũ dựa trên `javax.xml.bind.*`, cần chọn generator/runtime phù hợp và không trộn hai hệ annotation.

### 8.2. Khi schema sinh `JAXBElement<RequestContext>`

Nếu generated class thiếu `@XmlRootElement`, `ObjectFactory` có thể cung cấp factory method tạo `JAXBElement<RequestContext>`. Decoder ở trên đã có bước unwrap; phía gửi phải **marshal JAXBElement root** đúng QName thay vì chỉ marshal raw class.

Không dùng chuỗi thay prefix hoặc XML string substitution để chuyển v1↔v2; cách đó dễ phá namespace, dữ liệu và XML signature.

## 9. Header bắt buộc, tùy chọn hoặc xuất hiện trùng

`@SoapHeader` làm việc theo **QName**, nhưng hợp đồng phải trả lời các tình huống không hoàn hảo. Không tự suy luận rằng header luôn hiện diện chỉ vì request test mẫu có nó.

| Tình huống | Rủi ro | Chính sách nên định nghĩa |
| --- | --- | --- |
| `RequestContext` hiện diện một lần, đúng schema | Trường hợp bình thường | Unmarshal, validate, gắn vào context của use case. |
| Header vắng mặt | Không có metadata cần thiết | Từ chối với lỗi có cấu trúc nếu required; chỉ dùng default khi được công bố. |
| Cùng QName xuất hiện nhiều lần | Có thể chọn nhầm phần tử hoặc bỏ qua phần tử trái ý | Phải định nghĩa cardinality; với header singleton, từ chối bản trùng. |
| QName đúng nhưng field thiếu/sai kiểu | Có thể đi qua nếu không bật validation | XSD/schema validation hoặc kiểm tra decoder. |
| Header namespace v2 gửi vào v1 | Không match `@SoapHeader` v1 | Từ chối hoặc xử lý theo version contract rõ. |
| Header ở sai `actor/role` | Có thể dành cho node khác | Tôn trọng quy tắc SOAP targeting. |
| `mustUnderstand` nhưng không được xử lý | Vi phạm yêu cầu của sender | SOAP `MustUnderstand` Fault theo phiên bản và vai trò node. |
| Header chứa XML quá lớn hoặc ngoại tham chiếu | Rủi ro memory/XXE/DoS | Giới hạn kích thước, depth, parser security. |

### 9.1. Vì sao không giả định `@SoapHeader` tự từ chối trùng?

Annotation chỉ xác định header QName. Cách framework chọn hoặc expose các phần tử khi có trùng tùy resolver/stack, và **không nên dùng việc nhận được một `SoapHeaderElement` làm bằng chứng Header không có bản trùng**.

Nếu chính sách yêu cầu singleton, kiểm tra số lượng matching header elements ở một interceptor hoặc một adapter đọc toàn bộ `SoapHeader`; thử cụ thể trường hợp trùng để tránh “header confusion”. Tùy API, có thể truy cập request `SoapMessage` qua `MessageContext` rồi duyệt `SoapHeader.examineAllHeaderElements()` và so QName chính xác.

### 9.2. Header tùy chọn: đừng phụ thuộc hành vi thiếu tham số

Nếu optional header là requirement, hãy kiểm tra resolver Spring-WS đang sử dụng xử lý header vắng mặt ra sao, thay vì đoán nó luôn truyền `null`. Với nhu cầu duyệt header linh hoạt, có thể chủ động lấy `SoapMessage` từ `MessageContext` tại boundary:

```java
public void inspectRequestHeader(MessageContext messageContext) {
    SoapMessage message =
            (SoapMessage) messageContext.getRequest();
    SoapHeader header = message.getSoapHeader();

    java.util.Iterator<SoapHeaderElement> blocks =
            header.examineAllHeaderElements();

    while (blocks.hasNext()) {
        SoapHeaderElement block = blocks.next();
        // Chỉ xử lý những QName được contract cho phép.
        // Phát hiện missing/duplicate/mustUnderstand khi cần.
    }
}
```

Đây là phương thức minh họa trong một SOAP adapter/interceptor chứ không phải endpoint hoàn chỉnh; cần imports Spring-WS tương ứng. Nếu dùng một thư viện SOAP message factory khác, hãy đối chiếu API/behavior. Đối với header required và đơn giản, `@SoapHeader` vẫn là lựa chọn dễ đọc hơn.

### 9.3. Nên kiểm tra header ở đâu?

- **SOAP interceptor/adapter**: sự tồn tại, QName, duplicate, mustUnderstand/actor/role và schema.
- **Decoder**: chuyển XML sang Java context và kiểm tra dữ liệu shape đơn giản.
- **Security interceptor**: chữ ký, token, timestamp, certificate và authenticity.
- **Application service**: caller có được quyền dùng tenant và truy cập order ID hay không.

Không dồn mọi kiểm tra vào controller-like endpoint nếu có nhiều operation cùng dùng một header contract.

## 10. Client gửi SOAP Header bằng WebServiceTemplate

Phía client cần tạo `RequestContext` JAXB object từ generated Header XSD, marshal nó vào **SOAP Header**, đồng thời marshal `GetOrderRequest` vào **SOAP Body**.

`WebServiceTemplate.marshalSendAndReceive(...)` hỗ trợ `WebServiceMessageCallback` để bổ sung Header và điều chỉnh SOAPAction sau khi framework đã tạo request message.

```java
import org.springframework.oxm.Marshaller;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.soap.SoapMessage;

public final class OrderSoapClient {
    private final WebServiceTemplate template;
    private final Marshaller headerMarshaller;

    public OrderSoapClient(WebServiceTemplate template,
                           Marshaller headerMarshaller) {
        this.template = template;
        this.headerMarshaller = headerMarshaller;
    }

    public Object getOrder(GetOrderRequest request,
                           RequestContext context) {

        return template.marshalSendAndReceive(
            "https://soap.example.invalid/ws/orders",
            request,
            message -> {
                SoapMessage soap = (SoapMessage) message;
                soap.setSoapAction(
                    "urn:example:order:service:v1/GetOrder");

                // Header XML riêng với Body do template marshal.
                headerMarshaller.marshal(
                    context,
                    soap.getSoapHeader().getResult());
            }
        );
    }
}
```

Đây là ví dụ tích hợp hướng dẫn, chưa phải full runnable client: `template` phải được cấu hình marshaller/unmarshaller của **Body**, message factory, transport, timeout và Fault handling. `RequestContext` là JAXB root class sinh từ XSD header; nếu JAXB dùng `JAXBElement`, caller phải tạo JAXBElement trước khi gọi `marshal`. URI `example.invalid` là địa chỉ giả định.

### 10.1. Vì sao marshal vào `SoapHeader.getResult()`?

- Template đã marshal `request` thành Body payload.
- Callback làm việc trên `WebServiceMessage` để bổ sung Header.
- `SoapHeader.getResult()` là đích XML tại vùng Header, nên marshal một **global root header element** đúng QName.
- Nếu đã tạo `SoapHeaderElement` bên ngoài rồi lại marshal **toàn bộ root** vào kết quả của element ấy, có nguy cơ tạo **header lồng hai lần** tùy API. Hãy dùng một chiến lược rõ ràng và test XML sau khi gửi.

Kết quả cần có đúng **một** `ctx:RequestContext` trực tiếp dưới `soapenv:Header`, không phải:

```xml
<!-- Cấu trúc sai do lồng root hai lần: -->
<soapenv:Header xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
  <ctx:RequestContext xmlns:ctx="urn:example:order:context:v1">
    <ctx:RequestContext>
      ...
    </ctx:RequestContext>
  </ctx:RequestContext>
</soapenv:Header>
```

### 10.2. SOAPAction không phải SOAP Header

Trong callback:

```java
soap.setSoapAction(
    "urn:example:order:service:v1/GetOrder");
```

`SOAPAction` ở ví dụ SOAP 1.1 là binding/action metadata được vận chuyển qua HTTP theo stack, không phải một `<SOAPAction>` element cần nhét vào `soapenv:Header`. Nó phải khớp WSDL. Với SOAP 1.2, media type và Action semantics khác; không sao chép cứng SOAP 1.1 behavior.

### 10.3. SOAP Header ở response

Nếu WSDL công bố response Header, có thể đọc thông qua response callback hoặc lớp client message handling tương ứng; việc `marshalSendAndReceive` tự trả JAXB Body object không có nghĩa custom SOAP response Header cũng đã được chuyển thành business DTO. Cần thiết kế API client trả kèm context/metadata nếu caller có nhu cầu sử dụng.

## 11. `mustUnderstand`: header không chỉ là metadata tùy thích

SOAP cho phép sender đánh dấu header block **bắt buộc phải được hiểu/xử lý** bởi node được nhắm đến. Trong SOAP 1.1:

```xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ctx="urn:example:order:context:v1">
  <soapenv:Header>
    <ctx:RequestContext soapenv:mustUnderstand="1">
      <ctx:CorrelationId>CORR-1042</ctx:CorrelationId>
      <ctx:TenantCode>TENANT-A</ctx:TenantCode>
    </ctx:RequestContext>
  </soapenv:Header>
  <soapenv:Body>
    <!-- Payload theo contract -->
  </soapenv:Body>
</soapenv:Envelope>
```

`mustUnderstand="1"` biểu thị rằng node SOAP được nhắm đến phải hiểu và xử lý header theo quy tắc giao thức, hoặc phát sinh Fault phù hợp (nếu node có nghĩa vụ xử lý header đó). Không có nghĩa “xác thực thành công” hay “header có quyền cao”.

Với SOAP 1.2, cú pháp/giá trị `mustUnderstand`, cơ chế role/relay và Fault shape có khác biệt. Không giả định mọi header block được gửi đi đều do endpoint cuối trực tiếp xử lý: một số có thể dành cho intermediary.

### 11.1. Header targeting: `actor` và `role`

- SOAP 1.1 dùng thuộc tính `actor` để chỉ node nhận trách nhiệm xử lý header.
- SOAP 1.2 dùng `role` và có thêm khái niệm `relay`.
- Header không được nhắm đến node hiện tại không nhất thiết phải được xử lý như header bắt buộc của node đó.
- Việc đánh dấu `mustUnderstand` không tự động làm runtime đã thực sự “hiểu” header; cần kiểm thử với message factory, interceptor và receiver đã cấu hình.

Trong Spring-WS, `SoapHeaderElement` cho phép kiểm tra/đặt một số thuộc tính SOAP của header block (tùy API/phiên bản). Nếu custom Header cần `mustUnderstand`, phía sender phải đặt giá trị chính xác và phía receiver phải có xử lý/policy thích hợp. **Chỉ inject tham số bằng `@SoapHeader` chưa đủ để kết luận toàn bộ quy tắc mustUnderstand đã được kiểm soát.**

### 11.2. Khi nào không cần mustUnderstand?

Với correlation ID tùy chọn để tracing, một header không critical có thể được bỏ qua mà không ảnh hưởng nghiệp vụ. Nhưng nếu Header quy định tenant routing hoặc security policy bắt buộc, nên công bố ràng buộc rõ trong WSDL/policy và kiểm thử khả năng từ chối thông điệp không tương thích.

Không dùng `mustUnderstand` thay cho schema validation, WS-Security signature validation hoặc authorization.

## 12. SOAP Header khác với WS-Security Header

Một SOAP message có thể có cả custom context Header và Header chuẩn `wsse:Security`:

```xml
<soapenv:Header
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ctx="urn:example:order:context:v1"
    xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">

  <ctx:RequestContext>
    <ctx:CorrelationId>CORR-1042</ctx:CorrelationId>
    <ctx:TenantCode>TENANT-A</ctx:TenantCode>
  </ctx:RequestContext>

  <wsse:Security>
    <!-- Token/chữ ký/mã hóa theo policy đã thỏa thuận -->
  </wsse:Security>
</soapenv:Header>
```

Đây là phác họa hình dạng của Header; một WS-Security header thực sự cần đầy đủ cấu trúc token, signature, timestamp, key references theo profile và không được viết tay qua ví dụ tối giản.

**Không dùng `@SoapHeader` để tự kiểm tra XML Signature bằng cách đọc `wsse:Security` như một chuỗi.** Hãy sử dụng stack security chuyên dụng và interceptor tương thích (ví dụ tích hợp WSS4J trong cấu hình Spring-WS), kiểm tra cryptographic signature, replay/timestamp, certificate trust và các reference thực sự được ký.

### 12.1. TenantCode là dữ liệu do client khai báo

Giả sử user A có quyền trên `TENANT-A` nhưng gửi Header:

```xml
<ctx:TenantCode>TENANT-B</ctx:TenantCode>
```

Nếu endpoint chỉ đọc trường rồi gọi repository theo tenant B, hệ thống có nguy cơ **cross-tenant data exposure**.

Luồng đúng:

1. Transport/security boundary xác thực caller (TLS/mTLS, token hoặc WS-Security theo policy).
2. Caller identity được đưa vào security/application context đã tin cậy.
3. Decoder đọc `TenantCode` như một **yêu cầu chọn tenant**, không coi là quyền.
4. Application authorization kiểm tra caller có quyền trên tenant được yêu cầu và resource cụ thể.
5. Chỉ khi hợp lệ mới truy vấn/trả dữ liệu.

Đánh dấu `mustUnderstand` không làm bước 4 tự xảy ra; một Header có chữ ký đúng cũng chưa bảo đảm caller được phép truy cập mọi tenant.

### 12.2. Chữ ký có bảo vệ custom Header không?

Có thể WS-Security policy yêu cầu ký SOAP Body nhưng không ký `RequestContext`, hoặc yêu cầu ký cả hai. Nếu tenant code ảnh hưởng quyền/routing, phải xác định **thành phần nào được ký và xác thực** theo policy và threat model, tránh header bị thay đổi bởi trung gian.

Không tự ý parse rồi reserialize SOAP message đã ký khi không cần; XML canonicalization, signature references và processing order có thể làm chữ ký hỏng hoặc tạo rủi ro xử lý sai phần tử.

### 12.3. XML parser cũng cần an toàn

Cấu hình JAXB/XML parser/schema loader cần chống external entity, DTD/entity expansion khi không cần, giới hạn độ sâu/kích thước XML và kiểm soát import từ nguồn ngoài. Chữ ký WS-Security hợp lệ không thay thế việc bảo vệ XML parser hoặc kiểm tra dữ liệu đầu vào.

## 13. Truyền correlation ID và application context

### 13.1. Correlation ID phục vụ điều gì?

Một correlation ID có thể được ghi vào:

- Log của SOAP client, reverse proxy, Spring-WS endpoint và downstream adapter.
- Trace context khi ứng dụng tích hợp tracing framework.
- Audit event cho một lệnh nghiệp vụ.
- SOAP Fault detail nếu hợp đồng cho phép và thông tin không nhạy cảm.

Khi nhận request, cần:

1. Kiểm tra correlation ID có format/độ dài hợp lệ.
2. Nếu absent và contract cho phép, sinh ID nội bộ bằng cơ chế chuẩn của ứng dụng.
3. Không dùng correlation ID làm authentication token, secret hoặc idempotency key nếu chưa có quy tắc nghiệp vụ.
4. Khi ghi log, không đưa nó vào high-cardinality metric labels gây tăng chi phí.
5. Nếu trả lại trong response, công bố header/Body contract rõ, không tự thêm vào output bất ngờ.

### 13.2. Không dựa vào ThreadLocal như nguồn context duy nhất

Một ứng dụng có thể có MDC hoặc security context gắn theo request thread. Nhưng nếu endpoint gọi `@Async`, CompletableFuture, broker worker hoặc reactive processing, **ThreadLocal không tự được truyền đến mọi luồng hoặc process**.

Ví dụ hướng tiếp cận rõ ràng:

```java
public record RequestExecutionContext(
        String correlationId,
        String authenticatedCallerId,
        String authorizedTenantId) {}

public interface OrderQueryService {
    OrderSnapshot findOrder(
        RequestExecutionContext context,
        String orderId);
}
```

Endpoint tạo `RequestExecutionContext` từ **correlation ID đã kiểm tra**, **caller đã xác thực** và **tenant đã được phép dùng**, rồi truyền bằng tham số khi cần. Domain vẫn không cần biết `SoapHeaderElement` hay XML namespace.

Không nên truyền toàn bộ SOAP Header xuống domain hoặc serialize một object chứa certificate/private key vào queue chỉ để giữ context.

### 13.3. Correlation ID không phải trace ID theo mặc định

Distributed tracing standards có khái niệm trace/span IDs với quy tắc và định dạng riêng. Một custom `CorrelationId` có thể được nối vào hệ thống trace theo thiết kế, nhưng đừng mặc định chúng tương đương hoặc cho phép sender tự quyết định mọi trace metadata mà không kiểm soát.

## 14. Header có version và khả năng tương tác nhiều nền tảng

Một SOAP Header là **public contract** nếu client phải gửi nó.

Ví dụ v1:

```text
{urn:example:order:context:v1}RequestContext
```

Khi thêm thuộc tính bắt buộc hay đổi nghĩa `TenantCode`, có thể cần phát hành v2:

```text
{urn:example:order:context:v2}RequestContext
```

Với `@SoapHeader`, lựa chọn QName trong annotation là **cụ thể**; nếu bên gọi gửi v2 nhưng endpoint chỉ chọn v1, code không thể dựa vào một thứ tự prefix để tự chuyển đổi.

### 14.1. Hai hướng tổ chức

- **Header version riêng**: endpoint v1/v2 hoặc interceptor/decoder theo QName; dùng WSDL/binding tương ứng.
- **Header chung ổn định**: cùng một context header có các trường cốt lõi không đổi cho nhiều version Body, nhưng phải quản lý tương thích chặt khi mở rộng.

Không nhất thiết phải tăng Header namespace mỗi lần tăng Body version. Quyết định tùy vào ý nghĩa và vòng đời riêng của Header contract.

### 14.2. Những thay đổi cần kiểm thử

| Thay đổi Header | Rủi ro |
| --- | --- |
| Đổi QName của root Header | `@SoapHeader` v1 không match. |
| Thêm trường required | Client cũ gửi thiếu; server mới có thể từ chối. |
| Thêm trường optional | JAXB/validator cũ có thể không chấp nhận khi nhận response/header mới. |
| Đổi thứ tự `xs:sequence` | XML hợp lệ cũ có thể trở thành sai XSD. |
| Đổi SOAP 1.1 sang SOAP 1.2 | SOAP Envelope và mustUnderstand/role semantics khác. |
| Đánh dấu mustUnderstand bắt buộc | Client/intermediary không hiểu Header có thể Fault. |
| Thay WS-Security signing scope | Header có thể không được bảo vệ theo policy hoặc chữ ký bị sai. |

### 14.3. Kiểm thử Java/JAXB, .NET và SOAP stack khác

- Cùng WSDL phải được các toolchain mục tiêu đọc được, đặc biệt `soap:header` và `wsdl:part`.
- JAXB có thể sinh `JAXBElement<T>`; .NET có thể sinh property/header class hoặc proxy configuration khác.
- Header không nằm trong Body: kiểm tra XML gửi thực, đừng chỉ assert object client.
- Prefix có thể thay đổi nhưng QName phải đúng.
- Kiểm tra receiver xử lý `mustUnderstand`, duplicate header, namespace v1/v2 và SOAPAction theo hợp đồng.
- Nếu có WS-Security, thử **message đã ký thật** của client khác nền tảng.

## 15. SOAP Fault và xử lý lỗi Header

Một số tình huống cần Fault hoặc từ chối theo policy:

| Tình huống | Phân loại | Hành vi cần thiết |
| --- | --- | --- |
| `RequestContext` thiếu nhưng contract bắt buộc | Contract/validation error | Không gọi nghiệp vụ; phản hồi lỗi theo WSDL/soap policy. |
| Header root sai QName | Header mapping/contract error | Không tự nhận thành Header đúng; ghi metadata an toàn. |
| Header trùng QName | Header ambiguity | Từ chối singleton duplicate nếu policy quy định. |
| `mustUnderstand` được nhắm đến nhưng không xử lý được | SOAP protocol error | Fault MustUnderstand theo SOAP version. |
| XML sai schema | Schema validation error | Chặn trước business use case khi được cấu hình. |
| Token/chữ ký/chứng chỉ không hợp lệ | Security error | Từ chối và không tiết lộ chi tiết bí mật. |
| Caller không có quyền trên TenantCode | Authorization/business security | Không truy cập dữ liệu tenant; mã lỗi công khai theo chính sách. |
| Database timeout sau khi Header được đọc | Application/infrastructure error | Phân biệt Fault với timeout không có SOAP response. |

### 15.1. SOAP 1.1 Fault minh họa cho Header không được hiểu

```xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
  <soapenv:Body>
    <soapenv:Fault>
      <faultcode>soapenv:MustUnderstand</faultcode>
      <faultstring>Required SOAP header was not understood</faultstring>
    </soapenv:Fault>
  </soapenv:Body>
</soapenv:Envelope>
```

Đây là ví dụ minh họa **cấu trúc SOAP 1.1 Fault**. Không có nghĩa mọi header thiếu đều phải phát sinh `MustUnderstand`: lỗi thiếu custom Header theo contract có thể là lỗi validation/Client Fault, trong khi `MustUnderstand` áp dụng khi một header *đã được gửi*, được target đúng node, đánh dấu mandatory và không được hiểu/xử lý.

SOAP 1.2 có định dạng Fault khác. Spring-WS có endpoint exception resolvers và security interceptors tương ứng, nhưng ánh xạ exception sang fault code/reason/detail đúng WSDL cần được cấu hình và kiểm thử; không nên throw một exception Java nội bộ rồi giả định detail XML sẽ xuất hiện đúng.

### 15.2. Không hứa rằng đọc Header đồng nghĩa xử lý được mọi Fault

`@SoapHeader` cung cấp một đối tượng header đã chọn, không tự đăng ký tất cả fault mappings hay quyết định HTTP status. Logic Fault thuộc message protocol/exception resolution; HTTP timeout, TLS handshake failure hoặc proxy rejection có thể không có SOAP Fault nào để client đọc.

### 15.3. Khi một Header không hợp lệ sau khi xác thực

Nếu `TenantCode` bị từ chối vì caller không có quyền, tránh gửi “tenant này tồn tại/không tồn tại” hoặc chi tiết phân quyền không cần thiết trong Fault. Có thể trả mã lỗi công khai chung, correlation ID và log chi tiết trong hệ thống nội bộ có bảo vệ.

## 16. Cách kiểm thử @SoapHeader

Một bộ test tốt có ít nhất ba tầng: **decoder**, **Spring-WS endpoint mapping** và **HTTP/SOAP interoperability**.

### 16.1. Unit test decoder

Dùng `SoapHeaderElement` giả lập với `Source` chứa `RequestContext` XML hợp lệ và không hợp lệ, sau đó assert:

- `CorrelationId` và `TenantCode` được ánh xạ chính xác.
- Khi JAXB trả `JAXBElement<T>`, decoder unwrap đúng.
- Kiểu root không mong đợi bị từ chối.
- Trường trống/quá dài bị từ chối theo policy.
- Không làm lộ toàn bộ XML hoặc credentials trong thông báo lỗi.

Với decoder dựa trên Spring OXM, có thể integration-test bằng `Jaxb2Marshaller` thật và XSD thật để xác minh QName, schema validation và annotation JAXB.

### 16.2. Endpoint test với SOAP Header thật

Dựng Spring-WS application context, gửi SOAP XML chứa cả Header và Body, rồi xác minh:

1. Request được định tuyến bởi `@PayloadRoot` của Body.
2. `@SoapHeader` nhận **đúng** `RequestContext` QName.
3. Decoder chuyển Header thành context và gọi application service đúng một lần.
4. Header vắng mặt/trùng/sai namespace không bị âm thầm bỏ qua nếu contract yêu cầu.
5. Identity/tenant authorization được thực hiện trước truy vấn dữ liệu.
6. Response Body vẫn tuân XSD dù prefix XML thay đổi.
7. WS-Security interceptor từ chối signature/timestamp/token sai theo policy.

Spring-WS có test support như `MockWebServiceClient` để thử endpoint ở mức application context, nhưng **không giả định một payload-only matcher tự kiểm tra SOAP Header**. Hãy tạo request message có Header qua API test tương ứng hoặc dùng integration test qua HTTP/transport để kiểm tra Envelope hoàn chỉnh.

### 16.3. Kiểm thử SOAP client Header

Với `WebServiceTemplate` client callback:

- Mock hoặc ghi lại outbound SOAP message sau callback.
- Xác minh chỉ một `ctx:RequestContext` nằm trực tiếp trong `Header`.
- Body vẫn có `ord:GetOrderRequest` riêng, không lẫn Header content.
- SOAPAction và Content-Type/Envelope version phù hợp WSDL.
- Header QName đúng khi prefix thay đổi.
- Nếu contract yêu cầu `mustUnderstand`, nó được tạo bằng đúng thuộc tính SOAP version và receiver chấp nhận.
- Nếu có ký số, xác minh phần Header cần bảo vệ được ký theo policy và không bị middleware sửa sau khi ký.

### 16.4. Ma trận kiểm thử biên

| Ca | Kết quả mong đợi |
| --- | --- |
| Header đúng QName, payload đúng QName | Endpoint nhận đúng hai tham số. |
| Prefix Header đổi, namespace giữ nguyên | `@SoapHeader` vẫn chọn đúng. |
| Header không namespace | Không bị hiểu nhầm thành context đúng. |
| Header v1 gửi đến endpoint đòi v2 | Hành vi lỗi/version đúng contract. |
| Thiếu Header required | Chặn trước use case theo policy đã công bố. |
| Header trùng QName | Từ chối nếu hợp đồng yêu cầu singleton. |
| `CorrelationId` vượt chiều dài | Validation/decoder chặn. |
| `TenantCode` không được phân quyền | Không đọc dữ liệu tenant khác. |
| SOAP mustUnderstand không được thỏa | Fault đúng SOAP version/targeting rules. |
| Chữ ký WS-Security không hợp lệ | Security interceptor từ chối. |
| HTTP/TLS failure | Client phân biệt transport error và SOAP Fault. |
| Java/JAXB và .NET gửi cùng WSDL | XML Headers/Body đều tương thích. |

### 16.5. Không chỉ kiểm thử object trong bộ nhớ

Một object JAXB có `TenantCode="TENANT-A"` chưa chứng minh XML do client sinh đúng QName, đúng namespace hoặc đúng vị trí `Header`. Bằng chứng tương thích là **SOAP message thực được marshal, gửi, xác thực và xử lý** theo WSDL/XSD/policy tương ứng.

## 17. Chọn @SoapHeader hay interceptor?

Hai cơ chế phục vụ mục tiêu khác nhau:

| Tình huống | Nên cân nhắc |
| --- | --- |
| Một endpoint cần đọc một custom Header rõ QName | `@SoapHeader` + `SoapHeaderElement`, dễ hiểu và gần logic handler. |
| Nhiều endpoints dùng chung correlation ID | Interceptor/adapter tạo context chung, endpoint chỉ nhận application data cần thiết. |
| Kiểm tra duplicate Header, chính sách cardinality chung | Interceptor hoặc boundary validator duyệt toàn bộ SOAP Header. |
| WS-Security signature/token/timestamp | Security interceptor/stack tiêu chuẩn, không tự parse chữ ký trong endpoint. |
| Authorization theo tenant và order | Application/security service sau xác thực danh tính. |
| HTTP Authorization, TLS certificate identity | Transport/security boundary, không phải `@SoapHeader`. |
| Header optional phức tạp | Custom resolver/adapter hoặc đọc `MessageContext` rõ ràng. |

**Không phải endpoint nào cũng cần tự đọc toàn bộ Header.** Nếu nhiều operation dùng cùng context, việc dời phần parsing/validation chung vào adapter giúp tránh trùng code và kiểm soát security nhất quán.

Nhưng cũng không nên xây một interceptor ghi dữ liệu nghiệp vụ hoặc thực hiện transaction chỉ vì nó có quyền đọc request sớm hơn endpoint.

## 18. Hiệu năng, logging và vòng đời context

### 18.1. Tái sử dụng JAXB/OXM cấu hình

Khởi tạo JAXB context cho từng request tạo chi phí không cần thiết. Nên dùng `Jaxb2Marshaller` bean tái sử dụng. Không lưu `SoapHeaderElement`/`WebServiceMessage` lâu hơn vòng đời request hoặc chuyển nguyên object này vào background thread; đó là đối tượng gắn với message processing.

Khi một header chứa dữ liệu lớn, việc luôn tạo DOM trong bộ nhớ có thể tăng GC/memory. Hãy đo trước khi tối ưu, giới hạn kích thước message và dùng XML parser configuration an toàn.

### 18.2. Logging an toàn

Một log thích hợp có thể chứa:

```text
operation=GetOrder
contractVersion=v1
correlationId=CORR-1042
result=SUCCESS
durationMs=84
```

Nhưng tránh ghi mặc định:

- Toàn bộ SOAP Header nếu nó chứa WS-Security token hoặc chữ ký.
- Full SOAP Body chứa dữ liệu cá nhân/tài chính.
- Private key, certificate secrets, mật khẩu.
- Giá trị tenant chỉ định nếu có chính sách hạn chế lộ thông tin khách hàng.

Đối với metrics, không dùng correlation ID làm label vì số lượng giá trị rất lớn; dùng operation, contract version và mã lỗi ổn định.

### 18.3. Async và message broker

Nếu endpoint gửi một task vào queue, không giả định MDC/SecurityContext ThreadLocal sẽ tự truyền sang worker. Chuyển các trường context đã được chọn lọc/kiểm tra và thuộc nghiệp vụ cần thiết; bên worker phải xác định lại trust boundary theo thiết kế. Không gửi toàn bộ token/certificate từ SOAP Header sang queue trừ khi thật sự cần và có chính sách bảo vệ.

## 19. Những anti-pattern thường gặp

### 19.1. Dùng SOAP Header làm “user đã đăng nhập”

`<ctx:TenantCode>TENANT-A</ctx:TenantCode>` chỉ là XML client gửi. Nếu sử dụng trực tiếp làm permission, caller có thể sửa thành tenant khác.

**Sửa:** xác thực caller qua policy đã kiểm chứng, kiểm tra quyền với requested tenant trong application service.

### 19.2. Dùng prefix để tìm Header

Regex `<ctx:RequestContext>` sẽ hỏng khi client đổi prefix hoặc dùng default namespace.

**Sửa:** `@SoapHeader` với expanded QName hoặc parser namespace-aware.

### 19.3. Đặt RequestContext vào Body chỉ để JAXB dễ dùng

Nếu Header là một phần contract SOAP, chuyển nó vào Body có thể phá WSDL và client khác nền tảng.

**Sửa:** giữ đúng khu vực Header, dùng `SoapHeaderElement` và JAXB decoder riêng.

### 19.4. Giả định JAXB sẽ tự map mọi SOAP Header

`@RequestPayload` chỉ chọn Body; Bean `Jaxb2Marshaller` không tự bảo đảm custom header đã được unmarshal vào tham số DTO tùy ý.

**Sửa:** dùng `@SoapHeader` và decode qua `getSource()`, hoặc custom argument resolver nếu có yêu cầu rõ.

### 19.5. Vừa tạo header element, vừa marshal root bên trong

Điều này có thể tạo XML lồng hai `RequestContext`.

**Sửa:** marshal root trực tiếp vào `SoapHeader.getResult()`, hoặc dùng API thêm element rồi chỉ ghi **nội dung** của nó theo chiến lược nhất quán; kiểm tra XML outbound thật.

### 19.6. Dùng `mustUnderstand` để thay authorization

Một header được “hiểu” theo SOAP protocol không bảo đảm nó trung thực hay caller được quyền dùng tenant.

**Sửa:** phân biệt processing, signature validation và authorization.

### 19.7. Đọc Header và làm mất signature

Middleware parse/serialize lại message đã ký mà không tôn trọng canonicalization/reference có thể làm hỏng XML signature hoặc tạo security ambiguity.

**Sửa:** để stack WS-Security thực hiện validation theo profile; hạn chế sửa những phần đã ký và kiểm thử end-to-end.

### 19.8. Không công bố Header trong WSDL

Java client nội bộ hoạt động vì tự thêm Header, còn đối tác sinh proxy từ WSDL không biết phải gửi gì.

**Sửa:** đưa custom Header vào XSD/WSDL binding/contract guide, chạy codegen và interoperability tests.

## 20. Bài tập thực hành

### Bài tập 1 — Chọn SOAP Header đúng QName

Dùng hai SOAP requests: một có prefix `ctx`, một có prefix `x`, nhưng cùng namespace `urn:example:order:context:v1`. Xây dựng handler `@SoapHeader` và chứng minh cả hai chọn cùng header block. Thử Header thiếu namespace và xác định hành vi lỗi.

### Bài tập 2 — JAXB decode Header

Sinh JAXB class `RequestContext` từ XSD mục 5.2. Tạo `RequestContextDecoder` dùng Spring OXM `Unmarshaller`, kiểm thử trường hợp JAXB object trực tiếp, `JAXBElement`, correlation ID rỗng và dữ liệu sai kiểu. Ghi lại XML thực để đối chiếu QName.

### Bài tập 3 — Tạo outbound Header

Dùng `WebServiceTemplate.marshalSendAndReceive` để gửi `GetOrderRequest` và thêm `RequestContext` trong callback. Xác nhận outbound SOAP Envelope có Body và Header đúng thứ tự/namespace, không có hai phần tử `RequestContext` lồng nhau.

### Bài tập 4 — Header thiếu, trùng và mustUnderstand

Dùng integration test để gửi Header vắng mặt, hai Header cùng QName và Header `soapenv:mustUnderstand="1"` không được hiểu theo cấu hình. Phân tích ca nào phải bị từ chối, ca nào có thể được bỏ qua và Fault code thuộc SOAP 1.1 hay SOAP 1.2.

### Bài tập 5 — Tenant spoofing

Caller được xác thực chỉ có quyền trên `TENANT-A`. Gửi `RequestContext` với `TenantCode=TENANT-B`. Thiết kế authorization check không tin Header client và chứng minh application không truy vấn dữ liệu tenant B dù XML hợp lệ.

### Bài tập 6 — Interoperability

Tạo client Java/JAXB và client .NET hoặc SOAP stack khác từ WSDL của mục 6. Kiểm tra operation, `soap:header`, QName, SOAPAction, timezone nếu mở rộng context, mustUnderstand và WS-Security policy. Đánh giá tình huống một client không sinh Header property như mong đợi: cần cấu hình proxy hay gửi callback XML theo contract?

## 21. Checklist trước khi phát hành

- [ ] SOAP Header và Body có XSD namespaces/QNames rõ ràng, không phụ thuộc prefix.
- [ ] `@PayloadRoot` chọn đúng Body operation; `@SoapHeader` chọn đúng Header QName.
- [ ] Tham số Handler dùng `SoapHeaderElement`/kiểu được adapter hỗ trợ, không giả định tự map tùy ý.
- [ ] Decoder chuyển Header XML thành application data, không rò rỉ kiểu SOAP xuống domain.
- [ ] JAXB classes/`Jaxb2Marshaller` đúng version Jakarta hoặc `javax` theo stack thực tế.
- [ ] WSDL 1.1 có `soap:header` và `wsdl:message/part` phù hợp; XSD imports resolve được.
- [ ] Client callback tạo Header đúng chỗ, không lồng root hai lần và không đặt SOAPAction thành custom SOAP element.
- [ ] Header required/optional, singleton/duplicate, absent/invalid có chính sách rõ.
- [ ] `mustUnderstand`, actor/role và SOAP 1.1/1.2 được kiểm thử với stack thực.
- [ ] Tenant identity/authorization không được suy ra chỉ từ một chuỗi Header chưa xác thực.
- [ ] WS-Security signature, timestamp, certificate trust và XML parser hardening được cấu hình nếu policy yêu cầu.
- [ ] Correlation ID được kiểm soát độ dài/format và không lẫn với secret/idempotency key nếu chưa được công bố.
- [ ] SOAP Fault và transport errors được phân biệt; không lộ chi tiết bảo mật.
- [ ] Có test Header theo QName, sai namespace, thiếu/trùng, SOAP Header v1/v2 và outbound Envelope.
- [ ] Có client interoperability tests với Java/JAXB và nền tảng đối tác.
- [ ] Logging/tracing không lưu toàn bộ dữ liệu nhạy cảm hoặc dùng correlation ID làm metric label.

## 22. Tổng kết

**`@SoapHeader` trong Spring Web Services ánh xạ một custom SOAP Header element được xác định bằng QName vào tham số handler**, thường là `SoapHeaderElement`. Endpoint có thể đồng thời nhận JAXB Body qua `@RequestPayload` và Header qua `@SoapHeader`, sau đó sử dụng OXM/JAXB để chuyển Header XML thành context Java đã kiểm tra cấu trúc.

Điều cốt lõi là **đúng ranh giới**: SOAP Header khác HTTP Header và SOAP Body; Header do client khai báo khác danh tính/quyền được xác thực; `mustUnderstand` khác authorization; JAXB parsing khác WS-Security validation. Khi công bố Header trong XSD/WSDL, kiểm tra namespace và cardinality, quản lý certificate/signature đúng policy, giữ application context độc lập với SOAP runtime và thử bằng message thật của nhiều client, Spring-WS service sẽ tích hợp ổn định và dễ vận hành trong môi trường doanh nghiệp.
