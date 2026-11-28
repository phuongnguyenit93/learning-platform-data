# Schema import, XSLT import và truy cập tài nguyên ngoài không được kiểm soát

Khi phát triển SOAP service bằng **Spring Web Services (Spring-WS)**, XML không chỉ chứa dữ liệu nghiệp vụ. Bộ xử lý XML còn có thể **tham chiếu và nạp các tài nguyên khác**: XSD dùng `xs:import`, `xs:include`, XML có `xsi:schemaLocation`, XSLT có `xsl:import`, `xsl:include` và hàm `document()`. Nếu các tham chiếu được giải quyết một cách tùy tiện, một service tưởng chỉ đọc SOAP Body có thể kết nối tới website ngoài, địa chỉ mạng nội bộ hoặc đọc file trong máy chủ.

Bài **“Schema import, XSLT import và truy cập tài nguyên ngoài không được kiểm soát”**, thuộc chương **Bảo vệ xử lý XML** của module `SPRING_WEB_SERVICES`, tập trung vào việc **hạn chế các đường đọc tài nguyên bên ngoài trong quá trình biên dịch schema, validation, transform và xử lý SOAP**. Chủ đề gắn với phát triển dịch vụ SOAP **contract-first**, thiết kế **XSD/WSDL**, ánh xạ **JAXB**, xây dựng `@Endpoint`/`WebServiceTemplate`, quản lý interceptor, SOAP Fault, XML security, WS-Security, chứng chỉ và kiểm thử tích hợp.

**Nguyên tắc xuyên suốt:** *không để input XML hoặc stylesheet/schema chưa được tin cậy quyết định một URL/file bất kỳ mà server sẽ mở*. Cấu hình nên **deny-by-default**, chỉ giải quyết những XSD/XSLT đã được đóng gói/kiểm duyệt qua **allowlist, resolver hoặc catalog**, và thất bại rõ ràng khi gặp tham chiếu lạ. Trong môi trường production, dùng thêm mạng egress policy, giới hạn kích thước/thời gian và monitoring.

Các tên miền `example.test`, `schemas.example.test`, dữ liệu đơn hàng và đường dẫn trong ví dụ đều giả định. Các đoạn code dùng JAXP tiêu chuẩn của Java, đặt bối cảnh JDK 17+; **khả năng hỗ trợ property và thứ tự áp dụng còn phụ thuộc XML provider/runtime thực tế**, đặc biệt khi thay Xerces/Xalan bằng thư viện khác.

## 1. Những đường mà XML processor có thể mở tài nguyên bên ngoài

Đừng chỉ nghĩ tới **XXE** (XML External Entity). Ngay cả khi parser đã chặn `DOCTYPE`, schema compiler và XSLT transformer vẫn có những đường mở tài nguyên khác.

~~~mermaid
flowchart TD
    R["SOAP request / XML / XSD / XSLT"] --> P["XML parser"]
    R --> S["SchemaFactory / Validator"]
    R --> T["TransformerFactory / Transformer"]

    P --> D["DOCTYPE / external entity / external DTD"]
    S --> X["xs:include, xs:import, schemaLocation"]
    T --> I["xsl:import, xsl:include"]
    T --> F["document() và extension functions"]

    D --> N["file://, http(s)://, jar:, network"]
    X --> N
    I --> N
    F --> N
    N --> V["SSRF, đọc file, lộ dữ liệu, phụ thuộc mạng, DoS"]
~~~

Một số đường đọc xảy ra **khi ứng dụng khởi động hoặc compile schema/stylesheet**, số khác chỉ xảy ra **khi nhận và validate/transform một request**.

| Cơ chế | Ví dụ | Khi nào thường được xử lý? | Bề mặt rủi ro |
| --- | --- | --- | --- |
| External DTD/entity | `<!DOCTYPE ... SYSTEM "...">` | Parse XML/XSD/XSLT. | XXE, đọc file, SSRF, entity expansion. |
| `xs:include` | `schemaLocation="common.xsd"` | Biên dịch tập XSD. | Nạp schema ngoài phạm vi, ghi đè hợp đồng ngoài ý muốn. |
| `xs:import` | Import namespace khác từ URL. | Biên dịch XSD hoặc theo resolver. | Outbound network, dependency từ host ngoài. |
| `xs:redefine` hoặc `xs:override` (theo XSD version) | Nạp schema khác để tái định nghĩa. | Biên dịch schema khi provider hỗ trợ. | Biến đổi ý nghĩa của schema được tin cậy. |
| `xsi:schemaLocation` | Hint trong XML instance. | Khi validator/parser dựa vào hint để tìm schema. | Client có thể gợi ý URL truy cập; không nhất thiết được truy cập nếu validator dùng schema cố định. |
| `xsl:include` / `xsl:import` | Nạp stylesheet phụ. | Compile XSLT/Templates. | Stylesheet ngoài kho được duyệt. |
| `document()` trong XSLT | Đọc thêm XML theo URI. | Lúc thực thi transformation. | SSRF, đọc tài nguyên ngoài, làm lộ dữ liệu. |
| XSLT extension functions | Java extension hoặc hàm vendor-specific. | Compile/chạy XSLT tùy engine. | Có thể vượt khỏi mô hình XPath/XSLT thuần. |
| XInclude | `xi:include` trong XML. | Khi XML parser/processor bật XInclude. | Nạp tài nguyên theo href ngoài. |

**Mức tin cậy của XSD/XSLT khác với dữ liệu SOAP request.** XSD và XSLT thường do đội phát triển đóng gói nên được xem là **trusted artifacts**, nhưng vẫn cần review và khóa dependency; nếu chúng được tải hoặc chỉnh bởi đối tác, chúng có thể trở thành input chưa được tin cậy. XML request từ mạng là dữ liệu không tin cậy ngay cả khi parse thành công.

### 1.1. Hậu quả điển hình

- **SSRF:** tiến trình SOAP server bị hướng gọi một URL không được phép, có thể vào mạng nội bộ hoặc dịch vụ metadata.
- **Local file disclosure:** XML processor đọc file tồn tại trên máy chủ nếu được phép.
- **Đọc tài nguyên do attacker kiểm soát:** stylesheet/schema có thể lấy nội dung động từ host ngoài, khiến kết quả thay đổi không qua release.
- **DoS hoặc startup failure:** recursive imports, network timeout, dữ liệu quá lớn, entity expansion, XSLT quá phức tạp làm tăng CPU/heap.
- **Đứt hợp đồng:** XSD được import ở runtime thay đổi mà không cập nhật WSDL, dẫn tới validator và JAXB không cùng nhận thức về contract.
- **Rò rỉ bảo mật:** dữ liệu hoặc HTTP metadata có thể xuất hiện trong log, callback hoặc báo cáo lỗi khi parser nạp tài nguyên ngoài.

### 1.2. Ví dụ tài nguyên bị tham chiếu là dữ liệu do client quyết định

Một instance XML có hint schema:

~~~xml
<ord:CreateOrderRequest
    xmlns:ord="urn:example:orders:v1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
      urn:example:orders:v1
      https://schemas.example.test/unreviewed/orders.xsd">
  <ord:clientOrderId>WEB-00042</ord:clientOrderId>
</ord:CreateOrderRequest>
~~~

`xsi:schemaLocation` là **hint**, không phải chỉ thị buộc validator có schema đã cấu hình phải tải URL đó. Tuy nhiên, nếu ứng dụng tạo validator không gắn schema đáng tin hoặc tin hint như nguồn hợp đồng, nó có thể dẫn đến external lookup.

**Không dùng `xsi:schemaLocation` do đối tác gửi để quyết định schema nào sẽ được tin cậy hoặc nơi server phải tải schema.** Với Spring-WS contract-first, server biết operation/XSD cần áp dụng từ cấu hình của chính mình.

## 2. XSD include/import có ý nghĩa hợp lệ, nhưng cần kiểm soát nguồn

Một contract SOAP thường tách XSD thành các file: `orders.xsd` chứa request/response, `common.xsd` chứa kiểu dùng chung, `payment-types.xsd` chứa kiểu từ namespace khác. Việc dùng import/include **không phải lỗi bảo mật tự thân**; vấn đề là **nguồn được nạp**.

### 2.1. Include cho cùng targetNamespace

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<!-- orders.xsd: trích đoạn, type ở common.xsd -->
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:ord="urn:example:orders:v1"
    targetNamespace="urn:example:orders:v1"
    elementFormDefault="qualified">

  <xs:include schemaLocation="common.xsd"/>

  <xs:element name="CreateOrderRequest"
              type="ord:CreateOrderRequestType"/>
</xs:schema>
~~~

Trong XSD 1.0, `xs:include` thường kết hợp các tài liệu schema cùng target namespace hoặc các trường hợp chameleon schema theo quy tắc chuẩn. Đường `common.xsd` được giải quyết **tương đối với base URI/systemId của file orders.xsd**, không nhất thiết so với thư mục làm việc hiện tại.

Nếu code tạo `StreamSource` từ `InputStream` mà **không đặt `systemId`**, relative imports/includes có thể lỗi dù file có tồn tại; một số thư viện có thể cố tìm từ vị trí không mong muốn. Thiếu base URI là vấn đề tính đúng và bảo mật.

### 2.2. Import từ namespace khác

~~~xml
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:ord="urn:example:orders:v1"
    xmlns:pay="urn:example:payments:v1"
    targetNamespace="urn:example:orders:v1">

  <xs:import
      namespace="urn:example:payments:v1"
      schemaLocation="https://schemas.example.test/payments/v1/payments.xsd"/>

  <!-- Các element/type nghiệp vụ khác -->
</xs:schema>
~~~

`namespace` là **định danh logic** của schema được import, trong khi `schemaLocation` là một **location hint** để tìm tài liệu. Hai giá trị không đồng nghĩa. Địa chỉ HTTPS hiển thị trong schema **không bắt buộc phải được tải từ mạng lúc chạy**; có thể map nó sang tài nguyên đã đóng gói bằng **LSResourceResolver/XML Catalog**.

### 2.3. Vì sao không cho phép tất cả HTTPS?

Một cấu hình như:

~~~java
schemaFactory.setProperty(
    XMLConstants.ACCESS_EXTERNAL_SCHEMA, "https");
~~~

chỉ giới hạn **giao thức**, không giới hạn host, path, IP đích hoặc bản phát hành schema. Nó vẫn cho phép những HTTPS URLs không nằm trong tập tài nguyên đã được duyệt nếu resolver/provider thực hiện lookup.

Trong production, ưu tiên:

1. **Khóa** các XSD và dependencies trong bản release, theo version/hash.
2. Cấu hình **`ACCESS_EXTERNAL_SCHEMA=""`** để không tự mở URL/file ngoài ở schema processor.
3. Cung cấp **resolver/catalog chỉ ánh xạ exact known IDs** vào bytes/resources đáng tin.
4. **Từ chối** tham chiếu không biết; không fallback sang URL từ `schemaLocation`.
5. Test offline hoàn toàn và chặn outbound network ở hạ tầng.

### 2.4. Đường xử lý schema thường có hai giai đoạn

~~~mermaid
sequenceDiagram
    participant APP as Spring-WS service
    participant SF as SchemaFactory
    participant RES as Allowlist Resolver
    participant V as Validator
    participant XML as SOAP payload

    APP->>SF: newSchema(trusted orders.xsd)
    SF->>RES: resolve common.xsd / import
    RES-->>SF: Allowed local schema bytes
    SF-->>APP: Compiled Schema
    APP->>V: newValidator()
    XML->>V: validate(payload)
    V-->>APP: valid / SAXException
~~~

