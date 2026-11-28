# WebServiceMessageCallback và tùy chỉnh thông điệp trước khi gửi

> **Chương:** Máy khách Spring-WS  
> **Ngữ cảnh:** SPRING_WEB_SERVICES — phát triển dịch vụ SOAP theo hướng **contract-first** với Spring Web Services, XSD/WSDL, JAXB/OXM, endpoint và SOAP client; đồng thời quản lý SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích khi tích hợp hệ thống doanh nghiệp.

## 1. Vấn đề mà WebServiceMessageCallback giải quyết

Một SOAP client không chỉ gửi một Java object. Đối tác có thể yêu cầu SOAPAction đúng WSDL, SOAP Header chứa correlation ID hoặc version giao thức, header WS-Addressing, thông tin an ninh WS-Security và attachment. Nếu chỉ gọi `WebServiceTemplate.marshalSendAndReceive(request)`, phần **payload** có thể được marshal đúng nhưng những yêu cầu ở mức **SOAP message** chưa chắc đã được đáp ứng.

`org.springframework.ws.client.core.WebServiceMessageCallback` là một **callback được gọi trên thông điệp request trước khi gửi đi**. Nó giúp bổ sung hoặc tùy chỉnh các chi tiết của `WebServiceMessage` khi client chuẩn bị gửi SOAP:

- Đặt **SOAPAction** theo binding/contract.
- Bổ sung **SOAP Header ứng dụng** với namespace và cấu trúc đúng.
- Thêm metadata kỹ thuật được chốt trong hợp đồng mà không thay đổi XSD của SOAP Body.
- Kết hợp nhiều thao tác tùy chỉnh trong **một lời gọi** của `WebServiceTemplate`.
- Phân định rõ phần **request payload**, phần **Envelope/Header** và cấu hình **HTTP transport**.

Callback này **không** thay thế JAXB/OXM, WS-SecurityPolicy, schema validation, certificate trust, HTTP authentication, SOAP Fault handling hoặc client interceptor dài hạn. Việc dùng đúng extension point là quan trọng để không sửa XML sau signing hoặc vô tình lộ dữ liệu nhạy cảm.

**Mục tiêu học tập:** sau bài, bạn có thể phân biệt callback với interceptor; thực hiện SOAPAction và custom header bằng Java; phối hợp callback với JAXB; xác định giai đoạn can thiệp trước khi gửi; kiểm thử SOAPAction/header/response; và tránh rủi ro khi ký số, gửi MTOM hoặc tương thích với đối tác đa nền tảng.

## 2. Callback nằm ở đâu trong vòng đời Spring-WS client?

Luồng gọi phổ biến của `WebServiceTemplate` khi dùng JAXB:

~~~mermaid
sequenceDiagram
  participant App as Business caller
  participant T as WebServiceTemplate
  participant M as JAXB Marshaller
  participant C as WebServiceMessageCallback
  participant I as ClientInterceptor(s)
  participant H as HTTP MessageSender
  participant S as SOAP server
  App->>T: marshalSendAndReceive(request, callback)
  T->>M: Marshal Java object into SOAP Body
  M-->>T: Request WebServiceMessage
  T->>C: doWithMessage(request)
  C-->>T: SOAPAction/Header tùy chỉnh
  T->>I: Xử lý request theo client interceptor chain
  I-->>T: Request tiếp tục
  T->>H: Send SOAP message
  H->>S: HTTP/SOAP request
  S-->>H: HTTP/SOAP response hoặc Fault
  H-->>T: WebServiceMessage response
  T->>I: Response/Fault processing
  T->>M: Unmarshal response payload
  M-->>App: Java response object
~~~

Sơ đồ là **mô hình logic** cho trường hợp marshal, callback và interceptor. Thứ tự chi tiết của nhiều interceptors, message sender, fault handling và security phải được xác nhận theo **phiên bản Spring-WS đang chạy**. Callback gắn với việc chuẩn bị **request**, không phải hook đọc toàn bộ response hoặc SOAP Fault.

### 2.1. Callback interface

~~~java
import java.io.IOException;
import javax.xml.transform.TransformerException;

import org.springframework.ws.WebServiceMessage;
import org.springframework.ws.client.core.WebServiceMessageCallback;

public final class ExampleCallback
        implements WebServiceMessageCallback {

    @Override
    public void doWithMessage(WebServiceMessage message)
            throws IOException, TransformerException {
        // Chỉ thao tác trên outgoing WebServiceMessage.
    }
}
~~~

Chữ ký nhận một `WebServiceMessage`, abstraction chung cho message, không nhất thiết là SOAP. Nếu cần `SoapHeader` hoặc SOAPAction, kiểm tra/cast sang `SoapMessage`. Các lớp `javax.xml.transform.*` ở đây là JAXP của JDK; trong ứng dụng Spring Boot/Jakarta mới, chúng **không** đồng nghĩa với việc dùng JAXB `javax.xml.bind` đời cũ.

Đối với thao tác đơn giản, `WebServiceMessageCallback` là functional interface nên có thể dùng lambda:

~~~java
WebServiceMessageCallback callback = message -> {
    if (!(message instanceof SoapMessage soap)) {
        throw new IllegalStateException("SOAP message required");
    }
    soap.setSoapAction("urn:example:orders:v1/GetOrder");
};
~~~

Cần import `org.springframework.ws.soap.SoapMessage`, `WebServiceMessageCallback`. Java 17 hỗ trợ cú pháp pattern matching `instanceof ... soap` như trên.

### 2.2. Callback khác gì với ClientInterceptor?

| Tiêu chí | `WebServiceMessageCallback` | `ClientInterceptor` |
|---|---|---|
| Phạm vi chính | Một lời gọi send/marshal-send khi được truyền vào | Cấu hình trên `WebServiceTemplate` cho các lời gọi |
| Thời điểm | Request đang được chuẩn bị trước khi gửi | Có các hook cho request, response và fault theo lifecycle |
| Đối tượng | `WebServiceMessage` outgoing | `MessageContext` và các trạng thái xử lý |
| Mục đích điển hình | SOAPAction riêng, header nghiệp vụ riêng của request | Logging metadata an toàn, security, validation, tracing cross-cutting |
| Xử lý response | Không trực tiếp | Có hook cho response/Fault |
| Tần suất logic | Dễ tùy chỉnh theo từng operation | Dễ áp dụng chung nhiều operations |
| Rủi ro | Sửa Body/Header gây sai contract/chữ ký | Cũng có thể phá streaming/chữ ký nếu đọc/sửa message không đúng lúc |

**Quy tắc chọn:** nếu chỉ cần đặt SOAPAction hoặc header **cho một request**, ưu tiên callback. Nếu cần quản lý một chính sách xuyên suốt nhiều lời gọi (ví dụ WS-Security, tracing hoặc response auditing), dùng cấu hình client chuyên trách/interceptor và kiểm thử thứ tự chính xác.

## 3. Bắt đầu từ XSD/WSDL, không từ tên Java method

Giả sử dịch vụ đơn hàng có XSD với namespace `urn:example:orders:v1`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:ord="urn:example:orders:v1"
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
        <xs:element name="orderId" type="xs:string"/>
        <xs:element name="status" type="xs:string"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
~~~

Trong WSDL 1.1 document/literal, input message có thể trỏ tới global element qua `wsdl:part/@element`:

~~~xml
<wsdl:message name="GetOrderInput">
  <wsdl:part name="parameters" element="ord:GetOrderRequest"/>
</wsdl:message>
~~~

Một SOAP 1.1 binding có thể quy định SOAPAction cho operation:

~~~xml
<wsdl:binding name="OrdersSoapBinding" type="ord:OrdersPort">
  <soap:binding style="document"
      transport="http://schemas.xmlsoap.org/soap/http"/>
  <wsdl:operation name="GetOrder">
    <soap:operation soapAction="urn:example:orders:v1/GetOrder"/>
    <wsdl:input>
      <soap:body use="literal"/>
    </wsdl:input>
    <wsdl:output>
      <soap:body use="literal"/>
    </wsdl:output>
  </wsdl:operation>
</wsdl:binding>
~~~

Đây chỉ là **mảnh WSDL**; một WSDL hoàn chỉnh còn khai báo namespaces, `portType`, `types`, `service` và các message tương ứng. Hãy dùng **SOAPAction do binding thực tế quy định**, không tự suy đoán nó luôn bằng tên operation hoặc QName request.

Với hợp đồng này:

