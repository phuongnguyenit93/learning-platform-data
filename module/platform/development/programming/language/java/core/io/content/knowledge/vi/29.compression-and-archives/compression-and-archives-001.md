# Phân biệt nén GZIP với archive ZIP trong Java I/O

## 1. Hai tên gần giống nhưng giải quyết hai bài toán khác nhau

**GZIP** và **ZIP** đều xuất hiện trong Java qua package `java.util.zip`, đều có thể dùng thuật toán nén **DEFLATE**, nhưng **không cùng định dạng** và **không có chung cấu trúc dữ liệu**.

- **GZIP (`.gz`):** định dạng **nén một luồng byte**. `GZIPOutputStream` nhận các byte và tạo luồng GZIP; `GZIPInputStream` đọc luồng GZIP, trả lại byte chưa nén. Nó không xây danh sách file/thư mục theo entry.
- **ZIP (`.zip`):** định dạng **archive/container** có thể chứa nhiều **entry** — tên file, đường dẫn tương đối, metadata và dữ liệu — trong một tập tin ZIP. `ZipOutputStream` tạo entry; `ZipInputStream` duyệt entry tuần tự; `ZipFile` tìm và đọc entry từ file archive.

Nói ngắn gọn: **GZIP nén nội dung của một luồng; ZIP đóng gói nhiều mục có tên và có thể nén riêng từng mục.**

Ví dụ sử dụng:

~~~text
report.txt
   |
   +-- GZIP --> report.txt.gz
                 (một luồng chứa dữ liệu report.txt đã nén)

docs/a.txt ----+
docs/b.txt ----+-- ZIP --> docs.zip
images/x.png --+             |
                             +-- docs/a.txt
                             +-- docs/b.txt
                             +-- images/x.png
~~~

Tên `report.txt.gz` là quy ước đặt tên bên ngoài; bản thân API `GZIPOutputStream` **không tạo file entry `report.txt` có thể duyệt như ZIP**. Bản GZIP không tự lưu cây thư mục mà chương trình giải nén dùng để tái tạo nhiều file.

## 2. Bảng so sánh tổng quan

| Tiêu chí | GZIP | ZIP |
|---|---|---|
| Mục đích | Nén **luồng dữ liệu** | **Đóng gói file/thư mục** vào archive, thường kết hợp nén |
| Nhiều file có tên riêng? | Không theo mô hình `GZIPInputStream` | Có, mỗi mục là một `ZipEntry` |
| Giữ cấu trúc thư mục | Không trực tiếp | Có thông qua tên entry/đường dẫn và metadata tương ứng |
| Kiểu dữ liệu ở Java | `GZIPInputStream`, `GZIPOutputStream` | `ZipInputStream`, `ZipOutputStream`, `ZipFile`, `ZipEntry` |
| Nén | Thường dùng DEFLATE bên trong GZIP wrapper | Entry có thể `DEFLATED` hoặc `STORED`; ZIP format có nhiều phương thức khác |
| Đọc theo thứ tự | Tự nhiên là đọc một stream | `ZipInputStream` đọc từng entry tuần tự |
| Tìm entry bằng tên | Không có entry/file index | `ZipFile.getEntry(name)` |
| Metadata riêng từng file | Không có `ZipEntry` | Tên, kích thước, CRC-32, thời gian, comment, extra fields tùy entry |
| Cấu trúc kết thúc | Trailer CRC-32 và kích thước nội dung (modulo 2³²) | Central directory / end-of-central-directory của archive |
| Đuôi thường gặp | `.gz`, `.tgz`, `.tar.gz` | `.zip`, `.jar` |
| Phù hợp | Nén log, response body, một luồng lớn | Gói nhiều tài liệu, backup/archive, thư mục tải về |
| Bảo mật dữ liệu | Không mặc nhiên mã hóa/xác thực | Không mặc nhiên mã hóa/xác thực |

**Lưu ý:** một số ứng dụng có thể ghép nhiều **GZIP members** liên tiếp thành một luồng GZIP hợp lệ. Điều đó **không biến GZIP thành ZIP archive**: vẫn không có directory các entry, không có API tìm file theo tên như `ZipFile`.

