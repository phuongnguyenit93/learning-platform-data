# AnnotationActionEndpointMapping và định tuyến bằng @Action

Trong một dịch vụ SOAP, client có thể gọi đúng URL và gửi một SOAP Body hợp lệ nhưng server vẫn **không chọn được endpoint**. Một nguyên nhân là dịch vụ dùng **WS-Addressing** để định tuyến: Spring Web Services (Spring-WS) cần đọc header `wsa:Action` và tìm method được khai báo bằng `@Action`, thay vì chỉ xét QName của phần tử gốc trong Body.

`AnnotationActionEndpointMapping` là cơ chế Spring-WS ánh xạ **WS-Addressing Action** vào các method `@Endpoint`. Nó hữu ích khi hợp đồng yêu cầu action URI, khi các SOAP/.NET/ESB systems trao đổi Message Addressing Properties hoặc khi cần điều phối reply/fault theo `ReplyTo` và `FaultTo`. Tuy nhiên, WS-Addressing không tự thay thế XSD validation, JAXB/OXM, SOAP Fault, phân quyền hay WS-Security.

Bài học thuộc chương **WS-Addressing** của module **SPRING_WEB_SERVICES**: phát triển dịch vụ SOAP theo hướng **contract-first** với XSD/WSDL, JAXB, endpoint và SOAP client, đồng thời xử lý SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích doanh nghiệp. Trọng tâm là **cách `AnnotationActionEndpointMapping` chọn handler qua `@Action`, cách cấu hình và kiểm thử định tuyến**, đặc biệt những điểm dễ nhầm với `@PayloadRoot` và `@SoapAction`.

## 1. WS-Addressing giải quyết bài toán gì?

Một SOAP message có hai vùng:

- **Body:** payload của operation, được mô tả bằng XSD/WSDL.
- **Header:** metadata dành cho các SOAP nodes, bao gồm routing, correlation và bảo mật.

WS-Addressing tiêu chuẩn hóa **Message Addressing Properties (MAPs)** ở mức thông điệp. Quan trọng nhất:

| Thuộc tính | Header WS-Addressing | Chức năng |
| --- | --- | --- |
| **Action** | `wsa:Action` | URI thể hiện **ý định** của message, có thể làm routing key |
| **To** | `wsa:To` | **Địa chỉ đích logic** của message |
| **MessageID** | `wsa:MessageID` | URI nhận diện một message để đối chiếu |
| **ReplyTo** | `wsa:ReplyTo/wsa:Address` | Endpoint reference nơi nhận phản hồi bình thường |
| **FaultTo** | `wsa:FaultTo/wsa:Address` | Endpoint reference nơi nhận Fault |
| **RelatesTo** | `wsa:RelatesTo` | Liên kết response hoặc Fault với message trước |
| **From** | `wsa:From` | Endpoint reference của nguồn gửi trong tình huống cần thiết |

Đây là cơ chế **độc lập về khái niệm với transport HTTP**: địa chỉ logic và địa chỉ trả lời có thể khác địa chỉ connection. Khi SOAP được gửi qua HTTP, message sender/servlet vẫn phải xử lý đúng URL và transport.

~~~mermaid
flowchart TD
    A["SOAP client"] --> T["HTTP/TLS + SOAP parser"]
    T --> D["MessageDispatcher"]
    D --> Q{"Chọn EndpointMapping"}
    Q --> P["@PayloadRoot<br/>root QName Body"]
    Q --> S["@SoapAction<br/>SOAP transport action"]
    Q --> W["AnnotationActionEndpointMapping<br/>wsa:Action"]
    W --> E["EndpointAdapter / JAXB"]
    E --> B["Application service"]
    B --> R["SOAP response hoặc Fault<br/>wsa:Action / RelatesTo"]
~~~

Sơ đồ là **tổng quan các chiến lược có thể tham gia**. Spring-WS không nhất thiết gọi cả ba mapping cho mọi request: dispatcher chọn handler theo **thứ tự mapping** và trả về mapping đầu tiên phù hợp.

## 2. Ví dụ SOAP request với WS-Addressing 1.0

Thông điệp SOAP 1.1 dùng WS-Addressing 1.0:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:wsa="http://www.w3.org/2005/08/addressing"
    xmlns:ord="urn:example:orders:v1">
    <soapenv:Header>
        <wsa:To>https://api.example.org/soap/orders</wsa:To>
        <wsa:Action>urn:example:orders:action:GetOrder</wsa:Action>
        <wsa:MessageID>urn:uuid:27f09ea4-6b3e-4df4-8a9e-1ac630fe6f16</wsa:MessageID>
        <wsa:ReplyTo>
            <wsa:Address>http://www.w3.org/2005/08/addressing/anonymous</wsa:Address>
        </wsa:ReplyTo>
    </soapenv:Header>
    <soapenv:Body>
        <ord:GetOrderRequest>
            <ord:orderId>ORD-1024</ord:orderId>
        </ord:GetOrderRequest>
    </soapenv:Body>
</soapenv:Envelope>
~~~

Trong XML này:

1. `wsa:Action` mang **URI** `urn:example:orders:action:GetOrder`, là khóa mà `@Action` có thể dùng.
2. `wsa:To` là đích logic. Nó có thể khác URL backend nội bộ sau reverse proxy.
3. `wsa:MessageID` định danh thông điệp, không mặc nhiên là khóa idempotency nghiệp vụ.
4. `ReplyTo=anonymous` chỉ ra reply thường trở lại bằng kênh trao đổi hiện tại (ví dụ HTTP response).
5. Body root có QName `{urn:example:orders:v1}GetOrderRequest`. Đây là định danh **khác** với action URI.

**Cần phân biệt hai namespace:** `http://schemas.xmlsoap.org/soap/envelope/` là SOAP 1.1; `http://www.w3.org/2005/08/addressing` là WS-Addressing 1.0. SOAP version, WS-Addressing version và XSD business namespace là **ba hệ version khác nhau**.

Prefix XML `wsa` có thể đổi thành `a` mà Header vẫn cùng QName; nhưng thay namespace URI sang `http://schemas.xmlsoap.org/ws/2004/08/addressing` làm thay đổi **phiên bản WS-Addressing**.

## 3. Phân biệt @Action, @SoapAction và @PayloadRoot

| Chiến lược | Annotation | Đọc từ đâu? | Ví dụ |
| --- | --- | --- | --- |
| Payload root | `@PayloadRoot(namespace=..., localPart=...)` | QName phần tử gốc trong SOAP Body | `{urn:example:orders:v1}GetOrderRequest` |
| SOAPAction | `@SoapAction("...")` | SOAP action của binding/transport | `urn:example:orders:soapaction:GetOrder` |
| WS-Addressing Action | `@Action("...")` | SOAP Header `wsa:Action` | `urn:example:orders:action:GetOrder` |

Một SOAP 1.1 request có thể mang:

~~~http
POST /soap/orders HTTP/1.1
Host: api.example.org
Content-Type: text/xml; charset=utf-8
SOAPAction: "urn:example:orders:soapaction:GetOrder"
~~~

Trong SOAP Header:

~~~xml
<wsa:Action xmlns:wsa="http://www.w3.org/2005/08/addressing">urn:example:orders:action:GetOrder</wsa:Action>
~~~

Hai giá trị **không tự bằng nhau**. Hợp đồng có thể yêu cầu nhất quán, nhưng `@SoapAction` không đọc `wsa:Action` và `@Action` không lấy HTTP `SOAPAction`. Tương tự, `wsa:To` không phải action: nó chỉ đích logic.

**WS-Addressing Action cũng không phải authorization token.** Một caller chưa xác thực có thể tự đặt Action thành tên operation nhạy cảm. Security và phân quyền cần được áp dụng độc lập.

## 4. AnnotationActionEndpointMapping vận hành thế nào?

Class `org.springframework.ws.soap.addressing.server.AnnotationActionEndpointMapping` triển khai `EndpointMapping`. Nó phát hiện các method thuộc Spring-managed `@Endpoint` beans được đánh dấu bằng `@Action`. Khi request mang header `wsa:Action` phù hợp với phiên bản WS-A được hỗ trợ, mapping có thể chọn method đó và đưa sang `EndpointAdapter`.

~~~mermaid
sequenceDiagram
    participant C as SOAP client
    participant D as MessageDispatcher
    participant M as AnnotationActionEndpointMapping
    participant E as @Endpoint method
    participant S as Domain service
    C->>D: SOAP Envelope có wsa:Action
    D->>M: Lookup handler
    M->>M: Đọc Message Addressing Properties
    M-->>D: MethodEndpoint / no match
    D->>E: Bind @RequestPayload qua adapter
    E->>S: Gọi nghiệp vụ sau kiểm tra hợp lệ
    S-->>E: Domain result
    E-->>D: @ResponsePayload
    D-->>C: SOAP response / Fault + WS-A headers
~~~

Method annotation đúng package:

~~~java
import org.springframework.ws.soap.addressing.server.annotation.Action;
~~~

`@Action` đặt trên **method**; nó có ba thuộc tính:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `value` | Action URI của **request**, dùng định tuyến |
| `output` | Action URI của **response thành công** |
| `fault` | Action URI của **SOAP Fault** đi ra |

`output` và `fault` là optional. Nếu bỏ trống, `AnnotationActionEndpointMapping` có thể dùng action của request và các suffix theo cấu hình `outputActionSuffix`/`faultActionSuffix` để tạo Action phản hồi. Khi WSDL quy định URI chính xác, **nên khai báo tường minh** thay vì dựa vào suffix.

Ví dụ:

~~~java
@Action(
    value = "urn:example:orders:action:GetOrder",
    output = "urn:example:orders:action:GetOrderResponse",
    fault = "urn:example:orders:action:GetOrderFault")
~~~

**Định tuyến không đồng nghĩa JAXB validation.** `@Action` chọn handler; `@RequestPayload` và `@ResponsePayload` điều khiển binding XML trong SOAP Body; XSD validation và authorization vẫn là trách nhiệm riêng.

## 5. Contract-first: XSD cho GetOrder và endpoint dùng @Action

Ví dụ `orders.xsd`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:ord="urn:example:orders:v1"
           targetNamespace="urn:example:orders:v1"
           elementFormDefault="qualified">

    <xs:simpleType name="OrderStatusType">
        <xs:restriction base="xs:string">
            <xs:enumeration value="PENDING"/>
            <xs:enumeration value="CONFIRMED"/>
            <xs:enumeration value="CANCELLED"/>
        </xs:restriction>
    </xs:simpleType>

    <xs:element name="GetOrderRequest">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="orderId" type="xs:string"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>

    <xs:element name="GetOrderResponse">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="orderId" type="xs:string"/>
                <xs:element name="status" type="ord:OrderStatusType"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
~~~

Endpoint minh họa:

~~~java
package org.example.orders.soap;

import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;
import org.springframework.ws.soap.addressing.server.annotation.Action;

@Endpoint
public class AddressingOrderEndpoint {
    private final OrderQueryService service;

    public AddressingOrderEndpoint(OrderQueryService service) {
        this.service = service;
    }

    @Action(
        value = "urn:example:orders:action:GetOrder",
        output = "urn:example:orders:action:GetOrderResponse",
        fault = "urn:example:orders:action:GetOrderFault")
    @ResponsePayload
    public GetOrderResponse getOrder(
            @RequestPayload GetOrderRequest request) {
        OrderStatusType status =
                service.findStatus(request.getOrderId());

        GetOrderResponse response = new GetOrderResponse();
        response.setOrderId(request.getOrderId());
        response.setStatus(status);
        return response;
    }
}
~~~

Đây là **mã minh họa**: `OrderQueryService` và các generated JAXB classes phải tồn tại, XJC/JAXB runtime đúng phiên bản và Spring-WS endpoint adapter phải hỗ trợ model. Nếu XSD tạo global element thông qua `JAXBElement<T>` thay vì `@XmlRootElement`, cần dùng `ObjectFactory`/resolver phù hợp, không sửa generated Java bằng tay.

Với request có `wsa:Action=urn:example:orders:action:GetOrder`, mapping có thể chọn `getOrder`, bind Body vào `GetOrderRequest` rồi marshal `GetOrderResponse`. Giá trị `output` mô tả WS-A Action của response; `fault` mô tả WS-A Action khi trả Fault theo đường processing của mapping.

**Tránh hai methods cùng request Action:** Java method name hoặc JAXB parameter khác nhau không biến một `Action URI` thành hai routing keys. Mỗi Action thuộc một handler có chủ đích trong mỗi mapping strategy.

## 6. @Address ràng buộc thêm đích logic wsa:To

Spring-WS có annotation `org.springframework.ws.soap.addressing.server.annotation.Address` đặt trên **endpoint class**. Nếu dùng, giá trị của nó được so với thuộc tính `To` của request.

~~~java
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.soap.addressing.server.annotation.Action;
import org.springframework.ws.soap.addressing.server.annotation.Address;

@Endpoint
@Address("https://api.example.org/soap/orders")
public class PublicOrderEndpoint {

    @Action("urn:example:orders:action:GetOrder")
    public void handleExample() {
        // Khung minh họa @Address; chưa khai báo JAXB parameters
        // và không dùng song song với endpoint cùng Action ở phần 5.
    }
}
~~~

`@Address` là **ràng buộc bổ sung**, không phải con đường chọn handler duy nhất thay cho `@Action`.

| Request To | @Address | Kết quả |
| --- | --- | --- |
| `https://api.example.org/soap/orders` | Bằng giá trị ví dụ | Có thể match nếu `Action` và header validity đúng |
| `https://api.example.org/soap/payments` | Không bằng | Không thỏa ràng buộc đích |
| `To` thiếu hoặc sai version | Có @Address | Xử lý theo WS-A header validation, không mặc định hợp lệ |
| Không đặt @Address | Không ràng buộc đích | WS-A mapping xét Action và các điều kiện của nó |

