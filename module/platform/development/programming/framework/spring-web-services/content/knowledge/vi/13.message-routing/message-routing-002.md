# @PayloadRoot, namespace và localPart của phần tử gốc

> **Chương:** Định tuyến thông điệp  
> **Module:** SPRING_WEB_SERVICES — thiết kế và phát triển dịch vụ SOAP theo hướng contract-first bằng Spring Web Services (Spring-WS), XSD/WSDL, JAXB, endpoint, SOAP client và kiểm thử tương thích trong tích hợp doanh nghiệp.

## 1. Vấn đề cần giải quyết: SOAP request đi đến endpoint nào?

Một ứng dụng Spring-WS có thể nhận hàng chục SOAP operation qua cùng một URL, chẳng hạn `POST /ws`. URL HTTP chỉ đưa request tới **SOAP servlet**; Spring-WS vẫn phải quyết định **method Java nào** sẽ xử lý payload.

`@PayloadRoot` là một annotation dành cho method của lớp `@Endpoint`. Nó khai báo cặp:

- **`namespace`** — URI định danh không gian tên XML của **phần tử gốc trong SOAP Body**.
- **`localPart`** — tên cục bộ của chính phần tử đó, không kèm prefix.

Spring-WS thường dùng `PayloadRootAnnotationMethodEndpointMapping` để liên hệ cặp giá trị trên với method phù hợp. Tên method Java, tên class, prefix XML và HTTP URL **không tự thay thế** hai giá trị này.

Đến cuối bài, bạn sẽ có thể:

1. Xác định đúng phần tử payload root của một SOAP Envelope và viết QName chuẩn.
2. Phân biệt namespace URI với XML prefix, localPart với tên qualified element.
3. Thiết kế XSD/WSDL contract-first sao cho request root có QName rõ ràng, ổn định.
4. Viết hai endpoint định tuyến bằng `@PayloadRoot` và gửi SOAP request thực.
5. Chẩn đoán lỗi sai namespace, sai chữ hoa/thường, thiếu `@Endpoint`, xung đột mapping và cấu hình SOAPAction.
6. Lập test để bảo vệ behavior khi đổi schema, JAXB, interceptor và WS-Security.

## 2. SOAP Envelope, Body và payload root là ba tầng khác nhau

Một SOAP 1.1 request minh họa:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1">
  <soapenv:Header/>
  <soapenv:Body>
    <ord:GetOrderRequest>
      <ord:orderId>ORD-1001</ord:orderId>
    </ord:GetOrderRequest>
  </soapenv:Body>
</soapenv:Envelope>
~~~

Ở đây:

- `soapenv:Envelope` là phần tử SOAP bao ngoài; không phải payload root được `@PayloadRoot` nhắm tới.
- `soapenv:Body` là vùng dữ liệu SOAP; cũng **không** phải payload root của operation.
- `ord:GetOrderRequest` là phần tử payload root — phần tử XML đầu của nội dung request nằm trong Body.
- `ord:orderId` là **phần tử con** của request root; `@PayloadRoot` không so tên phần tử con để tìm endpoint.

Mô hình:

~~~mermaid
flowchart TD
    A["SOAP Envelope"] --> H["SOAP Header (tùy chọn)"]
    A --> B["SOAP Body"]
    B --> R["Payload root: ord:GetOrderRequest"]
    R --> C["ord:orderId"]
    R --> Q["QName = {urn:example:orders:v1}GetOrderRequest"]
    Q --> M["PayloadRootAnnotationMethodEndpointMapping"]
    M --> E["&#64;Endpoint method"]
~~~

Với request trên, annotation cần có nội dung:

~~~java
@PayloadRoot(
    namespace = "urn:example:orders:v1",
    localPart = "GetOrderRequest")
~~~

**Không** khai báo `localPart="ord:GetOrderRequest"`; `ord` là prefix của XML instance, không phải một phần của local name. Cũng không khai báo `namespace="ord"` — namespace phải là **URI** được prefix trỏ tới.

> **Quy tắc đọc SOAP:** tìm phần tử đầu tiên bên trong `SOAP Body`, xác định **namespace URI thực** và **local name** của phần tử đó, rồi đối chiếu với `@PayloadRoot`. Không nhìn riêng tên thẻ để đoán endpoint.

## 3. QName: danh tính thực của phần tử XML

**QName (qualified name)** là cặp gồm **namespace URI** và **local name**. Một cách ký hiệu tiện đọc là:

~~~text
{urn:example:orders:v1}GetOrderRequest
└──── namespace URI ────┘└localPart─┘
~~~

Ví dụ:

| Cách viết XML | QName thực | Khớp `@PayloadRoot` trên? |
|---|---|---|
| `<ord:GetOrderRequest xmlns:ord="urn:example:orders:v1"/>` | `{urn:example:orders:v1}GetOrderRequest` | Có |
| `<x:GetOrderRequest xmlns:x="urn:example:orders:v1"/>` | `{urn:example:orders:v1}GetOrderRequest` | Có |
| `<GetOrderRequest xmlns="urn:example:orders:v1"/>` | `{urn:example:orders:v1}GetOrderRequest` | Có |
| `<GetOrderRequest/>` | `{}GetOrderRequest` (không namespace) | Không |
| `<ord:GetOrderRequest xmlns:ord="urn:example:orders:v2"/>` | `{urn:example:orders:v2}GetOrderRequest` | Không |
| `<ord:getOrderRequest xmlns:ord="urn:example:orders:v1"/>` | `{urn:example:orders:v1}getOrderRequest` | Không |
| `<ord:GetOrderResponse xmlns:ord="urn:example:orders:v1"/>` | `{urn:example:orders:v1}GetOrderResponse` | Không |

Những kết luận:

- **Prefix có thể đổi**, miễn trỏ đến cùng namespace URI.
- **Default namespace** có thể khiến thẻ không prefix vẫn thuộc namespace của contract.
- **Không có namespace** khác với namespace có URI `urn:example:orders:v1`.
- **Local name phân biệt chữ hoa/thường**. `GetOrderRequest` khác `getOrderRequest`.
- **Namespace URI được so như định danh**, không phải tên miền để Spring-WS tải qua HTTP. `urn:...` và `https://...` đều có thể được dùng làm URI namespace, nhưng bản thân giá trị không tự công bố dịch vụ.
- Đổi URI từ `v1` sang `v2` là **đổi QName**, dù phần XML bên trong giữ nguyên.

### 3.1. Default namespace và phạm vi áp dụng

Ví dụ request dưới đây vẫn khớp cùng annotation:

~~~xml
<GetOrderRequest xmlns="urn:example:orders:v1">
  <orderId>ORD-1001</orderId>
</GetOrderRequest>
~~~

Default namespace ở root áp dụng cho phần tử con không prefix trong phạm vi này. Ngược lại, nếu chỉ khai báo default namespace ở một phần tử **con**, nó không thay đổi namespace của root cha đã được phân tích.

~~~xml
<GetOrderRequest>
  <orderId xmlns="urn:example:orders:v1">ORD-1001</orderId>
</GetOrderRequest>
~~~

