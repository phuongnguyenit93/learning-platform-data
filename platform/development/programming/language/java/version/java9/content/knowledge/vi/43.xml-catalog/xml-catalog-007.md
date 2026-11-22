# Quan hệ giữa XML Catalog và giới hạn truy cập tài nguyên ngoài trong JAXP (Java 9+)

## 1. Vấn đề cần giải quyết

Khi đọc XML, trình xử lý JAXP có thể gặp tham chiếu đến DTD/entity, XSD hoặc XSLT nằm bên ngoài tài liệu. Ví dụ: `<!DOCTYPE message SYSTEM "https://example.invalid/vocab/message.dtd">` yêu cầu tìm một DTD có định danh là URL HTTPS. Nếu ứng dụng tự truy cập URL đó, nó có thể phụ thuộc mạng, làm chậm xử lý hoặc tạo đường tấn công XXE/SSRF và đọc tài nguyên ngoài ý muốn.

Từ **Java 9**, module `java.xml` cung cấp **XML Catalog API** (`javax.xml.catalog`), hỗ trợ chuẩn OASIS XML Catalog 1.1. Catalog ánh xạ định danh tài nguyên trong tài liệu XML sang tài nguyên được kiểm soát, thường là file đi kèm ứng dụng. Song song, JAXP có **External Access Properties (EAP)** để giới hạn các giao thức mà trình xử lý được phép tự dùng khi kết nối ra ngoài.

Hai cơ chế bổ sung cho nhau:

- **Catalog trả lời “tài nguyên có định danh này nên được giải quyết ở đâu?”** Ví dụ, URL DTD trong tài liệu được ánh xạ đến `local.dtd` đã đóng gói.
- **External Access Properties trả lời “nếu JAXP phải tự mở một tài nguyên ngoài, giao thức nào được phép?”** Ví dụ, `ACCESS_EXTERNAL_DTD=""` không cho trình xử lý tự kết nối qua HTTP, HTTPS hay `file` để lấy DTD.
- **Cấu hình xử lý khi Catalog không tìm thấy mục khớp** quyết định tiếp tục tìm theo cơ chế thông thường, bỏ qua tài nguyên hay phát sinh lỗi. Đây là quyết định khác với danh sách giao thức EAP.

Catalog **không phải tường lửa**, còn EAP **không phải công cụ ánh xạ URL**. Muốn sử dụng tài nguyên nội bộ đã được kiểm duyệt trong khi chặn truy cập tùy ý, hãy cấu hình cả hai trên đúng bộ xử lý XML.

## 2. Dòng xử lý và điểm kiểm soát

Với một tham chiếu ngoài được trình xử lý JDK hỗ trợ Catalog, hãy hình dung thứ tự:

1. XML/XSD/XSLT đưa ra `systemId`, `publicId` hoặc một URI cần giải quyết.
2. Nếu ứng dụng đã gắn **resolver tùy chỉnh**, JDK gọi resolver đó trước. Nếu nó trả về nguồn hợp lệ (khác `null`), nguồn đó được dùng; Catalog thường không cần tham gia.
3. Nếu resolver tùy chỉnh không xử lý, và `XMLConstants.USE_CATALOG` được bật với Catalog đã cấu hình, JDK tìm mục phù hợp trong Catalog, chẳng hạn `<system systemId="..." uri="local.dtd"/>`.
4. **Khớp Catalog:** trình xử lý sử dụng tài nguyên mà Catalog trả về (trong ví dụ là DTD nội bộ); không cần tải DTD từ URL gốc.
5. **Không khớp Catalog:** `javax.xml.catalog.resolve` xác định cách xử lý:
   - `strict` (mặc định của Catalog API): báo lỗi `CatalogException` khi không tìm được mục phù hợp.
   - `continue`: cho phép trình xử lý tiếp tục cơ chế giải quyết bình thường.
   - `ignore`: yêu cầu bỏ qua tham chiếu chưa được giải quyết khi loại trình xử lý hỗ trợ.
