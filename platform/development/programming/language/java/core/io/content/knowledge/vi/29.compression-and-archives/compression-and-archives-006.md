# ZipFile: truy cập từng entry và quản lý vòng đời trong Java

Một tệp ZIP có thể chứa nhiều **entry**: tệp, thư mục và metadata liên quan. Nếu chương trình chỉ cần lấy một tệp cụ thể từ một archive có hàng trăm entry, không nhất thiết phải đọc lần lượt toàn bộ ZIP theo thứ tự. Lớp `java.util.zip.ZipFile` cung cấp cách **mở ZIP đã tồn tại và tra cứu từng entry**, lấy thông tin qua `ZipEntry`, rồi mở `InputStream` để giải nén nội dung entry mong muốn.

Nhưng các đối tượng này có **vòng đời gắn nhau**: `ZipFile` giữ tài nguyên của archive, còn các stream lấy từ `getInputStream()` phụ thuộc vào archive đang mở. Đóng archive quá sớm, để rò rỉ stream hoặc giải nén đường dẫn không tin cậy đều có thể gây lỗi. Bài viết giải thích cách dùng đúng API, sự khác nhau với `ZipInputStream`, xử lý dữ liệu lớn, lỗi phổ biến và biện pháp an toàn.

## 1. ZipFile, ZipEntry và InputStream có vai trò gì?

| Thành phần | Chức năng |
| --- | --- |
| `ZipFile` | Mở archive ZIP đã tồn tại, duyệt danh sách entry và tra cứu entry theo tên; giữ tài nguyên tới khi đóng |
| `ZipEntry` | Mô tả một entry: tên, thư mục/tệp, kích thước, phương pháp nén, CRC, thời gian... nếu metadata hiện diện |
| `ZipFile.getEntry(name)` | Tìm một entry có tên khớp; trả `null` khi không tìm thấy |
| `ZipFile.entries()` | Trả `Enumeration<? extends ZipEntry>` để duyệt entry |
| `ZipFile.stream()` | Trả `Stream<? extends ZipEntry>` để lọc/sắp xếp entry bằng Stream API |
| `ZipFile.getInputStream(entry)` | Mở một luồng đọc dữ liệu đã giải nén của entry; luồng cần được đóng |
| `ZipInputStream` | Đọc một luồng ZIP theo thứ tự entry, thường dùng khi dữ liệu đến từ `InputStream` thay vì một tệp ZIP có thể truy cập ngẫu nhiên |
| `ZipOutputStream` | Tạo tệp/luồng ZIP và ghi lần lượt các entry |

**ZipFile dùng cho tệp ZIP đã có trên đĩa.** Nó đọc cấu trúc của archive để tìm entry và cho phép ứng dụng mở luồng của một entry được chọn, thay vì phải tiêu thụ toàn bộ các entry trước đó như `ZipInputStream`. Tuy vậy, việc gọi `getEntry()` không có nghĩa toàn bộ nội dung entry đã được giải nén vào RAM: nội dung được đọc khi chương trình đọc `InputStream` tương ứng.

Một mô hình ZIP đơn giản:

```text
backup.zip
├── docs/                 (directory entry, có thể tồn tại tường minh)
│   ├── guide.txt         (file entry)
│   └── notes.txt         (file entry)
└── assets/
    └── logo.png          (file entry)
```

ZIP không nhất thiết chứa một entry riêng cho mọi thư mục cha. Chẳng hạn có thể tồn tại `docs/guide.txt` mà không có entry `docs/`. Vì thế `isDirectory()` chỉ cho biết **entry đang xét** có dạng directory, không bảo đảm mọi thư mục hiện diện thành entry riêng.

## 2. Mở ZipFile và trách nhiệm đóng tài nguyên

Những constructor thường dùng:

```java
ZipFile zip = new ZipFile("backup.zip");

ZipFile zipUtf8 = new ZipFile(
        new File("backup.zip"), StandardCharsets.UTF_8);
```

Đây là đoạn minh họa, cần các import `java.util.zip.ZipFile`, `java.io.File` và `java.nio.charset.StandardCharsets`; chương trình phải xử lý `IOException`. Khi muốn dùng `Path`, có thể gọi `path.toFile()` trên default filesystem tương thích với `File`.

