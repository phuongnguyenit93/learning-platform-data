# Định danh yêu cầu, thông tin tương quan và truyền qua nhiều hệ thống

Trong hệ thống doanh nghiệp, một SOAP request hiếm khi chỉ đi từ client đến một server rồi kết thúc. Dịch vụ nhận đơn hàng có thể gọi dịch vụ kho, thanh toán, vận chuyển, sau đó phát sự kiện vào hàng đợi để xử lý bất đồng bộ. Khi một bước thất bại, câu hỏi quan trọng không chỉ là **“SOAP Fault nào đã xảy ra?”** mà còn là **“Những bản tin, log và thao tác ở các hệ thống khác nhau có thuộc cùng một yêu cầu nghiệp vụ không?”**

Đó là mục đích của **định danh yêu cầu** (*request identification*), **thông tin tương quan** (*correlation context*) và **truyền ngữ cảnh qua nhiều hệ thống** (*context propagation*). Trong **Spring Web Services (Spring-WS)**, thông tin này có thể xuất hiện ở SOAP Header, HTTP headers, WS-Addressing, distributed tracing context và log metadata; **không nên đưa tất cả thành một trường trong SOAP Body**.

Bài học thuộc chương **Header và ngữ cảnh**, đặt trong quy trình **contract-first** với XSD/WSDL, JAXB, SOAP endpoint/client, interceptor, SOAP Fault, XML security, WS-Security, chứng chỉ và kiểm thử tương thích. Ví dụ dùng SOAP 1.1, namespace nghiệp vụ `urn:example:orders:v1` và namespace header `urn:example:context:v1`. Các địa chỉ, ID và tên công ty đều là dữ liệu minh họa.

## 1. Bài toán: một yêu cầu đi qua nhiều dịch vụ

Giả sử bên mua gửi yêu cầu tạo đơn qua Spring-WS. Service đơn hàng gọi kho và thanh toán; một worker bất đồng bộ gửi thông báo khi giao dịch hoàn tất.

~~~mermaid
sequenceDiagram
    participant C as Client đối tác
    participant G as API Gateway
    participant O as Orders SOAP
    participant I as Inventory SOAP
    participant P as Payment SOAP
    participant Q as Event Broker
    participant N as Notification Worker

    C->>G: POST CreateOrder
    Note over C,G: correlationId = C-27A
    G->>O: SOAP request + correlationId
    O->>I: CheckStock + correlationId
    I-->>O: StockAvailable
    O->>P: ReservePayment + correlationId
    P-->>O: PaymentAccepted
    O->>Q: OrderCreated event + correlationId
    O-->>G: CreateOrderResponse + correlationId
    G-->>C: SOAP response
    Q-->>N: Event carries correlationId
    N->>N: Ghi log và gửi thông báo
~~~

Nếu mỗi service tự sinh một ID rồi không lưu quan hệ, việc lần ngược lỗi từ worker về request của client sẽ rất khó. Ngược lại, nếu mọi thao tác chỉ dùng **một ID duy nhất**, hệ thống lại không phân biệt được đâu là một HTTP request cụ thể, một SOAP message, một lần retry, một span trace hay một nghiệp vụ có tính idempotent.

Thiết kế hợp lý thường có **nhiều ID với phạm vi và vòng đời riêng**.

## 2. Phân biệt các định danh quan trọng

| Định danh | Phạm vi | Có thay khi gọi dịch vụ khác? | Công dụng chính |
| --- | --- | --- | --- |
| **Correlation ID** | Toàn bộ luồng nghiệp vụ hoặc chuỗi tác vụ cần theo dõi. | **Thường giữ nguyên** xuyên các hop cùng luồng. | Tìm log, SOAP request/response và sự kiện liên quan. |
| **Request ID** | Một lần xử lý HTTP/SOAP inbound tại một service. | **Thường tạo mới** ở mỗi hop inbound. | Phân biệt từng request cụ thể, kể cả cùng correlation. |
| **Message ID** | Một thông điệp SOAP/event riêng lẻ. | **Thường mới** cho từng message; theo quy tắc chuẩn đang áp dụng. | Nhận diện bản tin, liên kết request với response, chống xử lý lặp ở tầng messaging khi có thiết kế bổ sung. |
| **Trace ID** | Một distributed trace. | Giữ nguyên trong các span thuộc cùng trace. | Phân tích đường đi/latency bằng tracing backend. |
| **Span ID** | Một đơn vị công việc trong trace. | **Thay đổi** theo span. | Xác định quan hệ parent/child, timing từng thao tác. |
| **Idempotency key** | Một ý định thực hiện tác vụ nghiệp vụ có thể bị gửi lặp. | **Giữ nguyên khi retry cùng ý định**, thay khi là tác vụ mới. | Ngăn tạo đơn/thanh toán lặp khi request được gửi lại. |
| **Business ID** | Thực thể nghiệp vụ, ví dụ `orderId`. | Ổn định theo vòng đời thực thể. | Truy vấn trạng thái nghiệp vụ; không nhất thiết tồn tại trước xử lý. |
| **Attempt ID** | Một lần thử network/processing cụ thể. | **Mới ở mỗi lần retry**. | Phân biệt lỗi lần 1, lần 2, backoff và diagnostic. |

Không có quy định phổ quát rằng một trường tên `requestId` phải mang cùng ý nghĩa trong mọi công ty. Cần **định nghĩa contract nội bộ/đối tác**: ai cấp phát ID, phạm vi duy nhất, giới hạn độ dài, thời gian sống, chính sách retry và mức độ tin cậy.

### 2.1. Ví dụ với một lần retry

Client gửi `CreateOrder` lần thứ nhất và không nhận được response vì kết nối bị ngắt sau khi server có thể đã tạo đơn.

| Giá trị | Lần gửi thứ nhất | Retry cùng ý định |
| --- | --- | --- |
| `correlationId` | `corr-27a` | `corr-27a` |
| `idempotencyKey` | `create-order-9b2` | `create-order-9b2` |
| `requestId` ở gateway | `req-01` | `req-02` |
| `attemptId` | `try-01` | `try-02` |
| HTTP connection | Kết nối A | Kết nối B |
| `orderId` | Có thể đã được tạo | Phải tra cứu kết quả trước khi tạo mới |

**Correlation ID không phải idempotency key**. Giữ correlation ID chỉ giúp truy vết, không tự ngăn hệ thống tạo hai đơn hàng. Nếu cần idempotency, server phải lưu/kiểm tra khóa trong phạm vi thích hợp, xử lý atomicity và định nghĩa cách trả kết quả khi yêu cầu trùng.

### 2.2. Sinh ID và tránh đưa dữ liệu nhạy cảm vào ID

Ở lớp tích hợp, có thể dùng UUID ngẫu nhiên hoặc định dạng ID được tổ chức chuẩn hóa, ví dụ:

~~~java
import java.util.UUID;

String correlationId = UUID.randomUUID().toString();
String requestId = UUID.randomUUID().toString();
~~~

Một UUID ngẫu nhiên phù hợp mục tiêu xác suất va chạm thấp trong nhiều hệ thống, nhưng **không tự tạo xác thực, ủy quyền hay sự đảm bảo tính duy nhất mang tính giao dịch**. Để đảm bảo uniqueness ở nghiệp vụ, cần constraint/storage theo thiết kế.

Không tạo correlation ID bằng email, số điện thoại, số tài khoản, access token hoặc nội dung SOAP Body. Những chuỗi này dễ lọt vào log, header, trace export và hệ thống monitoring; chúng còn có thể làm lộ dữ liệu khi chuyển tiếp qua đối tác.

## 3. Correlation context nên đặt ở đâu?

Trong một tích hợp Spring-WS, có bốn vị trí chính:

| Vị trí | Ví dụ | Đặc điểm |
| --- | --- | --- |
| **SOAP Header** | `<ctx:CorrelationId>...</ctx:CorrelationId>` | Thông tin ở tầng SOAP, có namespace; có thể khai báo trong WSDL/XSD và bảo vệ bằng WS-Security. |
| **HTTP Header** | `X-Request-ID` hoặc `traceparent` | Tầng transport; gateway, proxy và tracing middleware có thể đọc trước SOAP parser. |
| **WS-Addressing Header** | `wsa:MessageID`, `wsa:RelatesTo`, `wsa:Action` | Ngữ nghĩa chuẩn hóa cho message identity và quan hệ giữa các SOAP message khi stack hỗ trợ. |
| **Nội bộ ứng dụng** | MDC, `MessageContext`, tracing `Context` | Sử dụng trong phạm vi xử lý để log/metrics/tracing; không tự đi qua mạng. |

Chọn nơi truyền dựa vào hợp đồng và kiến trúc. **Không đồng nhất** các kênh: thêm `traceparent` vào HTTP header không làm Spring-WS `@SoapHeader` tự nhận được nó, và đặt `CorrelationId` vào SOAP Header không tự đưa nó vào MDC hay hàng đợi sự kiện.

