# Ánh xạ public identifier, system identifier và URI bằng XML Catalog (Java 9+)

XML Catalog là bảng ánh xạ **định danh tài nguyên XML** sang một địa chỉ thay thế, thường là tệp được đóng gói cùng ứng dụng. Từ Java 9, JDK cung cấp API chuẩn `javax.xml.catalog` trong module `java.xml`. API này vẫn có trong các phiên bản Java hiện đại và được các bộ xử lý XML của JDK hỗ trợ. Chủ đề ở đây là **cách ba loại định danh được nhận diện, so khớp và ưu tiên khi phân giải**, không phải cách thay đổi nội dung XML.

Sau bài này, bạn có thể đọc một khai báo `DOCTYPE` hoặc tham chiếu XSD/XSLT, xác định cần viết mục `public`, `system` hay `uri`, giải thích vì sao một mục được chọn, và cấu hình bộ phân giải trong Java.

## 1. Tại sao cần ánh xạ?

Một tệp XML có thể tham chiếu tài nguyên ngoài: DTD, thực thể ngoài, XSD được `xs:include`/`xs:import`, hoặc XSLT được `xsl:include`/`xsl:import`. Địa chỉ xuất hiện trong tài liệu có thể là URL được quy định bởi đối tác, trong khi ứng dụng muốn dùng bản sao đã kiểm soát trong thư mục triển khai.

Ví dụ, XML ghi:

```xml
<!DOCTYPE report PUBLIC "-//EXAMPLE//DTD Report 1.0//EN"
                        "https://example.invalid/report.dtd">
<report>&where;</report>
```

Thay vì truy cập URL trong `DOCTYPE`, catalog có thể chỉ bộ phân giải tới `system.dtd` ngay cạnh ứng dụng. Chuỗi `https://example.invalid/report.dtd` ở đây là **định danh được dùng để tra cứu**; không bắt buộc phải có một máy chủ hoạt động ở địa chỉ đó. Catalog tạo sự độc lập giữa tên tài nguyên mà XML tham chiếu và nơi tài nguyên thực sự được lưu.

Lợi ích thực tế: hoạt động ổn định khi offline, dựng bản build lặp lại được, giảm phụ thuộc mạng, kiểm soát phiên bản DTD/XSD/XSLT và tránh tải tài nguyên không mong muốn. Catalog chỉ có tác dụng đối với tham chiếu mà bộ xử lý thực sự đưa qua cơ chế phân giải; bản thân việc có file catalog không tự chặn mọi kết nối.

## 2. Ba định danh: khác nhau ở đâu?

| Khái niệm | Xuất hiện ở đâu | Ví dụ | Cách ánh xạ chính |
| --- | --- | --- | --- |
| **Public identifier** (`publicId`) | Chuỗi sau từ khóa `PUBLIC` trong DTD/entity | `-//EXAMPLE//DTD Report 1.0//EN` | `<public publicId="..." uri="..."/>` |
| **System identifier** (`systemId`) | URI sau `SYSTEM`, hoặc URI thứ hai sau `PUBLIC` | `https://example.invalid/report.dtd` | `<system systemId="..." uri="..."/>` |
| **URI reference** | Địa chỉ `href`/`schemaLocation`/tài nguyên khác của XML | `https://example.invalid/report.xsd` | `<uri name="..." uri="..."/>` |

**Public identifier** là tên công khai mang tính quy ước, không phải địa chỉ tải xuống. **System identifier** là URI tham chiếu thực thể, có thể tương đối hoặc tuyệt đối. Với `DOCTYPE ... PUBLIC "P" "S"`, XML cung cấp **cả P lẫn S**, không phải chỉ P. **URI reference** là chuỗi dùng để xác định một tài nguyên khác, phổ biến trong XSD/XSLT.

Phân biệt hai thuộc tính của mục catalog: `systemId`/`publicId`/`name` là **khóa tìm kiếm**, còn `uri` là **đích thay thế**. Không nhầm `<uri name="...">` với thuộc tính `uri="..."` trên các mục `<system>` và `<public>`.

Ví dụ XSD:

```xml
<xs:import xmlns:xs="http://www.w3.org/2001/XMLSchema"
           namespace="urn:example:types"
           schemaLocation="https://example.invalid/schemas/types.xsd"/>
```

