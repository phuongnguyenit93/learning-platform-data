# Xác minh cấu hình bảo vệ trên đúng implementation đang sử dụng

> **Chương:** Bảo vệ xử lý XML  
> **Module:** SPRING_WEB_SERVICES — xây dựng dịch vụ SOAP contract-first bằng Spring Web Services (Spring-WS), thiết kế XSD/WSDL, JAXB/OXM, endpoint và SOAP client; xử lý SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích trong tích hợp doanh nghiệp.

## 1. Tại sao cấu hình bảo mật XML “đã đặt” vẫn chưa đủ?

Một ứng dụng Java có thể viết:

~~~java
factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
~~~

và cho rằng toàn bộ SOAP service đã an toàn trước XML External Entity (XXE), XML entity expansion hoặc external schema loading. Kết luận đó **không đủ căn cứ**. Một flag trên **một factory** không tự bảo vệ mọi parser, transformer, validator, XML marshaller hay SOAP message factory trong cùng ứng dụng. Hơn nữa, cách một flag được hỗ trợ, được áp dụng và có thể bị ghi đè phụ thuộc **implementation, phiên bản thư viện, JDK, provider và đường xử lý thực tế**.

Đây là bài về **xác minh bảo vệ đã hoạt động**, chứ không đơn thuần là liệt kê thuộc tính cấu hình.

### Sau bài học, bạn phải làm được

- Xác định **implementation/provider đang thực sự chạy** cho DOM, SAX, StAX, `SchemaFactory`, `TransformerFactory`, JAXB/OXM và SOAP message factory của Spring-WS.
- Hiểu khác biệt giữa cấu hình **JAXP API**, implementation-specific features và behavior thực tế của parser.
- Thiết lập chính sách không cho DTD, external entities, XInclude, external schema và external stylesheet khi ứng dụng không cần chúng.
- Biết **fail closed** khi thuộc tính bảo mật bắt buộc không được hỗ trợ, thay vì bỏ qua exception.
- Thiết kế kiểm thử âm tính có quan sát tài nguyên, chứng minh parser **không đọc file hay mở HTTP request** khi gặp đầu vào XML không tin cậy.
- Giải thích khi nào cần **XML Catalog/resource resolver whitelist** cho XSD/WSDL contract-first mà không bật truy cập mạng tùy ý.
- Kiểm tra cấu hình trong Spring Web Services ở **đúng vị trí nhận SOAP**, không chỉ trên một `DocumentBuilderFactory` ở code nghiệp vụ.
- Phân biệt bảo vệ XML parser với **SOAP XSD validation, WS-Security signature, mTLS, authorization** và các giới hạn tài nguyên.

**Nguyên tắc:** “Không ném exception khi gọi setter” là bước đầu, không phải bằng chứng cấu hình có hiệu lực trên request SOAP thật. Cần xác nhận **provider → thuộc tính → đường dữ liệu → phép thử âm tính → runtime đã đóng gói**.

## 2. Mô hình đe dọa đối với một SOAP service

SOAP là XML, do đó một service có thể chạm XML ở nhiều tầng trước khi nghiệp vụ nhận Java DTO:

~~~mermaid
flowchart TD
    A["HTTP SOAP / MTOM request"] --> B["SOAP MessageFactory"]
    B --> C["Envelope/Body parser"]
    C --> D["WS-Security: decrypt / verify"]
    D --> E["XSD Validator"]
    E --> F["JAXB/OXM / DOM / XPath endpoint"]
    F --> G["Business service"]
    G --> H["Marshaller + XSLT / Transformer"]
    H --> I["SOAP response"]
    X["WSDL/XSD imports & includes"] --> E
    Y["External URI/file resources"] -. "phải chặn hoặc whitelist" .-> B
    Y -. "phải chặn hoặc whitelist" .-> E
    Y -. "phải chặn hoặc whitelist" .-> H
~~~

Đây là sơ đồ **trách nhiệm**, không phải thứ tự bắt buộc của mọi Spring-WS/WS-SecurityPolicy. Một số stack parse SOAP trước khi gọi interceptor; quá trình verify/decrypt có thứ tự riêng theo policy. Điều cốt lõi: nếu một parser ở tầng đầu đã thực hiện external entity resolution, một `PayloadValidatingInterceptor` ở tầng sau **không thể hoàn tác** truy cập trái phép.

### 2.1. Các nhóm tấn công cần quan tâm

| Tấn công/đường lỗi | Đầu vào hoặc thành phần | Hậu quả có thể |
|---|---|---|
| XXE qua external general entity | XML chứa DTD/ENTITY trỏ file/URL | Đọc file, SSRF, tiết lộ dữ liệu |
| External parameter entity/DTD | External subset hoặc parameter entity | Truy cập tài nguyên ngoài, entity expansion |
| Entity expansion / Billion Laughs | Internal DTD với entity lồng | CPU/memory exhaustion |
| XInclude | Parser/DOM có bật XInclude | Đưa XML/file khác vào tài liệu |
| External XSD/import/include | `SchemaFactory`, `xs:import`, `xs:include`, `xsi:schemaLocation` | Tải schema không tin cậy, SSRF, đổi contract |
| XSLT `document()`, import/include | `TransformerFactory` | Đọc URL/file hoặc xử lý dữ liệu ngoài |
| XPath/XSLT extension functions | Implementation/provider mở extension | Side effects không mong muốn nếu stylesheet/expression untrusted |
| XML document quá lớn/sâu | XML/MTOM payload | Exhaustion heap, stack, CPU, temp disk |
| XML Signature Wrapping | Signed nodes khác nodes business parser dùng | Bypass integrity nếu security policy sai |
| Namespace spoofing | Prefix/QName/parser không namespace-aware | Endpoint mapping/validation sai |
| SOAP payload lộ qua logging | Interceptor/logger serialize toàn message | Lộ PII, tokens, certificates, attachments |

Các nhóm trên **không được giải quyết bởi một flag duy nhất**. Ví dụ, không tải external DTD vẫn không tự giới hạn XML 100 MiB, và XSD validation vẫn không thay thế WS-Security/authorization.

### 2.2. Ba ranh giới đầu vào

- **Untrusted XML instances:** SOAP Body/Header, XML upload, callback payload do client/đối tác cung cấp.
- **Trusted contract assets:** XSD/WSDL/XSLT được đóng gói, review, ký duyệt hoặc pin version; chúng vẫn cần cơ chế resolve phụ thuộc có giới hạn.
- **Untrusted references:** URLs trong XML/DTD, XSD location hints, XSLT document URIs hoặc attachment paths; không được tự coi là đáng tin chỉ vì xuất hiện trong một tài liệu XML.

Một ứng dụng có thể cho phép `xs:include` giữa hai XSD **nội bộ được duyệt** mà vẫn chặn external schema do caller SOAP gợi ý. “Cấm tất cả XML imports” và “cho phép mọi URL” đều có thể sai nếu không phân biệt **nguồn tham chiếu** và **policy**.

## 3. Biết đúng implementation: API không phải provider

Các lớp `DocumentBuilderFactory`, `SAXParserFactory`, `XMLInputFactory`, `TransformerFactory` và `SchemaFactory` là các factory interfaces/abstract classes. Phương thức `newInstance()` chọn **provider thực**, có thể chịu ảnh hưởng của:

- Classpath/module path và service-provider declarations.
- JAXP configuration/system properties.
- Java runtime distribution/version và provider tích hợp trong JDK.
- Dependencies do Spring Boot BOM/thư viện SOAP/JAXB/XML security mang vào.
- Custom class loader, application server, plugin container hoặc test runner.
- XML message factory hoặc marshaller **tự tạo provider khác** bên trong.

**Một lần in class name từ code tiện ích không chứng minh mọi XML path trong ứng dụng dùng cùng provider.** Cần kiểm tra tại từng nơi tạo factory hoặc qua behavior test end-to-end.

### 3.1. In provider thực của các JAXP factories

Ví dụ Java 17:

~~~java
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.parsers.SAXParserFactory;
import javax.xml.transform.TransformerFactory;
import javax.xml.validation.SchemaFactory;
import javax.xml.stream.XMLInputFactory;
import javax.xml.xpath.XPathFactory;

public final class XmlProviderInventory {
    public static void main(String[] args) {
        print("DOM", DocumentBuilderFactory.newInstance());
        print("SAX", SAXParserFactory.newInstance());
        print("StAX", XMLInputFactory.newFactory());
        print("XSLT", TransformerFactory.newInstance());
        print("Schema", SchemaFactory.newInstance(
                XMLConstants.W3C_XML_SCHEMA_NS_URI));
        print("XPath", XPathFactory.newInstance());
    }

    private static void print(String name, Object provider) {
        Class<?> type = provider.getClass();
        System.out.println(name + " provider=" + type.getName()
                + " loader=" + type.getClassLoader());
    }
}
~~~

Output ví dụ **chỉ là minh họa**:

~~~text
DOM provider=com.some.xml.DomBuilderFactory
SAX provider=com.some.xml.SaxParserFactory
StAX provider=com.some.xml.StaxInputFactory
Schema provider=com.some.xml.SchemaFactory
...
~~~

Không hardcode các tên provider minh họa để so sánh. Trong hệ thống thật, nên ghi inventory ở startup/test diagnostics với **tên class, artifact/version và Java runtime**, nhưng không log configuration secrets hoặc nội dung XML.

