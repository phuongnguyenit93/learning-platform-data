# Tên Unicode, metadata và khả năng tương tác giữa các công cụ ZIP trong Java 7+

## 1. Mục tiêu và phạm vi

Một tệp ZIP có thể giải nén được nhưng tên tệp tiếng Việt bị sai dấu, dấu thời gian bị lệch hoặc thuộc tính tệp bị mất khi chuyển giữa Java, Windows, macOS, Linux và các chương trình nén khác nhau. Nguyên nhân thường nằm ở **cách ghi tên entry và metadata**, không nằm ở thuật toán DEFLATE.

Sau bài này, bạn có thể:
- Tạo và đọc ZIP chứa tên tệp/thư mục Unicode bằng các API `java.util.zip` vẫn được dùng hiện nay.
- Hiểu vai trò của UTF-8, cờ EFS, các trường metadata và giới hạn khi trao đổi ZIP giữa công cụ.
- Phân biệt lỗi mã hóa **tên entry** với mã hóa **nội dung tệp**, kiểm thử khả năng tương tác và xử lý an toàn tên đường dẫn khi giải nén.

Các constructor nhận `Charset` xuất hiện từ Java 7 và vẫn hữu ích trong Java hiện đại. Ví dụ hoàn chỉnh phía dưới chạy bằng Java 17+; API thời gian `FileTime` của `ZipEntry` xuất hiện từ Java 8 và được ghi rõ để tránh nhầm với API có sẵn trong Java 7.

## 2. Tên entry trong ZIP: chuỗi Java khác byte lưu trong archive

ZIP là một container gồm các **entry** (tệp hoặc thư mục). Mỗi entry có tên và một số metadata ở *local file header*; ở cuối archive còn có *central directory* để tra cứu các entry. Tên được lưu dưới dạng **byte**, trong khi `ZipEntry.getName()` trả về `String` Unicode sau khi thư viện giải mã byte đó.

Ví dụ, tên `báo cáo/Đà Nẵng-📄.txt` gồm chữ có dấu, dấu cách và emoji. Nếu trình tạo ghi tên bằng UTF-8 nhưng trình đọc hiểu nhầm theo bảng mã khác, nội dung tệp có thể vẫn nguyên vẹn trong khi tên hiển thị sai. Đổi charset đọc **nội dung** không giải quyết được lỗi này.

### Cờ EFS (general-purpose bit flag, bit 11)

Theo đặc tả ZIP, khi **bit 11/EFS được bật**, tên entry và comment liên quan phải được mã hóa UTF-8. Khi bit này không bật, không thể chỉ nhìn tên đã giải mã để chắc chắn archive được tạo bằng charset nào; thực tế có archive từ nhiều công cụ dùng bảng mã theo môi trường tạo.

Trong Java:
- `new ZipOutputStream(out)` và `new ZipOutputStream(out, StandardCharsets.UTF_8)` dùng UTF-8 cho tên và comment. Với UTF-8, JDK ghi cờ ngôn ngữ UTF-8 phù hợp.
- `new ZipInputStream(in)` và `new ZipFile(file)` mặc định đọc tên bằng UTF-8.
- `ZipInputStream(in, charset)` và `ZipFile(file, charset)` cho phép chọn bảng mã của những entry **không bật EFS**. Khi entry bật EFS, charset truyền vào **không ghi đè UTF-8**. Các overload nhận `Charset` được bổ sung từ Java 7.
- Charset của tên entry **độc lập** với charset của payload: văn bản bên trong vẫn phải được ghi/đọc bằng charset riêng, ví dụ `StandardCharsets.UTF_8`.

**Quy ước nên dùng cho ZIP mới:** UTF-8 + EFS, đặt tên entry theo đường dẫn tương đối với dấu `/`. Chỉ cấu hình charset khác khi có bằng chứng về nguồn tạo archive và encoding thực tế; không dùng charset mặc định của hệ điều hành làm giả định chung.

### Unicode Path/Comment extra fields

