# MessageContext, thông điệp yêu cầu, phản hồi và thuộc tính xử lý

Trong Spring Web Services (**Spring-WS**), một yêu cầu SOAP đi qua nhiều lớp: transport, phân tích thông điệp, endpoint mapping, interceptor, chuyển XML thành đối tượng Java, xử lý nghiệp vụ và tạo phản hồi. Các thành phần này cần một nơi để truy cập **thông điệp đang xử lý** và chia sẻ **dữ liệu tạm thời trong cùng một lượt trao đổi**. Giao diện `org.springframework.ws.context.MessageContext` đảm nhận vai trò đó.

`MessageContext` không phải bản thân SOAP Envelope, không phải `HttpServletRequest` và cũng không phải kho trạng thái toàn cục của ứng dụng. Nó là **ngữ cảnh của một lượt xử lý thông điệp** (message exchange) ở phía Spring-WS. Ngữ cảnh chứa tham chiếu tới request, response và các property do các thành phần xử lý đặt vào để phối hợp với nhau.

Trong module **SPRING_WEB_SERVICES**, ta phát triển dịch vụ SOAP theo hướng **contract-first** với XSD/WSDL, JAXB, endpoint và SOAP client; đồng thời học SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích. Hiểu `MessageContext` giúp đặt chính xác từng trách nhiệm vào pipeline: **XSD/WSDL định nghĩa hợp đồng**, **JAXB ánh xạ payload**, **endpoint làm nghiệp vụ**, còn **MessageContext nối các bước xử lý trong một lượt trao đổi**, nhất là khi cần logging, correlation, validation hoặc xử lý lỗi.

## 1. Phân biệt message, context và transport

Hãy xét thao tác `GetOrder`. Client gửi SOAP Envelope có phần Body chứa `GetOrderRequest`; server trả `GetOrderResponse` hoặc SOAP Fault.

| Thành phần | Nó chứa hoặc đại diện cho điều gì? | Ví dụ sử dụng |
| --- | --- | --- |
| **`WebServiceMessage`** | Một thông điệp của Spring-WS; cung cấp cách truy cập payload | Đọc XML request hoặc ghi XML response |
| **`SoapMessage`** | Dạng `WebServiceMessage` dành cho SOAP, có Envelope, Header, Body, SOAP Action | Đọc SOAP Header và kiểm tra SOAP Fault |
| **`MessageContext`** | Ngữ cảnh của **một lượt trao đổi**: request, response, properties | Chuyển correlation ID nội bộ từ interceptor tới endpoint |
| **HTTP request/response** | Chi tiết transport khi SOAP chạy trên HTTP: URL, method, status, headers | TLS, reverse proxy, `Content-Type`, HTTP status |
| **JAXB object** | Biểu diễn Java của một payload theo XSD | `GetOrderRequest.getOrderId()` |
| **Application service** | Quy tắc nghiệp vụ độc lập với SOAP | Kiểm tra quyền xem đơn hàng, tra cứu trạng thái |

Thông điệp SOAP trên dây:

~~~xml
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

`MessageContext` là đối tượng **trong runtime Spring-WS** bao quanh việc xử lý yêu cầu đó. Các property trong context **không tự trở thành phần tử trong SOAP Body**, không tự thêm SOAP Header và không được chuyển tới client chỉ vì được gọi `setProperty`.

### Tên gần giống nhưng vai trò khác

Trong Spring MVC, developer thường làm việc trực tiếp với `HttpServletRequest` và `HttpServletResponse`. Trong Spring-WS, `MessageContext` giúp các thành phần SOAP làm việc với **thông điệp web service**, không buộc tất cả xử lý phải phụ thuộc vào HTTP.

SOAP có thể gắn với nhiều transport/binding khác nhau; vì vậy mã xử lý nghiệp vụ nên tránh giả định rằng mọi thông tin cần thiết đều lấy từ servlet request. Khi thật sự cần header HTTP, địa chỉ kết nối hoặc thuộc tính transport, dùng cơ chế transport phù hợp ở ranh giới hạ tầng.

## 2. Giao diện MessageContext cung cấp những thao tác nào?

Những phương thức thường gặp của `org.springframework.ws.context.MessageContext`:

| Phương thức | Công dụng | Lưu ý |
| --- | --- | --- |
| `getRequest()` | Lấy `WebServiceMessage` yêu cầu | Request đã được tạo cho lượt xử lý hiện tại |
| `hasResponse()` | Kiểm tra context hiện có response hay chưa | Dùng trước khi **chỉ muốn kiểm tra** sự tồn tại của response |
| `getResponse()` | Lấy `WebServiceMessage` phản hồi | Một số implementation, trong đó có mặc định của Spring-WS, có thể **tạo response khi được gọi lần đầu** |
| `setResponse(WebServiceMessage)` | Gắn message phản hồi cho context | Chỉ thay khi cơ chế xử lý thực sự yêu cầu và hiểu vòng đời response |
| `getProperty(String)` | Đọc thuộc tính của lượt xử lý | Có thể trả `null` khi chưa đặt |
| `setProperty(String, Object)` | Gắn dữ liệu tạm thời trong context | Tên property cần thống nhất và tránh va chạm |
| `containsProperty(String)` | Kiểm tra tên property có tồn tại | Phân biệt “không có key” với “giá trị null” khi cần |
| `removeProperty(String)` | Xóa property | Có ích để giải phóng tham chiếu hoặc dọn dữ liệu nhạy cảm |

