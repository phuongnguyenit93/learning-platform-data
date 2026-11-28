# Biến đổi bằng Transformer và quản lý vòng đời thành phần không an toàn luồng

## 1. Bối cảnh trong Spring Web Services

Trong **Spring Web Services (Spring-WS)**, phát triển SOAP theo hướng **contract-first** thường đi từ **XSD/WSDL** đến ánh xạ **JAXB**, endpoint và SOAP client. Tuy nhiên, không phải mọi tích hợp đều có thể chuyển XML trực tiếp thành DTO Java theo một schema duy nhất. Một hệ thống doanh nghiệp có thể cần:

- Chuyển payload XML của đối tác cũ sang cấu trúc XML mà hệ thống hiện tại hiểu.
- Chuẩn hóa namespace, tên phần tử hoặc định dạng của một số trường theo hợp đồng.
- Lọc và định dạng một phần XML trước khi gọi SOAP service khác.
- Biến đổi dữ liệu qua **XSLT** mà không viết hàng trăm thao tác DOM thủ công.
- Đọc và ghi trực tiếp **`Source`/`Result`** trong Spring-WS khi không muốn dùng JAXB cho một công đoạn đặc thù.

Java cung cấp API **JAXP TrAX** (`javax.xml.transform`) gồm `TransformerFactory`, `Templates`, `Transformer`, `Source` và `Result`. Chúng giải quyết bài toán chuyển đổi XML, nhưng có một ràng buộc quan trọng: **nhiều đối tượng xử lý XML mang trạng thái có thể thay đổi và không được dùng đồng thời giữa các request**.

Ví dụ, một `Transformer` có thể chứa tham số XSLT, `URIResolver`, `ErrorListener` và output properties. Nếu đặt một `Transformer` làm singleton Spring bean rồi gọi `transform(...)` trên nhiều luồng HTTP, ứng dụng có thể nhận kết quả trộn tham số hoặc hành vi khó tái hiện. Cách thiết kế bền vững là **tái sử dụng bản XSLT đã biên dịch (`Templates`), tạo `Transformer` mới cho mỗi lần biến đổi**.

Mục tiêu của bài:

1. Phân biệt biến đổi **identity** và biến đổi theo **XSLT**.
2. Hiểu vòng đời và mức độ an toàn luồng của `TransformerFactory`, `Templates`, `Transformer` và các parser liên quan.
3. Tích hợp biến đổi XML với Spring-WS mà không nhầm SOAP Envelope với payload.
4. Bảo vệ XML parser/transformer trước **XXE**, tải tài nguyên ngoài và stylesheet không tin cậy.
5. Thiết kế kiểm thử xác thực XML, concurrency và lỗi SOAP để tích hợp doanh nghiệp ổn định.

## 2. Mô hình cơ bản: `Source → Transformer → Result`

Mọi phép biến đổi TrAX có hình dạng khái quát:

~~~mermaid
flowchart LR
    A["Nguồn XML: Source"] --> B["Transformer"]
    X["XSLT stylesheet — có thể không có"] --> B
    B --> C["Đích XML: Result"]
    C --> D["DOM / Stream / SAX / SOAP payload"]
~~~

Một số kiểu dữ liệu thường gặp:

| API | Ý nghĩa | Ví dụ sử dụng |
| --- | --- | --- |
| `Source` | Giao diện mô tả nguồn đầu vào cho phép biến đổi | Đọc payload SOAP hoặc XML từ file/stream |
| `StreamSource` | Nguồn XML từ `InputStream`, `Reader` hoặc system ID | Nhận chuỗi hoặc stream XML |
| `DOMSource` | Nguồn từ cây DOM `Node` | Đọc cây XML đã parse |
| `SAXSource` | Nguồn từ luồng sự kiện SAX, có thể gắn `XMLReader` đã bảo vệ | Xử lý XML không cần tạo DOM đầy đủ |
| `Result` | Giao diện mô tả nơi ghi kết quả | Đích của `transform` |
| `StreamResult` | Ghi ra `OutputStream`/`Writer` | Gửi kết quả đến buffer hoặc file |
| `DOMResult` | Xây dựng cây DOM từ kết quả | Phân tích/validate kết quả trước xử lý |
| `SAXResult` | Gửi sự kiện XML tới SAX handler | Xử lý kiểu sự kiện |
| `Transformer` | Thực thi một phép biến đổi | `transform(source, result)` |
| `Templates` | Biểu diễn stylesheet đã biên dịch để tạo transformer | Dùng lại cấu hình XSLT giữa nhiều request |

**`Source` không có nghĩa dữ liệu XML đã hợp lệ theo XSD.** Nó chỉ là hình thức cung cấp nguồn để JAXP xử lý. Cũng không được giả định mọi `Source` có thể đọc nhiều lần: `StreamSource` dựa trên input stream thường bị tiêu thụ sau một lần đọc.

### 2.1. Hai loại phép biến đổi

**Identity transform** về mặt ý nghĩa sao chép XML đầu vào sang đích, không áp dụng stylesheet:

~~~java
Transformer transformer =
        transformerFactory.newTransformer();
transformer.transform(source, result);
~~~

Identity transform có thể thay đổi **cách serialize** như prefix, XML declaration hoặc khoảng trắng; không có cam kết sao chép byte-for-byte.

**XSLT transform** áp dụng quy tắc định nghĩa trong stylesheet:

~~~java
Templates templates =
        transformerFactory.newTemplates(stylesheetSource);
Transformer transformer = templates.newTransformer();
transformer.transform(source, result);
~~~

Trong một ứng dụng server có nhiều request, mã ở ví dụ thứ hai nên chia thành **bước chuẩn bị một lần** (`newTemplates`) và **bước xử lý lặp lại** (`newTransformer` rồi `transform`).

## 3. `TransformerFactory`, `Templates` và `Transformer` khác nhau thế nào?

### 3.1. `TransformerFactory`: thành phần tạo và biên dịch

`TransformerFactory` chọn implementation TrAX đang có trên classpath/runtime, cấu hình các thuộc tính xử lý rồi tạo:

- `Transformer` dùng cho identity transform thông qua `newTransformer()`.
- `Transformer` từ một stylesheet cụ thể qua `newTransformer(Source)`.
- `Templates` đã biên dịch qua `newTemplates(Source)`.

Factory có thể mang cấu hình như `URIResolver`, `ErrorListener`, tùy chọn bảo mật và thuộc tính do implementation cung cấp. **Không có quy tắc chung rằng một `TransformerFactory` có thể gọi đồng thời từ nhiều luồng.** An toàn nhất là tạo/cấu hình nó trong bước khởi tạo dịch vụ, biên dịch stylesheet, rồi không chia sẻ factory để thực thi biến đổi trên từng request.

