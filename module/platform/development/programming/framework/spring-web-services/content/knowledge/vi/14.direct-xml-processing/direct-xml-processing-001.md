# Source, Result và các dạng dữ liệu XML được Spring-WS sử dụng

Trong **Spring Web Services (Spring-WS)**, không phải SOAP endpoint hoặc SOAP client nào cũng cần chuyển XML sang lớp Java được sinh bằng JAXB. Khi xử lý dữ liệu XML trực tiếp, hai giao diện quan trọng của Java là `javax.xml.transform.Source` và `javax.xml.transform.Result`. Chúng mô tả **nơi lấy XML làm đầu vào** và **nơi ghi dữ liệu XML sau xử lý**, cho phép kết nối nhiều biểu diễn như DOM, SAX, Stream, StAX và JAXB.

Đây là chủ đề của chương **Xử lý XML trực tiếp** trong module `SPRING_WEB_SERVICES`. Bài học liên hệ với mô hình **contract-first** (XSD/WSDL), chữ ký `@Endpoint`, `WebServiceTemplate`, xử lý SOAP Fault, interceptor, XML security/WS-Security và kiểm thử tương thích. Các API Java SE có tên `javax.xml.transform.*` vẫn giữ namespace `javax` ngay cả trong ứng dụng sử dụng Jakarta JAXB mới. Ví dụ minh họa chủ yếu dùng SOAP 1.1 và giả định hệ thống đã cấu hình Spring-WS tương thích.

## 1. Source và Result thực chất là gì?

`Source` là interface trong **Java API for XML Processing (JAXP)**, biểu diễn một nguồn dữ liệu XML. `Result` biểu diễn đích để một bộ xử lý XML ghi kết quả. Chúng không tương đương với `String` hay `byte[]`, và tự chúng **không xác định URL SOAP, operation WSDL hoặc chính sách bảo mật**.

Một cách hiểu trực quan:

~~~text
      XML bytes / DOM tree / SAX events / StAX events / JAXB object
                            |
                         [Source]
                            |
           Transformer / Validator / Spring-WS adapter
                            |
                         [Result]
                            |
        OutputStream / DOM tree / SAX handler / StAX writer
~~~

Hai giao diện này giúp tách thuật toán xử lý XML khỏi định dạng lưu trữ hoặc nguồn phát sinh dữ liệu.

| Khía cạnh | `Source` | `Result` |
| --- | --- | --- |
| Vai trò | **Đầu vào** XML của một phép biến đổi/xử lý. | **Đầu ra** XML sau một phép biến đổi/xử lý. |
| API Java SE | `javax.xml.transform.Source` | `javax.xml.transform.Result` |
| Ví dụ | `DOMSource`, `SAXSource`, `StreamSource`, `StAXSource`. | `DOMResult`, `SAXResult`, `StreamResult`, `StAXResult`. |
| Trong Spring-WS | Có thể lấy payload từ `WebServiceMessage#getPayloadSource()`. | Có thể nhận đích payload từ `WebServiceMessage#getPayloadResult()`. |
| Khi xử lý | Bộ xử lý **đọc** từ nguồn, có thể tiêu thụ stream. | Bộ xử lý **ghi** XML vào đích, thường chỉ hữu ích sau khi hoàn tất. |
| Metadata | Có thể có `systemId` để giải tham chiếu URI tương đối. | Có thể có `systemId` mô tả đích. |
| Lưu ý | Không chắc đọc lại được nếu dựa trên stream/event reader. | Không chắc nhận được toàn bộ document nếu writer chưa flush/close đúng. |

Cả hai là **giao diện trừu tượng**: cùng một phương thức nhận `Source` có thể được truyền một cây DOM đã tồn tại hoặc một nguồn stream đọc từ socket/file. Khác biệt về bộ nhớ, bảo mật và khả năng đọc lại nằm ở **lớp triển khai và vòng đời tài nguyên**.

### 1.1. Hai loại giao diện có đối xứng tuyệt đối không?

Không. Ví dụ `SAXSource` thường cung cấp SAX parser hoặc `InputSource` để tạo sự kiện XML; `SAXResult` lại nhận một `ContentHandler` để tiêu thụ sự kiện. `StreamSource` đọc từ stream/reader, còn `StreamResult` là nơi ghi ra stream/writer. Mặc dù tên tương ứng, không phải mọi `Source` đều có thể dùng làm `Result` hay ngược lại.

Một bộ `Transformer` của JAXP có thể chuyển nhiều dạng `Source` vào nhiều dạng `Result` mà không cần tự viết code chuyển đổi từng cặp.

### 1.2. Source/Result không phải cả SOAP Envelope

Trong Spring-WS, hai phương thức payload:

~~~java
Source source = requestMessage.getPayloadSource();
Result result = responseMessage.getPayloadResult();
~~~

thường đề cập tới **phần payload nghiệp vụ trong `soap:Body`**, không phải toàn bộ `soap:Envelope` có Header, Body và các thuộc tính SOAP. Không nên lấy một chuỗi XML đã bao gồm toàn bộ `soap:Envelope` rồi ghi nguyên vào `getPayloadResult()`, vì kết quả dễ thành **Envelope lồng trong Body**.

SOAP Envelope được message factory và runtime Spring-WS quản lý. Payload XML phải mang QName đúng XSD/WSDL, còn SOAP Header, WS-Security, SOAPAction và attachment có cơ chế riêng.

## 2. Mỗi loại Source biểu diễn dữ liệu XML theo cách nào?

### 2.1. `StreamSource` — XML từ InputStream, Reader hoặc systemId

`javax.xml.transform.stream.StreamSource` là kiểu thông dụng nhất khi đầu vào là file, stream hoặc chuỗi ký tự:

~~~java
import java.io.StringReader;
import javax.xml.transform.Source;
import javax.xml.transform.stream.StreamSource;

String xml = """
    <ord:CreateOrderRequest xmlns:ord="urn:example:orders:v1">
      <ord:clientOrderId>WEB-20261127-0042</ord:clientOrderId>
    </ord:CreateOrderRequest>
    """;

Source source = new StreamSource(new StringReader(xml));
~~~

Đoạn trên dùng Java text block (Java 15+); trên Java cũ cần nối chuỗi thông thường. `StreamSource` không parse XML ngay khi được tạo; bộ xử lý sau đó mới đọc từ `Reader` hoặc `InputStream`. `InputStream` mang byte để parser xử lý mã hóa XML; `Reader` đã giải mã thành ký tự, nên XML declaration encoding không còn quyết định cách Java `Reader` giải mã dữ liệu.

**Rủi ro vòng đời:** stream/reader có thể bị tiêu thụ một lần. Nếu tạo một `StreamSource` từ file rồi dùng nó cho validation và tiếp tục cố marshal cùng object lần thứ hai, dữ liệu có thể đã ở cuối stream. Muốn thực hiện hai lần đọc, phải mở lại nguồn đáng tin cậy hoặc thiết kế một lần xử lý/đệm có chủ đích.

### 2.2. `DOMSource` — XML đã là cây DOM

`javax.xml.transform.dom.DOMSource` bọc một `org.w3c.dom.Node`, thường là `Document` hoặc `Element`.

~~~java
import javax.xml.transform.Source;
import javax.xml.transform.dom.DOMSource;
import org.w3c.dom.Document;

Document document = obtainTrustedDocument();
Source source = new DOMSource(document);
~~~

`obtainTrustedDocument()` là hàm giả định phải được triển khai ở ứng dụng. Với DOM, có thể duyệt node và đọc lại nhiều lần, phù hợp khi cần chỉnh sửa cấu trúc, truy vấn XPath hoặc xác nhận chữ ký XML qua stack đòi DOM. Đổi lại, toàn bộ cây đã phải nằm trong bộ nhớ; lượng object có thể lớn hơn kích thước byte XML gốc.