Ở đây `schemaLocation` chứa **URI của tài nguyên cần nạp**; `namespace="urn:example:types"` định danh không gian tên của lược đồ. Namespace URI không nhất thiết trỏ tới một tệp có thể tải, nên không được mặc định coi nó là địa chỉ cần rewrite. Hãy ánh xạ giá trị mà bộ xử lý yêu cầu tìm (trong ví dụ là `schemaLocation`).

## 3. Tạo catalog đúng chuẩn OASIS XML Catalogs 1.1

Tệp `catalog.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<catalog xmlns="urn:oasis:names:tc:entity:xmlns:xml:catalog"
         prefer="public">
  <system systemId="https://example.invalid/report.dtd"
          uri="dtd/system.dtd"/>

  <public publicId="-//EXAMPLE//DTD Report 1.0//EN"
          uri="dtd/public.dtd"/>

  <uri name="https://example.invalid/report.xsd"
       uri="xsd/report.xsd"/>

  <uri name="https://example.invalid/xslt/common.xsl"
       uri="xslt/common.xsl"/>
</catalog>
```

Cấu trúc thư mục ví dụ:

```text
project/
├── catalog.xml
├── dtd/
│   ├── system.dtd
│   └── public.dtd
├── xsd/
│   └── report.xsd
└── xslt/
    └── common.xsl
```

Những điểm cần nhớ:

- Phần tử gốc phải thuộc namespace `urn:oasis:names:tc:entity:xmlns:xml:catalog`. Thiếu namespace này là lỗi dễ khiến catalog không được hiểu đúng.
- Mỗi mục nói: **khi thấy khóa X thì dùng URI Y**. `uri="dtd/system.dtd"` là đường dẫn tương đối, được giải theo URI nền của catalog (hoặc `xml:base` nếu khai báo). Nó không phụ thuộc vào thư mục làm việc hiện tại theo cách đọc path thông thường.
- `prefer="public"` cho phép dùng public identifier khi không có ánh xạ system phù hợp; **không** có nghĩa public được ưu tiên trước một mục system đã khớp.
- Tên, chữ hoa/thường, dấu gạch, dấu `/`, encoding URI và đường dẫn phải khớp theo quy tắc của catalog. Đừng dựa vào “gần giống” hoặc tự suy đoán tên file.
- Với dự án thực tế, đặt catalog và các bản sao DTD/XSD/XSLT trong cùng tài nguyên triển khai; quản lý nội dung các tệp này như một dependency có phiên bản.

## 4. Cơ chế chọn giữa system, public và URI

Một `CatalogResolver` của JDK nhận tham chiếu từ XML processor, tra catalog hiện tại, rồi mới xét các catalog được ủy quyền hoặc catalog dự phòng khi cần. Với tham chiếu có `systemId` và có thể có `publicId`, thứ tự chính là:

1. **System:** tìm mục `system` khớp chính xác, rồi các cơ chế `rewriteSystem`/`systemSuffix` phù hợp. Nếu tìm thấy, kết thúc; mục `public` tương ứng không được chọn.
2. **Public:** khi chưa tìm thấy system và chính sách `prefer` cho phép (thường là `public`, cũng là giá trị mặc định), thử `public`/`delegatePublic` theo `publicId`.
3. **URI:** nếu chưa tìm thấy, Java resolver có thể thử các mục `uri`/`rewriteURI`/`uriSuffix` đối với URI đang được hỏi hoặc `systemId`. Với lời gọi kiểu `URIResolver` (ví dụ tham chiếu XSLT), `href` là đầu vào chủ yếu.
4. **Không có kết quả:** áp dụng chính sách `resolve`: `strict`, `continue` hoặc `ignore` (phần 8).

Các cơ chế `delegateSystem`/`delegateURI`, `delegatePublic` và `nextCatalog` cho phép tra thêm catalog khác. Thứ tự các bước cụ thể có quy tắc theo loại entry, nhóm catalog và độ dài tiền tố/hậu tố; không nên suy từ thứ tự hiển thị của các dòng XML rằng dòng đầu luôn thắng. Một kết quả đã tìm được trong catalog chính không cần đi tìm lại ở catalog dự phòng.