Một số công cụ ghi thêm `0x7075` (Info-ZIP Unicode Path) hoặc `0x6375` (Unicode Comment) để giữ tên/comment UTF-8 bên cạnh trường tên theo cách mã hóa khác. Chúng là các **extra field**, khác cờ EFS. `java.util.zip` nhận biết EFS nhưng không tự dùng các trường Unicode Info-ZIP này để sửa tên; do đó một ZIP đọc đúng trong một phần mềm nén vẫn có thể sai tên khi mở bằng `ZipFile`. Nếu luồng tích hợp phải xử lý loại ZIP đó, nên xác định yêu cầu tương tác và dùng thư viện có hỗ trợ rõ ràng (ví dụ Apache Commons Compress), thay vì tự suy đoán encoding.

Không cần chủ động tạo extra field Unicode khi đã dùng tên UTF-8 và EFS, trừ khi yêu cầu thực tế của hệ thống đối tác đã được kiểm chứng. EFS cũng **không** quy định mã hóa nội dung tệp hay xác thực dữ liệu.

## 3. API nào dùng cho trường hợp nào?

| API | Dùng khi | Lưu ý về tên và metadata |
| --- | --- | --- |
| `ZipOutputStream` | Ghi ZIP tuần tự ra `OutputStream` | Dùng UTF-8; `putNextEntry` / `closeEntry` cho từng entry. |
| `ZipInputStream` | Đọc ZIP khi chỉ có `InputStream` (upload, network) | Đọc lần lượt local header; không thể coi là nguồn đầy đủ cho mọi metadata chỉ có trong central directory, đặc biệt entry comment. |
| `ZipFile` | Đọc ZIP đã nằm trong tệp, cần tra cứu hoặc duyệt entry | Đọc central directory, thuận lợi hơn khi cần tên, comment, kích thước và truy cập entry theo tên. Phải `close()` sau sử dụng. |
| `ZipEntry` | Biểu diễn tên, method, size, CRC, comment, timestamp, extra data | Không phải bản sao đầy đủ mọi thuộc tính hệ điều hành của tệp gốc. |
| ZIP File System Provider (`jdk.zipfs`) | Muốn thao tác các entry qua `Path`/`Files` | Có cấu hình `encoding` (mặc định UTF-8); kiểm tra khả năng lưu/đọc thuộc tính trên JDK và công cụ thực tế. |

Với archive đã tồn tại trên ổ đĩa và cần kiểm tra metadata, `ZipFile` thường phù hợp hơn `ZipInputStream`. Nếu dữ liệu đến qua luồng, vẫn dùng `ZipInputStream` được nhưng không nên kỳ vọng comment entry hoặc mọi trường chỉ có ở central directory đều hiện diện.

### Tên thư mục và đường dẫn

- Dùng `/` làm dấu phân cách phần đường dẫn bên trong ZIP, kể cả khi tạo trên Windows; không đưa ký tự phân cách của `Path` trên máy chạy vào tên entry một cách máy móc.
- Entry thư mục thường có tên kết thúc bằng `/`; `ZipEntry.isDirectory()` kiểm tra quy ước đó. Việc có một entry `docs/` riêng không phải lúc nào cũng cần để biểu diễn `docs/a.txt`, nhưng giúp nhiều công cụ hiện rõ thư mục rỗng.
- Tên entry nên **tương đối**: `docs/readme.txt`, không là đường dẫn tuyệt đối, ký hiệu ổ đĩa hoặc `../secret.txt`.
- Mặc dù tên trông giống nhau, Unicode có thể biểu diễn theo các chuỗi code point khác nhau: ví dụ chữ `é` dựng sẵn khác chuỗi `e` + dấu kết hợp. Java có `java.text.Normalizer` (chẳng hạn NFC), nhưng ZIP không tự chuẩn hóa mọi tên. Nếu ứng dụng chuẩn hóa tên, phải phát hiện trùng tên sau chuẩn hóa; cân nhắc cả hệ thống tệp không phân biệt hoa/thường.

## 4. Metadata nào có trong ZIP và độ tin cậy của nó?

