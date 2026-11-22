# Kiểm tra dữ liệu hỏng và kích thước đầu ra khi đọc luồng ZIP trong Java

## 1. Mục tiêu

Khi xử lý tệp `.zip`, ứng dụng cần kiểm tra **hai vấn đề độc lập**:

1. **Tính toàn vẹn dữ liệu (integrity):** nội dung mỗi entry có đọc và giải nén được không, có khớp CRC-32 và kích thước mà định dạng ZIP khai báo hay không?
2. **Kích thước đầu ra sau giải nén (decompressed output size):** số byte thực tế được giải nén có nằm trong ngân sách cho phép hay không, kể cả khi đầu vào nén rất nhỏ?

Ví dụ, một tệp ZIP 2 MB có thể mở rộng thành hàng trăm MB hoặc nhiều GB. Kiểm tra `Files.size(archive)` hay `ZipEntry.getCompressedSize()` **không thay thế** việc đếm số byte *sau giải nén*. Ngược lại, đếm byte không tự xác nhận CRC hay tính hợp lệ của toàn bộ cấu trúc ZIP.

Bài này sử dụng các API vẫn được hỗ trợ trong Java hiện đại: `ZipInputStream`, `ZipOutputStream`, `ZipEntry`, `ZipException`, `ZipFile`, `CRC32`, `InputStream` và try-with-resources. Đây là các khả năng chuẩn của `java.util.zip`, có thể áp dụng cho ứng dụng Java ngày nay.

## 2. Dữ liệu ZIP có thể hỏng ở đâu?

Một entry ZIP thường có dữ liệu và metadata như tên, phương pháp nén, kích thước trước/sau nén và CRC-32. Những trường này có thể nằm trong local file header, data descriptor và central directory tùy cách tạo ZIP.

| Tín hiệu | Ý nghĩa khi kiểm tra | Giới hạn cần nhớ |
| --- | --- | --- |
| `ZipEntry.getSize()` | Kích thước **không nén** được khai báo | Có thể là `-1` khi chưa biết; không lấy làm giới hạn đọc |
| `ZipEntry.getCompressedSize()` | Kích thước dữ liệu **đã nén** được khai báo | Có thể là `-1` khi đọc theo luồng; không phải kích thước đầu ra |
| `ZipEntry.getCrc()` | CRC-32 của nội dung giải nén được khai báo | Có thể là `-1` trước khi biết; CRC không phải chữ ký hay mã xác thực |
| `CRC32.update(...)` / `getValue()` | CRC-32 tính trên byte **thực tế đã giải nén** | Phát hiện nhiều lỗi tình cờ, không chống kẻ cố ý sửa dữ liệu và cập nhật CRC |
| Tổng số byte trả về từ `read(...)` | Kích thước đầu ra đo được | Phải cộng theo **từng entry** và **toàn archive** |
| `ZipException` / `IOException` | Lỗi cấu trúc, dữ liệu nén, CRC, kết thúc luồng hoặc I/O | Không phải mọi ZIP hỏng đều bị `ZipInputStream` phát hiện |

**Điểm mấu chốt:** metadata ZIP là **đầu vào chưa đáng tin**. Hãy đọc từng khối có giới hạn, đếm byte thực tế, rồi đối chiếu thông tin khai báo khi có. Nếu kết quả không đáp ứng quy tắc của ứng dụng, hãy từ chối archive.

### CRC-32 giúp được gì?

CRC-32 là checksum 32-bit của nội dung entry trước khi nén. Trong tình huống lưu trữ/truyền tải thông thường, sai khác CRC thường cho thấy byte hỏng hoặc không khớp với metadata. Với các entry `STORED` và `DEFLATED` do `ZipInputStream` hỗ trợ, Java thực hiện kiểm tra liên quan đến kích thước/CRC khi đọc entry đến kết thúc; lỗi có thể xuất hiện ngay tại lời gọi `read(...)` hoặc khi tiêu thụ nốt entry bằng `closeEntry()`.

