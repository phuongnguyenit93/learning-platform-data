# Tài nguyên cục bộ và xử lý XML khi không có mạng với XML Catalog (Java 9+)

## Mục tiêu

Sau bài này, bạn có thể giải thích vì sao một tài liệu XML nằm trên máy vẫn có thể khiến ứng dụng truy cập mạng, ánh xạ những tham chiếu ngoài sang tài nguyên cục bộ bằng **XML Catalog**, cấu hình JAXP trong Java 9 trở lên và kiểm thử chế độ **offline, fail-closed**. Nội dung sử dụng các API chuẩn `javax.xml.catalog` và `javax.xml.parsers` thuộc mô-đun `java.xml`, vẫn được hỗ trợ trong các JDK hiện đại.

## 1. Vì sao cần tài nguyên cục bộ?

Tài liệu XML có thể tham chiếu đến thành phần khác bằng địa chỉ mạng, chẳng hạn:

- DTD hoặc external entity qua `<!DOCTYPE ... SYSTEM "https://...">`;
- XSD qua `schemaLocation`, `xs:include`, `xs:import`;
- XSLT qua `xsl:include`, `xsl:import` hoặc hàm `document()`;
- XInclude nếu ứng dụng chủ động bật xử lý XInclude.

Nếu trình xử lý XML tìm tài nguyên tại địa chỉ gốc, việc phân tích, kiểm tra schema hoặc biến đổi tài liệu có thể thất bại khi mất mạng. Kết quả cũng có thể phụ thuộc vào nội dung trên máy chủ bên ngoài tại thời điểm chạy.

**XML Catalog** là tập quy tắc ánh xạ một định danh bên ngoài (system ID, public ID hoặc URI) sang tài nguyên khác, thường là bản sao cục bộ đã được kiểm soát. Catalog không tự tải hay tự tạo bản sao: ứng dụng phải cung cấp trước các DTD, XSD, XSLT hoặc XML phụ thuộc.

```text
XML / XSD / XSLT
      |
      v
Bộ xử lý JAXP của Java
      |
      v
XML Catalog: tra định danh ngoài
      |                         \
      | khớp                    \ không khớp, resolve=strict
      v                           v
DTD/XSD/XSLT cục bộ            Báo lỗi có kiểm soát
      |
      v
Phân tích / xác thực / biến đổi không cần tải tài nguyên từ mạng
```

Phân biệt hai khái niệm: **XML Catalog quyết định nơi phân giải tham chiếu**; **hạn chế truy cập ngoài của JAXP quyết định những giao thức nào được phép dùng nếu bộ xử lý muốn tự tải tài nguyên**. Cấu hình an toàn thường kết hợp cả hai.

## 2. Các thành phần hiện hành của XML Catalog

Từ Java 9, JDK cung cấp gói `javax.xml.catalog` trong `java.xml`, hỗ trợ chuẩn OASIS XML Catalog 1.1:

| Thành phần | Vai trò |
| --- | --- |
| `Catalog` | Tập mục ánh xạ bất biến, tra cứu theo định danh. |
| `CatalogFeatures` / `CatalogFeatures.Feature` | Cấu hình danh sách catalog và cách xử lý khi không khớp. |
| `CatalogManager` | Tạo `Catalog` hoặc `CatalogResolver`. |
| `CatalogResolver` | Bộ phân giải có thể dùng với SAX, StAX, DOM/Schema Validation và XSLT thông qua các giao diện resolver tương ứng. |

Một catalog XML dùng namespace chuẩn `urn:oasis:names:tc:entity:xmlns:xml:catalog`. Các mục thông dụng:

| Mục catalog | Phù hợp với | Ý nghĩa |
| --- | --- | --- |
| `<system systemId="..." uri="..."/>` | DTD / external entity có system ID | Ánh xạ chính xác system ID sang URI đích. |
| `<public publicId="..." uri="..."/>` | DTD có public ID | Ánh xạ public ID; quy tắc chọn system/public tuân thủ chuẩn Catalog. |
| `<uri name="..." uri="..."/>` | XSD include/import, XSLT include/import, tham chiếu URI | Ánh xạ chính xác một URI. |
| `<rewriteSystem .../>`, `<rewriteURI .../>` | Tập tài nguyên có tiền tố URI ổn định | Thay tiền tố định danh bằng tiền tố đích. |
| `<nextCatalog catalog="..."/>` | Tách catalog theo nhóm | Tra catalog bổ sung khi cần. |