Một số phiên bản API còn cung cấp cách duyệt tên property. Khi viết code dùng các API phụ trợ, hãy đối chiếu JavaDoc của **phiên bản Spring-WS cụ thể** mà dự án sử dụng.

**Ranh giới quan trọng:** property của context là dữ liệu **phục vụ xử lý trên server**. Nó khác với phần tử XSD trong SOAP Body, khác với SOAP Header và khác HTTP header. Muốn một giá trị xuất hiện ở client, dịch vụ phải đưa nó vào **thông điệp hoặc transport** theo hợp đồng đã công bố.

## 3. Vòng đời MessageContext trong pipeline Spring-WS

Khi một request đến qua HTTP, luồng khái quát:

~~~mermaid
flowchart TD
    T["HTTP transport / MessageDispatcherServlet"] --> F["WebServiceMessageFactory<br/>tạo request message"]
    F --> M["MessageContext<br/>request + properties<br/>response khi cần"]
    M --> D["MessageDispatcher<br/>endpoint mapping"]
    D --> I["EndpointInterceptor<br/>handleRequest"]
    I --> A["EndpointAdapter<br/>JAXB / payload resolver"]
    A --> E["@Endpoint<br/>service nghiệp vụ"]
    E --> R["Tạo response<br/>hoặc Fault"]
    R --> O["EndpointInterceptor<br/>handleResponse / handleFault"]
    O --> C["afterCompletion<br/>hoàn tất / dọn dẹp"]
    C --> H["Transport gửi SOAP response"]
~~~

Sơ đồ mô tả **trách nhiệm thông thường**, không khẳng định mọi lỗi đều đi qua toàn bộ các bước: lỗi parse XML, xác thực transport, SOAP security hoặc endpoint mapping có thể phát sinh **trước khi endpoint được gọi**. Thứ tự các interceptor và nhánh lỗi cụ thể phụ thuộc cấu hình/phiên bản framework.

Ở pipeline này:

1. **Transport/message factory** tạo request `WebServiceMessage` từ dữ liệu nhận được.
2. **MessageContext** chứa request và nơi lưu trạng thái xử lý ngắn hạn.
3. **Endpoint mapping** tìm method nhận payload có QName phù hợp, ví dụ `{urn:example:orders:v1}GetOrderRequest`.
4. **Interceptor** có thể kiểm tra message, đặt correlation ID, thời điểm bắt đầu, thực hiện validation hoặc security theo trách nhiệm đã cấu hình.
5. **Endpoint adapter** chuyển payload XML thành object JAXB nếu method và marshaller được hỗ trợ; endpoint gọi service nghiệp vụ.
6. **Response** được tạo/ghi vào message context; nếu phát sinh lỗi phù hợp, exception resolver hoặc SOAP stack có thể tạo SOAP Fault.
7. **Interceptor hậu xử lý** quan sát response/fault, dọn dẹp, rồi transport gửi message theo binding.

### Một MessageContext không phải một HTTP session

Hai request SOAP liên tiếp từ cùng client **không nên được giả định dùng chung context**. Các property chỉ là trạng thái của lượt xử lý hiện tại; chúng không có chức năng làm database, cache phân tán, session store hoặc bộ nhớ theo người dùng.

Nếu nghiệp vụ cần trạng thái lâu dài như idempotency key đã xử lý, trạng thái giao dịch hoặc lịch sử correlation, hãy lưu vào **hạ tầng trạng thái có vòng đời phù hợp**. `MessageContext` chỉ có thể giữ dữ liệu tạm thời để các bước của **cùng lượt xử lý** phối hợp với nhau.

## 4. Request và response: cách đọc đúng mà không tạo phản hồi ngoài ý muốn

### 4.1. `getRequest()` trả về message đầu vào

Trong một interceptor:

~~~java
import org.springframework.ws.context.MessageContext;
import org.springframework.ws.soap.SoapMessage;

public void inspectRequest(MessageContext context) {
    if (context.getRequest() instanceof SoapMessage soapRequest) {
        String soapAction = soapRequest.getSoapAction();
        // Chỉ sử dụng action để chẩn đoán/định tuyến theo hợp đồng
        // và không log thông tin nhạy cảm.
    }
}
~~~

`SoapMessage` giúp đọc các phần đặc thù của SOAP như Header, Body và SOAP Action. Không phải mọi `WebServiceMessage` đều cần được ép về `SoapMessage`; chỉ cast khi bạn biết transport/message factory của hệ thống tạo SOAP message tương ứng.

**Không nên phân tích SOAP Envelope bằng thao tác thay thế chuỗi** hoặc tiêu thụ stream payload nhiều lần mà không hiểu implementation. Với các message backed by streaming, việc đọc Source/stream không cẩn thận có thể khiến bước JAXB hoặc validation sau đó không còn dữ liệu để đọc. Ưu tiên API SOAP và các interceptor được framework cung cấp.

### 4.2. `hasResponse()` và `getResponse()` giải quyết hai nhu cầu khác nhau

Một lỗi tinh vi là viết:

~~~java
// Không nên làm chỉ để kiểm tra response đã có hay chưa:
boolean present = context.getResponse() != null;
~~~

Trong implementation ngữ cảnh mặc định thường gặp của Spring-WS, **`getResponse()` có thể khởi tạo response theo cơ chế lazy** nếu trước đó chưa có. Lời gọi trên có thể **thay đổi trạng thái context** và khiến các nhánh logic dựa trên “có response” hoạt động khác dự kiến.

Nếu chỉ cần biết liệu response đã tồn tại:

~~~java
if (context.hasResponse()) {
    // Response đã tồn tại; lúc này mới đọc.
    var response = context.getResponse();
    // Quan sát response theo chính sách xử lý.
}
~~~

