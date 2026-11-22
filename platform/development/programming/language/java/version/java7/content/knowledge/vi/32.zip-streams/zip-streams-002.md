# Chỉ rõ bảng mã tên mục ZIP bằng Charset (Java 7+)

## 1. Mục tiêu và vấn đề thực tế

Trong một tệp ZIP, mỗi mục (`ZipEntry`) có **tên đường dẫn** như `docs/giới-thiệu.txt` và có thể có **chú thích**. ZIP lưu tên/chú thích dưới dạng byte; Java phải dùng một bảng mã ký tự (`Charset`) để chuyển byte thành `String` khi đọc, hoặc chuyển `String` thành byte khi ghi. Nếu chọn sai bảng mã, tên chứa dấu có thể bị lỗi, không tìm được mục bằng `getEntry(name)`, hoặc quá trình đọc thất bại.

Sau bài này, bạn có thể:
- Chọn `Charset` cho tên mục ZIP khi đọc bằng `ZipFile` hoặc `ZipInputStream`.
- Chỉ rõ `Charset` khi tạo ZIP bằng `ZipOutputStream`, ưu tiên UTF-8 cho dữ liệu mới.
- Phân biệt **bảng mã tên mục** với **bảng mã nội dung tệp**, hiểu cờ UTF-8 của ZIP và xử lý ZIP không dùng UTF-8 khi có thông tin xác thực.

Các overload nhận `Charset` của ba lớp này có từ Java 7 và **vẫn được hỗ trợ trong JDK hiện đại**. Ví dụ hoàn chỉnh dưới đây dùng Java 17+.

## 2. Charset tác động lên phần nào của ZIP?

Giả sử ZIP chứa mục tên `báo-cáo.txt`, bên trong là một tệp văn bản. Có hai vấn đề mã hóa độc lập:

| Thành phần | Cách Java xử lý | Điều cần nhớ |
| --- | --- | --- |
| Tên đường dẫn và chú thích mục ZIP | `ZipFile`, `ZipInputStream`, `ZipOutputStream` dùng bảng mã tên mục | Đây là phạm vi của tham số `Charset` trong các constructor ZIP |
| Byte nội dung mục | `ZipFile.getInputStream(...)` hoặc `ZipInputStream.read(...)` trả byte đã giải nén | Nếu nội dung là văn bản, tự giải mã byte bằng đúng charset của **tệp bên trong**, chẳng hạn `StandardCharsets.UTF_8` |
| Cấu trúc nén / checksum | Do API ZIP xử lý | Thay đổi charset không thay đổi thuật toán nén hoặc tự động chuyển mã nội dung |

Một ZIP thường đánh dấu tên mục UTF-8 bằng **general purpose bit flag, bit 11** (còn gọi là *language encoding flag* hoặc *EFS*). Khi cờ này được đặt, API ZIP chuẩn của Java giải mã tên theo **UTF-8**, kể cả khi bạn truyền một `Charset` khác vào constructor. Vì vậy, tham số này chủ yếu cần cho các mục **không được đánh dấu UTF-8**.

Với ZIP mới do hệ thống hiện đại tạo ra, **ưu tiên UTF-8** và nhất quán giữa bên ghi và bên đọc. Không lấy `Charset.defaultCharset()` hoặc bảng mã hệ điều hành làm mặc định ngầm.

## 3. Những constructor cần biết

| API | Ví dụ | Công dụng |
| --- | --- | --- |
| `ZipFile(File, Charset)` | `new ZipFile(file, StandardCharsets.UTF_8)` | Mở tệp ZIP và giải mã tên mục/chú thích; hỗ trợ truy cập theo tên, duyệt danh sách |
| `ZipFile(String, Charset)` | `new ZipFile("data.zip", charset)` | Cùng mục đích, nhưng truyền đường dẫn dưới dạng `String` |
| `ZipInputStream(InputStream, Charset)` | `new ZipInputStream(input, charset)` | Đọc lần lượt các mục từ một luồng ZIP, không cần truy cập ngẫu nhiên |
| `ZipOutputStream(OutputStream, Charset)` | `new ZipOutputStream(output, charset)` | Ghi tên mục và chú thích khi tạo ZIP |

`Charset` được chọn cho **đối tượng ZIP**; API mức cao này không có lựa chọn charset riêng cho từng `ZipEntry`. Constructor không nhận `Charset` dùng UTF-8 trong các JDK hiện đại, nhưng truyền rõ `StandardCharsets.UTF_8` giúp hợp đồng mã hóa dễ kiểm tra khi trao đổi giữa các hệ thống.

**Chọn lớp đọc:** `ZipFile` phù hợp khi đã có ZIP trên đĩa và cần tìm/dò mục; `ZipInputStream` phù hợp khi đang nhận ZIP dưới dạng `InputStream` và xử lý tuần tự. Cả hai đều cần đóng bằng `try-with-resources`.

