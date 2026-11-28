# XSLT, biến đổi cấu trúc và ranh giới với ánh xạ đối tượng

Trong các hệ thống tích hợp doanh nghiệp, hai bên có thể cùng trao đổi XML nhưng dùng **namespace, tên phần tử và cấu trúc tài liệu khác nhau**. Ví dụ, đối tác gửi `<ExternalOrder>` còn dịch vụ nội bộ nhận `<GetOrderRequest>`; cả hai đều biểu đạt yêu cầu truy vấn đơn hàng nhưng không cùng hợp đồng XSD. Khi đó, cần phân biệt ba việc:

1. **Biến đổi cấu trúc XML**: đổi cây phần tử, thuộc tính, namespace, thứ tự và quan hệ cha–con. Đây là bài toán phù hợp với **XSLT**.
2. **Ánh xạ XML sang đối tượng Java**: đọc/ghi giá trị theo cấu trúc XML đã biết để tạo và sử dụng các POJO. Đây là bài toán của **JAXB** (hoặc một công cụ XML binding khác).
3. **Chuyển đổi mô hình nghiệp vụ**: kiểm tra quyền, tra cứu dữ liệu, áp dụng quy tắc giá, đổi trạng thái, gọi dịch vụ. Đây thường là việc của **mã ứng dụng Java**, không nên nhét hết vào stylesheet.

Trong module **SPRING_WEB_SERVICES**, Spring Web Services (Spring-WS) được dùng để phát triển SOAP theo hướng **contract-first** với XSD/WSDL, endpoint, SOAP client, JAXB, SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích. XSLT là một công cụ có thể dùng tại **ranh giới tích hợp XML** để điều chỉnh cấu trúc thông điệp; nó không thay thế hợp đồng SOAP hay cơ chế dispatch và bảo mật của Spring-WS.

## 1. XSLT là gì và thực sự biến đổi điều gì?

**XSLT (Extensible Stylesheet Language Transformations)** là ngôn ngữ khai báo để chuyển một cây XML nguồn thành một kết quả khác, thường là một cây XML có cấu trúc mới. Stylesheet XSLT chứa các **template**, điều kiện và biểu thức **XPath** để chọn node, đọc giá trị và sinh node đầu ra.

XSLT có thể:

- Đổi tên element/attribute, chuyển element thành attribute hoặc ngược lại.
- Thay đổi namespace, gom hoặc tách các nhánh, sắp xếp phần tử, chọn hoặc bỏ dữ liệu.
- Lặp qua danh sách, áp dụng quy tắc theo node và ánh xạ các trường tương ứng.
- Sinh XML, HTML hoặc văn bản, tùy cách cấu hình đầu ra.

XSLT **không tự biết** một XML đã thỏa mãn XSD, không tự sinh lớp JAXB và không hiểu ý nghĩa nghiệp vụ của `orderId`, `amount` hay `currency`. Nó chỉ thực thi các quy tắc được biểu diễn trong stylesheet. Bản thân việc biến đổi thành công chưa chứng minh dữ liệu sau biến đổi hợp lệ với hợp đồng đích.

### XSLT, XPath, XSD, WSDL và JAXB khác nhau thế nào?

| Công nghệ | Trả lời câu hỏi | Vai trò trong tích hợp SOAP |
| --- | --- | --- |
| **XML** | Dữ liệu được biểu diễn bằng cây node và namespace nào? | Cú pháp của SOAP Envelope và payload |
| **XPath** | Chọn node/giá trị nào trong cây XML? | Ngôn ngữ truy vấn được dùng bởi XSLT và công cụ kiểm thử |
| **XSLT** | Biến đổi cây XML này thành cây nào khác? | Ánh xạ giữa các cấu trúc XML khác nhau |
| **XSD** | Cây XML hợp lệ phải có cấu trúc và kiểu dữ liệu gì? | Hợp đồng payload request/response |
| **WSDL** | Dịch vụ có operation, message và binding nào? | Hợp đồng trao đổi SOAP của client và server |
| **JAXB** | Ánh xạ XML đã biết sang/ra đối tượng Java ra sao? | Marshalling/unmarshalling payload trong endpoint hoặc client |

Vì thế, **XSLT và JAXB có thể kết hợp**. XSLT làm nhiệm vụ chuyển từ XML của đối tác sang XML theo XSD nội bộ; JAXB tiếp tục chuyển XML nội bộ đó thành đối tượng Java phù hợp.

## 2. Tình huống: hai hợp đồng XML biểu diễn cùng một yêu cầu

Một hệ thống đối tác gửi yêu cầu tra cứu đơn hàng:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<p:OrderLookup xmlns:p="urn:partner:orders:v1">
    <p:ExternalId> A-0042 </p:ExternalId>
    <p:ChannelCode>WEB</p:ChannelCode>
</p:OrderLookup>
~~~

Hệ thống nội bộ đã có hợp đồng SOAP với payload mong đợi:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<c:LookupOrderRequest xmlns:c="urn:internal:orders:v1">
    <c:orderId>A-0042</c:orderId>
    <c:sourceChannel>WEB</c:sourceChannel>