Ở ví dụ thứ hai, `GetOrderRequest` **không có namespace**, còn `orderId` có namespace; endpoint `@PayloadRoot(namespace="urn:example:orders:v1", ...)` sẽ không match. Đây là lỗi khó phát hiện nếu chỉ tìm chuỗi `xmlns` mà không xác định phạm vi khai báo.

### 3.2. Attribute không quyết định payload root

`@PayloadRoot` không sử dụng `orderId`, attribute `requestId`, SOAP Header hay dữ liệu văn bản để chọn handler. Chẳng hạn:

~~~xml
<ord:GetOrderRequest
    xmlns:ord="urn:example:orders:v1"
    requestId="REQ-123">
  <ord:orderId>ORD-1001</ord:orderId>
</ord:GetOrderRequest>
~~~

Root QName vẫn không đổi. Những trường thông tin khác có thể cần XSD validation hoặc xử lý nghiệp vụ, nhưng **không phải tiêu chí mapping của annotation** này.

## 4. XSD contract-first quyết định QName của SOAP Body

Spring-WS được dùng phổ biến theo hướng **contract-first**: thiết kế XSD/WSDL trước khi đặt tên Java method hoặc tạo JAXB DTO. Xét XSD tối thiểu:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:tns="urn:example:orders:v1"
    targetNamespace="urn:example:orders:v1"
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
        <xs:element name="status" type="xs:string"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

  <xs:element name="CancelOrderRequest">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="orderId" type="xs:string"/>
        <xs:element name="reason" type="xs:string"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

  <xs:element name="CancelOrderResponse">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="accepted" type="xs:boolean"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

</xs:schema>
~~~

Có hai cặp global elements đầu vào/đầu ra. Từ schema này, chúng ta đã biết các QName request:

~~~text
{urn:example:orders:v1}GetOrderRequest
{urn:example:orders:v1}CancelOrderRequest
~~~

Ở `elementFormDefault="qualified"`, các phần tử **con** như `orderId`, `reason` cũng thuộc namespace trên. Tuy nhiên, **`@PayloadRoot` chỉ khớp root element**, không kiểm tra cấu trúc con. Nếu SOAP Body có root đúng nhưng `orderId` bị thiếu, mapping vẫn có thể tìm thấy endpoint; việc phát hiện dữ liệu sai phụ thuộc XML parsing/unmarshalling, schema validation và logic ứng dụng.

### 4.1. Global element khác với named type

Nếu XSD khai báo:

~~~xml
<xs:complexType name="GetOrderRequestType">
  <xs:sequence>
    <xs:element name="orderId" type="xs:string"/>
  </xs:sequence>
</xs:complexType>

<xs:element name="GetOrderRequest" type="tns:GetOrderRequestType"/>
~~~

thì SOAP root vẫn là **`GetOrderRequest`**, không phải `GetOrderRequestType`. Tên **global element** được SOAP Body sử dụng; tên type chỉ quy định cấu trúc dữ liệu. Trong hệ JAXB, class Java có thể lấy tên từ type, nhưng `@PayloadRoot` vẫn phải dùng local name của element trên wire.

### 4.2. WSDL message part trỏ đến element nào?

Với WSDL 1.1 document/literal, input message có thể như sau:

~~~xml
<wsdl:message name="GetOrderInput">
  <wsdl:part name="parameters"
             element="tns:GetOrderRequest"/>
</wsdl:message>

<wsdl:message name="GetOrderOutput">
  <wsdl:part name="parameters"
             element="tns:GetOrderResponse"/>
</wsdl:message>
~~~

Đây là một **mảnh WSDL**, chưa phải WSDL hoàn chỉnh. Trong một hợp đồng đầy đủ còn có `wsdl:types`, `portType`, `binding`, `service` và namespace declarations. Khi đọc một WSDL có sẵn, hãy theo `wsdl:part/@element` để tìm QName payload root; **`part name="parameters"` không tạo ra thẻ `<parameters>` trong SOAP Body**.

Đặc biệt, `wsdl:operation name="GetOrder"` không khiến Spring-WS tự so tên operation với method Java. Mapping payload root là quan hệ giữa **request XML** và `@PayloadRoot` — hoàn toàn có thể đặt method Java tên `handleLookup` nếu annotation đúng.

## 5. Endpoint Spring-WS: định tuyến hai request khác nhau

### 5.1. Tên class và method chỉ là tổ chức code Java

Một endpoint dùng DOM để minh họa routing và XML response, tránh phụ thuộc vào lớp JAXB chưa được sinh từ schema:

~~~java
package com.example.orders.endpoint;

import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.parsers.ParserConfigurationException;
import javax.xml.transform.Source;
import javax.xml.transform.dom.DOMSource;

import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.NodeList;

@Endpoint
public class OrderEndpoint {
    private static final String NS = "urn:example:orders:v1";

    @PayloadRoot(namespace = NS, localPart = "GetOrderRequest")
    @ResponsePayload
    public Source handleLookup(@RequestPayload Element request)
            throws ParserConfigurationException {
        String orderId = readSingleElement(request, "orderId");

        Document document = newDocument();
        Element root =
                document.createElementNS(NS, "ord:GetOrderResponse");
        root.setAttributeNS("http://www.w3.org/2000/xmlns/",
                "xmlns:ord", NS);
        document.appendChild(root);

        Element status = document.createElementNS(NS, "ord:status");
        status.setTextContent(
                "ORD-1001".equals(orderId) ? "PROCESSING" : "NOT_FOUND");
        root.appendChild(status);

        return new DOMSource(root);
    }

    @PayloadRoot(namespace = NS, localPart = "CancelOrderRequest")
    @ResponsePayload
    public Source handleCancellation(@RequestPayload Element request)
            throws ParserConfigurationException {
        readSingleElement(request, "orderId");
        readSingleElement(request, "reason");

        Document document = newDocument();
        Element root =
                document.createElementNS(NS, "ord:CancelOrderResponse");
        root.setAttributeNS("http://www.w3.org/2000/xmlns/",
                "xmlns:ord", NS);
        document.appendChild(root);

        Element accepted =
                document.createElementNS(NS, "ord:accepted");
        accepted.setTextContent("true");
        root.appendChild(accepted);

        return new DOMSource(root);
    }

    private static String readSingleElement(
            Element request, String localName) {
        NodeList matches = request.getElementsByTagNameNS(NS, localName);
        if (matches.getLength() != 1) {
            throw new IllegalArgumentException(
                    "Expected one element: " + localName);
        }
        return matches.item(0).getTextContent().trim();
    }

    private static Document newDocument()
            throws ParserConfigurationException {
        return DocumentBuilderFactory.newInstance()
                .newDocumentBuilder()
                .newDocument();
    }
}
~~~

Điểm rút ra:

- `@Endpoint` khiến lớp được nhận diện như một **Spring-WS endpoint** khi có component scan và hạ tầng annotation-driven.
- `@PayloadRoot` gắn **một request QName** với một method. Hai method có tên `handleLookup` và `handleCancellation` hoàn toàn không cần trùng tên request root.
- `@RequestPayload Element` cung cấp DOM element của payload; `@ResponsePayload Source` trả về XML payload để Spring-WS gói vào SOAP Envelope.
- `readSingleElement` chỉ là helper demo; dùng tìm phần tử con ở bất kỳ độ sâu nào nên không thay thế strict XSD validation. Trong thực tế, nên dùng JAXB/XSD model và validation chuẩn.
- Response có QName riêng `GetOrderResponse` hoặc `CancelOrderResponse`, không phải root request. `@PayloadRoot` **được dùng để chọn endpoint dựa trên request**, không định nghĩa tự động QName response.
- `DocumentBuilderFactory.newDocumentBuilder().newDocument()` ở đây chỉ **tạo DOM mới**, không parse XML từ nguồn chưa tin cậy. Nếu ứng dụng parse XML input thủ công, cần cấu hình an toàn chống XXE.

