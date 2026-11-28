# Đọc, tạo payload bằng DOM và quản lý namespace

## 1. DOM nằm ở đâu trong dịch vụ SOAP contract-first?

Trong Spring Web Services (Spring-WS), một dịch vụ SOAP thường được xây theo hướng **contract-first**: XSD mô tả kiểu dữ liệu và phần tử XML, WSDL mô tả các operation và binding, còn Java endpoint nhận request và tạo response phù hợp hợp đồng. JAXB/OXM thường là cách tiện lợi để chuyển giữa XML và Java object, nhưng một số tình huống cần đọc hoặc tạo XML trực tiếp.

**DOM (Document Object Model)** là API biểu diễn XML thành cây node trong bộ nhớ. Nó phù hợp khi endpoint chỉ cần truy cập vài element, khi cần xử lý các phần mở rộng XML, hoặc khi tích hợp với một thư viện nhận `org.w3c.dom.Element`/`Document` thay vì JAXB object. DOM cho phép kiểm soát rõ tên phần tử, namespace, attributes và thứ tự các node được tạo.

Tuy vậy, DOM cũng dễ gây lỗi nếu người viết:

- So sánh tên theo prefix như `ord:orderId` thay vì QName.
- Tạo phần tử bằng `createElement` thay cho `createElementNS`.
- Lấy nhầm phần tử ở nhánh con sâu bằng `getElementsByTagNameNS`.
- Coi XML parse được là XML đã hợp lệ theo XSD.
- Bỏ qua XXE, DTD, giới hạn kích thước và các yêu cầu WS-Security.
- Sửa thông điệp đã được ký XML mà không xét đến canonicalization và chữ ký.

Bài thuộc chương **Xử lý XML trực tiếp** của module **SPRING_WEB_SERVICES**, với trọng tâm **Đọc, tạo payload bằng DOM và quản lý namespace**. Trong quá trình học, ta dùng hợp đồng `GetOrder` làm ví dụ xuyên suốt và kết nối với Spring-WS endpoint, SOAP Fault, JAXB và kiểm thử tương thích giữa các hệ thống doanh nghiệp.

Sau bài học, bạn có thể đọc DOM bằng parser an toàn, chọn node đúng QName, tạo XML đúng namespace, gắn DOM vào SOAP endpoint, validate XSD và thiết kế test cho prefix, default namespace, nil, attribute, bảo mật và interoperability.

## 2. Phân biệt SOAP Envelope và payload

SOAP 1.1 request:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1">
    <soap:Header/>
    <soap:Body>
        <ord:GetOrderRequest correlationId="REQ-2026-001">
            <ord:orderId>ORD-2048</ord:orderId>
            <ord:includeHistory>true</ord:includeHistory>
        </ord:GetOrderRequest>
    </soap:Body>
</soap:Envelope>
~~~

Các namespace có vai trò khác nhau:

| Thành phần | Namespace URI | Chức năng |
|---|---|---|
| `Envelope`, `Header`, `Body` | `http://schemas.xmlsoap.org/soap/envelope/` | Cấu trúc SOAP 1.1 |
| `GetOrderRequest`, `orderId` | `urn:example:orders:v1` | Hợp đồng nghiệp vụ |
| `correlationId` không prefix | Không có namespace | Attribute unqualified theo XSD minh họa |

SOAP 1.2 có Envelope namespace `http://www.w3.org/2003/05/soap-envelope`; không được nhầm namespace giao thức này với namespace dữ liệu nghiệp vụ.

Trong Spring-WS, `MessageDispatcherServlet` và SOAP message factory xử lý Envelope. Với một method `@Endpoint` dùng `@RequestPayload Element`, tham số thường là **phần tử payload gốc** `GetOrderRequest` chứ không phải `soap:Envelope`. Nếu cần SOAP Header, hãy dùng API `SoapMessage`/`MessageContext` hoặc interceptor phù hợp, không cố tìm `soap:Header` trong cây payload.

~~~mermaid
flowchart TD
    A["HTTP SOAP request"] --> B["MessageDispatcherServlet"]
    B --> C["SOAP Envelope / Header / Body"]
    C --> D["Payload QName"]
    D --> E["Spring-WS @PayloadRoot"]
    E --> F["@RequestPayload Element"]
    F --> G["DOM đọc field"]
    G --> H["Application service"]
    H --> I["DOM tạo response payload"]
    I --> J["SOAP Body response"]
~~~

Điểm cốt lõi: **DOM xử lý cây XML**, còn **Spring-WS chịu trách nhiệm đặt cây payload vào SOAP Envelope**. Hai lớp này cần được kiểm thử riêng.

## 3. Các đối tượng DOM cần biết

| API | Vai trò | Lưu ý |
|---|---|---|
| `Document` | Tài liệu XML | Có một document element |
| `Element` | Phần tử XML | Có namespace URI, local name, attributes |
| `Node` | Kiểu cơ sở | Có thể là element, text, comment, CDATA... |
| `NodeList` | Tập node | Có thể gồm các descendant nodes hoặc các loại node khác |
| `Attr` | Attribute | QName riêng, không phải element con |
| `DocumentBuilderFactory` | Tạo cấu hình DOM parser | Bật namespace-aware và bảo mật |
| `DocumentBuilder` | Parse XML, tạo `Document` mới | Không chia sẻ giữa threads nếu không được bảo đảm |
| `DOMSource` | Biểu diễn DOM theo `Source` | Tương thích JAXP và một số API Spring-WS |
| `Transformer` | Serialize/biến đổi XML | Cần cấu hình an toàn |
| `QName` | Namespace URI + local name | Định danh XML độc lập prefix |

Cây payload minh họa:

~~~text
Document
└── Element {urn:example:orders:v1}GetOrderRequest
    ├── Attr {}correlationId = "REQ-2026-001"
    ├── Text (whitespace)
    ├── Element {urn:example:orders:v1}orderId
    │   └── Text "ORD-2048"
    ├── Text (whitespace)
    └── Element {urn:example:orders:v1}includeHistory
        └── Text "true"
~~~

Các ký tự xuống dòng hoặc thụt đầu dòng trong XML có thể xuất hiện dưới dạng `Text` nodes. Vì vậy, `getFirstChild()` không nhất thiết trả một `Element`; hãy luôn xét `getNodeType()` khi duyệt.

## 4. Namespace và QName: điều cần nắm trước khi viết Java

Một QName là cặp:

~~~text
QName = {namespace URI}local name
~~~

Hai XML dưới đây là cùng một global element:

~~~xml
<ord:GetOrderRequest xmlns:ord="urn:example:orders:v1"/>
~~~

~~~xml
<x:GetOrderRequest xmlns:x="urn:example:orders:v1"/>
~~~

Cả hai có QName `{urn:example:orders:v1}GetOrderRequest`. Prefix `ord` và `x` chỉ là cách viết.

Một document khác sử dụng default namespace:

~~~xml
<GetOrderRequest xmlns="urn:example:orders:v1">
    <orderId>ORD-2048</orderId>
</GetOrderRequest>
~~~

vẫn có root QName và child QName thuộc namespace v1. Prefix có thể null nhưng namespace URI không null.