Nếu **chủ đích tạo hoặc ghi response**, có thể dùng `getResponse()` theo cơ chế của implementation/adapter đang dùng. Nhưng việc gọi `getResponse()` **không phải lời bảo đảm phản hồi đã có nội dung XML hợp lệ**; phản hồi còn phải được marshal, đóng gói SOAP và gửi qua transport.

### 4.3. Không đánh đồng “chưa có response” với “đây là SOAP one-way”

Trước khi endpoint xử lý xong, `hasResponse()` có thể trả `false` trong một lượt trao đổi request–response thông thường. Điều đó không có nghĩa operation được mô hình hóa thành one-way trong WSDL.

Ngược lại, một implementation có thể tạo response rỗng vì một lời gọi API. Điều đó **không quyết định** transport sẽ gửi gì trong trường hợp operation one-way, hoặc cơ chế SOAP/HTTP cụ thể xử lý ra sao. Hãy căn cứ vào **WSDL message exchange pattern, endpoint contract và binding/transport**.

## 5. Mẫu thực hành: chia sẻ correlation ID nội bộ qua properties

Giả sử cần ghi log các giai đoạn xử lý `GetOrder` mà không truyền thông tin quan sát hạ tầng vào DTO JAXB. Một interceptor có thể tạo correlation ID và thời gian bắt đầu rồi lưu tạm trong `MessageContext`.

~~~java
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ws.context.MessageContext;
import org.springframework.ws.server.EndpointInterceptor;

public final class SoapTraceInterceptor implements EndpointInterceptor {
    private static final Logger log =
            LoggerFactory.getLogger(SoapTraceInterceptor.class);

    public static final String REQUEST_ID =
            SoapTraceInterceptor.class.getName() + ".requestId";
    private static final String START_NANOS =
            SoapTraceInterceptor.class.getName() + ".startNanos";

    @Override
    public boolean handleRequest(MessageContext context, Object endpoint) {
        context.setProperty(REQUEST_ID, UUID.randomUUID().toString());
        context.setProperty(START_NANOS, System.nanoTime());
        return true;
    }

    @Override
    public boolean handleResponse(MessageContext context, Object endpoint) {
        return true;
    }

    @Override
    public boolean handleFault(MessageContext context, Object endpoint) {
        // Có thể đánh dấu outcome nội bộ nếu cần, không sửa Fault ở đây.
        return true;
    }

    @Override
    public void afterCompletion(
            MessageContext context, Object endpoint, Exception ex) {
        Object started = context.getProperty(START_NANOS);
        Object requestId = context.getProperty(REQUEST_ID);

        if (started instanceof Long startedAt) {
            long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - startedAt);
            log.info("SOAP requestId={} durationMs={} hadException={}",
                    requestId, elapsedMs, ex != null);
        }

        context.removeProperty(START_NANOS);
        context.removeProperty(REQUEST_ID);
    }
}
~~~

Ví dụ dùng Java hỗ trợ `instanceof` pattern matching (Java 16+). Nếu dự án dùng Java cũ hơn, thay bằng cast truyền thống. Lớp `SoapTraceInterceptor` chỉ minh họa cơ chế đặt và đọc property; **còn phải đăng ký interceptor** trong cấu hình Spring-WS để nó tham gia pipeline.

Lợi ích của cách này:

- Endpoint và interceptor cùng trao đổi một correlation ID **trong lượt request hiện tại**.
- Không thêm field `requestId` vào XSD `GetOrderRequest` chỉ để phục vụ logging.
- Dữ liệu thời gian bắt đầu chỉ tồn tại ngắn hạn và được dọn trong `afterCompletion`.
- Key có prefix theo tên class để giảm nguy cơ va chạm với property khác.

**Giới hạn quan trọng:** `ex != null` chỉ cho biết callback nhận exception, **không đủ kết luận response có SOAP Fault hay không**. Một Fault có thể được tạo từ exception đã được xử lý hoặc từ nhánh khác mà callback không nhận exception. Nếu muốn ghi outcome chính xác, cần quan sát message/fault theo API và pipeline thực tế; không dùng cờ `hadException` làm thước đo duy nhất.

### Đọc correlation ID trong endpoint

Với cấu hình endpoint adapter hỗ trợ tiêm `MessageContext` vào method, endpoint có thể đọc property:

~~~java
import org.springframework.ws.context.MessageContext;
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
    public GetOrderResponse find(
            @RequestPayload GetOrderRequest request,
            MessageContext context) {
        String requestId =
                (String) context.getProperty(SoapTraceInterceptor.REQUEST_ID);
        // Có thể đưa requestId vào logging context khi cần.
        // Không dùng nó thay cho user identity/authorization.
        return service.findOrder(request.getOrderId());
    }
}
~~~

Ví dụ giả định `GetOrderRequest`/`GetOrderResponse` là các lớp JAXB đã sinh, `OrderService` đã tồn tại và method argument resolver hỗ trợ tham số `MessageContext` trong phiên bản Spring-WS đang dùng. Property có thể `null` nếu interceptor chưa đăng ký hoặc bị bỏ qua; endpoint không nên mặc định mọi property luôn có mặt.

Nếu muốn client nhìn thấy correlation ID, phải **quy định rõ trong hợp đồng**: đưa nó vào SOAP Header/Body hoặc transport header được phép. Đặt `context.setProperty(REQUEST_ID, ...)` chỉ giúp phía server phối hợp xử lý; không tự đẩy giá trị sang SOAP client.

## 6. Cách quản lý thuộc tính xử lý đúng vòng đời

