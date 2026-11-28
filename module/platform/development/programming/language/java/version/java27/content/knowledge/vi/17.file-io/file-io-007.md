# Đọc ghi ZIP và sử dụng hệ thống tệp ZIP trong Java 27

ZIP là định dạng tệp lưu trữ (*archive*) có thể chứa nhiều tệp, thư mục và thông tin đi kèm trong một tệp duy nhất. Trong Java 27, có hai nhóm API chính để làm việc với ZIP:

- **`java.util.zip`**: đọc/ghi các entry theo luồng, kiểm tra nội dung và truy cập từng entry.
- **ZIP File System Provider (`jdk.zipfs`)**: xem nội dung ZIP như một hệ thống tệp, sau đó dùng các API hiện đại của **`java.nio.file`** như `Files.copy`, `Files.walk`, `Files.readString` và `Files.writeString`.

Mỗi lựa chọn có thế mạnh khác nhau. Bài học thuộc chương **Tệp và nhập xuất**, trình bày cách chọn API, tạo và đọc ZIP, sửa nội dung bằng ZIP FileSystem, xử lý encoding, quản lý tài nguyên và bảo vệ ứng dụng trước ZIP từ nguồn không tin cậy. Các ví dụ sử dụng những API vẫn áp dụng trong Java SE 27.

## 1. Hiểu cấu trúc của một tệp ZIP

Một ZIP chứa các **entry**. Mỗi entry thường biểu diễn một tệp hoặc thư mục và có một tên tương đối so với gốc archive.

Ví dụ:

~~~text
backup.zip
├── config.properties
├── docs/
│   ├── readme.txt
│   └── guide.txt
└── images/
    └── logo.png
~~~

Các tên entry tương ứng:

~~~text
config.properties
docs/
docs/readme.txt
docs/guide.txt
images/
images/logo.png
~~~

Đặc điểm quan trọng:

- Tên entry trong ZIP sử dụng dấu gạch chéo xuôi (`/`) làm ký tự phân tách các cấp đường dẫn.
- Entry thư mục thường có tên kết thúc bằng `/`, chẳng hạn `docs/`.
- Một ZIP có thể chứa entry tệp mà không cần entry thư mục cha được ghi tường minh.
- Entry có thể kèm kích thước gốc, kích thước nén, checksum CRC-32, thời gian sửa đổi và metadata khác.
- ZIP hỗ trợ các phương thức lưu trữ không nén và nén dữ liệu, trong đó Java `ZipOutputStream` thường dùng **DEFLATED** theo mặc định.

ZIP khác **GZIP**. ZIP đóng gói nhiều entry; `GZIPInputStream` và `GZIPOutputStream` chủ yếu thao tác một luồng dữ liệu nén theo định dạng GZIP, không cung cấp danh sách các tệp con như ZIP.

Một tệp JAR cũng dùng cấu trúc ZIP, nhưng có thêm quy ước riêng dành cho Java, như manifest và metadata khác. Khi xử lý JAR chuyên biệt, Java còn cung cấp `java.util.jar`.

## 2. Chọn API phù hợp

| Nhu cầu | API nên cân nhắc | Điểm cần nhớ |
|---|---|---|
| Tạo ZIP mới bằng cách ghi lần lượt các entry | `ZipOutputStream` | Ghi tuần tự, quản lý `putNextEntry` / `closeEntry` |
| Đọc ZIP theo dòng chảy từ đầu đến cuối | `ZipInputStream` | Chỉ tiến về phía trước; phù hợp với stream/network |
| Tìm một entry theo tên trong ZIP trên đĩa | `ZipFile` | Truy cập entry chọn lọc, đọc cấu trúc ZIP |
| Duyệt thư mục, thêm, sửa hoặc xóa entry bằng NIO | `FileSystems.newFileSystem(...)` với ZIPFS | ZIP được xem như `FileSystem`; nhớ đóng |
| Giải nén ZIP đến thư mục hệ điều hành | `ZipInputStream` / `ZipFile` + `Files` | **Bắt buộc** kiểm tra tên entry và giới hạn tài nguyên |
| Đọc rất nhiều tệp bất kỳ trong ZIP như một cây thư mục | ZIPFS | Dùng `Path` và `Files` quen thuộc |
| Giải mã ZIP có mật khẩu hoặc các tính năng ngoài khả năng API chuẩn | Thư viện chuyên dụng đã được kiểm chứng | `java.util.zip` không cung cấp API giải mã ZIP bảo vệ bằng mật khẩu |

**`ZipInputStream` không phải `ZipFile`**: một bên đọc tuần tự trên stream, bên kia thao tác một ZIP hoàn chỉnh để có thể tra cứu entry. **ZIPFS không phải chỉ là một cách viết khác của `ZipInputStream`**: nó triển khai một hệ thống tệp ảo với ngữ nghĩa đọc/ghi bằng `Path`.

## 3. Các lớp cơ bản trong java.util.zip

Những lớp thường gặp:

| Lớp | Vai trò |
|---|---|
| `ZipEntry` | Đại diện metadata của một entry ZIP |
| `ZipOutputStream` | Ghi ZIP có nhiều entry vào `OutputStream` |
| `ZipInputStream` | Đọc lần lượt entry từ `InputStream` |
| `ZipFile` | Mở ZIP trên tệp để liệt kê và lấy một entry theo tên |
| `ZipException` | Ngoại lệ liên quan đến ZIP không hợp lệ hoặc một số lỗi xử lý ZIP |
| `CRC32` | Tính checksum CRC-32, hữu ích khi ghi entry STORED |
| `Deflater` | Điều chỉnh mức độ nén trong các trường hợp phù hợp |

Các API này thuộc module **`java.base`**, không cần thêm dependency bên ngoài.

Trong mã mới, nên kết hợp chúng với `Path`, `Files`, `StandardCharsets.UTF_8` và **try-with-resources**. Tránh tải cả archive hoặc một entry lớn vào bộ nhớ khi có thể xử lý theo luồng.

## 4. Tạo ZIP đơn giản bằng ZipOutputStream

Các bước cơ bản để ghi ZIP:

1. Mở một `OutputStream` tới tệp đích.
2. Bọc bằng `ZipOutputStream`.
3. Với mỗi entry: tạo `ZipEntry`, gọi `putNextEntry`, ghi dữ liệu rồi `closeEntry`.
4. Đóng `ZipOutputStream` để kết thúc archive và giải phóng tài nguyên.

Ví dụ tạo hai tệp văn bản trong một ZIP:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

