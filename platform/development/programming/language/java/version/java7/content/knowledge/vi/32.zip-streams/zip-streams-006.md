# Quản lý tài nguyên ZIP bằng try-with-resources

## Mục tiêu

Trong Java, đọc và ghi ZIP thường giữ các tài nguyên hệ điều hành như file handle và luồng I/O. Nếu lỗi xảy ra giữa quá trình xử lý mà luồng không được đóng, chương trình có thể rò rỉ tài nguyên hoặc tạo tệp ZIP chưa hoàn chỉnh. `try-with-resources`, có từ Java 7 và vẫn được khuyến nghị hiện nay, tự đóng các đối tượng `AutoCloseable` khi rời khỏi khối `try`.

Bài này tập trung vào việc sử dụng `ZipInputStream`, `ZipOutputStream` và `ZipFile` an toàn, phân biệt đóng một entry với đóng toàn bộ ZIP, hiểu ngoại lệ khi đóng tài nguyên, đồng thời ứng dụng các biện pháp cơ bản khi giải nén ZIP. Các chương trình minh họa chạy bằng **JDK 17+** và dùng API còn phù hợp hiện nay.

## 1. Phân biệt tài nguyên ZIP và ZipEntry

| Đối tượng | Dùng khi nào? | Quản lý vòng đời |
| --- | --- | --- |
| `ZipInputStream` | Đọc các entry của một ZIP **tuần tự** từ `InputStream`, kể cả ZIP đến từ mạng hoặc stream. | Là `Closeable`: đặt trong `try (...)`; `close()` đóng cả nguồn bên dưới do wrapper sở hữu. |
| `ZipOutputStream` | Ghi từng entry để tạo ZIP. | Là `Closeable`: `close()` hoàn tất cấu trúc ZIP và đóng luồng đích bên dưới. |
| `ZipFile` | Mở tệp ZIP trên đĩa, tìm entry theo tên hoặc duyệt danh sách entry. | Là `Closeable`: đặt `ZipFile` trong `try (...)`, đóng luồng đọc riêng của từng entry khi dùng xong. |
| `ZipEntry` | Chứa tên, loại entry, kích thước, CRC, thời gian và metadata liên quan. | Không thực hiện `AutoCloseable`, do đó **không đặt** trong danh sách tài nguyên của `try`. |
| `InputStream`/`OutputStream` của nội dung | Đọc dữ liệu entry hoặc ghi dữ liệu ra tệp. | Đóng bằng `try-with-resources` nếu phương thức tạo và sở hữu luồng. |

Hai lệnh thường bị nhầm:

- `closeEntry()`: chỉ kết thúc **entry đang xử lý**. Với `ZipInputStream`, phần dữ liệu entry chưa đọc được bỏ qua trước khi chuyển sang entry tiếp theo; với `ZipOutputStream`, entry hiện tại được kết thúc.
- `close()`: đóng **đối tượng ZIP**. Với `ZipOutputStream`, đây còn là bước hoàn thiện thông tin cuối của archive. `flush()` hoặc `closeEntry()` không thay thế `close()` của toàn bộ ZIP.

`ZipInputStream`/`ZipOutputStream` là *wrapper stream*. Khi viết `new ZipInputStream(Files.newInputStream(path))`, thông thường hãy đưa **ZipInputStream** vào `try-with-resources`; đóng wrapper sẽ đóng luồng tệp được bọc, không cần khai báo cùng luồng đó thêm một lần chỉ để đóng lại. Nếu luồng đầu vào thuộc quyền sở hữu của caller, phải thống nhất rõ ai có trách nhiệm đóng trước khi dùng wrapper ZIP.

## 2. Try-with-resources hoạt động thế nào?

Cú pháp:

```java
try (ZipInputStream zip = new ZipInputStream(Files.newInputStream(zipPath))) {
    // Đọc các entry.
} // zip.close() tự chạy ngay cả khi khối try ném ngoại lệ.
```

Đoạn trên là **mã minh họa nằm trong một phương thức** đã có biến `Path zipPath` và xử lý hoặc khai báo `throws IOException`.

