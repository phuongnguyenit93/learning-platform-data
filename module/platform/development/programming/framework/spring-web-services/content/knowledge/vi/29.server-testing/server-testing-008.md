# Kiểm tra interceptor, mapping và hợp đồng chữ ký endpoint

Một Spring Web Services endpoint có thể xử lý đúng khi gọi method trực tiếp trong unit test, nhưng vẫn sai khi nhận SOAP message thật. Nguyên nhân thường nằm ngoài phần nghiệp vụ: EndpointMapping chọn nhầm handler, interceptor không nằm trong invocation chain, request interceptor chặn message không đúng lúc, thứ tự security/validation sai, hoặc chữ ký method không còn tương thích với payload/header mà Spring-WS cần bind.

Kiểm thử máy chủ SOAP phải xác nhận cả **đường đi của message**: SOAP request được dispatch theo QName/SOAPAction, interceptor được gọi theo thứ tự, endpoint method được bind đúng tham số, response/Fault được tạo đúng contract. Bài này tập trung Spring-WS server side, đặc biệt EndpointMapping, EndpointInterceptor, EndpointAdapter, endpoint annotations và MockWebServiceClient.

Bài thuộc chương **Kiểm thử máy chủ** của module **SPRING_WEB_SERVICES**: phát triển dịch vụ SOAP contract-first với XSD/WSDL, JAXB/OXM, endpoint và SOAP client; xử lý SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích. Mục tiêu là xây bộ kiểm thử phát hiện lỗi dispatch, sai lifecycle interceptor, sai method signature và hồi quy contract trước khi triển khai tích hợp doanh nghiệp.

## 1. Bản đồ xử lý một SOAP request ở server

Spring-WS MessageDispatcher điều phối request qua các thành phần:

~~~mermaid
flowchart TD
    A["HTTP/JMS transport receives message"] --> B["MessageDispatcher"]
    B --> C["EndpointMapping"]
    C --> D["EndpointInvocationChain"]
    D --> E["EndpointInterceptor.handleRequest"]
    E --> F{"Còn interceptor?"}
    F -->|Có| E
    F -->|Không| G["EndpointAdapter"]
    G --> H["Resolve method arguments"]
    H --> I["Invoke @Endpoint method"]
    I --> J["Create response payload"]
    J --> K["Interceptor.handleResponse<br/>reverse order"]
    K --> L["Transport sends SOAP response"]
~~~

EndpointMapping xác định endpoint và có thể cung cấp interceptor chain trong EndpointInvocationChain. Sau khi chain được chọn, MessageDispatcher lần lượt gọi request interceptors; chỉ khi chúng cho phép tiếp tục thì EndpointAdapter mới bind tham số và gọi endpoint. Response interceptors được gọi theo thứ tự ngược lại. Vì vậy unit test gọi thẳng Java method không kiểm được mapping/interceptor lifecycle. [Spring-WS Reference 4.1.4 — Endpoint mappings](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/) · [EndpointInterceptor API](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/server/EndpointInterceptor.html)

### 1.1. Các thành phần và trách nhiệm

| Thành phần | Trách nhiệm | Lỗi cần test |
| --- | --- | --- |
| MessageDispatcher | Tìm mapping, thực thi chain và adapter | Không tìm thấy handler |
| EndpointMapping | Chọn endpoint theo message/metadata | QName/action/path trỏ nhầm |
| EndpointInvocationChain | Endpoint và interceptor áp dụng | Thiếu interceptor/sai scope |
| EndpointInterceptor | Pre-process, block, post-process | Sai thứ tự, không block, rò header |
| EndpointAdapter | Bind method args và invoke endpoint | Không resolve RequestPayload/SoapHeader |
| @Endpoint method | Xử lý request và trả response | Sai tham số/return type/annotation |
| EndpointExceptionResolver | Chuyển exception thành SOAP Fault | Fault code/detail sai contract |

### 1.2. Mức kiểm thử

| Mức | Điều chứng minh | Điều không chứng minh |
| --- | --- | --- |
| Unit test endpoint method | Business mapping và Java behavior | SOAP QName, dispatch, interceptor, XML binding |
| Unit test interceptor | Logic riêng interceptor | Đã đăng ký vào mapping chain |
| Mapping test | Endpoint được chọn | Adapter bind đúng signature nếu không dispatch thật |
| MockWebServiceClient | Message qua Spring-WS dispatcher, mapping, interceptor và endpoint trong context | TLS socket, servlet container, proxy |
| Embedded HTTP/SOAP | HTTP, SOAP envelope, servlet mapping, transport errors | Toàn bộ gateway topology |
| Partner interoperability | Contract chạy với stack đối tác | Biến thể chưa test của partner |

Một suite đáng tin có unit tests nhanh và server integration tests qua MockWebServiceClient; dùng embedded server khi cần kiểm HTTP binding, headers, TLS hoặc container.

## 2. Endpoint mapping: chọn đúng handler

EndpointMapping ánh xạ incoming MessageContext tới endpoint object và có thể trả interceptor chain. Những mapping Spring-WS thường dùng:

- PayloadRootAnnotationMethodEndpointMapping: chọn method theo root QName của SOAP Body, thường qua @PayloadRoot.
- SoapActionAnnotationMethodEndpointMapping: chọn method theo SOAPAction, thường qua @SoapAction.
- PayloadRootQNameEndpointMapping: map QName tới endpoint cấu hình.
- SoapActionEndpointMapping: map SOAPAction tới endpoint cấu hình.

@EnableWs/annotation-driven infrastructure thường đăng ký mapping annotation theo cấu hình Spring-WS. Không giả định mapping tùy chỉnh tự động có độ ưu tiên như mapping mặc định; cần xem order và request thực tế. [Spring-WS Reference 4.1.4 — Endpoint mappings](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/) · [EndpointMapping API](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/server/EndpointMapping.html)

### 2.1. QName, không phải prefix, quyết định payload root

Hai request có QName giống nhau:

~~~xml
<a:GetOrderRequest xmlns:a="urn:example:orders:v1">
    <a:orderId>O-100</a:orderId>
</a:GetOrderRequest>
~~~

~~~xml
<ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
    <ord:orderId>O-100</ord:orderId>
</ord:GetOrderRequest>
~~~

Đổi prefix không đổi namespace URI/local name. Cùng local name nhưng URI khác là message khác:

~~~xml
<ord:GetOrderRequest xmlns:ord="urn:example:orders:v2">
    <ord:orderId>O-100</ord:orderId>
</ord:GetOrderRequest>
~~~

Test phải dùng namespace URI đúng và có negative case cho sai namespace, không chỉ so chuỗi GetOrderRequest.

### 2.2. Endpoint method qua @PayloadRoot

~~~java
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;

@Endpoint
public class OrderEndpoint {
    private static final String NS = "urn:example:orders:v1";
    private final OrderService service;

    public OrderEndpoint(OrderService service) {
        this.service = service;
    }

    @PayloadRoot(namespace = NS, localPart = "GetOrderRequest")
    @ResponsePayload
    public GetOrderResponse getOrder(
            @RequestPayload GetOrderRequest request) {
        return service.find(request.getOrderId());
    }
}
~~~

Spring-WS chọn method nhờ @PayloadRoot khớp QName payload root. @RequestPayload nói rằng tham số được bind từ SOAP Body; @ResponsePayload đánh dấu return value trở thành payload response. Các lớp request/response là JAXB/OXM model do project generate/cấu hình. [PayloadRoot API](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/server/endpoint/annotation/PayloadRoot.html)

### 2.3. SOAPAction mapping

~~~java
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;
import org.springframework.ws.soap.server.endpoint.annotation.SoapAction;

@Endpoint
public class LegacyOrderEndpoint {
    private final OrderService orderService;

    public LegacyOrderEndpoint(OrderService orderService) {
        this.orderService = orderService;
    }

    @SoapAction("urn:example:orders:action:GetOrder")
    @ResponsePayload
    public GetOrderResponse getOrder(
            @RequestPayload GetOrderRequest request) {
        return orderService.find(request.getOrderId());
    }
}
~~~

Khi contract yêu cầu SOAPAction, test giá trị chính xác, thiếu action và action không khớp. Với SOAP 1.1, SOAPAction thường là HTTP header; SOAP 1.2 dùng action parameter trong Content-Type theo binding. Không coi raw HTTP header và QName là một cơ chế.

### 2.4. Xung đột mapping

Nếu hai mapping cùng có thể nhận một request:

- Xác định order của từng mapping.
- Xác định mapping nào thực sự được chọn trước.
- Test request có QName và SOAPAction mâu thuẫn.
- Tránh dùng defaultEndpoint để che lỗi route.
- Assert endpoint được gọi đúng một lần và endpoint khác không được gọi.

Endpoint mapping có thể trả null khi không match; MessageDispatcher tiếp tục hỏi mapping tiếp theo. Chỉ khi không mapping nào tìm được endpoint mới báo lỗi dispatch. [EndpointMapping API](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/server/EndpointMapping.html)

## 3. EndpointInterceptor: request, response và Fault lifecycle

EndpointInterceptor là workflow interface để thêm preprocessing/post-processing mà không lặp code trong endpoint:

- handleRequest(MessageContext, Object): chạy trước adapter. Trả true để tiếp tục; false để chặn invocation chain.
- handleResponse(MessageContext, Object): xử lý response sau khi endpoint đã chạy.
- handleFault(MessageContext, Object): xử lý SOAP Fault path.
- afterCompletion(MessageContext, Object, Exception): cleanup sau khi hoàn tất chain.

handleResponse chỉ được gọi nếu handleRequest tương ứng hoàn tất thành công. Response/Fault post-processing áp dụng theo thứ tự ngược với request. Nếu handleRequest trả false, endpoint không được gọi. [EndpointInterceptor API](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/server/EndpointInterceptor.html)

### 3.1. Ví dụ interceptor

~~~java
import org.springframework.ws.context.MessageContext;
import org.springframework.ws.server.EndpointInterceptor;

public class CorrelationInterceptor implements EndpointInterceptor {
    @Override
    public boolean handleRequest(MessageContext context, Object endpoint) {
        // Đọc/validate correlation header và lọc ký tự/độ dài.
        return true;
    }

    @Override
    public boolean handleResponse(MessageContext context, Object endpoint) {
        // Gắn correlation response header nếu contract yêu cầu.
        return true;
    }