### Reverse proxy thường gây lỗi To không khớp

~~~text
Public SOAP endpoint:  https://api.example.org/soap/orders
Backend servlet:       http://orders-app:8080/ws
Client-sent wsa:To:     https://api.example.org/soap/orders
~~~

Nếu đặt `@Address("http://orders-app:8080/ws")`, server có thể không tìm thấy handler mặc dù HTTP POST đã tới đúng servlet. **Không yêu cầu client đổi To thành URL backend nội bộ** khi WSDL/policy công bố địa chỉ public; định nghĩa logical To nhất quán và kiểm thử qua proxy.

Đặc biệt, `wsa:To` có thể nằm trong **signed SOAP Header**. Proxy sửa trường này tùy tiện có thể khiến WS-Security signature verification thất bại.

## 7. @EnableWs đã đăng ký AnnotationActionEndpointMapping chưa?

Với Spring-WS Java configuration, `@EnableWs` nhập cơ chế cấu hình tương ứng `WsConfigurationSupport`, đăng ký các mapping/adapters chuẩn. Theo JavaDoc Spring-WS 4.1:

| Mapping | Annotation | `order` mặc định |
| --- | --- | --- |
| `PayloadRootAnnotationMethodEndpointMapping` | `@PayloadRoot` | **0** |
| `SoapActionAnnotationMethodEndpointMapping` | `@SoapAction` | **1** |
| `AnnotationActionEndpointMapping` | `@Action` | **2** |

**Số order nhỏ hơn được xét trước.** Một request match `@PayloadRoot` ở order 0 có thể được dispatch trước khi `@Action` order 2 được xét. Vì vậy, chỉ thêm `@Action` không bảo đảm mọi request sẽ đi qua WS-A-based routing nếu ứng dụng còn có các handlers theo payload hoặc SOAPAction.

### Cấu hình thông thường

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.config.annotation.EnableWs;

@EnableWs
@Configuration
public class OrdersWsConfiguration {
    // Mappings/adapters chuẩn được đăng ký bởi @EnableWs.
    // Endpoint phải được component-scan trong đúng SOAP context.
}
~~~

**Không tạo thêm một bean AnnotationActionEndpointMapping chỉ vì muốn dùng @Action**, nếu `@EnableWs` đã tạo mapping đó. Đăng ký lặp có thể khiến dispatcher xét nhiều mapping instances có thứ tự hoặc chính sách khác nhau.

### Vì sao cần chú ý thứ tự mapping?

Giả sử request:

~~~text
Body root QName = {urn:example:orders:v1}GetOrderRequest
SOAPAction      = urn:example:orders:soapaction:GetOrder
wsa:Action      = urn:example:orders:action:GetOrder
~~~

Nếu ba strategy đều có handler khớp, dispatcher với cấu hình order 0/1/2 thường chọn **mapping theo payload QName trước**. Điều này là hành vi của **nhiều EndpointMappings**, không phải xung đột của hai `@Action` trong cùng mapping.

Đối với operation nhạy cảm, **không dùng lựa chọn handler làm bằng chứng WS-A headers đã được xác minh**. Phải enforce Action/Body consistency, XSD, WS-Security và quyền truy cập độc lập với thứ tự mapping.

## 8. Tùy chỉnh WS-Addressing version theo ứng dụng

Spring-WS mặc định hỗ trợ hai biến thể WS-Addressing phổ biến:

| Biến thể | Namespace Header |
| --- | --- |
| WS-Addressing **1.0** | `http://www.w3.org/2005/08/addressing` |
| WS-Addressing **August 2004** | `http://schemas.xmlsoap.org/ws/2004/08/addressing` |

`AnnotationActionEndpointMapping` kế thừa cấu hình `versions`. Nếu đối tác chỉ cho phép WS-A 1.0, một cách tùy biến theo Spring-WS 4.1 là **dùng cấu hình kế thừa `WsConfigurationSupport` thay cho `@EnableWs`**, rồi giới hạn `AddressingVersion`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.config.annotation.WsConfigurationSupport;
import org.springframework.ws.soap.addressing.server.AnnotationActionEndpointMapping;
import org.springframework.ws.soap.addressing.version.Addressing10;
import org.springframework.ws.soap.addressing.version.AddressingVersion;

@Configuration
public class WsAddressing10OnlyConfiguration
        extends WsConfigurationSupport {

    @Bean
    @Override
    public AnnotationActionEndpointMapping annotationActionEndpointMapping() {
        AnnotationActionEndpointMapping mapping =
                super.annotationActionEndpointMapping();
        mapping.setVersions(new AddressingVersion[] {
                new Addressing10()
        });
        return mapping;
    }
}
~~~

**Không dùng class này đồng thời với một cấu hình `@EnableWs` khác** mà không hiểu cách các beans được kết hợp. Đây là phương án quản lý infrastructure thay thế; trong dự án dùng Spring Boot auto-config, cần kiểm tra bean registry và tránh đăng ký trùng. Đoạn ví dụ giữ `order=2`; nếu cần thay ưu tiên mapping phải thiết kế và test riêng.

### Version SOAP, WS-Addressing và business schema không đồng nhất

1. **SOAP 1.1 / 1.2:** Envelope namespace, Content-Type, SOAP Fault shape.
2. **WS-A 2005/08 / 2004/08:** namespace `Action`/`To`/`ReplyTo`, quy tắc addressing.
3. **Business XSD v1/v2:** QName request/response, JAXB classes, WSDL messages.

Một SOAP 1.1 Envelope dùng WS-Addressing 1.0 và business XSD `urn:example:orders:v1` là lựa chọn bình thường nếu binding/policy cho phép. **Không trộn WS-A headers của hai namespaces trong cùng một bộ MAPs**.

## 9. ReplyTo, FaultTo, MessageID và RelatesTo

WS-Addressing giúp điều phối nơi nhận **reply** và **fault**:

~~~text
Anonymous (WS-Addressing 1.0):
http://www.w3.org/2005/08/addressing/anonymous

None (WS-Addressing 1.0):
http://www.w3.org/2005/08/addressing/none
~~~

- **ReplyTo anonymous:** response thường quay lại trên kênh request–response hiện tại.
- **ReplyTo/FaultTo non-anonymous:** có thể yêu cầu server mở **kênh outbound mới** tới callback URI.
- **None:** mang semantics không có endpoint reply theo WS-A version/message exchange pattern; không tự ý áp cho mọi operation.
- **MessageID:** identifier của request; response có thể dùng `RelatesTo` để liên hệ với nó.