### 3.2. `Templates`: bản stylesheet có thể tái sử dụng đồng thời

`javax.xml.transform.Templates` là biểu diễn đã xử lý/biên dịch của stylesheet. Theo hợp đồng JAXP, implementation của `Templates` được thiết kế để **an toàn luồng**: nhiều luồng có thể gọi `newTransformer()` trên **cùng một `Templates`** để nhận những phiên Transformer riêng.

Trong Spring, `Templates` là đối tượng thích hợp để giữ ở cấp singleton hoặc trong một service singleton:

~~~java
private final Templates templates;

public void transform(Source source, Result result)
        throws TransformerException {
    Transformer transformer = templates.newTransformer();
    transformer.transform(source, result);
}
~~~

Ở đây mỗi lần gọi `transform` nhận một `Transformer` mới. Các đối tượng `Source` và `Result` cũng phải thuộc **riêng từng lần gọi**; không lưu cùng `StreamSource` hoặc `DOMResult` trong field singleton để dùng chung.

### 3.3. `Transformer`: đối tượng xử lý có trạng thái

`Transformer` có các thao tác có thể thay đổi trạng thái:

~~~java
transformer.setParameter("currency", "VND");
transformer.setOutputProperty(OutputKeys.INDENT, "yes");
transformer.setURIResolver(resolver);
transformer.setErrorListener(errorListener);
~~~

JAXP **không bảo đảm `Transformer` an toàn để nhiều luồng sử dụng đồng thời**. Trong một số trường hợp, `reset()` có thể khôi phục một số thiết lập về trạng thái ban đầu, nhưng không biến nó thành công cụ synchronization; hành vi reset chi tiết của các thành phần gắn vào cũng phụ thuộc implementation. Đừng tạo singleton `Transformer` rồi gọi `reset()` giữa các request để cố làm nó an toàn luồng.

### 3.4. Bảng quyết định vòng đời

| Đối tượng | Cách dùng khuyến nghị | Lý do |
| --- | --- | --- |
| `TransformerFactory` | Tạo/cấu hình trong bước khởi tạo; không gọi đồng thời nếu provider không bảo đảm | Factory không có cam kết thread-safe phổ quát |
| `Templates` | Giữ trong singleton, chia sẻ qua nhiều request | Được thiết kế để thread-safe, tránh biên dịch XSLT lặp lại |
| `Transformer` | **Tạo mới mỗi phép biến đổi** | Trạng thái mutable và không thread-safe |
| `Source` dựa trên stream | Tạo riêng mỗi lần gọi | Stream có thể bị đọc hết sau một lần |
| `Result` / `ByteArrayOutputStream` / `DOMResult` | Tạo riêng mỗi lần gọi | Đích output chứa dữ liệu đang ghi |
| `URIResolver` / `ErrorListener` | Chọn implementation stateless hoặc request-scoped | Không mặc định callback tùy chỉnh thread-safe |
| Input XML DOM `Document` | Dùng riêng hoặc chỉ đọc theo kiểm soát rõ ràng | DOM có mutable state, dễ bị race khi sửa cây |

**Nguyên tắc cốt lõi:** cache **định nghĩa biến đổi**, không cache **phiên thực thi biến đổi**.

## 4. Ví dụ XSLT 1.0: chuyển request XML của đối tác cũ

Giả sử đối tác gửi payload:

~~~xml
<old:LegacyOrder xmlns:old="urn:example:legacy-orders:v1">
    <old:code>ORD-1001</old:code>
    <old:priority>HIGH</old:priority>
</old:LegacyOrder>
~~~

Trong khi tầng tích hợp mới yêu cầu:

~~~xml
<ord:SubmitOrderRequest xmlns:ord="urn:example:orders:v2">
    <ord:orderId>ORD-1001</ord:orderId>
    <ord:priority>HIGH</ord:priority>
</ord:SubmitOrderRequest>
~~~

Một stylesheet tại `src/main/resources/xslt/legacy-order.xsl`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet
    version="1.0"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:old="urn:example:legacy-orders:v1"
    xmlns:ord="urn:example:orders:v2"
    exclude-result-prefixes="old">

    <xsl:output method="xml"
                encoding="UTF-8"
                omit-xml-declaration="yes"/>

    <xsl:template match="/">
        <ord:SubmitOrderRequest>
            <ord:orderId>
                <xsl:value-of
                    select="/old:LegacyOrder/old:code"/>
            </ord:orderId>
            <ord:priority>
                <xsl:value-of
                    select="/old:LegacyOrder/old:priority"/>
            </ord:priority>
        </ord:SubmitOrderRequest>
    </xsl:template>
</xsl:stylesheet>
~~~

Trong XSLT này:

1. `xsl:stylesheet` định nghĩa tập quy tắc biến đổi; prefix `xsl` phải trỏ tới namespace `http://www.w3.org/1999/XSL/Transform`.
2. `match="/"` chọn root của cây tài liệu đầu vào.
3. Các biểu thức XPath `/old:LegacyOrder/old:code` và `.../old:priority` **so khớp theo namespace URI**, không theo cách viết prefix của XML nguồn.
4. Phần tử `ord:SubmitOrderRequest` và các phần tử con thuộc namespace mới.
5. `xsl:value-of` lấy nội dung text; dấu `<`, `&` trong dữ liệu được serializer XML xử lý theo ngữ cảnh output thông thường, không được tự nối chuỗi tạo XML không escape.

Đây là phép **thay đổi contract**, không đơn giản là đổi tên biến Java. Phải có XSD/WSDL phù hợp cho payload mới và kiểm thử cách chuyển dữ liệu: trường bắt buộc, giá trị enum, namespace, thứ tự và khả năng phát hiện thiếu `code` đều cần được xử lý.

### 4.1. Không biến một stylesheet minh họa thành validator

Nếu XML đầu vào thiếu `old:code`, `xsl:value-of` trong ví dụ có thể tạo `ord:orderId` rỗng. XSLT không tự hiểu rằng đơn hàng cần mã hợp lệ. Trong hệ thống thật:

- Xác thực đầu vào theo XSD cũ hoặc quy tắc nghiệp vụ.
- Biến đổi bằng stylesheet đã được quản lý.
- Xác thực kết quả theo **XSD đích**.
- Chỉ gọi nghiệp vụ hoặc SOAP client tiếp theo khi dữ liệu đã hợp lệ.