**Hai tình huống dễ nhầm:**

| Tham chiếu đầu vào | Mục đã có | Kết quả |
| --- | --- | --- |
| `PUBLIC "P" "S"` | Có cả `system(S)` và `public(P)` | **system(S)** thắng |
| `PUBLIC "P" "S2"` | Không có `system(S2)`; có `public(P)` và `prefer=public` | **public(P)** được chọn |
| `SYSTEM "S"` | Có `system(S)`, không có `publicId` | **system(S)** được chọn |
| Một `href` hoặc `schemaLocation` là `U` | Có `uri(name=U)` | Có thể chọn **uri(U)** khi thành phần XML ấy được đưa qua catalog |

Giá trị `prefer="system"` có ý nghĩa khác: khi tham chiếu có system identifier, bộ giải không dùng public fallback chỉ vì system không khớp; public hữu ích trong trường hợp không có system identifier. Với tài liệu vừa có `PUBLIC` vừa có `SYSTEM`, `prefer="public"` thường dễ đáp ứng kỳ vọng hơn.

**API tra cứu trực tiếp và API resolver không đồng nghĩa.** `Catalog.matchSystem(id)` chỉ tra các mục kiểu system; `matchPublic(id)` chỉ tra kiểu public; `matchURI(uri)` chỉ tra kiểu URI. Chúng trả lại URI đích (`String`) khi khớp hoặc `null` khi không khớp. `CatalogResolver` tổng hợp các quy tắc và giao tiếp với DOM/SAX, StAX, schema validation và XSLT.

## 5. Ví dụ Java 17+ chạy độc lập, kiểm chứng đủ ba loại

Chương trình dưới đây **tự tạo các file thử nghiệm trong một thư mục tạm**, xây một catalog, gọi ba phương thức tra cứu trực tiếp và parse hai tài liệu XML. Hai file DTD cùng khai báo thực thể `where` nhưng có giá trị khác nhau, nhờ đó ta thấy rõ quy tắc ưu tiên. Tất cả URL `example.invalid` chỉ là khóa tra cứu, không cần kết nối mạng.

Lưu toàn bộ vào `CatalogIdentifiersDemo.java`:

```java
import java.io.StringReader;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import javax.xml.XMLConstants;
import javax.xml.catalog.Catalog;
import javax.xml.catalog.CatalogFeatures;
import javax.xml.catalog.CatalogManager;
import javax.xml.catalog.CatalogResolver;
import javax.xml.parsers.DocumentBuilderFactory;
import org.xml.sax.InputSource;

public class CatalogIdentifiersDemo {
    private static final String PUBLIC_ID = "-//EXAMPLE//DTD Report 1.0//EN";
    private static final String SYSTEM_ID = "https://example.invalid/report.dtd";
    private static final String XSD_URI = "https://example.invalid/report.xsd";

    private static String parse(CatalogResolver resolver, String systemId)
            throws Exception {
        String xml = "<!DOCTYPE report PUBLIC \"" + PUBLIC_ID + "\" \"" + systemId
                + "\"><report>&where;</report>";

        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
        factory.setNamespaceAware(true);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);

        var builder = factory.newDocumentBuilder();
        builder.setEntityResolver(resolver);
        return builder.parse(new InputSource(new StringReader(xml)))
                .getDocumentElement().getTextContent();
    }

    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("catalog-demo-");
        Files.writeString(dir.resolve("system.dtd"), "<!ENTITY where 'SYSTEM'>\n");
        Files.writeString(dir.resolve("public.dtd"), "<!ENTITY where 'PUBLIC'>\n");
        Files.writeString(dir.resolve("report.xsd"),
                "<schema xmlns='http://www.w3.org/2001/XMLSchema'/>\n");

        Path catalogFile = dir.resolve("catalog.xml");
        Files.writeString(catalogFile, """
                <?xml version="1.0" encoding="UTF-8"?>
                <catalog xmlns="urn:oasis:names:tc:entity:xmlns:xml:catalog"
                         prefer="public">
                  <system systemId="https://example.invalid/report.dtd"
                          uri="system.dtd"/>
                  <public publicId="-//EXAMPLE//DTD Report 1.0//EN"
                          uri="public.dtd"/>
                  <uri name="https://example.invalid/report.xsd"
                       uri="report.xsd"/>
                </catalog>
                """);

        CatalogFeatures features = CatalogFeatures.builder()
                .with(CatalogFeatures.Feature.PREFER, "public")
                .with(CatalogFeatures.Feature.RESOLVE, "strict")
                .build();

        Catalog catalog = CatalogManager.catalog(features, catalogFile.toUri());
        System.out.println("system="
                + Path.of(URI.create(catalog.matchSystem(SYSTEM_ID))).getFileName());
        System.out.println("public="
                + Path.of(URI.create(catalog.matchPublic(PUBLIC_ID))).getFileName());
        System.out.println("uri="
                + Path.of(URI.create(catalog.matchURI(XSD_URI))).getFileName());

        CatalogResolver resolver = CatalogManager.catalogResolver(features,
                catalogFile.toUri());
        System.out.println("both=" + parse(resolver, SYSTEM_ID));
        System.out.println("publicFallback="
                + parse(resolver, "https://example.invalid/unlisted.dtd"));
    }
}
```

