# Tạo, đọc SoapHeader và SoapHeaderElement

Một SOAP request không chỉ có phần dữ liệu nghiệp vụ trong `Body`. Nó còn có **Header** để mang thông tin điều phối giữa các thành phần xử lý thông điệp, chẳng hạn mã tương quan, định tuyến, WS-Addressing hoặc các cấu trúc WS-Security. Trong **Spring Web Services (Spring-WS)**, các API `SoapHeader` và `SoapHeaderElement` cho phép ứng dụng đọc hoặc tạo những phần tử SOAP Header theo đúng **QName**, thay vì tự ghép chuỗi XML.

Nhưng Header không phải một “túi dữ liệu” tùy ý: mỗi phần tử có namespace, có thể nhắm đến một SOAP node/role, có thể mang `mustUnderstand` và phải tuân thủ hợp đồng tích hợp. Đặc biệt, **có Header không chứng minh request đã được xác thực**. Việc xác minh chữ ký, token và chứng chỉ phải giao cho cơ chế bảo mật phù hợp.

Bài học thuộc chương **Header và ngữ cảnh** của module **SPRING_WEB_SERVICES**. Trong quy trình SOAP **contract-first** của module, XSD/WSDL mô tả hợp đồng, JAXB ánh xạ payload Java, endpoint và SOAP client xử lý thông điệp, còn interceptor, SOAP Fault, XML security, WS-Security và TLS/mTLS bảo vệ trao đổi với hệ thống doanh nghiệp. Trọng tâm ở đây là **tạo và đọc `SoapHeader`/`SoapHeaderElement`** trong cả endpoint, interceptor và client, đồng thời phân biệt chúng với `MessageContext`, SOAP Body và HTTP Header.

## 1. SOAP Envelope có Header và Body

Một SOAP 1.1 Envelope minh họa:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:hdr="urn:example:headers:v1"
    xmlns:ord="urn:example:orders:v1">
    <soapenv:Header>
        <hdr:CorrelationId>req-8f21</hdr:CorrelationId>
    </soapenv:Header>
    <soapenv:Body>
        <ord:GetOrderRequest>
            <ord:orderId>ORD-1024</ord:orderId>
        </ord:GetOrderRequest>
    </soapenv:Body>
</soapenv:Envelope>
~~~

Ở ví dụ này:

- `soapenv:Envelope` là cấu trúc SOAP bên ngoài, theo namespace SOAP 1.1.
- `soapenv:Header` chứa một **header block** là `hdr:CorrelationId`.
- QName của header block là `{urn:example:headers:v1}CorrelationId`.
- `soapenv:Body` chứa payload nghiệp vụ `ord:GetOrderRequest` với QName `{urn:example:orders:v1}GetOrderRequest`.

Thứ tự SOAP hợp lệ ở mức Envelope là **Header (nếu có) trước Body**. Một Header có thể chứa nhiều header blocks. Phần tử `CorrelationId` là **ví dụ hợp đồng riêng**; SOAP không tự định nghĩa header này và cũng không bắt buộc mọi client phải gửi nó.

### SOAP Header, SOAP Body, HTTP Header không thay thế nhau

| Vị trí | Ví dụ | Mục đích | Cách truy cập điển hình |
| --- | --- | --- | --- |
| **SOAP Header** | `hdr:CorrelationId`, `wsse:Security` | Metadata trên thông điệp SOAP, có QName và thuộc tính SOAP | `SoapMessage.getSoapHeader()` |
| **SOAP Body** | `ord:GetOrderRequest` | Dữ liệu operation theo XSD/WSDL | `@RequestPayload`, JAXB hoặc XML `Source` |
| **HTTP Header** | `Content-Type`, `SOAPAction`, `Authorization` | Metadata transport HTTP | API transport hoặc cấu hình client/gateway |
| **MessageContext property** | `requestId`, thời điểm bắt đầu | Dữ liệu tạm **nội bộ một lượt xử lý** | `MessageContext.getProperty(...)` |

`MessageContext.setProperty("requestId", ...)` **không tạo** `<hdr:CorrelationId>`. Tương tự, thêm SOAP Header bằng `SoapHeader` **không đặt** HTTP header `SOAPAction`. Mỗi nơi có trách nhiệm và phạm vi truyền tải riêng.

## 2. Các API Spring-WS cần biết

Các interface chính thuộc ngăn xếp Spring-WS:

| API | Ý nghĩa | Thao tác hữu ích |
| --- | --- | --- |
| `WebServiceMessage` | Thông điệp ở lớp Spring Web Services | Truy cập payload |
| `SoapMessage` | Thông điệp SOAP: Envelope, Header, Body | `getSoapHeader()`, `getSoapBody()`, các thông tin SOAP tương ứng |
| `SoapHeader` | Container của các SOAP header blocks | Thêm phần tử mới, duyệt các header elements |
| `SoapHeaderElement` | Một header block cụ thể, có QName/nội dung/thuộc tính SOAP | `getName()`, `getText()`, `setText(...)`, `setMustUnderstand(...)`, `setActorOrRole(...)` |
| `MessageContext` | Ngữ cảnh của một lượt xử lý Spring-WS | `getRequest()`, `hasResponse()`, `getResponse()` và properties |
| `EndpointInterceptor` | Can thiệp trước/sau endpoint và nhánh Fault | `handleRequest`, `handleResponse`, `handleFault`, `afterCompletion` |

Ví dụ truy cập Header từ một request:

~~~java
import org.springframework.ws.context.MessageContext;
import org.springframework.ws.soap.SoapHeader;
import org.springframework.ws.soap.SoapMessage;

public SoapHeader requestHeader(MessageContext context) {
    if (!(context.getRequest() instanceof SoapMessage soapMessage)) {
        throw new IllegalStateException("Đang chờ SOAP request");
    }
    return soapMessage.getSoapHeader();
}
~~~

Đoạn mã dùng **Java 16+** cho `instanceof` pattern matching. Với Java cũ hơn, dùng kiểm tra kiểu và cast truyền thống. Ví dụ giả định service được triển khai bằng SOAP message factory; đừng cast mọi `WebServiceMessage` thành `SoapMessage` khi chưa kiểm tra.

### Vai trò của QName trong SoapHeaderElement

QName gồm **namespace URI + local name**; prefix chỉ là bí danh của namespace trong tài liệu XML.

~~~java
import javax.xml.namespace.QName;

public final class HeaderNames {
    public static final String NS = "urn:example:headers:v1";
    public static final QName CORRELATION_ID =
            new QName(NS, "CorrelationId");

    private HeaderNames() {}
}
~~~

Vì vậy hai XML sau cùng biểu diễn **một header QName**:

~~~xml
<hdr:CorrelationId xmlns:hdr="urn:example:headers:v1">
    req-8f21
</hdr:CorrelationId>

<!-- Tương đương về QName và text value, prefix khác nhau. -->
<t:CorrelationId xmlns:t="urn:example:headers:v1">
    req-8f21