Không được coi `CRC32` là cơ chế bảo mật: một người tạo ZIP độc hại có thể thay cả dữ liệu lẫn CRC. Với yêu cầu xác minh nguồn gốc/chống sửa đổi có chủ đích, dùng hash/chữ ký số hoặc cơ chế xác thực từ một kênh tin cậy, ngoài việc kiểm tra ZIP.

## 3. Quy trình đọc an toàn bằng ZipInputStream

Quy trình thích hợp với ZIP từ tệp hoặc luồng mạng:

1. **Giới hạn kích thước đầu vào nén** trước khi nhận/lưu archive. Với tệp đã lưu, có thể dùng `Files.size(path)` để chặn đầu vào quá lớn; với network stream, phải đếm cả byte nguồn.
2. Dùng `ZipInputStream` và lặp `getNextEntry()`; giới hạn **số lượng entry** để tránh archive chứa quá nhiều tệp nhỏ.
3. Đọc mỗi entry bằng bộ đệm kích thước cố định (ví dụ 8 KiB). Cộng byte thực nhận sau giải nén vào `entryBytes` và `totalBytes`, kiểm tra giới hạn **trước khi tăng bộ đếm**.
4. Cập nhật `CRC32` trên chính byte vừa đọc. Tiêu thụ entry đến EOF (`read(...) == -1`) để bộ máy ZIP có cơ hội hoàn tất kiểm tra checksum/kích thước.
5. Đối chiếu `ZipEntry.getSize()` và `getCrc()` khi các giá trị này đã biết (`>= 0`). Gọi `closeEntry()`, rồi chuyển entry tiếp theo.
6. Từ chối ngay khi gặp lỗi giải nén, CRC, kích thước hoặc ngân sách; đóng luồng bằng try-with-resources. Chỉ dùng kết quả/đầu ra sau khi toàn bộ bước kiểm tra theo chính sách đã hoàn thành.

Không dùng `InputStream.available()` để ước tính tổng byte: nó **không** biểu thị kích thước đã giải nén. Không gọi `readAllBytes()` hoặc `transferTo(...)` không giới hạn với ZIP không tin cậy, vì có thể cấp phát bộ nhớ/ghi quá nhiều dữ liệu trước khi biết kích thước.

## 4. Ví dụ Java độc lập: ZIP hợp lệ, quá giới hạn và hỏng CRC

Ví dụ này chạy không cần tải một tệp ZIP bên ngoài. Chương trình tự tạo entry `STORED` chứa `hello`, đọc kiểm tra, thử giới hạn đầu ra nhỏ hơn nội dung, rồi thay một byte payload để mô phỏng dữ liệu hỏng. Cuối cùng, nếu truyền đường dẫn `.zip` trên dòng lệnh, chương trình quét một archive thật bằng luồng tệp.

