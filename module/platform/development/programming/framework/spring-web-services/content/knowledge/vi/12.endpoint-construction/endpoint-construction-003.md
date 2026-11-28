# Nhận đối tượng JAXB hoặc dữ liệu XML trực tiếp

Trong Spring Web Services (**Spring-WS**), một SOAP endpoint thường nhận payload theo một trong hai cách: **nhận đối tượng Java do JAXB ánh xạ** hoặc **nhận biểu diễn XML trực tiếp** để tự đọc và xử lý. Hai cách có thể dùng chung một hợp đồng XSD/WSDL, nhưng chúng thay đổi đáng kể trách nhiệm của endpoint, khả năng kiểm soát cấu trúc XML, chi phí bộ nhớ và phương pháp kiểm thử.

Giả sử một đối tác gửi `GetOrderRequest`. Nếu XSD đã ổn định, JAXB biến các trường `orderId` thành property Java; endpoint chỉ cần gọi service nghiệp vụ. Nếu phải xử lý một đoạn XML đặc thù, chuyển đổi giữa các schema của đối tác hoặc kiểm tra cấu trúc mà binding chưa bao phủ, endpoint có thể nhận `Source`/DOM và thao tác trực tiếp trên cây XML. **Nhận XML trực tiếp không đồng nghĩa bỏ qua hợp đồng hay bảo mật.**

Bài học thuộc chương **Xây dựng endpoint** của module **SPRING_WEB_SERVICES**. Toàn module tập trung phát triển SOAP **contract-first** bằng XSD/WSDL, JAXB, endpoint và SOAP client, đồng thời xử lý SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích doanh nghiệp. Bài này làm rõ cách chọn kiểu tham số `@RequestPayload`, kiểu phản hồi `@ResponsePayload` và ranh giới giữa **XML transport**, **XML binding** và **logic nghiệp vụ**.

## 1. Hai con đường từ SOAP Body đến endpoint

~~~mermaid
flowchart TD
    A["SOAP Envelope nhận từ client"] --> B["Spring-WS MessageDispatcher<br/>endpoint mapping theo payload QName"]
    B --> C{"Kiểu tham số endpoint"}
    C -->|"JAXB model"| D["Payload method processor<br/>XML → JAXB object"]
    C -->|"XML Source / DOM"| E["XML payload trực tiếp<br/>Source / Element"]
    D --> F["Application service"]
    E --> G["XML adapter / parser<br/>đọc cấu trúc theo namespace"]
    G --> F
    F --> H{"Kiểu kết quả"}
    H -->|"JAXB response"| I["Marshaller → SOAP Body"]
    H -->|"XML Source"| J["Source → SOAP Body"]
    I --> K["SOAP response hoặc Fault"]
    J --> K
~~~

Một số thuật ngữ cần phân biệt:

| Thành phần | Trách nhiệm |
| --- | --- |
| `@Endpoint` | Đánh dấu bean đảm nhận xử lý SOAP endpoint |
| `@PayloadRoot` | Ánh xạ method theo **QName của phần tử gốc payload** trong SOAP Body |
| `@RequestPayload` | Yêu cầu Spring-WS ánh xạ payload đầu vào thành tham số method theo processor hỗ trợ |
| `@ResponsePayload` | Đưa giá trị trả về method thành payload XML của response |
| JAXB / Spring OXM | Chuyển đổi giữa XML và mô hình Java |
| `Source` / DOM | Biểu diễn XML, cho phép code làm việc với node/namespace trực tiếp |
| `MessageContext` / `SoapMessage` | Truy cập request/response message và thông tin SOAP ngoài payload khi cần |

**Điểm mấu chốt:** `@RequestPayload` mặc định nói tới **payload trong SOAP Body**, không phải toàn bộ SOAP Envelope hay HTTP request. Khi cần SOAP Header, chữ ký, thông tin vận chuyển hoặc tài nguyên bổ trợ, phải dùng đúng API/tầng phù hợp.

### Vì sao QName quan trọng hơn tên class?

Giả sử root XML của request là:

~~~xml
<ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
    <ord:orderId>ORD-1024</ord:orderId>
</ord:GetOrderRequest>
~~~

QName của root là `{urn:example:orders:v1}GetOrderRequest`. Dù client đổi prefix `ord` thành `o`, root vẫn có cùng QName. Nhưng đổi namespace thành `urn:example:orders:v2` sẽ tạo QName khác và có thể không khớp `@PayloadRoot`.

Endpoint mapping không nhất thiết dựa vào tên Java class `GetOrderRequest` hay tên WSDL operation. WSDL liên kết message/operation với những phần tử XSD; Spring-WS dispatch theo chiến lược endpoint mapping được cấu hình, trong đó `@PayloadRoot` là lựa chọn phổ biến.

## 2. Thiết kế XSD làm điểm chung cho cả hai cách nhận

Hãy lấy `orders.xsd` làm nguồn sự thật cho payload. Ví dụ đơn giản:

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

XSD này xác định:

- Hai **global elements** `GetOrderRequest` và `GetOrderResponse` thuộc namespace `urn:example:orders:v1`.
- `orderId` bắt buộc xuất hiện một lần theo mặc định `minOccurs=1`/`maxOccurs=1`.
- `status` trong response thuộc một enum ba giá trị.
- `xs:sequence` quy định thứ tự phần tử.
- `elementFormDefault="qualified"` làm cho các phần tử con `orderId` và `status` cũng thuộc namespace đơn hàng.

Cả endpoint JAXB lẫn endpoint XML trực tiếp đều phải tuân thủ XSD đó. Khác biệt nằm ở **ai thực hiện chuyển đổi từ XML sang dữ liệu ứng dụng**, không nằm ở việc contract có tồn tại hay không.

Một WSDL 1.1 contract-first có thể tham chiếu `ord:GetOrderRequest` trong `wsdl:message` input và `ord:GetOrderResponse` trong output, rồi gắn chúng với operation, SOAP binding và port. Việc JAXB sinh được class **không tự bảo đảm** SOAP client đã biết `soap:address`, SOAP version, SOAPAction hoặc security policy trong WSDL.

