# Chọn `ZipFile` hay các luồng đọc/ghi ZIP trong Java

## 1. Mục tiêu và phạm vi

ZIP là định dạng lưu trữ gồm nhiều *entry* (tệp hoặc thư mục), có thể nén từng entry. Khi làm việc với ZIP trong Java, hãy chọn API dựa trên **nguồn dữ liệu** và **cách cần truy cập**, thay vì chỉ dựa vào đuôi `.zip`.

Bài này dùng `java.util.zip`, `java.io` và `java.nio.file` còn được hỗ trợ trên Java hiện đại; ví dụ hoàn chỉnh chạy với **Java 17 trở lên**. Các API `ZipFile`, `ZipInputStream`, `ZipOutputStream` và `ZipEntry` vẫn thích hợp cho ứng dụng mới. Không dùng thư viện nội bộ `sun.*`, cách đóng tài nguyên thủ công dễ rò rỉ, hoặc kỹ thuật đã lỗi thời.

Sau bài học, bạn cần phân biệt được đọc ZIP theo tên entry với đọc tuần tự, hiểu chi phí I/O và bộ nhớ, tạo ZIP bằng luồng ghi, xử lý charset, đóng tài nguyên và bảo vệ ứng dụng khi nhận ZIP từ bên ngoài.

## 2. Chọn API theo tình huống

| Nhu cầu | Nên chọn | Lý do |
| --- | --- | --- |
| Có **tệp ZIP trên đĩa** và muốn tìm `images/logo.png` theo tên, chọn một vài entry hoặc truy cập lại nhiều lần | `ZipFile` | Đọc danh mục ZIP (central directory) và lấy entry theo tên; không cần giải nén tuần tự mọi entry trước đó |
| Có **`InputStream`** từ HTTP upload, mạng hoặc một nguồn dữ liệu một chiều; xử lý từng entry theo thứ tự | `ZipInputStream` | Đọc ZIP tuần tự từ luồng byte, không bắt buộc có tệp ZIP trên đĩa |
| Muốn **tạo ZIP mới** để lưu xuống đĩa hoặc gửi qua HTTP | `ZipOutputStream` | Ghi từng `ZipEntry`, nén dữ liệu và hoàn tất cấu trúc ZIP khi đóng |
| Cần duyệt, sao chép, sửa nội dung archive như một hệ tệp | Cân nhắc ZIP File System (`FileSystems.newFileSystem`) | Dùng giao diện `Path`/`Files` khi thao tác hệ tệp hợp lý hơn; không cần cho việc chỉ đọc một vài entry |

**Quy tắc nhớ nhanh:** cần đọc tùy ý từ một *file* → `ZipFile`; cần xử lý một *stream* đầu vào theo thứ tự → `ZipInputStream`; cần *tạo* ZIP → `ZipOutputStream`. Không có một API duy nhất tốt nhất cho mọi trường hợp.

Một ZIP có thể chứa entry thư mục (thường có tên kết thúc bằng `/`) và entry tệp. `ZipEntry` cung cấp tên, cờ thư mục và một số thông tin như kích thước, CRC; nó **không chứa sẵn toàn bộ byte đã giải nén**.

## 3. `ZipFile`: đọc các entry từ tệp ZIP có sẵn

`ZipFile` mở tệp ZIP trên hệ tệp và sử dụng danh mục ở cuối archive để xác định entry. Các thao tác tiêu biểu:

- `getEntry("path/in/zip.txt")`: tra cứu theo tên, trả `null` nếu không có.
- `entries()` hoặc `stream()`: liệt kê các entry; đây là duyệt **metadata**, chưa có nghĩa đã đọc hết nội dung tệp bên trong.
- `getInputStream(entry)`: mở luồng để đọc byte đã giải nén của đúng entry.
- `close()`: giải phóng tài nguyên và đóng các luồng entry liên quan.

`ZipFile` thuận tiện khi ứng dụng đọc một tệp cấu hình trong bản ZIP rất lớn, cần hiển thị danh sách tệp, hoặc lặp lại việc truy xuất nhiều entry. Truy cập tùy ý ở đây là **theo entry**; không đồng nghĩa có thể nhảy đến vị trí bất kỳ trong nội dung *đã giải nén* của một entry.

