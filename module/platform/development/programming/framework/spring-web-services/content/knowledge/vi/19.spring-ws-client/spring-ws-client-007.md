# SoapActionCallback và cấu hình action của lời gọi

## Mục tiêu học tập

Trong chương **Máy khách Spring-WS** thuộc module **SPRING_WEB_SERVICES**, chúng ta học cách cấu hình **SOAP action của một lời gọi client** bằng `SoapActionCallback` và `WebServiceTemplate`. Đây là một phần quan trọng của tích hợp SOAP **contract-first**: XSD/WSDL xác định hợp đồng, JAXB chuyển XML và Java, client thực hiện lời gọi, còn phía server có thể định tuyến theo payload QName hoặc SOAPAction.

Sau bài học, bạn có thể:

1. Đọc `soapAction` trong **WSDL 1.1 SOAP binding**, phân biệt nó với tên operation, URL của `soap:address` và QName của phần tử request.
2. Hiểu **SOAP 1.1 HTTP SOAPAction header**, cú pháp giá trị có dấu ngoặc kép trên wire, và vì sao không tự thêm dấu ngoặc kép vào constructor của `SoapActionCallback`.
3. Sử dụng `new SoapActionCallback(action)` với `WebServiceTemplate.marshalSendAndReceive(...)` để đặt action **cho từng lần gọi**.
4. Giải thích vì sao Spring-WS client **không tự động lấy action từ WSDL** chỉ vì đã cấu hình JAXB marshaller hoặc endpoint URI.
5. Phân biệt `SoapActionCallback` với `WebServiceMessageCallback`, `ClientInterceptor`, `SoapMessage.setSoapAction(...)` và WS-Addressing `ActionCallback`.
6. Xử lý đúng hợp đồng có **nhiều operation dùng chung một endpoint URL**, SOAPAction rỗng, action không thống nhất với payload và các khác biệt khi dùng SOAP 1.2.
7. Thiết kế một SOAP gateway client có constructor injection, cấu hình URI/message sender, exception handling, timeout và bảo mật tách bạch.
8. Kiểm thử action bằng `MockWebServiceServer`, test callback thuần Java, và kiểm tra HTTP headers/binding thực bằng integration test.
9. Tránh các lỗi phổ biến: hard-code sai action, dùng action như bằng chứng phân quyền, nhầm action với WSDL operation hoặc WS-Addressing header, và lưu request-specific action vào singleton mutable state.
10. Vận dụng checklist contract-first để duy trì tương thích khi WSDL/XSD, SOAP version, TLS/WS-Security hoặc client transport thay đổi.

## 1. Tình huống thực tế: Body đúng nhưng phía đối tác vẫn từ chối

Giả sử ứng dụng Spring Boot gọi SOAP service tra cứu đơn hàng của đối tác. Request gửi phần tử hợp lệ theo XSD:

```xml
<ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
    <ord:orderId>ORD-000042</ord:orderId>
</ord:GetOrderRequest>
```

Client đã JAXB-marshal chính xác, kết nối HTTPS thành công. Tuy nhiên phía server trả SOAP Fault như “operation not found”, HTTP error, hoặc thông báo SOAPAction không được hỗ trợ.

Một nguyên nhân thường gặp là **SOAPAction thiếu hoặc không khớp binding trong WSDL**. Ví dụ, WSDL yêu cầu:

```xml
<soap:operation soapAction="urn:example:orders:v1/GetOrder"
                style="document"/>
```

nhưng HTTP request thực tế lại gửi:

```http
SOAPAction: "urn:example:orders:v1/CancelOrder"
```

hoặc không gửi header theo profile server yêu cầu.

Trong Spring-WS client, cách đơn giản để đặt giá trị cho **một lời gọi** là:

```java
new SoapActionCallback("urn:example:orders:v1/GetOrder")
```

và truyền callback vào `WebServiceTemplate.marshalSendAndReceive(...)`.

**Điểm mấu chốt:** SOAPAction giúp mô tả **ý định thao tác theo SOAP binding**, không chứng minh danh tính người gửi, không thay thế SOAP Body và không tự cấp quyền cho người gọi.

## 2. Bốn khái niệm thường bị nhầm

Giả sử hợp đồng có operation `GetOrder`. Ta có bốn thông tin:

| Khái niệm | Giá trị minh họa | Nằm ở đâu? | Ý nghĩa |
| --- | --- | --- | --- |
| **Endpoint URL** | `https://partner.example.com/ws/orders` | `wsdl:service/wsdl:port/soap:address` hoặc cấu hình client | Nơi gửi request qua HTTP/TLS. |
| **Tên WSDL operation** | `GetOrder` | `wsdl:portType/wsdl:operation` và `wsdl:binding/wsdl:operation` | Tên thao tác trong hợp đồng. |
| **Payload root QName** | `{urn:example:orders:v1}GetOrderRequest` | `wsdl:message/wsdl:part` tham chiếu global XSD element; SOAP Body thực tế | Loại bản tin XML gửi tới endpoint. |
| **SOAPAction** | `urn:example:orders:v1/GetOrder` | `soap:operation/@soapAction` trong WSDL SOAP binding; trên HTTP theo SOAP 1.1 | Chỉ dấu action của request ở tầng SOAP/HTTP binding. |

Bốn giá trị này **có quan hệ nhưng không thay thế được nhau**.

### 2.1. Một URL có thể phục vụ nhiều operation

```text
POST https://partner.example.com/ws/orders

GetOrder:
  Payload QName = {urn:example:orders:v1}GetOrderRequest
  SOAPAction    = urn:example:orders:v1/GetOrder

CancelOrder:
  Payload QName = {urn:example:orders:v1}CancelOrderRequest
  SOAPAction    = urn:example:orders:v1/CancelOrder
```

Cả hai operation dùng **cùng URL**. Vì thế, không thể suy ra SOAPAction từ phần cuối URL `/orders`.

### 2.2. SOAPAction không bắt buộc trùng tên Java method

Server Spring-WS có thể khai báo:

```java
@Endpoint
public class OrdersEndpoint {

    @PayloadRoot(
        namespace = "urn:example:orders:v1",
        localPart = "GetOrderRequest")
    @ResponsePayload
    public GetOrderResponse handleLookup(
            @RequestPayload GetOrderRequest request) {
        // ...
    }
}
```

Tên Java method `handleLookup` không quyết định literal SOAPAction; giá trị đúng phải đến từ **WSDL/binding và thỏa thuận tích hợp**.

### 2.3. SOAPAction và HTTP header Authorization là hai việc khác nhau

Header `SOAPAction` có thể do bất kỳ client đủ khả năng gửi HTTP tự đặt. Nó không chứng minh caller có quyền `orders:read`. Một SOAP client production cần cấu hình riêng cho TLS/mTLS, token, WS-Security và phân quyền trên server.

## 3. Đọc action từ WSDL 1.1

### 3.1. Ví dụ WSDL contract-first tối giản nhưng đầy đủ cấu trúc

Bản WSDL sau dùng SOAP 1.1 **document/literal**, với hai operation và một service address. XSD minh họa được đặt inline trong `wsdl:types`.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<wsdl:definitions
    xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
    xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:tns="urn:example:orders:service:v1"
    xmlns:ord="urn:example:orders:v1"
    targetNamespace="urn:example:orders:service:v1"
    name="OrdersService">

    <wsdl:types>
        <xs:schema
            targetNamespace="urn:example:orders:v1"
            xmlns:ord="urn:example:orders:v1"
            elementFormDefault="qualified">

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
                        <xs:element name="status" type="xs:string"/>
                    </xs:sequence>
                </xs:complexType>
            </xs:element>

            <xs:element name="CancelOrderRequest">
                <xs:complexType>
                    <xs:sequence>
                        <xs:element name="orderId" type="xs:string"/>
                    </xs:sequence>
                </xs:complexType>
            </xs:element>

            <xs:element name="CancelOrderResponse">
                <xs:complexType>
                    <xs:sequence>
                        <xs:element name="cancelled" type="xs:boolean"/>
                    </xs:sequence>
                </xs:complexType>
            </xs:element>
        </xs:schema>
    </wsdl:types>

    <wsdl:message name="GetOrderInput">
        <wsdl:part name="parameters" element="ord:GetOrderRequest"/>
    </wsdl:message>
    <wsdl:message name="GetOrderOutput">
        <wsdl:part name="parameters" element="ord:GetOrderResponse"/>
    </wsdl:message>

    <wsdl:message name="CancelOrderInput">
        <wsdl:part name="parameters" element="ord:CancelOrderRequest"/>
    </wsdl:message>
    <wsdl:message name="CancelOrderOutput">
        <wsdl:part name="parameters" element="ord:CancelOrderResponse"/>
    </wsdl:message>

    <wsdl:portType name="OrdersPortType">
        <wsdl:operation name="GetOrder">
            <wsdl:input message="tns:GetOrderInput"/>
            <wsdl:output message="tns:GetOrderOutput"/>
        </wsdl:operation>
        <wsdl:operation name="CancelOrder">
            <wsdl:input message="tns:CancelOrderInput"/>
            <wsdl:output message="tns:CancelOrderOutput"/>
        </wsdl:operation>
    </wsdl:portType>

    <wsdl:binding name="OrdersSoap11Binding"
                  type="tns:OrdersPortType">
        <soap:binding
            style="document"
            transport="http://schemas.xmlsoap.org/soap/http"/>

        <wsdl:operation name="GetOrder">
            <soap:operation
                soapAction="urn:example:orders:v1/GetOrder"/>
            <wsdl:input>
                <soap:body use="literal"/>
            </wsdl:input>
            <wsdl:output>
                <soap:body use="literal"/>
            </wsdl:output>
        </wsdl:operation>

        <wsdl:operation name="CancelOrder">
            <soap:operation
                soapAction="urn:example:orders:v1/CancelOrder"/>
            <wsdl:input>
                <soap:body use="literal"/>
            </wsdl:input>
            <wsdl:output>
                <soap:body use="literal"/>
            </wsdl:output>
        </wsdl:operation>
    </wsdl:binding>

    <wsdl:service name="OrdersService">
        <wsdl:port name="OrdersSoap11Port"
                   binding="tns:OrdersSoap11Binding">
            <soap:address
                location="https://partner.example.com/ws/orders"/>
        </wsdl:port>
    </wsdl:service>
