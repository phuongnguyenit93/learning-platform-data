# Phòng tránh path traversal, XXE và giải tuần tự dữ liệu không tin cậy trong Java 27

Một ứng dụng Java xử lý đường dẫn do người dùng gửi, đọc XML từ API bên ngoài hoặc nhận dữ liệu tuần tự hóa từ mạng đang đưa **dữ liệu không tin cậy vượt qua ranh giới bảo mật**. Nếu coi dữ liệu đó là một phần của đường dẫn, một chỉ thị tải tài nguyên XML hoặc một đối tượng Java tùy ý, ứng dụng có thể vô tình đọc dữ liệu ngoài phạm vi được phép, gọi ra hệ thống nội bộ hoặc thực thi hành vi nguy hiểm khi tái tạo đối tượng.

Bài học thuộc chương **Bảo mật ứng dụng Java**, tập trung vào ba nhóm lỗi thường liên quan đến **nhầm lẫn giữa dữ liệu và quyền thực hiện thao tác**:

1. **Path traversal (CWE-22):** một giá trị đầu vào thay đổi vị trí tệp mà chương trình mở, kể cả qua `..`, đường dẫn tuyệt đối hay symbolic link.
2. **XML External Entity – XXE (CWE-611):** bộ xử lý XML truy cập DTD, entity, schema hoặc tài nguyên ngoài không được phép.
3. **Unsafe deserialization (CWE-502):** tái tạo object từ dòng byte không tin cậy, có thể kích hoạt logic của lớp trước khi ứng dụng kiểm tra kiểu kết quả.

Các ví dụ dùng những API còn hiện hành trong **Java 27**: `Path`, `Files`, `SecureDirectoryStream`, JAXP, `ObjectInputFilter` và các API quản lý tài nguyên. Không sử dụng `SecurityManager` làm giải pháp: Java đã vô hiệu hóa vĩnh viễn cơ chế Security Manager theo **JEP 486 (JDK 24)**. Mục tiêu là thiết kế **không cấp quyền cho dữ liệu đầu vào**, không vá lỗi bằng một danh sách chặn ký tự đơn giản.

> **Nguyên tắc chung:** xác định rõ **tài nguyên được phép**, **thành phần có quyền mở tài nguyên**, **cấu hình parser/filter**, và **giới hạn kích thước/thời gian**. Khi không thể cấu hình biện pháp bảo mật bắt buộc, nên **fail closed** thay vì tiếp tục với mặc định không rõ.

## 1. Ba bề mặt tấn công và ranh giới tin cậy

| Điểm vào | Dữ liệu không tin cậy | Thao tác nguy hiểm nếu xử lý sai | Chiến lược chính |
| --- | --- | --- | --- |
| API tải tệp | Tên tệp/đường dẫn từ URL, form, message | `Files.readAllBytes`, `Files.newInputStream`, xóa/ghi tệp ngoài thư mục cho phép | Không chấp nhận đường dẫn tùy ý; giới hạn tên, dùng `Path` và thao tác chống race |
| API nhận XML | XML, DTD, `xsi:schemaLocation`, chỉ thị XSLT | Parser/transformer đọc tệp nội bộ hoặc truy cập URL không được phép | Từ chối DTD khi không cần; khóa external access ở từng loại JAXP factory |
| API nhận bytes/object | Java Serialization stream, XMLDecoder hoặc binding tự động | Tạo object/đồ thị object ngoài dự kiến, gọi hook giải tuần tự | Tránh native deserialization; khi bất khả kháng mới dùng allowlist + giới hạn resource + filter |

Ví dụ luồng dữ liệu:

```text
HTTP request / upload / queue message
       │
       ▼
[Untrusted bytes / string]
       │
       ├─ path parameter ───> resolver ───> OS file system
       │                         ▲
       │                 phải kiểm tra phạm vi và link
       │
       ├─ XML document ────> JAXP parser/validator/transformer
       │                         ▲
       │                 chặn DTD, external resources
       │
       └─ serialized bytes ─> ObjectInputStream / binding
                                 ▲
                         ưu tiên không dùng Java serialization
```

**Input validation** chỉ là một phần. Một tên tệp hợp lệ về cú pháp vẫn có thể chỉ tới symbolic link; một XML có cấu trúc hợp lệ vẫn có thể chứa chỉ thị truy cập ngoài; một dòng serialization có header hợp lệ vẫn có thể tạo lớp không được phép.

## 2. Path traversal: cơ chế và điều kiện có thể xảy ra

Giả sử ứng dụng cho tải tài liệu trong thư mục cấu hình:

```text
/opt/app/documents/
  handbook.pdf
  invoice-001.pdf

/opt/app/secrets/
  credentials.txt
```

Một implementation nguy hiểm:

```java
// KHÔNG DÙNG: trực tiếp ghép dữ liệu người dùng thành đường dẫn.
Path root = Path.of("/opt/app/documents");
Path requested = root.resolve(userProvidedPath);
byte[] content = Files.readAllBytes(requested);
```

Nếu `userProvidedPath` là `../secrets/credentials.txt`, phép `resolve` có thể tạo đường dẫn ra ngoài tài liệu. Đây chỉ là ví dụ minh họa lỗi đường dẫn; khi thử nghiệm nên dùng tệp giả và không truy cập dữ liệu thật.

Những biến thể khác cần cân nhắc:

- Đường dẫn tuyệt đối có thể khiến `resolve` **bỏ qua base** tùy provider.
- Trên Windows, có dấu phân cách `\`, ổ đĩa, UNC path và các quy tắc tên riêng.
- Có thể có nhiều lớp decode URL: `%2e%2e%2f` có thể trở thành `../` ở một tầng xử lý; không kiểm tra trước decode rồi mở sau decode.
- Symbolic link bên trong thư mục hợp lệ có thể trỏ ra ngoài thư mục được phép.
- Tệp/thư mục có thể bị thay đổi **giữa lúc kiểm tra và lúc mở** (*time-of-check-to-time-of-use*, TOCTOU).
- Hard link, mount point và file-system provider có thể tạo quan hệ ngoài phạm vi chỉ kiểm tra bằng cách so sánh chuỗi.

Bảo mật không dựa trên một biểu thức `input.contains("..")`. Quy tắc này dễ bỏ sót biểu diễn đường dẫn khác, đồng thời có thể chặn nhầm tên hợp lệ.

### 2.1. normalize và startsWith: quan trọng nhưng chưa đủ

```java
Path base = Path.of("/opt/app/documents").toAbsolutePath().normalize();
Path candidate = base.resolve(userProvidedPath).normalize();

