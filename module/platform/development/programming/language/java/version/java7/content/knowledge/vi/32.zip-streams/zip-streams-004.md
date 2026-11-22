# Giới hạn định dạng ZIP và kho lưu trữ kích thước lớn (Java 7+)

## 1. Bài toán cần hiểu

Một tệp `.zip` có thể chứa vài tệp rất lớn hoặc hàng trăm nghìn tệp nhỏ. Câu hỏi “ZIP chứa tối đa bao nhiêu GB?” không có một đáp án duy nhất: cần phân biệt **kích thước từng mục (entry)**, **kích thước toàn bộ archive**, **số lượng entry**, **kích thước bảng chỉ mục**, và **khả năng của phần mềm đọc/ghi**.

Trong Java hiện đại, `java.util.zip` vẫn hữu ích để tạo và đọc ZIP lớn. Các nguyên tắc đang áp dụng là **ZIP64 cho giới hạn biểu diễn kích thước**, **luồng dữ liệu để tránh nạp cả tệp vào RAM**, **quản lý tài nguyên**, **kiểm tra tương thích** và **giới hạn tài nguyên khi xử lý ZIP không tin cậy**. ZIP64 không phải thuật toán nén mới.

## 2. Cấu trúc ZIP và nguồn gốc của các giới hạn

Một ZIP thông dụng gồm các thành phần:

```text
[Local file header][Dữ liệu entry 1][Data descriptor nếu dùng]
[Local file header][Dữ liệu entry 2][Data descriptor nếu dùng]
...
[Central directory: thông tin và vị trí các entry]
[ZIP64 EOCD + locator nếu cần]
[End of central directory (EOCD)]
```

- **Local file header** đứng trước dữ liệu từng entry. Khi ghi tuần tự và chưa biết CRC/kích thước cuối cùng, dữ liệu bổ sung có thể xuất hiện sau nội dung entry dưới dạng `data descriptor`.
- **Central directory** ở gần cuối ZIP, lưu danh sách entry, kích thước, CRC, phương pháp nén và vị trí để phần mềm có thể tìm từng mục.
- **EOCD** đánh dấu kết thúc phần thư mục và lưu thông tin tổng hợp. Vì thư mục trung tâm được hoàn thiện ở cuối, một luồng ZIP bị ngắt trước khi `finish()`/`close()` có thể không mở được dù dữ liệu entry đã được ghi.

Định dạng ZIP “cổ điển” dùng nhiều trường số nguyên **16 bit** hoặc **32 bit không dấu**. Vì vậy giới hạn xuất phát từ độ rộng của các trường metadata, không phải vì `InputStream` của Java chỉ đọc được 4 GB.

| Trường trong ZIP thông thường | Độ rộng | Ngưỡng biểu diễn cổ điển | Tác động |
| --- | ---: | --- | --- |
| Kích thước nén/giải nén của **một entry** | 32 bit | `0xFFFFFFFF` = 4.294.967.295 byte (xấp xỉ 4 GiB) | Tệp lớn cần ZIP64 |
| Offset tới header entry, kích thước/offset central directory | 32 bit | Gần 4 GiB | Ngay cả các entry nhỏ cũng có thể cần ZIP64 nếu archive đủ lớn |
| Tổng số entry trong EOCD | 16 bit | `0xFFFF` = 65.535 | Archive nhiều entry cần metadata ZIP64 khi vượt ngưỡng; triển khai có thể dùng giá trị biên làm dấu hiệu ZIP64 |
| Độ dài tên entry, comment và một số trường extra | 16 bit theo byte | Tối đa 65.535 byte cho từng trường tương ứng | **ZIP64 không xóa giới hạn tên/comment này** |

**Lưu ý đơn vị:** `4 GiB = 4 × 1.024³ = 4.294.967.296 byte`; `4 GB` theo hệ thập phân là `4.000.000.000 byte`. Các mô tả “giới hạn 4 GB” thường đang nói gần ngưỡng **4 GiB** của trường 32 bit.

## 3. ZIP64 giải quyết được gì?

**ZIP64** mở rộng metadata bằng các trường **64 bit** và các bản ghi mở rộng, đặc biệt là **ZIP64 extended information extra field**, **ZIP64 end of central directory record** và **ZIP64 locator**. Khi trường cổ điển không đủ biểu diễn, ZIP lưu giá trị thích hợp trong metadata ZIP64.

