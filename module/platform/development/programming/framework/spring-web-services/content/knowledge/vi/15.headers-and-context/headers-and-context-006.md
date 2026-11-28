# MessageContext và dữ liệu cần chia sẻ trong một lần xử lý

Trong **Spring Web Services (Spring-WS)**, một SOAP request thường đi qua nhiều lớp: transport, `MessageDispatcher`, `EndpointMapping`, interceptor, adapter, `@Endpoint` và dịch vụ nghiệp vụ. Có những dữ liệu chỉ có ý nghĩa **trong đúng một lần xử lý** nhưng lại cần được nhiều thành phần cùng đọc, chẳng hạn mã tương quan (correlation ID), mốc bắt đầu xử lý, tên thao tác đã nhận diện, cờ quyết định ghi log hoặc metadata đã được kiểm tra. Spring-WS cung cấp `org.springframework.ws.context.MessageContext` cho mục đích này.

Bài thuộc chương **Header và ngữ cảnh** của module `SPRING_WEB_SERVICES`. Trên nền tảng **contract-first**, XSD/WSDL xác định payload và những SOAP Header thuộc hợp đồng; JAXB ánh xạ nội dung XML; `MessageContext` giữ request/response và các thuộc tính nội bộ của một lượt dispatch. Hai loại dữ liệu — **SOAP Header đi qua mạng** và **property nằm trong bộ nhớ server** — có chức năng rất khác nhau. Hiểu rõ ranh giới đó giúp tránh nhầm lẫn giữa correlation ID, principal xác thực, WS-Security header, transaction, log tracing và dữ liệu nghiệp vụ.

Các ví dụ minh họa Spring-WS 4.x, Java 17+ và Jakarta JAXB. Một số đoạn tập trung vào kiến trúc hoặc dùng kiểu ứng dụng giả định; khi triển khai, cần ghép với XSD/WSDL, JAXB classes, interceptor và bảo mật thật của dự án.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vòng đời của `MessageContext` và vai trò của `WebServiceMessage` đối với request/response.
2. Sử dụng `getProperty`, `setProperty`, `containsProperty` và `removeProperty` để chia sẻ dữ liệu có phạm vi **một lần xử lý**.
3. Phân biệt property nội bộ, SOAP Header, SOAP Body, HTTP Header, MDC và application DTO.
4. Truy cập `MessageContext` từ `EndpointInterceptor` và tham số phương thức `@Endpoint` đúng cách.
5. Gắn correlation ID vào **SOAP response Header** một cách tường minh, kể cả khi endpoint tạo SOAP Fault.
6. Tránh tạo response ngoài ý muốn do `getResponse()`; hiểu `hasResponse()`, lifecycle interceptor và cleanup.
7. Thiết kế ranh giới an toàn cho header do client cung cấp, WS-Security, TLS/chứng chỉ, transaction và xử lý bất đồng bộ.
8. Kiểm thử dữ liệu ngữ cảnh, header XML, fault path, tính độc lập giữa hai requests và tương thích client.

## 1. Vì sao cần ngữ cảnh cho một SOAP request?

Giả sử client gửi thao tác `GetOrder`. Một lượt xử lý có thể cần:

- **Correlation ID** để liên kết log giữa gateway, server, database và downstream.
- **Thời điểm bắt đầu** để đo latency.
- **Tên operation/QName** để gắn nhãn metric.
- **Thông tin xác thực đã được xác minh** hoặc một dạng identity reference đáng tin để application layer kiểm quyền.
- **Cờ xử lý nội bộ** như “đã phát audit record”, tránh làm lại trong cùng lượt xử lý.
- **Metadata cho SOAP response** như correlation ID phản hồi cho client.

Không phải dữ liệu nào ở đây cũng nên đi vào XML Body. Ví dụ `GetOrderRequest` chỉ chứa `orderId`; tracing là thông tin kỹ thuật, không phải thuộc tính nghiệp vụ của đơn hàng. Hơn nữa, nếu nhiều requests chạy đồng thời trên cùng một bean singleton, các thông tin trên **không được lưu trong field dùng chung của bean**.

### 1.1. Bốn loại dữ liệu nên phân biệt ngay

| Loại dữ liệu | Ví dụ | Người có thể thấy | Phạm vi |
| --- | --- | --- | --- |
| **SOAP Body** | `GetOrderRequest/orderId` | Client và server | Theo hợp đồng XML trong mỗi message |
| **SOAP Header** | `CorrelationId`, `wsse:Security`, `wsa:Action` | Bên gửi/nhận SOAP, các intermediary có quyền xử lý | Được truyền trong một SOAP message |
| **`MessageContext` property** | `orders.traceId`, `orders.startedAtNanos` | Các thành phần có reference đến context trong server | **Một lần xử lý message** |
| **Application/domain context** | Principal đã xác thực, tenant ID tin cậy, transaction status | Use case và policy được cấp quyền | Theo kiến trúc ứng dụng; không đồng nhất với SOAP context |

**Điểm chốt:** gọi `context.setProperty("traceId", id)` không tự tạo `<TraceId>` trong SOAP Header, không thêm HTTP header và không ghi dữ liệu vào database. Muốn client nhìn thấy trace ID, bạn cần **thêm SOAP Header hoặc field response theo hợp đồng** một cách tường minh.

## 2. `MessageContext` chứa những gì?

`MessageContext` là interface của Spring-WS để giữ **request message**, **response message** (thường được tạo khi cần) và **các properties**. Implementation thường gặp là `DefaultMessageContext`; lập trình endpoint/interceptor nên phụ thuộc interface thay vì chi tiết implementation.

Các API chính:

| API | Mục đích | Điểm cần chú ý |
| --- | --- | --- |
| `getRequest()` | Lấy `WebServiceMessage` request | Không mặc định request là một class JAXB |
| `hasResponse()` | Kiểm tra đã có response message chưa | Không tạo response chỉ để kiểm tra |
| `getResponse()` | Lấy response, **có thể tạo mới nếu chưa có** | Có side effect khi lazy initialization |
| `setResponse(message)` | Đặt response message | Thường không được đặt đè nếu response đã được tạo |
| `clearResponse()` | Xóa response hiện tại khỏi context | Chỉ dùng trong logic điều phối có chủ đích |
| `getProperty(name)` | Đọc property theo khóa | Trả `Object` hoặc `null` |
| `setProperty(name, value)` | Lưu/ghi đè property | Không serialize ra SOAP/XML |
| `containsProperty(name)` | Kiểm tra khóa có tồn tại | Khác với suy đoán từ giá trị |
| `removeProperty(name)` | Bỏ property | Hữu ích khi cleanup |
| `getPropertyNames()` | Liệt kê khóa đang có | Không dùng để dump toàn bộ dữ liệu nhạy cảm |
| `readResponse(stream)` | Đọc response từ stream theo API | Không phải API mà endpoint thông thường cần tự gọi |

### 2.1. Request, response và property có bản chất khác nhau