## 3. Cấu trúc định dạng: GZIP wrapper và ZIP archive

### 3.1. GZIP

Một GZIP member thông thường được mô tả:

~~~text
+--------------------+
| GZIP header        |  magic bytes 1F 8B, flags, method, ...
+--------------------+
| Compressed payload |  DEFLATE-compressed bytes
+--------------------+
| GZIP trailer       |  CRC-32 + ISIZE (size mod 2^32)
+--------------------+
~~~

Phần header/trailer tạo **GZIP wrapper** xung quanh nội dung nén, giúp bên đọc biết cách nhận diện định dạng và kiểm tra checksum. GZIP không có danh sách file mang tên `docs/a.txt`, `docs/b.txt` như ZIP central directory. Định dạng GZIP có thể có một số optional header fields, nhưng không nên đồng nhất chúng với hệ thống entry của ZIP.

**CRC-32 là cơ chế kiểm tra lỗi vô tình, không phải mật mã xác thực**. Nếu file bị chỉnh sửa có chủ ý, checksum không cung cấp đảm bảo chống giả mạo.

### 3.2. ZIP

ZIP thường chứa nhiều record entry và một **central directory** gần cuối archive:

~~~text
+------------------------------+
| Local header: docs/a.txt     |
| Compressed data: a.txt       |
+------------------------------+
| Local header: docs/b.txt     |
| Compressed data: b.txt       |
+------------------------------+
| ...                          |
+------------------------------+
| Central directory            |
|   - tên và metadata entries  |
|   - offsets tới local records|
+------------------------------+
| End-of-central-directory     |
+------------------------------+
~~~

Mỗi entry có thể được **DEFLATED** hoặc **STORED** (không nén), tùy cấu hình. Một `ZipOutputStream` chưa được `finish()`/`close()` đầy đủ có thể chưa ghi xong directory, nên archive có thể không sử dụng được dù một số dữ liệu entry đã được xuất ra.

### 3.3. Magic bytes để nhận diện sơ bộ

- GZIP thường mở đầu bằng `1F 8B` (hex).
- ZIP có local file header thường mở đầu bằng `50 4B 03 04`, biểu diễn `PK` và phần còn lại. Một file ZIP rỗng có thể bắt đầu bằng end-of-central-directory signature khác.

**Không dùng magic bytes như một phép xác thực đầy đủ.** Chúng chỉ là kiểm tra định dạng sơ bộ; nội dung vẫn có thể bị lỗi, thiếu, giả mạo hoặc không tương thích.

## 4. Java API tương ứng: cùng package nhưng khác semantics

Package `java.util.zip` có các lớp sau:

| API | Vai trò |
|---|---|
| `GZIPOutputStream` | Nén các byte ghi vào thành một GZIP stream |
| `GZIPInputStream` | Giải nén một GZIP input stream thành byte |
| `ZipOutputStream` | Ghi ZIP archive với một hoặc nhiều `ZipEntry` |
| `ZipInputStream` | Đọc lần lượt các `ZipEntry` từ stream ZIP |
| `ZipFile` | Mở một file ZIP để liệt kê/tìm entry và mở stream đọc entry |
| `ZipEntry` | Đại diện một entry có tên/metadata trong ZIP |
| `Deflater`/`Inflater` | Nén/giải nén ở lớp thuật toán thấp hơn |
| `CRC32` | Tính checksum CRC-32 |

Không dùng `GZIPInputStream` để giải nén trực tiếp `.zip` và không dùng `ZipInputStream` để đọc trực tiếp `.gz`. Dù cả hai dùng DEFLATE trong nhiều trường hợp, **wrapper/container khác nhau**.

### ZIP có thể không nén

Theo Java 17, `ZipEntry` có `DEFLATED` và `STORED`:

~~~java
ZipEntry entry = new ZipEntry("image.png");
entry.setMethod(ZipEntry.STORED);
~~~

