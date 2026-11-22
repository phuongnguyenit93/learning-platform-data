# XML Catalog trong Java 9+: `CatalogFeatures` và chính sách khi không tìm thấy

## 1. Bài toán cần giải quyết

XML có thể tham chiếu tài nguyên nằm ngoài tài liệu: DTD trong `DOCTYPE`, external entity, XSD được `include`/`import`, stylesheet XSLT hoặc tài nguyên dùng bởi `document()`. Nếu mỗi lần xử lý đều tải URI gốc qua mạng, ứng dụng có thể chậm, không chạy được khi offline và khó kiểm soát tài nguyên nào được phép truy cập.

**XML Catalog** là bảng ánh xạ định danh bên ngoài (public ID, system ID hoặc URI) sang một tài nguyên khác, thường là bản sao cục bộ do ứng dụng kiểm soát. Java cung cấp API chuẩn trong module `java.xml`, package `javax.xml.catalog` **từ Java 9 và vẫn được hỗ trợ trên các JDK hiện hành**. Các thành phần chính:

- `Catalog`: mô hình catalog, được tạo và sử dụng để tìm ánh xạ.
- `CatalogFeatures`: các tùy chọn điều khiển danh sách catalog, cách tìm và cách xử lý khi không khớp.
- `CatalogManager`: tạo `Catalog` hoặc `CatalogResolver`.
- `CatalogResolver`: kết nối catalog với các giao diện resolver quen thuộc của SAX, StAX, DOM LS và XSLT.

**Phân biệt hai trường hợp:** “không tìm thấy” trong bài này nghĩa là **không có mục nào trong các catalog khớp định danh được yêu cầu**. Trường hợp *có ánh xạ nhưng tệp đích bị xóa, không đọc được hoặc XML/DTD đích sai cú pháp* là lỗi khác; đặt `RESOLVE=ignore` không tự sửa lỗi tài nguyên đã được ánh xạ.

## 2. Cơ chế tìm và các loại mục catalog

Một catalog theo XML Catalogs OASIS v1.1 thường có dạng:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<catalog xmlns="urn:oasis:names:tc:entity:xmlns:xml:catalog">
    <system systemId="https://example.invalid/dtd/book.dtd"
            uri="book.dtd"/>
    <public publicId="-//EXAMPLE//DTD Book 1.0//EN"
            uri="book.dtd"/>
    <uri name="https://example.invalid/schema/book.xsd"
         uri="schema/book.xsd"/>
</catalog>
~~~

- `system` ánh xạ `systemId` (ví dụ URL của DTD); `public` ánh xạ `publicId`; `uri` ánh xạ URI (thường dùng với XSD, XSLT, XInclude). Cũng có các mục `rewriteSystem`, `systemSuffix`, `rewriteURI`, `uriSuffix` và catalog thay thế để xử lý nhóm định danh.
- Trong ví dụ, `book.dtd` và `schema/book.xsd` là **URI tương đối so với vị trí của catalog**; phải thực sự có các tệp tương ứng khi parser cần đọc.
- `CatalogResolver` ưu tiên tìm các mục kiểu `system`, sau đó cân nhắc `public` theo `PREFER`, rồi tìm mục kiểu `uri`; nó có thể duyệt các catalog ủy quyền hoặc tiếp nối khi catalog hiện tại không khớp. Một mục khớp được sử dụng mà không cần thử tiếp các mục ở sau.
- Nếu ứng dụng đã gắn custom resolver vào bộ xử lý XML, JAXP gọi resolver đó trước; khi nó trả `null`, bộ xử lý mới có thể thử catalog. Nếu custom resolver đã cung cấp tài nguyên (kể cả nguồn rỗng), catalog không được hỏi tiếp.

## 3. Bốn `CatalogFeatures.Feature` còn áp dụng hiện nay

