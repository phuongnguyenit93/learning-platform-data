# Cấu hình message factory, message sender và bộ ánh xạ OXM

Khi viết **SOAP client** bằng **Spring Web Services (Spring-WS)**, nhiều lập trình viên bắt đầu với một lời gọi `WebServiceTemplate.marshalSendAndReceive(...)`. Lời gọi trông đơn giản, nhưng để giao tiếp thành công, client phải giải quyết đồng thời ba vấn đề: **tạo/đọc thông điệp SOAP**, **gửi/nhận thông điệp qua transport** và **chuyển đổi payload XML với đối tượng Java**. Trong Spring-WS, ba trách nhiệm đó thường tương ứng với **message factory**, **message sender** và **OXM marshaller/unmarshaller**.

Chẳng hạn, một đối tác công bố WSDL dùng SOAP 1.1, yêu cầu chứng chỉ mTLS và nhận `GetOrderRequest` trong namespace `urn:example:orders:v1`. Nếu client dùng SOAP 1.2 factory thì Envelope/Content-Type có thể sai; nếu sender không có truststore hoặc timeout hợp lý thì kết nối thất bại; nếu JAXB context dùng package sinh từ XSD v2 thì payload bị sai QName. Ba lỗi này có biểu hiện rất khác nhau dù xuất phát từ cùng một dòng `marshalSendAndReceive(...)`.

Bài thuộc chương **Máy khách Spring-WS** của module **SPRING_WEB_SERVICES**. Theo định hướng **contract-first**, XSD/WSDL là nguồn sự thật cho thông điệp; JAXB/OXM ánh xạ Java ↔ XML; Spring-WS endpoint/client giao tiếp bằng SOAP. Khi tích hợp doanh nghiệp, client còn phải hiểu SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích. Bài này tập trung vào **cách cấu hình ba thành phần lõi của WebServiceTemplate và kiểm chứng chúng hoạt động cùng nhau**, không chỉ liệt kê các setter.

## 1. Bức tranh tổng thể: ba trục cấu hình độc lập

~~~mermaid
flowchart LR
    A["Java request<br/>GetOrderRequest"] --> O["OXM / JAXB<br/>Marshaller"]
    O --> X["Payload XML<br/>theo XSD"]
    X --> F["WebServiceMessageFactory<br/>SOAP Envelope / Headers"]
    F --> S["WebServiceMessageSender<br/>HTTPS + TLS/mTLS"]
    S --> W["SOAP endpoint<br/>đối tác"]
    W --> S
    S --> R["SOAP response / Fault"]
    R --> F
    F --> U["OXM / JAXB<br/>Unmarshaller"]
    U --> D["Java response<br/>hoặc fault handling"]
~~~

| Thành phần | Công việc chính | Một lựa chọn thường gặp | Không nên kỳ vọng |
| --- | --- | --- | --- |
| **`WebServiceMessageFactory`** | Tạo và đọc SOAP message, Envelope/Header/Body, chọn SOAP version | `SaajSoapMessageFactory` | Không thực hiện HTTP/TLS hay ánh xạ Java fields |
| **`WebServiceMessageSender`** | Kết nối và gửi message qua transport | `HttpUrlConnectionMessageSender`, sender dựa trên Apache HTTP client | Không tự biến đổi JAXB object thành payload XML |
| **`Marshaller`/`Unmarshaller`** | Chuyển Java object ↔ payload XML | `Jaxb2Marshaller` của Spring OXM | Không tự chọn URL, SOAP version hoặc WS-Security policy |
| **`WebServiceTemplate`** | Điều phối ba khâu và xử lý request/response/Fault | Bean Spring hoặc gateway sử dụng template | Không làm đúng hợp đồng khi ba khâu cấu hình sai |

**Một câu dễ nhớ:** message factory quyết định **hình thức thông điệp**, message sender quyết định **đường đi của thông điệp**, OXM quyết định **nội dung payload được chuyển sang Java như thế nào**.

Ba thành phần cần tương thích nhưng có thể được cấu hình, thay thế và kiểm thử tương đối độc lập. Với nhiều endpoint SOAP cùng công nghệ, có thể chia sẻ cấu hình phù hợp; với đối tác khác SOAP version hoặc chứng chỉ, nên có những bean/client settings riêng.

## 2. Phân biệt WSDL URL, SOAP endpoint URL và payload QName

Giả sử đối tác cung cấp:

~~~text
WSDL public:
  https://partner.example.org/ws/orders.wsdl

SOAP endpoint trong wsdl:service/wsdl:port:
  https://partner.example.org/ws

Request payload QName:
  {urn:example:orders:v1}GetOrderRequest

Response payload QName:
  {urn:example:orders:v1}GetOrderResponse
~~~

Các thông tin này có vai trò khác nhau:

- **WSDL URL** là nơi tải mô tả hợp đồng; client có thể dùng nó khi sinh mã hoặc đối chiếu binding.
- **SOAP endpoint URL** là đích gửi request thực tế, thường được ghi trong `soap:address` hoặc `soap12:address` của WSDL.
- **Payload QName** đến từ global elements trong XSD; chúng phải xuất hiện đúng trong SOAP Body.
- **SOAPAction**, nếu WSDL/binding yêu cầu, là metadata action; nó **không thay thế** QName của payload.

Lỗi phổ biến là đặt `WebServiceTemplate.defaultUri` bằng URL `orders.wsdl` rồi POST SOAP lên đó. Một server có thể trả WSDL khi GET tới `.wsdl` nhưng từ chối POST cùng URL. Vì vậy hãy lấy đích thực tế từ **WSDL port/binding đã công bố**, đồng thời xác minh địa chỉ sau reverse proxy.

### 2.1. XSD mẫu dùng xuyên suốt

Ví dụ `src/main/resources/xsd/orders.xsd`:

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

Đây là contract **minh họa**, chưa phải toàn bộ WSDL. XJC có thể sinh Java model với `GetOrderRequest`, `GetOrderResponse`, `OrderStatusType`, `ObjectFactory` và `package-info.java`. Bài giả định generated classes đã được build cùng ứng dụng; bước sinh mã JAXB cần được quản lý bằng công cụ build phù hợp, không sửa generated Java thủ công.

### 2.2. SOAP request được mong đợi

Với SOAP 1.1, thông điệp có thể trông như sau:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1">
    <soapenv:Header/>
    <soapenv:Body>
        <ord:GetOrderRequest>
            <ord:orderId>ORD-1024</ord:orderId>
        </ord:GetOrderRequest>
    </soapenv:Body>
</soapenv:Envelope>
~~~

Phần JAXB chịu trách nhiệm tạo **`ord:GetOrderRequest` trong Body**. SOAP factory chịu trách nhiệm Envelope/Header/Body với **namespace SOAP 1.1**. Sender chịu trách nhiệm gửi message đó đến endpoint qua HTTPS. Cả ba phải nhất quán với WSDL/binding.

## 3. WebServiceMessageFactory là gì?

`WebServiceMessageFactory` trong Spring-WS tạo `WebServiceMessage` mới và đọc message từ dữ liệu transport. Với SOAP, `SoapMessage` là dạng message cung cấp các API như `getSoapHeader()`, `getSoapBody()`, `getSoapAction()`.

Factory **không phải nơi lập trình viên viết business data bằng tay** khi đã có JAXB. OXM chỉ ghi payload XML vào SOAP Body của message do factory tạo. Message factory quyết định các chi tiết SOAP wire format ở tầng thông điệp.

### 3.1. `SaajSoapMessageFactory`