Tạo file **`ZipSafetyDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.zip.CRC32;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;
import java.util.zip.ZipOutputStream;

public class ZipSafetyDemo {
    static final long MAX_INPUT_BYTES = 10L * 1024 * 1024;
    static final long MAX_ENTRY_BYTES = 20L * 1024 * 1024;
    static final long MAX_TOTAL_BYTES = 100L * 1024 * 1024;
    static final int MAX_ENTRIES = 500;

    static long scan(InputStream compressed, long entryLimit,
                     long totalLimit, int entryLimitCount)
            throws IOException {

        if (entryLimit <= 0 || totalLimit <= 0 || entryLimitCount <= 0) {
            throw new IllegalArgumentException("limits must be positive");
        }

        byte[] buffer = new byte[8192];
        long total = 0;
        int entries = 0;

        // Đóng ZipInputStream sẽ đóng luôn compressed.
        try (ZipInputStream zin = new ZipInputStream(compressed)) {
            ZipEntry entry;
            while ((entry = zin.getNextEntry()) != null) {
                if (++entries > entryLimitCount) {
                    throw new IOException("entry count limit exceeded");
                }

                long size = 0;
                CRC32 crc = new CRC32();
                int read;

                while ((read = zin.read(buffer)) != -1) {
                    // So sánh kiểu trừ để tránh overflow khi cộng.
                    if (read > entryLimit - size) {
                        throw new IOException("entry output limit exceeded");
                    }
                    if (read > totalLimit - total) {
                        throw new IOException("total output limit exceeded");
                    }

                    size += read;
                    total += read;
                    crc.update(buffer, 0, read);
                }

                // Metadata có thể là -1 nếu chưa/không biết.
                if (entry.getSize() >= 0 && entry.getSize() != size) {
                    throw new IOException("declared size mismatch");
                }
                if (entry.getCrc() >= 0
                        && entry.getCrc() != crc.getValue()) {
                    throw new IOException("declared CRC mismatch");
                }

                zin.closeEntry();
            }
        }

        // Chính sách ví dụ: không chấp nhận ZIP không có entry.
        if (entries == 0) {
            throw new IOException("empty or malformed ZIP");
        }

        System.out.printf("OK: %d entries, %d bytes%n", entries, total);
        return total;
    }

    // Tạo ZIP STORED để minh họa byte payload và CRC.
    static byte[] makeStoredZip(String text) throws IOException {
        byte[] content = text.getBytes(StandardCharsets.UTF_8);
        CRC32 crc = new CRC32();
        crc.update(content);

        ByteArrayOutputStream out = new ByteArrayOutputStream();
        try (ZipOutputStream zout = new ZipOutputStream(out)) {
            ZipEntry entry = new ZipEntry("note.txt");
            entry.setMethod(ZipEntry.STORED);
            entry.setSize(content.length);
            entry.setCompressedSize(content.length);
            entry.setCrc(crc.getValue());

            zout.putNextEntry(entry);
            zout.write(content);
            zout.closeEntry();
        }
        return out.toByteArray();
    }

    // Chỉ dành cho demo STORED; cố ý sửa byte payload.
    static byte[] corruptStoredPayload(byte[] zip, byte[] target) {
        byte[] modified = zip.clone();
        for (int i = 0; i <= modified.length - target.length; i++) {
            boolean match = true;
            for (int j = 0; j < target.length; j++) {
                if (modified[i + j] != target[j]) {
                    match = false;
                    break;
                }
            }
            if (match) {
                modified[i] ^= 1;
                return modified;
            }
        }
        throw new IllegalStateException("payload not found");
    }

    public static void main(String[] args) throws IOException {
        if (args.length == 1) {
            Path path = Paths.get(args[0]);

            // Giới hạn byte của archive nén trên đĩa.
            if (Files.size(path) > MAX_INPUT_BYTES) {
                throw new IOException("ZIP input limit exceeded");
            }

            scan(Files.newInputStream(path),
                    MAX_ENTRY_BYTES, MAX_TOTAL_BYTES, MAX_ENTRIES);
            return;
        }

        if (args.length != 0) {
            throw new IllegalArgumentException(
                    "Usage: java ZipSafetyDemo [file.zip]");
        }

        byte[] zip = makeStoredZip("hello");

        scan(new ByteArrayInputStream(zip), 100, 200, 10);

        try {
            scan(new ByteArrayInputStream(zip), 3, 200, 10);
        } catch (IOException ex) {
            System.out.println("REJECTED limit: " + ex.getMessage());
        }

        byte[] damaged = corruptStoredPayload(
                zip, "hello".getBytes(StandardCharsets.UTF_8));

        try {
            scan(new ByteArrayInputStream(damaged), 100, 200, 10);
        } catch (IOException ex) {
            System.out.println("REJECTED corrupt: "
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 ZipSafetyDemo.java
java ZipSafetyDemo
```

**Đầu ra đã kiểm tra:**

```text
OK: 1 entries, 5 bytes
REJECTED limit: entry output limit exceeded
REJECTED corrupt: ZipException
```