Đây là **mã minh họa, không độc lập**. Với `STORED`, `ZipOutputStream` yêu cầu đặt đúng size, compressed size và CRC trước khi `putNextEntry`; chỉ gọi `setMethod(STORED)` như trên rồi viết mà chưa có metadata sẽ gây lỗi. `DEFLATED` là phương thức mặc định của `ZipOutputStream` và thường tự tính metadata cần thiết sau khi ghi entry.

Vì vậy **ZIP không đồng nghĩa tất cả entry đều nén**; một archive có thể có entry lưu nguyên byte, hợp lý với ảnh/video đã nén sẵn.

## 5. GZIP trong Java: nén và giải nén một nội dung

Một chuỗi thao tác thông thường:

~~~java
// Tạo .gz từ một luồng byte:
try (InputStream in = Files.newInputStream(source);
     OutputStream out = new GZIPOutputStream(
             Files.newOutputStream(gzipPath))) {
    in.transferTo(out);
}

// Giải nén .gz về một luồng byte:
try (InputStream in = new GZIPInputStream(
             Files.newInputStream(gzipPath));
     OutputStream out = Files.newOutputStream(restoredPath)) {
    in.transferTo(out);
}
~~~

Đây là **mã minh họa trong một phương thức**, với `Path source`, `Path gzipPath`, `Path restoredPath` đã tồn tại và các import phù hợp. Nó xử lý **nội dung của một file**, không duyệt cây thư mục hay tự tạo những file con theo tên trong compressed stream.

**Tại sao cần `try-with-resources`?** `GZIPOutputStream` phải ghi đủ dữ liệu nén và trailer khi `finish()`/`close()`; đóng stream còn giải phóng tài nguyên của stream bên dưới. Nếu đọc `gzipPath` khi writer chưa finish/close, có thể gặp luồng chưa đầy đủ.

### `finish()` khác `flush()`

`GZIPOutputStream.finish()` hoàn tất GZIP stream nhưng **không đóng underlying OutputStream**. `close()` sẽ đóng filter và underlying stream. `flush()` không thay thế `finish()`: tùy cấu hình `syncFlush`, flush có thể chỉ đẩy output buffer hoặc yêu cầu `SYNC_FLUSH`, nhưng chưa nhất thiết ghi trailer kết thúc member.

Trong pipeline bình thường, **đóng GZIPOutputStream** ở cuối scope là lựa chọn đơn giản nhất; chỉ cần gọi `finish()` thủ công khi muốn hoàn tất GZIP mà còn giữ underlying stream cho tác vụ khác.

### Một file `.tar.gz` chứa nhiều file vì sao?

**TAR là archive; GZIP là nén.** Luồng xử lý thường là:

~~~text
docs/a.txt + docs/b.txt + dirs
        |
        v
TAR: đóng gói nhiều file/metadata thành một byte stream
        |
        v
GZIP: nén byte stream TAR
        |
        v
backup.tar.gz
~~~

Khi giải nén `.tar.gz`, ta phải **GZIP-decompress trước**, rồi dùng **TAR reader** để lấy từng file. Java standard library (`java.util.zip`) có GZIP và ZIP nhưng **không cung cấp TAR parser/writer chuyên dụng**. Cần thư viện ngoài hoặc công cụ TAR phù hợp nếu muốn đọc TAR entries. Đặt đuôi `.tar.gz` không biến `GZIPInputStream` thành TAR parser.

## 6. ZIP trong Java: tạo nhiều entry

Muốn tạo ZIP bằng `ZipOutputStream`, mỗi file phải được đặt thành một `ZipEntry`:

~~~java
try (ZipOutputStream zip = new ZipOutputStream(
        Files.newOutputStream(zipPath), StandardCharsets.UTF_8)) {

    zip.putNextEntry(new ZipEntry("docs/a.txt"));
    Files.copy(pathA, zip);
    zip.closeEntry();

    zip.putNextEntry(new ZipEntry("docs/b.txt"));
    Files.copy(pathB, zip);
    zip.closeEntry();
}
~~~

Đây là **đoạn mã minh họa** với `Path zipPath`, `pathA`, `pathB` hợp lệ và import tương ứng. Các tên `docs/a.txt`/`docs/b.txt` trong ZIP là **đường dẫn entry**, không yêu cầu source files nằm trong một cây thư mục cùng tên.

