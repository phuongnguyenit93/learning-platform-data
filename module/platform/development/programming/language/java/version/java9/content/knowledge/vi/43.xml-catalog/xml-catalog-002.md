# XML Catalog trong Java: `Catalog`, `CatalogManager` và `CatalogResolver`

**Phạm vi:** Java 9 trở lên, dùng API chuẩn `javax.xml.catalog` của module `java.xml` (vẫn được hỗ trợ trên các JDK hiện hành). Bài này tập trung vào cách ánh xạ tài nguyên XML bên ngoài sang tài nguyên được kiểm soát, tạo catalog và gắn resolver vào bộ xử lý XML của Java.

## 1. Vì sao cần XML Catalog?

Một tài liệu XML, DTD, XSD hoặc stylesheet có thể chứa tham chiếu đến tài nguyên khác bằng URI:

```xml
<!DOCTYPE article SYSTEM "https://example.invalid/dtd/article.dtd">
```

Nếu bộ xử lý XML cố tải URL này trực tiếp, ứng dụng có thể phụ thuộc vào mạng, bị lỗi khi endpoint không khả dụng, gặp khác biệt giữa các môi trường hoặc vô tình truy cập tài nguyên ngoài ý muốn. **XML Catalog** là tệp XML khai báo một bảng tra cứu: khi gặp một định danh bên ngoài, bộ xử lý sử dụng URI đích do catalog chỉ định, thường là bản sao được đóng gói cục bộ.

```text
XML -> external systemId/URI
    -> CatalogResolver tra cứu Catalog
    -> URI đã ánh xạ (ví dụ file:///.../article.dtd)
    -> bộ xử lý XML sử dụng tài nguyên tương ứng
```

Catalog giải quyết việc **xác định vị trí tài nguyên**; nó không tự phân tích cú pháp XML, không thay thế kiểm tra hợp lệ bằng XSD và cũng không tự bảo đảm an toàn trước mọi kiểu tấn công XML. Công dụng vẫn thiết thực trong hệ thống tích hợp XML, kiểm thử chạy offline, schema import/include và XSLT có các tham chiếu ngoài.

## 2. Vai trò của các API

| Thành phần | Vai trò chính | Cách dùng |
| --- | --- | --- |
| `Catalog` | Đại diện cho tập quy tắc ánh xạ; đối tượng catalog sau khi tạo là bất biến. | `matchSystem(id)`, `matchPublic(id)`, `matchURI(uri)` trả URI đích dạng `String` hoặc `null` nếu không tìm thấy trong phạm vi tra cứu tương ứng. |
| `CatalogManager` | Lớp tiện ích `final`, cung cấp các phương thức `static` để tạo catalog/resolver. | `catalog(features, uris...)`, `catalogResolver(catalog)`, `catalogResolver(features, uris...)`. |
| `CatalogResolver` | Bộ phân giải áp dụng các mục catalog cho tham chiếu mà XML processor đang xử lý. | Tạo qua `CatalogManager`, sau đó gắn vào DOM/SAX, StAX, Schema Validation hoặc XSLT. |
| `CatalogFeatures` | Cấu hình cách đọc và xử lý catalog. | `defaults()` hoặc `builder().with(Feature.RESOLVE, "strict").build()`. |

`CatalogResolver` đồng thời mở rộng bốn giao diện chuẩn: SAX `EntityResolver`, StAX `XMLResolver`, DOM LS `LSResourceResolver` (thường dùng với XSD) và XSLT `URIResolver`. Vì vậy, **một resolver** có thể được gắn vào nhiều loại XML processor phù hợp mà không phải tự viết bốn bộ tra cứu riêng. Các API này ở package `javax.xml.catalog` dù ứng dụng sử dụng Java hiện đại; không cần thư viện Maven/Gradle bổ sung khi chạy với JDK tiêu chuẩn.

### Mối quan hệ cần nhớ