</t:CorrelationId>
~~~

Không dùng `getNodeName()` hay regex tìm literal `hdr:CorrelationId` để quyết định header có đúng tên không; với `SoapHeaderElement`, ưu tiên so sánh trực tiếp `QName`.

## 3. Tạo một SOAP Header đơn giản ở phía server

Với một response SOAP, Spring-WS cho phép tạo header block từ `SoapHeader`:

~~~java
import javax.xml.namespace.QName;
import org.springframework.ws.soap.SoapHeaderElement;
import org.springframework.ws.soap.SoapMessage;

public void addCorrelationHeader(SoapMessage soapResponse,
                                 String correlationId) {
    QName name = new QName(
            "urn:example:headers:v1", "CorrelationId");

    SoapHeaderElement element =
            soapResponse.getSoapHeader().addHeaderElement(name);
    element.setText(correlationId);
}
~~~

Kết quả XML tương đương về mặt cấu trúc (prefix có thể khác tùy SOAP implementation):

~~~xml
<soapenv:Header
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
    <h:CorrelationId xmlns:h="urn:example:headers:v1">
        req-8f21
    </h:CorrelationId>
</soapenv:Header>
~~~

**Tại sao dùng `addHeaderElement(QName)` thay vì nối string?** Framework xử lý việc tạo phần tử trong đúng SOAP Header; QName giữ danh tính XML chính xác và `setText` ghi nội dung như text, tránh lỗi tự ghép các dấu `&`, `<`, `>`.

**Không gọi `addHeaderElement(...)` lặp lại mà không kiểm tra** nếu pipeline có nhiều thành phần cùng bổ sung `CorrelationId`. SOAP cho phép nhiều header blocks, nhưng hợp đồng nghiệp vụ có thể quy định chỉ một; header trùng là nguồn lỗi tương thích và rủi ro kiểm tra giá trị không nhất quán.

### 3.1. Tạo Header không có nghĩa gửi một SOAP message mới

`SoapHeaderElement` chỉ là phần tử **bên trong một SOAP message** đang được Spring-WS quản lý. Để client nhận được nó:

1. Endpoint/adapter phải tạo response hoặc Fault theo exchange pattern.
2. Header phải được thêm **vào response message**, không phải request message.
3. Spring-WS/transport phải thực sự gửi response đó.
4. Client phải đọc Header hoặc có SOAP processing stack hỗ trợ.

Nếu sửa `context.getRequest().getSoapHeader()` trên server và kỳ vọng response có Header mới, bạn đang sửa **thông điệp nhận vào** chứ không phải phản hồi.

### 3.2. Tạo Header có `mustUnderstand` và role/actor khi cần

Một header block có thể được đánh dấu phải được SOAP node đích hiểu và xử lý:

~~~java
SoapHeaderElement routing = soapResponse.getSoapHeader()
        .addHeaderElement(new QName(
                "urn:example:headers:v1", "RoutingHint"));
routing.setText("internal-route-a");
routing.setMustUnderstand(true);
// Chỉ đặt actor/role khi hợp đồng giao thức yêu cầu:
// routing.setActorOrRole("URI role/actor phù hợp SOAP version");
~~~

**Không bật `mustUnderstand=true` chỉ vì Header “quan trọng”.** Nếu receiver được nhắm đến không hiểu/xử lý Header bắt buộc, SOAP processing model yêu cầu phản ứng bằng **MustUnderstand Fault**. Một correlation ID tùy chọn thường không cần bật cờ này; routing/security header có thể cần, nhưng phải được thiết kế trong hợp đồng giữa các SOAP nodes.

`setActorOrRole(...)` giúp xác định SOAP node/role đích theo phiên bản SOAP. URI và semantics phụ thuộc SOAP 1.1 hay SOAP 1.2; không tự gán một HTTP hostname vào đây.

## 4. Đọc SoapHeader và SoapHeaderElement từ request

Khi nhận request, nên:

- Xác định **QName chính xác**.
- Không mặc định header chắc chắn hiện diện.
- Không âm thầm lấy header đầu tiên khi có **hai header trùng QName**.
- Kiểm tra giá trị theo hợp đồng, độ dài và ký tự cho phép.
- Không coi metadata do client gửi là chứng cứ xác thực.

Đoạn helper dưới đây đọc **header text đơn giản** và từ chối trường hợp trùng:

~~~java
import java.util.Iterator;
import javax.xml.namespace.QName;
import org.springframework.ws.soap.SoapHeader;
import org.springframework.ws.soap.SoapHeaderElement;

public final class HeaderReader {
    public static String readOptionalText(SoapHeader header, QName expected) {
        if (header == null) {
            return null; // Không có SOAP Header.
        }
        String found = null;
        boolean seen = false;

        Iterator<SoapHeaderElement> elements =
                header.examineAllHeaderElements();

        while (elements.hasNext()) {
            SoapHeaderElement current = elements.next();
            if (!expected.equals(current.getName())) {
                continue;
            }
            if (seen) {
                throw new IllegalArgumentException(
                        "SOAP Header bị trùng: " + expected);
            }
            seen = true;
            found = current.getText();
        }
        return found;
    }

    private HeaderReader() {}
}
~~~

Ý nghĩa:

- `examineAllHeaderElements()` cung cấp iterator để duyệt các header blocks.
- `current.getName()` là QName, không phải prefix văn bản.
- `current.getText()` phù hợp với **header chỉ mang text đơn giản**.
- `null` ở kết quả trên có thể được dùng cho “không có header” nếu hợp đồng quy định input là text thông thường; nếu cần phân biệt header rỗng với vắng mặt, nên trả về một kiểu kết quả có **presence flag**, không chỉ `String`.

Với dữ liệu `xs:string`, whitespace trong nội dung XML có thể là một phần giá trị. Đừng mặc định gọi `trim()` rồi coi “rỗng sau trim” là tương đương rỗng theo XSD: điều đó là **quy tắc chuẩn hóa nghiệp vụ** riêng. Nếu hợp đồng dùng `xs:token` hoặc restriction khác, cần tuân thủ cách xử lý whitespace của XML Schema và kiểm thử thực tế; khi có chữ ký WS-Security, không tự ý sửa XML đã ký để chuẩn hóa.

**Lưu ý API:** cách duyệt header và hỗ trợ đọc text phụ thuộc provider SOAP được Spring-WS tích hợp; hãy kiểm tra JavaDoc/behavior của phiên bản runtime khi cần những chức năng nâng cao. Không cố ép mọi header block về DOM rồi so sánh prefix.

### Header rỗng, thiếu và nil có khác nhau không?

Có. Với một header ứng dụng được định nghĩa bằng XSD:

~~~xml
<!-- Không có header CorrelationId -->

<hdr:CorrelationId xmlns:hdr="urn:example:headers:v1"/>

<hdr:CorrelationId xmlns:hdr="urn:example:headers:v1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:nil="true"/>
~~~

