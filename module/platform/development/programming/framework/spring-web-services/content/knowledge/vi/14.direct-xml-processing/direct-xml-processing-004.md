# XPathExpression, XPathOperations và truy xuất dữ liệu có namespace

> **Chương:** Xử lý XML trực tiếp  
> **Module:** SPRING_WEB_SERVICES — phát triển dịch vụ SOAP contract-first bằng Spring Web Services (Spring-WS), thiết kế XSD/WSDL, ánh xạ JAXB, xây dựng endpoint và SOAP client; đồng thời kiểm soát SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và khả năng tương thích giữa các hệ thống doanh nghiệp.

## 1. Mục tiêu và bối cảnh

Không phải SOAP endpoint nào cũng cần sinh một lớp JAXB đầy đủ cho từng request. Khi chỉ cần đọc một vài trường, khi hỗ trợ hợp đồng XML cũ nhiều phần tử mở rộng hoặc khi muốn trích xuất dữ liệu từ một tài liệu XML đã có, ta có thể dùng **XPath** để truy vấn trực tiếp cây XML.

Spring-WS cung cấp hai nhóm API trong package `org.springframework.xml.xpath`:

- **`XPathExpression`:** một biểu thức XPath được **biên dịch trước**, tạo bằng `XPathExpressionFactory` hoặc `XPathExpressionFactoryBean`, được đánh giá với một `org.w3c.dom.Node`.
- **`XPathOperations`:** interface thực hiện XPath từ chuỗi expression tại thời điểm gọi, với tham số context là `javax.xml.transform.Source`; các implementation điển hình là `Jaxp13XPathTemplate` và `JaxenXPathTemplate`.

XPath giúp chọn phần tử chính xác, nhưng **không thay thế XSD validation, JAXB khi cần model lớn, hay kiểm tra quyền nghiệp vụ**. Bài học tập trung vào cách dùng đúng hai API và, quan trọng nhất, cách truy vấn **namespace URI + local name** chứ không dựa vào prefix XML xuất hiện trên wire.

Sau bài học, bạn cần có khả năng:

1. Viết XPath 1.0 để lấy một phần tử, attribute, chuỗi, số, boolean hoặc nhiều node.
2. Giải thích vì sao `//invoiceId` thường không trả kết quả khi XML dùng default namespace.
3. Tạo map prefix → namespace URI và dùng cùng một XPath với các XML instance có prefix khác nhau.
4. Phân biệt `XPathExpression.evaluateAsString(Node)` với `XPathOperations.evaluateAsString(String, Source)`.
5. Viết `@Endpoint` đọc payload SOAP bằng DOM/XPath, xây response đúng XSD/WSDL.
6. Kiểm thử lỗi namespace, thiếu field, duplicate nodes, XML bảo mật và hồi quy với SOAP client độc lập.

## 2. Dữ liệu mẫu: một request SOAP có namespace

Ví dụ dịch vụ hóa đơn nhận request có mã hóa đơn, người mua và các dòng sản phẩm. SOAP 1.1 Envelope:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:inv="urn:example:invoices:v1">
  <soapenv:Header/>
  <soapenv:Body>
    <inv:GetInvoiceRequest>
      <inv:invoiceId>INV-1001</inv:invoiceId>
      <inv:customer>
        <inv:id>CUS-009</inv:id>
        <inv:displayName>Nguyễn An</inv:displayName>
      </inv:customer>
      <inv:lines>
        <inv:line status="ACTIVE">
          <inv:sku>BOOK-01</inv:sku>
          <inv:quantity>2</inv:quantity>
          <inv:unitPrice>125000.50</inv:unitPrice>
        </inv:line>
        <inv:line status="CANCELLED">
          <inv:sku>PEN-02</inv:sku>
          <inv:quantity>1</inv:quantity>
          <inv:unitPrice>18000.00</inv:unitPrice>
        </inv:line>
      </inv:lines>
    </inv:GetInvoiceRequest>
  </soapenv:Body>
</soapenv:Envelope>
~~~

Trong Spring-WS, `@RequestPayload Element` thường cung cấp trực tiếp element `inv:GetInvoiceRequest`. Từ đó, **node context** cho XPath là payload root chứ không nhất thiết là toàn bộ SOAP Envelope.

~~~mermaid
flowchart TD
    A["SOAP Envelope"] --> B["SOAP Body"]
    B --> C["Payload root: GetInvoiceRequest"]
    C --> D["invoiceId"]
    C --> E["customer"]
    E --> F["id"]
    E --> G["displayName"]
    C --> H["lines"]
    H --> I["line 1: ACTIVE"]
    H --> J["line 2: CANCELLED"]
    I --> K["sku / quantity / unitPrice"]
    J --> L["sku / quantity / unitPrice"]
~~~

Với payload root `GetInvoiceRequest`, ta có thể chọn mã hóa đơn bằng biểu thức:

~~~xpath
./i:invoiceId
~~~

Ở đây `i` là **prefix dành cho biểu thức XPath**, được ứng dụng gắn với namespace URI `urn:example:invoices:v1`. Nó **không bắt buộc** giống prefix `inv` trong XML request.

### 2.1. Một XSD tối thiểu cho ví dụ

XSD giúp xác định chính xác kiểu, thứ tự và namespace mà hai phía SOAP đã ký kết:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:tns="urn:example:invoices:v1"
    targetNamespace="urn:example:invoices:v1"
    elementFormDefault="qualified">

  <xs:element name="GetInvoiceRequest">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="invoiceId" type="xs:string"/>
        <xs:element name="customer">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="id" type="xs:string"/>
              <xs:element name="displayName" type="xs:string"
                          minOccurs="0"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
        <xs:element name="lines">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="line" minOccurs="1"
                          maxOccurs="unbounded">
                <xs:complexType>
                  <xs:sequence>
                    <xs:element name="sku" type="xs:string"/>
                    <xs:element name="quantity"
                                type="xs:positiveInteger"/>
                    <xs:element name="unitPrice" type="xs:decimal"/>
                  </xs:sequence>
                  <xs:attribute name="status"
                                type="xs:string"
                                use="required"/>
                </xs:complexType>
              </xs:element>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

  <xs:element name="GetInvoiceResponse">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="invoiceId" type="xs:string"/>
        <xs:element name="accepted" type="xs:boolean"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
~~~

Cặp element `GetInvoiceRequest` và `GetInvoiceResponse` thường được WSDL 1.1 document/literal tham chiếu qua `wsdl:part/@element`. `elementFormDefault="qualified"` khiến các **child elements** thuộc namespace `urn:example:invoices:v1`. Ngược lại, attribute `status` không có prefix vì attribute cục bộ mặc định là **unqualified** khi `attributeFormDefault` không đặt thành `qualified`.

**Chú ý:** XSD này cho `status` một chuỗi tùy ý để tập trung vào XPath. Dịch vụ thật có thể hạn chế nó thành enum, `pattern` hoặc một type chuyên biệt; XPath không tự áp những ràng buộc đó.

## 3. XPath 1.0: cú pháp cần dùng đúng

Spring-XML hỗ trợ XPath thông qua JAXP/Jaxen. Với tính tương thích SOAP doanh nghiệp, nên bắt đầu từ **các biểu thức XPath 1.0 phổ biến** thay vì mặc định runtime có XPath 2.0/3.x.

| Biểu thức từ payload root | Kết quả | Ghi chú |
|---|---|---|
| `./i:invoiceId` | Element `invoiceId` trực tiếp dưới root | `.` nghĩa là context hiện tại |
| `string(./i:invoiceId)` | Chuỗi `INV-1001` | Trả dạng string |
| `normalize-space(./i:invoiceId)` | Chuỗi đã loại whitespace thừa ở đầu/cuối, gộp chuỗi khoảng trắng | Không nên tự làm nếu whitespace có ý nghĩa nghiệp vụ |
| `./i:customer/i:id` | Element `id` của customer | Đường dẫn cha–con |
| `./i:lines/i:line` | Hai node `line` | Dùng hàm trả danh sách node |
| `./i:lines/i:line[1]` | Dòng đầu của nhóm line | XPath predicate vị trí |
| `./i:lines/i:line[@status='ACTIVE']` | Các dòng có attribute status ACTIVE | `@status` không namespace |
| `./i:lines/i:line[@status='ACTIVE']/i:sku` | SKU của dòng ACTIVE | Chọn điều kiện trước khi lấy child |
| `count(./i:lines/i:line)` | `2` | Kết quả số XPath là dạng double |
| `boolean(./i:customer/i:id)` | `true` nếu tồn tại node | Không kiểm tra nội dung đúng schema |
| `./i:lines/i:line[last()]/i:sku` | SKU dòng cuối | Predicate `last()` |
| `.//i:sku` | SKU ở mọi độ sâu dưới context | Rộng hơn đường dẫn trực tiếp |