</wsdl:definitions>
```

Trong file này, thông tin cần đọc để cấu hình client gồm:

- `wsdl:service/wsdl:port/soap:address/@location`: **URL mặc định** mà bên cung cấp công bố.
- `wsdl:port/@binding`: tên **binding** ứng với port.
- `wsdl:binding/@type`: tham chiếu `portType` gồm các operation.
- `wsdl:binding/wsdl:operation[@name='GetOrder']/soap:operation/@soapAction`: **action của lời gọi GetOrder**.
- `wsdl:message/wsdl:part/@element`: phần tử XSD xuất hiện trong SOAP Body, dùng để tạo JAXB request.

**Lưu ý:** Literal action trong binding ví dụ được chủ động chọn cho mục đích học. Khi tích hợp đối tác thật, **không tự thay** literal này theo quy tắc đặt tên riêng; đọc từ **WSDL của đúng environment/version/port**.

### 3.2. Tại sao phải bắt đầu từ đúng service/port/binding?

Một WSDL có thể công bố **nhiều port** hoặc **nhiều binding**, ví dụ SOAP 1.1, SOAP 1.2, một endpoint nội bộ và một endpoint công khai. Không nên tìm chuỗi `soapAction` đầu tiên trong toàn file rồi dùng cho mọi operation.

Quy trình:

1. Chọn `wsdl:service` và `wsdl:port` sẽ gọi.
2. Lần theo QName của `wsdl:port/@binding` tới binding tương ứng.
3. Kiểm tra binding có phải SOAP 1.1/1.2 và sử dụng transport nào.
4. Tìm `wsdl:operation` đúng tên trong **binding đó**.
5. Đọc `soap:operation/@soapAction`, kể cả trường hợp giá trị rỗng.
6. Đối chiếu input message → XSD global element để biết **JAXB request phải biểu diễn phần tử nào**.
7. Đối chiếu yêu cầu security từ chính sách giao tiếp/WS-SecurityPolicy, không suy từ action.

### 3.3. Điều gì thay đổi khi WSDL được sinh động?

`DefaultWsdl11Definition` trong Spring-WS có thể tạo WSDL từ XSD và quy ước request/response suffix. WSDL thực sự được xuất bản có thể **không giống** một WSDL thủ công, đặc biệt ở tên operation/action/binding.

Nếu đối tác yêu cầu SOAPAction **chính xác**, hãy kiểm tra **WSDL được xuất bản**, không chỉ XSD và tên Java method. Trường hợp cần kiểm soát chặt hợp đồng, cân nhắc công bố WSDL tĩnh qua `SimpleWsdl11Definition` hoặc cơ chế authoring đã được phê duyệt.

## 4. SOAP 1.1: HTTP SOAPAction có hình dạng gì?

SOAP 1.1 HTTP binding sử dụng request header `SOAPAction` để mô tả ý định của thông điệp.

Ví dụ đầy đủ:

```http
POST /ws/orders HTTP/1.1
Host: partner.example.com
Content-Type: text/xml; charset=utf-8
SOAPAction: "urn:example:orders:v1/GetOrder"
```

SOAP Envelope tương ứng:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1">
    <soap:Header/>
    <soap:Body>
        <ord:GetOrderRequest>
            <ord:orderId>ORD-000042</ord:orderId>
        </ord:GetOrderRequest>
    </soap:Body>
</soap:Envelope>
```

### 4.1. Phân biệt giá trị logic và cách biểu diễn trên wire

Khi gọi:

```java
new SoapActionCallback("urn:example:orders:v1/GetOrder")
```

hãy truyền **chuỗi action** được WSDL công bố, không tự bọc thêm hai dấu `"` vào Java string.

Một số SOAP transport sẽ biểu diễn action dưới dạng header có dấu ngoặc kép:

```http
SOAPAction: "urn:example:orders:v1/GetOrder"
```

Giá trị logic là `urn:example:orders:v1/GetOrder`. Nếu cố tình truyền dấu ngoặc kép trong giá trị constructor, bạn có thể gặp **double quoting** hoặc sai so sánh với server/gateway.

### 4.2. SOAPAction rỗng và SOAPAction vắng mặt

Theo SOAP 1.1, cần phân biệt về ngữ nghĩa:

```http
SOAPAction: "urn:example:orders:v1/GetOrder"
```

```http
SOAPAction: ""
```

```http
SOAPAction:
```

và trường hợp **không có header SOAPAction**.

Một số server legacy hoặc gateway nhạy với các biến thể này. Nếu WSDL có `soapAction=""`, không tự sinh chuỗi từ tên operation “cho đẹp”; hãy kiểm tra **đúng yêu cầu của binding và nhà cung cấp**.

`SoapActionCallback` dùng để **đặt action trên SOAP message**. Nó không phải cơ chế tổng quát để bảo đảm mỗi biến thể header HTTP rỗng/vắng đều được wire hóa giống nhau ở mọi transport. Khi đối tác yêu cầu cú pháp đặc biệt, cần thử **HTTP request thực tế** từ sender đã chọn.

### 4.3. HTTP SOAPAction không phải SOAP Header element

`SOAPAction` ở ví dụ SOAP 1.1 nằm trong **HTTP request headers**, không phải:

```xml
<soap:Header>
    <SOAPAction>urn:example:orders:v1/GetOrder</SOAPAction>
</soap:Header>
```

Đoạn XML trên **không tương đương** HTTP SOAPAction. Đừng thêm custom XML header tên `SOAPAction` để chữa lỗi thiếu HTTP header.

## 5. `SoapActionCallback` trong Spring Web Services

Class nằm tại:

```java
org.springframework.ws.soap.client.core.SoapActionCallback
```

Nó là một implementation của:

```java
org.springframework.ws.client.core.WebServiceMessageCallback
```

### 5.1. Ý tưởng API

```java
import org.springframework.ws.soap.client.core.SoapActionCallback;

SoapActionCallback callback = new SoapActionCallback(
        "urn:example:orders:v1/GetOrder");
```

Callback được `WebServiceTemplate` gọi trong quá trình chuẩn bị request message. Về nguyên lý, hành động trọng tâm của nó tương đương:

```java
WebServiceMessageCallback callback = message -> {
    SoapMessage soapMessage = (SoapMessage) message;
    soapMessage.setSoapAction(
            "urn:example:orders:v1/GetOrder");
};
```

Đoạn tương đương là **minh họa**: cần imports `WebServiceMessageCallback`, `SoapMessage` và message factory phải tạo SOAP message đúng loại. Dùng `SoapActionCallback` giúp tránh tự viết cast và làm rõ ý định.

### 5.2. Callback thay đổi gì?

- Đặt giá trị **SOAP action** trên một `SoapMessage` đang chuẩn bị gửi.
- Không thay đổi QName của JAXB payload.
- Không thay endpoint URI mà `WebServiceTemplate` sẽ kết nối.
- Không tự thêm WS-Security token/chữ ký.
- Không tự định nghĩa WSDL hoặc validate XSD.
- Không chứng minh lời gọi có quyền truy cập operation phía server.
- Không tự bắt lỗi network, timeout hay giải mã SOAP Fault.

### 5.3. Callback cần SOAP message

`SoapActionCallback` được thiết kế cho `SoapMessage`. Nếu client sử dụng một `WebServiceMessageFactory` không tạo SOAP message hoặc một transport/message type không phù hợp, không nên giả định callback vẫn hoạt động.