### 3.2. `newInstance()` không đồng nghĩa với `newDefaultInstance()`

Trên một số JAXP factories hiện đại có các API lựa chọn **system-default implementation**, khác cơ chế lookup provider có thể bị ảnh hưởng bởi classpath. Chọn provider mặc định của JDK **không nên là mẹo âm thầm để che một dependency xung đột**: nếu Spring-WS/SAAJ/JAXB dùng provider khác, kiểm thử helper vẫn có thể qua mà SOAP request thật vẫn thiếu bảo vệ.

Hãy kiểm chứng:

1. Provider được **test fixture** dùng.
2. Provider được **ứng dụng production** dùng.
3. Provider được **Spring-WS message factory, marshaller và validators** dùng.
4. Provider ở **WAR/application server** hoặc executable JAR/container cuối cùng.

### 3.3. Kiểm tra “setter được chấp nhận” chưa đủ

Ví dụ:

~~~java
factory.setFeature(
    "http://apache.org/xml/features/disallow-doctype-decl",
    true);
~~~

Đây là **feature URI gắn với những implementation như Xerces**, không phải mọi parser đều phải hỗ trợ. Có implementation ném `ParserConfigurationException`, có provider xử lý cấu hình theo cách khác, và một XML path khác có thể dùng factory không được cấu hình. Phải:

- Không nuốt lỗi khi một bảo vệ **bắt buộc** không được hỗ trợ.
- Test thực với XML có DOCTYPE/external reference.
- Xác minh request đi qua đúng parser mà bạn đã cấu hình.
- Ghi nhận provider/version để phát hiện thay đổi khi nâng dependency/JDK.

## 4. Định nghĩa tiêu chí bảo vệ có thể kiểm chứng

Trước khi chọn API, viết **acceptance criteria** cho dữ liệu XML chưa tin cậy.

| Tiêu chí | Kết quả mong đợi |
|---|---|
| XML hợp lệ đơn giản | Parse/validate thành công |
| XML chứa DOCTYPE khi policy cấm | Bị từ chối **trước** khi sử dụng entity |
| External entity tới file test | Không đọc file; request bị từ chối |
| External entity tới HTTP test receiver | Không có outbound HTTP request |
| External parameter entity/DTD | Bị từ chối hoặc không được resolve |
| XInclude tới file/URL | Không include tài nguyên |
| External XSLT stylesheet/document | Không tải tài nguyên chưa duyệt |
| External XSD hint từ XML instance | Không đổi tập XSD được tin cậy |
| XSD nội bộ có include/import đã duyệt | Vẫn compile/validate thành công qua resolver whitelist |
| XML quá lớn/quá sâu | Từ chối trong hạn mức được thiết kế |
| SOAP Header/Body namespace sai | Không được chấp nhận nhầm |
| Provider không hỗ trợ security flag bắt buộc | **Fail startup/config**, không tiếp tục im lặng |
| Client WS-Security signature sai | Bị từ chối theo security policy, bất kể XML well-formed |
| Servlet/gateway/MTOM vượt quota | Không qua business layer |

### 4.1. Dùng fixtures nhỏ, có kiểm soát

Không cần tạo một payload “Billion Laughs” khổng lồ để chứng minh nguy cơ. Chỉ cần một **DTD nhỏ** đáng lẽ phải bị từ chối và một URL tới **test receiver do đội kiểm thử sở hữu** để xác minh không có request ra ngoài.

Không thử truy cập file bí mật thật, cloud metadata service thật hoặc máy chủ production. Cấu hình một **sentinel file tạm** trong test sandbox, nội dung giả, và đối chiếu kết quả. Khi test HTTP egress, dùng mock server/traffic spy trong mạng kiểm soát.

### 4.2. “Không thấy dữ liệu rò rỉ trong output” chưa đủ

Một XXE có thể **đã đọc file** hoặc gọi HTTP nhưng dữ liệu không xuất hiện trong SOAP response. Phép thử chỉ assert “string output không chứa secret” không chứng minh không có external resolution.

Test phải quan sát:

- Parser có từ chối DTD/ENTITY hay không.
- Test receiver có nhận HTTP GET/POST không.
- Resource resolver có bị gọi với URI không được phê duyệt không.
- Quota CPU/memory/time có được áp dụng không.
- Lỗi có được chuyển thành SOAP Fault/HTTP failure **không lộ nội dung input** không.

## 5. DOM DocumentBuilderFactory: cấu hình và fail closed

Với XML chưa tin cậy phải parse thành DOM, hãy tạo factory theo **một chính sách cụ thể**. Ví dụ dưới đây dùng API JAXP và một số features được hỗ trợ bởi nhiều Xerces-compatible parsers, nhưng **phải xác minh trên provider thực**.

### 5.1. Mẫu factory bảo vệ đầu vào

~~~java
package com.example.soap.xml;

import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.parsers.ParserConfigurationException;

public final class SecureDomFactory {
    private SecureDomFactory() {}

    public static DocumentBuilderFactory create() {
        DocumentBuilderFactory factory =
                DocumentBuilderFactory.newInstance();

        factory.setNamespaceAware(true);

        try {
            factory.setFeature(
                    XMLConstants.FEATURE_SECURE_PROCESSING, true);

            // Chính sách này từ chối mọi DOCTYPE.
            factory.setFeature(
                "http://apache.org/xml/features/disallow-doctype-decl",
                true);

            // Defense in depth nếu provider hỗ trợ.
            factory.setFeature(
                "http://xml.org/sax/features/external-general-entities",
                false);
            factory.setFeature(
                "http://xml.org/sax/features/external-parameter-entities",
                false);
            factory.setFeature(
                "http://apache.org/xml/features/nonvalidating/load-external-dtd",
                false);

            factory.setXIncludeAware(false);
            factory.setExpandEntityReferences(false);

            factory.setAttribute(
                    XMLConstants.ACCESS_EXTERNAL_DTD, "");
            factory.setAttribute(
                    XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        } catch (ParserConfigurationException
                 | IllegalArgumentException
                 | UnsupportedOperationException ex) {
            throw new IllegalStateException(
                "Required XML parser security unavailable: "
                    + factory.getClass().getName(), ex);
        }

        return factory;
    }
}
~~~

Với provider không hỗ trợ `setXIncludeAware`, có thể có `UnsupportedOperationException`. Một cấu hình production muốn **fail closed triệt để** cũng phải xử lý lỗi này (và các runtime errors tương ứng) **một cách rõ ràng**, hoặc thay provider được kiểm thử; không tiếp tục xử lý XML chưa tin cậy sau khi bước hardening quan trọng thất bại.

**Hai điều cần nhớ:**

1. `setExpandEntityReferences(false)` **không phải** một biện pháp phòng XXE đủ dùng riêng lẻ; cần chặn DTD/external entities và external access.
2. `FEATURE_SECURE_PROCESSING` không bảo đảm tự chặn mọi external reference trên mọi JAXP provider/version. Hãy đặt rõ `ACCESS_EXTERNAL_DTD`/`ACCESS_EXTERNAL_SCHEMA` và feature tương ứng, rồi kiểm thử behavior.

### 5.2. Parse XML mà không thêm quyền truy cập ngoài

~~~java
import java.io.InputStream;
import org.w3c.dom.Document;

public Document parseUntrustedXml(InputStream input)
        throws Exception {
    var factory = SecureDomFactory.create();
    var builder = factory.newDocumentBuilder();

    // Không đặt EntityResolver cho phép tải URL bất kỳ.
    return builder.parse(input);
}
~~~

Mẫu này giả định caller **giới hạn số bytes của input**, thiết lập timeout ở tầng HTTP và đóng stream theo ownership policy. Do `DocumentBuilder` không nên được chia sẻ tùy ý giữa nhiều threads, ứng dụng có thể tạo builder riêng theo request hoặc sử dụng pool được kiểm soát, tránh biến một instance mutable thành singleton.

### 5.3. Tại sao tạo response DOM khác với parse input?

Lời gọi:

~~~java
Document document = DocumentBuilderFactory.newInstance()
        .newDocumentBuilder()
        .newDocument();
~~~

chỉ **tạo tài liệu rỗng**, không parse nội dung bên ngoài. Nó có rủi ro khác với `parse(InputStream)` trên dữ liệu client. Tuy vậy, nếu sau đó ứng dụng dùng `Transformer` hoặc marshal một cấu trúc chứa external references, vẫn phải bảo vệ **từng giai đoạn** phát sinh I/O riêng.

### 5.4. Không fallback sang parser yếu hơn

Phản ví dụ:

~~~java
try {
    configureSecureFeatures(factory);
} catch (Exception ignored) {
    // Nguy hiểm: vẫn dùng factory chưa được harden.
}
~~~

Nếu thuộc tính bảo mật bắt buộc không tồn tại, hành vi đúng là **dừng startup/config hoặc chặn đường XML chưa tin cậy**, báo lỗi nội bộ có kiểm soát và thay provider/config. Không bắt mọi exception rồi parse bằng default factory như “chế độ tương thích”.

## 6. SAX và XMLReader: phải bảo vệ cả parser kiểu sự kiện

SAX xử lý XML theo sự kiện, thường tránh phải giữ cả DOM tree trong heap, nhưng **không tự an toàn trước XXE**. Một `SAXParserFactory` có thể dùng implementation/provider riêng, và `XMLReader` có các feature/property ở tầng reader cần kiểm chứng.

### 6.1. Mẫu cấu hình SAX

~~~java
package com.example.soap.xml;

import javax.xml.XMLConstants;
import javax.xml.parsers.SAXParser;
import javax.xml.parsers.SAXParserFactory;
import org.xml.sax.SAXException;
import org.xml.sax.XMLReader;

public final class SecureSaxFactory {
    private SecureSaxFactory() {}