Nếu cần chọn giá trị mặc định, chuẩn hóa enum hoặc xử lý trường tùy chọn, hãy mô tả rõ quy tắc trong tài liệu hợp đồng và test; không tự điền dữ liệu giả để vượt qua validation.

## 5. Cài đặt Java: biên dịch XSLT một lần, biến đổi mỗi request

Một service chuyên trách có thể giữ `Templates` immutable dưới dạng field:

~~~java
package example.orders.xml;

import java.io.IOException;
import java.io.InputStream;
import java.util.Objects;
import javax.xml.XMLConstants;
import javax.xml.transform.Result;
import javax.xml.transform.Source;
import javax.xml.transform.Templates;
import javax.xml.transform.Transformer;
import javax.xml.transform.TransformerConfigurationException;
import javax.xml.transform.TransformerException;
import javax.xml.transform.TransformerFactory;
import javax.xml.transform.stream.StreamSource;

public final class OrderXsltTransformer {
    private final Templates templates;

    public OrderXsltTransformer()
            throws IOException, TransformerConfigurationException {

        TransformerFactory factory =
                TransformerFactory.newInstance();
        factory.setFeature(
                XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setAttribute(
                XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(
                XMLConstants.ACCESS_EXTERNAL_STYLESHEET, "");

        try (InputStream xsl = Objects.requireNonNull(
                getClass().getResourceAsStream(
                        "/xslt/legacy-order.xsl"),
                "Missing XSLT resource")) {
            templates = factory.newTemplates(new StreamSource(xsl));
        }
    }

    public void transform(Source source, Result result)
            throws TransformerException {
        Transformer transformer = templates.newTransformer();
        transformer.transform(source, result);
    }
}
~~~

**Giả định của ví dụ:** stylesheet đã được đóng gói nội bộ trên classpath, **không dùng `xsl:include` hoặc `xsl:import`**, và implementation JAXP hỗ trợ các thuộc tính bảo mật chuẩn được sử dụng. Nếu implementation không hỗ trợ một cấu hình quan trọng, hãy coi đó là **lỗi cấu hình cần xử lý**, không lặng lẽ bỏ qua rồi chạy không hạn chế.

Các điểm đáng chú ý:

- Constructor có thể chạy **một lần** khi Spring tạo singleton service.
- `Templates` được tạo từ **stylesheet tin cậy** và lưu trong field `final`.
- Mỗi lần gọi `transform(...)` tạo một `Transformer` độc lập, không trộn tham số hoặc output state giữa các HTTP request.
- `InputStream` của stylesheet được đóng sau khi `newTemplates(...)` hoàn tất; đối tượng `Templates` không phụ thuộc vào việc giữ nguyên stream này.
- `Source`/`Result` do **caller tạo cho từng request**; class không lưu input/output dùng chung.

Ví dụ đăng ký trong Spring:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class XmlTransformConfig {
    @Bean
    public OrderXsltTransformer orderXsltTransformer()
            throws Exception {
        return new OrderXsltTransformer();
    }
}
~~~

Nếu stylesheet không tồn tại hoặc không biên dịch được, ứng dụng **khởi động lỗi** thay vì phục vụ request bằng một transformer thiếu cấu hình. Với hợp đồng tích hợp doanh nghiệp, cơ chế fail-fast này thường an toàn hơn phát hiện lỗi biến đổi ở một request đầu tiên sau khi triển khai.

### 5.1. Gọi service với input/output thuộc riêng request

~~~java
import java.io.StringReader;
import java.io.StringWriter;
import javax.xml.transform.stream.StreamResult;
import javax.xml.transform.stream.StreamSource;

String legacyXml =
        "<old:LegacyOrder " +
        "xmlns:old=\"urn:example:legacy-orders:v1\">" +
        "<old:code>ORD-1001</old:code>" +
        "<old:priority>HIGH</old:priority>" +
        "</old:LegacyOrder>";

StringWriter output = new StringWriter();

orderXsltTransformer.transform(
        new StreamSource(new StringReader(legacyXml)),
        new StreamResult(output));

String transformedXml = output.toString();
~~~

Đây là ví dụ với **XML tin cậy tạo trong chương trình** để minh họa sử dụng API; khi input có nguồn bên ngoài, cần thêm bước tạo `Source` an toàn như mục 9. `StringWriter` chứa text trong bộ nhớ, không phù hợp nếu payload rất lớn. Dù service là singleton, **`StringReader`, `StringWriter`, `StreamSource` và `StreamResult` là biến cục bộ**, không bị các request khác sử dụng đồng thời.

### 5.2. Tham số XSLT thuộc từng request

Nếu stylesheet sử dụng:

~~~xml
<xsl:param name="sourceSystem" select="'UNKNOWN'"/>
~~~

có thể truyền giá trị với `Transformer.setParameter(...)`. Khi có nhiều request:

~~~java
public void transformWithSystem(
        Source input, Result output, String sourceSystem)
        throws TransformerException {

    Transformer transformer = templates.newTransformer();
    transformer.setParameter("sourceSystem", sourceSystem);
    transformer.transform(input, output);
}
~~~

Mỗi transformer chỉ xử lý tham số của **một lần gọi**. Không lưu `sourceSystem` vào field singleton rồi cho stylesheet đọc từ state chung. Dùng `setParameter` cũng không có nghĩa mọi giá trị đầu vào đều hợp lệ theo XSD hoặc được phép truy cập nghiệp vụ; vẫn phải validate.

## 6. Vì sao không chia sẻ một `Transformer` giữa nhiều luồng?

Phương án dễ viết nhưng sai về vòng đời:

~~~java
@Component
public class UnsafeTransformerService {
    private final Transformer sharedTransformer;

    // Constructor tạo sharedTransformer từ stylesheet...

    public void process(Source input, Result output, String tenant)
            throws TransformerException {
        sharedTransformer.setParameter("tenant", tenant);
        sharedTransformer.transform(input, output);
    }
}
~~~

Giả sử hai request chạy đồng thời:

~~~text
Request A (tenant = A)     Request B (tenant = B)
  setParameter("A")
                           setParameter("B")
  transform(sourceA)
                           transform(sourceB)
~~~

Vì cùng một `Transformer` mang mutable state, request A có thể thấy tham số do B thiết lập hoặc gặp hành vi không được API bảo đảm. Sự cố có thể chỉ xuất hiện khi hệ thống tăng tải và khó tái hiện bằng test đơn luồng.

**Không nên tự “sửa” bằng `synchronized` nếu không cần thiết.** Một khóa bao quanh toàn bộ phép transform có thể khiến tất cả request xếp hàng, tăng latency và giảm throughput. Nó cũng không giải quyết các sai lệch dữ liệu do state của Transformer còn sót giữa hai lần dùng tuần tự nếu không reset hoàn toàn. Tạo Transformer mới từ `Templates` thường là lựa chọn rõ ràng hơn.

### 6.1. Vì sao `ThreadLocal<Transformer>` không phải phương án mặc định?

`ThreadLocal` có thể tránh truy cập đồng thời vào cùng object, nhưng trong web server dùng **thread pool** sẽ phát sinh các câu hỏi khác:

- Tham số, output properties, resolver và listener có thể còn từ request trước trên cùng luồng.
- Thread pool tồn tại lâu, khiến object được giữ trong bộ nhớ cho đến khi được dọn đúng cách.
- Việc xử lý bất đồng bộ có thể chuyển qua luồng khác, làm mô hình thread-local không còn đúng.
- Code phức tạp hơn và dễ mắc lỗi cấu hình khi reload stylesheet hoặc đổi policy.

Nếu profiling cho thấy `templates.newTransformer()` thực sự là nút thắt, hãy đo đạc và thiết kế pool với vòng đời/reset rõ ràng. **Không tối ưu trước bằng cache mutable object dùng chung**.

## 7. Một số API XML khác cũng cần quản lý vòng đời

Vấn đề thread safety không chỉ xuất hiện ở `Transformer`. Khi xử lý SOAP XML trực tiếp, có thể còn dùng DOM, SAX, XPath, StAX và JAXB.

| Đối tượng | An toàn luồng theo cách sử dụng thông thường | Cách tổ chức khuyến nghị |
| --- | --- | --- |
| `DocumentBuilderFactory` | Không nên giả định thread-safe | Tạo và cấu hình trong phạm vi kiểm soát; tránh gọi đồng thời nếu provider không bảo đảm |
| `DocumentBuilder` | **Không thread-safe** | Tạo riêng mỗi phép parse hoặc dùng cơ chế quản lý rõ ràng |
| `SAXParser` / `XMLReader` | Stateful, không dùng chung đồng thời | Tạo riêng khi parse hoặc quản lý vòng đời tương đương |
| `XPathFactory` | Không được giả định dùng đồng thời an toàn | Chọn và cấu hình có kiểm soát, tạo `XPath` mới khi cần |
| `XPath` | **Không thread-safe** | Tạo riêng request hoặc một công đoạn |
| `XMLStreamReader` | Là cursor mutable | Tạo riêng từ input stream mỗi lần đọc |
| `JAXBContext` | Được thiết kế để dùng lại giữa các luồng | Tạo một lần, chia sẻ qua service/marshaller |
| `Marshaller` / `Unmarshaller` | **Không thread-safe** | Tạo theo lần marshal/unmarshal hoặc dùng pool có reset đúng |
| `Templates` | Thread-safe theo hợp đồng JAXP | Cache, chia sẻ |
| `Transformer` | Không bảo đảm thread-safe | Tạo mới mỗi phép transform |
| DOM `Document` | Mutable và không nên sửa đồng thời | Sở hữu dữ liệu theo request, tránh chia sẻ giữa các tác vụ ghi |

Hai điều dễ nhầm:

1. `JAXBContext` tương đối tốn chi phí khởi tạo và thích hợp để **cache**; `Marshaller`/`Unmarshaller` lấy từ context không nên dùng chung giữa các luồng.
2. `TransformerFactory` có chữ *Factory* không có nghĩa bản thân nó an toàn luồng; sự bảo đảm thread-safe cụ thể quan trọng ở **`Templates`**.

### 7.1. Đặt singleton đúng đối tượng

Một cấu trúc phù hợp trong Spring:

~~~mermaid
flowchart TD
    S["Spring singleton XmlIntegrationService"]
    S --> T["final Templates — chia sẻ"]
    S --> J["JAXBContext — chia sẻ nếu cần"]
    T --> A["new Transformer — request A"]
    T --> B["new Transformer — request B"]
    J --> C["new Unmarshaller — request A"]
    J --> D["new Unmarshaller — request B"]
    A --> RA["Source/Result A"]
    B --> RB["Source/Result B"]
~~~

Singleton **service** không có nghĩa tất cả đối tượng mà service dùng phải là singleton. Hãy giữ **dependency an toàn để chia sẻ** trong field, còn instance có mutable state trong local variable.

## 8. Tích hợp với `Source`/`Result` của Spring-WS

Spring-WS cung cấp `WebServiceMessage.getPayloadSource()` và `getPayloadResult()` để đọc/ghi **payload XML**. Trong thông điệp SOAP document/literal, payload thường là phần tử nghiệp vụ đầu trong `soap:Body`, không phải toàn bộ `soap:Envelope`.

Ví dụ SOAP 1.1:

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:old="urn:example:legacy-orders:v1">
    <soap:Header/>
    <soap:Body>
        <old:LegacyOrder>
            <old:code>ORD-1001</old:code>
            <old:priority>HIGH</old:priority>
        </old:LegacyOrder>
    </soap:Body>
</soap:Envelope>
~~~

**Nguồn XML để XSLT xử lý payload** trong một giao diện Spring-WS thông thường là phần tử `old:LegacyOrder` bên trong Body, **không bao gồm SOAP Header**. Nếu cần xử lý SOAP Header, action hoặc Fault, phải dùng API `SoapMessage` tương ứng.

### 8.1. Ghi request đã biến đổi vào SOAP client message

Khi cần tự viết phần payload trước khi gọi đối tác bằng `WebServiceTemplate`, callback có thể làm việc với `WebServiceMessage`:

~~~java
import javax.xml.transform.Source;
import org.springframework.ws.client.core.WebServiceMessageCallback;
import org.springframework.ws.soap.SoapMessage;

Source sourceForThisRequest = /* XML Source của riêng request */;

WebServiceMessageCallback callback = message -> {
    orderXsltTransformer.transform(
            sourceForThisRequest,
            message.getPayloadResult());

    SoapMessage soap = (SoapMessage) message;
    soap.setSoapAction("urn:example:orders:SubmitOrder");
};
~~~

Đây là **đoạn minh họa callback**, giả định đã có biến `orderXsltTransformer` và `sourceForThisRequest`, đồng thời `WebServiceTemplate` dùng SOAP message factory phù hợp. Callback cần được truyền vào một lời gọi client thực tế, chẳng hạn API `sendAndReceive(...)`; nó không tự gửi request.

Lưu ý:

- `getPayloadResult()` là **đích** để ghi payload SOAP Body; không dùng nó để đặt HTTP URL.
- `setSoapAction(...)` thiết lập action theo mô hình SOAP, khác QName phần tử request.
- Nguồn XML phải thuộc riêng callback/lần gọi; không chia sẻ một `StreamSource` đã đọc hết giữa nhiều request.
- Nếu stylesheet đổi root QName, WSDL của **đích** phải cho phép QName mới, và client phải dùng đúng SOAP binding/namespace/action.
- SOAP version, TLS, timeout, WS-Security và marshalling/validation khác vẫn cần được cấu hình riêng.

### 8.2. Endpoint nhận `@RequestPayload Source`

Một endpoint cũng có thể nhận XML trực tiếp:

~~~java
import javax.xml.transform.Source;
import javax.xml.transform.TransformerException;
import javax.xml.transform.dom.DOMResult;
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;

@Endpoint
public class LegacyOrderEndpoint {
    private final OrderXsltTransformer converter;

    public LegacyOrderEndpoint(OrderXsltTransformer converter) {
        this.converter = converter;
    }

    @PayloadRoot(
        namespace = "urn:example:legacy-orders:v1",
        localPart = "LegacyOrder"
    )
    public void receive(@RequestPayload Source request)
            throws TransformerException {

        DOMResult normalized = new DOMResult();
        converter.transform(request, normalized);

        // Tiếp theo: kiểm tra normalized.getNode() với XSD đích,
        // ánh xạ hoặc xử lý nghiệp vụ, áp dụng chính sách lỗi.
        // Đây chỉ là điểm trình diễn Source -> DOMResult.
    }
}
~~~

Ví dụ method **không trả payload** để tập trung vào thao tác biến đổi; nó phù hợp minh họa endpoint không có response payload, **không phải hiện thực hoàn chỉnh cho một WSDL operation request/response**. Nếu hợp đồng quy định response, hãy trả đúng response JAXB/`Source` qua `@ResponsePayload`. Trong production, không được dừng ở bước tạo `DOMResult` mà không kiểm tra/đưa kết quả vào nghiệp vụ.

### 8.3. Cảnh báo: biến đổi QName trước hay sau khi định tuyến?

`@PayloadRoot` và `PayloadRootAnnotationMethodEndpointMapping` định tuyến dựa trên **QName của payload lúc mapping diễn ra**. Với `LegacyOrder`, endpoint ở trên được chọn bằng QName namespace `legacy-orders:v1` **trước khi method chạy XSLT**.

Không nên giả định rằng một `EndpointInterceptor` được chạy **sau khi endpoint mapping đã chọn handler** có thể đổi root QName rồi khiến Spring-WS tự định tuyến lại sang method dành cho `SubmitOrderRequest`. Nếu cần chuyển đổi root **trước mapping**, phải đặt bước biến đổi ở một tầng có thứ tự phù hợp hoặc thiết kế một adapter endpoint cụ thể cho hợp đồng cũ.

Đây là lỗi kiến trúc thường gặp: XSLT sửa XML thành hợp lệ với schema mới nhưng request vẫn được dispatch theo endpoint mapping của payload cũ. **Biến đổi dữ liệu và chọn endpoint là hai hoạt động riêng biệt.**

## 9. XML security: khóa đường truy cập tài nguyên ngoài

Transformer xử lý XML có thể gặp nguồn dữ liệu **không đáng tin cậy**: SOAP Body của đối tác, XML tải về, stylesheet hoặc tài liệu được stylesheet tham chiếu. Những mối nguy quan trọng:

- **XXE (XML External Entity):** parser đọc DTD/entity rồi truy cập file nội bộ hoặc mạng.
- **SSRF/tải tài nguyên ngoài:** stylesheet dùng `xsl:include`, `xsl:import` hoặc `document()` để mở URL không mong muốn.
- **XSLT extension functions:** một số implementation hỗ trợ extension có quyền gọi Java hoặc cơ chế ngoài XSLT chuẩn.
- **DoS:** XML lồng sâu, khai báo entity quá lớn, stylesheet tốn CPU/bộ nhớ hoặc kết quả phình to.
- **Rò rỉ log:** exception lộ đường dẫn hệ thống, nguồn stylesheet hoặc nội dung payload nhạy cảm.

### 9.1. Cấu hình TrAX hạn chế truy cập ngoài

Mẫu ở mục 5 thiết lập:

~~~java
TransformerFactory factory = TransformerFactory.newInstance();
factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_STYLESHEET, "");
~~~

Ý nghĩa:

| Thiết lập | Mục đích |
| --- | --- |
| `FEATURE_SECURE_PROCESSING` | Yêu cầu chế độ xử lý an toàn theo khả năng JAXP/provider |
| `ACCESS_EXTERNAL_DTD=""` | Chặn truy cập DTD ngoài từ Transformer/processor theo hợp đồng JAXP |
| `ACCESS_EXTERNAL_STYLESHEET=""` | Chặn truy cập stylesheet/tài nguyên ngoài qua import/include/document theo các đường được provider hỗ trợ |

**Chỉ đặt `FEATURE_SECURE_PROCESSING` là chưa đủ để kết luận đã hết XXE/SSRF.** Phải cấu hình rõ external access và kiểm tra bằng test. Nếu provider ném lỗi vì không hỗ trợ thuộc tính bảo mật, phải giải quyết việc đó ở cấu hình hoặc thay provider, không dùng `catch (Exception ignored)`.

### 9.2. Tạo `SAXSource` với parser chống DTD cho XML từ đối tác

Với input XML không tin cậy, thay vì đưa một `StreamSource` thẳng cho provider tự quyết định parser nào được dùng, có thể tạo nguồn SAX với `XMLReader` đã cấu hình:

~~~java
import java.io.StringReader;
import javax.xml.parsers.SAXParserFactory;
import javax.xml.transform.Source;
import javax.xml.transform.sax.SAXSource;
import org.xml.sax.InputSource;
import org.xml.sax.XMLReader;

public static Source secureSource(String xml) throws Exception {
    SAXParserFactory factory = SAXParserFactory.newInstance();
    factory.setNamespaceAware(true);
    factory.setXIncludeAware(false);

    factory.setFeature(
        "http://apache.org/xml/features/disallow-doctype-decl",
        true);
    factory.setFeature(
        "http://xml.org/sax/features/external-general-entities",
        false);
    factory.setFeature(
        "http://xml.org/sax/features/external-parameter-entities",
        false);

    XMLReader reader = factory.newSAXParser().getXMLReader();
    reader.setFeature(
        "http://xml.org/sax/features/external-general-entities",
        false);
    reader.setFeature(
        "http://xml.org/sax/features/external-parameter-entities",
        false);

    return new SAXSource(
            reader,
            new InputSource(new StringReader(xml)));
}
~~~

Các tên feature trên được hỗ trợ rộng rãi trong nhiều parser Java, nhưng **không phải mọi provider đều hỗ trợ toàn bộ**. Khi cần chính sách chặn DTD, nên **fail closed** nếu một feature bắt buộc không thể bật/tắt, và kiểm thử payload chứa `DOCTYPE` ở runtime mục tiêu.

Trong ứng dụng thật, nên:

1. Chỉ parse dữ liệu sau khi giới hạn kích thước input phù hợp.
2. Dùng parser đã harden, không bật XInclude hoặc external entity nếu không có nhu cầu.
3. Bảo vệ cả XML **đầu vào** lẫn XSLT được biên dịch.
4. Không dùng XML do client gửi làm stylesheet trực tiếp.
5. Giới hạn timeout/tài nguyên và giám sát trường hợp stylesheet chạy lâu.

Ví dụ SAX phía trên cho phép minh họa XML dưới dạng `String`; với payload lớn, nên cấp `InputStream` giới hạn kích thước thay vì đọc toàn bộ vào string, nhưng phải quản lý đóng stream và tránh đọc lại source đã tiêu thụ.

### 9.3. Phân biệt stylesheet tin cậy và dữ liệu XML không tin cậy

Stylesheet là **chương trình biến đổi**, không chỉ là dữ liệu. Chấp nhận XSLT tùy ý từ client có thể cho phép:

- Đọc tài nguyên ngoài qua tính năng processor cho phép.
- Thực thi extension functions không an toàn tùy engine.
- Tạo vòng lặp/đệ quy tốn CPU hoặc kết quả cực lớn.

Với dịch vụ SOAP contract-first, nên quản lý stylesheet như **mã cấu hình được review và version hóa**, đóng gói cùng ứng dụng. Nếu cần tải stylesheet từ nguồn quản lý ngoài, phải xác thực nguồn, giới hạn chức năng XSLT, xác minh cấu hình provider và áp dụng sandbox/giới hạn tài nguyên theo hệ thống.

Nếu stylesheet tin cậy thực sự cần `xsl:include`, không mở quyền truy cập mạng toàn cục. Nên dùng `URIResolver` chỉ cho phép các resource đã duyệt trong classpath hoặc kho nội bộ, đồng thời xác minh chính sách `ACCESS_EXTERNAL_STYLESHEET` và cách resolver tương tác với processor. Đừng coi URIResolver tùy chỉnh là cơ chế an toàn nếu nó không kiểm tra đường dẫn và namespace tài nguyên đầu vào.

## 10. XSLT 1.0, XSLT 2.0 và tính di động của provider

JAXP đưa ra abstraction chung nhưng **không có nghĩa mọi TransformerFactory đều hỗ trợ cùng phiên bản XSLT hoặc cùng extension functions**:

- Nhiều JDK thông dụng cung cấp processor cho **XSLT 1.0**.
- XSLT 2.0/3.0 thường cần engine riêng có hỗ trợ tương ứng, được tích hợp và cấu hình có chủ đích.
- `TransformerFactory.newInstance()` có thể chọn provider theo service-provider configuration, system properties hoặc runtime. Thay dependency có thể thay engine thực tế.
- Kết quả transform và thông báo lỗi có thể khác nhau ở extension/proprietary features.

Để hợp đồng SOAP ổn định:

1. Chỉ dùng tính năng XSLT cần thiết và tương thích với provider đã chọn.
2. Kiểm thử compile stylesheet khi ứng dụng khởi động.
3. Ghi nhận implementation/provider trong quá trình chẩn đoán khi có lỗi môi trường.
4. Không dựa vào extension functions không kiểm soát hoặc hành vi parse không được specification bảo đảm.
5. Khi nâng JDK hoặc processor, chạy lại regression tests trên payload thực tế.

Đừng nhầm version của XSLT với **SOAP version 1.1/1.2**: hai lớp khác nhau. Đổi engine XSLT không tự sửa namespace Envelope hoặc WSDL binding.

## 11. Xử lý lỗi biến đổi và ánh xạ SOAP Fault

Các nhóm lỗi nên phân biệt:

| Lỗi | Thời điểm thường gặp | Phản ứng phù hợp |
| --- | --- | --- |
| `TransformerConfigurationException` | Biên dịch stylesheet hoặc cấu hình transformer | Fail-fast, không khởi động với contract lỗi |
| `TransformerException` | Đang biến đổi XML | Phân loại XML đầu vào/đầu ra và policy xử lý |
| XML không well-formed | Parse input | Từ chối request, báo lỗi có kiểm soát |
| XSD validation thất bại | Trước/sau transform | Trả lỗi hợp đồng phù hợp, không gọi nghiệp vụ |
| Mismatch root QName | Spring-WS endpoint mapping | Kiểm tra WSDL và định tuyến |
| SOAP Fault nghiệp vụ | Endpoint/interceptor/resolver | Trả SOAP Fault code/detail đã công bố |
| HTTP 500 trả HTML | Gateway hoặc hạ tầng HTTP | Không cố diễn giải thành SOAP Fault |
| DNS/TLS/read timeout | Transport | Không tự gán SOAP Fault khi chưa có SOAP response |

Nếu XML đầu vào không hợp lệ, một endpoint có thể ném exception và dùng `EndpointExceptionResolver` (ví dụ `SoapFaultMappingExceptionResolver`) để tạo SOAP Fault. Không nên mặc định rằng mọi `TransformerException` đã có sẵn typed Fault detail theo WSDL: ứng dụng phải thiết kế fault contract và mapping.

**Không trả stack trace, absolute file path, system ID nội bộ hoặc nguyên văn nội dung XML nhạy cảm trong Fault gửi cho client.** Ở log nội bộ, có thể ghi correlation ID, mã lỗi, QName payload, tên stylesheet/phiên bản và vị trí lỗi đã được lọc dữ liệu nhạy cảm.

### 11.1. XSLT thành công chưa có nghĩa giao dịch thành công

Biến đổi XML là một công đoạn kỹ thuật; nó không chứng minh nghiệp vụ đã thực hiện. Ví dụ request tạo đơn hàng có thể transform và validate thành công nhưng bị từ chối do tồn kho, chữ ký WS-Security hoặc quyền gọi operation.

Nếu biến đổi xảy ra ở SOAP client trước khi gửi dữ liệu, timeout sau khi gửi request **không chứng minh server chưa xử lý**. Khi retry thao tác có tác dụng phụ, dùng idempotency key hoặc cơ chế đối soát, không chỉ gọi lại XSLT rồi gửi thêm lần nữa.

## 12. Kiểm thử concurrency: tái sử dụng đúng thứ cần tái sử dụng

Vì vấn đề thread safety thường khó phát hiện qua một request, nên thiết kế test gọi cùng transformer service từ nhiều luồng. Các tiêu chí quan trọng:

- Mỗi tác vụ có **Source, Result và tham số riêng**.
- Tất cả tác vụ dùng **cùng một `Templates`** qua singleton service.
- Output của tác vụ A không chứa giá trị tenant/request của tác vụ B.
- Kết quả được parse và so sánh theo **QName + giá trị**, không chỉ so khớp chuỗi XML.
- Không có exception ngẫu nhiên, output bị cắt hoặc element trộn lẫn.

Ví dụ JUnit 5 minh họa ý tưởng chạy đồng thời:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.StringReader;
import java.io.StringWriter;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import javax.xml.transform.stream.StreamResult;
import javax.xml.transform.stream.StreamSource;
import org.junit.jupiter.api.Test;

class OrderXsltTransformerTest {