| Metadata | API Java | Điều cần nhớ |
| --- | --- | --- |
| Tên và comment của entry | `getName()`, `getComment()`, `setComment()` | Comment là mô tả tùy chọn, không là dữ liệu nghiệp vụ đáng tin cậy; entry comment chủ yếu ở central directory. |
| Comment của archive | `ZipFile.getComment()`, `ZipOutputStream.setComment()` | Khác với comment của từng entry. |
| Kích thước | `getSize()`, `getCompressedSize()` | Đơn vị byte; có thể trả `-1` nếu chưa biết, nhất là khi đọc streaming. ZIP64 có thể cần cho dữ liệu lớn. |
| CRC-32 | `getCrc()`, `setCrc()` | Phát hiện sai lệch dữ liệu do lỗi truyền/lưu, **không** phải chữ ký số hay bảo đảm chống sửa đổi có chủ đích. |
| Phương pháp nén | `getMethod()`, `setMethod()` | API chuẩn hỗ trợ chủ yếu `DEFLATED` và `STORED`; không nên mặc định hỗ trợ mọi kiểu nén/mã hóa nâng cao của phần mềm bên ngoài. |
| Thời gian sửa đổi cơ bản | `getTime()`, `setTime(long)` | Có từ trước Java 7; tương thích với trường thời gian kiểu DOS có độ chính xác và quy tắc múi giờ hạn chế. |
| Thời gian mở rộng | `getLastModifiedTime()`, `setLastModifiedTime(FileTime)`, `getLastAccessTime()`, `getCreationTime()` | Có từ Java 8; sử dụng optional extended timestamp khi có thể. Một công cụ khác có thể không giữ hoặc không xuất tất cả trường này. |
| Extra field | `getExtra()`, `setExtra(byte[])` | Dữ liệu nhị phân theo định dạng của từng extension; không sửa/xóa tùy tiện vì có thể chứa timestamp, ZIP64 hoặc metadata dành cho công cụ khác. |

**Về thời gian:** trường DOS date/time truyền thống có độ phân giải 2 giây và không mang thông tin múi giờ rõ ràng. `setLastModifiedTime(FileTime)` giúp JDK ghi thêm extended timestamp có biểu diễn UTC, nhưng khi trao đổi với ứng dụng chỉ hiểu trường DOS hoặc với file system có độ chính xác khác, thời gian có thể sai khác. Khi so sánh thời gian, dùng một quy ước UTC rõ ràng, xem metadata là thông tin có thể thiếu và kiểm thử vòng đi-về (*round-trip*).

Các extra field thường gặp cần **nhận diện**, không tự triển khai nếu không có yêu cầu: `0x5455` (extended timestamp), `0x0001` (ZIP64), `0x7075` (Unicode Path) và `0x6375` (Unicode Comment). Metadata quyền POSIX, chủ sở hữu, ACL, symbolic link và thuộc tính riêng của hệ điều hành có thể được lưu bằng các quy ước khác nhau; `java.util.zip.ZipEntry` không có API chung bảo đảm phục hồi đầy đủ chúng. Nếu đây là yêu cầu nghiệp vụ, phải chọn công cụ/thư viện hỗ trợ metadata tương ứng và xác minh trên hệ điều hành đích.

**Về kích thước và method:** khi ghi entry `STORED` (không nén), thông thường phải cung cấp trước size và CRC hợp lệ. Với entry `DEFLATED`, `ZipOutputStream` có thể tính trong quá trình ghi. Không tự gán size/CRC đoán trước; đọc hết payload rồi mới kết luận dữ liệu thực tế hợp lệ.

## 5. Ví dụ chạy được: Unicode + comment + mtime + nội dung UTF-8

Ví dụ dùng Java 17+ để tạo ZIP có thư mục và một tệp tên tiếng Việt kèm emoji, gán comment và thời gian sửa đổi UTC, sau đó đọc lại bằng `ZipFile`. Đây là chương trình đầy đủ, không cần thư viện ngoài.

**Tệp `ZipUnicodeDemo.java`:**

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;
import java.time.Instant;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import java.util.zip.ZipOutputStream;