## 3. Cách A: nhận một đối tượng JAXB từ `@RequestPayload`

Nếu XSD đã được thống nhất và những thông điệp trao đổi có cấu trúc ổn định, **JAXB là lựa chọn mặc định dễ duy trì**. Công cụ XJC có thể sinh Java classes tương ứng với hai global elements từ schema.

Ví dụ một endpoint (giả định đã sinh được `GetOrderRequest`/`GetOrderResponse`, cấu hình Spring-WS có JAXB payload method processor phù hợp):

~~~java
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;

@Endpoint
public class OrderJaxbEndpoint {
    private static final String NS = "urn:example:orders:v1";

    private final OrderApplicationService service;

    public OrderJaxbEndpoint(OrderApplicationService service) {
        this.service = service;
    }

    @PayloadRoot(namespace = NS, localPart = "GetOrderRequest")
    @ResponsePayload
    public GetOrderResponse getOrder(@RequestPayload GetOrderRequest request) {
        String orderId = request.getOrderId();
        String status = service.lookupStatus(orderId);

        GetOrderResponse response = new GetOrderResponse();
        response.setOrderId(orderId);
        response.setStatus(OrderStatusType.fromValue(status));
        return response;
    }
}
~~~

Đây là **mã minh họa**, giả định `OrderApplicationService` trả một trạng thái hợp lệ và công cụ JAXB đã sinh `OrderStatusType.fromValue(...)`. Chữ ký method, cách sinh enum/factory và tên package phụ thuộc toolchain; không thêm logic nội bộ vào generated classes để ví dụ có thể biên dịch.

Quá trình diễn ra:

1. Spring-WS chọn method theo QName của `GetOrderRequest`.
2. Payload argument resolver đọc XML theo cấu hình JAXB và tạo `GetOrderRequest`.
3. Endpoint lấy `orderId` rồi gọi service nghiệp vụ.
4. Endpoint tạo `GetOrderResponse` từ model JAXB.
5. Response payload processor marshal object thành XML; SOAP stack đóng gói vào response Envelope.

**Lợi ích:** code có kiểu rõ ràng, ít phải thao tác DOM, enum và getter/setter biểu đạt đúng cấu trúc đã thiết kế, dễ viết unit test cho logic nghiệp vụ.

**Giới hạn:** JAXB object không nhất thiết giữ mọi chi tiết của bản XML nguồn như prefix gốc, thứ tự attribute, whitespace giữa các node hoặc toàn bộ comment. Nó ưu tiên **dữ liệu theo binding**, không phải lưu giữ từng byte của tài liệu XML.

### 3.1. Chú ý `@XmlRootElement` và `JAXBElement<T>`

Khi XSD dùng anonymous complex type gắn với global element, XJC thường sinh class có `@XmlRootElement` phù hợp. Nhưng với **named complex type** được tham chiếu bởi global element, công cụ có thể tạo class type và một factory method trả `JAXBElement<T>`.

Ví dụ khái niệm:

~~~java
ObjectFactory factory = new ObjectFactory();
GetOrderRequest request = new GetOrderRequest();
request.setOrderId("ORD-1024");

JAXBElement<GetOrderRequest> root =
        factory.createGetOrderRequest(request);
~~~

**Không tự cho rằng `factory.createGetOrderRequest(...)` tồn tại** với mọi schema. Hãy đọc `ObjectFactory` thực tế và các annotation được sinh. Tùy phiên bản Spring-WS và cấu hình argument/return-value processor, một method có thể dùng class gốc được đánh dấu `@XmlRootElement` hoặc `JAXBElement<T>`. Nếu method processor hiện tại không hỗ trợ dạng JAXB đã sinh, cần chọn processor/adapter hoặc cách ánh xạ phù hợp, thay vì sửa class generated bằng tay.

### 3.2. `javax` và `jakarta` không thể trộn tùy ý

Ứng dụng Spring-WS hiện đại gắn với Jakarta XML Binding thường dùng:

~~~java
import jakarta.xml.bind.JAXBElement;
import jakarta.xml.bind.annotation.XmlRootElement;
~~~

Các ngăn xếp cũ có thể dùng `javax.xml.bind.*`. Class được sinh bằng annotation `javax` không được xem là tương đương trực tiếp với Jakarta JAXB runtime chỉ vì đổi dependency. Hãy thống nhất **XJC, API JAXB, runtime JAXB, Spring Framework/Spring-WS** theo thế hệ tương thích; đây là một phần của kiểm thử contract-first.

### 3.3. JAXB model không phải domain model

Mặc dù thuận tiện, đừng đưa generated `GetOrderRequest` vào sâu trong mọi service. Một adapter nhỏ giúp tách:

~~~text
SOAP GetOrderRequest (JAXB)
    ↓ endpoint / adapter
GetOrderQuery (application DTO)
    ↓ domain service
OrderStatus (domain result)
    ↓ mapper
SOAP GetOrderResponse (JAXB)
~~~

Nếu đối tác đổi namespace, thêm field optional hoặc nâng WSDL từ v1 lên v2, code mapper ở biên có thể đổi mà không bắt buộc tác động đến toàn bộ miền nghiệp vụ.

## 4. Cách B: nhận XML trực tiếp bằng `Source`

Spring-WS hỗ trợ làm việc với payload XML trực tiếp qua một số kiểu được endpoint adapter nhận biết. `javax.xml.transform.Source` là interface phổ biến để biểu diễn XML đầu vào/đầu ra mà không ép phải chuyển thành JAXB object.

Ví dụ method endpoint:

~~~java
import javax.xml.transform.Source;
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;

@Endpoint
public class OrderXmlEndpoint {
    private static final String NS = "urn:example:orders:v1";

    @PayloadRoot(namespace = NS, localPart = "GetOrderRequest")
    @ResponsePayload
    public Source getOrder(@RequestPayload Source requestXml) {
        // XML adapter: đọc payload, lấy orderId theo QName,
        // gọi service nghiệp vụ và tạo Source cho response.
        return transformToOrderResponse(requestXml);
    }