- Đối tượng tài nguyên phải thực hiện `AutoCloseable`. Sau khi kết thúc khối `try`, Java tự gọi `close()` dù kết thúc bình thường, `return` hay ném ngoại lệ.
- Nhiều tài nguyên khai báo trong cùng `try` được **đóng theo thứ tự ngược**: với `try (A a = ...; B b = ...)`, `b` được đóng trước, rồi `a`.
- Khi phần thân `try` và `close()` cùng phát sinh lỗi, lỗi trong phần thân là ngoại lệ chính; lỗi lúc đóng trở thành *suppressed exception*, đọc qua `getSuppressed()`. Nếu phần thân thành công nhưng `close()` lỗi, lỗi đóng được ném ra bình thường.
- `catch` và `finally` của một `try-with-resources` được thực hiện sau khi các tài nguyên đã được đóng.
- Java 7 cần khai báo tài nguyên ngay trong dấu ngoặc `try`. Từ Java 9, có thể dùng biến đã khai báo nếu biến đó là `final` hoặc `effectively final`. Cả hai cách vẫn được hỗ trợ hiện nay.

`try-with-resources` chỉ đảm nhiệm việc **đóng tài nguyên**; nó không tự xử lý `IOException`. Phương thức cần bắt/lan truyền ngoại lệ đúng yêu cầu nghiệp vụ.

## 3. Ví dụ hoàn chỉnh: tạo ZIP và đọc lại

Tệp **ZipResourcesDemo.java** dưới đây tạo một ZIP tạm có `docs/` và `docs/hello.txt`, đọc tuần tự bằng `ZipInputStream`, đọc theo tên bằng `ZipFile` rồi xóa tệp tạm. Mã chạy trên JDK 17+.

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

public class ZipResourcesDemo {
    public static void main(String[] args) throws IOException {
        Path zipPath = Files.createTempFile("zip-resources-", ".zip");
        try {
            writeZip(zipPath);
            readSequentially(zipPath);
            readByName(zipPath);
        } finally {
            Files.deleteIfExists(zipPath);
        }
    }

    private static void writeZip(Path zipPath) throws IOException {
        try (ZipOutputStream zip = new ZipOutputStream(
                Files.newOutputStream(zipPath), StandardCharsets.UTF_8)) {
            ZipEntry dir = new ZipEntry("docs/");
            dir.setMethod(ZipEntry.STORED);
            dir.setSize(0);
            dir.setCrc(0);
            zip.putNextEntry(dir);
            zip.closeEntry();

            zip.putNextEntry(new ZipEntry("docs/hello.txt"));
            zip.write("Xin chào ZIP!".getBytes(StandardCharsets.UTF_8));
            zip.closeEntry();
        }
        System.out.println("Đã tạo ZIP");
    }

    private static void readSequentially(Path zipPath) throws IOException {
        try (ZipInputStream zip = new ZipInputStream(
                Files.newInputStream(zipPath), StandardCharsets.UTF_8)) {
            ZipEntry entry;
            while ((entry = zip.getNextEntry()) != null) {
                if (!entry.isDirectory()) {
                    String text = new String(zip.readAllBytes(), StandardCharsets.UTF_8);
                    System.out.println("Đọc tuần tự: " + entry.getName() + " = " + text);
                }
                zip.closeEntry();
            }
        }
    }