```java
CatalogFeatures features = CatalogFeatures.builder()
        .with(CatalogFeatures.Feature.RESOLVE, "strict")
        .build();

Catalog catalog = CatalogManager.catalog(features, catalogFileUri);
CatalogResolver resolver = CatalogManager.catalogResolver(catalog);

// Cách viết gọn khi không cần giữ biến Catalog:
// CatalogResolver resolver = CatalogManager.catalogResolver(features, catalogFileUri);
```

Đây là **đoạn mã minh họa**, giả sử biến `catalogFileUri` đã chứa `java.net.URI` tuyệt đối hợp lệ trỏ đến file XML Catalog. Ví dụ chạy đầy đủ ở mục 4.

## 3. Cấu trúc tệp OASIS XML Catalog

Java hỗ trợ **OASIS XML Catalogs 1.1**. Tệp cần phần tử gốc `catalog` cùng namespace chính xác:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<catalog xmlns="urn:oasis:names:tc:entity:xmlns:xml:catalog"
         prefer="public">
    <system
        systemId="https://example.invalid/dtd/article.dtd"
        uri="article.dtd"/>
    <public
        publicId="-//EXAMPLE//DTD ARTICLE 1.0//EN"
        uri="article.dtd"/>
    <uri
        name="https://schemas.example.invalid/common.xsd"
        uri="schemas/common.xsd"/>
</catalog>
```

- **`system`** ánh xạ một `systemId`, thường được dùng để tìm DTD hoặc external entity.
- **`public`** ánh xạ `publicId` của một thực thể công khai; chỉ có ích khi tài liệu tham chiếu có định danh tương ứng.
- **`uri`** ánh xạ một URI tài nguyên, hữu ích cho XSD `import`/`include`, XInclude, XSLT `include`/`import`, v.v.
- Giá trị `uri="article.dtd"` và `uri="schemas/common.xsd"` là **URI tương đối theo vị trí catalog** (hoặc theo `xml:base` nếu được khai báo), không phải đường dẫn tương đối tùy ý theo working directory của ứng dụng. Tệp đích phải tồn tại.
- `prefer="public"` cho phép xét `public` khi không khớp mục `system`; **mục `system` khớp vẫn được ưu tiên trước**. Không hiểu nhầm `prefer="public"` là bỏ qua `system`.

Khi có nhiều ánh xạ, dùng mục chính xác (`system`, `public`, `uri`) nếu có thể để dễ kiểm soát. Với hệ thống nhiều tệp, XML Catalog còn có `rewriteSystem`, `systemSuffix`, `rewriteURI`, `uriSuffix`, các mục `delegate*` và `nextCatalog`. Ví dụ:

```xml
<systemSuffix systemIdSuffix="/schemas/customer.dtd"
              uri="dtd/customer.dtd"/>
