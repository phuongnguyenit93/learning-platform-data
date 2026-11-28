# Ánh xạ phần tử gốc, JAXBElement và namespace

Trong **Spring Web Services (Spring-WS)**, một đối tượng Java chỉ trở thành payload SOAP đúng hợp đồng khi JAXB biết **phần tử XML gốc** cần tạo: local name là gì, namespace URI nào và nội dung mang kiểu dữ liệu nào. Nếu lớp JAXB chỉ mô tả một `complexType` mà chưa gắn với phần tử gốc, thao tác marshal trực tiếp có thể thất bại dù lớp có đầy đủ field và annotation. `JAXBElement<T>` giải quyết tình huống này bằng cách mang thông tin **QName của phần tử** cùng với **giá trị Java**.

Bài học thuộc chương **Marshalling và OXM** của module `SPRING_WEB_SERVICES`. Ta dùng thiết kế **contract-first**, bắt đầu từ XSD/WSDL, để giải thích `@XmlRootElement`, `@XmlElementDecl`, `ObjectFactory`, `@XmlSchema` và `Jaxb2Marshaller`; sau đó áp dụng vào endpoint, SOAP client, schema validation, SOAP Fault, WS-Security và kiểm thử tương thích.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **XML element**, **XML schema type** và **đối tượng Java**; giải thích vì sao chúng không luôn tương ứng một-một.
2. Xác định QName của phần tử gốc trong SOAP Body, kể cả khi XML dùng default namespace hoặc prefix khác.
3. Phân biệt trường hợp marshal trực tiếp đối tượng có `@XmlRootElement` với trường hợp phải dùng `JAXBElement<T>`.
4. Đọc mã sinh JAXB gồm `ObjectFactory`, `@XmlElementDecl` và `package-info.java` để hiểu tên phần tử và namespace.
5. Cấu hình `Jaxb2Marshaller` và dùng `JAXBElement` trong Spring-WS endpoint và `WebServiceTemplate` client.
6. Phát hiện lỗi root/namespace và kiểm tra chúng bằng XML thực tế, XSD validation, SOAP Fault và bài test tích hợp.
7. Nhận biết giới hạn bảo mật: JAXB mapping không thay thế kiểm tra WS-Security, chữ ký XML, parser an toàn hoặc chứng chỉ TLS.

## 1. Mô hình tư duy: type không phải element

XSD có thể khai báo một **kiểu** và một **phần tử** sử dụng kiểu đó:

~~~xml
<xs:complexType name="GetOrderRequestType">
  <xs:sequence>
    <xs:element name="orderId" type="xs:string"/>
  </xs:sequence>
</xs:complexType>

<xs:element name="GetOrderRequest"
            type="tns:GetOrderRequestType"/>
~~~

Hai khai báo có trách nhiệm khác nhau:

| Khái niệm | Danh tính | Vai trò |
| --- | --- | --- |
| XSD complex type | `{urn:example:orders:v1}GetOrderRequestType` | Mô tả cấu trúc của giá trị: ở đây có `orderId` |
| XSD global element | `{urn:example:orders:v1}GetOrderRequest` | Đặt tên **nút XML gốc** và gắn nó với type |
| Java JAXB class | Ví dụ `GetOrderRequestType` | Mang dữ liệu trong JVM; có thể biểu diễn một XML type |
| `JAXBElement<GetOrderRequestType>` | Tên element `GetOrderRequest` + giá trị `GetOrderRequestType` | Cung cấp QName cho một type chưa tự xác định phần tử root |

XML hợp lệ cho khai báo này:

~~~xml
<ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
  <ord:orderId>ORD-42</ord:orderId>
</ord:GetOrderRequest>
~~~

Đối tác có thể viết:

~~~xml
<GetOrderRequest xmlns="urn:example:orders:v1">
  <orderId>ORD-42</orderId>
</GetOrderRequest>
~~~

Hai tài liệu trên **tương đương về QName của các phần tử**: prefix `ord` chỉ là bí danh cho URI; default namespace áp dụng cho các phần tử không có prefix. Với hợp đồng có `elementFormDefault="qualified"`, `orderId` cũng thuộc namespace đơn hàng.

**Quy tắc nền tảng:** tên hiển thị của class Java không quyết định QName của XML. QName là cặp `{namespace URI}localPart`. WSDL, XSD, JAXB và `@PayloadRoot` phải thống nhất trên cặp đó.

## 2. Ví dụ XSD contract-first để sinh JAXB

Đặt XSD ở `src/main/resources/xsd/orders-v1.xsd`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:tns="urn:example:orders:v1"
    targetNamespace="urn:example:orders:v1"
    elementFormDefault="qualified">

  <xs:complexType name="GetOrderRequestType">
    <xs:sequence>
      <xs:element name="orderId" type="xs:string"/>
    </xs:sequence>
  </xs:complexType>

  <xs:simpleType name="OrderStateType">
    <xs:restriction base="xs:string">
      <xs:enumeration value="CREATED"/>
      <xs:enumeration value="SHIPPED"/>
      <xs:enumeration value="CANCELLED"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:complexType name="GetOrderResponseType">
    <xs:sequence>
      <xs:element name="orderId" type="xs:string"/>
      <xs:element name="state" type="tns:OrderStateType"/>
    </xs:sequence>
  </xs:complexType>

  <!-- Hai global elements là payload root của operation SOAP. -->
  <xs:element name="GetOrderRequest"
              type="tns:GetOrderRequestType"/>
  <xs:element name="GetOrderResponse"
              type="tns:GetOrderResponseType"/>
</xs:schema>
~~~

Ở đây:

- `GetOrderRequestType`, `GetOrderResponseType` là **named global complex types**.
- `GetOrderRequest` và `GetOrderResponse` là **named global elements** dùng các type trên.
- `OrderStateType` giúp kiểm soát ba giá trị enum ở tầng schema.
- `elementFormDefault="qualified"` quy định namespace cho phần tử con như `orderId`, `state`.