### 4.1. So QName, không so getNodeName theo prefix

**Dễ sai:**

~~~java
if ("ord:GetOrderRequest".equals(root.getNodeName())) {
    // Phụ thuộc vào prefix ord trong tài liệu nguồn.
}
~~~

**Đúng hơn:**

~~~java
private static final String ORDERS_NS =
    "urn:example:orders:v1";

boolean matches =
    ORDERS_NS.equals(root.getNamespaceURI())
    && "GetOrderRequest".equals(root.getLocalName());
~~~

Cách này chấp nhận cả `ord:`, `x:` và default namespace với cùng URI, nhưng không âm thầm chấp nhận `urn:example:orders:v2`.

### 4.2. Default namespace không tự áp dụng cho attribute không prefix

Ví dụ:

~~~xml
<GetOrderRequest
    xmlns="urn:example:orders:v1"
    correlationId="REQ-2026-001"/>
~~~

- Element `GetOrderRequest` thuộc namespace v1.
- Attribute `correlationId` **không có namespace**.

Để đọc:

~~~java
String correlationId =
    root.getAttribute("correlationId");
~~~

Nếu attribute được khai báo có namespace, ví dụ `ord:messageType`, phải dùng `getAttributeNS(ORDERS_NS, "messageType")`. XSD quyết định attribute qualified hay unqualified thông qua `attributeFormDefault` và `form`.

Namespace URI không nhất thiết là URL đang phục vụ file XSD. Một tài liệu có thể tải từ `https://api.example.test/ws/orders-v1.xsd` nhưng khai báo `targetNamespace="urn:example:orders:v1"`. Đừng đổi namespace chỉ vì chuyển máy chủ hoặc URL metadata.

## 5. XSD contract-first cho GetOrder

Ví dụ XSD độc lập:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:ord="urn:example:orders:v1"
    targetNamespace="urn:example:orders:v1"
    elementFormDefault="qualified"
    attributeFormDefault="unqualified">

    <xs:element name="GetOrderRequest">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="orderId">
                    <xs:simpleType>
                        <xs:restriction base="xs:string">
                            <xs:minLength value="1"/>
                        </xs:restriction>
                    </xs:simpleType>
                </xs:element>
                <xs:element name="includeHistory"
                            type="xs:boolean"
                            minOccurs="0"/>
            </xs:sequence>
            <xs:attribute name="correlationId"
                          type="xs:string"
                          use="required"/>
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

Theo XSD:

- Request root là `{urn:example:orders:v1}GetOrderRequest`.
- `orderId` bắt buộc và có ít nhất một ký tự.
- `includeHistory` optional nhưng nếu xuất hiện phải là `xs:boolean`.
- `correlationId` là attribute required, unqualified.
- Response root là `GetOrderResponse`, với child `orderId` đứng trước `status`.
- Tất cả các child elements trong ví dụ thuộc namespace v1 vì `elementFormDefault="qualified"`.

**DOM cho phép tạo một cây bất kỳ dù nó sai XSD.** Do đó, tạo đúng node và validate schema là hai công việc riêng.

## 6. Parse XML thành DOM theo namespace

Để phân tích XML từ string:

~~~java
import java.io.StringReader;

import javax.xml.parsers.DocumentBuilderFactory;

import org.w3c.dom.Document;
import org.xml.sax.InputSource;

DocumentBuilderFactory factory =
    DocumentBuilderFactory.newInstance();

factory.setNamespaceAware(true);

Document document =
    factory.newDocumentBuilder().parse(
        new InputSource(new StringReader(xml))
    );
~~~

`setNamespaceAware(true)` rất quan trọng: nó giúp DOM lưu `namespaceURI` và `localName` đúng nghĩa. Tuy nhiên, đoạn trên **chưa phải cấu hình an toàn** cho dữ liệu đầu vào không tin cậy.

### 6.1. Parser DOM an toàn: chặn DTD và external entities

Một helper minh họa:

~~~java
import java.io.StringReader;

import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;

import org.w3c.dom.Document;
import org.xml.sax.InputSource;

public final class SafeDomReader {

    private SafeDomReader() {
    }

    public static Document parse(String xml) throws Exception {
        DocumentBuilderFactory factory =
            DocumentBuilderFactory.newInstance();

        factory.setNamespaceAware(true);
        factory.setFeature(
            XMLConstants.FEATURE_SECURE_PROCESSING,
            true
        );

        factory.setFeature(
            "http://apache.org/xml/features/disallow-doctype-decl",
            true
        );

        factory.setFeature(
            "http://xml.org/sax/features/external-general-entities",
            false
        );

        factory.setFeature(
            "http://xml.org/sax/features/external-parameter-entities",
            false
        );

        factory.setXIncludeAware(false);
        factory.setExpandEntityReferences(false);

        factory.setAttribute(
            XMLConstants.ACCESS_EXTERNAL_DTD,
            ""
        );

        factory.setAttribute(
            XMLConstants.ACCESS_EXTERNAL_SCHEMA,
            ""
        );

        DocumentBuilder builder = factory.newDocumentBuilder();

        return builder.parse(
            new InputSource(new StringReader(xml))
        );
    }
}
~~~

Các nguyên tắc bảo mật:

1. Cấm DOCTYPE và external entities nếu hợp đồng không cần chúng. Điều này giảm nguy cơ XXE và entity expansion.
2. `setExpandEntityReferences(false)` không thay thế các cơ chế khóa entity khác.
3. Một số XML parser/provider có thể không hỗ trợ feature/attribute ở trên. Khi chính sách an toàn không thể áp dụng, cần **fail closed**, không lặng lẽ parse bằng factory mặc định.
4. Ngoài XXE, còn cần giới hạn kích thước request, độ sâu XML, số node, timeout và concurrency.
5. Các công cụ khác trong pipeline như SOAP message factory, Transformer và SchemaFactory cũng phải được cấu hình an toàn riêng.

Khi dùng `@RequestPayload Element` trong Spring-WS, framework thường đã xử lý việc đọc SOAP request trước khi đưa Element vào method. Không cần parse lại toàn bộ Envelope chỉ để lấy root payload. Helper trên phù hợp khi ứng dụng chủ động đọc một XML string hoặc file.

### 6.2. Kiểm tra root QName

~~~java
import org.w3c.dom.Element;

Document document = SafeDomReader.parse(xml);
Element root = document.getDocumentElement();

if (root == null) {
    throw new IllegalArgumentException(
        "XML không có root element"
    );
}

boolean correctRoot =
    "urn:example:orders:v1".equals(root.getNamespaceURI())
    && "GetOrderRequest".equals(root.getLocalName());

if (!correctRoot) {
    throw new IllegalArgumentException(
        "Payload root QName không đúng hợp đồng"
    );
}
~~~

Khi request được xử lý bởi `@PayloadRoot`, Spring-WS cũng dùng QName payload để dispatch. Nhưng việc biết cách kiểm tra QName trực tiếp vẫn quan trọng với XML adapter, gateway hoặc các luồng DOM không qua endpoint mapping.

## 7. Duyệt node con: tránh chọn nhầm descendant

DOM có:

~~~java
NodeList matches = root.getElementsByTagNameNS(
    "urn:example:orders:v1",
    "orderId"
);
~~~