Header vắng mặt, phần tử rỗng và nil là ba trường hợp XML khác nhau. Có cho phép nil hay không phụ thuộc `nillable` của element XSD; quy tắc có/không có header còn có thể do hợp đồng WSDL, policy và ứng dụng quy định. Với một correlation ID bắt buộc **không rỗng**, helper đọc text cần được theo sau bởi validation độ dài/định dạng, thay vì tin rằng có một element đồng nghĩa giá trị hợp lệ.

## 5. Cấu trúc Header phức tạp: XML Source thay vì chỉ getText

Một header có thể chứa nhiều trường:

~~~xml
<hdr:RoutingInfo xmlns:hdr="urn:example:headers:v1">
    <hdr:TenantCode>tenant-a</hdr:TenantCode>
    <hdr:Channel>PARTNER_API</hdr:Channel>
</hdr:RoutingInfo>
~~~

Với cấu trúc này, `getText()` có thể trả text từ các node con nhưng **không bảo toàn danh tính từng trường**. Không nên phân tách text bằng dấu cách hay dựa vào thứ tự ký tự. Có hai cách phù hợp:

1. **JAXB/XSD binding:** khai báo header element trong schema, sinh class JAXB cho nó, rồi marshal/unmarshal từ XML `Source` với đúng QName.
2. **XML Source/DOM/StAX:** lấy XML của `SoapHeaderElement` theo API được hỗ trợ, parse bằng công cụ hiểu namespace và ràng buộc schema.

`SoapHeaderElement` có các khả năng làm việc với biểu diễn XML như `Source`/`Result` thông qua SOAP abstraction/provider. Khi dùng các API này, cần xác định đó là nội dung của **header block**, không phải toàn SOAP Envelope; trình tự dựng XML phải giữ đúng QName phần tử gốc và các phần tử con.

**Ví dụ về ý tưởng JAXB:**

~~~java
// Schema sinh ra một JAXB root class RoutingInfo có @XmlRootElement.
// Header block được lấy từ SOAP message theo đúng QName trước đó.
JAXBContext jaxbContext = JAXBContext.newInstance(RoutingInfo.class);
Unmarshaller unmarshaller = jaxbContext.createUnmarshaller();
unmarshaller.setSchema(routingInfoSchema);
RoutingInfo info =
        (RoutingInfo) unmarshaller.unmarshal(routingHeader.getSource());
~~~

Đây là ví dụ rút gọn (cần import Jakarta/Javax tương ứng, khai báo `routingInfoSchema` và `routingHeader`). Nếu generated type không có `@XmlRootElement`, kết quả JAXB có thể cần đọc dưới dạng `JAXBElement<RoutingInfo>` bằng overload hỗ trợ declared type; không ép class bằng cast sai. Trong ứng dụng lâu dài, tái sử dụng `JAXBContext` có kiểm soát và tạo `Unmarshaller` theo phạm vi thread, đồng thời hạn chế XML external entity/resolver.

### Parse XML không tin cậy một cách an toàn

Nếu tự tạo parser hoặc transformer trong XML adapter, phải thiết lập chính sách chống **XXE/DTD/external entities**, giới hạn kích thước/depth và bảo vệ khỏi tiêu tốn tài nguyên. Với `Source` mang stream, việc đọc nhiều lần có thể làm mất dữ liệu; không giả định XML parser cho phép rewind.

Nếu SOAP Header nằm trong vùng được ký/mã hóa bằng WS-Security, không thực hiện biến đổi tùy tiện **sau khi ký** hoặc trước/sau giải mã/xác minh trái chính sách. Việc đọc Header tại endpoint phải diễn ra sau các bước security cần thiết của pipeline.

## 6. MessageContext: nơi tìm request và response Header

`MessageContext` của Spring-WS giữ request, response và các property của một lượt xử lý. Từ context, interceptor hoặc thành phần phù hợp có thể truy cập:

~~~java
import org.springframework.ws.context.MessageContext;
import org.springframework.ws.soap.SoapMessage;

public void inspect(MessageContext context) {
    if (context.getRequest() instanceof SoapMessage request) {
        var inboundHeader = request.getSoapHeader();
        // Đọc header của thông điệp đến.
    }

    if (context.hasResponse()
            && context.getResponse() instanceof SoapMessage response) {
        var outboundHeader = response.getSoapHeader();
        // Đọc / thêm header của thông điệp phản hồi.
    }
}
~~~

**Vì sao kiểm tra `hasResponse()` trước?** Trong implementation context mặc định của Spring-WS, `getResponse()` có thể **khởi tạo response khi được gọi lần đầu**. Nếu chỉ muốn quan sát response đã tồn tại, gọi `getResponse() != null` có thể làm thay đổi trạng thái context và gây nhầm lẫn với quy trình tạo message. Khi chủ đích tạo/ghi response, code cần làm theo lifecycle của endpoint/adapter và SOAP stack.

### Property của MessageContext không phải SOAP Header

~~~java
context.setProperty("com.example.trace.requestId", "req-8f21");
~~~

Lệnh trên chỉ đặt metadata **nội bộ**; SOAP client không nhìn thấy nó. Muốn trả cùng ID ra Header, cần gọi `addHeaderElement(...)` trên **response `SoapMessage`**. Ngược lại, việc client gửi `hdr:CorrelationId` không làm Spring-WS tự thêm một property `requestId`. Một adapter/interceptor phải đọc header, chuẩn hóa/validate rồi chủ động đặt property nếu cần.

## 7. Ví dụ hoàn chỉnh: interceptor đọc Header yêu cầu và thêm Header phản hồi

Giả sử hệ thống quyết định:

- Header `{urn:example:headers:v1}CorrelationId` là **tùy chọn** trong request.
- Nếu không có, server tạo một ID mới.
- Nếu có, ID phải khớp quy tắc `[A-Za-z0-9_-]{1,64}`; có nhiều hơn một Header cùng QName thì từ chối.
- Response thành công **và** SOAP Fault (khi đã có response trong pipeline) có thể mang correlation ID để hỗ trợ đối soát.
- ID chỉ là **thông tin quan sát**, không phải bằng chứng quyền truy cập hay danh tính client.

Ví dụ `EndpointInterceptor`:

~~~java
import java.util.Iterator;
import java.util.Collections;
import java.util.UUID;
import java.util.regex.Pattern;
import javax.xml.namespace.QName;

import org.springframework.ws.context.MessageContext;
import org.springframework.ws.server.EndpointInterceptor;
import org.springframework.ws.soap.SoapHeader;
import org.springframework.ws.soap.SoapHeaderElement;
import org.springframework.ws.soap.SoapMessage;