Thứ tự:

1. `putNextEntry(entry)` mở entry mới.
2. `write(...)` hoặc `Files.copy(path, zip)` ghi byte của entry đó.
3. `closeEntry()` kết thúc entry hiện tại và chuẩn bị entry kế.
4. `close()`/`finish()` hoàn tất archive, bao gồm metadata directory.

Với entry thư mục, quy ước phổ biến là thêm dấu `/` cuối tên, ví dụ `docs/`, và không ghi dữ liệu như một file thường. Các tên entry nên dùng dấu `/` và đường dẫn **tương đối**, phù hợp tính di động.

### Metadata entry

`ZipEntry` hỗ trợ `getName()`, `isDirectory()`, `getSize()`, `getCompressedSize()`, `getCrc()`, `getTime()`, `getComment()` và các phương thức set tương ứng. Một số giá trị có thể là **-1** hoặc `null` nếu không biết. Với `ZipInputStream` đọc tuần tự, không được giả định toàn bộ metadata có sẵn từ local header tại thời điểm `getNextEntry()`.

Không suy luận nội dung file từ mỗi `ZipEntry.getName()` là đã được kiểm tra an toàn. Tên entry là **dữ liệu do archive cung cấp**, cần xác thực trước khi dùng làm file path.

## 7. ZIP: `ZipInputStream` khác `ZipFile`

Cả hai dùng đọc ZIP nhưng có khả năng khác:

### 7.1. ZipInputStream — đọc tuần tự

~~~java
try (ZipInputStream in = new ZipInputStream(
        Files.newInputStream(zipPath), StandardCharsets.UTF_8)) {

    ZipEntry entry;
    while ((entry = in.getNextEntry()) != null) {
        System.out.println("entry=" + entry.getName());

        // Đọc byte từ entry hiện tại tới EOF của entry.
        byte[] bytes = in.readAllBytes();
        // Chỉ dùng readAllBytes với entry nhỏ, đáng tin.
        in.closeEntry();
    }
}
~~~

Đoạn minh họa có `Path zipPath`, import thích hợp. `getNextEntry()` chuyển đến entry tiếp theo và trả `null` khi hết. `read(...) == -1` thể hiện **hết dữ liệu của entry đang đọc**, chưa chắc đã hết cả archive. Không dùng `available()` để xác định kích thước còn lại: với `ZipInputStream`, giá trị thường là 1 trước EOF entry và 0 sau EOF, **không phải số byte chưa đọc**.

Phù hợp khi đầu vào là **InputStream**, ví dụ upload ZIP qua network, hoặc muốn duyệt lần lượt mọi entry. Nó không phải API tra cứu ngẫu nhiên một entry theo tên từ trung tâm archive.

### 7.2. ZipFile — tra cứu và mở stream cho entry

~~~java
try (ZipFile zip = new ZipFile(zipPath.toFile(),
                              StandardCharsets.UTF_8)) {
    ZipEntry entry = zip.getEntry("docs/a.txt");
    if (entry != null) {
        try (InputStream in = zip.getInputStream(entry)) {
            // Đọc riêng nội dung docs/a.txt.
        }
    }
}
~~~

Đoạn minh họa có `Path zipPath`. `ZipFile` đọc metadata archive để tìm entry, gọi `getEntry(name)`, `entries()` hay `stream()`, và mở `InputStream` cho từng entry được chọn. Nó thường phù hợp nếu cần **chọn file theo tên** hoặc cần duyệt danh sách entry trong archive trên đĩa.

Đóng `ZipFile` cũng đóng các `InputStream` đã lấy qua `getInputStream(entry)`. Không giữ các stream đó để đọc sau khi `ZipFile` đã đóng. Trong thực tế, `ZipInputStream` duyệt các local entry header, còn `ZipFile` dùng central directory: hai cách có thể thể hiện **metadata khác nhau với archive được chế tạo bất thường**, cần chú ý khi kiểm tra archive không tin cậy.

### Chọn API nào?

