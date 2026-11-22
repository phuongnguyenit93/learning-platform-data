# Ánh xạ định danh XML tới tài nguyên do ứng dụng kiểm soát bằng XML Catalog (Java 9+)

## 1. Bài toán: XML tham chiếu tài nguyên ở ngoài tài liệu

Một tài liệu XML có thể nhắc tới DTD, thực thể ngoài (external entity), XSD, tệp XSLT hoặc tài liệu XML khác bằng định danh. Chẳng hạn:

```xml
<!DOCTYPE invoice SYSTEM "https://schemas.example.invalid/invoice.dtd">
<invoice>&message;</invoice>
```

Ở đây, `https://schemas.example.invalid/invoice.dtd` là **system identifier** (`systemId`). Nếu không có cơ chế giải quyết phù hợp, bộ xử lý XML có thể tìm cách truy cập địa chỉ đó. Với ứng dụng cần hoạt động ổn định, dùng tài nguyên đã kiểm duyệt hoặc chạy ngoại tuyến, ta muốn giữ nguyên định danh trong XML nhưng **thay nơi lấy nội dung thực tế** thành tệp do ứng dụng đóng gói và quản lý.

XML Catalog giải quyết bài toán này bằng một danh sách ánh xạ khai báo:

```text
XML tham chiếu định danh
  → SAX / DOM / StAX / Schema validator / XSLT transformer
  → CatalogResolver tra định danh trong catalog
  → URI tài nguyên đã được ứng dụng kiểm soát
  → bộ xử lý XML đọc tài nguyên thay thế
```

Ví dụ, mọi tài liệu dùng `https://schemas.example.invalid/invoice.dtd` được chuyển tới `resources/invoice.dtd` đi kèm ứng dụng. Bản thân tài liệu XML **không cần sửa**; thay đổi phiên bản hoặc vị trí tệp DTD được quản lý trong catalog và gói phát hành.

Điều này hữu ích cho ba mục tiêu: tính sẵn sàng (không phụ thuộc máy chủ từ xa), tính tái lập (cùng một phiên bản DTD/XSD/XSLT đã kiểm duyệt) và giảm bề mặt truy cập tài nguyên ngoài khi xử lý XML.

## 2. API chuẩn có từ Java 9 và vẫn dùng được hiện nay

Java 9 bổ sung package `javax.xml.catalog` trong module chuẩn `java.xml`, triển khai **OASIS XML Catalogs 1.1**. Đây là API có sẵn trong các JDK hiện đại, không cần thêm thư viện catalog bên thứ ba cho những tình huống JAXP tiêu chuẩn.

| Thành phần | Vai trò |
| --- | --- |
| `Catalog` | Biểu diễn tập quy tắc ánh xạ; đối tượng catalog đã tạo là bất biến. |
| `CatalogFeatures` | Cấu hình danh sách catalog, thứ tự ưu tiên, tải catalog bổ sung và cách xử lý khi không khớp. |
| `CatalogManager` | Tạo `Catalog` và `CatalogResolver`. |
| `CatalogResolver` | Tra catalog; đồng thời triển khai `EntityResolver` (SAX/DOM), `XMLResolver` (StAX), `LSResourceResolver` (XSD) và `URIResolver` (XSLT). |
| `XMLConstants.USE_CATALOG` | Cho phép bộ xử lý JAXP dùng catalog (mặc định là `true` với bộ xử lý JDK). |

Trường hợp ứng dụng dùng `module-info.java`, khai báo `requires java.xml;`. Ví dụ chạy với `javac`/`java` trên classpath ở phần thực hành không cần khai báo module.

Cần phân biệt **định danh cần tìm** và **địa chỉ được ánh xạ tới**:

- `systemId`: định danh hệ thống của DTD/thực thể ngoài; thường là URL hoặc URI.
- `publicId`: định danh công khai, chẳng hạn `-//Example//DTD Invoice 1.0//EN`, có thể đi kèm `systemId` trong `DOCTYPE PUBLIC`.
- URI/href: thường thấy ở `xsd:include`, `xsd:import`, `xsl:include`, `xsl:import` và một số nguồn tài nguyên của XSLT.
- URI đích: vị trí tài nguyên do ứng dụng kiểm soát, ví dụ `resources/invoice.dtd`; khi là đường dẫn tương đối, nó được giải quyết dựa vào URI của catalog hoặc `xml:base` thích hợp.