| Feature | Thuộc tính / giá trị | Mặc định và tác dụng |
|---|---|---|
| `FILES` | `javax.xml.catalog.files` = danh sách URI tuyệt đối, ngăn cách bởi dấu `;` | Không có catalog mặc định riêng do `FILES` chỉ định. Chỉ tới các tệp catalog; catalog đầu là catalog chính. Nên dùng `Path.toUri()` thay vì chuỗi đường dẫn hệ điều hành. |
| `PREFER` | `javax.xml.catalog.prefer` = `public` hoặc `system` | `public`. **Không có nghĩa public luôn thắng system**: mục `system` khớp vẫn được xét trước; khi `public` được ưu tiên, public ID có thể được xét nếu system không khớp. |
| `DEFER` | `javax.xml.catalog.defer` = `true` hoặc `false` | `true`: nạp catalog thay thế khi cần; `false`: nạp các catalog thay thế sớm. Tùy chọn về thời điểm nạp, không phải chính sách xử lý lỗi. |
| `RESOLVE` | `javax.xml.catalog.resolve` = `strict`, `continue` hoặc `ignore` | `strict`: quyết định điều gì xảy ra sau khi đã tìm hết các catalog được cấu hình mà không có ánh xạ. |

Các giá trị nêu trên **phân biệt chữ hoa/chữ thường** và phải đúng cú pháp; giá trị `RESOLVE` như `STRICT` hoặc `skip` không hợp lệ và có thể gây `IllegalArgumentException` ngay khi cấu hình. Có thể lấy tên thuộc tính từ `Feature.RESOLVE.getPropertyName()` để tránh gõ sai.

Tạo một bộ cấu hình bằng API:

~~~java
import javax.xml.catalog.CatalogFeatures;
import javax.xml.catalog.CatalogFeatures.Feature;
import java.nio.file.Path;

// Đoạn minh họa: đặt trong một phương thức Java thích hợp.
String catalogUri = Path.of("catalog.xml").toAbsolutePath().toUri().toString();

CatalogFeatures features = CatalogFeatures.builder()
        .with(Feature.FILES, catalogUri)
        .with(Feature.PREFER, "public")
        .with(Feature.DEFER, "true")
        .with(Feature.RESOLVE, "strict")
        .build();
~~~

`CatalogFeatures.defaults()` cung cấp cấu hình mặc định; `features.get(Feature.RESOLVE)` cho biết giá trị của feature. Khi dùng `CatalogManager.catalogResolver(features, uri1, ...)`, các URI catalog truyền trực tiếp cho phương thức được dùng làm đầu vào catalog, thay cho danh sách `FILES` trong builder.

## 4. Trọng tâm: ba chính sách `RESOLVE` khi không khớp

| `RESOLVE` | Kết quả ở `CatalogResolver.resolveEntity(publicId, systemId)` của SAX | Ý nghĩa khi chạy |
|---|---|---|
| `strict` (**mặc định**) | Ném `CatalogException` | Dừng việc phân giải tham chiếu chưa có ánh xạ; phù hợp khi mọi tài nguyên bên ngoài đều phải có trong catalog. |
| `continue` | Trả `null` | Cho phép bộ xử lý tiếp tục cơ chế phân giải bình thường, có thể thử URI gốc hoặc resolver khác. **Không bảo đảm xử lý thành công hay không truy cập mạng.** |
| `ignore` | Trả `InputSource` chứa `Reader` rỗng | Yêu cầu bỏ qua tham chiếu bên ngoài theo cách được SAX hỗ trợ; phù hợp khi tài nguyên thực sự là tùy chọn. |

Ví dụ: tài liệu chứa `<!DOCTYPE book SYSTEM "https://example.invalid/dtd/missing.dtd">`, nhưng catalog chỉ ánh xạ `book.dtd`. Khi đó `strict` báo lỗi không tìm thấy ánh xạ; `continue` để parser thử cách xử lý thông thường (có thể lỗi do không truy cập được URL); `ignore` có thể cho SAX bỏ qua DTD thiếu. Với XML cần khai báo entity hoặc ràng buộc từ DTD, việc bỏ qua này vẫn có thể dẫn đến XML không hợp lệ hoặc mất dữ liệu cần thiết.