### 3.1. SOAP Header chứa correlation và request ID

Một SOAP 1.1 request minh họa:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ctx="urn:example:context:v1"
    xmlns:ord="urn:example:orders:v1">
  <soap:Header>
    <ctx:CorrelationId>corr-27a</ctx:CorrelationId>
    <ctx:RequestId>req-01</ctx:RequestId>
  </soap:Header>
  <soap:Body>
    <ord:CreateOrderRequest>
      <ord:clientOrderId>WEB-20261127-0042</ord:clientOrderId>
      <ord:amount>1250000.00</ord:amount>
    </ord:CreateOrderRequest>
  </soap:Body>
</soap:Envelope>
~~~

Trong SOAP, **Header và Body có trách nhiệm khác nhau**:

- Header mô tả metadata về xử lý/định tuyến/điều phối thông điệp; ví dụ `CorrelationId` và `RequestId`.
- Body chứa yêu cầu nghiệp vụ `CreateOrderRequest` theo XSD; Spring-WS có thể dùng `@PayloadRoot` để chọn method dựa trên QName này.
- HTTP header chứa metadata vận chuyển, ví dụ `Content-Type`, `SOAPAction` (SOAP 1.1) hoặc `traceparent` khi đã thỏa thuận.

Namespace URI `urn:example:context:v1` là định danh logic của các phần tử header. Prefix `ctx` chỉ là bí danh XML, có thể đổi mà QName vẫn giữ nguyên. **Không parse SOAP Header bằng cách tìm chuỗi `"<ctx:CorrelationId>"`**, vì prefix, whitespace và serialization có thể khác.

### 3.2. SOAP Header không tự có nghĩa bắt buộc

Trong SOAP 1.1, thuộc tính `soap:mustUnderstand="1"` yêu cầu recipient phù hợp phải hiểu và xử lý header đó; nếu không, có thể phát SOAP `MustUnderstand` Fault. Với SOAP 1.2, giá trị/định nghĩa và role có khác biệt về namespace và diễn giải.

Ví dụ:

~~~xml
<ctx:CorrelationId
    xmlns:ctx="urn:example:context:v1"
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    soap:mustUnderstand="1">corr-27a</ctx:CorrelationId>
~~~

Không bật `mustUnderstand` chỉ vì “header quan trọng”. Nếu đối tác hoặc message processor chưa đăng ký xử lý header theo SOAP semantics, bản tin hợp lệ về XML vẫn có thể bị từ chối. Khi hợp đồng bắt buộc header correlation, cần thiết kế rõ SOAP processor sẽ xử lý gì, bên nào là recipient, hành vi thiếu/sai header và Fault tương ứng.

**Correlation ID chưa được xác thực chỉ là metadata không đáng tin**. Không dùng nó để xác định tenant, user, scope hoặc quyền giao dịch; các quyết định đó thuộc authentication/authorization và WS-Security/TLS.

## 4. Thiết kế XSD và WSDL cho custom correlation header

Trong mô hình **contract-first**, nếu đối tác buộc phải gửi correlation header, việc tài liệu hóa mỗi “gửi một header nhé” là chưa đủ. Cần chỉ rõ namespace, element name, kiểu, giới hạn và các SOAP binding sử dụng header.

### 4.1. XSD cho header metadata

File `context.xsd` minh họa, XSD 1.0 tự chứa:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           targetNamespace="urn:example:context:v1"
           xmlns:ctx="urn:example:context:v1"
           elementFormDefault="qualified">

  <xs:simpleType name="IdentifierType">
    <xs:restriction base="xs:token">
      <xs:minLength value="1"/>
      <xs:maxLength value="64"/>
      <xs:pattern value="[A-Za-z0-9][A-Za-z0-9._:-]*"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="CorrelationId" type="ctx:IdentifierType"/>
  <xs:element name="RequestId" type="ctx:IdentifierType"/>
</xs:schema>
~~~

Quy tắc này chấp nhận những ID minh họa như `corr-27a` hoặc UUID, từ chối chuỗi trắng/không hợp mẫu và giảm rủi ro log injection. Nó **không thay thế** việc giới hạn kích thước HTTP, kiểm tra Unicode/encoding ở ranh giới ứng dụng, xác thực nguồn gửi hoặc loại bỏ dữ liệu nhạy cảm.

Nếu muốn định dạng UUID nghiêm ngặt, phải thống nhất chuẩn, cách viết hoa/thường, có/không có prefix `urn:uuid:` và triển khai validator tương ứng. Không tự khẳng định mọi trace ID đều là UUID: W3C trace ID có định dạng riêng.

### 4.2. WSDL 1.1 khai báo Header message và SOAP binding

WSDL 1.1 có thể khai báo `wsdl:message` cho header, rồi tham chiếu từ `soap:header` trong `wsdl:binding`. Ví dụ **trích đoạn**, giả định tài liệu đầy đủ đã khai báo namespace `tns` cho service và `ctx` cho header, và đã import/include schema cần thiết:

~~~xml
<wsdl:message name="CorrelationHeaderMessage">
  <wsdl:part name="correlation"
             element="ctx:CorrelationId"/>
</wsdl:message>

<wsdl:binding name="OrdersSoapBinding" type="tns:OrdersPortType">
  <soap:binding
      style="document"
      transport="http://schemas.xmlsoap.org/soap/http"/>
  <wsdl:operation name="CreateOrder">
    <soap:operation soapAction="urn:example:orders:v1/CreateOrder"/>
    <wsdl:input>
      <soap:body use="literal"/>
      <soap:header
          message="tns:CorrelationHeaderMessage"
          part="correlation"
          use="literal"/>
    </wsdl:input>
    <wsdl:output>
      <soap:body use="literal"/>
      <soap:header
          message="tns:CorrelationHeaderMessage"
          part="correlation"
          use="literal"/>
    </wsdl:output>
  </wsdl:operation>
</wsdl:binding>
~~~

Đoạn này không phải WSDL độc lập: thiếu `definitions`, `types`, request/response messages, `portType`, `service` và các khai báo namespace. Nó minh họa **vị trí khai báo header trong binding**. Header `RequestId` có thể được bổ sung bằng một `wsdl:message/part` và `soap:header` riêng nếu hợp đồng yêu cầu.

Khi dùng `DefaultWsdl11Definition` để tạo WSDL từ XSD, đừng mặc định generator tự suy mọi custom SOAP Header và WS-Policy từ schema request/response. Nếu hợp đồng có các header/binding/policy phức tạp hoặc đã được đối tác ký duyệt, có thể cần WSDL tĩnh được quản lý phiên bản và kiểm thử generate client.

### 4.3. Request và response không nhất thiết dùng cùng Request ID

Thiết kế thường là:

- `CorrelationId` giữ ổn định trong cặp request/response, kể cả khi backend gọi nhiều dịch vụ.
- `RequestId` thể hiện **một request inbound** do gateway/service tạo, có thể được echo trong response để người gửi truy vấn log.
- Khi service gọi downstream, nó tạo request ID **mới** cho downstream, và có thể mang `ParentRequestId` nếu contract định nghĩa.

Vì vậy, không có quy tắc SOAP rằng phải đổi Request ID trong response. Điều đó do hợp đồng và ý nghĩa field quyết định; tránh trộn `responseMessageId` của WS-Addressing với request ID ở tầng log.

## 5. WS-Addressing: MessageID, RelatesTo và Action

**WS-Addressing** là đặc tả dùng các SOAP Header chuẩn hóa để mô tả định danh thông điệp, đích, action và quan hệ giữa các SOAP message. Những phần tử thường gặp sử dụng namespace:

~~~text
http://www.w3.org/2005/08/addressing
~~~

Một đoạn SOAP Header minh họa:

~~~xml
<soap:Header
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:wsa="http://www.w3.org/2005/08/addressing"
    xmlns:ctx="urn:example:context:v1">
  <wsa:Action>urn:example:orders:v1/CreateOrder</wsa:Action>
  <wsa:To>https://api.example.test/ws</wsa:To>
  <wsa:MessageID>urn:uuid:3d2d8d01-a914-4f25-a63f-c7400825f321</wsa:MessageID>
  <ctx:CorrelationId>corr-27a</ctx:CorrelationId>
</soap:Header>
~~~

Đoạn này chỉ minh họa các header. Việc sử dụng WS-Addressing phải phù hợp **WSDL, policy, binding và khả năng hỗ trợ SOAP client/server**; không mặc định thêm `wsa:MessageID` thì Spring-WS và đối tác tự động xử lý đầy đủ WS-Addressing.