Không nên compile schema từ Internet cho **mỗi SOAP request**. Việc compile schema có chi phí, phụ thuộc độ tin cậy của imports và có thể gây tải mạng. Nên chuẩn bị `Schema` từ **trusted artifacts** trong startup/deployment, kiểm thử import closure và dùng lại `Schema` khi phù hợp; **`Validator` không thread-safe**, tạo/được quản lý riêng cho mỗi lần validation theo quy tắc API.

## 3. JAXP: ba thuộc tính chặn truy cập ngoài không được nhầm lẫn

Java API for XML Processing (**JAXP**) định nghĩa các **External Access Properties (EAPs)** trong `javax.xml.XMLConstants`. Chúng cho biết một XML processor có được tự mở các tài nguyên bằng giao thức nào không.

| Constant (Java) | System property tương ứng | Kiểm soát chủ yếu |
| --- | --- | --- |
| `XMLConstants.ACCESS_EXTERNAL_DTD` | `javax.xml.accessExternalDTD` | DTD và external entity references trong XML/XSD/XSLT. |
| `XMLConstants.ACCESS_EXTERNAL_SCHEMA` | `javax.xml.accessExternalSchema` | Tham chiếu schema: `xs:include`, `xs:import`, schema-location hints theo điều kiện sử dụng. |
| `XMLConstants.ACCESS_EXTERNAL_STYLESHEET` | `javax.xml.accessExternalStylesheet` | `xsl:include`, `xsl:import`, `document()` và một số cách nạp stylesheet. |

Các giá trị cho phép là **danh sách protocol**, không phải hostname allowlist.

~~~java
// Cấm JAXP provider tự mở bất kỳ external resource nào.
factory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
~~~

~~~text
""          = không cho phép giao thức ngoài nào
"file"      = cho phép file:  (rất rộng, không phải sandbox thư mục)
"https"     = cho phép mọi HTTPS host có thể truy cập
"file,https"= cho phép cả file: và https:
"all"       = cho phép mọi giao thức provider hỗ trợ
~~~

**Không dùng `"none"` thay cho `""`**: các EAPs nhận danh sách protocol, không có từ khóa deny-all chuẩn là `none`. **Không dùng `"false"` như boolean** vì đây là thuộc tính kiểu String, không phải cờ `true/false`.

Đặc biệt, `file` cho phép tham chiếu đến bất kỳ file nào mà tiến trình có quyền đọc, **không giới hạn vào thư mục schema**. `https` cho phép một giao thức, **không kiểm tra hostname/IP/redirect**. Chính vì vậy bản production thường cần `""` cộng allowlist resolver/catalog.

### 3.1. FEATURE_SECURE_PROCESSING có ích nhưng không thay EAP

Các API factory JAXP thường hỗ trợ:

~~~java
factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
~~~

`FEATURE_SECURE_PROCESSING` (**FSP**) báo ý định xử lý an toàn, áp giới hạn hoặc hạn chế tính năng tùy provider. Với JDK, **bật FSP rõ ràng bằng API** thường giúp hạn chế external connections; nhưng trạng thái mặc định của các factories, thứ tự precedence, overrides và XML provider có thể khác giữa JDK/version.

Tuy vậy, **không chỉ bật FSP rồi cho là đã bảo vệ mọi đường**. Nên đặt trực tiếp các EAP cần thiết, kiểm tra provider chấp nhận cấu hình, quản lý resolver, tắt DTD nếu không cần và test network/file denial. Đặc biệt StAX `XMLInputFactory` không có cùng FSP interface; phải dùng các thuộc tính an toàn riêng.

### 3.2. Vì sao phải cấu hình cho từng factory/processor?

Một ứng dụng Spring-WS có thể có nhiều XML processors do nhiều thư viện khác nhau tạo ra:

~~~text
MessageFactory / SOAP parser
    ├─ SAX / DOM / StAX parser
XSD loading / validation
    ├─ SchemaFactory
    └─ Validator
JAXB marshalling
    ├─ JAXBContext / Marshaller / Unmarshaller
XSLT transformation
    ├─ TransformerFactory
    ├─ Templates
    └─ Transformer
WSDL generation
    └─ Spring-WS / Apache WS-Commons XMLSchema resolver
~~~

Cấu hình chặn external access trên **một** `TransformerFactory` không tự áp cho `SchemaFactory` trong một thư viện khác. Tương tự, đặt `ACCESS_EXTERNAL_SCHEMA` cho `SchemaFactory` của bạn **không chứng minh** `PayloadValidatingInterceptor` đã dùng factory đó.

**Mỗi nơi tạo XML parser, validator hoặc transformer là một ranh giới cấu hình.** Phải nhận diện factory/provider đang thực sự chạy và bảo đảm chính sách áp dụng từ startup tới runtime.

### 3.3. Property scope và precedence

Oracle JAXP Security Guide mô tả nhiều mức cấu hình:

1. Cấu hình **trực tiếp trên factory/processor**, có phạm vi hẹp và thường ưu tiên cao.
2. **JVM system properties** như `-Djavax.xml.accessExternalSchema=`.
3. **JAXP configuration file** (`conf/jaxp.properties` hoặc vị trí tùy JDK).
4. **Defaults** của provider/JDK, không nên coi luôn an toàn.

Trong môi trường ứng dụng đa module, **tránh gọi `System.setProperty` tùy tiện khi đang xử lý request**. Đây là trạng thái toàn tiến trình; một thread có thể thay đổi chính sách XML của thread khác. Ưu tiên cấu hình factory riêng và kiểm tra vào startup. JVM flags/JAXP config có thể đóng vai trò defense-in-depth nếu cần thống nhất mặc định.

Một ví dụ runtime flags cho cả ba EAP:

~~~text
-Djavax.xml.accessExternalDTD=
-Djavax.xml.accessExternalSchema=
-Djavax.xml.accessExternalStylesheet=
~~~

Dù có JVM flags, **custom resolver có thể chủ động mở resource** và không còn chịu tác dụng hạn chế của EAP cho nguồn do resolver trả về. Đây là lý do phải audit resolver và không cho phép fallback không kiểm soát.

## 4. SchemaFactory: compile XSD theo chính sách deny-by-default

Một cách tối thiểu để biên dịch **XSD đã tin cậy, không có imports/includes** là tạo `SchemaFactory` với các ràng buộc rõ:

~~~java
import javax.xml.XMLConstants;
import javax.xml.transform.stream.StreamSource;
import javax.xml.validation.Schema;
import javax.xml.validation.SchemaFactory;
import javax.xml.validation.Validator;

import java.io.InputStream;

public final class SchemaValidationSetup {

    public static Schema loadOrdersSchema() throws Exception {
        SchemaFactory factory = SchemaFactory.newInstance(
            XMLConstants.W3C_XML_SCHEMA_NS_URI);

        factory.setFeature(
            XMLConstants.FEATURE_SECURE_PROCESSING, true);

        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        try (InputStream in = SchemaValidationSetup.class
                .getResourceAsStream("/xsd/orders/orders.xsd")) {
            if (in == null) {
                throw new IllegalStateException(
                    "Missing trusted orders.xsd");
            }

            StreamSource main = new StreamSource(in);
            main.setSystemId("urn:bundled:orders:orders.xsd");

            return factory.newSchema(main);
        }
    }

    public static void validateXml(
            Schema schema, StreamSource xml) throws Exception {
        Validator validator = schema.newValidator();
        validator.setProperty(
            XMLConstants.ACCESS_EXTERNAL_DTD, "");
        validator.setProperty(
            XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        validator.validate(xml);
    }
}
~~~

**Giới hạn rất quan trọng của ví dụ:** phương thức `validateXml` nhận một `StreamSource` đã được ứng dụng tạo; trong production, phải đảm bảo **input XML parser** cũng được bảo vệ, không để `DOCTYPE` hoặc tài nguyên ngoài được mở trước khi tới validator. Với SOAP server, parser của `WebServiceMessageFactory` cần cấu hình riêng theo runtime. Xem mục 9.

Ở ví dụ này, `orders.xsd` giả định **không chứa import/include**; nếu chứa, factory bị chặn truy cập ngoài và có thể báo lỗi compile. Đừng chữa bằng `ACCESS_EXTERNAL_SCHEMA="all"`. Thay vào đó, chuyển sang **resolver/catalog với whitelist** ở mục 5.

### 4.1. Fail closed khi cấu hình bị provider từ chối

Các thao tác như:

~~~java
factory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
~~~

có thể ném exception nếu **provider cụ thể không hỗ trợ API/property** hoặc dùng một JAXP implementation quá cũ. Cách xử lý an toàn là:

- **Fail startup/test** với thông điệp cấu hình rõ ràng.
- Không nuốt exception rồi tiếp tục hoạt động với default mở rộng.
- Không dựa vào việc “application compile” là bằng chứng property có hiệu lực; phải có **negative tests** không tải được resource ngoài.
- Ghi provider class/version và config status khi khởi động dưới dạng metadata an toàn (không log XML chứa secrets).

Không cần dùng lệnh đọc file nhạy cảm để kiểm tra bảo mật. Test bằng tài nguyên mô phỏng trong loopback/test server được quản lý và xác nhận không phát sinh connection.

### 4.2. Schema là reusable, Validator thường không thread-safe

Theo JAXP, một `Schema` sau khi được compile có thể được dùng tạo nhiều `Validator` cho các request. Ngược lại, **`Validator` không an toàn để dùng chung nhiều thread**. Thực hành tốt:

~~~java
Schema compiledSchema = SchemaValidationSetup.loadOrdersSchema();

// Mỗi lần validate:
Validator validator = compiledSchema.newValidator();
// ... set properties/resolver đúng policy cho validator
// ... validate input đã được parse an toàn
~~~

Không giữ một singleton `Validator` rồi cho mọi SOAP request dùng song song. Không tạo lại `SchemaFactory.newSchema(...)` từ network cho từng request: vừa tốn CPU vừa thêm attack surface.

### 4.3. Đừng tin schemaLocation từ XML request

Một validator được cấu hình với schema đã biết nên validate theo **trusted Schema**. Tránh mẫu triển khai:

~~~java
// Không nên: lấy URL schemaLocation từ SOAP Body hoặc
// thuộc tính xsi:schemaLocation và truyền trực tiếp để load.
Schema schema = SchemaFactory.newInstance(
    XMLConstants.W3C_XML_SCHEMA_NS_URI
).newSchema(untrustedUrl);
~~~

Cách đó biến một hint do đối tác gửi thành **cấu hình truy cập URL** và có thể mở SSRF. Ngay cả khi `newSchema(URL)` được gọi bởi code nội bộ, URL vẫn có thể do dữ liệu không đáng tin tạo ra. Mặc định nên giữ schema cố định theo operation và release version.

## 5. Cho phép schema import có kiểm soát bằng LSResourceResolver

Khi contract XSD được chia nhiều file, một resolver cần chuyển **identifier đã biết** thành **tài nguyên được đóng gói sẵn**. Đối với `SchemaFactory`, giao diện tiêu chuẩn là `org.w3c.dom.ls.LSResourceResolver`.

Điểm dễ bỏ sót: **EAP không hạn chế việc một resolver trả về nguồn không null**. Theo JAXP Security Guide, khi resolver trả một `LSInput`/`Source` đã tự cung cấp, external access restrictions không được áp lại như đối với fallback lookup. Do đó, nếu resolver tự làm `new URL(systemId).openStream()` thì **`ACCESS_EXTERNAL_SCHEMA=""` không cứu được ứng dụng** khỏi kết nối do resolver chủ động mở.

### 5.1. Sai: resolver tải mọi systemId

~~~java
// KHÔNG DÙNG: ví dụ mô tả anti-pattern.
LSResourceResolver unsafe = (type, ns, publicId,
                              systemId, baseUri) -> {
    // Một triển khai mở URL bất kỳ từ systemId
    // có thể gây SSRF/đọc file/tải XSD ngoài.
    return fetchArbitraryResource(systemId);
};
~~~

`fetchArbitraryResource` chỉ là tên giả để minh họa điều **không được làm**, không phải hàm trong JAXP. Ngay cả khi `systemId` là relative, ghép nó với `baseURI` không kiểm tra cũng có thể dẫn đến path traversal hoặc URL nội bộ.

### 5.2. Đúng hướng: allowlist exact namespace và systemId

Giả định project chỉ có **hai dependency schema** được duyệt:

~~~text
src/main/resources/
  xsd/
    orders/
      orders.xsd
      common.xsd
    payments/
      payments.xsd
~~~

Chúng không được tải từ website ở runtime. Code sau minh họa resolver **không tạo URL từ input** và **không dùng đường dẫn filesystem người dùng cung cấp**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;

import org.w3c.dom.ls.DOMImplementationLS;
import org.w3c.dom.ls.LSInput;
import org.w3c.dom.ls.LSResourceResolver;

public final class BundledXsdResolver implements LSResourceResolver {