`SaajSoapMessageFactory` tích hợp với SAAJ (SOAP with Attachments API for Java) để tạo và thao tác SOAP messages. Một cấu hình thường gặp:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.soap.saaj.SaajSoapMessageFactory;

@Configuration
public class SoapMessageConfig {
    @Bean
    public SaajSoapMessageFactory soap11MessageFactory() {
        return new SaajSoapMessageFactory();
    }
}
~~~

Trong cấu hình thông dụng, factory SAAJ mặc định tạo SOAP 1.1. Tuy nhiên, **không nên lấy mặc định làm hợp đồng**; hãy kiểm chứng SOAP version thực tế của factory, dependencies SAAJ và WSDL đối tác. Nếu ứng dụng có auto-configuration Spring Boot, việc tự đăng ký một factory bean cần nhất quán với các bean client/server đang sử dụng.

### 3.2. Cấu hình SOAP 1.2 có chủ đích

Một cấu hình độc lập cho SOAP 1.2:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.ws.soap.SoapVersion;
import org.springframework.ws.soap.saaj.SaajSoapMessageFactory;

@Bean
public SaajSoapMessageFactory soap12MessageFactory() {
    SaajSoapMessageFactory factory = new SaajSoapMessageFactory();
    factory.setSoapVersion(SoapVersion.SOAP_12);
    return factory;
}
~~~

Khi factory SOAP 1.2 được chọn đúng, SOAP Envelope sử dụng namespace:

~~~xml
<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope">
    <env:Body>
        <!-- Payload nghiệp vụ -->
    </env:Body>
</env:Envelope>
~~~

SOAP 1.1 có namespace `http://schemas.xmlsoap.org/soap/envelope/` và HTTP Content-Type thường là `text/xml`, còn SOAP 1.2 dùng namespace `http://www.w3.org/2003/05/soap-envelope` và media type HTTP thường là `application/soap+xml`. WSDL SOAP 1.1 và SOAP 1.2 cũng có phần binding tương ứng. **Đừng đổi SOAP version chỉ để tránh một lỗi server** mà không đối chiếu WSDL và policy đối tác.

### 3.3. SAAJ implementation, Javax và Jakarta

Ứng dụng Java hiện đại không nên mặc định JDK tự cung cấp đầy đủ JAXB và SAAJ. Với Spring Framework 6 / Spring-WS thế hệ Jakarta, các API liên quan thường thuộc `jakarta.xml.soap.*` và `jakarta.xml.bind.*`; những ứng dụng Spring đời cũ có thể dùng `javax.xml.soap.*` và `javax.xml.bind.*`.

**Tránh trộn phiên bản Javax và Jakarta**:

- Generated JAXB classes có annotation `javax.xml.bind.annotation.*` không tương đương với class được sinh theo Jakarta JAXB.
- SAAJ API và implementation/provider phải cùng ngăn xếp tương thích.
- Thêm JAXB dependency **không tự bổ sung** SAAJ implementation cần cho SOAP factory.
- Nếu thiếu SAAJ implementation, có thể gặp lỗi khi khởi tạo message factory, trước khi client gửi request.

Trong Maven, nên dùng dependency management/BOM tương ứng Spring Boot/Spring-WS, rồi xác nhận cả **JAXB API/runtime** lẫn **SAAJ API/implementation** có mặt. Không pin những version ngẫu nhiên chỉ vì jar có tên gần giống.

### 3.4. Axiom và chiến lược xử lý XML lớn

Spring-WS có/đã có tích hợp với các message factory khác như Axiom trong những nhánh phiên bản nhất định. Một số giải pháp cho phép xử lý XML/attachment linh hoạt hơn, nhưng **khả năng có sẵn, tên class và cấu hình phụ thuộc phiên bản Spring-WS**. Chỉ chọn Axiom sau khi kiểm tra dependency và tài liệu của phiên bản dự án.

Với XML payload lớn, đừng kết luận đổi factory sẽ tự giải quyết mọi vấn đề: JAXB object graph, DOM transformation, MTOM và giới hạn server vẫn ảnh hưởng bộ nhớ. Hãy đo và thử tải trên SOAP message thực tế.

## 4. WebServiceMessageSender quản lý kết nối tới endpoint

`WebServiceMessageSender` định nghĩa cách gửi `WebServiceMessage` đến một destination. Với SOAP qua HTTP(S), implementation thường chịu trách nhiệm mở kết nối, ghi request bytes và đọc response.

Trong Spring-WS, client không nên tự dùng `HttpURLConnection` để ghép XML bằng string rồi bỏ qua các cơ chế message factory/OXM. `WebServiceTemplate` điều phối sender và cung cấp các extension point cần thiết.

### 4.1. HTTP sender cơ bản

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.ws.transport.http.HttpUrlConnectionMessageSender;

@Bean
public HttpUrlConnectionMessageSender basicHttpSender() {
    return new HttpUrlConnectionMessageSender();
}
~~~

Sender này dùng kết nối HTTP URL của Java và phù hợp để hiểu các khái niệm cơ bản hoặc chạy với cấu hình mạng đơn giản. Nó **không tự giải quyết** connection pooling theo yêu cầu hiệu năng cao, TLS/mTLS trust configuration phức tạp, proxy authentication hay chính sách retry.

### 4.2. Timeout phải được thiết kế rõ

Hai loại timeout thường phải phân biệt:

| Timeout | Ý nghĩa | Lỗi điển hình |
| --- | --- | --- |
| **Connect timeout** | Giới hạn thời gian thiết lập kết nối đến endpoint | Host không phản hồi, firewall drop |
| **Read/response timeout** | Giới hạn thời gian chờ/đọc response sau khi kết nối | Server xử lý lâu, response bị treo |
| **Pool acquisition timeout** (sender có pool) | Chờ lấy connection trong pool | Pool cạn vì tải cao hoặc connection leak |
| **Overall/deadline** | Ngân sách thời gian tổng của một lời gọi nghiệp vụ | Các bước DNS/connect/TLS/write/read cộng dồn vượt SLA |

Tên setter, loại giá trị (`int` milliseconds, `Duration` hoặc cấu hình Apache HTTP client) **khác nhau giữa sender và phiên bản thư viện**. Do đó, hãy xác minh JavaDoc của sender đã chọn trước khi áp cấu hình timeout. Không dùng một `readTimeout` đơn lẻ và cho rằng nó giới hạn **toàn bộ** thời gian trao đổi trong mọi điều kiện.

Ví dụ ý định cấu hình cho một sender hỗ trợ hai timeout:

~~~text
connect timeout:       3 s
response/read timeout: 10 s
total business budget: 12 s
~~~

Các con số chỉ minh họa, không phải khuyến nghị phổ quát. Trong tích hợp thật, cần biết SLA đối tác, retry/backoff, giới hạn connection và thời gian xử lý service.

### 4.3. HTTP sender có pooling

Khi throughput cao hoặc cần kiểm soát connection reuse, dự án có thể chọn sender dùng **Apache HttpClient**. Lưu ý rằng **Spring-WS 3.x, 4.x và các bản tích hợp HttpClient 4/5 không nhất thiết dùng cùng class/API**. Kiểm tra đúng artifact, adapter và cấu hình theo phiên bản; tránh sao chép class name từ ví dụ thuộc thế hệ HttpClient khác.

Một cấu hình pool cần có các giới hạn riêng:

| Thiết lập | Vì sao quan trọng |
| --- | --- |
| Max connections tổng | Tránh bão kết nối tới đối tác |
| Max connections per route | Không để một endpoint chiếm cả pool |
| Connection acquisition timeout | Phát hiện pool bị nghẽn |
| Connection idle/TTL/eviction | Hạn chế connection stale, quản lý tài nguyên |
| TLS context + trust/identity | Sử dụng certificate đúng cho từng đối tác |
| Request/response timeout | Tránh thread treo quá lâu |

**Có pool không đồng nghĩa gọi SOAP idempotent.** Nếu request timeout sau khi server đã xử lý, client không biết chắc đã có side effect hay chưa; retry cần policy nghiệp vụ riêng.

### 4.4. HTTPS, truststore và mTLS

TLS/mTLS là cấu hình của **đường truyền**, thường thuộc sender/HTTP client và môi trường vận hành:

- **Truststore:** dùng để xác minh chứng chỉ máy chủ và chuỗi tin cậy, đồng thời kiểm tra hostname.
- **Keystore/client certificate:** dùng khi đối tác yêu cầu **mTLS**, chứng minh danh tính client ở tầng kết nối.
- **Certificate rotation:** cần quy trình cập nhật material, theo dõi hạn dùng và kiểm thử khi đối tác đổi chứng chỉ.
- **Proxy TLS termination:** bảo đảm phạm vi tin cậy giữa client, gateway và backend được thiết kế rõ.

Không tắt certificate/hostname verification hoặc cài trust-all SSL context để “fix” lỗi kết nối production. Nếu có handshake error, xác minh chain, SAN/hostname, trust anchor, thuật toán hỗ trợ và client certificate được cấp đúng cho môi trường.

**TLS khác WS-Security:** TLS bảo vệ kênh truyền; SOAP signature/encryption với WS-Security bảo vệ thông điệp theo chính sách. Có thể cần cả hai và dùng chứng chỉ/khóa với mục đích khác nhau.

## 5. OXM: chuyển XML payload thành đối tượng Java

**OXM** (Object/XML Mapping) trong Spring định nghĩa các abstraction để marshal và unmarshal dữ liệu XML. Với hợp đồng **XSD trước, code sau**, `Jaxb2Marshaller` thường là lựa chọn trực tiếp: XJC sinh model Java, JAXB runtime ánh xạ object ↔ XML theo annotation và `ObjectFactory`.

### 5.1. `Marshaller` và `Unmarshaller`

| Hướng | Thuật ngữ | Ví dụ |
| --- | --- | --- |
| Java → XML | **Marshalling** | `GetOrderRequest` → `<ord:GetOrderRequest>...` |
| XML → Java | **Unmarshalling** | `<ord:GetOrderResponse>...` → `GetOrderResponse` |

Đối với `WebServiceTemplate`, cần cấu hình cả **marshaller cho request** và **unmarshaller cho response** khi gọi `marshalSendAndReceive(...)`. Thông thường một `Jaxb2Marshaller` có thể đảm nhiệm cả hai chiều, nhưng package/classes được cấu hình phải bao gồm các kiểu cần sử dụng.

### 5.2. JAXB từ XSD, không dựa vào prefix XML

Một số file Java được XJC sinh ra có thể gồm:

~~~text
target/generated-sources/jaxb/
└── org/example/orders/v1/
    ├── GetOrderRequest.java
    ├── GetOrderResponse.java
    ├── OrderStatusType.java
    ├── ObjectFactory.java
    └── package-info.java
~~~

Đây là cấu trúc **minh họa**, không phải tên package mặc định cố định của XJC. `package-info.java` thường khai báo namespace mapping, `ObjectFactory` có thể chứa các khai báo global elements.

Ví dụ:

~~~java
// Minh họa kết quả generated metadata:
@jakarta.xml.bind.annotation.XmlSchema(
    namespace = "urn:example:orders:v1",
    elementFormDefault =
        jakarta.xml.bind.annotation.XmlNsForm.QUALIFIED)
package org.example.orders.v1;
~~~

Một client **không nên đổi prefix** từ `ord` sang `o` rồi nghĩ XML sai hợp đồng. Prefix có thể thay; **QName gồm namespace URI và local name** mới là điều quyết định XML element thuộc đúng XSD hay không.

### 5.3. Cấu hình `Jaxb2Marshaller`

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;

@Configuration
public class OrderOxmConfig {

    @Bean
    public Jaxb2Marshaller orderJaxb2Marshaller() {
        Jaxb2Marshaller oxm = new Jaxb2Marshaller();
        oxm.setContextPath("org.example.orders.v1");
        return oxm;
    }
}
~~~

`setContextPath(...)` yêu cầu context path phù hợp với generated package metadata mà JAXB provider hiểu (thường có `ObjectFactory` hoặc thông tin JAXB tương ứng). **Không dùng XSD namespace URI làm context path**: `urn:example:orders:v1` là XML namespace, còn `org.example.orders.v1` là Java package.

Trong những tình huống khác, `Jaxb2Marshaller` hỗ trợ cách định nghĩa classes/packages bằng `setClassesToBeBound(...)` hoặc `setPackagesToScan(...)` theo version. Chọn một chiến lược nhất quán; nếu schemas có nhiều namespace, đảm bảo context chứa **tất cả classes cần thiết** và không gom các namespace khác nhau thành một package tùy tiện.

### 5.4. `@XmlRootElement`, `ObjectFactory` và `JAXBElement`

XJC không phải lúc nào cũng sinh root class có `@XmlRootElement`. Với một named complex type được tham chiếu bởi global element, mã có thể cần `JAXBElement<T>` từ `ObjectFactory`:

~~~java
// Chỉ là minh họa cho generated model có factory method tương ứng.
GetOrderRequest request = new GetOrderRequest();
request.setOrderId("ORD-1024");

ObjectFactory factory = new ObjectFactory();
JAXBElement<GetOrderRequest> root =
        factory.createGetOrderRequest(request);
~~~

Khi method `marshalSendAndReceive(...)` nhận root object, **phải truyền một đối tượng JAXB có thể marshal thành global element đúng QName**. Nếu lớp có `@XmlRootElement` đúng, có thể truyền trực tiếp; nếu chỉ có type chưa phải element, dùng factory/`JAXBElement` phù hợp.

Khi đọc response, tùy binding, kết quả có thể là `GetOrderResponse` hoặc `JAXBElement<GetOrderResponse>`. Không ép cast cứng trước khi biết JAXB binding thực tế; viết một adapter cho hai dạng nếu contract/toolchain của dự án yêu cầu.

### 5.5. Không nhầm JAXB object hợp lệ với XML hợp XSD

Một generated setter `setOrderId(null)` có thể chấp nhận Java `null` dù XSD yêu cầu `orderId`. JAXB marshalling **không tự đảm bảo** mọi `xs:pattern`, `minOccurs`, `xs:sequence` và constraint đều được kiểm tra nếu chưa cấu hình schema validation.

Điều đó cũng đúng với `xs:decimal`, `xs:dateTime`, enum, absent/nil/default. Nếu contract yêu cầu tính tương thích chặt, cần validation XSD cho payload inbound/outbound ở vị trí thích hợp.

## 6. Cấu hình đầy đủ ba thành phần trong Spring

Ví dụ sau mô tả một SOAP 1.1 client dùng SAAJ, HTTP URLConnection và JAXB. **Đây là cấu hình minh họa có thể hoàn thiện thành ứng dụng**, với giả định đã có JAXB classes từ XSD và dependency tương thích Spring-WS/Jakarta:

~~~java
package org.example.orders.client;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.soap.saaj.SaajSoapMessageFactory;
import org.springframework.ws.transport.http.HttpUrlConnectionMessageSender;

@Configuration
public class OrdersSoapClientConfiguration {

    @Bean
    public SaajSoapMessageFactory ordersSoapMessageFactory() {
        return new SaajSoapMessageFactory(); // SOAP 1.1 trong cấu hình thường gặp
    }

    @Bean
    public HttpUrlConnectionMessageSender ordersHttpSender() {
        return new HttpUrlConnectionMessageSender();
    }

    @Bean
    public Jaxb2Marshaller ordersOxm() {
        Jaxb2Marshaller oxm = new Jaxb2Marshaller();
        oxm.setContextPath("org.example.orders.v1");
        return oxm;
    }

    @Bean
    public WebServiceTemplate ordersWebServiceTemplate(
            SaajSoapMessageFactory ordersSoapMessageFactory,
            HttpUrlConnectionMessageSender ordersHttpSender,
            Jaxb2Marshaller ordersOxm) {

        WebServiceTemplate template = new WebServiceTemplate();
        template.setMessageFactory(ordersSoapMessageFactory);
        template.setMessageSender(ordersHttpSender);
        template.setMarshaller(ordersOxm);
        template.setUnmarshaller(ordersOxm);
        template.setDefaultUri("https://partner.example.org/ws");
        return template;
    }
}
~~~

**Giải thích từng dòng quan trọng:**

| Cấu hình | Vì sao cần |
| --- | --- |
| `setMessageFactory(...)` | Quyết định cấu trúc SOAP message/Envelope được tạo |
| `setMessageSender(...)` | Chọn cách kết nối và gửi request qua HTTP(S) |
| `setMarshaller(...)` | Biến Java request thành XML payload của SOAP Body |
| `setUnmarshaller(...)` | Biến XML response payload thành Java response |
| `setDefaultUri(...)` | Đích SOAP mặc định nếu lời gọi không chỉ rõ URI |

Trong thực tế **không hardcode endpoint URL trong source**. Dùng environment configuration, secret/config management và profile theo môi trường để thay `https://partner.example.org/ws` thành URL đã được cấp cho dev/staging/production. Chứng chỉ, mật khẩu và private key không nằm trong source hoặc log.

### 6.1. Vì sao cần xác nhận lifecycle bean?

`SaajSoapMessageFactory` và `Jaxb2Marshaller` có thể thực hiện khởi tạo tài nguyên trong lifecycle Spring. Khi chúng là các bean do Spring quản lý, framework gọi các bước lifecycle tương ứng. Nếu tạo object thủ công bên ngoài container, cần xác nhận API/lifecycle trước khi dùng; không mặc định factory/provider đã sẵn sàng hoặc JAXBContext đã được khởi tạo.

Nếu project đã có cấu hình Spring Boot tạo `WebServiceTemplateBuilder` hoặc các bean client sẵn, hãy **tích hợp với cấu hình thực tế** thay vì thêm các bean cùng tên/mục đích dẫn đến xung đột dependency injection.

### 6.2. Nhiều SOAP client hoặc nhiều endpoint?

Nếu một ứng dụng gọi hai đối tác:

~~~text
Partner A: SOAP 1.1, HTTPS + mTLS certificate A, JAXB package A
Partner B: SOAP 1.2, HTTPS + WS-Security policy B, JAXB package B
~~~

Không nên dùng một `WebServiceTemplate` singleton rồi liên tục **đổi factory, sender, marshaller và defaultUri** trước từng request. Cách đó vừa gây race condition vừa làm cấu hình khó kiểm toán. Thay vào đó, tạo **hai client beans riêng** với tên qualifier rõ ràng, cấu hình bất biến sau khi khởi tạo.

## 7. Gửi một SOAP request bằng WebServiceTemplate

Với generated `GetOrderRequest` có `@XmlRootElement` đúng, client có thể viết:

~~~java
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.soap.client.core.SoapActionCallback;

public final class OrdersClient {
    private final WebServiceTemplate template;

    public OrdersClient(WebServiceTemplate template) {
        this.template = template;
    }

    public GetOrderResponse getOrder(String orderId) {
        GetOrderRequest request = new GetOrderRequest();
        request.setOrderId(orderId);

        Object raw = template.marshalSendAndReceive(
                request,
                new SoapActionCallback("urn:example:orders:GetOrder"));

        if (!(raw instanceof GetOrderResponse response)) {
            throw new IllegalStateException(
                    "Kiểu response không khớp JAXB contract");
        }
        return response;
    }
}
~~~

Lớp được viết theo Java 16+ (pattern matching trong `instanceof`) và có các imports generated model phụ thuộc dự án. **SOAPAction ở đây là giá trị ví dụ**: chỉ dùng giá trị chính xác WSDL/binding yêu cầu. Nếu JAXB response được unmarshal thành `JAXBElement<GetOrderResponse>`, phải điều chỉnh adapter đọc kết quả theo generated model.

### 7.1. Những gì thực sự diễn ra trong lời gọi

~~~mermaid
sequenceDiagram
    participant App as Application code
    participant T as WebServiceTemplate
    participant O as Jaxb2Marshaller
    participant F as SaajSoapMessageFactory
    participant S as MessageSender
    participant P as SOAP partner
    App->>T: marshalSendAndReceive(request)
    T->>F: Tạo SOAP request message
    T->>O: Marshal request vào Body
    T->>S: Gửi message tới endpoint
    S->>P: HTTPS POST SOAP
    P-->>S: HTTPS SOAP response / Fault
    S-->>T: Dữ liệu response
    T->>F: Đọc SOAP response message
    alt SOAP success
        T->>O: Unmarshal response payload
        O-->>App: GetOrderResponse
    else SOAP Fault
        T-->>App: Fault handling / exception
    end
~~~

Sơ đồ mô tả trách nhiệm, không thể hiện mọi callback nội bộ, interceptor hoặc đường xử lý ngoại lệ của một phiên bản Spring-WS cụ thể.

### 7.2. Truyền URI khác cho một lời gọi

`WebServiceTemplate` hỗ trợ các overload dùng **URI chỉ định trực tiếp**, thay vì dùng `defaultUri`:

~~~java
Object response = template.marshalSendAndReceive(
        "https://partner-staging.example.org/ws",
        request,
        new SoapActionCallback("urn:example:orders:GetOrder"));
~~~

**Không biến URI thành input tùy ý từ người dùng không tin cậy.** Nếu service cho phép client chọn đích HTTP tùy ý, có thể phát sinh SSRF, lộ chứng chỉ client, bearer token hoặc SOAP security headers tới host sai. Chỉ chọn endpoint từ **allowlist/config đã được quản lý**.

### 7.3. Không nhầm SOAPAction với SOAP Header

SOAP 1.1 dùng HTTP `SOAPAction` theo binding. SOAP 1.2 thường sử dụng action parameter trong media type `application/soap+xml`, còn WS-Addressing có `wsa:Action` bên trong SOAP Header. Chúng **không mặc nhiên giống nhau**.

Nếu đối tác yêu cầu một Header `CorrelationId` riêng, dùng SOAP header API/callback thay vì gán `SOAPAction` bằng giá trị correlation.

## 8. Thêm Header khi gửi request

`marshalSendAndReceive(...)` nhận một `WebServiceMessageCallback` để chỉnh sửa message sau khi payload đã được marshal và trước khi gửi. Ví dụ:

~~~java
import javax.xml.namespace.QName;
import org.springframework.ws.soap.SoapHeaderElement;
import org.springframework.ws.soap.SoapMessage;