| WS-Addressing element | Ý nghĩa | Có đồng nghĩa Correlation ID không? |
| --- | --- | --- |
| `wsa:MessageID` | Định danh một thông điệp cụ thể. | **Không**; các SOAP message khác nhau thường có ID riêng. |
| `wsa:RelatesTo` | Liên kết một message với message khác, điển hình response với request. | **Không**; quan hệ cấp message, không nhất thiết toàn workflow. |
| `wsa:Action` | URI xác định ngữ nghĩa action/message. | **Không**; có thể tham gia dispatch/binding. |
| `wsa:To` | Đích của thông điệp theo WS-Addressing. | **Không**; phải khớp routing và transport. |
| `wsa:ReplyTo` | Địa chỉ nhận phản hồi trong mô hình phù hợp. | **Không**; phục vụ định tuyến response. |
| `wsa:FaultTo` | Đích nhận SOAP Fault khi được hỗ trợ. | **Không**; phục vụ luồng lỗi. |

### 5.1. Response có MessageID riêng và RelatesTo trỏ về request

Request có `MessageID`:

~~~xml
<wsa:MessageID xmlns:wsa="http://www.w3.org/2005/08/addressing">
  urn:uuid:3d2d8d01-a914-4f25-a63f-c7400825f321
</wsa:MessageID>
~~~

Response có thể mang:

~~~xml
<wsa:MessageID xmlns:wsa="http://www.w3.org/2005/08/addressing">
  urn:uuid:547b192a-ae0a-4b9f-8f6b-24882e12f457
</wsa:MessageID>
<wsa:RelatesTo xmlns:wsa="http://www.w3.org/2005/08/addressing">
  urn:uuid:3d2d8d01-a914-4f25-a63f-c7400825f321
</wsa:RelatesTo>
~~~

Đặc điểm:

- Response có **MessageID khác** request.
- `RelatesTo` cho biết response liên hệ với request có `MessageID` nào.
- Custom `CorrelationId` có thể vẫn là `corr-27a` qua request, response, các downstream calls và event.

Nếu đối tác đã dùng WS-Addressing chính thức, hãy tận dụng các trường chuẩn theo ngữ nghĩa của chúng. Tuy nhiên, **WS-Addressing không thay thế distributed tracing, idempotency hay authorization**.

### 5.2. Khi nào không cần custom MessageID?

Nếu mục tiêu chỉ là ghép cặp SOAP response với request và đối tác đã dùng WS-Addressing, `MessageID`/`RelatesTo` có thể đáp ứng nhu cầu đó. Nhưng nếu cần nối **nhiều request nối tiếp hoặc song song qua nhiều hệ thống**, correlation ID ổn định theo workflow hoặc trace context vẫn hữu ích.

Không nên đưa cùng một UUID vào `MessageID`, `CorrelationId`, `RequestId` và `trace-id` chỉ để đơn giản hóa. Cách này làm mất khả năng phân biệt **bản tin, lời gọi, workflow và distributed trace**.

## 6. W3C Trace Context và HTTP header: không phải SOAP Header

Nhiều hệ thống observability dùng **distributed tracing context** qua HTTP. Header `traceparent` của W3C Trace Context có dạng khái quát:

~~~text
version-traceid-parentid-flags
~~~

Ví dụ:

~~~http
POST /ws HTTP/1.1
Host: api.example.test
Content-Type: text/xml; charset=utf-8
SOAPAction: "urn:example:orders:v1/CreateOrder"
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
X-Request-ID: req-01
~~~

Ở ví dụ định dạng version `00`:

- `00` là version; `4bf92f3577b34da6a3ce929d0e0e4736` là trace ID gồm 32 ký tự hex.
- `00f067aa0ba902b7` là parent/span ID gồm 16 ký tự hex.
- `01` là trace flags (có bit sampled theo quy tắc W3C).
- Trace ID và parent ID không được là toàn số 0 theo quy tắc hợp lệ của `traceparent`.

`tracestate` là header tùy chọn mô tả thông tin tracing vendor theo chuẩn; `baggage` có thể mang metadata được chủ động cho phép qua nhiều hop. Không đưa PII, token, mật khẩu, chứng chỉ hoặc giá trị có độ dài không kiểm soát vào baggage/tracestate.

### 6.1. Một trace có thể có nhiều request và span

~~~text
Gateway nhận HTTP traceparent
  → OpenTelemetry/instrumentation tạo server span
  → Orders SOAP gọi Inventory SOAP: tạo client span mới
  → Inject traceparent vào HTTP outbound
  → Inventory trích context, tạo server span
  → Trace backend liên kết các span cùng trace
~~~

Trong các span cùng trace, **trace ID thường giữ nguyên**, còn **span ID thay đổi**. Điều này khác với request ID ứng dụng và correlation ID nghiệp vụ.

Không mặc định `WebServiceTemplate` tự copy HTTP `traceparent` từ inbound request sang outbound SOAP. Nên dùng instrumentation/propagator được hỗ trợ cho Spring-WS message sender/transport và phiên bản ứng dụng. Nếu triển khai tự viết, phải hiểu quy tắc format, sampling và trust boundary, tránh chỉ copy nguyên chuỗi từ client ngoài mà không validate.

### 6.2. Các kênh có thể cùng tồn tại

~~~text
HTTP traceparent       = distributed trace-id / parent-id
HTTP X-Request-ID      = request-id dùng bởi gateway (theo quy ước)
SOAP ctx:CorrelationId = correlation-id cho workflow
SOAP wsa:MessageID     = message-id của WS-Addressing
~~~

Chúng phục vụ các mục đích khác nhau, không cần ép vào một field. Khi chuyển sang message broker (không dùng HTTP), metadata cần đi qua event headers hoặc event envelope; HTTP headers không tự tồn tại trong queue. Khi tracing chuyển từ synchronous sang asynchronous processing, việc tiếp tục trace hay tạo trace mới có **span link** cần theo chính sách và khả năng hỗ trợ của hệ thống tracing thực tế.

## 7. Spring-WS đọc correlation header ở endpoint

Trong Spring-WS, `@RequestPayload` ánh xạ **SOAP Body**, còn `@SoapHeader` có thể lấy một element trong SOAP Header theo QName. Với endpoint annotation-based, một chữ ký minh họa:

~~~java
import java.util.regex.Pattern;
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;
import org.springframework.ws.soap.SoapHeaderElement;
import org.springframework.ws.soap.server.endpoint.annotation.SoapHeader;

@Endpoint
public class OrdersEndpoint {
    private static final String ORDER_NS = "urn:example:orders:v1";
    private static final Pattern SAFE_ID =
        Pattern.compile("[A-Za-z0-9][A-Za-z0-9._:-]{0,63}");

    private final OrderApplicationService orderService;

    public OrdersEndpoint(OrderApplicationService orderService) {
        this.orderService = orderService;
    }

    @PayloadRoot(namespace = ORDER_NS,
                 localPart = "CreateOrderRequest")
    @ResponsePayload
    public CreateOrderResponse create(
        @RequestPayload CreateOrderRequest request,
        @SoapHeader("{urn:example:context:v1}CorrelationId")
        SoapHeaderElement correlationHeader) {

        String correlationId = correlationHeader.getText();

        if (correlationId == null
                || !SAFE_ID.matcher(correlationId).matches()) {
            throw new InvalidCorrelationContextException(
                "Invalid correlation identifier");
        }

        return orderService.createOrder(request, correlationId);
    }
}
~~~

**Phạm vi:** `CreateOrderRequest` và `CreateOrderResponse` là JAXB DTO giả định đã sinh từ XSD, `OrderApplicationService` và `InvalidCorrelationContextException` do ứng dụng tự tạo. Đoạn này mô tả chữ ký, không phải ứng dụng Spring Boot độc lập. Kiểm tra `@SoapHeader`, argument resolver, trường hợp thiếu header và JAXB adapter theo **phiên bản Spring-WS thực tế**.

Ba annotation có vai trò khác nhau:

1. `@PayloadRoot` chọn method theo QName `{urn:example:orders:v1}CreateOrderRequest` ở SOAP Body.
2. `@RequestPayload` đưa dữ liệu nghiệp vụ từ Body sang đối tượng JAXB.
3. `@SoapHeader` lấy header `{urn:example:context:v1}CorrelationId`.

`@SoapHeader` **không phải** `@RequestHeader` của Spring MVC và không đọc trực tiếp HTTP `X-Request-ID`/`traceparent`. Nếu header optional và phải tự sinh ID lúc thiếu, một **interceptor** xử lý trước method thường linh hoạt hơn so với tham số bắt buộc.

### 7.1. QName khác prefix XML

Hai header sau có cùng QName:

~~~xml
<ctx:CorrelationId xmlns:ctx="urn:example:context:v1">corr-27a</ctx:CorrelationId>
~~~

~~~xml
<c:CorrelationId xmlns:c="urn:example:context:v1">corr-27a</c:CorrelationId>
~~~