ZIP64 được dùng khi gặp một hoặc nhiều trường hợp:

1. Một entry có kích thước đã nén hoặc chưa nén vượt mức biểu diễn 32 bit.
2. Vị trí hoặc kích thước central directory vượt mức biểu diễn 32 bit vì archive quá lớn.
3. Số lượng entry vượt mức biểu diễn của bộ đếm EOCD cổ điển.

Ví dụ: ZIP 9 GiB chứa ba video, mỗi video chỉ 3 GiB, vẫn có thể cần ZIP64 do **offset** và tổng kích thước archive. Ngược lại, archive 700 MiB chứa hơn 70.000 mục có thể cần ZIP64 vì **số lượng mục**. Mỗi ví dụ tác động tới trường metadata khác nhau.

**Trong thực tế Java:** các bản OpenJDK/Oracle JDK hiện đại có hỗ trợ ZIP64 trong `java.util.zip`; `ZipOutputStream` tự xuất metadata cần thiết khi gặp các điều kiện kích thước/số mục phù hợp. API không yêu cầu gọi `setZip64(true)`. Tuy nhiên, đặc tả Java cho phép một số triển khai `java.util.zip` hỗ trợ ZIP64 theo tính năng tùy chọn: khi chạy trên một Java runtime không quen thuộc, phải **kiểm tra runtime và thử đọc lại archive lớn**.

ZIP64 **không** làm cho archive vô hạn: thư viện, bộ nhớ, ổ đĩa, hệ thống tệp, thời gian xử lý, giới hạn tên entry, khả năng đọc của phần mềm đối tác và thiết kế vận hành vẫn là các giới hạn thực tế. Phần mềm ZIP không hỗ trợ ZIP64 có thể từ chối hoặc đọc sai archive lớn.

## 4. Chọn API Java phù hợp

| API | Dùng để làm gì | Tính chất đáng chú ý khi archive lớn |
| --- | --- | --- |
| `ZipOutputStream` | Ghi lần lượt các entry ra `OutputStream` | Ghi nội dung từng phần; ghi central directory khi hoàn tất; cần `close()`/`finish()`. Metadata quản lý từng entry vẫn tiêu tốn tài nguyên nếu số entry cực lớn. |
| `ZipInputStream` | Đọc tuần tự entry từ một luồng | Phù hợp khi dữ liệu đến qua mạng/stream; không cần nạp nguyên archive. Đọc từ local header, không dựa vào toàn bộ central directory; một số metadata có thể chưa biết trong lúc đang đọc. |
| `ZipFile` | Mở archive đã nằm trong tệp và tra cứu entry | Đọc central directory, `getEntry(name)`/`getInputStream(entry)` thuận tiện khi truy cập chọn lọc; cần đóng file và cân nhắc chi phí metadata với archive cực nhiều entry. |
| `ZipEntry` | Biểu diễn thông tin của một entry | `getSize()`, `getCompressedSize()` dùng `long`; có thể trả `-1` khi chưa biết, nhất là khi đọc luồng tuần tự. |
| `Files.newInputStream`, `Files.newOutputStream`, `InputStream.transferTo` | Truyền byte có bộ đệm | Tránh lưu toàn bộ entry vào mảng byte trong heap. `transferTo` có từ Java 9; ví dụ bên dưới dùng Java 17+. |

### DEFLATED và STORED

- `ZipEntry.DEFLATED` là nén DEFLATE thông thường; `ZipOutputStream` có thể tính kích thước đã nén và CRC trong quá trình ghi. Với entry mới, thường **không cần** `setSize()`, `setCompressedSize()` hay `setCrc()` trước.
- `ZipEntry.STORED` giữ nguyên nội dung (không nén). Trước `putNextEntry()`, Java yêu cầu biết **kích thước, compressed size và CRC-32 chính xác** của entry; thường phải tính trước một lượt. `STORED` thích hợp khi dữ liệu vốn đã nén và đã biết metadata, nhưng không có nghĩa là tự động tiết kiệm RAM.
- ZIP64 là **cách lưu kích thước/vị trí**, độc lập với DEFLATED/STORED. ZIP64 không bắt buộc nén mạnh hơn và không bảo đảm file ZIP nhỏ hơn.

## 5. Ví dụ chạy được: tạo ZIP từ một tệp lớn mà không giữ toàn bộ tệp trong RAM

