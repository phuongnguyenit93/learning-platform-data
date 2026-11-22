# Kiểm tra virus và loại tệp trước khi gửi trong Spring Framework Mail

Khi gửi email có tệp đính kèm, ứng dụng không nên chuyển thẳng mọi file nhận được sang `MimeMessageHelper.addAttachment(...)`. Một file có thể mang phần mở rộng giả, khai báo MIME type không đúng, chứa mã độc, khai thác lỗi của phần mềm đọc tài liệu hoặc có kích thước khiến hệ thống cạn bộ nhớ. Với email giao dịch, hóa đơn, hồ sơ hoặc tài liệu do người dùng tải lên, **kiểm tra loại tệp và quét malware trước khi gửi** là một phần của quy trình xử lý attachment.

Một luồng an toàn thường gồm:

1. Nhận tệp và áp dụng giới hạn kích thước.
2. Chuẩn hóa tên hiển thị; không dùng tên file làm đường dẫn lưu trữ.
3. Kiểm tra phần mở rộng theo allowlist của nghiệp vụ.
4. Phát hiện định dạng thực từ nội dung file (signature/content detection).
5. Kiểm tra cấu trúc, kích thước giải nén và các đặc điểm rủi ro nếu định dạng yêu cầu.
6. Đưa dữ liệu vào vùng quarantine hoặc vùng chờ quét.
7. Gửi nội dung qua dịch vụ antivirus/malware scanner.
8. Chỉ khi kết quả là **CLEAN** và chính sách cho phép mới tạo email chứa file đó.
9. Lưu trạng thái, hash và thông tin vận hành cần thiết; xóa dữ liệu tạm theo chính sách retention.

**Spring Mail không tự quét virus hoặc xác thực nội dung attachment.** `MimeMessageHelper` chỉ giúp đóng gói file vào MIME message. Ứng dụng phải thực hiện các kiểm soát trước khi gọi `addAttachment(...)` và `JavaMailSender.send(...)`.

## 1. Vì sao phải kiểm tra tệp trước khi gửi email?

Tệp đính kèm là dữ liệu có thể được mở bởi người nhận hoặc hệ thống tự động phía sau mailbox. Nếu ứng dụng chuyển tiếp một file độc hại, nó có thể trở thành phương tiện phát tán malware, lừa đảo hoặc khai thác lỗ hổng.

Các rủi ro phổ biến:

- **Giả mạo định dạng:** file thực chất là chương trình hoặc script nhưng được đổi tên thành `.pdf` hoặc `.jpg`.
- **Mã độc trong tài liệu:** Office macro, script nhúng, PDF có nội dung chủ động hoặc payload độc hại.
- **Archive bomb:** file ZIP nhỏ nhưng giải nén ra dữ liệu khổng lồ, nhiều lớp hoặc số lượng file quá lớn.
- **File gây cạn tài nguyên:** ảnh có kích thước pixel rất lớn, tài liệu phức tạp hoặc file nén làm CPU/RAM tăng cao khi phân tích.
- **Path traversal:** tên file chứa đường dẫn như `../../...` làm ứng dụng lưu file sai vị trí nếu dùng trực tiếp.
- **Nội dung không phù hợp:** file ngoài loại nghiệp vụ cho phép, ví dụ một form chỉ nhận PDF nhưng lại gửi file HTML hoặc executable.
- **Rò rỉ thông tin:** attachment chứa dữ liệu cá nhân, thông tin nội bộ hoặc tài liệu của người khác.
- **Lỗi phần mềm đọc file:** tài liệu được tạo đặc biệt để khai thác lỗ hổng trong trình đọc PDF, Office hoặc công cụ preview.

Việc gửi email còn làm tăng phạm vi phát tán: file có thể được chuyển tiếp, lưu trữ trên máy chủ email, đồng bộ xuống thiết bị hoặc được hệ thống DLP/antispam xử lý. Vì vậy, kiểm tra ở thời điểm upload và trước lúc gửi đều có vai trò.

### Các lớp bảo vệ bổ sung cho nhau

| Kiểm soát | Câu hỏi được trả lời | Giới hạn |
| --- | --- | --- |
| Allowlist phần mở rộng | Nghiệp vụ có cho phép loại tên file này không? | Tên file có thể bị giả |
| MIME type detection | Nội dung có giống định dạng được khai báo không? | MIME/signature không chứng minh file sạch |
| File signature / magic bytes | Header nhị phân có phù hợp định dạng không? | Một số định dạng phức tạp hoặc polyglot khó phân loại |
| Parser/structural validation | File có cấu trúc hợp lệ theo định dạng không? | File hợp lệ vẫn có thể chứa mã độc |
| Antivirus/malware scan | Engine có phát hiện mẫu độc đã biết hoặc hành vi đáng ngờ không? | Không bảo đảm phát hiện mọi mã độc mới |
| Quarantine và access control | File chưa được duyệt có bị ngăn sử dụng không? | Cần bảo vệ cả storage và luồng đọc |
| Giới hạn kích thước/tài nguyên | Có tránh được file quá lớn hoặc archive bomb không? | Phải áp dụng ở nhiều lớp |

Không một kiểm tra đơn lẻ nào đủ để tuyên bố file an toàn. **Allowlist + content detection + malware scan + resource limits + quarantine** tạo thành nhiều lớp phòng vệ.

## 2. Xác định loại tệp bằng allowlist

Đối với một nghiệp vụ cụ thể, nên xác định **những loại file thực sự cần thiết**. Ví dụ, chức năng gửi hóa đơn có thể chỉ nhận PDF; chức năng gửi ảnh sản phẩm có thể chỉ nhận PNG và JPEG.

Ví dụ allowlist:

| Phần mở rộng | MIME type dự kiến | Trường hợp sử dụng |
| --- | --- | --- |
| `.pdf` | `application/pdf` | Hóa đơn, hợp đồng hoặc báo cáo |
| `.png` | `image/png` | Ảnh raster |
| `.jpg`, `.jpeg` | `image/jpeg` | Ảnh raster |

Đây chỉ là ví dụ. Hãy chọn loại tệp theo nhu cầu thật, không bật hàng loạt định dạng chỉ vì thư viện có thể đọc chúng. Nếu không cần gửi `.exe`, `.js`, `.html`, `.svg`, macro-enabled Office hoặc archive, không nên đưa chúng vào allowlist.

### Allowlist tốt hơn blocklist

Blocklist cố liệt kê những phần mở rộng bị cấm:

~~~text
.exe, .bat, .cmd, .js, .vbs, ...
~~~

Danh sách này khó đầy đủ vì có nhiều loại script, định dạng lồng nhau, tên kép và cách đánh lừa khác nhau. Allowlist đặt câu hỏi ngược lại: **nghiệp vụ chỉ chấp nhận những định dạng nào?**

Ví dụ:

~~~java
private static final Map<String, String> ALLOWED_TYPES = Map.of(
        ".pdf", "application/pdf",
        ".png", "image/png",
        ".jpg", "image/jpeg",
        ".jpeg", "image/jpeg");
~~~