    private static final int MAX_SCHEMA_BYTES = 256 * 1024;
    private final DOMImplementationLS domLs;

    public BundledXsdResolver(DOMImplementationLS domLs) {
        this.domLs = domLs;
    }

    @Override
    public LSInput resolveResource(
            String type,
            String namespaceUri,
            String publicId,
            String systemId,
            String baseUri) {

        // Chỉ cho phép cặp (namespace, schema location)
        // có trong hợp đồng đã phê duyệt.
        final String trustedResource;

        if ("urn:example:orders:v1".equals(namespaceUri)
                && "common.xsd".equals(systemId)) {
            trustedResource = "xsd/orders/common.xsd";
        } else if ("urn:example:payments:v1".equals(namespaceUri)
                && "https://schemas.example.test/payments/v1/payments.xsd"
                    .equals(systemId)) {
            trustedResource = "xsd/payments/payments.xsd";
        } else {
            throw new IllegalArgumentException(
                "Disallowed schema reference");
        }

        try (InputStream in = getClass().getClassLoader()
                .getResourceAsStream(trustedResource)) {

            if (in == null) {
                throw new IllegalStateException(
                    "Missing bundled schema");
            }

            // Có giới hạn: schema đã duyệt phải đủ nhỏ.
            byte[] data = in.readNBytes(MAX_SCHEMA_BYTES + 1);
            if (data.length > MAX_SCHEMA_BYTES) {
                throw new IllegalStateException(
                    "Bundled schema exceeds configured limit");
            }

            LSInput resolved = domLs.createLSInput();
            resolved.setByteStream(new ByteArrayInputStream(data));
            resolved.setPublicId(publicId);
            resolved.setSystemId("urn:bundled:" + trustedResource);
            return resolved;

        } catch (IOException ex) {
            throw new IllegalStateException(
                "Cannot read approved schema", ex);
        }
    }
}
~~~

**Lưu ý giới hạn của ví dụ:** chỉ có hai cặp allowlist. Nó không tự hỗ trợ mọi graph schema nhiều tầng, không dùng source URI chưa được tin cậy và không đưa tên file từ input vào `getResourceAsStream`. Đối với production, cũng cần kiểm tra **base URI, loại tài nguyên, ký kết/kiểm soát dependency và số tầng import**, đặc biệt khi namespace hoặc identifier lặp ở nhiều schema versions. Nếu provider thay đổi cách truyền `systemId`, phải cập nhật **mapping exact được kiểm thử**, không nới thành `startsWith("http")`.

Tạo `DOMImplementationLS` bằng API DOM tiêu chuẩn và gắn resolver:

~~~java
import javax.xml.XMLConstants;
import javax.xml.transform.stream.StreamSource;
import javax.xml.validation.Schema;
import javax.xml.validation.SchemaFactory;
import java.io.InputStream;

import org.w3c.dom.DOMImplementation;
import org.w3c.dom.bootstrap.DOMImplementationRegistry;
import org.w3c.dom.ls.DOMImplementationLS;

// Khởi tạo trong startup/configuration, nơi Exception được xử lý fail-closed.
DOMImplementation dom = DOMImplementationRegistry
    .newInstance().getDOMImplementation("LS");

if (!(dom instanceof DOMImplementationLS domLs)) {
    throw new IllegalStateException(
        "DOM Load/Save implementation unavailable");
}

SchemaFactory factory = SchemaFactory.newInstance(
    XMLConstants.W3C_XML_SCHEMA_NS_URI);

factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
factory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
factory.setResourceResolver(new BundledXsdResolver(domLs));

try (InputStream in = getClass().getResourceAsStream(
        "/xsd/orders/orders.xsd")) {

    if (in == null) {
        throw new IllegalStateException(
            "Missing main contract schema");
    }

    StreamSource source = new StreamSource(in);
    source.setSystemId("urn:bundled:orders:orders.xsd");

    Schema schema = factory.newSchema(source);
    // Lưu Schema cho các lần validate theo policy.
}
~~~

**Đây là đoạn cấu hình trong một method/class**, không phải file Java có đủ package, imports của toàn project và chạy trực tiếp. `DOMImplementationRegistry` có thể ném exception khi tìm provider; không bỏ qua lỗi. `newSchema(source)` phải fail khi một include/import không nằm trong allowlist.

### 5.3. Resolver phải từ chối, không được fallback im lặng

Giao diện `LSResourceResolver` cho phép trả `null`; trong nhiều JAXP providers, `null` có nghĩa **để implementation dùng cơ chế lookup mặc định**. Với EAP rỗng, fallback thường bị chặn, nhưng việc trả `null` dễ khiến hệ thống **bị nới quyền trong cấu hình khác**.

Vì vậy mẫu fail-closed **ném lỗi cho identifier không cho phép**. Chỉ có resolver được quản lý mới được quyền trả các bytes đã duyệt. Khi test, hãy thử tham chiếu URI HTTP loopback, file URI, absolute URL và path traversal để đảm bảo không có network/file access.

### 5.4. XML Catalog là lựa chọn thay resolver tự viết

**XML Catalog** (JDK `javax.xml.catalog` hoặc thư viện phù hợp) ánh xạ external identifiers sang tài nguyên local theo bảng cấu hình. Nó hữu ích khi contract XSD nhiều files hoặc dùng URI ổn định do đối tác công bố.

Ý tưởng:

~~~text
External logical schema URI:
  https://schemas.example.test/payments/v1/payments.xsd

Catalog mapping (được quản trị theo phiên bản):
  → xsd/payments/payments.xsd đóng gói cùng ứng dụng

Runtime:
  không gọi schemas.example.test
  chỉ lấy bytes có trong artifact đã ký duyệt
~~~

Catalog phải được cấu hình theo **strict resolve policy**: tham chiếu chưa biết không được truy cập Internet. **Đừng chỉ đặt catalog rồi cho fallback network**, vì như vậy import chưa được map vẫn có thể tạo kết nối ngoài. Bản thân file catalog và target của nó cũng phải là **trusted inputs**, không được xây động từ SOAP request.

### 5.5. Không làm mất khả năng validate XSD

Cách sửa sai thường gặp là **tắt schema validation** khi import bị chặn. Điều đó chuyển lỗi cấu hình XSD thành lỗ hổng dữ liệu nghiệp vụ. Cách đúng:

- Resolve import/include từ nguồn local đã duyệt.
- Compile schema thành công ở startup hoặc pipeline CI.
- Dùng `Validator` hoặc Spring-WS payload interceptor với schema đã duyệt.
- Kiểm tra request sai schema vẫn bị phát hiện.
- Chặn resource không được duyệt nhưng **không chặn các schema hợp lệ trong allowlist**.

## 6. XSLT import/include và document(): hai thời điểm truy cập ngoài

XSLT thường được dùng để biến XML của một đối tác thành một format mà hệ thống khác hiểu, hoặc làm sạch/chuẩn hóa XML trước JAXB mapping. Khi dùng trong Spring-WS, XSLT có thể xuất hiện trong một interceptor, adapter hoặc component ứng dụng có `TransformerFactory`.

### 6.1. xsl:include và xsl:import: xử lý khi compile

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform">

  <xsl:include href="common.xsl"/>

  <xsl:template match="/">
    <normalized>
      <xsl:apply-templates/>
    </normalized>
  </xsl:template>
</xsl:stylesheet>
~~~

Đây là XSLT **minh họa**. `common.xsl` có thể định nghĩa templates được tái sử dụng, nhưng location cần được resolve từ artifact đã kiểm duyệt. Trong XSLT 1.0, `xsl:import` có quy tắc precedence và vị trí đặc biệt (thường trước các top-level elements khác), còn `xsl:include` có semantics gần với ghép stylesheet. Chỉ đổi URL import mà không xem thứ tự template có thể làm thay đổi kết quả nghiệp vụ.

### 6.2. document() có thể đọc tài nguyên khi transform

~~~xml
<xsl:variable name="codebook"
              select="document('codebook.xml')"/>
~~~

Hàm `document()` của XSLT 1.0 có thể yêu cầu nạp một XML document khác **khi chạy transformation**. Nếu `codebook.xml` là dữ liệu được duyệt và đóng gói, có thể dùng resolver local. Nhưng nếu stylesheet hoặc tham số do caller tạo ra được phép chèn `document($arbitraryUrl)`, processor có thể trở thành **network/file reader**.

Với tài nguyên chưa được tin cậy, không cho phép stylesheet tự quyết định arbitrary URI, kể cả URL dùng HTTPS. Một XSLT file được lưu trong source repository vẫn phải được code review: một lần thay `document('...')` có thể tạo đường truy cập ngoài trong production.

### 6.3. XSLT extension functions là bề mặt tách biệt

Một số XSLT engines hỗ trợ vendor-specific extension functions hoặc XSLT 2.0/3.0, vượt ngoài mô hình XSLT 1.0 tiêu chuẩn của JDK. Tùy provider, chúng có thể gọi code Java, đọc/ghi tài nguyên hoặc thực hiện tác vụ khác.

- Bật `FEATURE_SECURE_PROCESSING` và kiểm tra chính sách extension functions của provider.
- **Không chấp nhận stylesheet do người dùng/đối tác bất kỳ gửi tới để chạy trong JVM có quyền cao**.
- Nếu bắt buộc chạy XSLT chưa được tin cậy, nên **cách ly process/container**, giới hạn filesystem/network/CPU/memory, thay vì chỉ tin một flag JAXP.
- Không giả định `ACCESS_EXTERNAL_STYLESHEET=""` kiểm soát mọi extension function hoặc mọi output destination.

## 7. TransformerFactory và URIResolver: kiểm soát XSLT import và document()

JAXP `javax.xml.transform.TransformerFactory` có thể compile XSLT thành `Templates`, tạo `Transformer` rồi chạy trên XML input. Hai thời điểm cần bảo vệ là:

1. **Compile stylesheet:** `xsl:import`/`xsl:include` và external DTD.
2. **Execute transformation:** hàm `document()`, nguồn XML được parse, extension functions và output destination.

### 7.1. Cấu hình TransformerFactory tối thiểu

~~~java
import javax.xml.XMLConstants;
import javax.xml.transform.TransformerFactory;

TransformerFactory factory = TransformerFactory.newInstance();

factory.setFeature(
    XMLConstants.FEATURE_SECURE_PROCESSING, true);

// Cấm external DTD và stylesheet/document mặc định.
factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_STYLESHEET, "");
~~~

**Phải dùng `setAttribute` cho EAP của TransformerFactory**, không copy `SchemaFactory#setProperty` một cách máy móc. Khi provider không hỗ trợ/không chấp nhận thuộc tính bảo mật, nên fail startup thay vì bắt rồi bỏ qua exception.

Cấu hình này thường làm **XSLT có import/include từ URL/file tự do bị từ chối**. Nếu stylesheet dùng các file phụ hợp lệ, cung cấp **`URIResolver` chỉ trả về local bytes đã duyệt**.