| Đầu vào và nhu cầu | Phương án |
|---|---|
| Một luồng bytes GZIP | `GZIPInputStream` |
| Ghi một luồng GZIP | `GZIPOutputStream` |
| Nhận ZIP từ stream/upload và duyệt entry tuần tự | `ZipInputStream` |
| Tạo ZIP nhiều file | `ZipOutputStream` |
| Đọc file ZIP trên đĩa, cần lấy entry theo tên | `ZipFile` |
| Muốn xem ZIP như file system để duyệt `Path` | ZIP file system provider nếu môi trường có `jdk.zipfs` |

Không dùng `ZipFile` trực tiếp với một `InputStream` thuần túy; nó nhận tên file/`File` (và các overload liên quan), nên đầu vào mạng thường cần stream parse hoặc lưu tạm một file tùy nhu cầu.

## 8. Demo Java 17+ hoàn chỉnh: hai định dạng cạnh nhau

Để dễ chạy trên mọi máy có Java 17, ví dụ làm việc **trong bộ nhớ**, không cần tạo file/thư mục trên đĩa. Nó tạo và giải nén GZIP từ một payload, rồi tạo ZIP gồm hai file named entry và đọc chúng lại.

**Tên tệp: `GzipZipDemo.java`**

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.zip.GZIPInputStream;
import java.util.zip.GZIPOutputStream;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;
import java.util.zip.ZipOutputStream;