public class ZipUnicodeDemo {
    private static final String ENTRY_NAME = "báo cáo/Đà Nẵng-📄.txt";

    public static void main(String[] args) throws IOException {
        Path archive = Path.of("unicode-demo.zip");
        FileTime modified = FileTime.from(Instant.parse("2024-05-01T12:34:56Z"));

        try (ZipOutputStream out = new ZipOutputStream(
                Files.newOutputStream(archive), StandardCharsets.UTF_8)) {
            out.putNextEntry(new ZipEntry("báo cáo/"));
            out.closeEntry();

            ZipEntry entry = new ZipEntry(ENTRY_NAME);
            entry.setComment("Tài liệu UTF-8");
            entry.setLastModifiedTime(modified);
            out.putNextEntry(entry);
            out.write("Xin chào ZIP!".getBytes(StandardCharsets.UTF_8));
            out.closeEntry();
        }

        try (ZipFile zip = new ZipFile(archive.toFile(), StandardCharsets.UTF_8)) {
            ZipEntry entry = zip.getEntry(ENTRY_NAME);
            if (entry == null) {
                throw new IOException("Không tìm thấy entry");
            }
            System.out.println("Name: " + entry.getName());
            System.out.println("Comment: " + entry.getComment());
            System.out.println("Modified: " + entry.getLastModifiedTime().toInstant());
            try (InputStream in = zip.getInputStream(entry)) {
                System.out.println("Text: " +
                        new String(in.readAllBytes(), StandardCharsets.UTF_8));
            }
        }
    }
}
~~~

Biên dịch với mã nguồn UTF-8:

~~~bash
javac -encoding UTF-8 ZipUnicodeDemo.java
java ZipUnicodeDemo
~~~

Stdout khi terminal hiển thị Unicode đúng:

~~~text
Name: báo cáo/Đà Nẵng-📄.txt
Comment: Tài liệu UTF-8
Modified: 2024-05-01T12:34:56Z
Text: Xin chào ZIP!
~~~

Kết quả tạo thêm tệp `unicode-demo.zip` trong thư mục chạy. `ZipEntry.setLastModifiedTime` dùng `FileTime` (Java 8+), `Path.of` và `InputStream.readAllBytes` là API Java mới hơn; **đoạn này cố ý chạy trên Java 17+**, còn việc chỉ định `Charset` cho ZIP stream đã có từ Java 7. Nếu terminal hiện dấu `?` hoặc ký tự lạ, kiểm tra mã hóa terminal trước khi kết luận tên trong ZIP bị hỏng; có thể kiểm chứng tên qua một trình nén khác hoặc đọc byte/metadata.

Trong ví dụ, `entry.setComment` viết comment của **một tệp**, còn `new String(..., UTF_8)` giải mã **payload**. Cả hai quyết định độc lập với cách Java đọc **tên entry**.

## 6. Nhận ZIP từ công cụ khác: quy trình xử lý tên sai

1. **Xác nhận triệu chứng.** Tên entry sai nhưng nội dung đúng? Hay nội dung văn bản sai vì charset payload? Hay lỗi phát sinh ngay khi mở ZIP? Đây là ba lớp khác nhau.
2. **Kiểm tra nguồn tạo và thông số encoding.** Ưu tiên ZIP có EFS/UTF-8. Nếu entry không bật EFS và phía tạo cung cấp rõ charset, mở bằng `ZipFile(file, charset)` hoặc `ZipInputStream(in, charset)` tương ứng. Không thay charset theo thử-sai để rồi âm thầm đổi tên.
3. **Xem nhu cầu hỗ trợ extra field.** Nếu archive dựa vào Info-ZIP Unicode Path (`0x7075`), JDK `java.util.zip` không tự dùng nó như nguồn tên Unicode; cân nhắc Apache Commons Compress với cấu hình hỗ trợ các trường này.
4. **Kiểm tra tên sau giải mã.** Áp dụng chính sách tên hợp lệ, đường dẫn tương đối, Unicode normalization khi cần; phát hiện tên trùng/collision trên file system đích.
5. **Đọc và đối chiếu payload, metadata cần thiết.** Test lại archive bằng công cụ được đối tác thực sự sử dụng, thay vì chỉ test Java ghi rồi Java đọc.