6. Nếu quy trình đi đến bước **JAXP tự mở tài nguyên bên ngoài**, EAP tương ứng kiểm tra giao thức. Không được phép thì việc truy cập bị từ chối và thường phát sinh ngoại lệ riêng của bộ xử lý.

**Điểm tinh tế:** Theo tài liệu bảo mật JAXP, EAP không kiểm soát các nguồn mà resolver đã trả về thành công (nguồn khác `null`). Vì thế, khi Catalog hoặc resolver đưa ra đường dẫn nội bộ, hãy coi **nội dung và đích ánh xạ của resolver/Catalog là đầu vào cần được tin cậy và kiểm duyệt**. Không được diễn giải `ACCESS_EXTERNAL_DTD=""` thành “mọi đường dẫn file đều bị cấm ngay cả khi một resolver chủ động cung cấp file đó”.

### Bảng hành vi quan trọng

| Catalog / resolver | Cấu hình khi không khớp | EAP áp dụng khi tự truy cập | Hệ quả chính |
| --- | --- | --- | --- |
| Catalog khớp URL với file nội bộ tin cậy | `strict` hoặc `continue` | Không cần truy cập URL gốc | Dùng bản nội bộ do Catalog chọn |
| Không có mục khớp | `strict` | Chưa tới bước tải URL gốc | Báo lỗi Catalog, hữu ích với danh sách tài nguyên cho phép |
| Không có mục khớp | `continue` | `ACCESS_EXTERNAL_DTD=""` | Trình xử lý không được tự tải DTD qua giao thức ngoài |
| Không có mục khớp | `continue` | `ACCESS_EXTERNAL_DTD="file"` | Có thể truy cập DTD qua `file:`, nhưng không qua `http:`/`https:` |
| Resolver tùy chỉnh trả về nguồn | Bất kỳ | EAP không chặn nguồn resolver đã cung cấp | Phải tự bảo đảm resolver chỉ trả nguồn an toàn |
| Catalog bị tắt (`USE_CATALOG=false`) | Không áp dụng | EAP vẫn có hiệu lực với kết nối do JAXP thực hiện | Không có ánh xạ Catalog, nên tham chiếu gốc phải được xử lý theo chính sách còn lại |

Không nên lấy “không có kết nối mạng” làm bằng chứng rằng ứng dụng đã an toàn trước mọi XXE: bộ xử lý còn có thể đọc file cục bộ hoặc mở nguồn do resolver cung cấp; entity expansion cũng có thể gây tiêu tốn tài nguyên mà không cần mạng.

## 3. Thuộc tính cấu hình cần nắm

### 3.1. Giới hạn truy cập ngoài (EAP)

| API/thuộc tính | Nơi dùng tiêu biểu | Loại truy cập bị kiểm soát |
| --- | --- | --- |
| `XMLConstants.ACCESS_EXTERNAL_DTD` / `javax.xml.accessExternalDTD` | DOM, SAX, trình xử lý có tham chiếu DTD/entity | DTD ngoài và thực thể XML ngoài |
| `XMLConstants.ACCESS_EXTERNAL_SCHEMA` / `javax.xml.accessExternalSchema` | `SchemaFactory`/validator | XSD tham chiếu qua `schemaLocation`, `xs:include`, `xs:import`... |
| `XMLConstants.ACCESS_EXTERNAL_STYLESHEET` / `javax.xml.accessExternalStylesheet` | `TransformerFactory`/XSLT | Stylesheet ngoài, `xsl:include`, `xsl:import`, `document()`... |

Giá trị là danh sách **giao thức** cách nhau bằng dấu phẩy: `""` nghĩa là không cho phép giao thức nào; `"file"` chỉ cho phép `file:`; `"file,https"` cho hai giao thức tương ứng; `"all"` cho mọi giao thức. Đây là chính sách theo giao thức, **không phải danh sách đường dẫn hay tên miền cho phép**. Chỉ cho `file` không có nghĩa là chỉ đọc một thư mục cụ thể.