Để làm việc với SOAP 1.1/1.2, cần message factory, SOAP protocol và sender tương thích với binding thực tế.

## 6. Cách gọi trực tiếp với `WebServiceTemplate`

### 6.1. Ví dụ cơ bản

Giả sử bạn đã có một `WebServiceTemplate` được cấu hình JAXB marshaller/unmarshaller:

```java
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.soap.client.core.SoapActionCallback;

GetOrderRequest request = new GetOrderRequest();
request.setOrderId("ORD-000042");

Object reply = webServiceTemplate.marshalSendAndReceive(
        "https://partner.example.com/ws/orders",
        request,
        new SoapActionCallback("urn:example:orders:v1/GetOrder"));

GetOrderResponse response = (GetOrderResponse) reply;
```

Ở đây:

1. Tham số thứ nhất là **endpoint URI** dùng để kết nối.
2. Tham số thứ hai là **JAXB request payload**.
3. Tham số thứ ba là **request callback** được gọi để điều chỉnh SOAP message trước khi gửi, gồm action.
4. `marshalSendAndReceive` trả về Java object từ response unmarshalling theo cấu hình đã có.
5. Nếu đối tác trả SOAP Fault, transport lỗi, hoặc reply có kiểu khác kỳ vọng, lời gọi có thể ném exception hoặc trả đối tượng khác; phải có chính sách xử lý lỗi.

### 6.2. Overload dùng `defaultUri`

Nếu template đã có `defaultUri`:

```java
Object reply = webServiceTemplate.marshalSendAndReceive(
        request,
        new SoapActionCallback("urn:example:orders:v1/GetOrder"));
```

Cách này phù hợp khi một SOAP client instance chuyên gọi một service endpoint. Để giảm nhầm lẫn, cấu hình URL trong một bean/client chuyên trách và action theo operation.

### 6.3. Action khác nhau theo operation

```java
GetOrderResponse getOrder(String orderId) {
    GetOrderRequest request = new GetOrderRequest();
    request.setOrderId(orderId);

    return (GetOrderResponse) webServiceTemplate
            .marshalSendAndReceive(
                request,
                new SoapActionCallback(GET_ORDER_ACTION));
}

CancelOrderResponse cancelOrder(String orderId) {
    CancelOrderRequest request = new CancelOrderRequest();
    request.setOrderId(orderId);

    return (CancelOrderResponse) webServiceTemplate
            .marshalSendAndReceive(
                request,
                new SoapActionCallback(CANCEL_ORDER_ACTION));
}
```

Hai method trên minh họa một client có sẵn `webServiceTemplate`, `GET_ORDER_ACTION` và `CANCEL_ORDER_ACTION`. **Cùng default URI**, nhưng mỗi lời gọi gắn action của đúng WSDL operation.

Không nên đặt một field mutable kiểu `currentSoapAction` trong client singleton rồi thay đổi trước mỗi request; các thread đồng thời có thể ghi đè và làm gửi sai action.

## 7. Xây dựng một SOAP client gọn và dễ kiểm thử

Ví dụ sau dùng Spring Boot/Spring-WS với JAXB classes đã sinh từ XSD, cấu hình dependency injection và action constants tập trung.

### 7.1. Tập trung action theo hợp đồng

**`OrdersSoapContract.java`**

```java
package com.example.orders.soapclient;

public final class OrdersSoapContract {

    public static final String GET_ORDER_ACTION =
            "urn:example:orders:v1/GetOrder";

    public static final String CANCEL_ORDER_ACTION =
            "urn:example:orders:v1/CancelOrder";

    private OrdersSoapContract() {
    }
}
```

Việc lưu action trong constants tránh lỗi gõ lại cùng URI ở nhiều method, nhưng **không thay thế việc kiểm tra WSDL thật**. Nếu WSDL đổi action, cần review diff và cập nhật hợp đồng/test, không chỉ thay string cho test pass.

### 7.2. Spring configuration cho JAXB và template

**`OrdersSoapClientConfiguration.java`**

```java
package com.example.orders.soapclient;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.ws.client.core.WebServiceTemplate;

@Configuration
public class OrdersSoapClientConfiguration {

    @Bean
    public Jaxb2Marshaller ordersMarshaller() {
        Jaxb2Marshaller marshaller = new Jaxb2Marshaller();

        // Đúng package generated từ XSD/WSDL của đối tác.
        marshaller.setContextPath(
                "com.example.orders.contract");

        return marshaller;
    }

    @Bean
    public WebServiceTemplate ordersWebServiceTemplate(
            Jaxb2Marshaller ordersMarshaller) {

        WebServiceTemplate template = new WebServiceTemplate();
        template.setMarshaller(ordersMarshaller);
        template.setUnmarshaller(ordersMarshaller);

        // URL minh họa; production nên đưa vào configuration.
        template.setDefaultUri(
                "https://partner.example.com/ws/orders");

        return template;
    }
}
```

Cấu hình này minh họa **marshaller + unmarshaller + defaultUri**. Nó **chưa** cấu hình:

- Connect/read timeout, connection pool hoặc HTTP client sender.
- TLS/mTLS truststore/keystore.
- WS-Security outbound signing/token.
- Client interceptors, tracing và metrics.
- Retry/idempotency, circuit breaker hoặc exception mapping.
- Proxy hoặc cơ chế tìm địa chỉ thực tế theo môi trường.

Các phần này phải được bổ sung theo yêu cầu enterprise và stack message sender cụ thể.

### 7.3. SOAP gateway client dùng constructor injection

**`OrdersSoapClient.java`**

```java
package com.example.orders.soapclient;

import java.util.Objects;

import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.soap.client.core.SoapActionCallback;

import com.example.orders.contract.GetOrderRequest;
import com.example.orders.contract.GetOrderResponse;

import static com.example.orders.soapclient.OrdersSoapContract.GET_ORDER_ACTION;

public final class OrdersSoapClient {

    private final WebServiceTemplate template;

    public OrdersSoapClient(WebServiceTemplate template) {
        this.template = Objects.requireNonNull(template);
    }

    public GetOrderResponse getOrder(String orderId) {
        GetOrderRequest request = new GetOrderRequest();
        request.setOrderId(orderId);

        Object reply = template.marshalSendAndReceive(
                request,
                new SoapActionCallback(GET_ORDER_ACTION));

        if (reply instanceof GetOrderResponse response) {
            return response;
        }

        throw new IllegalStateException(
                "Unexpected GetOrder SOAP response type");
    }
}
```

Với JAXB/XJC tùy schema, `reply` đôi khi là `JAXBElement<GetOrderResponse>` chứ không phải trực tiếp `GetOrderResponse`. Khi đó cần xử lý wrapper hoặc điều chỉnh JAXB binding/return type theo code generated thực tế. **Đừng sửa XML contract chỉ để khớp một cast Java**.

### 7.4. Đăng ký client thành bean

Có thể thêm vào configuration:

```java
@Bean
public OrdersSoapClient ordersSoapClient(
        WebServiceTemplate ordersWebServiceTemplate) {
    return new OrdersSoapClient(ordersWebServiceTemplate);
}
```

Class `OrdersSoapClient` **không bắt buộc** extends `WebServiceGatewaySupport`. Nếu muốn dùng support class, có thể dùng `getWebServiceTemplate()`; cách dùng callback vẫn tương đương.

### 7.5. Dữ liệu nghiệp vụ ở lớp nào?

Một application service có thể dùng `OrdersSoapClient` qua interface `OrderGateway` để tránh phụ thuộc WSDL/JAXB. Tốt hơn là nó nhận domain DTO/command và để SOAP adapter tự map JAXB:

```text
Application service
    → OrderGateway (interface)
        → SpringWsOrderGateway (implementation)
            → WebServiceTemplate
            → JAXB generated classes
            → SoapActionCallback(GetOrder/CancelOrder)
```

Nhờ đó, unit tests của nghiệp vụ không cần gửi SOAP; test của SOAP gateway tập trung vào **payload + action + Fault/transport**.

## 8. Trình tự `WebServiceTemplate` tạo một lời gọi

Một mô hình khái niệm:

```mermaid
sequenceDiagram
    participant App as Application service
    participant Client as OrdersSoapClient
    participant WST as WebServiceTemplate
    participant CB as SoapActionCallback
    participant Sender as HTTP message sender
    participant Server as SOAP service

    App->>Client: getOrder("ORD-000042")
    Client->>WST: marshalSendAndReceive(request, callback)
    WST->>WST: Tạo SOAP request, JAXB marshal payload
    WST->>CB: doWithMessage(requestMessage)
    CB->>WST: Đặt SOAP action trên SoapMessage
    WST->>Sender: Chuẩn bị/gửi SOAP request
    Sender->>Server: HTTPS + SOAPAction + Envelope
    Server-->>Sender: SOAP response hoặc SOAP Fault
    Sender-->>WST: WebServiceMessage response
    WST->>WST: Kiểm tra lỗi/Fault; unmarshal nếu phù hợp
    WST-->>Client: Object response hoặc exception
    Client-->>App: Kết quả domain/response
```