Các import `javax.xml.parsers` và `javax.xml.transform` thuộc JAXP trong JDK, kể cả ứng dụng Java 17+/Jakarta. Chúng không đồng nghĩa việc ứng dụng dùng JAXB `javax.xml.bind` đời cũ; với Spring Boot 3/Jakarta, thư viện JAXB thường thuộc `jakarta.xml.bind`.

### 5.2. Vì sao không nên đặt annotation lên class thay vì method?

`@PayloadRoot` dùng để ánh xạ **endpoint method**. Một lớp `@Endpoint` có thể chứa nhiều method cho các request QName khác nhau. Nếu quên annotation trên method, hoặc đặt sai namespace/localPart, method không được mapping này chọn cho request mong đợi. `@Endpoint` ở cấp class **không tự cung cấp** localPart hay global element trong WSDL.

Với ứng dụng mẫu, hãy đặt package endpoint dưới package được `@SpringBootApplication` quét, bật `@EnableWs` hoặc dùng cấu hình Spring-WS annotation-driven phù hợp. Nếu Spring bean không được đăng ký vào context mà `MessageDispatcherServlet` sử dụng, annotation trong source cũng không giúp mapping tìm được handler.

## 6. Cấu hình tối thiểu để routing thực sự hoạt động

Annotation đúng chưa đủ nếu Spring context không có hạ tầng `MessageDispatcherServlet`, endpoint mapping và adapter. Với Spring Boot tích hợp Spring-WS, một cấu hình minh họa chủ động đăng ký servlet và công bố WSDL như sau:

~~~java
package com.example.orders.config;

import org.springframework.boot.web.servlet.ServletRegistrationBean;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.transport.http.MessageDispatcherServlet;
import org.springframework.ws.wsdl.wsdl11.DefaultWsdl11Definition;
import org.springframework.xml.xsd.SimpleXsdSchema;
import org.springframework.xml.xsd.XsdSchema;

@Configuration
@EnableWs
public class OrdersWsConfig {

    @Bean
    public ServletRegistrationBean<MessageDispatcherServlet>
            soapServlet(ApplicationContext context) {
        MessageDispatcherServlet servlet = new MessageDispatcherServlet();
        servlet.setApplicationContext(context);
        servlet.setTransformWsdlLocations(true);

        return new ServletRegistrationBean<>(servlet, "/ws/*");
    }

    @Bean
    public XsdSchema ordersSchema() {
        return new SimpleXsdSchema(
                new ClassPathResource("orders.xsd"));
    }

    @Bean(name = "orders")
    public DefaultWsdl11Definition ordersWsdl(XsdSchema ordersSchema) {
        DefaultWsdl11Definition wsdl =
                new DefaultWsdl11Definition();
        wsdl.setPortTypeName("OrdersPort");
        wsdl.setTargetNamespace("urn:example:orders:v1");
        wsdl.setLocationUri("/ws");
        wsdl.setSchema(ordersSchema);
        return wsdl;
    }
}
~~~

Ví dụ giả định `src/main/resources/orders.xsd` chứa schema ở mục 4 và các dependency Spring Boot/Spring-WS/WSDL4J tương thích đã có trong dự án. Không thêm servlet bean thủ công **lần thứ hai** nếu auto-configuration của Spring Boot hiện tại đã đăng ký đúng `MessageDispatcherServlet`. Kiểm tra bean registry và URL thực tế thay vì copy toàn bộ cấu hình vào một ứng dụng đang hoạt động.

Một số tầng độc lập:

| Thành phần | Điểm kiểm tra | Lỗi khi không đúng |
|---|---|---|
| `MessageDispatcherServlet` | HTTP mapping `/ws/*` | POST tới `/ws` bị 404 hoặc không vào Spring-WS |
| `@EnableWs` và endpoint config | Endpoint mappings/adapters được đăng ký | Không nhận diện `@PayloadRoot` |
| `@Endpoint` và component scanning | Có bean `OrderEndpoint` trong context servlet | Request đúng QName vẫn không có handler |
| `orders.xsd` | Global elements trong namespace `v1` | WSDL/XSD không phản ánh XML mà endpoint mong đợi |
| `DefaultWsdl11Definition` | GET `/ws/orders.wsdl` trả contract đúng | Client không lấy/sinh được proxy hoặc contract sai |
| `@PayloadRoot` | QName request khớp một method | Dispatcher không tìm thấy endpoint phù hợp |

`DefaultWsdl11Definition` có thể suy ra operation từ global elements có hậu tố `Request` và `Response`. Với schema minh họa, có thể có operation `GetOrder` và `CancelOrder`. **Cần đọc WSDL thực sự công bố** để xác minh `portType`, message parts, SOAP binding và endpoint address; không suy luận chắc chắn chỉ từ tên file.

### 6.1. Quy trình xử lý request

~~~mermaid
sequenceDiagram
    participant C as SOAP client
    participant S as MessageDispatcherServlet
    participant D as MessageDispatcher
    participant M as PayloadRootAnnotationMethodEndpointMapping
    participant A as EndpointAdapter
    participant E as OrderEndpoint

    C->>S: POST /ws, SOAP Body root GetOrderRequest
    S->>D: SOAP message
    D->>M: Tìm endpoint theo request
    M-->>D: handleLookup
    D->>A: Gọi handler phù hợp
    A->>E: @RequestPayload Element
    E-->>A: @ResponsePayload Source
    A-->>D: XML response
    D-->>S: SOAP response
    S-->>C: HTTP response + SOAP Envelope
~~~

Mô hình trên lược bỏ các interceptor, Fault path, security và transport details. Trong ứng dụng thật, có thể có nhiều `EndpointMapping` và `EndpointAdapter`; hạ tầng lựa chọn dựa trên mappings được đăng ký cùng thứ tự/điều kiện áp dụng. `@PayloadRoot` chỉ mô tả một **cách mapping**, không phải toàn bộ dispatcher.

## 7. Gửi SOAP request và kiểm tra routing bằng HTTP

### 7.1. GetOrderRequest