**Không coi DOM là tự an toàn:** an toàn phụ thuộc `DocumentBuilderFactory`/parser đã dùng để tạo `Document`. Một DOMSource từ Document được parse với external entity không an toàn vẫn có thể chứa dữ liệu ngoại lai.

### 2.3. `SAXSource` — XML qua sự kiện SAX

`javax.xml.transform.sax.SAXSource` thường kết hợp `org.xml.sax.XMLReader` và `InputSource`. Parser phát các sự kiện `startElement`, `characters`, `endElement`... thay vì bắt buộc tạo cây DOM.

~~~java
import java.io.StringReader;
import javax.xml.transform.Source;
import javax.xml.transform.sax.SAXSource;
import org.xml.sax.InputSource;
import org.xml.sax.XMLReader;

// reader phải được cấu hình bảo mật phù hợp.
XMLReader reader = obtainSecureXmlReader();
InputSource input = new InputSource(new StringReader(xml));
Source source = new SAXSource(reader, input);
~~~

Đây là ví dụ về hình thức API: `obtainSecureXmlReader()` đại diện cho code cấu hình parser đã kiểm tra version/provider. SAX phù hợp luồng sự kiện tuần tự, có thể hạn chế chi phí tạo object khi không cần truy cập ngẫu nhiên. Nhưng nó không tự tạo Java DTO; nếu một interceptor hoặc handler cần đọc lại payload sau SAX parse, phải có chiến lược replay/caching riêng.

### 2.4. `StAXSource` — XML pull/event stream

`javax.xml.transform.stax.StAXSource` nhận một `XMLStreamReader` hoặc `XMLEventReader`. StAX cho phép code yêu cầu sự kiện tiếp theo khi cần (pull parsing).

~~~java
import java.io.StringReader;
import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLStreamReader;
import javax.xml.transform.Source;
import javax.xml.transform.stax.StAXSource;

XMLInputFactory inputFactory = XMLInputFactory.newFactory();
inputFactory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
inputFactory.setProperty(
    XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false
);

XMLStreamReader reader =
    inputFactory.createXMLStreamReader(new StringReader(xml));

try {
    Source source = new StAXSource(reader);
    // Truyền source cho một consumer duy nhất khi cần.
    // consumer.transformOrProcess(source);
} finally {
    reader.close();
}
~~~

Một số provider có thể phản hồi khác hoặc từ chối property; ứng dụng phải kiểm tra cấu hình bảo mật của parser cụ thể, không chỉ giả định hai property trên đã bao trùm mọi đường đọc XML. Cũng cần cân nhắc `XMLResolver`, giới hạn kích thước và entity expansion. Đoạn code tạo ra một Source nhưng chưa parse; thực tế phải có bộ xử lý đọc Source **trước khi `reader.close()`**.

Spring-WS có thể sử dụng thông tin kiểu stream/AXIOM trong những cấu hình phù hợp, nhưng **dùng `StAXSource` trong method không đồng nghĩa toàn bộ SOAP request/response là zero-buffer**. SOAP message factory, interceptor, JAXB và HTTP sender có thể vẫn giữ nội dung trong bộ nhớ.

### 2.5. `JAXBSource` — dùng object JAXB như một nguồn XML

`JAXBSource` không nằm trong Java SE JAXP thuần mà thuộc JAXB utility package:

- Jakarta JAXB: `jakarta.xml.bind.util.JAXBSource`.
- JAXB thế hệ cũ: `javax.xml.bind.util.JAXBSource`.

Một nguồn XML có thể được tạo từ object JAXB:

~~~java
import jakarta.xml.bind.JAXBContext;
import jakarta.xml.bind.util.JAXBSource;

// OrderRequest được JAXB biết đến (ví dụ @XmlRootElement).
JAXBContext context = JAXBContext.newInstance(OrderRequest.class);
JAXBSource source = new JAXBSource(context, request);
~~~

Ví dụ giả định `OrderRequest` và `request` là object hợp lệ được ứng dụng cung cấp. `JAXBSource` nối Java object với pipeline dựa trên `Source`, không tự gửi SOAP. Nếu class không có root metadata, phải dùng `JAXBElement` hoặc cấu hình JAXB phù hợp.

## 3. Những dạng Result và cách chọn đúng đích XML

`Result` là đích nhận XML được transformer/adapter ghi ra. Chọn loại đích ảnh hưởng đến memory, encoding và quyền sở hữu stream.

| Loại Result | Đích | Khi nào dùng | Điều cần lưu ý |
| --- | --- | --- | --- |
| `StreamResult` | `OutputStream`, `Writer` hoặc output URI | Ghi XML ra HTTP/file/buffer. | Quản lý encoding/flush/đóng stream; tránh xuất vào path ngoài ý muốn. |
| `DOMResult` | `Document` hoặc `Node` | Cần DOM để kiểm tra/sửa XML trong bộ nhớ. | Tốn heap; node/ownerDocument cần xử lý đúng. |
| `SAXResult` | `ContentHandler` và optional lexical handler | Chuyển XML thành chuỗi sự kiện cho bộ xử lý khác. | Handler phải xử lý thứ tự sự kiện và state đúng. |
| `StAXResult` | `XMLStreamWriter` hoặc `XMLEventWriter` | Ghi XML theo sự kiện vào serializer. | Writer phải được flush/đóng theo ownership; không chia sẻ tùy tiện. |
| `JAXBResult` | JAXB unmarshaller dưới dạng Result | Nhận dữ liệu XML và tạo object JAXB. | Context và model JAXB phải tương thích; không có network I/O. |
| `StringResult` (Spring XML) | Buffer ký tự nội bộ | Test XML, demo hoặc payload nhỏ. | Đã lưu toàn bộ output dưới dạng String; không dùng cho streaming lớn. |

### 3.1. `StreamResult`: đích byte/character

~~~java
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import javax.xml.transform.Result;
import javax.xml.transform.stream.StreamResult;

ByteArrayOutputStream buffer = new ByteArrayOutputStream();
Result result = new StreamResult(buffer);

// Transformer sẽ ghi vào result.
// Sau đó đọc byte theo charset XML đã thống nhất.
String xmlOutput = buffer.toString(StandardCharsets.UTF_8);
~~~

Ví dụ dùng overload `ByteArrayOutputStream.toString(Charset)` có trên JDK mới. Với Java cũ có thể dùng `new String(buffer.toByteArray(), StandardCharsets.UTF_8)`. Khi transformer tạo XML declaration, thuộc tính encoding và encoding thực tế của output stream cần thống nhất; ghi vào `Writer` đã giải mã/encode theo charset của Writer có khác biệt so với ghi trực tiếp vào `OutputStream`.

### 3.2. `DOMResult`: đích cây XML

~~~java
import javax.xml.transform.dom.DOMResult;
import org.w3c.dom.Node;

DOMResult domResult = new DOMResult();
// transformer.transform(source, domResult);
Node resultNode = domResult.getNode();
~~~

Khi `DOMResult` được tạo rỗng, transformer thường tạo node/document kết quả khi transform diễn ra. Trước khi transform, `getNode()` có thể trả `null`; không dùng result khi chưa có bộ xử lý ghi dữ liệu. Nếu muốn chèn kết quả vào cây đã tồn tại, có thể truyền Node đích phù hợp và cần kiểm soát namespace/ownerDocument.

### 3.3. `SAXResult`, `StAXResult` và `JAXBResult`