Biên dịch và chạy từ thư mục chứa mã nguồn:

```bash
javac -encoding UTF-8 CatalogIdentifiersDemo.java
java CatalogIdentifiersDemo
```

Kết quả chính xác:

```text
system=system.dtd
public=public.dtd
uri=report.xsd
both=SYSTEM
publicFallback=PUBLIC
```

**Giải thích từng dòng:**

- `matchSystem` chọn `system.dtd` từ `systemId`; `matchPublic` độc lập chọn `public.dtd` từ `publicId`; `matchURI` chọn `report.xsd` từ URI. Đây là ba phép tra cứu trực tiếp, chưa phải thực thi xử lý XSD.
- Trường hợp `both`: XML mang cùng lúc public ID và system ID; catalog có cả hai mục. DOM parser nhờ `CatalogResolver` nạp DTD của **system**, nên `&where;` trở thành `SYSTEM`.
- Trường hợp `publicFallback`: system ID được đổi thành `.../unlisted.dtd` không khớp; `prefer=public` cho phép tìm theo public ID và nạp DTD còn lại, nên kết quả là `PUBLIC`.
- `ACCESS_EXTERNAL_DTD=""` hạn chế truy cập DTD không được phân giải qua tài nguyên đã kiểm soát; resolver ánh xạ tới file cục bộ. Đây là lớp bảo vệ bên cạnh catalog, không phải chính sách tra cứu `prefer`.

Nếu chạy với Java 9–16, thay cú pháp text block `"""` và suy luận biến `var` bằng cú pháp tương thích phiên bản đó; **API XML Catalog đã có từ Java 9**, còn ví dụ này cố ý dùng ngôn ngữ Java 17+.

## 6. Tích hợp với bộ xử lý XML trong ứng dụng

Có hai cách chuẩn: **gắn `CatalogResolver` trực tiếp** (đã dùng trong ví dụ), hoặc **cấu hình vị trí catalog trên XML processor của JDK** để processor tự dùng resolver. Các đoạn sau là **mảnh mã tích hợp**, được ghép vào phương thức đang có các import và biến cần thiết, không phải chương trình độc lập.

Giả sử `catalogFile` là một `Path` trỏ tới catalog. Lấy URI tuyệt đối:

```java
String catalogUri = catalogFile.toAbsolutePath().toUri().toString();
String catalogProperty = CatalogFeatures.Feature.FILES.getPropertyName();
```

| Bộ xử lý | Đăng ký catalog trên đối tượng | Loại tham chiếu tiêu biểu |
| --- | --- | --- |
| DOM | `DocumentBuilderFactory.setAttribute(catalogProperty, catalogUri)` | DTD, entity |
| SAX | `SAXParser.setProperty(catalogProperty, catalogUri)` | DTD, entity |
| StAX | `XMLInputFactory.setProperty(catalogProperty, catalogUri)` | Tham chiếu từ luồng XML |
| XSD | `SchemaFactory.setProperty(catalogProperty, catalogUri)` | `xs:include`, `xs:import` |
| XSLT | `TransformerFactory.setAttribute(catalogProperty, catalogUri)` | `xsl:include`, `xsl:import` |