    @Override
    public boolean handleFault(MessageContext context, Object endpoint) {
        // Ghi fault category đã lọc, không chèn stack trace.
        return true;
    }

    @Override
    public void afterCompletion(
            MessageContext context, Object endpoint, Exception ex) {
        // Cleanup ThreadLocal/resource nếu đã tạo.
    }
}
~~~

Nếu dùng ThreadLocal, bắt buộc cleanup trong afterCompletion và test với thread pool reuse. Không giữ MessageContext hoặc dữ liệu request trong singleton interceptor sau khi request kết thúc.

### 3.2. Test chặn request trước endpoint

Interceptor có thể từ chối request bằng cách tạo response/Fault và trả false:

~~~java
public class PartnerGuardInterceptor implements EndpointInterceptor {
    @Override
    public boolean handleRequest(MessageContext context, Object endpoint) {
        if (!hasTrustedPartnerHeader(context)) {
            addClientFault(context, "Partner is not authorized");
            return false;
        }
        return true;
    }

    // Implement các method lifecycle khác theo policy.
}
~~~

Đây là pseudocode: hasTrustedPartnerHeader và addClientFault là helper ứng dụng cần triển khai qua SOAP API thích hợp. Test cần khẳng định response là Fault mong muốn và mock domain service không được gọi. Chỉ kiểm tra Fault chưa chứng minh endpoint đã bị chặn trước side effect.

### 3.3. Thứ tự nhiều interceptor

~~~text
1. CorrelationInterceptor
2. SecurityValidationInterceptor
3. PayloadValidationInterceptor
4. AuditInterceptor
5. Endpoint
~~~

Request phase chạy theo thứ tự đăng ký. Response/Fault phase đi ngược chain theo lifecycle Spring-WS. Thứ tự minh họa không phải cấu hình security phổ quát; interceptor WS-Security phải theo policy và kiểm chứng bằng message ký thật.

Test thứ tự bằng probe interceptors ghi event vào list riêng:

~~~text
correlation.request
security.request
audit.request
...
audit.response
security.response
correlation.response
~~~

Không phụ thuộc log text framework để chứng minh order; record event và assert sequence cụ thể. Khi Fault xảy ra, test sequence fault path riêng vì handleResponse không thay thế handleFault.

## 4. Endpoint signature contract: method parameters và return value

DefaultMethodEndpointAdapter hỗ trợ nhiều kiểu tham số. Chữ ký method là một phần của server contract implementation: nếu XML/headers không thể bind vào tham số, adapter có thể lỗi trước khi business method chạy.

### 4.1. Các kiểu binding thường gặp

| Nguồn message | Kiểu tham số | Annotation |
| --- | --- | --- |
| SOAP Body | Source/DOMSource/SAXSource/StreamSource | @RequestPayload |
| SOAP Body | W3C DOM Element | @RequestPayload |
| SOAP Body | JAXB @XmlRootElement object/JAXBElement | @RequestPayload |
| SOAP Body | Spring OXM supported type | @RequestPayload |
| SOAP Body | XPath scalar/Node/NodeList | @XPathParam |
| SOAP Header | SoapHeader | Tham số SoapHeader được bind toàn header |
| SOAP Header | SoapHeaderElement/List<SoapHeaderElement> | @SoapHeader với QName của header element |
| Message-level | MessageContext | Không cần @RequestPayload |
| Full SOAP message | SoapMessage/SoapEnvelope/SoapBody | Theo supported method argument resolver |

Danh sách hỗ trợ phụ thuộc classpath và cấu hình adapters/unmarshaller. Xem endpoint handling methods và DefaultMethodEndpointAdapter của version dự án. [Spring-WS Reference 4.1.4 — Endpoint handling methods](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/)

### 4.2. JAXB payload và SOAP Header cùng method

~~~java
import org.springframework.ws.soap.SoapHeader;
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;

@Endpoint
public class SecureOrderEndpoint {
    private static final String NS = "urn:example:orders:v1";
    private final OrderService service;

    public SecureOrderEndpoint(OrderService service) {
        this.service = service;
    }

    @PayloadRoot(namespace = NS, localPart = "GetOrderRequest")
    @ResponsePayload
    public GetOrderResponse getOrder(
            @RequestPayload GetOrderRequest request,
            SoapHeader soapHeader) {
        // Đọc header qua SoapHeader API.
        return service.find(request.getOrderId());
    }
}
~~~

Payload JAXB và SOAP header là hai nguồn binding khác nhau. Tham số SoapHeader nhận toàn bộ SOAP Header; nếu chỉ cần một header element, dùng SoapHeaderElement với @SoapHeader theo QName. Test phải gửi đúng cả Body và Header QName, kiểm trường hợp Header thiếu/bị sai namespace, và xác định header optional hay bắt buộc.

Ví dụ bind một Header element cụ thể:

~~~java
import org.springframework.ws.soap.SoapHeaderElement;
import org.springframework.ws.soap.server.endpoint.annotation.SoapHeader;

public GetOrderResponse getOrder(
        @RequestPayload GetOrderRequest request,
        @SoapHeader("{urn:example:headers:v1}PartnerContext")
        SoapHeaderElement partnerContext) {
    String partnerId = partnerContext.getText();
    return service.findForPartner(request.getOrderId(), partnerId);
}
~~~

