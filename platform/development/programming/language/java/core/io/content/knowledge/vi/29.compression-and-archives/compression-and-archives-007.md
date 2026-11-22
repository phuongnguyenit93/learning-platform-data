# ZIP archive: charset của tên entry và metadata trong Java

Trong Java Core I/O, các lớp `java.util.zip.ZipFile`, `ZipInputStream`, `ZipOutputStream` và `ZipEntry` giúp đọc, ghi và kiểm tra file ZIP. Một archive không chỉ chứa **bytes nội dung**: mỗi entry còn có **tên đường dẫn, comment, thời gian, kích thước, phương thức nén, CRC và các extra fields**. Nếu thiết kế sai charset tên entry hoặc diễn giải metadata thiếu thận trọng, file ZIP có thể hiển thị tên tiếng Việt bị lỗi, mất dấu thời gian, hoặc gây lỗi và rủi ro khi giải nén.

**Ý chính:** Charset để mã hóa **tên entry/comment** và charset của **nội dung file bên trong entry** là hai việc độc lập. Với archive mới nên chọn **UTF-8** nhất quán. Với ZIP legacy, cần biết định dạng thực tế và bit đánh dấu UTF-8 trong ZIP trước khi đọc bằng charset khác. Metadata là **thông tin có điều kiện**, không phải bằng chứng nội dung an toàn, nguyên vẹn hay đã được xác thực.

## 1. Archive, entry và nội dung là ba tầng khác nhau

Một ZIP gồm nhiều entry và các cấu trúc như local file header, dữ liệu nén, central directory và phần kết thúc archive. Mỗi entry đại diện một file hoặc một đường dẫn thư mục. Ví dụ:

```text
documents.zip
├── tài-liệu/                     # Có thể là directory entry, nếu được ghi
│   └── đề-cương.txt               # Tên ZIP entry: "tài-liệu/đề-cương.txt"
├── images/
│   └── logo.png
└── README.md

Mỗi file entry gồm các khái niệm:
  name                tên/đường dẫn nội bộ archive
  comment             ghi chú tùy chọn của entry
  compressed data     bytes file sau khi nén
  CRC-32              checksum của bytes gốc
  size                kích thước không nén
  compressedSize      kích thước dữ liệu nén
  method              ví dụ STORED hoặc DEFLATED
  timestamps/extra    metadata và các trường mở rộng
```

Tên entry sử dụng quy ước ZIP với dấu phân cách đường dẫn `/`. Đừng đồng nhất nó với `Path` của hệ điều hành hiện tại: trên Windows, ZIP entry thường vẫn dùng `/`; archive có thể chứa tên lạ hoặc độc hại không thể ánh xạ trực tiếp sang file hợp lệ.

Một entry thư mục thường có tên **kết thúc bằng `/`**, ví dụ `"documents/"`, và `ZipEntry.isDirectory()` kiểm tra quy ước này. ZIP có thể chỉ chứa file entry `"documents/report.txt"` mà **không có entry thư mục `"documents/"` riêng**. Khi giải nén, ứng dụng có thể cần tạo thư mục cha.

## 2. Charset tên entry không phải charset của payload

Phân biệt rõ bốn khái niệm:

| Thành phần | Được mã hóa hoặc diễn giải ra sao? | Java API tiêu biểu |
| --- | --- | --- |
| Tên entry | Một chuỗi ký tự được chuyển thành các byte trong ZIP header/central directory. | `new ZipOutputStream(out, charset)`; `new ZipFile(file, charset)` |
| Comment của entry | Metadata dạng chuỗi; encoding phải tương thích với bên đọc. | `ZipEntry.setComment()` / `getComment()` |
| Comment toàn archive | Ghi chú lưu ở vùng kết thúc central directory. | `ZipOutputStream.setComment()`; `ZipFile.getComment()` |
| Nội dung file | Dãy byte tùy loại dữ liệu; ZIP không ép nó là văn bản UTF-8. | `out.write(bytes)`; `ZipFile.getInputStream(entry)` |

Ví dụ một ZIP lưu tên `"tài-liệu/đề-cương.txt"` bằng UTF-8. Bên trong có thể là một ảnh JPEG, tập tin PDF, hoặc một `.txt` với nội dung dùng UTF-8, UTF-16 hay một charset legacy khác. Tham số `Charset` của `ZipOutputStream` chỉ hướng tới mã hóa **tên và comment thuộc cấu trúc ZIP**; nó không tự chuyển mọi bytes nội dung thành UTF-8.

Mẫu đúng cho file text UTF-8:

```java
byte[] payload = "Xin chào".getBytes(StandardCharsets.UTF_8);
out.putNextEntry(new ZipEntry("tài-liệu/chào.txt"));
out.write(payload);
out.closeEntry();
```

Đây là snippet giả định `out` là `ZipOutputStream` đã được mở với UTF-8, có import `StandardCharsets` và `ZipEntry`. Khi đọc, giải mã **payload** bằng `new String(bytes, StandardCharsets.UTF_8)` hoặc dùng `InputStreamReader(in, UTF_8)` nếu biết file thật sự là văn bản UTF-8.

## 3. UTF-8 flag (bit 11) và charset legacy trong ZIP

Ở định dạng ZIP, **general purpose bit flag bit 11** còn được gọi là *language encoding flag* hoặc *EFS flag*. Khi được bật, tên entry và comment tương ứng được hiểu theo **UTF-8**. Bên đọc tương thích phải tôn trọng bit này, không ép tên UTF-8 thành CP437 hay một charset khác.

Khi bit này **không được bật**, tên/comment có thể được mã hóa theo một charset truyền thống. ZIP cổ điển thường gắn với **IBM437 (CP437)**; ngoài thực tế còn gặp tên do công cụ cũ ghi bằng Windows code page hoặc encoding địa phương. Vì vậy:

- Với ZIP do ứng dụng **mới** tạo, ưu tiên `StandardCharsets.UTF_8` và một công cụ phát hành thống nhất.
- Với ZIP **legacy**, cần biết charset mà nhà sản xuất ZIP thực sự sử dụng; chỉ vì file hiển thị lỗi dấu không đủ kết luận nó thuộc charset nào.
- Nếu ZIP có **UTF-8 flag**, charset legacy truyền vào các constructor đọc tên không được dùng để diễn giải những tên đã đánh dấu UTF-8. Đọc theo bit flag của ZIP.
- Nếu ZIP không có flag và tên đã được ghi bằng một bảng mã khác, dùng `Charset` phù hợp để diễn giải tên entry.
- Một số định dạng mở rộng ZIP có Unicode Path Extra Field (`0x7075`) và Unicode Comment Extra Field (`0x6375`), thường đi kèm CRC để liên hệ với tên/comment gốc. **Không mặc định** mọi thư viện ZIP đều tự xử lý những extra fields ấy theo cùng cách.

**Quan trọng về khả năng liên thông:** API `java.util.zip` không hứa tự phát hiện mọi charset legacy qua heuristic. Nếu cần hỗ trợ file ZIP từ nhiều nguồn, hãy đặt một chính sách chọn charset có cấu hình, ưu tiên bit flag/hợp đồng nguồn, thử các fixture thực tế, và xử lý lỗi giải mã thay vì âm thầm làm sai tên file.

## 4. Chọn charset đúng trong Java

Java 17+ có các constructor hữu ích:

```java
// Mặc định hiện đại: UTF-8 cho tên ZIP.
ZipOutputStream out1 = new ZipOutputStream(outputStream);
ZipInputStream in1 = new ZipInputStream(inputStream);
ZipFile zip1 = new ZipFile(file);

// Chỉ định rõ UTF-8 (phù hợp archive mới).
ZipOutputStream out2 = new ZipOutputStream(
        outputStream2, StandardCharsets.UTF_8);
ZipFile zip2 = new ZipFile(file2, StandardCharsets.UTF_8);

// Đọc/ghi ZIP legacy có charset tương thích.
Charset cp437 = Charset.forName("IBM437");
ZipInputStream legacyStream = new ZipInputStream(inputStream3, cp437);
ZipFile legacyZip = new ZipFile(legacyFile, cp437);
```

**Đây là các snippet riêng**, không phải một đoạn chạy độc lập: các biến stream/file phải đã được khởi tạo, và từng đối tượng sau khi dùng cần đóng đúng vòng đời bằng `try-with-resources`. Khi đặt charset khác UTF-8, phải chắc chắn charset đó mã hóa được những tên/comment dự kiến. Chẳng hạn `IBM437` có thể mã hóa `"café.txt"`, nhưng không thể mã hóa đầy đủ một tên file tiếng Việt hiện đại.

Ghi chú API:

| Lớp | Chức năng | Điểm cần lưu ý |
| --- | --- | --- |
| `ZipOutputStream(OutputStream, Charset)` | Tạo ZIP, mã hóa tên/comment theo quy định và charset đã chọn. | Phù hợp khi cần kiểm soát archive mới; encoding không hợp lệ có thể gây exception. |
| `ZipInputStream(InputStream, Charset)` | Đọc entry tuần tự, dùng charset thích hợp cho tên. | Truy cập tuần tự qua local file headers; không cung cấp trải nghiệm metadata/tra cứu toàn bộ như ZipFile. |
| `ZipFile(File, Charset)` | Mở central directory để tra cứu entry, comment và metadata. | Đọc tên đúng charset; phải đóng để giải phóng resource. |
| `ZipEntry(String)` | Đặt tên logic của một entry. | Không nhận `Charset`; việc mã hóa tên diễn ra ở ZipOutputStream. |

Trong Java 17, các overload không truyền charset của thư viện Java tiêu chuẩn dùng UTF-8 theo hợp đồng JDK. Tránh giả định archive được giải nén ở một phần mềm **khác** sẽ luôn dùng UTF-8 nếu file legacy không có flag.

## 5. Metadata thường gặp trên ZipEntry

`ZipEntry` đưa ra một số thông tin:

| API | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `getName()` | Tên entry đã giải mã. | Có thể là đường dẫn tương đối, tuyệt đối hoặc chuỗi chứa traversal do archive không tin cậy cung cấp. |
| `getComment()` / `setComment()` | Ghi chú tùy chọn của entry. | Có thể null; không dùng như dữ liệu có bảo đảm xác thực. |
| `getMethod()` / `setMethod()` | Phương thức ZIP; JDK tiêu biểu `STORED` và `DEFLATED`. | Không phải mọi compression method từ công cụ bên ngoài đều được JDK hỗ trợ. |
| `getSize()` / `setSize()` | Kích thước uncompressed, byte. | Có thể trả `-1` nếu chưa biết. |
| `getCompressedSize()` / `setCompressedSize()` | Số byte nén. | Có thể trả `-1` nếu chưa biết; phụ thuộc phương thức và thời điểm tạo/đọc. |
| `getCrc()` / `setCrc()` | CRC-32 của nội dung trước nén. | Có thể trả `-1` nếu chưa biết; CRC kiểm tra lỗi ngẫu nhiên, **không** phải chữ ký mật mã. |
| `getTime()` / `setTime(long)` | Thời điểm sửa đổi theo timestamp dạng milliseconds. | Giá trị có thể thiếu, phạm vi/độ chính xác phụ thuộc metadata ZIP. |
| `getLastModifiedTime()` | `FileTime` của mốc sửa đổi nếu có. | Có thể null; độ chính xác và cách biểu diễn phụ thuộc extra fields. |
| `getLastAccessTime()` / `getCreationTime()` | Mốc truy cập/tạo nếu archive cung cấp. | Có thể null; không suy diễn thiếu thành `now()`. |
| `getExtra()` / `setExtra(byte[])` | Các extra fields theo định dạng nhị phân ZIP. | Có thể null; cần parse theo ID/độ dài và kiểm tra biên nghiêm ngặt. |
| `isDirectory()` | Kiểm tra tên kết thúc bằng `/`. | Không xác nhận file ngoài archive thật sự là thư mục an toàn. |

