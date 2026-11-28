# XPath, ngữ cảnh namespace và lựa chọn nút dữ liệu

Trong tích hợp SOAP với **Spring Web Services (Spring-WS)**, dữ liệu nghiệp vụ nằm trong các nút XML thuộc những namespace cụ thể. Đọc đúng `orderId`, một thuộc tính hay nhiều dòng hàng không chỉ là tìm đúng chuỗi tên thẻ: cần hiểu **nút đang làm ngữ cảnh**, **QName (namespace URI + local name)** và **kết quả của biểu thức XPath**. Đây là kiến thức nền cho quy trình phát triển dịch vụ **contract-first** dựa trên XSD/WSDL, JAXB, endpoint và SOAP client; nó cũng giúp phân tích SOAP Fault, interceptor, kiểm thử tương thích và một số rủi ro XML security/WS-Security.

Bài học dùng **XPath 1.0 qua Java XPath API (JAXP)** làm trọng tâm vì đây là mức chức năng phổ biến khi xử lý DOM trong Java. Các phiên bản XPath 2.0/3.x có tính năng khác, không nên mặc định rằng JAXP hỗ trợ chúng.

## Mục tiêu

Sau bài học, bạn có thể:

1. Giải thích nút (node), trục chọn nút (axis), ngữ cảnh XPath và phân biệt đường dẫn tuyệt đối/tương đối.
2. Chọn đúng phần tử, thuộc tính, nút văn bản từ SOAP Envelope, Header và Body, kể cả khi XML dùng **default namespace**.
3. Dùng predicate, hàm và kiểu kết quả XPath 1.0 để tìm một hoặc nhiều nút dữ liệu.
4. Cấu hình `NamespaceContext` và gọi `XPath.evaluate` an toàn với DOM/JAXP trong Java.
5. Nhận biết lỗi thường gặp và giới hạn của XPath khi làm việc với hợp đồng SOAP, JAXB, interceptor và chữ ký XML.

## 1. Một thông điệp SOAP để thực hành

Giả sử client gửi yêu cầu tạo đơn hàng tới Spring-WS. Đây là **XML minh họa cấu trúc**, chưa phải hợp đồng XSD/WSDL hoàn chỉnh:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope
    xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:obs="urn:example:observability:v1"
    xmlns:ord="urn:example:orders:v1">
  <s:Header>
    <obs:Trace>
      <obs:correlationId>req-123</obs:correlationId>
    </obs:Trace>
  </s:Header>
  <s:Body>
    <CreateOrderRequest xmlns="urn:example:orders:v1"
                        version="1">
      <customerId>C-08</customerId>
      <items>
        <item sku="A-01" ord:category="physical">
          <quantity>2</quantity>
        </item>
        <item sku="B-02" ord:category="service">
          <quantity>1</quantity>
        </item>
      </items>
    </CreateOrderRequest>
  </s:Body>
</s:Envelope>
~~~

Các chi tiết quyết định cách chọn nút:

| Thành phần trong XML | Tên theo namespace (QName) | Ý nghĩa |
| --- | --- | --- |
| `s:Envelope` | `{http://schemas.xmlsoap.org/soap/envelope/}Envelope` | Phong bì SOAP 1.1 |
| `s:Body` | `{http://schemas.xmlsoap.org/soap/envelope/}Body` | Chứa payload nghiệp vụ |
| `CreateOrderRequest` | `{urn:example:orders:v1}CreateOrderRequest` | Phần tử gốc của payload, dù **không viết tiền tố** |
| `customerId`, `item`, `quantity` | Thuộc `urn:example:orders:v1` | Kế thừa default namespace của payload |
| `obs:correlationId` | `{urn:example:observability:v1}correlationId` | Metadata của Header |
| `sku`, `version` | **Không có namespace** | Thuộc tính không tiền tố không kế thừa default namespace |
| `ord:category` | `{urn:example:orders:v1}category` | Thuộc tính có namespace vì có tiền tố `ord` |

Lưu ý: `version="1"` chỉ là ví dụ thuộc tính XML, không thay thế chiến lược versioning hợp đồng bằng namespace/XSD/WSDL. Namespace URI là định danh; nó không nhất thiết là một địa chỉ HTTP có thể truy cập.

## 2. XPath nhìn tài liệu XML như một cây nút

XPath chọn nút trên mô hình cây. Để đọc đúng biểu thức, cần biết những loại nút cơ bản:

- **Document/root node:** gốc mô hình tài liệu; khác với phần tử `Envelope`.
- **Element node:** phần tử như `Body`, `CreateOrderRequest`, `item`.
- **Attribute node:** thuộc tính như `sku` hoặc `ord:category`.
- **Text node:** nội dung ký tự, chẳng hạn `C-08` hoặc `2`.
- Ngoài ra còn có comment, processing instruction và namespace node trong mô hình XPath 1.0.