Lưu `get-order.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:o="urn:example:orders:v1">
  <soapenv:Body>
    <o:GetOrderRequest>
      <o:orderId>ORD-1001</o:orderId>
    </o:GetOrderRequest>
  </soapenv:Body>
</soapenv:Envelope>
~~~

Gửi SOAP 1.1 qua HTTP POST:

~~~bash
curl -i -sS \
  -H "Content-Type: text/xml; charset=utf-8" \
  -H 'SOAPAction: ""' \
  --data-binary @get-order.xml \
  http://localhost:8080/ws
~~~

Đối với PowerShell trên Windows, gọi `curl.exe` và dùng câu lệnh trên một dòng nếu cần. Header `SOAPAction: ""` chỉ minh họa SOAPAction rỗng cho môi trường test, không nhất thiết đúng cho hợp đồng đối tác. Nếu WSDL binding đòi một action cụ thể, client phải tuân thủ action đó.

Response thành công về cấu trúc có thể là:

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:o="urn:example:orders:v1">
  <soapenv:Body>
    <o:GetOrderResponse>
      <o:status>PROCESSING</o:status>
    </o:GetOrderResponse>
  </soapenv:Body>
</soapenv:Envelope>
~~~

Bản thân `@PayloadRoot` chỉ giải thích vì sao `handleLookup` được chọn. Nội dung `PROCESSING` là từ logic demo, không được sinh tự động từ mapping. Prefix `o` hay `soapenv` có thể khác trong response mà vẫn cùng XML semantics.

### 7.2. CancelOrderRequest

Lưu `cancel-order.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:o="urn:example:orders:v1">
  <soapenv:Body>
    <o:CancelOrderRequest>
      <o:orderId>ORD-1001</o:orderId>
      <o:reason>Customer request</o:reason>
    </o:CancelOrderRequest>
  </soapenv:Body>
</soapenv:Envelope>
~~~

Gửi cùng URL:

~~~bash
curl -i -sS \
  -H "Content-Type: text/xml; charset=utf-8" \
  -H 'SOAPAction: ""' \
  --data-binary @cancel-order.xml \
  http://localhost:8080/ws
~~~

Kết quả từ `handleCancellation` có thể chứa:

~~~xml
<o:CancelOrderResponse xmlns:o="urn:example:orders:v1">
  <o:accepted>true</o:accepted>
</o:CancelOrderResponse>
~~~

**Điểm đáng quan sát:** Cả hai request đi tới **cùng URL** nhưng được chọn bởi **hai QName** khác nhau:

| HTTP URL | Payload QName | Java method |
|---|---|---|
| `POST /ws` | `{urn:example:orders:v1}GetOrderRequest` | `handleLookup` |
| `POST /ws` | `{urn:example:orders:v1}CancelOrderRequest` | `handleCancellation` |

Đây chính là ưu điểm của message routing: một transport endpoint phục vụ nhiều SOAP operations mà không phải tạo một URL HTTP riêng cho mỗi method.

### 7.3. Không trộn SOAP 1.1 với SOAP 1.2

Ở các ví dụ trên, SOAP 1.1 dùng Envelope namespace:

~~~text
http://schemas.xmlsoap.org/soap/envelope/
~~~

SOAP 1.2 dùng namespace khác:

~~~text
http://www.w3.org/2003/05/soap-envelope
~~~

SOAP 1.2 thường dùng media type `application/soap+xml`; action được mô tả theo cơ chế phù hợp với profile/binding. Nếu HTTP request bị từ chối do SOAP version hoặc Content-Type, `@PayloadRoot` có thể **chưa từng có cơ hội** xử lý message. Hãy kiểm tra tầng protocol trước khi quy lỗi cho QName.

## 8. @PayloadRoot và JAXB: class Java không phải QName

Trong dự án thực tế, endpoint thường nhận JAXB object thay vì DOM. Với schema `GetOrderRequest`, công cụ sinh mã có thể tạo class như `GetOrderRequest` hoặc `GetOrderRequestType`, đôi khi qua `ObjectFactory` và `JAXBElement`.

Ý tưởng endpoint:

~~~java
@Endpoint
public class OrderJaxbEndpoint {
    private static final String NS = "urn:example:orders:v1";

    @PayloadRoot(namespace = NS, localPart = "GetOrderRequest")
    @ResponsePayload
    public GetOrderResponse lookup(
            @RequestPayload GetOrderRequest request) {
        GetOrderResponse response = new GetOrderResponse();
        response.setStatus("PROCESSING");
        return response;
    }
}
~~~

Đây là **đoạn minh họa**. Để chạy trong dự án cụ thể, cần JAXB classes, adapter và root-element annotations phù hợp với tool/version. Một số XSD sinh `JAXBElement<GetOrderRequestType>` thay cho lớp `GetOrderRequest`; method signature khi đó phải điều chỉnh đúng hỗ trợ của endpoint adapter.

Dù code Java thay đổi:

- `@PayloadRoot(namespace, localPart)` **vẫn so XML payload QName**.
- Thay tên Java method `lookup` thành `getOrder` không đổi wire protocol.
- Đổi tên Java class/DTO không đổi QName **nếu** JAXB binding giữ đúng global element.
- Đổi `@XmlRootElement(name=...)` hoặc root `JAXBElement` có thể làm XML marshal khác XSD dù routing request vẫn đúng.
- Việc JAXB unmarshalling thành công không bảo đảm mọi facet `minOccurs`, `pattern`, `maxInclusive` đã được XSD validator áp dụng.

Nếu dùng `Jaxb2Marshaller`, cấu hình context path/packages/annotated classes phải tương thích với JAXB-generated model. Trong dòng Spring dùng Jakarta, chọn runtime và API `jakarta.xml.bind` đồng bộ; không trộn ngẫu nhiên với `javax.xml.bind` của dòng cũ.

## 9. SOAPAction, WS-Addressing Action và PayloadRoot khác nhau

Spring-WS có các lựa chọn mapping khác ngoài payload root, chẳng hạn `@SoapAction` và mapping theo WS-Addressing Action khi cấu hình hỗ trợ. Những tín hiệu này nói về **khía cạnh khác nhau** của request:

| Tín hiệu | Được tìm ở đâu? | Điểm mạnh / giới hạn |
|---|---|---|
| HTTP URL | HTTP request line + servlet mapping | Chọn servlet/transport; không tự chọn Java method theo QName |
| `@PayloadRoot` | QName của phần tử root trong SOAP Body | Rõ theo contract-first XSD; không phụ thuộc prefix XML |
| SOAPAction | Header SOAP 1.1 HTTP theo binding | Có ích với legacy contract; có thể rỗng/khác nhau giữa đối tác |
| WS-Addressing Action | Header theo WS-Addressing | Phù hợp contract/policy dùng WS-Addressing; phải bật và cấu hình tương ứng |

Ví dụ trong một contract XSD, cả `GetOrderRequest` và `CancelOrderRequest` có thể cùng địa chỉ `/ws` nhưng có các action khác nhau. `@PayloadRoot` vẫn phân biệt request theo XML Body. Nếu đồng thời cấu hình nhiều endpoint mappings, **thứ tự và điều kiện match** có thể ảnh hưởng lựa chọn cuối; đừng tự suy ra một mapping luôn thắng mapping kia.

Một cách thiết kế an toàn:

1. Chọn một **nguồn định tuyến chính** phù hợp contract đang có.
2. Duy trì sự nhất quán giữa WSDL operation, message element và action.
3. Không tạo hai handler cạnh tranh cho cùng QName mà không có mục đích và quy tắc rõ.
4. Kiểm thử trường hợp action đúng nhưng payload root sai, và payload đúng nhưng action sai.
5. Không dùng SOAPAction hoặc payload QName làm thay cho **xác thực/ủy quyền** người gọi.

### 9.1. Khi nào nên chọn payload-root routing?