</c:LookupOrderRequest>
~~~

Sự khác biệt không chỉ nằm ở tên trường. **QName** (qualified name) của phần tử gốc đã thay đổi từ `{urn:partner:orders:v1}OrderLookup` thành `{urn:internal:orders:v1}LookupOrderRequest`. Nếu lớp JAXB được sinh cho XSD nội bộ, không nên mặc định nó có thể unmarshal trực tiếp XML của đối tác.

Một stylesheet **XSLT 1.0** để chuyển đổi dữ liệu ví dụ:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:p="urn:partner:orders:v1"
    xmlns:c="urn:internal:orders:v1"
    exclude-result-prefixes="p">

    <xsl:output method="xml" encoding="UTF-8" indent="yes"/>

    <xsl:template match="/p:OrderLookup">
        <c:LookupOrderRequest>
            <c:orderId>
                <xsl:value-of select="normalize-space(p:ExternalId)"/>
            </c:orderId>
            <c:sourceChannel>
                <xsl:value-of select="p:ChannelCode"/>
            </c:sourceChannel>
        </c:LookupOrderRequest>
    </xsl:template>

</xsl:stylesheet>
~~~

Ở ví dụ này:

- `match="/p:OrderLookup"` chọn chính xác phần tử gốc theo **namespace URI + local name**, không phải chỉ nhìn tiền tố `p`.
- `<c:LookupOrderRequest>` và các phần tử con là **literal result elements**: XSLT tạo ra chúng trong namespace đích.
- `select="p:ExternalId"` và `select="p:ChannelCode"` dùng XPath để chọn giá trị.
- `normalize-space(...)` loại khoảng trắng đầu/cuối và thu gọn chuỗi khoảng trắng bên trong. **Chỉ dùng khi hợp đồng nghiệp vụ cho phép**; có những định danh mà khoảng trắng là dữ liệu có nghĩa.
- `exclude-result-prefixes="p"` tránh đưa namespace nguồn vào kết quả khi không cần thiết.

Tùy bộ xử lý, kết quả có thể khác về khai báo XML, khoảng trắng để thụt dòng hoặc lựa chọn prefix, nhưng **cấu trúc và QName đích** phải đúng. Không so sánh XML chỉ bằng chuỗi ký tự nếu những khác biệt trình bày đó không ảnh hưởng ngữ nghĩa.

### Vì sao namespace quan trọng?

Hai tài liệu sau mô tả cùng một QName:

~~~xml
<p:OrderLookup xmlns:p="urn:partner:orders:v1"/>
<q:OrderLookup xmlns:q="urn:partner:orders:v1"/>
~~~

Nhưng tài liệu sau **không** có cùng QName vì phần tử thuộc namespace rỗng:

~~~xml
<OrderLookup/>
~~~

Trong XPath 1.0, biểu thức `/OrderLookup` chỉ chọn phần tử **không thuộc namespace**. Dù tài liệu nguồn dùng namespace mặc định, trong stylesheet vẫn phải gán URI đó cho **một prefix XPath** và chọn bằng prefix ấy. Lỗi nhầm namespace là nguyên nhân phổ biến khiến template không chạy như mong đợi.

## 3. Tư duy theo cây XML thay vì thay thế chuỗi

XSLT làm việc với **node**. Một tài liệu XML bao gồm element, attribute, text, comment, processing instruction và namespace. Thay tên phần tử bằng cách tìm/đổi chuỗi dễ phá vỡ những khác biệt này.

Ví dụ nguồn:

~~~xml
<p:Line xmlns:p="urn:partner:orders:v1" code="A1">
    <p:Quantity>2</p:Quantity>
    <p:Unit>piece</p:Unit>
</p:Line>
~~~

Nếu hợp đồng đích yêu cầu thuộc tính `sku` và một element `quantity`, stylesheet có thể chọn chính xác:

~~~xml
<xsl:template match="p:Line">
    <c:Item sku="{@code}">
        <c:quantity>
            <xsl:value-of select="p:Quantity"/>
        </c:quantity>
    </c:Item>
</xsl:template>
~~~

Biểu thức `sku="{@code}"` là **attribute value template**, lấy giá trị thuộc tính `code` của node nguồn. Ví dụ giả định prefix `p` và `c` đã được khai báo trên stylesheet như ở phần trước.

Một số lệnh XSLT 1.0 quan trọng:

| Cú pháp | Ý nghĩa | Điểm cần lưu ý |
| --- | --- | --- |
| `xsl:template match="..."` | Áp dụng quy tắc với node phù hợp | Mẫu so khớp phụ thuộc namespace và ngữ cảnh |
| `xsl:apply-templates select="..."` | Yêu cầu xử lý các node được chọn theo template | Giúp tách logic mapping từng loại node |
| `xsl:for-each select="..."` | Lặp qua tập node | Phù hợp cho mapping danh sách ngắn, rõ ràng |
| `xsl:value-of select="..."` | Lấy giá trị chuỗi của biểu thức | Trong XSLT 1.0, node-set thường được chuyển thành chuỗi từ node đầu tiên theo thứ tự tài liệu |
| `xsl:copy` | Sao chép node hiện tại (không tự copy mọi con) | Thường kết hợp `xsl:apply-templates` hoặc `xsl:copy-of` |
| `xsl:copy-of` | Sao chép toàn bộ cây con hoặc giá trị được chọn | Có thể mang theo namespace/chi tiết không mong muốn |
| `xsl:if` / `xsl:choose` | Rẽ nhánh theo điều kiện | Phù hợp cho lựa chọn cấu trúc, không thay thế validation |
| `xsl:param` | Nhận giá trị tham số từ bên ngoài | Truyền qua API của transformer, không nối chuỗi vào XSLT |

### Ánh xạ danh sách và thứ tự phần tử

Nếu đối tác gửi nhiều dòng hàng, ta có thể biến mỗi `p:Line` thành `c:item`:

~~~xml
<xsl:template match="p:Lines">
    <c:items>
        <xsl:for-each select="p:Line">
            <c:item>
                <c:sku><xsl:value-of select="@code"/></c:sku>
                <c:quantity><xsl:value-of select="p:Quantity"/></c:quantity>
            </c:item>
        </xsl:for-each>
    </c:items>
</xsl:template>
~~~

Với XSD dùng `xs:sequence`, **thứ tự element đầu ra là một phần của hợp đồng**. XSLT có thể sinh XML đúng tên nhưng sai thứ tự, dẫn đến validation thất bại. XSLT không tự động căn chỉnh đầu ra theo XSD.

## 4. Ranh giới giữa XSLT và JAXB

Hãy hình dung pipeline:

~~~mermaid
flowchart LR
    A["XML nguồn<br/>theo XSD đối tác"] --> B["XSLT<br/>đổi cấu trúc và namespace"]
    B --> C["XML đích<br/>theo XSD nội bộ"]
    C --> D["XSD validation"]
    D --> E["JAXB unmarshal"]
    E --> F["DTO/POJO Java"]
    F --> G["Dịch vụ nghiệp vụ"]
~~~

**XSLT chuyển cây XML thành cây XML khác; JAXB chuyển giữa XML và object graph Java.**

| Cần làm gì? | Công cụ nên ưu tiên | Vì sao? |
| --- | --- | --- |
| Đổi `ExternalId` thành `orderId` và đổi namespace | XSLT | Thay đổi cấu trúc XML |
| Đưa `Line/@code` thành `Item/sku` | XSLT | Đổi attribute thành element |
| Chuyển XML đúng XSD thành `GetOrderRequest` Java | JAXB | Dùng XML binding dựa trên kiểu và annotation |
| Tạo response XML đúng XSD từ object Java | JAXB marshalling | Xuất XML theo lớp binding đã cấu hình |
| Kiểm tra số tiền đủ hạn mức, quyền truy cập đơn hàng | Java service/domain | Cần ngữ cảnh nghiệp vụ, dữ liệu hệ thống và chính sách |
| Chuyển `String amount` thành `BigDecimal`, áp dụng quy tắc làm tròn tiền | Java mapping/domain | Cần quy tắc chính xác, kiểm thử theo nghiệp vụ |
| Xác minh chữ ký của SOAP header | WS-Security trong SOAP stack | Đây là bảo mật thông điệp, không phải biến đổi XML |

Ví dụ sau khi XML đã được chuyển sang `LookupOrderRequest` theo XSD nội bộ, JAXB có thể tạo một đối tượng Java với `orderId` và `sourceChannel`. Nhưng **nó không tự biết** `ExternalId` của đối tác có nghĩa là `orderId` nếu hợp đồng và annotation không mô tả điều đó.

### Nếu không có XSLT thì sao?

Không phải cứ có hai XML khác nhau là cần XSLT. Một lựa chọn phổ biến khác:

~~~text
XML đối tác → JAXB (lớp đối tác) → Java mapper
            → Java DTO (lớp nội bộ) → JAXB (XML nội bộ)
~~~

Cách này hợp lý khi việc đổi cấu trúc gắn với nhiều **quy tắc nghiệp vụ, kiểu Java, tra cứu dữ liệu** hoặc mapping đã được quản lý tập trung trong code. Ngược lại, XSLT phù hợp khi khác biệt chủ yếu là **hình dạng XML** và cần một stylesheet độc lập, dễ đối chiếu với hợp đồng của đối tác.

Không nên đặt một quy tắc nghiệp vụ quan trọng ở cả XSLT lẫn Java mapper; hai nguồn sự thật sẽ dễ lệch nhau.

## 5. XSLT nằm ở đâu trong Spring Web Services?

Trong một dịch vụ Spring-WS, XML payload thường nằm trong **SOAP Body**:

~~~xml
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
    <soap:Header>
        <!-- Các header nghiệp vụ hoặc WS-Security khi hợp đồng yêu cầu -->
    </soap:Header>
    <soap:Body>
        <p:OrderLookup xmlns:p="urn:partner:orders:v1">
            <p:ExternalId>A-0042</p:ExternalId>
            <p:ChannelCode>WEB</p:ChannelCode>
        </p:OrderLookup>
    </soap:Body>
</soap:Envelope>
~~~

Một vị trí hợp lý để biến đổi là **lớp adapter tích hợp**, sau khi SOAP stack nhận/xác thực thông điệp và trước khi service nghiệp vụ sử dụng dữ liệu. Có thể biểu diễn:

~~~mermaid
flowchart TD
    A["SOAP client của đối tác"] --> B["MessageDispatcherServlet"]
    B --> C["Kiểm tra header, bảo mật,<br/>định tuyến endpoint"]
    C --> D["Payload XML theo hợp đồng ngoài"]
    D --> E{"Có cần đổi cấu trúc?"}
    E -->|Có| F["XSLT → XML hợp đồng nội bộ"]
    E -->|Không| G["XML theo hợp đồng đã chọn"]
    F --> H["Kiểm tra XSD đích"]
    G --> H
    H --> I["JAXB / Java mapper"]
    I --> J["Service nghiệp vụ"]
~~~

Các điểm thiết kế quan trọng:

- `@PayloadRoot` của Spring-WS thường định tuyến theo **QName của payload đến từ client**. Nếu đối tác gửi `OrderLookup`, endpoint public cần nhận biết QName đó; không nên giả định cấu hình XSLT ở bên trong service tự làm thay đổi định tuyến ban đầu.
- XSLT trong ví dụ biến đổi **payload**, không mặc định sao chép hoặc thay thế toàn bộ SOAP Envelope. SOAP version, header, attachment và Fault thuộc trách nhiệm của SOAP stack và hợp đồng tích hợp.
- Nếu hợp đồng **response gửi lại đối tác** khác mô hình nội bộ, cần một mapping ở chiều ngược lại: đối tượng/result nội bộ → XML theo schema phản hồi ngoài. Không được trả ngẫu nhiên một XML namespace nội bộ cho client có WSDL riêng.
- Khi cấu hình interceptor tùy biến để chuyển đổi trước endpoint, phải kiểm tra rõ thứ tự với **WS-Security, schema validation, endpoint mapping và fault handling**; interceptor không mặc nhiên an toàn hoặc đúng với mọi dạng ký SOAP.

### Cách nhìn theo contract-first

Giả sử XSD đích khai báo:

~~~xml
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           targetNamespace="urn:internal:orders:v1"
           xmlns:c="urn:internal:orders:v1"
           elementFormDefault="qualified">
    <xs:element name="LookupOrderRequest">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="orderId" type="xs:string"/>
                <xs:element name="sourceChannel" type="xs:string"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
~~~

XSD này quy định rõ phần tử gốc, namespace, hai trường con, thứ tự của chúng và kiểu dữ liệu. **Stylesheet phải sinh payload thỏa hợp đồng**, chứ không phải sửa XSD cho vừa với kết quả của stylesheet. Nếu dùng WSDL ở cổng SOAP, cần xác định rõ XSD nào thuộc giao diện **đối tác nhìn thấy** và XSD nào thuộc phần **thích ứng nội bộ**.

## 6. Thực thi XSLT trong Java với JAXP

Java cung cấp API chuẩn **JAXP** để tạo bộ xử lý XSLT qua `TransformerFactory`, biên dịch stylesheet thành `Templates` và chạy biến đổi qua `Transformer`. Với cấu hình JAXP thông thường trong JDK, nên chuẩn bị stylesheet tương thích **XSLT 1.0**; hỗ trợ XSLT 2.0/3.0 phụ thuộc vào processor khác, ví dụ Saxon, và phải được xác nhận rõ bằng dependency/configuration.

Đoạn code sau đọc XML từ đối tác, dùng stylesheet đã kiểm soát, rồi JAXB unmarshal kết quả sang lớp `LookupOrderRequest` **đã được sinh/ánh xạ theo XSD đích**:

~~~java
import jakarta.xml.bind.JAXBContext;
import jakarta.xml.bind.Unmarshaller;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.transform.Templates;
import javax.xml.transform.Transformer;
import javax.xml.transform.TransformerFactory;
import javax.xml.transform.dom.DOMResult;
import javax.xml.transform.dom.DOMSource;
import javax.xml.transform.stream.StreamSource;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import org.w3c.dom.Document;