Thứ tự nội bộ cụ thể của interceptor, connection và transport có thể khác theo phiên bản Spring-WS/message sender, nhưng **callback phải được áp dụng lên request message trước khi nó được gửi**.

### 8.1. Callback không truyền HTTP socket

`SoapActionCallback` không nhận `HttpServletRequest`. Nó chạy phía **SOAP client**, không phải một `@Endpoint` trên server. Việc set action trên `SoapMessage` sẽ được chuyển thành metadata transport phù hợp thông qua SOAP message factory và sender.

### 8.2. Không thiết lập action bằng cách sửa WSDL URL

URI trong `marshalSendAndReceive("https://...",...)` là URL service. Callback là **metadata operation**. Cả hai có thể thay đổi độc lập theo cấu hình và hợp đồng.

### 8.3. Không dùng SOAPAction để chọn dữ liệu riêng tư mà chưa authorize

Server có thể có `@SoapAction` mapping; một client gửi chuỗi đúng vẫn cần được xác thực và kiểm tra quyền trên operation, tenant và resource. SOAPAction là đầu vào có thể bị client giả mạo.

## 9. Khi không có `SoapActionCallback`, chuyện gì xảy ra?

Câu trả lời phụ thuộc message factory, callback khác, interceptor và binding của đối tác.

Nếu gọi:

```java
template.marshalSendAndReceive(request);
```

thì lời gọi này **không chỉ rõ action trong callback**. Không nên giả định Spring-WS sẽ tự tìm WSDL ở endpoint URL, phân tích `soap:operation` và chọn action dựa trên class JAXB hoặc tên method.

Trên wire, action có thể rỗng, vắng, là giá trị mặc định của SOAP message factory, hoặc được thiết lập bằng cơ chế khác. Muốn biết chính xác, hãy kiểm tra:

1. Request được tạo bởi `WebServiceMessageFactory` nào?
2. Có `ClientInterceptor` hoặc custom callback nào thay đổi SOAP action không?
3. SOAP 1.1 hay SOAP 1.2?
4. HTTP message sender nào đang dùng?
5. WSDL/SOAP binding yêu cầu giá trị nào?
6. HTTP request thực sự gửi gì?

**Hành vi không được quy định rõ trong client configuration là một rủi ro tương thích** khi nâng cấp thư viện hoặc đổi HTTP sender.

## 10. `@SoapAction` phía server và `SoapActionCallback` phía client

Spring-WS server có annotation:

```java
import org.springframework.ws.soap.server.endpoint.annotation.SoapAction;

@SoapAction("urn:example:orders:v1/GetOrder")
@ResponsePayload
public GetOrderResponse getOrder(
        @RequestPayload GetOrderRequest request) {
    // ...
}
```

`SoapActionAnnotationMethodEndpointMapping` có thể dùng action từ request để chọn method.

Phía client dùng:

```java
new SoapActionCallback("urn:example:orders:v1/GetOrder")
```

### 10.1. Đừng đánh đồng “action khớp” với “payload hợp lệ”

Một client có thể gửi:

```http
SOAPAction: "urn:example:orders:v1/GetOrder"
```

nhưng SOAP Body lại có:

```xml
<ord:CancelOrderRequest xmlns:ord="urn:example:orders:v1">
    <ord:orderId>ORD-000042</ord:orderId>
</ord:CancelOrderRequest>
```

Khi server có cả mapping theo payload QName và action, **thứ tự mapping** có thể ảnh hưởng method được chọn. Một ứng dụng an toàn phải có quy ước phát hiện mâu thuẫn, không âm thầm dùng action để đi vòng qua validation hoặc authorization.

### 10.2. `@PayloadRoot` vẫn hoạt động theo QName

Với `@PayloadRoot(namespace=...,localPart=...)`, server có thể chọn endpoint đúng chỉ từ request payload QName. Trong trường hợp đó, SOAPAction **có thể không được mapping đó dùng**, nhưng gateway hoặc hệ thống đối tác vẫn có thể kiểm tra header theo WSDL.

Do vậy câu “server của tôi không cần SOAPAction” **không đủ để suy ra đối tác/gateway cũng không cần**. Hợp đồng tích hợp mới là nguồn quyết định.

### 10.3. Chọn một chính sách nhất quán

Nếu hệ thống bạn quản lý cả client/server:

- Công bố literal action chính xác trong WSDL/binding.
- Đảm bảo `SoapActionCallback` gửi cùng literal.
- Kiểm tra payload QName với XSD.
- Nếu dùng đồng thời action-based và payload-based mapping, kiểm thử mâu thuẫn có chủ đích.
- Không cấp quyền dựa duy nhất vào action header.

## 11. Phân biệt SOAPAction và WS-Addressing Action

Hai chữ “Action” thường gây nhầm lẫn.

### 11.1. SOAPAction

Với SOAP 1.1 qua HTTP:

```http
SOAPAction: "urn:example:orders:v1/GetOrder"
```

Nó là thông tin của **SOAP HTTP binding**.

### 11.2. WS-Addressing `wsa:Action`

WS-Addressing định nghĩa SOAP Header, ví dụ:

```xml
<soap:Header
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:wsa="http://www.w3.org/2005/08/addressing">
    <wsa:Action soap:mustUnderstand="1">
        urn:example:orders:v1/GetOrder
    </wsa:Action>
    <wsa:To>https://partner.example.com/ws/orders</wsa:To>
</soap:Header>
```

`wsa:Action` nằm **bên trong SOAP Envelope**. Ngoài nó còn có thể có `wsa:MessageID`, `wsa:ReplyTo`, `wsa:FaultTo` tùy profile.

### 11.3. Spring-WS có callback riêng cho WS-Addressing

Trong Spring-WS, cơ chế client WS-Addressing sử dụng `org.springframework.ws.soap.addressing.client.ActionCallback` (khác `SoapActionCallback`). Cách khởi tạo/cấu hình chi tiết phụ thuộc WS-Addressing version, endpoint reference và thư viện đã chọn.

| Tiêu chí | `SoapActionCallback` | WS-Addressing `ActionCallback` |
| --- | --- | --- |
| Đối tượng | SOAP action theo SOAP binding/transport. | WS-Addressing header blocks/action. |
| Nơi dễ quan sát | SOAP 1.1 HTTP SOAPAction hoặc metadata SOAP 1.2 tương ứng. | SOAP Header `wsa:Action`. |
| Có thể dùng với | `WebServiceTemplate` callback. | `WebServiceTemplate` callback / WS-A infrastructure. |
| Giống WSDL operation name? | Không bắt buộc. | Không bắt buộc. |
| Là chứng cứ quyền? | Không. | Không. |

**Không chỉ đặt `SoapActionCallback` rồi tin rằng `wsa:Action` đã có mặt hoặc đã được ký.** Nếu đối tác yêu cầu cả hai, cần cấu hình và kiểm thử cả hai theo WS-Addressing/WS-Security profile.

### 11.4. SOAPAction và WS-A Action có phải cùng chuỗi?

Không nhất thiết, nhưng nhiều profile yêu cầu chúng **nhất quán** hoặc theo một quy tắc cụ thể. Nếu chúng mâu thuẫn, gateway hay SOAP node có thể từ chối. Chỉ dựa vào ví dụ literal giống nhau là không đủ; cần đọc WSDL, WS-Addressing metadata và integration specification.

## 12. SOAP 1.1 và SOAP 1.2: khác biệt ở tầng HTTP

`SoapActionCallback` đặt **action trên SOAP message**, còn cách biểu diễn trên wire phụ thuộc SOAP version/binding và implementation sender/message factory.

### 12.1. SOAP 1.1

Envelope namespace:

```text
http://schemas.xmlsoap.org/soap/envelope/
```

HTTP media type thường là:

```http
Content-Type: text/xml; charset=utf-8
SOAPAction: "urn:example:orders:v1/GetOrder"
```

### 12.2. SOAP 1.2

Envelope namespace:

```text
http://www.w3.org/2003/05/soap-envelope
```

SOAP 1.2 HTTP binding dùng media type `application/soap+xml`, có thể có **`action` parameter**:

```http
Content-Type: application/soap+xml; charset=utf-8; action="urn:example:orders:v1/GetOrder"
```

**Không** coi mẫu HTTP SOAP 1.1 với `text/xml` + `SOAPAction` là khuôn bắt buộc cho SOAP 1.2. Một số server, framework hoặc gateway có behavior/profile riêng; cần xác nhận thực tế.

### 12.3. Việc đặt action không tự chuyển SOAP version

Đoạn sau **không chuyển** SOAP 1.1 message factory thành SOAP 1.2:

```java
new SoapActionCallback("urn:example:orders:v1/GetOrder")
```

Muốn SOAP 1.2, phải có message factory, Envelope namespace, HTTP Content-Type, WSDL binding và đối tác hỗ trợ SOAP 1.2.

### 12.4. Test qua wire là bắt buộc khi đổi SOAP version

Kiểm tra đồng thời:

- Envelope namespace.
- HTTP Content-Type và action parameter/header thực.
- SOAPAction literal (nếu có).
- Action của WS-Addressing nếu được yêu cầu.
- Fault structure (`faultcode/faultstring` hay `Code/Reason`).
- Client-side message factory và SOAP server binding.
- Security signature/timestamp khi có WS-Security.

## 13. Cách kết hợp action với SOAP Header hoặc callback khác

`WebServiceTemplate.marshalSendAndReceive(...)` nhận một `WebServiceMessageCallback` cho request. Khi một operation còn cần thêm SOAP Header, có thể gom thao tác vào một callback.

### 13.1. Callback kết hợp

```java
import org.springframework.ws.client.core.WebServiceMessageCallback;
import org.springframework.ws.soap.SoapMessage;
import org.springframework.ws.soap.client.core.SoapActionCallback;

SoapActionCallback action =
        new SoapActionCallback(
                "urn:example:orders:v1/GetOrder");

WebServiceMessageCallback combined = message -> {
    action.doWithMessage(message);

    if (message instanceof SoapMessage soap) {
        // Thêm các SOAP Header theo contract bằng SOAP APIs
        // và marshalling/transformer được kiểm soát.
        // Không tự tạo wsse:Security giả thay cho WSS4J.
    }
};

Object reply = template.marshalSendAndReceive(
        request, combined);
```

Đây là ví dụ cấu trúc callback; mã thêm SOAP Header chi tiết phụ thuộc header QName/XSD và API phù hợp. Không viết một XML `<wsse:Security>` thủ công rồi coi là đã ký.

### 13.2. Khi nào dùng `ClientInterceptor`?

`ClientInterceptor` thích hợp cho chính sách **nhiều lời gọi**, chẳng hạn:

- Tracing, correlation, metrics.
- Thêm/kiểm tra SOAP Header chung theo hợp đồng.
- WS-Security outbound và inbound verification khi cấu hình đúng.
- Request/response logging có kiểm soát.
- Validation hoặc transformation theo chính sách.

`SoapActionCallback` rất phù hợp cho action **riêng của một operation**. Không ép một `ClientInterceptor` đoán operation bằng cách đọc tên Java method không có trong SOAP message.

### 13.3. Lưu ý thứ tự với security signing

Nếu SOAP message được ký theo WS-Security và action/WS-A Header cũng thuộc signed parts, thứ tự thêm header và ký phải tuân theo security profile. Đừng sửa phần XML được ký sau khi chữ ký đã được tạo.

Một unit test chỉ xác minh giá trị action **không chứng minh** phần WS-Addressing Header đã được ký hoặc token mTLS hợp lệ. Cần test security riêng.

## 14. Nhiều SOAP operation, một template và tính an toàn đồng thời

Một `WebServiceTemplate` thường được chia sẻ như Spring bean. Điều này tự nó **không có nghĩa** mọi tùy biến trong template/underlying sender đều có thể thay đổi động an toàn.

### 14.1. Tránh state mutable cho action hiện hành

Anti-pattern:

```java
public class UnsafeOrdersClient {
    private String currentAction; // Mutable shared state!

    public Object invoke(Object request, String action) {
        currentAction = action;

        // Interceptor khác đọc currentAction để set SOAPAction.
        return template.marshalSendAndReceive(request);
    }
}
```

Hai thread song song gọi `GetOrder` và `CancelOrder` có thể ghi đè action và gửi sai Header; đây là race condition.

### 14.2. Tạo callback cục bộ theo request

```java
public Object invoke(Object request, String action) {
    return template.marshalSendAndReceive(
            request, new SoapActionCallback(action));
}
```

Cách này giữ **action riêng ở request callback** thay vì ở field mutable. Tuy nhiên **action phải được chọn từ danh sách operation hợp lệ**, không được để input tùy ý của caller thay đổi action sang operation nhạy cảm.

### 14.3. Action mapping có thể đặt trong enum hoặc strategy

```java
enum OrderOperation {
    GET("urn:example:orders:v1/GetOrder"),
    CANCEL("urn:example:orders:v1/CancelOrder");

    private final String soapAction;

    OrderOperation(String soapAction) {
        this.soapAction = soapAction;
    }

    String soapAction() {
        return soapAction;
    }
}
```

Nếu dùng generic invoker, phải ràng buộc **operation → request type → expected response type → SOAPAction**, tránh tình trạng request `CancelOrderRequest` đi kèm action `GetOrder` do lỗi mapping.

## 15. Khi SOAPAction sai, lỗi sẽ xuất hiện ở đâu?

Một request có thể lỗi tại nhiều tầng.

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| HTTP 404 từ gateway | Sai URL/route. | `defaultUri`, target URI, reverse proxy path. |
| HTTP 415 Unsupported Media Type | SOAP 1.1/1.2 Content-Type hoặc encoding không phù hợp. | Message factory, Content-Type trên wire. |
| HTTP 401/403 | Thiếu hoặc sai authentication/authorization, policy gateway. | Token, mTLS, WS-Security, account permissions; không thay SOAPAction tùy tiện. |
| SOAP Fault “No endpoint mapping” | Action/Payload QName không khớp mapping. | WSDL binding, server `@PayloadRoot`/`@SoapAction`, mapping order. |
| SOAP Fault “Action not supported” | Chuỗi action, WS-A Action hoặc SOAP version sai. | Phân biệt HTTP SOAPAction với `wsa:Action`. |
| JAXB marshal failure | Generated class/schema/root element sai. | `@XmlRootElement`, `ObjectFactory`, package, marshaller; **không phải lỗi action**. |
| JAXB unmarshal failure | Response QName/type không tương ứng. | WSDL output message, schema và generated classes. |
| SOAP Fault nghiệp vụ `ORDER_NOT_FOUND` | Service đã xử lý operation nhưng không tìm thấy dữ liệu. | Fault code/reason/detail; không tự kết luận action sai. |
| TLS handshake failure | Chứng chỉ/truststore/protocol không phù hợp. | Message sender/TLS config, test HTTPS, không chờ SOAP Fault. |
| Timeout | Network, server, downstream hoặc sender config. | Connect/read timeout, retry/idempotency và traces. |

### 15.1. Không thấy SOAPAction trong log client?

Một client logger chỉ ghi SOAP Envelope có thể **không hiển thị HTTP headers**, vì SOAPAction thuộc transport binding. Muốn biết chính xác, cần:

- Logging có kiểm soát tại HTTP sender/gateway hoặc mock server HTTP.
- Wire capture trong môi trường test được phép, có masking token/credentials.
- Interceptor ở HTTP client nếu sender hỗ trợ.
- Test `MockWebServiceServer` cho giá trị action **ở mức SOAP message**.

**Không bật logging toàn bộ SOAP Envelope/Authorization headers trong production** chỉ để xem SOAPAction.

### 15.2. Có cần client gửi action trùng operation name không?

Không. `GetOrder` là WSDL operation name, nhưng literal action có thể là `urn:company:v1/actions/orderLookup` hoặc `http://example.org/soap/GetOrder` hoặc rỗng. Đọc binding, không đoán.

### 15.3. Đối tác ghi “Action mismatch” nhưng client set đúng string?

Kiểm tra lần lượt:

1. Client đang gọi **đúng port/binding/version** chứ không chỉ đúng hostname?
2. Đối tác yêu cầu SOAP 1.1 hay 1.2?
3. Action đang xuất hiện tại **HTTP SOAPAction** hay cần **WS-A Action**?
4. Giá trị có bị double quote, case khác, slash cuối, khoảng trắng không?
5. Proxy/gateway có sửa/drop header không?
6. SOAP Body QName có khớp operation mà action mô tả không?
7. HTTP Content-Type có phù hợp?
8. Server mapping có custom order hoặc interceptor từ chối?
9. Có thông báo Fault detail thực tế nào phân biệt security và routing?

## 16. Kiểm thử callback thuần Java

Unit test đầu tiên chỉ cần bảo đảm `SoapActionCallback` đặt đúng giá trị lên `SoapMessage`.

```java
package com.example.orders.soapclient;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.Test;
import org.springframework.ws.soap.SoapMessage;
import org.springframework.ws.soap.client.core.SoapActionCallback;

class SoapActionCallbackTest {

    @Test
    void setsConfiguredSoapAction() throws Exception {
        SoapMessage message = mock(SoapMessage.class);

        String action = "urn:example:orders:v1/GetOrder";

        new SoapActionCallback(action).doWithMessage(message);

        verify(message).setSoapAction(action);
    }
}
```