Nếu chức năng chỉ gửi PDF, allowlist nên chỉ có `.pdf`. Ít định dạng được phép đồng nghĩa với ít parser, ít hành vi đặc biệt và ít bề mặt tấn công hơn.

### Không tin phần mở rộng do người dùng cung cấp

Các tên sau đều có thể gây nhầm lẫn:

~~~text
invoice.pdf.exe
invoice.exe.pdf
photo.jpg.html
report.PDF
archive.zip.pdf
document.pdf.
~~~

Ứng dụng nên:

- Chuẩn hóa phần mở rộng bằng `Locale.ROOT` để xử lý chữ hoa/thường nhất quán.
- Chỉ xét phần mở rộng cuối cùng theo chính sách; tên nhiều phần mở rộng cần được kiểm soát rõ.
- Loại bỏ hoặc từ chối ký tự điều khiển, separator và tên rỗng.
- Không coi tên `.pdf` là bằng chứng nội dung là PDF.
- Không tự đổi đuôi file để biến định dạng không được phép thành định dạng được phép.

Một số hệ thống có thể từ chối tên có nhiều dấu chấm hoặc tên đáng ngờ thay vì cố suy đoán ý định. Quy tắc cần phù hợp với nghiệp vụ và được áp dụng nhất quán.

## 3. MIME type do client khai báo không đáng tin cậy

Khi upload qua HTTP, trình duyệt hoặc client thường gửi:

~~~http
Content-Disposition: form-data; name="file"; filename="invoice.pdf"
Content-Type: application/pdf
~~~

Giá trị `Content-Type` ở request là **metadata do phía gửi cung cấp**. Client có thể đặt nó thành bất kỳ chuỗi nào, kể cả khi nội dung thực không phải PDF. Không được dùng riêng `MultipartFile.getContentType()` để quyết định file có được gửi hay không.

Ví dụ file thực tế là HTML/script nhưng client khai báo:

~~~text
filename: invoice.pdf
Content-Type: application/pdf
body: nội dung khác định dạng PDF
~~~

Nếu ứng dụng chỉ kiểm tra hai trường đầu, file giả có thể đi qua.

### Phân biệt ba khái niệm

| Giá trị | Nguồn | Độ tin cậy |
| --- | --- | --- |
| Original filename | Request header / multipart | Không tin cậy; chỉ dùng như gợi ý sau khi chuẩn hóa |
| Declared Content-Type | Request header | Không tin cậy; có thể lưu để chẩn đoán |
| Detected media type | Phân tích nội dung bằng detector | Tốt hơn để phân loại, nhưng không chứng minh an toàn |

**MIME detection không phải antivirus.** Một file có thể đúng định dạng PDF và vẫn chứa payload độc hại. Một file PNG có signature đúng vẫn có thể khai thác lỗi parser hoặc chứa dữ liệu bất thường.

## 4. Kiểm tra chữ ký file (magic bytes)

Nhiều định dạng file có một số byte đặc trưng ở đầu hoặc các vị trí nhất định. Chúng thường được gọi là **file signature** hoặc **magic bytes**. Ví dụ minh họa:

| Định dạng | Signature thường gặp ở đầu file (hex) |
| --- | --- |
| PDF | `25 50 44 46` (`%PDF`) |
| PNG | `89 50 4E 47 0D 0A 1A 0A` |
| JPEG | `FF D8 FF` |
| ZIP | `50 4B 03 04` (một dạng ZIP phổ biến) |

Các byte này giúp nhận biết định dạng sơ bộ. Không nên triển khai một danh sách magic bytes đơn giản rồi coi đó là parser hoàn chỉnh. Một số định dạng có nhiều biến thể, header nằm ở vị trí khác, hoặc dùng container chung.

### Vì sao ZIP cần được xử lý riêng?

DOCX, XLSX và PPTX là các gói Office Open XML được lưu trong container ZIP. Nếu chỉ thấy signature ZIP, detector có thể nhận dạng là `application/zip` thay vì loại tài liệu Office cụ thể. Cần parser có khả năng nhận dạng cấu trúc container nếu nghiệp vụ cho phép Office.

ZIP cũng có thể chứa:

- Nhiều file con với tên và đường dẫn riêng.
- File lồng nhau hoặc archive lồng nhiều tầng.
- Tên entry có đường dẫn traversal.
- File mã hóa bằng password khiến scanner không đọc được nội dung.
- Số lượng entry hoặc kích thước giải nén quá lớn.

Nếu không cần archive, từ chối ZIP/RAR/7z sẽ đơn giản hơn. Nếu phải nhận, cần chính sách kiểm tra archive chuyên biệt, giới hạn tổng kích thước sau giải nén, số lượng entry, độ sâu lồng nhau và thời gian xử lý.

### Dùng Apache Tika để phát hiện media type

Apache Tika có thể phân tích nội dung để phát hiện định dạng. Ví dụ minh họa với dữ liệu đã được giới hạn kích thước:

~~~java
import org.apache.tika.Tika;

Tika tika = new Tika();
String detectedType = tika.detect(fileBytes);
~~~

Kết quả có thể là `application/pdf`, `image/png`, `image/jpeg` hoặc một loại tổng quát tùy dữ liệu và detector. Cần chọn phiên bản Tika phù hợp với dự án và hiểu các loại kết quả mà detector trả về. Với định dạng container phức tạp, có thể cần parser và metadata analysis bổ sung.

Một quy tắc chấp nhận có thể yêu cầu đồng thời:

1. Phần mở rộng nằm trong allowlist.
2. Media type phát hiện được nằm trong allowlist.
3. Extension và detected type tương ứng với nhau.
4. Cấu trúc file qua được parser/validation phù hợp.
5. Malware scanner trả kết quả sạch.

Nếu declared MIME type khác detected type, không tự động tin declared type. Tùy chính sách, có thể từ chối file, yêu cầu upload lại hoặc ghi nhận mismatch để điều tra. Không nên tự đổi MIME type rồi gửi file không rõ định dạng.

## 5. Kiểm tra tên file và metadata

Tên file thường xuất hiện trong header MIME của email và giao diện người nhận. Không nên dùng nguyên giá trị `MultipartFile.getOriginalFilename()` làm đường dẫn lưu file hoặc đưa trực tiếp vào mọi header.

### Rủi ro path traversal

Ví dụ tên file:

~~~text
../../../../etc/passwd
......Windowswin.ini
/var/app/secrets.txt
~~~

Nếu ứng dụng nối tên này vào thư mục lưu trữ, file có thể ghi ra ngoài vùng dự kiến. Dù mục tiêu chỉ là đính kèm email, việc lưu tạm để quét vẫn có nguy cơ nếu dùng tên người dùng cung cấp làm path.

Nguyên tắc:

- Sinh storage key ngẫu nhiên hoặc từ ID nội bộ.
- Không dùng original filename làm tên file vật lý.
- Chỉ giữ một tên hiển thị đã chuẩn hóa và giới hạn độ dài.
- Loại bỏ slash, backslash, ký tự điều khiển, CR/LF và ký tự không phù hợp với header.
- Không đưa tên file không tin cậy vào log nếu có thể chứa dữ liệu nhạy cảm hoặc ký tự điều khiển.

