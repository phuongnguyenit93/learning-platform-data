# Lựa chọn Axiom và streaming theo khả năng hỗ trợ của phiên bản

**Spring Web Services (Spring-WS)** giúp xây dựng dịch vụ SOAP theo hướng **contract-first**: thiết kế XSD/WSDL, ánh xạ JAXB, xây dựng `@Endpoint` và SOAP client, xử lý SOAP Fault, interceptor, XML security, WS-Security và kiểm thử tương thích. Khi dung lượng SOAP Body tăng hoặc thông điệp có attachment, một quyết định kiến trúc quan trọng là **dùng bộ tạo thông điệp SAAJ mặc định hay chuyển sang Axiom để tận dụng xử lý XML kiểu streaming**.

Không nên quyết định chỉ bằng khẩu hiệu “streaming nhanh hơn và tiết kiệm RAM”. Cần trả lời đồng thời:

1. **Phiên bản Spring-WS, Spring Boot, Java/Jakarta và thư viện Apache Axiom đang dùng có hỗ trợ API dự kiến không?**
2. **Ứng dụng có đọc payload nhiều lần không?** Endpoint mapping, schema validation, tracing, SOAP logging và security interceptor có thể cần đọc trước hoặc sau handler.
3. **Mục tiêu streaming ở đâu?** Đọc request, sinh response, xử lý attachment hay toàn bộ luồng truyền HTTP? Mỗi phần có khả năng buffering riêng.
4. **Kết quả đo hiệu năng và kiểm thử contract/security chứng minh được lợi ích trong tải thực tế không?**

Bài này thuộc chương **Kiến trúc xử lý**, dùng ví dụ tạo đơn hàng `CreateOrderRequest` trong namespace `urn:example:orders:v1`. Các API và cấu hình được minh họa theo **những phiên bản Spring-WS có hỗ trợ tương ứng**; cần kiểm tra lại Javadoc và dependency đúng version đang triển khai, không áp dụng máy móc cho mọi phiên bản.

## 1. Vị trí của message factory trong kiến trúc Spring-WS

SOAP không được trao thẳng vào method Java. Trước khi `@Endpoint` chạy, hệ thống phải tạo và đọc một `WebServiceMessage` từ byte HTTP rồi xử lý các lớp protocol.

~~~mermaid
flowchart TD
    A["HTTP(S) POST + SOAP bytes"] --> B["MessageDispatcherServlet / Transport"]
    B --> C["WebServiceMessageFactory"]
    C --> D["SoapMessage / Envelope + Header + Body"]
    D --> E["MessageDispatcher"]
    E --> F["EndpointMapping / EndpointInterceptor"]
    F --> G["EndpointAdapter, JAXB or XML Source"]
    G --> H["@Endpoint + Business Service"]
    H --> I["SOAP Response or SOAP Fault"]
    I --> J["Factory / serializer / HTTP(S) response"]
~~~

`WebServiceMessageFactory` tạo thông điệp trống khi cần phản hồi và đọc thông điệp từ `InputStream` cho yêu cầu đến. Với SOAP, hai triển khai quan trọng để đánh giá là:

- `org.springframework.ws.soap.saaj.SaajSoapMessageFactory`: dựa trên **SAAJ** (SOAP with Attachments API for Java), xử lý thông điệp theo mô hình cây XML, thường phải giữ đáng kể nội dung trong bộ nhớ.
- `org.springframework.ws.soap.axiom.AxiomSoapMessageFactory`: dựa trên **Apache AXIOM** (AXis Object Model), xây dựng trên **StAX/pull parsing**, có thể trì hoãn việc dựng cây và hỗ trợ các cách đọc/ghi theo luồng.

Khác biệt nằm ở **biểu diễn và vòng đời message**; XSD/WSDL của đối tác không tự động thay đổi khi đổi factory. Tuy nhiên, phần mềm có thể phụ thuộc hành vi đọc nhiều lần của DOM, vì vậy thay factory là một thay đổi kiến trúc cần kiểm thử.

### 1.1. Lớp nào xử lý nhiệm vụ nào?

| Thành phần | Chức năng | Tác động tới streaming |
| --- | --- | --- |
| `MessageDispatcherServlet`, transport | Nhận HTTP(S), tạo message context, đưa yêu cầu vào dispatcher. | HTTP request có thể được buffer bởi proxy, servlet container hoặc sender. |
| `WebServiceMessageFactory` | Chọn cách biểu diễn/parse SOAP message. | SAAJ và Axiom có đặc tính bộ nhớ, caching và serializer khác nhau. |
| `EndpointMapping` | Chọn endpoint bằng QName payload, SOAPAction hoặc tiêu chí khác. | Đọc QName đầu Body có thể tiêu thụ stream khi không cache. |
| `EndpointInterceptor` | Validation, logging, tracing, WS-Security, biến đổi payload. | Có thể đọc/biến đổi XML trước hoặc sau endpoint. |
| `EndpointAdapter`, `Jaxb2Marshaller` | Chuyển payload XML thành Java và ngược lại. | Có thể marshal/unmarshal qua stream, nhưng object Java vẫn tốn bộ nhớ. |
| `@Endpoint` và business service | Xử lý logic, truy cập DB, xây response. | Có thể tự tạo danh sách dữ liệu lớn dù transport streaming. |
| HTTP message sender, server container | Gửi/nhận byte HTTP, TLS và MIME. | Buffering, compression và chunking ảnh hưởng bộ nhớ/độ trễ thực tế. |

**Phân biệt hai tầng:** dùng StAX để parse payload không có nghĩa toàn bộ SOAP Envelope, object JAXB, chữ ký XML, attachment và HTTP request được xử lý hoàn toàn *zero-copy*.

## 2. SAAJ và Axiom khác nhau như thế nào?

### 2.1. SAAJ: lựa chọn đơn giản khi cần truy cập và chỉnh sửa message

SAAJ hoạt động theo mô hình cây SOAP/XML; khi message được dựng trong bộ nhớ, nhiều thao tác truy cập Header, Body, Fault hoặc node có thể thuận tiện hơn cho logging và interceptors.

~~~text
HTTP InputStream
  → SAAJ SOAPMessage / XML tree
  → EndpointMapping, Interceptor, JAXB/DOM
  → Response SOAP tree
  → HTTP OutputStream
~~~