**Ví dụ cấu hình (đoạn minh họa, chỉ dùng khi nhà cung cấp xác nhận charset và EFS không bật):**

~~~java
// Chỉ là cách cấu hình một archive từ nguồn đã xác nhận encoding.
// Không phải phương án mặc định cho ZIP mới.
try (ZipFile zip = new ZipFile(
        Path.of("partner.zip").toFile(),
        java.nio.charset.Charset.forName("windows-1258"))) {
    zip.stream().forEach(e -> System.out.println(e.getName()));
}
~~~

Nếu EFS bật, `Charset.forName("windows-1258")` không thay cách giải mã tên UTF-8. Việc đổi charset cũng không giải quyết được archive hỏng header, phương pháp nén không hỗ trợ hoặc metadata Unicode extra field mà thư viện không diễn giải.

## 7. Tương tác thực tế giữa Java và các công cụ

| Tình huống | Cách kiểm thử đáng tin |
| --- | --- |
| Java tạo ZIP, 7-Zip/Windows/macOS/Linux mở | Dùng UTF-8 + EFS; kiểm tra đúng tên có dấu/emoji, thư mục, comment và dữ liệu sau giải nén trên **phiên bản công cụ đích**. |
| Công cụ bên ngoài tạo ZIP, Java đọc | Kiểm tra tên qua `ZipFile`, xác minh EFS/charset nguồn và các extra field; đừng kết luận chỉ dựa trên việc archive mở thành công. |
| Tệp tên giống nhau sau normalization/case folding | Thử cặp tên NFC/NFD, hoa/thường, dấu kết hợp; phát hiện và giải quyết collision trước khi ghi ra ổ đĩa. |
| Cần giữ thời gian, quyền truy cập, symlink | Đối chiếu metadata trước/sau giải nén trên hệ điều hành đích; chọn thư viện hoặc định dạng bổ sung nếu cần fidelity cao. |
| ZIP lớn hoặc streaming | Kiểm tra ZIP64, giới hạn kích thước, tình huống size/CRC chưa có sẵn và khả năng hỗ trợ của công cụ đích. |
| Định dạng ZIP có mã hóa hoặc phương pháp nén đặc biệt | Xác minh công cụ đọc hỗ trợ thật; `java.util.zip` không phải bộ giải mã đa định dạng/mã hóa ZIP tổng quát. |

Một bộ test tương tác tốt nên có ít nhất các entry `ascii.txt`, `Tiếng Việt.txt`, `emoji-📄.txt`, tên có dấu kết hợp, thư mục rỗng, comment, mtime cố định và nội dung UTF-8. Kiểm tra **cả hai chiều**: tạo bằng Java → mở bằng công cụ khác và tạo bằng công cụ khác → mở bằng Java. Chụp lại tool version, hệ điều hành và ZIP thực tế để tái hiện khi lỗi xảy ra.

### Lưu ý bảo mật khi giải nén

Tên entry trong ZIP là **dữ liệu không tin cậy**. Không làm `outputDir.resolve(entry.getName())` rồi ghi ngay: entry có thể chứa `../`, đường dẫn tuyệt đối, ký tự phân cách ngoài quy ước hoặc tên xung đột trên hệ thống tệp. Trước khi giải nén:
- Giải mã tên theo chính sách đã xác minh, từ chối đường dẫn tuyệt đối, dấu ổ đĩa và thành phần `..`; chỉ chấp nhận đường dẫn nằm trong thư mục đích sau `normalize()` và kiểm tra `startsWith(root)`.
- Xử lý symlink trong cây thư mục đích và trong archive theo chính sách riêng; phép kiểm tra chuỗi đường dẫn/`normalize()` **không đủ** nếu có symlink hiện hữu dẫn ra ngoài root.
- Đặt giới hạn số entry, tổng byte sau giải nén, độ sâu thư mục, tỉ lệ nén, thời gian và tài nguyên để phòng ZIP bomb. Kiểm tra trùng tên trước khi ghi đè.
- Đừng coi CRC-32 là bảo vệ trước attacker; cần xác thực nguồn file hoặc chữ ký/checksum đáng tin theo bài toán bảo mật riêng.