if (!candidate.startsWith(base)) {
    throw new SecurityException("Outside document directory");
}
```

Đoạn trên **kiểm tra quan hệ đường dẫn theo từ vựng (*lexical*)**, giúp chặn `..` vượt base trong nhiều trường hợp. Nhưng:

- `normalize()` **không truy cập hệ thống tệp**; nó không giải quyết symbolic links.
- `Path.startsWith(Path)` kiểm tra theo **thành phần đường dẫn** (phù hợp hơn kiểm tra prefix chuỗi), nhưng cũng không tự chặn race hoặc hard links.
- `candidate.startsWith(base)` có thể đúng **trước** khi một entry thuộc base bị thay thành symlink; thao tác mở sau đó có thể theo link.
- Đường dẫn của các provider khác nhau không nhất thiết có cùng quy tắc so sánh/case sensitivity.

Do đó, đoạn trên là **một bước phòng vệ, không phải bằng chứng an toàn đầy đủ**.

### 2.2. toRealPath: đối chiếu với filesystem đang tồn tại

Với các tệp **đã tồn tại**, ta có thể so sánh đường dẫn thực:

```java
Path baseReal = configuredRoot.toRealPath();
Path fileReal = baseReal.resolve(relativeName).toRealPath();

if (!fileReal.startsWith(baseReal)) {
    throw new SecurityException("Resolved file leaves allowed root");
}
```

`toRealPath()` mặc định giải quyết symbolic links tới đích, nên có thể phát hiện link trỏ ra ngoài **tại thời điểm kiểm tra**. Tuy nhiên, các entry vẫn có thể bị thay thế trước khi gọi `Files.newInputStream(fileReal)`. `toRealPath(LinkOption.NOFOLLOW_LINKS)` cũng **không đồng nghĩa** “có một sandbox”: tùy hệ thống tệp, nó có thể không giải quyết links, vì vậy không thể dùng nó thay cho chính sách quyền truy cập.

**Kết luận:** dùng canonical/real-path checks khi phù hợp để phát hiện đường dẫn vượt ranh giới, nhưng với thư mục có thể bị attacker chỉnh sửa, cần thao tác dựa trên **directory handle** hoặc ranh giới OS/FS chặt hơn để đối phó race.

## 3. Thiết kế phòng thủ path traversal cho endpoint tải một tệp

Nếu API chỉ có nhiệm vụ tải **một tệp theo tên** chứ không phải truy cập cây thư mục tùy ý, cách đơn giản nhất là **không cho client cung cấp một đường dẫn**.

Ví dụ hợp đồng:

```http
GET /documents/handbook.pdf
```

Controller nhận **leaf filename**, không nhận đường dẫn chứa dấu phân cách. Một chính sách mẫu:

```java
import java.util.regex.Pattern;

private static final Pattern SAFE_LEAF =
        Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{0,127}");

static String validateLeaf(String userValue) {
    if (userValue == null || !SAFE_LEAF.matcher(userValue).matches()) {
        throw new IllegalArgumentException("Invalid document name");
    }
    return userValue;
}
```

Quy tắc trên:

- Chỉ nhận một tập ký tự được phép và độ dài có giới hạn.
- Không cho phép `/`, `\`, dấu hai chấm hay chuỗi chỉ có `..`.
- Không dùng nội dung đầu vào làm absolute path hoặc tự chọn thư mục.
- Có thể chưa đủ cho mọi file system (ví dụ tên thiết bị đặc biệt trên Windows), nên cần thiết kế contract theo môi trường triển khai.

Thậm chí an toàn hơn là **không đưa tên tệp nội bộ ra API**: nhận document ID dạng UUID, truy vấn metadata/ACL ở server rồi map nó đến đường dẫn do server kiểm soát.

### 3.1. Kiểm tra quyền truy cập là bắt buộc

Một tên tệp an toàn về mặt đường dẫn **không có nghĩa người dùng được quyền đọc tệp đó**. Endpoint còn phải kiểm tra:

1. User/tenant đã được xác thực hay chưa.
2. Tài liệu có thuộc tenant hiện tại không.
3. User có quyền đọc hoặc tải tài liệu này không.
4. Kết quả metadata có còn hợp lệ tại thời điểm thực hiện thao tác không.
5. Lỗi quyền và lỗi tồn tại có được trả về theo chính sách tránh lộ thông tin không.

**Path traversal** và **broken object-level authorization** là hai rủi ro khác nhau. Phòng tránh một lỗi không tự động xử lý lỗi còn lại.

## 4. SecureDirectoryStream: chống thay thế đường dẫn trong lúc mở

`java.nio.file.SecureDirectoryStream<Path>` cho phép thao tác tương đối với **directory handle đã mở**. Nó được thiết kế cho những ứng dụng bảo mật cần giảm race khi các phần của đường dẫn bị đổi/di chuyển bởi tiến trình khác.

**Điều kiện quan trọng:** API chỉ hoạt động khi file-system provider và hệ điều hành hỗ trợ. Kết quả `Files.newDirectoryStream(...)` **không phải lúc nào** cũng là `SecureDirectoryStream`. Với dữ liệu không tin cậy nằm trong một thư mục attacker có quyền sửa, không nên rơi về cách mở đường dẫn thông thường rồi giả định an toàn tương đương.

### 4.1. Ví dụ độc lập: đọc tệp thông qua directory handle

Ví dụ dưới đây chỉ nhận tên tệp một cấp, từ chối final symbolic link, giới hạn kích thước dữ liệu (1 MiB), và **fail closed** nếu provider không có `SecureDirectoryStream`. Giả định `configuredRoot` là thư mục cố định, được cấu hình bởi server, **không** lấy từ request.

```java
// File: SecureDocumentReaderDemo.java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.SeekableByteChannel;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.SecureDirectoryStream;
import java.nio.file.StandardOpenOption;
import java.util.Set;
import java.util.regex.Pattern;

public final class SecureDocumentReaderDemo {
    private static final int MAX_BYTES = 1_048_576;
    private static final Pattern SAFE_LEAF =
            Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{0,127}");

    private SecureDocumentReaderDemo() {}