`ZipFile` triển khai `Closeable`, nên dùng `try-with-resources`:

```java
try (ZipFile zip = new ZipFile(archive.toFile())) {
    ZipEntry entry = zip.getEntry("docs/guide.txt");
    if (entry == null) {
        throw new FileNotFoundException("Missing ZIP entry");
    }
    try (InputStream in = zip.getInputStream(entry)) {
        // Đọc nội dung của entry trong lúc ZipFile còn mở.
    }
}
```

Đây là mẫu minh họa với `archive` kiểu `Path`, cùng import `FileNotFoundException` / `InputStream`, chưa phải lớp Java độc lập.

Quy tắc vòng đời:

1. **Mở `ZipFile`** trước, giữ nó sống trong toàn bộ thời gian sử dụng các entry/stream.
2. **Tìm `ZipEntry`**; kiểm tra `null` nếu dùng tên entry từ đầu vào.
3. **Mở `InputStream`** cho entry cần đọc, tiêu thụ nội dung, rồi đóng stream bằng `try-with-resources`.
4. **Đóng `ZipFile`** ở ngoài cùng, sau khi các thao tác đọc đã kết thúc.

Theo hợp đồng API, đóng `ZipFile` cũng đóng những `InputStream` được trả về bởi `getInputStream()`. Tuy vậy, **đừng dựa vào điều này để cố ý bỏ qua đóng các stream**: đóng từng stream ở phạm vi nhỏ nhất giúp rõ quyền sở hữu, sớm thu hồi tài nguyên và tránh lỗi đọc trên archive đã đóng.

Sau khi `ZipFile.close()`, không tiếp tục gọi `getEntry()`, `entries()` hoặc đọc những stream gắn với archive như thể file vẫn còn mở. Nếu cần dữ liệu tồn tại độc lập sau khi đóng, phải **sao chép bytes hoặc xử lý hết nội dung** trong phạm vi `ZipFile` còn hoạt động.

## 3. Truy cập trực tiếp một entry theo tên

Ví dụ muốn đọc `config/app.properties` trong `settings.zip`:

```java
// Minh họa trong phương thức có xử lý IOException.
try (ZipFile zip = new ZipFile("settings.zip")) {
    ZipEntry entry = zip.getEntry("config/app.properties");
    if (entry == null) {
        System.out.println("Entry không tồn tại");
    } else if (entry.isDirectory()) {
        System.out.println("Đường dẫn chỉ một thư mục");
    } else {
        try (InputStream in = zip.getInputStream(entry)) {
            in.transferTo(System.out);
        }
    }
}
```

`getEntry(name)` nhận **tên entry được lưu trong ZIP**, không nhận đường dẫn filesystem bên ngoài. Trên ZIP thông thường, dấu `/` dùng phân tách thành phần tên, ví dụ `config/app.properties`. Không đổi nó thành `config\app.properties` chỉ vì hệ điều hành đang chạy là Windows.

Một số điểm dễ bỏ sót:

- **Tên phân biệt chữ hoa/chữ thường** theo chuỗi tên entry: `Guide.txt` và `guide.txt` không nên coi là một.
- `getEntry()` có thể trả `null`; phải kiểm tra trước `getInputStream()`.
- `entry.isDirectory()` dựa vào dấu `/` cuối tên theo quy ước `ZipEntry`; không nên đọc thư mục như file dữ liệu.
- Archive có thể chứa **tên entry trùng nhau**. `getEntry(name)` chỉ cho một entry phù hợp; nếu nghiệp vụ đòi hỏi xác định duy nhất, hãy duyệt toàn bộ và **từ chối tên trùng** thay vì suy đoán entry nào là “đúng”.
- `ZipFile` không tự trích xuất file ra ổ đĩa: đọc `InputStream` khác với ghi bytes vào đường dẫn đích.

## 4. Duyệt tất cả entry: Enumeration và Stream

Duyệt với `Enumeration`:

```java
try (ZipFile zip = new ZipFile("backup.zip")) {
    Enumeration<? extends ZipEntry> entries = zip.entries();
    while (entries.hasMoreElements()) {
        ZipEntry e = entries.nextElement();
        System.out.println(e.getName());
    }
}
```