public final class CorrelationHeaderInterceptor
        implements EndpointInterceptor {

    private static final QName CORRELATION =
            new QName("urn:example:headers:v1", "CorrelationId");
    private static final String PROPERTY =
            CorrelationHeaderInterceptor.class.getName() + ".correlationId";
    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");

    @Override
    public boolean handleRequest(MessageContext context, Object endpoint) {
        if (!(context.getRequest() instanceof SoapMessage request)) {
            throw new IllegalStateException("Yêu cầu không phải SOAP");
        }

        String id = null;
        boolean seen = false;
        SoapHeader incomingHeader = request.getSoapHeader();
        Iterator<SoapHeaderElement> headers =
                incomingHeader == null
                        ? Collections.emptyIterator()
                        : incomingHeader.examineAllHeaderElements();
        while (headers.hasNext()) {
            SoapHeaderElement element = headers.next();
            if (!CORRELATION.equals(element.getName())) {
                continue;
            }
            if (seen) {
                throw new IllegalArgumentException(
                        "CorrelationId xuất hiện nhiều lần");
            }
            seen = true;
            id = element.getText();
        }

        if (!seen) {
            id = UUID.randomUUID().toString();
        } else if (id == null || !SAFE_ID.matcher(id).matches()) {
            throw new IllegalArgumentException(
                    "CorrelationId không hợp lệ");
        }
        context.setProperty(PROPERTY, id);
        return true;
    }

    private void addHeaderIfPossible(MessageContext context) {
        if (!context.hasResponse()
                || !(context.getResponse() instanceof SoapMessage response)) {
            return;
        }
        Object value = context.getProperty(PROPERTY);
        if (!(value instanceof String id)) {
            return;
        }

        // Ví dụ giả định chỉ interceptor này sở hữu CorrelationId
        // trên response; khi tích hợp thật, kiểm tra trùng header.
        SoapHeaderElement header =
                response.getSoapHeader().addHeaderElement(CORRELATION);
        header.setText(id);
    }

    @Override
    public boolean handleResponse(MessageContext context, Object endpoint) {
        addHeaderIfPossible(context);
        return true;
    }

    @Override
    public boolean handleFault(MessageContext context, Object endpoint) {
        addHeaderIfPossible(context);
        return true;
    }

    @Override
    public void afterCompletion(
            MessageContext context, Object endpoint, Exception ex) {
        context.removeProperty(PROPERTY);
    }
}
~~~

Code dùng Java 16+ cho pattern matching; `EndpointInterceptor` phải được **đăng ký trong Spring-WS config** thì mới hoạt động. Phần Java được viết để minh họa lifecycle, không phải toàn bộ cấu hình một SOAP service. Ngoại lệ phát sinh từ `handleRequest` cần được ứng dụng xử lý theo **SOAP Fault policy** phù hợp; nếu exception xảy ra trước khi response tồn tại, không thể bảo đảm interceptor tự thêm correlation ID vào Fault.

### Luồng xử lý có Header

~~~mermaid
sequenceDiagram
    participant Client as SOAP client
    participant Interceptor as CorrelationHeaderInterceptor
    participant Endpoint as Spring-WS @Endpoint
    Client->>Interceptor: SOAP Header: CorrelationId=req-8f21
    Interceptor->>Interceptor: So QName, kiểm tra trùng/format
    Interceptor->>Interceptor: MessageContext.setProperty(id)
    Interceptor->>Endpoint: @RequestPayload GetOrderRequest
    Endpoint-->>Interceptor: GetOrderResponse hoặc Fault
    Interceptor->>Interceptor: Thêm CorrelationId vào response Header
    Interceptor-->>Client: SOAP response / Fault có Header khi có thể
    Note over Interceptor: afterCompletion dọn property
~~~

### Vì sao interceptor không phải hàng rào duy nhất?

`EndpointInterceptor` ở pipeline endpoint có thể **không chạy** khi request bị chặn trước bước mapping: TLS handshake fail, XML không parse được, không có endpoint phù hợp, hoặc lỗi gateway. Vì vậy yêu cầu “mọi lỗi HTTP/SOAP phải luôn có CorrelationId Header” cần giải pháp quan sát **ở nhiều tầng**, không chỉ trông chờ interceptor này.

## 8. Đọc Header trực tiếp trong endpoint bằng @SoapHeader

Khi endpoint thực sự cần một Header nghiệp vụ, Spring-WS cung cấp annotation `@SoapHeader` cho method argument ở những endpoint adapters hỗ trợ:

~~~java
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;
import org.springframework.ws.soap.SoapHeaderElement;
import org.springframework.ws.soap.server.endpoint.annotation.SoapHeader;

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
            @RequestPayload GetOrderRequest request,
            @SoapHeader("{urn:example:headers:v1}CorrelationId")
                    SoapHeaderElement correlationHeader) {

        String correlationId = correlationHeader.getText();
        // Validate dữ liệu Header theo contract nghiệp vụ.
        return service.findOrder(request.getOrderId(), correlationId);
    }
}
~~~

**Điều kiện của ví dụ:** lớp JAXB request/response và service đã tồn tại; cấu hình endpoint adapter hỗ trợ injection này; hợp đồng **yêu cầu Header hiện diện** cho method đang dùng. Nếu Header optional, cần kiểm thử rõ hành vi của argument resolver khi thiếu Header, hoặc đọc qua `MessageContext`/interceptor và tự xử lý absence. Không tự gọi `getText()` trên một reference giả định luôn có khi chưa xác minh đường đi.

Ưu điểm của `@SoapHeader`: endpoint thể hiện rõ một **header nghiệp vụ cụ thể** cần lấy, không phải tự duyệt toàn bộ SOAP Envelope trong mọi method.

Nhược điểm: endpoint phụ thuộc trực tiếp vào Spring SOAP API, phù hợp ở **adapter biên** nhưng không nên đẩy `SoapHeaderElement` vào domain service. Hãy chuyển giá trị thành Java DTO/trường đã validate trước khi gọi nghiệp vụ.

### @SoapHeader khác @RequestPayload

~~~java
@RequestPayload GetOrderRequest request
@SoapHeader("{urn:example:headers:v1}CorrelationId")
        SoapHeaderElement header
~~~

Tham số đầu tiên lấy **payload Body** theo XSD request; tham số thứ hai lấy **một Header block**. Đặt annotation `@RequestPayload` trên `SoapHeaderElement` hoặc tìm header trong `GetOrderRequest` khi schema Body không mô tả nó là sai ranh giới.

## 9. SOAP client: thêm Header qua WebServiceTemplate

Một client Spring-WS dùng `WebServiceTemplate` có thể thêm SOAP Header trong `WebServiceMessageCallback` trước khi gửi request:

~~~java
import javax.xml.namespace.QName;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.soap.SoapHeaderElement;
import org.springframework.ws.soap.SoapMessage;

public final class OrderSoapClient {
    private final WebServiceTemplate template;

    public OrderSoapClient(WebServiceTemplate template) {
        this.template = template;
    }

    public Object getOrder(GetOrderRequest request, String correlationId) {
        return template.marshalSendAndReceive(request, message -> {
            if (!(message instanceof SoapMessage soap)) {
                throw new IllegalStateException("Cần SOAP message");
            }
            SoapHeaderElement element = soap.getSoapHeader()
                    .addHeaderElement(new QName(
                            "urn:example:headers:v1", "CorrelationId"));
            element.setText(correlationId);
        });
    }
}
~~~