Thông số metadata có thể không được ghi đầy đủ trong mọi ZIP. Với ZIP được tạo từ một công cụ bên ngoài, một entry có thể thiếu comment, missing creation time, hoặc lưu thời gian với độ chính xác khác kỳ vọng. Khi copy/repack ZIP, không nên vô tình thay mọi timestamp về thời điểm hiện tại nếu ứng dụng cần bảo tồn thời gian nguồn.

### Metadata toàn archive

`ZipOutputStream.setComment(String)` đặt **archive comment**, còn `ZipEntry.setComment(String)` đặt **entry comment**. `ZipFile.getComment()` đọc archive comment. Hai loại này là hai cấu trúc riêng, không được nhầm với payload của file `README.txt`.

Giới hạn ghi chú ZIP thường tính **theo số byte được mã hóa**, tối đa 65.535 byte cho trường comment tương ứng. Chuỗi Java có 30.000 ký tự Unicode không đảm bảo nằm trong giới hạn bytes khi mã hóa UTF-8. Với archive do bên ngoài cung cấp, comment có thể null hoặc có ký tự ngoài charset.

## 6. Timestamps và độ chính xác

ZIP cổ điển có trường thời gian ngày/giờ kiểu MS-DOS, với một số giới hạn: độ phân giải giây có thể là **2 giây**, dải ngày bị giới hạn và thông tin múi giờ không luôn đầy đủ. Các extra fields thường được dùng để bổ sung timestamp có độ chính xác/ý nghĩa tốt hơn; nhưng các tool ZIP khác nhau có thể ghi hoặc đọc chúng không giống nhau.

Java cho phép đặt:

```java
ZipEntry entry = new ZipEntry("notes.txt");
entry.setLastModifiedTime(
        FileTime.from(Instant.parse("2024-01-02T03:04:06Z")));
entry.setLastAccessTime(
        FileTime.from(Instant.parse("2024-01-02T03:04:06Z")));
entry.setCreationTime(
        FileTime.from(Instant.parse("2024-01-02T03:04:06Z")));
```

Đây là snippet dùng imports `java.util.zip.ZipEntry`, `java.nio.file.attribute.FileTime`, `java.time.Instant`; giá trị trong ví dụ chỉ là timestamp mẫu.

**Phân biệt:**

- `setTime(long)` và `setLastModifiedTime(FileTime)` đều ảnh hưởng mốc sửa đổi, nhưng cách biểu diễn khi serialize tùy API/extra fields và khả năng của format.
- Chọn một nguồn dữ liệu có ý nghĩa rõ, tránh vô tình đặt hai mốc sửa đổi mâu thuẫn.
- Mốc creation/access không bắt buộc có trong mọi archive; `getCreationTime()`/`getLastAccessTime()` có thể trả null.
- Khi đối chiếu archive chạy trên nhiều OS hoặc timezone, nên so thời điểm qua `Instant` và chấp nhận độ chính xác theo format. **Không bắt buộc** mọi file ZIP giữ được chính xác nanosecond.
- Các timestamp trong một archive không phải bằng chứng an ninh: người tạo ZIP có thể đặt chúng thành giá trị tùy ý.

Nếu bảo toàn metadata có ý nghĩa pháp lý/nghiệp vụ, hãy định nghĩa schema manifest riêng, kiểm soát nguồn và chữ ký; đừng dựa hoàn toàn vào timestamp ZIP.

## 7. Ví dụ Java 17+ hoàn chỉnh: ZIP UTF-8 và ZIP IBM437

Ví dụ tạo **hai archive độc lập**:

1. ZIP UTF-8 với entry `"tài-liệu/đề-cương.txt"`, comment `"Bản mẫu"`, timestamp cố định.
2. ZIP legacy dùng `IBM437` với entry `"café.txt"`, comment ASCII.
3. Nội dung payload của **cả hai** đều mã hóa UTF-8, bất kể charset của entry name.
4. Mở lại bằng `ZipFile(..., charset)` đúng với archive đã tạo; đọc metadata, tính lại CRC-32 và in ra payload.

Lưu thành **`ZipEntryMetadataDemo.java`**:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;
import java.time.Instant;
import java.util.zip.CRC32;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import java.util.zip.ZipOutputStream;

public class ZipEntryMetadataDemo {
    private static final Instant FIXED_TIME =
            Instant.parse("2024-01-02T03:04:06Z");
    private static final byte[] PAYLOAD =
            "Xin chào".getBytes(StandardCharsets.UTF_8);

    private static void writeArchive(
            Path path, Charset nameCharset, String name, String entryComment)
            throws IOException {
        try (ZipOutputStream out = new ZipOutputStream(
                Files.newOutputStream(path), nameCharset)) {
            out.setComment("Archive note");
            ZipEntry entry = new ZipEntry(name);
            entry.setLastModifiedTime(FileTime.from(FIXED_TIME));
            entry.setComment(entryComment);
            out.putNextEntry(entry);
            out.write(PAYLOAD);
            out.closeEntry();
        }
    }