Ví dụ `uri="local/note.dtd"` là đường dẫn **tương đối với vị trí của file catalog** (hoặc `xml:base` nếu được thiết lập), không mặc định tương đối với thư mục chạy Java. Định danh bên ngoài phải khớp đúng ký tự, giao thức và đường dẫn; `https://...` khác `http://...`.

## 3. Ví dụ chạy hoàn chỉnh: đọc XML và DTD hoàn toàn cục bộ

Ví dụ dùng một XML khai báo DTD tại địa chỉ HTTPS giả định. DTD thực nằm trong thư mục `local`. Chính DTD khai báo entity `offline`; nếu không tải được DTD, chương trình không thể tạo ra đầu ra mong đợi.

Tạo cấu trúc:

```text
offline-xml/
├── OfflineCatalogDemo.java
├── catalog.xml
├── note.xml
└── local/
    └── note.dtd
```

**File `catalog.xml`** — ánh xạ system ID từ tài liệu XML đến bản DTD đi kèm ứng dụng:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<catalog xmlns="urn:oasis:names:tc:entity:xmlns:xml:catalog">
    <system
        systemId="https://schemas.example.invalid/note.dtd"
        uri="local/note.dtd"/>
</catalog>
```

**File `local/note.dtd`** — tài nguyên cục bộ đã chuẩn bị trước:

```dtd
<!ELEMENT note (#PCDATA)>
<!ENTITY offline "Offline OK">
```

**File `note.xml`** — vẫn tham chiếu đến URL ngoài, không cần sửa URL này để chạy offline:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE note SYSTEM "https://schemas.example.invalid/note.dtd">
<note>&offline;</note>
```

**File `OfflineCatalogDemo.java`** — chương trình Java 17+ độc lập, dùng API chuẩn:

```java
import java.nio.file.Path;
import javax.xml.XMLConstants;
import javax.xml.catalog.CatalogFeatures;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Document;

public class OfflineCatalogDemo {
    public static void main(String[] args) throws Exception {
        Path catalogFile = Path.of("catalog.xml").toAbsolutePath();
        Path xmlFile = Path.of("note.xml").toAbsolutePath();

        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
        factory.setNamespaceAware(true);
        factory.setFeature(XMLConstants.USE_CATALOG, true);
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);

        // JAXP dùng Catalog để thay URL DTD bằng file cục bộ.
        factory.setAttribute(
                CatalogFeatures.Feature.FILES.getPropertyName(),
                catalogFile.toUri().toString());
        factory.setAttribute(
                CatalogFeatures.Feature.RESOLVE.getPropertyName(), "strict");

        // Không cho parser tự truy cập DTD/XSD bên ngoài.
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        Document document = factory.newDocumentBuilder()
                .parse(xmlFile.toFile());

        System.out.println(
                document.getDocumentElement().getTextContent().trim());
    }
}
```

Mở terminal tại thư mục `offline-xml` (đã cài JDK 17 trở lên):

```sh
javac -encoding UTF-8 OfflineCatalogDemo.java
java OfflineCatalogDemo
```

Đầu ra chính xác:

```text
Offline OK
```

**Giải thích kết quả:** JAXP gặp system ID `https://schemas.example.invalid/note.dtd` trong DOCTYPE; Catalog chỉ đến `local/note.dtd` và parser đọc khai báo `&offline;` từ file đó. `ACCESS_EXTERNAL_DTD=""` chặn đường truy cập bên ngoài nếu parser định tự tải DTD. Vì vậy ví dụ không yêu cầu DNS hay truy cập HTTP; đã kiểm chứng luồng chạy này trên OpenJDK 24, trong khi mã chỉ dùng API có từ Java 9 và cú pháp tương thích Java 17.

Các điểm cấu hình cần hiểu:

1. `Path.toUri().toString()` tạo URI tuyệt đối của catalog theo hệ điều hành; đừng truyền một đường dẫn tương đối tùy tiện cho `javax.xml.catalog.files`.
2. `XMLConstants.USE_CATALOG` là feature cho phép bộ xử lý dùng catalog (JDK mặc định bật; ví dụ đặt tường minh).
3. `CatalogFeatures.Feature.RESOLVE = "strict"` khiến tham chiếu không khớp bị báo lỗi thay vì âm thầm quay ra mạng.
4. `FEATURE_SECURE_PROCESSING` áp dụng giới hạn xử lý XML, còn `ACCESS_EXTERNAL_DTD` và `ACCESS_EXTERNAL_SCHEMA` khóa các đường tự truy cập tài nguyên ngoài.
5. `DocumentBuilderFactory` chỉ tạo parser; trong ứng dụng thật hãy giữ cấu hình cho đúng factory/processor thực sự đang đọc XML.

## 4. Dùng Catalog cho XSD, XSLT và nhiều tài nguyên

Catalog không giới hạn ở DTD. Với một XSD có phần phụ thuộc:

```xml
<xs:include xmlns:xs="http://www.w3.org/2001/XMLSchema"
            schemaLocation="https://schemas.example.invalid/xsd/common.xsd"/>
```

Có thể đặt `common.xsd` dưới `local/xsd/` và thêm mục sau vào catalog:

```xml
<uri name="https://schemas.example.invalid/xsd/common.xsd"
     uri="local/xsd/common.xsd"/>
```

Với `xsl:include href="https://schemas.example.invalid/xsl/common.xsl"`, dùng mục `uri` tương ứng tới file XSLT cục bộ. Khi nhiều URI có chung tiền tố đã kiểm soát, có thể dùng:

```xml
<rewriteURI uriStartString="https://schemas.example.invalid/xsd/"
            rewritePrefix="local/xsd/"/>
```

Các đoạn trong mục này là **mảnh cấu hình** để ghép vào phần thân catalog XML đang có, không phải mỗi đoạn là một file XML độc lập. Quy tắc chính xác thường dễ kiểm toán hơn quy tắc đổi cả tiền tố; chỉ dùng `rewriteURI` cho phạm vi URI đáng tin và bảo đảm thư mục đích đã có đủ tài nguyên.

Ứng dụng cần cấu hình Catalog tại đúng điểm JAXP xử lý tham chiếu:

| Công việc | Điểm cấu hình phổ biến trong JDK |
| --- | --- |
| DOM | `DocumentBuilderFactory.setAttribute(FILES, catalogUri)` hoặc `DocumentBuilder.setEntityResolver(...)` |
| SAX | `SAXParser.setProperty(FILES, catalogUri)` hoặc `XMLReader.setEntityResolver(...)` |
| StAX | `XMLInputFactory.setProperty(FILES, catalogUri)` hoặc `setXMLResolver(...)` |
| XSD validation | `SchemaFactory.setProperty(FILES, catalogUri)` hoặc `setResourceResolver(...)` |
| XSLT transform | `TransformerFactory.setAttribute(FILES, catalogUri)` hoặc `Transformer.setURIResolver(...)` |

Ở bảng trên, `FILES` là `CatalogFeatures.Feature.FILES.getPropertyName()` và `catalogUri` là URI tuyệt đối của catalog. Đây là các **điểm tích hợp minh họa**, không phải các câu lệnh có thể chạy độc lập; cần tạo factory/parser và áp dụng thuộc tính bảo mật phù hợp cho từng trường hợp. Catalog chỉ giúp tìm XSD; nó **không tự bật xác thực schema**. Muốn validate, vẫn phải dùng `SchemaFactory` / `Validator` hoặc cấu hình xác thực tương ứng.

Nếu cần chủ động tạo resolver thay vì tính năng Catalog mặc định của JAXP, API chuẩn có thể dùng như sau (giả sử `catalogUri` là một `java.net.URI` hợp lệ):

```java
CatalogResolver resolver = CatalogManager.catalogResolver(
        CatalogFeatures.builder()
                .with(CatalogFeatures.Feature.RESOLVE, "strict")
                .build(),
        catalogUri);
```

Đoạn này cần các import `javax.xml.catalog.CatalogManager`, `CatalogResolver` và `CatalogFeatures`. Gắn `resolver` vào `DocumentBuilder.setEntityResolver(resolver)` hoặc API resolver phù hợp của SAX/StAX/XSD/XSLT. Một custom resolver của ứng dụng có thể được ưu tiên hơn catalog mặc định; hãy kiểm tra thứ tự phân giải nếu vừa dùng resolver riêng vừa thiết lập `FILES`.

## 5. Cách cấu hình Catalog khi chạy ứng dụng

**Cấu hình trực tiếp trong Java** như ví dụ phần 3 phù hợp khi một thành phần cần tập tài nguyên riêng. Đây là lựa chọn rõ phạm vi, dễ kiểm thử và không phụ thuộc vào việc thiết lập global JVM properties quá muộn.

Với ứng dụng đang dùng bộ xử lý JAXP của JDK và muốn cấp cấu hình lúc khởi chạy, có thể dùng system properties:

```sh
java -Djavax.xml.catalog.files=file:///absolute/path/catalog.xml -Djavax.xml.catalog.resolve=strict YourApp
```

Đây là **mẫu lệnh cấu hình**, cần thay `YourApp` và URI bằng giá trị thật; chạy ứng dụng biên dịch sẵn và **không đồng thời ghi đè `FILES` trong Java** nếu muốn áp dụng giá trị từ command line. Trên Windows, dùng URI `file:///C:/path/to/catalog.xml` hoặc tạo URI bằng `Path.toUri()`. Danh sách nhiều catalog được ngăn cách bằng dấu chấm phẩy (`;`), theo đặc tả `CatalogFeatures.FILES`.

JAXP cũng hỗ trợ cấu hình qua `jaxp.properties` trong thư mục `conf` của JDK hoặc file cấu hình JAXP do ứng dụng chỉ định bằng `java.xml.config.file` ở các JDK hỗ trợ. Với cấu hình từ hệ thống, hãy đặt thuộc tính **trước khi khởi tạo factory JAXP đầu tiên**, vì thời điểm đọc/caching cấu hình không được bảo đảm có thể thay đổi giữa chừng.

| Thuộc tính | Giá trị hữu ích | Tác dụng |
| --- | --- | --- |
| `javax.xml.catalog.files` | `file:///.../catalog.xml` | Danh sách catalog bằng URI tuyệt đối. |
| `javax.xml.catalog.resolve` | `strict` | Không khớp thì ném `CatalogException` (mặc định của Catalog). |
| `javax.xml.catalog.resolve` | `continue` | Cho phép parser tiếp tục xử lý như không khớp, có thể phát sinh truy cập ngoài. |
| `javax.xml.catalog.resolve` | `ignore` | Bỏ qua tham chiếu ngoài không khớp; có thể khiến thông tin bị thiếu. |
| `javax.xml.useCatalog` | `true` | Cho phép dùng Catalog; mặc định bật ở JDK. |

Với yêu cầu offline nghiêm ngặt, `strict` là lựa chọn dễ kiểm chứng nhất. `continue` không phù hợp nếu hệ thống phải bảo đảm không phát sinh yêu cầu mạng. `ignore` chỉ nên dùng khi chủ đích nghiệp vụ chấp nhận bỏ qua tài nguyên phụ thuộc.

## 6. An toàn XML khi dùng tài nguyên cục bộ

**Không có mạng không đồng nghĩa với an toàn khỏi XML External Entity (XXE).** XML độc hại vẫn có thể gây lộ file cục bộ, tiêu tốn tài nguyên vì mở rộng entity hoặc kích hoạt hành vi mà ứng dụng không dự liệu.

Với tài liệu cần DTD/XSD đáng tin, nên áp dụng đồng thời:

- Chỉ đóng gói những tài nguyên đã được xem xét, khóa phiên bản và kiểm tra nguồn gốc; không trỏ catalog đến đường dẫn người dùng tùy ý cung cấp.
- Bật `XMLConstants.FEATURE_SECURE_PROCESSING` và đặt các giới hạn tài nguyên phù hợp với độ lớn tài liệu.
- Hạn chế truy cập ngoài, chẳng hạn `XMLConstants.ACCESS_EXTERNAL_DTD=""` và `ACCESS_EXTERNAL_SCHEMA=""` cho parser/validator; với XSLT sử dụng `XMLConstants.ACCESS_EXTERNAL_STYLESHEET=""` tại factory phù hợp.
- Giữ `resolve=strict` và kiểm thử trường hợp thiếu mapping; đừng tự mở `http`/`https` trong các thuộc tính `ACCESS_EXTERNAL_*` chỉ để chữa lỗi catalog.
- Không bật XInclude hoặc các tính năng phân giải tham chiếu ngoài khác nếu bài toán không cần. Nếu XML là dữ liệu không tin cậy và không cần DTD, cấu hình parser để từ chối DOCTYPE thay vì cố xử lý DTD qua catalog.

Lưu ý: các hạn chế `ACCESS_EXTERNAL_*` ngăn **truy cập ngoài do JAXP tự thực hiện**. Tài nguyên được cấp tường minh thông qua resolver/catalog đã tin cậy có cơ chế xử lý riêng; đây là lý do phải kiểm soát đường dẫn đích và đầu vào, chứ không chỉ dựa vào một cờ bảo mật.

## 7. Đóng gói để chạy offline trong dự án thật

1. **Thu thập đủ phụ thuộc:** từ XML chính, XSD gốc hoặc XSLT chính, lần theo các `import`/`include`/`DOCTYPE` để xác định mọi file cần thiết; catalog không giúp ích nếu file đích chưa có.
2. **Đặt tài nguyên ổn định:** lưu catalog cạnh cây `local/` được đóng gói trong image/container hoặc thư mục cấu hình chỉ đọc. Dùng URI tạo từ đường dẫn thật thay vì hard-code `C:\...` hay `/home/...`.
3. **Khóa phiên bản:** giữ đúng phiên bản DTD/XSD/XSLT mà tài liệu yêu cầu; cập nhật phải qua kiểm thử vì một bản schema mới có thể đổi nghĩa dữ liệu.
4. **Kiểm thử khi tách khỏi mạng:** chạy trong môi trường không có outbound network và kiểm tra parse/validate/transform hoàn thành. Dùng địa chỉ mẫu `example.invalid` trong thử nghiệm để dễ phát hiện fallback sai.
5. **Coi lỗi là tín hiệu cấu hình:** nếu tham chiếu không khớp hoặc file cục bộ mất, báo rõ lỗi và dừng bước xử lý bị ảnh hưởng. Tránh cơ chế tự tải lại trên mạng trừ khi ứng dụng có yêu cầu rõ ràng.

Nếu tài nguyên được đóng **bên trong JAR**, đừng mặc định chuyển `getResource(...).toURI()` thành `Path` để tìm file: URL dạng `jar:` không luôn là file thông thường trên filesystem. Có thể triển khai tài nguyên ra một thư mục chỉ đọc tại thời điểm triển khai, hoặc cung cấp resolver đọc từ classpath `InputStream` với chính sách cho phép rõ ràng. Phải thử trên đúng cách đóng gói và JAXP implementation dùng trong production.

## 8. Kiểm thử và xử lý lỗi

| Hiện tượng | Nguyên nhân thường gặp | Cách xác minh/sửa |
| --- | --- | --- |
| Parser cố truy cập `https://...` | Không chỉ định catalog, `USE_CATALOG=false`, `RESOLVE=continue` hoặc mapping không khớp | Kiểm tra URI của catalog, định danh hệ thống và giá trị các feature. |
| Báo không tìm thấy catalog | `FILES` là đường dẫn sai/không phải URI tuyệt đối, file không đọc được | In `catalogFile.toUri()`, kiểm tra quyền và vị trí triển khai. |
| Có mapping nhưng vẫn không tìm thấy DTD/XSD | `uri` trỏ sai file, nhầm base URI, sai chữ hoa/thường | Đối chiếu file dưới thư mục catalog và đường dẫn `xml:base` (nếu có). |
| Không khớp và ném `CatalogException` | `resolve=strict` hoạt động đúng, thiếu mục ánh xạ | Bổ sung tài nguyên/mapping đã được phê duyệt; không đổi sang `continue` để che lỗi. |
| Parse XML thành công nhưng validate lỗi | Mapping chỉ cung cấp tài nguyên; tài liệu không hợp schema hoặc chưa có đúng schema | Kiểm tra namespace, `schemaLocation`, nội dung XSD và quy trình `Validator`. |
| Hoạt động trong IDE nhưng lỗi khi chạy JAR/container | Đường dẫn tương đối, working directory hoặc tài nguyên đóng gói khác nhau | Tạo catalog URI từ vị trí triển khai thực tế; kiểm thử image/artifact đã đóng gói. |
| Có lỗi bảo mật `accessExternalDTD` / `accessExternalSchema` | Parser vẫn tìm cách mở URL ngoài, thường do mapping thiếu hoặc resolver khác | Giữ giới hạn truy cập, xác minh catalog và thứ tự custom resolver. |

**Bộ kiểm thử tối thiểu:**

- **Đường thành công:** giữ đủ bốn file ở mục 3, chặn mạng, biên dịch và chạy; đầu ra phải là `Offline OK`.
- **Thiếu mapping:** xóa tạm mục `<system>` trong bản sao catalog thử nghiệm rồi chạy; phải nhận lỗi, không được âm thầm tải URL.
- **Thiếu file cục bộ:** đổi tên bản DTD trong bản sao môi trường thử; phải nhận lỗi rõ, không bỏ qua hay tự fetch HTTP.
- **Kiểm thử triển khai:** chạy lại cùng trường hợp trong container/JAR với user và working directory thực tế, kiểm tra log/giám sát không có kết nối outbound bất ngờ.

## 9. Những điều dễ hiểu sai

- **Catalog không phải cache HTTP.** Nó là bảng ánh xạ định danh; dữ liệu phải có sẵn và được quản lý phiên bản.
- **URL trong XML không bắt buộc phải sửa thành `file:`.** Catalog giữ nguyên định danh logic và thay nguồn vật lý khi phân giải.
- **Không phải mọi URL của ứng dụng đều đi qua JAXP.** Các HTTP client hay thư viện tự tải resource ngoài cơ chế XML resolver sẽ cần biện pháp riêng.
- **`javax.xml.catalog` vẫn là API chuẩn của Java hiện đại.** Tiền tố `javax` của gói này không có nghĩa API đã lỗi thời; nó thuộc mô-đun chuẩn `java.xml`.
- **Catalog không tự xác thực tính hợp lệ của XML.** Nó giúp định vị DTD/XSD; parser hay validator vẫn phải được gọi và cấu hình đúng.
- **Chỉ bật `FEATURE_SECURE_PROCESSING` chưa đủ để bảo đảm không truy cập mạng.** Hãy đặt `ACCESS_EXTERNAL_*` và kiểm thử mất mạng thực tế.

## 10. Checklist áp dụng

- [ ] Xác định mọi DTD/XSD/XSLT/XML phụ thuộc và lưu bản cục bộ đã kiểm soát.
- [ ] Viết OASIS XML Catalog với đúng namespace và định danh `system`/`public`/`uri`.
- [ ] Cung cấp URI tuyệt đối cho `javax.xml.catalog.files` và xác minh đường dẫn tương đối trong catalog.
- [ ] Bật Catalog, chọn `resolve=strict`, áp dụng giới hạn JAXP phù hợp với nguồn XML.
- [ ] Chạy thành công khi hoàn toàn không có mạng; kiểm tra trường hợp mapping/file bị thiếu.
- [ ] Lặp lại kiểm thử trên đúng artifact đóng gói và cập nhật catalog có kiểm soát khi tài nguyên thay đổi.

**Tài liệu chuẩn để tra cứu thêm:**

- [Java SE 25 — `javax.xml.catalog` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/catalog/package-summary.html)
- [Java SE 25 — CatalogFeatures và ý nghĩa `FILES`/`RESOLVE`](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/catalog/CatalogFeatures.html)
- [Java SE 25 — JAXP Security Guide](https://docs.oracle.com/en/java/javase/25/security/java-api-xml-processing-jaxp-security-guide.html)