Đoạn mã giả định `WebServiceTemplate` đã có marshaller/unmarshaller thích hợp (ví dụ `Jaxb2Marshaller`) và default URI hoặc đường dẫn endpoint đã được cấu hình, generated `GetOrderRequest` có root binding được hỗ trợ. Với một XJC model cần `JAXBElement`, client phải sử dụng root object factory phù hợp; không sửa class generated.

**Trước khi gửi**, client nên validate định dạng/độ dài `correlationId` và tránh đặt giá trị chứa dữ liệu nhạy cảm. `WebServiceMessageCallback` chạy ở phía client khi request message đang được chuẩn bị; không tạo Header ở phía server.

### SOAPAction và Header là hai cơ chế khác nhau

Trong SOAP 1.1, nếu WSDL định nghĩa SOAPAction, có thể truyền callback phù hợp như `SoapActionCallback` hoặc phối hợp callback theo API client; **không tạo** một SOAP Header block tên `SOAPAction` để thay thế HTTP header `SOAPAction`.

Với SOAP 1.2, action có thể nằm trong tham số media type `application/soap+xml`; với WS-Addressing, `wsa:Action` là SOAP Header riêng. Chúng có vai trò khác nhau và không nên được đồng nhất chỉ vì đều chứa từ “action”.

## 10. Đọc Header trên response của SOAP client

Khi client cần đối soát `CorrelationId` mà server trả ra, có thể đặt logic vào `ClientInterceptor` để quan sát response SOAP trong cùng lượt trao đổi:

~~~java
import org.springframework.ws.client.support.interceptor.ClientInterceptor;
import org.springframework.ws.context.MessageContext;
import org.springframework.ws.soap.SoapMessage;

public class CorrelationResponseInterceptor
        implements ClientInterceptor {

    @Override
    public boolean handleRequest(MessageContext context) {
        return true;
    }

    @Override
    public boolean handleResponse(MessageContext context) {
        if (context.hasResponse()
                && context.getResponse() instanceof SoapMessage response) {
            String id = HeaderReader.readOptionalText(
                    response.getSoapHeader(), HeaderNames.CORRELATION_ID);
            // Đưa id vào cơ chế tracing ứng dụng đã thiết kế.
            // Không tin rằng id này chứng minh danh tính server.
        }
        return true;
    }

    @Override
    public boolean handleFault(MessageContext context) {
        return handleResponse(context);
    }

    @Override
    public void afterCompletion(MessageContext context, Exception ex) {
        // Dọn dữ liệu client-side nếu cần.
    }
}
~~~

Ví dụ cần đăng ký `ClientInterceptor` vào `WebServiceTemplate` theo cấu hình client thực tế. Nếu framework/client mapping xử lý Fault trước hoặc sau một callback khác, hãy kiểm tra qua integration test trên phiên bản sử dụng; đừng suy luận rằng chỉ có `handleResponse` là đủ khi cần đọc Header đi cùng SOAP Fault.

**Lưu ý về SOAP response Header:** hợp đồng có thể yêu cầu correlation ID **cả khi thành công và khi Fault**. Phải kiểm thử từng nhánh server vì interceptor response/fault có thể được gọi trong các điều kiện khác nhau, và lỗi trước khi tạo SOAP message có thể không tạo Header nào.

## 11. mustUnderstand, actor, role và relay

SOAP Header có cơ chế kiểm soát **header block dành cho node nào** và node đích có bắt buộc hiểu header hay không.

### 11.1. SOAP 1.1

Ví dụ:

~~~xml
<soapenv:Header
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:hdr="urn:example:headers:v1">
    <hdr:RoutingHint
        soapenv:mustUnderstand="1"
        soapenv:actor="http://schemas.xmlsoap.org/soap/actor/next">
        route-a
    </hdr:RoutingHint>
</soapenv:Header>
~~~

Trong SOAP 1.1:

- `soapenv:mustUnderstand="1"` có nghĩa header block **bắt buộc được hiểu/xử lý** bởi SOAP node mà nó nhắm đến; `"0"` là không bắt buộc.
- `soapenv:actor` xác định vai trò/node nhận header; `http://schemas.xmlsoap.org/soap/actor/next` có nghĩa header dành cho node tiếp theo theo processing model.
- Header không có actor thường nhắm tới **ultimate receiver**.

**Không phải cứ thấy header không quen là trả MustUnderstand Fault.** Cần xét header có **được nhắm tới SOAP node hiện tại** và có `mustUnderstand` bắt buộc hay không. Một intermediary không nhất thiết xử lý header chỉ dành cho recipient cuối.

### 11.2. SOAP 1.2

SOAP 1.2 thay đổi namespace Envelope và dùng `role` thay cho `actor`. Nó cũng định nghĩa `relay` đối với một số tình huống xử lý qua trung gian:

~~~xml
<env:Header
    xmlns:env="http://www.w3.org/2003/05/soap-envelope"
    xmlns:hdr="urn:example:headers:v1">
    <hdr:RoutingHint
        env:mustUnderstand="true"
        env:role="http://www.w3.org/2003/05/soap-envelope/role/next"
        env:relay="true">
        route-a
    </hdr:RoutingHint>
</env:Header>
~~~

Một số điểm:

| Tiêu chí | SOAP 1.1 | SOAP 1.2 |
| --- | --- | --- |
| Envelope namespace | `http://schemas.xmlsoap.org/soap/envelope/` | `http://www.w3.org/2003/05/soap-envelope` |
| Đích xử lý Header | `actor` | `role` |
| Giá trị bắt buộc hiểu | `mustUnderstand="1"` | `mustUnderstand="true"` hoặc lexical boolean tương ứng |
| Cơ chế `relay` | Không có attribute SOAP 1.2 `relay` | Có, dùng theo SOAP 1.2 processing model |
| Fault “không hiểu Header” | SOAP Fault tương ứng SOAP 1.1 | `env:MustUnderstand` với cấu trúc Fault SOAP 1.2 |

**Cách viết attribute phải đúng namespace của SOAP version.** Không lấy `soapenv:actor` của SOAP 1.1 rồi chèn vào message SOAP 1.2. Tương tự, không coi `relay=true` là “forward mọi Header” mà không xét node role, targeting và trạng thái đã xử lý.

### 11.3. Giá trị role/mustUnderstand không phải quyết định authorization

Một client có thể tự đặt `mustUnderstand` hoặc một header có tên `AdminRoute`. Điều đó không chứng minh người gửi có quyền quản trị. Quyết định cấp quyền phải dựa trên **identity/claims đã xác minh**, chính sách dịch vụ và business authorization, không dựa vào routing metadata chưa tin cậy.

## 12. Đưa Header vào hợp đồng XSD/WSDL khi cần tương thích