### 7.2. URIResolver không được tự fetch arbitrary URL

Đối với XSLT, giao diện là `javax.xml.transform.URIResolver`:

~~~java
Source resolve(String href, String base)
    throws TransformerException;
~~~

Cả `href` và `base` có thể được sử dụng để tạo một URI. **Không viết**:

~~~java
// Anti-pattern: đừng dùng để xử lý XSLT không tin cậy.
URIResolver unsafe = (href, base) -> {
    return new StreamSource(new java.net.URL(
        java.net.URI.create(base).resolve(href).toString()
    ).openStream());
};
~~~

Đoạn này chỉ minh họa *vì sao resolver nguy hiểm*, không phải hướng dẫn triển khai. Nó có thể mở network/file không qua allowlist khi stylesheet quyết định `href`. Với remote redirects hoặc URI scheme khác, rủi ro còn lớn hơn nếu không có kiểm soát.

### 7.3. URIResolver chỉ trả về tài nguyên được đóng gói

Giả sử dự án chỉ cho phép XSLT dùng `common.xsl` và XML codebook `codebook.xml` tại classpath:

~~~text
src/main/resources/xslt/
  orders.xsl
  common.xsl
  codebook.xml
~~~

Một resolver fail-closed:

~~~java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.Map;

import javax.xml.transform.Source;
import javax.xml.transform.TransformerException;
import javax.xml.transform.URIResolver;
import javax.xml.transform.stream.StreamSource;

public final class BundledXsltResolver implements URIResolver {

    private static final int MAX_RESOURCE_BYTES = 256 * 1024;

    private static final Map<String, String> APPROVED = Map.of(
        "common.xsl", "xslt/common.xsl",
        "codebook.xml", "xslt/codebook.xml"
    );

    @Override
    public Source resolve(String href, String base)
            throws TransformerException {

        // Không ghép path trực tiếp từ input hoặc base URI.
        String resource = APPROVED.get(href);
        if (resource == null) {
            throw new TransformerException(
                "Unapproved XSLT resource reference");
        }

        try (InputStream in = getClass().getClassLoader()
                .getResourceAsStream(resource)) {

            if (in == null) {
                throw new TransformerException(
                    "Approved XSLT resource not packaged");
            }

            byte[] data = in.readNBytes(MAX_RESOURCE_BYTES + 1);
            if (data.length > MAX_RESOURCE_BYTES) {
                throw new TransformerException(
                    "Approved XSLT resource too large");
            }

            // Hệ thống chỉ cấp dữ liệu đã đóng gói, không fetch URI.
            StreamSource source =
                new StreamSource(new ByteArrayInputStream(data));
            source.setSystemId("urn:bundled:xslt:" + href);
            return source;

        } catch (IOException e) {
            throw new TransformerException(
                "Cannot load approved XSLT resource", e);
        }
    }
}
~~~

**Giới hạn của ví dụ:** nó chỉ chấp nhận **exact string** và không kiểm tra `base` chi tiết. Với production nhiều stylesheet lồng nhau, cần giới hạn thêm **base URI/version**, depth, namespace và quy tắc import tương ứng; không nới resolver để trả mọi file dưới một thư mục bằng string concatenation. Tài nguyên được map phải được **kiểm duyệt trong release**; không cho client ghi vào `xslt/common.xsl` hoặc `xslt/codebook.xml`.

Với `document('codebook.xml')`, provider có thể gọi cùng resolver khi transform; với `xsl:include href="common.xsl"`, provider gọi lúc compile. **Cả hai đường phải được kiểm thử**: chỉ test compile không chứng minh runtime không thể dùng `document()` khác.

### 7.4. Compile Templates và tạo Transformer an toàn

~~~java
import java.io.InputStream;
import javax.xml.XMLConstants;
import javax.xml.transform.Templates;
import javax.xml.transform.Transformer;
import javax.xml.transform.TransformerFactory;
import javax.xml.transform.stream.StreamSource;

BundledXsltResolver resolver = new BundledXsltResolver();

TransformerFactory factory = TransformerFactory.newInstance();
factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_STYLESHEET, "");
factory.setURIResolver(resolver);

Templates templates;

try (InputStream in = getClass().getResourceAsStream(
        "/xslt/orders.xsl")) {
    if (in == null) {
        throw new IllegalStateException("Missing trusted stylesheet");
    }

    StreamSource stylesheet = new StreamSource(in);
    stylesheet.setSystemId("urn:bundled:xslt:orders.xsl");
    templates = factory.newTemplates(stylesheet);
}

// Khi xử lý từng request:
Transformer transformer = templates.newTransformer();
transformer.setURIResolver(resolver);

// Source phải đến từ parser an toàn hoặc một object đã kiểm soát.
// Result phải là đích output do ứng dụng chọn.
// transformer.transform(trustedXmlSource, safeResult);
~~~

Đây là đoạn cấu hình trong một method/class có exception handling phù hợp. `Templates` là compiled stylesheet có thể dùng lại theo contract JAXP; `Transformer` tạo cho mỗi lần chạy, **không chia sẻ một instance mutable giữa các thread**.

Khi dùng `Result`:

- `StreamResult(outputStream)` tới stream do ứng dụng **sở hữu** có thể phù hợp.
- Không dùng `new StreamResult(userSuppliedFilePath)` hoặc URL do SOAP Body cung cấp.
- EAP **ACCESS_EXTERNAL_STYLESHEET** là kiểm soát **đọc nguồn ngoài** của transformation, **không tự bảo vệ mọi output target** do application chủ động chọn.
- Đừng log nguyên `Result` nếu nó chứa PII/credentials.

### 7.5. Stylesheet và nguồn XML đều cần chính sách riêng

Nếu bạn tạo `Transformer` an toàn nhưng cung cấp `StreamSource` trỏ tới một URL/file từ request, XML reader/provider vẫn có thể truy cập nguồn đó **trước hoặc trong quá trình biến đổi**. Cần đọc input qua một **parser an toàn** và cung cấp `DOMSource`/`SAXSource`/`StAXSource` theo kiểm soát thích hợp.

Không coi `transform(new StreamSource(untrustedUrl), result)` là an toàn chỉ vì `ACCESS_EXTERNAL_STYLESHEET=""`; URL ở đây có thể là **nguồn chính được code truyền trực tiếp**, không chỉ là import/document().

## 8. Parser đầu vào: phải chặn XXE trước khi validate/transform

Ngăn `xs:import` và `xsl:include` chưa đủ nếu SOAP parser/DOM/SAX/StAX **vẫn chấp nhận DOCTYPE và external entities** trong input XML. Hãy có quy tắc riêng cho parser tại mọi ranh giới.

### 8.1. DOM parser cho tài liệu XML chưa tin cậy

Một cấu hình phòng vệ thường dùng khi nhà cung cấp parser hỗ trợ các feature tương ứng:

~~~java
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;

import org.xml.sax.SAXException;

DocumentBuilderFactory dbf = DocumentBuilderFactory.newInstance();
dbf.setNamespaceAware(true);
dbf.setXIncludeAware(false);
dbf.setExpandEntityReferences(false);

dbf.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
dbf.setFeature(
    "http://apache.org/xml/features/disallow-doctype-decl", true);

dbf.setFeature(
    "http://xml.org/sax/features/external-general-entities", false);
dbf.setFeature(
    "http://xml.org/sax/features/external-parameter-entities", false);
dbf.setFeature(
    "http://apache.org/xml/features/nonvalidating/load-external-dtd",
    false);

dbf.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
dbf.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

DocumentBuilder builder = dbf.newDocumentBuilder();
builder.setEntityResolver((publicId, systemId) -> {
    throw new SAXException("External entities are not allowed");
});

// builder.parse(stream) chỉ sau khi kiểm tra giới hạn input.
~~~

**Không bắt/nuốt lỗi `ParserConfigurationException` hoặc UnsupportedOperationException rồi tiếp tục parse với defaults**. Nếu provider không hỗ trợ một feature cần thiết, phải xem tài liệu implementation và **fail closed** hoặc chọn parser khác đã kiểm thử. `setExpandEntityReferences(false)` chỉ là biện pháp bổ sung; **không đủ** nếu DTD/external entities vẫn được xử lý.

Để bảo vệ SOAP service, cấu hình này phải được áp tại **parser thực sự xử lý SOAP input**. Một factory DOM trong service utility không tự cấu hình `SaajSoapMessageFactory`/`AxiomSoapMessageFactory` hoặc mọi SAX parser nội bộ của framework.

### 8.2. StAX XMLInputFactory

StAX không có cùng `setFeature(FSP)` như DOM/SAX. Ví dụ:

~~~java
import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLStreamException;

XMLInputFactory xif = XMLInputFactory.newFactory();
xif.setProperty(XMLInputFactory.SUPPORT_DTD, Boolean.FALSE);
xif.setProperty(
    XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES,
    Boolean.FALSE);

xif.setXMLResolver((publicId, systemId, baseUri, namespace) -> {
    throw new XMLStreamException(
        "External references are not permitted");
});

// Dùng factory này để tạo XMLStreamReader trên nguồn đã giới hạn.
~~~

Không giả định mọi StAX provider tôn trọng property giống nhau. Để đánh giá an toàn, test đúng implementation/version trong classpath của Spring-WS application, nhất là khi có Axiom streaming.

### 8.3. JAXBUnmarshaller không thay parser hardening

Khi JAXB nhận `InputStream`/`Source`, cần phân biệt:

- Một `DOMSource` đã parse bằng **DOM parser an toàn**.
- Một `SAXSource` có XMLReader được cấu hình an toàn.
- Một `StAXSource` từ XMLStreamReader được cấu hình cấm DTD/external entities.
- Một `StreamSource` mà JAXB/provider có thể tự tạo parser phía sau.

Chỉ gọi `Jaxb2Marshaller#setSchemas(...)` hoặc gắn `Schema` **không chứng minh** parser đọc input trước đó đã chống XXE hoặc external DTD. Validation đúng XSD và parser security là hai trách nhiệm bổ sung nhau.

### 8.4. Giới hạn tài nguyên không chỉ là chặn mạng

Dù đã chặn mọi external references, XML/XSD/XSLT có thể gây hao CPU/heap bằng:

- XML rất lớn hoặc cấu trúc quá sâu.
- Quá nhiều phần tử/thuộc tính và nested constructs.
- XSLT có template recursion phức tạp.
- Schema import closure quá nhiều file, circular dependencies hoặc khó compile.
- MTOM attachments lớn, cache/tạm trên đĩa không giới hạn.

Cần đặt kích thước body/attachments, depth/entity expansion limits nếu provider hỗ trợ, timeouts và concurrency caps, và đo memory/GC. **EAP không phải giới hạn kích thước file hay thời gian xử lý**.

## 9. Áp dụng vào Spring Web Services theo contract-first

Spring-WS giúp xây SOAP services từ XSD/WSDL và thường xử lý XML qua các thành phần cấu hình:

- `MessageDispatcherServlet` nhận HTTP/SOAP request.
- `WebServiceMessageFactory` tạo và parse SOAP Envelope (SAAJ hoặc Axiom tùy dự án).
- `PayloadValidatingInterceptor` kiểm tra payload theo XSD.
- `PayloadTransformingInterceptor` dùng XSLT để biến đổi payload request/response nếu ứng dụng yêu cầu.
- `Jaxb2Marshaller` và các endpoint adapters chuyển payload sang Java objects.
- `DefaultWsdl11Definition`/`CommonsXsdSchemaCollection` có thể đọc/import/include XSD khi dựng WSDL.

**Những thành phần trên không nhất thiết dùng chung một `SchemaFactory` hoặc `TransformerFactory` instance**. Đó là lý do cần đánh giá từng đường nạp XML.