Đây là phần thân method minh họa. QName trong annotation dùng dạng `{namespace-uri}localPart`; resolver tìm đúng header element đó. Nếu header có thể lặp nhiều lần, có thể bind thành List<SoapHeaderElement> và kiểm tra cardinality theo contract.

### 4.3. @XPathParam và @Namespace

~~~java
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.Namespace;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.XPathParam;

@Endpoint
public class LightweightOrderEndpoint {
    private final OrderService orderService;

    public LightweightOrderEndpoint(OrderService orderService) {
        this.orderService = orderService;
    }

    @PayloadRoot(localPart = "GetOrderRequest",
                 namespace = "urn:example:orders:v1")
    @Namespace(prefix = "o", uri = "urn:example:orders:v1")
    public GetOrderResponse getOrder(
            @XPathParam("/o:GetOrderRequest/o:orderId") String orderId) {
        return orderService.find(orderId);
    }
}
~~~

@XPathParam dùng XPath để resolve giá trị; prefix trong XPath phải được bind với namespace URI bằng @Namespace ở method/type/package. Test cần kiểm prefix thay đổi nhưng namespace URI không đổi; kết quả vẫn giống nhau. @PayloadRoot quyết định route theo payload QName độc lập với XPath expression.

### 4.4. Return types và one-way behavior

- @ResponsePayload trên return value cho biết object/Source được dùng làm SOAP Body payload.
- Method void hoặc không có response payload có thể đại diện operation không trả body theo thiết kế.
- SoapMessage/MessageContext cho phép kiểm soát message-level, nhưng tăng trách nhiệm serialize/headers cho endpoint.
- Exception có thể được map thành SOAP Fault qua EndpointExceptionResolver.

Không suy ra WSDL MEP chỉ từ void một method riêng lẻ: phải đối chiếu WSDL/binding, SOAP HTTP behavior và endpoint adapter. Test operation one-way và request-response theo contract.

## 5. Những lỗi signature cần bắt

| Lỗi | Hậu quả | Test |
| --- | --- | --- |
| Thiếu @RequestPayload trên JAXB/DOM arg | Adapter không bind như dự kiến | Application context + request integration test |
| JAXB class không có root element/JAXBElement mapping sai | Unmarshal hoặc argument resolution fail | Test generated binding với XML fixture |
| Method có payload parameters không hỗ trợ/không rõ resolver | Invocation setup fail | Assert context/startup hoặc dispatch failure |
| @PayloadRoot sai namespace/localPart | Không tìm đúng method | QName negative test |
| @SoapAction sai hoặc SOAPAction thiếu | Mapping không match | Test SOAP 1.1/1.2 binding |
| Header parameter không có annotation/resolver phù hợp | Không bind được header | Valid/absent/wrong-QName tests |
| XPath prefix không khai báo | XPath không match/resolve | Prefix and namespace tests |
| Return type không được adapter hỗ trợ | Không serialize được response | Response mapping integration test |
| Thiếu @ResponsePayload trên return payload | Response body không như contract | Assert response QName/content |
| Exception không map đúng resolver | SOAP Fault generic/sai code | Fault mapping tests |
| Overloaded method mapping mơ hồ | Dispatch/startup failure | Context load + request routing test |

Không chỉ kiểm tra context load. Một số lỗi chỉ xuất hiện khi endpoint adapter resolve method argument trên message cụ thể; cần gửi fixture qua MessageDispatcher.

## 6. MockWebServiceClient: server-side integration test

MockWebServiceClient thuộc package org.springframework.ws.test.server. Nó tạo SOAP request message, gửi qua WebServiceMessageReceiver/MessageDispatcher trong application context Spring-WS, rồi cho phép kiểm response bằng ResponseMatcher. Đây là công cụ trọng tâm để test mapping, interceptors và endpoint pipeline mà không mở HTTP socket. [MockWebServiceClient API 4.1.x](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/test/server/MockWebServiceClient.html)

### 6.1. Tạo client và gửi payload

~~~java
import static org.springframework.ws.test.server.RequestCreators.withPayload;
import static org.springframework.ws.test.server.ResponseMatchers.payload;

import org.springframework.context.ApplicationContext;
import org.springframework.ws.test.server.MockWebServiceClient;
import org.springframework.xml.transform.StringSource;
import javax.xml.transform.Source;

class OrderEndpointIntegrationTest {
    private final MockWebServiceClient client;

    OrderEndpointIntegrationTest(ApplicationContext applicationContext) {
        this.client = MockWebServiceClient.createClient(applicationContext);
    }

    void returnsOrder() throws Exception {
        Source request = new StringSource("""
            <ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
                <ord:orderId>O-100</ord:orderId>
            </ord:GetOrderRequest>
            """);
        Source response = new StringSource("""
            <ord:GetOrderResponse xmlns:ord="urn:example:orders:v1">
                <ord:orderId>O-100</ord:orderId>
                <ord:status>READY</ord:status>
            </ord:GetOrderResponse>
            """);

        client.sendRequest(withPayload(request))
                .andExpect(payload(response));
    }
}
~~~

Đây là khung JUnit/TestNG minh họa; bootstrap context phụ thuộc test framework. MockWebServiceClient.createClient(ApplicationContext) dùng receiver/message factory từ context nếu có, nếu không tạo mặc định theo API. Trong test thực, dùng context của MessageDispatcherServlet chứa endpoints, mappings, adapters, interceptors và exception resolvers.