Điểm mạnh thường gặp:

- Tương thích với các pipeline cần kiểm tra nhiều lần SOAP Body và Header.
- Dễ khởi đầu với cấu hình Spring-WS cơ bản và các công cụ dựa vào cây XML.
- Thích hợp cho payload vừa/nhỏ khi bộ nhớ và độ trễ đạt yêu cầu.

Đánh đổi: nhiều XML nodes và object có thể tồn tại đồng thời; payload lớn, nhiều request song song hoặc attachment có thể tạo áp lực heap/GC. Tuy nhiên **không có số liệu cố định** chứng minh SAAJ luôn chậm hơn Axiom trong mọi môi trường; đo bằng phiên bản và workload thực tế.

### 2.2. Axiom: StAX và xây dựng cây theo nhu cầu

Apache Axiom sử dụng mô hình object XML có khả năng đọc kiểu pull qua StAX. Trong Spring-WS, `AxiomSoapMessageFactory` cung cấp một `SoapMessage` có thể tiết kiệm chi phí dựng/giữ toàn bộ payload khi cấu hình và cách sử dụng phù hợp.

~~~text
HTTP InputStream
  → AxiomSoapMessage / StAX
  → [cache payload?] → endpoint/interceptors
  → [stream response?] → HTTP OutputStream
~~~

Hai đặc tính cần tách biệt:

- **Streaming khi đọc request**: ảnh hưởng bởi `payloadCaching` và việc payload được truy cập bao nhiêu lần.
- **Streaming khi viết response**: có thể sử dụng khả năng của `StreamingWebServiceMessage`/`StreamingPayload` trong luồng response được Spring-WS adapter hỗ trợ, nhưng chưa chắc mọi kiểu handler hoặc mỗi tầng transport đều stream.

Axiom **không thay thế** JAXB, XSD validation, SOAP Fault hay WS-Security. Cùng một schema với `<ord:CreateOrderRequest>...` có thể đi qua SAAJ hoặc Axiom; dữ liệu XML cuối cùng vẫn phải khớp QName và binding SOAP.

### 2.3. Bảng lựa chọn sơ bộ

| Tiêu chí | SAAJ | Axiom, `payloadCaching=true` | Axiom, `payloadCaching=false` |
| --- | --- | --- | --- |
| Mô hình XML | Chủ yếu cây DOM/SAAJ. | AXIOM/StAX có cache payload. | Đọc body trực tiếp từ stream, một lần. |
| Có thể đọc Body nhiều lần? | Thường phù hợp. | Có thể truy cập payload đã cache. | **Không được giả định** có lần đọc thứ hai. |
| `@PayloadRoot` / mapping đọc Body | Phù hợp thông thường. | Thường phù hợp; cần test đúng stack. | **Không phù hợp** theo Javadoc Axiom factory. |
| `PayloadValidatingInterceptor` | Có thể dùng. | Có thể dùng theo cấu hình và test. | **Không phù hợp** nếu cần đọc payload trước handler. |
| `PayloadLoggingInterceptor` | Có thể dùng. | Có thể dùng theo cấu hình và test. | **Không phù hợp** nếu tiêu thụ payload. |
| SOAPAction-based routing | Có thể dùng. | Có thể dùng. | Là hướng mapping không cần đọc Body mà Javadoc khuyến nghị. |
| Lợi ích bộ nhớ | Dễ dự đoán với tải vừa; có thể tốn heap. | Có thể giảm một phần chi phí tùy workload. | Có thể giảm peak heap/độ trễ đọc, với ràng buộc nghiêm ngặt. |
| Độ phức tạp vận hành | Thường thấp hơn. | Cần thêm dependency/config/benchmark. | Cần rà soát toàn pipeline, tránh đọc lại stream. |

**Kết luận sơ bộ:** nếu project dùng `@PayloadRoot` cùng logging và validation payload như nhiều ứng dụng Spring-WS contract-first, **đừng bật `payloadCaching=false` chỉ vì thấy tùy chọn này tồn tại**. Cần chọn mapping/processing khác hoặc giữ caching; lợi ích chỉ có ý nghĩa khi được chứng minh bằng test.

## 3. Kiểm tra khả năng hỗ trợ theo đúng phiên bản

Vì lớp SOAP factory, dependency và hành vi streaming có thể thay đổi theo release, không thể chọn Axiom chỉ từ tên công nghệ.

### 3.1. Các mốc và điều gì đã được tài liệu hóa?

| Phạm vi tài liệu | Thông tin có thể xác nhận | Lưu ý áp dụng |
| --- | --- | --- |
| **Spring-WS 4.1.4** | Javadoc có `AxiomSoapMessageFactory` và các setter `setPayloadCaching`, `setAttachmentCaching`, `setAttachmentCacheDir`, `setAttachmentCacheThreshold`, `setSoapVersion`. | Đọc API của **4.1.4**; đặc biệt đọc cảnh báo “payload only once”. |
| **Spring-WS 5.0.0-M1** | Javadoc còn mô tả package `org.springframework.ws.soap.axiom` cùng `AxiomSoapMessageFactory`; tài liệu tham khảo mô tả streaming. | Mốc **milestone**, không đại diện cho mọi patch/nhánh tương lai. |
| **Ứng dụng dùng 4.x/5.x hoặc nhánh khác** | Cần kiểm tra artifact thực, Javadoc đúng version, Spring Boot BOM, Java/Jakarta và Axiom runtime. | Không lấy việc một class tồn tại ở bản khác làm bằng chứng cấu hình hiện tại hoạt động. |

Các nguồn API chính thức dùng để kiểm tra:

- [Spring-WS 4.1.x — AxiomSoapMessageFactory Javadoc](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/soap/axiom/AxiomSoapMessageFactory.html).
- [Spring-WS 4.1.4 — Reference, message factories](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/).
- [Spring-WS 5.0.0-M1 — Axiom package Javadoc](https://docs.spring.io/spring-ws/docs/5.0.0-M1/api/org/springframework/ws/soap/axiom/package-summary.html).

Những liên kết này xác nhận **khả năng đã được công bố trong mốc cụ thể**, không thay thế việc đối chiếu artifact và release notes của version dự án. Ví dụ không được suy rằng vì `AxiomSoapMessageFactory` tồn tại ở mốc 5.0.0-M1 thì mọi phiên bản 5.x đều có cùng constructor, dependency hay tính năng hoạt động giống hệt.

### 3.2. Quy trình kiểm tra trước khi bật Axiom

1. **Chốt đúng version** `spring-ws-core`, Spring Framework, Spring Boot và runtime Java bằng dependency tree/lockfile của dự án.
2. Mở **Javadoc đúng version** để kiểm tra class `org.springframework.ws.soap.axiom.AxiomSoapMessageFactory`, setters, interface và cảnh báo hạn chế.
3. Kiểm tra dependency của Apache Axiom và JAXB/Jakarta XML Binding có được kéo vào đúng phiên bản tương thích không; tránh trộn các phiên bản Axiom/Activation giữa transitive dependencies.
4. Xác định đang dùng **SOAP 1.1 hay 1.2** từ WSDL binding, không quyết định chỉ từ code factory.
5. Kiểm tra integration giữa factory với **server side**, **client side**, interceptors, security, attachment và serializer.
6. Chạy kiểm thử functional/contract với thông điệp nhỏ, vừa, lớn, SOAP Fault và concurrency; chỉ sau đó benchmark bộ nhớ/độ trễ.

Nếu lớp Axiom **không tồn tại** ở artifact đang triển khai, hoặc version được hỗ trợ chính thức trong tổ chức không có dependency thích hợp, chọn `SaajSoapMessageFactory` hoặc thiết kế streaming khác được chứng minh là tương thích. Đừng copy class từ JAR khác vào runtime để “bổ sung support”.

### 3.3. Phân biệt hỗ trợ API với hỗ trợ vận hành

Một compile pass chỉ chứng minh import/method tồn tại. “Hỗ trợ” trong môi trường production còn đòi hỏi:

- Message factory khởi tạo được dưới JDK hiện tại.
- SOAP Envelope, QName và SOAPAction tương thích WSDL/client.
- Interceptors, JAXB unmarshalling, validation, SOAP Fault và WS-Security chạy đúng.
- Không tăng đột biến heap, memory off-heap, GC hoặc tiêu thụ đĩa khi tải lớn.
- Có giới hạn kích thước request và quản lý attachment an toàn.

**Không nhận xét “Axiom hỗ trợ streaming” như một tuyên bố rằng tất cả các tính năng Spring-WS đều stream được đồng thời.**

## 4. Cấu hình factory: bắt đầu từ chế độ an toàn để so sánh

Ví dụ Java configuration sau chỉ áp dụng khi phiên bản Spring-WS có `AxiomSoapMessageFactory` và dependency Apache Axiom tương thích trong runtime classpath.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.soap.SoapVersion;
import org.springframework.ws.soap.axiom.AxiomSoapMessageFactory;

@Configuration
public class SoapMessageConfig {

    @Bean(name = "messageFactory")
    public AxiomSoapMessageFactory soapMessageFactory() {
        AxiomSoapMessageFactory factory =
                new AxiomSoapMessageFactory();

        factory.setSoapVersion(SoapVersion.SOAP_11);

        // Mac dinh true: giu kha nang truy cap lai payload.
        factory.setPayloadCaching(true);
        return factory;
    }
}
~~~

Đoạn code minh họa **một bean duy nhất** tên `messageFactory`; không đăng ký đồng thời hai bean cùng tên. Tùy cấu hình Spring Boot/Spring-WS, auto-configuration có thể đã tạo message factory; khi chuyển backend cần hiểu cơ chế bean được chọn thay vì thêm bean mà không biết dispatcher hoặc client có thực sự sử dụng nó không.

**Lưu ý phạm vi:** đăng ký `messageFactory` trong ApplicationContext của server có thể ảnh hưởng message factory mà `MessageDispatcherServlet` tìm. Client `WebServiceTemplate` có thể có instance/factory riêng; muốn client thực sự dùng Axiom, phải kiểm tra hoặc cấu hình `WebServiceTemplate#setMessageFactory(...)` với bean tương ứng. Đừng kết luận server/client đều dùng Axiom chỉ vì thấy một dòng `@Bean`.

### 4.1. Đối chứng SAAJ

Đối chứng đơn giản (chọn **thay thế** bean Axiom, không dùng cùng lúc với tên `messageFactory`):

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.ws.soap.SoapVersion;
import org.springframework.ws.soap.saaj.SaajSoapMessageFactory;

@Bean(name = "messageFactory")
public SaajSoapMessageFactory soapMessageFactory() {
    SaajSoapMessageFactory factory =
            new SaajSoapMessageFactory();
    factory.setSoapVersion(SoapVersion.SOAP_11);
    return factory;
}
~~~

Cùng `orders.xsd` và WSDL, hai factory phải tạo/đọc SOAP message nhất quán. Kiểm thử cả request thành công, response, SOAP Fault, SOAP Header, SOAP 1.1/1.2 nếu có đối tác dùng nhiều binding.

### 4.2. Bật `payloadCaching=false` có chủ đích, không mặc định

Chỉ xem xét cấu hình dưới đây **sau khi đã xác nhận tất cả thành phần đọc payload trong pipeline**:

~~~java
AxiomSoapMessageFactory factory =
        new AxiomSoapMessageFactory();
factory.setPayloadCaching(false);
~~~

Theo Javadoc 4.1.x, mặc định `payloadCaching=true`; khi chuyển sang `false`, SOAP Body được đọc trực tiếp từ stream và **chỉ được đọc một lần**. Những thành phần như sau **không tương thích với chế độ này khi chúng cần đọc Body trước handler**:

- `PayloadRootAnnotationMethodEndpointMapping`: phân tích QName của payload để quyết định gọi endpoint nào.
- `PayloadValidatingInterceptor`: đọc payload để kiểm tra XSD.
- `PayloadLoggingInterceptor`: đọc payload để log nội dung.
- Các transform/interceptor tự định nghĩa truy cập `getPayloadSource()` hoặc `getPayloadResult()` làm stream bị tiêu thụ hay thay đổi.

Đây không chỉ là vấn đề “log sẽ bị thiếu”. Nếu mapping đọc stream trước khi JAXB adapter unmarshal, endpoint có thể nhận payload rỗng, nhận lỗi parser hoặc xử lý sai dù HTTP request ban đầu hoàn toàn hợp lệ.

Javadoc đề xuất hướng **mapping dựa trên SOAPAction** để tránh đọc Body khi chọn endpoint, chẳng hạn `SoapActionAnnotationMethodEndpointMapping`. Điều này không đồng nghĩa mọi thành phần khác tự động tương thích; vẫn phải bảo đảm không ai đọc lại stream trước khi handler thực sự tiêu thụ nó.

### 4.3. Trường hợp routing bằng `@SoapAction`

Nếu hợp đồng WSDL 1.1 định nghĩa:

~~~xml
<soap:operation soapAction="urn:example:orders:v1/CreateOrder"/>
~~~

thì có thể xem xét handler với annotation SOAPAction (đây là **đoạn tập trung vào mapping**, giả định kiểu request/response và JAXB adapter đã được cấu hình):

~~~java
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;
import org.springframework.ws.soap.server.endpoint.annotation.SoapAction;

@Endpoint
public class OrderEndpoint {

    @SoapAction("urn:example:orders:v1/CreateOrder")
    @ResponsePayload
    public CreateOrderResponse create(
            @RequestPayload CreateOrderRequest request) {
        // Xu ly va tra response.
        return new CreateOrderResponse();
    }
}
~~~

**Không dùng đoạn này như cấu hình production hoàn chỉnh.** Tên class JAXB phụ thuộc XSD và có thể cần `JAXBElement`; phải kiểm tra `SoapActionAnnotationMethodEndpointMapping` được đăng ký/ưu tiên phù hợp trong phiên bản dự án và endpoint mapping khác không consume Body trước đó. Với SOAP 1.2, action thường thể hiện qua media type `application/soap+xml` và binding khác; không dùng ví dụ SOAP 1.1 như bảo đảm tương thích SOAP 1.2.

Routing SOAPAction có thêm rủi ro: header/action có thể thiếu, rỗng, hoặc không thống nhất giữa client và WSDL. Vì vậy cần xác định action từ **hợp đồng thực tế** và kiểm thử đầy đủ trước khi đánh đổi cách mapping theo QName.

## 5. Truy cập stream một lần: điều gì gây lỗi?

Một đường đi thường gặp trong hệ thống contract-first là:

~~~mermaid
sequenceDiagram
    participant HTTP as HTTP request
    participant F as Axiom factory
    participant M as PayloadRoot mapping
    participant V as XSD/Logging interceptor
    participant J as JAXB adapter
    HTTP->>F: SOAP byte stream
    F->>M: getPayloadSource()
    Note over M: Đọc QName từ Body
    M->>V: tiếp tục dispatch
    V->>J: validation/logging có thể đọc Body
    Note over J: Unmarshal cần đọc payload
    J-->>HTTP: Lỗi khi stream đã bị tiêu thụ
~~~

Sơ đồ minh họa **nguy cơ** khi `payloadCaching=false`, không phải thứ tự bắt buộc của mọi interceptor. Một khi XML parser đã kéo qua các sự kiện StAX của request, không thể giả định phía sau có thể quay lại vị trí đầu mà không có cơ chế lưu/cache hoặc một bản sao message.

### 5.1. Những thao tác cần kiểm tra trong code

| Thao tác | Có nguy cơ tiêu thụ/tạo bản sao payload? | Kết luận khi non-caching |
| --- | --- | --- |
| `message.getPayloadSource()` rồi transform/parse | Có; phụ thuộc cách Source được xử lý. | Cần chứng minh chỉ có **một consumer** theo luồng. |
| Log nguyên XML SOAP Body | Thường có. | Không phù hợp nếu handler còn phải unmarshal sau log. |
| Validate Body theo XSD ở interceptor | Có. | Không phù hợp với non-caching nếu lại cần unmarshal. |
| Chọn endpoint bằng QName trong Body | Có thể đọc đầu stream. | Javadoc cảnh báo `PayloadRootAnnotationMethodEndpointMapping`. |
| Chọn endpoint bằng SOAPAction của Header HTTP | Không cần đọc Body để chọn handler. | Có thể phù hợp hơn, nhưng phải kiểm tra các bước còn lại. |
| JAXB unmarshalling của Body tại endpoint | Có, đây thường là lần tiêu thụ chính. | Phải bảo đảm stream còn nguyên và adapter tương thích. |
| WS-Security verify signature XML | Có thể đòi truy cập toàn message/nhiều nodes. | Không mặc định hoạt động với non-caching; test từng policy. |

### 5.2. Không nên “chữa” bằng cách vô tình buffer toàn bộ XML

Một số giải pháp tạm thời đọc nguyên stream thành `String` hoặc `byte[]` để các interceptor đọc lại. Cách đó có thể khiến pipeline hoạt động, nhưng **vô hiệu hóa phần lớn mục tiêu tiết kiệm bộ nhớ**. Thậm chí có thể tạo nhiều bản sao đồng thời: raw bytes + Java String + DOM + JAXB objects + log buffer.

Nếu yêu cầu bảo mật, validation và logging thực sự cần nhiều lần đọc, hãy cân nhắc:

- Giữ `payloadCaching=true` và đánh giá lợi ích khác của Axiom.
- Dùng SAAJ nếu tổng thể đơn giản và benchmark đạt yêu cầu.
- Thay cách quan sát bằng log **metadata**: correlation ID, SOAPAction, QName, kích thước, latency, faultcode (không log nguyên Body).
- Tách một luồng xử lý đặc biệt cho message lớn nếu hợp đồng cho phép và endpoint mapping không cần đọc Body.
- Chuyển dữ liệu khối lớn sang attachment/MTOM hoặc giao thức phù hợp khi cần, thay vì ép mọi dữ liệu vào một chuỗi XML cực lớn.

**Không tắt XSD validation hoặc WS-Security chỉ để tăng thông lượng** nếu đó là yêu cầu an toàn/hợp đồng. Khi không thể đáp ứng hai mục tiêu cùng lúc, phải ưu tiên tính đúng và có phương án kiến trúc khác.

## 6. Streaming của response: có nhưng không phải mọi phản hồi đều zero-buffer

`AxiomSoapMessage` triển khai `StreamingWebServiceMessage`, và Spring-WS có khái niệm `StreamingPayload` để ghi payload trực tiếp vào output khi response được xuất. Tài liệu tham khảo mô tả luồng response streaming có thể được dùng với handler trả về đối tượng được JAXB hỗ trợ.

Ví dụ đường đi ý tưởng:

~~~text
Endpoint trả Java response/JAXB
   → EndpointAdapter/Marshaller
   → StreamingPayload (khi adapter và message hỗ trợ)
   → AxiomSoapMessage.writeTo(OutputStream)
   → HTTP response stream
~~~

Giá trị của cách này: ở điều kiện thích hợp, không cần dựng trước toàn bộ DOM của Body response rồi mới ghi byte ra socket.

Tuy nhiên, cần kiểm tra tất cả điểm có thể làm materialize payload:

1. **Đối tượng response Java**: nếu endpoint tạo `List<OrderItem>` 500.000 phần tử, danh sách đã nằm trong heap trước khi marshal; message streaming không làm biến mất nó.
2. **Marshaller và adapter**: cần đúng dạng handler trả về/kiểu JAXB mà version Spring-WS hỗ trợ; không phải mọi `Source` hoặc custom return value đều được tự động stream.
3. **SOAP Header và WS-Security**: ký toàn phần Body, canonicalization, encryption hoặc transform có thể buộc giữ material trong bộ nhớ.
4. **HTTP stack**: servlet container, proxy hoặc gateway có thể buffer response, nén hoặc đổi transfer encoding; việc Axiom stream ở tầng XML không chứng minh client nhận từng byte ngay lập tức.
5. **Error handling**: khi đã ghi một phần body ra output, không phải lúc nào có thể thay thế phản hồi bằng SOAP Fault hoàn chỉnh nếu lỗi xảy ra muộn.

Do đó benchmark nên xem **peak heap, thời gian bắt đầu gửi byte, tổng latency, tỷ lệ lỗi và khả năng rollback khi marshal thất bại**, không chỉ nhìn tốc độ của `writeTo` trong unit test.

### 6.1. Streaming không thay đổi quy tắc SOAP Fault

SOAP 1.1 Fault nằm trong `soap:Body` và có các thành phần như `faultcode`, `faultstring`, `detail`; SOAP 1.2 có cấu trúc Fault khác. Việc response được stream không cho phép gửi XML không well-formed hay một phần của một Envelope rồi đổi ý giữa chừng.

Nếu endpoint có thể phát lỗi khi truy xuất dữ liệu lớn, nên phát hiện/validate các lỗi dự đoán được **trước khi bắt đầu ghi response** khi kiến trúc cho phép. Đừng giả định mọi exception trong giai đoạn stream đều được exception resolver chuyển thành Fault hợp lệ sau khi HTTP response đã committed.

## 7. Attachment và MTOM: một bài toán streaming khác với SOAP Body

Nhiều hệ thống doanh nghiệp chuyển tài liệu PDF, ảnh hóa đơn hoặc dữ liệu nhị phân qua SOAP. Nếu nhúng base64 trực tiếp vào `soap:Body`, dung lượng dữ liệu tăng và parser có thể phải xử lý chuỗi XML rất lớn. **MTOM/XOP** cho phép truyền dữ liệu nhị phân bằng MIME parts trong những trường hợp hợp đồng và hai đầu hỗ trợ.

### 7.1. Axiom có cơ chế cache attachment xuống đĩa

Ở các phiên bản có hỗ trợ như Spring-WS 4.1.x, `AxiomSoapMessageFactory` cung cấp:

- `setAttachmentCaching(boolean)`: cho phép lưu những attachment lớn trên đĩa theo cấu hình; mặc định của property được Javadoc mô tả là `false`.
- `setAttachmentCacheThreshold(int)`: ngưỡng kích thước byte sử dụng cho cơ chế cache attachment.
- `setAttachmentCacheDir(File)`: thư mục lưu cache, mặc định tùy implementation/cấu hình (thường từ temp directory).

Ví dụ **cấu hình minh họa**, chỉ chọn khi môi trường có volume đủ dung lượng, quyền phù hợp và vòng đời cleanup đã được kiểm thử:

~~~java
import java.io.File;
import org.springframework.ws.soap.axiom.AxiomSoapMessageFactory;

AxiomSoapMessageFactory factory =
        new AxiomSoapMessageFactory();

factory.setPayloadCaching(true); // Khong doi stream request.
factory.setAttachmentCaching(true);
factory.setAttachmentCacheThreshold(1024 * 1024);
factory.setAttachmentCacheDir(
        new File("/var/app/soap-attachment-cache")
);
~~~

**Điều kiện thực tế:** thư mục phải tồn tại, writable với tài khoản tiến trình và có chính sách hạn mức, cleanup, mã hóa/kiểm soát truy cập nếu chứa dữ liệu nhạy cảm. Đường dẫn `/var/app/...` chỉ là ví dụ cho một môi trường Linux; Windows/container/managed hosting cần cấu hình path riêng. Không dùng `setAttachmentCaching(true)` như một bảo đảm tự động giải quyết giới hạn bộ nhớ hoặc tạo “streaming end-to-end”.

### 7.2. MTOM, attachment caching và payload caching là ba khái niệm

| Khái niệm | Đang tối ưu phần nào? | Không giải quyết điều gì? |
| --- | --- | --- |
| `payloadCaching=false` | Cách đọc **SOAP Body XML** của Axiom. | Không tự cấu hình attachment, security hay giới hạn request size. |
| `attachmentCaching=true` | Cách lưu **MIME attachments**, có thể chuyển dữ liệu lớn sang disk. | Không khiến mọi node trong SOAP Body đọc được nhiều lần. |
| MTOM/XOP | Biểu diễn/truyền **dữ liệu nhị phân** kèm SOAP theo hợp đồng. | Không tự bảo đảm client/server đều hỗ trợ, không thay XSD/WSDL/security policy. |

Khi benchmark attachment, đo đồng thời heap, disk space, I/O, cleanup và độ trễ. Nếu gateway giới hạn `Content-Length` hoặc tổng MIME body, attachment vẫn có thể bị từ chối dù code Java dùng Axiom.

## 8. Tương thích với validation, SOAP Header và WS-Security

Trong dự án contract-first, kiểm tra XSD và bảo mật message không phải lựa chọn tùy ý. Đặc biệt khi tích hợp hệ thống doanh nghiệp, server có thể yêu cầu:

- Kiểm tra `CreateOrderRequest` hợp lệ theo XSD, bao gồm `xs:sequence`, `enumeration` và miền giá trị.
- Đọc custom SOAP Header để lấy correlation ID hoặc WS-Addressing.
- Kiểm tra `wsse:Security`, timestamp, token, XML Signature/Encryption và chứng chỉ.
- Ghi audit metadata, ánh xạ exception sang SOAP Fault, chống replay hoặc giới hạn resource.

Các thao tác này có thể cần truy cập một phần hoặc toàn bộ nội dung SOAP nhiều lần. **Không coi chúng mặc nhiên tương thích với Axiom không cache**. Với chữ ký số, việc canonicalization, reference resolution hoặc xử lý policy có thể cần biểu diễn DOM/đệm dữ liệu; hãy xác nhận bằng end-to-end test trên stack WS-Security thực tế.

### 8.1. Tổ hợp tính năng và lựa chọn ban đầu

| Tính năng đang dùng | Điểm rủi ro với streaming | Lựa chọn khởi đầu nên thử |
| --- | --- | --- |
| `@PayloadRoot` định tuyến theo Body | Mapping đọc payload trước adapter. | SAAJ hoặc Axiom với `payloadCaching=true`. |
| `PayloadValidatingInterceptor` | Đọc Body trước khi JAXB unmarshalling. | Giữ caching, không bỏ validation tùy tiện. |
| `PayloadLoggingInterceptor` | Đọc Body để log XML. | Giữ caching hoặc thay bằng log metadata phù hợp. |
| SOAPAction routing không đọc Body | Có thể giúp dùng stream một lần. | Cân nhắc Axiom `false` khi các bước khác cũng tương thích. |
| WS-Security chữ ký/mã hóa | Có thể materialize Body, cần truy cập các nodes. | Test với chế độ caching và policy thực. |
| Payload phản hồi lớn | JAXB object và HTTP/proxy có thể vẫn buffer. | Đo Axiom response streaming trên handler thực. |
| Attachment/MIME lớn | Giới hạn heap và disk. | Axiom attachment caching/MTOM nếu đúng contract. |
| SOAP Fault/response mutation | Response có thể đã được commit. | Test lỗi khi chưa/đang serialize; tránh hỏng Envelope. |

Một interceptor ghi log `getPayloadSource()` “cho dễ debug” trong development có thể khiến non-caching chạy được ở môi trường không bật log nhưng thất bại ở production khi thêm tracing/security. Cần kiểm thử **đúng cấu hình interceptor của từng môi trường**, không chỉ unit test factory.

### 8.2. Bảo vệ XML parser và nguồn dữ liệu ngoài

SOAP parser xử lý input từ mạng không tin cậy phải chống XXE/DTD, external entity resolution và entity expansion theo các khả năng thật của parser/stack. Một số bản Axiom có các setter liên quan `setSupportingExternalEntities` và `setReplacingEntityReferences`, nhưng tên thuộc tính tồn tại **không đồng nghĩa mọi đường XML parser đã an toàn**.

Ví dụ minh họa thể hiện ý định chính sách:

~~~java
factory.setSupportingExternalEntities(false);
~~~

Cần đối chiếu Javadoc đúng version và kiểm thử XML độc hại trong môi trường được phép. Với hệ thống có XSD import hợp lệ, hãy dùng schema resolver được kiểm soát thay vì mở truy cập external entity tùy ý.

Không được thay kiểm soát bảo mật đầu vào bằng `payloadCaching=false`. Dù dữ liệu được đọc theo luồng, một request quá lớn vẫn có thể tiêu tốn CPU, I/O, bộ nhớ, thời gian thực thi hoặc làm đầy đĩa attachment cache.

## 9. Giới hạn kích thước thông điệp: bài học bảo mật theo phiên bản

Một vấn đề cần kiểm tra đặc biệt ở các phiên bản Spring-WS được triển khai cuối năm 2026 là **CVE-2026-59349 — Spring Web Services Memory Consumption via Oversized Incoming Messages**, công bố ngày **19/11/2026**.

Theo [advisory chính thức của Spring](https://spring.io/security/cve-2026-59349/), các factory `SaajSoapMessageFactory`, `AxiomSoapMessageFactory` và `DomPoxMessageFactory` ở một số version có thể tiếp nhận thông điệp HTTP quá lớn mà không có giới hạn mặc định trong chính factory, làm tiêu thụ bộ nhớ tỷ lệ với lượng dữ liệu gửi đến. Advisory nhấn mạnh rủi ro khi server nhận request HTTP từ bên không tin cậy và **không có request-body limit ở phía trước**.

| Phạm vi trong advisory | Trạng thái được nêu |
| --- | --- |
| Spring-WS `5.0.0–5.0.3` | Nằm trong các phiên bản bị ảnh hưởng. |
| Spring-WS `4.1.0–4.1.4` | Nằm trong các phiên bản bị ảnh hưởng. |
| Spring-WS `4.0.0–4.0.19` | Nằm trong các phiên bản bị ảnh hưởng. |
| Spring-WS `3.1.9` trở về trước | Nằm trong các phiên bản bị ảnh hưởng theo advisory. |
| Các bản fix được liệt kê | `5.0.4` (OSS), `5.0.3.1` (Enterprise), `4.1.5` (Enterprise), `4.0.20` (Enterprise), `3.1.10` (Enterprise). |

Bảng là tóm tắt **advisory theo thời điểm biên soạn**, không khẳng định tất cả phiên bản fix đã sẵn có qua mọi kênh phát hành tại thời điểm đọc bài. Hãy kiểm tra release thực tế, hỗ trợ thương mại và bản vá áp dụng cho môi trường.

Các phiên bản đã được vá theo advisory tăng cường giới hạn factory với mặc định **10 MB** và property `maxMessageSize` có thể được điều chỉnh. **Không copy `setMaxMessageSize(...)` vào code dùng version cũ** nếu Javadoc/class chưa có method này; trước tiên xác nhận phiên bản đã được vá. Khi ứng dụng cần hợp lệ xử lý message lớn hơn giới hạn, việc nâng giới hạn phải đi kèm thiết kế capacity và test.

Nếu chưa nâng cấp được:

1. Đặt **request-body size limit** trên reverse proxy, API gateway hoặc lớp tiếp nhận trước Spring-WS.
2. Kiểm tra hạn mức ở nhiều tầng: server container, request timeout, connection limit, MIME attachment limit, queue/backpressure.
3. Áp dụng xác thực/authorization và giới hạn concurrency phù hợp với rủi ro dịch vụ.
4. Theo dõi heap, GC, I/O đĩa, số request lớn bị từ chối và log audit đã lọc.
5. Lập kế hoạch cập nhật bản vá, kiểm thử lại XSD/JAXB, SOAP Fault và WS-Security khi nâng cấp.

**Thông điệp chính:** Axiom streaming là phương án hiệu năng, **không phải lá chắn DoS**. Một request ngoài giới hạn vẫn phải được từ chối tại ranh giới đáng tin cậy; việc có buffer hay không không thay thế hạn mức kích thước.

## 10. Đo hiệu năng đúng cách trước khi quyết định

Không chọn Axiom chỉ vì `payloadCaching=false` có vẻ nhanh hơn trong một benchmark cực nhỏ. Kết quả phải đại diện cho tải hệ thống của bạn.

### 10.1. Bốn cấu hình/kiểu kiểm thử nên so sánh

| Cấu hình thử nghiệm | Điều kiện | Mục tiêu kiểm tra |
| --- | --- | --- |
| A: SAAJ với pipeline hiện có | Giữ `@PayloadRoot`, validation, logging/security. | Đường baseline đúng chức năng. |
| B: Axiom, `payloadCaching=true` | Pipeline và hợp đồng giống A. | Khác biệt hiệu năng/bộ nhớ mà không bỏ các bước đọc Body. |
| C: Axiom, `payloadCaching=false` | Chỉ khi routing/handler/interceptor tương thích, ví dụ mapping SOAPAction. | Lợi ích streaming request và tính đúng sau một lần đọc. |
| D: Axiom với attachment caching hoặc MTOM | Chỉ khi hợp đồng có MIME attachment/MTOM. | Heap, disk, latency và cleanup với dữ liệu nhị phân. |

Không coi A/B/C là “cùng một điều kiện” nếu C phải tắt validation/security hoặc đổi ý nghĩa hợp đồng. Muốn benchmark công bằng, **yêu cầu bảo mật và chức năng phải tương đương**, hoặc ghi rõ trade-off thay vì công bố C “nhanh hơn”.

### 10.2. Dữ liệu và chỉ số cần thu thập

Tạo bộ test đại diện: request nhỏ (vài KB), trung bình (vài trăm KB), lớn (một vài MB), payload có danh sách dài, request không hợp lệ XSD, SOAP Fault và attachment theo giới hạn cho phép.

Với mỗi mức tải, đo:

- **Throughput**: số SOAP requests/giây khi đúng contract.
- **Latency**: p50, p95, p99 và thời gian đến byte đầu tiên của response (nếu đo được).
- **Peak heap** và phân bổ object: với GC log/profiler phù hợp, theo dõi memory allocation rate và số lần/duration GC.
- **RSS/off-heap và temp disk**: đặc biệt khi SOAP attachment được cache ngoài heap.
- **Tính đúng**: response XML/namespace, SOAP Fault, XSD validation và WS-Security có còn đúng không?
- **Ổn định khi concurrency**: số request đồng thời, queue length, timeout, retry, backpressure và tỉ lệ lỗi.

Nhớ giữ nguyên phiên bản JDK, container limits, TLS, HTTP keep-alive, parser, JVM flags và kích thước request giữa các lần đo. Kết luận có giá trị khi các mẫu tải đủ đại diện và lặp lại, chứ không phải từ một lần chạy duy nhất.

### 10.3. Phân tích kết quả trước khi tối ưu

| Quan sát | Cách diễn giải có cơ sở |
| --- | --- |
| Axiom true dùng ít heap hơn SAAJ, chức năng đúng | Có thể cân nhắc áp dụng Axiom không đổi routing/validation. |
| Axiom false nhanh nhưng mất validation hoặc route sai | Kết quả **không thể chấp nhận** dù throughput cao. |
| CPU/GC không đổi nhưng temp disk tăng mạnh | Đã chuyển chi phí sang I/O; cần tính giới hạn dung lượng và vận hành. |
| Response stream nhưng p99 tăng | Có thể do marshalling, HTTP buffering, backpressure, network hoặc security; phải profile thêm. |
| Một SOAP message lớn gây OOM dù dùng Axiom | Cần kiểm tra giới hạn size, vật liệu hóa JAXB, security transforms và attachment buffering. |
| Log đầy đủ XML làm hiệu năng giảm | Có thể thay bằng metrics + metadata đã lọc, tùy yêu cầu audit. |

## 11. Quy trình ra quyết định để dùng trong dự án

~~~mermaid
flowchart TD
    A["Cần tối ưu SOAP memory/latency?"] --> B{"Version hỗ trợ Axiom + dependency hợp lệ?"}
    B -- "Không hoặc chưa xác minh" --> S["SAAJ / nâng cấp được hỗ trợ"]
    B -- "Có" --> C{"Pipeline đọc Body nhiều lần?"}
    C -- "Có" --> D["Thử Axiom payloadCaching=true"]
    C -- "Không" --> E["Thử Axiom payloadCaching=false"]
    D --> F["Kiểm thử XSD / WS-Security / Fault / tải lớn"]
    E --> F
    F --> G{"Đạt tính đúng, an toàn, hiệu năng?"}
    G -- "Không" --> S
    G -- "Có" --> H["Chọn cấu hình, đặt limits, theo dõi production"]
~~~

**Bước 1 — Chốt contract và runtime.** Xác nhận SOAP 1.1/1.2, WSDL/XSD, JAXB version, Spring-WS artifact, Axiom runtime và JVM. Nếu chưa khớp, chưa nên thay message factory.

**Bước 2 — Liệt kê tất cả consumer của payload.** Xem endpoint mapping, validation interceptor, logging/trace, Wss4jSecurityInterceptor và custom handlers. Đặc biệt chú ý việc **cùng một request bị parse nhiều lần**.

**Bước 3 — Thử cấu hình ít rủi ro.** So sánh SAAJ với Axiom `payloadCaching=true`. Nếu pipeline đã hoạt động đúng, không tự loại bỏ validation và security để bật non-caching.

**Bước 4 — Chỉ thử non-caching khi có điều kiện.** Dùng mapping không đọc Body trước handler, kiểm tra toàn bộ interceptor và lỗi phát sinh khi stream không thể replay.

**Bước 5 — Tối ưu hướng dữ liệu.** Nếu payload lớn vì dữ liệu nhị phân, kiểm tra MTOM/attachment caching; nếu do danh sách dữ liệu, xét phân trang hoặc API trao đổi theo lô nếu hợp đồng cho phép.

**Bước 6 — Đặt an toàn làm cổng quyết định.** Giới hạn message size và concurrency, xác thực, secure XML parser, test security, Fault, retry và compatibility.

**Bước 7 — Đo và ghi quyết định.** Lưu version, cấu hình bean, test matrix và số liệu benchmark. Theo dõi sau khi phát hành để phát hiện thay đổi hành vi do nâng cấp dependency.

## 12. Bài thực hành: chọn cấu hình phù hợp trong bốn hệ thống

### Tình huống A — Service đơn hàng thông thường

Hệ thống dùng `@PayloadRoot`, `PayloadValidatingInterceptor`, `PayloadLoggingInterceptor` và JAXB endpoint. Mỗi SOAP Body chỉ vài KB.

**Đáp án gợi ý:** ưu tiên SAAJ nếu đã ổn định; khi cần tối ưu, thử Axiom `payloadCaching=true` trong cùng pipeline. `payloadCaching=false` không phù hợp với các thành phần hiện có theo Javadoc. Đo trước khi thêm phức tạp.

### Tình huống B — Gửi nhận hóa đơn PDF dung lượng lớn

SOAP Body nhỏ chứa metadata, attachment có thể vài chục MB, phải gửi qua MTOM theo contract.

**Đáp án gợi ý:** kiểm tra khả năng MTOM/XOP và compatibility của hai đầu, đánh giá Axiom attachment caching xuống disk nếu phiên bản hỗ trợ. Giới hạn kích thước request và temp disk vẫn cần có; không đồng nhất attachment caching với `payloadCaching=false`.

### Tình huống C — Ingest XML lớn nhưng cần XSD validation và WS-Security signature

Có yêu cầu audit nghiêm ngặt, inbound XML phải validate XSD và xác minh chữ ký trước khi xử lý.

**Đáp án gợi ý:** không bật non-caching nếu các thành phần đọc Body nhiều lần; giữ caching hoặc chọn SAAJ, đo chi phí thật. Khi throughput không đạt, cân nhắc thiết kế luồng/chia batch/hợp đồng thay vì vô hiệu hóa validation/chữ ký.

### Tình huống D — SOAPAction routing và handler chỉ đọc Body một lần

WSDL 1.1 yêu cầu SOAPAction cố định, server có mapping theo SOAPAction, không log nguyên Body, không dùng interceptor cần đọc trước và không có policy security buộc đọc lại payload.

**Đáp án gợi ý:** có thể thử Axiom `payloadCaching=false` nếu phiên bản và stack thực hỗ trợ. Kiểm tra SOAPAction thiếu/sai, response/Fault, malformed XML, timeout, concurrency và khả năng cleanup tài nguyên trước khi chọn.

### Câu hỏi tự kiểm tra

1. `AxiomSoapMessageFactory` và `SaajSoapMessageFactory` khác nhau ở đâu trong `WebServiceMessageFactory`?
2. Vì sao một endpoint `@PayloadRoot` có thể gặp lỗi khi `payloadCaching=false` dù XML request đúng XSD?
3. Tại sao `PayloadValidatingInterceptor` và `PayloadLoggingInterceptor` có thể xung đột với non-caching?
4. SOAPAction routing giúp giải quyết vấn đề nào, và có rủi ro hợp đồng gì?
5. Vì sao Axiom stream output không bảo đảm toàn bộ danh sách JAXB không chiếm heap?
6. Attachment caching xuống disk có thay thế request-size limit không?
7. Cần kiểm tra gì trước khi dùng `maxMessageSize` trong code của một bản Spring-WS cũ?
8. Khi đổi message factory, những ca test về WS-Security, SOAP Fault, SOAP 1.2 và client compatibility nào là bắt buộc?

### Ghi nhớ

- **Chọn theo version thực tế**: class `AxiomSoapMessageFactory`, setters, dependency Apache Axiom và tích hợp Spring/Jakarta phải được xác nhận ở artifact đang triển khai.
- **SAAJ và Axiom không tự thay đổi contract** XSD/WSDL, nhưng khác cách lưu và đọc XML trong message.
- **`payloadCaching=false` là quyết định kiến trúc lớn**: payload chỉ đọc một lần; theo Javadoc nó không phù hợp với `PayloadRootAnnotationMethodEndpointMapping`, `PayloadValidatingInterceptor` và `PayloadLoggingInterceptor` khi các thành phần đó đọc Body.
- **Streaming request, streaming response, MTOM và attachment caching là các cơ chế khác nhau**, không bảo đảm “toàn bộ hệ thống zero-buffer”.
- **Không hy sinh validation hoặc WS-Security** chỉ vì benchmark; kiểm tra routing, Fault, XML security và compatibility trong pipeline thực tế.
- **Giới hạn kích thước request là bắt buộc về vận hành** cho dịch vụ nhận dữ liệu không tin cậy, kể cả khi dùng Axiom; đối chiếu advisory và bản vá của phiên bản đang chạy.
- **Quyết định cuối cùng dựa trên số liệu**: throughput, p95/p99, peak heap, GC, temp disk, lỗi SOAP và bảo mật phải được đo trong cùng tải đại diện.

#### Tài liệu tham khảo để kiểm tra theo phiên bản

- [Spring-WS 4.1.x API — AxiomSoapMessageFactory](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/soap/axiom/AxiomSoapMessageFactory.html).
- [Spring-WS 4.1.x API — AxiomSoapMessage và StreamingWebServiceMessage](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/soap/axiom/AxiomSoapMessage.html).
- [Spring-WS 4.1.4 Reference — Message Factories / Axiom / SAAJ](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/).
- [Spring-WS 5.0.0-M1 API — AXIOM package](https://docs.spring.io/spring-ws/docs/5.0.0-M1/api/org/springframework/ws/soap/axiom/package-summary.html).
- [Spring Security Advisory — CVE-2026-59349, 19/11/2026](https://spring.io/security/cve-2026-59349/).