String correlationId = "req-8f21";
Object response = template.marshalSendAndReceive(
    request,
    message -> {
        if (!(message instanceof SoapMessage soap)) {
            throw new IllegalStateException("SOAP message factory bắt buộc");
        }
        SoapHeaderElement block = soap.getSoapHeader()
                .addHeaderElement(new QName(
                        "urn:example:headers:v1", "CorrelationId"));
        block.setText(correlationId);
        soap.setSoapAction("urn:example:orders:GetOrder");
    });
~~~

Đây là ví dụ SOAP 1.1 với một header ứng dụng **chỉ mang text**. `SoapHeaderElement` giữ QName và SOAP-specific attributes, còn `SoapMessage.setSoapAction(...)` phục vụ action metadata theo implementation/binding.

Một số điểm cần kiểm tra:

- Header `CorrelationId` không tự là chứng cứ xác thực; client có thể tự đặt bất kỳ giá trị nào.
- Nếu contract yêu cầu `mustUnderstand` hoặc actor/role, phải cấu hình đúng SOAP version và receiver capabilities.
- Với header phức tạp, dùng JAXB/XML `Source` thay vì ghép text; kiểm tra namespace và XSD riêng cho Header.
- Nếu có **WS-Security outbound interceptor**, việc ký/mã hóa Header/Body phải xảy ra ở thứ tự phù hợp với policy. Thêm/sửa vùng XML sau khi ký có thể làm chữ ký không hợp lệ.

## 9. Có cần dùng WebServiceGatewaySupport?

Spring-WS cung cấp `WebServiceGatewaySupport` làm lớp cơ sở thuận tiện cho SOAP client. Nó bao bọc `WebServiceTemplate` và các tiện ích cấu hình để code nghiệp vụ có thể gọi `getWebServiceTemplate()`:

~~~java
import org.springframework.ws.client.core.support.WebServiceGatewaySupport;
import org.springframework.ws.soap.client.core.SoapActionCallback;

public class OrdersGateway extends WebServiceGatewaySupport {
    public Object getOrder(GetOrderRequest request) {
        return getWebServiceTemplate().marshalSendAndReceive(
                request,
                new SoapActionCallback("urn:example:orders:GetOrder"));
    }
}
~~~

Khi chọn mô hình này, cần cấu hình marshaller/unmarshaller, factory/sender, default URI cho `WebServiceTemplate` bên trong gateway, hoặc gắn một template đã cấu hình theo API của phiên bản. **Không dùng đồng thời nhiều kiểu cấu hình mà không xác định nguồn cấu hình cuối cùng**.

So sánh:

| Cách viết client | Ưu điểm | Hạn chế |
| --- | --- | --- |
| Inject `WebServiceTemplate` trực tiếp | Phụ thuộc rõ ràng, dễ thay thế trong test, phù hợp composition | Cần viết wrapper/service chứa lời gọi |
| Kế thừa `WebServiceGatewaySupport` | Cung cấp helper API, dùng quen thuộc trong Spring-WS | Class bị ràng buộc framework qua inheritance |
| Tự dùng HTTP client và XML strings | Linh hoạt ở tầng byte/transport | Dễ sai SOAP version, XML namespace, Fault/security; thường không cần |

Với dịch vụ lớn cần nhiều đối tác, **composition với bean template có tên rõ ràng** thường dễ quản lý và test; gateway support vẫn là lựa chọn hợp lệ nếu nhóm đã thống nhất cách dùng.

## 10. Bật schema validation cho bộ ánh xạ OXM

Một ứng dụng cần phát hiện payload sai contract trước khi gửi và khi nhận. `Jaxb2Marshaller` hỗ trợ cấu hình schema:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.ClassPathResource;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;

@Bean
public Jaxb2Marshaller validatedOrdersOxm() {
    Jaxb2Marshaller oxm = new Jaxb2Marshaller();
    oxm.setContextPath("org.example.orders.v1");
    oxm.setSchema(new ClassPathResource("xsd/orders.xsd"));
    return oxm;
}
~~~

Khi schema được cung cấp, JAXB provider có thể sử dụng nó để kiểm tra XML ở các bước marshalling/unmarshalling theo cấu hình Spring-WS/OXM của bản đang chạy. **Phải test cả chiều request và response**, đặc biệt các quy tắc `minOccurs`, `nillable`, `default`/`fixed`, namespace và enum.

Đừng bỏ qua:

1. **XSD import/include:** phải resolve toàn bộ schema graph từ classpath/catalog/resource đáng tin cậy.
2. **XML security:** parser/schema factory phải được làm cứng trước DTD/external entities; `schemaLocation` do input không tin cậy cung cấp không được tùy ý mở truy cập mạng.
3. **Chi phí CPU:** validate mỗi message tiêu tốn tài nguyên; cân nhắc SLA, sampling trong quan sát nhưng không bỏ yêu cầu hợp đồng quan trọng.
4. **Phân biệt validation và business rules:** `orderId` hợp `xs:string` không chứng minh đơn tồn tại hoặc caller được xem đơn.
5. **Header:** validation của payload Body không tự bảo đảm mọi SOAP Header ứng dụng hoặc `wsse:Security` hợp chính sách.

### Không dựa vào getter/setter để validate

Nếu XSD yêu cầu `orderId`, code Java `request.setOrderId(null)` có thể vẫn chạy. Chỉ khi kiểm tra XML cuối cùng theo schema, lỗi thiếu `orderId` mới được phát hiện một cách có căn cứ. Khi client gửi request quan trọng, fail sớm ở phía client trước HTTP POST thường có ích; tuy nhiên server **vẫn phải validate** input, không được tin client đã kiểm tra.

### Nullable, nil và absent vẫn là những trạng thái khác nhau

Một property Java bằng `null` có thể khiến JAXB bỏ element hoặc xuất `xsi:nil="true"` tùy binding; `JAXBElement<T>` có thể giúp phân biệt absent/nilled khi contract cần. Không coi một request object “có kiểu Java đúng” là có XML structure chắc chắn hợp contract.

## 11. SOAP 1.1/1.2, Content-Type và thông điệp lỗi

| Cấu hình | SOAP 1.1 | SOAP 1.2 |
| --- | --- | --- |
| Envelope namespace | `http://schemas.xmlsoap.org/soap/envelope/` | `http://www.w3.org/2003/05/soap-envelope` |
| HTTP Content-Type thường gặp | `text/xml` | `application/soap+xml` |
| Action | HTTP `SOAPAction` theo SOAP binding | `action` parameter, WS-Addressing nếu thỏa thuận |
| SOAP Fault phần tử con | `faultcode`, `faultstring`, `detail` | `Code`, `Reason`, `Detail` |
| Client message factory | Factory SOAP 1.1 | Factory SOAP 1.2 |
| Bảo mật SOAP | Theo policy dịch vụ | Theo policy dịch vụ, không suy từ version |

Mỗi đối tác có thể cung cấp **nhiều WSDL ports** với các bindings khác nhau. Hãy chọn port/endpoint/binding tương ứng **cùng một SOAP version**, rồi test Content-Type, Envelope namespace, SOAPAction/WS-Addressing và Fault model. Không dựa vào tên method Java để suy SOAP version.

**Không nên sửa Content-Type thủ công** bằng HTTP sender để che sai cấu hình message factory. Nếu SOAP 1.2 factory tạo Envelope 1.2 nhưng bạn ép HTTP Content-Type thành `text/xml`, client/server có thể lỗi còn khó chẩn đoán hơn.