Ví dụ lấy tên hiển thị đã loại bỏ đường dẫn:

~~~java
static String safeDisplayFilename(String originalName) {
    if (originalName == null || originalName.isBlank()) {
        throw new IllegalArgumentException("Filename is required");
    }

    String normalized = originalName.replace('\\', '/');
    int lastSeparator = normalized.lastIndexOf('/');
    String basename = normalized.substring(lastSeparator + 1).trim();

    if (basename.isBlank()
            || basename.equals(".")
            || basename.equals("..")
            || basename.codePoints().anyMatch(Character::isISOControl)) {
        throw new IllegalArgumentException("Invalid filename");
    }

    if (basename.length() > 120) {
        throw new IllegalArgumentException("Filename is too long");
    }

    return basename;
}
~~~

Đây là bước chuẩn hóa hiển thị cơ bản, không phải bộ kiểm tra toàn diện Unicode. Với hệ thống đa nền tảng, cần thống nhất Unicode normalization, ký tự tương tự, dấu chấm/khoảng trắng cuối tên và quy tắc tên riêng của từng filesystem. Tên lưu trữ vẫn nên là ID do ứng dụng tạo.

### Không để CR/LF đi vào header

Filename có thể được đưa vào MIME Content-Disposition. Ký tự xuống dòng không được kiểm soát có thể làm header không hợp lệ hoặc gây header injection nếu thư viện xử lý không đúng. Dùng API của Spring/Jakarta Mail và tên hiển thị đã chuẩn hóa; không tự ghép raw header string.

### Hash để nhận diện chính xác nội dung

Có thể tính SHA-256 của byte stream để nhận diện file:

~~~java
import java.security.MessageDigest;
import java.util.HexFormat;

static String sha256(byte[] bytes) throws Exception {
    byte[] digest = MessageDigest.getInstance("SHA-256").digest(bytes);
    return HexFormat.of().formatHex(digest);
}
~~~

Hash không cho biết file sạch hay độc. Nó giúp gắn kết quả scan với **đúng phiên bản nội dung**, phát hiện dữ liệu thay đổi và hỗ trợ audit mà không cần log toàn bộ file. Nếu nội dung thay đổi một byte sau khi quét, hash cũng thay đổi và kết quả scan cũ không còn áp dụng.

## 6. Giới hạn kích thước trước khi đọc toàn bộ file

Không nên gọi `MultipartFile.getBytes()` cho mọi upload mà không giới hạn. File lớn có thể chiếm nhiều heap, gây GC pressure hoặc làm ứng dụng hết bộ nhớ. Cần giới hạn ở nhiều lớp:

- Reverse proxy / API gateway.
- Cấu hình multipart của Spring Boot và servlet container.
- Controller/service validation.
- Storage/quarantine quota.
- Antivirus scanner và parser.
- Tổng dung lượng tất cả attachment trong một email.
- Giới hạn của SMTP provider và mailbox nhận.

Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  servlet:
    multipart:
      max-file-size: 10MB
      max-request-size: 15MB
~~~

Đây là ví dụ minh họa cho giới hạn upload; giá trị thực phải theo nghiệp vụ, hạ tầng và giới hạn email. `max-request-size` cần đủ lớn cho multipart overhead và các trường khác, nhưng không nên quá rộng.

### Email có thể lớn hơn file gốc

Attachment thường được mã hóa Base64 trong MIME. Base64 làm dữ liệu tăng khoảng một phần ba, chưa kể header, boundary và các phần nội dung khác. Vì vậy, file PDF 10 MB không có nghĩa email cuối cùng đúng 10 MB.

Nếu SMTP provider giới hạn kích thước thư, cần để khoảng trống phù hợp. Nhiều attachment nhỏ cũng có thể cộng lại thành một email quá lớn.

### Archive bomb và decompression limits

Một ZIP có thể nhỏ khi truyền nhưng giải nén thành hàng gigabyte hoặc hàng triệu file. Nếu scanner/parser tự giải nén mà không có giới hạn, nó có thể bị DoS.

Khi cho phép archive, giới hạn:

| Giới hạn | Mục đích |
| --- | --- |
| Kích thước archive nén | Giới hạn dữ liệu upload |
| Tổng kích thước giải nén | Chống decompression bomb |
| Số lượng entry | Chống archive có quá nhiều file nhỏ |
| Độ sâu archive lồng nhau | Giới hạn recursion |
| Tỷ lệ nén tối đa | Phát hiện dữ liệu nén bất thường |
| Thời gian CPU/scan | Ngăn xử lý kéo dài vô hạn |
| Tên entry và đường dẫn | Chống path traversal trong archive |

Nếu scanner không hỗ trợ archive mã hóa hoặc file lồng nhau, cần từ chối hoặc chuyển sang xử lý riêng; **không coi việc scanner bỏ qua nội dung không đọc được là CLEAN**.

## 7. Quét virus/malware bằng dịch vụ chuyên dụng

Ứng dụng Spring thường không tự viết antivirus engine. Thay vào đó, nó tích hợp với một dịch vụ scanner được vận hành riêng, chẳng hạn:

- ClamAV daemon hoặc dịch vụ tương thích giao thức scanner.
- ICAP antivirus gateway.
- Dịch vụ malware scanning của nền tảng/cloud.
- Sản phẩm endpoint/content security được tổ chức quản lý.

Kiến trúc tổng quát:

~~~mermaid
flowchart LR
    A["Upload attachment"] --> B["Validate size + type"]
    B --> C["Quarantine storage"]
    C --> D["Malware scanner"]
    D --> E{"Scan result"}
    E -- "CLEAN" --> F["Approved attachment"]
    E -- "INFECTED" --> G["Reject / quarantine"]
    E -- "ERROR / UNKNOWN" --> H["Hold / retry / alert"]
    F --> I["MimeMessageHelper.addAttachment"]
    I --> J["JavaMailSender.send"]
~~~

Scanner có thể phân tích byte stream hoặc file được cung cấp qua một giao thức riêng. Ứng dụng cần adapter để chuyển dữ liệu đến scanner và chuẩn hóa kết quả về một mô hình nội bộ.

### Interface scanner trong ứng dụng

~~~java
import java.io.IOException;
import java.io.InputStream;

public interface MalwareScanner {

    ScanResult scan(InputStream content) throws IOException;
}

public record ScanResult(
        ScanStatus status,
        String engine,
        String signatureVersion,
        String detectionName
) {
}

public enum ScanStatus {
    CLEAN,
    INFECTED,
    ERROR,
    UNKNOWN
}
~~~

Interface này tạo ranh giới giữa code nghiệp vụ và nhà cung cấp scanner. Adapter thực tế sẽ gọi ClamAV, ICAP hoặc API của dịch vụ bảo mật; cách xác thực, timeout, giao thức, giới hạn kích thước và mã lỗi phụ thuộc sản phẩm được chọn.

**Không tự giả lập kết quả CLEAN khi scanner không kết nối được.** Nếu scanner timeout, unavailable, trả response không hiểu được hoặc không quét được file mã hóa, kết quả phải là ERROR/UNKNOWN hoặc trạng thái chờ xử lý theo chính sách.

### Quy tắc quyết định