Một biểu thức XPath thông thường có các **bước (steps)**, mỗi bước gồm trục chọn nút, kiểm tra tên/loại nút và bộ lọc tùy chọn.

~~~text
/s:Envelope/s:Body/o:CreateOrderRequest/o:customerId
│          │      │                      └── chọn con customerId
│          │      └── chọn con CreateOrderRequest
│          └── chọn con Body
└── bắt đầu ở gốc tài liệu rồi chọn Envelope
~~~

Ở đây `s` và `o` là các tiền tố do **ngữ cảnh XPath** ánh xạ tới namespace URI. Chúng không bắt buộc trùng tiền tố in trong XML. Ta sẽ cấu hình chúng ở phần sau.

### 2.1. Các ký hiệu XPath quan trọng

| Cú pháp | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `/` | Phân tách các bước; ở đầu biểu thức nghĩa là bắt đầu từ root node | `/s:Envelope/s:Body` |
| `.` | Nút ngữ cảnh hiện tại | `./o:customerId` |
| `..` | Nút cha | `../o:customerId` |
| `//` | Tìm ở các cấp con cháu; cần dùng có chủ đích | `//o:item` |
| `@` | Chọn thuộc tính | `@sku` |
| `text()` | Chọn nút văn bản con | `o:customerId/text()` |
| `*` | Chọn các phần tử ở trục hiện tại, không phân biệt tên | `o:items/*` |
| `[...]` | Lọc tập nút theo điều kiện (predicate) | `o:item[@sku='A-01']` |
| `|` | Hợp hai tập nút | `o:customerId | o:items` |
| `ancestor::` | Chọn các nút tổ tiên | `ancestor::s:Body` |
| `following-sibling::` | Chọn các nút anh em phía sau | `following-sibling::o:item` |

Dấu `/` dùng từ **root node** của tài liệu; một đường dẫn tương đối như `o:customerId` chỉ hoạt động đúng khi context node là `CreateOrderRequest` (hoặc một nút cha phù hợp với đường dẫn).

### 2.2. Ngữ cảnh quyết định ý nghĩa

Cùng một XPath có thể cho kết quả khác khi đánh giá trên nút khác:

~~~text
Context = Document
/s:Envelope/s:Body/o:CreateOrderRequest/o:customerId   → C-08

Context = CreateOrderRequest
o:customerId                                             → C-08

Context = một phần tử item
o:quantity                                               → 2 hoặc 1
../..                                                    → CreateOrderRequest
~~~

Với cây XML trên, `..` từ `item` là `items`; `../..` là `CreateOrderRequest`. Nếu đã chọn được một `item`, chỉ dùng `o:quantity` để lấy số lượng của **chính dòng đó**. Đường dẫn `//o:quantity` dễ vô tình chọn số lượng thuộc các dòng khác hoặc vùng khác của thông điệp.

### 2.3. Lựa chọn nút khác với lấy giá trị

Với:

~~~xml
<customerId xmlns="urn:example:orders:v1">C-08</customerId>
~~~

- `o:customerId` chọn **element node**.
- `o:customerId/text()` chọn **text node** là con của phần tử.
- `string(o:customerId)` tạo **giá trị chuỗi** của phần tử (văn bản từ các nút con của nó).
- `normalize-space(o:customerId)` chuẩn hóa khoảng trắng đầu/cuối và các nhóm khoảng trắng bên trong, hữu ích khi hợp đồng cho phép.

Không đánh đồng `text()` với `string()` khi phần tử chứa mixed content hoặc nhiều text node. Trong SOAP nghiệp vụ, dữ liệu thường được thiết kế rõ bằng XSD để tránh mơ hồ đó.

## 3. NamespaceContext: phần dễ sai nhất của XPath trên SOAP

### 3.1. Tên hiển thị không phải danh tính phần tử

Phần tử:

~~~xml
<CreateOrderRequest xmlns="urn:example:orders:v1">
  <customerId>C-08</customerId>
</CreateOrderRequest>
~~~

và phần tử:

~~~xml
<o:CreateOrderRequest xmlns:o="urn:example:orders:v1">
  <o:customerId>C-08</o:customerId>
</o:CreateOrderRequest>
~~~

đều có cùng cặp QName tương ứng. Tiền tố có thể khác, thậm chí XML dùng default namespace, nhưng namespace URI và local name không thay đổi.

**Quy tắc đặc biệt quan trọng với XPath 1.0:** tên phần tử **không có tiền tố** trong biểu thức XPath chỉ chọn phần tử ở **no namespace**. Việc XML khai báo default namespace không làm cho `/CreateOrderRequest/customerId` tự hiểu cùng namespace đó.