## 12. SOAP Fault và exception trên client

`WebServiceTemplate` kiểm tra response để phân biệt SOAP success và Fault. Theo cấu hình mặc định thường gặp, SOAP Fault có thể được chuyển thành `SoapFaultClientException`; những lỗi ở tầng transport/serialization có thể thuộc loại exception khác.

~~~java
import org.springframework.ws.soap.client.SoapFaultClientException;
import org.springframework.ws.client.WebServiceIOException;
import org.springframework.oxm.XmlMappingException;

try {
    GetOrderResponse response = ordersClient.getOrder("ORD-1024");
    // Dùng response cho nghiệp vụ.
} catch (SoapFaultClientException ex) {
    // SOAP Fault đã nhận được.
    var faultCode = ex.getFaultCode();
    String reason = ex.getFaultStringOrReason();
    logSoapFault(faultCode, reason);
} catch (XmlMappingException ex) {
    // XML/JAXB binding có lỗi, ví dụ response không ánh xạ được.
    logMappingFailure(ex);
} catch (WebServiceIOException ex) {
    // Lỗi I/O đường truyền; chưa chắc server đã/ chưa xử lý request.
    logTransportFailure(ex);
}
~~~

Đây là cấu trúc xử lý minh họa: logger/method helper do ứng dụng viết, và **loại exception chính xác phụ thuộc ngữ cảnh/version**. Đừng dựa vào một `catch` duy nhất để phân loại mọi lỗi. `SoapFaultClientException` có thể chứa fault code/reason; nếu client cần đọc typed Fault detail thì phải xây cơ chế đọc XML detail theo XSD/WSDL.

### Retry không chỉ dựa vào Fault Code

- SOAP 1.1 `Client` / SOAP 1.2 `Sender` thường chỉ ra request cần sửa; retry cùng nội dung ít có ích.
- SOAP 1.1 `Server` / SOAP 1.2 `Receiver` có thể liên quan lỗi tạm thời, nhưng không có nghĩa retry an toàn cho operation **có side effect**.
- Timeout hay connection reset **không chứng minh** server chưa nhận request. Có thể đã ghi đơn nhưng client chưa thấy response.
- Với `PlaceOrder`, cần idempotency key, khả năng hỏi trạng thái và transaction phù hợp.
- Với `GetOrder` read-only, retry có thể hợp lý hơn, nhưng vẫn cần timeout, backoff và giới hạn số lần.

Không biến HTTP 502 do proxy thành `SoapFaultClientException` hoặc dùng `faultstring` tiếng Việt để quyết định retry.

## 13. ClientInterceptor và quan sát toàn bộ lời gọi

`ClientInterceptor` cho phép chèn xử lý khi request được gửi, khi response/Fault được nhận và khi hoàn tất. Nó thường phù hợp để thêm Header ứng dụng, correlation ID, đo latency hoặc tích hợp chính sách bảo mật ở **tầng SOAP client**.

Ví dụ interceptor chỉ đo thời gian đơn giản:

~~~java
import org.springframework.ws.client.support.interceptor.ClientInterceptor;
import org.springframework.ws.context.MessageContext;

public final class SoapClientTraceInterceptor implements ClientInterceptor {
    private static final String START =
            SoapClientTraceInterceptor.class.getName() + ".start";

    @Override
    public boolean handleRequest(MessageContext context) {
        context.setProperty(START, System.nanoTime());
        return true;
    }

    @Override
    public boolean handleResponse(MessageContext context) {
        return true;
    }

    @Override
    public boolean handleFault(MessageContext context) {
        return true;
    }

    @Override
    public void afterCompletion(MessageContext context, Exception ex) {
        Object started = context.getProperty(START);
        if (started instanceof Long value) {
            long elapsedNanos = System.nanoTime() - value;
            // Ghi metrics với tags có kiểm soát, không log raw SOAP/token.
            recordDuration(elapsedNanos, ex != null);
        }
        context.removeProperty(START);
    }

    private void recordDuration(long elapsedNanos, boolean hadException) {
        // Gắn vào Micrometer/observability system của ứng dụng.
    }
}
~~~

Đoạn mã dùng Java 16+; `hadException` chỉ cho biết callback nhận exception, **không phải thước đo đầy đủ để kết luận SOAP Fault hay thành công**. Fault có thể đã được framework xử lý theo nhánh riêng. Đối với production metrics, dùng outcome từ response/fault/transport kết hợp với exception theo pipeline thực tế.

Đăng ký:

~~~java
template.setInterceptors(new ClientInterceptor[] {
    new SoapClientTraceInterceptor()
});
~~~

Đây là đoạn cấu hình được đặt trong bước tạo bean template. Khi có **nhiều interceptors**, thứ tự của `handleRequest`, `handleResponse`, `handleFault` và cách xử lý trường hợp một interceptor trả `false` cần được xác minh trên Spring-WS version. Không coi interceptor là nơi thay đổi arbitrary XML sau khi WS-Security đã ký.

## 14. WS-Security outbound và inbound trên SOAP client

Một đối tác có thể yêu cầu:

~~~text
Request:
  SOAP Header có UsernameToken + Timestamp
  SOAP Body phải được ký bởi client certificate
  Có thể phải mã hóa Body bằng public key đối tác

Response:
  Client xác minh chữ ký server và timestamp
  Client giải mã phần được gửi mã hóa theo policy
~~~

**Message factory** tạo SOAP container và cho phép truy cập Header/Body. **Message sender** thiết lập transport (có thể TLS/mTLS). **Security interceptor** thực hiện WS-Security; việc ký/mã hóa không tự xuất hiện chỉ nhờ `Jaxb2Marshaller` hoặc `SaajSoapMessageFactory`.

Trong Spring-WS có thể dùng cơ chế bảo mật dựa trên WSS4J, ví dụ `Wss4jSecurityInterceptor` theo stack tương thích. Cần cấu hình các thông tin cụ thể:

- Trust/key material, username token/nonce và cơ chế xử lý password an toàn.
- Signature algorithms, digest, canonicalization, certificate chain và private key.
- **Những SOAP parts/Headers nào bắt buộc được ký**; tránh signature wrapping.
- Timestamp validity, clock skew, replay cache/nonce theo policy.
- Mã hóa/giải mã, certificate của recipient và thứ tự xử lý thích hợp.
- Security SOAP Fault, audit/logging đã lọc.

**Không dùng đoạn “add `wsse:Security` text” tự chế để thay signature verification.** Một XML Header có tên Security chưa đủ chứng minh tính toàn vẹn, signer identity hay quyền truy cập.

### WS-Security và TLS/mTLS là hai mặt cấu hình khác nhau

| Cơ chế | Vị trí cấu hình điển hình | Mục đích |
| --- | --- | --- |
| TLS trust/hostname verification | HTTP sender/SSL context/gateway | Xác minh server, bảo vệ kênh |
| mTLS client certificate | Sender/SSL context | Xác thực client ở tầng kết nối |
| SOAP Signature | WS-Security stack/interceptor | Kiểm tra toàn vẹn/xác thực thông điệp theo policy |
| SOAP Encryption | WS-Security stack/interceptor | Bảo mật nội dung SOAP qua các chặng được thiết kế |
| Business authorization | Server application/domain | Kiểm tra caller có quyền thực hiện operation |

Các certificate có thể khác mục đích và vòng đời. Một lỗi TLS handshake không phải “SOAP signature invalid” và thường xảy ra trước khi SOAP Fault có thể được đọc.