| Kết quả scanner | Quyết định thông thường |
| --- | --- |
| CLEAN | Có thể chuyển sang bước phê duyệt tiếp theo |
| INFECTED | Cách ly/từ chối; không đính kèm |
| ERROR | Giữ ở trạng thái chờ hoặc từ chối; không gửi như file sạch |
| UNKNOWN | Cách ly hoặc yêu cầu xử lý thủ công |

Với tài liệu do người dùng tải lên rồi hệ thống gửi ra ngoài, cách tiếp cận an toàn phổ biến là **fail closed**: nếu không xác định được file sạch, không gửi file đó. Một số nghiệp vụ có thể chọn không gửi attachment và gửi thông báo thay thế, nhưng quyết định phải được định nghĩa trước.

## 8. Quarantine và trạng thái scan

Không nên đặt file mới upload vào vùng mà sender có thể đọc ngay. Tách vùng dữ liệu:

~~~text
upload/
  -> QUARANTINED
       |
       +--> SCANNING
              |
              +--> CLEAN ------> APPROVED
              |
              +--> INFECTED ---> REJECTED / ISOLATED
              |
              +--> ERROR ------> SCAN_PENDING / MANUAL_REVIEW
~~~

Ý nghĩa trạng thái:

| Trạng thái | Ý nghĩa | Có được gửi? |
| --- | --- | --- |
| QUARANTINED | File mới nhận, chưa quét | Không |
| SCANNING | Đang được scanner xử lý | Không |
| CLEAN / APPROVED | Scanner trả sạch và các kiểm tra khác đã đạt | Có thể, nếu chính sách nghiệp vụ cho phép |
| INFECTED / REJECTED | Có phát hiện hoặc bị chính sách từ chối | Không |
| ERROR / UNKNOWN | Không có kết quả đáng tin cậy | Không |
| EXPIRED | Quá thời gian lưu giữ hoặc job hết hạn | Không |

### Vì sao cần quarantine?

Quarantine giúp ngăn một file chưa được kiểm tra bị sử dụng do lỗi thứ tự xử lý. Ví dụ, upload endpoint lưu file rồi phát sự kiện gửi email ngay lập tức trong khi antivirus scan chạy bất đồng bộ. Nếu sender không kiểm tra trạng thái, email có thể rời hệ thống trước khi scanner trả kết quả.

Chỉ có một service hoặc role được phép đọc file đã phê duyệt. Tài khoản của sender không nên đọc được vùng quarantine trực tiếp. Khi file được xác nhận sạch, hệ thống có thể đánh dấu trạng thái và cấp quyền đọc qua một API/storage location riêng.

### Kết quả scan phải gắn với đúng nội dung

Không nên chỉ lưu:

~~~text
fileId = 123
scanStatus = CLEAN
~~~

nếu nội dung file có thể bị thay thế sau khi quét. Kết quả cần liên kết với:

- File ID hoặc object key.
- SHA-256 của nội dung đã quét.
- Kích thước và detected media type.
- Scanner engine và phiên bản signature/database.
- Thời điểm scan.
- Kết quả và detection name (nếu có).
- Phiên bản object hoặc storage generation nếu dùng object storage.

Trước khi gửi, bảo đảm byte stream được gửi có **cùng hash/version** với nội dung đã quét. Đây là cách giảm rủi ro TOCTOU (time-of-check to time-of-use): file bị thay đổi sau khi scan nhưng trước khi attach.

## 9. Ví dụ pipeline kiểm tra và quét trong Java

Ví dụ sau dùng byte array để dễ hiểu, phù hợp với **file nhỏ đã bị giới hạn kích thước**. Với file lớn, không nên tải toàn bộ vào heap; phần sau trình bày cách dùng quarantine storage và stream có thể mở lại.

### Mô hình attachment đã được duyệt

~~~java
public record ApprovedAttachment(
        String filename,
        String contentType,
        byte[] content,
        String sha256
) {
}
~~~

Không nên tạo object này trực tiếp từ request. Chỉ service validation/scanning được phép tạo nó sau khi các kiểm tra đạt yêu cầu.

### Service validate và scan

~~~java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.util.Locale;
import java.util.Map;

import org.apache.tika.Tika;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

@Service
public class AttachmentInspectionService {

    private static final long MAX_BYTES = 10L * 1024 * 1024;

    private static final Map<String, String> ALLOWED_TYPES = Map.of(
            ".pdf", "application/pdf",
            ".png", "image/png",
            ".jpg", "image/jpeg",
            ".jpeg", "image/jpeg");

    private final Tika tika = new Tika();
    private final MalwareScanner malwareScanner;

    public AttachmentInspectionService(MalwareScanner malwareScanner) {
        this.malwareScanner = malwareScanner;
    }

    public ApprovedAttachment inspect(MultipartFile upload)
            throws IOException {
        if (upload == null || upload.isEmpty()) {
            throw new IllegalArgumentException("Attachment is empty");
        }

        if (upload.getSize() > MAX_BYTES) {
            throw new IllegalArgumentException("Attachment is too large");
        }

        String filename = safeDisplayFilename(
                upload.getOriginalFilename());
        String extension = extensionOf(filename);
        String expectedType = ALLOWED_TYPES.get(extension);

        if (expectedType == null) {
            throw new IllegalArgumentException(
                    "File extension is not allowed");
        }

        // Chỉ dùng getBytes() vì ví dụ đã giới hạn kích thước ở 10 MiB.
        byte[] bytes = upload.getBytes();
        if (bytes.length == 0 || bytes.length > MAX_BYTES) {
            throw new IllegalArgumentException("Invalid file size");
        }

        String detectedType = tika.detect(bytes);
        if (!expectedType.equals(detectedType)) {
            throw new IllegalArgumentException(
                    "File content does not match the allowed type");
        }

        ScanResult scan;
        try (ByteArrayInputStream input = new ByteArrayInputStream(bytes)) {
            scan = malwareScanner.scan(input);
        }

        if (scan == null || scan.status() != ScanStatus.CLEAN) {
            throw new IllegalStateException(
                    "Attachment has not passed malware scanning");
        }

        return new ApprovedAttachment(
                filename,
                detectedType,
                bytes,
                sha256(bytes));
    }

    private static String extensionOf(String filename) {
        int dot = filename.lastIndexOf('.');
        if (dot <= 0) {
            return "";
        }
        return filename.substring(dot).toLowerCase(Locale.ROOT);
    }
}
~~~

Các helper `safeDisplayFilename(...)` và `sha256(...)` được mô tả ở phần trước; cần đưa chúng vào class tiện ích hoặc service phù hợp. Code này là ví dụ tích hợp, không phải một antivirus adapter hoàn chỉnh.

Những điểm cần hiểu:

1. Kích thước được giới hạn trước khi đọc byte array.
2. Extension được so với allowlist.
3. Tika phát hiện media type từ nội dung.
4. Extension và detected type phải khớp theo map nghiệp vụ.
5. Scanner nhận chính byte array được giữ lại.
6. Chỉ kết quả CLEAN mới tạo `ApprovedAttachment`.
7. Khi gửi, dùng đúng byte array đã scan; không đọc lại một file có thể đã thay đổi.