`MessageContext` có thể xem như một bản đồ property theo lượt xử lý. Tuy tiện lợi, nó cần được dùng có chủ đích.

| Nên đặt vào context | Không nên đặt vào context như kho dữ liệu chính |
| --- | --- |
| Correlation ID của request hiện tại | Hồ sơ khách hàng cần lưu lâu dài |
| Thời điểm bắt đầu để tính latency | Cấu hình dùng chung của toàn ứng dụng |
| Kết quả phân loại nhẹ phục vụ interceptor khác | Tập XML/ảnh lớn chưa có giới hạn bộ nhớ |
| Cờ nội bộ đã đi qua validation theo pipeline có kiểm soát | Password, private key hoặc token để lưu tạm không cần thiết |
| Thông tin lỗi đã được lọc để ghi log | Trạng thái idempotency cần dùng giữa nhiều request |

### Những quy tắc thực hành

1. **Đặt key có namespace riêng**, ví dụ `com.example.soap.trace.requestId`, thay vì `id`, `user`, `data`.
2. **Thống nhất kiểu giá trị**. Nếu set `Long` rồi cast sang `String` ở interceptor sau sẽ gặp `ClassCastException`. Cân nhắc một lớp helper dùng chung các constant key nếu nhiều thành phần phối hợp.
3. **Kiểm tra property vắng mặt**, nhất là khi interceptor được bật/tắt theo môi trường, endpoint được kiểm thử độc lập hoặc chuỗi xử lý lỗi ngắn hơn bình thường.
4. **Không coi context là thread-safe/global**. Giữ dữ liệu trong lượt xử lý, không cất reference của context vào singleton field hoặc gửi nó tùy tiện sang background thread.
5. **Giữ object nhỏ và ngắn hạn**. Context có thể sống đủ lâu để giữ tham chiếu gây tăng bộ nhớ nếu gắn payload lớn hoặc kết quả truy vấn phức tạp.
6. **Dọn dữ liệu tạm khi thích hợp** trong callback hoàn tất, kể cả khi có Fault hoặc exception.
7. **Không dùng property làm bằng chứng bảo mật** nếu nó không được thiết lập từ một bước xác minh đáng tin cậy.

### `getProperty` và `containsProperty` không luôn là một câu hỏi

Nếu chỉ cần một giá trị, `getProperty(key)` thường là đủ. Nhưng có hai tình huống cần phân biệt:

- **Không có property tên đó**.
- **Property được đặt nhưng giá trị null** (nếu implementation cho phép lưu null).

`containsProperty(key)` cho biết key có mặt hay không theo API. Không thiết kế nghiệp vụ quan trọng dựa vào giả định mọi implementation sẽ giữ nguyên null-valued entries; tốt hơn là dùng **giá trị có kiểu rõ ràng** hoặc loại trạng thái riêng. Với cờ boolean, dùng `Boolean.TRUE`/`Boolean.FALSE` và kiểm tra property thiếu.

## 7. Interceptor và các callback liên quan đến response

Một `EndpointInterceptor` điển hình có bốn callback:

| Callback | Thời điểm thường gặp | Vai trò phù hợp |
| --- | --- | --- |
| `handleRequest` | Trước khi endpoint được gọi | Tạo trace, kiểm tra request, chuẩn bị dữ liệu xử lý |
| `handleResponse` | Khi xử lý tạo response bình thường | Quan sát/kiểm tra response theo chính sách |
| `handleFault` | Khi response là SOAP Fault | Quan sát Fault, chuẩn hóa logging theo hợp đồng |
| `afterCompletion` | Sau khi xử lý interceptor hoàn tất | Giải phóng reference, dọn trạng thái, ghi metrics |

Các method `handleRequest`, `handleResponse` và `handleFault` trả về `boolean`. Giá trị `true` thường cho phép pipeline tiếp tục, còn `false` có thể chặn các bước tiếp theo theo hợp đồng của interceptor. **Trả về `false` không tự tạo một SOAP Fault có ý nghĩa**: nếu muốn từ chối request, cần bảo đảm message lỗi được sinh ở tầng phù hợp hoặc cơ chế xử lý lỗi được kích hoạt.

Không giả định callback hậu xử lý luôn chạy cho **mọi** lỗi có thể xảy ra. Một lỗi TLS handshake hoặc proxy có thể xảy ra trước khi request trở thành `MessageContext`; lỗi XML parse có thể ngăn endpoint mapping. Logging, metrics và audit của toàn hệ thống nên có thêm quan sát ở **transport/gateway** để bao phủ những nhánh này.

### Có cần sửa response ngay trong interceptor không?

Một số interceptor có mục tiêu chính đáng như schema validation, thêm SOAP Header theo hợp đồng hoặc security. Tuy nhiên, **không chỉnh SOAP Body đã ký hoặc mã hóa** một cách tùy tiện. Nếu cần biến đổi payload nghiệp vụ, ưu tiên làm trong adapter/service trước khi marshaling và ký.

Đối với SOAP Header, dùng API SOAP chuyên dụng và tuân thủ namespace, `mustUnderstand`, role/actor và WS-Security policy. Với thông tin HTTP, xử lý tại transport layer thích hợp thay vì chèn lẫn vào JAXB request DTO.

## 8. SOAP Fault tồn tại trong response message, không phải property

Ở SOAP, lỗi giao thức/nghiệp vụ phù hợp thường được biểu diễn dưới dạng **SOAP Fault** trong Body, ví dụ SOAP 1.1:

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
    <soapenv:Body>
        <soapenv:Fault>
            <faultcode>soapenv:Client</faultcode>
            <faultstring>Order ID không hợp lệ</faultstring>
        </soapenv:Fault>
    </soapenv:Body>