    static byte[] readOneFile(Path configuredRoot, String fileName)
            throws IOException {

        if (fileName == null || !SAFE_LEAF.matcher(fileName).matches()) {
            throw new IllegalArgumentException("Invalid file name");
        }

        // Root do server cấu hình, không đến từ client.
        Path root = configuredRoot.toRealPath();

        try (DirectoryStream<Path> directory = Files.newDirectoryStream(root)) {
            if (!(directory instanceof SecureDirectoryStream<?>)) {
                throw new IOException("Secure directory access unavailable");
            }

            @SuppressWarnings("unchecked")
            SecureDirectoryStream<Path> secure =
                    (SecureDirectoryStream<Path>) directory;

            // Tên file chỉ có một thành phần, mở tương đối với handle.
            try (SeekableByteChannel channel = secure.newByteChannel(
                    Path.of(fileName),
                    Set.of(StandardOpenOption.READ, LinkOption.NOFOLLOW_LINKS))) {

                ByteArrayOutputStream output = new ByteArrayOutputStream();
                ByteBuffer buffer = ByteBuffer.allocate(8_192);

                while (channel.read(buffer) != -1) {
                    buffer.flip();

                    if ((long) output.size() + buffer.remaining() > MAX_BYTES) {
                        throw new IOException("Document exceeds size limit");
                    }

                    output.write(
                        buffer.array(), 0, buffer.remaining());
                    buffer.clear();
                }
                return output.toByteArray();
            }
        }
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 2) {
            System.out.println(
                "Usage: java SecureDocumentReaderDemo <trusted-dir> <filename>");
            return;
        }

        byte[] bytes = readOneFile(Path.of(args[0]), args[1]);
        System.out.println("Read " + bytes.length + " bytes");
    }
}
```

Giải thích:

- `root.toRealPath()` xác định root đã tồn tại, nhưng việc an toàn vẫn phụ thuộc **root thuộc phạm vi cấu hình đáng tin cậy**.
- `Files.newDirectoryStream(root)` mở handle cho thư mục; code yêu cầu capability `SecureDirectoryStream` thay vì âm thầm giảm mức bảo vệ.
- `secure.newByteChannel(Path.of(fileName), Set.of(READ, NOFOLLOW_LINKS))` mở entry tương đối với **directory handle**, và không theo symlink ở entry cuối.
- `MAX_BYTES` chặn đọc tệp quá lớn vào RAM. Trong sản phẩm, nên ưu tiên **streaming response** có hạn mức và chính sách timeout nếu kích thước tệp lớn.
- `try-with-resources` đóng cả channel lẫn directory handle khi hoàn tất hoặc có exception.
- `main` chỉ in kích thước, không hiển thị nội dung tệp.

**Giới hạn:** một directory handle không tự cấp quyền đọc nếu OS từ chối; `SecureDirectoryStream` không thay thế kiểm tra ACL/tenant. Hard link và mount points có thể cần chính sách riêng. Nếu root được di chuyển trong lúc xử lý, thao tác tương đối với handle vẫn áp dụng cho đối tượng thư mục đã mở; hành vi đó có thể cần cân nhắc trong chính sách vận hành.

### 4.2. Nếu filesystem không hỗ trợ SecureDirectoryStream?

Đừng chuyển sang cách yếu hơn **một cách ngầm định** khi attacker có thể ghi vào thư mục. Hãy lựa chọn một trong các hướng có bằng chứng phù hợp:

- Chuyển nội dung cần bảo vệ vào thư mục **không cho đối tượng không tin cậy sửa tên/đổi symlink**, và dùng quyền OS thích hợp.
- Sử dụng storage service có object IDs, quyền truy cập và thao tác nguyên tử được cung cấp rõ.
- Dùng provider/API của OS hỗ trợ thao tác theo directory handle.
- Từ chối chức năng có mức bảo vệ không đạt yêu cầu trên môi trường đó.

Đối với **upload**, không tin vào filename gốc để ghi file. Tạo tên nội bộ ngẫu nhiên, lưu metadata tên gốc riêng để hiển thị sau khi escape phù hợp, và dùng `CREATE_NEW`/quyền file thích hợp để tránh overwrite không mong muốn. Chặn path traversal **không** giải quyết vấn đề file upload chứa malware hoặc thực thi nội dung, nên còn cần policy loại tệp, quét nội dung và nơi lưu ngoài executable web root.

## 5. XML External Entity (XXE) là gì?

XML có thể chứa `DOCTYPE`, định nghĩa entity và tham chiếu tới tài nguyên ngoài. Khi parser cho phép tải external DTD/entity, dữ liệu XML do người ngoài cung cấp có thể khiến server:

- Đọc tệp cục bộ ngoài ý muốn.
- Gửi request tới địa chỉ nội bộ hoặc bên ngoài (*server-side request forgery – SSRF*).
- Tốn nhiều CPU/bộ nhớ do entity expansion hoặc XML quá sâu.
- Làm lộ dữ liệu qua kết quả parse, log hoặc lỗi chi tiết.

Một ví dụ XML **chỉ dùng entity nội bộ** để minh họa cấu trúc (không truy cập tệp hay URL):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE note [
    <!ENTITY author "Example">
]>
<note><from>&author;</from></note>
```

Với những API **không cần DTD**, nên **từ chối toàn bộ DOCTYPE**, không chỉ tắt riêng external entities. Việc cho phép một phần DTD đôi khi vẫn để lại rủi ro expansion/DoS hoặc các tính năng khác của parser.

**XXE không chỉ nằm ở DOM**: SAX, StAX, XSLT, schema validator, XPath (nếu parse XML trước đó), JAXB/unmarshaller và các thư viện XML bên thứ ba có thể có bề mặt khác nhau. Mỗi thành phần tạo parser/transformer phải được cấu hình phù hợp.

## 6. Cấu hình DOM parser chống XXE trong Java 27

`DocumentBuilderFactory` và `DocumentBuilder` thuộc JAXP (`javax.xml.parsers`). Cấu hình bảo mật **trước khi tạo builder**:

1. Chọn implementation JAXP đáng tin cậy.
2. **Từ chối DOCTYPE**.
3. Bật `FEATURE_SECURE_PROCESSING`.
4. Đặt external DTD/schema access thành **chuỗi rỗng**.
5. Không bật XInclude.
6. Đặt giới hạn kích thước input cho hợp đồng API.
7. Dừng xử lý nếu một cài đặt bắt buộc không được hỗ trợ.

### 6.1. Chương trình đầy đủ: parse XML an toàn