SOAP response minh họa:

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:wsa="http://www.w3.org/2005/08/addressing"
    xmlns:ord="urn:example:orders:v1">
    <soapenv:Header>
        <wsa:Action>urn:example:orders:action:GetOrderResponse</wsa:Action>
        <wsa:MessageID>urn:uuid:7ad93627-8d13-4cce-85f8-02c615519ef8</wsa:MessageID>
        <wsa:RelatesTo>urn:uuid:27f09ea4-6b3e-4df4-8a9e-1ac630fe6f16</wsa:RelatesTo>
    </soapenv:Header>
    <soapenv:Body>
        <ord:GetOrderResponse>
            <ord:orderId>ORD-1024</ord:orderId>
            <ord:status>CONFIRMED</ord:status>
        </ord:GetOrderResponse>
    </soapenv:Body>
</soapenv:Envelope>
~~~

`RelatesTo` cần trỏ đến **MessageID của request liên quan**. Nó không tự là danh tính client và không phải chìa khóa thay thế business idempotency. Với WS-A 1.0, `Addressing10.hasRequiredProperties(...)` có điều kiện kiểm tra `To`/`Action` và `MessageID` khi có reply/fault destinations theo context.

## 10. WebServiceTemplate client dùng ActionCallback

Spring-WS cung cấp `org.springframework.ws.soap.addressing.client.ActionCallback`, một `WebServiceMessageCallback` giúp client tạo WS-Addressing headers. **Đừng nhầm với `SoapActionCallback`**, vốn xử lý SOAPAction transport.

~~~java
import java.net.URI;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.soap.addressing.client.ActionCallback;

public final class OrdersSoapClient {
    private final WebServiceTemplate template;

    public OrdersSoapClient(WebServiceTemplate template) {
        this.template = template;
    }

    public Object getOrder(GetOrderRequest request) {
        ActionCallback action = new ActionCallback(
                URI.create("urn:example:orders:action:GetOrder"));
        return template.marshalSendAndReceive(
                "https://api.example.org/soap/orders", request, action);
    }
}
~~~

Ví dụ giả định `WebServiceTemplate` đã cấu hình SAAJ SOAP factory, JAXB/OXM marshaller/unmarshaller và HTTP sender/TLS; JAXB request root được hỗ trợ. Kết quả `Object` cần được kiểm tra hoặc unwrap `JAXBElement` theo generated model. Constructor `ActionCallback(URI)` dùng **Addressing10** theo mặc định và `To` phản ánh connection URI.

### Chỉ định WS-A version và To riêng

~~~java
import java.net.URI;
import org.springframework.ws.soap.addressing.client.ActionCallback;
import org.springframework.ws.soap.addressing.version.Addressing10;

ActionCallback callback = new ActionCallback(
        URI.create("urn:example:orders:action:GetOrder"),
        new Addressing10(),
        URI.create("https://api.example.org/soap/orders"));
~~~

### Đặt ReplyTo và FaultTo non-anonymous

~~~java
import java.net.URI;
import org.springframework.ws.soap.addressing.client.ActionCallback;
import org.springframework.ws.soap.addressing.core.EndpointReference;

ActionCallback callback = new ActionCallback(
        URI.create("urn:example:orders:action:GetOrder"));
callback.setReplyTo(new EndpointReference(
        URI.create("https://callbacks.example.org/soap/replies")));
callback.setFaultTo(new EndpointReference(
        URI.create("https://callbacks.example.org/soap/faults")));
~~~

**Đây mới là tạo WS-A headers**, không phải một giải pháp callback bất đồng bộ hoàn chỉnh. Với non-anonymous replies, client phải có receiver endpoint xử lý phản hồi, correlation (MessageID/RelatesTo), bảo mật callback, timeout và giải quyết tình huống mất reply. Một lời gọi `marshalSendAndReceive` đồng bộ có thể không phù hợp nếu response đi qua out-of-band channel.

## 11. Out-of-band ReplyTo/FaultTo và yêu cầu bảo mật SSRF

Ví dụ client gửi:

~~~xml
<wsa:ReplyTo xmlns:wsa="http://www.w3.org/2005/08/addressing">
    <wsa:Address>https://callbacks.partner.example.org/replies</wsa:Address>
</wsa:ReplyTo>
~~~

Khi đích trả lời không phải anonymous, server có thể phải gửi **một SOAP message mới** tới `ReplyTo` hoặc `FaultTo` bằng sender được cấu hình trên `AnnotationActionEndpointMapping`. Mapping này kế thừa API `setMessageSenders(WebServiceMessageSender[])`; các senders có trách nhiệm vận chuyển out-of-band messages qua HTTP(S), JMS hoặc transport phù hợp.

**Rủi ro:** `ReplyTo` và `FaultTo` do client gửi có thể trở thành **SSRF** nếu server tự động gọi bất kỳ URI nào. Một client độc hại có thể đưa URI loopback, private network, cloud metadata endpoint, redirect sang host nội bộ hoặc một server do attacker kiểm soát để nhận SOAP Fault chứa dữ liệu.

~~~mermaid
flowchart TD
    A["SOAP Header chứa ReplyTo/FaultTo"] --> B["SOAP parse và policy kiểm tra"]
    B --> C["WS-Security xác minh danh tính<br/>signature/timestamp/trust"]
    C --> D{"URI callback được phép?"}
    D -->|Không| X["Từ chối; không mở connection"]
    D -->|Có| E["DestinationPolicy / allowlist<br/>DNS/redirect/host rules"]
    E --> F["WS-A messageSenders<br/>TLS/mTLS + bounded timeouts"]
    F --> G["Callback receiver"]
    G --> H["RelatesTo / audit / business correlation"]
~~~

### 11.1. Khuyến nghị bảo vệ khi bật callback

1. **Allowlist cụ thể** schemes/hosts/ports đã đăng ký cho mỗi đối tác; không nhận tự do URI trong SOAP Header.
2. Xem xét DNS resolution, IP private/loopback/link-local, DNS rebinding và redirect theo hạ tầng thực tế.
3. **Không gửi Fault trước khi request được xác thực** khi callback URI do client chọn.
4. Giới hạn outbound concurrency, response size, rate, timeout và retries để tránh làm server nghẽn.
5. Không sao chép credential, WS-Security key hoặc thông tin nhạy cảm sang destination chưa được tin cậy.
6. Dùng TLS trust/hostname verification; nếu cần mTLS, ràng buộc chứng chỉ đúng callback receiver.
7. Test riêng `FaultTo`: đường lỗi đôi khi dễ kích hoạt hơn đường response thành công.

Theo tài liệu Spring-WS 4.1, các message senders HTTP dùng cho out-of-band replies có kiểm tra địa chỉ mặc định; dự án có thể cấu hình thêm **`DestinationPolicy`** để enforce allowlist và chính sách DNS. **Không coi mặc định là bảo đảm đầy đủ** cho mọi DNS/redirect/network topology. Khi cần gửi response/fault ra ngoài, phải thiết kế bảo mật trước khi cho phép một remote party điều khiển địa chỉ gửi.

### 11.2. Thứ tự WS-Security và WS-Addressing interceptor