    private Source transformToOrderResponse(Source requestXml) {
        throw new UnsupportedOperationException(
                "Cài đặt XML adapter theo contract và chính sách bảo mật");
    }
}
~~~

Đây là **khung minh họa cho chữ ký endpoint**, không phải một handler chạy hoàn chỉnh. Phần tiếp theo cài đặt cách đọc Source an toàn hơn. Spring-WS cần method processor hỗ trợ `Source` tương ứng trong cấu hình endpoint hiện tại.

**Cảnh báo về cấu hình:** `OrderJaxbEndpoint` ở phần 3 và `OrderXmlEndpoint` ở phần 4 là **hai phương án thay thế cho cùng QName** `GetOrderRequest`. **Không đăng ký cả hai endpoint này với cùng một `@PayloadRoot` trong cùng dispatcher** nếu không có chiến lược mapping tách biệt, vì sẽ gây xung đột hoặc ánh xạ không xác định. Hãy chọn đúng một implementation cho operation.

### 4.1. `Source` là một biểu diễn XML, không phải chuỗi text

Một số implementation thường gặp:

| Kiểu | Đặc điểm | Khi cân nhắc |
| --- | --- | --- |
| `DOMSource` | Dựa trên cây DOM trong bộ nhớ | Cần đọc, kiểm tra hoặc chỉnh cấu trúc nhiều lần |
| `SAXSource` | Dựa trên cơ chế event SAX | Hỗ trợ parser/event flow phù hợp |
| `StreamSource` | Dựa trên stream/reader hoặc URI | Cần xử lý luồng nhưng phải kiểm soát vòng đời stream và parser |
| `StAXSource` | Dựa trên XML stream/event reader | Pipeline StAX/streaming có kiểm soát |

**Không giả định kiểu cụ thể của `Source`** mà Spring-WS sẽ truyền vào handler; đừng cast `Source` thành `DOMSource` nếu không có kiểm tra và bảo đảm cấu hình. Ngoài ra, một số `Source` chứa stream chỉ có thể tiêu thụ một lần: việc đọc để log rồi chuyển tiếp cho JAXB có thể khiến bước sau thiếu dữ liệu.

Nếu mục tiêu là kiểm tra vài giá trị payload theo namespace, có thể chuyển `Source` sang DOM tại ranh giới adapter, chấp nhận chi phí dựng cây. Với payload lớn hoặc attachment, cần cân nhắc giải pháp streaming và giới hạn tài nguyên.

## 5. Cách đọc `Source` theo namespace và tạo XML phản hồi

Ví dụ sau minh họa một XML adapter **đọc payload và tạo `DOMSource`**, không dùng JAXB. Nó chỉ xử lý XML đã vào endpoint qua Spring-WS, và phải được đặt sau các kiểm tra bảo mật/validation thích hợp.

~~~java
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.parsers.ParserConfigurationException;
import javax.xml.transform.Source;
import javax.xml.transform.Transformer;
import javax.xml.transform.TransformerException;
import javax.xml.transform.TransformerFactory;
import javax.xml.transform.dom.DOMResult;
import javax.xml.transform.dom.DOMSource;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;

public final class OrderXmlAdapter {
    private static final String NS = "urn:example:orders:v1";

    public static String readOrderId(Source payload)
            throws TransformerException {
        // Copy XML payload sang DOM, không biến đổi cấu trúc kinh doanh.
        TransformerFactory tf = TransformerFactory.newInstance();
        tf.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        tf.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        tf.setAttribute(XMLConstants.ACCESS_EXTERNAL_STYLESHEET, "");

        Transformer transformer = tf.newTransformer();
        DOMResult result = new DOMResult();
        transformer.transform(payload, result);

        Node rootNode = result.getNode();
        Element root = (rootNode instanceof Document)
                ? ((Document) rootNode).getDocumentElement()
                : (rootNode instanceof Element ? (Element) rootNode : null);

        if (root == null
                || !NS.equals(root.getNamespaceURI())
                || !"GetOrderRequest".equals(root.getLocalName())) {
            throw new IllegalArgumentException("Sai QName request");
        }

        NodeList ids = root.getElementsByTagNameNS(NS, "orderId");
        if (ids.getLength() != 1
                || ids.item(0).getParentNode() != root) {
            throw new IllegalArgumentException("orderId không hợp lệ");
        }

        String id = ids.item(0).getTextContent();
        if (id == null || id.isBlank() || id.length() > 100) {
            throw new IllegalArgumentException("Thiếu hoặc sai orderId");
        }
        return id;
    }

    public static Source writeResponse(String orderId, String status)
            throws ParserConfigurationException {
        DocumentBuilderFactory dbf = DocumentBuilderFactory.newInstance();
        dbf.setNamespaceAware(true);
        dbf.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);

        Document doc = dbf.newDocumentBuilder().newDocument();
        Element root = doc.createElementNS(NS, "ord:GetOrderResponse");
        root.setAttributeNS(XMLConstants.XMLNS_ATTRIBUTE_NS_URI,
                "xmlns:ord", NS);
        doc.appendChild(root);

        Element id = doc.createElementNS(NS, "ord:orderId");
        id.setTextContent(orderId);
        root.appendChild(id);

        Element state = doc.createElementNS(NS, "ord:status");
        state.setTextContent(status);
        root.appendChild(state);

        return new DOMSource(doc);
    }
}
~~~

Với adapter này, có thể thay phần body `getOrder(...)` ở `OrderXmlEndpoint` phần 4 bằng đoạn xử lý cụ thể sau; ví dụ giả định endpoint đã có field `service` kiểu `OrderApplicationService`:

~~~java
@PayloadRoot(namespace = NS, localPart = "GetOrderRequest")
@ResponsePayload
public Source getOrder(@RequestPayload Source requestXml)
        throws TransformerException, ParserConfigurationException {
    String orderId = OrderXmlAdapter.readOrderId(requestXml);
    String status = service.lookupStatus(orderId);
    return OrderXmlAdapter.writeResponse(orderId, status);
}
~~~