```java
// File: SecureXmlDemo.java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.parsers.ParserConfigurationException;

import org.w3c.dom.Document;
import org.xml.sax.SAXException;

public final class SecureXmlDemo {
    private static final int MAX_XML_BYTES = 1_000_000;

    private SecureXmlDemo() {}

    static Document parseUntrustedXml(InputStream source)
            throws IOException, ParserConfigurationException, SAXException {

        // Giới hạn byte trước khi tạo DOM; caller vẫn sở hữu InputStream.
        byte[] xml = source.readNBytes(MAX_XML_BYTES + 1);
        if (xml.length > MAX_XML_BYTES) {
            throw new IOException("XML body exceeds limit");
        }

        DocumentBuilderFactory factory =
                DocumentBuilderFactory.newDefaultInstance();

        factory.setNamespaceAware(true);
        factory.setXIncludeAware(false);
        factory.setFeature(
            "http://apache.org/xml/features/disallow-doctype-decl", true);
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);

        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        // Không dùng setExpandEntityReferences(false) để thay thế chặn DTD.
        try (ByteArrayInputStream input = new ByteArrayInputStream(xml)) {
            return factory.newDocumentBuilder().parse(input);
        }
    }

    public static void main(String[] args) throws Exception {
        String allowed = "<order><id>27</id></order>";
        String withDtd =
                "<!DOCTYPE order [<!ENTITY label 'test'>]>"
                + "<order><id>&label;</id></order>";

        try (InputStream input = new ByteArrayInputStream(
                allowed.getBytes(StandardCharsets.UTF_8))) {

            Document document = parseUntrustedXml(input);
            System.out.println(
                document.getDocumentElement().getTagName()); // order
        }

        try (InputStream input = new ByteArrayInputStream(
                withDtd.getBytes(StandardCharsets.UTF_8))) {

            parseUntrustedXml(input);
            throw new AssertionError("DOCTYPE should have been rejected");
        } catch (SAXException rejected) {
            System.out.println("DOCTYPE rejected");
        }
    }
}
```

**Ý nghĩa bảo mật của ví dụ:**

- `newDefaultInstance()` sử dụng JAXP implementation mặc định được JDK cung cấp, thay vì để provider lookup tùy ý chọn một parser bên thứ ba. Nếu ứng dụng chủ đích dùng provider khác, cần kiểm tra tương thích và kiểm thử lại toàn bộ cài đặt.
- `disallow-doctype-decl` làm parser ném lỗi khi gặp DOCTYPE; ví dụ test bằng một DTD nội bộ vô hại.
- `FEATURE_SECURE_PROCESSING` bật các giới hạn xử lý thích hợp theo JAXP. Không coi nó là lớp bảo vệ **duy nhất**.
- `ACCESS_EXTERNAL_DTD = ""` và `ACCESS_EXTERNAL_SCHEMA = ""` chặn quyền truy cập tài nguyên ngoài thuộc các loại đó.
- `setXIncludeAware(false)` tránh tải tài nguyên qua XInclude.
- Giới hạn số byte giúp ngăn input quá lớn; còn cần giới hạn chiều sâu/độ phức tạp XML hoặc các giới hạn JAXP khi tiếp nhận đầu vào không tin cậy.
- Lỗi cấu hình (`ParserConfigurationException`, `IllegalArgumentException` từ provider khi đặt thuộc tính) **không bị nuốt**. Khi không đủ bảo vệ, không tiếp tục parse bằng một factory mặc định yếu hơn.

`InputStream` do **caller** cung cấp vẫn thuộc quyền sở hữu của caller; ví dụ gọi sử dụng try-with-resources. Việc chặn external entity **không hạn chế một URI/tệp nguồn mà ứng dụng đã tự chọn mở trước khi parse**. Vì vậy, cần kiểm soát nguồn XML ở tầng gọi, không chỉ cấu hình parser.

### 6.2. Vì sao chỉ setExpandEntityReferences(false) không đủ?

`factory.setExpandEntityReferences(false)` điều khiển cách entity references xuất hiện trong DOM. Nó **không phải** một hợp đồng tổng quát để từ chối external DTD, cấm kết nối mạng hoặc chống mọi dạng XXE.

Ưu tiên **cấm DOCTYPE**. Nếu quy định nghiệp vụ bắt buộc dùng DTD, cần một chính sách riêng về nguồn DTD đáng tin cậy, `EntityResolver`/catalog allowlist, external access restriction và các giới hạn entity expansion; không nên mặc định mở `file` hoặc `http` cho tất cả tài liệu.

## 7. Bảo vệ SAX, StAX, XSLT và Schema validation

Mỗi công cụ XML có những điểm kích hoạt tải tài nguyên khác nhau. Cài đặt an toàn cho DOM **không tự áp dụng** cho một `TransformerFactory` hoặc `XMLInputFactory` khác trong cùng ứng dụng.

### 7.1. SAX: từ chối DOCTYPE trước khi tạo XMLReader

```java
import java.io.InputStream;
import javax.xml.XMLConstants;
import javax.xml.parsers.SAXParserFactory;
import org.xml.sax.InputSource;
import org.xml.sax.XMLReader;
import org.xml.sax.helpers.DefaultHandler;

static void parseSax(InputStream untrusted)
        throws Exception {

    SAXParserFactory factory = SAXParserFactory.newDefaultInstance();
    factory.setNamespaceAware(true);
    factory.setFeature(
        "http://apache.org/xml/features/disallow-doctype-decl", true);
    factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);

    XMLReader reader = factory.newSAXParser().getXMLReader();
    reader.setContentHandler(new DefaultHandler());
    reader.parse(new InputSource(untrusted));
}
```

Đây là mảnh method đặt trong class; **caller chịu trách nhiệm đóng `untrusted`**. `newDefaultInstance()` chọn parser mặc định của JDK. Với provider khác, đặt thêm external entity/DTD restrictions phù hợp và fail closed khi không hỗ trợ.

### 7.2. StAX: tắt DTD và external entities

```java
import java.io.InputStream;
import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLStreamException;
import javax.xml.stream.XMLStreamReader;

static void parseStax(InputStream untrusted) throws XMLStreamException {
    XMLInputFactory factory = XMLInputFactory.newDefaultFactory();
    factory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
    factory.setProperty(
        XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);

    factory.setXMLResolver(
        (publicId, systemId, baseURI, namespace) -> {
            throw new XMLStreamException("External XML resource rejected");
        }
    );

    XMLStreamReader reader = factory.createXMLStreamReader(untrusted);
    try {
        while (reader.hasNext()) {
            reader.next();
        }
    } finally {
        reader.close();
    }
}
```

Ở StAX, tắt `SUPPORT_DTD` có thể khiến DTD bị **bỏ qua** chứ không nhất thiết ném lỗi chỉ vì DOCTYPE tồn tại. Nếu chính sách yêu cầu **từ chối tuyệt đối mọi DOCTYPE**, phải kiểm thử parser và bổ sung kiểm soát phù hợp, thay vì giả định StAX có cùng semantics với DOM `disallow-doctype-decl`.