`@PayloadRoot` đặc biệt phù hợp khi:

- Hợp đồng SOAP là **document/literal** và input message gắn với global XSD element ổn định.
- Một endpoint URL phục vụ nhiều operations có request root riêng.
- Hệ thống có client đa ngôn ngữ: Java, CXF/JAX-WS, .NET, ESB; tất cả có thể trao đổi XML giống nhau.
- Muốn kiểm thử dispatch bằng SOAP Body rõ ràng, không dựa vào tên Java method.
- Operation name và tên Java service có thể thay đổi nội bộ nhưng contract XML giữ ổn định.

Nó kém phù hợp khi **nhiều logical operations được thiết kế cố ý cùng payload root QName** và cần phân biệt bằng một cơ chế action/header khác. Trong trường hợp đó, phải thiết kế message routing và binding phù hợp; không thể đặt hai `@PayloadRoot` trùng nhau rồi kỳ vọng framework tự phân biệt dựa trên dữ liệu con.

## 10. Xung đột QName và vấn đề version hóa contract

Một nguyên tắc thiết kế: **mỗi QName request trong phạm vi một endpoint mapping nên được gắn với một handler rõ ràng**.

Ví dụ không nên làm trong cùng mapping context:

~~~java
@PayloadRoot(namespace = "urn:example:orders:v1",
             localPart = "GetOrderRequest")
public Source lookupA(@RequestPayload Element request) { /* ... */ }

@PayloadRoot(namespace = "urn:example:orders:v1",
             localPart = "GetOrderRequest")
public Source lookupB(@RequestPayload Element request) { /* ... */ }
~~~

Hai method khai báo cùng request QName; mapping không có thông tin đủ để phân biệt. Tùy cách framework phát hiện, hệ thống có thể báo lỗi khi tạo mapping hoặc biểu hiện hành vi không mong muốn. Không dựa vào việc method nào được chọn “tình cờ”.

### 10.1. Khi phát hành v2

Một contract v2 có thể dùng:

~~~text
{urn:example:orders:v1}GetOrderRequest
{urn:example:orders:v2}GetOrderRequest
~~~

Đây là **hai QName khác nhau**. Nếu muốn giữ cả hai:

~~~java
@PayloadRoot(namespace = "urn:example:orders:v1",
             localPart = "GetOrderRequest")
@ResponsePayload
public Source handleV1(@RequestPayload Element request) { /* ... */ }

@PayloadRoot(namespace = "urn:example:orders:v2",
             localPart = "GetOrderRequest")
@ResponsePayload
public Source handleV2(@RequestPayload Element request) { /* ... */ }
~~~

Mỗi method còn phải trả XML response đúng namespace/version và logic tương thích. Đoạn minh họa bỏ thân method. Đừng coi việc thêm method v2 là đủ: cần quản lý **WSDL/XSD v2**, SOAP Fault, JAXB, policy bảo mật và client migration.

Có thể dùng hai URL riêng hoặc một URL; việc đó là quyết định **transport/triển khai**, không làm thay đổi nguyên lý QName matching. Nếu dùng chung servlet/context, các request v1/v2 đều có thể vào cùng dispatcher trừ khi cấu hình tách biệt bổ sung.

### 10.2. Breaking changes thường bị bỏ sót

| Thay đổi | Có thể phá `@PayloadRoot` routing? | Vì sao |
|---|---|---|
| Đổi prefix `ord` thành `x`, URI giữ nguyên | Không | Prefix không thuộc QName |
| Chuyển sang default namespace đúng URI | Không | QName không đổi |
| Đổi `targetNamespace` từ `v1` sang `v2` | Có | Request QName đổi |
| Đổi chữ hoa/thường của root element | Có | `localPart` đổi |
| Đổi XSD type nhưng giữ global element QName | Không nhất thiết với routing; vẫn có thể phá binding/validation | Root QName giữ nguyên, nội dung có thể đổi |
| Thay tên Java endpoint method | Không, nếu annotation giữ nguyên | Routing không dựa vào Java method name |
| Đổi WSDL operation name nhưng giữ request root | Không nhất thiết với payload mapping; có thể phá client generation | Operation contract và SOAPAction có thể đổi |
| Đổi XML child `orderId` thành `orderCode` | Không nhất thiết với routing; có thể phá XSD/JAXB | Root QName không đổi nhưng schema thay đổi |

**Chỉ vì request tìm được endpoint không có nghĩa request hợp lệ với contract.** Routing là một bước; unmarshalling, schema validation, authorization và xử lý nghiệp vụ là các bước khác.

## 11. Chẩn đoán “không tìm thấy endpoint” theo đúng tầng

Khi SOAP request không được xử lý, có nhiều nguyên nhân khác nhau. **Không phải mọi HTTP 404 hoặc SOAP Fault đều do `@PayloadRoot` sai.**

### 11.1. Sơ đồ kiểm tra

~~~mermaid
flowchart TD
    A["Gửi SOAP request"] --> B{"HTTP URL đến servlet?"}
    B -->|Không| C["Kiểm tra mapping /ws/*, context path, port"]
    B -->|Có| D{"SOAP Envelope đọc được?"}
    D -->|Không| E["Kiểm tra SOAP version, XML, Content-Type"]
    D -->|Có| F{"Payload QName có đúng?"}
    F -->|Không| G["So namespace URI và localPart"]
    F -->|Có| H{"@Endpoint có trong context?"}
    H -->|Không| I["Kiểm tra component scan, @EnableWs, bean context"]
    H -->|Có| J{"Mapping/adapter hỗ trợ?"}
    J -->|Không| K["Kiểm tra EndpointMapping, EndpointAdapter"]
    J -->|Có| L["Kiểm tra unmarshalling, XSD, security, business"]
~~~

Cách kiểm tra theo thứ tự:

1. **HTTP URL:** xác minh request POST vào đúng đường dẫn servlet (ví dụ `/ws`), đúng port/context path; `GET /ws/orders.wsdl` là thao tác khác.
2. **SOAP Envelope:** kiểm tra well-formed XML, SOAP 1.1/1.2, media type và SOAPAction.
3. **QName của root:** trích phần tử đầu tiên trong Body; so namespace URI **thực** và local name với annotation.
4. **Bean registration:** xác nhận lớp `@Endpoint` nằm trong component scan và application context của `MessageDispatcherServlet`.
5. **Endpoint mapping:** kiểm tra `PayloadRootAnnotationMethodEndpointMapping` tồn tại; các mappings khác có thể tham gia lựa chọn handler.
6. **Endpoint adapter:** handler đã được tìm nhưng method argument/return type có được hỗ trợ không?
7. **XSD/JAXB/security/business:** nếu đã tìm đúng handler, lỗi có thể nằm ở dữ liệu XML hoặc chính sách khác.

### 11.2. Các lỗi XML khó nhìn bằng mắt