Một header có cùng local name nhưng namespace khác, chẳng hạn `urn:untrusted:context`, **không phải** header tương quan của hợp đồng. Đừng tìm `CorrelationId` bằng string hoặc chỉ theo `localName`: luôn so QName đầy đủ (namespace URI và local name).

### 7.2. Thiếu header, header trùng và giá trị không hợp lệ

Nếu client gửi hai `CorrelationId` cùng QName, hệ thống cần chính sách rõ: **từ chối vì mơ hồ** hoặc phương án đã được hợp đồng quy định; không lấy tùy tiện header đầu/cuối.

Nếu header bị thiếu, có thể để gateway hoặc service tin cậy sinh correlation ID rồi echo; nếu header có ký tự điều khiển, xuống dòng, quá dài hoặc không đúng pattern, cần từ chối hoặc thay thế theo policy đã công bố. **Không tin ID do client gửi để quyết định tenant, user hoặc quyền giao dịch**.

## 8. Interceptor và MessageContext: duy trì ID trong một request

Spring-WS có `MessageContext` để truy cập request/response SOAP và lưu property trong **phạm vi một lần xử lý**. Một `EndpointInterceptor` thích hợp cho logic dùng chung như đọc/sinh correlation ID, đưa vào log context và thêm vào response.

### 8.1. Ví dụ interceptor tạo/echo CorrelationId

Đoạn code sau minh họa interceptor xử lý scalar SOAP header:

~~~java
import java.util.Iterator;
import java.util.UUID;
import java.util.regex.Pattern;
import javax.xml.namespace.QName;

import org.slf4j.MDC;
import org.springframework.ws.context.MessageContext;
import org.springframework.ws.server.EndpointInterceptor;
import org.springframework.ws.soap.SoapHeader;
import org.springframework.ws.soap.SoapHeaderElement;
import org.springframework.ws.soap.SoapMessage;

public final class CorrelationInterceptor
        implements EndpointInterceptor {

    public static final String CONTEXT_KEY =
        "com.example.soap.correlationId";

    private static final QName CORRELATION = new QName(
        "urn:example:context:v1", "CorrelationId", "ctx");

    private static final Pattern SAFE_ID =
        Pattern.compile("[A-Za-z0-9][A-Za-z0-9._:-]{0,63}");

    @Override
    public boolean handleRequest(
            MessageContext context, Object endpoint) {

        SoapMessage request = (SoapMessage) context.getRequest();
        String incoming = findUnique(
            request.getSoapHeader(), CORRELATION);

        String id;
        if (incoming == null) {
            id = UUID.randomUUID().toString();
        } else if (SAFE_ID.matcher(incoming).matches()) {
            id = incoming;
        } else {
            throw new IllegalArgumentException(
                "Invalid correlation identifier");
        }

        context.setProperty(CONTEXT_KEY, id);
        MDC.put("correlationId", id);
        return true;
    }

    @Override
    public boolean handleResponse(
            MessageContext context, Object endpoint) {
        echoIfPresent(context);
        return true;
    }

    @Override
    public boolean handleFault(
            MessageContext context, Object endpoint) {
        echoIfPresent(context);
        return true;
    }

    @Override
    public void afterCompletion(
            MessageContext context, Object endpoint, Exception ex) {
        MDC.remove("correlationId");
    }

    private static String findUnique(
            SoapHeader header, QName name) {

        String result = null;
        Iterator<SoapHeaderElement> it =
            header.examineAllHeaderElements();

        while (it.hasNext()) {
            SoapHeaderElement item = it.next();
            if (name.equals(item.getName())) {
                if (result != null) {
                    throw new IllegalArgumentException(
                        "Duplicate correlation header");
                }
                result = item.getText();
            }
        }
        return result;
    }

    private static void echoIfPresent(MessageContext context) {
        if (!context.hasResponse()) {
            return;
        }
        Object value = context.getProperty(CONTEXT_KEY);
        if (!(value instanceof String id)) {
            return;
        }
        SoapMessage response = (SoapMessage) context.getResponse();
        SoapHeaderElement element =
            response.getSoapHeader().addHeaderElement(CORRELATION);
        element.setText(id);
    }
}
~~~

**Giới hạn của ví dụ:** cần đăng ký interceptor trong Spring-WS configuration (ví dụ qua `WsConfigurer#addInterceptors`), xác định thứ tự với security/validation interceptors, và cấu hình exception resolver cho trường hợp header sai. Đoạn code giả định cả request và response là `SoapMessage`, chính interceptor này là thành phần duy nhất echo `CorrelationId`, runtime và JDK hỗ trợ cú pháp Java được dùng. Nếu code khác đã thêm header, cần xử lý duplicate thay vì thêm lần nữa.

`handleResponse` và `handleFault` giúp trả correlation ID trên cả phản hồi thành công lẫn Fault **khi framework đã tạo SOAP response và interceptor được gọi**. Không bảo đảm interceptor có thể thêm header cho lỗi HTTP xảy ra **trước** khi Spring-WS tạo SOAP message (ví dụ TLS handshake, proxy reject request, malformed transport).

Nếu trong `handleRequest` ném exception, chuỗi interceptor có thể không hoàn tất như request thành công. Thiết kế production phải kiểm tra việc dọn MDC trên cả đường lỗi, có thể dùng filter ở ranh giới HTTP với `try/finally` hoặc cơ chế context scope có quản lý, nhất là khi thread được tái sử dụng.

### 8.2. Không lưu ID vào field mutable của interceptor

Interceptor Spring bean thường được dùng cho **nhiều request đồng thời**. Không tạo field kiểu:

~~~java
// Sai: request khác có thể ghi đè dữ liệu.
private String currentCorrelationId;
~~~

`MessageContext#setProperty(...)` giữ giá trị theo message context; `MDC` giữ metadata theo execution context/thread; các biến cục bộ trong method không chia sẻ giữa request. Khi cần truyền sang service nghiệp vụ, có thể đọc property trong endpoint hoặc chuyển ID qua tham số method. Không giữ `MessageContext` sống trong field hoặc truyền sang worker sau khi HTTP request đã kết thúc.

### 8.3. Đăng ký interceptor và thứ tự xử lý

Ví dụ định hướng với Spring-WS configuration:

~~~java
import java.util.List;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.config.annotation.WsConfigurer;
import org.springframework.ws.server.EndpointInterceptor;

@Configuration
@EnableWs
public class WsConfig implements WsConfigurer {

    @Override
    public void addInterceptors(
            List<EndpointInterceptor> interceptors) {
        interceptors.add(new CorrelationInterceptor());
    }
}
~~~

Đây là cấu hình tối giản cho bài học. Một ứng dụng thật có thể inject interceptor như bean thay vì `new` trực tiếp, và đã có các interceptors khác (security, validation, logging). Thứ tự đăng ký ảnh hưởng thời điểm dữ liệu được đọc/xác minh và giá trị nào có thể dùng trong log. **Không đặt logic tin tưởng user/tenant vào một correlation interceptor chạy trước bước xác thực**.

## 9. Client Spring-WS: thêm correlation header khi gọi downstream

Khi Orders service gọi Inventory hoặc Payment qua `WebServiceTemplate`, phải **inject** correlation ID đã được xác minh vào SOAP message mới. Đồng thời mỗi lời gọi downstream nên có request ID mới theo quy ước đã thống nhất.

### 9.1. WebServiceMessageCallback để ghi SOAP Header

Một lời gọi minh họa với JAXB request object:

~~~java
import java.util.UUID;
import javax.xml.namespace.QName;

import org.springframework.ws.WebServiceMessage;
import org.springframework.ws.client.core.WebServiceMessageCallback;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.soap.SoapHeader;
import org.springframework.ws.soap.SoapMessage;

String correlationId = trustedCorrelationId;
String downstreamRequestId = UUID.randomUUID().toString();

WebServiceTemplate template = inventoryTemplate;

Object result = template.marshalSendAndReceive(
    "https://inventory.example.test/ws",
    inventoryRequest,
    new WebServiceMessageCallback() {
        @Override
        public void doWithMessage(WebServiceMessage message) {
            SoapMessage soap = (SoapMessage) message;
            soap.setSoapAction(
                "urn:example:inventory:v1/CheckStock");

            SoapHeader header = soap.getSoapHeader();

            header.addHeaderElement(new QName(
                "urn:example:context:v1", "CorrelationId", "ctx"
            )).setText(correlationId);

            header.addHeaderElement(new QName(
                "urn:example:context:v1", "RequestId", "ctx"
            )).setText(downstreamRequestId);
        }
    }
);
~~~

**Giả định:** `inventoryTemplate` đã cấu hình SOAP message factory, marshaller/unmarshaller, HTTP sender và security thích hợp; `inventoryRequest` có JAXB root metadata tương thích WSDL/XSD; `trustedCorrelationId` được tạo hoặc xác minh trước đó. URI và SOAPAction chỉ là ví dụ, không phải endpoint hoạt động thật.