    private static void inspect(Path path, Charset nameCharset, String name)
            throws IOException {
        try (ZipFile zip = new ZipFile(path.toFile(), nameCharset)) {
            ZipEntry entry = zip.getEntry(name);
            if (entry == null) {
                throw new IOException("Missing entry: " + name);
            }
            byte[] bytes;
            try (InputStream in = zip.getInputStream(entry)) {
                bytes = in.readAllBytes();
            }
            CRC32 check = new CRC32();
            check.update(bytes);
            System.out.println("name=" + entry.getName());
            System.out.println("entry-comment=" + entry.getComment());
            System.out.println("archive-comment=" + zip.getComment());
            System.out.println("mtime=" + entry.getLastModifiedTime().toInstant());
            System.out.println("crc-valid=" + (check.getValue() == entry.getCrc()));
            System.out.println("payload=" +
                    new String(bytes, StandardCharsets.UTF_8));
        }
    }

    public static void main(String[] args) throws IOException {
        Path modern = Files.createTempFile("utf8-zip-", ".zip");
        Path legacy = Files.createTempFile("legacy-zip-", ".zip");
        try {
            writeArchive(modern, StandardCharsets.UTF_8,
                    "tài-liệu/đề-cương.txt", "Bản mẫu");
            writeArchive(legacy, Charset.forName("IBM437"),
                    "café.txt", "Example");
            System.out.println("[UTF-8]");
            inspect(modern, StandardCharsets.UTF_8,
                    "tài-liệu/đề-cương.txt");
            System.out.println("[IBM437]");
            inspect(legacy, Charset.forName("IBM437"), "café.txt");
        } finally {
            Files.deleteIfExists(modern);
            Files.deleteIfExists(legacy);
        }
    }
}
```

Biên dịch/chạy (JDK 17 trở lên, có charset IBM437):

```bash
javac -encoding UTF-8 ZipEntryMetadataDemo.java
java ZipEntryMetadataDemo
```

Stdout đã được biên dịch và chạy kiểm chứng:

```text
[UTF-8]
name=tài-liệu/đề-cương.txt
entry-comment=Bản mẫu
archive-comment=Archive note
mtime=2024-01-02T03:04:06Z
crc-valid=true
payload=Xin chào
[IBM437]
name=café.txt
entry-comment=Example
archive-comment=Archive note
mtime=2024-01-02T03:04:06Z
crc-valid=true
payload=Xin chào
```

Diễn giải:

- `ZipOutputStream(..., StandardCharsets.UTF_8)` ghi tên/comment UTF-8. Với tên tiếng Việt, các byte thường có độ dài khác `String.length()`; bên đọc phải hiểu encoding đúng.
- `Charset.forName("IBM437")` là lựa chọn cho archive thứ hai, nơi `é` được biểu diễn trong bảng mã đó; entry name vẫn được API Java trả về dưới dạng `String` Unicode đúng nếu dùng đúng charset.
- `PAYLOAD` luôn được tạo bằng `getBytes(UTF_8)`. Charset ZIP header không tác động lên nó, vì `ZipOutputStream.write(byte[])` làm việc trên bytes.
- `ZipEntry.setLastModifiedTime(FileTime)` đặt mốc sửa đổi cố định. JDK được kiểm thử trả lại đúng `Instant` trong ví dụ, nhưng các archive từ công cụ khác có thể thiếu extra fields hoặc có độ phân giải khác.
- `ZipEntry.setComment()` và `ZipOutputStream.setComment()` là metadata riêng; đọc qua `ZipFile` cho thấy hai cấp comment.
- `CRC32` tính trên **bytes đã giải nén**, được so với `entry.getCrc()`. Kết quả `true` xác nhận checksum trùng; không chứng minh archive không bị sửa một cách cố ý.
- Ví dụ chỉ có hai archive một-entry, vì thế không cần code xử lý trùng tên, quota, zip bomb hay giải nén ra filesystem; các phần sau sẽ mô tả yêu cầu cho đầu vào không tin cậy.

**Giới hạn của demo:** `ZipFile` mở central directory hoàn chỉnh và ví dụ dùng `readAllBytes()` vì payload nhỏ, do chính chương trình tạo. Với ZIP lớn, không được gọi `readAllBytes()` cho từng entry tùy ý nếu chưa giới hạn kích thước thực tế. Hãy đọc theo chunk với quota.

## 8. ZipFile so với ZipInputStream: metadata không giống nhau ở mọi thời điểm

Hai mô hình đọc:

**`ZipFile`** truy cập thông tin central directory của ZIP. Nó thường phù hợp khi cần liệt kê nhiều entries, lấy comment, size, CRC, compressed size, hoặc truy cập một entry theo tên:

```java
try (ZipFile zip = new ZipFile(archive.toFile(),
        StandardCharsets.UTF_8)) {
    ZipEntry found = zip.getEntry("README.md");
    if (found != null) {
        System.out.println("size=" + found.getSize());
        try (InputStream input = zip.getInputStream(found)) {
            // Xử lý input theo chunk/quota.
        }
    }
}
```

Đây là snippet; `archive` phải là `Path` hợp lệ. `ZipFile.close()` sẽ giải phóng resource gắn với file nén; đóng stream từng entry khi dùng xong giúp code rõ ràng.

**`ZipInputStream`** đọc tuần tự, entry theo entry:

```java
try (ZipInputStream in = new ZipInputStream(
        Files.newInputStream(archive), StandardCharsets.UTF_8)) {
    ZipEntry entry;
    while ((entry = in.getNextEntry()) != null) {
        System.out.println(entry.getName());
        byte[] buf = new byte[8192];
        long expanded = 0;
        for (int n; (n = in.read(buf)) != -1; ) {
            expanded += n;
            if (expanded > MAX_UNCOMPRESSED_BYTES) {
                throw new IOException("Entry quá lớn");
            }
            // Xử lý buf[0..n) với sink theo yêu cầu.
        }
        in.closeEntry();
    }
}
```

Đây là **snippet**, cần định nghĩa hằng `MAX_UNCOMPRESSED_BYTES` theo quota và import phù hợp. `ZipInputStream` đọc local file headers; một số metadata (đặc biệt các trường chỉ có trong central directory) có thể chưa biết trước khi đọc xong entry hoặc không được cung cấp giống `ZipFile`. Vì thế không mặc định `getComment()` hay `getSize()` luôn có giá trị cho mỗi entry khi đang streaming.

Nếu cần comment của archive và metadata đầy đủ từ central directory, thường chọn `ZipFile`. Với file được nhận từ một stream không seekable, `ZipInputStream` có thể phù hợp nhưng ứng dụng vẫn phải thiết kế xác thực, quota, xử lý lỗi và chính sách EOF.

## 9. DEFLATED so với STORED và các trường phải khai báo

`ZipEntry` có hai method phổ biến được API Java tiêu chuẩn hỗ trợ:

- **`ZipEntry.DEFLATED`**: dữ liệu được nén DEFLATE. Với `ZipOutputStream`, JDK có thể tính CRC/kích thước khi hoàn tất entry nếu chưa khai báo trước; writer thường không cần biết mọi thông tin từ đầu.
- **`ZipEntry.STORED`**: không nén nội dung. Khi dùng `ZipOutputStream` với STORED, trước `putNextEntry` phải khai báo đầy đủ `size`, `compressedSize` và `CRC-32` theo yêu cầu API; cả hai kích thước bằng nhau.

Ví dụ STORED cho một mảng byte đã có:

```java
byte[] data = "Hello".getBytes(StandardCharsets.UTF_8);
CRC32 checksum = new CRC32();
checksum.update(data);