API này tìm các **descendant elements** phù hợp, không giới hạn ở direct children. Nếu XML có một `orderId` lồng trong `filter` và một `orderId` trực tiếp dưới request, lấy `matches.item(0)` có thể sai ngữ nghĩa. Các ví dụ có `filter` chỉ hợp XSD nếu schema có khai báo phần tử đó; mục đích ở đây là phân biệt cách duyệt DOM.

### 7.1. Helper tìm direct child bằng QName

~~~java
import org.w3c.dom.Element;
import org.w3c.dom.Node;

public final class DomFields {

    private DomFields() {
    }

    public static Element directChild(
            Element parent,
            String namespaceUri,
            String localName) {

        for (Node node = parent.getFirstChild();
             node != null;
             node = node.getNextSibling()) {

            if (node.getNodeType() != Node.ELEMENT_NODE) {
                continue;
            }

            Element child = (Element) node;

            if (namespaceUri.equals(child.getNamespaceURI())
                    && localName.equals(child.getLocalName())) {
                return child;
            }
        }

        return null;
    }

    public static Element requiredChild(
            Element parent,
            String namespaceUri,
            String localName) {

        Element found = directChild(
            parent,
            namespaceUri,
            localName
        );

        if (found == null) {
            throw new IllegalArgumentException(
                "Thiếu field bắt buộc: " + localName
            );
        }

        return found;
    }
}
~~~

Sử dụng:

~~~java
Element orderId = DomFields.requiredChild(
    root,
    "urn:example:orders:v1",
    "orderId"
);

String orderIdValue = orderId.getTextContent();
~~~

Helper này chỉ chọn **phần tử đầu tiên có QName khớp**. Nó chưa kiểm tra số lần xuất hiện, thứ tự `xs:sequence` hoặc kiểu dữ liệu. XSD validation phải kiểm tra tính hợp lệ của toàn bộ payload.

### 7.2. getTextContent không chỉ trả direct text node

Với `<ord:orderId>ORD-2048</ord:orderId>`, `getTextContent()` hữu ích vì XSD định nghĩa nội dung kiểu đơn. Nhưng với phần tử có nested elements hoặc mixed content, phương thức có thể ghép text của descendants và làm mất cấu trúc. Đừng dùng nó để lấy một object phức tạp rồi tưởng rằng đã bảo toàn tất cả dữ liệu XML.

Không tự động `trim()` mọi giá trị. `xs:string` và `xs:token` có quy tắc whitespace khác nhau; tự trim không đúng hợp đồng có thể làm thay đổi dữ liệu người dùng.

## 8. Đọc attribute đúng namespace và phân biệt thiếu/rỗng

Trong XSD ví dụ, `correlationId` là unqualified attribute:

~~~xml
<ord:GetOrderRequest
    xmlns:ord="urn:example:orders:v1"
    correlationId="REQ-2026-001">
    <ord:orderId>ORD-2048</ord:orderId>
</ord:GetOrderRequest>
~~~

Lấy giá trị:

~~~java
String correlationId =
    root.getAttribute("correlationId");
~~~

Nhưng `getAttribute` trả `""` khi attribute không có mặt, cũng giống một attribute có mặt với value rỗng. Muốn phân biệt:

~~~java
if (!root.hasAttribute("correlationId")) {
    throw new IllegalArgumentException(
        "Thiếu correlationId"
    );
}

String correlationId = root.getAttribute("correlationId");
~~~

Đối với qualified attribute, dùng `hasAttributeNS(namespaceUri, localName)` và `getAttributeNS(namespaceUri, localName)`.

Lưu ý `xmlns:ord` là khai báo namespace, thuộc `XMLConstants.XMLNS_ATTRIBUTE_NS_URI`. Nó không phải attribute nghiệp vụ thông thường. Khi đếm attribute để kiểm tra hợp đồng, không được coi mọi namespace declaration là field nghiệp vụ.

## 9. DOM trả chuỗi; kiểu XSD cần được chuyển đổi đúng

### 9.1. xs:boolean khác Boolean.parseBoolean

XSD cho phép `xs:boolean` với lexical values `true`, `false`, `1` và `0`. Tuy nhiên:

~~~java
Boolean.parseBoolean("1")  // false
~~~

Vì Java không coi `"1"` là true. Một helper cho text đã được XSD validate:

~~~java
public static boolean parseXsdBoolean(String value) {
    return switch (value) {
        case "true", "1" -> true;
        case "false", "0" -> false;
        default -> throw new IllegalArgumentException(
            "Giá trị xs:boolean không hợp lệ"
        );
    };
}
~~~

Nếu schema/adapter yêu cầu whitespace normalization, hãy xử lý theo datatype thật sự. Không nới lỏng bằng cách chấp nhận mọi chuỗi khác `true` là false.

### 9.2. Dùng BigDecimal cho xs:decimal

Với tiền tệ:

~~~java
BigDecimal amount =
    new BigDecimal(amountElement.getTextContent());
~~~

Tránh chuyển qua `double` khi cần độ chính xác thập phân. DOM không tự kiểm tra `totalDigits`, `fractionDigits`, min/max; phải validate XSD và business constraints.

### 9.3. xs:dateTime và offset

Một element `xs:dateTime` có thể chứa offset như `2026-11-27T09:30:00+07:00` hoặc có thể không chứa timezone tùy giá trị hợp lệ. DOM giữ lexical text; nếu đổi sang `Instant`, `OffsetDateTime` hay `XMLGregorianCalendar` cần chính sách rõ cho offset, precision và trường hợp thiếu timezone. Không âm thầm giả định mọi ngày giờ là UTC.

## 10. Phân biệt absent, empty và xsi:nil

Một request cập nhật có thể khai báo:

~~~xml
<xs:element name="deliveryNote"
            type="xs:string"
            minOccurs="0"
            nillable="true"/>
~~~

Ba thông điệp mang ý nghĩa khác nhau:

**Element vắng mặt:**

~~~xml
<!-- Không có deliveryNote -->
~~~

**Element có mặt và rỗng:**

~~~xml
<ord:deliveryNote xmlns:ord="urn:example:orders:v1"/>
~~~

**Element có mặt với nil:**

~~~xml
<ord:deliveryNote
    xmlns:ord="urn:example:orders:v1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:nil="true"/>
~~~

Ví dụ đọc DOM:

~~~java
import javax.xml.XMLConstants;
import org.w3c.dom.Element;

Element note = DomFields.directChild(
    requestRoot,
    ORDERS_NS,
    "deliveryNote"
);

if (note == null) {
    // Element vắng mặt.
} else {
    String nilText = note.getAttributeNS(
        XMLConstants.W3C_XML_SCHEMA_INSTANCE_NS_URI,
        "nil"
    );

    boolean isNil =
        "true".equals(nilText) || "1".equals(nilText);

    if (isNil) {
        // Element hiện diện và được đánh dấu nil.
    } else {
        String value = note.getTextContent();
        // Có thể là "" hoặc chuỗi có dữ liệu.
    }
}
~~~

Trong ví dụ, `ORDERS_NS` đại diện hằng `urn:example:orders:v1`. XSD validation cần kiểm tra rằng element được phép nil và không có nội dung không hợp lệ khi `xsi:nil` là true.