public class CreateSimpleZip {
    public static void main(String[] args) throws IOException {
        Path zipPath = Path.of("example.zip");

        try (ZipOutputStream zip = new ZipOutputStream(
                Files.newOutputStream(zipPath),
                StandardCharsets.UTF_8)) {

            zip.putNextEntry(new ZipEntry("docs/"));
            zip.closeEntry();

            zip.putNextEntry(new ZipEntry("docs/readme.txt"));
            zip.write("Hướng dẫn Java 27\n"
                    .getBytes(StandardCharsets.UTF_8));
            zip.closeEntry();

            zip.putNextEntry(new ZipEntry("config.txt"));
            zip.write("mode=demo\n"
                    .getBytes(StandardCharsets.UTF_8));
            zip.closeEntry();
        }

        System.out.println("Đã tạo: " + zipPath.toAbsolutePath());
    }
}
~~~

Kết quả là tệp `example.zip` gồm thư mục `docs/`, tệp `docs/readme.txt` và `config.txt`.

### 4.1. Dấu phân cách đường dẫn ZIP

Một tên entry nên viết như:

~~~java
new ZipEntry("docs/readme.txt");
~~~

Không nên tạo tên entry bằng cách nối trực tiếp các chuỗi `Path.toString()` trên Windows: đường dẫn hệ điều hành có thể dùng dấu `\`, trong khi tên ZIP nên dùng `/`.

Khi muốn đưa một đường dẫn tương đối vào ZIP, có thể chuyển thành tên entry:

~~~java
Path relative = Path.of("docs", "readme.txt");
String entryName = relative.toString().replace('\\', '/');
~~~

Chỉ áp dụng cho **đường dẫn tương đối đã được kiểm soát**. Không lấy trực tiếp đường dẫn tuyệt đối hoặc tên do người dùng gửi rồi đưa vào ZIP mà không xác thực.

### 4.2. Đóng entry và đóng stream khác nhau

- `closeEntry()` hoàn tất entry hiện tại để bắt đầu entry kế tiếp.
- `close()` trên `ZipOutputStream` hoàn tất ZIP và đóng luồng phía dưới.
- `finish()` có thể hoàn tất cấu trúc ZIP mà không đóng luồng cơ sở; chỉ dùng khi thực sự cần quản lý vòng đời stream theo cách đó.

Trong phần lớn chương trình ghi file ZIP, try-with-resources là lựa chọn rõ ràng nhất. Nếu xảy ra ngoại lệ trong khi ghi, ZIP có thể chưa hoàn chỉnh; không coi file đó là archive hợp lệ để phát hành.

## 5. Nén toàn bộ thư mục bằng Files.walkFileTree

Khi cần đóng gói một cây thư mục, `Files.walkFileTree` cho phép duyệt có cấu trúc và xử lý I/O bằng `IOException` mà không cần giữ toàn bộ danh sách tệp trong bộ nhớ.

Ví dụ dưới đây:

- Giữ đường dẫn tương đối bên trong ZIP.
- Thêm entry thư mục, kể cả thư mục rỗng.
- Không đưa bản thân thư mục gốc làm tiền tố bắt buộc.
- Không đi theo symbolic link khi duyệt cây.
- Chỉ đóng gói **regular files**; bỏ qua symbolic link và các loại tệp đặc biệt.
- Từ chối đặt ZIP đầu ra bên trong thư mục nguồn để tránh vô tình nén chính ZIP đang tạo.

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

public class ZipDirectoryExample {
    static void zipDirectory(Path directory, Path outputZip)
            throws IOException {

        Path source = directory.toAbsolutePath().normalize();
        Path archive = outputZip.toAbsolutePath().normalize();

        if (!Files.isDirectory(source)) {
            throw new IllegalArgumentException(
                    "Không phải thư mục nguồn: " + source
            );
        }

        if (archive.startsWith(source)) {
            throw new IllegalArgumentException(
                    "ZIP đầu ra phải nằm ngoài thư mục nguồn"
            );
        }

        Files.createDirectories(archive.getParent());

        try (ZipOutputStream zip = new ZipOutputStream(
                Files.newOutputStream(
                        archive,
                        StandardOpenOption.CREATE_NEW,
                        StandardOpenOption.WRITE
                ),
                StandardCharsets.UTF_8)) {

            Files.walkFileTree(source, new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult preVisitDirectory(
                        Path dir, BasicFileAttributes attrs)
                        throws IOException {

                    if (!dir.equals(source)) {
                        String name = source.relativize(dir)
                                .toString().replace('\\', '/') + "/";

                        zip.putNextEntry(new ZipEntry(name));
                        zip.closeEntry();
                    }

                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFile(
                        Path file, BasicFileAttributes attrs)
                        throws IOException {

                    if (!attrs.isRegularFile()) {
                        // Bỏ qua symbolic link và loại tệp đặc biệt.
                        return FileVisitResult.CONTINUE;
                    }

                    String name = source.relativize(file)
                            .toString().replace('\\', '/');

                    zip.putNextEntry(new ZipEntry(name));
                    Files.copy(file, zip);
                    zip.closeEntry();

                    return FileVisitResult.CONTINUE;
                }
            });
        }
    }

    public static void main(String[] args) throws IOException {
        Path root = Path.of("input");

        Files.createDirectories(root.resolve("docs"));
        Files.writeString(
                root.resolve("docs/readme.txt"),
                "Học ZIP trên Java 27\n",
                StandardCharsets.UTF_8
        );
        Files.writeString(
                root.resolve("config.properties"),
                "enabled=true\n",
                StandardCharsets.UTF_8
        );

        zipDirectory(root, Path.of("output.zip"));
        System.out.println("Đã tạo output.zip");
    }
}
~~~

**Lưu ý khi chạy lại:** `StandardOpenOption.CREATE_NEW` từ chối ghi đè nếu `output.zip` đã tồn tại. Đây là hành vi có chủ đích nhằm tránh làm mất dữ liệu cũ. Hãy chọn tên đích mới hoặc quản lý việc thay thế archive theo nghiệp vụ.

Ví dụ giả định thư mục nguồn do ứng dụng kiểm soát, không bị một tiến trình không tin cậy thay đổi liên tục ngay lúc đóng gói. Nếu nguồn có thể bị sửa đồng thời, cần cơ chế snapshot hoặc đồng bộ theo yêu cầu nhất quán.

## 6. Phương thức nén: DEFLATED và STORED

`ZipEntry` có hai phương thức thường dùng trong API ZIP chuẩn:

- **`ZipEntry.DEFLATED`**: dữ liệu được nén bằng DEFLATE; đây là cách ghi mặc định của `ZipOutputStream`.
- **`ZipEntry.STORED`**: dữ liệu được lưu mà không nén.

DEFLATED tiện cho văn bản hoặc dữ liệu dễ nén. STORED hữu ích khi dữ liệu đã được nén sẵn hoặc khi muốn tránh chi phí nén bổ sung.

### 6.1. Chỉnh mức nén

~~~java
import java.util.zip.Deflater;

zip.setLevel(Deflater.BEST_SPEED);
// Hoặc Deflater.DEFAULT_COMPRESSION / BEST_COMPRESSION.
~~~

Đoạn trên giả định `zip` là `ZipOutputStream` đang mở. Mức nén ảnh hưởng đến sự đánh đổi tốc độ CPU và kích thước đầu ra; **BEST_COMPRESSION không bảo đảm ZIP nhỏ nhất** đối với mọi dữ liệu.

### 6.2. STORED cần size và CRC-32 chính xác

Đối với entry STORED, `ZipOutputStream` cần biết kích thước, kích thước nén và CRC-32 trước khi ghi entry.

~~~java
import java.nio.charset.StandardCharsets;
import java.util.zip.CRC32;
import java.util.zip.ZipEntry;

byte[] data = "Đã nén sẵn".getBytes(StandardCharsets.UTF_8);

CRC32 crc = new CRC32();
crc.update(data);

ZipEntry entry = new ZipEntry("stored.txt");
entry.setMethod(ZipEntry.STORED);
entry.setSize(data.length);
entry.setCompressedSize(data.length);
entry.setCrc(crc.getValue());

zip.putNextEntry(entry);
zip.write(data);
zip.closeEntry();
~~~

Ví dụ này dùng `byte[]` nhỏ để minh họa cách xác định metadata. Với file lớn, có thể tính size và CRC-32 bằng lượt đọc theo buffer trước, rồi mở lượt đọc thứ hai để ghi nội dung mà không cần giữ cả file trong RAM.

Nếu size hoặc CRC khai báo không khớp dữ liệu được ghi, thao tác ZIP có thể lỗi. CRC-32 là checksum kiểm tra hỏng dữ liệu ngoài ý muốn, **không phải chữ ký số và không chứng minh archive đáng tin cậy**.

## 7. Đọc ZIP tuần tự bằng ZipInputStream

`ZipInputStream` phù hợp khi dữ liệu ZIP đến từ một `InputStream` hoặc khi bạn muốn đọc lần lượt mọi entry.

Quy trình:

1. Tạo `ZipInputStream`.
2. Gọi `getNextEntry()` để tiến đến entry kế tiếp; nếu hết, phương thức trả `null`.
3. Đọc bytes của entry hiện tại.
4. Gọi `closeEntry()` trước khi chuyển sang entry tiếp theo.
5. Đóng stream khi hoàn thành.

Ví dụ liệt kê entry và đọc văn bản từ archive:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

public class ReadZipSequentially {
    public static void main(String[] args) throws IOException {
        Path archive = Path.of("output.zip");

        try (ZipInputStream zip = new ZipInputStream(
                Files.newInputStream(archive),
                StandardCharsets.UTF_8)) {

            ZipEntry entry;
            byte[] buffer = new byte[8192];

            while ((entry = zip.getNextEntry()) != null) {
                System.out.println("Entry: " + entry.getName());

                if (!entry.isDirectory()) {
                    long bytesRead = 0;
                    int count;

                    while ((count = zip.read(buffer)) != -1) {
                        bytesRead += count;
                    }

                    System.out.println(
                            "Số byte đã giải nén: " + bytesRead
                    );
                }

                zip.closeEntry();
            }
        }
    }
}
~~~

Đoạn mã chỉ đếm byte đã giải nén, không lưu nội dung. Thay vào đó, nếu biết entry chứa văn bản UTF-8 và kích thước nhỏ, có thể đọc bytes rồi chuyển thành chuỗi. Với entry lớn hoặc không tin cậy, **không dùng `readAllBytes()` hoặc `readNBytes` với giới hạn quá cao** mà không tính toán ngân sách bộ nhớ.

### 7.1. Chỉ đọc đến cuối entry hiện tại

Khi đang ở một entry, `zip.read(...)` trả `-1` khi đã đọc hết nội dung của entry đó. Sau `closeEntry()`, gọi `getNextEntry()` để nhận entry kế tiếp.

Điều này cho phép xử lý ZIP có nhiều entry bằng một buffer cố định, không phải đưa toàn bộ archive vào bộ nhớ.

### 7.2. Metadata có thể chưa đầy đủ trước khi đọc xong

Trong ZIP, một số metadata có thể được ghi ở cuối nội dung entry hoặc chỉ biết khi tra cứu directory của archive. Vì vậy, khi dùng `ZipInputStream`, các phương thức như `entry.getSize()` hoặc `entry.getCompressedSize()` có thể trả `-1` nếu thông tin chưa biết ở thời điểm đó.

**Không dùng kích thước metadata khai báo làm giới hạn bảo vệ duy nhất.** Với ZIP từ nguồn không tin cậy, phải đo số byte thực tế được giải nén.

### 7.3. Tại sao không dùng ZipInputStream để tìm một entry ở cuối archive?

`ZipInputStream` phải tiến qua các entry theo thứ tự stream. Nếu cần truy cập thường xuyên một entry cụ thể, thao tác này có thể phải quét archive nhiều lần.

Với ZIP là tệp sẵn có trên đĩa và cần truy xuất chọn lọc, `ZipFile` thường tiện hơn.

## 8. Truy cập entry theo tên với ZipFile

`ZipFile` đọc cấu trúc archive và cung cấp API tìm entry:

- `getEntry(name)`: tìm entry theo tên.
- `entries()`: liệt kê entry qua `Enumeration`.
- `stream()`: cung cấp stream các `ZipEntry`.
- `getInputStream(entry)`: mở luồng đọc nội dung entry.

Ví dụ lấy tệp văn bản trong ZIP:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

public class ReadZipByName {
    public static void main(String[] args) throws IOException {
        Path archive = Path.of("output.zip");

        try (ZipFile zip = new ZipFile(
                archive.toFile(),
                StandardCharsets.UTF_8)) {

            ZipEntry entry = zip.getEntry("docs/readme.txt");

            if (entry == null) {
                throw new IOException("ZIP không có docs/readme.txt");
            }

            try (InputStream input = zip.getInputStream(entry)) {
                // Chỉ phù hợp khi biết trước entry là văn bản nhỏ.
                String text = new String(
                        input.readAllBytes(),
                        StandardCharsets.UTF_8
                );

                System.out.println(text);
            }
        }
    }
}
~~~

Trong ví dụ, `readAllBytes()` chỉ được sử dụng vì bài toán giả định **entry nhỏ và đã biết**. Đối với dữ liệu lớn, thay bằng buffer cố định, `transferTo` hoặc API đọc theo dòng có giới hạn.

### 8.1. Liệt kê entry và metadata

~~~java
try (ZipFile zip = new ZipFile(
        Path.of("output.zip").toFile(),
        StandardCharsets.UTF_8)) {

    zip.stream().forEach(entry -> {
        System.out.println(entry.getName());
        System.out.println("Directory: " + entry.isDirectory());
        System.out.println("Size: " + entry.getSize());
        System.out.println("Compressed: " + entry.getCompressedSize());
        System.out.println("CRC: " + entry.getCrc());
    });
}
~~~

Một số trường có thể trả giá trị không xác định, tùy entry và archive. Metadata được đọc từ ZIP không nên xem là bằng chứng bảo mật hoặc bảo đảm nội dung là hợp lệ.

### 8.2. Quản lý tài nguyên

`ZipFile` giữ tài nguyên phục vụ truy cập archive. Mỗi `getInputStream(entry)` cũng trả một stream cần đóng. Vì vậy, nên dùng **try-with-resources lồng nhau** như ví dụ.

Không trả một `InputStream` lấy từ `ZipFile` ra ngoài phạm vi nơi `ZipFile` đã bị đóng mà vẫn kỳ vọng tiếp tục đọc được.

## 9. So sánh ZipInputStream và ZipFile

| Tiêu chí | ZipInputStream | ZipFile |
|---|---|---|
| Nguồn | Bất kỳ `InputStream` thích hợp | Tệp ZIP |
| Duyệt | Tuần tự từ đầu tới cuối | Có thể chọn entry theo tên |
| Tìm entry | Phải duyệt đến khi gặp | `getEntry(name)` |
| Kiểu xử lý phù hợp | Stream/archive đang tải về hoặc xử lý một lần | ZIP trên đĩa, đọc chọn lọc nhiều entry |
| Kích thước entry biết trước | Có thể chưa biết | Thường có thông tin từ central directory |
| Ghi entry mới | Không | Không |
| Quản lý tài nguyên | Đóng `ZipInputStream` | Đóng `ZipFile` và input stream của entry |

Cả hai API đều đọc/giải nén nội dung entry. Không nên chọn chỉ vì tên lớp; hãy xem nguồn dữ liệu là stream hay file và liệu cần truy cập ngẫu nhiên hay không.

## 10. ZIP FileSystem: xem ZIP như một hệ thống tệp

Java NIO.2 hỗ trợ các `FileSystemProvider` khác nhau. **ZIP File System Provider** triển khai một hệ thống tệp lưu trữ bên trong archive ZIP.

Khi mở thành công, bạn có thể làm việc như sau:

~~~text
Archive trên ổ đĩa:  backups/data.zip
                           |
                           v
                   FileSystem ZIP
                           |
                       getPath("/")
                           |
           +---------------+---------------+
           |                               |
       /docs/readme.txt                /config.txt
           |                               |
       Files.readString                 Files.copy
~~~

Điểm khác biệt là các `Path` lấy từ ZIPFS **thuộc hệ thống tệp ZIP**, không phải hệ thống tệp mặc định của hệ điều hành.

### 10.1. Module jdk.zipfs

Trong JDK thông thường, provider này nằm trong module **`jdk.zipfs`**. Nó là một module cung cấp dịch vụ file-system provider, **không phải phụ thuộc vào một thư viện ZIP bên thứ ba**.

Tuy nhiên, khi đóng gói một custom runtime image bằng `jlink`, không được mặc định rằng module này luôn có mặt. Nếu ứng dụng cần ZIPFS, phải đảm bảo runtime chứa provider phù hợp; nếu không, thao tác mở ZIP bằng `FileSystems` có thể ném `ProviderNotFoundException`.

Các API `java.util.zip` nằm trong `java.base` và không cần provider ZIPFS để hoạt động.

## 11. Tạo ZIP bằng FileSystems.newFileSystem

Ví dụ tạo một ZIP mới qua API `Path`/`Files`:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

public class CreateZipFileSystem {
    public static void main(String[] args) throws IOException {
        Path zipPath = Path.of("via-zipfs.zip");

        try (FileSystem zipfs = FileSystems.newFileSystem(
                zipPath,
                Map.of("create", "true"))) {

            Path docs = zipfs.getPath("/docs");
            Files.createDirectories(docs);

            Path readme = zipfs.getPath("/docs/readme.txt");
            Files.writeString(
                    readme,
                    "Dữ liệu trong ZIPFS\n",
                    StandardCharsets.UTF_8
            );

            Path config = zipfs.getPath("/config.properties");
            Files.writeString(
                    config,
                    "active=true\n",
                    StandardCharsets.UTF_8
            );
        }

        System.out.println("Đã tạo ZIP qua FileSystem");
    }
}
~~~

Giải thích:

- `zipPath` là đường dẫn ZIP trên hệ thống tệp máy chủ.
- Environment `Map.of("create", "true")` yêu cầu provider tạo archive nếu chưa tồn tại.
- `zipfs.getPath("/docs")` tạo đường dẫn **bên trong ZIP**.
- `Files.createDirectories` và `Files.writeString` làm việc trên `Path` của ZIPFS.
- `close()` của `FileSystem` rất quan trọng để hoàn tất và giải phóng tài nguyên của provider.

Cơ chế ZIPFS có thể cần tái cấu trúc archive khi đóng hoặc ghi cập nhật. Không giả định mọi thao tác sửa ZIP có tính nguyên tử như một transaction.

### 11.1. Tạo mới và mở ZIP đã tồn tại

Với ZIP **đã tồn tại**, mở không cần yêu cầu tạo:

~~~java
Path zipPath = Path.of("via-zipfs.zip");

try (FileSystem zipfs = FileSystems.newFileSystem(
        zipPath,
        Map.of())) {

    Path readme = zipfs.getPath("/docs/readme.txt");

    String text = Files.readString(
            readme,
            StandardCharsets.UTF_8
    );

    System.out.println(text);
}
~~~

Đối với archive không tồn tại, `Map.of()` không yêu cầu tạo. Khi chạy các ví dụ này, cần phân biệt:

- Đường dẫn đến archive nằm trên hệ thống tệp thật.
- Đường dẫn bên trong archive bắt đầu từ gốc ZIPFS, ví dụ `/docs/readme.txt`.

### 11.2. Cách mở bằng jar: URI

Ngoài overload dùng `Path`, có thể dùng URI có scheme `jar:` đối với ZIP/JAR:

~~~java
import java.net.URI;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Path;
import java.util.Map;

Path zip = Path.of("via-zipfs.zip").toAbsolutePath();
URI uri = URI.create("jar:" + zip.toUri());

try (FileSystem zipfs = FileSystems.newFileSystem(
        uri,
        Map.of())) {

    System.out.println(zipfs.getPath("/docs/readme.txt"));
}
~~~

Overload dùng `Path` thường đơn giản hơn nếu bạn đã có đối tượng `Path` của file ZIP.

Khi dùng URI, việc mở lại cùng một file system đang tồn tại trong cùng runtime có thể gặp `FileSystemAlreadyExistsException`. Cần quản lý vòng đời, tái sử dụng khi phù hợp và đóng đúng chỗ.

## 12. Duyệt, đọc, sửa và xóa bằng ZIPFS

Sau khi mở ZIPFS, nhiều thao tác NIO quen thuộc có thể áp dụng.

### 12.1. Liệt kê file với Files.walk

~~~java
import java.io.IOException;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.stream.Stream;

public class ListZipFiles {
    public static void main(String[] args) throws IOException {
        try (FileSystem zipfs = FileSystems.newFileSystem(
                Path.of("via-zipfs.zip"),
                Map.of())) {

            Path root = zipfs.getPath("/");

            try (Stream<Path> paths = Files.walk(root)) {
                paths.filter(Files::isRegularFile)
                        .forEach(System.out::println);
            }
        }
    }
}
~~~

`Files.walk` trả một `Stream<Path>` quản lý tài nguyên; nên đóng stream bằng try-with-resources. Đừng chỉ đóng ZIPFS mà bỏ qua stream từ `Files.walk` khi vẫn còn đang duyệt.

### 12.2. Chép file từ hệ thống tệp thường vào ZIP

~~~java
import java.nio.file.StandardCopyOption;

Path destination = zipfs.getPath("/docs/notes.txt");

Files.createDirectories(destination.getParent());
Files.copy(
        Path.of("notes.txt"),
        destination,
        StandardCopyOption.REPLACE_EXISTING
);
~~~

Đoạn mã giả định `zipfs` đang mở và `notes.txt` tồn tại trên hệ thống tệp mặc định.

### 12.3. Chép file từ ZIP ra bên ngoài

~~~java
Path source = zipfs.getPath("/docs/readme.txt");
Path destination = Path.of("exported-readme.txt");

Files.copy(
        source,
        destination,
        StandardCopyOption.REPLACE_EXISTING
);
~~~

Đối với một đường dẫn ZIPFS **đã biết và tin cậy**, thao tác sao chép này đơn giản. Nếu đường dẫn đích được xây từ **tên entry không tin cậy**, cần kiểm tra chống path traversal trước khi ghi ra hệ thống tệp ngoài ZIP.

### 12.4. Di chuyển và xóa entry

~~~java
Path oldFile = zipfs.getPath("/docs/notes.txt");
Path newFile = zipfs.getPath("/docs/notes-renamed.txt");

Files.move(
        oldFile,
        newFile,
        StandardCopyOption.REPLACE_EXISTING
);

Files.deleteIfExists(newFile);
~~~

Các khả năng của `Files.move`, `Files.delete` và metadata có thể phụ thuộc vào provider. Không suy luận rằng mọi thuộc tính, kiểu liên kết hoặc bảo đảm atomic move của file system mặc định đều được ZIPFS hỗ trợ như nhau.

### 12.5. ZIPFS là một view, không phải thư mục đã giải nén

~~~text
File thường:         C:\data\backup.zip
ZIPFS path:           /docs/readme.txt
Hệ thống tệp thực:    C:\data\exported-readme.txt
~~~

Hai `Path` có thể trông giống chuỗi đường dẫn nhưng thuộc hai provider khác nhau. Khi tạo path bên trong ZIPFS, sử dụng `zipfs.getPath(...)` chứ không dùng `Path.of(...)` của hệ thống tệp mặc định.

## 13. Encoding tên entry và nội dung tệp

ZIP có ít nhất **hai vấn đề encoding độc lập**:

1. **Tên entry** như `docs/giới-thiệu.txt`.
2. **Nội dung byte của entry**, ví dụ một văn bản UTF-8.

Khi ghi hoặc đọc tên entry bằng `ZipInputStream`, `ZipOutputStream` hay `ZipFile`, Java cung cấp constructor nhận `Charset`.

Ví dụ:

~~~java
ZipOutputStream output = new ZipOutputStream(
        Files.newOutputStream(Path.of("documents.zip")),
        StandardCharsets.UTF_8
);
~~~

Và khi đọc:

~~~java
ZipInputStream input = new ZipInputStream(
        Files.newInputStream(Path.of("documents.zip")),
        StandardCharsets.UTF_8
);
~~~

Java hiện đại dùng UTF-8 theo mặc định cho tên entry trong những constructor ZIP phổ biến không chỉ định charset. Với archive được tạo bởi công cụ cũ sử dụng bảng mã khác, có thể cần xác định charset phù hợp. Tuy nhiên, nếu archive đánh dấu tên entry bằng UTF-8 theo cờ tương ứng của định dạng ZIP, Java tuân theo quy ước đó; không phải lúc nào truyền charset khác cũng thay thế được cờ encoding trong archive.

**Charset tên entry không tự chuyển mã nội dung file.**

Ví dụ, tên `docs/readme.txt` được giải mã đúng không bảo đảm nội dung bên trong đã là UTF-8. Khi đọc văn bản, hãy biết hoặc xác định encoding của nội dung:

~~~java
String text = new String(data, StandardCharsets.UTF_8);
~~~

Với dữ liệu nhị phân như ảnh, PDF hoặc file executable, **không chuyển qua String**. Hãy chép byte qua `InputStream` và `OutputStream`.

## 14. Giải nén an toàn: Zip Slip (path traversal)

Một nguy cơ bảo mật phổ biến xuất hiện khi ứng dụng lấy tên entry trong ZIP và dùng trực tiếp làm đường dẫn đầu ra.

Giả sử ZIP có entry:

~~~text
../../outside.txt
~~~

Nếu giải nén mà không kiểm tra, đường dẫn này có thể thoát khỏi thư mục đích và ghi đè file ở vị trí ngoài dự kiến. Lỗ hổng này thường được gọi là **Zip Slip**.

### 14.1. Ví dụ sai cần tránh

~~~java
// KHÔNG AN TOÀN: tên entry có thể chứa "../".
Path output = destinationDirectory.resolve(entry.getName());
Files.copy(zipInput, output);
~~~

Không được tin rằng archive ZIP luôn do công cụ hợp lệ tạo ra hoặc tên entry đã được làm sạch.

### 14.2. Nguyên tắc kiểm tra đường dẫn

Giả sử `destinationDirectory` là thư mục giải nén được ứng dụng quản lý:

~~~java
Path root = destinationDirectory
        .toAbsolutePath()
        .normalize();

String name = entry.getName();

Path target = root.resolve(name).normalize();

if (target.equals(root) || !target.startsWith(root)) {
    throw new IOException("Tên entry vượt ngoài thư mục đích");
}
~~~

Quy tắc này là **tối thiểu cần có**, nhưng chưa đủ để chống mọi dạng tấn công: một đường dẫn con có thể đang là symbolic link dẫn ra ngoài thư mục đích, hoặc bị một tiến trình khác thay đổi giữa lúc kiểm tra và lúc tạo file.

Đối với dữ liệu từ nguồn không tin cậy, cần cân nhắc thêm:

- Từ chối tên entry tuyệt đối và tên chứa ký tự phân tách không mong muốn.
- Kiểm tra các thành phần đường dẫn, đặc biệt symbolic link đã tồn tại.
- Sử dụng thư mục đích mới, riêng tư và không cho tác nhân không tin cậy thay đổi trong lúc giải nén.
- Không ghi đè file đã tồn tại nếu nghiệp vụ không cho phép.
- Khi cần chống tấn công đồng thời bằng symbolic link hoặc race condition, dùng cơ chế truy cập thư mục an toàn theo file descriptor, ví dụ kiểm tra hỗ trợ `SecureDirectoryStream` của provider và thiết kế thao tác tương ứng.

## 15. Giải nén có kiểm soát kích thước và số entry

Ngoài Zip Slip, ứng dụng còn phải tính đến **ZIP bomb**: archive có thể rất nhỏ ở trạng thái nén nhưng giải nén thành lượng dữ liệu cực lớn hoặc có số entry quá nhiều.

**Không thể chỉ dựa vào `ZipEntry.getSize()` hoặc tỷ lệ nén được khai báo.** Cần đếm byte thực tế sau khi giải nén và áp dụng giới hạn phù hợp.

Ví dụ sau minh họa cách giải nén ZIP bằng `ZipInputStream` vào một **thư mục đích tin cậy, không bị tác nhân khác chỉnh sửa đồng thời**, đồng thời:

- Từ chối tên entry vượt khỏi root.
- Từ chối ký tự backslash trong tên entry để tránh mơ hồ nền tảng.
- Kiểm tra symbolic link ở các thành phần thuộc root đã quản lý.
- Dùng `CREATE_NEW`, không ghi đè file sẵn có.
- Giới hạn số entry, số byte mỗi entry và tổng số byte giải nén.

~~~java
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

public class BoundedZipExtractor {
    private static final int MAX_ENTRIES = 10_000;
    private static final long MAX_ENTRY_BYTES = 50L * 1024 * 1024;
    private static final long MAX_TOTAL_BYTES = 200L * 1024 * 1024;

    static void ensureNoSymlinks(Path root, Path target)
            throws IOException {
        if (Files.isSymbolicLink(root)) {
            throw new IOException("Root là symbolic link: " + root);
        }

        Path cursor = root;
        for (Path component : root.relativize(target)) {
            cursor = cursor.resolve(component);
            if (Files.isSymbolicLink(cursor)) {
                throw new IOException(
                        "Đường dẫn chứa symbolic link: " + cursor
                );
            }
        }
    }

    static void extract(Path sourceZip, Path destination)
            throws IOException {

        Path root = destination.toAbsolutePath().normalize();

        // Ứng dụng phải sở hữu root và ngăn tiến trình khác
        // thay đổi cây thư mục đích trong lúc giải nén.
        Files.createDirectories(root);
        ensureNoSymlinks(root, root);

        int entries = 0;
        long totalBytes = 0;

        try (ZipInputStream zip = new ZipInputStream(
                Files.newInputStream(sourceZip),
                StandardCharsets.UTF_8)) {

            ZipEntry entry;
            byte[] buffer = new byte[8192];

            while ((entry = zip.getNextEntry()) != null) {
                if (++entries > MAX_ENTRIES) {
                    throw new IOException("ZIP có quá nhiều entry");
                }

                String name = entry.getName();

                if (name.isBlank()
                        || name.startsWith("/")
                        || name.indexOf('\\') >= 0) {
                    throw new IOException(
                            "Tên entry không được chấp nhận: " + name
                    );
                }

                Path target = root.resolve(name).normalize();
                if (target.equals(root) || !target.startsWith(root)) {
                    throw new IOException(
                            "Entry vượt ra ngoài root: " + name
                    );
                }

                if (entry.isDirectory()) {
                    ensureNoSymlinks(root, target);
                    Files.createDirectories(target);
                    ensureNoSymlinks(root, target);

                    // Directory entry hợp lệ không chứa dữ liệu.
                    // Không closeEntry() trên payload chưa kiểm soát.
                    if (zip.read(buffer) != -1) {
                        throw new IOException(
                                "Entry thư mục chứa dữ liệu: " + name
                        );
                    }
                } else {
                    Path parent = target.getParent();

                    ensureNoSymlinks(root, parent);
                    Files.createDirectories(parent);
                    ensureNoSymlinks(root, parent);
                    ensureNoSymlinks(root, target);

                    if (Files.exists(
                            target, LinkOption.NOFOLLOW_LINKS)) {
                        throw new IOException(
                                "Đường dẫn đã tồn tại: " + target
                        );
                    }

                    long entryBytes = 0;

                    try (OutputStream output = Files.newOutputStream(
                            target,
                            StandardOpenOption.CREATE_NEW,
                            StandardOpenOption.WRITE)) {

                        int read;
                        while ((read = zip.read(buffer)) != -1) {
                            entryBytes += read;
                            totalBytes += read;

                            if (entryBytes > MAX_ENTRY_BYTES
                                    || totalBytes > MAX_TOTAL_BYTES) {
                                throw new IOException(
                                        "Vượt giới hạn giải nén"
                                );
                            }

                            output.write(buffer, 0, read);
                        }
                    }
                }

                zip.closeEntry();
            }
        }
    }

    public static void main(String[] args) throws IOException {
        extract(
                Path.of("output.zip"),
                Path.of("unzipped")
        );
    }
}
~~~

Ví dụ giới hạn minh họa, **không phải chính sách mặc định của Java**. Sản phẩm cần chọn hạn mức phù hợp với khối lượng dữ liệu, số tệp và tài nguyên hệ thống.

### 15.1. Những giới hạn của ví dụ an toàn cơ bản

Hàm này giả định **đường dẫn gốc cùng các thành phần cha đáng tin cậy** và không có tiến trình đối kháng thay đổi đường dẫn trong lúc giải nén. Kiểm tra bằng `Files.isSymbolicLink` riêng lẻ **không loại bỏ race condition** giữa bước kiểm tra và bước mở file.

Ngoài ra:

- Khi một entry vượt giới hạn, tệp đang ghi có thể còn ở trạng thái dở dang.
- Giới hạn byte thực giải nén không tự giới hạn thời gian CPU hoặc số lượng cấu trúc thư mục lồng quá sâu.
- ZIP có entry trùng tên sẽ bị từ chối khi `CREATE_NEW` không cho ghi đè.
- Một hệ thống quan trọng còn nên giới hạn độ dài tên, độ sâu đường dẫn, dung lượng đĩa, timeout, số lần giải nén, chính sách symbolic link và tổng tài nguyên.
- Để có hành vi giống giao dịch, giải nén vào một thư mục tạm **độc lập và được bảo vệ**, kiểm tra đầy đủ rồi chuyển kết quả vào vị trí đích theo chiến lược triển khai phù hợp.

Điều này không mâu thuẫn với mục đích ví dụ: nó minh họa các bước bảo vệ cần thiết, nhưng không tuyên bố tạo ra một bộ giải nén an toàn tuyệt đối cho mọi threat model.

## 16. ZIPFS và an toàn đường dẫn

ZIP FileSystem thuận tiện vì nó cung cấp `Path`, nhưng không có nghĩa mọi tên tệp từ ZIP đều đáng tin cậy.

Nếu một ứng dụng lấy tên entry do người ngoài kiểm soát rồi ghép thành đường dẫn trên hệ thống tệp thật, cần áp dụng các kiểm tra root/normalize, symbolic link và giới hạn dung lượng như với `ZipInputStream`.

Với ZIPFS, các thao tác đọc bên trong archive như:

~~~java
try (FileSystem zipfs = FileSystems.newFileSystem(
        Path.of("input.zip"), java.util.Map.of())) {

    Path candidate = zipfs.getPath("/docs/readme.txt");

    if (Files.isRegularFile(candidate)) {
        System.out.println(
                Files.readString(candidate, StandardCharsets.UTF_8)
        );
    }
}
~~~

là ví dụ xử lý đường dẫn **cố định do ứng dụng chỉ định**. Nếu muốn xuất mọi entry ra máy chủ, không nên biến nội dung có tên bất kỳ thành đường dẫn đích mà không kiểm tra.

Ngoài ra, một thư mục ZIPFS hoặc một file ZIP đang mở để chỉnh sửa không nên bị nhiều tiến trình khác cùng thay đổi trên đĩa theo cách không được điều phối. Đóng file system và kiểm tra archive sau cập nhật trước khi xuất bản.

## 17. Quản lý bộ nhớ, độ tin cậy và hiệu năng

### 17.1. Xử lý theo stream, tránh tải toàn bộ file

Với file lớn, thay:

~~~java
// Chỉ phù hợp khi biết chắc nội dung nhỏ:
byte[] bytes = input.readAllBytes();
~~~

bằng:

~~~java
try (InputStream input = zipFile.getInputStream(entry);
     OutputStream output = Files.newOutputStream(target)) {

    input.transferTo(output);
}
~~~

Đoạn mã này giả định `zipFile`, `entry` và `target` đã được xác thực, đồng thời **không phải một ví dụ giải nén archive không tin cậy**. Nếu cần giới hạn byte thực tế, sử dụng vòng đọc buffer có bộ đếm như ở mục trước.

`InputStream.transferTo` chuyển byte theo stream, giúp tránh giữ toàn bộ nội dung trong bộ nhớ ứng dụng.

### 17.2. Tránh tạo archive trong chính thư mục đang quét

Nếu đang nén thư mục `reports/` và cũng tạo `reports/backup.zip`, thao tác duyệt có thể nhìn thấy archive đang được ghi, khiến kết quả không mong muốn hoặc gây lỗi.

Hãy đặt ZIP đầu ra **ngoài cây nguồn**, hoặc thiết kế chính sách loại trừ archive đích một cách tường minh.

### 17.3. Đóng tài nguyên theo đúng thứ tự

Tương ứng từng API:

- `ZipOutputStream`: đóng sau khi ghi xong mọi entry.
- `ZipInputStream`: đóng khi đọc xong.
- `ZipFile`: đóng sau khi mọi stream đọc entry đã hoàn tất.
- ZIPFS `FileSystem`: đóng sau khi mọi thao tác trên `Path` bên trong archive đã xong.
- `Files.walk(...)`: đóng stream `Path` do nó trả về.

Sử dụng try-with-resources giúp việc đóng được thực hiện cả khi có ngoại lệ, tránh giữ file handle hoặc dữ liệu chưa được hoàn tất.

### 17.4. CRC không thay thế xác thực nguồn

ZIP lưu checksum để phát hiện một số lỗi dữ liệu. CRC-32 không chống được kẻ tấn công cố ý chỉnh sửa nội dung.

Nếu ứng dụng nhận ZIP cập nhật phần mềm hoặc dữ liệu nhạy cảm, cần cơ chế xác thực nguồn phù hợp như chữ ký số, checksum mật mã lấy từ kênh đáng tin cậy hoặc quy trình xác nhận riêng. Không xem “giải nén thành công” là bằng chứng nội dung an toàn.

### 17.5. Quy mô và cập nhật ZIPFS

ZIP có thể chứa nhiều entry. Việc duyệt đầy đủ, xây dựng thư mục hoặc cập nhật archive lớn có thể có chi phí I/O và bộ nhớ đáng kể.

Với khối lượng rất lớn:

- Đo thời gian nén và giải nén bằng dữ liệu thực.
- Dùng buffer và giới hạn tài nguyên.
- Cân nhắc xử lý một lượt bằng stream nếu chỉ cần đọc tuần tự.
- Cân nhắc `ZipFile` khi chỉ cần một số entry.
- Dùng ZIPFS nếu nhu cầu thao tác với cây thư mục thật sự quan trọng.
- Tránh giả định cập nhật một entry bằng ZIPFS luôn có chi phí cố định hoặc luôn là thao tác atomic.

## 18. Những ngoại lệ thường gặp

| Triệu chứng / ngoại lệ | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `NoSuchFileException` | Tệp ZIP hoặc tệp nguồn không tồn tại | Kiểm tra `Path` và bước tạo tệp |
| `FileAlreadyExistsException` | Dùng `CREATE_NEW` khi file đích đã tồn tại | Chọn tên khác hoặc áp dụng chính sách thay thế có chủ đích |
| `ZipException` | ZIP không hợp lệ, entry trùng tên khi ghi hoặc metadata sai | Kiểm tra archive và quá trình ghi |
| `ProviderNotFoundException` | Không có ZIP FileSystem provider phù hợp trong runtime | Kiểm tra module `jdk.zipfs` và cấu hình runtime image |
| `FileSystemAlreadyExistsException` | URI file system đã được mở trong cùng JVM | Tái sử dụng hoặc quản lý vòng đời ZIPFS |
| `UnsupportedOperationException` | Provider không hỗ trợ một thao tác/thuộc tính | Chọn thao tác mà provider hỗ trợ |
| `AccessDeniedException` | Thiếu quyền truy cập file/archive | Kiểm tra quyền và trạng thái file |
| `SecurityException` | Môi trường có chính sách truy cập từ chối thao tác | Xử lý theo mô hình bảo mật của môi trường |
| ZIP xuất ra không đọc được | Stream chưa được đóng hoặc lỗi giữa chừng | Đảm bảo hoàn tất archive, xử lý cleanup khi thất bại |
| Tên entry tiếng Việt sai | Encoding tên entry không khớp archive | Dùng UTF-8 cho ZIP mới, xác định charset của ZIP cũ |
| Giải nén ghi ngoài thư mục | Path traversal/Zip Slip | Validate root, normalize, symbolic link và quyền ghi |
| Hết đĩa/RAM khi giải nén | ZIP bomb, dữ liệu quá lớn, không giới hạn | Đếm byte thực giải nén, hạn mức entry/tổng, quota và timeout |

Trong mã ZIP thông thường, hãy xử lý `IOException` và các ngoại lệ chuyên biệt phù hợp từ API đang gọi. Không nên bỏ qua nguyên nhân lỗi hoặc coi archive đang ghi dở là kết quả hợp lệ.

## 19. Quy trình lựa chọn và triển khai thực tế

~~~text
                         Cần xử lý ZIP?
                               |
                   +-----------+-----------+
                   |                       |
                Tạo ZIP                 Đọc / sửa ZIP
                   |                       |
             ZIP mới từ dữ liệu       +-----+------+
                   |                 |            |
           ZipOutputStream       Đọc stream   Đã có file ZIP
                                     |            |
                               ZipInputStream  +--+---------+
                                               |            |
                                          Entry riêng   Thao tác cây
                                               |            |
                                            ZipFile       ZIPFS
~~~

Một quy trình thực tiễn:

1. **Xác định nguồn và độ tin cậy**: ZIP từ người dùng, Internet hay tệp do ứng dụng tạo?
2. **Chọn API phù hợp**: tuần tự, tra cứu entry hay làm việc như file system.
3. **Quyết định encoding**: mặc định dùng UTF-8 cho ZIP mới; xác thực encoding của nội dung văn bản.
4. **Kiểm soát đường dẫn**: không dùng đường dẫn tuyệt đối hoặc `..` từ input không tin cậy.
5. **Đặt giới hạn tài nguyên**: số entry, byte giải nén, độ sâu và kích thước archive.
6. **Xử lý theo stream** khi dữ liệu lớn.
7. **Đóng tài nguyên** bằng try-with-resources.
8. **Xử lý lỗi và dọn dẹp**: không xuất bản tệp ZIP dở dang hay thư mục giải nén một phần.
9. **Kiểm thử trên các tình huống đặc biệt**: tên Unicode, thư mục rỗng, entry trùng tên, ZIP hỏng, dữ liệu rất lớn và archive cố tình độc hại.
10. **Không đồng nhất checksum với xác thực**: đánh giá chữ ký số hoặc kiểm tra nguồn khi cần.

## 20. Ví dụ tổng hợp: tạo ZIP, đọc nội dung và bổ sung file qua ZIPFS

Ví dụ sau trình bày ba cách thao tác trên **cùng một archive** trong một chương trình:

1. Tạo ZIP bằng `ZipOutputStream`.
2. Đọc một entry bằng `ZipFile`.
3. Bổ sung một entry bằng ZIPFS rồi đọc lại kết quả.

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import java.util.zip.ZipOutputStream;

public class ZipEndToEndDemo {
    public static void main(String[] args) throws IOException {
        Path archive = Path.of("end-to-end.zip");

        // 1. Tạo ZIP mới.
        try (ZipOutputStream zip = new ZipOutputStream(
                Files.newOutputStream(archive),
                StandardCharsets.UTF_8)) {

            zip.putNextEntry(new ZipEntry("docs/"));
            zip.closeEntry();

            zip.putNextEntry(new ZipEntry("docs/hello.txt"));
            zip.write("Xin chào Java 27\n"
                    .getBytes(StandardCharsets.UTF_8));
            zip.closeEntry();
        }

        // 2. Đọc đúng entry cần dùng.
        try (ZipFile zip = new ZipFile(
                archive.toFile(),
                StandardCharsets.UTF_8)) {

            ZipEntry entry = zip.getEntry("docs/hello.txt");

            if (entry == null) {
                throw new IOException("Thiếu entry bắt buộc");
            }

            try (InputStream input = zip.getInputStream(entry)) {
                String text = new String(
                        input.readAllBytes(),
                        StandardCharsets.UTF_8
                );
                System.out.print(text);
            }
        }

        // 3. Mở ZIP đã tồn tại như FileSystem và thêm file.
        try (FileSystem zipfs = FileSystems.newFileSystem(
                archive,
                Map.of())) {

            Path note = zipfs.getPath("/docs/note.txt");

            Files.writeString(
                    note,
                    "Được ghi bằng ZIPFS\n",
                    StandardCharsets.UTF_8
            );
        }

        // 4. Xác nhận entry mới đã có sau khi đóng ZIPFS.
        try (ZipFile zip = new ZipFile(
                archive.toFile(),
                StandardCharsets.UTF_8)) {

            System.out.println(
                    zip.getEntry("docs/note.txt") != null
            ); // true
        }
    }
}
~~~

Kết quả mong đợi:

~~~text
Xin chào Java 27
true
~~~

Ví dụ tạo ZIP bằng `Files.newOutputStream(archive)`, nên nếu file đã tồn tại, nội dung cũ có thể bị thay thế. Trong ứng dụng thực tế, hãy chọn rõ chính sách ghi đè hoặc dùng `CREATE_NEW`/tệp tạm khi không được phép mất dữ liệu.

Chương trình chỉ xử lý các entry nhỏ do chính nó tạo ra; không dùng thẳng mã này để giải nén archive không tin cậy.

## 21. Tóm tắt kiến thức cần nhớ

- ZIP chứa nhiều **entry**; tên entry nên là đường dẫn tương đối dùng dấu `/`.
- Dùng `ZipOutputStream` để tạo ZIP, `ZipInputStream` khi cần đọc tuần tự và `ZipFile` khi cần lấy entry theo tên.
- Dùng **ZIPFS** khi muốn áp dụng `Path` và `Files` cho nội dung ZIP.
- ZIPFS thường cần provider `jdk.zipfs` trong runtime; custom runtime image có thể không chứa sẵn.
- Đóng đúng stream và file system; ZIP có thể chỉ hoàn chỉnh sau khi writer/file system kết thúc.
- Dùng UTF-8 nhất quán khi ghi ZIP mới; phân biệt encoding tên entry và nội dung entry.
- STORED cần size và CRC-32 chính xác; CRC không phải bằng chứng xác thực.
- Đừng đọc nguyên entry lớn vào RAM khi có thể xử lý theo buffer hoặc stream.
- Với ZIP không tin cậy, phòng chống **Zip Slip**, symbolic link và **ZIP bomb** bằng validation, giới hạn byte, số entry và chính sách lưu file.
- ZIPFS không tự biến việc giải nén/ghi ra hệ thống tệp thật thành thao tác an toàn.
- Chọn API theo nhu cầu, không theo giả định rằng một API là tốt nhất trong mọi tình huống.

## Tài liệu tham khảo chính thức

- [ZipInputStream — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/zip/ZipInputStream.html)
- [ZipOutputStream — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/zip/ZipOutputStream.html)
- [ZipFile — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/zip/ZipFile.html)
- [ZipEntry — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/zip/ZipEntry.html)
- [CRC32 — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/zip/CRC32.html)
- [FileSystems — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/FileSystems.html)
- [FileSystem — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/FileSystem.html)
- [Files — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/Files.html)
- [SecureDirectoryStream — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/SecureDirectoryStream.html)
- [Zip File System Provider (jdk.zipfs) — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.zipfs/module-summary.html)