Callback thao tác **SOAP Header** và `SOAPAction`; không được thêm các metadata ấy như field trong JAXB SOAP Body nếu hợp đồng chưa định nghĩa. Giá trị SOAPAction phải theo binding WSDL, không được tự suy một chuỗi bất kỳ chỉ từ tên method Java.

### 9.2. Cần thêm gì ngoài callback?

Khi client phải truyền distributed tracing qua HTTP, callback thêm SOAP Header **không tự chèn** `traceparent` vào HTTP request. Phần đó thuộc instrumentation hoặc transport connection phù hợp với `WebServiceTemplate`/message sender đang dùng.

Khi client phải gửi WS-Security UsernameToken/chữ ký/chứng chỉ, dùng **security interceptor/runtime** phù hợp. Correlation header không thay thế security policy. Nếu một header cần được ký, metadata cần được đưa vào message **trước bước ký** và nằm trong phạm vi reference/policy được hai phía thỏa thuận; thêm/sửa header sau ký có thể làm chữ ký không còn phù hợp.

Đối với nhiều lời gọi, có thể triển khai client interceptor chung để inject correlation context, thay vì lặp callback ở mỗi operation. Tuy nhiên interceptor phía client là `ClientInterceptor`, khác `EndpointInterceptor` trên server: cần kiểm tra các callback `handleRequest`, `handleResponse`, `handleFault` và `afterCompletion` theo API version.

## 10. Truyền ngữ cảnh qua nhiều hệ thống và tác vụ bất đồng bộ

Một correlation ID chỉ hữu ích khi **mỗi bước tiếp nhận và chuyển tiếp đều có quy tắc rõ ràng**. Thiết kế propagation nên tách lớp:

~~~mermaid
flowchart LR
    A["Client / Gateway"] --> B["Orders SOAP"]
    B --> C["Inventory SOAP"]
    B --> D["Payment SOAP"]
    B --> E["OrderCreated event"]
    E --> F["Notification Worker"]
    F --> G["Email/SMS service"]

    A -. "corr-27a" .-> B
    B -. "corr-27a" .-> C
    B -. "corr-27a" .-> D
    B -. "corr-27a" .-> E
    E -. "corr-27a" .-> F
    F -. "corr-27a" .-> G
~~~

Mỗi hop nên làm việc này theo thứ tự:

1. **Extract**: lấy metadata từ SOAP/HTTP/event envelope ở ranh giới inbound.
2. **Validate**: kiểm tra QName, độ dài, ký tự, số lượng header và trust boundary; không tin thông tin bảo mật chỉ vì có ID.
3. **Resolve**: dùng correlation ID đáng tin theo policy, hoặc sinh mới khi thiếu; tạo request ID riêng cho hop đang xử lý.
4. **Store locally**: lưu trong `MessageContext`, request-scoped metadata/tracing context, hoặc tham số rõ ràng.
5. **Use**: gắn vào log/metrics/traces theo chính sách bảo vệ dữ liệu.
6. **Inject**: chuyển correlation ID vào outgoing SOAP Header/HTTP/event metadata; sinh request/message ID thích hợp cho outgoing hop.
7. **Clean up**: xóa MDC/thread-local context sau khi request kết thúc, không giữ tham chiếu stream hoặc context sống quá vòng đời.

### 10.1. Bảng các giá trị theo hop

| Hop | Correlation ID | Request ID | Message ID/attempt | Chú thích |
| --- | --- | --- | --- | --- |
| Client → Gateway | `corr-27a` | `req-client-1` | `msg-client-1` | Giá trị ngoài biên tin cậy; gateway kiểm tra. |
| Gateway → Orders | `corr-27a` | `req-gw-1` | `msg-gw-1` | Gateway có thể tạo request/message mới. |
| Orders → Inventory | `corr-27a` | `req-inv-1` | `msg-inv-1` | Span tracing cho call Inventory riêng. |
| Orders → Payment | `corr-27a` | `req-pay-1` | `msg-pay-1` | Không dùng lại ID của Inventory request. |
| Orders → event broker | `corr-27a` | `req-pub-1` | `event-1` | Định danh event có thể cần dedup riêng. |
| Broker → Notification | `corr-27a` | `req-worker-1` | delivery attempt riêng | Worker có execution context mới. |

Các chuỗi ở bảng là tên minh họa dễ đọc, không phải một định dạng bắt buộc. Hệ thống thực nên chọn ID format/version rõ ràng. `requestId` có thể được gateway cấp và giữ trong cặp request-response; khi service tạo downstream request, nên có ID mới để truy vết cụ thể từng hop.

### 10.2. Propagation qua message broker

Nếu xử lý `OrderCreated` bằng queue/topic, metadata correlation có thể đi qua **message headers của broker** hoặc event envelope rõ ràng, ví dụ:

~~~json
{
  "eventId": "event-1",
  "eventType": "OrderCreated",
  "correlationId": "corr-27a",
  "causationId": "msg-gw-1",
  "occurredAt": "2026-11-27T02:00:00Z",
  "payload": {
    "orderId": "ORD-000184",
    "status": "ACCEPTED"
  }
}
~~~

Đây là **schema minh họa** của event, không phải định dạng mặc định của JMS/Kafka/RabbitMQ. `causationId`, nếu tổ chức sử dụng, thường trỏ đến message/event/command tạo ra event hiện tại; cần mô tả rõ đối tượng được tham chiếu. `eventId` thường duy nhất cho event, giúp dedup và điều tra giao hàng lặp.

Khi worker nhận event, nó có thể:

- Đọc `correlationId` và `eventId`, validate và đưa vào log context.
- Tạo execution/request ID mới cho lần xử lý.
- Tiếp tục tracing context nếu được truyền hợp lệ và propagator hỗ trợ; nếu không, có thể tạo trace mới và liên kết theo dữ liệu có sẵn.
- Xử lý idempotent nếu broker có at-least-once delivery hoặc handler có thể bị retry.
- Dọn metadata khi xử lý xong; không tái sử dụng ThreadLocal/MDC của event trước.

**Không copy nguyên `MessageContext` hoặc đối tượng `SoapMessage` qua broker**: đó là object của Spring-WS request gốc, có thể chứa stream, XML tree, metadata nhạy cảm và vòng đời không phù hợp. Chỉ truyền những field được phép theo schema event/contract.

### 10.3. Khi có fan-out và nhiều nhánh song song

Orders gọi Inventory và Payment đồng thời. Cả hai có thể giữ `correlationId=corr-27a`, nhưng mỗi nhánh nên có request ID riêng. Nếu sử dụng distributed tracing, hai nhánh có thể tạo các span con cùng trace ID, với parent/span relationship phù hợp.

Nếu chỉ tìm log theo correlation ID, bạn thấy cả hai nhánh trong cùng kết quả. Muốn phân tích **thứ tự và nguyên nhân**, cần thêm timestamp, service name, operation, request/message ID, span ID, outcome và relation parent/causation; correlation ID một mình chưa đủ mô tả đồ thị phụ thuộc.

## 11. Retry, timeout và idempotency: giữ ID nào, đổi ID nào?

Đây là tình huống rất dễ sai khi client SOAP bị timeout: **timeout không chứng minh server chưa xử lý yêu cầu**. Client có thể ngắt kết nối sau khi payment service đã ghi nhận giao dịch nhưng trước khi gửi response.

### 11.1. Ví dụ retry tạo đơn

~~~mermaid
sequenceDiagram
    participant C as Client
    participant O as Orders SOAP
    participant DB as Database

    C->>O: CreateOrder, key=op-9b2, corr=corr-27a, attempt=1
    O->>DB: Ghi đơn có key=op-9b2
    DB-->>O: ORD-000184
    Note over C,O: Network timeout, client không thấy response
    C->>O: Retry, cùng key=op-9b2, corr=corr-27a, attempt=2
    O->>DB: Tra idempotency key
    DB-->>O: ORD-000184 đã có
    O-->>C: Kết quả phù hợp contract, không tạo đơn mới
~~~

Một quy tắc thường dùng:

| Dữ liệu | Khi retry cùng tác vụ | Vì sao |
| --- | --- | --- |
| `correlationId` | Thường giữ nguyên | Liên kết mọi lần thử thuộc cùng workflow. |
| `idempotencyKey` | **Giữ nguyên** | Server nhận ra cùng ý định nghiệp vụ. |
| `requestId`/attempt ID | Tạo mới | Phân biệt từng lần gửi và lỗi transport. |
| `wsa:MessageID` | Theo quy tắc addressing/retransmission đã thỏa thuận | Phải xác định là gửi lại cùng message hay tạo thông điệp mới. |
| `traceId` | Có thể tiếp tục trace hiện có hoặc dùng trace mới có liên kết | Phụ thuộc thời gian, sampling và mô hình tracing. |
| `orderId` | Không sinh mới nếu idempotency đã xác nhận tồn tại | Bảo toàn trạng thái nghiệp vụ. |