Một header ứng dụng mà đối tác bắt buộc gửi nên có **schema và tài liệu hợp đồng rõ ràng**. Ví dụ định nghĩa element riêng cho CorrelationId:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           targetNamespace="urn:example:headers:v1"
           xmlns:hdr="urn:example:headers:v1"
           elementFormDefault="qualified">
    <xs:element name="CorrelationId">
        <xs:simpleType>
            <xs:restriction base="xs:string">
                <xs:minLength value="1"/>
                <xs:maxLength value="64"/>
                <xs:pattern value="[A-Za-z0-9_-]+"/>
            </xs:restriction>
        </xs:simpleType>
    </xs:element>
</xs:schema>
~~~

Với WSDL 1.1, header có thể được mô tả trong SOAP binding bằng `soap:header`, tham chiếu một `wsdl:message` và `wsdl:part`:

~~~xml
<!-- Trích đoạn minh họa; các prefix/binding definitions đã khai báo. -->
<wsdl:message name="TrackingHeaderMessage">
    <wsdl:part name="correlation"
               element="hdr:CorrelationId"/>
</wsdl:message>

<wsdl:binding name="OrdersSoap11Binding"
              type="tns:OrdersPortType">
    <soap:binding style="document"
                  transport="http://schemas.xmlsoap.org/soap/http"/>
    <wsdl:operation name="GetOrder">
        <soap:operation soapAction="urn:example:orders:GetOrder"/>
        <wsdl:input>
            <soap:body use="literal"/>
            <soap:header message="tns:TrackingHeaderMessage"
                         part="correlation"
                         use="literal"/>
        </wsdl:input>
        <wsdl:output>
            <soap:body use="literal"/>
            <soap:header message="tns:TrackingHeaderMessage"
                         part="correlation"
                         use="literal"/>
        </wsdl:output>
    </wsdl:operation>
</wsdl:binding>
~~~

Đoạn trên **không phải WSDL hoàn chỉnh**: `definitions` cần khai báo namespaces `wsdl`, `soap`, `tns`, `hdr`, phần schema cho Header, input/output Body messages, portType và service/port. Đây là mẫu để phân biệt **Header binding** với **Body binding** khi thiết kế contract-first.

**Không mặc định `@PayloadRoot` sẽ định tuyến theo WSDL `soap:header`.** `@PayloadRoot` thường dựa vào phần tử gốc Body. Header có thể được kiểm tra riêng bằng `@SoapHeader` hoặc interceptor/argument resolver phù hợp; routing theo SOAPAction hay WS-Addressing là các strategy riêng.

### WSDL khai báo Header không tự validate mọi Header ở server

Có phần tử XSD/WSDL không có nghĩa runtime tự kiểm tra tất cả SOAP Header. `PayloadValidatingInterceptor` có thể được cấu hình để kiểm tra payload Body, nhưng **không nên suy ra nó tự validate toàn bộ Header tùy chỉnh**. Nếu yêu cầu kiểm tra dữ liệu Header, hãy dùng schema-aware binding/validator riêng và kiểm thử negative cases.

Tương tự, WSDL `soap:header` chỉ mô tả thông điệp/binding; nó không thay thế **WS-SecurityPolicy** hoặc việc thiết lập `mustUnderstand` và xác thực ở runtime. Đối tác có thể có SOAP stacks khác nhau, vì vậy cần kiểm tra khả năng code generation và xử lý Header của client thực tế.

## 13. WS-Security Header: xử lý khác Header metadata thông thường

Một SOAP request bảo mật có thể chứa cấu trúc:

~~~xml
<soapenv:Header
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">
    <wsse:Security soapenv:mustUnderstand="1">
        <!-- Security token, timestamp, signature được tạo bởi security stack. -->
    </wsse:Security>
</soapenv:Header>
~~~

Đây là **trích đoạn cú pháp Header**, không phải một WS-Security message hoàn chỉnh hay hợp lệ theo một security policy cụ thể: phần tử `wsse:Security` còn thiếu các token/chữ ký thực tế. Namespace URI phải khớp thông số OASIS. Các cấu trúc bên trong có thể gồm `wsu:Timestamp`, `wsse:UsernameToken`, `ds:Signature` hoặc thông tin mã hóa theo chính sách được thỏa thuận.

Tuy về mặt XML `wsse:Security` cũng là một SOAP Header block, **không nên dùng `SoapHeaderElement.getText()` để kiểm tra UsernameToken/Signature rồi đánh dấu “đã xác thực”**. Security stack phải kiểm tra:

- Chữ ký XML và những phần **thực sự được ký** (chống signature wrapping hoặc chọn nhầm node).
- Timestamp, thời gian hiệu lực và cơ chế replay prevention theo policy.
- Chứng chỉ X.509/truststore, chuỗi tin cậy, mục đích sử dụng và identity mapping.
- UsernameToken hoặc token khác theo profile, thuật toán và cấu hình.
- Mã hóa/giải mã body/header theo thứ tự xử lý đã thống nhất.

Với Spring-WS, các thành phần như **`Wss4jSecurityInterceptor`** được cấu hình để xử lý chính sách thích hợp. Sau khi bảo mật đã xác minh, application mới sử dụng kết quả đáng tin cậy để authorization; đừng lấy một property `authenticated=true` do client cung cấp hoặc tự đánh dấu trước bước verify.

### SOAP Header không thay thế TLS/mTLS

TLS bảo vệ kết nối giữa client và endpoint/proxy; mTLS dùng chứng chỉ để xác thực kết nối ở tầng transport. WS-Security xử lý tính toàn vẹn, xác thực và/hoặc bí mật ở tầng **SOAP message** theo policy. Việc có Header chứa `CorrelationId` hay `Security` không chứng minh TLS đã được bật; ngược lại TLS đúng không đảm bảo một Header tùy chỉnh đã hợp lệ với XSD.

### Chú ý chỉnh sửa Header đã ký

Nếu SOAP Header hoặc Body nằm trong phần dữ liệu được ký, việc sửa nội dung **sau khi ký** có thể làm chữ ký không còn hợp lệ. Một interceptor bổ sung correlation header cần được đặt ở thời điểm phù hợp với bước ký message; nếu Header mới được yêu cầu phải được ký, phải bao gồm nó trong cơ chế ký theo policy.

## 14. Nhận Header sai: lựa chọn SOAP Fault và logging

Một header tùy chỉnh có thể không đúng hợp đồng:

| Lỗi | Ví dụ | Phản ứng cần thiết kế |
| --- | --- | --- |
| **Thiếu Header bắt buộc** | Không có `CorrelationId` nhưng partner contract yêu cầu | Trả lỗi client/request phù hợp SOAP policy |
| **Trùng QName** | Hai `hdr:CorrelationId` | Từ chối hoặc có quy tắc hợp đồng minh bạch; tránh chọn tùy tiện |
| **Header sai namespace** | `urn:example:headers:v2` thay cho v1 | Không coi là cùng Header; cân nhắc version negotiation |
| **Giá trị không hợp schema** | ID dài quá giới hạn, ký tự lạ | Validate và phản hồi lỗi hợp đồng |
| **MustUnderstand sai** | Header bắt buộc nhắm tới node không hiểu | Xử lý MustUnderstand Fault theo SOAP version |
| **Sai role/actor** | Header nhắm intermediary khác | Tôn trọng SOAP processing model |
| **WS-Security không hợp lệ** | Signature/timestamp/token sai | Từ chối theo security policy, không cho nghiệp vụ chạy |
| **Không có response SOAP** | TLS/proxy lỗi trước Spring-WS | Lỗi transport; không thể cam kết trả SOAP Header/Fault |