Ví dụ sử dụng DOM mà không tự tạo resolver:

```java
DocumentBuilderFactory dbf = DocumentBuilderFactory.newInstance();
dbf.setNamespaceAware(true);
dbf.setAttribute(CatalogFeatures.Feature.FILES.getPropertyName(), catalogUri);
var builder = dbf.newDocumentBuilder();
// builder.parse(xmlSource); // xmlSource là InputSource/File do ứng dụng cung cấp
```

Với XSD, dùng API tương ứng:

```java
SchemaFactory sf = SchemaFactory.newInstance(
        XMLConstants.W3C_XML_SCHEMA_NS_URI);
sf.setProperty(CatalogFeatures.Feature.FILES.getPropertyName(), catalogUri);
// Schema schema = sf.newSchema(schemaFile);
```

Với XSLT:

```java
TransformerFactory tf = TransformerFactory.newInstance();
tf.setAttribute(CatalogFeatures.Feature.FILES.getPropertyName(), catalogUri);
// Transformer transformer = tf.newTransformer(stylesheetSource);
```

Khi dùng resolver tường minh, các điểm tích hợp tương đương gồm `DocumentBuilder.setEntityResolver(resolver)`, `XMLReader.setEntityResolver(resolver)`, `XMLInputFactory.setXMLResolver(resolver)`, `SchemaFactory.setResourceResolver(resolver)` và `TransformerFactory.setURIResolver(resolver)`. Chọn điểm cấu hình phù hợp với tài nguyên thực sự cần tải. Nhà cung cấp bộ xử lý XML khác JDK có thể có cách hỗ trợ khác; cần kiểm thử với implementation được dùng thực tế.

Các tùy chọn chuẩn trong `CatalogFeatures`:

| Feature | Giá trị | Ý nghĩa |
| --- | --- | --- |
| `FILES` | URI tuyệt đối của một/nhiều catalog (phân cách bằng `;`) | Khai báo vị trí catalog |
| `PREFER` | `public` (mặc định), `system` | Điều kiện xét public fallback |
| `DEFER` | `true` (mặc định), `false` | Hoãn/tải sớm các catalog phụ |
| `RESOLVE` | `strict` (mặc định), `continue`, `ignore` | Hành động khi không có ánh xạ |

Ngoài cấu hình theo từng processor, có thể đặt system property `javax.xml.catalog.files` với **URI file tuyệt đối**, ví dụ `-Djavax.xml.catalog.files=file:///opt/app/catalog.xml` (đường dẫn này chỉ là minh họa, phải thay theo hệ điều hành và nơi triển khai). `XMLConstants.USE_CATALOG` là cờ cho phép sử dụng catalog trên processor JDK; thông thường mặc định bật khi có cấu hình catalog. Cần phân biệt `javax.xml.catalog.resolve` của catalog người dùng với `jdk.xml.jdkcatalog.resolve` của **catalog dựng sẵn trong JDK**: đây là hai cấu hình khác nhau.

## 7. Ánh xạ khi có nhiều tên hoặc đường dẫn biến đổi

Với nhiều DTD/XSD cùng thư mục, không nhất thiết tạo hàng trăm mục `system`/`uri`. OASIS XML Catalog hỗ trợ các quy tắc sau (chỉ thêm những mục phù hợp với dữ liệu thực):

```xml
<rewriteSystem systemIdStartString="https://example.invalid/dtd/"
               rewritePrefix="dtd/"/>
<systemSuffix systemIdSuffix="/common.dtd" uri="dtd/common.dtd"/>

<rewriteURI uriStartString="https://example.invalid/schemas/"
            rewritePrefix="xsd/"/>
<uriSuffix uriSuffix="/shared.xsd" uri="xsd/shared.xsd"/>
```