### 9.1. PayloadValidatingInterceptor dùng schema đáng tin

Ví dụ cấu hình phía server với một XSD đã đóng gói:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.ws.config.annotation.WsConfigurer;
import org.springframework.ws.server.EndpointInterceptor;
import org.springframework.ws.soap.server.endpoint.interceptor.PayloadValidatingInterceptor;

@Configuration
class SoapValidationBeans {
    @Bean
    PayloadValidatingInterceptor ordersValidator() {
        PayloadValidatingInterceptor v =
            new PayloadValidatingInterceptor();
        v.setSchema(new ClassPathResource("xsd/orders/orders.xsd"));
        v.setValidateRequest(true);
        v.setValidateResponse(true);
        return v;
    }
}

@Configuration
class SoapValidationConfig implements WsConfigurer {
    private final PayloadValidatingInterceptor validator;

    SoapValidationConfig(PayloadValidatingInterceptor validator) {
        this.validator = validator;
    }

    @Override
    public void addInterceptors(List<EndpointInterceptor> interceptors) {
        interceptors.add(validator);
    }
}
~~~

Đây là ví dụ **đăng ký interceptor qua Spring bean có lifecycle được quản lý**, không phải ứng dụng hoàn chỉnh. `@EnableWs`/servlet/endpoint adapter và XML dependencies được giả định đã cấu hình. Spring sẽ gọi `afterPropertiesSet()` khi khởi tạo bean, giúp chuẩn bị validator theo lifecycle; không nên thêm một object unmanaged rồi bỏ qua bước này.

**Điểm bảo mật:** dùng `ClassPathResource` cho XSD gốc **không tự chứng minh các `xs:include`/`xs:import` bên trong được kiểm soát**. Cần xác minh cách Spring-WS và Spring XML loading/validator giải quyết **cả dependency closure** và các EAP; negative-test external URL/file references. Nếu validation library không cho cấu hình `SchemaFactory` trực tiếp, cân nhắc adapter/validator do bạn kiểm soát, cơ chế XML catalog/resolver tương thích hoặc các JAXP security properties ở deployment **kèm test cụ thể**.

Không tắt `validateRequest` hay `validateResponse` chỉ để tránh lỗi import. Cần giữ lựa chọn validation theo hợp đồng và threat model: input từ mạng thường cần kiểm tra ranh giới; output validation có thể hữu ích để phát hiện server vi phạm XSD nhưng có chi phí.

### 9.2. CommonsXsdSchemaCollection và WSDL động

Với nhiều XSD được include/import, tài liệu Spring-WS sử dụng `CommonsXsdSchemaCollection` dựa trên **Apache WS-Commons XML Schema**. Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.ClassPathResource;
import org.springframework.xml.xsd.commons.CommonsXsdSchemaCollection;
import org.springframework.ws.wsdl.wsdl11.DefaultWsdl11Definition;

@Bean
public CommonsXsdSchemaCollection ordersSchemas() {
    CommonsXsdSchemaCollection schemas =
        new CommonsXsdSchemaCollection(
            new ClassPathResource("xsd/orders/orders.xsd"));

    schemas.setInline(true);
    return schemas;
}

@Bean
public DefaultWsdl11Definition ordersWsdl(
        CommonsXsdSchemaCollection ordersSchemas) {

    DefaultWsdl11Definition definition =
        new DefaultWsdl11Definition();

    definition.setPortTypeName("OrdersPort");
    definition.setLocationUri("/ws");
    definition.setTargetNamespace("urn:example:orders:v1");
    definition.setSchemaCollection(ordersSchemas);
    return definition;
}
~~~

`setInline(true)` giúp inlining các XSD liên quan trong WSDL theo khả năng thư viện; **không phải thiết lập bảo mật**. `CommonsXsdSchemaCollection` có `setUriResolver(org.apache.ws.commons.schema.resolver.URIResolver)` để tùy chỉnh resolution; **giao diện này khác `org.w3c.dom.ls.LSResourceResolver` của JAXP**. Không ép một resolver JAXP vào Apache WS-Commons rồi cho rằng nó có hiệu lực.

Mục tiêu là:

~~~text
WSDL/XSD gốc được lấy từ classpath đã duyệt
      → Apache WS-Commons resolver chỉ lấy imports/includes hợp lệ
      → Không truy cập network/uri lạ trong startup/WSDL GET
      → XSD collection đúng version được công bố qua WSDL
~~~

Theo Spring-WS Reference 4.1.4, `CommonsXsdSchemaCollection` có resolver mặc định xử lý classpath relative imports, nhưng **vẫn phải đánh giá thực tế** nếu dự án có HTTP URLs, custom URIResolver hoặc XSD nhập từ bên thứ ba. Đặc biệt, **các JAXP EAPs không đảm bảo tự điều khiển Apache WS-Commons URIResolver**.

Nếu hợp đồng WSDL được ký duyệt và cần công bố ổn định, có thể **sinh WSDL rồi kiểm duyệt và công bố WSDL tĩnh**. Spring-WS Reference cũng nêu các nhược điểm của dynamic WSDL (có thể thay đổi khi framework update, tốn chi phí sinh). WSDL tĩnh không thay thế bảo vệ runtime validation/imports nhưng giảm bất định về nội dung hợp đồng public.

### 9.3. PayloadTransformingInterceptor: XSLT import cần audit

Spring-WS cung cấp `PayloadTransformingInterceptor` để chuyển payload giữa các schema versions bằng stylesheets đã cấu hình. Ví dụ định hướng:

~~~java
import org.springframework.core.io.ClassPathResource;
import org.springframework.ws.server.endpoint.interceptor.PayloadTransformingInterceptor;

PayloadTransformingInterceptor transforming =
    new PayloadTransformingInterceptor();

transforming.setRequestXslt(
    new ClassPathResource("xslt/old-to-current.xsl"));
transforming.setResponseXslt(
    new ClassPathResource("xslt/current-to-old.xsl"));
~~~

**Không coi “stylesheet nằm trong classpath” là đủ**. Nó vẫn có thể chứa `xsl:import href="https://..."` hoặc `document('file:...')`. Nếu interceptor tạo `TransformerFactory` nội bộ, cấu hình factory tự viết ở mục 7 **không tự áp dụng**. Cần xác minh Spring-WS version, TransformerFactory provider và JAXP properties ở runtime; khi cần kiểm soát sâu, có thể dùng một component transform riêng với **hardened TransformerFactory + URIResolver** và tích hợp vào pipeline có quản lý.

Trong hệ thống nâng schema version, XSLT được sử dụng để biến đổi **dữ liệu** chứ không được phá WS-Security signed content hoặc bypass request validation. Thứ tự xử lý giữa transform, schema validation và security phải được kiểm thử theo hợp đồng.

### 9.4. JAXB generated classes và XSD imports

Khi dùng **XJC/JAXB** để generate DTO từ XSD, các tool codegen cũng có thể giải quyết `xs:import`/`xs:include`. Đó là **build-time**, khác với runtime server, nhưng vẫn là bề mặt cần kiểm soát:

- Build phải dùng **pinned XSD dependencies** và resolver/catalog đã duyệt.
- Không để codegen tải một schema public đang thay đổi trên mạng.
- Kiểm tra output Java packages/`ObjectFactory`/`JAXBElement` tương thích WSDL.
- Quản lý release artifacts và generated code như phần của contract.
- Bảo vệ **runtime unmarshalling** trước parser external entity ngay cả khi XJC build an toàn.

Build pass không chứng minh runtime SOAP parser an toàn; runtime secure không cứu một codegen pipeline có thể bị thay schema ở build.

### 9.5. WS-Security và XML Signature: không sửa message đã ký để chữa schema import

WS-Security có thể ký SOAP Header, Body hoặc một số phần XML được policy chọn. Nếu bạn thay đổi XML đã ký sau bước verify/sign (ví dụ transform dữ liệu, thêm/bớt namespace hoặc normalize), chữ ký có thể không còn hợp lệ.

Không xử lý lỗi import bằng cách tự tải schema không kiểm soát, tắt validation hoặc **sửa raw XML trước khi xác minh WS-Security**. Đúng hơn, phân biệt:

1. **Lỗi cấu hình schema/XSLT**: trusted dependency không resolve được, phải sửa package/catalog/resolver.
2. **Lỗi XML parser/security**: DTD/URL bên ngoài bị chặn đúng policy, phải trả lỗi an toàn.
3. **Lỗi XSD/business validation**: payload đã parse an toàn nhưng không hợp contract, trả SOAP Fault phù hợp.
4. **Lỗi WS-Security**: token/chữ ký/certificate không hợp lệ, xử lý theo security policy.
5. **Lỗi HTTP/TLS**: kết nối chưa có SOAP response, không mặc định biến thành SOAP Fault.

## 10. Phân biệt lỗi bị chặn với lỗi cấu hình hợp đồng

Khi chặn external access, ứng dụng có thể nhận những exception như:

~~~text
SAXException / SAXParseException
TransformerConfigurationException
TransformerException
XMLStreamException
Spring bean initialization failure
SOAP Fault nếu lỗi validation diễn ra trong request pipeline
~~~

Đừng tự động chuyển mọi lỗi thành `SOAP Server Fault` chứa URL/file path đã cố mở. Lỗi dependency XSD xảy ra **khi startup** nên có thể chặn deploy; lỗi XML do đối tác gửi có thể dẫn tới SOAP Client/Sender Fault theo binding/policy, với thông điệp an toàn.

| Tình huống | Nguyên nhân | Ứng xử an toàn |
| --- | --- | --- |
| `xs:import` đã duyệt không tìm được | Artifact thiếu file hoặc mapping sai. | **Fail startup/build**, sửa bundle/resolver; không mở network tự động. |
| Import sang hostname không nằm allowlist | Schema location không được duyệt. | Từ chối, không fallback URL; log mã lỗi đã phân loại. |
| XSLT `xsl:include` thiếu file | Build/packaging sai. | Fail compile stylesheet, không chạy transform với kết quả một phần. |
| XSLT `document()` dùng URL ngoài | Stylesheet/runtime yêu cầu external resource lạ. | Chặn transform, trả lỗi xử lý thích hợp; không tải URI. |
| XML có DTD/external entity | Input không phù hợp parser policy. | Chặn parse trước khi xử lý JAXB/endpoint. |
| SOAP Body sai `xs:pattern` | Dữ liệu không hợp XSD. | Trả validation Fault theo contract, không đổ cho network. |
| WS-Security signature sai | Signed references/token/certificate không hợp lệ. | Security Fault, không bypass check để debug XSD. |
| SOAP client nhận HTML `502` | Proxy hoặc upstream không có SOAP Envelope. | Transport error, không parse thành SOAP Fault. |

### 10.1. Logging có thể vô tình làm lộ URI nhạy cảm

Nếu exception chứa `systemId` là đường dẫn file nội bộ hoặc URL có query token, việc log raw exception message có thể làm lộ dữ liệu. Với security outcomes:

~~~text
event=XML_EXTERNAL_RESOURCE_BLOCKED
operation=CreateOrder
processor=SchemaFactory
referenceType=XSD_IMPORT
correlationId=corr-27a
source=trusted_schema_bundle
allowed=false
~~~

Đây là mẫu log **minh họa**, không phải output mặc định. Chỉ ghi các field đã được kiểm soát; tránh in toàn XML Envelope, raw `schemaLocation`, URL có secret, UsernameToken, SAML assertion, file contents và stack trace ở log public. Chi tiết kỹ thuật cần đưa vào hệ thống log nội bộ phân quyền.

### 10.2. Chặn theo protocol khác với chặn theo destination