Với `Stream` (Java 9+):

```java
try (ZipFile zip = new ZipFile("backup.zip")) {
    zip.stream()
            .filter(e -> !e.isDirectory())
            .map(ZipEntry::getName)
            .sorted()
            .forEach(System.out::println);
}
```

Cả hai là **đoạn minh họa** với import `ZipFile`, `ZipEntry` và `Enumeration`. `Enumeration` thích hợp cho vòng lặp cơ bản; `Stream` thuận tiện khi cần lọc và sắp xếp. **Hãy duyệt trong khi ZipFile đang mở**. Đóng `Stream` (nếu dùng `try-with-resources` cho stream) không thay thế `ZipFile.close()`.

Không giả định thứ tự entry do `entries()` hoặc `stream()` trả về giống thứ tự danh sách mong muốn. Nếu cần output ổn định, **tự sắp xếp** theo tên hoặc tiêu chí nghiệp vụ. Nếu ZIP cực lớn, cách `stream().sorted()` cần giữ metadata của nhiều entry để sắp xếp; duyệt tuần tự không sắp xếp sẽ tiết kiệm bộ nhớ hơn.

### ZipEntry chứa những metadata nào?

| API | Thông tin |
| --- | --- |
| `getName()` | Tên entry trong ZIP |
| `isDirectory()` | Entry có dạng thư mục theo quy ước tên kết thúc bằng `/` |
| `getSize()` | Số byte dữ liệu sau giải nén, có thể `-1` nếu chưa biết |
| `getCompressedSize()` | Số byte dữ liệu đã nén, có thể `-1` nếu chưa biết |
| `getCrc()` | CRC-32 lưu trong ZIP, có thể `-1` nếu chưa biết |
| `getMethod()` | Phương pháp nén, thường `ZipEntry.STORED` hoặc `ZipEntry.DEFLATED` |
| `getTime()` | Thời điểm sửa đổi, nếu có; có thể `-1` |
| `getComment()` | Ghi chú cho entry nếu có |
| `getExtra()` | Dữ liệu bổ sung trong phần metadata nếu có |

Các trường này **không đồng nghĩa với việc đã đọc/giải nén thành công payload**. Metadata trong ZIP có thể thiếu, không đáng tin hoặc không phù hợp kỳ vọng của ứng dụng. CRC-32 giúp phát hiện một số sai lệch ngẫu nhiên, **không phải chữ ký số, MAC hay cơ chế xác thực chống kẻ tấn công**.

## 5. Charset tên entry: dữ liệu byte khác với tên file

Các overload `ZipFile(File, Charset)` hoặc `ZipFile(File, int, Charset)` cho phép chỉ định charset để giải mã **tên entry và comment** khi định dạng tên trong archive không được đánh dấu UTF-8. Nếu ZIP entry có cờ UTF-8 theo đặc tả, tên của entry đó được giải mã bằng UTF-8 bất kể charset truyền vào.

Ví dụ khi phải đọc archive cũ được tạo bằng charset di sản:

```java
// Minh họa, cần biết chính xác encoding mà bên tạo ZIP đã dùng.
Charset legacy = Charset.forName("windows-1252");
try (ZipFile zip = new ZipFile(archive.toFile(), legacy)) {
    for (ZipEntry entry : java.util.Collections.list(zip.entries())) {
        System.out.println(entry.getName());
    }
}
```

Không chọn charset bằng cách thử ngẫu nhiên rồi dùng kết quả sai lệch cho tên file. Charset trong constructor **không tự động quyết định encoding nội dung văn bản bên trong một entry**; payload cần decoder đúng theo định dạng file hoặc giao thức riêng. Ví dụ một entry chứa văn bản UTF-16 vẫn có thể có tên ZIP được giải mã bằng UTF-8.

Với archive mới, nên ưu tiên UTF-8 nhất quán. Với archive nhận từ bên ngoài, đôi khi phải biết tool đã tạo ZIP và quy ước encoding để tránh tên bị lỗi.

## 6. Ví dụ Java 17+ hoàn chỉnh: tạo ZIP, chọn entry và đóng đúng vòng đời