**Phân biệt `/`, `./` và `//`**:

- `/i:GetInvoiceRequest/...` là XPath tuyệt đối từ document root; phù hợp khi document đầy đủ là context hoặc engine xử lý context Node có owner document đúng.
- `./i:invoiceId` đọc child trực tiếp **của node context**. Đây là lựa chọn dễ hiểu khi `@RequestPayload Element` đã cung cấp `GetInvoiceRequest`.
- `.//i:invoiceId` tìm ở mọi mức bên dưới context. Nó có thể vô tình chọn một `invoiceId` lồng sâu khác trong tương lai khi schema tiến hóa.
- `//i:invoiceId` có thể tìm rộng trên cây tài liệu, dễ che giấu lỗi cấu trúc. Đừng dùng như giải pháp “tạm” khi quên namespace.

### 3.1. XPath phân biệt element và attribute

Vì `status` là attribute **không namespace**, điều kiện đúng:

~~~xpath
./i:lines/i:line[@status='ACTIVE']
~~~

Nếu dùng `@i:status`, XPath sẽ tìm attribute có namespace `urn:example:invoices:v1`, khác với attribute `status` không prefix trong mẫu.

### 3.2. Hàm string, boolean, number có semantics riêng

- `string(node-set)` trong XPath 1.0 thường lấy **string-value của node đầu tiên theo document order**; không tự xác nhận chỉ có đúng một node.
- `boolean(node-set)` chỉ cho biết node-set rỗng hay không, không xác minh text field có khác rỗng hoặc đúng format.
- `number(...)` tạo giá trị số kiểu XPath double; nếu lexical không chuyển được, có thể thành `NaN`. Đối với tiền/currency, **đừng dùng kết quả double để tính toán tài chính**.
- `count(...)` trả một giá trị số, không phải danh sách node.
- `normalize-space(...)` có thể hữu ích với field dạng mã, nhưng làm thay đổi whitespace; chỉ dùng nếu contract cho phép.

Trong kiểm tra nghiệp vụ, phải phân biệt “không tồn tại node”, “có một node với chuỗi rỗng”, “có nhiều node” và “node có giá trị không hợp lệ”. Một lệnh `evaluateAsString` đơn lẻ không bảo đảm các điều này.

## 4. Namespace trong XPath: bẫy quan trọng nhất

### 4.1. Prefix của XPath do ứng dụng định nghĩa

XML client có thể gửi cùng payload dưới ba dạng sau:

~~~xml
<inv:GetInvoiceRequest xmlns:inv="urn:example:invoices:v1">
  <inv:invoiceId>INV-1001</inv:invoiceId>
</inv:GetInvoiceRequest>
~~~

~~~xml
<x:GetInvoiceRequest xmlns:x="urn:example:invoices:v1">
  <x:invoiceId>INV-1001</x:invoiceId>
</x:GetInvoiceRequest>
~~~

~~~xml
<GetInvoiceRequest xmlns="urn:example:invoices:v1">
  <invoiceId>INV-1001</invoiceId>
</GetInvoiceRequest>
~~~

Ba instance (đã lược các field khác của XSD để minh họa QName) đều có cùng root QName và child QName. Biểu thức `./i:invoiceId` sẽ tìm được field trong cả ba **nếu** namespace map của XPath đăng ký `i → urn:example:invoices:v1`.

**Không được phụ thuộc prefix `inv` của người gửi.** Prefix là bí danh, không thuộc danh tính của element. Điều cần so khớp là cặp `{namespaceURI}localName`.

### 4.2. Default namespace của XML không tự áp dụng cho tên XPath

Đây là điểm dễ nhầm:

~~~xpath
./invoiceId
~~~

Biểu thức trên tìm element tên `invoiceId` **không có namespace**, ngay cả khi XML dùng `xmlns="urn:example:invoices:v1"` cho các phần tử.

Muốn tìm element có namespace, phải đăng ký prefix XPath và viết:

~~~xpath
./i:invoiceId
~~~

Namespace map là **dữ liệu cấu hình của XPath evaluator**, ví dụ:

~~~java
import java.util.Map;

private static final String NS = "urn:example:invoices:v1";

private static final Map<String, String> XPATH_NAMESPACES =
        Map.of("i", NS);
~~~

Dấu `i` có thể đổi thành `a`, `invoice` hoặc tên khác, miễn **biểu thức XPath và namespace map tương ứng**. `Map.of` tạo map không chỉnh sửa trong Java hiện đại, phù hợp với cấu hình cố định.

### 4.3. Nhiều namespace trong cùng một tài liệu

Trong SOAP, namespace của Envelope khác namespace payload:

~~~text
SOAP 1.1 Envelope:
http://schemas.xmlsoap.org/soap/envelope/

Business payload:
urn:example:invoices:v1
~~~

Nếu XPath context là **toàn bộ Envelope**, truy vấn tuyệt đối có thể là:

~~~xpath
/s:Envelope/s:Body/i:GetInvoiceRequest/i:invoiceId
~~~

Phải đăng ký cả hai prefix:

~~~java
Map<String, String> namespaces = Map.of(
    "s", "http://schemas.xmlsoap.org/soap/envelope/",
    "i", "urn:example:invoices:v1"
);
~~~

Nếu context là **`@RequestPayload Element`**, bạn đã ở root `GetInvoiceRequest` và nên dùng đường dẫn tương đối `./i:invoiceId`. Một biểu thức trên Envelope **không** hoạt động khi chỉ được cung cấp node payload; lỗi này liên quan **context node**, không nhất thiết do namespace sai.

Khi có child element của namespace bên thứ ba, chẳng hạn `{urn:partner:common:v1}referenceId`, đăng ký prefix riêng `c` và dùng `c:referenceId`. XSD của service phải khai báo đúng cấu trúc/import/wildcard cho phần tử đó; XPath tìm được node không có nghĩa message hợp lệ với schema.

### 4.4. Có nên dùng local-name() thay namespace?

Biểu thức “chống cháy”:

~~~xpath
./*[local-name()='invoiceId']
~~~

có thể chọn cả các element thuộc namespace sai. Khi có nhiều namespace chứa cùng local name, nguy cơ đọc nhầm dữ liệu tăng. Nếu cần một XPath chung nhưng **phải kiểm tra cả QName**, có thể viết:

~~~xpath
./*[local-name()='invoiceId'
    and namespace-uri()='urn:example:invoices:v1']
~~~

Tuy nhiên, cách dùng prefix + namespace map rõ ràng, dễ đọc, dễ review hơn cho một contract đã biết. `local-name()`/`namespace-uri()` chỉ nên dùng ở những chỗ thật sự cần thao tác XML động và được kiểm thử kỹ.

## 5. `XPathExpression`: biên dịch XPath khi cấu hình đã biết

Spring-XML định nghĩa `org.springframework.xml.xpath.XPathExpression` là abstraction cho một biểu thức đã biên dịch. Tạo bằng `XPathExpressionFactory.createXPathExpression(...)`:

~~~java
import java.util.Map;
import org.springframework.xml.xpath.XPathExpression;
import org.springframework.xml.xpath.XPathExpressionFactory;
import org.w3c.dom.Element;

public final class InvoiceXPathReader {
    private static final String NS = "urn:example:invoices:v1";

    public String readInvoiceId(Element payload) {
        XPathExpression expression =
                XPathExpressionFactory.createXPathExpression(
                        "./i:invoiceId",
                        Map.of("i", NS));

        return expression.evaluateAsString(payload);
    }
}
~~~

**Quan trọng về API:** `XPathExpression` của Spring-XML **không phải** interface `javax.xml.xpath.XPathExpression` trong JDK, dù Spring có thể dùng JAXP bên dưới. Các method trên Spring `XPathExpression` nhận **`Node`**, không nhận trực tiếp `Source` hoặc chuỗi expression ở mỗi lượt gọi.

Ví dụ này tạo expression ngay trong method để thể hiện đầy đủ cách dùng và tránh chia sẻ cùng một evaluator giữa các request. Trong ứng dụng có lưu lượng lớn, có thể biên dịch/cấu hình trước và tái sử dụng theo **mô hình an toàn luồng mà implementation hỗ trợ**; không tự suy luận mọi `javax.xml.xpath.XPathExpression` ở bên dưới là thread-safe. Với resolver cụ thể của project, cần kiểm chứng concurrency hoặc dùng giải pháp tạo evaluator riêng theo lượt xử lý.

### 5.1. Các phương thức cốt lõi

| Phương thức `XPathExpression` | Kiểu trả về | Dùng để làm gì |
|---|---|---|
| `evaluateAsString(Node)` | `String` | Giá trị text/chuỗi của kết quả |
| `evaluateAsBoolean(Node)` | `boolean` | Kiểm tra điều kiện XPath |
| `evaluateAsNumber(Node)` | `double` | Đánh giá biểu thức số |
| `evaluateAsNode(Node)` | `Node` | Lấy một node được chọn |
| `evaluateAsNodeList(Node)` | `List<Node>` | Lấy các node thỏa điều kiện |
| `evaluateAsObject(Node, NodeMapper<T>)` | `T` | Ánh xạ một node sang một Java object |
| `evaluate(Node, NodeMapper<T>)` | `List<T>` | Ánh xạ một danh sách nodes |

Tên method dễ nhầm: `XPathExpression` dùng **`evaluateAsNumber`**, còn `XPathOperations` dùng **`evaluateAsDouble`**. Chúng không hoàn toàn có cùng API signature.

### 5.2. Chọn đúng kiểu kết quả để tránh đọc nhầm

Một XPath chọn node, ví dụ:

~~~xpath
./i:invoiceId
~~~

Có thể đánh giá theo ba mục đích:

~~~java
XPathExpression expr =
        XPathExpressionFactory.createXPathExpression(
                "./i:invoiceId", Map.of("i", NS));

Node node = expr.evaluateAsNode(payload);
String value = expr.evaluateAsString(payload);
List<Node> nodes = expr.evaluateAsNodeList(payload);
~~~

- `evaluateAsNode` hữu ích để kiểm tra **không có node** (thường trả `null`) trước khi đọc text.
- `evaluateAsString` dùng khi bạn chỉ cần scalar string, nhưng đừng lấy nó làm chứng minh rằng node tồn tại duy nhất.
- `evaluateAsNodeList` phù hợp khi muốn yêu cầu **đúng một node** hoặc xử lý nhiều dòng.

Ví dụ ràng buộc chính xác một `invoiceId`:

~~~java
XPathExpression idExpr =
        XPathExpressionFactory.createXPathExpression(
                "./i:invoiceId", Map.of("i", NS));

List<Node> matches = idExpr.evaluateAsNodeList(payload);
if (matches.size() != 1) {
    throw new IllegalArgumentException(
            "Exactly one invoiceId element is required");
}

String invoiceId = matches.get(0).getTextContent().trim();
if (invoiceId.isEmpty()) {
    throw new IllegalArgumentException("invoiceId must not be blank");
}
~~~

Đây là kiểm tra tại lớp ứng dụng; **không thay thế** validator XSD, nhưng minh họa cách xử lý tình huống XPath trả node-set không như mong đợi.

### 5.3. Dùng NodeMapper để ánh xạ nhiều nodes

`NodeMapper<T>` của Spring-XML có phương thức `mapNode(Node node, int nodeNum)`. Nó khác cách viết lambda chỉ có một tham số:

~~~java
import java.util.List;
import org.springframework.xml.xpath.XPathExpression;
import org.springframework.xml.xpath.XPathExpressionFactory;
import org.w3c.dom.Node;

XPathExpression lineExpr =
        XPathExpressionFactory.createXPathExpression(
                "./i:lines/i:line[@status='ACTIVE']",
                Map.of("i", NS));

List<String> activeSkus = lineExpr.evaluate(
        payload,
        (Node line, int nodeNum) -> {
            XPathExpression skuExpr =
                    XPathExpressionFactory.createXPathExpression(
                            "./i:sku", Map.of("i", NS));
            Node sku = skuExpr.evaluateAsNode(line);
            if (sku == null) {
                throw new IllegalArgumentException(
                        "Missing sku at index " + nodeNum);
            }
            return sku.getTextContent().trim();
        });
~~~

Ví dụ bảo đảm XPath thứ hai được đánh giá từ **context node của từng `line`**, không phải từ root request. Với lưu lượng cao, có thể tổ chức biên dịch expression theo cấu hình của ứng dụng và chính sách thread-safety phù hợp, thay vì biên dịch `skuExpr` lặp lại trong callback. Bài học ưu tiên minh họa đúng **ngữ nghĩa context và chữ ký NodeMapper**.

## 6. `XPathOperations`: linh hoạt với XPath truyền theo từng lần gọi

`XPathOperations` là một interface khác trong Spring-XML:

~~~java
org.springframework.xml.xpath.XPathOperations
~~~

Các implementation thông thường:

- `Jaxp13XPathTemplate` — dựa trên JAXP XPath trong Java, có trong JVM hiện đại.
- `JaxenXPathTemplate` — dựa trên thư viện Jaxen khi được cấu hình và có dependency tương ứng.

Lợi ích của `XPathOperations` là truyền XPath string vào lúc gọi, phù hợp trường hợp cần nhiều biểu thức hoặc yêu cầu truy vấn thay đổi có kiểm soát. Tài liệu API cũng lưu ý kiểu template không dùng biểu thức được biên dịch sẵn theo mô hình `XPathExpression`; với truy vấn cố định chạy rất nhiều lần, có thể cân nhắc biểu thức compiled và chiến lược tái sử dụng phù hợp.

### 6.1. Cấu hình Jaxp13XPathTemplate với namespace map

~~~java
import java.util.Map;
import javax.xml.transform.Source;
import javax.xml.transform.dom.DOMSource;

import org.springframework.xml.xpath.Jaxp13XPathTemplate;
import org.springframework.xml.xpath.XPathOperations;
import org.w3c.dom.Element;

public class InvoiceOperationsReader {
    private static final String NS = "urn:example:invoices:v1";

    private final XPathOperations xpath;

    public InvoiceOperationsReader() {
        Jaxp13XPathTemplate template = new Jaxp13XPathTemplate();
        template.setNamespaces(Map.of("i", NS));
        this.xpath = template;
    }

    public String invoiceId(Element payload) {
        Source source = new DOMSource(payload);
        return xpath.evaluateAsString(
                "./i:invoiceId", source);
    }

    public double lineCount(Element payload) {
        return xpath.evaluateAsDouble(
                "count(./i:lines/i:line)",
                new DOMSource(payload));
    }
}
~~~

Lưu ý:

- `XPathOperations` nhận **`String expression` và `Source context`** ở mỗi lần gọi, không nhận trực tiếp `Node` như `XPathExpression`.
- `setNamespaces(Map<String, String>)` được gọi trên implementation `Jaxp13XPathTemplate` trước khi bắt đầu sử dụng nó; không thay namespace map liên tục trong lúc nhiều request đang xử lý.
- `DOMSource(payload)` là cầu nối từ DOM `Element` sang JAXP `Source`.
- `lineCount` trả `double` theo semantics XPath 1.0; dù kết quả là số lượng nguyên, chữ ký API vẫn là double.
- Một số `Source` như stream có thể chỉ đọc được một lần. Nếu cần chạy nhiều XPath, cân nhắc DOM đã được chuẩn bị an toàn hoặc tạo `Source` mới cho mỗi lượt.

### 6.2. Danh sách phương thức của XPathOperations

| Phương thức | Kiểu trả về | So sánh với XPathExpression |
|---|---|---|
| `evaluateAsString(String, Source)` | `String` | Expression là tham số thay vì compiled field |
| `evaluateAsBoolean(String, Source)` | `boolean` | Đánh giá giá trị true/false |
| `evaluateAsDouble(String, Source)` | `double` | Tương ứng ý nghĩa với `evaluateAsNumber(Node)` |
| `evaluateAsNode(String, Source)` | `Node` | Chọn một node |
| `evaluateAsNodeList(String, Source)` | `List<Node>` | Chọn nhiều nodes |
| `evaluateAsObject(String, Source, NodeMapper<T>)` | `T` | Ánh xạ một node |
| `evaluate(String, Source, NodeMapper<T>)` | `List<T>` | Ánh xạ một tập node |
| `evaluate(String, Source, NodeCallbackHandler)` | `void` | Callback xử lý từng node |

Các phiên bản có thể dùng annotation nullability khác nhau; hãy xác minh tài liệu API của dependency đang chạy, đặc biệt với trường hợp không chọn được node.

### 6.3. Truy vấn nhiều dòng bằng XPathOperations

~~~java
XPathOperations xpath = /* bean đã cấu hình namespace i */;

List<Node> lineNodes = xpath.evaluateAsNodeList(
        "./i:lines/i:line",
        new DOMSource(payload));

List<String> activeSkus = xpath.evaluate(
        "./i:lines/i:line[@status='ACTIVE']",
        new DOMSource(payload),
        (node, nodeNum) -> {
            // node hiện là <i:line>; có thể xử lý DOM tại đây.
            // Với dữ liệu nghiệp vụ lớn, tách mapper thành class riêng.
            return node.getTextContent().trim();
        });