Trong pipeline nhận request, một endpoint mapping theo WS-A thường gắn interceptor xử lý addressing. Với các out-of-band senders, Spring-WS 4.1 nhấn mạnh **WS-Security interceptor chạy trước WS-Addressing interceptor** (ví dụ `Wss4jSecurityInterceptor` và `AddressingEndpointInterceptor`) để tránh gửi Fault đến URI do người gửi không được xác minh cung cấp. Dù framework có cơ chế order cho các interceptor này, cần **kiểm tra và test cấu hình thật** của phiên bản đang deploy.

Lưu ý bảo vệ bằng endpoint interceptor không thay thế những giới hạn **trước endpoint mapping** như TLS/gateway allowlist, SOAP parser hardening hay giới hạn kích thước XML.

## 12. Đồng bộ Action URI với WSDL, XSD và SOAP binding

Trong dịch vụ **contract-first**, WSDL 1.1 công bố operations, input/output/fault messages, SOAP binding, địa chỉ port; XSD công bố các global elements. WS-Addressing metadata có thể khai báo **Action URI** cho các message đó.

Ví dụ trích đoạn `wsdl:portType`:

~~~xml
<!-- Giả định definitions đã khai báo wsdl, tns, ord, wsaw. -->
<wsdl:portType name="OrdersPortType">
    <wsdl:operation name="GetOrder">
        <wsdl:input
            message="tns:GetOrderInput"
            wsaw:Action="urn:example:orders:action:GetOrder"/>
        <wsdl:output
            message="tns:GetOrderOutput"
            wsaw:Action="urn:example:orders:action:GetOrderResponse"/>
        <wsdl:fault
            name="OrderNotFound"
            message="tns:OrderNotFoundFaultMessage"
            wsaw:Action="urn:example:orders:action:GetOrderFault"/>
    </wsdl:operation>
</wsdl:portType>
~~~

Một namespace WS-Addressing WSDL metadata extension thường gặp:

~~~xml
xmlns:wsaw="http://www.w3.org/2006/05/addressing/wsdl"
~~~

**Đây không phải WSDL hoàn chỉnh:** nó còn cần definitions, namespaces, message parts trỏ tới XSD elements, binding, service/port và `soap:address`. Một số công cụ/đối tác dùng namespace **WS-Addressing Metadata** khác như `wsam`; phải đối chiếu phiên bản extension và XSD/schema mà phía đối tác hiểu, không trộn tùy tiện `wsaw` và `wsam`.

### 12.1. Ba URI cần thống nhất

~~~text
WSDL input Action:
  urn:example:orders:action:GetOrder

SOAP request wsa:Action:
  urn:example:orders:action:GetOrder

Spring-WS @Action.value:
  urn:example:orders:action:GetOrder
~~~

Đây là **cùng một giá trị hợp đồng**. Đồng thời:

~~~text
WSDL output Action:
  urn:example:orders:action:GetOrderResponse

Spring-WS @Action.output:
  urn:example:orders:action:GetOrderResponse
~~~

Với Fault:

~~~text
WSDL fault Action:
  urn:example:orders:action:GetOrderFault

Spring-WS @Action.fault:
  urn:example:orders:action:GetOrderFault
~~~

**Không đổi URI vì Java class đổi tên.** Action URI thuộc hợp đồng public, có thể được client sinh mã hoặc ESB/WCF dùng. Đổi Action có thể phá tương thích ngay khi Body schema không đổi.

### 12.2. SOAPAction trong WSDL khác WS-A Action

WSDL SOAP 1.1 binding có thể chứa:

~~~xml
<soap:operation soapAction="urn:example:orders:soapaction:GetOrder"/>
~~~

`soap:operation soapAction` mô tả action theo SOAP binding/transport. Nó **không nhất thiết** giống `wsaw:Action`/`wsam:Action` của WS-Addressing, dù đối tác có thể yêu cầu hai giá trị khớp nhau. Khi tích hợp, kiểm tra metadata, headers thực tế và các mapping strategies đang bật.

### 12.3. Action không thay thế XSD

Một request có `wsa:Action=GetOrder` nhưng Body `<ord:CancelOrderRequest>` có thể vẫn chọn method GetOrder **nếu mapping chỉ xét Action**. Bước JAXB unmarshal/schema validation phải từ chối Body không hợp contract; không cố xử lý mọi Body trong một method vì action có vẻ đúng.

Nếu nghiệp vụ nhạy cảm, cần kiểm tra nhất quán **Action ↔ payload QName ↔ WSDL operation ↔ quyền của caller**. Những giá trị này có nhiệm vụ khác nhau, không phải nhiều tên cho cùng một cơ chế.

## 13. Duplicate @Action và shadowing bởi mapping khác

Hai nhóm lỗi rất khác nhau cần phân biệt.

### 13.1. Hai methods khai báo cùng request Action

~~~java
@Action("urn:example:orders:action:GetOrder")
public GetOrderResponse handleA(GetOrderRequest input) {
    // ...
    return null;
}

@Action("urn:example:orders:action:GetOrder")
public GetOrderResponse handleB(GetOrderRequest input) {
    // ...
    return null;
}
~~~

Đây là **pseudocode** minh họa, không phải handler production. Hai methods cùng dùng routing key `urn:example:orders:action:GetOrder`. Tên `handleA`/`handleB` khác nhau, package khác nhau hay overload khác nhau **không làm Action khác nhau**.

Tùy phiên bản Spring-WS/implementation, duplicate registration có thể bị phát hiện khi khởi tạo hoặc dẫn đến hành vi không mong muốn. Không dựa vào thứ tự bean registration để chọn handler “sau cùng thắng”; mỗi Action phải có một owner rõ ràng.

### 13.2. Một request đồng thời khớp nhiều EndpointMappings

~~~text
Root QName  = {urn:example:orders:v1}GetOrderRequest
SOAPAction  = urn:example:orders:soapaction:GetOrder
wsa:Action  = urn:example:orders:action:GetOrder
~~~

Nếu ứng dụng đăng ký các handlers theo `@PayloadRoot`, `@SoapAction` và `@Action`, thứ tự mặc định `0/1/2` có thể khiến method theo payload được chọn **trước** WS-A method.

Đây là **cạnh tranh giữa các chiến lược**; nó không nhất thiết tạo lỗi duplicate trong một `AnnotationActionEndpointMapping`. Giải pháp:

1. Xác định strategy nào là **nguồn định tuyến chính** cho từng operation.
2. Không đăng ký nhiều handlers có thể cùng match một request nếu không có thiết kế cụ thể.
3. Nếu giữ nhiều mappings, định nghĩa priority và test khi Action, SOAPAction, Body QName bất nhất.
4. Không sửa `setOrder` tùy tiện chỉ để chữa triệu chứng; nó có thể thay đổi hành vi của toàn bộ SOAP endpoints.
5. Đảm bảo authorization/WS-Security/XSD validation **không phụ thuộc việc một strategy cụ thể được gọi**.

## 14. SOAP Fault liên quan đến WS-Addressing

Lỗi có thể xảy ra ở nhiều tầng:

| Loại lỗi | Ví dụ | Phản ứng cần thiết kế |
| --- | --- | --- |
| **Addressing protocol** | Thiếu `wsa:Action` khi bắt buộc; `wsa:To` không hợp lệ | Addressing Fault theo WS-A version và config |
| **SOAP processing** | Header `mustUnderstand` nhắm tới node nhưng node không hiểu | SOAP MustUnderstand Fault |
| **SOAP version** | SOAP 1.2 Envelope tới stack 1.1 | VersionMismatch/transport handling |
| **Validation/JAXB** | Body khác XSD dù Action đúng | Fault dữ liệu, không gọi nghiệp vụ |
| **Authorization** | Action chọn CancelOrder nhưng caller không có quyền | Security/business Fault có kiểm soát |
| **Domain** | `orderId` không tồn tại | Typed business Fault theo WSDL nếu công bố |
| **Transport callback** | `FaultTo` host không reachable | Delivery failure/observability, không tự retry vô hạn |

Spring-WS có cơ chế WS-Addressing errors tương ứng như **invalid addressing header** hoặc **message addressing header required**, tùy `AddressingVersion`. `SoapFaultMappingExceptionResolver` và `@SoapFault` xử lý một số Java exceptions, nhưng không bảo đảm mọi lỗi trước dispatch đều đi qua cùng resolver.

### 14.1. Fault Action không phải SOAP Fault Code

Trong SOAP 1.2, một Fault message có thể có Header:

~~~xml
<env:Header xmlns:env="http://www.w3.org/2003/05/soap-envelope"
            xmlns:wsa="http://www.w3.org/2005/08/addressing">
    <wsa:Action>urn:example:orders:action:GetOrderFault</wsa:Action>
</env:Header>
~~~

Và Body:

~~~xml
<env:Fault xmlns:env="http://www.w3.org/2003/05/soap-envelope">
    <env:Code>
        <env:Value>env:Sender</env:Value>
    </env:Code>
    <env:Reason>
        <env:Text xml:lang="vi">Yêu cầu không hợp lệ</env:Text>
    </env:Reason>
</env:Fault>
~~~

Đây là **hai trích đoạn**, không phải hai SOAP messages hoàn chỉnh. `@Action(fault="...")` mô tả **WS-Addressing Action của message Fault**, còn `env:Code`/`env:Reason` mô tả **SOAP Fault**; typed Fault detail theo XSD là nội dung ứng dụng riêng.

### 14.2. FaultTo không bảo đảm mọi lỗi đều được callback

Nếu request thất bại trước khi parse SOAP, trong TLS handshake hoặc trước khi đủ MAPs, server có thể **không có** một SOAP message hợp lệ để gửi Fault qua `FaultTo`. Tương tự, khi URI FaultTo bị chính sách SSRF từ chối, không được cố gửi chỉ vì client mong muốn.

Không thiết kế SLA dựa trên giả định rằng mọi lỗi HTTP sẽ được chuyển thành SOAP Fault tại một URL callback.

## 15. WS-Addressing và WS-Security: hai nhiệm vụ riêng

Một caller chưa xác thực có thể tự gửi:

~~~xml
<wsa:Action xmlns:wsa="http://www.w3.org/2005/08/addressing">urn:example:orders:action:CancelOrder</wsa:Action>
~~~

`@Action` định tuyến theo header URI **chưa được tin cậy**; nó không chứng minh caller có quyền hủy đơn.

| Header | Rủi ro khi tin trực tiếp |
| --- | --- |
| `Action` | Caller chọn operation nhạy cảm không có quyền |
| `To` | Giả mạo logical destination/tenant |
| `ReplyTo`/`FaultTo` | SSRF, gửi response nhạy cảm tới attacker |
| `MessageID` | Giả mạo correlation, gây replay hoặc trùng ID |
| `RelatesTo` | Giả mạo quan hệ message |

Một hệ thống doanh nghiệp cần:

- TLS/mTLS theo transport policy, không tắt hostname verification.
- WS-Security signature/token/certificate trust/timestamp/replay protection theo hợp đồng.
- Xác minh **đúng SOAP parts và headers được ký**; nếu Action/To/ReplyTo ảnh hưởng bảo mật, cần được bảo vệ và ràng buộc với trusted identity.
- Authorization theo verified principal, scope, customer/tenant/resource trong Body.
- XSD/JAXB validation sau khi message được xử lý bảo mật phù hợp và trước tác dụng phụ nghiệp vụ.
- DestinationPolicy/allowlist cho mọi out-of-band callbacks.

**MustUnderstand không thay thế chữ ký.** `soapenv:mustUnderstand="1"` yêu cầu SOAP node đích xử lý header, không chứng minh header đã được xác thực.

### Chữ ký đúng trên node khác vẫn chưa đủ

Một request có thể có `ds:Signature` hợp lệ nhưng chỉ ký node **khác** với Body/Action được endpoint sử dụng, mở ra rủi ro XML Signature Wrapping hoặc header tampering. Security stack phải verify **coverage của dữ liệu thực sự được tiêu thụ**, không chỉ có mặt một phần tử `Signature`.

## 16. Kiểm thử định tuyến bằng SOAP message, không chỉ gọi Java method

Unit test:

~~~java
endpoint.getOrder(request);
~~~

chỉ chứng minh logic method chạy với Java input đã cung cấp. Nó **không chứng minh** Spring-WS dispatcher đọc được WS-A Action, xử lý To/ReplyTo, chọn đúng mapping order hoặc thêm output/fault Action.

### 16.1. Server-side MockWebServiceClient

Với Spring test application context đã đăng ký endpoint, có thể viết custom `RequestCreator` để tạo SOAP request có WS-A headers:

~~~java
import java.io.IOException;
import javax.xml.namespace.QName;
import javax.xml.transform.TransformerException;
import javax.xml.transform.TransformerFactory;
import org.springframework.xml.transform.StringSource;
import org.springframework.ws.WebServiceMessage;
import org.springframework.ws.soap.SoapMessage;
import org.springframework.ws.test.server.MockWebServiceClient;
import org.springframework.ws.test.server.RequestCreator;
import static org.springframework.ws.test.server.ResponseMatchers.payload;

String wsaNamespace = "http://www.w3.org/2005/08/addressing";
String payloadXml = """
    <ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
      <ord:orderId>ORD-1024</ord:orderId>
    </ord:GetOrderRequest>
    """;

RequestCreator request = factory -> {
    WebServiceMessage message = factory.createWebServiceMessage();
    try {
        TransformerFactory.newInstance().newTransformer()
                .transform(new StringSource(payloadXml),
                        message.getPayloadResult());
    } catch (TransformerException ex) {
        throw new IOException("Không tạo được SOAP test payload", ex);
    }

    SoapMessage soap = (SoapMessage) message;
    soap.getSoapHeader().addHeaderElement(
            new QName(wsaNamespace, "Action"))
            .setText("urn:example:orders:action:GetOrder");
    soap.getSoapHeader().addHeaderElement(
            new QName(wsaNamespace, "To"))
            .setText("https://api.example.org/soap/orders");
    return message;
};