## 15. MTOM/attachments và thông điệp lớn

Nếu XSD chứa dữ liệu nhị phân, cách truyền payload có thể ảnh hưởng mạnh đến kích thước thông điệp. JAXB có thể ánh xạ `xs:base64Binary` thành `byte[]` hoặc dạng khác tùy binding; inline Base64 làm SOAP XML phình to. **MTOM/XOP** cho phép tối ưu việc đính kèm dữ liệu nhị phân theo binding/phần mềm hai phía hỗ trợ.

`Jaxb2Marshaller` có tùy chọn bật MTOM:

~~~java
Jaxb2Marshaller oxm = new Jaxb2Marshaller();
oxm.setContextPath("org.example.orders.v1");
oxm.setMtomEnabled(true);
~~~

**Bật MTOM ở OXM chưa đủ**: message factory/provider, sender, JAXB mapping, receiver và hợp đồng/policy đối tác đều phải hỗ trợ phù hợp. Kiểm tra Content-Type multipart/related, attachment boundaries, SOAP body XOP references và response decoding trong integration test.

Với file lớn:

- Hạn chế tạo nhiều bản sao `byte[]`/DOM trong bộ nhớ.
- Đặt giới hạn body/attachment size, streaming và timeout tại transport/message factory phù hợp.
- Kiểm thử virus scanning, content type và quyền truy cập nếu là dữ liệu người dùng tải lên.
- Xem WS-Security signature/encryption policy có bao phủ attachments hay không; **MTOM không tự bảo vệ attachment**.

## 16. Kiểm thử client không cần gọi đối tác thật

Spring-WS có **`MockWebServiceServer`** để kiểm thử `WebServiceTemplate` gửi payload đúng và xử lý response/Fault từ fixture.

### 16.1. Test marshal/send/unmarshal

~~~java
import static org.springframework.ws.test.client.RequestMatchers.payload;
import static org.springframework.ws.test.client.ResponseCreators.withPayload;

import org.springframework.xml.transform.StringSource;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.test.client.MockWebServiceServer;

WebServiceTemplate template = ordersWebServiceTemplate;
MockWebServiceServer mock =
        MockWebServiceServer.createServer(template);

String expectedRequest = """
    <ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
      <ord:orderId>ORD-1024</ord:orderId>
    </ord:GetOrderRequest>
    """;

String stubResponse = """
    <ord:GetOrderResponse xmlns:ord="urn:example:orders:v1">
      <ord:orderId>ORD-1024</ord:orderId>
      <ord:status>CONFIRMED</ord:status>
    </ord:GetOrderResponse>
    """;

mock.expect(payload(new StringSource(expectedRequest)))
    .andRespond(withPayload(new StringSource(stubResponse)));

Object response = template.marshalSendAndReceive(
        newOrderRequest("ORD-1024"));

mock.verify();
~~~

Đây là **mẫu test rút gọn**: `ordersWebServiceTemplate`, `newOrderRequest` và các imports phù hợp phải được khai báo trong test fixture; Java text blocks cần Java 15+. Kết quả response nên được assert thành `GetOrderResponse`/`JAXBElement` đúng theo generated bindings; chỉ gọi `mock.verify()` chưa đủ để xác minh toàn bộ nội dung Java trả về.

Mock server giúp kiểm tra **payload Java ↔ XML**, nhưng không tự tạo một TLS handshake thật, không kiểm tra mTLS, proxy timeout hay certificate trust production.

### 16.2. Ma trận kiểm thử ba thành phần

| Nhóm test | Điều cần xác minh | Thành phần có liên quan |
| --- | --- | --- |
| **SOAP 1.1** | Envelope namespace 1.1, Content-Type text/xml | Message factory + sender |
| **SOAP 1.2** | Envelope namespace 1.2, Content-Type application/soap+xml | Message factory + sender |
| **SOAPAction** | Action theo WSDL, không nhầm với Body QName | Callback/message factory |
| **JAXB marshal** | Request XML đúng root, namespace, element order | OXM |
| **JAXB unmarshal** | Response thành Java object đúng kiểu | OXM |
| **Schema invalid** | Request thiếu field, response sai enum bị phát hiện khi validation bật | OXM/schema |
| **SOAP Header** | CorrelationId đúng QName, WS-Security policy được áp dụng | Callback/interceptor |
| **SOAP Fault** | Client phân biệt Fault code/reason/detail | WebServiceTemplate |
| **HTTP timeout** | Sender fail có kiểm soát, không treo vô hạn | Message sender |
| **TLS trust** | Chứng chỉ server không tin cậy bị từ chối | Sender/SSL |
| **mTLS** | Client cert đúng được chấp nhận, cert thiếu/sai bị từ chối | Sender/SSL + server |
| **WS-Security** | Signature, timestamp, encryption policy đúng | Security interceptor |
| **MTOM** | Multipart/attachment XOP theo hợp đồng | OXM + factory + sender |
| **Interop** | Java/.NET/ESB client/server hiểu cùng WSDL và SOAP messages | Toàn pipeline |

### 16.3. Phân biệt test phía client và phía server

- **`MockWebServiceServer`** kiểm tra mã **SOAP client** với `WebServiceTemplate`.
- **`MockWebServiceClient`** kiểm tra **SOAP endpoint server** được Spring-WS đăng ký trong test context.
- Unit test JAXB thuần chỉ kiểm tra phần OXM; nó không đủ khẳng định SOAP Envelope, sender hoặc Fault.
- Integration test thật cần dùng WSDL public, URL đúng sau reverse proxy, TLS/mTLS và WS-Security policy của môi trường tích hợp.

### 16.4. Test nhiều SOAP versions

Không chỉ tạo một fixture XML rồi đổi mỗi prefix. Hãy cấu hình **hai message factories/bindings** khác nhau khi dự án hỗ trợ cả SOAP 1.1 và SOAP 1.2, sau đó kiểm tra:

1. Namespace Envelope.
2. HTTP Content-Type và action semantics.
3. SOAP Fault structure (`faultcode` vs `env:Code`).
4. Sender có đọc response đúng SOAP version hay không.
5. WSDL port và endpoint URL tương ứng.

Nếu đối tác chỉ hỗ trợ một version, tránh “fallback tự động” sang version khác mà chưa có hợp đồng.

## 17. Những lỗi thường gặp và cách xác định đúng thành phần

| Triệu chứng | Khả năng gây ra | Kiểm tra trước |
| --- | --- | --- |
| `SOAP Fault: VersionMismatch` | Message factory tạo Envelope khác SOAP version server hỗ trợ | Namespace Envelope, WSDL SOAP binding, Content-Type |
| `415 Unsupported Media Type` | SOAP 1.1/1.2 Content-Type không khớp | SOAP factory và HTTP headers thực tế |
| `404/405` khi gọi service | POST nhầm `.wsdl` hoặc proxy route sai | `defaultUri` và `soap:address` public |
| `JAXBException: class ... not known to context` | Context path không chứa generated type | `ObjectFactory`, package, JAXB config |
| `missing @XmlRootElement` | Marshal named type không có global element root trực tiếp | `JAXBElement`/factory generated |
| `javax.xml.bind` vs `jakarta.xml.bind` lỗi | Trộn thế hệ XJC/API/runtime | Dependency graph, generated annotations |
| `SAAJ provider not found` | Thiếu hoặc sai SAAJ implementation | Message factory/API/provider dependency |
| SOAP request có QName sai | Generated package/binding namespace sai | XSD, `package-info.java`, serialized payload |
| SSL handshake/PKIX error | Truststore/cert chain/hostname/mTLS sai | Sender TLS/SSL context và chứng chỉ |
| Connection timeout | Endpoint không reachable, firewall/DNS/proxy | Network + sender connect timeout |
| Response timeout | Server chậm hoặc read timeout quá ngắn | Sender/read timeout, SLA và server tracing |
| Pool exhausted | Pool sizing/connection leak hoặc tải cao | Sender Apache/pool metrics |
| Response unmarshal lỗi | XML response sai XSD hoặc binding phiên bản khác | OXM, schema validation, actual SOAP XML |
| Client báo `SoapFaultClientException` | Server đã gửi SOAP Fault | Fault Code/Detail, nghiệp vụ/security |
| HTTP 502 nhưng không có Fault | Gateway/proxy không tạo SOAP Envelope | Transport logs, upstream health |
| Chữ ký SOAP sai | Header/Body bị sửa sau ký, signed parts không đúng | WS-Security interceptor order |
| Attachment không đọc được | MTOM config không đồng bộ hai phía | OXM, factory, multipart binding |