| Thành phần | Giá trị | Vai trò |
|---|---|---|
| Endpoint URI (ví dụ) | `https://partner.example.test/soap/orders` | URL đích do HTTP transport sử dụng |
| SOAP Body root | `{urn:example:orders:v1}GetOrderRequest` | Global element contract-first |
| WSDL operation | `GetOrder` | Operation công bố cho client |
| SOAPAction | `urn:example:orders:v1/GetOrder` | Action của SOAP 1.1 binding trong ví dụ |
| Java client method | `findById` hoặc `getOrder` | Tên nội bộ, không quyết định wire contract |
| SOAP Header ứng dụng | `{urn:example:meta:v1}CorrelationId` | Metadata ngoài Body nếu đối tác quy định |

**Không nhầm SOAPAction với @PayloadRoot:** `@PayloadRoot` ở server đối chiếu QName phần tử đầu SOAP Body; SOAPAction là tín hiệu khác. Server có thể cấu hình routing theo SOAPAction hoặc WS-Addressing Action, vì vậy cần giữ các giá trị đồng bộ theo WSDL.

## 4. Dùng SoapActionCallback: cách đơn giản và rõ nghĩa nhất

Spring-WS cung cấp `SoapActionCallback`, một implementation sẵn có của `WebServiceMessageCallback`:

~~~java
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.soap.client.core.SoapActionCallback;

public class OrderSoapClient {
    private final WebServiceTemplate webServiceTemplate;

    public OrderSoapClient(WebServiceTemplate webServiceTemplate) {
        this.webServiceTemplate = webServiceTemplate;
    }

    public Object getOrder(Object jaxbRequest) {
        return webServiceTemplate.marshalSendAndReceive(
            "https://partner.example.test/soap/orders",
            jaxbRequest,
            new SoapActionCallback("urn:example:orders:v1/GetOrder"));
    }
}
~~~

Đây là **ví dụ vị trí API**: `jaxbRequest` phải là JAXB root object mà `Jaxb2Marshaller` marshal được, endpoint URI phải được cấu hình cho môi trường thực. Khi XJC sinh `JAXBElement` thay vì class có `@XmlRootElement`, hãy dùng `ObjectFactory` bọc request phù hợp.

`SoapActionCallback` nên được ưu tiên khi **chỉ** cần đặt SOAPAction vì không phải tự cast message hoặc viết callback tùy biến. Nó cũng làm mục đích của lời gọi rõ ràng khi review code.

### 4.1. SOAPAction trên HTTP

Một SOAP 1.1 HTTP request thường có hình thức:

~~~http
POST /soap/orders HTTP/1.1
Host: partner.example.test
Content-Type: text/xml; charset=utf-8
SOAPAction: "urn:example:orders:v1/GetOrder"
~~~

Message body là SOAP Envelope riêng. Cách library encode/quote SOAPAction header phụ thuộc message factory/transport; hãy **capture request thực** trong integration test thay vì tự ghép chuỗi header hoặc thêm dấu ngoặc kép vào giá trị Java khi chưa biết contract framework.

Không dùng callback để tự ghi trực tiếp HTTP `Content-Type`, `Host` hoặc `Authorization`. Đó là trách nhiệm của **message factory/HTTP transport/message sender** (và chính sách TLS/credential). SOAP Header XML và HTTP headers thuộc hai tầng khác nhau.

### 4.2. SOAP 1.1 và SOAP 1.2

- SOAP 1.1 thường có HTTP header `SOAPAction` được binding quy định.
- SOAP 1.2 dùng media type `application/soap+xml` và action parameter/cơ chế liên quan theo binding; không áp dụng máy móc cách xây SOAP 1.1 vào SOAP 1.2.
- `SoapMessage.setSoapAction(...)` là API abstraction của Spring-WS, nhưng kết quả trên wire và khả năng hỗ trợ phụ thuộc SOAP version/message factory.

Trước khi đặt action, phải xác nhận `WebServiceTemplate` đang dùng message factory tạo đúng SOAP version mà đối tác chấp nhận. Không chỉ sửa HTTP header để biến một Envelope SOAP 1.1 thành SOAP 1.2.

## 5. Tùy chỉnh SOAP Header bằng WebServiceMessageCallback

Giả sử đối tác yêu cầu một SOAP Header **ứng dụng**, không phải WS-Security Header:

~~~xml
<soapenv:Header
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:m="urn:example:meta:v1">
  <m:CorrelationId>TRACE-1001</m:CorrelationId>
</soapenv:Header>
~~~

Giá trị `TRACE-1001` chỉ là dữ liệu test. Một correlation ID thật nên được sinh hoặc kiểm soát theo **trust boundary** của hệ thống, giới hạn ký tự và độ dài; không gắn PII hoặc secret vào nó.

### 5.1. Tạo element từ DOM, không nối XML string từ input

~~~java
package com.example.orders.soap;

import java.io.IOException;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.parsers.ParserConfigurationException;
import javax.xml.transform.Transformer;
import javax.xml.transform.TransformerException;
import javax.xml.transform.TransformerFactory;
import javax.xml.transform.dom.DOMSource;

import org.springframework.ws.WebServiceMessage;
import org.springframework.ws.client.core.WebServiceMessageCallback;
import org.springframework.ws.soap.SoapMessage;
import org.w3c.dom.Document;
import org.w3c.dom.Element;

public final class OrderHeaderCallback
        implements WebServiceMessageCallback {

    private static final String META_NS = "urn:example:meta:v1";
    private static final String ACTION =
            "urn:example:orders:v1/GetOrder";

    private final String correlationId;

    public OrderHeaderCallback(String correlationId) {
        if (correlationId == null
                || !correlationId.matches("[A-Za-z0-9-]{1,64}")) {
            throw new IllegalArgumentException(
                    "Invalid correlation ID format");
        }
        this.correlationId = correlationId;
    }

    @Override
    public void doWithMessage(WebServiceMessage message)
            throws IOException, TransformerException {
        if (!(message instanceof SoapMessage soap)) {
            throw new IllegalStateException("SOAP message required");
        }

        soap.setSoapAction(ACTION);

        // Chỉ tạo một DOM fragment do ứng dụng sở hữu.
        DocumentBuilderFactory factory =
                DocumentBuilderFactory.newInstance();
        factory.setNamespaceAware(true);

        try {
            Document doc =
                    factory.newDocumentBuilder().newDocument();

            Element headerValue = doc.createElementNS(
                    META_NS, "m:CorrelationId");
            headerValue.setAttributeNS(
                    "http://www.w3.org/2000/xmlns/",
                    "xmlns:m", META_NS);
            headerValue.setTextContent(correlationId);
            doc.appendChild(headerValue);

            Transformer transformer =
                    TransformerFactory.newInstance()
                            .newTransformer();

            transformer.transform(
                    new DOMSource(headerValue),
                    soap.getSoapHeader().getResult());
        } catch (ParserConfigurationException ex) {
            throw new IllegalStateException(
                    "Cannot create SOAP header DOM", ex);
        }
    }
}
~~~

**Tại sao dùng `setTextContent`?** Nó giữ escaping XML đúng cho giá trị text, thay vì chèn nguyên input vào markup. Ở đây giá trị còn được giới hạn vào tập ký tự cho phép. `DOMSource` được tạo từ tài liệu **mới do ứng dụng dựng**, không parse XML từ Internet, nên không phải một bộ parser nhận input chưa tin cậy.

`SoapHeader#getResult()` cung cấp đích JAXP `Result` để đưa nội dung header vào SOAP message. Không tự ghi cả `<soapenv:Header>...</soapenv:Header>` vào đích này: SOAP message factory đã quản lý SOAP Envelope/Header. Ví dụ viết **một child element** `m:CorrelationId`, không tạo Header lồng.

**Điều kiện tương thích:** đoạn code trên mô tả một cách làm với SOAP message factory hỗ trợ `SoapHeader#getResult()` và Transformer JAXP. Hãy chạy test với **message factory/version thực** của dự án (SAAJ/Axiom hoặc implementation tương đương), vì buffering và khả năng transform có thể khác nhau.

### 5.2. Gọi callback từ client

~~~java
Object response = webServiceTemplate.marshalSendAndReceive(
    "https://partner.example.test/soap/orders",
    requestJaxbRoot,
    new OrderHeaderCallback("TRACE-1001"));
~~~

`requestJaxbRoot` là request JAXB đã cấu hình; callback thực hiện **cả SOAPAction lẫn custom header** trong một lời gọi. Nó không sửa cấu trúc Body sinh từ XSD và không cung cấp chữ ký WS-Security.