Ví dụ SOAP 1.1 Fault mang cấu trúc:

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
    <soapenv:Body>
        <soapenv:Fault>
            <faultcode>soapenv:Client</faultcode>
            <faultstring>CorrelationId không hợp lệ</faultstring>
        </soapenv:Fault>
    </soapenv:Body>
</soapenv:Envelope>
~~~

Đây là ví dụ **Fault nghiệp vụ/giao thức cho Header không hợp lệ**, không phải chính xác Fault mà Spring-WS tự động trả nếu interceptor ném `IllegalArgumentException`. Cần cấu hình exception resolver hoặc handler thích hợp để ánh xạ lỗi thành SOAP Fault đúng contract. Đối với `mustUnderstand` bắt buộc không được xử lý, dùng **MustUnderstand Fault** theo SOAP version thay vì một business fault thông thường.

SOAP 1.2 dùng `Code`, `Reason`, `Detail` và các quy tắc khác SOAP 1.1. Không sao chép nguyên cấu trúc SOAP 1.1 vào SOAP 1.2.

**Logging:** ưu tiên ghi correlation ID đã được validate, QName, role, loại lỗi và thời gian xử lý. Không dump toàn bộ SOAP Header nếu có token, chữ ký, certificate assertion hoặc dữ liệu nhạy cảm. Trên hệ thống nhiều tenant, correlation ID do client cấp không được xem là globally unique hay đáng tin tuyệt đối nếu chưa có quy tắc.

## 15. Kiểm thử Header ở phía endpoint và client

Một test trên Java service không chứng minh SOAP Header được serialize đúng hoặc đọc đúng QName. Cần kiểm thử trên **SOAP message thực**.

### 15.1. Ma trận test đề xuất

| Tình huống | Input | Kết quả mong đợi |
| --- | --- | --- |
| Header chuẩn | `hdr:CorrelationId=req-8f21` | Interceptor/endpoint đọc đúng QName và value |
| Đổi prefix | `h:CorrelationId` cùng URI | Vẫn nhận ra Header |
| Đổi namespace URI | `urn:example:headers:v2` | Không coi là header v1 |
| Thiếu Header optional | Không có CorrelationId | Server tạo ID mới theo ví dụ |
| Thiếu Header required | Không có header theo contract bắt buộc | Lỗi hợp đồng có kiểm soát |
| Giá trị rỗng | `<hdr:CorrelationId/>` | Bị từ chối nếu quy tắc không cho rỗng |
| Header trùng | Hai block cùng QName | Không chọn tùy tiện; lỗi theo policy |
| Nội dung có ký tự XML | ID chứa `&`/`<` | Được escape đúng khi tạo, rồi validate và có thể từ chối format |
| Header khác | `hdr:RoutingHint` có mặt | Không bị nhận nhầm thành CorrelationId |
| Response thành công | Server tạo `GetOrderResponse` | Có Header khi cấu hình yêu cầu |
| SOAP Fault do nghiệp vụ | Endpoint ném lỗi được xử lý | Header trên Fault nếu pipeline hỗ trợ và policy yêu cầu |
| Lỗi trước dispatcher | HTTP/TLS/XML parse fail | Không kỳ vọng interceptor trả SOAP Header |
| `mustUnderstand` | Header nhắm đích bắt buộc nhưng node không hiểu | Fault đúng SOAP processing model |
| WS-Security sai | Signature/token/timestamp sai | Không chạy nghiệp vụ; security Fault/policy thích hợp |
| Client interoperability | Client Java/.NET/ESB từ WSDL | Hiểu cùng QName/Body/Header/binding |

### 15.2. `MockWebServiceClient` cho endpoint server

`MockWebServiceClient` trong Spring-WS có thể gửi SOAP request với Header, chẳng hạn bằng API tạo SOAP Envelope từ nguồn XML mà phiên bản thư viện hỗ trợ, hoặc bằng custom request creator. Kiểm tra:

1. Interceptor đã đăng ký trong test `ApplicationContext`.
2. Header `CorrelationId` có đúng QName và được đọc vào `MessageContext`.
3. Request Body dispatch đúng `@PayloadRoot`.
4. SOAP response/Header hoặc SOAP Fault thực tế có thông tin mong đợi.
5. Hai request riêng có correlation ID riêng và không chia sẻ context state.

Nếu test chỉ dùng helper `withPayload(...)`, cần lưu ý nó đang tạo **payload Body**, không nhất thiết tạo một request có custom SOAP Header; hãy sử dụng helper/request creator phù hợp để kiểm thử Header thực sự.

### 15.3. `MockWebServiceServer` cho SOAP client

Với `WebServiceTemplate`, `MockWebServiceServer` có thể kiểm tra client tạo request SOAP có header block đúng QName/nội dung, rồi đưa response hoặc Fault để client xử lý. Đây là test **phía client**, không thay thế kiểm thử endpoint server.

Kiểm thử tích hợp thật vẫn cần khi triển khai TLS/mTLS, reverse proxy, WS-Security, WSDL import, SOAP 1.1/1.2 và client từ công nghệ khác.

### 15.4. Không so sánh XML chỉ theo chuỗi byte

Header blocks sau có cùng QName:

~~~xml
<h:CorrelationId xmlns:h="urn:example:headers:v1">req-8f21</h:CorrelationId>
<trace:CorrelationId xmlns:trace="urn:example:headers:v1">req-8f21</trace:CorrelationId>
~~~

Vì XML prefix có thể khác, hãy dùng parser **namespace-aware**, XPath với namespace context, DOM/JAXB hoặc assertion trên QName và text content. Khi kiểm thử WS-Security signature, sử dụng canonicalization và verification thực tế, không thay bằng phép so sánh string XML.

## 16. Chẩn đoán lỗi thường gặp với SoapHeader