### 6.2. Kiểm tra response bằng matcher

Có thể chain andExpect(...). Các matcher mặc định nằm trong ResponseMatchers; custom ResponseMatcher có thể inspect request/response, SOAP version/header/Fault hoặc thuộc tính đặc thù. Khi so payload, nên so XML theo namespace/structure thay vì serialization string nếu prefix/whitespace không thuộc contract.

### 6.3. Test SOAP Fault

~~~java
import static org.springframework.ws.test.server.RequestCreators.withPayload;
import static org.springframework.ws.test.server.ResponseMatchers.clientOrSenderFault;

client.sendRequest(withPayload(invalidRequest))
        .andExpect(clientOrSenderFault());
// verify(orderService, never()).createOrder(any());
~~~

Matcher clientOrSenderFault() phù hợp client/sender-class fault; chọn matcher tương ứng khi test server/receiver Fault hoặc viết custom matcher để assert fault code/detail. Không kiểm HTTP 500 thay SOAP Fault: mock server không thực hiện HTTP exchange thật.

### 6.4. Kiểm tra SOAP Header

Khi endpoint method bind SOAP Header, request fixture phải tạo envelope/header thực tế. withPayload(...) chỉ tập trung payload và thường không đủ chứng minh header binding. Tạo custom RequestCreator bằng message factory hoặc dùng request creator phù hợp phiên bản để thêm SOAP Header, rồi assert endpoint nhận đúng header QName/value.

## 7. Kiểm thử interceptor theo lifecycle

Tạo probe interceptor cho test, ghi sự kiện vào list riêng:

| Test | Setup | Assertion |
| --- | --- | --- |
| Request order | Hai hoặc ba interceptors | handleRequest đúng order |
| Response order | Request đi hết chain | handleResponse reverse order |
| Block | Interceptor đầu trả false | Endpoint không được gọi |
| Request exception | Interceptor ném exception | Endpoint không được gọi; resolver path đúng |
| Endpoint exception | Endpoint throw | Fault path chạy; kiểm handleFault |
| Cleanup | Request success/fault | afterCompletion cleanup đúng |
| Mapping scope | Request tới mapping A và B | Interceptor chỉ chạy với chain được cấu hình |
| Concurrent requests | Nhiều request song song | Không trộn state/correlation |

### 7.1. Probe interceptor

~~~java
import java.util.List;
import org.springframework.ws.context.MessageContext;
import org.springframework.ws.server.EndpointInterceptor;

public class RecordingInterceptor implements EndpointInterceptor {
    private final String name;
    private final List<String> events;

    public RecordingInterceptor(String name, List<String> events) {
        this.name = name;
        this.events = events;
    }

    @Override
    public boolean handleRequest(MessageContext context, Object endpoint) {
        events.add(name + ".request");
        return true;
    }

    @Override
    public boolean handleResponse(MessageContext context, Object endpoint) {
        events.add(name + ".response");
        return true;
    }

    @Override
    public boolean handleFault(MessageContext context, Object endpoint) {
        events.add(name + ".fault");
        return true;
    }

    @Override
    public void afterCompletion(
            MessageContext context, Object endpoint, Exception ex) {
        events.add(name + ".complete");
    }
}
~~~

Trong test, tạo events không static và không share giữa test chạy song song. Đăng ký hai probe, gửi SOAP request qua MockWebServiceClient rồi assert order. Với lỗi giữa request chain, không giả định mọi interceptor sau điểm lỗi đã chạy.

### 7.2. Mapping scope và SmartEndpointInterceptor

SmartEndpointInterceptor cho phép quyết định interceptor có áp dụng cho message/endpoint cụ thể hay không. Các triển khai như PayloadRootSmartSoapEndpointInterceptor hoặc SoapActionSmartEndpointInterceptor phù hợp khi security/audit chỉ áp dụng cho namespace/action cụ thể. Test positive và negative scope:

- QName V1: interceptor được gọi.
- QName V2: không được gọi nếu policy chỉ bảo vệ V1.
- SOAPAction khác: không áp dụng nếu action ngoài scope.
- Default endpoint: xác định rõ interceptor scope, không vô tình bỏ qua security.

Không dùng SmartEndpointInterceptor để thay authorization policy; selection condition không chứng minh caller được phép dùng operation.

## 8. Kiểm tra WS-Security và interceptor ordering

Nếu endpoint sử dụng Wss4jSecurityInterceptor, chỉ kiểm @Endpoint trả kết quả đúng là chưa đủ. Cần test:

1. Message hợp lệ có UsernameToken/Signature/Encryption được chấp nhận.
2. Security Header thiếu hoặc sai bị từ chối trước endpoint.
3. Signature validation chạy trước logic nghiệp vụ.
4. Signed Body/Headers cover đúng dữ liệu được dùng.
5. SOAP Fault khi validation fail được tạo theo SOAP version.
6. Không có mapping khác bỏ qua interceptor.

### 8.1. Negative test: thiếu security header

~~~java
String requestXml = """
    <ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
        <ord:orderId>O-100</ord:orderId>
    </ord:GetOrderRequest>
    """;

client.sendRequest(withPayload(new StringSource(requestXml)))
        .andExpect(clientOrSenderFault());