- `SAXResult` ghi sự kiện vào `ContentHandler`: phù hợp khi muốn pipeline event-driven, thu thống kê hoặc làm SAX filter.
- `StAXResult` ghi XML qua `XMLStreamWriter`/`XMLEventWriter`: hợp với serialization tuần tự và có thể quản lý writer ở tầng ngoài.
- `JAXBResult` nhận XML rồi tạo object JAXB mà `getResult()` trả ra sau khi transform, ví dụ:

~~~java
import jakarta.xml.bind.JAXBContext;
import jakarta.xml.bind.util.JAXBResult;

JAXBContext context = JAXBContext.newInstance(OrderResponse.class);
JAXBResult jaxbResult = new JAXBResult(context);

// transformer.transform(source, jaxbResult);
// Object response = jaxbResult.getResult();
~~~

Đây không phải đường tối ưu mặc định để đọc SOAP response; nếu đã dùng Spring-WS `Jaxb2Marshaller` hoặc `WebServiceTemplate.marshalSendAndReceive(...)`, nên dùng API tương ứng thay vì chồng nhiều lần chuyển XML.

## 4. Chuyển đổi Source → Result với JAXP Transformer

Phương thức trung tâm của JAXP:

~~~java
Transformer transformer = transformerFactory.newTransformer();
transformer.transform(source, result);
~~~

Nếu không gắn XSLT stylesheet, `newTransformer()` thường tạo **identity transformer**: sao chép biểu diễn XML từ Source sang Result (có thể thay đổi XML declaration, whitespace, prefix hoặc chi tiết serialization tùy processor).

Một ví dụ độc lập dùng Java SE:

~~~java
import java.io.StringReader;
import java.io.StringWriter;
import javax.xml.XMLConstants;
import javax.xml.transform.Source;
import javax.xml.transform.Transformer;
import javax.xml.transform.TransformerFactory;
import javax.xml.transform.stream.StreamResult;
import javax.xml.transform.stream.StreamSource;

public class CopyXml {
    public static void main(String[] args) throws Exception {
        String xml =
            "<ord:CreateOrderRequest " +
            "xmlns:ord=\"urn:example:orders:v1\">" +
            "<ord:clientOrderId>WEB-20261127-0042" +
            "</ord:clientOrderId>" +
            "</ord:CreateOrderRequest>";

        Source source = new StreamSource(new StringReader(xml));
        StringWriter writer = new StringWriter();
        StreamResult result = new StreamResult(writer);

        TransformerFactory factory = TransformerFactory.newInstance();
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_STYLESHEET, "");

        Transformer transformer = factory.newTransformer();
        transformer.transform(source, result);

        System.out.println(writer);
    }
}
~~~

Chương trình dùng XML literal đã biết, không cần file hoặc kết nối SOAP. Cấu hình bảo vệ ở `TransformerFactory` giúp hạn chế external resources ở mức processor. Tuy nhiên **phải kiểm tra provider hỗ trợ các property này** và các parser được dùng trước đó cũng đã được cấu hình an toàn. Một cấu hình bảo mật transformer không thay thế hoàn toàn phòng vệ XXE ở XML parser hoặc source do thư viện khác cung cấp.

### 4.1. Nếu Result là StreamResult, ai sở hữu stream?

Trong chương trình minh họa, ứng dụng sở hữu `StringWriter`; nếu thay bằng `FileOutputStream`, chính ứng dụng nên đóng stream theo `try-with-resources`. Transformer thường **không phải nơi quyết định vòng đời của HTTP response stream hoặc stream do caller cung cấp**.

Khi Spring-WS chuyển XML payload vào `getPayloadResult()`, **framework sở hữu SOAP response message/transport**. Không được tự đóng output stream HTTP của servlet khi chỉ muốn kết thúc phần payload. Việc đóng quá sớm có thể khiến SOAP Envelope chưa hoàn chỉnh, attachment chưa ghi hoặc response bị commit không đúng.

### 4.2. Identity transform không có nghĩa tương đương byte

Ví dụ hai payload XML sau có thể biểu diễn cùng QName và nội dung:

~~~xml
<ord:CreateOrderRequest xmlns:ord="urn:example:orders:v1">
  <ord:clientOrderId>WEB-20261127-0042</ord:clientOrderId>
</ord:CreateOrderRequest>
~~~

~~~xml
<x:CreateOrderRequest xmlns:x="urn:example:orders:v1"><x:clientOrderId>WEB-20261127-0042</x:clientOrderId></x:CreateOrderRequest>
~~~

Prefix, khoảng trắng trình bày và cách viết tag khác nhau, nhưng QName/root và cấu trúc dữ liệu có thể tương đương theo contract. Vì thế **không nên so sánh payload bằng raw String equality** khi kiểm thử SOAP nếu hợp đồng cho phép serializer thay đổi prefix hoặc whitespace không có nghĩa. Dùng assertion dựa trên namespace-aware XML, XPath, schema hoặc bộ so sánh XML phù hợp.

Đồng thời, **không bao giờ áp dụng identity transform lên XML đã ký rồi giả định chữ ký WS-Security vẫn hợp lệ**. Các thay đổi serialization/canonicalization có thể tác động kiểm tra chữ ký; hãy để stack security chuẩn xử lý đúng dữ liệu được ký.

## 5. Spring-WS cung cấp Source và Result như thế nào?

Ở tầng message, `WebServiceMessage` có các API payload:

~~~java
import javax.xml.transform.Source;
import javax.xml.transform.Result;
import org.springframework.ws.WebServiceMessage;

WebServiceMessage requestMessage = context.getRequest();
WebServiceMessage responseMessage = context.getResponse();

Source requestPayload = requestMessage.getPayloadSource();
Result responsePayload = responseMessage.getPayloadResult();
~~~

Ở đây `context` đại diện `org.springframework.ws.context.MessageContext` do framework cấp. `getPayloadSource()` là đầu vào cho parser/transformer; `getPayloadResult()` là đích ghi nội dung response. Chúng là **XML payload**, không tự bao gồm HTTP headers hoặc `soap:Header`.

Nếu message là `SoapMessage`, các API SOAP riêng cho phép truy cập Envelope/Header và SOAP Fault. Không nên dùng `getPayloadSource()` để đọc WS-Security Header; điều đó thuộc phần SOAP Header và cơ chế interceptor bảo mật.

### 5.1. Vòng đời quan trọng khi làm việc trực tiếp với XML

~~~mermaid
sequenceDiagram
    participant Client as SOAP client
    participant Factory as WebServiceMessageFactory
    participant Map as EndpointMapping
    participant Xml as XML handler
    participant Out as Response writer
    Client->>Factory: HTTP SOAP request
    Factory->>Map: WebServiceMessage
    Map->>Xml: Source của payload
    Note over Xml: Parser / Transformer / business logic
    Xml-->>Out: Result hoặc Source của response payload
    Out-->>Client: SOAP Envelope + Body
~~~

Tùy message factory, `Source` có thể dựa trên DOM đã dựng sẵn hoặc là **stream chỉ tiêu thụ được một lần**. Không lưu đối tượng `Source` trong field của singleton endpoint hoặc trả về để xử lý sau khi HTTP request đã hoàn tất: nguồn có thể phụ thuộc input stream đã đóng hoặc tài nguyên đã được giải phóng.

Trong kiến trúc request-response thông thường, đọc payload **ngay trong phạm vi xử lý message**, ghi result trước khi framework hoàn thành response, và không chia sẻ cùng một `Result` cho các request đồng thời.

### 5.2. Ý nghĩa của `Source` trong chữ ký endpoint

Spring-WS hỗ trợ nhiều kiểu tham số cho endpoint annotation-based, trong đó có dạng XML Source tùy phiên bản và adapter:

~~~java
@PayloadRoot(namespace = NS, localPart = "CreateOrderRequest")
@ResponsePayload
public Source createOrder(@RequestPayload Source requestPayload) {
    // Biến đổi Source, tạo Source đại diện
    // cho <CreateOrderResponse> theo đúng XSD.
    return responsePayload;
}
~~~

Ví dụ là chữ ký khái niệm: `NS` và `responsePayload` cần được cung cấp từ code hợp lệ. `@PayloadRoot` xác định **QName** đầu vào, `@RequestPayload` chỉ định tham số chứa XML từ SOAP Body, `@ResponsePayload` ghi return value thành XML payload phản hồi. Cả ba **không tự bảo đảm XSD hợp lệ** và không tự xử lý SOAP Fault.

Đây là phương án thay cho:

~~~java
@ResponsePayload
public CreateOrderResponse createOrder(
        @RequestPayload CreateOrderRequest request) {
    return orderService.createResponse(request);
}
~~~

Phiên bản thứ hai dùng **JAXB DTO** đã sinh từ XSD; phiên bản thứ nhất dùng **XML Source** trực tiếp. Cả hai có thể tuân theo cùng hợp đồng XSD/WSDL, chỉ khác biểu diễn nội bộ và API xử lý.

## 6. Ví dụ endpoint trực tiếp với DOMSource

Để minh họa thực tế, giả sử global elements trong XSD 1.0 là `CreateOrderRequest` và `CreateOrderResponse` thuộc `urn:example:orders:v1`. Request chứa `clientOrderId`; response chứa `orderId` và `status`. Ví dụ sau chuyển một `Source` đến cây DOM, đọc request rồi tạo response DOM **không lắp XML bằng nối chuỗi**.

~~~java
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.transform.Source;
import javax.xml.transform.TransformerFactory;
import javax.xml.transform.dom.DOMResult;
import javax.xml.transform.dom.DOMSource;

import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;

import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;

@Endpoint
public class OrdersXmlEndpoint {
    private static final String NS = "urn:example:orders:v1";

    @PayloadRoot(namespace = NS, localPart = "CreateOrderRequest")
    @ResponsePayload
    public Source createOrder(@RequestPayload Source request)
            throws Exception {

        TransformerFactory transformerFactory =
                TransformerFactory.newInstance();
        transformerFactory.setFeature(
                XMLConstants.FEATURE_SECURE_PROCESSING, true);
        transformerFactory.setAttribute(
                XMLConstants.ACCESS_EXTERNAL_DTD, "");
        transformerFactory.setAttribute(
                XMLConstants.ACCESS_EXTERNAL_STYLESHEET, "");

        DOMResult domResult = new DOMResult();
        transformerFactory.newTransformer()
                .transform(request, domResult);

        Node node = domResult.getNode();
        Document incoming = (Document) node;
        Element root = incoming.getDocumentElement();

        if (!NS.equals(root.getNamespaceURI())
                || !"CreateOrderRequest".equals(root.getLocalName())) {
            throw new IllegalArgumentException("Unexpected payload root");
        }

        NodeList ids = root.getElementsByTagNameNS(NS, "clientOrderId");
        if (ids.getLength() != 1) {
            throw new IllegalArgumentException("Invalid clientOrderId");
        }
        String clientOrderId = ids.item(0).getTextContent();

        // Ví dụ cố định; production phải gọi business service an toàn,
        // kiểm tra uniqueness và mapping lỗi theo contract.
        if (clientOrderId.isBlank()) {
            throw new IllegalArgumentException("Missing clientOrderId");
        }

        DocumentBuilderFactory builderFactory =
                DocumentBuilderFactory.newInstance();
        builderFactory.setNamespaceAware(true);
        Document document =
                builderFactory.newDocumentBuilder().newDocument();

        Element response =
                document.createElementNS(NS, "ord:CreateOrderResponse");
        document.appendChild(response);

        Element orderId = document.createElementNS(NS, "ord:orderId");
        orderId.setTextContent("ORD-000184");
        response.appendChild(orderId);

        Element status = document.createElementNS(NS, "ord:status");
        status.setTextContent("ACCEPTED");
        response.appendChild(status);

        return new DOMSource(document);
    }
}
~~~

**Phạm vi ví dụ:** đây là demo về Source → DOM → Source, không phải một dịch vụ nghiệp vụ đầy đủ. Chương trình giả định input Source có thể được identity-transform thành một `Document`, XSD validation được xử lý ở pipeline nếu cần, endpoint adapter hỗ trợ `Source`, và ví dụ chạy trên Java có `String.isBlank()`. Khi dùng kết quả thật từ DB, tạo XML với DOM API hoặc serializer chuẩn (không lắp chuỗi), kiểm soát thời gian xử lý/transaction và map exception sang SOAP Fault phù hợp.

Điểm bảo mật quan trọng: `TransformerFactory` được cấu hình hạn chế external DTD/stylesheet ở bước transform, nhưng **nó không tự bảo vệ mọi parser ở những tầng trước đó**, bao gồm parser do SOAP message factory/interceptor sử dụng. Khi `request` là SAXSource/StreamSource từ nguồn không tin cậy, kiểm tra cấu hình parser và giới hạn đầu vào toàn pipeline.

### 6.1. Tại sao không nên truy cập `NodeList` không kiểm soát?

`getElementsByTagNameNS` tìm **mọi descendant** trùng tên, không chỉ direct child. Với XSD có cấu trúc phức tạp hoặc dữ liệu không tin cậy, truy cập như vậy có thể lấy nhầm element lồng bên trong. Dùng kiểm tra schema trước, helper chỉ lấy direct child đúng QName hoặc XPath namespace-aware, và ràng buộc số lần xuất hiện theo XSD. Khi nhiều bản ghi, cân nhắc dữ liệu lớn, limits và tránh lặp qua toàn DOM không cần thiết.

### 6.2. Vì sao response dùng `setTextContent`?

`setTextContent` thêm text node đúng cách và XML serializer sẽ escape những ký tự cần thiết như `&` hoặc `<`. Nếu nối raw XML bằng `"<ord:orderId>" + value + "</ord:orderId>"`, một giá trị chứa `&` có thể làm XML không well-formed và tăng nguy cơ XML injection. Tạo XML qua DOM/StAX/JAXB đúng API giúp tách **dữ liệu text** khỏi **markup**.

## 7. Spring-WS client: dùng Source và Result thay cho JAXB DTO

Ở phía client, `WebServiceTemplate` có cách gửi payload XML trực tiếp thay vì bắt buộc dùng `marshalSendAndReceive`. Một API thường dùng là `sendSourceAndReceiveToResult`: đầu vào `Source`, đích response `Result`.

### 7.1. `StringSource` và `StringResult` là tiện ích của Spring XML

Spring XML cung cấp hai tiện ích:

- `org.springframework.xml.transform.StringSource`: một `Source` khởi tạo từ `String` chứa XML.
- `org.springframework.xml.transform.StringResult`: một `Result` gom XML output thành chuỗi khi hoàn tất.

Chúng **không phải `javax.xml.transform.Source` và `Result` mới**; đây là các lớp cụ thể triển khai giao diện JAXP. Rất tiện cho kiểm thử và bản tin nhỏ, nhưng không phải cách lựa chọn cho tải rất lớn vì payload/response nằm trong heap dưới dạng chuỗi.

Ví dụ client ở mức luồng xử lý:

~~~java
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.xml.transform.StringSource;
import org.springframework.xml.transform.StringResult;

WebServiceTemplate template = new WebServiceTemplate();
template.setDefaultUri("https://api.example.test/ws");

String requestXml =
    "<ord:CreateOrderRequest " +
    "xmlns:ord=\"urn:example:orders:v1\">" +
    "<ord:clientOrderId>WEB-20261127-0042</ord:clientOrderId>" +
    "</ord:CreateOrderRequest>";