~~~

`lineNodes` là các `Node`; `activeSkus` trong ví dụ trên thực ra sẽ là **toàn bộ text kết hợp của line**, không phải chỉ field SKU. Muốn kết quả chỉ gồm SKU, hãy đổi XPath trực tiếp thành `./i:lines/i:line[@status='ACTIVE']/i:sku` rồi map text của từng SKU node:

~~~java
List<String> skus = xpath.evaluate(
        "./i:lines/i:line[@status='ACTIVE']/i:sku",
        new DOMSource(payload),
        (node, nodeNum) -> node.getTextContent().trim());
~~~

Đây là ưu điểm của XPath: chọn đúng node mục tiêu thay vì lấy tất cả text con rồi tách chuỗi thủ công.

## 7. So sánh hai API và quy tắc chọn

| Tiêu chí | XPathExpression | XPathOperations |
|---|---|---|
| Cách xây | `XPathExpressionFactory.createXPathExpression(expression, namespaces)` | Chọn template `Jaxp13XPathTemplate`/`JaxenXPathTemplate` |
| XPath nằm ở đâu? | Được biên dịch khi tạo object | Chuỗi truyền tại mỗi lời gọi |
| Context | `org.w3c.dom.Node` | `javax.xml.transform.Source` |
| Ví dụ scalar | `evaluateAsString(node)` | `evaluateAsString(xpath, source)` |
| Ví dụ số | `evaluateAsNumber(node)` | `evaluateAsDouble(xpath, source)` |
| Namespace | Map khi tạo expression | `setNamespaces(map)` trên template |
| Linh hoạt | Thấp hơn, biểu thức cố định | Cao hơn, nhiều expression khác nhau |
| Hiệu năng | Tránh parse/compile lại biểu thức; cần xem concurrency | Có overhead phân tích expression mỗi lượt tùy implementation |
| Cách dùng tốt | Truy vấn lặp lại, cấu trúc cố định | Công cụ đọc XML, truy vấn linh hoạt có kiểm soát |

**Lựa chọn thực tế:** không bắt buộc mọi endpoint đều dùng XPath. Nếu schema ổn định, request có nhiều field nghiệp vụ và cần validate/serialize nhiều phần tử, **JAXB từ XSD** thường dễ duy trì hơn. XPath phù hợp hơn khi chỉ đọc một nhóm field, cần xét attribute/nested nodes đặc thù hoặc cần phân tích một thông điệp XML đã có.

## 8. Namespace và XPath trong một @Endpoint Spring-WS

Dưới đây là endpoint đọc `GetInvoiceRequest` bằng `XPathOperations` và trả `GetInvoiceResponse` bằng DOM. Ví dụ này giữ contract-first: request/response phải khớp XSD ở mục 2.

~~~java
package com.example.invoice.endpoint;

import java.util.List;
import java.util.Map;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.parsers.ParserConfigurationException;
import javax.xml.transform.Source;
import javax.xml.transform.dom.DOMSource;

import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;
import org.springframework.xml.xpath.Jaxp13XPathTemplate;
import org.springframework.xml.xpath.XPathOperations;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;

@Endpoint
public class InvoiceEndpoint {
    private static final String NS = "urn:example:invoices:v1";

    private final XPathOperations xpath;

    public InvoiceEndpoint() {
        Jaxp13XPathTemplate template = new Jaxp13XPathTemplate();
        template.setNamespaces(Map.of("i", NS));
        this.xpath = template;
    }

    @PayloadRoot(namespace = NS, localPart = "GetInvoiceRequest")
    @ResponsePayload
    public Source getInvoice(@RequestPayload Element request)
            throws ParserConfigurationException {

        List<Node> ids = xpath.evaluateAsNodeList(
                "./i:invoiceId", new DOMSource(request));
        if (ids.size() != 1) {
            throw new IllegalArgumentException(
                    "Exactly one invoiceId is required");
        }

        String invoiceId = ids.get(0).getTextContent().trim();
        if (invoiceId.isEmpty()) {
            throw new IllegalArgumentException(
                    "invoiceId must not be blank");
        }

        // Truy cập số lượng line bằng XPath, không dùng double để
        // tính toán tiền hoặc precision cao.
        double count = xpath.evaluateAsDouble(
                "count(./i:lines/i:line)",
                new DOMSource(request));
        boolean accepted = count > 0;

        Document doc = DocumentBuilderFactory
                .newInstance().newDocumentBuilder().newDocument();

        Element root = doc.createElementNS(
                NS, "i:GetInvoiceResponse");
        root.setAttributeNS(
                "http://www.w3.org/2000/xmlns/",
                "xmlns:i", NS);
        doc.appendChild(root);

        Element idElement = doc.createElementNS(NS, "i:invoiceId");
        idElement.setTextContent(invoiceId);
        root.appendChild(idElement);

        Element result = doc.createElementNS(NS, "i:accepted");
        result.setTextContent(Boolean.toString(accepted));
        root.appendChild(result);

        return new DOMSource(root);
    }
}
~~~

Điểm chính:

1. `@PayloadRoot(namespace, localPart)` chọn method bằng QName của **request root**, không chạy XPath để chọn method.
2. `@RequestPayload Element` đã cung cấp DOM payload; XPath `./i:invoiceId` là đường dẫn **tương đối** đến child của payload.
3. `XPathOperations` được cấu hình một map prefix riêng. `i` không cần giống prefix `inv` của SOAP client.
4. `evaluateAsNodeList` được dùng để phát hiện thiếu/trùng trường; `count(...)` minh họa kết quả số.
5. `@ResponsePayload Source` trả DOM payload có QName `{urn:example:invoices:v1}GetInvoiceResponse`. Spring-WS sẽ đóng gói nó trong SOAP Envelope.
6. `setTextContent` tránh lỗi XML escaping khi giá trị chứa `&`, `<` hoặc ký tự đặc biệt.
7. `DocumentBuilderFactory.newDocumentBuilder().newDocument()` **chỉ tạo tài liệu mới**, không parse XML từ nguồn chưa tin cậy ở đây. Parser đọc XML từ client cần được framework/hạ tầng cấu hình an toàn.

Đây là logic minh họa; trong production, acceptance phải dựa trên business service, quyền truy cập và validation thật. Không nên tính invoice total hoặc quyết định giao dịch chỉ bằng XPath `count(...)`. Đặc biệt, **endpoint này không tự chạy XSD validation** chỉ vì schema tồn tại trên classpath.

### 8.1. Response SOAP mẫu

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:i="urn:example:invoices:v1">
  <soapenv:Body>
    <i:GetInvoiceResponse>
      <i:invoiceId>INV-1001</i:invoiceId>
      <i:accepted>true</i:accepted>
    </i:GetInvoiceResponse>
  </soapenv:Body>
</soapenv:Envelope>
~~~

Với SOAP client dùng JAXB/CXF, prefix XML có thể khác nhưng QName và thứ tự các child elements phải đúng XSD/WSDL. Nếu WSDL của đối tác dùng namespace khác hoặc root element tên khác, phải điều chỉnh **contract và annotation**, không chỉ sửa XPath.

## 9. Payload XPath khác với truy vấn cả SOAP Envelope/Header

Trong Spring-WS, `@RequestPayload Element` đưa vào method **phần XML payload** của SOAP Body. Bạn không mặc nhiên nhận được toàn bộ SOAP Envelope:

~~~text
Envelope
├── Header
│   └── wsse:Security / correlation ID / metadata...
└── Body
    └── i:GetInvoiceRequest   ← @RequestPayload Element
        ├── i:invoiceId
        ├── i:customer
        └── i:lines
~~~

Do đó:

~~~xpath
./i:invoiceId
~~~

hợp lý với context là payload element. Còn biểu thức:

~~~xpath
/s:Envelope/s:Header/m:correlationId
~~~

**không thể** tự hoạt động khi bạn chỉ cung cấp `Element GetInvoiceRequest`. Muốn đọc SOAP Header, sử dụng API SOAP message/header hoặc annotation hỗ trợ phù hợp của Spring-WS và thiết lập namespace riêng; đừng mở rộng XPath root giả định đã chứa cả Header.

### 9.1. Vì sao phân biệt này quan trọng?

- **Dispatch:** `@PayloadRoot` chọn method dựa trên QName của request payload root, không dựa vào một XPath tùy ý.
- **Security:** WS-Security thường nằm trong SOAP Header. Header security cần được xử lý và xác minh bởi thành phần WS-Security đúng chuẩn, **không đọc vài field bằng XPath rồi coi đó là xác thực thành công**.
- **Tracing:** một correlation ID trong Header khác dữ liệu nghiệp vụ trong Body; nó có thể bị spoof nếu ứng dụng chưa kiểm tra nguồn tin cậy.
- **Contract:** WSDL/XSD định nghĩa payload và header theo binding, không phải mọi header đều xuất hiện trong XSD của request Body.
- **Validation:** validate Body theo XSD không tự chứng minh SOAP Header hợp lệ hay chữ ký/MTOM attachment được xử lý đúng.