Nên cấu hình trực tiếp tại factory/processor của luồng xử lý cần bảo vệ; cấu hình qua system property hoặc file JAXP hữu ích khi áp dụng cho toàn JVM. Thứ tự ưu tiên trong JAXP hiện hành: **API của factory/processor > system property > file cấu hình JAXP tùy chọn > `$JAVA_HOME/conf/jaxp.properties` > mặc định**. Đừng dựa vào giá trị mặc định giữa môi trường hoặc phiên bản JDK.

### 3.2. Thuộc tính XML Catalog

| API / system property | Ý nghĩa |
| --- | --- |
| `CatalogFeatures.Feature.FILES` / `javax.xml.catalog.files` | URI của một hay nhiều file Catalog |
| `CatalogFeatures.Feature.RESOLVE` / `javax.xml.catalog.resolve` | `strict`, `continue`, `ignore` khi không tìm thấy mục |
| `CatalogFeatures.Feature.PREFER` / `javax.xml.catalog.prefer` | Quy tắc ưu tiên tìm `public`/`system` theo chuẩn Catalog |
| `CatalogFeatures.Feature.DEFER` / `javax.xml.catalog.defer` | Có trì hoãn nạp Catalog được tham chiếu hay không |
| `XMLConstants.USE_CATALOG` / `javax.xml.useCatalog` | Bật/tắt dùng Catalog; mặc định là `true` trong JDK hiện đại |

Trong trường hợp thông dụng, chỉ cần `FILES` và lựa chọn rõ `RESOLVE`. Bản thân Catalog có thể chứa mục `system`, `public`, `uri`, `rewriteSystem`, `rewriteURI` hoặc `nextCatalog`; dùng loại mục phù hợp định danh thực sự xuất hiện trong tài liệu. Tùy tình huống, Catalog có thể phục vụ DTD, XSD, XSLT và các URI khác, nhưng loại tham chiếu và API xử lý phải hỗ trợ cách ánh xạ tương ứng.

**Phân biệt hai thuộc tính dễ nhầm:** `javax.xml.catalog.resolve=strict` quy định *không tìm thấy thì thất bại*; `javax.xml.accessExternalDTD=""` quy định *không tự kết nối ra giao thức ngoài để lấy DTD*. Thiết lập một thuộc tính không thay thế thuộc tính còn lại.

## 4. Ví dụ Java 17+: dùng DTD nội bộ và từ chối truy cập ngoài

Tạo **bốn file cùng thư mục**. URL `example.invalid` chỉ là định danh trong XML, không cần và không nên truy cập mạng.