StringSource requestSource = new StringSource(requestXml);
StringResult responseResult = new StringResult();

boolean hasResponse =
    template.sendSourceAndReceiveToResult(requestSource, responseResult);

if (hasResponse) {
    // Chỉ minh họa; không log XML có dữ liệu nhạy cảm.
    String xmlResponse = responseResult.toString();
}
~~~

**Giả định:** có Spring-WS client dependencies, endpoint test thật tương ứng, SOAP message factory/transport được cấu hình, request hợp lệ theo WSDL/XSD, có thể cần SOAPAction hoặc security headers riêng. URL `api.example.test` chỉ là địa chỉ minh họa, không phải dịch vụ đang chạy.

Giá trị Boolean phản ánh việc có response payload/response theo ngữ nghĩa API và tình trạng protocol tương ứng; không dùng nó làm bằng chứng rằng nghiệp vụ thành công. SOAP Fault thường được xử lý qua fault resolver/exception, còn HTTP transport failure có exception riêng.

### 7.2. SOAPAction và callback được xử lý ngoài XML payload

Một số dịch vụ SOAP 1.1 đòi SOAPAction khớp WSDL binding. Đặt SOAPAction trong callback (với overload hỗ trợ của Spring-WS version đang sử dụng), không nhúng vào payload:

~~~java
import org.springframework.ws.soap.client.core.SoapActionCallback;

boolean hasResponse = template.sendSourceAndReceiveToResult(
    "https://api.example.test/ws",
    new StringSource(requestXml),
    new SoapActionCallback("urn:example:orders:v1/CreateOrder"),
    responseResult
);
~~~

`SoapActionCallback` áp dụng trên SOAP message/protocol; `StringSource` chỉ chứa payload `CreateOrderRequest`. Giá trị SOAPAction ở đây là ví dụ, không phải giá trị framework tự suy từ `@PayloadRoot`. Nếu WSDL thực tế định nghĩa action khác hoặc rỗng, phải dùng hợp đồng thực tế.

### 7.3. `sendSourceAndReceiveToResult` so với `marshalSendAndReceive`

| API | Đầu vào Java | Đầu ra Java | Khi nào chọn |
| --- | --- | --- | --- |
| `sendSourceAndReceiveToResult` | `Source`: XML payload có thể serialize. | `Result`: nhận XML payload phản hồi. | Tích hợp XML trực tiếp, cần giữ control trên DOM/StAX/XML. |
| `marshalSendAndReceive` | Object được marshaller hỗ trợ, thường JAXB DTO. | Object được unmarshaller tạo. | Contract-first có XSD và classes sinh ổn định; code nghiệp vụ dễ dùng. |
| `sendAndReceive` với message callback/extractor | Tự thao tác request/response message tùy API. | Kết quả do extractor trả. | Cần kiểm soát SOAP Header, attachment, biến thể message đặc biệt. |

Một ứng dụng có thể dùng **cả hai chiến lược** cho các operation khác nhau, nhưng nên thống nhất cấu hình endpoint URL, SOAP version, headers/security và cách map lỗi. Khi đã có JAXB model từ XSD, sử dụng XML trực tiếp chỉ vì “đơn giản hơn” có thể đánh mất type safety và gây nhiều code parsing thủ công.

## 8. Source, Result và XML schema validation

Đưa XML qua `Transformer` không tự xác minh các ràng buộc `xs:sequence`, `xs:enumeration`, `xs:pattern`, `minOccurs` hoặc miền giá trị. Để validate một payload, có thể dùng `javax.xml.validation.SchemaFactory` và `Validator` (JAXP).

### 8.1. Validate payload XML độc lập

Ví dụ giả định có file XSD tin cậy `orders.xsd` tại runtime path của ứng dụng:

~~~java
import java.io.File;
import java.io.StringReader;
import javax.xml.XMLConstants;
import javax.xml.transform.Source;
import javax.xml.transform.stream.StreamSource;
import javax.xml.validation.Schema;
import javax.xml.validation.SchemaFactory;
import javax.xml.validation.Validator;

SchemaFactory schemaFactory = SchemaFactory.newInstance(
    XMLConstants.W3C_XML_SCHEMA_NS_URI
);

schemaFactory.setFeature(
    XMLConstants.FEATURE_SECURE_PROCESSING, true
);
schemaFactory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
schemaFactory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

Schema schema = schemaFactory.newSchema(new File("orders.xsd"));
Validator validator = schema.newValidator();

Source payload = new StreamSource(new StringReader(requestXml));
validator.validate(payload);
~~~

Code giả định `requestXml` chứa **payload XML độc lập** và đáp ứng root XSD, không phải cả SOAP Envelope. Ví dụ schema path chỉ mang tính minh họa: trong ứng dụng đóng gói JAR, cần tải resource qua classpath/stream hoặc resolver đáng tin cậy, không giả định file nằm ở working directory.

**Điểm cần chú ý:** sau khi `Validator#validate(payload)` dùng một `StreamSource`, stream có thể đã bị tiêu thụ. Không nên tiếp tục đưa cùng `Source` đó cho handler/adapter; hãy cấu hình validation trong pipeline với chiến lược caching phù hợp, hoặc sử dụng một nguồn mới có thể đọc lại khi đã chủ động quản lý dữ liệu.

### 8.2. Validation trong Spring-WS không tự bật vì method nhận Source

Ở server, Spring-WS có thể dùng `PayloadValidatingInterceptor` để kiểm tra request hoặc response với XSD:

~~~java
import org.springframework.core.io.ClassPathResource;
import org.springframework.ws.soap.server.endpoint.interceptor.PayloadValidatingInterceptor;

PayloadValidatingInterceptor validator =
    new PayloadValidatingInterceptor();

validator.setXsdSchema(
    new ClassPathResource("xsd/orders.xsd")
);
validator.setValidateRequest(true);
validator.setValidateResponse(true);
~~~

Đoạn trên mới tạo object interceptor; **cần đăng ký nó** trong chuỗi interceptors của `MessageDispatcherServlet`/Spring-WS theo configuration đang sử dụng. `setValidateResponse(true)` nên được kiểm tra trong test, nhất là khi server có SOAP Fault hoặc response đặc biệt.

Nếu message factory sử dụng Apache Axiom với `payloadCaching=false` trong một phiên bản có hỗ trợ, `PayloadValidatingInterceptor` có thể tiêu thụ SOAP Body trước handler `@RequestPayload Source`. **Không bật non-caching đồng thời một cách vô điều kiện**: đọc Javadoc đúng version và test routing, validation, security cùng nhau.

### 8.3. Nguồn XML có khác cách biểu diễn nhưng phải cùng contract

Một test tốt kiểm tra cùng payload từ `StringSource`, `DOMSource` và nguồn SAX/StAX phù hợp sẽ cho kết quả cùng về nghĩa nghiệp vụ (nếu tất cả nguồn biểu diễn cùng XML và có cấu hình namespace đúng). Kết quả byte có thể khác vì serializer, nhưng schema, QName và giá trị phải nhất quán.

Khi so sánh DOM hoặc XPath, luôn cấu hình **namespace-aware**. XPath `/CreateOrderRequest/clientOrderId` thường không tìm thấy root trong namespace nghiệp vụ nếu không bind prefix/namespace context; đó không phải lỗi Source tự thay đổi XML.

## 9. Lựa chọn kiểu Source/Result theo bộ nhớ và cách truy cập