ZipEntry entry = new ZipEntry("hello.txt");
entry.setMethod(ZipEntry.STORED);
entry.setSize(data.length);
entry.setCompressedSize(data.length);
entry.setCrc(checksum.getValue());

out.putNextEntry(entry);
out.write(data);
out.closeEntry();
```

Đây là **snippet**: `out` phải là `ZipOutputStream` đang mở và có import `ZipEntry`, `CRC32`, `StandardCharsets`. Với STORED, cung cấp sai size/CRC hoặc ghi sai số byte có thể khiến thư viện ném `ZipException`. Với DEFLATED, size/compressed size phụ thuộc mức nén và nội dung; không suy kích thước nén từ số ký tự.

Đừng tự tin rằng mọi entry đọc từ nguồn ngoài đều dùng DEFLATED/STORED mà bỏ qua `getMethod()`. ZIP có nhiều extension và method khác; Java `java.util.zip` không phải thư viện hỗ trợ mọi biến thể ZIP (ví dụ nhiều định dạng mã hóa hoặc method nén mở rộng).

## 10. Extra fields: khi nào cần và vì sao phải parse cẩn thận?

ZIP extra fields là những vùng byte mở rộng trong header/central directory. Mỗi mục thường có header ID, kích thước dữ liệu và payload riêng. Ví dụ các nhóm thường gặp:

| ID minh họa | Ý nghĩa phổ biến | Lưu ý |
| --- | --- | --- |
| `0x5455` | Extended timestamp (thường gọi UT). | Có thể chứa modification/access/creation theo độ dài và vị trí. |
| `0x000A` | NTFS extra field. | Có thể chứa timestamp dạng Windows FILETIME. |
| `0x0001` | ZIP64 extended information. | Dùng để biểu diễn size/offset vượt giới hạn header cổ điển. |
| `0x7075` | Unicode Path Extra Field. | Bổ sung tên Unicode, có version và CRC kiểm tra tên gốc. |
| `0x6375` | Unicode Comment Extra Field. | Bổ sung comment Unicode, không đồng nghĩa mọi reader sẽ tự dùng. |

Ví dụ truy xuất raw extras:

```java
byte[] extra = entry.getExtra();
if (extra != null) {
    System.out.println("extra bytes=" + extra.length);
}
```

Đây là snippet; `entry` là `ZipEntry`. **Không giả định** mỗi extra field luôn có độ dài mong đợi. Khi cần tự parse:

1. Giới hạn tổng số byte extra theo cấu trúc ZIP.
2. Với mỗi field, kiểm tra còn ít nhất 4 byte header (ID và data length).
3. Đọc số nguyên header theo thứ tự byte **little-endian** của ZIP.
4. Trước khi đọc payload, kiểm tra data length không vượt vùng còn lại.
5. Chấp nhận các field lạ bằng cách bỏ qua có giới hạn; không cast hoặc cấp phát bộ nhớ không kiểm soát.
6. Đối với Unicode extras, kiểm tra version, CRC và quan hệ với tên gốc trước khi tin dữ liệu đó.
7. Không mặc định `ZipEntry.getExtra()` phản ánh y nguyên toàn bộ dữ liệu raw ban đầu sau khi JVM đã diễn giải các timestamp/field đặc biệt.

`setExtra(byte[])` dành cho metadata nhị phân có cấu trúc cụ thể; nó không tự biến bytes bất kỳ thành những thuộc tính được ZIP và mọi công cụ hiểu đúng. Nếu cần bảo tồn đầy đủ các external attributes/permission/ownership đặc thù của ZIP, có thể phải dùng công cụ/libraries chuyên dụng và kiểm tra khả năng tương thích ngoài `java.util.zip`.

## 11. Comment và encoding: các lỗi thường xuất hiện

Những lỗi điển hình:

- Ghi tên UTF-8 nhưng bên đọc legacy cố decode bằng code page khác ⇒ chữ có dấu biến thành chuỗi rác hoặc lỗi.
- Ghi entry name có ký tự không biểu diễn được trong charset legacy ⇒ writer có thể ném exception hoặc không tạo được archive như dự kiến.
- Nhầm `ZipEntry.comment` với `ZipOutputStream.setComment` ⇒ chỉ đọc archive comment không thấy chú thích riêng của entry.
- Cho rằng `ZipInputStream.getNextEntry()` cung cấp đủ comment metadata của central directory ⇒ có thể nhận `null`.
- Ghi comment vượt 65.535 **byte mã hóa** ⇒ writer từ chối hoặc archive không hợp lệ.
- Lưu tên tiếng Việt nhưng quên rằng một số phần mềm archive cũ không có cơ chế xác định encoding phù hợp.
- Tạo file ZIP bằng một thư viện rồi đọc lại bằng một thư viện khác; Unicode extras, bit flag, timestamp và external attributes không thống nhất ⇒ kết quả khác kỳ vọng.

Để có khả năng liên thông tốt, kiểm thử **cả hai chiều**: Java tạo ZIP → công cụ đích đọc; công cụ đích tạo ZIP → Java đọc. Bộ fixture nên gồm tên ASCII, tiếng Việt có dấu, ký tự bổ sung (emoji nếu được hỗ trợ), tên dài, comment có dấu, timestamp, thư mục rỗng và entries không có directory entry cha.

## 12. Giải nén an toàn: tên entry không phải đường dẫn đáng tin cậy

Một archive do người ngoài cung cấp có thể chứa tên như:

```text
../outside.txt
/absolute/path.txt
C:/Windows/target.txt
safe/../../escape.txt
folder\..\escape.txt
```

**Không được** nối trực tiếp tên entry với root rồi ghi file mà không kiểm tra. Hành vi ánh xạ tên ZIP sang đường dẫn thực phụ thuộc OS và chính sách thư mục.

Một chiến lược cơ bản:

1. Định nghĩa một thư mục đích cố định, được kiểm soát, ví dụ `targetRoot.toAbsolutePath().normalize()`.
2. Chỉ chấp nhận entry name theo định dạng tương đối với dấu `/`; từ chối absolute path, drive prefix, dấu `\` nếu không có lý do hỗ trợ và những thành phần `..`.
3. Dùng `Path.resolve(name).normalize()` và xác minh đường dẫn kết quả vẫn nằm dưới root **bằng `startsWith(Path)` trên các Path đã normalize**, không so prefix của string.
4. Trước khi ghi, bảo vệ khỏi symlink đã có trong đường dẫn đích; `normalize()` là kiểm tra **cú pháp**, không loại bỏ race symlink/TOCTOU.
5. Dùng thư mục giải nén riêng, permission phù hợp, chính sách ghi đè rõ ràng; khi có nguồn không tin cậy cần giới hạn tài nguyên và cân nhắc API an toàn hơn (ví dụ cơ chế resolve tương đối có kiểm soát / `SecureDirectoryStream` nếu provider hỗ trợ).
6. Từ chối tên trùng hoặc trùng sau normalization/case-fold trên filesystem mục tiêu, tránh ghi đè file không mong muốn.

Ví dụ minh họa:

```java
// Snippet: trustedRoot là Path được ứng dụng kiểm soát.
Path root = trustedRoot.toAbsolutePath().normalize();
String rawName = entry.getName();