| Biện pháp | Điều chặn tốt | Điều chưa giải quyết |
| --- | --- | --- |
| `ACCESS_EXTERNAL_SCHEMA=""` | Provider không tự fetch các nguồn schema ngoài thuộc phạm vi EAP. | Resolver tự nạp resources, source URL do code truyền trực tiếp. |
| `ACCESS_EXTERNAL_STYLESHEET=""` | Provider không tự fetch XSLT import/include/document() thuộc phạm vi EAP. | Custom resolver và extension functions riêng. |
| Exact allowlist resolver | Chỉ mapping approved identifiers sang local bytes. | Parser khác hoặc transport outbound do code tự gọi. |
| XML Catalog strict | Cho phép resolution offline có quản lý. | Catalog bị sửa hoặc resolver fallback không kiểm soát. |
| Network egress firewall | Giới hạn tiến trình/container đi tới host/IP ngoài. | Đọc file local hoặc tính toán quá nặng. |
| OS/container filesystem permissions | Giảm file có thể bị đọc. | SSRF tới mạng ngoài hoặc data exfil qua thành phần khác. |
| Limits/timeout | Hạn chế kích thước, CPU/heap/độ sâu. | Không thay thế kiểm soát trust và authorization. |

**Defense in depth** quan trọng vì một thư viện mới có thể tạo XML processor riêng, một resolver custom có thể bypass EAP, hoặc operator vô tình đặt `javax.xml.accessExternalSchema=all` khi troubleshoot.

## 11. Ma trận kiểm thử: phải chứng minh không có truy cập ngoài

Chỉ kiểm tra `SchemaFactory#setProperty(...)` chạy không ném lỗi là **chưa đủ**. Cần kiểm thử cả hai chiều:

- **Positive:** các XSD/XSLT hợp lệ được đóng gói vẫn compile/validate/transform đúng.
- **Negative:** schema/stylesheet/XML chứa external references không được duyệt **bị từ chối và không tạo outbound network/file access**.

### 11.1. Các ca kiểm thử tối thiểu

| Case | Tài nguyên đưa vào | Kỳ vọng |
| --- | --- | --- |
| XSD local không import | `orders.xsd` đơn giản. | Compile thành công; validation đúng schema. |
| `xs:include` đã duyệt | `common.xsd` trong classpath. | Được resolve từ bundle, không gọi mạng. |
| `xs:import` đã duyệt | URI đối tác map sang local XSD. | Compile thành công với namespace/type đúng. |
| `xs:import` HTTP chưa duyệt | URL test server không có trong allowlist. | Compile fail; **zero HTTP request** tới URL ấy. |
| `xs:include` path traversal | `../unknown.xsd` hoặc absolute path. | Resolver từ chối; không mở filesystem path do input. |
| Import nested chưa được duyệt | Schema đã duyệt include tiếp tài nguyên lạ. | Fail closed; không fallback network. |
| `xsi:schemaLocation` từ client | SOAP XML chứa URL ngoài. | Không tải schema do client gợi ý; validate theo schema cố định. |
| External DTD/entity | XML instance có DOCTYPE. | Parser từ chối trước JAXB/endpoint. |
| XSLT `xsl:include` hợp lệ | `common.xsl` đã duyệt. | Templates compile thành công offline. |
| XSLT `xsl:import` từ URL lạ | URI chưa duyệt. | TransformerFactory compile fail; không connect. |
| XSLT `document()` local | `codebook.xml` đã duyệt. | Transform thành công, đầu ra đúng kỳ vọng. |
| XSLT `document()` remote | URI HTTP/HTTPS lạ. | Runtime transform fail; **zero network request**. |
| XSLT extension function | Stylesheet thử gọi extension không cho phép. | Bị từ chối theo processor policy. |
| XSLT output path chưa duyệt | Request gợi ý đường dẫn file đích. | Ứng dụng không ghi file; Result do server kiểm soát. |
| Mất local import | Bỏ artifact/mapping được duyệt trong test. | Fail startup/build rõ ràng, không tự tải từ Internet. |
| Mixed provider | Thay XML provider được dùng bởi Spring-WS. | Feature/property support và test security vẫn pass. |
| XML quá lớn hoặc sâu | Payload test đã giới hạn và không nhạy cảm. | Bị từ chối theo size/depth/time limits. |
| SOAP parser khác validator | SOAP Envelope có DTD bị chặn. | Request không đi tới endpoint/side effect. |
| WS-Security failure | Message có chữ ký sai hoặc header bị sửa. | Không bypass security để xử lý transform/schema. |

Bảng là một **test plan**, không phải kết quả test của dự án này. Kiểm tra trên JDK/Spring-WS/provider/OS/network policy **đúng môi trường deployment**; các thư viện có thể dùng parser riêng và chọn default khác nhau.

### 11.2. Kiểm tra sơ đồ mạng: deny-by-default phải đo được

Một cách kiểm thử an toàn là chạy một **HTTP test server do nhóm sở hữu** trên loopback hoặc mạng test cách ly, với bộ đếm số request nhận được.

~~~mermaid
sequenceDiagram
    participant T as Unit/Integration Test
    participant P as XML Processor
    participant R as Approved Resolver
    participant H as Local HTTP Test Server

    T->>P: Compile XSD / transform XSLT
    P->>R: resolve external test URI
    alt Identifier được allowlist
        R-->>P: Bundled bytes từ classpath
        P-->>T: Kết quả đúng
    else Identifier không được duyệt
        R--xP: Reject
        P-->>T: Exception mong đợi
    end
    Note over H: HTTP request counter = 0
~~~

**Acceptance criterion:** sau negative test, test server đếm **0 request**. Chỉ assertion có exception là chưa đủ vì một parser có thể đã mở kết nối rồi mới ném lỗi do response sai. Test phải kiểm chứng **không có network side effect**; có thể kết hợp egress-blocking network namespace nếu môi trường test hỗ trợ.

Không sử dụng URL của dịch vụ thực, metadata endpoint thật hoặc file nhạy cảm để test. Chỉ dùng destination giả hoặc server do nhóm kiểm soát.

### 11.3. JUnit kiểm thử deny-all trên SchemaFactory

Ví dụ skeleton test dùng một schema import chưa được duyệt:

~~~java
import java.io.StringReader;
import javax.xml.XMLConstants;
import javax.xml.transform.stream.StreamSource;
import javax.xml.validation.SchemaFactory;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertThrows;

class SchemaExternalAccessTest {

    @Test
    void disallowsRemoteSchemaImport() throws Exception {
        String xsd = """
            <xs:schema
              xmlns:xs="http://www.w3.org/2001/XMLSchema"
              xmlns:remote="urn:example:remote:v1"
              targetNamespace="urn:example:test:v1">
              <xs:import namespace="urn:example:remote:v1"
                  schemaLocation="http://127.0.0.1:18081/blocked.xsd"/>
              <xs:element name="Root" type="remote:RemoteType"/>
            </xs:schema>
            """;

        SchemaFactory factory = SchemaFactory.newInstance(
            XMLConstants.W3C_XML_SCHEMA_NS_URI);

        factory.setFeature(
            XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        StreamSource source = new StreamSource(
            new StringReader(xsd));
        source.setSystemId("urn:test:root.xsd");

        // Phần tử Root tham chiếu type ở imported namespace.
        // Test integration còn phải assert HTTP hits = 0.
        assertThrows(
            org.xml.sax.SAXException.class,
            () -> factory.newSchema(source));
    }
}
~~~

**Giới hạn để tránh false-positive/false-negative:** ví dụ đã tham chiếu `remote:RemoteType` để tạo nhu cầu resolve import, nhưng `SAXException` vẫn có thể xảy ra vì **type chưa có** chứ không tự chứng minh kết nối bị chặn. Trong test thật, chạy HTTP test server có bộ đếm và assert **zero requests**; kiểm tra cả imports ở compile và `xsi:schemaLocation` ở validation runtime.

Nếu provider hành xử khác, **không viết `assertThrows` cứng rồi cho rằng code sai**: phân tích semantics thực tế, chọn negative fixture buộc đọc tài nguyên và kiểm tra kết nối không xảy ra.

### 11.4. Test XSLT phải có cả compile-time và runtime

Một stylesheet có `xsl:include href="https://example.test/blocked.xsl"` có thể fail khi gọi `newTemplates(...)`. Nhưng `document('https://example.test/blocked.xml')` có thể chỉ được gọi khi chạy `transform(...)`.

Vì vậy cần:

~~~text
Test 1: TransformerFactory.newTemplates(XSLT with external import)
        → blocked before transform

Test 2: Compile allowed XSLT with document() remote URI
        → run Transformer.transform(...)
        → blocked during execution

Test 3: Compile allowed XSLT + known local common.xsl
        → success, no network

Test 4: Run allowed XSLT + known local codebook.xml
        → output correct, no network
~~~

Phải xác minh **dữ liệu output chính xác**, không chỉ “không ném lỗi”. Nếu resolver mapping một file XSD/XSLT sai version nhưng hợp lệ về XML, service vẫn có thể xử lý sai nghiệp vụ.

### 11.5. MockWebServiceClient không bảo đảm mọi tầng an toàn

`MockWebServiceClient` kiểm thử Spring-WS endpoint/interceptor trong ApplicationContext. Nó hữu ích để xác minh:

- XSD validator từ chối payload sai.
- SOAP Fault được tạo đúng version/contract.
- JAXB endpoint không xử lý request bị chặn.
- Security interceptors từ chối header/token sai.
- Validation/transform không thay đổi response nghiệp vụ.

Nhưng **mock SOAP test không tự chứng minh toàn bộ HTTP/TLS, reverse proxy, Axiom/SAAJ parser cấu hình thực, external schema resolution hoặc network egress**. Cần integration tests khác kiểm chứng startup schema compilation, JAXP provider, HTTP connection denial và MTOM/streaming nếu có.

## 12. Một pipeline phòng vệ mẫu từ startup tới request

Thiết kế đầy đủ thường chia **startup/build-time** và **request-time**.

~~~mermaid
flowchart TD
    B["Build / CI"] --> C["Pinned XSD/XSLT artifacts và hashes"]
    C --> D["Compile Schema/Templates offline"]
    D --> E{"Chỉ resolve known IDs?"}
    E -- "Không" --> F["Fail build/startup"]
    E -- "Có" --> G["Deploy app với EAP deny + egress controls"]