~~~text
MessageContext (một lần dispatch)
│
├── request: WebServiceMessage
│   ├── SOAP Envelope / Body / Header, nếu là SoapMessage
│   └── XML payload của request
│
├── response: WebServiceMessage (có thể chưa tồn tại)
│   ├── SOAP Envelope / Body / Header, nếu là SoapMessage
│   └── XML payload của response hoặc SOAP Fault
│
└── properties: name → Object
    ├── orders.traceId → String
    ├── orders.startedAtNanos → Long
    └── orders.auditDecision → Boolean
~~~

`WebServiceMessage` là lớp abstraction message, không phải kho tùy ý để chứa các object Java. Khi message là SOAP, có thể kiểm tra `instanceof SoapMessage` để truy cập `SoapHeader`, `SoapBody`, SOAPAction và metadata SOAP. Ngược lại, property có thể là Java object thuần, không phụ thuộc namespace XML.

### 2.2. `getResponse()` là thao tác cần thận trọng

Theo hợp đồng API Spring-WS, `MessageContext.getResponse()` có thể **tạo response mới** nếu context chưa có response. Do đó đoạn này không chỉ “nhìn trạng thái”:

~~~java
// Không nên dùng như phép kiểm tra vô hại:
WebServiceMessage response = messageContext.getResponse();
~~~

Nếu đang ở `handleRequest` và chỉ muốn biết có response chưa:

~~~java
if (messageContext.hasResponse()) {
    WebServiceMessage existing = messageContext.getResponse();
    // Có response đã tồn tại để xử lý theo chính sách.
}
~~~

Một request-response endpoint bình thường để adapter dựng response; interceptor **không nên tạo response rỗng trước khi endpoint được gọi** chỉ để ghi một trace ID. Với thao tác one-way hoặc khi xử lý lỗi, việc tạo response quá sớm có thể làm thay đổi hành vi mong đợi. Chỉ gọi `getResponse()` khi bạn thật sự cần lấy/tạo response và hiểu nhánh điều phối.

`setResponse(...)` / `clearResponse()` phục vụ các tình huống điều phối đặc biệt; tránh dùng để thay thế response của endpoint nếu chưa có yêu cầu kiến trúc rõ ràng.

## 3. Vòng đời của `MessageContext` trong Spring-WS

Một lượt xử lý điển hình:

~~~mermaid
sequenceDiagram
    autonumber
    participant C as SOAP Client
    participant T as Transport/Servlet
    participant D as MessageDispatcher
    participant M as EndpointMapping
    participant I as EndpointInterceptor
    participant E as @Endpoint
    participant S as Application Service

    C->>T: HTTP POST + SOAP Envelope
    T->>D: Tạo/chuyển MessageContext(request)
    D->>M: Tìm endpoint
    M-->>D: EndpointInvocationChain
    D->>I: handleRequest(context, endpoint)
    I->>I: setProperty(traceId, startedAt)
    I-->>D: true
    D->>E: @RequestPayload + MessageContext
    E->>E: getProperty(traceId)
    E->>S: Gọi use case với application DTO
    S-->>E: Business result
    E-->>D: @ResponsePayload
    D->>I: handleResponse(context, endpoint)
    I->>I: Thêm SOAP Header phản hồi nếu có response
    D->>I: afterCompletion(context,...)
    D-->>T: Response message
    T-->>C: HTTP SOAP response
~~~

Đây là luồng thành công mang tính khái niệm. Một SOAP Fault, interceptor từ chối xử lý, mapping thất bại hoặc lỗi transport có thể dẫn tới callback và trạng thái response khác nhau.

**Một `MessageContext` không phải một session của người dùng.** Nó không được thiết kế để chứa trạng thái dài hạn qua nhiều SOAP calls. Khi client retry cùng `requestId`, đó là **lượt xử lý mới** với context mới; nếu cần trạng thái liên tục, phải lưu trong repository/idempotency store hoặc một hệ thống state rõ ràng.

### 3.1. Interceptor chạy ở những pha nào?

`EndpointInterceptor` có các callback:

| Pha | Callback | Công việc nên thực hiện |
| --- | --- | --- |
| Trước endpoint | `handleRequest(context, endpoint)` | Tạo/đọc metadata, kiểm tra input, đặt property |
| Response bình thường | `handleResponse(context, endpoint)` | Đọc property, gắn response Header, metric |
| SOAP Fault | `handleFault(context, endpoint)` | Gắn correlation ID, ghi metadata fault, không log secret |
| Kết thúc | `afterCompletion(context, endpoint, ex)` | Cleanup MDC/tài nguyên ngắn hạn, metric cuối |

Các interceptor xử lý request theo thứ tự trong chain, còn nhánh response/fault và cleanup được gọi theo **thứ tự ngược** đối với những interceptor đã tham gia thành công. `handleRequest` trả `false` nghĩa là dừng việc đi tiếp đến các interceptor/endpoint còn lại theo cơ chế xử lý. Đừng suy rằng endpoint vẫn được gọi sau khi một interceptor từ chối.

**Giới hạn quan trọng:** interceptor endpoint được gắn với chain **sau khi mapping đã tìm thấy endpoint**. Nếu request không map được hoặc bị từ chối sớm ở transport/parse, một interceptor gắn với endpoint có thể không chạy. Do đó muốn bảo vệ **toàn bộ** URL SOAP/WSDL/XSD phải dùng thêm policy ở gateway, servlet filter hoặc transport.

### 3.2. Property không tự biến mất giữa các callback

Khi một interceptor đặt `context.setProperty(...)` trong `handleRequest`, những thành phần nhận cùng `MessageContext` có thể đọc property đó trong quá trình xử lý. Giá trị được lưu trong context, không nằm trong annotation `@PayloadRoot` hay trong object JAXB.

Điều này đặc biệt hữu ích khi thông tin chưa hoặc không cần xuất hiện trong XML Body: trace ID, thời điểm bắt đầu, phân loại audit. Tuy nhiên, chỉ nên giữ dữ liệu thật sự cần cho các thành phần sau; đừng biến context thành “túi chứa mọi thứ”.

## 4. Case study: correlation ID từ request đến response

Một dịch vụ `GetOrder` nhận:

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1"
    xmlns:meta="urn:example:orders:meta:v1">
  <soap:Header>
    <meta:CorrelationId>corr-2026-00042</meta:CorrelationId>
  </soap:Header>
  <soap:Body>
    <ord:GetOrderRequest>
      <ord:orderId>ORD-42</ord:orderId>
    </ord:GetOrderRequest>
  </soap:Body>
</soap:Envelope>
~~~

Dịch vụ có hai lựa chọn hợp đồng:

- **Client-provided correlation ID:** nhận một SOAP Header tùy chọn từ client, **kiểm tra format, độ dài, namespace, số lần xuất hiện**, rồi dùng làm correlation ID nếu policy cho phép.
- **Server-generated correlation ID:** luôn tạo UUID riêng trên server, có thể lưu thêm ID do client gửi như một thuộc tính quan sát riêng sau khi validate.