Do đó với ví dụ đầu bài:

~~~xpath
/s:Envelope/s:Body/CreateOrderRequest/customerId
~~~

không chọn được payload vì `CreateOrderRequest` và `customerId` thực sự thuộc `urn:example:orders:v1`. Biểu thức đúng là:

~~~xpath
/s:Envelope/s:Body/o:CreateOrderRequest/o:customerId
~~~

miễn là cấu hình:

| Tiền tố **trong XPath** | Namespace URI |
| --- | --- |
| `s` | `http://schemas.xmlsoap.org/soap/envelope/` |
| `o` | `urn:example:orders:v1` |
| `obs` | `urn:example:observability:v1` |

Mặc dù XML dùng `ord` ở một số thuộc tính, biểu thức vẫn có thể dùng `o`: cả hai trỏ tới cùng URI. Ngược lại, tên `o:customerId` với URI sai vẫn không khớp.

### 3.2. Quy tắc namespace cho thuộc tính

Default namespace của một phần tử **không áp dụng cho thuộc tính không có tiền tố**:

~~~xpath
/s:Envelope/s:Body/o:CreateOrderRequest/@version
/s:Envelope/s:Body/o:CreateOrderRequest/o:items/o:item/@sku
/s:Envelope/s:Body/o:CreateOrderRequest/o:items/o:item/@o:category
~~~

Biểu thức `@o:sku` sẽ không khớp `sku="A-01"` trong XML ví dụ vì thuộc tính `sku` không có namespace. Biểu thức `@category` cũng không khớp thuộc tính `ord:category` vì thuộc tính đó **có** namespace.

### 3.3. Khi nào dùng `local-name()` và `namespace-uri()`?

Hai hàm giúp chẩn đoán:

~~~xpath
local-name(/s:Envelope/s:Body/*[1])
namespace-uri(/s:Envelope/s:Body/*[1])
~~~

Kết quả tương ứng là `CreateOrderRequest` và `urn:example:orders:v1`.

Có thể thấy mẹo:

~~~xpath
//*[local-name()='CreateOrderRequest']
~~~

Mẹo này **không nên là cách chọn nút mặc định**: nó bỏ qua namespace, có thể bắt cả phần tử trùng local name trong Header, Body khác, phiên bản hợp đồng khác hoặc một nút do kẻ tấn công chèn thêm. Nếu phải kiểm tra linh hoạt trong công cụ chẩn đoán, ít nhất hãy kết hợp `namespace-uri()` và đường dẫn cha rõ ràng; trong code nghiệp vụ và bảo mật nên ưu tiên QName cụ thể.

## 4. Chọn nút dữ liệu thực tế bằng XPath 1.0

Các ví dụ dưới đây dùng ba tiền tố đã ánh xạ (`s`, `o`, `obs`) và giả định context node là `Document`, trừ khi được ghi rõ.

Để biểu thức ngắn gọn, đặt:

~~~text
BASE = /s:Envelope/s:Body/o:CreateOrderRequest
~~~

`BASE` là ký hiệu **giải thích** trong bài, không phải cú pháp biến tự khai báo của XPath. Trong ứng dụng, hãy viết đầy đủ đường dẫn hoặc đánh giá biểu thức tương đối từ node request.

| Mục đích | Biểu thức XPath (đặt từ `Document`) | Kết quả kỳ vọng |
| --- | --- | --- |
| Lấy mã correlation | `/s:Envelope/s:Header/obs:Trace/obs:correlationId` | Element có giá trị `req-123` |
| Lấy khách hàng | `/s:Envelope/s:Body/o:CreateOrderRequest/o:customerId` | Element có giá trị `C-08` |
| Lấy version thuộc tính | `/s:Envelope/s:Body/o:CreateOrderRequest/@version` | Attribute có giá trị `1` |
| Chọn tất cả dòng | `/s:Envelope/s:Body/o:CreateOrderRequest/o:items/o:item` | 2 element |
| Chọn dòng SKU A-01 | `/s:Envelope/s:Body/o:CreateOrderRequest/o:items/o:item[@sku='A-01']` | 1 element |
| Chọn dòng số lượng lớn hơn 1 | `/s:Envelope/s:Body/o:CreateOrderRequest/o:items/o:item[o:quantity > 1]` | Dòng `A-01` |
| Đếm số dòng | `count(/s:Envelope/s:Body/o:CreateOrderRequest/o:items/o:item)` | Number `2` |
| Cộng số lượng | `sum(/s:Envelope/s:Body/o:CreateOrderRequest/o:items/o:item/o:quantity)` | Number `3` |
| Kiểm tra SKU B-02 có mặt | `boolean(/s:Envelope/s:Body/o:CreateOrderRequest/o:items/o:item[@sku='B-02'])` | Boolean `true` |

Các biểu thức `count()`, `sum()`, `boolean()` trả **giá trị**, không trả nút. `sum()` chuyển giá trị văn bản thành số theo quy tắc XPath 1.0; với giá trị không phải số có thể dẫn đến `NaN`. XSD nên quy định kiểu số nếu đây là dữ liệu nghiệp vụ cần tính toán.

### 4.1. Predicate và thứ tự

XPath **đếm vị trí từ 1**, không phải từ 0:

~~~xpath
/s:Envelope/s:Body/o:CreateOrderRequest/o:items/o:item[1]
~~~

chọn dòng `A-01`. Tuy nhiên có một khác biệt quan trọng:

~~~xpath
//o:item[1]
(//o:item)[1]
~~~

Biểu thức đầu chọn `item` đầu tiên **trong từng nhóm con cùng cha**; biểu thức thứ hai chọn `item` đầu tiên **trong toàn bộ tập kết quả**. Vì thế, `//o:item[1]` có thể trả nhiều nút nếu XML có nhiều `items` cha khác nhau. Khi muốn đúng một dòng hàng đầu tiên, nên bắt đầu từ `CreateOrderRequest/o:items` hoặc đặt dấu ngoặc rõ ràng.

### 4.2. Kết quả rỗng, chuỗi rỗng và nút không tồn tại

Ví dụ:

~~~xpath
string(/s:Envelope/s:Body/o:CreateOrderRequest/o:missingField)
~~~

trả chuỗi rỗng dù không có `missingField`. Nếu `missingField` tồn tại nhưng chứa chuỗi rỗng, kết quả chuỗi cũng rỗng. Vì vậy **không dùng `String.isEmpty()` để kết luận một nút có tồn tại hay không**. Muốn phân biệt, hãy lấy `NODE` để kiểm tra `null`, hoặc kiểm tra `boolean(...)`.

## 5. Thực hành trên Java: DOM, NamespaceContext và XPath

JAXP nằm trong Java `java.xml` và dùng các lớp `javax.xml.xpath.*`, `javax.xml.namespace.NamespaceContext` ngay cả khi dự án Spring Boot 3+/Jakarta dùng `jakarta.xml.bind.*` cho JAXB. Đừng nhầm namespace Java của JAXP với namespace JAXB: hai API có nhiệm vụ khác nhau.

### 5.1. Tạo DOM với parser có nhận diện namespace

Đặt XML minh họa ở mục 1 vào biến `soapXml` (ví dụ đọc từ test fixture), rồi dùng:

~~~java
import java.io.StringReader;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Document;
import org.xml.sax.InputSource;

// soapXml là chuỗi XML ở mục 1, do ví dụ/test cung cấp.
DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
factory.setNamespaceAware(true);

// Chính sách an toàn cho XML không tin cậy.
factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
factory.setFeature(
    "http://apache.org/xml/features/disallow-doctype-decl", true);
factory.setFeature(
    "http://xml.org/sax/features/external-general-entities", false);
factory.setFeature(
    "http://xml.org/sax/features/external-parameter-entities", false);
factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
factory.setXIncludeAware(false);

Document document = factory.newDocumentBuilder()
    .parse(new InputSource(new StringReader(soapXml)));
~~~

`setNamespaceAware(true)` là điều kiện quan trọng khi dùng QName trong XPath trên DOM. Các cơ chế chặn DOCTYPE, external entities và external access là lớp bảo vệ khỏi **XXE**. Tính năng cụ thể có thể phụ thuộc parser/provider; nếu cấu hình bảo mật không được hỗ trợ, cần xử lý như lỗi cấu hình, **không bỏ qua exception rồi tiếp tục parse**. Ngoài ra cần giới hạn kích thước XML, độ sâu và tài nguyên xử lý phù hợp với môi trường triển khai.

Trong Spring-WS thực tế, thông điệp có thể đến dưới dạng `Source`, SAAJ hoặc cơ chế streaming; không nên mặc định đó đã là `Document` hoặc cứ mỗi request đều chuyển toàn bộ SOAP sang DOM. Đoạn DOM này phục vụ việc hiểu XPath/JAXP và cho những trường hợp thực sự cần duyệt cây XML.

### 5.2. Khai báo ánh xạ prefix → namespace URI

~~~java
import java.util.Collections;
import java.util.Iterator;
import java.util.Map;
import java.util.Objects;
import javax.xml.XMLConstants;
import javax.xml.namespace.NamespaceContext;
import javax.xml.xpath.XPath;
import javax.xml.xpath.XPathFactory;

Map<String, String> ns = Map.of(
    "s",   "http://schemas.xmlsoap.org/soap/envelope/",
    "o",   "urn:example:orders:v1",
    "obs", "urn:example:observability:v1"
);

XPath xpath = XPathFactory.newInstance().newXPath();
xpath.setNamespaceContext(new NamespaceContext() {

    @Override
    public String getNamespaceURI(String prefix) {
        Objects.requireNonNull(prefix, "prefix");
        if ("xml".equals(prefix)) {
            return XMLConstants.XML_NS_URI;
        }
        if ("xmlns".equals(prefix)) {
            return XMLConstants.XMLNS_ATTRIBUTE_NS_URI;
        }
        return ns.getOrDefault(prefix, XMLConstants.NULL_NS_URI);
    }

    @Override
    public String getPrefix(String namespaceURI) {
        Objects.requireNonNull(namespaceURI, "namespaceURI");
        if (XMLConstants.XML_NS_URI.equals(namespaceURI)) {
            return "xml";
        }
        if (XMLConstants.XMLNS_ATTRIBUTE_NS_URI.equals(namespaceURI)) {
            return "xmlns";
        }
        for (Map.Entry<String, String> entry : ns.entrySet()) {
            if (entry.getValue().equals(namespaceURI)) {
                return entry.getKey();
            }
        }
        return null;
    }

    @Override
    public Iterator<String> getPrefixes(String namespaceURI) {
        String prefix = getPrefix(namespaceURI);
        return prefix == null
            ? Collections.emptyIterator()
            : Collections.singleton(prefix).iterator();
    }
});
~~~

Những tiền tố `s`, `o`, `obs` là **biến ánh xạ trong câu truy vấn**, không phải điều kiện bắt buộc về cách đối tác viết tiền tố trong SOAP. Nếu đối tác đổi `s:Envelope` thành `soap:Envelope` nhưng vẫn dùng đúng URI SOAP 1.1, XPath trên vẫn hoạt động.

### 5.3. Đánh giá một nút, tập nút và giá trị

~~~java
import javax.xml.xpath.XPathConstants;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;

// Document document và XPath xpath được tạo ở các đoạn trước.
String base = "/s:Envelope/s:Body/o:CreateOrderRequest";

Node requestNode = (Node) xpath.evaluate(
    base, document, XPathConstants.NODE);

if (requestNode == null) {
    throw new IllegalArgumentException("Missing CreateOrderRequest payload");
}

// Khi context node là request, dùng đường dẫn tương đối.
String customerId = xpath.evaluate("o:customerId", requestNode);

NodeList items = (NodeList) xpath.evaluate(
    "o:items/o:item", requestNode, XPathConstants.NODESET);

for (int i = 0; i < items.getLength(); i++) {
    Node item = items.item(i);
    String sku = xpath.evaluate("@sku", item);
    String quantityText = xpath.evaluate("o:quantity", item);
    String category = xpath.evaluate("@o:category", item);
    System.out.printf("%s: %s (%s)%n", sku, quantityText, category);
}

String correlationId = xpath.evaluate(
    "/s:Envelope/s:Header/obs:Trace/obs:correlationId",
    document
);

Double totalQuantity = (Double) xpath.evaluate(
    "sum(o:items/o:item/o:quantity)",
    requestNode,
    XPathConstants.NUMBER
);
~~~

Dữ liệu kỳ vọng:

~~~text
customerId   = C-08
correlationId = req-123
A-01: 2 (physical)
B-02: 1 (service)
totalQuantity = 3.0
~~~

Phân biệt kiểu kết quả:

| Kiểu `XPathConstants` | Giá trị Java thường nhận được | Trường hợp sử dụng |
| --- | --- | --- |
| `NODE` | `org.w3c.dom.Node` hoặc `null` | Chọn một nút và kiểm tra có tồn tại |
| `NODESET` | `org.w3c.dom.NodeList` | Duyệt nhiều phần tử/thuộc tính |
| `STRING` | `String` | Đọc giá trị chuỗi |
| `NUMBER` | `Double` | `count()`, `sum()`, phép tính |
| `BOOLEAN` | `Boolean` | `boolean()`, điều kiện |

Phương thức `evaluate(expression, context)` không truyền `returnType` sẽ trả chuỗi theo API JAXP. Với `NODE` và `NODESET`, ép kiểu chỉ nên thực hiện khi đã yêu cầu hằng `XPathConstants` tương ứng.

Có thể dùng `XPath.compile(...)` trước khi đánh giá nhiều lần, nhưng không mặc định chia sẻ `XPath` hoặc `XPathExpression` cho nhiều thread vì API không bảo đảm thread-safety. Với dịch vụ xử lý đồng thời, quản lý vòng đời đối tượng theo cách phù hợp.

## 6. XPath nằm ở đâu trong Spring Web Services?

### 6.1. Endpoint mapping dựa vào QName payload

Spring-WS có thể chọn endpoint theo phần tử gốc trong SOAP Body:

~~~java
@Endpoint
public class OrderEndpoint {
    private static final String ORDERS_NS = "urn:example:orders:v1";

    @PayloadRoot(namespace = ORDERS_NS, localPart = "CreateOrderRequest")
    @ResponsePayload
    public CreateOrderResponse createOrder(
            @RequestPayload CreateOrderRequest request) {
        // Các kiểu request/response JAXB và nghiệp vụ là ví dụ minh họa.
        // Xử lý dữ liệu đã được ánh xạ theo hợp đồng XSD...
        return new CreateOrderResponse();
    }
}
~~~

Trong cách này, `@PayloadRoot` kiểm tra QName của phần tử root của payload; không cần XPath tìm `CreateOrderRequest` từ toàn bộ Envelope. Khi mục tiêu là xử lý request/response có schema ổn định, **JAXB + XSD validation** thường rõ kiểu và dễ bảo trì hơn việc trích từng field bằng XPath.

XPath hữu ích khi:

- Kiểm tra hoặc trích một vài nút trong tài liệu XML phục vụ **diagnostic/test**.
- Làm việc với XML bán cấu trúc ở ranh giới tích hợp, khi yêu cầu chưa đủ để dùng model Java mạnh.
- Chọn phần tử trong một phép biến đổi, truy vấn báo cáo hoặc chính sách xử lý XML đã được kiểm soát.

Không dùng XPath như một cách thay thế việc thiết kế contract-first, đặt namespace hợp đồng, tạo SOAP client bằng `WebServiceTemplate`, hay định nghĩa lỗi bằng SOAP Fault.

### 6.2. Header, interceptor và SOAP Fault

Header có thể chứa correlation ID hoặc metadata bảo mật; Body chứa request hoặc SOAP Fault. Các nhóm phải được xử lý tách bạch:

| Phần SOAP | Kiểu dữ liệu cần đọc | Cách tiếp cận |
| --- | --- | --- |
| Header ứng dụng | Correlation ID, routing metadata | Chọn QName chính xác, kiểm tra chính sách định dạng và tin cậy |
| Body request | Payload thuộc namespace XSD nghiệp vụ | JAXB/endpoint mapping/validation; XPath khi cần truy vấn có kiểm soát |
| Body response | Payload thành công theo hợp đồng | JAXB unmarshal hoặc XML assertions |
| SOAP Fault | `Fault` với fault code, fault string/detail | Fault handling của Spring-WS/SOAP client, không ép kiểu thành response thành công |
| WS-Security Header | Signature, token, timestamp | Bộ xác thực WS-Security, **không tự quyết định tính hợp lệ bằng XPath có token/chữ ký xuất hiện** |

Nếu truy vấn trực tiếp SOAP 1.1 Fault, nó có phần tử `{http://schemas.xmlsoap.org/soap/envelope/}Fault`. SOAP 1.2 có namespace Envelope và cấu trúc Fault khác. Biểu thức định tuyến cho SOAP 1.1 sẽ không tự tương thích với SOAP 1.2.

Ở interceptor, không nên tin tưởng một `customerId` được tìm bằng truy vấn toàn cục `//o:customerId` rồi coi đó chắc chắn là dữ liệu mà endpoint sẽ xử lý. Khi SOAP message có nhiều nút trùng tên, đặc biệt với chữ ký XML, việc **xác thực một nút nhưng xử lý một nút khác** có thể tạo lỗi nghiêm trọng. Hãy dựa trên kết quả xác thực chuẩn của thư viện WS-Security và nhất quán về đối tượng payload đã kiểm tra.

### 6.3. XPath không thay được XSD/WSDL và JAXB

- **XSD** xác định XML nào hợp lệ: phần tử, namespace, thứ tự, kiểu và điều kiện.
- **WSDL** công bố operation/binding/address của dịch vụ.
- **JAXB** ánh xạ XML theo contract thành kiểu Java.
- **XPath** chọn hoặc tính toán dựa trên những nút đang có trong một cây XML.
- **SOAP client/endpoint** gửi/nhận thông điệp và điều phối xử lý.

Một biểu thức XPath chạy thành công **không chứng minh** XML tuân thủ XSD, yêu cầu WS-Security đã được xác minh, hay client/server tương thích với cùng WSDL. Những vấn đề đó cần cơ chế kiểm tra riêng.

## 7. An toàn, hiệu năng và khả năng tương thích

### 7.1. Tránh XPath injection

Không nối trực tiếp dữ liệu người dùng vào XPath:

~~~java
// Không an toàn nếu sku do bên ngoài cung cấp.
String expression = "o:items/o:item[@sku='" + sku + "']";
~~~

Nếu `sku` chứa dấu nháy hoặc cú pháp XPath, biểu thức có thể sai hoặc bị thay đổi logic. JAXP cho phép truyền **biến XPath** qua `XPathVariableResolver`:

~~~java
// sku là giá trị đầu vào đã có từ request.
xpath.setXPathVariableResolver(name -> {
    if ("sku".equals(name.getLocalPart())
            && name.getNamespaceURI().isEmpty()) {
        return sku;
    }
    throw new IllegalArgumentException("Unknown XPath variable: " + name);
});

// Context = requestNode; giá trị sku không được nối vào câu truy vấn.
NodeList matchingItems = (NodeList) xpath.evaluate(
    "o:items/o:item[@sku = $sku]",
    requestNode,
    XPathConstants.NODESET
);
~~~

Trong ví dụ, `$sku` là biến không có namespace; `NamespaceContext` vẫn chịu trách nhiệm ánh xạ `o`. Nếu cần nhiều biểu thức khác nhau, hãy kiểm soát whitelist biểu thức hợp lệ thay vì cho client gửi nguyên văn XPath.

### 7.2. Giảm rủi ro từ truy vấn rộng

Các biểu thức `//`, `*`, `local-name()` trên toàn tài liệu có thể chọn nhiều nút ngoài ý muốn, tốn CPU khi XML lớn, và gây nhầm namespace/version. Cố gắng:

1. Bắt đầu từ nút đã biết, như phần tử gốc của SOAP Body.
2. Chọn các nhánh cha/con cụ thể và khai báo namespace rõ ràng.
3. Xác thực cấu trúc bằng XSD và giới hạn tài nguyên parser.
4. Không chuyển tài liệu SOAP lớn thành DOM nếu một bộ xử lý streaming hoặc JAXB đáp ứng nhu cầu tốt hơn.

Một `XPathExpression` hợp lệ nhưng thiếu khống chế dữ liệu đầu vào vẫn có thể gây chi phí cao khi đánh giá trên tài liệu sâu/rộng.

### 7.3. Bảo mật thông điệp cần nhiều hơn “chọn đúng nút”

Trong tích hợp doanh nghiệp, HTTPS/TLS với chứng chỉ hợp lệ bảo vệ kênh truyền; **WS-Security** (ví dụ chữ ký XML, timestamp, mã hóa) áp dụng bảo vệ ở cấp thông điệp theo chính sách đối tác. Nếu cần kiểm tra chữ ký, dùng thư viện WS-Security phù hợp như cơ chế tích hợp WSS4J trong Spring-WS, xác minh chính xác phần tử được ký và phần tử nghiệp vụ được xử lý. Không xem kết quả XPath là bằng chứng chữ ký hợp lệ, không tự tắt kiểm tra chứng chỉ để xử lý lỗi kết nối.

Namespace cũng tham gia versioning: đổi `urn:example:orders:v1` thành `urn:example:orders:v2` đồng nghĩa QName đổi, dù local name vẫn là `CreateOrderRequest`. Cần cập nhật contract, endpoint mapping, namespace context của XPath và kiểm thử client tương thích; không chỉ sửa prefix in XML.

## 8. Kiểm thử lựa chọn nút trong dự án SOAP

| Trường hợp thử | Kỳ vọng | Điều xác nhận |
| --- | --- | --- |
| XML dùng prefix `ord:` thay default namespace, cùng URI | Cùng XPath namespace-aware vẫn lấy được khách hàng | XPath dựa vào URI, không phụ thuộc prefix XML |
| XML đổi `urn:example:orders:v1` thành URI khác | XPath `o:...` không khớp | Namespace là một phần QName |
| `sku` không tiền tố, `ord:category` có tiền tố | `@sku` và `@o:category` lần lượt đúng | Namespace thuộc tính được hiểu riêng |
| Có hai `item`, số lượng 2 và 1 | NODESET có 2 nút; `sum()` = 3 | Chọn nhiều nút và tính toán |
| Không có `customerId` | NODE trả `null`; STRING có thể trả `""` | Phân biệt nút vắng mặt và giá trị rỗng |
| Header chứa phần tử cùng tên `customerId` | Đường dẫn neo ở Body không chọn nhầm | XPath đủ cụ thể |
| XML có DOCTYPE/external entity độc hại | Parser bị từ chối theo cấu hình | Phòng chống XXE |
| SKU chứa dấu nháy và ký tự XPath | Truy vấn với `$sku` coi là dữ liệu thuần | Tránh injection |
| Payload hợp XPath nhưng không thỏa XSD | XSD validation từ chối | XPath không thay schema validation |
| Thông điệp có WS-Security signature sai | Chính sách bảo mật từ chối | Chữ ký không được xác minh bằng XPath thuần |

Trong test Spring-WS, có thể dùng `MockWebServiceClient` để kiểm tra endpoint và XML response; dùng `MockWebServiceServer` cho client. Ngoài việc kiểm tra XPath, nên kiểm thử XSD/WSDL thực tế, fault khi sai namespace và chính sách bảo mật với hệ thống đối tác. Các test XPath không thay thế kiểm thử SOAP transport, chứng chỉ hay tương thích client khác nền tảng.

## 9. Lỗi phổ biến và cách gỡ

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Biểu thức trả rỗng dù thấy thẻ trong XML | Phần tử thuộc default namespace nhưng XPath không dùng prefix | In `namespace-uri()`, thêm `NamespaceContext` |
| XML hiển thị prefix khác XPath | Hiểu nhầm prefix phải giống nhau | So namespace URI, không so tiền tố |
| `@o:sku` trả rỗng | Thuộc tính `sku` không có namespace | Dùng `@sku` |
| Từ `item` dùng `o:customerId` trả rỗng | Context node không phù hợp | Dùng đường dẫn tương đối đúng hoặc `../..` có chủ đích |
| `//o:item[1]` trả nhiều hơn một nút | Predicate vị trí áp dụng trên từng nhóm con | Dùng `(//o:item)[1]` hoặc đường dẫn cụ thể |
| `STRING` trả `""` nhưng không rõ có thiếu node | STRING của node-set rỗng là chuỗi rỗng | Truy vấn `NODE` hoặc `BOOLEAN` |
| `sum()` trả `NaN` | Giá trị quantity không chuyển được thành số | XSD validation, kiểm tra đầu vào |
| Truy vấn đúng nhưng endpoint không được chọn | Payload root QName khác mapping | So namespace/localPart trong SOAP Body và `@PayloadRoot` |
| Parser hoặc security middleware từ chối XML | DOCTYPE/XXE, SOAP version, signature hoặc timestamp | Kiểm tra lỗi của đúng lớp, tránh tắt bảo vệ |
| XML lớn xử lý chậm | DOM + `//` rộng hoặc đánh giá lặp | Thu hẹp đường dẫn, dùng JAXB/streaming khi thích hợp |

## 10. Bài tập tự kiểm tra

Với XML tại mục 1, hãy thử trả lời trước khi đọc gợi ý:

1. Vì sao `/s:Envelope/s:Body/CreateOrderRequest` không chọn được payload, còn `/s:Envelope/s:Body/o:CreateOrderRequest` thì có?
2. `@sku` khác `@o:category` ở điểm nào dù hai thuộc tính nằm trên cùng một phần tử `item`?
3. Biểu thức tương đối nào chọn quantity của dòng có `sku="B-02"` khi context node là `CreateOrderRequest`?
4. Vì sao nên dùng `NODE` khi cần xác nhận `customerId` có tồn tại, thay vì chỉ lấy `STRING`?
5. Có nên dùng `//*[local-name()='CreateOrderRequest']` để lựa chọn payload đã ký số trong một luồng WS-Security không? Vì sao?
6. Khi đối tác đổi prefix XML nhưng giữ nguyên namespace URI, có cần sửa XPath `o:customerId` không? Nếu đổi hẳn namespace URI thì sao?

**Đáp án gợi ý:** (1) XPath 1.0 không tự áp dụng default namespace của tài liệu cho tên không tiền tố; (2) `sku` thuộc no namespace còn `ord:category` thuộc namespace đơn hàng; (3) `o:items/o:item[@sku='B-02']/o:quantity`; (4) một node vắng mặt có thể được chuyển thành chuỗi rỗng giống node có nội dung rỗng; (5) không, vì bỏ qua namespace/ngữ cảnh có thể chọn sai nút và không chứng minh chữ ký hợp lệ; (6) không cần sửa khi URI không đổi, nhưng phải điều chỉnh mapping/contract khi URI thay đổi.

**Ghi nhớ:** Với XML/SOAP, chọn dữ liệu đúng nghĩa là chọn **đúng QName, đúng vị trí trong cây và đúng context node**. XPath là công cụ truy vấn; contract XSD/WSDL, JAXB, endpoint Spring-WS, SOAP Fault và lớp XML/WS-Security vẫn giữ trách nhiệm riêng trong một hệ thống tích hợp đáng tin cậy.