Đừng dùng `getTextContent().isEmpty()` để kết luận một element là nil: empty text và nil là hai trạng thái khác nhau. Trong nghiệp vụ cập nhật, có thể quy định absent = giữ nguyên, nil = xóa, empty = đặt chuỗi rỗng. Đây là **quy tắc nghiệp vụ của hợp đồng**, không phải ý nghĩa tự động do DOM áp đặt.

## 11. Tạo Document và phần tử XML đúng namespace

Tạo một tài liệu DOM mới:

~~~java
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Document;

DocumentBuilderFactory factory =
    DocumentBuilderFactory.newInstance();

factory.setNamespaceAware(true);

Document document =
    factory.newDocumentBuilder().newDocument();
~~~

Vì `newDocument()` chỉ tạo Document rỗng, nó không parse XML từ nguồn không tin cậy. Điều này không miễn yêu cầu an toàn cho các bước parse/import/transform khác của pipeline.

### 11.1. Vì sao createElement có thể tạo QName sai?

Sai nếu hợp đồng yêu cầu namespace v1:

~~~java
Element response =
    document.createElement("GetOrderResponse");
~~~

Node có local name nhìn đúng, nhưng **không được gắn namespace URI v1**. Client kiểm tra theo XSD có thể từ chối `{}GetOrderResponse` thay vì `{urn:example:orders:v1}GetOrderResponse`.

Đúng:

~~~java
String ordersNs = "urn:example:orders:v1";

Element response = document.createElementNS(
    ordersNs,
    "ord:GetOrderResponse"
);
~~~

Tạo children đúng QName:

~~~java
Element id = document.createElementNS(
    ordersNs,
    "ord:orderId"
);

id.setTextContent("ORD-2048");

Element status = document.createElementNS(
    ordersNs,
    "ord:status"
);

status.setTextContent("PAID");
~~~

### 11.2. Khai báo namespace rõ ràng

Nếu dùng prefix `ord`, có thể khai báo:

~~~java
import javax.xml.XMLConstants;

response.setAttributeNS(
    XMLConstants.XMLNS_ATTRIBUTE_NS_URI,
    "xmlns:ord",
    ordersNs
);
~~~

Cũng có thể tạo phần tử bằng default namespace:

~~~java
Element response = document.createElementNS(
    ordersNs,
    "GetOrderResponse"
);

response.setAttributeNS(
    XMLConstants.XMLNS_ATTRIBUTE_NS_URI,
    "xmlns",
    ordersNs
);
~~~

Hai cách có thể cho cùng QName root. Việc chọn prefix chỉ ảnh hưởng cách serialize, không thay hợp đồng nếu URI và local name đúng.

### 11.3. Thứ tự appendChild phải theo xs:sequence

~~~java
document.appendChild(response);
response.appendChild(id);
response.appendChild(status);
~~~

XSD định nghĩa `orderId` rồi đến `status`. Đảo thứ tự có thể khiến response không hợp lệ dù cả hai element đều có namespace đúng.

Output mong muốn:

~~~xml
<ord:GetOrderResponse xmlns:ord="urn:example:orders:v1">
    <ord:orderId>ORD-2048</ord:orderId>
    <ord:status>PAID</ord:status>
</ord:GetOrderResponse>
~~~

Nếu cần tạo unqualified attribute:

~~~java
response.setAttribute("correlationId", "REQ-2026-001");
~~~

Nếu cần qualified attribute:

~~~java
response.setAttributeNS(
    ordersNs,
    "ord:messageType",
    "STATUS"
);
~~~

Nhưng **chỉ thêm attribute nếu XSD response có khai báo**. Có namespace đúng vẫn chưa bảo đảm XSD validity.

## 12. Nhập node từ Document khác và giữ đúng owner document

Một DOM node có `ownerDocument`. Nếu bạn đọc dữ liệu từ XML tài liệu A rồi muốn sao chép một nhánh sang tài liệu response B, không nên tự ý `appendChild` node từ tài liệu A vào B: DOM có thể ném `WRONG_DOCUMENT_ERR`.

Dùng `importNode` khi muốn sao chép:

~~~java
import org.w3c.dom.Node;

Node copied = responseDocument.importNode(
    sourceElement,
    true
);

responseParent.appendChild(copied);
~~~

Tham số `true` yêu cầu import sâu, gồm các child nodes. Nếu muốn chuyển quyền sở hữu node thay vì sao chép, DOM có `adoptNode` nhưng cần hiểu hành vi implementation và trạng thái node.

**Cẩn trọng:** Sao chép một fragment XML từ request vào response không bảo đảm fragment đó hợp XSD response. Phải kiểm tra namespace, thứ tự, số lần xuất hiện, attributes và những giá trị không được phép phản hồi cho đối tác. Không copy toàn bộ request chỉ để tiết kiệm code tạo response.

Không tự động sửa prefix bằng tìm-thay text như `replace("ord:", "x:")`. Nếu cần thay prefix/namespace, sử dụng DOM namespace APIs và xác nhận QName sau thao tác. Với XML đã ký bằng WS-Security, việc sửa nội dung hoặc namespace declarations có thể làm chữ ký không còn hợp lệ.

## 13. Serialize DOM thành XML

Trong các unit test và adapter, có thể serialize DOM qua JAXP `Transformer`:

~~~java
import java.io.StringWriter;

import javax.xml.XMLConstants;
import javax.xml.transform.OutputKeys;
import javax.xml.transform.Transformer;
import javax.xml.transform.TransformerFactory;
import javax.xml.transform.dom.DOMSource;
import javax.xml.transform.stream.StreamResult;

public static String toXml(Document document)
        throws Exception {

    TransformerFactory factory =
        TransformerFactory.newInstance();

    factory.setFeature(
        XMLConstants.FEATURE_SECURE_PROCESSING,
        true
    );

    factory.setAttribute(
        XMLConstants.ACCESS_EXTERNAL_DTD,
        ""
    );

    factory.setAttribute(
        XMLConstants.ACCESS_EXTERNAL_STYLESHEET,
        ""
    );

    Transformer transformer = factory.newTransformer();

    transformer.setOutputProperty(
        OutputKeys.OMIT_XML_DECLARATION,
        "yes"
    );

    StringWriter writer = new StringWriter();

    transformer.transform(
        new DOMSource(document),
        new StreamResult(writer)
    );

    return writer.toString();
}
~~~

Ở đây `newTransformer()` tạo **identity transformer**, dùng để ghi cây DOM ra text. Khi áp dụng vào hệ thống thật, cần bảo đảm XML provider hỗ trợ các thuộc tính bảo mật; nếu không, phải fail closed hoặc dùng provider/cơ chế khác phù hợp chính sách.

### 13.1. Vì sao không so XML từng byte?

Hai output:

~~~xml
<ord:GetOrderResponse xmlns:ord="urn:example:orders:v1">
    <ord:orderId>ORD-2048</ord:orderId>
</ord:GetOrderResponse>
~~~

và:

~~~xml
<x:GetOrderResponse xmlns:x="urn:example:orders:v1">
    <x:orderId>ORD-2048</x:orderId>