### 5.3. Header cần namespace riêng

| Sai lầm | Vì sao sai |
|---|---|
| Viết `CorrelationId` không namespace | Đối tác có thể mong `{urn:example:meta:v1}CorrelationId` |
| Dùng prefix `m` nhưng không khai báo URI | XML header không namespace-well-formed |
| Đổi namespace URI để giống URL endpoint | QName của header bị thay |
| Đưa `CorrelationId` vào SOAP Body | Làm sai payload root/structure theo XSD |
| Gửi credential/password dưới dạng custom header tự tạo | Không tự có xác thực, integrity hay bảo mật |
| Tạo XML bằng string concatenation với input | Có nguy cơ XML injection/escaping sai |

Dùng QName thực tế từ WSDL/header contract hoặc tài liệu tích hợp đã thỏa thuận. Nếu đối tác yêu cầu SOAP Header với `mustUnderstand`, `actor`/`role` hoặc WS-Addressing, phải xử lý theo **đúng SOAP version và policy**; không tự đoán các thuộc tính này.

## 6. Kết hợp nhiều tùy chỉnh trong một request

Một số operation vừa cần SOAPAction vừa cần metadata header, trong khi một operation khác chỉ cần SOAPAction. Vì `marshalSendAndReceive(...)` nhận **một `WebServiceMessageCallback`** ở vị trí callback, không thể truyền nhiều callback như nhiều tham số độc lập; cần tạo **callback tổng hợp** hoặc dùng callback tự xử lý các thao tác cần thiết.

### 6.1. Lambda tổng hợp

~~~java
import org.springframework.ws.client.core.WebServiceMessageCallback;
import org.springframework.ws.soap.SoapMessage;

WebServiceMessageCallback callback = message -> {
    if (!(message instanceof SoapMessage soap)) {
        throw new IllegalStateException("SOAP message required");
    }

    soap.setSoapAction("urn:example:orders:v1/GetOrder");

    // Bổ sung các SOAP headers hợp lệ của request tại đây.
    // Nếu cần thao tác DOM, tái sử dụng helper tạo header
    // từ dữ liệu đã được kiểm tra, không nối XML raw.
};
~~~

Để tránh trùng logic với `OrderHeaderCallback` ở mục 5, cách đơn giản nhất là đặt tất cả tùy chỉnh của operation đó trong cùng một class. Không nên tạo nhiều callback rải rác rồi tự ý gọi chúng ở nhiều giai đoạn vì dễ vi phạm thứ tự ký hoặc gắn trùng header.

### 6.2. Tái sử dụng SoapActionCallback

Nếu muốn tái sử dụng implementation có sẵn:

~~~java
import org.springframework.ws.client.core.WebServiceMessageCallback;
import org.springframework.ws.soap.client.core.SoapActionCallback;

SoapActionCallback action =
        new SoapActionCallback("urn:example:orders:v1/GetOrder");

WebServiceMessageCallback callback = message -> {
    action.doWithMessage(message);

    // Helper của ứng dụng chỉ thêm metadata header theo contract.
    // Không tạo security token thủ công trong helper này.
    addBusinessMetadataHeader(message, "TRACE-1001");
};
~~~

`addBusinessMetadataHeader(...)` là **helper giả định** của ứng dụng. Nó cần triển khai thao tác SOAP Header tương tự mục 5, kiểm tra đầu vào và namespace, có test riêng. Đoạn code diễn giải cơ chế composition, không phải một file Java độc lập có thể compile ngay.

Chú ý callback có thể được gọi lại ở mỗi attempt nếu ứng dụng thực hiện retry, hoặc tạo callback riêng cho mỗi request. Tránh callback chứa trạng thái thay đổi giữa requests như `currentInvoiceId` hay `currentToken` trong singleton.

### 6.3. SOAPActionCallback so với callback tự viết

| Nhu cầu | Phương án phù hợp |
|---|---|
| Chỉ SOAPAction | `new SoapActionCallback(actionFromWsdl)` |
| SOAPAction + 1 header metadata | Callback tổng hợp như `OrderHeaderCallback` |
| Nhiều headers theo cùng contract | Helper tạo từng element từ QName/schema; một callback |
| WS-Addressing Action/MessageID/ReplyTo | API WS-Addressing chuyên dụng hoặc callback do framework hỗ trợ |
| UsernameToken, chữ ký, encryption | WS-Security interceptor và security policy, **không tự ghép XML** |
| HTTP Authorization, proxy, TLS | Message sender/transport hoặc cơ chế credential của client |
| Đọc/chuyển response SOAP | `ClientInterceptor` hoặc response extractor/handler phù hợp |

Tùy chỉnh ít hơn thường an toàn hơn: không cần thêm một custom callback chỉ để đặt SOAPAction khi Spring-WS đã có `SoapActionCallback`.

## 7. Cấu hình JAXB/OXM cho WebServiceTemplate

Trong ứng dụng contract-first, XSD/WSDL là nguồn sự thật. Từ XSD, dùng XJC/JAXB tooling để sinh các model hoặc tạo JAXB root object tương thích. Spring OXM cung cấp `Jaxb2Marshaller` để marshal/unmarshal.

### 7.1. Bean cấu hình

~~~java
package com.example.orders.client;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.ws.client.core.WebServiceTemplate;

@Configuration
public class OrdersClientConfiguration {

    @Bean
    public Jaxb2Marshaller ordersMarshaller() {
        Jaxb2Marshaller m = new Jaxb2Marshaller();

        // Package phải tồn tại sau khi sinh JAXB model từ XSD.
        m.setContextPath("com.example.orders.contract");
        return m;
    }

    @Bean
    public WebServiceTemplate ordersWebServiceTemplate(
            Jaxb2Marshaller ordersMarshaller) {
        WebServiceTemplate template = new WebServiceTemplate();
        template.setMarshaller(ordersMarshaller);
        template.setUnmarshaller(ordersMarshaller);
        return template;
    }
}
~~~

Giả định project dùng Spring Boot/Spring-WS/JAXB runtime **tương thích phiên bản** và package `com.example.orders.contract` đã có `ObjectFactory` hoặc metadata JAXB cần thiết. Các bản Spring Boot dùng Jakarta mới thường cần JAXB API/runtime dưới namespace `jakarta.xml.bind.*`; không trộn `javax.xml.bind.*` đời cũ với runtime mới.

Config này chưa chứa endpoint URL mặc định, HTTP timeout, TLS truststore, proxy, WS-Security, connection pool hoặc cơ chế retry. Vì thế, không nên chép nguyên vào production rồi coi là cấu hình client hoàn chỉnh.

### 7.2. JAXB request: class hay JAXBElement?

Một số XSD sinh lớp có `@XmlRootElement`, còn một số sinh `JAXBElement` qua `ObjectFactory`. Nếu root element không tự marshal được, cần dùng đúng factory:

~~~java
// Minh họa với kiểu JAXB sinh ra, tên class/method tùy XJC.
GetOrderRequestType body = new GetOrderRequestType();
body.setOrderId("ORD-1001");

ObjectFactory factory = new ObjectFactory();
JAXBElement<GetOrderRequestType> requestRoot =
        factory.createGetOrderRequest(body);

Object result = webServiceTemplate.marshalSendAndReceive(
        "https://partner.example.test/soap/orders",
        requestRoot,
        new SoapActionCallback("urn:example:orders:v1/GetOrder"));
~~~

Ví dụ này **chỉ chạy** khi XJC của schema thực sự sinh `GetOrderRequestType` và phương thức `createGetOrderRequest(...)` nhận type đó. XSD minh họa ở mục 3 dùng *anonymous complex type* nên công cụ sinh mã có thể tạo một class `GetOrderRequest` có root annotation thay vì một `GetOrderRequestType`. Hãy xem **mã đã sinh thật**, không đoán chữ ký từ tên operation.

**Điểm mấu chốt:** callback tùy chỉnh SOAP message, nhưng **không sửa QName payload root** nếu marshaller đã tạo đúng global element. Thay tên Java method hoặc proxy DTO không được coi là đổi wire contract nếu XML phát ra không đổi.

### 7.3. Thứ tự xử lý payload và callback

Khi gọi `marshalSendAndReceive`, request payload được marshal trước rồi callback được gọi trên outgoing message. Vì thế có thể:

- Set SOAPAction và thêm Header mà không đụng Body.
- Đọc một số metadata đã được **định nghĩa và cho phép** nếu thật sự cần (nhưng tránh parse/serialize Body chỉ để logging).
- Đặt WS-Addressing headers theo API hỗ trợ nếu các header là yêu cầu riêng của message.