Tạo tệp `LargeZipExample.java`:

```java
import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import java.util.zip.ZipOutputStream;

public class LargeZipExample {
    public static void main(String[] args) throws IOException {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: java LargeZipExample <input-file> <new-zip-file>");
        }

        Path input = Path.of(args[0]);
        Path output = Path.of(args[1]);
        if (!Files.isRegularFile(input)) {
            throw new IOException("Input is not a regular file: " + input);
        }

        try (InputStream in = new BufferedInputStream(
                    Files.newInputStream(input));
             ZipOutputStream zip = new ZipOutputStream(
                    new BufferedOutputStream(Files.newOutputStream(
                            output,
                            StandardOpenOption.CREATE_NEW,
                            StandardOpenOption.WRITE)),
                    StandardCharsets.UTF_8)) {

            ZipEntry entry = new ZipEntry(input.getFileName().toString());
            zip.putNextEntry(entry);  // DEFLATED mac dinh
            in.transferTo(zip);       // Doc/ghi theo luong, khong readAllBytes()
            zip.closeEntry();
        } // close() hoan tat central directory va dong tep

        try (ZipFile check = new ZipFile(
                output.toFile(), StandardCharsets.UTF_8)) {
            ZipEntry entry =
                    check.getEntry(input.getFileName().toString());
            if (entry == null) {
                throw new IOException("Entry missing from ZIP");
            }
            System.out.println(
                    "ZIP created; entry metadata read successfully.");
        }
    }
}
```

Biên dịch/chạy bằng JDK 17+ (thay `large.bin` bằng đường dẫn tệp thực tế; `archive.zip` phải chưa tồn tại):

```bash
javac -encoding UTF-8 LargeZipExample.java
java LargeZipExample large.bin archive.zip
```

Khi thành công, stdout chính xác là:

```text
ZIP created; entry metadata read successfully.
```

**Giải thích:**

1. `transferTo(zip)` chuyển dữ liệu theo luồng nên không cấp phát mảng có kích thước bằng tệp gốc. Tệp 6 GiB vẫn được xử lý từng phần; áp lực RAM chủ yếu thuộc bộ đệm, trạng thái nén và metadata ZIP.
2. `ZipOutputStream` mặc định dùng DEFLATED, cập nhật thông tin entry khi ghi và kết thúc cấu trúc ZIP khi đóng. Với JDK có ZIP64, các trường mở rộng được sinh khi cần; không tính CRC/kích thước trước cho DEFLATED.
3. `StandardOpenOption.CREATE_NEW` từ chối ghi đè `archive.zip` đã có. Trong ứng dụng thật, nên ghi file tạm, kiểm tra rồi đổi tên khi hoàn tất để tránh công bố archive dở dang nếu lỗi giữa chừng.
4. `ZipFile` mở lại và tìm entry từ central directory. Đoạn ví dụ chỉ kiểm tra **đọc được metadata**, chưa kiểm chứng nội dung từng byte, mã băm đầu-cuối hay khả năng tương thích với phần mềm khác.
5. Thời gian và tỷ lệ nén phụ thuộc dữ liệu. Video/JPEG đã nén thường không giảm đáng kể; văn bản lặp nhiều có thể giảm mạnh. Không dựa vào dung lượng ZIP để dự đoán dung lượng giải nén.

## 6. Ví dụ chạy được: quét ZIP theo luồng và chặn vượt hạn mức giải nén

Archive đầu vào có thể chứa một entry khai báo dung lượng nhỏ hoặc `getSize() == -1`, nhưng thực tế giải nén ra rất nhiều byte. Vì vậy **phải đếm số byte thật sự đọc**, bên cạnh việc kiểm tra metadata. Ví dụ bên dưới **chỉ quét, không giải nén ra ổ đĩa**, với hạn mức minh họa cho từng hệ thống (cần điều chỉnh theo nhu cầu thực tế).

