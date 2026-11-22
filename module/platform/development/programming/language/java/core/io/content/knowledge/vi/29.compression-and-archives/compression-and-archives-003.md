# ZipInputStream, ZipOutputStream và ZipEntry trong Java Core I/O

## 1. ZIP là gì và vì sao cần ba lớp này?

ZIP là định dạng **archive**: một tệp chứa nhiều entry (tệp, thư mục và metadata), có thể sử dụng nén cho từng entry. Java cung cấp thư viện chuẩn `java.util.zip` để đọc và tạo ZIP mà không cần một thư viện bên thứ ba.

Ba lớp quan trọng:

- **`ZipInputStream`**: đọc tuần tự từng entry từ một `InputStream` chứa dữ liệu ZIP. Nó phù hợp khi nguồn là stream và không cần truy cập ngẫu nhiên.
- **`ZipOutputStream`**: tạo archive ZIP và ghi lần lượt từng entry ra một `OutputStream`. Nó tự viết các cấu trúc ZIP cần thiết khi hoàn tất archive.
- **`ZipEntry`**: mô tả **một mục** trong archive: tên, phương thức nén, kích thước (nếu biết), CRC-32, thời gian, comment/extra field... Nó là metadata, **không phải stream byte nội dung**.

Hình dung:

```text
Ghi ZIP                                 Đọc ZIP
-------                                 -------
OutputStream (tệp/network/memory)       InputStream (tệp/network/memory)
       ^                                       |
       |                                       v
ZipOutputStream                         ZipInputStream
       ^                                       |
 putNextEntry(ZipEntry)                  getNextEntry() -> ZipEntry
 write(payload bytes)                   read(payload bytes)
 closeEntry()                            closeEntry()
       |                                       |
   [a.txt][b.bin][folder/]              xử lý lần lượt từng entry
```

Một ZIP có thể chứa nhiều entry. **Dấu phân cách entry là cấu trúc định dạng ZIP**, không phải một delimiter văn bản tự chọn. Các entry có thể dùng phương thức `DEFLATED` (nén) hoặc `STORED` (không nén).

## 2. Sự khác nhau giữa tệp ZIP, entry và stream

Giả sử `backup.zip` chứa:

```text
backup.zip
├── docs/
│   ├── hello.txt
│   └── guide.md
└── image.bin
```

- `backup.zip` là **tệp ZIP bên ngoài**, mở qua `Files.newInputStream` hoặc `Files.newOutputStream`.
- `docs/`, `docs/hello.txt`, `docs/guide.md`, `image.bin` là các **entry**, nhận diện bằng `ZipEntry.getName()`.
- `ZipInputStream.read()` đọc **nội dung của entry hiện tại**, chứ không tự trả một `InputStream` độc lập cho từng entry.
- `ZipOutputStream.write()` ghi **byte cho entry hiện tại** sau khi `putNextEntry()`.
- `ZipEntry` chứa tên và thuộc tính; muốn lấy byte nội dung phải dùng stream phù hợp.

Quy ước phổ biến là tên entry dùng dấu `/` ngay cả trên Windows. Directory entry thường có tên kết thúc bằng `/`, ví dụ `docs/`, và `ZipEntry.isDirectory()` nhận diện theo quy ước này. Có thể có ZIP không chứa entry thư mục riêng nhưng vẫn có tệp với tên `docs/hello.txt`; khi giải nén vẫn phải tự tạo thư mục cha.

## 3. Luồng ghi bằng `ZipOutputStream`

Quy trình cơ bản:

```java
try (ZipOutputStream zout = new ZipOutputStream(
        Files.newOutputStream(zipPath), StandardCharsets.UTF_8)) {

    ZipEntry entry = new ZipEntry("docs/hello.txt");
    zout.putNextEntry(entry); // Mở entry mới trong archive
    zout.write(contentBytes); // Ghi dữ liệu thuộc entry hiện tại
    zout.closeEntry();        // Kết thúc entry
} // close() hoàn tất archive và đóng stream bên dưới
```

Đây là **đoạn minh họa trong phương thức**: `zipPath` và `contentBytes` cần được khai báo từ trước, đồng thời cần import `java.nio.file.*`, `java.nio.charset.StandardCharsets` và `java.util.zip.*`.

Hợp đồng quan trọng:

1. **`putNextEntry(entry)`** mở một mục mới, viết header tương ứng và chuẩn bị trạng thái ghi. Nếu trước đó còn entry chưa đóng, `putNextEntry` có thể kết thúc entry trước theo hợp đồng triển khai; tuy vậy nên gọi `closeEntry()` tường minh để code rõ ràng.
2. **`write(byte[])` hoặc `write(byte[],off,len)`** ghi byte của entry đang mở. Nếu chưa có entry được mở, không được tùy tiện ghi payload.
3. **`closeEntry()`** hoàn tất entry hiện tại: flush/trình bày metadata cần thiết như size và CRC, kết thúc phần dữ liệu nén. Nó **không đóng toàn archive**.
4. **`finish()`** viết xong cấu trúc kết thúc ZIP, nhưng không đóng underlying stream. Hữu ích nếu muốn hoàn thành ZIP mà vẫn giữ `OutputStream` bên dưới. Sau `finish()` không ghi thêm entry.
5. **`close()`** đóng `ZipOutputStream`, hoàn tất ZIP nếu cần và đóng stream bên dưới. Sử dụng `try-with-resources` là lựa chọn mặc định.