</soapenv:Envelope>
~~~

SOAP 1.2 dùng cấu trúc Fault khác như `Code`, `Reason` và `Detail`. Định nghĩa typed fault chi tiết có thể được công bố trong XSD/WSDL theo hợp đồng. Spring-WS cung cấp cơ chế exception resolver, ví dụ `SoapFaultMappingExceptionResolver`, để ánh xạ exception phù hợp thành Fault.

**Phân biệt hai trạng thái:**

- `context.setProperty("error", ... )` chỉ đặt dữ liệu **nội bộ**; nó **không gửi lỗi tới SOAP client**.
- Response `SoapMessage` có SOAP Body chứa Fault mới là thông điệp lỗi giao thức được gửi theo SOAP binding, khi runtime/transport thực sự hoàn tất gửi.

Nếu cần quan sát Fault trong interceptor sau khi response đã được tạo:

~~~java
import org.springframework.ws.context.MessageContext;
import org.springframework.ws.soap.SoapMessage;

public boolean hasSoapFault(MessageContext context) {
    if (!context.hasResponse()) {
        return false;
    }
    if (context.getResponse() instanceof SoapMessage soapResponse) {
        return soapResponse.getSoapBody().hasFault();
    }
    return false;
}
~~~

Ví dụ sử dụng `hasResponse()` trước để không vô tình khởi tạo response chỉ nhằm kiểm tra trạng thái. `hasFault()` cho biết SOAP Body hiện chứa Fault; nó không nhất thiết bao phủ lỗi ở HTTP proxy, TLS, timeout hoặc kết nối chưa tới Spring-WS.

### Khi nào nên đặt error marker vào context?

Một interceptor có thể đặt property phân loại lỗi, thời gian xử lý, hoặc mã quan sát nội bộ để callback sau đọc được. Nhưng đó là **metadata trợ giúp**. Không xem marker là nguồn chân lý duy nhất thay cho `SOAP Fault`, kết quả exception resolver và HTTP transport status.

## 9. Kết hợp MessageContext với XSD/WSDL và JAXB

Một dịch vụ SOAP contract-first cần phân chia trách nhiệm rõ:

~~~mermaid
flowchart TB
    X["XSD / WSDL<br/>hợp đồng dữ liệu & dịch vụ"] --> M["SOAP request<br/>theo hợp đồng"]
    M --> C["MessageContext<br/>request + properties"]
    C --> V["Interceptor validation/security"]
    V --> J["JAXB unmarshal"]
    J --> E["Endpoint + Domain service"]
    E --> R["JAXB marshal"]
    R --> F["SOAP response / Fault"]
    F --> W["Transport tới client"]
~~~

Mỗi lớp trả lời câu hỏi riêng:

| Cần kiểm soát | Tầng chịu trách nhiệm |
| --- | --- |
| `orderId` có phải xuất hiện và thuộc namespace nào? | XSD |
| Operation `GetOrder` nhận/trả thông điệp nào, qua SOAP version/binding nào? | WSDL |
| Request được JAXB unmarshal thành class nào? | JAXB binding, endpoint adapter |
| Interceptor đã đánh dấu thời điểm bắt đầu xử lý chưa? | `MessageContext` property |
| Có cần thêm một SOAP Header được client hiểu không? | SOAP message/Header + contract |
| Caller có được phép truy cập order này không? | Bảo mật và service nghiệp vụ |
| Lỗi trả về có đúng dạng SOAP Fault không? | SOAP runtime/exception resolver + contract |

Đừng nhét property `requestId` nội bộ vào generated JAXB class rồi sửa XSD một cách vô ý. Mặt khác, cũng **không đặt dữ liệu nghiệp vụ cần trả về client chỉ trong MessageContext**; client không nhìn thấy nó.

### Một endpoint có thể không cần dùng MessageContext trực tiếp

Với thao tác đơn giản, method:

~~~java
@PayloadRoot(namespace = NS, localPart = "GetOrderRequest")
@ResponsePayload
public GetOrderResponse find(@RequestPayload GetOrderRequest request) {
    return service.findOrder(request.getOrderId());
}
~~~

là đủ khi framework đã tự quản lý message context và JAXB binding. **Không phải endpoint nào cũng nên tiêm MessageContext**; chỉ sử dụng khi method thực sự cần metadata SOAP/ngữ cảnh xử lý. Điều này giúp nghiệp vụ ít phụ thuộc framework và dễ kiểm thử.

## 10. MessageContext và bảo mật SOAP: ranh giới tin cậy

Các hệ thống doanh nghiệp thường yêu cầu xác minh chữ ký XML, UsernameToken, timestamp, chứng chỉ X.509 và có thể mã hóa thông điệp theo **WS-Security**. Spring-WS hỗ trợ tích hợp những cơ chế này qua interceptor và SOAP stack, ví dụ giải pháp dựa trên WSS4J khi phù hợp.

### Những điều không nên suy diễn