- `rewriteSystem`/`rewriteURI` thay tiền tố URI khớp bằng `rewritePrefix`; phần đuôi còn lại được nối vào để xác định đích. Nếu nhiều prefix phù hợp, ưu tiên **prefix khớp dài nhất**.
- `systemSuffix`/`uriSuffix` nhận biết đuôi URI; nếu nhiều suffix khớp thì ưu tiên **suffix khớp dài nhất**. Quy tắc suffix hữu ích khi parser biến `common.dtd` tương đối thành URI tuyệt đối có đường dẫn nền khác nhau; nhưng dễ đụng tên nếu mọi dự án đều có `common.dtd`.
- `delegateSystem`, `delegatePublic`, `delegateURI` chuyển phần việc sang catalog khác; `nextCatalog` thêm catalog dự phòng. Hãy dùng khi tổ chức nhiều gói schema độc lập, không cần thiết cho một vài ánh xạ đơn giản.
- `xml:base` trên `catalog`/`group` điều chỉnh URI nền cho đích tương đối. Khi chuyển catalog sang một vị trí mới, kiểm tra lại các URI đích và việc đóng gói tệp.

Các mục rewrite và suffix cũng tuân thủ thứ tự/độ ưu tiên của resolver; một mapping `system` chính xác thường giải quyết ngay tài nguyên đó trước khi cần quy tắc tổng quát. Tránh tạo quy tắc rộng khiến các URI từ nguồn không tin cậy bị điều hướng tới tài nguyên ngoài ý muốn.

## 8. Không khớp catalog, xử lý lỗi và an toàn

Nếu không có ánh xạ, `RESOLVE` quyết định hành vi của `CatalogResolver`:

- **`strict`:** báo `CatalogException` khi không tìm được tài nguyên. Phù hợp khi ứng dụng yêu cầu mọi tham chiếu ngoài được khai báo và không muốn fallback im lặng.
- **`continue`:** trả quyền điều khiển cho XML processor tiếp tục xử lý theo cơ chế thông thường; nếu chính sách truy cập ngoài cho phép, nó có thể thử URI gốc.
- **`ignore`:** yêu cầu bỏ qua tham chiếu trong những API có hỗ trợ. Không được giả định mọi bộ phân giải đều có thể bỏ qua: trong giao diện StAX `XMLResolver` và DOM LS `LSResourceResolver`, hành vi của `ignore` có thể tương đương `continue`.

**Catalog không thay thế biện pháp bảo mật XML.** Khi xử lý dữ liệu không tin cậy, hãy xác định có thực sự cần DTD/entity ngoài hay không; nếu không cần, vô hiệu hóa chúng theo API parser phù hợp. Nếu cần, chỉ ánh xạ sang tài nguyên đã kiểm soát, ưu tiên `strict` khi yêu cầu toàn bộ tham chiếu phải nằm trong catalog, bật xử lý an toàn và giới hạn giao thức truy cập ngoài qua:

- `XMLConstants.FEATURE_SECURE_PROCESSING` trên factory có hỗ trợ.
- `XMLConstants.ACCESS_EXTERNAL_DTD` đối với DTD/entity.
- `XMLConstants.ACCESS_EXTERNAL_SCHEMA` đối với schema.
- `XMLConstants.ACCESS_EXTERNAL_STYLESHEET` đối với stylesheet.

Giá trị rỗng `""` cho thuộc tính external access thường mang nghĩa không cho giao thức ngoài nào; một danh sách như `"file"` chỉ cho phép giao thức đó khi cần. Hãy kiểm tra cấu hình cụ thể của DOM/SAX/StAX/XSD/XSLT; các cơ chế hạn chế của từng loại không hoàn toàn đồng nhất. Đặc biệt, **`continue` không đồng nghĩa “không dùng mạng”**, và ánh xạ sai hoặc file đích không tồn tại có thể vẫn gây lỗi parse.

## 9. Chẩn đoán các lỗi thường gặp