    @Test
    void transformsIndependentRequestsConcurrently() throws Exception {
        OrderXsltTransformer service = new OrderXsltTransformer();
        ExecutorService pool = Executors.newFixedThreadPool(8);

        try {
            List<Callable<String>> tasks = new ArrayList<>();
            for (int i = 0; i < 100; i++) {
                final String orderId = "ORD-" + i;
                tasks.add(() -> {
                    String xml =
                            "<old:LegacyOrder " +
                            "xmlns:old=\"urn:example:legacy-orders:v1\">" +
                            "<old:code>" + orderId + "</old:code>" +
                            "<old:priority>HIGH</old:priority>" +
                            "</old:LegacyOrder>";

                    StringWriter out = new StringWriter();
                    service.transform(
                            new StreamSource(new StringReader(xml)),
                            new StreamResult(out));
                    return out.toString();
                });
            }

            List<Future<String>> results = pool.invokeAll(tasks);
            assertEquals(100, results.size());
            for (int i = 0; i < results.size(); i++) {
                String output = results.get(i).get();
                assertTrue(output.contains("ORD-" + i));
            }
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

Test này là **kiểm tra concurrency minh họa**, chưa đủ làm XSD validation hay chứng minh hoàn toàn không có race condition. Trong bộ test thực:

1. Parse từng output bằng parser an toàn.
2. Kiểm tra root QName `{urn:example:orders:v2}SubmitOrderRequest` và giá trị `orderId`/`priority` theo từng request.
3. Thêm tham số XSLT riêng từng request để phát hiện rò rỉ state.
4. Thử số lần gọi lớn hơn, thay đổi thứ tự thực thi và chạy dưới profiler nếu có lỗi.
5. Kiểm thử cả input lỗi/thiếu trường, bảo đảm exception của một tác vụ không làm hỏng tác vụ khác.

Với thao tác xử lý SOAP, nên bổ sung `MockWebServiceClient`/`MockWebServiceServer` để xác nhận payload đúng contract và test tích hợp HTTP(S) cho servlet, gateway, TLS và SOAP Fault. Test biến đổi trực tiếp ở mức Java không thể xác minh đường truyền SOAP.

## 13. Ma trận kiểm thử chức năng và bảo mật

| Tình huống | Kết quả cần xác nhận |
| --- | --- |
| Input XML hợp lệ namespace cũ | XSLT tạo root QName và field theo namespace mới |
| XML dùng prefix khác nhưng cùng namespace URI | XPath trong XSLT vẫn tìm đúng node |
| XML thiếu trường bắt buộc | Validation đầu vào/đầu ra phát hiện, không gửi nghiệp vụ |
| Input có ký tự đặc biệt `&`, `<` trong text | Output serialize XML hợp lệ, không nối chuỗi không escape |
| Input sai thứ tự phần tử | XSD validator xử lý đúng theo `xs:sequence` |
| Input hoặc stylesheet có `DOCTYPE` ngoài | Cấu hình parser/security chặn theo policy |
| XSLT dùng `document()` mở URL ngoài | External access policy từ chối |
| XSLT dùng `xsl:include` trái policy | Không biên dịch được hoặc bị policy chặn |
| XSLT compile lỗi | Ứng dụng fail-fast, không phục vụ với template hỏng |
| 100 request song song | Không trộn tham số/đầu ra; mỗi request có Transformer riêng |
| `StreamSource` đã bị đọc một lần | Không dùng lại nguồn đã tiêu thụ |
| Root QName thay đổi sau transform | Không mong interceptor sau mapping tự map lại endpoint |
| SOAP Header có chữ ký | Không sửa nội dung đã ký một cách tùy tiện |
| SOAP 1.1 vs SOAP 1.2 | Envelope, Content-Type, binding và Fault đúng version |
| Kết quả XSLT đúng cấu trúc nhưng nghiệp vụ từ chối | Xử lý SOAP Fault riêng, không coi transform thành công là giao dịch thành công |
| Timeout sau khi gửi thao tác ghi | Không retry mù quáng, kiểm tra idempotency/trạng thái |

Trong kiểm thử contract-first, nên lưu các file XML mẫu làm **golden fixtures**, kiểm tra expanded names thay vì prefix cố định và chạy schema validation với XSD được công bố. Với XSLT có định dạng whitespace không ổn định, so sánh cây XML/giá trị quan trọng hơn so sánh byte-for-byte.

## 14. Hiệu năng, bộ nhớ và streaming

Biến đổi XML có thể gây tải đáng kể:

- **Biên dịch XSLT** thường đắt hơn tạo một `Transformer` từ `Templates`. Hãy biên dịch một lần khi khởi động hoặc khi cập nhật stylesheet.
- **DOM** giữ cây XML trong bộ nhớ, thuận tiện truy vấn/sửa đổi nhưng có chi phí theo kích thước payload.
- **StreamSource/StreamResult** cho phép làm việc với stream nhưng không bảo đảm XSLT processor thực thi hoàn toàn theo kiểu streaming; một số stylesheet/engine phải giữ dữ liệu trung gian trong bộ nhớ.
- **StringWriter/ByteArrayOutputStream** giữ toàn bộ output trong RAM; không phù hợp với payload hoặc attachment rất lớn.
- **SAX/StAX** có thể hữu ích khi bài toán phù hợp xử lý theo sự kiện/cursor, nhưng cần quản lý parser và stream theo request.

Không nên giả định rằng chuyển từ `DOMSource` sang `StreamSource` là đủ để đạt streaming với mọi XSLT. XSLT có các phép truy vấn ngược, sắp xếp, gom nhóm hoặc `document()` có thể yêu cầu processor lưu trạng thái đáng kể.

### 14.1. Khi stylesheet cần reload

Trong hệ thống vận hành dài hạn, nếu phải thay stylesheet khi đang chạy:

1. Tải stylesheet mới từ nguồn tin cậy và compile thành **`Templates` mới**.
2. Kiểm thử syntax, security policy và các XML fixtures trước khi áp dụng.
3. Thay **tham chiếu Templates** một cách nguyên tử, ví dụ qua một holder sử dụng `AtomicReference<Templates>`.
4. Mỗi request lấy đúng một snapshot Templates rồi tạo Transformer từ snapshot đó.
5. Giữ thông tin version để truy vết request được xử lý bằng stylesheet nào.

Không sửa trực tiếp một `Transformer` đang phục vụ request, cũng không thay đổi cấu hình factory cùng lúc các luồng khác đang dùng nó. Nếu hệ thống không có nhu cầu reload, **constructor compile một lần và field `final`** là giải pháp đơn giản và an toàn hơn.

## 15. Bài tập tình huống

Một dịch vụ Spring-WS nhận `LegacyPaymentRequest`, dùng XSLT chuyển thành `PaymentRequest` để gọi SOAP client ngân hàng. Đội phát triển viết:

~~~java
@Component
public class PaymentXmlTransformer {
    private final Transformer transformer;

    public PaymentXmlTransformer(TransformerFactory factory,
                                 Source stylesheet)
            throws TransformerConfigurationException {
        this.transformer = factory.newTransformer(stylesheet);
    }

    public void convert(Source source, Result result, String tenant)
            throws TransformerException {
        transformer.setParameter("tenant", tenant);
        transformer.transform(source, result);
    }
}
~~~

Khi tải tăng, có request của khách hàng A xuất hiện mã tenant B trong output. Đồng thời hệ thống cho phép người dùng gửi một URL stylesheet để áp dụng “tùy biến”.

**Câu hỏi:**

1. Vì sao `Transformer` đặt trong singleton là nguy hiểm?
2. Nên cache đối tượng nào thay cho `Transformer`?
3. Cần thay đổi logic `convert(...)` như thế nào?
4. Vì sao không nên để người dùng truyền stylesheet URL tùy ý?
5. Nếu XSLT biến đổi `LegacyPaymentRequest` thành `PaymentRequest` trong interceptor **sau endpoint mapping**, Spring-WS có tự chọn lại handler theo root mới không?
6. Sau khi XSLT thành công, có thể retry vô điều kiện nếu client gọi ngân hàng bị read timeout không?

**Đáp án gợi ý:**

1. `Transformer` chứa mutable state như tham số tenant và không được bảo đảm an toàn luồng; nhiều request có thể ảnh hưởng nhau.
2. Cache một `Templates` đã biên dịch từ stylesheet tin cậy; đối tượng này được thiết kế để dùng đồng thời.
3. Mỗi lần gọi `convert` tạo `Transformer local = templates.newTransformer()`, đặt tenant trên transformer local rồi gọi transform với Source/Result riêng.
4. Stylesheet có thể truy cập tài nguyên ngoài, sử dụng extension function hoặc tiêu tốn tài nguyên; phải dùng stylesheet được kiểm soát và bảo vệ JAXP.
5. **Không.** Endpoint mapping đã chọn handler theo trạng thái thông điệp tại thời điểm mapping; biến đổi sau đó không tự kích hoạt routing lần nữa.
6. **Không.** Read timeout không chứng minh ngân hàng chưa xử lý; phải dùng idempotency/reconciliation theo nghiệp vụ.

### 15.1. Nhiệm vụ thực hành

Hãy thay thế `PaymentXmlTransformer` bằng service sử dụng:

- `TransformerFactory` được cấu hình `FEATURE_SECURE_PROCESSING` và hạn chế external DTD/stylesheet access.
- `Templates` compile một lần từ resource nội bộ.
- `Transformer` mới mỗi lần gọi.
- `SAXSource` với parser có chính sách chặn DTD cho input không tin cậy.
- XSD validation trước và sau transform.
- Test đa luồng với tenant A/B xen kẽ và test URL access bị chặn.

**Tiêu chí đạt:** output của mỗi request độc lập, không có tải tài nguyên ngoài trái phép, XML hợp schema đích, và lỗi biến đổi được báo theo hợp đồng SOAP thay vì để lộ thông tin nội bộ.

## 16. Ghi nhớ

- **`Transformer`** thực hiện `transform(Source, Result)` nhưng mang mutable state và **không được bảo đảm thread-safe**; không chia sẻ một instance giữa nhiều SOAP request.
- **`Templates`** là stylesheet đã biên dịch, **được thiết kế để thread-safe**; cache trong singleton và gọi `newTransformer()` cho từng phép biến đổi.
- **`TransformerFactory`** là factory/configuration object; không mặc định nó an toàn khi gọi đồng thời. Cấu hình và compile stylesheet ở bước khởi tạo có kiểm soát.
- **`Source`/`Result`** thường chứa dữ liệu hoặc stream riêng của một request; không tái sử dụng stream đã tiêu thụ hay output buffer giữa các luồng.
- **XML trực tiếp không đồng nghĩa XSD-valid**: sau XSLT vẫn cần kiểm tra schema, QName và ngữ nghĩa dữ liệu nếu hợp đồng yêu cầu.
- **An toàn XML là yêu cầu thiết yếu**: chặn DTD/external entities, giới hạn stylesheet access, không cho chạy XSLT tùy ý từ nguồn không tin cậy và áp dụng giới hạn tài nguyên.
- Với **Spring-WS**, `getPayloadSource()`/`getPayloadResult()` thao tác với **payload SOAP Body**, không phải toàn bộ Envelope; SOAP Header, action và Fault có API riêng.
- **Biến đổi sau endpoint mapping không tự định tuyến lại request**; phải đặt conversion ở đúng tầng hoặc dùng adapter endpoint riêng.
- Quản lý đúng vòng đời **`DocumentBuilder`, `XPath`, `Marshaller`/`Unmarshaller`** như các đối tượng có trạng thái; giữ `JAXBContext`/`Templates` ở phạm vi dùng chung khi phù hợp.
- Kiểm thử **concurrency, namespace, XSD, SOAP version, SOAP Fault, TLS, WS-Security và timeout/idempotency** để pipeline tích hợp doanh nghiệp đáng tin cậy.