Kết luận hợp lệ:

- Callback gọi setter `SoapMessage.setSoapAction(...)` với đúng giá trị logic.
- Test này chạy nhanh, không cần Spring ApplicationContext hoặc HTTP server.

**Test này không chứng minh** một HTTP sender thực sẽ viết `SOAPAction` header chính xác, SOAP 1.2 action parameter ra sao, hay server chấp nhận action đó.

## 17. Kiểm thử client bằng `MockWebServiceServer`

Spring-WS Test có `MockWebServiceServer`, cho phép kiểm thử request mà `WebServiceTemplate` tạo ra và dựng response giả. Công cụ này kiểm tra **client phía gọi**, khác với `MockWebServiceClient` kiểm tra **server `MessageDispatcher`**.

### 17.1. Test xác nhận SOAPAction

Giả sử `OrdersSoapClient`, `WebServiceTemplate` và JAXB classes đã được cấu hình như mục 7:

```java
package com.example.orders.soapclient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.ws.test.client.RequestMatchers.soapAction;
import static org.springframework.ws.test.client.ResponseCreators.withPayload;

import org.junit.jupiter.api.Test;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.test.client.MockWebServiceServer;
import org.springframework.xml.transform.StringSource;
import com.example.orders.contract.GetOrderResponse;

class OrdersSoapClientTest {

    @Test
    void sendsActionFromWsdlBinding() throws Exception {
        Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
        marshaller.setContextPath("com.example.orders.contract");
        marshaller.afterPropertiesSet();

        WebServiceTemplate template = new WebServiceTemplate();
        template.setMarshaller(marshaller);
        template.setUnmarshaller(marshaller);
        template.setDefaultUri(
                "https://partner.example.com/ws/orders");

        MockWebServiceServer server =
                MockWebServiceServer.createServer(template);

        String responseXml = """
            <ord:GetOrderResponse xmlns:ord="urn:example:orders:v1">
                <ord:orderId>ORD-000042</ord:orderId>
                <ord:status>CONFIRMED</ord:status>
            </ord:GetOrderResponse>
            """;

        server.expect(soapAction(
                "urn:example:orders:v1/GetOrder"))
              .andRespond(withPayload(
                      new StringSource(responseXml)));

        OrdersSoapClient client = new OrdersSoapClient(template);

        GetOrderResponse response = client.getOrder("ORD-000042");

        assertEquals("CONFIRMED", response.getStatus());
        server.verify();
    }
}
```

**Điều kiện của code:**

- Có `spring-ws-test`, JUnit Jupiter, JAXB API/runtime, Spring OXM và SOAP message factory phù hợp.
- Import `GetOrderResponse` từ package generated tương ứng.
- `Jaxb2Marshaller` được khởi tạo sau khi set context path; JAXB classes có root element hoặc wrapper phù hợp.
- Server mock trả về payload **hợp lệ** theo cấu hình unmarshaller.
- Class `OrdersSoapClient` như mục 7 xử lý reply trực tiếp kiểu `GetOrderResponse`; nếu generator dùng `JAXBElement`, sửa adapter/test theo output thực tế.

Test này kiểm tra **giá trị action mà SOAP message chứa**, không thay thế integration test HTTP/TLS.

### 17.2. Test payload độc lập

Để kiểm tra **JAXB request QName và nội dung**, có thể viết một test tương tự nhưng dùng:

```java
import static org.springframework.ws.test.client.RequestMatchers.payload;

String requestXml = """
    <ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
        <ord:orderId>ORD-000042</ord:orderId>
    </ord:GetOrderRequest>
    """;

server.expect(payload(new StringSource(requestXml)))
      .andRespond(withPayload(new StringSource(responseXml)));
```

Đây là **đoạn bổ sung cho một test riêng**, với `server`/`responseXml`/marshaller đã được khởi tạo như ví dụ trước. Đặt kỳ vọng cho **cùng một request** theo API test framework thực tế; đừng vô tình đăng ký hai expected requests trong khi client chỉ gửi một message.

### 17.3. Test khi action sai

Có thể tạo test dùng expected SOAPAction `GetOrder` nhưng client cố tình truyền action `CancelOrder` và khẳng định mock server phát hiện mismatch. Hoặc kiểm thử integration với stub server bắt buộc đúng header.

Test phủ định này hữu ích khi refactor action constants hoặc bổ sung operation mới để tránh tái sử dụng nhầm callback.

### 17.4. Test service lỗi SOAP Fault

`MockWebServiceServer` có thể dựng SOAP Fault response theo SOAP version cho client. Hãy kiểm tra client phân biệt **SOAP Fault từ đối tác** với **transport exception** (timeout, TLS error), và nếu WSDL có typed detail thì client adapter trích xuất code đúng hợp đồng.

Không nên catch mọi `Exception` rồi trả một `GetOrderResponse` rỗng. Hành vi mặc định của `WebServiceTemplate` có thể dùng `SoapFaultMessageResolver` và ném `SoapFaultClientException`; cấu hình message resolver tùy biến có thể thay đổi cách này.

## 18. Kiểm tra HTTP SOAPAction trên wire

Một test mock ở cấp `WebServiceMessage` không luôn kiểm tra format **HTTP header thực sự**, proxy hoặc Content-Type. Trong tích hợp enterprise, cần ít nhất một integration test qua HTTP/HTTPS có stub hoặc server kiểm tra request headers.

### 18.1. Request SOAP 1.1 mẫu với curl

Dùng cho môi trường test được phép:

```bash
curl -i 'https://partner-test.example.com/ws/orders' \
  -H 'Content-Type: text/xml; charset=utf-8' \
  -H 'SOAPAction: "urn:example:orders:v1/GetOrder"' \
  --data-binary @get-order-envelope.xml
```

`get-order-envelope.xml` là file SOAP Envelope hợp lệ do người thực hành chuẩn bị trong môi trường test; ví dụ không tạo file này sẵn.

Mục đích của lệnh: kiểm tra thủ công **cú pháp HTTP header và WSDL action**. Nó không chứng minh `WebServiceTemplate` đang gửi cùng headers; muốn kiểm tra client Java, phải chạy Java client qua stub HTTP hoặc server có logging được kiểm soát.

### 18.2. Các điều cần xác minh trên wire

| Thuộc tính | SOAP 1.1 | SOAP 1.2 |
| --- | --- | --- |
| Envelope namespace | `http://schemas.xmlsoap.org/soap/envelope/` | `http://www.w3.org/2003/05/soap-envelope` |
| Media type | `text/xml` | `application/soap+xml` |
| Action biểu diễn | HTTP `SOAPAction` header theo binding. | `action` parameter của media type theo HTTP binding/profile. |
| Binding trong WSDL | `soap:binding`/`soap:operation`. | SOAP 1.2 binding extension/profile. |
| Fault XML | `faultcode`/`faultstring`. | `Code`/`Reason`. |

**Không thể kết luận “SoapActionCallback hỗ trợ SOAP 1.2” chỉ từ unit test `setSoapAction`.** Phải kiểm tra combination message factory, sender và wire với endpoint SOAP 1.2 thật.

### 18.3. Đối tác dùng HTTPS/mTLS

Nếu TLS/mTLS thất bại, có thể chưa hề có HTTP request chứa SOAPAction đến server. Hãy phân biệt:

```text
TLS handshake error
  != HTTP 415 / 401 / 403
  != SOAP Fault với action mismatch
  != lỗi JAXB marshalling
```

Thực hiện kiểm tra chứng chỉ/truststore/keystore và transport trước khi sửa chuỗi SOAPAction.

## 19. SOAPAction, WS-Security và các ranh giới tin cậy

Một client gửi đúng action vẫn có thể bị từ chối vì security, và ngược lại một client có WS-Security Header hợp lệ vẫn có thể không đủ quyền gọi operation.

### 19.1. SOAPAction không phải bằng chứng authentication

Client có thể gửi:

```http
SOAPAction: "urn:example:orders:v1/CancelOrder"
```

nhưng điều này **không chứng minh** client có quyền hủy đơn hàng. Server phải xác thực caller và kiểm tra `order:cancel` trên đúng order/tenant.

### 19.2. WS-Security và mTLS là tầng khác

- **TLS/mTLS** bảo vệ kênh và có thể xác thực peer ở hop TLS.
- **WS-Security** có thể kiểm tra token, timestamp, chữ ký, encryption, certificate trust ở cấp SOAP message.
- **Authorization** kiểm tra principal đã xác thực có quyền operation, tenant và resource cụ thể.
- **SOAPAction** là thông tin **routing/binding**, không thay ba bước trên.

### 19.3. Khi action được sử dụng để quyết định bảo mật

