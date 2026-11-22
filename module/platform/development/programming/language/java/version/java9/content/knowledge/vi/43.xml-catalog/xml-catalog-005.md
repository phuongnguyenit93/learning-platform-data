# Tích hợp XML Catalog với SAX, DOM, StAX, XSLT và XML Schema trong Java 9+

## 1. Vì sao cần tích hợp XML Catalog?

Một tài liệu XML, tệp XSD hoặc stylesheet XSLT có thể tham chiếu tài nguyên khác bằng URI, chẳng hạn DTD, external entity, `xs:include`, `xs:import` hoặc `xsl:include`. Nếu parser tự truy cập URI đó qua mạng, chương trình phụ thuộc vào kết nối, máy chủ bên ngoài và chính sách bảo mật của môi trường chạy.

**XML Catalog** là bảng ánh xạ định danh/URI sang tài nguyên đã biết, thường đóng gói cùng ứng dụng. Ví dụ tài liệu tham chiếu `https://example.invalid/note.dtd` nhưng catalog ánh xạ nó sang `dtd/note.dtd` trên đĩa. Parser sử dụng bản cục bộ mà không cần tải địa chỉ bên ngoài.

Java đã tích hợp API chuẩn `javax.xml.catalog` trong module `java.xml` từ Java 9; API này vẫn dùng được trên các JDK hiện đại. Không cần thư viện resolver bên thứ ba cho các trường hợp JAXP thông thường. XML Catalog giải quyết **vị trí tài nguyên**; nó không tự kiểm tra tính hợp lệ của XML/XSD và không thay thế các biện pháp phòng chống XXE.

Luồng xử lý:

```text
XML / XSD / XSLT có external reference
             |
       Bộ xử lý JAXP
             |
      CatalogResolver
             |
    Tìm system/public/uri
       /              \
     Có               Không
     |                  |
URI cục bộ       strict: báo lỗi
     |           continue: xử lý tiếp
Đọc tài nguyên    ignore: bỏ qua nếu hỗ trợ
```

## 2. Các thành phần và điểm nối tương ứng

- `CatalogFeatures`: cấu hình đường dẫn catalog, chính sách khớp và xử lý tham chiếu không tìm thấy.
- `CatalogManager.catalogResolver(...)`: tạo `CatalogResolver` từ một hoặc nhiều file catalog.
- `CatalogResolver` triển khai **bốn giao diện resolver hiện hành**: SAX `EntityResolver`, StAX `XMLResolver`, XSLT `URIResolver` và XML Schema `LSResourceResolver`. DOM dùng `EntityResolver` qua `DocumentBuilder`.

| Bộ xử lý | Điểm tích hợp trực tiếp | Loại tham chiếu điển hình |
| --- | --- | --- |
| SAX | `XMLReader.setEntityResolver(resolver)` | DTD, external entity |
| DOM | `DocumentBuilder.setEntityResolver(resolver)` | DTD, external entity khi dựng DOM |
| StAX | `XMLInputFactory.setXMLResolver(resolver)` | DTD/entity khi đọc luồng |
| XSLT | `TransformerFactory.setURIResolver(resolver)`; khi cần, `Transformer.setURIResolver(resolver)` | `xsl:import`, `xsl:include`, hàm `document()` |
| XML Schema (XSD) | `SchemaFactory.setResourceResolver(resolver)`; khi cần, `Validator.setResourceResolver(resolver)` | `xs:include`, `xs:import`, schema tham chiếu lúc validate |

**Chọn cách nối:** Tích hợp **trực tiếp** bằng một `CatalogResolver` thuận tiện khi chỉ muốn áp dụng cho các processor cụ thể. Cách **khai báo `javax.xml.catalog.files`** trên factory hoặc thuộc tính hệ thống thuận tiện nếu muốn JAXP tự sử dụng catalog; xem mục 5. Với transformer, đặt resolver lên `TransformerFactory` **trước** khi biên dịch stylesheet để xử lý `xsl:include`/`xsl:import`. Với XSD, đặt lên `SchemaFactory` **trước** `newSchema(...)`.

### Cú pháp catalog

Catalog XML dùng namespace `urn:oasis:names:tc:entity:xmlns:xml:catalog`. Các mục thông dụng:

- `<system systemId="..." uri="..."/>`: ánh xạ system identifier, thường dùng với DTD và external entity.
- `<public publicId="..." uri="..."/>`: ánh xạ public identifier khi tài liệu khai báo PUBLIC.
- `<uri name="..." uri="..."/>`: ánh xạ URI, thường dùng cho XSD, XSLT và tài nguyên liên quan.
- `<rewriteSystem>`, `<rewriteURI>` hoặc `<systemSuffix>`/`<uriSuffix>`: hữu ích khi cần xử lý có quy tắc nhiều URI, nhưng phải chọn tiền tố/hậu tố đủ cụ thể.

Resolver tìm các mục `system` thích hợp trước; sau đó có thể xét `public` theo `prefer`; cuối cùng xét `uri`. `uri` tương đối trong catalog được giải quyết theo vị trí file catalog hoặc `xml:base`, không theo working directory tùy ý. URI dùng làm khóa khớp phải đúng với URI mà processor yêu cầu; tham chiếu tương đối đôi khi được parser chuẩn hóa thành URI tuyệt đối.

## 3. Ví dụ hoàn chỉnh: cả năm bộ xử lý dùng một catalog, chạy offline

Ví dụ sau sử dụng API tiêu chuẩn của **Java 17+**, tương thích với tính năng XML Catalog có từ Java 9. URI `example.invalid` là địa chỉ minh họa cố ý không hoạt động: thành công của ví dụ chứng tỏ tham chiếu được ánh xạ sang tài nguyên cục bộ. Tệp XML có DTD chỉ nhằm thể hiện trường hợp tích hợp thực tế; với dữ liệu XML mới, hãy chọn XSD khi cần kiểm tra cấu trúc và kiểu.

Tạo cấu trúc thư mục:

```text
xml-catalog-demo/
├── catalog.xml
├── note.xml
├── CatalogDemo.java
├── dtd/
│   └── note.dtd
├── xsd/
│   ├── root.xsd
│   └── types.xsd
└── xsl/
    ├── main.xsl
    └── common.xsl
```

### 3.1. Khai báo ánh xạ `catalog.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<catalog xmlns="urn:oasis:names:tc:entity:xmlns:xml:catalog" prefer="public">
  <system systemId="https://example.invalid/note.dtd" uri="dtd/note.dtd"/>
  <uri name="https://example.invalid/types.xsd" uri="xsd/types.xsd"/>
  <uri name="https://example.invalid/common.xsl" uri="xsl/common.xsl"/>