    public static XMLReader createReader() {
        try {
            SAXParserFactory factory =
                    SAXParserFactory.newInstance();
            factory.setNamespaceAware(true);
            factory.setFeature(
                    XMLConstants.FEATURE_SECURE_PROCESSING, true);

            factory.setFeature(
                "http://apache.org/xml/features/disallow-doctype-decl",
                true);
            factory.setFeature(
                "http://xml.org/sax/features/external-general-entities",
                false);
            factory.setFeature(
                "http://xml.org/sax/features/external-parameter-entities",
                false);
            factory.setFeature(
                "http://apache.org/xml/features/nonvalidating/load-external-dtd",
                false);

            SAXParser saxParser = factory.newSAXParser();
            XMLReader reader = saxParser.getXMLReader();

            reader.setProperty(
                    XMLConstants.ACCESS_EXTERNAL_DTD, "");
            reader.setProperty(
                    XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

            reader.setEntityResolver((publicId, systemId) -> {
                throw new SAXException(
                        "External XML entity resolution denied");
            });

            return reader;
        } catch (Exception ex) {
            throw new IllegalStateException(
                    "Required SAX parser security unavailable", ex);
        }
    }
}
~~~

**Phạm vi cần xác minh:** `XMLReader#setProperty(...)` có thể từ chối một property trên một số providers; `SAXParserFactory#setFeature(...)` cũng có thể không hỗ trợ URI của Xerces. Ví dụ cố ý **fail closed**: nếu cấu hình không chạy được, không dùng reader đó để xử lý request.

Trong production, nên bắt nhóm exceptions dự kiến với thông điệp provider rõ ràng và giữ stack trace **nội bộ**; không gửi exception chi tiết về clients. Nếu một parser không hỗ trợ thuộc tính bắt buộc, phải thay parser hoặc đưa vào một cơ chế kiểm tra có bằng chứng tương đương, không bỏ qua exception rồi coi là bảo mật.

### 6.2. SAXParser và XMLReader là hai điểm cấu hình khác nhau

Một số chương trình chỉ harden `SAXParserFactory` nhưng sau đó một thư viện gọi `XMLReaderFactory`, tạo reader riêng, hoặc dùng `SAXSource` chứa reader do caller đưa tới. Vì vậy cần kiểm tra **instance thực dùng để parse**, không chỉ factory mà bạn tự khai báo.

Với JAXB `Unmarshaller.unmarshal(SAXSource)`, nguồn `SAXSource` có thể mang `XMLReader` và `InputSource`. Khi có đường unmarshalling như vậy, hãy tạo reader đã được bảo vệ và test với XML input thực. Đừng cho caller truyền `SAXSource`/`XMLReader` tùy ý vượt qua chính sách ứng dụng.

### 6.3. Dữ liệu lớn vẫn cần quota

SAX giảm nhu cầu lưu cây, nhưng không ngăn một XML message có hàng triệu elements, text cực dài, depth quá sâu hoặc HTTP streaming không có giới hạn. Cần thêm:

- Giới hạn bytes tại gateway/HTTP và SOAP message layer.
- Giới hạn XML depth, total nodes/attributes và string lengths khi parser/provider hỗ trợ.
- Timeout, request concurrency limits, CPU budgets.
- Validation XSD và business limits theo contract.
- Test với payload vừa đủ vượt ngưỡng, không tạo payload phá hoại hàng gigabyte.

Không dùng “streaming” làm lý do bỏ tất cả resource limits.

## 7. StAX XMLInputFactory: hai thuộc tính thường bị quên

StAX phù hợp với streaming XML, nhưng `XMLInputFactory` có cấu hình DTD và external entity **độc lập** với DOM/SAX. Nếu Spring-WS/JAXB hoặc thư viện khác dùng StAX reader được tạo ở nơi khác, cấu hình DOM không tác động tới nó.

### 7.1. Mẫu StAX không chấp nhận DTD

~~~java
package com.example.soap.xml;

import java.io.InputStream;
import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLStreamConstants;
import javax.xml.stream.XMLStreamException;
import javax.xml.stream.XMLStreamReader;

public final class SecureStax {
    private SecureStax() {}

    public static XMLInputFactory factory() {
        XMLInputFactory f = XMLInputFactory.newFactory();

        try {
            f.setProperty(XMLInputFactory.SUPPORT_DTD, false);
            f.setProperty(
                    XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES,
                    false);
            // Một số providers hỗ trợ JAXP external access property;
            // yêu cầu support nếu policy ứng dụng coi đây là bắt buộc.
            f.setProperty(
                    javax.xml.XMLConstants.ACCESS_EXTERNAL_DTD,
                    "");
        } catch (IllegalArgumentException ex) {
            throw new IllegalStateException(
                    "StAX provider cannot enforce XML policy: "
                            + f.getClass().getName(), ex);
        }

        return f;
    }

    public static void consumeSafely(InputStream input)
            throws XMLStreamException {
        XMLStreamReader reader =
                factory().createXMLStreamReader(input);

        try {
            while (reader.hasNext()) {
                if (reader.next() == XMLStreamConstants.DTD) {
                    throw new XMLStreamException(
                            "DOCTYPE prohibited by XML policy");
                }
                // Xử lý streaming XML theo contract.
            }
        } finally {
            reader.close();
        }
    }
}
~~~

Ví dụ minh họa **vòng đọc và chính sách DTD**, không phải một parser SOAP đầy đủ. `InputStream` thuộc caller phải được đóng ở tầng sở hữu stream; `XMLStreamReader#close` không phải cam kết mọi provider đều đóng input stream gốc. Lưu ý `ACCESS_EXTERNAL_DTD` trên `XMLInputFactory` có thể không được provider hỗ trợ: fail closed là quyết định thiết kế có chủ đích, không được mặc định rằng mọi StAX implementation chấp nhận property đó.

### 7.2. Tại sao vẫn cần test hành vi?

Một provider có thể:

- Ném exception ngay khi gặp DOCTYPE.
- Bỏ qua DTD nhưng phát `DTD` event.
- Cho phép internal DTD dù external entities bị tắt.
- Thay đổi default khi nâng phiên bản.
- Cho phép XMLResolver custom tải tài nguyên nếu cấu hình không đúng.

Nếu **policy yêu cầu cấm hoàn toàn DOCTYPE**, test phải xác minh XML chứa DOCTYPE bị từ chối, không chỉ “external entity không được mở”. Khi cần, có thể cung cấp `XMLResolver` **từ chối mọi external resolution**, đồng thời cấm DTD và external access. Một resolver tự trả stream từ URL do caller cung cấp sẽ phá chính sách dù `SUPPORT_DTD` đã được đặt trong một factory khác.

### 7.3. Những API không tự “chữa” StAX

- `XMLStreamReader` được thư viện khác tạo trước khi gọi JAXB không bị thay đổi retroactively bởi factory mới của bạn.
- `StAXSource` chỉ bọc reader; XML có thể đã được parse một phần hoặc resolver đã mở resource.
- `WebServiceTemplate` với marshaller dùng StAX có thể được cấu hình bằng provider nội bộ riêng.
- `XMLInputFactory` và `XMLOutputFactory` có trách nhiệm khác nhau: outbound writer không phải inbound reader.

Vì vậy phải kiểm tra từ **HTTP SOAP request thực** đến endpoint, không chỉ một `newFactory()` trong unit test.

## 8. TransformerFactory và XSLT: chống external document/stylesheet

Transformer có thể được dùng để copy XML, biến đổi `Source` thành `Result`, viết SOAP Header, render payload hoặc thực thi một stylesheet XSLT. Nếu một stylesheet được cung cấp bởi bên không tin cậy, nó có thể tham chiếu **external document**, `xsl:import` hoặc `xsl:include`.

### 8.1. Mẫu TransformerFactory với external access bị tắt

~~~java
package com.example.soap.xml;

import javax.xml.XMLConstants;
import javax.xml.transform.TransformerException;
import javax.xml.transform.TransformerFactory;

public final class SecureXsltFactory {
    private SecureXsltFactory() {}