| Biểu hiện | Nguyên nhân | Cách sửa |
|---|---|---|
| `<GetOrderRequest/>` không match | Root không có namespace | Gắn đúng namespace bằng prefix hoặc default xmlns |
| `<ord:GetOrderRequest>` báo prefix chưa khai báo | XML không well-formed | Khai báo `xmlns:ord="urn:example:orders:v1"` |
| Prefix đổi nhưng lại báo routing lỗi | Trong lúc đổi prefix đã đổi nhầm namespace URI | So URI bằng parser namespace-aware |
| `urn:example:orders:v1/` không match `urn:example:orders:v1` | Dấu `/` cuối là thành phần khác của URI | Dùng chính xác URI đã công bố |
| `http://...` không match `https://...` | Namespace URI không giống nhau | Không tự đổi scheme của namespace theo TLS |
| `getOrderRequest` không match `GetOrderRequest` | XML local name phân biệt chữ hoa | Giữ đúng localPart |
| Root đúng, child sai namespace | Routing vẫn có thể match; XSD/JAXB lỗi sau đó | Kiểm tra `elementFormDefault`, child QNames |
| SOAP Header chứa `GetOrderRequest` nhưng Body khác | Header không phải payload root | Đặt request element đúng trong Body |
| Có nhiều element top-level trong Body | Contract mơ hồ/không theo profile mong đợi | Thiết kế message document/literal rõ ràng, validate theo WSDL/XSD |
| Lớp `@Endpoint` nằm ngoài component scan | Annotation không được đăng ký làm bean | Sửa package scanning hoặc cấu hình bean |

Một lời khuyên thực tế: **so URI + local name bằng XML parser namespace-aware**. Grep chuỗi `<GetOrderRequest>` hoặc so toàn bộ XML text dễ sai khi có prefix, default namespace hoặc formatting khác nhau.

### 11.3. Trường hợp đúng root nhưng vẫn lỗi

Giả sử server mong:

~~~xml
<o:GetOrderRequest xmlns:o="urn:example:orders:v1">
  <o:orderId>ORD-1001</o:orderId>
</o:GetOrderRequest>
~~~

Client lại gửi:

~~~xml
<o:GetOrderRequest xmlns:o="urn:example:orders:v1">
  <o:orderCode>ORD-1001</o:orderCode>
</o:GetOrderRequest>
~~~

Cả hai có **cùng QName root**, nên `@PayloadRoot` có thể định tuyến thành công. Nhưng XSD quy định `orderId`, vì vậy:

- Nếu `PayloadValidatingInterceptor` được bật, request phải bị phát hiện sai schema.
- Nếu dùng JAXB binding, có thể xảy ra lỗi unmarshalling hoặc field bị thiếu, tùy JAXB model và cấu hình.
- Nếu endpoint DOM tự đọc field, `readSingleElement("orderId")` ở ví dụ sẽ ném exception.
- Nếu không có kiểm tra phù hợp, dữ liệu sai có thể đi sâu hơn vào business service.

Đây là khác biệt giữa **message routing** và **contract validation**.

## 12. Validation, SOAP Fault và interceptor liên quan đến định tuyến

### 12.1. Validate schema sau khi đã xác định request type

`@PayloadRoot` không thay `PayloadValidatingInterceptor`. Nếu muốn kiểm tra request/response theo XSD, một cấu hình Spring-WS thường dùng `WsConfigurer`:

~~~java
import java.util.List;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.config.annotation.WsConfigurer;
import org.springframework.ws.server.EndpointInterceptor;
import org.springframework.ws.soap.server.endpoint.interceptor.PayloadValidatingInterceptor;
import org.springframework.xml.xsd.XsdSchema;

@Configuration
@EnableWs
public class ValidationWsConfig implements WsConfigurer {

    private final XsdSchema ordersSchema;

    public ValidationWsConfig(XsdSchema ordersSchema) {
        this.ordersSchema = ordersSchema;
    }

    @Override
    public void addInterceptors(
            List<EndpointInterceptor> interceptors) {
        PayloadValidatingInterceptor validation =
                new PayloadValidatingInterceptor();
        validation.setXsdSchema(ordersSchema);
        validation.setValidateRequest(true);
        validation.setValidateResponse(true);
        interceptors.add(validation);
    }
}
~~~

**Đây là một phương án cấu hình thay thế/bổ sung được tổ chức có chủ ý**, không nên dán nguyên một lớp `@EnableWs` thứ hai vào cùng application context nếu đã có cấu hình ở mục 6. Khi triển khai, có thể gộp `WsConfigurer` vào lớp cấu hình hiện hữu, tiêm đúng `XsdSchema`, và bảo đảm request/response của các namespace cần phục vụ đều được validation theo đúng schema. Một validator áp dụng mọi endpoint nhưng chỉ biết schema của một service có thể từ chối hợp đồng hợp lệ khác.

### 12.2. SOAP Fault khi mapping thất bại

Lỗi “không có endpoint phù hợp” xảy ra ở **dispatch/mapping**; lỗi dữ liệu XSD/JAXB xảy ra ở những bước khác. Một cấu hình có thể tạo SOAP Fault hoặc phản hồi lỗi HTTP tùy version, message factory và resolver. Không nên dạy client dựa vào một chuỗi tiếng Anh trong fault reason để tự suy ra lỗi QName.

Một cơ chế fault hợp lý cần trả thông tin được phép công bố, chẳng hạn:

- Sai XML hoặc dữ liệu request: lỗi thuộc phía caller khi đúng SOAP version/profile.
- Lỗi nội bộ: lỗi server, không lộ stack trace, bean name, đường dẫn file hay khóa bảo mật.
- Lỗi nghiệp vụ được khai báo: SOAP Fault detail theo XSD/WSDL contract.
- Lỗi security: lỗi theo policy, tránh tiết lộ quá nhiều chi tiết xác thực.

Spring-WS có các `EndpointExceptionResolver` và resolver ánh xạ exception sang SOAP Fault, nhưng **không phải mọi lỗi parsing, routing, transport hoặc WS-Security đều đi qua cùng một resolver của endpoint**. Kiểm thử trực tiếp lỗi xảy ra tại từng tầng.

### 12.3. Interceptor không phải điều kiện để @PayloadRoot hoạt động

`EndpointInterceptor` có thể dùng cho XSD validation, correlation ID, logging, authorization context hoặc WS-Security tùy thiết kế. Tuy nhiên:

- Endpoint mapping chọn handler theo QName; interceptor thường là bước xử lý bổ sung trong chuỗi dispatch.
- Thứ tự interceptor trên request, response và fault có thể quan trọng.
- Không log SOAP Body/token/file nhạy cảm ở mức debug trên production.
- Nếu thay đổi mapping, phải xác minh security interceptor vẫn áp dụng cho handler mới.
- Một SOAP request sai định dạng ngay ở parser có thể bị từ chối trước khi interceptor endpoint chạy.

**Không coi namespace URI hay localPart là bằng chứng xác thực.** Kẻ gửi request có thể tự tạo XML với QName đúng; chỉ security/authentication và business authorization mới quyết định có cho phép xử lý thao tác hay không.

## 13. Bảo mật XML và WS-Security khi routing theo QName

### 13.1. QName matching không giải quyết XML parser security

Ngay cả khi chỉ cần tìm root element, server vẫn phải đọc SOAP XML từ mạng. Các rủi ro như XXE, DTD/external entities, tài liệu XML lồng sâu, payload quá lớn hoặc attachment giải mã tốn bộ nhớ cần được kiểm soát ở tầng **parser, message factory, HTTP và resource limits**, không phải ở `@PayloadRoot`.