</catalog>
```

Ánh xạ thứ nhất phục vụ SAX/DOM/StAX, ánh xạ thứ hai phục vụ XSD, ánh xạ thứ ba phục vụ XSLT. Cả ba URI đích đều tương đối so với `catalog.xml`.

### 3.2. Tài liệu XML và DTD cục bộ

**`note.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE note SYSTEM "https://example.invalid/note.dtd">
<note><text>&greet;</text></note>
```

**`dtd/note.dtd`**

```dtd
<!ELEMENT note (text)>
<!ELEMENT text (#PCDATA)>
<!ENTITY greet "Xin chào XML Catalog">
```

Khi bộ phân tích XML gặp `&greet;`, nó cần nội dung DTD. Resolver cung cấp `dtd/note.dtd`, qua đó xác định entity `greet` thành chuỗi trong kết quả.

### 3.3. Hai file XSD: `xs:include` cần catalog

**`xsd/root.xsd`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:include schemaLocation="https://example.invalid/types.xsd"/>
  <xs:element name="note">
    <xs:complexType>
      <xs:sequence><xs:element name="text" type="TextType"/></xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
```

**`xsd/types.xsd`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="TextType">
    <xs:restriction base="xs:string"><xs:minLength value="1"/></xs:restriction>
  </xs:simpleType>
</xs:schema>
```

`SchemaFactory` tải `types.xsd` thông qua ánh xạ catalog khi biên dịch `root.xsd`; sau đó `Validator` kiểm tra phần tử `note` và `text` theo `TextType`. Hai XSD ở đây không khai báo `targetNamespace`, đúng với quy tắc dùng `xs:include` giữa các schema không namespace.

### 3.4. Hai file XSLT: `xsl:include` cần catalog

**`xsl/main.xsl`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0">
  <xsl:include href="https://example.invalid/common.xsl"/>
  <xsl:output method="text" encoding="UTF-8"/>
  <xsl:template match="/"><xsl:call-template name="line"/></xsl:template>
</xsl:stylesheet>
```

**`xsl/common.xsl`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0">
  <xsl:template name="line"><xsl:value-of select="/note/text"/></xsl:template>
</xsl:stylesheet>
```

Khi `TransformerFactory.newTransformer(...)` biên dịch `main.xsl`, `URIResolver` ánh xạ URI trong `xsl:include` sang `xsl/common.xsl`. Ví dụ dùng XSLT 1.0, phạm vi được JAXP trong JDK hỗ trợ.

### 3.5. Chương trình Java đầy đủ `CatalogDemo.java`

```java
import java.io.InputStream;
import java.io.StringWriter;
import java.nio.file.Files;
import java.nio.file.Path;
import javax.xml.XMLConstants;
import javax.xml.catalog.CatalogFeatures;
import javax.xml.catalog.CatalogManager;
import javax.xml.catalog.CatalogResolver;
import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.parsers.SAXParserFactory;
import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLStreamConstants;
import javax.xml.stream.XMLStreamReader;
import javax.xml.transform.Transformer;
import javax.xml.transform.TransformerFactory;
import javax.xml.transform.dom.DOMSource;
import javax.xml.transform.stream.StreamResult;
import javax.xml.transform.stream.StreamSource;
import javax.xml.validation.Schema;
import javax.xml.validation.SchemaFactory;
import javax.xml.validation.Validator;
import org.w3c.dom.Document;
import org.xml.sax.XMLReader;
import org.xml.sax.helpers.DefaultHandler;

public class CatalogDemo {
    public static void main(String[] args) throws Exception {
        Path xml = Path.of("note.xml").toAbsolutePath();
        CatalogFeatures features = CatalogFeatures.builder()
                .with(CatalogFeatures.Feature.RESOLVE, "strict")
                .build();
        CatalogResolver resolver = CatalogManager.catalogResolver(
                features, Path.of("catalog.xml").toAbsolutePath().toUri());

        // SAX: nhận event và giải quyết external DTD qua EntityResolver.
        SAXParserFactory saxFactory = SAXParserFactory.newInstance();
        saxFactory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        XMLReader saxReader = saxFactory.newSAXParser().getXMLReader();
        saxReader.setEntityResolver(resolver);
        saxReader.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        StringBuilder saxText = new StringBuilder();
        saxReader.setContentHandler(new DefaultHandler() {
            @Override public void characters(char[] ch, int start, int length) {
                saxText.append(ch, start, length);
            }
        });
        saxReader.parse(xml.toUri().toString());
        System.out.println("SAX: " + saxText.toString().trim());

        // DOM: dựng cây và giải quyết DTD ngay khi parse().
        DocumentBuilderFactory domFactory = DocumentBuilderFactory.newInstance();
        domFactory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        domFactory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        DocumentBuilder builder = domFactory.newDocumentBuilder();
        builder.setEntityResolver(resolver);
        Document dom = builder.parse(xml.toFile());
        System.out.println("DOM: " + dom.getDocumentElement()
                .getElementsByTagName("text").item(0).getTextContent());

        // StAX: ví dụ có DTD đã biết; KHÔNG bật external entities cho XML lạ.
        XMLInputFactory staxFactory = XMLInputFactory.newFactory();
        staxFactory.setProperty(XMLInputFactory.SUPPORT_DTD, true);
        staxFactory.setProperty(XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, true);
        staxFactory.setProperty(XMLInputFactory.IS_REPLACING_ENTITY_REFERENCES, true);
        staxFactory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        staxFactory.setXMLResolver(resolver);
        StringBuilder staxText = new StringBuilder();
        try (InputStream in = Files.newInputStream(xml)) {
            XMLStreamReader stax = staxFactory.createXMLStreamReader(xml.toUri().toString(), in);
            try {
                while (stax.hasNext()) {
                    if (stax.next() == XMLStreamConstants.CHARACTERS) {
                        staxText.append(stax.getText());
                    }
                }
            } finally {
                stax.close();
            }
        }
        System.out.println("StAX: " + staxText.toString().trim());

        // XSLT: resolver phải được đặt trước khi biên dịch xsl:include.
        TransformerFactory xsltFactory = TransformerFactory.newInstance();
        xsltFactory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        xsltFactory.setAttribute(XMLConstants.ACCESS_EXTERNAL_STYLESHEET, "");
        xsltFactory.setURIResolver(resolver);
        Transformer transformer = xsltFactory.newTransformer(
                new StreamSource(Path.of("xsl/main.xsl").toFile()));
        StringWriter transformed = new StringWriter();
        transformer.transform(new DOMSource(dom), new StreamResult(transformed));
        System.out.println("XSLT: " + transformed.toString().trim());

        // XSD: resolver xử lý xs:include khi tạo Schema.
        SchemaFactory schemaFactory = SchemaFactory.newInstance(
                XMLConstants.W3C_XML_SCHEMA_NS_URI);
        schemaFactory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        schemaFactory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        schemaFactory.setResourceResolver(resolver);
        Schema schema = schemaFactory.newSchema(Path.of("xsd/root.xsd").toFile());
        Validator validator = schema.newValidator();
        validator.setResourceResolver(resolver);
        validator.validate(new DOMSource(dom));
        System.out.println("XSD: hợp lệ");
    }
}
```

Các lệnh chạy tại thư mục `xml-catalog-demo`:

```bash
javac -encoding UTF-8 CatalogDemo.java
java CatalogDemo
```

Kết quả chuẩn của bộ dữ liệu trên:

```text
SAX: Xin chào XML Catalog
DOM: Xin chào XML Catalog
StAX: Xin chào XML Catalog
XSLT: Xin chào XML Catalog
XSD: hợp lệ
```

Đã đối chiếu kết quả khi biên dịch và chạy trên JDK 24; mã chỉ dùng API có trong Java 17. Trong SAX, callback `characters(...)` có thể được gọi nhiều lần nên phải nối từng đoạn; DOM lấy text sau khi parser thay entity; StAX đọc các sự kiện `CHARACTERS`; XSLT nhận `DOMSource` đã phân tích sẵn; XSD validate cùng cây DOM. Cả năm bước dùng đúng một ánh xạ catalog.

## 4. Cơ chế tích hợp và lựa chọn API trong ứng dụng thực tế

### SAX và DOM

`XMLReader.setEntityResolver` và `DocumentBuilder.setEntityResolver` được gọi **trước** `parse(...)`. Resolver nhận `publicId`/`systemId` và trả về `InputSource` của bản cục bộ. SAX thích hợp với xử lý event trên dữ liệu lớn; DOM thích hợp khi cần truy cập/sửa cây tài liệu. Nếu dùng `SAXParser.parse(...)` với handler thay vì `XMLReader` trực tiếp, hãy bảo đảm resolver được gắn lên đúng parser/reader thực sự được dùng.

### StAX

`XMLInputFactory.setXMLResolver` gắn resolver cho parser dạng pull; StAX có thể truyền thêm `baseURI` và namespace nhưng CatalogResolver chủ yếu khớp định danh hệ thống. Phần ví dụ **chủ động bật hỗ trợ DTD và external entity cho file được kiểm soát** để chứng minh việc ánh xạ; cấu hình này **không thích hợp cho dữ liệu XML không tin cậy**. Khi không cần DTD/entity bên ngoài, tắt chúng (`SUPPORT_DTD=false` và `IS_SUPPORTING_EXTERNAL_ENTITIES=false`) thay vì cố phân giải.

### XSLT

`TransformerFactory.setURIResolver` xử lý tham chiếu khi biên dịch stylesheet (`xsl:include`, `xsl:import`). Nếu stylesheet còn gọi `document(...)` trong lúc thực thi, gắn resolver lên `Transformer` tương ứng nếu cần. `URIResolver` xử lý URI của stylesheet/tài nguyên XSLT; việc phân tích XML đầu vào là công việc riêng, nên ví dụ đưa vào `DOMSource` đã được DOM parser phân giải. Khi đầu vào là `StreamSource` chứa DTD, phải cấu hình cả bộ parser tương ứng hoặc chính sách catalog chung.

### XML Schema

`SchemaFactory.setResourceResolver` giải quyết `xs:include`/`xs:import` trong giai đoạn **tạo `Schema`**. `Validator.setResourceResolver` giải quyết thêm tài nguyên cần trong giai đoạn **validate**, tùy nguồn và cấu hình. Gắn resolver chỉ sau khi `newSchema(...)` sẽ quá muộn với import/include của chính file XSD. Đặt `namespaceAware=true` cho DOM nếu xử lý XML có namespace; đồng thời kiểm tra `targetNamespace`/`namespace` của các schema import/include đúng quy tắc W3C XML Schema.

### Chu kỳ sống và đa luồng

`CatalogResolver` có thể tái sử dụng để thống nhất ánh xạ giữa nhiều bước xử lý. Tuy nhiên không mặc định chia sẻ đối tượng parser, `DocumentBuilder`, `XMLStreamReader`, `Transformer` hay `Validator` đang chạy giữa nhiều thread; khởi tạo/cấu hình cho từng tác vụ theo hợp đồng thread-safety của provider. Đặt catalog và tài nguyên đi kèm trong gói triển khai, tạo URI tuyệt đối từ `Path.toUri()` để tránh lệ thuộc vào working directory.

## 5. Cách cấu hình JAXP tự sử dụng catalog, không cần tạo resolver thủ công

Khi dùng bộ xử lý JAXP chuẩn của JDK, có thể khai báo file catalog ngay trên factory. Ví dụ DOM:

```java
DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
factory.setAttribute(
    CatalogFeatures.Feature.FILES.getPropertyName(),
    Path.of("catalog.xml").toAbsolutePath().toUri().toString()
);
DocumentBuilder builder = factory.newDocumentBuilder();
// Các tham chiếu phù hợp sẽ được JAXP tra qua catalog.
```

Đoạn trên là mã minh họa cần import các lớp `javax.xml.parsers`, `javax.xml.catalog` và `java.nio.file`, rồi gọi `builder.parse(...)` trong chương trình của bạn. Với SAX cũng có thể đặt property `CatalogFeatures.Feature.FILES.getPropertyName()` trên `SAXParser`; với XSLT trên `TransformerFactory` và với XSD trên `SchemaFactory`/`Validator` theo API tương ứng.

Một lựa chọn phạm vi toàn tiến trình là đưa **URI tuyệt đối** của catalog qua tham số JVM (thay đường dẫn bằng URI của máy triển khai):

```bash
java -Djavax.xml.catalog.files=file:///opt/app/catalog.xml -Djavax.xml.catalog.resolve=strict CatalogDemo
```

`XMLConstants.USE_CATALOG` có giá trị mặc định `true` trên các JAXP processor của JDK; nếu ứng dụng đã tắt nó, phải bật lại. Cấu hình qua property chỉ có tác dụng khi catalog hợp lệ được cung cấp và processor dùng cơ chế catalog của JAXP. Cách dùng resolver thủ công ở mục 3 độc lập, rõ ràng hơn khi muốn một catalog riêng cho từng pipeline. Resolver tùy chỉnh đã đăng ký với processor được ưu tiên hơn resolver catalog tự động của JAXP.

## 6. Chế độ không tìm thấy URI và bảo mật

| `CatalogFeatures.Feature.RESOLVE` | Khi không tìm được entry | Cân nhắc |
| --- | --- | --- |
| `strict` | Ném `CatalogException` (có thể được API parser bọc vào ngoại lệ khác) | Nên chọn để phát hiện thiếu dependency và tránh fallback ngoài dự kiến |
| `continue` | Cho processor tiếp tục cơ chế phân giải mặc định | Có thể dẫn tới yêu cầu mạng hoặc truy cập file nếu không bị giới hạn |
| `ignore` | Cố bỏ qua tài nguyên với một số giao diện resolver | Có thể khiến dữ liệu/DTD bị bỏ thiếu; với `LSResourceResolver`, `ignore` hoạt động giống `continue` |

Nên dùng `strict` cùng danh sách ánh xạ được kiểm soát. Các thuộc tính giới hạn truy cập ngoài JAXP gồm:

- `XMLConstants.ACCESS_EXTERNAL_DTD`: kiểm soát giao thức đọc DTD và entity ngoài.
- `XMLConstants.ACCESS_EXTERNAL_SCHEMA`: kiểm soát tham chiếu schema ngoài.
- `XMLConstants.ACCESS_EXTERNAL_STYLESHEET`: kiểm soát tham chiếu stylesheet ngoài.

Giá trị `""` không cho phép bất kỳ giao thức truy cập **trực tiếp** nào; ví dụ đã đặt giá trị này trên các processor tương ứng. **Điểm rất quan trọng:** Khi resolver tùy chỉnh trả về nguồn **khác null**, giới hạn `ACCESS_EXTERNAL_*` có thể không còn chặn chính nguồn đó. Do vậy chỉ đưa file catalog đáng tin cậy vào ứng dụng, chỉ ánh xạ sang tài nguyên nội bộ được phép đọc, không chấp nhận catalog do người dùng lạ cung cấp, đồng thời chặn network ở cấp hệ thống khi yêu cầu môi trường offline nghiêm ngặt.

Các cài đặt an toàn phụ thuộc nguồn dữ liệu:

1. **XML không tin cậy, không cần DTD:** tắt xử lý DTD/external entity; không bật `IS_SUPPORTING_EXTERNAL_ENTITIES` chỉ để dùng catalog.
2. **XML đã biết cần DTD:** dùng catalog allowlist + `strict` và hạn chế truy cập ngoài; kiểm soát kích thước/số lượng entity để tránh tấn công khuếch đại.
3. **XSD/XSLT có import/include:** ánh xạ đúng URI, dùng `ACCESS_EXTERNAL_SCHEMA/STYLESHEET`, giới hạn quyền đọc file và xác minh checksum/nguồn của các bản schema/stylesheet được phân phối.

`XMLConstants.FEATURE_SECURE_PROCESSING` giúp bật giới hạn bảo mật JAXP nhưng **không thay thế** các cấu hình và kiểm tra trên. Đối với provider JAXP khác JDK mặc định, xác nhận các property/feature được hỗ trợ vì provider có thể ném ngoại lệ nếu không nhận dạng chúng.

## 7. Chẩn đoán lỗi thường gặp

| Dấu hiệu | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| `CatalogException` hoặc lỗi URI không tìm thấy | Key catalog không trùng `systemId`/`href`; sai đường dẫn catalog; thiếu entry | In/log URI thật mà processor yêu cầu; so sánh dạng tuyệt đối/tương đối; kiểm tra `xml:base` |
| Parser vẫn cố kết nối mạng | Resolver chưa gắn vào processor thực sự dùng; `RESOLVE=continue`; custom resolver trả `null` | Gắn resolver **trước** parse/compile; đổi sang `strict`, cấu hình `ACCESS_EXTERNAL_*` |
| SAX/DOM báo entity chưa định nghĩa | DTD không được nạp hoặc entry không khớp | Kiểm tra `DOCTYPE`, entry `system`, quyền đọc DTD cục bộ |
| StAX không thay `&greet;` | DTD/entity bị tắt, hoặc không thay entity references | Chỉ với XML tin cậy: kiểm tra `SUPPORT_DTD`, `IS_SUPPORTING_EXTERNAL_ENTITIES` và `IS_REPLACING_ENTITY_REFERENCES` |
| `xsl:include` vẫn lỗi dù đã set resolver | Set `URIResolver` trên `Transformer` sau `newTransformer(...)` | Đăng ký trên `TransformerFactory` trước khi biên dịch XSLT |
| `xs:include`/`xs:import` thất bại | Đặt resolver quá muộn; `namespace`/`targetNamespace` không hợp lệ | Đặt trên `SchemaFactory` trước `newSchema`; kiểm tra URI và namespace |
| Chạy IDE được, đóng gói JAR thì lỗi | URI `file:`/working directory thay đổi; file resource không được phân phối | Tính URI từ vị trí triển khai; đóng gói catalog và dependency cùng ứng dụng |

**Bài tập tự kiểm tra:** Đổi `uri` của entry `types.xsd` thành tên file không tồn tại: bước tạo `Schema` phải thất bại. Trả lại file gốc; đổi kiểu phần tử `text` trong XSD thành một kiểu không nhận chuỗi ví dụ để chứng minh `Validator` kiểm tra dữ liệu độc lập với việc catalog chỉ tìm tài nguyên. Cuối cùng thử một URI mới không có entry với `strict` để xác nhận pipeline không âm thầm truy cập ngoài.

## 8. Tài liệu chuẩn còn áp dụng

- Oracle Java SE 17: [`javax.xml.catalog`](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/catalog/package-summary.html), [`CatalogResolver`](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/catalog/CatalogResolver.html), [`CatalogFeatures`](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/catalog/CatalogFeatures.html).
- Oracle JDK: [Use Catalog with XML Processors](https://docs.oracle.com/en/java/javase/24/core/use-catalog-xml-processors.html).
- Oracle JDK: [Java API for XML Processing (JAXP) Security Guide](https://docs.oracle.com/en/java/javase/25/security/java-api-xml-processing-jaxp-security-guide.html).
