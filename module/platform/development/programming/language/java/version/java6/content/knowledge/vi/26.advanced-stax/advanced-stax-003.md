# XMLResolver và chính sách tài nguyên bên ngoài trong StAX nâng cao

Trong StAX, một tài liệu XML có thể chứa tham chiếu đến **DTD hoặc entity được khai báo ở tài nguyên bên ngoài**. Nếu parser tự động mở `file:`, `http:`, `https:` hoặc những URI khác do tài liệu XML cung cấp, ứng dụng có thể gặp **XXE (XML External Entity), SSRF, đọc tệp ngoài ý muốn, lộ dữ liệu hoặc tiêu thụ tài nguyên quá mức**. Vì vậy, vấn đề không chỉ là "đọc XML được hay không", mà là **ai có quyền quyết định nguồn bên ngoài nào được truy cập**.

`javax.xml.stream.XMLResolver` là giao diện dành cho **custom external-resource resolution** của StAX. Ta đăng ký resolver vào `XMLInputFactory` qua `setXMLResolver(XMLResolver)`; khi parser cần phân giải một external resource mà tính năng tương ứng được bật, nó có thể gọi resolver thay vì tự đi tới URI do XML cung cấp.

Có hai chính sách phù hợp với hệ thống hiện đại:

- **Mặc định từ chối (deny-by-default):** nếu ứng dụng không cần DTD/external entities, tắt chức năng đó, đặt `XMLConstants.ACCESS_EXTERNAL_DTD=""` và không cung cấp bất kỳ đường fallback mở tài nguyên nào.
- **Chỉ cho phép tài nguyên đã duyệt (explicit allowlist):** nếu ứng dụng thực sự phải dùng một DTD/entity cố định, custom `XMLResolver` hoặc **XML Catalog** ánh xạ định danh bên ngoài tới nội dung/tệp cục bộ do ứng dụng quản lý. Mọi định danh không có trong allowlist phải **ném lỗi**, không âm thầm trả `null` cho parser thử phân giải mặc định.

**Điểm bảo mật quan trọng nhất:** nếu `XMLResolver.resolveEntity(...)` trả `null`, StAX được phép dùng **cơ chế phân giải mặc định**. Ngược lại, nếu resolver trả **một tài nguyên không null**, giới hạn `ACCESS_EXTERNAL_DTD` **không kiểm soát hành động mở tài nguyên do chính resolver thực hiện**. Một resolver tự gọi `URL.openStream()` theo URI người dùng gửi vào vẫn nguy hiểm dù factory đã đặt `ACCESS_EXTERNAL_DTD=""`.

Bài này thuộc nhóm **StAX nâng cao**, chỉ sử dụng các API **còn áp dụng trên Java 17+ và Java SE hiện hành**: `XMLResolver`, `XMLInputFactory`, `XMLStreamReader`, `XMLStreamException`, `XMLConstants.ACCESS_EXTERNAL_DTD` và `javax.xml.catalog`. Hai chương trình minh họa **Java 17+ chạy độc lập** đã biên dịch bằng `javac --release 17` và chạy trên **JDK 24**, tổng cộng **9 kiểm tra PASS**. Ví dụ không sử dụng database, không chủ động kết nối mạng và không dựa vào một URI Internet đang hoạt động.

## 1. Mục tiêu học tập

Kết thúc bài, bạn sẽ:

1. Biết `XMLResolver` được gọi để giải quyết external references trong StAX khi parser có nhu cầu và cho phép xử lý DTD/entity.
2. Hiểu đủ bốn tham số `publicID`, `systemID`, `baseURI`, `namespace` và các kiểu dữ liệu có thể trả về từ `resolveEntity`.
3. Phân biệt **return null** với **return resource** và **throw XMLStreamException**.
4. Đặt chính sách mặc định **không mở external resources** bằng `XMLInputFactory.SUPPORT_DTD`, `IS_SUPPORTING_EXTERNAL_ENTITIES` và `ACCESS_EXTERNAL_DTD`.
5. Xây resolver **allowlist đúng định danh** trả một `InputStream` cục bộ bất biến, không gọi network theo input.
6. Biết khi nào nên dùng `CatalogResolver` thuộc Java XML Catalog API với `CatalogFeatures.Feature.RESOLVE="strict"`.
7. Hiểu vì sao resolver có thể làm *bypass* một phần external-access controls nếu implementation mở URI một cách thiếu kiểm soát.
8. Phân tích URI tương đối, `baseURI`, percent encoding, path traversal, redirects và allowlist host/path.
9. Kiểm soát tài nguyên: input bytes, entity expansion, nesting, memory, timeout, stream lifecycle và parser providers.
10. Viết negative tests chống XXE/SSRF, kiểm tra URI không được duyệt bị từ chối thay vì bị truy cập.
11. Biết giới hạn của `SUPPORT_DTD=false`: không xử lý DTD **không đồng nghĩa** luôn báo lỗi khi thấy DOCTYPE.
12. Phân biệt `XMLResolver` của StAX với `EntityResolver` của SAX/DOM, `URIResolver` của XSLT và `LSResourceResolver` của XSD validation.

## 2. DTD và external entity xuất hiện từ đâu?

Một XML có thể khai báo external DTD:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE doc SYSTEM "https://schemas.example.invalid/approved.dtd">
<doc>&company;</doc>
```

Trong ví dụ này, `SYSTEM "https://schemas.example.invalid/approved.dtd"` là **system identifier**. Nếu parser đọc DTD, DTD có thể định nghĩa entity như:

```text
<!ENTITY company "Approved-Co">
```

Khi entity được xử lý, `&company;` có thể biến thành ký tự `Approved-Co` trong nội dung `<doc>`. DTD không nằm trong XML document ban đầu, và parser cần một cơ chế để lấy nó.

Một ví dụ khác dùng external general entity được khai báo trong **internal subset**:

```xml
<!DOCTYPE doc [
  <!ENTITY external SYSTEM "https://example.invalid/private.txt">
]>
<doc>&external;</doc>
```

Nếu parser tự mở URI không được kiểm soát, XML không đáng tin có thể dẫn đến việc truy cập tài nguyên ngoài ý muốn. Đây là một trong các dạng rủi ro XXE/SSRF.

**DTD/entity processing là một khả năng riêng, không cần cho mọi ứng dụng XML.** Nếu dữ liệu chỉ có element, attribute, text, CDATA và namespaces thông thường, giải pháp an toàn hơn thường là **tắt DTD và external entity resolution**, không xây resolver phức tạp chỉ để xử lý XML cơ bản.

### 2.1. Luồng xử lý không có kiểm soát và có kiểm soát

```text
Mô hình dễ gặp rủi ro:

XML upload
  -> StAX parser
  -> DTD/entity systemId do XML cung cấp
  -> parser hoặc custom resolver tự mở URL/file
  -> dữ liệu bên ngoài đi vào quá trình parse

Mô hình chủ động kiểm soát:

XML upload
  -> XMLInputFactory cấu hình chặn access mặc định
  -> cần external resource?
       | không -> xử lý XML không có DTD/entity ngoài
       | có
       v
    XMLResolver / CatalogResolver
       | allowlisted exact identifier -> InputStream/tệp tin TRUSTED được duyệt
       | bất kỳ identifier khác -> THROW / REJECT
  -> parser xử lý trong size/depth/entity limits