Trong hệ thống thực, cần xử lý exception của scanner thành trạng thái ERROR có phân loại, không biến nó thành CLEAN. Cũng cần kiểm tra loại file bằng parser phù hợp nếu định dạng yêu cầu, vì media detection chỉ nhận diện định dạng sơ bộ.

### Declared Content-Type xử lý thế nào?

Code mẫu không dùng `upload.getContentType()` làm căn cứ cho phép. Có thể lưu giá trị đó để audit hoặc ghi nhận mismatch:

~~~java
String clientDeclaredType = upload.getContentType();
String detectedType = tika.detect(bytes);
~~~

Nếu client khai báo `application/pdf` nhưng detector nhận `image/png`, policy có thể từ chối upload. Nếu client gửi `application/octet-stream` nhưng nội dung thực là PDF hợp lệ, policy có thể chấp nhận theo detected type. Điều quan trọng là quyết định dựa trên allowlist và detection tin cậy hơn, không dựa riêng vào header do client gửi.

## 10. Gắn file đã được duyệt vào email bằng MimeMessageHelper

Khi đã có `ApprovedAttachment`, sender có thể đính kèm:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public class ReportMailSender {

    private final JavaMailSender mailSender;

    public ReportMailSender(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendReport(
            String recipient,
            ApprovedAttachment attachment)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message, true, "UTF-8");

        helper.setFrom("reports@example.com");
        helper.setTo(recipient);
        helper.setSubject("Báo cáo của bạn");
        helper.setText(
                "Xin chào, báo cáo đã được kiểm tra và được đính kèm.");

        helper.addAttachment(
                attachment.filename(),
                new ByteArrayResource(attachment.content()),
                attachment.contentType());

        mailSender.send(message);
    }
}
~~~

Ở đây `true` bật multipart; `addAttachment(...)` đóng gói byte array đã được kiểm tra vào MIME message. **Phương thức addAttachment không thực hiện antivirus scan**. Điều kiện an toàn phải được bảo đảm trước khi sender nhận `ApprovedAttachment`.

Một cách thiết kế tốt hơn là giữ constructor của `ApprovedAttachment` ở phạm vi package hoặc dùng factory/service riêng, để các lớp khác không thể tùy tiện tự tạo một object được coi là sạch. Java record công khai trong ví dụ chỉ nhằm minh họa dữ liệu; nó không tự tạo ranh giới bảo mật.

## 11. Xử lý file lớn bằng stream và quarantine storage

Với file lớn, cách dùng `MultipartFile.getBytes()` có thể làm heap tăng mạnh. Nên dùng stream đến storage tạm/quarantine, quét nội dung tại đó và chỉ cấp một resource có thể mở lại sau khi đã phê duyệt.

Luồng tổng quát:

~~~text
MultipartFile input stream
        |
        v
Quarantine object / temp file (random key)
        |
        +--> tính SHA-256
        |
        +--> xác định media type
        |
        +--> antivirus scan
        |
        v
Kết quả CLEAN + hash + object version
        |
        v
Approved storage object
        |
        v
InputStreamSource mở stream mới
        |
        v
MimeMessageHelper.addAttachment(...)
~~~

### InputStreamSource cần mở được stream mới

Spring `MimeMessageHelper.addAttachment(String, InputStreamSource, String)` nhận một `InputStreamSource`. Resource được cung cấp cần có khả năng mở stream mới khi thư viện cần đọc dữ liệu. Ví dụ về ý tưởng:

~~~java
InputStreamSource attachmentSource = () ->
        approvedStorage.openStream(
                attachment.objectKey(),
                attachment.objectVersion());

helper.addAttachment(
        attachment.filename(),
        attachmentSource,
        attachment.contentType());
~~~

Đây là code minh họa; `approvedStorage.openStream(...)` là API của storage do ứng dụng định nghĩa. Phải bảo đảm nó đọc đúng **object version đã được quét**, không đọc object hiện tại nếu object có thể bị ghi đè.

### Không dùng stream đã bị tiêu thụ

Scanner thường đọc hết stream. Nếu đưa cùng một `InputStream` đã scan vào `addAttachment`, stream có thể ở cuối hoặc đã đóng, khiến email đính kèm file rỗng/lỗi.

Giải pháp:

- Scan từ một stream riêng được mở từ quarantine object.
- Gửi bằng stream mới từ cùng object/version đã xác nhận.
- Hoặc giữ byte array nhỏ trong memory và tạo stream mới từ byte array.
- Không tái sử dụng một InputStream đã được scanner tiêu thụ.

### Temp file an toàn

Nếu cần file tạm:

- Lưu trong thư mục riêng không được web server phục vụ.
- Tạo tên ngẫu nhiên do ứng dụng sinh.
- Quyền đọc/ghi chỉ cấp cho process/role cần thiết.
- Không dùng original filename làm path.
- Đặt giới hạn dung lượng và số lượng file.
- Xóa file khi hoàn tất hoặc khi hết hạn.
- Không để file quarantine được sender truy cập trước trạng thái CLEAN.
- Cân nhắc mã hóa storage theo chính sách dữ liệu.

## 12. Quét bất đồng bộ khi cần xử lý nhiều file

Với hệ thống có nhiều upload hoặc scanner mất thời gian, có thể tách scan thành job bất đồng bộ:

~~~mermaid
sequenceDiagram
    participant U as User/API
    participant A as Attachment Service
    participant Q as Quarantine Storage
    participant W as Scan Worker
    participant AV as Antivirus
    participant M as Mail Worker

    U->>A: Upload file
    A->>A: Validate size/name/type
    A->>Q: Store as QUARANTINED
    A-->>U: attachmentId + PENDING_SCAN
    W->>Q: Read exact object version
    W->>AV: Scan content
    AV-->>W: CLEAN / INFECTED / ERROR
    W->>Q: Record scan result and hash
    alt CLEAN
        W->>M: Notify approved attachment
        M->>Q: Open same approved version
        M->>M: Attach and send email
    else INFECTED or ERROR
        W->>Q: Keep isolated / reject
    end
~~~

Ưu điểm:

- Request upload không phải chờ scanner lâu.
- Có thể scale worker scan độc lập.
- Có thể retry khi scanner tạm thời không khả dụng.
- Có trạng thái rõ ràng để UI hoặc nghiệp vụ theo dõi.

Nhưng không được gửi email ngay sau khi upload chỉ vì đã có attachment ID. Mail worker phải kiểm tra trạng thái CLEAN và phiên bản/hash tương ứng trước khi mở file.

### Trạng thái job scan

| Trạng thái | Chuyển tiếp hợp lệ điển hình |
| --- | --- |
| PENDING_SCAN | SCANNING hoặc EXPIRED |
| SCANNING | CLEAN, INFECTED, ERROR |
| CLEAN | APPROVED hoặc REVOKED theo policy |
| INFECTED | REJECTED / ISOLATED |
| ERROR | RETRY_PENDING hoặc MANUAL_REVIEW |
| APPROVED | ATTACHED / SENT khi nghiệp vụ hoàn tất |