</x:GetOrderResponse>
~~~

có QName giống nhau. Prefix, thứ tự attributes, whitespace dùng để indent, cách viết empty element và các namespace declarations có thể khác mà XML vẫn hợp hợp đồng.

Trong test, nên parse output bằng namespace-aware parser, kiểm tra các QName, giá trị và validate XSD. **Không dùng phép so chuỗi byte-for-byte thay thế cho so ngữ nghĩa XML.** Nếu message có chữ ký XML, việc kiểm tra canonicalization/chữ ký là một bài toán riêng, không được suy ra từ việc business fields giống nhau.

### 13.2. Tránh XML injection khi tạo text

Nếu status hoặc note chứa:

~~~text
PAID & CLOSED
~~~

thì:

~~~java
statusElement.setTextContent("PAID & CLOSED");
~~~

giúp serializer escape `&` thành dạng XML hợp lệ như `&amp;`. Không tạo XML bằng cách nối raw input:

~~~java
// Dễ sai và có thể tạo markup không mong muốn.
String output =
    "<ord:status>" + userSuppliedStatus + "</ord:status>";
~~~

Dù DOM giúp tránh nối markup trực tiếp, dữ liệu vẫn phải được kiểm tra theo XSD và quy tắc nghiệp vụ.

## 14. Sử dụng DOM trong Spring-WS @Endpoint

Spring-WS hỗ trợ các kiểu payload DOM trong các argument/return value processors tương ứng khi annotation endpoint infrastructure đã được kích hoạt. Với ứng dụng Java Config, cần có `@EnableWs` hoặc cấu hình tương đương và component scan chứa class `@Endpoint`.

Một endpoint đọc request DOM và trả element response:

~~~java
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.parsers.ParserConfigurationException;

import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;
import org.w3c.dom.Document;
import org.w3c.dom.Element;

@Endpoint
public class GetOrderDomEndpoint {

    private static final String NS = "urn:example:orders:v1";

    private final OrderApplicationService service;

    public GetOrderDomEndpoint(OrderApplicationService service) {
        this.service = service;
    }

    @PayloadRoot(namespace = NS, localPart = "GetOrderRequest")
    @ResponsePayload
    public Element getOrder(
            @RequestPayload Element request)
            throws ParserConfigurationException {

        Element idElement = DomFields.requiredChild(
            request,
            NS,
            "orderId"
        );

        String orderId = idElement.getTextContent();

        if (orderId.isEmpty()) {
            throw new IllegalArgumentException(
                "orderId không được rỗng"
            );
        }

        String correlationId =
            request.getAttribute("correlationId");

        String status = service.findStatus(orderId);

        DocumentBuilderFactory domFactory =
            DocumentBuilderFactory.newInstance();

        domFactory.setNamespaceAware(true);

        Document document =
            domFactory.newDocumentBuilder().newDocument();

        Element response = document.createElementNS(
            NS,
            "ord:GetOrderResponse"
        );

        response.setAttributeNS(
            XMLConstants.XMLNS_ATTRIBUTE_NS_URI,
            "xmlns:ord",
            NS
        );

        document.appendChild(response);

        Element id = document.createElementNS(
            NS,
            "ord:orderId"
        );
        id.setTextContent(orderId);

        Element state = document.createElementNS(
            NS,
            "ord:status"
        );
        state.setTextContent(status);

        response.appendChild(id);
        response.appendChild(state);

        return response;
    }
}
~~~

Ví dụ này giả định:

- Spring-WS đã đăng ký `@Endpoint` và các argument/return value processors hỗ trợ DOM `Element` trong phiên bản đang dùng.
- `OrderApplicationService` là service nghiệp vụ có phương thức `findStatus(String)`.
- XSD/WSDL công bố đúng request và response như ví dụ.
- Bean validator được cấu hình ở ranh giới SOAP nếu muốn từ chối payload sai XSD.
- Lỗi từ endpoint được ánh xạ sang SOAP Fault phù hợp; ví dụ chưa khai báo resolver.

Biến `correlationId` minh họa việc đọc attribute unqualified; mã chưa sử dụng biến đó. Trong sản phẩm, nên đưa vào correlation/logging theo chính sách hoặc bỏ phần đọc dư.

Điểm quan trọng nhất: **`@RequestPayload Element` nhận cây payload**; `@ResponsePayload Element` cho phép Spring-WS đưa element phản hồi vào SOAP Body. Trong endpoint này ta tạo Document response mới, không biến đổi request DOM tại chỗ.

### 14.1. Khi nào dùng DOMSource hoặc Source?

Một số API xử lý XML chấp nhận `javax.xml.transform.Source`:

~~~java
import javax.xml.transform.dom.DOMSource;

DOMSource source = new DOMSource(document);
~~~

Đây là cách đưa một cây DOM vào API nhận Source. Nhưng một tham số Spring-WS kiểu `Source` có thể được cung cấp dưới dạng `DOMSource`, `SAXSource` hoặc dạng khác tùy cấu hình; không ép kiểu mù quáng sang DOMSource.

Nếu cần DOM nhưng nhận Source khác DOM, có thể transform vào `DOMResult` bằng quá trình biến đổi an toàn. Điều này có thể tốn thêm bộ nhớ, vì vậy với payload lớn nên cân nhắc giải pháp streaming.

### 14.2. DOM khác JAXB ở chữ ký endpoint

Một endpoint JAXB điển hình có thể khai báo:

~~~java
@PayloadRoot(namespace = NS, localPart = "GetOrderRequest")
@ResponsePayload
public GetOrderResponse getOrder(
        @RequestPayload GetOrderRequest request) {
    // Dựa trên class JAXB sinh từ XSD.
}
~~~

Endpoint DOM dùng `Element` thay vì generated JAXB class. Trong trường hợp request phức tạp, JAXB/OXM giúp biểu diễn XSD types, lists và nil/optional một cách có cấu trúc hơn. DOM hữu ích khi cần thao tác cây XML trực tiếp hoặc không muốn chuyển cả payload sang object graph.

Không có cách nào miễn kiểm tra XSD. Nếu API response là DOM và code đặt sai QName, client vẫn từ chối dù server không gặp exception lúc tạo Document.

### 14.3. Không giả định DOM payload cho phép sửa SOAP Header

Nếu client gửi WS-Security UsernameToken, BinarySecurityToken hoặc XML Signature trong SOAP Header, việc endpoint nhận DOM payload không có nghĩa token nằm trong cây đó. Hãy dùng security interceptor hoặc SOAP message APIs để xử lý Header và xác thực/chứng chỉ theo chính sách.

Không sửa DOM request đã được ký mà không hiểu quá trình xác minh chữ ký. Nếu một gateway thật sự cần biến đổi XML, phải thiết kế rõ thứ tự xác minh/biến đổi/ký lại và các phần tử được bảo vệ.

## 15. XSD validation không được bỏ qua khi dùng DOM

DOM đọc và tạo XML tree nhưng không tự thực thi mọi quy tắc XML Schema:

- QName, minOccurs, maxOccurs.
- Thứ tự `xs:sequence`.
- Các nhánh `xs:choice`.
- Datatype `xs:boolean`, `xs:decimal`, `xs:dateTime`.
- Facets như enumeration, pattern, minLength, maxLength.
- Giá trị `xsi:nil` và khả năng nillable.
- Value constraints `default`, `fixed`.