public final class XmlContractAdapter {
    // XSLT được lưu trong file đã được ứng dụng kiểm soát.
    public LookupOrderRequest adapt(Path stylesheet, InputStream sourceXml)
            throws Exception {

        DocumentBuilderFactory parserFactory = DocumentBuilderFactory.newInstance();
        parserFactory.setNamespaceAware(true);
        parserFactory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        parserFactory.setFeature(
                "http://apache.org/xml/features/disallow-doctype-decl", true);
        parserFactory.setXIncludeAware(false);
        parserFactory.setExpandEntityReferences(false);

        Document input = parserFactory.newDocumentBuilder().parse(sourceXml);

        TransformerFactory transformerFactory = TransformerFactory.newInstance();
        transformerFactory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        transformerFactory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        transformerFactory.setAttribute(XMLConstants.ACCESS_EXTERNAL_STYLESHEET, "");

        Templates templates;
        try (InputStream xsl = Files.newInputStream(stylesheet)) {
            templates = transformerFactory.newTemplates(new StreamSource(xsl));
        }

        Transformer transformer = templates.newTransformer();
        DOMResult transformed = new DOMResult();
        transformer.transform(new DOMSource(input), transformed);

        JAXBContext jaxb = JAXBContext.newInstance(LookupOrderRequest.class);
        Unmarshaller unmarshaller = jaxb.createUnmarshaller();
        return unmarshaller.unmarshal(
                new DOMSource(transformed.getNode()),
                LookupOrderRequest.class
        ).getValue();
    }
}
~~~

Ví dụ dùng `jakarta.xml.bind` theo các phiên bản Spring/Jakarta hiện đại. Nếu dự án cũ dùng `javax.xml.bind`, phải chọn API, runtime JAXB và mã được sinh cùng hệ phiên bản; **không trộn lẫn javax/jakarta JAXB**. `LookupOrderRequest` là tên lớp minh họa, chưa bao gồm mã sinh từ XSD và dependency cụ thể.

Về cơ chế:

1. XML nguồn được parse thành **DOM** với namespace và cấu hình parser hạn chế DOCTYPE.
2. `TransformerFactory` tạo `Templates` từ stylesheet, với quyền truy cập tài nguyên ngoài bị hạn chế.
3. Mỗi lần gọi, một `Transformer` xử lý `DOMSource` và tạo node XML đích qua `DOMResult`.
4. `Unmarshaller` chuyển node XML đích thành POJO JAXB.

**Giới hạn của code mẫu:** Đây là minh họa cho ranh giới kỹ thuật, không phải một HTTP/SOAP endpoint hoàn chỉnh. Chưa có schema validation, giới hạn kích thước input, thời gian xử lý, chính sách lỗi, cache `Templates`/`JAXBContext` hay xử lý stream lifecycle bên ngoài; các phần đó cần thêm trước khi chạy production. Nếu XML parser hoặc XSLT provider không hỗ trợ cài đặt bảo mật yêu cầu, nên **báo lỗi cấu hình và không tiếp tục bằng chế độ kém an toàn**.

### Cải thiện cho ứng dụng tải cao

- **Biên dịch stylesheet một lần** thành `Templates` khi khởi tạo ứng dụng hoặc khi triển khai phiên bản mapping mới. `Templates` có thể dùng lại đồng thời theo hợp đồng JAXP.
- Tạo **`Transformer` mới cho từng lần biến đổi**; đối tượng này không nên chia sẻ giữa các request đồng thời.
- Cache `JAXBContext` nếu phù hợp; tạo `Unmarshaller`/`Marshaller` riêng mỗi lần dùng hoặc quản lý vòng đời an toàn vì các đối tượng này không mặc định thread-safe.
- Với payload lớn, cân nhắc parser/processor hỗ trợ xử lý dòng; `DOMSource` và `DOMResult` dựng cây trong bộ nhớ nên chi phí tăng theo kích thước tài liệu. Không giả định mọi stylesheet XSLT có thể stream.

## 7. Thẩm định hợp đồng trước và sau khi biến đổi

Một request có thể **hợp lệ với XSD của đối tác** nhưng không hợp lệ với **XSD nội bộ** sau khi chuyển đổi. Hai kiểm tra giải quyết hai câu hỏi khác nhau:

~~~text
XML đối tác
  → validate theo XSD đối tác (nếu áp dụng)
  → XSLT
  → validate theo XSD đích
  → JAXB
  → nghiệp vụ
~~~

Ví dụ, XSLT sinh ra:

~~~xml
<c:LookupOrderRequest xmlns:c="urn:internal:orders:v1">
    <c:sourceChannel>WEB</c:sourceChannel>
    <c:orderId>A-0042</c:orderId>
</c:LookupOrderRequest>
~~~

Kết quả vẫn là XML well-formed, nhưng **không hợp lệ với XSD ví dụ** vì thứ tự `orderId` và `sourceChannel` bị đảo trong `xs:sequence`. JAXB có thể đọc được một số dữ liệu thiếu/sai thứ tự tùy binding và cách gọi, nên **unmarshal thành công không thể thay thế schema validation**.

Trong Java, có thể tạo `Schema` bằng `SchemaFactory` rồi gọi `schema.newValidator().validate(source)` trên **DOMSource đầu ra** trước khi chuyển sang JAXB. Khi nạp XSD, cũng phải chặn truy cập DTD/schema ngoài không được tin cậy, kiểm soát cơ chế resolve các `xs:include`/`xs:import` nếu schema thực sự cần chúng và không lấy schema tùy ý từ request.