1. **Có SOAP Header chứa username không chứng minh username đã xác thực.** Header chỉ là dữ liệu đầu vào cho đến khi qua cơ chế xác minh phù hợp.
2. **Có property `authenticated=true` trong context cũng không tự chứng minh caller hợp lệ.** Giá trị đó chỉ đáng tin nếu được thiết lập từ một pipeline security đã xác minh chữ ký/token/chứng chỉ đúng chính sách và không thể bị ghi đè bởi nhánh không đáng tin cậy.
3. **TLS/mTLS và WS-Security bảo vệ phạm vi khác nhau.** TLS bảo vệ kênh truyền; chữ ký/mã hóa SOAP có thể bảo vệ phần message qua các trung gian theo chính sách.
4. **Không biến đổi phần đã ký sau khi xác minh/ký tùy ý.** JAXB hoặc interceptor ghi đè SOAP Body/Header có thể làm chữ ký không còn hợp lệ.
5. **Không lưu bí mật trong property để dễ debug.** Private key, mật khẩu, raw token và dữ liệu nhạy cảm cần cơ chế quản lý tương ứng, không nên nằm trong log/context không cần thiết.

### Ví dụ về một chuỗi bảo mật hợp lý ở mức trách nhiệm

~~~text
Nhận SOAP message
    ↓
Kiểm tra transport / TLS / mTLS (tại tầng kết nối phù hợp)
    ↓
Kiểm tra SOAP Header / WS-Security
    ↓
Xác minh token, chữ ký, timestamp, quyền truy cập
    ↓
Schema validation / JAXB binding theo pipeline đã thiết kế
    ↓
Endpoint thực thi nghiệp vụ
    ↓
Tạo payload phản hồi rồi ký/mã hóa khi chính sách yêu cầu
    ↓
Gửi SOAP response / Fault
~~~

Trình tự thực tế có thể khác vì các bước giải mã, xác minh chữ ký và validation ảnh hưởng lẫn nhau. Sơ đồ chỉ nhấn mạnh rằng **MessageContext vận chuyển trạng thái xử lý; nó không thay thế engine WS-Security hoặc chính sách xác thực**.

## 11. Context property và SOAP/HTTP header: chọn đúng kênh

Giả sử bạn có một mã tương quan `traceId`. Mã này có thể tồn tại ở ba nơi:

| Nơi chứa | Phạm vi | Client có nhìn thấy? | Trường hợp thích hợp |
| --- | --- | --- | --- |
| `MessageContext` property | Nội bộ một lượt xử lý Spring-WS | Không tự động | Correlation giữa interceptor và endpoint |
| **SOAP Header** | Trên SOAP message, có namespace/role | Có, nếu được gửi và client đọc | Correlation ID theo thỏa thuận tích hợp SOAP |
| **HTTP header** | Trên transport HTTP | Có, nếu proxy và client cho phép | Tracing tại gateway, điều phối transport |

Hướng thiết kế:

- Nếu chỉ muốn liên kết log server, **property trong context** có thể đủ.
- Nếu đối tác cần nhận mã tương quan và làm việc qua SOAP, **thỏa thuận SOAP Header hoặc response field** là lựa chọn cần xem xét.
- Nếu hệ thống tổ chức tracing tại HTTP gateway, có thể có **HTTP correlation header** độc lập; nhưng nó không tự trở thành SOAP Header.

Đừng tùy ý chuyển một tên header sang property context rồi kỳ vọng framework đồng bộ hai chiều. Cần **adapter rõ ràng** và quy tắc kiểm tra độ tin cậy, vì các giá trị từ request header của client có thể bị giả mạo.

## 12. Vòng đời, thread và xử lý bất đồng bộ

Spring-WS thường xử lý một request trong luồng điều phối của transport cho đến khi trả response. `MessageContext` thuộc **lượt xử lý**; không thể coi nó là đối tượng thread-safe hoặc có vòng đời dài hơn request.

### Không giữ MessageContext trong singleton

~~~java
// Ví dụ không an toàn về vòng đời:
@Component
public class IncorrectContextHolder {
    private MessageContext lastContext; // Không giữ request context dùng chung.

    public void remember(MessageContext context) {
        this.lastContext = context;
    }
}
~~~

Với nhiều request đồng thời, field `lastContext` bị ghi đè, có thể trộn dữ liệu giữa người dùng và giữ reference tới SOAP message quá lâu. Nếu cần lưu correlation cho nghiệp vụ bất đồng bộ, hãy trích **giá trị immutable cần thiết** rồi truyền nó bằng một DTO/job metadata phù hợp, thay vì đưa cả `MessageContext` sang worker queue.

### Dữ liệu dùng chung nên đặt ở đâu?

| Nhu cầu | Giải pháp phù hợp hơn |
| --- | --- |
| Một request cần trace ID xuyên interceptor và endpoint | `MessageContext` property |
| Một job async cần trace ID sau khi SOAP request hoàn tất | Copy trace ID vào metadata của job |
| Cần xử lý idempotency khi client retry | Database/cache có transaction hoặc cơ chế idempotency có kiểm soát |
| Cần cấu hình schema, SOAP endpoint URL | Spring configuration bean/properties |
| Cần lưu phiên đăng nhập giữa các request | Cơ chế session/security phù hợp, không đặt trong MessageContext |
| Cần metrics toàn hệ thống | Metrics registry/tracing platform, context chỉ là dữ liệu tạm |

### Cleanup và lỗi giữa chừng

`afterCompletion` giúp cleanup khi callback được framework gọi cho lượt xử lý thuộc phạm vi interceptor. Tuy nhiên, đừng đặt **duy nhất** một cơ chế dọn dẹp tài nguyên quan trọng ở đây nếu lỗi có thể xảy ra **trước khi interceptor được kích hoạt**. Với stream, transaction hoặc file tạm, luôn dùng lifecycle API và `try/finally` ở đúng tầng quản lý tài nguyên.

## 13. Kiểm thử MessageContext và pipeline xử lý