**Hành vi `ignore` khác nhau theo giao diện resolver, không nên khái quát rằng nó luôn bỏ qua được tài nguyên:**

- **SAX `EntityResolver`:** `ignore` trả nguồn rỗng; `continue` trả `null`.
- **StAX `XMLResolver`:** khi không khớp, cả `ignore` và `continue` đều trả `null`; giao diện này không có khả năng trực tiếp biểu diễn thao tác “bỏ qua”, nên hai giá trị được đối xử tương tự.
- **DOM LS `LSResourceResolver`:** khi không khớp, `ignore` cũng được đối xử như `continue` và trả `null`.
- **XSLT `URIResolver`:** `ignore` trả `Source` rỗng; `continue` trả `Source` trỏ tới URI ban đầu (kết hợp `base` nếu thích hợp).
- **`strict`:** `CatalogResolver` ném `CatalogException` khi không tìm thấy ánh xạ, bất kể giao diện nói trên; bộ xử lý gọi nó có thể đóng gói lỗi thêm ở tầng trên.

Vì vậy, **`RESOLVE` là chính sách của catalog resolver**, không phải công tắc bảo đảm mọi parser có cùng cách “skip” hay thay thế cho kiểm soát truy cập tài nguyên.

## 5. Ví dụ chạy được trên Java 17+ và các JDK hiện hành

Tạo **bốn tệp trong cùng một thư mục**. Ví dụ dùng domain `example.invalid` chỉ làm định danh; khi có ánh xạ, parser đọc DTD tại chỗ, không cần mạng.

**Tệp `catalog.xml`:**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<catalog xmlns="urn:oasis:names:tc:entity:xmlns:xml:catalog">
    <system systemId="https://example.invalid/dtd/book.dtd"
            uri="book.dtd"/>
</catalog>
~~~

**Tệp `book.dtd`:**