Những điểm cần kiểm tra:

| Điều kiện | Ví dụ lỗi | Hậu quả |
| --- | --- | --- |
| Namespace URI / local name | Đầu ra dùng `urn:internal:orders:v2` thay `v1` | Không khớp phần tử gốc hoặc endpoint |
| Thứ tự / số lần xuất hiện | Sinh hai `orderId` khi XSD chỉ cho một | Sai `maxOccurs` |
| Dữ liệu bắt buộc | Bỏ `sourceChannel` | Sai `minOccurs` |
| Kiểu và định dạng | Gửi chữ vào phần tử `xs:decimal` | Lỗi validation/unmarshal |
| Giá trị rỗng so với không có node | `<amount/>` thay phần tử `amount` vắng mặt | Có thể thay đổi ngữ nghĩa của trường optional |
| Namespace của attribute | Tạo attribute có/không có namespace khác XSD | Sai hợp đồng |
| Ngày, timezone, tiền tệ | Đổi chuỗi nhưng không chuẩn hóa quy tắc | Có thể hợp schema nhưng sai nghiệp vụ |

Khi giữ được cả **mẫu XML nguồn, stylesheet và mẫu XML đích**, lỗi mapping thường dễ truy tìm hơn so với chỉ ghi log stack trace từ JAXB.

## 8. Bảo mật XML, XSLT và WS-Security

Các phép biến đổi XML xử lý dữ liệu đầu vào có thể do bên ngoài gửi, vì vậy phải coi payload là **không đáng tin cậy**. Một số nguồn rủi ro:

**XXE và thực thể XML:** Parser cho phép DTD và entity ngoài có thể đọc tệp hoặc gửi yêu cầu mạng ngoài dự kiến. Cấu hình parser an toàn trước khi đưa XML vào transformer; không chỉ dựa vào cài đặt của `TransformerFactory`.

**Truy cập tài nguyên của XSLT:** Các cú pháp như `xsl:include`, `xsl:import` hoặc hàm `document()` có thể tham chiếu tài nguyên bên ngoài. Giới hạn `ACCESS_EXTERNAL_STYLESHEET` và `ACCESS_EXTERNAL_DTD` khi provider hỗ trợ; nếu dự án thật sự cần import, dùng stylesheet tin cậy và resolver kiểm soát đích truy cập. Một số bộ xử lý còn cho phép **extension functions** hoặc gọi mã mở rộng; cần tắt hoặc giới hạn tùy provider.

**Từ chối dịch vụ:** Tài liệu XML rất lớn, lồng node quá sâu hoặc stylesheet có thuật toán tốn tài nguyên có thể làm cạn bộ nhớ/CPU. Giới hạn kích thước payload, thời gian xử lý, độ sâu/độ phức tạp thích hợp và theo dõi chi phí thực tế. `FEATURE_SECURE_PROCESSING` hỗ trợ giới hạn ở một số processor nhưng **không phải cơ chế bảo vệ toàn diện**.

**Stylesheet không được kiểm soát:** Không chấp nhận stylesheet do client upload rồi thực thi tùy ý. Stylesheet là logic thực thi trong XML processor và phải được quản lý cùng mã nguồn, review và versioning.

### Ranh giới cực kỳ quan trọng với chữ ký SOAP

Một chữ ký số WS-Security có thể bảo vệ chính phần SOAP Body. Nếu **sửa XML của phần đã ký sau khi chữ ký được tính**, chữ ký có thể không còn hợp lệ. Dù nhìn thấy dữ liệu tương đương, phép biến đổi cấu trúc, namespace hoặc canonicalized content có thể thay đổi giá trị chữ ký.

Vì vậy:

1. Đối với thông điệp **đi vào**, xác minh chữ ký, token, timestamp và chính sách WS-Security theo yêu cầu trước khi tin tưởng nội dung; xử lý payload adaptation ở ranh giới được thiết kế rõ ràng.
2. Với thông điệp **đi ra**, hoàn thiện payload cần gửi rồi áp dụng bước ký/bảo mật cho Envelope cuối cùng theo thứ tự thích hợp.
3. Không dùng XSLT như một cách tùy tiện sửa `wsse:Security`, signature, certificate hoặc SOAP Header. Những phần này cần SOAP/WS-Security stack chuyên dụng, chẳng hạn interceptor dựa trên WSS4J trong Spring-WS.

**TLS/mTLS và WS-Security khác phạm vi**: TLS bảo vệ kênh kết nối, còn chữ ký/mã hóa SOAP có thể bảo vệ nội dung thông điệp qua các bước trung gian theo chính sách tích hợp. XSLT không tự tạo cơ chế xác thực hay chứng thực dữ liệu.

### Lỗi transform nên thành lỗi giao tiếp có kiểm soát