Tạo `BoundedZipScan.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

public class BoundedZipScan {
    private static final int MAX_ENTRIES = 100_000;
    private static final long MAX_ENTRY_BYTES =
            2L * 1024 * 1024 * 1024;  // 2 GiB
    private static final long MAX_TOTAL_BYTES =
            8L * 1024 * 1024 * 1024;  // 8 GiB

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: java BoundedZipScan <zip-file>");
        }

        long totalBytes = 0;
        int entries = 0;
        byte[] buffer = new byte[8192];

        try (ZipInputStream zip = new ZipInputStream(
                Files.newInputStream(Path.of(args[0])),
                StandardCharsets.UTF_8)) {
            ZipEntry entry;
            while ((entry = zip.getNextEntry()) != null) {
                if (++entries > MAX_ENTRIES) {
                    throw new IOException("Too many ZIP entries");
                }
                if (entry.getSize() > MAX_ENTRY_BYTES) {
                    throw new IOException("Declared entry too large");
                }

                long entryBytes = 0;
                int read;
                while ((read = zip.read(buffer)) != -1) {
                    entryBytes += read;
                    totalBytes += read;
                    if (entryBytes > MAX_ENTRY_BYTES
                            || totalBytes > MAX_TOTAL_BYTES) {
                        throw new IOException(
                                "Decompressed data quota exceeded");
                    }
                }
                zip.closeEntry();
            }
        }

        System.out.printf(
                "Entries: %d, uncompressed bytes: %d%n",
                entries, totalBytes);
    }
}
```

```bash
javac -encoding UTF-8 BoundedZipScan.java
java BoundedZipScan archive.zip
```

Stdout có dạng `Entries: <số mục>, uncompressed bytes: <số byte>`; giá trị thực phụ thuộc archive. Đoạn chương trình giới hạn **số entry, kích thước từng entry và tổng byte giải nén** dù metadata chưa biết. Nó không tự đặt giới hạn thời gian/CPU, tỷ lệ nén, độ sâu thư mục hay kiểm chứng chữ ký; nếu dùng trong dịch vụ nhận upload, phải bổ sung các giới hạn phù hợp và cơ chế hủy công việc.

**Điểm cần phân biệt:** `ZipInputStream` đi theo local header, nên không có đủ metadata trong central directory; đây là lựa chọn tốt để xử lý tuần tự nhưng **không thay thế** việc xác thực cấu trúc toàn archive bằng trình đọc phù hợp khi ứng dụng cần kiểm tra/tra cứu central directory. Tránh `readAllBytes()` đối với entry lớn hoặc không tin cậy: nó có thể dùng lượng heap rất lớn và gây `OutOfMemoryError`.

## 7. Các giới hạn vận hành vẫn tồn tại với ZIP64

### 7.1. Hệ thống tệp, ổ đĩa và đường truyền

- Kiểm tra dung lượng đĩa **trong quá trình** tạo/giải nén; tổng dữ liệu sau giải nén có thể lớn hơn rất nhiều so với ZIP. Hệ thống tệp hoặc quota của container có thể chặn tệp rất lớn dù định dạng ZIP64 cho phép.
- Dự kiến lỗi I/O, hết dung lượng, mất mạng, tệp nguồn bị thay đổi khi đang nén, archive bị cắt khi upload. Việc nén thành công cần đóng stream, rồi xác minh rằng file ZIP hoàn chỉnh đã được lưu.
- Ghi ra tệp tạm và chỉ công bố tệp kết quả sau khi hoàn tất. Nếu cần đảm bảo không phát hành file lỗi, thêm xác minh giải nén/test archive và dọn file tạm khi thất bại.
- Khi truyền ZIP lớn qua mạng hoặc lưu trên object storage, dùng multipart/resumable upload và xác minh kích thước/checksum theo khả năng hệ thống lưu trữ; ZIP64 không giải quyết truyền tải bị gián đoạn.

### 7.2. Số lượng entry và bộ nhớ metadata

- Đọc/ghi **một** entry lớn theo luồng giúp tránh heap tương đương kích thước entry, nhưng **hàng triệu entry** tạo ra nhiều đối tượng metadata, tên file và bản ghi central directory. RAM, file handle, thời gian mở archive và lập chỉ mục có thể trở thành nút thắt.
- Nếu ứng dụng cần tra cứu một số entry trong ZIP đã hoàn chỉnh, `ZipFile` thường thuận tiện hơn việc quét lặp lại toàn bộ archive bằng `ZipInputStream`.
- Nếu cần xử lý tuần tự đầu vào chưa nằm trên đĩa, `ZipInputStream` phù hợp hơn; nó không hỗ trợ truy cập ngẫu nhiên tới entry phía sau.
- Khi chứa quá nhiều tệp nhỏ, cân nhắc chia nhiều archive có kích thước quản lý được, và kiểm tra yêu cầu khôi phục/đối tác. Chia thành nhiều **ZIP độc lập** khác với “split ZIP” nhiều volume; không giả định mọi thư viện Java đều hiểu dạng nhiều volume.