**Không nên dùng callback để tái định nghĩa request XML bằng cách thay DOM Body sau JAXB marshalling.** Việc đó dễ làm mất `@XmlRootElement`/JAXB invariant, gây sai XSD, hoặc phá chữ ký nếu security processing được đặt ở giai đoạn không phù hợp.

### 7.4. Nếu dùng Source thay JAXB

Spring-WS còn có các đường gọi dựa trên `Source`; API truyền payload và callback có overload riêng tùy operation. Khi không dùng JAXB, vẫn cần phân biệt:

1. `Source` đại diện **payload XML**.
2. `WebServiceMessageCallback` chỉnh **message** trước khi gửi.
3. Message factory đóng gói **SOAP Envelope** và HTTP transport gửi bytes.

Vì các overload `sendSourceAndReceive...` không hoàn toàn giống `marshalSendAndReceive(...)`, hãy kiểm tra chữ ký thực của **WebServiceTemplate version đang dùng** và không tự thay `Source` vào một overload dành cho JAXB object rồi kỳ vọng nó marshal đúng.

## 8. SOAP Header và WS-Addressing không phải SOAPAction

Ba cơ chế dễ bị nhầm:

| Cơ chế | Vị trí trên wire | Ý nghĩa |
|---|---|---|
| SOAPAction (SOAP 1.1) | HTTP header | Action theo SOAP 1.1 binding |
| WS-Addressing `wsa:Action` | SOAP Header | Message addressing/action của WS-Addressing profile |
| Business header `m:CorrelationId` | SOAP Header | Metadata nghiệp vụ do hợp đồng riêng định nghĩa |

Một request có thể có **cả ba**, và các giá trị không nhất thiết trùng nhau. WSDL, WS-Addressing metadata/policy và tài liệu đối tác quyết định quan hệ giữa chúng.

### 8.1. WS-Addressing ActionCallback

Spring-WS có `org.springframework.ws.soap.addressing.client.ActionCallback` cho việc cấu hình action WS-Addressing theo API hỗ trợ:

~~~java
import java.net.URI;
import org.springframework.ws.soap.addressing.client.ActionCallback;

// Minh họa: URI action phải theo WS-Addressing contract thực.
ActionCallback callback =
        new ActionCallback(URI.create("urn:example:orders:v1/GetOrder"));
~~~

`ActionCallback` là lựa chọn ở tầng WS-Addressing, không đồng nghĩa `SoapActionCallback`. Khi kết hợp WS-Addressing và SOAPAction trên cùng client:

- Chốt namespace WS-Addressing (2005/08 hay profile legacy nếu đối tác dùng).
- Xác minh `Action`, `To`, `MessageID`, `ReplyTo` theo hợp đồng và policy.
- Không tự đặt một header `<wsa:Action>` bằng chuỗi chỉ để làm server hết báo lỗi.
- Kiểm tra SOAPAction và `wsa:Action` có nhất quán **khi đối tác yêu cầu**; đừng giả định mọi stack tự động đồng bộ.
- Nếu các headers nằm trong phạm vi WS-Security signature, phải bảo đảm chúng được tạo **trước khi ký** theo cấu hình thực.

Lưu ý: khi compose callback WS-Addressing với callback khác, phải bảo đảm chúng không ghi đè nhau và message factory hiện hành hỗ trợ profile WS-Addressing đang dùng.

### 8.2. Một SOAP Envelope minh họa

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:m="urn:example:meta:v1"
    xmlns:wsa="http://www.w3.org/2005/08/addressing"
    xmlns:o="urn:example:orders:v1">
  <soapenv:Header>
    <wsa:Action>urn:example:orders:v1/GetOrder</wsa:Action>
    <m:CorrelationId>TRACE-1001</m:CorrelationId>
  </soapenv:Header>
  <soapenv:Body>
    <o:GetOrderRequest>
      <o:orderId>ORD-1001</o:orderId>
    </o:GetOrderRequest>
  </soapenv:Body>
</soapenv:Envelope>
~~~

Đây là **mẫu cấu trúc**, không phải SOAP message có đầy đủ WS-Addressing headers hoặc WS-Security theo mọi policy. Tùy hợp đồng, có thể cần `wsa:To`, `MessageID`, `ReplyTo` và security headers. Đừng dùng ví dụ này để kết luận một đối tác enterprise sẽ chấp nhận request nếu chưa đọc WSDL/policy.

## 9. Tránh sai lầm: SOAP Header, HTTP Header và bảo mật

Callback tiếp cận `WebServiceMessage`. Một số thông tin cần đặt ở **HTTP transport**, không phải SOAP Header:

| Yêu cầu | Tầng cấu hình |
|---|---|
| HTTP Basic authentication hoặc bearer token qua HTTPS | HTTP message sender/credential mechanism |
| mTLS client certificate | TLS/SSL context, keystore, message sender |
| Truststore và hostname verification | TLS transport policy |
| Proxy, connection timeout, read timeout | HTTP message sender |
| SOAPAction | `SoapActionCallback` hoặc `SoapMessage.setSoapAction` |
| Business SOAP Header | `WebServiceMessageCallback` hoặc SOAP-specific helper |
| WS-Security signature/token/encryption | WSS4J/security interceptor theo policy |
| Content-Type SOAP 1.1/1.2 | SOAP message factory + HTTP transport |
| SOAP Fault response interpretation | `WebServiceTemplate` fault handling / `ClientInterceptor` |

**Bảo mật quan trọng:** SOAP Header có tên `Authorization` hoặc `UsernameToken` do bạn tự chèn XML **không** tự có chữ ký, chống replay, encryption hoặc key trust. Một WS-SecurityPolicy đúng cần WSS4J hoặc implementation tương thích, được cấu hình và kiểm thử với chứng chỉ đối tác.

### 9.1. Callback không thay thế XML security

Nếu callback biến raw XML untrusted thành SOAP header, cần bảo vệ parser/transformer chống XXE, external entity, SSRF và XML injection. Ví dụ mục 5 chỉ tạo DOM mới từ text đã được kiểm tra, không parse XML từ mạng.

Khi thực sự phải parse XML input:

- Vô hiệu hóa DTD/external entities không cần thiết.
- Kiểm soát `TransformerFactory`/`SchemaFactory` external access theo provider.
- Giới hạn kích thước, độ sâu, số lượng elements/attributes.
- Không cho user truyền URI schema hay XPath bất kỳ để server/client tự tải tài nguyên ngoài.
- Dùng namespace-aware processing và type/field validation theo XSD.

Đừng xử lý vấn đề bằng cách chỉ “escape HTML” một chuỗi rồi đưa vào SOAP Header; XML có cấu trúc namespace, attribute, character escaping và schema riêng.

### 9.2. WSDL và chứng chỉ có vai trò khác nhau

WSDL mô tả SOAP contract; chứng chỉ/TLS/WS-Security quyết định tính xác thực và an toàn khi trao đổi. Client có thể gửi payload QName/SOAPAction đúng WSDL nhưng vẫn bị từ chối do:

- TLS certificate chain không được trust.
- Hostname certificate không khớp.
- Client chưa gửi mTLS certificate.
- WS-Security timestamp quá hạn hoặc token không hợp lệ.
- Chữ ký SOAP sai thuật toán/reference/profile.
- User hoặc service principal thiếu quyền gọi operation.

Không suy luận callback đã “cấu hình security” chỉ vì đã thêm một XML header hoặc đặt SOAPAction thành công.

## 10. Tùy chỉnh trước khi ký: tránh làm hỏng WS-Security

### 10.1. Phân biệt trạng thái của một SOAP message

Trong hệ thống enterprise, outgoing message có thể lần lượt trải qua những trạng thái:

~~~mermaid
flowchart LR
    M["JAXB marshal Body"] --> C["Callback: SOAPAction + app headers"]
    C --> V["Kiểm tra contract / policy"]
    V --> S["WS-Security: ký/mã hóa theo policy"]
    S --> T["Transport: HTTP/TLS"]
    T --> R["Đối tác verify + process"]
~~~

Đây là **sơ đồ trách nhiệm** mong muốn, không phải lời khẳng định mọi implementation luôn có cùng thứ tự sign/encrypt/validation. SecurityPolicy có thể yêu cầu ký rồi mã hóa, mã hóa rồi ký hoặc bảo vệ các parts khác nhau. Phải dựa vào WSS4J/security configuration đúng phiên bản và kiểm thử actual wire message.