Checklist tối thiểu:

- Cấu hình XML parser và schema resolution theo profile an toàn, hạn chế external entity/DTD không được phép.
- Giới hạn HTTP body size, độ sâu XML, số lượng elements/attributes và thời gian xử lý.
- Kiểm soát multipart/MTOM attachment sizes, tổng byte sau giải mã và vòng đời tài nguyên.
- Không tin MIME type, namespace hay QName do client gửi để quyết định quyền truy cập.
- Bảo vệ log, tracing và Fault detail trước dữ liệu nhạy cảm.

### 13.2. WS-Security cần bảo vệ chính message được route

Trong tích hợp doanh nghiệp, WS-Security có thể yêu cầu chữ ký XML, encryption, Timestamp, token và chứng chỉ. Nếu SOAP Body được ký, thay đổi root QName, namespace hoặc XML canonicalization có thể ảnh hưởng chữ ký; việc client gửi request match `@PayloadRoot` chưa chứng minh chữ ký hợp lệ.

Một số câu hỏi cần xác minh với đối tác:

1. Body/Header nào phải được ký hoặc mã hóa?
2. Algorithm/profile/canonicalization và WS-SecurityPolicy nào được dùng?
3. Keystore, truststore, chuỗi chứng chỉ, rotation và timestamp tolerance ra sao?
4. Tất cả endpoint mappings có áp dụng đúng security interceptor hoặc security policy không?
5. SOAP 1.1/1.2, MTOM/XOP và attachment signing có được hỗ trợ ở cả hai phía không?
6. Client thiếu chữ ký hoặc gửi token hết hạn có bị từ chối **trước khi nghiệp vụ chạy** không?

**TLS và WS-Security khác nhau:** TLS bảo vệ kết nối; WS-Security bảo vệ các phần của thông điệp theo policy và có thể đáp ứng yêu cầu qua trung gian. Không tự suy ra dùng HTTPS nghĩa là đã đáp ứng WS-Security của khách hàng.

### 13.3. Tương thích với CXF/JAX-WS và .NET

Spring-WS endpoint mapping không buộc client dùng Spring. Một JAX-WS/CXF proxy sinh từ WSDL hoặc một .NET SOAP client có thể gửi đúng XML payload QName, và server Spring-WS sẽ định tuyến bình thường nếu:

- Client tuân thủ global element, namespace, SOAP binding/version và các kiểu XSD.
- WSDL operation/binding đúng với tài liệu đã công bố.
- Header action, WS-Addressing/WS-Security và transport phù hợp.
- SOAP Fault được tạo đúng profile client hiểu được.
- Client thực sự gửi XML mong đợi — không chỉ Java method signature có tên đúng.

Với client code-first, annotation và tool code generation có thể tạo root QName khác nếu tên wrapper/namespace được suy diễn không giống WSDL contract-first. Luôn **capture request XML thực** và so QName, thay vì mặc định mọi tool tạo ra cùng thông điệp.

## 14. Kiểm thử route theo QName

Một test tốt phải kiểm tra cả **các case tương đương QName** (đổi prefix nhưng không đổi URI) và **các case không tương đương** (đổi namespace, localPart). Không chỉ test một happy path.

### 14.1. MockWebServiceClient gửi payload XML

Khi endpoint và context ở các mục trước đã được triển khai, sử dụng `spring-ws-test`:

~~~java
import javax.xml.transform.Source;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.xml.transform.StringSource;
import org.springframework.ws.test.server.MockWebServiceClient;

import static org.springframework.ws.test.server.RequestCreators.withPayload;
import static org.springframework.ws.test.server.ResponseMatchers.payload;

@SpringBootTest
class OrderRoutingTest {

    @Autowired
    ApplicationContext context;

    @Test
    void routesGetOrderByNamespaceAndLocalPart() {
        MockWebServiceClient client =
                MockWebServiceClient.createClient(context);

        Source request = new StringSource("""
            <x:GetOrderRequest xmlns:x="urn:example:orders:v1">
              <x:orderId>ORD-1001</x:orderId>
            </x:GetOrderRequest>
            """);

        Source expected = new StringSource("""
            <r:GetOrderResponse xmlns:r="urn:example:orders:v1">
              <r:status>PROCESSING</r:status>
            </r:GetOrderResponse>
            """);

        client.sendRequest(withPayload(request))
              .andExpect(payload(expected));
    }
}
~~~

Ý nghĩa của test:

- Request prefix `x` khác prefix `ord` trong annotation/mẫu, nhưng URI không đổi nên vẫn phải route đến `handleLookup`.
- Expected response dùng prefix `r` khác prefix `x` nhưng XML semantics giữ nguyên.
- Test xác nhận request được xử lý và payload trả về có cấu trúc mong đợi; nó **chưa** chứng minh HTTP servlet, proxy, TLS hay WSDL publication.

Đoạn test yêu cầu dependency `spring-ws-test` (scope test), JUnit, Spring test, endpoint và cấu hình XML như các mục trước. Không chạy trực tiếp nếu dự án chưa có các phần đó.

### 14.2. Bảng case bắt buộc

| Case | SOAP Body root | Kỳ vọng |
|---|---|---|
| GetOrder hợp lệ | `{urn:example:orders:v1}GetOrderRequest` | `handleLookup` |
| Prefix khác nhưng URI đúng | `{urn:example:orders:v1}GetOrderRequest` | Vẫn `handleLookup` |
| Default xmlns đúng | `{urn:example:orders:v1}GetOrderRequest` | Vẫn `handleLookup` |
| CancelOrder hợp lệ | `{urn:example:orders:v1}CancelOrderRequest` | `handleCancellation` |
| Không namespace | `{}GetOrderRequest` | Không match `@PayloadRoot` v1 |
| Namespace v2 chưa hỗ trợ | `{urn:example:orders:v2}GetOrderRequest` | Không match `@PayloadRoot` v1 |
| Sai chữ hoa | `{urn:example:orders:v1}getOrderRequest` | Không match |
| Root đúng, `orderId` thiếu | `{urn:example:orders:v1}GetOrderRequest` | Mapping có thể match; schema/business phải reject |
| HTTP URL sai | Request chưa đến servlet | Không chạy endpoint dù QName đúng |
| SOAP protocol sai | Parsing/message factory từ chối | Không kết luận mapping lỗi |

Đối với các case âm tính, có thể gửi SOAP qua HTTP test và kiểm tra **không có side effect nghiệp vụ**, response fault/status phù hợp. Nếu test môi trường có mapping khác như SOAPAction, cần xác minh không có fallback bất ngờ khiến request sai QName vẫn được route theo action.

### 14.3. Test bằng curl và XML capture

Lệnh gửi SOAP request vào server phát triển:

~~~bash
curl -i -sS \
  -H "Content-Type: text/xml; charset=utf-8" \
  -H 'SOAPAction: ""' \
  --data-binary @get-order.xml \
  http://localhost:8080/ws
~~~

Lưu lại:

- HTTP status và SOAP version.
- Request QName được gửi sau serialization.
- Response payload QName và dữ liệu con.
- SOAP Fault với request sai namespace hoặc malformed XML.
- Correlation ID (nếu có), nhưng không log thông tin nhạy cảm.