public class GzipZipDemo {
    public static void main(String[] args) throws Exception {
        byte[] payload =
                "Xin chao NIO".getBytes(StandardCharsets.UTF_8);

        ByteArrayOutputStream gzipData = new ByteArrayOutputStream();
        try (GZIPOutputStream gzip = new GZIPOutputStream(gzipData)) {
            gzip.write(payload);
        }

        try (GZIPInputStream gzip = new GZIPInputStream(
                new ByteArrayInputStream(gzipData.toByteArray()))) {
            System.out.println("gzip=" +
                    new String(gzip.readAllBytes(), StandardCharsets.UTF_8));
        }

        System.out.printf("gzip magic=%02X %02X%n",
                gzipData.toByteArray()[0] & 0xFF,
                gzipData.toByteArray()[1] & 0xFF);

        ByteArrayOutputStream zipData = new ByteArrayOutputStream();
        try (ZipOutputStream zip =
                new ZipOutputStream(zipData, StandardCharsets.UTF_8)) {

            zip.putNextEntry(new ZipEntry("docs/a.txt"));
            zip.write("Alpha".getBytes(StandardCharsets.UTF_8));
            zip.closeEntry();

            zip.putNextEntry(new ZipEntry("docs/b.txt"));
            zip.write("Beta".getBytes(StandardCharsets.UTF_8));
            zip.closeEntry();
        }

        try (ZipInputStream zip = new ZipInputStream(
                new ByteArrayInputStream(zipData.toByteArray()),
                StandardCharsets.UTF_8)) {
            ZipEntry entry;
            while ((entry = zip.getNextEntry()) != null) {
                String content = new String(zip.readAllBytes(),
                        StandardCharsets.UTF_8);
                System.out.println(entry.getName() + "=" + content);
                zip.closeEntry();
            }
        }

        byte[] zipBytes = zipData.toByteArray();
        System.out.printf("zip magic=%02X %02X %02X %02X%n",
                zipBytes[0] & 0xFF, zipBytes[1] & 0xFF,
                zipBytes[2] & 0xFF, zipBytes[3] & 0xFF);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac GzipZipDemo.java
java GzipZipDemo
~~~

**Stdout đã kiểm chứng bằng JDK:**

~~~text
gzip=Xin chao NIO
gzip magic=1F 8B
docs/a.txt=Alpha
docs/b.txt=Beta
zip magic=50 4B 03 04
~~~

Giải thích:

1. `GZIPOutputStream` chỉ nhận `payload` — một luồng nội dung; `GZIPInputStream` trả lại bytes của `Xin chao NIO`. Không có `ZipEntry` hay tên file bên trong dữ liệu ví dụ GZIP.
2. `ZipOutputStream` dùng `putNextEntry` để tạo **hai file mang tên riêng** trong archive; mỗi entry có dữ liệu và ranh giới.
3. `ZipInputStream.getNextEntry()` lần lượt trả `docs/a.txt` và `docs/b.txt`. `readAllBytes()` ở đây an toàn cho demo vì **chúng ta tự tạo dữ liệu rất nhỏ**; không áp dụng trực tiếp cho upload không đáng tin.
4. `closeEntry()` hoàn tất đọc/ghi entry theo vị trí hiện tại. `try-with-resources` hoàn tất GZIP/ZIP stream và đóng tài nguyên.
5. Magic bytes khác nhau (`1F 8B` vs `50 4B 03 04`) cho thấy không thể coi cả hai là cùng định dạng chỉ vì đều dùng DEFLATE.

## 9. Định dạng nào nén tốt hơn?

Không có đáp án tuyệt đối. Cả GZIP và ZIP thường dùng DEFLATE, nhưng **đơn vị nén và metadata** khác nhau:

- GZIP nén **một stream liên tục**; nếu kết hợp nhiều file bằng TAR rồi GZIP, compressor có thể tận dụng sự lặp lại dữ liệu gần nhau trên stream (trong giới hạn cửa sổ thuật toán).
- ZIP thường nén **mỗi entry riêng**, nên dễ duyệt hoặc lấy riêng entry, nhưng không tự dùng lịch sử dữ liệu của một entry khác cho entry hiện tại.
- ZIP phải lưu local headers, tên file và central directory, nên archive gồm rất nhiều file nhỏ có thể có overhead đáng kể.
- GZIP cũng có header/trailer; với dữ liệu rất nhỏ hoặc đã nén sẵn (PNG, JPEG, MP4…), kích thước sau nén có thể bằng hoặc **lớn hơn** ban đầu.
- Kết quả phụ thuộc compressor level, loại dữ liệu, kích thước, số lượng file và khả năng nén riêng từng file. So sánh **cùng tập dữ liệu và cùng yêu cầu chức năng** mới có ý nghĩa.

Đừng so `data.gz` nén một file với `bundle.zip` gồm nhiều file rồi kết luận thuật toán nào tốt hơn chỉ dựa vào kích thước.

### Chọn định dạng theo use case

**Chọn GZIP** nếu đầu vào đã là **một stream**: log stream, file text đơn lẻ, HTTP response content coding `gzip`, backup TAR đã đóng gói. Với HTTP `Content-Encoding: gzip`, response body được nén dưới dạng một luồng dữ liệu HTTP; header encoding không có ý rằng body trở thành ZIP archive chứa files.

**Chọn ZIP** nếu người dùng cần tải về **nhiều tệp**, giữ tên/đường dẫn và giải nén riêng từng tệp, hoặc cần API tìm một entry bằng tên. File `.jar` cũng dựa trên định dạng ZIP, bổ sung cấu trúc `META-INF` và semantics Java archive.

Khi yêu cầu **streaming xử lý** nhiều entry ngay từ network, `ZipInputStream` có thể thuận tiện; khi cần **random lookup** trên file đã lưu, `ZipFile` thường thích hợp hơn.

## 10. Charset và tên entry

Tên `ZipEntry` là **vấn đề riêng** với byte nội dung file:

- `new ZipOutputStream(out, StandardCharsets.UTF_8)` mã hóa tên entry theo UTF-8 nếu phù hợp.
- `new ZipInputStream(in, StandardCharsets.UTF_8)`/`new ZipFile(file, StandardCharsets.UTF_8)` giải mã tên entry theo charset đã chọn, nhưng nếu ZIP **language encoding flag** báo UTF-8 thì Javadoc áp dụng UTF-8 bất kể charset tùy chọn.
- Nội dung `docs/a.txt` có thể là UTF-8, UTF-16 hoặc dữ liệu nhị phân, **không bị quyết định** bởi charset truyền cho `ZipInputStream`.

Ví dụ tên entry `"tiếng-việt.txt"` có thể được mã hóa UTF-8, nhưng byte nội dung phải tự giải mã theo charset của file đó.

Đừng coi `ZipEntry.getName()` là chuỗi path an toàn chỉ vì đã giải mã đúng Unicode. Vẫn phải xác thực path trước khi giải nén xuống filesystem.

## 11. An toàn khi giải nén ZIP/GZIP từ nguồn không tin cậy

### 11.1. Zip Slip — đường dẫn traversal

Archive có thể cố tình chứa entry như `../../outside.txt` hoặc tên tuyệt đối `/tmp/target`. Nếu dùng trực tiếp `outputRoot.resolve(entry.getName())` mà không kiểm tra, chương trình có thể ghi **ra ngoài thư mục dự kiến**.

Kiểm tra cơ bản:

~~~java
Path root = outputDir.toAbsolutePath().normalize();
Path target = root.resolve(entry.getName()).normalize();

if (!target.startsWith(root) || target.equals(root)) {
    throw new IOException("Unsafe ZIP entry: " + entry.getName());
}
~~~

Đây là **đoạn mã minh họa**, biến `outputDir` và `ZipEntry entry` phải tồn tại. Kiểm tra này là **lớp bảo vệ cơ bản**, không phải toàn bộ giải pháp chống Zip Slip trên mọi OS. Phải cấm entry path tuyệt đối/drive prefix theo chính sách, kiểm tra symlink/hardlink/path components trong thư mục đích, tránh các thao tác tạo file race và dùng cơ chế filesystem an toàn. Với archive không đáng tin, nên giải nén vào thư mục riêng do ứng dụng kiểm soát, có chính sách chống symlink và giới hạn ghi.

### 11.2. Zip bomb/GZIP bomb

Một luồng nén nhỏ có thể bung thành dữ liệu cực lớn. Với ZIP còn có thể chứa **rất nhiều entry** làm cạn CPU, RAM hoặc storage.

Cần giới hạn:

1. **Tổng số byte giải nén** cho cả archive.
2. **Số byte giải nén tối đa trên mỗi entry**.
3. **Số lượng entry**, độ dài tên/path và độ sâu thư mục.
4. **Thời gian xử lý/deadline**, quota disk và memory.
5. Khi thích hợp, **tỷ lệ nén bất thường**, nhưng không chỉ tin vào ratio hoặc metadata khai báo.
6. Số byte đếm được **thực sự trong lúc stream đọc**, vì `ZipEntry.getSize()` có thể là `-1` hoặc dữ liệu khai báo không đáng tin.

Dùng `readAllBytes()` trên upload nén không có giới hạn có thể làm hết heap. Thay vào đó, đọc theo chunk cố định với `read(byte[])`, kiểm đếm rồi mới ghi ra output. Nguyên tắc này đúng cả với `GZIPInputStream` và `ZipInputStream`.

### 11.3. CRC-32 không xác thực nguồn

CRC-32 trong GZIP/ZIP dùng phát hiện lỗi dữ liệu truyền/lưu trữ; **không chống giả mạo có chủ đích**. Khi yêu cầu bảo đảm file đến từ nguồn đáng tin và chưa bị sửa có chủ đích, dùng cơ chế chữ ký số/MAC hoặc checksum cryptographic đã được xác thực bằng kênh tin cậy khác. ZIP encryption không có nghĩa `java.util.zip` cung cấp sẵn API password giải mã mọi ZIP có mật khẩu; JDK 17 standard ZIP API không phải thư viện encryption ZIP tổng quát.

### 11.4. Đọc/ghi đúng tài nguyên

- Dùng `try-with-resources` để close các stream và `ZipFile`.
- Nếu tạo ZIP/GZIP và cần đọc output ngay, hoàn tất `close()`/`finish()` trước.
- Tránh ghi archive dưới cùng path của tệp nguồn mà bạn đang đọc; có thể làm hỏng dữ liệu.
- Với ZIP streaming, đóng entry bằng `closeEntry()` đúng lúc.
- Với ZIP entry có metadata thiếu, **không tự tin** vào kích thước để cấp phát mảng lớn.

## 12. Lỗi dễ gặp

1. **Cho rằng ZIP = GZIP chỉ khác phần mở rộng.** Sai: định dạng và cấu trúc khác.
2. **Dùng `GZIPInputStream` để đọc `.zip`.** Sai: GZIP wrapper không phải ZIP archive.
3. **Dùng `ZipInputStream` để đọc `.gz`.** Sai: một GZIP stream không có các local entry ZIP.
4. **Cho rằng mọi ZIP entry đều bị nén.** Sai: `STORED` lưu nội dung không nén.
5. **Cho rằng GZIP tự giữ nhiều file và tên thư mục.** Sai: GZIP là nén stream; muốn nhiều file thường dùng TAR trước.
6. **Nhầm `.tar.gz` là ZIP.** Sai: TAR đóng gói, GZIP nén TAR.
7. **Quên `putNextEntry()` trước khi ghi byte vào ZIP.** Sai thứ tự cấu trúc entry.
8. **Quên finish/close ZIP output rồi cố đọc ngay.** Archive có thể thiếu central directory.
9. **Cho rằng `ZipInputStream.read()==-1` tức hết cả archive.** Sai: thường là EOF của entry hiện tại.
10. **Dùng `available()` trên ZipInputStream để tính byte còn lại.** Sai: không phải remaining byte count.
11. **Cho rằng charset entry name là charset file content.** Sai: metadata tên và payload là hai việc khác.
12. **Giải nén `entry.getName()` không kiểm tra.** Dễ có Zip Slip/path traversal.
13. **Dùng `readAllBytes()` trên archive không tin cậy.** Dễ gây OOM/zip bomb.
14. **Coi CRC-32 là bảo mật hoặc chữ ký số.** Sai: checksum không bảo đảm tính xác thực.
15. **Cho rằng `ZipFile` nhận tùy ý InputStream.** Sai: `ZipFile` đọc file ZIP; với InputStream dùng `ZipInputStream`.
16. **Cho rằng file đã nén sẵn chắc chắn nhỏ thêm khi gzip/zip.** Sai: header và overhead có thể làm kích thước tăng.

## 13. Tự kiểm tra kiến thức

**Câu 1.** Cần nén riêng một file log để truyền trên HTTP, không cần giữ nhiều file. Chọn gì?

**Đáp án:** GZIP là lựa chọn tự nhiên cho stream; `GZIPOutputStream` hoặc HTTP `Content-Encoding: gzip` theo giao thức phù hợp.

**Câu 2.** Cần gửi cho người dùng thư mục chứa 30 file, khi giải nén cần giữ tên và cấu trúc. Chọn gì?

**Đáp án:** ZIP archive với `ZipOutputStream` tạo `ZipEntry` cho từng file/thư mục (hoặc TAR rồi GZIP nếu hệ sinh thái phù hợp), không dùng GZIP trực tiếp để ghi 30 file có tên riêng.

**Câu 3.** Tại sao `.tar.gz` có nhiều file dù GZIP nén một stream?

**Đáp án:** TAR đóng gói nhiều file thành một stream; GZIP nén stream TAR đó.

**Câu 4.** Với file ZIP trên đĩa, muốn đọc duy nhất entry `config/settings.json`, nên dùng gì?

**Đáp án:** `ZipFile.getEntry("config/settings.json")`, sau đó `getInputStream(entry)`. Với dữ liệu ZIP đang stream, dùng `ZipInputStream` duyệt entry.

**Câu 5.** Một ZIP có entry `../../secret.txt` có thể ghi thẳng xuống thư mục đích không?

**Đáp án:** Không. Phải xác thực path, chống traversal/symlinks và đặt giới hạn tài nguyên trước khi giải nén.

**Câu 6.** ZIP đang tạo với `ZipOutputStream`, đã ghi hết entry nhưng chưa đóng/finish. Có nên coi file ZIP đã hoàn chỉnh?

**Đáp án:** Không. Central directory và metadata kết thúc archive có thể chưa được ghi đầy đủ.

### Tài liệu chính thức Java 17

- [java.util.zip package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/package-summary.html)
- [GZIPInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/GZIPInputStream.html)
- [GZIPOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/GZIPOutputStream.html)
- [ZipInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipInputStream.html)
- [ZipOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipOutputStream.html)
- [ZipFile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipFile.html)
- [ZipEntry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipEntry.html)