Một WSDL document/literal có thể tham chiếu các global elements qua `wsdl:part/@element`. Ví dụ, operation `GetOrder` dùng input `tns:GetOrderRequest`, output `tns:GetOrderResponse`. Trong Spring-WS, `DefaultWsdl11Definition` có thể suy ra operation từ hậu tố `Request`/`Response`; nếu công bố WSDL tĩnh, cần bảo đảm nó tham chiếu đúng QName đó.

### 2.1. Nhận diện nguồn tạo ra `JAXBElement`

Khi dùng XJC theo một binding phổ biến, XSD **tách named type và global element** như trên thường sinh:

~~~text
com.example.orders.contract/
├── GetOrderRequestType.java
├── GetOrderResponseType.java
├── OrderStateType.java
├── ObjectFactory.java
└── package-info.java
~~~

Class `GetOrderRequestType` biểu diễn **type**, có thể **không** có `@XmlRootElement`. Trong `ObjectFactory` thường có method tạo `JAXBElement<GetOrderRequestType>` cho global element `GetOrderRequest`.

Đây là **hình dạng thường gặp**, không phải cam kết tuyệt đối về tên class/phương thức của mọi phiên bản XJC hoặc external binding. Hãy đọc annotation và `ObjectFactory` mà công cụ của dự án thực sự sinh, vì các tùy chỉnh `.xjb` có thể thay đổi Java naming và cách binding.

## 3. Cơ chế thứ nhất: lớp có `@XmlRootElement`

Một lớp JAXB tự có thông tin root nhờ annotation:

~~~java
import jakarta.xml.bind.annotation.XmlAccessType;
import jakarta.xml.bind.annotation.XmlAccessorType;
import jakarta.xml.bind.annotation.XmlElement;
import jakarta.xml.bind.annotation.XmlRootElement;
import jakarta.xml.bind.annotation.XmlType;

@XmlRootElement(
    name = "GetOrderRequest",
    namespace = "urn:example:orders:v1")
@XmlAccessorType(XmlAccessType.FIELD)
@XmlType(propOrder = {"orderId"})
public class GetOrderRequest {

    @XmlElement(
        name = "orderId",
        namespace = "urn:example:orders:v1",
        required = true)
    private String orderId;

    public String getOrderId() {
        return orderId;
    }

    public void setOrderId(String orderId) {
        this.orderId = orderId;
    }
}
~~~

Đây là ví dụ **class viết tay độc lập** để minh họa root annotation. Nó không phải class thứ hai cần thêm vào cùng package JAXB của XSD mục 2; trong một ứng dụng thật, chọn model và binding nhất quán theo hợp đồng.

Khi đã cấu hình một `Marshaller` biết class này, có thể marshal trực tiếp:

~~~java
GetOrderRequest request = new GetOrderRequest();
request.setOrderId("ORD-42");

marshaller.marshal(request, result);
~~~

Trong Spring OXM, `result` thường là một `Result` như `StreamResult` hoặc `DOMResult`. Nếu dùng `jakarta.xml.bind.Marshaller` trực tiếp thì có overload và cách xử lý exception khác, nhưng ý tưởng vẫn là class tự định nghĩa được QName của root.

### 3.1. Khi nào XJC tạo `@XmlRootElement`?

Với một **global element có anonymous complex type** như:

~~~xml
<xs:element name="GetOrderRequest">
  <xs:complexType>
    <xs:sequence>
      <xs:element name="orderId" type="xs:string"/>
    </xs:sequence>
  </xs:complexType>
</xs:element>
~~~

công cụ XJC thường sinh class `GetOrderRequest` gắn `@XmlRootElement`, nên có thể marshal object trực tiếp. Với **named complex type** được nhiều element cùng dùng, việc không gắn một root cố định vào type và sử dụng `JAXBElement` là tự nhiên hơn.

Tuy vậy, **không suy luận chỉ từ tên file hoặc tên class**. Hãy mở class/annotation đã sinh và xác nhận thực tế. JAXB binding customization có thể khiến hai schema khác nhau sinh API Java khác nhau dù XML trên mạng vẫn cùng QName.

### 3.2. Tên root suy ra tự động dễ bị nhầm

Nếu viết `@XmlRootElement` mà bỏ `name` hoặc `namespace`, JAXB có thể suy ra tên từ class và namespace từ package. Ví dụ tên class Java `GetOrderRequest` có thể được chuẩn hóa thành tên XML khác định dạng PascalCase mong muốn nếu dựa vào giá trị mặc định của annotation.

Trong hợp đồng SOAP yêu cầu độ chính xác cao, nên kiểm tra QName XML phát ra và tránh trông chờ vào quy tắc đặt tên ngầm. `GetOrderRequest` và `getOrderRequest` có **local name khác nhau**; server dùng `@PayloadRoot(localPart="GetOrderRequest")` sẽ không chọn phần tử tên khác.

## 4. Cơ chế thứ hai: `JAXBElement<T>` mang QName cùng giá trị

`JAXBElement<T>` là một wrapper có các thông tin chính:

| Thành phần | Ý nghĩa |
| --- | --- |
| `name`: `QName` | Tên phần tử XML, gồm **namespace URI** và **localPart** |
| `declaredType`: `Class<T>` | Type mà phần tử được khai báo sử dụng |
| `scope` | Phạm vi khai báo phần tử, global hoặc trong một scope cụ thể |
| `value`: `T` | Giá trị Java chứa các field của phần tử |
| `nil` | Thể hiện trạng thái XML nil trong điều kiện phù hợp với hợp đồng |

Tư duy:

~~~text
GetOrderRequestType (Java)
      │ chứa orderId = ORD-42
      ▼
JAXBElement<GetOrderRequestType>
      ├── QName = {urn:example:orders:v1}GetOrderRequest
      ├── declaredType = GetOrderRequestType.class
      └── value = requestObject
      │ marshal
      ▼
<ord:GetOrderRequest>
  <ord:orderId>ORD-42</ord:orderId>
</ord:GetOrderRequest>
~~~

Class `GetOrderRequestType` mô tả **nội dung**, còn `JAXBElement` nói rõ **dùng tên phần tử nào** cho nội dung đó.

### 4.1. `ObjectFactory` và `@XmlElementDecl`

Một `ObjectFactory` sinh từ schema ở mục 2 thường có cấu trúc tương tự:

~~~java
package com.example.orders.contract;

import javax.xml.namespace.QName;
import jakarta.xml.bind.JAXBElement;
import jakarta.xml.bind.annotation.XmlElementDecl;
import jakarta.xml.bind.annotation.XmlRegistry;

@XmlRegistry
public class ObjectFactory {

    private static final QName GET_ORDER_REQUEST_QNAME =
        new QName("urn:example:orders:v1", "GetOrderRequest");

    private static final QName GET_ORDER_RESPONSE_QNAME =
        new QName("urn:example:orders:v1", "GetOrderResponse");

    public GetOrderRequestType createGetOrderRequestType() {
        return new GetOrderRequestType();
    }

    @XmlElementDecl(
        namespace = "urn:example:orders:v1",
        name = "GetOrderRequest")
    public JAXBElement<GetOrderRequestType> createGetOrderRequest(
            GetOrderRequestType value) {
        return new JAXBElement<>(
            GET_ORDER_REQUEST_QNAME,
            GetOrderRequestType.class,
            null,
            value);
    }

    @XmlElementDecl(
        namespace = "urn:example:orders:v1",
        name = "GetOrderResponse")
    public JAXBElement<GetOrderResponseType> createGetOrderResponse(
            GetOrderResponseType value) {
        return new JAXBElement<>(
            GET_ORDER_RESPONSE_QNAME,
            GetOrderResponseType.class,
            null,
            value);
    }
}
~~~

Đoạn trên là **mã mô phỏng hình dạng XJC-generated ObjectFactory**, lược các method khác; một dự án thật không cần viết đè file generated. Annotation `@XmlRegistry` đăng ký factory, còn `@XmlElementDecl` cung cấp khai báo element và QName để JAXB context nhận diện.

**Một chi tiết của Jakarta dễ gây nhầm:** `JAXBElement` và annotation JAXB thuộc package `jakarta.xml.bind` trên Spring Boot 3+/Spring Framework 6+; nhưng `QName` vẫn thuộc **`javax.xml.namespace.QName`** trong Java XML API. Đó là tên API tiêu chuẩn và **không phải** dấu hiệu dự án đang dùng JAXB `javax.xml.bind` cũ.

### 4.2. Cách tạo wrapper đúng

~~~java
ObjectFactory factory = new ObjectFactory();

GetOrderRequestType value = factory.createGetOrderRequestType();
value.setOrderId("ORD-42");

JAXBElement<GetOrderRequestType> requestElement =
    factory.createGetOrderRequest(value);
~~~

Một cách tương đương về mặt cấu trúc là tự tạo:

~~~java
QName name =
    new QName("urn:example:orders:v1", "GetOrderRequest");

JAXBElement<GetOrderRequestType> requestElement =
    new JAXBElement<>(
        name,
        GetOrderRequestType.class,
        value);
~~~

Ở ví dụ này, hàm tạo ba tham số dùng scope global. Tuy nhiên, **ưu tiên factory do XJC sinh** khi có sẵn, vì factory đi theo schema, giảm nguy cơ sai namespace, local name hoặc declared type. Tự dựng QName chỉ phù hợp khi có lý do kỹ thuật rõ ràng và kiểm thử với XSD/WSDL.

### 4.3. Tại sao không marshal `value` trực tiếp?

Với model `GetOrderRequestType` không có `@XmlRootElement`:

~~~java
// Có thể lỗi vì JAXB chưa biết element root cần tạo.
marshaller.marshal(value, result);

// Rõ ràng root QName theo hợp đồng:
marshaller.marshal(factory.createGetOrderRequest(value), result);
~~~

Tùy provider và context, lỗi trực tiếp có thể có thông điệp kiểu “unable to marshal type ... because it is missing an @XmlRootElement annotation”. Nguyên nhân **không phải** JAXB không biết `orderId`; vấn đề là **không xác định được element root** cho type khi marshal như một tài liệu độc lập.

### 4.4. Một type có thể xuất hiện dưới nhiều element

Giả sử cùng một `OrderIdentifierType` được khai báo cho hai global elements:

~~~xml
<xs:element name="FindOrderRequest" type="tns:OrderIdentifierType"/>
<xs:element name="CancelOrderRequest" type="tns:OrderIdentifierType"/>
~~~

Cùng dữ liệu Java chứa `orderId` nhưng hai loại thao tác khác nhau cần hai QName:

~~~text
{urn:example:orders:v1}FindOrderRequest
{urn:example:orders:v1}CancelOrderRequest
~~~

Đây là tình huống điển hình cho `JAXBElement<OrderIdentifierType>`: type Java giống nhau **không có nghĩa** root XML giống nhau. Với Spring-WS, hai QName đó có thể ánh xạ tới hai endpoint methods khác nhau.

## 5. Namespace trong JAXB: root, phần tử con và thuộc tính

Namespace có thể được khai báo ở nhiều nơi, mỗi nơi với trách nhiệm cụ thể.

### 5.1. `package-info.java` với `@XmlSchema`

XJC thường tạo metadata package tương tự:

~~~java
@jakarta.xml.bind.annotation.XmlSchema(
    namespace = "urn:example:orders:v1",
    elementFormDefault =
        jakarta.xml.bind.annotation.XmlNsForm.QUALIFIED)
package com.example.orders.contract;
~~~

`@XmlSchema` giúp JAXB xác định namespace mặc định của **XML elements** trong package, cùng chính sách qualified/unqualified cho local elements. Tùy schema, binding và generator, class hoặc field vẫn có thể có các annotation namespace cụ thể.

Điều quan trọng: **package Java không phải namespace XML**. Đổi package Java vì cấu trúc mã nguồn không tự đổi `urn:example:orders:v1`. Ngược lại, thay namespace XML v1 → v2 là thay đổi QName hợp đồng, có thể làm client cũ và `@PayloadRoot` không còn khớp.

### 5.2. `@XmlRootElement` so với `@XmlType`

~~~java
@XmlType(
    name = "GetOrderRequestType",
    namespace = "urn:example:orders:v1")
public class GetOrderRequestType {
    // ...
}
~~~