Ví dụ sau tạo một ZIP tạm bằng `ZipOutputStream`, sau đó mở nó bằng `ZipFile` và đọc **một entry xác định**. Archive có ba entry, gồm một directory entry, một tệp trong thư mục và một tệp ở gốc.

Tạo file **`ZipFileEntryDemo.java`**:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Collectors;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import java.util.zip.ZipOutputStream;

public final class ZipFileEntryDemo {
    private ZipFileEntryDemo() {}

    public static void main(String[] args) throws IOException {
        Path archive = Files.createTempFile("zip-file-demo-", ".zip");

        try {
            try (ZipOutputStream output = new ZipOutputStream(
                    Files.newOutputStream(archive), StandardCharsets.UTF_8)) {
                output.putNextEntry(new ZipEntry("docs/"));
                output.closeEntry();
                addText(output, "docs/hello.txt", "Hello ZIP!\n");
                addText(output, "readme.txt", "Sample archive\n");
            }

            try (ZipFile zip = new ZipFile(
                    archive.toFile(), StandardCharsets.UTF_8)) {
                System.out.println("entries=" + zip.size());

                String names = zip.stream()
                        .map(ZipEntry::getName)
                        .sorted()
                        .collect(Collectors.joining(","));
                System.out.println("names=" + names);

                ZipEntry entry = zip.getEntry("docs/hello.txt");
                if (entry == null || entry.isDirectory()) {
                    throw new IOException("Expected text entry missing");
                }

                System.out.println("chosen=" + entry.getName());
                System.out.println("uncompressed bytes=" + entry.getSize());

                try (InputStream input = zip.getInputStream(entry)) {
                    byte[] content = input.readAllBytes();
                    System.out.println("text=" + new String(
                            content, StandardCharsets.UTF_8).strip());
                }

                System.out.println("missing="
                        + (zip.getEntry("missing.txt") == null));
            }
        } finally {
            Files.deleteIfExists(archive);
        }
    }