Phương án thứ hai đặc biệt phù hợp nếu hệ thống cần trace ID do phía server kiểm soát. Phần code kế tiếp minh họa cách **server tự sinh ID** để tập trung vào vòng đời context; mục 7 sẽ trình bày cách đọc Header từ client.

### 4.1. Mục tiêu trao đổi

~~~mermaid
flowchart LR
    A["SOAP request<br/>GetOrderRequest"] --> B["CorrelationInterceptor<br/>setProperty(traceId)"]
    B --> C["@Endpoint<br/>getProperty(traceId)"]
    C --> D["OrderQueryService"]
    D --> E["JAXB response"]
    E --> F["CorrelationInterceptor<br/>thêm SOAP Header"]
    F --> G["SOAP response<br/>Header CorrelationId + Body GetOrderResponse"]
~~~

Không có bước nào yêu cầu domain model của đơn hàng chứa correlation ID như một field nghiệp vụ.

## 5. Mã mẫu: một interceptor lưu và dùng property

Giả sử ta định nghĩa một SOAP response header `{urn:example:orders:meta:v1}CorrelationId` có giá trị text. Ví dụ dưới đây dùng API thật của Spring-WS.

~~~java
import java.util.UUID;
import javax.xml.namespace.QName;

import org.springframework.ws.context.MessageContext;
import org.springframework.ws.server.endpoint.interceptor.EndpointInterceptorAdapter;
import org.springframework.ws.soap.SoapHeader;
import org.springframework.ws.soap.SoapMessage;

public final class CorrelationInterceptor
        extends EndpointInterceptorAdapter {

    public static final String TRACE_ID_PROPERTY =
        CorrelationInterceptor.class.getName() + ".traceId";

    private static final QName CORRELATION_HEADER =
        new QName("urn:example:orders:meta:v1", "CorrelationId");

    @Override
    public boolean handleRequest(
            MessageContext context, Object endpoint) {

        String traceId = UUID.randomUUID().toString();
        context.setProperty(TRACE_ID_PROPERTY, traceId);

        // Không gọi context.getResponse() chỉ để kiểm tra.
        return true;
    }

    @Override
    public boolean handleResponse(
            MessageContext context, Object endpoint) {

        addCorrelationHeaderIfPossible(context);
        return true;
    }

    @Override
    public boolean handleFault(
            MessageContext context, Object endpoint) {

        addCorrelationHeaderIfPossible(context);
        return true;
    }

    @Override
    public void afterCompletion(
            MessageContext context, Object endpoint, Exception ex) {

        // Property chỉ có giá trị trong lượt xử lý hiện tại.
        context.removeProperty(TRACE_ID_PROPERTY);
    }

    private void addCorrelationHeaderIfPossible(MessageContext context) {
        if (!context.hasResponse()) {
            return; // Không tự tạo response cho request one-way.
        }

        Object value = context.getProperty(TRACE_ID_PROPERTY);
        if (!(value instanceof String traceId)) {
            return;
        }

        if (context.getResponse() instanceof SoapMessage soapResponse) {
            SoapHeader header = soapResponse.getSoapHeader();
            header.addHeaderElement(CORRELATION_HEADER).setText(traceId);
        }
    }
}
~~~

Đoạn này diễn giải cơ chế chia sẻ và phản hồi, không phải middleware hoàn chỉnh cho production:

- `TRACE_ID_PROPERTY` là **khóa Java nội bộ**; dùng tên có tiền tố package/class để giảm xung đột.
- `context.setProperty(...)` không làm thay đổi SOAP request/response.
- `header.addHeaderElement(QName).setText(...)` **thực sự tạo một SOAP Header element** trên response.
- `hasResponse()` ngăn không vô tình tạo response khi nhánh hiện tại chưa có.
- `handleFault` dùng cùng ID cho nhánh SOAP Fault **khi fault response đã được tạo và callback được gọi**.
- `afterCompletion` xóa property, nhưng context còn có vòng đời riêng và được thu hồi sau request; việc cleanup quan trọng hơn đối với MDC, connection/tài nguyên và dữ liệu nhạy cảm.
- Ví dụ chưa chặn **trùng response header** nếu một thành phần khác cũng thêm `CorrelationId`. Trong ứng dụng thật, chọn một chủ sở hữu duy nhất hoặc kiểm tra header hiện hữu theo QName.
- Một lỗi phát sinh trước khi mapping/interceptor chạy sẽ **không nhất thiết** có correlation header. Muốn trace cả những lỗi HTTP/parse sớm, cần instrumentation ở tầng transport/gateway.

### 5.1. Đăng ký interceptor bằng `WsConfigurer`

~~~java
import java.util.List;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.config.annotation.WsConfigurer;
import org.springframework.ws.server.EndpointInterceptor;

@Configuration
@EnableWs
public class SoapInterceptorConfiguration implements WsConfigurer {

    @Override
    public void addInterceptors(
            List<EndpointInterceptor> interceptors) {
        interceptors.add(new CorrelationInterceptor());
    }
}
~~~

Trong ứng dụng thật, có thể đăng ký interceptor như bean Spring để inject clock, metrics hay tracer. Khi dùng Spring Boot auto-configuration, cần kiểm tra cách cấu hình `@EnableWs`/servlet và tránh tạo đường dispatch trùng lặp.

Với nhiều interceptors, **thứ tự là quyết định kiến trúc**. Nếu interceptor A tạo trace ID và interceptor B cần đọc nó trong `handleRequest`, hãy đặt A trước B trong chain.

### 5.2. SOAP response có header như thế nào?

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1"
    xmlns:meta="urn:example:orders:meta:v1">
  <soap:Header>
    <meta:CorrelationId>fc5e8d4f-42b7-4810-ae32-f01d5f521afd</meta:CorrelationId>
  </soap:Header>
  <soap:Body>
    <ord:GetOrderResponse>
      <ord:orderId>ORD-42</ord:orderId>
      <ord:state>CREATED</ord:state>
    </ord:GetOrderResponse>
  </soap:Body>
</soap:Envelope>
~~~

Trường hợp này, **response Body** vẫn tuân theo XSD nghiệp vụ cho `GetOrderResponse`. Header dùng namespace metadata riêng và cần được đặc tả trong hợp đồng tích hợp nếu đối tác phụ thuộc nó. Prefix `meta` chỉ là bí danh; client nên kiểm tra QName theo URI + local name.

## 6. Endpoint có thể nhận trực tiếp `MessageContext`

Spring-WS cung cấp `MessageContextMethodArgumentResolver`, hỗ trợ truyền context vào phương thức endpoint khi adapter/resolver phù hợp được đăng ký. Có thể khai báo `MessageContext` như **tham số không cần `@RequestPayload`**, bên cạnh tham số JAXB được đánh dấu `@RequestPayload`.

~~~java
import org.springframework.ws.context.MessageContext;
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;

@Endpoint
public class OrdersEndpoint {