`XMLStreamReader` có method `close()` nhưng **không được xem như một `AutoCloseable` chung trong ví dụ này**, nên dùng `finally`. Chú ý `reader.close()` không tự đảm bảo đóng input stream do caller truyền vào; caller cần quản lý `InputStream`.

### 7.3. XSLT: không tin stylesheet và document() bên ngoài

`TransformerFactory` có thể tải stylesheet thông qua `xsl:include`, `xsl:import` hoặc hàm `document()`, độc lập với DTD. Khi dùng stylesheet cố định do ứng dụng sở hữu:

```java
import javax.xml.XMLConstants;
import javax.xml.transform.TransformerFactory;

TransformerFactory factory = TransformerFactory.newDefaultInstance();
factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_STYLESHEET, "");
```

Sau đó mới biên dịch stylesheet tin cậy bằng `factory.newTransformer(...)`; **không nhận stylesheet từ người dùng rồi coi hai thuộc tính trên là sandbox thực thi XSLT**. Khi input XML của phép transform là không tin cậy, nên cung cấp một `SAXSource` dùng XMLReader đã khóa XXE hoặc cơ chế nhập tài liệu tương đương.

### 7.4. SchemaFactory và Validator

XSD có thể dùng `xs:import` và `xs:include` để nạp tài nguyên khác. Cần cấu hình cả tại **schema factory** lẫn nơi validate theo chính sách:

```java
import javax.xml.XMLConstants;
import javax.xml.validation.SchemaFactory;

SchemaFactory factory =
    SchemaFactory.newInstance(XMLConstants.W3C_XML_SCHEMA_NS_URI);

factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
factory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

// Tạo Schema bằng XSD đáng tin cậy do ứng dụng chọn.
// Nếu Validator cần cấu hình riêng, đặt external access và resolver
// của Validator trước khi validate.
```

Nếu schema cần dependencies hợp lệ, dùng **catalog hoặc resolver allowlist** ánh xạ identifier đến tài nguyên kiểm soát được, không đơn giản cho phép mọi URL `https://...`. Cho phép một **protocol** không tương đương cho phép một danh sách **host/resource** an toàn.

### 7.5. Kiểm soát chung bằng cấu hình JAXP

JDK cung cấp các thuộc tính cấu hình toàn cục, chẳng hạn `jdk.xml.dtd.support=deny` để từ chối DTD khi các loại parser/processor phù hợp. Đây là **defense in depth** hữu ích ở tầng runtime/JAXP config nhưng **không** thay thế cấu hình bảo mật cụ thể cho các parser do application tạo.

Khi có nhiều provider hoặc thư viện wrapper XML, cần kiểm tra liệu nó có **thay thế parser/reader/resolver** đã được cấu hình hay không. Bật một cờ “secure XML” ở một nơi **không bảo vệ** mọi thư viện XML khác trong ứng dụng.

## 8. Giải tuần tự dữ liệu không tin cậy: rủi ro nằm trước khi cast

`java.io.ObjectInputStream.readObject()` dựng lại một object graph từ định dạng **Java Serialization**. Quá trình này có thể gọi những hook theo serialization contract như `readObject`, `readResolve`, constructor của các superclass không Serializable và logic của một số class liên quan.

Xem ví dụ không an toàn:

```java
// KHÔNG DÙNG với bytes do client/đối tác bất kỳ cung cấp.
try (ObjectInputStream input =
        new ObjectInputStream(networkInputStream)) {

    UserMessage value = (UserMessage) input.readObject();
}
```

**Đặt cast sau `readObject()` không bảo vệ được quá trình dựng object.** Trước khi cast chạy, runtime đã phải đọc mô tả lớp, xử lý dữ liệu và có thể khởi tạo nhiều đối tượng.

Các rủi ro gồm:

- Khởi tạo lớp ngoài dự kiến, có thể liên quan đến **gadget chains** trên classpath.
- Nhiều đối tượng tham chiếu lẫn nhau, độ sâu, array hoặc chuỗi dữ liệu lớn gây cạn bộ nhớ/CPU.
- Logic được gọi trong quá trình deserialization có tác dụng phụ mà application chưa cho phép.
- Dữ liệu đầu vào tạo ra object graph khác với kiểu mà business code chờ đợi.
- Các giao thức cũ có thể thiếu ranh giới versioning, validation và quyền cập nhật object.

> **Khuyến nghị đầu tiên cho thiết kế mới:** không dùng `ObjectInputStream` hoặc `XMLDecoder` để nhận nội dung không tin cậy. Ưu tiên định dạng dữ liệu thuần với **schema rõ ràng**, chuyển thành DTO đã biết và kiểm tra input. JSON/CBOR/Protocol Buffers cũng vẫn cần giới hạn kích thước, độ sâu và tránh cơ chế tự tạo lớp tùy ý qua tên kiểu trong payload.

## 9. Thay Java native deserialization bằng dữ liệu có schema

Ví dụ một request ứng dụng chỉ cần ba trường:

```json
{
  "orderId": "O-27",
  "quantity": 2,
  "note": "gift"
}
```

Định nghĩa DTO với contract rõ ràng:

```java
record OrderInput(String orderId, int quantity, String note) {
    OrderInput {
        if (orderId == null || !orderId.matches("[A-Z]-[0-9]{1,12}")) {
            throw new IllegalArgumentException("Invalid order ID");
        }
        if (quantity < 1 || quantity > 100) {
            throw new IllegalArgumentException("Invalid quantity");
        }
        if (note != null && note.length() > 200) {
            throw new IllegalArgumentException("Note too long");
        }
    }
}
```

Ứng dụng cấu hình JSON library để ánh xạ **đúng DTO `OrderInput`**, giới hạn kích thước/depth, từ chối các kiểu/dữ liệu không mong muốn, rồi mới dùng object trong nghiệp vụ. Java SE **không cung cấp sẵn một API JSON binding tổng quát** tương đương `ObjectInputStream`; chọn thư viện và version được bảo trì, cấu hình theo tài liệu hiện hành.

Các nguyên tắc:

1. **Schema/DTO allowlist**: caller không được đưa một Java class name vào payload và ép runtime instantiate class đó.
2. **Không bật polymorphic default typing cho input không tin cậy** trừ khi có allowlist kiểu được kiểm soát chặt chẽ và cần thiết thực sự.
3. **Validation sau parse**: enum/range/length/required fields, authorization và consistency business.
4. **Giới hạn tài nguyên trước và trong parse**: kích thước message, độ sâu object, số phần tử collection, timeout.
5. **Không dựa vào tên định dạng**: “JSON” không tự động an toàn khi có auto-instantiation, reflection hoặc custom deserializer nguy hiểm.