## 4. Ví dụ hoàn chỉnh: ghi rồi đọc tên tiếng Việt bằng UTF-8

Tạo tệp **ZipCharsetDemo.java** với mã Java 17+ sau. Chương trình tạo `demo-utf8.zip`, chứa một mục có tên tiếng Việt; sau đó đọc lại qua hai API khác nhau. Lưu ý hai lần sử dụng `StandardCharsets.UTF_8`: một lần cho **tên ZIP**, một lần cho **văn bản bên trong**.

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import java.util.zip.ZipInputStream;
import java.util.zip.ZipOutputStream;

public class ZipCharsetDemo {
    public static void main(String[] args) throws IOException {
        Path archive = Paths.get("demo-utf8.zip");
        Charset entryCharset = StandardCharsets.UTF_8;
        String entryName = "docs/giới-thiệu.txt";

        try (ZipOutputStream out =
                new ZipOutputStream(Files.newOutputStream(archive), entryCharset)) {
            out.putNextEntry(new ZipEntry(entryName));
            out.write("Xin chào từ ZIP\n".getBytes(StandardCharsets.UTF_8));
            out.closeEntry();
        }

        try (ZipFile file = new ZipFile(archive.toFile(), entryCharset)) {
            ZipEntry entry = file.getEntry(entryName);
            if (entry == null) {
                throw new IOException("Không tìm thấy mục: " + entryName);
            }
            try (InputStream in = file.getInputStream(entry)) {
                String text = new String(in.readAllBytes(), StandardCharsets.UTF_8).strip();
                System.out.println("ZipFile: " + entry.getName());
                System.out.println("Nội dung: " + text);
            }
        }

        try (ZipInputStream in =
                new ZipInputStream(Files.newInputStream(archive), entryCharset)) {
            ZipEntry entry = in.getNextEntry();
            if (entry != null) {
                System.out.println("ZipInputStream: " + entry.getName());
                in.closeEntry();
            }
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa mã nguồn (tệp Java được lưu bằng UTF-8):

```bash
javac --release 17 -encoding UTF-8 ZipCharsetDemo.java
java ZipCharsetDemo
```

Kết quả stdout:

```text
ZipFile: docs/giới-thiệu.txt
Nội dung: Xin chào từ ZIP
ZipInputStream: docs/giới-thiệu.txt
```

Giải thích từng bước:
1. `ZipOutputStream(..., entryCharset)` mã hóa tên mục `docs/giới-thiệu.txt` thành byte ZIP với UTF-8; `putNextEntry`, `write` và `closeEntry` ghi xong mục.
2. `ZipFile(..., entryCharset)` giải mã tên mục, nên `getEntry(entryName)` tìm đúng mục. `getInputStream` lấy **byte nội dung**, rồi `new String(..., UTF_8)` mới giải mã văn bản.
3. `ZipInputStream(..., entryCharset)` đọc tuần tự, `getNextEntry()` trả về mục hiện tại, `getName()` cho tên đã giải mã. `closeEntry()` kết thúc mục.
4. `try-with-resources` đóng luồng ZIP và file ngay cả khi phát sinh ngoại lệ. Chương trình chủ động tạo lại `demo-utf8.zip` ở thư mục làm việc mỗi lần chạy.

`InputStream.readAllBytes()` và `String.strip()` là tiện ích Java mới hơn Java 7; chúng được dùng ở đây để ví dụ dễ đọc trên Java 17+. **Các constructor ZIP nhận `Charset` chính là khả năng có từ Java 7 và tiếp tục dùng được ngày nay.**

## 5. Đọc ZIP không đánh dấu UTF-8: chọn bảng mã dựa trên nguồn thực tế

Một số kho lưu trữ do phần mềm hoặc đối tác hiện tại cung cấp vẫn có tên mục không gắn cờ UTF-8. Khi **biết rõ** đối tác dùng IBM437 (CP437), có thể chỉ rõ:

```java
Charset entryNames = Charset.forName("IBM437");
try (ZipFile zip = new ZipFile(new java.io.File("archive-from-partner.zip"), entryNames)) {
    java.util.Enumeration<? extends ZipEntry> items = zip.entries();
    while (items.hasMoreElements()) {
        System.out.println(items.nextElement().getName());
    }
}
```

Đây là **đoạn mã minh họa** đặt trong một phương thức có `throws IOException`; cần import `Charset`, `ZipFile` và `ZipEntry` như ví dụ trước. IBM437 chỉ là ví dụ một bảng mã có thể gặp, **không phải lựa chọn đúng cho mọi ZIP cũ hoặc mọi ZIP không có cờ UTF-8**. Với nguồn khác, tên bảng mã được xác nhận có thể khác; dùng `Charset.forName("...")` chỉ khi charset đó có sẵn trong runtime.

Quy trình xử lý hợp lý:
1. **Xác định nguồn ZIP** và quy ước của hệ thống tạo tệp; hỏi đối tác hoặc xem tài liệu giao tiếp/file mẫu có tên không ASCII.
2. **Kiểm tra cờ UTF-8**. Với mục đã đánh dấu UTF-8, `Charset` truyền vào sẽ không ghi đè cách giải mã UTF-8 của API Java.
3. **Chọn charset đúng cho tên/chú thích**, mở lại ZIP qua constructor nhận `Charset`, rồi xác minh `getName()`, `getEntry(name)` với các tên chứa dấu.
4. **Kiểm tra nội dung riêng** theo quy ước của chính tệp bên trong ZIP; đừng tự suy ra cùng bảng mã với tên mục.
5. Nếu ZIP pha trộn nhiều bảng mã giữa các mục hoặc metadata mâu thuẫn, hãy xử lý tại nguồn tạo ZIP hoặc dùng công cụ/thư viện có khả năng kiểm tra header phù hợp. Một tham số `Charset` toàn cục không giải quyết được tất cả trường hợp đó.

Không sửa tên bằng thao tác kiểu `new String(entry.getName().getBytes(...), ...)` sau khi đã đọc sai; cách này phụ thuộc vào byte còn giữ được hay không và có thể làm dữ liệu sai thêm. Sửa cấu hình giải mã **ngay tại lúc mở ZIP** hoặc yêu cầu tái xuất ZIP chuẩn UTF-8.

## 6. Lỗi phổ biến và lưu ý khi ứng dụng

- **Nhầm tên mục với nội dung:** truyền `UTF_8` cho `ZipFile` không biến nội dung tệp từ một encoding khác sang UTF-8. Khi đọc tệp văn bản, giải mã nội dung với charset được thỏa thuận riêng; với ảnh/PDF thì xử lý như dữ liệu nhị phân.
- **Phụ thuộc hệ điều hành:** tránh chọn charset theo máy đang chạy. Một ZIP cần đọc giống nhau trên Windows, Linux, container và CI.
- **Thử charset ngẫu nhiên:** một tên ngắn không dấu có thể hiển thị đúng với nhiều bảng mã, nên không chứng minh được bảng mã thực. Dùng tên có dấu và dữ liệu kiểm thử đã xác nhận.
- **Cố ép charset khi cờ UTF-8 đã bật:** API Java ưu tiên UTF-8 cho mục có EFS; nếu header/tên không nhất quán, cần sửa nơi tạo ZIP.
- **Không đóng tài nguyên:** `ZipFile`, `ZipInputStream`, `ZipOutputStream` giữ tài nguyên I/O; luôn dùng `try-with-resources`.
- **Giải nén đường dẫn thiếu kiểm soát:** tên `ZipEntry` là dữ liệu đầu vào, không được ghép thẳng để ghi file. Khi giải nén, chuẩn hóa đường dẫn, đảm bảo nó nằm trong thư mục đích, đề phòng symlink/path traversal và đặt giới hạn dung lượng để chống ZIP bomb. Chọn đúng charset là cần thiết nhưng không thay thế các kiểm tra an toàn này.

## 7. Checklist trước khi đưa vào hệ thống

- Khi **tạo ZIP mới**, đặt quy ước UTF-8 cho tên mục; dùng `ZipOutputStream(..., StandardCharsets.UTF_8)`.
- Khi **đọc ZIP từ nguồn đã biết**, dùng `ZipFile` hoặc `ZipInputStream` với charset đúng của nguồn; xử lý cờ UTF-8 theo quy tắc ZIP.
- Khi **xử lý văn bản trong ZIP**, quyết định charset nội dung tách biệt với charset tên mục.
- Viết kiểm thử round-trip với tên có dấu/ký tự Unicode, bao gồm `getEntry` và đọc nội dung; kiểm tra thêm file mẫu thật từ đối tác.
- Đóng stream, xác thực đường dẫn giải nén và giới hạn dữ liệu đầu vào không tin cậy.

**Ghi nhớ:** Tham số `Charset` của API ZIP giải quyết việc mã hóa/giải mã **tên mục và chú thích ZIP**. Sử dụng UTF-8 cho ZIP mới; khi tích hợp ZIP không đánh dấu UTF-8, chọn đúng charset theo quy ước thực tế, không đoán theo hệ điều hành.

### Tài liệu API chính thức

- [Java SE 21 — ZipFile](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/zip/ZipFile.html)
- [Java SE 21 — ZipInputStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/zip/ZipInputStream.html)
- [Java SE 21 — ZipOutputStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/zip/ZipOutputStream.html)