```

Các URI có hậu tố `example.invalid` là **giá trị nhận dạng giả lập** dành cho test. Chúng không phải địa chỉ DTD thật và không yêu cầu kết nối Internet.

## 3. Interface XMLResolver

Chữ ký của `javax.xml.stream.XMLResolver` trong Java SE:

```java
public interface XMLResolver {
    Object resolveEntity(
            String publicID,
            String systemID,
            String baseURI,
            String namespace) throws XMLStreamException;
}
```

Đây là chữ ký **giải thích API**, không phải một source file độc lập. `XMLResolver` là một **functional interface về mặt sử dụng** với một method trừu tượng, vì vậy có thể triển khai bằng lambda.

| Tham số | Ý nghĩa | Điều không nên mặc định |
| --- | --- | --- |
| `publicID` | Public identifier của external entity, có thể `null`. | Không phải URL an toàn hoặc thông tin đã xác thực. |
| `systemID` | System identifier của external entity, có thể là URI tương đối hoặc tuyệt đối theo ngữ cảnh. | Không được mở trực tiếp như URL do user nhập. |
| `baseURI` | Base URI dùng để giải quyết system identifier tương đối khi được cung cấp. | Không phải lúc nào cũng non-null; không tự có quyền mở mọi file dưới base. |
| `namespace` | Namespace liên quan đến resource theo API/processor. | Không phải whitelist host, không mặc định có giá trị. |
| Kết quả `Object` | Resource để parser đọc, hoặc `null`. | Không phải mọi Java Object bất kỳ đều được hỗ trợ. |

Theo API Java SE 17, resolver có thể trả một trong ba loại resource được chỉ định:

- `java.io.InputStream`.
- `javax.xml.stream.XMLStreamReader`.
- `javax.xml.stream.XMLEventReader`.

Method có thể ném `XMLStreamException` để báo không thể hoặc không được phép phân giải.

### 3.1. Ba kết quả khác nhau

| Resolver trả gì? | Diễn giải | Phù hợp khi nào? |
| --- | --- | --- |
| `new ByteArrayInputStream(approvedBytes)` | Parser nhận nội dung đã được ứng dụng lựa chọn. | URI nằm chính xác trong allowlist; bytes/tài nguyên do ứng dụng tin cậy cung cấp. |
| `XMLStreamReader` / `XMLEventReader` hợp lệ | Parser nhận một nguồn sự kiện XML. | Trường hợp chuyên biệt theo contract của provider. |
| `null` | Parser **có thể tiếp tục default resolution**, không có nghĩa từ chối. | Chỉ khi bạn chủ động chấp nhận fallback và đã có policy bảo vệ độc lập. |
| `throw new XMLStreamException(...)` | Không cung cấp resource và báo lỗi. | Cách **fail closed** cho identifier không được duyệt. |

**Chống chỉ định:** viết resolver trả `null` cho mọi URI không có trong danh sách rồi kết luận “đã deny”. Cách đó trao lại quyết định cho parser/catalog mặc định; bên ngoài có thể vẫn được xử lý tùy cấu hình runtime.

### 3.2. Đăng ký resolver với factory

```java
XMLInputFactory factory = XMLInputFactory.newFactory();
factory.setXMLResolver((publicId, systemId, baseUri, namespace) -> {
    throw new XMLStreamException("External resources are disabled");
});
```

Đây là mảnh code đặt trong method có import `javax.xml.stream.*`. `setXMLResolver` là API trực tiếp, tương đương việc dùng property `XMLInputFactory.RESOLVER` qua `setProperty` khi implementation hỗ trợ đúng.

Mọi `XMLStreamReader`/`XMLEventReader` được tạo **sau khi** factory được cấu hình sẽ nhận resolver tương ứng. Đừng thay đổi factory settings giữa lúc nhiều threads cùng tạo readers mà không có chiến lược đồng bộ/ownership rõ ràng.

## 4. Chính sách mặc định: không cho external access

Một factory StAX dùng cho XML không cần DTD có thể được cấu hình:

```java
XMLInputFactory factory = XMLInputFactory.newFactory();
factory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
factory.setProperty(XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
factory.setXMLResolver((publicId, systemId, baseUri, namespace) -> {
    throw new XMLStreamException("External reference denied");
});
```

**Các thuộc tính có vai trò khác nhau:**

| Thiết lập | Chính sách |
| --- | --- |
| `SUPPORT_DTD=false` | Không xử lý DTD theo yêu cầu của ứng dụng. |
| `IS_SUPPORTING_EXTERNAL_ENTITIES=false` | Không resolve các external parsed entities. |
| `ACCESS_EXTERNAL_DTD=""` | Chặn các giao thức bên ngoài mà parser **tự** mở cho DTD/external entities. |
| Resolver always-throw | Nếu parser gọi resolver với external reference, callback từ chối thay vì trả tài nguyên hoặc `null`. |

Hãy cấu hình trước khi tạo parser. `setProperty` có thể ném `IllegalArgumentException` nếu parser/provider không hỗ trợ một property hoặc giá trị; **không catch rồi im lặng bỏ qua cấu hình bảo mật**. Khi provider khác JDK được sử dụng, kiểm thử hiệu lực thực tế của từng setting.

### 4.1. Tắt DTD khác với từ chối một tài liệu có DOCTYPE

`SUPPORT_DTD=false` yêu cầu processor không xử lý DTD, nhưng **không bảo đảm mọi implementation sẽ từ chối toàn bộ document chỉ vì có `<!DOCTYPE ...>`**. Một số parser có thể bỏ qua DTD mà vẫn xử lý các phần còn lại.

Nếu chính sách ứng dụng là **không cho phép bất kỳ DOCTYPE nào**, cần cơ chế kiểm soát rõ ràng và được kiểm chứng:

- Kiểm tra sự xuất hiện của `DTD` event theo parser đang dùng khi thích hợp, và từ chối trước khi tiếp tục xử lý.
- Hoặc dùng cấu hình DTD *deny* của JDK có hỗ trợ theo phiên bản/processor đã được kiểm chứng.
- Không dựa vào một phép tìm substring `"<!DOCTYPE"` trên raw XML làm XML parser/security control đầy đủ: encoding, whitespace, entity và các trường hợp lexical khác có thể làm check hời hợt bị bypass.
- Dù dùng cách nào, vẫn giữ `ACCESS_EXTERNAL_DTD=""` và không cho resolver fallback ngoài kiểm soát.

**Mã ví dụ ở mục 7:** `configured(false, false)` minh họa parser không xử lý DTD và từ chối resolver request; bài test này **không tuyên bố đã tự từ chối mọi DOCTYPE**. Những nhánh negative tests cho phép parser gặp DTD để xác minh resolver từ chối request.

### 4.2. StAX không dùng FSP theo cách DOM/SAX

`XMLConstants.FEATURE_SECURE_PROCESSING` (FSP) được áp dụng cho các JAXP factories khác như DOM/SAX/Transformer theo cách riêng. Theo **JAXP Security Guide**, StAX **không hỗ trợ FSP** như các factory đó; vì thế, đừng gọi:

```java
// Không phải một cấu hình FSP portable cho XMLInputFactory:
factory.setProperty(XMLConstants.FEATURE_SECURE_PROCESSING, true);
```

Hãy dùng StAX properties, external access restrictions, JDK XML processing limits và application-level policy phù hợp. Việc tắt DTD/external entities không thay thế các giới hạn dữ liệu đầu vào lớn.

## 5. ACCESS_EXTERNAL_DTD: giới hạn phạm vi nào?

`XMLConstants.ACCESS_EXTERNAL_DTD` là một **External Access Property (EAP)**. Giá trị có thể là:

- `""`: không cho phép protocol nào.
- `"file"`: parser có thể mở tài nguyên file theo chính sách của EAP.
- `"https"`: parser có thể mở HTTPS resources theo chính sách EAP.
- `"file,https"`: cho phép hai schemes.
- `"all"`: không giới hạn giao thức bằng EAP, **không nên dùng cho XML không tin cậy**.

Giá trị là **danh sách protocol/scheme**, **không phải danh sách các hostname, path hoặc tài nguyên được duyệt cụ thể**. Cấu hình `"https"` **không giới hạn** parser chỉ được gọi một host an toàn; nếu resolver/parser có quyền làm HTTP tới mọi địa chỉ HTTPS, nguy cơ SSRF vẫn tồn tại.

Vì vậy, cấu hình bảo thủ nhất trong đa số ứng dụng là:

```java
factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
```

### 5.1. Một ngoại lệ quan trọng: resolver do ứng dụng viết

Tài liệu Oracle xác nhận EAP **không áp dụng** lên các external references đã được custom resolver giải quyết bằng **nguồn không null**. Điều này có ích khi dùng local catalog nhưng cũng là điểm nguy hiểm:

```java
// Anti-pattern: KHÔNG DÙNG với XML không tin cậy.
// Một resolver tự mở URL do XML gửi đến.
factory.setXMLResolver((publicId, systemId, baseUri, namespace) -> {
    return java.net.URI.create(systemId).toURL().openStream();
});
```

Đoạn trên là **mảnh code sai về bảo mật**, minh họa nguyên nhân rủi ro, không phải ví dụ để chạy. Nó còn chưa xử lý URI tương đối/null, redirects, timeout và lifecycle. EAP `""` **không tự ngăn** lời gọi `openStream()` trong Java application code.

**Chính sách đúng:** resolver chỉ trả về resource do **application kiểm soát**; không cho URI từ XML quyết định network/file path của hàm mở nguồn. Nếu thực sự cần fetch có kiểm soát, phải có một hệ thống resource-fetch riêng với URI canonicalization, strict allowlist, DNS/IP validation, redirect policy, timeouts và size limits, chứ không trực tiếp fetch trong XMLResolver từ input không tin cậy.

## 6. Thiết kế một XMLResolver allowlist

Một resolver an toàn nhất khi chỉ cần một số DTD/entity cố định có thể làm:

1. Nhận `publicID`, `systemID`, `baseURI`, `namespace`.
2. Chỉ chấp nhận **identifier chính xác** được cấu hình, kèm các điều kiện về publicID nếu cần.
3. Không lấy nguồn từ `systemID`/`baseURI` một cách trực tiếp.
4. Trả về **bytes được đóng gói/kiểm soát** của ứng dụng hoặc tệp cục bộ đã được phê duyệt.
5. Với mọi identifier còn lại, **ném `XMLStreamException`**, tuyệt đối không trả `null` để parser fallback.
6. Bổ sung giới hạn kích thước và entity expansion trong parser, kể cả với DTD được duyệt.

Mảnh ý tưởng:

```java
private static final String APPROVED =
        "https://schemas.example.invalid/approved.dtd";
private static final byte[] APPROVED_BYTES =
        "<!ENTITY company \"Approved-Co\">"
                .getBytes(StandardCharsets.UTF_8);

// Trong XMLInputFactory.setXMLResolver(...)
(publicId, systemId, baseUri, namespace) -> {
    if (publicId == null && APPROVED.equals(systemId)) {
        return new ByteArrayInputStream(APPROVED_BYTES);
    }
    throw new XMLStreamException("External resource not allowed");
}
```

Đây là **mảnh thiết kế**, không phải source file độc lập. `APPROVED_BYTES` là bản DTD cố định; URI có hậu tố `example.invalid` chỉ là **tên định danh giả**. Không cần network: chỉ mở `ByteArrayInputStream` trên nội dung đã biết.

### 6.1. Vì sao không dùng startsWith để kiểm tra địa chỉ?

Không nên:

```java
// Sai: host/path không được kiểm tra chính xác.
if (systemId.startsWith("https://trusted.example")) {
    // Cho phép mở URL...
}
```

Các địa chỉ như `https://trusted.example.evil.invalid/...` hoặc `https://trusted.example@other.invalid/...` làm phép so prefix không đủ an toàn. URI encoding, Unicode hostnames, redirects, path normalization và relative paths có thể tạo thêm trường hợp bỏ sót.

**Trong ví dụ chạy được**, phép so `APPROVED.equals(systemId)` chỉ chấp nhận **một identifier tuyệt đối đã xác định**, và **không hỗ trợ relative identifiers**. Đây là thiết kế có chủ đích: mọi relative ID đều bị từ chối thay vì được cố suy diễn từ baseURI có thể không đáng tin.

### 6.2. Khi cần relative systemId và baseURI

Nếu nghiệp vụ thực sự cần tham chiếu tương đối như `"schemas/book.dtd"`:

```text
systemID = "schemas/book.dtd"
baseURI  = "https://schemas.example.invalid/v1/"
effective URI = "https://schemas.example.invalid/v1/schemas/book.dtd"
```

Một thành phần được giao **quyền resolution** có thể dùng `java.net.URI` để resolve:

```java
URI base = URI.create(baseURI);
URI resolved = base.resolve(systemID).normalize();
```

Nhưng đây chỉ là **bước tính URI**, không tự là kiểm soát bảo mật. Trước khi mở bất kỳ nguồn nào, phải:

- Xác minh `baseURI` thật sự do ứng dụng tin cậy cấp hoặc đã được policy chấp nhận.
- Kiểm tra `scheme`, `host`, `port`, `userInfo`, `fragment`, path sau normalization và encoding theo một bộ quy tắc nhất quán.
- Không chấp nhận `file:`, `jar:`, `http:` hoặc một scheme lạ nếu chính sách chỉ dùng resource nội bộ.
- Ngăn path traversal với `..`, encoded separators và symbolic links nếu ánh xạ sang filesystem.
- Nếu có HTTP fetch ở tầng riêng, xác nhận DNS/IP cuối cùng và **mọi lần redirect**, chặn loopback/metadata/private endpoints theo threat model.
- Không chuyển `URI.resolve` thành `URL.openStream` trên user-controlled URI mà thiếu các bước trên.

Với phần lớn XML import, **strict mapping sang embedded resources** ít rủi ro và dễ kiểm thử hơn network fetch.

## 7. Chương trình 1: resolver strict, DTD chỉ có trong memory

Đây là chương trình Java 17+ chạy đầy đủ, **không cần file cấu hình, không cần database, không cần kết nối Internet**. Nó kiểm thử:

- XML không dùng DTD được đọc với factory đã tắt DTD/external entities.
- Một DTD có **systemId được allowlist** được trả từ `ByteArrayInputStream`, và entity được expand thành text.
- Một DTD không được allowlist bị từ chối bằng `XMLStreamException`.
- Trong một negative test khác, resolver luôn từ chối dù parser được cấu hình xử lý DTD.
- Bộ đếm kiểm tra resolver thật sự được gọi đúng số lần.

**Tệp đầy đủ:** `XmlResolverPolicyDemo.java`.

### 7.1. Source code

```java
import java.io.ByteArrayInputStream;
import java.io.StringReader;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;
import javax.xml.XMLConstants;
import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLStreamConstants;
import javax.xml.stream.XMLStreamException;
import javax.xml.stream.XMLStreamReader;

public final class XmlResolverPolicyDemo {
    private static final String APPROVED =
            "https://schemas.example.invalid/approved.dtd";
    private static final String DTD =
            "<!ENTITY company \"Approved-Co\">";
    private static final AtomicInteger allowed = new AtomicInteger();
    private static final AtomicInteger denied = new AtomicInteger();

    private static XMLInputFactory configured(boolean allowApproved,
                                              boolean needsDtd) {
        XMLInputFactory f = XMLInputFactory.newDefaultFactory();
        f.setProperty(XMLInputFactory.IS_NAMESPACE_AWARE, true);
        f.setProperty(XMLInputFactory.SUPPORT_DTD, needsDtd);
        f.setProperty(XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, needsDtd);
        f.setProperty(XMLInputFactory.IS_REPLACING_ENTITY_REFERENCES, true);
        f.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        f.setXMLResolver((publicId, systemId, baseUri, namespace) -> {
            if (allowApproved && publicId == null
                    && APPROVED.equals(systemId)) {
                allowed.incrementAndGet();
                return new ByteArrayInputStream(
                        DTD.getBytes(StandardCharsets.UTF_8));
            }
            denied.incrementAndGet();
            throw new XMLStreamException("External resource not allowed");
        });
        return f;
    }

    private static String readText(XMLInputFactory f, String xml)
            throws XMLStreamException {
        XMLStreamReader reader =
                f.createXMLStreamReader(new StringReader(xml));
        try {
            while (reader.hasNext()) {
                if (reader.next() == XMLStreamConstants.START_ELEMENT
                        && reader.getLocalName().equals("doc")) {
                    return reader.getElementText();
                }
            }
            throw new XMLStreamException("Missing doc root");
        } finally {
            reader.close();
        }
    }

    private static void check(String name, boolean value) {
        if (!value) throw new AssertionError(name);
        System.out.println(name + "=PASS");
    }

    public static void main(String[] args) throws Exception {
        check("normalXml",
                "Xin chào 😀".equals(readText(
                        configured(false, false), "<doc>Xin chào 😀</doc>")));

        String safe = "<!DOCTYPE doc SYSTEM '" + APPROVED +
                "'><doc>Chào 😀 &company;</doc>";
        String output = readText(configured(true, true), safe);
        check("approvedLocalDtd", "Chào 😀 Approved-Co".equals(output));
        check("approvedResolverCalls", allowed.get() == 1);

        String unknown = "<!DOCTYPE doc SYSTEM "
                + "'https://schemas.example.invalid/unlisted.dtd'>"
                + "<doc>blocked</doc>";
        try {
            readText(configured(true, true), unknown);
            throw new AssertionError("Unknown URI should have been blocked");
        } catch (XMLStreamException expected) {
            check("unlistedRejected",
                    expected.toString().contains("External resource not allowed"));
        }
        check("deniedResolverCalls", denied.get() == 1);

        try {
            readText(configured(false, true), safe);
            throw new AssertionError("Deny-all resolver should block DTD");
        } catch (XMLStreamException expected) {
            check("denyAllRejected",
                    expected.toString().contains("External resource not allowed"));
        }
        check("denyAllResolverCalls", denied.get() == 2);
    }
}
```

### 7.2. Biên dịch và chạy

```bash
javac --release 17 -encoding UTF-8 XmlResolverPolicyDemo.java
java XmlResolverPolicyDemo
```

`XMLInputFactory.newDefaultFactory()` có từ Java 9 và còn hoạt động trên Java 17+, giúp demo chọn default JDK StAX provider thay vì tình cờ chọn provider bên thứ ba trên classpath. Trong sản phẩm thực, `newFactory()` có thể chọn implementation theo cơ chế JAXP provider discovery; phải kiểm chứng settings trên provider thật.

### 7.3. Stdout chính xác đã kiểm chứng trên JDK 24

```text
normalXml=PASS
approvedLocalDtd=PASS
approvedResolverCalls=PASS
unlistedRejected=PASS
deniedResolverCalls=PASS
denyAllRejected=PASS
denyAllResolverCalls=PASS
```

**7/7 kiểm tra PASS.** Không có lệnh HTTP hoặc file network fetch trong chương trình. Các URI `example.invalid` chỉ là identifiers và không được dùng để mở network connection.

### 7.4. Giải thích từng kết quả

**`normalXml=PASS`:** factory đặt `needsDtd=false` nên không xử lý DTD và không resolve external parsed entities cho tài liệu thuần `<doc>Xin chào 😀</doc>`. Đọc XML text thông thường không đòi hỏi resolver callback.

**`approvedLocalDtd=PASS`:** trong test này **chỉ riêng** `needsDtd=true` để parser có thể dùng DTD. Resolver nhận identifier chính xác `APPROVED`, trả một `ByteArrayInputStream` từ `DTD` được hardcode. Text nhận được là `Chào 😀 Approved-Co`, chứng minh entity `company` đã được thay đúng và unicode từ tài liệu chính được giữ.

**`approvedResolverCalls=PASS`:** callback allowlist được gọi **đúng một lần** trong môi trường JDK 24 của test. Không suy luận mọi parser/version bắt buộc dùng cùng một số callbacks với mọi tài liệu, DTD phức tạp hoặc nested entity.

**`unlistedRejected=PASS`:** một URI khác với `APPROVED` khiến resolver ném `XMLStreamException`, **không trả `null` để kích hoạt fallback**. Test không cần truy cập URL thực.

**`deniedResolverCalls=PASS`:** biến `denied` đã tăng một lần cho URI lạ.

**`denyAllRejected=PASS`:** test chủ động cho xử lý DTD với `needsDtd=true` nhưng `allowApproved=false` để đảm bảo callback từ chối ngay cả URI `APPROVED`. Đây là negative test để quan sát resolver, **không** phải cấu hình default khuyên dùng cho XML không cần DTD.

**`denyAllResolverCalls=PASS`:** bộ đếm cho thấy có thêm một yêu cầu bị từ chối.

### 7.5. Giới hạn của ví dụ

- DTD được phép chỉ định nghĩa một entity ASCII `Approved-Co`. Văn bản XML chính có tiếng Việt và emoji, nhưng bài này **không phải bài kiểm thử toàn bộ DTD encoding edge cases**.
- Không có mạng để kiểm tra SSRF thật; tính an toàn của ví dụ đến từ **logic không mở URI**, không từ một công cụ giám sát network được trình bày trong đây. Production nên bổ sung network egress policy và test kiểm chứng truy cập bị chặn.
- `XMLInputFactory.newDefaultFactory()` khiến bài test ổn định trên JDK; provider khác có thể khác chi tiết callback/event handling.
- `AtomicInteger` chỉ dùng đếm lượt trong test; không biến việc chia sẻ một XMLInputFactory tùy ý giữa nhiều threads thành an toàn.
- Chương trình chỉ đọc một element text-only bằng `getElementText()`. Nếu XML có nested elements, phải dùng StAX event loop theo phạm vi thay vì getElementText.

## 8. XML Catalog: giải pháp quản lý nhiều DTD/entity

Nếu hệ thống có nhiều DTD/XSD/tài nguyên cố định cần quản lý, thay vì tự viết một danh sách hàng chục `if (...)`, có thể dùng **XML Catalog API** trong package `javax.xml.catalog` (còn được hỗ trợ trên Java 17+).

`CatalogResolver` implements:

- `javax.xml.stream.XMLResolver` cho StAX.
- `org.xml.sax.EntityResolver` cho SAX/DOM.
- `javax.xml.transform.URIResolver` cho transformations.
- `org.w3c.dom.ls.LSResourceResolver` cho schema validation.

Do đó một catalog có thể **ánh xạ định danh ngoài tới resource nội bộ** ở nhiều API; tuy nhiên policy cụ thể của mỗi parser/validator vẫn phải được cấu hình độc lập.

### 8.1. Ví dụ catalog XML

```xml
<?xml version="1.0" encoding="UTF-8"?>
<catalog xmlns="urn:oasis:names:tc:entity:xmlns:xml:catalog">
  <system
      systemId="https://schemas.example.invalid/approved.dtd"
      uri="approved.dtd"/>
</catalog>
```

Catalog file này nói: khi gặp `systemId` chính xác của DTD đã duyệt, dùng tệp `approved.dtd` **tương đối với vị trí catalog**. Trong production, catalog và DTD phải được cấp phát từ **nguồn cài đặt tin cậy**, không từ một thư mục upload hoặc một đường dẫn có thể bị attacker thay đổi.

Các dạng mapping khác trong OASIS XML Catalog gồm `public`, `uri`, `rewriteSystem`, `systemSuffix` và catalog chaining. Mapping rộng bằng suffix/rewrites có thể tạo bất ngờ nếu mục tiêu là chỉ cho phép một URI tuyệt đối: ưu tiên **exact `system` mapping** cho tài nguyên nhạy cảm.

### 8.2. Strict là lựa chọn quan trọng

`CatalogFeatures.Feature.RESOLVE` có các giá trị như:

| Giá trị | Khi không tìm thấy mapping | Tác động tới bảo mật |
| --- | --- | --- |
| `"strict"` | Báo lỗi `CatalogException`/từ chối theo Catalog API. | Phù hợp khi mọi external resource phải nằm trong catalog. |
| `"continue"` | Cho phép parser tiếp tục xử lý bằng cơ chế khác. | Có thể mở đường fallback không mong muốn nếu các kiểm soát khác yếu. |
| `"ignore"` | Bỏ qua external resource khi không có mapping. | Không tương đương kiểm tra đầy đủ tài liệu; có thể khiến parse thiếu entity/DTD. |

Chính sách cần **fail closed** khi một tài nguyên bắt buộc không được ánh xạ; dùng `"strict"` và vẫn giữ `ACCESS_EXTERNAL_DTD=""` để chặn parser tự fetch những URI không được resolver giải quyết.

**Đặc biệt:** Catalog là resolver. Khi nó trả tệp cục bộ đã cho phép, `ACCESS_EXTERNAL_DTD=""` **không tự chặn** việc cung cấp resource ấy, vì nó đến từ resolver chứ không phải truy cập mặc định của parser. Bởi vậy phải kiểm soát nội dung/catalog/tệp nội bộ.

## 9. Chương trình 2: CatalogResolver strict với local DTD tạm thời

Chương trình hoàn chỉnh sau tự tạo **một thư mục tạm**, ghi một DTD/ catalog cục bộ, đăng ký CatalogResolver cho StAX, đọc XML và xác nhận unknown ID bị từ chối. Cuối cùng, nó **xóa đúng các tệp tạm do nó tạo ra**.

Không có JDBC driver, không cần kết nối mạng. URI ở XML chỉ dùng làm **system identifier**. Tệp DTD local là một tài nguyên mà **chính chương trình** đã tạo trong thư mục temp riêng.

**Tệp:** `CatalogPolicyDemo.java`.

### 9.1. Source code

```java
import java.io.StringReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import javax.xml.XMLConstants;
import javax.xml.catalog.CatalogFeatures;
import javax.xml.catalog.CatalogManager;
import javax.xml.catalog.CatalogResolver;
import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLStreamConstants;
import javax.xml.stream.XMLStreamException;
import javax.xml.stream.XMLStreamReader;

public final class CatalogPolicyDemo {
    private static final String APPROVED =
            "https://schemas.example.invalid/approved.dtd";

    private static String read(XMLInputFactory factory, String xml)
            throws XMLStreamException {
        XMLStreamReader reader =
                factory.createXMLStreamReader(new StringReader(xml));
        try {
            while (reader.hasNext()) {
                if (reader.next() == XMLStreamConstants.START_ELEMENT
                        && reader.getLocalName().equals("doc")) {
                    return reader.getElementText();
                }
            }
            throw new XMLStreamException("No root");
        } finally {
            reader.close();
        }
    }

    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("stax-catalog-demo-");
        Path catalogFile = directory.resolve("catalog.xml");
        Path dtdFile = directory.resolve("approved.dtd");
        try {
            Files.writeString(dtdFile, "<!ENTITY source \"FromCatalog\">",
                    StandardCharsets.UTF_8);
            Files.writeString(catalogFile,
                    "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
                    + "<catalog xmlns=\"urn:oasis:names:tc:entity:xmlns:xml:catalog\">"
                    + "<system systemId=\"" + APPROVED + "\" uri=\"approved.dtd\"/>"
                    + "</catalog>",
                    StandardCharsets.UTF_8);

            CatalogFeatures features = CatalogFeatures.builder()
                    .with(CatalogFeatures.Feature.RESOLVE, "strict").build();
            CatalogResolver resolver = CatalogManager.catalogResolver(
                    features, catalogFile.toUri());
            XMLInputFactory factory = XMLInputFactory.newDefaultFactory();
            factory.setProperty(XMLInputFactory.SUPPORT_DTD, true);
            factory.setProperty(
                    XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, true);
            factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
            factory.setXMLResolver(resolver);

            String approvedXml =
                    "<!DOCTYPE doc SYSTEM '" + APPROVED + "'>"
                    + "<doc>Chào &source;</doc>";
            if (!"Chào FromCatalog".equals(read(factory, approvedXml))) {
                throw new AssertionError(
                        "Catalog did not resolve approved DTD");
            }
            System.out.println("catalogApproved=PASS");

            String unknownXml =
                    "<!DOCTYPE doc SYSTEM "
                    + "'https://schemas.example.invalid/unlisted.dtd'>"
                    + "<doc>blocked</doc>";
            try {
                read(factory, unknownXml);
                throw new AssertionError(
                        "Unknown catalog reference accepted");
            } catch (XMLStreamException | RuntimeException expected) {
                System.out.println("catalogUnlisted=REJECTED");
            }
        } finally {
            Files.deleteIfExists(catalogFile);
            Files.deleteIfExists(dtdFile);
            Files.deleteIfExists(directory);
        }
    }
}
```

### 9.2. Biên dịch và chạy

```bash
javac --release 17 -encoding UTF-8 CatalogPolicyDemo.java
java CatalogPolicyDemo
```

**Stdout đã kiểm chứng trên JDK 24:**

```text
catalogApproved=PASS
catalogUnlisted=REJECTED
```

Hai kiểm tra đã thành công. `catalogApproved` nghĩa là định danh được duyệt được ánh xạ tới DTD tạm cục bộ; `catalogUnlisted` nghĩa là URI ngoài catalog không được chấp nhận theo chế độ strict.

### 9.3. Những chi tiết cần hiểu

- `CatalogFeatures.builder().with(Feature.RESOLVE,"strict")` chọn **fail-closed lookup**.
- `CatalogManager.catalogResolver(features,catalogFile.toUri())` tạo resolver từ một **URI absolute** trỏ đến catalog file.
- `catalogFile` và `approved.dtd` nằm trong cùng thư mục temp; catalog dùng `uri="approved.dtd"` tương đối với **tệp catalog** do ứng dụng quản lý.
- Factory bật DTD trong **bài thử catalog có chủ đích** để DTD được sử dụng. Đừng bê nguyên `SUPPORT_DTD=true` vào parser dành cho XML không cần DTD.
- EAP đặt chuỗi rỗng để không cho parser tự do tải external resources.
- `CatalogResolver` triển khai `XMLResolver`, nên có thể truyền vào `factory.setXMLResolver(resolver)` trực tiếp.
- Catch `RuntimeException` là để ghi nhận những dạng lỗi catalog như `CatalogException`, không phải khuyến nghị production nuốt mọi RuntimeException. Trong production, nên phân biệt lỗi catalog, XML syntax, filesystem và operation context.
- Test xóa các tệp đã tạo. Nó không sửa repository hoặc tạo tệp ghi nhớ dài hạn.
- Tệp catalog có thể được tải qua filesystem API do **ứng dụng cung cấp**. EAP của StAX không phải sandbox bảo vệ mọi file reads trong ứng dụng.

### 9.4. Độ tin cậy và hạn chế

Một local catalog cũng phải được coi là **dependency có phiên bản**. Nếu người khác có thể sửa catalog hoặc DTD, mapping “được duyệt” vẫn có thể trỏ vào tài nguyên độc hại.

Trong môi trường thật:

- Đóng gói DTD/catalog trong artifact hoặc thư mục read-only với quyền tối thiểu.
- Bảo vệ pipeline cập nhật và kiểm tra integrity/signature/hash khi hợp đồng yêu cầu.
- Tránh trỏ catalog đến symlink hay thư mục do user upload kiểm soát.
- Không dùng `CatalogFeatures.RESOLVE="continue"` nếu yêu cầu mọi tham chiếu phải giải quyết trong allowlist.
- Kiểm thử tất cả referenced nested DTDs/parameter entities, không chỉ URI ở cấp ngoài.
- Kiểm soát đường dẫn thực/realpath và giới hạn file size, ngay cả với local resources.
- Có logging an toàn khi catalog miss, không tạo raw URL fetch fallback.

## 10. So sánh XMLResolver với CatalogResolver

| Tiêu chí | Custom XMLResolver | CatalogResolver |
| --- | --- | --- |
| Mục tiêu | Chính sách resolve theo logic ứng dụng. | Mapping resource theo catalog chuẩn. |
| Cấu hình | Java code/lambda/class. | Catalog XML và `CatalogFeatures`. |
| Input | `publicID`, `systemID`, `baseURI`, `namespace`. | Sử dụng định danh qua hệ catalog. |
| Allowlist | Developer tự kiểm tra chặt chẽ. | System/public/URI mappings. |
| Unmapped resource | Tự `throw XMLStreamException`. | `RESOLVE="strict"` để fail. |
| Local resource | `InputStream` từ bytes trusted hoặc source được duyệt. | Catalog trỏ đến resource đã cấu hình. |
| Portability | API StAX tiêu chuẩn, behavior resolver phụ thuộc provider. | Java XML Catalog API có từ Java 9; JDK hỗ trợ. |
| Rủi ro | Viết nhầm resolver tự mở URL/path. | Catalog/map quá rộng hoặc file bị sửa. |
| Phù hợp | Một số resource hoặc policy động rất hạn chế. | Nhiều DTD/schema được version hóa theo artifact. |

Không cần dùng cả hai cùng lúc. Nếu ứng dụng chỉ cần **từ chối toàn bộ external resources**, cấu hình deny-by-default không sử dụng catalog là đơn giản hơn. Nếu phải dùng DTD, hãy chọn cách giải quyết có thể kiểm chứng và giới hạn tốt nhất.

## 11. Quy tắc của XMLResolver khi identifier không nằm trong allowlist

Một resolver có thể thấy:

```text
publicID = null
systemID = "https://schemas.example.invalid/unlisted.dtd"
baseURI  = null
namespace = null
```

Đó là **ví dụ một callback có thể xảy ra**; không phải giá trị bắt buộc trên mọi implementation/document.

Các lựa chọn:

**A. Trả `null`:**

```java
return null;
```

Nghĩa là **để parser tiếp tục** giải quyết resource theo cơ chế mặc định. Nếu EAP không được khóa, điều này có thể dẫn đến network/file access. Nếu EAP đã khóa, parser có thể ném lỗi/không resolve, nhưng bảo mật giờ phụ thuộc vào một tầng khác.

**B. Trả `new ByteArrayInputStream(new byte[0])`:**

```java
return new ByteArrayInputStream(new byte[0]);
```

Nghĩa là cung cấp **nguồn rỗng** cho parser, **không giống từ chối**. Trong một số trường hợp, parser có thể tiếp tục thiếu DTD/entity declarations và khiến dữ liệu đầu ra bị sai hoặc thiếu. Không dùng cách này làm “deny” khi nghiệp vụ yêu cầu thông báo lỗi rõ ràng.

**C. Ném lỗi:**

```java
throw new XMLStreamException("External resource not allowed");
```

Đây là lựa chọn rõ ràng cho **strict deny policy**, làm parse thất bại thay vì im lặng hoặc thử fallback. Nếu cần cho client một lỗi an toàn, hãy dùng mã lỗi nghiệp vụ chung và correlation ID; tránh trả nguyên systemID nhạy cảm ra HTTP response.

## 12. DTD/entity processing là tính năng riêng, không chỉ chuyện fetch

Kể cả khi **không mở tài nguyên bên ngoài**, một DTD chứa **internal entities** có thể tạo resource-exhaustion nếu entity được mở rộng quá mức. Ví dụ các entity lồng nhau làm lượng text được mở rộng lớn hơn nhiều so với XML input nhỏ ban đầu.

Vì vậy, nên phân lớp:

1. **Không cần DTD:** `SUPPORT_DTD=false`; `IS_SUPPORTING_EXTERNAL_ENTITIES=false`.
2. **Không tự mở URL/file:** `ACCESS_EXTERNAL_DTD=""`.
3. **Nếu có resolver:** chỉ cấp **resource đã duyệt**, throw cho mọi trường hợp khác.
4. **Processing limits:** hạn chế tổng số entity expansions, entity sizes, input bytes, text length và nesting depth.
5. **Application limits:** giới hạn số business records, request timeout, memory budget và thời gian parse.
6. **Test độc lập:** malformed XML, huge input, nested entity definitions, external references, catalog misses và cleanup.

JDK JAXP Security Guide mô tả các cấu hình liên quan như `jdk.xml.entityExpansionLimit`, `jdk.xml.totalEntitySizeLimit` và `jdk.xml.maxElementDepth`. **Tên/kiểu property và khả năng áp dụng phải xác nhận trên phiên bản JDK/parser**, không tự giả định một vendor StAX bên thứ ba sẽ hiểu hết mọi JDK-specific setting.

### 12.1. XMLInputFactory không phải network firewall

Parser có thể được cấu hình đúng, nhưng các đoạn code khác trong ứng dụng vẫn có khả năng mở network. Nếu hệ thống chạy ở môi trường nhạy cảm, cân nhắc:

- Egress network policy/firewall theo service role.
- Không cấp quyền truy cập cloud instance metadata endpoints.
- File permissions tối thiểu và filesystem sandbox phù hợp.
- DNS/IP/redirect controls nếu thật sự cần HTTP fetch.
- Không cho tự cập nhật/catalog từ nguồn XML không tin cậy.
- Telemetry để phát hiện các attempts bị resolver từ chối.

**Defense in depth** quan trọng hơn một cờ boolean trên factory.

## 13. Public ID, System ID, Base URI và namespace

Từng tham số có thể thiếu, thay đổi theo provider hoặc theo cách parser nhìn external reference.

### 13.1. Public ID

XML cho phép khai báo:

```xml
<!DOCTYPE doc PUBLIC "-//Example//DTD Doc 1.0//EN"
                     "https://schemas.example.invalid/doc.dtd">
```

Một resolver/catalog có thể tra theo public identifier, system identifier hoặc phối hợp chúng. Không đánh đồng publicID với DNS host hay xác thực nguồn. Tên public ID là dữ liệu được document cung cấp; chỉ dùng để match với policy cụ thể.

### 13.2. System ID

System ID thường biểu diễn một URI hoặc URI reference. Nó có thể là absolute hoặc relative tùy ngữ cảnh; có thể chứa encoded characters. **Không gọi `new URL(systemId).openStream()` chỉ vì API cung cấp một systemID**.

Nếu muốn cho phép một ID như `APPROVED`, phép `APPROVED.equals(systemId)` là đủ cho **đúng một canonical identifier bạn đã chọn**, nhưng có thể từ chối các cách biểu diễn hợp lệ khác. Đó là trade-off **có chủ đích** trong strict policy.

### 13.3. Base URI

`baseURI` phục vụ phân giải relative IDs. Khi không có baseURI đáng tin hoặc input có thể dẫn đến filesystem/network ngoài ý muốn, **từ chối relative ID** là chiến lược an toàn. Nếu resolver chấp nhận relative, sau khi resolve vẫn phải kiểm tra host/path/encoding và scope của tài nguyên.

### 13.4. Namespace

`namespace` không có nghĩa là external resource sẽ an toàn nếu thuộc một XML namespace hợp lệ. Namespace URI trong XML thường là identifier; **không phải lời cho phép tự tải tài nguyên từ URI đó**. Việc parse XML bình thường có `xmlns="..."` không yêu cầu parser truy cập URL của namespace.

## 14. XML schemaLocation, XSD và XSLT: không phải tất cả đều qua XMLResolver

Một tài liệu có thể chứa:

```xml
<root xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="urn:example https://schemas.example.invalid/types.xsd"/>
```

**StAX XMLResolver chủ yếu liên quan DTD/external entity resolution của StAX parser**. Nó không tự làm XSD validation; nếu ứng dụng sau đó gọi `SchemaFactory`, `Validator` hoặc transform bằng `TransformerFactory`, các processors đó có **policy và resource resolvers riêng**.

| XML processing API | Resolver thường dùng | Cấu hình external access liên quan |
| --- | --- | --- |
| StAX `XMLInputFactory` | `javax.xml.stream.XMLResolver` | `ACCESS_EXTERNAL_DTD`, DTD/entity properties. |
| SAX/DOM | `org.xml.sax.EntityResolver` | External DTD/entity feature flags, EAP. |
| XSD `SchemaFactory`/`Validator` | `org.w3c.dom.ls.LSResourceResolver` | `ACCESS_EXTERNAL_SCHEMA` và DTD/other parser controls. |
| XSLT `TransformerFactory` | `javax.xml.transform.URIResolver` | `ACCESS_EXTERNAL_STYLESHEET`, FSP và extension/function policy. |
| Java Catalog | `CatalogResolver` có thể tích hợp nhiều API trên | `CatalogFeatures`/catalog mapping + policy từng processor. |

`XMLConstants.ACCESS_EXTERNAL_SCHEMA` và `ACCESS_EXTERNAL_STYLESHEET` có giá trị khi xử lý schema/stylesheet, nhưng **không thay cho `ACCESS_EXTERNAL_DTD` của StAX**. Đặt một EAP không tự áp lên tất cả loại tài nguyên.

Nếu pipeline của bạn parse bằng StAX rồi validate XSD bằng schema processor, phải áp dụng restrictions cho **cả hai tầng**; không coi việc StAX không tải XSD khi chỉ parse là chứng minh validator cũng an toàn.

## 15. Thứ tự cấu hình và thay đổi provider

StAX có thể được cấp bởi JDK built-in provider hoặc library XML parser khác. Các method hiện hành:

```java
XMLInputFactory factory = XMLInputFactory.newFactory();
factory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
factory.setProperty(XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
factory.setXMLResolver(resolver);
XMLStreamReader reader = factory.createXMLStreamReader(source);
```

`resolver` và `source` ở đây là những biến được ứng dụng cung cấp; đây là **mảnh code tích hợp**, không phải source độc lập.

Chú ý:

- **Thứ tự** nên là tạo factory → đặt policy/properties/resolver → tạo reader → parse.
- Không thay policy của một factory đang được dùng chung một cách không đồng bộ rồi giả định mọi readers lập tức nhận cập nhật.
- Với `newFactory()`, provider discovery có thể chọn parser bên ngoài; xem class/vendor trong môi trường thử nếu quan trọng.
- Với `newDefaultFactory()` trên Java 17+, JDK default implementation được chọn; thích hợp cho test deterministic của bài.
- Nếu `setProperty` ném `IllegalArgumentException`, không bỏ qua thiết lập bảo mật quan trọng; fail deployment hoặc chuyển sang provider có hỗ trợ.
- `getProperty`/`isPropertySupported` có thể giúp thăm dò, nhưng **support flag không thay cho thử nghiệm hành vi thực**.

### 15.1. Resolver có thể được gọi nhiều lần

Một tài liệu có thể tham chiếu nhiều DTDs, parameter entities và external general entities. Đừng viết resolver chỉ kiểm tra “lần gọi đầu được duyệt” rồi cho những lần sau đi qua. **Mỗi lần callback phải kiểm tra policy độc lập**, kể cả nguồn phát sinh trong tài nguyên đã được allowlist.

Trong tests đơn giản của bài, callback count bằng 1 cho DTD được cho phép, nhưng production không được phụ thuộc vào con số đó.

### 15.2. Vòng đời InputStream/Reader

`XMLStreamReader.close()` giải phóng tài nguyên do reader sở hữu **nhưng không bảo đảm tự đóng nguồn `InputStream` hoặc `Reader` mà caller đã truyền vào**. Cấu trúc tài nguyên:

```java
try (InputStream input = Files.newInputStream(path)) {
    XMLStreamReader reader = factory.createXMLStreamReader(input);
    try {
        while (reader.hasNext()) {
            reader.next();
            // Xử lý events.
        }
    } finally {
        reader.close();
    }
}
```

Đây là mảnh code tích hợp cần `path`, `factory`, imports và file hợp lệ. Nguồn bên ngoài được resolver trả về cũng cần được quản lý theo contract parser/provider, đặc biệt nếu mở file hoặc stream dài; không giữ file descriptors vô hạn hoặc cache một InputStream đã bị đọc hết để tái sử dụng cho lần callback khác.

Trong demo, mỗi lần phân giải tạo một **ByteArrayInputStream mới**, tránh dùng chung vị trí đọc giữa các lần parse.

## 16. Điều kiện phải kiểm thử trước khi triển khai

| Kiểm thử | Input/policy | Kết quả cần đạt |
| --- | --- | --- |
| XML không DTD | Element/text thông thường | Parse bình thường, không truy cập external resource. |
| URI allowlisted | DTD cố định/đúng ID | Resolver cấp nội dung trusted, parse đúng. |
| Unknown systemID | URI ngoài danh sách | **Reject**, không trả null/default fetch. |
| PublicID giả | Đúng systemID nhưng publicID khác policy | Từ chối nếu policy chỉ chấp nhận publicID null/đúng giá trị. |
| Relative ID | `systemID="a.dtd"` | Reject nếu không có explicit trusted base/mapping. |
| File URI | `file:///...` | Không truy cập file ngoài policy. |
| Network URI | `http/https://...` không duyệt | Không thực hiện fetch, trả lỗi. |
| Redirect/host deception | Host tương tự, userInfo, redirect | Không vượt allowlist. |
| Nested external entity | Approved DTD chứa một external reference mới | Callback thứ hai phải được kiểm tra, unknown bị reject. |
| Malformed XML | Thẻ không khớp | XMLStreamException, không chuyển thành default fetch. |
| Internal entity expansion | DTD/entity lồng quá nhiều | Processing limits chặn resource exhaustion. |
| Large document | XML input lớn | Đúng quota/timeouts/heap budget. |
| Catalog strict miss | ID không có trong catalog | Lỗi catalog, không tiếp tục tìm ngoài. |
| Unsupported property | Provider không hỗ trợ EAP/DTD setting | Parser setup fail, không silently relax policy. |
| Resource cleanup | Parse thành công/lỗi giữa chừng | Reader/input streams được đóng, không leak. |

**Tách kết quả khác nhau:** "XML có cú pháp không hợp lệ", "DTD bị chính sách từ chối", "catalog không có mapping", "property không được hỗ trợ" và "I/O lỗi" là những nguyên nhân khác nhau. Không gom mọi `XMLStreamException` thành "XML malformed".

### 16.1. Ghi log an toàn

Có thể ghi:

```text
event=xml.external_resource.denied
operation=import-document
resolutionKind=external-dtd
identifierCategory=unapproved-system-id
parserProvider=<configured provider>
correlationId=<request-id>
outcome=REJECTED
```

Đây là **mẫu log**, không phải stdout từ code. Nếu systemID chứa thông tin nhạy cảm, query token hoặc nội bộ network path, cần redaction/hash hoặc bỏ URI thô khỏi log. Không ghi toàn XML document người dùng tải lên nếu không có cơ sở và chính sách bảo mật dữ liệu.

## 17. Sai lầm thường gặp

| Hiểu nhầm | Vì sao sai | Cách đúng |
| --- | --- | --- |
| `resolveEntity()` trả null nghĩa từ chối. | Parser có thể tiếp tục default resolution. | Throw cho ID không được duyệt. |
| `ACCESS_EXTERNAL_DTD=""` bảo vệ cả code resolver. | EAP không hạn chế non-null resource do resolver tự cấp. | Resolver chỉ cấp nguồn trusted. |
| `ACCESS_EXTERNAL_DTD="https"` chỉ cho host của tôi. | EAP giới hạn protocol, không hostname/path. | Exact allowlist hoặc local catalog. |
| Chỉ cấm `http:` là đủ. | `https:`, `file:`, `jar:` và schemes khác vẫn có thể rủi ro. | Deny-by-default toàn bộ. |
| Dùng `startsWith(trustedHost)` để allowlist. | Host confusion và URI parser tricks. | So exact canonical identifiers/URI fields. |
| Gọi `new URL(systemId).openStream()` trong resolver. | URI không tin cậy điều khiển network/file I/O. | Không fetch trực tiếp; map tới local resource. |
| `SUPPORT_DTD=false` luôn throw khi có DOCTYPE. | Có parser chỉ bỏ qua DTD. | Nếu cần reject DOCTYPE, áp chính sách explicit và test. |
| Tắt external entities là hết XML bomb. | Internal entity expansion/large XML vẫn có thể tốn tài nguyên. | Processing limits và input quotas. |
| Chỉ bảo vệ factory trước parser provider JDK. | Provider được thay đổi khi dùng newFactory. | Test provider thật, fail closed. |
| Catalog strict miss sẽ fallback network. | Strict định nghĩa hành vi lỗi khi không map. | Giữ strict và EAP deny. |
| Chọn catalog với `continue` vẫn deny. | Continue cho cơ chế khác xử lý. | Dùng strict nếu yêu cầu allowlist. |
| File catalog luôn an toàn. | File/symlink bị sửa có thể trỏ tài nguyên khác. | Trusted immutable catalog và filesystem access control. |
| Cấu hình StAX sẽ bảo vệ XSD/XSLT. | Validator/transformer có resolvers/EAP riêng. | Cấu hình từng processor. |
| Namespace URI trong XML phải được tải qua HTTP. | Namespace thường chỉ là identifier. | Không tự dereference namespace URI. |
| Chỉ kiểm tra callback đầu tiên. | Có nested DTD/parameter entities. | Kiểm tra từng resolver invocation. |
| Dùng một InputStream cho nhiều lần resolve. | Stream đã bị đọc/đóng một phần. | Tạo source mới mỗi lần. |
| Đóng XMLStreamReader là đóng mọi input. | Caller-owned source không được bảo đảm đóng. | Quản lý InputStream/Reader riêng. |
| Khi XML parse lỗi, cứ retry network fetch. | Có thể tăng rủi ro/độ trễ và phá policy. | Phân loại lỗi, không tự retry external URIs. |
| Log raw systemID/DTD toàn bộ. | Có thể chứa nội bộ file paths, tokens/PII. | Redaction và structured logging. |

## 18. Checklist kiến trúc production

- [ ] Đã xác định XML documents có **thực sự cần DTD/external entities** hay không?
- [ ] Nếu không cần, đã đặt `SUPPORT_DTD=false` và `IS_SUPPORTING_EXTERNAL_ENTITIES=false`?
- [ ] `ACCESS_EXTERNAL_DTD=""` được set trước khi tạo parser?
- [ ] Có resolver fail-closed khi cần, không trả null cho ID lạ?
- [ ] Khi cho phép một DTD, mapping chỉ tới nội dung/tệp **trusted**?
- [ ] Không có `URL.openStream()` hoặc open file trực tiếp bằng untrusted systemID?
- [ ] Nếu có relative URI, baseURI và kết quả resolve có được chuẩn hóa/kiểm tra lại?
- [ ] Có chặn host confusion, redirect, userInfo, path traversal và unsafe schemes?
- [ ] Nếu dùng catalog, `RESOLVE="strict"` và catalog immutable?
- [ ] Mọi nested references cũng được áp chính sách?
- [ ] DTD/entity expansion, total input bytes, nesting và parse duration có limits?
- [ ] Parser provider thực được test trong CI với negative cases?
- [ ] Unsupported security property làm setup fail, không silently ignore?
- [ ] Application-level network egress/file permissions được hạn chế thêm?
- [ ] Đã phân biệt policy reject và malformed XML trong diagnostics?
- [ ] Đã bảo vệ XSD `SchemaFactory`/XSLT `TransformerFactory` nếu pipeline sử dụng?
- [ ] Đã đóng reader/source streams và resource resolver đúng ownership?
- [ ] Có test unknown URI, relative URI, file URI, network URI, nested DTD và catalog miss?
- [ ] Có kiểm tra đúng SQL/XML StAX business outcome mà không cần external fetch?
- [ ] Các lỗi bị từ chối không rò raw XML/token/path trong logs hoặc client messages?

## 19. Bài tập thực hành

**A — Deny-by-default.** Trong `XmlResolverPolicyDemo.java`, thử tài liệu XML bình thường không có DTD. Giải thích vì sao `SUPPORT_DTD=false` và `IS_SUPPORTING_EXTERNAL_ENTITIES=false` phù hợp.

**B — Không được fallback.** Thay nhánh `throw new XMLStreamException(...)` bằng `return null` trong một sandbox có EAP vẫn khóa; quan sát sự thay đổi loại lỗi. Giải thích vì sao return null **không phải** một policy deny an toàn nếu EAP/cấu hình provider thay đổi.

**C — Allowlist.** Thêm một định danh DTD thứ hai trong code và content riêng. Làm sao bảo đảm mỗi identifier chỉ nhận đúng nội dung đã được duyệt?

**D — Public ID.** Cho XML có `PUBLIC` identifier và cùng systemID. Kiểm tra callback `publicID` và sửa policy theo business requirements.

**E — Relative URI.** Gửi `"approved.dtd"` thay vì absolute systemID. Trong demo strict hiện tại nó bị từ chối. Hãy giải thích lợi ích bảo mật của việc không tự resolve bằng baseURI từ XML.

**F — Catalog strict.** Trong `CatalogPolicyDemo.java`, đổi `systemId` của input sang URI không có mapping; vì sao kết quả là REJECTED và không phải một HTTP request thành công?

**G — Catalog continue.** So sánh `RESOLVE="strict"` với `"continue"` trong một sandbox có EAP deny và một môi trường có EAP lỏng. Vì sao môi trường cấu hình khác có thể thay đổi hành vi fallback?

**H — Nested entities.** Thêm một external entity trong DTD được duyệt trỏ tới một URI không được allowlist. Thiết kế test chứng minh callback mới vẫn bị từ chối.

**I — Resource limits.** Tạo dữ liệu XML có nhiều internal entity expansions nhưng **giữ quy mô nhỏ, an toàn trong sandbox**. Bật entity-expansion limits và kiểm tra failure category.

**J — Provider differences.** Thay parser provider trên một môi trường thử, kiểm chứng `isPropertySupported`, security settings, expected exceptions và reader cleanup. Không coi mọi implementation có cùng event layout/callback counts.

**K — Egress policy.** Tại tầng môi trường triển khai, chặn toàn bộ outbound Internet requests của XML-import worker, để dù resolver bị viết sai vẫn không đọc được metadata/internal networks.

**L — Logging.** Viết formatter chỉ ghi operation ID, event category, correlation ID và mã policy rejection; tránh raw systemIDs hoặc nội dung tài liệu có dữ liệu nhạy cảm.

## 20. Câu hỏi tự kiểm tra

**1.** `XMLResolver.resolveEntity` được gọi để làm gì? — Để ứng dụng tùy chỉnh cách StAX phân giải tài nguyên bên ngoài khi parser cần xử lý references.

**2.** Callback có những tham số nào? — `publicID`, `systemID`, `baseURI`, `namespace`.

**3.** Có thể trả những kiểu object nào? — Theo Java SE: `InputStream`, `XMLStreamReader` hoặc `XMLEventReader`, hoặc trả null để parser thử cơ chế mặc định.

**4.** `return null` có phải deny tuyệt đối? — **Không.** Nó cho parser cơ hội fallback; strict policy nên throw.

**5.** `ACCESS_EXTERNAL_DTD=""` có chặn resolver tự gọi `URL.openStream` không? — **Không**. EAP không kiểm soát non-null resource do custom resolver cấp.

**6.** Có nên để `ACCESS_EXTERNAL_DTD="https"` để chỉ cho một host duy nhất không? — **Không.** Giá trị chỉ liệt kê protocols, không phải danh sách host.

**7.** Nếu không cần DTD, cấu hình nào thường phù hợp? — `SUPPORT_DTD=false`, `IS_SUPPORTING_EXTERNAL_ENTITIES=false`, `ACCESS_EXTERNAL_DTD=""` và resolver deny nếu được gọi.

**8.** `SUPPORT_DTD=false` có luôn từ chối XML chứa DOCTYPE? — **Không được giả định**; một số parser bỏ qua DTD. Nếu yêu cầu reject toàn bộ DOCTYPE, cần policy/test riêng.

**9.** Một DTD được duyệt có thể chứa nested references không? — Có. Mỗi callback cần kiểm tra allowlist lại.

**10.** `CatalogResolver` có dùng được làm StAX XMLResolver không? — **Có.** Nó implements `XMLResolver` trong Java XML Catalog API.

**11.** `CatalogFeatures.Feature.RESOLVE="strict"` có ý nghĩa gì? — Khi không tìm thấy mapping, catalog báo lỗi thay vì cho parser tiếp tục tự tìm tài nguyên.

**12.** Đã có XMLResolver an toàn thì có cần processing limits? — **Có.** Nội dung trusted vẫn có thể lớn hoặc khai báo internal entities tốn tài nguyên.

**13.** Namespace URI trong `xmlns` có luôn là địa chỉ cần tải không? — **Không.** Nó thường là identifier, parser không cần mở URL chỉ vì thấy namespace declaration.

**14.** Nếu pipeline còn validate XSD hoặc transform XSLT, có cần cấu hình resolver khác không? — **Có.** Các processors có policy/EAP/resolvers riêng.

**15.** Hai chương trình ví dụ đã được kiểm thử trên môi trường nào? — `javac --release 17` trên JDK 24, 7 checks cho custom resolver và 2 checks cho strict XML catalog. Không có network/database dependency.

## 21. Tài liệu chính thức hiện hành

- [XMLResolver — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/stream/XMLResolver.html): `resolveEntity(publicID,systemID,baseURI,namespace)`, return types và null fallback.
- [XMLInputFactory — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLInputFactory.html): `setXMLResolver`, `SUPPORT_DTD`, `IS_SUPPORTING_EXTERNAL_ENTITIES`, `RESOLVER` và `ACCESS_EXTERNAL_DTD`.
- [XMLStreamReader — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLStreamReader.html): StAX reader events, `getElementText` và lifecycle.
- [XMLStreamException — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLStreamException.html): lỗi phân giải/parse, location và cause.
- [CatalogResolver — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/catalog/CatalogResolver.html): implementation đa giao diện, resolve modes và mappings.
- [CatalogFeatures — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/catalog/CatalogFeatures.html): `FILES`, `PREFER`, `DEFER`, `RESOLVE`, strict/continue/ignore.
- [CatalogManager — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/catalog/CatalogManager.html): tạo catalog và catalog resolver.
- [XMLConstants — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/XMLConstants.html): `ACCESS_EXTERNAL_DTD`, `ACCESS_EXTERNAL_SCHEMA`, `ACCESS_EXTERNAL_STYLESHEET`.
- [JAXP Security Guide — Java SE 25](https://docs.oracle.com/en/java/javase/25/security/java-api-xml-processing-jaxp-security-guide.html): giải thích resolver precedence, EAPs, StAX FSP limitations, XML Catalog API, DTD và processing limits.

**Ghi nhớ:** `XMLResolver` không chỉ là tiện ích tìm DTD; nó là một **ranh giới kiểm soát tài nguyên**. **Không cần external resources thì tắt DTD/entity resolution và đặt EAP deny**. Khi thật sự cần, chỉ ánh xạ định danh **được duyệt chính xác** sang tài nguyên trusted, **throw với mọi ID khác**, không trả null để fallback. `ACCESS_EXTERNAL_DTD=""` không thay thế việc viết resolver an toàn, vì non-null resolver result vượt qua bước kiểm soát giao thức của parser. Dùng `CatalogResolver` strict nếu có nhiều resources, kiểm soát nested references, limits, provider và lifecycle bằng tests cụ thể.