Không nên để job ERROR tự chuyển thành CLEAN sau một khoảng thời gian. Chỉ có kết quả scanner đáng tin cậy cùng các kiểm tra khác mới cho phép phê duyệt.

## 13. Các loại tệp có rủi ro đặc biệt

### PDF

PDF là định dạng phổ biến cho hóa đơn và tài liệu, nhưng có thể chứa JavaScript, embedded files, launch actions, form, nội dung nhúng hoặc cấu trúc phức tạp. Antivirus scan là một lớp; nếu nghiệp vụ chỉ cần tài liệu PDF đơn giản, có thể dùng parser để kiểm tra cấu trúc và policy bổ sung cho active content. Không tự loại bỏ nội dung PDF bằng cách sửa byte stream mà không dùng thư viện phù hợp.

### Office documents

DOCX/XLSX/PPTX có thể là container ZIP. Các biến thể macro-enabled như DOCM/XLSM có hành vi khác và nên được phân biệt rõ. Nếu nghiệp vụ không cần macro, từ chối các loại macro-enabled. Nếu cho phép tài liệu Office, scanner phải hiểu container và giới hạn giải nén; không chỉ kiểm tra phần mở rộng `.docx`.

### SVG và HTML

SVG là XML có thể chứa script, tham chiếu tài nguyên ngoài hoặc nội dung phức tạp. HTML có thể chứa script, form, liên kết lừa đảo và nội dung hoạt động. Nếu chỉ cần ảnh, ưu tiên PNG/JPEG thay vì cho phép SVG tùy ý. Không gửi file HTML như một attachment vô hại chỉ vì nó có đuôi `.html`.

### Hình ảnh

Ảnh có thể có kích thước pixel rất lớn dù file nén nhỏ, metadata nhạy cảm (ví dụ EXIF/GPS), hoặc cấu trúc làm parser tiêu tốn nhiều tài nguyên. Nếu cần xử lý/thumbnail, giới hạn chiều rộng, chiều cao, tổng pixel và thời gian decode. Nếu cần xóa metadata, dùng thư viện ảnh phù hợp rồi **quét lại nội dung sau khi biến đổi**.

### Archive

Archive có thể chứa executable, script, file lồng nhau, đường dẫn traversal hoặc dữ liệu nén quá lớn. Chỉ chấp nhận archive nếu nghiệp vụ cần; scanner phải xử lý được các entry bên trong và báo rõ file mã hóa/không quét được.

### Tài liệu được bảo vệ bằng password

Scanner có thể không đọc được nội dung bên trong PDF/Office/ZIP được mã hóa. Nếu engine trả về “encrypted” hoặc “cannot inspect”, không nên tự coi đó là sạch. Có thể từ chối, yêu cầu định dạng không mã hóa qua kênh được kiểm soát, hoặc chuyển quy trình duyệt thủ công theo chính sách.

## 14. Kết hợp kiểm tra loại tệp, antivirus và chính sách nghiệp vụ

Một quyết định cho phép attachment nên có nhiều điều kiện:

~~~text
ACCEPT =
    size within limit
    AND extension is allowed
    AND detected media type is allowed
    AND extension matches detected type
    AND structural validation passes (when required)
    AND archive/resource limits pass (when applicable)
    AND malware scan result == CLEAN
    AND attachment belongs to this user/transaction
~~~

Đây là logic khái niệm. Mỗi nghiệp vụ có thể có thêm quy tắc: người gửi có quyền đính kèm tài liệu đó không, tài liệu có thuộc đúng đơn hàng/hồ sơ không, recipient có được phép nhận không và loại email có cho phép gửi tài liệu nhạy cảm không.

### MIME type cuối cùng dùng trong email

Khi đã xác định loại thực:

~~~java
helper.addAttachment(
        approved.filename(),
        new ByteArrayResource(approved.content()),
        approved.contentType());
~~~

Đặt content type theo **định dạng đã được phát hiện và chấp nhận**, không lấy trực tiếp header do client khai báo. Tên file hiển thị cũng phải là tên đã chuẩn hóa.

Nếu detector chỉ trả `application/octet-stream` hoặc không xác định được loại, không tự gán `application/pdf` vì tên file kết thúc bằng `.pdf`. Cần xử lý theo policy: từ chối hoặc dùng parser/detector phù hợp hơn.

## 15. Tích hợp Spring Boot: các lớp trách nhiệm

Một thiết kế có thể tách thành:

| Thành phần | Trách nhiệm |
| --- | --- |
| Upload controller | Nhận multipart request, áp dụng authorization và trả trạng thái |
| Attachment policy | Allowlist extension/type, size, rule nghiệp vụ |
| Content detector | Phát hiện media type từ byte stream |
| Structural validator | Kiểm tra cấu trúc/giới hạn theo định dạng |
| MalwareScanner adapter | Gọi antivirus/ICAP/cloud scanner |
| Quarantine storage | Lưu nội dung chưa được phê duyệt |
| Attachment approval service | Ghi trạng thái CLEAN, hash và object version |
| Mail service | Chỉ nhận attachment đã được phê duyệt và gửi |

Ví dụ controller không nên tự quét và gửi trong cùng một method nếu scanner có thể chạy lâu. Controller có thể tạo attachment job rồi trả trạng thái:

~~~java
@PostMapping("/attachments")
public ResponseEntity<AttachmentSubmission> upload(
        @RequestParam("file") MultipartFile file) {

    AttachmentSubmission submission = attachmentService.submit(file);

    return ResponseEntity.accepted().body(submission);
}
~~~

Đoạn code giả định `attachmentService.submit(...)` thực hiện kiểm tra cơ bản, lưu quarantine và khởi tạo scan job; `AttachmentSubmission` là DTO do ứng dụng định nghĩa. Endpoint cần authorization, CSRF protection khi phù hợp, rate limiting và giới hạn multipart ở hạ tầng.

### Mail service nhận kiểu dữ liệu đã phê duyệt

Thay vì nhận `MultipartFile` trực tiếp:

~~~java
public void sendReport(
        String recipient,
        ApprovedAttachment attachment) {
    // Tạo MimeMessage và gắn attachment đã được phê duyệt.
}
~~~

Điều này làm rõ hợp đồng: sender chỉ nhận dữ liệu đã qua bước inspection/scan. Với hệ thống lớn, có thể dùng ID của approved object và để mail worker tự kiểm tra trạng thái/hash trước khi mở stream.

## 16. Lỗi scanner và chính sách fail-closed

Antivirus service cũng là một dependency có thể lỗi:

- Network timeout.
- Scanner daemon không chạy.
- Database signature chưa cập nhật.
- File quá lớn so với giới hạn scanner.
- Định dạng mã hóa hoặc parser không hỗ trợ.
- Scanner trả response không hợp lệ.
- Queue scan bị tắc hoặc hết dung lượng.

Không được ánh xạ tất cả các trường hợp này thành CLEAN. Hãy phân biệt:

| Kết quả | Cách xử lý |
| --- | --- |
| CLEAN | Tiếp tục nếu các policy khác đạt |
| INFECTED | Từ chối, cách ly và phát cảnh báo phù hợp |
| TIMEOUT | Giữ pending, retry có backoff hoặc yêu cầu xử lý |
| UNAVAILABLE | Không gửi file; báo tình trạng scanner |
| UNSUPPORTED | Từ chối hoặc chuyển manual review |
| ENCRYPTED / CANNOT_INSPECT | Không coi là sạch; xử lý theo policy |
| MALFORMED_RESPONSE | UNKNOWN, ghi nhận lỗi adapter và điều tra |

### Fail-closed và trải nghiệm người dùng

Fail-closed không có nghĩa ứng dụng phải lỗi toàn bộ. Có thể:

- Lưu upload ở trạng thái chờ quét.
- Hiển thị “Tệp đang được kiểm tra”.
- Cho phép người dùng tiếp tục thao tác không phụ thuộc attachment.
- Chỉ gửi email sau khi scan hoàn tất.
- Nếu scan thất bại lâu, thông báo rằng tệp chưa thể gửi và hướng dẫn tải lên lại hoặc liên hệ hỗ trợ.

Với email không có attachment, nghiệp vụ có thể tiếp tục nếu không phụ thuộc file. Nhưng **không gửi file chưa được xác nhận sạch** chỉ để giữ tiến độ.

### Timeout và retry scanner

Retry scanner nên có:

- Timeout kết nối và timeout xử lý riêng.
- Số lần thử tối đa.
- Exponential backoff và jitter.
- Queue/dead-letter cho job quá số lần thử.
- Cảnh báo khi scanner unavailable kéo dài.
- Không gửi trùng hoặc scan cùng file vô hạn nếu không cần.

Kết quả scan có thể cache theo hash và phiên bản engine/signature database, nhưng phải có thời hạn và chính sách re-scan khi signature update hoặc mức rủi ro thay đổi. Không dùng cache CLEAN vô thời hạn cho file có thể đã bị phát hiện sau này.

## 17. Rủi ro TOCTOU: gửi đúng file đã được quét

Một lỗi tinh vi:

1. Ứng dụng quét file A và nhận CLEAN.
2. File lưu trên storage bị thay thế bằng file B.
3. Sender đọc file B và đính kèm.

Kết quả scan CLEAN thuộc về A, nhưng email gửi B. Đây là lỗi **time-of-check to time-of-use (TOCTOU)**.

Giảm rủi ro bằng cách:

- Tạo object immutable hoặc version ID sau khi upload.
- Tính SHA-256 khi đọc nội dung scan.
- Lưu hash cùng kết quả scan.
- Sender chỉ đọc đúng object version đó.
- Có thể kiểm tra hash trong lúc stream gửi nếu kiến trúc cho phép.
- Không cho phép update nội dung approved object; thay đổi tạo object/version mới và phải scan lại.

Nếu ứng dụng biến đổi file sau scan (ví dụ resize ảnh, convert PDF, xóa metadata), nội dung sau biến đổi là một file mới và nên được **kiểm tra/quét lại** trước khi gửi.

## 18. Quyền riêng tư và lưu giữ tệp

Quarantine và scanner có thể lưu nội dung tài liệu chứa thông tin cá nhân hoặc bí mật. Cần:

- Mã hóa dữ liệu khi lưu và khi truyền theo chính sách hạ tầng.
- Giới hạn quyền đọc quarantine và approved storage.
- Không phục vụ file quarantine qua URL công khai.
- Dùng signed URL có thời hạn và authorization nếu cần download.
- Không ghi nội dung file, password tài liệu hoặc toàn bộ dữ liệu cá nhân vào log.
- Đặt retention cho file sạch, file bị từ chối và file lỗi scan.
- Xóa bản tạm sau khi gửi hoặc sau khi job hết hạn theo chính sách.
- Ghi audit event cho upload, scan, approval, reject và send.

Scanner bên thứ ba có thể nhận bản sao file. Trước khi tích hợp, cần xác định vùng lưu trữ, nơi xử lý dữ liệu, thời hạn lưu, quyền truy cập và yêu cầu bảo mật của tổ chức. Không chuyển dữ liệu nhạy cảm tới dịch vụ không được phép chỉ vì API scanner tiện sử dụng.

## 19. Kiểm thử pipeline attachment

Kiểm thử nên bao gồm các trường hợp thành công và thất bại:

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| PDF hợp lệ, detected type PDF, scanner CLEAN | Có thể được phê duyệt |
| File thực thi đổi tên thành `.pdf` | Bị từ chối vì detected type không khớp |
| Client khai báo MIME sai | Không dựa vào khai báo; phát hiện/đối chiếu và xử lý theo policy |
| Phần mở rộng không trong allowlist | Bị từ chối trước scan hoặc theo policy |
| File rỗng | Bị từ chối |
| File vượt giới hạn | Bị từ chối trước khi đọc toàn bộ vào heap |
| Scanner trả INFECTED | Cách ly/từ chối, không gửi |
| Scanner timeout/unavailable | Trạng thái ERROR/PENDING, không gửi |
| File ZIP mã hóa/không thể inspect | Không được coi là CLEAN |
| File thay đổi sau scan | Hash/version không khớp, yêu cầu scan lại |
| Tên file có path traversal hoặc CR/LF | Bị từ chối hoặc chuẩn hóa an toàn |
| Attachment approved | Email dùng đúng content bytes, filename và detected MIME type |

### Unit test với scanner giả

Trong test, có thể thay antivirus thật bằng mock để kiểm tra quyết định của service:

~~~java
when(malwareScanner.scan(any(InputStream.class)))
        .thenReturn(new ScanResult(
                ScanStatus.CLEAN,
                "test-engine",
                "test-signatures",
                null));
~~~

Test này chỉ kiểm tra luồng ứng dụng khi scanner trả CLEAN; nó không chứng minh antivirus thật hoạt động. Cần integration test với scanner test instance hoặc môi trường được kiểm soát để xác nhận giao thức, timeout, kích thước và xử lý kết quả thực tế.

### Kiểm tra attachment trong email test

Sau khi tạo `MimeMessage`, có thể đọc MIME tree hoặc gửi tới SMTP capture server để xác nhận:

- Attachment có đúng tên hiển thị đã chuẩn hóa.
- Content-Type theo detected type.
- Byte content/hash trùng với file đã scan.
- Không có file nào ở trạng thái PENDING/ERROR/INFECTED được đính kèm.
- Kích thước email cuối cùng nằm trong giới hạn.

Không gửi file test độc hại thật vào mailbox người dùng. Khi kiểm tra khả năng phát hiện của scanner, dùng bộ test file chuyên dụng được nhà cung cấp scanner khuyến nghị, chẳng hạn EICAR trong môi trường test biệt lập, theo chính sách bảo mật của tổ chức.

## 20. Các lỗi thường gặp

### Chỉ kiểm tra đuôi file

```java
if (filename.endsWith(".pdf")) {
    helper.addAttachment(filename, file);
}
```

Đoạn này không xác minh nội dung thực, không quét malware, không giới hạn tài nguyên và không kiểm tra quyền của người dùng. Extension chỉ là một điều kiện đầu vào trong allowlist.

### Chỉ tin `MultipartFile.getContentType()`