Callback thường được dùng để **chuẩn bị những headers cần thiết trước các client interceptors xử lý request** trong `WebServiceTemplate`. Khi ký SOAP Header hoặc Body, phải xác minh callback đã hoàn tất trước thời điểm ký. Nếu gắn security theo một cơ chế khác hoặc có các transport hooks riêng, cần kiểm tra thứ tự thực.

### 10.2. Những thay đổi có thể phá XML Signature

| Hành động | Rủi ro |
|---|---|
| Đổi giá trị `orderId` trong Body đã ký | Digest của reference Body có thể thay đổi |
| Đổi `amount` từ `100.00` thành `100` sau signing | XSD decimal có thể coi bằng nhau nhưng XML Signature có thể fail |
| Sửa namespace declarations/prefix/whitespace | Có thể ảnh hưởng canonicalization tùy transform và phạm vi ký |
| Đổi `wsu:Id` hoặc vị trí referenced element | Có thể làm verifier không tìm đúng signed part |
| Thêm header nằm trong phạm vi signature/policy sau ký | Có thể phá digest hoặc vi phạm policy |
| Thay byte của MTOM attachment đã ký | Signature/attachment integrity fail nếu được bảo vệ |
| Thêm một header ngoài references | Chưa chắc phá digest, nhưng vẫn có thể vi phạm WS-SecurityPolicy |

XML Signature xác minh **dữ liệu được reference sau canonicalization và transforms**, không so sánh hai Java DTO theo `equals`. Vì vậy, callback và interceptor khác phải tôn trọng signed parts. Không đưa code “format lại XML cho đẹp” vào đường gửi message đã ký.

### 10.3. Dùng đúng thư viện cho UsernameToken, signature và encryption

Khi đối tác yêu cầu WS-Security, cấu hình dựa trên WSS4J và policy phù hợp để xử lý:

- Private key, certificate, keystore và truststore.
- Signed references cho SOAP Body/Header, Timestamp và các security headers cần bảo vệ.
- Signature/encryption algorithms, canonicalization và timestamp tolerance.
- Replay protection, token validation và quyền nghiệp vụ.
- MTOM/attachment signing khi policy yêu cầu.

Không viết:

~~~java
// KHÔNG phải cách triển khai WS-Security:
String xml = "<wsse:UsernameToken><wsse:Password>"
        + rawPassword
        + "</wsse:Password></wsse:UsernameToken>";
~~~

Đoạn trên là **anti-pattern minh họa**, không phải XML đúng chuẩn hay bảo mật. Nó vừa có nguy cơ injection vừa không thực hiện key derivation/nonce/timestamp/password digest theo profile. Đừng log secret hoặc chèn plaintext password nếu policy không cho phép.

### 10.4. TLS và WS-Security không thay thế nhau

- **TLS:** bảo vệ đường truyền giữa hai endpoints của một kết nối; cần xác thực certificate chain/hostname, và có thể cần mTLS.
- **WS-Security:** có thể bảo vệ phần của SOAP message qua trung gian, theo chính sách signing/encryption/token.
- **Business authorization:** kiểm tra người gọi có quyền thực hiện operation và truy cập đơn hàng cụ thể.

SOAPAction và header do callback thêm vào chỉ giúp yêu cầu giao thức/định tuyến, **không chứng minh** caller đã xác thực.

## 11. MTOM, attachment và chi phí của callback

SOAP có thể mang binary trong `xs:base64Binary` inline hoặc dùng MTOM/XOP để truyền qua MIME attachments. Callback tác động lên `WebServiceMessage` lúc sắp gửi, nên các thao tác quan sát hoặc sửa message có thể ảnh hưởng streaming.

### 11.1. Cảnh báo: đọc lại toàn bộ message trong callback

Đây là ví dụ **không nên làm** trong callback gửi file lớn:

~~~java
// Anti-pattern: serialize toàn SOAP chỉ để log.
ByteArrayOutputStream buffer = new ByteArrayOutputStream();
message.writeTo(buffer);
logger.debug("SOAP outgoing: {}",
        buffer.toString(StandardCharsets.UTF_8));
~~~

Tác hại:

1. Có thể tạo thêm bản copy của XML, Base64 hoặc MIME package trong heap.
2. Có thể làm mất ưu thế streaming hoặc tạo temporary I/O khi xử lý attachments.
3. Bộc lộ PII, SOAP Header và token/secret ra log.
4. Với stream chỉ đọc một lượt, thao tác đọc/serialize có thể khiến send sau đó thất bại hoặc thay behavior.
5. Tăng GC, latency và rủi ro memory pressure dưới tải đồng thời.

Đừng kết luận `writeTo(...)` **luôn** tiêu thụ stream hoặc **luôn** phá chữ ký: hành vi còn phụ thuộc message factory, attachment implementation và thời điểm signing. Nhưng nó là thao tác rủi ro cao, cần tránh khi không thực sự cần.

### 11.2. Dùng DataHandler đúng mục đích

Với JAXB model được sinh từ XSD có `xmime:expectedContentTypes`, một số công cụ dùng `DataHandler` thay `byte[]`:

~~~java
import jakarta.activation.DataHandler;
import jakarta.activation.FileDataSource;

// Chỉ ví dụ: DTO phải có accessor tương ứng sau XJC.
DataHandler pdf =
        new DataHandler(new FileDataSource("sample.pdf"));
uploadRequest.setDocument(pdf);
~~~

Phần này cần source file tin cậy, lifecycle stream rõ và runtime JAXB/MTOM được cấu hình đúng. Không đưa đường dẫn file từ input người dùng trực tiếp vào `FileDataSource`, tránh path traversal; kiểm tra MIME type thực, dung lượng, policy quét file và cleanup.

Nếu bật MTOM trên `Jaxb2Marshaller`:

~~~java
Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
marshaller.setContextPath("com.example.documents.contract");
marshaller.setMtomEnabled(true);
~~~

thì đó là **một điều kiện** cho marshalling tối ưu, không bảo đảm mọi blob luôn được tách MIME part hoặc endpoint/gateway đều hỗ trợ. Muốn chứng minh, phải capture actual HTTP multipart package và so bytes/chữ ký qua client/server thật.

### 11.3. Callback có nên sửa attachment không?

Chỉ khi có yêu cầu giao thức cụ thể, API message factory hỗ trợ và bảo đảm:

- Attachment Content-ID, MIME headers và XOP references nhất quán.
- Binary bytes đúng như contract, không bị thay sau signing.
- Nếu security policy ký attachment, các transforms/profile được hỗ trợ đúng.
- Giới hạn kích thước **wire bytes** và **decoded bytes**.
- Stream/temporary files được đóng và dọn trong cả success/Fault.
- Không log raw attachments hoặc tên file nhạy cảm.

Một callback thêm correlation ID không có lý do phải truy cập mọi attachment. **Càng ít chạm dữ liệu nhạy cảm, càng dễ giữ hiệu năng và tính toàn vẹn.**

## 12. Thread safety, callback theo request và retry

### 12.1. Callback nên mang trạng thái bất biến

Một `WebServiceTemplate` bean thường được tái sử dụng cho nhiều request. Callback có thể là object tạo theo từng lời gọi, ví dụ:

~~~java
public Object fetchOrder(
        Object requestRoot, String correlationId) {
    WebServiceMessageCallback callback =
            new OrderHeaderCallback(correlationId);

    return webServiceTemplate.marshalSendAndReceive(
            "https://partner.example.test/soap/orders",
            requestRoot, callback);
}
~~~

`OrderHeaderCallback` giữ `correlationId` trong một field `final`, đã validate tại constructor, không đặt biến mutable `currentRequestId` trên singleton Spring bean. Với nhiều threads, thiết kế này tránh việc request A vô tình dùng ID của request B.

Nếu các callback cần cấu hình chung, hãy lưu **cấu hình bất biến** (namespace URI, SOAPAction từ contract, trust policy), còn metadata per-request phải được truyền theo request thay vì ghi vào biến static.

### 12.2. Chú ý retries

Một retry có thể thực hiện **lại callback** để chuẩn bị request mới. Không giả định callback chỉ chạy duy nhất một lần trong toàn bộ vòng đời nghiệp vụ nếu ứng dụng có retry wrapper. Điều này đặc biệt quan trọng với:

- `MessageID` của WS-Addressing: có policy yêu cầu message identifier riêng cho mỗi attempt hoặc cơ chế tương quan cụ thể.
- Correlation ID: cùng business request nhưng nhiều attempts phải được phân biệt nếu cần observability.
- Timestamp/nonce/security token: không tái sử dụng sai profile hoặc dùng giá trị đã hết hạn.
- SOAP operations có side effects như `SubmitPayment`: retry mù có thể tạo giao dịch trùng.

