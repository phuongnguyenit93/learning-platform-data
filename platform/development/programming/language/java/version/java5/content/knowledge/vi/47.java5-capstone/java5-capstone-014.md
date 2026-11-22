# Kiểm tra XML an toàn bằng XPath và Schema

## 1. Ba câu hỏi khác nhau trong một luồng xử lý

Một tài liệu XML cần được đánh giá ở nhiều tầng:

| Tầng | Câu hỏi |
| --- | --- |
| Phân tích XML | Có đọc được tài liệu mà không mở tài nguyên ngoài hoặc tiêu tốn tài nguyên vượt chính sách không? |
| Schema | Tài liệu có đúng cấu trúc, namespace, kiểu dữ liệu và ràng buộc đã chọn không? |
| XPath | Có trích xuất đúng nút, đúng phạm vi và không biến đầu vào thành cú pháp truy vấn không? |

XML hợp lệ theo XSD không tự chứng minh parser đã an toàn. XPath tìm thấy một giá trị cũng không chứng minh toàn bộ tài liệu hợp lệ. Cần ghép các bước theo đúng thứ tự và dùng cùng dữ liệu đã kiểm tra.

Bài thực hành dùng DOM, XSD tin cậy và XPath của JDK hiện đại; chương trình chạy độc lập trên Java 17+. Không cần thư viện ngoài hoặc tài nguyên mạng.

## 2. Nguy cơ xuất hiện trước khi Schema kiểm tra xong