Mẫu thường gặp:

```java
try (ZipFile zip = new ZipFile(zipPath.toFile(), StandardCharsets.UTF_8)) {
    ZipEntry entry = zip.getEntry("config/app.properties");
    if (entry == null || entry.isDirectory()) {
        throw new FileNotFoundException("Thiếu config/app.properties trong ZIP");
    }
    try (InputStream in = zip.getInputStream(entry)) {
        // Đọc entry bằng bộ đệm hoặc chuyển sang OutputStream.
        in.transferTo(destination);
    }
}
```

Đây là **đoạn minh họa**, giả định `zipPath` và `destination` đã được khai báo, `destination` do caller quản lý. Khi đọc dữ liệu không tin cậy, phải giới hạn số byte được giải nén; `transferTo` không tự áp đặt hạn mức.

**Giới hạn:** `ZipFile` cần một tệp để mở (qua `File` hoặc đường dẫn dạng chuỗi), không nhận trực tiếp một `InputStream` tùy ý; nó cũng không phải API để thêm entry và ghi lại ZIP.

## 4. `ZipInputStream`: đọc tuần tự từ một luồng byte

`ZipInputStream` bọc một `InputStream` có nội dung định dạng ZIP. Với mỗi vòng lặp:

1. `getNextEntry()` chuyển tới entry kế tiếp; trả `null` khi hết.
2. Kiểm tra `entry.isDirectory()` trước khi xử lý dữ liệu tệp.
3. Gọi `read(...)` để đọc **nội dung của entry hiện tại** đến `-1`; chuyển byte sang nơi xử lý hoặc lưu trữ.
4. `closeEntry()` kết thúc entry hiện tại trước khi chuyển tiếp.

Điểm quan trọng là `ZipInputStream` **không tra cứu trực tiếp theo tên**. Muốn tìm `config/app.properties`, bạn phải duyệt các entry cho đến khi gặp nó; những entry phía trước vẫn được đọc/bỏ qua theo thứ tự. Nếu yêu cầu liên tục truy vấn nhiều entry trong cùng tệp, thường nên dùng `ZipFile`.

Trong lúc đọc tuần tự, metadata của entry có thể **chưa đầy đủ**: `getSize()` và `getCompressedSize()` có thể trả `-1` vì thông tin chưa có trong phần header đang đọc. Không dùng các giá trị này làm giới hạn bảo mật duy nhất; hãy **đếm byte giải nén thực tế** khi đọc.

`ZipInputStream` đặc biệt hữu ích khi server nhận ZIP qua `InputStream` rồi xử lý từng tệp một lần, hoặc khi dữ liệu nguồn không hỗ trợ truy cập ngẫu nhiên. Nếu nghiệp vụ cần tìm nhiều entry theo tên hoặc tái sử dụng archive, có thể lưu luồng đầu vào thành một tệp tạm **có hạn mức dung lượng**, rồi mở bằng `ZipFile`.

## 5. `ZipOutputStream`: tạo ZIP theo từng entry

`ZipOutputStream` bọc `OutputStream` đích. Với mỗi tệp cần đưa vào archive:

1. Tạo `ZipEntry` với **tên tương đối bên trong ZIP**, ưu tiên dấu `/`.
2. Gọi `putNextEntry(entry)`.
3. Ghi byte bằng `write(...)` hoặc `InputStream.transferTo(zipOut)`.
4. Gọi `closeEntry()`; lặp lại cho entry khác.
5. Gọi `close()` (qua try-with-resources) để ghi hoàn chỉnh cấu trúc ZIP và giải phóng tài nguyên.

Ví dụ tên entry hợp lệ: `docs/readme.txt`, `photos/2026/photo.jpg`. Tên entry **không phải** đường dẫn đích tuyệt đối; tránh đưa đường dẫn máy chủ hay bí mật vào archive.

`ZipOutputStream` không chỉnh sửa trực tiếp một `ZipFile` đang mở. Khi cần thay đổi nội dung của ZIP, cách đơn giản, an toàn là tạo một ZIP mới chứa các entry mong muốn, kiểm tra xong mới thay thế archive cũ; hoặc cân nhắc ZIP File System nếu yêu cầu và môi trường phù hợp.