Cần thiết kế **idempotency key** và retry policy theo hợp đồng, không tự dùng SOAPAction hoặc một correlation ID tự phát làm bằng chứng idempotent.

### 12.3. Callback failure xảy ra trước khi gửi

Nếu `doWithMessage(...)` ném exception, request có thể bị dừng **trước khi transport gửi**. Ứng dụng cần phân biệt:

- Callback/serialization failure: vấn đề cấu hình hoặc dữ liệu phía client, không mặc định đối tác đã nhận.
- Connection/TLS failure: có thể chưa tới server hoặc đã kết nối một phần, tùy thời điểm.
- Response timeout: không chắc server chưa thực hiện operation.
- SOAP Fault: đối tác đã xử lý ở tầng SOAP và trả Fault, cần đọc fault code/detail theo policy.

Không ghi log raw SOAP Body trong catch block chỉ để điều tra callback exception; thông tin operation code, exception category và correlation/tracing ID đã kiểm soát thường đủ để bắt đầu chẩn đoán.

## 13. SOAP Fault, exception và response không đi qua request callback

`WebServiceMessageCallback#doWithMessage` chỉ xử lý **outgoing request**. Nó không phải cơ chế nhận SOAP Fault hoặc sửa incoming response.

### 13.1. Một SOAP Fault mẫu

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
  <soapenv:Body>
    <soapenv:Fault>
      <faultcode>soapenv:Client</faultcode>
      <faultstring>Request validation failed</faultstring>
    </soapenv:Fault>
  </soapenv:Body>
</soapenv:Envelope>
~~~

Đây là **minh họa SOAP 1.1**, không có `Detail` hay modeled fault cụ thể; SOAP 1.2 sử dụng cấu trúc Fault khác. Đối tác có thể dùng fault code, reason và detail theo WSDL/profile được thỏa thuận.

Trong Spring-WS, `WebServiceTemplate` có cơ chế fault detection/handling; ứng dụng thường cần xử lý các exception như `SoapFaultClientException` và phân biệt chúng với transport exceptions, marshalling errors và callback failures.

~~~java
try {
    Object response = webServiceTemplate.marshalSendAndReceive(
            endpointUri,
            requestRoot,
            new SoapActionCallback(action));

    // Chuyển response JAXB theo model hợp đồng.
    return response;
} catch (SoapFaultClientException ex) {
    // Không log nguyên faultstring/detail nếu đối tác có thể
    // đưa dữ liệu nhạy cảm hoặc nội dung do caller kiểm soát.
    throw new PartnerSoapCallException(
            "Partner returned a SOAP Fault", ex);
}
~~~

`PartnerSoapCallException` là **exception do ứng dụng phải tự định nghĩa**; biến `endpointUri` và `action` phải được cấu hình thật. Ví dụ này cho thấy ranh giới xử lý, không phải đầy đủ retry/error mapping. Đừng đánh đồng mọi SOAP Fault là lỗi có thể retry.

### 13.2. ClientInterceptor khác callback trong việc quan sát response

Nếu cần đo latency, phân loại SOAP Fault hoặc thêm metrics của client, `ClientInterceptor` có các callback thích hợp với request, response và fault. Nhưng:

- Interceptor logging cũng phải **metadata-only** theo mặc định.
- Không parse toàn bộ response để làm metrics nếu đã có API fault category hoặc protocol metadata.
- Bảo đảm trình tự verify WS-Security response trước khi dùng dữ liệu nhạy cảm.
- Một số lỗi transport/TLS xảy ra trước khi có SOAP response để interceptor xử lý.
- Interceptor không thay thế schema validation hoặc xử lý lỗi nghiệp vụ trong service layer.

**Kết luận:** callback dành cho chuẩn bị message outgoing; interceptor và fault handler dành cho những trách nhiệm xuyên suốt hoặc response/fault theo phạm vi tương ứng.

## 14. Những sai sót phổ biến và cách xác định nguyên nhân

| Hiện tượng | Nguyên nhân khả dĩ | Kiểm tra đầu tiên |
|---|---|---|
| WSDL tải được nhưng SOAP POST bị từ chối | SOAPAction sai, payload QName sai, SOAP version khác | So WSDL binding, Body root, Content-Type |
| Gửi SOAPAction nhưng server vẫn “no endpoint” | Server routing theo `@PayloadRoot` hoặc WS-Addressing Action khác | QName/WS-A action thực |
| SOAP Header có thẻ nhưng đối tác không đọc | Namespace URI/QName sai, sai cấp Header/Body, sai `mustUnderstand` | Capture actual Envelope, WSDL/header contract |
| XML header không well-formed | Ghép chuỗi không escape, prefix chưa khai báo | Dùng DOM/JAXB, namespace-aware processing |
| Message ký xong bị từ chối signature | Callback/interceptor khác sửa signed part, order sai | Capture security references và callback/interceptor order |
| Chỉ lỗi với SOAP 1.2 | Envelope và media type/action chưa đồng bộ | Message factory, WSDL binding |
| Request nhỏ chạy, MTOM lớn thất bại | Buffer, stream đọc một lần, attachment references/limits | MIME package/Content-ID, memory/disk |
| Callback tạo đúng header nhưng HTTP Basic auth vẫn 401 | Nhầm SOAP Header với HTTP Authorization | Message sender credentials, TLS |
| TLS handshake fail trước SOAP | Truststore/keystore/hostname/mTLS | Transport/certificate, không sửa SOAPAction |
| JAXB marshal lỗi | Không có root element, package sai hoặc javax/jakarta mismatch | Generated model, `JAXBElement`, marshaller |
| SOAP Fault detail chứa secret trong log | Exception logger ghi nguyên response | Redact theo policy hoặc log fault category |
| Retry làm lặp operation | Chưa có idempotency hoặc timeout bị hiểu là “chưa xử lý” | Business operation semantics, request keys |

### 14.1. Quy trình chẩn đoán theo lớp

~~~mermaid
flowchart TD
    A["Call marshalSendAndReceive"] --> B{"Marshal JAXB được?"}
    B -->|Không| C["JAXB root / context path / type"]
    B -->|Có| D{"Callback chạy được?"}
    D -->|Không| E["SOAP message type / DOM / header / action"]
    D -->|Có| F{"Kết nối transport thành công?"}
    F -->|Không| G["URL, DNS, proxy, TLS, auth, timeout"]
    F -->|Có| H{"Đối tác trả SOAP Fault?"}
    H -->|Có| I["Binding/action/QName, XSD, WS-Security, business"]
    H -->|Không| J["Unmarshal response / validate business result"]
~~~

Nên lưu **operation code, request attempt number, phase và error category**, thay vì dump raw SOAP message ở mỗi bước. Một file WSDL đúng hoặc một HTTP 200 riêng lẻ chưa đủ chứng minh hợp đồng và business response đúng.

## 15. Kiểm thử callback ở phía client

Test tốt cần chứng minh **message thực sắp gửi** có đúng SOAPAction, Header QName/nội dung và payload XSD, thay vì chỉ kiểm tra constructor callback chạy không lỗi.

### 15.1. Dùng MockWebServiceServer

Spring-WS test support có `org.springframework.ws.test.client.MockWebServiceServer`; nó có thể chặn một lần gọi `WebServiceTemplate` để kiểm tra request message và trả response giả mà không cần gọi Internet.

Ví dụ minh họa cách kiểm tra **SOAPAction và header presence**; dự án cần dependency `spring-ws-test` (test scope), JAXB model thật và cấu hình `WebServiceTemplate`:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.ws.test.client.ResponseCreators.withPayload;

import java.util.Iterator;
import javax.xml.namespace.QName;

import org.junit.jupiter.api.Test;
import org.springframework.ws.WebServiceMessage;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.soap.SoapHeaderElement;
import org.springframework.ws.soap.SoapMessage;
import org.springframework.ws.test.client.MockWebServiceServer;
import org.springframework.xml.transform.StringSource;

class OrderHeaderCallbackTest {

