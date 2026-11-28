# marshalSendAndReceive và trao đổi đối tượng JAXB

## 1. Vai trò của marshalSendAndReceive trong SOAP client

Trong module **SPRING_WEB_SERVICES**, ta phát triển dịch vụ SOAP theo hướng **contract-first**: XSD/WSDL là hợp đồng công khai; JAXB ánh xạ dữ liệu XML sang đối tượng Java; Spring Web Services (Spring-WS) xây dựng endpoint và SOAP client, xử lý SOAP Fault, interceptor, XML/WS-Security và kiểm thử tương thích giữa các hệ thống.

Ở phía máy khách, thao tác thường gặp là:

~~~java
Object response = webServiceTemplate.marshalSendAndReceive(request);
~~~

`marshalSendAndReceive` của `WebServiceTemplate` dùng `Marshaller` chuyển đối tượng request thành **XML payload**, gửi SOAP message qua transport đã cấu hình, rồi dùng `Unmarshaller` chuyển XML response trở lại đối tượng Java.

Nó giúp lập trình viên gọi SOAP như một lời gọi Java mà **không cần tự ghép từng thẻ XML**. Tuy nhiên, nó không làm mất đi trách nhiệm hiểu hợp đồng: QName, namespace URI, JAXB root element, SOAPAction/action, SOAP 1.1/1.2, XSD constraints và cơ chế Fault vẫn cần được cấu hình/kiểm thử đúng.

Ví dụ luồng:

~~~mermaid
flowchart LR
    A["OrderClient Java"] --> B["JAXB request / JAXBElement"]
    B --> C["WebServiceTemplate"]
    C --> D["Jaxb2Marshaller"]
    D --> E["SOAP Body XML"]
    E --> F["Message sender / HTTPS"]
    F --> G["SOAP server"]
    G --> H["SOAP response / Fault"]
    H --> I["Unmarshaller / Fault resolver"]
    I --> J["JAXB response hoặc exception"]
~~~

**Mục tiêu học tập**

Sau bài này, bạn có thể:

1. Giải thích `marshalSendAndReceive` hoạt động ở mức payload, SOAP message và HTTP transport.
2. Phân biệt `@XmlRootElement` và `JAXBElement<T>` khi sinh binding bằng XJC.
3. Cấu hình `Jaxb2Marshaller` và `WebServiceTemplate` với namespace/contract đúng.
4. Viết một Java client gửi request bằng `ObjectFactory` và kiểm tra response QName trước khi xử lý.
5. Chọn đúng biến thể `marshalSendAndReceive` và `SoapActionCallback`.
6. Phân loại SOAP Fault, lỗi transport, lỗi XML/XSD và lỗi JAXB một cách rõ ràng.
7. Kiểm tra hợp đồng bằng XSD validation và `MockWebServiceServer`.
8. Tránh những lỗi tương thích khi làm việc với dịch vụ SOAP doanh nghiệp dùng JAXB, XML security, WS-Security hoặc chứng chỉ.

## 2. Những thành phần tham gia một lời gọi SOAP

Một SOAP client Spring-WS điển hình có các lớp trách nhiệm sau:

| Thành phần | Vai trò | Không tự bảo đảm |
|---|---|---|
| `WebServiceTemplate` | Điều phối gửi/nhận và các bước mở rộng | Hợp đồng XML có tương thích với server |
| `Jaxb2Marshaller` | Marshal/unmarshal JAXB object ↔ XML | Mọi ràng buộc XSD nếu chưa bật schema validation |
| `WebServiceMessageFactory` | Tạo/đọc SOAP Envelope và các message representations | SOAP version đúng với WSDL nếu cấu hình sai |
| `WebServiceMessageSender` | Gửi HTTP/HTTPS hoặc transport tương ứng | Truststore, timeout, proxy tự đúng |
| `WebServiceMessageCallback` | Chỉnh request cho một lời gọi (SOAPAction/Header...) | Xử lý response/Fault |
| `ClientInterceptor` | Xử lý request, response, Fault và completion | Domain validation, retry policy hoàn chỉnh |
| `FaultMessageResolver` | Xử lý SOAP Fault | Lỗi TCP/TLS/timeout |
| `JAXB generated classes` | Diễn đạt cấu trúc XSD ở Java | Version server/client tự đồng bộ |
| `XSD/WSDL` | Nguồn quy định QName, element/type, binding | Runtime đã bật validation |

Một lời gọi thuận lợi có thể diễn ra như sau:

~~~text
Ứng dụng tạo JAXB request
    -> Marshaller viết XML vào SOAP Body
    -> callback / client interceptors xử lý message
    -> message sender gửi request qua HTTP(S)
    -> nhận SOAP response
    -> client interceptors xử lý response
    -> Unmarshaller đọc response payload sang Java
    -> ứng dụng xử lý object
~~~

Đối với lỗi:

~~~text
SOAP Fault -> fault handling / FaultMessageResolver
HTTP lỗi không có SOAP Fault -> transport/template exception
XML không đúng SOAP Envelope -> message factory/parse error
XML đúng Envelope nhưng JAXB mapping sai -> unmarshalling exception
XML hợp XSD nhưng nghiệp vụ không hợp lệ -> domain/business handling
~~~

Đừng coi tất cả các loại lỗi trên là một `RuntimeException` chung rồi tự retry như nhau.

## 3. XSD mẫu: hợp đồng GetOrder làm nguồn sự thật

Ta xây một SOAP operation tra cứu đơn hàng với namespace cố định:

~~~text
urn:example:orders:v1
~~~

Giả sử XSD ở `src/main/resources/xsd/orders-v1.xsd`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:ord="urn:example:orders:v1"
    targetNamespace="urn:example:orders:v1"
    elementFormDefault="qualified">

    <xs:simpleType name="OrderIdType">
        <xs:restriction base="xs:string">
            <xs:minLength value="1"/>
            <xs:maxLength value="30"/>
            <xs:pattern value="ORD-[0-9]+"/>
        </xs:restriction>
    </xs:simpleType>

    <xs:simpleType name="OrderStatusType">
        <xs:restriction base="xs:string">
            <xs:enumeration value="PENDING"/>
            <xs:enumeration value="PAID"/>
            <xs:enumeration value="CANCELLED"/>
        </xs:restriction>
    </xs:simpleType>

    <xs:complexType name="GetOrderRequestType">
        <xs:sequence>
            <xs:element name="orderId"
                        type="ord:OrderIdType"/>
            <xs:element name="includeHistory"
                        type="xs:boolean"
                        minOccurs="0"/>
        </xs:sequence>
    </xs:complexType>

    <xs:complexType name="GetOrderResponseType">
        <xs:sequence>
            <xs:element name="orderId"
                        type="ord:OrderIdType"/>
            <xs:element name="status"
                        type="ord:OrderStatusType"/>
            <xs:element name="note"
                        type="xs:string"
                        minOccurs="0"
                        nillable="true"/>
        </xs:sequence>
    </xs:complexType>

    <xs:element name="GetOrderRequest"
                type="ord:GetOrderRequestType"/>

    <xs:element name="GetOrderResponse"
                type="ord:GetOrderResponseType"/>
</xs:schema>
~~~

Các ràng buộc quan trọng:

- Global request element: `{urn:example:orders:v1}GetOrderRequest`.
- Global response element: `{urn:example:orders:v1}GetOrderResponse`.
- `orderId` bắt đầu bằng `ORD-` rồi đến ít nhất một chữ số.
- `includeHistory` optional và thuộc kiểu `xs:boolean`.
- `status` chỉ thuộc ba giá trị enum đã công bố.
- `note` là optional và nillable.
- Element con phải đúng thứ tự của `xs:sequence`.
- Vì `elementFormDefault="qualified"`, các child elements cũng dùng namespace v1.

### 3.1. Request và response trên dây

Một SOAP 1.1 request có dạng:

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1">
    <soap:Body>
        <ord:GetOrderRequest>
            <ord:orderId>ORD-2048</ord:orderId>
            <ord:includeHistory>true</ord:includeHistory>
        </ord:GetOrderRequest>
    </soap:Body>
</soap:Envelope>
~~~

SOAP 1.1 response:

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1">
    <soap:Body>
        <ord:GetOrderResponse>
            <ord:orderId>ORD-2048</ord:orderId>
            <ord:status>PAID</ord:status>
        </ord:GetOrderResponse>
    </soap:Body>
</soap:Envelope>
~~~

`Jaxb2Marshaller` viết và đọc **payload** `GetOrderRequest` hoặc `GetOrderResponse`. `WebServiceTemplate` và message factory đặt payload trong SOAP Body, xử lý transport và phân loại SOAP Fault.

Cần tránh nhầm:

~~~text
JAXB root: {urn:example:orders:v1}GetOrderRequest
SOAP Envelope: {http://schemas.xmlsoap.org/soap/envelope/}Envelope
~~~

Hai QName này thuộc hai lớp khác nhau. JAXB object của request không phải một object biểu diễn toàn bộ SOAP Envelope.

## 4. XJC sinh những class Java nào?

Dùng XJC/JAXB code generation trong quá trình build để sinh Java binding từ XSD. Công cụ và plugin Gradle/Maven phải phù hợp Java/Jakarta XML Bind runtime của dự án.

Với XSD có **named complex types** và global element declarations như phần 3, kết quả thường có:

~~~text
com.example.contract.orders.v1/
    GetOrderRequestType.java
    GetOrderResponseType.java
    OrderStatusType.java
    ObjectFactory.java
    package-info.java
~~~

Một model JAXB tương ứng có thể có:

~~~java
public class GetOrderRequestType {

    protected String orderId;
    protected Boolean includeHistory;

    public String getOrderId() { ... }
    public void setOrderId(String value) { ... }

    public Boolean isIncludeHistory() { ... }
    public void setIncludeHistory(Boolean value) { ... }
}
~~~

Đây là **minh họa chữ ký**. Tên accessor, kiểu nullable, cách dùng `JAXBElement` và annotations thực tế tùy phiên bản XJC và binding customizations. Với boolean optional, generated binding thường có `Boolean` thay cho primitive `boolean` để biểu diễn vắng mặt; khi XSD hoặc customization khác, kiểu cũng khác.

### 4.1. Named complex type khác global element

Trong XSD:

~~~xml
<xs:complexType name="GetOrderRequestType">...</xs:complexType>
<xs:element name="GetOrderRequest" type="ord:GetOrderRequestType"/>
~~~

`GetOrderRequestType` là **tên kiểu**. `GetOrderRequest` là **tên phần tử toàn cục** mang QName mà SOAP Body cần.

JAXB có thể sinh class cho kiểu nhưng không đánh dấu class đó bằng `@XmlRootElement`. Thay vào đó, `ObjectFactory` thường khai báo:

~~~java
@XmlElementDecl(
    namespace = "urn:example:orders:v1",
    name = "GetOrderRequest"
)
public JAXBElement<GetOrderRequestType> createGetOrderRequest(
        GetOrderRequestType value) {
    // Generated implementation.
}
~~~

Trong tình huống này, request cần được marshal bằng **`JAXBElement<GetOrderRequestType>`** có QName đúng. Không chỉ marshal một instance `new GetOrderRequestType()` rồi cho rằng JAXB tự biết tên root.

### 4.2. @XmlRootElement là trường hợp khác

Nếu XSD khai báo anonymous complex type trực tiếp trong global element:

~~~xml
<xs:element name="GetOrderRequest">
    <xs:complexType>
        <xs:sequence>
            <xs:element name="orderId" type="xs:string"/>
        </xs:sequence>
    </xs:complexType>
</xs:element>
~~~

XJC thường có thể sinh `GetOrderRequest` class được gắn `@XmlRootElement(name="GetOrderRequest", namespace=...)`. Khi đó có thể truyền object root trực tiếp cho marshaller.

**Không nên viết tài liệu như thể mọi XSD đều tạo `@XmlRootElement`.** Với schema contract-first có global elements tham chiếu named types, `JAXBElement` là trường hợp quan trọng và rất thường gặp.

### 4.3. Namespace trong package-info.java

XJC thường sinh metadata package, ví dụ:

~~~java
@jakarta.xml.bind.annotation.XmlSchema(
    namespace = "urn:example:orders:v1",
    elementFormDefault =
        jakarta.xml.bind.annotation.XmlNsForm.QUALIFIED
)
package com.example.contract.orders.v1;
~~~

Metadata này ảnh hưởng namespace XML của các elements khi marshal/unmarshal. Dự án Spring Framework 6/Spring-WS 4 dùng Jakarta XML Bind (`jakarta.xml.bind`), trong khi một số stack cũ dùng `javax.xml.bind`. Không trộn generated classes `javax` với runtime chỉ hỗ trợ `jakarta` mà không có migration strategy và phiên bản thư viện phù hợp.

### 4.4. Generated code là dữ liệu từ contract, không phải domain model

JAXB classes phản ánh XSD và đôi khi có getters trả live list, `XMLGregorianCalendar`, `BigDecimal` hoặc `JAXBElement`. Ứng dụng nên có mapper giữa JAXB DTO và domain model:

~~~text
JAXB request
    -> Contract mapper
    -> Domain command/query
    -> Business service

Business result
    -> Contract mapper
    -> JAXB response
~~~

Điều này giúp domain không phụ thuộc trực tiếp vào cấu trúc của đối tác. Một thay đổi hợp đồng v2 có thể tạo package JAXB riêng mà không phải đổi toàn bộ business logic.

## 5. Tạo JAXB request đúng root QName bằng ObjectFactory

Đối với XSD ở phần 3, ta có thể tạo request như sau:

~~~java
import jakarta.xml.bind.JAXBElement;

import com.example.contract.orders.v1.GetOrderRequestType;
import com.example.contract.orders.v1.ObjectFactory;

ObjectFactory factory = new ObjectFactory();

GetOrderRequestType request = new GetOrderRequestType();
request.setOrderId("ORD-2048");
request.setIncludeHistory(Boolean.TRUE);

JAXBElement<GetOrderRequestType> root =
    factory.createGetOrderRequest(request);
~~~

Bên trong `root` có hai phần liên quan:

1. **Tên phần tử**: `root.getName()`, một `QName`.
2. **Giá trị phần tử**: `root.getValue()`, đối tượng `GetOrderRequestType`.

Kiểm tra root:

~~~java
import javax.xml.namespace.QName;

QName expected = new QName(
    "urn:example:orders:v1",
    "GetOrderRequest"
);

assert expected.equals(root.getName());
~~~

Trong unit test thực tế dùng JUnit Assertions thay vì Java `assert` (vì `assert` có thể bị vô hiệu hóa nếu JVM không bật `-ea`).

**Mục tiêu:** Gửi đúng phần tử `GetOrderRequest` theo WSDL. Không gửi `GetOrderRequestType` làm root chỉ vì class Java có tên đó.

### 5.1. Nếu không có ObjectFactory phù hợp thì sao?

Trước hết kiểm tra XSD root element và binding đã sinh. Không nên lập tức tự tạo `JAXBElement` với QName đoán:

~~~java
// Chỉ làm cách này khi đã xác minh QName và declared type:
new JAXBElement<>(
    new QName("urn:example:orders:v1", "GetOrderRequest"),
    GetOrderRequestType.class,
    request
);
~~~

Có thể dùng constructor đó trong các trường hợp được thiết kế phù hợp, nhưng `ObjectFactory` sinh từ XSD là lựa chọn an toàn hơn vì chứa các `@XmlElementDecl` và quy tắc element factory của hợp đồng.

### 5.2. Thế nào là JAXBElement sai?

Một object như:

~~~java
new JAXBElement<>(
    new QName("urn:example:orders:v2", "GetOrderRequest"),
    GetOrderRequestType.class,
    request
);
~~~

sẽ có QName v2, dù class Java `GetOrderRequestType` đến từ binding v1. Marshaller có thể tạo XML không được server v1 chấp nhận. **Tên class đúng không cứu được QName sai.**

## 6. Cấu hình Jaxb2Marshaller

`Jaxb2Marshaller` của Spring OXM cung cấp `Marshaller` và `Unmarshaller` cho JAXB. Một cấu hình Java:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;

@Configuration
public class OrdersBindingConfiguration {

    @Bean(name = "ordersMarshaller")
    public Jaxb2Marshaller ordersMarshaller() {
        Jaxb2Marshaller marshaller =
            new Jaxb2Marshaller();

        marshaller.setContextPath(
            "com.example.contract.orders.v1"
        );

        return marshaller;
    }
}
~~~

`setContextPath` sử dụng tên **package JAXB binding**, không phải đường dẫn đến XSD. Package cần có metadata JAXB phù hợp, thường là `ObjectFactory`/`jaxb.index` hoặc cách khởi tạo context khác mà JAXB runtime hỗ trợ.

Một lựa chọn khác, khi project có generated root classes hoặc JAXB-bound classes rõ ràng, là `setClassesToBeBound(...)`. Cũng có `setPackagesToScan(...)` cho một số tình huống. Chọn cách khởi tạo JAXBContext theo cấu trúc binding thực tế; đừng trộn các phương án tùy tiện rồi khó xác định classes nào được nạp.

### 6.1. Bật XSD validation khi cần

Có thể đặt:

~~~java
import org.springframework.core.io.ClassPathResource;

marshaller.setSchema(
    new ClassPathResource("xsd/orders-v1.xsd")
);
~~~

Đây là cách giúp JAXB marshal/unmarshal với schema validation theo khả năng runtime. Nếu XSD có `xs:include`/`xs:import`, cần cung cấp resources/resolver thích hợp để schema compiler phân giải đủ các phụ thuộc.

**Quan trọng:** Không gắn schema **không có nghĩa JAXB hoàn toàn không kiểm tra gì**, nhưng cũng **không bảo đảm** các facet như `pattern`, `minOccurs`, `enumeration` và sequence đều được enforce. Với contract-first, cần các test validation rõ ràng.

### 6.2. Không tự tạo XJC classes khi runtime khởi động

`Jaxb2Marshaller` không tự sinh code từ XSD/WSDL lúc gửi SOAP. Việc sinh classes nên xảy ra ở build, còn runtime dùng lớp đã được biên dịch và metadata JAXB để marshal/unmarshal.

Quản lý version binding như quản lý phần phụ thuộc: nếu WSDL/XSD thay đổi, cần đánh giá breaking change, sinh lại code có chủ đích, chạy test và triển khai đúng gói JAXB v1/v2.

### 6.3. Tối ưu bằng bean dùng chung nhưng tránh thay cấu hình lúc chạy

Tạo `Jaxb2Marshaller` thành Spring bean thường tốt hơn việc tự khởi tạo JAXBContext cho từng SOAP call. Khi đã cấu hình và khởi tạo, marshaller do Spring quản lý có thể được sử dụng cho nhiều lời gọi theo thiết kế Spring OXM; không thay `setContextPath`/`setSchema` trong lúc có threads đang gửi request.

Những giá trị động như URL từng cuộc gọi, correlation ID hoặc SOAPAction nên truyền qua API gọi/template callback, không thay mutable bean configuration giữa các threads.

## 7. Cấu hình WebServiceTemplate cho JAXB

Ví dụ wiring:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.ws.client.core.WebServiceTemplate;

@Configuration
public class OrdersSoapClientConfiguration {

    @Bean(name = "ordersTemplate")
    public WebServiceTemplate ordersTemplate(
            @Qualifier("ordersMarshaller")
            Jaxb2Marshaller marshaller) {

        WebServiceTemplate template =
            new WebServiceTemplate();

        template.setMarshaller(marshaller);
        template.setUnmarshaller(marshaller);

        template.setDefaultUri(
            "https://partner.example.test/ws"
        );

        return template;
    }
}
~~~

Vai trò:

- `setMarshaller`: chuyển request JAXB thành XML.
- `setUnmarshaller`: chuyển response XML thành JAXB.
- `setDefaultUri`: URI dùng khi method không truyền URI tường minh.
- Message factory và message sender được cấu hình/khởi tạo theo template/framework version; với SOAP 1.1/1.2 và TLS enterprise, cần chọn rõ chúng theo hợp đồng.

`WebServiceTemplate` có thể được cấu hình bằng cách khác, ví dụ dùng `WebServiceGatewaySupport` hoặc Spring XML. Dù cách nào, kiểm tra rằng **marshaller/unmarshaller cùng hiểu phiên bản hợp đồng được gọi**.

### 7.1. Phân biệt URI và QName

Giả sử dịch vụ có endpoint URL:

~~~text
https://partner.example.test/api/order/soap
~~~

và XSD namespace:

~~~text
urn:example:orders:v1
~~~

URI transport và namespace URI có mục đích khác nhau. Đổi máy chủ/gateway không yêu cầu đổi targetNamespace; ngược lại, đổi namespace hợp đồng không được xử lý chỉ bằng cập nhật `setDefaultUri`.

### 7.2. Một template có thể gọi nhiều URI?

`WebServiceTemplate` có overload nhận URI tường minh cho từng request:

~~~java
Object result = template.marshalSendAndReceive(
    "https://staging.partner.example.test/ws",
    root
);
~~~

Giữ `defaultUri` ổn định là phù hợp cho đối tác cố định. Dùng URI per-call có thể hữu ích khi deploy staging/prod, nhưng phải quản lý danh sách host được phép và tránh nhận URL tùy ý từ người dùng không tin cậy gây SSRF hoặc rò rỉ credentials.

### 7.3. Cấu hình nhiều SOAP client

Một ứng dụng có thể gọi `OrdersService v1` và `BillingService v2`. Không nên dùng chung một JAXB package/schema/marshaller chỉ vì cả hai dùng SOAP. Mỗi client cần ít nhất:

~~~text
Client identity / contract version
    -> JAXBContext đúng package
    -> XSD đúng version
    -> SOAP message factory/binding
    -> Endpoint URI
    -> Interceptors / WS-Security policy
    -> HTTP sender / TLS trust
~~~

Khi có nhiều beans cùng type, nên dùng tên bean hoặc `@Qualifier` tránh inject sai marshaller.

## 8. Các biến thể thường dùng của marshalSendAndReceive

`WebServiceTemplate` cung cấp nhiều overload, tùy việc dùng default URI hay URI tường minh và có callback hay không.

| Mẫu gọi | Khi nào dùng |
|---|---|
| `marshalSendAndReceive(request)` | Dùng `defaultUri` đã cấu hình |
| `marshalSendAndReceive(uri, request)` | Chọn endpoint URI tường minh |
| `marshalSendAndReceive(request, callback)` | Dùng default URI và tùy chỉnh SOAP message |
| `marshalSendAndReceive(uri, request, callback)` | Chỉ định URI và callback cho lời gọi đó |

Ví dụ:

~~~java
Object result = template.marshalSendAndReceive(
    root
);
~~~

Có callback:

~~~java
Object result = template.marshalSendAndReceive(
    "https://partner.example.test/ws",
    root,
    callback
);
~~~

**Lưu ý:** `marshalSendAndReceive` nhận `Object` và trả `Object`, không có kiểu generic ràng buộc response tại compile time. Vì vậy cần kiểm tra kiểu thực tế, QName và giá trị sau khi nhận, thay vì cast thẳng với giả định “response chắc chắn giống class mong đợi”.

### 8.1. Trường hợp marshaller không được cấu hình

Nếu gọi `marshalSendAndReceive` mà template không có marshaller/unmarshaller phù hợp, sẽ phát sinh lỗi cấu hình hoặc mapping. Không nên sửa bằng cách gửi trực tiếp một Java object bất kỳ rồi hy vọng framework tự chọn JAXBContext.

Một unit test khởi tạo template/client adapter giúp bắt lỗi này trước khi deploy.

### 8.2. Khi nào dùng sendSourceAndReceive?

Nếu muốn gửi XML `Source` thay vì JAXB object, có các API như `sendSourceAndReceiveToResult`. Đó là cách làm việc trực tiếp với XML, khác mục tiêu bài này. Với contract-first và generated JAXB classes, `marshalSendAndReceive` thường giúp giảm code tạo/parse XML và giữ kiểu Java rõ hơn.

## 9. SOAPAction và WebServiceMessageCallback

Nhiều WSDL SOAP 1.1 binding quy định `soapAction` cho operation. Một client có payload QName đúng nhưng SOAPAction sai có thể bị gateway/đối tác từ chối hoặc định tuyến không như mong đợi.

Spring-WS cung cấp `SoapActionCallback`:

~~~java
import org.springframework.ws.soap.client.core.SoapActionCallback;

Object result = template.marshalSendAndReceive(
    root,
    new SoapActionCallback(
        "urn:example:orders:action:GetOrder"
    )
);
~~~

Chuỗi `urn:example:orders:action:GetOrder` chỉ là **giá trị minh họa**; phải lấy đúng từ WSDL binding thực tế. Không tự đoán SOAPAction dựa trên tên method Java.

### 9.1. QName, operation và SOAPAction khác nhau

| Khái niệm | Ví dụ | Mục đích |
|---|---|---|
| Request root QName | `{urn:example:orders:v1}GetOrderRequest` | Định danh XML payload |
| WSDL operation | `GetOrder` | Định nghĩa operation trong portType/binding |
| SOAPAction | `urn:example:orders:action:GetOrder` | Metadata action theo SOAP binding |
| Endpoint address | `https://partner.example.test/ws` | URI mạng |
| JAXB class | `GetOrderRequestType` | Cấu trúc Java cho type |

Một thay đổi SOAPAction không đồng nghĩa đổi QName; một thay đổi endpoint address không đồng nghĩa đổi namespace. Test mỗi ranh giới riêng.

### 9.2. SOAP 1.1 và SOAP 1.2

SOAP 1.1 thường dùng HTTP media type `text/xml` và header `SOAPAction`. SOAP 1.2 dùng `application/soap+xml` và có thể dùng tham số `action` của media type theo binding.

Không mặc định chuyển `SoapActionCallback` từ SOAP 1.1 sang SOAP 1.2 mà mọi đối tác sẽ chấp nhận như cũ. Chọn `SoapVersion` cho message factory và kiểm tra WSDL SOAP binding, Content-Type và yêu cầu action thực tế.

### 9.3. Callback thêm SOAP Header

Với một SOAP Header theo hợp đồng:

~~~java
import javax.xml.namespace.QName;

import org.springframework.ws.WebServiceMessage;
import org.springframework.ws.client.core.WebServiceMessageCallback;
import org.springframework.ws.soap.SoapMessage;
import org.springframework.ws.soap.SoapHeaderElement;

WebServiceMessageCallback correlationCallback =
    new WebServiceMessageCallback() {

        @Override
        public void doWithMessage(
                WebServiceMessage message) {

            SoapMessage soap = (SoapMessage) message;

            QName headerName = new QName(
                "urn:example:common:v1",
                "CorrelationId"
            );

            SoapHeaderElement element =
                soap.getSoapHeader()
                    .addHeaderElement(headerName);

            element.setText("REQ-2048");
        }
    };
~~~

Đây là ví dụ callback **chỉ khi template dùng SOAP message factory**. Nếu message không phải `SoapMessage`, cast cần được kiểm tra/phân loại. Header QName phải được đối tác chấp nhận, và với WS-Security phải được ký nếu security policy yêu cầu.

Callback khác `ClientInterceptor`: callback tập trung vào **request của lời gọi này**, còn interceptor được đăng ký trên template và có hooks request/response/Fault/completion.

## 10. Viết một gateway typed thay vì để Object tràn vào domain

Trong code nghiệp vụ, không nên lặp đi lặp lại `marshalSendAndReceive` và các cast. Tạo một adapter client có method trả kiểu domain hoặc kiểu response được kiểm tra rõ ràng.

Ví dụ đầy đủ từ binding **named complex type + JAXBElement**:

~~~java
package com.example.integration.orders;

import javax.xml.namespace.QName;

import jakarta.xml.bind.JAXBElement;

import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.soap.client.core.SoapActionCallback;

import com.example.contract.orders.v1.GetOrderRequestType;
import com.example.contract.orders.v1.GetOrderResponseType;
import com.example.contract.orders.v1.ObjectFactory;

public final class PartnerOrderSoapClient {

    private static final String NS =
        "urn:example:orders:v1";

    private static final QName RESPONSE_QNAME =
        new QName(NS, "GetOrderResponse");

    private static final String GET_ORDER_ACTION =
        "urn:example:orders:action:GetOrder";

    private final WebServiceTemplate template;
    private final ObjectFactory factory = new ObjectFactory();

    public PartnerOrderSoapClient(
            WebServiceTemplate template) {
        this.template = template;
    }

    public GetOrderResponseType getOrder(String orderId) {
        GetOrderRequestType request =
            new GetOrderRequestType();

        request.setOrderId(orderId);
        request.setIncludeHistory(Boolean.FALSE);

        JAXBElement<GetOrderRequestType> requestRoot =
            factory.createGetOrderRequest(request);

        Object raw = template.marshalSendAndReceive(
            requestRoot,
            new SoapActionCallback(GET_ORDER_ACTION)
        );

        if (!(raw instanceof JAXBElement<?> responseRoot)) {
            throw new IllegalStateException(
                "SOAP response không có JAXB element root"
            );
        }

        if (!RESPONSE_QNAME.equals(responseRoot.getName())) {
            throw new IllegalStateException(
                "SOAP response root QName không đúng contract: "
                    + responseRoot.getName()
            );
        }

        Object value = responseRoot.getValue();

        if (!(value instanceof GetOrderResponseType response)) {
            throw new IllegalStateException(
                "SOAP response value không đúng JAXB type"
            );
        }

        return response;
    }
}
~~~

Điểm chính:

1. Dự án sử dụng binding sinh từ XSD; `ObjectFactory` giữ declaration của root QName.
2. Client API `getOrder(String)` che đi `JAXBElement` và template `Object` return type khỏi tầng nghiệp vụ.
3. Kiểm tra **QName** trước khi tin vào kiểu value.
4. Không cast thẳng `(GetOrderResponseType) template.marshalSendAndReceive(...)` vì trường hợp này return object thường là `JAXBElement<?>`.
5. `SoapActionCallback` dùng giá trị từ WSDL binding thực tế.
6. Code ví dụ có thể bổ sung validation `orderId`, mapper domain, logging, security và exception mapping theo kiến trúc dự án.

Ví dụ này giả định generated API tương ứng với XSD ở mục 3. Khi XJC customization thay đổi class/constructor/method, cần dùng đúng code đã được sinh, không đổi tên bằng phỏng đoán.

### 10.1. Nếu root class có @XmlRootElement

Trong binding khác:

~~~java
GetOrderRequest request = new GetOrderRequest();
request.setOrderId("ORD-2048");

Object raw = template.marshalSendAndReceive(request);

if (!(raw instanceof GetOrderResponse response)) {
    throw new IllegalStateException(
        "Response không phải GetOrderResponse"
    );
}
~~~

Chỉ dùng cách này khi XJC/JAXB classes thực sự có root mapping phù hợp. Thực hành tốt là viết test khẳng định QName của XML được tạo, bởi kiểu Java trông có vẻ phù hợp chưa đủ.

### 10.2. Tại sao không so tên class với tên operation?

Class `GetOrderRequestType` đại diện type có thể được dùng lại cho nhiều global elements. XML element QName mới là định danh hợp đồng. Không tự rename các JAXB classes rồi kỳ vọng SOAP Body hoặc WSDL tự đổi theo.

### 10.3. Kết quả null hoặc empty response

Tùy template operation, một lời gọi có thể không có payload response, ví dụ một-way contract hoặc cấu hình đặc biệt. Với `GetOrder` được thiết kế request/response, nên coi response null/missing là **vi phạm kỳ vọng của operation** và xử lý rõ ràng; không đưa null lặng lẽ vào domain.

Cần test cả normal response, SOAP Fault, response thiếu root, response sai namespace và response trống bất thường.

## 11. Cách khai báo service adapter trong Spring

Để tách wiring khỏi business class:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.client.core.WebServiceTemplate;

@Configuration
public class OrdersGatewayConfiguration {

    @Bean
    public PartnerOrderSoapClient partnerOrderSoapClient(
            @Qualifier("ordersTemplate")
            WebServiceTemplate template) {

        return new PartnerOrderSoapClient(template);
    }
}
~~~

Tầng nghiệp vụ sử dụng:

~~~java
GetOrderResponseType response =
    partnerOrderSoapClient.getOrder("ORD-2048");

switch (response.getStatus()) {
    case PAID -> { /* ... */ }
    case PENDING -> { /* ... */ }
    case CANCELLED -> { /* ... */ }
}
~~~

Đoạn `switch` chỉ minh họa nếu XJC tạo enum `OrderStatusType`. Với binding customization hoặc code khác, accessor/kiểu có thể thay đổi. Trong hệ thống lớn, domain service thường nhận `OrderStatus` riêng của ứng dụng thay vì phụ thuộc generated XJC enum.

### 11.1. WebServiceGatewaySupport là một lựa chọn khác

Spring-WS có `WebServiceGatewaySupport` giúp viết client gateway theo phong cách inheritance và truy cập `getWebServiceTemplate()`.

Có thể chọn:

~~~java
public class OrderGateway extends WebServiceGatewaySupport {

    public Object getOrder(Object request) {
        return getWebServiceTemplate()
            .marshalSendAndReceive(request);
    }
}
~~~

Nhưng không bắt buộc phải dùng kế thừa. Constructor injection của `WebServiceTemplate` như mục 10 thường rõ ràng, dễ kiểm thử và dễ tách nhiều clients. Dù lựa chọn phong cách nào, hợp đồng JAXB, namespace, message factory và Fault handling giống nhau.

## 12. Khi nào JAXB object được tạo ở phía client?

Dựa trên XSD, XJC sinh types/classes trong build; phía application tạo instance để gửi. Trình tự:

~~~text
XSD/WSDL contract
     |
     +-- Build-time JAXB code generation
              |
              v
        ObjectFactory / JAXB classes
              |
              v
        Tạo request từ dữ liệu domain
              |
              v
        marshalSendAndReceive
              |
              v
        JAXB response / JAXBElement
              |
              v
        Map sang domain response
~~~

`Jaxb2Marshaller` không gọi XJC động ở runtime. Đổi XSD không khiến client đang chạy tự cập nhật các class. Phải phát hành code mới với binding mới và kiểm tra khả năng tương thích với service versions.

### 12.1. Domain mapper giúp tránh phụ thuộc JAXB trực tiếp

Ví dụ:

~~~java
public record OrderQuery(
    String orderId,
    boolean includeHistory
) {}

public record OrderSummary(
    String orderId,
    String status
) {}
~~~

Mapper:

~~~java
GetOrderRequestType toJaxb(OrderQuery query) {
    GetOrderRequestType request = new GetOrderRequestType();
    request.setOrderId(query.orderId());
    request.setIncludeHistory(query.includeHistory());
    return request;
}

OrderSummary fromJaxb(GetOrderResponseType response) {
    return new OrderSummary(
        response.getOrderId(),
        response.getStatus().value()
    );
}
~~~

`response.getStatus().value()` là cách dùng thường gặp với enum do XJC sinh, nhưng phụ thuộc binding thực tế. Khi domain enum khác contract enum, nên ánh xạ tường minh và ném lỗi cho trạng thái không biết, không ép về giá trị mặc định “SUCCESS”.

Với các service có nhiều fields, dùng mapper chuyên dụng giúp test optional/nil, số tiền và thời gian độc lập với network.

## 13. Những trường hợp dữ liệu dễ mất ngữ nghĩa khi JAXB round-trip

### 13.1. Optional không giống false

`includeHistory` là optional `xs:boolean`. Một request không có element có thể khác request có `<includeHistory>false</includeHistory>`.

JAXB có thể sinh `Boolean`, cho phép null để biểu diễn vắng mặt:

~~~java
request.setIncludeHistory(null);          // Có thể không xuất element.
request.setIncludeHistory(Boolean.FALSE); // Gửi false.
~~~

Ý nghĩa chính xác tùy generated binding và mapper. Đừng tự biến null thành false nếu contract nghiệp vụ phân biệt “đối tác không chỉ định” và “đối tác chỉ định không bao gồm”.

### 13.2. Note absent/nil/empty

`note` vừa optional vừa nillable. Ba XML có thể mang nghĩa khác nhau:

~~~xml
<!-- note vắng mặt -->
~~~

~~~xml
<ord:note xmlns:ord="urn:example:orders:v1"/>
~~~

~~~xml
<ord:note
    xmlns:ord="urn:example:orders:v1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:nil="true"/>
~~~

Tùy binding, XJC có thể dùng `JAXBElement<String>` để bảo toàn trạng thái element hiện diện/nil hoặc dùng getter nullable mà gộp một số trạng thái. Nếu nghiệp vụ phân biệt ba trường hợp, phải kiểm tra generated code và viết round-trip tests riêng.

### 13.3. BigDecimal thay vì double

Nếu XSD có `xs:decimal` cho số tiền, ưu tiên `BigDecimal`; tránh tạo tiền từ `double` nhị phân:

~~~java
BigDecimal amount = new BigDecimal("125000.50");
~~~

Khi so giá trị số:

~~~java
boolean sameValue =
    new BigDecimal("1.0").compareTo(
        new BigDecimal("1.00")
    ) == 0;
~~~

`BigDecimal.equals()` so cả scale; XSD decimal value-space có thể coi hai lexical forms trên tương đương về số. Nếu ứng dụng cần giữ scale chính xác, phải quy định riêng thay vì mặc định marshalling bảo toàn từng ký tự.

### 13.4. XMLGregorianCalendar và timezone

`xs:dateTime` thường được XJC ánh xạ thành `XMLGregorianCalendar`. Có giá trị mang offset như:

~~~xml
<ord:createdAt>2026-11-27T09:30:00+07:00</ord:createdAt>
~~~

và có giá trị không có timezone (nếu contract cho phép). Chuyển sang `Instant` hoặc `OffsetDateTime` phải có chính sách rõ; không tự coi mọi giá trị không offset là UTC.

## 14. Điều gì xảy ra khi response không giống JAXB type mong đợi?

Các trường hợp:

| Tình huống | Hệ quả |
|---|---|
| Response root QName đúng và type hợp binding | Unmarshal thành công |
| Prefix khác nhưng namespace URI giống | Thường vẫn hợp lệ |
| Root namespace v2 thay v1 | Có thể không nhận ra global element; mapping lỗi |
| Root local name khác | JAXB có thể báo unexpected element |
| Server thêm enum value mới | Binding cũ có thể lỗi hoặc xử lý không như dự tính |
| Thiếu required child | Có thể bị XSD validation chặn nếu bật; JAXB mặc định không luôn enforce |
| SOAP Body là Fault | Đi qua Fault path, không phải normal JAXB response |
| SOAP 1.2 Envelope vào factory chỉ hỗ trợ 1.1 | Có thể lỗi ở message factory trước JAXB |
| XML malformed hoặc chứa entity không an toàn | Parser/security exception |
| Response rỗng khi operation cần output | Vi phạm mong đợi nghiệp vụ/contract |

Một client có thể nhận response `GetOrderResponse` đúng QName nhưng field `status=DELIVERED` ngoài enum v1. Đừng khắc phục bằng cách catch exception rồi trả `PAID` mặc định; cần xác định phía server đã thay đổi contract hay có dữ liệu sai.

### 14.1. Unmarshal không phải schema validation đầy đủ

Nếu marshaller không bật `setSchema(...)` hoặc không có validation độc lập, có những lỗi cấu trúc mà JAXB runtime vẫn đọc được. Khi trao đổi thông điệp doanh nghiệp, cần regression tests dùng XML fixtures độc lập từ XSD để tránh hai phía cùng chấp nhận một sai lệch.

### 14.2. Không vô tình sử dụng cùng JAXBContext cho v1/v2

Khi chạy song song versions, cấu hình context/package và QName riêng:

~~~text
com.example.contract.orders.v1 -> urn:example:orders:v1
com.example.contract.orders.v2 -> urn:example:orders:v2
~~~

Không chỉ đổi endpoint URI mà dùng binding v1 để gửi QName v2. Nếu có adapter giữa hai versions, nó phải chuyển dữ liệu có chủ đích và được kiểm thử đủ trường hợp breaking changes.

## 15. Phân biệt SOAP Fault, transport error và JAXB error

Một lời gọi `marshalSendAndReceive` có thể thất bại ở nhiều tầng. Điều quan trọng là nhận diện lỗi **trước khi gửi**, **trong vận chuyển**, **trong SOAP response** hay **khi giải mã JAXB**.

| Lớp lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Marshal request | JAXB không biết root element; Java object vi phạm XSD | Sửa binding/schema, không retry nguyên request |
| HTTP transport | 404, proxy sai route, 503 không có SOAP body | Kiểm tra endpoint/gateway |
| I/O / TLS | Timeout, certificate trust error, connection reset | Kiểm tra transport/TLS; retry có điều kiện |
| SOAP protocol | Envelope/Content-Type sai SOAP 1.1/1.2 | Chỉnh SOAP factory và binding |
| SOAP Fault | Server trả `soap:Fault` | Fault resolver và chính sách nghiệp vụ |
| Unmarshal response | Sai root QName, response type không hợp binding | Đánh giá contract/version |
| XSD validation | `status` ngoài enum, thiếu element required | Dữ liệu sai hợp đồng |
| Business response | `status=CANCELLED` hợp XSD | Xử lý nghiệp vụ, không coi là SOAP Fault |

### 15.1. SOAP Fault không phải GetOrderResponse

SOAP 1.1 Fault mẫu:

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
    <soap:Body>
        <soap:Fault>
            <faultcode>soap:Client</faultcode>
            <faultstring>orderId không hợp lệ</faultstring>
        </soap:Fault>
    </soap:Body>
</soap:Envelope>
~~~

Khi `WebServiceTemplate` nhận SOAP Fault, nó thường gọi cơ chế `FaultMessageResolver` thay vì unmarshal Fault thành `GetOrderResponseType`. Spring-WS có `SoapFaultMessageResolver` và exception `SoapFaultClientException` phục vụ trường hợp này.

SOAP 1.2 Fault dùng cấu trúc `Code`/`Reason`. Không viết logic chỉ đọc `faultcode`/`faultstring` 1.1 rồi giả định áp dụng cho mọi SOAP versions.

### 15.2. Phân loại lỗi ở client adapter

Ví dụ code minh họa:

~~~java
import org.springframework.ws.client.WebServiceIOException;
import org.springframework.ws.client.WebServiceTransportException;
import org.springframework.ws.soap.client.SoapFaultClientException;
import org.springframework.oxm.XmlMappingException;

public GetOrderResponseType lookup(String orderId) {
    try {
        return partnerClient.getOrder(orderId);

    } catch (SoapFaultClientException fault) {
        throw new PartnerRejectedRequestException(
            "Đối tác trả SOAP Fault", fault
        );

    } catch (WebServiceTransportException transport) {
        throw new PartnerUnavailableException(
            "HTTP transport lỗi", transport
        );

    } catch (WebServiceIOException io) {
        throw new PartnerUnavailableException(
            "Kết nối hoặc I/O lỗi", io
        );

    } catch (XmlMappingException xml) {
        throw new PartnerContractException(
            "SOAP XML không tương thích JAXB binding", xml
        );
    }
}
~~~

`PartnerRejectedRequestException`, `PartnerUnavailableException` và `PartnerContractException` là **exception do ứng dụng tự định nghĩa**, không phải class Spring-WS. Chữ ký minh họa một method ở tầng adapter, cần thêm class/field imports và xem lại phân cấp exception cụ thể theo framework version trong sản phẩm.

Không bắt mọi exception rồi trả `null` hoặc tạo `GetOrderResponse` giả chứa `status=PAID`. Caller phải biết server trả Fault, không nhận được response hay nhận response sai contract.

### 15.3. Retry không được làm mù

- SOAP 1.1 `Client` / SOAP 1.2 `Sender` thường chỉ lỗi phía request; retry nguyên payload dễ vô ích.
- SOAP 1.1 `Server` / SOAP 1.2 `Receiver` có thể tạm thời, nhưng cần xem fault detail và chính sách đối tác.
- Timeout sau khi server đã xử lý một operation có side effect có thể khiến client gửi lại và gây giao dịch trùng.

Retry nên ở tầng client adapter có **idempotency key**, timeout budget, backoff và giới hạn số lần. Không retry đệ quy vô hạn trong `ClientInterceptor.handleFault`.

### 15.4. Không tiết lộ dữ liệu khi log Fault

Không ghi nguyên SOAP Body, token, private key, password, certificate secret hoặc Fault Detail chứa dữ liệu khách hàng. Có thể ghi correlation ID an toàn, operation, fault code và loại lỗi đã chuẩn hóa theo chính sách bảo mật.

## 16. ClientInterceptor trong WebServiceTemplate

`WebServiceTemplate` cho phép đăng ký `ClientInterceptor` để thêm SOAP Header, WS-Security, tracing và metrics:

~~~java
import org.springframework.ws.client.support.interceptor.ClientInterceptor;

template.setInterceptors(new ClientInterceptor[] {
    observationInterceptor,
    correlationInterceptor,
    securityInterceptor
});
~~~

Thứ tự có ý nghĩa. Trong mô hình thông dụng:

~~~text
Outbound request:
    Observation -> Correlation -> Security -> HTTP

Inbound response / SOAP Fault:
    HTTP -> Security -> Correlation -> Observation
~~~

Trong các nhánh trả `false` hoặc throw exception, không phải interceptor nào cũng chạy đủ vòng đời. Nên viết test callback order cho phiên bản Spring-WS thực tế.

### 16.1. Bốn callback của ClientInterceptor

| Callback | Nhiệm vụ điển hình |
|---|---|
| `handleRequest` | Gắn SOAP Header, bắt đầu tracing, ký/mã hóa theo policy |
| `handleResponse` | Xử lý response thường, observability, metadata |
| `handleFault` | Quan sát SOAP Fault, không nuốt Fault resolver |
| `afterCompletion` | Kết thúc span/duration, cleanup theo lifecycle |

Không coi `handleResponse` là chứng minh business success. Một normal SOAP response có thể chứa trạng thái CANCELLED hoặc từ chối nghiệp vụ. Và HTTP/TLS error có thể không tạo `SoapFault` object, nên không thể chỉ dựa vào `handleFault` để đo mọi lỗi.

### 16.2. Correlation ID phải là dữ liệu per-call

Một singleton interceptor không nên chứa field `currentCorrelationId` vì nhiều threads cùng gọi sẽ có race condition. Hãy giữ metadata trên `MessageContext` hoặc context tracing có lifecycle rõ ràng:

~~~java
@Override
public boolean handleRequest(MessageContext context) {
    String id = UUID.randomUUID().toString();
    context.setProperty("partner.orders.correlation", id);

    SoapMessage soap = (SoapMessage) context.getRequest();
    SoapHeaderElement header = soap.getSoapHeader()
        .addHeaderElement(
            new QName("urn:example:common:v1", "CorrelationId")
        );

    header.setText(id);
    return true;
}
~~~

Đây là snippet minh họa; nó giả định SOAP message factory và đối tác chấp nhận Header QName tương ứng. Thêm header trước bước ký không tự bảo đảm chữ ký **bao phủ header**; cần cấu hình signature parts đúng.

### 16.3. Callback một operation và interceptor chung

Dùng `SoapActionCallback` hoặc `WebServiceMessageCallback` cho action/header riêng của một lời gọi. Dùng `ClientInterceptor` cho cross-cutting concerns áp dụng nhiều calls. Tránh cả hai nơi cùng thêm `CorrelationId` hoặc sửa SOAPAction khiến đối tác nhận metadata mâu thuẫn.

## 17. SOAP version, message factory và Content-Type

Một JAXB object có thể đi trong SOAP 1.1 hoặc SOAP 1.2 Envelope; **SOAP version không do JAXB class quyết định**.

| Thuộc tính | SOAP 1.1 | SOAP 1.2 |
|---|---|---|
| Envelope namespace | `http://schemas.xmlsoap.org/soap/envelope/` | `http://www.w3.org/2003/05/soap-envelope` |
| Media type | `text/xml` | `application/soap+xml` |
| Action | HTTP header `SOAPAction` | Tham số `action` tùy binding |
| Fault group | `Client` / `Server` | `Sender` / `Receiver` |

Nếu server yêu cầu SOAP 1.1, ví dụ cấu hình message factory:

~~~java
import org.springframework.ws.soap.SoapVersion;
import org.springframework.ws.soap.saaj.SaajSoapMessageFactory;

SaajSoapMessageFactory factory =
    new SaajSoapMessageFactory();

factory.setSoapVersion(SoapVersion.SOAP_11);

template.setMessageFactory(factory);
~~~

Đây là phần minh họa **một số API**; trong cấu hình production nên để Spring quản lý bean initialization/lifecycle của SOAP message factory. Với SOAP 1.2, cần WSDL binding/đối tác thực sự hỗ trợ và cấu hình factory `SOAP_12` tương ứng.

SOAPAction đúng không tự sửa một Body QName sai; ngược lại Body QName đúng không cứu một SOAPAction trái binding. Test cả hai.

### 17.1. WSDL có thể có nhiều SOAP ports

Nếu WSDL mô tả nhiều bindings/ports, hãy chọn đúng port theo SOAP version và endpoint. Đừng lấy `soap:address` của SOAP 1.2 rồi sử dụng factory chỉ hỗ trợ SOAP 1.1.

## 18. Transport HTTP/HTTPS và chứng chỉ

`WebServiceTemplate` sử dụng `WebServiceMessageSender` để kết nối tới dịch vụ. Những cấu hình thường cần có:

- Connection timeout và response/read timeout.
- HTTP proxy, connection pool và keep-alive.
- TLS protocol/cipher suite theo chính sách.
- Truststore/certificate validation.
- Client certificate khi đối tác dùng mutual TLS.
- HTTP authentication nếu được yêu cầu.
- DNS và endpoint network routing.

Không đặt password, private key, keystore password hoặc access token trong source code. Sử dụng secret manager và quy trình xoay khóa.

### 18.1. Timeout thuộc message sender

Tên API và kiểu tham số thay đổi theo message sender/HTTP client implementation và Spring-WS version. Không sao chép `setReadTimeout(int)` của một sender cũ sang library mới cần `Duration` hoặc request configuration khác mà chưa đối chiếu. Việc đổi `Jaxb2Marshaller` không thay thế cấu hình timeout.

### 18.2. HTTP 200 không đủ

Proxy có thể trả HTTP 200 chứa HTML login page; một server cũng có thể trả Envelope sai SOAP version. JAXB sẽ lỗi dù status network thành công. Kiểm tra Content-Type, SOAP Envelope, payload QName và schema thay vì chỉ status code.

### 18.3. Không nhận endpoint URI tùy ý từ người dùng

`marshalSendAndReceive(uri, request)` cho phép chọn URL từng lượt gọi. Nếu URI được lấy trực tiếp từ input bên ngoài, ứng dụng có thể gặp SSRF hoặc gửi thông tin xác thực sai nơi. Nên chọn host từ danh sách đối tác tin cậy và quản lý cấu hình riêng cho staging/production.

## 19. WS-Security và chính sách ký/mã hóa

Một SOAP service doanh nghiệp có thể yêu cầu:

- UsernameToken.
- Timestamp, clock skew và chống replay.
- XML Signature cho SOAP Body và một số Headers.
- XML Encryption cho nội dung nhạy cảm.
- Certificate trust, thuật toán phù hợp và key rotation.

Spring-WS có tích hợp Apache WSS4J trong các phiên bản hỗ trợ. Mẫu khái niệm:

~~~java
// Pseudocode, không phải cấu hình production hoàn chỉnh:
//
// Wss4jSecurityInterceptor security = new Wss4jSecurityInterceptor();
// security.setSecurementActions("Timestamp Signature");
// security.setValidationActions("Timestamp Signature");
//
// Cần crypto configuration, aliases, keystore,
// truststore, password callback, signed parts,
// timestamp policy, replay protection và algorithms.
~~~

Không dùng đoạn này như cấu hình bảo mật hoàn chỉnh. API/module và cách cấu hình thay đổi theo Spring-WS/WSS4J version.

### 19.1. Thứ tự tạo Header và ký

Nếu đối tác yêu cầu `CorrelationId` được ký, tạo Header trước bước ký rồi cấu hình **Header QName là signed part**. Header hiện diện khi ký không đồng nghĩa chữ ký tự bảo vệ Header nếu policy chỉ ký SOAP Body.

### 19.2. Tránh sửa XML đã ký

Thay namespace declarations, nội dung, element ordering hoặc serialization có thể làm chữ ký XML thất bại theo canonicalization/references. Logging interceptor không nên marshal lại payload đã ký chỉ để đổi prefix cho đẹp.

### 19.3. XML security khác WS-Security

Dù có TLS và chữ ký, client vẫn phải kiểm soát XXE, external entities, external schema fetch và XML resource exhaustion trong SOAP parser, JAXB và validator. WS-Security giải quyết integrity/authentication theo policy, không tự thay thế parser hardening.

## 20. MockWebServiceServer: kiểm thử client không cần partner

`spring-ws-test` cung cấp `MockWebServiceServer` để giả lập SOAP service ở phía đối tác và kiểm tra request đi ra từ `WebServiceTemplate`.

| Công cụ | Chức năng |
|---|---|
| `MockWebServiceServer` | Test **client** và `WebServiceTemplate` |
| `MockWebServiceClient` | Test **server** và `@Endpoint` |

### 20.1. Test round-trip JAXB

Ví dụ JUnit 5 dùng binding package của phần trước và client adapter `PartnerOrderSoapClient`:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.ws.test.client.RequestMatchers.payload;
import static org.springframework.ws.test.client.ResponseCreators.withPayload;

import org.junit.jupiter.api.Test;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.test.client.MockWebServiceServer;
import org.springframework.xml.transform.StringSource;

import com.example.contract.orders.v1.GetOrderResponseType;
import com.example.contract.orders.v1.OrderStatusType;

class PartnerOrderSoapClientTest {

    @Test
    void marshalsRequestAndUnmarshalsResponse() throws Exception {
        Jaxb2Marshaller jaxb = new Jaxb2Marshaller();
        jaxb.setContextPath("com.example.contract.orders.v1");
        jaxb.afterPropertiesSet();

        WebServiceTemplate template = new WebServiceTemplate();
        template.setMarshaller(jaxb);
        template.setUnmarshaller(jaxb);
        template.setDefaultUri("https://partner.example.test/ws");

        MockWebServiceServer mock =
            MockWebServiceServer.createServer(template);

        String expectedRequest = """
            <ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
                <ord:orderId>ORD-2048</ord:orderId>
                <ord:includeHistory>false</ord:includeHistory>
            </ord:GetOrderRequest>
            """;

        String responseXml = """
            <ord:GetOrderResponse xmlns:ord="urn:example:orders:v1">
                <ord:orderId>ORD-2048</ord:orderId>
                <ord:status>PAID</ord:status>
            </ord:GetOrderResponse>
            """;

        mock.expect(payload(new StringSource(expectedRequest)))
            .andRespond(withPayload(new StringSource(responseXml)));

        PartnerOrderSoapClient gateway =
            new PartnerOrderSoapClient(template);

        GetOrderResponseType response =
            gateway.getOrder("ORD-2048");

        assertEquals("ORD-2048", response.getOrderId());
        assertEquals(OrderStatusType.PAID, response.getStatus());

        mock.verify();
    }
}
~~~

Ví dụ cần generated JAXB classes và dependencies Spring-WS test/JUnit. Nếu XJC sinh accessor hoặc enum khác, điều chỉnh code theo binding thực tế. `MockWebServiceServer` thay transport, không kiểm tra TLS/proxy thật.

`mock.expect(payload(...))` kiểm tra request XML mà JAXB đã tạo. Matcher XML nên hiểu QName/structure thay vì ép prefix phải giống từng byte. `mock.verify()` kiểm tra kỳ vọng thực sự được đáp ứng.

### 20.2. Test SOAPAction và SOAP Header

Các matcher của `spring-ws-test` có thể kiểm tra action và payload:

~~~java
import static org.springframework.ws.test.client.RequestMatchers.soapAction;

// Gợi ý một expectation theo API matcher của version đang dùng:
soapAction("urn:example:orders:action:GetOrder");
~~~

Trong test hoàn chỉnh, cần gắn matcher vào `mock.expect(...)` cùng response được trả, không gọi riêng một matcher và nghĩ nó tự thực thi. Nếu cần kiểm tra Header tùy chỉnh, viết `RequestMatcher` đọc `SoapMessage#getSoapHeader()` rồi so QName chứ không so raw prefix.

### 20.3. Test response sai QName

Một response giả có:

~~~xml
<x:GetOrderResponse xmlns:x="urn:example:orders:v2">
    <x:orderId>ORD-2048</x:orderId>
    <x:status>PAID</x:status>
</x:GetOrderResponse>
~~~

sẽ có root QName v2, khác hợp đồng v1. Client cần từ chối hoặc báo contract mismatch theo JAXB/schema configuration, không ép về type v1 chỉ vì local name giống.

### 20.4. Test SOAP Fault riêng

Dùng response creator SOAP Fault tương ứng Spring-WS test version để giả lập remote Fault. Assert:

1. `handleFault` được gọi nếu cấu hình interceptor và Fault được nhận diện.
2. Response Fault không bị unmarshal thành `GetOrderResponseType`.
3. Caller nhận `SoapFaultClientException` (nếu resolver mặc định) hoặc application exception rõ ràng.
4. Fault Detail không bị log thô.
5. HTTP error không có SOAP Fault và transport timeout được kiểm thử riêng.

Không coi mọi HTTP 500 là SOAP Fault; phải thực sự có SOAP Envelope/Fault hợp lệ.

## 21. Kiểm thử XSD trước và sau JAXB

Một bộ test tốt nên bao phủ những ranh giới sau:

~~~text
Java request -> marshal -> XML -> validate XSD
XML fixture -> unmarshal -> Java -> marshal -> validate XSD
SOAP client -> MockWebServiceServer -> SOAP response -> JAXB
SOAP Fault -> Fault resolver / client exception
Transport failure -> transport exception / retry policy
~~~

**Đừng tạo mọi XML fixture bằng chính marshaller đang kiểm thử.** Nếu cả chiều tạo và chiều đọc cùng có lỗi QName/namespace, một round-trip tự sinh vẫn có thể pass. Hãy giữ các XML fixture độc lập dựa trên XSD/WSDL đã công bố.

### 21.1. Ma trận dữ liệu biên

| Ca | Input hoặc response | Kỳ vọng |
|---|---|---|
| B1 | `orderId=ORD-1` | Hợp XSD |
| B2 | `orderId=ORD-2048` | Hợp XSD |
| B3 | `orderId=ABC` | Sai `pattern` |
| B4 | `orderId=""` | Sai `minLength` và pattern |
| B5 | Không có `orderId` | Sai required field |
| B6 | `includeHistory` vắng mặt | Hợp `minOccurs=0` |
| B7 | `includeHistory=false` | Hợp lệ |
| B8 | `includeHistory=0` | Hợp lexical form `xs:boolean` |
| B9 | `includeHistory=maybe` | Sai `xs:boolean` |
| B10 | `status=PAID` | Hợp response enum |
| B11 | `status=DELIVERED` | Sai response enum |
| B12 | Response đổi prefix, giữ namespace URI v1 | Hợp lệ |
| B13 | Response đổi namespace sang v2 | Không tương thích v1 |
| B14 | `note` absent/empty/nil | Test semantics hợp đồng |
| B15 | `status` đứng trước `orderId` | Sai `xs:sequence` |
| B16 | Envelope SOAP 1.2 vào factory SOAP 1.1 | Lỗi giao thức |
| B17 | SOAP Fault từ server | Fault path, không phải JAXB response |

### 21.2. So XML theo ngữ nghĩa, không theo byte

Khi marshal, JAXB có thể dùng prefix `ns2` thay vì `ord`, đổi indentation và cách escape XML entities. XML vẫn có thể cùng QName và giá trị. Test nên parse namespace-aware để so QName, kiểu/giá trị và thứ tự element; sau đó validate bằng XSD.

Với tiền tệ `BigDecimal`, phép so giá trị qua `compareTo()==0` thường phù hợp hơn `equals()` nếu không yêu cầu giữ scale; với timezones, cần biết contract so instant hay giữ offset. Không dùng quy tắc tổng quát ép mọi kiểu dữ liệu về chuỗi.

### 21.3. Kiểm tra optional, nil và empty riêng

Trong SOAP data exchange, có khi:

- Element không xuất hiện.
- Element xuất hiện rỗng.
- Element xuất hiện với `xsi:nil="true"`.

JAXB binding có thể phân biệt bằng `JAXBElement<T>` hoặc class metadata tùy schema. Nếu domain coi absent là “không thay đổi”, nil là “xóa” và empty là “đặt chuỗi rỗng”, phải test cả chiều XML→Java và Java→XML để tránh gộp trạng thái sai.

## 22. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| JAXB báo không có `@XmlRootElement` | Truyền named complex type trực tiếp | Dùng `ObjectFactory` / `JAXBElement` |
| `Unexpected element` | Root QName sai, client/server khác namespace | So URI + local name, XSD/WSDL version |
| Enum mới gây unmarshal error | Response ngoài binding/XSD client | Đánh giá breaking change |
| Class không được biết bởi JAXBContext | Thiếu package/classes trong context | `setContextPath` hoặc classes |
| Response object khác kiểu dự kiến | Root binding có thể là `JAXBElement` | Kiểm tra QName và value trước cast |
| SOAP client nhận HTTP 415 | Content-Type/SOAP version không khớp | Message factory và WSDL binding |
| SOAP Fault về action | `SOAPAction` không khớp | Đọc `soapAction` trong WSDL |
| TLS handshake lỗi | Certificate/trust/protocol mismatch | Message sender và TLS configuration |
| Timeout không có Fault | Không có SOAP message response | Transport policy |
| Server không hiểu Header | Sai QName, `mustUnderstand` hoặc WS-Security policy | SOAP header/trust/signature |
| Bật XSD validation mới fail | Request/response trước đó đã sai schema | Kiểm tra XML fixture độc lập |
| Partner B fail, A chạy tốt | Dùng nhầm JAXB/template/security policy | Tách client per partner |
| Log correlation bị trộn | Singleton interceptor giữ mutable request ID | `MessageContext` per-call |
| WSDL tải được nhưng XSD import fail | Schema location/resolver sai | GET đầy đủ imports/includes |

### 22.1. Debug trường hợp unexpected element

Thực hiện theo thứ tự:

1. Xác định response đang là SOAP success hay SOAP Fault.
2. Kiểm tra SOAP version, HTTP Content-Type và Endpoint URI.
3. Lấy root payload QName thực tế theo URI/local name, không chỉ prefix.
4. So QName với WSDL/XSD mà client đang dùng.
5. Kiểm tra `package-info.java`, `ObjectFactory`, `@XmlElementDecl` và `@XmlRootElement`.
6. Kiểm tra JAXBContext package/version và cách template được wiring.
7. Kiểm tra SOAPAction và SOAP Header/WS-Security policy.
8. Chạy response fixture bằng JAXB unmarshaller có schema validation.
9. Dùng `MockWebServiceServer` tái hiện lỗi.
10. Nếu server thay hợp đồng, quản lý version thay vì âm thầm ép client v1 bỏ qua namespace.

Không chữa bằng cách tắt schema validation hoặc ép mọi namespace về `local-name()`. QName của XML là một phần hợp đồng công khai.

## 23. Phát hành và kiểm soát thay đổi

Những thay đổi cần chạy regression:

- XSD/WSDL hoặc SOAP binding được chỉnh sửa.
- XJC plugin, generated JAXB classes hoặc JAXB runtime nâng cấp.
- Spring-WS/`WebServiceTemplate`/SOAP factory/message sender thay đổi.
- `XmlAdapter` hoặc mapper chuyển tiền/ngày giờ/enum thay đổi.
- SOAPAction, WS-Addressing, ClientInterceptor hoặc WS-Security policy thay đổi.
- URL endpoint, TLS certificate/truststore, reverse proxy hoặc timeout cấu hình lại.

Một pipeline phù hợp:

~~~mermaid
flowchart TD
    A["WSDL/XSD contract"] --> B["XJC generate JAXB binding"]
    B --> C["Compile client / mapper"]
    C --> D["Unit tests JAXB + XSD fixtures"]
    D --> E["MockWebServiceServer tests"]
    E --> F["SOAP Fault + transport tests"]
    F --> G["Interop tests với stack độc lập"]
    G --> H["Deploy + monitoring + rollback"]
~~~

Lưu lại WSDL/XSD version đã công bố để phát hiện breaking change. Nếu v2 đổi QName hoặc enum semantics, cân nhắc sinh package JAXB v2 độc lập, giữ adapter chuyển đổi và chạy song song khi cần.

### 23.1. Monitoring sau phát hành

Theo dõi:

- Request rate và latency p50/p95/p99.
- SOAP Fault theo operation/fault code.
- HTTP/TLS/timeout errors.
- JAXB/contract mismatch.
- Certificate expiry và key rotation.
- Retry rate, idempotency conflicts.
- Log an toàn, correlation/tracing metadata.

Tránh dùng orderId, userId, token, UUID từng request hoặc fault reason nguyên văn làm metric labels vì cardinality cao và có thể tiết lộ dữ liệu nhạy cảm.

## 24. Bài thực hành: xây Order SOAP client theo contract-first

Bài toán: một hệ thống cần gọi `GetOrder` của đối tác, input domain là `OrderQuery` và output là `OrderSummary`.

Hãy thực hiện:

1. Lưu XSD/WSDL v1 đã thống nhất, xác định targetNamespace, global elements và SOAP binding.
2. Cấu hình XJC để sinh JAXB classes vào package `com.example.contract.orders.v1`.
3. Đọc `ObjectFactory` và `package-info.java`, phân biệt named types với global element declarations.
4. Viết mapper `OrderQuery` → `GetOrderRequestType`.
5. Dùng `ObjectFactory.createGetOrderRequest(...)` tạo `JAXBElement` đúng QName.
6. Cấu hình `Jaxb2Marshaller` với `contextPath` v1 và schema validation khi chính sách yêu cầu.
7. Tạo `WebServiceTemplate` với marshaller/unmarshaller, default URI và SOAP message factory đúng binding.
8. Viết `PartnerOrderSoapClient.getOrder(...)` dùng `marshalSendAndReceive`.
9. Kiểm tra QName của response trước khi xử lý `JAXBElement` value.
10. Gắn `SoapActionCallback` theo action thực tế trong WSDL.
11. Thêm một `ClientInterceptor` gắn CorrelationId per-call, tránh mutable singleton state.
12. Nếu WS-Security được yêu cầu, cấu hình ký Body/Header theo policy, truststore và certificate đúng.
13. Dùng `MockWebServiceServer` assert request payload, SOAPAction và SOAP Header.
14. Trả normal response, kiểm tra JAXB response và domain mapper.
15. Trả SOAP Fault, kiểm tra exception/fault resolver.
16. Trả response sai namespace v2, enum lạ và XML malformed; kiểm tra mismatch không bị che.
17. Giả lập timeout/transport error, phân biệt với SOAP Fault.
18. Test prefix khác/default namespace nhưng cùng QName.
19. Chạy test qua HTTPS ở môi trường đối tác được cho phép, xác nhận certificate trust và latency.
20. Chuẩn bị rollback nếu binding/policy mới làm client không còn tương thích.

**Tiêu chí hoàn thành:** Client gửi request đúng QName/XSD/SOAPAction, nhận JAXB response đúng type, phân loại lỗi rõ ràng, không làm lộ secrets và có kiểm thử độc lập với server thực.

## 25. Checklist trước khi đưa marshalSendAndReceive vào production

- [ ] Đã xác định đúng WSDL/XSD contract và phiên bản.
- [ ] Generated JAXB classes đúng package và namespace.
- [ ] Đã kiểm tra `@XmlRootElement` hay `ObjectFactory`/`JAXBElement` là cần thiết.
- [ ] Root QName request/response được test độc lập với prefix.
- [ ] `Jaxb2Marshaller` có `contextPath`/classes phù hợp.
- [ ] `WebServiceTemplate` có đúng marshaller và unmarshaller.
- [ ] SOAP message factory đúng SOAP 1.1/1.2 binding.
- [ ] Endpoint URI lấy từ nguồn cấu hình đáng tin.
- [ ] SOAPAction/action theo WSDL khi cần.
- [ ] SOAP Headers, `mustUnderstand` và WS-Security phù hợp đối tác.
- [ ] TLS/truststore/client certificate và timeout được xác minh.
- [ ] SOAP Fault được phân biệt với transport/JAXB/schema errors.
- [ ] Retry có giới hạn, timeout budget và idempotency policy.
- [ ] Optional/nil/empty, decimal, dateTime và enum có tests.
- [ ] Có outbound/inbound XSD validation nơi phù hợp.
- [ ] Có `MockWebServiceServer` tests cho payload, action, Fault.
- [ ] Có HTTP/TLS integration test và interoperability test khi cần.
- [ ] Không log raw SOAP Body, token, mật khẩu, khóa riêng hoặc thông tin nhạy cảm.
- [ ] Có monitoring, correlation ID và kế hoạch rollback.

## 26. Ghi nhớ

- **`marshalSendAndReceive`** là cầu nối Java ↔ SOAP XML trong `WebServiceTemplate` thông qua marshaller/unmarshaller.
- **JAXB type khác JAXB root element**: named complex type thường cần `JAXBElement` từ `ObjectFactory` để tạo QName đúng.
- **Đúng Java class chưa đủ**: request/response phải có đúng global element QName trong XSD/WSDL.
- **SOAPAction, endpoint URI và QName là các khái niệm khác nhau**; kiểm tra từng thứ.
- **SOAP Fault không phải JAXB success response**, và HTTP/transport error không mặc nhiên là SOAP Fault.
- **XSD validation, WS-Security, TLS và domain authorization là các lớp khác nhau**, không được JAXB tự giải quyết toàn bộ.
- **`MockWebServiceServer` kiểm thử client** mà không gọi partner thật; dùng thêm XML fixtures độc lập để bảo vệ hợp đồng.
- **Versioning có kiểm soát** giúp tránh sinh lại JAXB code rồi vô tình phá các hệ thống đã tích hợp.

**Câu hỏi tự kiểm tra:** XSD khai báo global element `GetOrderRequest` có type `GetOrderRequestType` trong namespace `urn:example:orders:v1`. XJC sinh class `GetOrderRequestType` không có `@XmlRootElement`, nhưng bạn truyền trực tiếp instance của class đó vào `marshalSendAndReceive`. Vì sao marshalling có thể thất bại? Hãy trình bày cách dùng `ObjectFactory`/`JAXBElement`, cách kiểm tra QName response và ba test `MockWebServiceServer` phân biệt normal response, SOAP Fault và response sai namespace.