    private static final String NS = "urn:example:orders:v1";
    private final OrderQueryService orderQueryService;

    public OrdersEndpoint(OrderQueryService orderQueryService) {
        this.orderQueryService = orderQueryService;
    }

    @PayloadRoot(namespace = NS, localPart = "GetOrderRequest")
    @ResponsePayload
    public GetOrderResponse getOrder(
            @RequestPayload GetOrderRequest request,
            MessageContext context) {

        String traceId = (String) context.getProperty(
            CorrelationInterceptor.TRACE_ID_PROPERTY);

        // Truyền metadata cần thiết vào ứng dụng bằng giá trị đơn giản.
        OrderView order = orderQueryService.getVisibleOrder(
            request.getOrderId(), traceId);

        GetOrderResponse response = new GetOrderResponse();
        response.setOrderId(order.id());
        response.setState(order.state());
        return response;
    }
}
~~~

`OrderQueryService` và `OrderView` là abstraction của ứng dụng; giả định class JAXB root và setter được sinh phù hợp XSD. Nếu XSD dùng named complex type, JAXB có thể yêu cầu `JAXBElement<T>` và `ObjectFactory` cho response.

Điểm kiến trúc quan trọng:

1. `@RequestPayload` áp dụng cho dữ liệu XML Body, còn tham số `MessageContext` được resolver riêng hỗ trợ.
2. Phương thức lấy trace ID bằng khóa **đã thống nhất** với interceptor.
3. Service nhận một chuỗi/immutable metadata DTO, **không phải toàn bộ `MessageContext`** nếu không có lý do đặc biệt.
4. Nếu không đăng ký interceptor hoặc interceptor chạy theo nhánh khác, `getProperty(...)` có thể trả `null`; phải có quy tắc rõ.
5. Không dùng trace ID này để quyết định danh tính hoặc quyền xem đơn. Authorization cần thông tin **đã xác thực**.

### 6.1. Khi nào nên tránh nhận cả context trong endpoint?

Nếu endpoint chỉ cần business request, tốt hơn để method nhận JAXB request và gọi use case. Không thêm `MessageContext` vào mọi chữ ký “để dành”, vì điều này tăng coupling với Spring-WS.

Khi cần correlation, audit hoặc metadata từ interceptor, có thể:

- Nhận context trực tiếp và tạo một `RequestMetadata` immutable DTO.
- Dùng một abstraction request-scoped do hạ tầng quản lý, nếu dự án đã có.
- Dùng tracer/MDC đúng vòng đời cho mục tiêu logging, nhưng không lạm dụng nó làm nguồn sự thật nghiệp vụ.

Không truyền `MessageContext` vào repository hoặc lưu nó trong domain entity; nó có liên kết đến request/response và chỉ hợp lệ trong một lượt message.

## 7. Đọc một SOAP Header từ client: dữ liệu chưa đáng tin

Nếu client gửi:

~~~xml
<soap:Header
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:meta="urn:example:orders:meta:v1">
  <meta:CorrelationId>partner-a-00042</meta:CorrelationId>
</soap:Header>
~~~

server có thể đọc nó bằng `SoapMessage` và `SoapHeader`:

~~~java
import java.util.Iterator;
import javax.xml.namespace.QName;

import org.springframework.ws.context.MessageContext;
import org.springframework.ws.soap.SoapHeader;
import org.springframework.ws.soap.SoapHeaderElement;
import org.springframework.ws.soap.SoapMessage;

public final class IncomingCorrelationHeaders {

    private static final QName CORRELATION_QNAME =
        new QName("urn:example:orders:meta:v1", "CorrelationId");

    public static String readOptionalCorrelationId(MessageContext context) {
        if (!(context.getRequest() instanceof SoapMessage request)) {
            return null;
        }

        SoapHeader header = request.getSoapHeader();
        Iterator<SoapHeaderElement> matches =
            header.examineHeaderElements(CORRELATION_QNAME);

        if (!matches.hasNext()) {
            return null;
        }

        String candidate = matches.next().getText();

        // Header trùng là lỗi hợp đồng trong chính sách ví dụ.
        if (matches.hasNext()) {
            throw new IllegalArgumentException(
                "Duplicate CorrelationId header");
        }

        if (candidate == null ||
                !candidate.matches("[A-Za-z0-9._:-]{1,64}")) {
            throw new IllegalArgumentException(
                "Invalid CorrelationId header");
        }

        return candidate;
    }
}
~~~

Ở đây method **chỉ minh họa kiểm tra header dữ liệu đơn giản**; một hệ thống thật cần fault mapping chuẩn, giới hạn kích thước XML, parser an toàn, kiểm soát header trùng, charset/format theo contract và kiểm thử từng SOAP version. `getText()` phù hợp với header chứa **text đơn giản**, không phải cách giải mã tổng quát header XML phức tạp.

Sau khi kiểm tra, bạn có thể đặt metadata đã chuẩn hóa vào `MessageContext`:

~~~java
String supplied = IncomingCorrelationHeaders
    .readOptionalCorrelationId(context);

String internalTraceId = UUID.randomUUID().toString();
context.setProperty("orders.internalTraceId", internalTraceId);
context.setProperty("orders.partnerCorrelationId", supplied);
~~~

Nếu muốn dùng ID do partner cung cấp làm ID trả về, hợp đồng và chính sách bảo mật phải nêu rõ. Một cách bảo thủ là **giữ riêng ID partner và ID nội bộ**, tránh kẻ gọi điều khiển tên trace/span của hệ thống quan sát.

### 7.1. SOAP Header và HTTP Header không giống nhau

| Thuộc tính | SOAP Header | HTTP Header |
| --- | --- | --- |
| Vị trí | Bên trong `soap:Envelope/soap:Header` | Phần header của HTTP request/response |
| Ví dụ | `meta:CorrelationId`, `wsse:Security`, `wsa:Action` | `Content-Type`, `SOAPAction`, tracing headers của gateway |
| Định danh chính | QName XML và SOAP semantics | Tên/value theo HTTP |
| Được JAXB đọc như Body? | Không tự động; cần binding/handler phù hợp | Không thuộc JAXB payload |
| Ai có thể sửa/quan sát? | SOAP intermediary/endpoint theo vai trò | HTTP proxies/gateways |
| Đường truy cập | `SoapMessage.getSoapHeader()` | Transport/servlet API ở tầng HTTP |

`MessageContext` không tự cung cấp một HTTP request object chuẩn cho mọi transport. Nếu cần HTTP header, có thể sử dụng abstraction transport/request của môi trường đã cấu hình; tránh hardcode servlet API khi ứng dụng còn hỗ trợ JMS hoặc một transport khác.

### 7.2. Annotation `@SoapHeader` là cách khác, không phải property

Spring-WS có annotation `org.springframework.ws.soap.server.endpoint.annotation.SoapHeader` dùng để bind một SOAP Header element vào tham số endpoint theo **QName**:

~~~java
@PayloadRoot(namespace = NS, localPart = "GetOrderRequest")
@ResponsePayload
public GetOrderResponse getOrder(
        @RequestPayload GetOrderRequest request,
        @org.springframework.ws.soap.server.endpoint.annotation.SoapHeader(
            "{urn:example:orders:meta:v1}CorrelationId")
        SoapHeaderElement correlationHeader) {

    // correlationHeader.getText(): dữ liệu bên ngoài, phải validate.
    // ...
}
~~~

Đây là minh họa chữ ký, lược implementation. Với header tùy chọn, thiếu header hoặc xuất hiện nhiều lần có thể có semantics riêng của resolver/cấu hình; đọc qua `MessageContext` như mục trên giúp diễn tả quy tắc tùy chọn/trùng rõ hơn. **Đừng coi việc bind được header là nó đã được xác thực hoặc nằm trong một transaction.**

### 7.3. `mustUnderstand`, role/actor và khả năng tương thích

SOAP Header còn có metadata giao thức:

- `mustUnderstand` cho biết bên nhận ở vai trò tương ứng phải hiểu/xử lý header hoặc phản hồi fault theo SOAP rules.
- SOAP 1.1 dùng thuật ngữ `actor`; SOAP 1.2 dùng `role`.
- Một header do ứng dụng tự định nghĩa không nên mặc định bật `mustUnderstand` nếu đối tác không có cam kết xử lý.
- Header có tác dụng nghiệp vụ hoặc bảo mật phải có schema, namespace/version và semantics rõ.

Một `@Endpoint` đọc được Header không chứng minh toàn bộ các điều kiện `mustUnderstand` và WS-Security đã được thực hiện. Hãy sử dụng infrastructure và test đúng SOAP version.

## 8. Ngữ cảnh không phải cơ chế bảo mật

### 8.1. Property không tự trở thành trusted principal

Giả sử một interceptor đọc SOAP Header:

~~~xml
<meta:UserRole xmlns:meta="urn:example:orders:meta:v1">ADMIN</meta:UserRole>
~~~

và đặt:

~~~java
context.setProperty("userRole", "ADMIN");
~~~

Điều này **không làm caller trở thành admin**. Dữ liệu do client gửi là không đáng tin cho đến khi được xác thực và ủy quyền theo policy.

Đối với WS-Security, sử dụng thành phần chuyên trách, ví dụ `Wss4jSecurityInterceptor`, để xác minh signature, timestamp, token/encryption theo cấu hình. Với HTTPS/mTLS, xác minh certificate chain, hostname và client identity tại transport. Sau đó application service phải kiểm tra quyền đối với order cụ thể.

Nếu muốn đưa identity đã xác thực vào một request metadata DTO, phải rõ **thành phần nào đã xác minh**, giá trị đến từ nguồn nào và nó được truyền qua những boundary nào. Một property không có cơ chế chống giả mạo chỉ vì nó nằm trong `MessageContext`.

### 8.2. Thứ tự interceptor ảnh hưởng tính đáng tin

Nếu interceptor A đọc Header rồi gắn `orders.userId`, trong khi interceptor B mới kiểm chữ ký ở bước sau, endpoint không được mặc nhiên coi mọi property do A gắn là đáng tin. Một thiết kế an toàn là các thành phần xác thực phải hoàn thành trước khi tạo/tiêu thụ **trusted identity metadata**, và mọi nhánh từ chối phải dừng endpoint invocation.

Vì thứ tự interceptor và ranh giới transport có thể phức tạp, nên chọn một **security context/identity adapter** đáng tin đã được test, thay vì tự phát minh chuỗi property cho authorization.

### 8.3. XML Signature wrapping và QName

SOAP XML có thể chứa nhiều Header, Body, namespace và phần tử trùng local name. Nếu thành phần bảo mật xác minh một XML node nhưng mapper/endpoint dùng node khác, hệ thống có thể bị đánh lừa. Tránh XPath quá rộng như `//*[local-name()='GetOrderRequest']` và không tự tuyên bố chữ ký hợp lệ chỉ vì tìm thấy `<Signature>`.

`@PayloadRoot` định tuyến theo QName của phần tử gốc trong Body; WS-Security phải đảm bảo phần tử **thực sự được xử lý** chính là phần tử đã được xác thực theo chính sách.

### 8.4. Những thứ không nên lưu trong property

- Password, private key, raw token hoặc SOAP XML nhạy cảm không có nhu cầu.
- JPA entity hoặc persistence context sống dài hơn một lượt xử lý.
- Input stream hoặc XML parser cursor đã bị tiêu thụ rồi trông chờ thành phần sau đọc lại.
- Mutable collection dùng chung với worker thread mà không có đồng bộ.
- Dữ liệu có kích thước không giới hạn lấy từ Header chưa validate.

Nguyên tắc **minimize retention**: lưu metadata nhỏ, đã chuẩn hóa, dùng đúng mục đích và dọn dẹp sau khi hoàn thành.

## 9. `MessageContext`, MDC và threading là ba khái niệm khác nhau

### 9.1. Bean singleton xử lý nhiều SOAP requests đồng thời

Một `@Endpoint` hoặc interceptor Spring thường được tạo một lần và phục vụ nhiều request đồng thời. Không lưu dữ liệu riêng của request vào field:

~~~java
// SAI: dễ bị request khác ghi đè khi chạy đồng thời.
@Component
public class BrokenTraceInterceptor extends EndpointInterceptorAdapter {
    private String currentTraceId;

    @Override
    public boolean handleRequest(MessageContext context, Object endpoint) {
        currentTraceId = UUID.randomUUID().toString();
        return true;
    }
}
~~~

Nếu request A và B xen kẽ nhau, `currentTraceId` có thể chứa ID của B khi A tạo response. Dùng `MessageContext.setProperty(...)` sẽ giữ ID theo mỗi lượt xử lý.

### 9.2. Mapped Diagnostic Context (MDC) có vòng đời thread

Nếu hệ thống dùng SLF4J MDC:

~~~java
@Override
public boolean handleRequest(MessageContext context, Object endpoint) {
    String traceId = UUID.randomUUID().toString();
    context.setProperty(TRACE_ID_PROPERTY, traceId);
    MDC.put("traceId", traceId);
    return true;
}

@Override
public void afterCompletion(
        MessageContext context, Object endpoint, Exception ex) {
    MDC.remove("traceId");
    context.removeProperty(TRACE_ID_PROPERTY);
}
~~~

Đây là **mẫu ý tưởng**, các phương thức đặt vào một interceptor có import `org.slf4j.MDC`. Trong một request đồng bộ bình thường, MDC hỗ trợ đưa trace ID vào log trong cùng thread.

Nhưng:

- MDC thường dùng `ThreadLocal`; nó **không tự lan** tới các worker threads hoặc các callback bất đồng bộ.
- Thread của servlet container có thể được **tái sử dụng**, nên MDC phải được dọn đúng cách.
- `afterCompletion` chỉ được gọi đối với interceptor đã hoàn tất `handleRequest` theo lifecycle; nếu đặt MDC rồi ném exception trước khi trả `true`, chính interceptor đó phải cleanup trong nhánh lỗi.
- Nếu application chuyển thread trước khi callback kết thúc, cần propagation và cleanup theo cơ chế async/tracing chính thức; không mặc định cùng thread.
- Một SOAP Header do client cung cấp không được dùng trực tiếp làm MDC value nếu chưa kiểm tra/normalize, tránh log injection hoặc cardinality bùng nổ.

### 9.3. Đừng giữ `MessageContext` sau khi request kết thúc

Nếu endpoint tạo job bất đồng bộ:

~~~java
// NÊN TRÁNH:
executor.submit(() -> processLater(messageContext));
~~~

Thread khác có thể nhìn request/response đã thay đổi, resource đã đóng hoặc context không còn hợp lệ. Thay bằng **immutable snapshot** dữ liệu tối thiểu:

~~~java
record ProcessingMetadata(String traceId, String orderId) {}

ProcessingMetadata metadata = new ProcessingMetadata(
    (String) context.getProperty(TRACE_ID_PROPERTY),
    request.getOrderId());

jobService.enqueueDurably(metadata);
~~~

Đoạn này minh họa về mặt mô hình; `enqueueDurably` phải thật sự lưu bền vững nếu SOAP response cam kết job đã được tiếp nhận. Với sự kiện nghiệp vụ cần bảo đảm qua crash, có thể dùng transactional outbox. **Property trong MessageContext không phải cơ chế lưu trạng thái giữa các SOAP retries.**

## 10. Fault path: ngữ cảnh giúp gì và không giúp gì?

Những lỗi khác nhau có thể xảy ra ở các thời điểm khác nhau:

| Điểm lỗi | Endpoint đã chạy? | Có thể còn `MessageContext` property? | Điều cần kiểm tra |
| --- | --- | --- | --- |
| HTTP route sai / TLS thất bại | Chưa | Không có context endpoint | Gateway/transport logs |
| SOAP XML parse lỗi trước mapping | Chưa | Không bảo đảm interceptor đã chạy | Parser/message factory |
| Không tìm được endpoint mapping | Chưa | Endpoint interceptor không bảo đảm chạy | Dispatcher/mapping |
| XSD validation từ chối trong interceptor | Chưa | Phụ thuộc thứ tự interceptor đã chạy | Validation + fault |
| WS-Security verification thất bại | Chưa cho chạy nghiệp vụ | Phụ thuộc thứ tự security interceptor | Chữ ký/token/timestamp |
| Business service ném exception | Có thể đã vào | Thường còn trong cùng lượt xử lý | Resolver/fault detail |
| Response serialization lỗi | Endpoint đã chạy hoặc service đã hoàn tất | Có thể còn context, nhưng không luôn tạo fault trọn vẹn | Marshalling/transport |
| Client disconnect | Có thể đã hoàn tất | Không chứng minh client đã nhận response | Retry/idempotency |

Ví dụ khi application service ném `OrderNotFoundException`, `EndpointExceptionResolver` có thể tạo SOAP Fault. Nếu interceptor correlation đã chạy thành công và fault response có sẵn trong context, `handleFault` có thể gắn correlation ID để client đối chiếu log.

Tuy nhiên, **một SOAP Fault có trace ID không chứng minh transaction đã rollback**. Nếu lỗi phát sinh sau khi DB commit, client có thể vẫn cần retry/query status an toàn; đây là vấn đề hợp đồng nghiệp vụ, không được giải quyết chỉ bằng `MessageContext`.

### 10.1. Header trên SOAP Fault

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:meta="urn:example:orders:meta:v1">
  <soapenv:Header>
    <meta:CorrelationId>fc5e8d4f-42b7-4810-ae32-f01d5f521afd</meta:CorrelationId>
  </soapenv:Header>
  <soapenv:Body>
    <soapenv:Fault>
      <faultcode>soapenv:Client</faultcode>
      <faultstring>Order not found</faultstring>
    </soapenv:Fault>
  </soapenv:Body>
</soapenv:Envelope>
~~~

Ví dụ SOAP 1.1 chỉ minh họa khả năng có Header cùng với Fault. SOAP 1.2 dùng cấu trúc Fault khác. Với lỗi diễn ra rất sớm, hoặc khi response đã bị gửi một phần, không bảo đảm tạo được Header/Fault hoàn chỉnh.

## 11. SOAP Header thuộc hợp đồng, property nội bộ thì không

Nếu đối tác yêu cầu `CorrelationId` ở response, định nghĩa chính sách:

| Câu hỏi | Cần thống nhất |
| --- | --- |
| Header QName là gì? | `{urn:example:orders:meta:v1}CorrelationId` |
| Có bắt buộc không? | Có trên success/fault được phát từ endpoint, hay best-effort? |
| Định dạng? | UUID do server cấp hoặc ID của partner, max length rõ |
| Có echo nguyên bản client ID không? | Chỉ sau validation và chính sách bảo mật |
| Có `mustUnderstand` không? | Chỉ bật khi hai bên hiểu và xử lý theo SOAP semantics |
| Có được WS-Security ký số không? | Phụ thuộc threat model và WSDL/policy |
| Header absent/trùng phải xử lý thế nào? | Xác định fault/fallback rõ |
| Một operation có dùng cùng header với operation khác? | Version hóa và test tương thích |

Nếu client generator cần biết Header là một phần interface, có thể khai báo trong WSDL 1.1 binding bằng `soap:header` tham chiếu `wsdl:message/part` cùng global element schema tương ứng. Đối với một Header chỉ là tùy chọn kỹ thuật, có thể công bố bằng tài liệu bổ sung nhưng phải đánh giá nhu cầu interoperability của đối tác.

**Đừng nhầm:** việc thêm `header.addHeaderElement(...)` vào response **không tự thêm phần định nghĩa Header vào WSDL**; chỉ định nghĩa `wsdl:part` cũng **không tự khiến interceptor truyền dữ liệu**. Contract và implementation phải được kết nối và kiểm thử riêng.

### 11.1. Ví dụ XSD cho một Header text

~~~xml
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    targetNamespace="urn:example:orders:meta:v1"
    xmlns:meta="urn:example:orders:meta:v1"
    elementFormDefault="qualified">

  <xs:simpleType name="CorrelationIdType">
    <xs:restriction base="xs:string">
      <xs:minLength value="1"/>
      <xs:maxLength value="64"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="CorrelationId"
              type="meta:CorrelationIdType"/>
</xs:schema>
~~~

Đây là XSD **riêng** cho metadata header, không phải một phần tử bên trong `GetOrderRequest`. Nếu sử dụng WSDL static, cần import/include schema đúng namespace và tham chiếu QName ở phần binding theo hợp đồng.

## 12. Cần chia sẻ thông tin nào trong một lần xử lý?

### 12.1. Phân loại theo sự cần thiết