    @Test
    void sendsExpectedSoapActionAndHeader() {
        WebServiceTemplate template = configuredTemplate();
        MockWebServiceServer server =
                MockWebServiceServer.createServer(template);

        server.expect((WebServiceMessage requestMessage) -> {
            assertInstanceOf(SoapMessage.class, requestMessage);
            SoapMessage soap = (SoapMessage) requestMessage;

            assertEquals(
                "urn:example:orders:v1/GetOrder",
                soap.getSoapAction());

            QName expected = new QName(
                "urn:example:meta:v1", "CorrelationId");

            boolean found = false;
            Iterator<SoapHeaderElement> headers =
                    soap.getSoapHeader().examineAllHeaderElements();

            while (headers.hasNext()) {
                if (expected.equals(headers.next().getName())) {
                    found = true;
                }
            }
            assertTrue(found, "CorrelationId header is missing");
        }).andRespond(withPayload(new StringSource("""
            <o:GetOrderResponse xmlns:o="urn:example:orders:v1">
              <o:orderId>ORD-1001</o:orderId>
              <o:status>PROCESSING</o:status>
            </o:GetOrderResponse>
            """)));

        Object request = generatedJaxbRequest("ORD-1001");
        template.marshalSendAndReceive(
                "https://partner.example.test/soap/orders",
                request,
                new OrderHeaderCallback("TRACE-1001"));

        server.verify();
    }

    // configuredTemplate() và generatedJaxbRequest() là helper
    // ứng dụng phải viết theo XSD/JAXB model và config thật.
}
~~~

Test trên không chạy độc lập nếu chưa cung cấp `configuredTemplate()` và `generatedJaxbRequest()`. Các helper chỉ là cách tránh gắn cứng một XJC output cụ thể vào bài học. `MockWebServiceServer` dùng cùng `WebServiceTemplate`, không thực hiện TLS/HTTP request thật; vì vậy **không** chứng minh mTLS, proxy, Content-Type hay WS-Security interoperability.

Với SOAP header custom, test thêm **nội dung** `CorrelationId` và namespace child, không chỉ test có element. Có thể viết một `RequestMatcher` riêng dùng XPath với namespace map hoặc duyệt SOAP Header DOM theo API message factory phù hợp. Tránh so raw XML string chỉ dựa vào prefix `m` vì prefix có thể khác mà QName không đổi.

### 15.2. Test SOAPActionCallback riêng

Nếu một operation chỉ cần action:

~~~java
MockWebServiceServer server =
        MockWebServiceServer.createServer(template);

server.expect(message -> {
    SoapMessage soap = (SoapMessage) message;
    assertEquals("urn:example:orders:v1/GetOrder",
                 soap.getSoapAction());
}).andRespond(withPayload(new StringSource("""
    <o:GetOrderResponse xmlns:o="urn:example:orders:v1">
      <o:orderId>ORD-1001</o:orderId>
      <o:status>PROCESSING</o:status>
    </o:GetOrderResponse>
    """)));

template.marshalSendAndReceive(
        "https://partner.example.test/soap/orders",
        generatedJaxbRequest("ORD-1001"),
        new SoapActionCallback("urn:example:orders:v1/GetOrder"));

server.verify();
~~~

Đây là mảnh code **dùng trong test đã cấu hình**, cần import/static import như mục 15.1. Nó chứng minh client đặt SOAPAction trên `SoapMessage` được mock server nhận, không thay thế test thực tế về cách HTTP sender biểu diễn header.

### 15.3. Integration test qua HTTP thật

Một test môi trường tích hợp phải kiểm tra:

| Tầng | Cần quan sát |
|---|---|
| HTTP URL | POST đúng endpoint, path và proxy rewriting |
| SOAP version | Envelope namespace và HTTP media type đúng |
| SOAPAction | Giá trị trên wire đúng binding WSDL |
| Business Header | `{urn:example:meta:v1}CorrelationId` có một element, text đúng và được escape |
| WS-Addressing | `wsa:Action`/`To`/`MessageID` đúng contract khi có yêu cầu |
| SOAP Body | `GetOrderRequest` root QName và `orderId` đúng XSD |
| WS-Security | Signature/token/timestamp/attachments được verify đúng |
| TLS | Certificate chain, hostname verification, mTLS nếu yêu cầu |
| Response | Unmarshal được response JAXB và validate business data |
| Fault | Trả SOAP Fault đúng profile khi request sai |
| Logging | Không lộ raw SOAP Body/Header, secret và attachments |

Để kiểm tra actual wire HTTP/SOAP, dùng test server có TLS/soap binding phù hợp, instrumentation ở môi trường test hoặc client phía đối tác cung cấp. Khi lưu fixtures, dùng **giá trị giả**, không chứa secret thật. Một bài test mock có thể pass nhưng gateway trong production vẫn chặn WS-Addressing Header, MIME multipart hoặc TLS certificate.

### 15.4. Test trường hợp header và action không hợp lệ

Nên có các ca âm tính:

- Header namespace URI sai nhưng local name đúng → không coi là header hợp lệ.
- Header thiếu hoặc có hai `CorrelationId` khi contract quy định đúng một → xử lý lỗi.
- SOAPAction không trùng binding WSDL → bên nhận có thể từ chối/route khác tùy stack.
- Body root QName v1/v2 không khớp operation → mapping/XSD failure.
- Header chứa `&` hoặc `<` trong giá trị nghiệp vụ nếu được phép → XML phải được escape đúng.
- Header `mustUnderstand` không được service đích hiểu → xử lý theo SOAP version/profile.
- WS-Addressing Action khác SOAPAction khi policy yêu cầu nhất quán → phải bị phát hiện.
- Chữ ký hợp lệ nhưng sau đó header được chỉnh sửa → kiểm tra integrity/reference policy.
- MTOM attachment lớn và callback log raw XML → thử memory leak/stream consumption trong sandbox.
- Retry khi timeout sau khi đối tác đã xử lý → test idempotency và không lặp side effects.

Không có một mã HTTP cố định cho mọi lỗi trên; quan sát SOAP Fault, transport behavior và WSDL/policy thực tế của hai phía.

## 16. Tình huống thực tế: tích hợp nhiều đối tác SOAP

### 16.1. Bối cảnh

Một ứng dụng Java gọi hai hệ thống:

- **Đối tác A:** SOAP 1.1, WSDL yêu cầu SOAPAction `urn:partner-a:orders:GetOrder` và Header `a:CorrelationId`.
- **Đối tác B:** SOAP 1.2, WS-Addressing Action, ký SOAP Body và một SOAP Header theo WS-SecurityPolicy, dùng mTLS.

Cả hai cùng có request nghiệp vụ “tra cứu đơn hàng”, nhưng **không có nghĩa có thể dùng cùng một callback XML** hoặc cùng message factory/client settings.

Một thiết kế gọn:

~~~mermaid
flowchart TB
    Service["OrderIntegrationService"]
    Service --> A["Partner A client adapter"]
    Service --> B["Partner B client adapter"]
    A --> A1["JAXB model + WebServiceTemplate A"]
    A1 --> A2["SoapActionCallback / business header"]
    A2 --> A3["SOAP 1.1 sender + HTTPS"]
    B --> B1["JAXB model + WebServiceTemplate B"]
    B1 --> B2["WS-Addressing callback + WS-Security interceptor"]
    B2 --> B3["SOAP 1.2 sender + mTLS"]
~~~

Những quyết định cần có:

1. **Hợp đồng riêng:** lưu WSDL/XSD/version và message policies của từng đối tác.
2. **Bean client riêng:** message factory, marshaller, interceptors và message sender phù hợp.
3. **Callback theo operation:** chỉ đặt những headers mà contract yêu cầu, không copy Header A sang B.
4. **Security:** ký/mã hóa theo policy của B, bảo vệ certificate/private key và rotate được.
5. **Error mapping:** chuyển SOAP Fault của từng đối tác sang error model nội bộ ổn định mà không lộ raw Fault.
6. **Tests:** capture request từ cả hai client và thử client/server interoperability độc lập.

### 16.2. Vì sao không làm tất cả bằng một callback khổng lồ?

Một callback tự kiểm tra URI đối tác, đổi SOAP version, thêm headers, tạo UsernameToken, sửa Body và xử lý retry sẽ:

- Làm lẫn trách nhiệm payload/transport/security.
- Khiến unit test khó độc lập với WSDL.
- Dễ tạo lỗi namespace/WS-Addressing Action.
- Có nguy cơ thực hiện security không đúng thứ tự.
- Tăng rủi ro log secret hoặc giữ stream tài liệu lớn trong bộ nhớ.
- Khó quản lý versioning khi một đối tác thay policy.

Nên dùng **client adapter có cấu hình riêng**, callback nhỏ, và các interceptor/transport/security components chuyên biệt. Dù có thể tái sử dụng Java service interface ở tầng domain, phần SOAP contract cần tôn trọng sự khác biệt giữa các đối tác.