### 15.1. Validate một Document trực tiếp bằng JAXP

Ví dụ minh họa:

~~~java
import java.io.File;

import javax.xml.XMLConstants;
import javax.xml.transform.dom.DOMSource;
import javax.xml.validation.Schema;
import javax.xml.validation.SchemaFactory;
import javax.xml.validation.Validator;

SchemaFactory factory = SchemaFactory.newInstance(
    XMLConstants.W3C_XML_SCHEMA_NS_URI
);

factory.setFeature(
    XMLConstants.FEATURE_SECURE_PROCESSING,
    true
);

factory.setProperty(
    XMLConstants.ACCESS_EXTERNAL_DTD,
    ""
);

factory.setProperty(
    XMLConstants.ACCESS_EXTERNAL_SCHEMA,
    ""
);

Schema schema = factory.newSchema(
    new File("src/main/resources/xsd/orders-v1.xsd")
);

Validator validator = schema.newValidator();
validator.validate(new DOMSource(document));
~~~

Đường dẫn File trên phù hợp minh họa trong project khi chạy từ thư mục gốc; với ứng dụng đóng gói JAR/WAR cần nạp schema qua classpath resource hoặc URI đáng tin cậy, đồng thời cấu hình `LSResourceResolver` cho import/include nếu có.

Nên tái sử dụng `Schema` theo khả năng thread-safety của API và tạo `Validator` riêng mỗi lần xử lý hoặc mỗi thread, không chia sẻ một Validator mutable giữa các request đồng thời. External schema access nên được giới hạn; không cho một nguồn XML không tin cậy tự dẫn validator đến URL/file tùy ý.

### 15.2. PayloadValidatingInterceptor ở tầng Spring-WS

Một cấu hình Java ví dụ:

~~~java
import java.util.List;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.config.annotation.WsConfigurer;
import org.springframework.ws.server.EndpointInterceptor;
import org.springframework.ws.soap.server.endpoint.interceptor.PayloadValidatingInterceptor;
import org.springframework.xml.xsd.XsdSchema;

@Configuration
@EnableWs
public class OrdersValidationConfig implements WsConfigurer {

    private final XsdSchema schema;

    public OrdersValidationConfig(
            @Qualifier("ordersSchema") XsdSchema schema) {
        this.schema = schema;
    }

    @Override
    public void addInterceptors(
            List<EndpointInterceptor> interceptors) {

        PayloadValidatingInterceptor validator =
            new PayloadValidatingInterceptor();

        validator.setXsdSchema(schema);
        validator.setValidateRequest(true);
        validator.setValidateResponse(true);

        interceptors.add(validator);
    }
}
~~~

Ví dụ giả định bean `ordersSchema` đã được đăng ký từ XSD có cả request/response, và các import/include (nếu có) được giải đúng. Validator kiểm tra cấu trúc XML trước/sau endpoint theo cấu hình, nhưng **không xác thực quyền gọi dịch vụ hoặc chữ ký WS-Security**.

Cần kiểm thử trường hợp request sai không được chuyển thành side effect nghiệp vụ. Nếu endpoint trả response DOM thiếu `status` hoặc đảo thứ tự child elements, response validation phải phát hiện thay vì gửi một message sai hợp đồng.

### 15.3. Công bố WSDL/XSD là trách nhiệm khác

`DefaultWsdl11Definition` và `XsdSchema` beans có thể công bố metadata qua `MessageDispatcherServlet`. Nhưng việc client tải được `orders.wsdl` không bảo đảm request/response được validate. Ngược lại, schema validation thành công không chứng minh client từ ngoài mạng có thể tải mọi XSD import/include.

Hãy kiểm thử cả **GET metadata** và **POST SOAP request**.

## 16. SOAP Fault và phân loại lỗi

Một endpoint DOM có thể gặp nhiều lỗi khác nhau:

| Lớp | Ví dụ | Kết quả nên thiết kế |
|---|---|---|
| XML parsing | Tag không đóng, dữ liệu không well-formed | Lỗi xử lý XML/SOAP |
| SOAP version | Envelope 1.2 đến server chỉ hỗ trợ 1.1 | Fault/HTTP response theo binding |
| XSD validation | Thiếu orderId, sai QName, sai sequence | SOAP Fault cho request không hợp đồng |
| Domain validation | Order không tồn tại hoặc người gọi không có quyền | SOAP Fault nghiệp vụ ổn định |
| Hạ tầng | Database/queue lỗi | Fault phía server/receiver, không lộ nội bộ |

SOAP 1.1 có `faultcode`, `faultstring` và `detail`. SOAP 1.2 dùng `Code`, `Reason` và `Detail`. Trong Spring-WS, `EndpointExceptionResolver` hoặc cơ chế annotation `@SoapFault` có thể ánh xạ lỗi thành Fault khi được cấu hình đúng.

Không trả HTTP 200 với một payload trông như thành công chỉ vì code đã bắt exception DOM. Cũng không đưa stack trace, SQL, file path, token hay thông tin chứng chỉ vào Fault Detail.

## 17. Kiểm thử DOM độc lập bằng JUnit

Các XML fixtures nên được viết độc lập từ XSD/WSDL. Nếu chỉ kiểm tra một XML được sinh bởi chính code tạo DOM rồi được đọc lại bởi cùng helper, cả hai phía có thể cùng mắc một lỗi namespace mà test không phát hiện.

Ví dụ JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.w3c.dom.Document;
import org.w3c.dom.Element;

class DomNamespaceTest {

    private static final String NS = "urn:example:orders:v1";

    @Test
    void prefixChangeDoesNotChangeQName() throws Exception {
        String xml = """
            <x:GetOrderRequest
                xmlns:x="urn:example:orders:v1"
                correlationId="REQ-001">
                <x:orderId>ORD-2048</x:orderId>
            </x:GetOrderRequest>
            """;

        Document doc = SafeDomReader.parse(xml);
        Element root = doc.getDocumentElement();

        assertEquals(NS, root.getNamespaceURI());
        assertEquals("GetOrderRequest", root.getLocalName());

        Element orderId = DomFields.requiredChild(
            root,
            NS,
            "orderId"
        );

        assertEquals("ORD-2048", orderId.getTextContent());
        assertEquals("REQ-001", root.getAttribute("correlationId"));
    }

    @Test
    void defaultNamespaceAlsoMatches() throws Exception {
        String xml = """
            <GetOrderRequest
                xmlns="urn:example:orders:v1"
                correlationId="REQ-002">
                <orderId>ORD-2049</orderId>
            </GetOrderRequest>
            """;

        Element root = SafeDomReader.parse(xml)
            .getDocumentElement();

        assertEquals(NS, root.getNamespaceURI());
        assertEquals("GetOrderRequest", root.getLocalName());
    }
}
~~~

Đây là ví dụ dùng lại các helper ở phần trên. Trong dự án thật cần dependency JUnit 5, cấu hình chạy test và các class helper. Nó chưa chứng minh toàn bộ request hợp XSD nếu không gọi validator; bổ sung test validation riêng.