Đây là **đoạn thay thế method**, không phải operation mới để đăng ký bên cạnh handler cùng QName. Khi tích hợp thật, cần **ánh xạ exception thành SOAP Fault** bằng resolver phù hợp; không để đường dẫn XML, chi tiết parser hoặc stack trace nội bộ lộ ra client.

**Các giới hạn của mã mẫu cần hiểu rõ:**

1. `getElementsByTagNameNS` tìm node con/cháu; code đã thêm kiểm tra parent trực tiếp nhưng **không thay thế XSD validation** cho mọi trường hợp như thứ tự, phần tử ngoài dự kiến hay giá trị enum.
2. `TransformerFactory` và parser/provider có thể khác nhau. Nếu provider không hỗ trợ cấu hình an toàn yêu cầu, **báo lỗi và không tiếp tục bằng chế độ kém an toàn**.
3. `DOMResult` dựng cây XML trong bộ nhớ, vì vậy phải **giới hạn kích thước/depth của payload** ở tầng phù hợp trước khi dùng trên dữ liệu không tin cậy.
4. Phần tạo response dùng `setTextContent` thay vì ghép chuỗi XML, giảm nguy cơ sinh XML sai khi giá trị có ký tự đặc biệt.
5. `status` phải được service nghiệp vụ và/hoặc validator kiểm tra thuộc enum XSD; không cho dữ liệu tùy ý lọt vào phản hồi công khai.
6. Việc nhận `Source` trong endpoint **không tự làm nguồn XML an toàn**. An toàn bắt đầu từ SOAP message factory/parser, cấu hình không đọc DTD/entity ngoài, WS-Security và các giới hạn tài nguyên của ứng dụng.

### Vì sao không đọc XML bằng regex hoặc cắt chuỗi?

Hai XML này có cùng QName và nội dung:

~~~xml
<ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
    <ord:orderId>ORD-1024</ord:orderId>
</ord:GetOrderRequest>
~~~

~~~xml
<o:GetOrderRequest xmlns:o="urn:example:orders:v1">
    <o:orderId>ORD-1024</o:orderId>
</o:GetOrderRequest>
~~~

Regex tìm literal `<ord:orderId>` sẽ bỏ sót trường hợp thứ hai. XPath/DOM/JAXB với namespace hiểu **namespace URI + local name**, không phụ thuộc vào prefix do phía gửi tự chọn. Đồng thời, parsing bằng chuỗi khó xử lý escape như `&amp;`, CDATA, XML entity hoặc whitespace theo quy tắc XML.

## 6. Có nên nhận trực tiếp DOM `Element` hoặc `Document`?

Tùy phiên bản Spring-WS và endpoint adapter được đăng ký, một số processor hỗ trợ các kiểu DOM như `org.w3c.dom.Element` và/hoặc `Document`. Khi có hỗ trợ, code có thể sử dụng API DOM trực tiếp, tránh bước convert `Source` sang DOM.

Ví dụ ở mức thiết kế:

~~~java
@PayloadRoot(namespace = NS, localPart = "GetOrderRequest")
@ResponsePayload
public Source getOrder(@RequestPayload Source requestXml) {
    // Chọn Source là kiểu tổng quát nhất trong ví dụ của bài.
    // Nếu endpoint adapter hỗ trợ Element, có thể chọn Element
    // và thao tác getNamespaceURI()/getLocalName()/getChildNodes().
    return handleXml(requestXml);
}
~~~

Không tự ép mọi `Source` thành DOM. Nếu tổ chức muốn dùng trực tiếp `Element` trong signature, cần xác nhận **method argument resolver** của Spring-WS thực tế hỗ trợ kiểu đó, và viết integration test với `MockWebServiceClient`.

Khi thao tác DOM, đặc biệt phân biệt:

- `getNodeName()` có thể bao gồm prefix, trong khi `getLocalName()`/`getNamespaceURI()` phản ánh QName.
- `getTextContent()` trả về nội dung text của node và các descendant; nếu node chứa cấu trúc lồng nhau, việc lấy text không đủ để xác nhận hợp đồng.
- `NodeList` có thể là tập node con/cháu tùy API, và thứ tự `xs:sequence` phải được validator kiểm tra.
- XML namespace của **attribute** khác với namespace của element; `elementFormDefault` không mặc nhiên quyết định `attributeFormDefault`.

## 7. Phản hồi endpoint: JAXB object hay XML `Source`?

`@ResponsePayload` chỉ định kết quả method được xử lý như **payload XML đầu ra**. Kiểu trả về phải nằm trong tập kiểu mà endpoint adapter hỗ trợ.

| Kiểu trả về | Đặc điểm | Khi phù hợp |
| --- | --- | --- |
| `GetOrderResponse` được JAXB gắn `@XmlRootElement` | Spring-WS/JAXB tạo XML theo metadata JAXB | Hợp đồng XSD ổn định, ưu tiên type safety |
| `JAXBElement<GetOrderResponse>` | Mang QName element tường minh qua factory/binding | Global element tham chiếu named type; phụ thuộc processor hỗ trợ |
| `DOMSource` / `Source` | Trả payload dưới dạng XML source | Adapter XML cần giữ hoặc xây dựng cấu trúc XML trực tiếp |
| Không trả payload | Có thể không sinh response body theo method contract | Chỉ dùng khi service contract và cách trao đổi message cho phép |

Ví dụ JAXB response lý tưởng với XSD phần 2:

~~~xml
<ord:GetOrderResponse xmlns:ord="urn:example:orders:v1">
    <ord:orderId>ORD-1024</ord:orderId>
    <ord:status>CONFIRMED</ord:status>
</ord:GetOrderResponse>
~~~

Trong code, **không trả một SOAP Envelope hoàn chỉnh** dưới dạng JAXB payload hay `DOMSource` khi `@ResponsePayload` chờ **payload của Body**. Spring-WS chịu trách nhiệm đóng gói SOAP Envelope. Nếu bạn đưa cả Envelope vào payload, kết quả có thể bị lồng Envelope sai giao thức.

### Kiểm tra điều gì khi tạo XML trực tiếp?