    public static TransformerFactory create() {
        TransformerFactory f = TransformerFactory.newInstance();

        try {
            f.setFeature(
                    XMLConstants.FEATURE_SECURE_PROCESSING, true);
            f.setAttribute(
                    XMLConstants.ACCESS_EXTERNAL_DTD, "");
            f.setAttribute(
                    XMLConstants.ACCESS_EXTERNAL_STYLESHEET, "");

            f.setURIResolver((href, base) -> {
                throw new TransformerException(
                    "External XSLT resolution prohibited");
            });
        } catch (Exception ex) {
            throw new IllegalStateException(
                    "Required XSLT security unavailable: "
                            + f.getClass().getName(), ex);
        }

        return f;
    }
}
~~~

Một `TransformerFactory` với property chưa hỗ trợ thường có thể ném `IllegalArgumentException`. Ví dụ chọn fail closed. Đừng thiết lập “thư giãn” các property sau khi factory tạo `Templates`/`Transformer` rồi suy rằng instance đã tạo sẽ tự cập nhật policy.

### 8.2. Những gì cấu hình này làm được và chưa làm được

- Giới hạn external references mà **implementation** tuân thủ trong quá trình transform/compile stylesheet.
- Có `URIResolver` mặc định từ chối tài nguyên ngoài.
- Không tự giới hạn mọi chi phí CPU/memory của một XSLT cực lớn.
- Không retroactively sửa một `DOMSource` đã parse XML không an toàn trước đó.
- Không thay đổi bộ `TransformerFactory` nội bộ mà một thư viện khác đã tự tạo.
- Không bảo vệ `JAXBUnmarshaller`/`SchemaFactory` nếu chúng có resolver riêng.
- Không bảo đảm một transformer arbitrary provider không hỗ trợ extension functions nguy hiểm theo cách khác; hãy kiểm tra khả năng mở extensions và dùng **trusted XSLT only**.

### 8.3. Khi cần XSLT nội bộ import stylesheet phụ thuộc

Một stylesheet được tổ chức review có thể dùng `xsl:include href="shared.xsl"`. Nếu tắt mọi external stylesheet reference, việc biên dịch có thể thất bại. Điều đó không có nghĩa cần bật `http,file` cho tất cả:

1. Lưu XSLT chính và các dependencies trong classpath/library đã phê duyệt.
2. Cung cấp `URIResolver` **whitelist** map tên logical → tài nguyên tin cậy; không để input quyết định URI.
3. Giữ base URI phù hợp khi dùng `StreamSource` để resolver xác định resource.
4. Từ chối mọi path traversal, absolute URL lạ và protocol ngoài policy.
5. Test XSLT import nội bộ **thành công**; XSLT remote/untrusted bị từ chối mà không có egress.

Nếu bật quyền `file` rộng cho transformer chỉ để giải quyết `shared.xsl`, parser có thể đọc **file ngoài thư mục hợp đồng**, gây rủi ro khi source/stylesheet chịu ảnh hưởng của client. Dùng resolver chặt hơn.

## 9. SchemaFactory, Validator và XSD import/include

Spring-WS contract-first thường cần `xs:import`, `xs:include`, JAXB-generated model, validator của request/response. Đây là **phần dễ phát sinh mâu thuẫn**: cần nạp XSD nội bộ nhưng không được cho phép SOAP client điều khiển nguồn schema.

### 9.1. Phân biệt schema được trust và location hint từ XML

Ví dụ một payload instance có:

~~~xml
<ord:GetOrderRequest
    xmlns:ord="urn:example:orders:v1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
      urn:example:orders:v1
      https://untrusted.example/schema.xsd">
  <ord:orderId>ORD-1001</ord:orderId>
</ord:GetOrderRequest>
~~~

`xsi:schemaLocation` là **gợi ý trong XML instance**, không phải nguồn sự thật để server contract-first tải XSD mới. Server phải validate bằng schema đã đăng ký và phê duyệt, chứ không tự tải một URL do caller điền.

Một bộ schema tin cậy có thể trông như sau:

~~~text
classpath:/xsd/orders/orders.xsd
    ├── xs:include → order-types.xsd
    └── xs:import  → ../common/common.xsd
                              └── xs:include → common-types.xsd
~~~

Hai quan hệ import/include ở đây là **trusted contract dependencies**, khác với URL ngoài do SOAP caller cung cấp.

### 9.2. Cấu hình JAXP SchemaFactory

~~~java
package com.example.soap.xml;

import javax.xml.XMLConstants;
import javax.xml.validation.SchemaFactory;

public final class SecureSchemaFactory {
    private SecureSchemaFactory() {}