### 17.1. So output qua QName và XSD

Đối với một response mới tạo:

~~~java
Element root = document.getDocumentElement();

assertEquals(
    "urn:example:orders:v1",
    root.getNamespaceURI()
);

assertEquals("GetOrderResponse", root.getLocalName());

Element status = DomFields.requiredChild(
    root,
    "urn:example:orders:v1",
    "status"
);

assertEquals("PAID", status.getTextContent());
~~~

Sau đó validate cả `Document` để bắt thiếu `orderId`, sai sequence, type hoặc attribute ngoài XSD. Đừng chỉ so raw XML string: serializer có quyền dùng prefix khác mà QName vẫn hợp lệ.

### 17.2. Ma trận dữ liệu biên quan trọng

| Ca | Dữ liệu | Kỳ vọng |
|---|---|---|
| N1 | Prefix ord, namespace v1 | Đọc đúng |
| N2 | Prefix x, namespace v1 | Đọc như N1 |
| N3 | Default namespace v1 | Đọc như N1 |
| N4 | Namespace v2 | Không nhận như v1 |
| N5 | orderId vắng mặt | XSD reject |
| N6 | orderId rỗng | XSD reject vì minLength 1 |
| N7 | correlationId thiếu | XSD reject |
| N8 | correlationId là attribute unqualified | `getAttribute("correlationId")` đọc đúng |
| N9 | includeHistory có value `1` | Hợp lệ theo xs:boolean |
| N10 | includeHistory không có | Hợp lệ do minOccurs 0 |
| N11 | orderId xuất hiện ở nhánh lồng sai | Không được chọn như direct child hợp lệ |
| N12 | Response root/child tạo bằng createElement | XSD reject do thiếu namespace |
| N13 | Response đảo status trước orderId | XSD reject theo sequence |
| N14 | XML có DOCTYPE/external entity | Parser an toàn từ chối/không truy cập nguồn ngoài |
| N15 | Payload quá lớn hoặc quá sâu | Bị giới hạn theo chính sách tài nguyên |

Đối với test negative, hãy kiểm tra lỗi đến từ **vi phạm hợp đồng đang thử**, không phải do thiếu file XSD hoặc cấu hình test sai.

## 18. Kiểm thử Spring-WS endpoint bằng MockWebServiceClient

`spring-ws-test` hỗ trợ gửi payload vào application context chứa endpoint mà không cần HTTP server thật:

~~~java
import static org.springframework.ws.test.server.RequestCreators.withPayload;
import static org.springframework.ws.test.server.ResponseMatchers.payload;

import org.junit.jupiter.api.Test;
import org.springframework.context.ApplicationContext;
import org.springframework.ws.test.server.MockWebServiceClient;
import org.springframework.xml.transform.StringSource;

class GetOrderEndpointTest {

    private final MockWebServiceClient client;

    GetOrderEndpointTest(ApplicationContext context) {
        client = MockWebServiceClient.createClient(context);
    }

    @Test
    void domEndpointReturnsContractResponse() {
        String request = """
            <x:GetOrderRequest
                xmlns:x="urn:example:orders:v1"
                correlationId="REQ-001">
                <x:orderId>ORD-2048</x:orderId>
            </x:GetOrderRequest>
            """;

        String response = """
            <x:GetOrderResponse xmlns:x="urn:example:orders:v1">
                <x:orderId>ORD-2048</x:orderId>
                <x:status>PAID</x:status>
            </x:GetOrderResponse>
            """;

        client.sendRequest(
                withPayload(new StringSource(request))
            )
            .andExpect(
                payload(new StringSource(response))
            );
    }
}
~~~

Đây là **test skeleton**: để chạy được cần cấu hình Spring test extension, ApplicationContext, `@EnableWs`, component scan và một test bean `OrderApplicationService` trả status `PAID`. Các XML matchers cần được chọn đúng ngữ nghĩa namespace thay vì so prefix tùy ý.

Thêm các ca integration:

- Request vắng `orderId` hoặc `correlationId` phải bị XSD validation từ chối.
- QName v2 không được xử lý nhầm như v1.
- SOAP response phải có root QName và thứ tự children đúng.
- Khi lỗi nghiệp vụ, trả SOAP Fault không lộ dữ liệu nội bộ.
- Nếu có WS-Security, kiểm tra chữ ký/token/chứng chỉ ở pipeline thực tế.

`MockWebServiceClient` không kiểm tra HTTP Content-Type, servlet mapping, gateway, TLS hay WSDL address. Các điều này phải có test SOAP HTTP thật và ít nhất một client độc lập (ví dụ công cụ SOAP/.NET) khi kiểm thử interoperability.

## 19. Bảo mật DOM trong dịch vụ doanh nghiệp

### 19.1. XXE là rủi ro của parser, không phải riêng của DOM

Nếu XML parser cho phép DTD và external entities, một request không tin cậy có thể gây truy cập file/URL ngoài ý muốn. Cấu hình parser an toàn như ở mục 6 là cần thiết, nhưng phải kiểm tra cả SOAP message factory, Transformer, SchemaFactory và các thư viện parse khác đang được sử dụng. Không mặc định một helper an toàn bảo vệ toàn bộ pipeline.

### 19.2. Quản lý bộ nhớ và giới hạn đầu vào

DOM thường giữ toàn bộ cây XML trong bộ nhớ. Khi số lượng item lớn hoặc payload phức tạp, chi phí object nodes có thể cao hơn đáng kể kích thước XML thô. Cần đặt giới hạn:

- Kích thước HTTP/SOAP body và số node.
- Độ sâu XML và số lần lặp theo XSD.
- Timeout và concurrency.
- Mức độ logging, tránh log nguyên message chứa dữ liệu nhạy cảm.
- Cân nhắc StAX/streaming thay vì DOM nếu payload có thể rất lớn.

### 19.3. WS-Security và chữ ký XML

Chữ ký XML bảo vệ các phần được tham chiếu thông qua quy tắc canonicalization. Sau khi thông điệp đã ký, đổi namespace declarations, element structure hoặc nội dung có thể khiến chữ ký không hợp lệ; không được coi business fields giống nhau là đủ để giữ chữ ký.

Hệ thống cần xác minh trust, certificate, chữ ký và quyền người gọi tại những lớp thích hợp trước khi tin cậy dữ liệu. DOM chỉ cho phép thao tác cây; nó không tự xác thực danh tính hay tính toàn vẹn của thông điệp.

## 20. Chọn DOM hay JAXB/OXM, XPath, StAX?

| Tiêu chí | DOM | JAXB/OXM | XPath | StAX |
|---|---|---|---|---|
| Đọc vài trường | Có thể làm trực tiếp | Có thể sinh nhiều class | Rất phù hợp | Cần xử lý event |
| Tạo response có cấu trúc | Tạo node tường minh | Sinh từ Java object | Không phải công cụ tạo XML | Ghi tuần tự |
| Quản lý namespace | Tường minh với NS APIs | Theo binding/XSD | Qua NamespaceContext | Qua reader/writer namespaces |
| Payload rất lớn | Giữ cây, tốn bộ nhớ | Tạo object graph | Có thể materialize nhiều node | Thường tốt hơn cho streaming |
| XSD validation | Cấu hình riêng | Cấu hình riêng | Không tự validate | Cấu hình riêng |
| Schema có choice/list phức tạp | Nhiều code traversal | Thường rõ ràng hơn | XPath có thể khó duy trì | Cần logic streaming |
| Yêu cầu sửa cây XML | Phù hợp | Chuyển qua object | Chủ yếu chọn node | Không có cây mặc định |