Chỉ test method `OrderService.findOrder` không chứng minh interceptor đã đặt property, endpoint nhận đúng QName hay response được gửi đúng SOAP contract.

### Một ma trận kiểm thử thực tế

| Nhóm | Tình huống | Điều cần xác minh |
| --- | --- | --- |
| **Request creation** | Gửi SOAP Body `GetOrderRequest` | Endpoint mapping nhận đúng QName |
| **Property propagation** | Interceptor đặt `requestId` trong `handleRequest` | Endpoint nhận được trong cùng lượt xử lý |
| **Property isolation** | Hai SOAP request kế tiếp/đồng thời | Không dùng chung `requestId` hoặc `startNanos` |
| **Response presence** | Kiểm tra context trước khi endpoint tạo response | `hasResponse()` phản ánh trạng thái; không gọi `getResponse()` chỉ để check |
| **Response content** | Endpoint trả `GetOrderResponse` | XML namespace, element order và dữ liệu khớp XSD |
| **Fault** | `orderId` không hợp lệ | SOAP Fault đúng phiên bản/contract, interceptor xử lý nhánh fault theo cấu hình |
| **Exception** | Service ném lỗi không mong đợi | Fault mapping/logging không lộ stack trace |
| **Security** | Token/chữ ký/timestamp sai | Bị từ chối theo chính sách, property xác thực không được tin nhầm |
| **Error before dispatch** | SOAP XML không parse được, TLS/proxy lỗi | Hệ thống quan sát được ở tầng tương ứng; không kỳ vọng endpoint callback chạy |
| **Interop** | Client bên ngoài sinh mã từ WSDL | Request/response/Fault được xử lý đúng độc lập với model Java nội bộ |

### Kiểm thử endpoint với Spring-WS

`MockWebServiceClient` cho phép gửi SOAP request tới endpoint trong test và kiểm tra response payload/Fault. Nó phù hợp để kiểm tra interceptor hoạt động cùng endpoint khi cấu hình test context chứa interceptor tương ứng.

Ví dụ XML request cố định:

~~~xml
<ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
    <ord:orderId>ORD-1024</ord:orderId>
</ord:GetOrderRequest>
~~~

Ở mức kiểm thử tích hợp, cần thực hiện:

1. Gửi request như trên qua `MockWebServiceClient` vào test application context của Spring-WS.
2. Kiểm tra endpoint hoặc service được gọi một lần với `ORD-1024`.
3. Kiểm tra interceptor gắn một correlation ID và endpoint có thể đọc được property trong cùng exchange.
4. Kiểm tra response XML có root `GetOrderResponse` đúng namespace, và hợp XSD khi bật schema validation.
5. Lặp lại request và xác nhận correlation ID độc lập; không lưu state request vào singleton.
6. Gửi request gây SOAP Fault rồi quan sát `handleFault`/`afterCompletion` và nội dung phản hồi thực tế theo cấu hình.

Với phía **SOAP client**, `MockWebServiceServer` dùng để kiểm tra `WebServiceTemplate` gửi request đã marshal đúng và xử lý response/Fault. Hai công cụ mock có phạm vi khác nhau; chúng không tự thay thế kiểm thử TLS, proxy, chứng chỉ hay tính tương thích thật với đối tác.

### Unit test interceptor khi cần

Có thể tạo `MessageContext` bằng implementation phù hợp như `DefaultMessageContext` cùng một `WebServiceMessageFactory` trong test, sau đó gọi callback của interceptor và kiểm tra property. Cách này kiểm tra logic nội bộ nhanh, nhưng phải nhớ:

- Unit test không chứng minh interceptor đã được đăng ký đúng vào `MessageDispatcher`.
- Unit test không chứng minh SOAP response được ghi ra HTTP client.
- Việc gọi `getResponse()` có thể tác động trạng thái context, nên test phân biệt rõ thời điểm trước/sau tạo response.

Chỉ nên viết những test giúp phát hiện lỗi thật, không cần lặp lại getter/setter thông thường của framework.

## 14. Những lỗi điển hình và cách tìm nguyên nhân

| Hiện tượng | Khả năng gây ra | Cách kiểm tra |
| --- | --- | --- |
| Endpoint nhận `null` khi đọc `requestId` | Interceptor chưa đăng ký, key khác hoặc không chạy | Cấu hình `EndpointInterceptor`, log `handleRequest`, constant key |
| `hasResponse()` đã là `true` sớm hơn dự kiến | Có thành phần đã gọi `getResponse()` và tạo lazy response | Tìm nơi chỉ định “kiểm tra” bằng `getResponse()!=null` |
| Log báo `hadException=false` nhưng client nhận Fault | Fault được tạo/đã xử lý không đi qua exception callback theo giả định | Kiểm tra `SoapBody.hasFault()` và resolver |
| Correlation ID giữa hai request bị trộn | Lưu context/property vào singleton hoặc static mutable field | Rà vòng đời object và xử lý đồng thời |
| Client không nhận header mặc dù đã đặt property | Nhầm `MessageContext` property với SOAP/HTTP header | Kiểm tra XML/HTTP response thực tế |
| JAXB class đúng nhưng endpoint không được chọn | Root QName của SOAP Body không khớp `@PayloadRoot` | So namespace URI/local name từ payload với mapping |
| Response có XML sai schema | Không bật validation hoặc Java tạo thiếu field bắt buộc | XSD validation inbound/outbound và model JAXB |
| Interceptor không chạy với lỗi XML bị hỏng | Lỗi xảy ra trước giai đoạn endpoint mapping/interceptor | Quan sát tầng parsing/transport |
| SOAP Fault bị biến thành HTML 502 | Proxy/gateway sinh lỗi ngoài ứng dụng | Phân biệt lỗi backend SOAP với lỗi HTTP gateway |
| Chữ ký SOAP sai sau khi interceptor chỉnh Body | Payload bị thay đổi sau bước ký hoặc trước bước verify | Kiểm tra WS-Security order, canonicalization |
| Bộ nhớ tăng sau nhiều request | Context/large message bị giữ reference quá lâu | Heap profiling, singleton/static references, cleanup |