~~~

Đoạn trên chỉ tạo Body và cố ý thiếu wsse:Security, phù hợp test required-security khi context bật inbound validation. Bổ sung assertion verify(orderService, never()).find(...). Nếu request không match endpoint mapping, Fault có thể đến từ dispatch chứ không phải WSS4J; positive control phải chứng minh cùng QName/route đi tới endpoint khi security header hợp lệ.

### 8.2. Positive test với signed SOAP thật

Không tạo một wsse:Security rỗng rồi gọi đó là request đã bảo vệ. Positive integration test cần client ký message bằng test keystore/private key:

~~~text
Test SOAP sender:
  WebServiceTemplate + WSS4J outbound signature
  private key test + signer certificate

Spring-WS server context:
  same endpoint mapping + Wss4jSecurityInterceptor
  validationSignatureCrypto trusts the test signer

Assertions:
  valid signature -> endpoint called exactly once
  modified Body/signature -> SOAP Fault, endpoint not called
~~~

Test response/Fault cần kiểm signed parts và trust identity, không chỉ có sự hiện diện của ds:Signature.

### 8.3. Thứ tự bảo vệ message

Nếu interceptor mutate SOAP payload sau signature verification, nội dung nghiệp vụ dùng có thể khác nội dung đã ký. Test tamper và probe order nên chứng minh payload được xác thực là payload được consume, và outbound signature được áp dụng lên response cuối cùng.

TLS/mTLS và WS-Security là hai lớp độc lập. MockWebServiceClient không mở socket TLS; test trust/hostname/mTLS phải dùng embedded HTTPS server hoặc staging test riêng.

## 9. Payload validation và endpoint mapping

PayloadValidatingInterceptor có thể validate request/response theo schema. Khi đăng ký, cần chỉ rõ:

- Schema dùng theo version/namespace.
- Validation xảy ra trước hay sau transformation/interceptor khác.
- validateRequest/validateResponse bật đúng.
- Fault path khi XML không hợp lệ.
- Không gọi domain khi request validation fail.

Một hệ thống phục vụ nhiều version có thể cần mapping riêng/interceptor scope theo version. Không gắn một schema validator toàn cục rồi mặc định mọi payload đều theo cùng XSD.

### 9.1. Contract test theo namespace và SOAP version

| Case | Request | Kỳ vọng |
| --- | --- | --- |
| V1 valid | QName V1, XSD V1 | Endpoint V1/compatibility chain |
| V2 valid | QName V2, XSD V2 | Endpoint V2 |
| Wrong namespace | Local name đúng, URI sai | Không route nhầm |
| Unknown operation | QName/action không đăng ký | Dispatch Fault |
| Wrong SOAPAction | Payload đúng, action sai | Mapping/Fault theo contract |
| SOAP 1.1 | Envelope SOAP 1.1 | SOAP 1.1 semantics |
| SOAP 1.2 | Envelope SOAP 1.2 | SOAP 1.2 semantics hoặc reject rõ |
| Malformed XML | Không parse được | Parser/transport error, endpoint không gọi |
| XSD violation | XML parse được nhưng sai contract | Validation Fault, no side effect |

MockWebServiceClient kiểm message-level behavior, nhưng HTTP Content-Type, SOAPAction transport header và servlet path cần kiểm ở HTTP integration layer.

## 10. Exception resolver và Fault contract

EndpointExceptionResolver chuyển exception trong server processing thành SOAP Fault. Test cần phân biệt:

- Validation/input faults: request không hợp lệ.
- Security faults: WS-Security/authentication không đạt.
- Authorization faults: identity hợp lệ nhưng không có quyền.
- Business faults: nghiệp vụ từ chối theo contract.
- Receiver/server faults: lỗi nội bộ hoặc dependency.

Không trả stack trace, SQL, alias keystore hoặc nội dung secret trong Fault detail. Kiểm SOAP 1.1 faultcode/faultstring và SOAP 1.2 Code/Reason/Detail nếu server hỗ trợ hai version.

### 10.1. Test không có side effect khi Fault

~~~text
Given: endpoint service mock + transaction-aware repository test
When: invalid SOAP message is sent through MockWebServiceClient
Then:
  expected Fault is returned
  service method is never invoked
  repository writes = 0
  no outbox/event is emitted
~~~

Với request validation/security failure, domain không được chạy. Với business fault xảy ra sau khi endpoint chạy, transaction semantics phụ thuộc thiết kế; đừng assert rollback mặc định nếu operation cố ý ghi audit/rejection record.

## 11. Test fixtures và tránh false positives

Các lỗi khiến test pass giả:

1. QName sai nên endpoint không được tìm thấy; test thấy bất kỳ Fault nào và tưởng interceptor đã chặn.
2. SOAPAction không khớp nên request rẽ sang mapping khác.
3. Interceptor không được đăng ký vào mapping chain.
4. Mock domain service không phải bean mà endpoint thực sự dùng.
5. @Endpoint không được component-scan nhưng test chỉ gọi method trực tiếp.
6. SOAP 1.1/1.2 mismatch khiến parser lỗi trước interceptor.
7. Fault matcher quá rộng, không assert fault code/detail.
8. Test chỉ kiểm HTTP 500 mà không đọc SOAP Fault.