**File `input.xml`:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE message SYSTEM "https://example.invalid/vocab/message.dtd">
<message>&greeting;</message>
```

**File `local.dtd`:** đây là nguồn nội bộ được kiểm soát; trình phân tích sẽ lấy khai báo `greeting` từ file này.

```dtd
<!ELEMENT message (#PCDATA)>
<!ENTITY greeting "Xin chào từ DTD nội bộ">
```

**File `catalog.xml`:** ánh xạ chính xác `systemId` trong `input.xml` sang đường dẫn tương đối cạnh Catalog.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<catalog xmlns="urn:oasis:names:tc:entity:xmlns:xml:catalog">
    <system
        systemId="https://example.invalid/vocab/message.dtd"
        uri="local.dtd"/>
</catalog>
```

**File `CatalogSecurityDemo.java`:**

```java
import java.nio.file.Path;
import javax.xml.XMLConstants;
import javax.xml.catalog.CatalogFeatures;
import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Document;

public class CatalogSecurityDemo {
    public static void main(String[] args) throws Exception {
        Path catalog = Path.of("catalog.xml").toAbsolutePath();

        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setFeature(XMLConstants.USE_CATALOG, true);

        // Catalog phải trỏ bằng URI; các mục tương đối tính từ URI này.
        factory.setAttribute(
            CatalogFeatures.Feature.FILES.getPropertyName(),
            catalog.toUri().toString()
        );
        factory.setAttribute(
            CatalogFeatures.Feature.RESOLVE.getPropertyName(),
            "strict"
        );

        // Không cho JAXP tự mở DTD/entity hoặc schema bên ngoài.
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        DocumentBuilder builder = factory.newDocumentBuilder();
        Document document = builder.parse(Path.of("input.xml").toFile());

        System.out.println(
            document.getDocumentElement().getTextContent().trim()
        );
    }
}
```

Biên dịch và chạy từ thư mục chứa cả bốn file bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 CatalogSecurityDemo.java
java CatalogSecurityDemo
```

**Đầu ra chuẩn:**

```text
Xin chào từ DTD nội bộ
```

Giải thích: parser gặp URL DTD trong `input.xml`, dùng Catalog để tìm `local.dtd`, sau đó mở rộng entity `&greeting;` bằng khai báo từ file nội bộ. Không cần truy xuất URL `https://example.invalid/...`. Cấu hình EAP rỗng ngăn các kết nối DTD/schema ngoài do JAXP tự thực hiện nếu phát sinh.

### 4.1. Kiểm chứng trường hợp không có ánh xạ

Hãy thử **đổi riêng `systemId` trong `input.xml`** thành `https://example.invalid/vocab/unknown.dtd`, giữ nguyên Catalog và `RESOLVE="strict"`. Kết quả mong đợi là **xử lý thất bại**, thường với `CatalogException` hoặc một ngoại lệ parser bao bọc lỗi đó, vì Catalog không có mục khớp. Đây là phép thử chặn tài nguyên chưa được duyệt, không phải lỗi của DTD nội bộ.

Tiếp theo, nếu đổi `RESOLVE` sang `continue` mà vẫn giữ `ACCESS_EXTERNAL_DTD=""`, Catalog sẽ nhường việc xử lý tham chiếu không khớp cho parser; **parser vẫn không được tự tải DTD ngoài**. Ngoại lệ có thể nêu rõ giao thức `https` không được phép bởi `accessExternalDTD`. Đừng dùng `"all"` để “sửa” lỗi này khi xử lý XML không tin cậy.

Nếu đặt `USE_CATALOG=false` thì Catalog không tham gia; việc parser có truy cập được DTD hay không phụ thuộc chính sách EAP và các cấu hình XML khác. Trên JDK, thuộc tính `USE_CATALOG` có từ Java 9 và mặc định bật, nhưng ví dụ khai báo tường minh để dễ kiểm tra.

## 5. Áp dụng đúng với XSD, XSLT và các resolver khác

- **XSD:** dùng `SchemaFactory`/`Validator` với `ACCESS_EXTERNAL_SCHEMA` và, khi có DTD/entity, cả `ACCESS_EXTERNAL_DTD`. Catalog có thể ánh xạ URI `xs:import`/`xs:include` đến XSD đã đóng gói. Với `SchemaFactory`, cấu hình Catalog qua `setProperty(CatalogFeatures.Feature.FILES.getPropertyName(), catalogUri)`. Nếu ứng dụng chủ động gọi `newSchema` với một `Source` thì phải tự kiểm soát nguồn đầu vào; EAP không thay một chính sách kiểm soát đầu vào do ứng dụng tự cấp.
- **XSLT:** dùng `TransformerFactory` và `ACCESS_EXTERNAL_STYLESHEET` cho `xsl:import`, `xsl:include`, `document()` hoặc stylesheet liên quan; có thể gắn Catalog theo cơ chế hỗ trợ của JDK. Chỉ cấu hình `ACCESS_EXTERNAL_DTD` không đủ để bảo vệ các phép tải stylesheet.
- **Resolver tùy chỉnh:** `EntityResolver` (SAX/DOM), `XMLResolver` (StAX), `LSResourceResolver` (Schema) và `URIResolver` (XSLT) có thể được gọi trước Catalog. Khi resolver tùy chỉnh trả nguồn, hãy kiểm soát URL/path, không để dữ liệu từ XML quyết định tùy ý file hoặc máy chủ cần đọc.
- **Trình xử lý và thư viện khác nhau:** các API JAXP có cách đặt thuộc tính khác nhau (`setAttribute`, `setProperty`, `setFeature`). Xác minh thư viện thực tế hỗ trợ thuộc tính đang dùng, và cấu hình trên **từng điểm tạo parser/validator/transformer** của ứng dụng. Chỉ thay đổi một factory không tự động bảo vệ mọi XML processor khác.

Ví dụ ngắn cho một `SchemaFactory` sử dụng XSD có Catalog (đây là **đoạn cấu hình**, không phải một chương trình độc lập):

```java
SchemaFactory schemaFactory =
    SchemaFactory.newInstance(XMLConstants.W3C_XML_SCHEMA_NS_URI);
schemaFactory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
schemaFactory.setProperty(
    CatalogFeatures.Feature.FILES.getPropertyName(),
    Path.of("catalog.xml").toAbsolutePath().toUri().toString()
);
schemaFactory.setProperty(
    CatalogFeatures.Feature.RESOLVE.getPropertyName(), "strict"
);
schemaFactory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
schemaFactory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
```

Để biên dịch đoạn trên khi đưa vào lớp Java, cần import `javax.xml.validation.SchemaFactory` cùng `java.nio.file.Path`, `javax.xml.XMLConstants` và `javax.xml.catalog.CatalogFeatures`. Với XSD, nội dung Catalog phải có mục phù hợp chính xác URI được tham chiếu; không thể dùng nguyên `catalog.xml` của ví dụ DTD rồi kỳ vọng nó tự ánh xạ mọi schema.

## 6. Những giới hạn bảo mật không được bỏ qua

1. **Không cần DTD thì nên không xử lý DTD.** Với XML không tin cậy mà nghiệp vụ không cần DOCTYPE/entities, cấu hình parser từ chối DOCTYPE và external entity theo API/implementation đang dùng sẽ giảm bề mặt tấn công hơn so với cố gắng Catalog hóa mọi URL.
2. **Catalog là cấu hình tin cậy, cần kiểm soát phiên bản.** Đóng gói Catalog và các file đích cùng ứng dụng; dùng đường dẫn cục bộ cố định, xem xét các mục `rewrite*` và `nextCatalog`, tránh để người dùng nhập tùy ý nội dung Catalog hay `uri` đích. Catalog ánh xạ đến một file nhạy cảm vẫn có thể dẫn tới rủi ro, dù URL gốc là HTTPS.
3. **Giới hạn giao thức không giới hạn đường dẫn.** `ACCESS_EXTERNAL_DTD="file"` cho phép giao thức `file:` trên phạm vi bộ xử lý liên quan, không khóa vào thư mục ứng dụng. Khi cần khóa đường dẫn thật sự, kiểm duyệt đích và áp dụng quyền truy cập ở lớp ứng dụng/hệ điều hành.
4. **Giữ `FEATURE_SECURE_PROCESSING` và giới hạn tài nguyên.** FSP hỗ trợ kiểm soát hoạt động XML tốn CPU/bộ nhớ; ví dụ `jdk.xml.entityExpansionLimit` hữu ích trong môi trường có nguy cơ XML bomb. FSP được bật mặc định cho một số factory trong JDK nhưng **không nên suy luận rằng mọi kết nối ngoài đều bị chặn mặc định**; đặt EAP tường minh.
5. **EAP áp dụng cho truy cập do JAXP thực hiện.** Nếu mã ứng dụng chủ động tạo `URL.openStream()`, tự đọc file, hoặc resolver tự tải qua HTTP, phải kiểm soát các thao tác đó bằng cơ chế riêng. EAP không tự biến thành bộ lọc mạng toàn JVM.
6. **Thử cả nhánh thành công và nhánh bị chặn.** Một kiểm thử tốt phải chứng minh: tài nguyên được cho phép thì tìm đúng file nội bộ; URL lạ không được phép có kết quả thất bại dự đoán được; đổi cấu hình Catalog/EAP không âm thầm mở ra truy cập mạng.

## 7. Lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra |
| --- | --- | --- |
| Catalog có file nhưng không ánh xạ | `systemId`/URI không khớp tuyệt đối, sai loại mục `system`/`uri` hoặc Catalog chưa được gắn vào parser | So sánh định danh thực tế, kiểm tra URI Catalog, dùng `RESOLVE=strict` khi thử |
| Không tìm thấy `local.dtd` | Đường dẫn `uri` tương đối dựa trên vị trí file Catalog, không nhất thiết là thư mục đang chạy | Đặt file đích cạnh Catalog hoặc dùng URI cục bộ rõ ràng |
| Bị chặn bởi `accessExternalDTD` | Catalog không khớp, bị tắt hoặc resolver trả `null` rồi parser tự mở URL | Kiểm tra `USE_CATALOG`, `FILES`, loại mục, `RESOLVE` trước khi xem xét nới EAP |
| Cài Catalog nhưng vẫn thấy kết nối ra ngoài | Có tham chiếu ngoài khác không khớp; `resolve=continue`; bộ xử lý khác chưa cấu hình; hoặc custom resolver tự truy cập | Kiểm tra luồng thực tế, các factory/processor và quyền truy cập |
| Đặt `ACCESS_EXTERNAL_DTD=""` nhưng XSLT vẫn tải file | Thiếu `ACCESS_EXTERNAL_STYLESHEET` trên `TransformerFactory` | Khóa đúng thuộc tính theo loại tài nguyên |
| Cấu hình xử lý XML khác nhau giữa máy | Dựa vào mặc định hoặc system properties/file JAXP khác nhau | Đặt thuộc tính tường minh tại điểm khởi tạo và kiểm thử trong runtime thật |

**Gợi ý thiết kế:** đối với tài liệu XML có bộ DTD/XSD cố định, ưu tiên Catalog cục bộ với `RESOLVE=strict` và EAP rỗng; chỉ nới quyền khi có nhu cầu có lý do rõ ràng, sau khi đánh giá tác động trên đúng processor. Đối với XML đầu vào không cần DTD, ưu tiên vô hiệu hóa khả năng xử lý DTD.

## Tài liệu tham khảo đang được duy trì

- [Oracle: XML Catalog API – Java SE Core Libraries](https://docs.oracle.com/en/java/javase/25/core/xml-catalog-api1.html) — API chuẩn có từ Java 9.
- [Oracle: Use Catalog with XML Processors](https://docs.oracle.com/en/java/javase/25/core/use-catalog-xml-processors.html) — cấu hình Catalog với DOM/SAX và các processor.
- [Oracle: JAXP Security Guide](https://docs.oracle.com/en/java/javase/25/security/java-api-xml-processing-jaxp-security-guide.html) — external access, resolver, xử lý bảo mật XML.
- [Java SE 25: XMLConstants](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/XMLConstants.html) — các hằng số EAP, `USE_CATALOG` và ý nghĩa giá trị.
- [Java SE 25: java.xml module](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/module-summary.html) — cấu hình, thứ tự ưu tiên thuộc tính JAXP.

Các nguyên tắc và API chính ở trên áp dụng từ Java 9 đến JDK hiện hành; ví dụ thực hành sử dụng cú pháp Java 17+ và tránh các cơ chế đã lỗi thời.