### Quy trình chẩn đoán hiệu quả

~~~mermaid
flowchart TD
    A["Request SOAP đến gateway"] --> B{"Vào được Spring-WS?"}
    B -->|Không| C["Xem transport / proxy / TLS"]
    B -->|Có| D{"XML parse & endpoint mapping đúng?"}
    D -->|Không| E["Xem SOAP namespace / payload QName / parser"]
    D -->|Có| F{"Interceptor đã chạy?"}
    F -->|Không| G["Kiểm tra registration / mapping / short-circuit"]
    F -->|Có| H{"Property có mặt đúng key/type?"}
    H -->|Không| I["Kiểm tra setProperty, lifecycle, cleanup"]
    H -->|Có| J{"Response hoặc SOAP Fault đúng?"}
    J -->|Không| K["Kiểm tra JAXB, resolver, validation, security"]
    J -->|Có| L["Kiểm thử client và contract công bố"]
~~~

Nếu client nhận sai dữ liệu, đừng vội thay XSD/WSDL trước khi xác định lỗi nằm ở property nội bộ, JAXB mapping, response SOAP hay proxy. Mỗi tầng có một loại trạng thái và thông điệp riêng.

## 15. Các nguyên tắc thiết kế cần ghi nhớ

1. **`MessageContext` đại diện cho một lượt trao đổi**, chứa request, response và properties tạm thời; nó không phải SOAP Envelope hay HTTP session.
2. **`getRequest()` dùng để tiếp cận request message**; khi cần đọc SOAP-specific header/body, kiểm tra kiểu `SoapMessage`.
3. **`hasResponse()` dùng để kiểm tra response đã tồn tại**; `getResponse()` có thể tạo response trong một số implementation, nên không dùng bừa để hỏi “có hay không?”.
4. **`setProperty(...)` không sửa XML và không gửi dữ liệu cho client**. Muốn client nhận thông tin, phải đặt vào SOAP payload/header hoặc transport theo contract.
5. **Interceptor chia sẻ dữ liệu ngắn hạn qua properties**; endpoint không cần phụ thuộc vào context nếu chỉ xử lý nghiệp vụ với JAXB object.
6. **SOAP Fault là message lỗi có cấu trúc**, không phải một property `error` trong context.
7. **WS-Security không được chứng minh bằng một cờ property tự đặt**; phải có bước xác minh chữ ký/token/chứng chỉ theo chính sách.
8. **Không lưu MessageContext vào singleton, static field hoặc queue async**. Chỉ sao chép dữ liệu immutable cần thiết và dùng storage có vòng đời phù hợp.
9. **Kiểm thử qua SOAP message thật**: QName, JAXB mapping, response/Fault, interceptor, tính độc lập giữa request và khả năng tương thích với client.

## 16. Bài tập tự đánh giá

**Tình huống:** Đối tác gửi `GetOrderRequest`. Hệ thống cần ghi một correlation ID cho từng request, trả `GetOrderResponse` khi thành công và SOAP Fault khi mã đơn hàng không hợp lệ.

1. Chỉ ra ba nơi có thể lưu correlation ID: `MessageContext` property, SOAP Header, HTTP Header. Khi nào client nhìn thấy từng giá trị?
2. Giải thích vì sao `context.getResponse() != null` không phải cách an toàn để kiểm tra response đã được tạo.
3. Thiết kế `SoapTraceInterceptor` lưu `startNanos` và `requestId`, sau đó dọn trong `afterCompletion`. Nếu endpoint không đọc được key, những khả năng nào cần kiểm tra?
4. Dùng `MockWebServiceClient` gửi hai SOAP request liên tiếp. Nêu cách xác minh chúng nhận hai correlation ID khác nhau.
5. Gây lỗi nghiệp vụ để tạo SOAP Fault. Tại sao `ex == null` trong callback không đủ kết luận request thành công?
6. Một lập trình viên đặt `context.setProperty("error", "ORDER_NOT_FOUND")` rồi kết thúc xử lý. SOAP client có tự nhận được mã lỗi này không? Cần bổ sung thành phần nào?
7. Đối tác yêu cầu kiểm tra chữ ký số SOAP Body. Việc interceptor ghi `authenticated=true` khi thấy một UsernameToken có đủ không? Vì sao?
8. Một background worker cần correlation ID sau khi SOAP response đã trả. Có nên đưa cả `MessageContext` vào queue không? Đề xuất giải pháp giữ vòng đời dữ liệu đúng.

**Kết luận:** `MessageContext` là mắt xích điều phối **request, response và metadata tạm trong một lượt xử lý Spring-WS**. Dùng đúng `getRequest()`, `hasResponse()`, `getResponse()` và các property giúp interceptor, endpoint và xử lý lỗi phối hợp rõ ràng. Khi giữ ranh giới giữa **MessageContext nội bộ**, **SOAP Envelope theo XSD/WSDL**, **JAXB object**, **transport** và **WS-Security**, ứng dụng SOAP contract-first sẽ dễ quan sát, kiểm thử và tương thích hơn khi tích hợp với các hệ thống doanh nghiệp.