### 7.3. Tương thích ZIP64, phương pháp nén và tên tệp

- Không phải mọi phần mềm gắn nhãn “hỗ trợ ZIP” đều hỗ trợ ZIP64, ZIP chia volume, ZIP có mật khẩu/AES, hoặc mọi phương pháp nén. `java.util.zip` chuẩn tập trung vào **STORED/DEFLATED**; đừng suy luận nó đọc được mọi extension ZIP.
- Chọn UTF-8 khi tạo tên entry (`StandardCharsets.UTF_8`) và thử đọc trên các hệ thống đích. ZIP có cơ chế cờ UTF-8; khi cờ này bật, charset do caller truyền cho `ZipFile`/`ZipInputStream` không thay thế tên đã đánh dấu UTF-8.
- Tên entry trong ZIP dùng dấu `/` làm dấu phân cách hợp lý cho đường dẫn bên trong archive; không ghi trực tiếp đường dẫn tuyệt đối của máy nguồn. Giới hạn độ dài tên và một số trường comment là **số byte**, không phải số ký tự Unicode.
- CRC-32 giúp phát hiện hỏng dữ liệu vô tình, **không phải mã xác thực chống sửa đổi độc hại**. Với gói phân phối cần tính toàn vẹn/nguồn gốc, dùng cơ chế băm có kiểm chứng và chữ ký phù hợp bên ngoài ZIP.

## 8. ZIP không tin cậy: rủi ro tăng theo kích thước

**ZIP bomb:** Archive rất nhỏ nhưng giải nén ra lượng byte rất lớn hoặc rất nhiều entry; tỷ lệ nén cao làm cạn CPU, RAM, đĩa. Không chỉ kiểm tra kích thước ZIP hay `ZipEntry.getSize()`. Đếm byte thực tế, giới hạn từng mục, tổng số mục, tổng byte, thời gian xử lý và ngân sách tài nguyên. Các hạn mức mẫu trong `BoundedZipScan` chỉ mang tính minh họa.

**ZIP Slip/path traversal:** Entry có tên như `../../outside.txt`, tên tuyệt đối hoặc các biến thể đường dẫn theo hệ điều hành có thể khiến chương trình giải nén ghi ra ngoài thư mục đích. Với một chương trình ghi entry ra file, tối thiểu phải chuẩn hóa và kiểm tra containment:

```java
Path root = Path.of("extract").toAbsolutePath().normalize();
Path target = root.resolve(entry.getName()).normalize();
if (!target.startsWith(root)) {
    throw new IOException("Entry escapes extraction root");
}
```

Đây **chỉ là một bước kiểm tra đường dẫn**, không phải bộ giải nén bảo mật hoàn chỉnh: phải xử lý các dạng tên nguy hiểm theo nền tảng, symlink có sẵn hoặc được tạo trong thư mục đích, đua tranh thay đổi đường dẫn (TOCTOU), tên trùng, ghi đè file và giới hạn tài nguyên. Thực tế nên giải nén trong thư mục cách ly do chương trình kiểm soát, từ chối link không được phép, không cho ghi đè file quan trọng và chỉ công bố kết quả sau khi kiểm tra.

**Archive hỏng/cố ý gây lỗi:** Catch `IOException`/`ZipException`, đóng tài nguyên, không coi metadata được khai báo là chân lý; tránh để tệp giải nén một nửa được tiếp tục sử dụng. Nếu cần xác minh đầy đủ một gói quan trọng, thử đọc toàn bộ nội dung, đối chiếu checksum/chữ ký từ nguồn đáng tin và kiểm tra cấu trúc bằng công cụ tương thích.

## 9. Tình huống lựa chọn giải pháp