<nextCatalog catalog="other-catalog.xml"/>
```

`systemSuffix` hữu ích khi phần đầu của `systemId` thay đổi theo môi trường; `nextCatalog` nối đến một tệp catalog khác. Quy tắc phạm vi rộng có thể khớp nhầm tài nguyên, vì vậy chỉ áp dụng khi thật sự cần. Trong `Catalog`, các phương thức `matchSystem`/`matchPublic`/`matchURI` chủ yếu tra mục thuộc loại tương ứng; `CatalogResolver` thực hiện quy trình tìm kiếm thích hợp trên các catalog chính và catalog thay thế.

## 4. Ví dụ Java hoàn chỉnh: tải DTD cục bộ qua Catalog

Tạo bốn tệp sau **cùng một thư mục**. URL `example.invalid` được dùng làm định danh để chứng minh rằng chương trình vẫn phân tích XML thành công mà không cần tải DTD từ Internet.

**Tệp `article.dtd`:**

```dtd
<!ELEMENT article (#PCDATA)>
```

**Tệp `catalog.xml`:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<catalog xmlns="urn:oasis:names:tc:entity:xmlns:xml:catalog" prefer="public">
  <system systemId="https://example.invalid/dtd/article.dtd" uri="article.dtd"/>
</catalog>
```

**Tệp `article.xml`:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE article SYSTEM "https://example.invalid/dtd/article.dtd">
<article>Java XML Catalog</article>
```

**Tệp `CatalogDemo.java`:**

```java
import java.nio.file.Path;
import javax.xml.XMLConstants;
import javax.xml.catalog.Catalog;
import javax.xml.catalog.CatalogFeatures;
import javax.xml.catalog.CatalogManager;
import javax.xml.catalog.CatalogResolver;
import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Document;

public class CatalogDemo {
    public static void main(String[] args) throws Exception {
        Path catalogPath = Path.of("catalog.xml").toAbsolutePath();
        String externalId = "https://example.invalid/dtd/article.dtd";

        CatalogFeatures features = CatalogFeatures.builder()
                .with(CatalogFeatures.Feature.RESOLVE, "strict")
                .build();

        // Catalog là bảng ánh xạ; chưa phải bộ phân tích XML.
        Catalog catalog = CatalogManager.catalog(features, catalogPath.toUri());
        System.out.println("Mapping exists: " + (catalog.matchSystem(externalId) != null));

        // CatalogManager tạo resolver từ catalog.
        CatalogResolver resolver = CatalogManager.catalogResolver(catalog);

        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        DocumentBuilder builder = factory.newDocumentBuilder();
        builder.setEntityResolver(resolver); // DOM sử dụng giao diện SAX EntityResolver.

        Document doc = builder.parse(Path.of("article.xml").toFile());
        System.out.println("Root: " + doc.getDocumentElement().getTagName());
        System.out.println("Text: " + doc.getDocumentElement().getTextContent().trim());
    }
}
```

Chạy từ thư mục chứa bốn tệp, với **JDK 17 trở lên** (API Catalog có từ Java 9):

```bash
javac CatalogDemo.java
java CatalogDemo
```

Kết quả chuẩn:

```text
Mapping exists: true
Root: article
Text: Java XML Catalog
```

**Diễn giải từng bước:**

1. `Path.toUri()` tạo URI `file:` tuyệt đối hợp lệ cho `catalog.xml`; tránh truyền thẳng chuỗi đường dẫn Windows như `C:\...` vào API nhận `URI`.
2. `CatalogFeatures` đặt `RESOLVE=strict` để thiếu ánh xạ trở thành lỗi rõ ràng, thay vì âm thầm tìm tài nguyên bên ngoài.
3. `CatalogManager.catalog(...)` nạp quy tắc; `Catalog.matchSystem(...)` cho phép kiểm tra mục `system` có khớp hay không. Bản thân bước tra cứu này không parse `article.xml`.
4. `CatalogManager.catalogResolver(catalog)` tạo `CatalogResolver`; `DocumentBuilder.setEntityResolver(...)` gắn nó vào quá trình parse.
5. Khi gặp `DOCTYPE ... SYSTEM "https://example.invalid/dtd/article.dtd"`, resolver trả nguồn cục bộ `article.dtd`; DOM đọc XML và tạo `Document`.
6. Cấu hình `FEATURE_SECURE_PROCESSING` và `ACCESS_EXTERNAL_DTD`/`ACCESS_EXTERNAL_SCHEMA` hạn chế truy cập ngoài. Chúng là lớp bảo vệ riêng; ví dụ vẫn cho phép tài nguyên được resolver ánh xạ rõ ràng.

Ví dụ trên đã được kiểm tra biên dịch và chạy với OpenJDK 24; không cần thêm dependency và cũng không cần server HTTP. Trong ứng dụng thật, hãy để catalog và các tệp được ánh xạ ở đường dẫn được kiểm soát, hoặc triển khai cơ chế tìm tài nguyên trong package/JAR phù hợp với môi trường của bạn.

## 5. `CatalogFeatures`: quyết định xử lý khi tra cứu

| Feature | Ý nghĩa | Mặc định/giá trị quan trọng |
| --- | --- | --- |
| `FILES` | Danh sách URI tuyệt đối của các tệp catalog (ngăn cách bằng `;`). | Có thể cấu hình qua `javax.xml.catalog.files`; khi truyền URI trực tiếp cho `CatalogManager.catalog(...)`, dùng chính các URI đó. |
| `PREFER` | Có xem xét mục `public` sau khi không khớp `system` hay không. | Mặc định `public`; `system` vẫn được tìm trước. |
| `DEFER` | Trì hoãn nạp catalog thay thế, delegate hoặc `nextCatalog` tới khi cần. | Mặc định `true`; `false` nạp sớm hơn. |
| `RESOLVE` | Hành vi khi resolver không tìm được ánh xạ. | Mặc định `strict`; các lựa chọn `strict`, `continue`, `ignore`. |

Với `RESOLVE`:

- **`strict`**: ném `CatalogException` khi không khớp. Thích hợp khi cần bảo đảm tham chiếu phải được khai báo, nhất là quy trình offline có kiểm soát.
- **`continue`**: nhường bước tiếp theo cho XML processor; processor **có thể** tự truy cập tài nguyên ngoài nếu không có chính sách hạn chế truy cập.
- **`ignore`**: yêu cầu processor bỏ qua tham chiếu ngoài không khớp. Điều này có thể làm thay đổi nội dung được đọc hoặc khiến validation thất bại; không dùng như cách che giấu file bị thiếu.

Thiết lập bằng builder:

```java
CatalogFeatures features = CatalogFeatures.builder()
        .with(CatalogFeatures.Feature.RESOLVE, "strict")
        .with(CatalogFeatures.Feature.DEFER, "true")
        .build();
```

Lưu ý giá trị feature là chuỗi có phân biệt hoa/thường. Thiết lập `prefer`, `defer`, `resolve` ngay trên phần tử catalog cũng có thể ảnh hưởng đến giá trị hiệu lực theo quy tắc ưu tiên cấu hình của API; không giả định giá trị trong builder luôn ghi đè thuộc tính XML Catalog.

## 6. Hai cách kết nối với JAXP

**Cách A — tạo `CatalogResolver` tường minh:** như ví dụ mục 4. Cách này hữu ích khi muốn dùng cùng resolver cho nhiều bộ xử lý, quản lý cấu hình tại một nơi hoặc kiểm soát rõ quy tắc không tìm thấy.

Với biến `resolver` đã được tạo ở ví dụ trên, các dòng **minh họa API** sau cho thấy vị trí gắn resolver tương ứng (không phải một chương trình Java độc lập):

```java
// DOM hoặc SAX sử dụng EntityResolver:
builder.setEntityResolver(resolver);

// StAX sử dụng XMLResolver:
javax.xml.stream.XMLInputFactory stax =
        javax.xml.stream.XMLInputFactory.newFactory();
stax.setXMLResolver(resolver);

// XML Schema validation sử dụng LSResourceResolver:
javax.xml.validation.SchemaFactory schemaFactory =
        javax.xml.validation.SchemaFactory.newInstance(
                XMLConstants.W3C_XML_SCHEMA_NS_URI);
schemaFactory.setResourceResolver(resolver);

// XSLT sử dụng URIResolver:
javax.xml.transform.TransformerFactory transformerFactory =
        javax.xml.transform.TransformerFactory.newInstance();
transformerFactory.setURIResolver(resolver);
```

**Cách B — cấu hình catalog trực tiếp trên JAXP processor:** các processor XML do JDK cung cấp hỗ trợ catalog thông qua thuộc tính `javax.xml.catalog.files`. Khi dùng cách này, thường không cần tự tạo `CatalogResolver`.

Đoạn dưới thay phần cấu hình `DocumentBuilderFactory` trong mục 4 và sử dụng lại `article.xml`, `catalog.xml`, `article.dtd` đã tạo (các câu lệnh này nằm trong phương thức có `throws Exception`):

```java
DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
factory.setAttribute(
        CatalogFeatures.Feature.FILES.getPropertyName(),
        Path.of("catalog.xml").toAbsolutePath().toUri().toString());
factory.setAttribute(
        CatalogFeatures.Feature.RESOLVE.getPropertyName(), "strict");
factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");

Document doc = factory.newDocumentBuilder()
        .parse(Path.of("article.xml").toFile());
System.out.println(doc.getDocumentElement().getTextContent());
```

Kết quả đoạn B là `Java XML Catalog` (đã kiểm tra trên OpenJDK 24). JDK XML processors mặc định bật khả năng dùng catalog (`XMLConstants.USE_CATALOG`), nhưng vẫn **cần khai báo catalog hợp lệ**. Resolver tự đăng ký của ứng dụng thường được ưu tiên; cách JAXP fallback về catalog còn phụ thuộc resolver đó trả về giá trị gì. Chọn A khi cần tường minh; chọn B khi muốn cấu hình tập trung trên processor/JAXP.

### Tình huống dùng XSD hiện đại

Giả sử một XSD đang có:

```xml
<xs:include xmlns:xs="http://www.w3.org/2001/XMLSchema"
            schemaLocation="https://schemas.example.invalid/shared/types.xsd"/>
```

Có thể ánh xạ bằng mục sau trong catalog (giả sử `xsd/types.xsd` tồn tại cạnh catalog):

```xml
<uri name="https://schemas.example.invalid/shared/types.xsd"
     uri="xsd/types.xsd"/>
```

Khi bộ xử lý schema đi qua một URI tham chiếu, `CatalogResolver`/cấu hình catalog phù hợp có thể đưa nó sang XSD cục bộ. XML Catalog **không làm thay** `SchemaFactory` hoặc `Validator`: chúng vẫn chịu trách nhiệm tạo schema và kiểm tra XML.

## 7. Luồng tra cứu, độ ưu tiên và khả năng thất bại

Khi xử lý một `systemId`/`publicId`/URI, resolver dùng quy tắc tương ứng: tìm nhóm **`system`** trước (`system`, `rewriteSystem`, `systemSuffix`); tiếp đến có thể xét **`public`** nếu `prefer` cho phép; cuối cùng có thể xét các mục **`uri`**. Nếu catalog chính không khớp, resolver có thể đi qua catalog được delegate, `nextCatalog` hoặc catalog thay thế. Một khi đã khớp, không cần thử catalog tiếp theo.

Ba điểm thực hành:

1. **Định danh cần khớp**: URL, scheme, dấu `/`, chữ hoa/thường và việc biến URI tương đối thành tuyệt đối có thể khiến `system` không khớp. Kiểm tra `systemId`/URI thực tế mà XML processor chuyển cho resolver. Khi URL nền thay đổi, cân nhắc `systemSuffix` nhưng giới hạn phạm vi chặt chẽ.
2. **Danh sách catalog có thứ tự**: catalog chính được xét trước catalog thay thế; các mục `nextCatalog` và delegate ảnh hưởng trình tự. Không giả định tất cả mapping cùng mức ưu tiên.
3. **Thiếu mapping khác với thiếu file đích**: mapping có thể khớp nhưng file cục bộ được trỏ tới không tồn tại/không đọc được. Hai vấn đề cần chẩn đoán riêng: `matchSystem(...)` chỉ xác nhận tìm thấy URI ánh xạ, không bảo đảm parse tài nguyên đích thành công.

`Catalog` bất biến giúp tái sử dụng một cấu hình nhất quán. Nếu cần đổi mapping, hãy cập nhật nguồn catalog và tạo đối tượng catalog/resolver mới theo vòng đời ứng dụng, thay vì mong đối tượng đã tạo tự đồng bộ mọi chỉnh sửa của file.

## 8. Bảo mật và lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ khai báo `catalog.xml` nhưng không truyền file cho `CatalogManager` hay JAXP. | Processor không biết catalog cần dùng. | Truyền URI vào `CatalogManager` hoặc cấu hình `Feature.FILES`. |
| Truyền đường dẫn tệp như chuỗi URL không hợp lệ. | Lỗi URI hoặc không tìm thấy catalog. | Dùng `Path.toAbsolutePath().toUri()`. |
| Dùng `<uri>` cho một `systemId` rồi giả định mọi API có cùng quy tắc tra cứu. | Tra cứu khó dự đoán; loại entry/processor có thể khác nhau. | Dùng entry đúng vai trò; thử với processor thật. |
| Dùng `RESOLVE=continue` và nghĩ rằng ứng dụng đã offline. | Có thể truy cập mạng hoặc đọc tài nguyên ngoài. | Ưu tiên `strict` khi cần fail-closed và đặt giới hạn external access. |
| Mặc định `prefer=public` có nghĩa là bỏ qua `system`. | Hiểu sai kết quả mapping. | Nhớ `system` vẫn được thử trước. |
| Gắn resolver vào một processor rồi kỳ vọng mọi parser trong ứng dụng tự dùng nó. | Các đường xử lý XML khác vẫn có thể tải URI ngoài. | Cấu hình từng processor liên quan hoặc áp dụng cấu hình JAXP có chủ đích. |
| Xem catalog là biện pháp bảo vệ XXE đầy đủ. | Vẫn có nguy cơ do XML không tin cậy hoặc cấu hình parser thiếu chặt chẽ. | Hạn chế truy cập ngoài, bật xử lý an toàn và tắt DTD khi nghiệp vụ không cần. |

**Nguyên tắc bảo mật:** Với XML không đáng tin và không cần DTD, cách rõ ràng nhất là cấu hình processor từ chối DTD/external entity. Khi **thật sự cần** DTD/XSD ngoài, chỉ ánh xạ đến tài nguyên được tin cậy và kiểm soát, kết hợp `XMLConstants.FEATURE_SECURE_PROCESSING`, `ACCESS_EXTERNAL_DTD`, `ACCESS_EXTERNAL_SCHEMA` và các hạn mức JAXP phù hợp. Không tải catalog hoặc file đích từ nguồn không tin cậy; các tham chiếu `nextCatalog`/delegate cũng phải được quản lý. Nếu parser cho phép `continue`, catalog không phải rào chắn chống truy cập ngoài.

## 9. Tự kiểm tra sau bài học

1. Thay URL `systemId` trong `article.xml` thành một URL không có entry trong catalog, giữ `RESOLVE=strict`: phân tích XML còn thành công không? Giải thích khác biệt giữa lỗi thiếu mapping và lỗi không đọc được file đích.
2. Thêm một entry `<uri .../>` cho XSD `include`; cho biết lúc nào nên gắn resolver qua `SchemaFactory.setResourceResolver(...)` và lúc nào có thể dùng cấu hình catalog trực tiếp.
3. Vì sao `Catalog.matchSystem(id) != null` chưa chứng minh toàn bộ quá trình parse an toàn? Trình bày vai trò riêng của `CatalogResolver` và `ACCESS_EXTERNAL_DTD`.

**Điểm cần nắm:** `Catalog` giữ ánh xạ, `CatalogManager` tạo catalog/resolver, `CatalogResolver` thực hiện phân giải trong các pipeline JAXP. Luôn kiểm soát file catalog, đường dẫn đích và chính sách xử lý tham chiếu không khớp.

## Tài liệu chuẩn đang áp dụng

- [Java SE — `javax.xml.catalog` package](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/catalog/package-summary.html)
- [Java SE — `Catalog`](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/catalog/Catalog.html)
- [Java SE — `CatalogManager`](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/catalog/CatalogManager.html)
- [Java SE — `CatalogResolver`](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/catalog/CatalogResolver.html)
- [Java SE — `CatalogFeatures`](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/catalog/CatalogFeatures.html)
- [Oracle — JAXP Security Guide](https://docs.oracle.com/en/java/javase/25/security/java-api-xml-processing-jaxp-security-guide.html)