## 8. Những lỗi thường gặp và cách sửa

- **Tên sai dấu khi đọc:** kiểm tra EFS, charset thực của tên, Unicode extra field; không thay charset của payload để sửa tên.
- **Java đọc được nhưng công cụ đích hiển thị sai:** test theo phiên bản công cụ đích; tránh giả định mọi chương trình giải nén hỗ trợ metadata giống nhau.
- **Comment bị `null` khi dùng `ZipInputStream`:** phần comment của entry thuộc central directory; đọc bằng `ZipFile` nếu cần metadata đó.
- **Timestamps lệch hoặc mất:** phân biệt DOS timestamp với extended timestamp UTC và xem hỗ trợ của công cụ đích; không dùng thời gian làm định danh duy nhất của nội dung.
- **Tên bị trùng sau giải nén:** chú ý normalization, hoa/thường và quy tắc đặt tên của file system đích; kiểm tra collision trước khi tạo tệp.
- **Metadata mất sau round-trip:** `ZipEntry` không bảo tồn tự động toàn bộ quyền, chủ sở hữu hay symlink của file system; cần bài test và thư viện phù hợp.
- **Cố đoán CRC/size với `STORED`:** tính đúng trước khi ghi hoặc dùng `DEFLATED` để stream an toàn hơn trong trường hợp thông dụng.
- **Giải nén đúng tên nhưng không an toàn:** kiểm tra path traversal, symlink, trùng tên và hạn mức tài nguyên trước khi ghi.

## 9. Checklist cho một luồng ZIP có khả năng tương tác tốt

- [ ] ZIP mới ghi tên/comment entry bằng UTF-8 với EFS; nội dung tệp chọn charset độc lập.
- [ ] Tên entry là đường dẫn tương đối với `/`; chính sách normalization và collision được định nghĩa rõ.
- [ ] Công cụ đọc được chọn theo dữ liệu đầu vào: `ZipFile` cho tệp và central metadata, `ZipInputStream` cho luồng.
- [ ] Metadata cần giữ được chỉ định rõ (mtime, comment, permissions, symlink...) và có test round-trip trên công cụ/OS đích.
- [ ] Không dựa vào charset mặc định, không tự suy đoán encoding khi EFS vắng mặt, không kỳ vọng Java tự diễn giải `0x7075`.
- [ ] Có kiểm soát đường dẫn, symlink, số entry và tổng dung lượng giải nén cho ZIP không tin cậy.
- [ ] Bộ test có tên tiếng Việt, Unicode kết hợp, emoji, thư mục rỗng, ZIP lớn (nếu cần) và kiểm tra được cả hai chiều tương tác.

### Tài liệu đối chiếu

- [Oracle JDK 21 — `ZipOutputStream`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/zip/ZipOutputStream.html), [`ZipInputStream`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/zip/ZipInputStream.html), [`ZipFile`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/zip/ZipFile.html), [`ZipEntry`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/zip/ZipEntry.html).
- [PKWARE — APPNOTE ZIP File Format Specification](https://support.pkware.com/pkzip/appnote) (Language Encoding/EFS, extra fields, central directory).
- [Apache Commons Compress — ZIP package and interoperability](https://commons.apache.org/proper/commons-compress/zip).
- [Oracle — ZIP File System Provider properties](https://docs.oracle.com/javase/8/docs/technotes/guides/io/fsp/zipfilesystemproviderprops.html).

**Ghi nhớ:** dữ liệu tệp, tên Unicode và metadata là ba phần cần kiểm tra độc lập. Ghi ZIP theo UTF-8/EFS, đọc đúng nguồn gốc encoding và kiểm thử bằng công cụ đích giúp luồng ZIP đáng tin cậy hơn.