MockWebServiceClient client =
        MockWebServiceClient.createClient(applicationContext);
client.sendRequest(request)
        .andExpect(payload(new StringSource(expectedResponseXml)));
~~~

Ví dụ là **khung test**, cần `applicationContext`, `expectedResponseXml` và service stub có response phù hợp. Java text blocks cần Java 15+. Với policy WS-A nghiêm ngặt, cần bổ sung `MessageID` và các MAPs thích hợp; hãy kiểm tra output/fault WS-A headers bằng matcher namespace-aware. `TransformerFactory` ở đây dùng **fixture XML tĩnh do test sở hữu**, không phải một XML parser cho dữ liệu không tin cậy trong production.

### 16.2. withPayload không tự tạo WS-A headers

~~~java
client.sendRequest(withPayload(new StringSource(payloadXml)));
~~~

Lệnh trên chỉ xây **Body payload**; nó **không tự thêm `wsa:Action`**. Nếu một method `@PayloadRoot` khớp và được gọi, test có thể vượt qua mà không hề kiểm tra `AnnotationActionEndpointMapping`. Muốn test WS-A routing phải gửi header đúng và xác minh chính xác handler/mapping được dùng.

### 16.3. MockWebServiceServer là test phía client

`MockWebServiceServer` kiểm tra `WebServiceTemplate` với `ActionCallback` đã tạo đúng `Action`, `To`, `MessageID`, `ReplyTo` và Body QName, đồng thời trả response/Fault giả lập. Nó **không kiểm chứng** server mapping `@Action`; phía server dùng `MockWebServiceClient`.

Các client Java/.NET/ESB có thể serialize prefix khác nhau. Hãy test dựa trên **QName, URI text, MAPs, SOAP binding**, không so raw XML bytes hoặc phụ thuộc prefix `wsa`.

## 17. Ma trận kiểm thử tích hợp WS-Addressing

| Test | Input hoặc cấu hình | Kỳ vọng |
| --- | --- | --- |
| Happy path | WS-A 1.0 Action đúng, To đúng, Body hợp XSD | Handler đúng, response hợp contract |
| Action sai | Giữ Body, đổi sang URI operation khác | Không gọi handler GetOrder theo WS-A mapping |
| Action thiếu | Không có `wsa:Action` | Không khớp WS-A mapping; lỗi theo runtime |
| Đổi prefix | `wsa` thành `x`, namespace giữ nguyên | Vẫn đọc đúng Action |
| Namespace cũ | WS-A 2004/08 thay 2005/08 | Theo `versions` hỗ trợ; không trộn namespaces |
| To sai | `@Address` ràng buộc public URL nhưng request dùng backend URL | Không match theo To |
| Proxy đúng | Public To, backend servlet khác | Routing vẫn hoạt động |
| Cùng Action, sai Body | Body root không hợp JAXB/XSD | Từ chối, không thực thi nghiệp vụ sai |
| Duplicate Action | Hai methods cùng URI | Phát hiện conflict hoặc hành vi đăng ký không chấp nhận |
| Shadowing | @PayloadRoot cũng match, order thấp hơn | Phát hiện handler được chọn theo order |
| Output Action | SOAP success | `wsa:Action` response đúng `@Action.output` |
| Fault Action | Exception được map thành SOAP Fault | Action Fault đúng theo policy khi response được tạo |
| Correlation | Request có MessageID | `RelatesTo` phản ánh request MessageID |
| Anonymous ReplyTo | HTTP request–response bình thường | Reply đi trên cùng kênh |
| Non-anonymous ReplyTo | Callback host được allowlist | Có outbound sender/receiver và security phù hợp |
| FaultTo không tin cậy | localhost/private/attacker URI | Không mở outbound connection |
| Signature sai | Action/To/Body bị thay sau khi ký | WS-Security từ chối, không gây side effect |
| SOAP 1.2 | SOAP1.2 Envelope, WS-A header 1.0 | Xử lý đúng version/Content-Type/Fault |
| Interoperability | Client sinh từ WSDL trên Java/.NET/ESB | Cùng Action, To, ReplyTo, SOAP version |

Trong negative tests, **HTTP status hoặc SOAP Fault cụ thể phụ thuộc phiên bản và cấu hình**. Bất biến quan trọng là **handler sai không được gọi**, không có tác dụng phụ, callback không tin cậy không được kết nối, và SOAP response/Fault đúng hợp đồng.

## 18. Chẩn đoán lỗi @Action thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra trước |
| --- | --- | --- |
| No endpoint mapping found | Thiếu/sai `wsa:Action` | Action URI và header namespace thực tế |
| Action đúng nhưng không match | WS-A version chưa hỗ trợ | `versions` trên mapping |
| To khác @Address | Public URL vs backend URL | Logical `wsa:To` và annotation |
| @Action method không chạy nhưng handler khác chạy | @PayloadRoot/@SoapAction ưu tiên hơn | Mapping order 0/1/2 |
| Không thấy mapping bean | @EnableWs/context thiếu hoặc khác | Runtime ApplicationContext |
| @Endpoint không được scan | Package/condition bean registration | Endpoint beans thực tế |
| Hai method cùng Action | Duplicate action registration | Mỗi Action một owner |
| SOAPAction đúng nhưng @Action không hoạt động | Nhầm HTTP SOAPAction với WS-A Action | So hai trường riêng |
| Body không unmarshal được | JAXB root/namespace sai | XSD, JAXB classes, EndpointAdapter |
| Response Action sai | Output không khai báo hoặc suffix không khớp | @Action.output và WSDL output action |
| Fault Action sai | Fault resolver/WS-A policy không phù hợp | @Action.fault, Fault path |
| MessageID bị mất | Client callback không tạo MAPs như kỳ vọng | ActionCallback và SOAP headers |
| Non-anonymous reply không tới | Thiếu sender, callback receiver hoặc TLS | messageSenders, endpoint, network |
| Callback URL bị từ chối | DestinationPolicy/allowlist | Host, DNS, redirect rules |
| Chữ ký hỏng sau reverse proxy | Proxy sửa Header To/Body được ký | Signature coverage và public address |
| Client nhận VersionMismatch | SOAP 1.1/1.2 mismatch | SAAJ factory, Content-Type, WSDL binding |

### Lưu đồ chẩn đoán

~~~mermaid
flowchart TD
    A["SOAP POST đến dịch vụ"] --> B{"Transport và SOAP parser OK?"}
    B -->|Không| C["HTTP/TLS, SOAP version, XML"]
    B -->|Có| D{"Action URI và WS-A version đúng?"}
    D -->|Không| E["Kiểm wsa:Action QName và namespace"]
    D -->|Có| F{"To khớp @Address nếu có?"}
    F -->|Không| G["Public logical address vs backend proxy"]
    F -->|Có| H{"Mapping khác được chọn trước?"}
    H -->|Có| I["Kiểm order 0/1/2, shadowed methods"]
    H -->|Không| J{"Endpoint adapter / JAXB OK?"}
    J -->|Không| K["Binding, XSD, @RequestPayload"]
    J -->|Có| L{"Security và authorization đạt?"}
    L -->|Không| M["Từ chối, không side effect"]
    L -->|Có| N["Business → WS-A response/Fault"]