Ví dụ một header:

~~~xml
<soapenv:Header
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:meta="urn:example:metadata:v1">
  <meta:correlationId>REQ-001</meta:correlationId>
</soapenv:Header>
~~~

Header này có QName `{urn:example:metadata:v1}correlationId`, khác với `invoiceId` thuộc namespace invoice. Nếu cần trích nó, hãy khai báo namespace map `meta → urn:example:metadata:v1` cho XPath context tương ứng **hoặc** dùng API header có sẵn; đừng tìm bằng `./i:invoiceId` trên payload.

## 10. Chọn Node, DOMSource, StreamSource và cách đọc XML

Spring-XML hỗ trợ hai phong cách:

- `XPathExpression` làm việc với `org.w3c.dom.Node`, chẳng hạn `Document` hoặc `Element`.
- `XPathOperations` làm việc với `javax.xml.transform.Source`, chẳng hạn `DOMSource`, `SAXSource` hoặc `StreamSource` tùy cách truyền và runtime.

### 10.1. Node và DOMSource

Khi endpoint có `Element request`:

~~~java
Element request = ...;           // Payload root do Spring-WS cung cấp.
Node contextNode = request;      // Dùng với XPathExpression.
Source source = new DOMSource(request); // Dùng với XPathOperations.
~~~

Đường đi này tận dụng DOM đã tồn tại. Nếu Java method nhận `Source` thay vì `Element`, nên chọn `XPathOperations` hoặc một cách xử lý tương thích với `Source` đó; đừng giả định có thể cast mọi `Source` sang `DOMSource`.

### 10.2. StreamSource có thể tiêu thụ dữ liệu một lần

Một `StreamSource` tạo từ `InputStream` có thể bị tiêu thụ sau khi XPath template chuyển nó thành cây XML để truy vấn. Không nên gọi nhiều biểu thức khác nhau trên **cùng stream** nếu không có cách tạo lại source. Khi cần truy cập nhiều trường, có thể:

1. Chuyển **một lần** sang DOM bằng parser được cấu hình an toàn.
2. Dùng `XPathExpression` trên DOM node ở nhiều câu truy vấn.
3. Hoặc dùng `XPathOperations` với các `DOMSource` mới trỏ tới cùng DOM element.
4. Đặt giới hạn dung lượng để tránh giữ tài liệu XML quá lớn trong heap.

Trước khi tối ưu, cần đo mức độ tải thực: DOM phù hợp các payload nhỏ hoặc vừa cần truy vấn ngẫu nhiên; với XML/MTOM rất lớn, streaming XML (SAX/StAX) và xử lý cấu trúc từng phần có thể thích hợp hơn. XPath về cơ bản làm việc với mô hình cây, do đó phải tính đến chi phí xây/giữ cây của implementation.

### 10.3. Nếu tự parse XML, bật namespace awareness và hardening

Khi Spring-WS đã parse request thành payload `Element`, không cần biến nó về chuỗi XML rồi parse lần thứ hai. Nhưng nếu ứng dụng nhận thêm XML ngoài SOAP hoặc viết unit test dùng DOM parser, cần đảm bảo:

~~~java
import java.io.InputStream;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Document;

DocumentBuilderFactory factory =
        DocumentBuilderFactory.newInstance();

factory.setNamespaceAware(true);
factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);

// Feature dưới đây thường được hỗ trợ bởi Xerces;
// nếu provider không hỗ trợ, cần fail closed và cấu hình khác.
factory.setFeature(
    "http://apache.org/xml/features/disallow-doctype-decl",
    true);

factory.setXIncludeAware(false);
factory.setExpandEntityReferences(false);

// Có thể thêm ACCESS_EXTERNAL_DTD/SCHEMA theo provider và
// cấu hình resource limits ở tầng parser/HTTP.
try (InputStream stream = trustedInputStream()) {
    Document document =
            factory.newDocumentBuilder().parse(stream);
}
~~~

`trustedInputStream()` là một phương thức giả định mà ứng dụng phải định nghĩa. Ví dụ tập trung vào cấu hình parser, không phải một chương trình chạy độc lập. **Không** nuốt lỗi khi provider không hỗ trợ tính năng bảo mật: phải thay cấu hình hoặc parser phù hợp trước khi xử lý XML chưa tin cậy. Trên stack thực, cần còn chặn external general/parameter entities, external DTD/schema access theo provider, giới hạn độ sâu, kích thước và tài nguyên.

Hai bẫy đáng nhớ:

- Nếu quên `setNamespaceAware(true)` khi tự parse DOM, các XPath dùng prefix/namespace có thể không chọn đúng node.
- Nếu dùng `DocumentBuilderFactory.newInstance().newDocumentBuilder().newDocument()` chỉ để tạo response DOM mới, nó không parse XML input nên rủi ro XXE ở chính lời gọi tạo document khác với parser đọc dữ liệu mạng.

## 11. XPath động và nguy cơ XPath injection

Xây biểu thức bằng cách **nối chuỗi từ input người dùng** dễ tạo lỗ hổng tương tự injection trong các ngôn ngữ query khác.

Ví dụ **không nên dùng**:

~~~java
String statusFromClient = ...; // Untrusted input.
String expression =
        "./i:lines/i:line[@status='" + statusFromClient + "']";
~~~

Nếu input chứa dấu nháy, dấu `]` hoặc cú pháp XPath, query có thể bị đổi nghĩa, chọn nhiều node hơn dự kiến hoặc lỗi cú pháp. Đây là vấn đề **XPath injection**, không được giải quyết chỉ bằng việc truy vấn trên DOM thay vì database.

### 11.1. Chọn nodes cố định, so giá trị trong Java

Trong trường hợp cần filter một attribute đơn giản, giữ XPath cố định:

~~~java
XPathExpression lineExpr =
        XPathExpressionFactory.createXPathExpression(
                "./i:lines/i:line",
                Map.of("i", NS));

List<Node> matching = new java.util.ArrayList<>();
for (Node node : lineExpr.evaluateAsNodeList(payload)) {
    if (!(node instanceof org.w3c.dom.Element line)) {
        continue;
    }

    // DOM API trả attribute không namespace.
    String actual = line.getAttribute("status");
    if ("ACTIVE".equals(actual)) {
        matching.add(line);
    }
}
~~~

Từ `List<Node> matching`, bạn tiếp tục xử lý SKU/quantity theo XSD. Trong Java 17+, `instanceof ... line` là cú pháp pattern matching được hỗ trợ. Với JDK cũ, cast truyền thống có thể được dùng.

Nếu thực sự cần biểu thức XPath động, thiết kế **whitelist** các truy vấn đã được review hoặc API biến XPath được cung cấp và hỗ trợ rõ bởi implementation; tránh tự tạo một hệ thống escaping XPath string phức tạp từ dữ liệu chưa tin cậy. Đồng thời kiểm tra quyền truy cập ở tầng nghiệp vụ, không cho client điều khiển XPath áp dụng trên tài liệu nhạy cảm.

### 11.2. Không nhầm logic XPath với authentication

Các biểu thức như:

~~~xpath
boolean(./i:customer/i:id)
~~~

chỉ kiểm tra một node tồn tại. Nó **không chứng minh** người gọi có quyền xem hóa đơn của `customerId` đó. Cần xác thực thông qua transport/WS-Security theo policy, sau đó kiểm tra authorization trong service nghiệp vụ. Không sử dụng namespace URI, tên thẻ, SOAPAction hoặc header do caller tự cung cấp làm chứng cứ xác thực.

## 12. Số, ngày giờ và dữ liệu phức tạp: giới hạn của XPath 1.0

XPath 1.0 có scalar string, boolean, number và node-set. Nó không mang đầy đủ semantics của các loại dữ liệu XSD như `xs:decimal`, `xs:dateTime` hay `xs:base64Binary`.

### 12.1. Không dùng double cho tiền

Trong XSD, field `unitPrice` có type `xs:decimal`. Nếu XPath trả `double` từ `evaluateAsNumber` hoặc `evaluateAsDouble`, bạn có nguy cơ mất precision khi thực hiện phép tính tài chính.

Cách tốt hơn: lấy chuỗi text của node, rồi chuyển sang `BigDecimal` theo contract:

~~~java
XPathExpression priceExpr =
        XPathExpressionFactory.createXPathExpression(
                "./i:unitPrice", Map.of("i", NS));