Dùng DOM khi cần quyền kiểm soát cây và payload vừa phải. Dùng JAXB khi contract có nhiều kiểu dữ liệu, danh sách hoặc logic chuyển đổi phức tạp. Dùng XPath khi chỉ cần chọn vài node rõ ràng. Dùng StAX khi streaming quan trọng hơn khả năng duyệt cây.

Việc lựa chọn công cụ không được thay đổi nghĩa của hợp đồng: QName, XSD constraints, WSDL binding, SOAP Fault và chính sách bảo mật vẫn là cam kết chung.

## 21. Tình huống thực tế: response nhìn đúng nhưng client từ chối

Một nhóm phát triển trả XML:

~~~xml
<GetOrderResponse>
    <orderId>ORD-2048</orderId>
    <status>PAID</status>
</GetOrderResponse>
~~~

Nhìn bằng mắt, tên element đều đúng. Tuy nhiên WSDL/XSD yêu cầu namespace `urn:example:orders:v1`. Vì code đã dùng:

~~~java
document.createElement("GetOrderResponse");
document.createElement("orderId");
document.createElement("status");
~~~

nên các node này không mang namespace v1. Client sinh từ XSD có thể báo unexpected element hoặc không ánh xạ được response.

Cách sửa là tạo bằng:

~~~java
document.createElementNS(
    "urn:example:orders:v1",
    "ord:GetOrderResponse"
);

document.createElementNS(
    "urn:example:orders:v1",
    "ord:orderId"
);
~~~

và khai báo namespace nếu sử dụng prefix `ord`. Sau đó validate bằng XSD, thay vì chỉ xem XML output trông đã đúng.

Một lỗi khác là dùng `getElementsByTagNameNS` lấy phần tử `orderId` đầu tiên trong toàn bộ descendants, vô tình chọn giá trị của object lồng. Cách sửa là đọc direct child theo schema và bắt input không hợp lệ bằng validation. Đừng “chữa” bằng cách tắt XSD hoặc bỏ qua namespace.

## 22. Bài thực hành tổng hợp

Thiết kế SOAP operation `GetShipmentStatus`:

~~~text
targetNamespace: urn:example:shipping:v1
request element: GetShipmentStatusRequest
response element: GetShipmentStatusResponse
~~~

Yêu cầu:

- Request có `shipmentId` required, qualified.
- `includeEvents` optional kiểu xs:boolean.
- `correlationId` là attribute unqualified, required.
- Response có `shipmentId` trước `status`.
- `status` thuộc enum `CREATED`, `IN_TRANSIT`, `DELIVERED`.

Hãy thực hiện:

1. Tạo XSD và xác định QName cho mọi root/child elements.
2. Dùng parser DOM namespace-aware và bảo mật để đọc payload mẫu.
3. Thử hai XML cùng QName: một dùng `sh:`, một dùng default namespace.
4. Đọc `shipmentId` bằng helper direct child, không phụ thuộc prefix.
5. Đọc `correlationId` và phân biệt missing với empty.
6. Parse `includeEvents`, cho phép lexical forms `true`, `false`, `1`, `0` theo XSD và phân biệt absent.
7. Dùng `createElementNS` để tạo response đúng namespace.
8. Tạo response cố tình sai thứ tự child, xác nhận XSD validator reject.
9. Dùng Spring-WS endpoint nhận `@RequestPayload Element` và trả `@ResponsePayload Element`.
10. Gửi request sai XSD, xác nhận nghiệp vụ không chạy và SOAP Fault được trả theo chính sách.
11. Thử parser với DOCTYPE và external entities, xác nhận không có truy cập tài nguyên ngoài.
12. Thử response bằng client độc lập để chứng minh compatibility không phụ thuộc cách viết prefix.

**Tiêu chí đạt:** Cùng QName phải có cùng hành vi dù prefix khác; sai namespace hoặc sai schema phải được phát hiện; response DOM có QName/thứ tự hợp đồng; parser không truy cập nguồn ngoài không tin cậy.

## 23. Checklist trước khi đưa DOM vào production

- [ ] Biết rõ đang thao tác SOAP payload hay toàn bộ Envelope.
- [ ] Parser xử lý XML không tin cậy đã bật namespace-aware và chặn XXE.
- [ ] Dùng `namespaceURI` + `localName`, không so prefix cố định.
- [ ] Không nhầm default namespace của elements với unqualified attributes.
- [ ] Duyệt direct children khi XSD yêu cầu direct child.
- [ ] Dùng `hasAttribute` nếu cần phân biệt attribute vắng mặt và rỗng.
- [ ] Phân biệt absent, empty và xsi:nil khi hợp đồng yêu cầu.
- [ ] Dùng `createElementNS` và `setAttributeNS` phù hợp khi tạo XML.
- [ ] Không tạo XML bằng nối chuỗi input không tin cậy.
- [ ] Giữ thứ tự và cardinality theo XSD.
- [ ] Validate cả request và response, không chỉ parse thành công.
- [ ] Không sửa DOM của thông điệp đã ký tùy tiện.
- [ ] Có giới hạn tài nguyên cho XML lớn và cân nhắc streaming.
- [ ] Kiểm thử prefix khác, default namespace, v2 namespace, attribute và schema errors.
- [ ] Kiểm thử SOAP Fault, bảo mật và client độc lập.

## 24. Ghi nhớ

- **DOM biểu diễn XML thành cây**, thích hợp khi cần đọc/tạo node tường minh.
- **QName = namespace URI + local name**. Prefix chỉ là ký hiệu xuất hiện trong XML.
- **`setNamespaceAware(true)`** cần thiết để đọc namespace đúng khi parse DOM.
- **`createElementNS` và `setAttributeNS`** giúp tạo QName chính xác; `createElement` không tự gắn namespace của XSD.
- **DOM không tự bảo vệ XML parser hay xác thực XSD**: cả hai cần cấu hình riêng và kiểm thử.
- **Spring-WS có thể nhận/trả DOM payload**, nhưng endpoint vẫn phải giữ XSD/WSDL, SOAP version và Fault contract.
- **DOM không thay thế JAXB, WS-Security hoặc domain authorization**. Chọn công cụ theo cấu trúc thông điệp, khối lượng dữ liệu và rủi ro bảo trì.

**Câu hỏi tự kiểm tra:** Một endpoint Spring-WS đọc được `GetOrderRequest` bằng DOM nhưng client từ chối `GetOrderResponse`. Mã đang gọi `document.createElement("GetOrderResponse")` dù XSD yêu cầu namespace `urn:example:orders:v1`. Vì sao tên nhìn đúng nhưng QName sai? Hãy sửa bằng `createElementNS`, giải thích cách dùng `xmlns:ord` và đề xuất ba test để ngăn lỗi tương tự.