if (rawName.startsWith("/") || rawName.contains("\\") ||
        rawName.contains("..") || rawName.indexOf('\0') >= 0) {
    throw new IOException("Tên entry không được phép");
}

Path destination = root.resolve(rawName).normalize();
if (!destination.startsWith(root) || destination.equals(root)) {
    throw new IOException("Entry nằm ngoài thư mục đích");
}
```

Đây là **snippet phòng thủ sơ cấp** và có chủ đích từ chối rộng (ví dụ chuỗi chứa `..` trong một tên file bình thường cũng có thể bị từ chối). Nó không tự ngăn mọi symlink/TOCTOU khi filesystem bị thay đổi đồng thời; trước khi dùng production, cần chính sách phù hợp platform/provider và thư mục đích do ứng dụng sở hữu. Đừng coi ví dụ này là bộ giải nén hoàn chỉnh.

## 13. ZIP bomb, CRC và metadata không đáng tin

Ngay cả khi entry không có path traversal, archive có thể có **compressed size nhỏ nhưng uncompressed size rất lớn**. Một file vài KB có thể nở thành nhiều GB khi giải nén. Ngoài ra còn có archive nhiều entry, entry lồng archive khác, tên rất dài và cấu trúc hỏng.

Các giới hạn nên định nghĩa:

| Rủi ro | Biện pháp |
| --- | --- |
| Entry không nén quá lớn | Đặt quota bytes sau giải nén **trong lúc streaming**. |
| Tổng bytes toàn ZIP vượt hạn mức | Đếm tổng bytes cho mọi entry và dừng khi vượt quota. |
| Quá nhiều entry | Giới hạn số entry và độ sâu thư mục. |
| Tỷ lệ nén bất thường | Đặt ngưỡng/rủi ro compression ratio, nhưng **không chỉ dựa một ratio**. |
| Thời gian giải nén quá lâu | Deadline/quota CPU, xử lý có giới hạn, không block dịch vụ. |
| Entry hỏng hoặc CRC sai | Kiểm tra, hủy toàn bộ dữ liệu đầu ra chưa được commit và ghi log hợp lý. |
| Extra fields/metadata kỳ lạ | Validate độ dài và bỏ qua field không hỗ trợ theo chính sách. |
| File trùng tên hoặc ghi đè | Kiểm tra tập tên đã normalize và dùng chế độ tạo file an toàn. |

**CRC-32 không phải cơ chế xác thực nguồn gốc.** Nó giúp phát hiện lỗi dữ liệu thông thường, nhưng người tạo archive có thể chỉnh payload và tính lại CRC. Khi cần tin cậy nội dung, dùng chữ ký số/hàm băm mật mã gắn với manifest do nguồn đáng tin xác thực, hoặc cơ chế bảo vệ riêng của hệ thống. ZIP cũng không cung cấp giao ước rằng timestamp/comment/file name đáng tin để ra quyết định bảo mật.

Nếu `entry.getSize()` là `-1` hoặc bị giả mạo, không được cấp phát theo size và tin rằng mọi thứ an toàn; quota phải dựa trên **số byte thực tế** đang đi qua stream.

## 14. Cách giữ metadata khi sao chép hoặc repack ZIP

Khi đọc archive đầu vào rồi tạo archive khác, ứng dụng có thể muốn giữ:

- Tên entry đã được decode chính xác.
- Quan hệ thư mục và dấu `/` khi là directory entry.
- Comment riêng của entry và comment archive.
- Modification/access/creation times nếu có.
- Compression method, size, CRC và extra fields khi tương thích.
- Permission/owner/external attributes nếu nghiệp vụ yêu cầu, thường cần giải pháp chuyên dụng vì API tiêu chuẩn không bao quát mọi trường.

Tuy nhiên **không nên copy tất cả metadata bằng cách gọi setter vô điều kiện**:

1. Nếu tên đã decode sai do charset, ghi lại bằng UTF-8 sẽ “đóng băng” tên sai.
2. Đừng ép `STORED` nếu chưa có size/CRC tương thích.
3. ZipEntry của một archive đã nén có thể có size/compressed size/CRC không còn phù hợp nếu payload được thay đổi hoặc đổi compression level.
4. Extra fields có thể chứa dữ liệu gắn với layout cũ, offsets, tên file hoặc timestamp; copy raw bytes mù quáng có thể tạo metadata bất nhất.
5. Metadata không hợp lệ cần được từ chối/làm sạch với chính sách rõ. Giữ external symlink/permission ngoài ý muốn có thể gây rủi ro khi extract.

Với archive chuyển đổi sang chuẩn UTF-8, hãy **giải mã tên cũ đúng trước, chuẩn hóa quy tắc nội bộ, rồi ghi lại ZIP UTF-8 mới**. Với yêu cầu bảo tồn bit-identical archives, quá trình unpack/repack bằng API mức cao không phù hợp; cần copy bytes gốc hoặc công cụ biết bảo toàn cấu trúc.

## 15. Chọn API và quy ước khi thiết kế hệ thống

**Tạo ZIP mới dùng cho nhiều nền tảng:**

- Ưu tiên `StandardCharsets.UTF_8` và `ZipOutputStream`.
- Đặt tên entry dùng dấu `/`, không dùng đường dẫn tuyệt đối của hệ điều hành.
- Chỉ thêm metadata cần thiết, đồng thời mô tả rõ yêu cầu bên nhận.
- Đóng từng entry bằng `closeEntry()` và đóng `ZipOutputStream` qua `try-with-resources` để central directory được ghi hoàn chỉnh.
- Đặt giới hạn input/entry count/size; chuẩn hóa trùng tên và loại trừ các path không an toàn.

**Đọc ZIP legacy:**

- Dùng `ZipFile(file, charset)` nếu cần đầy đủ central directory và truy cập theo tên.
- Tôn trọng UTF-8 bit flag và chọn charset legacy đúng từ hợp đồng nguồn khi flag không bật.
- Kiểm tra tên, charset, comments, timestamps và method qua fixture thực tế.
- Xem metadata là tùy chọn/không tin cậy; không đưa raw entry name thẳng tới filesystem.

**Đọc ZIP streaming:**

- Dùng `ZipInputStream(input, charset)` khi cần xử lý tuần tự.
- Không dựa vào `getSize()`/comment luôn sẵn ngay tại `getNextEntry()`; thống kê bytes giải nén thực tế.
- Đảm bảo đọc hết/đóng entry và xử lý lỗi/EOF đúng.
- Cần entry count, quota toàn ZIP và giới hạn thời gian; không tạo một mảng kích thước theo metadata không tin cậy.

**Archive yêu cầu metadata giàu hơn chuẩn ZIP cơ bản:** cân nhắc library hỗ trợ external attributes, symlinks, encryption, ZIP64/Unicode extras theo nhu cầu cụ thể. Không cố làm `java.util.zip` hỗ trợ chức năng không được API cam kết.

## 16. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Tên entry tiếng Việt biến thành ký tự lạ | Giải mã sai charset khi ZIP legacy không bật bit UTF-8. | Biết charset nguồn, truyền rõ vào `ZipFile/ZipInputStream`. |
| Reader vẫn dùng UTF-8 dù truyền IBM437 | Entry có UTF-8/EFS flag. | Tuân thủ flag; không ép decode legacy khi flag chỉ định UTF-8. |
| Không tạo được ZIP với tên Unicode | Charset được chọn không biểu diễn được tên/comment. | Chọn UTF-8 cho ZIP mới. |
| Payload text đọc sai dù tên đúng | Dùng charset tên entry để giải mã nội dung. | Tách charset header và charset payload; xác định encoding file bên trong. |
| `getComment()` trả null | Không có comment hoặc đang đọc từ nguồn thiếu metadata central directory. | Coi comment tùy chọn, dùng `ZipFile` khi cần. |
| `getSize()` trả -1 | Metadata chưa biết trong bối cảnh streaming. | Đếm bytes thực tế và giới hạn quota. |
| CRC mismatch / `ZipException` | File nén hỏng, thiếu bytes hoặc metadata không khớp. | Từ chối dữ liệu, không commit output dở dang. |
| Timestamp sai lệch | DOS time, múi giờ, độ phân giải hoặc extra fields khác nhau. | Thống nhất time policy, dùng Instant/FileTime, test roundtrip. |
| Extra fields không nhận biết | Metadata extension của công cụ ZIP khác. | Parse theo ID/length có giới hạn hoặc dùng thư viện phù hợp. |
| Giải nén thoát khỏi thư mục đích | Entry name có `..`/absolute path/symlink. | Validate path, root-boundary và bảo vệ khỏi TOCTOU. |
| Disk đầy khi extract | Zip bomb hoặc không có quota. | Giới hạn bytes giải nén thực và tổng dung lượng. |
| Không thấy thư mục rỗng | ZIP chỉ ghi file hoặc thiếu directory entry. | Ghi explicit directory entry khi cần bảo toàn thư mục rỗng. |
| ZIP mở được trong Java nhưng không ở công cụ khác | Hỗ trợ method, charset, extras hoặc ZIP64 khác nhau. | Xác minh compatibility trên tool/platform đích. |

## 17. Bài tập thực hành

**Bài 1 — Charset của tên và payload.** Đổi tên entry UTF-8 thành `"ảnh/đồ-thị.txt"` và payload thành `"Đồ thị mẫu"`. Kiểm tra việc đổi charset của payload **không** làm đổi cách decode tên entry; nêu nơi mỗi charset được thiết lập.

**Bài 2 — ZIP IBM437.** Với entry `"café.txt"`, đọc bằng charset `IBM437` và so sánh với trường hợp dùng constructor UTF-8. Dự đoán việc đọc sai có thể báo lỗi hoặc tên không đúng. Không dùng tên có dấu tiếng Việt không tồn tại trong IBM437 để thử ghi legacy mà không xử lý exception.

**Bài 3 — Metadata STORED.** Dùng `CRC32` và `ZipEntry.STORED` để thêm entry `"raw.bin"` chứa 10 byte. Tạo đúng size, compressed size, CRC trước `putNextEntry`; thử khai báo CRC sai để quan sát lỗi và giải thích vì sao CRC chưa phải chữ ký số.

**Bài 4 — Timestamp/extra.** Tạo entry có thời gian sửa đổi cố định, đọc lại bằng `ZipFile` và thống kê `getTime()`/`getLastModifiedTime()`/`getExtra()`. So sánh trên hai chương trình ZIP khác nhau để tìm khác biệt về độ chính xác và extra fields.

**Bài 5 — Directory entries.** Tạo ZIP chỉ có `"empty/"` và `"docs/info.txt"`. Kiểm tra `isDirectory()`, nội dung và cách giải nén giữ thư mục rỗng. Vì sao `"docs/info.txt"` không đòi archive phải có entry riêng `"docs/"`?

**Bài 6 — Giải nén an toàn.** Xây một hàm `safeExtract` có kiểm tra absolute path, thành phần `..`, symlink, trùng tên và giới hạn 100 MiB uncompressed tổng. Dùng archive thử nghiệm có `"../escape.txt"` để kiểm tra bị từ chối mà không ghi bất kỳ file ngoài root.

**Bài 7 — ZIP bomb.** Mô phỏng entry nhỏ khi nén nhưng có nhiều byte lặp khi giải nén. Đếm bytes thực tế trong vòng đọc, dừng theo quota dù `entry.getSize()` thiếu hoặc sai. Chỉ thử trong thư mục tạm có giới hạn dung lượng, không dùng dữ liệu production.

**Bài 8 — Chuyển encoding legacy sang UTF-8.** Nhận file ZIP có tên IBM437, giải mã đúng, tạo ZIP mới UTF-8 với tên Unicode và comment phù hợp. Đo khả năng đọc trên các công cụ mục tiêu và kiểm tra metadata đã được giữ/chuyển đổi theo chính sách.

### Câu hỏi tự kiểm tra

1. Charset nào điều khiển tên entry và charset nào điều khiển dữ liệu trong entry?
2. EFS/UTF-8 bit 11 cho bên đọc biết điều gì?
3. Vì sao truyền charset IBM437 không nên override tên đã được đánh dấu UTF-8?
4. ZIP entry comment khác archive comment ở đâu?
5. Khi `ZipInputStream.getNextEntry()` trả một entry, mọi size/CRC/comment đã chắc chắn sẵn sàng chưa?
6. Khi nào cần đặt trước size/compressed size/CRC cho STORED?
7. `FileTime` và các extra fields có bảo toàn timestamp nanosecond trên mọi OS không?
8. CRC-32 có chống được người tấn công chỉnh sửa archive rồi tính lại CRC không?
9. Vì sao `Path.normalize()` chưa đủ để chống mọi symlink race khi giải nén?
10. Nên dùng `ZipFile` hay `ZipInputStream` khi cần archive comment và tra cứu entry nhanh?

## 18. Tài liệu tham khảo

- [Java SE 21 — ZipEntry](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/zip/ZipEntry.html): name, comment, time, method, size, CRC và extra.
- [Java SE 21 — ZipFile](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/zip/ZipFile.html): mở ZIP với charset, tra cứu entry và archive comment.
- [Java SE 21 — ZipInputStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/zip/ZipInputStream.html): đọc tuần tự entry từ InputStream.
- [Java SE 21 — ZipOutputStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/zip/ZipOutputStream.html): ghi entry, charset, comments và hoàn tất central directory.
- [Java SE 21 — Charset](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/Charset.html): lựa chọn và xử lý mã hóa ký tự.
- [PKWARE APPNOTE — ZIP format specification](https://pkware.cachefly.net/webdocs/casestudies/APPNOTE.TXT): trường flag, metadata và extra field conventions của ZIP.

**Ghi nhớ:** Tên entry/comment là metadata của ZIP và có charset/flags riêng; payload là bytes độc lập. Chọn UTF-8 cho archive mới, đọc archive legacy bằng charset được xác minh, hiểu rằng timestamp/extra/size có thể thiếu hoặc khác nhau giữa công cụ, và luôn kiểm soát tên đường dẫn, quota và độ tin cậy trước khi giải nén.