String text = priceExpr.evaluateAsString(lineElement);
java.math.BigDecimal price = new java.math.BigDecimal(text);
~~~

`lineElement` là context `<i:line>`; giá trị `125000.50` được giữ chính xác theo chữ số decimal. Trước khi dùng, cần xác nhận node tồn tại, không trùng, đúng lexical form và schema constraints (precision, scale, min/max). `new BigDecimal(text)` từ chối một số chuỗi không phù hợp nhưng **không thay thế validator `xs:decimal`**, vì Java và XSD không có tập lexical/ràng buộc đồng nhất trong mọi trường hợp.

### 12.2. Date/time cũng cần quy tắc rõ

`xs:dateTime` có thể có hoặc không có timezone trong XSD 1.0. XPath `string(...)` trả text, nhưng không tự biến nó thành một instant có timezone xác định. Khi cần `Instant` hoặc `OffsetDateTime`, định nghĩa policy rõ về offset/UTC và dùng Java time/XMLGregorianCalendar hoặc JAXB adapter phù hợp.

Không tự thêm `Z` hoặc lấy `ZoneId.systemDefault()` để xử lý timestamp thiếu thông tin nếu contract không có quy định.

### 12.3. Binary không thích hợp với XPath để xử lý nội dung lớn

Với `xs:base64Binary` và MTOM/XOP, XPath có thể dùng để xác định presence hoặc metadata, nhưng không nên đọc toàn bộ tài liệu binary hàng chục MiB qua `string(...)` rồi giữ trong heap. Dùng API attachment/MTOM và giới hạn dung lượng, kiểm tra nội dung, cleanup streams theo runtime tương thích.

### 12.4. XSD validation là nhiệm vụ riêng

Ví dụ XPath có thể thấy `./i:customer/i:id` trả text đúng, nhưng request vẫn có thể vi phạm XSD vì:

- Thiếu `invoiceId` bắt buộc.
- Sai thứ tự `xs:sequence`.
- Có `quantity=0` dù XSD là `xs:positiveInteger`.
- Có quá ít hoặc quá nhiều phần tử `line`.
- Trường `unitPrice` không đúng lexical decimal hoặc facet.

Do đó, XPath giúp **trích xuất**, còn `PayloadValidatingInterceptor` hoặc cơ chế validation tương đương giúp kiểm tra **hợp đồng XML**; business validation kiểm tra **ý nghĩa và quyền**.

## 13. Hiệu năng và vòng đời của XPath evaluator

Một biểu thức XPath đúng về logic vẫn có thể trở thành điểm nghẽn nếu mỗi SOAP request lớn cần parse hoặc đi qua toàn bộ DOM nhiều lần.

### 13.1. Khi nào biên dịch trước đáng giá?

- Biểu thức **cố định** và chạy lặp lại nhiều lần: `XPathExpressionFactory` phù hợp để tránh phân tích cú pháp XPath lặp lại.
- Biểu thức **khác nhau** theo thao tác, nhưng đều thuộc danh sách đã review: `XPathOperations` linh hoạt hơn; cần đo overhead trong ứng dụng thực.
- Payload có nhiều field: JAXB hoặc code xử lý DOM theo cấu trúc có thể dễ bảo trì hơn rất nhiều XPath rời rạc.
- XML rất lớn: cân nhắc streaming qua SAX/StAX và quản lý memory; đừng chọn XPath chỉ để tránh viết một chút code.

### 13.2. Cảnh báo về thread safety

Spring SOAP server xử lý nhiều HTTP request đồng thời. Không phải mọi implementation XPath/evaluator bên dưới đều được bảo đảm thread-safe. Đặc biệt, `javax.xml.xpath.XPathExpression` của JAXP không nên mặc định dùng chung một instance qua nhiều threads mà không kiểm tra contract của implementation.

Phương án thiết kế:

1. Cấu hình **namespace map bất biến** và không thay trạng thái template lúc đã phục vụ request.
2. Nếu dùng compiled expression chung, kiểm tra tài liệu và thử concurrent stress test với implementation thực, hoặc tạo evaluator riêng theo request/thread.
3. Nếu chọn `XPathOperations` singleton, kiểm tra việc template và transformer factory được cấu hình trước khi chạy, không mutate trong request handler.
4. Tránh lưu `Document` hoặc `Node` của request thành field singleton, vì có thể trộn dữ liệu giữa các phiên xử lý.
5. Đặt timeout/giới hạn tài nguyên ở SOAP/HTTP layer thay vì hy vọng một XPath được tối ưu sẽ ngăn tấn công denial-of-service.

**Không đưa ra kết luận hiệu năng chỉ bằng tên class.** Hãy đo trên XSD, kích thước payload và JVM/library thực tế; so compiled XPath, template động, JAXB và streaming theo workload. Trên các payload nhỏ, độ đơn giản và tính đúng của code thường quan trọng hơn một tối ưu chưa có số liệu.

### 13.3. Truy vấn rộng làm tăng độ phức tạp

Biểu thức:

~~~xpath
.//i:sku
~~~

có thể quét rất nhiều node và vô tình chọn field ở cấu trúc con được thêm trong phiên bản mới. Đường dẫn cụ thể:

~~~xpath
./i:lines/i:line/i:sku
~~~

đơn giản hơn để review và có semantics rõ ràng theo XSD. Khi schema thay đổi, nên sửa XPath có chủ đích thay vì cố thiết kế một biểu thức quá rộng để “chịu mọi XML”.

## 14. SOAP Fault, interceptor và XML security trong xử lý XPath

### 14.1. Phân biệt các dạng lỗi

| Vấn đề | Tầng có thể phát hiện | Cách xử lý |
|---|---|---|
| SOAP Envelope không well-formed | XML parser/message factory | Từ chối request theo SOAP/HTTP profile, không chạy XPath |
| Payload root QName sai | `@PayloadRoot` mapping | Trả lỗi dispatch được kiểm soát |
| XPath sai cú pháp | Compile `XPathExpression` hoặc lúc đánh giá template | Sửa cấu hình XPath; không biến lỗi kỹ thuật thành dữ liệu nghiệp vụ |
| Prefix XPath chưa gắn namespace | Namespace resolver/XPath evaluator | Đăng ký map đúng và kiểm tra expression |
| XPath không tìm thấy node | XPath evaluation | Phân biệt optional field với thiếu field bắt buộc |
| XPath tìm nhiều nodes | XPath evaluation | Xử lý danh sách có chủ đích hoặc từ chối khi contract yêu cầu đúng một |
| XML không thỏa XSD | Schema validator | SOAP Fault/validation error theo contract |
| Dữ liệu hợp lệ nhưng thiếu quyền | Business authorization | Từ chối dù XPath đọc được field |
| WS-Security signature sai | Security interceptor/policy | Từ chối trước khi thao tác nghiệp vụ |
| Response XML không đúng QName/schema | Response generation/validation | Sửa server mapping/serialization |

Spring-WS có `EndpointExceptionResolver` và các SOAP fault resolver để ánh xạ lỗi của endpoint thành SOAP Fault. Tuy nhiên, **lỗi phát sinh ở parser, transport, security hoặc mapping** có thể đi qua các đường xử lý khác; không coi một resolver endpoint là nơi xử lý mọi exception trong toàn stack.

Đối với một contract SOAP doanh nghiệp, hãy thiết kế fault code/reason/detail phù hợp và không tiết lộ stack trace, đường dẫn file, khóa ký hoặc nội dung bí mật. Thông tin chẩn đoán chi tiết chỉ nên ở hệ thống log bảo vệ truy cập, có redaction.

### 14.2. XSD validation không tự động chạy vì có XPath

Một endpoint được annotate:

~~~java
@PayloadRoot(
    namespace = "urn:example:invoices:v1",
    localPart = "GetInvoiceRequest")
~~~

có thể tìm thấy đúng handler chỉ vì root QName hợp lệ. Nếu bên trong `quantity` chứa `0`, XSD mẫu quy định `xs:positiveInteger` sẽ từ chối dữ liệu đó **khi validation được bật**. Nhưng không thể mặc định có validation chỉ vì một `XsdSchema` hoặc WSDL bean đã được công bố.

Spring-WS có `PayloadValidatingInterceptor`; nên cấu hình request/response validation với các schema đúng namespace và có test fault path. Nếu nhiều service dùng chung servlet, đừng vô tình gắn validator chỉ biết một namespace vào mọi endpoint rồi từ chối hợp đồng khác.

### 14.3. Bảo vệ đầu vào trước khi đánh giá XPath