Không để thông điệp lỗi parser hoặc đường dẫn tệp stylesheet nội bộ xuất thẳng về SOAP client. Phân loại:

- Input XML không well-formed, sai XSD hoặc thiếu trường bắt buộc: **lỗi dữ liệu yêu cầu**, thường phù hợp nhóm lỗi phía client của SOAP contract.
- Lỗi do stylesheet bị hỏng, triển khai sai phiên bản hoặc cấu hình bảo mật không hoạt động: **lỗi hệ thống**, cần log nội bộ và theo dõi.
- Xác minh chữ ký/chứng chỉ thất bại: **lỗi bảo mật**, xử lý theo chính sách WS-Security của dịch vụ, không cố biến đổi dữ liệu để vượt qua kiểm tra.

Trong Spring-WS, nên ánh xạ lỗi theo cách sinh **SOAP Fault phù hợp phiên bản SOAP và hợp đồng**, thay vì chỉ trả exception Java hoặc một JSON body không thuộc giao thức SOAP.

## 9. XSLT 1.0, 2.0 và 3.0: khả năng phụ thuộc processor

Phiên bản stylesheet và bộ xử lý phải tương thích:

| Phiên bản | Ví dụ khả năng | Lưu ý trong Java |
| --- | --- | --- |
| **XSLT 1.0** | Template, XPath 1.0, `for-each`, `choose`, `value-of`, `copy-of` | Thường là mức hỗ trợ mặc định có thể dựa vào với processor JDK thông dụng |
| **XSLT 2.0** | Hỗ trợ kiểu dữ liệu tốt hơn, grouping, hàm và biểu thức phong phú hơn | Cần processor hỗ trợ riêng; không mặc định có trên JDK |
| **XSLT 3.0** | Package, chức năng nâng cao, hỗ trợ stream trong điều kiện được processor cho phép | Cần processor tương ứng; tính năng và giấy phép có thể phụ thuộc edition |

Để giữ ví dụ chạy được ở môi trường Java thông thường, các stylesheet trong bài sử dụng cú pháp **1.0**. Nếu hợp đồng phức tạp đến mức cần grouping hoặc function hiện đại, hãy chọn processor và version trong dependency một cách có chủ đích; không đổi `version="3.0"` rồi kỳ vọng JAXP mặc định hỗ trợ.

Trong dự án thực tế, nên kiểm thử stylesheet với **đúng processor và phiên bản dùng khi deploy**, vì các chi tiết liên quan đến định dạng số, timezone, extension function, sắp thứ tự, serialization hoặc xử lý lỗi có thể khác nhau giữa implementation.

## 10. Kiểm thử biến đổi như một hợp đồng

Kiểm thử XSLT chỉ bằng cách xem “transform không ném exception” là chưa đủ. Nên xây dựng bộ mẫu gồm **XML nguồn + XML đích mong đợi + XSD đích**, đồng thời kiểm tra các tình huống lỗi và bảo mật.

| Nhóm kiểm thử | Tình huống | Điều cần xác nhận |
| --- | --- | --- |
| Happy path | OrderLookup hợp lệ có ID và channel | XML đích đúng QName và giá trị |
| Namespace | Nguồn đổi prefix `p` thành `q` nhưng URI giữ nguyên | Mapping vẫn hoạt động |
| Sai namespace | URI nguồn bị thay đổi | Từ chối hoặc phát hiện sai schema, không âm thầm trả response rỗng |
| Danh sách | 0, 1, nhiều `Line` | Số lượng, thứ tự và phần tử optional đúng XSD |
| Trường trống | Thiếu ID hoặc ID chỉ có khoảng trắng | Validation/logic nghiệp vụ xác định rõ kết quả |
| XML đặc biệt | `&amp;`, `&lt;`, Unicode tiếng Việt | Không mất hoặc làm hỏng ký tự |
| Kiểu dữ liệu | Thời gian có timezone, decimal, null | Đúng định dạng XSD và quy tắc domain |
| Tấn công XML | DOCTYPE, entity ngoài, import stylesheet ngoài | Parser/transformer từ chối theo cấu hình |
| SOAP thực tế | SOAP 1.1/1.2, Fault, Header, WS-Security | Không phá hợp đồng và bảo mật thông điệp |
| Tải cao | Payload lớn, nhiều request đồng thời | Không chia sẻ `Transformer` sai cách, không cạn bộ nhớ |

Một cách kiểm tra XML đích có ý nghĩa hơn so sánh string:

1. Parse XML đầu ra bằng parser có hỗ trợ namespace và cấu hình an toàn.
2. Kiểm tra QName của root và các node bằng XPath có khai báo prefix.
3. Validate theo XSD đích.
4. JAXB unmarshal để xác nhận lớp Java nhận được đủ dữ liệu.
5. Nếu dùng ở Spring-WS, kiểm tra request/response SOAP bằng `MockWebServiceClient` và kiểm tra SOAP client bằng `MockWebServiceServer` khi thích hợp.

Ví dụ assertion ở mức ý tưởng:

~~~text
Given:
  {urn:partner:orders:v1}OrderLookup
  ExternalId = " A-0042 ", ChannelCode = "WEB"

When:
  áp dụng stylesheet phiên bản đã triển khai

Then:
  root QName = {urn:internal:orders:v1}LookupOrderRequest
  /c:LookupOrderRequest/c:orderId = "A-0042"
  /c:LookupOrderRequest/c:sourceChannel = "WEB"
  validate XSD đích = PASS
  JAXB unmarshal = PASS
~~~

Nếu so sánh hai bản XML, nên cân nhắc so sánh theo cây hoặc canonicalization phù hợp thay vì so byte-by-byte; khác biệt prefix hoặc cách thụt dòng thường không làm đổi nghĩa của XML. Riêng các test về chữ ký số và tính tương thích phải dùng quy tắc canonicalization và chính sách chữ ký thực tế, không tự đơn giản hóa thành so sánh chuỗi.

## 11. Khi nào dùng XSLT và khi nào dùng ánh xạ đối tượng?

Một quy tắc thực hành hữu ích:

| Bối cảnh | Giải pháp gợi ý | Lý do |
| --- | --- | --- |
| Client và server cùng XSD, chỉ cần đối tượng Java | **JAXB** | Giữ cấu trúc theo hợp đồng, không cần lớp biến đổi bổ sung |
| Hai XSD khác nhau chủ yếu ở tên, namespace, tổ chức node | **XSLT → JAXB** | Tập trung logic thay đổi cấu trúc ở một nơi |
| Phải tra cứu database, áp dụng nhiều rule domain, tính tiền | **JAXB → Java mapper/service → JAXB** | Business logic cần typed Java, transaction và test nghiệp vụ |
| Chỉ cần chọn một vài field từ XML không phức tạp | **XPath hoặc JAXB** tùy tình huống | Có thể không cần stylesheet |
| Cần ký SOAP Body, kiểm tra UsernameToken, chứng chỉ | **WS-Security stack của Spring-WS** | Đây là chức năng bảo mật protocol |
| Có dịch vụ REST/JSON cần trao đổi với SOAP | **Adapter ở tầng giao tiếp + mapper** | XML/JSON serialization, transport và contract cần xử lý rõ ràng |

### Mẫu kiến trúc rõ trách nhiệm

~~~mermaid
flowchart TB
    P["Đối tác SOAP<br/>WSDL/XSD bên ngoài"] --> E["Spring-WS endpoint<br/>định tuyến và WS-Security"]
    E --> X["XML adapter<br/>XSLT nếu cần"]
    X --> V["Validate XSD đích"]
    V --> B["JAXB binding"]
    B --> S["Application / Domain service"]
    S --> R["Mapper phản hồi"]
    R --> E
~~~

Mỗi lớp có một tiêu chí đúng riêng: **Spring-WS** tuân thủ giao thức SOAP, **XSLT** tuân thủ mapping cấu trúc, **XSD** quy định dữ liệu hợp lệ, **JAXB** tuân thủ XML binding, còn **service** thực thi nghiệp vụ. Việc phân lớp giúp đối tác thay đổi tên field hoặc namespace mà không bắt buộc sửa thuật toán nghiệp vụ.

## 12. Bài thực hành tự kiểm tra

Giả sử đối tác đổi payload sang:

~~~xml
<q:OrderLookup xmlns:q="urn:partner:orders:v1">
    <q:ExternalId>B-0099</q:ExternalId>
    <q:ChannelCode>MOBILE</q:ChannelCode>
</q:OrderLookup>
~~~

Hãy thử:

1. Dùng lại stylesheet ở phần 2. Giải thích vì sao đổi prefix từ `p` sang `q` không làm mất khả năng match.
2. Kiểm tra đầu ra đúng `urn:internal:orders:v1` và thứ tự `orderId` trước `sourceChannel`.
3. Bỏ `ChannelCode` khỏi input rồi quan sát output; so sánh với XSD đích. Tìm hiểu vì sao **XSLT chạy xong** vẫn chưa có nghĩa là yêu cầu hợp lệ về nghiệp vụ.
4. Thử một đầu vào dùng namespace `urn:partner:orders:v2`; xác định cách ứng dụng nên báo lỗi thay vì âm thầm diễn giải sai hợp đồng.
5. Giải thích lý do một thao tác ký SOAP Body cần được đặt đúng thời điểm so với phép biến đổi XSLT.

**Điểm cốt lõi:** XSLT dùng để thay đổi **hình dạng của XML**; JAXB dùng để chuyển đổi **XML với đối tượng Java**; XSD/WSDL là **hợp đồng tích hợp** cần bảo vệ; Spring-WS quản lý **giao thức SOAP**; còn các quy tắc nghiệp vụ và WS-Security phải ở đúng tầng chuyên trách. Phân định được các ranh giới này giúp hệ thống contract-first tích hợp ổn định, kiểm thử được và dễ thay đổi khi hợp đồng XML của đối tác tiến hóa.