1. **Root QName**: đúng `{urn:example:orders:v1}GetOrderResponse`.
2. **Namespace của phần tử con**: `orderId` và `status` thuộc namespace đơn hàng.
3. **Thứ tự và số lượng**: `orderId` đứng trước `status`, mỗi trường xuất hiện theo XSD.
4. **Kiểu và giá trị**: `status` thuộc enum; `orderId` hợp các ràng buộc đã công bố.
5. **Không rò rỉ dữ liệu**: không thêm debug stack trace hoặc nội dung nội bộ vào Body.

Khi JAXB đã có thể sinh đúng XML, việc tự xây DOM cho một response đơn giản chỉ tăng công việc và rủi ro. Chỉ dùng XML trực tiếp khi nó giải quyết nhu cầu tích hợp cụ thể.

## 8. Xử lý SOAP Header và MessageContext không nằm trong `@RequestPayload`

Một đối tác có thể gửi SOAP Header chứa correlation ID, thông tin routing hoặc WS-Security token, trong khi SOAP Body chỉ chứa `GetOrderRequest`.

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1"
    xmlns:hdr="urn:example:headers:v1">
    <soapenv:Header>
        <hdr:CorrelationId>req-123</hdr:CorrelationId>
    </soapenv:Header>
    <soapenv:Body>
        <ord:GetOrderRequest>
            <ord:orderId>ORD-1024</ord:orderId>
        </ord:GetOrderRequest>
    </soapenv:Body>
</soapenv:Envelope>
~~~

`@RequestPayload GetOrderRequest` hay `@RequestPayload Source` chỉ mô tả **payload XML của Body**. Muốn kiểm tra SOAP Header, không nên tìm `CorrelationId` trong request JAXB model nếu XSD Body không định nghĩa trường đó.

Khi cần làm việc với message-level information, có thể sử dụng `MessageContext` trong thành phần mà Spring-WS hỗ trợ, chẳng hạn interceptor:

~~~java
import org.springframework.ws.context.MessageContext;
import org.springframework.ws.soap.SoapMessage;

public void inspectSoapRequest(MessageContext context) {
    if (context.getRequest() instanceof SoapMessage soapMessage) {
        var soapHeader = soapMessage.getSoapHeader();
        // Dùng API SOAP Header phù hợp để đọc phần tử có QName đã biết.
        // Không coi bất kỳ giá trị Header nào là đáng tin trước khi xác minh.
    }
}
~~~

Đây là đoạn **minh họa ngữ cảnh**, chưa trích Header cụ thể. Nếu nhiều interceptor cần chia sẻ correlation ID đã được làm sạch, có thể lưu property trong `MessageContext`; property đó là metadata **nội bộ lượt xử lý**, không tự xuất hiện trong SOAP Header/Body hoặc HTTP response.

**Nhất là với WS-Security:** không tự đọc `wsse:Security` bằng DOM rồi coi nó là chứng cứ caller hợp lệ. Chữ ký, timestamp, token, mã hóa và chứng chỉ cần được xác minh bởi SOAP security stack/interceptor chuyên trách theo chính sách tích hợp.

## 9. Khi nào chọn JAXB, khi nào chọn XML trực tiếp?

| Tiêu chí | JAXB object | `Source` / DOM XML |
| --- | --- | --- |
| XSD ổn định, contract-first | **Rất phù hợp** | Có thể dùng nhưng không cần thiết |
| Code Java có kiểu mạnh | Getter/setter, enum và model được sinh | Cần tự đọc node, chuyển kiểu và kiểm tra |
| Thay đổi field XSD | Sinh lại lớp, sửa mapper có kiểm soát | Có thể phải cập nhật XPath/DOM lookup bằng tay |
| Không cần giữ chi tiết lexical XML | Phù hợp | Có thể linh hoạt hơn |
| Cần thao tác cấu trúc XML đặc biệt | Có thể cần adapter tùy chỉnh | **Phù hợp** nếu có lý do rõ ràng |
| XML có phần mở rộng `xs:any` | Có binding linh hoạt nhưng phải thiết kế | Dễ truy cập node mở rộng; vẫn cần contract |
| Payload lớn | Object graph có thể tốn bộ nhớ | Streaming có thể phù hợp nhưng DOM cũng tốn bộ nhớ |
| Bảo mật XML/WS-Security | Vẫn phải cấu hình | Vẫn phải cấu hình; thêm bề mặt XML parsing |
| Test nghiệp vụ | Dễ unit test với Java types | Cần test XML namespace, node/structure nhiều hơn |
| Kiểm thử tương thích đối tác | Phải so XML thực tế | Cũng phải so XML thực tế |

**Khuyến nghị cho đa số operation SOAP doanh nghiệp:** nhận JAXB khi payload XSD rõ và ổn định, sau đó ánh xạ về DTO/domain. Dùng XML trực tiếp khi integration thực sự đòi **biến đổi, kiểm tra hoặc duy trì cấu trúc XML** mà JAXB bình thường không giải quyết tốt.

### Không đồng nhất “XML trực tiếp” với “không cần schema”

Nếu đối tác gửi XML sai XSD, endpoint nhận `Source` có thể vẫn đọc được một số trường. Điều này **không biến payload thành hợp lệ**. Ngược lại, JAXB có thể unmarshal XML thiếu trường bắt buộc mà không ném lỗi khi không bật validation. Vì vậy **cả hai nhánh đều cần schema validation và quy tắc nghiệp vụ** theo hợp đồng.

## 10. Mô hình kết hợp: XML adapter ở biên, domain vẫn có kiểu rõ ràng

Một tình huống hợp lý để dùng XML trực tiếp là phải nhận payload của đối tác ở schema A rồi chuyển sang schema B nội bộ.

~~~mermaid
flowchart LR
    A["SOAP Body đối tác<br/>XML theo XSD A"] --> B["Spring-WS endpoint<br/>@RequestPayload Source"]
    B --> C["XML adapter<br/>XSLT / DOM / XPath"]
    C --> D["XML đích<br/>theo XSD B"]
    D --> E["Schema validation"]
    E --> F["JAXB unmarshal"]
    F --> G["Domain DTO/service"]
    G --> H["Response mapper"]
    H --> I["SOAP payload theo hợp đồng"]