- Hạn chế HTTP body, XML depth, attribute count, số nodes và thời gian xử lý; xem việc dùng `.//` trên XML lớn như một chi phí cần đo.
- Chặn external entities và DTD theo profile parser; không tự cho phép XPath/transformer tải URL hoặc tài nguyên ngoài.
- Không chấp nhận XPath string từ đối tác như một “ngôn ngữ truy vấn mở” trên tài liệu nhạy cảm trừ khi có sandbox/allowlist và authorization rõ ràng.
- Tránh logging toàn bộ SOAP Body hoặc SOAP Header chứa token, chữ ký, thông tin khách hàng và binary.
- Với MTOM/XOP, dùng cơ chế đọc attachment an toàn; XPath không thay thế kiểm soát MIME parts và byte đã giải mã.

### 14.4. WS-Security và chứng chỉ nằm ngoài QName/XPath

WS-Security xử lý chữ ký, mã hóa, token và timestamp theo chính sách; TLS/HTTPS bảo vệ kênh truyền. Hai lớp này có thể đòi keystore, truststore, chứng chỉ, hostname verification, rotation, replay protection và WS-SecurityPolicy mà đối tác đã thống nhất.

**XPath chọn đúng dữ liệu không chứng minh dữ liệu đó đáng tin hay đã được xác thực.** Một attacker vẫn có thể tạo SOAP Body có `invoiceId` đúng định dạng. Hệ thống chỉ nên truy cập hóa đơn sau khi hoàn thành security validation và business authorization.

## 15. Kiểm thử XPath có namespace và kiểm thử SOAP thực tế

### 15.1. Unit test XPath trên DOM

Ví dụ JUnit 5 dùng XML fixture tĩnh, không đọc dữ liệu từ mạng. Nó xác minh rằng một XPath với prefix `i` vẫn tìm được data khi client dùng prefix `x`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.io.StringReader;
import java.util.Map;

import javax.xml.parsers.DocumentBuilderFactory;

import org.junit.jupiter.api.Test;
import org.springframework.xml.xpath.XPathExpression;
import org.springframework.xml.xpath.XPathExpressionFactory;
import org.w3c.dom.Document;
import org.xml.sax.InputSource;

class InvoiceXPathTest {

    @Test
    void matchesNamespaceUriNotLiteralPrefix() throws Exception {
        String xml = """
            <x:GetInvoiceRequest xmlns:x="urn:example:invoices:v1">
              <x:invoiceId>INV-1001</x:invoiceId>
            </x:GetInvoiceRequest>
            """;

        DocumentBuilderFactory f =
                DocumentBuilderFactory.newInstance();
        f.setNamespaceAware(true);

        // XML fixture do test sở hữu; không mở rộng đoạn parser này
        // để parse dữ liệu mạng nếu chưa cấu hình chống XXE/DTD.
        Document doc = f.newDocumentBuilder()
                .parse(new InputSource(new StringReader(xml)));

        XPathExpression expr =
                XPathExpressionFactory.createXPathExpression(
                    "./i:invoiceId",
                    Map.of("i", "urn:example:invoices:v1"));

        assertEquals("INV-1001",
                expr.evaluateAsString(doc.getDocumentElement()));
    }
}
~~~

Vì test fixture cố ý chỉ giữ `invoiceId` để cô lập XPath, XML này **chưa đầy đủ theo XSD ở mục 2**. Unit test truy vấn XPath không thay thế test XSD validation trên request hoàn chỉnh.

### 15.2. Test XPathOperations bằng StringSource

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.xml.transform.StringSource;
import org.springframework.xml.xpath.Jaxp13XPathTemplate;
import org.springframework.xml.xpath.XPathOperations;

class InvoiceXPathOperationsTest {

    @Test
    void readsValueThroughSource() {
        String xml = """
            <GetInvoiceRequest xmlns="urn:example:invoices:v1">
              <invoiceId>INV-1001</invoiceId>
            </GetInvoiceRequest>
            """;

        Jaxp13XPathTemplate template = new Jaxp13XPathTemplate();
        template.setNamespaces(
                Map.of("i", "urn:example:invoices:v1"));

        XPathOperations operations = template;
        String invoiceId = operations.evaluateAsString(
                "./i:invoiceId", new StringSource(xml));

        assertEquals("INV-1001", invoiceId);
    }
}
~~~

Đây là test riêng cho semantics context `Source` và default namespace. Cần dependency `spring-xml`/Spring-WS đúng version, JUnit 5 và project test configuration phù hợp.

### 15.3. Test endpoint với MockWebServiceClient

Khi `InvoiceEndpoint` và các bean Spring-WS đã được đăng ký, `MockWebServiceClient` có thể gửi SOAP **payload** vào application context:

~~~java
@SpringBootTest
class InvoiceEndpointTest {

    @Autowired
    ApplicationContext applicationContext;

    @Test
    void extractsInvoiceIdAndResponds() {
        MockWebServiceClient client =
                MockWebServiceClient.createClient(applicationContext);

        Source request = new StringSource("""
            <x:GetInvoiceRequest xmlns:x="urn:example:invoices:v1">
              <x:invoiceId>INV-1001</x:invoiceId>
              <x:customer>
                <x:id>CUS-009</x:id>
              </x:customer>
              <x:lines>
                <x:line status="ACTIVE">
                  <x:sku>BOOK-01</x:sku>
                  <x:quantity>2</x:quantity>
                  <x:unitPrice>125000.50</x:unitPrice>
                </x:line>
              </x:lines>
            </x:GetInvoiceRequest>
            """);

        Source expected = new StringSource("""
            <i:GetInvoiceResponse xmlns:i="urn:example:invoices:v1">
              <i:invoiceId>INV-1001</i:invoiceId>
              <i:accepted>true</i:accepted>
            </i:GetInvoiceResponse>
            """);

        client.sendRequest(withPayload(request))
              .andExpect(payload(expected));
    }
}
~~~

Đoạn code minh họa này cần import JUnit, Spring Test, `org.springframework.ws.test.server.MockWebServiceClient`, `org.springframework.xml.transform.StringSource`, cùng static import `withPayload` từ `RequestCreators` và `payload` từ `ResponseMatchers`. Phải có `spring-ws-test` trong test dependencies. Nó giúp kiểm tra dispatch và response trong application context nhưng **không** xác minh HTTP servlet, Content-Type, reverse proxy, TLS hoặc interoperability với client độc lập.

### 15.4. Ma trận kiểm thử âm tính/biên

| Input | Kết quả XPath mong đợi | Kết quả hợp đồng mong đợi |
|---|---|---|
| Prefix `inv` thay bằng `x`, URI không đổi | Vẫn chọn được `invoiceId` | Request vẫn có thể hợp lệ |
| Dùng default namespace đúng | Vẫn chọn được với `i:invoiceId` | Request vẫn có thể hợp lệ |
| Root URI đổi từ `v1` sang `v2` | `@PayloadRoot` v1 không match | Không được dispatch tới endpoint v1 |
| Child `invoiceId` không namespace | `./i:invoiceId` không chọn được | Không hợp lệ với XSD mẫu |
| Có hai `invoiceId` | Node list size = 2 | Không hợp lệ với XSD sequence |
| Thiếu `invoiceId` | Node list rỗng | Không hợp lệ với XSD |
| `quantity=0` | XPath vẫn có thể đọc text `0` | Không hợp lệ vì `xs:positiveInteger` |
| `unitPrice=125000.50` | XPath đọc được string chính xác | Hợp lệ với `xs:decimal` |
| Input XPath chứa nháy/cú pháp do user gửi | Không được nối vào query | Không có XPath injection |
| SOAP Header thay đổi nhưng Body đúng | Payload XPath vẫn chọn đúng data | Bảo mật/header policy phải được xét riêng |
| SOAPAction không khớp binding | Payload QName có thể vẫn đúng | Cần test mapping/contract theo stack thực |

Khi chạy integration test thực, quan sát SOAP response/fault hoàn chỉnh, kiểm tra rằng lỗi không gây side effect nghiệp vụ và dùng một client JAX-WS/CXF hoặc .NET được sinh từ WSDL để phát hiện khác biệt interoperable.

## 16. Bài tập tự luyện có đáp án

### Bài 1 — Default namespace và XPath không prefix

Input:

~~~xml
<GetInvoiceRequest xmlns="urn:example:invoices:v1">
  <invoiceId>INV-2002</invoiceId>
</GetInvoiceRequest>
~~~

Hai expression:

~~~xpath
./invoiceId
./i:invoiceId
~~~

**Câu hỏi:** Expression nào tìm được node khi map có `i → urn:example:invoices:v1`?

**Đáp án:** `./i:invoiceId`. XPath không prefix chọn element không namespace, còn child `invoiceId` trong mẫu thuộc default namespace.

### Bài 2 — Cùng namespace nhưng prefix khác