### 11.1. Positive control và negative control

| Positive control | Negative biến thể |
| --- | --- |
| QName đúng, endpoint được gọi | QName URI sai |
| SOAPAction đúng | SOAPAction sai/thiếu |
| Security Header/Signature hợp lệ | Header thiếu/signature hỏng |
| Schema hợp lệ | Sai datatype/cardinality |
| Header hợp lệ | Header missing/wrong namespace |
| Response JAXB hợp lệ | Endpoint return type không serialize được |

Chỉ thay một điều kiện tại một thời điểm. Assert response, endpoint identity, service invocation count và interceptor event trace.

### 11.2. Test source-of-truth cho endpoint signature

~~~text
src/test/resources/soap/
  v1/
    get-order-valid.xml
    get-order-missing-id.xml
    get-order-wrong-namespace.xml
    get-order-missing-header.xml
  v2/
    get-order-valid.xml
    get-order-unknown-status.xml
  fault/
    sender-fault.xml
    receiver-fault.xml
~~~

Tên/folder trên là cấu trúc gợi ý. Fixture nên thể hiện SOAP Body/Header thật và được đối chiếu XSD/WSDL. Không generate mọi request fixture từ cùng JAXB class đang test, vì cùng một sai sót model có thể làm producer test và expected result sai giống nhau.

## 12. Khi nào cần embedded HTTP server?

MockWebServiceClient kiểm dispatch/message pipeline trong Spring-WS, không kiểm:

- HTTP route/context path trong servlet container.
- Request Content-Type và SOAPAction trên wire.
- HTTP authentication, TLS/mTLS, reverse proxy.
- Connection errors/timeouts và response status.
- Container filters/compression nếu có.

Dùng embedded servlet container hoặc test environment cho các contract transport này. Gửi SOAP bytes/HTTP headers thật, assert response Content-Type/status và parse SOAP envelope/Fault.

### 12.1. Ranh giới test

| Điều cần test | Công cụ phù hợp |
| --- | --- |
| Endpoint/interceptor/mapping | MockWebServiceClient |
| Client template request XML | MockWebServiceServer |
| JAXB/XSD binding | Marshal/unmarshal/schema tests |
| HTTP SOAPAction/Content-Type/path | Embedded HTTP server |
| TLS/mTLS/certificate chain | Embedded HTTPS test setup |
| WS-Security signature/encryption | WSS4J test keys + SOAP integration |
| Reverse proxy headers | Staging/contract topology tests |

Không cố dùng mock message context để kết luận TLS hoặc proxy behavior đã được xác minh.

## 13. Concurrency, state và transaction trong test server

Spring endpoint/interceptor thường là singleton bean. Vì vậy:

- Không lưu request-specific mutable state trong field của endpoint/interceptor.
- MessageContext chỉ có vòng đời trong một exchange.
- ThreadLocal phải cleanup dù success, Fault hay exception.
- Test nhiều requests đồng thời để bắt state leakage/correlation mix-up.
- Transaction boundary phải rõ: interceptor chạy trước endpoint transaction có thể chưa ở trong transaction; post-processing có thể diễn ra sau service transaction theo proxy/lifecycle.
- Nếu interceptor publish event, dùng outbox/transaction strategy phù hợp; không giả định interceptor Fault tự rollback side effect đã commit.

Test concurrency có thể dùng executor/latches với số request hữu hạn, service stub có barrier và assertions per request ID. Tránh dùng static event lists làm test flake khi chạy parallel.

## 14. Ma trận kiểm thử server tổng hợp

| ID | Kịch bản | Kết quả cần chứng minh |
| --- | --- | --- |
| MAP-01 | QName V1 hợp lệ | Đúng handler V1 |
| MAP-02 | QName V2 hợp lệ | Đúng handler V2 |
| MAP-03 | Sai namespace, cùng localPart | Không route nhầm |
| MAP-04 | SOAPAction đúng/sai | Mapping action đúng |
| MAP-05 | QName/action mâu thuẫn | Conflict policy rõ, không endpoint tùy tiện |
| INT-01 | Interceptor request order | Đúng thứ tự chain |
| INT-02 | Response reverse order | Đúng chiều post-processing |
| INT-03 | Interceptor trả false | Endpoint không chạy |
| INT-04 | Interceptor request throws | Resolver/Fault đúng |
| INT-05 | Endpoint throws | Fault chain và cleanup đúng |
| INT-06 | Mapping scope | Interceptor chỉ chạy cho endpoint được chỉ định |
| SIG-01 | JAXB @RequestPayload | DTO được bind đúng |
| SIG-02 | SOAP Header parameter | Header QName/value bind đúng |
| SIG-03 | @XPathParam | Namespace binding đúng |
| SIG-04 | Unsupported signature/return | Dispatch/adapter failure rõ ràng |
| SEC-01 | Missing WS-Security | Fault, no domain invocation |
| SEC-02 | Valid signature | Endpoint được gọi đúng một lần |
| SEC-03 | Tampered signature | Fault, no side effect |
| VAL-01 | XSD valid | Endpoint tiếp tục |
| VAL-02 | XSD invalid | Validation Fault, no side effect |
| FAULT-01 | Business Fault | Correct SOAP fault code/detail |
| FAULT-02 | Server exception | Generic receiver Fault, no leak |
| SOAP-01 | SOAP 1.1 | Contract behavior đúng |
| SOAP-02 | SOAP 1.2 | Contract behavior đúng hoặc reject rõ |
| HTTP-01 | Wrong Content-Type/SOAPAction | Transport/binding response đúng |
| HTTP-02 | TLS/mTLS | Embedded HTTPS validation |
| CONC-01 | Concurrent requests | Không rò state/context |