    private static void readByName(Path zipPath) throws IOException {
        try (ZipFile archive = new ZipFile(zipPath.toFile(), StandardCharsets.UTF_8)) {
            ZipEntry entry = archive.getEntry("docs/hello.txt");
            if (entry == null) {
                throw new IOException("Thiếu docs/hello.txt");
            }
            try (InputStream input = archive.getInputStream(entry)) {
                String text = new String(input.readAllBytes(), StandardCharsets.UTF_8);
                System.out.println("Đọc trực tiếp: " + text);
            }
        }
    }
}
```

Biên dịch/chạy (lưu file mã nguồn UTF-8):

```bash
javac -encoding UTF-8 ZipResourcesDemo.java
java ZipResourcesDemo
```

Kết quả khi terminal hiển thị UTF-8:

```text
Đã tạo ZIP
Đọc tuần tự: docs/hello.txt = Xin chào ZIP!
Đọc trực tiếp: Xin chào ZIP!
```

### Giải thích từng tài nguyên

1. Trong `writeZip`, `ZipOutputStream` sở hữu `OutputStream` do `Files.newOutputStream` trả về. `closeEntry()` kết thúc lần lượt entry thư mục và entry file; ra khỏi `try`, `zip.close()` hoàn tất archive và đóng output bên dưới. Entry thư mục được đánh dấu `STORED`, kích thước và CRC bằng 0 để tránh nén nội dung rỗng.
2. Trong `readSequentially`, `getNextEntry()` lấy từng entry theo thứ tự; khi hết trả về `null`. Sau khi đọc xong, `closeEntry()` xác nhận kết thúc entry hiện tại. Ra khỏi khối `try`, cả `ZipInputStream` và nguồn tệp được đóng.
3. Trong `readByName`, `ZipFile` tra cứu trực tiếp `docs/hello.txt`; luồng lấy từ `getInputStream(entry)` được đóng trong `try` lồng nhau **trước khi** `ZipFile` đóng. `ZipFile.close()` cũng đóng các stream entry nó đã tạo, nhưng chủ động đóng từng stream làm vòng đời rõ ràng và giải phóng sớm hơn.
4. `Files.createTempFile` tránh trùng tên tệp; `finally` ở `main` dùng để dọn **tệp tạm**, không thay thế `try-with-resources` trong việc đóng luồng.

Ở ví dụ này, `readAllBytes()` là hợp lý vì nội dung ngắn và do chính chương trình tạo. **Không dùng `readAllBytes()` không giới hạn** để giải nén dữ liệu lớn hay ZIP từ nguồn lạ: cần buffer và hạn mức như phần tiếp theo. Java 17+ có `InputStream.readAllBytes()` và `Path.of(...)`; các API này không thuộc Java 7 ban đầu nhưng vẫn được dùng phổ biến trong Java hiện nay.

### Chọn API theo nhu cầu

- **ZipInputStream:** cần đọc tuần tự hoặc nguồn ZIP là một luồng.
- **ZipFile:** ZIP đã nằm trên đĩa, cần lấy một entry theo tên hoặc truy cập không tuần tự.
- **ZipOutputStream:** tạo archive. Hoàn tất `try` thành công rồi mới sử dụng tệp ZIP đầu ra.

## 4. Ngoại lệ, sở hữu luồng và tệp ghi dở

### Không làm mất lỗi gốc

```java
try (ZipFile archive = new ZipFile(zipPath.toFile())) {
    // Xử lý ZIP.
} catch (IOException e) {
    System.err.println("Không đọc được ZIP: " + e.getMessage());
    for (Throwable suppressed : e.getSuppressed()) {
        System.err.println("Lỗi bổ sung khi đóng: " + suppressed);
    }
    throw e;
}
```

Đây là **đoạn minh họa bên trong một phương thức** có biến `zipPath` và khai báo `throws IOException`. Khi lỗi xảy ra, đừng dùng `catch (Exception e) { }` để nuốt ngoại lệ rồi báo thành công. Hãy báo lỗi hoặc lan truyền để caller xử lý và, khi hữu ích, ghi nhận `getSuppressed()`.

Khi đóng một `ZipInputStream` hoặc `ZipOutputStream`, wrapper thường đóng luôn luồng nguồn/đích bên dưới. Một API nhận `InputStream` từ bên ngoài cần nêu rõ *ownership*: nếu caller muốn tiếp tục dùng luồng sau khi phương thức trả về, không được tự ý đóng luồng đó; phải thiết kế lại phạm vi sở hữu hoặc sử dụng wrapper phù hợp.

**Lưu ý khi tạo ZIP:** `try-with-resources` bảo đảm nỗ lực đóng luồng, nhưng nếu ghi gặp lỗi đĩa hay dữ liệu nguồn thì tệp ZIP đầu ra vẫn có thể không hợp lệ. Với dữ liệu quan trọng, ghi vào tệp tạm ở cùng filesystem, chỉ công bố/đổi tên sau khi khối `try` hoàn tất thành công; xóa tệp tạm khi lỗi. Nếu cần thay thế nguyên tử, xử lý cả trường hợp hệ thống tệp không hỗ trợ `Files.move(..., ATOMIC_MOVE)`.

## 5. Giải nén an toàn với try-with-resources

Đóng đúng luồng chưa đủ nếu ZIP đến từ người dùng hoặc nguồn không tin cậy. Cần chú ý:

- **ZIP Slip:** entry như `../outside.txt` hay đường dẫn tuyệt đối có thể ghi ra ngoài thư mục đích. Luôn `resolve`, `normalize`, kiểm tra `startsWith(root)` và lưu ý symlink/race.
- **ZIP bomb:** ZIP có thể giải nén thành lượng dữ liệu rất lớn. Đếm số entry và byte thực tế, giới hạn kích thước từng tệp và tổng dữ liệu. `ZipEntry.getSize()` có thể trả về `-1` hoặc không đáng tin; không dựa riêng vào metadata.
- **Ghi đè:** tránh ghi vào tệp có sẵn nếu không có chính sách rõ ràng; giải nén vào thư mục mới đáng tin là lựa chọn an toàn hơn.
- **Bộ nhớ:** copy theo buffer nhỏ thay vì giữ toàn bộ nội dung trong RAM.

Ví dụ **SafeZipExtract.java** (JDK 17+) giải nén vào **thư mục mới chưa tồn tại**, có thư mục cha đáng tin và không bị bên khác sửa đồng thời. Chương trình minh họa đóng riêng mỗi `OutputStream` và sau đó đóng `ZipInputStream`, giới hạn số lượng/kích thước đã giải nén, và từ chối đường dẫn nguy hiểm.

```java
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