`@XmlType` mô tả **XML type** và thứ tự/nội dung binding; nó **không tự tạo global root element**. Một class có `@XmlType` nhưng không có `@XmlRootElement` thường cần wrapper `JAXBElement` khi marshal thành payload root.

Ngược lại, `@XmlRootElement(name="GetOrderRequest", namespace=...)` định danh **XML element root** cho class đó. Phần annotation này không thay thế việc định nghĩa type hợp lệ và field trong XSD.

### 5.3. `@XmlElement` và namespace của phần tử con

Với `elementFormDefault="qualified"`, XML request cần:

~~~xml
<ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
  <ord:orderId>ORD-42</ord:orderId>
</ord:GetOrderRequest>
~~~

Nếu serializer tạo:

~~~xml
<ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
  <orderId>ORD-42</orderId>
</ord:GetOrderRequest>
~~~

thì `orderId` **không có namespace**, vì không có prefix và không được khai báo default namespace. Nó khác QName `{urn:example:orders:v1}orderId` và sẽ không thỏa schema đã khai báo qualified.

Các nguyên nhân cần kiểm tra: `@XmlSchema`, `@XmlElement`, binding file, JAXB context đang nạp nhầm package hoặc model được tạo thủ công không khớp XSD.

### 5.4. Prefix là cách biểu diễn, URI mới là danh tính

Hai kết quả này có thể cùng hợp đồng:

~~~xml
<ns2:GetOrderResponse xmlns:ns2="urn:example:orders:v1">
  <ns2:orderId>ORD-42</ns2:orderId>
  <ns2:state>CREATED</ns2:state>
</ns2:GetOrderResponse>
~~~

~~~xml
<GetOrderResponse xmlns="urn:example:orders:v1">
  <orderId>ORD-42</orderId>
  <state>CREATED</state>
</GetOrderResponse>
~~~

Đừng viết test so sánh byte-for-byte chỉ để yêu cầu JAXB dùng prefix `ord`. Hãy kiểm tra **namespace URI, localPart, cấu trúc và giá trị** bằng XML-aware assertions hoặc schema validation. Thứ tự phần tử theo `xs:sequence` vẫn quan trọng; chỉ tên prefix có thể khác.

### 5.5. Thuộc tính không tự kế thừa default namespace

Với XML:

~~~xml
<GetOrderRequest xmlns="urn:example:orders:v1"
                 version="1">
  <orderId>ORD-42</orderId>
</GetOrderRequest>
~~~

`version` là **attribute không có namespace** dù phần tử root có default namespace. Trong XSD, `attributeFormDefault` và khai báo thuộc tính quyết định yêu cầu namespace của local attributes. JAXB có thể dùng `@XmlAttribute` để ánh xạ; đừng suy từ `elementFormDefault="qualified"` rằng tất cả attributes đều qualified.

## 6. Spring OXM và `Jaxb2Marshaller` nạp contract thế nào?

Spring OXM cung cấp abstraction marshalling/unmarshalling; `org.springframework.oxm.jaxb.Jaxb2Marshaller` có thể thực hiện cả hai vai trò:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;

@Configuration
public class OrdersJaxbConfig {

    @Bean
    public Jaxb2Marshaller ordersMarshaller() {
        Jaxb2Marshaller marshaller = new Jaxb2Marshaller();

        // Package có ObjectFactory / metadata JAXB do XJC sinh.
        marshaller.setContextPath("com.example.orders.contract");

        // Tùy chọn khi cần validation theo XSD ngay tại OXM layer.
        marshaller.setSchema(
            new ClassPathResource("xsd/orders-v1.xsd"));

        return marshaller;
    }
}
~~~

Điều kiện để ví dụ chạy đúng:

- Package `com.example.orders.contract` tồn tại trong artifact và chứa các lớp JAXB + `ObjectFactory`/metadata phù hợp.
- Spring Boot/Spring Framework và XJC dùng cùng thế hệ **Jakarta JAXB**.
- XSD có trong classpath nếu đã bật `setSchema(...)`.
- Dữ liệu request/response có QName và field đúng hợp đồng.
- Bean được inject vào SOAP client hoặc endpoint adapter theo cấu hình ứng dụng.

`setContextPath` không chỉ định namespace trực tiếp. **Namespace xuất phát từ annotation/schema binding** của các class trong JAXB context. Nếu đổi package XJC sinh mà quên sửa context path, lỗi thường xảy ra lúc tạo JAXB context hoặc marshal.

Có thể dùng `setClassesToBeBound(...)` hoặc `setPackagesToScan(...)` trong những mô hình khác, nhưng tránh trộn các kiểu từ nhiều version/namespace mà không có chủ đích. Với nhiều hợp đồng SOAP khác nhau, cân nhắc tách marshaller theo namespace hoặc boundary để giảm nhầm root type.

### 6.1. JAXB marshalling là payload, không phải toàn bộ SOAP Envelope

Trong Spring-WS, `Jaxb2Marshaller` thường tạo hoặc đọc **XML payload**:

~~~text
GetOrderRequestType
      │ ObjectFactory + JAXBElement
      ▼
<GetOrderRequest>...</GetOrderRequest>   ← XML payload
      │ WebServiceTemplate / Spring-WS infrastructure
      ▼
<soapenv:Envelope>
  <soapenv:Body>
    <GetOrderRequest>...</GetOrderRequest>
  </soapenv:Body>
</soapenv:Envelope>
~~~

SOAP Envelope, Header, SOAP version, HTTP transport và SOAP Fault thuộc hạ tầng SOAP, message factory, transport và cấu hình liên quan. JAXB không tự cung cấp chứng chỉ TLS hoặc xác minh WS-Security. Nếu bạn marshal JAXB object vào một `DOMResult`, kết quả thông thường là **phần tử payload**, không phải một SOAP Envelope hoàn chỉnh.

### 6.2. Vòng đời và hiệu năng

`JAXBContext` có chi phí khởi tạo và thường được tái sử dụng; trong JAXB chuẩn, các instance `Marshaller` và `Unmarshaller` không được mặc định là thread-safe để chia sẻ đồng thời. Spring `Jaxb2Marshaller` được thiết kế để quản lý context và tạo các đối tượng thao tác phù hợp cho từng lần gọi sau khi cấu hình bean ổn định.