**XML Catalog không tự tải, kiểm duyệt hay cập nhật tài nguyên.** Ứng dụng phải chủ động đưa bản DTD/XSD/XSLT đáng tin cậy vào gói triển khai và bảo đảm URI đích thực sự đọc được.

## 3. Khai báo ánh xạ trong tệp XML Catalog

Tệp catalog dùng namespace chuẩn `urn:oasis:names:tc:entity:xmlns:xml:catalog`. Đây là ví dụ minh họa nhiều loại định danh (mỗi URI đích phải trỏ đến một tệp mà ứng dụng thật sự cung cấp):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<catalog xmlns="urn:oasis:names:tc:entity:xmlns:xml:catalog">
    <system
        systemId="https://schemas.example.invalid/invoice.dtd"
        uri="resources/invoice.dtd"/>

    <public
        publicId="-//Example//DTD Invoice 1.0//EN"
        uri="resources/invoice.dtd"/>

    <uri
        name="https://schemas.example.invalid/xsd/invoice-v1.xsd"
        uri="resources/invoice-v1.xsd"/>

    <uri
        name="https://schemas.example.invalid/xslt/common.xsl"
        uri="resources/common.xsl"/>
</catalog>
```

- `<system>` khớp `systemId` của DTD hay thực thể ngoài.
- `<public>` khớp `publicId`. Khi XML khai báo cả `PUBLIC` và `SYSTEM`, bộ phân giải vẫn ưu tiên thử ánh xạ `system` trước; thiết lập `prefer` quyết định việc có tra `public` sau khi `system` không khớp.
- `<uri>` khớp URI/href, phù hợp khi giải quyết XSD, XSLT, XInclude hoặc tài nguyên URI khác. Java CatalogResolver cũng có thể tra dạng `uri` cho một `systemId` chưa được ánh xạ.
- Các URI đích tương đối như `resources/invoice.dtd` dựa trên vị trí của chính tệp `catalog.xml`, **không mặc định dựa trên thư mục làm việc hiện tại**.

Đối với một nhóm URI dùng chung tiền tố, có thể dùng `rewriteURI` hoặc `rewriteSystem`; ví dụ:

```xml
<rewriteURI
    uriStartString="https://schemas.example.invalid/xsd/"
    rewritePrefix="resources/xsd/"/>
```

Khi gặp `https://schemas.example.invalid/xsd/customer.xsd`, quy tắc trên chuyển phần tiền tố thành `resources/xsd/` để trỏ tới tệp `resources/xsd/customer.xsd` (nếu có). Quy tắc tiền tố hữu ích khi có nhiều tài nguyên cùng một namespace, nhưng phải **giới hạn tiền tố đủ hẹp** để không ánh xạ nhầm URI khác. Ngoài ra còn có `systemSuffix`, `uriSuffix` và `nextCatalog`; chỉ dùng khi có nhu cầu quản lý cụ thể, vì ánh xạ chính xác dễ kiểm soát và kiểm thử hơn.

**Thứ tự tra cứu:** trong catalog hiện tại, resolver thử nhóm `system` (`system`, `rewriteSystem`, `systemSuffix`); nếu phù hợp với `prefer` thì xét `public`; tiếp theo là nhóm `uri` (`uri`, `rewriteURI`, `uriSuffix`). Sau đó mới xét các catalog được ủy quyền hoặc catalog kế tiếp nếu chưa khớp. Với các quy tắc tiền tố/hậu tố cùng loại, độ dài phần khớp cũng ảnh hưởng tới kết quả theo chuẩn. Không dựa vào thứ tự các dòng XML để đoán chắc quy tắc nào sẽ thắng.

## 4. Ví dụ hoàn chỉnh: ánh xạ DTD ra tệp của ứng dụng