Đừng dùng `CorrelationId` như khóa duy nhất để chống thanh toán lặp: một workflow có thể chứa nhiều thao tác hợp lệ khác nhau. **Idempotency key phải được scope đúng**, ví dụ theo tenant + operation + hành động nghiệp vụ, có thời hạn lưu, tính nguyên tử, xử lý request body không tương thích và chính sách trả response nhất quán.

### 11.2. Idempotency khác chống replay WS-Security

WS-Security timestamp, nonce và chữ ký có thể hỗ trợ chính sách phát hiện replay ở tầng thông điệp/credential. Nhưng một request retry hợp lệ theo nghiệp vụ vẫn có thể dùng SOAP message mới, header security mới và cùng idempotency key.

Ngược lại, một chữ ký WS-Security hợp lệ **không bảo đảm** không tạo đơn trùng nếu client gọi `CreateOrder` nhiều lần. Cần xử lý cả hai tầng theo thiết kế.

## 12. Bảo mật và quyền tin cậy đối với correlation metadata

Correlation header có vẻ vô hại vì chỉ là chuỗi ID, nhưng nó đi qua log, API gateway, tracing backend và có thể được echo cho client. Do đó phải coi nó là **dữ liệu không tin cậy ở biên hệ thống**.

### 12.1. Các nguyên tắc vận hành

| Rủi ro | Biện pháp |
| --- | --- |
| Header injection / log forging bằng newline | Hạn chế charset và độ dài; không log raw unescaped header. |
| Khách ngoài cố tình dùng correlation ID của người khác | Không cho phép dùng correlation ID để quyết định quyền; bảo vệ truy vấn log bằng authorization. |
| Gửi hàng nghìn header trùng lặp | Giới hạn tổng kích thước header/message; từ chối duplicate theo contract. |
| ID chứa PII, token hoặc secrets | Không tạo ID từ dữ liệu nhạy cảm; masking/redaction khi log. |
| ID do client tự chọn gây collision | Quy định nguồn cấp phát/trust boundary, tạo ID server nếu cần; không dùng làm database key bảo mật. |
| SOAP Header bị sửa bởi trung gian | TLS bảo vệ kênh; WS-Security signature/policy khi cần bảo vệ end-to-end. |
| Baggage quá lớn theo nhiều hop | Allowlist key/value, giới hạn kích thước/độ sâu, không truyền secrets. |
| Dùng correlation để bypass kiểm tra tenant | Tenant/user/scope phải lấy từ identity đã được xác minh. |

Nếu CorrelationId header được yêu cầu ký bằng WS-Security, phải đưa header vào signature reference theo policy thật. **Không giả định cứ có XML Signature trong SOAP Header thì mọi sibling header đều được ký**. Bên nhận cần xác định chính xác phần XML nào đã được xác minh và thông tin nào được tin cậy.

### 12.2. TLS, client certificate và WS-Security có vai trò khác nhau

- **TLS** bảo vệ kết nối từ client đến endpoint/proxy liên quan.
- **mTLS/client certificate** giúp xác thực peer ở tầng TLS khi được cấu hình và kiểm tra trust.
- **WS-Security** giúp xác thực/bảo vệ nội dung SOAP theo message policy, có thể quan trọng khi qua nhiều trung gian.
- **Correlation ID** hỗ trợ truy vết; nó **không phải** credential, bearer token hoặc chữ ký số.

Một SOAP request có correlation ID hợp lệ nhưng sai chứng chỉ/chữ ký vẫn phải bị từ chối theo chính sách bảo mật. Một SOAP request có chứng thực hợp lệ nhưng thiếu correlation ID có thể được server bổ sung ID nếu contract cho phép.

### 12.3. Không làm lộ nội dung SOAP khi logging

Một log phù hợp để tìm lỗi thường cần:

~~~text
timestamp=2026-11-27T02:00:00Z
service=orders-soap
operation=CreateOrder
correlationId=corr-27a
requestId=req-gw-1
traceId=4bf92f3577b34da6a3ce929d0e0e4736
outcome=SOAP_FAULT
faultCategory=VALIDATION
durationMs=42
~~~

Các số liệu trong ví dụ là giả lập; không phải kết quả đo của hệ thống thật. Khi ghi log, ưu tiên **metadata đã lọc** thay vì in toàn bộ SOAP Envelope có thông tin cá nhân, token hoặc private key. Nếu bắt buộc lưu raw SOAP để kiểm tra, phải có cơ chế phân quyền, redaction, mã hóa, thời gian lưu và phê duyệt tương ứng.

### 12.4. XML parser vẫn cần bảo vệ

Một correlation header XML có thể chứa DTD/entity hoặc dữ liệu phức tạp nếu parser chấp nhận input không tin cậy. Cần bảo vệ SOAP parser/transformer trước XXE, external entity, quá sâu cây XML và request size. Việc chỉ áp dụng regex cho `getText()` **sau khi parse** không thay thế cấu hình XML parser an toàn và giới hạn kích thước ở gateway/server.

## 13. Correlation ID trong SOAP response, SOAP Fault và lỗi transport

Một hệ thống tích hợp tốt phải hỗ trợ điều tra lỗi, không chỉ ở đường thành công.

### 13.1. Echo correlation trong response thành công

Ví dụ response SOAP 1.1 giữ `CorrelationId` từ request:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ctx="urn:example:context:v1"
    xmlns:ord="urn:example:orders:v1">
  <soap:Header>
    <ctx:CorrelationId>corr-27a</ctx:CorrelationId>
  </soap:Header>
  <soap:Body>
    <ord:CreateOrderResponse>
      <ord:orderId>ORD-000184</ord:orderId>
      <ord:status>ACCEPTED</ord:status>
    </ord:CreateOrderResponse>
  </soap:Body>
</soap:Envelope>
~~~

Ở cấu hình này, client đọc header để đối chiếu log của mình với server. Nếu response cũng có `RequestId`, hợp đồng cần mô tả nó là **request ID của inbound request nào** (ví dụ request ID do gateway cấp), không tự suy đó là một HTTP request mới.

### 13.2. SOAP Fault vẫn có thể mang CorrelationId

Ví dụ server trả SOAP 1.1 Fault về input sai:

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ctx="urn:example:context:v1">
  <soap:Header>
    <ctx:CorrelationId>corr-27a</ctx:CorrelationId>
  </soap:Header>
  <soap:Body>
    <soap:Fault>
      <faultcode>soap:Client</faultcode>
      <faultstring>Request không hợp lệ</faultstring>
      <detail>
        <errorCode>INVALID_ORDER_REQUEST</errorCode>
      </detail>
    </soap:Fault>
  </soap:Body>
</soap:Envelope>
~~~

Đây là **ví dụ minh họa**, không tự suy ra từ một exception cụ thể. Trong Spring-WS, SOAP Fault thường được tạo qua exception resolver/message processor, chẳng hạn `SoapFaultMappingExceptionResolver`. Interceptor phải được đăng ký và tham gia xử lý ở đường Fault thì mới có thể thêm header như thiết kế. SOAP 1.2 có cấu trúc Fault khác SOAP 1.1.

**Không nhét correlation header vào Fault detail tùy tiện** nếu hợp đồng yêu cầu header riêng hoặc đã có XSD cho Fault detail. Có thể cung cấp mã hỗ trợ điều tra trong `detail` theo thỏa thuận, nhưng không đưa stack trace, token, đường dẫn máy chủ hoặc bí mật vào Fault.

### 13.3. Không phải lỗi nào cũng có SOAP Fault

Có những lỗi xảy ra trước khi Spring-WS xử lý request:

- DNS/TLS handshake thất bại hoặc chứng chỉ không được tin.
- Gateway từ chối vì request quá lớn, authentication, rate limit.
- Proxy timeout, circuit breaker mở hoặc kết nối bị reset.
- Dữ liệu HTTP không đủ điều kiện để tạo SOAP message.

Trong các trường hợp đó, **không bảo đảm có SOAP Envelope hay correlation SOAP Header trong response**. Gateway có thể trả HTTP request ID riêng để hỗ trợ truy vấn log. Vì thế người vận hành cần có khả năng tìm bằng **gateway request ID, trace ID và correlation ID** tùy lỗi ở tầng nào.

Nếu WS-Security interceptor phát hiện chữ ký sai, request có thể bị từ chối trước endpoint. **Không echo vô điều kiện header chưa được xác minh** nếu chính sách tin cậy yêu cầu metadata đáng tin; có thể dùng ID do server tự tạo cho Fault và lưu quan hệ nội bộ phù hợp.

## 14. Thiết kế logging và observability

Một bản ghi log hữu ích cần trả lời **chuyện gì xảy ra, ở service nào, trong request nào và thuộc workflow/trace nào**.