Nếu gateway hoặc SOAP node dùng action để chọn security policy, cần kiểm tra tính nhất quán với payload QName, WS-Addressing Action và nội dung **đã được xác thực/ký** theo profile. Không sử dụng SOAPAction tự khai để chọn một nhánh **bỏ qua** WS-Security hoặc một truststore yếu hơn.

### 19.4. WS-Addressing signed parts

Nếu đối tác yêu cầu ký `wsa:Action`/`wsa:To`, chỉ gắn SOAPAction HTTP **không thể thay** việc tạo SOAP Header và chữ ký. Xác minh signed parts để chống giả mạo và tránh trường hợp chữ ký hợp lệ với một phần XML nhưng endpoint xử lý phần tử khác (XML Signature Wrapping).

### 19.5. Logging an toàn

Khi debug action, nên log:

```text
operation=GetOrder
soapAction=urn:example:orders:v1/GetOrder
soapVersion=SOAP_11
endpointAlias=orders-partner
result=SOAP_FAULT
correlationId=<server-generated>
```

Đừng log nguyên `wsse:Security`, token, private key, chữ ký, raw SOAP Body có dữ liệu nhạy cảm hoặc URL chứa credentials. Giới hạn cardinality nếu đưa action vào metric label; chỉ dùng danh sách action đã chuẩn hóa.

## 20. Timeout, retry và xử lý Fault ở client

`SoapActionCallback` chỉ giải quyết **action**, không cấu hình độ tin cậy của lời gọi.

### 20.1. Timeout

`WebServiceTemplate` ủy nhiệm HTTP transport cho `WebServiceMessageSender`. Connect/read timeout và connection pooling được cấu hình ở **message sender/HTTP client** tương ứng với phiên bản Spring-WS và thư viện được chọn.

**Không** đặt timeout bằng cách thay action hoặc chờ callback khác tự xử lý.

### 20.2. Retry theo ngữ nghĩa nghiệp vụ

Lời gọi `GetOrder` đọc dữ liệu thường dễ cân nhắc retry hơn `CancelOrder` ghi trạng thái. Nếu SOAP client không nhận response do mất mạng, phía đối tác **có thể đã thực hiện thao tác thành công**.

Đối với thao tác ghi:

- Định nghĩa idempotency key/request ID theo hợp đồng.
- Liên kết key với authenticated caller và phạm vi nghiệp vụ.
- Giới hạn retry và backoff, theo dõi trạng thái đã xử lý.
- Không giả định `SOAPAction=CancelOrder` chứng minh thao tác chưa thực hiện.
- Khi có Fault hoặc timeout, có thể cần truy vấn lại trạng thái trước khi retry.

### 20.3. Phân biệt SOAP Fault với transport error

| Sự kiện | Ví dụ | Cách ứng dụng nên phản ứng |
| --- | --- | --- |
| SOAP Fault nghiệp vụ | `ORDER_NOT_FOUND` trong `detail` | Giải mã typed detail, phản hồi cho use case. |
| SOAP Fault phía server | `Server`/`Receiver` | Xem retry policy; không tự động retry thao tác ghi. |
| HTTP/gateway error không có SOAP Envelope | 502/503 hoặc body HTML | Xử lý transport/proxy riêng, ghi trace. |
| TLS exception | Certificate/handshake không hợp lệ | Sửa trust/security config, không đổi action. |
| JAXB marshal/unmarshal error | Schema khác generated model | Kiểm tra XSD/WSDL/namespace. |
| Action mismatch | Sai literal hoặc SOAP version/profile | Kiểm tra WSDL binding, HTTP wire, WS-A Action. |

Nên thiết kế adapter client chuyển những exception hạ tầng thành **kiểu lỗi application phù hợp**, nhưng giữ nguyên thông tin chẩn đoán an toàn ở nội bộ. Không đưa SOAP Fault raw chứa dữ liệu nhạy cảm trực tiếp ra API khác của ứng dụng.

## 21. Các anti-pattern cần tránh

### 21.1. Tự sinh action từ tên class JAXB

`GetOrderRequest.class.getSimpleName()` không tương đương `soapAction`. WSDL có thể dùng một URI hoàn toàn khác. Hãy dùng action của đúng binding.

### 21.2. Đặt URL service vào action

`new SoapActionCallback("https://partner.example.com/ws/orders")` là sai nếu WSDL yêu cầu `urn:example:orders:v1/GetOrder`. Một URL không nhất thiết đại diện cho operation.

### 21.3. Tự thêm dấu nháy kép vào chuỗi Java

`new SoapActionCallback("\"urn:example:orders:v1/GetOrder\"")` có thể tạo double quoting trên wire. Truyền **giá trị logic** không chứa dấu nháy bao ngoài.

### 21.4. Dùng SOAPAction để thay WS-Addressing

Một HTTP `SOAPAction` header không tự tạo `wsa:Action`. Nếu hợp đồng đòi WS-Addressing, dùng API/header handling tương ứng và test.

### 21.5. Đặt action vào một field singleton thay đổi cho từng request

Dễ race condition giữa các thread. Tạo `SoapActionCallback` cục bộ theo operation/request.

### 21.6. Catch mọi SOAP Fault rồi trả response rỗng

Làm mất thông tin lỗi, dễ khiến application hiểu nhầm đã thành công. Hãy giải mã Fault theo contract hoặc trả lỗi application có kiểu rõ ràng.

### 21.7. Bỏ qua SOAP 1.2 message factory/binding

Chỉ thay SOAPAction string không làm đổi SOAP version. Kiểm tra Envelope/Content-Type/action representation trên wire.

### 21.8. Tin rằng MockWebServiceServer kiểm tra TLS thực

Nó xác minh client message và expectations trong mock transport. Cần integration test riêng cho TLS/mTLS, proxy, HTTP Content-Type và headers.

### 21.9. Dùng action để cấp quyền

SOAPAction không phải credential, có thể bị giả mạo. Phải có authentication, WS-Security/mTLS và authorization trên operation, tenant, resource.

### 21.10. Chỉ kiểm tra action mà không kiểm tra payload QName

Một client gửi action `GetOrder` với Body `CancelOrderRequest` có thể tạo tình huống mâu thuẫn, bị từ chối hoặc bị định tuyến nhầm tùy server mapping. Cần test **cặp action + payload**.

## 22. Checklist tích hợp SOAP client contract-first

- [ ] Đã xác định đúng WSDL `service/port/binding` cho môi trường/phiên bản đang gọi.
- [ ] Đã đọc literal `soapAction` từ **binding operation**, không suy từ operation name hoặc URL.
- [ ] Đã đối chiếu input `wsdl:message/wsdl:part` với global XSD element và JAXB class.
- [ ] Client dùng đúng SOAP 1.1/1.2 message factory và HTTP binding.
- [ ] `SoapActionCallback` được truyền vào từng `marshalSendAndReceive(...)` cần action.
- [ ] Giá trị callback là URI/chuỗi action **logic**, không tự bọc thêm dấu nháy kép.
- [ ] Với action rỗng, đã kiểm tra behavior của sender và yêu cầu đối tác trên wire.
- [ ] Với nhiều operation, action được gắn với đúng request/response type, không có shared mutable state.
- [ ] Nếu dùng WS-Addressing, đã cấu hình và test `wsa:Action`/`wsa:To` riêng.
- [ ] Phía server/gateway có quy tắc xử lý action và payload QName mâu thuẫn.
- [ ] Action không được dùng làm bằng chứng authentication hoặc authorization.
- [ ] Đã cấu hình connect/read timeout, HTTPS/mTLS/truststore phù hợp với environment.
- [ ] WS-Security outbound/inbound được cấu hình theo policy (nếu có).
- [ ] JAXB runtime, schema version, response mapping và Fault detail khớp WSDL/XSD.
- [ ] Unit test `SoapActionCallback` xác nhận `SoapMessage.setSoapAction(...)`.
- [ ] `MockWebServiceServer` test SOAP action và payload trên client.
- [ ] Integration test HTTP/HTTPS kiểm tra header/Content-Type/action trên wire.
- [ ] Test các case negative: thiếu/sai action, action với payload không nhất quán, SOAP 1.2 mismatch, security failure.
- [ ] Có kế hoạch xử lý SOAP Fault/transport exception, retry và idempotency của thao tác ghi.
- [ ] Logging chỉ giữ metadata an toàn, có correlation ID và không làm lộ token/PII.
- [ ] Khi WSDL version thay đổi, cập nhật constants và chạy conformance tests với đối tác.

## 23. Bài tập thực hành có đáp án

### Bài 1. Đọc đúng SOAPAction trong WSDL

WSDL có operation `GetOrder`, SOAP binding khai báo `soapAction="urn:partner:orders/lookup"`. Client nên dùng giá trị nào?

**Đáp án:** `new SoapActionCallback("urn:partner:orders/lookup")`. Không dùng `GetOrder` hoặc tự sinh `urn:.../GetOrder` nếu binding không quy định.

### Bài 2. Phân biệt URI và action