Chạy tương tự từ client thực của đối tác (CXF/JAX-WS/.NET) để kiểm tra **interoperability**. `MockWebServiceClient` hữu ích để test Java endpoint, còn HTTP/client test xác nhận môi trường đóng gói và transport.

## 15. Bài tập thực hành kèm đáp án

### Bài 1. Có cần sửa @PayloadRoot khi prefix thay đổi?

Server dùng:

~~~java
@PayloadRoot(
    namespace = "urn:example:orders:v1",
    localPart = "GetOrderRequest")
~~~

Client A gửi:

~~~xml
<a:GetOrderRequest xmlns:a="urn:example:orders:v1"/>
~~~

Client B gửi:

~~~xml
<b:GetOrderRequest xmlns:b="urn:example:orders:v1"/>
~~~

**Câu hỏi:** Hai request có đến cùng method không?

**Đáp án:** Có, khi xét riêng `@PayloadRoot`; cả hai có cùng QName `{urn:example:orders:v1}GetOrderRequest`. Việc XML instance dùng prefix `a` hay `b` không đổi namespace URI của element. Dĩ nhiên nội dung request còn phải hợp lệ theo XSD; các mẫu rỗng ở đây chỉ nhằm minh họa QName.

### Bài 2. Vì sao default namespace đặt ở chỗ khác lại làm routing lỗi?

Hai XML:

~~~xml
<!-- A -->
<GetOrderRequest xmlns="urn:example:orders:v1">
  <orderId>ORD-1001</orderId>
</GetOrderRequest>
~~~

~~~xml
<!-- B -->
<GetOrderRequest>
  <orderId xmlns="urn:example:orders:v1">ORD-1001</orderId>
</GetOrderRequest>
~~~

**Câu hỏi:** Mẫu nào khớp `@PayloadRoot(namespace="urn:example:orders:v1", localPart="GetOrderRequest")`?

**Đáp án:** Chỉ mẫu A. Mẫu B có root `GetOrderRequest` không namespace; namespace của `orderId` không thể thay QName của phần tử cha.

### Bài 3. WSDL operation name có phải localPart?

WSDL khai báo operation `GetOrder`, input message dùng part `element="tns:GetOrderRequest"`. Java method tên `handleLookup`. `localPart` đúng là gì?

**Đáp án:** `GetOrderRequest`, vì SOAP Body chứa global element đó. Tên operation `GetOrder` và Java method `handleLookup` không phải tên payload root.

### Bài 4. Sao cùng URL lại xử lý hai method?

Gửi `GetOrderRequest` và `CancelOrderRequest` tới `POST /ws`. Cả hai thuộc namespace `urn:example:orders:v1`.

**Đáp án:** Mỗi request có QName khác nhau ở local part; `PayloadRootAnnotationMethodEndpointMapping` có thể chọn method tương ứng dựa trên element, dù servlet URL giống nhau.

### Bài 5. Root đúng nhưng payload sai schema

Client gửi `GetOrderRequest` có `orderCode` thay vì `orderId`. Có thể khẳng định mapping thất bại không?

**Đáp án:** Không. Root QName có thể vẫn khớp; lỗi thuộc **schema validation**, JAXB/unmarshalling hoặc business logic. Cần kiểm tra bước request được từ chối và SOAP Fault tương ứng.

### Bài 6. Một v2 đổi namespace

v1 là `urn:example:orders:v1`; v2 là `urn:example:orders:v2`. Client v2 gửi cùng tên root `GetOrderRequest`. Server chỉ có annotation v1. Chuyện gì xảy ra?

**Đáp án:** `@PayloadRoot` v1 không match. Để hỗ trợ v2, cần ánh xạ QName v2 và công bố contract phù hợp; nếu cả hai chạy đồng thời, kiểm thử response, fault, security và JAXB cho từng version.

### Bài 7. SOAPAction không thay thế security

Một đối tác gửi SOAPAction chính xác và root QName đúng nhưng không có chữ ký SOAP bắt buộc. Có nên cho chạy business service?

**Đáp án:** Không. SOAPAction và `@PayloadRoot` dùng cho lựa chọn handler, **không xác minh tính xác thực hay quyền gọi**. Request phải qua authentication/WS-Security và business authorization theo policy.

## 16. Checklist thiết kế và vận hành

### Trước khi viết @PayloadRoot

- [ ] Đọc WSDL input message `wsdl:part/@element` hoặc global element trong XSD.
- [ ] Ghi lại QName đầy đủ `{namespaceURI}localPart` cho từng request.
- [ ] Có `targetNamespace` nhất quán giữa XSD, WSDL và endpoint.
- [ ] Hiểu `elementFormDefault` và namespace của các phần tử con, nhưng không nhầm với root QName.
- [ ] Mỗi request QName có một handler không mơ hồ trong phạm vi mapping.
- [ ] Không dựa vào Java method name, JAXB type name hay SOAPAction thay cho element QName.

### Khi cấu hình Spring-WS

- [ ] `@Endpoint` được component scan thành bean.
- [ ] `@EnableWs`/cấu hình annotation-driven hoạt động trong context của servlet.
- [ ] `MessageDispatcherServlet` nhận POST qua URL mong đợi.
- [ ] `@PayloadRoot(namespace, localPart)` dùng đúng URI và local name, phân biệt chữ hoa/thường.
- [ ] `@RequestPayload` và `@ResponsePayload` có JAXB/DOM/Source adapter phù hợp.
- [ ] WSDL được công bố và chứa đúng input/output elements, SOAP version và `soap:address`.
- [ ] Nếu dùng `@SoapAction` hoặc WS-Addressing, đã kiểm tra mapping order và tình huống giao nhau.

### Khi kiểm thử và phát hành

- [ ] Test đổi prefix/default namespace nhưng giữ QName, phải route như cũ.
- [ ] Test đổi URI hoặc localPart, phải không match mapping không phù hợp.
- [ ] Test root đúng nhưng child sai, XSD/JAXB validation phải phát hiện.
- [ ] Test duplicate mapping hoặc multiple mappings không chọn handler sai.
- [ ] Test SOAP 1.1/1.2 và Content-Type đúng hợp đồng.
- [ ] Test SOAP Fault của các lỗi routing, validation, security và nghiệp vụ.
- [ ] XML parser và giới hạn tài nguyên đã được harden; không ghi log payload nhạy cảm.
- [ ] WS-Security signature/token/certificate được kiểm chứng trên mọi đường dispatch.
- [ ] Có bài test qua HTTP và từ client độc lập sinh theo WSDL.
- [ ] Mỗi thay đổi namespace/version được đánh giá là thay đổi contract và có lộ trình client migration.

**Ghi nhớ:** Trong Spring Web Services, `@PayloadRoot` gắn một **method Java** với **QName của phần tử đầu tiên trong SOAP Body**. QName là cặp `{namespaceURI}localPart`; prefix XML, tên operation WSDL, tên class Java và đường dẫn HTTP không phải giá trị thay thế. Một dịch vụ SOAP contract-first ổn định bắt đầu bằng XSD/WSDL rõ ràng, routing không mơ hồ và kiểm thử đầy đủ cả validation, Fault, bảo mật và tính tương thích client.