**Nếu chỉ gọi `flush()` trên output stream rồi gửi tệp đi**, ZIP có thể thiếu central directory và không đọc được hoàn chỉnh. Hoàn tất ZIP bằng `finish()` hoặc `close()`.

### 3.1. Ghi thư mục

```java
zout.putNextEntry(new ZipEntry("docs/"));
zout.closeEntry();
```

Đây là snippet trong phạm vi có `ZipOutputStream zout`. Tên có dấu `/` cuối biểu thị directory entry và thường không chứa payload. ZIP không buộc mọi thư mục phải có entry riêng; có thể chỉ ghi các file bên dưới `docs/`.

### 3.2. Ghi hai entry tệp liên tiếp

```java
zout.putNextEntry(new ZipEntry("first.txt"));
zout.write("One".getBytes(StandardCharsets.UTF_8));
zout.closeEntry();

zout.putNextEntry(new ZipEntry("second.txt"));
zout.write("Two".getBytes(StandardCharsets.UTF_8));
zout.closeEntry();
```

Không ghi byte tệp thứ hai trước khi mở `second.txt`, nếu không byte sẽ bị gắn vào entry đang mở.

## 4. Luồng đọc bằng `ZipInputStream`

Quy trình đọc theo thứ tự entry:

```java
try (ZipInputStream zin = new ZipInputStream(
        Files.newInputStream(zipPath), StandardCharsets.UTF_8)) {

    ZipEntry entry;
    byte[] buffer = new byte[8192];

    while ((entry = zin.getNextEntry()) != null) {
        System.out.println("entry=" + entry.getName());

        int n;
        while ((n = zin.read(buffer)) != -1) {
            // Chỉ buffer[0..n) chứa byte mới của entry này.
            processBytes(buffer, 0, n); // callback do ứng dụng định nghĩa
        }

        zin.closeEntry();
    }
}
```

Đây là **mẫu thuật toán minh họa**, không chạy độc lập vì `zipPath` và `processBytes` là thành phần do ứng dụng cung cấp.

Quy tắc sử dụng:

- **`getNextEntry()`** di chuyển tới entry kế và trả metadata, hoặc `null` khi không còn entry.
- **`read(byte[])`** đọc byte đã giải nén của entry hiện tại; trả **số byte dương** (hoặc có thể 0 theo hợp đồng overload trong trường hợp yêu cầu độ dài 0), và **`-1` khi đã hết nội dung entry đó**.
- `-1` từ `read()` là **cuối entry hiện tại**. Nó **không chứng minh archive hết entry**. Chỉ `getNextEntry()==null` mới báo hết danh sách entry trong luồng đọc này.
- **`closeEntry()`** kết thúc việc xử lý entry hiện tại; nếu chưa đọc hết, việc bỏ qua/drain phần còn lại có thể phát sinh I/O và phát hiện lỗi ZIP.
- **`close()`** đóng ZIP input stream và stream bên dưới.

Một lần `read(buffer)` không bảo đảm nhận đủ kích thước buffer hoặc toàn bộ entry. Luôn lặp đến `-1`; không dùng `available()` làm “số byte còn lại của ZIP”. `ZipInputStream.available()` không phải hàm đo đầy đủ kích thước dữ liệu còn lại.

## 5. Ví dụ Java 17+ đầy đủ: tạo ZIP và đọc lại

Ví dụ này tạo ZIP thật trong thư mục tạm, chứa một directory entry, một tệp văn bản UTF-8 và một tệp nhị phân. Sau khi `ZipOutputStream` đóng hoàn chỉnh archive, `ZipInputStream` đọc từng entry và in kết quả. Dữ liệu hiển thị có thứ tự xác định.

Tạo file `ZipStreamsDemo.java`:

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;
import java.util.zip.ZipOutputStream;