Expression được biên dịch với `Map.of("i", "urn:example:invoices:v1")`. Client gửi `<p:invoiceId xmlns:p="urn:example:invoices:v1">INV-2002</p:invoiceId>`.

**Đáp án:** XPath `i:invoiceId` vẫn chọn đúng vì so namespace URI + local name. Không phải sửa expression theo prefix `p` của client.

### Bài 3 — Context Node không phải SOAP Envelope

Endpoint nhận `@RequestPayload Element request` và gọi:

~~~xpath
/s:Envelope/s:Body/i:GetInvoiceRequest/i:invoiceId
~~~

Nó không chọn được gì dù request gửi đúng.

**Đáp án:** Context đã là payload root; nên dùng `./i:invoiceId`. Muốn đọc cả Envelope/Header phải lấy SOAP message qua API phù hợp chứ không dùng payload Node rồi suy đoán nó chứa cả Envelope.

### Bài 4 — Đúng một node hay lấy chuỗi đầu tiên?

XPath `./i:invoiceId` có thể chọn hai element nếu XML bị lỗi schema. Method `evaluateAsString` trả một chuỗi. Có thể kết luận request hợp lệ không?

**Đáp án:** Không. Dùng `evaluateAsNodeList` rồi kiểm tra có đúng một node và bật XSD validation. `evaluateAsString` có thể lấy string-value của node đầu tiên trong tập.

### Bài 5 — Khác biệt method tên Number/Double

Một developer gọi `xpathOperations.evaluateAsNumber("./i:quantity", source)` và gặp lỗi compile. Phương thức đúng là gì?

**Đáp án:** `XPathOperations` dùng `evaluateAsDouble(String, Source)`; `XPathExpression` dùng `evaluateAsNumber(Node)`. Cả hai trả `double`, không nên dùng để biểu diễn số tiền chính xác.

### Bài 6 — XPath injection

Code nối `statusFromClient` vào XPath:

~~~java
String xpath = "./i:lines/i:line[@status='" + statusFromClient + "']";
~~~

**Câu hỏi:** Rủi ro và phương án thay thế?

**Đáp án:** Input có thể phá cú pháp hoặc thay điều kiện XPath. Chọn toàn bộ line bằng một expression **cố định**, rồi so attribute trong Java; nếu cần truy vấn động, dùng whitelist/truyền biến qua API được hỗ trợ một cách có kiểm soát.

### Bài 7 — Chọn JAXB hay XPath

Một request có 60 field, nhiều nested complex types, enumeration, optional/nillable và adapter dữ liệu ngày giờ. Có nên dùng 60 expression XPath?

**Gợi ý:** Thường không. Với contract-first XSD ổn định, JAXB model sinh từ schema kết hợp XSD validation thường dễ bảo trì và kiểm thử hơn. XPath thích hợp khi chỉ cần vài field hoặc XML có cấu trúc riêng đặc thù.

### Bài 8 — Test bảo mật thực tế

Endpoint đọc được `invoiceId` nhờ XPath và SOAP client nhận response thành công. Có đủ để chứng minh WS-Security và quyền truy cập đúng?

**Đáp án:** Không. Phải test token/chữ ký/timestamp/chứng chỉ và business authorization, kể cả request từ caller không được phép. XPath chỉ xác định dữ liệu trong XML, không xác định độ tin cậy của caller.

## 17. Checklist áp dụng trong dự án SOAP contract-first

### Thiết kế XPath

- [ ] Bắt đầu từ **global element** trong XSD/WSDL và xác định đúng node context của XPath.
- [ ] Dùng prefix XPath được ánh xạ tới **namespace URI**, không phụ thuộc prefix xuất hiện trong SOAP XML.
- [ ] Phân biệt element có namespace với attribute không namespace.
- [ ] Ưu tiên đường dẫn cụ thể `./i:...`, tránh `//` rộng không có lý do rõ.
- [ ] Không tự động dùng `local-name()` mà bỏ kiểm tra namespace URI.
- [ ] Có quy tắc khi node rỗng, không tồn tại, bị lặp hoặc có dữ liệu không hợp lệ.
- [ ] Giữ XPath cố định hoặc whitelist; không nối chuỗi từ input chưa tin cậy.

### API và hiệu năng

- [ ] `XPathExpression` đánh giá trên `Node`; `XPathOperations` đánh giá `String XPath + Source`.
- [ ] Dùng đúng `evaluateAsNumber(Node)` so với `evaluateAsDouble(String, Source)`.
- [ ] Dùng `NodeMapper.mapNode(Node, int)` hoặc callback khi cần xử lý nhiều nodes.
- [ ] Namespace map được cấu hình ổn định, không mutate khi xử lý đồng thời.
- [ ] Xác minh thread-safety của implementation trước khi chia sẻ compiled evaluator.
- [ ] Không dùng `double` để tính số tiền hoặc biểu diễn decimal đòi hỏi chính xác.
- [ ] Tránh parse/serialize XML nhiều lần và giới hạn tài nguyên với payload lớn.

### Spring-WS, contract và bảo mật

- [ ] `@PayloadRoot` khớp QName của **request** root, độc lập tên Java method.
- [ ] Spring context có `@Endpoint`, endpoint mapping, adapter và servlet đúng.
- [ ] SOAP Body response được marshal đúng global element và XSD.
- [ ] Có XSD validation riêng, không giả định XPath/JAXB tự kiểm tra mọi facet.
- [ ] SOAP Fault xử lý lỗi parser, mapping, XPath, validation và nghiệp vụ có kiểm soát.
- [ ] Parser, Transformer và XML infrastructure được cấu hình chống XXE/DTD/tải resource ngoài.
- [ ] Đã giới hạn kích thước/độ sâu XML và attachments; không log dữ liệu nhạy cảm.
- [ ] WS-Security, TLS, keystore/truststore, chứng chỉ và quyền nghiệp vụ được kiểm thử riêng.
- [ ] Có unit tests cho namespace/default namespace và integration tests qua SOAP client độc lập.
- [ ] Đánh giá tương thích khi đổi `targetNamespace`, element name, XSD structure hoặc SOAP binding.

## 18. Tóm lược quyết định và nguồn tham khảo

| Nếu bạn đang cần… | Công cụ nên cân nhắc |
|---|---|
| Trích một vài node của XML có namespace | `XPathExpression` hoặc `XPathOperations` |
| Truy vấn XPath cố định nhiều lần | `XPathExpressionFactory` + chính sách reuse/concurrency đúng |
| Chạy nhiều XPath khác nhau trên `Source` | `Jaxp13XPathTemplate` triển khai `XPathOperations` |
| Ánh xạ nhiều node thành đối tượng | `NodeMapper<T>` với `(Node, int)` |
| Marshal/unmarshal DTO lớn theo XSD | JAXB/OXM với schema validation |
| Xử lý XML/attachment rất lớn | SAX/StAX/streaming và giới hạn tài nguyên |
| Kiểm chứng request hợp đồng | XSD validator, SOAP Fault và compatibility tests |
| Xác thực/ủy quyền request | TLS/WS-Security và business authorization |

Tài liệu API để đối chiếu với **đúng version Spring-WS đang sử dụng**:

- [Spring-WS: XPathExpression](https://www.springframework.org/spring-ws/docs/4.1.2/api/org/springframework/xml/xpath/XPathExpression.html) — kiểu tham số `Node`, kết quả `String`/`Node`/`List<Node>`/`double`.
- [Spring-WS: XPathOperations](https://www.springframework.org/spring-ws/docs/4.1.1/api/org/springframework/xml/xpath/XPathOperations.html) — `String expression`, `Source` và các phương thức đánh giá.
- [Spring-WS: XPathExpressionFactory](https://www.springframework.org/spring-ws/docs/4.1.1/api/org/springframework/xml/xpath/XPathExpressionFactory.html) — tạo expression có namespace map.
- [Spring-WS: Jaxp13XPathTemplate](https://docs.spring.io/spring-ws/docs/5.0.0-M1/api/org/springframework/xml/xpath/Jaxp13XPathTemplate.html) — implementation XPathOperations với JAXP, cấu hình namespaces. Trang này là API bản milestone; với dự án production cần tra JavaDoc của phiên bản dependency chính thức đang cài.

**Ghi nhớ:** XPath trong Spring Web Services hiệu quả nhất khi bạn xác định chính xác **node context** và **namespace URI** của từng element. `XPathExpression` dùng biểu thức đã biên dịch trên `Node`; `XPathOperations` dùng chuỗi XPath linh hoạt trên `Source`. Cả hai chỉ đảm nhiệm việc chọn dữ liệu XML: một SOAP service đáng tin cậy vẫn cần XSD/WSDL rõ ràng, validation, SOAP Fault, XML security, WS-Security và kiểm thử tương thích giữa các client.