| Triệu chứng | Nguyên nhân có thể | Kiểm tra đầu tiên |
| --- | --- | --- |
| `getSoapHeader()` có Header nhưng không đọc ra ID | Dùng sai QName/local name/namespace URI | Log QName từng Header block đã lọc |
| Đổi prefix làm code lỗi | Regex hoặc so `nodeName` theo prefix | So `QName` hoặc `namespaceURI/localName` |
| Client không nhận Header dù `setProperty` thành công | Nhầm property nội bộ với Header message | Kiểm tra `response.getSoapHeader().addHeaderElement` |
| Header xuất hiện hai lần | Nhiều interceptor/endpoint cùng thêm block | Xác định một owner; kiểm tra trùng trước add |
| Header chỉ có trên response thành công, không có trên Fault | Không xử lý `handleFault` hoặc Fault được tạo ở tầng khác | Kiểm tra pipeline/exception resolver |
| `getResponse()` làm response “xuất hiện” sớm | Dùng getter lazy để kiểm tra hiện diện | Dùng `hasResponse()` trước |
| SOAP client báo MustUnderstand | Đặt cờ true nhưng receiver không hiểu Header hoặc role không phù hợp | Phân tích Header QName, role/actor, SOAP version |
| Header SOAP 1.1 gửi vào SOAP 1.2 bị lỗi | Sai Envelope namespace, actor/role/attribute | Kiểm tra WSDL binding và SOAP version |
| Header phức tạp đọc sai | Dùng `getText()` cho XML nhiều phần tử | Đọc `Source` bằng JAXB/DOM namespace-aware |
| Server đánh dấu authenticated chỉ vì có `Security` | Bỏ qua signature/token verification | Dùng security interceptor/policy đúng |
| JAXB payload đúng nhưng Header vẫn sai | Schema validation chỉ kiểm Body | Có validation riêng cho Header custom |
| SOAP response bị chữ ký sai sau thêm Header | Header được sửa sau bước ký | Xem thứ tự ký/marshal/interceptors |

### Quy trình tìm lỗi

~~~mermaid
flowchart TD
    A["SOAP request qua transport"] --> B{"Parse được Envelope?"}
    B -->|Không| C["Kiểm tra XML, SOAP version, parser"]
    B -->|Có| D{"Đúng SOAP Header QName?"}
    D -->|Không| E["So namespace URI + local name"]
    D -->|Có| F{"Header thuộc node/role hiện tại?"}
    F -->|Không| G["Xem actor/role, mustUnderstand"]
    F -->|Có| H{"Header hợp đồng/đã được verify?"}
    H -->|Không| I["Validation hoặc WS-Security policy"]
    H -->|Có| J["MessageContext / endpoint xử lý"]
    J --> K{"Header response được tạo?"}
    K -->|Không| L["Xem response vs Fault, interceptor registration"]
    K -->|Có| M["Test client thực, WSDL/binding/interoperability"]
~~~

## 17. Bài thực hành tự đánh giá

### Bài 1 — Tạo Header đúng QName

Viết `WebServiceMessageCallback` thêm `CorrelationId` vào request SOAP; dùng `new QName("urn:example:headers:v1", "CorrelationId")`. Kiểm tra XML tạo ra và giải thích vì sao prefix có thể khác `hdr` trong ví dụ nhưng message vẫn hợp lệ.

### Bài 2 — Đọc Header trong interceptor

Viết `EndpointInterceptor` đọc tất cả Header blocks, chỉ nhận `CorrelationId` đúng QName, phát hiện duplicate và validate độ dài 1–64 ký tự. Nếu thiếu Header, tạo UUID; nếu có Header sai, ánh xạ lỗi thành SOAP Fault theo chính sách.

### Bài 3 — Phân biệt nơi chứa correlation ID

So sánh `MessageContext.setProperty(...)`, `SoapHeader.addHeaderElement(...)` và HTTP header `X-Correlation-ID`. Trong mỗi trường hợp, dữ liệu sống bao lâu và client có nhìn thấy không?

### Bài 4 — Header phức tạp

Thiết kế XSD cho `RoutingInfo` có `TenantCode` và `Channel`. Giải thích vì sao `SoapHeaderElement.getText()` không đủ để ánh xạ an toàn, rồi chọn JAXB/XSD binding hoặc parser namespace-aware để đọc.

### Bài 5 — SOAP processing model

Tạo hai SOAP messages: SOAP 1.1 dùng `actor`, SOAP 1.2 dùng `role`/`relay`; mỗi message có header `mustUnderstand`. Xác định SOAP node nào chịu trách nhiệm và khi nào phải trả MustUnderstand Fault.

### Bài 6 — SOAP Header và WS-Security

Đối tác gửi `wsse:Security` có UsernameToken nhưng chữ ký hoặc timestamp không hợp lệ. Chỉ thấy phần tử XML đó có cho phép application coi caller là authenticated không? Mô tả kiểm soát cần thiết và vị trí interceptor.

### Bài 7 — Kiểm thử Fault và interoperability

Viết test SOAP request thành công và test SOAP Fault, kiểm tra correlation header trên response. Sau đó sinh client từ WSDL có `soap:header` và thử với ít nhất một client công nghệ khác để xác minh cùng cách hiểu về QName, optional/required và mustUnderstand.

## 18. Checklist thiết kế và triển khai

| Kiểm tra | Điều kiện chấp nhận |
| --- | --- |
| **QName** | Header block có namespace URI/local name đúng, không dựa vào prefix |
| **Contract** | Header bắt buộc hoặc có cấu trúc phức tạp được mô tả rõ bằng XSD/WSDL/policy khi cần |
| **Nguồn dữ liệu** | Phân biệt SOAP Header với Body, HTTP Header, MessageContext property |
| **Serialization** | Dùng `SoapHeader.addHeaderElement`/JAXB/XML API; không ghép string raw |
| **Presence** | Xử lý thiếu, rỗng, nil và trùng Header theo hợp đồng |
| **SOAP version** | `actor` (1.1), `role`/`relay` (1.2) và `mustUnderstand` đúng version |
| **Server pipeline** | Interceptor/endpoint được đăng ký, nhận đúng request và sửa đúng response |
| **Client pipeline** | WebServiceTemplate callback và client interceptor xử lý request/response/Fault |
| **Security** | Xác minh token/chữ ký/chứng chỉ theo WS-Security; bảo vệ XML parser; không log bí mật |
| **Fault** | Phân biệt business validation, MustUnderstand, security và transport errors |
| **Interoperability** | Test WSDL/XSD public, SOAP 1.1/1.2, QName và các client khác nhau |

**Kết luận:** `SoapHeader` là vùng chứa những header blocks trong thông điệp SOAP; `SoapHeaderElement` là **một phần tử Header có QName, nội dung và các thuộc tính SOAP**. Trong Spring-WS, có thể lấy chúng từ `SoapMessage` thông qua `MessageContext`, đọc trong interceptor hoặc endpoint với `@SoapHeader`, và tạo Header ở response hoặc SOAP client bằng `addHeaderElement(...)`. Muốn hệ thống **SPRING_WEB_SERVICES** tương thích và an toàn, phải phân biệt Header với Body/HTTP/context property, xử lý `mustUnderstand` và actor/role đúng SOAP version, quản lý Header trùng hoặc thiếu, mô tả contract XSD/WSDL và áp dụng WS-Security/validation phù hợp. Khi làm đúng các ranh giới này, SOAP Header trở thành công cụ điều phối rõ ràng thay vì nguồn lỗi tích hợp khó chẩn đoán.