| Hiện tượng | Nguyên nhân hay gặp | Cách kiểm tra |
| --- | --- | --- |
| Parser vẫn tìm URL trên mạng | Catalog không được đăng ký, URI lookup không khớp, hoặc dùng `continue` | Xác minh `CatalogFeatures.Feature.FILES`, resolver đang gắn và chính sách khi miss |
| Có mục `public` nhưng DTD khác được chọn | Có mục `system` khớp; system thắng public | Xem **cả hai** giá trị trong `DOCTYPE PUBLIC "P" "S"` |
| `public` không được chọn khi system miss | `prefer=system` hoặc `publicId` thực tế khác | Kiểm tra chính tả public ID và `prefer=public` |
| `systemId` có vẻ đúng mà không match | Parser đã chuẩn hóa đường dẫn tương đối thành URI tuyệt đối | Log system ID thực tế; dùng `systemSuffix` có phạm vi hẹp nếu phù hợp |
| Catalog có XML hợp lệ nhưng không hoạt động | Sai namespace của catalog, URI catalog không tuyệt đối, hoặc entry sai cú pháp | So sánh namespace chuẩn, dùng `Path.toUri()`, kiểm tra `matchSystem`/`matchPublic`/`matchURI` |
| Match được nhưng vẫn báo không nạp được tệp | URI đích tương đối sai base, file chưa được đóng gói hoặc không có quyền đọc | Xem `xml:base`, đường dẫn tính từ vị trí catalog, tồn tại và quyền truy cập của tệp |
| XSD import hay XSLT include chưa được ánh xạ | Đang map namespace thay vì `schemaLocation`/`href` hoặc cấu hình nhầm parser | Xác định giá trị lookup thật và cấu hình `SchemaFactory`/`TransformerFactory` tương ứng |

Một quy trình debug gọn: (1) ghi lại `publicId`, `systemId` hoặc `href` thực tế; (2) thử `Catalog.matchXxx(...)` trên từng loại tương ứng; (3) xác định quy tắc ưu tiên với `prefer`; (4) kiểm tra URI đích tuyệt đối sau khi phân giải base; (5) kiểm tra chính sách `RESOLVE`, external access và bộ xử lý XML.

## 10. Tự kiểm tra

**Bài 1.** XML có `PUBLIC "P" "S"`; catalog chứa cả `system(S) -> a.dtd` và `public(P) -> b.dtd`; `prefer=public`. File nào được chọn? **Đáp án:** `a.dtd`, vì có system match.

**Bài 2.** Giữ nguyên public ID nhưng đổi system ID sang `S2` không khớp; `prefer=public`. File nào? **Đáp án:** `b.dtd` nếu mục public khớp và tài nguyên tồn tại.

**Bài 3.** Một `xs:include schemaLocation="https://example.invalid/schemas/common.xsd"` cần bản sao local. Mục nào biểu đạt trực tiếp nhất? **Đáp án:** `<uri name="https://example.invalid/schemas/common.xsd" uri="xsd/common.xsd"/>`; cấu hình catalog trên thành phần xử lý XSD. Không lấy namespace URI làm khóa trừ khi đó thực sự là URI mà resolver đang tra.

**Bài 4.** Mục `systemId="common.dtd"` không khớp khi parser truyền `file:/data/input/common.dtd`. Khắc phục? **Đáp án:** ưu tiên dùng khóa systemId tuyệt đối đúng với URI thực tế, hoặc cân nhắc `systemSuffix` đủ đặc thù; không nên sửa XML gốc chỉ để che lỗi cấu hình base.

## Tài liệu tham khảo đang được hỗ trợ

- [JDK 26 — `javax.xml.catalog` package](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/catalog/package-summary.html): API chuẩn được giới thiệu từ Java 9.
- [JDK 26 — `Catalog`](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/catalog/Catalog.html): các kiểu entry và quy tắc khớp.
- [JDK 26 — `CatalogResolver`](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/catalog/CatalogResolver.html): thứ tự tìm và hành vi khi không khớp.
- [JDK 21 — dùng catalog với XML processors](https://docs.oracle.com/en/java/javase/21/core/use-catalog-xml-processors.html): ví dụ cấu hình DOM/SAX/StAX/XSD/XSLT vẫn dùng được trong Java hiện đại.
- [JDK 26 — JAXP Security Guide](https://docs.oracle.com/en/java/javase/26/security/java-api-xml-processing-jaxp-security-guide.html): xử lý an toàn và giới hạn truy cập tài nguyên ngoài.

Mấu chốt cần vận dụng: **xác định đúng loại khóa mà parser đang gửi, viết mapping đến URI đích thật, hiểu rằng system match được xét trước public fallback, rồi kiểm tra hành vi miss và chính sách truy cập ngoài.**