| Field | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `timestamp` | Thời điểm sự kiện. | Dùng chuẩn thời gian nhất quán, ví dụ UTC. |
| `service`, `environment` | Dịch vụ và môi trường. | Field chuẩn, không diễn giải bằng text mơ hồ. |
| `operation` | SOAP operation hoặc QName payload. | Nhiều operation có thể dùng chung URL `/ws`. |
| `correlationId` | ID workflow. | Chỉ dùng ID đã validate hoặc do server sinh. |
| `requestId` | Một lần xử lý ở service. | Thường riêng cho inbound hop. |
| `messageId` | WS-Addressing/event message ID nếu có. | Khác request ID và correlation ID. |
| `traceId`, `spanId` | Distributed tracing context. | Không tự invent span IDs nếu đã có instrumentation. |
| `durationMs`, `outcome` | Thời gian, kết quả/loại lỗi. | Không lộ secret. |
| `faultCode` | SOAP Fault code nếu có. | Có thể map thành category/enum ổn định. |

Ví dụ log metadata:

~~~text
timestamp=2026-11-27T02:00:00Z
service=orders-soap
operation=CreateOrder
correlationId=corr-27a
requestId=req-gw-1
traceId=4bf92f3577b34da6a3ce929d0e0e4736
outcome=SOAP_FAULT
faultCategory=VALIDATION
durationMs=42
~~~

Các số liệu trong ví dụ là dữ liệu giả lập. Khi lưu log, ưu tiên **metadata đã lọc** thay vì toàn bộ SOAP Envelope có PII, token, password hoặc private key. Nếu raw SOAP thật sự cần thiết để điều tra, phải có phân quyền, redaction, mã hóa và thời gian lưu phù hợp.

### 14.1. Sampling làm trace có thể thiếu, correlation giúp bổ trợ

Distributed trace có thể bị sampling hoặc mất span do exporter/network. Correlation ID hỗ trợ tìm log khác, nhưng cũng không có bảo đảm log tồn tại vô thời hạn hoặc không bị lọc. Cần xác định retention, quota, sampling, privacy controls và quyền truy cập.

Không biến correlation ID thành một truy vấn công khai cho phép người dùng xem log của workflow khác. ID **không phải credential**; quyền truy cập log phải được kiểm soát riêng.

### 14.2. MDC không tự chạy theo CompletableFuture

~~~java
MDC.put("correlationId", correlationId);
try {
    CompletableFuture.runAsync(() -> {
        // Thread khác không mặc định có cùng MDC.
        notificationService.send();
    }, executor);
} finally {
    MDC.remove("correlationId");
}
~~~

Để truyền context vào task, cần một cơ chế có chủ đích: chụp metadata đã kiểm tra rồi thiết lập/khôi phục MDC ở task, dùng `TaskDecorator` phù hợp hoặc thư viện context propagation hỗ trợ. Với trace, không chỉ copy `traceId` dạng String; cần xử lý parent/span hoặc span link semantics bằng tracing API.

Trong thread pool, luôn dọn log context trong `finally` và không lưu correlation vào static/global mutable state: một thread có thể phục vụ nhiều request khác nhau.

## 15. Kiểm thử propagation xuyên biên hệ thống

Một unit test gọi thẳng `OrdersEndpoint#createOrder(...)` không chứng minh SOAP Header được parse, interceptor lưu ID hoặc client gửi đúng downstream header. Cần kiểm tra **các biên**.

### 15.1. Ma trận kiểm thử

| Ca thử | Input | Kỳ vọng |
| --- | --- | --- |
| Header đúng QName | `ctx:CorrelationId=corr-27a` | Server xử lý/echo ID theo contract. |
| Prefix đổi | `x:CorrelationId` cùng namespace | Xử lý như cùng QName. |
| Sai namespace | `CorrelationId` thuộc namespace khác | Không tin như metadata của contract. |
| Thiếu header | SOAP request chỉ có Body | Sinh ID hoặc Fault theo policy. |
| Header trùng | Hai `ctx:CorrelationId` | Từ chối hoặc xử lý theo quy tắc rõ, không chọn ngẫu nhiên. |
| Có newline/quá dài | ID ngoài pattern | Từ chối/thay thế an toàn; không log forging. |
| Response thành công | Input hợp lệ | Echo ID, JAXB response đúng XSD. |
| SOAP Fault | Validation/business fail | Fault đúng SOAP version, echo khi pipeline cho phép. |
| Lỗi TLS/proxy | Request không vào Spring-WS | Có gateway ID để truy vết; không giả định SOAP Fault. |
| Orders → Inventory | Outbound SOAP | Cùng correlation, request ID mới, SOAPAction theo WSDL. |
| Orders → Payment fan-out | Hai outbound calls | Correlation giống nhau, request IDs khác nhau. |
| Retry | Hai lần gửi cùng ý định | Idempotency key giữ, attempt ID đổi, không side effect trùng. |
| Queue redelivery | Một event được phát lại | Event ID ổn định, worker attempt mới, xử lý idempotent. |
| Thread pool | Hai request trên một thread | MDC không rò dữ liệu từ request trước. |
| W3C traceparent | Header hợp lệ và malformed | Propagation an toàn, không crash, span đúng. |
| WS-Security | Header được yêu cầu ký | Xác minh đúng signed references/policy. |

### 15.2. Gửi HTTP request với SOAP Header thật

Giả sử ứng dụng test có SOAP endpoint `http://localhost:8080/ws`. Lưu SOAP Envelope ở mục 3 vào file `create-order.xml` mã hóa UTF-8 rồi thử:

~~~powershell
curl.exe --include --request POST --header 'Content-Type: text/xml; charset=utf-8' --header 'SOAPAction: "urn:example:orders:v1/CreateOrder"' --header 'X-Request-ID: req-01' --header 'traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01' --data-binary '@create-order.xml' 'http://localhost:8080/ws'
~~~

`SOAPAction` và URL đều là ví dụ, phải dùng giá trị thật từ WSDL `soap:operation`/`soap:address`. HTTP headers trong lệnh **không tạo SOAP Header**: `<ctx:CorrelationId>` phải nằm bên trong XML request đã lưu trong file. Gateway/instrumentation chịu trách nhiệm đọc `traceparent`/`X-Request-ID` ở HTTP layer khi được cấu hình.

Sau khi gửi, kiểm tra SOAP Header/Body, response QName, SOAP Fault nếu có, log của Orders và từng downstream service, rồi đối chiếu correlation ID và request/message IDs. HTTP status 200 **không tự chứng minh** SOAP Body hay header đúng contract.

Có thể dùng `MockWebServiceClient` để kiểm thử Spring-WS server endpoint/interceptor trong ApplicationContext, và `MockWebServiceServer` hoặc test transport tương ứng để xác minh `WebServiceTemplate` outbound. Những test đó chưa thay thế end-to-end HTTP/TLS/proxy thực tế.

### 15.3. Kiểm tra tương thích client công nghệ khác

Nếu WSDL khai báo custom SOAP Header trong `soap:header`, hãy sinh thử client JAX-WS/.NET từ **WSDL public** để xác định công cụ tạo client có API gửi/nhận header như mong đợi không. Tùy generator/runtime, header có thể được ánh xạ thành tham số method, handler, interceptor hoặc context riêng.

Nếu header **không được khai báo trong WSDL**, client generator không bắt buộc biết header đó. Có thể cần SOAP handler/callback bổ sung. Không thêm correlation vào XSD Body chỉ để né thiếu WSDL header vì đó là thay đổi hợp đồng ở sai tầng.

## 16. Lỗi thường gặp và cách khoanh vùng