| Tình huống | Source/Result phù hợp để bắt đầu | Vì sao | Điều kiện |
| --- | --- | --- | --- |
| Test SOAP payload vài dòng | `StringSource`, `StringResult` | Dễ tạo fixture và assertion. | Không dùng production logs để in raw dữ liệu nhạy cảm. |
| XML nhỏ, cần XPath/sửa node | `DOMSource`, `DOMResult` | Truy cập ngẫu nhiên node. | Có đủ heap, parser đã bảo vệ. |
| File XML lớn, chuyển đổi tuần tự | `StreamSource`/`StreamResult` | Có thể tránh giữ cả file dạng String. | Transformer, schema/security và transport không buffer toàn bộ. |
| Event-driven parsing | `SAXSource`/`SAXResult` | Xử lý qua SAX callbacks. | Parser/handler đúng state và namespace. |
| Streaming pull/ghi event | `StAXSource`/`StAXResult` | Kiểm soát luồng đọc/ghi tuần tự. | Không đọc lại stream; đóng reader/writer đúng lúc. |
| Có JAXB classes từ XSD | JAXB DTO hoặc `JAXBSource`/`JAXBResult` | Type-safe, bớt parser code. | JAXB metadata/schema version đúng. |
| SOAP Header phức tạp/WS-Security | Dùng SOAP message API + interceptor chuẩn | Source chỉ là payload, không quản lý security header. | Thứ tự interceptor và policy đã kiểm thử. |
| Tải tài liệu nhị phân lớn | MTOM/attachment API nếu hợp đồng hỗ trợ | Tránh nhúng base64 XML rất lớn. | Cấu hình MIME/attachment/size limit đúng. |

**Không đồng nhất `StreamSource` với streaming end-to-end.** Nếu transform vào `DOMResult`, cuối cùng XML vẫn được vật liệu hóa thành cây DOM. Nếu buffer response vào `StringResult`, mọi ký tự vẫn nằm trong heap. Chỉ nhìn tên lớp không đủ để đo memory.

### 9.1. Quyền sở hữu và tuổi thọ tài nguyên

Một số quy tắc nên áp dụng:

1. **Tạo Source theo request**, không dùng lại `StreamSource`/`StAXSource` đã bị đọc.
2. **Tạo Result theo response**, không dùng chung `StringResult`/`DOMResult` giữa các request đồng thời.
3. **Đóng stream/reader/writer do mình tạo**, nhưng không tự đóng stream do Spring-WS hoặc container sở hữu.
4. **Không cache `Source` chứa network stream** vượt khỏi vòng đời SOAP request.
5. **Không giả định mọi Transformer, Validator và parser thread-safe**; tạo instance theo scope đúng hoặc tuân theo hướng dẫn của provider.
6. Với output qua writer, kiểm tra flush/close, encoding và dữ liệu đã ghi xong trước khi inspect.

### 9.2. Chuỗi chuyển đổi nào nên tránh?

Ví dụ:

~~~text
InputStream → byte[] → String → StringSource
    → DOMResult → DOMSource → JAXB DTO
    → StringResult → String → HTTP OutputStream
~~~

Có thể hoạt động nhưng tạo nhiều bản sao XML, tăng heap và GC. Khi đã biết dữ liệu đầu vào phải thành JAXB DTO, dùng unmarshalling trực tiếp phù hợp có thể giảm những lần chuyển đổi thừa. Ngược lại, khi chỉ cần transform cấu trúc từ XML sang XML, tránh ép thành DTO rồi serialize lại nếu không có lợi ích.

**Mục tiêu kiến trúc là ít bước, đúng hợp đồng và an toàn**, không phải bắt buộc dùng mọi loại Source/Result trong cùng một request.

## 10. XML security: Source không tự làm XML an toàn

Các dạng `Source`/`Result` là abstraction cho xử lý XML, **không phải ranh giới bảo mật**. Khi nhận payload SOAP từ mạng, phải bảo vệ parser, transformer, schema validator và transport khỏi những dữ liệu hoặc tham chiếu không tin cậy.

### 10.1. Những rủi ro cần phân biệt

| Rủi ro | Ví dụ biểu hiện | Biện pháp nền tảng |
| --- | --- | --- |
| XXE/external entity | XML cố mở file nội bộ hoặc URL ngoài. | Hạn chế DTD, external entities; cấu hình parser/transformer/validator an toàn. |
| SSRF qua schema/XSLT | `schemaLocation` hoặc XSLT include/import mở URI ngoài. | Tắt external access mặc định; sử dụng resolver/catalog allowlist. |
| Entity expansion/độ sâu XML | Parser tiêu tốn CPU/heap quá mức. | Secure processing, giới hạn XML depth/size/entity theo provider, request-size limit. |
| XML injection | Ghép text dữ liệu thành markup XML. | Dùng DOM `setTextContent`, JAXB hoặc XMLStreamWriter; không ghép chuỗi tùy tiện. |
| Signature wrapping/modified payload | Handler đọc element khác với element được WS-Security xác minh. | Dùng stack WS-Security chuẩn, kiểm tra reference và policy, không parse lại body bỏ qua xác minh. |
| Lộ dữ liệu khi trace | Log raw SOAP có token, địa chỉ, thông tin tài khoản. | Chỉ log metadata đã lọc, phân quyền truy cập log. |
| Memory exhaustion | Buffer request lớn thành DOM, String và JAXB objects. | Giới hạn kích thước, timeout/concurrency, benchmark, streaming khi tương thích. |

### 10.2. DOM parser an toàn hơn khi cấu hình đúng provider

Nếu ứng dụng **tự parse một nguồn byte XML không tin cậy**, có thể xây `DocumentBuilderFactory` theo định hướng an toàn:

~~~java
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;

DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
factory.setNamespaceAware(true);
factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
factory.setXIncludeAware(false);
factory.setExpandEntityReferences(false);

factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

// Khi provider hỗ trợ, chính sách có thể từ chối mọi DOCTYPE:
// factory.setFeature(
//     "http://apache.org/xml/features/disallow-doctype-decl", true);

var builder = factory.newDocumentBuilder();
// Document doc = builder.parse(trustedBoundedInputStream);
~~~

Đoạn này minh họa **cấu hình cơ bản** trên parser provider phù hợp, không bảo đảm an toàn tuyệt đối trên mọi JAXP implementation. Một số `setFeature`/`setAttribute` có thể ném exception nếu provider không hỗ trợ; **phải fail closed** cho nguồn không tin cậy thay vì bắt exception rồi tiếp tục parse không có bảo vệ. Nên đặt `EntityResolver` chặn external resolution và kiểm tra giới hạn XML parser của Java/runtime thực tế. Đặc biệt, `setExpandEntityReferences(false)` không phải biện pháp duy nhất chống XXE.

Dùng `DOMSource` sau khi đã parse bằng parser an toàn; không mặc nhiên tin một `Document` được cung cấp từ nơi khác mà không biết cách nó được tạo.

### 10.3. XSLT và schema import cần chính sách riêng

`TransformerFactory` và `SchemaFactory` có thể đi tới tài nguyên bên ngoài qua XSLT `document()`, `xsl:include/import` hoặc XSD `xs:include/import`. Đặt:

~~~java
transformerFactory.setAttribute(
    XMLConstants.ACCESS_EXTERNAL_DTD, "");
transformerFactory.setAttribute(
    XMLConstants.ACCESS_EXTERNAL_STYLESHEET, "");

schemaFactory.setProperty(
    XMLConstants.ACCESS_EXTERNAL_DTD, "");