~~~

Một cách khác là JAXB binding cả schema A và B, rồi map hai object models bằng Java thay vì XSLT. Chọn giải pháp theo độ phức tạp cấu trúc và nghiệp vụ.

**Không nên nhét cả phân tích XML, tra cứu database, xử lý transaction, ký SOAP và dựng response vào cùng một `@Endpoint`.** Endpoint nên điều phối ngắn gọn:

~~~text
Endpoint
  → XML/JAXB adapter (biên giao tiếp)
  → Input validation (XSD + business)
  → Application service (nghiệp vụ, transaction)
  → Response mapper
  → SOAP message / Fault
~~~

Với cách tách này, có thể unit test domain service không cần SOAP, rồi integration test toàn bộ contract ở biên.

## 11. Validation, SOAP Fault và xử lý exception

Một endpoint nhận JAXB hoặc XML `Source` đều có thể gặp ba loại lỗi:

| Loại lỗi | Ví dụ | Cách xử lý nên hướng tới |
| --- | --- | --- |
| **Sai cấu trúc XML/XSD** | Thiếu `orderId`; sai namespace; `status` ngoài enum | Từ chối payload; tạo SOAP Fault phía client/request theo contract |
| **Sai nghiệp vụ/quyền** | `orderId` không tồn tại, caller không được truy cập | Lỗi nghiệp vụ/bảo mật có kiểm soát; không lộ dữ liệu nhạy cảm |
| **Lỗi hệ thống** | XML transformer lỗi cấu hình, DB timeout | Fault phía server/hệ thống, log nội bộ và correlation ID |

Trong Spring-WS, exception có thể được ánh xạ thành SOAP Fault thông qua exception resolver, ví dụ `SoapFaultMappingExceptionResolver` hoặc cơ chế tương đương. SOAP Fault 1.1 có cấu trúc khác SOAP Fault 1.2; mã Fault, detail và HTTP status phải phù hợp với SOAP binding của dịch vụ.

Ví dụ SOAP 1.1 Fault minh họa:

~~~xml
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
    <soapenv:Body>
        <soapenv:Fault>
            <faultcode>soapenv:Client</faultcode>
            <faultstring>orderId không hợp lệ</faultstring>
        </soapenv:Fault>
    </soapenv:Body>
</soapenv:Envelope>
~~~

Đừng ném thẳng exception với stack trace và kỳ vọng SOAP client hiểu. Nếu WSDL định nghĩa typed fault detail, cần sinh/ánh xạ phần detail đúng schema. Với lỗi xác minh chữ ký/chứng chỉ, dùng policy và security stack thích hợp, không cố tiếp tục phân tích payload như một request hợp lệ.

### Validation dùng ở đâu?

Trong Spring-WS có thể cấu hình `PayloadValidatingInterceptor` để validate payload theo XSD ở các bước phù hợp của pipeline. Với luồng dùng JAXB, cũng có thể cấu hình `Jaxb2Marshaller` hoặc `Unmarshaller` dùng schema. Hai phương án có phạm vi khác nhau; không giả định chỉ cần có tệp XSD thì framework **tự động validate mọi message**.

Cần kiểm tra:

1. Root QName và namespace v1/v2.
2. Thứ tự `xs:sequence`, cardinality `minOccurs`/`maxOccurs`.
3. Kiểu số/ngày/enum, trường `nillable`, default/fixed.
4. XML response **đi ra** hợp XSD, không chỉ request đi vào.
5. Mọi `xs:include`/`xs:import` resolve đúng từ JAR và client ngoài hệ thống.

**Validation không thay thế authorization.** Một `orderId` đúng kiểu XSD vẫn có thể thuộc khách hàng khác.

## 12. XML security khi nhận raw XML

Nếu xử lý XML trực tiếp, ứng dụng có thêm trách nhiệm liên quan đến parser và transformer:

**XXE / DTD / external entities.** Parser cho phép tài liệu không tin cậy nạp DTD hoặc entity ngoài có thể dẫn đến đọc tài nguyên trái phép, SSRF hoặc tiêu tốn tài nguyên. Cần cấu hình SOAP message factory/parser có chính sách an toàn, và với parser tự tạo phải tắt các cơ chế không cần thiết, hạn chế external DTD/schema.

**Transformer và XSLT.** Nếu dùng `TransformerFactory` hoặc `XSLT`, hạn chế `ACCESS_EXTERNAL_DTD` và `ACCESS_EXTERNAL_STYLESHEET` theo provider, kiểm soát stylesheet/resolve/import. Không cho SOAP client tự upload stylesheet rồi thực thi.

**Từ chối dịch vụ.** XML rất lớn, lồng sâu, nhiều node hoặc stylesheet phức tạp có thể ngốn CPU/bộ nhớ. DOM đưa toàn bộ cây vào RAM; ngay cả StAX/streaming cũng cần giới hạn kích thước/độ sâu và timeout.

**SOAP signatures.** Nếu WS-Security ký SOAP Body, việc biến đổi XML sau khi ký hoặc sửa nội dung trước/sau bước xác minh không đúng chính sách có thể làm chữ ký thất bại. Chỉ biến đổi ở ranh giới được thiết kế, với thứ tự verify/decrypt/transform/sign thích hợp.

**TLS/mTLS và chứng chỉ.** TLS bảo vệ kết nối transport, còn WS-Security bảo vệ SOAP message theo chính sách. Endpoint nhận JAXB hay `Source` không thay thế cấu hình keystore, truststore, xác thực hoặc kiểm tra quyền nghiệp vụ.

### Không parse XML không tin cậy bằng cách bỏ qua lỗi cấu hình

Ví dụ với `DocumentBuilderFactory` khi cần parse **một XML file hoặc input stream riêng** ngoài SOAP message factory:

~~~java
DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
factory.setNamespaceAware(true);
factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
factory.setFeature(
        "http://apache.org/xml/features/disallow-doctype-decl", true);