## 10. Khi buộc phải đọc Java Serialization: ObjectInputFilter

Trong một hệ thống đang phụ thuộc vào Java native serialization, `java.io.ObjectInputFilter` có thể kiểm soát:

- Các lớp/kiểu array được phép hoặc bị từ chối khi deserializing.
- Độ sâu object graph (`maxdepth`).
- Số lượng tham chiếu (`maxrefs`).
- Chiều dài array (`maxarray`).
- Số byte stream đã đọc (`maxbytes`).

Theo JEP 290 và JEP 415, có cả **per-stream filters** và cấu hình **JVM-wide/context-specific filter factory**. Đây là **giảm thiểu rủi ro**, không phải bằng chứng native deserialization từ nguồn không tin cậy đã an toàn tuyệt đối.

### 10.1. Pattern filter: cú pháp và chính sách

```text
maxdepth=8;maxrefs=64;maxbytes=16384;maxarray=256;com.example.dto.*;!*
```

Ý nghĩa:

- Giới hạn độ sâu, references, input bytes và array length.
- Cho phép những class ở package `com.example.dto` theo pattern.
- `!*` từ chối những class khác nếu chúng được filter xét đến.

**Đây chỉ là minh họa cấu hình**, phải thay package bằng những class/kiểu thực sự cần của protocol. Một allowlist rộng cho mọi class “có vẻ thuộc ứng dụng” vẫn có thể cho phép gadget hoặc dữ liệu nguy hiểm nếu những class đó có deserialization hooks không an toàn.

**Đặc biệt:** không phải mọi giá trị primitive, String hoặc giá trị nested đều được gọi filter dưới dạng một lần kiểm tra class. Filter có giới hạn phạm vi và thời điểm áp dụng theo Javadoc. Cần kiểm soát kích thước dữ liệu **ngay tại tầng nhận bytes**, thay vì cho client gửi luồng vô hạn rồi trông vào filter.

### 10.2. Chương trình hoàn chỉnh: lọc kiểu cho một format nội bộ có sẵn

Ví dụ sau tạo một serialized record **nội bộ** bằng chính chương trình, rồi đọc lại bằng filter. Nó **không** khuyến nghị nhận stream tùy ý từ Internet.

```java
// File: FilteredObjectDemo.java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InvalidObjectException;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public final class FilteredObjectDemo {

    record Envelope(String id, long amount) implements Serializable {}

    private static final int MAX_BYTES = 16_384;

    static Envelope readInternalFormat(byte[] data)
            throws IOException, ClassNotFoundException {

        if (data == null || data.length > MAX_BYTES) {
            throw new IOException("Input size exceeds policy");
        }

        ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
            "maxdepth=6;maxrefs=40;maxbytes=16384;maxarray=256;"
            + "FilteredObjectDemo$Envelope;!*"
        );

        try (ObjectInputStream input = new ObjectInputStream(
                new ByteArrayInputStream(data))) {

            // Phải cấu hình TRƯỚC lần readObject() đầu tiên.
            input.setObjectInputFilter(filter);

            Object value = input.readObject();
            if (!(value instanceof Envelope result)) {
                throw new InvalidObjectException("Unexpected root type");
            }
            if (result.id() == null || result.id().length() > 80
                    || result.amount() < 0) {
                throw new InvalidObjectException("Invalid envelope data");
            }

            return result;
        }
    }

    public static void main(String[] args) throws Exception {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (ObjectOutputStream output = new ObjectOutputStream(bytes)) {
            output.writeObject(new Envelope("internal-27", 42));
        }

        Envelope restored = readInternalFormat(bytes.toByteArray());
        System.out.println(restored); // Envelope[id=internal-27, amount=42]
    }
}
```

**Các giới hạn của ví dụ:**

- Chỉ dùng cho **format nội bộ đã biết**, không phải endpoint tiếp nhận object stream công khai.
- Pattern cho phép **chính xác** nested record `FilteredObjectDemo$Envelope` và từ chối các class khác mà filter kiểm tra. Trên protocol thật, phải bao quát chính xác các class cần thiết và toàn bộ schema.
- Kiểm tra `data.length` trước khi xây `ObjectInputStream`. Với dữ liệu nhận qua mạng, giới hạn lượng byte được đọc từ socket/body **trước khi cấp phát `byte[]`**.
- `ObjectInputFilter` không tự kiểm tra tất cả giá trị `String`, nên phải kiểm tra giới hạn chiều dài và các điều kiện dữ liệu ở tầng nghiệp vụ.
- Nếu luồng đã mang cấu hình filter JVM-wide, **không tự giả định** gọi `setObjectInputFilter` sẽ kết hợp cả hai filter. Hành vi phụ thuộc **filter factory** được cài đặt; phải xem policy tổng thể.
- Cả một filter đúng cú pháp cũng **không phải sandbox** để thực thi các hook của class được allowlist. Không đưa class nguy hiểm vào allowlist.

### 10.3. Filter JVM-wide và filter factory

Có thể cấu hình filter khi **khởi động JVM**:

```text
-Djdk.serialFilter=maxdepth=8;maxrefs=64;maxarray=256;maxbytes=16384;!*
```

Dòng trên là **tham số JVM minh họa**, không phải lệnh shell hoàn chỉnh; khi chạy trong shell, chuỗi chứa dấu `;` phải được quote/escape theo quy tắc của shell. Pattern `!*` là deny-all đối với những class filter có thể kiểm tra, nên **không dùng nguyên xi cho hệ thống cần deserialize các class khác**.

Các điểm quản trị:

- `jdk.serialFilter` là property được đọc khi cấu hình filter khởi tạo; gọi `System.setProperty("jdk.serialFilter", ...)` sau khi runtime đã bắt đầu sử dụng serialization **không phải** cách đáng tin cậy để thay đổi global filter.
- `ObjectInputFilter.Config.setSerialFilter(...)` chỉ cài global filter khi chưa được cài; không dùng tùy tiện giữa lúc app đã phục vụ request.
- `jdk.serialFilterFactory` / `setSerialFilterFactory(...)` (JEP 415) cho phép điều khiển cách gán/gộp filter khi tạo `ObjectInputStream` hay đặt per-stream filter. Cần thiết kế sao cho filter mới **không vô hiệu hóa các ràng buộc toàn JVM** ngoài ý muốn.
- `ObjectInputFilter.Status.UNDECIDED` không tương đương `REJECTED`; khi cần chính sách allowlist chặt, phải xét đúng kết quả của filter và class chưa có quyết định. `ObjectInputFilter.rejectUndecidedClass(...)` hữu ích trong ngữ cảnh phù hợp.
- Không bật native deserialization cho dữ liệu Internet chỉ vì đã thêm một chuỗi pattern filter.

