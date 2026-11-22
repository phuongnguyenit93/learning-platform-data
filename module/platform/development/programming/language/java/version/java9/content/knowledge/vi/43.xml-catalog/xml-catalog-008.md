# Kiểm thử ánh xạ, tài nguyên thiếu và đầu vào ngoài hợp đồng với XML Catalog (Java 9+)

XML Catalog giúp bộ xử lý XML tìm tài nguyên bên ngoài (DTD, XSD, XSLT…) thông qua một bảng ánh xạ có kiểm soát, chẳng hạn biến định danh `https://example.invalid/xml/invoice.dtd` thành tệp `invoice.dtd` được đóng gói cùng ứng dụng. Khi kiểm thử, cần phân biệt **có ánh xạ**, **có thể đọc tài nguyên đích**, và **bộ xử lý XML thật sự dùng đúng tài nguyên**. Ba việc này không tương đương.

Bài tập trung vào API `javax.xml.catalog` thuộc module `java.xml`, có từ Java 9 và vẫn dùng trong Java hiện đại (Java 17/21+). Ví dụ sử dụng DTD để quan sát hành vi rõ ràng; cùng nguyên tắc áp dụng cho XSD import/include, XSLT import/include và các bộ xử lý JAXP tương ứng.

## 1. Xác định hợp đồng trước khi viết test

Giả sử ứng dụng chỉ chấp nhận tài liệu có DTD định danh:

```text
https://example.invalid/xml/invoice.dtd
```

Catalog có mục:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<catalog xmlns="urn:oasis:names:tc:entity:xmlns:xml:catalog">
    <system systemId="https://example.invalid/xml/invoice.dtd"
            uri="invoice.dtd"/>