factory.setXIncludeAware(false);
factory.setExpandEntityReferences(false);
factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
// Sau đó mới tạo DocumentBuilder và parse input.
~~~

Một số feature/attribute phụ thuộc XML parser provider. Nếu dự án yêu cầu chặn DTD nhưng provider không hỗ trợ, nên **từ chối cấu hình và báo lỗi**, không tự tiếp tục với parser kém an toàn. Giới hạn body size, thời gian xử lý và tài nguyên vẫn cần được áp dụng độc lập.

**Lưu ý:** Khi `@RequestPayload Source` đã được Spring-WS tạo từ SOAP message, nguồn đã trải qua bước xử lý của message factory/transport. Đừng coi đoạn cấu hình `DocumentBuilderFactory` ở trên là thay thế cho việc làm cứng **SOAP parser gốc**.

## 13. Kiểm thử endpoint theo cả hai kiểu dữ liệu

Một unit test trên `OrderApplicationService` không thể chứng minh endpoint đã nhận đúng SOAP payload, QName, JAXB model hay XML `Source`.

### 13.1. Kiểm thử bằng `MockWebServiceClient`

Ví dụ với một Spring test context có endpoint đã đăng ký:

~~~java
import static org.springframework.ws.test.server.RequestCreators.withPayload;
import static org.springframework.ws.test.server.ResponseMatchers.payload;

import org.springframework.xml.transform.StringSource;
import org.springframework.ws.test.server.MockWebServiceClient;

String requestXml = """
    <ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
        <ord:orderId>ORD-1024</ord:orderId>
    </ord:GetOrderRequest>
    """;

String responseXml = """
    <ord:GetOrderResponse xmlns:ord="urn:example:orders:v1">
        <ord:orderId>ORD-1024</ord:orderId>
        <ord:status>CONFIRMED</ord:status>
    </ord:GetOrderResponse>
    """;

MockWebServiceClient client =
        MockWebServiceClient.createClient(applicationContext);

client.sendRequest(withPayload(new StringSource(requestXml)))
      .andExpect(payload(new StringSource(responseXml)));
~~~

Đoạn này minh họa lõi kiểm thử; cần `applicationContext` test và service stub/fixture trả đúng `CONFIRMED`. Java text block yêu cầu Java phù hợp (Java 15+). Kiểm thử nên dùng cấu hình endpoint thực tế, không đăng ký đồng thời hai handler trùng `@PayloadRoot`.

Với XML, một số công cụ so sánh theo cây/namespace sẽ bớt nhạy cảm với format/prefix. Không nên chỉ so byte-by-byte vì hai XML dùng prefix khác nhau nhưng cùng namespace URI có thể tương đương về QName.

### 13.2. Ma trận tình huống phải kiểm thử

| Nhóm | Tình huống | Điều cần khẳng định |
| --- | --- | --- |
| JAXB happy path | Request hợp lệ | JAXB fields đúng, service được gọi, response hợp XSD |
| XML Source happy path | Cùng payload hợp lệ | XML adapter đọc đúng QName/orderId; response đúng |
| Prefix khác nhau | `ord` đổi thành `o`, URI giữ nguyên | Cả hai cách nhận vẫn hoạt động |
| Sai namespace | URI đổi sang v2 | Endpoint v1 không dispatch như request hợp lệ hoặc validator từ chối |
| Thiếu trường bắt buộc | Không có `orderId` | Schema validation/Fault được xử lý đúng |
| Có phần tử lạ | Thêm node không được XSD cho phép | Không âm thầm tin payload chỉ vì đọc được orderId |
| SOAP Header bổ sung | Correlation ID trong Header | Không bị nhầm thành field JAXB Body |
| SOAP Fault | ID sai/không tồn tại | Fault đúng phiên bản SOAP và policy |
| Dữ liệu đặc biệt | Ký tự `&amp;`, Unicode, text rỗng | Marshal/DOM không làm hỏng XML |
| Payload lớn | XML lớn/độ sâu cao | Bị giới hạn hoặc xử lý an toàn, không OOM |
| Bảo mật | WS-Security token/chữ ký sai | Bị từ chối trước khi tin dữ liệu nghiệp vụ |
| Client độc lập | Java/.NET/ESB từ WSDL công bố | SOAP request/response tương thích |

### 13.3. Kiểm thử phía SOAP client

`MockWebServiceServer` giúp kiểm tra `WebServiceTemplate` hoặc SOAP client Spring-WS có tạo đúng XML/headers, xử lý response/Fault phù hợp. Nó không tương đương `MockWebServiceClient` (kiểm tra endpoint server).

Kiểm thử tích hợp ngoài mock vẫn cần thiết khi môi trường có reverse proxy, TLS/mTLS, chứng chỉ, timestamp WS-Security, policy gateway hoặc WSDL/XSD được công bố động.

## 14. Những lỗi thiết kế và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Endpoint không được gọi | QName root sai hoặc `@PayloadRoot` không khớp | Namespace URI + local name của SOAP Body |
| Có hai endpoint cùng nhận `GetOrderRequest` | Trùng endpoint mapping | Chỉ đăng ký một handler cho QName hoặc đổi mapping có chủ đích |
| JAXB unmarshal lỗi nhưng XML nhìn “đúng” | Sai namespace phần tử con, `xs:sequence`, enum, javax/jakarta | XSD validation, JAXB runtime/toolchain |
| `ClassCastException` từ `Source` | Giả định luôn là `DOMSource` | Dùng API `Source` hoặc transform an toàn |
| XJC sinh type không có `@XmlRootElement` | Global element trỏ tới named complex type | Kiểm tra `ObjectFactory`/`JAXBElement` |
| Response bị lồng hai Envelope | Trả cả SOAP Envelope trong `@ResponsePayload` | Chỉ trả root payload, để SOAP stack đóng Envelope |
| XML response thiếu namespace con | Dựng DOM bằng `createElement` thay vì `createElementNS` | QName của từng node, XSD validation |
| JAXB bỏ trường bắt buộc | Validation không bật, giá trị Java null | Validate outbound XML theo XSD |
| Client ngoài không gọi được dù endpoint chạy local | `soap:address`/proxy đường dẫn sai | WSDL URL public, binding/endpoint mapping |
| Chữ ký SOAP invalid sau biến đổi XML | Sửa vùng XML đã ký | Thứ tự WS-Security/transform |
| Lỗi bảo mật XML | Parser đọc DTD/entity ngoài hoặc thiếu giới hạn | XML parser/message factory hardening, quotas |
| Fault khác kỳ vọng | Resolver map exception sai hoặc proxy thay body | SOAP version, faultcode/detail, HTTP transport |