~~~dtd
<!ELEMENT book (#PCDATA)>
~~~

**Tệp `book.xml`:**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE book SYSTEM "https://example.invalid/dtd/book.dtd">
<book>XML Catalog offline</book>
~~~

**Tệp `CatalogResolveDemo.java`:**

~~~java
import java.nio.file.Path;
import java.util.List;
import javax.xml.XMLConstants;
import javax.xml.catalog.CatalogException;
import javax.xml.catalog.CatalogFeatures;
import javax.xml.catalog.CatalogFeatures.Feature;
import javax.xml.catalog.CatalogManager;
import javax.xml.catalog.CatalogResolver;
import javax.xml.parsers.DocumentBuilderFactory;
import org.xml.sax.InputSource;

public class CatalogResolveDemo {
    public static void main(String[] args) throws Exception {
        var catalogUri = Path.of("catalog.xml").toAbsolutePath().toUri();

        // So sánh cùng một catalog và cùng một ID không có ánh xạ.
        for (String policy : List.of("strict", "continue", "ignore")) {
            CatalogFeatures features = CatalogFeatures.builder()
                    .with(Feature.RESOLVE, policy)
                    .build();

            CatalogResolver resolver =
                    CatalogManager.catalogResolver(features, catalogUri);

            InputSource hit = resolver.resolveEntity(
                    null, "https://example.invalid/dtd/book.dtd");
            System.out.print(policy + ": matched="
                    + (hit != null && hit.getSystemId() != null)
                    + ", missing=");

            try {
                InputSource miss = resolver.resolveEntity(
                        null, "https://example.invalid/dtd/missing.dtd");
                if (miss == null) {
                    System.out.println("null");
                } else if (miss.getCharacterStream() != null) {
                    System.out.println("empty InputSource");
                } else {
                    System.out.println("other InputSource");
                }
            } catch (CatalogException ex) {
                System.out.println("CatalogException");
            }
        }

        // Tích hợp native catalog với DOM: URL DTD được ánh xạ về book.dtd.
        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
        factory.setAttribute(Feature.FILES.getPropertyName(),
                catalogUri.toString());
        factory.setAttribute(Feature.RESOLVE.getPropertyName(), "strict");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");

        var document = factory.newDocumentBuilder()
                .parse(Path.of("book.xml").toFile());
        System.out.println("DOM: "
                + document.getDocumentElement().getTextContent().trim());
    }
}
~~~

Biên dịch và chạy **từ thư mục có bốn tệp**:

~~~bash
javac CatalogResolveDemo.java
java CatalogResolveDemo
~~~

Kết quả stdout:

~~~text
strict: matched=true, missing=CatalogException
continue: matched=true, missing=null
ignore: matched=true, missing=empty InputSource
DOM: XML Catalog offline
~~~

Giải thích:

1. Cả ba resolver đều tìm được `book.dtd`, bởi vậy `matched=true`. Chính sách không tìm thấy không can thiệp một ánh xạ thành công.
2. Với định danh `missing.dtd`, `strict` ném ngoại lệ, `continue` trả `null`, còn `ignore` trả nguồn SAX rỗng. Chương trình gọi trực tiếp resolver nên không thử kết nối mạng cho trường hợp `continue`.
3. Phần DOM đăng ký catalog qua thuộc tính `FILES` của factory. Dù tài liệu dùng URL `https://example.invalid/...`, catalog dẫn tới DTD cục bộ. Cấu hình `ACCESS_EXTERNAL_DTD=""` hạn chế việc truy cập DTD bên ngoài qua các giao thức ngoài cơ chế resolver được cung cấp; đây là **kiểm soát bổ sung**, không phải một giá trị `RESOLVE`.

Lưu ý: mã Java trên là chương trình độc lập; `CatalogFeatures` và `CatalogResolver` nằm sẵn trong module `java.xml`, không phải tải thư viện ngoài. Môi trường module có `module-info.java` thì khai báo `requires java.xml;`.

## 6. Dùng `CatalogFeatures` với bộ xử lý XML thực tế

Có hai hướng dùng phổ biến:

**A. Cho JAXP tự sử dụng catalog:** đặt `Feature.FILES.getPropertyName()` và `Feature.RESOLVE.getPropertyName()` trên factory/parser hỗ trợ `setAttribute` hoặc `setProperty`, như ví dụ `DocumentBuilderFactory` ở trên. `XMLConstants.USE_CATALOG` mặc định là `true` trong JDK; catalog chỉ được sử dụng khi tính năng đó bật **và** có tệp catalog hợp lệ được chỉ định. Có thể cấu hình riêng cho SAX, StAX, DOM, schema validation, XSLT qua API tương ứng.

**B. Tạo resolver tường minh:** dùng `CatalogManager.catalogResolver(features, catalogUri)`, sau đó gắn resolver vào `XMLReader.setEntityResolver(...)`, `XMLInputFactory.setXMLResolver(...)`, `SchemaFactory.setResourceResolver(...)` hoặc `TransformerFactory.setURIResolver(...)` theo nhu cầu. Chọn cách này khi muốn kiểm soát rõ một chuỗi resolver; nhớ thứ tự ưu tiên custom resolver và catalog nếu kết hợp các cơ chế.

Không phải tất cả factory đều có chung tên phương thức thiết lập thuộc tính; dùng chính API mà factory/parser đó công bố. Nếu Java code tự tạo `CatalogResolver` thì `Feature.RESOLVE` truyền trong builder điều khiển resolver đó; nếu JAXP tự kích hoạt catalog, thuộc tính thiết lập trên factory/processor là đầu vào cần kiểm tra.

## 7. Phạm vi và mức ưu tiên cấu hình

Có thể thiết lập các giá trị qua:

- API (`CatalogFeatures.builder().with(...)` hoặc thuộc tính trên JAXP factory/processor);
- system property, ví dụ `-Djavax.xml.catalog.resolve=continue`;
- tệp cấu hình JAXP, thường ở `$JAVA_HOME/conf/jaxp.properties`;
- một số thuộc tính trực tiếp của **catalog chính** (ví dụ `prefer`, `defer`, `resolve`).

Trong cấu hình JAXP thông thường, API có độ ưu tiên cao hơn system property, rồi đến tệp cấu hình và giá trị mặc định. **Riêng thuộc tính được khai báo trong catalog XML có thể ưu tiên hơn các nguồn trên**. Chẳng hạn, khi `<catalog resolve="continue">` đã khai báo, không nên chỉ nhìn vào đoạn Java đặt `RESOLVE=strict` rồi kết luận chắc chắn chính sách đang chạy là strict. Để ví dụ minh bạch, `catalog.xml` ở phần 5 không khai báo thuộc tính `resolve`.

Khi dùng `Feature.FILES` dưới dạng system property, giá trị là một hay nhiều **URI tuyệt đối**, ví dụ `file:///opt/app/catalog/catalog.xml`; không đưa nguyên đường dẫn Windows `C:\...` làm URI. `PREFER` không có system property tương ứng trong bảng feature chuẩn; nên cấu hình qua API hoặc thuộc tính được hỗ trợ trong catalog.

**Phân biệt catalog do ứng dụng khai báo với catalog dựng sẵn của JDK:** trên JDK hiện hành, resolver của catalog dựng sẵn có thuộc tính riêng `jdk.xml.jdkcatalog.resolve` (mặc định `continue`). Không đồng nhất thuộc tính này với `javax.xml.catalog.resolve`, vốn quy định cách resolver của catalog ứng dụng xử lý khi không khớp và mặc định là `strict`.

## 8. Chọn chính sách theo tình huống

| Tình huống | Lựa chọn hợp lý | Điều cần kiểm soát |
|---|---|---|
| Ứng dụng cần parse offline, tài nguyên có danh sách xác định, CI phải phát hiện thiếu catalog | `strict` | Gắn đủ DTD/XSD/XSLT được dùng; kiểm tra đường dẫn đích và lỗi đọc tệp. |
| Hệ thống có catalog tăng tốc nhưng vẫn chủ động cho phép fallback đến nguồn ngoài đáng tin | `continue` | Thời gian chờ, truy cập mạng, allowlist/giao thức, hành vi khi URL gốc lỗi. |
| SAX xử lý XML có DTD ngoài thật sự tùy chọn và muốn bỏ qua khi catalog không khớp | `ignore` | Dữ liệu/entity/validation phụ thuộc DTD có thể thiếu; thử trên parser thực tế. |
| Dùng StAX hoặc DOM LS và tưởng `ignore` luôn ngăn truy cập ngoài | Không dựa riêng vào `ignore` | Với các resolver này, `ignore` có thể hoạt động như `continue`; dùng cơ chế chặn truy cập tài nguyên phù hợp. |

**Bảo mật:** catalog giúp ánh xạ tài nguyên nhưng tự nó không phải biện pháp chống XXE hay bảo đảm không có I/O mạng. Khi đầu vào XML không đáng tin, cấu hình các giới hạn tài nguyên bên ngoài và các tính năng parser phù hợp, ví dụ `XMLConstants.ACCESS_EXTERNAL_DTD`, `XMLConstants.ACCESS_EXTERNAL_SCHEMA` và chính sách xử lý DTD/entity. `continue` đặc biệt cần được xem xét vì có thể dẫn đến fallback sang URI gốc. Khi xử lý tài liệu không cần DTD, có thể chặn DTD theo yêu cầu ứng dụng thay vì dùng `ignore` để che một tham chiếu thiếu.

## 9. Lỗi phổ biến và cách kiểm tra

1. **Sai ID nên catalog không khớp:** so sánh chính xác `systemId`/`publicId`/`href` mà parser cung cấp. Với URI tương đối, parser có thể đổi thành URI tuyệt đối; khi thích hợp, sử dụng mục `systemSuffix` hay `uriSuffix` có phạm vi đủ hẹp.
2. **Thiếu file catalog hoặc ánh xạ sang file không tồn tại:** kiểm tra URI của catalog, namespace OASIS, đường dẫn tương đối tính từ catalog và quyền đọc tệp. Thiếu ánh xạ khác với lỗi mở file đích.
3. **Dùng `PREFER=public` rồi mong public thắng mọi system:** mục system khớp vẫn được tìm trước theo chuẩn.
4. **Đặt `RESOLVE=continue` rồi mong ứng dụng luôn chạy:** `continue` chỉ cho phép thử cơ chế phân giải tiếp theo; mạng, chính sách bảo mật, cú pháp hoặc validation vẫn có thể làm parser lỗi.
5. **Đặt `RESOLVE=ignore` rồi tin StAX/LSResourceResolver sẽ bỏ qua:** kiểm tra giao diện resolver; ở StAX và DOM LS, giá trị này không thể hiện thao tác skip giống SAX.
6. **Chỉ cấu hình `RESOLVE` nhưng không khai báo catalog hợp lệ:** JAXP không có catalog để tìm; chính sách của catalog không tự tạo một ánh xạ.
7. **Cấu hình bị ghi đè:** kiểm tra thuộc tính `resolve` trong catalog chính, setting trên factory, system property, `jaxp.properties` và custom resolver được gắn vào parser.
8. **Che lỗi cấu hình bằng `ignore`:** khi phát triển nên dùng `strict` với bộ kiểm thử có cả ID khớp và không khớp, sau đó mới chọn chính sách production theo mục đích.

## 10. Câu hỏi tự kiểm tra

- Một ánh xạ `system` đã khớp: ba giá trị `RESOLVE` có khác kết quả không? **Không**; `RESOLVE` chỉ quyết định khi không còn ánh xạ phù hợp.
- `continue` có đồng nghĩa “bỏ qua DTD” không? **Không**; nó cho phép parser tiếp tục cơ chế phân giải, có thể truy cập URI gốc.
- `ignore` trên `XMLResolver` của StAX có luôn chặn external resource không? **Không**; khi không khớp nó được xử lý như `continue`, trả `null`.
- Vì sao không dùng đường dẫn `C:\app\catalog.xml` trực tiếp cho `FILES`? Vì `FILES` yêu cầu **URI tuyệt đối**; sử dụng `Path.toUri()`.
- Có thể dùng API này mà không cài dependency ngoài không? **Có**; `javax.xml.catalog` thuộc module `java.xml` của Java 9+.

## Tài liệu tham khảo hiện hành

- [Java SE 26 — `CatalogFeatures`](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/catalog/CatalogFeatures.html): feature, giá trị mặc định, mức ưu tiên và JAXP.
- [Java SE 26 — `CatalogResolver`](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/catalog/CatalogResolver.html): thứ tự tìm và khác biệt xử lý lỗi theo từng giao diện.
- [Java SE 26 — `CatalogManager`](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/catalog/CatalogManager.html): tạo resolver với features/catalog URI.
- [Java SE 26 — `XMLConstants`](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/XMLConstants.html): `USE_CATALOG` và các thuộc tính giới hạn truy cập tài nguyên ngoài.
- [Java SE 26 — JAXP Security Guide](https://docs.oracle.com/en/java/javase/26/security/java-api-xml-processing-jaxp-security-guide.html): kiểm soát truy cập XML ngoài và catalog dựng sẵn của JDK.