Không tự tạo `JAXBContext.newInstance(...)` cho mỗi request nếu không có lý do; cũng không chia sẻ một JAXB `Marshaller` thô giữa nhiều thread mà không bảo đảm an toàn. Việc validate XML lớn hoặc tạo DOM cũng có chi phí cần đo trong điều kiện thực.

## 7. Endpoint Spring-WS nhận `JAXBElement`

Giả sử các lớp `GetOrderRequestType`, `GetOrderResponseType` và `ObjectFactory` được sinh từ XSD ở mục 2, endpoint có thể nhận phần tử root dưới dạng `JAXBElement`:

~~~java
import jakarta.xml.bind.JAXBElement;
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;

@Endpoint
public class OrdersEndpoint {

    private static final String NS = "urn:example:orders:v1";

    private final OrderService orderService;
    private final ObjectFactory factory = new ObjectFactory();

    public OrdersEndpoint(OrderService orderService) {
        this.orderService = orderService;
    }

    @PayloadRoot(namespace = NS, localPart = "GetOrderRequest")
    @ResponsePayload
    public JAXBElement<GetOrderResponseType> getOrder(
            @RequestPayload JAXBElement<GetOrderRequestType> requestElement) {

        GetOrderRequestType request = requestElement.getValue();
        if (request == null) {
            throw new IllegalArgumentException("Missing request value");
        }

        OrderRecord record =
            orderService.requireOrder(request.getOrderId());

        GetOrderResponseType response =
            factory.createGetOrderResponseType();
        response.setOrderId(record.id());
        response.setState(record.state());

        return factory.createGetOrderResponse(response);
    }
}
~~~

`OrderService` và `OrderRecord` là abstraction nghiệp vụ minh họa, không phải class sẵn có trong Spring-WS. Cần cấu hình endpoint adapter hỗ trợ JAXB/JAXBElement và các dependency tương thích. Tùy binding, endpoint có thể khai báo object root `@XmlRootElement` trực tiếp thay vì `JAXBElement`; với class type thuần, wrapper giải quyết phần QName.

Đáng chú ý:

- `@PayloadRoot(namespace, localPart)` định tuyến theo **QName của root payload trên mạng**.
- `@RequestPayload` yêu cầu Spring-WS đọc payload và chuyển thành tham số phù hợp.
- `requestElement.getName()` cho biết QName thực sự gắn với phần tử.
- `requestElement.getValue()` chỉ lấy dữ liệu Java; bản thân value không bảo đảm bạn giữ được QName khi marshal lại.
- `@ResponsePayload` cho biết kết quả phải trở thành payload XML.
- `factory.createGetOrderResponse(response)` gắn **QName của response**, khác QName request.

Endpoint vẫn phải xử lý các trường hợp không hợp lệ theo XSD, lỗi nghiệp vụ và security bằng thành phần phù hợp. Ném `IllegalArgumentException` ở ví dụ không phải một chính sách SOAP Fault hoàn chỉnh; hệ thống thật cần exception resolver/validation và hợp đồng lỗi nhất quán.

### 7.1. Một phép kiểm tra QName ở ranh giới

Nếu có yêu cầu kiểm tra rõ wrapper trong logic tích hợp:

~~~java
private static final QName EXPECTED_REQUEST_QNAME =
    new QName("urn:example:orders:v1", "GetOrderRequest");

if (!EXPECTED_REQUEST_QNAME.equals(requestElement.getName())) {
    throw new IllegalArgumentException("Unexpected payload QName");
}
~~~

Nhớ import `javax.xml.namespace.QName`. Nếu đã dùng `@PayloadRoot` và endpoint mapping chuẩn, không cần lặp lại kiểm tra này ở mọi method; nó hữu ích khi một method/factory xử lý nhiều element names hoặc khi chẩn đoán sai schema.

## 8. SOAP client gửi `JAXBElement` bằng `WebServiceTemplate`

Cấu hình template sử dụng chung marshaller/unmarshaller:

~~~java
@Bean
public WebServiceTemplate ordersWebServiceTemplate(
        Jaxb2Marshaller ordersMarshaller) {

    WebServiceTemplate template = new WebServiceTemplate();
    template.setMarshaller(ordersMarshaller);
    template.setUnmarshaller(ordersMarshaller);
    template.setDefaultUri("http://localhost:8080/ws");

    return template;
}
~~~

Đường dẫn localhost chỉ dành cho ví dụ. Trong môi trường doanh nghiệp, URI, timeout, HTTP transport, TLS, truststore, SOAP version và chính sách WS-Security phải được cấu hình theo đối tác.

Cách gọi SOAP với type tách khỏi element:

~~~java
import jakarta.xml.bind.JAXBElement;
import javax.xml.namespace.QName;

public GetOrderResponseType getOrder(
        String orderId,
        WebServiceTemplate template) {

    ObjectFactory factory = new ObjectFactory();

    GetOrderRequestType request = factory.createGetOrderRequestType();
    request.setOrderId(orderId);

    JAXBElement<GetOrderRequestType> root =
        factory.createGetOrderRequest(request);

    Object rawResult = template.marshalSendAndReceive(root);

    if (!(rawResult instanceof JAXBElement<?> element)) {
        throw new IllegalStateException("Unexpected response shape");
    }

    QName expected = new QName(
        "urn:example:orders:v1", "GetOrderResponse");

    if (!expected.equals(element.getName())) {
        throw new IllegalStateException("Unexpected response QName");
    }

    if (!(element.getValue() instanceof GetOrderResponseType response)) {
        throw new IllegalStateException("Unexpected response type");
    }

    return response;
}
~~~

Đây là ví dụ minh họa một client **sử dụng model XJC và JAXB context tương ứng**. Trong code thật, đưa `WebServiceTemplate` và `ObjectFactory` vào dependency injection/lifecycle phù hợp; xử lý lỗi kết nối và SOAP Fault riêng, không coi mọi invocation đều trả response thành công.