- Lần đầu: một entry có 5 byte không nén, cả kích thước lẫn CRC hợp lệ.
- Lần hai: `entryLimit = 3`, nhưng bộ giải nén trả 5 byte; chương trình từ chối **trước khi cộng vượt giới hạn**.
- Lần ba: byte dữ liệu đã bị sửa trong khi CRC lưu trong ZIP giữ nguyên; `ZipInputStream` phát hiện lỗi và ném `ZipException` khi đọc hết entry. Tên/thông điệp lỗi cụ thể có thể khác tùy kiểu hỏng dữ liệu và JDK; ví dụ chỉ in ra lớp exception.

Quét tệp thực:

```bash
java ZipSafetyDemo archive.zip
```

Đối với tệp bên ngoài, chương trình giới hạn archive nén 10 MiB, mỗi entry đầu ra 20 MiB, tổng đầu ra 100 MiB và tối đa 500 entry. Đây là **giá trị minh họa**, cần điều chỉnh theo nghiệp vụ/tài nguyên thực tế. Kết quả khi quét tệp bên ngoài phụ thuộc nội dung, ví dụ `OK: 3 entries, 1800 bytes` nếu có ba entry hợp lệ với tổng 1.800 byte không nén.

### Vì sao dùng STORED trong phần mô phỏng hỏng dữ liệu?

`STORED` lưu payload nguyên dạng, giúp ta sửa đúng một byte rồi quan sát CRC mismatch một cách xác định. Khi tạo `ZipEntry.STORED` bằng `ZipOutputStream`, phải đặt size, compressed size và CRC trước `putNextEntry()`. Với `DEFLATED`, Java có thể tính metadata trong quá trình ghi; quy trình kiểm tra kích thước đầu ra ở `scan(...)` vẫn áp dụng như nhau.

## 5. Điều gì có thể và không thể được xác nhận từ ZIP stream?

`ZipInputStream` duyệt **local entry headers** theo thứ tự trong luồng. Một entry được đọc thành công có thể có CRC và kích thước đúng mà **central directory** hoặc phần kết thúc archive vẫn thiếu/hỏng. Chẳng hạn, nếu cắt bỏ phần central directory của một ZIP sau khi dữ liệu entry đã hoàn chỉnh, `ZipInputStream` vẫn có thể đọc được entry và kết thúc mà không báo lỗi. Do đó:

- **Quét toàn bộ byte giải nén qua `ZipInputStream`** phù hợp để phát hiện nhiều lỗi ở payload và kiểm soát số byte đầu ra; không kết luận rằng toàn bộ cấu trúc ZIP hợp lệ chỉ từ kết quả này.
- **`ZipFile`** đọc archive dựa trên central directory, phù hợp khi cần duyệt ngẫu nhiên các entry và yêu cầu archive có cấu trúc directory đọc được. Tuy nhiên, đừng mặc định việc tạo `ZipFile` hoặc gọi `getInputStream(entry)` đã kiểm tra toàn bộ CRC của tất cả entry.
- Khi cần kiểm tra nghiêm ngặt, phải thiết kế kiểm tra cả **cấu trúc archive** lẫn **nội dung từng entry**: mở bằng `ZipFile` để xác minh khả năng truy cập central directory, đọc đầy đủ mọi entry, tự đếm output, tự tính CRC/đối chiếu kích thước và áp dụng giới hạn. Việc tồn tại central directory cũng không biến CRC thành xác thực mật mã.

**Điểm phân biệt:** một ZIP có nhiều entry không thể được coi là hợp lệ chỉ vì entry đầu tiên đã giải nén thành công. Không bỏ qua exception, không dừng sớm sau vài byte rồi đánh dấu `PASS`, và không dùng thông tin từ một entry để đại diện toàn bộ archive.

## 6. Giới hạn output size và phòng tránh ZIP bomb