## 15. Bài tập thực hành

1. Tạo endpoint V1/V2 cùng localPart nhưng namespace khác; gửi prefix khác nhau nhưng URI đúng và URI lạ.
2. Tạo method @SoapAction, kiểm SOAPAction đúng, sai và thiếu; xác định SOAP 1.1/1.2 behavior.
3. Đăng ký hai RecordingInterceptor, assert request forward và response reverse order; làm endpoint throw để xác minh fault path.
4. Tạo partner guard interceptor trả false khi Header thiếu; assert Fault và service method không được gọi.
5. Viết method dùng JAXB @RequestPayload, SoapHeader và @XPathParam; test namespace/prefix.
6. Cho endpoint trả object chưa được adapter hỗ trợ; xác định lỗi response serialization và Fault.
7. Gửi signed request hợp lệ và tampered; valid gọi service, invalid Fault và không side effect.
8. Gửi XML well-formed nhưng vi phạm XSD; xác minh validation interceptor chặn endpoint.
9. Tạo business Fault và receiver Fault cho SOAP 1.1/1.2; assert code/reason/detail và không rò stack trace.
10. Đăng ký interceptor chỉ áp dụng namespace V1; test V1 và V2 để xác minh scope.
11. Khởi động embedded server trên port động; gửi SOAP qua HTTP thật với Content-Type/SOAPAction khác nhau.
12. Gửi request đồng thời với correlation khác nhau; xác minh không trộn header, principal, MessageContext hoặc event trace.

## 16. Checklist review endpoint và test suite

| Nhóm | Điều kiện đạt |
| --- | --- |
| **Mapping** | QName/SOAPAction/path mapping rõ và có negative tests |
| **Precedence** | Mapping order/default endpoint không che route lỗi |
| **Interceptor registration** | Chain gắn đúng mapping/endpoint scope |
| **Lifecycle** | Request, response, Fault và afterCompletion được kiểm riêng |
| **Blocking** | handleRequest=false thực sự ngăn endpoint invocation |
| **Signature** | RequestPayload, SoapHeader, XPathParam và return type đúng adapter |
| **JAXB/OXM** | Generated models/unmarshaller được cấu hình và test từ XML fixture |
| **SOAP version** | SOAP 1.1/1.2 behavior được công bố và kiểm thử |
| **Security** | WS-Security validation trước business logic; signed parts cover data được dùng |
| **Validation** | XSD source/target phù hợp mapping và validation scope |
| **Fault handling** | Fault code/detail đúng contract, không rò nội bộ |
| **Side effects** | Invalid/security failures không gọi domain hoặc commit nghiệp vụ |
| **Test realism** | MockWebServiceClient cho message pipeline; embedded HTTP/TLS cho transport |
| **Concurrency** | Singleton endpoint/interceptor không chứa mutable request state |
| **Observability** | Correlation/mapping/endpoint/error category được log có kiểm soát |
| **Fixtures** | XML fixtures độc lập DTO, namespace-aware, đại diện contract versions |

## 17. Tài liệu tham khảo

- [Spring Web Services Reference 4.1.4 — Endpoint mappings](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/): EndpointMapping, EndpointInvocationChain, @PayloadRoot, @SoapAction và interceptor chain.
- [Spring-WS Reference 4.1.4 — Server-side Testing](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/): MockWebServiceClient, RequestCreators, ResponseMatchers và integration tests.
- [MockWebServiceClient API 4.1.x](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/test/server/MockWebServiceClient.html): tạo client từ ApplicationContext hoặc receiver/message factory.
- [EndpointInterceptor API 4.1.x](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/server/EndpointInterceptor.html): lifecycle request/response/Fault/afterCompletion.
- [EndpointMapping API 4.1.4](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/server/EndpointMapping.html): endpoint selection và invocation chain.
- [PayloadRoot API 4.1.x](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/server/endpoint/annotation/PayloadRoot.html): QName-based method mapping.
- [W3C SOAP 1.2 Part 1](https://www.w3.org/TR/soap12-part1/): Envelope, Header, Body, processing model và Fault.

**Kết luận:** Kiểm thử máy chủ Spring-WS phải xác nhận toàn bộ đường dispatch, không chỉ gọi endpoint method trực tiếp. EndpointMapping chọn handler và interceptor chain; interceptor có lifecycle request/response/Fault với thứ tự xác định; EndpointAdapter bind chữ ký method từ payload, SOAP Header hoặc XPath. MockWebServiceClient là công cụ chính để kiểm message pipeline, còn embedded HTTP/TLS tests cần thiết cho transport behavior. Khi suite có positive/negative cases cho QName, SOAPAction, interceptor order/blocking, JAXB/header binding, WS-Security, XSD và Fault, nhóm phát triển có thể phát hiện sớm endpoint route sai, interceptor bị bỏ sót và method signature lệch contract trước khi tích hợp đối tác.