public class SafeZipExtract {
    private static final int MAX_ENTRIES = 1_000;
    private static final long MAX_FILE_BYTES = 20L * 1024 * 1024;
    private static final long MAX_TOTAL_BYTES = 100L * 1024 * 1024;

    public static void main(String[] args) throws IOException {
        if (args.length != 2) {
            System.err.println("Cách dùng: java SafeZipExtract archive.zip thu-muc-moi");
            return;
        }
        extract(Path.of(args[0]), Path.of(args[1]));
        System.out.println("Giải nén hoàn tất");
    }

    static void extract(Path zipPath, Path outputDir) throws IOException {
        Path root = outputDir.toAbsolutePath().normalize();
        Files.createDirectory(root); // Thư mục mới dưới thư mục cha đáng tin.

        long totalBytes = 0;
        int entryCount = 0;
        byte[] buffer = new byte[8192];

        try (ZipInputStream zip = new ZipInputStream(
                Files.newInputStream(zipPath), StandardCharsets.UTF_8)) {
            ZipEntry entry;
            while ((entry = zip.getNextEntry()) != null) {
                if (++entryCount > MAX_ENTRIES) {
                    throw new IOException("Quá nhiều entry trong ZIP");
                }
                String name = entry.getName();
                if (name.isBlank() || name.indexOf('\\') >= 0) {
                    throw new IOException("Tên entry không hợp lệ: " + name);
                }
                Path target = root.resolve(name).normalize();
                if (!target.startsWith(root) ||
                        (target.equals(root) && !entry.isDirectory())) {
                    throw new IOException("Chặn ZIP Slip: " + name);
                }

                if (entry.isDirectory()) {
                    Files.createDirectories(target);
                } else {
                    Files.createDirectories(target.getParent());
                    long fileBytes = 0;
                    try (OutputStream out = Files.newOutputStream(
                            target, StandardOpenOption.CREATE_NEW,
                            StandardOpenOption.WRITE)) {
                        int count;
                        while ((count = zip.read(buffer)) != -1) {
                            if (count > MAX_FILE_BYTES - fileBytes ||
                                    count > MAX_TOTAL_BYTES - totalBytes) {
                                throw new IOException("Vượt giới hạn giải nén");
                            }
                            out.write(buffer, 0, count);
                            fileBytes += count;
                            totalBytes += count;
                        }
                    }
                }
                zip.closeEntry();
            }
        }
    }
}
```

Biên dịch và chạy (thư mục `extracted-new` **chưa tồn tại**, còn thư mục cha phải tồn tại):

```bash
javac -encoding UTF-8 SafeZipExtract.java
java SafeZipExtract archive.zip extracted-new
```

**Vì sao các kiểm tra này quan trọng?** `Files.createDirectory(root)` từ chối đích đã tồn tại; `CREATE_NEW` từ chối ghi đè; `normalize()/startsWith()` chặn đường dẫn đi ra khỏi root; bộ đếm hạn mức được cập nhật theo từng lần `read(buffer)`, không theo số byte do file ZIP khai báo. Khi một entry lỗi, khối `try` bên trong vẫn đóng output file; cuối cùng khối `try` bên ngoài đóng ZIP.

Đây là ví dụ cho **thư mục cha đáng tin, quyền truy cập được kiểm soát**. Nếu đối tượng khác có thể tạo/sửa symlink hoặc thư mục đồng thời, chỉ so sánh `normalize()/startsWith()` chưa đủ ngăn tấn công qua symlink hay race; cần cô lập thư mục giải nén, giới hạn quyền hệ điều hành và cân nhắc `SecureDirectoryStream` khi được hỗ trợ. Nếu giải nén lỗi, thư mục mới có thể chứa tệp **ghi một phần**: phải coi kết quả chưa thành công, dọn vùng tạm và chỉ công bố dữ liệu sau khi xử lý đầy đủ. Trong sản phẩm thật, hạn mức entry/byte phải điều chỉnh theo tài nguyên hệ thống; có thể cần cả quota đĩa và giới hạn thời gian.

`java.util.zip` xử lý ZIP thông thường; không nên mặc định nó hỗ trợ mọi kiểu ZIP đặt mật khẩu/mã hóa. Nội dung ZIP không được xác thực chỉ nhờ kiểm tra CRC: với gói phân phối có yêu cầu tin cậy, kiểm tra nguồn/chữ ký/checksum đáng tin trước khi sử dụng.

## 6. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Chỉ `closeEntry()`, không đóng toàn bộ ZIP | Rò rỉ luồng; ZIP đầu ra có thể thiếu cấu trúc cuối. | Đặt `ZipInputStream`/`ZipOutputStream` trong `try-with-resources`. |
| Đưa `ZipEntry` vào `try (...)` | `ZipEntry` không phải `AutoCloseable`. | Chỉ quản lý đối tượng ZIP và các luồng mở thật. |
| Đọc ZIP lớn bằng `readAllBytes()` | Có thể dùng hết RAM. | Copy theo buffer và giới hạn byte giải nén. |
| Lấy số byte còn lại bằng `ZipInputStream.available()` | `available()` không phải kích thước dữ liệu còn lại. | Đọc đến khi `read(...)` trả `-1`. |
| Nối thẳng `entry.getName()` vào đường dẫn đích | Có thể tạo path traversal. | Chuẩn hóa và kiểm tra đường dẫn; kiểm soát symlink. |
| Đóng `ZipFile` trước luồng entry | Entry stream không còn đọc được. | Dùng `try` của stream **bên trong** `try` của `ZipFile`. |
| Bỏ qua `IOException` và lỗi đóng | Có thể che giấu ZIP hỏng. | Xử lý hoặc lan truyền lỗi; kiểm tra lỗi `suppressed` khi cần. |
| Coi `flush()` đã hoàn tất ZIP | Thiếu bước kết thúc archive. | Đóng `ZipOutputStream` hoặc `finish()` theo yêu cầu ownership. |
| Đóng tùy tiện stream do caller truyền vào | Caller có thể cần tiếp tục dùng stream. | Quy định rõ bên sở hữu và quyền đóng. |

## 7. Tự luyện tập

1. Thêm `docs/readme.txt` trong `ZipResourcesDemo`, xem vòng lặp `getNextEntry()` in ra hai file. Giải thích vì sao mỗi file có `closeEntry()` riêng nhưng toàn bộ ZIP chỉ đóng một lần.
2. Sau `putNextEntry(...)`, cố ý ném `IOException`. Xác nhận tài nguyên vẫn đóng khi có lỗi và giải thích vì sao không nên công bố ZIP chưa tạo thành công.
3. Tìm entry thứ hai bằng `ZipFile`, dùng `try (InputStream input = archive.getInputStream(entry))` và phân tích thứ tự đóng `input`/`archive`.
4. Tạo tệp ZIP kiểm thử có entry `../outside.txt`; xác nhận `SafeZipExtract` từ chối. Dùng **thư mục đích mới** trong mỗi lần chạy.
5. Giảm `MAX_FILE_BYTES` xuống nhỏ hơn kích thước một entry. Quan sát lỗi và đề xuất cách dọn tệp giải nén chưa hoàn chỉnh.

## 8. Tài liệu tham khảo hiện hành

- [Java SE 21 — ZipInputStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/zip/ZipInputStream.html): `getNextEntry()`, `closeEntry()`, `read(...)`, `close()`.
- [Java SE 21 — ZipOutputStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/zip/ZipOutputStream.html): `putNextEntry()`, `closeEntry()`, `finish()`, `close()`.
- [Java SE 21 — ZipFile](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/zip/ZipFile.html): `getEntry()`, `getInputStream()` và đóng ZIP.
- [Java Language Specification `14.20.3 — try-with-resources](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20.3): quy tắc đóng tài nguyên và suppressed exceptions.

**Ghi nhớ:** `try-with-resources` quản lý vòng đời **toàn bộ đối tượng ZIP**; `closeEntry()` quản lý **từng entry**. Với ZIP không đáng tin, cần kết hợp đóng tài nguyên, kiểm tra đường dẫn và giới hạn dữ liệu giải nén.