| Triệu chứng | Nguyên nhân điển hình | Hướng kiểm tra |
| --- | --- | --- |
| Correlation ID biến mất sau khi gọi service khác | `WebServiceTemplate`/callback không inject, metadata không đi qua transport. | Capture outgoing SOAP Header ở môi trường test. |
| `@SoapHeader` không đọc được `X-Request-ID` | Nhầm SOAP Header với HTTP Header. | Đọc ở transport/gateway hoặc mapping rõ sang SOAP Header. |
| Header cùng local name nhưng không match | Namespace URI khác; code chỉ so prefix hoặc local name. | So QName đầy đủ và kiểm tra XML namespace. |
| Client nhận `MustUnderstand` Fault | Header có `mustUnderstand` nhưng recipient không có processor phù hợp. | Kiểm tra hợp đồng, SOAP role/actor và registered handlers. |
| Response không echo correlation | Interceptor chưa đăng ký, bị bỏ qua trong Fault hoặc response chưa được tạo. | Kiểm tra interceptor chain và lifecycle. |
| Retry dùng cùng request ID cho mọi attempt | Copy nguyên toàn bộ metadata outbound từ lần đầu. | Giữ correlation/idempotency, tạo request/attempt ID mới theo policy. |
| Cùng correlation nhưng tạo hai đơn hàng | Nhầm correlation với idempotency. | Áp dụng idempotency store/atomic check. |
| Log của request A chứa ID request B | MDC hoặc ThreadLocal không cleanup ở thread pool. | `finally`, `afterCompletion`, context propagation và test concurrency. |
| Trace ID đổi ở một hop không chủ đích | Propagator hoặc HTTP sender không được instrument. | So `traceparent` inbound/outbound, tracing SDK và export. |
| WS-Security fail sau khi thêm header | Sửa thông tin đã ký hoặc signed references/policy không phù hợp. | Inject trước khi ký, xác minh policy và reference. |
| ID từ khách hàng chứa token/PII | Nối ID từ dữ liệu nhạy cảm, log header không kiểm soát. | Random opaque IDs, validation, redaction, access control. |
| Client nhận 502/504 thay vì SOAP Fault | Lỗi proxy/transport trước hoặc ngoài xử lý SOAP. | Tìm gateway request ID và logs transport. |
| Event broker làm mất correlation | Chỉ giữ trong request-scoped `MessageContext`/MDC. | Đưa metadata vào event headers/envelope. |
| Client đoán ID để xem log của người khác | Không tách correlation khỏi authorization. | Đừng dùng ID làm credential; kiểm soát quyền truy vấn. |
| Hai header CorrelationId có giá trị khác nhau | Parser code chọn header đầu/cuối tùy tình cờ. | Kiểm tra duplicate theo QName; từ chối khi hợp đồng yêu cầu một. |

**Quy trình debug gợi ý:** bắt đầu với HTTP/SOAP request gốc và gateway ID → kiểm tra SOAP Header QName → xác định ID đã được validate/generate → kiểm tra `MessageContext`/MDC → capture outgoing SOAP/HTTP → kiểm tra log/tracing downstream → kiểm tra queue event metadata → so response hoặc Fault. Ghi rõ tầng cuối cùng còn giá trị đúng, thay vì đổi nhiều interceptor cùng lúc.

## 17. Bài thực hành và câu hỏi tình huống

### Tình huống A — Một correlation ID nhưng ba request riêng

Orders gọi Inventory và Payment sau khi nhận SOAP request gốc:

~~~text
Inbound Orders:   correlation=corr-27a, request=req-order-1
Outbound Stock:   correlation=?,       request=?
Outbound Payment: correlation=?,       request=?
~~~

**Đáp án:** giữ `corr-27a` cho hai downstream calls, tạo hai request ID mới riêng biệt, ví dụ `req-stock-1` và `req-payment-1`. Nếu có tracing, dùng các client spans riêng và đúng parent/span relationships.

### Tình huống B — SOAP response chứa RelatesTo

Request có `wsa:MessageID=urn:uuid:A`; response có `wsa:MessageID=urn:uuid:B` và `wsa:RelatesTo=urn:uuid:A`.

**Đáp án:** `B` định danh response message, `RelatesTo=A` liên kết với request message. Cặp này không thay thế correlation ID cho cả workflow khi có nhiều SOAP messages liên tiếp.

### Tình huống C — Client cũ chưa gửi correlation header

Một đối tác chưa gửi `ctx:CorrelationId`, trong khi contract hiện tại cho phép header optional.

**Đáp án:** gateway hoặc server có thể tạo ID mới, đưa vào log/response theo chính sách. Nếu hợp đồng mới yêu cầu bắt buộc, cần kế hoạch tương thích client cũ; không bật `mustUnderstand` rồi tự coi mọi đối tác đã hỗ trợ.

### Tình huống D — Timeout làm thanh toán bị lặp

Client gọi `ReservePayment` hai lần sau timeout. Hai request có cùng correlation ID nhưng không có idempotency key.

**Đáp án:** correlation chỉ hỗ trợ truy vết, **không ngăn side effect lặp**. Cần idempotency key scoped đúng, lưu kết quả/transaction atomically và trả kết quả tương thích cho retry cùng ý định. Attempt/request ID vẫn thay ở lần thử mới.

### Tình huống E — Log trộn dữ liệu giữa các khách hàng

Endpoint lưu correlation ID vào field mutable của một singleton interceptor và dùng khi thêm response header.

**Đáp án:** field có thể bị ghi đè bởi request khác. Chuyển sang `MessageContext` property hoặc request-scoped metadata, dọn MDC sau request và test concurrency.

### Tình huống F — Header tenant không được ký

WS-Security xác minh chữ ký hợp lệ trên SOAP Body, nhưng SOAP Header `<ctx:Tenant>other-company</ctx:Tenant>` không thuộc signed references. Endpoint tin ngay giá trị này để truy cập database.

**Đáp án:** lỗi **trust boundary/authorization**. Một phần SOAP được ký không bảo đảm tất cả sibling headers đã xác minh. Phải kiểm tra identity đáng tin, phạm vi chữ ký phù hợp và quyền truy cập tenant trước thao tác dữ liệu.

### Câu hỏi tự kiểm tra

1. Khi nào nên giữ nguyên correlation ID qua nhiều lời gọi? Khi nào request ID phải đổi?
2. `wsa:MessageID` và `wsa:RelatesTo` khác gì với custom `CorrelationId`?
3. Tại sao `@SoapHeader` không đọc được HTTP `traceparent`?
4. `MessageContext` và MDC có tự truyền qua HTTP hoặc message broker không?
5. Retry cùng idempotency key khác replay cùng WS-Security nonce/timestamp như thế nào?
6. Khi `mustUnderstand="1"` gây SOAP Fault, cần kiểm tra gì ở recipient?
7. Vì sao correlation ID được echo không tự chứng minh server đã xác thực client?
8. Cần theo dõi gì để metadata vẫn còn qua fan-out, queue redelivery và thread handoff?

## 18. Checklist triển khai và ghi nhớ

| Nội dung | Điều kiện đạt |
| --- | --- |
| Định nghĩa ID | Correlation, request, message, trace/span, idempotency và business IDs có phạm vi rõ. |
| Quy tắc sinh ID | Ai sinh, khi nào giữ/đổi, collision/format/length policies được thống nhất. |
| XSD/WSDL headers | QName, kiểu, `soap:header` và WS-Addressing policy được công bố nếu cần. |
| SOAP Header inbound | So QName, kiểm tra missing/duplicate/length/charset và trust boundary. |
| Context nội bộ | `MessageContext`/MDC dùng theo request, không chia sẻ mutable state. |
| Client outbound | `WebServiceTemplate` hoặc JAX-WS client inject metadata vào đúng tầng. |
| HTTP tracing | Instrumentation truyền `traceparent`/`tracestate` khi cần. |
| Async propagation | Event envelope/headers mang correlation/event ID, worker có context riêng. |
| Retry/idempotency | ID giữ/đổi đúng ngữ nghĩa, side effect được chống lặp. |
| SOAP response/Fault | Echo ID đúng policy, không rò nội dung nhạy cảm. |
| Trust/security | TLS, WS-Security và authorization; signed references bao phủ field cần tin. |
| Observability | Log/trace có service, operation, correlation/request/message/trace IDs, outcome. |
| Boundary limits | Giới hạn header/message size, XML parser, timeout và concurrency. |
| Interoperability | Client khác ngôn ngữ gửi/đọc header đúng WSDL và SOAP binding. |
| Test | Missing/duplicate/spoofed headers, fan-out, retry, queue, Fault, TLS/proxy. |

### Ghi nhớ

- **Correlation ID liên kết các bước cùng workflow**; **request ID** nhận diện một lần xử lý; **MessageID** nhận diện SOAP message; **trace ID/span ID** phục vụ distributed tracing; **idempotency key** hỗ trợ chống lặp side effect.
- **SOAP Header, HTTP Header và WS-Addressing là các kênh khác nhau**. Truyền qua nhiều hệ thống cần extract, validate, lưu context nội bộ rồi inject sang outgoing message/transport với đúng ngữ nghĩa.
- Trong Spring-WS, `@SoapHeader` có thể đọc SOAP Header, `MessageContext` chứa metadata trong request, `EndpointInterceptor` áp dụng logic chung, `WebServiceMessageCallback` hoặc `ClientInterceptor` bổ sung header outbound, còn MDC phục vụ log trong execution context.
- **WS-Security, TLS và authorization** quyết định mức độ tin cậy; correlation ID không phải chứng chỉ hoặc bằng chứng phân quyền.
- **Retry không đồng nghĩa một tác vụ nghiệp vụ mới**: giữ idempotency key cho cùng ý định, nhưng phân biệt các lần thử bằng request/attempt ID.
- Một tích hợp contract-first ổn định phải truy vết được luồng **SOAP client → gateway → endpoint → downstream SOAP → queue/worker → response/Fault**, đồng thời bảo vệ dữ liệu nhạy cảm và kiểm thử tương thích client/server.