    G --> H["SOAP request từ đối tác"]
    H --> I["HTTP size limits + TLS/security"]
    I --> J["Secure SOAP parser - no DTD/XXE"]
    J --> K["Spring-WS mapping + WS-Security"]
    K --> L["Validate XSD với trusted schema"]
    L --> M["Transform XSLT nếu cần, URIResolver allowlist"]
    M --> N["JAXB / business service"]
    N --> O["SOAP response/Fault"]
~~~

Sơ đồ mô tả một kiến trúc **khái niệm**. Thứ tự WS-Security, validation và transform cần được thiết kế phù hợp với chữ ký, schema version và interceptor chain thực tế; không mặc định transform trước hoặc sau xác minh chữ ký là an toàn trong mọi hợp đồng.

### 12.1. Checklist khởi động

Khi ứng dụng khởi động:

1. Xác minh XSD/XSLT có trong JAR/container image và đúng version/hash.
2. Tạo XML processors với **FSP + EAP deny-all** ở nơi hỗ trợ.
3. Đăng ký resolver/catalog fail-closed cho tập imports/includes được duyệt.
4. Compile Schema/Templates trước khi nhận traffic.
5. Fail startup nếu XSD/XSLT tham chiếu file/URL không thuộc bundle hoặc property bảo mật bị từ chối.
6. Kiểm tra provider class/version và mô hình parser thực tế của Spring-WS.
7. Xác minh cấu hình network egress và filesystem permissions.
8. Thực hiện health/readiness gate chỉ khi trusted contract artifacts đã compile thành công.

### 12.2. Checklist khi xử lý request

Khi server nhận SOAP request:

1. Giới hạn HTTP size, attachment size, timeout và concurrency.
2. Parse SOAP với DTD/external entities/XInclude bị hạn chế theo policy.
3. Xác thực transport và WS-Security theo hợp đồng.
4. Route endpoint và validate XML theo schema do server **đã chọn**.
5. Nếu có XSLT, chỉ dùng stylesheet đã duyệt, resolver allowlist và output do server kiểm soát.
6. Không tin `xsi:schemaLocation`/stylesheet URL/callback địa chỉ do client gửi để nạp tài nguyên.
7. Chặn lỗi và phân loại SOAP Fault an toàn, tránh ghi raw file paths/URLs/secrets.
8. Gắn correlation/trace IDs đã được kiểm soát để phục vụ chẩn đoán.
9. Không phát sinh side effects nghiệp vụ khi parser/validation/security thất bại.

### 12.3. Client outbound cũng cần bảo vệ

Một Spring-WS `WebServiceTemplate` có thể nhận XML từ đối tác hoặc dịch vụ ngoài qua HTTP. Dù client chủ động chọn URL server, XML response vẫn là **input chưa được tin cậy**; parser/unmarshaller/XSLT response adapter cần chính sách tương tự.

Đặc biệt, **mTLS hoặc WS-Security signature hợp lệ không tự bảo đảm mọi XSLT/XSD external reference an toàn**: chúng xác minh peer/message theo scope, không thay thế whitelist external resource resolution. Nếu client sử dụng `PayloadValidatingInterceptor` phía client hoặc custom transform trước JAXB, kiểm tra factory và resolver của đường đó riêng với server.

## 13. Troubleshooting: lỗi do chặn đúng và lỗi do cấu hình sai

| Triệu chứng | Nguyên nhân có thể | Điều tra/sửa đúng |
| --- | --- | --- |
| `ACCESS_EXTERNAL_SCHEMA` denied | XSD include/import chưa được map hoặc code dùng external location. | Xem schema closure, base/systemId và resolver allowlist; không bật `all`. |
| `ACCESS_EXTERNAL_STYLESHEET` denied | XSLT import/include/document() ngoài phạm vi. | Kiểm tra stylesheet package, URIResolver compile và runtime. |
| XML parser báo DOCTYPE không cho phép | Payload có DTD; policy SOAP không chấp nhận. | Từ chối input hoặc sửa đối tác gửi XML hợp lệ, không bật lại XXE. |
| XSD relative include lỗi dù có file | `StreamSource` thiếu `systemId` hoặc resource không được đóng gói. | Đặt base URI đúng, kiểm tra classpath/packaging/resolver. |
| Schema compile thành công ở dev, fail production | Dev có network/file khác, artifact thiếu file, JDK/provider khác. | Test offline, khóa dependencies, so JDK/classpath. |
| XSLT compile pass nhưng transform fail | `document()` chỉ chạy runtime và bị chặn. | Test URIResolver lúc transform, map local codebook hoặc bỏ call. |
| Đã đặt EAP nhưng vẫn thấy HTTP call | Resolver tự open URL, thư viện khác dùng HTTP client, provider khác. | Audit resolver, call stack, socket telemetry/egress policy. |
| WSDL GET chậm hoặc phụ thuộc Internet | Dynamic WSDL/CommonsXsdSchemaCollection import từ URL. | Bundle XSD; cấu hình Apache WS-Commons URIResolver hoặc static WSDL. |
| Spring-WS PayloadValidatingInterceptor sai schema | Import thiếu, schema version lẫn hoặc relative URI không resolve. | Kiểm tra XSD schema collection và full validation fixture. |
| XSLT request cho ra response sai | Version template hoặc import precedence thay đổi. | Pin XSLT và dependency, test output XML theo contract. |
| JVM flags không có tác dụng | Factory override hoặc custom resolver bypass EAP. | Kiểm tra precedence, source of XML factory và implementation. |
| StAX không hỗ trợ FSP | Dùng `XMLInputFactory` với API khác. | `SUPPORT_DTD=false`, external entities false và XMLResolver chặn. |
| XSLT báo extension function bị chặn | FSP/provider-specific security policy. | Loại bỏ extension hoặc chuyển trusted transform theo review; không tắt bảo vệ mù. |
| Sau upgrade Java có lỗi property | Provider/JDK version xử lý security flags khác. | Đọc JAXP guide của JDK thực tế, chạy negative tests. |
| SOAP Fault detail lộ file path | Exception raw bị expose. | Map lỗi an toàn, log có redaction/permissions. |
| MTOM lớn gây heap/disk spike | Thư viện buffer attachment hoặc thiếu limits. | Kiểm thử MIME/MTOM end-to-end; giới hạn kích thước/temp storage. |

**Quy trình debug khuyến nghị:**

~~~text
1. Xác định lỗi xảy ra khi build, startup, request hay transform runtime.
2. Ghi nhận JDK, XML provider, Spring-WS version và method đang gọi.
3. Xác định reference bị từ chối: DTD, XSD import/include, XSLT import/document().
4. So systemId/baseURI với allowlist/catalog và resource đóng gói.
5. Chạy positive test với resource đã duyệt: phải thành công offline.
6. Chạy negative test với local test URL: phải không có HTTP access.
7. Kiểm tra parser/SAX/DOM/StAX + SchemaFactory/Validator/TransformerFactory.
8. Xác nhận SOAP Fault/HTTP error đúng tầng và không lộ secrets.
9. Kiểm tra egress policy, size limits, log volume và side effects.
10. Chỉ sau khi có bằng chứng mới điều chỉnh whitelist theo thay đổi hợp đồng.
~~~

Không chữa bằng `ACCESS_EXTERNAL_SCHEMA="all"` hoặc `ACCESS_EXTERNAL_STYLESHEET="all"`, cũng không tắt WS-Security/XSD validation để tạm vượt lỗi. Những thay đổi đó thường làm mất ranh giới phòng vệ đáng lẽ cần giữ.

## 14. Bài tập tình huống có đáp án gợi ý

### Tình huống A — XSD import HTTPS làm startup thất bại

Đội phát triển dùng một XSD có:

~~~xml
<xs:import
    namespace="urn:example:payments:v1"
    schemaLocation="https://schemas.example.test/payments/v1/payments.xsd"/>
~~~

Khi bật `ACCESS_EXTERNAL_SCHEMA=""`, application không compile được schema. Một thành viên đề nghị đổi thành `"https"`.

**Câu hỏi:** có nên cho phép toàn bộ HTTPS để service khởi động?

**Đáp án:** Không. `https` là cho phép theo **giao thức**, không giới hạn host/path hay phiên bản. Cách phù hợp là **đóng gói XSD payments đã được duyệt**, map exact URI+namespace trong `LSResourceResolver` hoặc strict XML Catalog, compile offline và kiểm thử số outbound connections bằng 0.

### Tình huống B — XSLT compile thành công nhưng request lỗi sau khi deploy

Một stylesheet không có `xsl:import`, nên `TransformerFactory.newTemplates(...)` pass. Nhưng một nhánh transform chỉ chạy khi đơn hàng có loại nhất định, dùng:

~~~xml
<xsl:variable name="lookup"
              select="document('https://schemas.example.test/codebook.xml')"/>
~~~

Sau khi bật `ACCESS_EXTERNAL_STYLESHEET=""`, chỉ những request kích hoạt nhánh này mới thất bại.

**Đáp án:** `document()` có thể được gọi **ở runtime**, không phải compile-time. Cần map `codebook.xml` đã duyệt qua `URIResolver` hoặc bỏ external document dependency. Test compile và transform với dữ liệu kích hoạt mọi nhánh XSLT, đồng thời xác nhận không có network access.

### Tình huống C — Resolver tự động fallback về URL

Ứng dụng có resolver:

~~~text
if (knownSystemId) return classpath schema
else return URL.openStream(systemId)
~~~

JAXP có `ACCESS_EXTERNAL_SCHEMA=""`, nhưng test cho thấy server vẫn gửi request HTTP.

**Đáp án:** Resolver tự mở URL **nằm ngoài cơ chế fallback mà EAP có thể kiểm soát**. Đổi thành fail-closed khi ID lạ, không làm network fetch; đảm bảo map chỉ đến resources đã duyệt. Thêm negative test kiểm tra HTTP test server nhận **0** requests.

### Tình huống D — Client cung cấp xsi:schemaLocation

SOAP Body có `xsi:schemaLocation="urn:example:orders:v1 http://127.0.0.1:18081/schema.xsd"`. Một lập trình viên muốn lấy URL đó rồi gọi `SchemaFactory.newSchema(url)` để “validate đúng schema client chọn”.

**Đáp án:** Không cho client chọn schema làm nguồn tin cậy. Service biết hợp đồng `CreateOrder` từ XSD/WSDL do server công bố; dùng `Schema` đã compile từ bundle. Kiểm tra XML đầu vào theo parser policy và schema đã duyệt. Test không có outbound HTTP request tới `127.0.0.1`.

### Tình huống E — XML có DOCTYPE nhưng XSD validator vẫn bật

Ứng dụng có `PayloadValidatingInterceptor` và `Jaxb2Marshaller`. Nhóm cho rằng chỉ cần validate XSD thì XXE đã được xử lý.

**Đáp án:** **XSD validation không thay parser hardening**. Có thể XML bị đọc/resolve external entities trước khi validator làm việc. Cần cấu hình đúng SOAP message factory/parser (SAAJ/Axiom/StAX/SAX/DOM), chặn DTD/entities/XInclude phù hợp và giới hạn tài nguyên. Kiểm thử với request có DOCTYPE giả trong môi trường an toàn.

### Tình huống F — XSLT đã được ký nhưng chứa URL document()

Một XSLT release được ký và đóng gói từ CI; nó vẫn có `document('http://unreviewed.example.test/lookup.xml')`.

**Đáp án:** Chữ ký đảm bảo artifact không bị thay đổi ngoài ý muốn, **không chứng minh nội dung stylesheet không có hành vi nguy hiểm**. Artifact phải qua kiểm duyệt dependency, URIResolver allowlist, EAP và test offline. Nếu stylesheet cần tài nguyên động, thiết kế một **trusted data retrieval service** riêng với allowlist, authentication, timeout và caching, thay vì để XSLT tự gọi URL.

### Tình huống G — WSDL dynamic import khác production

Dev startup thành công vì XSD `common.xsd` nằm ở thư mục máy phát triển, nhưng production đóng gói JAR không có file đó. WSDL GET và SOAP validation lỗi khi không có Internet.

**Đáp án:** Đây là **sai packaging/dependency closure**. Đưa mọi XSD đã duyệt vào artifact, kiểm tra resources trong CI, cấu hình đúng resolver của `CommonsXsdSchemaCollection`, không mở `http/file` để bù. Có thể công bố **WSDL tĩnh** đã kiểm duyệt cho môi trường cần ổn định contract.

### Tình huống H — Chặn external XSD nhưng quên external XSLT

Team đặt:

~~~text
javax.xml.accessExternalSchema=
javax.xml.accessExternalDTD=
~~~

rồi tin rằng toàn bộ XML processing đã không còn truy cập mạng.

**Đáp án:** Còn thiếu `javax.xml.accessExternalStylesheet=` cho XSLT import/include/document(); đồng thời phải audit `TransformerFactory`, URIResolver và extension functions. Không có property nào tự quản lý mọi HTTP client hoặc output Result.

### Tình huống I — XML Signature hợp lệ nhưng stylesheet biến đổi Body

Một interceptor biến đổi Body bằng XSLT sau khi WS-Security xác minh signature; chương trình tiếp tục xử lý JAXB object đã transform.

**Đáp án:** Cần review **thứ tự tin cậy và ngữ nghĩa dữ liệu ký**. Verification có thể xác nhận Body trước transformation, nhưng business logic đang sử dụng dữ liệu sau transformation. Nếu transform được phép, phải chứng minh nó là thao tác tin cậy, có version/policy và không thay các điều kiện authorization. Không coi “đã verify signature” là chứng minh mọi kết quả XSLT đều được đối tác ký.

### Tình huống J — Bảo mật hoạt động trong mock nhưng fail với Axiom

Mock test dùng `StreamSource` đơn giản và pass. Production dùng Axiom streaming với payload caching bị tắt; interceptor transform/validate có thể tiêu thụ stream trước khi JAXB endpoint đọc.

**Đáp án:** Đây là **tương tác pipeline/streaming**, không nhất thiết do security property. Cần test với chính message factory và cấu hình streaming production; đảm bảo validation, security và transformation không đọc lại payload bất khả dụng. Không tắt XML security hoặc validation để sửa lỗi stream bị tiêu thụ.

## 15. Câu hỏi tự kiểm tra

1. `xs:include` và `xs:import` khác nhau chủ yếu ở namespace và schema resolution thế nào?
2. `xsi:schemaLocation` trong SOAP request có bắt server phải tải URL do client gửi không? Vì sao?
3. `XMLConstants.ACCESS_EXTERNAL_SCHEMA=""` chặn những đường nào, và đường nào có thể vẫn chạy qua custom resolver?
4. Vì sao `"file"` và `"https"` không tương đương allowlist thư mục/hostname?
5. Tại sao `FEATURE_SECURE_PROCESSING` hữu ích nhưng chưa đủ nếu không test provider/resolver?
6. `SchemaFactory#setResourceResolver` và `TransformerFactory#setURIResolver` giải quyết những loại tham chiếu nào?
7. Vì sao một resolver trả `null` hoặc tự mở URL tùy ý có thể làm thiết kế deny-by-default thất bại?
8. `xsl:include` và `document()` khác nhau về thời điểm access resource ra sao?
9. Có thể dùng `Templates` chung cho nhiều request không? Có nên dùng một `Transformer` hoặc `Validator` mutable cho nhiều thread không?
10. Khi đã chặn DTD ở DOM parser, tại sao còn phải bảo vệ `SchemaFactory` và `TransformerFactory`?
11. `PayloadValidatingInterceptor` ở server và `PayloadTransformingInterceptor` dùng các loại processor nào? Tại sao phải kiểm tra factory/provider nội bộ?
12. `CommonsXsdSchemaCollection#setUriResolver` có cùng interface với JAXP `LSResourceResolver` không?
13. Vì sao `CommonsXsdSchemaCollection#setInline(true)` không phải biện pháp chống SSRF?
14. Có cách nào chứng minh negative test **không tạo HTTP request** thay vì chỉ assert có exception?
15. Khi XML parser báo DTD bị chặn và SOAP client nhận Fault, có nên bật lại DTD để endpoint nhận request không?
16. Khi một schema đã duyệt bị thiếu khỏi JAR, biện pháp đúng là fail startup hay cho phép tải từ Internet?
17. Vì sao TLS/mTLS và WS-Security không thay thế việc chặn XSLT external resource access?
18. Cần những kiểm soát nào ngoài JAXP EAP để chống DoS, local file access và callback/SSRF?
19. Khi đổi JDK hoặc TransformerFactory provider, cần chạy lại nhóm test bảo mật nào?
20. Vì sao log đầy đủ `systemId`/URL có query string có thể làm lộ thông tin?

## 16. Checklist triển khai an toàn

| Hạng mục | Điều kiện đạt |
| --- | --- |
| Danh sách XML processors | Biết chính xác nơi tạo SAX/DOM/StAX, SchemaFactory, Validator, TransformerFactory và provider. |
| XSD contract pinned | Mọi XSD/import/include được đóng gói, version hóa và review. |
| Schema compilation offline | `ACCESS_EXTERNAL_DTD=""` và `ACCESS_EXTERNAL_SCHEMA=""` áp dụng cho JAXP provider liên quan. |
| LSResourceResolver/catalog | Chỉ map exact known IDs sang local bytes; không URL fallback. |
| Base URI/systemId | `StreamSource` có systemId hợp lý; relative references không phụ thuộc working dir tùy ý. |
| XSLT stylesheet pinned | Stylesheet chính và imports/includes/codebooks được duyệt, không nhận stylesheet tùy ý từ SOAP input. |
| TransformerFactory EAP | `ACCESS_EXTERNAL_DTD=""` và `ACCESS_EXTERNAL_STYLESHEET=""` trên factory khi hỗ trợ. |
| URIResolver | Deny-by-default; cùng policy cho compile và runtime `document()`. |
| XSLT extension controls | Extension functions được kiểm soát theo provider; không chạy untrusted stylesheet có quyền cao. |
| Secure parser | DTD/external entities/XInclude bị hạn chế, cùng memory/depth/input limits. |
| Validator isolation | `Schema` compiled trusted; `Validator` per request và thuộc tính security đúng. |
| Transformer isolation | `Templates` dùng lại hợp lý; `Transformer` per request và Result đích tin cậy. |
| Spring-WS validation | `PayloadValidatingInterceptor` dùng schema đúng và test import closure. |
| Spring-WS XSLT | `PayloadTransformingInterceptor`/custom transform không tự load URL ngoài. |
| WSDL/XSD publication | `CommonsXsdSchemaCollection`/static WSDL không phụ thuộc network không kiểm soát. |
| JAXB/contract tương thích | DTO từ XSD đã pin; parser input và unmarshalling được bảo vệ. |
| WS-Security và TLS | Signature/credential/certificate validation chạy đúng; XML transform không phá trust boundary. |
| Deny network test | Invalid XSD/XSLT/DTD gây error nhưng 0 outbound request tới test server. |
| Positive offline test | Approved imports/includes/document() vẫn hoạt động và output đúng XSD. |
| Error handling | SOAP Fault/log dùng mã lỗi an toàn; không lộ file path, token, raw XML. |
| Hạ tầng | Network egress policy, filesystem permissions, timeout, body/attachment limits. |
| CI/deployment | Fail build/startup nếu artifact thiếu hoặc provider từ chối security config. |
| Sau nâng cấp | Chạy lại test matrix với đúng JDK, Spring-WS, JAXB, XML/XSLT engine version. |

### 16.1. Quy tắc quyết định nhanh

~~~mermaid
flowchart TD
    A["XML cần tài nguyên ngoài?"] --> B{"Có được kiểm duyệt và pin version?"}
    B -- "Không" --> C["Không tự fetch: từ chối hoặc thiết kế lại"]
    B -- "Có" --> D{"Có thể đóng gói local?"}
    D -- "Có" --> E["Bundle + exact resolver/catalog + EAP deny"]
    D -- "Không" --> F["Trusted integration service riêng + network allowlist"]
    E --> G["Negative network test + positive offline test"]
    F --> G
    G --> H{"Compile, transform, security, JAXB đúng?"}
    H -- "Không" --> I["Fail startup/test, sửa contract/config"]
    H -- "Có" --> J["Deploy kèm monitoring, size limits, egress"]
~~~

**Khi nào cần thật sự lấy tài nguyên động?** Nếu dữ liệu tra cứu thay đổi thường xuyên, nên tạo **dịch vụ lấy dữ liệu được kiểm soát** ngoài XML parser, dùng URL allowlist, authentication, caching, timeout và quy trình xác minh dữ liệu. Sau đó truyền giá trị đã kiểm chứng vào business logic/transform như một input cụ thể. Không biến `schemaLocation` hoặc `document($url)` thành HTTP client tổng quát.

## 17. Tài liệu chuẩn và nguồn kiểm chứng

Tài liệu chính thức nên đối chiếu với phiên bản Java/Spring-WS đang dùng:

- **Oracle — [JAXP Security Guide (Java 17)](https://docs.oracle.com/en/java/javase/17/security/java-api-xml-processing-jaxp-security-guide.html)**: EAPs, FEATURE_SECURE_PROCESSING, resolver/catalog, limits và precedence.
- **Oracle — [JAXP Security Guide (Java 25)](https://docs.oracle.com/en/java/javase/25/security/java-api-xml-processing-jaxp-security-guide.html)**: các cập nhật về properties, XML processors, DTD và strict external access policy ở JDK mới.
- **Java SE 17 — [XMLConstants](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/XMLConstants.html)**: định nghĩa `ACCESS_EXTERNAL_DTD`, `ACCESS_EXTERNAL_SCHEMA` và `ACCESS_EXTERNAL_STYLESHEET`.
- **Java SE 17 — [SchemaFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/validation/SchemaFactory.html)**: `newSchema`, `setResourceResolver`, giới hạn external schema/DTD.
- **Java SE 17 — [Validator](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/validation/Validator.html)**: validator lifecycle, `setResourceResolver` và validation-time lookups.
- **Java SE 17 — [TransformerFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/transform/TransformerFactory.html)**: `setURIResolver`, `newTemplates`, các restrictions cho external stylesheet/document.
- **Spring Web Services — [Reference 4.1.4](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/)**: contract-first, `PayloadValidatingInterceptor`, `PayloadTransformingInterceptor`, `CommonsXsdSchemaCollection` và WSDL.
- **Spring Web Services — [AbstractValidatingInterceptor API 4.1.4](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/server/endpoint/interceptor/AbstractValidatingInterceptor.html)**: `setSchema`, `setSchemas`, `setXsdSchemaCollection`.
- **Spring Web Services — [CommonsXsdSchemaCollection API 4.1.x](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/xml/xsd/commons/CommonsXsdSchemaCollection.html)**: URIResolver riêng của WS-Commons, `setXsds` và `setInline`.
- **Spring Web Services — [PayloadTransformingInterceptor API 4.1.1](https://docs.spring.io/spring-ws/docs/4.1.1/api/org/springframework/ws/server/endpoint/interceptor/PayloadTransformingInterceptor.html)**: XSLT transform ở server interceptor.

Một số implementation-specific flags và defaults thay đổi theo Java/Spring-WS/provider version; **đừng áp dụng cấu hình từ một bản tài liệu mới lên JAR cũ mà không xác minh**.

### Ghi nhớ

- **XSD `xs:include`/`xs:import` và XSLT `xsl:include`/`xsl:import`/`document()` có thể khiến XML processor đọc tài nguyên ngoài**; parser chống XXE không tự kiểm soát hết những đường này.
- **JAXP EAP:** `ACCESS_EXTERNAL_DTD=""`, `ACCESS_EXTERNAL_SCHEMA=""` và `ACCESS_EXTERNAL_STYLESHEET=""` là các thiết lập cốt lõi để chặn automatic external lookups của provider. **FSP là bổ sung**, không thay kiểm thử thực tế.
- **Resolver/catalog phải fail-closed.** Một `LSResourceResolver` hoặc `URIResolver` tự mở URL chưa duyệt có thể **bypass mục tiêu của EAP**; hãy map exact known identifiers sang bytes đã đóng gói, không cho fallback mạng.
- **XSLT có hai thời điểm truy cập ngoài:** import/include lúc compile, `document()` lúc transform. Bảo vệ cả `TransformerFactory` và `Transformer`/resolver.
- **Spring-WS có nhiều XML processors** từ SOAP message factory, schema validation, XSLT interceptor, JAXB và WSDL generation. Cần kiểm tra từng implementation/provider, đặc biệt resolver riêng của Apache WS-Commons.
- **Không để client chọn schema hoặc stylesheet từ URL trong SOAP Body**; validate theo XSD/WSDL được server sở hữu. Không tắt validation hay WS-Security chỉ để sửa import lỗi.
- **Kiểm thử an toàn phải đo cả hành vi:** tài nguyên đã duyệt load offline thành công; tài nguyên chưa duyệt bị từ chối, **không có network/file access**, không phát sinh side effects nghiệp vụ. Kết hợp egress controls, permissions và resource limits.