### Quy trình tìm lỗi theo từng tầng

~~~mermaid
flowchart TD
    A["SOAP client gửi request"] --> B{"Đến được Spring-WS?"}
    B -->|Không| C["Kiểm tra URL, proxy, TLS/mTLS"]
    B -->|Có| D{"Root QName khớp endpoint?"}
    D -->|Không| E["Kiểm tra WSDL/XSD, @PayloadRoot"]
    D -->|Có| F{"XML hợp XSD?"}
    F -->|Không| G["Validation + SOAP Fault"]
    F -->|Có| H{"Binding JAXB hoặc XML Source đọc đúng?"}
    H -->|Không| I["Kiểm tra method processor, parser, namespace"]
    H -->|Có| J{"Nghiệp vụ trả kết quả đúng?"}
    J -->|Không| K["Kiểm tra domain service"]
    J -->|Có| L["Validate SOAP response + security + client"]
~~~

Phân tầng như vậy tránh việc sửa generated JAXB classes để giải quyết lỗi thực tế nằm ở reverse proxy hoặc interceptor, và tránh nới lỏng XML validation khi vấn đề là thiếu binding configuration.

## 15. Bài thực hành: hai phương án cho một hợp đồng

Với `orders.xsd` ở phần 2, hãy thử các bước sau trong một ứng dụng Spring-WS:

1. Dùng XJC sinh `GetOrderRequest`, `GetOrderResponse` và `OrderStatusType`, kiểm tra `@XmlRootElement`/`ObjectFactory` thực tế.
2. Tạo **phương án JAXB** dùng `@RequestPayload GetOrderRequest` và `@ResponsePayload GetOrderResponse`. Cho service giả lập trả `CONFIRMED`.
3. Tạo **phương án XML** dùng `@RequestPayload Source` và `@ResponsePayload Source`; đọc `orderId` theo namespace rồi trả `DOMSource`.
4. **Chỉ bật một phương án mỗi lần chạy** vì cả hai map cùng root QName. Dùng cùng một SOAP request mẫu để so sánh output.
5. Đổi prefix `ord` thành `x` nhưng giữ namespace URI. Chứng minh cả hai phương án vẫn nhận ra root và field.
6. Đổi namespace URI từ v1 sang v2; xác định lỗi xuất hiện ở endpoint mapping, validation hay JAXB/DOM adapter.
7. Bỏ `orderId`, thêm một node lạ, hoặc đảo thứ tự response. Bật schema validation để kiểm tra rằng XML handler không thể lách XSD.
8. Gửi SOAP Header có correlation ID và giải thích vì sao nó không xuất hiện trong `GetOrderRequest` JAXB hoặc `Source` của Body.
9. Tạo một lỗi nghiệp vụ có kiểm soát và ánh xạ thành SOAP Fault, kiểm tra cả SOAP 1.1 và SOAP 1.2 theo hợp đồng thực tế.
10. Thử input chứa nhiều node hoặc XML lớn. So sánh chi phí bộ nhớ của DOM với JAXB model và lựa chọn streaming khi cần.
11. Nếu dịch vụ dùng WS-Security, xác minh chữ ký/timestamp bằng interceptor rồi thử biến đổi một phần XML đã ký. Giải thích tác động.
12. Dùng `MockWebServiceClient` và một SOAP client độc lập từ WSDL để kiểm thử tính tương thích của cả hai phương án.

## 16. Nguyên tắc lựa chọn trong dự án doanh nghiệp

**Chọn JAXB** khi có XSD rõ, thông điệp ổn định và muốn endpoint tập trung vào nghiệp vụ, kiểm tra kiểu dữ liệu với model Java. **Chọn XML trực tiếp** khi cần cấu trúc đặc thù, xử lý phần mở rộng hoặc transformation; khi đó cần ranh giới XML adapter rõ ràng, parser/transformer an toàn và validation đầy đủ.

Trước khi đưa endpoint vào production, luôn kiểm tra năm điều:

1. **Contract:** XML request/response thật khớp QName, XSD và WSDL.
2. **Binding:** kiểu tham số/trả về được endpoint adapter hỗ trợ; `javax`/`jakarta` và JAXB toolchain nhất quán.
3. **Validation:** request và response được kiểm tra theo hợp đồng cùng quy tắc nghiệp vụ; lỗi được trả thành SOAP Fault phù hợp.
4. **Security:** SOAP header, WS-Security, chứng chỉ, TLS/mTLS và XML parser được xử lý tại đúng tầng, không tin input trước khi xác minh.
5. **Interoperability:** kiểm thử bằng client thực tế, không chỉ gọi trực tiếp method Java hoặc test happy path.

**Kết luận:** `@RequestPayload` trong Spring-WS có thể đưa SOAP Body vào endpoint dưới dạng **JAXB object** hoặc **XML trực tiếp** như `Source`, tùy method processor và cấu hình. JAXB giúp code có kiểu mạnh và tách biệt khỏi chi tiết XML; `Source`/DOM cho phép kiểm soát cây XML khi thực sự cần. Dù chọn hướng nào, **XSD/WSDL vẫn là hợp đồng**, `@PayloadRoot` vẫn cần đúng QName, response phải là payload hợp lệ và bảo mật/kiểm thử SOAP vẫn bắt buộc. Giữ rõ các ranh giới này giúp tích hợp **SPRING_WEB_SERVICES** ổn định, dễ bảo trì và tương thích giữa các hệ thống doanh nghiệp.