| Tình huống | Phương án hợp lý | Vì sao |
| --- | --- | --- |
| Nén một log 6 GiB | `ZipOutputStream` + stream + runtime hỗ trợ ZIP64 | Một entry vượt vùng kích thước cổ điển; không nạp log vào heap |
| Nén 100.000 JSON nhỏ | ZIP64 + theo dõi số entry/bộ nhớ; có thể chia thành các ZIP độc lập | Giới hạn bộ đếm entry; chi phí central directory |
| Đọc một file cụ thể trong ZIP 20 GiB trên đĩa | `ZipFile.getEntry()` + `getInputStream()` | Tra cứu từ central directory, đọc entry được chọn |
| Nhận archive qua HTTP stream | `ZipInputStream` + quota byte/entry + timeout | Đọc tuần tự, chưa cần lưu cả ZIP; metadata có thể chưa đầy đủ |
| Nhận ZIP upload của người dùng và giải nén | Path validation, kiểm soát symlink, quota, vùng cách ly | Ngăn traversal, ZIP bomb và ghi đè không an toàn |
| Chuyển ZIP lớn cho bên thứ ba | Thử giải nén bằng chính công cụ phiên bản phía nhận | Tính tương thích ZIP64/phương pháp nén khác nhau giữa các phần mềm |

## 10. Lỗi phổ biến cần tránh

1. **Nhầm “archive > 4 GiB” với “mỗi entry > 4 GiB”.** Cả offset, central directory và số entry đều có thể kích hoạt ZIP64.
2. **Cho rằng đổi sang ZIP64 là đủ.** Phần mềm đọc, quota đĩa, giới hạn tài nguyên và kiểm tra an toàn vẫn quyết định khả năng xử lý.
3. **Dùng `int` để cộng kích thước.** Dùng `long` cho byte count; kiểm tra vượt giới hạn khi cộng để tránh tràn số trong code tổng quát.
4. **Dùng `readAllBytes()`/`ByteArrayOutputStream` cho file lớn.** Nên truyền từng khối dữ liệu; không coi `getSize() == -1` là tệp có kích thước 0.
5. **Dùng STORED nhưng không có CRC và kích thước chính xác trước.** Chọn DEFLATED để ghi stream dễ hơn, hoặc tính một lượt trước khi ghi STORED.
6. **Quên đóng `ZipOutputStream`.** Central directory/EOCD có thể chưa được ghi; archive tạo dở không hợp lệ.
7. **Tin đường dẫn và kích thước khai báo của ZIP không rõ nguồn.** Áp hạn mức thực tế, kiểm tra đường dẫn và chặn symlink/ghi đè.
8. **Cho rằng CRC-32 bảo đảm tính xác thực.** CRC không thay thế chữ ký số hay cơ chế xác thực.
9. **Không kiểm thử ZIP64 với phần mềm nhận.** Một file tạo được trên JDK của bạn vẫn có thể không được phần mềm bên ngoài chấp nhận.

## 11. Checklist trước khi đưa vào hệ thống

- [ ] Biết rõ giới hạn **entry**, **archive**, **số entry** và ngưỡng byte đã giải nén cho nghiệp vụ.
- [ ] Xác minh runtime Java và công cụ phía nhận có hỗ trợ ZIP64 khi cần.
- [ ] Dùng stream và `long`, tránh tải cả entry vào RAM; đóng mọi tài nguyên với try-with-resources.
- [ ] Hoàn thiện/đóng ZIP, kiểm tra dung lượng đĩa và xác minh archive trước khi công bố.
- [ ] Với ZIP không tin cậy: chặn path traversal/symlink, giới hạn entry, tổng byte, CPU/thời gian và không ghi đè ngoài ý muốn.
- [ ] Kiểm thử trên dữ liệu thật: tệp lớn hơn 4 GiB, số mục nhiều hơn 65.535, ZIP bị cắt, dữ liệu nén rất mạnh, tên Unicode và hệ thống đích.

## Tài liệu tham khảo

- [PKWARE — ZIP File Format Specification (APPNOTE, bản cập nhật chính thức)](https://www.pkware.com/documents/casestudies/APPNOTE.TXT)
- [Oracle Java SE — `java.util.zip` package](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/zip/package-summary.html)
- [Oracle Java SE — `ZipOutputStream`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/zip/ZipOutputStream.html)
- [Oracle Java SE — `ZipInputStream`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/zip/ZipInputStream.html)
- [Oracle Java SE — `ZipFile`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/zip/ZipFile.html)
- [Oracle Java SE — `ZipEntry`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/zip/ZipEntry.html)
- [OWASP WSTG — Upload of Malicious Files (archive traversal và ZIP bombs)](https://wstg.owasp.org/latest/4-Web_Application_Security_Testing/10-Business_Logic/09-Upload_of_Malicious_Files/)