Content-Type do client khai báo có thể giả. Dùng content detection từ byte stream và policy tương ứng; vẫn cần antivirus scan.

### Quét xong nhưng gửi file khác

Nếu scan từ một bản tạm nhưng sender đọc lại path có thể thay đổi, kết quả scan không còn gắn với byte gửi. Dùng immutable object/version và hash.

### Scanner không kết nối được nhưng vẫn gửi

Không coi timeout/unavailable là CLEAN. Giữ file pending hoặc từ chối gửi attachment cho đến khi có kết quả đáng tin cậy.

### Dùng `getBytes()` với file không giới hạn

Có thể làm heap cạn. Đặt giới hạn trước khi đọc; với file lớn, stream vào quarantine storage và dùng stream mới cho scan/send.

### Gửi ZIP mà không kiểm tra nội dung

ZIP có thể chứa executable, archive lồng nhau, file mã hóa hoặc archive bomb. Chỉ cho phép khi nghiệp vụ cần và scanner/policy hiểu nội dung bên trong.

### Dùng original filename làm đường dẫn

Có nguy cơ path traversal và ghi đè file. Tên lưu trữ phải do ứng dụng tạo; tên hiển thị được chuẩn hóa riêng.

### Coi file đúng định dạng là file sạch

Magic bytes hoặc parser xác nhận định dạng không thay thế antivirus. Một PDF hợp lệ vẫn có thể chứa payload độc hại.

### Quét trước khi biến đổi rồi gửi file đã biến đổi

Nếu resize, convert hoặc chỉnh sửa file sau scan, hash/nội dung đã thay đổi. Scan lại phiên bản cuối cùng sẽ được gửi.

### Bỏ qua file scanner không đọc được

Encrypted hoặc unsupported không đồng nghĩa sạch. Đưa về UNKNOWN/ERROR hoặc từ chối theo policy.

## 21. Quy trình xử lý attachment trước khi gửi

Một quy trình có thể áp dụng:

1. Xác thực người dùng và quyền đính kèm tài liệu vào giao dịch.
2. Kiểm tra request/file có rỗng và vượt giới hạn không.
3. Chuẩn hóa tên hiển thị, tạo storage ID ngẫu nhiên.
4. Kiểm tra extension theo allowlist.
5. Đọc/stream vào quarantine, tính hash và xác định media type.
6. Đối chiếu extension, detected type và policy định dạng.
7. Kiểm tra cấu trúc, archive limits và parser-specific rules nếu cần.
8. Gửi file đến antivirus scanner; nhận CLEAN/INFECTED/ERROR/UNKNOWN.
9. Chỉ phê duyệt khi toàn bộ điều kiện đạt và kết quả gắn với đúng hash/version.
10. Mail worker xác nhận trạng thái approved, đọc đúng object version và gắn file bằng `MimeMessageHelper`.
11. Gửi qua `JavaMailSender`, ghi trạng thái submission.
12. Xóa file tạm/quarantine theo retention và audit policy.

### Bảng quyết định cuối

| Điều kiện | Quyết định |
| --- | --- |
| Định dạng không được phép | Reject |
| Extension và detected type không khớp | Reject hoặc manual review |
| Cấu trúc không hợp lệ | Reject |
| Kích thước/giải nén vượt giới hạn | Reject |
| Scanner phát hiện malware | Isolate / reject |
| Scanner không khả dụng | Pending / reject; không gửi |
| Scanner trả CLEAN và hash/version khớp | Có thể approve |
| File thay đổi sau scan | Scan lại |
| Attachment approved và người nhận có quyền | Được đưa vào MIME message |

## 22. Câu hỏi tự kiểm tra

**1. Vì sao chỉ kiểm tra phần mở rộng không đủ?**

Vì tên file có thể bị đổi. File `.pdf` có thể chứa nội dung khác định dạng; cần phát hiện media type từ nội dung và quét malware.

**2. Có thể tin `MultipartFile.getContentType()` không?**

Không. Đây là giá trị client khai báo, có thể sai hoặc giả mạo. Dùng detector phân tích nội dung và allowlist.

**3. Magic bytes có chứng minh file sạch không?**

Không. Nó chỉ giúp nhận dạng định dạng sơ bộ. File đúng định dạng vẫn có thể chứa mã độc hoặc khai thác parser.

**4. Vì sao nên dùng allowlist?**

Vì nghiệp vụ chỉ cần một số loại file cụ thể; allowlist giới hạn bề mặt tấn công tốt hơn việc cố liệt kê mọi định dạng nguy hiểm.

**5. Scanner timeout thì có thể coi file là CLEAN không?**

Không. Timeout là ERROR/UNKNOWN. Theo chính sách an toàn, file phải ở trạng thái chờ hoặc bị từ chối, không được gửi.

**6. Vì sao phải quarantine file?**

Để ngăn file chưa được quét bị sender hoặc người dùng khác đọc và gửi đi trước khi có kết quả.

**7. Vì sao cần hash sau scan?**

Để gắn kết quả CLEAN với đúng byte content. Nếu file thay đổi sau scan, phải quét lại.

**8. Có thể dùng `getBytes()` cho mọi file upload không?**

Không. Cách này tải toàn bộ file vào heap. Chỉ dùng khi đã có giới hạn kích thước nhỏ; file lớn nên stream vào storage và mở stream mới cho scan/send.

**9. ZIP có thể được coi là an toàn khi signature hợp lệ không?**

Không. Cần kiểm tra entry, archive lồng nhau, file mã hóa, path traversal và giới hạn giải nén; hoặc từ chối nếu nghiệp vụ không cần archive.

**10. Nếu đổi kích thước ảnh sau khi scan thì có cần scan lại không?**

Có. Nội dung cuối cùng khác byte stream đã được quét, nên kết quả CLEAN cũ không còn áp dụng.

**11. `MimeMessageHelper.addAttachment(...)` có tự quét virus không?**

Không. Nó chỉ thêm nội dung vào MIME message. Scan và approval phải diễn ra trước đó.

**12. Vì sao cần kiểm tra tổng kích thước email?**

Base64 làm attachment lớn hơn file gốc và MIME có overhead. Nhiều file cộng lại có thể vượt giới hạn SMTP provider.

## Kết luận

**Kiểm tra virus và loại tệp phải diễn ra trước khi attachment được đưa vào email.** Spring Framework Mail cung cấp `MimeMessageHelper.addAttachment(...)` để đóng gói file, nhưng không xác minh định dạng hay quét mã độc. Hãy dùng allowlist theo nghiệp vụ, phát hiện media type từ nội dung, kiểm tra cấu trúc và giới hạn tài nguyên, quét bằng antivirus service, cách ly file chưa có kết quả và chỉ phê duyệt khi scanner trả CLEAN cho đúng hash/version. Khi gửi, dùng chính nội dung đã được duyệt, tên hiển thị đã chuẩn hóa và MIME type đã xác định. Nếu scanner lỗi, file mã hóa hoặc không thể inspect, không tự coi là sạch. **Một pipeline kiểm tra nhiều lớp giúp ngăn file không an toàn bị phát tán qua email và giữ rõ trách nhiệm giữa upload, scanning, approval và SMTP delivery.**