### Một sơ đồ chẩn đoán có thể lặp lại

~~~mermaid
flowchart TD
    A["Client gọi SOAP"] --> B{"Kết nối HTTPS thành công?"}
    B -->|Không| C["Sender / DNS / proxy / TLS/mTLS"]
    B -->|Có| D{"Server nhận đúng SOAP version?"}
    D -->|Không| E["Message factory, Content-Type, WSDL binding"]
    D -->|Có| F{"Payload QName/XSD đúng?"}
    F -->|Không| G["JAXB/OXM, ObjectFactory, generated types"]
    F -->|Có| H{"WS-Security và SOAPAction đạt?"}
    H -->|Không| I["Security interceptor, header/action policy"]
    H -->|Có| J{"SOAP response hoặc Fault?"}
    J -->|Fault| K["Đọc Fault Code/Detail, phân loại lỗi"]
    J -->|Success| L["JAXB unmarshal, response validation"]
~~~

Đây là sơ đồ **chẩn đoán từ phía client**, không phải thứ tự callback cố định tại server. Nếu client đã nhận SOAP Fault nhưng Java cast response sai, điều tra OXM; nếu chưa thiết lập TLS, sửa generated JAXB class sẽ không giải quyết vấn đề.

## 18. Bài thực hành tự đánh giá

### Bài 1 — Cấu hình SOAP 1.1 client

Dùng XSD `orders.xsd` để sinh JAXB model, tạo ba bean riêng: `SaajSoapMessageFactory` SOAP 1.1, `HttpUrlConnectionMessageSender`, `Jaxb2Marshaller`. Gắn chúng vào `WebServiceTemplate` cùng SOAP endpoint URL. Gửi `GetOrderRequest` và kiểm tra XML Body QName.

### Bài 2 — SOAP 1.2 và lỗi VersionMismatch

Tạo message factory SOAP 1.2 và gửi tới test endpoint chỉ hỗ trợ SOAP 1.1. Ghi lại Envelope namespace/Content-Type và Fault hoặc transport error nhận được. Giải thích vì sao không thể sửa lỗi bằng cách đổi `SOAPAction` hay prefix XML.

### Bài 3 — Chọn JAXB root đúng

Chỉnh XSD để global element tham chiếu một named complex type; sinh lại model và xem `ObjectFactory`. Nếu class không có `@XmlRootElement`, dùng `JAXBElement<T>` đúng QName rồi kiểm tra marshalling.

### Bài 4 — Phân biệt transport, OXM và Fault

Cho ba lỗi: thiếu SAAJ provider, TLS handshake fail và response có `ord:status` ngoài enum. Đặt mỗi lỗi vào factory/sender/OXM, và nêu log/kiểm thử thích hợp.

### Bài 5 — Cấu hình mTLS và WS-Security

Thiết kế sender sử dụng client certificate và truststore tin cậy. Đồng thời chỉ ra vị trí cấu hình WS-Security signature, timestamp và kiểm tra signed parts. Giải thích vì sao có mTLS chưa đủ đáp ứng SOAP signature policy.

### Bài 6 — Chạy MockWebServiceServer

Viết test `MockWebServiceServer` kiểm tra payload của `GetOrderRequest` và trả `GetOrderResponse`. Assert Java response, thêm một test SOAP Fault, rồi bổ sung kiểm tra SOAP Header `CorrelationId`. Không chỉ test getter/setter generated class.

### Bài 7 — Timeout và retry

Đối tác chậm, client timeouts xảy ra sau một operation `PlaceOrder`. Thiết kế retry policy với backoff, idempotency key và khả năng truy vấn trạng thái. Giải thích vì sao timeout không chứng minh server chưa xử lý lệnh.

### Bài 8 — So sánh hai đối tác

Với Partner A (SOAP 1.1, mTLS) và Partner B (SOAP 1.2, WS-Security + MTOM), thiết kế các bean template riêng. Chỉ ra những thành phần có thể chia sẻ, những thành phần phải tách riêng và các integration tests cần có.

## 19. Checklist trước khi đưa SOAP client vào production

| Nhóm kiểm tra | Điều kiện đạt |
| --- | --- |
| **Contract** | WSDL/XSD đúng phiên bản, đủ import/include, SOAP port/operation được xác nhận |
| **Endpoint** | `defaultUri` trỏ SOAP endpoint public, không nhầm WSDL URL; proxy route đúng |
| **Message factory** | SOAP 1.1/1.2, Envelope namespace, provider SAAJ tương thích |
| **Transport sender** | Connect/read/pool timeouts, proxy, TLS trust, hostname verification, mTLS đúng |
| **OXM** | JAXB generated types, context path, `ObjectFactory`, `JAXBElement`, Javax/Jakarta nhất quán |
| **Validation** | Request/response XML hợp XSD, null/nil/default theo contract |
| **SOAP Headers** | SOAPAction/WS-Addressing/CorrelationId theo đúng binding và QName |
| **Security** | WS-Security tokens, signature, encryption, timestamp, certificates, replay và signed parts đúng |
| **Fault** | Phân biệt SOAP Fault, HTTP error, timeout và unmarshalling error |
| **Reliability** | Retry idempotent, backoff, circuit breaker và giới hạn concurrency khi phù hợp |
| **MTOM** | Chỉ bật khi cả hai phía hỗ trợ, giới hạn attachment và kiểm tra bảo mật |
| **Testing** | MockWebServiceServer, schema tests, SOAP versions, TLS/mTLS và interop thực tế |
| **Observability** | Correlation ID, metrics theo lỗi, log đã lọc, không lộ token/password/raw XML nhạy cảm |

**Kết luận:** Cấu hình SOAP client trong **SPRING_WEB_SERVICES** cần ba mảnh ghép rõ ràng: **message factory** tạo/đọc SOAP Envelope đúng phiên bản, **message sender** vận chuyển thông điệp qua HTTP(S) cùng TLS/mTLS, timeout và connection management, còn **OXM** ánh xạ payload XML theo XSD sang/về JAXB classes. `WebServiceTemplate` kết nối các thành phần đó thành một client hoạt động, nhưng không thay thế WSDL contract, schema validation, SOAP Fault handling hay WS-Security. Khi phân biệt đúng trách nhiệm, quản lý cấu hình theo đối tác và kiểm thử XML/SOAP thực tế, nhóm có thể xây dựng SOAP client đáng tin cậy, dễ quan sát và tương thích với các hệ thống doanh nghiệp.