    public static SchemaFactory create() {
        SchemaFactory f = SchemaFactory.newInstance(
                XMLConstants.W3C_XML_SCHEMA_NS_URI);

        try {
            f.setFeature(
                    XMLConstants.FEATURE_SECURE_PROCESSING, true);
            f.setProperty(
                    XMLConstants.ACCESS_EXTERNAL_DTD, "");
            f.setProperty(
                    XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        } catch (Exception ex) {
            throw new IllegalStateException(
                    "Required XSD security unavailable: "
                            + f.getClass().getName(), ex);
        }

        return f;
    }
}
~~~

Phải giải quyết các XSD dependencies nội bộ bằng **catalog/resource resolver được duyệt** hoặc đưa các sources đã được tin cậy vào schema compilation theo cơ chế provider hỗ trợ. Khi dùng `LSResourceResolver`, giới hạn mapping tới các tài nguyên đã review; không mở `file:` hoặc `https:` tùy ý do input điều khiển.

### 9.3. `Schema` và `Validator`: vòng đời khác nhau

~~~java
import javax.xml.validation.Schema;
import javax.xml.validation.Validator;

// Compile trusted XSD sources với resolver đã phê duyệt.
Schema schema = schemaFactory.newSchema(trustedSources);

// Mỗi lượt validate tạo Validator riêng, không dùng chung
// một mutable Validator cho nhiều threads.
Validator validator = schema.newValidator();
validator.setProperty(
        javax.xml.XMLConstants.ACCESS_EXTERNAL_DTD, "");
validator.setProperty(
        javax.xml.XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
validator.validate(xmlSource);
~~~

`trustedSources` và `xmlSource` là các biến giả định, cần được tạo từ **đúng schema đã duyệt** và **đúng XML payload**. Đặt `ACCESS_EXTERNAL_*` trên validator bổ sung defense-in-depth, nhưng có provider không hỗ trợ property hoặc tương tác khác với resolver; phải kiểm tra và fail closed khi đó là bắt buộc.

Lưu ý: một `Schema` compiled có thể được tái sử dụng theo API, còn `Validator` có trạng thái mutable và **không nên chia sẻ cùng instance qua request threads**.

### 9.4. Chỉ truyền đúng input root tới validator

Nếu XSD định nghĩa `ord:GetOrderRequest`, một validator kiểm tra **payload XML** chứ không phải toàn SOAP Envelope trừ khi schema chứa định nghĩa Envelope. Trong Spring-WS, `PayloadValidatingInterceptor` hướng đến payload, sau khi message factory đã parse SOAP.

Vì vậy test `SchemaFactory` chạy thành công trên một XML string không chứng minh `SoapMessageFactory` đã an toàn. Và test `PayloadValidatingInterceptor` bắt XML sai schema cũng không chứng minh external DTD đã bị chặn **trước đó**.

### 9.5. Lỗi khi chặn external schema quá mạnh

Nếu bật `ACCESS_EXTERNAL_SCHEMA=""` mà file `orders.xsd` vẫn tham chiếu `../common/common.xsd` qua đường dẫn tương đối mặc định, compiler có thể không resolve được. Cách xử lý **không phải** bật toàn bộ network access.

Hãy kiểm tra:

- Base URI/systemId của root `StreamSource`.
- Tài nguyên thật trong classpath/executable JAR.
- Resolver/catalog mapping đúng namespace/system ID.
- XSD collection/nested include/import không định nghĩa trùng global types.
- Provider có gọi resolver trước khi áp dụng restriction không.
- Các test chạy được cả khi **mất Internet**.

Nếu cần cho phép một ít `file` resource qua provider, phải quyết định policy scope rất cẩn thận, dùng local allowlist/resolver và test không thể đọc file ngoài danh sách. Đây là quyết định bảo mật, không phải “sửa warning” bằng wildcard quyền.

## 10. JAXB/OXM: một lớp model an toàn không bảo đảm parser an toàn

Trong Spring Web Services, JAXB/OXM chuyển giữa Java object và XML payload. Nhưng **JAXB model được sinh từ XSD** không tự áp dụng DTD policy, không đồng nghĩa với việc schema validation luôn bật và cũng không kiểm soát mọi parser có thể được tạo ở tầng input.

### 10.1. Một unmarshaller có thể nhận nhiều loại Source

Các đường thường gặp:

| Input | Điều phải xác minh |
|---|---|
| `DOMSource` | DOM đã được parse từ trước; parser DOM ban đầu có chặn XXE không? |
| `SAXSource` | `XMLReader` bên trong có được cấu hình chống DTD/external entities không? |
| `StAXSource` | `XMLStreamReader`/`XMLEventReader` do provider nào tạo? Có cấm DTD không? |
| `StreamSource` | JAXB provider có thể tự tạo parser; cấu hình/parser nội bộ là gì? |
| SOAP Body do Spring-WS cấp | Message factory đã parse thế nào, đã đọc DTD/entity trước JAXB chưa? |

Ví dụ truyền `SAXSource` sử dụng reader do ứng dụng tạo:

~~~java
import java.io.InputStream;
import javax.xml.transform.sax.SAXSource;
import org.xml.sax.InputSource;

// springUnmarshaller là org.springframework.oxm.Unmarshaller,
// đã cấu hình cho JAXB model đúng schema.
InputSource input = new InputSource(untrustedXmlStream);
SAXSource source = new SAXSource(
        SecureSaxFactory.createReader(), input);

Object value = springUnmarshaller.unmarshal(source);
~~~

`springUnmarshaller` và `untrustedXmlStream` là biến do ứng dụng cung cấp. Cần kiểm tra Spring OXM implementation/version, exception behavior, schema validation, stream ownership và các XML limits. Mẫu này **không thay** bảo vệ SOAP MessageFactory nếu đường xử lý đầu tiên đã parse Envelope trước đó.

### 10.2. Namespace và Jakarta JAXB

Spring-WS/Spring Boot thế hệ Jakarta dùng JAXB API như `jakarta.xml.bind`; các dự án cũ có thể dùng `javax.xml.bind`. Ngược lại, những JAXP classes như `javax.xml.parsers.DocumentBuilderFactory`, `javax.xml.transform.Source` và `javax.xml.validation.SchemaFactory` **vẫn thuộc `javax.xml` trong Java SE**.

Đừng thay hàng loạt `javax.xml.parsers` thành `jakarta.xml.parsers` vì nhìn thấy một dự án Spring Boot 3+. Phải kiểm tra dependency/API thực tế.

### 10.3. JAXB-generated DTO không thay XSD validation

Nếu XSD quy định:

~~~xml
<xs:element name="quantity" type="xs:positiveInteger"/>
~~~

thì đối tượng Java có thuộc tính số nguyên không mặc định chứng minh request XML đã được kiểm tra đúng `xs:positiveInteger` và mọi facets theo schema. Cần dùng XSD validator được cấu hình hợp lệ, ví dụ Spring-WS `PayloadValidatingInterceptor` hoặc cơ chế tương đương, **sau khi** XML input đã được parse an toàn.

Đồng thời, một request đúng XSD vẫn có thể bị từ chối do WS-Security signature sai hoặc caller không có quyền. Không coi validation của XML là authentication.

## 11. Spring-WS SOAP MessageFactory: mắt xích dễ bị bỏ qua

### 11.1. Vì sao harden JAXP DOM trong endpoint chưa đủ?

Giả sử endpoint:

~~~java
@Endpoint
public class OrdersEndpoint {
    @PayloadRoot(namespace = "urn:example:orders:v1",
                 localPart = "GetOrderRequest")
    @ResponsePayload
    public GetOrderResponse getOrder(
            @RequestPayload GetOrderRequest request) {
        // ...
    }
}
~~~

Trước khi Java method này được gọi, Spring-WS đã cần xử lý HTTP SOAP message, tìm payload QName và có thể dùng SOAP message factory/parser để tạo representation của Envelope/Header/Body. Một entity bên ngoài có thể được xử lý **ở giai đoạn sớm** nếu implementation/config không an toàn.

Một `DocumentBuilderFactory` tự tạo trong business service, dù đã harden, **không tự đổi parser** dùng bên trong SAAJ/Axiom/message factory hoặc SOAP client khác.

### 11.2. Kiểm tra bean SOAP message factory thực

Các thành phần cần xem xét trong **chính application context**:

- Bean `org.springframework.ws.WebServiceMessageFactory` hoặc cấu hình message factory mà servlet/template sử dụng.
- Implementation thực, chẳng hạn `SaajSoapMessageFactory` khi stack đó được chọn; những ứng dụng/version cũ có thể có lựa chọn khác.
- SAAJ provider thực (API/package có thể khác giữa Jakarta và Java EE), XML parser/streaming implementation bên trong.
- Spring-WS version, JDK runtime, JAXB provider, Apache HttpClient/HTTP sender nếu có.
- Mọi tùy biến MessageDispatcherServlet, message receiver, interceptors, payload mappings.
- Vị trí SOAP Body được trích vào `Source`/JAXB: DOM, SAX, StAX hoặc implementation-specific representation.

**Không** kết luận tất cả Spring-WS releases có cùng default message factory. Đặc biệt khi nâng Spring-WS/Jakarta/SAAJ provider, phải đo lại behavior.

### 11.3. Startup inventory trên Spring application context

Ví dụ bean Java chỉ quan sát class của message factory **thật được inject**:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.WebServiceMessageFactory;

@Configuration
public class SoapRuntimeInventory {

    private static final Logger log =
            LoggerFactory.getLogger(SoapRuntimeInventory.class);

    @Bean
    public ApplicationRunner soapFactoryReport(
            WebServiceMessageFactory soapMessageFactory) {
        return args -> log.info(
                "soap_message_factory={}",
                soapMessageFactory.getClass().getName());
    }
}
~~~

Đoạn code giả định chỉ có **một** bean tương ứng hoặc DI đã xác định qualifier. Nếu có nhiều message factories/templates, phải kiểm kê từng bean và mapping thực tới servlet/client. Class name này chỉ là **bằng chứng về factory bên ngoài**, chưa nói provider SAX/DOM/StAX nội bộ có chặn DTD hay không.

### 11.4. Cách xác minh đúng đường inbound

Kiểm thử phải gửi SOAP request **qua chính HTTP endpoint** ở môi trường test với config giống production:

~~~text
HTTP request
  → MessageDispatcherServlet / message receiver
  → SOAP MessageFactory
  → WS-Security / interceptors / endpoint mapping
  → JAXB / endpoint
~~~

Các assertions quan trọng:

1. SOAP request hợp lệ, đúng Envelope/QName, vẫn được xử lý.
2. Request có DOCTYPE theo policy cấm bị từ chối.
3. Test receiver cho external entity không nhận HTTP request nào.
4. Endpoint/business service không chạy nếu XML chưa được chấp nhận.
5. Lỗi parser không echo raw XML/file content trong HTTP/SOAP Fault.
6. Các test chạy bằng **artifact JAR/WAR/container cuối cùng** và đúng provider/classpath.
7. Xác minh phía SOAP client cũng không parse untrusted response theo cách khác.

Không bắt buộc mọi lỗi XML sớm phải trở thành `SoapFaultClientException` đẹp: nếu parser chặn trước dispatch, có thể là HTTP error hoặc SOAP Fault tùy transport/message factory. Quan trọng là **từ chối an toàn**, không có side effects và không rò dữ liệu.

### 11.5. Spring-WS interceptor không phải điểm chặn đầu tiên

`PayloadValidatingInterceptor`, `ClientInterceptor`, WS-Security interceptors và custom `EndpointInterceptor` thường hoạt động **sau một phần việc tạo SOAP message**. Không đặt toàn bộ niềm tin XXE defense vào interceptor nếu parser đã chạy trước đó.

Ngược lại, nếu muốn harden **outgoing** SOAP client, cần kiểm tra response parsing ở `WebServiceTemplate`, JAXB unmarshal và HTTP message sender. Bảo vệ XML trước input parse không tự giải quyết TLS certificate/hostname checking; đó là trách nhiệm khác.

## 12. Xác minh bằng test: từ unit test đến kết nối thật

### 12.1. Test DOM: input tốt được chấp nhận

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.io.StringReader;
import org.junit.jupiter.api.Test;
import org.xml.sax.InputSource;

class SecureDomFactoryTest {

    @Test
    void parsesSimpleDocument() throws Exception {
        String xml =
                "<request xmlns='urn:example:orders:v1'>OK</request>";

        var builder =
                SecureDomFactory.create().newDocumentBuilder();

        var doc = builder.parse(
                new InputSource(new StringReader(xml)));

        assertEquals("request",
                doc.getDocumentElement().getLocalName());
        assertEquals("urn:example:orders:v1",
                doc.getDocumentElement().getNamespaceURI());
    }
}
~~~

Đây là phép thử dương tính để bảo đảm security policy không làm hỏng XML hợp lệ trong phạm vi parser này; nó **chưa** chứng minh DOCTYPE bị từ chối.

### 12.2. Test DOM: DOCTYPE nhỏ phải bị từ chối

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.io.StringReader;
import org.junit.jupiter.api.Test;
import org.xml.sax.InputSource;
import org.xml.sax.SAXException;

class DomDoctypeRejectionTest {

    @Test
    void rejectsEvenSmallInternalDoctype() throws Exception {
        String xml = """
            <!DOCTYPE request [
              <!ENTITY synthetic "TEST_VALUE">
            ]>
            <request>&synthetic;</request>
            """;

        var builder =
                SecureDomFactory.create().newDocumentBuilder();

        assertThrows(SAXException.class,
                () -> builder.parse(
                    new InputSource(new StringReader(xml))));
    }
}
~~~

Vì chính sách đã chọn **cấm DOCTYPE hoàn toàn**, nội dung entity ở đây không cần đọc file thật hoặc tạo expansion cực lớn. Nếu test fail do provider từ chối security flags ngay từ factory, đó cũng là thông tin quan trọng: ứng dụng phải fail closed, nhưng cần sửa provider/config trước khi đưa vào production.

### 12.3. Test external entity không được mở HTTP connection

Một fixture nhỏ để kiểm tra **không có egress** trong test sandbox:

~~~xml
<?xml version="1.0"?>
<!DOCTYPE request [
  <!ENTITY synthetic SYSTEM
      "http://127.0.0.1:18081/xml-sentinel">
]>
<request>&synthetic;</request>
~~~

Trong integration test do đội phát triển sở hữu, dựng một HTTP listener cục bộ chỉ ghi số lượt truy cập. Sau đó:

1. Tạo parser theo **đúng factory/provider đang dùng**.
2. Parse XML trên (hoặc gửi SOAP chứa DOCTYPE tới test server).
3. Assert việc xử lý bị từ chối theo policy.
4. Assert **số request tới listener bằng 0**.
5. Assert không có nội dung listener trong output, log, Fault.
6. Chạy lại trên JDK/container và SOAP message factory production-like.

**Không cần** thử URLs tới metadata service thật hoặc file bí mật thật. Địa chỉ `127.0.0.1` ở đây chỉ trỏ đến **listener của bài test được cô lập**.

### 12.4. Test các đường khác

| Đường XML | Positive test | Negative test cần có |
|---|---|---|
| DOM | XML không DTD được parse | DOCTYPE, external entity bị chặn |
| SAX | XML namespace-aware được đọc | DOCTYPE/parameter entity bị chặn |
| StAX | XML stream hợp lệ được duyệt | DTD event hoặc parser error; không external fetch |
| SchemaFactory | Import/include **được duyệt** compile | External schema lạ không được tải |
| Validator | Payload đúng XSD thành công | Sai type/order/QName, external hint không có tác dụng |
| TransformerFactory | Trusted XSLT chạy | `document()`/external stylesheet bị từ chối |
| JAXB/OXM | JAXB root đúng contract | `StreamSource`/`SAXSource` không đưa parser yếu vào đường xử lý |
| Spring-WS SOAP inbound | Request hợp lệ tới endpoint | XML có DTD từ chối trước business; no egress |
| Spring-WS SOAP outbound | JAXB response an toàn | Response XML bên đối tác không gây external resolution ở client |
| SOAP security | Signed request hợp lệ được verify | Tampered body/header bị từ chối |
| HTTP/MTOM | SOAP/attachment trong quota | Quá kích thước/depth/time bị chặn |

Một unit test mock SOAP message **không đủ** nếu nó không dùng HTTP parser/message factory thực. Ngược lại, một integration test HTTP thành công không chứng minh XSLT compiler riêng an toàn nếu XSLT chưa được exercise.

### 12.5. Test “setter accepted” và “behavior denied” là hai assertions khác nhau

Nên phân biệt hai cổng kiểm thử:

**Configuration gate**

~~~text
Security feature/property mandatory?
  ├─ set/get/provider contract hỗ trợ → tiếp tục behavior test
  └─ Unsupported/unknown → FAIL startup/test
~~~

**Behavior gate**

~~~text
Untrusted XML thực đi qua đúng code path?
  ├─ DTD/external resource bị chặn, listener 0 request → PASS
  └─ Truy cập ngoài, parse thành công trái policy, bypass → FAIL
~~~

`getFeature`/`getProperty` có thể hữu ích cho introspection nếu provider hỗ trợ, nhưng **giá trị đọc ngược không thay thế behavior test**. Có implementation chấp nhận một thuộc tính nhưng đường gọi thực dùng instance khác.

## 13. Java XML processing limits: chống resource exhaustion

Chặn XXE chưa bảo vệ khỏi XML payload hợp lệ nhưng rất lớn, deep nesting, số attributes cực cao hoặc attachment khiến heap/temp disk cạn. Trong JDK có một số **JAXP processing limits** dạng properties/system properties, ví dụ:

~~~text
jdk.xml.entityExpansionLimit
jdk.xml.totalEntitySizeLimit
jdk.xml.maxGeneralEntitySizeLimit
jdk.xml.maxElementDepth
jdk.xml.elementAttributeLimit
jdk.xml.maxOccurLimit
~~~

**Không coi tất cả properties này là universal API**: chúng là cấu hình tùy JDK/provider, tên và cách áp dụng có thể khác với XML parser bên ngoài JDK. Cần đọc tài liệu của đúng JDK và kiểm tra bằng tests trên runtime thực.

### 13.1. Bảng quy tắc giới hạn

| Tài nguyên | Giới hạn ở đâu? |
|---|---|
| Raw HTTP request bytes | Reverse proxy, servlet container, HTTP message sender |
| SOAP Envelope/XML bytes | SOAP message factory và application-specific parser |
| XML depth, element count, attributes | Parser limits + validation/business limits |
| Entity expansion và total entity size | JAXP provider limits, **cấm DTD khi có thể** |
| XSD regexp/complexity | Trusted schema review, validator policy, timeouts |
| JAXB object graph size | Payload contract, request quotas, memory |
| MTOM/MIME attachment count/bytes | Multipart parser/transport/attachment layer |
| XSLT processing time/output size | Trusted stylesheets, time/resource budget |
| Concurrent SOAP requests | Gateway rate limit, servlet threads, application admission |
| Temporary file space | Container disk quotas và cleanup policy |

### 13.2. Giới hạn phải được kiểm chứng tại điểm nạp dữ liệu

Nếu reverse proxy cho tối đa 10 MiB, nhưng SOAP server vẫn có đường nội bộ không qua proxy nhận 100 MiB, policy tổng thể chưa hoàn chỉnh. Nếu MTOM binary 200 MiB có raw XML chỉ vài KB, quota “XML text bytes” không chặn binary.

Vì vậy phải test **đầu vào thật**, cả SOAP Body inline Base64 và MIME attachment, đồng thời đo heap/disk/CPU ở mức concurrency phù hợp. Không chạy một “Billion Laughs” cỡ lớn trên shared test/prod environment; dùng payload nhỏ có kiểm soát và parser limits để chứng minh enforcement.

## 14. Kiểm chứng trên artifact triển khai, không chỉ trong IDE

Một thay đổi Maven/Gradle dependencies, Spring Boot upgrade, JDK image hoặc application server có thể khiến runtime chọn **provider khác**. Unit test trên laptop có thể pass trong khi executable JAR/container lại thực thi parser khác với security defaults khác.

### 14.1. Lập inventory implementation và security policy

| Thành phần | Dữ liệu cần giữ trong báo cáo build/test | Lý do |
|---|---|---|
| JVM | Version, vendor, image digest, JAXP properties | Defaults/limits có thể khác |
| Spring-WS | Version và `WebServiceMessageFactory` thực | Đường parser SOAP |
| SAAJ/SOAP provider | Class/version/class loader | SOAP Envelope parsing |
| DOM/SAX/StAX | Provider class, property support, negative tests | DTD/external entity policy |
| TransformerFactory | Provider, access restrictions, URIResolver | XSLT/document() và imports |
| SchemaFactory | Provider, resolver, external schema policy | XSD imports và validation |
| JAXB runtime | Version, `Source` types, parser path | Unmarshal có thể tạo parser riêng |
| WSS4J | Version, signature/reference policy | Integrity, wrapping, header verification |
| HTTP/MTOM | Sender/parser, input/attachment quotas | Resource exhaustion |
| Contract assets | XSD/WSDL/XSLT/catalog version và base URIs | Offline, reproducible resolution |

Lưu class names/versions ở **startup diagnostics hoặc CI artifacts** có kiểm soát; không log nội dung SOAP, secrets hoặc toàn bộ Java system properties vì chúng có thể chứa credentials.

### 14.2. Một SOAP service có thể dùng nhiều parser

~~~text
Custom XML utility
  └── DocumentBuilderFactory provider A

SOAP message factory
  └── SAAJ provider B
       └── XML parser/stream reader C

JAXB/OXM unmarshal
  └── JAXB provider D
       └── XML input provider E

XSD validation
  └── SchemaFactory provider F

XSLT transformation
  └── TransformerFactory provider G
~~~

Ngay cả nếu A và C đều dựa trên JAXP, chúng không nhất thiết là cùng instance, được tạo bởi cùng factory hoặc dùng cùng flags.

### 14.3. Các môi trường cần chạy lại test

- Executable Spring Boot JAR và nested JAR dependency loading.
- WAR trong application server có XML/SAAJ provider do server cung cấp.
- Container dùng JRE/JDK khác máy build.
- CI test classpath khác runtime classpath.
- Custom class loader, module path hoặc native-image (nếu có hỗ trợ).
- Provider mới do plugin, SOAP client hoặc dependency transitively đưa vào.
- JDK security properties, XML processing limits hoặc schema resolver thay đổi.

Nếu production dùng provider khác, không giải quyết bằng cách chỉ cưỡng bức một global system property không được review. Xác định component nào tạo parser nào và chọn cơ chế cấu hình có phạm vi thích hợp.

### 14.4. Regression gates sau khi nâng phiên bản

Khi đổi JDK/Spring Boot/Spring-WS/JAXB/SAAJ/WSS4J/HTTP stack hoặc schema assets, chạy lại:

1. Provider inventory và **fail-on-unsupported-security-setting** tests.
2. DOM/SAX/StAX DOCTYPE rejection.
3. External entity/file/HTTP sentinel tests với **0 outbound access**.
4. XSD import/include **nội bộ** compile thành công; external location bị chặn.
5. XSLT trusted transform pass; external `document()`/stylesheet bị chặn.
6. SOAP request hợp lệ qua HTTP đến đúng endpoint và JAXB unmarshal được.
7. SOAP malicious request không chạy business layer, không leak dữ liệu.
8. WS-Security signed/unsigned/tampered cases và attachment/MTOM limits.
9. So sánh kết quả **trong artifact/container cuối cùng** với baseline đã phê duyệt.

Không nên chỉ so provider class name bằng string rồi coi như đủ. Implementation cùng tên vẫn có thể thay behavior qua version/security patches.

## 15. Kết hợp bảo mật XML với SOAP contract-first và WS-Security

### 15.1. XSD/WSDL nội bộ phải resolve được mà không phụ thuộc Internet

Bộ schema ứng dụng có thể có:

~~~text
xsd/orders/orders.xsd
  ├── xs:include → order-types.xsd
  └── xs:import  → ../common/common.xsd
                        └── xs:include → common-types.xsd
~~~

Nếu `SchemaFactory` bị cấm external schema access nhưng các file nội bộ vẫn cần nạp, hãy cung cấp resolver/catalog **mapping các system IDs đã phê duyệt** sang resources trong classpath. Đảm bảo base URI của `Source` đầy đủ, tránh path traversal.

Không bật `ACCESS_EXTERNAL_SCHEMA="all"` để “sửa lỗi import”. Cần kiểm thử cả hai chiều: **dependency tin cậy phải hoạt động** và **reference chưa duyệt không thể nạp**.

Phân biệt hai việc:

- Phía **server parse SOAP request**: không tin `xsi:schemaLocation` hoặc external DTD do client cung cấp.
- Phía **client tải WSDL từ partner được duyệt**: HTTPS và XML resource policy riêng, có thể tải tài nguyên đã cho phép theo danh sách endpoints, certificates và trust anchors.

### 15.2. WS-Security không thay parser hardening

WSS4J/WS-Security có thể xác minh SOAP Signature, token, timestamp và encryption, nhưng nếu parser truy cập external entities **trước khi verify signature**, rủi ro XXE có thể đã xảy ra.

Ngược lại, XML parser đã tắt DTD không bảo vệ trước **XML Signature Wrapping**. Cần bảo đảm business handler sử dụng đúng các phần tử được chữ ký bảo vệ theo signed references/security policy, không phải một element cùng tên khác.

- XSD validation không phải authentication.
- SOAP `@PayloadRoot` khớp QName không chứng minh caller có quyền.
- TLS certificate/hostname checking không thay WS-Security message signature.
- Một Header `wsse:Security` tồn tại không tự có nghĩa signature đã được kiểm chứng.
- Không mutate signed DOM nodes giữa verify và business usage.
- Không log decrypted SOAP payload, token, private key, raw signature hay attachments.

### 15.3. Lỗi phải được xử lý đúng tầng, không làm rò thông tin

| Vị trí lỗi | Hành vi mong muốn |
|---|---|
| Parser từ chối DOCTYPE/external entity | Không truy cập resource; HTTP/SOAP error có kiểm soát |
| XSD không compile tại startup | **Fail startup**, không phục vụ như đã validate |
| Payload sai XSD | Fault theo contract, không dump raw XML |
| SOAP version/Envelope sai | Protocol rejection trước business |
| WS-Security signature sai | Từ chối message, không gọi endpoint |
| XSLT external URI bị chặn | Không fallback sang transformer không hạn chế |
| MIME/MTOM vượt limits | Chặn, dọn temp files, không OOM |
| Provider không hỗ trợ hardening bắt buộc | **Fail closed**, sửa config/provider |

Một số lỗi xảy ra **trước** `EndpointExceptionResolver` và `EndpointInterceptor`. Không mặc định chúng đều chuyển thành SOAP Fault có detail hoàn chỉnh. Quan trọng là không có side effects, network egress hay lộ dữ liệu khi input không hợp lệ.

### 15.4. Observability an toàn

Ghi metadata có kiểm soát:

~~~text
service=orders
stage=xml_parse
failure_class=DOCTYPE_REJECTED
provider_id=approved-jaxp-runtime
result=denied
~~~

Không đưa raw XML, external URI do caller cung cấp, certificate secrets, file paths nhạy cảm hoặc exception message chứa input vào log/metrics labels. Có thể lưu stack trace nội bộ để điều tra trong môi trường được bảo vệ, áp dụng redaction và retention policy.

## 16. Case study: DOM test pass nhưng SOAP server vẫn gọi URL ngoài

### 16.1. Triệu chứng

Một nhóm phát triển có helper `SecureDomFactory` chặn DOCTYPE, unit test trên helper thành công. Tuy nhiên, một integration test HTTP trong môi trường sandbox gửi SOAP chứa external entity trỏ tới **test listener**; listener ghi nhận HTTP request được mở từ ứng dụng.

Vậy bằng chứng nào đang mâu thuẫn?

- Unit test chỉ chứng minh behavior của **factory được gọi trong unit test**.
- SOAP integration test chứng minh **ít nhất một thành phần trên đường request thực** đã cho phép external resolution.
- Chưa thể kết luận thành phần gây lỗi là SAAJ, JAXB, interceptor, XSLT hay SchemaFactory chỉ từ hai kết quả trên.

### 16.2. Các nguyên nhân có thể

1. SOAP message factory sử dụng parser khác, không dùng `SecureDomFactory`.
2. SOAP Header logger/interceptor tự parse raw XML bằng default DOM/SAX provider.
3. JAXB runtime nhận `StreamSource` rồi tạo parser riêng không được harden.
4. XSD validator có resource resolver tải URL từ schema hoặc instance hint.
5. XSLT transformation dùng `document()` tới external URI.
6. Một custom entity/URI resolver bỏ qua security policy.
7. Classpath/container đã thay StAX/SAAJ/JAXP provider so với test runner.
8. Một parser được cấu hình **sau** khi instance đã được tạo và bắt đầu parse.

### 16.3. Quy trình xử lý có căn cứ

~~~mermaid
flowchart TD
    A["HTTP SOAP request có sentinel reference"] --> B{"Test listener thấy outbound call?"}
    B -->|Không| C["Xác minh parser reject + endpoint không chạy"]
    B -->|Có| D["Inventory SOAP factory/JAXB/JAXP providers"]
    D --> E["Khoanh vùng component phát sinh external resolution"]
    E --> F["Cấu hình/chọn đúng provider và resolver"]
    F --> G["Fail closed khi security setting unsupported"]
    G --> H["Chạy lại test trong packaged artifact"]
    H --> I["Regression: SOAP hợp lệ, XSD, WSS, MTOM"]
~~~

Trên môi trường test, cô lập dần các thành phần để xác định **ai mở outbound connection**. Không vô hiệu hóa toàn bộ WS-Security hoặc XSD validation ở production chỉ để tìm cho nhanh. Khi đã sửa, phải thử thêm XML hợp lệ và XSD imports tin cậy để tránh “fix XXE” bằng cách làm hỏng SOAP contract.

### 16.4. Tiêu chí đóng sự cố

| Tiêu chí | Bằng chứng |
|---|---|
| XML DOCTYPE bị từ chối | Parser/HTTP integration test |
| Không có SSRF/external resolution | Test listener nhận 0 request |
| Provider thực được xác định | Runtime inventory và dependency versions |
| XML hợp lệ vẫn xử lý | SOAP endpoint/JAXB/XSD positive test |
| XSD import/include nội bộ không bị phá | Offline schema compilation test |
| Signed SOAP message được verify | WS-Security valid/tampered tests |
| Fault/log không lộ secrets/URLs | Synthetic-secret test |
| Test chạy trên artifact triển khai | CI job dùng đúng JDK/container image |

**Bài học:** “đã harden một parser” không đồng nghĩa “đã harden cả ứng dụng”. Bảo vệ XML là thuộc tính **end-to-end** của đường dữ liệu thực.

## 17. Bài tập thực hành kèm đáp án

### Bài 1 — Chỉ bật FEATURE_SECURE_PROCESSING

Một developer chỉ bật `FEATURE_SECURE_PROCESSING=true` rồi tuyên bố DOM, StAX, XSLT và SOAP đều không thể bị XXE. Có đúng không?

**Đáp án:** Không. Mỗi provider/factory có chính sách riêng; phải chặn DTD/external resources, kiểm tra support thực và chạy negative tests trên đúng đường xử lý. FSP không thay tất cả các giới hạn/thuộc tính riêng.

### Bài 2 — Security setter không được hỗ trợ

`DocumentBuilderFactory` ném `ParserConfigurationException` khi đặt `disallow-doctype-decl`. Có được catch/ignore để tiếp tục nhận SOAP không?

**Đáp án:** Không nếu cấm DTD là yêu cầu bắt buộc. Cần fail closed, thay provider/config hoặc cung cấp lớp bảo vệ tương đương đã được kiểm chứng, rồi test DOCTYPE thực bị từ chối.

### Bài 3 — Response không chứa nội dung entity

Khi gửi XML có external entity, response không chứa nội dung sentinel. Có chứng minh server không đọc external resource không?

**Đáp án:** Chưa. Phải chứng minh **không có outbound connection/đọc file**, ví dụ test listener không có requests, parser/handler bị từ chối trước business. Việc dữ liệu không xuất hiện ở response không đủ.

### Bài 4 — XSD nội bộ không nạp được

Sau khi đặt `ACCESS_EXTERNAL_SCHEMA=""`, `orders.xsd` không resolve được `../common/common.xsd`. Có nên bật `http,file` cho mọi URI không?

**Đáp án:** Không. Thiết kế XML Catalog/`LSResourceResolver` whitelist, giữ base URI/systemId và chỉ nạp tài nguyên schema đã được duyệt. Chạy cả positive local import test và negative remote reference test.

### Bài 5 — JAXB và StAX

Một `Jaxb2Marshaller` nhận `StAXSource`, nhưng bạn chỉ harden `DocumentBuilderFactory`. Vì sao chưa đủ?

**Đáp án:** `StAXSource` mang reader do `XMLInputFactory`/provider khác tạo. Phải kiểm tra `SUPPORT_DTD`, external entity policy, actual reader, và behavior trên đường client/endpoint thật.

### Bài 6 — XSLT document()

XML parser đầu vào đã cấm DOCTYPE; stylesheet được lấy từ client có thể dùng `document()` tới URL ngoài. Service đã an toàn chưa?

**Đáp án:** Chưa. `TransformerFactory`/URIResolver phải giới hạn external document/stylesheet và chỉ dùng trusted stylesheet; parser DOM an toàn không tự chặn hoạt động XSLT.

### Bài 7 — SOAP parser lỗi trước endpoint

Integration test gửi SOAP với DOCTYPE, nhận HTTP error thay vì SOAP Fault do `EndpointExceptionResolver` tạo. Có nhất thiết là thất bại bảo mật không?

**Đáp án:** Không. Parser có thể chặn trước dispatch. Kiểm tra denial an toàn, no egress, no side effect và không leak; yêu cầu SOAP Fault cụ thể phải xét theo binding/contract riêng.

### Bài 8 — JAXB tạo DTO thành công

Một SOAP request được unmarshaled thành `GetOrderRequest` object. Có thể kết luận XSD facets và WS-Security signature đã hợp lệ?

**Đáp án:** Không. JAXB, XSD validation, WS-Security và business authorization là những kiểm soát riêng biệt. Cần cấu hình và test từng lớp.

### Bài 9 — Provider thay đổi sau nâng JDK

CI dùng JDK build cũ, production container dùng JRE mới và một StAX provider mới. Vì sao phải chạy lại bảo mật XML?

**Đáp án:** Service loading, defaults, supported features/properties và parser behavior có thể khác. Phải xác nhận provider thực và chạy lại positive/negative tests trên packaged runtime.

### Bài 10 — MTOM attachment rất lớn

SOAP XML Body chỉ 5 KiB, nhưng attachment MTOM là 500 MiB. XML parser đã chặn DTD và giới hạn depth, vậy đủ chưa?

**Đáp án:** Chưa. Cần MIME/attachment count, decoded bytes, streaming/spooling, temporary disk, timeout, concurrency và cleanup limits. XML parser flags không kiểm soát mọi binary attachments.

### Bài 11 — XML Signature Wrapping

SOAP Body có hai elements cùng tên và một element được ký; business code đọc element khác theo XPath quá rộng. DTD đã bị tắt. Rủi ro còn không?

**Đáp án:** Có. Đây là nguy cơ sử dụng node **khác signed/reference-verified node**. Cần WS-Security library và policy ràng buộc việc verify với đúng phần dữ liệu business sử dụng; DTD policy không xử lý signature wrapping.

### Bài 12 — Logging exception

Parser từ chối external DTD chứa URL do attacker cung cấp. Logger đưa nguyên exception và XML vào metrics label. Rủi ro?

**Đáp án:** Có thể lộ thông tin, log injection, cardinality explosion và lưu dữ liệu attacker-controlled lâu dài. Chỉ xuất error category/operation code được allowlist, dùng redaction và retention theo chính sách.

## 18. Checklist xác minh security trên đúng implementation

### 18.1. Inventory và ownership

- [ ] Đã xác định Java runtime/vendor/version và container artifact cuối cùng.
- [ ] Đã xác định Spring-WS version, `WebServiceMessageFactory` và SAAJ provider thực.
- [ ] Đã kiểm kê DOM/SAX/StAX/`TransformerFactory`/`SchemaFactory` providers.
- [ ] Đã xác định JAXB source path và parser mà unmarshaller thực sự dùng.
- [ ] Biết XML security controls được áp dụng ở **tầng nào, instance nào, trước hay sau parse**.
- [ ] Factory/provider class và required property support có thể kiểm tra tại startup/test.
- [ ] Mỗi mandatory security setting không hỗ trợ đều **fail closed**.
- [ ] Không có fallback vô hạn chế hoặc code catch-and-ignore lỗi hardening.
- [ ] Factory/Validator mutable không bị dùng chung sai giữa nhiều request threads.

### 18.2. XML parser và resource access

- [ ] DOM parser cấm DOCTYPE theo policy.
- [ ] SAX/XMLReader cấm external general/parameter entities và external DTD.
- [ ] StAX `XMLInputFactory` cấm DTD/external entities theo policy, behavior đã test.
- [ ] XInclude bị vô hiệu hóa nếu không có yêu cầu rõ ràng.
- [ ] `TransformerFactory` hạn chế external DTD/XSLT stylesheet/document.
- [ ] `SchemaFactory`/`Validator` không tải external schema chưa phê duyệt.
- [ ] XSD import/include và XSLT nội bộ chỉ resolve qua resources/catalog whitelist.
- [ ] Không dựa vào `xsi:schemaLocation` từ SOAP caller làm hợp đồng server.
- [ ] Không chỉ kiểm tra getter của feature; có **behavior tests** chứng minh nó hoạt động.
- [ ] Có network/file sentinel tests và xác nhận **0 external resource access**.
- [ ] Có positive tests XML/XSD/XSLT hợp lệ để tránh cấu hình làm hỏng service.

### 18.3. SOAP, JAXB, security và limits

- [ ] HTTP SOAP integration test sử dụng đúng message factory của ứng dụng.
- [ ] Đầu vào bị chặn không tới `@Endpoint`/business service.
- [ ] Namespace/QName của SOAP Body/Header được parser xử lý đúng.
- [ ] XSD validation được bật rõ ràng, không suy từ JAXB model tồn tại.
- [ ] WS-Security signing/encryption/verification và certificate trust được test riêng.
- [ ] Chống signed-node confusion/XML Signature Wrapping theo policy thực.
- [ ] SOAP Fault/log không chứa raw XML, token, file content, private key hoặc PII.
- [ ] Có HTTP body limits, XML depth/entity/attribute limits và concurrency/timeouts.
- [ ] MTOM/XOP/MIME count, decoded bytes, disk usage và streams được kiểm soát.
- [ ] Không log toàn SOAP message trong interceptor chỉ để debug.
- [ ] Runtime không được tự mở URL ngoài do input XML hoặc resolver chưa duyệt cung cấp.

### 18.4. CI, triển khai và tương thích

- [ ] Tests chạy lại sau JDK/Spring-WS/SAAJ/JAXB/WSS4J/provider upgrades.
- [ ] Tests chạy trên executable JAR/WAR/container image được deploy.
- [ ] Có bài test **offline**: trusted XSD/WSDL dependencies vẫn resolve.
- [ ] Có bài test **negative egress** cho DOCTYPE, external entity, XSLT và schema.
- [ ] Có regression test SOAP document/literal, SOAP Fault và JAXB round trip.
- [ ] Có test MTOM và client tương thích độc lập khi contract yêu cầu.
- [ ] Có policy review khi thay external access properties, XML catalogs hoặc resource resolvers.
- [ ] Kết quả test được lưu với provider/version/environment fingerprint rõ.
- [ ] Có monitoring/alerting cho parser rejection và quota violations mà không thu raw payload.
- [ ] Đã phân biệt hoàn thành kỹ thuật với audit/QA security và test production readiness.

### 18.5. Bảng quyết định cuối bài

| Khi muốn kiểm chứng… | Cần nhìn vào |
|---|---|
| XML string được parse thành DOM | `DocumentBuilderFactory` và input parse thực |
| XML sự kiện SAX | `SAXParserFactory`, `XMLReader` và resolver |
| XML streaming | `XMLInputFactory`, `XMLStreamReader`, actual provider |
| XSLT | `TransformerFactory`, `URIResolver`, external access properties |
| XSD imports/validation | `SchemaFactory`, `Validator`, `LSResourceResolver` |
| JAXB object | Nguồn `Source`, parser trước JAXB, XSD validation |
| SOAP inbound | `WebServiceMessageFactory`, SAAJ provider, servlet integration |
| SOAP WS-Security | WSS4J/security policy và exact signed elements |
| HTTPS/certificates | TLS message sender, truststore và hostname verification |
| XXE/SSRF đã thực sự bị chặn | End-to-end test với sentinel và **không có outbound access** |
| Upgrade an toàn | Test lại trên **packaged production-like runtime** |

**Ghi nhớ:** cấu hình bảo vệ XML chỉ có ý nghĩa khi **đúng implementation đang sử dụng thực sự thực thi cấu hình đó trên đường dữ liệu cần bảo vệ**. Trong Spring Web Services, hãy kiểm kê provider thực, dùng fail-closed security properties, kiểm thử DOCTYPE/external entities/external schema/XSLT bằng fixtures có kiểm soát, và xác nhận request SOAP end-to-end không mở tài nguyên trái phép. Đồng thời giữ XSD/WSDL/JAXB hoạt động với resources được duyệt, kiểm tra WS-Security và giới hạn tài nguyên, rồi chạy lại các bài kiểm thử mỗi khi JDK, message factory hoặc dependencies thay đổi.