    private static void addText(ZipOutputStream output,
                                String name,
                                String content) throws IOException {
        output.putNextEntry(new ZipEntry(name));
        output.write(content.getBytes(StandardCharsets.UTF_8));
        output.closeEntry();
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac ZipFileEntryDemo.java
java ZipFileEntryDemo
```

Đầu ra trong môi trường I/O bình thường:

```text
entries=3
names=docs/,docs/hello.txt,readme.txt
chosen=docs/hello.txt
uncompressed bytes=11
text=Hello ZIP!
missing=true
```

**Giải thích:** `ZipOutputStream` tạo đúng ba entry: `docs/` (thư mục), `docs/hello.txt` và `readme.txt`. Lời gọi `zip.size()` đếm **entry**, không phải byte. `zip.stream()` lấy tên rồi `sorted()` để output không phụ thuộc thứ tự duyệt. `getEntry("docs/hello.txt")` chọn tệp dài 11 byte ASCII `Hello ZIP!\n`. `getInputStream(entry)` trả luồng byte đã giải nén để đọc; `strip()` bỏ ký tự xuống dòng trước khi in. `getEntry("missing.txt")` trả `null`.

Ví dụ chỉ gọi `readAllBytes()` với entry mà **chính chương trình đã tạo** và biết trước dài 11 byte. **Không dùng `readAllBytes()` vô điều kiện với ZIP không tin cậy**: dữ liệu sau giải nén có thể rất lớn dù ZIP nén nhỏ. Phần tiếp theo trình bày cách đọc theo luồng và đặt giới hạn.

### Kiểm soát vòng đời của ví dụ

- `ZipOutputStream` đóng trước khi `ZipFile` mở archive; điều này bảo đảm ZIP đã được ghi hoàn chỉnh phần cấu trúc cuối.
- `InputStream` của entry được đóng **trước** `ZipFile`.
- `ZipFile` được đóng trước khi xóa file tạm.
- Khối `finally` cố gắng dọn ZIP tạm ngay cả khi thao tác đọc thất bại.
- Không giữ tham chiếu stream hoặc dùng `ZipFile` sau khi đã đóng.

## 7. Đọc entry lớn theo luồng thay vì nạp toàn bộ vào heap

`ZipFile.getInputStream(entry)` cho phép đọc incremental bằng bộ đệm cố định. Ví dụ trích dữ liệu của một entry ra file đích với vòng lặp:

```java
// Đoạn minh họa, zip và entry còn hợp lệ;
// destination được ứng dụng kiểm soát và không trùng file ZIP.
try (InputStream input = zip.getInputStream(entry);
     OutputStream output = Files.newOutputStream(destination)) {

    byte[] buffer = new byte[8192];
    int read;
    while ((read = input.read(buffer)) != -1) {
        output.write(buffer, 0, read);
    }
}
```

Đây là đoạn minh họa cần import `OutputStream`/`Files`, xử lý `IOException`, và phải có chính sách bảo vệ `destination`. Nó tránh tạo mảng bằng toàn bộ uncompressed size, nhưng **không tự giới hạn tổng số byte được ghi ra đĩa**: nếu entry là ZIP bomb, vẫn có thể làm đầy thiết bị.

Một phiên bản kiểm soát tối đa số byte cho **một entry**:

```java
// Hàm độc lập về mặt logic, đặt trong một lớp Java đã import InputStream,
// OutputStream, IOException; dùng khi nguồn là entry không tin cậy.
static long copyAtMost(InputStream input,
                       OutputStream output,
                       long maxBytes) throws IOException {
    if (maxBytes < 0) {
        throw new IllegalArgumentException("maxBytes < 0");
    }

    byte[] bytes = new byte[8192];
    long total = 0;
    int n;
    while ((n = input.read(bytes)) != -1) {
        if (n > maxBytes - total) {
            throw new IOException("Entry exceeds size limit");
        }
        output.write(bytes, 0, n);
        total += n;
    }
    return total;
}
```

Hàm này giới hạn byte **thực đọc/ghi**; phép `maxBytes - total` không tràn nếu `maxBytes` không âm và `total` được giữ không vượt ngưỡng. Với output file, nếu vượt ngưỡng, **phải xóa file tạm đang ghi dở** trong quy trình cleanup. Muốn xử lý archive nhiều entry còn cần tổng ngân sách toàn archive, giới hạn số entry, hạn mức thời gian/CPU và chính sách file name.

`ZipEntry.getSize()` có thể dùng để từ chối sớm entry được khai báo quá lớn nhưng **không thay thế kiểm soát số byte thực giải nén**. Metadata có thể thiếu (`-1`) hoặc không đáng tin; giới hạn phải áp dụng ngay khi đọc stream.

## 8. Bảo mật khi trích xuất: Zip Slip và đường dẫn đích

Một ZIP từ bên ngoài có thể chứa entry tên:

```text
../../outside.txt
/absolute/path.txt
safe/../outside.txt
```

Nếu chương trình nối tên entry trực tiếp vào đường dẫn đích mà không kiểm tra, dữ liệu có thể bị ghi **ra ngoài thư mục giải nén dự kiến** (*Zip Slip/path traversal*). Một bước bảo vệ căn bản là chuẩn hóa đường dẫn và xác minh vẫn nằm dưới thư mục đích:

```java
// Đoạn minh họa về kiểm tra đường dẫn, chưa phải bộ giải nén an toàn đầy đủ.
Path root = destinationRoot.toAbsolutePath().normalize();
Path target = root.resolve(entry.getName()).normalize();

if (!target.startsWith(root) || target.equals(root)) {
    throw new IOException("Unsafe entry path: " + entry.getName());
}
```

Đừng dùng `String.startsWith(root.toString())` để kiểm tra containment: tiền tố chuỗi như `/safe/out` và `/safe/outside` có thể gây nhầm. Hãy dùng `Path.startsWith(Path)` sau `normalize()`, theo ngữ nghĩa đường dẫn của filesystem.

**Lưu ý cực kỳ quan trọng:** Kiểm tra lexical `normalize()` / `startsWith()` **không đủ an toàn khi thư mục đích có symbolic link hoặc bị tác nhân khác thay đổi đồng thời**. Ví dụ `root/link` là symlink trỏ ra ngoài, thì `root/link/file.txt` vượt qua kiểm tra lexical nhưng việc ghi thực có thể đi ra ngoài root. Nếu trích xuất ZIP không tin cậy:

1. Ưu tiên giải nén vào **thư mục riêng mới tạo, không cho bên không tin cậy chỉnh sửa**, với quyền truy cập tối thiểu.
2. Từ chối entry có tên không hợp lệ, đường dẫn tuyệt đối, thành phần đi ngược cha (`..`) hoặc tên không tương thích quy ước triển khai. Khi chạy đa nền tảng, xử lý dấu phân cách và tên đặc biệt trên hệ điều hành đích.
3. Kiểm tra đường dẫn sau chuẩn hóa, nhưng **không coi đây là lá chắn duy nhất** trước symlink/race. Với yêu cầu đối kháng mạnh, dùng thao tác filesystem không đi theo symlink hoặc cơ chế truy cập directory descriptor phù hợp nền tảng.
4. Chỉ tạo thư mục/tệp dưới root đã được kiểm soát; có chính sách xử lý entry trùng tên, file đã tồn tại và tranh chấp.
5. Giới hạn số entry, kích thước mỗi entry, tổng kích thước giải nén và độ sâu đường dẫn; dùng stream để kiểm soát tài nguyên.
6. Không coi ZIP là định dạng đã được xác thực về nguồn gốc hoặc tính toàn vẹn đối kháng. Nếu cần xác thực, dùng chữ ký hoặc cơ chế integrity/authentication riêng.

Những quy tắc này áp dụng khi **ghi dữ liệu ra filesystem**. Nếu chỉ đọc byte của một entry trong bộ nhớ, không có path traversal từ việc gọi `getEntry()`, nhưng vẫn có rủi ro về tiêu thụ bộ nhớ/CPU do dữ liệu nén độc hại.

## 9. ZipFile và ZipInputStream: chọn API theo nhu cầu

| Tiêu chí | `ZipFile` | `ZipInputStream` |
| --- | --- | --- |
| Nguồn dữ liệu | File ZIP có thể mở bằng `File` | `InputStream` chứa luồng ZIP |
| Truy cập entry theo tên | `getEntry(name)` trực tiếp | Thường phải đọc từng entry theo thứ tự bằng `getNextEntry()` |
| Duyệt danh sách entry | `entries()`, `stream()` | Vòng `getNextEntry()` / `closeEntry()` |
| Luồng đọc nội dung | `zip.getInputStream(entry)` cho entry được chọn | Đọc trực tiếp từ `ZipInputStream` của entry hiện hành |
| Metadata archive | Có thể tra từ cấu trúc ZIP, gồm central directory | Có thể chỉ biết một phần metadata trước khi đọc entry |
| Quản lý tài nguyên | `ZipFile` và từng `InputStream` | `ZipInputStream` làm tài nguyên chính |
| Tình huống nên dùng | Đọc một vài entry được biết tên trong ZIP đã lưu | Xử lý ZIP đến từ network stream hoặc luồng tuần tự |

Không có lựa chọn “luôn nhanh hơn”. Với archive nằm trên đĩa và chỉ cần một entry, `ZipFile` tránh phải duyệt payload của mọi entry theo trình tự. Nếu dữ liệu ZIP đang đến qua HTTP/socket dưới dạng luồng và không được lưu thành tệp, `ZipInputStream` phù hợp hơn.

`ZipFile` cũng không đồng nghĩa với ánh xạ toàn bộ archive vào bộ nhớ. Điều đáng quan tâm khi chọn API là **có cần tra entry theo tên và có khả năng truy cập một tệp ZIP đã tồn tại hay không**.

## 10. Lỗi thường gặp và cách khắc phục

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Quên đóng `ZipFile` | Giữ file descriptor/tài nguyên, có thể cản trở xóa/đổi tên file tùy hệ điều hành | `try-with-resources` cho archive |
| Lấy stream rồi đóng `ZipFile` trước khi đọc | Đọc thất bại vì tài nguyên nguồn đã đóng | Giữ ZipFile sống lâu hơn tất cả stream |
| Không đóng `InputStream` của entry | Khó kiểm soát giải phóng tài nguyên và phạm vi đọc | `try-with-resources` lồng bên trong ZipFile |
| Không kiểm tra `getEntry(name) == null` | `NullPointerException` hoặc logic lỗi | Kiểm tra missing entry trước khi mở stream |
| Đọc entry thư mục như file thường | Xử lý dữ liệu sai mục đích | Kiểm tra `isDirectory()` |
| Nghĩ `getEntry()` đã đọc toàn bộ payload | Ước lượng sai I/O/bộ nhớ | Đọc `InputStream` và đóng đúng lúc |
| Dùng `readAllBytes()` cho ZIP không tin cậy | Có thể cạn RAM vì ZIP bomb | Đọc theo luồng, đặt hạn mức bytes |
| Dựa duy nhất vào `getSize()` | Metadata có thể thiếu hoặc không đáng tin | Kiểm soát byte thực giải nén |
| Dùng tên entry làm đường dẫn đích mà không kiểm tra | Zip Slip ghi ra ngoài thư mục dự kiến | Normalize, containment và phòng symlink/race |
| Tự giả định thứ tự duyệt entry | Output không ổn định hoặc sai thứ tự nghiệp vụ | Sort khi cần hoặc thiết kế xử lý không dựa vào thứ tự |
| Coi tên entry giống path của OS | Sai dấu phân cách, sai tên hoặc trích xuất không an toàn | Phân biệt tên ZIP với path ở filesystem đích |
| Coi CRC-32 là chữ ký xác thực | Không phát hiện sửa đổi có chủ đích theo mô hình bảo mật mạnh | Dùng chữ ký/kiểm tra xác thực phù hợp |
| Gọi `ZipFile.getInputStream()` với entry tên trùng mà không có chính sách | Có thể lấy sai bản khi ZIP có tên trùng | Duyệt, từ chối trùng nếu cần tính duy nhất |
| Xóa/di chuyển ZIP khi `ZipFile` đang mở | Hành vi khác nhau theo OS, có thể thất bại | Đóng archive rồi mới thay đổi file |

## 11. Câu hỏi tự kiểm tra

**1. Nếu chỉ cần đọc `docs/readme.txt` từ một ZIP lớn trên đĩa, dùng gì?**  
Mở `ZipFile`, gọi `getEntry("docs/readme.txt")`, kiểm tra kết quả rồi `getInputStream()` cho đúng entry. Không cần lần lượt giải nén các entry trước nó.

**2. `ZipFile.close()` có tương đương `InputStream.close()` không?**  
Đóng `ZipFile` sẽ đóng những stream mà nó cấp, nhưng quản lý stream bằng khối `try-with-resources` riêng là thiết kế rõ ràng hơn. Ngược lại, đóng **một** stream entry không có nghĩa đóng toàn bộ `ZipFile`.

**3. Có thể trả `InputStream` của entry từ một phương thức đã đóng `ZipFile` trong `try-with-resources` không?**  
Không nên: stream phụ thuộc archive còn mở. Hãy xử lý nội dung trong phạm vi ZipFile còn sống, hoặc thiết kế một tài nguyên sở hữu cả ZipFile và stream và phải được caller đóng đúng cách.

**4. Khi `entry.getSize()` nhỏ, đã đủ chắc chắn an toàn để giải nén vào RAM chưa?**  
Chưa. ZIP không tin cậy cần giới hạn số byte thực đọc, số entry, tổng byte, nguồn dữ liệu và tài nguyên khác.

**5. `zip.stream().close()` có thay thế `zip.close()` không?**  
Không. `ZipFile` vẫn là chủ sở hữu tài nguyên archive, cần đóng rõ ràng.

**Ghi nhớ:** `ZipFile` cho phép tra cứu và đọc **từng entry** trong archive ZIP đã tồn tại. Mở `ZipFile` ở phạm vi ngoài, mở/đóng `InputStream` của entry ở phạm vi trong, luôn kiểm tra entry thiếu, không giả định metadata/trật tự duyệt và giới hạn việc giải nén dữ liệu không tin cậy. Quản lý vòng đời đúng giúp tránh lỗi đọc archive đã đóng, rò rỉ tài nguyên và các lỗ hổng khi trích xuất.