Một **ZIP bomb** là archive có tỷ lệ nén lớn hoặc cấu trúc gây chi phí giải nén quá mức. Một số ZIP có rất nhiều entry nhỏ; một số chứa dữ liệu nén thành đầu ra cực lớn; một số chứa ZIP lồng nhau nếu ứng dụng tự giải nén đệ quy.

Nên thiết lập các giới hạn độc lập:

| Giới hạn | Ví dụ bảo vệ | Cách kiểm tra thực tế |
| --- | --- | --- |
| Dung lượng archive nén đầu vào | Chặn upload/network stream quá lớn | Đếm byte nhận hoặc `Files.size` cho tệp ổn định |
| Byte giải nén của **mỗi entry** | Chặn một tệp quá lớn | Cộng số byte `read(...)` trả về trong entry |
| Tổng byte giải nén của **toàn ZIP** | Chặn nhiều entry cộng lại quá lớn | Cộng `read(...)` qua mọi entry |
| **Số lượng entry** | Chặn hàng chục nghìn file cực nhỏ | Đếm mỗi lần `getNextEntry()` trả entry |
| Thời gian/CPU, độ sâu lồng nhau | Tránh công việc quá lâu hoặc giải nén đệ quy vô hạn | Giới hạn tài nguyên/tác vụ ở tầng ứng dụng và các lần giải nén phụ |

Số byte **thực tế** mới là điều kiện quyết định. Không dùng kiểu kiểm tra sau làm chốt duy nhất:

```java
// KHÔNG đủ an toàn cho đầu vào không đáng tin:
if (entry.getSize() <= MAX_ENTRY_BYTES) {
    // entry.getSize() có thể bằng -1 hoặc là metadata chưa đáng tin.
    byte[] all = zipInputStream.readAllBytes(); // Có thể cấp phát quá nhiều RAM.
}
```

Thay vào đó đọc từng chunk có giới hạn như `scan(...)`. Nếu cần **trích xuất ra đĩa**, không ghi quá giới hạn rồi mới xóa: kiểm tra byte trước khi ghi, sử dụng nơi lưu tạm được kiểm soát, dọn phần đã ghi nếu bị từ chối, rồi mới chuyển kết quả đã xác thực vào vị trí sử dụng. Bảo vệ đường dẫn entry để tránh **ZIP Slip** (ví dụ `../`, đường dẫn tuyệt đối), tránh ghi theo symlink hoặc ghi đè tệp ngoài thư mục đích; kiểm tra này riêng với CRC và giới hạn output.

Giới hạn byte không thay thế giới hạn CPU/time. Với ZIP nén cực mạnh, phần mềm vẫn cần khoảng thời gian và tài nguyên để giải nén đến ngưỡng byte. Giới hạn thời gian chạy/tài nguyên nên được thi hành ở tầng xử lý tác vụ khi nhận đầu vào không tin cậy. Tỷ lệ nén từ metadata chỉ có thể là **tín hiệu bổ trợ**, vì kích thước nén hoặc không nén có thể chưa biết hoặc không đáng tin lúc đang đọc.

## 7. Xử lý lỗi và trạng thái kết quả

| Trường hợp | Biểu hiện có thể gặp | Cách phản ứng |
| --- | --- | --- |
| Payload bị sửa, CRC không khớp | `ZipException` hoặc kiểm tra CRC thủ công thất bại | Từ chối entry và archive, thông báo lỗi dữ liệu |
| Dữ liệu nén bị cắt/không thể giải nén | `EOFException`, `ZipException` hoặc `IOException` khi đọc | Từ chối, đóng luồng; không dùng bản trích xuất một phần |
| Kích thước khai báo khác dữ liệu thực | Exception khi đọc đến cuối hoặc giá trị tự tính khác `getSize()` | Từ chối |
| Một entry giải nén vượt ngưỡng | `entry output limit exceeded` trong ví dụ | Hủy thao tác, không tiếp tục ghi output |
| Tổng entry cộng lại vượt ngưỡng | `total output limit exceeded` | Hủy thao tác trên toàn archive |
| Quá nhiều entry | `entry count limit exceeded` | Hủy thao tác |
| Thiếu central directory nhưng local entries còn đọc được | `ZipInputStream` có thể không phát hiện | Dùng kiểm tra cấu trúc bổ sung qua `ZipFile` nếu yêu cầu |
| Archive rỗng | `getNextEntry()` trả `null` ngay | Quyết định chính sách rõ ràng; ví dụ chủ động từ chối |