~~~

Lưu đồ mô tả **cách điều tra**, không phải thứ tự callback bất biến: XML parser cần xử lý tối thiểu trước khi security engine đọc headers; endpoint mapping có thể được chọn trước endpoint-bound interceptors. **Bảo mật phải được xác minh trước khi tin dữ liệu hoặc gây side effects**.

## 19. Bài tập thực hành

### Bài 1 — Định tuyến bằng Action URI

Dùng XSD `GetOrderRequest/GetOrderResponse` ở phần 5, viết `@Endpoint` chỉ có `@Action`, không thêm `@PayloadRoot` cho method đó. Tạo SOAP request có `wsa:Action` và dùng `MockWebServiceClient` xác nhận đúng method.

### Bài 2 — So sánh ba chiến lược

Tạo request có Body QName, HTTP SOAPAction và WS-A Action khác nhau có chủ đích. Khi ba mapping strategies đều có handler, dự đoán thứ tự với `WsConfigurationSupport` order 0/1/2, rồi chứng minh bằng test.

### Bài 3 — @Address sau reverse proxy

Public SOAP endpoint `https://api.example.org/soap/orders` chuyển tới `http://orders-app:8080/ws`. Chọn `@Address` và giá trị `wsa:To` đúng theo hợp đồng. Thử gửi To là backend URL và giải thích vì sao không nên tự sửa Header đã ký ở proxy.

### Bài 4 — Khóa WS-A version

Viết hai SOAP fixtures có header namespace 2005/08 và 2004/08. Chạy với mapping mặc định rồi giới hạn chỉ `Addressing10` bằng cấu hình nâng cao; ghi nhận khác biệt.

### Bài 5 — Output và Fault Action

Khai báo `@Action(value,output,fault)` với ba URIs. Cho domain service trả thành công rồi ném business exception được resolver ánh xạ; xác minh response/fault Action và RelatesTo khi có SOAP message trả về.

### Bài 6 — Client ActionCallback

Dùng `WebServiceTemplate` + `ActionCallback` gửi SOAP request. Kiểm tra `Action`/`To`/`MessageID`/`ReplyTo`. So sánh với `SoapActionCallback` và giải thích vì sao hai callback không thay thế nhau.

### Bài 7 — Threat modeling FaultTo

Client chưa xác thực gửi `FaultTo=http://127.0.0.1:8080/admin` và request gây lỗi. Thiết kế lớp chặn từ gateway, WS-Security đến DestinationPolicy, kiểm soát DNS/redirect và bảo đảm không có outbound POST tới localhost.

### Bài 8 — Interoperability

Xây WSDL có Action metadata cho input/output/fault rồi sinh client Java/.NET/ESB. Thử hai phiên bản WS-A, SOAP binding và xác nhận nhận/đọc được response/Fault bằng QName, MAPs và typed detail phù hợp.

## 20. Checklist production cho AnnotationActionEndpointMapping

| Nhóm | Điều kiện cần đạt |
| --- | --- |
| **Contract** | XSD/WSDL công bố Body messages và Action URIs input/output/fault nhất quán |
| **Version** | SOAP 1.1/1.2 và WS-A 2005/08 hoặc 2004/08 được chọn rõ |
| **Endpoint registration** | @Endpoint là bean đúng servlet context; @EnableWs hoặc cấu hình thay thế có mapping |
| **Action keys** | @Action.value chính xác, mỗi URI một owner, không bị mapping khác shadow |
| **Mapping order** | Biết thứ tự 0/1/2 mặc định; mọi thay đổi priority có regression tests |
| **To/Address** | @Address và wsa:To hợp public logical endpoint qua reverse proxy |
| **Reply/Fault** | @Action.output/fault, RelatesTo/MessageID, Fault detail đúng hợp đồng |
| **Non-anonymous callbacks** | messageSenders/callback receiver có TLS, timeout, authentication và allowlist |
| **SSRF** | DestinationPolicy, hostname/IP/DNS/redirect controls trên ReplyTo và FaultTo |
| **Security** | WS-Security signature coverage/trust/timestamp; authorization theo caller đã xác minh |
| **Validation** | Body JAXB/XSD và Action/Body consistency; không gây side effect khi không hợp lệ |
| **Testing** | MockWebServiceClient, MockWebServiceServer, negative tests, HTTP(S) partner integration |
| **Observability** | Ghi Action URI, QName, MessageID/RelatesTo đã lọc; không log token/secret |

## 21. Tài liệu chuẩn để đối chiếu

- [Spring-WS Reference 4.1.4 — WS-Addressing](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/): Action mapping, @Address và out-of-band replies.
- [Spring-WS API — AnnotationActionEndpointMapping](https://www.springframework.org/spring-ws/docs/4.1.1/api/org/springframework/ws/soap/addressing/server/AnnotationActionEndpointMapping.html): mapping lookup, các cấu hình được kế thừa và output/fault actions.
- [Spring-WS API — Action annotation](https://docs.spring.io/spring-ws/docs/4.0.0-M2/api/org/springframework/ws/soap/addressing/server/annotation/Action.html): thuộc tính value/output/fault.
- [Spring-WS API — WsConfigurationSupport](https://docs.spring.io/spring-ws/docs/4.1.x-SNAPSHOT/api/org/springframework/ws/config/annotation/WsConfigurationSupport.html): thứ tự mặc định ba mapping.
- [Spring-WS API — ActionCallback](https://www.springframework.org/spring-ws/docs/4.1.1/api/org/springframework/ws/soap/addressing/client/ActionCallback.html): tạo WS-A headers phía client.
- [W3C Web Services Addressing 1.0 — Core](https://www.w3.org/TR/ws-addr-core/) và [SOAP Binding](https://www.w3.org/TR/ws-addr-soap/): chuẩn Message Addressing Properties và SOAP processing.

**Kết luận:** `AnnotationActionEndpointMapping` cho phép Spring-WS chọn `@Endpoint` method bằng **`wsa:Action` trong SOAP Header**. `@Action(value,output,fault)` xác định action URI của request, response thành công và Fault; `@Address` có thể bổ sung ràng buộc `wsa:To`. Cơ chế này **khác** `@PayloadRoot` và `@SoapAction`, và thứ tự EndpointMappings có thể khiến strategy khác được chọn trước. Để dịch vụ **SPRING_WEB_SERVICES** contract-first an toàn và tương thích, hãy giữ URI Action/To nhất quán với WSDL, kiểm soát ReplyTo/FaultTo chống SSRF, thực thi XSD/JAXB validation và WS-Security/authorization độc lập, đồng thời kiểm thử SOAP messages thực thay vì chỉ gọi Java method.