XML có thể chứa khai báo hoặc tham chiếu tài nguyên ngoài. Nếu parser tự xử lý các tham chiếu ấy, một tài liệu không đáng tin có thể khiến ứng dụng đọc file hoặc liên hệ địa chỉ mạng không mong muốn. Việc mở rộng thực thể còn có thể tạo chi phí CPU/bộ nhớ rất lớn. [JAXP Security Guide](https://docs.oracle.com/en/java/javase/25/security/java-api-xml-processing-jaxp-security-guide.html).

Với hồ sơ bài học không cần DTD hoặc tài nguyên ngoài, chính sách là:

- Từ chối mọi `DOCTYPE` của tài liệu đầu vào.
- Không cho xử lý external entity hoặc tải external DTD.
- Tắt XInclude vì ứng dụng không cần nhập nội dung ngoài.
- Chặn truy cập DTD/schema ngoài ở các processor liên quan.
- Giới hạn kích thước đầu vào và độ sâu phần tử phù hợp.

`setExpandEntityReferences(false)` không phải biện pháp độc lập đủ để giải quyết mọi truy cập ngoài. Cũng không chỉ dựa vào một cấu hình mặc định có thể khác theo JDK/provider. Bài đặt chính sách tường minh trước khi tạo processor.

## 3. Luồng xử lý của bài thực hành

```text
Byte XML trong giới hạn
  -> parser DOM có chính sách bảo mật và hỗ trợ namespace
  -> DOM của tài liệu
  -> Validator với XSD do ứng dụng kiểm soát
  -> cùng DOM đã kiểm tra
  -> XPath cố định + biến dữ liệu
  -> kết quả đã chọn, rồi kiểm tra nghiệp vụ cần thiết
```

Không kiểm tra một bản tài liệu rồi đọc lại file/URL bằng một parser khác để truy vấn. Nguồn có thể thay đổi, hoặc parser thứ hai có cấu hình khác. Cũng không truyền trực tiếp một `InputSource` không được kiểm soát vào XPath rồi giả định cấu hình bảo mật của parser trước đó vẫn có tác dụng.

DOM giữ cây tài liệu trong bộ nhớ; phù hợp ví dụ có giới hạn đầu vào nhỏ. Với tài liệu lớn hơn, cần đánh giá thiết kế xử lý dòng và các giới hạn tài nguyên theo nhu cầu, không chỉ tăng giới hạn vô điều kiện.

## 4. Schema phải là hợp đồng tin cậy của ứng dụng

Ví dụ dùng một XSD được nhúng trong chương trình. Nó mô tả:

| Thành phần | Ràng buộc minh họa |
| --- | --- |
| Namespace | `urn:demo:order` |
| Phần tử gốc | `order` |
| Thuộc tính `id` | Bắt buộc, kiểu số nguyên dương |
| Phần tử `total` | Xuất hiện một lần, kiểu thập phân |
| Miền `total` | Từ 0 đến 1.000.000, giá trị không cần quá hai chữ số phần thập phân |

Các giới hạn này là hợp đồng minh họa. Chúng chưa xác nhận quyền truy cập đơn hàng, danh tính người gửi hoặc tổng có khớp các dòng nghiệp vụ hay không.

`SchemaFactory` biên dịch nguồn XSD thành `Schema`; `Validator` kiểm tra tài liệu theo schema đó. Đừng để đầu vào tùy ý chọn XSD riêng rồi coi kết quả là đã qua hợp đồng của hệ thống. Cũng cần chặn việc schema tải `include`/`import` ngoài nếu hồ sơ không cho phép. [API SchemaFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/validation/SchemaFactory.html).

## 5. Chương trình Java 17+ chạy đầy đủ

Lưu thành `SafeXmlDemo.java`:

```java
import java.io.ByteArrayInputStream;
import java.io.StringReader;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.Iterator;
import javax.xml.XMLConstants;
import javax.xml.namespace.NamespaceContext;
import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.transform.dom.DOMSource;
import javax.xml.transform.stream.StreamSource;
import javax.xml.validation.Schema;
import javax.xml.validation.SchemaFactory;
import javax.xml.validation.Validator;
import javax.xml.xpath.XPath;
import javax.xml.xpath.XPathConstants;
import javax.xml.xpath.XPathFactory;
import org.w3c.dom.Document;
import org.xml.sax.ErrorHandler;
import org.xml.sax.SAXException;
import org.xml.sax.SAXParseException;
import org.xml.sax.helpers.DefaultHandler;

public class SafeXmlDemo {
    static final int MAX_XML_BYTES = 64 * 1024;
    static final String NS = "urn:demo:order";
    static final String XSD = """
            <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
                       targetNamespace="urn:demo:order"
                       xmlns:o="urn:demo:order" elementFormDefault="qualified">
              <xs:element name="order">
                <xs:complexType>
                  <xs:sequence>
                    <xs:element name="total">
                      <xs:simpleType>
                        <xs:restriction base="xs:decimal">
                          <xs:minInclusive value="0"/>
                          <xs:maxInclusive value="1000000"/>
                          <xs:fractionDigits value="2"/>
                        </xs:restriction>
                      </xs:simpleType>
                    </xs:element>
                  </xs:sequence>
                  <xs:attribute name="id" type="xs:positiveInteger" use="required"/>
                </xs:complexType>
              </xs:element>
            </xs:schema>
            """;
    static final ErrorHandler ERRORS = new DefaultHandler() {
        @Override public void warning(SAXParseException ex) throws SAXException { throw ex; }
        @Override public void error(SAXParseException ex) throws SAXException { throw ex; }
        @Override public void fatalError(SAXParseException ex) throws SAXException { throw ex; }
    };

    static Schema schema() throws Exception {
        SchemaFactory factory = SchemaFactory.newDefaultInstance();
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        factory.setErrorHandler(ERRORS);
        return factory.newSchema(new StreamSource(new StringReader(XSD)));
    }

    static Document parse(byte[] bytes) throws Exception {
        if (bytes.length > MAX_XML_BYTES) {
            throw new IllegalArgumentException("XML input too large");
        }
        DocumentBuilderFactory factory = DocumentBuilderFactory.newDefaultInstance();
        factory.setNamespaceAware(true);
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
        factory.setFeature("http://xml.org/sax/features/external-general-entities", false);
        factory.setFeature("http://xml.org/sax/features/external-parameter-entities", false);
        factory.setFeature("http://apache.org/xml/features/nonvalidating/load-external-dtd", false);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        factory.setAttribute("jdk.xml.maxElementDepth", "32");
        factory.setXIncludeAware(false);
        factory.setExpandEntityReferences(false);
        DocumentBuilder builder = factory.newDocumentBuilder();
        builder.setErrorHandler(ERRORS);
        builder.setEntityResolver((publicId, systemId) -> {
            throw new SAXException("External entity resolution denied");
        });
        try (ByteArrayInputStream input = new ByteArrayInputStream(bytes)) {
            return builder.parse(input);
        }
    }

    static Document validated(String xml, Schema schema) throws Exception {
        Document document = parse(xml.getBytes(StandardCharsets.UTF_8));
        Validator validator = schema.newValidator();
        validator.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        validator.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        validator.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        validator.setErrorHandler(ERRORS);
        validator.validate(new DOMSource(document));
        return document;
    }

    static String totalFor(Document document, String wantedId) throws Exception {
        XPathFactory factory = XPathFactory.newDefaultInstance();
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        XPath xpath = factory.newXPath();
        xpath.setNamespaceContext(new NamespaceContext() {
            @Override public String getNamespaceURI(String prefix) {
                if (prefix == null) throw new IllegalArgumentException("Null prefix");
                return switch (prefix) {
                    case "o" -> NS;
                    case "xml" -> XMLConstants.XML_NS_URI;
                    case "xmlns" -> XMLConstants.XMLNS_ATTRIBUTE_NS_URI;
                    default -> XMLConstants.NULL_NS_URI;
                };
            }
            @Override public String getPrefix(String uri) {
                if (uri == null) throw new IllegalArgumentException("Null namespace URI");
                if (NS.equals(uri)) return "o";
                if (XMLConstants.XML_NS_URI.equals(uri)) return "xml";
                if (XMLConstants.XMLNS_ATTRIBUTE_NS_URI.equals(uri)) return "xmlns";
                return null;
            }
            @Override public Iterator<String> getPrefixes(String uri) {
                String prefix = getPrefix(uri);
                return prefix == null ? Collections.emptyIterator()
                        : Collections.singleton(prefix).iterator();
            }
        });
        xpath.setXPathVariableResolver(name ->
                name.getNamespaceURI().isEmpty() && name.getLocalPart().equals("wantedId")
                        ? wantedId : null);
        return (String) xpath.compile("/o:order[@id=$wantedId]/o:total")
                .evaluate(document, XPathConstants.STRING);
    }

    @FunctionalInterface
    interface CheckedAction { void run() throws Exception; }

    static void expectSaxRejection(String label, CheckedAction action) throws Exception {
        try {
            action.run();
            throw new AssertionError("Expected rejection: " + label);
        } catch (SAXException expected) {
            System.out.println(label + "=rejected");
        }
    }

    public static void main(String[] args) throws Exception {
        Schema schema = schema();
        String valid = "<order xmlns=\"urn:demo:order\" id=\"101\"><total>12.30</total></order>";
        Document document = validated(valid, schema);
        String total = totalFor(document, "101");
        if (!total.equals("12.30")) throw new AssertionError("Unexpected total");
        System.out.println("total=" + total);
        String attackAsData = "101' or '1'='1";
        boolean matched = !totalFor(document, attackAsData).isEmpty();
        if (matched) throw new AssertionError("XPath data changed query meaning");
        System.out.println("injectionMatched=" + matched);
        expectSaxRejection("negativeTotal", () -> validated(valid.replace("12.30", "-1"), schema));
        expectSaxRejection("wrongNamespace", () -> validated(valid.replace(NS, "urn:other"), schema));
        String doctype = "<!DOCTYPE order [<!ENTITY x '12.30'>]>"
                + valid.replace("12.30", "&x;");
        expectSaxRejection("doctype", () -> validated(doctype, schema));
        try {
            parse(new byte[MAX_XML_BYTES + 1]);
            throw new AssertionError("Expected size rejection");
        } catch (IllegalArgumentException expected) {
            System.out.println("oversize=rejected");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 SafeXmlDemo.java
java SafeXmlDemo
```

Stdout:

```text
total=12.30
injectionMatched=false
negativeTotal=rejected
wrongNamespace=rejected
doctype=rejected
oversize=rejected
```

Chương trình đã được kiểm tra với implementation JAXP tích hợp trong JDK 17. Nó không mở file hoặc URL ngoài. Ca DOCTYPE sử dụng một thực thể nội bộ để kiểm tra chính sách từ chối toàn bộ khai báo DOCTYPE, không đọc một file bí mật thật làm dữ liệu thử.

`expectSaxRejection()` chỉ chấp nhận lỗi thuộc lớp SAX mà ca đó kỳ vọng. Lỗi cấu hình processor hoặc lỗi lập trình khác được truyền ra, không biến mọi ngoại lệ thành “đã từ chối an toàn”.

## 6. Những cấu hình nào bảo vệ bước parse?

Hàm `parse()` có các phần độc lập:

| Cấu hình | Vai trò trong hồ sơ bài học |
| --- | --- |
| `setNamespaceAware(true)` | Parser lưu và phân biệt đúng namespace |
| `FEATURE_SECURE_PROCESSING` | Bật cơ chế xử lý có hạn chế bảo mật theo processor |
| `disallow-doctype-decl` | Từ chối DOCTYPE ở parser được kiểm chứng |
| External entity và external DTD features | Tắt các đường xử lý ngoài không cần thiết |
| `ACCESS_EXTERNAL_DTD/SCHEMA = ""` | Không cho truy cập giao thức tài nguyên ngoài ở phạm vi cấu hình |
| `setXIncludeAware(false)` | Không thực hiện nhập nội dung qua XInclude |
| `EntityResolver` từ chối | Bổ sung điểm chặn nếu parser yêu cầu giải quyết thực thể ngoài |
| Giới hạn byte và độ sâu | Hạn chế tài nguyên theo nhu cầu ví dụ |

Các URI feature kiểu Apache/Xerces và thuộc tính `jdk.xml.maxElementDepth` phụ thuộc khả năng processor/implementation. Bài chọn implementation mặc định tích hợp bằng `newDefaultInstance()` và đã kiểm chứng nó. Nếu chuyển provider và một thiết lập bắt buộc không được hỗ trợ, phải thất bại khi khởi tạo thay vì bắt lỗi rồi tiếp tục bằng parser không có chính sách yêu cầu. [DocumentBuilderFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/parsers/DocumentBuilderFactory.html), [JAXP Security Guide](https://docs.oracle.com/en/java/javase/25/security/java-api-xml-processing-jaxp-security-guide.html).

Giới hạn 64 KiB và độ sâu 32 là lựa chọn cho tài liệu nhỏ của bài, không phải cấu hình chung cho mọi dịch vụ. Trong đầu vào HTTP/file thật, cần giới hạn ngay khi đọc và sau các bước giải nén phù hợp; kiểm tra sau khi đã nạp toàn bộ dữ liệu vào một `String` không ngăn được chi phí cấp phát trước đó.

## 7. Bảo vệ cả lúc biên dịch schema và lúc validation

Không chỉ làm cứng `DocumentBuilderFactory`. Schema có thể tham chiếu DTD hoặc schema khác; processor validation cũng có các điểm giải quyết tài nguyên. Bài đặt hạn chế trên `SchemaFactory` và `Validator`, đồng thời dùng nguồn XSD cố định do ứng dụng sở hữu.

Chuỗi rỗng trong thuộc tính truy cập ngoài nghĩa là không cho phép giao thức nào ở điểm kiểm tra ấy. Không thay bằng `all` chỉ để một lỗi import biến mất. Nếu ứng dụng thực sự cần nhiều schema, có thể dùng bộ tài nguyên nội bộ/catalog hoặc resolver với danh sách được phép, từ chối mọi tham chiếu ngoài danh sách. Resolver tự viết cũng là mã tin cậy: nó không được tải tùy ý theo URI do dữ liệu cung cấp.

`FEATURE_SECURE_PROCESSING` là một phần của chính sách, không phải cam kết mọi loại XML đều có chi phí thấp. Giữ các giới hạn xử lý, nguồn schema và biểu thức truy vấn có kiểm soát. [JAXP Security Guide về cấu hình factory và truy cập ngoài](https://docs.oracle.com/en/java/javase/25/security/java-api-xml-processing-jaxp-security-guide.html).

Schema validation và parser không sửa quyền truy cập nghiệp vụ. Một XML có `id=101` đúng kiểu vẫn cần được kiểm tra người gọi có được xem tài nguyên 101 hay không.

## 8. Namespace trong XPath phải khớp URI

XML mẫu dùng default namespace:

```xml
<order xmlns="urn:demo:order" id="101">
  <total>12.30</total>
</order>
```

Trong XPath 1.0 thông thường của API JDK, tên phần tử không có prefix không tự nhận default namespace của tài liệu. Vì vậy, truy vấn `/order/total` có thể không tìm được phần tử như người viết kỳ vọng.

Chương trình ánh xạ prefix truy vấn `o` sang URI `urn:demo:order`, rồi dùng `/o:order/o:total`. Prefix `o` không cần xuất hiện trong tài liệu; URI namespace mới là danh tính liên quan. [API XPath và NamespaceContext](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/xpath/XPath.html).

Đừng chữa lỗi namespace bằng cách bỏ qua mọi namespace và chỉ tìm theo `local-name()` ở mọi nơi. Hai phần tử cùng tên cục bộ nhưng khác namespace có thể mang nghĩa khác nhau. XSD và truy vấn nên thống nhất cùng hợp đồng namespace.

## 9. Biến XPath giữ dữ liệu tách khỏi cú pháp truy vấn

Biểu thức trong bài là một hằng:

```text
/o:order[@id=$wantedId]/o:total
```

Giá trị `wantedId` được cấp qua `XPathVariableResolver`. Chuỗi `101' or '1'='1` là dữ liệu của biến; nó không được ghép vào biểu thức để trở thành một điều kiện XPath mới. Kết quả `injectionMatched=false` kiểm chứng tình huống đó trên tài liệu mẫu.

Tránh cách tạo biểu thức như:

```java
// Minh họa cách ghép không an toàn; không dùng với đầu vào không tin cậy.
String expression = "/o:order[@id='" + suppliedId + "']/o:total";
```

Đoạn này chỉ minh họa lỗi thiết kế và cần các biến ở lớp tích hợp, không phải mã thuộc chương trình chạy phía trên. Không cố sửa bằng một quy tắc thay dấu nháy tự chế cho mọi biểu thức. Dùng biến cho giá trị; dùng danh sách biểu thức đã được phép nếu người dùng cần chọn loại truy vấn.

Một người dùng được phép truyền giá trị tìm kiếm không đồng nghĩa được phép gửi toàn bộ XPath tùy ý. Biểu thức không tin cậy có thể đọc rộng hơn phạm vi mong muốn hoặc gây chi phí xử lý. Chính sách trong bài không cung cấp chức năng chạy XPath tùy ý.

## 10. Cardinality và kiểu kết quả phải theo hợp đồng

Chương trình yêu cầu kết quả `XPathConstants.STRING`. Với tài liệu đã được XSD kiểm tra, mô hình chỉ có một `order` và đúng một `total`, nên cách trích xuất này phù hợp với phạm vi ví dụ.

Trong mô hình có nhiều nút, kết quả chuỗi có thể không phản ánh mọi nút người gọi tưởng đã kiểm tra. Nếu yêu cầu đúng một phần tử, truy vấn node-set và kiểm tra số phần tử, hoặc dùng schema/quy tắc rõ ràng bảo đảm điều ấy. Không chỉ lấy nút đầu tiên rồi bỏ qua phần còn lại của đầu vào.

Nếu cần tính số thập phân chính xác theo nghiệp vụ, lấy giá trị văn bản đã hợp lệ và chuyển sang kiểu thập phân phù hợp. Không mặc định kết quả số của XPath 1.0 là cách giữ nguyên độ chính xác thập phân bất kỳ.

Cũng phân biệt “không tìm thấy” với giá trị hợp lệ như `0`. Trong schema của bài, `total` bắt buộc là số thập phân nên chuỗi rỗng từ truy vấn theo id có thể biểu diễn không có nút khớp; mô hình khác cần quy tắc xử lý riêng.

## 11. Quyền sở hữu, đồng thời và thông báo lỗi

`Schema` là đối tượng có thể dùng chung an toàn theo hợp đồng API. `Validator` không an toàn luồng và không reentrant; `XPath` cũng không an toàn luồng. Bài tạo các đối tượng xử lý riêng trong mỗi lượt thay vì dùng một instance mutable chung cho nhiều yêu cầu. [Schema](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/validation/Schema.html), [Validator](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/validation/Validator.html), [XPath](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/xpath/XPath.html).

DOM đã được kiểm tra cũng không nên bị chỉnh sửa đồng thời trước/lúc truy vấn. Nếu sửa nội dung sau validation, kết quả validation trước đó không còn tự bảo đảm nội dung mới.

Handler trong ví dụ chuyển warning/error thành ngoại lệ và không để parser tự in chi tiết đầu vào ra stderr. Ứng dụng thật cần phân loại lỗi và trả thông báo phù hợp: cú pháp sai, không khớp schema, quá giới hạn, hoặc cấu hình processor không đáp ứng. Đừng gửi toàn bộ XML, system identifier hay đường dẫn nội bộ về cho người gọi khi không cần thiết.

Giữ dữ liệu chẩn đoán cần thiết ở phạm vi có quyền truy cập phù hợp, nhưng tránh log toàn bộ tài liệu vì XML có thể chứa thông tin bí mật. Thông báo “XML không hợp lệ” và mã lỗi có thể đủ cho phía gọi; vận hành có thể cần metadata đã được kiểm soát.

## 12. Mở rộng kiểm thử theo đúng đe dọa cần ngăn

| Ca kiểm thử | Điều cần xác nhận |
| --- | --- |
| XML hợp lệ, đúng namespace | Validation thành công và XPath lấy đúng dữ liệu |
| Sai kiểu, thiếu trường hoặc giá trị ngoài miền | Schema từ chối |
| Tên cục bộ đúng nhưng namespace sai | Không bị nhận như tài liệu đúng hợp đồng |
| DOCTYPE nội bộ hoặc tham chiếu ngoài | Hồ sơ không cho DTD từ chối trước khi dùng dữ liệu |
| Input quá lớn hoặc quá sâu | Bị chặn bởi giới hạn, không xử lý vô điều kiện |
| Chuỗi tìm kiếm chứa cú pháp giống XPath | Vẫn là giá trị biến, không sửa nghĩa biểu thức |
| Schema có import/include ngoài chính sách | Không tự mở quyền truy cập ngoài |
| Provider không hỗ trợ cài đặt bắt buộc | Khởi tạo thất bại, không chạy với cấu hình yếu hơn |

Ca `doctype` của chương trình chứng minh parser được cấu hình để từ chối DOCTYPE; nó không phải một cuộc kiểm toán mạng cho mọi cấu hình provider. Khi tích hợp hệ thống thật, kiểm tra thêm rằng không có bước khác phân tích lại tài liệu bằng processor chưa làm cứng hoặc tự tải schema theo đầu vào.

Bài tập: thêm một trường `quantity` bắt buộc, kiểu số nguyên dương, rồi cập nhật truy vấn cố định để trích xuất nó. Viết ca thiếu trường, giá trị 0 và namespace sai; giữ nguyên các hạn chế tài nguyên ngoài. Không mở mạng chỉ vì schema mới cần một kiểu dùng chung: xác định tài nguyên tin cậy và cách giải quyết cục bộ rõ ràng.

An toàn ở bài này đến từ một luồng xử lý nhất quán: nguồn schema tin cậy, parser/validator có hạn chế rõ, dữ liệu có giới hạn, XPath tách cú pháp khỏi giá trị và chỉ dùng đúng tài liệu đã được kiểm tra.