Ví dụ sau chạy trực tiếp trên **Java 17+** (cũng sử dụng được trên các JDK mới hơn). Để dễ quan sát kết quả, DTD định nghĩa một thực thể `message`; XML tham chiếu đến URL giả dưới miền `.invalid`, còn catalog chuyển nó tới tệp nội bộ. Như vậy đầu ra chỉ xuất hiện khi DTD nội bộ thực sự được đọc.

Tạo thư mục và bốn tệp như sau:

```text
xml-catalog-demo/
├── CatalogDemo.java
├── catalog.xml
├── invoice.xml
└── resources/
    └── invoice.dtd
```

**Tệp `catalog.xml`:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<catalog xmlns="urn:oasis:names:tc:entity:xmlns:xml:catalog">
    <system systemId="https://schemas.example.invalid/invoice.dtd"
            uri="resources/invoice.dtd"/>
</catalog>
```

**Tệp `resources/invoice.dtd`:**

```dtd
<!ELEMENT invoice (#PCDATA)>
<!ENTITY message "Resolved via XML Catalog">
```

**Tệp `invoice.xml`:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE invoice SYSTEM "https://schemas.example.invalid/invoice.dtd">
<invoice>&message;</invoice>
```

**Tệp `CatalogDemo.java`:**

```java
import javax.xml.XMLConstants;
import javax.xml.catalog.CatalogFeatures;
import javax.xml.catalog.CatalogManager;
import javax.xml.catalog.CatalogResolver;
import javax.xml.parsers.DocumentBuilderFactory;
import java.nio.file.Path;
import org.w3c.dom.Document;

public class CatalogDemo {
    public static void main(String[] args) throws Exception {
        Path catalogFile = Path.of("catalog.xml").toAbsolutePath();

        CatalogFeatures features = CatalogFeatures.builder()
                .with(CatalogFeatures.Feature.RESOLVE, "strict")
                .build();

        CatalogResolver resolver =
                CatalogManager.catalogResolver(features, catalogFile.toUri());

        DocumentBuilderFactory factory =
                DocumentBuilderFactory.newInstance();

        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        var builder = factory.newDocumentBuilder();
        builder.setEntityResolver(resolver);

        Document document =
                builder.parse(Path.of("invoice.xml").toFile());

        System.out.println(
                document.getDocumentElement().getTextContent().trim()
        );
    }
}
```

Mở terminal tại thư mục `xml-catalog-demo` rồi chạy:

```bash
javac -encoding UTF-8 CatalogDemo.java
java CatalogDemo
```

Kết quả stdout chính xác:

```text
Resolved via XML Catalog
```

Giải thích lần lượt:

1. `Path.of("catalog.xml").toAbsolutePath().toUri()` tạo URI `file:` tuyệt đối của catalog; API cần URI catalog hợp lệ, không phải một chuỗi tên tệp tùy ý.
2. `CatalogFeatures.builder()` thiết lập `RESOLVE=strict` để định danh không tìm thấy ánh xạ sẽ gây lỗi, thay vì âm thầm tìm nguồn khác.
3. `CatalogManager.catalogResolver(...)` đọc catalog và xây dựng bộ phân giải.
4. `builder.setEntityResolver(resolver)` kết nối resolver với DOM. Khi gặp `SYSTEM "https://schemas.example.invalid/invoice.dtd"`, DOM dùng ánh xạ `system` tới `resources/invoice.dtd`.
5. Bộ phân tích đọc định nghĩa `message` từ DTD nội bộ; `getTextContent()` trả về `Resolved via XML Catalog`. Không cần truy cập địa chỉ `https://schemas.example.invalid/....`.
6. `ACCESS_EXTERNAL_DTD=""` không cho parser tự ý mở DTD ngoài theo cơ chế truy cập mặc định; nguồn đã được resolver chủ động cung cấp vẫn được dùng. `FEATURE_SECURE_PROCESSING` thêm các giới hạn xử lý XML, nhưng không thay thế quy tắc chặn truy cập ngoài.

Đây là **chương trình Java hoàn chỉnh**, không phải đoạn mã giả. Mẫu trên đã được biên dịch và chạy với OpenJDK 24; Java 17+ đủ các API và cú pháp mà ví dụ sử dụng.

## 5. Hai cách kết nối Catalog với JAXP

### 5.1. Gắn `CatalogResolver` trực tiếp (như ví dụ)

```java
CatalogResolver resolver = CatalogManager.catalogResolver(
        CatalogFeatures.defaults(), catalogFile.toUri());

var builder = DocumentBuilderFactory.newInstance()
        .newDocumentBuilder();
builder.setEntityResolver(resolver);
```

Đây là **đoạn mã minh họa**, giả sử `catalogFile` đã là `Path` hợp lệ. Ưu điểm là phạm vi cấu hình rõ ràng: resolver chỉ phục vụ bộ xử lý được gắn vào. Cũng có thể dùng cùng resolver ở API hỗ trợ giao diện tương ứng, ví dụ `XMLInputFactory.setXMLResolver`, `SchemaFactory.setResourceResolver` hay `Transformer.setURIResolver`.

### 5.2. Để bộ xử lý JDK dùng Catalog tự động

Đối với DOM, có thể đặt thuộc tính `FILES` trên factory, không cần tự tạo `CatalogResolver`:

```java
DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
factory.setAttribute(
        CatalogFeatures.Feature.FILES.getPropertyName(),
        catalogFile.toUri().toString()
);
factory.setAttribute(
        CatalogFeatures.Feature.RESOLVE.getPropertyName(),
        "strict"
);
var builder = factory.newDocumentBuilder();
```

Đây là **đoạn minh họa**, `catalogFile` là `Path` và `CatalogFeatures`, `DocumentBuilderFactory` phải được import. Khi JAXP xử lý tham chiếu ngoài và không có custom resolver giải quyết trước, processor JDK sẽ tra catalog đã cấu hình. `XMLConstants.USE_CATALOG` mặc định bật trong bộ xử lý của JDK; nếu trước đó đã tắt tính năng này thì cần bật lại.

Các điểm cấu hình tương ứng ở những API khác:

| Nhu cầu | Điểm gắn catalog |
| --- | --- |
| DOM | `DocumentBuilderFactory.setAttribute(FILES, catalogUri)` hoặc `DocumentBuilder.setEntityResolver(resolver)` |
| SAX | `SAXParser.setProperty(FILES, catalogUri)` hoặc `XMLReader.setEntityResolver(resolver)` |
| StAX | `XMLInputFactory.setProperty(FILES, catalogUri)` hoặc `setXMLResolver(resolver)` |
| XSD `include`/`import` | `SchemaFactory.setProperty(FILES, catalogUri)` hoặc `setResourceResolver(resolver)` |
| XSLT `include`/`import` | `TransformerFactory.setAttribute(FILES, catalogUri)` hoặc gắn `URIResolver` phù hợp |

`FILES` ở bảng là tên thuộc tính lấy từ `CatalogFeatures.Feature.FILES.getPropertyName()`. Một số thư viện XML bên thứ ba có thể có hành vi và cách cấu hình riêng; bảng này mô tả các bộ xử lý JAXP của JDK.

Khi đặt cấu hình cho cả JVM, có thể dùng tùy chọn khởi động (thay URI ví dụ bằng URI `file:` thực tế):

```bash
java -Djavax.xml.catalog.files=file:///opt/app/catalog.xml -Djavax.xml.catalog.resolve=strict CatalogDemo
```

Không bắt buộc dùng cấu hình toàn JVM; ở các ứng dụng có nhiều bộ xử lý với nhu cầu khác nhau, cấu hình riêng theo factory/processor dễ kiểm soát hơn. Giá trị `FILES` gồm nhiều URI catalog tuyệt đối thì phân tách bằng dấu chấm phẩy (`;`), theo mô tả của API; không dùng dấu phẩy.

## 6. Các tùy chọn ảnh hưởng trực tiếp tới ánh xạ

| `CatalogFeatures.Feature` | Giá trị đáng quan tâm | Ý nghĩa thực tế |
| --- | --- | --- |
| `FILES` | URI catalog tuyệt đối, có thể nhiều URI cách nhau bằng `;` | Nguồn danh sách quy tắc. URI đầu là catalog chính. |
| `PREFER` | `public` (mặc định), `system` | `system` luôn được thử trước; `public` cho phép xét `publicId` khi `systemId` không khớp. Với `system`, không xét public nếu có system ID. |
| `DEFER` | `true` (mặc định), `false` | Trì hoãn đọc các catalog bổ sung tới khi cần hoặc tải sớm; không quyết định bản thân URI đích là đáng tin hay không. |
| `RESOLVE` | `strict` (mặc định), `continue`, `ignore` | Cách phản ứng khi không tìm được ánh xạ. |

Đặc biệt với `RESOLVE`:

- `strict`: báo `CatalogException` khi không tìm được ánh xạ; phù hợp khi danh sách tài nguyên được phép phải được quản lý chặt.
- `continue`: trả quyền xử lý lại cho processor theo cơ chế mặc định. Nếu không kèm hạn chế truy cập ngoài, xử lý có thể tìm tới mạng hoặc tệp ngoài ý muốn.
- `ignore`: tùy API, có thể bỏ qua tham chiếu (như SAX) hoặc có hiệu lực gần giống `continue` (như StAX/LSResourceResolver). Không coi `ignore` là hàng rào bảo mật áp dụng giống nhau cho mọi parser.

**Lưu ý về mức ưu tiên cấu hình:** thiết lập trực tiếp trên factory/processor thường ưu tiên hơn system property và tệp cấu hình JAXP; thuộc tính khai báo ngay trong catalog hoặc `group` có quy tắc ưu tiên riêng theo chuẩn/API. Vì vậy nên giữ cấu hình tập trung, tránh cùng lúc đặt các giá trị mâu thuẫn ở nhiều nguồn.

## 7. Thiết kế an toàn với tài nguyên do ứng dụng kiểm soát

Catalog là **cơ chế ánh xạ**, không phải bộ lọc an toàn hoàn chỉnh. Với XML từ nguồn không tin cậy, cần xác định từ đầu có thực sự cần DTD/thực thể ngoài hay không.

- **Không cần DTD:** vô hiệu hóa xử lý `DOCTYPE` hoặc external entities bằng cấu hình parser phù hợp. Trong trường hợp đó catalog cho DTD không cần được sử dụng.
- **Cần một tập DTD/XSD/XSLT đã duyệt:** giữ tài nguyên trong artifact/thư mục được kiểm soát phiên bản, khai báo ánh xạ chính xác, dùng `RESOLVE=strict` và chặn truy cập ngoài không được phép.
- **Giới hạn kênh truy cập ngoài:** trên DOM/SAX, cân nhắc `XMLConstants.ACCESS_EXTERNAL_DTD`; với validation dùng thêm `ACCESS_EXTERNAL_SCHEMA`; với XSLT dùng `ACCESS_EXTERNAL_STYLESHEET`. Giá trị chuỗi rỗng cấm các protocol mặc định cho loại tài nguyên tương ứng. Kiểm thử thực tế vì việc gắn resolver thủ công có thể cung cấp nguồn ngoài cơ chế hạn chế protocol.
- **Giới hạn tài nguyên xử lý:** bật `FEATURE_SECURE_PROCESSING` và cấu hình ngưỡng xử lý thực thể/kích cỡ phù hợp; một DTD nằm trong catalog nhưng chứa cấu trúc gây bùng nổ thực thể vẫn có thể nguy hiểm.
- **Kiểm soát URI đích:** chỉ ánh xạ tới thư mục, phiên bản và tệp đáng tin. Tránh dùng các quy tắc `rewrite` quá rộng; không dựng catalog từ đầu vào người dùng rồi cho phép nó trỏ tùy ý tới `file:`, `http:` hay `jar:`.
- **Đóng gói:** `Path.of("catalog.xml")` trong ví dụ giả định tệp nằm trên filesystem. Khi đóng gói trong JAR/container, phải lấy đúng URI có protocol được bộ xử lý hỗ trợ và bảo đảm các URI đích tương đối thật sự truy cập được; không mặc nhiên coi tài nguyên trong JAR là một `Path` trên đĩa.

Một thử nghiệm an toàn quan trọng: thay `systemId` trong `invoice.xml` bằng một URL khác không có trong catalog. Với `RESOLVE=strict`, việc phân tích phải **thất bại**; không được tự động tải URL mới. Đây là kiểm thử “fail closed” của chính sách ánh xạ.

## 8. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xác minh / xử lý |
| --- | --- | --- |
| `CatalogException`, không thấy ánh xạ | `systemId`/`publicId`/URI đầu vào không khớp chính xác; sai `prefer` | In/log định danh parser thực sự yêu cầu; đối chiếu với `systemId`/`publicId`/`name` trong catalog. |
| URI tương đối không khớp | Parser đã chuẩn hóa tham chiếu theo base URI thành URI tuyệt đối | Khai báo URI thực tế hoặc dùng `systemSuffix`/`uriSuffix` có phạm vi rõ ràng. |
| Tìm được quy tắc nhưng không đọc được tệp | `uri` đích tương đối với vị trí catalog, hoặc tệp thiếu khi đóng gói | Kiểm tra URI đích sau giải quyết, quyền đọc tệp và cấu trúc artifact. |
| Parser vẫn truy cập mạng | Đang để `continue`, thiếu ánh xạ, catalog chưa bật, hoặc custom resolver trả về `null` | Xác nhận cấu hình catalog; dùng `strict` và các thuộc tính `ACCESS_EXTERNAL_*` thích hợp. |
| Catalog không được sử dụng | `XMLConstants.USE_CATALOG=false`, sai namespace, dùng parser khác hoặc custom resolver xử lý trước | Kiểm tra bộ xử lý thực tế, namespace và thứ tự resolver. |
| XML bị lỗi sau khi ánh xạ | DTD/XSD/XSLT nội bộ không tương thích tài liệu hoặc giới hạn xử lý được đặt quá chặt | Cố định phiên bản tài nguyên, kiểm tra nội dung và đọc lỗi parser chi tiết. |

Khi cần debug, nên bắt đầu bằng **một catalog, một định danh và `strict`**; chỉ mở rộng sang nhiều catalog hoặc quy tắc tiền tố sau khi ánh xạ cơ bản chạy đúng. Không bỏ tạm cơ chế kiểm soát truy cập ngoài trên môi trường xử lý dữ liệu không tin cậy.

## 9. Tình huống áp dụng và điều cần ghi nhớ

Giả sử ứng dụng đọc hóa đơn XML của đối tác. Đối tác gửi tài liệu có `DOCTYPE SYSTEM "https://schemas.example.invalid/invoice.dtd"`. DTD này đã được nhóm phát triển kiểm duyệt và lưu thành `resources/invoice.dtd` theo một phiên bản cố định. Catalog giữ một quy tắc `system` từ định danh của đối tác sang tệp nội bộ; parser có resolver được cấu hình, đồng thời không được truy cập DTD tùy ý. Khi đối tác thay định danh hoặc chuyển sang phiên bản DTD mới, nhóm phát triển cập nhật catalog, tệp được duyệt và kiểm thử cùng bản phát hành. Dữ liệu XML vẫn giữ định danh chuẩn mà không buộc phải kết nối Internet.

Hãy tự kiểm tra ba câu hỏi: (1) parser yêu cầu **định danh nào**, sau khi tính base URI? (2) catalog chuyển định danh đó tới **tệp nào** và ai quản lý phiên bản tệp? (3) nếu **không có ánh xạ**, ứng dụng báo lỗi hay có đường truy cập ngoài nào còn mở? Trả lời chính xác cả ba mới chứng tỏ việc ánh xạ đang nằm trong quyền kiểm soát của ứng dụng.

## Tài liệu tham khảo chính thức

- Oracle Java SE Core Libraries — [XML Catalog API](https://docs.oracle.com/en/java/javase/25/core/xml-catalog-api1.html) và [Use Catalog with XML Processors](https://docs.oracle.com/en/java/javase/25/core/use-catalog-xml-processors.html).
- Java SE API — [CatalogFeatures](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/catalog/CatalogFeatures.html), [CatalogResolver](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/catalog/CatalogResolver.html), [javax.xml.catalog (JDK 26)](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/catalog/package-summary.html).
- Oracle — [JAXP Security Guide](https://docs.oracle.com/en/java/javase/25/security/java-api-xml-processing-jaxp-security-guide.html).