Một service công bố URL `https://partner.example.com/ws/orders` và action `urn:partner:GetOrder`. Tham số nào là URI trong `marshalSendAndReceive(uri, request, callback)`?

**Đáp án:** `uri` là URL service `https://partner.example.com/ws/orders`, còn callback mang `urn:partner:GetOrder`. Không hoán đổi hai giá trị.

### Bài 3. Dấu ngoặc kép

HTTP header kỳ vọng là `SOAPAction: "urn:partner:GetOrder"`. Khi tạo callback, có nên truyền thêm `"` vào chuỗi action không?

**Đáp án:** Không. Truyền `new SoapActionCallback("urn:partner:GetOrder")`; message factory/sender đảm nhận biểu diễn trên wire. Kiểm tra HTTP thực nếu đối tác nhạy với quoting.

### Bài 4. Nhiều operation

`GetOrder` và `CancelOrder` cùng dùng một URL, nhưng hai action khác nhau. Có cần tạo hai `WebServiceTemplate` chỉ để có hai action không?

**Đáp án:** Không bắt buộc. Có thể dùng cùng template cấu hình đúng marshaller/sender và tạo callback riêng theo từng operation; tránh mutable global action. Có thể tách client/template theo ranh giới vận hành nếu security/timeouts khác nhau.

### Bài 5. Payload root không trùng SOAPAction

Client gửi Body `GetOrderRequest` nhưng callback `CancelOrder`. Có chắc server gọi `GetOrder` không?

**Đáp án:** Không. Server có thể mapping theo QName hoặc SOAPAction tùy cấu hình/thứ tự; gateway cũng có thể từ chối. Cần giữ action + payload nhất quán và test tình huống mâu thuẫn.

### Bài 6. SOAP 1.2

Client dùng SOAP 1.1 Envelope và `text/xml` nhưng đổi callback sang action của SOAP 1.2 binding. Đã chuyển sang SOAP 1.2 chưa?

**Đáp án:** Chưa. Phải đổi SOAP message factory/Envelope namespace/Content-Type/binding và kiểm thử với server. Action string không đổi phiên bản SOAP.

### Bài 7. SOAPAction và WS-Addressing

Đối tác yêu cầu `wsa:Action` trong SOAP Header. Client chỉ dùng `SoapActionCallback`. Đã đủ chưa?

**Đáp án:** Chưa. Cần WS-Addressing Header bằng `ActionCallback`/cơ chế thích hợp, kiểm tra namespace, signed parts, và nhất quán với SOAPAction nếu profile yêu cầu.

### Bài 8. Authentication

Client có thể đặt `SOAPAction: "AdminDeleteOrder"`. Điều này chứng minh caller có quyền admin không?

**Đáp án:** Không. SOAPAction là metadata routing do client gửi. Server phải xác thực principal và phân quyền operation/order/tenant độc lập.

### Bài 9. MockWebServiceServer

Unit test `SoapActionCallback` pass nhưng đối tác vẫn bảo thiếu HTTP header. Nên test gì tiếp?

**Đáp án:** Integration test qua sender HTTP/HTTPS thật hoặc stub server nhận request để kiểm tra `SOAPAction` wire header, Content-Type và proxy; `MockWebServiceServer` chỉ xác minh SOAP message ở mức mock.

### Bài 10. Action rỗng

WSDL có `soapAction=""`. Developer tự gán `soapAction="GetOrder"` để dễ đọc. Có phù hợp không?

**Đáp án:** Không. Phải tuân thủ binding và kiểm tra sự khác nhau giữa giá trị rỗng, header rỗng/vắng trên wire theo sender và đối tác. Không tự thay contract.

### Bài 11. Fault và timeout

Lời gọi `CancelOrder` mất kết nối sau khi server xử lý nhưng trước khi client nhận response. Có nên retry vô hạn chỉ vì không nhận SOAP Fault?

**Đáp án:** Không. Trạng thái có thể đã thay đổi. Cần idempotency key, truy vấn trạng thái, timeout/retry policy và cơ chế xử lý kết quả không chắc chắn.

### Bài 12. Đọc WSDL nhiều binding

WSDL có cả SOAP 1.1 và SOAP 1.2 binding với các action/endpoint khác nhau. Nên chọn action thế nào?

**Đáp án:** Chọn đúng `service/port` → `binding` → `operation`, đọc action từ binding đó, đồng bộ SOAP version/message factory/sender với endpoint, rồi test wire.

### Bài 13. Thay đổi XSD nhưng action không đổi

Đối tác thay namespace payload từ `v1` sang `v2` nhưng giữ nguyên action. Có cần sửa client?

**Đáp án:** Có thể cần tái sinh JAXB, cập nhật QName/mapper, WSDL và contract tests dù action string không đổi. SOAPAction đúng không bảo đảm Body đúng.

### Bài 14. Chọn vị trí cấu hình

Một ứng dụng có mười operation khác action nhưng cùng endpoint URL. Nên đặt action ở bean `WebServiceTemplate` hay từng method?

**Đáp án:** `WebServiceTemplate` thường giữ cấu hình chung như endpoint URI, marshaller và sender. Action cụ thể nên được chọn **theo operation/request** qua `SoapActionCallback`, tập trung literals trong contract constants hoặc mapping an toàn.

## 24. Tài liệu tham khảo chính thức

Những API dưới đây nên được đối chiếu với phiên bản Spring-WS và Spring Boot đang sử dụng. Ví dụ Java trong bài theo hệ sinh thái Jakarta/JAXB và Java 17+ thường dùng với Spring-WS 4.x; cấu hình chi tiết có thể thay đổi ở các nhánh lớn khác.

1. [Spring Web Services Reference Documentation](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/) — phần client-side WebServiceTemplate, SOAP Action, message callbacks, client interceptors và testing.
2. [SoapActionCallback API](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/soap/client/core/SoapActionCallback.html) — constructor với SOAP action và `doWithMessage`.
3. [WebServiceTemplate API](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/client/core/WebServiceTemplate.html) — `marshalSendAndReceive` overloads, `defaultUri` và exception handling.
4. [WebServiceMessageCallback API](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/client/core/WebServiceMessageCallback.html) — callback thay đổi request message trước khi gửi.
5. [SoapMessage API](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/soap/SoapMessage.html) — `setSoapAction`, SOAP Header và SOAP version.
6. [MockWebServiceServer API](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/test/client/MockWebServiceServer.html) — client-side mock request/response.
7. [RequestMatchers API](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/test/client/RequestMatchers.html) — `soapAction` và `payload` matchers.
8. [ClientInterceptor API](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/client/support/interceptor/ClientInterceptor.html) — xử lý cắt ngang phía client.
9. [WS-Addressing ActionCallback API](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/soap/addressing/client/ActionCallback.html) — SOAP Header `wsa:Action` và endpoint reference.
10. [W3C WSDL 1.1](https://www.w3.org/TR/wsdl11/) — SOAP binding extension, `soap:operation/@soapAction`, message/portType/binding/service.
11. [W3C SOAP 1.1](https://www.w3.org/TR/2000/NOTE-SOAP-20000508/) — HTTP binding và ngữ nghĩa SOAPAction.
12. [SOAP 1.2 Part 2 — Adjuncts](https://www.w3.org/TR/soap12-part2/) và [RFC 3902: application/soap+xml](https://www.rfc-editor.org/rfc/rfc3902) — media type và `action` parameter.
13. [Spring Security Reference](https://docs.spring.io/spring-security/reference/) — khác biệt authentication/authorization với action routing.

**Giới hạn ví dụ:** Các kiểu JAXB được giả định đã sinh từ XSD minh họa; các code block không hợp thành project độc lập có thể chạy ngay nếu chưa tạo generated classes, thêm dependency, message sender và servlet/gateway của đối tác. Các test kiểm tra callback/message là bước đầu; để bảo đảm interoperability doanh nghiệp cần xác minh HTTP/TLS/WS-Security thực và WSDL đúng môi trường.

## Tổng kết

**`SoapActionCallback` là cách thuận tiện trong Spring-WS client để gắn action của một lời gọi SOAP trước khi `WebServiceTemplate` gửi request.** Giá trị action phải lấy từ **SOAP binding của đúng WSDL service/port/operation**, không đoán từ Java method, tên class JAXB, payload QName hoặc endpoint URL.

Hãy luôn phân biệt **SOAPAction** với **WS-Addressing `wsa:Action`**, phân biệt **SOAP 1.1 HTTP header** với **SOAP 1.2 action parameter**, và nhớ rằng action không phải bằng chứng xác thực/phân quyền. Một client contract-first ổn định cần **JAXB đúng XSD, action đúng WSDL, sender/TLS/WS-Security đúng policy, test SOAP message và HTTP wire thật**, cùng xử lý SOAP Fault, timeout và idempotency phù hợp trước khi tích hợp production.