Với hệ thống phục vụ người dùng, phân loại phản hồi lỗi hữu ích hơn việc hiển thị stack trace: chẳng hạn `INVALID_ZIP`, `ZIP_SIZE_LIMIT` và `ZIP_TOO_MANY_ENTRIES`; ghi log kỹ thuật an toàn ở backend, tránh trả về tên tệp/đường dẫn nhạy cảm. Lưu ý là các exception có thể khác theo phương pháp nén và vị trí byte hỏng; không viết logic nghiệp vụ chỉ dựa trên **nội dung thông điệp exception** của JDK.

## 8. Đảm bảo tệp ZIP được tạo hoàn chỉnh

Ở phía ghi, một entry phải được kết thúc bằng `ZipOutputStream.closeEntry()` sau khi ghi toàn bộ dữ liệu. `ZipOutputStream.close()` hoàn thiện cấu trúc ZIP và đóng tài nguyên (bao gồm central directory); `flush()` **không thay thế** bước hoàn thiện archive. Try-with-resources bảo đảm đóng ngay cả khi có ngoại lệ.

Nếu ghi ZIP ra tệp nhưng gặp lỗi giữa chừng, không công bố tệp đó là một archive thành công. Mẫu xử lý thường là ghi vào tệp tạm, hoàn tất/đóng `ZipOutputStream`, xác nhận tệp tạm, rồi chuyển vào vị trí đích. Dữ liệu chưa hoàn tất có thể chỉ có local entries và thiếu central directory, khiến các cách đọc ZIP khác nhau đưa ra kết quả khác nhau.

## 9. Tự kiểm tra

1. **ZIP nén 1 MiB, đầu ra 500 MiB; giới hạn đầu ra 50 MiB.** Có được đọc cả 500 MiB rồi mới từ chối không? **Không.** Dừng ngay khi lượng byte trả về từ `read` làm vượt giới hạn, và không cung cấp dữ liệu đã trích xuất một phần.
2. **`getSize() == -1` trong lúc đọc entry.** Có nên coi đây là lỗi dữ liệu? **Không nhất thiết.** Metadata có thể chưa sẵn có khi đọc theo luồng; đo kích thước thực tế và kiểm tra khi metadata trở nên khả dụng.
3. **CRC đúng thì tệp chắc chắn an toàn?** **Không.** CRC phát hiện lỗi tình cờ, không ngăn mã độc, ZIP Slip, lạm dụng tài nguyên hoặc sự chỉnh sửa có chủ đích.
4. **`ZipInputStream` đọc xong một entry mà không lỗi nghĩa là ZIP có central directory hợp lệ?** **Không.** Kiểm tra cấu trúc archive bằng công cụ/API phù hợp nếu nghiệp vụ yêu cầu.
5. **ZIP chứa 1.000 tệp, mỗi tệp 1 KiB.** Giới hạn từng entry 2 KiB đã đủ chưa? **Chưa.** Phải giới hạn thêm số entry và tổng output; cân nhắc chi phí hệ thống tệp khi trích xuất.

### Tài liệu API chính thức

- [`ZipInputStream` — đọc entry theo luồng](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/zip/ZipInputStream.html)
- [`ZipEntry` — size, compressed size và CRC](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/zip/ZipEntry.html)
- [`ZipFile` — truy cập entry theo central directory](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/zip/ZipFile.html)
- [`CRC32` — checksum](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/zip/CRC32.html)
- [`ZipOutputStream` — hoàn tất entry và ZIP](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/zip/ZipOutputStream.html)