</catalog>
```

Đường dẫn `invoice.dtd` ở đây được tính tương đối từ vị trí **tệp catalog**, không phải thư mục làm việc ngẫu nhiên của tiến trình. Nội dung DTD ví dụ:

```dtd
<!ELEMENT invoice (#PCDATA)>
<!ENTITY origin "FROM_LOCAL_DTD">
```

Và tài liệu XML sử dụng nó:

```xml
<!DOCTYPE invoice SYSTEM "https://example.invalid/xml/invoice.dtd">
<invoice>&origin;</invoice>
```

Kết quả mong đợi khi parse là nội dung nút `invoice` bằng `FROM_LOCAL_DTD`. Giá trị này là dấu hiệu cho thấy parser đã đọc đúng DTD nội bộ; chỉ kiểm tra rằng resolver trả về một URI chưa đủ.

Luồng xử lý cần kiểm thử:

```text
XML có external ID
    -> CatalogResolver tìm mục khớp
    -> trả về URI hoặc nguồn tài nguyên đích
    -> parser mở/đọc tài nguyên
    -> DTD/XSD/XSLT được sử dụng theo ngữ nghĩa của bộ xử lý
```

**Hợp đồng đầu vào** nên ghi rõ: loại tài nguyên được hỗ trợ; tập định danh bên ngoài được phép; quy tắc `publicId`/`systemId`/`URI`; cách xử lý khi không tìm thấy; có cho phép fallback ra mạng hay không; và kết quả cần khẳng định ở tầng parser. XML Catalog là cơ chế phân giải tài nguyên, **không tự động là tường lửa chặn mọi truy cập mạng hay mọi kiểu tấn công XML**.

## 2. Các API và chế độ liên quan tới kiểm thử

- `CatalogFeatures.builder()` cấu hình catalog; `Feature.FILES` nhận URI tuyệt đối của tệp catalog (hoặc danh sách URI phân cách bằng dấu chấm phẩy). Dùng `path.toUri().toString()` để tránh nhầm đường dẫn hệ điều hành với URI.
- `CatalogManager.catalogResolver(features)` tạo `CatalogResolver`. Resolver này hỗ trợ `EntityResolver` (SAX/DOM), `XMLResolver` (StAX), `LSResourceResolver` (schema) và `URIResolver` (transform).
- Với định danh `system`, resolver tìm các mục hệ thống (`system`, `rewriteSystem`, `systemSuffix`) trước; nếu phù hợp, mới xét `public` theo thuộc tính `prefer`; tiếp theo có thể tìm các mục `uri`. Vì vậy không được mặc định rằng `prefer="public"` sẽ thắng một `system` khớp.
- Tài liệu chỉ định URI tương đối có thể được parser chuyển thành tuyệt đối dựa trên base URI trước khi tra cứu. Test phải dùng đúng chuỗi ID parser truyền cho resolver; không tự giả định phần đuôi tên tệp luôn khớp. `systemSuffix`/`uriSuffix` chỉ thích hợp nếu quy tắc hậu tố thực sự thuộc hợp đồng và không gây trùng đích.
- `Feature.RESOLVE` quyết định phản ứng **khi không có mục khớp**, không bảo đảm tệp đích tồn tại. Giá trị mặc định là `strict`.

| `RESOLVE` | Kết quả khi không khớp đối với `EntityResolver.resolveEntity(publicId, systemId)` | Hệ quả cần kiểm thử |
| --- | --- | --- |
| `strict` | Ném `CatalogException` | Fail fast; thích hợp cho test yêu cầu mọi external ID phải được khai báo. |
| `continue` | Trả `null` | Parser có thể dùng cách phân giải tiếp theo; **không đồng nghĩa với từ chối truy cập mạng**. |
| `ignore` | Trả `InputSource` rỗng | Tham chiếu bị bỏ qua theo hợp đồng SAX; nếu tài liệu cần DTD/entity đó, parse có thể tiếp tục lỗi. |

Lưu ý: bảng trên mô tả **SAX `EntityResolver`**. Với `XMLResolver` của StAX hoặc `LSResourceResolver`, hành vi `ignore` không giống hoàn toàn: ở đường đi tương ứng, nó có thể trả `null` giống `continue`. Không viết một assertion chung cho mọi API chỉ dựa vào tên chế độ.

## 3. Ma trận kiểm thử bắt buộc theo hợp đồng

| Nhóm | Đầu vào hoặc fixture | Điều cần khẳng định |
| --- | --- | --- |
| Ánh xạ chính xác | `systemId` đã khai báo và tệp local tồn tại | Resolver trả nguồn đúng URI local; parse tạo kết quả mong đợi, ví dụ `FROM_LOCAL_DTD`. |
| Phân giải `public`/`system` | Có cả hai ID và các mục ánh xạ riêng | Thứ tự ưu tiên đúng theo quy tắc API, không suy đoán từ tên thuộc tính `prefer`. |
| URI dùng cho XSD/XSLT | `uri`/`rewriteURI` với href/import cụ thể | Bộ xử lý thực tế dùng tài nguyên mong đợi; kiểm tra cả base URI khi có include/import. |
| Không có mục ánh xạ | ID không xuất hiện trong catalog | `strict` ném `CatalogException` ở tầng resolver; `continue`/`ignore` đúng kiểu kết quả của API đang kiểm thử. |
| Có mục nhưng thiếu tệp đích | Catalog trỏ tới `absent.dtd` không tồn tại | Lookup có thể thành công, nhưng parse/load phải thất bại; phân loại đây là **thiếu tài nguyên đích**, khác với **thiếu ánh xạ**. |
| ID ngoài hợp đồng | `null`, `file:///...`, host/đường dẫn khác, ID thừa fragment | Tầng kiểm tra hợp đồng từ chối trước khi parser fallback; không tự mở URI lạ. |
| Khác biệt biểu diễn ID | ID tương đối/tuyệt đối, chữ hoa-thường, percent-encoding, URI có base khác | Chỉ cách biểu diễn đã được định nghĩa mới được chấp nhận; không dùng so khớp hậu tố quá rộng. |
| Catalog hỏng hoặc đặt sai chỗ | FILES sai, file không tồn tại, XML catalog sai cú pháp | Không coi test là PASS chỉ vì parser cuối cùng vẫn hoàn thành nhờ một cơ chế khác; bắt buộc có test khẳng định mapping dương tính. |
| Tài nguyên đích sai nội dung | Mapping trỏ tới DTD/schema khác nhưng hợp lệ | Assertion phải kiểm tra tác động ngữ nghĩa hoặc dấu hiệu đặc trưng của đúng fixture, thay vì chỉ kiểm tra không ném lỗi. |
| Tài liệu XML ngoài hợp đồng | Sai root, XML không well-formed, DOCTYPE không được phép, entity độc hại | Kiểm tra quy tắc nhập liệu/bảo mật riêng; catalog không thay thế kiểm tra cú pháp, schema hay chính sách DTD. |

Đối với test ngoại lệ, kiểm tra **đúng tầng** và **đúng nguyên nhân**. Ví dụ, một `CatalogException` báo không tìm thấy mapping khác với lỗi `FileNotFoundException`/`SAXException` trong quá trình đọc hoặc phân tích tệp được ánh xạ. Loại ngoại lệ bao ngoài có thể tùy parser; test tích hợp nên kiểm tra nguyên nhân gốc, thông điệp chứa ID/tệp đích hoặc sự kiện I/O quan sát được.

## 4. Ví dụ tự chạy: kiểm thử mapping, fallback và đầu vào sai

Ví dụ sau hoàn toàn độc lập, không tải thư viện ngoài. Nó tạo các fixture trong thư mục tạm, xây dựng hai catalog, rồi chạy các assertion có thông báo rõ. Định danh `example.invalid` là địa chỉ giả; tài nguyên dùng để parse thành công đến từ DTD local.

Lưu mã dưới tên **`CatalogContractTest.java`**:

```java
import java.io.StringReader;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import javax.xml.XMLConstants;
import javax.xml.catalog.CatalogException;
import javax.xml.catalog.CatalogFeatures;
import javax.xml.catalog.CatalogManager;
import javax.xml.catalog.CatalogResolver;
import javax.xml.parsers.DocumentBuilderFactory;
import org.xml.sax.InputSource;

public final class CatalogContractTest {
    private static final String KNOWN = "https://example.invalid/xml/invoice.dtd";
    private static final String UNKNOWN = "https://example.invalid/xml/unknown.dtd";

    private static CatalogResolver resolver(Path file, String mode) {
        var features = CatalogFeatures.builder()
                .with(CatalogFeatures.Feature.FILES, file.toUri().toString())
                .with(CatalogFeatures.Feature.RESOLVE, mode)
                .build();
        return CatalogManager.catalogResolver(features);
    }

    private static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    private static void expectCatalogException(Runnable action, String test) {
        try {
            action.run();
            throw new AssertionError("Expected CatalogException: " + test);
        } catch (CatalogException expected) {
            System.out.println("PASS " + test);
        }
    }

    private static InputSource resolveAllowed(CatalogResolver resolver, String systemId) {
        if (!KNOWN.equals(systemId)) {
            throw new IllegalArgumentException("External ID outside agreed contract");
        }
        return resolver.resolveEntity(null, systemId);
    }

    private static void expectRejected(CatalogResolver resolver, String systemId) {
        try {
            resolveAllowed(resolver, systemId);
            throw new AssertionError("Expected rejection: " + systemId);
        } catch (IllegalArgumentException expected) {
            // Refused before any parser fallback or I/O.
        }
    }

    private static String document(String systemId) {
        return "<!DOCTYPE invoice SYSTEM \"" + systemId + "\">"
                + "<invoice>&origin;</invoice>";
    }

    private static String parse(String xml, CatalogResolver resolver) throws Exception {
        var factory = DocumentBuilderFactory.newInstance();
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        var builder = factory.newDocumentBuilder();
        builder.setEntityResolver(resolver);
        return builder.parse(new InputSource(new StringReader(xml)))
                .getDocumentElement().getTextContent();
    }

    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("xml-catalog-contract-");
        Files.writeString(dir.resolve("invoice.dtd"),
                "<!ELEMENT invoice (#PCDATA)>\n"
                + "<!ENTITY origin \"FROM_LOCAL_DTD\">\n",
                StandardCharsets.UTF_8);

        Path catalog = dir.resolve("catalog.xml");
        Files.writeString(catalog,
                "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
                + "<catalog xmlns=\"urn:oasis:names:tc:entity:xmlns:xml:catalog\">\n"
                + "  <system systemId=\"" + KNOWN + "\" uri=\"invoice.dtd\"/>\n"
                + "</catalog>\n",
                StandardCharsets.UTF_8);

        CatalogResolver strict = resolver(catalog, "strict");
        InputSource matched = strict.resolveEntity(null, KNOWN);
        check(matched != null && matched.getSystemId() != null, "No mapping");
        check(Path.of(URI.create(matched.getSystemId()))
                .equals(dir.resolve("invoice.dtd")), "Wrong local target");
        System.out.println("PASS exact mapping");

        check("FROM_LOCAL_DTD".equals(parse(document(KNOWN), strict)),
                "Local DTD not used");
        System.out.println("PASS offline parse");

        expectCatalogException(() -> strict.resolveEntity(null, UNKNOWN),
                "strict rejects unmapped ID");

        CatalogResolver continuing = resolver(catalog, "continue");
        check(continuing.resolveEntity(null, UNKNOWN) == null,
                "continue must return null to SAX EntityResolver");
        System.out.println("PASS continue resolver contract");

        CatalogResolver ignoring = resolver(catalog, "ignore");
        InputSource ignored = ignoring.resolveEntity(null, UNKNOWN);
        check(ignored != null && ignored.getCharacterStream() != null,
                "ignore must yield an empty SAX source");
        System.out.println("PASS ignore resolver contract");

        Path missingCatalog = dir.resolve("missing-catalog.xml");
        Files.writeString(missingCatalog,
                "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
                + "<catalog xmlns=\"urn:oasis:names:tc:entity:xmlns:xml:catalog\">\n"
                + "  <system systemId=\"" + KNOWN + "\" uri=\"absent.dtd\"/>\n"
                + "</catalog>\n",
                StandardCharsets.UTF_8);
        CatalogResolver missing = resolver(missingCatalog, "strict");
        check(missing.resolveEntity(null, KNOWN) != null,
                "Catalog lookup should match the absent target URI");
        try {
            parse(document(KNOWN), missing);
            throw new AssertionError("Missing local target unexpectedly parsed");
        } catch (Exception expected) {
            System.out.println("PASS mapped target missing fails during load");
        }

        expectRejected(strict, null);
        expectRejected(strict, "file:///etc/passwd");
        expectRejected(strict, UNKNOWN);
        System.out.println("PASS outside-contract IDs rejected");
        System.out.println("ALL TESTS PASSED");
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 --release 17 CatalogContractTest.java
java CatalogContractTest
```

Stdout của ví dụ khi chạy thành công:

```text
PASS exact mapping
PASS offline parse
PASS strict rejects unmapped ID
PASS continue resolver contract
PASS ignore resolver contract
PASS mapped target missing fails during load
PASS outside-contract IDs rejected
ALL TESTS PASSED
```

**Giải thích assertions:**

1. `strict.resolveEntity(null, KNOWN)` kiểm tra lookup; so sánh `Path` sau khi chuyển URI xác nhận catalog trỏ đúng file, không chỉ trả non-null.
2. `parse(document(KNOWN), strict)` là test tích hợp parser: entity `&origin;` phải thực sự được mở rộng thành `FROM_LOCAL_DTD`.
3. Unknown ID được kiểm tra với cả ba chế độ. Với `continue` chỉ khẳng định kết quả ở tầng resolver, **không gọi parser để vô tình thử tải URL bên ngoài**.
4. Catalog thứ hai có mục ánh xạ hợp lệ tới `absent.dtd`. Resolver vẫn tìm được mapping, còn parser không đọc được file; đó là hai trạng thái lỗi khác nhau. Đoạn `catch (Exception)` giữ ví dụ di động; trong bộ test sản phẩm nên xác nhận cụ thể nguyên nhân có liên quan `absent.dtd` để tránh false positive.
5. `resolveAllowed` minh họa một **chính sách của ứng dụng**, không phải chức năng allowlist có sẵn trong CatalogResolver. Khi yêu cầu chỉ cho phép một ID, mọi đầu vào khác phải bị loại sớm. Catalog `strict` vẫn hữu ích khi ứng dụng đã qua lớp kiểm tra hợp đồng.

Fixture tạo bằng `Files.createTempDirectory`. Với JUnit, đặt tạo/xóa fixture trong vòng đời test (ví dụ `@TempDir`), tránh để lại thư mục tạm và bảo đảm mỗi test không chia sẻ trạng thái.

## 5. Kiểm thử tích hợp JAXP khi không tự gắn CatalogResolver

Ví dụ ở trên **gắn resolver tường minh** qua `builder.setEntityResolver(strict)`. Khi ứng dụng dùng cơ chế tích hợp tự động của JAXP, cần có test riêng cấu hình catalog trên factory/processor, vì resolver tùy chỉnh có thể được ưu tiên trước catalog mặc định.

Ví dụ đoạn cấu hình DOM (đặt trong phương thức đã có biến `catalog` kiểu `Path`):

```java
DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
factory.setFeature(XMLConstants.USE_CATALOG, true);
factory.setAttribute(CatalogFeatures.Feature.FILES.getPropertyName(),
        catalog.toUri().toString());
factory.setAttribute(CatalogFeatures.Feature.RESOLVE.getPropertyName(), "strict");
factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

var builder = factory.newDocumentBuilder();
// Không gọi builder.setEntityResolver(...) ở phép thử tích hợp tự động.
```

Đoạn này là **trích đoạn cấu hình**, sử dụng các import và biến đã nêu, không phải chương trình Java độc lập. Sau khi cấu hình, parse cùng XML fixture và kiểm tra nội dung nút. Test nên gồm hai tình huống: `USE_CATALOG=true` cùng FILES hợp lệ thì mapping có tác dụng; nếu không có FILES đúng, không được cho rằng parser sẽ tự tìm catalog.

Với SAX, StAX, schema validation hay XSLT, dùng factory và điểm cấu hình thích hợp của từng API; nhất quán kiểm tra **bộ xử lý thực tế sử dụng tài nguyên nào**. Khi ứng dụng đã đăng ký custom resolver, kiểm tra rõ thứ tự resolver tùy chỉnh, catalog và fallback. Custom resolver trả `null` có thể cho phép parser tiếp tục thử catalog; custom resolver trả dữ liệu thì catalog có thể không được gọi.

## 6. Trường hợp thiếu tài nguyên: chẩn đoán đúng lớp lỗi

Có ít nhất ba nhóm lỗi cần tách ra:

1. **Không có mục khớp:** ID đầu vào không khớp `system`/`public`/`uri` nào. Với `strict`, kiểm tra `CatalogException` ngay tại resolver.
2. **Có mapping nhưng tệp đích không tồn tại/không đọc được:** lookup có thể thành công; lỗi xuất hiện khi parser mở `file:` URI hoặc xử lý DTD/schema. Kiểm tra đường dẫn được chọn, quyền truy cập, dữ liệu fixture và cause của ngoại lệ.
3. **Có file nhưng nội dung sai/hỏng:** ví dụ DTD khai báo thiếu entity, XSD import sang sai namespace, XSLT include sai stylesheet. Có thể parse thất bại hoặc thành công với nội dung không mong muốn; test phải khẳng định cấu trúc/giá trị kết quả, không chỉ `assertDoesNotThrow`.

Khi catalog hỏng hoặc một phần tài nguyên cấu hình không thể đọc, việc bộ xử lý tiếp tục dùng đường phân giải khác có thể che lỗi cấu hình. Để phát hiện, dùng catalog đơn lẻ cho fixture, kiểm tra file catalog và các đích tồn tại trước test dương tính, bật `strict` và luôn có ít nhất một assertion mapping cụ thể. Không dựa duy nhất vào việc API khởi tạo resolver mà không ném lỗi.

## 7. Đầu vào ngoài hợp đồng và ranh giới bảo mật

Ngoài ID không có trong catalog, hãy lập test cho những chuỗi **không bao giờ được cấp quyền phân giải**: `file:///...`, `jar:file:...`, host bên ngoài, XML có DOCTYPE khi module chỉ chấp nhận tài liệu không DTD, đường dẫn tương đối vượt thư mục được cho phép, ID bị biến dạng hoặc một public/system ID không nằm trong danh sách đã duyệt.

Có hai lớp kiểm soát độc lập:

- **Hợp đồng ứng dụng**: kiểm tra allowlist của ID/scheme/host hay loại bỏ DOCTYPE nếu không cần; quyết định từ chối đầu vào lạ trước khi gọi parser.
- **Cấu hình parser/JAXP**: đặt giới hạn truy cập tài nguyên ngoài, chẳng hạn `XMLConstants.ACCESS_EXTERNAL_DTD` và `XMLConstants.ACCESS_EXTERNAL_SCHEMA`; dùng `FEATURE_SECURE_PROCESSING` và những giới hạn parser tương ứng. Nếu nghiệp vụ không cần DTD, có thể cấu hình cấm DOCTYPE bằng tính năng được parser hỗ trợ. Nếu cần DTD, chỉ cho phép các bản local đã kiểm soát.

Cần hiểu giới hạn: các thuộc tính `ACCESS_EXTERNAL_*` quản lý những truy cập mà bộ xử lý thực hiện; tài nguyên do resolver tùy chỉnh cung cấp có quy tắc riêng. Không coi `RESOLVE=continue` là giải pháp an toàn vì nó cho phép fallback. `RESOLVE=ignore` cũng không bảo đảm tài liệu vẫn hợp lệ sau khi thiếu DTD/entity. Kiểm thử an toàn mạng thật sự nên chạy trong môi trường cô lập hoặc có giám sát/khóa outbound, thay vì chỉ cho rằng domain `.invalid` là đủ chứng minh không có kết nối.

Test schema/XSLT cần xem thêm các thuộc tính cùng họ như `ACCESS_EXTERNAL_STYLESHEET` ở bộ xử lý transform. Điều kiện kiểm thử thay đổi theo API; không nên áp đặt nguyên xi đường đi DTD lên XSD và XSLT.

## 8. Quy trình review kết quả và lỗi thường gặp

Trước khi chấp nhận bộ kiểm thử, rà theo thứ tự:

1. **Fixture có thể tái lập:** catalog là XML hợp lệ với namespace OASIS đúng; URI tệp catalog tuyệt đối; tất cả file local được tạo rõ ràng và có thể dọn dẹp.
2. **Kiểm chứng mapping:** đối chiếu ID vào với URI local ra, sau đó khẳng định dấu hiệu chỉ tồn tại trong tệp local bằng test parser.
3. **Negative tests có ý nghĩa:** phân biệt thiếu mục, thiếu file, file sai, ID ngoài hợp đồng và XML sai cú pháp; tránh bắt mọi exception rồi coi là PASS trong code sản phẩm.
4. **Không có fallback không mong muốn:** quy định rõ `strict`/`continue`/`ignore`; kiểm tra bộ xử lý dùng đúng resolver và không truy cập mạng khi chính sách cấm.
5. **Không lệ thuộc môi trường:** không hard-code ổ đĩa, thư mục hiện tại, proxy hay tài nguyên mạng; dùng `Path.toUri()`, fixture tạm và điều kiện lỗi dựa trên ngữ nghĩa.
6. **Áp dụng cho phiên bản Java được dùng:** chạy trên phiên bản JDK thực tế và thiết lập `--release` phù hợp. Tránh các class triển khai nội bộ `com.sun.*` và cơ chế catalog không còn được dựa vào trong mã ứng dụng.

Những lỗi phổ biến nhất: nhầm `strict` với việc xác minh file đã tồn tại; assert chỉ “không exception”; kỳ vọng `prefer="public"` vượt một `system` khớp; dùng URI tương đối nhưng không kiểm soát base URI; cho `continue` chạy ra mạng trong CI; nghĩ rằng catalog thay cho cấu hình chống XXE; và gom mọi lỗi thành “không tìm thấy mapping”.

## 9. Câu hỏi tự kiểm tra

- Catalog có mục `<system ... uri="absent.dtd"/>`, `resolveEntity` trả non-null nhưng parse lỗi. Đây là thiếu ánh xạ hay thiếu tài nguyên đích? Giải thích tầng nào phát hiện.
- Nếu đổi `RESOLVE` từ `strict` sang `continue`, assertion nào còn đúng tại SAX `EntityResolver`, và vì sao không được suy ra parser sẽ offline?
- Vì sao test chỉ kiểm tra `matched != null` yếu hơn test kiểm tra `getSystemId()` và giá trị entity sau parse?
- Khi XML gửi `SYSTEM "invoice.dtd"` nhưng catalog chỉ có URI tuyệt đối, yếu tố nào ảnh hưởng việc khớp và khi nào cần chỉnh hợp đồng thay vì dùng `systemSuffix`?
- Một ứng dụng vốn không cho phép DOCTYPE có nên bật XML Catalog để chấp nhận mọi DOCTYPE lạ hay phải từ chối ở ranh giới đầu vào?

**Kết luận kiến thức:** kiểm thử XML Catalog tốt cần chứng minh **ID đúng được ánh xạ tới đúng fixture và parser thật sự sử dụng nó**, đồng thời chứng minh **ID không hợp lệ, mapping thiếu và tệp đích thiếu được xử lý đúng chính sách**. Đặt những kết quả này trong cấu hình bảo mật JAXP hiện hành để test vừa chính xác vừa không phụ thuộc tài nguyên bên ngoài.

### Tài liệu tham khảo hiện hành

- [Java SE 21 — Package javax.xml.catalog](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/catalog/package-summary.html)
- [Java SE 21 — CatalogFeatures, thứ tự ưu tiên và RESOLVE](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/catalog/CatalogFeatures.html)
- [Java SE 21 — CatalogResolver (SAX, StAX, schema, transform)](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/catalog/CatalogResolver.html)
- [Java SE 21 — JAXP Security Guide](https://docs.oracle.com/en/java/javase/21/security/java-api-xml-processing-jaxp-security-guide.html)