Nếu client SOAP 1.1 yêu cầu `SOAPAction`, `WebServiceTemplate` có thể nhận `SoapActionCallback`. Nhưng SOAPAction thuộc binding/chính sách phía HTTP, **không sửa QName trong `JAXBElement`**.

### 8.1. Vì sao phải kiểm tra QName của response?

Cùng một Java type có thể được sử dụng bởi nhiều global elements. Nếu client chỉ ép `element.getValue()` sang type và bỏ qua `element.getName()`, client có thể chấp nhận một phần tử root khác ý định, nhất là khi contract đã thêm operation/version. Trong trường hợp type và element có quan hệ một-một được xác thực chặt chẽ, kiểm tra QName có thể do framework/schema validation đảm nhiệm; nhưng ở biên tích hợp, **xác nhận hợp đồng trên wire** là một kiểm thử quan trọng.

### 8.2. XML trên mạng trông như thế nào?

Với SOAP 1.1, message có thể là:

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:o="urn:example:orders:v1">
  <soapenv:Body>
    <o:GetOrderRequest>
      <o:orderId>ORD-42</o:orderId>
    </o:GetOrderRequest>
  </soapenv:Body>
</soapenv:Envelope>
~~~

Response thành công:

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:o="urn:example:orders:v1">
  <soapenv:Body>
    <o:GetOrderResponse>
      <o:orderId>ORD-42</o:orderId>
      <o:state>CREATED</o:state>
    </o:GetOrderResponse>
  </soapenv:Body>
</soapenv:Envelope>
~~~

JAXB tạo phần tử nghiệp vụ; Spring-WS đảm nhiệm Envelope. Dù dùng prefix khác `o`, QName phải khớp XSD và WSDL.

## 9. `JAXBElement`, giá trị vắng mặt và `xsi:nil`

Một điểm dễ nhầm: `JAXBElement<T>` có thể giữ một value `null` hoặc trạng thái nil, nhưng **điều đó không tự làm mọi XML với `xsi:nil="true"` hợp lệ theo XSD**.

Giả sử schema có:

~~~xml
<xs:element name="optionalComment"
            type="xs:string"
            minOccurs="0"
            nillable="true"/>
~~~

Ba trạng thái cần phân biệt:

| Trạng thái XML | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Phần tử vắng mặt | Không có `optionalComment` | Không cung cấp field |
| Phần tử xuất hiện, rỗng | `<optionalComment/>` | Có phần tử, giá trị chuỗi rỗng |
| Phần tử nil | `<optionalComment xsi:nil="true"/>` | Có phần tử được đánh dấu nil |

`minOccurs="0"` cho phép **không xuất hiện**; `nillable="true"` cho phép **một phần tử đã xuất hiện** có trạng thái nil. Nếu XSD quy định `nillable="false"` (mặc định), XML nil không hợp lệ.

Ngoài ra, `JAXBElement` có `isNil()` / `setNil(...)`; cách wrapper và nullable property được sinh ra phụ thuộc binding và scope. Đừng dùng `null`, “missing” và nil thay thế tùy tiện khi contract nghiệp vụ phân biệt chúng. Trong các hệ thống tích hợp, nên có sample XML và test riêng cho cả ba trạng thái.

**Không nhầm collection rỗng với phần tử nil**: một wrapper `items` có thể chứa 0 `item` nếu schema cho phép, còn một `item xsi:nil="true"` vẫn là một lần xuất hiện của `item`.

## 10. Chẩn đoán lỗi marshal/unmarshal và namespace

| Triệu chứng | Nguyên nhân thường gặp | Cách xác minh |
| --- | --- | --- |
| Marshal type báo thiếu `@XmlRootElement` | Đang marshal class biểu diễn named complex type, chưa có root | Kiểm tra `ObjectFactory`; bọc bằng `JAXBElement` đúng QName |
| XML root thành `getOrderRequest`, endpoint chờ `GetOrderRequest` | Tên root được suy ra từ class/annotation khác hợp đồng | Xem `@XmlRootElement(name=...)` và QName wire |
| Root đúng local name nhưng namespace rỗng | Bỏ `namespace` hoặc metadata package không được nạp | Kiểm tra `@XmlSchema`, `@XmlElementDecl` |
| Namespace đúng ở root, sai ở `orderId` | Child element unqualified | So `elementFormDefault` với `@XmlElement` |
| `setContextPath(...)` thất bại lúc startup | Package sai, thiếu `ObjectFactory`/`jaxb.index` | Kiểm tra artifact JAR/WAR và classpath |
| `UnmarshalException: unexpected element` | Payload root QName khác các element JAXB context biết | In expected QName/actual QName; kiểm tra schema version |
| `JAXBElement` có type đúng nhưng response root sai | Tạo wrapper bằng factory operation khác | So `element.getName()` với WSDL/XSD |
| JAXB client gửi XML đúng nhưng server không vào endpoint | `@PayloadRoot` sai QName hoặc servlet mapping sai | So Body root QName và endpoint annotation |
| Prefix XML khác prefix trong test | Test so text XML cứng, không so QName | Dùng XML-aware assertions/XSD validation |
| Thứ tự element khác `xs:sequence` | Binding/order chưa phù hợp contract | Kiểm tra `@XmlType(propOrder=...)`, XSD validation |
| JAXB marshal thành công nhưng XML vi phạm XSD | Validation chưa được cấu hình | Bật schema validation và test invalid payload |
| Java 17+/Spring 6 gặp lỗi `javax.xml.bind` class | Trộn XJC/JAXB runtime Java EE cũ với Jakarta | Chọn plugin, API, runtime cùng thế hệ |
| SOAP Fault bị ép như response thường | Fault path không được xử lý riêng | Dùng SOAP fault handler/exception mapping |

### 10.1. Quy trình gỡ lỗi có thứ tự

Khi gặp lỗi, kiểm tra theo thứ tự:

~~~mermaid
flowchart TD
    A["XML Body root có đúng QName theo XSD/WSDL?"] --> B{"Đúng?"}
    B -- "Không" --> C["Sửa namespace/local name hoặc wrapper"]
    B -- "Có" --> D["Model JAXB có @XmlRootElement?"]
    D --> E{"Có root annotation?"}
    E -- "Không" --> F["Dùng ObjectFactory + JAXBElement"]
    E -- "Có" --> G["Kiểm tra @XmlSchema và field binding"]
    F --> G
    G --> H["JAXB context có đủ class/ObjectFactory?"]
    H --> I["Schema validation và test XML wire"]
    I --> J["Endpoint mapping / client / fault / security"]
~~~

Đừng sửa `@PayloadRoot` theo tên class để “chạy được” nếu QName đó trái với hợp đồng đã giao cho đối tác. Bước đầu tiên luôn là xác định XML thật và XSD/WSDL mà hai bên đã thống nhất.

## 11. Validation, SOAP Fault và bảo mật không được bỏ qua

Ánh xạ JAXB đúng không bảo đảm mọi ràng buộc đã được áp dụng. Ví dụ XSD yêu cầu `orderId`, nhưng object Java có setter cho phép gán `null`; serializer có thể bỏ field và không báo lỗi nếu chưa bật validation. Vì vậy:

- **XSD validation** kiểm tra QName, thứ tự `xs:sequence`, field bắt buộc, kiểu dữ liệu, enumeration và cardinality.
- **Spring-WS `PayloadValidatingInterceptor`** có thể kiểm tra XML request/response theo XSD khi được cấu hình; còn `Jaxb2Marshaller.setSchema(...)` hỗ trợ schema validation ở tầng OXM.
- **Business validation** xác nhận `orderId` tồn tại, người gọi có quyền, trạng thái hợp lệ và các quy tắc ngoài khả năng XSD.
- **SOAP Fault** cần biểu diễn những lỗi client/server và fault detail theo hợp đồng; lỗi JAXB không nhất thiết tự trở thành fault code và detail mà đối tác muốn.
- **WS-Security** dùng interceptor/thư viện xác minh signature, timestamp, token và mã hóa thông điệp theo chính sách; JAXB chỉ đọc dữ liệu, không xác minh chữ ký.
- **HTTPS/TLS** cần kiểm tra chứng chỉ, trust chain và hostname; nếu có mTLS thì xác minh client certificate theo cấu hình.

### 11.1. Xác thực **đúng phần tử được xử lý**

Trong thông điệp SOAP có thể có Header, Body, nhiều namespace và các phần tử tên trùng nhau. Một kiểm tra tìm `//*[local-name()='GetOrderRequest']` không chứng minh nó là payload đã được xác thực hoặc đã được ký số. Cần bảo đảm hệ thống bảo mật xác minh đúng đối tượng XML được chuyển tới endpoint, tránh sai lệch giữa “nút được kiểm tra” và “nút được xử lý”.

Không tự viết kiểm chứng chữ ký bằng cách đọc `<Signature>` rồi kết luận hợp lệ. Dùng WS-Security/WSS4J đã cấu hình và kiểm thử các trường hợp chữ ký sai, timestamp hết hạn, phần tử bị thay thế hoặc XML wrapping.

### 11.2. XML parser và giới hạn tài nguyên

Với XML không tin cậy, cấu hình parser an toàn để chống XXE/DTD bên ngoài; đặt giới hạn kích thước request, độ sâu, thời gian xử lý và số lượng phần tử phù hợp. Đừng dùng một cấu hình debug bỏ qua validation hoặc chứng chỉ trong production. Log chỉ nên chứa correlation ID, root QName, mã lỗi và dữ liệu cần thiết đã được che.

`JAXBElement` chỉ mô tả **ràng buộc element/type**, không phải cơ chế an toàn cho XML. Việc nâng chất lượng tích hợp cần kiểm tra đồng thời contract, security và khả năng tương thích.

## 12. Kiểm thử đúng hợp đồng khi marshal/unmarshal

### 12.1. Ma trận các trường hợp quan trọng

| Ca kiểm thử | Đầu vào | Kỳ vọng |
| --- | --- | --- |
| Marshal class có `@XmlRootElement` đúng | `GetOrderRequest` đã gắn QName | XML root đúng namespace/local name |
| Marshal named type trực tiếp | `GetOrderRequestType` không có root | Bị từ chối hoặc cần wrapper, tùy cấu hình |
| Marshal bằng `ObjectFactory` | `createGetOrderRequest(value)` | XML root `{urn:example:orders:v1}GetOrderRequest` |
| Unmarshal XML dùng prefix khác | `o:` thành `ns3:` nhưng giữ URI | Nhận cùng QName/type |
| Unmarshal XML đổi namespace v1 → v2 | Root local name giữ nguyên | Không được tự nhận như v1 khi context/schema chỉ hỗ trợ v1 |
| Child element bỏ namespace | `orderId` không qualified | Schema validation từ chối |
| Thứ tự phần tử sai | Field đổi vị trí so với `xs:sequence` | Schema validation từ chối |
| `JAXBElement` response gắn nhầm QName request | Value response đúng type | Kiểm thử QName phát hiện sai |
| Lỗi `orderId` không tồn tại | XML hợp XSD nhưng nghiệp vụ không có đơn | SOAP Fault nghiệp vụ theo hợp đồng |
| SOAP Fault được trả thay response | Server tạo fault | Client xử lý fault path, không ép kiểu response |
| Header chữ ký bị sửa | Body có vẻ hợp lệ | WS-Security từ chối |
| Client khác nền tảng dùng WSDL | .NET/Java khác framework | Sinh stub và trao đổi SOAP XML tương thích |

### 12.2. Unit test tập trung vào QName

Khi muốn kiểm tra wrapper mà không cần chạy server:

~~~java
ObjectFactory factory = new ObjectFactory();
GetOrderRequestType value = factory.createGetOrderRequestType();
value.setOrderId("ORD-42");

JAXBElement<GetOrderRequestType> element =
    factory.createGetOrderRequest(value);

QName expected = new QName(
    "urn:example:orders:v1", "GetOrderRequest");

assertEquals(expected, element.getName());
assertEquals("ORD-42", element.getValue().getOrderId());
~~~

Test này xác định factory gắn QName đúng và value có dữ liệu; **nó chưa chứng minh XML sau marshal hợp lệ theo XSD**. Cần thêm test XML wire có schema validation.