| Loại thông tin | Có phù hợp để là property? | Giải thích |
| --- | --- | --- |
| Correlation ID nội bộ | Có | Nhỏ, immutable, dùng giữa interceptor và endpoint |
| Thời điểm bắt đầu đo latency | Có | Một `long`/`Instant` dùng cho metric |
| Cờ audit đã ghi | Có, nếu scope ngắn | Tránh lặp trong cùng một request; không thay persistence |
| Operation QName đã chuẩn hóa | Có, khi thật sự cần | Để log/metric, không thay mapping |
| Kết quả kiểm tra header đã chuẩn hóa | Có, với ranh giới tin cậy rõ | Không dùng thay authorization |
| Principal/tài khoản đã xác thực | Chỉ khi policy cho phép và nguồn tin cậy | Ưu tiên security context adapter chuyên trách |
| Mã `requestId` nghiệp vụ | Thường ở JAXB request/application command | Nếu cần truy cập ngang, đừng tạo hai nguồn sự thật |
| Object JPA lớn/lazy | Không nên | Dễ vượt ranh giới transaction |
| Full SOAP Envelope thô | Không nên | Nặng và có thể chứa dữ liệu nhạy cảm |
| Password, token, private key | Không | Bí mật không nên nhân bản vào property |
| Trạng thái job cần tồn tại sau response | Không | Cần database/queue/outbox |
| Dữ liệu của session giữa nhiều lần gọi | Không | MessageContext không phải session store |

### 12.2. Đặt tên khóa và hợp đồng nội bộ

Tránh các khóa dễ xung đột như `"user"`, `"id"`, `"status"`. Có thể đặt:

~~~java
public final class SoapContextKeys {
    private SoapContextKeys() {}

    public static final String TRACE_ID =
        "com.example.orders.soap.traceId";

    public static final String STARTED_AT_NANOS =
        "com.example.orders.soap.startedAtNanos";
}
~~~

Dù API nhận `String` và `Object`, hãy quy định **kiểu dữ liệu** của từng khóa; ví dụ `TRACE_ID` luôn là `String`, `STARTED_AT_NANOS` luôn là `Long`. Gắn tên có prefix không phải namespace XML và không mang tính bảo mật; đây chỉ là quy ước tránh va chạm.

Với ứng dụng phức tạp, một DTO bất biến như `RequestMetadata(traceId, receivedAt, authenticatedTenant)` có thể tốt hơn nhiều property rời rạc, miễn thông tin xác thực đến từ thành phần tin cậy và không làm lộ secret.

## 13. Kiểm thử ngữ cảnh, header và khả năng tương thích

### 13.1. Ma trận kiểm thử

| Ca kiểm thử | Kỳ vọng | Lớp cần xác minh |
| --- | --- | --- |
| Hai SOAP requests khác nhau | Hai `traceId` độc lập | Không dùng field singleton |
| Interceptor `setProperty` rồi endpoint đọc | Cùng ID trong một lượt dispatch | `MessageContextMethodArgumentResolver` |
| Chỉ kiểm `hasResponse()` | Không tạo response rỗng | Lazy response semantics |
| Response thành công | Có `meta:CorrelationId` khi policy yêu cầu | `handleResponse` + SOAP Header |
| SOAP Fault sau khi interceptor chạy | Có cùng correlation ID nếu fault response đã tạo | `handleFault` |
| Fault trước mapping/parse | Không giả định interceptor chạy | Transport/dispatcher instrumentation |
| Request thiếu correlation Header tùy chọn | Tạo server ID hoặc xử lý theo policy | Header parser/fallback |
| Hai correlation headers trùng QName | Từ chối hoặc xử lý theo chính sách công bố | Header validation |
| Header có CR/LF/ký tự lạ hoặc quá dài | Không đưa trực tiếp vào log | Input validation |
| Client đổi prefix, giữ namespace URI | Header vẫn được nhận diện | QName semantics |
| Client đổi namespace header | Không coi là cùng header v1 | Contract versioning |
| Dữ liệu `buyerId` trong Header không có chữ ký | Không tự trở thành danh tính đáng tin | WS-Security/authorization |
| Response chỉ có Body nhưng contract đòi Header | Test thất bại | WSDL + wire assertions |
| SOAP 1.2 client với header `mustUnderstand` | Xử lý theo SOAP 1.2 role/semantics | SOAP version interoperability |
| Tác vụ async giữ `MessageContext` | Bị tránh; metadata truyền bằng immutable snapshot | Thread/lifecycle |
| Interceptor dọn MDC sau request | Không rò trace sang request tiếp theo trên reused thread | MDC lifecycle |
| Client retry do timeout | Context mới, idempotency state nằm ở store bền vững | Domain retry contract |

### 13.2. Unit test tối thiểu cho interceptor

Với Mockito, có thể chứng minh interceptor **đặt property nhưng không chủ động tạo response trong `handleRequest`**:

~~~java
@Test
void requestInterceptorStoresTraceWithoutCreatingResponse() {
    MessageContext context = mock(MessageContext.class);
    Object endpoint = new Object();
    CorrelationInterceptor interceptor = new CorrelationInterceptor();

    assertTrue(interceptor.handleRequest(context, endpoint));

    verify(context).setProperty(
        eq(CorrelationInterceptor.TRACE_ID_PROPERTY),
        any(String.class));

    verify(context, never()).getResponse();
}
~~~

Test giả định JUnit/Mockito đã có; `MessageContext` là mock nên không tự giữ property. Các test khác cần dùng implementation/context thực hoặc mock có state để kiểm tra round-trip.

### 13.3. Spring-WS test trên đường XML

`MockWebServiceClient` cho phép gửi payload qua dispatcher/test context rồi kiểm tra response. Nếu muốn test SOAP Header ngoài Body:

1. Tạo request SOAP có Header `meta:CorrelationId`, thông qua callback của `RequestCreator` hoặc công cụ tạo SOAP message của Spring-WS Test phù hợp.
2. Đăng ký interceptor và endpoint trong test context.
3. Gửi request đúng payload `{urn:example:orders:v1}GetOrderRequest`.
4. Kiểm tra SOAP response Header theo QName `{urn:example:orders:meta:v1}CorrelationId` và giá trị text; đừng yêu cầu prefix cố định.
5. Gửi request thứ hai, đảm bảo ID không rò từ request thứ nhất.
6. Tạo business exception → SOAP Fault, xác minh header/tracing theo phạm vi policy.
7. Dùng cấu hình SOAP 1.1 và SOAP 1.2 khi cần interoperability.

`MockWebServiceServer` ở phía `WebServiceTemplate` phù hợp để kiểm tra client phát Header đúng hợp đồng và xử lý response/fault. Với client Java/.NET thực tế, tải WSDL/XSD và kiểm tra giao tiếp trên wire, không chỉ kiểm tra object Java.

### 13.4. Test thứ tự interceptor

Một test thứ tự hữu ích:

~~~text
Request phase:
  A.handleRequest: tạo traceId
  B.handleRequest: đọc traceId, ghi log
  Endpoint: đọc traceId và gọi service