schemaFactory.setProperty(
    XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
~~~

Nếu hợp đồng doanh nghiệp thật sự có schema chia file, nên dùng **resource resolver/catalog tin cậy** trỏ tới các XSD đã đóng gói hoặc được kiểm duyệt. Không mở quyền truy cập bất kỳ URL ngoài để giải quyết nhanh lỗi import trong production.

### 10.4. WS-Security không được thay bằng transformer

SOAP Header có thể chứa `wsse:Security`, chữ ký số, timestamp hoặc token. `Source` lấy từ `soap:Body` không thay thế bước xác minh Header/Signature. Khi sử dụng `MessageContext` hoặc API `SoapMessage`, phần xử lý bảo mật nên giao cho các interceptor/runtime WS-Security phù hợp, ví dụ stack tích hợp với WSS4J.

Một SOAP Body có thể **hợp lệ XSD nhưng không được xác thực**, hoặc **chữ ký hợp lệ nhưng có giá trị nghiệp vụ sai**. Cần cả security validation và payload/schema/business validation theo hợp đồng, không loại bỏ bước nào chỉ vì sử dụng XML streaming.

## 11. SOAP Fault và lỗi XML trực tiếp

Khi một phép transform hoặc unmarshal thất bại, mã lỗi xuất hiện ở tầng nào?

| Lỗi | Khi nào xảy ra? | Điều client nên kiểm tra |
| --- | --- | --- |
| `TransformerException` / `SAXParseException` | Nguồn XML malformed hoặc transform/parse thất bại. | Log kỹ thuật an toàn; lỗi có thể xảy ra trước endpoint và được map Fault tùy stack. |
| `SAXException` từ XSD validator | Payload sai cấu trúc/kiểu/ràng buộc. | SOAP Fault/validation contract; không giả định cùng HTTP status ở mọi stack. |
| `SoapFaultClientException` (Spring-WS client) | Server trả SOAP Fault và fault resolver mặc định xử lý. | Fault code/reason/detail, operation và correlation ID. |
| Lỗi HTTP/TLS/timeout | Chưa có SOAP response hợp lệ hoặc request chưa đến server. | Transport, DNS, certificate/trust, proxy, timeout. |
| JAXB marshal/unmarshal failure | Model Java hoặc XML root/namespace/kiểu không tương thích. | Metadata JAXB, XSD version và QName payload. |
| Business exception | XML hợp đồng hợp lệ nhưng nghiệp vụ không chấp nhận. | Quy tắc domain và fault mapping được thỏa thuận. |

Nếu endpoint ở mục 6 tự ném `IllegalArgumentException`, server **không tự đảm bảo** tạo SOAP 1.1 `Client` Fault với mã và detail đúng yêu cầu. Cần cấu hình exception resolver, chẳng hạn `SoapFaultMappingExceptionResolver` hoặc cơ chế tương ứng của Spring-WS version đang dùng. Không trả raw stack trace hay đường dẫn hệ thống vào Fault.

Một SOAP 1.1 Fault minh họa:

~~~xml
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <soap:Fault>
      <faultcode>soap:Client</faultcode>
      <faultstring>Payload XML không hợp lệ</faultstring>
      <detail>
        <errorCode>INVALID_XML_PAYLOAD</errorCode>
      </detail>
    </soap:Fault>
  </soap:Body>
</soap:Envelope>
~~~

Đây là bản tin ví dụ; `detail` thực tế cần namespace/structure theo WSDL fault contract nếu có. SOAP 1.2 có Fault structure khác. **Không ghi một thẻ `<soap:Fault>` vào `getPayloadResult()` như XML nghiệp vụ bình thường** rồi mặc định framework sẽ coi đó là Fault chuẩn; cần dùng SOAP Fault API/exception resolver.

### 11.1. Khi lỗi xuất hiện sau khi stream response bắt đầu

Nếu response được ghi theo luồng và transformer phát sinh exception khi một phần HTTP body đã được gửi, response có thể đã committed. Lúc đó không phải lúc nào còn có thể thay toàn bộ response bằng SOAP Fault hợp lệ.

Vì vậy, cần kiểm tra các điều kiện dễ dự đoán (quyền truy cập, XSD input, tham số nghiệp vụ) trước khi bắt đầu ghi lượng XML lớn khi có thể. Với XML response có nhiều phần, test cả lỗi giữa chừng, cơ chế đóng/cleanup stream và hành vi proxy/client trước kết quả dở dang.

## 12. Kiểm thử Source/Result với Spring-WS

### 12.1. Unit test độc lập cho Transformer

Một phép thử cơ bản: lấy `StreamSource` chứa XML hợp lệ, identity-transform sang `DOMResult`, rồi kiểm tra namespace URI/localName/root và giá trị text. Sau đó biến đổi cùng XML sang `StreamResult` để kiểm tra serializer tạo XML well-formed.

Tập tình huống nên bao gồm:

- XML có Unicode tiếng Việt: `Nguyễn Thị Hà`, ký tự `&amp;` trong nội dung.
- Prefix thay đổi nhưng namespace URI không đổi.
- Root QName sai namespace hoặc local name.
- XML malformed, dấu `&` không escape, thiếu closing tag.
- `xs:sequence` sai thứ tự, phần tử thiếu hoặc thừa khi bật XSD validation.
- Stream chỉ đọc được một lần: thử cố đọc lại để hiểu giới hạn, **không đưa code kiểu đó vào production**.
- DOM có nested element trùng tên: xác minh helper đọc đúng *direct child* theo contract.
- SAX/StAX với DOCTYPE và external entity: hệ thống phải từ chối/không resolve theo security policy.

### 12.2. Kiểm thử endpoint với `MockWebServiceClient`

Spring-WS Test cung cấp `MockWebServiceClient` cho phép gửi **payload XML** tới endpoint trong test ApplicationContext mà không phải chạy HTTP server thật:

~~~java
import org.springframework.ws.test.server.MockWebServiceClient;
import org.springframework.xml.transform.StringSource;

import static org.springframework.ws.test.server.RequestCreators.withPayload;
import static org.springframework.ws.test.server.ResponseMatchers.noFault;

// applicationContext chứa @Endpoint, mapping và adapter thật.
MockWebServiceClient client =
    MockWebServiceClient.createClient(applicationContext);

String xml =
    "<ord:CreateOrderRequest " +
    "xmlns:ord=\"urn:example:orders:v1\">" +
    "<ord:clientOrderId>WEB-20261127-0042" +
    "</ord:clientOrderId>" +
    "</ord:CreateOrderRequest>";

client.sendRequest(withPayload(new StringSource(xml)))
      .andExpect(noFault());
~~~

Ví dụ rút gọn, giả định cấu hình test chứa endpoint ở mục 6 và nghiệp vụ giả lập không phát lỗi. `noFault()` chỉ chứng minh test response **không có SOAP Fault**; nên bổ sung assertion trên `CreateOrderResponse`, QName, XSD validity và giá trị từ business service. Nếu SOAP server yêu cầu Header WS-Security, test cũng phải mô phỏng hoặc kiểm thử độc lập security pipeline theo chính sách dự án.

### 12.3. End-to-end bằng HTTP và SOAP Envelope

Trong môi trường test, nếu server đăng ký `MessageDispatcherServlet` dưới `/ws/*` và SOAP endpoint ở `http://localhost:8080/ws`, có thể lưu file `request.xml` như sau:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1">
  <soap:Header/>
  <soap:Body>
    <ord:CreateOrderRequest>
      <ord:clientOrderId>WEB-20261127-0042</ord:clientOrderId>
    </ord:CreateOrderRequest>
  </soap:Body>
</soap:Envelope>
~~~

Gửi request trên PowerShell/Windows:

~~~powershell
curl.exe --include --request POST --header 'Content-Type: text/xml; charset=utf-8' --header 'SOAPAction: "urn:example:orders:v1/CreateOrder"' --data-binary '@request.xml' "http://localhost:8080/ws"
~~~

`SOAPAction` ở đây là ví dụ; phải lấy giá trị thực tế từ WSDL `soap:operation`. Nếu Spring-WS server chưa có contract/endpoint tương ứng, command chỉ dùng để minh họa HTTP/Envelope chứ không bảo đảm phản hồi thành công.

**Phân biệt test:** `MockWebServiceClient` đánh giá pipeline endpoint ở server; lệnh HTTP kiểm tra thêm servlet mapping, SOAP message factory, MIME content type, network/TLS/proxy. Khi tải response, kiểm tra SOAP Envelope ngoài cùng, root QName trong Body, Fault nếu có, HTTP status và schema validity.

## 13. Bảng lỗi thường gặp khi dùng Source và Result

| Triệu chứng | Nguyên nhân điển hình | Hướng xử lý |
| --- | --- | --- |
| `Source` đọc được một lần rồi rỗng | `StreamSource`/`StAXSource` đã tiêu thụ stream. | Chỉ dùng một consumer, hoặc tạo nguồn mới/caching có kiểm soát. |
| `getPayloadSource()` không có Header WS-Security | API trả payload của SOAP Body, không phải Envelope. | Dùng `SoapMessage`/Header và security interceptor chuẩn. |
| `getPayloadResult()` tạo Envelope lồng trong Body | Ghi nguyên `soap:Envelope` làm payload. | Chỉ ghi XML element nghiệp vụ theo XSD. |
| XML response mất namespace | DOM element tạo bằng `createElement` thay vì `createElementNS`. | Tạo XML với namespace URI đúng và kiểm tra QName. |
| XPath không tìm được element | XPath thiếu NamespaceContext hoặc nhầm prefix. | Bind namespace URI khi đánh giá XPath. |
| Output có `&` không escape | Nối XML bằng String. | DOM `setTextContent`, JAXB hoặc XMLStreamWriter. |
| XML declaration encoding khác byte thực | Dùng Writer/OutputStream không nhất quán encoding. | Chọn UTF-8 rõ ràng và kiểm tra byte thực. |
| SOAP response nhận `SoapFaultClientException` | Server đã trả Fault, không phải XML payload thành công. | Đọc Fault code/reason/detail và correlation ID. |
| JAXBSource không hoạt động | Class chưa có JAXB metadata/root. | Kiểm tra `JAXBContext`, `@XmlRootElement` hoặc `JAXBElement`. |
| SAX/StAX parse mở external entity | Parser/provider chưa tắt truy cập tài nguyên ngoài. | Cấu hình chống XXE và kiểm thử fail-closed. |
| Axiom không caching làm endpoint lỗi | Mapping/validation/logging tiêu thụ Body nhiều lần. | Giữ caching hoặc thiết kế luồng một lần phù hợp version. |
| Request lớn gây OOM | DOM/String buffers, JAXB graph hoặc không có size limit. | Áp giới hạn ở gateway/container và profile bộ nhớ. |
| Bean có nhiều request bị trộn dữ liệu | Lưu Source/Result/DOM mutable làm field singleton. | Tạo instance theo request; kiểm soát concurrency. |

## 14. Bài tập chọn biểu diễn XML và checklist

### Tình huống A — Chỉ cần sửa một element XML nhỏ

Một ứng dụng nhận SOAP Body nhỏ và muốn sửa `currency` trong payload, giữ nguyên các element khác. Nếu cần truy cập ngẫu nhiên và chỉnh node, `DOMSource`/`DOMResult` là lựa chọn dễ hiểu. Nhưng phải parse an toàn, kiểm tra XSD sau chỉnh sửa và bảo đảm không sửa nội dung đã ký theo chính sách WS-Security.

### Tình huống B — Chuyển một file XML rất lớn sang file khác

Chỉ cần biến đổi tuần tự, không truy vấn ngẫu nhiên hoặc tạo Java DTO: `StreamSource`/`StreamResult` hoặc pipeline StAX phù hợp có thể giảm việc tạo DOM. Tuy nhiên, transformer và các tầng ở trước/sau vẫn có thể buffer; cần benchmark peak heap, latency và giới hạn input.

### Tình huống C — Có XSD ổn định và sinh JAXB được

Dữ liệu đơn hàng có nhiều trường, ràng buộc và client Java. `Jaxb2Marshaller` với DTO từ XSD có thể giảm code parse thủ công. `JAXBSource`/`JAXBResult` hữu ích khi phải tích hợp vào một pipeline nhận `Source`/`Result`, nhưng không phải lựa chọn bắt buộc cho mọi request.

### Tình huống D — XML đọc qua StAX và còn một interceptor cần log Body

StAX reader hoặc Axiom không caching có thể chỉ đọc một lần; interceptor đọc trước adapter làm cạn payload. Giải pháp không phải chỉ đổi kiểu tham số thành `Source`. Phải xem toàn pipeline, lựa chọn caching, logging metadata hoặc thiết kế xử lý một lần có kiểm soát.

### Tình huống E — Client gặp SOAP Fault sau khi gửi StringSource

`StringSource` đã tạo được XML, nhưng server trả Fault. Kiểm tra schema/QName, SOAPAction, endpoint URL, binding SOAP 1.1/1.2, WS-Security, XSD validation và business error. Kết luận “StringSource sai” khi chưa đọc Fault là quá vội.

### Checklist trước khi chọn Source/Result trong Spring-WS

| Câu hỏi | Điều kiện đạt |
| --- | --- |
| Đang xử lý đúng tầng? | Payload trong SOAP Body được tách khỏi SOAP Header/Envelope. |
| Chọn Source đúng nhu cầu? | DOM/SAX/Stream/StAX/JAXB có lý do rõ về truy cập và bộ nhớ. |
| Chọn Result đúng đích? | DOM, event writer, stream hoặc JAXB phù hợp với consumer. |
| Có quyền đọc lại dữ liệu không? | Stream/reader không bị tiêu thụ hai lần ngoài ý muốn. |
| Tài nguyên được quản lý đúng? | Chỉ đóng stream do ứng dụng sở hữu, không đóng stream của framework. |
| QName và schema chính xác? | Namespace, element và dữ liệu phù hợp XSD/WSDL. |
| Chặn XXE và external access? | Parser, transformer và validator có cấu hình fail-closed phù hợp. |
| WS-Security đúng tầng? | Header/token/signature được xử lý bởi stack được hỗ trợ. |
| Có giới hạn đầu vào? | HTTP size, XML depth, timeout, concurrency và temp storage phù hợp. |
| Xử lý Fault rõ ràng? | Không nhầm SOAP Fault với response payload nghiệp vụ. |
| Có kiểm thử thực tế? | Unit transform + endpoint test + HTTP SOAP integration. |
| Có benchmark khi cần? | Đo heap, CPU/GC, latency và I/O cho workload đại diện. |

### Ghi nhớ

- **`Source` là nguồn XML; `Result` là đích XML**: chúng là giao diện JAXP, không phải SOAP Envelope, Java DTO hay proxy HTTP.
- **`DOMSource/DOMResult`** thuận tiện khi cần cây XML, **`StreamSource/StreamResult`** làm việc với stream, **`SAX` và `StAX`** dùng mô hình sự kiện, **`JAXBSource/JAXBResult`** nối object JAXB với xử lý XML.
- Trong Spring-WS, **`getPayloadSource()` và `getPayloadResult()` thao tác trên SOAP Body payload**; Header, Fault, SOAPAction và WS-Security được xử lý qua API/tầng tương ứng.
- **`StringSource`/`StringResult`** hữu ích cho bài học và kiểm thử; muốn tránh tạo buffer lớn thì phải kiểm tra toàn pipeline chứ không chỉ đổi tên kiểu Java.
- **XML security, XSD validation và SOAP Fault không được giải quyết tự động bởi `Transformer`**. Thiết kế hợp đồng cần kiểm thử cả QName, schema, streaming, bảo mật và tương thích client/server.