## 17. Bài tập thực hành kèm đáp án

### Bài 1 — Chọn extension point

Một operation chỉ cần `SOAPAction="urn:orders:GetOrder"`. Có nên tạo class custom callback dài 100 dòng?

**Đáp án:** Không cần. Dùng `SoapActionCallback` với action lấy từ WSDL binding. Chỉ tạo callback riêng khi có thêm yêu cầu chưa được hỗ trợ bởi callback sẵn có.

### Bài 2 — Header QName sai vì thiếu namespace

Client gửi:

~~~xml
<soapenv:Header
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
  <CorrelationId>TRACE-1001</CorrelationId>
</soapenv:Header>
~~~

Đối tác cần `{urn:example:meta:v1}CorrelationId`. Sai ở đâu?

**Đáp án:** Header gửi đi không có namespace. Phải tạo child element đúng QName bằng `createElementNS` hoặc cơ chế XML marshalling tương đương; không chỉ dùng trùng local name.

### Bài 3 — SOAPAction vs WS-Addressing

Client đã đặt `SoapActionCallback` nhưng đối tác báo thiếu `wsa:Action`. Có mâu thuẫn không?

**Đáp án:** Không. SOAPAction thuộc binding/HTTP đối với SOAP 1.1, còn WS-Addressing Action là SOAP Header trong profile WS-Addressing. Có thể cần `ActionCallback` hoặc cấu hình WS-Addressing tương ứng theo contract.

### Bài 4 — Phân biệt SOAP Header và HTTP Authorization

Client thêm `<Authorization>Bearer ...</Authorization>` vào SOAP Header, nhưng server vẫn trả HTTP 401. Vì sao?

**Đáp án:** HTTP Authorization là HTTP header và do transport/credential mechanism quản lý. SOAP Header tự tạo không tự thay thế nó, cũng không tạo WS-Security authentication hợp lệ.

### Bài 5 — Header bị sửa sau signing

Client ký SOAP Body và header, một interceptor tiếp theo normalize lại giá trị correlation ID. Chữ ký có còn đúng?

**Đáp án:** Có nguy cơ không. Nếu header đó nằm trong signed references, đổi text node có thể phá digest. Phải hoàn thành tạo/chuẩn hóa header theo policy **trước signing** và test signature verification thực.

### Bài 6 — SOAP 1.2

Một ứng dụng đổi `SOAPAction` nhưng vẫn dùng SOAP 1.1 Envelope và `Content-Type: text/xml`. Đối tác chỉ nhận SOAP 1.2. Có đủ không?

**Đáp án:** Không. Cần cấu hình SOAP message factory/binding và transport theo SOAP 1.2, bao gồm Envelope namespace, Content-Type và action semantics đúng profile.

### Bài 7 — JAXB request class không marshal được

XJC sinh `GetOrderRequestType` và `ObjectFactory#createGetOrderRequest(...)`, nhưng client đưa thẳng type vào `marshalSendAndReceive`. Lỗi có thể do đâu?

**Đáp án:** Class type không nhất thiết là root element; cần bọc `JAXBElement` tương ứng hoặc dùng đúng JAXB model do XSD sinh. SOAPAction callback không sửa lỗi JAXB root.

### Bài 8 — MTOM bị ảnh hưởng bởi debug callback

Một callback serialize toàn SOAP request 30 MiB vào `ByteArrayOutputStream` để log. Production phát sinh OOM và file đính kèm bị lỗi đọc lại. Cần làm gì?

**Đáp án:** Bỏ raw payload logging; không đọc toàn message/attachments chỉ để tracing. Đo memory/temp disk, thử MTOM bytes/checksum và kiểm tra behavior message factory/stream lifecycle.

### Bài 9 — Retry và idempotency

`SubmitPayment` trả timeout. Client tự gọi lại với cùng correlation ID mà không có idempotency contract. Có an toàn không?

**Đáp án:** Không thể kết luận. Timeout không chứng minh phía server chưa hoàn tất thanh toán. Cần idempotency key/policy do hai bên thỏa thuận, khả năng query trạng thái và retry có kiểm soát; correlation ID không mặc định là idempotency key.

### Bài 10 — Test callback đủ chưa?

Một unit test gọi `new OrderHeaderCallback("TRACE-1001")` và không bị exception. Có chứng minh request SOAP đúng không?

**Đáp án:** Chưa. Cần dùng `MockWebServiceServer` hoặc message factory để kiểm tra SOAPAction, Header QName/text và payload. Đồng thời kiểm thử HTTP/TLS/WS-Security/MTOM với server hoặc client tương thích thực.

## 18. Checklist và bảng quyết định cuối bài

### Khi viết callback

- [ ] Xác định SOAPAction và SOAP Header requirements từ WSDL/policy thực.
- [ ] Chọn `SoapActionCallback` nếu chỉ cần đặt action.
- [ ] Dùng `WebServiceMessageCallback` cho tùy chỉnh outgoing message theo từng call.
- [ ] Cast `SoapMessage` chỉ khi message factory thực tạo SOAP message.
- [ ] Tạo SOAP Header child bằng QName/namespace đúng; không tạo Envelope/Header lồng.
- [ ] Không ghép raw XML từ input chưa tin cậy; dùng DOM/JAXB và escaping đúng.
- [ ] Callback không chứa mutable shared state của các requests.
- [ ] Không sửa SOAP Body do JAXB marshal nếu không có lý do và kiểm thử contract rõ.
- [ ] Không giả định callback xử lý response/Fault.

### Khi tích hợp enterprise

- [ ] SOAP 1.1/1.2, Content-Type, SOAPAction và WS-Addressing được cấu hình đồng bộ.
- [ ] HTTP credentials, mTLS, proxy, timeout và hostname verification ở đúng transport layer.
- [ ] WS-Security token/signature/encryption do security stack chuyên dụng xử lý.
- [ ] Callback tạo headers trước signing theo thứ tự đã được kiểm chứng.
- [ ] Không chỉnh signed references hoặc attachments sau signing.
- [ ] XML parser/transformer security và hạn mức tài nguyên được cấu hình.
- [ ] Không log SOAP Body, SOAP Header, credentials, private key hay MIME attachments.
- [ ] Có kiểm soát retry và idempotency cho operations có side effects.
- [ ] SOAP Fault được xử lý theo profile, không echo hoặc log detail nhạy cảm.
- [ ] Mỗi đối tác/contract version có client adapter/configuration rõ ràng.

### Khi kiểm thử

- [ ] `MockWebServiceServer` xác minh outgoing SOAPAction và Header QName.
- [ ] Test giá trị header, prefix khác nhau nhưng cùng namespace và text được escape.
- [ ] Test payload JAXB root, schema và WSDL operation thực.
- [ ] Test SOAP Fault và lỗi transport/callback riêng biệt.
- [ ] Test WS-Addressing Action, Timestamp và chữ ký hợp lệ/không hợp lệ.
- [ ] Test MTOM/XOP bytes và memory khi có tài liệu lớn.
- [ ] Test HTTP/TLS/mTLS với endpoint thật hoặc test server đại diện.
- [ ] Test log/trace không chứa synthetic secrets ở success/fault/timeout.
- [ ] Test retry, concurrency và regression khi nâng Spring-WS/JAXB.

| Câu hỏi | Lựa chọn |
|---|---|
| Cần đặt riêng SOAPAction? | `SoapActionCallback` |
| Cần SOAP business Header trên một call? | `WebServiceMessageCallback` |
| Cần WS-Addressing theo policy? | `ActionCallback`/API addressing phù hợp |
| Cần signature/encryption? | WS-Security/WSS4J interceptor |
| Cần HTTP auth, TLS và timeout? | Message sender/transport |
| Cần kiểm tra response, SOAP Fault? | `ClientInterceptor`/fault handling |
| Cần request/response object đúng XSD? | JAXB/OXM + validation |

**Ghi nhớ:** `WebServiceMessageCallback` là hook **tùy chỉnh WebServiceMessage trước khi gửi**, rất hữu ích cho SOAPAction và SOAP Header đặc thù của từng request. Nó không thay JAXB, không tự tạo security policy và không giải quyết transport hay response Fault. Một SOAP client Spring-WS ổn định bắt đầu bằng **XSD/WSDL làm hợp đồng**, dùng callback nhỏ, kiểm soát đúng thứ tự signing, giới hạn dữ liệu nhạy cảm và xác minh bằng test trên message thực.