Đóng `ZipOutputStream` cũng sẽ đóng `OutputStream` được bọc. Nếu caller còn sở hữu và cần tiếp tục dùng luồng bên dưới (ví dụ response stream), hãy thiết kế hợp đồng quản lý tài nguyên rõ ràng; đừng mặc định đóng một luồng do thành phần khác quản lý.

## 6. Ví dụ chạy được: tạo một ZIP rồi đọc bằng hai cách

Chương trình sau tạo một archive nhỏ, đọc trực tiếp entry theo tên bằng `ZipFile`, rồi đọc tuần tự từ cùng tệp bằng `ZipInputStream`. Nó dùng `readAllBytes()` **chỉ để in một chuỗi rất nhỏ**; với dữ liệu lớn, hãy đọc theo khối như phần tiếp theo.

Lưu thành **`ZipChoiceDemo.java`**:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import java.util.zip.ZipInputStream;
import java.util.zip.ZipOutputStream;

public class ZipChoiceDemo {
    public static void main(String[] args) throws IOException {
        Path archive = Files.createTempFile("zip-choice-", ".zip");

        try {
            // A. Tạo ZIP chứa một thư mục và một tệp.
            try (ZipOutputStream out = new ZipOutputStream(
                    Files.newOutputStream(archive), StandardCharsets.UTF_8)) {
                out.putNextEntry(new ZipEntry("docs/"));
                out.closeEntry();

                out.putNextEntry(new ZipEntry("docs/readme.txt"));
                out.write("Xin chào ZIP!\n".getBytes(StandardCharsets.UTF_8));
                out.closeEntry();
            }

            // B. Đọc trực tiếp một entry theo tên.
            try (ZipFile zip = new ZipFile(archive.toFile(), StandardCharsets.UTF_8)) {
                ZipEntry entry = zip.getEntry("docs/readme.txt");
                if (entry == null) {
                    throw new IOException("Không tìm thấy docs/readme.txt");
                }
                try (InputStream in = zip.getInputStream(entry)) {
                    String text = new String(in.readAllBytes(), StandardCharsets.UTF_8);
                    System.out.println("ZipFile: " + text.strip());
                }
            }

            // C. Đọc tuần tự từ InputStream chứa ZIP.
            try (ZipInputStream in = new ZipInputStream(
                    Files.newInputStream(archive), StandardCharsets.UTF_8)) {
                ZipEntry entry;
                while ((entry = in.getNextEntry()) != null) {
                    if (!entry.isDirectory()) {
                        String text = new String(in.readAllBytes(), StandardCharsets.UTF_8);
                        System.out.println("ZipInputStream: "
                                + entry.getName() + " -> " + text.strip());
                    }
                    in.closeEntry();
                }
            }
        } finally {
            Files.deleteIfExists(archive);
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ZipChoiceDemo.java
java ZipChoiceDemo
```

Kết quả chuẩn:

```text
ZipFile: Xin chào ZIP!
ZipInputStream: docs/readme.txt -> Xin chào ZIP!
```

Trong bước B, `getEntry` tìm entry trực tiếp nhờ danh mục archive. Trong bước C, chương trình đi qua `docs/` rồi mới đến `docs/readme.txt` theo thứ tự của luồng. Cả hai đều giải nén nội dung khi thực sự đọc; không cần giải nén toàn bộ ZIP ra thư mục trước.

## 7. Đọc dữ liệu lớn mà không giữ hết trong RAM

Với entry lớn, tránh `readAllBytes()` và tránh chuyển mọi nội dung thành `String`. Dùng bộ đệm cố định, ví dụ:

```java
// Mảnh mã: in là InputStream của entry hiện tại,
// out là OutputStream đích đã mở; caller quản lý việc đóng hai luồng.
byte[] buffer = new byte[8192];
int n;
while ((n = in.read(buffer)) != -1) {
    out.write(buffer, 0, n);
}
```

Mẫu này áp dụng với `ZipFile.getInputStream(entry)` lẫn `ZipInputStream` khi đang ở trong một entry. Bộ đệm ~8 KiB giúp tránh cấp phát theo kích thước tệp; bộ nhớ tiêu thụ **không phụ thuộc tuyến tính vào kích thước entry** nếu bản thân nơi nhận cũng xử lý theo luồng.

Trước khi chọn API, cân nhắc I/O và số lần đọc:

- Chỉ cần một entry trong một ZIP nằm trên đĩa: `ZipFile` thường tiết kiệm việc quét những entry không liên quan.
- Muốn xử lý toàn bộ các entry **một lần** khi dữ liệu đến qua mạng: `ZipInputStream` tự nhiên hơn, có thể không cần lưu archive tạm.
- Cần tạo file tải về: `ZipOutputStream` ghi ZIP trực tiếp tới đích, nhưng phải nghĩ đến điều gì xảy ra nếu xử lý lỗi ở giữa hoặc phía nhận ngắt kết nối.
- Khi kích thước lớn: cả ba đều có thể kết hợp `InputStream`/`OutputStream` và bộ đệm, miễn là không tự gom tất cả byte vào bộ nhớ.

## 8. An toàn và tính đúng đắn với ZIP từ nguồn không tin cậy

### 8.1. Chặn Zip Slip trước khi giải nén ra đĩa

Tên `ZipEntry` do bên gửi quyết định. Nếu nối trực tiếp `../../outside.txt` vào thư mục đích, chương trình có thể ghi ra ngoài thư mục được phép. Kiểm tra đường dẫn **trước khi tạo file/thư mục**:

```java
// Mảnh mã: destinationRoot và entry có sẵn trong hàm giải nén.
// Chỉ xử lý được tên đường dẫn; xem thêm lưu ý symlink bên dưới.
Path root = destinationRoot.toAbsolutePath().normalize();
Path output = root.resolve(entry.getName()).normalize();
if (!output.startsWith(root)) {
    throw new IOException("ZIP entry nằm ngoài thư mục đích: " + entry.getName());
}
```

Đây là lớp kiểm tra **cần thiết nhưng chưa đủ** khi thư mục đích có sẵn symbolic link hoặc bị tiến trình khác thay đổi. Với archive không tin cậy, nên giải nén vào thư mục mới, riêng biệt, kiểm soát symlink và quyền ghi, tránh ghi đè tệp hiện có, rồi mới chuyển các tệp đã kiểm tra tới nơi sử dụng. Cần xét cả đường dẫn tuyệt đối, ký tự đặc biệt, tên trùng nhau và khác biệt của hệ điều hành đích.

### 8.2. Giới hạn tài nguyên để giảm rủi ro ZIP bomb

ZIP nhỏ ở dạng nén có thể bung ra thành dữ liệu khổng lồ. Áp đặt hạn mức phù hợp nghiệp vụ cho **số entry**, **tổng byte đầu vào**, **số byte giải nén từng entry**, **tổng byte giải nén** và thời gian xử lý. Đếm byte **khi đọc** thay vì chỉ dựa vào `entry.getSize()` (có thể chưa biết hoặc không đáng tin), đồng thời hủy và dọn file tạm khi vượt giới hạn. Với các luồng từ mạng còn cần giới hạn request/timeout theo tầng ứng dụng.

Khi phát hiện archive lỗi, không chấp nhận đầu ra giải nén một phần như dữ liệu hợp lệ. Dùng thư mục tạm, chỉ công bố kết quả sau khi đọc và xác minh hoàn tất.

### 8.3. Charset, tên entry, quyền sở hữu luồng

- Mặc định hiện nay là **UTF-8** cho tên entry; có thể truyền `StandardCharsets.UTF_8` một cách tường minh khi đọc/ghi. Nếu nhận archive tạo bằng bộ mã khác, chỉ chọn `Charset` tương ứng khi thực sự biết nguồn mã; một số ZIP đặt cờ UTF-8 khiến charset tùy chọn không được dùng cho tên entry.
- **Tên entry và nội dung entry là hai vấn đề mã hóa khác nhau.** File `.txt` bên trong có thể dùng charset riêng; `ZipInputStream`/`ZipFile` không tự chuyển mã nội dung.
- Dùng **try-with-resources** với `ZipFile`, `ZipInputStream`, `ZipOutputStream`. Đóng ZIP stream sẽ đóng luồng nền được bọc; tổ chức rõ ai chịu trách nhiệm đóng.
- Kiểm tra `getEntry(...) == null`, phân biệt entry thư mục, xử lý `IOException`/`ZipException`, và không cho rằng file `.zip` nào cũng hợp lệ.
- `java.util.zip` chuẩn phục vụ ZIP thông thường; đừng giả định các API này tự cung cấp cơ chế mở/ghi archive ZIP có mật khẩu. Nếu sản phẩm bắt buộc hỗ trợ encryption, đánh giá một thư viện được duy trì tốt và yêu cầu bảo mật cụ thể.

## 9. Sai lầm thường gặp

| Sai lầm | Cách xử lý |
| --- | --- |
| Dùng `ZipInputStream` để gọi tên entry tùy ý nhiều lần | Chuyển sang `ZipFile` nếu archive có trên đĩa và cần truy cập theo tên |
| Dùng `ZipFile` trực tiếp với dữ liệu mới chỉ có `InputStream` | Xử lý tuần tự bằng `ZipInputStream`, hoặc lưu tệp tạm có giới hạn rồi mở `ZipFile` |
| Nghĩ `ZipEntry` chứa sẵn toàn bộ nội dung | Mở luồng và đọc byte thực tế; metadata chỉ mô tả entry |
| Dùng `readAllBytes()` cho archive/entry không rõ kích thước | Dùng vòng lặp bộ đệm với hạn mức byte |
| Tin `getSize()` luôn dương và chính xác trong khi stream | Chấp nhận `-1`; đo kích thước thực tế khi giải nén |
| Ghép `entry.getName()` trực tiếp vào đường dẫn đích | Kiểm tra traversal, symlink, overwrite và giới hạn quyền ghi |
| Quên `closeEntry()`, `close()` hoặc không hoàn tất ZIP đầu ra | Dùng try-with-resources, đóng từng entry và xử lý lỗi rõ ràng |
| Dùng tên entry phụ thuộc dấu `\` của Windows | Chuẩn hóa tên tương đối trong ZIP với dấu `/` |
| Giả định ZIP đồng nghĩa với nội dung đáng tin hoặc có mật khẩu | Xác minh nguồn, quota, nội dung và chọn giải pháp mã hóa chuyên dụng nếu cần |

## 10. Tình huống tự kiểm tra lựa chọn

1. **Service nhận ZIP qua request body**, mỗi entry là một bản ghi cần nhập, chỉ xử lý một lần: chọn **`ZipInputStream`**, xử lý tuần tự và đặt quota.
2. **Ứng dụng desktop có file `manuals.zip`** và chỉ muốn lấy `vi/intro.md` theo tên: chọn **`ZipFile`** và `getEntry`.
3. **API cần đóng gói nhiều báo cáo thành một file tải xuống**: chọn **`ZipOutputStream`**, gọi `putNextEntry` và ghi từng báo cáo.
4. **Hệ thống cần đọc nhiều entry từ một ZIP đang upload**, nhưng chưa cần ghi ra disk: nếu có thể xử lý tuần tự thì `ZipInputStream`; nếu cần truy vấn qua lại theo tên, cân nhắc tệp tạm có quota rồi dùng `ZipFile`.
5. **Gói ZIP do người dùng đưa lên sẽ được bung vào một thư mục**: lựa chọn API đọc chỉ là bước đầu; bắt buộc kết hợp kiểm tra đường dẫn, symlink, hạn mức byte/entry và xử lý kết quả chưa hoàn tất.

## 11. Tài liệu API chính thức

- [`ZipFile` — Java SE](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/zip/ZipFile.html)
- [`ZipInputStream` — Java SE](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/zip/ZipInputStream.html)
- [`ZipOutputStream` — Java SE](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/zip/ZipOutputStream.html)
- [`ZipEntry` — Java SE](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/zip/ZipEntry.html)

**Tiêu chí quyết định:** nguồn là *file hay stream*; cần *truy cập theo tên hay xử lý một lượt*; mục tiêu là *đọc hay tạo ZIP*. Sau khi chọn, mọi đường xử lý dữ liệu ZIP từ bên ngoài vẫn phải kiểm soát tài nguyên, tên đường dẫn và vòng đời I/O.