public class ZipStreamsDemo {
    public static void main(String[] args) throws IOException {
        Path archive = Files.createTempFile("zip-streams-", ".zip");

        try {
            try (OutputStream raw = Files.newOutputStream(archive);
                 ZipOutputStream zout = new ZipOutputStream(
                         raw, StandardCharsets.UTF_8)) {

                zout.putNextEntry(new ZipEntry("docs/"));
                zout.closeEntry();

                zout.putNextEntry(new ZipEntry("docs/hello.txt"));
                zout.write("Xin chào ZIP".getBytes(StandardCharsets.UTF_8));
                zout.closeEntry();

                zout.putNextEntry(new ZipEntry("data.bin"));
                zout.write(new byte[] {0, 1, 2, (byte) 255});
                zout.closeEntry();
            }

            try (InputStream raw = Files.newInputStream(archive);
                 ZipInputStream zin = new ZipInputStream(
                         raw, StandardCharsets.UTF_8)) {

                ZipEntry entry;
                byte[] buffer = new byte[1024];

                while ((entry = zin.getNextEntry()) != null) {
                    ByteArrayOutputStream content = new ByteArrayOutputStream();
                    int n;

                    while ((n = zin.read(buffer)) != -1) {
                        content.write(buffer, 0, n);
                    }

                    if (entry.isDirectory()) {
                        System.out.println("directory: " + entry.getName());
                    } else if (entry.getName().endsWith(".txt")) {
                        String text = new String(
                                content.toByteArray(), StandardCharsets.UTF_8);
                        System.out.println(
                                entry.getName() + " = " + text);
                    } else {
                        System.out.println(
                                entry.getName() + " = "
                                + Arrays.toString(content.toByteArray()));
                    }

                    zin.closeEntry();
                }
            }
        } finally {
            Files.deleteIfExists(archive);
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac ZipStreamsDemo.java
java ZipStreamsDemo
```

Stdout dự kiến:

```text
directory: docs/
docs/hello.txt = Xin chào ZIP
data.bin = [0, 1, 2, -1]
```

**Giải thích từng bước:**

1. Tạo ZIP bằng `Files.createTempFile`, sau đó ghi qua `ZipOutputStream`.
2. Ghi directory entry `docs/` với payload rỗng.
3. Ghi `docs/hello.txt`, mã hóa chuỗi thành byte UTF-8 **trước khi nén**. Tên entry và nội dung là hai loại dữ liệu khác nhau.
4. Ghi `data.bin` gồm byte 0, 1, 2, `0xFF`. Java `byte` là số có dấu, nên `Arrays.toString` in byte `0xFF` thành `-1`; đây **không phải dấu hiệu EOF** của `ZipInputStream.read()`.
5. Khi output ZIP được đóng, archive đã có các thành phần ZIP hoàn chỉnh để mở bằng input ZIP.
6. `getNextEntry()` lần lượt trả ba entry. Vòng `zin.read(buffer)` lấy **đúng byte đã giải nén của một entry** tới `-1`.
7. Ví dụ dùng `ByteArrayOutputStream` để đơn giản hóa cách in. Với entry lớn hoặc ZIP không tin cậy, **không gom toàn bộ nội dung vào RAM**; phải xử lý theo luồng và áp giới hạn số byte (xem phần bảo mật).

Dùng `try-with-resources` giúp đóng cả wrapper ZIP và underlying streams khi bình thường hoặc khi có lỗi. Đoạn `finally` xóa tệp tạm trong điều kiện hệ điều hành cho phép.

## 6. `ZipEntry`: đọc và đặt metadata đúng cách

`ZipEntry` biểu diễn thông tin về một thành phần ZIP. Các API hữu ích:

| API | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `getName()` | Tên entry bên trong ZIP | **Không được tin cậy** khi dùng làm đường dẫn hệ điều hành |
| `isDirectory()` | Có tên kết thúc bằng `/` hay không | Không có entry thư mục riêng vẫn có thể có thư mục ngầm |
| `getSize()` | Kích thước dữ liệu **sau giải nén** | Có thể trả `-1` khi không được biết trong local header |
| `getCompressedSize()` | Kích thước dữ liệu nén | Có thể trả `-1` khi chưa biết |
| `getCrc()` | CRC-32 32-bit của nội dung chưa nén | Có thể trả `-1` khi chưa biết |
| `getMethod()` | `STORED` hoặc `DEFLATED` | Phụ thuộc entry và định dạng ZIP |
| `getTime()`, `getLastModifiedTime()` | Timestamp entry nếu có | Độ chính xác và khả năng bảo toàn có thể khác |
| `getComment()`, `getExtra()` | Comment/extra fields nếu được cung cấp | Không phải lúc nào stream reader cũng nhận đủ central-directory metadata |
| `setMethod()`, `setSize()`, `setCrc()` | Metadata cho entry khi ghi | Phải hợp lệ, đặc biệt với `STORED` |

Một `ZipEntry` có thể được đọc từ `zin.getNextEntry()` hoặc tạo bằng `new ZipEntry("path/in/archive")`. Nó không nắm quyền sở hữu `ZipInputStream` hoặc `ZipOutputStream`.

### 6.1. Vì sao `getSize()` có thể là `-1`?

Khi ghi ZIP với DEFLATED, writer có thể chưa biết trước độ dài giải nén, độ dài nén và CRC của entry. Các giá trị ấy có thể được đặt trong **data descriptor** sau payload hoặc central directory cuối archive.

`ZipInputStream` là reader **tuần tự**, thường lấy metadata từ local file header. Vì thế `entry.getSize()` hoặc `entry.getCrc()` có thể bằng `-1` khi mới bắt đầu đọc entry, mặc dù entry đó hoàn toàn hợp lệ.

Không viết code kiểu `new byte[(int) entry.getSize()]` khi `getSize()` chưa biết. Đếm **byte thực tế khi giải nén**, vừa để xử lý dữ liệu, vừa để chống ZIP bomb.

### 6.2. Tên entry không nhất thiết là đường dẫn an toàn

Tên `../secret.txt`, `/etc/config`, hoặc các chuỗi đặc biệt khác có thể có trong ZIP nhận từ nguồn ngoài. Khi dùng chúng để ghi lên đĩa phải kiểm tra giới hạn root (phần bảo mật). Không lấy `ZipEntry.getName()` rồi gọi trực tiếp `destination.resolve(name)` và ghi file mà không kiểm tra.

## 7. `DEFLATED` và `STORED`: hai chế độ phổ biến

`ZipEntry.DEFLATED` là phương thức nén DEFLATE, thường được `ZipOutputStream` dùng mặc định. `ZipEntry.STORED` lưu byte không nén.

| Thuộc tính | `DEFLATED` | `STORED` |
| --- | --- | --- |
| Nén nội dung | Có | Không |
| CPU khi ghi/đọc | Có chi phí nén/giải nén | Không cần DEFLATE |
| Dung lượng archive | Có thể nhỏ hơn hoặc lớn hơn chút với dữ liệu khó nén | Gần dung lượng nguyên bản cộng metadata ZIP |
| Phải biết size/CRC **trước** `putNextEntry()` | Thường không cần | **Có**; cần size, compressed size và CRC |
| Khi phù hợp | Text, JSON, dữ liệu lặp | Dữ liệu đã nén, cần tránh nén lại, hoặc yêu cầu định dạng |

Ví dụ DEFLATED:

```java
ZipEntry entry = new ZipEntry("notes.txt");
entry.setMethod(ZipEntry.DEFLATED);
zout.putNextEntry(entry);
zout.write(data);
zout.closeEntry();
```

Đây là snippet với `ZipOutputStream zout` và `byte[] data` đã có. Khi không đặt trước kích thước/CRC, writer có thể tính sau khi hoàn tất entry.

### 7.1. Ghi STORED phải tính trước CRC và kích thước

```java
import java.util.zip.CRC32;
import java.util.zip.ZipEntry;

// Bên trong phương thức có ZipOutputStream zout và byte[] data:
CRC32 crc = new CRC32();
crc.update(data);

ZipEntry entry = new ZipEntry("already-compressed.bin");
entry.setMethod(ZipEntry.STORED);
entry.setSize(data.length);
entry.setCompressedSize(data.length);
entry.setCrc(crc.getValue());

zout.putNextEntry(entry);
zout.write(data);
zout.closeEntry();
```

`STORED` yêu cầu **size bằng compressed size** và CRC-32 đã xác định **trước khi ghi entry**. Thiếu metadata có thể làm `putNextEntry()` ném `ZipException`. Nếu byte ghi thực tế không khớp size/CRC đã khai báo, quá trình ghi/đóng entry cũng có thể thất bại.

Với dữ liệu rất lớn mà chưa biết CRC, có thể phải đọc một lượt để tính CRC rồi đọc lại lượt hai, hoặc chuyển sang DEFLATED để cho writer tính metadata sau. Không nên đọc toàn bộ file lớn vào một `byte[]` chỉ để tính CRC.

### 7.2. Compression level

`ZipOutputStream.setLevel(int level)` đặt mức nén DEFLATED cho các entry tiếp theo, thường từ `Deflater.NO_COMPRESSION` (0) tới `Deflater.BEST_COMPRESSION` (9), hoặc `Deflater.DEFAULT_COMPRESSION` (-1). Mức cao có thể tốn CPU hơn mà chưa chắc làm file nhỏ đáng kể; cần benchmark trên dữ liệu thực tế. Level không phải cờ bảo mật hoặc độ “chuẩn” của ZIP.

## 8. ZIP entry name và character encoding

Tên entry là metadata có thể chứa Unicode; Java hỗ trợ constructor có `Charset`:

```java
ZipOutputStream zout = new ZipOutputStream(
        Files.newOutputStream(zipPath), StandardCharsets.UTF_8);

ZipInputStream zin = new ZipInputStream(
        Files.newInputStream(zipPath), StandardCharsets.UTF_8);
```

Đây là **hai đoạn tạo stream riêng biệt**; không mở ghi và đọc chồng lên cùng tệp ZIP đang được tạo như một quy trình thường lệ. Hãy hoàn tất/đóng writer trước khi mở reader.

Phân biệt:

- `Charset` của `ZipInputStream`/`ZipOutputStream` điều khiển **mã hóa tên entry và thông tin ZIP liên quan** theo quy tắc format.
- Nội dung một entry là **mảng byte tùy ý**. Nếu đó là text, code phải tự chọn charset khi `String.getBytes` hoặc `new String(bytes, charset)`.
- ZIP từ các công cụ cũ đôi khi dùng code page khác UTF-8; nếu metadata/flag ZIP không tương thích, tên entry có thể đọc sai hoặc ném lỗi. Chọn charset dựa trên đặc tả/nguồn archive, không thử đoán bằng tên ngẫu nhiên.
- Khi ZIP đánh dấu tên entry là UTF-8 theo chuẩn, cờ này ảnh hưởng cách reader giải mã; constructor `Charset` không phải “ép mọi entry bất chấp flag”.

Tên entry nên sử dụng dấu `/` theo quy ước ZIP. Không dựa vào `File.separator` của hệ điều hành khi dựng tên nội bộ trong archive.

## 9. `ZipInputStream` hay `ZipFile`?

Cùng đọc ZIP nhưng phục vụ nhu cầu khác nhau:

| Tiêu chí | `ZipInputStream` | `ZipFile` |
| --- | --- | --- |
| Nguồn dữ liệu | Một `InputStream` | Một tệp ZIP truy cập được qua đường dẫn hoặc `File` |
| Truy cập entry | Tuần tự qua `getNextEntry()` | Liệt kê và lấy entry cụ thể qua `getEntry()`/`entries()` |
| Đọc dữ liệu | `read()` trên stream đang trỏ tới entry hiện tại | `getInputStream(entry)` trả stream nội dung entry |
| Metadata | Chủ yếu từ local file header | Có thể dựa vào central directory, đầy đủ hơn |
| Phù hợp | Upload/network stream, giải nén tuần tự | Chọn file bất kỳ trong archive, truy cập lặp lại |
| Vòng đời | Một stream duy nhất; xử lý entry theo thứ tự | Đóng `ZipFile` và các entry streams đúng cách |

`ZipInputStream` không phải công cụ tốt nếu cần mở `report.csv` ở cuối archive ngay mà không duyệt các entry đứng trước. Khi file ZIP đã nằm trên đĩa và cần random access theo tên, `ZipFile` thường phù hợp hơn.

Cũng có lựa chọn **Zip File System** (`FileSystems.newFileSystem` với provider `jar`) để thao tác `Path` bên trong archive; đó là mô hình khác với đọc/ghi tuần tự ở bài này.

## 10. Giải nén an toàn: chống Zip Slip

Khi nhận ZIP từ người dùng, một entry có thể tên `../../outside.txt`. Nếu ứng dụng nối tên đó với thư mục đích mà không kiểm tra, nó có thể ghi **ra ngoài thư mục được phép**. Đây là lỗ hổng **Zip Slip**.

Luôn xác định root hợp lệ, chuẩn hóa path và từ chối path vượt ra ngoài root:

```java
Path root = destination.toAbsolutePath().normalize();
Path target = root.resolve(entry.getName()).normalize();

if (!target.startsWith(root)) {
    throw new IOException("ZIP entry escapes destination");
}
```

Đây là **đoạn minh họa**; `destination`, `entry` là biến đã có. Có thêm các yêu cầu:

1. Không chấp nhận đường dẫn tuyệt đối hoặc tên entry không hợp lệ.
2. Không chấp nhận thành phần `..` khiến target vượt root.
3. Từ chối các tên đặc biệt/định dạng path không hợp lệ trên hệ điều hành đích.
4. Tạo thư mục cha trước khi mở file đích.
5. Chọn chính sách trùng tên: `CREATE_NEW` để không âm thầm ghi đè file tồn tại; kiểm tra các entry trùng tên trong ZIP.
6. **Quan trọng:** kiểm tra `normalize()/startsWith()` chỉ bảo vệ ở mức đường dẫn lexical. Nếu thư mục giải nén đã có **symlink** hoặc có tiến trình độc hại cùng sửa cây thư mục, việc đi xuyên symlink/TOCTOU vẫn có thể khiến ghi ra ngoài root. An toàn hơn là giải nén vào **thư mục mới, riêng tư, không có symlink và không cho tác nhân khác sửa đồng thời**; với threat model cao cần cơ chế mở path tương đối với directory handle/an toàn symlink của nền tảng.

Không xem `ZipEntry.isDirectory()` là bằng chứng một entry an toàn: `ZipEntry` chỉ mang metadata, còn phép ghi thực tế dựa trên đường dẫn đã giải quyết.

## 11. Chống ZIP bomb: đếm byte thực tế, không tin metadata

ZIP bomb là archive rất nhỏ sau nén nhưng giải nén thành lượng dữ liệu cực lớn, hoặc có hàng triệu entry. `getSize()` có thể không biết trước hoặc không đáng tin cậy với input không xác thực.

Giới hạn tối thiểu cho một extraction service:

- **Số entry tối đa**, ví dụ 1.000.
- **Dung lượng sau giải nén của mỗi entry**, ví dụ 20 MiB.
- **Tổng dung lượng sau giải nén của mọi entry**, ví dụ 100 MiB.
- **Độ sâu/tổng độ dài đường dẫn** và số thư mục.
- **Thời gian CPU/timeout**, số lần truy cập, dung lượng đĩa và quota xử lý đồng thời.
- Có thể thêm ngưỡng tỷ lệ giải nén với định nghĩa đo rõ ràng, nhưng đừng chỉ dựa vào ratio: một archive hợp lệ nén rất tốt vẫn có ratio lớn.

Ví dụ vòng xử lý byte với quota thực tế:

```java
long currentSize = 0;
int n;

while ((n = zin.read(buffer)) != -1) {
    if (n > MAX_ENTRY_BYTES - currentSize
            || n > MAX_TOTAL_BYTES - totalSize) {
        throw new IOException("ZIP extraction size limit exceeded");
    }

    currentSize += n;
    totalSize += n;
    output.write(buffer, 0, n);
}
```

Đây là **snippet minh họa bên trong vòng xử lý một entry**, với `ZipInputStream zin`, `OutputStream output`, `byte[] buffer`, `long totalSize` và hằng số quota đã định nghĩa. Cách kiểm tra `n > quota - used` giúp tránh overflow khi cộng, với điều kiện các biến `used` ban đầu không âm và không vượt quota.

`Files.copy(zin, target)` hoặc `zin.transferTo(output)` rất tiện nhưng không tự gắn giới hạn byte sau giải nén theo chính sách nghiệp vụ của bạn. Với archive không tin cậy, nên đọc theo block và kiểm tra quota trước mỗi lần ghi.

### 11.1. Mẫu extraction có quota và kiểm tra đường dẫn

Phương thức dưới đây mang tính **minh họa theo phạm vi thiết kế**, không phải bảo đảm chống mọi đường tấn công filesystem đồng thời:

```java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

static void extractIntoPrivateDirectory(
        InputStream zipData, Path privateRoot) throws IOException {

    final long MAX_ENTRY_BYTES = 20L * 1024 * 1024;
    final long MAX_TOTAL_BYTES = 100L * 1024 * 1024;
    final int MAX_ENTRIES = 1000;

    // privateRoot phải là thư mục mới, không có symlink và
    // không bị tác nhân khác sửa đồng thời.
    Path root = privateRoot.toAbsolutePath().normalize();
    long total = 0;
    int count = 0;
    byte[] buffer = new byte[8192];

    try (ZipInputStream zin = new ZipInputStream(zipData)) {
        ZipEntry entry;
        while ((entry = zin.getNextEntry()) != null) {
            if (++count > MAX_ENTRIES) {
                throw new IOException("Too many ZIP entries");
            }

            Path relative = Path.of(entry.getName());
            Path target = root.resolve(relative).normalize();
            if (relative.isAbsolute() || !target.startsWith(root)
                    || target.equals(root)) {
                throw new IOException("Unsafe ZIP entry path");
            }

            if (entry.isDirectory()) {
                Files.createDirectories(target);
            } else {
                Files.createDirectories(target.getParent());
                long entryBytes = 0;

                try (OutputStream out = Files.newOutputStream(
                        target, StandardOpenOption.CREATE_NEW,
                        StandardOpenOption.WRITE)) {
                    int n;
                    while ((n = zin.read(buffer)) != -1) {
                        if (n > MAX_ENTRY_BYTES - entryBytes
                                || n > MAX_TOTAL_BYTES - total) {
                            throw new IOException("ZIP content too large");
                        }
                        out.write(buffer, 0, n);
                        entryBytes += n;
                        total += n;
                    }
                }
            }
            zin.closeEntry();
        }
    }
}
```

**Điều kiện sử dụng mẫu:**

- Caller phải **tạo sẵn một thư mục trống, riêng tư** rồi truyền `privateRoot` vào. Phương thức này không tự tạo root và không bảo vệ tuyệt đối nếu tác nhân khác có thể tạo symlink trong tree giữa các thao tác. Với nguồn untrusted có threat model mạnh, hãy dùng sandbox/cơ chế path traversal chống symlink phù hợp hệ điều hành.
- `Path.of(entry.getName())` có thể ném `InvalidPathException` với tên không hợp lệ; có thể bắt và chuyển thành lỗi archive không hợp lệ ở ranh giới API.
- `CREATE_NEW` từ chối việc ghi đè tệp đã tồn tại, kể cả khi entry khác trong ZIP có cùng tên. Đây là lựa chọn chính sách; với tệp tạm đang giải nén dở, khi xảy ra lỗi ứng dụng cần cleanup theo quy trình giao dịch riêng.
- Không dùng `closeEntry()` thay cho quota: nếu gặp entry quá lớn, ném exception để dừng giải nén thay vì cố drain toàn bộ archive.
- ZIP có thể chứa tên path mang semantics đặc thù OS; trên Windows cần chú ý tên thiết bị, ký tự `:`, trailing dots/spaces, phân biệt hoa thường và giới hạn path. Luôn kiểm tra trong môi trường đích.

Phương thức được trình bày để dạy các lớp bảo vệ chính, không phải một trình giải nén production hoàn chỉnh. Ứng dụng thực cần thêm quota về thời gian, số thư mục, file permissions, không gian đĩa, báo cáo tiến độ, cancellation, antivirus khi phù hợp, và kiểm thử cạnh tranh/symlink.

## 12. CRC-32 và tính toàn vẹn dữ liệu

CRC-32 trong ZIP dùng để phát hiện hư hỏng do truyền/lưu trữ không chủ ý. Khi đọc đầy đủ entry qua `ZipInputStream`, implementation có thể kiểm tra CRC và kích thước khai báo khi gặp phần kết thúc entry, rồi báo `ZipException` nếu không khớp.

Tuy nhiên:

- CRC-32 **không phải** chữ ký số, MAC hoặc mã xác thực; kẻ tấn công có thể thay nội dung rồi tính lại CRC.
- Không dùng CRC-32 để quyết định rằng ZIP an toàn hoặc đến từ nguồn đáng tin.
- Không tin rằng `getCrc()` đã sẵn sàng ngay tại đầu entry.
- Việc đọc/đóng ZIP có thể phát sinh `ZipException`, `EOFException` hoặc `IOException` nếu dữ liệu bị cắt hoặc hỏng. Phải xử lý đường lỗi, không lặng lẽ công bố tệp giải nén dở là đã hoàn tất.

Nếu cần bảo đảm tính xác thực, sử dụng một cơ chế chữ ký/MAC ở tầng ứng dụng hoặc định dạng container hỗ trợ xác thực, kèm quy trình kiểm chứng phù hợp.

## 13. ZIP không mặc định là mã hóa hay backup an toàn

`ZipOutputStream` trong Java chuẩn **không cung cấp tính năng tạo ZIP có mật khẩu/mã hóa**. Nó nén và đóng gói dữ liệu, không bảo mật nội dung trước người đọc. Tương tự, `ZipInputStream` của JDK không phải giải pháp tổng quát cho ZIP được mã hóa bằng các biến thể password/encryption phổ biến.

Không nên xem file `.zip` là an toàn chỉ vì khó đọc trực tiếp trong text editor. Nếu cần bảo mật, dùng mã hóa/authentication phù hợp ở lớp khác hoặc thư viện ZIP hỗ trợ format đã được thẩm định, kiểm tra nguồn gốc và cấu hình đúng cách.

Ngoài ra ZIP không phải định dạng lưu trữ toàn bộ metadata hệ điều hành theo cách thống nhất. Quyền POSIX, symlink, owner/group và các thuộc tính nâng cao có thể nằm trong extra fields hoặc convention do các chương trình khác nhau dùng; chỉ sử dụng `ZipEntry` của JDK không có nghĩa sẽ khôi phục chính xác mọi permission/symlink khi giải nén.

## 14. Stream I/O, buffer và việc dùng bộ nhớ

Ưu điểm của `ZipInputStream`/`ZipOutputStream` là **xử lý tuần tự theo stream**. Với tệp lớn, có thể dùng buffer 8 KiB hoặc 64 KiB thay vì đọc toàn bộ vào `byte[]`.

Ví dụ thêm tệp vào ZIP theo luồng (mẫu trong phương thức):

```java
try (InputStream fileIn = Files.newInputStream(sourceFile)) {
    zout.putNextEntry(new ZipEntry(entryName));
    byte[] buffer = new byte[8192];
    int n;
    while ((n = fileIn.read(buffer)) != -1) {
        zout.write(buffer, 0, n);
    }
    zout.closeEntry();
}
```

Giả sử `zout` là `ZipOutputStream` đang mở; `sourceFile` và `entryName` đã được kiểm tra. Không đưa một file vào ZIP dưới đường dẫn tuyệt đối của hệ điều hành. Tên entry nên là path tương đối, dùng dấu `/` và không chứa thông tin nhạy cảm.

Khi giải nén, cũng dùng một buffer cố định và ghi `output.write(buffer,0,n)`. Điều này giới hạn dung lượng **buffer trung gian**, nhưng phải cộng thêm quota thực tế của đích và số tác vụ cùng chạy.

Nếu tạo rất nhiều ZIP đồng thời, tổng bộ nhớ cần xem số `ZipOutputStream`/`ZipInputStream`, buffer do `Deflater`/`Inflater` sở hữu, file handles, số byte đang chờ và executor threads. Đóng stream khi xong để giải phóng tài nguyên kịp thời.

## 15. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Không gọi `putNextEntry()` trước khi `write()` | Không có entry hợp lệ để ghi payload | Mỗi entry: mở → ghi → đóng |
| Chỉ `flush()` rồi sử dụng archive chưa hoàn thành | ZIP thiếu central directory | `finish()` hoặc `close()` |
| Cho rằng `read()==-1` là hết toàn ZIP | Dừng sau entry đầu | Gọi `getNextEntry()` đến `null` |
| Đọc `getSize()` luôn phải dương | Metadata có thể chưa biết | Đếm byte thực tế |
| Tạo `byte[(int)getSize()]` không kiểm tra | Âm, overflow hoặc cạn RAM | Streaming + quota |
| Dùng `STORED` nhưng không đặt size/CRC | `ZipException` khi ghi | Tính trước metadata |
| Đặt `compressedSize` bằng `size` cho DEFLATED | Có thể sai vì dữ liệu nén dài khác | Để writer tính hoặc cung cấp metadata đúng |
| Viết tên entry bằng `File.separator` | ZIP không portable | Dùng dấu `/` |
| Coi `ZipEntry.getName()` là path an toàn | Zip Slip, ghi đè ra ngoài thư mục | Normalize + root check + chống symlink |
| Giải nén không giới hạn | ZIP bomb và đầy đĩa | Per-entry/total quotas và timeout |
| Dùng `available()` để biết entry đã hết | Sai ngữ nghĩa | Lặp `read` tới `-1` |
| Đọc text bằng charset mặc định | Chữ Unicode sai | Charset rõ ràng, ví dụ UTF-8 |
| Coi CRC như xác thực | Không chống sửa đổi có chủ ý | Chữ ký/MAC khi cần |
| Nghĩ ZIP mặc định mã hóa | Nội dung có thể đọc công khai | Mã hóa riêng hoặc giải pháp có xác thực |
| Bỏ qua lỗi khi đọc/đóng entry | Có thể chấp nhận tệp hỏng | Propagate lỗi, cleanup tệp dở |
| Giữ `ByteArrayOutputStream` cho mọi entry lớn | Heap phình to | Xử lý theo block/stream |
| Tên trùng nhau trong archive | Trích xuất ghi đè hoặc lỗi không thống nhất | Quy định duplicate policy từ đầu |

## 16. Bài tập và đáp án

**Bài 1.** Một ZIP có hai entry. Sau khi đọc `zin.read()` trả `-1`, có phải hết ZIP không?

**Đáp án:** Không; chỉ hết nội dung **entry hiện tại**. Cần `zin.getNextEntry()` để tới entry sau; `null` mới báo hết entry.

**Bài 2.** `ZipEntry.getSize()` trả `-1`. Archive có chắc bị hỏng không?

**Đáp án:** Không. Reader tuần tự có thể chưa biết size tại local file header; đếm dữ liệu đã giải nén khi đọc tới cuối entry.

**Bài 3.** Vì sao `ZipOutputStream` với `STORED` phải biết CRC-32 trước khi ghi?

**Đáp án:** Theo hợp đồng Java ZIP writer, entry STORED phải có size, compressed size và CRC được xác định trước khi `putNextEntry()`.

**Bài 4.** Có nên lấy `entry.getName()` rồi viết thẳng vào `outputDir.resolve(name)`?

**Đáp án:** Không. Tên có thể chứa `..`, path tuyệt đối hoặc tấn công qua symlink; cần giải nén vào root an toàn, normalize/check và phối hợp chống symlink.

**Bài 5.** ZIP có một entry giải nén thành 5 GiB dù file nén chỉ vài MiB. Dùng buffer 8 KiB có tự giải quyết nguy cơ không?

**Đáp án:** Không. Buffer trung gian nhỏ chỉ giảm RAM tức thời; vẫn có thể làm đầy đĩa hoặc tiêu tốn CPU. Cần quota tổng byte, byte mỗi entry, thời gian và số entry.

**Bài 6.** `ZipEntry` có tự chứa nội dung tệp không?

**Đáp án:** Không. Nó chỉ mô tả metadata; nội dung được đọc/ghi bằng các stream ZIP khi entry đang active.

**Bài 7.** Tại sao sau khi ghi các entry phải đóng `ZipOutputStream` hoặc gọi `finish()`?

**Đáp án:** Để hoàn tất các cấu trúc định dạng ZIP, đặc biệt central directory cuối archive, giúp reader nhận đủ entry.

**Bài 8.** ZIP có tên `docs/hello.txt` nhưng không có `docs/`. ZIP có nhất thiết không hợp lệ không?

**Đáp án:** Không. Entry tệp có thể mô tả thư mục cha ngầm; khi giải nén cần tự tạo các thư mục cha.

**Bài 9.** Nếu dữ liệu entry là tiếng Việt, constructor `ZipInputStream(..., UTF_8)` có tự giải mã nội dung thành `String` không?

**Đáp án:** Không. Charset của stream ZIP áp dụng cho tên entry theo quy tắc metadata. Payload vẫn là byte, cần decode bằng charset đã thỏa thuận.

**Bài 10.** Có thể dùng CRC-32 để xác minh ZIP đến từ người gửi đáng tin không?

**Đáp án:** Không. CRC phát hiện lỗi ngẫu nhiên, không phải cơ chế chứng thực chống kẻ tấn công.

## 17. Checklist khi ứng dụng tạo hoặc nhận ZIP

1. Chọn `ZipOutputStream` cho ghi ZIP tuần tự, `ZipInputStream` cho đọc tuần tự, `ZipFile` cho truy cập ngẫu nhiên một archive trên đĩa.
2. Mỗi entry dùng đúng thứ tự `putNextEntry` → `write` → `closeEntry`; hoàn tất archive bằng `close` hoặc `finish`.
3. Đọc bằng `getNextEntry()` đến `null`, và `read()` đến `-1` trong **mỗi entry**.
4. Chọn charset rõ ràng cho tên entry và cho nội dung văn bản.
5. Khi dùng `STORED`, thiết lập size, compressed size, CRC trước khi ghi; `DEFLATED` phù hợp khi không biết trước metadata.
6. Không giả định `getSize/getCrc` luôn biết khi đọc stream.
7. Với ZIP untrusted, chặn Zip Slip, path tuyệt đối, duplicate entries, symlink/TOCTOU và file-name đặc thù hệ điều hành.
8. Giới hạn số entry, byte mỗi entry, tổng byte giải nén, chiều dài path, thời gian và số archive xử lý đồng thời.
9. Xử lý `ZipException`, `IOException`, lỗi CRC và cleanup tệp giải nén chưa hoàn chỉnh; không publish kết quả trước khi toàn bộ policy thành công.
10. Không coi nén là mã hóa, không coi CRC là xác thực, và không giả định metadata filesystem được phục hồi đầy đủ.

## Tài liệu Java chính thức

- Java SE 17 — `ZipInputStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipInputStream.html
- Java SE 17 — `ZipOutputStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipOutputStream.html
- Java SE 17 — `ZipEntry`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipEntry.html
- Java SE 17 — `ZipFile`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipFile.html
- Java SE 17 — `CRC32`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/CRC32.html
- Java SE 17 — `Files`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html