Ví dụ test round-trip (mang tính khung code) với Spring OXM:

~~~java
ObjectFactory factory = new ObjectFactory();
GetOrderRequestType value = factory.createGetOrderRequestType();
value.setOrderId("ORD-42");

StringWriter out = new StringWriter();

marshaller.marshal(
    factory.createGetOrderRequest(value),
    new StreamResult(out));

Object unmarshalled = marshaller.unmarshal(
    new StreamSource(new StringReader(out.toString())));

if (!(unmarshalled instanceof JAXBElement<?> root)) {
    throw new AssertionError("Expected JAXBElement root");
}

assertEquals(
    new QName("urn:example:orders:v1", "GetOrderRequest"),
    root.getName());
~~~

Cần có import JUnit, `StringWriter`, `StringReader`, `StreamResult` và `StreamSource`, cùng bean `Jaxb2Marshaller` được cấu hình như ở mục 6. Đoạn khung test giả định unmarshal trả `JAXBElement` vì global element thuộc named type theo binding; nếu generator/binding khác, hãy kiểm tra kiểu kết quả thực tế thay vì cố ép vào một shape.

### 12.3. Kiểm thử trong Spring-WS

Với Spring-WS Test:

- `MockWebServiceClient` kiểm tra endpoint nhận đúng payload QName, ánh xạ request, trả XML response và xử lý SOAP Fault.
- `MockWebServiceServer` kiểm tra `WebServiceTemplate` gửi payload JAXB qua SOAP đúng hợp đồng, nhận response hoặc Fault như dự kiến.
- XSD validation khẳng định phần tử/namespace/thứ tự thực sự hợp đồng.
- Test integration với WSDL công bố và client khác nền tảng xác minh rằng JAXB type và element có thể tiêu thụ bên ngoài Java.

Không chỉ so sánh `toString()` của object hoặc prefix XML. Hãy kiểm tra namespace URI, localPart, cấu trúc và giá trị theo XML semantics.

## 13. Thực hành ra quyết định trong một dự án mới

~~~mermaid
flowchart TD
    A["XSD/WSDL contract-first"] --> B["Sinh JAXB với XJC tương thích"]
    B --> C{"Class có @XmlRootElement?"}
    C -- "Có" --> D["Marshal trực tiếp object root"]
    C -- "Không" --> E["ObjectFactory tạo JAXBElement<T>"]
    D --> F["Jaxb2Marshaller / WebServiceTemplate"]
    E --> F
    F --> G["Kiểm tra QName + XSD validation"]
    G --> H["SOAP endpoint/client + Fault tests"]
    H --> I["Security + interoperability tests"]
~~~

Các bước nên làm trước khi đưa endpoint lên môi trường tích hợp:

1. Chốt global elements cho request/response và namespace trong XSD/WSDL.
2. Sinh mã JAXB phù hợp Jakarta; xem `@XmlRootElement`, `@XmlElementDecl`, `@XmlSchema`, `ObjectFactory` và package thực tế.
3. Nếu model có root annotation, có thể marshal object trực tiếp. Nếu type thuần, dùng `ObjectFactory` tạo `JAXBElement` đúng global element.
4. Cấu hình `Jaxb2Marshaller` với JAXB context path hoặc classes/packages phù hợp; bật schema validation khi cần.
5. Dùng `@PayloadRoot` khớp QName của request; tạo response có QName riêng.
6. Kiểm tra XML thật trên wire, không dựa vào tên Java class hay XML prefix.
7. Kiểm thử SOAP Fault, XML security/WS-Security, TLS certificate, namespace version và client khác nền tảng.

### Bài tập tự kiểm tra

**Bài 1.** Một XSD định nghĩa `<xs:complexType name="CreateInvoiceType">` và `<xs:element name="CreateInvoiceRequest" type="tns:CreateInvoiceType">`. Vì sao class `CreateInvoiceType` có thể không marshal trực tiếp được? Viết thao tác `ObjectFactory` cần tìm.

**Bài 2.** So sánh `@XmlType(name="GetOrderRequestType")` với `@XmlRootElement(name="GetOrderRequest")`. Hai annotation này mô tả cùng một khái niệm hay hai khái niệm khác nhau?

**Bài 3.** Đối tác gửi XML với `xmlns:o="urn:example:orders:v1"` thay `xmlns:ord`, nhưng QName không đổi. Bạn có nên sửa `@PayloadRoot` hoặc JAXB class không? Vì sao?

**Bài 4.** Endpoint nhận `JAXBElement<GetOrderRequestType>`, nhưng client đặt root `CancelOrderRequest` cho cùng type. Thành phần nào có thể phân biệt hai thao tác? Vì sao kiểm tra riêng `getValue()` là chưa đủ?

**Bài 5.** Class Java đã marshal ra `<GetOrderRequest>` không có namespace. Hãy liệt kê những annotation/config cần kiểm tra, và cách xác minh XML đã sửa là đúng.

**Bài 6.** Trong dự án Jakarta JAXB, vì sao `javax.xml.namespace.QName` vẫn là import đúng? Tại sao không dùng `javax.xml.bind.JAXBElement`?

**Bài 7.** Nếu request hợp lệ theo JAXB nhưng thiếu `orderId` bắt buộc hoặc chứa XML signature giả, những lớp kiểm tra nào phải từ chối yêu cầu?

**Bài 8.** Hai version hợp đồng sử dụng cùng `GetOrderRequestType` Java nhưng global elements thuộc namespace v1 và v2. Bạn sẽ giữ ranh giới JAXB context, endpoint mapping và compatibility tests như thế nào?

**Ghi nhớ:** JAXB phải biết **cả cấu trúc giá trị lẫn QName của phần tử gốc**. `@XmlRootElement` gắn root vào class; `JAXBElement<T>` gắn root QName vào giá trị, thường thông qua `ObjectFactory`/`@XmlElementDecl`. Khi dùng Spring-WS, hãy giữ QName nhất quán giữa XSD/WSDL, JAXB, `@PayloadRoot` và SOAP client, đồng thời kiểm tra XML thực tế, SOAP Fault và chính sách bảo mật.