Response phase:
  B.handleResponse
  A.handleResponse: thêm CorrelationId Header

Completion:
  B.afterCompletion
  A.afterCompletion: cleanup
~~~

Đây là thứ tự điển hình khi A, B đều `handleRequest=true` và không có lỗi cắt ngắn chain. Nếu B trả `false` hoặc ném exception, callbacks có thể khác. Cần test các nhánh có thể xảy ra trong ứng dụng thay vì giả định mọi callback đều luôn chạy.

## 14. Các lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Lưu trace ID trong field interceptor singleton | Requests đồng thời ghi đè nhau | `MessageContext` property |
| Gọi `getResponse()` ở `handleRequest` chỉ để xem có chưa | Tạo response sớm ngoài ý muốn | Dùng `hasResponse()` |
| Tưởng `setProperty` tự ghi SOAP Header | Client không bao giờ thấy metadata | Thêm Header tường minh ở response |
| Tưởng có SOAP Header là đã được xác thực | Có thể tin dữ liệu giả mạo | WS-Security/TLS + authorization |
| Lấy `UserRole` từ Header làm quyền | Privilege escalation | Trusted principal/policy |
| Dùng local name bỏ qua namespace | Nhầm header giữa version | QName đầy đủ |
| Log toàn bộ SOAP Envelope/WSSE token | Lộ dữ liệu nhạy cảm | Log metadata đã che/giới hạn |
| Không dọn MDC trên thread tái sử dụng | Trace ID rò sang request khác | Cleanup đúng lifecycle |
| Giữ context trong `@Async` job sau response | Resource hết hạn, trạng thái race | Immutable snapshot + durable store |
| Đặt object JPA lazy vào context | Rò transaction/serialization lỗi | DTO nhỏ, bất biến |
| Không định nghĩa Header trong WSDL khi đối tác cần | Sinh client không biết header | WSDL binding/schema + tests |
| Chỉ test Body, bỏ Header/Fault | Không phát hiện hợp đồng metadata sai | SOAP-aware integration tests |
| Dùng context như session store | Mất state ở request kế tiếp | DB/cache/queue có chính sách |
| Interceptor gắn endpoint được coi là bảo vệ mọi URL | Request không map có thể không chạy interceptor | Gateway/filter/transport policy |
| Bật `mustUnderstand` tùy tiện | Đối tác không hiểu header sẽ Fault | Thiết kế theo SOAP semantics |

## 15. Quy trình triển khai một chính sách request context

~~~mermaid
flowchart TD
    A["Xác định metadata cần chia sẻ"] --> B{"Có cần client thấy?"}
    B -- "Không" --> C["MessageContext property"]
    B -- "Có" --> D["Thiết kế SOAP Header QName + contract"]
    C --> E["Xác định nguồn tin cậy và lifecycle"]
    D --> E
    E --> F["Interceptor: đọc/validate/tạo metadata"]
    F --> G["Endpoint: dùng property/metadata DTO"]
    G --> H["Application service: quyền và nghiệp vụ"]
    H --> I["Response/Fault: gắn Header nếu có"]
    I --> J["Cleanup MDC; kiểm thử concurrency/fault"]
~~~

Trước khi triển khai, hãy trả lời:

1. Dữ liệu là **metadata kỹ thuật** hay **payload nghiệp vụ**?
2. Nó phải được client nhìn thấy hay chỉ lưu nội bộ server?
3. Nó đến từ nguồn đáng tin, client, gateway hay thành phần WS-Security?
4. Khóa property, kiểu dữ liệu và chủ sở hữu được quy định ở đâu?
5. Thời điểm nào value được tạo, đọc và dọn?
6. Response có thể chưa tồn tại khi interceptor chạy hay không?
7. Fault path có bảo đảm header không, và nhánh lỗi sớm phải quan sát thế nào?
8. Có luồng async/thread khác hay retry mới cần truyền metadata bằng cách khác?
9. WSDL/XSD/WS-Policy có mô tả header khi đối tác phụ thuộc nó không?
10. Test nào chứng minh không có state rò giữa requests, không lộ secret và không nhầm namespace?

### Câu hỏi tự kiểm tra

1. `MessageContext.setProperty(...)` khác `SoapHeader.addHeaderElement(...)` thế nào?
2. Vì sao `getResponse()` không nên dùng để “kiểm tra response đã tồn tại”?
3. `handleRequest` và `handleResponse` có thể chia sẻ trace ID bằng cách nào?
4. `MessageContext` có được tự động tái sử dụng giữa hai lần gọi SOAP không?
5. Tại sao không nên đặt `currentTraceId` thành field của interceptor singleton?
6. Có thể inject `MessageContext` trực tiếp vào method `@Endpoint` không? Có phải gắn `@RequestPayload` không?
7. Vì sao Header `UserRole=ADMIN` do client gửi không đủ để cho phép truy cập?
8. Khi client đổi prefix XML nhưng giữ namespace URI, việc đọc Header theo QName có thay đổi không?
9. Khi SOAP Fault xuất hiện trước khi endpoint mapping, có thể kỳ vọng `handleFault` của endpoint interceptor đã chạy không?
10. MDC qua `ThreadLocal` có tự xuất hiện trong một `@Async` worker không?
11. Muốn client nhận `CorrelationId` trên response, cần thêm bước runtime và bước mô tả hợp đồng nào?
12. Khi một downstream job cần trace ID sau response, nên giữ `MessageContext` hay truyền snapshot nhỏ và lưu job bền vững?

## Tài liệu tham khảo

- [Spring-WS API — MessageContext](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/context/MessageContext.html): request/response, lazy `getResponse()` và property API.
- [Spring-WS API — EndpointInterceptor](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/server/EndpointInterceptor.html): `handleRequest`, `handleResponse`, `handleFault` và `afterCompletion`.
- [Spring-WS API — MessageContextMethodArgumentResolver](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/server/endpoint/adapter/method/MessageContextMethodArgumentResolver.html): truyền context vào endpoint method.
- [Spring-WS API — SoapHeader và SoapHeaderElement](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/soap/SoapHeader.html): truy xuất, thêm SOAP Header theo QName và set text.
- [Spring Web Services Reference](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/): endpoint, interceptor và các nguyên tắc trao đổi SOAP.

**Ghi nhớ:** `MessageContext` là **ngữ cảnh của một lượt xử lý Spring-WS**, giữ request, response và những property nội bộ. Nó giúp interceptor và endpoint chia sẻ metadata mà **không biến metadata thành XML hoặc trạng thái lâu dài**. Muốn gửi thông tin cho đối tác, phải thêm **SOAP Header** theo QName và mô tả hợp đồng; muốn xác thực phải dùng **security policy**; muốn xử lý retry/async phải lưu trạng thái ngoài request. Đặc biệt, kiểm tra response bằng `hasResponse()` để tránh vô tình tạo response rỗng bằng `getResponse()`.