## 11. XMLDecoder và các dạng “deserialization” khác

`java.beans.XMLDecoder` dùng XML mô tả các bean/biểu thức để tạo object; dù đầu vào có tên XML, nó **không phải parser dữ liệu XML thông thường**. Không dùng `XMLDecoder` với dữ liệu không tin cậy. Việc khóa XXE ở parser XML **không** triệt tiêu rủi ro tạo object hoặc thực thi thao tác của XMLDecoder.

Tương tự, các thư viện binding dữ liệu có thể cho phép metadata chỉ định class/constructor hoặc thực hiện **custom deserializer**. Khi một API nhận JSON/XML/YAML từ người dùng, cần:

- Chỉ định kiểu đích ở application, không chấp nhận tên lớp tùy ý từ input.
- Kiểm soát subclass/polymorphism và extension points.
- Giới hạn độ sâu, kích thước mảng, số trường và tổng byte.
- Không dùng dữ liệu vừa parse làm câu lệnh SQL, template, đường dẫn hoặc shell command mà không qua ranh giới bảo vệ tương ứng.
- Áp dụng authorization sau khi đã xác định danh tính/tenant và đối tượng được phép xử lý.

**Deserialization an toàn** không chỉ là chọn format; quan trọng là **không cho dữ liệu đầu vào quyết định những đối tượng/capability nguy hiểm nào được tạo**.

## 12. Phòng thủ theo lớp và lỗi thường gặp

| Lỗi hoặc niềm tin sai | Vì sao không đúng | Hướng xử lý |
| --- | --- | --- |
| “Chặn chuỗi `../` là đủ” | Bỏ sót đường dẫn tuyệt đối, Windows separator, encoding, link | Chấp nhận ID/leaf name, giới hạn grammar và thao tác theo handle |
| “`normalize()` là sandbox” | Chỉ là phép lexical, không chặn symlink/race | Giới hạn quyền OS, kiểm tra real path và dùng `SecureDirectoryStream` khi threat model yêu cầu |
| “`startsWith` chuỗi bảo vệ root” | Prefix chuỗi có thể khớp tên thư mục khác | Dùng `Path.startsWith(Path)`, nhưng vẫn phải chống link/TOCTOU |
| “Đã `toRealPath()` nên mở tệp sau đó luôn an toàn” | File có thể bị đổi giữa check và open | Dùng directory-handle operations hoặc ranh giới lưu trữ không thể bị attacker sửa |
| “Chỉ cần xác thực người dùng là tải được mọi file” | Authentication khác authorization | Kiểm tra ownership/tenant/ACL với từng tài liệu |
| “Parser XML mặc định đã chắc chặn XXE” | Cấu hình phụ thuộc JAXP/provider và thao tác | Từ chối DOCTYPE, cấm external DTD/schema, giới hạn parse và fail closed |
| “`setExpandEntityReferences(false)` chặn XXE” | Chỉ điều khiển mô hình entity reference trong DOM | Chặn DTD/external access ngay tại factory |
| “DOM an toàn thì XSLT/Validator cũng an toàn” | Các factory khác có đường nạp tài nguyên riêng | Cấu hình cả `TransformerFactory`/`SchemaFactory`/`XMLInputFactory` |
| “Chặn HTTP trong XML là đủ” | `file`, `jar` hoặc resolver khác vẫn có thể truy cập | Dùng chuỗi rỗng cho external access, allowlist resource nghiêm ngặt khi bắt buộc |
| “Cứ parse XML rồi bắt Exception là đủ” | Parser có thể đã đọc tài nguyên ngoài trước khi lỗi | Cấu hình trước khi parse, chặn input quá lớn |
| “Cast sau `readObject()` sẽ ngăn class lạ” | Hook có thể đã chạy trong deserialization | Tránh native deserialization; nếu bất khả kháng dùng filter trước read |
| “Có `ObjectInputFilter` là deserialize dữ liệu Internet an toàn” | Filter có blind spots và allowlisted classes vẫn có side effects | Tránh Java native serialized input; dùng DTO/schema và giới hạn tầng đọc |
| “Pattern allowlist của package bất kỳ là an toàn” | Có thể cho phép class có hook nguy hiểm | Allowlist tối thiểu theo protocol, phân tích class graph |
| “Đã có global serialFilter nên per-stream filter luôn cộng thêm” | Built-in filter factory có thể **thay thế** theo ngữ cảnh | Đọc Javadoc và thiết kế factory/composition có chủ đích |
| “Chặn serialization có thể thay SecurityManager” | Hai cơ chế giải quyết threat model khác nhau; SecurityManager không còn là sandbox | Dùng OS isolation, least privilege và kiểm soát đầu vào |

## 13. Cách kiểm thử phòng thủ mà không dùng dữ liệu nhạy cảm

Sử dụng môi trường test riêng với tệp/XML giả. Không cần truy cập secret thật hoặc host nội bộ.

### 13.1. Test path traversal

Với một root test chỉ có dữ liệu giả, thử:

- Tên hợp lệ: `report-27.txt`.
- Path có parent: `../example.txt`.
- Path có separator: `subfolder/data.txt`, `subfolder\data.txt`.
- Absolute/drive path: `/tmp/example.txt`, `C:\test\example.txt` (tùy OS).
- Path sau URL decoding: kiểm thử tại **đúng tầng decode được framework sử dụng**.
- Symbolic link final entry chỉ sang một tệp giả bên ngoài root.
- Thư mục bị thay/rename giữa lúc code kiểm tra và mở, nếu hệ thống hỗ trợ test concurrency có kiểm soát.
- Trên provider không hỗ trợ `SecureDirectoryStream`, xác nhận API **từ chối** thay vì silently downgrade.

Kết quả kỳ vọng: input vi phạm không dẫn tới thao tác ngoài phạm vi; lỗi được trả về mà không tiết lộ đường dẫn máy chủ hoặc stack trace cho client. Test truy cập hợp lệ phải vẫn hoạt động trên provider được hỗ trợ.

### 13.2. Test XXE

Với parser DOM/SAX đã cấu hình, thử:

- XML hợp lệ không có DOCTYPE → parse thành công.
- XML có DOCTYPE/entity **nội bộ vô hại** → **bị từ chối** nếu chính sách là cấm toàn bộ DTD.
- XML quá dung lượng → bị từ chối trước khi tạo DOM.
- Schema/XSLT có external dependency chưa được allowlist → parser/transformer không tự truy cập tài nguyên đó.
- Khi cố tình dùng JAXP provider khác trong môi trường test, nếu thiếu feature/attribute bảo vệ bắt buộc, factory setup phải fail closed.

Không cần sử dụng payload truy xuất tệp thật hoặc URL hệ thống nội bộ để chứng minh việc từ chối DOCTYPE.

### 13.3. Test deserialization

Trong giao thức nội bộ đã kiểm soát:

- Byte stream đúng schema/đủ nhỏ → có thể đọc và validate.
- Đồ thị quá sâu, quá nhiều references, array quá dài → filter từ chối.
- Class nằm ngoài allowlist → filter từ chối.
- Root object sai loại → kiểm tra loại sau parse từ chối (không dùng nó làm bảo vệ chính).
- Field vi phạm rule (`null`, chuỗi quá dài, số âm) → business validation từ chối.
- Filter toàn JVM và per-stream hoạt động đồng thời đúng **policy composition**; không làm yếu filter chung.
- Input quá kích thước bị từ chối **trước khi** nạp vào bộ nhớ hoặc tạo `ObjectInputStream`.

Nếu hệ thống đã có phụ thuộc cần Java serialization, nên đánh giá kế hoạch **loại bỏ dữ liệu native serial từ biên không tin cậy**, thay vì mở rộng allowlist để sửa lỗi test.

## 14. Checklist bảo mật cho Java 27

1. **Xác định ranh giới tin cậy:** path, XML, serialized bytes đến từ đâu, ai có thể điều khiển?
2. **Giảm quyền dữ liệu:** client chỉ gửi resource ID/leaf name, không gửi đường dẫn filesystem tùy ý.
3. **Kiểm tra access control:** quyền đọc/ghi theo user và tenant, tách khỏi path validation.
4. **Dùng `Path` đúng cách:** tránh ghép chuỗi tùy tiện; hiểu `normalize`, `startsWith` và `toRealPath` là các lớp kiểm tra khác nhau.
5. **Kiểm soát symlink và TOCTOU:** dùng `SecureDirectoryStream`/OS-backed capability khi cần; nếu không hỗ trợ, fail closed hoặc thay kiến trúc lưu trữ.
6. **Không xem upload filename là tên lưu nội bộ:** tạo internal ID, giới hạn vị trí ghi và quyền filesystem.
7. **Khóa JAXP trước khi parse:** cấm DOCTYPE khi không cần; `FEATURE_SECURE_PROCESSING`; external access rỗng.
8. **Cấu hình mọi chỗ dùng XML:** DOM, SAX, StAX, XSLT, XSD/Validator và wrapper libraries.
9. **Giới hạn XML resource use:** byte size, depth/complexity, time/cost theo threat model; fail closed nếu không hỗ trợ setting.
10. **Tránh Java ObjectInputStream ở ranh giới Internet:** dùng DTO có schema và giới hạn input.
11. **Nếu buộc dùng native serialization:** `ObjectInputFilter` tối thiểu, giới hạn số byte/depth/ref/array, kiểm soát filter factory và validate fields.
12. **Không dùng `XMLDecoder` với untrusted XML:** đây là bề mặt tạo object khác với parse dữ liệu thông thường.
13. **Không dựa vào SecurityManager:** thiết kế least privilege, sandbox hệ điều hành/container và network egress policies.
14. **Đóng tài nguyên:** directory streams, channels, input streams và XML readers được giải phóng theo vòng đời rõ.
15. **Kiểm thử các trường hợp biên:** link swap, path encoding, provider không hỗ trợ feature, DTD, array/graph quá lớn.
16. **Theo dõi vận hành:** log lý do từ chối có redaction; không lộ secret, path nhạy cảm hoặc nội dung payload đầy đủ.

## Tài liệu tham khảo chính thức và hướng dẫn phòng thủ

- [`Path` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/Path.html) — `resolve`, `normalize`, `startsWith` và `toRealPath`.
- [`Files` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/Files.html) — mở tệp, đọc nội dung, directory streams và xử lý symbolic link.
- [`SecureDirectoryStream` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/SecureDirectoryStream.html) — thao tác tương đối với directory handle, `newByteChannel` và `NOFOLLOW_LINKS`.
- [`DocumentBuilderFactory` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.xml/javax/xml/parsers/DocumentBuilderFactory.html) — cấu hình DOM parser và `setFeature`/`setAttribute`.
- [`XMLConstants` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.xml/javax/xml/XMLConstants.html) — `FEATURE_SECURE_PROCESSING` và external access restrictions.
- [`XMLInputFactory` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.xml/javax/xml/stream/XMLInputFactory.html) — vô hiệu hóa DTD và external entity resolution trong StAX.
- [`TransformerFactory` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.xml/javax/xml/transform/TransformerFactory.html) — kiểm soát external stylesheet và DTD của XSLT.
- [`SchemaFactory` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.xml/javax/xml/validation/SchemaFactory.html) — giới hạn truy cập DTD/schema khi validate XML.
- [`ObjectInputFilter` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/io/ObjectInputFilter.html) — class filtering, resource limits và filter composition.
- [`ObjectInputFilter.Config` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/io/ObjectInputFilter.Config.html) — per-stream/JVM-wide filter, pattern syntax và filter factory.
- [OWASP XML External Entity Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html) — các cấu hình chống XXE cho JAXP và thư viện bao.
- [OWASP Path Traversal](https://owasp.org/www-community/attacks/Path_Traversal) — threat model của đường dẫn không tin cậy.
- [OWASP Deserialization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Deserialization_Cheat_Sheet.html) — tránh deserialization không tin cậy và phòng thủ theo lớp.
- [Oracle JAXP Security Guide](https://docs.oracle.com/en/java/javase/26/security/java-api-xml-processing-jaxp-security-guide.html) — cấu hình DTD, JAXP limits, external access và catalog (hướng dẫn vẫn áp dụng).
- [JEP 290 — Filter Incoming Serialization Data](https://openjdk.org/jeps/290) — serial filters.
- [JEP 415 — Context-Specific Deserialization Filters](https://openjdk.org/jeps/415) — filter factory tùy ngữ cảnh.
- [JEP 486 — Permanently Disable the Security Manager](https://openjdk.org/jeps/486) — xác nhận SecurityManager không còn là cơ chế sandbox cho Java hiện hành.
